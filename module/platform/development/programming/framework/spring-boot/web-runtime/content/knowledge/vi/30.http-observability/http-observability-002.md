# Cấu hình access log theo Tomcat, Jetty, Undertow hoặc Reactor Netty trong Spring Boot

## 1. Access log là gì và vì sao cần cấu hình theo HTTP server?

Khi HTTP request đi qua Spring Boot, một developer có thể nhìn thấy `log.info(...)` trong service, exception stack trace, Micrometer metrics hoặc access log. Các nguồn này **không giống nhau**. **HTTP access log** là bản ghi ở tầng HTTP server, thường mô tả phương thức, URL, thời điểm, client IP, mã trạng thái, số byte và thời lượng request. Nó có thể xuất hiện ngay cả khi controller **không tự gọi logger**.

Ví dụ dòng theo Common Log Format, số liệu và thời gian **chỉ minh họa**:

~~~text
127.0.0.1 - - [08/Nov/2026:09:00:01 +0700] "GET /ping HTTP/1.1" 200 15
127.0.0.1 - - [08/Nov/2026:09:00:02 +0700] "GET /missing HTTP/1.1" 404 88
~~~

Từ hai dòng này có thể quan sát request GET `/ping` thành công và `/missing` trả 404. Nhưng không thể kết luận nguyên nhân nghiệp vụ của lỗi 404, thời gian SQL query hoặc identity đã qua MFA chỉ từ access log.

Spring Boot có thể dùng nhiều embedded web servers. **Không có một namespace cấu hình access log chung cho mọi server**:

| Embedded server | Spring Boot web stack điển hình | Cách bật access log |
| --- | --- | --- |
| Tomcat | Spring MVC/Servlet mặc định | `server.tomcat.accesslog.enabled=true` |
| Jetty | Spring MVC/Servlet khi đổi dependency | `server.jetty.accesslog.enabled=true` |
| Undertow | Spring MVC/Servlet khi đổi dependency | `server.undertow.accesslog.enabled=true` |
| Reactor Netty | Spring WebFlux/reactive mặc định | **JVM** `-Dreactor.netty.http.server.accessLogEnabled=true` hoặc `HttpServer.accessLog(true)` |

Bài sử dụng Spring Boot **3.3.x, Java 17+** làm phạm vi phiên bản. Giá trị property, behavior và library packages có thể thay đổi khi sang major version khác; luôn kiểm tra tài liệu ứng với phiên bản trong dự án.

Mục tiêu: chọn server đúng, bật logs đúng chỗ, hiểu format/đơn vị latency, biết logs ra file hay stderr, xử lý proxy/client IP và privacy, kiểm thử HTTP thật, đồng thời phân biệt access log với tracing, business audit và debug wiretap.

## 2. Quan sát một HTTP request ở nhiều tầng

~~~text
Browser / Mobile / API client
      |
      v
CDN / Load balancer / API gateway / Reverse proxy
      |  Edge access log: client IP bên ngoài, cache, WAF,
      |                   TLS, edge status, upstream latency
      v
Tomcat / Jetty / Undertow / Reactor Netty
      |  Server access log: method, path, status, bytes, time
      v
Spring MVC DispatcherServlet / WebFlux Handler
      |  Application logs: validation, errors, domain context
      v
Service / Database / Downstream APIs
      |  Micrometer metrics and distributed trace spans
      v
HTTP response
~~~

| Nguồn | Nên dùng để trả lời | Không trả lời đầy đủ |
| --- | --- | --- |
| Proxy/CDN access log | Request có đến edge? cache HIT/MISS? 502/504 do gateway? | Code Spring controller đã xử lý nghiệp vụ nào |
| Embedded server access log | Request nào đến HTTP listener, status/size/duration | Logic domain/DB lỗi ở bước nào |
| Application logs | Exceptions, business events, validation | Mọi 404/static resource khi code không chủ động log |
| Micrometer HTTP metrics | Throughput, duration percentiles, route/status aggregates | Từng request với đầy đủ thông tin forensic |
| Distributed traces | Latency qua các service, trace/span correlation | Complete audit nếu bị sampling hoặc thiếu instrumentation |
| Business/security audit | Actor, action, resource, permission, outcome | HTTP byte counts và transport behavior nếu không ghi |

**Một request bị WAF từ chối sẽ không nhất thiết có log ở Spring.** Một access line HTTP 200 cũng không bảo đảm business operation thành công. Đừng dùng số dòng access log làm số giao dịch/người dùng duy nhất vì retry, redirects, browser assets, preflight và proxy hops có thể tạo nhiều requests.

## 3. Trước khi bật logs, hãy xác định embedded server thật

### Spring MVC

Dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
~~~

mặc định mang theo **Tomcat embedded** trong Boot 3.x. Nếu thêm `server.jetty.accesslog.enabled=true` mà vẫn dùng Tomcat, property Jetty không điều khiển Tomcat.

Để dùng **Jetty thay Tomcat**, chọn một trong các cấu hình dependencies:

~~~groovy
implementation('org.springframework.boot:spring-boot-starter-web') {
    exclude group: 'org.springframework.boot',
            module: 'spring-boot-starter-tomcat'
}
implementation 'org.springframework.boot:spring-boot-starter-jetty'
~~~

Để dùng **Undertow thay Tomcat**:

~~~groovy
implementation('org.springframework.boot:spring-boot-starter-web') {
    exclude group: 'org.springframework.boot',
            module: 'spring-boot-starter-tomcat'
}
implementation 'org.springframework.boot:spring-boot-starter-undertow'
~~~

**Hai lựa chọn này là thay thế, không sử dụng đồng thời**. Giữ versions Boot-managed cho Jetty/Undertow thay vì tự ép dependency cũ không tương thích Jakarta Servlet.

### Spring WebFlux

Dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

thường cho Spring WebFlux chạy trên **Reactor Netty**. Nếu có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot 3.x thường chọn **Servlet MVC**. Vì thế thêm WebFlux chỉ để dùng `WebClient` **không** tự đổi incoming HTTP server sang Netty.

Một process có thể dùng Tomcat làm server và Reactor Netty làm HTTP client. HTTP server access log của Reactor Netty **không tự log WebClient outbound calls**. Muốn quan sát outbound requests, dùng client observations/tracing hoặc cấu hình client logging riêng.

Cách kiểm chứng server: xem dependency tree, startup message, application context type và HTTP integration test; không chỉ dựa tên property trong `application.properties`.

## 4. Dự án Servlet mẫu dùng chung để thử ba server

