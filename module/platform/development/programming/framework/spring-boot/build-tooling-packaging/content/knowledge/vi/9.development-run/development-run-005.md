# Cấu hình gỡ lỗi từ xa cho tiến trình ứng dụng Spring Boot

## 1. Remote debugging là gì và đang gỡ lỗi JVM nào?

**Remote debugging** là việc dùng một trình gỡ lỗi (IntelliJ IDEA, VS Code, Eclipse hoặc một công cụ JDWP tương thích) kết nối vào **tiến trình Java đã được khởi động với debug agent**. Trình gỡ lỗi có thể đặt breakpoint, xem call stack/biến, bước qua mã và kiểm tra luồng thực thi. “Remote” chỉ có nghĩa debugger và JVM ứng dụng là hai thực thể kết nối qua giao thức; chúng có thể nằm trên **cùng máy**, trong **Docker container**, trên **VM** khác hoặc trong **pod Kubernetes**.

Cơ chế phổ biến trên Java 17+ là **Java Debug Wire Protocol (JDWP)**. JVM ứng dụng nạp debug agent bằng tham số `-agentlib:jdwp=...`. IDE kết nối vào cổng của agent. Spring Boot không cần một “chế độ debug network” riêng để hỗ trợ JDWP; đây là tính năng của JVM.

```text
Máy lập trình viên / IDE                          JVM ứng dụng Spring Boot
+--------------------------------+              +-------------------------------+
| IntelliJ / VS Code             |  JDWP TCP    | Java 17+ + JDWP agent        |
| - Source của đúng phiên bản    |------------->| - port 5005                 |
| - Breakpoint                  |              | - class + dependency        |
| - Attach: localhost:5005      |              | - HTTP server: port 8080    |
+--------------------------------+              +-------------------------------+
                                      ^                       ^
                                      |                       |
                              Cổng gỡ lỗi              Cổng HTTP API
                              (VD 5005)                (VD 8080)
```

**Hai cổng độc lập:** `server.port=8080` của Spring Boot phục vụ HTTP; `address=127.0.0.1:5005` trong JDWP phục vụ debugger. Đổi `server.port` không đổi cổng JDWP. Ngược lại, mở port 5005 không đồng nghĩa HTTP endpoint đang chạy, nhất là khi bật `suspend=y`.

### Các trường hợp cần remote debugging

- Chạy ứng dụng qua `java -jar`, Gradle `bootRun` hoặc Maven `spring-boot:run`, rồi attach IDE để xem lỗi chỉ xuất hiện ở runtime.
- Chạy dịch vụ trong Docker hoặc môi trường development riêng, nhưng muốn đặt breakpoint bằng IDE trên máy.
- Tìm vấn đề xảy ra tại startup: dùng `suspend=y` để attach **trước khi** phương thức `main`/Spring context khởi tạo.
- Tìm vấn đề request cụ thể: dùng `suspend=n` để ứng dụng lên sẵn rồi attach trước khi gửi request.
- So sánh cấu hình runtime, luồng thực thi qua controller/service, exception stack và trạng thái bean.

**Không nhầm với** `--debug` của Spring Boot: tham số đó bật một số thông tin logging/condition evaluation, **không mở cổng JDWP**. `-Dorg.gradle.debug=true` lại gỡ lỗi **Gradle daemon/build logic**, không phải Spring Boot application JVM. Cần chọn đúng tiến trình.

## 2. Cú pháp JDWP của Java 17+

Lệnh chuẩn để chạy một ứng dụng JAR đã build trong môi trường phát triển:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

Ở đây `app.jar` là tên file JAR thực thi; ví dụ chạy thật ở mục 4 tạo một tên cụ thể. Với Java 17+, dùng `address=127.0.0.1:5005` để agent **chỉ lắng nghe trên loopback**. Một cấu hình khác tương đương cho localhost thường là `address=5005` (trên JDK hiện đại), nhưng dạng có host rõ ràng dễ kiểm tra hơn.

| Thành phần | Ý nghĩa và hành vi |
| --- | --- |
| `-agentlib:jdwp` | Nạp debug agent vào **JVM ứng dụng**. Đây là JVM option, phải đứng trước `-jar` hoặc tên main class. |
| `transport=dt_socket` | Kết nối debugger qua socket/TCP. |
| `server=y` | JVM ứng dụng **lắng nghe**, IDE chủ động **attach** vào JVM. |
| `server=n` | JVM chủ động kết nối ra một debugger đang lắng nghe (mô hình đảo chiều; chỉ dùng khi chủ động thiết kế). |
| `suspend=n` | JVM bắt đầu chạy ngay; có thể attach debugger sau khi ứng dụng khởi động. |
| `suspend=y` | JVM chờ debugger attach và cho tiếp tục trước khi chạy mã ứng dụng; hữu ích khi bắt startup. |
| `address=127.0.0.1:5005` | Gắn JDWP vào cổng 5005 trên loopback, phù hợp local dev và SSH tunnel. |
| `address=*:5005` | Lắng nghe trên **mọi interface**; có thể cần trong container nhưng nguy hiểm nếu port có đường truy cập công khai. |
| `address=5005` | Trên Java 9+ thường chỉ loopback; hành vi trên JDK cũ khác. |

