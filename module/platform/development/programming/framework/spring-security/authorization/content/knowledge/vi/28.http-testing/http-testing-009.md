# Kiểm thử FORWARD, ERROR, ASYNC và endpoint xử lý lỗi trong Spring Security (Servlet)

> Phạm vi: kiểm thử **ủy quyền HTTP** của ứng dụng Spring MVC chạy trên Servlet với Spring Security. Các ví dụ dùng Java 17+, Spring Boot 3.x và Spring Security 6.x (`jakarta.servlet`). Đây là bài kiểm thử phía **Servlet**, không áp dụng nguyên xi cho WebFlux.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt một HTTP request từ client với các lần **dispatch nội bộ** (`REQUEST`, `FORWARD`, `ERROR`, `ASYNC`).
2. Giải thích khi nào `SecurityFilterChain` và `AuthorizationFilter` được gọi ở lần dispatch tiếp theo.
3. Viết test chứng minh `FORWARD` không vô tình mở đường vào endpoint yêu cầu quyền cao hơn.
4. Viết test cho việc xử lý lỗi: endpoint gốc giữ đúng mã lỗi, `/error` hiển thị được trên `ERROR` nhưng không thành endpoint công khai khi gọi trực tiếp.
5. Kiểm thử đủ hai pha của Spring MVC async và sự hiện diện của `SecurityContext` khi chạy `Callable`.
6. Biết giới hạn của `MockMvc` và chọn kiểm thử với servlet container thật khi cần chứng minh hành vi end-to-end.

## 2. Hiểu đúng request và dispatcher type

Một kết nối HTTP bên ngoài có thể tạo nhiều lần đi qua servlet pipeline:

| `DispatcherType` | Khi nào xuất hiện | Điều cần kiểm thử |
| --- | --- | --- |
| `REQUEST` | Client gửi request đầu tiên | Xác thực và quyền của URL/HTTP method ban đầu |
| `FORWARD` | Ứng dụng gọi `RequestDispatcher.forward(...)` hoặc chuyển đến view nội bộ | Quyền của **đích forward** còn được bảo vệ không |
| `ERROR` | Container điều phối tới error page/`/error` sau lỗi hoặc `sendError` | Lỗi gốc có được render đúng, không bị thay bằng lỗi 401/403 mới |
| `ASYNC` | Servlet async hoàn tất và được dispatch lại để tạo response | Quyền và security context trong pha xử lý/phát lại response |
| `INCLUDE` | `RequestDispatcher.include(...)` | Nếu dùng include, cũng phải xác định quy tắc ủy quyền; không tự suy từ FORWARD |

Ví dụ các dòng xử lý, **không phải** ba HTTP request mới từ client:

```text
GET /demo/forward (REQUEST, có quyền USER)
  -> controller forward("/views/landing")
     -> /views/landing (FORWARD, kiểm tra quyền đích)
        -> HTTP 200

GET /demo/fail (REQUEST, có quyền USER)
  -> controller gửi lỗi 500
     -> /error (ERROR, hiển thị lỗi)
        -> HTTP 500 cho client

GET /demo/async (REQUEST, có quyền USER)
  -> controller trả Callable, request chuyển sang async
  -> Callable chạy ở thread khác
  -> /demo/async (ASYNC dispatch, hoàn tất response)
     -> HTTP 200
```

Cần phân biệt **hai lớp cấu hình**:

- **Đăng ký servlet filter:** container chỉ gọi Spring Security filter cho những dispatcher type được đăng ký. Trong Spring Boot có thuộc tính `spring.security.filter.dispatcher-types`. Với các bản Boot 3.3–3.5, tài liệu thuộc tính mặc định liệt kê `request,error,async,forward,include`; tuy nhiên luôn kiểm tra phiên bản, cấu hình override và `FilterRegistrationBean` thật của hệ thống.
- **Quy tắc ủy quyền:** sau khi dispatch đã vào Spring Security, `authorizeHttpRequests(...)` và `dispatcherTypeMatchers(...)` quyết định permit/deny theo từng request. `AuthorizationFilter` được thiết kế để xét cả các dispatch tiếp theo. Việc viết matcher không thể tự bổ sung dispatcher type đang thiếu trong đăng ký servlet filter.