Tạo một Spring Boot 3.3.13 / Java 17 project. Mã nguồn HTTP giữ nguyên khi đổi Tomcat/Jetty/Undertow; chỉ đổi dependency và server properties.

### 4.1. File tree

~~~text
servlet-access-logging/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/http/ServletAccessApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/http/ServletAccessTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'servlet-access-logging'
~~~

`build.gradle`, Tomcat mặc định:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`src/main/java/demo/http/ServletAccessApplication.java` — **một file Java runnable**:

~~~java
package demo.http;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletAccessApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServletAccessApplication.class, args);
    }
}

@RestController
class ProbeController {

    @GetMapping("/ping")
    Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/bad")
    ResponseEntity<Map<String, String>> bad() {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid-demo-request"));
    }

    @GetMapping("/slow")
    Map<String, String> slow() throws InterruptedException {
        // CHỈ LAB: cố ý làm chậm request 80 ms.
        // Không dùng Thread.sleep trên request thread ở production.
        Thread.sleep(80L);
        return Map.of("status", "slow-ok");
    }
}
~~~

Một public class `ServletAccessApplication` và một package-private controller là hợp lệ trong Java 17. `spring-boot-starter-web` có Jackson để serialize `Map` thành JSON. Không có authentication trong lab; production cần Spring Security/authorization riêng.

### 4.2. Thử HTTP sau khi bật server

Tất cả cấu hình server ở các mục kế tiếp dùng:

~~~properties
server.port=8080
~~~

Chạy với Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper, tạo từ Gradle tương thích hoặc dùng `gradle bootRun` đã cài.

Gọi:

~~~bash
curl -i http://localhost:8080/ping
curl -i http://localhost:8080/bad
curl -i http://localhost:8080/missing
curl -i http://localhost:8080/slow
~~~

Kỳ vọng status lần lượt **200, 400, 404, 200**. Body logic của `/ping`:

~~~json
{"status":"ok"}
~~~

Và `/bad`:

~~~json
{"error":"invalid-demo-request"}
~~~

Response headers, body 404, thời gian thực và log fields phụ thuộc server/hệ điều hành. **Mục tiêu là kiểm tra access records cho nhiều loại status**, không so khớp nguyên văn một dòng log minh họa với timestamp ngẫu nhiên.

## 5. Tomcat: AccessLogValve, directory và pattern

Tomcat access logging mặc định **tắt**. Trong `application.properties` của **Servlet lab đang dùng Tomcat**, cấu hình:

~~~properties
server.port=8080

server.tomcat.basedir=./runtime/tomcat
server.tomcat.accesslog.enabled=true
server.tomcat.accesslog.directory=logs
server.tomcat.accesslog.prefix=access_log
server.tomcat.accesslog.suffix=.log
server.tomcat.accesslog.rotate=true
server.tomcat.accesslog.max-days=14

# Method + path không chứa query + protocol + status + bytes + duration
server.tomcat.accesslog.pattern=%t %a "%m %U %H" %s %b %D
~~~

**Vị trí file:** tương đối với working directory, thường theo dạng:

~~~text
runtime/tomcat/logs/access_log.<yyyy-MM-dd>.log
~~~

Vì đã đặt `server.tomcat.basedir=./runtime/tomcat`, Tomcat không phải lấy base từ temporary directory. Theo tài liệu Boot, nếu không cố định base dir hoặc directory absolute, Tomcat embedded có thể lưu access logs dưới **thư mục tạm**, khiến developer không tìm thấy ở `./logs`.

### 5.1. Token Tomcat cần nhớ

| Token | Ý nghĩa |
| --- | --- |
| `%t` | Request timestamp dạng common log |
| `%a` | Remote address theo Tomcat |
| `%h` | Remote hostname/IP |
| `%m` | HTTP method |
| `%U` | URL **path**, không gồm query |
| `%q` | Query string; có thể chứa token/PII |
| `%r` | Request line (có thể chứa full URL/query) |
| `%H` | HTTP protocol |
| `%s` | Response status |
| `%b` | Số bytes gửi; giá trị gạch nếu không có bytes |
| `%B` | Số bytes dạng số |
| `%D` | Duration **microseconds** trên Tomcat 10.1 |
| `%T` | Duration **seconds** |
| `%{ms}T` | Duration **milliseconds** rõ đơn vị |
| `%{X-Request-ID}o` | Value response header X-Request-ID nếu được phát |

Ví dụ dòng minh họa:

~~~text
[08/Nov/2026:09:12:00 +0700] 127.0.0.1 "GET /slow HTTP/1.1" 200 20 85100
~~~

`85100` ở cột cuối là **85.100 microseconds = 85.1 milliseconds**, không phải 85.1 giây. Giá trị không cố định, vì nó bao gồm thêm chi phí xử lý HTTP ngoài `Thread.sleep(80L)` trong lab.

### 5.2. Buffered output, rotation, retention

- `server.tomcat.accesslog.buffered` mặc định true: dòng log có thể **chưa flush ngay** khi cURL hoàn thành.
- `file-date-format` mặc định thêm ngày vào file name; rotate và prefix/suffix được cấu hình riêng.
- `max-days=14` là một ví dụ retention; mặc định `-1` không giới hạn số ngày theo property này.
- `check-exists` giúp một số kịch bản external log rotation/rename; cần chọn một owner rotation và kiểm tra thực tế.
- `logging.file.name` điều khiển logging framework thông thường, **không thay** nơi ghi file native Tomcat AccessLogValve.

### 5.3. IP thật sau proxy

Nếu Spring Boot nằm sau NGINX/load balancer, `%a` có thể là IP proxy. Tomcat có RemoteIpValve và property:

~~~properties
# Chỉ dùng cùng một trusted proxy configuration có kiểm chứng:
server.forward-headers-strategy=native
server.tomcat.accesslog.request-attributes-enabled=true
~~~

Khi trust proxy đúng, AccessLogValve có thể dùng request attributes mà RemoteIpValve đặt. **Không nhận mọi X-Forwarded-For do client Internet khai** rồi xem là địa chỉ thật; gateway phải strip/overwrite untrusted forwarded headers, còn Tomcat cần đúng danh sách internal/trusted proxies.

### 5.4. Tomcat troubleshooting

