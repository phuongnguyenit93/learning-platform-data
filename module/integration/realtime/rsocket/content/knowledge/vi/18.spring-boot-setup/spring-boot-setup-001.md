# Chuẩn bị Java 21, Gradle và spring-boot-starter-rsocket

Để bắt đầu một ứng dụng RSocket với Spring Boot, cần chuẩn bị JDK 21, Gradle Wrapper và dependency `spring-boot-starter-rsocket`. JDK cung cấp trình biên dịch và runtime Java; Gradle quản lý build, dependency và test; Spring Boot starter đưa các thành phần Spring Messaging và RSocket cần thiết vào ứng dụng.

Trong module này, Java 21 là phiên bản nền để biên dịch và chạy ví dụ. Gradle Wrapper giúp mọi thành viên dùng cùng phiên bản Gradle mà không phụ thuộc vào Gradle cài toàn cục. Spring Boot quản lý phiên bản các thư viện RSocket tương thích thông qua dependency management, vì vậy thông thường không cần tự ghim riêng từng phiên bản `rsocket-core`, Netty hoặc Reactor.

## 1. Chuẩn bị JDK 21

Cài **JDK 21** từ một bản phân phối OpenJDK phù hợp với hệ điều hành, ví dụ Eclipse Temurin, Oracle JDK hoặc Amazon Corretto. Cần cài JDK thay vì chỉ có JRE vì Gradle phải gọi `javac` để biên dịch mã nguồn.

Sau khi cài đặt, mở terminal mới và kiểm tra:

```bash
java -version
javac -version
```

Kết quả cần thể hiện phiên bản major là `21`, ví dụ:

```text
openjdk version "21.0.x" ...
javac 21.0.x
```

Nếu hai lệnh không tìm thấy hoặc hiển thị phiên bản khác, hãy kiểm tra biến môi trường:

- `JAVA_HOME` trỏ tới thư mục gốc của JDK 21, không trỏ vào thư mục `bin`.
- `PATH` có mục `%JAVA_HOME%\bin` trên Windows hoặc `$JAVA_HOME/bin` trên Linux/macOS.
- Nếu máy có nhiều JDK, kiểm tra thứ tự các mục trong `PATH` và cấu hình Java runtime của IDE.

Trên PowerShell, có thể kiểm tra đường dẫn đang được sử dụng:

```powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
```

`java -version` cho biết runtime được shell tìm thấy. Gradle daemon và IDE có thể dùng một JDK khác, vì vậy cần kiểm tra thêm sau khi tạo wrapper.

## 2. Chuẩn bị Gradle và Gradle Wrapper

Gradle là hệ thống build của dự án. Với Java 21, cần Gradle **8.5 trở lên** nếu chạy chính Gradle bằng JDK 21. Có thể dùng Gradle 8.14.3 làm baseline minh họa trong bài này; khi dự án có quy định phiên bản riêng, hãy theo phiên bản được nhóm quản lý.

Ưu tiên **Gradle Wrapper** (`gradlew` trên Linux/macOS và `gradlew.bat` trên Windows). Wrapper tải đúng phiên bản Gradle đã khai báo trong repository, nhờ đó CI và máy lập trình viên có môi trường build nhất quán.

Nếu đã cài Gradle toàn cục, tạo wrapper từ thư mục dự án:

```bash
gradle wrapper --gradle-version 8.14.3
```

Lệnh tạo các file wrapper, thường gồm:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

Nếu chưa có Gradle toàn cục, có thể tạo project Gradle từ Spring Initializr và chọn Java 21, Gradle Kotlin DSL; Initializr sẽ tạo wrapper sẵn. Sau khi wrapper đã tồn tại, dùng wrapper cho tất cả lệnh build thay vì gọi `gradle` trực tiếp.

Kiểm tra phiên bản và JVM mà wrapper sử dụng:

```bash
./gradlew --version
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
```

Trong phần JVM của kết quả, xác nhận Gradle đang chạy bằng JDK 21. Nếu không đúng, kiểm tra `JAVA_HOME`, cấu hình Gradle JVM trong IDE và các daemon Gradle đang hoạt động. Có thể dừng daemon cũ rồi chạy lại:

```bash
./gradlew --stop
./gradlew --version
```

## 3. Tạo cấu trúc project Gradle

Một project Spring Boot tối thiểu có thể tổ chức như sau:

