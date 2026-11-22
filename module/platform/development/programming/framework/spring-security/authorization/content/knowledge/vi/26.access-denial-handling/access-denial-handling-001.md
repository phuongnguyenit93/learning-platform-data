# Phân biệt chưa xác thực, thiếu quyền và tài nguyên không tồn tại trong Spring Security

Trong ứng dụng Spring Security dùng **Servlet/Spring MVC**, ba kết quả thường bị nhầm lẫn là **401 Unauthorized**, **403 Forbidden** và **404 Not Found**. Chúng phản ánh ba câu hỏi khác nhau: *người gọi đã chứng minh danh tính chưa?*, *người gọi có được phép thực hiện thao tác không?*, và *đường dẫn hoặc đối tượng cần tìm có tồn tại (hoặc được phép tiết lộ) không?* Cần phân biệt chúng trước khi thiết kế API, xử lý exception và viết kiểm thử.

## 1. Bảng quyết định

| Trường hợp | HTTP thường dùng | Ý nghĩa với client | Nơi có thể quyết định |
| --- | --- | --- | --- |
| Không có thông tin xác thực hoặc thông tin không hợp lệ/hết hạn | **401 Unauthorized** | Cần cung cấp hoặc làm mới thông tin xác thực | Authentication filter, `AuthenticationEntryPoint` |
| Đã xác thực nhưng không có quyền cho thao tác này | **403 Forbidden** | Đổi quyền/chính sách; đăng nhập lại với cùng quyền thường không giúp | `AuthorizationFilter`, method security, `AccessDeniedHandler` |
| Đường dẫn không được ánh xạ hoặc bản ghi được yêu cầu không tồn tại | **404 Not Found** | Không có tài nguyên phù hợp để trả về | Spring MVC routing, controller/service |
| Đối tượng tồn tại nhưng chính sách cần giấu sự tồn tại khỏi người không được truy cập | **404 Not Found** *theo chủ đích* | Không thể suy ra đối tượng có tồn tại hay không | Chính sách bảo mật ở lớp ứng dụng |

**401 không có nghĩa là “đã đăng nhập nhưng thiếu quyền”**, dù tên tiếng Anh là `Unauthorized`. Đây là lỗi **chưa xác thực hợp lệ**. Theo HTTP, phản hồi 401 đi kèm ít nhất một challenge trong header `WWW-Authenticate`, ví dụ `Basic` hoặc `Bearer`. **403** là từ chối yêu cầu; trong luồng kiểm tra quyền thông thường, người gọi đã xác thực nhưng thiếu quyền. Tuy nhiên, 403 còn có thể do CSRF hoặc các chính sách bảo vệ khác, vì vậy không thể chẩn đoán “thiếu role” chỉ từ mã 403. **404** không phải một ngoại lệ phân quyền mặc định của Spring Security.

## 2. Vì sao cùng một URL có thể trả về mã khác nhau?

Luồng xử lý được giản lược:

~~~text
HTTP request
  |
  v
Spring Security FilterChainProxy
  |-- Xác thực: cookie/session, HTTP Basic, Bearer token...
  |-- Phân quyền URL: AuthorizationFilter
  |     |-- chưa được xác thực -> AuthenticationEntryPoint -> thường 401
  |     |-- đã xác thực, thiếu quyền -> AccessDeniedHandler -> thường 403
  |     '-- cho phép -> tiếp tục filter chain
  v
DispatcherServlet / HandlerMapping
  |-- không có route phù hợp -> 404
  v
Controller -> Service -> Repository
  |-- không tìm thấy đối tượng -> 404
  |-- vi phạm quyền ở mức đối tượng -> 403 hoặc 404 theo chính sách
  '-- hợp lệ -> 2xx
~~~

`ExceptionTranslationFilter` chuyển các `AuthenticationException` hoặc `AccessDeniedException` phát sinh ở phần xử lý phía sau nó thành hành vi HTTP thích hợp. Với `AuthenticationException`, hoặc `AccessDeniedException` khi người gọi được xem là anonymous/remember-me chưa đủ xác thực, nó khởi động `AuthenticationEntryPoint`. Với người đã xác thực đầy đủ mà vẫn bị `AccessDeniedException`, nó gọi `AccessDeniedHandler`. Một số authentication filter xử lý lỗi xác thực của chính chúng trước khi exception tới filter này. Do đó **không nên hiểu rằng mọi 401 đều đi qua cùng một exception handler**.

