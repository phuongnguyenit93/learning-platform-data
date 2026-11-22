# Kotlin Multiplatform: target, source set và vai trò của plugin trong Gradle

**Kotlin Multiplatform (KMP)** cho phép chia sẻ mã Kotlin giữa nhiều nền tảng, chẳng hạn JVM/backend, Android, iOS, JavaScript/Node.js, WebAssembly, macOS và Linux. Tuy nhiên, **Gradle** không tự biết phải biên dịch một thư mục Kotlin thành JVM bytecode, JavaScript hay native library. Công việc đó được thực hiện bởi **Kotlin Multiplatform Gradle plugin** (`org.jetbrains.kotlin.multiplatform`): plugin khai báo mô hình target–compilation–source set, đăng ký tasks, quản lý dependencies, chọn toolchains và công bố các biến thể artifact cho consumer.

Bài thuộc phần **Hệ sinh thái Gradle** của *Build Tool Gradle* và trả lời câu hỏi **“Kotlin Multiplatform: target, source set và vai trò của plugin”**. Trọng tâm là thiết kế build, không phải học lại cú pháp Kotlin: cách áp dụng plugin, vì sao `commonMain` không phải JVM module, cách `jvm()` và `js { nodejs() }` tạo tasks, quan hệ `dependsOn` giữa source sets, default hierarchy template, `expect/actual`, khai báo dependencies và test, Gradle Module Metadata/variant-aware resolution, Java 17 interoperability, Android/iOS constraints, kiểm thử và chẩn đoán.

Phần thực hành là **một project đầy đủ với hai Gradle modules**: `:shared` dùng Kotlin Multiplatform để tạo JVM và JS/Node variants, `:app` là Java 17 application dùng JVM variant của `:shared` qua `implementation(project(":shared"))`. Có các file Kotlin, Java, Gradle Kotlin DSL, tests chạy được và **stdout Java chính xác**. Mảnh cấu hình cho Android/iOS, publishing hoặc hierarchy nâng cao được chỉ rõ là minh họa, không ghép vô điều kiện vào project runnable.

**Phiên bản và tương thích tại ngày 09/11/2026:** Kotlin stable và KMP plugin mới nhất được tài liệu Kotlin công bố là **2.4.21** (08/10/2026). *Kotlin Multiplatform Compatibility Guide* nêu dải Gradle hỗ trợ của KMP 2.4.20–2.4.21 tới **Gradle 9.7.0**. Vì vậy ví dụ dùng **KMP 2.4.21 + Gradle Wrapper 9.7.0 + JDK 17**. Không tự suy rằng Gradle 9.8/9.9, dù mới hơn, đã nằm trong compatibility range chính thức của plugin 2.4.21; phải kiểm tra release notes/compatibility guide khi đổi một thành phần. Phần Android có thêm AGP và SDK compatibility, phần Apple còn có Xcode/host constraints.

## 1. KMP giải quyết vấn đề gì?

Giả sử bạn có:
- Backend chạy JVM/Java.
- Web client chạy trong browser hoặc Node.js.
- Mobile app chạy Android và iOS.
- Nhiều ứng dụng cần dùng **cùng quy tắc validation, mô hình dữ liệu, thuật toán định giá, logic nghiệp vụ**.

Nếu mỗi nền tảng viết lại logic, bạn có rủi ro code duplication và behavior lệch. KMP cho phép đặt những phần không phụ thuộc platform vào `commonMain`, rồi biên dịch chúng cùng code platform-specific của từng **target**:

~~~text
                    src/commonMain/kotlin
                   Validation + shared business rules
                          /       \
                         /         \
             src/jvmMain/kotlin   src/jsMain/kotlin
                 JVM APIs          JavaScript APIs
                     |                 |
                    jvm()             js { nodejs() }
                     |                 |
               JVM class/JAR     JavaScript modules
                     |                 |
               Java application   Node.js consumer
~~~

**Không có một “universal JAR” chạy được mọi platform.** Kotlin/JVM tạo JVM bytecode; Kotlin/JS tạo JavaScript; Kotlin/Native tạo binaries hoặc `.klib` theo native target; Kotlin/Wasm dùng pipeline riêng. KMP giúp **chia sẻ source/API** và xuất các artifacts tương ứng với từng target.

Không đồng nhất KMP với **Compose Multiplatform**. Compose cung cấp framework chia sẻ UI, có thể được dùng trong KMP nhưng không phải điều kiện để dùng KMP. Một thư viện validation/DTO thuần logic có thể không có Compose.

## 2. Ba tầng cốt lõi: plugin → target → source set

| Thành phần | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Gradle project/module** | Đơn vị cấu hình build với `build.gradle.kts` | `:shared`, `:app` |
| **KMP plugin** | Mở rộng Gradle model cho Multiplatform | `kotlin("multiplatform") version "2.4.21"` |
| **Target** | Một platform/compilation backend mà plugin biết build cho | `jvm()`, `js()`, `iosArm64()` |
| **Compilation** | Cấu hình biên dịch bên trong target | `main`, `test` |
| **Kotlin source set** | Nhóm source/resources/dependencies chia sẻ giữa các compilations/targets | `commonMain`, `jvmMain`, `jsTest`, `iosMain` |
| **Execution environment** | Nơi chạy binary/test của target | Node.js, browser, JVM, simulator/device |
| **Gradle task** | Công việc cụ thể do plugin đăng ký theo target | `compileKotlinJvm`, `jvmTest`, `jsNodeTest` |
| **Variant/publication** | Artifact và Gradle attributes để consumer chọn đúng platform | JVM JAR, JS variant, KMP root metadata |

Ba thuật ngữ **target**, **compilation** và **source set** khác nhau:

- **Target** trả lời “biên dịch **cho platform nào**?”
- **Compilation** trả lời “là **main/test/custom** compilation của target đó?”
- **Source set** trả lời “**những source files và dependencies nào** cùng được biên dịch và tái sử dụng bởi compilation(s)?”
  
Ví dụ: `jvm()` tạo JVM target, mặc định có compilations `main` và `test`. KMP quản lý `jvmMain` và `jvmTest` cùng `commonMain`/`commonTest` trong dependency graph của sources. `js { nodejs() }` là target JavaScript cộng lựa chọn môi trường chạy tests; không tạo ra Java class files.

## 3. Vai trò thực sự của Kotlin Multiplatform Gradle plugin

Nếu chỉ đặt file `.kt` vào một Java Gradle project, Gradle core Java plugin **không tự biến** chúng thành KMP. KMP plugin thực hiện các việc sau:

1. **Tạo Gradle extension `kotlin { }`** cho targets, source sets, compiler options và dependencies.
2. **Đăng ký Kotlin compilation tasks** theo target/backend, output locations và task dependencies.
3. **Quản lý compiler/stdlib/tooling** phù hợp Kotlin version và target, trong giới hạn Gradle/plugin compatibility.
4. **Tạo source set hierarchy**, gồm common/shared/intermediate/platform source sets theo targets.
5. **Giới hạn APIs**: common code chỉ tham chiếu APIs khả dụng ở toàn bộ những targets mà source set áp dụng.
6. **Liên kết source set dependencies** và cho Gradle chọn platform-specific variants của multiplatform libraries.
7. **Tạo tasks kiểm thử** cho targets, ví dụ JUnit ở JVM, Mocha ở Node.js và runner tương ứng trên native.
8. **Quản lý JVM/JS/Native toolchains và môi trường chạy** theo backend và host capabilities.
9. **Hỗ trợ Gradle metadata/publications**: JVM artifact, JS artifact, native artifact và root Kotlin Multiplatform publication khi dùng `maven-publish`.
10. **Tích hợp IDE import/model**, giúp Kotlin Multiplatform aware IDE thấy source sets, targets và dependencies.

Plugin **không tự tải Android SDK/Xcode hợp lệ hoặc làm iOS simulator xuất hiện trên Windows**. Toolchain/backend và build host vẫn có điều kiện riêng. Plugin cũng **không bảo đảm mọi third-party JVM library có JS/native variants**.

## 4. Plugin ID, version và cách áp dụng

Trong file `shared/build.gradle.kts`:

~~~kotlin
plugins {
    kotlin("multiplatform") version "2.4.21"
}
~~~

Cú pháp tương đương:

~~~kotlin
plugins {
    id("org.jetbrains.kotlin.multiplatform") version "2.4.21"
}
~~~

**Chỉ chọn một trong hai đoạn**, không áp dụng plugin hai lần. Tên plugin đầy đủ là `org.jetbrains.kotlin.multiplatform`; `kotlin("multiplatform")` là Kotlin DSL syntax/alias cho plugin ID tương ứng, **không phải một target hoặc source set**. KMP plugin version đi cùng version Kotlin compiler line (ở đây 2.4.21), không phải version Gradle.

Trong một multi-project lớn, có thể khai báo plugin version một lần ở root:

~~~kotlin
// Root build.gradle.kts (mảnh thay thế chiến lược quản lý version):
plugins {
    kotlin("multiplatform") version "2.4.21" apply false
}
~~~

Rồi dùng:

~~~kotlin
// shared/build.gradle.kts khi root đã khai báo plugin:
plugins {
    kotlin("multiplatform")
}
~~~

Đây là **mảnh cấu hình version management**, không paste thêm vào runnable demo bên dưới vì demo đã pin version ở `:shared`. `apply false` chỉ đưa plugin/version vào plugin resolution scope, **không tạo targets/source sets trên root**.

Có thể quản lý plugin version bằng version catalog (`gradle/libs.versions.toml`), hoặc convention plugin, nhưng cần hiểu repository resolution/Gradle plugin marker dependencies. **Maven Central cho code dependencies không tự đảm bảo plugin marker được resolve**; Gradle Plugin Portal hoặc `pluginManagement.repositories` phải phù hợp tổ chức.

## 5. Target là platform, không phải một source folder

Một KMP library:

