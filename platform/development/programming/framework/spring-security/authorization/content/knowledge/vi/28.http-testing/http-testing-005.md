# Kiểm thử từng HTTP method trên cùng đường dẫn

> **Phạm vi:** Spring Security – authorization, nhóm **Kiểm thử HTTP**. Bài học tập trung vào việc chứng minh các quy tắc **GET, POST, PUT, PATCH, DELETE trên đúng cùng một URL** hoạt động độc lập; xử lý đầy đủ quyền của caller, CSRF, kết quả HTTP và trường hợp các method chưa được cho phép. Ví dụ dùng **Java 17+, Spring Boot 3.5.6, Spring Security 6.5.x, Servlet/Spring MVC, JUnit 5, MockMvc và spring-security-test**.

## 1. Vấn đề: cùng một URL không có nghĩa cùng một quyền

Giả sử API tài liệu đặt mọi thao tác trên URL `/api/records/42`. Mỗi HTTP method biểu thị một hành động khác nhau:

| Cùng URL `/api/records/42` | Hành động minh họa | Authority bắt buộc |
|---|---|---|
| `GET` | Đọc bản ghi | `records:read` |
| `POST` | Thực hiện thao tác tạo bổ sung trên bản ghi | `records:create` |
| `PUT` | Thay thế bản ghi | `records:update` |
| `PATCH` | Cập nhật một phần | `records:patch` |
| `DELETE` | Xóa bản ghi | `records:delete` |

Đây là một hợp đồng ví dụ được cố ý thiết kế với **cả năm method trên đúng một URL** để minh họa phân quyền. Trong REST API thực tế, `POST` thường tạo tài nguyên dưới collection (`POST /api/records`), còn `PUT/PATCH/DELETE` tác động đến tài nguyên cụ thể. Cách bố trí route sản phẩm cần phản ánh đúng domain; bài học không khuyến khích ép tất cả API theo đường dẫn này.

Vì cùng path nhưng permission khác nhau, chỉ có kiểm thử kiểu `GET /api/records/42` thành công **không thể chứng minh** `DELETE /api/records/42` được bảo vệ. Test phải thay đổi method trong khi **giữ nguyên URL**, rồi kiểm tra quyền cần thiết, response và việc controller có thực sự được gọi khi được phép.

### Hai lớp quyết định cần phân biệt

