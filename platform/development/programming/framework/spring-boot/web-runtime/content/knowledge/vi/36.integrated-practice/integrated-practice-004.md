# Thay Tomcat bằng máy chủ khác và kiểm tra cấu hình thực tế trong Spring Boot

## 1. Mục tiêu thực hành: đổi **HTTP server**, không đổi nhầm web framework

Spring Boot MVC thường khởi động bằng **embedded Tomcat** vì `spring-boot-starter-web` mang theo `spring-boot-starter-tomcat`. Trong một ứng dụng cần thử nghiệm hoặc triển khai với **Jetty** hoặc **Undertow**, ta có thể thay container bằng cách **loại Tomcat starter ra khỏi dependency graph và thêm đúng một server starter thay thế**. Controller, service, Jakarta Servlet và đa số cấu hình Spring MVC có thể giữ nguyên.

Nhưng một thay đổi dependency thành công **không chứng minh** cấu hình thực tế còn phù hợp:

- App có thật sự sử dụng Jetty/Undertow, hay một transitive dependency đã kéo Tomcat trở lại?
- Các property `server.tomcat.*` trước đây đã được chuyển thành `server.jetty.*`/`server.undertow.*` phù hợp chưa?
- HTTP request header limit, max form size, worker threads, compression, keep-alive, access logs và encoded paths còn theo chính sách bảo mật/hiệu năng không?
- HTTP/2 (TLS `h2` hoặc cleartext `h2c`) có thực sự negotiate được theo client/proxy, hay chỉ bật một property?
- Servlet filters, handler mappings, errors, cookies/session và Actuator có còn hoạt động khi container thay?
- Server mới có nằm trong **supported platform matrix** của phiên bản Spring Boot đang dùng không?
- Có test HTTP thật, load test, kế hoạch rollback và số liệu so sánh trước–sau không?

Bài thuộc nhóm **Thực hành tổng hợp** của module **Spring Boot - web-runtime**. Ví dụ dùng **Spring Boot 3.5.16, Java 17+, Maven, Spring MVC/Jakarta Servlet**: bắt đầu với **Jetty 12.0**, đổi sang **Undertow 2.3**, và có đường quay lại Tomcat 10.1. Mã Java ứng dụng giữ nguyên trong cả ba bước. Có unit test, `@WebMvcTest`/`MockMvc`, `@SpringBootTest(RANDOM_PORT)` với HTTP client thực, endpoint quan sát **server object thực tế**, test Servlet ngoài MVC, `curl` cho routing/compression và profile cấu hình riêng.

> **Phạm vi:** đây là bài **thay embedded HTTP server** trong Spring MVC. Không phải hướng dẫn chuyển `@RestController` MVC sang Spring WebFlux hay deploy WAR vào Tomcat ngoài. Với ứng dụng reactive, default là Reactor Netty; cách chọn server và API không hoàn toàn giống Servlet MVC.

### Mục tiêu sau bài

1. Hiểu ranh giới: MVC framework, Servlet engine, transport, proxy.
2. Đổi Tomcat thành Jetty bằng Maven/Gradle đúng dependency scope, không để hai container cùng classpath.
3. Đổi Jetty thành Undertow **chỉ khi target Spring Boot còn hỗ trợ**.
4. Quan sát server hiện hành từ `ServletWebServerApplicationContext`, không đoán bằng tên JAR hoặc HTTP `Server` header.
5. Đọc config chung và config riêng của container, phân biệt “property được Environment đọc” với “server áp dụng thành công”.
6. So sánh đúng HTTP behavior: mapping, JSON, status, headers, compression, URL/encoding, session, filter, Actuator, HTTP/2.
7. Chạy tests, đo performance có kiểm soát và rollback theo chứng cứ.

## 2. Vẽ đúng các lớp hệ thống

Một request Spring Boot MVC đi qua:

```text
Client / browser / HTTP load generator
            |
            v
Ingress / gateway / TLS termination (nếu có)
            |
            v
Embedded HTTP Server
    [Tomcat hoặc Jetty hoặc Undertow]
            |
            v
Jakarta ServletContext
  -> Container dispatch / Servlet Filter chain
  -> DispatcherServlet
  -> Spring MVC HandlerMapping/HandlerAdapter
  -> JSON converter, validation, @ControllerAdvice
  -> @RestController, service, repository
            |
            v
HTTP response / headers / bytes
```

**Spring MVC không đổi thành WebFlux** khi bạn dùng Jetty hoặc Undertow làm Servlet container. Các annotations `@GetMapping`, `@RequestBody`, `@Valid`, `@RestControllerAdvice` vẫn chạy qua `DispatcherServlet`. Điều thay là HTTP connector, Servlet implementation, thread/executor/buffer, access logging và server-specific defaults.

| Thành phần | Có thay khi swap? | Hệ quả |
| --- | --- | --- |
| Spring MVC `DispatcherServlet` | Không, nếu vẫn dùng starter-web | Giữ MVC tests/contracts |
| Jakarta Servlet API | Cùng generation được Boot hỗ trợ | Custom Servlet/Filter vẫn phải test |
| Server implementation | Có | Thread pools, connectors, limits, access log |
| Spring `server.port` | Cấu hình chung | Cả các server hỗ trợ |
| `server.tomcat.threads.max` | **Không còn tác động lên Jetty/Undertow** | Phải rà property phù hợp |
| `server.compression.*` | API cấu hình chung | Kiểm tra actual response |
| SSL/HTTP/2 | Có abstraction, implementation khác | Cần wire/protocol test |
| Actuator & Micrometer | Các base meters vẫn có; server-specific có thể khác | Review dashboards/alerts |
| External reverse proxy | Không đổi vì swap app | Nhưng upstream protocol/redirect có thể khác |
| Application's business logic | Nên giữ nguyên | Unit tests giúp cô lập regression |

Một app có thể *trả HTTP 200 đúng* nhưng mất access logs hoặc thay thread limits mà không có warning hữu ích; đó là lý do bài yêu cầu đọc **dependency graph + runtime identity + effective configuration + HTTP evidence**.

## 3. Ma trận phiên bản: đừng dùng hướng dẫn Boot 3 để cấu hình Boot 4

### 3.1. Spring Boot 3.5.16

Theo [Spring Boot 3.5 system requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html):

| Embedded servlet server | Phiên bản được Boot 3.5 hỗ trợ | Servlet spec |
| --- | --- | --- |
| Tomcat | **10.1** (tối thiểu patch theo docs) | 6.0 |
| Jetty | **12.0** | 6.0 |
| Undertow | **2.3** | 6.0 |

Boot 3.5.16 cần **Java 17+** và Spring Framework 6.2.19+ theo baseline. Với external WAR còn có requirement Servlet 5.0+ compatible container. Lab chọn **embedded** server; external WAR được bàn riêng ở mục 20.

Không pin một phiên bản Jetty/Tomcat/Undertow ngẫu nhiên ngoài Spring Boot BOM chỉ vì patch đó mới hơn. Cần đối chiếu versions, APIs, security advisories và dependencies đi kèm. Dùng đúng parent/BOM của target Boot line.

### 3.2. Spring Boot 4.x không còn Undertow starter hỗ trợ

Spring Boot 4.0 migration guide xác nhận **Servlet baseline 6.1**, hỗ trợ **Tomcat 11 / Jetty 12.1**, và **Undertow support bị loại** do không phù hợp baseline tại thời điểm phát hành. Vì vậy bài này **dùng Boot 3.5 để thực hành Jetty và Undertow**, không làm ví dụ Undertow trên Boot 4.

| Nhu cầu | Hướng xử lý |
| --- | --- |
| Boot 3.5 + Jetty | Starter Jetty 12.0 |
| Boot 3.5 + Undertow | Starter Undertow 2.3 |
| Boot 3.5 + Tomcat | Starter Tomcat 10.1 mặc định |
| Boot 4 + Jetty | Đọc Boot 4 guide và dùng Jetty 12.1 |
| Boot 4 + Tomcat | Đọc Boot 4 guide và dùng Tomcat 11 |
| Boot 4 + Undertow | **Không dùng giả định starter Undertow được Boot hỗ trợ** |

**Ghi chú version:** `spring-boot-starter-web` là starter Spring MVC dùng trong Boot **3.5**. Boot 4 có modular starter naming (`spring-boot-starter-webmvc`) và test/auto-configuration package changes; không chỉ sửa `<version>` thành 4.x rồi tin rằng toàn bộ ví dụ chạy nguyên văn.

## 4. Thao tác Maven: Tomcat → Jetty

