# Truyền thuộc tính bằng -P, -D và biến môi trường trong Gradle với Spring Boot

## 1. Ba cơ chế, ba phạm vi tác động

Khi chạy Gradle để build hoặc chạy ứng dụng Spring Boot, người lập trình thường gặp ba dạng:

```bash
./gradlew build -PbuildMode=ci
./gradlew build -Ddemo.trace=on
APP_ENV=staging ./gradlew build
```

Cả ba đều “truyền một giá trị”, nhưng **không cùng loại thuộc tính, không cùng nơi đọc và không tự đến được mọi tiến trình Java**. Để dùng đúng, hãy hỏi: **giá trị điều khiển Gradle build logic, JVM đang chạy Gradle, hay ứng dụng Spring Boot được Gradle khởi chạy?**

| Cơ chế | Nơi giá trị được thiết lập | Cách build Gradle nên đọc | Dùng chủ yếu cho |
| --- | --- | --- | --- |
| `-Pkey=value` | **Gradle project property** | `providers.gradleProperty("key")` | Chọn target, build variant, URL không nhạy cảm, cờ của custom task |
| `-Dkey=value` | **Java system property của Gradle JVM** | `providers.systemProperty("key")` | JVM/Gradle tooling, proxy và các công cụ đọc system property trong build process |
| `KEY=value` trong môi trường | **OS environment variable** của tiến trình gọi Gradle | `providers.environmentVariable("KEY")` | CI metadata, endpoint theo môi trường, credential qua secret injection |
| `-Dorg.gradle.project.key=value` | Cú pháp **system property đặc biệt** được Gradle chuyển thành **project property** | `providers.gradleProperty("key")` | Truyền project property bằng kênh `-D` |
| `ORG_GRADLE_PROJECT_key=value` | Biến môi trường có prefix đặc biệt; Gradle chuyển thành **project property** | `providers.gradleProperty("key")` | Project property/secret được CI inject |
| `--args='--server.port=9090'` với `bootRun` | **Command-line args của ứng dụng Spring Boot** | Spring `Environment`/binding | Cấu hình Spring Boot tại runtime |

**Điểm mấu chốt:** `-PserverPort=9090` không tự biến thành `server.port=9090` trong Spring Boot. `-Dserver.port=9090` trên **lệnh Gradle** đặt system property cho Gradle JVM; `bootRun` thường tạo **JVM khác**, nên cũng không mặc nhiên nhận property đó. Muốn ứng dụng thấy giá trị, phải chuyển qua `bootRun --args`, môi trường hệ điều hành, cấu hình `BootRun.systemProperty(...)` hoặc chạy executable JAR với tham số Java/Spring tương ứng.

## 2. `-P`: project property của Gradle

### 2.1. Cú pháp và cách đọc

Ví dụ:

```bash
./gradlew build -PbuildMode=ci
./gradlew :service:bootJar -PtargetEnv=staging
```

Gradle đặt `buildMode=ci` / `targetEnv=staging` trong không gian **project properties**. Trong build script Kotlin DSL:

```kotlin
val buildMode = providers.gradleProperty("buildMode").orElse("local")

tasks.register("showBuildMode") {
    doLast {
        println("buildMode=" + buildMode.get())
    }
}
```

Nếu chạy `./gradlew -q showBuildMode -PbuildMode=ci`, dòng được in ra là:

```text
buildMode=ci
```

Nếu không có `-PbuildMode` và không có nguồn giá trị nào khác, kết quả là `buildMode=local`. Đó là **giá trị mặc định do script tự định nghĩa**, không phải Gradle tự đặt.

Ưu tiên `providers.gradleProperty("key")` cho dữ liệu build vì trả về `Provider<String>`: có thể dùng `orElse`, `map`, nối với input của task và được Gradle theo dõi khi dùng đúng cách. Các API cũ như `project.findProperty("key")` vẫn dùng được, nhưng chúng tìm trong mô hình project động và có thể bao gồm extra properties, extensions hay task names; `providers.gradleProperty` tập trung vào **Gradle properties từ môi trường cấu hình build**, dễ lý giải và phù hợp configuration cache.

### 2.2. Những cách khác cũng tạo project property

Bốn kênh điển hình:

```bash
./gradlew showBuildMode -PbuildMode=ci
./gradlew showBuildMode -Dorg.gradle.project.buildMode=ci
ORG_GRADLE_PROJECT_buildMode=ci ./gradlew showBuildMode
```

Hoặc ở `gradle.properties`:

```properties
buildMode=ci
```

Cả bốn có thể được đọc bằng `providers.gradleProperty("buildMode")`. Tuy nhiên **`-DbuildMode=ci` không tương đương `-PbuildMode=ci`**: thiếu prefix `org.gradle.project.` thì đây chỉ là system property; `providers.gradleProperty("buildMode")` sẽ không lấy giá trị từ `-DbuildMode`.

**Cú pháp đặc biệt cần nhớ:**
- `-PbuildMode=ci` → project property `buildMode`.
- `-Dorg.gradle.project.buildMode=ci` → cũng tạo project property `buildMode`.
- `-DbuildMode=ci` → system property `buildMode` của Gradle.
- `ORG_GRADLE_PROJECT_buildMode=ci` → biến môi trường được Gradle diễn giải thành project property `buildMode`.
- `BUILD_MODE=ci` → biến môi trường bình thường, đọc bằng `providers.environmentVariable("BUILD_MODE")`; không tự tạo project property `buildMode`.

