# @SpringBootTest với MOCK, RANDOM_PORT và DEFINED_PORT

## 1. Mục tiêu học tập và quy tắc phân biệt

`@SpringBootTest` là annotation dùng để khởi tạo **Spring Boot ApplicationContext gần với ứng dụng thật** trong một bài kiểm thử. Annotation này không tự đồng nghĩa với “mở Tomcat”, “gửi HTTP qua mạng” hoặc “chạy end-to-end”. Thuộc tính **`webEnvironment`** quyết định test được cấp **môi trường web giả lập**, **web server thật trên port ngẫu nhiên** hay **web server thật trên port đã xác định**.

Bài thuộc nhóm **Kiểm thử web runtime** của module **Spring Boot - web-runtime**, với các mục tiêu:

1. Phân biệt chính xác `MOCK`, `RANDOM_PORT`, `DEFINED_PORT` và biết thêm `NONE` để tránh hiểu thiếu.
2. Chọn `MockMvc`/`WebTestClient` cho mock environment và `TestRestTemplate`/`WebTestClient`/HTTP client thật cho running-server environment.
3. Hiểu sự khác nhau giữa chạy Spring MVC controller qua mock servlet infrastructure và chạy cả embedded web server qua TCP socket.
4. Tạo được project **Java 17 + Spring Boot 3.3.5 + Maven + JUnit Jupiter 5** với ba nhóm test chạy được.
5. Dùng đúng `@AutoConfigureMockMvc`, `@AutoConfigureWebTestClient`, `@LocalServerPort` và cấu hình `server.port` theo mục đích.
6. Biết khi nào cần test real HTTP stack (network binding, filters, cookies, HTTP status, server-specific behavior, compression, TLS, proxy).
7. Nhận diện bẫy `@Transactional`: test rollback ở test thread **không rollback** transaction trong server thread khi gọi qua HTTP thật.
8. Tổ chức tests không xung đột port trong CI, không nhầm “random” với “đổi port mỗi method”, và quản lý Spring test context cache.

**Quy tắc nhớ nhanh:**

- **`MOCK` (mặc định):** full Spring application context, **không start embedded HTTP server**.
- **`RANDOM_PORT`:** full context + **embedded server thật**, OS chọn port khả dụng.
- **`DEFINED_PORT`:** full context + **embedded server thật**, dùng `server.port` hoặc mặc định `8080`.
- **`NONE`:** full context nhưng **không có web environment**.

Các mô tả này theo **Spring Boot 3.3.x**; với Spring Boot phiên bản khác, kiểm tra package và test client API tương ứng. Đừng lấy các API test của Boot 4.x (có thể đổi module/package) áp trực tiếp vào project Boot 3.3.

## 2. @SpringBootTest đang khởi động những gì?

`@SpringBootTest` dùng Spring Boot infrastructure để xây dựng ApplicationContext (được tạo bằng cơ chế `SpringApplication`). Nó thường tìm main configuration `@SpringBootApplication` hoặc `@SpringBootConfiguration` bằng cách đi ngược package từ lớp test lên các package cha.

~~~text
JUnit Jupiter chạy class test
         |
         v
@SpringBootTest + Spring TestContext
         |
         +--> tìm @SpringBootApplication
         +--> tải application.properties / test properties / profiles
         +--> dựng dependency injection, services, controllers, auto-configs
         +--> quyết định webEnvironment
                   |
                   +--> MOCK:       mock web context, KHÔNG mở cổng
                   +--> RANDOM_PORT: web context + HTTP listener port tự chọn
                   +--> DEFINED_PORT:web context + HTTP listener port cố định
                   '--> NONE:       ApplicationContext không web
         |
         v
Thực thi @Test và assertions
         |
         v
Context có thể được CACHE để dùng lại cho tests khác
~~~

Điểm quan trọng: **full context** chỉ nói về phạm vi beans/autoconfiguration được load. Còn **request có đi qua network/embedded container hay không** là một lựa chọn khác.

Một `@SpringBootTest(webEnvironment=MOCK)` vẫn có thể load `@Service`, `@Repository`, transaction manager, event listeners, filters, security chains và các external dependencies được cấu hình. Nó **không** giống việc chỉ tạo một `@Controller` bằng `new` trong unit test. Ngược lại, `@WebMvcTest` là web slice test, không phải full context.

### 2.1. Spring MVC hay Spring WebFlux?

Spring Boot kiểm tra classpath để xác định loại web application:

- Có **Spring MVC/Servlet**: thông thường tạo MVC web context, embedded Tomcat/Servlet server khi dùng port thật.
- Có **chỉ Spring WebFlux**: tạo reactive web context; với mặc định Boot WebFlux starter thường dùng Reactor Netty khi chạy server thật.
- Có **cả MVC và WebFlux**: Boot 3.3 **ưu tiên MVC** nếu không override `spring.main.web-application-type=reactive`.
- Thiếu cả hai web stacks: `MOCK` có thể fallback về non-web ApplicationContext.

Việc inject `WebClient` vào một dự án MVC **không tự đổi** ứng dụng sang WebFlux. Khi viết test, phải xác định **runtime inbound** đang dùng để chọn đúng test client và expectation.

## 3. Bảng so sánh ba chế độ chính

| Tiêu chí | `MOCK` | `RANDOM_PORT` | `DEFINED_PORT` |
| --- | --- | --- | --- |
| `@SpringBootTest` default? | **Có** | Không | Không |
| Khởi động ApplicationContext đầy đủ? | Có | Có | Có |
| Start embedded HTTP server thật? | **Không** | **Có** | **Có** |
| Mở TCP port / nhận HTTP thật? | **Không** | **Có** | **Có** |
| Port được chọn | Không có port đang listen do test | `server.port=0` / port khả dụng | `server.port` hoặc 8080 |
| MVC test client thường dùng | `MockMvc` | `TestRestTemplate` hoặc real HTTP client | `TestRestTemplate` hoặc real HTTP client |
| Reactive test client thường dùng | `WebTestClient` bound-to-context | `WebTestClient` bound-to-server | `WebTestClient` bound-to-server |
| Dùng `@LocalServerPort` để đọc port thật? | Không phù hợp | **Có** | **Có** |
| Kiểm thử network socket/embedded container? | Không | Có | Có |
| Kiểm thử MVC routing/filter/serialization? | Có, tại mock servlet level | Có, qua HTTP runtime | Có, qua HTTP runtime |
| Nguy cơ port conflict trong CI | Không từ embedded HTTP listener | Thấp hơn; OS cấp port | **Cao** nếu trùng port |
| Client HTTP và server xử lý trên threads khác nhau? | Không có HTTP server thật | **Có** | **Có** |
| Test `@Transactional` rollback server-side DB writes khi gọi HTTP? | Có thể trong cùng test thread với mock sync request | **Không tự rollback** | **Không tự rollback** |
| Tốc độ khởi động thường gặp | Không start server, thường nhẹ hơn | Thêm chi phí start/stop server | Thêm chi phí start/stop server |
| Khi nào ưu tiên | MVC handler behavior, validation, security/filter logic | Integration chạy cả HTTP stack, CI | Yêu cầu cố định port trong môi trường được kiểm soát |

**`RANDOM_PORT` không có nghĩa mỗi `@Test` có một cổng mới.** Port được chọn khi server/context khởi động; nhiều test methods chia sẻ cùng ApplicationContext thường chia sẻ một port. Context cache có thể làm một nhóm test classes dùng cùng context và cùng bound port.

**`DEFINED_PORT` không có nghĩa cổng luôn là 8080.** Có thể đặt `server.port=18081` hoặc giá trị từ profile/config. Nếu bạn cố tình đặt `server.port=0`, OS vẫn chọn ephemeral port dù annotation tên `DEFINED_PORT`; điều quyết định là effective server property.

## 4. WebEnvironment.NONE dùng để làm gì?

Ngoài ba mode của đề bài, Spring Boot có:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class SomeContextTests {
    // ...
}
~~~

`NONE` tạo non-web ApplicationContext qua SpringApplication, không cấp mock servlet environment hoặc embedded HTTP server. Hữu ích khi chỉ kiểm tra wiring/config/business services mà muốn bỏ web environment. `NONE` **không phải** biến thể của `MOCK`: `MOCK` có thể tạo mock web context để hỗ trợ MockMvc/WebTestClient, còn `NONE` hoàn toàn không yêu cầu web layer.

