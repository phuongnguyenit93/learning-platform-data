# Thiết kế ca kiểm thử có token đúng, thiếu và sai

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Thiết kế các ca kiểm thử **CSRF token hợp lệ, thiếu, sai giá trị, sai phiên hoặc sai kênh truyền** cho những HTTP request thay đổi trạng thái.
- Xác định **điều kiện tiên quyết, dữ liệu test, request, kết quả mong đợi** và bằng chứng không xảy ra tác động nghiệp vụ khi server từ chối request.
- Hiểu khác biệt giữa **expected token do repository quản lý** và **submitted token do client gửi**, kể cả trường hợp token render dưới dạng **XOR-masked**.
- Kiểm thử cả **hidden form field** và **HTTP header**, thay đổi phiên/cookie, login/logout, cookie repository cho SPA, token hết hạn và thao tác HTTP an toàn.
- Sử dụng `MockMvc` với `spring-security-test` cho **Spring Security Servlet** và `WebTestClient` cho **Reactive/WebFlux**; biết giới hạn của helper `csrf()`.
- Xây dựng bài test **end-to-end lấy token thực từ GET, giữ đúng session và submit lại**, thay vì chỉ dựa vào mock principal.
- Phân biệt lỗi CSRF với **authentication, authorization, CORS, SameSite, HTTP firewall và validation** khi gặp `401`, `403` hoặc redirect.
- Đưa các ca kiểm thử quan trọng vào regression suite để phát hiện cấu hình CSRF bị tắt, bỏ qua matcher hoặc hỏng sau thay đổi frontend/API.

## 1. Bài toán: chứng minh điều gì khi nói “CSRF đã được bảo vệ”?

Giả sử ứng dụng có endpoint đổi email:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=alice@example.test
~~~

Nếu request trên không có CSRF token mà server vẫn đổi email trong phiên Alice, ứng dụng có thể bị **Cross-Site Request Forgery** khi browser tự gửi cookie xác thực trong một ngữ cảnh attacker có thể kích hoạt.

CSRF protection yêu cầu **giá trị client chủ động gửi** phải phù hợp token kỳ vọng và chính sách:

~~~http
POST /profile/email HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/x-www-form-urlencoded

email=new@example.test&_csrf=VALID_TOKEN_FOR_A
~~~

Tại mức tối thiểu, bộ kiểm thử phải chứng minh:

1. **Token đúng:** Request được phép vượt qua **lớp CSRF** (không bảo đảm tự động được phân quyền hoặc dữ liệu hợp lệ).
2. **Token thiếu:** Request thuộc phạm vi CSRF bị từ chối **trước khi thao tác nghiệp vụ hoàn tất**.
3. **Token sai:** Token ngẫu nhiên, biến đổi hoặc thuộc ngữ cảnh khác bị từ chối.
4. **Không có side effect khi bị từ chối:** Email, đơn hàng, quyền truy cập, sự kiện nghiệp vụ hay dữ liệu lưu trữ không đổi.
5. **Không có đường vòng:** Form, JSON, header, endpoint login/logout, phương thức và security chain khác không vô tình bỏ qua chính sách.

> **Định nghĩa ca kiểm thử tốt:** Không chỉ nhìn mã HTTP; phải chỉ ra **request được gửi với credential nào, expected token ở đâu, submitted token ở đâu, lớp nào từ chối và trạng thái nghiệp vụ có bị thay đổi không**.

Đây là kỹ năng nền tảng của module **SPRING_SECURITY_HTTP_PROTECTION**, kết hợp CSRF với CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session trên Spring Security **Servlet** lẫn **Reactive**.

## 2. Hiểu hai giá trị trước khi viết test

### 2.1. Expected token và submitted token

Trong mẫu **synchronizer token**:

- **Expected token:** Giá trị được server sinh/tải từ repository, ví dụ `HttpSessionCsrfTokenRepository` hoặc `WebSessionServerCsrfTokenRepository`, gắn với phiên đang xử lý.
- **Submitted token:** Giá trị gửi trong form parameter hoặc header của HTTP request.
- **Request handler:** Quyết định tên field/header, biểu diễn token, có giải mask khi cần.
- **CSRF filter:** Kiểm tra request cần bảo vệ hay không, lấy expected và submitted, từ chối nếu không đáp ứng chính sách.

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Trình duyệt
    participant S as Spring Security
    participant R as CSRF Repository
    participant C as Controller

    B->>S: GET /profile/edit
    S->>R: Load hoặc tạo expected token khi cần
    R-->>S: Token của session A
    S-->>B: HTML có token cho form
    U->>B: Bấm lưu thay đổi
    B->>S: POST + cookie session A + submitted token
    S->>R: Tìm expected token của session A
    S->>S: Resolve submitted, giải mask nếu có, đối chiếu
    alt Hợp lệ
        S->>C: Cho request đi tiếp
        C-->>B: Kết quả nghiệp vụ
    else Thiếu hoặc sai
        S-->>B: Từ chối, thường HTTP 403
    end
~~~

Khi repository dựa vào cookie (double-submit), expected token được lấy theo repository cookie thay vì server session; nếu ứng dụng dùng biến thể HMAC có ký/ràng buộc phiên, bài test phải kiểm tra **chữ ký và binding theo đúng thiết kế tùy chỉnh**. Không mặc định `CookieCsrfTokenRepository` thông thường tự triển khai signed double-submit.

### 2.2. Không phải token hiển thị trong HTML luôn bằng raw token

Trong Spring Security Servlet hiện đại, `XorCsrfTokenRequestAttributeHandler` có thể xuất CSRF token **được mask bằng XOR** khi render HTML, nhằm giảm một số rủi ro rò rỉ liên quan đến nén phản hồi như BREACH.

~~~text
Raw expected token trong session: R

Lần render 1: submitted form token = M1 = mask(R, random1)
Lần render 2: submitted form token = M2 = mask(R, random2)

M1 khác M2, nhưng cả hai có thể được handler giải mask về R.
~~~

Do đó bài test không nên tự khẳng định “token trong hai form phải giống hệt nhau”. Cần kiểm chứng **token do cùng ứng dụng render có thể được gửi lại thành công**, còn token bị thay đổi/đến từ phiên khác thì thất bại.

Với SPA dùng cookie `XSRF-TOKEN`, frontend có thể gửi **raw token** qua `X-XSRF-TOKEN`. Nếu request handler chỉ nhận masked token, request có thể `403` dù cookie/header nhìn có vẻ giống nhau. Đây là **bất tương thích handler**, không phải bằng chứng nguyên tắc CSRF không hiệu quả.

### 2.3. Token đúng không thay authentication và authorization

Một POST có token hợp lệ nhưng không đăng nhập hoặc thiếu quyền có thể vẫn trả `401`, `403` hoặc redirect login. Khi thiết kế test, cần đảm bảo **người dùng test có quyền** đối với positive case để tránh kết luận sai rằng CSRF token bị lỗi.

