# @LocalServerPort và khám phá cổng do máy chủ cấp phát trong kiểm thử Spring Boot web runtime

## 1. Vì sao kiểm thử HTTP cần biết cổng thực tế?

Một ứng dụng Spring Boot thường lắng nghe ở `8080` khi chạy độc lập. Nhưng bộ kiểm thử có thể đang chạy song song với một instance phát triển, một test khác, một service trong Docker hoặc một process đã chiếm cổng đó. Nếu integration test luôn gọi `http://localhost:8080`, test có thể:

- Thất bại vì `BindException: Address already in use`.
- Gọi nhầm **một ứng dụng khác** đang chạy trên máy.
- Vượt qua test vì endpoint trùng tên ở instance cũ.
- Chạy được trên máy người viết nhưng thất bại trên CI.
- Tranh chấp cổng khi nhiều test forks/builds chạy song song.

Giải pháp trong Spring Boot là **để web server bind vào cổng do hệ điều hành cấp phát**, sau đó **đọc cổng thực đã bind** để gửi HTTP request thật. Trong test, cặp thành phần quan trọng nhất là:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpTest {

    @LocalServerPort
    int port;
}
```

Với **Spring Boot 3.3.x**, import đúng là:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
```

Bài học tập trung vào **kiểm thử web runtime**, không phải chọn một cổng “ngẫu nhiên” cho mọi mục đích. Các ví dụ dùng **Java 21, Spring Boot 3.3.13, JUnit Jupiter 5, Gradle**, tương thích kiến thức Java 17+. Đặc biệt phải phân biệt giữa `server.port`, `local.server.port`, cổng HTTP application, cổng HTTP management, và cổng của container hoặc upstream service.

## 2. Ba khái niệm: configured port, bound port, test port injection

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `server.port` | `8080`, `9090`, `0` | Giá trị cấu hình để embedded server **thử bind** |
| **Bound/local server port** | `49317` | Cổng **thực tế** mà socket web server đang lắng nghe |
| `local.server.port` | `49317` | Thuộc tính được Spring Boot công bố **sau khi server khởi tạo** |
| `@LocalServerPort` | `int port` | Annotation test inject giá trị từ `local.server.port` |
| `management.server.port` | `9091` | Cổng cấu hình riêng của management server, nếu dùng |
| `local.management.port` | `49318` | Cổng management **đã bind**, khi có management web server |
| `@LocalManagementPort` | `int managementPort` | Annotation đọc `local.management.port` trong test |

Khi `server.port=8080`, configured port và bound port thường cùng là 8080 nếu startup thành công. Khi `server.port=0`, configured port vẫn có ý nghĩa là **“hãy để OS chọn một cổng phù hợp”**, chứ không biến thành một giá trị cấu hình cố định mới sau startup.

Ví dụ:

```text
Trước khi khởi động:
  server.port = 0

Hệ điều hành bind socket:
  actual listening port = 49317

Sau khi server khởi tạo:
  local.server.port = 49317

Test:
  @LocalServerPort int port = 49317
```

Số `49317` chỉ là minh họa. Trên máy khác hoặc lần chạy khác có thể nhận cổng khác; **không khẳng định lần nào cũng khác nhau** vì OS có thể tái sử dụng một cổng vừa giải phóng.

## 3. OS cấp cổng khi `bind(0)`, không phải Spring tự bốc số tùy ý

TCP/HTTP server muốn nhận connections phải bind địa chỉ IP và cổng. Khi ứng dụng chỉ định **port 0**, socket API yêu cầu hệ điều hành chọn một cổng khả dụng trong phạm vi được phép của hệ thống. Hệ điều hành thực hiện việc chọn và bind trong cùng thao tác cấp tài nguyên socket.

```text
Spring Boot context startup
    |
    v
Embedded Tomcat / Jetty / Undertow / Reactor Netty
    |
    v
Bind listen socket with requested port 0
    |
    v
Operating system picks an available port and binds socket
    |
    v
WebServer.getPort() -> actual positive port
    |
    v
Boot publishes local.server.port
    |
    v
Test receives @LocalServerPort and calls HTTP endpoint
```

Đừng gọi thuật toán này là “Spring sinh số random bằng `Random.nextInt`”. Khác biệt quan trọng là **OS vừa chọn vừa giữ socket**. Nếu code test tự tìm port rảnh rồi đóng socket để đưa số ấy cho server, giữa hai thời điểm có một **race condition** mà process khác có thể chiếm cổng.

Một cổng “rảnh lúc kiểm tra” không bảo đảm “rảnh lúc Spring Boot bind”. Dùng `server.port=0`/`RANDOM_PORT` tránh bước check-and-reuse không an toàn.

**Giới hạn:** Random port giảm tranh chấp cổng của web server thử nghiệm, **không bảo đảm** database schema, Kafka topic, file path, cache, shared static state, management port hoặc tài nguyên bên ngoài khác cũng độc lập.

## 4. Bốn chế độ `@SpringBootTest.webEnvironment` trong Spring Boot 3.3

| Giá trị | Embedded HTTP server thật? | Cách kiểm thử phù hợp | `@LocalServerPort`? |
| --- | --- | --- | --- |
| `MOCK` (mặc định) | **Không** | `MockMvc`, WebTestClient mock-bound; kiểm tra MVC handler/service | Không có bound HTTP port của test |
| `RANDOM_PORT` | **Có** | HTTP client thật gọi socket local do OS chọn | Có |
| `DEFINED_PORT` | **Có** | HTTP client thật gọi cổng cấu hình hoặc mặc định 8080 | Có thể dùng sau startup; thường không cần |
| `NONE` | **Không** | Kiểm thử application context hoặc non-web components | Không |

Ví dụ phân biệt:

```java
@SpringBootTest
class MockByDefaultTest {
    // MOCK: không tự tạo HTTP listener.
}
```

và:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RunningServerTest {
    @LocalServerPort
    int port;
}
```

**`MOCK` không phải một server đang lắng nghe trên localhost**. Với `MockMvc`, request được dispatch trong web application context giả lập, thường không đi qua TCP, TLS, socket accept queue hoặc web container theo đúng cách một HTTP request thực.

Chọn `RANDOM_PORT` khi hành vi cần kiểm tra phụ thuộc vào web runtime thật: network listener, Servlet container, HTTP status/headers, actual codecs, filters, error dispatch, cookies, redirect, compression và tương tác HTTP client–server. Chọn `MOCK` khi chỉ cần xác nhận controller mappings và logic web mà không cần network.

## 5. `RANDOM_PORT` tương đương gì với `server.port=0`?

Trên Spring Boot 3.3, `@SpringBootTest(webEnvironment = RANDOM_PORT)` tạo một **web server application context** và đặt cấu hình test làm embedded HTTP server chọn cổng động, về bản chất là `server.port=0`.

```text
@SpringBootTest(RANDOM_PORT)
    |
    v
Test context loads Spring Boot app
    |
    v
Test bootstrapping applies server.port=0
    |
    v
Web server starts and binds actual port
    |
    v
local.server.port becomes available
    |
    v