Nếu một service phụ thuộc rõ vào web-only beans, test `NONE` có thể cần thêm cấu hình hoặc không phù hợp. Không chọn NONE chỉ vì test không cần gửi request nếu app initialization có web dependencies thiết yếu.

## 5. @SpringBootTest mặc định MOCK; @AutoConfigureMockMvc không đồng nghĩa mở cổng

Hai annotation thường đi cùng nhau:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class GreetingMockTest {
    // ...
}
~~~

Nghĩa là:

- `@SpringBootTest`: tải **full context**.
- `webEnvironment` bỏ trống: mặc định **`MOCK`**.
- `@AutoConfigureMockMvc`: cấu hình bean `MockMvc` để gọi vào MVC infrastructure **không cần TCP listener**.

`MockMvc` xây dựng request/response giả lập ở Servlet MVC layer: bạn gọi `mvc.perform(get("/api/hello"))`, Spring DispatcherServlet/handlers xử lý và trả `MvcResult`. Kết quả kiểm tra status, headers, body, exception mapping, filters nếu được cấu hình chạy — nhưng **không có DNS/TCP connect/TLS handshake/network proxy**.

### 5.1. Những gì MOCK có thể kiểm tra tốt

- `@RequestMapping`, HTTP method/path, `@RequestParam`, `@PathVariable`.
- Binding/serialization JSON qua MVC converters.
- Validation/exception handlers/response status.
- Servlet filters và Spring Security filters nếu mock test tích hợp đúng.
- Controller/service wiring trong Spring ApplicationContext.
- Business behavior không phụ thuộc vào socket thật.

### 5.2. Những gì MOCK không chứng minh

- Embedded Tomcat/Jetty/Netty thật đã bind đúng cổng.
- TCP/TLS/HTTP2/WebSocket Upgrade/chunked network semantics.
- Hành vi error page mức servlet container (ví dụ customized error pages được container render).
- Reverse proxy/gateway routing, firewall và DNS.
- Browser cookie policy/real redirects dưới một runtime network thật.
- Connection timeouts, keep-alive, socket resets, compression và server configuration thực.

Nếu bug chỉ xuất hiện khi request đi qua connector/TLS/proxy, `MockMvc` có thể PASS trong khi deployment vẫn FAIL.

## 6. Lab MVC dùng chung: Java 17, Spring Boot 3.3.5, Maven

Đây là một project **hoàn chỉnh có thể chạy**, gồm một application với REST endpoint và bốn test classes:

1. `GreetingMockTest` dùng `MOCK + MockMvc`.
2. `GreetingRandomPortTest` dùng `RANDOM_PORT + TestRestTemplate`.
3. `GreetingDefinedPortTest` dùng `DEFINED_PORT + TestRestTemplate`.
4. `GreetingNonWebTest` dùng `NONE` để đối chiếu.

**Yêu cầu:** JDK 17+, Maven 3.x, Internet truy cập Maven dependencies lần đầu. Để tránh test ảnh hưởng một server đang chạy sẵn, stop các ứng dụng chiếm cổng 18081 trước khi chạy toàn bộ test suite.

### 6.1. Cấu trúc thư mục

~~~text
spring-boot-web-environment-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webtest/
    │   │   ├── WebEnvironmentApplication.java
    │   │   ├── GreetingService.java
    │   │   ├── GreetingResponse.java
    │   │   ├── GreetingRequest.java
    │   │   └── GreetingController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/webtest/
            ├── GreetingMockTest.java
            ├── GreetingRandomPortTest.java
            ├── GreetingDefinedPortTest.java
            └── GreetingNonWebTest.java
~~~

Test classes nằm trong **cùng package** hoặc package con của main class để `@SpringBootTest` tìm được `@SpringBootApplication` tự động. Nếu đặt test ở package không có quan hệ với main, cần dùng `@SpringBootTest(classes=WebEnvironmentApplication.class)` hoặc cấu trúc package đúng.

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-boot-web-environment-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

- `spring-boot-starter-web` dùng Spring MVC và embedded Tomcat.
- `spring-boot-starter-test` cung cấp Spring Test, Spring Boot Test, MockMvc APIs, JUnit Jupiter, AssertJ và Mockito trong test scope.
- Project **không thêm WebFlux**, giúp chứng minh với MVC có thể dùng `MockMvc` cho `MOCK` và `TestRestTemplate` cho real ports.
- Spring Boot parent quản lý phiên bản JUnit/Spring/Test dependencies; tránh khai báo lẫn JUnit4/5 versions không cần thiết.
- Java 17 hỗ trợ `record` để biểu diễn request/response DTO.

### 6.3. application.properties

**`src/main/resources/application.properties`:**

~~~properties
spring.application.name=web-environment-lab

# CỐ Ý không ghi server.port.
# - DEFINED_PORT không override sẽ dùng default 8080.
# - Ở lab ta override DEFINED_PORT sang 18081 trong annotation.
# - RANDOM_PORT chọn ephemeral port.
# - MOCK không mở embedded HTTP listener.
~~~

Với test thật, Spring Boot sẽ kết hợp properties từ application, test annotation, system/environment, active profile và các nguồn khác theo thứ tự ưu tiên. Một cấu hình bên ngoài có thể gây xung đột — hãy ghi lại effective test properties khi debug.

### 6.4. Main application

**`src/main/java/com/example/webtest/WebEnvironmentApplication.java`:**

~~~java
package com.example.webtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebEnvironmentApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebEnvironmentApplication.class, args);
    }
}
~~~

### 6.5. Service chứa nghiệp vụ

**`src/main/java/com/example/webtest/GreetingService.java`:**

~~~java
package com.example.webtest;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greeting(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Service đơn giản giúp test nhìn thấy full context thực sự inject bean. Ứng dụng production có thể dùng DB/external APIs; đó là phần mở rộng cần test data và dependency isolation.

### 6.6. DTO request/response

**`src/main/java/com/example/webtest/GreetingRequest.java`:**

~~~java
package com.example.webtest;

public record GreetingRequest(String name) {
}
~~~

**`src/main/java/com/example/webtest/GreetingResponse.java`:**

~~~java
package com.example.webtest;

public record GreetingResponse(String message) {
}
~~~

Jackson (qua starter-web) serialize record thành JSON `{"message":"Hello, Lan!"}`, deserialize request JSON như `{"name":"An"}` vào `GreetingRequest`. JSON whitespace có thể khác nhưng logical fields phải khớp.

### 6.7. Controller có GET, POST và lỗi 400

**`src/main/java/com/example/webtest/GreetingController.java`:**

~~~java
package com.example.webtest;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/hello")
    public GreetingResponse hello(
            @RequestParam(defaultValue = "World") String name) {
        return new GreetingResponse(service.greeting(name));
    }

    @PostMapping("/echo")
    public GreetingResponse echo(@RequestBody GreetingRequest request) {
        return new GreetingResponse(
                service.greeting(request.name()));
    }

    @GetMapping("/required")
    public ResponseEntity<String> required(
            @RequestParam("code") String code) {
        return ResponseEntity.ok(code);
    }
}
~~~

**Hợp đồng API:**

| Request | Status mong đợi | Response |
| --- | --- | --- |
| `GET /api/hello` | 200 | JSON message `Hello, World!` |
| `GET /api/hello?name=Lan` | 200 | JSON message `Hello, Lan!` |
| `POST /api/echo` body `{"name":"An"}` | 200 | JSON message `Hello, An!` |
| `GET /api/required?code=OK` | 200 | text `OK` |
| `GET /api/required` thiếu code | 400 | Error body tùy MVC/error handling |

**Không hardcode JSON error body** trong tests của bài này vì cấu trúc error response có thể phụ thuộc Boot exception handling, content negotiation và container. Chỉ assert status 400 cho missing required param.

## 7. Test 1 — MOCK + MockMvc (không có embedded server)

