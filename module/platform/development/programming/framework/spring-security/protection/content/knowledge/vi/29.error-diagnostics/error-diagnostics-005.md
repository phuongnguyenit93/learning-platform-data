# Token cũ sau đăng nhập, đăng xuất hoặc đổi phiên

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Một lỗi 403 chỉ xuất hiện *sau khi* người dùng đăng nhập

Ứng dụng Spring Boot dùng session cookie cho web UI và CSRF protection cho các request thay đổi trạng thái. Một chuỗi thao tác điển hình:

~~~text
12:00  GET /csrf              -> token A
12:01  POST /login            -> đăng nhập thành công
12:01  POST /profile          -> 403 Forbidden
12:02  GET /csrf              -> token B
12:02  POST /profile          -> 204 No Content
~~~

Điểm đáng chú ý: request `POST /profile` lần đầu **có gửi token A**, nhưng token đó được lấy trước khi authentication thay đổi trạng thái. Nếu CSRF token cũ đã bị xóa/invalidate khi đăng nhập thành công, server sẽ không còn chấp nhận token A.

Tình huống tương tự có thể xảy ra:

- Sau **logout**: cookie hoặc session cũ bị xóa; giao diện vẫn giữ token của phiên trước.
- Sau **đăng nhập lại**: tab cũ gửi form với hidden token từ trước khi session chuyển trạng thái.
- Sau **session timeout**: trình duyệt còn HTML/SPA state nhưng server đã không còn phiên tương ứng.
- Sau **session fixation protection**: session ID có thể đổi hoặc session được thay thế; token CSRF có thể bị clear tùy cơ chế.
- Sau **SSO/OAuth2 redirect**: ứng dụng có authentication mới nhưng AJAX client vẫn giữ token từ anonymous context.
- Sau **chuyển node/cookie path thay đổi**: server xử lý POST không tìm thấy trạng thái CSRF mà GET trước đó đã sử dụng.

**Mục tiêu:** chẩn đoán chính xác lúc CSRF token bị stale, phân biệt token bị invalidate với token chỉ đổi biểu diễn vì masking chống BREACH, xây luồng làm mới token an toàn cho Spring Security **Servlet** và **Reactive/WebFlux**, và kiểm thử cả đường authentication lẫn các request nghiệp vụ.

## 2. Phân biệt CSRF token, authentication token và session ID

Một lỗi phổ biến trong ticket là dùng từ “token” cho ba thứ khác nhau:

| Dữ liệu | Ví dụ | Vai trò | Điều xảy ra khi đăng nhập/đổi phiên |
|---|---|---|---|
| **CSRF token** | Hidden input `_csrf`, header `X-CSRF-TOKEN` | Chứng minh request thay đổi trạng thái có giá trị bí mật được server cấp trong ngữ cảnh phù hợp | Có thể bị clear/rotate, cần cấp hoặc tải lại |
| **Session ID** | Cookie `JSESSIONID` hoặc cookie session khác | Xác định phiên server của browser | Có thể được đổi khi login để chống session fixation |
| **Authentication credential** | Basic credentials, Bearer access token, authentication state trong session | Xác thực người dùng | Login tạo authentication; logout xóa, token Bearer có vòng đời riêng |

CSRF token **không phải access token**; không gửi nó vào `Authorization: Bearer ...`. Ngược lại, một access token hợp lệ không làm token CSRF của form tự trở thành hợp lệ, đặc biệt nếu ứng dụng còn dựa vào cookie/session để xác thực.

### Hai lỗi mang cùng HTTP status

~~~text
POST /profile, session còn hợp lệ
  -> thiếu CSRF token hiện hành
  -> CsrfFilter/CSRF validation từ chối, thường 403

POST /profile, CSRF hợp lệ
  -> user không có ROLE_USER hoặc không sở hữu profile
  -> authorization/method security từ chối, thường 403
~~~

Vì thế không kết luận “token đã hết hạn” chỉ vì frontend thấy 403. Phải xác định filter/handler, exception và authentication state.

## 3. Dòng đời CSRF token và các sự kiện chuyển trạng thái

Trong ứng dụng dùng CSRF repository, có thể tư duy theo những trạng thái sau:

~~~mermaid
stateDiagram-v2
    [*] --> ChuaMaterialize: Khởi tạo request/phiên
    ChuaMaterialize --> HienHanh: GET form hoặc GET /csrf truy cập token
    HienHanh --> HienHanh: POST hợp lệ với token hiện hành
    HienHanh --> TokenCu: Authentication/logout xóa token
    HienHanh --> TokenCu: Session hết hạn hoặc repository không còn state
    TokenCu --> HienHanh: Bootstrap token mới trong ngữ cảnh mới
    TokenCu --> BiTuChoi: POST tiếp tục dùng token cũ
    BiTuChoi --> HienHanh: Tải token mới và xác thực hợp lệ
~~~

Đây là mô hình chẩn đoán **không phải state machine cứng của mọi Spring Security configuration**. Repository có thể lưu token trong session, cookie hoặc storage custom; token được mask có thể thay biểu diễn mà underlying token chưa bị xóa.

### Bốn sự kiện cần theo dõi riêng

1. **Issue/materialize:** token được tạo hoặc tải từ repository khi được yêu cầu.
2. **Expose:** token được đưa đến template HTML, endpoint JSON hoặc cookie để client sử dụng.
3. **Invalidate/clear:** expected token bị xóa hoặc không còn áp dụng do login, logout, phiên hết hạn hay cơ chế khác.
4. **Re-bootstrap:** client nhận token phù hợp với ngữ cảnh mới **trước khi gửi yêu cầu thay đổi trạng thái tiếp theo**.

Nếu thiếu bước 4, frontend có thể tiếp tục gửi đúng header name và đúng kiểu dữ liệu, nhưng đó vẫn là **giá trị cũ**.

## 4. Spring Security Servlet: tại sao authentication có thể xóa CSRF token?

Trong Spring Security Servlet, các thành phần cần hiểu:

- `CsrfFilter`: thực thi CSRF protection cho request cần bảo vệ.
- `CsrfTokenRepository`: tải/tạo/lưu token, ví dụ `HttpSessionCsrfTokenRepository` hoặc `CookieCsrfTokenRepository`.
- `CsrfTokenRequestHandler`: expose và resolve giá trị client gửi, có thể sử dụng masking.
- `CsrfAuthenticationStrategy`: chiến lược có thể xóa CSRF token cũ khi quá trình authentication thành công.
- `CsrfLogoutHandler`: xử lý xóa CSRF token khi logout theo cấu hình Spring Security.
- `SessionAuthenticationStrategy` và `SessionManagementFilter` hoặc cơ chế authentication tương ứng: liên quan tới session và các chiến lược khi authentication thay đổi.

Tùy phiên bản và cách cấu hình authentication filter, các chiến lược được nối vào luồng khác nhau. Điều cần kiểm tra là **sự kiện authentication thành công có thực sự gọi cơ chế xóa CSRF token của ứng dụng hiện tại hay không**, thay vì giả định chỉ dựa vào phiên bản được ghi trong dependency.

### Mô phỏng một lần đăng nhập

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant S as Spring Security Servlet
    participant R as CsrfTokenRepository
    U->>S: GET /login
    S->>R: Resolve/generate CSRF token A khi form cần
    R-->>S: Expected token A
    S-->>U: HTML login với token A
    U->>S: POST /login kèm token A, username/password
    S->>R: Validate token A
    S->>S: Authentication success
    S->>R: Clear token cũ nếu configured strategy áp dụng
    S-->>U: Redirect/cookie session mới hoặc cập nhật
    U->>S: POST /profile kèm token A (stale)
    S->>R: Resolve expected token mới/khác
    S-->>U: 403 nếu không khớp
    U->>S: GET /csrf trong ngữ cảnh mới
    S->>R: Resolve/generate token B
    S-->>U: Token B
~~~

Việc dùng **token A để xác thực request login** và **không tiếp tục dùng A sau authentication success** không mâu thuẫn. Token A hợp lệ **tại thời điểm POST login được kiểm tra**; sau đó chiến lược authentication có thể invalidates nó.

### Ngữ nghĩa quan trọng

**CSRF invalidation sau login không đồng nghĩa authentication thất bại.** Login có thể thành công, session và principal đều hợp lệ, nhưng AJAX đầu tiên sau login nhận 403 chỉ vì ứng dụng không cấp/đọc token mới.

## 5. Logout: request logout cũng có thể cần CSRF token hiện hành

Trong ứng dụng dùng Spring Security logout endpoint trên Servlet, HTTP POST logout thường được CSRF protection bảo vệ khi CSRF được bật. Một giao diện:

~~~html
<form action="/logout" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Khi request logout **được chấp nhận**, quá trình logout có thể:

- Xóa authentication khỏi security context.
- Invalidate HTTP session theo cấu hình.
- Xóa/clear CSRF token cũ qua logout handler.
- Xóa hoặc ghi đè cookie có liên quan; hành vi cụ thể phụ thuộc cấu hình và repository.

**Trình tự hợp lệ:**

~~~text
GET /account -> form/SPA nhận CSRF token hiện hành
POST /logout kèm token đó -> logout success
Browser xóa CSRF state phía frontend
GET /login hoặc GET /csrf mới -> token cho ngữ cảnh anonymous mới
POST /login theo luồng bảo vệ phù hợp
~~~

Nếu SPA sau logout vẫn giữ token của user trước, một request mới có thể thất bại hoặc gửi một giá trị không còn phù hợp. **Không dùng GET logout hoặc tắt CSRF để làm logout dễ gọi hơn** khi ứng dụng đang dựa vào cookie/browser authentication.

## 6. Session fixation: đổi session ID khác với mất toàn bộ session

Sau login, Spring Security thường dùng biện pháp chống **session fixation** để không tiếp tục dùng session ID đã biết trước khi authentication. Nhưng có nhiều chiến lược:

| Chiến lược/hiện tượng | Điều có thể thay đổi | Không được kết luận tự động |
|---|---|---|
| `changeSessionId()` | Session ID thay đổi, session object/attributes có thể được duy trì | “Mọi session attribute và CSRF token đã mất” |
| `migrateSession()` | Session mới, attributes có thể được chuyển | “CSRF token chắc chắn vẫn còn hiệu lực” |
| `newSession()` | Session mới với dữ liệu được giữ theo chính sách cụ thể | “Authentication và CSRF chắc chắn giống phiên cũ” |
| `Session.invalidate()` | Phiên cũ bị hủy | “Client đã nhận token mới ngay lập tức” |
| Token repository cookie-based | Expected token không nhất thiết nằm trong HttpSession | “Đổi JSESSIONID tự làm raw cookie CSRF thay đổi” |

**Hai cơ chế độc lập có thể xảy ra đồng thời:** session fixation protection thay đổi session ID **và** CSRF authentication strategy xóa token. Muốn biết tại sao POST sau login 403, phải xem cả hai.

### Ví dụ chẩn đoán

~~~text
Trước login:
  session cookie ID A
  CSRF expected token R1

Sau login:
  session cookie ID B
  session attributes có thể được migrate
  CSRF expected token R1 có thể đã bị clear bởi auth strategy

POST dùng token R1:
  => Không hợp lệ nếu expected token đã bị invalidate
~~~

**Không sửa lỗi CSRF bằng cách tắt session fixation protection.** Cách đúng là làm mới CSRF token cho ngữ cảnh hiện hành, rồi kiểm thử lại đăng nhập và các thao tác thay đổi dữ liệu.

## 7. Deferred/lazy CSRF: token mới có thể chưa được tạo ngay sau login

Spring Security hiện đại có thể trì hoãn việc resolve/generate CSRF token. Điều này làm xuất hiện một tình huống đặc biệt:

~~~text
POST /login thành công
  -> clear expected CSRF token cũ
  -> response redirect hoặc JSON không truy cập CSRF token mới

Frontend đọc cookie XSRF-TOKEN
  -> cookie cũ có thể đã bị xóa
  -> không có token mới ngay trong response login

Frontend gửi POST /profile
  -> thiếu token hoặc token cũ
  -> 403
~~~

Đó không nhất thiết là bug của CSRF repository. **Frontend chưa có bước bootstrap token mới**. Nếu muốn token sẵn sàng ngay sau login, ứng dụng có thể:

1. Redirect tới trang server-rendered có form thực sự truy cập `_csrf.token`.
2. Cho SPA gọi `GET /csrf` sau authentication thành công.
3. Với chiến lược cookie raw cho SPA, dùng một handler/endpoint đã được thiết kế để materialize deferred token sau login/logout.

Không giả định mỗi GET tự tạo một token mới. Với cơ chế deferred, token chỉ cần materialize khi frontend thực sự yêu cầu; tạo session/token dư thừa trên mọi tài nguyên tĩnh không phải mục tiêu.

## 8. Masking chống BREACH không phải token rotation

Spring Security Servlet hiện đại thường expose CSRF token dưới dạng được **mask** bằng `XorCsrfTokenRequestAttributeHandler` để giảm rủi ro lộ secret qua phản hồi nén (*BREACH*).

Một underlying token R có thể được trình bày bằng nhiều biểu diễn:

~~~text
Repository token:           R
GET /profile lần 1:         masked(R, mask1) -> M1
GET /profile lần 2:         masked(R, mask2) -> M2

M1 != M2
nhưng M1 và M2 đều có thể được server chấp nhận
nếu expected token R vẫn đang là token hiện hành.
~~~

Đừng dùng test:

~~~java
assertNotEquals(firstHtmlToken, secondHtmlToken);
~~~

để **chứng minh** CSRF token đã rotate khi login. Hai chuỗi khác nhau có thể chỉ vì mỗi response được mask lại.

### Test đúng để phát hiện token cũ

Giữ cùng repository/session và handler:

1. Lấy token trước login; chứng minh nó hợp lệ **trước** sự kiện authentication.
2. Đăng nhập thành công bằng request hợp lệ.
3. Thử lại **giá trị token cũ** trên một POST được CSRF bảo vệ; kết quả có thể bị từ chối nếu token đã invalidate.
4. Lấy token mới trong ngữ cảnh sau login; POST với token mới phải qua CSRF validation.
5. Dùng log/handler phân biệt CSRF rejection với authorization/controller.

Đây mới là phép thử **hiệu lực theo thời điểm**, thay vì so sánh hai chuỗi bị mask.

## 9. HttpSessionCsrfTokenRepository và CookieCsrfTokenRepository sau đổi phiên

CSRF repository quyết định **expected token nằm ở đâu**, nên cùng một chuỗi sự kiện login/logout có thể tạo các biểu hiện khác nhau.

| Nội dung | `HttpSessionCsrfTokenRepository` | `CookieCsrfTokenRepository` |
|---|---|---|
| Vị trí expected token | Attribute trong HTTP session | Cookie CSRF |
| Dấu hiệu phía browser | Hidden input/JSON token và cookie session | Có thể thêm `XSRF-TOKEN` cookie |
| Sau session timeout | Expected token cũ không còn trong session | Cookie CSRF có thể vẫn còn nhưng auth/session không còn |
| Sau login/logout | Có thể bị xóa bởi authentication/logout strategy | Cookie CSRF có thể được xóa qua `Set-Cookie` |
| SPA nhận giá trị | Template hoặc endpoint GET `/csrf` | Đọc cookie nếu cho phép, hoặc endpoint |
| Điểm cần kiểm tra | Session ID và underlying session state | Cookie raw, phạm vi và handler hiểu raw/masked |

### Lưu ý về cookie còn nhưng phiên đã mất

Browser có thể giữ một cookie `XSRF-TOKEN` từ trước nhưng `JSESSIONID` đã hết hạn. Điều đó **không chứng minh người dùng còn authenticated**, cũng không bảo đảm token CSRF phải được chấp nhận. Auth/session và CSRF là hai lớp riêng.

Trong chiến lược cookie CSRF, expected token có thể không trực tiếp phụ thuộc HttpSession. Vì vậy không suy rằng đổi `JSESSIONID` **tự động** làm cookie token không hợp lệ. Cần kiểm tra logout/login handlers có clear cookie hay không và response `Set-Cookie` thực tế.

## 10. Cookie scope: token cũ hay browser gửi nhầm phiên?

Giả sử GET form ở:

~~~text
https://app.example.com/profile
~~~

nhưng POST được gửi tới:

~~~text
https://api.example.com/profile
~~~

Browser có thể có cookie session chỉ dành cho host `app.example.com` và không gửi sang `api.example.com`. Khi đó server API không thể tải expected token theo cùng phiên, dù JavaScript vẫn giữ giá trị token đúng từ trang ban đầu.

| Thuộc tính | Ảnh hưởng tới luồng token | Hướng kiểm tra |
|---|---|---|
| `Domain`/host-only | Cookie chỉ đến những hostname phù hợp | Request Cookie của GET và POST |
| `Path` | Cookie chỉ đến các path phù hợp | POST sau proxy rewrite có còn thuộc Path? |
| `Secure` | Cookie chỉ gửi trên giao thức bảo mật phù hợp | HTTPS public và TLS termination |
| `SameSite` | Hạn chế cookie trong một số tình huống cross-site | Navigation, iframe, fetch khác site |
| `HttpOnly` | JavaScript không đọc cookie trực tiếp | SPA dùng raw-cookie strategy hay GET JSON? |
| `Max-Age`/`Expires` | Cookie có thể hết hạn độc lập với state ở server | So sánh thời điểm cấp và thời điểm POST |
| `credentials` của `fetch` | Quyết định browser gửi/nhận credentials phù hợp | `same-origin` hay `include` theo kiến trúc |