~~~kotlin
kotlin {
    jvm()

    js {
        nodejs()
    }
}
~~~

Nghĩa là library có **hai target backends**: Kotlin/JVM và Kotlin/JS, với JS test/runtime environment là Node.js. Plugin có thể tạo các tasks tương ứng. Một target có thể có compilations, và các compilations dùng nhiều source sets. **Không có nghĩa duy nhất hai source directories**: còn `commonMain` và `commonTest`.

### Những target phổ biến

| KMP target DSL | Platform | Output/khả năng điển hình |
| --- | --- | --- |
| `jvm()` | JVM | Kotlin/JVM bytecode/JAR; có thể được Java/JVM Gradle module tiêu thụ |
| `js { nodejs() }` | JavaScript | Node.js tests/app JS output |
| `js { browser() }` | JavaScript | Browser JS output; browser test runner/cấu hình riêng |
| `wasmJs { browser() }` | WebAssembly JS interop | Wasm cho web/browser runtime theo toolchain |
| `wasmWasi { nodejs() }` hoặc `wasmtime()` | WebAssembly + WASI | Wasm/WASI runtime, constraints riêng |
| `linuxX64()` | Kotlin/Native | Linux x64 native library/executable theo binaries |
| `mingwX64()` | Kotlin/Native | Windows x64 native |
| `macosArm64()` | Kotlin/Native | macOS ARM64 |
| `iosArm64()` | Kotlin/Native | iOS device ARM64 |
| `iosSimulatorArm64()` | Kotlin/Native | iOS simulator ARM64 |
| `androidLibrary { ... }` kết hợp Android-KMP library plugin | Android/KMP | Android library variant và Android-specific source set/tooling |

Danh sách không đầy đủ và **target DSL cụ thể có thể thay đổi theo phiên bản Kotlin/AGP**. Android mới khác legacy `androidTarget`; phần Android ở cuối bài giải thích.

### Cùng platform có thể có nhiều target architectures

`iosArm64()` và `iosSimulatorArm64()` không phải “hai source sets cho cùng một target”. Chúng là **hai native targets**, mỗi target có platform source sets; plugin có thể tạo `iosMain` để chia sẻ code giữa chúng khi default hierarchy template phù hợp.

### Không nhầm JS và Wasm

`js { nodejs() }` dùng **Kotlin/JS compiler**. `wasmJs { nodejs() }` dùng **Kotlin/Wasm backend**; dù cùng Node runtime hỗ trợ, artifacts/compiler/APIs khác nhau. Một JS library npm không mặc nhiên chạy được như Kotlin/Wasm library.

## 6. Source set: nơi đặt mã, resources và dependency scope

Cấu trúc phổ biến:

~~~text
shared/
└── src/
    ├── commonMain/
    │   ├── kotlin/
    │   └── resources/
    ├── commonTest/
    │   └── kotlin/
    ├── jvmMain/
    │   └── kotlin/
    ├── jvmTest/
    │   └── kotlin/
    ├── jsMain/
    │   └── kotlin/
    └── jsTest/
        └── kotlin/
~~~

| Source set | Được dùng ở đâu | Có thể gọi APIs gì? |
| --- | --- | --- |
| `commonMain` | Main compilations của **mọi target đã khai báo** | Kotlin common stdlib, multiplatform dependencies, expected declarations |
| `commonTest` | Test compilations của mọi targets | `kotlin.test` và shared test helpers |
| `jvmMain` | Main compilation target `jvm` | Common APIs, JVM APIs như `java.time`, JVM libraries |
| `jvmTest` | Test compilation target `jvm` | Common + JVM test APIs |
| `jsMain` | Main compilation target `js` | Common + JS APIs, JS/npm compatible libraries |
| `jsTest` | Test compilation target `js` | Common + JS test environment/APIs |
| `iosMain` | Main của nhóm iOS targets khi hierarchy tạo ra | Common + những APIs hợp lệ cho nhóm iOS |
| `appleMain` | Main của nhóm Apple targets khi hierarchy tạo ra | Common + những APIs hợp lệ chung cho Apple targets |

**Kotlin source set không hoàn toàn đồng nghĩa Gradle Java `sourceSets.main`.** KMP có source set hierarchy mà một compilation kết hợp nhiều Kotlin source sets. Một Gradle project có **nhiều targets** và mỗi target có output/variants riêng. Đừng chuyển mọi Java plugin source-set convention sang KMP mà không kiểm tra API.

### Quy tắc chia sẻ mã

- Logic không gọi platform-specific APIs → `commonMain`.
- JVM-only functionality → `jvmMain`.
- JS-only functionality → `jsMain`.
- APIs chia sẻ trong một nhóm platforms, chẳng hạn iOS → intermediate source set nếu hierarchy hỗ trợ.
- Tests có thể chạy được ở mọi target → `commonTest`.
- Tests yêu cầu JVM reflection/filesystem/Mockito/JUnit → `jvmTest`, không `commonTest`.
- Tests dùng JS-only code/Node.js package → `jsTest`.

**Một common source set chỉ được phép tham chiếu APIs hợp lệ cho toàn bộ những targets compile source set đó.** `import java.time.LocalDate` trong `commonMain` của module JVM+JS sẽ không compile: Java API không tồn tại ở JS.

## 7. Source set hierarchy và `dependsOn`: một quan hệ khác Gradle task dependency

Khi source set B `dependsOn` source set A, B **nhìn thấy các declarations/dependencies phù hợp từ A** và compilation của B kết hợp code A. Ví dụ khái niệm:

~~~text
commonMain
   |
   +-- jvmMain
   |
   +-- jsMain

commonTest
   |
   +-- jvmTest
   |
   +-- jsTest
~~~

Trong KMP, `dependsOn` là **source set dependency**: nối tập source/code. Nó **không giống**:
- `tasks.named("test") { dependsOn("compileKotlinJvm") }`: Gradle task execution dependency.
- `dependencies { implementation(project(":shared")) }`: Gradle project/library dependency.
- `commonMain.dependencies { implementation("...") }`: external library dependency.

Các quan hệ này đều được Gradle plugin phối hợp, nhưng ý nghĩa khác nhau. **Đừng thêm `dependsOn` thủ công giữa mọi source sets chỉ vì nghĩ cần “nối task graph”**.

### Default hierarchy template

KMP có **default hierarchy template**: dựa trên targets, plugin tự tạo các intermediate source sets phù hợp. Ví dụ (mảnh **không ghép vào demo runnable** vì thêm native targets):

~~~kotlin
kotlin {
    iosArm64()
    iosSimulatorArm64()
    iosX64()
}
~~~

Nếu các targets trong cùng một module kích hoạt template phù hợp, Kotlin plugin có thể tạo `iosMain`/`iosTest` chia sẻ code cho nhiều iOS compilations. Khi thêm `macosArm64()`/`watchos...`, plugin có thể thêm `appleMain` trong hierarchy phù hợp.

**Không cần copy/paste `dependsOn(commonMain)` cho mỗi target** trong dự án dùng hierarchy mặc định. Mọi source set được tạo theo template không nhất thiết phải có thư mục vật lý nếu chưa có source files.

### Khi tùy biến manual `dependsOn`

Ví dụ low-level **minh họa** cho một nhóm native desktop, không phải full runnable build:

~~~kotlin
kotlin {
    linuxX64()
    mingwX64()
    macosArm64()

    sourceSets {
        val desktopMain by creating {
            dependsOn(commonMain.get())
        }
        linuxX64Main.get().dependsOn(desktopMain)
        mingwX64Main.get().dependsOn(desktopMain)
        macosArm64Main.get().dependsOn(desktopMain)
    }
}
~~~

