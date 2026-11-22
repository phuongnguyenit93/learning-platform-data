# Android Gradle Plugin: module, build type, product flavor và variant

## 1. Đặt bài học trong Hệ sinh thái Gradle

**Android Gradle Plugin (AGP)** mở rộng Gradle để xây dựng ứng dụng và thư viện Android. Gradle đảm nhiệm task graph, dependency resolution, incremental execution, build cache và multi-project build; AGP bổ sung mô hình Android SDK, manifest, resources, DEX, APK/AAB/AAR, signing, testing và đặc biệt là **build variants**.

Một nhóm phát triển có thể dùng cùng repository để tạo bản debug phục vụ lập trình, bản release phát hành, bản demo hạn chế chức năng và bản full. Các cấu hình này không cần bốn codebase riêng. AGP tạo các **tổ hợp có kiểm soát** từ build types, product flavors, source sets, dependencies và variant rules.

Bốn khái niệm phải phân biệt:

- **Module:** đơn vị Gradle project, ví dụ `:app` hoặc `:core`; được khai bằng `include` trong `settings.gradle`.
- **Build type:** cách build một sản phẩm, thường `debug`/`release`, liên quan debuggability, shrinking, signing, build-type-specific sources.
- **Product flavor:** phiên bản của sản phẩm, ví dụ `demo`/`full`, `free`/`paid`, `us`/`eu`; mỗi flavor thuộc một **flavor dimension**.
- **Build variant:** một tổ hợp **một build type + một flavor từ mỗi dimension** của cùng module, có code/resources/dependencies/tasks/artifacts tương ứng.

### 1.1. Sau bài học, bạn có thể

1. Chọn đúng `com.android.application`, `com.android.library`, `java-library` hoặc dynamic-feature plugin theo module.
2. Phân biệt root project, module, source set, Android build variant và Gradle variant-aware dependency.
3. Khai `namespace`, `applicationId`, `defaultConfig`, `compileSdk`/`minSdk`/`targetSdk`.
4. Thiết kế `buildTypes`, `productFlavors`, `flavorDimensions`; đếm và đặt tên variants.
5. Hiểu source-set priority `variant > build type > flavor > main > library`.
6. Giải thích `applicationIdSuffix` và tại sao `namespace`/Java package không cần đổi theo app ID.
7. Biết Gradle tasks `assembleDemoDebug`, `bundleFullRelease`, `testDemoDebugUnitTest` và `connectedDemoDebugAndroidTest`.
8. Dùng `matchingFallbacks`, `missingDimensionStrategy` khi Android library có cấu hình khác app.
9. Hiểu `androidComponents.beforeVariants`/`onVariants` trong modern AGP APIs.
10. Chạy project Android hai module bằng **Gradle Groovy DSL và Java 17**, cùng một Java17 program độc lập cho stdout chính xác.
11. Chẩn đoán mismatch AGP/Gradle/JDK/SDK, manifest/resource conflicts, duplicate Java classes, signing và variant explosion.

**Lưu ý:** Đây là bài Android build nên muốn build APK cần Android SDK và dependencies; chỉ chương trình Java CLI phụ trợ chạy bằng `javac`/`java` mà không cần SDK. Những version được chọn để ví dụ có thể tái lập, không tự nhận là phiên bản mới nhất ở mọi thời điểm.

## 2. Sơ đồ modules và variants

~~~text
Gradle build: variant-lab
  settings.gradle
    |
    +-- :app  (com.android.application)
    |      buildTypes: debug, release
    |      flavorDimensions: tier
    |      productFlavors: demo, full
    |      variants:
    |         demoDebug
    |         demoRelease
    |         fullDebug
    |         fullRelease
    |
    +-- :core (com.android.library)
           buildTypes: debug, release
           productFlavors: không có
           library variants: debug, release

:app:demoDebug   --->  :core:debug
:app:demoRelease --->  :core:release
:app:fullDebug   --->  :core:debug
:app:fullRelease --->  :core:release
~~~

**Điểm quan trọng:** `demoDebug` là **variant bên trong `:app`**, không phải một Gradle module tên `:demoDebug`. `src/demoDebug` là **source set**, cũng không phải module độc lập.

### 2.1. Công thức số variants

Giả sử một module có \(B\) build types và có \(n\) flavor dimensions, mỗi dimension thứ \(i\) có \(F_i\) flavors:

\[
V = B \times \prod_{i=1}^{n} F_i
\]

Nếu không có product flavor, coi phần tích bằng 1. Ví dụ:
- 2 build types, không flavors ⇒ **2 variants**.
- 2 build types × 2 flavors ở dimension `tier` ⇒ **4 variants**.
- 3 build types × 2 flavors `tier` × 2 flavors `region` ⇒ **12 variants**.
- 2 build types × 3 tiers × 4 regions × 2 channels ⇒ **48 variants**.

Đây là số **tổ hợp sản phẩm trước khi filter**. Nếu dùng `androidComponents.beforeVariants` để disable một số tổ hợp, số variants được tạo thật giảm. Test components/tasks không phải một build type được cộng thêm vào công thức.

### 2.2. Ma trận tên cho một dimension

| Flavor / Build type | debug | release |
| --- | --- | --- |
| demo | `demoDebug` | `demoRelease` |
| full | `fullDebug` | `fullRelease` |

Tên ghép flavor trước, build type sau và viết hoa chữ đầu tên build type: `demo` + `Debug` → `demoDebug`. Nếu có nhiều dimensions, tên ghép lần lượt các flavors theo **thứ tự dimension**, rồi tới build type.

## 3. Các loại module trong hệ sinh thái Android Gradle

| Module | Plugin | Sản phẩm hoặc nhiệm vụ |
| --- | --- | --- |
| Ứng dụng Android | `com.android.application` | APK hoặc Android App Bundle (AAB) |
| Android library | `com.android.library` | AAR chứa Android Java/Kotlin code, resources và manifest |
| Java-only library | `java-library` | JAR JVM, không có Android resource processing |
| Dynamic Feature | `com.android.dynamic-feature` | Feature module gắn với base app trong Android App Bundle |
| Android test-only | `com.android.test` | Test module dành cho trường hợp Android instrumentation riêng |

**Product flavor khác dynamic feature:** flavor chọn cách build ứng dụng; dynamic feature là một module Android phân phối theo App Bundle. Một flavor không tự làm tính năng được tải động từ Google Play.

`settings.gradle` quyết định có những Gradle projects nào. `app/build.gradle` quyết định plugin và variants của app. `implementation project(':core')` là **một dependency edge**, không tạo `:core` nếu settings chưa khai module ấy.

### 3.1. Android plugin không giống core Java plugin

| Chủ đề | `java`/`application` plugin | Android Gradle Plugin |
| --- | --- | --- |
| Artifact | JAR/JVM distribution | APK/AAB/AAR |
| Compile APIs | Java classpath/JDK | Android SDK API và Java/Kotlin compilers |
| Manifest/resources | Không có Android manifest/R | Manifest merger, `R`, resources/assets |
| Variants | api/runtime Java variants | Build types/flavor variants và dependencies |
| Tests | JVM test | JVM unit tests và instrumentation tests |
| Install lên Android | Không có | `install...` khi có device/emulator |

**Không áp `java` plugin thêm vào `com.android.application` module chỉ để biên dịch Java.** AGP đã cung cấp Java source compilation và Android-specific tasks. Một `java-library` module thuần JVM có thể tồn tại cạnh Android modules, nhưng nó không được tự động coi là Android library AAR.

## 4. Bộ phiên bản mẫu có kiểm chứng

