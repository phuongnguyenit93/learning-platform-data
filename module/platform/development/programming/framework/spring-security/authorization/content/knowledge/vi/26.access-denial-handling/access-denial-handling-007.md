# Phân biệt AccessDeniedException với lỗi CSRF hoặc lỗi nghiệp vụ

> Phạm vi: **Spring Security Authorization trên Servlet stack**, HTTP request và Spring MVC (đặc biệt Spring Security 6.x với Spring Boot 3.x). Bài này tập trung vào **nguyên nhân bị từ chối, nơi phát sinh, nơi xử lý và cách trả lỗi đúng**. Với WebFlux, WebSocket/STOMP hoặc hệ thống gateway, tên thành phần xử lý và đường đi của lỗi có thể khác.

## 1. Điều cần hiểu trước

Khi một API trả `403 Forbidden`, không thể kết luận ngay rằng người dùng “thiếu quyền”. Có ít nhất ba nguyên nhân cần phân biệt:

1. **Từ chối phân quyền (authorization denial):** người dùng đã được nhận diện nhưng không có authority/role/quyền trên tài nguyên cần thao tác. Tầng Spring Security có thể phát sinh `AccessDeniedException`.
2. **CSRF không hợp lệ:** request cần bảo vệ CSRF nhưng token thiếu hoặc không hợp lệ. `CsrfFilter` phát sinh `CsrfException`, điển hình là `MissingCsrfTokenException` hoặc `InvalidCsrfTokenException`.
3. **Quy tắc nghiệp vụ không thỏa:** request đã qua xác thực, CSRF và các chính sách phân quyền nhưng không thể hoàn thành vì trạng thái nghiệp vụ, chẳng hạn hết hàng, đơn đã khóa, chuyển trạng thái không hợp lệ. Service/controller thường phát sinh exception riêng của miền nghiệp vụ.

**Điểm mấu chốt về kiểu exception:** `CsrfException extends AccessDeniedException`. Vì vậy “lỗi CSRF” và “ngoại lệ thuộc lớp `AccessDeniedException`” **không phải hai tập loại trừ nhau**. Muốn phân loại đúng, phải xét **subtype và nguồn phát sinh**, thay vì dùng `exception instanceof AccessDeniedException` để coi tất cả là lỗi phân quyền.

Mục tiêu sau bài:

- Phân biệt `AuthenticationException`, `AccessDeniedException`, các subclass CSRF và exception nghiệp vụ.
- Giải thích hành vi của `CsrfFilter`, `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler` và `@RestControllerAdvice`.
- Chọn `401`/`403`/`409`/`422`/`400` phù hợp theo ngữ nghĩa, không đoán nguyên nhân chỉ bằng HTTP status.
- Cấu hình một API demo trả mã lỗi phân biệt được, rồi kiểm thử từng tình huống bằng `MockMvc`.

## 2. Nhìn theo ba chiều: loại lỗi, nơi phát sinh, nơi xử lý

| Tình huống | Loại exception thường gặp | Nơi phát sinh | Nơi xử lý điển hình | HTTP response điển hình |
| --- | --- | --- | --- | --- |
| Chưa đăng nhập hoặc token đăng nhập sai/hết hạn | `AuthenticationException` và các subclass | Authentication filter/provider | `AuthenticationEntryPoint` hoặc cơ chế authentication failure | `401` cho REST; có thể redirect đến login với website |
| Đã đăng nhập nhưng thiếu role/authority tại URL | `AccessDeniedException` / `AuthorizationDeniedException` | `AuthorizationFilter` (hoặc cơ chế authorization tương ứng) | `ExceptionTranslationFilter` → `AccessDeniedHandler` | `403` |
| Thiếu quyền tại `@PreAuthorize`, `@PostAuthorize` hay method security | Exception thuộc họ `AccessDeniedException` | Method-security interceptor | Có thể truyền ngược qua web security chain đến handler nếu không bị xử lý trước | Thường `403` với user đã xác thực |
| POST/PUT/PATCH/DELETE cần CSRF nhưng token không hợp lệ | `CsrfException` (subclass `AccessDeniedException`) | `CsrfFilter` | `AccessDeniedHandler` do CSRF filter sử dụng | Thường `403` |
| Đơn hàng đã thanh toán, hết tồn kho, xung đột trạng thái | Exception nghiệp vụ do ứng dụng định nghĩa | Service/domain model | `@RestControllerAdvice`/`@ExceptionHandler` | Có thể `409` hoặc `422` tùy hợp đồng API |
| Payload thiếu trường, không hợp lệ về định dạng | `MethodArgumentNotValidException`, lỗi chuyển đổi dữ liệu | Spring MVC validation/binding | MVC exception resolver/advice | Thường `400` |

