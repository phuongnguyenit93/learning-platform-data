# Xây dựng bộ kiểm thử tái hiện các lỗi web runtime thường gặp trong Spring Boot

## 1. Bối cảnh, mục tiêu và kết quả thực hành

Một endpoint Spring Boot có thể trả **404, 400, 401, 403, 405, 406, 409, 415, 429, 500, 503, 504** hoặc không trả response đúng thời hạn. Các mã lỗi nhìn giống nhau trong log ngắn, nhưng **nguồn gốc** rất khác: Servlet context path, handler mapping, HTTP method, JSON decoder, Bean Validation, Spring Security, domain service, reverse proxy, connection pool hay một upstream đang chậm. Bộ kiểm thử tốt phải **tái hiện được lỗi theo điều kiện xác định**, sau đó kiểm regression để thay đổi code không làm lỗi quay lại.

Bài thuộc nhóm **Thực hành tổng hợp**, module **Spring Boot - web-runtime**, với yêu cầu trực tiếp: **Xây dựng bộ kiểm thử tái hiện các lỗi web runtime thường gặp**. Thay vì một danh sách câu lệnh rời rạc, bài cung cấp **một project Maven chạy được bằng Java 17+**, Spring Boot 3.5.16, Spring MVC/Tomcat, Bean Validation, Spring Security, Actuator, JUnit 5, MockMvc và JDK `HttpClient`.

Bộ bài thực hành chứa:

- **21 HTTP integration tests** bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` + Java 17 `HttpClient`, đi qua embedded Tomcat thật.
- **3 controller slice tests** bằng `@WebMvcTest` + `MockMvc` để kiểm mapping/validation nhanh, với giới hạn phạm vi được giải thích minh bạch.
- Một ứng dụng có context path `/lab`, API đọc/tạo widget, validation, cache ETag, lỗi domain 404, lỗi ngoài dự kiến 500, basic authentication và phân quyền 401/403.
- Ma trận chẩn đoán, bài tập **red → green → regression**, gợi ý mở rộng cho upload, CORS, proxy, streaming, WebFlux, timeouts và overload.
- Các lệnh chạy bằng Maven, `curl`, cách đọc kết quả, cách thiết kế fixtures và CI để không thử sai vào production.

Mục tiêu sau bài học:

1. Phân biệt test **MockMvc** với real HTTP qua socket, không lấy green slice test làm bằng chứng context-path/connector/proxy hoạt động đúng.
2. Tạo các request lỗi có chủ đích rồi assert **HTTP status, headers, body và side effects** ở phạm vi phù hợp.
3. Viết test 400 cho JSON hỏng và Bean Validation, 405 cho method, 406 cho Accept, 415 cho Content-Type, 404 cho mapping/domain.
4. Kiểm 401 chưa xác thực, 403 không đủ quyền, hiểu CSRF có thể trả 403 trước controller.
5. Kiểm một 500 được phát từ server, phân biệt lỗi bất ngờ với một lỗi domain có contract riêng.
6. Xác nhận 201 + Location + đọc lại resource; kiểm ETag và conditional GET 304 không tải lại body.
7. Tạo test ổn định: random port, dữ liệu giả, không phụ thuộc thứ tự, không ngủ chờ tùy tiện, không gọi hạ tầng ngoài chưa được phép.
8. Biết chọn kiểm thử riêng khi lỗi chỉ xảy ra với WebFlux, SSE/NDJSON, reverse proxy, TLS, tải cao hoặc database thật.

**Nguyên tắc:** mỗi test có một *giả thuyết lỗi*, *điều kiện tái hiện*, *tín hiệu đo/được assert* và *giới hạn kết luận*. Không phải mọi lỗi web runtime đều do controller Java.

## 2. Bản đồ nguồn lỗi và cấp kiểm thử

```text
Browser / Mobile / curl
       |
       v
DNS, TLS, load balancer, ingress / reverse proxy
       |-- sai Host, path rewrite, timeout, header limits
       v
Embedded Tomcat + Servlet context /lab
       |-- thiếu /lab => 404 trước controller
       v
Spring Security filter chain
       |-- chưa auth => 401; không đủ role/CSRF => 403
       v
DispatcherServlet / HandlerMapping
       |-- path 404; method 405; produces 406; consumes 415
       v
HTTP converters / Bean Validation
       |-- JSON malformed / DTO invalid => 400
       v
Controller / service / domain
       |-- known resource => 200; created => 201
       |-- missing business object => explicit 404
       |-- unexpected failure => 500
       v
Serialization / cache / response completion
       |-- ETag + If-None-Match => 304
       |-- streamed response / client disconnect / proxy buffering
```

| Cấp kiểm thử | Công cụ | Kiểm được | Chưa được chứng minh |
| --- | --- | --- | --- |
| Unit | JUnit/Mockito, `StepVerifier` nếu Reactive | Điều kiện, nhánh lỗi, domain state, publisher signals | HTTP mapping, Jackson, filter chain |
| Web slice | `@WebMvcTest` + MockMvc, hoặc `@WebFluxTest` + WebTestClient | Controller mapping, validation, codecs, advice trong slice | Tomcat/Netty socket, public proxy, service/DB bị mock |
| Full app mock | `@SpringBootTest` + `@AutoConfigureMockMvc` | Wiring toàn app, filter/handler chain mock | Socket/TLS/error page ở container thật |
| Real HTTP | `@SpringBootTest(RANDOM_PORT)` + JDK HttpClient/WebTestClient | Embedded server, context path, HTTP response, app wiring | CDN, ingress bên ngoài, remote API/DB nếu không kết nối |
| Staging/E2E | HTTP qua gateway + test data/credentials | URL public, TLS, proxy/auth/upstream integration | Capacity/sự cố ngẫu nhiên nếu không có test tải và chaos riêng |

Theo tài liệu Spring Boot 3.5, `@SpringBootTest` mặc định dùng `webEnvironment=MOCK`, **không khởi động embedded server**; `RANDOM_PORT` khởi động server thật. `@WebMvcTest` thường nhanh hơn nhưng là **slice**, và nếu Spring Security có mặt, phải xác định filters nào đang được áp dụng chứ không chỉ nhìn assertion 200.

**Mục tiêu test này là Servlet MVC.** Với WebFlux native Netty, thay bằng `@WebFluxTest`, `WebTestClient` và Reactive Streams-specific tests. Không thêm `spring-boot-starter-webflux` vào POM MVC rồi gọi nó là bài test WebFlux: khi cả MVC và WebFlux cùng trên classpath, Spring Boot thường ưu tiên MVC.

## 3. Chọn lỗi có thể tái hiện một cách xác định

Bộ lab cố tình tạo cả “đường đúng” và “đường sai” trên **cùng hệ thống**:

| Trường hợp | Request giả định | Kỳ vọng | Nguồn/tầng |
| --- | --- | --- | --- |
| OK health | `GET /lab/actuator/health` | 200 | Actuator cùng context path |
| URL đúng | `GET /lab/api/ping` | 200 JSON | Handler mapping |
| Thiếu context | `GET /api/ping` | 404 | Tomcat context path |
| Sai route | `GET /lab/api/pign` | 404 | Spring handler/resource lookup |
| Thêm slash | `GET /lab/api/ping/` | 404 theo cấu hình mặc định | Path matching |
| Sai verb | `POST /lab/api/ping` | 405 | Method condition |
| Accept sai | `GET /lab/api/ping`, `Accept: application/xml` | 406 | Produces/media negotiation |
| Body Content-Type sai | `POST /lab/api/widgets`, `text/plain` | 415 | Consumes/media negotiation |
| JSON malformed | POST JSON không parse được | 400 | HttpMessageConverter |
| DTO invalid | POST name trống/quantity 0 | 400 | Jakarta Bean Validation |
| Thiếu query | `GET /lab/api/page` | 400 | Required parameter |
| Query sai type | `GET /lab/api/page?size=abc` | 400 | Type conversion |
| Tài nguyên có thật | `GET /lab/api/widgets/w1` | 200 | Domain service |
| Tài nguyên không tồn tại | `GET /lab/api/widgets/unknown` | 404 có code riêng | Domain + advice |
| Tạo tài nguyên | POST widget hợp lệ | 201 + Location; GET lại 200 | Controller + in-memory store |
| Lỗi chưa xử lý | `GET /lab/api/fail` | 500 | Unexpected exception |
| Chưa xác thực | `GET /lab/api/secure/member` | 401 | Spring Security |
| Đăng nhập đúng | GET member với Basic demo user | 200 | Authentication |
| Không đủ quyền | GET admin với Basic demo user | 403 | Authorization |
| Conditional cache | GET snapshot, sau đó `If-None-Match` | 200 rồi 304 | ETag semantics |
| Actuator mappings | `GET /lab/actuator/mappings` | 200 local, liệt kê route | Diagnostic mapping |

**Lưu ý:** con số 401/403/405/406/415 trên chỉ đáng tin khi test environment cấu hình như source code. Security, proxy, WAF, content negotiation và error handlers tùy chỉnh có thể thay đổi response. Bộ test chủ đích cố định các yếu tố ấy; không khẳng định mọi Spring Boot app phải trả đúng các status đó cho mọi request.

## 4. Dựng dự án MVC/Tomcat kiểm thử độc lập

### 4.1. Cấu trúc thư mục

```text
runtime-error-lab/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/runtimelab/
   │  │  ├─ RuntimeErrorLabApplication.java
   │  │  ├─ Widget.java
   │  │  ├─ CreateWidgetRequest.java
   │  │  ├─ WidgetService.java
   │  │  ├─ InMemoryWidgetService.java
   │  │  ├─ UnknownWidgetException.java
   │  │  ├─ ApiErrorHandler.java
   │  │  ├─ SecurityConfiguration.java
   │  │  └─ RuntimeApiController.java
   │  └─ resources/
   │     └─ application.properties
   └─ test/
      └─ java/com/example/runtimelab/
         ├─ RuntimeHttpIntegrationTest.java
         └─ RuntimeWebSliceTest.java