**Quy tắc an toàn:** JDWP không cung cấp lớp xác thực và mã hóa như một dịch vụ HTTPS chuẩn. Ai kết nối được vào debugger có thể quan sát và can thiệp sâu vào tiến trình. Chỉ bật trong môi trường phát triển hoặc một phiên điều tra được cho phép; ưu tiên **loopback + SSH tunnel/kubectl port-forward** và giới hạn quyền network. Không để `*:5005` thông trực tiếp ra Internet, không bật debug agent mặc định trên mọi pod production.

### Chọn `suspend=y` hay `suspend=n`

**`suspend=y`:** JVM thường in thông báo tương tự `Listening for transport dt_socket at address: 5005` và **chưa chạy SpringApplication** cho tới khi IDE attach/resume. Vì thế `curl localhost:8080` sẽ chưa thành công trước thời điểm resume. Dùng cách này để đặt breakpoint trong `main`, bean initialization hoặc code chạy ngay khi startup.

**`suspend=n`:** ứng dụng khởi động bình thường. Đặt breakpoint trong handler/controller, attach IDE rồi mới gọi endpoint. Nếu request đến **trước** khi attach hoặc trước khi đặt breakpoint, debugger không thể quay ngược thời gian để dừng request đã xử lý.

**Lưu ý:** khi breakpoint tạm dừng tất cả threads hoặc một luồng xử lý request, client có thể timeout. Điều đó là tác dụng của debugger, không mặc định là lỗi deadlock của ứng dụng.

## 3. Chuẩn bị môi trường và một ứng dụng Java 17 runnable

Phần này dùng ví dụ **Spring Boot 3.5.0 và Java 17+** để lệnh và cấu hình nhất quán. Đây là một phiên bản ví dụ cố định, **không ngụ ý phiên bản Spring Boot mới nhất**. Cần JDK 17 hoặc cao hơn, Maven hoặc Gradle tương thích với plugin, và kết nối repository để tải dependencies. Mã Java giống nhau cho Maven và Gradle; chỉ chọn một build tool trong lần thực hành.

Cấu trúc:

```text
jdwp-demo/
├── pom.xml                        # dùng nếu chọn Maven
├── settings.gradle.kts             # dùng nếu chọn Gradle
├── build.gradle.kts                # dùng nếu chọn Gradle
└── src/main/java/com/example/debug/JdwpDemoApplication.java
```

**`src/main/java/com/example/debug/JdwpDemoApplication.java`:**

```java
package com.example.debug;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class JdwpDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdwpDemoApplication.class, args);
    }

    @GetMapping("/calc")
    public String calculate(
            @RequestParam("a") int a,
            @RequestParam("b") int b) {
        int result = a + b; // Đặt breakpoint tại dòng này.
        return "sum=" + result;
    }
}
```

Ví dụ có một HTTP endpoint `GET /calc?a=2&b=3`. Khi chạy bình thường, response body là **`sum=5`** (không nhất thiết có ký tự xuống dòng). Breakpoint nằm ở dòng `int result = a + b;`; IDE sẽ dừng tại dòng đó khi request được xử lý.

### 3.1. POM Maven đầy đủ

**`pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jdwp-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Chạy `mvn clean package` tạo executable archive `target/jdwp-demo-0.0.1-SNAPSHOT.jar` nhờ Spring Boot Maven plugin. Nếu repository đã có Maven Wrapper, thay `mvn` bằng `./mvnw` (Windows: `mvnw.cmd`). Dùng POM mẫu và mã Java nêu trên là đủ để khởi động HTTP endpoint.

### 3.2. Gradle Kotlin DSL đầy đủ (lựa chọn thay Maven)

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "jdwp-demo"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.0"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

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
```

Với Gradle Wrapper tương thích Spring Boot 3.5:

```bash
./gradlew clean bootJar
```

Tệp executable JAR thường là `build/libs/jdwp-demo-0.0.1-SNAPSHOT.jar`. Khi chưa có Wrapper, dùng Gradle đã cài tương thích để chạy `gradle wrapper` rồi dùng wrapper, hoặc thay `./gradlew` bằng `gradle`. Trên Windows dùng `gradlew.bat`. Đừng chép `pom.xml` vào một project Gradle đang sử dụng rồi suy luận cả hai build tool đang tự chia sẻ cấu hình: mỗi công cụ có mô hình plugin/task riêng.

## 4. Cách đơn giản nhất: gỡ lỗi JAR bằng `java -jar`

Đây là cách kiểm tra cơ chế JDWP trực tiếp nhất, không phụ thuộc Maven/Gradle runtime sau khi đã có archive.

Với project Maven ở mục 3:

```bash
mvn clean package
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar target/jdwp-demo-0.0.1-SNAPSHOT.jar
```

