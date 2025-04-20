package com.example.motorhud

import android.Manifest
import android.content.pm.PackageManager
import android.location.Location
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import com.google.android.gms.location.FusedLocationProviderClient
import com.google.android.gms.location.LocationServices
import android.util.Log
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import androidx.annotation.RequiresPermission
import java.io.OutputStream
import java.util.*
import kotlin.concurrent.fixedRateTimer

// Global destination coords
private var destinationLat: Double = 0.0
private var destinationLon: Double = 0.0

data class NavStep(
    val instruction: String,
    val lat: Double,
    val lon: Double
)

class MainActivity : AppCompatActivity() {
    private lateinit var fusedLocationClient: FusedLocationProviderClient
    private lateinit var sentTextView: TextView
    private val LOCATION_PERMISSION_REQUEST_CODE = 1000
    private val deviceName = "ESP32_HUD"
    private val uuid: UUID = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb")

    private var bluetoothAdapter: BluetoothAdapter? = null
    private var btSocket: BluetoothSocket? = null
    private var outputStream: OutputStream? = null

    private lateinit var destinationInput: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        destinationInput = findViewById(R.id.destinationInput)
        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)
        bluetoothAdapter = BluetoothAdapter.getDefaultAdapter()

        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.BLUETOOTH_CONNECT)
            != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.BLUETOOTH_CONNECT),
                101
            )
        } else {
            connectToESP32()
        }

        val getLocationButton = findViewById<Button>(R.id.getLocationButton)
        val directionsText = findViewById<TextView>(R.id.directionsText)

        sentTextView = findViewById(R.id.sentTextView)

        getLocationButton.setOnClickListener {
            val destinationAddress = destinationInput.text.toString()

            if (destinationAddress.isBlank()) {
                directionsText.text = "Please enter a destination address"
                return@setOnClickListener
            }

            if (ActivityCompat.checkSelfPermission(
                    this, Manifest.permission.ACCESS_FINE_LOCATION
                ) != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this,
                    arrayOf(Manifest.permission.ACCESS_FINE_LOCATION),
                    LOCATION_PERMISSION_REQUEST_CODE
                )
            } else {
                fusedLocationClient.lastLocation.addOnSuccessListener { location: Location? ->
                    if (location != null) {
                        getLatLngFromAddress(destinationAddress) { destLat, destLon ->
                            destinationLat = destLat
                            destinationLon = destLon
                            startNavigationLoop()
                            getDirections(location.latitude, location.longitude)
                        }
                    } else {
                        directionsText.text = "Couldn't get current location"
                    }
                }
            }
        }
    }

    private fun startNavigationLoop() {
        fixedRateTimer("liveDirections", false, 0L, 5000L) {
            runOnUiThread {
                if (ActivityCompat.checkSelfPermission(
                        this@MainActivity,
                        Manifest.permission.ACCESS_FINE_LOCATION
                    ) == PackageManager.PERMISSION_GRANTED
                ) {
                    fusedLocationClient.lastLocation
                        .addOnSuccessListener { location: Location? ->
                            if (location != null) {
                                getDirections(location.latitude, location.longitude)
                            }
                        }
                }
            }
        }
    }

    private fun getLatLngFromAddress(address: String, callback: (lat: Double, lon: Double) -> Unit) {
        val apiKey = ""
        val url = "https://maps.googleapis.com/maps/api/geocode/json" +
                "?address=${address.replace(" ", "+")}&key=$apiKey"
        Log.d("GEOCODE_URL", url)

        Thread {
            try {
                val client = okhttp3.OkHttpClient()
                val request = okhttp3.Request.Builder().url(url).build()
                val response = client.newCall(request).execute()
                val json = response.body?.string()

                val jsonObject = org.json.JSONObject(json)
                val results = jsonObject.getJSONArray("results")
                if (results.length() == 0) {
                    runOnUiThread {
                        findViewById<TextView>(R.id.directionsText).text = "No results found for that address"
                    }
                    return@Thread
                }

                val location = results
                    .getJSONObject(0)
                    .getJSONObject("geometry")
                    .getJSONObject("location")

                val lat = location.getDouble("lat")
                val lon = location.getDouble("lng")

                runOnUiThread {
                    callback(lat, lon)
                }

            } catch (e: Exception) {
                e.printStackTrace()
            }
        }.start()
    }

    private fun getDirections(originLat: Double, originLon: Double) {
        val apiKey = ""
        val url = "https://maps.googleapis.com/maps/api/directions/json" +
                "?origin=$originLat,$originLon" +
                "&destination=$destinationLat,$destinationLon" +
                "&mode=driving&key=$apiKey"

        Thread {
            try {
                val client = okhttp3.OkHttpClient()
                val request = okhttp3.Request.Builder().url(url).build()
                val response = client.newCall(request).execute()
                val json = response.body?.string()

                val jsonObject = org.json.JSONObject(json)
                val status = jsonObject.getString("status")

                if (status != "OK") return@Thread

                val steps = jsonObject
                    .getJSONArray("routes")
                    .getJSONObject(0)
                    .getJSONArray("legs")
                    .getJSONObject(0)
                    .getJSONArray("steps")

                val step = steps.getJSONObject(0)
                val htmlInstruction = step.getString("html_instructions")
                val instruction = android.text.Html.fromHtml(htmlInstruction).toString()
                val distance = step.getJSONObject("distance").getString("text")

                val navMessage = "$distance $instruction"

                try {
                    outputStream?.write((navMessage + "\n").toByteArray())
                    Log.d("NAV", "Sent: $navMessage")
                    runOnUiThread {
                        sentTextView.text = "Sent: $navMessage"
                    }
                } catch (e: Exception) {
                    e.printStackTrace()
                }

            } catch (e: Exception) {
                e.printStackTrace()
            }
        }.start()
    }

    @RequiresPermission(Manifest.permission.BLUETOOTH_CONNECT)
    private fun connectToESP32() {
        val pairedDevices: Set<BluetoothDevice>? = bluetoothAdapter?.bondedDevices
        val device = pairedDevices?.find { it.name == deviceName }

        if (device == null) {
            runOnUiThread {
                findViewById<TextView>(R.id.directionsText).text = "HUD not paired!"
            }
            return
        }

        try {
            btSocket = device.createRfcommSocketToServiceRecord(uuid)
            btSocket?.connect()
            outputStream = btSocket?.outputStream
            runOnUiThread {
                findViewById<TextView>(R.id.directionsText).text = "Connected to ESP32"
            }
        } catch (e: Exception) {
            e.printStackTrace()
            runOnUiThread {
                findViewById<TextView>(R.id.directionsText).text = "BT connection failed"
            }
        }
    }

    private fun calculateDistance(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Float {
        val result = FloatArray(1)
        Location.distanceBetween(lat1, lon1, lat2, lon2, result)
        return result[0]
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == LOCATION_PERMISSION_REQUEST_CODE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                recreate()
            }
        }
    }
}