Bảng nói “điển hình” vì HTTP status cuối cùng còn phụ thuộc cấu hình authentication, handler, policy và cách ứng dụng ánh xạ lỗi. **Không có quy tắc “mọi `AccessDeniedException` đều là 403”**: nếu người dùng chưa xác thực đầy đủ, `ExceptionTranslationFilter` có thể chuyển sang `AuthenticationEntryPoint`.

### Sơ đồ thứ tự xử lý HTTP Servlet

~~~text
HTTP request
   │
   ▼
Spring Security FilterChainProxy
   │
   ├─ Authentication filters
   │      └─ Xác thực thất bại → AuthenticationEntryPoint/failure handler
   │
   ├─ CsrfFilter
   │      ├─ HTTP method cần CSRF + token sai/thiếu
   │      │      → CsrfException (is-a AccessDeniedException)
   │      │      → AccessDeniedHandler → thường 403
   │      └─ Token hợp lệ / không cần kiểm tra → đi tiếp
   │
   └─ ExceptionTranslationFilter
          └─ downstream AuthorizationFilter / DispatcherServlet
                  ├─ URL/method security từ chối
                  │      → AccessDeniedException
                  │      → nếu anonymous/chưa xác thực đầy đủ:
                  │           AuthenticationEntryPoint
                  │        nếu đã xác thực:
                  │           AccessDeniedHandler → thường 403
                  │
                  └─ Controller → Service
                         ├─ nghiệp vụ thành công → 2xx
                         └─ exception nghiệp vụ
                                → MVC @ExceptionHandler → 4xx/5xx theo API
~~~

Sơ đồ này khái quát một filter chain thông thường. Thứ tự filter và việc cấu hình nhiều `SecurityFilterChain` có thể ảnh hưởng đường đi cụ thể. `CsrfFilter` tự chuyển lỗi token đến handler của nó; không nên giả định mọi lỗi CSRF phải được ném xuyên qua `ExceptionTranslationFilter`.

## 3. Phân biệt AccessDeniedException với AuthenticationException

### 3.1 Authentication: “Bạn là ai?”

`AuthenticationException` thể hiện vấn đề xác thực: chưa có credentials cần thiết, credentials không hợp lệ, phiên không còn hiệu lực, bearer token sai... Một REST API thường trả `401 Unauthorized` với thông tin cách xác thực tương ứng. Với form login, `AuthenticationEntryPoint` có thể điều hướng `302` sang trang đăng nhập.

### 3.2 Authorization: “Bạn có quyền làm việc này không?”

`AccessDeniedException` thuộc giai đoạn quyết định quyền. Một user có authority `ROLE_USER` gọi `GET /api/admin/report` được yêu cầu `ROLE_ADMIN` sẽ bị từ chối dù user đã đăng nhập thành công.

Trong Spring Security, `ExceptionTranslationFilter` là cầu nối giữa exception và HTTP response; nó **không tự đưa ra quyết định phân quyền**. Trong trường hợp phổ biến:

- Khi nhận `AuthenticationException`, nó bắt đầu quy trình authentication thông qua `AuthenticationEntryPoint`.
- Khi nhận `AccessDeniedException` của request chưa xác thực đầy đủ (bao gồm anonymous và tùy tình huống remember-me), nó bắt đầu authentication.
- Khi nhận `AccessDeniedException` của principal đã được xác thực đầy đủ, nó gọi `AccessDeniedHandler`. Mặc định kết quả thường là `403`.

Ví dụ rule:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .requestMatchers("/api/orders/**").authenticated()
    .anyRequest().denyAll()
);
~~~

Đây là **đoạn cấu hình**, chưa phải class Java độc lập. `hasRole("ADMIN")` mặc định đối chiếu authority `ROLE_ADMIN`; khác với `hasAuthority("ADMIN")`. `authenticated()` xác nhận đã đăng nhập nhưng không kiểm tra quyền nghiệp vụ trên từng đơn hàng.