**`src/test/java/com/example/webtest/GreetingMockTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class GreetingMockTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void getHelloUsesMvcRequestMapping() throws Exception {
        mvc.perform(get("/api/hello").param("name", "Lan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Lan!"));
    }

    @Test
    void postEchoDeserializesJson() throws Exception {
        mvc.perform(post("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"An\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, An!"));
    }

    @Test
    void missingRequiredParameterIsBadRequest() throws Exception {
        mvc.perform(get("/api/required"))
                .andExpect(status().isBadRequest());
    }
}
~~~

**Điều được test ở đây:**

1. `@SpringBootTest(webEnvironment=MOCK)` tạo full application context nhưng **không mở HTTP port**.
2. `@AutoConfigureMockMvc` cung cấp `MockMvc`, hỗ trợ test MVC dispatch/parameter binding và Jackson serialization.
3. `.param("name","Lan")` mô phỏng query parameter; không cần tạo HTTP client socket.
4. `jsonPath("$.message")` kiểm tra **field** JSON, tránh phụ thuộc whitespace/order.
5. Missing required `code` được Spring MVC map thành HTTP 400 theo request mapping.
6. Filter/security có thể chạy trong MockMvc nếu được cấu hình phù hợp; `@AutoConfigureMockMvc(addFilters = false)` sẽ bỏ filters và có thể che mất một lỗi authorization.
7. Test không chứng minh Tomcat đã khởi động, vì không hề có embedded server.

### 7.1. Viết ngắn hơn mà không đổi mode

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DefaultMockEnvironmentTest {
    // @SpringBootTest mặc định là MOCK.
}
~~~

Đoạn trên chỉ để nhắc về default và **không phải một test class có assertions**. Trong project lab, `GreetingMockTest` là class chạy thực sự. Không tự thêm class trống này nếu muốn suite chỉ gồm test cases có kiểm chứng.

### 7.2. Mock context vẫn “full” như thế nào?

Trong project thực, các `@Component`/`@Service`/`@Repository`/`@Configuration` hợp lệ có thể được tạo trong context. Nếu service gọi external API ngay lúc khởi tạo, test MOCK vẫn có thể fail do dependency thật **không được mock tự động**. Muốn tách dependency, dùng test bean overrides, Testcontainers/WireMock/MockWebServer hoặc profile riêng một cách có chủ đích.

Đây là khác biệt then chốt với `@WebMvcTest(GreetingController.class)`: `@WebMvcTest` chỉ cấu hình **một lát cắt MVC** và thường cần mock/import `GreetingService`. Với `@SpringBootTest(MOCK)` toàn bộ service thật có thể được inject, dù request không đi qua network.

## 8. Test 2 — RANDOM_PORT + TestRestTemplate (HTTP thật)

**`src/test/java/com/example/webtest/GreetingRandomPortTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.address=127.0.0.1")
class GreetingRandomPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void actualHttpServerResponds() {
        assertThat(port).isGreaterThan(0);

        String url = "http://127.0.0.1:" + port
                + "/api/hello?name=Lan";

        ResponseEntity<GreetingResponse> response =
                restTemplate.getForEntity(
                        url, GreetingResponse.class);

        assertThat(response.getStatusCode().is2xxSuccessful())
                .isTrue();
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().message())
                .isEqualTo("Hello, Lan!");
    }

    @Test
    void serverReturnsHttp400ForMissingParam() {
        String url = "http://127.0.0.1:" + port
                + "/api/required";

        ResponseEntity<String> response =
                restTemplate.getForEntity(url, String.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(400);
    }
}
~~~

**Ý nghĩa:**

1. `RANDOM_PORT` khởi động **Tomcat thật** và bind lên một port do OS chọn.
2. `@LocalServerPort` trong Boot 3.3 có package **`org.springframework.boot.test.web.server.LocalServerPort`**; nó được inject khi server đã khởi động.
3. `TestRestTemplate` là HTTP client dành cho tests; ở đây ta dùng URL tuyệt đối để nhìn rõ **port thực**.
4. `@SpringBootTest(properties = "server.address=127.0.0.1")` bind listener localhost để lab không expose trên toàn bộ network interfaces.
5. HTTP request đi qua TCP → Tomcat → Servlet filters → DispatcherServlet → Controller → JSON response.
6. Nếu app còn có management server trên **port riêng**, mode `RANDOM_PORT` cũng có thể cho management server một **random port riêng**, không nhất thiết trùng application port.
7. `assertThat(port).isGreaterThan(0)` không kiểm tra port bằng 8080 vì ephemeral port là bất định.

### 8.1. RANDOM_PORT và server.port=0

Spring Boot thực hiện ý tưởng random port bằng cấu hình tương đương `server.port=0` cho web server test. `0` có nghĩa server yêu cầu OS chọn **một cổng khả dụng khi bind**, không có nghĩa cổng thật luôn là 0.

Nếu application.properties có `server.port=8080` nhưng test dùng `RANDOM_PORT`, test infrastructure yêu cầu random port theo mode; đừng tự tính base URL từ property 8080. Dùng `@LocalServerPort` hoặc test client được Boot cấu hình.

### 8.2. TestRestTemplate có sẵn không?

Trong **Spring Boot 3.3** với `spring-boot-starter-test` và `spring-boot-starter-web` như lab, `TestRestTemplate` có thể được autowire trong running-server tests. Nó có semantics “test friendly”: thông thường không ném exception chỉ vì server trả 4xx/5xx; bạn kiểm tra status/body qua `ResponseEntity`.

Trong một Spring Boot **4.x** project, module/package/client auto-configuration có thể khác; đừng copy `org.springframework.boot.test.web.client.TestRestTemplate` mà không đối chiếu version. Bài này cố định **3.3.5**.

### 8.3. Có thể dùng client Java chuẩn không?

Có. Khi có port thật, bất kỳ HTTP client tương thích cũng có thể gửi request — kể cả JDK 17 `java.net.http.HttpClient`, WebClient, REST Assured hoặc curl từ process khác. `TestRestTemplate` chỉ là một tiện ích, không phải thành phần làm server thật chạy.

Snippet sau nằm **trong một test method có biến `port` đã inject**, không phải source file độc lập:

~~~java
java.net.http.HttpClient client =
        java.net.http.HttpClient.newHttpClient();

java.net.http.HttpRequest request =
        java.net.http.HttpRequest.newBuilder(
                java.net.URI.create(
                        "http://127.0.0.1:" + port + "/api/hello"))
                .GET()
                .build();

java.net.http.HttpResponse<String> response =
        client.send(request,
                java.net.http.HttpResponse.BodyHandlers.ofString());

// response.statusCode() == 200
// response.body() chứa JSON field "message"
~~~

JDK HttpClient có thể được dùng khi muốn kiểm tra details ở tầng HTTP mà không phụ thuộc vào TestRestTemplate. Nên đặt connect/request timeouts để tests không treo vô hạn khi server fail.

## 9. Test 3 — DEFINED_PORT + TestRestTemplate (port cố định)

