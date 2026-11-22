# Giới hạn của MockMvc so với gọi server qua HTTP thật

## 1. Bức tranh tổng quan

**MockMvc** là công cụ của Spring Test để kiểm thử **Spring MVC request handling** mà **không cần khởi động một HTTP server đang lắng nghe cổng mạng**. Khi chạy `mockMvc.perform(...)`, Spring Test tạo các đối tượng request/response giả lập theo Servlet API rồi đưa chúng qua `DispatcherServlet` và các thành phần MVC phù hợp. Bạn vẫn kiểm tra được request mapping, argument binding, JSON converter, validation, controller advice, nhiều filter và logic ứng dụng; nhưng không có kết nối TCP thực từ một HTTP client đến một embedded servlet container.

Ngược lại, bài kiểm thử gửi HTTP thật, ví dụ dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `java.net.http.HttpClient`, khởi động embedded server, lấy cổng đang lắng nghe và gửi request qua socket. Điều này kiểm tra thêm **bề mặt HTTP transport, servlet container và việc client/server chạy tách thread** mà MockMvc không trực tiếp bao phủ.

Cả hai đều hữu ích. Sai lầm thường gặp là coi MockMvc như “toàn bộ ứng dụng production” hoặc coi một request HTTP qua `RANDOM_PORT` đã tự động kiểm chứng mọi thứ ở hạ tầng production (proxy/TLS/load balancer/cloud network). Hai nhận định đó đều quá rộng.

**Mục tiêu học tập:**

- Giải thích chính xác MockMvc thực thi những tầng nào và bỏ qua những tầng nào.
- So sánh `@WebMvcTest`, `@SpringBootTest(MOCK) + @AutoConfigureMockMvc` và `@SpringBootTest(RANDOM_PORT)`.
- Viết ví dụ Java 17+/Spring Boot 3.x có thể chạy, gồm test MockMvc và test gửi HTTP thật qua JDK HttpClient tới **cùng endpoint**.
- Phân biệt hành vi filter/Spring Security, session/cookie, async, encoding, networking, port, transaction và rollback.
- Chọn công cụ theo lỗi cần phát hiện, không vì công cụ nào “mạnh hơn” theo tên.
- Tránh hiểu nhầm về Spring Boot 3/4, WebFlux, Spring TestContext cache và môi trường CI.

## 2. MockMvc thật sự chạy những gì?

### 2.1. Request được xử lý trong JVM test

Khi gọi:

```java
mockMvc.perform(get("/api/greetings/Lan"))
       .andExpect(status().isOk());
```

đây là **đoạn trích nằm trong test đã được cấu hình MockMvc**, không phải chương trình Java độc lập. Trình tự khái niệm:

```text
JUnit test method
   |
   +-- MockMvc.perform(...)
         |
         +-- MockHttpServletRequest / MockHttpServletResponse
         |
         +-- Servlet Filter chain (nếu được đăng ký vào MockMvc)
         |
         +-- DispatcherServlet
               |
               +-- HandlerMapping
               +-- HandlerAdapter
               +-- Argument resolvers, data binding, validation
               +-- Controller --> Service --> Repository (nếu cấu hình)
               +-- HttpMessageConverter, exception resolvers
         |
         +-- Mock response --> status(), header(), jsonPath()...
```

**Không có tầng HTTP socket thật giữa test method và DispatcherServlet.** Vì thế MockMvc có thể kiểm tra sâu cách Spring MVC xử lý request mà không cần cấp phát cổng mạng. Nó rất nhanh và chẩn đoán lỗi controller/mapping tương đối chính xác.

**Lưu ý:** các servlet filter chỉ chạy nếu được đăng ký với MockMvc theo cấu hình. Khi dùng Spring Boot `@AutoConfigureMockMvc`, `addFilters = true` là mặc định và đưa các filter thích hợp từ context vào mock pipeline. Với `MockMvcBuilders.standaloneSetup(...)` tự tạo, cấu hình filter khác và không tự động phản ánh toàn bộ application.

### 2.2. Vì sao MockMvc không phải mock controller?

Tên “MockMvc” dễ gây hiểu nhầm. MockMvc **không tự thay controller, service hoặc repository thành Mockito mock**. Nó tạo mock **Servlet request/response** và chạy cơ chế Spring MVC.

- Với `@WebMvcTest(SomeController.class)`: Spring Boot nạp **MVC slice** có controller và các thành phần web phù hợp; service/repository thường cần mock/import riêng.
- Với `@SpringBootTest(webEnvironment = MOCK)` kết hợp `@AutoConfigureMockMvc`: Spring Boot nạp **application context đầy đủ theo cấu hình test**, nhưng vẫn không khởi động embedded server.
- Với `MockMvcBuilders.standaloneSetup(controller)`: bạn tự cung cấp controller và infrastructure cần thiết; không tự động nạp đầy đủ context.

Vì vậy hai bài test đều dùng MockMvc nhưng có **độ rộng của dependency graph** hoàn toàn khác nhau. Phải xác định đồng thời **cách xây ApplicationContext** và **cách gửi request**.

## 3. HTTP thật bổ sung tầng nào?

Một bài test chạy real HTTP, thường với:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RealHttpTest {
    @LocalServerPort
    int port;
}
```

sẽ khởi động embedded server (Tomcat, Jetty hoặc server container tương ứng mà dự án cấu hình) và lắng nghe trên cổng ngẫu nhiên. JDK `HttpClient`, `TestRestTemplate`, `RestClient` hoặc `WebTestClient.bindToServer()` có thể gửi HTTP đến cổng đó.

Luồng thực thi khác:

```text
JUnit test method (client thread)
   |
   +-- HTTP client xây method/URI/header/body
   |
   +-- HTTP encoding, TCP socket, localhost:<randomPort>
   |
   +-- Embedded servlet container / connector
   |      |
   |      +-- Parse request line, headers, body
   |      +-- Servlet request/response thực
   |      +-- Configured servlet filter chain
   |      +-- DispatcherServlet
   |             +-- Controller --> Service --> Repository
   |             +-- MVC converters / exception resolvers
   |
   +-- HTTP response bytes qua socket
   |
   +-- Client decode response --> assertions