```text
rsocket-demo/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   ├── main/
│   │   ├── java/com/example/rsocket/
│   │   │   ├── RSocketApplication.java
│   │   │   └── GreetingController.java
│   │   └── resources/
│   │       └── application.yml
│   └── test/java/com/example/rsocket/
├── build.gradle.kts
├── settings.gradle.kts
├── gradlew
└── gradlew.bat
```

Đặt tên project trong `settings.gradle.kts`:

```kotlin
rootProject.name = "rsocket-demo"
```

Tên project được Gradle dùng để định danh build và thường xuất hiện trong tên artifact nếu không cấu hình tên khác.

## 4. Khai báo Java 21 và Spring Boot plugin

Ví dụ `build.gradle.kts` dùng Kotlin DSL:

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
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-rsocket")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

Các phiên bản plugin trong đoạn mã là một baseline minh họa tương thích với Java 21. Với dự án thực tế, hãy thay bằng bản Spring Boot 3.x patch đang được tổ chức hỗ trợ và giữ phiên bản plugin Spring Boot cùng dependency management nhất quán. Nếu dự án đã có version catalog hoặc convention plugin, hãy khai báo dependency theo cơ chế sẵn có thay vì tạo thêm một nguồn quản lý phiên bản.

Giải thích các phần chính:

- `java`: bật các task biên dịch, test và đóng gói Java.
- `org.springframework.boot`: cung cấp task như `bootRun` và `bootJar`.
- `io.spring.dependency-management`: nhập BOM của Spring Boot để quản lý phiên bản dependency.
- `java.toolchain`: yêu cầu Gradle biên dịch bằng JDK 21, kể cả khi JVM chạy Gradle được chọn riêng.
- `mavenCentral()`: repository lấy plugin/dependency đã được khai báo trong build.
- `useJUnitPlatform()`: chạy test dùng JUnit Jupiter, là nền tảng test mặc định của Spring Boot starter test.

Nếu dùng Gradle Kotlin DSL, tên file phải là `build.gradle.kts`. Với Groovy DSL, dùng `build.gradle` và cú pháp dependency tương ứng; không trộn hai cú pháp trong cùng một file.

## 5. Thêm spring-boot-starter-rsocket

Dependency cốt lõi của bài học là:

```kotlin
implementation("org.springframework.boot:spring-boot-starter-rsocket")
```

Starter này đưa hạ tầng Spring RSocket vào ứng dụng và để Spring Boot quản lý các dependency tương thích theo BOM của phiên bản Spring Boot đã chọn. Các API quan trọng mà ứng dụng thường dùng gồm:

| Thành phần | Vai trò |
|---|---|
| `RSocketRequester` | API phía client để tạo request và nhận response theo kiểu reactive |
| `@MessageMapping` | Ánh xạ route RSocket tới handler phía server |
| `RSocketStrategies` | Cấu hình encoder, decoder và xử lý metadata |
| RSocket transport | Kết nối qua TCP hoặc WebSocket, tùy cấu hình |
| Reactor `Mono` / `Flux` | Biểu diễn kết quả đơn hoặc luồng dữ liệu bất đồng bộ |

Không cần khai báo thủ công các dependency lõi như `rsocket-core`, `rsocket-transport-netty` hoặc các phiên bản Netty riêng trong ví dụ cơ bản. Tự thêm phiên bản có thể làm lệch dependency graph mà Spring Boot đã kiểm thử. Chỉ thêm dependency cấp thấp khi có yêu cầu kỹ thuật rõ ràng và kiểm tra tương thích với BOM đang dùng.

Hai dependency test có vai trò khác nhau:

- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Test và các thư viện kiểm thử ứng dụng.
- `reactor-test` cung cấp `StepVerifier` để kiểm tra tín hiệu `Mono`/`Flux`, thời gian và luồng reactive.

## 6. Cấu hình Gradle Wrapper

Mở `gradle/wrapper/gradle-wrapper.properties` và kiểm tra URL phân phối Gradle. Với baseline của ví dụ:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

Wrapper tải Gradle vào cache người dùng ở lần chạy đầu. Vì vậy, lần chạy đầu tiên cần có kết nối tới máy chủ phân phối Gradle hoặc cache đã có sẵn. Trong CI, nên cache thư mục Gradle phù hợp để giảm thời gian tải, nhưng vẫn chạy bằng wrapper của repository.