**`src/test/java/com/example/webtest/GreetingDefinedPortTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.DEFINED_PORT,
        properties = {
                "server.address=127.0.0.1",
                "server.port=18081"
        })
class GreetingDefinedPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void predefinedPortIsActuallyUsed() {
        assertThat(port).isEqualTo(18081);

        String url = "http://127.0.0.1:" + port
                + "/api/hello?name=An";

        ResponseEntity<GreetingResponse> response =
                restTemplate.getForEntity(
                        url, GreetingResponse.class);

        assertThat(response.getStatusCode().value())
                .isEqualTo(200);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().message())
                .isEqualTo("Hello, An!");
    }
}
~~~

**Điểm cần nhớ:**

- `DEFINED_PORT` cũng start Tomcat thật giống `RANDOM_PORT`, chỉ khác **cách lấy port**.
- `server.port=18081` được đặt qua properties của test để không đụng `8080` mặc định của dev server. Dù vậy nếu một process khác đang dùng 18081, test vẫn fail khi bind.
- `@LocalServerPort` vẫn đọc được actual server port, không chỉ dành cho RANDOM_PORT.
- Nếu bỏ `server.port=18081` và không có config nào khác, `DEFINED_PORT` sẽ dùng `8080` theo mặc định Boot.
- Nếu cố tình đặt `server.port=0` với `DEFINED_PORT`, embedded server vẫn có thể bind ephemeral port; không nên lạm dụng tên mode để suy ra giá trị bind thực.

### 9.1. Khi nào DEFINED_PORT có giá trị?

- Có external test fixture/gateway cần gọi đúng host:port mà bạn đã cố định.
- Có test topology gồm nhiều local services, mỗi service có port đã phân phối rõ.
- Test hành vi của config `server.port` cụ thể.

**Không nên dùng làm mặc định CI** khi nhiều jobs chạy trên cùng host. Port conflict/flakiness là rủi ro đáng kể. Với integration tests HTTP thuần, `RANDOM_PORT` thường phù hợp hơn.

### 9.2. Lỗi “Port 18081 was already in use”

Đó là lỗi web server **không bind được**, thường xuất hiện ngay lúc tạo ApplicationContext, **trước khi body của test method chạy**. Đừng chữa bằng tăng timeout của TestRestTemplate hay thêm `@DirtiesContext` bừa; hãy kiểm tra ai đang chiếm cổng, chạy tests sequentially, đổi sang RANDOM_PORT hoặc cấp port riêng có kiểm soát.

## 10. Test 4 — NONE để thấy không cần web environment

**`src/test/java/com/example/webtest/GreetingNonWebTest.java`:**

~~~java
package com.example.webtest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class GreetingNonWebTest {

    @Autowired
    private GreetingService service;

    @Test
    void serviceCanRunWithoutWebServer() {
        assertThat(service.greeting("Lan"))
                .isEqualTo("Hello, Lan!");
    }
}
~~~

`NONE` vẫn tải Spring beans cần cho app và có thể inject `GreetingService`, nhưng **không cấp mock Servlet environment lẫn embedded server**. Trong project lab đơn giản, service không phụ thuộc web runtime nên test sẽ chạy. Với app thật có beans khởi tạo phụ thuộc servlet request/session, cần cấu hình phù hợp và không nhất thiết chọn NONE.

**Không thể dùng `MockMvc` như cách của MOCK test chỉ vì có `@SpringBootTest`**, vì NONE không cấp web context cần thiết.

## 11. Build, chạy và đọc kết quả

Trong thư mục `spring-boot-web-environment-lab`:

~~~bash
mvn clean test
~~~

Bốn class `*Test.java` được Maven Surefire/JUnit Jupiter phát hiện; tập tests dự kiến gồm:

- `GreetingMockTest`: 3 test methods.
- `GreetingRandomPortTest`: 2 test methods.
- `GreetingDefinedPortTest`: 1 test method.
- `GreetingNonWebTest`: 1 test method.

**Tổng: 7 test methods.** Nếu source code/properties giữ nguyên và không có process tranh cổng 18081, kết quả mong đợi là **7 tests PASS, 0 failures, 0 errors**. Console có Spring Boot startup logs, Tomcat “started on port(s)” đối với real-port modes và Maven test summary; không hardcode toàn bộ stdout vì thứ tự logs, JDK/OS/timing thay đổi.

Ví dụ ý nghĩa của output (minh họa, không phải byte-for-byte):

~~~text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0

BUILD SUCCESS
~~~

Khi cần chạy từng case:

~~~bash
mvn -Dtest=GreetingMockTest test
mvn -Dtest=GreetingRandomPortTest test
mvn -Dtest=GreetingDefinedPortTest test
mvn -Dtest=GreetingNonWebTest test
~~~

**Bash/Linux và Windows PowerShell:** các lệnh Maven một dòng ở trên đều diễn đạt ý tưởng chạy một test class; cách shell xử lý `-Dtest=...` có thể yêu cầu quote ở môi trường đặc biệt.

### 11.1. Thử ứng dụng thật bằng curl

Khởi động manual application (không phải test):

~~~bash
mvn spring-boot:run
~~~

Vì `application.properties` không đặt server.port, app phát triển thường mở `8080`:

~~~bash
curl -i http://127.0.0.1:8080/api/hello?name=Lan
~~~

Kỳ vọng status 200, JSON chứa `"message":"Hello, Lan!"`. **Đây là bài kiểm tra thủ công của running app**, không có liên quan đến việc MOCK test cần mở cổng. Dừng app trước khi chạy một test `DEFINED_PORT` nếu app được cấu hình trùng port test.

### 11.2. Đừng kết luận test MOCK đã bind một port từ log bean

`@SpringBootTest(MOCK)` vẫn log Spring context startup và có thể tạo nhiều web-related beans. Nhưng chỉ có thể chứng minh server bind port thật bằng server lifecycle/HTTP exchange ở running-server mode. `@LocalServerPort` không nên được inject vào MOCK test để kỳ vọng một số cổng có nghĩa.

## 12. @LocalServerPort và các trường hợp dễ nhầm

Trong Spring Boot 3.3:

~~~java
import org.springframework.boot.test.web.server.LocalServerPort;
~~~

`@LocalServerPort` là tiện ích inject **cổng HTTP thực tế của embedded web server** vào test. Thường dùng ở `RANDOM_PORT` và có thể ở `DEFINED_PORT`.

~~~java
@LocalServerPort
int port;
~~~

Nó dựa trên giá trị runtime **`local.server.port`** sau khi embedded server đã khởi động.

**Không lẫn ba giá trị:**

- `server.port`: property **yêu cầu** server bind port; nếu là 0 thì yêu cầu OS chọn.
- `local.server.port`: giá trị port **thực tế** sau khi server đã bind.
- `management.server.port` / `local.management.port`: cổng management nếu management server mở riêng.

Nếu application có `management.server.port` khác application server port, đặc biệt ở RANDOM_PORT, management server có thể nhận **random port khác**. Muốn gọi management APIs, cần xác định riêng `@LocalManagementPort`/`local.management.port` trong môi trường phù hợp, không dùng nhầm application `@LocalServerPort`.

### 12.1. Đừng đọc local.server.port quá sớm

`local.server.port` chỉ được xác định **sau lúc embedded server bind xong**. Nếu dùng `@Value("${local.server.port}")` trong một application bean được tạo **trước khi** server start, bean có thể lỗi vì property chưa sẵn. Cách an toàn là đọc `@LocalServerPort` trong integration test sau khi context đã khởi động, hoặc nghe `WebServerInitializedEvent` nếu thực sự cần làm gì ở runtime.

### 12.2. Tại sao không hardcode 8080 trong RANDOM_PORT?

~~~java
// Sai khi test webEnvironment=RANDOM_PORT:
String url = "http://localhost:8080/api/hello";
~~~

Port ephemeral thường **khác 8080**, và server phát triển khác có thể đang chiếm 8080. Viết:

~~~java
// Snippet trong test có @LocalServerPort int port:
String url = "http://127.0.0.1:" + port + "/api/hello";
~~~

hoặc dùng Boot-managed `TestRestTemplate` với relative URI khi được cấu hình root URI phù hợp.

## 13. MockMvc, WebTestClient và TestRestTemplate: chọn đúng client

| Test client | Mock environment? | HTTP server thật? | Dành cho |
| --- | --- | --- | --- |
| `MockMvc` | **Có**, MVC layer | Không tự gọi qua network | Spring MVC request handling |
| `TestRestTemplate` | Không dùng làm mock Servlet request | **Có**, HTTP | Boot 3.3 running-server integration tests |
| `WebTestClient` bound-to-application-context | **Có**, nhất là WebFlux mock | Không | Reactive handler/router tests |
| `WebTestClient` bound-to-server | Không cần mock backend | **Có** | Reactive và các HTTP integration tests nếu dependency hỗ trợ |
| JDK `HttpClient`, curl, REST Assured | Không (trừ khi gắn adapter riêng) | **Có** | Network-level HTTP tests |

### 13.1. MockMvc không phải Mockito

- **Mockito**: tạo mock của method collaborator (service/repository), ví dụ `when(service.greeting(...))`.
- **MockMvc**: tạo servlet request/response mock và thực thi Spring MVC pipeline.

Trong `@SpringBootTest(MOCK)`, bạn có thể dùng **service thật** nhưng **request giả lập**. Nếu muốn stub `GreetingService`, cần khai báo test bean override/mocking phù hợp. Boot 3.3 hỗ trợ `@MockBean`, nhưng khi nâng lên các dòng mới hơn cần đối chiếu khuyến nghị của Spring Framework/Boot (ví dụ `@MockitoBean` trong Spring Framework 6.2). Không trộn API mới vào lab Boot 3.3 mà chưa kiểm tra package.

### 13.2. Có thể dùng WebTestClient cho MVC MOCK không?

Spring Boot 3.3 docs có trường hợp dùng `WebTestClient` để điều khiển MVC tests khi WebFlux test APIs nằm trên classpath và adapter MockMvc được cấu hình. Nhưng **project lab MVC không thêm WebFlux dependency**; dùng `MockMvc` là đường trực tiếp, rõ ràng. Không kết luận rằng `WebTestClient` chỉ chạy được khi start một Netty server.

### 13.3. Trong MOCK, phải chọn cách bind đúng

Cùng API `WebTestClient` có thể được tạo **bound-to-controller/application-context** hoặc **bound-to-server**. Nó không tự trở thành network client chỉ vì dùng fluent syntax `.get().uri(...).exchange()`. Muốn chứng minh socket/network, test phải dùng running-server environment và client configured tới port thật.

## 14. WebFlux: MOCK và RANDOM_PORT với WebTestClient

Chủ đề cũng áp dụng cho **Spring WebFlux**, nhưng test client điển hình là `WebTestClient` thay vì `MockMvc`. Đây là **project riêng**, không dán vào project MVC có `starter-web` để tránh Boot tự ưu tiên Servlet.

### 14.1. pom.xml cho WebFlux test module riêng

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-test-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-webflux` cung cấp Spring WebFlux/reactive server. `spring-boot-starter-test` cung cấp JUnit/Boot Test/WebTestClient test support; `reactor-test` hữu ích khi test `Flux/Mono` với `StepVerifier`. Không có `starter-web` để inbound runtime không chuyển về Servlet.