Thứ tự matcher có ý nghĩa: quy tắc **khớp đầu tiên** quyết định quyền. `dispatcherTypeMatchers(ERROR).permitAll()` đặt trước `anyRequest().denyAll()` cho phép dispatch lỗi đi tiếp; **GET /error từ trình duyệt vẫn có loại REQUEST** nên không được phép chỉ nhờ quy tắc ERROR.

**Cảnh báo ủy quyền:** mẫu `dispatcherTypeMatchers(FORWARD, ERROR).permitAll()` trong tài liệu Spring hữu ích khi toàn bộ forward chỉ phục vụ render view an toàn. Nếu ứng dụng có forward tới `/admin/**` hoặc endpoint nghiệp vụ nhạy cảm, `permitAll()` cho **mọi** FORWARD có thể bỏ qua kiểm tra URL đích. Hãy kiểm thử luồng thực tế và chỉ nới quyền trong phạm vi chứng minh được là an toàn; ví dụ dưới đây **không** cho phép mọi FORWARD.

## 3. Hợp đồng kiểm thử: điều gì được coi là PASS?

| Tình huống | Kỳ vọng |
| --- | --- |
| Ẩn danh gọi `GET /demo/forward` hoặc `/demo/async` | 401 trong cấu hình HTTP Basic mẫu |
| USER gọi `/demo/forward`, chuyển đến `/views/landing` | 200, body `VIEW_OK` |
| USER gọi `/demo/forward-admin`, đích là `/admin/report` | 403, **không trả** dữ liệu bí mật |
| USER gọi trực tiếp `/admin/report` | 403 |
| USER gọi `/demo/async` | Bắt đầu async; sau `asyncDispatch` có 200 và principal đúng |
| USER gọi `/demo/fail` | Response lỗi 500, `/error` render thông tin lỗi thay vì bị khóa nhầm |
| Ẩn danh gửi `GET /error` như request bình thường | 401 theo HTTP Basic và rule `denyAll` mẫu |
| Request giả lập với `DispatcherType.ERROR` tới `/error` | 500 theo status gốc, chứng minh rule ERROR cho phép xử lý |

Mã 401 chỉ là kỳ vọng của **ứng dụng mẫu sử dụng HTTP Basic**. Với form login, request chưa đăng nhập có thể trả 302; khi đã xác thực nhưng thiếu quyền thường là 403. Test phải dựa trên `AuthenticationEntryPoint`/`AccessDeniedHandler` thực tế, không gắn cứng 401 cho mọi cấu hình.

## 4. Ứng dụng mẫu để chạy test

Cần các dependency sau trong dự án Spring Boot đã cấu hình plugin/BOM tương thích:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Các class bên dưới dùng cùng package `com.example.dispatch`. Tạo entry point:

**`src/main/java/com/example/dispatch/DispatchDemoApplication.java`**

```java
package com.example.dispatch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DispatchDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DispatchDemoApplication.class, args);
    }
}
```

**`src/main/java/com/example/dispatch/SecurityConfig.java`**

```java
package com.example.dispatch;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                // Chỉ ERROR nội bộ được render không cần đăng nhập.
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                // Đích nhạy cảm phải giữ rule riêng, kể cả khi được forward tới.
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .requestMatchers("/demo/**", "/views/**").hasRole("USER")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
```

Không có `dispatcherTypeMatchers(FORWARD).permitAll()`. Nếu một USER cố forward vào `/admin/report`, đích vẫn yêu cầu vai trò ADMIN. `hasRole("USER")` tương ứng authority `ROLE_USER`; `hasRole("ADMIN")` tương ứng `ROLE_ADMIN`.