Với project Gradle, chạy `./gradlew bootJar` rồi thay đường dẫn JAR:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 -jar build/libs/jdwp-demo-0.0.1-SNAPSHOT.jar
```

**Trình tự khi `suspend=y`:**

1. Terminal khởi động JVM và JDWP agent, chờ debugger kết nối vào `127.0.0.1:5005`.
2. Mở IDE, tạo cấu hình **Attach / Remote JVM Debug** với host `localhost` và port `5005`.
3. Attach; nếu IDE yêu cầu resume hoặc dừng tại startup, tiếp tục execution.
4. Spring Boot khởi tạo web server (mặc định port `8080` nếu không bị cấu hình khác ghi đè).
5. Đặt breakpoint ở `calculate` và gửi HTTP request từ terminal khác.

```bash
curl -fsS 'http://localhost:8080/calc?a=2&b=3'
```

Khi breakpoint dừng tại `int result = a + b;`, các biến đầu vào là `a=2` và `b=3`; sau khi bước qua phép cộng, `result=5`. Resume để HTTP client nhận response **`sum=5`**. Nếu bật `suspend=n`, có thể đảo thứ tự bước 2–4, nhưng vẫn phải attach trước request muốn bắt breakpoint.

**Chú ý thứ tự JVM option:** đúng là `java -agentlib:jdwp=... -jar app.jar`. Đặt `-agentlib:jdwp` sau `-jar app.jar` sẽ biến nó thành argument của ứng dụng, không kích hoạt JDWP. Tương tự, `--debug` sau tên JAR là argument Spring Boot, không phải debug-agent JVM option.

### Đổi cổng và bind address

Khi port 5005 đã được tiến trình khác dùng, đổi sang `5006`:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5006 -jar target/jdwp-demo-0.0.1-SNAPSHOT.jar
```

IDE phải attach tới port **5006**, còn HTTP API vẫn là **8080**. Cổng JDWP không cần trùng HTTP port, và cả hai phải không xung đột với những tiến trình khác.

## 5. Gradle: debug tiến trình `bootRun` đúng cách

Spring Boot Gradle plugin tạo task `bootRun`, là một dạng `JavaExec`. Nó khởi động **ứng dụng Spring Boot trong JVM con**, vì vậy có thể dùng tùy chọn `--debug-jvm` của task hoặc cấu hình `debugOptions`.

### 5.1. Bật debug tức thời với `--debug-jvm`

Với Gradle Kotlin DSL ở mục 3:

```bash
./gradlew bootRun --debug-jvm
```

Gradle khởi động tiến trình ứng dụng với debug agent, mặc định **port 5005** và **suspend chờ debugger**. IDE attach `localhost:5005`, sau đó ứng dụng tiếp tục start và có thể gọi `/calc` như mục 4.

Mục tiêu của `--debug-jvm` ở đây là **JVM chạy task `bootRun`**, không phải Gradle daemon. Nếu không muốn chờ startup, xem `debugOptions` ở mục sau. Lệnh `./gradlew test --debug-jvm` thường bật debug cho **forked test JVM**, không phải ứng dụng Spring Boot; chọn task đúng mục đích.

**Tránh nhầm:**

```bash
./gradlew help -Dorg.gradle.debug=true
```

Lệnh này cho phép debug **Gradle build process** (ví dụ build script/plugin), thường chờ debugger ở port 5005; nó không tương đương với `bootRun --debug-jvm`. Không bật đồng thời hai chế độ này trên cùng port 5005 nếu không có chủ đích và bố trí port riêng.

### 5.2. Cấu hình `debugOptions` với Kotlin DSL

Nếu muốn cổng riêng và ứng dụng chạy ngay mà không chờ IDE, **bổ sung** đoạn sau vào `build.gradle.kts` ở mục 3:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    debugOptions {
        enabled.set(true)
        host.set("127.0.0.1")
        port.set(5006)
        server.set(true)
        suspend.set(false)
    }
}
```

Sau đó:

```bash
./gradlew bootRun
```

Ứng dụng chạy với JDWP ở `127.0.0.1:5006`, không chờ debugger (`suspend=false`). Cấu hình IDE attach `localhost:5006`. Các properties `enabled`, `host`, `port`, `server`, `suspend` thuộc `JavaDebugOptions` của Gradle; chúng mô tả **agent trong JVM ứng dụng**.

**Chú ý:** đây là cấu hình debug mặc định cho mọi lần `bootRun` nếu được giữ nguyên trong build script. Trong dự án chung, nên chỉ bật khi có Gradle project property hoặc chỉ lưu ở nhánh/cấu hình development, tránh debug agent được mở ngoài ý muốn khi chạy task trên CI.

Ví dụ chỉ bật khi truyền `-PlocalDebug`:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

val localDebug = providers.gradleProperty("localDebug")

tasks.named<BootRun>("bootRun") {
    debugOptions {
        enabled.set(localDebug.isPresent)
        host.set("127.0.0.1")
        port.set(5006)
        server.set(true)
        suspend.set(false)
    }
}
```

Đây là **phương án thay thế** block `tasks.named<BootRun>` ở trên, không dán cả hai để tránh ghi đè cùng option. Khi gọi `./gradlew bootRun -PlocalDebug`, agent bật. Khi gọi `./gradlew bootRun` và property không có, agent tắt. Với môi trường phát triển lớn, có thể dùng provider rõ ràng để theo dõi cờ cấu hình cho configuration cache.

### 5.3. Groovy DSL tương đương

Nếu project dùng `build.gradle` thay vì Kotlin DSL, có thể khai báo:

```groovy
tasks.named('bootRun') {
    debugOptions {
        enabled = true
        host = '127.0.0.1'
        port = 5006
        server = true
        suspend = false
    }
}
```

Đoạn Groovy này giả định Spring Boot plugin đã tạo task `bootRun`. Các giá trị giống Kotlin DSL: port 5006, chạy ngay, lắng nghe loopback. Chỉ dùng **một** dạng DSL theo project.

### 5.4. `-Dorg.gradle.debug`, `-P`, `--debug` và `--debug-jvm` khác nhau