Test field @LocalServerPort receives actual port
```

Còn trong application bình thường, có thể ghi:

```properties
server.port=0
```

để chạy một process **không phải test** trên cổng được OS cấp. Tuy nhiên `@LocalServerPort` là annotation hỗ trợ **test**, không phải cơ chế khuyến nghị để application beans lấy cổng ngay trong construction.

**Tránh nhầm `server.port=0` với không có server:** cổng bằng 0 là yêu cầu **tạo web server trên cổng OS chọn**. Trong Spring Boot, `server.port=-1` là một cơ chế khác để tắt HTTP endpoints trong những cấu hình web context phù hợp; `webEnvironment=NONE` còn khác nữa vì không tạo web environment.

## 6. `@LocalServerPort` hoạt động thế nào?

Trong Spring Boot 3.3, `@LocalServerPort` nằm tại:

```java
org.springframework.boot.test.web.server.LocalServerPort
```

Annotation này là shortcut tương đương:

```java
@Value("${local.server.port}")
```

trên test field hoặc supported injection point. Ví dụ test có thể viết:

```java
@LocalServerPort
int port;
```

hoặc:

```java
@Value("${local.server.port}")
int port;
```

Điểm quan trọng: **`local.server.port` được công bố sau khi HTTP server khởi tạo**, còn `server.port` là giá trị cấu hình đầu vào. `ServerPortInfoApplicationContextInitializer` của Spring Boot lắng nghe `WebServerInitializedEvent` để đưa cổng thực vào `Environment`.

Vì vậy trong một test đã load xong context, `@LocalServerPort` thường có cổng thực dương. Nhưng trong constructor của một `@Configuration`/`@Bean` bình thường, server có thể chưa start và property này có thể **chưa tồn tại**. Không biến một test-only convenience annotation thành dependency của application startup.

## 7. Chuỗi lifecycle chính xác cần nhớ

```text
JUnit bắt đầu test class
   |
   v
Spring TestContext/bootstrapper
   |
   v
Tạo Spring ApplicationContext và đăng ký properties
   |
   v
Tạo beans / cấu hình embedded web server
   |
   v
Embedded web server bind port 0
   |
   v
WebServerInitializedEvent được phát
   |
   v
local.server.port được cung cấp trong Environment
   |
   v
Spring inject test instance fields (ví dụ @LocalServerPort)
   |
   v
@BeforeEach và @Test chạy
```

Sơ đồ thể hiện **vòng đời logic**, thứ tự chính xác của một số Spring callbacks có thể khác theo context/registration. Hợp đồng quan trọng là **field trong test sử dụng sau khi `@SpringBootTest(RANDOM_PORT)` startup hoàn tất**, không phải đọc giá trị trong static field initializer hoặc application bean lúc chưa bind socket.

**Không lấy cổng ở `@BeforeAll` static theo cách chưa có test instance**, trừ khi cấu hình JUnit lifecycle cho phép và test context đã sẵn sàng, vẫn phải xác nhận injection. Cách đơn giản và đáng tin nhất là dùng **instance field** trong `@Test` hoặc `@BeforeEach`.

## 8. Project Spring Boot MVC chạy được: cấu trúc

Một app nhỏ để minh họa full HTTP integration test:

```text
build.gradle
src/main/java/com/example/portdemo/
  PortDemoApplication.java
  PingController.java
src/main/resources/application.properties
src/test/java/com/example/portdemo/
  RandomPortHttpTest.java
```

Yêu cầu: Gradle Wrapper có sẵn, JDK 21, network loopback. Khi tạo project thực tế, đảm bảo các packages nằm bên dưới package chứa `@SpringBootApplication` để component scan nhận controller.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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
```

`spring-boot-starter-web` đưa vào Servlet MVC và embedded Tomcat mặc định; `spring-boot-starter-test` đưa vào Spring Boot Test, JUnit Jupiter, AssertJ và các utilities. **Không cần** tự thêm `spring-boot-starter-webflux` chỉ để dùng `@LocalServerPort` hoặc `TestRestTemplate`.

Phiên bản trong ví dụ có mục đích học tập; production project nên tuân thủ Spring Boot BOM/version và Java toolchain đã được tổ chức phê duyệt.

## 9. Ứng dụng và controller của demo

**`src/main/java/com/example/portdemo/PortDemoApplication.java`:**

```java
package com.example.portdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PortDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/portdemo/PingController.java`:**

```java
package com.example.portdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Map<String, String> ping() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/echo/{id}")
    public Map<String, String> echo(@PathVariable String id) {
        return Map.of("id", id);
    }
}
```

Đây là controller test-only friendly: có endpoint cố định `/api/ping` và endpoint có path variable `/api/echo/{id}` để xác nhận HTTP route dispatch. Nó **không** xác thực người dùng và không kết nối database; chỉ dùng trong học tập, không expose Internet như sản phẩm thật.

**`src/main/resources/application.properties`:**

```properties
# Cấu hình dùng khi bootRun bình thường.
server.address=127.0.0.1
server.port=8080
```

Một điểm đáng nhớ: khi test dùng `@SpringBootTest(RANDOM_PORT)`, cấu hình test **chọn cổng động thay vì 8080**. Cùng một source application chạy `./gradlew bootRun` không có test annotation vẫn sử dụng cấu hình `8080` bên trên nếu port đó rảnh.

## 10. Test HTTP thật: `@LocalServerPort`, `TestRestTemplate` và `Environment`

**`src/test/java/com/example/portdemo/RandomPortHttpTest.java`:**

```java
package com.example.portdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class RandomPortHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate client;

    @Autowired
    Environment environment;

    @Autowired
    WebServerApplicationContext webContext;

    @Test
    void injectsActualPortAfterEmbeddedServerStarted() {
        assertThat(port).isBetween(1, 65535);
        assertThat(webContext.getWebServer().getPort()).isEqualTo(port);
        assertThat(environment.getProperty(
                "local.server.port", Integer.class)).isEqualTo(port);
    }

    @Test
    void relativeUrlTargetsTheRunningRandomPort() {
        ResponseEntity<String> response =
                client.getForEntity("/api/ping", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("\"status\":\"ok\"");
    }

    @Test
    void pathVariableIsHandledByRealHttpServer() {
        ResponseEntity<String> response =
                client.getForEntity("/api/echo/book-7", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
                .contains("\"id\":\"book-7\"");
    }
}
```

**Giải thích:**

- `@SpringBootTest(...RANDOM_PORT)` khởi động Tomcat thật ở cổng do OS cấp.
- `@LocalServerPort` lấy **cổng được bind**, không lấy `server.port=8080` từ source `application.properties`.
- `WebServerApplicationContext.getWebServer().getPort()` xác nhận cổng ở tầng embedded runtime; đây là cách kiểm tra độc lập với annotation.
- `Environment.getProperty("local.server.port", Integer.class)` lấy property công bố khi server đã init; khác ý nghĩa `server.port`.
- Spring Boot cung cấp `TestRestTemplate` được liên kết với started test server; **relative URI `/api/ping`** được giải quyết tới đúng local server port.
- Test kiểm tra response đi qua **HTTP socket thật**, không gọi trực tiếp controller method.

Nếu application bật Spring Security, response có thể bị chặn bởi authentication/CSRF và test cần cấu hình credentials/roles phù hợp. Demo này không có Spring Security, vì vậy mong đợi HTTP 200.

## 11. Chạy kiểm thử và hiểu kết quả

Từ project có `gradlew`:

```bash
./gradlew test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
```