- Có `logging.level.org.apache.catalina=DEBUG` nhưng không có access log: debug app/container logger **không bật AccessLogValve**.
- Không có file trong `./logs`: kiểm tra `server.tomcat.basedir` và relative directory.
- Log chưa xuất hiện ngay: kiểm tra buffered flush và file date rotation.
- Access duration cực lớn khi nhìn dashboard: `%D` Tomcat **microseconds**, cần đổi sang ms.
- Pattern `%r` làm lộ query string chứa reset token: dùng `%m %U` hoặc thiết kế route không chứa secret.
- Chạy app Jetty/Undertow nhưng đặt properties Tomcat: namespace không đúng server.

## 6. Jetty: RequestLog và System.err nếu không đặt filename

Muốn thử **Jetty**, trong `build.gradle` của Servlet lab thay block dependencies bằng:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Chạy lại build/bootRun để Jetty thực sự là embedded HTTP server.

### 6.1. Bật nhanh để xem ở stderr

~~~properties
server.port=8080
server.jetty.accesslog.enabled=true
~~~

Theo Spring Boot 3.3, nếu `server.jetty.accesslog.filename` **không được cấu hình**, access logs được gửi tới **`System.err`**, không có một file `logs/jetty-access.log` mặc định cho bạn đi tìm.

Điều này thường thuận tiện với Docker/Kubernetes thu thập console logs. Nhưng Jetty log ra System.err không đồng nghĩa nó là Java exception hoặc HTTP 500; đó là nơi output access log được gửi.

### 6.2. Cấu hình file + custom format

~~~properties
server.port=8080

server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=logs/jetty-access.log
server.jetty.accesslog.append=true
server.jetty.accesslog.retention-period=14

# Dựa trên org.eclipse.jetty.server.CustomRequestLog
server.jetty.accesslog.custom-format=%{client}a %t "%m %U %H" %s %{ms}T
~~~

Đảm bảo `logs/` có quyền ghi. Jetty Boot properties đáng nhớ:

| Property | Ý nghĩa |
| --- | --- |
| `server.jetty.accesslog.enabled` | Bật request log |
| `server.jetty.accesslog.filename` | File path; không đặt → System.err |
| `server.jetty.accesslog.format` | Format tích hợp, mặc định `ncsa` |
| `server.jetty.accesslog.custom-format` | Jetty CustomRequestLog format, **override format** |
| `server.jetty.accesslog.append` | Append file |
| `server.jetty.accesslog.file-date-format` | Date suffix khi log rotation |
| `server.jetty.accesslog.retention-period` | Retention ngày |
| `server.jetty.accesslog.ignore-paths` | Bỏ qua request paths theo cơ chế Jetty/Boot |

Jetty `CustomRequestLog` hỗ trợ `%m`, `%U`, `%s`, `%D` và `%{ms}T`; `%D` ở Jetty là **microseconds**, còn `%{ms}T` cho milliseconds. Dù pattern có nhiều token giống Tomcat, đừng sao chép tất cả syntax/time/date escaping giữa Jetty và Tomcat mà không kiểm tra.

### 6.3. Jetty khác Jetty standalone

Cấu hình `server.jetty.accesslog.*` này dành cho **embedded Jetty do Spring Boot quản lý**. Jetty standalone có cơ chế modules/JETTY_BASE và file format properties riêng. Không giả định bật module `requestlog` trong một phân phối Jetty standalone sẽ tự cấu hình một app embedded Boot.

Khi thấy `Jetty enabled=true` mà không có file, hãy xem console stderr trước, rồi check `filename` và permissions. Trong container, logs ghi file riêng cần file collector hoặc mounted volume.

## 7. Undertow: accesslog.dir và record-request-start-time

Muốn thử **Undertow**, trong Servlet lab thay block dependencies bằng:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-undertow'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

### 7.1. Bật access log cơ bản

~~~properties
server.port=8080

server.undertow.accesslog.enabled=true
server.undertow.accesslog.dir=logs/undertow
server.undertow.accesslog.pattern=common
server.undertow.accesslog.rotate=true
~~~

Theo Spring Boot 3.3, mặc định Undertow có thể ghi file dưới `logs` **tương đối working directory**, khác Tomcat basedir. Các property gồm `enabled`, `dir`, `pattern` (mặc định `common`), `prefix` (mặc định `access_log.`), `suffix` (mặc định `log`) và `rotate` (mặc định true).

Tomcat `max-days` và Jetty `retention-period` **không điều khiển** Undertow native log rotation. Xây policy retention theo hệ thống đang dùng và cấu hình collector/disk phù hợp.

### 7.2. Cấu hình đúng khi cần duration

Tài liệu Spring Boot hướng dẫn:

~~~properties
server.undertow.accesslog.enabled=true
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
~~~

**Lý do:** muốn dùng elapsed time `%D`, Undertow cần thu thập **request start time**. Bật option `record-request-start-time=true` có chi phí nhỏ nhưng cần thiết cho duration có ý nghĩa trong access logger.

Đặc biệt:

| Cột | Tomcat 10.1 | Jetty CustomRequestLog | Undertow (ví dụ Boot) |
| --- | --- | --- | --- |
| `%D` | **microseconds** | **microseconds** | **milliseconds** |
| Có cần extra option để đo %D? | Không theo cấu hình ví dụ | Không theo cấu hình ví dụ | **Có: record-request-start-time** |
| Cách lấy millis dễ đọc | `%{ms}T` | `%{ms}T` | `%D` |

Nếu lấy số 90000 từ Tomcat rồi gắn nhãn milliseconds, dashboard sẽ hiểu nhầm 90 ms thành 90 giây. Chuẩn hóa đơn vị trong pipeline ingestion.

### 7.3. Ví dụ dòng, không phải output cố định

~~~text
[08/Nov/2026:09:30:00 +0700] 127.0.0.1 GET /slow HTTP/1.1 200 (90 milliseconds)
~~~

Kết quả thực thay đổi theo request overhead, server formatting, timezone và client. Pattern chứa `%r` có thể đưa URL query vào logs: khi production có URL sensitive, chọn format/redaction phù hợp đúng version Undertow hoặc giảm raw URI logging ở layer có kiểm soát.

### 7.4. Undertow troubleshooting

- Có `server.tomcat.accesslog.*` nhưng embedded server là Undertow → không có kết quả.
- Quên `record-request-start-time=true` → `%D` thiếu/không đáng tin.
- Relative `dir` được hiểu từ working directory khác IDE → tìm sai file.
- File system read-only hoặc không mount volume → logs mất hoặc không ghi được.
- Đọc duration Undertow như microseconds của Tomcat → sai.
- Để pattern chứa raw query có PII → cần sửa data retention và route/log pattern.

## 8. Reactor Netty: access log của reactive HTTP server