Với Spring Boot 3.5 Maven, `spring-boot-starter-web` kéo `spring-boot-starter-tomcat` theo dependency transitively. Phải thêm **exclusion** ở dependency đó:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
```

Đây là snippet cho POM (POM **hoàn chỉnh** ở mục 10). Giữ `spring-boot-starter-web` vì nó chứa Spring MVC, Jackson và các integrations. **Không loại toàn bộ starter-web** chỉ vì muốn thay Tomcat.

Maven sẽ resolve Jetty versions qua Spring Boot dependency management. Bản build nên dùng đúng **một lựa chọn embedded server**. Nếu dependency khác cũng kéo Tomcat starter hoặc servlet engine, xem cây dependency và exclude tại nguồn phù hợp — không chỉ đoán từ `pom.xml`.

### Kiểm tra dependency graph

```bash
mvn clean package
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-jetty
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-undertow
```

Kỳ vọng cấu hình Jetty:

- Starter Jetty có mặt trong runtime tree.
- Starter Tomcat **không** còn trong application dependency graph sau exclusion.
- Undertow starter không xuất hiện.
- Spring MVC và Jakarta Servlet APIs tương thích Boot 3.5.

Nhớ rằng có thể tồn tại **test-only** Tomcat dependency, hoặc Boot plugin packaging có nuances; kiểm tra **runtime scope** và artifact `jar tf`, không chỉ tìm string `tomcat` ở bất cứ file nào rồi kết luận app dùng Tomcat.

## 5. Thao tác Maven: Jetty → Undertow

Trong Spring Boot 3.5, từ cấu hình Jetty đã exclude Tomcat, thay **một starter**:

```xml
<!-- Bỏ dependency spring-boot-starter-jetty khỏi POM. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
```

Giữ nguyên `spring-boot-starter-web` với Tomcat exclusion. Không khai báo đồng thời Jetty và Undertow và chờ Boot “tự chọn” theo thứ tự dependency; nếu cả hai có mặt, dễ gây bean ambiguity hoặc phụ thuộc auto-configuration conditions khó dự đoán.

Chạy:

```bash
mvn clean test
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-undertow
mvn clean package
```

Sau swap, cần **xóa hoặc tắt cấu hình riêng Jetty** và bật cấu hình Undertow đã được review. Property `server.jetty.threads.max` vẫn có thể xuất hiện trong `Environment` nhưng **không trở thành Undertow worker thread setting**. Đây là một lỗi “startup xanh nhưng hiệu năng khác” rất phổ biến.

### Rollback về Tomcat

Khôi phục `spring-boot-starter-web` **không có Tomcat exclusion**, đồng thời bỏ Jetty/Undertow starter riêng. Sau đó build/test và kiểm tra server name thực. Đừng chỉ thêm starter Tomcat vào POM có sẵn Jetty/Undertow vì có thể tạo hai server choices.

## 6. Gradle tương đương: đừng quên loại transitive Tomcat

Groovy DSL dùng Spring Boot 3.5:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Đây là **build.gradle** thay thế Maven POM, không dùng đồng thời hai build tools. Để thử Undertow, đổi `spring-boot-starter-jetty` thành `spring-boot-starter-undertow` với Boot **3.5**, giữ Tomcat exclusion.

```bash
./gradlew clean test bootJar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat
./gradlew dependencyInsight --dependency spring-boot-starter-jetty
```

Nếu project có plugin BOM riêng hoặc các dependencies khác cũng kéo Tomcat, phải rà cấu hình Gradle thực tế; một exclusion cục bộ không tự loại mọi đường kéo Tomcat. Không dùng `compileOnly` để loại servlet engine trong executable JAR.

## 7. Phân lớp cấu hình: chung, riêng, và environment thực

### 7.1. Thuộc tính chung của Boot 3.5

| Key | Ý nghĩa | Có thể dùng với Jetty/Undertow/Tomcat? |
| --- | --- | --- |
| `server.port` | Main HTTP listener port | Có |
| `server.address` | Bind address | Có |
| `server.servlet.context-path` | Servlet context path embedded | Có |
| `server.compression.enabled` | Response compression bật/tắt | Có |
| `server.compression.min-response-size` | Ngưỡng response length cho compression | Có, behavior implementation cần test |
| `server.compression.mime-types` | Content types được phép nén | Có |
| `server.max-http-request-header-size` | Request header limit | Có, cách tính giới hạn tùy server |
| `server.http2.enabled` | Yêu cầu HTTP/2 nếu runtime hỗ trợ | Có, cần deps/TLS/protocol test |
| `server.ssl.*` | SSL configuration | Có abstraction, details có thể khác |
| `server.forward-headers-strategy` | Cách xử lý forwarded headers | Có, phải xác định trusted proxy |
| `server.shutdown` | Shutdown mode | Có, kiểm tra graceful behavior |
| `spring.lifecycle.timeout-per-shutdown-phase` | Timeout lifecycle phase | Có |

Ví dụ cấu hình chung dành cho lab:

```properties
server.port=8080
server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json
server.max-http-request-header-size=16KB
server.http2.enabled=false
server.forward-headers-strategy=none
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
```

**Đây là cấu hình khai báo**, chưa phải bằng chứng 16KB được container áp đúng theo cùng semantics. Theo bảng properties Boot 3.5, request-header size có interpretation khác giữa servers; ví dụ Tomcat tính tổng request line và headers, Reactor Netty có cách giới hạn khác.

### 7.2. Server-specific properties KHÔNG tự chuyển đổi

| Tomcat | Jetty | Undertow | Ghi chú |
| --- | --- | --- | --- |
| `server.tomcat.threads.max` | `server.jetty.threads.max` | `server.undertow.threads.worker` | **Không** tương đương 1:1 về thread model |
| `server.tomcat.threads.min-spare` | `server.jetty.threads.min` | Không có minimum tương đương một-một | Model khác |
| `server.tomcat.max-connections` | `server.jetty.max-connections` | Xem Undertow socket/server options | Semantics khác |
| `server.tomcat.accesslog.enabled` | `server.jetty.accesslog.enabled` | `server.undertow.accesslog.enabled` | Paths/pattern syntax khác |
| `server.tomcat.max-http-response-header-size` | `server.jetty.max-http-response-header-size` | Không đoán key tương ứng | Test server-specific |
| `server.tomcat.connection-timeout` | `server.jetty.connection-idle-timeout` | `server.undertow.no-request-timeout` | Không thay key máy móc |
| `server.tomcat.relaxed-path-chars` | Xem Jetty URI compliance | `server.undertow.decode-slash` và options | Rủi ro path canonicalization/security |

**Không được** lấy `server.tomcat.threads.max=200` rồi đặt `server.undertow.threads.worker=200` và xem đó là “giữ nguyên capacity”. Undertow có **I/O threads** riêng và **worker threads** cho tasks blocking; Jetty có QueuedThreadPool với selectors/acceptors. Benchmark cùng workload mới có ý nghĩa.

### 7.3. Cấu hình Jetty theo profile

Ví dụ `application-jetty.properties`:

```properties
# Chỉ kích hoạt khi thực sự chạy Jetty trong lab.
server.jetty.threads.min=8
server.jetty.threads.max=64
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=./logs/jetty-access.log
```

Đây là **giá trị thử nghiệm**, không phải production sizing. Cần đảm bảo thư mục logs được phép ghi và log retention/rotation. Nếu chạy Undertow nhưng vô tình kích hoạt profile jetty, key trên có thể vẫn được Environment đọc nhưng không tác động tới server hiện tại.

### 7.4. Cấu hình Undertow theo profile

Ví dụ `application-undertow.properties`:

```properties
# Chỉ kích hoạt khi thực sự chạy Undertow (Boot 3.5).
server.undertow.threads.io=2
server.undertow.threads.worker=32
server.undertow.accesslog.enabled=true
server.undertow.accesslog.dir=./logs/undertow
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Theo docs Boot, nếu muốn `%D` có thời gian đáp ứng trong Undertow access log, cần bật `server.undertow.options.server.record-request-start-time=true`. Không tự dịch pattern `%D` của Tomcat theo đơn vị thời gian: Tomcat có thể dùng microseconds trong template, Undertow ví dụ docs dùng milliseconds. Hãy đọc docs của engine và xác minh log thực.

### 7.5. Profile và môi trường chạy

Profiles giúp tách **cấu hình engine-specific**, nhưng **không chọn engine**. Engine được quyết định bởi classpath/starter và auto-configuration, còn `spring.profiles.active` chỉ quyết định config sources/beans có điều kiện.