Kết quả mong đợi trong điều kiện đúng JDK, dependencies, loopback và project structure là **tests PASS**. **Không có một cổng cố định hoặc stdout Gradle chính xác**: test framework có thể log kiểu:

```text
Tomcat started on port 49152 (http) with context path '/'
```

Dòng và số `49152` là **minh họa**, không phải output bắt buộc. Đừng viết assertion test dựa vào parse log `"Tomcat started on port ..."`. Nếu đổi embedded server từ Tomcat sang Jetty hoặc WebFlux Netty, log text sẽ đổi dù behavior HTTP vẫn đúng.

Để điều tra failure, kiểm tra: app context có startup thành công? `local.server.port` đã có? Test đang dùng `MOCK` hay `RANDOM_PORT`? Client có tự động dùng relative base URL không? Profile có HTTP/HTTPS/context path khác không?

## 12. Khi cần xây URL tuyệt đối từ cổng đã cấp

`TestRestTemplate` dùng relative URLs tiện lợi, nhưng có những test cần truyền full URL cho client ngoài, WebSocket client, callback hoặc SDK không được auto-configure. Lúc ấy xây URL **sau khi field đã được inject**:

```java
String baseUrl = "http://127.0.0.1:" + port;
String pingUrl = baseUrl + "/api/ping";
```

Đây là **đoạn tích hợp trong test**, không phải code chạy độc lập; biến `port` đến từ `@LocalServerPort`.

Thêm vào `RandomPortHttpTest` một test dùng JDK `HttpClient`:

```java
@Test
void jdkHttpClientCanUseDiscoveredPort() throws Exception {
    java.net.http.HttpClient http =
            java.net.http.HttpClient.newHttpClient();

    java.net.URI uri = java.net.URI.create(
            "http://127.0.0.1:" + port + "/api/ping");

    java.net.http.HttpRequest request =
            java.net.http.HttpRequest.newBuilder(uri).GET().build();

    java.net.http.HttpResponse<String> response =
            http.send(request,
                    java.net.http.HttpResponse.BodyHandlers.ofString());

    assertThat(response.statusCode()).isEqualTo(200);
    assertThat(response.body()).contains("\"status\":\"ok\"");
}
```

JDK 17+ đã có `java.net.http.HttpClient`, không cần dependency HTTP client khác. Test này chứng minh **một client không biết Spring context** vẫn dùng được cổng vừa khám phá.

Không tạo URL trong static initializer bằng `port` chưa được inject. Tránh hardcode scheme `http` khi test dùng SSL: nếu application bật HTTPS, base URL phải là `https://...` và client có trust material phù hợp. Không tắt certificate verification bừa bãi để test qua HTTPS.

## 13. `TestRestTemplate` có điểm gì khác `RestTemplate` thông thường?

`TestRestTemplate` là tiện ích của Spring Boot cho integration tests, có một số hành vi tiện cho kiểm thử:

- Khi đi với `RANDOM_PORT`/`DEFINED_PORT`, có thể gọi **relative URL** thay vì tự nối host/port.
- Không throw theo cùng cách `RestTemplate` mặc định đối với nhiều HTTP 4xx/5xx responses; test có thể trực tiếp assert `ResponseEntity.getStatusCode()` và error body.
- Có helper hỗ trợ Basic Auth khi phù hợp, ví dụ `withBasicAuth(...)`.
- Dùng HTTP thật khi embedded server đã được start.

Ví dụ kiểm tra route không tồn tại:

```java
@Test
void missingEndpointReturnsHttp404() {
    ResponseEntity<String> response =
            client.getForEntity("/does-not-exist", String.class);

    assertThat(response.getStatusCode()).isEqualTo(
            HttpStatus.NOT_FOUND);
}
```

Đây là method bổ sung trong `RandomPortHttpTest`. Nếu có custom fallback route hoặc security filter trong ứng dụng thật, kết quả có thể khác. **Đừng gọi `getForObject` rồi mong HTTP 404 tự ném exception** theo mặc định và bỏ qua status; dùng `getForEntity` để nhìn status trực tiếp.

`new RestTemplate()` độc lập sẽ **không tự biết random port** của test. Nếu sử dụng `RestTemplate`, `RestClient`, OkHttp hoặc HTTP client custom, phải cấu hình base URL bằng `@LocalServerPort` sau startup.

## 14. `WebTestClient` có thể giảm nhu cầu tự nối port

Theo Spring Boot 3.3, test dùng running server có thể `@Autowired WebTestClient` khi `spring-webflux` nằm trên classpath trong môi trường test. Với project MVC ở trên, thêm dependency **chỉ ở test scope** nếu muốn dùng WebTestClient:

```groovy
testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Sau đó test riêng:

```java
package com.example.portdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "server.address=127.0.0.1")
class WebTestClientRandomPortTest {

    @Autowired
    WebTestClient webClient;