**Cảnh báo quan trọng:** thêm explicit `dependsOn` edges có thể khiến KMP **không áp dụng default hierarchy template** và hiện warning. Khi custom hierarchy thật sự cần thiết, đọc [Source set hierarchy](https://kotlinlang.org/docs/multiplatform/multiplatform-hierarchy.html), dùng các options/apply template đúng phiên bản hoặc quyết định opt-out có chủ đích. Không lẫn một nửa manual edges với default template rồi giả định mọi intermediate sets vẫn được tạo như trước.

Manual hierarchy hữu ích khi có nhu cầu share APIs giữa một nhóm targets không được template bao phủ, nhưng làm Gradle model phức tạp hơn; với project mới nên **ưu tiên default hierarchy template**.

## 8. Compilation: có `main` và `test` cho mỗi target

Plugin thiết lập các compilations phổ biến:

~~~text
jvm target
  main compilation -> commonMain + jvmMain
  test compilation -> commonTest + jvmTest + relevant main outputs

js target (Node)
  main compilation -> commonMain + jsMain
  test compilation -> commonTest + jsTest + relevant main outputs
~~~

Một **compilation** có:
- Compile task/compile dependency files.
- Output.
- Compiler options.
- Participating Kotlin source sets.
- Runtime classpath/test runner association nếu target hỗ trợ.

Đây là lý do **`commonMain` không tự tạo một “common JVM JAR” có thể import trong Java**. Kotlin common metadata có thể được tạo cho module metadata, nhưng Java code cần **JVM variant** được biên dịch từ `commonMain + jvmMain`.

Cấu hình compiler options có ba tầng: extension-level defaults, target-level overrides, compilation/task-level overrides. Ví dụ **mảnh cấu hình**:

~~~kotlin
kotlin {
    compilerOptions {
        allWarningsAsErrors.set(true)
    }

    jvm {
        compilerOptions {
            // JVM-only compiler settings belong here.
        }
    }
}
~~~

Các option thấp hơn có thể override option cao hơn. Trong Kotlin Gradle Plugin mới, ưu tiên `compilerOptions { }`; `kotlinOptions { }` đã deprecated trong nhiều trường hợp.

## 9. `expect`/`actual`: nối common API với platform implementation

`commonMain` không thể gọi `java.lang.System` hoặc JS `window` trực tiếp. Nếu common logic cần một giá trị platform-specific, Kotlin có cơ chế `expect`/`actual`:

~~~text
commonMain:
  expect fun platformName(): String

jvmMain:
  actual fun platformName(): String = "JVM"

jsMain:
  actual fun platformName(): String = "JS"
~~~

Khi Kotlin compile JVM target, nó ghép common declarations với JVM actual implementation; khi compile JS target, nó ghép common declarations với JS actual. **Mỗi target cần một implementation compatible** cho expected declaration sử dụng. Nếu `jsMain` thiếu `actual`, JS compilation fail.

### Không dùng expect/actual quá mức

Nếu một logic có thể viết bằng interface và dependency injection, không cần expect/actual cho mọi class. Theo Kotlin docs, `expect/actual functions`/`properties` rất phù hợp khi phải bắc cầu platform APIs; **expect/actual classes** có thêm maturity/compatibility considerations. Đừng tự biến toàn bộ domain model thành expect classes khi classes có thể nằm hoàn toàn trong `commonMain`.

Ví dụ trong demo dưới đây dùng **expect/actual function** đơn giản để thấy rõ compilation theo target. Code chính `greet(name)` nằm trong common, còn `platformName()` được actualize trên JVM/JS.

## 10. Thực hành chạy được: KMP JVM + JS/Node và Java 17 consumer

Mục tiêu là một repository thật sự có **hai Gradle projects**:

- `:shared` áp dụng KMP plugin, khai báo **`jvm()` và `js { nodejs() }`**, gồm common code, platform implementations, shared tests và platform-specific tests.
- `:app` áp dụng Gradle core `application` plugin, viết **Java 17**, import Kotlin JVM-facing top-level function từ `:shared`. Gradle tự chọn JVM variant của KMP project thông qua variant-aware resolution.
- Không thêm Android/iOS trong runnable project vì chúng cần SDK/Xcode/host tương ứng.
- `jsNodeTest` dùng Node.js/Mocha theo Kotlin plugin; lần đầu có thể download npm/toolchain từ mạng.
- Tất cả file code và build scripts được cung cấp; ngoại lệ duy nhất là **Gradle Wrapper binaries/scripts**, phải tạo bằng `gradle wrapper` hoặc dự án mẫu do Gradle sinh (không viết giả wrapper JAR).

### 10.1. Cây thư mục

~~~text
kmp-gradle-lab/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── shared/
│   ├── build.gradle.kts
│   └── src/
│       ├── commonMain/kotlin/demo/shared/
│       │   ├── Greeting.kt
│       │   └── Platform.kt
│       ├── commonTest/kotlin/demo/shared/
│       │   └── GreetingCommonTest.kt
│       ├── jvmMain/kotlin/demo/shared/
│       │   └── PlatformJvm.kt
│       ├── jvmTest/kotlin/demo/shared/
│       │   └── PlatformJvmTest.kt
│       ├── jsMain/kotlin/demo/shared/
│       │   └── PlatformJs.kt
│       └── jsTest/kotlin/demo/shared/
│           └── PlatformJsTest.kt
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/App.java
~~~

Các source directories `commonMain`, `jvmMain`, `jsMain` thuộc **module `shared`**. Java source của `app` đặt ở `src/main/java` chuẩn Gradle Java plugin, **không** nằm trong `shared/src/jvmMain/java`. Tách module như vậy giảm rủi ro plugin interactions giữa `org.jetbrains.kotlin.multiplatform` và Java ecosystem plugin trong cùng một module.

### 10.2. `settings.gradle.kts` — file đầy đủ

~~~kotlin
rootProject.name = "kmp-gradle-lab"

include(":shared", ":app")
~~~

Dự án có hai Gradle subprojects. `:shared` là KMP module; `:app` là Java 17 application. Không bắt buộc đặt root `build.gradle.kts` nếu không có root configuration riêng.

### 10.3. `shared/build.gradle.kts` — file đầy đủ

~~~kotlin
plugins {
    kotlin("multiplatform") version "2.4.21"
}

repositories {
    mavenCentral()
}

kotlin {
    // JVM variant có thể được Gradle Java project chọn.
    jvm()

    // JS variant với Node.js làm môi trường chạy test.
    js {
        nodejs()
    }

    // Toolchain cho Kotlin/JVM; không biến JS thành JVM.
    jvmToolchain(17)

    sourceSets {
        commonTest.dependencies {
            implementation(kotlin("test"))
        }
    }
}
~~~

Giải thích từng phần:

1. `plugins { kotlin("multiplatform") ... }` áp dụng plugin chính thức cho `shared`.
2. `repositories { mavenCentral() }` cho Kotlin stdlib/test dependencies. **Plugin resolution** vẫn cần Plugin Portal hoặc `pluginManagement.repositories` thích hợp theo settings của Gradle.
3. `jvm()` tạo JVM target và compilations `main`/`test`. Không cần apply thêm `org.jetbrains.kotlin.jvm` trong cùng `shared`.
4. `js { nodejs() }` tạo JS target dùng Node.js. Không cần `binaries.executable()` vì project này là **shared library + tests**, không có `main()` JS application để chạy bằng JS run task.
5. `jvmToolchain(17)` chọn JDK 17 cho Kotlin/JVM build toolchain; Java app dùng Java17 toolchain riêng.
6. `commonTest.dependencies { implementation(kotlin("test")) }` cấp Kotlin test API và chọn platform-specific implementations cho JVM/JS. **Không dùng JUnit5 dependency ở commonTest** vì JS không chạy JVM/JUnit5.
7. Đoạn này không thêm explicit `dependsOn`. KMP default source set hierarchy đã xử lý common ↔ target source sets.

**Lưu ý về test frameworks:** mặc định Kotlin/JVM dùng JUnit 4 variant khi chỉ `kotlin("test")`; Kotlin/JS Node dùng Mocha. Nếu team yêu cầu JUnit5, cấu hình JVM test run `useJUnitPlatform()` và dependencies đúng như phần nâng cao, không tự gọi JUnit5 trong `commonTest`.

### 10.4. `shared/src/commonMain/kotlin/demo/shared/Greeting.kt`

~~~kotlin
package demo.shared

fun greet(name: String): String {
    require(name.isNotBlank()) {
        "name must not be blank"
    }
    return "Hello, " + name + " from " + platformName() + "!"
}
~~~

`greet` dùng API Kotlin common (`String.isNotBlank`, `require`, string concatenation), nên compile được sang JVM và JS. Nó gọi `platformName` là một expected declaration được actualized riêng.

### 10.5. `shared/src/commonMain/kotlin/demo/shared/Platform.kt`

~~~kotlin
package demo.shared

expect fun platformName(): String
~~~

Khai báo chỉ có signature. `commonMain` không viết JVM/JS implementation.

### 10.6. `shared/src/jvmMain/kotlin/demo/shared/PlatformJvm.kt`

~~~kotlin
package demo.shared

actual fun platformName(): String = "JVM"
~~~

Đây là actual implementation cho `jvm()`. Kotlin/JVM compiler ghép nó với common `expect` khi tạo JVM classes.

### 10.7. `shared/src/jsMain/kotlin/demo/shared/PlatformJs.kt`

~~~kotlin
package demo.shared

actual fun platformName(): String = "JS"
~~~

Đây là actual implementation cho `js { nodejs() }`. Trên JS, `platformName()` trả `JS` chứ không phải `JVM`.

### 10.8. `shared/src/commonTest/kotlin/demo/shared/GreetingCommonTest.kt`

~~~kotlin
package demo.shared

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class GreetingCommonTest {

    @Test
    fun greetUsesThePlatformName() {
        assertEquals(
            "Hello, Ada from " + platformName() + "!",
            greet("Ada")
        )
    }

    @Test
    fun blankNameIsRejected() {
        assertFailsWith<IllegalArgumentException> {
            greet("   ")
        }
    }
}
~~~

Hai tests dùng `kotlin.test` chung. Khi compile sang JVM, chúng chạy trong `jvmTest` compilation; khi compile sang JS, chúng tham gia JS Node test run. Không dùng `java.lang.System`/`org.junit.jupiter.api.Test` trong `commonTest`.

### 10.9. `shared/src/jvmTest/kotlin/demo/shared/PlatformJvmTest.kt`

~~~kotlin
package demo.shared

import kotlin.test.Test
import kotlin.test.assertEquals

class PlatformJvmTest {

    @Test
    fun jvmImplementationIsSelected() {
        assertEquals("JVM", platformName())
    }
}
~~~

Test này chỉ dùng `jvmTest`; nó xác minh JVM actual implementation.

### 10.10. `shared/src/jsTest/kotlin/demo/shared/PlatformJsTest.kt`

~~~kotlin
package demo.shared

import kotlin.test.Test
import kotlin.test.assertEquals

class PlatformJsTest {

    @Test
    fun jsImplementationIsSelected() {
        assertEquals("JS", platformName())
    }
}
~~~

Test này chỉ dùng `jsTest`. Kotlin JS test infrastructure dựa trên Node.js/Mocha ở target này, **không chạy JVM JUnit**.

### 10.11. `app/build.gradle.kts` — Java 17 consumer file đầy đủ

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation(project(":shared"))
}

application {
    mainClass.set("demo.app.App")
}
~~~

**Điểm cần hiểu:** Java `:app` không apply KMP plugin. Nó là **Gradle Java/Application project** bình thường. `implementation(project(":shared"))` yêu cầu Gradle resolution chọn **biến thể JVM phù hợp** từ KMP library, không compile mọi target của `:shared`.

Plugin Kotlin/Gradle xuất JVM variant cùng Gradle attributes, module metadata và Kotlin stdlib runtime dependencies phù hợp. Nếu chỉ publish JS/native mà không khai báo `jvm()`, một Java consumer sẽ thiếu JVM variant và dependency resolution fail.