| Artifact được build | Profile | Kết quả |
| --- | --- | --- |
| Jetty starter | `lab,jetty` | Jetty + settings Jetty |
| Undertow starter | `lab,undertow` | Undertow + settings Undertow |
| Jetty starter | `lab,undertow` | **Vẫn Jetty**, Undertow properties không biến thành Jetty |
| Undertow starter | `lab,jetty` | **Vẫn Undertow**, Jetty properties không tự áp |
| Tomcat default | `lab` | Tomcat, nếu không có server alternative |

Để tránh “profile đặt tên đúng nhưng engine sai”, bài có test **runtime server class** và so dependency graph.

## 8. Cách xác minh máy chủ thực, tránh dựa vào dấu hiệu yếu

Đừng chỉ dùng các tín hiệu sau:

- File tên `jetty-app.jar`: tên artifact không quyết định runtime.
- Một dòng log `Started ...` của Spring Boot: dòng này không nói được connector nào xử lý request.
- `Server: Jetty(...)` HTTP header: server có thể tắt/sửa/ẩn header hoặc proxy thay thế.
- `pom.xml` thấy Jetty starter: transitive Tomcat/alternative starter còn tồn tại.
- Thuộc tính `server.jetty.threads.max=64` trong `Environment`: biết **có cấu hình**, chưa biết Jetty thực sự chạy.

Cách chắc hơn trong embedded servlet app: inject `ServletWebServerApplicationContext` và đọc **đối tượng `WebServer` đang chạy**:

```java
String implementation =
        servletWebServerApplicationContext.getWebServer()
                .getClass().getSimpleName();
```

Trong Spring Boot 3.5 embedded MVC, các implementation thường là:

- `TomcatWebServer`
- `JettyWebServer`
- `UndertowWebServer`

Tên class là diagnostic hữu ích của **phiên bản demo**, không phải public API contract của sản phẩm. Đừng viết client production phụ thuộc chuỗi đó. Bài đặt endpoint runtime dưới `@Profile("lab")` để không expose port, server implementation và configuration trong production.

### Ba mức kiểm chứng cấu hình

1. **Declared:** `application*.properties`, environment, Helm/CI config thực sự chứa key gì?
2. **Bound/effective:** Spring `Environment`/`@ConfigurationProperties` và active profiles đọc giá trị nào?
3. **Applied/observed:** Jetty/Undertow objects, HTTP behavior, access logs, thread metrics và perf test cho thấy gì?

Ví dụ `server.max-http-request-header-size=16KB` được trả về từ `Environment` chỉ chứng minh key có hiệu lực ở **Spring property source**. Muốn biết giới hạn request được container áp ra sao, cần gửi một request header **có kích thước kiểm soát** qua actual TCP, quan sát kết quả và đối chiếu tài liệu server. Đừng thử flood headers trên production host.

## 9. Checklist trước khi thay đổi: baseline nên lưu

Để bài thực hành có thể so sánh Tomcat/Jetty/Undertow, cần lưu baseline:

- Boot version, Java version, build tool và dependency tree.
- Server object thật, Servlet version, HTTP port/bind address/context path.
- Endpoint/method/status/body/header contracts.
- Multipart upload, session/cookies, CORS/CSRF/security filters.
- Request header limit/size, form parameters, URL decoding, encoded slash.
- Compression response headers/bytes theo `Accept-Encoding`.
- HTTP/1.1 vs HTTP/2, TLS/mTLS/ALPN nếu có.
- Access logs đúng thư mục, pattern, rotation, request IDs.
- Active profiles và **non-secret** effective configuration.
- Actuator health/metrics, JVM/thread/connection measurements.
- Load test với cùng workload/dataset/duration, p95/p99/errors.
- Rollback artifact, deployment flags, expected startup time.

Nếu một default khác server làm status/limits thay đổi, **đừng vội “fix” bằng cách nới security policy**. Đầu tiên xác định behavior mong muốn theo application contract, sau đó config tương đương (nếu được hỗ trợ) và regression test.

## 10. Project thực hành Java 17+, Maven, Spring Boot 3.5.16

Ta xây một ứng dụng nhỏ mà **cùng code không đổi** khi dùng Jetty, Undertow hoặc Tomcat. Endpoint:

- `GET /api/products/pen`: JSON sản phẩm, header `X-Lab-Contract: v1`.
- `POST /api/quotes`: nhận JSON được `@Valid`, tính tiền.
- `GET /api/blob?size=8192`: text lặp có thể nén để test response compression.
- `GET /raw/ping`: Servlet độc lập Spring MVC, kiểm tra container dispatch.
- `GET /lab/server`: diagnostic **chỉ khi profile `lab` được bật**, trả server class, port/context và vài **non-secret** properties.
- `GET /actuator/health`: health endpoint qua Spring Boot Actuator.
- `X-Lab-Filter: active`: do Servlet filter thêm vào HTTP responses.

### 10.1. Cấu trúc project

```text
server-swap-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/serverswap/
    │   │   ├── ServerSwapApplication.java
    │   │   ├── CatalogService.java
    │   │   ├── CatalogController.java
    │   │   ├── ApiErrorHandler.java
    │   │   ├── ResponseMarkerFilter.java
    │   │   ├── RawServletConfiguration.java
    │   │   └── RuntimeDiagnosticsController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── application-jetty.properties
    │       └── application-undertow.properties
    └── test/
        └── java/com/example/serverswap/
            ├── CatalogServiceTest.java
            ├── CatalogControllerMvcTest.java
            └── LiveHttpServerTest.java
```

Các file Java có `public class` mang đúng tên file. Các DTO/exception/Servlet phụ ở cùng package có thể là nested class/record hoặc package-private; không cần tạo thêm file ẩn.

### 10.2. `pom.xml` hoàn chỉnh — Jetty là engine mặc định của bài

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>server-swap-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
            <exclusions>
                <exclusion>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-starter-tomcat</artifactId>
                </exclusion>
            </exclusions>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jetty</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Lý do từng dependency:

- `starter-web` giữ Spring MVC/JSON, loại riêng transitive Tomcat.
- `starter-jetty` cung cấp embedded Jetty phù hợp Boot 3.5.
- `starter-validation` cho Jakarta Bean Validation.
- `starter-actuator` cho health.
- `starter-test` cho JUnit, Mockito, Spring Test/MockMvc, TestRestTemplate.
- Boot Maven plugin tạo executable JAR.

Không thêm WebFlux chỉ để thay Tomcat bằng Jetty; đó là một thay đổi **khác vấn đề**.

### 10.3. `ServerSwapApplication.java`

```java
package com.example.serverswap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServerSwapApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerSwapApplication.class, args);
    }
}
```

Class `@SpringBootApplication` ở root `com.example.serverswap` để controllers/services/config được scan.

### 10.4. `CatalogService.java`