### 2.3. Đừng nhầm project property với hệ thống property của Spring Boot

Khi build bằng `-Pprofile=dev`, Spring Boot không tự thấy profile `dev`. `-P` hữu ích nếu **build logic** cần chọn artifact/version/task, hoặc cần cấu hình task `bootRun` để chuyển giá trị tới JVM ứng dụng. Ngược lại, nếu chỉ muốn chạy Spring Boot với profile `dev`, lệnh ngắn gọn thường là:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Lệnh này gửi tham số **đúng vào ứng dụng** thông qua `bootRun`, không đòi xây thêm mapping `-P`. Khi cần triển khai tách biệt build/runtime, càng nên giữ secret/cấu hình chạy riêng khỏi bước đóng gói.

## 3. `-D`: Java system property của Gradle JVM

### 3.1. `-D` trên lệnh Gradle tác động đến đâu?

```bash
./gradlew build -Ddemo.trace=enabled
```

Trong `build.gradle.kts`:

```kotlin
val traceMode = providers.systemProperty("demo.trace").orElse("disabled")

tasks.register("showTrace") {
    doLast {
        println("demo.trace=" + traceMode.get())
    }
}
```

Chạy `./gradlew -q showTrace -Ddemo.trace=enabled` sẽ in:

```text
demo.trace=enabled
```

System property này thuộc **JVM thực thi Gradle build**. Lệnh `-Ddemo.trace=enabled` không tự làm mọi JVM khác do Gradle tạo (ví dụ `Test`, `JavaExec`, `bootRun`) nhận cùng property. Cần cấu hình forwarding vào task cụ thể; phần 8 minh họa.

Dùng `-D` cho các tùy chọn JVM/Gradle và plugin thực sự đọc system property, chẳng hạn một số setting mạng/proxy, debug build hoặc cấu hình Gradle `org.gradle.*`. Không mặc định mọi key `-D` là khóa cấu hình ứng dụng Spring Boot.

### 3.2. `-Dorg.gradle.project.*` là ngoại lệ về project property

```bash
./gradlew -q showBuildMode -Dorg.gradle.project.buildMode=preprod
```

Gradle hỗ trợ prefix `org.gradle.project.` để tạo **project property**. Trong ví dụ này, `providers.gradleProperty("buildMode")` trả về `preprod`. Đây là ngoại lệ có chủ đích, không phải mọi system property đều được chuyển thành project property.

Có thể cấu hình từ `gradle.properties` theo hai kiểu:

```properties
# Project property trực tiếp
buildMode=local

# Java system property của Gradle JVM
systemProp.demo.trace=enabled

# Cũng là project property vì prefix đặc biệt
systemProp.org.gradle.project.deployTier=preprod
```

Không cần khai báo cả ba kênh cho cùng một tên. Chọn một giá trị mặc định rõ ràng, cho phép CLI hoặc CI override, và kiểm tra precedence khi có xung đột.

### 3.3. Cấu hình Gradle `org.gradle.*` khác project property

Một số giá trị làm thay đổi bản thân Gradle:

```properties
# gradle.properties
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
```

Hoặc, đối với những Gradle property hỗ trợ override, dùng `-Dorg.gradle.caching=true` / `-Dorg.gradle.java.home=/path/to/jdk`. Chúng **cấu hình Gradle**, không tự đưa thuộc tính đến Spring Boot application. `org.gradle.jvmargs` ảnh hưởng đến Gradle daemon JVM, không phải tự động cấp heap cho `bootRun` hoặc executable JAR của ứng dụng. Muốn cấu hình heap cho `bootRun`, cấu hình JavaExec/BootRun JVM args; với JAR độc lập dùng `java -Xmx... -jar app.jar`.

## 4. Biến môi trường: hai kiểu hoàn toàn khác nhau

### 4.1. Biến môi trường OS thông thường

Ví dụ trên Linux/macOS:

```bash
export APP_ENV=staging
./gradlew -q showInputs
```

Trong Gradle Kotlin DSL:

```kotlin
val appEnv = providers.environmentVariable("APP_ENV").orElse("local")

tasks.register("showAppEnvironment") {
    doLast {
        println("APP_ENV=" + appEnv.get())
    }
}
```

`providers.environmentVariable("APP_ENV")` trả về giá trị environment variable truyền cho tiến trình Gradle; nếu không tồn tại thì `orElse("local")` cung cấp default. `System.getenv("APP_ENV")` vẫn có thể đọc được, nhưng API Provider thường phù hợp hơn với việc theo dõi input cho configuration cache và task state.

Lưu ý **tên biến môi trường thường phân biệt chữ hoa/chữ thường trên Linux**. `APP_ENV` khác `app_env`; trong CI cần thống nhất chính tả, nhất là khi chuyển từ Windows sang Linux container.

### 4.2. Biến môi trường đặc biệt `ORG_GRADLE_PROJECT_*`

Gradle đọc tên biến theo quy ước:

```bash
export ORG_GRADLE_PROJECT_buildMode=ci
./gradlew -q showBuildMode
```

Task `showBuildMode` đọc qua `providers.gradleProperty("buildMode")` và in `buildMode=ci` nếu không bị nguồn ưu tiên cao hơn ghi đè. Đây là cách phổ biến để CI inject **project property** mà không cần đặt trực tiếp `-P...` vào command line.

Khác nhau:

| Biến môi trường | API thường đọc | Ý nghĩa |
| --- | --- | --- |
| `APP_ENV` | `providers.environmentVariable("APP_ENV")` | Biến OS bình thường, có thể được process con kế thừa |
| `ORG_GRADLE_PROJECT_buildMode` | `providers.gradleProperty("buildMode")` | Gradle chuyển thành project property |
| `SPRING_PROFILES_ACTIVE` | Spring Boot `Environment` | Chọn active Spring profile ở runtime khi biến được truyền đến ứng dụng |
| `SERVER_PORT` | Spring Boot `Environment` | Giá trị cấu hình `server.port` ở runtime |
| `JAVA_HOME` | Gradle/JVM bootstrap | Chọn JDK dùng để khởi chạy Gradle, trừ khi có cơ chế chỉ định JDK riêng |
| `GRADLE_USER_HOME` | Gradle | Đổi vị trí cấu hình/cache Gradle user home |

**`ORG_GRADLE_PROJECT_*` không phải magic Spring Boot variable.** Ví dụ `ORG_GRADLE_PROJECT_springProfile=dev` được Gradle chuyển thành project property `springProfile`; Spring Boot chỉ nhận profile nếu task `bootRun` được cấu hình forwarding.

### 4.3. Khai báo biến trong các shell

Linux/macOS:

```bash
APP_ENV=staging ./gradlew -q showInputs
ORG_GRADLE_PROJECT_buildMode=ci ./gradlew -q showInputs
```

PowerShell:

```powershell
$env:APP_ENV = "staging"
$env:ORG_GRADLE_PROJECT_buildMode = "ci"
.\gradlew.bat -q showInputs
```

Trong PowerShell, biến được đặt trong session hiện tại và tồn tại đến khi thay đổi/xóa hoặc kết thúc session; với CI nên dùng cơ chế biến môi trường ở cấp job/step. Nếu dùng Windows Command Prompt:

```bat
set APP_ENV=staging
set ORG_GRADLE_PROJECT_buildMode=ci
gradlew.bat -q showInputs
```

`./gradlew` là script wrapper trên Unix; trên Windows dùng `gradlew.bat`. Các ví dụ đầu ra bên dưới giả sử Gradle Wrapper tương thích đã tồn tại; nếu chưa có wrapper, tạo bằng `gradle wrapper` từ Gradle đã cài, hoặc dùng lệnh `gradle` thay cho wrapper.

## 5. Precedence: khi cùng một khóa được đặt ở nhiều nơi

Không có **một** bảng ưu tiên dùng chung cho Gradle project property, JVM system property, biến môi trường OS và Spring Boot configuration. Chúng thuộc những không gian khác nhau. Cần xét **từng khóa trong từng không gian**.

### 5.1. Ưu tiên đối với Gradle project property

Với một project property đọc qua `providers.gradleProperty("buildMode")`, các nguồn phổ biến có thứ tự ưu tiên từ cao xuống thấp:

1. `-PbuildMode=...` trên CLI.
2. `-Dorg.gradle.project.buildMode=...` (hoặc system property với prefix tương đương).
3. `ORG_GRADLE_PROJECT_buildMode=...` từ môi trường.
4. Giá trị trong `gradle.properties` được Gradle nạp (user home/root/install theo thứ tự riêng).

Ví dụ `gradle.properties` đặt `buildMode=local`, môi trường đặt `ORG_GRADLE_PROJECT_buildMode=ci`, nhưng lệnh có `-PbuildMode=manual` thì task đọc `manual`.

Thứ tự cụ thể của **các file** `gradle.properties`: user-level `GRADLE_USER_HOME/gradle.properties` thường ưu tiên hơn file ở build root, và file Gradle installation có ưu tiên thấp hơn. Việc một API đọc cả file `gradle.properties` trong thư mục subproject hay giá trị extra property được gán động còn tùy API; `providers.gradleProperty` chỉ tập trung vào **build-level Gradle properties**, khác `Project.findProperty`. Không dựa vào lookup động ở project cha để tạo contract build mới.

### 5.2. Ưu tiên đối với JVM system property của Gradle

Với `providers.systemProperty("demo.trace")`, giá trị `-Ddemo.trace=on` trên CLI ưu tiên hơn `systemProp.demo.trace=off` trong `gradle.properties`. Đây là **system property** và không có nghĩa biến môi trường `DEMO_TRACE` sẽ tự ghi đè nó.

Lưu ý multi-project Gradle: những dòng `systemProp.*` trong `gradle.properties` của **subproject** không được dùng như nguồn system properties như root project; đặt chúng ở root hoặc Gradle user home. Nếu cần cấu hình khác nhau cho từng module, dùng project properties/task properties thay vì mong mỗi subproject có JVM Gradle riêng.

### 5.3. Spring Boot có thứ tự riêng khi ứng dụng đã chạy

Khi nhiều nguồn cùng đặt `demo.message` cho **Spring Boot application**, các nguồn thông dụng thường được ưu tiên theo hướng:

```text
Application command-line args: --demo.message=from-args
      (cao hơn)
Java system property của JVM ứng dụng: -Ddemo.message=from-jvm
      (cao hơn)
OS environment variable: DEMO_MESSAGE=from-env
      (cao hơn)
application.properties / application.yml: demo.message=from-file
```

Đây là so sánh **những nguồn quen thuộc trong cùng tình huống**, không phải danh sách tuyệt đối tất cả PropertySources: test properties, Devtools, `SPRING_APPLICATION_JSON` và các cấu hình đặc biệt có thể thay đổi kết quả. Luôn phân biệt: `-Ddemo.message` trên **lệnh `java`** khác với `-Ddemo.message` trên **lệnh `gradlew`** nếu không forward.