Để tránh dùng API/DSL của nhiều thế hệ plugin trong cùng project, bài chọn:

| Thành phần | Bản dùng trong ví dụ |
| --- | --- |
| Android Gradle Plugin | **8.9.2** |
| Gradle Wrapper | **8.11.1** |
| JVM chạy Gradle | **JDK 17** |
| Java source/bytecode target | **17** |
| Android compile SDK | **35** |
| Android target SDK | **35** |
| Android minimum SDK | **24** |
| Android SDK Build Tools | **35.0.0** |
| Unit testing | JUnit **4.13.2** |

Theo [release notes AGP 8.9](https://developer.android.com/build/releases/agp-8-9-0-release-notes), AGP 8.9 yêu cầu Gradle tối thiểu **8.11.1**, JDK **17**, hỗ trợ tối đa Android API **35**, và có bản patch **8.9.2**. Đây là một **bộ phiên bản cụ thể cho học tập**, không phải kết luận AGP 8.9.2 là bản Android plugin mới nhất. Khi nâng AGP 9.x phải đọc [bảng compatibility](https://developer.android.com/build/releases/about-agp) và migration notes.

### 4.1. Cần chuẩn bị gì?

- Android SDK **Platform 35** và Build Tools **35.0.0**, qua Android Studio SDK Manager hoặc `sdkmanager`.
- JDK 17 phù hợp để chạy Gradle daemon.
- Gradle Wrapper 8.11.1 đã được sinh từ Gradle distribution được tin cậy.
- Network hoặc cache để lấy AGP từ Google Maven và JUnit từ Maven Central.
- Android emulator/device nếu muốn **chạy giao diện**, không cần device để `assemble`.

Kiểm tra:

~~~bash
java -version
./gradlew --version
sdkmanager --list
~~~

Khi Android command-line tools đã được cài:

~~~bash
sdkmanager "platforms;android-35" "build-tools;35.0.0"
~~~

Cần chấp nhận SDK licenses theo cơ chế của Android Studio hoặc command-line tools; không coi một build thiếu license là lỗi Java source.

### 4.2. Wrapper phải thực sự có file nhị phân

Repository cần đủ:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

Có thể sinh Wrapper từ bản Gradle tin cậy trên máy setup:

~~~bash
gradle wrapper --gradle-version 8.11.1 --distribution-type bin
~~~

`gradle/wrapper/gradle-wrapper.properties` điển hình:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.11.1-bin.zip
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

File properties **không tự tạo** scripts/JAR. Khi đưa vào CI/release, nên bổ sung `distributionSha256Sum` lấy từ checksum **chính thức đúng ZIP 8.11.1 -bin**, và validate Wrapper JAR. Không tự bịa checksum hoặc copy JAR không rõ nguồn.

### 4.3. Java version ≠ Android API version

- JVM17 là runtime để chạy Gradle/AGP.
- `sourceCompatibility/targetCompatibility=17` là Java language/bytecode target.
- `compileSdk35` là Android APIs dùng khi compile.
- `minSdk24` là Android API thấp nhất ứng dụng tuyên bố hỗ trợ.
- `targetSdk35` ảnh hưởng hành vi hệ điều hành mà ứng dụng opt-in.
- Android Runtime không phải desktop JVM17; không được giả định mọi JDK17 API đều có trên thiết bị minSdk24. Một số API yêu cầu core library desugaring hoặc minimum Android version thích hợp.

## 5. `namespace`, `applicationId`, Java package

Trong AGP hiện đại:

~~~groovy
android {
    namespace 'dev.example.variantlab'

    defaultConfig {
        applicationId 'dev.example.variantlab'
    }
}
~~~

**`namespace`** là namespace của generated Android `R` và `BuildConfig`. **`applicationId`** là identity của ứng dụng cài trên thiết bị hoặc được phát hành. **Java package** là package declaration của classes, có thể thống nhất với namespace để thuận tiện, nhưng applicationId có thể khác.

Ví dụ `demo` thêm `.demo` và `debug` thêm `.debug`:

~~~text
Application ID variant demoDebug: dev.example.variantlab.demo.debug
Java package MainActivity:       dev.example.variantlab
Generated BuildConfig namespace: dev.example.variantlab
~~~

Không sửa Java `package` theo mọi `applicationIdSuffix`. Android library module khai `namespace` nhưng không dùng `applicationId` như application module. Với AGP 8.x, namespace nên khai trong Gradle DSL; đừng dựa vào `package` trong AndroidManifest của một mẫu project cũ.

## 6. Lab hoàn chỉnh: Android app Java17 có bốn variants và thư viện dùng chung

Ta tạo repository `variant-lab` gồm:
- `:app` Android application có `debug`/`release` và `demo`/`full`.
- `:core` Android library chỉ có `debug`/`release`, cung cấp class Java `GreetingFormatter`.
- `MainActivity` hiển thị `BuildConfig.FLAVOR`, `BuildConfig.BUILD_TYPE` và resources đã merge.
- `app_name` thay theo flavor/variant, `channel_name` thay theo build type.
- JUnit4 local tests trong `:core`.
- `tools/VariantMatrix.java` chạy độc lập, in đúng tên 4 variants.

### 6.1. Cây thư mục

~~~text
variant-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── app/
│   ├── build.gradle
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml
│       │   ├── java/dev/example/variantlab/MainActivity.java
│       │   └── res/values/strings.xml
│       ├── demo/res/values/strings.xml
│       ├── full/res/values/strings.xml
│       ├── debug/res/values/strings.xml
│       └── demoDebug/res/values/strings.xml
├── core/
│   ├── build.gradle
│   └── src/
│       ├── main/
│       │   ├── AndroidManifest.xml
│       │   └── java/dev/example/core/GreetingFormatter.java
│       └── test/java/dev/example/core/GreetingFormatterTest.java
└── tools/
    └── VariantMatrix.java
~~~

Không cần Kotlin/AndroidX/Compose cho project này. Không có `src/release/res` hay `src/fullDebug/res` cũng hợp lệ vì chúng **tùy chọn**; AGP dùng những source sets hiện có.

### 6.2. Root `settings.gradle`

~~~groovy
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = 'variant-lab'
include ':app', ':core'
~~~

- `pluginManagement.repositories` tìm AGP plugin implementation/marker metadata; `google()` quan trọng.
- `dependencyResolutionManagement.repositories` dùng cho libraries như JUnit.
- `RepositoriesMode.FAIL_ON_PROJECT_REPOS` tránh mỗi module tự thêm repository ngoài source policy.
- `include` tạo hai Gradle modules, không tạo các Android variants.

### 6.3. Root `build.gradle`

~~~groovy
plugins {
    id 'com.android.application' version '8.9.2' apply false
    id 'com.android.library' version '8.9.2' apply false
}
~~~

`apply false` pin plugin versions tại root nhưng không áp plugin Android app/library lên root. `:app` và `:core` áp đúng plugin riêng trong file module.

### 6.4. `app/build.gradle` — runnable Groovy DSL

~~~groovy
plugins {
    id 'com.android.application'
}

android {
    namespace 'dev.example.variantlab'
    compileSdk 35

    defaultConfig {
        applicationId 'dev.example.variantlab'
        minSdk 24
        targetSdk 35
        versionCode 1
        versionName '1.0'
    }

    buildFeatures {
        buildConfig true
    }

    buildTypes {
        debug {
            applicationIdSuffix '.debug'
            versionNameSuffix '-debug'
            debuggable true
        }

        release {
            minifyEnabled false
        }
    }

    flavorDimensions 'tier'

    productFlavors {
        demo {
            dimension 'tier'
            applicationIdSuffix '.demo'
            versionNameSuffix '-demo'
        }

        full {
            dimension 'tier'
        }
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}

dependencies {
    implementation project(':core')
}
~~~

**Giải thích thiết kế:**

1. `com.android.application` tạo app variants/APK/AAB pipeline.
2. `namespace` là namespace của generated Android code, không tự đổi khi `applicationIdSuffix` thay.
3. `compileSdk35` dùng SDK35 khi biên dịch; `minSdk24` và `targetSdk35` có nghĩa khác.
4. `defaultConfig` cho defaults của các flavors/variants.
5. `buildConfig true` đảm bảo `BuildConfig` được generate khi code đọc `BuildConfig.FLAVOR`/`BUILD_TYPE`. AGP8.x có thể disable generation mặc định nên khai rõ.
6. `debug` có ID suffix `.debug` và nhãn `-debug`.
7. `release` để `minifyEnabled false` cho lab, không phải recommendation cho mọi production app.
8. `flavorDimensions 'tier'` nhóm flavors thành một chiều.
9. `demo` thêm ID suffix `.demo`; `full` kế thừa app ID gốc.
10. `compileOptions` chọn Java17 source/bytecode; không thay Android compileSdk.
11. `implementation project(':core')` cho phép app code gọi Java library classes và AGP chọn library variant thích hợp.
12. Lab chưa có release signing config; **release artifacts chưa chắc ký hợp lệ để phân phối**. Debug thường được AGP ký bằng debug keystore.

### 6.5. `core/build.gradle`

~~~groovy
plugins {
    id 'com.android.library'
}

android {
    namespace 'dev.example.core'
    compileSdk 35

    defaultConfig {
        minSdk 24
    }

    compileOptions {
        sourceCompatibility JavaVersion.VERSION_17
        targetCompatibility JavaVersion.VERSION_17
    }
}

dependencies {
    testImplementation 'junit:junit:4.13.2'
}
~~~

`:core` tạo Android library AAR, không phải APK cài đặt. Nó có `debug` và `release` library variants. Vì không có flavor dimension `tier`, library không phải tạo `demoDebug`/`fullRelease`. App variants vẫn resolve được appropriate library build type. JUnit dùng cho `core/src/test`, không phải một dependency để chạy trong Android APK.

### 6.6. `core/src/main/AndroidManifest.xml`

~~~xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android" />
~~~

Android library có manifest tối giản và namespace được khai trong Gradle DSL.

### 6.7. `core/src/main/java/dev/example/core/GreetingFormatter.java`

~~~java
package dev.example.core;

public final class GreetingFormatter {

    private GreetingFormatter() {
    }

    public static String label(String flavor, String buildType) {
        return "Variant: " + flavor + "/" + buildType;
    }
}
~~~

Đây là Java code độc lập với Android SDK APIs; khi dùng trong app, nó được compile/package như một phần library dependency.

### 6.8. `core/src/test/java/dev/example/core/GreetingFormatterTest.java`

~~~java
package dev.example.core;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

public final class GreetingFormatterTest {

    @Test
    public void rendersDebug() {
        assertEquals(
            "Variant: demo/debug",
            GreetingFormatter.label("demo", "debug")
        );
    }

    @Test
    public void rendersRelease() {
        assertEquals(
            "Variant: full/release",
            GreetingFormatter.label("full", "release")
        );
    }
}
~~~

Hai local JVM unit tests không cần emulator, nhưng cần Android project được cấu hình với AGP/SDK phù hợp và dependency JUnit đã resolve.

### 6.9. `app/src/main/AndroidManifest.xml`

~~~xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:label="@string/app_name"
        android:allowBackup="false"
        android:theme="@android:style/Theme.Material.Light.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
~~~

`android:exported="true"` được khai cho Activity có launcher intent filter trên các target Android versions hiện đại. Manifest không cần khai `package` thay namespace. `@string/app_name` lấy từ merged resources của variant đang build.

### 6.10. `app/src/main/java/dev/example/variantlab/MainActivity.java`

~~~java
package dev.example.variantlab;

import android.app.Activity;
import android.os.Bundle;
import android.widget.TextView;

import dev.example.core.GreetingFormatter;

public final class MainActivity extends Activity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        String variant = GreetingFormatter.label(
            BuildConfig.FLAVOR,
            BuildConfig.BUILD_TYPE
        );

        TextView textView = new TextView(this);
        textView.setText(
            variant + "\n"
                + getString(R.string.app_name) + "\n"
                + getString(R.string.channel_name)
        );
        textView.setTextSize(20);
        textView.setPadding(32, 48, 32, 48);
        setContentView(textView);
    }
}
~~~

