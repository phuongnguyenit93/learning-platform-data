# Tùy chỉnh `springBoot.mainClass` và các tác vụ Boot trong Gradle

Trong một dự án Spring Boot dùng Gradle, lớp có phương thức `public static void main(String[] args)` thường được plugin tìm tự động. Khi dự án có **nhiều entry point**, build nhiều module hoặc muốn chạy một main class khi phát triển nhưng đóng gói main class khác, sự tự động đó có thể không còn đủ rõ ràng. Spring Boot Gradle plugin cho phép khai báo **`springBoot.mainClass` cho cả project** và cấu hình riêng các tác vụ như `bootRun`, `bootJar`, `bootWar`, `bootBuildImage`.

Bài này giải thích cơ chế chọn main class, cách cấu hình **Groovy DSL (`build.gradle`)** và **Kotlin DSL (`build.gradle.kts`)**, cách truyền đối số/JVM options, sự khác nhau giữa chạy và đóng gói, và phương pháp kiểm tra artifact đầu ra. Ví dụ sử dụng **Spring Boot 3.3.13, Java 17, Gradle 8.x** để minh họa nhất quán; đây là phiên bản hướng dẫn, **không hàm ý là phiên bản Spring Boot mới nhất**. Kiểm tra tài liệu tương ứng nếu project dùng Spring Boot hoặc Gradle ở nhánh khác.

## 1. Từ plugin đến các tác vụ Boot

`org.springframework.boot` là **Gradle plugin** bổ sung khả năng xây dựng và chạy ứng dụng Spring Boot. Nó phản ứng với các plugin Java/WAR/application khác để đăng ký, kết nối và cấu hình task thích hợp.

| Task | Chức năng | Điều kiện hoặc lưu ý chính |
| --- | --- | --- |
| `bootRun` | Chạy ứng dụng trực tiếp từ classpath main; không cần tạo executable JAR trước | Được tạo khi áp dụng Spring Boot plugin cùng Java plugin |
| `bootJar` | Đóng gói executable JAR có ứng dụng và runtime dependencies | Có với Java plugin; khác với `jar` thông thường |
| `bootWar` | Đóng gói executable WAR | Có khi áp dụng `war` plugin; cần cấu hình deployment phù hợp |
| `bootBuildImage` | Dùng Cloud Native Buildpacks để xây OCI container image từ ứng dụng đã đóng gói | Cần Docker daemon/đầu cuối container được hỗ trợ; không tự chạy chỉ vì gọi `build` |
| `bootTestRun` | Chạy một main class từ **test source set** cùng test runtime classpath | Hữu ích với launcher thử nghiệm; không phải task chạy unit test |
| `bootBuildInfo` | Sinh build metadata `META-INF/build-info.properties` | Thường cần gọi `springBoot { buildInfo() }` để đăng ký/sử dụng |
| `bootAot`, `bootTestAot`, `processAot` | Task liên quan AOT, khi phiên bản/plugin/cấu hình tương ứng cung cấp | Không giả định luôn có trong mọi dự án; xác minh bằng danh sách task thực tế |

**Phân biệt task:** `test` chạy bài kiểm thử JUnit; `bootTestRun` chạy một **chương trình có `main` trong test source set**. `bootJar` làm ra artifact; `bootRun` chạy trực tiếp; `bootBuildImage` tạo container image. Chúng dùng một số cài đặt chung nhưng có mục đích và đầu ra khác nhau.

Luồng điển hình:

```text
src/main/java + src/main/resources
                |
            compileJava
                |
       classes / resources
                |
          +-----+---------------------+
          |                           |
       bootRun                       bootJar
    (JavaExec)              (Boot executable archive)
          |                           |
      JVM chạy                    build/libs/*.jar
                                      |
                                      v
                               bootBuildImage
                                (OCI image)

src/test/java + src/test/resources
                |
           test classes
                |
          +-----+------+
          |            |
         test       bootTestRun
        (JUnit)      (main test)
```

Đây là **sơ đồ khái niệm**, không phải danh sách dependency task đầy đủ. Để xem task thực có trong project, chạy `./gradlew tasks --all` hoặc `./gradlew help --task bootJar`. Một project thư viện không áp dụng Spring Boot plugin có thể không có các task Boot.