**`src/main/java/com/example/dispatch/DemoController.java`**

```java
package com.example.dispatch;

import java.io.IOException;
import java.util.concurrent.Callable;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class DemoController {
    @GetMapping("/demo/forward")
    public void forwardView(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        request.getRequestDispatcher("/views/landing").forward(request, response);
    }

    @GetMapping("/demo/forward-admin")
    public void forwardAdmin(HttpServletRequest request, HttpServletResponse response)
            throws ServletException, IOException {
        request.getRequestDispatcher("/admin/report").forward(request, response);
    }

    @GetMapping("/views/landing")
    public String landing() {
        return "VIEW_OK";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "TOP_SECRET";
    }

    @GetMapping("/demo/async")
    public Callable<String> async() {
        return () -> "ASYNC_OK:"
                + SecurityContextHolder.getContext().getAuthentication().getName();
    }

    @GetMapping("/demo/fail")
    public void fail() {
        throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Demo failure");
    }
}
```

`/demo/fail` dùng `ResponseStatusException` để tạo lỗi 500. Trong servlet container, `sendError` có thể dẫn đến dispatch `ERROR` cho error page mặc định của Spring Boot, thường ở `/error`. `@ExceptionHandler` trả `ResponseEntity` trực tiếp là **nhánh khác**: lỗi có thể đã được xử lý trong Spring MVC mà không có dispatch `ERROR`. Phải chọn ca kiểm thử phù hợp.

Để demo không phụ thuộc mặc định giữa các phiên bản Boot, khai báo rõ các loại dispatch cho filter:

**`src/main/resources/application.properties`**

```properties
spring.security.filter.dispatcher-types=request,error,async,forward,include
```

Đây là cấu hình servlet filter, **không phải** một `authorizeHttpRequests` rule. Trong ứng dụng thật, kiểm tra tất cả custom `FilterRegistrationBean`, `SecurityFilterChain`, `securityMatcher` và cách triển khai servlet container; không coi riêng dòng properties là bằng chứng an toàn.

Các user phục vụ test được cung cấp riêng, không đưa password thử nghiệm vào cấu hình production.

**`src/test/java/com/example/dispatch/TestUsers.java`**

```java
package com.example.dispatch;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@TestConfiguration(proxyBeanMethods = false)
class TestUsers {
    @Bean
    UserDetailsService testUsers() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}pw")
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password("{noop}pw")
                .roles("USER", "ADMIN")
                .build()
        );
    }
}
```

`{noop}` là cách lưu mật khẩu thuần văn bản **chỉ dành cho fixture test**, tuyệt đối không dùng cho tài khoản thực.

## 5. MockMvc: kiểm thử rule và vòng đời async

`MockMvc` rất nhanh để kiểm tra security rule và xử lý request trong Spring MVC. Tuy nhiên, nó chạy trên các servlet mock **không có container thật**. `forwardedUrl(...)` chỉ xác minh URL forward đã được yêu cầu; nó **không** chứng minh container đã thực thi forward tới handler đích hoặc áp dụng lại filter. Tương tự, MockMvc thường không tự thực hiện error-page dispatch sau `sendError`. Với async, cần gọi `asyncDispatch` một cách tường minh.

**`src/test/java/com/example/dispatch/DispatchSecurityMockMvcTest.java`**