1. **Spring Security – authorization:** `AuthorizationFilter` (khi dùng `authorizeHttpRequests`) áp dụng `RequestMatcher` có cả method và path. Nếu đã xác thực nhưng thiếu authority thì request thường nhận **403 Forbidden**.
2. **Spring MVC – request mapping:** `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, `@DeleteMapping` quyết định handler nào có thể nhận method/path *sau khi qua security*. Nếu method không được controller hỗ trợ, sau khi được security cho qua, Spring MVC có thể trả **405 Method Not Allowed**.

Còn **401 Unauthorized** (ví dụ HTTP Basic yêu cầu xác thực) thể hiện caller chưa có xác thực phù hợp; **403 do CSRF thiếu/sai token** là một nguồn từ chối khác, có thể xảy ra trước khi đến rule phân quyền. Vì thế một assertion `status().isForbidden()` đơn lẻ chưa chắc đã kiểm tra đúng chính sách authorization.

## 2. Thiết kế ma trận kiểm thử trước khi viết code

Ta sử dụng ba danh tính đã xác thực:

- **reader:** có `records:read`.
- **editor:** có `records:read`, `records:create`, `records:update`, `records:patch`, **không có** `records:delete`.
- **admin:** có đủ cả năm authority.

Với cùng `/api/records/42`, ma trận trạng thái dự kiến là:

| HTTP method | Reader | Editor | Admin | Tại sao? |
|---|---:|---:|---:|---|
| GET | 200 | 200 | 200 | Cả ba có `records:read` |
| POST | 403 | 200 | 200 | Reader thiếu `records:create` |
| PUT | 403 | 200 | 200 | Reader thiếu `records:update` |
| PATCH | 403 | 200 | 200 | Reader thiếu `records:patch` |
| DELETE | 403 | 403 | 200 | Chỉ admin có `records:delete` |

**Mỗi cặp (method, user) là một test case độc lập.** Ma trận trên có 5 × 3 = **15 ca**; các ca cho method thay đổi trạng thái sẽ kèm **CSRF token hợp lệ** để chỉ còn phân biệt quyền.

Kiểm tra thêm ngoài ma trận chính:

1. **Anonymous + GET** → HTTP 401 khi ứng dụng dùng HTTP Basic.
2. **Admin + POST nhưng không có CSRF token** → HTTP 403 do CSRF, dù đủ authority.
3. **Admin + POST có CSRF token** → HTTP 200, chứng minh rule cho phép và controller mapping tồn tại.
4. **HEAD/OPTIONS** chưa định nghĩa rule authorization trong ví dụ → bị chặn bởi `anyRequest().denyAll()`, kể cả user có nhiều authority. Cách xử lý khác khi bật CORS/CSRF hoặc có rule riêng cần được kiểm thử theo cấu hình thực tế.
5. **Một request GET chứa query string** vẫn dùng policy của GET và path, vì `requestMatchers(HttpMethod.GET, "...")` không tự kiểm tra query parameter.

Đây là cách viết test từ policy mong muốn. Tránh đọc implementation rồi tạo test phản chiếu đúng từng nhánh hiện tại; cần dùng ma trận cố định như **hợp đồng bảo mật**, để test có thể phát hiện regression.

## 3. Nguyên tắc cấu hình method-aware authorization

Trong `SecurityFilterChain`, dùng overload `requestMatchers(HttpMethod, String...)`:

```java
.requestMatchers(HttpMethod.GET,    "/api/records/*").hasAuthority("records:read")
.requestMatchers(HttpMethod.POST,   "/api/records/*").hasAuthority("records:create")
.requestMatchers(HttpMethod.PUT,    "/api/records/*").hasAuthority("records:update")
.requestMatchers(HttpMethod.PATCH,  "/api/records/*").hasAuthority("records:patch")
.requestMatchers(HttpMethod.DELETE, "/api/records/*").hasAuthority("records:delete")
.anyRequest().denyAll()
```

Điểm thiết yếu:

- **`HttpMethod.GET` chỉ khớp GET**, không tự áp dụng cho POST, PUT, PATCH, DELETE. Không coi “path giống nhau” là cùng rule.
- **`"/api/records/*"`** đại diện cho một đoạn sau `/api/records/` trong ví dụ; test dùng đúng `/api/records/42`. Khi dùng MVC path matching, cần đặc biệt chú ý path variables, trailing slash, servlet path và nested path theo cấu hình thực tế.
- **Thứ tự matcher quan trọng:** Spring Security xét rule theo thứ tự khai báo và dùng **rule khớp đầu tiên**. Một rule chỉ theo path đặt trước rule chi tiết theo method có thể nuốt hết các method.
- `hasAuthority("records:delete")` kiểm tra **chuỗi authority đúng nguyên văn**, không tự thêm `ROLE_`. `hasRole("ADMIN")` lại thường thêm prefix `ROLE_`; không trộn lẫn hai cách mà không hiểu mapping.
- `anyRequest().denyAll()` đóng các nhánh không được khai báo. Khi ứng dụng còn actuator, health, static resources hoặc CORS preflight, cần đặt policy cho chúng một cách có chủ ý; không mở tất cả method chỉ để sửa một test thất bại.
- Phạm vi `requestMatchers` chỉ áp dụng **bên trong SecurityFilterChain đã được chọn**. Với nhiều chain, phải kiểm tra `securityMatcher` và thứ tự chain trước khi kết luận.

### Lỗi thứ tự thường gặp

**Cấu hình sai:**

```java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/records/**").hasAuthority("records:read")
    .requestMatchers(HttpMethod.DELETE, "/api/records/*")
        .hasAuthority("records:delete")
    .anyRequest().denyAll()
)
```

Rule chỉ theo path ở đầu khớp cả DELETE, nên một reader có `records:read` có thể vượt qua rule đầu và không bao giờ đến rule `records:delete`. Đây là lỗi **leo thang quyền qua HTTP method** mà ma trận 15 ca sẽ phát hiện: reader + DELETE bất ngờ thành công.

**Cấu hình đúng:** dùng các rule phân biệt method cụ thể trước, và đặt fallback tổng quát ở cuối. Nếu có rule theo path rộng, cần chứng minh nó không cấp quyền cho method khác ngoài dự định.

## 4. Dự án chạy được với Spring Boot

### 4.1. Cấu trúc thư mục và dependencies

```text
method-authorization-demo/
├── pom.xml
├── src/main/java/com/example/methodauth/
│   ├── MethodAuthorizationApplication.java
│   ├── SecurityConfig.java
│   └── RecordController.java
└── src/test/java/com/example/methodauth/
    └── HttpMethodAuthorizationTest.java
```

`pom.xml` dùng Java 17, Spring Boot 3.5.6 (quản lý các phiên bản Spring Security tương thích qua dependency management):

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>method-authorization-demo</artifactId>
    <version>1.0.0</version>
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

`spring-boot-starter-test` cung cấp Spring Test, MockMvc và JUnit Jupiter (bao gồm test tham số hóa); `spring-security-test` cung cấp `user()` và `csrf()`. Ví dụ dùng HTTP Basic để quan sát 401/403 và cố ý **giữ CSRF protection mặc định**.

### 4.2. Main class

`src/main/java/com/example/methodauth/MethodAuthorizationApplication.java`:

```java
package com.example.methodauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MethodAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(MethodAuthorizationApplication.class, args);
    }
}
```

### 4.3. SecurityFilterChain: năm quyền trên cùng URL

`src/main/java/com/example/methodauth/SecurityConfig.java`:

```java
package com.example.methodauth;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/records/*")
                    .hasAuthority("records:read")
                .requestMatchers(HttpMethod.POST, "/api/records/*")
                    .hasAuthority("records:create")
                .requestMatchers(HttpMethod.PUT, "/api/records/*")
                    .hasAuthority("records:update")
                .requestMatchers(HttpMethod.PATCH, "/api/records/*")
                    .hasAuthority("records:patch")
                .requestMatchers(HttpMethod.DELETE, "/api/records/*")
                    .hasAuthority("records:delete")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails reader = User.withUsername("reader")
            .password("{noop}reader123")
            .authorities("records:read")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password("{noop}editor123")
            .authorities(
                "records:read",
                "records:create",
                "records:update",
                "records:patch")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password("{noop}admin123")
            .authorities(
                "records:read",
                "records:create",
                "records:update",
                "records:patch",
                "records:delete")
            .build();

        return new InMemoryUserDetailsManager(reader, editor, admin);
    }
}
```

**Giải thích:** `UserDetailsService` tạo người dùng mẫu cho phép thử qua HTTP Basic. Các `authorities(...)` là chuỗi nguyên văn. `"{noop}"` không bảo vệ mật khẩu và **chỉ dùng cho ví dụ chạy cục bộ**; production cần password encoder an toàn, nguồn danh tính thật và HTTPS.

Ta không tắt CSRF bằng `csrf(csrf -> csrf.disable())`. Với cookie/session/HTTP Basic trên trình duyệt, CSRF protection có ý nghĩa bảo mật và test cần phản ánh điều đó. Nếu một API thật sử dụng Bearer token độc lập cookie và thiết kế stateless, đội phát triển có thể đánh giá lại chính sách CSRF theo mô hình đe dọa; việc bỏ CSRF là quyết định kiến trúc, không phải mẹo để cho test xanh.

### 4.4. Controller phân biệt rõ method

`src/main/java/com/example/methodauth/RecordController.java`:

```java
package com.example.methodauth;

import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/records/{id}")
public class RecordController {
    @GetMapping
    public Map<String, String> get(@PathVariable String id) {
        return Map.of("method", "GET", "id", id);
    }

    @PostMapping
    public Map<String, String> post(@PathVariable String id) {
        return Map.of("method", "POST", "id", id);
    }

    @PutMapping
    public Map<String, String> put(@PathVariable String id) {
        return Map.of("method", "PUT", "id", id);
    }

    @PatchMapping
    public Map<String, String> patch(@PathVariable String id) {
        return Map.of("method", "PATCH", "id", id);
    }

    @DeleteMapping
    public Map<String, String> delete(@PathVariable String id) {
        return Map.of("method", "DELETE", "id", id);
    }
}
```

Mỗi handler trả một JSON body có hai trường `method` và `id`, giúp test kiểm chứng **đã đến đúng controller method**, không chỉ kiểm tra status. Các handler cố ý không cập nhật cơ sở dữ liệu để bài học cô lập hành vi bảo mật. Trong API thật, POST/PUT/PATCH/DELETE phải có semantics dữ liệu, validation, quyền trên từng bản ghi và transaction phù hợp.

Vì cùng URL có nhiều mapping, nếu chỉ đặt `@GetMapping` mà gửi POST thì MVC không tự gọi GET. Nhưng **Spring Security chạy trước MVC**; một method chưa có rule có thể bị `denyAll()` trả 403 trước khi MVC có cơ hội trả 405.

## 5. Viết kiểm thử ma trận có thể chạy thực tế

### 5.1. Vì sao dùng `@SpringBootTest` và MockMvc?

`@SpringBootTest` + `@AutoConfigureMockMvc` tạo ứng dụng Spring và tích hợp Spring Security filter chain vào MockMvc. Điều này giúp kiểm tra **cả request matcher, authentication đã thiết lập, CSRF, authorization filter và MVC controller**.

Chúng ta cố ý dùng `with(user(...))` để tạo caller có authorities xác định; không cần phát HTTP Basic credentials cho từng ca. Hạn chế: `with(user(...))` **không kiểm chứng password hashing hay UserDetailsService**. Nếu muốn test xác thực thật, cần một ca HTTP integration qua Basic hoặc `httpBasic(...)`.

### 5.2. Toàn bộ test class

`src/test/java/com/example/methodauth/HttpMethodAuthorizationTest.java`:

```java
package com.example.methodauth;

import static org.junit.jupiter.params.provider.Arguments.arguments;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpMethod;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.ResultActions;

@SpringBootTest
@AutoConfigureMockMvc
class HttpMethodAuthorizationTest {
    private static final String PATH = "/api/records/42";

    @Autowired
    MockMvc mvc;

    private static UserDetails actor(String name) {
        return switch (name) {
            case "reader" -> User.withUsername("reader")
                .password("{noop}ignored")
                .authorities("records:read")
                .build();
            case "editor" -> User.withUsername("editor")
                .password("{noop}ignored")
                .authorities(
                    "records:read",
                    "records:create",
                    "records:update",
                    "records:patch")
                .build();
            case "admin" -> User.withUsername("admin")
                .password("{noop}ignored")
                .authorities(
                    "records:read",
                    "records:create",
                    "records:update",
                    "records:patch",
                    "records:delete")
                .build();
            default -> throw new IllegalArgumentException("Unknown actor: " + name);
        };
    }

    // Contract đã thiết kế ở phần 2. Không tạo expectedStatus từ rule thực tế.
    static Stream<Arguments> accessMatrix() {
        return Stream.of(
            arguments(HttpMethod.GET,    "reader", 200),
            arguments(HttpMethod.GET,    "editor", 200),
            arguments(HttpMethod.GET,    "admin",  200),

            arguments(HttpMethod.POST,   "reader", 403),
            arguments(HttpMethod.POST,   "editor", 200),
            arguments(HttpMethod.POST,   "admin",  200),

            arguments(HttpMethod.PUT,    "reader", 403),
            arguments(HttpMethod.PUT,    "editor", 200),
            arguments(HttpMethod.PUT,    "admin",  200),

            arguments(HttpMethod.PATCH,  "reader", 403),
            arguments(HttpMethod.PATCH,  "editor", 200),
            arguments(HttpMethod.PATCH,  "admin",  200),

            arguments(HttpMethod.DELETE, "reader", 403),
            arguments(HttpMethod.DELETE, "editor", 403),
            arguments(HttpMethod.DELETE, "admin",  200)
        );
    }

    @ParameterizedTest(name = "{index}: {0} by {1} -> {2}")
    @MethodSource("accessMatrix")
    void samePathRespectsHttpMethod(
            HttpMethod method, String username, int expectedStatus)
            throws Exception {

        MockHttpServletRequestBuilder builder = request(method, PATH)
                .with(user(actor(username)));

        // Token hợp lệ để ca 403 phản ánh thiếu authority,
        // không bị CSRF chặn trước khi kiểm tra quyền.
        if (method == HttpMethod.POST
                || method == HttpMethod.PUT
                || method == HttpMethod.PATCH
                || method == HttpMethod.DELETE) {
            builder.with(csrf());
        }

        ResultActions result = mvc.perform(builder)
                .andExpect(status().is(expectedStatus));

        if (expectedStatus == 200) {
            result.andExpect(jsonPath("$.method").value(method.name()))
                  .andExpect(jsonPath("$.id").value("42"));
        }
    }

    @Test
    void anonymousGetRequiresAuthentication() throws Exception {
        mvc.perform(get(PATH))
           .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfReturns403EvenWhenAuthorized() throws Exception {
        mvc.perform(post(PATH).with(user(actor("admin"))))
           .andExpect(status().isForbidden());

        mvc.perform(post(PATH)
                .with(user(actor("admin")))
                .with(csrf()))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.method").value("POST"));
    }

    static Stream<Arguments> unlistedMethods() {
        return Stream.of(
            arguments(HttpMethod.HEAD),
            arguments(HttpMethod.OPTIONS)
        );
    }

    @ParameterizedTest(name = "unlisted method {0} is denied")
    @MethodSource("unlistedMethods")
    void unlistedMethodsAreDeniedByFallback(HttpMethod method)
            throws Exception {
        mvc.perform(request(method, PATH).with(user(actor("admin"))))
           .andExpect(status().isForbidden());
    }

    @Test
    void queryStringDoesNotChangeGetPermission() throws Exception {
        mvc.perform(get(PATH)
                .queryParam("view", "summary")
                .with(user(actor("reader"))))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.method").value("GET"));
    }
}
```

**Số ca kiểm thử:** 15 test instances từ ma trận, 1 ca anonymous, 1 ca so sánh CSRF không/có token, 2 ca method chưa cho phép và 1 ca query string — tổng **20 test executions** (trong đó test CSRF thực hiện hai HTTP requests).

**Vì sao test đáng tin hơn test 403 đơn lẻ?**

1. Với POST/PUT/PATCH/DELETE, `with(csrf())` tạo token hợp lệ đúng cách mà Spring Security Test hỗ trợ. Nếu reader bị 403 trong ma trận này, đó không phải do cố tình thiếu CSRF.
2. Với admin, mọi method hợp lệ nhận **200 và JSON method đúng**, chứng minh request đi tới đúng handler MVC.
3. Test riêng không có CSRF cho admin chứng minh **cùng quyền nhưng đổi CSRF token có thể đổi kết quả**.
4. HEAD và OPTIONS không được phép bởi policy minh họa, dù Spring MVC có thể tự hỗ trợ HEAD từ GET và tự trả header `Allow` cho OPTIONS.
5. Query string không thay thế method-based authorization; nếu policy phụ thuộc query/body, cần cơ chế kiểm tra khác ở tầng thích hợp, không chỉ một URL matcher.

### 5.3. Chạy test

Mở terminal ở thư mục chứa `pom.xml`:

```bash
mvn test
```

Khi mọi ca đạt, Maven kết thúc thành công (`exit code 0`), JUnit không báo failure/error. Số lớp/ca xuất hiện trong log Maven phụ thuộc cấu hình Surefire; dựa vào kết quả assertion thay vì giả định chính xác một dòng stdout của plugin.

Để chạy thử ứng dụng độc lập:

```bash
mvn spring-boot:run
```

Tại terminal khác:

```bash
# Reader đủ quyền đọc, kỳ vọng HTTP 200.
curl -i -u reader:reader123 http://localhost:8080/api/records/42

# Không xác thực, HTTP Basic thường trả HTTP 401.
curl -i http://localhost:8080/api/records/42

# Reader thử DELETE: thường 403, nhưng không dùng lệnh này
# để chứng minh quy tắc authorization vì CSRF mặc định cũng chặn.
curl -i -X DELETE -u reader:reader123 http://localhost:8080/api/records/42
```

Khi gọi `POST/PUT/PATCH/DELETE` bằng curl, cần thực hiện đúng **CSRF token exchange** theo cơ chế ứng dụng đã cấu hình; command chỉ có HTTP Basic credentials **không đủ** để chứng minh người dùng thiếu quyền. Các ca MockMvc `with(csrf())` ở trên là phương pháp kiểm tra bảo mật có kiểm soát trong bài.

Trên Windows PowerShell, dùng `curl.exe` để tránh alias `curl` sang cmdlet khác. Không đưa mật khẩu demo vào script CI hoặc shell history trong hệ thống thực tế.

## 6. Đọc đúng kết quả 200, 401, 403, 404 và 405

Bản thân HTTP status chưa đủ để kết luận nguyên nhân. Với cùng path và method:

| Status | Cách diễn giải trước tiên | Kiểm tra tiếp |
|---|---|---|
| **200** | Request qua security và handler trả thành công | Xác minh response body `method`, controller được gọi và không có đường bypass |
| **401** | Entry point yêu cầu xác thực (HTTP Basic) | Kiểm tra credential, session/token, `AuthenticationEntryPoint` |
| **403** | Quyền bị từ chối **hoặc** CSRF/filter khác chặn | Có `csrf()` hợp lệ chưa? Authentication và authorities đã đúng chưa? |
| **404** | Không có route/resource phù hợp, hoặc bị che theo chính sách ứng dụng | Kiểm tra URL, base path, servlet path, controller mapping |
| **405** | MVC nhận path nhưng không hỗ trợ method đó | Chỉ thấy 405 nếu request được security cho qua đến MVC |

Ví dụ: nếu controller chỉ có `@GetMapping("/api/items/{id}")` và policy security cho phép POST đến path đó, POST có thể trả 405 vì không có `@PostMapping`. Nếu security từ chối POST trước, HTTP 403 xuất hiện và không thể dùng nó để kết luận controller có hay không có POST handler.

### Cẩn thận với HEAD và OPTIONS

Spring MVC có hành vi đặc biệt: `@GetMapping` thường hỗ trợ **HEAD** một cách tự động; **OPTIONS** có thể được MVC xử lý để trả danh sách method qua header `Allow`. Nhưng security matcher `HttpMethod.GET` **không đồng nghĩa** với `HttpMethod.HEAD`, và một request OPTIONS không tự được phép chỉ vì MVC hỗ trợ OPTIONS.

Trong ví dụ, `anyRequest().denyAll()` chặn cả HEAD/OPTIONS đối với user đã xác thực trước khi đến MVC. Điều đó là **kết quả của policy đang kiểm thử**, không phải quy tắc phải áp dụng mọi dự án.

Khi làm API trình duyệt cross-origin, **CORS preflight** thường là OPTIONS có `Origin` và `Access-Control-Request-Method`. Cần cấu hình CORS cùng security chain phù hợp để preflight được xử lý trước các yêu cầu cần authentication; việc bật `cors(...)` hoặc chọn cho phép OPTIONS phải dựa trên policy nguồn gốc/method/header được duyệt. Test CORS preflight **riêng** với một request OPTIONS thông thường, vì hai trường hợp không tương đương.

## 7. Cách kiểm tra nhanh khi test thất bại

Một trình tự giúp tránh sửa sai chỗ:

1. **Xác định đúng URL và HTTP method.** `GET` và `POST` trên cùng chuỗi path là hai request khác nhau. Kiểm tra path có dấu slash cuối, context path, servlet path, URL encoding và proxy rewrite.
2. **Kiểm tra authentication.** Với `with(user(...))`, principal có các authorities cụ thể; với Basic thật, phải có credentials hợp lệ. 401 là vấn đề xác thực hoặc entry point, chưa chắc là vấn đề role.
3. **Kiểm tra CSRF trước khi suy ra lỗi phân quyền.** Với POST/PUT/PATCH/DELETE ở ứng dụng còn CSRF protection, thêm `with(csrf())` trong test phân quyền; viết **một test khác** chuyên xác nhận token thiếu/sai bị chặn.
4. **Kiểm tra matcher method + path.** Đừng để `requestMatchers("/api/records/**")` khớp trước rule riêng cho DELETE. Rule đầu tiên khớp sẽ thắng.
5. **Kiểm tra authority nguyên văn.** `hasAuthority("records:delete")` cần đúng `GrantedAuthority` đó; `roles("ADMIN")` tạo `ROLE_ADMIN`, không tạo `records:delete`.
6. **Kiểm tra chain được chọn.** Nếu có nhiều `SecurityFilterChain`, `securityMatcher` có thể đưa request sang chain khác; `anyRequest()` chỉ là fallback của chain hiện tại.
7. **Kiểm tra MVC mapping.** Nếu security cho phép nhưng còn 404/405, xem `@RequestMapping` và các annotation theo method, không thêm quyền bừa bãi để che lỗi routing.
8. **Kiểm tra dispatcher và filter ngoài security.** Một số request phát sinh `ERROR`, `FORWARD` hoặc bị reverse proxy chặn; test cần phản ánh pipeline thực tế.

Để debug, có thể tăng log Spring Security ở **môi trường thử nghiệm kiểm soát**, nhưng tránh log credentials, cookies, token hoặc payload nhạy cảm. Đừng bật TRACE toàn hệ thống ở production để giải thích một ca 403.

## 8. Kiểm thử ranh giới và trường hợp đặc biệt

Ma trận chính bao phủ các thao tác hỗ trợ; hệ thống thật cần chọn thêm các ca theo rủi ro.

### 8.1. Người dùng không có authority và user chưa xác thực

- **Authenticated nhưng không có bất cứ `records:*` nào:** cả năm method phải bị từ chối (khi request mutation có CSRF hợp lệ); đó là test “default-deny cho role thấp nhất”.
- **Anonymous:** với HTTP Basic, request bảo vệ có thể trả 401. Nếu cấu hình form login, HTTP redirect 302 tới login là hành vi thường gặp; assertion 401 phải phù hợp cơ chế xác thực.
- **Authority sai chính tả/chữ hoa:** `records:Delete` khác `records:delete`. Test đúng literal authority giúp phát hiện sai mapping.

### 8.2. Phân quyền theo tài nguyên

`records:read` chỉ chứng minh một **quyền chức năng**; nó không tự chứng minh reader được xem bản ghi số 42 của người khác. Đối với policy “chỉ chủ sở hữu mới được sửa/xóa”, cần bổ sung kiểm tra **object-level authorization** tại service/method hoặc `AuthorizationManager` thích hợp. Test phải bao gồm bản ghi của chính mình và người khác, với cùng HTTP method và authority.

Ví dụ bảng bổ sung:

| User | Method | ID bản ghi | Kỳ vọng |
|---|---|---|---|
| Editor sở hữu bản ghi | PATCH | Của mình | Cho phép nếu đúng domain policy |
| Editor không sở hữu | PATCH | Người khác | 403 hoặc kết quả che tồn tại theo thiết kế |
| Admin | DELETE | Bản ghi được quản trị | Cho phép nếu đúng domain policy |

Đây là **minh họa policy mở rộng**, không phải hành vi tự có từ `hasAuthority(...)` ở ví dụ.

### 8.3. Phân biệt method override và client/proxy

Một số ứng dụng có cơ chế `_method`, proxy rewrite hoặc gateway hỗ trợ override HTTP method. Nếu bật, phải xác định method **hiệu lực tại security filter** và method **MVC nhận được** có nhất quán không; tránh trường hợp gateway cho phép POST nhưng backend hiểu DELETE. Trong môi trường production, tích hợp kiểm thử qua gateway để tìm sai lệch giữa các tầng. Không giả định framework tự bật mọi kiểu override.

### 8.4. CORS, filter chain khác và lỗi method không hỗ trợ

- Request `OPTIONS` với header preflight cần test theo cấu hình CORS thật, không dùng nó thay cho OPTIONS thông thường.
- `HEAD` có thể do Spring MVC xử lý tương ứng GET nhưng vẫn cần security policy rõ ràng.
- `TRACE`/`CONNECT` thường phải bị tắt hoặc chặn ở server/gateway phù hợp; không thử trực tiếp trên production nếu không có lý do và ủy quyền.
- Nếu `DELETE` không có trong controller, security policy vẫn có thể chặn 403 trước MVC; để assert 405, cần dựng một bối cảnh đã **cho qua security** và không có handler cho method đó.

### 8.5. Kiểm thử bypass và thứ tự rule

Một ca regression bổ sung rất có giá trị là xác nhận **reader + DELETE trả 403** dù reader có `records:read`. Ca này sẽ thất bại nếu ai đó vô tình thêm rule `.requestMatchers("/api/records/**").hasAuthority("records:read")` ở trước rule DELETE, giúp phát hiện thay đổi nguy hiểm trong cấu hình.

Ngoài ra, kiểm tra path lân cận như `/api/records/42/history` nếu ứng dụng có nested resource, bởi `*` và `**` có phạm vi khác nhau theo matcher. Không nên tự khẳng định mọi endpoint con được bảo vệ như endpoint cha nếu chưa có test.

## 9. Các lỗi phổ biến và cách sửa

| Dấu hiệu | Nguyên nhân điển hình | Cách xử lý |
|---|---|---|
| Reader POST 403 kể cả khi có `records:create` | Test thiếu/không hợp lệ CSRF token | Dùng `with(csrf())` để kiểm tra authorization; viết test riêng cho CSRF |
| Reader DELETE được 200 dù không có quyền xóa | Matcher path rộng đặt trước matcher DELETE | Đưa rule chi tiết method lên trước, giữ `anyRequest().denyAll()` |
| Editor PATCH 403 nhưng PUT 200 | Chưa cấp `records:patch` hoặc thiếu rule PATCH | Kiểm tra authority literal và thứ tự rule theo method |
| Admin DELETE 404/405 thay vì 200 | Security có thể đã cho qua, controller path/method chưa đúng | Kiểm tra `@DeleteMapping` và route thực tế |
| Không xác thực mà test kỳ vọng 403, thực tế 401 | HTTP Basic dùng `AuthenticationEntryPoint` | Tách test anonymous (401) khỏi test authenticated thiếu quyền (403) |
| GET 200, HEAD 403 | Rule chỉ khớp GET; fallback deny HEAD | Viết policy HEAD tường minh nếu ứng dụng cần HEAD |
| OPTIONS preflight bị chặn | Chưa cấu hình CORS cùng filter chain | Test preflight thật và cấu hình CORS chính xác; tránh `permitAll` bừa bãi |
| Test MockMvc bỏ qua security và mọi request đều 200 | Dựng MockMvc standalone nhưng không gắn Spring Security filters | Dùng `@SpringBootTest` + `@AutoConfigureMockMvc` hoặc `springSecurity()` |
| Test chỉ kiểm tra status 200 nên vào nhầm handler mà không biết | Thiếu assertion body/side effect | Kiểm tra `$.method` và kết quả nghiệp vụ mong đợi |
| Policy GET đúng nhưng trên production vẫn có bypass | Gateway/servlet path/chain khác với MockMvc | Thêm integration test qua HTTP server/gateway ở môi trường kiểm soát |
| Test matrix tạo kỳ vọng dựa trên implementation | Test lặp lại đúng logic đang có, không bắt lỗi cấu hình | Dùng policy table độc lập do nhóm nghiệp vụ/security phê duyệt |

## 10. Checklist hoàn thành bài

- [ ] Có **một URL duy nhất** và ít nhất năm method GET, POST, PUT, PATCH, DELETE để phân biệt.
- [ ] `SecurityFilterChain` đặt rule theo **method + path** và fallback `denyAll` sau cùng.
- [ ] Ma trận test gồm các trường hợp **đủ quyền và thiếu quyền** cho từng method.
- [ ] Test mutation **có CSRF hợp lệ** khi mục tiêu là kiểm thử authorization.
- [ ] Có test riêng **thiếu CSRF bị 403 dù user đủ quyền**.
- [ ] Có test anonymous phù hợp cơ chế xác thực; trong demo HTTP Basic → 401.
- [ ] Response của trường hợp được phép xác nhận **đúng controller method**, không chỉ status.
- [ ] Không đánh đồng **403 do security/CSRF** với **405 do MVC mapping**.
- [ ] HEAD và OPTIONS được đánh giá riêng; CORS preflight có policy riêng nếu API phục vụ browser.
- [ ] Nếu có nhiều chain, method override, owner-based permission hoặc gateway, bổ sung test đúng đường đi thực tế.
- [ ] Mọi thay đổi rule đều chạy lại ma trận để bắt regression leo thang quyền.

## Tài liệu chính thức

- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): thứ tự rule, match theo HTTP method, `anyRequest().denyAll()` và kiểm thử.
- [Spring Security – CSRF Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): dùng `with(csrf())`/invalid CSRF token trong MockMvc.
- [Spring Security – MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html): `with(user(...))` và `@WithMockUser`.
- [Spring Security – Servlet Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): tích hợp security filter chain vào MockMvc.
- [Spring Framework – Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html): `@GetMapping`, `@PostMapping`, hỗ trợ HEAD/OPTIONS và HTTP method mapping.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): xử lý preflight trước khi yêu cầu authentication.