### 10.12. `app/src/main/java/demo/app/App.java` — Java 17 đầy đủ

~~~java
package demo.app;

import demo.shared.GreetingKt;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(GreetingKt.greet("Java"));
    }
}
~~~

**Vì sao import `GreetingKt`?** Trên JVM, Kotlin top-level function `fun greet(...)` từ file `Greeting.kt` được biên dịch thành Java-callable static function trên một class facade thường đặt theo tên file: `GreetingKt`. Đây là naming rule JVM-specific, **không áp dụng cho JavaScript/Native**.

Nếu file Kotlin đổi tên, Java facade name có thể đổi theo; khi cần API ổn định cho Java consumers, có thể dùng `@file:JvmName("...")` trong Kotlin/JVM-facing module/source phù hợp. Trong demo giữ tên file cố định để import chính xác.

### 10.13. Tạo Gradle Wrapper hợp lệ

Cần Gradle installation có sẵn để bootstrap nếu chưa có Wrapper:

~~~bash
gradle wrapper --gradle-version 9.7.0 --distribution-type bin
~~~

Sau đó kiểm tra:

~~~bash
./gradlew --version
~~~

Ở Windows PowerShell:

~~~powershell
.\gradlew.bat --version
~~~

Wrapper phải tải Gradle 9.7.0. Kotlin 2.4.21 compatibility guide nêu support tới Gradle9.7.0; dùng một version mới hơn chưa được liệt kê là **một quyết định upgrade cần test**, không phải thay tùy tiện. Nếu script `gradle` global không có sẵn, dùng Gradle official installation hoặc project skeleton được tạo với Wrapper phù hợp.

Không viết thủ công `gradle-wrapper.jar`. Commit cả `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle/wrapper/gradle-wrapper.properties` sau khi tạo từ nguồn tin cậy. Trên Linux, xác nhận executable bit `gradlew` được lưu trong Git.

### 10.14. Chạy tests và Java application

Linux/macOS:

~~~bash
./gradlew :shared:jvmTest :shared:jsNodeTest --console=plain
./gradlew :app:run --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat :shared:jvmTest :shared:jsNodeTest --console=plain
.\gradlew.bat :app:run --console=plain
~~~

**Stdout chính xác của Java program từ `App.main`:**

~~~text
Hello, Java from JVM!
~~~

Gradle có thể in task logs, dependency downloads và `BUILD SUCCESSFUL` trước/sau Java output. Chỉ dòng trên là stdout của chương trình Java, không phải toàn bộ terminal output.

Ở lần chạy tests, các assertions dự kiến PASS:
- `GreetingCommonTest.greetUsesThePlatformName` trên JVM và JS.
- `GreetingCommonTest.blankNameIsRejected` trên JVM và JS.
- `PlatformJvmTest.jvmImplementationIsSelected` trên JVM.
- `PlatformJsTest.jsImplementationIsSelected` trên Node.js.

Kết quả task outcomes có thể `SUCCESS`, `UP-TO-DATE` hoặc `FROM-CACHE` tùy trạng thái build/cache; **không bịa số downloads hay task count cố định**. Kotlin/JS plugin có thể tải Node toolchain/npm test runners lần đầu, nên cần network và môi trường cho phép.

### 10.15. Chạy lifecycle/quan sát tasks

~~~bash
./gradlew :shared:tasks --all
./gradlew :shared:check
./gradlew :app:build
./gradlew :app:run --quiet
~~~

`:shared:check` thường gom test runs cho các target khai báo và môi trường test được cấu hình; một target không chạy được trên host hoặc chưa cấu hình test runner có thể có khác biệt. Trong demo `jvm` và `js nodejs` là hai targets phù hợp cho Windows/macOS/Linux nếu JDK/Node tooling và network đúng.

Khi thêm iOS targets, đừng giả định một Linux runner có thể chạy iOS simulator tests. Bài này không ép Android/iOS tasks vào baseline CI trên một host không hỗ trợ.

### 10.16. Các tác động khi sửa source

| Thay đổi | Compile/tests nào bị ảnh hưởng? |
| --- | --- |
| Sửa `commonMain/Greeting.kt` | Cả JVM và JS compilations dùng common code phải cập nhật theo Gradle fingerprint |
| Sửa `jvmMain/PlatformJvm.kt` | JVM variant thay đổi; JS code không tham chiếu file JVM |
| Sửa `jsMain/PlatformJs.kt` | JS variant thay đổi; JVM variant không phụ thuộc JS implementation |
| Sửa `commonTest/GreetingCommonTest.kt` | JVM/JS test compilations dùng shared tests bị ảnh hưởng |
| Sửa `jvmTest/PlatformJvmTest.kt` | JVM test compilation; không phải JS test code |
| Sửa `app/src/main/java/demo/app/App.java` | Java app compilation; KMP `shared` source không đổi |
| Sửa KMP plugin version | Plugin task implementation/compiler/metadata có thể invalidation rộng |

Đây là **hướng ảnh hưởng theo dependency graph**, không phải cam kết Gradle chỉ chạy lại một task ở mọi môi trường. Compiler caches, Build Cache, toolchain changes và Gradle task implementation hashes quyết định outcome cụ thể.

## 11. Vì sao Java application nhận JVM variant mà không nhận JS?

Gradle có **variant-aware dependency resolution**. Khi Java `:app` yêu cầu `implementation(project(":shared"))`, nó cần một **library variant** dùng được trên JVM. KMP plugin cấu hình attributes/capabilities/artifacts phù hợp từng target.

Mô hình:

~~~text
:shared KMP project
  common metadata (chứa thông tin common/source-set/module)
  JVM target variant --> JAR/class files, JVM runtime deps
  JS target variant  --> JS artifacts, JS/npm deps

:app Java project
  compile/runtime classpath requests a JVM-compatible variant
                  |
                  v
              :shared JVM
                  |
                  v
          demo.shared.GreetingKt
~~~

Nếu Gradle không tìm được matching variant, bạn sẽ thấy lỗi dạng **“No matching variant ...”** cùng attributes/consumer requirements. Không phải “Gradle không biết Kotlin”; cần đọc attributes, JVM target compatibility, plugin version và dependency wiring.

**Không copy `shared/build/libs/*.jar` thủ công vào `app/libs` như giải pháp mặc định.** Làm vậy mất project producer task dependencies, Gradle Module Metadata và transitive dependency resolution. Dùng `implementation(project(":shared"))` là contract đúng giữa các modules.

### Root KMP publication và platform publications

Khi dùng `maven-publish`, KMP plugin có thể tạo:
- **Root `kotlinMultiplatform` publication**: metadata entry point, ví dụ `group:artifact:version`, không phải một JAR duy nhất chạy trên mọi platform.
- **Target-specific publications**: ví dụ `group:artifact-jvm:version`, `group:artifact-js:version`, native variants tương ứng.
- Gradle Module Metadata để Gradle/Kotlin consumer tìm đúng artifact theo platform/source-set usage.

Không xuất thủ công một `:shared:jvm` JAR rồi gọi nó “KMP root artifact”. Khi publish KMP module, root metadata và targets phải được publish **đồng bộ**; thiếu một artifact được metadata tham chiếu sẽ làm dependency consumers lỗi.

## 12. Dependencies: `commonMain` khác `jvmMain`/`jsMain`

Nếu một library thật sự có multiplatform variants cho các platforms bạn cần, thêm ở `commonMain`:

~~~kotlin
kotlin {
    sourceSets {
        commonMain.dependencies {
            implementation(
                "org.jetbrains.kotlinx:kotlinx-coroutines-core:1.11.0"
            )
        }
    }
}
~~~

Đây là **mảnh minh họa** cho KMP library với Coroutines và versions cần kiểm tra theo compatibility matrix; không thuộc demo runnable vốn chỉ dùng Kotlin standard library. `commonMain` không được thêm JVM-only library như một API common nếu JS consumer cũng cần compile.

Với JVM-specific library:

~~~kotlin
kotlin {
    sourceSets {
        jvmMain.dependencies {
            implementation("com.google.guava:guava:33.5.0-jre")
        }
    }
}
~~~

Đây là mảnh source-set dependency, không bắt buộc cho demo và không dùng trực tiếp từ `commonMain`. Guava là JVM dependency; nếu bạn muốn một chức năng dùng chung thì bọc qua interface/`expect/actual`, đặt Guava call trong `jvmMain`, cung cấp JS implementation khác.

Với Kotlin/JS npm-only library:

~~~kotlin
kotlin {
    sourceSets {
        jsMain.dependencies {
            implementation(npm("left-pad", "1.3.0"))
        }
    }
}
~~~

Đây là **mảnh minh họa JS-only dependency**; đừng copy vào commonMain hoặc JVM classpath. npm package/version là ví dụ quy tắc syntax; không có code sử dụng package nên không cần đưa vào runnable build.

### Phân biệt `api` và `implementation`

Trong source-set dependency DSL:
- `api(...)` dùng cho dependency được lộ ra như một phần public API của library.
- `implementation(...)` dùng cho dependency chi tiết nội bộ, không tự đưa vào compile API của consumer.
- `compileOnly(...)` chỉ compile-time trong những source sets/targets hỗ trợ.
- `runtimeOnly(...)` chỉ runtime theo backend tương ứng.

Chọn `api` không làm một JVM-only dependency trở thành multiplatform; Gradle/KMP vẫn yêu cầu variants phù hợp và source set API constraints.

## 13. Tests: `commonTest` không đồng nghĩa chạy đúng một lần

Các files `commonTest` được **compile và chạy theo các target test runs**. Một function kiểm thử ở commonTest có thể được chạy hai lần: một lần qua JVM test task, một lần qua JS Node test task. Điều này có giá trị vì cùng contract có thể gặp bug chỉ ở backend khác.

~~~text
commonTest (kotlin.test)
     /                 \