```

Điều này có thể phát hiện thêm lỗi về **server startup, cổng lắng nghe, container integration, network-level request/response framing, HTTP client behavior, timeout và cấu hình transport**. Tuy nhiên nó **không tự tái hiện** reverse proxy, TLS termination, load balancer, firewall, WAF, internet latency hoặc ingress configuration nếu những thành phần đó không nằm trong môi trường test.

## 4. Ma trận so sánh thực tế

| Khía cạnh | MockMvc | Gửi HTTP thật tới embedded server |
|---|---|---|
| Spring MVC routing/controller | Có | Có |
| JSON serialization/deserialization | Có, theo converters được cấu hình | Có, cộng với HTTP request/response encoding |
| `@Valid`, binding, controller advice | Có | Có |
| Service/repository thật | Tùy application context đã nạp | Tùy application context đã nạp |
| Filter chain | Có **nếu được đăng ký trong MockMvc** | Đi qua filter chain do servlet container/app đăng ký |
| Authentication/authorization | Có thể kiểm tra với Spring Security Test và filter chain | Có thể kiểm tra theo thực tế client/server |
| Cổng TCP đang lắng nghe | **Không** | **Có** |
| Connector của Tomcat/Jetty/Undertow | Không chạy qua socket/connector | Có, nếu đó là embedded server được chọn |
| HTTP parser, header size, keep-alive | Không kiểm chứng bằng đường network | Có thể kiểm chứng với client/connector phù hợp |
| TLS handshake, chứng chỉ | Không | Có **nếu test cấu hình HTTPS thật** |
| Reverse proxy, gateway, LB | Không | **Không**, trừ khi đưa chúng vào môi trường test |
| Client và server ở hai thread | Thường không ở đường đồng bộ | Có |
| `@Transactional` trên test method | Có thể bao phủ synchronous MVC processing | Không tự bao phủ giao dịch server thread |
| Hiệu năng chạy suite | Thường nhanh, ít tốn tài nguyên | Thường nặng hơn do server/port/socket |
| Phát hiện lỗi network timeout | Không đo được network timeout thật | Có thể kiểm tra timeout của client/server được cấu hình |
| Kiểm tra response JSON/status | Có | Có |

**Không coi bảng là cam kết tuyệt đối:** ví dụ Spring MVC async trong MockMvc có thể sử dụng thread phụ; một real HTTP test có thể dùng client quá đơn giản nên bỏ qua lỗi browser-specific; full-context test có thể mock các gateway ngoài. Hãy xác định phạm vi bằng cấu hình và assertions cụ thể.

## 5. Chọn đúng annotation theo Spring Boot

### 5.1. MockMvc với MVC slice

```java
@WebMvcTest(controllers = GreetingController.class)
class GreetingSliceTest {

    @Autowired
    MockMvc mockMvc;
}
```

Đây là **snippet cấu hình**, thiếu test methods. `@WebMvcTest` hướng đến controller và các component hỗ trợ MVC; không tự nạp mọi service. Phù hợp cho kiểm tra mapping, validation, JSON, exception handler trong một lát cắt web.

### 5.2. MockMvc với application context đầy đủ

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class GreetingFullMockMvcTest {

    @Autowired
    MockMvc mockMvc;
}
```

Mặc dù context có thể chứa real service/repository, **HTTP server không được khởi động**. Đây là cách kiểm tra phối hợp các Spring bean và MVC trong JVM test, không phải bài test socket.

`MOCK` là mặc định của `@SpringBootTest`. Ghi tường minh giúp người đọc phân biệt với `RANDOM_PORT`.

### 5.3. Real HTTP server với cổng ngẫu nhiên

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class GreetingHttpTest {

    @LocalServerPort
    int port;
}
```

Trên Spring Boot 3.x, import `@LocalServerPort` từ `org.springframework.boot.test.web.server.LocalServerPort`. Chọn một HTTP client và gửi request tới `http://127.0.0.1:<port>/...`; server đã mở socket.

**Không cần** `@AutoConfigureMockMvc` để dùng JDK `HttpClient`. Nếu thêm cả hai vào một test `RANDOM_PORT`, vẫn phải phân biệt lời gọi nào là `mockMvc.perform(...)` (trong JVM) và lời gọi nào là HTTP thật (qua port). Chỉ vì annotation của test khởi động real server không làm `MockMvc.perform` đột nhiên đi qua TCP.

### 5.4. `DEFINED_PORT`, `NONE` và khi nào không dùng

- `DEFINED_PORT` khởi động server trên cổng được cấu hình, mặc định thường là 8080. Phù hợp khi phải tương tác với một hệ thống ngoài test process nhưng dễ gây xung đột khi chạy song song.
- `NONE` khởi động SpringApplication không có web environment; nó **không phải lựa chọn** cho servlet MockMvc request processing.
- `RANDOM_PORT` phù hợp hơn cho real HTTP integration test trong CI vì tránh tranh chấp cổng giữa nhiều job.

Nếu dự án có management server ở port riêng, một `RANDOM_PORT` test có thể khiến management server chạy trên cổng ngẫu nhiên riêng nữa. Khi cần kiểm tra actuator endpoint, hãy xác định đúng cổng, context path và security policy.

## 6. Ví dụ chạy được: một ứng dụng, hai phương pháp test

Ta sẽ kiểm tra cùng endpoint qua hai con đường: (1) `MockMvc`, (2) JDK `HttpClient` qua real HTTP. Chúng có cùng logic, cùng cấu hình web, cùng filter thử nghiệm. Sự khác biệt nằm ở cách request được đưa vào Spring MVC.

**Yêu cầu:** Java 17+, Spring Boot **3.x**, JUnit Jupiter, Servlet MVC (ví dụ `spring-boot-starter-web`). Không cần PostgreSQL, Docker, external HTTP, Spring Security hay data store. Ví dụ độc lập với dự án khác nếu đặt đúng tên tệp/package và cấu hình build hợp lệ.

### 6.1. Dependencies và build tool

Gradle Groovy DSL — thêm vào `build.gradle` đã có Spring Boot plugin, repositories và Java toolchain thích hợp:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven — phần dependency của `pom.xml` đã có Spring Boot parent/BOM và Surefire tương thích:

```xml
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
```

Đây là **snippets**, không phải toàn bộ build file. Không thêm dependency trùng nếu ứng dụng đã có. JDK 17 có sẵn `java.net.http.HttpClient` nên không cần thêm thư viện HTTP client cho test.

### 6.2. Cây tệp

```text
src/
├── main/java/com/example/mvclimits/
│   ├── BoundaryApplication.java
│   ├── GreetingController.java
│   └── MarkerFilter.java
└── test/java/com/example/mvclimits/
    ├── MockMvcBoundaryTest.java
    └── RealHttpBoundaryTest.java
```