**Same-origin và same-site không phải một.** Hai subdomain có thể cùng site trong một số quy tắc cookie nhưng vẫn là cross-origin đối với CORS. Browser còn có chính sách third-party cookies riêng.

### Các biến thể cần tách

1. **Raw token cũ:** token từ repository đã bị clear/rotate.
2. **Session cookie thiếu:** browser không gửi `JSESSIONID` hoặc cookie tương ứng.
3. **Cookie CSRF bị giữ cũ:** raw `XSRF-TOKEN` không được refresh sau authentication.
4. **Cookie trùng tên khác Path/Domain:** JavaScript và backend có thể đọc các cookie khác nhau nếu cấu hình không nhất quán.
5. **Header CSRF bị proxy loại bỏ:** frontend gửi nhưng upstream không thấy.

Không mở rộng Domain toàn site, tắt `Secure` hoặc chuyển sang `SameSite=None` chỉ để làm test xanh. Những thay đổi đó phải phù hợp trust boundary và security review.

## 11. Servlet: cấu hình ứng dụng có login, logout và CSRF

Ví dụ một ứng dụng Spring MVC dùng form login/session:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SessionSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
            .requestMatchers("/login", "/css/**", "/js/**").permitAll()
            .requestMatchers("/profile/**").authenticated()
            .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Chương trình giả định có user store và handler `/profile`. Nếu có nhiều `SecurityFilterChain`, cần xác định chain thực sự xử lý `GET /csrf`, `POST /login`, `POST /logout` và `POST /profile`; một chain khác có thể có repository/handler khác.

**Không tắt CSRF cho toàn ứng dụng** chỉ vì frontend chưa lấy token mới sau login. Ở flow dùng cookie session, CSRF là lớp phòng vệ thiết yếu cho các request thay đổi trạng thái.

### Controller bootstrap token

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfBootstrapController {

    @GetMapping("/csrf")
    public ResponseEntity<Map<String, String>> csrf(
            HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute("_csrf");
        if (token == null) {
            throw new IllegalStateException(
                "No CSRF request attribute; check security chain"
            );
        }

        // Truy cập getToken() để resolve deferred token khi cần.
        Map<String, String> body = Map.of(
            "headerName", token.getHeaderName(),
            "parameterName", token.getParameterName(),
            "token", token.getToken()
        );

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}
~~~

Endpoint này dành cho ứng dụng có CSRF filter expose request attribute `_csrf` theo cấu hình phù hợp. Nếu route GET `/csrf` rơi vào chain không bật CSRF, attribute có thể null; **không tạo token ngẫu nhiên tự chế trong controller** để chữa lỗi chain.

Response chứa token gắn với ngữ cảnh người dùng phải tránh **shared caching**, không log token và không cho website ngoài được tùy tiện đọc thông qua CORS.

### Vì sao GET /csrf sau login có thể cần thiết?

Sau khi request login hoàn tất, token cũ có thể bị clear. `GET /csrf` trong cùng phiên **buộc backend cấp/đọc token hiện hành**, tránh phụ thuộc vào việc response login hoặc GET static asset có vô tình tạo token mới hay không.

### Một endpoint demo cho bài test

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {
    record ProfileUpdate(String displayName) {}

    @PostMapping("/profile")
    ResponseEntity<Void> update(@RequestBody ProfileUpdate update) {
        // Mục đích lab: quan sát request qua security filters.
        return ResponseEntity.noContent().build();
    }
}
~~~

Đây là fixture **không thực hiện cập nhật dữ liệu thật**. Ứng dụng production còn cần validation, kiểm tra user sở hữu resource và bảo vệ dữ liệu ở service layer.

## 12. Form Thymeleaf: token của trang đăng nhập khác token sau login

Một trang login dùng form POST có thể nhận CSRF token từ request attribute:

~~~html
<form th:action="@{/login}" method="post">
  <input type="text" name="username" autocomplete="username">
  <input type="password" name="password" autocomplete="current-password">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Tùy tích hợp Thymeleaf/Spring MVC, form processor có thể **tự chèn CSRF hidden input** cho form POST. Nếu đã có input tự động, tránh chèn trùng cùng tên. Hãy kiểm tra **HTML response thực tế**, không chỉ nhìn template source.

Sau khi đăng nhập, trình duyệt thường điều hướng tới trang mới. Nếu trang này chứa form POST, token cần được lấy **từ ngữ cảnh sau login**, không tái sử dụng một hidden input đã lưu sẵn trong DOM trước đó.

### Rủi ro khi dùng fragment cache

Một layout cache toàn bộ fragment chứa `_csrf.token` qua nhiều user/session có thể làm người dùng A nhận token của user B. Đây là vấn đề vừa chức năng vừa bảo mật; cần tránh shared cache cho nội dung cá nhân hóa.

## 13. SPA: hợp đồng rõ ràng ở bốn ranh giới authentication

SPA thường có một bộ nhớ `csrfToken` dùng chung cho các request AJAX. Để tránh stale token, phải xác định **khi nào state ấy không còn đáng tin**:

| Sự kiện | Frontend cần làm gì? |
|---|---|
| Khởi tạo SPA | Lấy CSRF token từ backend khi cần request state-changing |
| Login thành công | Bỏ token cũ, **await** GET token mới trước request tiếp |
| Logout thành công | Bỏ token của phiên trước; lấy token của anonymous context nếu tiếp tục dùng form/login |
| Session expired / reauthentication | Hủy token cached; yêu cầu người dùng xác thực lại và bootstrap token |
| Đăng nhập tại tab khác | Đồng bộ tín hiệu authentication change, không chia sẻ secret token trực tiếp giữa tab |
| API đổi hostname/đường cookie | Tải token theo API/session hiện hành, kiểm tra CORS/cookie scope |

**Đừng xử lý mọi 403 bằng cách gọi GET /csrf rồi lặp POST vô hạn.** Một 403 có thể là thiếu quyền, rule WAF, CSRF hoặc lỗi nghiệp vụ; thao tác POST có thể không idempotent.

### Luồng trước và sau login

~~~mermaid
flowchart LR
    A[SPA chưa authenticated] --> B[GET /csrf]
    B --> C[POST /login với token]
    C --> D{Login đã xác nhận thành công?}
    D -- Không --> E[Hiển thị lỗi login, không gửi profile POST]
    D -- Có --> F[Xóa csrfState cũ]
    F --> G[GET /csrf trong phiên mới]
    G --> H[CSRF token hiện hành]
    H --> I[POST /profile kèm cookie và token]
~~~

Nếu ứng dụng dùng token đăng nhập riêng hoặc SSO redirect thay vì form login, điều chỉnh bước C theo cơ chế đã được thiết kế; **bước F–H vẫn có ý nghĩa** khi CSRF token theo phiên có thể thay đổi.

## 14. SPA JavaScript: tránh race giữa token cũ và token mới

Một cách quản lý state trên frontend không cần biết token raw hay masked (chỉ cần backend trả `headerName` và `token` hợp lệ):

~~~javascript
let csrfState = null;
let authEpoch = 0;

function invalidateCsrfState() {
  authEpoch += 1;
  csrfState = null;
}

async function refreshCsrf() {
  const requestEpoch = authEpoch;
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("CSRF bootstrap failed: " + response.status);
  }
  const result = await response.json();
  if (!result.token || !result.headerName) {
    throw new Error("CSRF bootstrap response is incomplete");
  }

  // Một request GET cũ có thể về sau lúc login/logout đã hoàn tất.
  if (requestEpoch !== authEpoch) {
    throw new Error("Discarding CSRF token from previous auth state");
  }
  csrfState = { epoch: requestEpoch, value: result };
  return result;
}

async function csrfForUnsafeRequest() {
  if (csrfState?.epoch === authEpoch) {
    return csrfState.value;
  }
  return refreshCsrf();
}

async function afterLoginOrLogoutSucceeded() {
  invalidateCsrfState();
  // Đợi server ghi session/cookie và hoàn thành auth transition.
  await refreshCsrf();
}

async function submitProfile(displayName) {
  const csrf = await csrfForUnsafeRequest();
  const response = await fetch("/profile", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ displayName })
  });

  if (!response.ok) {
    throw new Error("Profile request failed: " + response.status);
  }
  return response;
}
~~~