**Lưu ý về quyền trên dữ liệu:** nếu user đăng nhập hợp lệ nhưng cố đọc đơn hàng của người khác, đó có thể là một **lỗi phân quyền đối tượng**, dù việc kiểm tra được thực hiện trong service. Nên biểu diễn và xử lý theo policy bảo mật; đừng tùy tiện đổi thành “lỗi nghiệp vụ” chỉ vì nó phát sinh sau khi vào controller. Một số API cố ý trả 404 để không tiết lộ sự tồn tại của tài nguyên; đó phải là quyết định thiết kế nhất quán.

## 4. CSRF: vì sao vẫn liên quan AccessDeniedException?

CSRF (Cross-Site Request Forgery) khai thác trường hợp trình duyệt tự gắn credentials như cookie phiên vào request do trang khác khởi tạo. Spring Security bảo vệ các request có nguy cơ thay đổi trạng thái bằng việc yêu cầu token mà trang độc hại không được phép lấy/đọc. Mặc định với Servlet:

- Các phương thức `GET`, `HEAD`, `OPTIONS`, `TRACE` được xem là an toàn và thường không yêu cầu CSRF token.
- Các phương thức như `POST`, `PUT`, `PATCH`, `DELETE` được kiểm tra CSRF nếu không có ngoại lệ được cấu hình.
- Nếu token thiếu hoặc không khớp, `CsrfFilter` kết thúc request bằng `AccessDeniedHandler`. Request chưa đến endpoint nghiệp vụ.

Quan hệ kế thừa:

~~~text
RuntimeException
   └─ AccessDeniedException
        ├─ AuthorizationDeniedException (trong những luồng authorization)
        └─ CsrfException
             ├─ MissingCsrfTokenException
             └─ InvalidCsrfTokenException
~~~

Các lớp CSRF nằm ở package `org.springframework.security.web.csrf`. Phân biệt ý nghĩa chung:

- `MissingCsrfTokenException`: quá trình bảo vệ không tìm thấy token được kỳ vọng ở kho lưu trữ trong tình huống tương ứng.
- `InvalidCsrfTokenException`: token gửi lên không khớp kỳ vọng (có thể bao gồm trường hợp không gửi header nhưng token kỳ vọng đã tồn tại). Đừng chỉ dựa vào tên subclass để suy luận chắc chắn “frontend thiếu header” hay “token quá hạn”; cần quan sát request, session, repository và cấu hình request handler.
- `CsrfException` là lớp cha chung để có thể phân loại đúng lỗi CSRF, bất kể dạng cụ thể.

Ví dụ người dùng đã đăng nhập, gửi `POST /api/orders/checkout`:

~~~text
Cookie: JSESSIONID=...
POST /api/orders/checkout
(no X-CSRF-TOKEN / X-XSRF-TOKEN header)
                 │
                 ▼
CsrfFilter: token missing/invalid
                 │
                 ▼
AccessDeniedHandler: HTTP 403 (CSRF_REJECTED)
                 │
                 └─ Controller và logic nghiệp vụ không chạy
~~~

Điểm cần nhớ: **status 403 của CSRF và 403 do thiếu role có thể giống hệt nhau**. Việc nhận biết phải dựa vào subtype exception (nếu có quyền quan sát), cấu hình security và đường đi request.

Ở Spring Security Servlet, `CsrfConfigurer` có thể dùng `AccessDeniedHandler` cấu hình qua `exceptionHandling`; đoạn demo bên dưới tận dụng cơ chế đó để trả mã lỗi khác nhau. Nếu dự án có nhiều filter chain, handler CSRF tùy biến hoặc invalid-session strategy riêng, phải kiểm tra chain nào thực sự bắt request.

### CSRF có phải luôn cần cho REST API?

Không. Rủi ro phụ thuộc **cách trình duyệt gửi credential**: cookie/session dễ bị tự động gửi; bearer token do JavaScript chủ động đặt trong `Authorization` header có threat model khác. Tuy vậy, không được suy ra “REST là vô trạng thái nên tắt CSRF” hoặc “dùng JWT nên chắc chắn không có CSRF”; nếu JWT nằm trong cookie tự gửi, CSRF vẫn có thể là vấn đề. Chỉ thay đổi cấu hình CSRF sau khi hiểu rõ frontend, session/cookie và phương thức xác thực.