| Lệnh/tùy chọn | Mục tiêu |
| --- | --- |
| `./gradlew bootRun --debug-jvm` | Bật JDWP cho **JVM ứng dụng** mà task bootRun khởi chạy. |
| `./gradlew help -Dorg.gradle.debug=true` | Bật JDWP cho **Gradle daemon/build logic**. |
| `./gradlew bootRun --debug` | Bật logging DEBUG của **Gradle CLI**, không tự mở JDWP cho app. |
| `./gradlew bootRun --args='--debug'` | Truyền `--debug` vào **Spring Boot application**; đây là cấu hình log/conditions của Boot, không phải JDWP. |
| `./gradlew bootRun -Pfoo=bar` | Đặt một Gradle project property; không tự chuyển thành JDWP hay Spring runtime property. |

Khi thấy IDE “đã kết nối” nhưng breakpoint ở Java controller không dừng, trước hết xác minh IDE đang attach **đúng JVM ứng dụng**, không phải Gradle daemon.

## 6. Maven: truyền JDWP vào JVM của `spring-boot:run`

Maven Spring Boot plugin chạy `spring-boot:run` trong **forked application process**. Vì vậy `-D...` không tự động forward mọi system property từ Maven JVM sang ứng dụng. Plugin có parameter riêng `spring-boot.run.jvmArguments` dùng để truyền **JVM options** vào tiến trình Spring Boot.

Với POM ở mục 3, chạy:

```bash
mvn spring-boot:run "-Dspring-boot.run.jvmArguments=-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
```

Maven khởi chạy JVM ứng dụng với JDWP port 5005 và chờ debugger; IDE attach rồi ứng dụng startup. Đây là một cờ **cho Spring Boot Maven plugin** thông qua Maven property, khác `-Dorg.gradle.debug=true` của Gradle.

Để không chờ debugger từ lúc khởi động, đổi `suspend=n`:

```bash
mvn spring-boot:run "-Dspring-boot.run.jvmArguments=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005"
```

Quoting ở đây đặt toàn bộ `-Dspring-boot.run.jvmArguments=...` trong dấu nháy kép để shell giữ nguyên argument. Nếu project có Maven Wrapper, dùng `./mvnw` hoặc `mvnw.cmd` tương ứng.

### Cấu hình Maven plugin trong POM

Khi thực sự cần dùng một profile phát triển có cấu hình debug riêng, **bên trong** `<plugin>` của `spring-boot-maven-plugin` có thể thêm:

```xml
<configuration>
    <jvmArguments>
        -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005
    </jvmArguments>
</configuration>
```

Đây là **đoạn trong plugin**, không phải một file `pom.xml` độc lập. Cách này bật debug cho mọi lần goal `spring-boot:run` áp dụng cấu hình, vì vậy nên giới hạn ở Maven profile development nếu cần chia sẻ project. Cổng/suspend có thể điều chỉnh bằng CLI như trên.

**Không trộn:** `mvn -X` tăng log/debug **Maven build**, không bật JDWP. `-Dspring-boot.run.arguments=--debug` gửi ứng dụng tham số log Spring Boot, cũng không bật JDWP. Nếu POM có cấu hình `jvmArguments` và CLI có giá trị tương ứng, cần xác định giá trị thực tế được plugin dùng qua output/log và tránh khai báo trùng debug agent.

## 7. IDE: attach tới đúng nguồn mã, đúng host/port

### 7.1. IntelliJ IDEA

1. Mở chính project chứa `JdwpDemoApplication.java`, đảm bảo source tương ứng với class bytecode trong JVM.
2. Đặt breakpoint tại `int result = a + b;`.
3. Vào **Run → Edit Configurations → Add New → Remote JVM Debug** (tên menu có thể thay đổi theo phiên bản IDE).
4. Chọn chế độ debugger **Attach to remote JVM**, đặt **Host = localhost**, **Port = 5005** (hoặc 5006 nếu đã đổi).
5. Khởi động JVM ứng dụng với JDWP, sau đó chạy remote debug configuration để attach.
6. Nếu `suspend=y`, resume để ứng dụng start; gửi `curl /calc` rồi quan sát breakpoint.

IDE cần biết source/classpath tương ứng. Khi có nhiều module/class trùng tên, chọn đúng module hoặc khai báo source lookup. Breakpoint **màu xám, unverified hoặc không dừng** thường do class chưa được nạp, source khác version, không vào nhánh code đó hoặc đã attach nhầm tiến trình.

Remote JDWP attach cho Java thường không cần tính năng bổ sung riêng của Spring Boot debugger plugin. Một số khả năng chuyên sâu về Spring runtime có thể phụ thuộc phiên bản/bản IDE, nhưng bước attach JDWP cơ bản vẫn giống nhau.

### 7.2. Visual Studio Code