Đặt các class dưới package `com.example.mvclimits` để `@SpringBootApplication` scan đúng các bean. Không có bean nào gọi dịch vụ ngoài; không có mutable shared fixture.

### 6.3. Application class

**File `src/main/java/com/example/mvclimits/BoundaryApplication.java`:**

```java
package com.example.mvclimits;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

Không cấu hình port cố định. Với `MOCK` test, server không mở cổng; với `RANDOM_PORT` test, Spring Boot tự chọn port đang rảnh.

### 6.4. Controller nhận path, header và JSON body

**File `src/main/java/com/example/mvclimits/GreetingController.java`:**

```java
package com.example.mvclimits;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    public record GreetingRequest(String name) {}

    public record GreetingReply(String message, String requestId) {}

    @GetMapping("/{name}")
    public GreetingReply greet(
            @PathVariable String name,
            @RequestHeader(
                name = "X-Request-Id",
                required = false
            ) String requestId) {

        return reply(name, requestId);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public GreetingReply create(
            @RequestBody GreetingRequest request,
            @RequestHeader(
                name = "X-Request-Id",
                required = false
            ) String requestId) {

        return reply(request.name(), requestId);
    }

    private GreetingReply reply(String name, String requestId) {
        String id = requestId == null ? "absent" : requestId;
        return new GreetingReply("Xin chào " + name, id);
    }
}
```

Đây là một controller đơn giản. GET chứng minh path/header binding; POST chứng minh JSON request-body conversion, response status 201 và JSON response conversion. Không có validation logic trong ví dụ — để tránh đánh đồng JSON parsing với Bean Validation, nội dung JSON sai cú pháp sẽ được kiểm tra riêng.

### 6.5. Servlet Filter thật, dùng trong cả hai cách test

**File `src/main/java/com/example/mvclimits/MarkerFilter.java`:**

```java
package com.example.mvclimits;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class MarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Filter-Visited", "yes");
        chain.doFilter(request, response);
    }
}
```

Filter gắn một response header dễ kiểm tra. Khi Boot auto-configures MockMvc với `addFilters=true` (mặc định), filter bean được thêm vào mock chain. Khi chạy real server, filter cũng được Boot đăng ký với servlet container. Cả hai bài test đều kiểm tra header `X-Filter-Visited: yes`.

**Bài học quan trọng:** cả hai đường có thể chạy cùng filter logic. Vì vậy “MockMvc bỏ qua tất cả filters” là nhận định **sai**. Giới hạn nằm ở việc nó không kiểm tra **container/network integration** như HTTP connector, không phải mặc định bỏ hết mã filter của ứng dụng.

### 6.6. Test 1 — MockMvc trong tiến trình, không server

**File `src/test/java/com/example/mvclimits/MockMvcBoundaryTest.java`:**

```java
package com.example.mvclimits;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class MockMvcBoundaryTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getChecksMvcMappingJsonAndConfiguredFilter()
            throws Exception {

        mvc.perform(get("/api/greetings/Lan")
                .header("X-Request-Id", "mock-get")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(header().string(
                        "X-Filter-Visited", "yes"))
                .andExpect(jsonPath("$.message").value("Xin chào Lan"))
                .andExpect(jsonPath("$.requestId").value("mock-get"));
    }

    @Test
    void postChecksJsonRequestBodyAndCreatedStatus()
            throws Exception {

        mvc.perform(post("/api/greetings")
                .header("X-Request-Id", "mock-post")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Minh\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        "X-Filter-Visited", "yes"))
                .andExpect(jsonPath("$.message").value("Xin chào Minh"))
                .andExpect(jsonPath("$.requestId").value("mock-post"));
    }

    @Test
    void malformedJsonReturnsBadRequest()
            throws Exception {

        mvc.perform(post("/api/greetings")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{"))
                .andExpect(status().isBadRequest());
    }
}
```

**Kỳ vọng:** **3 JUnit tests pass**. Context có controller và filter thật, MockMvc dùng `MockHttpServletRequest/Response`. Test không cần/không khởi động server socket; không cần biết localhost port. Lỗi JSON hỏng thường được Spring MVC xử lý thành HTTP 400 qua `HttpMessageNotReadableException`.

Đừng suy luận từ việc status/header pass rằng TLS certificate, proxy headers hay connector đã được kiểm chứng. Những bước đó **không có mặt trong lời gọi `mvc.perform(...)`**.

### 6.7. Test 2 — real HTTP qua `java.net.http.HttpClient`

**File `src/test/java/com/example/mvclimits/RealHttpBoundaryTest.java`:**

```java
package com.example.mvclimits;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = BoundaryApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RealHttpBoundaryTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private final HttpClient client = HttpClient.newHttpClient();

    private URI endpoint(String path) {
        return URI.create(
                "http://127.0.0.1:" + port + path);
    }

    @Test
    void getUsesActualListeningPortAndRealHttpTransport()
            throws Exception {

        assertThat(port).isGreaterThan(0);

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/greetings/Lan"))
                .header("X-Request-Id", "http-get")
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers()
                .firstValue("X-Filter-Visited"))
                .contains("yes");

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("message").asText())
                .isEqualTo("Xin chào Lan");
        assertThat(json.path("requestId").asText())
                .isEqualTo("http-get");
    }

    @Test
    void postJsonOverHttpReturnsCreated()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/greetings"))
                .header("X-Request-Id", "http-post")
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"name\":\"Minh\"}",
                        StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(201);
        assertThat(response.headers()
                .firstValue("X-Filter-Visited"))
                .contains("yes");

        JsonNode json = mapper.readTree(response.body());
        assertThat(json.path("message").asText())
                .isEqualTo("Xin chào Minh");
        assertThat(json.path("requestId").asText())
                .isEqualTo("http-post");
    }

    @Test
    void malformedJsonIsRejectedOverHttp()
            throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                endpoint("/api/greetings"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{", StandardCharsets.UTF_8))
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(400);
    }
}
```

**Kỳ vọng:** **3 JUnit tests pass**. `@LocalServerPort` chỉ có giá trị hợp lệ khi web test thực sự khởi động server ở `RANDOM_PORT/DEFINED_PORT`; trong ví dụ là `RANDOM_PORT`. `HttpClient.send(...)` gửi HTTP request tới địa chỉ loopback và nhận response bytes qua socket.

Class này có **real server startup + real HTTP call**, nhưng vẫn chưa chứng minh TLS hay reverse proxy, vì URI dùng `http://127.0.0.1` và không có proxy. Server cụ thể được chọn dựa trên dependencies/cấu hình dự án. Không khẳng định một server implementation cố định nếu dự án có thể thay Tomcat bằng Jetty.