jvmTest compilation  jsTest compilation
     |                 |
 JUnit 4 default       Mocha on Node
     |                 |
 :shared:jvmTest      :shared:jsNodeTest
~~~

Theo Kotlin docs, khi dùng `kotlin("test")` với JVM mặc định framework là JUnit 4; nếu muốn JUnit 5:

~~~kotlin
kotlin {
    jvm {
        testRuns["test"].executionTask.configure {
            useJUnitPlatform()
        }
    }
    sourceSets {
        commonTest.dependencies {
            implementation(kotlin("test"))
        }
    }
}
~~~

Đây là **mảnh thay thế/cấu hình thêm**, không phải một project runnable độc lập. Khi chuyển framework, kiểm tra runtime engine/launcher dependencies thích hợp cho Kotlin compiler/plugin version; có thể cần explicit `kotlin("test-junit5")` hoặc JUnit Platform Launcher theo Gradle test setup. **Không gọi `useJUnitPlatform()` trong commonTest**, vì commonTest không phải Gradle JVM Test task và JS không dùng JUnit Platform.

### Không để test framework rò vào business code

`kotlin.test` dành cho tests (`commonTest`) thay vì `commonMain`. Nếu đưa `org.junit.jupiter.api.Test` vào commonTest của module JVM+JS, JS compilation sẽ lỗi do JUnit JVM-only. Nếu cần JVM-only assertions hoặc test libraries (Mockito, Testcontainers), đặt ở `jvmTest`.

### Browser testing không giống Node

KMP `js { browser() }` cần browser test runner (Karma legacy hoặc DSL mới có maturity constraints theo Kotlin 2.4 docs). KMP `js { nodejs() }` dùng Node.js/Mocha. Không giả định laptop/CI có Chrome/Playwright được cài chỉ vì có Node. Demo chọn Node để tránh dependency browser-specific.

## 14. Tổ chức code theo common/platform để tránh sao chép

Một cách chọn source set theo câu hỏi:

1. **Có thể implement hoàn toàn bằng Kotlin common stdlib?** → commonMain.
2. **Cần một API system thuộc JVM, Android hoặc Native?** → platform-specific source set.
3. **Nhiều Apple targets có cùng API, nhưng JS/JVM không có?** → intermediate `appleMain`/`iosMain` nếu hierarchy tạo.
4. **Cần platform feature trong common contract?** → interface/DI hoặc `expect/actual`.
5. **Là test chung?** → commonTest; platform-only test → targetTest.

Ví dụ logic validation chỉ kiểm tra email text có thể nằm ở commonMain. Code truy cập `java.nio.file.Path` phải nằm ở jvmMain. Trên JS, xử lý file Node sẽ dùng APIs riêng; nếu common contract cần lưu dữ liệu, thiết kế một interface `Storage` rồi cung cấp implementation cho target tương ứng, hoặc expected declarations.

**Không đưa một source folder chung rồi add cùng file vào JVM và JS compilations một cách thủ công** khi KMP đã có `commonMain`; như vậy có thể mất khả năng phân tích common API/metadata và bị lặp code.

## 15. Android trong KMP: plugin nào tạo Android target?

Phần này được tách riêng vì **AGP 9.x thay đổi mô hình Android integration**. KMP plugin không phải Android SDK/AGP replacement.

**Android module chia sẻ logic (KMP library)** với AGP9 hướng tới plugin:
- `org.jetbrains.kotlin.multiplatform` từ JetBrains.
- `com.android.kotlin.multiplatform.library` từ Android Gradle Plugin.

Mảnh **minh họa**, cần Android SDK/AGP version tương thích và namespace/compileSdk thực, không chạy nếu paste vào demo Java+JS:

~~~kotlin
plugins {
    id("org.jetbrains.kotlin.multiplatform") version "2.4.21"
    id("com.android.kotlin.multiplatform.library") version "9.3.1"
}

kotlin {
    androidLibrary {
        namespace = "demo.shared.android"
        compileSdk = 36
        minSdk = 24
    }
}
~~~

**Phiên bản AGP/SDK trong mảnh chỉ minh họa cấu trúc và phải kiểm chứng với Android tooling installation/project constraints**; đừng dùng ví dụ như một template chắc chắn phù hợp mọi Android Studio/JDK. Kotlin compatibility guide công bố dải AGP của 2.4.20–2.4.21 tới 9.3.1; nếu nâng riêng AGP vượt dải này, cần đọc guide mới.

### Phân biệt legacy Android DSL