Tương tự, positive case với body không hợp lệ có thể trả `400` hoặc lỗi validation. Để chứng minh **CSRF pass**, hãy giữ body hợp lệ hoặc kiểm tra một dấu hiệu chắc chắn request đã vượt qua lớp CSRF.

## 3. Quy định phạm vi và giả thiết kiểm thử

### 3.1. Trước khi chạy test phải xác định

| Nhóm điều kiện | Câu hỏi cần trả lời |
|---|---|
| **Đường dẫn** | Endpoint là `/profile/email`, `/api/profile`, `/login` hay `/logout`? |
| **HTTP method** | `GET` chỉ đọc hay `POST`/`PUT`/`PATCH`/`DELETE` có tác động? |
| **Credential** | Session cookie, WebSession cookie, JWT cookie, Bearer header, Basic hay BFF cookie? |
| **Security chain** | Request có đi qua `SecurityFilterChain`/`SecurityWebFilterChain` dự kiến không? |
| **CSRF repository** | Token trong HttpSession/WebSession hay cookie? |
| **Request handler** | Nhận `_csrf`, `X-CSRF-TOKEN`, `X-XSRF-TOKEN`, raw hoặc masked? |
| **Nguồn token** | Client lấy token qua HTML, meta tag, endpoint JSON hay cookie `XSRF-TOKEN`? |
| **Phiên** | Session A và B có tách biệt không? Token còn hiệu lực sau login/logout không? |
| **Kết quả** | Status/redirect dự kiến và trạng thái nghiệp vụ nào phải/không được thay đổi? |
| **Môi trường** | Test mock security filter hay browser tích hợp với cookie thật và CORS? |

### 3.2. Xác định một hợp đồng endpoint làm ví dụ

Để các đoạn test bên dưới có kết quả xác định, giả sử ứng dụng triển khai:

- `GET /csrf`: endpoint minh họa trả tên form parameter, tên header và CSRF token **theo request hiện tại**; có thể dùng trước và sau đăng nhập nếu policy cho phép.
- `GET /profile/edit`: render form với hidden `_csrf`.
- `POST /profile/email`: nhận form `email`, cập nhật user đang đăng nhập, trả `204 No Content` khi hợp lệ.
- `POST /api/preferences`: nhận JSON, cập nhật theme và trả `204`.
- `POST /login` và `POST /logout`: sử dụng luồng form login/logout tiêu chuẩn của Spring Security với CSRF bật.

Đây là **hợp đồng ví dụ**, không phải endpoint Spring Security tự sinh đầy đủ. Phải có controller/service và security configuration thích hợp, đồng thời kiểm tra quyền, email format, dữ liệu nghiệp vụ trong ứng dụng thật.

**Nguyên tắc test data:** Sử dụng người dùng test có session riêng, tài nguyên/dữ liệu có thể khôi phục, và một kho lưu có thể kiểm tra sau request. Không thực hiện phép thử làm thay đổi tiền, dữ liệu riêng tư hay quyền trên môi trường ngoài phạm vi được phép.

## 4. Ma trận tối thiểu: đúng, thiếu và sai

| ID | Request | Submitted token | Kỳ vọng lớp CSRF | Kỳ vọng nghiệp vụ |
|---|---|---|---|---|
| **CSRF-01** | POST form có cookie session A | Token hợp lệ của A | **Qua bước CSRF** | Cập nhật thành công khi đủ quyền và input hợp lệ |
| **CSRF-02** | POST form có cookie session A | **Thiếu** field `_csrf` | **Từ chối** | Không đổi dữ liệu |
| **CSRF-03** | POST form có cookie session A | Chuỗi **sai** hoặc bị sửa | **Từ chối** | Không đổi dữ liệu |
| **CSRF-04** | POST JSON có cookie session A | Header CSRF đúng cấu hình | **Qua bước CSRF** | Thực hiện cập nhật nếu đủ quyền |
| **CSRF-05** | POST JSON có cookie session A | **Thiếu** header CSRF | **Từ chối** | Không đổi dữ liệu |
| **CSRF-06** | POST JSON có cookie session A | Header token **sai** | **Từ chối** | Không đổi dữ liệu |
| **CSRF-07** | POST của session A | Token của session **B** | **Từ chối** với synchronizer token theo phiên | Không đổi dữ liệu |
| **CSRF-08** | POST của session A | Token đúng nhưng **sai tên** header/field | Thường xem như **thiếu** | Không đổi dữ liệu |
| **CSRF-09** | GET đọc cùng session A | Không gửi CSRF token | **Không yêu cầu CSRF** theo mặc định | Chỉ đọc, không ghi |
| **CSRF-10** | POST hợp lệ nhưng user thiếu quyền | Token đúng | Qua bước CSRF | **Authorization từ chối** |
| **CSRF-11** | POST login chưa xác thực | Thiếu/sai token | Từ chối nếu login thuộc CSRF protection | Không tạo phiên login mới |
| **CSRF-12** | POST logout đã xác thực | Thiếu/sai token | Từ chối | Không logout, session chưa bị vô hiệu hóa bởi request đó |
| **CSRF-13** | POST sau login/logout làm mới phiên | Token **cũ** đã bị vô hiệu | Từ chối | Không thực hiện tác động |
| **CSRF-14** | POST sau khi lấy token mới | Token mới đúng ngữ cảnh | Qua bước CSRF | Hoạt động khi đủ quyền |
| **CSRF-15** | Unsafe request đi qua chain khác | Không token | Phải theo **policy của chain đó** | Không có đường bypass ngoài thiết kế |

Một test suite cơ bản cần tối thiểu **CSRF-01, 02, 03, 04, 05, 06**. Các ca còn lại giúp phát hiện lỗi thiết kế, thay đổi security chain và vòng đời phiên mà test helper đơn giản có thể bỏ sót.

### 4.1. Ba trạng thái token có nghĩa kỹ thuật khác nhau

- **Đúng:** Token được ứng dụng phát hành, theo **đúng repository, đúng request handler và đúng ngữ cảnh**. Không đồng nghĩa chuỗi ký tự token HTML bằng raw token trong session.
- **Thiếu:** Không có header hoặc form field mà handler dự kiến đọc. Một chuỗi rỗng có thể được xem là thiếu hoặc không hợp lệ tùy handler; test cả hai nếu nghiệp vụ quan trọng.
- **Sai:** Có token nhưng bị thay giá trị, sai phiên, hết hiệu lực hoặc sai dạng raw/masked. Nó có thể gây `InvalidCsrfTokenException` hoặc kết quả từ chối tương tự theo stack.

Không nên dùng **token đúng nhưng không có credential xác thực** để test nhánh positive, vì nó tạo thêm biến số authentication.