Các file wrapper nên được commit cùng mã nguồn. Không commit thư mục `.gradle/` hoặc `build/`, vì đó là cache và output sinh ra trong quá trình build.

## 7. Tạo ứng dụng Spring Boot tối thiểu

Tạo file `RSocketApplication.java`:

```java
package com.example.rsocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(RSocketApplication.class, args);
    }
}
```

Thêm handler đơn giản trong `GreetingController.java`:

```java
package com.example.rsocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class GreetingController {

    @MessageMapping("greeting")
    public Mono<String> greet(String name) {
        return Mono.just("Xin chào " + name);
    }
}
```

`@MessageMapping("greeting")` khai báo route ở tầng RSocket metadata. Handler trả về `Mono` để biểu diễn một kết quả reactive. Route này độc lập với địa chỉ TCP port hoặc WebSocket mapping path.

## 8. Cấu hình RSocket server qua TCP

Để chạy server RSocket độc lập qua TCP, thêm `src/main/resources/application.yml`:

```yaml
spring:
  rsocket:
    server:
      transport: tcp
      address: 0.0.0.0
      port: 7000
```

Trong cấu hình này:

- `transport: tcp` chọn transport TCP.
- `address: 0.0.0.0` cho phép server lắng nghe trên các giao diện IPv4.
- `port: 7000` là cổng TCP của RSocket server.

Client kết nối từ cùng máy có thể dùng `localhost:7000`. Khi chạy trong container hoặc từ máy khác, hãy thay `localhost` bằng DNS hoặc IP có thể truy cập từ môi trường client. Không dùng `0.0.0.0` làm địa chỉ đích phía client.

## 9. Chọn WebSocket khi cần tích hợp trình duyệt

Nếu client là ứng dụng web chạy trong trình duyệt, WebSocket thường là lựa chọn phù hợp. Khi đó RSocket endpoint được gắn vào embedded web server của Spring Boot:

```yaml
server:
  address: 0.0.0.0
  port: 8080

spring:
  rsocket:
    server:
      transport: websocket
      mapping-path: /rsocket
```

Client kết nối tới URL như `ws://localhost:8080/rsocket` trong môi trường phát triển. Khi triển khai TLS, dùng `wss://` và cấu hình chứng chỉ ở web server hoặc reverse proxy. Với WebSocket, `server.port` là cổng HTTP/WebSocket; `mapping-path` là đường dẫn handshake. `spring.rsocket.server.port` được dùng cho transport TCP, không phải cổng HTTP của WebSocket endpoint.

Đừng nhầm ba giá trị:

| Giá trị | Ví dụ | Tầng |
|---|---|---|
| TCP port | `7000` | Transport TCP |
| Web server port | `8080` | HTTP/WebSocket |
| RSocket route | `greeting` | Metadata của từng request |

Chọn một transport phù hợp với cách triển khai. Không cần bật TCP và WebSocket trên cùng một server chỉ để có thể dùng cả hai kiểu tương tác RSocket; transport là cách mang frame, còn request-response, stream và channel thuộc giao thức RSocket.

## 10. Kết nối client bằng RSocketRequester

Một ứng dụng client Spring có thể tạo requester qua TCP:

```java
import org.springframework.util.MimeTypeUtils;

RSocketRequester.builder()
    .dataMimeType(MimeTypeUtils.TEXT_PLAIN)
    .tcp("localhost", 7000)
    .flatMap(requester -> requester
        .route("greeting")
        .data("Lan")
        .retrieveMono(String.class));
```

`dataMimeType(MimeTypeUtils.TEXT_PLAIN)` khai báo rằng data trong ví dụ được mã hóa dưới dạng văn bản; handler server nhận `String` tương ứng. `tcp(...)` trả về `Mono<RSocketRequester>` vì việc kết nối diễn ra bất đồng bộ. Sau khi có requester, client chọn route, gửi data và khai báo kiểu response mong đợi. Với WebSocket, dùng phương thức `websocket(URI)` và URL khớp với `mapping-path` trên server.

Trong ứng dụng dài hạn, nên quản lý requester như một tài nguyên dùng chung và xử lý lifecycle/đóng kết nối rõ ràng. Không tạo kết nối TCP mới cho từng request nếu nhiều request có thể multiplex trên một kết nối RSocket.

## 11. Kiểm tra dependency và build