### 14.2. Cấu trúc tệp project WebFlux

~~~text
webflux-test-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/reactivetest/
    │   ├── ReactiveTestApplication.java
    │   └── ReactiveHelloController.java
    └── test/java/com/example/reactivetest/
        ├── ReactiveMockTest.java
        └── ReactiveRandomPortTest.java
~~~

**`ReactiveTestApplication.java`:**

~~~java
package com.example.reactivetest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveTestApplication.class, args);
    }
}
~~~

**`ReactiveHelloController.java`:**

~~~java
package com.example.reactivetest;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ReactiveHelloController {

    @GetMapping("/reactive/hello")
    public Mono<String> hello(
            @RequestParam(defaultValue = "World") String name) {
        return Mono.just("Hello, " + name + "!");
    }
}
~~~

### 14.3. WebFlux MOCK test: không mở server

**`src/test/java/com/example/reactivetest/ReactiveMockTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ReactiveMockTest {

    @Autowired
    private WebTestClient client;

    @Test
    void helloViaReactiveMockEnvironment() {
        client.get()
                .uri("/reactive/hello?name=Lan")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello, Lan!");
    }
}
~~~

`@AutoConfigureWebTestClient` trong Boot 3.3 (package `org.springframework.boot.test.autoconfigure.web.reactive`) cấu hình `WebTestClient` để đi vào WebFlux handler infrastructure **không mở Netty listener** khi `webEnvironment=MOCK`.

### 14.4. WebFlux RANDOM_PORT test: có Netty server thật

**`src/test/java/com/example/reactivetest/ReactiveRandomPortTest.java`:**

~~~java
package com.example.reactivetest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.address=127.0.0.1")
@AutoConfigureWebTestClient
class ReactiveRandomPortTest {

    @LocalServerPort
    private int port;

    @Autowired
    private WebTestClient client;

    @Test
    void helloOverRealHttpConnection() {
        assertThat(port).isGreaterThan(0);

        client.get()
                .uri("/reactive/hello?name=An")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("Hello, An!");
    }
}
~~~

**Giống nhau ở client API, khác nhau ở transport:** test MOCK dùng mock application handler context; test RANDOM_PORT thực sự start Reactor Netty web server và client gửi HTTP đến bound port. `WebTestClient` của Boot test có thể được preconfigure để resolve relative URI trên running server.

Nếu muốn **DEFINED_PORT với WebFlux**, đổi annotation thành `WebEnvironment.DEFINED_PORT`, đặt `properties={"server.port=18082","server.address=127.0.0.1"}` và dùng `@LocalServerPort` kiểm tra port. Phần còn lại tương tự nhưng lại có nguy cơ port conflict trong CI.

### 14.5. Đừng “bật reactive” chỉ bằng một annotation giả

Nếu project vô tình chứa cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot thường chọn Spring MVC. Khi thật sự cần test reactive app trong trường hợp này, tài liệu Boot hướng dẫn đặt:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive")
class ReactiveConfiguredTest {
    // Test body/config riêng tùy use case.
}
~~~

Đây là snippet minh họa ý tưởng, **không phải một test runnable có assertions**. Cần xác nhận dependencies, runtime server và test client đúng trước khi kết luận đang test WebFlux.

## 15. MOCK không phải @WebMvcTest hay @WebFluxTest

Tất cả đều có thể **không mở cổng thật**, nhưng phạm vi context khác nhau.

| Annotation | Context | Mục đích |
| --- | --- | --- |
| `@SpringBootTest(webEnvironment=MOCK)` | **Full Spring Boot context** với mock web environment | Kiểm thử nhiều tầng wiring và MVC/WebFlux behavior |
| `@WebMvcTest(GreetingController.class)` | **MVC slice** (chủ yếu controller/web MVC infrastructure) | Controller mapping/serialization/error/security filter logic |
| `@WebFluxTest(ReactiveHelloController.class)` | **WebFlux slice** | Reactive controller/web layer |
| `@SpringBootTest(webEnvironment=RANDOM_PORT)` | Full context + embedded server thật | HTTP integration/network behavior |
| `@SpringBootTest(webEnvironment=DEFINED_PORT)` | Full context + fixed-port embedded server | Integration với port được quy định |

**Ví dụ web slice có dependency:** `GreetingController` trong lab cần `GreetingService`. Nếu chỉ test controller bằng `@WebMvcTest(GreetingController.class)`, Spring không tự tạo mọi service thực; phải dùng mock bean hoặc import dependencies cần thiết. Trong `@SpringBootTest(MOCK)`, `GreetingService` được component-scan tạo bình thường.

### 15.1. Khi nào chọn loại test nào?

- Unit test thuần cho `GreetingService.greeting(...)`, không Spring: nhanh nhất, phát hiện logic.
- `@WebMvcTest`: cần đảm bảo mapping/JSON/filters/controller contract ở web slice, mock dependencies rõ.
- `@SpringBootTest(MOCK)`: cần wiring thực và interaction controller/service nhưng không cần network stack.
- `@SpringBootTest(RANDOM_PORT)`: cần chứng minh HTTP socket, server configuration, real status/headers/cookies/network semantics.
- `@SpringBootTest(DEFINED_PORT)`: khi một external participant có ràng buộc cổng chính xác; chấp nhận rủi ro collision.

Không “đẩy hết mọi test sang RANDOM_PORT” khi chỉ cần verify phép cộng của service. Mỗi lần khởi động full context/server tốn chi phí và làm suite chậm hơn.

## 16. Bẫy quan trọng nhất: @Transactional và real HTTP threads

Spring Test có cơ chế **test-managed transaction**. Khi một test được gắn `@Transactional` và cấu hình transaction manager phù hợp, Spring Test thường bắt đầu transaction ở **test thread** rồi rollback sau test method. Nhưng HTTP client/server thật tách luồng.

### 16.1. MOCK với MockMvc

~~~text
JUnit test thread
   |
   | @Transactional test-managed transaction (khi có TxManager)
   |
   '--> MockMvc.perform(...)
           |
           '--> DispatcherServlet / Controller trong cùng test thread
                 |
                 '--> Repository dùng transaction context của test thread
   |
   '--> rollback sau test
~~~

Với MVC **synchronous mock request** và transaction manager đồng bộ thông thường, database writes có thể thuộc test-managed transaction và được rollback. Tuy nhiên nếu controller dispatch async sang thread khác hoặc code tạo transaction riêng (`REQUIRES_NEW`), không được suy rằng mọi side effect đều rollback cùng test.

### 16.2. RANDOM_PORT/DEFINED_PORT với HTTP thật

~~~text
JUnit test thread                         Embedded server thread
     | @Transactional test                   |
     |                                       |
     | HTTP client GET/POST ---------------->|
     |                                       | Controller / @Transactional service
     |                                       | DB write + commit của server tx
     |<--------------------------- HTTP 200  |
     |
     | test transaction ROLLBACK
     '--> KHÔNG rollback transaction server đã commit
~~~

**Cảnh báo trong tài liệu Spring Boot 3.3:** Khi sử dụng `RANDOM_PORT` hoặc `DEFINED_PORT` cho web integration test, HTTP client và server chạy ở **các threads khác nhau**, tức **các transactions khác nhau**. Transaction ở phía server **không** được rollback chỉ vì test method có `@Transactional`.

Đây là nguồn flakiness phổ biến: test tạo dữ liệu thông qua HTTP rồi tưởng `@Transactional` test tự xóa dữ liệu; lần chạy kế tiếp gặp duplicate key hoặc unexpected row count.

### 16.3. Cách cô lập DB cho real HTTP tests

- Dùng **test database riêng**/container riêng (Testcontainers hoặc DB ephemeral) với lifecycle được quản lý.
- Seed và cleanup dữ liệu bằng `@Sql` hoặc repository setup/teardown, bảo đảm cleanup transaction được commit thực sự nếu server writes đã commit.
- Sử dụng IDs/tenant keys duy nhất cho từng test, tránh phụ thuộc thứ tự methods.
- Có explicit cleanup/reset endpoint **chỉ trong test** nếu cần; không expose destructive management endpoints ra production.
- Nếu có migrations/async jobs, chờ điều kiện hoàn thành trước khi assert, tránh `Thread.sleep` dự đoán.
- Dùng transaction boundaries rõ ràng trong application service và test setup.
- Không gắn `@DirtiesContext` chỉ để mong DB server-side được rollback; nó chủ yếu quyết định **context cache**, không xóa tự động mọi external state.

## 17. Spring TestContext caching và tại sao port có thể được tái sử dụng

Spring Test Framework có cache các ApplicationContexts giữa tests có cấu hình tương đương, để tránh start full context liên tục.

### 17.1. Với MOCK

Nhiều tests dùng cấu hình giống nhau có thể share một mock web context (không có port). Nếu test thay mutable singleton state hoặc mock configuration không được reset đúng, test sau có thể bị ảnh hưởng.

### 17.2. Với RANDOM_PORT

Nếu context được cache, **embedded server và random port đó cũng có thể được tái sử dụng** bởi nhiều test classes có cùng cache key. Random port được chọn **lúc web server bind**, không phải từng HTTP call hay từng @Test. Không assert “hai test methods phải có ports khác nhau”.

### 17.3. Với DEFINED_PORT

Đặc biệt nhạy cảm với context cache/parallel tests. Một server test còn hoạt động trên fixed port 18081 có thể khiến test khác (cấu hình context khác) không bind cùng port. Việc test teardown, JUnit parallelization hoặc Maven fork strategy có thể làm xung đột.

**`@DirtiesContext`** yêu cầu Spring test cache loại bỏ/đóng context tại thời điểm được cấu hình; hữu ích khi test thật sự làm thay đổi context state. Nhưng:

- Làm tăng thời gian test khi phải rebuild/restart server.
- Không tự giải quyết một process ngoài suite chiếm port.
- Không tự rollback DB/external side effects.
- Không nên gắn lên mọi test class chỉ vì tiện.

Khi có thể, dùng RANDOM_PORT và isolate external state lành mạnh.

## 18. Profiles và test properties: tránh chạy nhầm config production

`@SpringBootTest` cho phép override properties ngay trên annotation:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "server.address=127.0.0.1",
        "app.feature.new-checkout=false"
    })
class MyIntegrationTest {
}
~~~

**Lưu ý:** Đây là ví dụ cấu hình của một test class chưa có methods, không phải file độc lập trong project lab. Cần property `app.feature.new-checkout` được ứng dụng thực sử dụng mới có hiệu lực nghiệp vụ.

Với test profile:

~~~java
@org.springframework.test.context.ActiveProfiles("test")
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProfiledWebTest {
}
~~~

Tệp `src/test/resources/application-test.properties` có thể chứa:

~~~properties
app.dependency.base-url=http://127.0.0.1:18090
app.feature.new-checkout=false

# Đừng hardcode server.port=8080 cho RANDOM_PORT tests.
~~~

Khi một bean gọi external dependency thật, bạn phải cung cấp stub/test server tương ứng hoặc mock collaborator; `@SpringBootTest` không tự thay external service bằng giả lập.

### 18.1. @DynamicPropertySource và Testcontainers

Một external service/Testcontainers có port được OS chọn có thể công bố runtime properties thông qua `@DynamicPropertySource`. Ví dụ **snippet**:

~~~java
@org.springframework.test.context.DynamicPropertySource
static void registerTestProperties(
        org.springframework.test.context.DynamicPropertyRegistry registry) {
    registry.add("app.dependency.base-url",
            () -> "http://127.0.0.1:18090");
}
~~~

Đây chỉ là ví dụ đăng ký một test property; nếu muốn port dynamic thật, supplier phải đọc **thông tin test server/container đã start**. Không được hardcode 18090 rồi gọi là dynamic. `@DynamicPropertySource` khác `@LocalServerPort`: nó thường dùng để cung cấp **dependencies’ connection addresses trước khi context xây**, còn `@LocalServerPort` đọc inbound web listener sau khi server start.

### 18.2. Test properties và environment precedence

Ngay cả khi bạn viết `server.port=8080` trong `src/main/resources/application.properties`, `RANDOM_PORT` làm web server sử dụng random port qua test infrastructure. Với `DEFINED_PORT`, property có hiệu lực là kết quả merge các nguồn. Nếu thấy bind sai port, kiểm tra:

- `@SpringBootTest(properties=...)`, `@TestPropertySource`.
- `@ActiveProfiles` và `application-test.properties`.
- JVM system properties/environment variables.
- Test framework/context caching và Maven fork settings.
- Application boot version, embedded server type, web application type.

Đừng đoán port từ tên annotation nếu có config override bất thường.

## 19. Mock filter/security behavior và HTTP container behavior

Có hai nhóm lỗi kiểm thử web thường gặp.

### 19.1. MOCK có filters nhưng không đồng nghĩa test security đúng

`@AutoConfigureMockMvc` mặc định hỗ trợ áp dụng Servlet filters đã đăng ký; nếu Spring Security có trên classpath, cần đảm bảo security filter chain và test user/auth phù hợp. Dùng `addFilters=false` để test controller “đỡ phải login” có thể khiến suite PASS dù production unauthorized requests bị xử lý sai.

Hãy dùng Spring Security test support (`@WithMockUser`, `SecurityMockMvcRequestPostProcessors` hoặc auth mechanism phù hợp) khi security contract là một phần của hành vi cần kiểm chứng.

### 19.2. MOCK không tái hiện mọi behavior của embedded container

Một mock servlet request có thể đi qua DispatcherServlet và Spring MVC exception resolution, nhưng **không** tạo cùng network/container error page, TLS, proxy headers hoặc Tomcat connector behavior. Ví dụ official Spring Boot docs lưu ý custom error page phụ thuộc container error page support, nên phải dùng running-server test nếu muốn verify rendering end-to-end.

**Khi chọn RANDOM_PORT**, đừng tự nghĩ test sẽ tự đi qua reverse proxy production. Nó chỉ chạy embedded server local trong test process. Để kiểm thử NGINX/ingress/firewall, cần môi trường integration/staging riêng thực sự có các components đó.

## 20. Cấu hình server thật có những điều khác biệt nào?

### 20.1. Đường đi MOCK

~~~text
Test method
  |
  | MockMvc.perform(get("/api/hello"))
  v
MockHttpServletRequest/MockHttpServletResponse
  |
  v
MVC DispatcherServlet / handlers / converters
  |
  '--> MvcResult assertions
~~~

### 20.2. Đường đi RANDOM_PORT hoặc DEFINED_PORT

~~~text
Test method
  |
  | TestRestTemplate / real HTTP client
  |
  v
TCP socket to 127.0.0.1:<bound-port>
  |
  v
Embedded Tomcat/Netty server
  |
  v
Web filters -> MVC/WebFlux pipeline
  |
  v
HTTP status + headers + body
  |
  '--> Client deserializes/asserts
~~~

### 20.3. Chỉ running server mới kiểm tra được những gì?

- Lỗi port binding/configuration connector.
- Thực tế một client độc lập có kết nối được host:port không.
- Server compression headers/connection behavior (nếu đã bật).
- Network timeouts và socket lifecycle.
- TLS certificate/handshake, khi test fixture cấu hình TLS.
- HTTP2/WebSocket upgrades ở web server hỗ trợ, với client tương ứng.
- Một số error page/rendering behaviors do container xử lý.

**Không tự suy running-server mode cover mọi production path.** Nếu ứng dụng đằng sau CDN, WAF, service mesh, API gateway hoặc mTLS ingress, test local RANDOM_PORT chưa test các thành phần đó.

## 21. Những lỗi thường gặp khi chạy tests

| Lỗi / dấu hiệu | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `No qualifying bean of type MockMvc` | Chưa có `@AutoConfigureMockMvc` hoặc không phải MVC mock context | Thêm annotation và dùng MOCK/MVC đúng |
| `@LocalServerPort` không có giá trị trong MOCK | Không có embedded server thật | Không inject port ở MOCK; chọn RANDOM_PORT/DEFINED_PORT |
| `Connection refused: localhost:8080` với RANDOM_PORT | Hardcode port 8080, server dùng ephemeral port | Dùng `@LocalServerPort`/Boot test client |
| `Port 18081 already in use` trong DEFINED_PORT | App/process/test khác chiếm cổng | Đổi port, stop process, dùng RANDOM_PORT |
| Test MOCK PASS, live test FAIL | Container/network/TLS/error page hoặc client behavior khác | Quan sát running server logs, real HTTP response |
| 404 khi gọi endpoint | Sai `@RequestMapping`, context path, URI | Kiểm tra mapping, context-path, HTTP method |
| `SpringBootConfiguration not found` | Test package ngoài phạm vi tìm main class | Đặt test dưới main package hoặc `classes=...` |
| Test `@Transactional` không rollback DB writes từ HTTP | Client/server khác thread/transaction | DB isolation và cleanup explicit |
| Suite flake khi parallel | Fixed-port server collision hoặc shared test state | RANDOM_PORT, isolate resources, quản lý context |
| `WebTestClient` không autowire vào MVC project | WebFlux test APIs/auto-config không có | Dùng MockMvc/TestRestTemplate hoặc thêm deps/adapter đúng |
| Chạy WebFlux nhưng logs khởi động Tomcat/MVC | Có cả starter-web và webflux, MVC được ưu tiên | Kiểm tra classpath/web-application-type |
| Test 401/403 khi bật Spring Security | Security filters hoạt động nhưng test thiếu auth | Dùng Spring Security test support phù hợp |
| Missing Content-Type hoặc JSON field khác | Client, converter/DTO hoặc content negotiation | Inspect raw HTTP body/headers, JSON serializer |
| test clients treo lâu | External dependency không timeout hoặc server chưa ready | Timeout, isolate dependency, startup checks |
| Test flaky vì random port khác giữa methods | Code giả định port cố định | Inject actual port; không ghi lại trong static singleton quá sớm |
| `@DirtiesContext` không xóa dữ liệu | Nó đóng/evict Spring context, không reset DB remote | Dùng DB cleanup/test data isolation |
| Health management port khác app port | Dedicated management server | Inject local.management.port hoặc cấu hình management riêng |
| TestRestTemplate import không có trên Boot 4 | API/module đổi theo version | Pin docs đúng Boot version, sửa deps/import phù hợp |
| App fail ngay khi test tạo context | Bean init truy cập DB/external service thật | Test config/containers/mocks, không đổ cho webEnvironment |

### 21.1. Ba phép kiểm tra khi debug

1. **Đang dùng webEnvironment nào?** Nếu MOCK, tuyệt đối không kiểm tra network port như mục tiêu của test. Nếu RANDOM_PORT/DEFINED_PORT, xác minh server đã bind và client URL đúng.
2. **Test client là loại nào và bind vào đâu?** MockMvc/WebTestClient bound-to-context khác TestRestTemplate/WebTestClient bound-to-server.
3. **Tài nguyên ngoài có được kiểm soát?** DB, Kafka, HTTP downstream, file system, security credentials và test context caching có thể gây lỗi dù bản thân HTTP handler đúng.

## 22. Các anti-pattern nên tránh

1. **“@SpringBootTest luôn bật server thật.”** Sai; default MOCK không start server.
2. **“MOCK chỉ load controller.”** Sai; đó là full Boot context, khác `@WebMvcTest`.
3. **“MockMvc gửi request qua localhost.”** Sai; MockMvc xử lý ở MVC test infrastructure.
4. **“RANDOM_PORT sẽ chọn port khác cho mỗi @Test method.”** Sai; chọn khi server context bind, cache có thể reuse.
5. **“DEFINED_PORT mặc định luôn bằng 8080 dù config server.port khác.”** Sai; dùng effective server.port.
6. **“RANDOM_PORT luôn cần @LocalServerPort.”** Không tuyệt đối; Boot-configured clients có thể có base URL, nhưng annotation giúp biết actual port.
7. **“@LocalServerPort thuộc package cũ ở mọi bản Boot.”** Sai; ở Boot 3.3 dùng `org.springframework.boot.test.web.server.LocalServerPort`.
8. **“@Transactional test rollback mọi server-side HTTP write.”** Sai khi client/server ở threads/transactions khác nhau.
9. **“Có WebTestClient nghĩa là server Netty đã start.”** Sai; WebTestClient có mock mode.
10. **“Có WebClient trong Spring MVC nghĩa web stack reactive.”** Sai; Boot ưu tiên MVC khi cả starters.
11. **“@DirtiesContext làm sạch external DB.”** Sai; cần DB cleanup riêng.
12. **“Test chạy ở port cố định luôn ổn định hơn random.”** Sai trong CI parallel shared hosts.
13. **“Mock test PASS chứng minh TLS/HTTP2/ingress hoạt động.”** Sai; phải test running server và hạ tầng tương ứng.
14. **“Tắt mọi servlet filters để tests dễ pass.”** Có thể che security regression.
15. **“Gắn @SpringBootTest cho tất cả unit tests giúp chất lượng hơn.”** Không; làm suite chậm và dễ phụ thuộc môi trường ngoài.
16. **“Một HTTP client call từ test bằng RestTemplate ở MOCK tự chạy được.”** Không có listener; cần TestRestTemplate trong real server mode hoặc MockMvc.
17. **“Port 0 nghĩa server lắng nghe port 0.”** Không; đó là yêu cầu OS cấp ephemeral port.
18. **“Test với app thật cục bộ là end-to-end toàn hệ thống.”** Không nếu external database, gateway, proxy vẫn bị mock/bỏ qua.

## 23. Bộ câu hỏi tự kiểm tra

**Câu 1.** `@SpringBootTest` không khai báo `webEnvironment` thì server có mở cổng HTTP thật không?

**Câu 2.** `MOCK` với `@AutoConfigureMockMvc` khác `@WebMvcTest` về phạm vi ApplicationContext như thế nào?

**Câu 3.** Khi nào cần `RANDOM_PORT` thay vì `MOCK`?

**Câu 4.** `DEFINED_PORT` sẽ lắng nghe port nào nếu không có `server.port` ở bất kỳ cấu hình nào?

**Câu 5.** Đặt `server.port=18081` trong một `DEFINED_PORT` test và có process khác đang listen 18081; điều gì xảy ra?

**Câu 6.** `@LocalServerPort` lấy giá trị từ đâu, và tại sao không dùng nó trong MOCK test?

**Câu 7.** Hai test methods trong `RANDOM_PORT` class có bắt buộc dùng hai ports khác nhau không?

**Câu 8.** `WebTestClient` có thể chạy cả mocked WebFlux context và running WebFlux server không?

**Câu 9.** Với real HTTP server, test method `@Transactional` có rollback transaction trong controller/service request không?

**Câu 10.** Vì sao MOCK không đủ để chứng minh custom container error page?

**Câu 11.** Có cả Spring MVC và WebFlux starters, Boot 3.3 thường chọn stack nào?

**Câu 12.** Tại sao DEFINED_PORT dễ gây flakiness khi chạy test parallel trong CI?

**Câu 13.** TestRestTemplate và MockMvc khác nhau ở đâu khi cùng assert status=200?

**Câu 14.** Một MockMvc test PASS nhưng HTTPS certificate sai. Có mâu thuẫn không?

**Câu 15.** Khi test class không tìm thấy `@SpringBootConfiguration`, nên sửa cấu trúc package hay test config thế nào?

**Câu 16.** `WebEnvironment.NONE` có thể dùng để test một `@Service` không phụ thuộc web không?

**Câu 17.** Tại sao `@DirtiesContext` không tự xóa database row được server thread commit?

**Câu 18.** Dùng `@SpringBootTest(RANDOM_PORT)` rồi gọi hardcoded `http://localhost:8080` có đúng không?