Đoạn code phục vụ **nguyên tắc epoch**: một GET token được bắt đầu ở authentication state cũ không được ghi đè token mới nếu response đến trễ. Nó chưa cung cấp cơ chế single-flight/deduplicate, retry hoặc định nghĩa API login/logout: caller phải gọi `afterLoginOrLogoutSucceeded()` **chỉ sau khi đã xác nhận authentication transition thành công**.

### Điểm cần điều chỉnh khi triển khai thật

- Có thể dùng một Promise shared để tránh nhiều request `GET /csrf` song song, nhưng vẫn phải hủy/loại bỏ kết quả từ epoch cũ.
- Khi logout hoàn tất, `GET /csrf` chỉ hợp lệ nếu endpoint cho phép anonymous. Nếu không, chỉ invalidate local state rồi bootstrap khi vào login page theo thiết kế.
- Đoạn code dùng `credentials: "same-origin"` cho kiến trúc cùng origin. Cross-origin phải có CORS và cookie policy phù hợp, không đổi sang `include` tùy tiện.
- Nếu app dùng masked token từ endpoint JSON, gửi nguyên token nhận được; không tự `decode` hoặc copy raw cookie trộn với endpoint.
- Khi có nhiều tab, mỗi tab phải invalidate CSRF cache khi auth state đổi; không nên broadcast token secret giữa tab.

## 15. Nhiều tab và request bất đồng bộ: “login rồi” chưa đủ

Một lỗi rất khó tái hiện xảy ra khi hai request đồng thời:

~~~mermaid
sequenceDiagram
    participant T1 as Tab 1
    participant T2 as Tab 2
    participant S as Spring
    T1->>S: GET /csrf (token A)
    T2->>S: POST /logout (token A)
    S-->>T2: Logout success, session/token A không còn
    T1->>S: POST /profile (token A)
    S-->>T1: 403
    T1->>S: GET /csrf ngữ cảnh mới
    S-->>T1: Token hiện hành cho phiên mới
~~~

Vì mỗi tab có thể có bộ nhớ JavaScript riêng nhưng cùng cookie jar, tab 1 có thể giữ token cũ ngay cả khi tab 2 làm thay đổi session.

### Tín hiệu đồng bộ có kiểm soát

Một cơ chế browser như `BroadcastChannel` có thể phát **sự kiện không chứa bí mật**:

~~~javascript
const authChannel = new BroadcastChannel("auth-lifecycle");

authChannel.addEventListener("message", event => {
  if (event.data?.type === "AUTH_CHANGED") {
    invalidateCsrfState();
    // Tab này sẽ tự bootstrap token khi cần.
  }
});

function announceAuthenticationChanged() {
  authChannel.postMessage({ type: "AUTH_CHANGED" });
}
~~~

Chỉ gọi `announceAuthenticationChanged()` khi login/logout đã thành công. Không truyền CSRF token hoặc session cookie qua channel. `BroadcastChannel` hoạt động theo chính sách origin/storage partition của browser và **không bảo đảm đồng bộ giữa mọi tab/domain/browser**; vẫn cần xử lý trường hợp session hết hạn mà không nhận được sự kiện.

## 16. CookieCsrfTokenRepository: tại sao XSRF-TOKEN biến mất sau login?

Một SPA đọc raw token từ cookie có thể báo:

~~~text
Trước login:
  XSRF-TOKEN = R1
  POST /login với token R1 -> thành công

Sau login:
  Browser thấy cookie XSRF-TOKEN bị xóa
  hoặc frontend vẫn giữ giá trị R1 trong memory

POST /api/settings với header X-XSRF-TOKEN: R1
  -> 403 do R1 không còn expected token hợp lệ
~~~

Nếu CSRF authentication strategy clear token qua `CookieCsrfTokenRepository`, response có thể gửi `Set-Cookie` để xóa cookie. **Với deferred token, không nên giả định cookie mới sẽ tự được phát ngay trong response login.** SPA có thể phải gọi endpoint bootstrap hoặc cần một handler materialize token theo cách đã chọn.

### Cookie raw và HTML masked là hai luồng khác nhau

| Form HTML | SPA đọc cookie |
|---|---|
| Có thể dùng `_csrf.token` được XOR-mask | Có thể dùng raw token trong cookie `XSRF-TOKEN` |
| Submitted token nằm trong form parameter | Submitted token ở header `X-XSRF-TOKEN` |
| Handler cần nhận và giải mask khi phù hợp | Handler cần biết đọc raw header |
| Sau login, form mới được render với token hợp lệ | Sau login, cookie/token state cần được refresh |

Nếu server nhận raw token ở header nhưng chỉ dùng handler luôn mong đợi giá trị đã mask, POST vẫn có thể trả 403 **dù token không stale**. Do đó phải tách:

1. Token đã bị clear sau login/logout.
2. Token vẫn là current raw value nhưng handler không hiểu dạng submitted.

Hai nguyên nhân có thể cùng xuất hiện và đòi hỏi hai phép thử riêng.

## 17. Servlet: handler cho SPA dùng raw cookie nhưng giữ masking cho form

Với ứng dụng thật sự cần JavaScript đọc `XSRF-TOKEN` và gửi raw token trong header, có thể dùng cách tổ chức:

- `XorCsrfTokenRequestAttributeHandler` expose token cho HTML theo dạng chống BREACH.
- `CsrfTokenRequestAttributeHandler` resolve raw header cho SPA.
- Chủ động resolve deferred token khi cần phát cookie, kể cả sau authentication transition ở request tiếp theo.

Ví dụ class:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.function.Supplier;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.security.web.csrf.CsrfTokenRequestHandler;
import org.springframework.security.web.csrf.CsrfTokenRequestAttributeHandler;
import org.springframework.security.web.csrf.XorCsrfTokenRequestAttributeHandler;
import org.springframework.util.StringUtils;