## 6. Ví dụ runnable độc lập: thử cả `-P`, `-D` và environment variable

Tạo thư mục trống và hai file. Ví dụ chỉ cần Gradle/JDK tương thích; **không cần Spring Boot plugin** để thấy các nguồn cấu hình.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "gradle-property-lab"
```

**`build.gradle.kts`:**

```kotlin
val mode = providers.gradleProperty("buildMode").orElse("local")
val trace = providers.systemProperty("demo.trace").orElse("disabled")
val environment = providers.environmentVariable("APP_ENV").orElse("unset")

tasks.register("showInputs") {
    group = "help"
    description = "In 3 loại cấu hình không nhạy cảm"
    doLast {
        println("buildMode=" + mode.get())
        println("demo.trace=" + trace.get())
        println("APP_ENV=" + environment.get())
    }
}
```

Chạy trên Linux/macOS:

```bash
APP_ENV=staging ./gradlew -q showInputs -PbuildMode=ci -Ddemo.trace=enabled
```

**Stdout chính xác của các dòng do task in:**

```text
buildMode=ci
demo.trace=enabled
APP_ENV=staging
```

Trong project mới không có các biến/property đã đặt, chạy `./gradlew -q showInputs` cho output:

```text
buildMode=local
demo.trace=disabled
APP_ENV=unset
```

Dòng thứ hai chỉ đúng nếu `APP_ENV` thực sự vắng mặt; giá trị hiện có từ shell/CI hoặc `gradle.properties` có thể làm output khác. `-q` tắt log Gradle thông thường, nhưng nếu xảy ra lỗi hoặc Gradle version có warning, terminal vẫn có thể xuất hiện thông báo ngoài ba dòng trên.

Để kiểm tra dạng `-D` đặc biệt:

```bash
./gradlew -q showInputs -Dorg.gradle.project.buildMode=preprod
```

Với các nguồn khác vắng mặt, output:

```text
buildMode=preprod
demo.trace=disabled
APP_ENV=unset
```

Nếu đổi thành `-DbuildMode=preprod`, dòng `buildMode` trở về `local` vì đó là một system property không được script đọc qua `providers.gradleProperty`. Muốn kiểm tra, thêm `providers.systemProperty("buildMode")` trong task.

**Tương đương Groovy DSL** (thay `build.gradle.kts` bằng `build.gradle` và dùng `settings.gradle` tương ứng):

```groovy
def mode = providers.gradleProperty('buildMode').orElse('local')
def trace = providers.systemProperty('demo.trace').orElse('disabled')
def environment = providers.environmentVariable('APP_ENV').orElse('unset')

tasks.register('showInputs') {
    group = 'help'
    doLast {
        println 'buildMode=' + mode.get()
        println 'demo.trace=' + trace.get()
        println 'APP_ENV=' + environment.get()
    }
}
```

Chỉ dùng **một** DSL cho file build trong một lần thử, không dán đồng thời cả hai đoạn.

## 7. Tách Gradle build JVM với ứng dụng Spring Boot runtime JVM

Cấu trúc tiến trình thường là:

```text
Shell / CI
   |
   +-- Gradle wrapper/client -> Gradle daemon (JVM chạy build logic)
                                    |
                                    +-- compileJava / test (có thể dùng worker/test JVM)
                                    |
                                    +-- bootRun -> JVM ứng dụng Spring Boot
                                    |
                                    +-- bootJar -> file executable JAR (chưa chạy app)
                                                     |
                                                     +-- java -jar app.jar (JVM khác, ở runtime)
```

`./gradlew bootRun` thực thi task `BootRun` thuộc loại `JavaExec` và khởi động ứng dụng trong JVM riêng. `-P`, system property của Gradle daemon và `org.gradle.jvmargs` **không tự động trở thành** cấu hình ứng dụng. Trái lại, những environment variables bình thường của OS thường được tiến trình con kế thừa trừ khi task/CI tùy chỉnh environment.

Có ba cách rõ ràng để truyền cấu hình **vào ứng dụng Spring Boot** khi dùng `bootRun`:

1. Truyền application args qua `bootRun --args='--spring.profiles.active=dev --server.port=9090'`.
2. Cung cấp môi trường runtime được Spring Boot nhận, như `SPRING_PROFILES_ACTIVE=dev` hoặc `SERVER_PORT=9090`.
3. Cấu hình `tasks.named<BootRun>("bootRun") { systemProperty(...); environment(...) }` để map giá trị Gradle sang JVM ứng dụng khi thực sự cần.

Khi đóng gói thành JAR, **mục 1 và 2 thuộc lúc chạy JAR**, không thuộc lúc `bootJar` tạo artifact. `-Penv=prod` không có ý nghĩa Spring Boot mặc định khi chỉ chạy `bootJar`.

## 8. Ví dụ runnable Spring Boot: truyền cấu hình từ Gradle đến ứng dụng

Ví dụ dùng **Spring Boot 3.5.0**, Java **17+**, cố định version để mã và lệnh có điểm tham chiếu; đây **không phải** tuyên bố bản mới nhất. Cần mạng để Gradle tải plugin/dependency. Nếu dự án có Gradle Wrapper, sử dụng wrapper của repo; ví dụ dưới đây có thể dùng Gradle được cài tương thích nếu chưa tạo wrapper.

Cấu trúc:

```text
spring-property-demo/
├── settings.gradle.kts
├── build.gradle.kts
└── src/main/java/com/example/propertydemo/PropertyDemoApplication.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "spring-property-demo"
```

**`build.gradle.kts`:**

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.1.0"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
}

tasks.named<BootRun>("bootRun") {
    // Chỉ forward khi có -PdemoMessage hoặc nguồn project property tương đương.
    providers.gradleProperty("demoMessage").orNull?.let { value ->
        systemProperty("demo.message", value)
    }
}
```