Cần **Debugger for Java** (có trong Extension Pack for Java). Trong project, tạo **`.vscode/launch.json`**:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "java",
      "name": "Attach Spring Boot JVM (5005)",
      "request": "attach",
      "hostName": "localhost",
      "port": 5005
    }
  ]
}
```

Mở Run and Debug, chọn `Attach Spring Boot JVM (5005)` rồi bắt đầu. File này chỉ mô tả debugger ở máy phát triển, **không tự khởi động JVM ứng dụng**. Ứng dụng phải được khởi động trước với JDWP và cổng đúng. Đổi `port` thành 5006 nếu build/run dùng 5006. Đảm bảo đã import Java project và có source đúng.

Nếu gỡ lỗi qua VPN/SSH/kubectl tunnel, vẫn nên attach `localhost:<local-port>` sau khi tunnel được thiết lập, thay vì mở JDWP trực tiếp trên địa chỉ IP công cộng.

### 7.3. Các thao tác thường dùng

- **Breakpoint:** dừng tại một dòng khi luồng chạy đến đó; đặt trước khi gửi request.
- **Step Over:** thực hiện dòng hiện tại và dừng ở dòng kế tiếp.
- **Step Into:** vào phương thức đang gọi nếu có bytecode/source tương ứng.
- **Evaluate Expression:** xem giá trị biểu thức trong stack frame hiện tại; tránh gọi hàm có side effect trên dữ liệu nhạy cảm.
- **Exception Breakpoint:** dừng khi exception được ném hoặc chưa được bắt, giúp tìm nguyên nhân trước khi lỗi bị chuyển thành HTTP 500.
- **Resume:** tiếp tục chạy cho tới breakpoint tiếp theo; request HTTP mới nhận response sau khi luồng xử lý được resume.

Khi xem giá trị nhạy cảm qua debugger, cần tôn trọng quyền dữ liệu và chính sách của môi trường đang được gỡ lỗi; debugger có thể nhìn thấy secret hoặc payload nằm trong bộ nhớ tiến trình.

## 8. Docker: debug ứng dụng trong container và attach từ host

Khi JVM nằm trong Docker, `127.0.0.1` **bên trong container** không phải loopback trên máy host. Để port publishing hoạt động thông thường, JVM cần lắng nghe trên interface mà Docker kết nối tới, ví dụ `address=*:5005` **bên trong container**. Sau đó chỉ publish port debugger về **loopback của máy host**.

Ví dụ dùng JAR Maven ở mục 3. **`Dockerfile`:**

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/jdwp-demo-0.0.1-SNAPSHOT.jar app.jar
USER 10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Chạy từ thư mục chứa POM, source và Dockerfile:

```bash
mvn clean package
docker build -t jdwp-demo:dev .
docker run --rm \
  -e 'JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005' \
  -p 127.0.0.1:8080:8080 \
  -p 127.0.0.1:5005:5005 \
  jdwp-demo:dev
```

Các dòng trên dùng dấu `\` để nối lệnh trong Bash; trong PowerShell nên viết `docker run` trên một dòng hoặc dùng cú pháp nối dòng riêng của PowerShell. Có thể chạy trên một dòng:

```bash
docker run --rm -e 'JAVA_TOOL_OPTIONS=-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005' -p 127.0.0.1:8080:8080 -p 127.0.0.1:5005:5005 jdwp-demo:dev
```

**Cách hoạt động:**

- `JAVA_TOOL_OPTIONS` được cấp **riêng cho container ứng dụng**, nên JVM `java -jar` nhận JDWP agent mà không cần sửa Dockerfile để bật debug cố định.
- `address=*:5005` để agent lắng nghe các interface của **container**; đây là điều kiện hay gặp để Docker chuyển kết nối từ host tới container.
- `-p 127.0.0.1:5005:5005` giới hạn **địa chỉ publish ở host** thành loopback. Nó khác `-p 5005:5005`, vốn có thể publish trên nhiều interface host tùy thiết lập Docker.
- `-p 127.0.0.1:8080:8080` publish HTTP API riêng về loopback.
- IDE trên máy host attach `localhost:5005`; sau đó gọi `http://localhost:8080/calc?a=2&b=3`.

**Hai lớp địa chỉ:** `address=*:5005` chỉ là địa chỉ socket **trong container**, không phải lời khuyên mở port này ra công cộng. Phải kiểm tra chính sách network/host binding, Docker version và môi trường (Docker Desktop, bridge network, remote Docker host). Đừng thêm public ingress/service cho 5005.

**Cẩn trọng với `JAVA_TOOL_OPTIONS`:** nếu đặt biến này toàn cục trên máy chạy Maven hoặc Gradle, nó có thể vô tình bật JDWP cho **nhiều JVM** (build tool, daemon, worker, ứng dụng), gây đụng cổng 5005. Ví dụ trên chỉ cấp cho container runtime đúng mục tiêu. Một số launchers có thể in thông báo “Picked up JAVA_TOOL_OPTIONS”; đây là thông báo từ JVM chứ không phải lỗi build.

### Docker Compose tương đương cho môi trường dev

```yaml
services:
  app:
    image: jdwp-demo:dev
    environment:
      JAVA_TOOL_OPTIONS: >-
        -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=*:5005
    ports:
      - "127.0.0.1:8080:8080"
      - "127.0.0.1:5005:5005"
```

File này giả định image `jdwp-demo:dev` đã build như trên. Đây là cấu hình **dev riêng**, không ghép mặc định vào compose production. Khi không gỡ lỗi nữa, tắt cấu hình agent và bỏ mapping port 5005.

## 9. Máy ảo, SSH tunnel và Kubernetes: cách kết nối có kiểm soát

### 9.1. VM/remote host: dùng SSH local forwarding

Khi ứng dụng chạy trên VM phát triển qua SSH, một mô hình an toàn hơn là:

1. JVM trên VM lắng nghe JDWP **127.0.0.1:5005**, không công bố public.
2. Máy phát triển mở một **SSH local port forward** bảo mật từ `localhost:5005` tới `127.0.0.1:5005` của VM.
3. IDE attach `localhost:5005` thông qua tunnel; không cần mở port 5005 trên firewall công cộng.