- `BuildConfig.FLAVOR` chọn `demo` hoặc `full`.
- `BuildConfig.BUILD_TYPE` chọn `debug` hoặc `release`.
- `GreetingFormatter.label` từ `:core` trả text có thể kiểm tra.
- `R.string.app_name` và `R.string.channel_name` phản ánh resources overlays.
- Kết quả hiển thị trong Android UI **không phải stdout từ Java `main`**.

### 6.11. Resource file chung `app/src/main/res/values/strings.xml`

~~~xml
<resources>
    <string name="app_name">Variant Lab</string>
    <string name="channel_name">Production</string>
</resources>
~~~

### 6.12. Flavor `app/src/demo/res/values/strings.xml`

~~~xml
<resources>
    <string name="app_name">Demo Variant Lab</string>
</resources>
~~~

### 6.13. Flavor `app/src/full/res/values/strings.xml`

~~~xml
<resources>
    <string name="app_name">Full Variant Lab</string>
</resources>
~~~

### 6.14. Build type `app/src/debug/res/values/strings.xml`

~~~xml
<resources>
    <string name="channel_name">Development</string>
</resources>
~~~

### 6.15. Variant `app/src/demoDebug/res/values/strings.xml`

~~~xml
<resources>
    <string name="app_name">Demo Debug Lab</string>
</resources>
~~~

Có cùng resource key `app_name` tại main, demo và demoDebug. **Đây là overlay hợp lệ** vì AGP có priority giữa source sets. Không tạo một duplicated Java class ở nhiều source sets cùng tham gia và tưởng có thể overlay giống resources.

### 6.16. UI mong đợi của từng app variant

| Variant | Dòng 1 | Dòng 2 (`app_name`) | Dòng 3 (`channel_name`) |
| --- | --- | --- | --- |
| `demoDebug` | `Variant: demo/debug` | `Demo Debug Lab` | `Development` |
| `demoRelease` | `Variant: demo/release` | `Demo Variant Lab` | `Production` |
| `fullDebug` | `Variant: full/debug` | `Full Variant Lab` | `Development` |
| `fullRelease` | `Variant: full/release` | `Full Variant Lab` | `Production` |

Đây là **ba dòng nội dung TextView**, không phải toàn bộ UI layout screenshot hay Gradle console output. Release variants chỉ chạy được trên thiết bị khi APK đã được ký/đóng gói hợp lệ.

### 6.17. Application ID của từng variant

| Variant | Application ID sau packaging |
| --- | --- |
| `demoDebug` | `dev.example.variantlab.demo.debug` |
| `demoRelease` | `dev.example.variantlab.demo` |
| `fullDebug` | `dev.example.variantlab.debug` |
| `fullRelease` | `dev.example.variantlab` |

AGP ghép suffix của flavor **trước** suffix của build type. Các IDs khác nhau cho phép các bản ứng dụng đã được ký đúng tồn tại song song trên device. Đừng nhầm việc ID khác với việc `MainActivity` phải đổi Java package.