Reactor Netty không dùng Servlet AccessLogValve, Jetty RequestLog hay Undertow AccessLogHandler. Spring Boot 3.x khi dùng WebFlux với Reactor Netty có hai cách bật:

1. **JVM system property**: `-Dreactor.netty.http.server.accessLogEnabled=true`.
2. **Programmatic**: `reactor.netty.http.server.HttpServer.accessLog(true)` qua `NettyReactiveWebServerFactory` customizer.

Mặc định Reactor Netty HTTP access log **tắt**.

### 8.1. System property là JVM option, không phải Boot application property

Ví dụ sau khi build JAR:

~~~bash
java -Dreactor.netty.http.server.accessLogEnabled=true \
  -jar build/libs/reactive-access-logging-1.0.0.jar
~~~

`-D...=true` cần đứng **trước `-jar`**. Đặt sau JAR thường thành application argument thay vì JVM system property.

**Không nhầm với:**

~~~properties
# KHÔNG phải Boot 3.3 accesslog namespace:
reactor.netty.http.server.accessLogEnabled=true
~~~

ở `application.properties`. Logging level `logging.level.reactor.netty.http.server.AccessLog=INFO` chỉ cho phép logger phát message nếu access logger đã được bật, **không tự kích hoạt generator**. Thêm `logging.level.reactor.netty=DEBUG` hoặc bật `wiretap` cũng không tương đương access log; wiretap có thể lộ headers/payload nhạy cảm.

### 8.2. Logger name

Reactor Netty dùng logger:

~~~text
reactor.netty.http.server.AccessLog
~~~

để phát HTTP access entries theo logging framework (SLF4J/Logback thường đi cùng Spring Boot). Nếu default appender ra console, có thể quan sát trực tiếp; muốn file riêng, dùng dedicated appender ở mục sau. Không đặt `server.tomcat.accesslog.directory` cho Reactor Netty rồi kỳ vọng có tác dụng.

## 9. WebFlux Reactor Netty: dự án Java 17+ chạy được

### 9.1. Cấu trúc

~~~text
reactive-access-logging/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/reactivelog/ReactiveAccessApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/demo/reactivelog/ReactiveAccessTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'reactive-access-logging'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootRun') {
    // JVM riêng chạy app nhận system property này.
    systemProperty 'reactor.netty.http.server.accessLogEnabled', 'true'
}
~~~

`application.properties`:

~~~properties
server.port=8082
logging.level.reactor.netty.http.server.AccessLog=INFO
~~~

Tệp `src/main/java/demo/reactivelog/ReactiveAccessApplication.java`:

~~~java
package demo.reactivelog;

import java.time.Duration;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveAccessApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveAccessApplication.class, args);
    }
}

@RestController
class ReactiveProbeController {

    @GetMapping("/ping")
    Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/bad")
    Mono<ResponseEntity<Map<String, String>>> bad() {
        return Mono.just(ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid-demo-request")));
    }

    @GetMapping("/slow")
    Mono<Map<String, String>> slow() {
        // Reactive timer: không Thread.sleep trên event loop.
        return Mono.delay(Duration.ofMillis(80))
                .map(ignored -> Map.of("status", "slow-ok"));
    }
}
~~~

**Một file Java runnable:** một public main class và một package-private controller. Chỉ có `spring-boot-starter-webflux`, nên Boot 3.3 dùng WebFlux trên Reactor Netty. Không thêm starter-web vào dự án này nếu muốn chắc server là Netty.

### 9.2. Chạy bằng bootRun

~~~bash
./gradlew bootRun
~~~

Block `tasks.named('bootRun')` đã đặt JVM system property. Truy cập:

~~~bash
curl -i http://localhost:8082/ping
curl -i http://localhost:8082/bad
curl -i http://localhost:8082/missing
curl -i http://localhost:8082/slow
~~~

Kỳ vọng status **200/400/404/200**. Reactor Netty access logger sẽ được kích hoạt trong JVM chạy app nếu không bị tắt/override bởi customizer và logging framework nhận logger ở INFO.

### 9.3. Chạy từ executable JAR

~~~bash
./gradlew bootJar

java -Dreactor.netty.http.server.accessLogEnabled=true -jar build/libs/reactive-access-logging-1.0.0.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootJar
java -Dreactor.netty.http.server.accessLogEnabled=true -jar .\build\libs\reactive-access-logging-1.0.0.jar
~~~

Tên JAR là ví dụ từ project name/version ở Gradle; nếu build artifact bị đổi tên, dùng file thực tế trong `build/libs`. Không dùng `./gradlew bootRun --args=...` để thay JVM system property vì `--args` là application args.

## 10. Reactor Netty: Logback file và cấu hình programmatic

### 10.1. Ghi access logger ra file riêng

Nếu không muốn access records xen vào application console, tạo `src/main/resources/logback-spring.xml` trong **project WebFlux**:

~~~xml
<configuration>
    <include resource="org/springframework/boot/logging/logback/defaults.xml"/>

    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <appender name="ACCESS_FILE"
              class="ch.qos.logback.core.rolling.RollingFileAppender">
        <file>logs/reactor-access.log</file>
        <rollingPolicy class="ch.qos.logback.core.rolling.TimeBasedRollingPolicy">
            <fileNamePattern>logs/reactor-access.%d{yyyy-MM-dd}.log</fileNamePattern>
            <maxHistory>7</maxHistory>
        </rollingPolicy>
        <encoder>
            <pattern>%msg%n</pattern>
        </encoder>
    </appender>