Ví dụ dạng lệnh SSH:

```bash
ssh -N -L 5005:127.0.0.1:5005 devuser@devhost.example
```

`devhost.example` là hostname **minh họa** phải thay bằng VM phát triển có quyền SSH; `devuser` là tài khoản SSH được cấp quyền. `-N` yêu cầu SSH chỉ thực hiện forwarding. Trên máy IDE, port `localhost:5005` phải còn trống. Nếu dùng host port khác, ví dụ `15005`, attach IDE tới `localhost:15005` trong khi JVM remote vẫn lắng nghe 5005.

Đường tunnel được mã hóa bởi SSH, nhưng **JDWP vẫn không có cơ chế user authentication riêng**. Chỉ cấp SSH access cho đúng người, tắt agent khi kết thúc phiên debug.

### 9.2. Kubernetes development namespace

Trong Kubernetes, chỉ debug khi được phê duyệt ở namespace development và có quyền truy cập pod. Giả sử ứng dụng đã được khởi chạy với debug agent lắng nghe `*:5005` **bên trong pod** (ví dụ qua environment tạm thời của dev deployment), chạy trên máy lập trình viên:

```bash
kubectl port-forward --address 127.0.0.1 deployment/jdwp-demo 5005:5005
```

Nếu namespace không phải context hiện tại, thêm `-n <namespace>` với namespace dev chính xác. `kubectl port-forward` chọn một pod thuộc deployment; nếu pod restart hoặc phiên kết nối chấm dứt, phải thiết lập lại forwarding. Cờ `--address 127.0.0.1` đảm bảo **cổng local** chỉ mở trên loopback. IDE attach `localhost:5005`.

**Điều kiện bắt buộc:** có JVM đang nghe 5005 ở pod và Kubernetes RBAC/network policy cho phép port-forward. Không phải chỉ chạy `kubectl port-forward` là tự bật JDWP cho ứng dụng; việc bật agent thường đòi **restart tiến trình JVM** với JVM option thích hợp. Tránh kích hoạt JDWP trên deployment production hoặc expose nó qua `Service`/`Ingress` công cộng. Nếu muốn debug nhiều replica, xác định đúng pod chứa request đang xử lý; lần port-forward tới deployment có thể chọn một pod khác với pod nhận traffic.

### 9.3. Có thể attach vào JVM đang chạy mà không bật agent từ đầu không?

Trong workflow Spring Boot thông thường, cách ổn định và dễ tái lập nhất là **khởi động JVM với `-agentlib:jdwp`**. Một số JDK/tool có cơ chế attach agent động, nhưng cần quyền OS/JDK tương ứng và không nên mặc định khả dụng trong container/production. Bài này sử dụng JDWP agent được cấu hình ngay khi start để tránh kết luận nhầm rằng chỉ cần mở IDE là kết nối được một JVM bất kỳ.

## 10. Xử lý breakpoint khi Spring Boot có nhiều classloader

Spring Boot DevTools (nếu project dùng) có thể tổ chức **restart classloader** riêng cho lớp ứng dụng, giúp phát hiện thay đổi code nhanh. Hệ quả khi debug:

- Breakpoint có thể chuyển trạng thái lúc class được load lại hoặc khi ứng dụng restart; kiểm tra IDE vẫn attach **đúng JVM** và source map đúng.
- Nếu code mới được biên dịch mà JVM cũ vẫn chạy, debugger có thể hiển thị source mới nhưng class trong bộ nhớ vẫn là bytecode cũ. Hãy rebuild/restart hoặc sử dụng HotSwap trong giới hạn công cụ hỗ trợ.
- **Hot Code Replace/HotSwap** thường hỗ trợ thay đổi logic trong phần thân phương thức, nhưng nhiều thay đổi cấu trúc class (thêm field/method, đổi hierarchy) cần restart JVM. Hành vi cụ thể phụ thuộc JDK, IDE và chế độ runtime.
- Spring Boot DevTools **remote update/restart** là cơ chế khác với JDWP và có rủi ro bảo mật riêng; không cần bật remote DevTools để attach debugger JDWP.
- Khi dùng Spring proxies (AOP, transactions, security), lời gọi có thể đi qua proxy/interceptor; đặt breakpoint tại controller/service đúng code path, có thể bật exception breakpoint để xem lỗi trước khi bị handler chuyển đổi.

**Breakpoint trong constructor/bean startup:** dùng `suspend=y`. Với `suspend=n`, Spring đã có thể chạy qua phần tạo bean trước khi IDE attach, nên breakpoint khởi tạo không hit.

## 11. Debug session kết thúc như thế nào?

- **Disconnect trong IDE** chỉ ngắt kết nối debugger; ứng dụng thường vẫn chạy nếu JVM không bị IDE/launcher kill.
- **Stop/Terminate ứng dụng** từ terminal, IDE hoặc container runtime mới thực sự kết thúc Java process.
- Nếu ứng dụng đang suspend tại breakpoint và debugger disconnect, hành vi tiếp tục/phục hồi phụ thuộc IDE và trạng thái thread; không xem disconnect là một cơ chế resume được đảm bảo.
- Nếu debug agent được bật qua Docker/CI/deployment configuration, **tắt nguồn cấu hình đó** để lần restart sau không tự mở cổng JDWP.
- Với `suspend=y` mà không có debugger attach, startup có thể treo mãi ở trạng thái chờ; đừng vô tình đưa cấu hình này vào health-check startup production.