```java
package com.example.dispatch;

import jakarta.servlet.DispatcherType;
import jakarta.servlet.RequestDispatcher;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.forwardedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestUsers.class)
class DispatchSecurityMockMvcTest {
    @Autowired
    MockMvc mvc;

    @Test
    void anonymousCannotReachProtectedSource() throws Exception {
        mvc.perform(get("/demo/forward"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void forwardedUrlIsRecordedButDestinationIsNotExecuted() throws Exception {
        mvc.perform(get("/demo/forward"))
            .andExpect(status().isOk())
            .andExpect(forwardedUrl("/views/landing"));

        // Không suy ra handler đích /views/landing đã chạy.
    }

    @Test
    @WithMockUser(roles = "USER")
    void simulatedForwardToAdminIsDenied() throws Exception {
        mvc.perform(get("/admin/report").with(req -> {
                req.setDispatcherType(DispatcherType.FORWARD);
                return req;
            }))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void asyncRequestCompletesWithTheExpectedPrincipal() throws Exception {
        MvcResult pending = mvc.perform(get("/demo/async"))
            .andExpect(request().asyncStarted())
            .andReturn();

        mvc.perform(asyncDispatch(pending))
            .andExpect(status().isOk())
            .andExpect(content().string("ASYNC_OK:alice"));
    }

    @Test
    void directRequestToErrorEndpointIsNotPublic() throws Exception {
        mvc.perform(get("/error"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void simulatedErrorDispatchCanRenderTheOriginal500() throws Exception {
        mvc.perform(get("/error").with(req -> {
                req.setDispatcherType(DispatcherType.ERROR);
                req.setAttribute(RequestDispatcher.ERROR_STATUS_CODE,
                    HttpStatus.INTERNAL_SERVER_ERROR.value());
                req.setAttribute(RequestDispatcher.ERROR_REQUEST_URI, "/demo/fail");
                return req;
            }))
            .andExpect(status().isInternalServerError());
    }
}
```

Giải thích các assertion quan trọng:

- `@AutoConfigureMockMvc` trong `@SpringBootTest` dùng filter chain của context; `spring-security-test` cung cấp `@WithMockUser` và request post-processors. Nếu dựng `MockMvcBuilders` thủ công, cần tích hợp `springSecurity()` hoặc filter chain thích hợp.
- `with(req -> req.setDispatcherType(FORWARD))` tạo **một mock request có loại FORWARD** để kiểm tra matcher. Nó không tạo forward thật từ URL nguồn, và không chứng minh servlet mapping đã gọi filter trong container.
- `asyncStarted()` xác nhận handler trả về xử lý bất đồng bộ; `asyncDispatch(pending)` thực hiện pha hoàn tất. Chỉ assert 200 trên request đầu là thiếu.
- `SecurityContextHolder` trong `Callable` có username `alice` là chứng cứ context được truyền sang thread thực thi. Spring Security hỗ trợ tích hợp `Callable` của Spring MVC; với `DeferredResult` do thread ứng dụng tự hoàn tất thì việc truyền context **không tự động tương đương**, cần cơ chế phù hợp như `DelegatingSecurityContextExecutor` và test riêng.
- `RequestDispatcher.ERROR_STATUS_CODE` là thuộc tính của error dispatch; chỉ gọi `GET /error` **không** đại diện cho `ERROR` vì mặc định nó vẫn là `REQUEST`.
- Nếu muốn test POST/PUT/DELETE có CSRF mặc định, thêm `.with(csrf())` cho request hợp lệ và một test CSRF thiếu/sai token; không vô hiệu hóa CSRF chỉ để test xanh.

## 6. Servlet container thật: chứng minh forward/error/async end-to-end

Đây là phần test bổ sung **bắt buộc khi cần kết luận về ủy quyền trên FORWARD và ERROR thực sự**. Chạy server với cổng ngẫu nhiên; `TestRestTemplate` gửi HTTP từ bên ngoài, còn Tomcat/Jetty/Undertow xử lý dispatcher mapping bên trong.

**`src/test/java/com/example/dispatch/DispatchSecurityHttpTest.java`**