    @Test
    void autoConfiguredClientCallsActualServer() {
        webClient.get()
                .uri("/api/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }
}
```

WebTestClient được Boot liên kết với running test server nên relative URI sử dụng đúng cổng đã bind. Không cần tự tạo `WebTestClient.bindToServer().baseUrl("http://localhost:8080")` cho case này.

**Quan trọng:** Nếu đưa cả `spring-boot-starter-web` và `spring-boot-starter-webflux` vào runtime application, Spring Boot thường chọn **Servlet** application type vì MVC có ưu tiên. Chỉ thêm WebFlux ở **testImplementation** tránh vô tình đổi runtime dependencies của sản phẩm.

## 15. Cùng `WebTestClient`, nhưng mock-bound và live-bound khác nhau

Một API test có thể dùng cùng tên `WebTestClient` cho hai kiểu:

**Mock environment:**

```java
@SpringBootTest
@AutoConfigureWebTestClient
class MockBoundExample {
    @Autowired
    WebTestClient client;
}
```

**Real HTTP environment:**

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpExample {
    @Autowired
    WebTestClient client;
}
```

Các snippets trên là **mẫu minh họa**, cần imports/dependencies phù hợp. Với `@AutoConfigureWebTestClient` ở MOCK, client có thể bind vào **application context**, không mở cổng TCP thật. Trong RANDOM_PORT, WebTestClient được liên kết tới started server. **Đừng suy có network socket chỉ vì test gọi `.exchange()`**.

Muốn kiểm tra một bug phụ thuộc Tomcat connector, cookie serialization, proxy/real HTTP headers hoặc TLS, dùng **real-bound client**. Muốn test logic handler/validation nhanh, mock-bound thường rẻ hơn. Chọn công cụ theo failure mode chứ không theo tên API.

## 16. Spring WebFlux: `@LocalServerPort` vẫn áp dụng

`@LocalServerPort` không dành riêng cho Tomcat. `@SpringBootTest(RANDOM_PORT)` hoạt động với **reactive web application** khi WebFlux được Boot chọn. Với một project WebFlux độc lập:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Controller reactive:

```java
package com.example.reactiveport;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactivePingController {

    @GetMapping("/api/ping")
    public Mono<String> ping() {
        return Mono.just("reactive-ok");
    }
}
```

Test:

```java
package com.example.reactiveport;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactivePortTest {

    @LocalServerPort
    int port;

    @Autowired
    WebTestClient client;

    @Test
    void nettyServerBindsARealRandomPort() {
        assertThat(port).isPositive();

        client.get()
                .uri("/api/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reactive-ok");
    }
}
```

Các snippets này cần `@SpringBootApplication` trong cùng project/package và dependencies đã nêu; đây là **ví dụ tích hợp cho WebFlux**, không phải source hoàn chỉnh khi chỉ sao chép controller/test. Với WebFlux starter mặc định, server dùng Reactor Netty; có thể thay engine, nhưng cơ chế `RANDOM_PORT`/`@LocalServerPort` vẫn theo Spring Boot web runtime.

Nếu cả MVC và WebFlux cùng ở **runtime** classpath và muốn cố ý test reactive app, xem cấu hình `spring.main.web-application-type=reactive` phù hợp; không cho rằng WebFlux luôn thắng khi cả hai starters hiện diện.

## 17. Cổng được cấp phát là của **web server**, không phải cổng của client

Dễ nhầm ba thứ:

```text
HTTP client local ephemeral port:  52042
HTTP server listen port:          49317
Database port:                    5432
```

Khi test HTTP:

```text
Client 127.0.0.1:52042 ---> Server 127.0.0.1:49317
```

`@LocalServerPort` trả **49317**, tức cổng mà server đang lắng nghe, không phải `52042` của socket client và cũng không phải port database hay Testcontainers mapping.

Tương tự, khi một app được đặt sau reverse proxy:

```text
Browser -> https://public.example.test:443
Proxy   -> http://127.0.0.1:49317
```

`@LocalServerPort` không tự trả `443` vì đây là **public ingress port** của proxy. Nó chỉ phản ánh **local embedded application server** trong test context; muốn kiểm thử gateway/ingress phải có setup riêng.

## 18. Tại sao không dùng port 8080 hardcode trong test?

Anti-pattern:

```java
String url = "http://localhost:8080/api/ping";
```

Với RANDOM_PORT, URL này **không liên quan** đến cổng vừa bind. Nếu một process trên 8080 đang trả `{"status":"ok"}`, test có thể **PASS giả** dù ứng dụng test của bạn bị lỗi mapping, security hay data.

Cách đúng khi cần full URL:

```java
String url = "http://127.0.0.1:" + port + "/api/ping";
```

Hoặc dùng `TestRestTemplate`/`WebTestClient` auto-bound và relative paths. Với URL là biến, test phải assert server đã start, port > 0, response status/body và những hành vi mong đợi.

Đừng sửa test bằng cách ép `server.port=8080` để giống URL cũ; điều đó tái tạo vấn đề collision, đặc biệt ở CI.

## 19. `server.port=0` khác việc tự tìm cổng rảnh rồi đóng socket

Một cách thường thấy trên Internet:

```java
try (ServerSocket socket = new ServerSocket(0)) {
    int port = socket.getLocalPort();
}
// Socket đã đóng; port có thể bị process khác chiếm.
// Sau đó mới cấu hình Spring Boot server.port=port.
```

**Đây là anti-pattern** nếu mục đích là “bảo đảm port không bị tranh chấp”. Socket vừa đóng không còn giữ quyền sở hữu cổng. Nó hữu ích chỉ để hiểu API `ServerSocket`, **không phải thiết kế cấp phát HTTP test port**.

Với Spring Boot test:

```java
@SpringBootTest(
  webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
```

server thực bind `0` rồi Spring Boot công bố cổng đã giữ. Không có khoảng trống giữa “check free port” và “bind actual listener” do ứng dụng tự gây ra.

Nếu một dependency **buộc phải biết cổng trước khi server khởi động**, cần thiết kế dependency initialization/lifecycle khác hoặc để dependency nhận URL sau startup, không giải quyết bằng cách đóng preallocated `ServerSocket`.

## 20. Thực hành Java 17 độc lập: hiểu socket port 0 bằng một listener còn mở

Để thấy cơ chế OS cấp cổng mà không cần Spring, chương trình dưới đây giữ `ServerSocket` **mở** trong lúc client kết nối:

**`EphemeralPortDemo.java`:**

```java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class EphemeralPortDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket server =
                     new ServerSocket(0, 1, loopback)) {
            int assigned = server.getLocalPort();
            ExecutorService executor =
                    Executors.newSingleThreadExecutor();

            try {
                Future<String> received = executor.submit(() -> {
                    try (Socket accepted = server.accept();
                         BufferedReader input = new BufferedReader(
                             new InputStreamReader(
                                 accepted.getInputStream(),
                                 StandardCharsets.UTF_8))) {
                        return input.readLine();
                    }
                });

                try (Socket client =
                             new Socket(loopback, assigned);
                     PrintWriter writer = new PrintWriter(
                             client.getOutputStream(), true,
                             StandardCharsets.UTF_8)) {
                    writer.println("ping");
                }

                System.out.println("port-assigned=" + (assigned > 0));
                System.out.println(
                        "server-received="
                                + received.get(5, TimeUnit.SECONDS));
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
```

Chạy JDK 17+:

```bash
javac EphemeralPortDemo.java
java EphemeralPortDemo
```

**Stdout chính xác khi localhost networking hoạt động:**

```text
port-assigned=true
server-received=ping
```

Điểm học được: OS chọn cổng và **listener vẫn sở hữu cổng** khi client dùng nó. Trong Spring Boot, socket listener do embedded server giữ và `@LocalServerPort` chỉ là cách đưa bound port vào test sau initialization. Không tái sử dụng snippet này làm một custom port allocator cho Spring Boot.

## 21. Cổng được công bố lúc nào và tại sao cấu hình sớm có thể thất bại?

Một lỗi thiết kế là tạo bean:

```java
@Configuration
class EarlyClientConfiguration {

    @Bean
    RestClient selfCallingClient(
            @Value("${local.server.port}") int port) {
        return RestClient.create("http://localhost:" + port);
    }
}
```

Đây là **anti-pattern** cho application startup với `server.port=0`. Khi Spring khởi tạo `EarlyClientConfiguration` và bean `selfCallingClient`, web server có thể chưa hoàn tất bind và `local.server.port` chưa tồn tại, dẫn đến placeholder resolution failure hoặc vòng phụ thuộc lifecycle. Trong test, annotation trên **test instance** hoạt động vì web context được khởi động trước khi method test chạy.

Nếu application thực sự cần biết cổng của chính mình sau startup, dùng lifecycle event phù hợp:

- `WebServerInitializedEvent` khi embedded web server được khởi tạo.
- `WebServerApplicationContext.getWebServer().getPort()` **sau startup**.
- `ApplicationReadyEvent` hoặc công đoạn sau khi context sẵn sàng khi use case phù hợp.

Không khuyến nghị một service tự gọi URL public của chính nó qua HTTP chỉ để dùng business logic; thường nên gọi service method trực tiếp để tránh network loop/transaction/authorization bất ngờ.

## 22. Chương trình Spring Boot lấy cổng sau khi server init bằng event

Trong code application (không phải test), có thể lắng nghe:

```java
package com.example.portdemo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ActualPortLogger
        implements ApplicationListener<WebServerInitializedEvent> {

    private static final Logger log =
            LoggerFactory.getLogger(ActualPortLogger.class);

    @Override
    public void onApplicationEvent(WebServerInitializedEvent event) {
        int port = event.getWebServer().getPort();
        String namespace =
                event.getApplicationContext().getServerNamespace();

        if (namespace == null) {
            log.info("Application HTTP server bound to port {}", port);
        }
    }
}
```

File này có thể thêm vào application MVC demo. Khi web server initialized, `event.getWebServer().getPort()` là cổng thực. Kiểm tra `getServerNamespace()` giúp phân biệt main web context với management context khi chạy một **management server riêng**; namespace có thể khác tùy thiết kế.

Không nên lấy cổng trong constructor của component rồi kết luận server đã start. `ApplicationListener` cũng cần được đăng ký trước khi event phát; một bean listener được Spring quản lý trong context đáp ứng case thông dụng theo tài liệu Boot. Khi ứng dụng có nhiều nested web contexts hoặc custom web servers, xác định **event thuộc context nào** trước khi ghi nhận.

## 23. Nếu cần cổng trong test setup, lấy ở `@BeforeEach` hoặc `@Test`

Ví dụ:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CallbackTest {

    @LocalServerPort
    int port;

    private String callbackBaseUrl;

    @BeforeEach
    void configureCallbackUrl() {
        callbackBaseUrl = "http://127.0.0.1:" + port;
    }

    @Test
    void usesActualPort() {
        assertThat(callbackBaseUrl).contains("127.0.0.1:");
        assertThat(port).isPositive();
    }
}
```

Đây là **mẫu tích hợp**, cần JUnit/AssertJ/Spring imports và app phù hợp. Điểm quan trọng không phải bản thân assertions, mà là **thời điểm tạo URL**: `@BeforeEach` chạy sau khi Spring TestContext đã inject `port`.

Tránh:

```java
static String URL = "http://localhost:" + port;
```

vì `port` là instance field; không truy cập được từ static initializer. Cũng tránh gán field khác sớm:

```java
String url = "http://localhost:" + port;
```

trong field initializer của test: tại thời điểm Java constructor/initializer chạy, `port` có thể vẫn là giá trị mặc định `0`, và URL được giữ sai. Tạo URL trong `@BeforeEach`/test method thay vì eager field initialization.

## 24. Vì sao `@DynamicPropertySource` không phù hợp để đọc `@LocalServerPort`?

Spring TestContext thường đánh giá `@DynamicPropertySource` **khi dựng ApplicationContext**, nghĩa là **trước khi web server khởi động xong**.

Một anti-pattern:

```java
@LocalServerPort
int port;

@DynamicPropertySource
static void dynamicProperties(DynamicPropertyRegistry registry) {
    // Không thể đọc instance port ở đây.
    // Kể cả lưu tạm trong static cũng có thể chạy quá sớm.
}
```

`@DynamicPropertySource` phù hợp cho **các dependencies đã được khởi động trước context**, ví dụ Testcontainers PostgreSQL/Kafka hoặc một mock HTTP server được test framework khởi tạo trước, không phải tự tạo URL của **chính Spring Boot server đang được bootstrap**.

Nếu có component cần biết self URL lúc startup, xem lại kiến trúc và điểm phụ thuộc lifecycle. Nếu một hệ thống khác cần callback URL sau khi app listen, cấu hình qua event sau bind hoặc API test sau startup. Đừng cố ghi `local.server.port` vào một property dynamic sớm hơn sự kiện đã tạo ra nó.

## 25. `@LocalManagementPort`: cổng Actuator có thể khác cổng ứng dụng

Khi ứng dụng sử dụng Spring Boot Actuator trên **cổng riêng**, có hai listeners:

```text
Application HTTP server:
  local.server.port       -> application endpoints

Management HTTP server:
  local.management.port   -> Actuator endpoints
```

Import annotation trong Spring Boot 3.3:

```java
import org.springframework.boot.test.web.server.LocalManagementPort;
```

Nếu `management.server.port` không được cấu hình riêng, Actuator có thể chạy chung web server với app, và không nhất thiết tồn tại management listener riêng. **Không giả định `@LocalManagementPort` luôn nhận một cổng riêng.**

Theo Spring Boot 3.3 testing docs, khi application được cấu hình dùng **management server trên cổng khác**, `@SpringBootTest(RANDOM_PORT)` có thể làm **cả main server và management server** dùng các cổng ngẫu nhiên riêng trong test. Phải kiểm tra đúng thông tin runtime thay vì đoán cổng management từ `management.server.port` trong file properties.

## 26. Test Actuator trên management port riêng

Đây là **biến thể độc lập** của MVC demo: thêm Actuator vào Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

Test cổng ứng dụng và management, khi chúng được cấu hình trên port khác nhau:

```java
package com.example.portdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.server.LocalManagementPort;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "management.server.address=127.0.0.1",
        "management.server.port=9091",
        "management.endpoints.web.exposure.include=health"
    })
