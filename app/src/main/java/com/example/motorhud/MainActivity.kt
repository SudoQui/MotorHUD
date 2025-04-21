package com.example.motorhud

import android.Manifest
import android.content.pm.PackageManager
import android.location.Location
import android.os.Bundle
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import com.google.android.gms.location.*
import android.util.Log
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import androidx.annotation.RequiresPermission
import java.io.OutputStream
import java.util.*

/* --------- Globals --------- */
private var destinationLat = 0.0
private var destinationLon = 0.0

class MainActivity : AppCompatActivity() {

    /* ---------- Bluetooth ---------- */
    private val deviceName = "ESP32_HUD"
    private val uuid: UUID = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb")
    private var bluetoothAdapter: BluetoothAdapter? = null
    private var btSocket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null

    /* ---------- Location ---------- */
    private lateinit var fusedLocationClient: FusedLocationProviderClient
    private lateinit var locationCallback: LocationCallback
    private lateinit var locationRequest: LocationRequest

    /* ---------- UI ---------- */
    private lateinit var destinationInput: EditText
    private lateinit var directionsText: TextView
    private lateinit var sentTextView: TextView
    private val LOCATION_PERMISSION_REQUEST_CODE = 1000

    /* ---------- Lifecycle ---------- */
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        /*  UI handles  */
        destinationInput = findViewById(R.id.destinationInput)
        directionsText   = findViewById(R.id.directionsText)
        sentTextView     = findViewById(R.id.sentTextView)
        val getLocationButton: Button = findViewById(R.id.getLocationButton)

        /*  Location & BT setup  */
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)
        bluetoothAdapter    = BluetoothAdapter.getDefaultAdapter()
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT)
            == PackageManager.PERMISSION_GRANTED) connectToESP32()
        else ActivityCompat.requestPermissions(
            this, arrayOf(Manifest.permission.BLUETOOTH_CONNECT), 101)

        /*  Create high‑accuracy request (every 5 s OR 5 m) */
        locationRequest = LocationRequest.Builder(
            Priority.PRIORITY_HIGH_ACCURACY, 5000L
        ).setMinUpdateDistanceMeters(5f).build()

        /*  Button click ‑> geocode address and start nav  */
        getLocationButton.setOnClickListener {
            val addr = destinationInput.text.toString().trim()
            if (addr.isEmpty()) {
                directionsText.text = "Please enter a destination address"
                return@setOnClickListener
            }
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
                != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.ACCESS_FINE_LOCATION),
                    LOCATION_PERMISSION_REQUEST_CODE
                )
                return@setOnClickListener
            }
            /*  Get current fix once (to seed the first route) */
            fusedLocationClient.getCurrentLocation(
                Priority.PRIORITY_HIGH_ACCURACY, null
            ).addOnSuccessListener { loc ->
                if (loc == null) {
                    directionsText.text = "Couldn't get current location"
                    return@addOnSuccessListener
                }
                /*  Geocode destination */
                getLatLngFromAddress(addr) { dLat, dLon ->
                    destinationLat = dLat
                    destinationLon = dLon
                    /* First route immediately */
                    requestAndSendRoute(loc)
                    /* start continuous updates */
                    startLocationUpdates()
                }
            }
        }
    }

    /* ---------- Continuous GPS updates ---------- */
    private fun startLocationUpdates() {
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)
            != PackageManager.PERMISSION_GRANTED) return

        locationCallback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                val loc = result.lastLocation ?: return
                requestAndSendRoute(loc)          // every fresh fix
            }
        }
        fusedLocationClient.requestLocationUpdates(
            locationRequest, locationCallback, Looper.getMainLooper()
        )
    }

    /* ---------- Single route refresh ---------- */
    private fun requestAndSendRoute(loc: Location) {
        val apiKey = ""
        val url = "https://maps.googleapis.com/maps/api/directions/json" +
                "?origin=${loc.latitude},${loc.longitude}" +
                "&destination=$destinationLat,$destinationLon" +
                "&mode=driving&key=$apiKey"

        Thread {
            try {
                val client   = okhttp3.OkHttpClient()
                val request  = okhttp3.Request.Builder().url(url).build()
                val response = client.newCall(request).execute()
                val jsonObj  = org.json.JSONObject(response.body?.string())
                if (jsonObj.getString("status") != "OK") return@Thread

                val step = jsonObj.getJSONArray("routes")
                    .getJSONObject(0)
                    .getJSONArray("legs")
                    .getJSONObject(0)
                    .getJSONArray("steps")
                    .getJSONObject(0)

                val instruction = android.text.Html.fromHtml(
                    step.getString("html_instructions")
                ).toString()
                val distance = step.getJSONObject("distance").getString("text")
                val navMsg = "$distance $instruction"

                outputStream?.write((navMsg + "\n").toByteArray())
                Log.d("NAV", "Sent: $navMsg")
                runOnUiThread { sentTextView.text = "Sent: $navMsg" }

            } catch (e: Exception) { e.printStackTrace() }
        }.start()
    }

    /* ---------- Geocode utility ---------- */
    private fun getLatLngFromAddress(addr: String, cb: (Double, Double) -> Unit) {
        val apiKey = ""
        val url = "https://maps.googleapis.com/maps/api/geocode/json" +
                "?address=${addr.replace(" ", "+")}&key=$apiKey"
        Thread {
            try {
                val res = okhttp3.OkHttpClient()
                    .newCall(okhttp3.Request.Builder().url(url).build())
                    .execute().body?.string()
                val obj = org.json.JSONObject(res)
                val loc = obj.getJSONArray("results")
                    .getJSONObject(0)
                    .getJSONObject("geometry")
                    .getJSONObject("location")
                cb(loc.getDouble("lat"), loc.getDouble("lng"))
            } catch (e: Exception) { e.printStackTrace() }
        }.start()
    }

    /* ---------- Bluetooth connect ---------- */
    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private fun connectToESP32() {
        val dev = bluetoothAdapter?.bondedDevices?.find { it.name == deviceName } ?: run {
            findViewById<TextView>(R.id.directionsText).text = "HUD not paired!"; return
        }
        try {
            btSocket = dev.createRfcommSocketToServiceRecord(uuid)
            btSocket?.connect()
            outputStream = btSocket?.outputStream
            findViewById<TextView>(R.id.directionsText).text = "Connected to ESP32"
        } catch (e: Exception) {
            findViewById<TextView>(R.id.directionsText).text = "BT connection failed"
        }
    }

    /* ---------- Permission callback ---------- */
    override fun onRequestPermissionsResult(
        reqCode: Int, perms: Array<out String>, results: IntArray
    ) {
        super.onRequestPermissionsResult(reqCode, perms, results)
        if (reqCode == LOCATION_PERMISSION_REQUEST_CODE &&
            results.isNotEmpty() && results[0] == PackageManager.PERMISSION_GRANTED) {
            recreate()
        }
    }

    /* ---------- Stop updates when app paused ---------- */
    override fun onPause() {
        super.onPause()
        if (::locationCallback.isInitialized) {
            fusedLocationClient.removeLocationUpdates(locationCallback)
        }
    }
}