## 5. Lỗi nghiệp vụ: request đã được chấp nhận về bảo mật nhưng thao tác không thể thực hiện

Một ví dụ: user được phép mua hàng, cung cấp CSRF token hợp lệ, nhập dữ liệu hợp lệ, nhưng kho không còn đủ số lượng. Đây là xung đột trạng thái nghiệp vụ, không phải thiếu `ROLE_ADMIN` hay token CSRF.

Nên định nghĩa exception/response cho miền nghiệp vụ, ví dụ `OutOfStockException` → `409 Conflict` với `code=OUT_OF_STOCK`. Ứng dụng khác có thể chọn `422 Unprocessable Content` cho một số vi phạm semantic; hãy công bố quy tắc thống nhất trong API contract. Các lỗi không tìm thấy tài nguyên thường dùng `404`, còn validation cú pháp/trường dữ liệu thường dùng `400`.

Không nên:

- Throw `AccessDeniedException` chỉ vì lượng hàng không đủ, rồi trả 403.
- Throw `OutOfStockException` khi user thực tế không có quyền đọc kho (đó là sai ngữ nghĩa và có thể rò rỉ thông tin).
- Bắt `Exception` tổng quát rồi biến mọi lỗi thành 403/400. Lỗi chương trình và hạ tầng có thể cần 500; lỗi bảo mật cần đi đúng nhánh xử lý.

Phân biệt “không có quyền” và “không đủ điều kiện nghiệp vụ” qua **mô hình quyền và quy tắc miền nghiệp vụ**, chứ không đơn thuần bằng việc exception xảy ra trong controller hay service.

## 6. Ví dụ hoàn chỉnh: cùng API, ba kết quả từ chối khác nhau

Ví dụ dưới dùng **Java 17+**, một dự án Spring Boot 3.x (Spring Security 6.x), các dependency thông thường:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- Cho phần kiểm thử: `spring-boot-starter-test` và `spring-security-test`

Các file Java sau đặt tại `src/main/java/example/denial/` (package trùng đường dẫn). Sử dụng session và CSRF mặc định; demo không cấu hình login form hoặc bearer token, mà kiểm thử bằng security test principal. Khi tích hợp thực tế, ứng dụng cần cấu hình cơ chế đăng nhập/xác thực riêng.

### 6.1 Entry point của ứng dụng

**DenialDemoApplication.java**

~~~java
package example.denial;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DenialDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DenialDemoApplication.class, args);
    }
}
~~~

### 6.2 Phân quyền và phân loại lỗi bảo mật

**SecurityConfig.java**

~~~java
package example.denial;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfException;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, ObjectMapper json) throws Exception {

        http
            .csrf(Customizer.withDefaults())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/orders/checkout")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, exception) ->
                    writeError(response, json, 401, "AUTHENTICATION_REQUIRED")
                )
                .accessDeniedHandler((request, response, exception) -> {
                    String code = (exception instanceof CsrfException)
                        ? "CSRF_REJECTED" : "ACCESS_DENIED";
                    writeError(response, json, 403, code);
                })
            );

        return http.build();
    }

    private static void writeError(
            HttpServletResponse response,
            ObjectMapper json,
            int status,
            String code) throws IOException {

        response.setStatus(status);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        json.writeValue(response.getOutputStream(), Map.of("code", code));
    }
}
~~~

Giải thích:

- `requestMatchers(...).hasRole("ADMIN")` quyết định quyền truy cập URL. User đã đăng nhập nhưng thiếu role sẽ qua nhánh `AccessDeniedHandler` với `code=ACCESS_DENIED`.
- `csrf(Customizer.withDefaults())` bật cấu hình bảo vệ mặc định. Một POST không có token hợp lệ bị `CsrfFilter` chặn **trước controller**; handler nhận subclass `CsrfException` và trả `code=CSRF_REJECTED`.
- `AuthenticationEntryPoint` trả `401` cho request cần xác thực mà chưa có principal hợp lệ trong bối cảnh demo. Từng loại cơ chế xác thực có thể trả 401 hoặc chuyển hướng login khác nhau.
- Việc dùng `instanceof CsrfException` phải đứng **trước phép phân loại chung `AccessDeniedException`** về mặt ý nghĩa; nếu chỉ kiểm tra lớp cha sẽ gộp nhầm CSRF vào lỗi thiếu quyền.
- API trả mã lỗi công khai ổn định, không đưa chi tiết exception, token, cookie, quyền nội bộ hoặc stack trace vào response.