class SeparateManagementPortTest {

    @LocalServerPort
    int appPort;

    @LocalManagementPort
    int managementPort;

    @Test
    void portsAreBoundIndependently() {
        assertThat(appPort).isBetween(1, 65535);
        assertThat(managementPort).isBetween(1, 65535);
        assertThat(managementPort).isNotEqualTo(appPort);
    }
}
```

Test dùng property `management.server.port=9091` để **bật cơ chế management listener riêng** khi chạy như application cấu hình. Với `RANDOM_PORT` trong Spring Boot 3.3, test bootstrap hỗ trợ chọn cổng ngẫu nhiên cho management listener khi dùng separate management server. Không đưa kỳ vọng “managementPort phải luôn bằng 9091” vào assertions.

Để gọi `/actuator/health`, dùng URL **với managementPort**, không dùng relative URL của `TestRestTemplate` đang bound về application port:

```java
String healthUrl =
        "http://127.0.0.1:" + managementPort + "/actuator/health";
```

Đây là snippet tích hợp trong test. Nếu Actuator base path thay đổi, Spring Security bảo vệ endpoint, hoặc management SSL riêng được bật, phải dùng đúng base path/scheme/credentials. Không expose management port ra Internet để phục vụ tests.

## 27. So sánh `server.port`, `local.server.port`, management và Testcontainers

| Trường hợp | Thuộc tính/cách khám phá đúng | Không nên dùng |
| --- | --- | --- |
| Test Spring Boot HTTP app | `@LocalServerPort`, `local.server.port` | Hardcode `8080` |
| Server production dùng `server.port=0` | `WebServerInitializedEvent` hoặc `WebServerApplicationContext` sau startup | `@LocalServerPort` trong bean constructor |
| Actuator separate listener | `@LocalManagementPort`, `local.management.port` | App port để đoán management URL |
| PostgreSQL Testcontainer mapped port | `container.getMappedPort(5432)` hoặc JDBC URL do Testcontainers cấp | `@LocalServerPort` |
| WireMock/mock server riêng | Port do mock server expose sau khi khởi động | `local.server.port` của Spring app |
| Browser qua ingress/reverse proxy | Public route/ingress port và host | Embedded server port để đoán public URL |
| JDK `HttpClient` outbound TCP source port | Socket/OS networking semantics, thường không cần biết | Spring web server local port |
| WebSocket endpoint của cùng embedded server | `ws://host:<local.server.port>/...` hoặc `wss` nếu TLS | Một cổng WebSocket giả định riêng |

`@LocalServerPort` không thể thay thế Testcontainers mapped port. Nếu một integration test cần Spring app kết nối vào DB container, hãy inject **DB URL** trước Spring context startup bằng `@DynamicPropertySource` hoặc Spring Boot service connections; đó là một **đường cấu hình ngược** với việc test HTTP client khám phá Spring listener sau startup.