### 4.2. Không chỉ kiểm tra HTTP 403

Ví dụ negative case phải chứng minh:

~~~text
Trước request: email(Alice) = alice@example.test
Gửi POST /profile/email với cookie session A, thiếu CSRF token
Phản hồi: thường HTTP 403 (hoặc response AccessDeniedHandler đã cấu hình)
Sau request: email(Alice) = alice@example.test
Sự kiện EmailChanged: không có
Audit thành công: không có
~~~

Một controller có thể trả lỗi sau khi đã ghi database nếu cấu hình filter sai. Vì vậy kiểm tra status **và trạng thái sau request** mới thật sự chứng minh bảo vệ nghiệp vụ.

## 5. Phân vùng các trường hợp sai token

Token **sai** không chỉ là một chuỗi bất kỳ. Nên tách:

| Biến thể | Cách tạo test data | Điều muốn chứng minh |
|---|---|---|
| Chuỗi sai ngẫu nhiên | Gửi `not-the-issued-token` | Server không chấp nhận giá trị không được cấp |
| Token bị thay một ký tự | Thay đổi một ký tự của submitted token | Phát hiện sửa đổi |
| Token rỗng | Header hoặc parameter tồn tại với giá trị rỗng | Không chấp nhận token rỗng |
| Token của phiên B | Lấy token thật từ session B, gửi với session A | **Session binding** |
| Token cũ | Đăng nhập/đăng xuất hoặc vô hiệu hóa token rồi dùng lại | Vòng đời token được kiểm soát |
| Token sai kênh | Gửi `X-CSRF-TOKEN` khi cấu hình chỉ đọc `X-XSRF-TOKEN` | Không tự dò mọi header |
| Raw/masked không phù hợp | SPA gửi raw cookie token cho handler chỉ đọc masked | Phát hiện sai request handler |
| Duplicate field/header | Gửi hai giá trị trùng tên nếu ứng dụng có parser đặc biệt | Phát hiện ambiguity; không đoán thứ tự chọn giá trị |
| Token phiên đúng nhưng payload thiếu quyền | Token hợp lệ, user không được phép | CSRF không thay authorization |
| Token đúng nhưng body sai | Token hợp lệ, JSON/form sai định dạng | CSRF pass không làm request nghiệp vụ hợp lệ |

**Lưu ý:** Không phải mọi repository đều có **session binding**. Một double-submit cookie thông thường đối chiếu cookie/header có tính chất khác synchronizer token lưu theo phiên; nếu test yêu cầu HMAC gắn phiên phải triển khai và kiểm chứng đúng biến thể đó. Không kỳ vọng test “token B sai phiên” có cùng cơ chế trên mọi repository.

## 6. Hai kênh truyền: form field và header

### 6.1. Form HTML

~~~html
<form action="/profile/email" method="post">
  <label for="email">Email mới</label>
  <input id="email" type="email" name="email" required>

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Lưu</button>
</form>
~~~

Với Spring MVC + Thymeleaf, `th:name` và `th:value` lấy đúng tên/value từ `CsrfToken` do Spring Security cung cấp. Nếu dùng tích hợp tự thêm hidden field qua `th:action`, hãy kiểm tra HTML cuối cùng để tránh hai trường `_csrf` trùng nhau.

**Positive test** nên dùng token lấy từ form thật; **negative test** thử xóa field hoặc thay value nhưng giữ nguyên session.

### 6.2. HTTP header trong Ajax/JSON

~~~http
POST /api/preferences HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=SESSION_A
Content-Type: application/json
X-CSRF-TOKEN: VALID_CSRF_TOKEN

{"theme":"dark"}
~~~

CSRF filter thông thường **không tự đọc một thuộc tính `"_csrf"` bất kỳ trong JSON body**. Với JSON request, dùng header mà handler dự kiến đọc.

Tên header có thể là `X-CSRF-TOKEN` với session repository hoặc `X-XSRF-TOKEN` với cookie repository; phải lấy đúng cấu hình. Test case **sai tên header** khác với **đúng tên nhưng sai value** — cả hai nên được kiểm thử.

### 6.3. Không cần đồng thời cả form field và header

Nếu server hỗ trợ cả hai, mỗi request hợp lệ thường chỉ cần **một kênh đúng**. Gửi cả hai với giá trị khác nhau khiến hành vi phụ thuộc quy tắc ưu tiên của request handler. Chỉ test biến thể “cả hai cùng tồn tại” khi ứng dụng thực sự hỗ trợ và đã xác định rõ hành vi.

## 7. Spring Security Servlet: thiết lập môi trường test

### 7.1. SecurityFilterChain dùng CSRF theo phiên

Ví dụ cấu hình Spring Security Servlet thông dụng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/csrf", "/login", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new HttpSessionCsrfTokenRepository()))
            .build();
    }
}
~~~

`HttpSessionCsrfTokenRepository` lưu token kỳ vọng theo session; `CsrfFilter` kiểm tra unsafe requests. CSRF thường được bật mặc định trong cấu hình Spring Security web; ví dụ viết rõ repository để giúp đối chiếu expected/submitted.

**Giới hạn code mẫu:** Đây là cấu hình minh họa; cần user source, endpoint `/profile/email`, dependency web/security/test và policy thực tế trong project. Không đưa các ví dụ cấu hình thay thế khác vào cùng ứng dụng nếu chúng tạo bean trùng.

### 7.2. Endpoint cấp token dành riêng cho test hoặc SPA

Một endpoint GET cùng origin có thể công bố token theo request, để bài test lấy đúng giá trị trước khi POST:

~~~java
import java.util.Map;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenEndpoint {

    @GetMapping("/csrf")
    Map<String, String> csrf(CsrfToken token) {
        return Map.of(
            "parameterName", token.getParameterName(),
            "headerName", token.getHeaderName(),
            "token", token.getToken()
        );
    }
}
~~~

Đây là **endpoint ứng dụng tự triển khai**, không phải Spring Security tự sinh. Với Spring MVC và tích hợp Spring Security tương ứng, `CsrfToken` có thể được resolve như method argument.

**Yêu cầu bảo mật cho endpoint này:**

- Chỉ trả token trong bối cảnh được phép và **không mở credentialed CORS cho mọi origin**; nếu origin ngoài đọc được token cùng phiên, lớp chống CSRF suy yếu.
- Không ghi token vào access log, tracing, analytics hoặc URL.
- Sử dụng cache policy phù hợp, thường tránh cache response chứa token riêng theo phiên; có thể cấu hình `Cache-Control: no-store`.
- Nếu frontend dùng session cookie, test phải giữ **cùng session** giữa GET token và POST.

### 7.3. Controller nghiệp vụ mẫu

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
class ProfileController {

    private final ProfileService profiles;

    ProfileController(ProfileService profiles) {
        this.profiles = profiles;
    }