**`src/main/java/com/example/propertydemo/PropertyDemoApplication.java`:**

```java
package com.example.propertydemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PropertyDemoApplication {
    private final String message;

    public PropertyDemoApplication(
            @Value("${demo.message:from-default}") String message) {
        this.message = message;
    }

    @GetMapping("/message")
    public String message() {
        return message;
    }

    public static void main(String[] args) {
        SpringApplication.run(PropertyDemoApplication.class, args);
    }
}
```

Trong Java, `@Value("${demo.message:from-default}")` dùng **Spring property placeholder**. Nếu `demo.message` không được cấp từ bất kỳ nguồn nào, ứng dụng trả về `from-default`. Nếu được cấp, Spring `Environment` xác định giá trị theo thứ tự ưu tiên runtime.

### 8.1. Dùng `--args`: chuyển trực tiếp application arguments

```bash
./gradlew bootRun --args='--demo.message=from-args'
```

Mở terminal khác:

```bash
curl -fsS http://localhost:8080/message
```

**Response body chính xác:** `from-args` (không nhất thiết có newline). Lệnh curl giả định server đang chạy thành công ở cổng 8080 và cổng chưa bị ứng dụng khác chiếm. Dừng server bằng Ctrl+C.

Thay bằng `--args='--server.port=9090 --demo.message=from-args'` thì endpoint tương ứng chuyển sang `http://localhost:9090/message`. Đây là cách trực tiếp để gửi arguments cho Spring Boot, không cần `-P` hay `-D`.

### 8.2. Dùng `-P` rồi forward vào JVM ứng dụng

```bash
./gradlew bootRun -PdemoMessage=from-project
```

Vì `build.gradle.kts` đã có `providers.gradleProperty("demoMessage").orNull?.let { systemProperty(...) }`, Gradle đọc project property và **cấu hình task bootRun** đặt Java system property `demo.message=from-project` cho JVM ứng dụng.

Gọi:

```bash
curl -fsS http://localhost:8080/message
```

**Response body:** `from-project`.

Nếu **bỏ** đoạn mapping trong `tasks.named<BootRun>`, lệnh `-PdemoMessage=from-project` **không tự thay đổi** Spring Boot property `demo.message`. Đây là điểm thường gây nhầm lẫn nhất khi điều khiển Spring Boot bằng Gradle.

### 8.3. `-D` trên Gradle không tự đi vào JVM ứng dụng

```bash
./gradlew bootRun -Ddemo.message=from-gradle
```

Với build script mẫu **không có** mapping từ `providers.systemProperty("demo.message")`, giá trị `from-gradle` chỉ nằm trong Gradle build JVM. Nếu không có nguồn cấu hình khác, endpoint vẫn trả `from-default`.

Nếu thật sự muốn map `-D` của Gradle sang JVM Spring Boot, thêm **bên trong block `tasks.named<BootRun>("bootRun")`**:

```kotlin
providers.systemProperty("demo.message").orNull?.let { value ->
    systemProperty("demo.message", value)
}
```

Đoạn này là **bổ sung tùy chọn** vào block hiện có. Chỉ dùng khi có lý do cụ thể; thường `--args` hoặc environment là cách dễ hiểu hơn. Nếu cùng lúc có cả `demoMessage` project property và `demo.message` system property, cần định nghĩa rõ nguồn nào được ưu tiên trong build logic, vì cả hai đoạn cùng gọi `systemProperty` có thể ghi đè lẫn nhau theo thứ tự cấu hình.

### 8.4. Dùng biến môi trường Spring Boot trực tiếp

```bash
DEMO_MESSAGE=from-env ./gradlew bootRun
```

Nếu **không** truyền `-PdemoMessage` và không có system property khác được forward cho `demo.message`, JVM ứng dụng kế thừa `DEMO_MESSAGE`. Spring Boot hỗ trợ relaxed binding cho tên environment variable như `DEMO_MESSAGE` tương ứng với `demo.message`. Endpoint trả `from-env`.

Có thể dùng biến môi trường chuẩn:

```bash
SPRING_PROFILES_ACTIVE=dev SERVER_PORT=9090 ./gradlew bootRun
```

Ứng dụng chạy trên cổng 9090 và profile `dev` được kích hoạt, nếu không có cấu hình ưu tiên cao hơn ghi đè. Đừng nhầm với `ORG_GRADLE_PROJECT_demoMessage=from-env`: biến đó cấp **project property** cho Gradle; trong build script mẫu nó cũng có thể đến ứng dụng **nhờ mapping đã viết**, không phải Spring Boot tự hiểu prefix `ORG_GRADLE_PROJECT_`.

### 8.5. Sau khi build executable JAR: runtime có đường truyền riêng

Đóng gói:

```bash
./gradlew clean bootJar
```

Với project name/version của ví dụ, artifact thường là `build/libs/spring-property-demo-0.1.0.jar`. Kiểm tra tên file thật trong `build/libs` nếu build được tùy chỉnh.

Ba cách chạy:

```bash
# Spring Boot application arguments
java -jar build/libs/spring-property-demo-0.1.0.jar --demo.message=jar-args

# Java system property của chính JVM ứng dụng: -D PHẢI trước -jar
java -Ddemo.message=jar-jvm -jar build/libs/spring-property-demo-0.1.0.jar

# Environment variable của tiến trình Java
DEMO_MESSAGE=jar-env java -jar build/libs/spring-property-demo-0.1.0.jar
```

Chạy từng lệnh riêng, dừng tiến trình cũ trước khi mở lệnh tiếp theo. `curl http://localhost:8080/message` trả lần lượt `jar-args`, `jar-jvm` hoặc `jar-env` khi không có nguồn cao hơn ghi đè. Trong ba lệnh này **Gradle không còn chạy**; `-P` không tồn tại và `-D` nằm trên lệnh `java` là system property đúng JVM ứng dụng.

## 9. Truyền cấu hình cho `Test`, `JavaExec` và task tùy biến

Không chỉ `bootRun`, những task Gradle khởi chạy JVM con cũng cần phân biệt phạm vi:

- `Test` chạy test trong một hoặc nhiều JVM riêng.
- `JavaExec`/`BootRun` khởi chạy ứng dụng Java trong tiến trình khác.
- Compiler daemon/worker có cơ chế runtime riêng tùy plugin và Gradle version.

Ví dụ **đoạn bổ sung cho project đã áp dụng Java plugin** khi muốn truyền project property vào JVM chạy test:

```kotlin
tasks.withType<Test>().configureEach {
    val testMode = providers.gradleProperty("testMode").orElse("local")
    systemProperty("demo.test.mode", testMode.get())
}
```

`./gradlew test -PtestMode=ci` khiến test JVM thấy `System.getProperty("demo.test.mode")` là `ci` khi test thực sự chạy. Đây là cấu hình task, **không** có nghĩa `-Ddemo.test.mode=ci` trên Gradle CLI sẽ tự truyền đến test JVM. Với Groovy DSL:

```groovy
tasks.withType(Test).configureEach {
    systemProperty 'demo.test.mode', providers.gradleProperty('testMode').orElse('local').get()
}
```

Nếu muốn đưa một biến OS cụ thể vào JVM của `JavaExec` hoặc `Test` (ví dụ test phải dùng một endpoint sandbox), có thể cấu hình `environment("API_BASE_URL", value)` trên task; thông thường biến môi trường do shell cấp đã được process con kế thừa, nhưng cấu hình rõ ràng giúp kiểm soát tên/giá trị và dễ kiểm thử.

**Quan trọng:** với test phụ thuộc dữ liệu biến đổi, cần khai báo/forward input đúng, tránh để task `UP-TO-DATE` trong khi kết quả thực chất phụ thuộc vào biến môi trường hoặc property chưa được tính vào fingerprint. Các API `systemProperty` của task `Test` giúp Gradle đưa giá trị vào test execution; với custom task, khai báo `@Input` hoặc `inputs.property(...)` và output tương ứng để up-to-date/build cache chính xác. Đọc trực tiếp `System.getenv` trong `doLast` rồi ghi file nhưng không khai báo input có thể làm cache trả kết quả cũ.

## 10. Build logic nên dùng Provider API và xử lý giá trị thiếu có chủ đích

Ba API thường dùng:

```kotlin
val branch = providers.gradleProperty("buildBranch")
val trace = providers.systemProperty("demo.trace")
val endpoint = providers.environmentVariable("SERVICE_ENDPOINT")
```

Mỗi lệnh trả về `Provider<String>`. Có thể:

- `.orElse("local")`: đặt giá trị mặc định nếu không có source.
- `.map { ... }`: chuyển đổi giá trị lười.
- `.isPresent` hoặc `.orNull`: kiểm tra có giá trị trước khi cấu hình một tùy chọn.
- `.get()`: lấy giá trị; ném lỗi nếu giá trị không có và không đặt default.
- `.orElse(providerKhac)`: tổ chức fallback giữa nhiều nguồn.

Ví dụ một project property điều khiển tên build variant nhưng phải kiểm tra đúng tập cho phép:

```kotlin
val buildFlavor = providers.gradleProperty("buildFlavor").orElse("local")
val acceptedFlavors = setOf("local", "qa", "prod")

tasks.register("validateFlavor") {
    doLast {
        val flavor = buildFlavor.get()
        require(flavor in acceptedFlavors) {
            "Unsupported buildFlavor: $flavor"
        }
        println("buildFlavor=" + flavor)
    }
}
```

Chạy `./gradlew -q validateFlavor -PbuildFlavor=qa` in `buildFlavor=qa`. Với giá trị khác, task fail rõ nguyên nhân. Không tự động nối cấu hình này với một production deployment hay môi trường chạy khác: ví dụ chỉ xác thực input của một custom task.

**Configuration cache:** dùng `Provider` giúp Gradle theo dõi một số input từ cấu hình build. Tránh truy cập ngầm `project`/`gradle`/`rootProject` bên trong action khi tạo custom task phức tạp; dùng các task properties và service API hợp lệ. Khi một property ảnh hưởng output của custom task, khai báo nó thành task input (ví dụ `@Input Property<String>`), không chỉ lấy giá trị trong action.

## 11. Cách tổ chức `gradle.properties` và CI/CD

### 11.1. Những loại file configuration

**File project root `gradle.properties`** (có thể commit những giá trị **không nhạy cảm**):

```properties
org.gradle.caching=true
org.gradle.parallel=true
buildFlavor=local
```