Một phiên debug hữu ích nên ghi nhận **câu lệnh khởi động**, JVM version, host/port JDWP, source revision, thao tác tái hiện bug và kết quả quan sát. Không cần lưu debug port/password/secret nội bộ vào bài hướng dẫn công khai.

## 12. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Kiểm tra và sửa |
| --- | --- | --- |
| IDE báo `Connection refused` | JVM chưa bật JDWP, nhầm port, startup fail, agent chỉ nghe địa chỉ khác | Xác nhận command JVM, log `Listening for transport dt_socket`, host/port |
| IDE báo `Connection timed out` | Firewall, route, Docker publish, Kubernetes port-forward hoặc SSH tunnel hỏng | Kiểm tra đường kết nối tới đúng JVM/port và network policy |
| `ERROR: transport error 202: bind failed` | Port JDWP đã bị tiến trình khác chiếm hoặc bind address không hợp lệ | Đổi port, tắt JVM cũ, kiểm tra IP bind |
| `JDWP Transport dt_socket failed to initialize` | Option sai cú pháp, cổng không khả dụng, agent bị nạp trùng | Kiểm tra `-agentlib` chỉ xuất hiện một lần và option trước `-jar` |
| Ứng dụng không mở HTTP port 8080 | `suspend=y` chưa attach/resume, hoặc app startup fail | Attach debugger trước; phân biệt chờ JDWP với log Spring Boot |
| `bootRun --debug-jvm` nhưng breakpoint không hit | IDE attach Gradle daemon/VM khác, class không đúng | Kiểm tra PID, source, cổng JDWP và đúng task `bootRun` |
| `-Dorg.gradle.debug=true` khiến build chờ | Đang debug Gradle daemon, không phải ứng dụng | Dùng `bootRun --debug-jvm` cho Spring Boot |
| Maven `spring-boot:run` không nhận `-agentlib` | Đặt `-D` sai tên, thiếu `spring-boot.run.jvmArguments`, quote sai | Dùng exact Maven plugin parameter trong mục 6 |
| Java báo `Unrecognized option: -agentlib...` | JVM option bị đặt sau `-jar` hoặc JDK/runtime không hợp lệ | Đưa option lên trước `-jar`, kiểm tra `java -version` |
| Docker host thấy 5005 nhưng attach thất bại | JDWP trong container chỉ bind `127.0.0.1`, không phải interface container | Dùng `address=*:5005` bên trong container + host publish loopback |
| Debug port trong container lộ công cộng | Dùng `-p 5005:5005` hoặc service/ingress công khai | Publish `127.0.0.1:5005:5005`, dùng port-forward/tunnel, tắt sau khi xong |
| Một breakpoint mã nguồn màu xám hoặc bị bỏ qua | Source/bytecode không khớp, class chưa load, branch chưa chạy | Rebuild, chọn đúng module, gửi request đúng endpoint |
| Breakpoint bị mất sau restart của DevTools | Classloader được tái tạo, IDE/source mappings thay đổi | Kiểm tra reload, đặt lại breakpoint, thử tắt DevTools restart để khoanh vùng |
| Client HTTP timeout khi debug | Thread request đang bị breakpoint suspend | Resume thread, tăng timeout ở dev client khi cần |
| Đổi code rồi HotSwap báo fail | JVM/IDE không hỗ trợ thay đổi cấu trúc class | Restart app với artifact mới |
| `curl` tới `/calc` trả 404 | Sai endpoint, context path, port HTTP, app không chạy đúng build | Dùng đúng `/calc?a=2&b=3` và kiểm tra Spring logs |
| IDE attach được nhưng sai instance trên Kubernetes | Port-forward chọn pod khác với pod phục vụ request | Port-forward đúng pod, hướng request tới instance đó để tái hiện |

### Phép kiểm tra trên Windows và Linux/macOS

**Trên Windows PowerShell:**

```powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen
```

**Trên Linux:**

```bash
ss -lntp | grep 5005
```

Hai lệnh trên chỉ giúp kiểm tra **máy đang chạy lệnh đó** có socket LISTEN hay không. Nếu JVM ở Docker hoặc pod, phải kiểm tra đúng network namespace và cả host binding/tunnel. Không có listener 5005 trên máy host không tự chứng minh container chưa bật JDWP nếu chưa publish port.

Kiểm tra JVM đang dùng trong terminal:

```bash
java -version
```

Khi nghi source không khớp runtime, kiểm tra phiên bản artifact đã build, PID thực sự được start và terminal/container logs. Đừng attach ngẫu nhiên vào một port 5005 có sẵn mà không xác nhận nó thuộc đúng dịch vụ.

## 13. Lỗi thiết kế thường thấy khi triển khai chức năng remote debug

### Nhầm debug JVM với debug logging

Spring Boot `--debug` chỉ tăng thông tin chẩn đoán Spring Boot; Gradle `--debug` tăng verbosity Gradle; JDWP đòi debug agent trong JVM application. Tên giống nhau không có nghĩa chúng thực hiện cùng hành vi.

### Bật JDWP mặc định cho mọi môi trường