    @PostMapping("/profile/email")
    ResponseEntity<Void> changeEmail(
            java.security.Principal principal,
            @RequestParam String email) {

        profiles.changeEmail(principal.getName(), email);
        return ResponseEntity.noContent().build();
    }
}
~~~

`ProfileService` ở đây là một **interface/service giả định của ứng dụng**: cần thực hiện xác thực quyền cập nhật, validation email, transaction và audit phù hợp. Các test có thể dùng service fake/in-memory database để xác nhận request thiếu CSRF token không gọi `changeEmail`.

## 8. MockMvc: ba test cơ bản có token đúng, thiếu và sai

Dùng `spring-security-test`, `MockMvc` được cấu hình với security filters và một endpoint `POST /profile/email` trả `204` khi hợp lệ.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfBasicServletTests {

    @Autowired MockMvc mvc;

    @Test
    void validTokenPassesCsrfCheck() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf())
                .param("email", "new@example.test"))
            .andExpect(status().isNoContent());
    }

    @Test
    void missingTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenIsRejected() throws Exception {
        mvc.perform(post("/profile/email")
                .with(user("alice"))
                .with(csrf().useInvalidToken())
                .param("email", "new@example.test"))
            .andExpect(status().isForbidden());
    }
}
~~~

`with(user("alice"))` tạo mock authentication cho request test, tránh nhầm lỗi thiếu đăng nhập với lỗi CSRF. `with(csrf())` tạo CSRF token hợp lệ trong môi trường test; `useInvalidToken()` tạo giá trị không hợp lệ; request không có `with(csrf())` dùng để thử nhánh thiếu.

**Phải hiểu giới hạn:** Các helper này **không tự chứng minh** frontend đã render token thật, cookie được gửi đúng SameSite hoặc handler SPA raw/masked đã tương thích. Chúng chỉ chứng minh một lớp security test đang xử lý các trường hợp cơ bản.

### 8.1. Kiểm tra riêng header và form

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@Test
void formParameterTokenWorks() throws Exception {
    mvc.perform(post("/profile/email")
            .with(user("alice"))
            .with(csrf())
            .param("email", "new@example.test"))
        .andExpect(status().isNoContent());
}

@Test
void headerTokenWorks() throws Exception {
    mvc.perform(post("/profile/email")
            .with(user("alice"))
            .with(csrf().asHeader())
            .param("email", "new@example.test"))
        .andExpect(status().isNoContent());
}

@Test
void invalidHeaderTokenIsRejected() throws Exception {
    mvc.perform(post("/profile/email")
            .with(user("alice"))
            .with(csrf().asHeader().useInvalidToken())
            .param("email", "new@example.test"))
        .andExpect(status().isForbidden());
}
~~~

Ba method trên được đặt **trong test class có `mvc` đã cấu hình**, không phải một file Java độc lập. `csrf().asHeader()` kiểm tra khả năng nhận submitted token qua header; nó không chứng minh một SPA đã biết tên header và gửi raw token tương thích với request handler custom.

### 8.2. Không để authorization che lỗi CSRF

Test sau **không đủ** làm bài kiểm thử “thiếu CSRF” nếu endpoint đòi đăng nhập:

~~~java
// Có thể bị chặn vì chưa đăng nhập trước hoặc sau bước CSRF.
mvc.perform(post("/profile/email")
        .param("email", "new@example.test"))
    .andExpect(status().isForbidden());
~~~

Để quy trách nhiệm lỗi cho CSRF, cần auth hợp lệ và kiểm soát các policy khác, hoặc quan sát exception/filter trong test. Trong thiết kế chuẩn, nên chạy cả positive `with(csrf())` và negative **trên cùng loại principal, quyền và payload**.

## 9. MockMvc tích hợp: lấy token thật từ GET rồi gửi theo session

Test bằng `csrf()` rất hữu ích để kiểm tra filter nhưng chưa bao trùm **chu trình client nhận token rồi gửi lại**. Đối với ứng dụng dùng `HttpSessionCsrfTokenRepository`, có thể thiết kế bài test lấy token qua `GET /csrf`, giữ `MockHttpSession`, rồi gửi POST.

### 9.1. Luồng một session

~~~text
GET /csrf (session chưa xác thực hoặc user A)
    -> server tạo/tải expected token
    -> response trả parameterName/headerName/token
    -> browser nhận cookie JSESSIONID ứng với session

POST /profile/email (cùng JSESSIONID)
    -> gửi token GET vừa trả qua form/header
    -> phải qua lớp CSRF

POST /profile/email (cùng JSESSIONID)
    -> bỏ token hoặc thay bằng một chuỗi sai
    -> phải bị từ chối
~~~

Trong test, nếu tự tạo session mới ở mỗi request, positive case có thể bị lỗi **không phải vì token sai nội dung**, mà vì expected token nằm ở session khác. Vì vậy cần thiết kế rõ việc **giữ cùng cookie/session giữa hai bước**.

### 9.2. Ví dụ MockMvc giữ session và kiểm tra token thật

Đoạn test bên dưới giả định đã triển khai endpoint `GET /csrf` ở mục 7.2, backend sử dụng `HttpSessionCsrfTokenRepository` và endpoint POST trả `204`.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfRoundTripServletTests {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper json;

    @Test
    void issuedTokenWorksOnlyWithMatchingSession() throws Exception {
        MvcResult issueA = mvc.perform(get("/csrf").with(user("alice")))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode payloadA = json.readTree(
            issueA.getResponse().getContentAsString());

        String field = payloadA.get("parameterName").asText();
        String tokenA = payloadA.get("token").asText();
        HttpSession rawSessionA = issueA.getRequest().getSession(false);
        MockHttpSession sessionA = (MockHttpSession) rawSessionA;

        // Token được chính ứng dụng phát cho session A.
        mvc.perform(post("/profile/email")
                .session(sessionA)
                .with(user("alice"))
                .param("email", "new@example.test")
                .param(field, tokenA))
            .andExpect(status().isNoContent());

        // Cùng session A nhưng bỏ token.
        mvc.perform(post("/profile/email")
                .session(sessionA)
                .with(user("alice"))
                .param("email", "wrong@example.test"))
            .andExpect(status().isForbidden());

        // Cùng session A nhưng có giá trị không được phát hành.
        mvc.perform(post("/profile/email")
                .session(sessionA)
                .with(user("alice"))
                .param("email", "wrong@example.test")
                .param(field, "invalid-token"))
            .andExpect(status().isForbidden());
    }
}
~~~

**Điểm cần chú ý:**