## 28. `@LocalServerPort` trong `MOCK`/`NONE`: lỗi phổ biến

Ví dụ có vấn đề:

```java
@SpringBootTest
class IncorrectMockTest {
    @LocalServerPort
    int port;
}
```

`@SpringBootTest` mặc định là `MOCK`, không có embedded HTTP listener; vì vậy không có cổng thực đã cấp để `local.server.port` sử dụng. Test có thể lỗi unresolved placeholder/injection hoặc không có port hợp lệ tùy setup.

Tương tự:

```java
@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.NONE)
```

được thiết kế không tạo web environment; không thể dùng `@LocalServerPort` để gọi một server không được khởi động.

**Sửa đúng:**

- Nếu cần network thực, chuyển sang `RANDOM_PORT`.
- Nếu chỉ cần kiểm thử controller ở MVC layer, dùng `@WebMvcTest`/`MockMvc` hoặc mock-bound setup.
- Nếu cần application context nhưng không cần HTTP, bỏ injection port.

Đừng thêm `@LocalServerPort` vào mọi test class như một “trang trí” hoặc giả định test library sẽ tự mở socket.

## 29. `DEFINED_PORT`: lúc nào phù hợp và rủi ro gì?

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT)
```

khởi động web server ở `server.port` đã cấu hình (hoặc mặc định `8080` khi không cấu hình), trừ khi profile/properties khác thay đổi. Mode này hữu ích với trường hợp integration test **bắt buộc có cổng cố định** để một hệ thống bên ngoài kết nối.

Nhưng có rủi ro:

- Port collision giữa test và IDE/server đang chạy.
- Parallel CI jobs tranh cùng host port.
- Test gọi nhầm process cũ đang chiếm port khi cấu hình thiếu kiểm tra.
- Khó tái sử dụng tests trên local/CI.
- Một test class được cache context có thể giữ port xuyên nhiều methods.

Trong phần lớn HTTP integration tests của một service, ưu tiên `RANDOM_PORT`. Dùng `DEFINED_PORT` khi có lý do cụ thể, có ownership của port và lifecycle cleanup. Ngay cả với `DEFINED_PORT`, test có thể đọc actual bound port sau startup qua `local.server.port`/web context để tránh giả định bừa.

## 30. Context caching: port không mặc nhiên đổi ở mỗi test method

Spring TestContext framework **cache ApplicationContext** giữa các tests tương thích để tăng tốc. Nếu hai test methods dùng cùng Spring context, chúng thường chia sẻ **cùng embedded server và cùng random port**.

```text
JUnit test method A ─┐
                     ├─ cached SpringBootTest ApplicationContext
JUnit test method B ─┘             |
                                   v
                          one embedded server
                          one bound local port
```

Vì thế đừng assert:

```text
portInMethodA != portInMethodB
```

đó không phải hợp đồng của `RANDOM_PORT`. “Random” mô tả **cách server bind khi một context được khởi động**, không phải yêu cầu đổi port sau từng request/method.

Khi context bị đóng/recreated (`@DirtiesContext`, khác profiles/configuration hoặc cache eviction), server mới có thể nhận cổng khác — nhưng OS vẫn có thể **tái sử dụng cùng số port**. Test không nên dựa vào tính duy nhất của cổng qua thời gian.

## 31. Kiểm thử song song và context independence

`RANDOM_PORT` giảm cổng cố định bị tranh chấp khi nhiều application contexts chạy cùng host. Nó không làm toàn bộ test suite tự nhiên thread-safe.

Các nguồn xung đột khác:

- Database schema/bảng hoặc test fixtures chung.
- Static singleton mutable state.
- Cùng file path/tạm thư mục.
- Các background jobs gửi events vào broker topic chung.
- Shared Redis cache/session store.
- External API rate limits.
- Một management port **cố định** còn sót lại.
- Một mock server/WireMock dùng cổng fixed.
- `@TestPropertySource`/system property shared được thay đổi trong lúc các tests khác chạy.

Thiết kế isolation theo **resource ownership**: dùng random HTTP port cho web app, mapped ports cho Testcontainers, test-specific database/schema/topic, cleanup dữ liệu hoặc transaction boundaries phù hợp. Khi test suite parallel forks, xác định liệu Gradle test process/contexts có chia sẻ hệ thống bên ngoài không.

## 32. Transaction trong real HTTP tests không tự rollback server-side work

Tài liệu Spring Boot 3.3 cảnh báo: `@SpringBootTest` với `RANDOM_PORT` hoặc `DEFINED_PORT` chạy **HTTP client và HTTP server ở các threads khác nhau**, vì vậy transaction của test method và transaction được mở trên server **không phải cùng một transaction**.

Ví dụ:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class CreateOrderHttpTest {
    // Nếu gọi HTTP POST tạo order, server có thể commit transaction riêng.
    // Rollback ở test thread không tự rollback server-side DB commit.
}
```

Đây là mẫu minh họa, yêu cầu spring-tx/test dependencies và persistence setup thật; **không phải cơ chế cleanup dữ liệu**.

Nếu test thực hiện `POST /orders` rồi backend commit một row, test cần cleanup theo database transaction/fixture strategy, idempotent delete hoặc isolated schema/container. Không tưởng rằng `@Transactional` trên test method sẽ xóa state tạo bởi HTTP server thread.

Đây là một lý do nên phân biệt unit/slice tests (thường có transaction scope dễ kiểm soát) với real HTTP integration tests.

## 33. Địa chỉ bind khác với cổng: `127.0.0.1`, `localhost`, IPv4/IPv6

Một cổng TCP chỉ có nghĩa cùng **địa chỉ lắng nghe và protocol**. Ví dụ:

```text
Server binds 127.0.0.1:49317   -> IPv4 loopback
Client connects ::1:49317     -> IPv6 loopback
```

Nếu OS/hostname resolution ưu tiên IPv6 trong khi server chỉ bind IPv4, `http://localhost:49317` đôi khi không tương thích với setup test. Trong demo có:

```properties
server.address=127.0.0.1
```

nên test dùng:

```java
"http://127.0.0.1:" + port
```

để thống nhất IPv4 loopback. Trong app thực, có thể cấu hình `server.address=0.0.0.0` để bind mọi IPv4 interfaces, nhưng đó là quyết định mạng/bảo mật, **không cần cho test local**.

`@LocalServerPort` chỉ cho **số port**. Nó không tự xác định hostname công khai, DNS, scheme, reverse proxy prefixes hoặc CORS origin. Khi app dùng IPv6 literal, URL có thể cần dạng `http://[::1]:<port>/...`.

## 34. HTTPS, `server.servlet.context-path` và base URL đúng

Khi dùng HTTPS, một URL đúng cần **scheme, host, port và path**:

```text
https://127.0.0.1:<assigned-port>/<context-path>/api/ping
```

`@LocalServerPort` **không trả scheme** và không tự cấu hình SSL trust cho JDK HttpClient/TestRestTemplate. Nếu server chỉ có HTTPS listener và client gọi `http`, lỗi thường là handshake/protocol, không phải lỗi khám phá port.

Với MVC:

```properties
server.servlet.context-path=/demo
```

các routes ở app có base path `/demo`; URL HTTP thực thường là:

```text
http://127.0.0.1:<port>/demo/api/ping
```