```java
package com.example.dispatch;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Import(TestUsers.class)
class DispatchSecurityHttpTest {
    @Autowired
    TestRestTemplate http;

    @Test
    void forwardToSafeViewSucceeds() {
        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .getForEntity("/demo/forward", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("VIEW_OK");
    }

    @Test
    void forwardMustNotBypassAdminAuthorization() {
        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .getForEntity("/demo/forward-admin", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(response.getBody()).doesNotContain("TOP_SECRET");
    }

    @Test
    void authorizedAdminCanReachForwardDestination() {
        ResponseEntity<String> response = http.withBasicAuth("admin", "pw")
            .getForEntity("/demo/forward-admin", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("TOP_SECRET");
    }

    @Test
    void asyncDispatchCompletesAndRetainsIdentity() {
        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .getForEntity("/demo/async", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("ASYNC_OK:reader");
    }

    @Test
    void errorDispatchPreserves500InsteadOfSecurityFailure() {
        HttpHeaders headers = new HttpHeaders();
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));

        ResponseEntity<String> response = http.withBasicAuth("reader", "pw")
            .exchange("/demo/fail", HttpMethod.GET,
                new HttpEntity<Void>(headers), String.class);

        assertThat(response.getStatusCode())
            .isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(response.getBody()).contains("\"status\":500");
    }

    @Test
    void directErrorUrlIsStillDenied() {
        ResponseEntity<String> response = http
            .getForEntity("/error", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.UNAUTHORIZED);
    }
}
```

Các test này phân biệt rất rõ:

- `GET /demo/forward` phải nhận **body của handler đích**, không chỉ tên forward. Test `forward-admin` là test chống truy cập vượt quyền; test trực tiếp `GET /admin/report` một mình chưa đủ vì không xác minh đường đi FORWARD.
- `GET /demo/fail` phải có lỗi 500 kèm JSON lỗi của `/error`. Nếu filter chặn dispatch lỗi, trạng thái/body có thể khác; nên xét cả **body, status, log và dispatcher type** khi debug.
- `GET /error` gửi từ client là REQUEST và bị chặn. Cho phép render lỗi nội bộ không đồng nghĩa public endpoint.
- `GET /demo/async` trả body chứa identity từ `Callable`, giúp phát hiện mất security context trong thread xử lý.

Chạy test bằng Gradle wrapper của dự án đã tạo:

```bash
./gradlew test --tests '*DispatchSecurityMockMvcTest' --tests '*DispatchSecurityHttpTest'
```

Trên Windows PowerShell/cmd:

```powershell
.\gradlew.bat test --tests '*DispatchSecurityMockMvcTest' --tests '*DispatchSecurityHttpTest'
```

Các ví dụ trên là fixture độc lập về **mã ứng dụng/test**, còn build cần cấu hình Spring Boot plugin, repository và dependency management của dự án. Chỉ coi test PASS khi đã chạy trên dependency versions/container thực tế; không diễn giải code mẫu như bằng chứng đã thực thi trong môi trường của bạn.

## 7. Trường hợp mở rộng cần phân biệt

### 7.1. Khi controller có `@ControllerAdvice` hoặc `@ExceptionHandler`

Một `@ExceptionHandler` bắt lỗi và trả `ResponseEntity.status(500)...` có thể giải quyết response ngay trên `REQUEST`, **không cần** container ERROR dispatch. Test của đường xử lý này nên assert HTTP status, nội dung lỗi, không rò rỉ exception/stack trace và quyền truy cập endpoint. Để kiểm tra `DispatcherType.ERROR`, phải tạo điều kiện dẫn đến `sendError` hoặc error dispatch container thật, hoặc tạo mock ERROR có chủ đích.

### 7.2. Khi yêu cầu bất đồng bộ gặp lỗi

`Callable` ném exception và `DeferredResult.setErrorResult(...)` thường được Spring MVC xử lý trong pha async redispatch; lỗi có thể đi qua `@ExceptionHandler` hoặc gửi tới container error page tùy cách xử lý. Test **cả** `asyncStarted()`, `asyncDispatch(...)`, status/body lỗi, và quyền truy cập. Nếu app tự tạo thread/`CompletableFuture`/`DeferredResult`, đừng giả định `SecurityContextHolder` (thường dựa trên ThreadLocal) tự lan truyền; hãy truyền context an toàn và xác minh trong test.

### 7.3. Khi có nhiều `SecurityFilterChain`