- `getSession(false)` phải trả về session sau khi endpoint truy cập token; nếu `null`, cần kiểm tra token đã được tạo và repository có lưu token hay không.
- `@Autowired ObjectMapper` giả định project có Jackson/JSON support phù hợp.
- `with(user("alice"))` vẫn là **mock principal**; test này chứng minh token lifecycle của repository/session trong MockMvc, chưa phải login qua browser thật.
- Nếu ứng dụng có endpoint thay đổi email thật, nên dùng dữ liệu test biệt lập và kiểm tra service/database để chắc chắn hai negative request không đổi email.
- Nếu token render ở dạng XOR-masked, dùng chính chuỗi `token` trả từ handler; **không tự thay nó bằng raw token** đọc từ internal session.

### 9.3. Test hoán đổi token giữa hai session

Với **synchronizer token theo HttpSession**, một token phát cho session B không được dùng trong session A. Mở rộng mẫu ở trên:

~~~java
@Test
void tokenFromSessionBCannotAuthorizeSessionA() throws Exception {
    MvcResult getA = mvc.perform(get("/csrf").with(user("alice")))
        .andReturn();
    MvcResult getB = mvc.perform(get("/csrf").with(user("bob")))
        .andReturn();

    String tokenB = json.readTree(
        getB.getResponse().getContentAsString())
        .get("token").asText();

    String field = json.readTree(
        getA.getResponse().getContentAsString())
        .get("parameterName").asText();

    MockHttpSession sessionA =
        (MockHttpSession) getA.getRequest().getSession(false);

    mvc.perform(post("/profile/email")
            .session(sessionA)
            .with(user("alice"))
            .param("email", "wrong@example.test")
            .param(field, tokenB))
        .andExpect(status().isForbidden());
}
~~~

Test method trên được đặt **trong class `CsrfRoundTripServletTests` có `mvc`/`json` đã khai báo**. Nó dùng hai GET khác nhau tạo hai session riêng trong giả thiết cấu hình. Để kiểm chứng session binding ở E2E, nên dùng **hai browser context** hoặc hai cookie jar độc lập.

**Không áp dụng kết luận này máy móc cho repository cookie double-submit không ràng buộc phiên**. Với signed double-submit tùy biến, thêm bài test HMAC/session binding theo thiết kế của repository đó.

### 9.4. Chứng minh không có tác động phụ

Từ chối request chưa đủ nếu service ghi dữ liệu trước khi trả lỗi. Đối với các negative test, nên thêm một trong những phương pháp:

- Đọc lại dữ liệu trong repository/database sau POST và so với trước request.
- Dùng fake service ghi lại số lần `changeEmail` được gọi và xác nhận không bị gọi.
- Kiểm tra **không có** event nghiệp vụ, message vào queue hoặc tác động tới hệ thống ngoài.
- Nếu luồng có transaction, kiểm tra trạng thái commit/rollback sau request.

Ví dụ **pseudo-assertion**, cần tùy chỉnh cho test repository thật:

~~~java
String original = profileRepository.emailOf("alice");

performPostWithMissingCsrfToken();

assertThat(profileRepository.emailOf("alice")).isEqualTo(original);
assertThat(eventRecorder.count("EmailChanged")).isZero();
~~~

Nếu test chạy có nhiều request song song hoặc dữ liệu chung, sử dụng **mỗi test một user/tài nguyên riêng** hoặc reset fixture. Không dựa vào thứ tự các test method.

## 10. Reactive/WebFlux: cách kiểm thử tương đương bằng WebTestClient

### 10.1. SecurityWebFilterChain có CSRF token theo WebSession

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
class ReactiveWebSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/csrf", "/login").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .csrf(csrf -> csrf
                .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
~~~

`CsrfWebFilter` là lớp kiểm tra CSRF của Reactive; `WebSessionServerCsrfTokenRepository` lưu token expected theo WebSession. Phần test nên chạy qua security web filter chain, không chỉ gọi trực tiếp method controller.

### 10.2. Ba ca test cơ bản trên WebTestClient

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class CsrfBasicReactiveTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void validTokenCanPassCsrf() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isNoContent();
    }

    @Test
    void missingTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void incorrectTokenIsRejected() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/profile/email")
            .header("X-CSRF-TOKEN", "invalid-token")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

Ví dụ giả định một endpoint test `POST /profile/email` **không bắt buộc request body** hoặc đã có dữ liệu phù hợp qua request fixture và trả `204` khi hợp lệ. Nếu controller thật yêu cầu form field hoặc JSON, **bổ sung body hợp lệ ở cả ba test**; nếu không, positive case có thể trả `400` do body thiếu, không phải CSRF.

Ở đây:

- `mutateWith(csrf())` cấp token hợp lệ trong môi trường `spring-security-test`.
- Thiếu `mutateWith(csrf())` tạo đường thử **missing token**.
- Header chuỗi sai tạo đường thử **wrong submitted token** ở giả định handler đọc `X-CSRF-TOKEN`.
- Helper Reactive không nhất thiết có mọi biến thể fluent API giống MockMvc Servlet; tránh sao chép `csrf().useInvalidToken()` của Servlet vào Reactive mà chưa kiểm tra version.

### 10.3. Endpoint phát token Reactive cho E2E

Để test **token thật từ server**, một endpoint minh họa:

~~~java
import java.util.Map;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfTokenEndpoint {

    @GetMapping("/csrf")
    Mono<Map<String, String>> token(ServerWebExchange exchange) {
        Mono<CsrfToken> publisher =
            exchange.getAttribute(CsrfToken.class.getName());

        return publisher.map(csrf -> Map.of(
            "parameterName", csrf.getParameterName(),
            "headerName", csrf.getHeaderName(),
            "token", csrf.getToken()
        ));
    }
}
~~~

Ví dụ giả định exchange đã đi qua `CsrfWebFilter` và attribute chứa `Mono<CsrfToken>`. Với deferred token, việc subscribe publisher cho phép phát/tải token khi cần. Nếu custom handler hoặc framework version dùng cách truyền token khác, hãy điều chỉnh theo API thực tế.

### 10.4. E2E với cookie `SESSION` và token của WebSession

Với WebFlux session repository, kiểm thử phải giữ **WebSession cookie** giữa GET và POST:

~~~text
Client A:
  GET /csrf
    -> ghi nhận cookie SESSION=A
    -> ghi nhận headerName, tokenA
  POST /profile/email
    Cookie: SESSION=A
    CSRF headerName: tokenA
    -> qua CSRF nếu token/handler tương thích

  POST /profile/email
    Cookie: SESSION=A
    bỏ CSRF header
    -> bị từ chối

Client B:
  GET /csrf
    -> SESSION=B, tokenB

Client A:
  POST /profile/email
    Cookie: SESSION=A
    CSRF headerName: tokenB
    -> bị từ chối với token repository gắn theo WebSession
~~~

Một `WebTestClient` được bind vào application context là công cụ test server, **không tự bảo đảm ghi nhớ và gửi lại mọi cookie như browser**. Nếu viết test theo nhiều bước, phải dùng cơ chế cookie/state rõ ràng trong test client hoặc đưa qua cookie nhận từ response trước. Với browser automation, dùng **browser context riêng cho A và B** để tránh gộp session.

