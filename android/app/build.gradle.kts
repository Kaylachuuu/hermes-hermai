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
        versionCode = 2
        versionName = "0.1.1"
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