**Đáp án định hướng:**

1. Không, mặc định là **MOCK**.
2. MOCK load **full application context**; `@WebMvcTest` chỉ MVC slice.
3. Khi cần real socket/server/HTTP container behavior, TLS/headers/network-level integration.
4. **8080** theo mặc định Boot nếu không override.
5. Context/server startup fail do port conflict trước khi test assertions chạy.
6. Đọc actual bound port từ runtime `local.server.port`; MOCK không mở server thật.
7. Không; random port chọn khi context start, có thể reuse do caching.
8. Có; xem bound-to-context và bound-to-server mode.
9. Không tự rollback; HTTP server thread dùng transaction riêng.
10. MockMvc không thực thi toàn bộ embedded servlet container error-page machinery.
11. Spring MVC/Servlet, trừ khi override web-application-type.
12. Nhiều processes/contexts có thể tranh cùng fixed port.
13. MockMvc thực thi fake Servlet request; TestRestTemplate gửi real HTTP request.
14. Không, MOCK không thử TLS.
15. Đặt test cùng package/subpackage main hoặc dùng `@SpringBootTest(classes=...)`.
16. Có, nếu service/config không phụ thuộc web-specific beans.
17. `@DirtiesContext` chủ yếu quản lý Spring context cache; DB state cần reset/cleanup riêng.
18. Sai; phải dùng actual `@LocalServerPort` hoặc test client được config.