**Quan trọng:** Đây là một cấu hình SecurityFilterChain có chủ đích cho bài học; với project đang có nhiều chain hoặc custom handler, cần gắn cùng chính sách vào đúng chain trước khi kết luận response sẽ giống demo.

### 6.3 Controller và exception nghiệp vụ

**OrderController.java**

~~~java
package example.denial;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.Map;

@RestController
class OrderController {

    @GetMapping("/api/admin/report")
    String adminReport() {
        return "report-ok";
    }

    @PostMapping("/api/orders/checkout")
    String checkout() {
        throw new OutOfStockException();
    }
}

class OutOfStockException extends RuntimeException {
}

@RestControllerAdvice
class BusinessErrorAdvice {

    @ExceptionHandler(OutOfStockException.class)
    ResponseEntity<Map<String, String>> outOfStock(
            OutOfStockException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
            .body(Map.of("code", "OUT_OF_STOCK"));
    }
}
~~~

`checkout()` cố tình ném `OutOfStockException` để minh họa kết quả nghiệp vụ; một ứng dụng thật sẽ kiểm tra tồn kho trong service, xử lý giao dịch và idempotency theo yêu cầu. `BusinessErrorAdvice` là thành phần Spring MVC, chỉ xử lý lỗi đi đến pha MVC. Nó không có nhiệm vụ thay thế CSRF/security filter.

### 6.4 Kiểm thử ranh giới bằng MockMvc

**src/test/java/example/denial/DenialDemoApplicationTests.java**

~~~java
package example.denial;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class DenialDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void anonymousAdminRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/api/admin/report"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void authenticatedUserWithoutAdminRoleIsDenied() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void postWithoutCsrfIsRejectedBeforeBusinessLogic() throws Exception {
        mvc.perform(post("/api/orders/checkout")
                .with(user("alice").roles("USER")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("CSRF_REJECTED"));
    }

    @Test
    void validCsrfReachesBusinessRuleAndReturnsConflict() throws Exception {
        mvc.perform(post("/api/orders/checkout")
                .with(user("alice").roles("USER"))
                .with(csrf()))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("OUT_OF_STOCK"));
    }

    @Test
    void adminCanReadReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("root").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("report-ok"));
    }
}
~~~

Các test dùng MockMvc và mock principal của `spring-security-test`; chúng **không kiểm thử cơ chế login thực tế**, nhưng kiểm tra đúng ranh giới 401/403 CSRF/403 authorization/409 business. Chạy bằng task kiểm thử của dự án (chẳng hạn `./gradlew test` trong Gradle project có dependency nói trên). Đừng chạy từng file bằng `javac` thuần, vì các class phụ thuộc Spring/JUnit và phải chạy trong Spring Boot context.

Kết quả HTTP mong đợi (phần `code` của JSON; định dạng đầy đủ do cấu hình ở trên tạo):

| Request | Principal và token | Status | JSON code |
| --- | --- | --- | --- |
| `GET /api/admin/report` | Anonymous | 401 | `AUTHENTICATION_REQUIRED` |
| `GET /api/admin/report` | `ROLE_USER` | 403 | `ACCESS_DENIED` |
| `POST /api/orders/checkout` | `ROLE_USER`, không CSRF | 403 | `CSRF_REJECTED` |
| `POST /api/orders/checkout` | `ROLE_USER`, CSRF hợp lệ | 409 | `OUT_OF_STOCK` |
| `GET /api/admin/report` | `ROLE_ADMIN` | 200 | `report-ok` (body dạng text) |

**Hai dòng 403 có cùng status nhưng khác nguyên nhân.** Với POST có CSRF hợp lệ, chỉ khi vượt qua lớp bảo mật, điều kiện nghiệp vụ mới được đánh giá và trả 409.

## 7. Cách chẩn đoán trong dự án thực tế

Đi theo luồng sau thay vì đoán dựa vào trang lỗi:

### Bước 1: Xác định đúng request và security filter chain

Ghi nhận method, path, thời điểm, identity được xác thực, request correlation ID và status. Kiểm tra chính xác `SecurityFilterChain` áp dụng cho path (đặc biệt khi có nhiều chain, context path, reverse proxy). **Không log token CSRF, cookie, header Authorization hay mật khẩu**.