```

Tất cả public Java top-level types nằm trong file đúng tên và package `com.example.runtimelab`. Application root class ở package cha để Spring Boot component-scan tìm được controller/service/advice/security configuration.

### 4.2. Maven POM hợp lệ — Spring Boot 3.5.16 / Java 17

**`pom.xml`**

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>runtime-error-lab</artifactId>
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
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

- `starter-web` dùng **Spring MVC + embedded Tomcat**, có JSON/Jackson.
- `starter-validation` bật Jakarta Bean Validation cho request DTO.
- `starter-security` bật Spring Security Servlet filter chain và HTTP Basic lab.
- `starter-actuator` cung cấp health/mappings, chỉ expose trong local lab.
- `starter-test` cung cấp JUnit Jupiter, MockMvc, AssertJ, Mockito.
- `spring-security-test` sẵn cho mở rộng test role/CSRF bằng MockMvc; bộ real HTTP dùng HTTP Basic header của JDK.
- Không cần database/Redis/third-party API. Store in-memory được dùng để test HTTP state bằng fixture đơn giản.

### 4.3. Runtime config chỉ dành cho local lab

**`src/main/resources/application.properties`**

```properties
spring.application.name=runtime-error-lab
server.port=8080

# Ngăn demo lộ ra mạng ngoài. Trong container, phải cấu hình
# bind address theo topology thay vì sao chép 127.0.0.1 vô thức.
server.address=127.0.0.1
server.servlet.context-path=/lab

# Chỉ để chẩn đoán local; không public mappings ở production.
management.endpoints.web.exposure.include=health,mappings

# Ẩn message/stack trace của lỗi ứng dụng trong HTTP response mặc định.
server.error.include-message=never
server.error.include-stacktrace=never
```

`server.servlet.context-path=/lab` làm HTTP client phải gửi URL `/lab/api/...`. Cấu hình Spring MVC `@RequestMapping("/api")` **không** được thêm `/lab` lần thứ hai. Nếu sau này thêm `spring.mvc.servlet.path` khác `/`, phải xét tương thích của matching strategy với `PathPatternParser` theo phiên bản Boot.

### 4.4. Main application

**`src/main/java/com/example/runtimelab/RuntimeErrorLabApplication.java`**

```java
package com.example.runtimelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RuntimeErrorLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RuntimeErrorLabApplication.class, args);
    }
}
```

### 4.5. Domain DTO và validation

**`src/main/java/com/example/runtimelab/Widget.java`**

```java
package com.example.runtimelab;

public record Widget(String id, String name, int quantity) {}
```

**`src/main/java/com/example/runtimelab/CreateWidgetRequest.java`**

```java
package com.example.runtimelab;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateWidgetRequest(
        @NotBlank String name,
        @Min(1) int quantity
) {}
```

Java 17 record làm DTO bất biến, Jackson đọc/ghi JSON. `@NotBlank` không chấp nhận `null`, empty, toàn whitespace; `@Min(1)` không chấp nhận zero/âm. Input validation xảy ra ở web boundary, không thay thế domain authorization hoặc DB constraints production.

### 4.6. Service contract

**`src/main/java/com/example/runtimelab/WidgetService.java`**

```java
package com.example.runtimelab;

public interface WidgetService {
    Widget find(String id);
    Widget create(CreateWidgetRequest input);
}
```

### 4.7. Domain not-found exception

**`src/main/java/com/example/runtimelab/UnknownWidgetException.java`**

```java
package com.example.runtimelab;