Sau khi khai báo build script, chạy các lệnh từ thư mục gốc project:

```bash
./gradlew clean test
./gradlew bootRun
./gradlew bootJar
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat bootRun
.\gradlew.bat bootJar
```

Ý nghĩa:

- `clean test`: xóa output cũ và chạy test.
- `bootRun`: chạy ứng dụng Spring Boot trong môi trường phát triển.
- `bootJar`: đóng gói executable JAR có dependency cần thiết.

Kiểm tra dependency graph nếu cần xác nhận starter đã được tải:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency rsocket-core --configuration runtimeClasspath
```

Nếu build thành công, có thể chạy JAR trong `build/libs/`:

```bash
java -jar build/libs/rsocket-demo-0.0.1-SNAPSHOT.jar
```

Tên file thực tế phụ thuộc `rootProject.name`, `version` và cấu hình archive của dự án.

## 12. Xử lý lỗi chuẩn bị môi trường

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `JAVA_HOME is not set` | Chưa cấu hình biến môi trường | Đặt `JAVA_HOME` tới thư mục JDK 21 và mở terminal mới |
| `Unsupported class file major version` | JVM/Gradle/plugin không tương thích với bytecode đang dùng | Kiểm tra Gradle runtime, toolchain và phiên bản plugin |
| Gradle chạy bằng JDK cũ | Daemon hoặc IDE đang chọn JDK khác | Kiểm tra `./gradlew --version`, IDE Gradle JVM và chạy `./gradlew --stop` |
| Không tải được dependency | Mạng, proxy, DNS hoặc Maven Central bị chặn | Kiểm tra kết nối, proxy và cấu hình repository của tổ chức |
| Không tìm thấy `spring-boot-starter-rsocket` | Sai group/artifact hoặc repository | Dùng đúng tọa độ `org.springframework.boot:spring-boot-starter-rsocket` và `mavenCentral()` |
| Không có task `bootRun` | Chưa áp dụng Spring Boot Gradle plugin | Kiểm tra block `plugins` và đồng bộ Gradle project |
| Port đã được sử dụng | Ứng dụng khác đang lắng nghe cổng đã chọn | Đổi port hoặc dừng tiến trình đang sử dụng cổng đó |
| Client không kết nối được | Sai transport, host, port hoặc WebSocket path | Đối chiếu cấu hình server và địa chỉ client theo đúng transport |

Khi đổi JDK hoặc phiên bản Gradle, hãy đồng bộ lại project trong IDE. Không cần xóa cache Gradle ngay khi gặp lỗi; trước hết đọc thông báo lỗi và xác định đó là lỗi JVM, dependency resolution, compile hay runtime.

## 13. Checklist trước khi bắt đầu bài RSocket

- [ ] `java -version` và `javac -version` đều hiển thị JDK 21.
- [ ] `JAVA_HOME` trỏ đúng thư mục gốc JDK 21.
- [ ] Gradle Wrapper có trong repository và dùng phiên bản tương thích với Java 21.
- [ ] `./gradlew --version` hiển thị JVM 21 theo cấu hình mong muốn.
- [ ] Gradle toolchain đặt `JavaLanguageVersion.of(21)`.
- [ ] Spring Boot plugin và dependency management dùng phiên bản tương thích.
- [ ] `spring-boot-starter-rsocket` được khai báo trong `implementation`.
- [ ] Dependency test có `spring-boot-starter-test` và `reactor-test`.
- [ ] Server chọn TCP hoặc WebSocket với địa chỉ/cổng/path phù hợp.
- [ ] `./gradlew clean test` chạy thành công trước khi phát triển tiếp.

Khi JDK, Gradle Wrapper và starter đã thống nhất, dự án có nền tảng để xây dựng RSocket client/server bằng Spring Boot. Giữ phiên bản dependency dưới sự quản lý của Spring Boot BOM, kiểm tra đúng JVM của Gradle và chọn transport ngay trong cấu hình sẽ giúp các ví dụ tiếp theo chạy nhất quán trên máy cá nhân và CI.

## Tài liệu tham khảo

- [Spring Boot — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html)
- [Spring Boot Gradle Plugin](https://docs.spring.io/spring-boot/gradle-plugin/index.html)
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html)
- [Gradle — Compatibility with Java](https://docs.gradle.org/current/userguide/compatibility.html)
- [Spring Initializr](https://start.spring.io/)