### Bước 2: Xem lỗi có xảy ra trước controller không

- Controller/service chưa được gọi; request unsafe; log/handler cho biết `CsrfException` → ưu tiên kiểm tra CSRF.
- Controller chưa được gọi; `AuthorizationFilter`/URL policy từ chối → kiểm tra principal và authorities.
- Controller/service đã chạy → kiểm tra method security, object-level authorization, validation và exception nghiệp vụ. Không phải cứ “đã vào controller” thì không thể xảy ra `AccessDeniedException`.

### Bước 3: Đọc *loại exception gốc* thay vì text lỗi

Mẫu quyết định (pseudocode):

~~~text
if cause is CsrfException:
    classification = CSRF_REJECTED
else if cause is AccessDeniedException:
    classification = ACCESS_DENIED
else if cause is AuthenticationException:
    classification = AUTHENTICATION_REQUIRED
else if cause is domain-specific exception:
    classification = BUSINESS_RULE_VIOLATION
else:
    classification = other error
~~~

Đây là mẫu **phân loại nguyên nhân**, không phải lời khuyên ném mọi exception lên một global catch. Vị trí bắt và xử lý đúng của từng lớp trong Spring Security/MVC vẫn phải được giữ nguyên.

### Bước 4: Kiểm tra bằng đối chứng có kiểm soát

- Cùng user, cùng `GET /api/admin/report`, chỉ thay role `USER` ↔ `ADMIN`: nếu kết quả 403 ↔ 200, đây là vấn đề authorization.
- Cùng user, cùng `POST /api/orders/checkout`, chỉ thay CSRF token thiếu/sai ↔ hợp lệ: nếu 403 CSRF ↔ 409 nghiệp vụ, đây là kiểm soát CSRF hoạt động đúng.
- Với token CSRF hợp lệ, giữ nguyên quyền user rồi thay trạng thái nghiệp vụ tồn kho: lỗi business có thể chuyển giữa 2xx và 409. Nếu cả hai request vẫn 403, cần xem authorization hoặc một tầng filter khác trước.
- Thử anonymous tách biệt khỏi “đã đăng nhập nhưng không có role”; `ExceptionTranslationFilter` có thể định tuyến hai trường hợp đến handler khác nhau.

### Bước 5: Giữ phản hồi ổn định và an toàn

API có thể công bố một schema nhất quán, ví dụ:

~~~json
{
  "code": "ACCESS_DENIED",
  "message": "Bạn không có quyền thực hiện thao tác này.",
  "requestId": "req-7b22"
}
~~~

`requestId` ở trên chỉ là ví dụ minh họa; trong hệ thống thật, giá trị phải do cơ chế trace/correlation tạo. Nội dung response nên tránh nêu tài nguyên/role bí mật hoặc chi tiết token; log phía server có thể ghi loại exception và mã trace để hỗ trợ vận hành. Không cần trả stack trace cho client.

## 8. Các sắc thái thường bị bỏ qua

### 8.1 Method security có thể tạo AccessDeniedException sau URL authorization

Khi bật `@EnableMethodSecurity` và dùng `@PreAuthorize`, một method service có thể bị chặn dù URL rule là `authenticated()`. Ví dụ:

~~~java
// Minh họa một method trong @Service của ứng dụng.
@PreAuthorize("hasAuthority('invoice:approve')")
public void approveInvoice(long invoiceId) {
    // Kiểm tra tiếp quyền trên invoiceId và xử lý nghiệp vụ.
}
~~~

Lưu ý: đoạn này là **method minh họa**, không phải class độc lập. Nếu deny exception đi ngược qua servlet filter chain, `ExceptionTranslationFilter` có thể xử lý. Nếu có `@ControllerAdvice` bắt `AccessDeniedException`/`Exception` quá rộng thì hành vi có thể bị đổi trước đó; cần tránh bắt lẫn như vậy.

### 8.2 Lỗi 403 không chứng minh AuthorizationFilter là nơi gây ra lỗi

Một 403 có thể từ `CsrfFilter`, một filter bảo mật khác, chính ứng dụng hoặc một reverse proxy. Các lớp CSRF kế thừa `AccessDeniedException` nên ngay cả tên exception cha cũng chưa đủ. Dựa vào nguồn phát sinh + subtype + test đối chứng.