`AuthenticationEntryPoint` phụ thuộc cơ chế xác thực: REST API dùng HTTP Basic thường phản hồi `401` kèm `WWW-Authenticate: Basic ...`; OAuth2 Resource Server thường dùng Bearer challenge; ứng dụng dùng form login có thể chuyển hướng `302` đến trang đăng nhập. Vì vậy không được khẳng định “mọi request chưa đăng nhập luôn là 401” khi chưa xem cấu hình thực tế.

**Thứ tự rất quan trọng.** Nếu quy tắc bảo vệ `/api/reports/**` chặn request trước khi Spring MVC tra route hoặc dữ liệu, một URL thực tế không tồn tại vẫn có thể trả `401` hoặc `403`. Chỉ khi request đi tới tầng quyết định sự tồn tại thì mới có cơ hội trả `404`.

## 3. Ví dụ Spring Boot: quan sát 401, 403, 404 trên cùng endpoint

Ví dụ dùng **Java 17+, Spring Boot 3.x/Spring Security 6.x**, API Servlet/MVC, HTTP Basic và hai user in-memory. Trong dự án Spring Boot đã có Maven/Gradle, thêm dependency `spring-boot-starter-web` và `spring-boot-starter-security`. Phần test dùng thêm `spring-boot-starter-test` và `spring-security-test`. Các tệp dưới đây là mã ví dụ hoàn chỉnh trong package `com.example.demo`; mật khẩu `{noop}` chỉ dành cho demo, **không dùng trong production**.