### 6.8. Chạy hai nhóm test

Linux/macOS, chọn build tool của dự án:

```bash
# Gradle Wrapper:
./gradlew test --tests "com.example.mvclimits.MockMvcBoundaryTest"
./gradlew test --tests "com.example.mvclimits.RealHttpBoundaryTest"

# Hoặc Maven Wrapper:
./mvnw -Dtest=MockMvcBoundaryTest test
./mvnw -Dtest=RealHttpBoundaryTest test
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.mvclimits.MockMvcBoundaryTest"
.\gradlew.bat test --tests "com.example.mvclimits.RealHttpBoundaryTest"

# Hoặc với Maven Wrapper:
.\mvnw.cmd "-Dtest=MockMvcBoundaryTest" test
.\mvnw.cmd "-Dtest=RealHttpBoundaryTest" test
```

**Tổng mẫu có 6 tests, chia đều thành 2 test classes.** Nếu chạy riêng từng class, mỗi lệnh có 3 tests; nếu chạy toàn bộ test suite, có 6 tests của ví dụ cùng với các test khác thuộc dự án. Code không chủ động in stdout; log startup và summary do Boot/build tool/JUnit tạo theo phiên bản.

Các snippets của build tool giả định dự án đã có wrapper và cấu hình plugin tương ứng. Không chạy cả Gradle lẫn Maven nếu project chỉ dùng một build system.

### 6.9. Hai cách chạy chứng minh điều gì, chưa chứng minh điều gì?

Cả hai test đều xác minh route, JSON body, response status và filter header. Các phần **MVC contract** trùng nhau được kiểm tra bằng cả hai cơ chế.

Khác biệt được chứng minh bằng **thiết lập và transport**:

- MockMvc test dùng `mockMvc.perform(...)` trên request/response mock, không có port.
- Real HTTP test inject `@LocalServerPort`, tạo URI có port và gọi JDK HttpClient qua socket.
- Chỉ nhóm HTTP thật đi qua network connector và request parsing ở server đang chạy.

Nếu cả hai xanh, có thể nói ứng dụng mẫu xử lý đúng các request đã thử **cả trong MockMvc và qua embedded HTTP server**. **Không được** nói “đã kiểm chứng mọi trường hợp container, browser, security, HTTP/2 hoặc production network”.

## 7. Các giới hạn transport mà MockMvc không thay thế được

### 7.1. Server startup, port và socket

MockMvc **không bắt lỗi kiểu**:

- HTTP server không thể bind vào cổng đã chiếm.
- Connector configuration có lỗi khởi tạo.
- Một client thật không thể kết nối hoặc bị connection refused.
- Server đóng kết nối bất ngờ hay timeout ở network layer.
- HTTP keep-alive và connection pooling không hoạt động theo cấu hình.

Các lỗi này yêu cầu ít nhất một bài test dùng real server và HTTP client. Tuy vậy, `RANDOM_PORT` thường **không bắt lỗi tranh chấp cổng 8080 production**, vì nó yêu cầu hệ điều hành chọn cổng rảnh. Nếu mục tiêu là cổng cố định hoặc networking production, cần môi trường phù hợp hơn.

### 7.2. HTTP parser và xử lý headers

MockMvc cho phép bạn tạo header, path, query string và content trực tiếp trên mock request. Nó không tự kiểm tra parser của embedded server khi nhận **HTTP request bytes thật**:

- Giới hạn kích thước request line/header.
- Header không hợp lệ hoặc cách chuẩn hóa của container.
- Truyền `Transfer-Encoding: chunked` hay `Content-Length` theo đường wire.
- Connection reuse, disconnect giữa chừng hoặc slow client.
- Một số hành vi của HTTP/1.1, HTTP/2, upgrade, streaming.

**Không có nghĩa MockMvc bỏ qua mọi kiểm tra URL/header.** Spring MVC vẫn parse/resolve mapping, query params và header values mà mock request biểu diễn. Nó chỉ bỏ qua tầng **HTTP connector/network parser** của server thực.

Ngay cả real HTTP test với JDK `HttpClient` cũng có giới hạn: client chuẩn có thể tự chuẩn hóa request và không cho tạo những header thô bất hợp lệ. Để test low-level protocol parser, có thể cần client/socket test chuyên biệt hoặc kiểm thử bảo mật giao thức.

### 7.3. TLS, HTTPS, chứng chỉ và proxy

MockMvc có thể mô phỏng thuộc tính request như scheme, secure flag hoặc forwarded headers cho controller/filter xem. Nhưng nó **không thực hiện TLS handshake hoặc certificate verification**.

Một test real HTTP qua URI `http://127.0.0.1:<port>` cũng **không** kiểm thử HTTPS. Muốn kiểm tra HTTPS thật phải cấu hình SSL keystore/truststore, dùng URI `https://...`, xác nhận certificates và client trust.

Với reverse proxy/load balancer/API gateway, kể cả một embedded server chạy real HTTP ở localhost vẫn không kiểm tra:

- TLS termination tại ingress.
- Chuyển tiếp `X-Forwarded-*` / `Forwarded` headers bởi proxy thật.
- Rewrite paths, host routing hoặc gateway authentication.
- WAF, sticky session, rate limiting, retry hoặc timeout ở proxy.
- DNS, cloud firewall, service mesh và network policy.

Để chứng minh các điều này cần test ở môi trường có thành phần hạ tầng tương ứng. MockMvc có thể kiểm thử **logic ứng dụng phản ứng với forwarded headers** khi cấu hình filter/handler đúng; nhưng không chứng minh proxy sẽ gửi đúng header trong production.

### 7.4. Compression và response streaming

MockMvc có thể kiểm tra content và response headers được code MVC tạo, nhưng không thay thế test response compression/chunking thực tế của container. Ví dụ nếu cấu hình gzip ở server connector, bạn nên gửi HTTP thật với `Accept-Encoding: gzip` và kiểm tra response bytes/headers theo client phù hợp.

Tương tự, nếu API trả file lớn, streaming body, Server-Sent Events hoặc multipart upload, MockMvc có thể xác minh một phần application logic; nhưng **backpressure, client disconnect, timeout, chunk boundaries và network throughput** cần các phép kiểm tra qua transport thực tế hoặc môi trường tích hợp.

Không dùng `content().string(...)` trên MockMvc rồi kết luận ứng dụng đáp ứng tốt tải 100 MB qua mạng.