Các dự án cũ dùng `androidTarget()` cùng `com.android.library` hoặc `com.android.application` trong shared module. Trong AGP9+, Kotlin docs hướng tới Android-KMP library plugin mới. **Không máy móc trộn `androidTarget()` và `androidLibrary { }`** hoặc apply nhiều Android plugins trong cùng shared module; đọc [AGP9 migration guide](https://kotlinlang.org/docs/multiplatform/multiplatform-project-agp-9-migration.html).

Khi có **Android application entry point**, kiến trúc thường tách:
- `:shared` KMP library, Android target qua Android-KMP library plugin.
- `:androidApp` Android application plugin cho UI/manifest/signing/distribution.
- `androidApp` phụ thuộc `project(":shared")` và Gradle chọn đúng Android variant.

Mục tiêu là **không để một KMP shared module đồng thời làm Android app entry point** nếu AGP/plugin versions không cho phép.

## 16. iOS/Apple target: Gradle khai báo nhưng Xcode/host vẫn cần

KMP native targets thường gặp:

~~~kotlin
kotlin {
    iosArm64()
    iosSimulatorArm64()
    iosX64()
}
~~~

Đây là **mảnh mở rộng**, không paste vào demo runnable nếu không có Xcode/Apple development requirements. Các native targets có thể hỗ trợ cross-compiling một số library `.klib` từ nhiều hosts, nhưng **build/test final iOS app/framework có interop, CocoaPods hoặc simulator execution** thường yêu cầu **macOS + Xcode**. Kotlin/Native target availability còn phụ thuộc host, binary type và plugin versions.

### Framework cho Swift

Một KMP shared module dùng bởi iOS app có thể cấu hình framework binaries, ví dụ:

~~~kotlin
kotlin {
    iosArm64()
    iosSimulatorArm64()

    listOf(
        iosArm64(),
        iosSimulatorArm64()
    ).forEach { target ->
        target.binaries.framework {
            baseName = "SharedKit"
            isStatic = true
        }
    }
}
~~~

**Lưu ý:** đây là **mảnh mô tả công việc framework** cho một Gradle KMP module, không phải file đầy đủ. Không thêm khai báo `iosArm64()` trùng ở trên và trong list trong cùng một file; dùng **một cách đăng ký targets**. Mẫu được viết kiểu diễn giải để thấy ý tưởng tạo framework cho từng target, nhưng khi chuyển thành code thật cần lấy target providers/instances một lần, đọc DSL docs theo plugin version và kiểm tra host/Xcode. Hãy dùng Kotlin official iOS templates khi cần actual runnable iOS integration.

Đừng hiểu **KMP target = artifact tự đủ để cài chạy iOS app**. Kotlin/Native framework chỉ là phần binary dùng bởi iOS application, build/sign/test vẫn ở Apple toolchain.

## 17. Kotlin/JS và Kotlin/Wasm: cùng là web nhưng backend khác nhau

Bằng KMP plugin, có thể khai báo:

~~~kotlin
kotlin {
    js {
        browser()
        binaries.executable()
    }
}
~~~

Hoặc:

~~~kotlin
kotlin {
    wasmJs {
        browser()
        binaries.executable()
    }
}
~~~

**Đây là hai mảnh cấu hình cho những dự án khác nhau, không phải cùng một JS target**. Các prerequisites về browser test runner/webpack/dev server/runtime support khác nhau. Kotlin/JS biên dịch JavaScript; Kotlin/Wasm biên dịch WebAssembly. Một native JS dependency không mặc định trở thành Wasm-compatible dependency.

Trong demo sử dụng `js { nodejs() }` cho **library tests**, không thêm `binaries.executable()` hoặc `main()` JS vì mục tiêu là shared source sets/targets và Java consumer. Nếu muốn có executable Node application, tạo `src/jsMain/kotlin/.../Main.kt` với `fun main()` và bật `binaries.executable()`; dùng `jsNodeDevelopmentRun` theo Kotlin docs, đồng thời xác minh dependency/setup Node.

### Browser test framework hiện hành

Theo Kotlin 2.4 docs, Karma test runner là legacy/deprecated (không có planned fixes), còn browser test DSL mới vẫn Experimental và có opt-in. **Đừng khẳng định mọi KMP 2.4 browser test chạy tự động trên Chrome đã cài**; CI cần browser dependencies và runner configuration. Node/Mocha đơn giản hơn cho bài tập backend-neutral.

## 18. Gradle tasks sinh ra từ target model

Kotlin plugin có thể đăng ký tasks dựa trên target name, compilation và execution environment. Một số task names trong demo:

| Task | Vai trò |
| --- | --- |
| `:shared:compileKotlinJvm` | Biên dịch Kotlin common+jvmMain thành JVM output |
| `:shared:compileTestKotlinJvm` | Biên dịch JVM test code/commonTest |
| `:shared:jvmTest` | Chạy tests JVM qua Gradle Test infrastructure |
| `:shared:compileKotlinJs` | Biên dịch Kotlin common+jsMain sang JS IR/backend |
| `:shared:jsNodeTest` | Chạy JS tests trong Node.js |
| `:shared:check` | Aggregate verification cho KMP targets được cấu hình |
| `:shared:tasks --all` | Xem tasks do plugin đăng ký (CLI, không phải build artifact) |
| `:app:compileJava` | Compile Java source, chọn JVM variant của :shared |
| `:app:run` | Chạy Java main class với JVM runtime classpath |
| `:app:build` | Java application lifecycle build |

**Tên task của KMP có thể phụ thuộc plugin version, target name, compilation và JS runner mode.** Trước khi automation dùng một task ít phổ biến, chạy `./gradlew :shared:tasks --all` để xác minh chính xác. Với nhiều host targets, `check` có thể kéo nhiều test binaries/compilers hơn dự kiến. Khi đặt tên target khác default, tasks/source sets cũng đổi tên tương ứng.

### Task graph không phải target hierarchy

Ví dụ `:app:run` tiêu thụ `:shared` JVM variant:
- Gradle resolution chọn JVM producer variant.
- Task graph đảm bảo JVM classes/JAR/dependencies được tạo trước khi Java run cần.
- Java app không tự gọi JS compilation/test task nếu không có dependency khác.

Ngược lại `:shared:check` có thể chạy JVM và JS test tasks cho shared module. Đừng dùng `:app:run` để tuyên bố “đã test KMP JS target” chỉ vì module shared có `js()`.

## 19. Có nên thêm Java source trực tiếp vào KMP module?

Kotlin Multiplatform `jvm()` hỗ trợ interop với Java/JVM, nhưng Gradle/Kotlin docs lưu ý giới hạn tương thích khi trộn Java ecosystem plugins trong **cùng một KMP module**. Các APIs cũ như `withJava()`/legacy `jvmWithJava` có migration history riêng, không phải universal solution cho mọi Gradle/plugin version.

**Kiến trúc demo chọn an toàn:** 
- KMP module `:shared` chứa common + JVM + JS Kotlin.
- Java 17 application `:app` riêng áp dụng `application`/Java plugin.
- `app` phụ thuộc `project(":shared")` để chọn JVM variant.

Nếu thực sự cần `.java` trong KMP `jvmMain`, đọc [KMP compatibility guide](https://kotlinlang.org/docs/multiplatform/multiplatform-compatibility-guide.html) và hướng dẫn Java source-set support của Kotlin version đã pin; cấu hình Java compile tasks/source directories đúng, không assume `src/main/java` của Java plugin được KMP `jvm()` tự biết.

### Java 17 interop có giới hạn platform

Trong Java app có thể gọi top-level Kotlin `greet` thông qua `GreetingKt`. Điều này **chỉ khả dụng với JVM variant**; Java không gọi `JS` artifacts. Kotlin nullability, default arguments, suspend functions và unsigned types có JVM-facing API shape riêng; nếu public library phục vụ Java callers, review ABI/interoperability và cân nhắc wrapper APIs/JVM-specific annotations.

## 20. Publishing KMP library: root metadata và target-specific artifacts

Thêm Gradle plugin `maven-publish` vào `shared` khi thực sự muốn publish một library:

~~~kotlin
plugins {
    kotlin("multiplatform") version "2.4.21"
    id("maven-publish")
}

group = "dev.learning"
version = "1.0.0"
~~~

Đây là **mảnh thay thế phần plugin/group/version** của shared project, chưa cấu hình remote repository. Trong nhiều KMP library projects, `maven-publish` tạo publications gồm:
- Root `kotlinMultiplatform` module, chứa metadata entry point.
- JVM artifact/publication.
- JS artifact/publication.
- Native publications cho targets có thể build/publish trên host.
- Android publication cần configuration riêng theo Android Gradle library plugin.

Với Maven Local, sau khi cấu hình thích hợp và plugin compatible:

~~~bash
./gradlew :shared:publishToMavenLocal
~~~

Đây là **lệnh cho phiên bản build đã bổ sung `maven-publish`**, không chạy trên demo runnable mặc định (nơi chưa thêm publish plugin). Không upload thật lên Maven Central/GitHub Packages chỉ vì mục tiêu học task model.

### Không publish root publication một mình

Root metadata tham chiếu target artifacts. Nếu chỉ publish `kotlinMultiplatform` root mà không có JVM/JS target publications, consumer không tìm được variants. Với remote publishing, dùng all-publications umbrella task/repository phù hợp và đảm bảo target/host support. Không publish cùng tọa độ/version từ nhiều hosts đồng thời nếu repository từ chối duplicates.

### Vì sao Gradle Module Metadata quan trọng?

Một KMP coordinate có thể cung cấp nhiều variants; Gradle Module Metadata giữ platform attributes/source-set metadata để consumer chọn artifact đúng. Maven POM thông thường khó mô tả đầy đủ cấu trúc này. Vì vậy KMP publication thường đi kèm metadata chuyên dụng.

**Không biến KMP module thành một “single JAR” rồi mất JS/native variants**, trừ khi mục tiêu thực tế chỉ cần JVM. Nếu chỉ cần JVM, `org.jetbrains.kotlin.jvm` đơn giản hơn.

## 21. Version catalogs và quản trị plugin KMP trong repository lớn

Thay version literal bằng `gradle/libs.versions.toml` có thể tạo nguồn quản trị tập trung:

~~~toml
[versions]
kotlin = "2.4.21"

[plugins]
kotlin-multiplatform = {
    id = "org.jetbrains.kotlin.multiplatform",
    version.ref = "kotlin"
}
~~~

Và ở `shared/build.gradle.kts`:

~~~kotlin
plugins {
    alias(libs.plugins.kotlin.multiplatform)
}
~~~

Đây là **mảnh cấu hình thay thế** plugin block của demo, không paste song song với version literal. Version catalog tạo typed accessor `libs.plugins.kotlin.multiplatform` theo alias `kotlin-multiplatform`. Nếu root build dùng `apply false` và included build riêng, lưu ý **version catalogs không tự xuất hiện trong mọi included build/buildSrc**; cần cấu hình riêng hoặc import catalog theo Gradle docs.

Trong multi-project KMP, giữ Kotlin plugin version nhất quán giúp tránh plugin classloader/resolution conflict. Nhưng **không nâng Kotlin version chỉ để có API mới mà quên xem Gradle/AGP/Xcode compatibility table**.

## 22. Android/iOS UI application không phải KMP plugin duy nhất

Đối với một ứng dụng thực:
- KMP plugin tạo **shared code module** và variants.
- Android Gradle Plugin tạo **Android application** hoặc Android-specific library/target integration.
- Xcode/Swift Package Manager/Apple project quản lý iOS app packaging/signing.
- Compose Multiplatform (nếu chọn) thêm UI/compiler/runtime tooling.
- Java Application plugin có thể tạo JVM backend/desktop process nếu app là Java.

Vì vậy một sơ đồ nhiều nền tảng có thể là:

~~~text
Gradle root
  :sharedLogic [org.jetbrains.kotlin.multiplatform]
    - commonMain
    - androidMain / iosMain / jvmMain / jsMain ...
    - platform publications/frameworks
  :androidApp  [Android application plugin]
  :desktopApp  [JVM Application plugin]
  :webApp      [Kotlin/JS/Wasm toolchain]
  :server      [Kotlin/JVM or Java plugin]

Xcode workspace (iOS)
  iosApp -> uses shared Kotlin/Native framework
~~~

Mỗi app entry-point module có runtime/deployment responsibility riêng. **KMP plugin không thay mọi application/publishing plugins**. Bài demo cố tình chọn Java JVM consumer để nhấn mạnh Gradle variants và interoperability, không lấy Android/iOS toolchain làm điều kiện học KMP concepts.

## 23. Khi nào không nên dùng Kotlin Multiplatform?

KMP có lợi khi:
- Có logic đáng kể cần chia sẻ giữa JVM/Android/iOS/JS/native.
- Team chấp nhận KMP toolchain/compiler/test matrix.
- Thư viện third-party quan trọng có KMP variants hoặc có thể bọc platform APIs.
- CI có runner/SDK/toolchain phù hợp cho targets thực sự cần.
- Quy trình release cần đảm bảo variant metadata/compatibility.

KMP có thể không phải lựa chọn tối ưu nếu:
- Chỉ xây Java backend/JVM service, không cần target khác → dùng `java`/`org.jetbrains.kotlin.jvm`.
- Chỉ muốn web frontend TypeScript không có shared Kotlin logic → KMP có thể thêm complexity không cần.
- Project cần một JVM-only library không có KMP equivalents trên JS/native → cost của refactoring/expect actual cao.
- Không có macOS/Xcode runner nhưng bắt buộc iOS tests/cinterop pipeline → không thể hứa CI toàn platform chạy đủ.
- Build toolchain và plugin ecosystem không có release compatibility cần thiết.

**KMP là một quyết định kiến trúc để tái sử dụng source code**, không phải yêu cầu mặc định cho mọi dự án Kotlin hoặc Gradle.

## 24. Chẩn đoán Gradle sync và compilation

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm chứng |
| --- | --- | --- |
| `Unresolved reference: kotlin` trong `plugins` DSL | Gradle Kotlin DSL context/plugin resolution sai | Kiểm tra `build.gradle.kts`, Plugin Portal, Wrapper |
| `Plugin not found` | Plugin ID/version/repository không đúng | `org.jetbrains.kotlin.multiplatform` và `pluginManagement.repositories` |
| Kotlin 2.4.21 với Gradle 9.9 lỗi lạ | Combo vượt dải đã được guide công bố | Hạ Wrapper về Gradle9.7.0 đã ghi nhận compatible hoặc chờ plugin guide mới |
| Không thấy `jvmMain`/`jsMain` trong IDE | Target chưa được khai báo hoặc Gradle Sync stale | `kotlin { jvm(); js { nodejs() } }`, Reload Gradle |
| `Unresolved reference: java.time` trong commonMain | Common code dùng JVM-only API | Di chuyển sang jvmMain hoặc dùng expect/actual/interface |
| `Expected declaration ... has no actual` | Thiếu actual ở một target | Tạo đúng package/signature trong jsMain/jvmMain |
| `Actual ... has no corresponding expect` | Sai package/name/type/scope | So exact expect/actual declarations, source-set hierarchy |
| JVM tests pass, JS tests fail | JS actual/library API khác | Xem `jsNodeTest` logs, JS runtime/deps |
| `No matching variant` khi Java app dùng :shared | Không có jvm target/attributes mismatch | `jvm()`, `:app:dependencies`, JVM toolchain |
| `Could not resolve kotlin-stdlib` | Maven repo/offline/proxy | `repositories { mavenCentral() }`, network, cache |
| `Could not resolve Kotlin plugin` | Plugin repository/version | `pluginManagement`, connectivity |
| `Task jsNodeTest not found` | Chưa khai báo JS node target hoặc version/task naming khác | `:shared:tasks --all` |
| Node download/npm lỗi | Network/registry, certificate, Node install restrictions | JS setup logs, proxy/CI mirror |
| Browser tests fail missing Chrome | Browser runner toolchain chưa setup | Browser test DSL/Karma/Playwright config |
| JUnit Platform not found | Nhầm JUnit5 với JVM default KMP Kotlin test | JVM testRuns configuration và dependencies |
| JS code không thấy JVM-only lib | Dependency ở jvmMain, không có JS variant | Dùng multiplatform lib hoặc JS-specific implementation |
| Default hierarchy warning | Manual `dependsOn` edges chặn template | Xóa edges không cần hoặc thiết kế hierarchy có chủ đích |
| `iosMain` không được tạo | Không có set iOS targets phù hợp | Xem Kotlin default hierarchy conditions |
| iOS tasks fail trên Linux | Apple final artifacts/simulator cần macOS/Xcode | Chạy trên macOS CI; phân biệt klib cross-compile |
| Android target DSL không được nhận | AGP/KGP mismatch hoặc legacy Android plugin | Android-KMP plugin + compat matrix/migration guide |
| `withJava()` deprecation/compatibility | Java plugin integration legacy | Dùng module Java consumer riêng hoặc guide cụ thể |
| IDE Java import `GreetingKt` không được | IDE chưa import JVM variant hoặc file name khác | `:shared:compileKotlinJvm`, `:app:compileJava`, Gradle sync |
| Java app runtime `NoClassDefFoundError` Kotlin | Runtime classpath bị tự dựng sai | Dùng `implementation(project(":shared"))`, Gradle `run` |
| KMP publishing thiếu JS artifact | Chỉ publish root/JVM target | Publish all publications, verify module metadata |
| Build quá nặng | Khai báo targets không cần, JS/native toolchains | Chỉ khai báo targets thật sự cần, CI matrix hợp lý |

### Các lệnh điều tra thực dụng

~~~bash
./gradlew --version
./gradlew :shared:tasks --all
./gradlew :shared:compileKotlinJvm --info
./gradlew :shared:jvmTest --info
./gradlew :shared:jsNodeTest --info
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight \
  --configuration runtimeClasspath \
  --dependency kotlin-stdlib
~~~

Bash dùng `\` nối dòng; PowerShell có thể chuyển thành một dòng. Với nhiều platforms, đừng dựa vào `./gradlew build` không tham số để biết chính xác mọi target đã test — xem task graph của target-specific verification tasks.

## 25. KMP Gradle task graph và incremental build/cache

Kotlin plugin là Gradle plugin nên tận dụng task input/output tracking, configuration avoidance và build cache mechanisms. Tuy nhiên:
- Mỗi target có compiler backend/output khác nhau.
- Thay `commonMain` có thể invalidation nhiều target compilations.
- Thay platform-only source thường chỉ ảnh hưởng target đó.
- Kotlin/JS npm/yarn dependencies và Node toolchain có cache riêng; không nhầm với JVM classpath cache.
- Kotlin/Native compilation/linking chịu ảnh hưởng Xcode/host/ABI.
- KMP Gradle plugin version thay đổi có thể làm task implementation/metadata/outputs khác.
- Configuration Cache compatibility phải xem theo Gradle/Kotlin plugin versions và custom build logic.

**Không đặt chung outputs của các custom Kotlin generators cho JVM và JS trong cùng directory rồi hy vọng Gradle vẫn cacheable.** Để mỗi producer task sở hữu output riêng và nối output Provider vào consumer compilation đúng cách.

Với `--build-cache`:
~~~bash
./gradlew :shared:jvmTest --build-cache
~~~
nó chỉ có thể reuse **cacheable tasks** có inputs/implementation phù hợp. Không có bảo đảm tất cả KMP tasks đều `FROM-CACHE`. Với `--configuration-cache`:
~~~bash
./gradlew :shared:jvmTest --configuration-cache
~~~
đó là configuration-state reuse, không đồng nghĩa compilation được skip. Nên kiểm chứng Gradle/KMP compatibility khi bật trong CI.

## 26. CI cơ bản cho JVM và JS/Node targets

GitHub Actions workflow minh họa cho đúng demo `shared` + `app`, dùng Wrapper 9.7.0 đã commit:

~~~yaml
name: KMP Gradle CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Ensure Gradle Wrapper executable
        run: chmod +x ./gradlew

      - name: Run KMP JVM and Node tests
        run: |
          ./gradlew :shared:jvmTest :shared:jsNodeTest \
            --no-daemon --stacktrace

      - name: Verify Java consumer
        run: ./gradlew :app:build --no-daemon

      - name: Save JVM test reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: kmp-test-reports
          path: |
            shared/build/reports/tests/
            shared/build/test-results/
          if-no-files-found: ignore
~~~

**Đây là workflow YAML đầy đủ** cho targets không yêu cầu Android SDK/Xcode. JS Node tests có thể tải Node/npm runners lần đầu; CI phải có network/mirror nếu môi trường bị cô lập. Lựa chọn action versions phù hợp tài liệu được tra vào tháng 11/2026; production nên pin verified SHA/Actions dependency lockfile theo policy.

Không nhầm GitHub Actions runner **Ubuntu** với việc test native iOS target — muốn test iOS simulator phải có macOS/Xcode. Khi mở rộng target matrix, phân biệt:
- **Compile coverage** của các platforms/variants.
- **Executable test coverage** thực sự chạy trên host thích hợp.
- **Publishing verification**/metadata integrity.

Đừng để một Ubuntu job Java+Node PASS được mô tả là “đã test KMP tất cả platforms”.

## 27. Quy trình chọn target/source set khi bắt đầu dự án

1. Xác định platforms thật sự phải **ship** (JVM, JS, Android, iOS...); không khai báo mọi target chỉ để trông đa nền tảng.
2. Kiểm tra Kotlin KMP/Gradle/AGP/Xcode compatibility table trước khi pin versions.
3. Tạo `shared` module với Kotlin Multiplatform plugin.
4. Khai báo targets + test environments cần thiết.
5. Giữ business rules và model portable trong `commonMain`.
6. Đặt Java/Android/JS/Native APIs trong target-specific source sets.
7. Dùng default hierarchy template cho nhóm targets phù hợp.
8. Chỉ viết manual `dependsOn` hierarchy khi có lý do rõ và test source visibility.
9. Thêm multiplatform dependencies vào commonMain, platform-specific dependencies vào source set đúng.
10. Viết commonTest để kiểm tra contract trên mọi target.
11. Viết platformTest cho API/behavior đặc thù.
12. Tạo app entry modules riêng, nối project dependencies qua Gradle variant-aware model.
13. Build/test từng target ở host tương thích.
14. Nếu publish library, kiểm tra root KMP metadata cùng target artifacts.
15. Đo CI performance/Build Cache và kiểm tra artifact consistency trước release.

### Những câu hỏi thiết kế quan trọng

- Bạn chia sẻ **logic** hay cả **UI**? KMP logic không đòi Compose.
- API nào thực sự khả dụng trên tất cả targets?
- Plugin và dependencies có hỗ trợ Kotlin version target không?
- Cần JVM interop với Java 17? Có nên đặt Java consumer riêng không?
- Có CI runner để test iOS/native không?
- Cần artifact publish cho bên ngoài hay chỉ project dependency trong repo?
- Có một module shared đủ không, hay phải tách `sharedLogic`/`sharedUI`/server?

## 28. Bài tập thực hành

### Bài A — Đọc target và source set graph

Trong demo, trả lời:
- Kotlin shared source nằm ở đâu?
- JVM actual implementation nằm ở đâu?
- JS actual implementation nằm ở đâu?
- Khi gọi `:app:run`, Gradle chọn variant nào của `:shared`?

**Đáp án hướng dẫn:** `commonMain` chứa `greet` và expected declaration; `jvmMain` actual là JVM, `jsMain` actual là JS; Java `app` cần JVM variant.

### Bài B — Thay đổi common code và quan sát tác động

Đổi dòng return trong `Greeting.kt` thành:

~~~kotlin
return "Welcome, " + name + " from " + platformName() + "!"
~~~

Chạy `:shared:jvmTest :shared:jsNodeTest`. Shared test `greetUsesThePlatformName` sẽ FAIL do expected vẫn là `Hello`. Sửa expected trong `commonTest` cho đúng nghiệp vụ rồi chạy lại. Bài tập cho thấy **một thay đổi commonMain ảnh hưởng cả JVM và JS**.

Không merge một thay đổi khiến tests fail. Không dùng `-x test` để “chữa” việc common API thay đổi.

### Bài C — Xóa JS actual để tái hiện compiler error

Tạm xóa/đổi tên file `shared/src/jsMain/kotlin/demo/shared/PlatformJs.kt` trên branch thực hành, rồi chạy:

~~~bash
./gradlew :shared:jsNodeTest
~~~

JS compilation cần actual cho `expect fun platformName()`, nên sẽ báo missing actual hoặc compiler mismatch phù hợp compiler version. Khôi phục file và chạy lại. JVM tests có thể vẫn pass vì JVM actual không thay đổi.

### Bài D — Thử Java interop

Trong `App.java` đổi:

~~~java
System.out.println(GreetingKt.greet("Java"));
~~~

thành:

~~~java
System.out.println(GreetingKt.greet("Gradle"));
~~~

Chạy `./gradlew :app:run --quiet`. **Stdout Java mới chính xác**:

~~~text
Hello, Gradle from JVM!
~~~

Giải thích vì sao dù KMP module có JS target, Java app vẫn chọn JVM variant và không thấy `platformName()=="JS"`.

### Bài E — Đặt dependency sai source set

Thử thêm `java.time.LocalDate` import vào `commonMain` hoặc một JVM-only dependency rồi dùng JVM API trong common code. Chạy `:shared:jsNodeTest` và quan sát compile error. Sửa bằng cách chuyển Java API usage sang `jvmMain`; nếu common cần kết quả, thêm `expect/actual` hoặc interface.

### Bài F — Dùng default hierarchy template

Trên một **branch/project riêng có Apple toolchain phù hợp**, thêm `iosArm64()` và `iosSimulatorArm64()`, xem source set `iosMain` được tạo ra và IDE import model. **Không bắt buộc build/run iOS simulator trên Windows/Linux**; phân biệt Gradle model configuration với native executable test.

## 29. Câu hỏi tự kiểm tra

**1. KMP plugin ID đầy đủ là gì?** `org.jetbrains.kotlin.multiplatform`; Kotlin DSL alias `kotlin("multiplatform")`.

**2. `jvm()` tạo ra điều gì?** JVM target và compilations/tasks/variants tương ứng, không chỉ một folder.

**3. `commonMain` có thể import `java.time.LocalDate` trong JVM+JS module không?** Không; JS không có JVM Java API.

**4. `commonMain` là một artifact JVM duy nhất có thể gọi từ Java không?** Không; Java consumer cần JVM variant biên dịch từ common+jvmMain.

**5. `jvmMain` có truy cập commonMain code không?** Có theo source-set hierarchy; ngược lại commonMain không được dùng JVM-only APIs.

**6. `dependsOn` giữa source sets có tương đương `tasks.dependsOn` không?** Không; nó mô tả source-set hierarchy/code visibility, không phải task graph order.

**7. Vì sao default hierarchy template hữu ích?** Tự tạo intermediate source sets phù hợp targets, tránh copy/paste manual edges.

**8. Manual `dependsOn` có thể gây warning gì?** Có thể chặn default template; cần thiết kế hierarchy có chủ đích.

**9. `expect/actual` dùng để làm gì?** Mở common declaration contract và cung cấp platform-specific implementation cho từng target.

**10. Vì sao Java `App.java` import `GreetingKt`?** Top-level `fun greet` trong Kotlin file `Greeting.kt` có JVM static facade tên `GreetingKt` theo naming convention.

**11. `commonTest` với `kotlin("test")` chạy bao nhiêu lần?** Theo target test runs được thực thi; demo JVM+JS chạy shared tests ở cả hai môi trường.

**12. KMP JVM `kotlin("test")` mặc định dùng test framework nào?** Theo Kotlin docs, JUnit 4 variant; có thể chọn JUnit5 với configuration phù hợp.

**13. Node.js JS tests dùng framework gì?** Kotlin/JS Node target mặc định hỗ trợ Mocha.

**14. Có nên đưa JUnit Jupiter vào commonTest của module JS+JVM không?** Không; JUnit chỉ dành JVM.

**15. Gradle :app dependency nhận JVM hay JS artifact của :shared?** JVM variant, vì Java application cần JVM-compatible library.

**16. `js { nodejs() }` và `wasmJs { nodejs() }` có tương đương không?** Không; compiler backend/artifact khác.

**17. Vì sao KMP không thay Android Gradle Plugin?** Android SDK/app/library tooling và target integration do Android Gradle plugin đảm nhiệm.

**18. AGP9 KMP library plugin ID mới là gì?** `com.android.kotlin.multiplatform.library`; cấu hình theo Android-KMP docs.

**19. iOS simulator tests chạy được trên Linux chỉ vì khai báo `iosSimulatorArm64()` không?** Không; cần host/Xcode/runtime phù hợp.

**20. Vì sao publish KMP root metadata chưa đủ?** Consumer còn cần platform-specific target artifacts được metadata tham chiếu.

**21. Nếu chỉ cần Kotlin/JVM server thì có cần KMP không?** Không bắt buộc; `org.jetbrains.kotlin.jvm` đơn giản hơn nếu không có nhu cầu share multi-target.

**22. Tại sao nên kiểm tra Gradle/Kotlin compatibility trước?** Plugin/compiler/Gradle/AGP/Xcode có dải hỗ trợ cụ thể; dùng “latest mọi thứ” có thể sai.

**23. Kotlin 2.4.21 support Gradle tới đâu theo guide hiện tại?** Dải được công bố tới Gradle **9.7.0** ở thời điểm biên soạn; không tự suy hỗ trợ Gradle9.9.

**24. `:app:run` PASS có chứng minh JS tests pass không?** Không; phải chạy `:shared:jsNodeTest`/`:shared:check` theo scope phù hợp.

## 30. Checklist chất lượng cho module Kotlin Multiplatform

- [ ] Plugin đúng `org.jetbrains.kotlin.multiplatform` và version đã pin.
- [ ] KMP plugin/Gradle Wrapper/JDK nằm trong compatibility range được công bố.
- [ ] Android KMP AGP plugin và Xcode nếu dùng đã được kiểm tra theo target host.
- [ ] Chỉ khai báo targets thực sự phải build/test/publish.
- [ ] `commonMain` chỉ dùng common-compatible APIs.
- [ ] Platform-specific APIs/dependencies đặt ở đúng `jvmMain`, `jsMain`, `iosMain`...
- [ ] Không nhầm KMP source-set `dependsOn` với task `dependsOn`.
- [ ] Ưu tiên default hierarchy template, chỉ manual edges khi có lý do.
- [ ] Expected declarations có actual implementations ở mọi target cần.
- [ ] Dùng interface/DI thay vì expect/actual classes nếu đủ.
- [ ] `commonTest` có `kotlin("test")` cho shared assertions.
- [ ] JVM/JS/native tests có test runner/host/toolchain tương ứng.
- [ ] JS Node tests không bị nhầm browser tests; Node/npm downloads có policy.
- [ ] Java consumer sử dụng Gradle project dependency/variant-aware resolution.
- [ ] Java interop imports/API signature đã được compile test ở JVM.
- [ ] Không ghép Java plugin/legacy `withJava` vào KMP module một cách máy móc.
- [ ] KMP root metadata cùng target artifacts được publish đồng bộ nếu phát hành library.
- [ ] CI test matrix phản ánh targets đã thật sự kiểm chứng, không overclaim.
- [ ] Build Cache/Configuration Cache được bật khi plugin/build logic compatible.
- [ ] Codegen tasks không ghi đè output roots giữa các targets.
- [ ] IDE đã import/sync Gradle model sau khi đổi targets/source sets.
- [ ] Kotlin plugin version catalog đồng bộ và included builds có resolution riêng khi cần.
- [ ] Đọc Kotlin docs deprecations/migration guide trước khi nâng version.
- [ ] Trước release, verify artifacts có JVM, JS/native variants đúng consumer requirements.

## 31. Tài liệu chính thức

- [Kotlin — Multiplatform Gradle DSL Reference](https://kotlinlang.org/docs/multiplatform/multiplatform-dsl-reference.html): plugin ID/version, targets, sourceSets, compilations, compiler options, dependencies.
- [Kotlin — KMP Compatibility Guide](https://kotlinlang.org/docs/multiplatform/multiplatform-compatibility-guide.html): Kotlin–Gradle–AGP–Xcode matrix và migration/deprecation.
- [Kotlin — Kotlin Releases](https://kotlinlang.org/docs/releases.html): Kotlin/KMP plugin 2.4.21 ở thời điểm 11/2026.
- [Kotlin — Basics of KMP Project Structure](https://kotlinlang.org/docs/multiplatform/multiplatform-discover-project.html): target/source-set graph, common và platform declarations.
- [Kotlin — Source Set Hierarchy](https://kotlinlang.org/docs/multiplatform/multiplatform-hierarchy.html): default template, manual dependsOn, intermediate sets.
- [Kotlin — Expected and Actual Declarations](https://kotlinlang.org/docs/multiplatform/multiplatform-expect-actual.html): expect/actual implementation rules và alternatives.
- [Kotlin — Adding KMP Dependencies](https://kotlinlang.org/docs/multiplatform/multiplatform-add-dependencies.html): common/platform dependencies và variants.
- [Kotlin — Configure a Gradle Project](https://kotlinlang.org/docs/gradle-configure-project.html): JVM toolchain, kotlin.test JVM test variants.
- [Kotlin — JS Project Setup](https://kotlinlang.org/docs/js-project-setup.html): JS Node/browser targets và test runners/npm.
- [Kotlin — Run Kotlin/JS](https://kotlinlang.org/docs/running-kotlin-js.html): `jsNodeDevelopmentRun` for executable Node apps.
- [Kotlin — Run Tests in Kotlin/JS](https://kotlinlang.org/docs/js-running-tests.html): Mocha/Browser testing and dependencies.
- [Kotlin — Publishing KMP Libraries](https://kotlinlang.org/docs/multiplatform/multiplatform-publish-lib-setup.html): root KotlinMultiplatform publication and target artifacts.
- [Kotlin — AGP9 Migration](https://kotlinlang.org/docs/multiplatform/multiplatform-project-agp-9-migration.html): Android-KMP library plugin and legacy migration.
- [Kotlin — Recommended KMP Project Structure](https://kotlinlang.org/docs/multiplatform/multiplatform-project-recommended-structure.html): shared modules and app entry points.
- [Gradle — Variant-Aware Resolution](https://docs.gradle.org/current/userguide/variant_aware_resolution.html): Gradle attributes/variants and library consumption.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html): `include` and project dependency organization.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): Java17 compiler selection, daemon vs task toolchains.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): version pinning and wrapper generation.