    <logger name="reactor.netty.http.server.AccessLog"
            level="INFO" additivity="false">
        <appender-ref ref="ACCESS_FILE"/>
    </logger>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

Access log message sẽ vào `logs/reactor-access.log` khi enabled. Application logs bình thường vẫn ra console. Cần permission ghi `logs` và rotation/shipper riêng. Trong container có collector stdout/stderr, file appender chỉ phù hợp nếu đã có volume/tailer; không mặc định tốt hơn console.

Tệp XML là ví dụ cho ứng dụng nhỏ; nếu tổ chức đã có `logback-spring.xml`/structured JSON/async appenders, **tích hợp riêng logger AccessLog vào cấu hình sẵn** thay vì thay toàn bộ file. Spring Boot `logging.file.name` đơn lẻ không bật Netty access logger.

### 10.2. Cấu hình bằng WebServerFactoryCustomizer

Thay vì system property, có thể bật bằng Java config của Spring Boot 3.3. Tệp `src/main/java/demo/reactivelog/NettyAccessConfig.java`:

~~~java
package demo.reactivelog;

import org.springframework.boot.web.embedded.netty.NettyReactiveWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class NettyAccessConfig {

    @Bean
    WebServerFactoryCustomizer<NettyReactiveWebServerFactory>
            nettyAccessLogCustomizer() {

        return factory -> factory.addServerCustomizers(
                server -> server.accessLog(true));
    }
}
~~~

`NettyReactiveWebServerFactory.addServerCustomizers` cho phép tùy chỉnh builder `reactor.netty.http.server.HttpServer`. `accessLog(true)` bật generator; **programmatic config có ưu tiên hơn system property**. Không kỳ vọng cả hai nguồn sẽ ghi hai bản log độc lập.

Khi dùng config Java này, có thể bỏ `bootRun.systemProperty` cho access log, giúp policy được quản lý bằng code.

### 10.3. Custom format và bỏ query khỏi URI

Một mẫu **thay phần return của customizer**, cần import `reactor.netty.http.server.logging.AccessLog`:

~~~java
return factory -> factory.addServerCustomizers(server ->
        server.accessLog(true, args -> {
            String uri = String.valueOf(args.uri());
            int q = uri.indexOf('?');
            String path = q < 0 ? uri : uri.substring(0, q);

            return AccessLog.create(
                    "method={} path={} status={}",
                    args.method(), path, args.status());
        }));
~~~

Đoạn trên dùng `HttpServer.accessLog(boolean, AccessLogFactory)`. Nó không dùng format tokens của Tomcat/Jetty. Việc bỏ query giảm nguy cơ ghi reset-token, email hoặc secrets trong query string, **nhưng path vẫn có thể chứa dữ liệu cá nhân** (`/users/alice@example.test`). Production cần whitelist/normalize route templates, không chỉ bỏ mọi dấu hỏi.

`AccessLogFactory.createFilter(...)` còn hỗ trợ bỏ qua một số path health-check để giảm volume, nhưng không lọc toàn bộ 401/403/5xx chỉ để “giảm logs”. Nếu bỏ health events, giữ metrics tương ứng và bảo đảm filter không nhận nhầm URL giả dạng.

## 11. Bảng đối chiếu quan trọng nhất

| Hạng mục | Tomcat | Jetty | Undertow | Reactor Netty |
| --- | --- | --- | --- | --- |
| Enable | `server.tomcat.accesslog.enabled` | `server.jetty.accesslog.enabled` | `server.undertow.accesslog.enabled` | JVM `reactor.netty.http.server.accessLogEnabled` |
| Default enabled | false | false | false | false |
| Tầng | Tomcat AccessLogValve | Jetty RequestLog/CustomRequestLog | Undertow access handler | Reactor Netty HttpServer accessLog |
| Output default khi enabled | File under Tomcat basedir/logs | **System.err** nếu filename trống | Files under working-dir/logs | SLF4J logger AccessLog |
| Đổi file | directory/prefix/suffix | filename | dir/prefix/suffix | Logback/Log4j2 appender |
| Tùy biến format | accesslog.pattern | custom-format | accesslog.pattern | AccessLogFactory |
| Duration | `%D` microseconds | `%D` microseconds, `%{ms}T` milliseconds | `%D` milliseconds khi start-time enabled | Formatter/metrics của Netty |
| Rotation/retention | rotate/max-days | filename/date/retention-period | rotate và ops policy | logging appender/collector |
| Đặc điểm dễ nhầm | basedir có thể là thư mục tạm | không có file khi filename unset | cần record-request-start-time cho `%D` | không có Boot accesslog.* namespace như Servlet |

Không lấy các con số latency thô từ bốn log formats này rồi đặt chung trong dashboard `duration_ms` trước khi kiểm tra/normalize units. Một access log ở app cũng không có cùng điểm đo thời gian với gateway upstream time hay browser performance timing.

## 12. Tránh ghi credentials và thông tin cá nhân vào access logs

Một số common/combined log patterns có `%r` (request line) hoặc `%q` (query string), và query có thể chứa dữ liệu nhạy cảm:

~~~http
GET /reset-password?token=example-secret HTTP/1.1
Authorization: Bearer example-token
Cookie: SESSION=example-session
~~~

Không đưa các giá trị này vào logs thật. Cần tránh:
- Raw `Authorization`, `Cookie` và `Set-Cookie`.
- Reset tokens, OTP, API keys, access tokens trong query/path.
- Request/response body chứa dữ liệu riêng, password, thẻ thanh toán.
- Session ID (ví dụ Tomcat `%S`) khi không có căn cứ nghiệp vụ/chính sách.
- Toàn bộ User-Agent/Referer/X-Forwarded-* không được kiểm soát nếu không có mục tiêu.
- Log injection qua giá trị client-controlled không được escape.

Tomcat có thể log path-only bằng `%m %U %H` thay vì `%r`. Jetty hỗ trợ `%U`. Undertow và Reactor Netty cần kiểm chứng formatter/sanitization theo version; với Reactor Netty có thể dùng custom `AccessLogFactory`. **Bỏ query không đủ nếu path chứa PII hoặc token.** Thiết kế URL không có secrets là bước đầu tiên.

### Log privacy và retention

- Xác định ai được xem logs và vì sao IP/path là dữ liệu cần thiết.
- Giới hạn retention, phân quyền volume, encryption at rest, central logging controls.
- Không copy raw bearer/session token vào issue tracker.
- Nếu logs đã vô tình chứa secrets, sửa pattern mới không xóa bản cũ; áp dụng incident/credential rotation và retention policy cần thiết.
- Không chỉ xem no-store HTTP Cache-Control là đã bảo vệ access log: HTTP caching và log persistence là hai cơ chế khác nhau.

## 13. Reverse proxy, client IP và Forwarded headers

~~~text
Client 203.0.113.50
       |
       v
Reverse proxy 10.0.0.20
       |
       v
Spring Boot 10.0.0.30
~~~

Spring origin có thể ghi IP `10.0.0.20` vì đó là TCP peer, không phải browser. Proxy có thể truyền `Forwarded`/`X-Forwarded-For`, nhưng headers này **có thể bị giả mạo** nếu server tin trực tiếp input Internet.

Yêu cầu an toàn:

1. Reverse proxy đầu vào phải xóa/ghi đè các forwarded headers do untrusted client gửi.
2. Cấu hình các trusted proxies/ranges/RemoteIpValve theo topology thực tế.
3. Tomcat `server.tomcat.accesslog.request-attributes-enabled=true` giúp access valve có thể đọc attributes từ RemoteIpValve đã được trust-aware xử lý.
4. `server.forward-headers-strategy=native` hoặc `framework` tùy server và hạ tầng, không bật theo suy đoán chung.
5. Khi có nhiều hops, client IP selection cần policy rõ, không lấy bất kỳ IP đầu tiên trong `X-Forwarded-For`.
6. Giữ edge access log và origin access log phân biệt bằng `layer`, `service`, `instance`, correlation ID.
7. IP address có thể là dữ liệu cá nhân; xem xét retention/permissions và privacy requirements.

Một request 502/504 hoặc 429 có thể được tạo bởi gateway trước Spring, nên **không có access log tại origin**. Không xem việc thiếu line ở Spring là log writer hỏng nếu request chưa bao giờ vào origin.

## 14. Correlation ID: nối access log với application log

Thông thường access log ghi “GET /orders/42 → 500”, trong khi Spring application log có stack trace. Muốn nối hai loại records, cần một request ID/trace ID được propagate có kiểm soát.

~~~text
Gateway generates trusted request ID
          |
          v
Spring filters / WebFlux context
          |
          +-> app logs, traces, response header
          +-> access log if its formatter includes the ID
          +-> downstream correlation
~~~

Một `X-Request-ID` do bất kỳ client tùy ý gửi **không tự đáng tin**. Có thể validate length/charset/allowlist ở gateway hoặc tạo ID mới.

### Servlet filter demo tạo UUID mới

Trong servlet lab, thêm `src/main/java/demo/http/RequestIdFilter.java`:

~~~java
package demo.http;

import java.io.IOException;
import java.util.UUID;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestIdFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        String id = UUID.randomUUID().toString();
        response.setHeader("X-Request-ID", id);