## 8. Spring Security và Servlet filters: khác biệt nằm ở cấu hình

### 8.1. MockMvc có thể kiểm tra security

Một hiểu nhầm phổ biến: “MockMvc không chạy Spring Security”. Thực tế, với Spring Security Test tích hợp và filter chain được đăng ký, MockMvc có thể kiểm tra authentication, authorization, access denied/401/403 và CSRF rất hiệu quả.

Với `@AutoConfigureMockMvc` trong Spring Boot, `addFilters = true` là mặc định. Ví dụ:

```java
@AutoConfigureMockMvc(addFilters = true)
```

giữ các Servlet Filter thích hợp từ context. Nếu test có security starter, request chưa authenticated có thể bị chặn trước controller. Đó có thể là behavior đúng.

Trong unit/MVC-slice test, bạn có thể dùng `@WithMockUser` hoặc `SecurityMockMvcRequestPostProcessors.user(...)` / `csrf()` để cung cấp security context/test CSRF token mà không đi qua real login/OIDC protocol.

### 8.2. Test bằng mock authentication khác với real authentication handshake

`@WithMockUser` giúp xác minh **authorization rule của ứng dụng đối với một principal giả lập**. Nó không chứng minh:

- OAuth/OIDC redirect và code flow trong browser hoạt động.
- JWT được issuer thật ký đúng và client gửi token đúng.
- Session cookie flags/redirects/SSO proxy hoạt động xuyên hệ thống.
- TLS channel bảo vệ cookie/token trên network.
- Identity provider hoặc gateway đang hoạt động.

Những hợp đồng đó cần nhiều test ở mức integration/e2e phù hợp. Nhưng không có lý do bỏ mọi security MockMvc tests: chúng nhanh, hữu ích và có thể phát hiện lỗi access rule rất tốt.

### 8.3. Đừng dùng `addFilters=false` để “sửa” test 403

```java
@AutoConfigureMockMvc(addFilters = false)
```

có thể khiến request đi đến controller mà bỏ qua filter chain; test đó **không còn chứng minh security filter behavior**. Nếu endpoint thực sự được bảo vệ, hãy dùng authenticated user/token/CSRF đúng theo policy rồi assert cả trường hợp được phép và bị từ chối.

**Phân biệt:** loại filter khỏi `MockMvc` không nhất thiết xóa bean filter khỏi Spring context. Thao tác này khác với component-scan `excludeFilters` trên test slice.

## 9. Transaction và rollback: giới hạn dễ tạo lỗi nghiêm trọng

### 9.1. Test transaction và MockMvc đồng bộ

Spring TestContext có thể mở một **test-managed transaction** khi phương thức test được gắn `@Transactional` và có transaction manager phù hợp. Sau test, transaction đó thường rollback theo mặc định.

Với MockMvc và request xử lý **đồng bộ trong cùng thread** của test, code controller/service/repository có thể tham gia transaction đó nếu transaction propagation phù hợp. Điều này khiến data mutation trong quá trình `mockMvc.perform(...)` có thể được rollback khi test hoàn tất.

Tuy nhiên không nên khẳng định mọi mutation đều rollback:

- `@Async` hoặc xử lý sang thread khác không tự dùng transaction ThreadLocal của test.
- `REQUIRES_NEW` có thể mở transaction độc lập và commit.
- External queue, cache, file và HTTP side effects không được rollback theo database test transaction.
- Code không dùng cùng transaction manager cũng có thể không tham gia transaction test.

### 9.2. Real HTTP: client và server ở thread/transaction khác

Theo tài liệu Spring Boot về `@SpringBootTest(RANDOM_PORT/DEFINED_PORT)`, HTTP client và embedded server chạy trong **các thread khác nhau**, vì vậy transaction mở ở test thread **không tự rollback** transaction thực thi request phía server.

Ví dụ:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class OrderHttpTest {
    // Gửi POST HTTP thật tới server.
}
```

Đây là **snippet minh họa**, không phải test đầy đủ. `@Transactional` ở đây không thể được xem là cleanup tự động cho một POST mà server xử lý và commit trong transaction riêng. Sau test, dữ liệu có thể vẫn tồn tại.

**Hậu quả thực tế:** một bộ test chuyển từ MockMvc sang real HTTP và giữ nguyên `@Transactional` có thể bắt đầu làm bẩn database, gây thất bại phụ thuộc thứ tự test.

### 9.3. Chiến lược dữ liệu cho real HTTP tests

Chọn phương án phù hợp:

- Dùng database/container riêng cho test, seed/cleanup qua API hoặc truy vấn quản trị có kiểm soát.
- Cấp schema/database riêng cho từng suite/worker song song.
- Thiết kế test data id duy nhất; dọn dữ liệu trong `@AfterEach` hoặc fixture manager.
- Kiểm chứng không có background job/triggers làm cleanup sai thứ tự.
- Tránh truy cập production database và không dùng cùng bảng dữ liệu shared của developer.
- Không lạm dụng `@DirtiesContext` để “xóa database”: annotation này chủ yếu ảnh hưởng context cache, không dọn dữ liệu đã commit ở hệ ngoài.

Đặc biệt với asynchronous flows, hãy dùng cơ chế chờ có điều kiện/deterministic và timeout hợp lý thay vì ngủ cố định rồi đọc dữ liệu.

## 10. Async, streaming và request lifecycle

### 10.1. Spring MVC async trong MockMvc

Một controller có thể trả `Callable`, `DeferredResult` hoặc kiểu hỗ trợ async. Trong MockMvc, bạn thường kiểm tra hai pha:

```java
MvcResult pending = mockMvc
        .perform(get("/api/async"))
        .andExpect(request().asyncStarted())
        .andReturn();

mockMvc.perform(asyncDispatch(pending))
       .andExpect(status().isOk());