## 7. Chạy Gradle tasks cho từng variant

Sau khi có JDK17/SDK35/Wrapper8.11.1:

~~~bash
./gradlew --version
./gradlew :app:tasks --all
./gradlew :app:assembleDemoDebug
./gradlew :app:assembleDemoRelease
./gradlew :app:assembleFullDebug
./gradlew :app:assembleFullRelease
./gradlew :app:bundleFullRelease
./gradlew :core:testDebugUnitTest
~~~

Giải thích:

| Task | Chức năng |
| --- | --- |
| `:app:assembleDemoDebug` | Build demoDebug APK |
| `:app:assembleFullRelease` | Build fullRelease APK, signing tùy cấu hình |
| `:app:bundleFullRelease` | Build Android App Bundle fullRelease |
| `:app:assembleDebug` | Aggregate các debug app variants được bật |
| `:app:assembleRelease` | Aggregate các release app variants được bật |
| `:app:assemble` | Lifecycle assemble theo các AGP variants |
| `:app:installDemoDebug` | Cài debug APK lên device/emulator tương thích |
| `:core:testDebugUnitTest` | Chạy JUnit4 local tests của library debug |
| `:app:testDemoDebugUnitTest` | Chạy local unit tests của app variant nếu có source |

Android Studio Build Variants window giúp chọn active variant cho IDE Run/Debug. Chọn variant trong IDE không tạo Gradle module mới; command line vẫn có thể build những variants khác qua task names.

### 7.1. Build không cần device, install cần device

~~~bash
./gradlew :app:assembleDemoDebug
adb devices
./gradlew :app:installDemoDebug
~~~

`assembleDemoDebug` compile/package APK trên máy build. `installDemoDebug` cần ADB nhìn thấy Android device/emulator phù hợp. Nếu `adb devices` rỗng, đừng kết luận source/Gradle plugin bị lỗi.

### 7.2. Output artifacts và đường dẫn

Output APK/AAB/AAR thường nằm dưới:

~~~text
app/build/outputs/apk/demo/debug/
app/build/outputs/apk/full/release/
app/build/outputs/bundle/fullRelease/
core/build/outputs/aar/
~~~

Tên file cụ thể có thể thay theo version AGP, signing, output metadata và plugins. **Không hard-code** một tên APK đoán trước trong release automation; lấy từ build output metadata hoặc Android Components Artifacts API nếu viết plugin.

### 7.3. Release không tự publishable

Lab không cấu hình keystore release, nên `assembleFullRelease` PASS **không** chứng minh có signed release APK được phép upload Play. Debug signing thường được AGP tự tạo; release signing cần keys/passwords được bảo vệ, approval và Play policy. Không dùng debug key cho production.

## 8. Java 17 độc lập: in ma trận với stdout chính xác

Android `MainActivity` không có JVM desktop `public static void main`. Để tự kiểm tra công thức variants bằng Java17 mà không cần Android SDK, tạo `tools/VariantMatrix.java`:

~~~java
public final class VariantMatrix {

    private VariantMatrix() {
    }

    public static void main(String[] args) {
        String[] flavors = {"demo", "full"};
        String[] types = {"debug", "release"};

        for (String flavor : flavors) {
            for (String type : types) {
                String variant = flavor
                    + Character.toUpperCase(type.charAt(0))
                    + type.substring(1);
                System.out.println(variant);
            }
        }
    }
}
~~~

Trên Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out tools/VariantMatrix.java
java -cp out VariantMatrix
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac --release 17 -encoding UTF-8 -d out tools/VariantMatrix.java
java -cp out VariantMatrix
~~~

**Stdout chính xác theo thứ tự dòng:**

~~~text
demoDebug
demoRelease
fullDebug
fullRelease
~~~

Chương trình mô phỏng tên bằng hai vòng lặp Java, không query AGP. `mkdir -p out` hoặc PowerShell `New-Item` đảm bảo output directory tồn tại trước khi `javac -d out`. Trên Windows, `println` có thể xuất CRLF thay vì LF, nhưng nội dung và thứ tự bốn dòng giữ nguyên.

**Phân biệt:**
- `java -cp out VariantMatrix`: Java17 CLI stdout, không yêu cầu Android SDK.
- `./gradlew :app:assembleDemoDebug`: Android packaging, không in bốn dòng của Java CLI.
- Android `MainActivity`: hiển thị UI TextView trên device, không phải stdout CLI.

## 9. Build type: điều kiện build, debug và release

AGP tạo `debug` và `release` build types mặc định. Có thể tùy chỉnh:

~~~groovy
android {
    buildTypes {
        debug {
            debuggable true
            applicationIdSuffix '.debug'
        }
        release {
            minifyEnabled true
        }
    }
}
~~~

**Đây là snippet thay thế**, không phải nguyên văn lab vì lab dùng `minifyEnabled false`. Nếu bật shrinking/minification, cần kiểm tra R8 rules, reflection, resources và regression tests.

Build-type-specific concerns:
- `debuggable` và debug signing cho development.
- Release signing/proguard/R8 khi cấu hình production.
- `applicationIdSuffix`/`versionNameSuffix`.
- Source sets `src/debug`/`src/release`.
- Dependencies `debugImplementation`/`releaseImplementation`.
- Manifest placeholders/resources khác nhau theo môi trường.

### 9.1. Tạo staging build type

Một app cần QA staging có thể thêm:

~~~groovy
android {
    buildTypes {
        debug {}
        release {}
        staging {
            initWith debug
            applicationIdSuffix '.staging'
            versionNameSuffix '-staging'
            matchingFallbacks = ['debug']
        }
    }
}
~~~

Ví dụ là **phần mở rộng**, không dán nguyên block thứ hai song song block lab nếu chưa hợp nhất. Khi app có demo/full và 3 build types, số variant là **2 × 3 = 6**:

~~~text
demoDebug
demoRelease
demoStaging
fullDebug
fullRelease
fullStaging
~~~

`matchingFallbacks` cho phép app staging chọn library debug nếu `:core` chỉ có debug/release. `initWith debug` cũng có thể kế thừa debug signing/debuggable settings: **staging không đồng nghĩa production-hardened release**.

### 9.2. Không đặt secret trong BuildConfig

Nếu đưa API token vào `buildConfigField` hoặc `resValue` thì nó được package trong APK; obfuscation không biến nó thành bí mật. Đặt secrets ở server, cấp quyền ở backend và chỉ ship public configuration phù hợp.

## 10. Product flavors và flavor dimensions

Một dimension có hai flavors:

~~~groovy
android {
    flavorDimensions 'tier'

    productFlavors {
        demo {
            dimension 'tier'
            applicationIdSuffix '.demo'
        }
        full {
            dimension 'tier'
        }
    }
}
~~~

Flavors có thể ảnh hưởng version name, app ID, resources, feature-specific source, dependencies, manifest placeholders và configuration. `defaultConfig` cho defaults; flavor-specific values có thể override defaults của phần tương ứng.

### 10.1. Hai dimensions

~~~groovy
android {
    flavorDimensions 'tier', 'region'

    productFlavors {
        demo { dimension 'tier' }
        full { dimension 'tier' }
        eu { dimension 'region' }
        us { dimension 'region' }
    }
}
~~~

Với `debug`/`release`, có tám variants:

~~~text
demoEuDebug
demoEuRelease
demoUsDebug
demoUsRelease
fullEuDebug
fullEuRelease
fullUsDebug
fullUsRelease
~~~