`securityMatcher(...)` chọn **chuỗi filter** áp dụng; `requestMatchers(...)` bên trong chỉ chọn **rule** của chuỗi đó. Mỗi lần dispatch có thể có URI/path khác hoặc matching khác. Cần xác nhận lần REQUEST và lần FORWARD/ERROR/ASYNC khớp chuỗi filter dự định. Cấu hình `web.ignoring()` hoặc loại một đường dẫn khỏi filter chain làm mất các bảo vệ khác; ưu tiên rule có phạm vi rõ ràng.

### 7.4. Khi dùng quy tắc permit cho FORWARD

Có thể cho phép FORWARD của một số view nội bộ đã xác định; tuy nhiên phải test **đích nhạy cảm**, không dùng `dispatcherTypeMatchers(FORWARD).permitAll()` mặc định khi app có thể forward tới business API yêu cầu quyền cao hơn. Không cho rằng một request ban đầu đã qua ủy quyền thì mọi đích nội bộ sau đó đều có cùng độ nhạy.

### 7.5. Khi log hay test báo 401/403/500 không như dự kiến

Kiểm tra theo thứ tự:

1. Request thực tế mang `DispatcherType` gì; đó là request client hay internal dispatch?
2. Servlet container có gọi Spring Security filter trên type ấy không (`spring.security.filter.dispatcher-types` và filter registration)?
3. `SecurityFilterChain` nào được chọn; matcher nào khớp **đầu tiên**?
4. Principal/authorities còn tồn tại ở pha dispatch/worker thread không?
5. Lỗi đã được MVC resolver xử lý hay đã được gửi tới `/error`? Có error dispatch lặp không?
6. Cơ chế đăng nhập dùng HTTP Basic, form login, bearer token hay custom entry point? Từ đó mới xác định 401, 302 hay 403 kỳ vọng.

Có thể bật `logging.level.org.springframework.security=DEBUG` **trong môi trường test** để đối chiếu filter chain và quyết định truy cập; quan sát thêm request URI, dispatcher type, response status mà không log credential/token.

## 8. Checklist trước khi kết luận hoàn tất

- [ ] Test REQUEST cho anonymous, USER và ADMIN theo đúng rule.
- [ ] Test FORWARD tới view bình thường **và** forward vào endpoint nhiều quyền hơn; khẳng định dữ liệu bí mật không bị lộ.
- [ ] Không nhầm `forwardedUrl` của MockMvc với việc container đã thực sự chạy đích.
- [ ] Test ERROR bằng dispatcher type/attributes đúng; kiểm tra `/error` trên REQUEST riêng.
- [ ] Test status **và body** cho lỗi thật, tránh một 401/403 ở error page che mất lỗi gốc.
- [ ] Test hai pha `asyncStarted` → `asyncDispatch`, body cuối và principal trong `Callable`.
- [ ] Nếu dùng `DeferredResult`/thread tự tạo, test cả cách truyền `SecurityContext`.
- [ ] Xác minh filter dispatcher mapping và thứ tự authorization matcher trên phiên bản Boot/Security đang dùng.
- [ ] Có ít nhất một kiểm thử HTTP với embedded servlet container cho luồng FORWARD/ERROR thật.

## 9. Nguồn tham khảo chính thức

- Spring Security — Authorize HttpServletRequests (authorization theo dispatcher type): https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Boot — Common Application Properties (`spring.security.filter.dispatcher-types`): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Framework — MockMvc vs End-to-End Tests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/vs-end-to-end-integration-tests.html
- Spring Framework — Test Async Requests: https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/async-requests.html
- Spring Security — Spring MVC Async Integration: https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html

**Tiêu chí đạt:** người học có thể chứng minh bằng test thực thi rằng một REQUEST hợp lệ không mở đường FORWARD vào endpoint nhạy cảm, ERROR dispatch giữ đúng lỗi, còn ASYNC hoàn tất với identity và quyền mong đợi.