```

**Đây là snippet minh họa** cho endpoint async đã tồn tại; cần imports `MockMvcResultMatchers.request` và `MockMvcRequestBuilders.asyncDispatch`. Không copy vào controller đồng bộ của ví dụ phần 6 vì nó không khởi động async.

Trong real HTTP, client thường chờ response cuối cùng (hoặc đọc dữ liệu streaming theo chunk). Network-level timeout, disconnect hoặc client-side cancellation có thể bộc lộ lỗi khác với MockMvc async dispatch.

### 10.2. ThreadLocal, security context và request attributes

Dù MockMvc đồng bộ thường xử lý trên test thread, asynchronous logic có thể chuyển sang executor khác và cần propagation thích hợp cho security context, MDC logging, transaction hoặc request context. Nếu MockMvc test pass vì mọi thứ chạy cùng thread nhưng production dùng async, bạn có thể bỏ sót lỗi propagation.

Một real HTTP test kiểm tra thêm ranh giới client/server thread; tuy nhiên **nó không tự stress race conditions**. Với concurrency, cần test riêng có kiểm soát và chỉ kết luận về các điều kiện đã được kích hoạt.

### 10.3. Session và cookie

MockMvc có thể tạo `MockHttpSession`, đọc/ghi cookies và tiếp tục nhiều request bằng cách tái sử dụng session/cookie trong test. Điều này phù hợp để kiểm tra session handling **ở tầng ứng dụng**.

Nhưng nó không kiểm chứng đầy đủ:

- Cookie được browser lưu/gửi theo SameSite/Secure/Domain/Path rules trong network thực.
- Sticky sessions của load balancer.
- Session replication/distributed session behavior.
- Browser redirect chain, CORS preflight và credential behavior ngoài server.
- TLS-only cookie transmission.

Một real HTTP client cũng không tự cư xử như browser: JDK HttpClient có thể cần `CookieHandler` và redirect policy riêng nếu muốn mô phỏng cookie jar/redirect. Hãy kiểm tra client config và tạo browser-level test khi đó là hợp đồng.

## 11. Request URL, content encoding và forwarded headers

### 11.1. Path/query/encoding trong MockMvc

Bạn có thể viết:

```java
mockMvc.perform(get("/api/search")
        .param("q", "cà phê")
        .header("X-Request-Id", "test-123"))
        .andExpect(status().isOk());
```

**Snippet này giả định endpoint tồn tại**, không phải ví dụ runnable độc lập. `param(...)` thêm logical request parameter vào mock Servlet request; nó không tạo rồi gửi một URI đã percent-encode qua TCP.

Khi lỗi xảy ra chỉ trên đường dẫn có ký tự Unicode, dấu cách, dấu `%`, dấu `/` được encode hoặc query string rất dài, cần thêm real HTTP tests với URI được xây dựng/encode theo contract. Embedded container có thể xử lý encoded slash, URI normalization và limits khác với mock request.

### 11.2. Multipart upload

MockMvc có `multipart(...)` builder để tạo `MockMultipartFile` và xác minh controller nhận multipart request. Nó không gửi MIME multipart body thực qua HTTP socket.

Nếu bug nằm ở client multipart boundary, upload size limit, container multipart parser, streaming file lớn hoặc proxy body limit, cần thử real HTTP client/server; nếu nằm ở controller validation và business service gọi từ multipart handler, MockMvc vẫn rất hữu ích.

### 11.3. Encoding và charsets

MockMvc kiểm tra Spring MVC converters với các mock request/response có cấu hình encoding. Real HTTP còn đi qua việc client encode URI/headers/body thành bytes, server decode và trả response bytes. Do vậy, để xác minh vấn đề charset thực sự xảy ra qua đường wire, dùng HTTP client và assert dữ liệu Unicode sau decode.

Ví dụ runnable phần 6 cố ý trả chuỗi tiếng Việt **“Xin chào Lan”** ở cả hai đường. Khi cả hai test pass, ta biết JSON converter và đường HTTP test đã xử lý đúng chuỗi **trong những request cụ thể đó**. Không mặc định mọi encoding/locale/Unicode normalization đều đúng.

## 12. Full context không đồng nghĩa real HTTP

Một bẫy rất phổ biến:

```java
@SpringBootTest
@AutoConfigureMockMvc
class FullContextTest {
    @Autowired MockMvc mvc;
}
```

Nó có thể chứa **mọi bean thật** của app nhưng mặc định `@SpringBootTest` dùng `WebEnvironment.MOCK` và không có server socket. Ngược lại:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpContextTest {
}
```

sẽ mở embedded server. Nhưng nếu bạn dùng Mockito để thay `PaymentGateway` bằng mock, gọi HTTP thật cũng không tự kiểm tra payment provider production.

Có **hai trục độc lập** cần ghi trong test documentation:

1. **Độ rộng Spring context:** controller-only slice, full context, hoặc full context với một số dependencies bị override.
2. **Đường request:** MockMvc in-process hoặc real HTTP qua server/port.

Một test có thể full context + MockMvc; full context + HTTP; MVC slice + MockMvc. Tránh chỉ gắn nhãn “integration test” rồi suy ra mức độ bao phủ.

### 12.1. Các ví dụ kết hợp không tương đương

| Kết hợp | Điều bạn có thể kết luận |
|---|---|
| `@WebMvcTest + MockMvc` | MVC mapping/converters/validation với bean/filters thuộc slice |
| `@SpringBootTest(MOCK) + MockMvc` | MVC pipeline với full test context, không socket |
| `@SpringBootTest(RANDOM_PORT) + HttpClient` | Full test context, embedded servlet container và HTTP socket |
| `@SpringBootTest(RANDOM_PORT) + MockMvc` | Nếu cũng auto-configure MockMvc, `MockMvc.perform` vẫn là in-process request |
| Browser → staging ingress → service | Browser/network/ingress thực tế theo staging config, không tự giống 100% production |

## 13. Chọn test theo rủi ro thực tế

### 13.1. Khi MockMvc đủ mạnh

MockMvc là lựa chọn tốt khi cần kiểm tra:

- Mapping và method/path của controller.
- JSON serialization/deserialization ở tầng Spring MVC.
- `@Valid`, argument conversion, message conversion.
- ControllerAdvice, exception-to-status mapping.
- Những Servlet Filter và Spring Security rules được cấu hình trong MockMvc.
- Controller gọi đúng service/repository trong full test context.
- Hành vi lỗi 400/404/409 theo API contract.
- Một số request/response session flow và async logic ở tầng framework.

Đặc biệt phù hợp cho nhiều test nhanh trong CI và làm vòng phản hồi hàng ngày.

### 13.2. Khi bắt buộc thêm real HTTP

Ưu tiên ít nhất một nhóm `RANDOM_PORT`/HTTP tests cho các rủi ro:

- Ứng dụng có mở được embedded server đúng cấu hình không?
- Client thật có gửi request đúng URI/method/header/body không?
- HTTP response có đúng status, content encoding, cookies/redirects theo client không?
- Server connector, compression, timeout, multipart size limits hoặc HTTP protocol behavior có đúng yêu cầu không?
- Cần chứng minh giao dịch không bị hiểu nhầm qua client/server thread.
- Các lỗi chỉ tái hiện qua socket, connection pool hoặc request body streaming.
- Một thư viện HTTP client thực được dùng trong hệ thống có cấu hình proxy/timeout riêng.