**Không có** variant kết hợp cả `demo` và `full` vì chúng thuộc cùng dimension. Thứ tự `tier` rồi `region` chi phối thứ tự tên và source-set priority giữa dimensions.

### 10.2. Source sets của nhiều dimensions

Có thể dùng:
- `src/main` cho common.
- `src/demo` và `src/eu` cho individual flavors.
- `src/demoEu` cho flavor combination.
- `src/demoEuDebug` cho full variant.
- `src/debug` cho build type.

Khi có hai dimensions, `src/demoDebug` **không đại diện đầy đủ** cho một variant, vì còn thiếu region dimension. Tổ chức source sets theo đúng model thay vì copy tên từ dự án một dimension.

### 10.3. Variant explosion

Nếu số flavors tăng theo tích, IDE sync và CI matrix có thể chậm. Trước khi tạo thêm dimension:
1. Có thật sự cần code/resources/APK khác nhau không?
2. Có thể dùng runtime/server configuration thay vì compile-time variant không?
3. Có unsupported combinations cần loại bằng `beforeVariants` không?
4. CI có coverage cho các variants phát hành?
5. Đã kiểm tra APK IDs, resource conflicts, library matching và signing của mọi tổ hợp chưa?

Đừng tạo product flavors chỉ vì muốn đặt một biến môi trường mà không có sự khác biệt build thực sự.

## 11. Source sets, overlay và merge precedence

Android source sets thường có:

| Source set | Phạm vi |
| --- | --- |
| `src/main` | Mọi variants |
| `src/debug` | Build type debug |
| `src/release` | Build type release |
| `src/demo` | Flavor demo |
| `src/full` | Flavor full |
| `src/demoDebug` | Variant demoDebug với một dimension |
| `src/test` | Local JVM unit tests |
| `src/androidTest` | Device/emulator instrumentation tests |

### 11.1. Ưu tiên của `demoDebug`

~~~text
Cao nhất     src/demoDebug/
             src/debug/
             src/demo/
             src/main/
Thấp nhất    Android library dependencies
~~~

Android docs xác nhận: **variant > build type > product flavor > main source set > library**. Với nhiều dimensions, combined-flavor source sets có ưu tiên cao hơn individual flavors; dimension được khai sớm có mức ưu tiên cao hơn.

### 11.2. Resource overlay

Trong lab:
- `app_name` trong `main` là `Variant Lab`.
- `app_name` trong `demo` là `Demo Variant Lab`.
- `app_name` trong `demoDebug` là `Demo Debug Lab`.

`demoDebug` dùng giá trị `Demo Debug Lab`; `demoRelease` dùng `Demo Variant Lab`; `fullDebug` dùng `Full Variant Lab`. Đây là ưu tiên resource có chủ đích.

Nếu hai resource directories **cùng priority trong một source set** định nghĩa trùng một resource, AGP có thể báo conflict thay vì tự chọn một directory. Không nhầm với override giữa các source sets có thứ tự rõ.

### 11.3. Java class không overlay theo resource rule

Hai file cùng fully-qualified Java class ở `src/main/java` và `src/debug/java` đều tham gia debug variant, nên có thể gây **duplicate class**. Không dùng cùng tên class trong main và debug như thể debug tự override. Nếu cần implementations khác nhau, để interface/common API ở main và implementations ở những source sets **loại trừ nhau** như debug/release.

### 11.4. Manifest merging

App main/flavor/build type/variant manifests và library manifests được merge; priority tương tự source sets. Lỗi `Manifest merger failed` có thể do conflicting attributes, thiếu `android:exported` hoặc unresolved placeholders. Xem merged manifest và manifest merger reports **đúng variant**, không tự loại bỏ security-sensitive attributes để build qua.

### 11.5. Assets, resource qualifiers và runtime

`res/values-vi`, `drawable-hdpi`, `layout-land` thuộc Android **runtime resource qualifiers**, không phải flavors. Flavor `eu` có thể chứa resources đủ các ngôn ngữ/màn hình; Android runtime vẫn chọn qualifier phù hợp thiết bị sau khi APK build xong.

## 12. Variant-aware dependencies giữa app và library

Gradle/AGP không tùy tiện chọn một file library. Nó so **consumer attributes** với **producer variants** theo build type, flavors và những attributes khác.

Trong lab:
- `:app:demoDebug` chọn `:core:debug`.
- `:app:fullDebug` chọn `:core:debug`.
- `:app:demoRelease` chọn `:core:release`.
- `:app:fullRelease` chọn `:core:release`.

Library không có flavor dimension `tier` nên app's tier không cần matched dimension bên library. Nếu library cùng dimension nhưng có flavor names khác, AGP cần matching strategy tương ứng.

### 12.1. `matchingFallbacks`: app cần một build type không có ở library

Ví dụ app `staging`, library `debug`/`release`:

~~~groovy
android {
    buildTypes {
        staging {
            initWith debug
            matchingFallbacks = ['debug', 'release']
        }
    }
}
~~~

AGP thử fallbacks theo thứ tự **khi producer thiếu exact staging**. Nếu library có staging thật và tương thích, exact match được ưu tiên. Fallback giải quyết mismatch có chủ đích, không sửa lỗi tùy ý trong dependency graph.

### 12.2. `matchingFallbacks` cho product flavor cùng dimension

Giả sử app có `demo`/`full` ở dimension `tier`, còn một library có `trial`/`full` trong dimension `tier`. App demo không thể tìm flavor demo của library:

~~~groovy
android {
    flavorDimensions 'tier'
    productFlavors {
        demo {
            dimension 'tier'
            matchingFallbacks = ['trial', 'full']
        }
        full {
            dimension 'tier'
        }
    }
}
~~~

**Chỉ là snippet thay thế** cho project có thư viện `trial`/`full`, không cần dán vào lab nơi `:core` không có product flavors. Flavor fallback phải đặt trên **product flavor cần match**, không đặt trong `defaultConfig`.

### 12.3. `missingDimensionStrategy`: library có dimension app không có

Ví dụ library thêm dimension `minApi` gồm `minApi21`/`minApi24` nhưng app không khai dimension đó:

~~~groovy
android {
    defaultConfig {
        missingDimensionStrategy 'minApi', 'minApi24'
    }
}
~~~

App yêu cầu AGP chọn một library flavor khi dimension còn thiếu. Có thể override strategy theo từng app flavor. Đừng dùng `matchingFallbacks` để chữa **missing dimension**, vì hai cơ chế có điều kiện khác nhau.

### 12.4. Dependency configurations theo scope

| Tên | Ý nghĩa |
| --- | --- |
| `implementation` | Dependency dùng chung các variants |
| `debugImplementation` | Dependency cho debug build types |
| `releaseImplementation` | Dependency cho release |
| `demoImplementation` | Dependency cho demo flavors |
| `demoDebugImplementation` | Dependency cho demoDebug variant |
| `testImplementation` | Local JVM unit tests |
| `androidTestImplementation` | Instrumentation tests |

Availability/names phụ thuộc module/AGP version. Với một thư viện gỡ lỗi chỉ cần khi debug, nên khai debug scope thay vì generic `implementation` để tránh kéo tooling vào release.

### 12.5. Xem resolved classpath

~~~bash
./gradlew :app:dependencies --configuration demoDebugRuntimeClasspath
./gradlew :app:dependencies --configuration fullReleaseRuntimeClasspath
./gradlew :app:tasks --all
~~~

Khi báo `No matching variant`, đọc **consumer attributes và producer variants** trong error message, không đoán. Tránh lệnh `dependencyInsight` với một dependency **không có trong configuration**: trong lab, JUnit chỉ ở `:core` testImplementation, không phải app demoDebug runtime.