**`src/main/java/com/example/demo/DemoApplication.java`**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/demo/ApiSecurityConfig.java`**

~~~java
package com.example.demo;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password("{noop}reader123")
                .authorities("REPORT_READ")
                .build(),
            User.withUsername("guest")
                .password("{noop}guest123")
                .authorities("OTHER")
                .build()
        );
    }
}
~~~

Quy tắc `GET /api/reports/**` đòi đúng authority `REPORT_READ`. User `guest` xác thực thành công nhưng chỉ có `OTHER` nên bị từ chối. Cấu hình `DispatcherType.ERROR` cho phép Spring Boot chuyển tiếp tới bộ xử lý lỗi mà không vô tình biến lỗi 404 thành một lần từ chối quyền mới; trong ứng dụng thực, phải xem xét quy tắc dispatcher tương ứng với toàn bộ hệ thống.

**`src/main/java/com/example/demo/ReportController.java`**

~~~java
package com.example.demo;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    @GetMapping("/{id}")
    public Report get(@PathVariable long id) {
        if (id != 42L) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Report not found");
        }
        return new Report(42L, "Quarterly");
    }

    public record Report(long id, String title) {}
}
~~~

Giả sử ứng dụng chạy ở `localhost:8080` (`mvn spring-boot:run` trong dự án Maven đã cấu hình Spring Boot). Chạy các lệnh sau trong shell hỗ trợ `curl`:

~~~bash
# Không có credentials -> 401
curl -s -o /dev/null -w '%{http_code}\n' \
  http://localhost:8080/api/reports/42

# Có danh tính nhưng sai quyền -> 403
curl -s -o /dev/null -w '%{http_code}\n' -u guest:guest123 \
  http://localhost:8080/api/reports/42

# Có đúng quyền, bản ghi không có -> 404
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 \
  http://localhost:8080/api/reports/99

# Có đúng quyền và bản ghi tồn tại -> 200
curl -s -o /dev/null -w '%{http_code}\n' -u reader:reader123 \
  http://localhost:8080/api/reports/42
~~~

**Stdout kỳ vọng** (mỗi lệnh in ra một dòng; không bao gồm HTTP body):

~~~text
401
403
404
200
~~~

Với request thành công, endpoint trả JSON `{"id":42,"title":"Quarterly"}`. Nếu bỏ thông tin xác thực khi gọi `/api/reports/99`, kết quả là **401 trước khi controller kiểm tra `id`**; `99` không được dùng làm bằng chứng rằng API phải trả 404 cho mọi người gọi.

## 4. 401: xử lý yêu cầu xác thực

- **Chưa đăng nhập/không có credentials**: với endpoint yêu cầu danh tính, đi vào cơ chế authentication challenge. API HTTP Basic thường dùng `WWW-Authenticate: Basic realm="..."`; API Bearer dùng `WWW-Authenticate: Bearer`.
- **Mật khẩu/token sai hoặc hết hạn**: xác thực thất bại; với Bearer token lỗi `invalid_token` thường là 401. Client có thể xin token mới hoặc yêu cầu người dùng đăng nhập, tùy cơ chế.
- **Không tự phát 403 chỉ vì token bị từ chối**: nếu không chứng minh được danh tính thì chưa thể kết luận người gọi đã xác thực nhưng thiếu quyền.
- **Không gửi chi tiết nhạy cảm**: body trả về mã lỗi ổn định, message chung và request id; tránh tiết lộ có hay không một username.

Ví dụ response Bearer theo nguyên tắc HTTP/OAuth (các thuộc tính thực tế do cấu hình và loại lỗi quyết định):

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Khi tùy biến API, `AuthenticationEntryPoint` là điểm mở đầu xác thực. Đừng thay `BearerTokenAuthenticationEntryPoint` bằng handler JSON đơn giản làm mất challenge chuẩn nếu client OAuth2 phụ thuộc vào `WWW-Authenticate`.

## 5. 403: xử lý yêu cầu đã xác thực nhưng bị từ chối

- **Quyền theo URL**: `requestMatchers(...).hasAuthority("REPORT_READ")` hoặc `hasRole("ADMIN")`.
- **Quyền theo method**: `@PreAuthorize("hasAuthority('REPORT_READ')")` và các quy tắc method security khi đã bật `@EnableMethodSecurity`.
- **Quyền theo đối tượng**: người dùng đọc được báo cáo nói chung nhưng không có quyền với `reportId` cụ thể. Quyết định này phải dựa trên user hiện tại và dữ liệu đối tượng, không chỉ URL.
- **Lý do khác**: CSRF token thiếu/không hợp lệ ở request thay đổi trạng thái có thể gây 403. Khi thấy 403 của POST/PUT/DELETE, kiểm tra cả cấu hình CSRF thay vì chỉ kiểm tra role.

Phân biệt `hasRole("ADMIN")` (thường kiểm tra authority `ROLE_ADMIN`) với `hasAuthority("ADMIN")` (so khớp đúng chuỗi `ADMIN`). JWT Resource Server mặc định thường ánh xạ scope thành authority có tiền tố `SCOPE_`; token có `scope=report.read` không tự động có `REPORT_READ` nếu chưa có converter. Vì vậy **đúng token nhưng sai mapping authority vẫn trả 403**.

`AccessDeniedHandler` xử lý từ chối ở tầng Spring Security. `@RestControllerAdvice` thông thường chỉ tham gia vào exception trong phần MVC; không nên dùng nó làm điểm duy nhất để bắt lỗi bị filter chặn trước controller.

Với OAuth2 Bearer, token hợp lệ nhưng scope không đủ có thể được trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Đây là lỗi phân quyền, khác với `invalid_token` của 401.

## 6. 404: tài nguyên không tồn tại và chính sách che giấu

404 xảy ra khi không tìm thấy route phù hợp sau khi qua các filter cần thiết, hoặc khi tìm kiếm theo `id` không thấy bản ghi. Trong controller/service, có thể dùng `ResponseStatusException(HttpStatus.NOT_FOUND)` (như ví dụ), `ResponseEntity.notFound().build()`, hoặc một domain exception được map rõ ràng thành 404.

**Không đồng nhất “không được xem” với “không tồn tại”.** Hãy xác định chính sách API:

1. Với tài nguyên có thể công khai sự tồn tại, trả **403** khi đối tượng tồn tại nhưng user không có quyền; trả **404** khi thực sự không tìm thấy. Người dùng và hệ thống vận hành có thể phân biệt lỗi quyền với lỗi dữ liệu.
2. Với tài nguyên riêng tư (ví dụ hồ sơ, tệp của tenant khác), có thể chủ ý trả **404** cho cả “không tồn tại” và “không được phép thấy” để tránh dò ID. Cần nhất quán giữa truy vấn danh sách, truy vấn chi tiết và thông báo lỗi.
3. Kiểm tra ownership/tenant **ở backend**. Ví dụ repository tra bằng cả khóa đối tượng lẫn user/tenant đang đăng nhập; nếu không tìm thấy bản ghi phù hợp thì trả 404, không cho client truyền tùy ý tenant của người khác.

Một cách diễn đạt truy vấn minh họa (tên bảng/cột tùy schema):

~~~sql
SELECT id, title
FROM report
WHERE id = :reportId AND owner_id = :currentUserId;
~~~

Trả 404 khi kết quả rỗng có thể bao gồm cả ID không tồn tại và ID thuộc chủ sở hữu khác. Cách này **chỉ phù hợp nếu đó là chính sách đã chọn**; với hệ thống yêu cầu báo cáo thiếu quyền rõ ràng, hãy quyết định 403 ở lớp phân quyền sau khi xác minh đối tượng. Dù chọn cách nào, log nội bộ cần ghi đúng lý do và không lộ dữ liệu nhạy cảm ra response.

**Chú ý:** Một route không tồn tại không chắc trả 404 ngay. Nếu `anyRequest().denyAll()` chặn tất cả các request lạ, kết quả có thể là 401/403 trước `DispatcherServlet`. Không nên nới rule bảo mật chỉ để ép mọi URL lạ thành 404.

## 7. Kiểm thử cả trạng thái, quyền và sự tồn tại

Khi dự án có `spring-boot-starter-test` và `spring-security-test`, có thể viết kiểm thử tích hợp với `MockMvc`:

**`src/test/java/com/example/demo/ReportSecurityTests.java`**

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityTests {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsReturns401() throws Exception {
        mvc.perform(get("/api/reports/42"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void invalidCredentialsReturn401() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutPermissionReturns403() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("guest", "guest123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void permittedUserWithMissingReportGets404() throws Exception {
        mvc.perform(get("/api/reports/99")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isNotFound());
    }

    @Test
    void permittedUserWithExistingReportGets200() throws Exception {
        mvc.perform(get("/api/reports/42")
                .with(httpBasic("reader", "reader123")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42));
    }
}
~~~

Chạy `mvn test` trong dự án Maven. `httpBasic(...)` gửi header Basic thực để kiểm tra luồng xác thực; `@WithMockUser` hữu ích cho test phân quyền nhưng không kiểm tra việc xác minh mật khẩu thật. Khi kiểm thử Bearer API, thay bằng request chứa Bearer token/`jwt()` phù hợp và kiểm tra header `WWW-Authenticate` cùng scope/authority.

## 8. Checklist gỡ lỗi khi mã trả về khác kỳ vọng

1. **Có user thật hay chỉ anonymous?** Kiểm tra authentication provider, session, bearer expiration, `SecurityContext` và không log credential/token.
2. **Quy tắc URL nào match trước?** Xem `SecurityFilterChain` và thứ tự `requestMatchers`; kiểm tra có chain khác, `securityMatcher` hoặc `anyRequest().denyAll()`.
3. **User có authority thực tế nào?** So sánh chính xác `ROLE_`, `SCOPE_`, tên permission và rule ở method/object.
4. **Request có tới controller không?** Nếu chưa tới MVC, đừng mong `@ExceptionHandler` của controller tạo 404.
5. **Có CSRF hoặc ERROR dispatch không?** Đặc biệt khi POST trả 403 hoặc lỗi gốc bị đổi thành 401/403 trong quá trình xử lý `/error`.
6. **404 là không tìm thấy thật hay do chính sách ẩn đối tượng?** Xác minh repository/tenant check bằng log an toàn và test riêng case cross-tenant.
7. **Response giữ đúng semantics?** 401 phải có authentication challenge tương ứng; 403 không bảo client cứ làm mới token; 404 không được vô tình tiết lộ đối tượng riêng tư.

Khi triển khai thực tế, định nghĩa nhất quán ba tình huống trong API contract, thống nhất cấu trúc body lỗi (có thể dùng Problem Details), dùng đúng `AuthenticationEntryPoint`/`AccessDeniedHandler` và map lỗi domain sang 404 ở lớp MVC/service. Luôn có test cho anonymous, authenticated thiếu quyền, authenticated đủ quyền nhưng ID không tồn tại, và truy cập thành công.

## Tài liệu tham khảo chính thức

- [Spring Security — Servlet Architecture, Handling Security Exceptions](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Testing HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html)
- [Spring Security — OAuth2 Bearer Token Failure](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