```java
package com.example.serverswap;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    public record Product(String sku, long unitPriceVnd) {
    }

    public record Quote(
            String sku,
            int quantity,
            long unitPriceVnd,
            long totalVnd) {
    }

    public Product product(String sku) {
        return switch (sku) {
            case "pen" -> new Product("pen", 12_000L);
            case "book" -> new Product("book", 35_000L);
            default -> throw new ProductNotFoundException(sku);
        };
    }

    public Quote quote(String sku, int quantity) {
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be between 1 and 100");
        }
        Product found = product(sku);
        long total = Math.multiplyExact(
                found.unitPriceVnd(), (long) quantity);
        return new Quote(
                found.sku(),
                quantity,
                found.unitPriceVnd(),
                total);
    }
}

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

Dùng `Math.multiplyExact` tránh silent overflow. Service không phụ thuộc Jetty/Tomcat/Undertow. Nếu chỉ server đổi, các unit tests của service nên giữ nguyên.

### 10.5. `CatalogController.java`

```java
package com.example.serverswap;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class CatalogController {

    public record QuoteRequest(
            @NotBlank String sku,
            @Min(1) @Max(100) int quantity) {
    }

    private final CatalogService catalog;

    public CatalogController(CatalogService catalog) {
        this.catalog = catalog;
    }

    @GetMapping(
            value = "/products/{sku}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<CatalogService.Product> product(
            @PathVariable String sku) {
        return ResponseEntity.ok()
                .cacheControl(CacheControl.noStore())
                .header("X-Lab-Contract", "v1")
                .body(catalog.product(sku));
    }

    @PostMapping(
            value = "/quotes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public CatalogService.Quote quote(
            @Valid @RequestBody QuoteRequest body) {
        return catalog.quote(body.sku(), body.quantity());
    }

    @GetMapping(
            value = "/blob",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> blob(
            @RequestParam(defaultValue = "8192") int size) {
        int n = Math.min(Math.max(size, 0), 32_768);
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .cacheControl(CacheControl.noStore())
                .body("x".repeat(n));
    }
}
```

`GET /api/blob?size=8192` có body **8192 ký tự `x`**, nằm trong ngưỡng `server.compression.min-response-size=1KB`. Nên quan sát HTTP `Content-Encoding` bằng client hỗ trợ gzip; đừng đánh đồng property `enabled=true` với việc mọi response đều được nén (phụ thuộc content type, request `Accept-Encoding`, response size và server).

### 10.6. `ApiErrorHandler.java`

```java
package com.example.serverswap;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> notFound(
            ProductNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("code", "PRODUCT_NOT_FOUND"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> validation(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_REQUEST"));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_JSON"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> illegal(
            IllegalArgumentException ex) {
        return ResponseEntity.badRequest()
                .body(Map.of("code", "INVALID_REQUEST"));
    }
}
```

Public error schema rõ hơn so với việc phụ thuộc mặc định error HTML/JSON của từng container. Unknown SKU 404, validation 400; tests bảo vệ contract này sau khi swap.

### 10.7. `ResponseMarkerFilter.java`

```java
package com.example.serverswap;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ResponseMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        response.setHeader("X-Lab-Filter", "active");
        chain.doFilter(request, response);
    }
}
```

Đây là Filter bean được Boot đăng ký trong embedded Servlet container. Test thực trên Jetty và Undertow sẽ xác minh header `X-Lab-Filter` có mặt; MockMvc cũng có thể chạy filters được cấu hình, nhưng **không đủ để chứng minh container registration trên TCP**.

### 10.8. `RawServletConfiguration.java`

```java
package com.example.serverswap;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RawServletConfiguration {

    @Bean
    ServletRegistrationBean<RawPingServlet> rawServlet() {
        ServletRegistrationBean<RawPingServlet> bean =
                new ServletRegistrationBean<>(
                        new RawPingServlet(), "/raw/*");
        bean.setName("rawPingServlet");
        return bean;
    }
}

class RawPingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {
        if (!"/ping".equals(request.getPathInfo())) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("raw-servlet-ok\n");
    }
}
```

`/raw/*` thuộc **Servlet container dispatch**, không phải `@GetMapping`. Nếu swap server rồi `/api/products/pen` vẫn tốt nhưng `/raw/ping` 404, lỗi có thể nằm ở Servlet registration/URL mapping hoặc incompatibility container, không phải business logic.

### 10.9. `RuntimeDiagnosticsController.java` — xác minh server class và config

```java
package com.example.serverswap;

import java.util.Map;

import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Profile("lab")
@RestController
@RequestMapping("/lab")
public class RuntimeDiagnosticsController {

    private final ServletWebServerApplicationContext context;
    private final Environment environment;

    public RuntimeDiagnosticsController(
            ServletWebServerApplicationContext context,
            Environment environment) {
        this.context = context;
        this.environment = environment;
    }

    @GetMapping("/server")
    public Map<String, Object> server() {
        return Map.of(
                "server",
                context.getWebServer().getClass().getSimpleName(),
                "port",
                context.getWebServer().getPort(),
                "contextPath",
                context.getServletContext().getContextPath(),
                "compressionProperty",
                environment.getProperty(
                        "server.compression.enabled", "unset"),
                "requestHeaderLimitProperty",
                environment.getProperty(
                        "server.max-http-request-header-size", "unset"),
                "http2Property",
                environment.getProperty(
                        "server.http2.enabled", "unset"));
    }
}
```

`@Profile("lab")` giúp endpoint **không được tạo** khi không bật profile lab. Đây là thông tin chẩn đoán của project học tập, không triển khai public ở production. `server` là class của `WebServer` đang chạy; `compressionProperty`/`requestHeaderLimitProperty`/`http2Property` chỉ cho biết **giá trị cấu hình Spring nhìn thấy**, chưa chứng minh web engine áp dụng cùng semantics.

Trong test `RANDOM_PORT`, property `port` là cổng đã bind thật, không phải `server.port=8080` trong main config. Có thể dùng thông tin này để đối chiếu thay vì suy đoán server từ log hoặc header.

### 10.10. `application.properties`

```properties
spring.application.name=server-swap-lab
server.port=8080

server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json

server.max-http-request-header-size=16KB
server.http2.enabled=false
server.forward-headers-strategy=none

management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
```

Đặt `server.forward-headers-strategy=none` trong lab direct HTTP để **không tin các `X-Forwarded-*` headers do client tự gửi**. Trong production sau trusted proxy, thiết kế `native`/`framework` có kiểm soát và test path/redirect; không blindly tin forwarded host từ Internet.

### 10.11. `application-jetty.properties`

```properties
server.jetty.threads.min=8
server.jetty.threads.max=64
server.jetty.accesslog.enabled=true
server.jetty.accesslog.filename=./logs/jetty-access.log
```

### 10.12. `application-undertow.properties`

```properties
server.undertow.threads.io=2
server.undertow.threads.worker=32
server.undertow.accesslog.enabled=true
server.undertow.accesslog.dir=./logs/undertow
server.undertow.accesslog.pattern=%t %a %r %s (%D milliseconds)
server.undertow.options.server.record-request-start-time=true
```

Các số lượng threads là **lab settings**; phải đo và chỉnh theo CPU, blocking workload, concurrency và platform limits. Cả Jetty và Undertow access logs cần writable paths/quyền/retention; không gửi query tokens/PII vào raw access logs trên production.

## 11. Unit test — business logic không phụ thuộc HTTP server

Tệp `src/test/java/com/example/serverswap/CatalogServiceTest.java`:

```java
package com.example.serverswap;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class CatalogServiceTest {

    private final CatalogService service = new CatalogService();

    @Test
    void correctQuote() {
        assertEquals(
                new CatalogService.Quote(
                        "pen", 2, 12000L, 24000L),
                service.quote("pen", 2));
    }

    @Test
    void invalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote("pen", 0));
    }

    @Test
    void unknownSku() {
        assertThrows(ProductNotFoundException.class,
                () -> service.product("not-found"));
    }
}
```

Ba tests không cần Spring context, Servlet API, Jetty, Undertow hay Tomcat. Nếu chúng fail sau swap, khả năng lớn bạn đã đổi code/dependency business ngoài phạm vi, cần phân tích riêng.

## 12. MockMvc test — kiểm tra MVC contract, chưa kiểm tra HTTP server

Tệp `src/test/java/com/example/serverswap/CatalogControllerMvcTest.java`:

```java
package com.example.serverswap;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
class CatalogControllerMvcTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CatalogService catalog;

    @Test
    void itemMappingAndSerialization() throws Exception {
        given(catalog.product("pen"))
                .willReturn(
                        new CatalogService.Product("pen", 12000L));

        mvc.perform(get("/api/products/pen")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Lab-Contract", "v1"))
                .andExpect(jsonPath("$.sku").value("pen"))
                .andExpect(jsonPath("$.unitPriceVnd")
                        .value(12000));
    }

    @Test
    void invalidRequestIs400() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));
    }

    @Test
    void unknownMethodIs405() throws Exception {
        mvc.perform(post("/api/products/pen"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

`@MockitoBean` thuộc Spring Framework 6.2, có package `org.springframework.test.context.bean.override.mockito`. Test dùng MVC mock servlet objects, **không có live Jetty/Undertow socket**. Nó kiểm tra route, JSON, `@Valid`, error response; cần lớp test tiếp theo để khẳng định server swap thật.

## 13. Live HTTP test — kiểm tra đúng server implementation

Tệp `src/test/java/com/example/serverswap/LiveHttpServerTest.java`:

```java
package com.example.serverswap;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("lab")
class LiveHttpServerTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void selectedServerIsReallyRunning() {
        assertTrue(port > 0);
        ResponseEntity<Map> response =
                http.getForEntity(url("/lab/server"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());

        String expected = System.getenv().getOrDefault(
                "EXPECTED_SERVER", "JettyWebServer");
        assertEquals(expected, response.getBody().get("server"));

        assertEquals(port,
                ((Number) response.getBody().get("port"))
                        .intValue());
        assertEquals("true",
                response.getBody().get("compressionProperty"));
        assertEquals("16KB",
                response.getBody().get(
                        "requestHeaderLimitProperty"));
    }

    @Test
    void catalogContractWorksThroughTcp() {
        ResponseEntity<Map> response =
                http.getForEntity(
                        url("/api/products/pen"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pen", response.getBody().get("sku"));
        assertEquals(12000,
                ((Number) response.getBody()
                        .get("unitPriceVnd")).intValue());
        assertEquals("v1",
                response.getHeaders()
                        .getFirst("X-Lab-Contract"));
        assertEquals("active",
                response.getHeaders()
                        .getFirst("X-Lab-Filter"));
    }

    @Test
    void jsonValidationWorksThroughTcp() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new CatalogController.QuoteRequest("pen", 0),
                        Map.class);

        assertEquals(HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals("INVALID_REQUEST",
                response.getBody().get("code"));
    }

    @Test
    void servletRegistrationIsNotJustMvc() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/raw/ping"), String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("raw-servlet-ok\n", response.getBody());
        assertEquals("active",
                response.getHeaders()
                        .getFirst("X-Lab-Filter"));
    }

    @Test
    void actuatorHealthWorks() {
        ResponseEntity<Map> response =
                http.getForEntity(
                        url("/actuator/health"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("UP", response.getBody().get("status"));
    }

    @Test
    void largePayloadIsReturned() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/api/blob?size=8192"), String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(8192, response.getBody().length());
    }
}
```

**Ý nghĩa test:** `ServletWebServerApplicationContext.getWebServer()` được trả qua HTTP và test so với expected implementation. Trên **Jetty POM** default expected là `JettyWebServer`. Khi đổi sang Undertow, đặt environment variable `EXPECTED_SERVER=UndertowWebServer` trước khi chạy tests; quay về Tomcat dùng `TomcatWebServer`. Đây là **đối chiếu explicit**, không có logic “thấy server nào cũng PASS”.

Tại đây `@ActiveProfiles("lab")` làm diagnostic controller tồn tại trong test. `RANDOM_PORT` khởi động actual embedded server ở port do OS cấp, không dùng cố định 8080. Tests **chưa** xác minh compression được bật trên wire; mục 17 có lệnh `curl` riêng. TestRestTemplate có thể giải nén response tùy HTTP client, vì vậy test `largePayloadIsReturned` chỉ khẳng định response body logic không mất dữ liệu.

### Các ranh giới của live HTTP test

| Test | Kiểm tra được | Chưa kiểm tra |
| --- | --- | --- |
| Unit | Business rules | HTTP stack |
| `@WebMvcTest` + MockMvc | MVC mappings/JSON/validation | Jetty/Undertow listener |
| `@SpringBootTest(RANDOM_PORT)` | Real embedded server, TCP, Servlet dispatch/filter | External proxy/TLS, browser |
| `curl` với `Accept-Encoding` | Response compression trên wire nếu có | p95 under load |
| Deployment smoke | Container image, networking, ingress | Toàn bộ scenarios |
| Load/soak | Throughput/latency/resources theo workload | Mọi security edge case |

## 14. Bước 1: build và chạy Jetty thật

Ở thư mục `server-swap-lab`:

```bash
java -version
mvn -version
mvn clean test
mvn clean package
```

Khi POM đang chọn Jetty, live test kỳ vọng `JettyWebServer`. Build được JAR:

```text
target/server-swap-lab-1.0.0.jar
```

Tạo thư mục access log nếu muốn chạy profile Jetty:

```bash
mkdir -p logs
```

Chạy:

```bash
java -jar target/server-swap-lab-1.0.0.jar \
  --spring.profiles.active=lab,jetty
```

Trong terminal khác:

```bash
curl -sS http://127.0.0.1:8080/lab/server
curl -i http://127.0.0.1:8080/api/products/pen
curl -i http://127.0.0.1:8080/raw/ping
curl -i http://127.0.0.1:8080/actuator/health
```

**Mẫu kết quả được suy ra từ code/config**, không phải kết quả đo thực tế trong môi trường người đọc:

`GET /lab/server` (thứ tự JSON keys không cố định):

```json
{
  "server": "JettyWebServer",
  "port": 8080,
  "contextPath": "",
  "compressionProperty": "true",
  "requestHeaderLimitProperty": "16KB",
  "http2Property": "false"
}
```

`GET /api/products/pen`:

```json
{"sku":"pen","unitPriceVnd":12000}
```

Response có `X-Lab-Contract: v1` và `X-Lab-Filter: active`. `GET /raw/ping` trả body text:

```text
raw-servlet-ok
```

Có ký tự newline sau `raw-servlet-ok` do `write("raw-servlet-ok\n")`. `/actuator/health` trả `{"status":"UP"}` khi health contributors UP.

**Nếu `/lab/server` không trả `JettyWebServer`, dừng và kiểm tra dependency tree/classpath trước khi ghi nhận đã swap.**

### Kiểm tra access log Jetty

Khi `application-jetty.properties` được kích hoạt và đường dẫn writable, Jetty access log được ghi tại file đã cấu hình. Gửi vài requests rồi kiểm tra `./logs/jetty-access.log`. Không có log? Kiểm tra profile, quyền folder, startup warnings, log filename và phiên bản property. Access log **khác** application log (`logging.level.*`); việc log startup xuất hiện không chứng minh access logging hoạt động.

## 15. Bước 2: đổi sang Undertow đúng cách

Sửa POM theo mục 5: **bỏ Jetty starter, thêm Undertow starter**, giữ Tomcat excluded. Không đổi Java source. Kiểm tra:

```bash
mvn clean package
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-undertow
```

Để chạy tests với expected server trên Bash/macOS/Linux:

```bash
EXPECTED_SERVER=UndertowWebServer mvn clean test
```

PowerShell:

```powershell
$env:EXPECTED_SERVER = 'UndertowWebServer'
mvn clean test
Remove-Item Env:EXPECTED_SERVER
```

**Chú ý:** tests đọc environment variable ngay trong test JVM. Nếu chạy CI, set đúng cho test process; không đặt biến cho process app rồi quên cấu hình test.

Tạo folder log rồi chạy Undertow:

```bash
mkdir -p logs/undertow
java -jar target/server-swap-lab-1.0.0.jar \
  --spring.profiles.active=lab,undertow
```

Lưu ý với Maven, nếu bạn chạy `mvn clean package` **trước** khi set `EXPECTED_SERVER`, Maven sẽ chạy tests mặc định kỳ vọng Jetty và có thể fail. Cách đúng theo thứ tự:

```bash
EXPECTED_SERVER=UndertowWebServer mvn clean package
```

PowerShell:

```powershell
$env:EXPECTED_SERVER = 'UndertowWebServer'
mvn clean package
Remove-Item Env:EXPECTED_SERVER
```

Kỳ vọng `/lab/server` có `"server":"UndertowWebServer"` và các contract HTTP vẫn như Jetty:

- `/api/products/pen`: 200, JSON item, `X-Lab-Contract: v1`.
- `/api/quotes` valid: 200, JSON quantity/total.
- `/api/quotes` invalid: 400 với stable error code.
- `/raw/ping`: 200 từ Servlet ngoài MVC.
- `/actuator/health`: UP khi healthy.
- `X-Lab-Filter: active` trên HTTP requests.

Nếu app chỉ start khi đồng thời có Jetty và Undertow, đó là dấu hiệu POM/configuration sai, không phải giải pháp. Mục tiêu là **một server choice được xác minh rõ ràng**.

### Quan sát Undertow access logs

Theo profile Undertow, log path là `./logs/undertow`. Pattern `%D` có timing khi `record-request-start-time` được bật. Kiểm tra file sinh thật sau requests và đối chiếu thời gian, không so đơn vị trực tiếp với Tomcat Jetty mà chưa chuẩn hóa.

## 16. Bước 3: quay lại Tomcat để có baseline

Nếu muốn có A/B giữa ba engines, khôi phục starter-web mặc định:

- Bỏ `<exclusions>` Tomcat trong `spring-boot-starter-web`.
- Bỏ `spring-boot-starter-jetty`/`spring-boot-starter-undertow`.
- Nếu cần server-specific settings Tomcat, cấu hình lại theo **`server.tomcat.*`**, không cố tái sử dụng Jetty/Undertow keys.

Chạy:

```bash
EXPECTED_SERVER=TomcatWebServer mvn clean package
```

Mở artifact với `--spring.profiles.active=lab` để chỉ có chung properties. Kỳ vọng `/lab/server` trả `"TomcatWebServer"`.

**Tại sao phải test cả đường rollback?** Khi production gặp lỗi hiếm trong Jetty/Undertow, rollback phải trả lại artifact/classpath/properties nhất quán. Chỉ chỉnh một dependency mà còn settings của server cũ có thể khiến performance/limits khác baseline.

## 17. Kiểm tra cấu hình THỰC bằng HTTP, log và metrics

### 17.1. Kiểm tra HTTP status/header/JSON

```bash
curl -i http://127.0.0.1:8080/api/products/pen

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":2}'

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":0}'

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: text/plain" \
  --data 'sku=pen&quantity=2'
```

Kỳ vọng ở demo khi không có security/proxy chặn trước:

| Request | Status | Nội dung |
| --- | --- | --- |
| GET `/api/products/pen` | 200 | JSON `{"sku":"pen","unitPriceVnd":12000}` |
| POST quote quantity 2 | 200 | JSON totalVnd 24000 |
| POST quote quantity 0 | 400 | `{"code":"INVALID_REQUEST"}` |
| POST quote Content-Type text/plain | 415 | Unsupported Media Type |
| GET `/api/products/missing` | 404 | `{"code":"PRODUCT_NOT_FOUND"}` |
| GET `/raw/ping` | 200 | `raw-servlet-ok` + newline |

Body thành công của quote:

```json
{"sku":"pen","quantity":2,"unitPriceVnd":12000,"totalVnd":24000}
```

JSON key order không được bảo đảm; dùng JSONPath hoặc schema-aware assertions thay vì so string order. Nếu 415 thành 403 khi bật Security/CSRF, đó là dấu hiệu request bị chặn ở tầng trước controller; phân tích theo chain chứ đừng vô hiệu hóa security chỉ để đạt đúng mã 415.

### 17.2. Kiểm tra compression qua actual bytes

Lab cấu hình:

```properties
server.compression.enabled=true
server.compression.min-response-size=1KB
server.compression.mime-types=text/plain,application/json
```

Gửi request có `Accept-Encoding`:

```bash
curl -sS -D - -o /dev/null \
  -H "Accept-Encoding: gzip" \
  http://127.0.0.1:8080/api/blob?size=8192

curl -sS --compressed -D - -o /dev/null \
  http://127.0.0.1:8080/api/blob?size=8192
```

Quan sát `Content-Encoding: gzip` khi server chọn gzip; `curl --compressed` tự giải nén body nếu lưu/in ra. Kết quả phụ thuộc HTTP engine, response metadata, transfer encoding và request. Không kết luận “compression enabled” chỉ từ `/lab/server` trả `"true"`.

**Khi cần so bandwidth:** đo raw compressed bytes/Content-Length/transfer encoding cẩn thận; `curl -w '%{size_download}'` cho số bytes payload được tải theo request, nhưng không đồng nhất với tổng on-wire TCP overhead. Đừng dùng test thiếu `Accept-Encoding` để kết luận gzip không hoạt động.

### 17.3. Kiểm tra giới hạn request header

`server.max-http-request-header-size=16KB` là config chung, nhưng cách tính limits và error handling **khác theo implementation**. Tài liệu Boot 3.5 nêu Tomcat tính giới hạn kết hợp request line + headers, trong khi một số runtime khác áp dụng khác.

Quy trình an toàn:

1. Chạy app trên localhost/staging, không thử trực tiếp production.
2. Tạo requests nhỏ hơn và lớn hơn ngưỡng, với headers synthetic không chứa secrets.
3. Quan sát status 200/4xx, startup logs và access logs.
4. Xem liệu 400/431/connection close do server nào trả; không hardcode một status chung cho mọi container.
5. Kiểm tra ingress/proxy header limits vì upstream có thể chặn trước backend.
6. Ghi actual threshold **bằng bytes** và request-line component, không chỉ config `"16KB"`.

Dùng các tools như `curl`/HTTP client được kiểm soát, không flood đồng thời để ép server cạn tài nguyên. **Header limit config được bind không đồng nghĩa HTTP parser đã thực thi đúng cùng nghĩa trên Jetty/Undertow/Tomcat**.

### 17.4. Access logs: cả 3 server có namespaces khác

- Tomcat: `server.tomcat.accesslog.enabled`, `server.tomcat.accesslog.pattern`, `server.tomcat.basedir`.
- Jetty: `server.jetty.accesslog.enabled`, `server.jetty.accesslog.filename`, `server.jetty.accesslog.format`.
- Undertow: `server.undertow.accesslog.enabled`, `server.undertow.accesslog.dir`, `server.undertow.accesslog.pattern`, và `server.undertow.options.server.record-request-start-time` khi pattern `%D` cần timing.

Lưu cả **config, file path, example sanitized line, rotation** vào bằng chứng. Không mở access logs cho toàn bộ request URI nếu URI chứa tokens/PII; chọn format và redaction policy thích hợp. Tomcat/Jetty/Undertow có semantics thời gian/format khác nhau.

### 17.5. Micrometer/Actuator và meter names

Micrometer/Spring Boot Actuator ghi HTTP request observations, JVM memory/GC/threads và các server-specific meters khi conditions phù hợp. **Không giả định tất cả `tomcat.*` metrics còn tồn tại sau khi chuyển sang Jetty**. Jetty có metrics riêng cho ThreadPool/Connector; Undertow cung cấp cơ chế instrumentation khác, khả năng xuất metrics còn phụ thuộc registry/instrumentation.

Đối với Tomcat, `server.tomcat.mbeanregistry.enabled=true` có thể cần để bật một số Tomcat MBeans/metrics; setting này **không có tác dụng mở Jetty MBeans**. Kiểm tra actual registered meters và dashboards/alerts khi swap.

Lab mặc định chỉ expose `/actuator/health`/`info`. Nếu cần `/actuator/metrics` để chẩn đoán, chỉ bật trong môi trường được bảo vệ:

```properties
management.endpoints.web.exposure.include=health,info,metrics
```

Sau thử nghiệm, thu hẹp lại. Đừng public `/actuator/env`, `configprops`, `mappings`, `heapdump`, `loggers`, `shutdown` chỉ để tiện so sánh. Giá trị `configprops` có thể cần sanitize/role-based access, không được dump secrets.

## 18. HTTP/2: không chỉ là `server.http2.enabled=true`

Spring Boot 3.5 có property:

```properties
server.http2.enabled=true
```

Tài liệu nêu có thể dùng **h2** (HTTP/2 qua TLS) và **h2c** (HTTP/2 cleartext) khi runtime hỗ trợ. Tuy vậy actual protocol phụ thuộc server-specific modules/ALPN/TLS/client/proxy:

- **Tomcat 10.1:** hỗ trợ h2/h2c với Boot setup tương thích.
- **Jetty 12:** để hỗ trợ HTTP/2 qua TLS, có thể cần thêm module `org.eclipse.jetty.http2:jetty-http2-server` và ALPN support (`org.eclipse.jetty:jetty-alpn-java-server` cho JDK ALPN theo docs); h2c có dependency requirements khác, xem exact target version.
- **Undertow 2.3:** docs Boot 3.5 nói hỗ trợ h2c/h2; vẫn cần kiểm chứng negotiated protocol.
- **Reactor Netty:** thuộc reactive stack, không phải Jetty/Undertow MVC trong bài.

Ví dụ dependencies Jetty HTTP/2 khi **thật sự** bật TLS h2 (đây là snippet bổ sung cho POM Jetty, không cần cho demo HTTP/1.1):

```xml
<dependency>
    <groupId>org.eclipse.jetty.http2</groupId>
    <artifactId>jetty-http2-server</artifactId>
</dependency>
<dependency>
    <groupId>org.eclipse.jetty</groupId>
    <artifactId>jetty-alpn-java-server</artifactId>
</dependency>
```

Dùng Boot BOM quản lý versions khi có. Cần cấu hình `server.ssl.*`/certificate phù hợp và client có HTTP/2 support; đừng thêm TLS keys giả vào repo. Để kiểm tra:

```bash
curl -V
curl -vk --http2 https://localhost:8443/api/products/pen
```

Lệnh chỉ **minh họa sau khi bạn đã thiết lập HTTPS listener ở 8443**, không thuộc cấu hình POM demo mặc định. Đọc dòng HTTP version negotiated trong output và kết quả TLS trust. Nếu proxy terminate TLS, client có thể nói h2 với proxy nhưng proxy nói HTTP/1.1 với backend; đo đúng **hop**. Với h2c, dùng client h2c phù hợp và xác minh end-to-end, không xem `server.http2.enabled` là bằng chứng.

## 19. Security/URL parsing/session khác nhau giữa containers

### 19.1. Encoded slashes và đường dẫn đặc biệt

Các servers có defaults khác cho percent-encoded characters, `/%2F`, `;`, path parameters, request lines và invalid UTF-8. Undertow có `server.undertow.decode-slash` và các options; docs cảnh báo decoding encoded slash có **rủi ro bảo mật** nếu reverse proxy không thực hiện cùng cách.

Phải test path traversal, URL canonicalization, encoded slash, duplicate slash, semicolon/matrix params và security path matchers theo policy. **Không nới relaxed path chars/slash decode chỉ để làm test 404 biến thành 200**. Cả ingress lẫn application server cần cùng mô hình normalize URL để tránh bypass authorization.

### 19.2. Cookies và session

Kiểm tra `Set-Cookie`, `JSESSIONID` Path/Domain/Secure/HttpOnly/SameSite, session creation, redirects, CSRF và login callbacks. Một server có thể serialize session/track session IDs khác khi config không explicit. Nếu có Spring Session/Redis, check repository integration và multi-replica behavior; local live test không thay browser/staging E2E.

### 19.3. Servlet filters và non-MVC routes

Custom Servlet/Filter/Jersey may be registered differently depending on configuration. Lab `GET /raw/ping` cho phép xác nhận container Servlet routing không phụ thuộc MVC `DispatcherServlet`. `X-Lab-Filter` trên `/raw/ping` cho biết Filter bean được registered trên actual HTTP request path.

### 19.4. Multipart, form post, large headers

Tomcat/Jetty/Undertow có form-post limits, multipart part limits và temp directories khác. Trong Boot 3.5 appendix, các keys được chứng thực gồm `server.jetty.max-http-form-post-size`, `server.undertow.max-http-post-size` và `server.tomcat.max-http-form-post-size` (semantics không hoàn toàn giống nhau). Khi upload lớn, còn có reverse proxy body size/timeout, disk quota, temp dir và Servlet multipart configuration. Cần test file size boundaries bằng dữ liệu synthetic, không tải files nhạy cảm hoặc gây quá tải.

### 19.5. Graceful shutdown và keep-alive

Các engines có connector timeout/keep-alive/connection draining khác nhau. Khi chuyển server, check shutdown `SIGTERM`, readiness fail, requests đang chạy được hoàn tất, pool threads/socket đóng và Kubernetes grace period đủ. Đừng đo sự an toàn chỉ bằng việc `/actuator/health` trả 200 khi app vừa start.

## 20. Servlet MVC, WebFlux và external WAR: ba câu hỏi khác nhau

### 20.1. Nếu đang dùng Spring MVC

Chọn server bằng dependency swap ở mức Servlet starter:

```text
spring-boot-starter-web -> exclude spring-boot-starter-tomcat
                        -> add spring-boot-starter-jetty
                         OR spring-boot-starter-undertow (Boot 3.5)
```

`DispatcherServlet`/Jakarta APIs vẫn là web stack hiện tại.

### 20.2. Nếu ứng dụng đang dùng Spring WebFlux

`spring-boot-starter-webflux` mặc định mang **Reactor Netty**. Boot 3.5 docs cho phép thay reactive HTTP server bằng Tomcat/Jetty/Undertow khi dependencies và reactive adapters phù hợp, nhưng thao tác phải **exclude `spring-boot-starter-reactor-netty`**, chọn reactive-compatible server và xác minh application type. Không dùng công thức `exclude starter-tomcat` từ MVC trên WebFlux mặc định.

Nếu có cả web và webflux starters, Boot thường chọn MVC inbound; sự hiện diện của `WebClient` không chứng minh inbound đã là WebFlux. Khi chủ đích dùng reactive runtime, kiểm tra `spring.main.web-application-type` và WebFlux-specific tests/metrics.

### 20.3. Nếu muốn deploy WAR vào server bên ngoài

Đó là **traditional WAR deployment**, khác embedded swap. Cần `SpringBootServletInitializer`, `<packaging>war</packaging>`, container `provided`, Jakarta Servlet version và external context path. External Tomcat/Jetty/app server quản lý connectors; các `server.jetty.*` properties của embedded Jetty không tự cấu hình external Jetty đang chạy.

**Không cố sửa cả web framework, packaging và server engine trong cùng một thay đổi khi không bắt buộc.** Tách PR/feature flag, có baseline cho từng boundary.

## 21. Đo hiệu năng và ra quyết định server bằng dữ liệu

Không có “Jetty luôn nhanh hơn Tomcat” hay “Undertow luôn dùng ít RAM hơn” đúng cho mọi workload. Khác biệt phụ thuộc CPU cores, Java version, allocation/GC, blocking JDBC, response size, TLS, HTTP/2, request rate và cấu hình threads/buffers.

### Thiết kế thử nghiệm công bằng

1. Chốt Java/OS/container image, resource limits CPU/RAM và dependencies version.
2. Cùng ứng dụng/service/DB, cùng dataset, traffic mix GET/POST và validation errors.
3. Cùng đường đo (direct HTTP hoặc qua proxy) và network conditions.
4. Thực hiện warm-up rồi đo steady-state, peak/burst và soak phù hợp.
5. So **achieved RPS**, p50/p95/p99 latency, error rate, throughput, CPU, RSS, heap/GC, active threads/sockets, pool waits.
6. Dùng repeated runs và confidence intervals khi sự khác biệt nhỏ; random noise không thành quyết định kiến trúc.
7. Đo trước–sau từng cấu hình riêng (không thay server + tăng CPU + đổi DB query đồng thời).
8. Xác định SLO/operational cost và maintainability/security updates của target server.

### Thread tuning không phải phép đổi đơn vị

- Tomcat: connector threads/max connections/accept queue.
- Jetty: thread pool max/min, selector/acceptor threads, max connections.
- Undertow: I/O threads và worker threads, XNIO options/direct buffers.

Một servlet handler blocking ở JDBC có thể cần worker concurrency phù hợp; quá nhiều worker threads lại gây context-switch/memory/DB pressure. Không “tăng threads tới 1000” thay cho việc phân tích pool/cpu/DB. Nếu dùng Java virtual threads, các server-specific pool keys có thể không còn tác dụng như cách platform threads làm; đọc target version docs.

### Dấu hiệu production regression sau swap

- 4xx/5xx increase do parser/header/path changes.
- p95/p99 tăng trong peak dù average vẫn ổn.
- `Queue full`/connection resets/timeout sau proxy.
- Multipart upload 413/400 do form limits khác.
- Session redirects/cookie paths lỗi.
- Actuator metrics/server-specific dashboards biến mất.
- Access logs không được lưu hoặc bị rotate khác.
- Memory native/direct buffers/threads tăng bất thường.
- HTTP/2/TLS handshake errors.
- Graceful shutdown không hoàn tất request.

## 22. Troubleshooting: chẩn đoán theo tầng

| Hiện tượng | Giả thuyết | Hành động |
| --- | --- | --- |
| POM thêm Jetty nhưng `/lab/server` trả Tomcat | Tomcat starter chưa bị exclude | `mvn dependency:tree`, loại đúng dependency |
| Jetty và Undertow cùng tồn tại | Hai starters được thêm | Chọn một, build sạch |
| Runtime server là Undertow nhưng profile `jetty` active | Profiles không chọn engine | Đồng bộ profile và classpath |
| Server start nhưng `server.tomcat.*` được Environment đọc | Property cũ không tác động tới Jetty | Chuyển config theo namespace hiện tại |
| Jetty threads mặc định vẫn 200 | `application-jetty.properties` chưa active | Check active profiles và effective bindings |
| Undertow access log không có timing | Thiếu record-request-start-time | Bật option đúng, verify `%D` |
| Không tìm thấy access log | Directory/filename/profile/permissions | Kiểm tra config/log path, request đã gửi |
| Compression property true nhưng response không gzip | Accept-Encoding, size, MIME, buffering | Test `/api/blob` với request header gzip |
| Gzip có với Jetty nhưng không với Undertow | Behavior/config khác hoặc proxy | So headers, actual bytes và server docs |
| HTTP/2 không negotiate | Thiếu SSL/Jetty modules/ALPN/client | Xác minh h2/h2c, dùng curl có HTTP2 |
| `/raw/ping` 404 còn MVC OK | Servlet registration/mapping issue | Live HTTP test Servlet path |
| Invalid JSON 500 thay 400 | Advice/converter/server filter mismatch | Test negative contract, logs |
| Header limit status không giống | Container parser semantics khác | So actual policy, không hardcode 431 |
| Encoded slash hoạt động khác | URL decoder/Servlet container policy | Chuẩn hóa routing/security, không relax vô điều kiện |
| Security 403 chỉ sau swap | Session/cookie/filter/CSRF/proxy path | Compare auth chain và cookies |
| Startup error `NoSuchMethodError` Jetty | Jetty modules/BOM version mismatch | Loại pin versions, inspect dependencies |
| Undertow không tìm thấy trên Boot 4 | Starter support removed | Dùng Boot3.5 hoặc supported Boot4 engine |
| `RANDOM_PORT` test PASS dù engine sai | Test không assert actual server | Assert `/lab/server` with expected |
| Production metrics tomcat.* biến mất | Server đã đổi | Update monitoring cho Jetty/Undertow |
| App chạy direct nhưng ingress 502 | Port readiness/proxy connector | Deployed smoke via gateway |
| Load test tệ hơn khi tăng workers | Blocking DB/CPU/GC contention | Profile toàn hệ thống |
| `Server` header vẫn ghi Tomcat qua proxy | Proxy/header cache hoặc client hit nhầm service | Probe backend class và port |
| Test green khi context là MOCK | Không start HTTP listener | `@SpringBootTest(RANDOM_PORT)` |

Không chỉnh global configs mù quáng khi gặp 400/404/500. Xác nhận request được server nào xử lý, có đến MVC hay bị container/proxy chặn trước, và kiểm chứng bằng log/trace có correlation ID.

## 23. Bài tập thực hành và đáp án định hướng

### Bài A — đổi dependency nhưng quên exclusion

Thêm Jetty starter vào project `starter-web` mặc định nhưng không exclude Tomcat. Dự đoán trạng thái dependency tree và runtime. Đáp án: có hai server starter trên classpath, kết quả không đáp ứng “một server đã được chọn rõ”; sửa exclusion và kiểm tra `/lab/server`.

### Bài B — gửi profile sai engine

Build Undertow nhưng chạy `--spring.profiles.active=lab,jetty`. Kiểm tra `/lab/server` và access logs. Đáp án: server **vẫn Undertow**; Jetty properties không thể “chuyển” engine hoặc chỉnh Undertow worker. Sửa profile theo engine và test config.

### Bài C — kiểm tra 16KB header limit

Tạo hai HTTP requests có synthetic header vừa dưới/vượt ngưỡng. So Tomcat, Jetty, Undertow về status, connection close và thời gian nhận error. Đáp án: ngưỡng/đơn vị và cách tính request line/headers có thể khác, không assert cùng status/byte count nếu tài liệu target không bảo đảm.

### Bài D — kiểm tra Jetty access log

Bật `server.jetty.accesslog.enabled`, chọn filename có write permission, gửi `/api/products/pen`, kiểm tra file thực. Đáp án: startup log không phải access log, phải nhìn thấy request đã ghi.

### Bài E — kiểm tra Undertow `%D`

Bật Undertow access log pattern có `%D` nhưng quên `server.undertow.options.server.record-request-start-time=true`. Đối chiếu timing; sau đó bật option và test lại. Đáp án: record-request-start-time cần cho pattern đo duration theo docs.

### Bài F — server swap và Servlet registration

Xóa `RawServletConfiguration` và chạy lại `LiveHttpServerTest`. `@WebMvcTest` có thể vẫn PASS cho MVC, nhưng live `/raw/ping` fail. Đáp án: tests cần phủ cả container routing.

### Bài G — `Server` header bị proxy sửa

Dùng một reverse proxy giả định thêm `Server: gateway`. So HTTP header và `/lab/server`. Đáp án: header không chứng minh backend class; endpoint diagnostic chỉ dùng local/secured test.

### Bài H — bật HTTP/2

Đọc docs Jetty HTTP2/ALPN, thêm module phù hợp, thiết lập TLS test certificate, dùng `curl -V`, `curl --http2` rồi quan sát protocol thực. Đáp án: flag `server.http2.enabled=true` không đủ để nói client đã sử dụng h2.

### Bài I — so tải công bằng

Cho Jetty max threads 64, Undertow I/O=2/worker=32. Lập kế hoạch load test với cùng request mix/CPU/DB/duration, đo p95/p99 và errors. Đáp án: không kết luận nhanh/chậm từ hai con số threads không cùng semantics.

### Bài J — chuyển Boot 3.5 → Boot 4

Nêu lại matrix: Boot4 cần Servlet6.1, Jetty12.1/Tomcat11; Undertow starter support removed. Đáp án: không copy `spring-boot-starter-undertow` của Boot3.5 sang Boot4 rồi kỳ vọng supported startup.

### Bài K — rollback về Tomcat

Bỏ Jetty/Undertow, khôi phục Tomcat default, đặt `EXPECTED_SERVER=TomcatWebServer`, chạy Maven tests và HTTP smoke. Đáp án: rollback cần đồng bộ dependency **và** server-specific settings.

### Bài L — thử encoded slash

Gửi URL có `%2F` vào local test environment và xem server/proxy/application routing. Đáp án: parser/security normalization cần consistent giữa hops, không cho phép encoded slash tùy tiện vì có nguy cơ bypass.

## 24. Checklist giao nộp một lần server swap

### Build/dependency

- [ ] Java, Spring Boot, Servlet engine versions nằm trong supported matrix.
- [ ] Chỉ một embedded servlet server starter trong dependency graph.
- [ ] `starter-web` vẫn còn cho MVC, Tomcat exclusion đúng.
- [ ] Không pin/override transitive Jetty/Tomcat/Undertow libraries trái Boot BOM.
- [ ] Build clean và inspect executable JAR/dependency tree.
- [ ] Nếu dùng Boot4, không dùng Undertow như một supported starter.
- [ ] Có artifact + commit ID + JDK + image digest để rollback.

### Runtime/config

- [ ] HTTP server class thực khớp expected qua live test.
- [ ] Port/context path/bind address chính xác; không tin chỉ `Server` header.
- [ ] `server.*` config chung được bound; behavior thực được kiểm chứng.
- [ ] Không còn `server.tomcat.*` vô tác dụng khi chạy Jetty/Undertow.
- [ ] Jetty/Undertow thread, queue, buffer, keep-alive có capacity plan.
- [ ] Access logs thực sự được ghi/rotate với privacy policy.
- [ ] Compression được test qua Accept-Encoding, body size, content type.
- [ ] HTTP/2 nếu yêu cầu được test qua đúng TLS/proxy hop.
- [ ] Header/form/upload limits, URL encoding và session/cookies được test.
- [ ] Actuator health, metrics/alerts, readiness và graceful shutdown còn đúng.
- [ ] Diagnostic endpoint `@Profile("lab")` không public ở production.

### QA và rollout

- [ ] Unit tests business logic pass.
- [ ] MVC MockMvc tests validation/JSON/status pass.
- [ ] Live HTTP `RANDOM_PORT` tests assert **actual server class**, Servlet and Filter registration.
- [ ] `curl` negative cases 400/404/405/415, compression và context path được kiểm tra.
- [ ] Security auth, CSRF, CORS, proxy headers được thử trên staging nếu có.
- [ ] Representative load test so p95/p99/error rate + CPU/GC/memory/pools.
- [ ] Canary/blue-green deployment, health/smoke, logs/metrics và rollback trigger cụ thể.
- [ ] Đã thử rollback về server cũ, không chỉ có kế hoạch trên giấy.

## 25. Tài liệu chính thức tham khảo

- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): đổi server starter, HTTP compression, HTTP/2, access logs, forwarded headers, WebServerFactoryCustomizer.
- [Spring Boot 3.5.16 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java 17+, Tomcat10.1/Jetty12.0/Undertow2.3 và Servlet6.0.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `server.*`, `server.jetty.*`, `server.undertow.*`, `server.tomcat.*`.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC and servlet/filter registrations.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc, `RANDOM_PORT`, TestRestTemplate.
- [Spring Boot 3.5 — Actuator Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): JVM/HTTP/Jetty/Tomcat metric capabilities.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): health, exposure, metrics/security.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Servlet6.1 baseline, Undertow removal.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): Jetty12.1, Tomcat11, supported Servlet6.1.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): giả lập MVC request/response không mở cổng.
- [Jetty 12 Documentation](https://jetty.org/docs/jetty/12/): Jetty connectors, thread pool, HTTP/2 và ALPN.
- [Undertow Documentation](https://undertow.io/): handler, XNIO worker, options/HTTP.
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): kiểm tra dependency graph.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): URL mapping, filters, sessions và lifecycle.

**Kết luận:** Thay Tomcat bằng Jetty/Undertow trong Spring Boot MVC là một thay đổi **dependency + runtime configuration + verification**. Một POM có Jetty không đủ; phải chứng minh Jetty/Undertow **thực sự đang nghe HTTP**, config engine-specific phù hợp, Servlet/Filter/JSON/error contract còn nguyên, logs/metrics/limits/HTTP2 an toàn và performance đáp ứng SLO. Thực hành trên Boot **3.5.16** vì có đủ ba engines; nếu lên Boot **4**, kiểm tra lại server support matrix trước khi chọn.