## 13. Android Components Variant API hiện đại

Nếu cần can thiệp variant creation beyond DSL, AGP có `androidComponents`:

~~~text
android {} DSL
     |
     +--> androidComponents.finalizeDsl()
     |
     +--> androidComponents.beforeVariants()
     |         chỉnh builder / enable hoặc disable variant
     |
     +--> AGP tạo Variant objects
     |
     +--> androidComponents.onVariants()
     |         properties, providers, artifacts
     |
     +--> tasks và artifacts pipeline
~~~

API mới ưu tiên lazy providers/artifact wiring, giảm phụ thuộc vào internal task names. Trong AGP hiện đại, legacy `applicationVariants.all` và `variantFilter` đã bị deprecate/xóa theo migration roadmap; không phát triển plugin mới dựa trên những legacy hooks.

### 13.1. `beforeVariants`: bỏ demoRelease

**Bổ sung riêng** ở cuối `app/build.gradle`:

~~~groovy
androidComponents {
    beforeVariants(selector().withName('demoRelease')) { builder ->
        builder.enable = false
    }
}
~~~

Khi bật snippet, AGP không tạo `demoRelease` như variant sản phẩm thông thường. Từ bốn variants còn **demoDebug, fullDebug, fullRelease**. Task `:app:assembleDemoRelease` có thể không còn. **Không thêm snippet này trước khi chạy baseline bốn variants** nếu bạn muốn đối chiếu output lab ban đầu.

### 13.2. `onVariants`: quan sát/cấu hình lazy

~~~groovy
androidComponents {
    onVariants(selector().withBuildType('debug')) { variant ->
        logger.lifecycle(
            'Configured Android variant: ' + variant.name
        )
    }
}
~~~

Callback có thể ghi log trong **configuration**, không phải stdout ứng dụng và không chứng minh APK đã build. Với production custom plugin, dùng AGP public Sources/Artifacts APIs và Gradle Providers thay vì `afterEvaluate` hoặc truy cập internal task instances dựa trên tên.

### 13.3. `finalizeDsl`

Dùng khi convention plugin cần chỉnh một phần DSL trước khi AGP khóa nó để tạo variants. Nếu chỉ khai build types/flavors tĩnh, `android {}` là đủ. Không cần biến một bài cấu hình đơn giản thành plugin extension phức tạp.

### 13.4. Cảnh báo compatibility AGP 9.x