## 2. `mainClass` là gì? Chọn lớp khởi động ở đâu?

### 2.1. Ý nghĩa của main class

Một chương trình Java khởi động tại phương thức:

```java
public static void main(String[] args)
```

Với Spring Boot, lớp khởi động thường gắn `@SpringBootApplication` rồi gọi `SpringApplication.run(...)`. Nhưng **Java main class không bắt buộc có `@SpringBootApplication`**: một công cụ command line dùng cùng project cũng có thể khai báo `main`.

Tên dùng trong Gradle là **tên class đầy đủ theo package**, ví dụ:

```text
com.example.launch.LaunchApplication
```

Không dùng đường dẫn file `src/main/java/com/example/launch/LaunchApplication.java`, không thêm `.java` hoặc `.class`, không viết tên tắt `LaunchApplication` khi package thực là `com.example.launch`.

### 2.2. Gradle Boot tự tìm main class thế nào?

Ở Spring Boot 3.3, `bootRun`, `bootJar` và `bootWar` có thể xác định main class bằng cách tìm class với phương thức `public static void main(String[])` trong **đầu ra main source set**. Khi có **một ứng viên rõ ràng**, cấu hình mặc định thường đủ. Khi **có nhiều ứng viên**, plugin có thể không chọn được duy nhất hoặc chọn khác mong muốn; giải pháp là khai báo tường minh.

Nếu một dự án chỉ có test main class ở `src/test/java`, nó không trở thành main class của executable JAR chính; `bootTestRun` là một trường hợp riêng tìm trong **test source set**.

### 2.3. Thiết lập toàn project: `springBoot.mainClass`

Với **Groovy DSL** (`build.gradle`):

```groovy
springBoot {
    mainClass = 'com.example.launch.LaunchApplication'
}
```

Với **Kotlin DSL** (`build.gradle.kts`):

```kotlin
springBoot {
    mainClass.set("com.example.launch.LaunchApplication")
}
```

Đây là cấu hình **Spring Boot plugin extension của project**. Nó cung cấp lựa chọn main class chung cho các Boot task dùng quy ước đó, đặc biệt `bootRun` và các task executable archive. Ưu tiên cách này khi bạn muốn **chạy local và JAR/WAR sản xuất dùng cùng một entry point**.

**Đừng nhầm với `spring.main.*` trong `application.yml`:** `springBoot.mainClass` là cấu hình **Gradle build** chọn class nào chứa `main`. `spring.main.*` là nhóm thuộc tính **Spring Application runtime** có nghĩa khác; nó không chọn class cho `bootJar`.

## 3. Ví dụ chạy được: dự án có hai main class

Giả sử một project có ứng dụng REST thật và một chương trình console dùng để kiểm tra nhanh. Cấu trúc:

```text
launcher-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/main/java/com/example/launch/
    ├── LaunchApplication.java
    └── DiagnosticMain.java
```

Tạo `settings.gradle`:

```groovy
rootProject.name = 'launcher-demo'
```

Tạo `build.gradle` đầy đủ:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