## 24. Bài tập thực hành mở rộng

### Bài tập A — chuyển MOCK sang RANDOM_PORT

Lấy `GreetingMockTest`, tạo **class mới** dùng `RANDOM_PORT`, `TestRestTemplate` và `@LocalServerPort` thay cho `MockMvc`. So sánh log startup Tomcat, thời gian chạy và HTTP response. Giải thích vì sao việc thay mỗi annotation mà giữ `mvc.perform(...)` sẽ không chứng minh requests đi qua TCP.

### Bài tập B — thay đổi DEFINED_PORT bằng profile

Thêm `src/test/resources/application-it.properties`:

~~~properties
server.port=18111
server.address=127.0.0.1
~~~

Rồi tạo test `DEFINED_PORT + @ActiveProfiles("it")`, không override `server.port` ở annotation. Xác minh port 18111. Chạy song song hai Maven processes cùng profile rồi quan sát conflict; thử đổi một test sang RANDOM_PORT.

### Bài tập C — test POST JSON

Từ `GreetingMockTest.postEchoDeserializesJson()`, viết real HTTP `TestRestTemplate.postForEntity(...)` tương ứng. So sánh result body/headers/encoding, không dựa vào exact JSON whitespace.

### Bài tập D — thêm Spring Security

Bảo vệ `GET /api/hello` bằng một security filter chain test. So `@AutoConfigureMockMvc` mặc định với `addFilters=false`. Dùng Spring Security test support để test unauthorized/authenticated behavior đúng; không vô hiệu hóa security trên production chỉ để test PASS.