        MDC.put("requestId", id);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove("requestId");
        }
    }
}
~~~

Đây là Java class runnable nếu thêm trong package `demo.http` đã có `spring-boot-starter-web`. Bản lab **tạo UUID mới tại origin** thay vì tin header client. Tomcat access log có thể ghi ID từ response header:

~~~properties
server.tomcat.accesslog.pattern=%t "%m %U" %s %{X-Request-ID}o
~~~

Jetty CustomRequestLog cũng có format response header `%{X-Request-ID}o`; kiểm thử với Jetty version đang dùng. Đối với Undertow, cần kiểm tra exchange attribute syntax tương ứng chứ không tự áp Tomcat token.

**MDC trong Servlet filter không tự propagate cho mọi async worker**; Reactor Context/Micrometer Tracing dùng cơ chế khác khi chạy WebFlux. Một response header không tự trở thành trace ID trong APM nếu không có instrumentation. Tracing chuẩn như W3C Trace Context bổ sung cho request IDs.

## 15. Thời gian và kích thước: không diễn giải quá mức

### 15.1. Timing

Nếu cột `%D` bằng 100000:

- Tomcat 10.1: **100000 µs = 100 ms**.
- Jetty: `%D` được định nghĩa microseconds.
- Undertow (pattern trong Boot docs): **100000 ms**, nếu đã bật record-request-start-time.
- Reactor Netty: dùng logger/custom factory/metrics của chính nó, không có một grammar Tomcat `%D` chung.

Server access duration không nhất thiết bao gồm browser DNS/TLS, edge queue, CDN cache wait, client rendering hoặc mỗi downstream service riêng. Nó còn có thể chứa thời gian ghi response tùy implementation. Để tìm điểm chậm thật, kết hợp edge timings, server metrics và distributed trace spans.

### 15.2. Bytes

`%b` Tomcat là số bytes gửi, không phải số ký tự UTF-16/Java Strings. Với gzip, HTTP/2, chunked transfer hoặc aborted response, ý nghĩa/điểm đo bytes cần kiểm tra theo server/version. Không dùng access-log bytes như business record count.

### 15.3. Long-lived streaming

SSE, streaming downloads và một số HTTP long-poll giữ response mở dài. Access log thường ghi **khi response kết thúc**, không tạo một line cho từng `Flux` element/SSE event. Vì thế chưa thấy access log ngay không có nghĩa server không nhận request. Cần thêm metrics active connections/streams.

HTTP WebSocket upgrade có lifecycle riêng; status 101 hoặc log timing tùy server/handshake. Không giả định access log HTTP đủ quan sát từng WebSocket message.

## 16. Test tích hợp HTTP bằng TestRestTemplate (Servlet)

Tạo `src/test/java/demo/http/ServletAccessTest.java`:

~~~java
package demo.http;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletAccessTest {
    @Autowired
    TestRestTemplate rest;

    @Test
    void pingIs200() {
        ResponseEntity<String> r =
                rest.getForEntity("/ping", String.class);
        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).contains("ok");
    }

    @Test
    void badIs400() {
        ResponseEntity<String> r =
                rest.getForEntity("/bad", String.class);
        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
    }

    @Test
    void missingIs404() {
        ResponseEntity<String> r =
                rest.getForEntity("/missing", String.class);
        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
~~~

Chạy với dependency Tomcat, hoặc thay sang Jetty/Undertow **một server mỗi lần**:

~~~bash
./gradlew test --tests demo.http.ServletAccessTest
~~~

Test sử dụng embedded web server với random HTTP port và kiểm tra status thực tế. **Nó chưa chứng minh file/stderr access log có record**, vì test không mở log file và buffered writer có thể chưa flush. Muốn chứng minh access logging, chạy app với config tương ứng và quan sát nơi log được ghi sau cURL, có polling/wait phù hợp cho async flush.

## 17. Test WebFlux bằng WebTestClient

Trong project WebFlux tạo `src/test/java/demo/reactivelog/ReactiveAccessTest.java`:

~~~java
package demo.reactivelog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveAccessTest {
    @Autowired
    WebTestClient client;

    @Test
    void pingIs200WithJson() {
        client.get().uri("/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void missingIs404() {
        client.get().uri("/missing")
                .exchange()
                .expectStatus().isNotFound();
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests demo.reactivelog.ReactiveAccessTest
~~~

**Lưu ý:** block `bootRun.systemProperty` chỉ áp cho task bootRun. Gradle test chạy JVM khác, nên HTTP test pass không có nghĩa access logger đã bật trong test JVM. Để test access-log emission, chạy project như app/bootJar với JVM `-D` đúng hoặc thêm system property cho test task theo mục tiêu riêng và quan sát logger.

## 18. Quy trình kiểm tra log trên host và container

### 18.1. Kiểm tra tại origin

1. Xác nhận embedded server, build artifact và dependency tree.
2. Bật đúng namespace/system property; đảm bảo output destination writable.
3. Restart process. Đừng chỉ hot-reload source code khi setting cần server init lại.
4. Dùng `curl -i` gọi `/ping`, `/bad`, `/missing`, `/slow`.
5. Xem log ở **đúng nơi** cho server; không tìm file Jetty khi Jetty đang xuất stderr.
6. Kiểm tra status và duration unit, rồi so sample line với pattern đang dùng.
7. Kiểm tra có ghi query/secret không bằng **dữ liệu giả**; không đưa credential thật vào log test.
8. Khi có proxy, so call trực tiếp origin với public hostname.
9. Test rotation, permissions, disk-full và log shipping sau restart/rolling deploy.

Ví dụ Linux/macOS cho cấu hình lab:

~~~bash
# Tomcat
find runtime/tomcat/logs -type f -name 'access_log*.log'
tail -f runtime/tomcat/logs/access_log*.log

# Jetty nếu đã đặt filename
tail -f logs/jetty-access.log

# Undertow
find logs/undertow -type f

# Reactor Netty với logback-spring.xml đã tạo
tail -f logs/reactor-access.log
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem .\runtime\tomcat\logs\access_log*.log
Get-Content .\logs\reactor-access.log -Tail 20 -Wait
~~~

Vị trí tương đối tính từ **working directory của process**, không phải chắc chắn từ thư mục chứa source. IDE, Gradle, Windows service, systemd và Docker có working directory khác nhau.

### 18.2. Container/Kubernetes

- Jetty enabled không có filename có thể gửi System.err, được container log collector nhận.
- Reactor Netty với SLF4J console appender có thể được collector nhận; file appender yêu cầu volume/tailer.
- Tomcat/Undertow native access log thường ra file, **không tự xuất hiện trong `kubectl logs`**.
- Pod filesystem ephemeral: file có thể biến mất khi pod bị thay; cần ship logs hoặc mount đúng.
- Edge logs và origin logs đều hữu ích nhưng cần field `layer` để tránh đếm một HTTP call nhiều lần.
- Tính dung lượng ingestion/indexing, dùng retention hợp lý và bảo vệ logs khỏi truy cập không cần thiết.

Ví dụ capacity **chỉ là phép tính giả định**: 1.000 req/s × 200 bytes/log ≈ 200.000 bytes/s ≈ 17,28 GB/ngày dữ liệu thô theo hệ thập phân, chưa tính indexing/replicas. Traffic và log size thực khác nhau, phải đo.

## 19. Troubleshooting theo server và triệu chứng

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra |
| --- | --- | --- |
| Tomcat bật access log nhưng không tìm thấy file | basedir tạm, directory sai, buffered writer | basedir/directory, working directory, flush |
| Jetty enabled nhưng không có file | filename unset nên ghi System.err | Xem stderr hoặc đặt filename writable |
| Undertow không ghi | App vẫn chạy Tomcat hoặc dir không có quyền | Dependency exclude, server runtime, dir |
| Undertow %D thiếu/không hợp lệ | Chưa bật start-time | `record-request-start-time=true` |
| Netty không có access records | Đặt property trong application.properties thay JVM -D; logger không được nhận | System property trước -jar, logger/appender |
| Console DEBUG rất nhiều nhưng không có access log | Debug/wiretap khác HTTP access logger | Bật đúng access log generator |
| Jetty có file nhưng không có latency | Default NCSA không hẳn chứa duration | custom-format có `%{ms}T` |
| Duration dashboard sai hàng nghìn lần | Trộn microseconds và milliseconds | Normalize per server/pattern |
| 404 không xuất hiện trong origin log | Gateway đã chặn request hoặc lọc path | Compare edge vs origin |
| `Client IP` là load balancer | Không có trusted forwarded config | Trusted proxy, RemoteIpValve |
| Client IP có thể bị spoof | Tin raw X-Forwarded-For từ Internet | Strip/overwrite headers ở gateway |
| Mới cURL mà chưa thấy line | Buffered/async file writer | Đợi flush và check file date |
| HTTP 504 ở edge nhưng origin không thấy | Timeout/error tại proxy trước origin | Gateway error/access log |
| Access log chứa reset token | %r/%q hoặc full URI logger | Bỏ query/route secret, incident cleanup |
| WebClient outbound không xuất hiện | Server access log không phải client log | Client metrics/tracing |
| SSE chưa ghi access line | Stream chưa kết thúc | Active stream metrics và completion |
| App có 2 server starters | Boot chọn server khác kỳ vọng | Verify actual runtime/dependencies |
| File logging biến mất sau deploy | Ephemeral filesystem, không có shipper | Mount/collector/retention |

Đừng “sửa” bằng việc bật wiretap ghi payload thật trên production: đó là rủi ro privacy cao. Thay vào đó, xác định logger đúng và kiểm tra output destination.

## 20. Logging overhead, retention và high-traffic operation

Access logger tốn tài nguyên cho format metadata, ghi file/stderr, flush, rotation và shipping. Một stream dài có thể chỉ ghi khi hoàn tất. Với traffic lớn, chọn:

- Tối giản fields; không ghi raw body/headers chứa secret.
- Có appender/queue/collector được monitor; async logging có nguy cơ mất log khi queue đầy hoặc process chết.
- Rotation và retention thuộc **đúng server/logging framework**. Tomcat native rotation không phải Logback; Netty file Logback không phải Undertow rotation.
- Theo dõi file descriptors, disk usage, shipper backlog, dropped logs và IO latency.
- Giữ 401/403/5xx vì hữu ích cho security, không chỉ xóa mọi lỗi để giảm cost.
- Có policy bỏ health checks khi cần, nhưng giữ metrics và không vô tình lọc request tấn công giả dạng health path.
- Khi gửi logs qua collector, tạo fields chuẩn `timestamp`, `service`, `instance`, `layer`, `method`, `route/path`, `status`, `duration_ms`, `trace_id` với redaction.
- Benchmark throughput và p95/p99 latency khi bật/tắt logging cùng workload; kiểm tra rolling restart và disk-full.

### Access log không phải security audit

Server HTTP log có thể ghi `GET /orders/42 200`, nhưng không chứng minh “đúng người dùng được phép đọc order”. Business audit cần actor đáng tin sau authentication, action, resource, outcome, retention và chống chỉnh sửa theo chính sách. Có thể liên kết cả hai bằng trace/request ID, nhưng đừng log bearer/session tokens.

## 21. Checklist trước release

1. Server nào thực sự chạy: Tomcat, Jetty, Undertow hay Reactor Netty?
2. Cấu hình tương ứng đúng dependency và namespace/system property chưa?
3. Có biết log nằm ở file Tomcat basedir, Jetty stderr/file, Undertow dir hay Netty logger?
4. Format có method/path/status/duration hữu ích và đúng đơn vị không?
5. Có ghi query, cookies, Authorization, PII/token hoặc request body ngoài ý muốn không?
6. Client IP/Forwarded headers có trust boundary và chống spoofing không?
7. Có rotation, retention, writable directories, permissions, log shipping và disk limits?
8. Có quan sát request 200/400/404, proxy errors, streaming/long-lived requests?
9. Có phân biệt một request tại edge với cùng request tại origin, tránh double counting?
10. Có cấu hình app log/tracing/Micrometer song song để điều tra nguyên nhân lỗi?
11. Có test bằng HTTP thật, không chỉ unit test controller?
12. Có tài liệu dành cho người vận hành: tìm log ở đâu, cách đổi format, rollback, xử lý PII incident?
13. Khi bật Reactor Netty customizer, đã chọn một nguồn enable rõ, không chồng JVM property và code không kiểm soát?
14. Với Undertow %D, đã bật `server.undertow.options.server.record-request-start-time`?
15. Có dùng đúng version docs để tránh áp cú pháp Tomcat 9/Boot 2 sang Boot 3.3?

## 22. Câu hỏi tự kiểm tra

**1.** App có `spring-boot-starter-web` và `server.jetty.accesslog.enabled=true` nhưng không log. Vì sao?

**Đáp án:** Starter-web thường chạy Tomcat. Cần dùng Tomcat namespace hoặc đổi dependency sang Jetty và exclude starter-tomcat.

**2.** Tomcat access log enabled nhưng không có `./logs/access_log`. Tìm đâu?

**Đáp án:** Xem `server.tomcat.basedir` và `server.tomcat.accesslog.directory`; Tomcat base có thể là temporary directory.

**3.** Jetty enabled không cấu hình filename sẽ ghi đâu?

**Đáp án:** `System.err` trong Spring Boot 3.3. Nó không tự tạo file logs/jetty-access.log.

**4.** Để Undertow log duration %D, cần property nào?

**Đáp án:** `server.undertow.options.server.record-request-start-time=true`.

**5.** %D Tomcat và Undertow đều là milliseconds?

**Đáp án:** Không. Tomcat 10.1 dùng microseconds, Undertow theo ví dụ Boot dùng milliseconds. Jetty cũng hỗ trợ %D microseconds và %{ms}T milliseconds.

**6.** Bật `logging.level.reactor.netty=DEBUG` là đủ để bật Netty server access log?

**Đáp án:** Không. Bật JVM `-Dreactor.netty.http.server.accessLogEnabled=true` hoặc `HttpServer.accessLog(true)`; logger phải được logging framework nhận.

**7.** Có thể bật Netty access log qua `application.properties` bằng cùng tên JVM option?

**Đáp án:** Không mặc nhiên. `reactor.netty.http.server.accessLogEnabled` là JVM system property, không phải server accesslog property do Boot 3.3 bind.

**8.** Vì sao Spring không có line access log cho một response 504 thấy ở browser?

**Đáp án:** 504 có thể được gateway tạo trước khi origin trả response; kiểm tra edge logs và đường đi.

**9.** Đặt Tomcat pattern `%r` cho API password reset có token trong query an toàn không?

**Đáp án:** Rủi ro cao vì request line thường gồm query. Tránh token trong URL, dùng path-only fields hoặc redaction phù hợp.

**10.** SSE stream mở 5 phút mà chưa xuất hiện access log, có nghĩa server không nhận request?

**Đáp án:** Không. Record access log thường phát khi response hoàn tất; dùng thêm metrics active streams.

**11.** Reactor Netty HTTP server access log có theo dõi mọi outbound WebClient không?

**Đáp án:** Không, HTTP server log khác client-side observability.

**12.** X-Forwarded-For của Internet client có đủ tin để ghi “IP thật” không?

**Đáp án:** Không. Chỉ trust proxy đã được kiểm soát; gateway strip/overwrite và server xử lý trusted proxy ranges.

## 23. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Configure Access Logging](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): hướng dẫn Tomcat, Jetty, Undertow, đường ghi và thời gian Undertow.
- [Spring Boot 3.3 – Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): thuộc tính native access logging của ba Servlet servers, logging và forwarded headers.
- [Apache Tomcat 10.1 – AccessLogValve](https://tomcat.apache.org/tomcat-10.1-doc/config/valve.html): token %m/%U/%r/%q/%s/%D, units, RemoteIpValve và request attributes.
- [Jetty 12 – CustomRequestLog API](https://jetty-project.github.io/javadoc.jetty.org/jetty-12/org/eclipse/jetty/server/CustomRequestLog.html): custom pattern/latency/response header fields.
- [Jetty 12 – Request Logging Module](https://jetty.org/docs/jetty/12/operations-guide/modules/standard.html): NCSA request logs và file handling.
- [Undertow – UndertowOptions source](https://github.com/undertow-io/undertow/blob/main/core/src/main/java/io/undertow/UndertowOptions.java): RECORD_REQUEST_START_TIME option.
- [Reactor Netty 1.1 – HTTP Access Log Reference](https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.15/reference/html/): system property, logger, file appender, programmatic accessLog.
- [Spring Boot 3.3 – NettyReactiveWebServerFactory API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/embedded/netty/NettyReactiveWebServerFactory.html): addServerCustomizers.
- [Reactor Netty – AccessLogFactory API](https://docs.spring.io/projectreactor/reactor-netty/docs/1.1.4/api/reactor/netty/http/server/logging/AccessLogFactory.html): custom format và filters.
- [Spring Boot – Logging Features](https://docs.spring.io/spring-boot/3.3/reference/features/logging.html): app logs/console/file khác native access logs.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): correlation và distributed spans.

**Kết luận:** access log thuộc **HTTP server thực sự chạy**, không thuộc mọi controller. Tomcat, Jetty và Undertow dùng ba nhóm `server.*.accesslog.*` khác nhau; Reactor Netty dùng JVM system property hoặc `HttpServer.accessLog(...)` và logging framework. Cấu hình đúng phải bao gồm cả **đích ghi, privacy/redaction, trusted proxy, đơn vị duration, retention và kiểm chứng từ HTTP requests thật**.