## 11. Bài test đầy đủ phải có login/logout

### 11.1. POST login có thể cần CSRF trước khi người dùng xác thực

Login CSRF có thể ép browser đăng nhập vào **tài khoản do attacker kiểm soát**. Với form login Spring Security thông thường, `POST /login` phải mang CSRF token ngay cả khi chưa xác thực.

| Request | Credential trước request | Submitted token | Điều cần xác minh |
|---|---|---|---|
| `GET /login` | Chưa đăng nhập | Không cần token để GET | Trang render form có token hợp lệ |
| `POST /login` với credentials đúng | Pre-auth session | **Đúng** | Qua CSRF, login theo chính sách |
| `POST /login` với credentials đúng | Pre-auth session | **Thiếu** | Không tạo phiên đăng nhập |
| `POST /login` với credentials đúng | Pre-auth session | **Sai** | Không tạo phiên đăng nhập |
| `POST /login` credentials sai | Pre-auth session | **Đúng** | Qua CSRF nhưng thất bại ở authentication |

Một request login trả redirect không tự chứng minh nó được xác thực thành công. Cần kiểm tra **đích redirect và trạng thái xác thực** sau request. Test credentials sai với token đúng rất hữu ích để tách “CSRF từ chối” với “authentication từ chối”.

### 11.2. POST logout: token thiếu không được logout

| Request | Session hiện tại | Token | Điều cần xác minh |
|---|---|---|---|
| `POST /logout` | User A đang login | Đúng | Logout xảy ra theo cấu hình |
| `POST /logout` | User A đang login | Thiếu | Request bị chặn; phiên A vẫn còn xác thực |
| `POST /logout` | User A đang login | Sai | Request bị chặn; phiên A vẫn còn xác thực |
| `GET /logout` | User A đang login | Không | Trong cấu hình chuẩn có thể hiển thị trang xác nhận, **không logout ngay** |

Với WebFlux, logout có thể dọn security context nhưng không mặc nhiên hủy **toàn bộ WebSession** trong mọi cấu hình. Vì vậy **kiểm tra kết quả đăng xuất thực tế** (khả năng truy cập endpoint bảo vệ sau logout, session policy) thay vì chỉ quan sát redirect.

### 11.3. Token cũ sau đăng nhập/đăng xuất

Spring Security có cơ chế dọn CSRF token ở các ranh giới xác thực. Với deferred token, một SPA có thể:

1. Lấy token `T_before` ở trang login.
2. Gửi POST login có token `T_before` thành công.
3. Tài liệu session/token repository có thể xóa expected token cũ.
4. SPA gửi ngay POST nghiệp vụ với `T_before` và bị `403`.
5. SPA lấy token `T_after` mới rồi POST thành công.

**Test đúng cần xét toàn bộ vòng đời**, không chỉ “token cũ luôn sai trong mọi cấu hình”. Nếu ứng dụng không làm mới token theo giả thiết trên, cần hiểu repository và authentication strategy đang dùng trước khi viết assertion.

## 12. Khi repository là cookie: test thêm raw/masked và phạm vi cookie

Đối với SPA, có thể sử dụng `CookieCsrfTokenRepository` (Servlet) hoặc `CookieServerCsrfTokenRepository` (Reactive). Ví dụ browser nhận cookie `XSRF-TOKEN` rồi JavaScript gửi `X-XSRF-TOKEN`.

### 12.1. Các ca bổ sung

| ID | Cookie CSRF | Header CSRF | Kỳ vọng cần kiểm chứng |
|---|---|---|---|
| **SPA-01** | Token được server phát | Header raw đúng, handler phù hợp | Request qua CSRF |
| **SPA-02** | Cookie có token | Header **thiếu** | Request bị từ chối |
| **SPA-03** | Cookie có token | Header **sai** | Request bị từ chối |
| **SPA-04** | Không có cookie CSRF | Header tự bịa | Bị từ chối theo repository/policy |
| **SPA-05** | Cookie/header có giá trị trùng nhau | Handler đòi masked form token | Có thể bị từ chối nếu cấu hình không khớp |
| **SPA-06** | Token cũ sau login/logout | Header còn dùng token cũ | Phải theo vòng đời token; client cần nhận token mới khi đã invalidate |
| **SPA-07** | Cookie bị thay từ subdomain ít tin cậy | Header tương ứng | Đánh giá cookie injection/duplicate cookie và signed session binding nếu có |
| **SPA-08** | Cookie csrf khác Domain/Path với session cookie | Header đúng | Kiểm tra browser có gửi cookie đúng request không |

### 12.2. Không áp thuộc tính cookie giống nhau một cách máy móc

- **Session cookie xác thực:** Thường nên `HttpOnly; Secure` với `SameSite` và scope phù hợp.
- **Cookie CSRF để SPA đọc bằng JavaScript:** Có thể cần **không HttpOnly**, nhưng phải hạn chế host/path, xem XSS và có cơ chế cấp token an toàn.
- **Header CSRF:** Do JavaScript ứng dụng chủ động gửi, **khác** cookie được browser tự gắn.
- **Raw vs masked:** Header đúng tên nhưng sai biểu diễn có thể `403`; bài test phải dùng đúng handler.
- **HMAC signed double-submit:** Là thiết kế riêng có kiểm chứng chữ ký và ràng buộc phiên; `CookieCsrfTokenRepository` thông thường không tự thực hiện toàn bộ mô hình này.

Không “sửa” SPA lỗi CSRF bằng cách tắt filter trên `/api/**` khi API vẫn nhận credential cookie.

## 13. Kiểm thử trình duyệt thật: khác với helper framework

### 13.1. Browser E2E cần những bước nào?

Trong môi trường được phép:

1. **Login hoặc tạo pre-auth session A.** Lưu cookie thực tế từ `Set-Cookie`; kiểm tra `Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path`.
2. **GET trang form hoặc `/csrf`.** Lấy submitted token và tên field/header từ **response thật**; không chép token từ một lần chạy trước.
3. **POST với cùng browser session A + token đúng.** Kiểm tra hành động được thực hiện đúng một lần khi đủ quyền.
4. **POST với session A nhưng bỏ token.** Kiểm tra bị từ chối và **không có side effect**.
5. **POST với session A và token sai.** Kiểm tra bị từ chối và trạng thái dữ liệu không đổi.
6. **Tạo session B độc lập.** Lấy token B, dùng token B cùng session A rồi kiểm tra bị từ chối nếu repository yêu cầu session binding.
7. **Thử JSON/header riêng với form/parameter.** Ghi nhận tên header, định dạng raw/masked, cookie CSRF nếu có.
8. **Thử POST sau login/logout/timeout.** Token cũ bị xử lý theo chính sách và frontend biết cách nhận token mới.
9. **Thử route khác security chain** và các endpoint có tác động bằng `PUT`/`PATCH`/`DELETE`.
10. **Quan sát trên origin khác:** Phân biệt same-site cross-origin với cross-site, cookie tự gửi và CORS preflight; request không có token vẫn phải bị kiểm soát nếu đến server với credential.