**File riêng của người dùng `~/.gradle/gradle.properties`** (không commit):

```properties
# Giá trị nhạy cảm chỉ để minh họa tên khóa, KHÔNG điền vào repo Git
corpRepoUsername=service-account
corpRepoPassword=secret-injected-by-secure-process
```

Khi CI inject giá trị, ưu tiên cơ chế secret của nền tảng thay vì ghi password ra file thường trực. Chú ý “có file user-level” không đồng nghĩa project dễ dàng tái lập nếu người khác không có cùng file; tài liệu hóa **tên các property cần thiết** và đặt default an toàn cho phần không nhạy cảm.

### 11.2. CI truyền project property qua biến môi trường

Thay vì in token lên dòng lệnh:

```bash
./gradlew publish -PrepoPassword=real-secret
```

Hãy để CI cấp `ORG_GRADLE_PROJECT_repoPassword` từ secret store, còn build script đọc `providers.gradleProperty("repoPassword")` hoặc sử dụng cơ chế credentials dành riêng của plugin. Ví dụ:

```text
CI secret store
   -> ORG_GRADLE_PROJECT_repoPassword (environment of Gradle process)
   -> providers.gradleProperty("repoPassword")
   -> repository/publishing task config
```

Trong Gradle, repository có tên `corpRepo` còn hỗ trợ convention dành riêng cho `PasswordCredentials` với property `corpRepoUsername` và `corpRepoPassword`. Ví dụ Kotlin DSL **đoạn cấu hình trong build.gradle.kts**:

```kotlin
repositories {
    maven {
        name = "corpRepo"
        url = uri("https://repo.example.org/repository/maven-private/")
        credentials(PasswordCredentials::class)
    }
}
```

Khi kho cần auth, Gradle có thể lấy credentials từ property theo convention nêu trên; CI cấp `ORG_GRADLE_PROJECT_corpRepoUsername` và `ORG_GRADLE_PROJECT_corpRepoPassword`. URL `example.org` là minh họa, không phải endpoint hoạt động. Không ép khai báo credential cho Maven Central public.

**Bảo mật thực tế:** environment variable không phải một vault; tiến trình có đủ quyền hoặc log/job config vẫn có thể lộ giá trị. Không echo secret, không đặt token vào tên artifact hoặc lệnh hiển thị công khai, không in toàn bộ Gradle properties trong build scan/test output. Nếu token đã bị commit hoặc gửi trong log, cần xoay vòng token. Tránh truyền secret vào Spring Boot runtime chỉ để build JAR nếu ứng dụng không cần giá trị đó.

### 11.3. Biến nào nên chọn?

| Tình huống | Cách truyền khuyến nghị | Lý do |
| --- | --- | --- |
| Bật cờ custom task khi build | `-PbuildFlavor=qa` | Build logic đọc trực tiếp, dễ minh bạch |
| CI cấp credentials repository | `ORG_GRADLE_PROJECT_...` qua secret store | Không đặt secret lên CLI/Git |
| Cấu hình proxy Java cho Gradle | `-Dhttps.proxyHost=...` hoặc `systemProp.https.proxyHost` | Proxy là system property của Gradle/JVM networking |
| Chọn Spring profile với `bootRun` | `--args='--spring.profiles.active=dev'` hoặc `SPRING_PROFILES_ACTIVE` | Gửi trực tiếp vào runtime application |
| Đổi port khi chạy JAR | `java -jar app.jar --server.port=9090` hoặc `SERVER_PORT` | Tách deployment runtime khỏi build |
| Chạy test cần một test property | `-PtestMode=ci` + `Test.systemProperty(...)` | Forward vào forked test JVM một cách rõ ràng |
| Cấu hình heap Gradle daemon | `org.gradle.jvmargs` | Khác heap JVM ứng dụng |
| Cấu hình heap ứng dụng standalone | `java -Xmx... -jar app.jar` | Tác động đúng JVM app |
| Config ứng dụng sản xuất | Secret/config của deployment (environment, config file, secret store) | Không nhúng secret vào artifact khi đóng gói |

## 12. Các lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân phổ biến | Kiểm tra/sửa |
| --- | --- | --- |
| `-Pfoo=x` nhưng Spring Boot vẫn nhận default | Project property chưa được forward sang JVM Spring Boot | Dùng `bootRun --args` / env hoặc thêm mapping `BootRun.systemProperty` |
| `-Dfoo=x` nhưng `providers.gradleProperty("foo")` trả trống | `-Dfoo` là system property, không phải project property | Dùng `providers.systemProperty("foo")` hoặc `-Dorg.gradle.project.foo=x` |
| `ORG_GRADLE_PROJECT_foo` không có tác dụng | Sai case/tên, biến không nằm trong environment của Gradle, bị `-P` override | Kiểm tra tên và precedence, dùng task hiển thị giá trị **không nhạy cảm** |
| `gradle.properties` có `foo=local` nhưng CLI lại thấy `ci` | `-P` / prefix system / env override hoặc file user-level có giá trị khác | Kiểm tra nguồn cho đúng property và file Gradle user home |
| Chạy `-Dserver.port=9090` với `gradlew bootRun` nhưng server vẫn nghe 8080 | -D đặt ở Gradle JVM, không phải app JVM | Dùng `bootRun --args='--server.port=9090'` |
| `bootRun -PdemoMessage=...` chạy được nhưng executable JAR không nhận | Mapping `-P` nằm trong task `BootRun`, không tồn tại khi chạy JAR riêng | Cấp runtime config qua `java -D... -jar`, `--...` hoặc env |
| `java -jar app.jar -Ddemo.message=x` không đổi property | JVM option `-D` đặt sai vị trí, sau tên JAR được coi là application arg | Dùng `java -Ddemo.message=x -jar app.jar` |
| Test JVM không nhận `-Dfoo=x` của Gradle | Task `Test` fork JVM khác | Cấu hình `Test.systemProperty("foo", ...)` |
| CI thấy property trống, dev thấy đúng | CI không inject env/user-level file hoặc tên biến sai | So sánh environment **không lộ secret**, root/user Gradle property và job config |
| Bật cache nhưng output thay đổi sai khi đổi env | Task tự viết không khai báo env/property làm input | Dùng `Provider` với `@Input` hoặc `inputs.property` |
| Cấu hình trong subproject `gradle.properties` không có hiệu lực | API `providers.gradleProperty` không quét tùy tiện mọi file subproject; `systemProp` chỉ root/user | Đặt build-level property ở root hoặc user home |
| Spring Boot env `SERVER_PORT` bị CLI args ghi đè | Runtime config sources có precedence riêng | Kiểm tra `--server.port`, Java system properties và active config |
| Secret bị in trong build log | Task/debug script đã `println` hoặc Gradle CLI chứa token | Loại log, rotate token, dùng secret manager/CI masking và least privilege |