Chọn số ít test đại diện nhưng có giá trị về boundary; không sao chép toàn bộ hàng trăm case MockMvc thành hàng trăm tests socket nếu không tăng khả năng bắt lỗi.

### 13.3. Khi real HTTP localhost vẫn chưa đủ

Cần thêm staging/e2e/contract tests có hạ tầng tương ứng cho:

- API gateway, ingress và path rewriting.
- HTTPS certificates, mTLS, proxy authentication.
- Browser security/cross-origin behaviors.
- Load balancer, horizontal scaling, sticky sessions.
- Container images, Kubernetes readiness/liveness, cloud secrets.
- DNS/network policy/firewall hoặc môi trường production-specific.

Mục tiêu là **kim tự tháp kiểm thử có tầng rõ ràng**, không tuyên bố một loại test thay thế tất cả.

## 14. Version: Spring Boot 3.x, 4.x và lựa chọn client

### 14.1. Import trong Spring Boot 3.x

Ví dụ runnable sử dụng:

```java
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.servlet.MockMvc;
```

Với Spring Boot 3.x, servlet MVC application thường dùng `spring-boot-starter-web`; test dùng `spring-boot-starter-test`. Java 17+ phù hợp. Nếu ứng dụng có Spring Security, hãy thêm test security support và cung cấp auth/CSRF phù hợp, vì code runnable ở phần 6 **không có Security dependency**.

### 14.2. Sang Spring Boot 4.x cần kiểm tra package và starter

Spring Boot 4 tổ chức lại MVC testing auto-configuration, ví dụ:

```java
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
```

Web MVC production/testing starters thuộc kiến trúc module mới, ví dụ `spring-boot-starter-webmvc` và `spring-boot-starter-webmvc-test`; kiểm tra version/BOM và docs của nhánh đang dùng. Không copy nguyên import Boot 3 vào Boot 4 rồi nghĩ annotation đã bị xóa.

**Mốc ý nghĩa vẫn giữ:** MockMvc dùng mock Servlet pipeline không socket; `RANDOM_PORT` chạy embedded server HTTP thật. Nhưng classpath, module, JUnit/Jackson phiên bản và imports có thể thay đổi, nên ví dụ phần 6 chỉ cam kết mục tiêu **Spring Boot 3.x**.

### 14.3. WebFlux không phải Servlet MVC

Nếu ứng dụng chỉ dùng **Spring WebFlux (reactive stack)**, `MockMvc` không phải công cụ tương đương để test reactive handlers. Với WebFlux, dùng `WebTestClient` bind tới application context hoặc live server phù hợp.

Spring Framework cũng hỗ trợ `WebTestClient` gắn vào MockMvc cho MVC, nhưng điều đó **không tự biến thành HTTP thật**; điều quan trọng là client được **bindToMockMvc** hay **bindToServer**.

**Không đánh giá độ “thật” chỉ dựa trên tên client.** `WebTestClient` có thể dùng cho mô phỏng hoặc cho live HTTP tùy cách bind.

## 15. Lỗi thường gặp và cách truy nguyên

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
|---|---|---|
| `Connection refused` khi cố gọi localhost trong test MOCK | `@SpringBootTest(MOCK)` không mở server socket | Dùng MockMvc hoặc đổi sang `RANDOM_PORT` và real client |
| `@LocalServerPort` không có giá trị | Test không khởi động embedded server hoặc import/version sai | Dùng `RANDOM_PORT`, kiểm tra config và port |
| MockMvc test pass, real HTTP 404 | Context path, encoding, request URI, servlet container config hoặc test setup khác | So sánh raw HTTP request, mappings và port/context path |
| MockMvc test pass, HTTP timeout | Network connector/client timeout, server thread/long I/O | Kiểm tra client timeout, server logs và blocking operations |
| HTTP 401/403 thay vì 200/201 | Security filter chain, auth hoặc CSRF khác | Cung cấp auth/CSRF đúng policy, không tùy tiện tắt filters |
| MockMvc 200 nhưng HTTP 413 | Body/header size limits của server/proxy | Dùng real HTTP test với payload size có kiểm soát |
| HTTPS client báo certificate error | Truststore/SNI/certificate/TLS setup chưa đúng | Test HTTPS thật, không dùng MockMvc để chứng minh TLS |
| Test `@Transactional` qua real HTTP vẫn để lại data | Test/client và server thread khác transaction | Cleanup database/fixture riêng, không tin rollback test thread |
| Response JSON khác khi có charset | Encoding bytes/headers/client decoding khác | So sánh content-type charset và response body raw/decode |
| MockMvc filter header thiếu | Filter chưa đăng ký, `addFilters=false`, standaloneSetup khác Boot setup | Kiểm tra filter chain/config; không mặc định filter luôn chạy |
| Đã dùng `RANDOM_PORT` nhưng vẫn gọi `mockMvc.perform` | MockMvc vẫn in-process | Gọi HTTP client tới `@LocalServerPort` |
| Test quá chậm sau khi đổi sang HTTP thật | Server startup, DB migrations, context cache misses | Tách ít boundary tests, giữ nhiều MVC/unit tests |
| IDE xanh, CI đỏ | JDK, port, dependencies, proxy, credentials, race, test selection khác | Chạy wrapper, so logs/test reports và môi trường |
| WebFlux controller không chạy với MockMvc | Khác web stack | Dùng WebTestClient reactive configuration |
| HTTP 400 khi JSON sai | Message converter đã từ chối body trước controller | Kiểm tra request bytes, content type, resolved exception |
| Real HTTP test pass nhưng staging fail | Proxy/TLS/ingress/environment chưa có trong localhost test | Thêm environment-level test tại đúng boundary |

### 15.1. Debug theo tầng, tránh sửa sai chỗ

1. Xác nhận test được JUnit/Gradle/Maven **thực sự thực thi**, không bị skip.
2. Xác nhận application context khởi động được. Nếu `Failed to load ApplicationContext`, đọc root cause bean/config trước.
3. Xác định **đường request**: `MockMvc.perform` hay HTTP client tới host/port?
4. Nếu dùng HTTP thật, xác minh `@LocalServerPort`, URI, context path, connector và client timeout.
5. Kiểm tra Servlet Filters/Spring Security trước MVC mapping.
6. Kiểm tra route, path/query encoding, JSON converters và validation.
7. Kiểm tra service/repository fixture, transaction/thread và cleanup.
8. Kiểm tra response status/header/body ở đúng boundary.
9. Nếu chỉ production/staging lỗi, kiểm tra TLS, proxy, ingress, distributed state và network policies.