public class UnknownWidgetException extends RuntimeException {
    public UnknownWidgetException(String id) {
        super("Widget not found");
    }
}
```

Thông điệp lỗi không chứa dữ liệu nhạy cảm hoặc raw upstream exception. Lỗi domain này sẽ được `@RestControllerAdvice` ánh xạ sang 404 JSON có `code` cố định để client biết phải xử lý ra sao.

### 4.8. In-memory service thực thi được

**`src/main/java/com/example/runtimelab/InMemoryWidgetService.java`**

```java
package com.example.runtimelab;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class InMemoryWidgetService implements WidgetService {

    private final Map<String, Widget> store =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(100);

    public InMemoryWidgetService() {
        store.put("w1", new Widget("w1", "Book", 10));
    }

    @Override
    public Widget find(String id) {
        Widget widget = store.get(id);
        if (widget == null) {
            throw new UnknownWidgetException(id);
        }
        return widget;
    }

    @Override
    public Widget create(CreateWidgetRequest input) {
        String id = "w" + sequence.incrementAndGet();
        Widget widget =
            new Widget(id, input.name(), input.quantity());
        store.put(id, widget);
        return widget;
    }
}
```

`ConcurrentHashMap` và `AtomicLong` đủ cho lab có request đồng thời; chúng **không** là database transaction, constraint, persistent storage hay authorization layer. Test chỉ xác minh HTTP behavior của **app này**, không suy DB ngoài đã ghi đúng.

Do Spring Test có cache ApplicationContext, ID mới có thể thay đổi nếu tests chia sẻ context/khởi động lại. Tests **không assert ID luôn w101**. Chúng chỉ kiểm ID thực nhận và GET lại đúng resource.

### 4.9. Error advice cho domain 404

**`src/main/java/com/example/runtimelab/ApiErrorHandler.java`**

```java
package com.example.runtimelab;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(UnknownWidgetException.class)
    public ResponseEntity<Map<String, String>> unknownWidget(
            UnknownWidgetException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Map.of(
                "code", "WIDGET_NOT_FOUND",
                "message", "Widget not found"
            ));
    }
}
```

Quan trọng: `/lab/api/widgtes` **sai đường dẫn** cũng có thể trả HTTP 404, nhưng lỗi này không đi qua `UnknownWidgetException`; không thể mặc nhiên assert `code=WIDGET_NOT_FOUND` cho mọi 404. Nên tách hai test để phân biệt **routing 404** và **domain 404**.

### 4.10. Spring Security filter chain có chủ đích

**`src/main/java/com/example/runtimelab/SecurityConfiguration.java`**

```java
package com.example.runtimelab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            // CHỈ CHO LAB: API POST không có cookie session, test 405/400/415.
            // Không bỏ CSRF đại trà trong production khi có cookie-based auth.
            .csrf(csrf -> csrf.ignoringRequestMatchers(
                "/api/widgets", "/api/ping"))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/secure/admin").hasRole("ADMIN")
                .requestMatchers("/api/secure/**").authenticated()
                .anyRequest().permitAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password("{noop}lab-only-password")
                .roles("USER")
                .build()
        );
    }
}
```

**Chỉ dùng ở loopback/local training.** `{noop}` là mật khẩu không hash và account có giá trị công khai trong tutorial, **không bao giờ deploy cấu hình này ra production**. App real phải dùng lưu trữ user an toàn, password encoder thích hợp, HTTPS và security policy tương ứng. Ignoring CSRF tại hai API paths chỉ để lab có thể tái hiện HTTP 405/415/400 mà không bị CSRF trả 403 trước; production phải đánh giá cookie/sessions, token authentication, cross-origin requests và authorization.

Matcher `/api/secure/**` được xét **trong application context**; không thêm `/lab` vào matcher chỉ vì Servlet context path là `/lab`. Nếu security filter chạy trước controller, 401/403 phản ánh **security**, không có nghĩa handler mapping mất.

Khi client chưa có Basic credentials, `/api/secure/member` thường trả 401 với `WWW-Authenticate`. Khi gửi đúng user role USER vào `/api/secure/admin`, status 403 cho thấy user được xác thực nhưng thiếu role ADMIN.

### 4.11. Controller với path/method/media/validation/cache/error

**`src/main/java/com/example/runtimelab/RuntimeApiController.java`**

```java
package com.example.runtimelab;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import jakarta.validation.Valid;
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
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api")
public class RuntimeApiController {

    private final WidgetService widgets;

    public RuntimeApiController(WidgetService widgets) {
        this.widgets = widgets;
    }

    @GetMapping(
        path = "/ping",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @GetMapping(
        path = "/widgets/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Widget find(@PathVariable("id") String id) {
        return widgets.find(id);
    }

    @PostMapping(
        path = "/widgets",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Widget> create(
            @Valid @RequestBody CreateWidgetRequest input) {
        Widget widget = widgets.create(input);

        URI location = ServletUriComponentsBuilder
            .fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(widget.id())
            .toUri();

        return ResponseEntity.created(location).body(widget);
    }

    @GetMapping(
        path = "/page",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, Integer> page(
            @RequestParam("size") int size) {
        return Map.of("size", size);
    }

    @GetMapping(
        path = "/snapshot",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, String>> snapshot() {
        return ResponseEntity.ok()
            .eTag("\"snapshot-v1\"")
            .cacheControl(
                CacheControl.maxAge(Duration.ofSeconds(60))
                    .cachePublic()
            )
            .body(Map.of("version", "v1"));
    }

    @GetMapping(
        path = "/secure/member",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> member() {
        return Map.of("access", "member");
    }

    @GetMapping(
        path = "/secure/admin",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Map<String, String> admin() {
        return Map.of("access", "admin");
    }

    @GetMapping("/fail")
    public void failOnPurpose() {
        // Chỉ tạo lỗi 500 có chủ đích để kiểm test/runtime.
        throw new IllegalStateException(
            "Deliberate server failure for test"
        );
    }
}
```

**Những điểm cần kiểm tra:**

- `@RequestMapping("/api")` ở class cộng `@GetMapping("/ping")` tạo **mapping nội bộ `/api/ping`**; context `/lab` là tầng Servlet và không nằm trong annotation.
- `@PostMapping(consumes=application/json)` giúp tái hiện 415 khi gửi `text/plain`.
- `@GetMapping(produces=application/json)` giúp tái hiện 406 khi client chỉ `Accept: application/xml`.
- `@Valid @RequestBody` kiểm malformed JSON và Bean Validation; service không nên nhận invalid DTO.
- `@RequestParam("size") int size` giúp tạo 400 do **thiếu tham số** hoặc **chuyển kiểu thất bại**.
- `ServletUriComponentsBuilder.fromCurrentRequest()` tạo Location URL dựa trên request thật, gồm context path, thay vì hardcode `/api/widgets/{id}` và làm client bị thiếu `/lab`.
- `ResponseEntity.eTag` cộng `Cache-Control` cho phép kiểm conditional GET: khi ETag khớp `If-None-Match`, response được rút còn 304 (nếu framework xử lý conditional request theo contract).
- `/fail` **cố tình ném exception** để test 500, không đưa endpoint lỗi này vào sản phẩm thật. Error body mặc định không ổn định giữa versions/format Accept, nên test assert status thay vì dựa byte-for-byte vào JSON error page.
- Phần `/secure` được bảo vệ bởi Servlet security filter chain bên ngoài controller.

## 5. HTTP test chạy qua Tomcat thật

### 5.1. Vì sao dùng JDK `HttpClient`?

Khi yêu cầu kiểm **context path, Servlet container, HTTP headers, security filter chain và response status**, việc khởi động real server là hữu ích. `@SpringBootTest(RANDOM_PORT)` mở embedded Tomcat ở một cổng ngẫu nhiên; `@LocalServerPort` inject cổng. `java.net.http.HttpClient` trong JDK 17 gửi request HTTP thật qua loopback, không cần thêm một HTTP client dependency riêng.

`@WebMvcTest` và MockMvc rất hữu ích cho controller tests, nhưng không chứng minh request đi qua connector/socket, Tomcat context root và error dispatch của container. Bộ HTTP tests bên dưới kiểm cả **đường đúng** và **đường sai**.

### 5.2. File `RuntimeHttpIntegrationTest.java` — 21 test methods

**`src/test/java/com/example/runtimelab/RuntimeHttpIntegrationTest.java`**

```java
package com.example.runtimelab;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class RuntimeHttpIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient client =
        HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .build();

    private final ObjectMapper json = new ObjectMapper();

    private HttpResponse<String> call(
            String method,
            String path,
            String accept,
            String contentType,
            String body,
            String basicCredentials,
            String ifNoneMatch) throws Exception {

        URI uri = URI.create(
            "http://127.0.0.1:" + port + path
        );

        HttpRequest.Builder builder =
            HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5));

        if (accept != null) {
            builder.header("Accept", accept);
        }
        if (contentType != null) {
            builder.header("Content-Type", contentType);
        }
        if (ifNoneMatch != null) {
            builder.header("If-None-Match", ifNoneMatch);
        }
        if (basicCredentials != null) {
            String encoded = Base64.getEncoder().encodeToString(
                basicCredentials.getBytes(StandardCharsets.UTF_8)
            );
            builder.header("Authorization", "Basic " + encoded);
        }

        if ("GET".equals(method)) {
            builder.GET();
        } else {
            builder.method(
                method,
                HttpRequest.BodyPublishers.ofString(
                    body == null ? "" : body
                )
            );
        }

        return client.send(
            builder.build(),
            HttpResponse.BodyHandlers.ofString()
        );
    }

    private HttpResponse<String> get(String path) throws Exception {
        return call("GET", path, null, null, null, null, null);
    }

    private HttpResponse<String> getAccept(
            String path, String accept) throws Exception {
        return call("GET", path, accept, null, null, null, null);
    }

    private HttpResponse<String> getBasic(
            String path, String credentials) throws Exception {
        return call("GET", path, null, null, null, credentials, null);
    }

    private HttpResponse<String> post(
            String path, String contentType, String body)
            throws Exception {
        return call(
            "POST", path, null, contentType, body, null, null
        );
    }

    // 1. Correct context path + JSON contract.
    @Test
    void correctContextPathReturns200AndJson() throws Exception {
        HttpResponse<String> r = get("/lab/api/ping");

        assertEquals(200, r.statusCode());
        assertTrue(r.headers()
            .firstValue("Content-Type")
            .orElse("")
            .contains("application/json"));
        assertEquals(
            "pong",
            json.readTree(r.body()).get("message").asText()
        );
    }

    // 2. Missing Servlet context never reaches the controller.
    @Test
    void missingContextPrefixReturns404() throws Exception {
        assertEquals(404, get("/api/ping").statusCode());
    }

    // 3. Typo in handler mapping.
    @Test
    void wrongRouteReturns404() throws Exception {
        assertEquals(404,
            get("/lab/api/pign").statusCode());
    }

    // 4. Spring 6 PathPatternParser does not auto-match trailing slash.
    @Test
    void extraTrailingSlashIsNotSilentlyAccepted()
            throws Exception {
        assertEquals(404,
            get("/lab/api/ping/").statusCode());
    }

    // 5. POST to GET-only path: 405, not 404.
    @Test
    void unsupportedHttpMethodReturns405() throws Exception {
        HttpResponse<String> r = call(
            "POST", "/lab/api/ping",
            null, null, "", null, null
        );
        assertEquals(405, r.statusCode());
    }

    // 6. produces=JSON but client only accepts XML: 406.
    @Test
    void incompatibleAcceptReturns406() throws Exception {
        assertEquals(406,
            getAccept(
                "/lab/api/ping",
                "application/xml"
            ).statusCode());
    }

    // 7. consumes=JSON but request text/plain: 415.
    @Test
    void wrongRequestContentTypeReturns415() throws Exception {
        assertEquals(415,
            post(
                "/lab/api/widgets",
                "text/plain",
                "name=Notebook&quantity=2"
            ).statusCode());
    }

    // 8. The JSON decoder should reject malformed text.
    @Test
    void malformedJsonReturns400() throws Exception {
        assertEquals(400,
            post(
                "/lab/api/widgets",
                "application/json",
                "{ invalid-json "
            ).statusCode());
    }

    // 9. Bean Validation should reject blank name and quantity 0.
    @Test
    void invalidDtoReturns400() throws Exception {
        assertEquals(400,
            post(
                "/lab/api/widgets",
                "application/json",
                "{\"name\":\" \",\"quantity\":0}"
            ).statusCode());
    }

    // 10. A required query parameter was omitted.
    @Test
    void missingQueryParameterReturns400() throws Exception {
        assertEquals(400,
            get("/lab/api/page").statusCode());
    }

    // 11. String "abc" cannot be converted to int.
    @Test
    void invalidQueryParameterTypeReturns400()
            throws Exception {
        assertEquals(400,
            get("/lab/api/page?size=abc").statusCode());
    }

    // 12. Positive control for query parameter binding.
    @Test
    void validQueryParameterReturnsJson() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/page?size=25");

        assertEquals(200, r.statusCode());
        assertEquals(
            25,
            json.readTree(r.body()).get("size").asInt()
        );
    }

    // 13. Seed item is found.
    @Test
    void knownWidgetReturns200() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/widgets/w1");

        assertEquals(200, r.statusCode());
        JsonNode body = json.readTree(r.body());
        assertEquals("w1", body.get("id").asText());
        assertEquals("Book", body.get("name").asText());
    }

    // 14. Domain not-found must contain stable business code.
    @Test
    void missingWidgetReturnsDomain404() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/widgets/no-such-widget");

        assertEquals(404, r.statusCode());
        assertEquals(
            "WIDGET_NOT_FOUND",
            json.readTree(r.body()).get("code").asText()
        );
    }

    // 15. POST then follow Location; no hardcoded generated ID.
    @Test
    void createReturns201LocationAndReadableResource()
            throws Exception {

        HttpResponse<String> created = post(
            "/lab/api/widgets",
            "application/json",
            "{\"name\":\"Marker\",\"quantity\":3}"
        );

        assertEquals(201, created.statusCode());
        JsonNode item = json.readTree(created.body());
        assertEquals("Marker", item.get("name").asText());
        assertEquals(3, item.get("quantity").asInt());

        String location = created.headers()
            .firstValue("Location")
            .orElseThrow();

        assertTrue(location.contains("/lab/api/widgets/"));
        URI locationUri = URI.create(location);
        assertEquals(
            "/lab/api/widgets/" + item.get("id").asText(),
            locationUri.getRawPath()
        );

        HttpResponse<String> fetched =
            get(locationUri.getRawPath());

        assertEquals(200, fetched.statusCode());
        assertEquals(
            item.get("id").asText(),
            json.readTree(fetched.body()).get("id").asText()
        );
    }

    // 16. Unhandled exception must not masquerade as 200.
    @Test
    void unexpectedExceptionReturns500() throws Exception {
        assertEquals(500,
            get("/lab/api/fail").statusCode());
    }

    // 17. Anonymous requests to protected route get 401.
    @Test
    void anonymousMemberRequestReturns401() throws Exception {
        HttpResponse<String> r =
            get("/lab/api/secure/member");

        assertEquals(401, r.statusCode());
        assertTrue(r.headers()
            .firstValue("WWW-Authenticate")
            .orElse("")
            .contains("Basic"));
    }

    // 18. Authenticated user can access member endpoint.
    @Test
    void memberWithCredentialsReturns200() throws Exception {
        HttpResponse<String> r = getBasic(
            "/lab/api/secure/member",
            "student:lab-only-password"
        );

        assertEquals(200, r.statusCode());
        assertEquals(
            "member",
            json.readTree(r.body()).get("access").asText()
        );
    }

    // 19. Authenticated USER lacks ADMIN role: 403.
    @Test
    void userCannotAccessAdminReturns403() throws Exception {
        assertEquals(403,
            getBasic(
                "/lab/api/secure/admin",
                "student:lab-only-password"
            ).statusCode());
    }

    // 20. Conditional request: GET 200 with ETag, then 304.
    @Test
    void matchingIfNoneMatchReturns304() throws Exception {
        HttpResponse<String> first =
            get("/lab/api/snapshot");

        assertEquals(200, first.statusCode());
        String etag = first.headers()
            .firstValue("ETag")
            .orElseThrow();

        HttpResponse<String> second = call(
            "GET",
            "/lab/api/snapshot",
            null, null, null, null, etag
        );

        assertEquals(304, second.statusCode());
        assertTrue(second.body().isEmpty());
    }

    // 21. Diagnostic endpoint is under Servlet context path.
    @Test
    void actuatorMappingsUsesContextPath() throws Exception {
        HttpResponse<String> r =
            get("/lab/actuator/mappings");

        assertEquals(200, r.statusCode());
        assertTrue(r.body().contains("/api/ping"));
    }
}
```

**Đây là mã hoàn chỉnh một test class.** `@SpringBootTest(RANDOM_PORT)` làm test sử dụng cổng ngẫu nhiên, không phụ thuộc việc có một app khác đang chạy port 8080. `call` cho phép thay method, Accept, Content-Type, Authorization, If-None-Match để mỗi lỗi có request tái hiện rõ ràng.

**Một số điểm QA cho test HTTP:**

- Test 500 sẽ khiến app ghi exception stack vào log server trong lab. Điều đó **được cố ý tạo ra**; đừng nhầm stack log là bản test đã fail, và đừng đưa `/fail` lên production.
- Test 404 ngoài context path chỉ assert status; body 404 do Tomcat có thể khác 404 từ Spring MVC/BasicErrorController.
- Test domain 404 **có thể assert `code`** vì `ApiErrorHandler` xác định JSON contract, còn route typo 404 không nên ép dùng business code đó.
- Test 201 **không** giả định ID luôn `w101`; dùng value trả về và Location để đọc lại, giảm flaky do cached context.
- Test conditional cache dùng `If-None-Match` có giá trị ETag lấy từ response đầu, không hardcode HTTP wire quoting; `304` đúng nghĩa không gửi body.
- Test security check 401/403 phải chạy **real SecurityFilterChain**. Nếu bypass filters ở test rồi assert 401, bạn có thể có kết quả sai hoặc test không kiểm đúng tầng.
- HttpClient có timeout 5 giây cho mỗi request, nên khi server vô tình bị kẹt thì test thất bại có giới hạn thay vì treo mãi. Đây là **test timeout**, không phải API timeout policy.
- Các kiểm thử này dùng **trạng thái ứng dụng memory**, không chạm database, không gọi internet, không có production credentials.

## 6. Controller web-slice tests: nhanh nhưng có giới hạn rõ

Web slice giúp phát hiện lỗi annotations, HTTP converter và validation mà không cần khởi động Tomcat. Tuy nhiên với Spring Security trên classpath, filter chain mặc định/custom có thể thay đổi status. Để **minh họa mapping-only tests**, file này cố ý tắt việc gắn filters vào MockMvc; do đó **không được dùng các tests này làm bằng chứng authentication, authorization hoặc CSRF**. Những điều đó đã được kiểm bằng real HTTP tests ở phần 5.

**`src/test/java/com/example/runtimelab/RuntimeWebSliceTest.java`**

```java
package com.example.runtimelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verifyNoInteractions;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@WebMvcTest(controllers = RuntimeApiController.class)
@AutoConfigureMockMvc(addFilters = false)
class RuntimeWebSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    WidgetService widgets;

    @Test
    void controllerMappingReturnsPong() throws Exception {
        mvc.perform(get("/api/ping"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("pong"));
    }

    @Test
    void invalidJsonDtoGets400WithoutCallingService()
            throws Exception {

        mvc.perform(post("/api/widgets")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\" \",\"quantity\":0}"))
            .andExpect(status().isBadRequest());

        verifyNoInteractions(widgets);
    }

    @Test
    void wrongMethodGets405WithinWebSlice()
            throws Exception {

        mvc.perform(post("/api/ping"))
            .andExpect(status().isMethodNotAllowed());
    }
}
```

**Import lưu ý:** Java static imports có thể được viết qua xuống dòng giữa các dấu chấm và identifier theo lexical grammar Java, nhưng để tránh nhầm khi copy, bạn có thể viết mỗi static import trên **một dòng duy nhất**. Bộ code phía trên dùng cách chia dòng sau tên package bằng dấu `.`, điều này Java vẫn tokenize thành package/import name hợp lệ khi không có ký tự lạ xen vào.

**Khác biệt quan trọng:**

- `@WebMvcTest` không nạp `@Service` thông thường, nên `@MockitoBean WidgetService` cung cấp collaborator.
- Test gửi `/api/ping` (mapping bên trong app), **không tự kiểm context root `/lab`** vì MockMvc không cần request đi qua Tomcat connector. Real HTTP test mới kiểm `/lab/api/ping` và `/api/ping` bị 404.
- `@AutoConfigureMockMvc(addFilters=false)` là lựa chọn **chỉ cho mapping-only lab**. Khi kiểm Spring Security, phải giữ filters bật và dùng `spring-security-test` (ví dụ `@WithMockUser` hoặc `SecurityMockMvcRequestPostProcessors`), đồng thời import security policy thật nếu slice không tự mang đúng custom configuration.
- `MockMvc` không kiểm DNS, TLS, ingress, socket timeout hay Servlet error-page dispatch thực tế. Với những vấn đề ấy dùng real HTTP/integration.

## 7. Chạy dự án và đọc kết quả

### 7.1. Chạy tất cả

Từ thư mục `runtime-error-lab`:

```bash
java -version
mvn test
```

Hoặc với Maven Wrapper **nếu project đã có**:

```bash
./mvnw test
```

Trên Windows PowerShell có thể dùng `mvnw.cmd test`. Lệnh `mvn test` cần network lần đầu nếu Maven chưa tải các dependencies. Với đúng project và environment JDK/Maven phù hợp, **24 test methods** được thiết kế để pass: 21 HTTP integration + 3 web slice.

**Quan trọng:** đây là các **kết quả kỳ vọng khi người học thực thi**; bài viết không tuyên bố chúng đã được chạy trong workspace hiện tại. Test compilation và execution là bước bắt buộc trước khi đưa project mẫu vào CI production thực sự.

Chạy riêng:

```bash
mvn -Dtest=RuntimeHttpIntegrationTest test
mvn -Dtest=RuntimeWebSliceTest test
```

Tổng quan output Maven sẽ nêu tests run, failures, errors, skipped. **Không chỉ kiểm dòng BUILD SUCCESS**; xem Surefire report và đảm bảo các lớp test mong muốn được phát hiện. Nếu tests bị skip do cấu hình hoặc tên class không match, không được gọi đó là regression suite xanh.

### 7.2. Chạy ứng dụng để tái hiện bằng curl

```bash
mvn spring-boot:run
```

App có `server.address=127.0.0.1` và `server.servlet.context-path=/lab`. Thử:

```bash
curl -i "http://127.0.0.1:8080/lab/api/ping"
curl -i "http://127.0.0.1:8080/api/ping"
curl -i -X POST "http://127.0.0.1:8080/lab/api/ping"
curl -i -H "Accept: application/xml" \
  "http://127.0.0.1:8080/lab/api/ping"
curl -i -H "Content-Type: text/plain" \
  -d "name=Pencil" \
  "http://127.0.0.1:8080/lab/api/widgets"
curl -i -H "Content-Type: application/json" \
  -d '{"name":"Pencil","quantity":4}' \
  "http://127.0.0.1:8080/lab/api/widgets"
curl -i "http://127.0.0.1:8080/lab/api/secure/member"
curl -i -u student:lab-only-password \
  "http://127.0.0.1:8080/lab/api/secure/member"
curl -i -u student:lab-only-password \
  "http://127.0.0.1:8080/lab/api/secure/admin"
```

PowerShell có thể có alias `curl` khác cú pháp, dùng `curl.exe` khi cần. **Không dùng account lab này trên hệ thống thật**; nếu demo được triển khai ra địa chỉ mạng công khai, hãy đổi/loại bỏ cấu hình mật khẩu `{noop}` và security rules, hoặc không triển khai project đó.

### 7.3. Phân tích số liệu thay vì chỉ nhìn status

Nên ghi một bảng ngắn cho mỗi case:

| Case | Request + headers | Expected | Actual | Tầng | Evidence |
| --- | --- | --- | --- | --- | --- |
| C01 | GET /api/ping | 404 | *khi chạy* | Servlet context | context=/lab, no mapping invoked |
| C02 | GET /lab/api/ping | 200 | *khi chạy* | Spring MVC | JSON message=pong |
| C03 | POST /lab/api/ping | 405 | *khi chạy* | Handler method | Allowed methods |
| C04 | POST invalid JSON | 400 | *khi chạy* | HTTP decoder | parse/validation |
| C05 | GET secure/admin USER | 403 | *khi chạy* | Authorization | roles=USER |
| C06 | GET snapshot + If-None-Match | 304 | *khi chạy* | Conditional response | ETag matched |

`*khi chạy*` nghĩa là **người học tự thu thập kết quả**; đây không phải số liệu đã chạy. Lưu ý body error 404/500 có thể khác tùy `Accept` và Boot patch level; giữ assertions của bộ core trên **status + contract JSON do app tự định nghĩa**.

## 8. Quy trình Red → Green → Regression có kiểm soát

Mục tiêu là **tái hiện một bug rồi sửa nguyên nhân**, không tạo test viết lại theo output sai.

### 8.1. Red: sai context path

Tình huống: người dùng gọi `GET /api/ping` dù ứng dụng chạy `server.servlet.context-path=/lab`.

- **Red:** real HTTP test `missingContextPrefixReturns404` chứng minh URL cũ không khớp. Nếu requirement là public `/api/ping`, bug nằm ở config/client contract, không phải `@GetMapping`.
- **Fix:** quyết định public base URL nào là hợp đồng; sửa caller base URL hoặc cấu hình context path/nginx rewrite cho nhất quán.
- **Green:** `GET /lab/api/ping` trả 200 theo requirement đã thống nhất.
- **Regression:** giữ một test positive và một test negative để tránh **lặp prefix** hoặc **bỏ prefix** ở lần deploy sau.

**Không sửa bằng cách thêm `/lab` vào annotation khi context đã là `/lab`**, vì có thể tạo URL `/lab/lab/api/ping`.

### 8.2. Red: thiếu Bean Validation

Tình huống: POST `{"name":" ","quantity":0}` vẫn trả 201 vì ai đó bỏ `@Valid` hoặc `starter-validation`.

- **Red:** `invalidDtoReturns400` thất bại (actual có thể 201).
- **Fix:** bật đúng validation dependency và `@Valid @RequestBody`, kiểm constraint annotations.
- **Green:** invalid POST trả 400.
- **Regression:** ngoài status, một test service/mock phù hợp nên xác nhận invalid request không tạo widget; với DB real có thể query fixtures.

Cẩn thận: một 400 do malformed JSON khác 400 do Bean Validation. Chúng cùng status nhưng nguyên nhân/logging/contract khác. Giữ **hai test riêng**.

### 8.3. Red: security policy bị vô hiệu hóa

Tình huống: một thay đổi security config làm GET `/api/secure/admin` không cần ADMIN.

- **Red:** `userCannotAccessAdminReturns403` trả 200.
- **Fix:** khôi phục `hasRole("ADMIN")`, kiểm matcher precedence, filter chain được áp dụng và authorities thực tế.
- **Green:** user role USER trả 403; anonymous member trả 401; member USER trả 200.
- **Regression:** giữ đủ ba tình huống: anonymous, authenticated đúng, authenticated thiếu quyền; không chỉ assert mọi request bị chặn.

Nếu test MockMvc dùng `addFilters=false`, security tests ở đó **không thể** chứng minh chính sách thực. Dùng full HTTP tests hoặc slice với real security chain/`spring-security-test`.

### 8.4. Red: JSON client gửi sai Content-Type

Tình huống: frontend gửi `text/plain` cho POST JSON.

- **Red:** `wrongRequestContentTypeReturns415`.
- **Fix:** client đặt `Content-Type: application/json` và gửi JSON đúng schema. Không sửa server cho phép `text/plain` chỉ để “hết lỗi” nếu API contract không chấp nhận nó.
- **Green:** POST đúng request type trả 201.
- **Regression:** giữ test 415 để không vô tình mở nhận các format ngoài spec.

### 8.5. Red: business not-found bị biến thành 500

Tình huống: service ném `NullPointerException` khi widget không tồn tại; controller không có error handler.

- **Red:** `missingWidgetReturnsDomain404` trả 500 hoặc status khác, hoặc không có `code=WIDGET_NOT_FOUND`.
- **Fix:** chuyển absence thành domain exception và map ổn định qua `@RestControllerAdvice`.
- **Green:** 404 JSON có code đúng; `/api/pign` vẫn 404 nhưng **không** nhận domain code.
- **Regression:** test cả đúng mapping nhưng missing data và sai mapping để phân biệt hai nguồn 404.

### 8.6. Red: Location header thiếu context path

Tình huống: controller hardcode `Location: /api/widgets/w101` nhưng app chạy dưới `/lab`.

- **Red:** `createReturns201LocationAndReadableResource` không đọc lại được resource theo Location.
- **Fix:** dùng `ServletUriComponentsBuilder.fromCurrentRequest()` hoặc URI builder tôn trọng context/proxy config an toàn.
- **Green:** POST 201, Location có `/lab/api/widgets/{id}`, GET lại 200.
- **Regression:** nếu chạy sau reverse proxy có public prefix `/portal`, thêm staging test qua ingress để bảo đảm absolute Location không trỏ sai nội bộ.

### 8.7. Bảo vệ nguyên tắc tái lập

Đối với một lỗi production thật:

1. Ẩn/khử PII trong request fixture, giữ lại HTTP method/path/header types cần thiết.
2. Xác định phạm vi: tầng gateway, container, MVC, security, codec, service, DB hay response streaming.
3. Viết **failing test** với kết quả đúng theo requirement, không hardcode output bug.
4. Thấy test fail **vì đúng nguyên nhân** (không phải setup thiếu token/DB).
5. Sửa code/config tối thiểu.
6. Chạy test riêng, suite cùng module, rồi integration/staging khi cần.
7. Ghi regression case ID và reason để lần sau không xóa test vì “thỉnh thoảng đỏ”.

Trong phiên bản README này, ví dụ chủ yếu thể hiện **đường correct + negative behavior cố định**. Để thực hành TDD red-green thật, người học phải tự thay đổi một điều kiện như đã mô tả và quan sát test fail, sau đó revert/fix. Không claim tất cả source hiện đang có bug.

## 9. Các lỗi 4xx cần hiểu theo tầng

### 9.1. 404: context path, handler mapping, static resource và domain

Một response 404 có thể đến từ:

- **Container** trước DispatcherServlet vì thiếu Servlet context path.
- **HandlerMapping** không có route khớp path.
- **Static resource handler** nhận `/**` nhưng không tìm thấy asset (`NoResourceFoundException` trong Spring Framework 6.1+).
- **Controller/service** chủ động trả 404 cho resource không tồn tại.
- **Reverse proxy/ingress** trả 404 trước khi request tới Java app.

Đừng assert tất cả 404 có cùng JSON body. Dùng diagnostics `/actuator/mappings` (nội bộ) và request correlation ID để phân biệt.

### 9.2. 405, 406 và 415

- 405: method sai (POST vào GET-only endpoint).
- 406: `Accept` của request không tương thích `produces` của endpoint.
- 415: `Content-Type` của request không tương thích `consumes` hoặc decoder không hỗ trợ.

Một gateway/security filter có thể chặn sớm thành 401/403, nên trong test muốn kiểm 405/415 cần xác minh filter chain không phải nguồn lỗi. Lab security cố ý không đòi auth cho `/api/ping`/`/api/widgets` và có CSRF exceptions giới hạn.

### 9.3. 400: JSON syntax, validation, binding và query

Các trường hợp khác nhau:

- JSON malformed → `HttpMessageNotReadableException` hoặc lỗi decoder.
- JSON hợp lệ nhưng không thỏa `@NotBlank`/`@Min` → validation.
- Query `size=abc` không convert được sang `int` → type mismatch.
- Query thiếu `size` → missing request parameter.
- File upload size quá lớn hoặc multipart malformed có thể trả 400/413 hoặc lỗi cấu hình khác; phải cấu hình limit và test riêng.

Không nên gom tất cả thành “bad request” trong logs mà không có error classification. Đồng thời tránh trả raw exception/stack trace/SQL query trong response cho client.

### 9.4. 401 vs 403 và CSRF

- **401 Unauthorized** trong HTTP nghĩa là chưa có/không hợp lệ authentication credentials; thường kèm `WWW-Authenticate`.
- **403 Forbidden** nghĩa access bị từ chối dù đã xác thực, hoặc CSRF/security policy từ chối request.
- Spring Security filter chain chạy trước MVC handler, nên 403 không nhất thiết do `@PreAuthorize`.
- Một user có role USER bị 403 khi cần ADMIN là đúng; tắt security chỉ để POST test 200 là bỏ mất coverage.

Bộ demo dùng HTTP Basic + một tài khoản local để tạo tình huống 401/403 có tính tái lập. **Cấm dùng tài khoản plaintext hoặc `{noop}` production.**

## 10. Các lỗi 5xx và timeout không nên kiểm bằng cách ngủ tùy tiện

### 10.1. 500: unhandled exception

Trong lab, `/api/fail` ném một `IllegalStateException` có chủ đích và status 500 được assert qua HTTP thật. Nhưng một số lỗi startup, Servlet filters, JSON serialization sau response commit hoặc proxy errors có semantics khác nhau. Không dựa vào exact BasicErrorController JSON của mọi Boot version.

### 10.2. 503 và 429: admission control/capacity

- 429 Too Many Requests thường là rate limit/admission rejection theo identity/quota.
- 503 Service Unavailable có thể do overload, maintenance, unavailable pool hoặc failed dependency; response status có thể đến từ app hoặc proxy.

Để test ổn định, **không** phát một nghìn requests ngẫu nhiên rồi hy vọng thấy 429. Hãy inject một fake rate limiter/bulkhead với **đồng hồ và quota xác định** trong test, ví dụ hạn mức 2 requests/identity, request thứ ba trả 429. Sau đó test `Retry-After` theo contract nếu có, reset fixture giữa tests. Với 503, mô phỏng dependency unavailable qua stub có kiểm soát thay vì cố làm hỏng production DB.

### 10.3. 504 và 408: timeout boundary

- 408 Request Timeout thường liên quan server đợi client request data lâu.
- 504 Gateway Timeout thường do gateway/proxy chờ upstream, hoặc app chủ động map downstream timeout thành 504.
- Client `HttpTimeoutException` là **lỗi từ phía test client**, không tự chứng minh server đã trả HTTP 504. Nếu request hết deadline trước khi đọc response, test có thể **không có HTTP status**.
- `Mono.timeout(...)` trong WebFlux/`CompletableFuture.orTimeout(...)` không bảo đảm blocking native I/O/DB call đã dừng; phải có driver timeouts và cleanup.

Để kiểm server 504, dùng upstream HTTP stub cố ý delay và cấu hình short timeout ở client của app, assert **HTTP response** 504. Để kiểm client timeout, assert `HttpTimeoutException` riêng, không gộp hai case vào cùng testcase. Tránh `Thread.sleep` cho test timing nhạy với CI nếu có cách dùng fake clock/`StepVerifier.withVirtualTime`.

### 10.4. Response đã committed

Nếu endpoint streaming đã gửi headers/body 200 rồi nguồn dữ liệu phát error, server **không chắc đổi status thành 500/504**. Client có thể thấy kết nối bị ngắt/stream terminal error. Cần kiểm cả HTTP headers, số events và terminal signals, không chỉ status đầu tiên.

## 11. Streaming/WebFlux: mở rộng bộ test cho reactive runtime

**Phần này là mở rộng khái niệm, không phải file thuộc project Spring MVC đã biên dịch ở phần 4.** Với reactive app riêng sử dụng `spring-boot-starter-webflux` và reactor-test, các lỗi cần tái hiện khác:

- WebFlux handler trả `Flux` nhưng gọi `Thread.sleep`/JDBC/`Mono.block()` trên Netty event-loop → queueing/starvation.
- SSE `text/event-stream` bị reverse proxy buffering, client không thấy events theo thời gian.
- NDJSON `application/x-ndjson` bị client parse như một JSON document.
- Infinite stream không cancel, tạo leak subscription/connection hoặc memory.
- `@WebFluxTest` mock exchange pass nhưng real Netty HTTP request fail vì base path, codec hoặc TLS config.

### 11.1. Snippet Spring WebFlux SSE

Snippet dưới đây **chỉ minh họa**, không biên dịch độc lập trong Maven MVC project ở phần 4:

```java
@GetMapping(
    path = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofMillis(100))
        .take(3)
        .map(n -> ServerSentEvent.<String>builder()
            .id(Long.toString(n))
            .data("event-" + n)
            .build());
}
```

WebFlux streaming test thường dùng `WebTestClient`, `FluxExchangeResult<ServerSentEvent<String>>` và `StepVerifier`:

```java
FluxExchangeResult<ServerSentEvent<String>> result =
    client.get().uri("/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(
            new ParameterizedTypeReference<
                ServerSentEvent<String>>() {}
        );

StepVerifier.create(result.getResponseBody())
    .assertNext(e -> assertEquals("event-0", e.data()))
    .expectNextCount(1)
    .assertNext(e -> assertEquals("event-2", e.data()))
    .verifyComplete();
```

Đây là snippet trong một WebFlux test có `client`, imports và controller thật. Nó không thể đặt thẳng vào MVC runtime demo rồi tuyên bố server là Reactor Netty. Với infinite stream phải `thenCancel()` thay vì `verifyComplete()`.

### 11.2. Tái hiện blocking anti-pattern một cách an toàn

Sai khi gọi blocking dependency ngay trên event-loop:

```java
// Sai trong reactive handler; blockingClient là ví dụ giả định.
String value = blockingClient.fetch();
return Mono.just(value);
```

Dùng mẫu offloading:

```java
Mono<String> value =
    Mono.fromCallable(() -> blockingClient.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

`Mono.fromCallable` **hoãn** blocking invocation cho đến lúc subscribe; `subscribeOn` đặt source call trên boundedElastic, tránh event-loop. Nó vẫn dùng một worker thread cho blocking call, không làm downstream database nhanh hơn hay hết giới hạn pool. Với test cần xác minh offloading bằng thread observation/BlockHound tương thích và real Netty runtime; một `StepVerifier` của `Mono.just(...)` không chứng minh hệ thống non-blocking end-to-end.

### 11.3. SSE và cancel cần test HTTP thật

`@WebFluxTest` auto-configures WebTestClient cho mock exchanges, **không khởi động Netty port thật**. Muốn kiểm response streaming qua socket:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class StreamingHttpTest {
    @Autowired WebTestClient client;
}
```

Snippet này cần app WebFlux/classpath và test methods phù hợp. Test trả result Flux và `StepVerifier.thenCancel()`; nếu cần kiểm server-side cleanup thực, đo active subscription counter **eventually**, không assert ngay sau client cancel qua network do disconnect propagation có độ trễ. Còn proxy buffering/reconnect cần staging integration qua edge, không phải mock exchange.

## 12. Reverse proxy, forwarding và các lỗi không nằm trong JVM

Lỗi chỉ xuất hiện khi đi qua ingress/CDN rất khó tái hiện bằng `@SpringBootTest(RANDOM_PORT)` trong process, vì test đó thường bypass proxy. Cần **hai loại request**:

```text
Direct to app:
  http://127.0.0.1:8080/lab/api/ping

Via gateway:
  https://service.example.test/portal/lab/api/ping
```

Nếu direct 200 nhưng public 404, kiểm:

1. Host-based routing; `Host`/SNI có trỏ đúng virtual host không?
2. Path prefix `/portal` có được strip trước khi tới Tomcat không?
3. Backend app có context `/lab` và controller mapping `/api/ping`; prefix có bị lặp/mất không?
4. HTTP vs HTTPS redirect và `X-Forwarded-Proto`/`Forwarded` có tin cậy đúng edge không?
5. Service port/namespace và rollout version; nhiều pods có configuration khác nhau không?
6. Request size, headers, gzip/chunked, idle timeout có bị proxy giới hạn không?

**Không xem `X-Forwarded-Prefix` là một lệnh tự rewrite request path**. Một proxy có thể strip path, giữ path hoặc gửi forwarded headers để app dựng public URLs. Khi ghép absolute Location, kiểm hostname/scheme/prefix qua real staging route. Chỉ tin forwarded headers từ **trusted proxy**, xóa/ghi đè headers do client tự gửi để tránh host-header poisoning/open redirect.

Mô hình Nginx chỉ để đọc rule, không tự deploy:

```nginx
location /portal/ {
    proxy_pass http://127.0.0.1:8080/;
}
```

Với prefix location và proxy_pass có URI `/` ở cuối trong cấu hình đơn giản, Nginx thường thay `/portal/` bằng `/`; URL public `/portal/lab/api/ping` thành upstream `/lab/api/ping`. Nếu đổi `proxy_pass` để **không** có URI, semantics khác; rewrite/location regex/normalization còn tác động. Phải đối chiếu upstream access logs thực, không suy URL backend chỉ từ một snippet.

## 13. Session, cookie, file upload và security edge cases

Bộ core lab chưa thêm session hay upload endpoint, để tránh kéo I/O/file permissions vào một bài kiểm status codes. Khi mở rộng sang production:

### 13.1. Cookie/session

Cần kiểm:

- `Set-Cookie: HttpOnly; Secure; SameSite` đúng theo HTTPS/cross-site requirements.
- Path của cookie có phù hợp context `/lab`/proxy prefix hay không.
- Session state không “lẫn” giữa hai người dùng; CSRF token gắn đúng phiên.
- Session expiration/invalidation và logout không tạo session fixation.
- SameSite không thay thế hoàn toàn CSRF protections trong mọi threat model.

JDK HttpClient mặc định không phải browser cookie jar. Nếu test session, tạo `CookieManager` **riêng cho từng test client/user** và assert cookies thật, hoặc dùng browser E2E khi cần behavior domain/same-site. Đừng chia sẻ một CookieManager giữa user A và user B rồi kết luận có data leak.

### 13.2. Upload/download

Các testcase thường gặp:

- Sai Content-Type multipart hoặc thiếu required part → 400/415 theo contract.
- File quá lớn → 413 hoặc một exception/limit status đã được app map rõ; không assume mọi container trả 413 giống nhau.
- `Content-Disposition` filename có ký tự đặc biệt, Unicode và path traversal-like values cần encode/validate.
- File download phải có đúng Content-Type, Content-Length/streaming semantics, không lộ file hệ thống ngoài allowlist.
- Đường dẫn `../` hoặc percent-encoded variants không được cho đọc file tùy ý; test ở môi trường được phép và chỉ với test fixtures.

Đặc biệt, không tạo test upload 5 GB trong CI chỉ để xem 413: cấu hình limit nhỏ trên một test profile, gửi payload ít KB vượt limit và assert kết quả sau khi đã map exception như contract.

### 13.3. CORS/preflight

Một browser có thể bị lỗi CORS dù server trả status 200 cho GET trực tiếp. Kiểm preflight:

```text
OPTIONS /lab/api/widgets
Origin: https://frontend.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: Content-Type
```

CORS do browser enforced; `curl` có thể cho phép request nhưng browser chặn đọc response. Test headers như `Access-Control-Allow-Origin`/`Access-Control-Allow-Methods` trong môi trường dùng đúng `CorsConfiguration`, đồng thời xem Spring Security filter ordering/CSRF. Không đặt `Access-Control-Allow-Origin: *` với credentials khi trình duyệt yêu cầu credentials và dữ liệu riêng.

### 13.4. Cache/ETag

`304 Not Modified` là **conditional response**, không phải HTTP error. Nếu endpoint dùng cache:

- Gửi GET đầu, ghi lại ETag từ response.
- Gửi `If-None-Match` bằng đúng value.
- Kiểm `304`, thường không có response body.
- Đổi phiên bản dữ liệu, kiểm ETag thay đổi và trả 200 khi resource mới.
- Tránh cache dữ liệu có chứa user secrets theo public cache, xác định `Cache-Control: private/no-store` thích hợp.

Cache behavior có thể khác qua CDN/reverse proxy; một test local 304 không chứng minh toàn bộ edge caching đúng. Với dữ liệu streaming vô hạn, ETag tự tính toàn response có thể cần buffer toàn body — cần đánh giá trước khi bật caching filter.

## 14. Tránh bộ test “xanh giả” và flaky tests

Một bộ regression tốt phải kiểm đúng hành vi và có khả năng tái lập.

| Anti-pattern | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Test gọi controller method trực tiếp rồi nói “HTTP 200” | Không có request mapping/codec/filter/container | Web slice hoặc real HTTP |
| `@SpringBootTest` mặc định rồi nói “đã kiểm Tomcat” | Default MOCK không mở port | RANDOM_PORT nếu cần connector |
| Assert mọi 404 cùng JSON | Container, domain, resource/gateway có thể khác | Chỉ assert domain schema nơi app sở hữu contract |
| Một test POST invalid trả 403 rồi ghi “validation pass” | CSRF/security đã chặn trước controller | Đúng auth/CSRF setup, verify service not invoked |
| Assert generated ID luôn `w101` | Context caching/test order có thể đổi counter | Lấy ID từ response, kiểm readback |
| Hardcode port 8080 trong integration test | CI có thể đang dùng port đó | @LocalServerPort |
| `Thread.sleep(100)` để chờ message async | Máy CI/GC jitter gây timing failures | Fake clock, StepVerifier virtual time, Awaitility/poll có timeout |
| Test gọi production API thật | Rủi ro thay đổi data/quota/outages/secret leak | Local stub, Testcontainers, staging được phép |
| Test chỉ assert status 200 | Body/header có thể sai | Assert media type, fields, Location, ETag |
| Bỏ các failures khỏi RPS/latency stats | Sai SLO/goodput | Đếm HTTP statuses/timeouts trong dashboard |
| Mock service luôn thành công | Không thấy DB exception/connection pool | Thêm integration/contract tests |
| Disable security cho mọi test | Bỏ sót 401/403/CSRF | Tách mapping slice và security integration |
| Assert response time < 30ms | Timing phụ thuộc CI/máy/network | Dùng bounded deadline rộng, load test riêng |
| Test không dọn DB/queue | Dữ liệu giữa tests nhiễm lẫn | Fixtures cleanup/unique keys/transactions đúng boundary |
| `@Transactional` test RANDOM_PORT tự tin rollback server writes | Server và test chạy transaction khác nhau | Data reset thực tế, không dựa test thread rollback |
| Chỉ kiểm one pod/localhost | Sai proxy/replica/rolling upgrade chưa được bắt | Staging E2E & rollout contract checks |

### 14.1. Một bài test lỗi cần ít nhất bốn assertions loại nào?

Không phải bắt buộc bốn assertion Java cho mọi test, mà cần cân nhắc bốn **mặt** của contract:

1. **Status**: đúng 200/201/304/400/401/403/404/405/406/415/500.
2. **Headers**: Content-Type, Location, WWW-Authenticate, ETag, Cache-Control, CORS/Retry-After nếu có.
3. **Body**: data schema/fields, business error code, tránh stack trace/PII.
4. **Side effects**: invalid request không ghi data; created resource GET lại được; timeout không tạo duplicate operation; cancellation release stream.

Với routing 404, việc chỉ assert status có thể đủ nếu body thuộc container, không phải contract app. Với business 404, nên assert error code ổn định.

### 14.2. CI nên chia hai luồng

- **Fast suite**: unit + web slice, chạy trên mỗi commit, ít dependencies, không tạo heavy contexts không cần.
- **Integration suite**: RANDOM_PORT, database Testcontainers/stub HTTP nếu có, chạy trên PR và trước release.

Có thể dùng JUnit `@Tag("integration")` hoặc Maven Surefire/Failsafe naming profile nếu dự án phát triển lớn. Nếu dùng `maven-failsafe-plugin` cho tên `*IT`, phải cấu hình plugin và verify phase đúng; README mẫu dùng tên `*Test` để `mvn test` chạy cả 24 tests một cách đơn giản.

Đừng xóa integration tests chậm chỉ để CI đẹp; có thể chuyển sang job riêng có feedback đủ nhanh và rõ người sở hữu. Flaky test phải được root-cause, không chỉ tăng retries vô hạn che lỗi.

### 14.3. Đặt ranh giới dữ liệu và bảo mật

- Chỉ dùng test accounts và fake data; không đưa production credentials vào source control hay logs.
- Redact Authorization/Cookie, JWT, session ID và PII khỏi test failure output.
- Actuator `mappings`, `env`, `threaddump` không public; trong lab server bind 127.0.0.1.
- Không chạy load/chaos lên production hoặc dịch vụ bên thứ ba chưa được phép.
- Giữ Spring Security policy thực ở các test kiểm authorization; phân biệt với mapping-only slice test có filters disabled.
- Đảm bảo test artifacts không ghi exception stack chứa bí mật; lab failure deliberate chỉ dùng string không nhạy cảm.
- Khi mô phỏng path traversal/upload, chỉ test trong sandbox/temp directory cho phép.

## 15. Checklist hoàn thành thực hành

- [ ] Project biên dịch bằng Java 17+, dùng đúng Spring Boot 3.5.x imports và dependencies.
- [ ] `server.servlet.context-path=/lab` được hiểu là prefix container, không lặp ở `@RequestMapping`.
- [ ] Có test positive 200 và negative 404 cho sai context/path/trailing slash.
- [ ] Có 405 do method, 406 do Accept, 415 do Content-Type.
- [ ] Có 400 JSON malformed, 400 Bean Validation, 400 required query missing, 400 int binding fail.
- [ ] Có 200 đọc widget có thật và domain 404 có JSON error code.
- [ ] Có 201 + Location + GET đọc lại resource không hardcode ID mới.
- [ ] Có 500 deliberate test, không assert default error body cứng theo framework version.
- [ ] Có 401 anonymous, 200 auth success và 403 authenticated thiếu role trên **real SecurityFilterChain**.
- [ ] Có 200 ETag và conditional GET 304 với If-None-Match.
- [ ] Có Actuator mappings diagnostic ở context path đúng, chỉ local/internal.
- [ ] Có sự phân biệt rõ @WebMvcTest/MockMvc với RANDOM_PORT real HTTP.
- [ ] Tests có timeout và random port, không phụ thuộc thứ tự, local-only fake credentials.
- [ ] Không nhầm 403 CSRF với lỗi validation 400 hoặc method 405.
- [ ] Không chạy những bài kiểm proxy/TLS/CORS/WebFlux bằng mock MVC rồi tuyên bố E2E.
- [ ] Nếu có session/DB/upload, đã bổ sung fixtures và cleanup đúng transaction/network boundary.
- [ ] Từng bug có thể đưa vào vòng **red → green → regression** mà không phụ thuộc máy developer.
- [ ] Báo cáo QA ghi đúng phạm vi đã kiểm; không bịa benchmark throughput/latency.

## 16. Câu hỏi tự kiểm tra và đáp án

**1. Vì sao `GET /api/ping` trả 404 còn `GET /lab/api/ping` trả 200?**  
Vì Servlet context path là `/lab`. Controller mapping chỉ là `/api/ping` ở bên trong context.

**2. POST lên GET-only route nên trả 404 hay 405?**  
Thường là 405 khi path có handler nhưng HTTP method không được hỗ trợ và không bị một filter/security khác chặn sớm.

**3. Accept application/xml nhưng endpoint chỉ produces application/json là gì?**  
Thường 406 Not Acceptable.

**4. Body text/plain gửi vào @PostMapping(consumes=application/json) là gì?**  
Thường 415 Unsupported Media Type.

**5. JSON malformed và @NotBlank fail có giống nhau?**  
Cùng có thể trả 400, nhưng một lỗi ở decoder, một lỗi ở Bean Validation. Cần tests riêng.

**6. Chưa có Basic credentials và có credentials role USER nhưng thiếu ADMIN khác gì?**  
Trường hợp đầu thường 401, trường hợp sau 403.

**7. Tại sao MockMvc test pass không chứng minh Tomcat context path /lab?**  
Vì MockMvc dùng mock servlet request/response trong process, không gọi Tomcat socket/context registration.

**8. Làm sao tránh flaky ID trong test tạo resource?**  
Lấy ID/Location từ POST response và GET lại, không hardcode counter value.

**9. Vì sao GET /lab/api/widgets/nope cần assert domain error code, còn GET /lab/api/pign không nhất thiết?**  
Vì domain 404 thuộc contract do app/advice sở hữu; route typo 404 có thể do container/static resource mapping.

**10. Nếu POST invalid trả 403, có chứng minh @Valid hoạt động không?**  
Không. Security/CSRF có thể chặn trước validation.

**11. `@SpringBootTest` mặc định mở server port thật không?**  
Không; dùng `RANDOM_PORT` để có embedded server thật.

**12. Vì sao HTTP 304 không phải lỗi?**  
Nó thông báo representation không thay đổi so với ETag/Last-Modified client đã có, giúp tránh truyền lại body.

**13. Nếu client timeout, server đã trả 504 chắc chưa?**  
Chưa. Client timeout có thể xảy ra khi không nhận được bất kỳ HTTP response nào.

**14. Nếu SSE đã gửi event 200 rồi publisher lỗi, test chỉ assert status 200 đã đủ chưa?**  
Chưa. Cần kiểm stream signals/termination/cancel và resource cleanup.

**15. Nếu direct backend 200 nhưng gateway 404, nên sửa @GetMapping trước không?**  
Không. Kiểm host routing/path rewrite/upstream port tại gateway trước.

**16. 24 tests pass có chứng minh API chịu được 10.000 RPS không?**  
Không. Functional regression tests không phải capacity/performance benchmark.

**17. Có thể đưa mã account `{noop}` của lab ra production để test 401/403 dễ hơn không?**  
Không. Đó là tài khoản/mật khẩu công khai, thiếu password hashing; chỉ dùng loopback lab.

**18. Phần nào cần thêm khi chuyển app sang WebFlux?**  
`@WebFluxTest`/WebTestClient, StepVerifier cho Flux/Mono, test event-loop blocking/cancellation/NDJSON/SSE và real Netty HTTP.

## 17. Tài liệu chính thức

- Spring Boot 3.5 — **Testing Spring Boot Applications**, `@WebMvcTest`, `@SpringBootTest`, `RANDOM_PORT` và transaction semantics: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — **Servlet Web Applications**, path mapping/static resources: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 — **Common Application Properties**, `server.servlet.context-path`, Actuator/security settings: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Boot 3.5 — **Actuator Mappings Endpoint**: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/mappings.html
- Spring Framework — **MockMvc**: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring Framework — **HTTP Status Code Handling**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html
- Spring Framework — **Web MVC Request Mapping and Content Negotiation**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework — **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — **Servlet Testing with MockMvc**: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Security — **CSRF Protection**: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Project Reactor — **Testing Reactive Streams with StepVerifier**: https://projectreactor.io/docs/core/release/reference/testing.html
- Spring Boot 3.5.16 — **Release 25/06/2026, final OSS 3.5.x**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** một bộ kiểm thử web runtime có chất lượng không chỉ kiểm “GET trả 200”. Nó phải tái hiện **sai context path, sai handler/method/media type, JSON/validation lỗi, security 401/403, domain 404, unexpected 500, conditional cache 304** và side effects theo cách ổn định; tách rõ controller-slice MockMvc với real HTTP through Tomcat. Đối với proxy, WebFlux streaming, upload, sessions, rate limiting, timeout và database, mở rộng bằng integration/E2E tests đúng tầng. Luôn giữ test dữ liệu giả, kiểm status/headers/body ở mức hợp đồng, và dùng vòng **red → green → regression** để lỗi đã sửa không quay lại.