Nếu dùng `TestRestTemplate` root URI autoconfig, phải xác nhận cách client xử lý context path theo version và test setup; khi không chắc, dùng full URL gồm context path rồi assert. Với WebFlux, property context path khác MVC Servlet (`spring.webflux.base-path` trong những cấu hình phù hợp). Không hoán đổi các property theo framework mà không kiểm tra.

Management endpoint base path mặc định `/actuator` và có thể được tùy chỉnh. Khi dùng separate management port, context/management base path phải được xác nhận độc lập.

## 35. Cổng `0` không bảo đảm tất cả external services đã sẵn sàng

Khi embedded HTTP server đã bind, `@LocalServerPort` có số dương; nhưng điều đó không nhất thiết chứng minh:

- Database đã có fixtures hoặc migration của môi trường ngoài hoàn tất.
- Background consumer đã subscribe broker.
- Cache đã warmed.
- Một dependency remote đã sẵn sàng.
- Một task được trigger bất đồng bộ đã hoàn thành.
- TLS reverse proxy bên ngoài đã cập nhật route.

Một HTTP integration test cần **readiness condition đúng nghiệp vụ**. Nếu HTTP endpoint phụ thuộc async setup, dùng bounded polling/eventual assertion, không `Thread.sleep(10000)` tùy ý để “đợi server”.

`@SpringBootTest` hoàn tất context startup trước test methods, nhưng các công việc không đồng bộ do app khởi chạy có lifecycle khác. **Cổng đã bind là bằng chứng về listener**, không phải một health check đầy đủ của mọi dependency.

## 36. Kiểm tra cổng thực mà không parse log startup

Có vài cách hợp lệ:

| Phương pháp | Dùng ở đâu | Ưu điểm |
| --- | --- | --- |
| `@LocalServerPort int port` | Spring Boot tests | Đơn giản, đúng sau test context startup |
| `@Value("${local.server.port}")` | Test field hoặc code sau startup | Truy cập property tương đương |
| `Environment.getProperty("local.server.port")` | Sau khi web server initialized | Chủ động đọc Environment |
| `WebServerApplicationContext.getWebServer().getPort()` | Context đang chạy | Truy cập embedded server object |
| `ApplicationListener<WebServerInitializedEvent>` | Runtime listener sau bind | Nhận sự kiện startup và cổng thực |
| `TestRestTemplate` | Real HTTP test | Có thể dùng relative URLs, không cần tự nối |
| `WebTestClient` | WebFlux hoặc MVC test có WebFlux test dependency | HTTP assertions theo fluent API |

Không nên parse một dòng `Tomcat started on port ...` bằng regex rồi chờ file stdout, vì startup log format, server type và logger configuration đều có thể đổi. Chọn contract được framework công bố thay vì scraping output.

## 37. Test failure diagnosis theo triệu chứng

| Triệu chứng | Khả năng nổi bật | Kiểm tra |
| --- | --- | --- |
| `Could not resolve placeholder 'local.server.port'` | Không có real server, injection quá sớm | `MOCK` hay `RANDOM_PORT`? field ở test hay constructor bean? |
| Port được inject bằng `0` | Field chưa inject / đọc quá sớm / test setup không chuẩn | Lifecycle, instance vs static field, test annotations |
| `Connection refused` tới 8080 | Client hardcode port cũ | Dùng `@LocalServerPort` hoặc auto-bound test client |
| `Connection refused` tới random port | Server shutdown, hostname/bind mismatch, sai context | Web server lifecycle, `server.address`, context cache |
| `Address already in use` | Fixed port bị chiếm, quản lý port ngoài đang fixed | `DEFINED_PORT`, `server.port`, `management.server.port`, mocks |
| Test PASS nhưng app test bị lỗi | HTTP request gọi process khác | Ghi rõ actual port, test endpoint unique, bỏ 8080 |
| HTTP 404 | Port đúng nhưng route/context path sai | `/api/ping`, context path, filters/router |
| HTTP 401/403 | Security policy | Test auth/CSRF, không coi là port lỗi |
| TLS handshake exception | `https`/`http` nhầm hoặc trust setup | Server SSL config, client TLS |
| `@LocalManagementPort` không resolve | Không có management server riêng hoặc Actuator chưa setup | management listener và version |
| Test có port giống lần trước | OS tái sử dụng hoặc context cached | Không assert uniqueness giữa executions |
| WebTestClient bean không có | Thiếu WebFlux test classpath hoặc config khác | Dependencies Boot 3.3, running vs mock binding |
| Port thay đổi khi test class khác chạy | Context bị tái tạo | Context cache profiles/configuration |
| Server chạy nhưng callback URL được build sai | Build URL trước injection | Chuyển logic sang `@BeforeEach`/test method |
| Bind error chỉ khi chạy parallel | Một dependency còn fixed port | Check Testcontainers, WireMock, management, forks |

Nếu có failures do port, **đừng vội “retry test 3 lần”**. Phải xác định là port collision, bind/interface mismatch, startup race, closed context hay gọi nhầm server. Retry có thể che một test flakiness cần sửa.

## 38. Kiểm thử cổng bằng assertions có ý nghĩa

Một test tốt xác nhận ít nhất:

1. `@LocalServerPort` trả số dương hợp lệ.
2. `webContext.getWebServer().getPort()` nhất quán với cổng inject.
3. Một HTTP request thật qua đúng port trả status mong đợi.
4. Body/headers thể hiện **đúng ứng dụng test** đang chạy.
5. Không dựa vào số port cố định hay parse startup log.

Ví dụ assertion hợp lý:

```java
assertThat(port).isBetween(1, 65535);
assertThat(webContext.getWebServer().getPort()).isEqualTo(port);
```

Không hữu ích:

```java
assertThat(port).isEqualTo(8080);
assertThat(port).isNotEqualTo(previousTestPort);
```

Bài học cốt lõi là **cổng được khám phá sau bind** và test tương tác đúng server, không chứng minh bộ sinh số ngẫu nhiên.

Nếu muốn test hai contexts độc lập cùng lúc, cần khởi động hai server được OS cấp port 0 trong vòng đời **đồng thời**, xác nhận cả hai có thể accept connections và dùng đúng URL tương ứng. Đừng assert hai cổng từ **hai lần chạy tuần tự** buộc phải khác nhau.

## 39. Port và test scope: không nhầm Testcontainers với Spring server

Trong integration test phức tạp có thể có:

```text
Spring Boot app HTTP      127.0.0.1:<appPort>
Testcontainers PostgreSQL localhost:<mappedDbPort>
WireMock downstream       localhost:<wireMockPort>
Kafka broker              localhost:<mappedBrokerPort>
```

Đối với Spring app, `@LocalServerPort` chỉ `appPort`.

Đối với Testcontainers, phải lấy thông tin đã mapped từ container lifecycle, ví dụ `container.getJdbcUrl()`, `container.getMappedPort(5432)` hoặc Spring Boot `@ServiceConnection` ở phiên bản được hỗ trợ. Đối với WireMock/test stub, lấy URL thực của stub server sau startup. Các ports này **không liên quan** tới property `local.server.port`.

Khi test gửi URL callback tới một mock service cần biết appPort, chỉ cập nhật callback URL **sau khi Spring server đã bind**. Nếu code service phải biết callback URL từ lúc dựng bean, cần thiết kế cách truyền dependency khác thay vì tự đoán cổng.