### Quy trình debug ngắn

1. Xác định **giá trị cần đến đâu**: Gradle script, Gradle JVM, forked `Test`/`bootRun`, hay JVM chạy JAR sau triển khai.
2. Ghi chính xác lệnh gọi, ví dụ `./gradlew bootRun -Pprofile=dev` hay `./gradlew bootRun --args='--spring.profiles.active=dev'`.
3. Đối chiếu đúng API nguồn: `gradleProperty`, `systemProperty`, `environmentVariable` hoặc Spring `Environment`.
4. Nếu là ứng dụng Spring Boot, xem **đường forwarding**: `--args`, `BootRun.systemProperty`, `BootRun.environment` hoặc biến môi trường được kế thừa.
5. Kiểm tra precedence cùng khóa và các cấu hình đang hoạt động; nếu có `gradle.properties` user-level, so sánh với project root.
6. Với CI/production, log tên property và trạng thái hiện diện hoặc giá trị **không nhạy cảm**; không dump secret ra terminal.
7. Chạy lại ở môi trường gần thực tế và kiểm tra kết quả: HTTP endpoint, test assertion hoặc artifact output. Không suy đoán từ việc lệnh Gradle kết thúc thành công.

## 13. Bài luyện tập ngắn

Với task `showInputs` ở mục 6, hãy dự đoán output trước khi chạy:

**Bài A.** Project root có `gradle.properties`:

```properties
buildMode=local
```

Chạy `APP_ENV=qa ./gradlew -q showInputs -PbuildMode=ci -Ddemo.trace=on`. Kết quả:

```text
buildMode=ci
demo.trace=on
APP_ENV=qa
```

`-P` override `gradle.properties`; `-Ddemo.trace` là Gradle JVM system property; `APP_ENV` là environment variable.

**Bài B.** Không dùng `-P`, thiết lập `ORG_GRADLE_PROJECT_buildMode=integration` rồi chạy `./gradlew -q showInputs -DbuildMode=system-only`. Giả sử không có override nào khác:

```text
buildMode=integration
demo.trace=disabled
APP_ENV=unset
```

`-DbuildMode=system-only` không ghi đè project property, vì thiếu prefix `org.gradle.project.`.

**Bài C.** Trong project Spring Boot ở mục 8, chạy `./gradlew bootRun -PdemoMessage=from-P --args='--demo.message=from-args'`. Với hai nguồn cùng đặt `demo.message`, ứng dụng trả **`from-args`**, vì Spring Boot command-line args có ưu tiên cao hơn Java system property được `BootRun` forward. Đây là **quy tắc runtime Spring Boot**, không phải luật ưu tiên giữa `-P` và `-D` của Gradle.

**Bài D.** Chạy executable JAR với `DEMO_MESSAGE=from-env java -Ddemo.message=from-jvm -jar build/libs/spring-property-demo-0.1.0.jar`. Endpoint trả **`from-jvm`** do Java system property của **chính JVM ứng dụng** có ưu tiên hơn environment variable cho khóa đó.

## 14. Tài liệu chính thức để đối chiếu

- Gradle – [Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): project/system/Gradle properties, environment variables, kênh cấu hình và ưu tiên.
- Gradle – [Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `-P`, `-D` và tùy chọn Gradle.
- Gradle – [Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Provider` và property API.
- Gradle – [Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): theo dõi build configuration inputs.
- Gradle – [Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task inputs/outputs và khai báo state.
- Spring Boot Gradle Plugin – [Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): `bootRun`, `--args`, `systemProperty`.
- Spring Boot – [Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): môi trường, Java system properties, command-line args và PropertySources.

**Quy tắc ghi nhớ:** `-P` tạo **project property cho Gradle**, `-D` đặt **system property cho JVM chạy Gradle** (ngoại lệ đặc biệt `-Dorg.gradle.project.*` tạo project property), còn biến môi trường là dữ liệu của **tiến trình OS** (prefix `ORG_GRADLE_PROJECT_*` được Gradle chuyển thành project property). `bootRun`, `Test` và `java -jar` có JVM/runtime riêng; phải chọn cơ chế forwarding phù hợp và kiểm tra precedence **tại nơi giá trị được sử dụng**.