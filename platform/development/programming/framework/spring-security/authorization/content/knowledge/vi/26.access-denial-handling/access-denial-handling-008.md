# Xử lý lỗi từ method security qua lớp web mà vẫn giữ đúng mã trạng thái

> **Phạm vi:** Spring Security cho ứng dụng **Servlet + Spring MVC/REST**, đặc biệt khi `@PreAuthorize`, `@PostAuthorize` hoặc mã nghiệp vụ ném ngoại lệ phân quyền từ service. Mục tiêu là giữ đúng **HTTP status** và semantics xác thực, đồng thời trả body lỗi nhất quán nếu API cần. Ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit 5 và MockMvc; nguyên lý áp dụng cho các phiên bản mới hơn khi kiểm tra lại API tương ứng.

## 1. Vấn đề thực tế và kết quả cần đạt

Giả sử một API đọc tài liệu có phương thức service được bảo vệ:

```java
@PreAuthorize("hasAuthority('document:read')")
public Document find(long id) { ... }
```

Nếu HTTP request gọi tới phương thức này mà không đủ quyền, method-security interceptor sẽ từ chối trước khi method chạy. Một lỗi phổ biến là đưa mọi exception từ controller/service vào bộ xử lý lỗi chung rồi luôn trả `200 OK`, `400 Bad Request` hoặc `500 Internal Server Error`, kể cả khi nguyên nhân thực sự là thiếu đăng nhập/quyền. Kết quả làm sai hợp đồng HTTP, khiến client quyết định sai (ví dụ hiển thị “hệ thống hỏng” thay vì yêu cầu đăng nhập), che khuất lỗi phân quyền và làm test bảo mật khó tin cậy.

**Hợp đồng trạng thái cần kiểm thử:**

| Tình huống | Trạng thái HTTP phù hợp | Thành phần chịu trách nhiệm |
| --- | --- | --- |
| Chưa xác thực, truy cập thao tác cần quyền | Thường là **401 Unauthorized** trong REST API | `AuthenticationEntryPoint` |
| Basic/Bearer credential không hợp lệ hoặc hết hạn | **401 Unauthorized** (kèm challenge/header phù hợp scheme) | Bộ lọc xác thực + `AuthenticationEntryPoint` |
| Đã xác thực nhưng thiếu authority, scope hoặc không sở hữu tài nguyên | **403 Forbidden** | `AccessDeniedHandler` hoặc policy lỗi đã được định nghĩa rõ |
| Có quyền xem nhưng tài nguyên không tồn tại | **404 Not Found** | Exception handler nghiệp vụ |
| Đầu vào không hợp lệ | **400 Bad Request** hoặc **422 Unprocessable Content** theo hợp đồng API | Validation + MVC exception handling |
| Lỗi bất ngờ không liên quan đến bảo mật | **5xx**, thường là **500** | Error handler / hạ tầng giám sát |
| Thao tác hợp lệ | Mã thành công dự kiến (`200`, `201`, `204`, …) | Controller |

**Lưu ý về 401 và 403:** “401” trong HTTP có tên chuẩn là *Unauthorized* nhưng ngữ nghĩa chủ yếu là **thiếu hoặc sai xác thực**; “403” là **không được phép thực hiện thao tác**. Với ứng dụng dùng form login, người chưa đăng nhập có thể được chuyển hướng `302` đến trang login: đó là hành vi của `AuthenticationEntryPoint` dạng redirect. Ví dụ dưới đây thiết kế **REST API dùng HTTP Basic**, nên chọn phản hồi `401`/`403` rõ ràng; không áp một quy tắc status chung cho mọi kiểu giao diện.

## 2. Ngoại lệ từ method security đi qua lớp web như thế nào?

### 2.1. Đường đi chuẩn