springBoot {
    mainClass = 'com.example.launch.LaunchApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Giải thích:** Java toolchain yêu cầu Java 17 cho compile/test; Spring Boot plugin cung cấp các task Boot; dependency-management plugin quản lý version dependency theo BOM Spring Boot phù hợp. `springBoot.mainClass` chọn duy nhất `LaunchApplication` dù project có thêm `DiagnosticMain`. Phiên bản các plugin trong ví dụ là **cặp minh họa cụ thể**; khi nâng cấp nên tra cứu compatibility của plugin hiện dùng.

Tạo `src/main/java/com/example/launch/LaunchApplication.java`:

```java
package com.example.launch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class LaunchApplication {

    public static void main(String[] args) {
        SpringApplication.run(LaunchApplication.class, args);
    }
}

@RestController
class PingController {

    @GetMapping("/ping")
    String ping() {
        return "boot-main-ok";
    }
}
```

Tạo `src/main/java/com/example/launch/DiagnosticMain.java`:

```java
package com.example.launch;

public final class DiagnosticMain {

    private DiagnosticMain() {
    }

    public static void main(String[] args) {
        System.out.println("diagnostic:" + String.join(",", args));
    }
}
```

Hai file hợp lệ với Java 17; tên file public class và package nhất quán. `PingController` là class package-private cùng file `LaunchApplication.java`, Spring quét được nhờ package của `@SpringBootApplication`.

Chạy **ứng dụng REST** với task mặc định:

```bash
./gradlew bootRun --args='--server.port=8091'
```

Khi ứng dụng khởi động xong, mở terminal khác và gửi:

```bash
curl -s http://localhost:8091/ping
```

HTTP response body kỳ vọng:

```text
boot-main-ok
```

Đây là **body** phản hồi; log Spring Boot/Gradle không có stdout cố định. `--args` truyền **application arguments** (ở đây là Spring Boot property `server.port`) cho lần chạy `bootRun`; nó không viết lại `application.yml` và không thay đổi entry point trong JAR sau này.

Đóng gói:

```bash
./gradlew clean test bootJar
```

Với cấu hình trên, artifact thường có tên `build/libs/launcher-demo-1.0.0.jar`. Chạy:

```bash
java -jar build/libs/launcher-demo-1.0.0.jar --server.port=8091
```

Gửi lại `GET /ping` và thấy body `boot-main-ok`. **Dừng tiến trình `bootRun` trước** để tránh xung đột cổng 8091. Các lệnh trên dành cho Linux/macOS; trên Windows PowerShell dùng `.\gradlew.bat` thay `./gradlew` khi project có Gradle Wrapper.

## 4. Cấu hình main class riêng cho từng task

Đặt `springBoot.mainClass` là mặc định rồi chỉ override khi một task thực sự cần entry point khác.

### 4.1. `bootRun` chạy một main khác với executable JAR

Thêm vào cuối `build.gradle` của ví dụ trên:

```groovy
tasks.named('bootRun') {
    mainClass = 'com.example.launch.DiagnosticMain'
    args 'alpha', 'beta'
}
```

Chạy:

```bash
./gradlew bootRun
```

Đây là **stdout từ `DiagnosticMain`** (bỏ qua log Gradle quanh nó):

```text
diagnostic:alpha,beta
```

Lúc này `bootRun` chạy console main và kết thúc nhanh; **`bootJar` vẫn dùng `com.example.launch.LaunchApplication`** theo giá trị toàn project, vì bạn chỉ override `bootRun`. Để chạy REST như mục 3, hãy bỏ đoạn override này hoặc đổi lại `mainClass` của `bootRun`.

Kỹ thuật này hữu ích khi cần chạy tool nội bộ, migration launcher hoặc kiểm tra cấu hình mà không đóng gói tool ấy thành entry point sản xuất. Tuy nhiên, một ứng dụng nên có entry point deploy rõ ràng; tránh để cấu hình local khác bản đóng gói mà không có lý do và test.

### 4.2. `bootJar` dùng main khác với `bootRun`

Muốn chỉ thay entry point của JAR, cấu hình:

```groovy
tasks.named('bootJar') {
    mainClass = 'com.example.launch.LaunchApplication'
}
```

Khi chỉ có một main class đúng, không cần đoạn này. Nó đặc biệt hữu ích trong project có nhiều chương trình hoặc khi đang triển khai cấu hình riêng cho từng artifact. Nếu bạn đặt `bootJar.mainClass` là `DiagnosticMain` thay vì `LaunchApplication`, JAR sẽ chạy chương trình console; Spring Boot web server không tự khởi động chỉ vì dependency web vẫn có mặt.

**Giới hạn tác động:** override task ảnh hưởng **task đó**. `bootRun.mainClass` không tự đổi `bootJar.mainClass`, và ngược lại. `bootBuildImage` tạo image từ archive được nó sử dụng, nên **entry point thực của image gắn với artifact đóng gói**, không nhất thiết trùng task `bootRun` local.

### 4.3. Tùy chỉnh `bootWar` nếu ứng dụng đóng gói WAR

Với project đã áp dụng Gradle `war` plugin và cần đóng gói executable WAR:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

springBoot {
    mainClass = 'com.example.launch.LaunchApplication'
}

tasks.named('bootWar') {
    archiveFileName = 'launcher-demo.war'
}
```

Đây là **đoạn minh họa cho cấu hình dự án WAR riêng**, không chèn lại một khối `plugins` thứ hai vào `build.gradle` mục 3. Với ứng dụng WAR cần chạy trên servlet container bên ngoài, còn phải chuẩn bị launcher/`SpringBootServletInitializer`, scope phù hợp (ví dụ `providedRuntime` cho container) và thiết lập deployment; chỉ khai báo `bootWar` chưa hoàn thành bài toán triển khai servlet container. Khi chỉ deploy bằng executable JAR, tiếp tục dùng `bootJar`.

## 5. Cấu hình `bootRun`: đối số chương trình, JVM và môi trường chạy

`bootRun` là một task kiểu `BootRun`, kế thừa khả năng của Gradle `JavaExec`. Vì vậy có thể điều chỉnh **đối số truyền cho `main`**, JVM arguments, system properties, working directory và environment variables cho tiến trình chạy thử.

### 5.1. Application args khác JVM args và Gradle args

| Loại tham số | Ví dụ | Ai nhận? |
| --- | --- | --- |
| Gradle task/option | `./gradlew bootRun --info` | Gradle, dùng để điều khiển/log quá trình build |
| Application arguments | `./gradlew bootRun --args='--server.port=8091'` | Mảng `String[] args` của main class |
| JVM system property của ứng dụng | `systemProperty 'app.mode', 'local'` trong `bootRun` | JVM mà `bootRun` khởi chạy |
| JVM argument | `jvmArgs '-Xmx512m'` trong `bootRun` | JVM chạy ứng dụng; đặt heap, module flags... |
| Biến môi trường | `environment 'DEMO_FLAG', 'on'` | Process environment của JVM chạy thử |

Cấu hình Groovy:

```groovy
tasks.named('bootRun') {
    systemProperty 'app.mode', findProperty('runMode') ?: 'local'
    jvmArgs '-Xmx512m'
    environment 'DEMO_FLAG', 'on'
}
```

Sau đó:

```bash
./gradlew bootRun -PrunMode=dev --args='--server.port=8091'
```

`-PrunMode=dev` tạo **Gradle project property**. Đoạn `systemProperty` chuyển nó thành Java system property `app.mode=dev` trong JVM ứng dụng. `--args` đi vào `String[] args`. Nếu không truyền `-PrunMode`, `app.mode` nhận giá trị `local`.

**Phân biệt JVM chạy Gradle với JVM của `bootRun`:** `org.gradle.jvmargs` điều chỉnh Gradle daemon, trong khi `bootRun.jvmArgs` điều chỉnh tiến trình Java ứng dụng. Cũng không nhầm `jvmArgs` với application args.

### 5.2. Đọc resource trực tiếp trong lúc phát triển

Theo mặc định, resource được xử lý/sao chép từ `src/main/resources` vào classpath output rồi `bootRun` sử dụng. Có thể cho `bootRun` đọc một số static resource ngay từ source directory:

```groovy
tasks.named('bootRun') {
    sourceResources sourceSets.main
}
```

Điều này hỗ trợ thấy thay đổi static resource trong lúc chạy thử. Nó **không tự bảo đảm Java source được hot reload** và không thay đổi cách `bootJar` đóng gói file; muốn tự động restart khi class thay đổi thường cần cơ chế devtools/IDE/build tương ứng.

### 5.3. Tối ưu khởi động của `bootRun`

`bootRun` mặc định bật cơ chế `optimizedLaunch` để cải thiện khởi động khi phát triển. Chỉ tắt nếu có lý do đo lường/debug:

```groovy
tasks.named('bootRun') {
    optimizedLaunch = false
}
```

Đây là cài đặt **task `bootRun`**, không phải cách bật/tắt auto-configuration Spring Boot, và không tương đương với tối ưu bytecode/JVM cho JAR production.

## 6. `bootJar`: tên JAR, main class và manifest

### 6.1. `bootJar` so với `jar`

Khi dùng Spring Boot Gradle plugin cùng Java plugin:

- `bootJar` tạo **Spring Boot executable JAR** chứa application class/resource và runtime dependencies.
- `jar` là task Gradle Java tạo **plain JAR** (thường được gán classifier `plain` để phân biệt).
- `assemble` / `build` thường được nối với `bootJar`. Khi chỉ cần xác minh artifact cụ thể, có thể chạy trực tiếp `bootJar`.

Cấu trúc executable JAR thông thường:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/...       # launcher của Spring Boot
BOOT-INF/classes/...                      # class và resource ứng dụng
BOOT-INF/lib/...                          # runtime dependency JAR
```

**Không đổi `Main-Class` của manifest thành lớp ứng dụng một cách tùy tiện.** Trong executable Boot JAR, `Main-Class` thường là Spring Boot launcher, còn `Start-Class` trỏ tới **entry point của ứng dụng**. Cấu hình `springBoot.mainClass` hoặc `bootJar.mainClass` giúp plugin quản lý đúng `Start-Class` và cấu trúc launch. Trong trường hợp chuyên biệt, có thể chỉnh `Start-Class` qua manifest task, nhưng cách rõ ràng nhất là dùng `mainClass`.

### 6.2. Đổi tên artifact mà không đổi main class

Thêm vào `build.gradle`:

```groovy
tasks.named('bootJar') {
    archiveFileName = 'launcher-demo.jar'
}
```

Chạy:

```bash
./gradlew bootJar
jar tf build/libs/launcher-demo.jar
java -jar build/libs/launcher-demo.jar
```

`archiveFileName` đổi **tên output**; nó không đổi `springBoot.mainClass`, package của Java source hay tên endpoint. Muốn đổi classifier hoặc đường dẫn output, dùng các thuộc tính archive tương ứng của Gradle và kiểm tra artifact thật. Nếu project vừa dùng `jar` vừa dùng `bootJar`, hãy chọn đúng sản phẩm khi deploy; plain JAR có thể không chạy bằng `java -jar` như executable Boot JAR.

### 6.3. Về `launchScript()` và layered JAR

`bootJar` cho phép tùy chỉnh đóng gói nâng cao, ví dụ:

```groovy
tasks.named('bootJar') {
    // Chỉ bật nếu cần thực thi trực tiếp bằng shell script trên hệ thống phù hợp
    launchScript()
}
```

`launchScript()` thêm shell script ở đầu archive để hỗ trợ chạy trực tiếp trên hệ thống Unix thích hợp. Một số công cụ thao tác ZIP/JAR có thể không đọc dạng này như mong đợi; không bật chỉ để thay đổi main class. Executable JAR thông thường đã chạy được với `java -jar` mà không cần launch script.

Spring Boot 3.3 cũng hỗ trợ **layered archives** để tối ưu caching trong image; main class vẫn là thông tin về entry point, còn layer định nghĩa cách chia class/dependency thành các nhóm. Hai mục tiêu này độc lập.

## 7. `bootBuildImage`: từ task đóng gói đến OCI image

`bootBuildImage` dùng Cloud Native Buildpacks để xây container image từ executable archive, thường lấy từ `bootJar` hoặc `bootWar`. Nếu đã đặt main class cho archive, image sẽ mang entry point tương ứng trong artifact được build. Nó **không chạy server local bằng `bootRun`**.

Ví dụ tùy chỉnh tên image:

```groovy
tasks.named('bootBuildImage') {
    imageName = 'example/launcher-demo:1.0.0'
}
```

Lệnh:

```bash
./gradlew bootBuildImage
```

Task cần truy cập Docker daemon cùng builder/run image hỗ trợ; việc tải builder/buildpacks có thể cần mạng. Đây là ví dụ **build local image**; nó không tự push image lên registry khi chưa yêu cầu publishing. Muốn xác minh artifact có main class đúng, kiểm tra `bootJar`/`bootWar` trước, sau đó kiểm tra image đã được tạo và chạy thử trong môi trường container tương ứng.

**Không giả định `./gradlew build` luôn xây OCI image.** `build` thường bao gồm kiểm tra và đóng gói JAR/WAR; `bootBuildImage` là một task riêng, phải được gọi hoặc nối vào graph có chủ đích.

## 8. `bootTestRun` và `bootBuildInfo` không cùng vai trò với `bootRun`

### 8.1. `bootTestRun`

Spring Boot 3.3 đăng ký `bootTestRun` để chạy main class trong **test source set** với test runtime classpath. Ví dụ tạo `src/test/java/com/example/launch/TestLauncher.java`:

```java
package com.example.launch;

public final class TestLauncher {

    private TestLauncher() {
    }

    public static void main(String[] args) {
        System.out.println("test-launcher");
    }
}
```

Chạy:

```bash
./gradlew bootTestRun
```

Nếu không có main test khác gây nhập nhằng, stdout từ chương trình gồm:

```text
test-launcher
```

Để không phụ thuộc tự dò entry point, có thể cấu hình riêng:

```groovy
tasks.named('bootTestRun') {
    mainClass = 'com.example.launch.TestLauncher'
}
```

**Không dùng `bootTestRun` để thay thế `./gradlew test`.** Task `test` kiểm thử theo test framework; `bootTestRun` chỉ thực thi main class đã chọn và có thể dừng/tiếp tục tùy chương trình.

### 8.2. `bootBuildInfo`

Spring Boot plugin có thể tạo metadata build bằng DSL:

```groovy
springBoot {
    buildInfo()
}
```

Khi bật, task `bootBuildInfo` tạo metadata như tên, version và thời điểm build (tùy cấu hình), phục vụ chức năng hiển thị build information của ứng dụng. Task này **không chọn main class**, không trực tiếp biên dịch Java, và không phải lệnh xây executable JAR thay `bootJar`.

Tùy dự án và cách reproducible build, có thể cần kiểm soát/loại thời điểm build để tránh nội dung artifact biến động mỗi lần build. Chỉ bật build info nếu có người tiêu thụ metadata thực tế.

## 9. Kotlin DSL tương đương

Các đoạn phía trên dùng Groovy DSL. Với `build.gradle.kts`, cấu hình task cụ thể bằng typed task:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

springBoot {
    mainClass.set("com.example.launch.LaunchApplication")
}

tasks.named<BootRun>("bootRun") {
    systemProperty("app.mode", findProperty("runMode") ?: "local")
}

tasks.named<BootJar>("bootJar") {
    archiveFileName.set("launcher-demo.jar")
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là **file `build.gradle.kts` đầy đủ** dùng cùng hai lớp Java trong mục 3. Phần khác biệt chính:
- Groovy: `mainClass = '...'`. Kotlin: `mainClass.set("...")`.
- Groovy: `tasks.named('bootJar') { ... }`. Kotlin: `tasks.named<BootJar>("bootJar") { ... }`.
- Groovy có thể dùng cú pháp method call `jvmArgs '-Xmx512m'`; Kotlin dùng `jvmArgs("-Xmx512m")`.
- Không chép nguyên cú pháp Groovy vào `build.gradle.kts`, và không chép Kotlin DSL vào `build.gradle`.

Nếu chỉ muốn chuyển **`bootRun` sang diagnostic main** trong Kotlin DSL, thêm:

```kotlin
tasks.named<BootRun>("bootRun") {
    mainClass.set("com.example.launch.DiagnosticMain")
    args("alpha", "beta")
}
```

Đoạn này **ghi đè cấu hình `bootRun` theo cùng task**; trong file hoàn chỉnh, hãy gộp các thuộc tính trong một `tasks.named<BootRun>("bootRun")` hoặc chỉnh khối có sẵn để dễ đọc, không cần tạo nhiều nơi cấu hình cho cùng một mục đích.

## 10. Dự án nhiều module: chỉ áp dụng Boot task cho module chạy thật

Ví dụ một Gradle multi-project:

```text
root-project/
├── settings.gradle
├── build.gradle
├── shared-lib/
│   └── build.gradle
└── api-service/
    └── build.gradle
```

`shared-lib` là thư viện; `api-service` là ứng dụng Spring Boot. Các task thuộc **project sở hữu chúng**: `:api-service:bootRun`, `:api-service:bootJar`, `:shared-lib:jar`.

Nên đặt `springBoot.mainClass` **trong project ứng dụng cần chạy**:

```groovy
// api-service/build.gradle (đoạn cấu hình của module)
springBoot {
    mainClass = 'com.example.api.ApiApplication'
}
```

Không giả định mọi module trong repository đều có `bootJar` hoặc có lớp main. Nếu áp dụng Boot plugin cho toàn bộ subproject kể cả thư viện, Gradle có thể tạo task Boot không cần thiết hoặc build lỗi vì không tìm được main class. Thay vào đó, các thư viện thuần thường chỉ cần `java-library`; module ứng dụng áp dụng `org.springframework.boot` ở nơi phù hợp.

Chạy từ thư mục gốc:

```bash
./gradlew :api-service:bootJar
./gradlew :api-service:bootRun
```

Hai lệnh chỉ là **ví dụ với module thực sự mang tên `api-service`**. Dấu hai chấm biểu thị Gradle project path. Khi cần chạy `bootRun` ở module khác, không sửa global main class của mọi project chỉ để đổi đối tượng đang thực thi.

## 11. Kiểm tra main class thực sự trong JAR và task graph

### 11.1. Xem danh sách task

```bash
./gradlew tasks --all
./gradlew help --task bootRun
./gradlew help --task bootJar
```

Nếu không có `bootJar`, kiểm tra plugin `java`/`org.springframework.boot` ở đúng project. Nếu không có `bootWar`, kiểm tra `war` plugin. Để xem task phụ thuộc mà không thực thi:

```bash
./gradlew bootJar --dry-run
```

`--dry-run` cho biết task dự kiến được chạy; nó **không kiểm tra nội dung JAR**, nên phải build thật để xác minh main class và dependency.

### 11.2. Phân biệt `Start-Class` và `Main-Class`

Build:

```bash
./gradlew clean bootJar
```

Dùng lệnh JDK:

```bash
jar tf build/libs/launcher-demo-1.0.0.jar
```

Tìm `META-INF/MANIFEST.MF`, `BOOT-INF/classes/com/example/launch/LaunchApplication.class`, `BOOT-INF/lib/`. Với Spring Boot 3.3 executable JAR, manifest điển hình có:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.launch.LaunchApplication
```

Đây là **hai thuộc tính minh họa cần đối chiếu**, không phải toàn bộ manifest; thứ tự và các trường khác có thể thay đổi. Có thể xem nội dung manifest bằng công cụ đọc ZIP/JAR phù hợp, hoặc giải nén `META-INF/MANIFEST.MF` vào thư mục tạm rồi mở file. Lệnh `jar tf` **chỉ liệt kê entry**, không in nội dung manifest.

- **`Main-Class`**: Boot launcher, cho Java biết chương trình nào nhận lệnh `java -jar` đầu tiên.
- **`Start-Class`**: class `main` thực của ứng dụng, Boot launcher sẽ chuyển quyền điều khiển đến đây.

Nếu manifest có `Start-Class` không như mong đợi, kiểm tra `springBoot.mainClass`, `tasks.named('bootJar')`, `application.mainClass` (nếu có) và mọi cấu hình manifest ghi đè. Khi dùng `bootWar`, layout/launcher khác JAR nên kiểm tra theo artifact thực.

### 11.3. Chạy chính artifact đó

```bash
java -jar build/libs/launcher-demo-1.0.0.jar --server.port=8091
```

Kiểm tra endpoint `GET /ping` như mục 3. Điều này quan trọng khi `bootRun` và `bootJar` được cố ý cấu hình main class khác nhau: chạy local thành công không chứng minh executable JAR sẽ chọn đúng main.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể xảy ra | Cách kiểm tra / sửa |
| --- | --- | --- |
| `bootJar` không xác định được main class | Có nhiều lớp `main` hoặc entry point không nằm trong main source set | Đặt `springBoot.mainClass` đúng fully qualified class |
| `bootRun` chạy main khác JAR | Có override `tasks.named('bootRun')` riêng | So sánh cấu hình `bootRun` và `bootJar`, kiểm tra `Start-Class` |
| `ClassNotFoundException` khi `java -jar` | Tên package/class không đúng hoặc class không được biên dịch/đóng gói | Đối chiếu source path, package và `jar tf` |
| `bootJar` thành công nhưng không có HTTP endpoint | JAR dùng console main; hoặc thiếu web dependency/configuration | Kiểm tra `Start-Class` và chạy thử đúng artifact |
| `bootBuildImage` không chạy được | Docker daemon chưa truy cập được, lỗi builder/buildpack hoặc plugin | Kiểm tra Docker và log task; xác minh `bootJar` trước |
| Không có `bootWar` | Chưa áp dụng Gradle `war` plugin | Bật `war` ở module thực sự đóng gói WAR |
| Không có `bootRun` ở module thư viện | Module không áp dụng Spring Boot plugin/Java plugin | Xác định module ứng dụng; không ép thư viện trở thành app |
| Đặt `spring.main.class` trong YAML nhưng JAR chọn sai main | Nhầm cấu hình Spring runtime và Gradle entry point | Dùng `springBoot.mainClass` hoặc `bootJar.mainClass` |
| `--args` không được đưa vào JAR khi deploy | `--args` chỉ là tham số của **lần chạy `bootRun`** | Truyền đối số khi `java -jar`/container start |
| Đổi `archiveFileName` rồi CI không tìm thấy JAR | Đường dẫn artifact trong pipeline vẫn dùng tên cũ | Đồng bộ đúng tên và đường dẫn output |
| `bootTestRun` không chạy unit tests | Đây là task chạy main class test, không phải JUnit test task | Dùng `./gradlew test` và `useJUnitPlatform()` khi cần |
| JVM chạy local khác môi trường production | Java toolchain, Gradle JVM và runtime JDK khác nhau | Kiểm tra `java -version`, `./gradlew --version` và runtime của image/JAR |
| Dùng `Main-Class` = class ứng dụng bằng tay | Vô tình thay launcher của Spring Boot archive | Cấu hình `mainClass`; kiểm tra `Main-Class` và `Start-Class` |

## 13. Checklist khi cấu hình và kiểm thử

- [ ] Xác định entry point sản xuất là lớp nào, tên **fully qualified** đúng với Java package.
- [ ] Nếu có nhiều main class, đặt `springBoot.mainClass` ở project ứng dụng.
- [ ] Chỉ override `bootRun.mainClass`, `bootJar.mainClass` hay `bootWar.mainClass` khi các task **thật sự cần entry point khác nhau**.
- [ ] Test phát triển bằng `bootRun`; kiểm thử hành vi trong JAR bằng `bootJar` và `java -jar`.
- [ ] Truyền application args qua `--args` hoặc `args`; JVM settings qua `jvmArgs`/`systemProperty` đúng mục đích.
- [ ] Phân biệt `bootJar` với plain `jar` và `bootBuildImage` với `bootRun`.
- [ ] Nếu đóng gói WAR, xác minh `war` plugin và điều kiện deployment thay vì chỉ đổi tên file.
- [ ] Trong multi-project, chạy task theo đúng Gradle project path và không áp dụng Boot plugin đại trà cho thư viện thuần.
- [ ] Chạy `./gradlew tasks --all`, `bootJar --dry-run`, build thật và kiểm tra `jar tf` / manifest.
- [ ] Xác nhận `Start-Class` đúng, endpoint/console output đúng, CI lấy đúng artifact.

**Ghi nhớ:** `springBoot.mainClass` là **entry point mặc định cấp project**; `bootRun.mainClass`, `bootJar.mainClass`, `bootWar.mainClass` là **các lựa chọn riêng cấp task**. `bootRun` vận hành từ classpath, `bootJar`/`bootWar` tạo executable archive, còn `bootBuildImage` tạo image từ artifact. Kiểm tra chính artifact được deploy là cách tin cậy nhất để biết main class cuối cùng có đúng hay không.

## Tài liệu tham khảo

- [Spring Boot 3.3 Gradle Plugin — Running Your Application](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging-oci-image.html)
- [Gradle User Manual — The Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)