Mỗi lỗi cần được chẩn đoán ở tầng phát sinh. Một lỗi TCP connection refused không thể chữa bằng cách đổi `jsonPath(...)`; một lỗi `NoSuchBeanDefinitionException` cũng không phải do thiếu HTTP real client.

## 16. Bài tập áp dụng và đáp án

### Bài A — Một test có Spring context đầy đủ, nhưng chưa có HTTP thật

Bạn thấy:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ProductsTest {
    @Autowired MockMvc mvc;
}
```

Hỏi: lớp test có khởi động HTTP server mặc định không? Có chạy service thật không?

**Đáp án:** mặc định không mở server socket vì `@SpringBootTest` có `webEnvironment=MOCK`. Nhưng service vẫn có thể là bean thật trong application context. Hai thuộc tính độc lập: **độ rộng context** và **đường request**.

### Bài B — Muốn kiểm tra port ngẫu nhiên và response thực

Cấu hình cần thay đổi thế nào?

**Đáp án:** dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)`, lấy `@LocalServerPort`, gửi request bằng HttpClient tới `http://127.0.0.1:<port>` và assert status/header/body. Đừng chỉ thêm `@LocalServerPort` vào test MOCK.

### Bài C — Filter chưa chạy trong MockMvc

Một test dùng `@AutoConfigureMockMvc(addFilters = false)` và mong chứng minh audit filter thêm header. Vì sao assertion fail?

**Đáp án:** bạn chủ động bỏ đăng ký filters từ context vào MockMvc. Bật filter registration và đảm bảo bean/filter chain đúng; có thể viết real HTTP test bổ sung để kiểm tra container registration.

### Bài D — @Transactional không dọn dữ liệu

Bài test real HTTP POST vào repository, test method được `@Transactional` nhưng bản ghi vẫn ở database. Có phải Spring TestContext rollback bị lỗi?

**Đáp án:** không nhất thiết. Request server xử lý trong thread/transaction riêng; test-managed transaction của client thread không tự rollback giao dịch server. Dùng fixture/cleanup/schema test hợp lệ.

### Bài E — Lỗi chỉ xảy ra với HTTPS qua reverse proxy

Bạn nên ưu tiên MockMvc, localhost HTTP hay staging gateway?

**Đáp án:** MockMvc có thể kiểm tra controller/filter logic cho forwarded headers; localhost HTTP kiểm tra embedded connector nhưng **không chứng minh TLS termination và proxy behavior**. Muốn kiểm tra vấn đề HTTPS/proxy cần môi trường và client đi qua gateway/TLS thật.

### Bài F — WebTestClient có luôn gửi HTTP thật?

**Đáp án:** không. WebTestClient có chế độ bind tới mock application/MockMvc và chế độ bind tới live server. Phải đọc cách client được cấu hình: **bindToServer** với URI host/port thực mới là HTTP network path.

### Checklist trước khi kết luận một web test đạt

- [ ] Nêu rõ context là MVC slice hay full Spring Boot context.
- [ ] Nêu rõ request đi qua MockMvc in-process hay HTTP client/server thật.
- [ ] Với MockMvc, biết filters/security có được đăng ký không.
- [ ] Với HTTP thật, biết cổng, base URL, context path và client timeout.
- [ ] Không dùng mock HTTP để tuyên bố test TCP/TLS/HTTP2/container connector.
- [ ] Không dùng localhost real HTTP để tuyên bố đã test proxy/load balancer/internet.
- [ ] Status, headers, JSON fields và business contract có assertions cụ thể.
- [ ] Negative cases được kiểm tra: malformed body, 4xx, authentication khi cần.
- [ ] Test transactions/cleanup đúng theo mô hình thread và connection.
- [ ] Async/streaming/multipart được test ở tầng thích hợp.
- [ ] Spring Security/CSRF không bị tắt ngoài ý định.
- [ ] Dự án Servlet MVC hay WebFlux được xác định đúng.
- [ ] Dependency/import Boot 3.x hay Boot 4.x nhất quán.
- [ ] Không gọi production endpoints hoặc dùng production credentials trong test.
- [ ] Test được chạy với JDK/build wrapper và báo cáo đúng số lượng trên CI.

## 17. Tóm tắt

**MockMvc kiểm chứng Spring MVC request handling bằng mock Servlet API — không kiểm chứng một kết nối HTTP qua server thật.** Nó vẫn có thể chạy controller, service, repository và filter thật theo cấu hình, vì vậy rất mạnh cho API contract ở mức MVC.

**Real HTTP với `@SpringBootTest(RANDOM_PORT)`** bổ sung embedded server, port, socket, HTTP transport và ranh giới thread giữa client/server; đổi lại có thêm chi phí startup, xử lý dữ liệu/transaction phức tạp hơn và yêu cầu quản lý fixture chặt chẽ. Ngay cả real HTTP localhost vẫn không kiểm chứng proxy, TLS, gateway hoặc cloud infrastructure nếu chưa đưa chúng vào môi trường.

Lựa chọn đúng nhất là **kết hợp có chủ đích**: nhiều test unit/MVC slice/MockMvc cho phản hồi nhanh, một tập real HTTP integration tests cho các boundary quan trọng, và những environment-level tests cần thiết cho hạ tầng triển khai.

## Tài liệu tham khảo chính thức

- [Spring Framework — MockMvc Overview](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html): MockMvc gọi DispatcherServlet bằng mock Servlet API, không có running server.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): hướng kiểm tra Spring MVC, setup và MockMvcTester/WebTestClient bridge.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, transaction caveat và TestRestTemplate/WebTestClient.
- [Spring Boot 3.5 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/AutoConfigureMockMvc.html): `addFilters` và cấu hình MockMvc.
- [Spring Boot 4 — AutoConfigureMockMvc Javadoc](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webmvc/test/autoconfigure/AutoConfigureMockMvc.html): package mới của Spring Boot 4.
- [Spring Framework — MockMvc Async Requests](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html): kiểm tra asyncStarted và asyncDispatch.
- [Spring Security — MockMvc Test Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): tích hợp Spring Security vào MockMvc.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client HTTP dùng trong ví dụ chạy qua socket.