Modern AGP liên tục đổi APIs. Đặc biệt khi nâng AGP 8.x lên 9.x, xem [AGP DSL/API migration roadmap](https://developer.android.com/build/releases/gradle-plugin-roadmap): nhiều legacy BaseVariant/task access APIs không còn được hỗ trợ. Không copy plugin code đời cũ vào AGP mới mà không chạy compatibility tests.

## 14. BuildConfig và cấu hình theo variant

Lab dùng generated `BuildConfig.FLAVOR` và `BuildConfig.BUILD_TYPE`. Khi muốn thêm public edition label:

~~~groovy
android {
    buildFeatures {
        buildConfig true
    }

    productFlavors {
        demo {
            dimension 'tier'
            buildConfigField 'String', 'EDITION_NAME', '"demo"'
        }
        full {
            dimension 'tier'
            buildConfigField 'String', 'EDITION_NAME', '"full"'
        }
    }
}
~~~

Đây là **snippet nâng cao**, phải hợp nhất với `flavorDimensions 'tier'`/`productFlavors` đã có, không dùng như một file build.gradle độc lập. Dấu ngoặc kép bên trong `'"demo"'` quan trọng để generated Java dùng literal `"demo"`.

**Không lưu secrets** trong BuildConfig, resource XML, manifest placeholders hoặc compiled Java constants: người có APK có thể extract chúng. Flavor khác nhau không tự tạo cơ chế chống truy cập trả phí; cần server-side authorization.

## 15. Test variants: local JVM và Android instrumentation

### 15.1. Local JVM unit tests

`src/test/java` chứa tests chạy trên host JVM. Các task có dạng:

~~~bash
./gradlew :core:testDebugUnitTest
./gradlew :app:testDemoDebugUnitTest
~~~

Trong lab, hai tests của `:core` thật sự được khai, còn `:app` không có test source. Vì vậy app unit-test task có thể báo `NO-SOURCE` hoặc không chạy test nào, và một task “thành công” như vậy **không chứng minh** MainActivity đã được test.

### 15.2. Instrumentation tests

`src/androidTest/java` chứa tests cần Android device/emulator và instrumentation runner (thường AndroidX Test). Với debug app variant, task có dạng:

~~~bash
./gradlew :app:connectedDemoDebugAndroidTest
~~~

**Lab cơ bản chưa khai AndroidX Test/runner hoặc androidTest source**, nên lệnh này là hướng dẫn mở rộng, không phải một test runnable đã có sẵn. Cần thêm test runner/dependencies và connected device thật. AGP thường ưu tiên instrumentation test build type debug mặc định; không suy ra mọi release/staging đều tự có connected tests.

### 15.3. Test source sets cụ thể

Có thể có `src/testDemoDebug/java` hoặc `src/androidTestDemoDebug/java` theo variant/source-set support. Kiểm tra Gradle/AGP task list/sourceSet model ở version đang dùng. Không đặt một content root dùng đồng thời vào nhiều source sets rồi kỳ vọng Android Studio/Gradle cho phép tùy ý.

## 16. APK, AAB, AAR và signing

| Artifact | Ví dụ task | Mục đích |
| --- | --- | --- |
| APK | `:app:assembleDemoDebug` | Android installable package nếu ký/hợp lệ |
| APK release | `:app:assembleFullRelease` | Release package, signing cần riêng |
| AAB | `:app:bundleFullRelease` | Android App Bundle để phân phối |
| AAR | `:core:assembleRelease` | Android library artifact |
| Reports | `:core:testDebugUnitTest` | Unit test results |

**AAB không được cài trực tiếp bằng `adb install` giống APK.** Android App Bundle được xử lý qua Play/bundletool để phân phối APKs. Với release production, khóa ký/password/CI identities phải được bảo vệ, không commit vào build script hoặc đưa vào BuildConfig.

### 16.1. Debug key vs release key

Debug builds thường được AGP ký bằng debug keystore thuận tiện cho dev. Release build của lab không có `signingConfigs`, nên `assembleFullRelease` PASS **không** có nghĩa artifact đã sẵn sàng upload Play hoặc install trên device. Đừng dùng debug key để phát hành bản production.

### 16.2. CI matrix

- Pull Request: build/debug unit tests và lint cho những variants đại diện.
- Nightly: đầy đủ các important flavors/build types, nhất là combinations có source/resource riêng.
- Release: bundle/sign trusted fullRelease, kiểm tra upload metadata/target API requirements.
- Device tests: chỉ chạy khi đã provision emulator/device và instrumentation runner.

Build chỉ `demoDebug` PASS không đảm bảo `fullRelease` PASS vì source sets, manifest, R8/dependencies/signing có thể khác. Cân bằng coverage và chi phí, không build mọi biến thể lớn theo phản xạ.

## 17. Android Studio và Gradle CLI

Trong Android Studio:
1. Import project bằng Gradle Wrapper/AGP đã pin.
2. Sync để IDE đọc model modules/variants.
3. Mở **Build Variants** tool window.
4. Chọn `demoDebug` hoặc `fullDebug` cho `:app`.
5. Run/Debug trên device/emulator khi sẵn sàng.
6. So source code/resources được IDE sử dụng theo active variant.

**Sync khác assemble:** Sync dựng Gradle/Android IDE model, không nhất thiết tạo APK. Terminal `./gradlew :app:assembleDemoDebug` là một build rõ mục tiêu; IDE có thể dùng Gradle JVM riêng khác terminal `JAVA_HOME` nên cần kiểm tra khi lỗi xuất hiện ở một bên.

## 18. Troubleshooting theo từng lớp

### 18.1. Không tìm thấy `com.android.application` plugin

**Triệu chứng:** `Plugin [id: 'com.android.application'] was not found`.

**Kiểm tra:** `pluginManagement.repositories` có `google()` chưa, AGP version đúng không, Gradle offline/network/proxy có vấn đề không. `repositories { mavenCentral() }` trong app module không thay thế Google plugin repository.

### 18.2. AGP yêu cầu JDK17

Kiểm tra:

~~~bash
java -version
./gradlew --version
~~~

AGP8.9 cần JDK17 chạy Gradle. Nếu IDE dùng JDK11 còn terminal JDK17, build có thể chỉ lỗi trong IDE. Java compiler `sourceCompatibility` không sửa daemon JVM. Xem IDE Gradle JVM, `JAVA_HOME` và `org.gradle.java.home` nếu có.

### 18.3. AGP/Gradle version mismatch

AGP8.9.2 + Wrapper cũ hơn Gradle8.11.1 có thể fail khi áp plugin. Đối chiếu chính xác [AGP compatibility table](https://developer.android.com/build/releases/about-agp). Nâng AGP/Gradle đồng bộ qua PR/tests, không chỉ đổi một number trong root build.gradle.

### 18.4. Không thấy Android SDK platform

**Triệu chứng:** `Failed to find Platform SDK with path: platforms;android-35` hoặc thông báo thiếu SDK35.

**Khắc phục:** SDK Manager cài `platforms;android-35` và Build Tools phù hợp; kiểm tra SDK location (`ANDROID_HOME`/`local.properties`). `compileSdk35` không phải JDK35 hoặc Gradle35.

### 18.5. `Namespace not specified`

Android module thiếu `namespace` khi dùng AGP8+. Khai namespace riêng cho app/library; không thay bằng `applicationId`. Tránh manifest `package` kiểu cũ như workaround.

### 18.6. Flavor thiếu dimension

**Triệu chứng:** `All flavors must now belong to a named flavor dimension`.

**Khắc phục:** Khai `flavorDimensions 'tier'` và `dimension 'tier'` trong mỗi flavor cần thiết. Tên `tier` khác `tiers`; Gradle không tự sửa typo.

### 18.7. `No matching variant`/`Ambiguous variant selection`

**Nguyên nhân:** Consumer app variant attributes không match producer library variants; staging vs debug/release hoặc flavors cùng dimension khác tên, hoặc library có dimension app thiếu.

**Khắc phục:** Đọc log liệt kê attributes và producer variants. Dùng `matchingFallbacks` đúng build type/flavor hoặc `missingDimensionStrategy` đúng missing dimension. Không loại dependency chỉ để build tạm xanh.

### 18.8. `Duplicate class`

Java/Kotlin classes có cùng fully-qualified name trong các source sets cùng tham gia variant hoặc dependencies chồng lấn. Không áp resource overlay rules cho Java source; sửa code layout hoặc dependency graph.

### 18.9. Resource merge conflict

Hai resource folders cùng priority chứa resource trùng, hoặc sourceSets bị map chồng lấn. Xem merged resources và conflict report. `app_name` của demoDebug override demo/main là hợp lệ vì priorities khác.

### 18.10. `Manifest merger failed`

Kiểm tra `android:exported`, component names, permissions, placeholders và merge source priority. Đừng dùng `tools:replace` diện rộng chỉ để qua lỗi; xác định source manifest nào định nghĩa thuộc tính gây conflict.

### 18.11. `BuildConfig cannot be resolved`

`buildFeatures.buildConfig` có thể disabled hoặc class được generate trong namespace khác. Bật `buildConfig true` trong đúng module, kiểm tra Java import namespace. Không import `BuildConfig` của library khi muốn app variant fields.

### 18.12. Task `assembleDemoDebug` không tồn tại

Có thể sai module/name, chưa khai flavor/dimension, variant bị disable bằng `beforeVariants` hoặc build configuration fail. Chạy:

~~~bash
./gradlew :app:tasks --all
~~~

Dựa vào model thực thay vì đoán từ tên task project khác.

### 18.13. `installDemoDebug` lỗi dù assemble PASS

Có thể không có device/emulator, ADB unauthorized/offline, device API dưới minSdk hoặc thiếu SDK components. Kiểm tra `adb devices` và target device; app build không cần device.

### 18.14. Release artifact không ký

`assembleFullRelease` có thể sinh unsigned output. Release job cần keystore/Play signing workflow, tránh lưu signing password/keys trong source; không hard-code tên APK theo một AGP version đoán trước.

### 18.15. Nhiều variants làm sync/build chậm

Số variants tăng theo tích; AGP phải configure nhiều components/tasks. Giảm dimensions không cần, disable unsupported variants bằng `beforeVariants`, dùng lazy providers và CI test matrix phù hợp. Không dùng legacy eager `applicationVariants.all` trong plugin mới.

## 19. Bài tập kèm lời giải

### Bài 1 — Module hay variant?

**Hỏi:** `:app` có variant `demoDebug`. `demoDebug` có phải một Gradle module riêng?

**Đáp án:** Không. `:app` là Gradle project/module; `demoDebug` là variant của nó.

### Bài 2 — Công thức

**Hỏi:** Hai build types, ba flavors trong một dimension tạo bao nhiêu variants?

**Đáp án:** \(2 \times 3 = 6\).

### Bài 3 — Hai dimensions

**Hỏi:** debug/release × demo/full × eu/us tạo bao nhiêu variants?

**Đáp án:** \(2 \times 2 \times 2 = 8\), ví dụ `demoEuDebug`.

### Bài 4 — Chọn flavor

**Hỏi:** Một variant được chứa đồng thời `demo` và `full` cùng dimension tier không?

**Đáp án:** Không, mỗi dimension chọn đúng một flavor.

### Bài 5 — `defaultConfig`

**Hỏi:** `minSdk24` trong defaultConfig và flavors không override. Biến thể nào dùng minSdk24?

**Đáp án:** Tất cả.

### Bài 6 — Application ID

**Hỏi:** demo suffix `.demo`, debug suffix `.debug`. ID của demoDebug?

**Đáp án:** `dev.example.variantlab.demo.debug`.

### Bài 7 — Namespace

**Hỏi:** Thêm `applicationIdSuffix` có làm Java package của MainActivity đổi?

**Đáp án:** Không. `namespace`/Java package là lớp khác installed application ID.

### Bài 8 — Resource precedence

**Hỏi:** `app_name` có ở main, demo, demoDebug. demoDebug lấy giá trị nào?

**Đáp án:** `Demo Debug Lab` từ `src/demoDebug`.

### Bài 9 — Java source conflict

**Hỏi:** `src/debug` và `src/main` cùng định nghĩa một fully-qualified Java class. Debug variant chọn class ưu tiên cao không?

**Đáp án:** Không, có nguy cơ duplicate class error. Java source không overlay như resource.

### Bài 10 — Library variant

**Hỏi:** App `fullRelease` phụ thuộc library không có flavors. Chọn library variant nào?

**Đáp án:** `release`.

### Bài 11 — Staging missing

**Hỏi:** App có staging, library chỉ debug/release. Dùng cơ chế nào?

**Đáp án:** `matchingFallbacks = ['debug']` cho app staging build type.

### Bài 12 — Flavor mismatch

**Hỏi:** App demo, library trial/full cùng tier dimension. Dùng gì?

**Đáp án:** `matchingFallbacks` cho app flavor demo, với danh sách library flavors có thật như `['trial']`.

### Bài 13 — Missing dimension

**Hỏi:** Library có dimension minApi nhưng app không có. Cấu hình nào?

**Đáp án:** `missingDimensionStrategy 'minApi', 'minApi24'` với một flavor thực của library.

### Bài 14 — Build APK

**Hỏi:** Lệnh build demoDebug?

**Đáp án:** `./gradlew :app:assembleDemoDebug`.

### Bài 15 — Android App Bundle

**Hỏi:** `adb install app-full-release.aab` có cài trực tiếp được không?

**Đáp án:** Không; phải tạo/distribute APKs qua Play/bundletool phù hợp.

### Bài 16 — JVM vs Android API

**Hỏi:** `compileSdk35` có nghĩa Gradle chạy trên JDK35?

**Đáp án:** Không. Lab dùng JDK17 chạy AGP và Android SDK35 để compile.

### Bài 17 — Variant API

**Hỏi:** Muốn disable demoRelease trước khi AGP tạo variant, dùng gì?

**Đáp án:** `androidComponents.beforeVariants(selector().withName('demoRelease'))` và `builder.enable=false`.

### Bài 18 — Tests

**Hỏi:** `testDemoDebugUnitTest` và `connectedDemoDebugAndroidTest` giống nhau?

**Đáp án:** Không, một chạy JVM local, một chạy Android instrumentation trên device.

### Bài 19 — BuildConfig

**Hỏi:** Vì sao lab bật `buildFeatures { buildConfig true }`?

**Đáp án:** Code MainActivity đọc `BuildConfig.FLAVOR`/`BUILD_TYPE`; không nên giả định buildConfig auto-generated trong mọi AGP8.x configuration.

### Bài 20 — Java CLI stdout

**Hỏi:** `java -cp out VariantMatrix` in gì?

**Đáp án:** Bốn dòng lần lượt `demoDebug`, `demoRelease`, `fullDebug`, `fullRelease`, có newline sau mỗi dòng.

### Bài 21 — Thực hành

1. Tạo project với file tree và toàn bộ code từ phần 6.
2. Sinh Wrapper8.11.1 tin cậy và cài Android SDK35/JDK17.
3. Chạy `./gradlew --version` và kiểm tra JDK/Gradle.
4. Sync Android Studio, quan sát hai Gradle modules.
5. Xác nhận bốn app variants trong Build Variants window.
6. Chạy `:app:assembleDemoDebug` và `:app:assembleFullRelease`.
7. Chạy `:core:testDebugUnitTest`; xác nhận hai JUnit tests được chạy.
8. Biên dịch/chạy `tools/VariantMatrix.java` bằng Java17, so stdout chính xác.
9. Install demoDebug khi có device; xem UI ba dòng.
10. Giải thích resource overlay của `app_name`/`channel_name`.
11. Thêm staging + matchingFallbacks, tính lại sáu variants.
12. Bật `beforeVariants` loại demoRelease; kiểm tra task thiếu, sau đó khôi phục.
13. Giải thích `missingDimensionStrategy` qua giả định library có minApi dimension.
14. Lập kế hoạch CI test debug/release/flavor coverage và bảo vệ release signing.

**Tiêu chí đạt:** dựng được app Android Java17 hai modules, phân biệt bốn khái niệm, hiểu source-set priority/variant dependency và chạy được Java CLI với output như dự kiến.

## 20. Checklist triển khai thực tế

- [ ] `settings.gradle` khai đúng modules và plugin resolution có `google()`.
- [ ] Root pin AGP version; Gradle Wrapper tương thích AGP.
- [ ] JDK chạy Gradle, Android SDK và Java compiler target được kiểm tra riêng.
- [ ] App dùng `com.android.application`; library dùng `com.android.library`.
- [ ] Mỗi Android module có `namespace`.
- [ ] App có `applicationId` và versionCode/versionName phù hợp.
- [ ] `compileSdk`, `minSdk`, `targetSdk` được hiểu đúng.
- [ ] Mỗi flavor thuộc dimension hợp lệ.
- [ ] Số variant combinations được tính trước khi thêm dimensions.
- [ ] Source sets đúng tên, Java classes không trùng trong cùng variant.
- [ ] Merged resources/manifests được test cho variants quan trọng.
- [ ] BuildConfig generation bật khi code cần.
- [ ] Local library dependencies chọn đúng build-type/flavor variants.
- [ ] `matchingFallbacks`/`missingDimensionStrategy` được dùng đúng tình huống.
- [ ] Variant-specific dependencies đúng scope, debug tooling không vào release.
- [ ] Custom build logic ưu tiên `androidComponents` public API.
- [ ] APK/AAB/AAR outputs được lấy từ build metadata thay vì hard-code tên đoán.
- [ ] Unit tests và instrumentation tests có coverage khác nhau.
- [ ] Release signing keys không được commit vào repository.
- [ ] Không ship secrets qua BuildConfig/resources/manifest.
- [ ] CI build các variants đại diện và kiểm tra release artifact.
- [ ] Android Studio và CI dùng chung Wrapper/plugin versions đã pin.
- [ ] Mỗi lần nâng AGP major đều kiểm tra Gradle/JDK/SDK compatibility và migration notes.

## 21. Tài liệu tham khảo chính thức

- [Android Developers — Configure build variants](https://developer.android.com/build/build-variants): module build types/flavors, variant names, source sets, matchingFallbacks, missingDimensionStrategy.
- [Android Developers — Configure your build](https://developer.android.com/build): Android Gradle DSL, root/module build model.
- [Android Developers — AGP 8.9 release notes](https://developer.android.com/build/releases/agp-8-9-0-release-notes): Gradle8.11.1, JDK17, API35 và patch AGP8.9.2.
- [Android Developers — AGP/Gradle compatibility table](https://developer.android.com/build/releases/about-agp): kiểm tra versions khi nâng plugin.
- [Android Developers — Java versions in Android builds](https://developer.android.com/build/jdks): JDK runtime, Android SDK APIs và desugaring.
- [Android Developers — Write Gradle plugins / Android Components API](https://developer.android.com/build/extend-agp): `finalizeDsl`, `beforeVariants`, `onVariants`.
- [Android Developers — AGP DSL/API migration roadmap](https://developer.android.com/build/releases/gradle-plugin-roadmap): tránh legacy applicationVariants/variantFilter.
- [Android Developers — Add app resources](https://developer.android.com/studio/write/add-resources): merge priority và resource conflicts.
- [Android Developers — Manifest merger](https://developer.android.com/build/manage-manifests): merge manifest và tools directives.
- [Android Developers — Application module configuration](https://developer.android.com/build/configure-app-module): applicationId và namespace.
- [Android Developers — Testing](https://developer.android.com/studio/test): JVM unit và instrumentation tests.
- [Android Developers — App signing](https://developer.android.com/studio/publish/app-signing): debug/release signing và bảo vệ keystores.
- [Android Developers — Android App Bundle](https://developer.android.com/guide/app-bundle): APK vs AAB.
- [Gradle — Creating Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): AGP configurations/attributes và variant-aware dependencies.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `settings.gradle` và project dependencies.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): reproducible Gradle distribution.
