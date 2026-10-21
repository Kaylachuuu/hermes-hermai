plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "dev.hermai.herma"
    compileSdk = 34

    defaultConfig {
        applicationId = "dev.hermai.herma"
        minSdk = 26
        targetSdk = 33 // the Galaxy Tab Active3 stops at Android 13
        versionCode = 3
        versionName = "0.2.0"
        // sherpa-onnx ships native code for four kinds of processor; tablets and phones are ARM.
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a") }
    }

    signingConfigs {
        // A fixed debug key, so each new build installs over the last one without uninstalling.
        getByName("debug") {
            storeFile = file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }

    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("debug") }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    // "Hey Athena": the sherpa-onnx library and its model come from ./fetch-wake-word.sh, not git.
    implementation(files("libs/sherpa-onnx-1.13.8.aar"))
}