Cấu hình `JAVA_TOOL_OPTIONS` ở image chung, Helm chart production hoặc shell profile có thể làm mọi JVM bật cổng debug khi startup, kể cả batch job, Gradle daemon hoặc các replica. Nên áp dụng debug option chỉ ở **lần khởi chạy phát triển cụ thể**, và tắt ngay khi kết thúc. Chú ý các deployment dùng cùng image: image có thể giữ nguyên, còn environment runtime mới quyết định có bật agent hay không.

### Debug port mở mọi interface mà không bảo vệ đường mạng

`address=*:5005` có thể cần bên trong container, nhưng nếu Docker publish toàn host hoặc Kubernetes Service công khai, bất kỳ người nào có thể kết nối tới JDWP đều có quyền can thiệp rất sâu. Bảo vệ bằng loopback, SSH tunnel, Kubernetes port-forward nội bộ, firewall/RBAC và quyền truy cập tối thiểu. **JDWP không nên được coi là một API ứng dụng có cơ chế auth riêng**.

### Giữ `suspend=y` trên CI/production

Nếu không có debugger kết nối, ứng dụng chờ mãi và health check có thể fail, kéo theo restart loop. Chỉ bật suspend khi muốn bắt startup, không duy trì nó như cấu hình bình thường.

### Source và bytecode khác nhau

Khi dùng remote debugger qua Docker/VM, IDE có thể hiển thị checkout hiện tại trong khi JVM chạy artifact từ commit trước. Breakpoint khó hit hoặc line mapping lệch. Tái tạo image đúng source revision, xác định tên/timestamp artifact và build với debug symbols (Java compiler mặc định thường tạo thông tin cần thiết; kiểm tra cấu hình custom compiler/minification nếu đã thay đổi).

### Kỳ vọng debugger sửa cấu hình runtime

Attaching JDWP **không tự sửa** Spring properties, environment, bean wiring hay network routing. Debugger giúp quan sát vấn đề; thay đổi application configuration thường cần restart hoặc cơ chế reload cụ thể. Không dùng Evaluate Expression để làm thay đổi dữ liệu thực tế ngoài phiên debug được cho phép.

## 14. Checklist thao tác từ đầu tới cuối

1. **Chọn đúng JVM:** ứng dụng sẽ chạy qua `java -jar`, Gradle `bootRun`, Maven `spring-boot:run`, Docker hay Kubernetes?
2. **Xác định JVM/JDK:** Java 17+, source revision và artifact đang chạy; đảm bảo IDE có source phù hợp.
3. **Chọn suspend:** `y` để bắt startup; `n` để debug request khi app đã sẵn sàng.
4. **Chọn bind/port:** local VM `127.0.0.1:5005`; container có thể dùng `*:5005` bên trong, nhưng chỉ publish về loopback/tunnel.
5. **Khởi động với JDWP agent:** qua `-agentlib:jdwp`, `bootRun --debug-jvm`, Gradle `debugOptions` hoặc Maven `spring-boot.run.jvmArguments`.
6. **Attach IDE:** Remote JVM Debug (IntelliJ) hoặc `request: attach` (VS Code), host/port đúng.
7. **Đặt breakpoint và tái hiện:** gọi `curl 'http://localhost:8080/calc?a=2&b=3'`, xem `a=2`, `b=3`, `result=5`.
8. **Phân tích:** quan sát call stack, thread, exception, biểu thức; phân biệt tác động timeout khi debugger đang suspend.
9. **Kết thúc:** resume hoặc stop JVM, gỡ cổng forward, bỏ biến debug và kiểm tra deployment kế tiếp không mở JDWP.

## 15. Tài liệu chính thức

- Oracle Java 17 – [JPDA Connection and Invocation Details](https://docs.oracle.com/en/java/javase/17/docs/specs/jpda/conninv.html): `-agentlib:jdwp`, transport, `server`, `suspend` và `address`.
- Gradle – [JavaExec API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html): `--debug-jvm` và `debugOptions`.
- Gradle – [JavaDebugOptions API](https://docs.gradle.org/current/javadoc/org/gradle/process/JavaDebugOptions.html): `enabled`, `host`, `port`, `server` và `suspend`.
- Gradle – [Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): phân biệt gỡ lỗi Gradle daemon.
- Spring Boot – [Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): task `bootRun` dựa trên `JavaExec`.
- Spring Boot – [Running Your Application with Maven](https://docs.spring.io/spring-boot/maven-plugin/run.html): `spring-boot.run.jvmArguments` cho forked JVM.
- IntelliJ IDEA – [Attach to Process / Remote JVM Debug](https://www.jetbrains.com/help/idea/attach-to-process.html): các bước cấu hình attach debugger.
- VS Code – [Java Debugging](https://code.visualstudio.com/docs/java/java-debugging): `launch.json` và `request: attach`.
- Kubernetes – [kubectl port-forward](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/): forward cổng tới pod qua kết nối Kubernetes.
- Docker – [Publishing and Exposing Ports](https://docs.docker.com/get-started/docker-concepts/running-containers/publishing-ports/): ý nghĩa host binding khi publish debug port.

**Điểm phải ghi nhớ:** remote debugging cấu hình trên **JVM đang thực sự chạy ứng dụng**. `bootRun --debug-jvm` và Maven `spring-boot.run.jvmArguments` hướng vào JVM Spring Boot; `-Dorg.gradle.debug=true` lại hướng vào Gradle daemon. Đặt JDWP chỉ trên loopback khi có thể, dùng tunnel có kiểm soát khi ở xa, xác minh source/bytecode trùng nhau và tắt agent sau phiên debug.