public final class SpaCsrfTokenRequestHandler
        implements CsrfTokenRequestHandler {

    private final CsrfTokenRequestHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final CsrfTokenRequestHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(HttpServletRequest request,
                       HttpServletResponse response,
                       Supplier<CsrfToken> csrfToken) {
        xor.handle(request, response, csrfToken);

        // Đảm bảo repository thực sự resolve deferred token.
        // Đây là trade-off cho SPA, không phải bắt buộc trên mọi GET.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request, CsrfToken csrfToken) {
        String header = request.getHeader(csrfToken.getHeaderName());
        return StringUtils.hasText(header)
            ? plain.resolveCsrfTokenValue(request, csrfToken)
            : xor.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Cấu hình trên chain Servlet tương ứng:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
);
~~~

**Cảnh báo triển khai:**

- Đây là ví dụ cho các phiên bản Spring Security Servlet có API như trên; cần đối chiếu phiên bản ứng dụng và kiểm thử thực tế.
- `withHttpOnlyFalse()` làm cookie CSRF đọc được từ JavaScript. Chỉ dùng nếu frontend cần điều đó; không tắt `HttpOnly` của session cookie.
- Nếu frontend lấy **masked token qua GET /csrf**, không tự thay nó bằng raw cookie value trong cùng một request.
- Sau login/logout cần kiểm tra cookie mới được cấp và các AJAX POST dùng đúng giá trị.
- Nếu nhận đồng thời parameter và header, handler trên ưu tiên header có nội dung; thiết kế frontend tránh gửi hai token mâu thuẫn.
- Giữ nguyên CSRF validation ở server; không tự so sánh token bằng JavaScript rồi kết luận request an toàn.

Một cách khác đơn giản hơn cho một số SPA là **GET /csrf trả token cho client** như mục 11, không cần cookie CSRF readable. Hai chiến lược phải được chọn có chủ đích, tránh lắp ghép tùy tiện.

## 18. Reactive/WebFlux: cùng bài toán stale state, khác stack và API

Ở Spring Security Reactive, những thành phần liên quan:

| Servlet | Reactive/WebFlux |
|---|---|
| `CsrfFilter` | `CsrfWebFilter` |
| `CsrfTokenRepository` | `ServerCsrfTokenRepository` |
| `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| `CookieCsrfTokenRepository` | `CookieServerCsrfTokenRepository` |
| `HttpServletRequest` | `ServerWebExchange` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |

WebFlux có thể expose một `Mono<CsrfToken>` trong exchange; việc chỉ nhìn thấy một publisher không chứng minh token đã được tạo/lưu. Publisher cần được tiêu thụ để resolve token deferred.

**Quan trọng:** `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` được nêu ở mục 4 là cơ chế **Servlet**. Không suy rằng Reactive mặc định gọi đúng hai class đó hoặc có thứ tự filter giống hệt. Với WebFlux cần xác minh hành vi của CSRF/session/logout ở phiên bản và cấu hình Reactive thực chạy: token có bị clear khi authentication/logout, session có bị invalidate, cookie có bị xóa và request đầu tiên sau transition có token mới chưa.

### Reactive security chain ví dụ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSessionSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers("/login", "/csrf").permitAll()
            .pathMatchers("/profile/**").authenticated()
            .anyExchange().authenticated()
        );
        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Nếu ứng dụng có nhiều `SecurityWebFilterChain`, phải bảo đảm `GET /csrf` và `POST /profile` dùng repository/handler tương thích; rule `permitAll()` ở authorization **không tắt CSRF**.

## 19. Reactive GET /csrf: resolve token trước khi SPA gửi POST

Ví dụ WebFlux controller:

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCsrfBootstrapController {

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders()
            .setCacheControl(CacheControl.noStore());

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());
        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF publisher unavailable; check security chain"
            ));
        }

        return tokenMono.map(csrfToken -> Map.of(
            "token", csrfToken.getToken(),
            "headerName", csrfToken.getHeaderName(),
            "parameterName", csrfToken.getParameterName()
        ));
    }
}
~~~

`Mono.map(...)` chỉ chạy khi response được subscribe. Điều này cho phép token được lấy/khởi tạo ở thời điểm thật sự cần; **không dùng `block()` để ép lấy token trong WebFlux request processing**.

### Cookie-based CSRF trong WebFlux

Khi thiết kế SPA cookie flow riêng, WebFlux có thể dùng:

~~~java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

Chỉ đổi repository **không tự giải quyết stale token hay raw/masked**. Phải test sau login/logout, việc cookie được phát ở request nào, CSRF request handler Reactive hiểu giá trị client gửi ra sao và WebSession có còn hợp lệ không. Không sao chép Servlet `CsrfTokenRequestHandler` vào WebFlux.

### Sự khác nhau ở session

WebFlux sử dụng `WebSession`; khi kiểm thử session expiry, cluster hoặc cookie scope, cần xem session storage của Reactive (và Spring Session Reactive nếu có). Một request test chạy trên mock exchange không tái hiện hoàn toàn Reactor Netty hoặc gateway trong production.

## 20. SSO/OAuth2 login: token cũ trước redirect có thể không còn áp dụng

Một luồng OAuth2 login:

~~~text
SPA ở /login giữ CSRF token A
  -> browser bắt đầu OAuth2 authorization redirect
  -> quay về /login/oauth2/code/...
  -> Spring xử lý authentication success, session/cookie đổi
  -> SPA hydrate từ cache cũ, vẫn giữ A
  -> POST /profile dùng A -> 403 nếu A không còn hợp lệ
~~~

**Không nhầm CSRF token của ứng dụng với tham số `state` của OAuth2 authorization flow.** `state` giúp bảo vệ quan hệ giữa authorization request và callback theo cơ chế OAuth2; nó không tự là token dùng trong header `X-CSRF-TOKEN` của POST nghiệp vụ.

Nếu có OpenID Connect, đừng nhầm `nonce` của ID token với CSRF token của form. Các giá trị này có mục đích, storage và vòng đời khác nhau.

### Hướng xử lý

- Chờ authentication callback hoàn tất và session/cookie được ghi trước khi bootstrap CSRF token.
- Khi SPA khởi động sau redirect, không dùng state token lưu từ trang trước redirect.
- Nếu frontend trả HTML/JS từ CDN, CSP trên HTML và CSRF endpoint trên API có trách nhiệm khác nhau.
- Kiểm tra same-site/cross-site cookie policies cho từng chặng redirect, đặc biệt khi môi trường dùng HTTPS và reverse proxy.

Với request callback OAuth2, **không tùy tiện gắn yêu cầu CSRF token của form** mà không hiểu cách framework xử lý callback; điều tra auth flow và security chain riêng, rồi test cả callback và POST nghiệp vụ.

## 21. Những thay đổi khác khiến token stale dù không có login rõ ràng

| Sự kiện | Token có thể bị stale như thế nào? | Dấu hiệu |
|---|---|---|
| Session timeout | Server không còn expected token/session | Chỉ lỗi sau thời gian dài không hoạt động |
| Session concurrency control | Một session bị expire khi login nơi khác | User thấy đột ngột redirect/login hoặc 403 |
| Security context đổi | Principal/authorization đổi nhưng frontend state không refresh | Chỉ lỗi khi switch account/tenant |
| Session store evict/TTL | Expected token mất khỏi backend | Cookie vẫn tồn tại nhưng server không tìm thấy session |
| Deployment thay CSRF repository | New node dùng cơ chế khác | Chỉ lỗi khi rolling deploy/canary |
| Proxy đổi route/host | GET token và POST đi qua service/chain khác | Origin vs public path khác nhau |
| Multi-tab logout | Tab 1 giữ hidden token cũ | Lỗi sau khi thao tác ở tab 2 |
| Bfcache khôi phục trang | DOM cũ được khôi phục không qua HTTP GET mới | Back/forward rồi submit thất bại |
| CDN cache HTML có token | Phát lại token từ response/phiên khác | Lỗi có thể ngẫu nhiên theo cache hit |

Trong mọi trường hợp, phải tìm **điểm expected token thay đổi hoặc biến mất** trước khi nói tới chính sách refresh ở frontend.

## 22. MockMvc: kiểm thử lọc CSRF không đủ để kiểm tra token sau login

Test nhanh với `spring-security-test`:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());

mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .with(csrf())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());

mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .with(csrf().useInvalidToken())
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());
~~~

Ví dụ giả định controller `POST /profile` trả 204 và user `ROLE_USER` có quyền gọi. MockMvc đã gắn Spring Security, CSRF filter áp dụng và JSON được controller chấp nhận.

**Điểm yếu của test:** `with(csrf())` tạo CSRF token phù hợp ngay trong test request. Nó không thực hiện `GET /csrf`, không đăng nhập thật, không chuyển session và không dùng token cũ. Vì vậy các test trên có thể PASS dù SPA production giữ token stale sau login.

## 23. MockMvc: đo vòng đời token qua login thực

Một integration test tốt nên dùng **đúng authentication flow** và **đúng session**. Ví dụ sau giả định:

- Ứng dụng dùng Servlet, session repository và form login.
- Test user `alice` có mật khẩu thử nghiệm `test-password`, role `USER`.
- `GET /csrf` trả JSON `token`, `headerName`, `parameterName` và materialize token.
- Login thành công redirect tới `/` theo cấu hình test, CSRF authentication strategy có clear token cũ.
- `POST /profile` trả 204 khi CSRF và auth hợp lệ.

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

ObjectMapper json = new ObjectMapper();

// 1. Anonymous GET materialize token A.
MvcResult anonymousBootstrap = mockMvc.perform(get("/csrf"))
    .andExpect(status().isOk())
    .andReturn();

JsonNode before = json.readTree(
    anonymousBootstrap.getResponse().getContentAsString()
);
String tokenBeforeLogin = before.path("token").asText();
String csrfParameterName = before.path("parameterName").asText();
MockHttpSession anonymousSession =
    (MockHttpSession) anonymousBootstrap.getRequest().getSession(false);
assertNotNull(anonymousSession);

// 2. Đăng nhập THẬT theo form-login filter, dùng token A hợp lệ.
MvcResult login = mockMvc.perform(post("/login")
        .session(anonymousSession)
        .param("username", "alice")
        .param("password", "test-password")
        .param(csrfParameterName, tokenBeforeLogin))
    .andExpect(status().is3xxRedirection())
    .andExpect(redirectedUrl("/"))
    .andReturn();

// Lấy session hiện hành sau authentication/session fixation strategy.
MockHttpSession loggedInSession =
    (MockHttpSession) login.getRequest().getSession(false);
assertNotNull(loggedInSession);

// 3. Dùng token A trong phiên sau login: mong đợi bị từ chối
// khi CSRF authentication strategy đã invalidate token A.
mockMvc.perform(post("/profile")
        .session(loggedInSession)
        .header(before.path("headerName").asText(), tokenBeforeLogin)
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());

// 4. Bootstrap token hiện hành của session sau login.
MvcResult freshBootstrap = mockMvc.perform(get("/csrf")
        .session(loggedInSession))
    .andExpect(status().isOk())
    .andReturn();

JsonNode fresh = json.readTree(
    freshBootstrap.getResponse().getContentAsString()
);

// 5. Token mới được chấp nhận trên cùng session.
mockMvc.perform(post("/profile")
        .session(loggedInSession)
        .header(
            fresh.path("headerName").asText(),
            fresh.path("token").asText()
        )
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());
~~~

Đoạn code minh họa **nội dung bên trong test method** có sẵn `MockMvc mockMvc`; không phải một test class độc lập. Không đặt mật khẩu thật trong test source. Nếu application redirect sau login tới URL khác, điều chỉnh assertion `redirectedUrl("/")` theo cấu hình.

### Vì sao test này tốt hơn việc so hai chuỗi token?

Test xác minh **hành vi**: token trước login từng hợp lệ, nhưng sau authentication bị từ chối; token bootstrap sau login lại vượt qua CSRF và tới controller. Chỉ so `tokenBeforeLogin != tokenAfterLogin` không có giá trị tương đương vì masked representation có thể đổi mà expected token vẫn giống.

**Lưu ý về chiến lược session:** ứng dụng custom có thể không clear token sau login. Khi đó bước 3 không nhất thiết phải là 403 và test cần phản ánh chính sách đã được review. Nếu session sau login khác hẳn và token được chuyển tiếp theo một cách riêng, điều tra cơ chế đó thay vì tự ép một mô hình mặc định.

### Tránh nhầm login thất bại với login thành công

Chỉ thấy status 302 không chứng minh login thành công: login thất bại cũng có thể redirect đến `/login?error`. Nên xác nhận redirect đích hoặc tài nguyên authenticated riêng. Trong test, `redirectedUrl("/")` là một ràng buộc cụ thể cho cấu hình minh họa, không phải mặc định buộc mọi hệ thống.

## 24. MockMvc: logout và token của anonymous context

Logout là một sự kiện **thay đổi trạng thái xác thực**, nên cũng phải dùng token hợp lệ và invalidate state frontend khi thành công.

Quy trình test:

~~~text
1. Login bằng cơ chế thật.
2. GET /csrf trên session authenticated -> token L.
3. POST /logout cùng session với token L -> logout thành công.
4. Browser bỏ session/token state trước logout.
5. GET /csrf trong ngữ cảnh anonymous mới -> token N.
6. POST một endpoint public nhưng vẫn được CSRF bảo vệ:
   - dùng token L -> bị từ chối (nếu repository đã clear)
   - dùng token N -> qua CSRF filter.
~~~

**Không dùng `POST /profile` sau logout làm phép thử duy nhất về CSRF**, vì request có thể bị từ chối **do authentication** dù token đúng. Một fixture `POST /csrf-lab/submit` với authorization `permitAll()` nhưng CSRF enabled giúp cô lập lớp CSRF.

Một kiểm thử logout đúng còn phải xem cookie session bị xóa, redirect/response, `SecurityContext` bị clear và route yêu cầu authentication không còn được truy cập. CSRF token không thay thế kiểm thử logout/session security.

## 25. MockMvc: token mới khác *hiệu lực* chứ không phải khác chuỗi

Có ba phép thử nên giữ song song:

| Phép thử | Điều được chứng minh | Điều chưa được chứng minh |
|---|---|---|
| Cùng session, hai GET /csrf trả hai chuỗi khác nhau | Có thể có masking mới | Không chứng minh CSRF token rotate |
| Cùng session, cả hai giá trị masked đều được chấp nhận | Handler biết resolve token được expose | Không chứng minh logout đã clear token |
| Token trước login bị từ chối sau login, token bootstrap mới được chấp nhận | Vòng đời token phù hợp với auth transition test | Không chứng minh browser/proxy cookies đúng trong production |

Ở ứng dụng dùng cookie repo, test cần chuyển cookie `XSRF-TOKEN` từ GET sang POST thay vì chỉ dùng `MockHttpSession`. Nếu muốn kiểm tra cả đọc raw cookie và masked form, tạo **hai ca riêng** dùng handler đã cấu hình.

### Cảnh báo về test helper

Một mock user được chèn bằng `with(user(...))` là tiện cho test authorization, nhưng không nhất thiết kích hoạt **form-login authentication success**, session fixation strategy hoặc CSRF authentication strategy giống luồng login thật. Vì vậy bài test vòng đời phải đi qua request login thực hoặc một integration harness tương đương.

## 26. WebTestClient: Reactive CSRF filter và session transition

Kiểm thử nhanh trong WebFlux:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .post().uri("/profile")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post().uri("/profile")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isNoContent();
~~~

Giả định ứng dụng có controller WebFlux trả 204, `spring-security-test` được cấu hình và CSRF áp dụng cho POST. Các helper xác nhận filter logic nhưng không thực hiện login/logout thật hoặc kiểm tra session/cookie trên browser.

### Test bootstrap WebFlux

~~~java
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.emptyOrNullString;

webTestClient.get()
    .uri("/csrf")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches("Cache-Control", ".*no-store.*")
    .expectBody()
    .jsonPath("$.token").value(not(emptyOrNullString()))
    .jsonPath("$.headerName").exists();
~~~

Với ứng dụng Reactive, để kiểm chứng token cũ **sau login/logout**, dùng WebTestClient bind vào **HTTP server thật có thể quản lý cookie**, hoặc browser E2E. Thực hiện:

1. GET token + giữ cookie WebSession.
2. Submit login thật với token hợp lệ.
3. Xác nhận authentication thành công.
4. Gửi token cũ trong context sau login và ghi kết quả.
5. GET token mới, gửi POST và xác nhận controller.

**Không bắt buộc khẳng định token trước login luôn bị từ chối trong mọi cấu hình WebFlux.** Hành vi invalidate phụ thuộc CSRF/session/authentication/logout setup. Test đo kết quả hiện tại và so với security contract của ứng dụng.

## 27. Browser E2E: chứng minh token stale trên đường HTTP thật

Một bài kiểm thử Playwright trên môi trường lab nên sử dụng **browser cookie jar thực**, thay vì chỉ mock header:

~~~javascript
import { test, expect } from "@playwright/test";

test("token cũ sau login bị từ chối; token mới hoạt động", async ({ page }) => {
  const base = "http://localhost:8080";

  // Trang /login có form Spring Security hoạt động với user test.
  await page.goto(base + "/login");

  async function getCsrf() {
    return page.evaluate(async () => {
      const response = await fetch("/csrf", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store"
      });
      if (!response.ok) throw new Error("CSRF bootstrap failed");
      return response.json();
    });
  }

  async function submit(token) {
    return page.evaluate(async csrf => {
      const response = await fetch("/csrf-lab/submit", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          [csrf.headerName]: csrf.token
        },
        body: JSON.stringify({ value: "demo" })
      });
      return response.status;
    }, token);
  }

  const before = await getCsrf();
  expect(await submit(before)).toBe(204);

  // Đăng nhập bằng form thật. Cần fixture với user/password test hợp lệ.
  await page.locator('input[name="username"]').fill("alice");
  await page.locator('input[name="password"]').fill("test-password");
  await page.locator('button[type="submit"]').click();

  // Route authenticated do lab cung cấp, không chỉ tin HTTP 302.
  await expect.poll(() => page.evaluate(async () => {
    const r = await fetch("/csrf-lab/whoami", {
      credentials: "same-origin"
    });
    // fetch tự follow redirect: đừng nhận nhầm trang /login 200 là auth success.
    return r.redirected ? 0 : r.status;
  })).toBe(200);

  // Test mặc định Servlet đã clear CSRF token trên authentication success.
  expect(await submit(before)).toBe(403);

  const after = await getCsrf();
  expect(await submit(after)).toBe(204);
});
~~~

### Những fixture bắt buộc cho test Playwright

- `GET /csrf-lab/whoami` trả 200 **chỉ khi đã authenticated**, nếu không trả 401/302 theo cấu hình đã xác định.
- `POST /csrf-lab/submit` được authorization cho phép nhưng **vẫn bật CSRF**, và controller trả 204 khi hợp lệ.
- `GET /login` có HTML form login với selector đã dùng; user test `alice` được cấu hình.
- Authentication success trong cấu hình lab thực sự clear token cũ như contract muốn kiểm thử.
- Tất cả request dùng cùng origin và cookie jar hiện hành; không được CDN cache response `/csrf`.

Nếu thiếu fixture hoặc flow dùng SSO, hãy điều chỉnh test trước khi chạy. Không được coi script minh họa là test PASS ngoài một ứng dụng đã chuẩn bị những route đó.

### Tại sao không so chuỗi token?

Browser test cần trả lời: **sau login, request với token cũ còn hợp lệ hay không; request với token mới hoạt động hay không?** Nó không cần giả định token trước/sau login có độ dài hay encoding khác nhau. Với masking, hai chuỗi khác nhau chỉ là một tín hiệu về presentation, không phải trạng thái repository.

## 28. Multi-tab E2E và trường hợp Back/Forward Cache

Ngoài tình huống một tab, nên test:

1. Mở hai pages trong **cùng browser context** để chúng chia sẻ cookie/session.
2. Tab A GET form và giữ hidden token.
3. Tab B logout rồi login lại.
4. Tab A submit form cũ: nếu token đã bị invalidated, phải bị từ chối.
5. Tab A refresh form/token và thử lại với ngữ cảnh authenticated mới.

Khi người dùng nhấn Back, browser có thể khôi phục document từ *back-forward cache* mà không tạo HTTP GET mới. Trang nhìn như mới mở nhưng hidden input vẫn là token cũ. Không nhầm điều này với shared HTTP cache hoặc lỗi CSRF repository.

Một chiến lược UX là kiểm tra auth/session lifecycle và yêu cầu người dùng refresh form sau khi phiên đổi; không tự động submit lại dữ liệu nhạy cảm bằng token cũ.

## 29. Phân biệt lỗi token stale với lỗi cookie, CORS, CSP và authorization

Cùng một thao tác “Save” trong SPA có thể nhận 403 hoặc lỗi JavaScript vì nhiều nguyên nhân **không phải token cũ**:

| Biểu hiện | Nguồn lỗi đáng nghi | Bằng chứng cần tìm |
|---|---|---|
| POST có token, có session và `InvalidCsrfTokenException` | Token stale hoặc sai dạng raw/masked | Repository, handler, login/logout timeline |
| POST thiếu token nhưng session hợp lệ | Bootstrap chưa xảy ra, frontend quên header | DevTools Request Headers/Form Data |
| POST không gửi cookie session | SameSite/Secure/Domain/Path/credentials | DevTools Cookies request, session log |
| OPTIONS preflight trả 403, POST không xuất hiện | CORS processor/gateway | Origin, requested method/header, CORS config |
| Browser báo `Content Security Policy: connect-src` | CSP của tài liệu HTML | Console violation, CSP trên HTML response |
| POST có CSRF hợp lệ nhưng nhận 403 | Authorization/method security/business denial | `AccessDeniedHandler`, authorities, controller |
| 401 hoặc 302 đến `/login` | Authentication/session expired | Entry point, cookie, principal |
| 400 và `RequestRejectedException` | HTTP firewall Servlet | URI/method/header, RequestRejectedHandler |
| Proxy/WAF trả 403, backend không có log | Gateway/edge rule | Trace ID, edge response và access logs |
| POST đến sai route/chain sau redirect | Proxy rewrite/securityMatcher khác | Chain được chọn, path thực nhận |
| Chỉ lỗi sau login, GET /csrf mới sửa được | Token lifecycle/deferred regeneration | Tái hiện login → stale POST → bootstrap → POST |
| Chỉ lỗi trên một node | Session store/affinity/canary config | Node ID, session state, phiên bản repository |

**Bước số 1 luôn là xác nhận HTTP POST có thật sự đến CSRF filter không.** Nếu browser không gửi vì CSP/CORS hoặc WAF chặn trước Spring, làm mới token có thể không thay đổi kết quả.

### Không nhầm 401 với 403 do CSRF

Ở Servlet, một `CsrfFilter` có thể từ chối unsafe request trước khi authentication entry point xử lý theo cách UI mong đợi. Vì vậy một POST của user đã logout có thể nhận 403 do thiếu token, trong khi GET cùng route trả 302 login. Đừng dùng mã status đơn lẻ để kết luận user vẫn đang authenticated hoặc authorization đã đúng.

## 30. Browser DevTools: bảng thời gian để phát hiện token cũ

Khi lỗi chỉ xuất hiện sau chuyển trạng thái, điều tra **cả chuỗi**, không chỉ request cuối.

| Thứ tự | Request/response | Bằng chứng cần giữ |
|---|---|---|
| T1 | GET `/login` hoặc GET `/csrf` trước login | Route, cookie scope, token được expose chưa |
| T2 | POST `/login` | Có token hợp lệ, authentication success/failure |
| T3 | Redirect/auth callback | Session cookie mới, Location, status, thời điểm |
| T4 | GET `/csrf` sau login (nếu có) | Response JSON, `Cache-Control`, token state |
| T5 | POST `/profile` đầu tiên | Cookie hiện hành, CSRF header/parameter, trace ID |
| T6 | Logout hoặc session timeout | Token/session bị clear ở thời điểm nào |
| T7 | GET login/token sau logout | Token của context anonymous mới |

Ở tab **Network**, kiểm tra `Preserve log` khi redirect và theo dõi **Response Headers** của request tạo cookie, không chỉ Request Headers của request thất bại.

### Những điều nên ghi, không ghi

Nên ghi: method, path đã làm sạch, HTTP status, request ID, loại token repository, có/không cookie session, header name, authentication event và nhóm CSRF exception.

Không ghi nguyên: session cookie, `Authorization`, Bearer/JWT, CSRF token raw/masked, password, nội dung form nhạy cảm hoặc query chứa token.

**Một HTTP 302 sau login không chứng minh login thành công** nếu nó redirect về trang lỗi. Kiểm tra principal/resource authenticated hoặc redirect đích đã biết.

## 31. Log Servlet và Reactive: tìm điểm clear token, không in token

Khi cần chẩn đoán trong môi trường dev/staging:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.csrf=DEBUG
logging.level.org.springframework.security.web.session=DEBUG
logging.level.org.springframework.security.web.server.csrf=DEBUG
~~~

Trong một khoảng thời gian ngắn có thể bật TRACE cho component được điều tra nếu môi trường/log policy cho phép. Tuyệt đối không bật TRACE toàn bộ HTTP traffic lâu dài trong production, đặc biệt khi có token/cookie.

### Cần trả lời bằng log

1. Authentication success hoặc logout success diễn ra **khi nào**?
2. Security chain nào thực sự xử lý request GET token, POST login, POST logout và POST profile?
3. CSRF repository đang dùng là **session**, **cookie** hay **custom**?
4. Sau transition, expected token có bị clear/không còn không? Chỉ ghi cờ trạng thái.
5. Request POST mang submitted token hay không; tên header/parameter có đúng?
6. Filter/handler nào từ chối? Có `MissingCsrfTokenException`, `InvalidCsrfTokenException` hoặc lỗi khác?
7. Session state có được khôi phục trên đúng node/cluster không?

**Các exception không phải lúc nào có tên giống nhau giữa Servlet, WebFlux hoặc phiên bản.** Một 403 có thể do authentication/authorization hoặc custom handler. Log phải gắn correlation ID và phân loại *nguyên nhân*, không suy từ chữ “Forbidden”.

## 32. Proxy, CDN và nhiều node: session chuyển trạng thái nhưng dữ liệu không đồng bộ

Sau login, một backend node có thể clear CSRF token, nhưng request kế tiếp lại được phục vụ bởi node có session cũ hoặc cache không tương thích. Những tình huống cần test:

### 32.1. GET token từ node A, POST qua node B

~~~text
GET /csrf:
  node A -> expected token trong session store A

POST /login:
  node A -> authentication thành công, session/token transition

POST /profile:
  node B -> không khôi phục đúng session/CSRF token
  => mismatch hoặc thiếu authentication
~~~

Kiểm tra session persistence, Spring Session nếu dự án sử dụng, cookie scope, affinity và phiên bản cấu hình giữa node. **Đừng dùng stickiness như một lý do bỏ kiểm tra failover**, và đừng gắn token vào một node tùy tiện.

### 32.2. HTML có token bị shared cache

~~~text
User A: GET /profile -> HTML có token thuộc context A
CDN cache HTML
User B: GET /profile -> nhận HTML cache của A
User B: POST /profile với token A, cookie session B
=> CSRF từ chối; có thể kèm nguy cơ rò dữ liệu A
~~~

Với HTML cá nhân hóa và endpoint bootstrap token, cần cache policy như:

~~~http
Cache-Control: no-store
~~~

Đồng thời cấu hình edge không lưu/không chia sẻ response chứa secret. Không chỉ nhìn `Cache-Control` rồi giả định CDN tuân thủ; kiểm tra cache hit/miss và header/body trên đường public.

### 32.3. Back-forward cache không phải shared HTTP cache

Sau logout/login lại, browser có thể quay về một form cũ bằng **bfcache** mà không gửi HTTP GET mới. Form token trong DOM vẫn thuộc phiên trước. Cách giải quyết là nhận biết authentication lifecycle, tải lại form/token khi cần và bảo đảm server vẫn từ chối token stale. **Không vô hiệu CSRF để hỗ trợ Back button.**

### 32.4. Reverse proxy làm cookie session không gửi đúng

Ở origin, app chạy `http://service:8080` nhưng public dùng `https://app.example.com`. Nếu cookie `Secure`/`Domain`/`Path` hoặc forwarded headers không được thiết kế đúng theo proxy tin cậy, browser có thể không gửi session cookie ở POST. Khi đó CSRF token lấy trước đó sẽ không có cùng expected context ở server.

Chỉ chấp nhận forwarded headers từ proxy đáng tin. Không nới cookie Domain hoặc tắt Secure bừa bãi để chữa một lỗi 403.

## 33. Biên giới an toàn: tránh các “cách sửa” phá bảo vệ

| Cách làm sai | Rủi ro | Cách đúng |
|---|---|---|
| Tắt `http.csrf(...)` vì POST sau login 403 | Mất phòng vệ CSRF cho cookie-authenticated workflows | Bootstrap token mới sau auth transition |
| Tắt session fixation protection | Tăng rủi ro cố định session | Giữ session protection, sửa token lifecycle |
| Chấp nhận token cũ vĩnh viễn | Giảm ranh giới giữa các ngữ cảnh xác thực | Tôn trọng invalidation, refresh token |
| Hard-code CSRF token chung vào frontend | Token không gắn ngữ cảnh, dễ đoán/tái sử dụng | Repository sinh/lưu token thích hợp |
| Tự so `rawCookie == maskedForm` | Hai biểu diễn vốn khác nhau | Dùng handler đúng định dạng |
| Biến mọi 403 thành “token expired” | Che lỗi authorization/CORS/WAF | Backend classification/log có kiểm soát |
| Tự retry POST ngay khi 403 | Có thể lặp thao tác không idempotent | Tái xác thực/refresh, yêu cầu người dùng xác nhận |
| Dùng GET để cập nhật dữ liệu thay POST | GET có thể bị prefetch/cross-site trigger | Unsafe method và CSRF protection |
| Dùng `Access-Control-Allow-Origin: *` cho credentialed request | Mở CORS sai mô hình bảo vệ | Explicit allowed origins/methods/headers |
| Cho mọi origin đọc GET `/csrf` | Lộ secret ở mô hình dùng browser credentials | SOP/CORS hạn chế, đúng auth context |
| Log toàn CSRF token hoặc session ID | Rò thông tin nhạy cảm | Log boolean và trace ID |
| Cache shared response chứa token | Token sai phiên, nguy cơ rò data | no-store + edge config |
| Mở cookie `HttpOnly=false` cho tất cả cookies | JavaScript đọc được session cookie nhạy cảm | Chỉ cân nhắc readable CSRF cookie khi cần |
| Bỏ qua CORS/HTTP firewall/HSTS vì test CSRF fail | Suy yếu bảo vệ khác | Sửa đúng layer dựa trên chứng cứ |

## 34. Bài thực hành tổng hợp

**Bối cảnh:** một ứng dụng Spring Boot có login bằng cookie session, form chỉnh hồ sơ, endpoint bootstrap CSRF cho SPA, logout và một trang quản trị. Lỗi chỉ xảy ra khi user login/logout, mở nhiều tab hoặc chuyển node.

### Các nhiệm vụ

1. **Servlet baseline:** cấu hình `SecurityFilterChain` với form login, logout, CSRF enabled và endpoint `GET /csrf`.
2. Gọi GET token trong anonymous session A; dùng token A để POST login thật. Xác nhận authentication success bằng route được bảo vệ.
3. Không bootstrap token mới, thử POST `/profile` với token A. Ghi exception và status trong cấu hình mặc định có invalidation.
4. GET `/csrf` sau login, thử lại POST với token mới; chứng minh request vượt qua CSRF filter mà không cần tắt CSRF.
5. Lặp quá trình với logout: dùng token hiện hành cho POST logout, sau đó tải token cho anonymous session mới và thử form.
6. Dùng MockMvc viết ba phép thử: request thiếu token; token trước login stale; token sau login hợp lệ.
7. Với Thymeleaf form, so hidden token giữa hai GET trong **cùng session**; giải thích vì sao chuỗi có thể khác do XOR masking.
8. Chuyển sang `CookieCsrfTokenRepository` trong môi trường lab: xác minh cookie có bị xóa sau login, được phát lại ở GET nào, và SPA lấy raw token ra sao.
9. Dùng SPA mock form hoặc JavaScript minh họa `authEpoch`. Tái hiện request bootstrap cũ trả về sau login, rồi xác nhận response đó không ghi đè token mới.
10. Dùng hai tabs cùng browser context: tab B logout/login, tab A gửi form cũ; xác minh token stale bị từ chối.
11. Dùng Playwright kiểm thử browser thực, quan sát cookies, redirect và request headers; **không xuất secret vào test report**.
12. Tạo phiên bản **Reactive/WebFlux** dùng `CsrfWebFilter` và `Mono<CsrfToken>`. Đo hành vi cụ thể sau login/logout thay vì mặc định lấy chính xác cơ chế Servlet.
13. Chạy qua reverse proxy, thử cache hit/miss và trường hợp cookie Path/Secure không phù hợp; phân biệt lỗi session với lỗi stale token.
14. Ghi báo cáo gồm: thời điểm login/logout, repository/handler, cookie/session continuity, token cũ/mới, CSRF exception, response status và test hồi quy.

### Câu hỏi tự đánh giá

1. Vì sao CSRF token hợp lệ ở POST login có thể không hợp lệ ở POST tiếp theo?
2. `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` có vai trò gì trong Servlet?
3. Session ID đổi sau login có tự chứng minh expected CSRF token bị xóa không?
4. Vì sao không tắt session fixation protection để sửa 403 do CSRF?
5. Điều gì khiến CookieCsrfTokenRepository khác HttpSessionCsrfTokenRepository khi cookie session đổi?
6. Tại sao giá trị `_csrf` của hai lần render có thể khác mà token vẫn hợp lệ?
7. Bằng chứng nào tốt hơn việc so sánh hai chuỗi token trước/sau login?
8. Vì sao deferred token có thể chưa có ngay trong response login thành công?
9. Sau logout, SPA nên xử lý token cached thế nào?
10. Khi hai tabs chia sẻ cookie nhưng không chia sẻ JavaScript state, lỗi nào có thể xảy ra?
11. `BroadcastChannel` có nên truyền nguyên CSRF token giữa tab không? Vì sao?
12. Vì sao `with(csrf())` PASS chưa chứng minh token stale sau login đã được xử lý?
13. Khi test form login bằng MockMvc, vì sao phải kiểm tra login success thực sự, không chỉ HTTP 302?
14. Với Reactive, tại sao không được giả định `CsrfAuthenticationStrategy` Servlet luôn được gọi?
15. SSO/OAuth2 `state` có giống token CSRF dùng trong POST `/profile` không?
16. Nếu browser không gửi POST vì CORS preflight, có thể kết luận CSRF token bị stale không?
17. Nếu POST có token và cookie nhưng không có app log, nên kiểm tra tầng nào?
18. Vì sao HTTP cache và bfcache có thể khiến form dùng token cũ theo cách khác nhau?
19. Khi nhiều node chạy khác version, thông tin nào cần thu để xác minh lỗi token?
20. Vì sao không nên retry tự động một POST thanh toán chỉ vì 403?

## 35. Ghi nhớ

**Token CSRF cũ sau login, logout hoặc đổi phiên là lỗi vòng đời ngữ cảnh, không phải đơn thuần thiếu một header.** Trong Spring Security Servlet, authentication/logout có thể clear expected token; session fixation protection cũng có thể đổi session ID, nhưng **đổi ID và invalidate CSRF là hai sự kiện khác nhau**. Với deferred token, sau khi xóa token cũ, token mới có thể chưa được tạo ngay nếu không có view/controller/endpoint yêu cầu nó.

Giải pháp chuẩn là **đăng nhập/đăng xuất hợp lệ → xác nhận transition → hủy token frontend cũ → bootstrap token trong ngữ cảnh hiện hành → chỉ sau đó gửi unsafe request**. Đừng coi việc hidden token thay đổi vì XOR masking chống BREACH là bằng chứng token đã rotate. Hãy kiểm thử *hiệu lực* bằng request thật và cùng cookie/session, không chỉ so chuỗi.

Trong **Servlet**, quan sát `CsrfFilter`, `CsrfTokenRepository`, `CsrfTokenRequestHandler` và authentication/logout strategies; trong **Reactive/WebFlux**, dùng đúng `CsrfWebFilter`, `ServerCsrfTokenRepository`, `WebSession` và `Mono<CsrfToken>`. Kết hợp MockMvc/WebTestClient với browser E2E để phân biệt CSRF khỏi CORS, CSP, authorization, HTTP firewall, proxy/cache và session cluster. Mục tiêu của `SPRING_SECURITY_HTTP_PROTECTION` là xử lý token stale mà vẫn bảo toàn **CSRF, CORS, HSTS, security headers, CSP và bảo vệ session**.