### Bài tập E — transaction rollback thực tế

Thêm database test riêng với một POST ghi row. Chạy test `@Transactional` qua `MockMvc` synchronous và qua `RANDOM_PORT`. Quan sát DB sau test, giải thích vì sao server transaction đã commit không chịu test-managed rollback. Sử dụng DB ephemeral/rollback cleanup rõ ràng; tránh làm trên DB thật.

### Bài tập F — WebFlux

Dùng project WebFlux mục 14, thêm test `DEFINED_PORT` tại 18082 và so sánh `WebTestClient` MOCK/RANDOM/DEFINED. Ghi lại actual port và xác minh HTTP requests đi qua Reactor Netty ở running-server modes.

### Bài tập G — kiểm tra management port

Thêm Actuator vào một test project có management server riêng, đặt management port phù hợp. Dùng `@LocalServerPort` và `@LocalManagementPort` để chứng minh hai bound ports là hai khái niệm khác nhau; ghi nhận rằng `RANDOM_PORT` có thể làm management port cũng được chọn ngẫu nhiên.

## 25. Checklist chọn webEnvironment trong dự án

- [ ] Xác định mục tiêu test là **controller behavior**, **wiring** hay **network/server runtime**.
- [ ] Với `@SpringBootTest` không khai báo mode, hiểu rõ default **MOCK**.
- [ ] Với MVC MOCK, dùng `@AutoConfigureMockMvc` và `MockMvc`; không giả định embedded server đang nghe.
- [ ] Với WebFlux MOCK, dùng `@AutoConfigureWebTestClient` và WebTestClient bound-to-context.
- [ ] Với running-server, chọn `RANDOM_PORT` trừ khi có lý do rõ cần DEFINED_PORT.
- [ ] Với `RANDOM_PORT`, đọc actual port bằng `@LocalServerPort` hoặc Boot-configured client, không hardcode 8080.
- [ ] Với `DEFINED_PORT`, đặt port riêng cho test, quản lý conflicts và parallel CI jobs.
- [ ] Giữ test classes dưới package của `@SpringBootApplication` hoặc chỉ rõ `classes=...`.
- [ ] Dùng `spring-boot-starter-test` ở test scope, pin version BOM.
- [ ] Không nhầm MockMvc với Mockito, `MOCK` với `@WebMvcTest`.
- [ ] Kiểm tra app đang MVC hay WebFlux thực tế khi có cả hai starters.
- [ ] Với real HTTP tests, đừng dựa vào `@Transactional` test để rollback server-side writes.
- [ ] Dùng test database/dependency isolation và cleanup tường minh.
- [ ] Hiểu context caching và không lạm dụng `@DirtiesContext`.
- [ ] Test security filters đúng thay vì disable filters để suite pass.
- [ ] Với proxy/TLS/HTTP2/network bugs, dùng running-server và môi trường test tương ứng.
- [ ] Test thật các trường hợp 2xx, 4xx, auth, serialization, startup failure và port conflict.
- [ ] Theo dõi flaky tests, startup overhead và môi trường CI.
- [ ] Khi nâng Spring Boot 3.x → 4.x, đối chiếu lại imports/modules của test clients theo version.

## 26. Tài liệu tham khảo chính thức

1. **Spring Boot 3.3 — Testing Spring Boot Applications** (MOCK/RANDOM_PORT/DEFINED_PORT/NONE, transactions, MockMvc, WebTestClient, TestRestTemplate): https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
2. **Spring Boot 3.3 — Testing Overview** (starter-test, JUnit, Mockito/AssertJ): https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
3. **Spring Boot 3.3 — @SpringBootTest Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/SpringBootTest.html
4. **Spring Boot 3.3 — @LocalServerPort Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/server/LocalServerPort.html
5. **Spring Boot 3.3 — @AutoConfigureMockMvc Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html
6. **Spring Boot 3.3 — @AutoConfigureWebTestClient Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/web/reactive/AutoConfigureWebTestClient.html
7. **Spring Boot 3.3 — TestRestTemplate Javadoc**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/web/client/TestRestTemplate.html
8. **Spring Framework 6.1 — Spring MVC Testing (MockMvc)**: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
9. **Spring Framework 6.1 — Spring WebFlux Testing (WebTestClient)**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
10. **Spring Framework — TestContext transaction management**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html
11. **Spring Framework — TestContext context caching**: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
12. **Spring Framework — @DynamicPropertySource**: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dynamicpropertysource.html
13. **Spring Boot 3.3 — Test Slices**: https://docs.spring.io/spring-boot/3.3/reference/test-auto-configuration/slices.html