```text
HTTP request
  │
  ▼
Spring Security FilterChainProxy
  ├─ authentication filter (HTTP Basic/Bearer/session...)
  ├─ ExceptionTranslationFilter
  └─ AuthorizationFilter (HTTP URL authorization)
       │
       ▼
  DispatcherServlet (Spring MVC)
       │
       ▼
  @RestController
       │ gọi một bean khác qua Spring AOP proxy
       ▼
  @Service + @PreAuthorize / @PostAuthorize
       │
       ├─ cho phép ──> logic / response thành công
       │
       └─ từ chối ──> AccessDeniedException
                          │
                          ├─ nếu MVC không xử lý mất exception
                          │      ▼
                          │  ExceptionTranslationFilter
                          │      ├─ anonymous/unauthenticated ──> AuthenticationEntryPoint
                          │      └─ authenticated ──────────────> AccessDeniedHandler
                          │
                          └─ nếu @ControllerAdvice bắt và trả response
                                 └─ bộ lọc không còn thấy ngoại lệ đó
```

`@EnableMethodSecurity` kích hoạt method authorization; Spring Boot Starter Security không tự bật `@PreAuthorize` chỉ vì thêm dependency. Với `@PreAuthorize`, Spring AOP đánh giá quyền **trước** khi gọi method; khi từ chối, Spring Security ném `AccessDeniedException` (các phiên bản hiện đại có thể dùng `AuthorizationDeniedException` là lớp con của `AccessDeniedException`). Với `@PostAuthorize`, kiểm tra diễn ra **sau** khi method đã chạy, nên side effect trong method có thể đã xảy ra dù kết quả HTTP sau cùng là 403.

`ExceptionTranslationFilter` chỉ chuyển **`AuthenticationException` hoặc `AccessDeniedException`** xảy ra trong phạm vi filter chain thành hành vi HTTP phù hợp. Nó không tự thực hiện phân quyền. Đối với `AuthenticationException`, nó gọi `AuthenticationEntryPoint`; với `AccessDeniedException`, nó dùng `AuthenticationTrustResolver` để phân biệt danh tính anonymous/remember-me chưa đủ tin cậy và người dùng xác thực phù hợp, rồi gọi entry point hoặc access-denied handler.

Đây là nguyên lý cho một HTTP request có đi qua filter chain. Một lời gọi service trực tiếp từ scheduler, message listener, CLI, unit test hoặc background task không có lớp HTTP tự động đổi exception thành `401`/`403`; adapter gọi service phải quyết định cách biểu diễn lỗi của giao thức đó.

### 2.2. Vì sao `@ControllerAdvice` dễ làm sai status?

Spring MVC đưa exception qua chuỗi `HandlerExceptionResolver`. `@ExceptionHandler` trên controller hoặc `@ControllerAdvice` có thể **giải quyết exception trước khi nó thoát ra filter chain**. Khi một handler đã viết response, `ExceptionTranslationFilter` không còn gì để xử lý.

Ví dụ **sai**:

```java
@RestControllerAdvice
class DangerousAdvice {

    @ExceptionHandler(Exception.class)
    ResponseEntity<String> everyError(Exception ex) {
        return ResponseEntity.ok("Something went wrong");
    }
}
```

Nếu handler trên bắt được `AccessDeniedException`, người dùng không đủ quyền có thể nhận **200 OK**. Đổi `ok` thành `internalServerError` cũng sai: lỗi ủy quyền sẽ biến thành **500**. Một ví dụ khác:

```java
@ExceptionHandler(AccessDeniedException.class)
ResponseEntity<String> denied(AccessDeniedException ex) {
    return ResponseEntity.status(403).body("Forbidden");
}
```

Handler này có thể làm **anonymous nhận 403 thay vì 401**, vì đã bỏ qua logic phân nhánh của `AuthenticationEntryPoint`. Nó cũng có thể bỏ sót challenge `WWW-Authenticate`, phân tách API/browser, hoặc cơ chế bearer token cụ thể.

**Quy tắc an toàn cho web MVC:** để `AccessDeniedException`/`AuthenticationException` đi đến xử lý bảo mật mặc định hoặc các handler bảo mật được cấu hình trong `HttpSecurity.exceptionHandling(...)`; dùng `@RestControllerAdvice` cho **lỗi nghiệp vụ được xác định hẹp** như not-found/validation. Khi phải xử lý bảo mật tại MVC vì yêu cầu kiến trúc riêng, cần tái tạo rõ điều kiện anonymous/authenticated, scheme/challenge và status, đồng thời test cả 401 lẫn 403.

## 3. Ví dụ chạy được: API REST phân quyền tại service

Ví dụ có 3 danh tính:

- `reader` có authority `document:read`, được đọc tài liệu.
- `viewer` đăng nhập được nhưng chỉ có `document:list`, không được đọc.
- Anonymous không có credential.

Để **thật sự kiểm tra method security**, lớp URL cho phép `GET /api/documents/**` đi qua; quyền cụ thể được giữ ở `@PreAuthorize` trên service. Những route không khai báo bị từ chối ở lớp HTTP. Mô hình này phục vụ minh họa: dự án thật có thể thêm chính sách HTTP độc lập với method security.

Dependencies trong Maven (`pom.xml`) do Spring Boot quản lý phiên bản:

```xml
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
```

Phần dependencies trên là đoạn chèn vào một **Spring Boot Maven project đã có parent/BOM và plugin phù hợp**, không phải toàn bộ `pom.xml`. Tất cả Java class bên dưới nằm trong package `example.methodsecurity`. Mỗi khối ghi tên file tương ứng.

### 3.1. Khởi động ứng dụng

**`src/main/java/example/methodsecurity/DemoApplication.java`**

```java
package example.methodsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 3.2. Cấu hình Spring Security, phân nhánh 401/403 và body lỗi

**`src/main/java/example/methodsecurity/ApiSecurityConfig.java`**

```java
package example.methodsecurity;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint unauthenticated = (request, response, cause) -> {
            response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Basic realm=\"documents\"");
            sendProblem(response, 401, "Unauthorized");
        };

        AccessDeniedHandler forbidden = (request, response, cause) ->
                sendProblem(response, 403, "Forbidden");

        return http
                .authorizeHttpRequests(auth -> auth
                        // Tránh lỗi khi container dispatch sang trang xử lý lỗi.
                        .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                        // Cho phép tới controller; @PreAuthorize vẫn phải quyết định.
                        .requestMatchers(HttpMethod.GET, "/api/documents/**").permitAll()
                        .anyRequest().denyAll())
                // Credential sai cũng đi qua entry point 401 với Basic challenge.
                .httpBasic(basic -> basic.authenticationEntryPoint(unauthenticated))
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint(unauthenticated)
                        .accessDeniedHandler(forbidden))
                .build();
    }

    private static void sendProblem(
            HttpServletResponse response, int status, String title) throws IOException {
        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);

        // title là hằng số do server chọn, không chèn exception message vào JSON.
        response.getWriter().write(
                "{\"type\":\"about:blank\",\"title\":\"" + title
                        + "\",\"status\":" + status + "}");
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("reader")
                        .password("{noop}reader-pass")
                        .authorities("document:read")
                        .build(),
                User.withUsername("viewer")
                        .password("{noop}viewer-pass")
                        .authorities("document:list")
                        .build());
    }
}
```

**Giải thích thiết kế:**

1. `@EnableMethodSecurity` bật AOP kiểm tra `@PreAuthorize`. Phải gọi service qua Spring-managed proxy; lời gọi `this.someSecuredMethod()` trong chính bean có thể bỏ qua interceptor của proxy.
2. `requestMatchers(GET, "/api/documents/**").permitAll()` chỉ cho request đi qua **HTTP URL authorization**, không trao `document:read`. Người đọc không được phép nếu `@PreAuthorize` từ chối.
3. `AuthenticationEntryPoint` trả `401` với header `WWW-Authenticate: Basic realm="documents"`. Điều này giữ Basic challenge đúng scheme. Nếu dùng OAuth2 Resource Server/JWT, dùng entry point tương ứng để bảo toàn header Bearer và mô tả lỗi; **không** thay bằng Basic.
4. `AccessDeniedHandler` trả `403` khi đã xác thực nhưng thiếu quyền. Body dạng `application/problem+json` có status khớp với HTTP status. Body không chứa stacktrace, tên user hay message kỹ thuật nhạy cảm.
5. Bộ xử lý lỗi này được cấu hình ở `HttpSecurity.exceptionHandling` và cả nhánh HTTP Basic. Nhờ đó lỗi bắt nguồn từ authentication hoặc method authorization đều đi về cặp handler nhất quán.
6. `DispatcherType.ERROR` được phép để việc xử lý lỗi downstream không vô tình bị chặn bởi `anyRequest().denyAll()`. Ở dự án có nhiều `SecurityFilterChain`, phải bảo đảm chính sách tương ứng cho chain thực sự khớp API.
7. `{noop}` cùng mật khẩu trong source **chỉ dành cho ví dụ local/test**. Trong hệ thống thật, dùng password encoder mạnh hoặc identity provider, bí mật đặt ngoài mã nguồn, chính sách kết nối HTTPS và cách quản lý session/token phù hợp.
8. Không tắt CSRF một cách đại trà trong ví dụ. Các request minh họa chỉ là GET, nên không cần CSRF token; API có thao tác thay đổi trạng thái phải thiết kế CSRF tương ứng với phương thức xác thực.

Nếu không cần JSON lỗi tùy biến, có thể bỏ các lambda `unauthenticated`/`forbidden` và chỉ bật `httpBasic(Customizer.withDefaults())`: Spring Security vẫn chọn 401 hoặc 403 theo mặc định. Tính chính xác của status **không phụ thuộc** việc tự viết một `@ControllerAdvice` cho `AccessDeniedException`.

### 3.3. Service có phân quyền, controller chỉ gọi service

**`src/main/java/example/methodsecurity/DocumentService.java`**

```java
package example.methodsecurity;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentService {

    public record Document(long id, String title) {}

    @PreAuthorize("hasAuthority('document:read')")
    public Document find(long id) {
        if (id == 404L) {
            throw new DocumentNotFoundException(id);
        }
        return new Document(id, "Guide " + id);
    }
}
```

Ở đây `404L` là fixture mô phỏng tài liệu không tồn tại, giúp test phân biệt **404 nghiệp vụ** và **403 phân quyền**; ứng dụng thật sẽ tra cứu database và ném not-found khi không có bản ghi.

**`src/main/java/example/methodsecurity/DocumentNotFoundException.java`**

```java
package example.methodsecurity;