## 40. Port 0 không thay thế authorization, test isolation hay network safety

Dùng OS-assigned port không có nghĩa server là private. Nếu bind `0.0.0.0`/`::`, app có thể lắng nghe trên nhiều network interfaces với một **port được cấp động**. Test chứa endpoints không có security vẫn có thể bị máy khác truy cập nếu network policy cho phép.

Khuyến nghị cho test local:

```properties
server.address=127.0.0.1
```

hoặc config tương ứng cho IPv6 loopback. Khi cần test remote/container networking, phải cấu hình host mapping đúng theo môi trường, không tùy tiện public port.

Một số test frameworks điều khiển browser ở container riêng, nơi `127.0.0.1` trỏ **về browser container**, không phải JVM của test. Khi ấy cần network alias/exposed mapping từ môi trường tích hợp; `@LocalServerPort` vẫn chỉ cho **port bên JVM**, không biến host network tự động.

Không log access tokens/cookies hoặc dữ liệu nhạy cảm trong URL chỉ vì đang debug random port. Có thể ghi `port` và route template trong test diagnostics, không in raw Authorization/query/body.

## 41. Test suite design: phân tầng thay vì dùng `RANDOM_PORT` mọi nơi

Một bộ kiểm thử Spring Boot lớn nên cân bằng chi phí:

| Lớp test | Cách thực hiện | Mục tiêu |
| --- | --- | --- |
| Unit test | JUnit/Mockito không Spring | Business logic thuần |
| MVC slice | `@WebMvcTest`, `MockMvc` | Controller mapping/validation/security rules |
| Full app mock web | `@SpringBootTest` + `@AutoConfigureMockMvc` | Wiring nhiều beans không cần socket |
| Full app real web | `@SpringBootTest(RANDOM_PORT)` | HTTP transport, container, filters, serialization |
| End-to-end system | App + DB/broker/proxy hoặc deployed env | Contract across services, TLS/ingress |

`RANDOM_PORT` có startup cost, server threads và test context resource consumption. Nó phù hợp cho các tests mà **real HTTP transport tạo thêm giá trị**, không bắt buộc cho mọi service method.

Giữ test classes có cùng configuration để tận dụng Spring context caching khi hợp lý, nhưng không giữ application state rò rỉ giữa methods. `@DirtiesContext` chỉ nên dùng khi thực sự cần recreate context; nó có thể làm suite chậm và thay port khi context rebuild.

## 42. Thực hành và câu hỏi kiểm tra

1. Vì sao `@SpringBootTest` mặc định không làm `@LocalServerPort` có cổng thật?
2. `RANDOM_PORT` thực hiện điều gì với `server.port`?
3. Tại sao `server.port=0` không có nghĩa cổng HTTP cuối cùng là `0`?
4. `local.server.port` được công bố trước hay sau khi embedded server bind?
5. Vì sao `@LocalServerPort` phù hợp trên test field nhưng dễ sai trong application bean constructor?
6. `TestRestTemplate.getForEntity("/api/ping", ...)` biết random port từ đâu?
7. Khác biệt giữa WebTestClient mock-bound và live HTTP-bound là gì?
8. Trong demo, vì sao test không assert port là `8080`?
9. Nếu hai test methods dùng cached context, chúng có phải dùng hai cổng khác nhau không?
10. Vì sao không lấy `ServerSocket(0)` rồi đóng socket để “giữ” một free port cho Spring?
11. Khi test có cổng management riêng, annotation nào dùng để lấy?
12. Cổng `@LocalServerPort` là cổng public ingress hay cổng listener nội bộ?
13. Nếu test `@Transactional` gửi POST thực qua HTTP, vì sao rollback test transaction không nhất thiết rollback server transaction?
14. Với `server.servlet.context-path=/demo`, URL request thay đổi thế nào?
15. Vì sao `localhost` có thể dẫn tới IPv6 loopback trong khi server chỉ bind IPv4?
16. `@DynamicPropertySource` có dùng được để đọc cổng chính app trước startup không?
17. Khi cả starter-web và starter-webflux cùng ở runtime, Spring Boot thường chọn web application type nào?
18. Port được inject dương có đủ chứng minh database/broker sẵn sàng không?
19. Trong hệ thống có Testcontainers DB, lấy mapped DB port thế nào và vì sao không dùng `@LocalServerPort`?
20. Khi nào `DEFINED_PORT` là lựa chọn có lý do, và nó làm tăng rủi ro gì?

**Bài tập A:** Chạy demo MVC, xem các test với `RANDOM_PORT` PASS. Đổi URL test sang `8080` rồi xác định vì sao test không còn bảo đảm gọi đúng app.

**Bài tập B:** Thêm test `@SpringBootTest(MOCK)` dùng `MockMvc` và so sánh thời gian chạy, stack thực thi và khác biệt không có socket.

**Bài tập C:** Chạy cùng test class hai lần và ghi port. Nếu hai giá trị trùng nhau, giải thích vì sao điều đó vẫn phù hợp với hợp đồng `RANDOM_PORT`.

**Bài tập D:** Bật management port riêng và `@LocalManagementPort`; xác nhận hai HTTP endpoints có thể gọi bằng hai ports khác nhau theo cấu hình test.

**Bài tập E:** Dùng WebFlux starter riêng, kiểm tra Reactor Netty listener bằng `@LocalServerPort` và WebTestClient real-bound; không sử dụng port cố định.

## 43. Kết luận: yêu cầu port 0, chờ bind, đọc port thực, rồi gửi HTTP

Chuỗi tư duy đúng:

```text
RANDOM_PORT / server.port=0
        |
        v
OS chọn và giữ listener port khi bind
        |
        v
WebServerInitializedEvent
        |
        v
local.server.port = bound HTTP port
        |
        v
@LocalServerPort được inject vào test
        |
        v
TestRestTemplate / WebTestClient / JDK HttpClient gọi đúng URL
```

**Bốn điều cần nhớ nhất:**

1. `@SpringBootTest(RANDOM_PORT)` chạy **HTTP server thật**; `MOCK` không chạy listener.
2. `@LocalServerPort` đưa **cổng đã bind** vào test, không đọc `server.port=0` và không yêu cầu cổng là một số cố định.
3. `local.server.port` xuất hiện **sau** server initialization; application startup sớm không được phụ thuộc vào nó.
4. Test port management, database container, mock server và proxy phải khám phá **đúng loại cổng tương ứng**, không dùng một annotation cho tất cả.

Khi hiểu ranh giới này, integration tests ít bị port collision, tránh gọi nhầm process và có thể chạy song song trong CI mà không phải ép nhiều ứng dụng vào một cổng HTTP chung.

### Tài liệu tham khảo

- Spring Boot 3.3 — Testing Spring Boot Applications, Running Server / RANDOM_PORT: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Embedded Web Servers, Random Port và Discover HTTP Port at Runtime: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3.13 — `LocalServerPort` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html
- Spring Boot 3.3.13 — `LocalManagementPort` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html
- Spring Boot 3.3.13 — `ServerPortInfoApplicationContextInitializer` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/ServerPortInfoApplicationContextInitializer.html
- Spring Boot 3.3 — Actuator HTTP Management Port: https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html
- Spring Framework — TestContext framework và context caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Oracle Java 21 — `ServerSocket` và `getLocalPort`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html
- Oracle Java 21 — HTTP client: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html