Các bước test cần dùng **tài khoản và dữ liệu giả**, không thực hiện request tác động lên production. Token và cookie trong bản ghi HAR cần được làm mờ trước khi chia sẻ.

### 13.2. Phân biệt browser gửi cookie với client tự gắn cookie

cURL hoặc Postman có thể tự viết:

~~~http
Cookie: JSESSIONID=SESSION_A
~~~

Điều đó rất tốt để kiểm tra **server-side token logic** nhưng **không chứng minh** browser sẽ gửi cookie trong một request cross-site cụ thể. SameSite phụ thuộc browser, ngữ cảnh điều hướng và chính sách cookie. Bài E2E cần chạy trình duyệt thật hoặc browser automation phù hợp.

### 13.3. Một phác thảo test dùng browser context riêng

~~~text
Browser Context A:
    GET /login hoặc /csrf -> lưu cookie session A, token A
    POST protected endpoint + token A -> kỳ vọng qua CSRF
    POST protected endpoint không token -> kỳ vọng từ chối

Browser Context B:
    GET /login hoặc /csrf -> cookie session B, token B

Browser Context A:
    POST protected endpoint + token B -> kỳ vọng từ chối

Sau mỗi negative case:
    GET/DB check -> email/theme/quyền/số dư không đổi
~~~

Hai browser context phải **không chia sẻ cookie jar/storage state**. Nếu dùng tab trong **cùng** browser context, các tab có thể dùng chung session cookie; như vậy “token A và token B” không nhất thiết thuộc hai phiên khác nhau.

## 14. Thiết kế kết quả kiểm thử để phát hiện lỗi cấu hình

Một test suite có giá trị phải thất bại nếu developer:

- Đặt `csrf(csrf -> csrf.disable())` cho chain dùng cookie.
- Thêm `ignoringRequestMatchers("/api/**")` mà trong đó có endpoint dùng cookie.
- Chuyển `POST /logout` thành `GET /logout` thực hiện ngay.
- Đổi tên `_csrf`/`X-CSRF-TOKEN` nhưng không sửa frontend.
- Chuyển `HttpSessionCsrfTokenRepository` sang cookie repo nhưng quên handler SPA.
- Không cấp CSRF token mới sau xác thực hoặc vô hiệu hóa token cũ.
- Đưa GET có side effect vào ứng dụng.
- Để security chain API đứng trước chain web với matcher quá rộng.
- Chấp nhận Bearer và cookie fallback nhưng miễn CSRF vì tưởng API “stateless”.
- Cho phép Origin/CORS quá rộng để site ngoài đọc token từ endpoint cấp token.

**Quy tắc regression:** Mỗi lần thay bảo mật nên làm chạy lại không chỉ positive case, mà cả **missing, wrong, wrong-session, wrong-channel và endpoint ngoài route chính**.

## 15. Gỡ lỗi: vì sao test trả 403?

| Triệu chứng | Nguyên nhân có thể | Cách kiểm chứng |
|---|---|---|
| POST đúng token nhưng `403` | Authentication/authorization thất bại | Kiểm tra principal, role, security chain, AccessDeniedHandler |
| POST thiếu token nhưng trả redirect login | Authentication entry point xử lý trước/trong luồng | Dùng user test đã xác thực và quan sát security filter |
| Header có token nhưng `403` | Header name sai hoặc raw/masked handler không tương thích | Đối chiếu `CsrfToken.getHeaderName()` và request handler |
| Form token của GET rồi POST `403` | GET/POST dùng **hai session khác nhau** | Kiểm tra cookie `JSESSIONID`/`SESSION` giữa hai bước |
| Chỉ lỗi sau login/logout | Token cũ bị xóa hoặc đã rotate | Lấy token mới và đối chiếu request thực |
| Chỉ lỗi với SPA | Cookie `XSRF-TOKEN` chưa phát, JS không đọc được hoặc gửi sai header | Kiểm tra cookie scope, deferred token, handler và headers |
| POST không token vẫn được xử lý | CSRF bị tắt, matcher bỏ qua hoặc request đi qua chain khác | Kiểm tra chain/matcher, endpoint/method và test tác động nghiệp vụ |
| GET thiếu token được xử lý | GET là **safe method** theo mặc định | Xác nhận GET chỉ đọc; không phải bug CSRF nếu đúng ngữ nghĩa |
| JSON có `_csrf` nhưng `403` | Request handler không tìm token trong JSON property | Gửi qua header CSRF đúng |
| Browser báo CORS error | Preflight/credentials/origin policy | Kiểm tra POST thật có đến server không; không đánh đồng CORS với CSRF |
| HTTP client test pass nhưng browser không có cookie | SameSite, Secure, Domain, Path, third-party cookie policy | Dùng Network DevTools |
| `MockMvc` pass nhưng E2E fail | Test helper bỏ qua lỗi render token/cookie thực | Thêm GET → lấy token → giữ session → POST thật |
| Token A dùng cho phiên B vẫn được chấp nhận | Repository hoặc thiết kế token không bind session; hoặc test không thực sự tách session | Kiểm tra repository, hai cookie jar và yêu cầu binding thực tế |

**Không log giá trị thật của session ID, CSRF token hoặc access token để gỡ lỗi**. Những thông tin phù hợp hơn: request method/path, filter chain, token có/không, tên header/parameter, cookie có/không, exception class và mã lỗi.

### 15.1. Missing và InvalidCsrfTokenException

Ở Spring Security Servlet có thể gặp:

- `MissingCsrfTokenException` khi token không có ở những ngữ cảnh phù hợp;
- `InvalidCsrfTokenException` khi có submitted token nhưng không hợp lệ.

Không nên dựa vào **một exception class duy nhất** để thay kiểm tra hành vi nghiệp vụ, vì repository, handler và cách xử lý lỗi có thể thay đổi theo phiên bản/cấu hình. Với Reactive, xem luồng `CsrfWebFilter` và các access-denied xử lý tương ứng.

### 15.2. Không ép status 403 cho mọi cấu hình

`403 Forbidden` là kết quả điển hình khi CSRF không hợp lệ, nhưng ứng dụng có thể dùng custom AccessDeniedHandler, authentication entry point hoặc trả JSON lỗi có mã riêng. Test nên:

- Xác định policy response đã thống nhất (thường `403`);
- Assert response theo hợp đồng đó;
- **Luôn** assert không có side effect khi CSRF bị từ chối;
- Không bỏ qua khác biệt giữa CSRF failure và authorization failure.