public class DocumentNotFoundException extends RuntimeException {
    public DocumentNotFoundException(long id) {
        super("Document " + id + " does not exist");
    }
}
```

**`src/main/java/example/methodsecurity/DocumentController.java`**

```java
package example.methodsecurity;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public DocumentService.Document get(@PathVariable long id) {
        return service.find(id); // Gọi qua Spring bean/proxy.
    }
}
```

Không cần `try/catch(AccessDeniedException)` trong controller. Nếu service từ chối, exception được truyền qua MVC và Spring Security xử lý theo scheme. Nếu service thành công, controller trả JSON tài liệu với HTTP `200`.

### 3.4. Chỉ xử lý lỗi nghiệp vụ trong MVC

**`src/main/java/example/methodsecurity/DomainErrorAdvice.java`**

```java
package example.methodsecurity;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DomainErrorAdvice {

    @ExceptionHandler(DocumentNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(DocumentNotFoundException ex) {
        ProblemDetail problem = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Document not found");
        problem.setDetail("The requested document does not exist");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }
}
```

Advice này **không nhận** `AccessDeniedException`, `AuthenticationException` hoặc `Exception.class`; do đó nó không biến lỗi quyền thành 404/500/200. Trong API thực tế, có thể thêm handler hẹp cho validation (`MethodArgumentNotValidException`, v.v.) với status thích hợp. Giữ phạm vi exception cụ thể giúp phát hiện lỗi bất ngờ dưới dạng 5xx, thay vì im lặng báo thành công.

## 4. Kiểm thử end-to-end trong Spring MVC với đầy đủ Security Filter Chain

Chỉ unit-test một method có `@PreAuthorize` là chưa đủ: bạn phải test **HTTP status thực** sau khi MVC, SecurityFilterChain và handler xử lý. Với Spring Boot 3.x, có thể dùng `@SpringBootTest` + `@AutoConfigureMockMvc`; cần có `spring-security-test` trong test classpath.

**`src/test/java/example/methodsecurity/MethodSecurityHttpStatusTest.java`**

```java
package example.methodsecurity;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodSecurityHttpStatusTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private DocumentService documents;

    @Test
    void anonymousRequestDeniedByMethodSecurityReturns401() throws Exception {
        mvc.perform(get("/api/documents/42"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate", "Basic realm=\"documents\""))
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void wrongBasicCredentialsReturn401() throws Exception {
        mvc.perform(get("/api/documents/42")
                        .with(httpBasic("reader", "wrong-pass")))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate", "Basic realm=\"documents\""))
                .andExpect(jsonPath("$.status").value(401));
    }

    @Test
    void authenticatedButMissingAuthorityReturns403() throws Exception {
        mvc.perform(get("/api/documents/42")
                        .with(httpBasic("viewer", "viewer-pass")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.status").value(403))
                .andExpect(jsonPath("$.title").value("Forbidden"));
    }

    @Test
    void authorizedRequestReturns200AndDocument() throws Exception {
        mvc.perform(get("/api/documents/42")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(42))
                .andExpect(jsonPath("$.title").value("Guide 42"));
    }

    @Test
    void authorizedButMissingDocumentRetains404() throws Exception {
        mvc.perform(get("/api/documents/404")
                        .with(httpBasic("reader", "reader-pass")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.title").value("Document not found"));
    }

    @Test
    @WithMockUser(username = "viewer", authorities = "document:list")
    void directServiceCallThrowsSecurityExceptionNotHttpResponse() {
        assertThrows(AccessDeniedException.class, () -> documents.find(42L));
    }
}
```

Các ca test chứng minh những điều khác nhau:

- Không credential với URL đã `permitAll`: request **đi tới method security**, bị chặn ở `@PreAuthorize` và quay lại `401`. Điều này phân biệt method security với trường hợp URL filter từ chối ngay từ đầu.
- Credential sai: thất bại tại lớp xác thực HTTP Basic, cũng là `401`, chưa cần gọi method.
- Credential đúng nhưng authority thiếu: đi qua HTTP, bị service từ chối và nhận `403`; body cũng có `status=403`.
- Có đúng authority: method chạy và trả `200` với dữ liệu.
- Có quyền nhưng không có tài liệu: qua kiểm tra `@PreAuthorize` rồi ném exception nghiệp vụ, MVC trả `404`.
- Gọi service trực tiếp dưới `@WithMockUser` thiếu authority: nhận Java exception `AccessDeniedException`, chứ không tự sinh ra HTTP response.

**Chạy test** trong Spring Boot Maven project có cấu hình và các file trên:

```bash
./mvnw test -Dtest=MethodSecurityHttpStatusTest
```

Hoặc:

```bash
mvn test -Dtest=MethodSecurityHttpStatusTest
```

Nếu dùng Gradle, chạy class test tương ứng bằng Gradle test task. **Kỳ vọng**: 6 phương thức test đều thành công; hãy đối chiếu log runner thực tế, không kết luận từ một stdout minh họa. Nếu dùng Spring Boot 4 trở lên, vị trí một số annotation test có thể thay đổi; xác nhận package với phiên bản dự án rồi cập nhật import, giữ nguyên ý tưởng kiểm chứng.

## 5. Tách các tầng để tìm đúng nguyên nhân khi status sai

### 5.1. Case A: anonymous nhận 403 thay vì 401

Các nguyên nhân hay gặp:

1. Một `@RestControllerAdvice` có `@ExceptionHandler(AccessDeniedException.class)` đã tự trả `403` trước bộ lọc; trường hợp anonymous không còn đi qua entry point.
2. API được cấu hình `Http403ForbiddenEntryPoint` cho mô hình xác thực khác (entry point này cố ý trả 403), hoặc `SecurityFilterChain` khác khớp request.
3. Test đã gắn `@WithMockUser` nên request **được coi là đã xác thực**, dù người viết test tưởng là anonymous.
4. Client HTTP tự gửi cookie/token cũ; dùng browser hoặc test fixture rò security context.

Cách chẩn đoán: lặp lại bằng request **không** Authorization/Cookie, kiểm tra handler nào chạy (`AuthenticationEntryPoint` hay `AccessDeniedHandler`), kiểm tra `SecurityContextHolder` và chain khớp route. Đảm bảo test có một positive control với credential hợp lệ.

### 5.2. Case B: thiếu quyền nhưng trả 500

Kiểm tra theo thứ tự:

1. `@EnableMethodSecurity` đã bật chưa? Nếu chưa, `@PreAuthorize` bị bỏ qua, thường gây lộ dữ liệu/`200` chứ không gây `403`.
2. Phương thức có được gọi **qua Spring proxy** không? Self-invocation, tạo service bằng `new` hoặc không là Spring bean có thể bỏ qua interceptor.
3. Exception có đúng kiểu `AccessDeniedException` (hoặc subclass) không? Ném `IllegalStateException("Forbidden")` chỉ là lỗi runtime thông thường, mặc định thành `500`.
4. `@ExceptionHandler(Exception.class)` có bắt exception bảo mật rồi chuyển thành 500 không?
5. Có filter/async boundary bất thường làm exception không đi qua `ExceptionTranslationFilter` không?
6. Response đã bị commit (streaming, write body quá sớm) trước khi từ chối chưa? Lúc này server không thể đổi header/status một cách an toàn.

Đặt breakpoint/log có kiểm soát ở `AuthorizationManagerBeforeMethodInterceptor`, `ExceptionHandlerExceptionResolver`, `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`. Không ghi credential/token vào log. Trong Spring Security có thể bật DEBUG tạm thời cho package security khi debug, rồi tắt ở production.

### 5.3. Case C: lỗi quyền bị biến thành 200

Điển hình là kiểu:

```java
try {
    return ResponseEntity.ok(service.find(id));
} catch (Exception ex) {
    return ResponseEntity.ok(Map.of("success", false, "message", "Error"));
}
```

Đây là mẫu **không nên dùng**: `@PreAuthorize` bị từ chối nhưng API vẫn phát `200`. Nếu business contract buộc trả một envelope cố định, **status HTTP vẫn phải đúng**:

```json
{
  "code": "FORBIDDEN",
  "message": "Insufficient permission",
  "status": 403
}
```

Body trên chỉ là ví dụ shape của error envelope; response HTTP thực phải là **403**, không phải 200. Không dùng `catch(Exception)` để viết envelope trước khi biết class lỗi hoặc quyền.

### 5.4. Case D: tài nguyên không tồn tại trả 403/404 sai

Một `404` chỉ có nghĩa “không tìm thấy” **sau khi** quyền truy cập phù hợp đã được kiểm tra (tùy policy). Nếu anonymous và user không đủ quyền cùng gọi một tài liệu, thứ tự kiểm tra có thể làm thay đổi quan sát:

```text
Anonymous -> GET /api/documents/404
  -> @PreAuthorize từ chối trước -> 401

Viewer authenticated, thiếu document:read -> GET /api/documents/404
  -> @PreAuthorize từ chối trước -> 403

Reader authenticated, có document:read -> GET /api/documents/404
  -> service chạy, không thấy tài liệu -> 404
```

Đây là kết quả có chủ ý của ví dụ. Một số sản phẩm cố tình trả 404 thay cho 403 để tránh tiết lộ sự tồn tại của tài nguyên, nhưng đó phải là policy được phê duyệt và test nhất quán; không nên để exception handler đổi tùy tiện.

### 5.5. Case E: lỗi 404/500 biến thành 403 khi dispatch `/error`

Một request đã được quyền truy cập có thể phát sinh exception khiến container thực hiện `DispatcherType.ERROR` để render phản hồi lỗi. Nếu `AuthorizationFilter` cũng từ chối error dispatch (do rule `anyRequest().denyAll()`), lỗi gốc có thể bị che bởi lỗi phân quyền mới. Bởi vậy ví dụ cho phép `DispatcherType.ERROR`, thay vì chỉ cho phép request ban đầu. Trong ứng dụng thực cần xem thêm FORWARD/ASYNC dispatch nếu dùng các cơ chế đó, và test các đường lỗi có auth/anonymous.

## 6. Hai cách chuẩn hóa error body mà vẫn giữ status

### Lựa chọn 1 — để Security xử lý 401/403, MVC xử lý domain errors

Đây là cách đã dùng trong ví dụ:

- `AuthenticationEntryPoint`: thiếu hoặc sai auth → status 401, thêm challenge phù hợp.
- `AccessDeniedHandler`: đã xác thực nhưng không có quyền → status 403.
- `@RestControllerAdvice` cho not-found/validation → 404/400 theo nghiệp vụ.
- Lỗi hạ tầng không được biến thành 2xx; có error handler 5xx và logging/trace phù hợp.

Có thể dùng `ProblemDetail`, JSON cố định, hoặc error envelope của tổ chức. Cốt lõi là **HTTP status thực**, `Content-Type` và trường `status` trong body không mâu thuẫn; không đưa stacktrace, path nhạy cảm hay lý do nội bộ vào phản hồi công khai.

### Lựa chọn 2 — custom entry point/denied handler cho từng authentication scheme

Một hệ thống có thể dùng nhiều scheme, ví dụ `/api/**` dùng Bearer token, `/admin/**` dùng form login. Khi đó:

- Mỗi `SecurityFilterChain` cần xác định đúng `securityMatcher` và thứ tự chain.
- OAuth2 Resource Server cung cấp `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler` để tạo challenge và mã lỗi phù hợp Bearer; tự viết handler phải bảo toàn các header/challenge đó.
- Form login có thể điều hướng đến trang login (`302`) theo contract UI, không tự ép `401 JSON` như API.
- Nếu request được ứng dụng xử lý **không qua SecurityFilterChain** (test standalone MVC hoặc adapter khác), không kỳ vọng bộ lọc security chuyển ngoại lệ.

**Không gắn `@ResponseStatus(403)` trên mọi `AccessDeniedException` như một giải pháp chung.** Nó không biết phân biệt anonymous/đã xác thực, không xử lý lỗi đăng nhập từ Basic/Bearer và có thể làm mất thông tin challenge.

## 7. Checklist kiểm thử các tầng bảo mật

| Tầng | Kiểm thử nên có | Điều được khẳng định |
| --- | --- | --- |
| Method security | Gọi Spring-managed service với user đủ/thiếu authority | `@PreAuthorize` thật sự bảo vệ business method |
| HTTP authentication | Anonymous, password/token sai hoặc hết hạn | `AuthenticationEntryPoint` trả 401/challenge theo scheme |
| HTTP authorization → method | HTTP URL matcher cho phép tới controller nhưng method từ chối | 401/403 đến từ method security, không phải bị HTTP chặn trước |
| HTTP authorization riêng | URL ngoài whitelist, role sai ở filter | SecurityFilterChain vẫn bảo vệ endpoint |
| MVC error handling | Business not-found/validation | 404/400, không bị security handler chiếm |
| Unexpected exception | Mô phỏng lỗi hệ thống thật | Giữ 5xx, không biến thành 2xx/403 |
| Output contract | Assert HTTP status **và** body status/headers | Không lệch mã trạng thái, không lộ chi tiết |
| Asynchronous/streaming | Exception xảy ra sau khi response commit | Có cơ chế ứng dụng riêng; không giả định có thể sửa status sau commit |

Đối với API có thao tác ghi, thêm test để chứng minh từ chối trước khi lưu DB/gửi message. Cẩn thận với `@PostAuthorize`: một phép kiểm tra sau khi method chạy có thể trả 403 **sau khi side effect đã xảy ra**; nếu đây là lệnh thay đổi trạng thái, ưu tiên đặt authorization ở giai đoạn trước và kiểm soát transaction/rollback đúng yêu cầu.

Đối với resource-level security, ngoài `hasAuthority` còn phải test ownership như `@PreAuthorize("@documentPolicy.canRead(authentication, #id)")` với user sở hữu/không sở hữu tài nguyên. Chính sách đó phụ thuộc business code nên cần cung cấp `documentPolicy` bean thực và kiểm thử đường từ controller đến proxy, không dừng ở status mock cố định.

## 8. Sai lầm cần tránh khi viết test

1. **MockMvc không nối SecurityFilterChain.** `MockMvcBuilders.standaloneSetup(...)` chỉ tạo MVC đơn lẻ; nếu không bổ sung `springSecurity()`/filter, status test 401/403 không đại diện ứng dụng thật. Với ví dụ sử dụng `@SpringBootTest + @AutoConfigureMockMvc`, filter được cấu hình trong context.
2. **Service bị mock mất logic `@PreAuthorize`.** Nếu mock cả bean đã được AOP bảo vệ, interceptor thực có thể không còn tham gia như production. Dùng service bean thật hoặc bố trí mock ở dependency bên dưới service.
3. **`@WithMockUser` cho bài test “anonymous”.** Annotation này chủ động gắn user đã xác thực, không phù hợp để kiểm tra nhánh 401 từ anonymous.
4. **Chỉ assert body JSON có `status=403`.** Server vẫn có thể trả HTTP 200. Phải assert `status().isForbidden()` cùng body.
5. **Chỉ assert 403 mà không kiểm tra 200.** Một cấu hình deny-all cũng làm ca âm tính pass; có positive test với quyền đúng để chứng minh route vận hành.
6. **Test chỉ ở URL layer.** Nếu HTTP matcher chặn trước, chưa chứng minh `@PreAuthorize` có tác dụng. Dùng route `permitAll` có kiểm soát để kiểm tra service, hoặc unit test method proxy riêng.
7. **Catch mọi exception trong Advice** rồi biến thành 500. Đây là một trong những nguyên nhân chính làm mất tín hiệu 401/403 của method security.
8. **Nhầm `hasRole("ADMIN")` với `hasAuthority("ADMIN")`.** `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`; authority của ví dụ dùng tên đầy đủ `document:read`, nên kiểm tra `hasAuthority("document:read")`.
9. **Không kiểm tra dispatcher error / multi-chain.** Status 404/500 có thể bị quy tắc URL ở dispatch hoặc chain khác thay đổi.
10. **Kỳ vọng mọi exception tự động thành 401/403.** Lỗi nghiệp vụ và lỗi lập trình không phải `AccessDeniedException`/`AuthenticationException`; mapping phải đúng class và đúng tầng.
11. **Quên phản hồi đã commit.** Nếu đã stream body, handler không thể đáng tin cậy thay status; thiết kế authorization trước khi tạo response.
12. **Không giới hạn thông tin trong body/log.** Nội dung exception bảo mật có thể chứa thông tin policy; chỉ xuất thông điệp an toàn và correlation ID, lưu chi tiết ở log có kiểm soát.

## 9. Bài tập mở rộng có thể áp dụng ngay

### 9.1. Cố tình thêm Advice lỗi rồi dùng test phát hiện

Tạm thêm đoạn code `@ExceptionHandler(Exception.class)` trả `ResponseEntity.status(500)`. Chạy lại các ca test anonymous/thiếu authority: các ca đã dựa trên propagation của method security phải phát hiện status bị đổi thành 500. Xóa handler đó, thay bằng handler hẹp cho từng lỗi nghiệp vụ và chạy lại test. Đây là một **thí nghiệm có kiểm soát trong code test**, không phải cấu hình nên giữ ở production.

### 9.2. Đổi từ Basic sang Bearer token

Thay `httpBasic` bằng cấu hình Resource Server/JWT đúng cho dự án, rồi kiểm tra: token thiếu/không hợp lệ → 401 với `WWW-Authenticate: Bearer ...`; token hợp lệ thiếu scope → 403 và challenge/chi tiết phù hợp; token hợp lệ đủ scope → 200; entity vắng → 404. Không copy handler Basic của ví dụ sang môi trường Bearer.

### 9.3. Bổ sung ownership và side-effect

Dùng hai người dùng cùng `document:read` nhưng tài liệu thuộc chủ khác, test `@PreAuthorize` theo `documentId` và `Authentication`. Với endpoint update, assert DB không đổi sau 403; xác minh rằng logic kiểm tra chạy trước mutation và rằng các kết quả bất ngờ không bị wrapper `ResponseEntity.ok(...)` che đi.

## 10. Tài liệu đối chiếu

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, interceptor và exception khi denied.
- [Spring Security — Servlet Architecture / Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html): vị trí `ExceptionTranslationFilter` và cách phân nhánh authentication/authorization.
- [Spring Security — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): `AuthenticationEntryPoint` và `AccessDeniedHandler`.
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matcher, thứ tự và `DispatcherType.ERROR`.
- [Spring Framework — MVC Exception Handling](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html): `@ExceptionHandler`, `@ControllerAdvice` và resolver.
- [Spring Security — Spring MVC Test Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/): test với `MockMvc` và bộ lọc security.

**Tiêu chí hoàn thành:** Khi quyền bị từ chối tại **service/method**, lớp web phải phân biệt đúng **401 cho anonymous hoặc credential sai**, **403 cho người đã xác thực nhưng không đủ quyền**, và vẫn bảo toàn **404/400/500** của các loại lỗi khác. Test phải kiểm tra HTTP status, headers, error body và đường đi qua method-security proxy, thay vì chỉ nhìn message ngoại lệ.