### 8.3 401 và 403 có thể thay đổi theo cơ chế xác thực

Với REST sử dụng `AuthenticationEntryPoint` trả 401, anonymous thường thấy 401. Với form login, cùng nhánh có thể redirect. Người dùng nhớ đăng nhập (remember-me) đôi khi vẫn bị coi là chưa đủ mức xác thực cho tài nguyên cụ thể. Vì thế điều cần kết luận là **nhánh authentication hay authorization**, sau đó mới xét status/redirect của cấu hình.

### 8.4 ControllerAdvice không bao trùm Security FilterChain

`@ExceptionHandler` trong MVC xử lý exception khi request đến DispatcherServlet và được MVC resolver xử lý. CSRF và nhiều authorization decision ở filter diễn ra sớm hơn, nên handler của MVC thường **không nhận** chúng. Hãy cấu hình `exceptionHandling` cho lỗi HTTP security; dùng `@RestControllerAdvice` cho domain/validation. Nếu muốn định dạng lỗi thống nhất, các handler có thể dùng chung utility/schema nhưng phải đăng ký ở đúng lớp.

### 8.5 Không biến lỗi 403 thành lý do bỏ kiểm tra CSRF

Tắt `csrf()` có thể khiến test business 409 “đột nhiên chạy”, nhưng đồng thời gỡ bỏ cơ chế bảo vệ khỏi request giả mạo nếu ứng dụng dựa vào cookie/session. Cách sửa đúng thường là cấp và gửi token cho request phù hợp, xử lý vòng đời token sau đăng nhập/đăng xuất hoặc xác định rõ threat model trước khi tùy chỉnh.

### 8.6 Không đánh đồng toàn bộ lỗi ứng dụng với “không có quyền”

Một request vượt qua HTTP authorization nhưng vi phạm quy tắc nghiệp vụ nên được biểu diễn bằng domain exception và mã lỗi theo hợp đồng. Tuy nhiên, nếu quy tắc liên quan đến **quyền của người dùng trên đối tượng** (chủ sở hữu, tenant, thành viên phòng), cần coi đó là authorization để tránh rò rỉ dữ liệu, áp dụng nhất quán với policy.

## 9. Bảng chốt để tự đối chiếu

| Câu hỏi | Authorization denial | CSRF rejection | Business rejection |
| --- | --- | --- | --- |
| Điều kiện bị vi phạm | Principal không có quyền/authority/tài nguyên | Token CSRF không phù hợp khi request cần bảo vệ | Trạng thái/quy tắc nghiệp vụ không cho hoàn tất |
| Exception phổ biến | `AccessDeniedException` và subclass (không tính CSRF) | `CsrfException`, **cũng là AccessDeniedException** | Custom `RuntimeException` cho domain |
| Thành phần nhận diện | AuthorizationFilter/method interceptor | CsrfFilter | Service/domain/controller |
| Thường xử lý | ExceptionTranslationFilter → EntryPoint hoặc AccessDeniedHandler | CsrfFilter → AccessDeniedHandler | MVC advice/exception resolver |
| Status thường thấy | 403 nếu đã đăng nhập; 401/redirect nếu chưa | 403 | 409, 422, 400 hoặc status khác theo loại lỗi |
| Bằng chứng tốt nhất | Role/authority/ownership và denial decision | Exception subtype + CSRF/token state | Domain error code + state |
| Cách sửa đúng | Cập nhật quyền hoặc policy theo nghiệp vụ | Sửa token/client flow và CSRF config hợp lý | Sửa input/trạng thái/quy trình nghiệp vụ |

**Câu nhớ lâu:** `AccessDeniedException` mô tả họ lỗi bảo mật; `CsrfException` là **một nhánh trong họ đó**; lỗi nghiệp vụ có **nguồn và cách biểu diễn riêng**. Khi cùng thấy HTTP 403, đọc exception subtype, filter/handler đã xử lý và bằng chứng request trước khi kết luận.

## 10. Tài liệu chính thức

- Spring Security — Servlet architecture / Handling Security Exceptions: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — CSRF protection và Handling AccessDeniedException: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — HTTP authorization: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Method security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security API — CsrfException (là subclass AccessDeniedException): https://docs.spring.io/spring-security/site/docs/6.5.6/api/org/springframework/security/web/csrf/CsrfException.html