## 16. Cấu trúc bộ test theo tầng

| Tầng | Công cụ | Kiểm tra tốt nhất | Điều không thể tự kết luận |
|---|---|---|---|
| **Security filter test** | `MockMvc` + `spring-security-test` | Valid/missing/invalid form/header, matcher, chain | Cookie SameSite và token frontend render thật |
| **Reactive security test** | `WebTestClient` + `spring-security-test` | CSRF WebFilter, authorization và HTTP status | Browser tự gửi cookie theo SameSite |
| **HTTP integration** | Client có cookie jar rõ ràng | GET token → POST với cùng session, session binding, invalidation | Browser cross-site policy nếu tự gắn Cookie |
| **Browser E2E** | Browser DevTools/automation | Form thực, cookies, CORS, SPA raw/masked, login/logout | Chữ ký/HMAC nội bộ nếu không có kiểm thử server riêng |
| **Service/repository integration** | Test database/fake service | Không có ghi dữ liệu hay event sau negative case | Frontend render/behavior thực |
| **Security review** | Đọc config và review luồng auth | CSRF exceptions, BFF/cookie fallback, trusted origins | Runtime policy nếu không có regression tests |

### 16.1. Đề xuất cấu trúc regression suite

~~~text
csrf/
  expected-value/
    valid-form
    valid-header
  missing/
    missing-form
    missing-header
    empty-value
  invalid/
    random-value
    mutated-value
    wrong-session
    wrong-format
  lifecycle/
    after-login
    after-logout
    expired-session
  routes/
    protected-post-put-patch-delete
    safe-get-no-side-effect
    login-logout
    chain-boundary
  browser/
    same-site-subdomain
    cross-site-form
    spa-cookie-header
    cors-preflight
~~~

Đây là **gợi ý tổ chức ca kiểm thử**, không nhất thiết là tên file hoặc class bắt buộc. Trên mỗi nhóm, giữ dữ liệu rõ ràng, mức độ tích hợp phù hợp và thông báo thất bại giúp truy nguyên nhanh.

## 17. Bài tập thực hành

### Bài tập 1: Lập ma trận cho ứng dụng form

Ứng dụng có `GET /account/edit` và `POST /account/email`, xác thực bằng `JSESSIONID` và lưu CSRF token theo `HttpSession`.

Hãy viết ít nhất sáu test: form đúng, thiếu, sai, token thuộc phiên khác, request GET chỉ đọc, POST đúng token nhưng user không có quyền. Với negative cases, kiểm tra **email trước/sau**.

**Gợi ý đáp án:** Token của GET phải dùng đúng session; thiếu và sai đều bị từ chối; token B với session A bị từ chối; GET không làm thay đổi email; đúng CSRF token không vượt qua authorization.

### Bài tập 2: Xác định vì sao header token bị từ chối

SPA đọc cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN`, nhưng server vẫn trả `403`. Bạn cần quan sát và kiểm tra những gì?

**Gợi ý đáp án:** Cookie CSRF đã được cấp chưa, scope/HttpOnly có cho JS đọc không, header name chính xác không, handler có mong đợi raw hay masked, request có cookie phiên đúng không, token có bị invalidated sau login/logout không, và lỗi có thực sự phát sinh ở CSRF filter không.

### Bài tập 3: Bắt lỗi khi một API đổi sang JWT

Nhóm đổi backend sang JWT. Access token lúc đầu được SPA gắn vào `Authorization`; sau đó chuyển sang cookie HttpOnly để giảm nguy cơ JS đọc token và bỏ CSRF vì cho rằng “JWT stateless”.

**Gợi ý đáp án:** Cách truyền credential đã đổi: browser có thể tự gắn JWT cookie. Cần đánh giá lại CSRF, áp token/defense phù hợp cho unsafe requests, kiểm thử cookie-only missing/wrong token và giữ các lớp XSS/session protection.

### Bài tập 4: Test dương tính qua bước CSRF nhưng vẫn 403

Test `with(csrf())` trả `403` ở endpoint yêu cầu quyền `ROLE_ADMIN`; mock principal chỉ có `ROLE_USER`. Có thể kết luận CSRF filter sai không?

**Gợi ý đáp án:** Không. CSRF token đúng có thể đã qua filter, sau đó authorization chặn. Hãy cấp quyền phù hợp cho test dương tính và có test riêng xác minh phân quyền từ chối.

### Bài tập 5: Thiết kế test phiên A/B trong Reactive

Dùng `GET /csrf` của WebFlux để lấy hai token với hai WebSession độc lập, rồi POST bằng cookie A với token B. Nếu expected token lưu theo `WebSession`, điều gì phải xảy ra?

**Gợi ý đáp án:** Request bị từ chối và không có side effect. Test phải đảm bảo session A/B thật sự khác nhau (hai cookie jar/browser contexts), không phải hai tab chung session.

## Kết luận

Để kiểm thử CSRF có ý nghĩa, **ba trạng thái token đúng, thiếu, sai là bắt buộc nhưng chưa đủ**. Test phải xác định expected token được repository quản lý ở đâu, submitted token được form/header gửi như thế nào, request handler có masking/raw token ra sao, và session/credential nào đang được browser sử dụng. Với synchronizer token, test hoán đổi session A/B đặc biệt quan trọng.

Spring Security **Servlet** cho phép tạo test nhanh bằng `MockMvc`, `csrf()`, `csrf().asHeader()` và `csrf().useInvalidToken()`. **Reactive/WebFlux** dùng `WebTestClient` cùng `springSecurity()`, `mockUser()` và `csrf()` để kiểm tra web filter. Tuy nhiên các helper **không thay** E2E lấy token thực qua GET, giữ cookie/session, kiểm tra login/logout, SPA và CORS trên browser.

**Kết quả cần bảo đảm là request ghi thiếu hoặc sai token không thể gây tác động nghiệp vụ**, trong khi request đúng token và đủ quyền vẫn hoạt động. Kết hợp bộ test này với kiểm soát phương thức HTTP, session security, CORS, CSP, HSTS, security headers và HTTP firewall giúp module **SPRING_SECURITY_HTTP_PROTECTION** có phòng vệ nhiều lớp có thể xác minh và bảo trì.

## Tài liệu tham khảo

- [Spring Security — CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): token repository, request handler, masking, SPA và matcher.
- [Spring Security — CSRF Testing (Servlet)](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `csrf()`, `asHeader()` và `useInvalidToken()`.
- [Spring Security — CSRF Protection (WebFlux)](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): CSRF web filter và token repository của Reactive.
- [Spring Security — WebTestClient CSRF Test](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `SecurityMockServerConfigurers.csrf()`.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): threat model, synchronizer/double-submit, SameSite và phòng vệ bổ trợ.
