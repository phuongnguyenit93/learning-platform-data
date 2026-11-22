# Kiểm thử phân quyền HTTP trong Spring WebFlux: WebTestClient, mockUser và authorizeExchange

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể đọc một cấu hình `authorizeExchange`, xác định request nào được phép đi tiếp, viết kiểm thử HTTP cho khách chưa đăng nhập và người dùng mang các role/authority khác nhau, đồng thời nhận ra lỗi kiểm thử do thiếu CSRF. Bài tập trung vào **Spring Security trên nền Spring WebFlux (reactive)**, nơi `ServerHttpSecurity` tạo `SecurityWebFilterChain` và `WebTestClient` mô phỏng yêu cầu HTTP qua chuỗi xử lý WebFlux.

Ba thành phần có nhiệm vụ khác nhau:

- `authorizeExchange(...)` khai báo **quy tắc phân quyền trên request** (method, đường dẫn, thứ tự ưu tiên).
- `mockUser(...)` trong `SecurityMockServerConfigurers` gắn một `Authentication` giả lập vào request kiểm thử. Nó giúp thử phân quyền mà không phải đăng nhập thật.
- `WebTestClient` gửi request thử nghiệm và kiểm tra HTTP status, header, body. Khi bind vào `ApplicationContext` và tích hợp Spring Security, các request chạy qua bộ lọc bảo mật của ứng dụng.

**Phân biệt stack:** Đây là DSL reactive `ServerHttpSecurity.authorizeExchange`, với kiểu trả về `SecurityWebFilterChain`. Ứng dụng Spring MVC/Servlet thường dùng `HttpSecurity.authorizeHttpRequests`, `SecurityFilterChain` và `MockMvc`; không sao chép nguyên đoạn cấu hình WebFlux sang Servlet.

## 2. Request đi qua bảo mật như thế nào?

Luồng khái quát:

1. `WebTestClient` tạo request GET/POST với URI, header và body tùy chọn.
2. Chuỗi `WebFilter` của Spring Security xử lý các vấn đề liên quan đến security, trong đó có authentication, bảo vệ CSRF và authorization.
3. `authorizeExchange` chọn quy tắc phù hợp theo **thứ tự khai báo**: quy tắc khớp đầu tiên có hiệu lực.
4. Khi được cho phép, request mới tới WebFlux handler/controller; `WebTestClient` tiếp tục kiểm tra status và response body.

Authentication trả lời “người gọi là ai?”; authorization trả lời “người đó được làm gì?”. `mockUser("mai").roles("ADMIN")` tạo một người đã được xác thực trong môi trường test, có authority `ROLE_ADMIN`. Nó **không** xác nhận password, JWT, cookie phiên hay quy trình đăng nhập thật.

Các quy tắc thường dùng:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `.pathMatchers("/public/**").permitAll()` | Khách chưa đăng nhập vẫn được truy cập |
| `.pathMatchers("/admin/**").hasRole("ADMIN")` | Cần authority `ROLE_ADMIN`; đừng truyền `ROLE_ADMIN` vào `hasRole` |
| `.pathMatchers("/report/**").hasAuthority("report:read")` | Cần authority đúng chuỗi `report:read` |
| `.pathMatchers(HttpMethod.POST, "/report").hasAuthority("report:write")` | Chỉ áp dụng cho POST tại đường dẫn đó |
| `.anyExchange().authenticated()` | Mọi request chưa khớp phải được xác thực |
| `.anyExchange().denyAll()` | Mặc định từ chối các request chưa khớp |

`hasRole("ADMIN")` khác `hasAuthority("ADMIN")`: với tiền tố role mặc định, biểu thức đầu kiểm tra `ROLE_ADMIN`, biểu thức sau kiểm tra chính xác `ADMIN`. Dùng `roles("ADMIN")` trong mock tạo `ROLE_ADMIN`; dùng `authorities("report:write")` tạo quyền tùy ý.

**Đặt quy tắc cụ thể trước quy tắc rộng.** Ví dụ, nếu `.pathMatchers("/api/**").authenticated()` đứng trước `.pathMatchers("/api/admin/**").hasRole("ADMIN")`, đường dẫn admin đã khớp quy tắc đầu và quy tắc role phía sau không có tác dụng. Đặt `.anyExchange()` cuối chuỗi.

## 3. Dựng ví dụ có thể chạy (Java 17, Spring Boot 3.5.7)

Dự án mẫu sử dụng Maven và chỉ có WebFlux, không có starter Spring MVC. Các tệp bên dưới là **mã đầy đủ của ví dụ**, cùng một package `com.example.authz`.

Cấu trúc:

```text
webflux-authz/
├── pom.xml
└── src/
    ├── main/java/com/example/authz/
    │   ├── DemoApplication.java
    │   ├── ApiController.java
    │   └── SecurityConfig.java
    └── test/java/com/example/authz/
        └── ApiSecurityTests.java
```

### 3.1. Cấu hình Maven

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-authz</artifactId>
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
            <artifactId>spring-boot-starter-security</artifactId>
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

`spring-security-test` cung cấp `mockUser`, `csrf` và `springSecurity()`; `spring-boot-starter-test` cung cấp JUnit 5 và Spring Test; `spring-boot-starter-webflux` cung cấp WebFlux và API `WebTestClient` qua phụ thuộc test.

### 3.2. Ứng dụng và các endpoint

`src/main/java/com/example/authz/DemoApplication.java`:

```java
package com.example.authz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/com/example/authz/ApiController.java`:

```java
package com.example.authz;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {
    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/profile")
    public Mono<String> profile() {
        return Mono.just("profile");
    }

    @GetMapping("/admin/report")
    public Mono<String> readReport() {
        return Mono.just("report");
    }

    @PostMapping("/admin/report")
    public Mono<String> createReport() {
        return Mono.just("created");
    }
}
```

Các handler trả `Mono<String>` để minh họa ứng dụng reactive. Nội dung trả về là hằng số nên việc đánh giá status phụ thuộc trực tiếp vào cấu hình security.

### 3.3. Cấu hình authorizeExchange

`src/main/java/com/example/authz/SecurityConfig.java`:

```java
package com.example.authz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/report").hasRole("ADMIN")
                .pathMatchers(HttpMethod.POST, "/api/admin/report").hasAuthority("report:write")
                .pathMatchers(HttpMethod.GET, "/api/profile").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Giải thích từng đường đi:

- `GET /api/public`: mở cho mọi người, kể cả chưa đăng nhập.
- `GET /api/profile`: cần đã đăng nhập; role cụ thể không quan trọng.
- `GET /api/admin/report`: cần `ROLE_ADMIN`.
- `POST /api/admin/report`: cần authority `report:write` **và** CSRF token hợp lệ vì ví dụ để CSRF bật theo mặc định.
- Phương thức/path khác: `.anyExchange().denyAll()` (không vô tình mở endpoint mới).
- `httpBasic` cho phép phản hồi challenge HTTP Basic đối với request chưa xác thực; trong test, `mockUser` bỏ qua bước gửi Basic credentials.

Ở đây `.pathMatchers(HttpMethod.GET, ...)` và `.pathMatchers(HttpMethod.POST, ...)` phân biệt hai quyền trên cùng một URL. Các quy tắc này xét yêu cầu HTTP, không xét quyền sở hữu dữ liệu của một bản ghi trong database.

## 4. Kiểm thử WebTestClient + mockUser

`src/test/java/com/example/authz/ApiSecurityTests.java`:

```java
package com.example.authz;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ApiSecurityTests {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
            .bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicEndpointIsAccessibleWithoutLogin() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void profileRequiresAuthentication() {
        client.get().uri("/api/profile")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserCanReadProfile() {
        client.mutateWith(mockUser("mai").roles("USER"))
            .get().uri("/api/profile")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile");
    }

    @Test
    void regularUserCannotReadAdminReport() {
        client.mutateWith(mockUser("mai").roles("USER"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminCanReadReport() {
        client.mutateWith(mockUser("lan").roles("ADMIN"))
            .get().uri("/api/admin/report")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report");
    }

    @Test
    void writerCanCreateReportWithCsrfToken() {
        client.mutateWith(mockUser("linh").authorities("report:write"))
            .mutateWith(csrf())
            .post().uri("/api/admin/report")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("created");
    }

    @Test
    void missingCsrfTokenBlocksPostEvenForWriter() {
        client.mutateWith(mockUser("linh").authorities("report:write"))
            .post().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void adminRoleAloneDoesNotGrantWriteAuthority() {
        client.mutateWith(mockUser("lan").roles("ADMIN"))
            .mutateWith(csrf())
            .post().uri("/api/admin/report")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Chạy ở thư mục chứa `pom.xml`:

```bash
mvn test
```

**Kết quả mong đợi:** cả tám test JUnit đều pass (Maven thoát với mã 0). Các test không mở cổng HTTP thật: `bindToApplicationContext(context)` đưa request qua WebFlux handler và security filters trong `ApplicationContext`; `.apply(springSecurity())` cài đặt hỗ trợ test bảo mật cần thiết cho `mockUser`/`csrf`.

Đọc một chuỗi assertion:

- `.get()` hoặc `.post()` chọn HTTP method; `.uri(...)` chọn đường dẫn.
- `.mutateWith(mockUser(...))` tạo biến thể client cho request giả lập người dùng được xác thực.
- `.exchange()` thực thi request trên mock server.
- `.expectStatus()` kiểm tra status; `.expectBody(String.class).isEqualTo(...)` kiểm tra nội dung body chỉ khi request được phép tới controller.
- `.mutateWith(csrf())` bổ sung token CSRF hợp lệ cho kiểm thử POST, không tự cấp thêm role/authority.

`mockUser()` mặc định có username `user`, role `USER`; `mockUser("lan").roles("ADMIN")` dùng authority `ROLE_ADMIN`. `authorities("report:write")` không tự thêm `ROLE_`. Vì thế role ADMIN trong bài không đồng nghĩa với quyền `report:write`; kiểm thử cuối chứng minh hai điều kiện tách biệt.

## 5. Ma trận trường hợp cần bảo vệ

| Request | Trạng thái xác thực và quyền | CSRF | Status kỳ vọng | Lý do |
| --- | --- | --- | --- | --- |
| GET `/api/public` | Khách ẩn danh | Không cần | `200` | `permitAll()` |
| GET `/api/profile` | Khách ẩn danh | Không cần | `401` | `authenticated()` và HTTP Basic |
| GET `/api/profile` | `ROLE_USER` | Không cần | `200` | Đã xác thực |
| GET `/api/admin/report` | `ROLE_USER` | Không cần | `403` | Thiếu `ROLE_ADMIN` |
| GET `/api/admin/report` | `ROLE_ADMIN` | Không cần | `200` | Đúng role |
| POST `/api/admin/report` | `report:write` | Có | `200` | Đúng authority, CSRF hợp lệ |
| POST `/api/admin/report` | `report:write` | Không | `403` | Bị lớp bảo vệ CSRF chặn |
| POST `/api/admin/report` | Chỉ `ROLE_ADMIN` | Có | `403` | Thiếu authority `report:write` |

Thông thường `401 Unauthorized` diễn tả **chưa được xác thực** và `403 Forbidden` diễn tả **đã xác thực nhưng bị từ chối**, nhưng status thực tế còn chịu ảnh hưởng của cơ chế entry point, CSRF, thứ tự filter và cấu hình ứng dụng. Không khẳng định mọi trường hợp 403 đều do thiếu role. Nếu muốn kiểm tra riêng một quy tắc phân quyền của POST, phải cung cấp CSRF token hợp lệ trước.

Thử bổ sung case âm khi đổi rule:

- Nếu đảo `hasRole("ADMIN")` và `authenticated()` cho cùng đường dẫn, test với `ROLE_USER` có thể từ 403 thành 200; test âm phát hiện rò rỉ quyền.
- Nếu thay `hasAuthority("report:write")` bằng `hasRole("ADMIN")`, test writer trước đây thành 403 và test admin với CSRF có thể thành 200.
- Nếu thêm endpoint mới mà vẫn dùng `.anyExchange().denyAll()`, cần khai báo một rule mới, có chủ ý và test cả trường hợp được phép lẫn từ chối.

## 6. Khi nào dùng @WithMockUser, WebFluxTest hoặc test HTTP thật?

`@WithMockUser` là cách khác để đặt ngữ cảnh security cho test tích hợp Spring Security; khi muốn biến thể theo từng request, `client.mutateWith(mockUser(...))` giúp từng trường hợp minh bạch hơn. Ví dụ minh họa (đặt trong test class đã kết nối Spring Security và import `org.springframework.security.test.context.support.WithMockUser`):

```java
@WithMockUser(roles = "ADMIN")
@Test
void adminUsingAnnotation() {
    client.get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk();
}
```

Với controller WebFlux đơn lẻ, có thể dùng `@WebFluxTest(ApiController.class)` và `@Import(SecurityConfig.class)`; slice test không tự quét được custom bean `SecurityWebFilterChain`, nên cần import cấu hình bảo mật. Ví dụ chính dùng `@SpringBootTest` để chắc chắn kiểm tra đúng chuỗi filter của ứng dụng. Khi không cần tự dựng client, Spring Boot cũng có `@AutoConfigureWebTestClient` để tiêm `WebTestClient` trong mock web environment.

`mockUser` chỉ chứng minh **logic cho phép/từ chối với một Authentication giả lập**. Muốn kiểm chứng đăng nhập thật, HTTP Basic credentials, JWT validation, OAuth2, session/cookie hoặc reverse proxy, cần bộ test tích hợp tương ứng với cơ chế authentication thật. Với test gửi HTTP đến server thật (`bindToServer()`/cổng ngẫu nhiên), hãy dùng credential/token thật hoặc test fixture phù hợp; đừng dựa vào `mockUser` để mô phỏng xác thực phía server từ xa.

## 7. Lỗi thường gặp và cách chẩn đoán

1. **Mọi request đều 200 dù đã khai báo bảo mật.** Bạn có thể bind client trực tiếp vào controller bằng `bindToController(...)` mà chưa lắp chuỗi security thật, hoặc slice test thiếu `@Import(SecurityConfig.class)`. Hãy xác nhận test đã load `SecurityWebFilterChain`.
2. **`mockUser` không tác dụng hoặc thiếu ngữ cảnh.** Kiểm tra dependency `spring-security-test`, việc áp dụng `springSecurity()` khi bind thủ công vào `ApplicationContext`, và việc chọn đúng `SecurityMockServerConfigurers.mockUser` của WebFlux (không phải request post-processor cho Servlet).
3. **Đã có `ADMIN` mà vẫn 403.** Xem `.hasRole("ADMIN")` có đúng `ROLE_ADMIN` không; xem request thực sự là GET hay POST; nếu POST kiểm tra CSRF và authority riêng.
4. **Đặt `.anyExchange()` hoặc matcher rộng quá sớm.** Quy tắc sau không được xét khi matcher trước đã khớp; viết thêm test phủ định cho endpoint nhạy cảm.
5. **Khẳng định 401/403 là 404.** Security filter có thể chặn request trước khi WebFlux tìm handler, vì vậy endpoint chưa tồn tại vẫn có thể nhận 401/403 tùy rule. Muốn xác minh mapping, kiểm tra độc lập URI và cấu hình authorization.
6. **Test pass nhưng production vẫn hở quyền.** Mock chỉ cho biết code chọn đúng rule với principal giả. Cần kiểm tra thêm mapping role từ token/identity provider, nhiều `SecurityWebFilterChain`, quyền trên từng tài nguyên, và bảo vệ tầng service nếu ứng dụng có yêu cầu.
7. **Tắt CSRF chỉ để test POST pass.** Điều này thay đổi hành vi an ninh của ứng dụng. Giữ CSRF đúng cấu hình thực tế; khi cần thử POST, thêm `.mutateWith(csrf())`. Chỉ tắt CSRF khi kiến trúc và mô hình xác thực của API có cơ sở rõ ràng.

## 8. Checklist tự đánh giá

Trước khi coi một bộ test phân quyền là đủ, hãy trả lời được:

- Cấu hình đang dùng WebFlux `authorizeExchange` hay Servlet `authorizeHttpRequests`?
- Với mỗi endpoint, HTTP method, path và matcher **đầu tiên** nào được áp dụng?
- Test có bao phủ khách ẩn danh, user đủ quyền, user thiếu quyền và quyền có tên gần giống nhưng không khớp không?
- Có hiểu sự khác nhau giữa `roles("ADMIN")` và `authorities("report:write")` không?
- Test POST/PUT/PATCH/DELETE đã phản ánh chính sách CSRF của ứng dụng chưa?
- Request đi qua filter chain thật hay chỉ gọi controller?
- Cơ chế xác thực thực tế (mật khẩu, token, session) có một bộ test riêng không?

Nắm được ba điểm — **quy tắc rõ ràng, mock đúng quyền, kiểm thử cả trường hợp bị chặn** — giúp phát hiện lỗi phân quyền HTTP sớm mà không cần khởi động server cho từng case.

## Tài liệu chính thức

- Spring Security, Reactive HTTP authorization: https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/authorize-http-requests.html
- Spring Security, WebTestClient test setup: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html
- Spring Security, testing authentication with `mockUser`: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html
- Spring Security, testing CSRF: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot 3.5, testing WebFlux controllers and `@WebFluxTest`: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html