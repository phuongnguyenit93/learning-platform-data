# CSRF token thiếu do chưa được tạo hoặc chưa tải

> **Chương:** Chẩn đoán lỗi  
> **Mô-đun:** `SPRING_SECURITY_HTTP_PROTECTION` — áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security, từ CSRF, CORS, security headers, CSP, HSTS đến HTTP firewall và bảo vệ session. Người học cấu hình cho Servlet lẫn Reactive, kiểm thử các kịch bản tấn công web và chẩn đoán xung đột bảo mật khi triển khai.

## 1. Vấn đề: người dùng đăng nhập được nhưng POST lại nhận 403

Một ứng dụng Spring Boot có trang hồ sơ. Người dùng đăng nhập, mở `GET /profile`, thấy form hiển thị bình thường và nhấn **Lưu**. Trình duyệt gửi:

~~~http
POST /profile HTTP/1.1
Cookie: JSESSIONID=...
Content-Type: application/x-www-form-urlencoded

displayName=An
~~~

Server trả:

~~~http
HTTP/1.1 403 Forbidden
~~~

Người dùng đã đăng nhập, có quyền cập nhật hồ sơ, nhưng request vẫn bị từ chối. Một khả năng phổ biến là **thiếu token chống Cross-Site Request Forgery (CSRF)**. Có ba trường hợp khác nhau thường bị mô tả chung là “token không tồn tại”:

1. **Token chưa được tạo hoặc chưa được lưu:** Spring Security trì hoãn việc nạp/tạo token, và request hiển thị trang chưa có thành phần nào yêu cầu lấy giá trị thật.
2. **Token tồn tại nhưng client chưa nhận được:** template không render hidden input, JavaScript không đọc endpoint bootstrap, cookie không được gửi/không thể đọc, hoặc response cache/CDN phục vụ nội dung cũ.
3. **Token đã được gửi nhưng không hợp lệ:** token thuộc phiên khác, bị xoay vòng sau login/logout, sai tên header/parameter, lỗi giải mã token được mask, hoặc repository và handler không tương thích.

**Mã 403 chỉ cho biết request bị từ chối, không tự chứng minh lỗi CSRF.** Authorization, CORS, security chain, HTTP firewall, reverse proxy và nghiệp vụ cũng có thể tạo 403. Bài học tập trung chẩn đoán trường hợp CSRF nhưng luôn giữ bước xác minh nguyên nhân.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao CSRF token có thể được tạo **deferred/lazy** trong Spring Security hiện đại.
- Phân biệt CSRF token repository, cách token được expose cho view/SPA và cách token được đọc trên request POST.
- Sửa form server-rendered và SPA khi token chưa được tạo hoặc chưa được tải.
- Hiểu sự khác nhau giữa giá trị CSRF **thực** và giá trị **được mask** để giảm nguy cơ BREACH.
- Xử lý trường hợp token đổi sau login/logout hoặc session hết hạn.
- Cấu hình và kiểm thử trên **Servlet** lẫn **Reactive/WebFlux**, không nhầm các filter/repository giữa hai stack.
- Kiểm tra bằng DevTools, HTTP client, MockMvc, WebTestClient và log có chọn lọc mà không tắt CSRF để “hết 403”.

## 2. CSRF bảo vệ điều gì và áp dụng khi nào?

CSRF khai thác việc trình duyệt **tự gửi thông tin xác thực gắn với phiên/ngữ cảnh**, đặc biệt cookie session, trong request do một trang khác kích hoạt. Nếu server chỉ dựa vào cookie để tin request thay đổi trạng thái, website lạ có thể khiến trình duyệt người dùng thực hiện thao tác không mong muốn.

Ví dụ:

~~~text
Người dùng có session cookie hợp lệ ở app.example.com
        ↓
Trang bên ngoài kích hoạt POST tới app.example.com/profile
        ↓
Browser có thể tự gửi cookie phù hợp theo chính sách cookie
        ↓
Server không được coi cookie là bằng chứng người dùng đã chủ động gửi form
        ↓
CSRF token hoặc cơ chế bảo vệ tương ứng giúp phân biệt request hợp lệ
~~~

Trong Spring Security, cơ chế CSRF mặc định thường kiểm tra các phương thức **không an toàn** như `POST`, `PUT`, `PATCH` và `DELETE`, còn `GET`, `HEAD`, `OPTIONS` và `TRACE` thường được coi là safe theo matcher mặc định. Ứng dụng phải thiết kế để **không thực hiện thay đổi trạng thái quan trọng bằng GET**.

| Trường hợp | CSRF có đáng quan tâm? | Lý do |
|---|---|---|
| Spring MVC với login bằng session cookie | Có | Browser tự gửi session cookie |
| Form HTML POST sau khi đăng nhập | Có | Cookie có thể đi cùng request do trang khác khởi phát |
| SPA cùng origin gọi backend và sử dụng session cookie | Có | Frontend cần gửi token cùng session |
| API nhận HTTP Basic do browser giữ credentials | Cần đánh giá | Browser có thể tự thêm credentials trong một số ngữ cảnh |
| API stateless chỉ nhận Bearer token do code chủ động đặt vào header | Phụ thuộc mô hình đe dọa | Không tự mặc định miễn CSRF nếu có cookie hoặc cách auth khác |
| API JSON chỉ phục vụ GET không thay đổi trạng thái | Không cần CSRF token cho GET mặc định | Không đồng nghĩa được phép chuyển thay đổi trạng thái sang GET |

**CORS, SameSite cookie và CSP là các lớp bổ trợ, không thay thế CSRF token trong mọi trường hợp.** CORS giới hạn việc JavaScript đọc response cross-origin theo cơ chế browser; nó không ngăn mọi khả năng một website gửi request. SameSite hạn chế cookie trong một số ngữ cảnh, nhưng có quy tắc site/origin và yêu cầu triển khai riêng.

## 3. Dòng đời CSRF token trong Servlet

Trong Spring Security Servlet, những thành phần chủ yếu:

- `CsrfFilter`: xử lý cơ chế bảo vệ CSRF trên request được bảo vệ.
- `CsrfTokenRepository`: tải, tạo và lưu giá trị token được dùng để đối chiếu.
- `HttpSessionCsrfTokenRepository`: phương án lưu token trong HTTP session.
- `CookieCsrfTokenRepository`: phương án lưu token trong cookie khi phù hợp với mô hình frontend.
- `CsrfTokenRequestHandler`: cung cấp token cho request/view và xử lý giá trị token do client gửi; Spring Security hiện đại có cơ chế masking chống BREACH.
- `MissingCsrfTokenException` và `InvalidCsrfTokenException`: các loại ngoại lệ thường gặp khi request cần CSRF không có token hoặc token không hợp lệ.

Mô hình khái quát:

~~~mermaid
flowchart TD
    A[GET /profile] --> B[Security chain chứa CsrfFilter]
    B --> C[Deferred CsrfToken]
    C --> D{View / controller / endpoint có truy cập token không?}
    D -- Có --> E[Repository tải token hoặc sinh/lưu token mới]
    E --> F[Token được render vào HTML / JSON / cookie phù hợp]
    D -- Không --> G[Không nhất thiết nạp hoặc tạo token ngay]
    F --> H[Browser lưu session/cookie và nhận token]
    H --> I[POST /profile kèm token]
    I --> J[CsrfFilter lấy expected token từ repository]
    J --> K{Token được gửi có hợp lệ không?}
    K -- Có --> L[Tiếp tục authentication / authorization / controller]
    K -- Không --> M[Từ chối, thường 403]
~~~

Sơ đồ không có nghĩa mọi hệ thống luôn dùng session. Một ứng dụng có thể chọn cookie repository hoặc custom repository, và các filter khác vẫn ảnh hưởng đường request. Điểm cốt lõi là **token phải được materialize, chuyển tới client, lưu lại đúng ngữ cảnh và gửi lại ở request cần xác minh**.

### Cần phân biệt ba hoạt động

| Hoạt động | Thành phần | Dấu hiệu |
|---|---|---|
| Sinh và lưu token dự kiến | `CsrfTokenRepository` | Session/cookie hoặc storage phù hợp có token |
| Đưa token cho frontend | `CsrfTokenRequestHandler`, template, GET `/csrf`, cookie | Hidden input, JSON hoặc cookie xuất hiện |
| Đọc và so khớp token trên POST | `CsrfFilter` + handler + repository | Token được chấp nhận hoặc sinh lỗi CSRF |

**Một token được lưu ở session nhưng không xuất hiện trong form vẫn có thể dẫn tới 403.** Tương tự, một cookie `XSRF-TOKEN` có giá trị không chứng minh request POST đã gửi đúng header và xử lý mask phù hợp.

## 4. Deferred/lazy token: chưa được truy cập thì có thể chưa được tạo

Trong các phiên bản Spring Security hiện đại, việc nạp CSRF token có thể được **trì hoãn** (*deferred*) để tránh truy cập session hoặc lưu token không cần thiết cho các request không dùng nó.

Điều này rất hữu ích: một GET tới trang tĩnh hoặc endpoint không cần token không nhất thiết tạo session chỉ vì hệ thống có CSRF protection. Tuy nhiên nó có thể khiến developer hiểu nhầm:

~~~text
GET /profile
  → CsrfFilter chuẩn bị cơ chế lấy token
  → Controller trả template nhưng template không đọc _csrf
  → Request kết thúc mà không cần materialize token

POST /profile
  → Browser không gửi token
  → CsrfFilter từ chối
  → 403 Forbidden
~~~

**Đây không phải lỗi Spring Security “quên sinh token”.** Frontend chưa yêu cầu tải/hiển thị token theo luồng đã thiết kế.

### Kích hoạt việc tạo/tải token khi thực sự cần

Ví dụ trong MVC:

~~~java
import org.springframework.security.web.csrf.CsrfToken;

// Trong một controller đã nhận request được Spring Security xử lý:
CsrfToken csrfToken =
    (CsrfToken) request.getAttribute("_csrf");

if (csrfToken == null) {
    throw new IllegalStateException("CSRF attribute not available");
}

String tokenForClient = csrfToken.getToken();
~~~

`getToken()` là thao tác cần thiết khi muốn lấy giá trị token cho client; tùy repository/handler, nó làm deferred token được resolve và lưu khi cần. **Không gọi getter chỉ để log token** hoặc đặt nó vào header công khai ngoài nhu cầu; CSRF token là dữ liệu bảo mật.

Tên request attribute thường là `_csrf`, nhưng cách expose có thể được tùy biến bởi `CsrfTokenRequestHandler`. Luôn kiểm tra tên thực tế khi dùng custom config.

### Dấu hiệu nhận biết lazy loading

- GET HTML trả 200 nhưng DOM không có hidden input CSRF.
- Dùng cookie repository mà GET không trả `Set-Cookie: XSRF-TOKEN=...` theo kỳ vọng.
- Sau khi thêm một endpoint GET thật sự đọc token, cookie/JSON hoặc form xuất hiện token và POST thành công.
- Log không cho thấy token repository bị đọc ở GET vốn không cần CSRF; điều này có thể **là tối ưu hóa đúng**, không phải lỗi.

Không nên “sửa” bằng cách gọi `csrf.disable()`. Mục tiêu là **cung cấp token khi frontend cần**, không phải loại bỏ bước xác minh.

## 5. Form server-rendered: token phải xuất hiện trong HTML gửi đi

Với một form do Spring MVC/Thymeleaf render:

~~~html
<form th:action="@{/profile}" method="post">
  <label for="displayName">Tên hiển thị</label>
  <input id="displayName" name="displayName" type="text">
  <button type="submit">Lưu</button>
</form>
~~~

Nếu ứng dụng dùng tích hợp Thymeleaf/Spring Security và `RequestDataValueProcessor` theo cấu hình phù hợp, framework có thể **tự thêm hidden input** CSRF cho form POST được xử lý đúng. Không nên giả định tính năng này luôn hoạt động với mọi template engine, custom form tag hoặc HTML được render từ frontend khác.

Một cách chèn tường minh (khi không được tự chèn):

~~~html
<form action="/profile" method="post">
  <input type="text" name="displayName">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Lưu</button>
</form>
~~~

Trong ví dụ Thymeleaf, truy cập `_csrf.token` buộc template cần giá trị token và giúp đường lazy/deferred được materialize. **Không thêm hai input CSRF trùng nhau** nếu framework đã tự chèn một input; kiểm tra HTML cuối cùng và request POST thực tế.

### Cách kiểm tra bằng DevTools

1. Mở **Network → GET /profile → Response/Preview**, tìm hidden input thật sự trong HTML.
2. Kiểm tra `name` và `value` của input, không chỉ attribute trong template source.
3. Submit form; ở **Network → POST /profile → Payload/Form Data**, xác nhận parameter được gửi và session cookie phù hợp đi cùng request.
4. Nếu POST vẫn 403, xem `MissingCsrfTokenException` hay `InvalidCsrfTokenException`/cấu hình handler thay vì đoán từ UI.

**Với mẫu HTML có token chống BREACH, giá trị token render ở form có thể khác giữa các GET** dù token underlying trong session không đổi. Không suy luận từ khác biệt của chuỗi hidden input rằng session token đã bị xoay vòng.

### Lỗi do HTML render sai đường

Form có thể được:

- Sinh bởi Thymeleaf nhưng thay `th:action` bằng HTML tĩnh ở một đoạn code mới.
- Trả từ CDN dưới dạng HTML đã build, không đi qua Spring MVC.
- Render bằng React/Vue/Angular, không có `_csrf` request attribute.
- Chứa input disabled, nằm ngoài form hoặc bị JavaScript xóa trước khi submit.
- Gửi bằng `fetch`/XHR nhưng code chỉ lấy dữ liệu từ một số field và **quên token hidden**.

Trong các trường hợp này cần kiểm tra **request thực gửi**, không chỉ nhìn giao diện.

## 6. SPA: token không tự xuất hiện chỉ vì người dùng đã đăng nhập

Một Single Page Application có thể tải HTML/JS từ CDN, còn Spring Security phục vụ API dùng session cookie. Không có Thymeleaf render form, nên frontend phải có **luồng lấy token rõ ràng**.

Phương án thường dùng:

1. Browser mở ứng dụng, có hoặc tạo session theo cơ chế đăng nhập.
2. SPA gọi endpoint GET do backend cung cấp để **materialize và nhận CSRF token**.
3. SPA gửi token trong request POST/PUT/PATCH/DELETE, với **đúng header name** và session cookie tương ứng.
4. Sau khi login/logout hoặc phiên/token đổi, SPA lấy token mới trước request cần bảo vệ.

Ví dụ một endpoint được backend cung cấp:

~~~http
GET /csrf HTTP/1.1
Accept: application/json
Cookie: JSESSIONID=...
~~~

Response minh họa:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "parameterName": "_csrf",
  "headerName": "X-CSRF-TOKEN",
  "token": "TOKEN_VALUE_FROM_SERVER"
}
~~~

`TOKEN_VALUE_FROM_SERVER` là placeholder; không dùng token cố định trong ứng dụng thật. Tên header có thể là `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy repository và cấu hình.

Với token được lưu trong session, frontend phải giữ cùng session khi lấy token và khi POST. Với API cross-origin có cookie, phải cấu hình `fetch` credentials, SameSite/Secure và CORS có chủ đích; không phải mọi website tùy ý đều được đọc endpoint `/csrf`.

## 7. Servlet: endpoint GET /csrf giải quyết lazy loading

Ví dụ Spring MVC controller cấp CSRF token cho SPA:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfTokenController {

    @GetMapping("/csrf")
    public ResponseEntity<CsrfToken> csrf(CsrfToken csrfToken) {
        // CsrfToken được Spring Security expose trong request.
        // Serialization của token làm giá trị cần thiết được truy cập.
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(csrfToken);
    }
}
~~~

Endpoint này **không thay thế CsrfFilter**. Nó chỉ trả token cho client, còn Spring Security tiếp tục xác minh token trên các request cần bảo vệ.

Các điều kiện để hoạt động:

- Route `/csrf` thực sự đi qua `SecurityFilterChain` có CSRF protection và request attribute phù hợp.
- Quy tắc authorization cho GET `/csrf` được chọn theo luồng login/SPA: có thể cho phép truy cập mà không cần login nếu thiết kế cần token trước form login, nhưng phải đánh giá auth/CORS/cache.
- Response không được cache công khai; không gửi token qua analytics, log hay URL query.
- Serializer phải gọi giá trị token theo đúng cấu hình; nếu có custom serializer/handler, nên kiểm tra JSON thực tế.
- Khi SPA dùng session cookie, cookie/session phải đồng nhất giữa GET token và POST.

### SecurityFilterChain ví dụ

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
            .requestMatchers(HttpMethod.GET, "/profile").authenticated()
            .requestMatchers(HttpMethod.POST, "/profile").authenticated()
            .anyRequest().authenticated()
        );

        http.formLogin(Customizer.withDefaults());
        http.csrf(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Ví dụ này chỉ minh họa tích hợp CSRF. Nó không tạo user, database, trang profile hoặc toàn bộ API. Nếu dự án có nhiều security chains, cần kiểm tra chain nào match `/csrf` và `/profile`; một route `/csrf` bị đưa sang chain khác không có CSRF có thể không có request attribute cần thiết.

### JavaScript lấy token và gửi kèm POST

~~~javascript
async function loadCsrfToken() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Cannot load CSRF token");
  }
  return response.json();
}

async function saveProfile(displayName) {
  const csrf = await loadCsrfToken();

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
    throw new Error("Profile save failed: " + response.status);
  }
}
~~~

`credentials: "same-origin"` phù hợp khi SPA và API ở **cùng origin**. Nếu API nằm ở origin khác, cần cơ chế cookie/CORS được thiết kế rõ ràng; không đổi thành `include` bừa bãi hay cho phép mọi origin đọc token. Đoạn JS không tự triển khai validation, authentication hay lỗi nghiệp vụ; nó chỉ minh họa CSRF token flow.

## 8. Session repository và cookie repository: token “nằm ở đâu”?

Khi chẩn đoán, trước tiên tìm **repository được cấu hình trong security chain thực sự xử lý request**.

| Repository | Token được lưu ở đâu? | Cách đưa token cho frontend | Lỗi phổ biến |
|---|---|---|---|
| `HttpSessionCsrfTokenRepository` | HTTP session của server | Hidden input hoặc endpoint `GET /csrf` | GET chưa materialize, session không khớp, thiếu cookie phiên |
| `CookieCsrfTokenRepository` | Cookie CSRF do server phát | JavaScript đọc cookie nếu cookie cho phép, hoặc endpoint phù hợp | Cookie chưa được tạo, HttpOnly, Path/Domain/Secure, header sai |
| Custom `CsrfTokenRepository` | Phụ thuộc ứng dụng | Theo hợp đồng custom | Lưu/tải không đồng bộ, key khác nhau, cache hoặc cluster |

**Cookie CSRF không thay thế cookie xác thực.** Ví dụ một SPA dùng session cookie `JSESSIONID` và cookie `XSRF-TOKEN`: cookie đầu tiên nhận diện phiên; cookie thứ hai chứa giá trị mà frontend cần đưa vào header để chứng minh request không đơn thuần được kích hoạt từ một trang khác.

Đối với repository dựa trên session, **expected token** thường gắn với session. Nếu GET token ở session A nhưng POST dùng session B, token của A sẽ không khớp.

### Triệu chứng của session không đồng bộ

~~~text
GET /csrf
  Cookie: JSESSIONID=A
  -> token_A

POST /profile
  Cookie: JSESSIONID=B
  X-CSRF-TOKEN: token_A
  -> expected token_B hoặc chưa có token
  -> 403
~~~

Điều này có thể xảy ra khi:

- Browser không gửi cookie ở POST vì `SameSite`, `Secure`, domain hoặc Path.
- SPA lấy token từ API ở hostname khác mà không gửi credentials đúng.
- Session đã hết hạn hoặc bị invalidated.
- Sau login/logout session đã đổi, nhưng frontend vẫn giữ token cũ.
- Ứng dụng dùng nhiều node với session storage không nhất quán.
- Proxy hoặc cache phục vụ nội dung HTML/token của session khác.

Đừng coi token dạng chuỗi “có giá trị” là đủ; phải xác minh **cùng context và cùng repository**.

## 9. CookieCsrfTokenRepository và tên cookie/header

Với ứng dụng Servlet mà JavaScript cần lấy token từ cookie, có thể cân nhắc:

~~~java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

CookieCsrfTokenRepository repository =
    CookieCsrfTokenRepository.withHttpOnlyFalse();
~~~

Một cấu hình thường gặp sử dụng:

~~~text
Cookie: XSRF-TOKEN=<giá trị token>
Request header: X-XSRF-TOKEN: <giá trị token>
Request parameter: _csrf=<giá trị token>
~~~

**Vì sao `withHttpOnlyFalse()` không phải lựa chọn mặc định cho mọi ứng dụng?** Nó làm token trong cookie có thể được JavaScript cùng origin đọc. Điều này phục vụ cơ chế SPA, nhưng làm giảm một hàng rào ngăn JavaScript truy cập token. Nếu dùng form server-rendered hoặc `GET /csrf` JSON với cookie session HttpOnly, bạn có thể không cần đặt cookie CSRF đọc được bằng JavaScript.

Lưu ý:

1. Cookie CSRF có thể **chưa được phát** nếu deferred token chưa được nạp/khởi tạo.
2. Tên cookie và header có thể tùy biến; không hard-code `X-CSRF-TOKEN` nếu repository đang chờ `X-XSRF-TOKEN`.
3. Phải kiểm tra `Path`, `Domain`, `Secure`, `SameSite` và việc browser có gửi/cho đọc cookie trong môi trường thật.
4. Cookie CSRF không được phép bị website khác đọc tùy ý. Một cấu hình CORS rộng cho endpoint token có thể phá ranh giới bảo vệ.
5. Nếu dùng nhiều host hoặc subdomain, phải thiết kế domain/path cookie có chủ đích; không đặt `Domain=.example.com` chỉ để “mọi nơi đều có token”.

### Cấu hình repository trong Servlet

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Một phần cấu hình HttpSecurity của chain áp dụng cho HTML/API đó:
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
~~~

**Đoạn cấu hình này chưa phải giải pháp SPA đầy đủ** với Spring Security sử dụng token masking và deferred token: bạn còn phải xác minh token thực sự được khởi tạo, cách handler giải mã giá trị header và việc làm mới token sau authentication/logout. Không chỉ thêm repository rồi kết luận mọi framework SPA sẽ tự hoạt động.

## 10. BREACH masking: token trong HTML có thể khác token thật trong repository

Để giảm rủi ro tấn công nén phản hồi kiểu **BREACH**, Spring Security Servlet hiện đại thường dùng `XorCsrfTokenRequestAttributeHandler` để cung cấp giá trị token được mask trên request/view. Mỗi lần mask có thể tạo chuỗi khác nhau dù **token thực** được lưu trong repository không đổi.

Hãy phân biệt:

| Giá trị | Nguồn | Cách dùng |
|---|---|---|
| Token thực (*raw*) | CSRF repository/session hoặc cookie | Dùng làm expected secret/reference |
| Token được mask | Token request attribute xuất cho HTML | Gửi lại theo cơ chế handler có khả năng giải mã |
| Token trong header do JS gửi | JSON bootstrap hoặc cookie | Handler phải hiểu đúng dạng raw/masked |

Ví dụ minh họa:

~~~text
Expected token trong repository:  token_ABC

GET /profile lần 1:
  hidden _csrf = MASKED_1(token_ABC)

GET /profile lần 2:
  hidden _csrf = MASKED_2(token_ABC)

POST hợp lệ:
  Client gửi masked token nhận từ form
  Handler khôi phục giá trị và so với token_ABC
~~~

**Không nên tự strip/mask/hash token ở frontend.** Hãy sử dụng chính giá trị mà server cung cấp với handler/repository tương ứng. Việc khác nhau giữa hai hidden token không đủ chứng minh CSRF token bị rotate hoặc bug cache.

### Bẫy SPA đọc raw cookie

Một SPA đọc cookie `XSRF-TOKEN` thường nhận **raw token**. Nếu server đang dùng handler chỉ chờ một token dạng mask từ request attribute, việc gửi raw token ở header có thể không được giải mã như mong đợi và dẫn đến 403.

Đây là lỗi **token đã gửi nhưng không được handler chấp nhận**, khác với lỗi token không được tạo. Phải nhìn cả repository lẫn `CsrfTokenRequestHandler`.

### Ví dụ handler kết hợp cho SPA và form Servlet

Một phương án theo mô hình Spring Security hiện đại là dùng:

- `XorCsrfTokenRequestAttributeHandler` cho việc expose/mask token ở form HTML.
- `CsrfTokenRequestAttributeHandler` đọc token thô từ header do SPA lấy ở cookie.
- Chủ động resolve deferred token khi cần phát cookie cho SPA.

Ví dụ một class minh họa:

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

    private final CsrfTokenRequestAttributeHandler plain =
        new CsrfTokenRequestAttributeHandler();

    private final XorCsrfTokenRequestAttributeHandler xor =
        new XorCsrfTokenRequestAttributeHandler();

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            Supplier<CsrfToken> csrfToken) {
        // HTML/form vẫn dùng giá trị mask chống BREACH.
        xor.handle(request, response, csrfToken);

        // SPA muốn cookie có sẵn phải trigger deferred token.
        csrfToken.get();
    }

    @Override
    public String resolveCsrfTokenValue(
            HttpServletRequest request,
            CsrfToken csrfToken) {
        String headerValue = request.getHeader(csrfToken.getHeaderName());
        if (StringUtils.hasText(headerValue)) {
            // Token raw được SPA gửi từ cookie bằng header.
            return plain.resolveCsrfTokenValue(request, csrfToken);
        }
        // Token ở form HTML có thể được mask.
        return xor.resolveCsrfTokenValue(request, csrfToken);
    }
}
~~~

Cấu hình cho Servlet chain:

~~~java
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(new SpaCsrfTokenRequestHandler())
);
~~~

**Điều kiện và giới hạn:**

- Ví dụ dành cho môi trường Spring Security Servlet có API tương ứng, cần đối chiếu version thực dùng.
- Gọi `csrfToken.get()` trên request qua handler có thể materialize token ở nhiều GET hơn thiết kế lazy mặc định; đó là **trade-off có chủ đích** để SPA có cookie, không phải tối ưu mặc định cho mọi web app.
- Cơ chế cookie phải được kiểm thử sau login/logout, khi server clear token cũ và cần cấp lại giá trị mới.
- Nếu frontend đã nhận **masked token qua JSON** và gửi đúng token đó, đường xử lý có thể khác; không áp dụng handler raw-cookie cho mọi chiến lược.
- Đừng trộn một handler custom không hiểu raw token với cách đọc cookie ở JS và cho rằng 403 đến từ authorization.

### Khi nào nên chọn GET /csrf thay vì readable cookie?

Nếu frontend và backend cùng origin, một endpoint JSON chủ động materialize token với `Cache-Control: no-store` có thể dễ kiểm soát hơn việc ép cookie xuất hiện trên mọi GET. Với hệ thống dùng form và session, token ở request attribute cho Thymeleaf thường đơn giản nhất.

**Không có một repository/handler tối ưu cho mọi ứng dụng.** Chọn theo kiến trúc SSR/SPA, cookie/session, browser, mô hình nén phản hồi và yêu cầu quyền riêng tư; rồi kiểm thử đường đi đầy đủ.

## 11. Sau login/logout, token cũ có thể không còn hợp lệ

Spring Security có thể xóa hoặc invalidate CSRF token cũ khi authentication thành công hoặc khi logout để chống việc tái sử dụng token không còn phù hợp với security context.

Ví dụ tình huống SPA:

~~~text
GET /csrf trước đăng nhập
  -> token_A

POST /login kèm token_A
  -> login thành công
  -> token cũ có thể bị clear/invalidate

SPA vẫn giữ token_A trong memory/cookie cũ

POST /profile kèm token_A
  -> 403 do expected token mới hoặc thiếu token hiện hành
~~~

**Luồng hợp lệ hơn:**

1. Lấy CSRF token cho form login hoặc request login theo cơ chế ứng dụng.
2. Đăng nhập; chấp nhận việc authentication success có thể thay đổi session/token.
3. **Tải lại CSRF token sau login**, hoặc cho server cấp token mới theo một flow đã được kiểm thử.
4. Khi logout thành công, reset token state ở frontend; nếu có tiếp tục gọi endpoint cần CSRF thì lấy token mới cho ngữ cảnh mới.

Ở SPA, sau login/logout cần kiểm tra cả cookie `XSRF-TOKEN` bị xóa, response có `Set-Cookie` mới hay không, và thời điểm request bootstrap token kế tiếp. **Không giữ token ở localStorage hay sessionStorage vô thời hạn** rồi giả định nó còn đúng qua thay đổi phiên.

### Token được mask đổi không đồng nghĩa token thực đổi

Phân biệt hai sự kiện:

~~~text
GET /profile lần 1 và lần 2:
  masked form token khác nhau
  underlying repository token có thể vẫn giống nhau

Login/logout:
  expected repository token có thể bị clear
  cần cấp/nhận token mới cho phiên hiện tại
~~~

Khi phân tích bug, đừng lấy việc chuỗi hidden `_csrf` đổi giữa hai trang làm chứng cứ session đã reset. Cần xem vòng đời repository, authentication và cookie/session, không ghi log raw token.

## 12. Cookie, SameSite, Secure và việc browser không mang đúng phiên

Một token có thể được tạo và client nhận được, nhưng POST vẫn bị 403 vì browser không gửi cùng session:

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh |
|---|---|---|
| GET `/csrf` có token, POST không gửi `JSESSIONID` | `SameSite`, `Secure`, Path/Domain, fetch credentials | Xem request Cookie và Application/Cookies trong DevTools |
| Cookie CSRF có tại API origin nhưng JS không đọc được | `HttpOnly`, khác origin, Path | Xem cookie scope và cách cấp token |
| Local HTTP hoạt động, HTTPS/proxy thất bại | Reverse proxy không truyền scheme đúng, cookie Secure/callback URL sai | Kiểm tra TLS termination và trusted forwarded headers |
| Token GET ở node A, POST tới node B bị invalid | Session storage không chia sẻ hoặc routing sai | Kiểm tra session replication/storage, affinity nếu có |
| Chỉ lỗi sau thời gian chờ | Session timeout, token stale | Kiểm tra session lifetime và bootstrap lại |
| SPA và API khác origin, GET token được nhưng POST mất cookie | `fetch` credentials hoặc chính sách cookie không phù hợp | Đo cả hai request, đừng chỉ xem response JSON |
| Request preflight OPTIONS bị 403 | CORS không cho Origin/method/header | Kiểm tra preflight trước khi đổ lỗi CSRF |

**Site khác origin.** Hai subdomain có thể same-site theo một số quy tắc cookie nhưng vẫn là **cross-origin** đối với SOP/CORS. Đừng suy rằng vì cookie được gửi nên JavaScript được phép đọc `/csrf` từ một origin khác.

Nếu cần cross-origin credentials, CORS phải cho phép origin cụ thể, phương thức và headers cần thiết; không dùng wildcard origin cho credentialed requests. Cấu hình `SameSite=None` thường đi cùng yêu cầu `Secure` trên browser hiện đại, nhưng chỉ dùng khi có lý do nghiệp vụ và đã đánh giá CSRF/cookie privacy.

## 13. CORS có thể chặn trước khi CSRF được kiểm tra

Khi SPA gửi header CSRF tùy chỉnh tới API khác origin, browser có thể tạo preflight:

~~~http
OPTIONS /profile HTTP/1.1
Origin: https://frontend.example.net
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Nếu CORS configuration không cho `X-CSRF-TOKEN` hoặc origin đang dùng, browser có thể không gửi request POST thực. Developer nhìn frontend báo lỗi rồi nghĩ token thiếu, nhưng **CSRF filter của POST chưa hề chạy**.

### Trình tự chẩn đoán

1. Xem **Network → OPTIONS** và header `Access-Control-Request-Headers`.
2. Kiểm tra response preflight có cho đúng origin, method và header CSRF không.
3. Xác nhận trình duyệt có gửi request POST thật không.
4. Nếu POST đã gửi và nhận 403, xem CSRF validation, authentication và authorization riêng.
5. Nếu preflight thành công nhưng JS không đọc được response, kiểm tra CORS response của request thật; đừng tự nới CSRF.

Đặt CORS ở backend API và tích hợp đúng security chain. **`permitAll()` cho OPTIONS không tự tạo CORS headers**. Ngược lại, cho phép CORS không tự cấp quyền nghiệp vụ hoặc tự gắn CSRF token vào request.

## 14. Security chain thực tế quyết định repository/handler nào áp dụng

Một dự án có hai Servlet chains:

~~~text
API chain: /api/** -> session/API auth, CSRF config A
Web chain: phần còn lại -> form login, CSRF config B
~~~

Nếu `GET /csrf` được phục vụ bởi web chain nhưng `POST /api/profile` đi vào API chain dùng repository khác, token lấy ở GET có thể không khớp POST dù đều thuộc cùng ứng dụng.

Các lỗi thường gặp:

- `GET /csrf` trả token từ session, POST dùng cookie repository.
- `GET /csrf` đi qua chain không bật CSRF nên request attribute không có.
- Một chain dùng `CookieCsrfTokenRepository` nhưng chain khác dùng `HttpSessionCsrfTokenRepository`.
- Rule `securityMatcher("/api/**")` che/không bao phủ route dự kiến.
- Fallback chain đứng trước API chain nên cả hai route dùng entry point/repository không đúng.
- Bỏ Spring Security qua `web.ignoring()` thay vì `permitAll()` khiến token không được expose.

**Tìm chain đã chọn bằng log, matcher và test**, sau đó mới so sánh repository/handler. Không chữa bằng cách thêm cùng một token tĩnh ở mọi chain.

### PermitAll không có nghĩa bỏ qua CSRF

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/form").permitAll()
    .anyRequest().authenticated()
);
~~~

Nếu chain vẫn bật CSRF, POST `/public/form` có thể cần token dù endpoint được `permitAll()` ở bước authorization. Đây là hành vi **đúng thiết kế**: authorization và CSRF kiểm tra những rủi ro khác nhau.

### Một API stateless không có cookie

Nếu một API **thật sự chỉ dùng Bearer token do JavaScript chủ động gắn vào `Authorization` và không dựa vào browser tự gửi credentials**, đội ngũ có thể chọn cơ chế bảo vệ CSRF khác hoặc giới hạn các endpoint cần CSRF bằng matcher phù hợp.

Phải xác minh không còn cookie session, HTTP Basic/browser auth hoặc đường xác thực ambient khác. Không sao chép công thức `csrf.disable()` lên toàn bộ ứng dụng chỉ vì một API dùng JSON. Đặc biệt, frontend dùng cookie credentials vẫn cần được đánh giá CSRF dù API trả JSON.

## 15. Reactive/WebFlux: token dưới dạng Mono và việc subscribe

Trong **Spring Security Reactive/WebFlux**, cơ chế tương ứng được thực hiện bằng các thành phần như:

- `CsrfWebFilter`: xử lý CSRF trên reactive web exchange.
- `ServerCsrfTokenRepository`: tải, sinh và lưu token.
- `WebSessionServerCsrfTokenRepository`: repository dựa trên web session.
- `CookieServerCsrfTokenRepository`: repository dùng cookie theo thiết kế SPA nếu phù hợp.
- Các `ServerCsrfTokenRequestHandler` liên quan đến cách đưa/đọc giá trị token.

**Không dùng Servlet `CsrfFilter`, `HttpSessionCsrfTokenRepository` hoặc `HttpServletRequest` trong WebFlux.** Reactor làm việc với luồng publisher, nên việc có một `Mono<CsrfToken>` chưa đảm bảo giá trị token đã được tính nếu không có subscriber tiêu thụ nó.

### 15.1. Endpoint materialize CSRF token trong WebFlux

Spring Security WebFlux có thể expose `Mono<CsrfToken>` trong `ServerWebExchange` attributes với key theo `CsrfToken.class.getName()`. Một endpoint minh họa:

~~~java
import org.springframework.http.CacheControl;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCsrfTokenController {

    @GetMapping("/csrf")
    public Mono<CsrfToken> csrf(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders()
            .setCacheControl(CacheControl.noStore());

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "No CSRF token attribute: check security chain"
            ));
        }
        return tokenMono;
    }
}
~~~

Việc trả `Mono<CsrfToken>` cho WebFlux serialization làm publisher được subscribe trong quá trình tạo response, nên CSRF token cần thiết được materialize. Ví dụ này giả định Spring Security WebFlux phiên bản tương thích và endpoint đi qua đúng `SecurityWebFilterChain` có CSRF được cấu hình.

Nếu code chỉ lấy `Mono<CsrfToken>` từ attribute nhưng không trả, subscribe hoặc xử lý nó đúng cách, token có thể **chưa được tải/tạo** — tương tự vấn đề deferred ở Servlet. Không gọi `block()` trong reactive request flow để ép token, vì có thể chặn event-loop hoặc làm sai mô hình xử lý.

### 15.2. SecurityWebFilterChain cho luồng SPA

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        http.authorizeExchange(auth -> auth
            .pathMatchers(HttpMethod.GET, "/csrf").permitAll()
            .pathMatchers("/profile").authenticated()
            .anyExchange().authenticated()
        );

        http.csrf(Customizer.withDefaults());
        http.formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Nếu WebFlux chỉ phục vụ API còn HTML do CDN trả, endpoint token thuộc backend API và phải đáp ứng chính sách CORS/credentials phù hợp. CSP của **response HTML** được phát ở frontend, không phải do việc bật CSRF tại WebFlux tự thêm vào trang CDN.

### 15.3. Cookie repository trong Reactive

Ở WebFlux, repository có thể được chọn thông qua:

~~~java
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;

http.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()
    )
);
~~~

Những vấn đề tương tự Servlet vẫn tồn tại: deferred token, cookie có được phát không, JS có đọc được không, token đổi sau login/logout và cách reactive request handler tiếp nhận token. **Đừng giả định chỉ chuyển tên class là tương đương hoàn toàn**: phải kiểm tra kiểu token thực, header và hành vi WebFlux phiên bản đang dùng.

## 16. MockMvc: tách kiểm thử CSRF filter với kiểm thử tải token thật

MockMvc cung cấp helper từ `spring-security-test` để kiểm tra đường CSRF. Ví dụ ứng dụng có endpoint `POST /profile` cho user đã xác thực và controller trả HTTP 204 khi thành công.

### 16.1. Không có token → thường 403

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/profile")
        .with(user("alice").roles("USER"))
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isForbidden());
~~~

**Điều kiện:** route nằm trong Servlet security chain có CSRF protection, không có ngoại lệ matcher bỏ qua và POST đến controller khi token hợp lệ. Nếu application dùng custom denied handler hoặc proxy ngoài MockMvc, status có thể khác.

### 16.2. Token do helper tạo → vượt qua CSRF filter

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;

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

Hai ca giúp xác minh CSRF filter từ chối/cho qua token, nhưng **`with(csrf())` không chứng minh frontend đã tải token đúng**. Helper tạo token cho test, có thể che mất bug real-world như thiếu hidden input hoặc cookie không được phát sau GET.

### 16.3. Test luồng GET /csrf → POST /profile thật sự

Với **`HttpSessionCsrfTokenRepository` mặc định** trong cấu hình Servlet minh họa, có thể lấy token qua endpoint thật, giữ cùng session và gửi POST:

~~~java
import com.jayway.jsonpath.JsonPath;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

MvcResult bootstrap = mockMvc.perform(get("/csrf"))
    .andExpect(status().isOk())
    .andReturn();

String json = bootstrap.getResponse().getContentAsString();
String token = JsonPath.read(json, "$.token");
String headerName = JsonPath.read(json, "$.headerName");

MockHttpSession session =
    (MockHttpSession) bootstrap.getRequest().getSession(false);
assertNotNull(session, "Expected session from HttpSessionCsrfTokenRepository");

mockMvc.perform(post("/profile")
        .session(session)
        .with(user("alice").roles("USER"))
        .header(headerName, token)
        .contentType("application/json")
        .content("{\"displayName\":\"Alice\"}"))
    .andExpect(status().isNoContent());
~~~

**Phạm vi của ví dụ:** test này giả định Spring MVC endpoint `GET /csrf` tồn tại, session repository được dùng, MockMvc đã tích hợp Spring Security và `JsonPath` có sẵn trong test dependencies. Với CookieCsrfTokenRepository, cần chuyển đúng cookie sang request thay vì giả định `MockHttpSession` được tạo.

Ngoài việc POST thành công, test nên có ca bỏ token trong **chính session đó** để xác nhận 403. Khi endpoint trả masked token, phải gửi nguyên giá trị được endpoint cấp và để request handler xử lý; **không tự giải mã hoặc cắt chuỗi** trong test.

### 16.4. Thử lỗi token cũ sau login/logout

Một test integration thực tế có thể:

1. GET `/csrf` và nhận token A.
2. Hoàn thành login bằng session A theo cơ chế ứng dụng.
3. Gửi POST với token A; quan sát nó có bị invalidate theo cấu hình không.
4. GET `/csrf` sau login và nhận token tương ứng với session hiện tại.
5. Gửi POST với token mới và xác nhận controller được gọi.

Không dùng `with(csrf())` cho bước 3–5 nếu mục tiêu là xác minh vòng đời token thực sự trong repository. Cần kiểm soát authentication/session cookies và security chain trong test.

## 17. WebTestClient: Reactive CSRF filter và giới hạn của mock helper

Với Spring Security WebFlux, dùng helper Reactive:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

// Đã authenticated nhưng POST không có CSRF token.
webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .post()
    .uri("/profile")
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isForbidden();

// Test helper tạo request hợp lệ theo CSRF test support.
webTestClient.mutateWith(mockUser("alice").roles("USER"))
    .mutateWith(csrf())
    .post()
    .uri("/profile")
    .bodyValue("{\"displayName\":\"Alice\"}")
    .exchange()
    .expectStatus().isNoContent();
~~~

Giống Servlet, các ca trên cần route `POST /profile` và WebTestClient được gắn Spring Security; giả định controller trả 204 sau khi request qua CSRF/auth/authorization.

Test riêng endpoint lazy token:

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

Đoạn test yêu cầu WebFlux controller ở mục 15 và JSON serializer hoạt động. Đây là test **endpoint đã materialize token**, không đủ chứng minh browser giữ đúng session/cookie giữa GET và POST.

Muốn kiểm tra end-to-end, cần dùng WebTestClient gắn **HTTP server thật với session/cookie được chuyển tiếp** hoặc Playwright/browser test. Các mock helper `csrf()` không kiểm tra lỗi CORS, SameSite cookie, proxy cache hay việc frontend thực sự gọi GET token trước POST.

## 18. Kiểm tra bằng DevTools: ba request cần xem cùng nhau

Khi frontend báo lỗi 403, đừng chỉ xem một POST thất bại. Mở DevTools → Network và sắp theo thời gian:

<escape>**A. GET HTML/GET /csrf → B. POST /login (nếu có) → C. POST /profile**</escape>

### A. GET trang hoặc GET token

- Có HTTP 200 thật, không phải 302 tới login hoặc response cache cũ?
- Nếu là HTML form, có hidden input `_csrf` đúng trong HTML gửi về không?
- Nếu là JSON, có `token`, `headerName` và response `Cache-Control: no-store` không?
- Nếu dùng cookie repo, response có `Set-Cookie: XSRF-TOKEN=...` khi cần không?
- Session cookie có được gắn đúng không?
- Request có đi vào đúng security chain bật CSRF không?

### B. Sau login/logout

- Authentication có thay session hoặc clear token không?
- SPA có lấy lại token sau khi security context thay đổi không?
- Có response mới cấp token/cookie sau login không?
- Có request bất đồng bộ gửi bằng token cũ **trước khi** việc refresh token hoàn thành không?

### C. POST cần bảo vệ

- Browser có gửi đúng `Cookie` nhận diện session không?
- Có header `X-CSRF-TOKEN`/`X-XSRF-TOKEN` hoặc form parameter `_csrf` đúng không?
- Tên header/parameter có trùng repository/handler server đang chờ không?
- Browser có gửi OPTIONS preflight và bị chặn trước POST không?
- 403 do CSRF exception hay authorization/HTTP firewall/gateway?

Không chia sẻ ảnh Network có nguyên cookie/token. Khi cần gửi ticket, hãy **che toàn bộ secret**, giữ lại tên header, sự hiện diện của giá trị và request ID.

## 19. Chẩn đoán bằng log an toàn

Trong môi trường dev/staging có quyền kiểm soát, bật log có chọn lọc:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.csrf=DEBUG
logging.level.org.springframework.security.web.server.csrf=DEBUG
~~~

Mức và nội dung log thực tế phụ thuộc phiên bản Spring Security. Khi cần, tăng TRACE **tạm thời** cho component cụ thể, nhưng tuyệt đối tránh ghi token raw, cookie, Authorization header hoặc dữ liệu cá nhân vào log công khai.

Các tín hiệu hữu ích:

| Tín hiệu | Giúp xác minh |
|---|---|
| `MissingCsrfTokenException` | Có request bị đánh giá thiếu CSRF token hợp lệ trong bối cảnh filter |
| `InvalidCsrfTokenException` | Token được cung cấp không khớp expected hoặc sai biểu diễn |
| Security chain và đường matcher được chọn | Repository/handler nào đang áp dụng |
| Có `CsrfFilter`/`CsrfWebFilter` trong chain | Request có được CSRF filter xử lý không |
| CSRF token repository được cấu hình | Session, cookie hoặc custom |
| HTTP 302 đến login hoặc 401 challenge | Có thể là authentication, không phải CSRF |
| CORS preflight 403 | POST có thể chưa được gửi |
| RequestRejectedException hoặc WAF block | Có thể request bị từ chối trước CSRF |

**Không suy rằng chỉ có một kiểu exception cho “thiếu token”.** Spring Security có thể phân biệt repository chưa có expected token với trường hợp expected token có nhưng request không gửi/không khớp. Tên exception cụ thể còn phụ thuộc filter, repository và request handler.

### Gợi ý quy trình log

1. Tìm request/correlation ID trong app, proxy và browser.
2. Xác định request có đến Spring không và chain nào xử lý.
3. Tìm filter hoặc exception đã sinh phản hồi.
4. Xác minh expected token từ đúng repository **không ghi giá trị token ra log**.
5. Xem giá trị token do client gửi có mặt không; nếu có, phân loại sai session, sai tên, masked/raw hoặc token stale.
6. Tái hiện sau khi sửa bằng test POST có/không token và browser thực tế.

## 20. Bảng chẩn đoán theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Phép kiểm tra ưu tiên | Cách xử lý đúng hướng |
|---|---|---|---|
| Form POST 403, HTML không có input `_csrf` | Template không materialize token; không có tích hợp form processor | Xem response HTML và request Form Data | Dùng tích hợp template đúng hoặc render hidden input |
| SPA không có `XSRF-TOKEN` cookie sau GET | Deferred token chưa được truy cập; cookie Path/Domain | Xem GET response và repository | Chủ động GET token hoặc handler phù hợp |
| GET `/csrf` trả 302 login | Route không được permit khi cần, sai chain | Xem response `Location` và chain | Đặt auth rule cho token endpoint theo thiết kế |
| GET `/csrf` trả 500 vì attribute null | Endpoint không đi qua CSRF-enabled chain | Kiểm tra filter chain/matcher | Bảo đảm route được CSRF filter xử lý |
| GET `/csrf` trả token, POST không có header | Frontend bỏ qua kết quả hoặc request chạy trước bootstrap | DevTools Initiator, Headers, JavaScript flow | Await token bootstrap và gắn đúng header |
| POST có header nhưng 403 | Token stale, sai session hoặc raw/masked handler không tương thích | Repository/handler và authentication session | Đồng bộ phiên, request handler, rotate token |
| Token đổi sau login, AJAX dùng giá trị cũ | Token cũ bị clear sau authentication | Network login → token GET → POST | Fetch token mới sau login/logout |
| POST browser không gửi `JSESSIONID` | Cookie SameSite/Secure/Path/Domain hoặc credentials | Request Cookies trong Network | Sửa cấu hình cookie/credentials có chủ đích |
| Cross-origin POST không xuất hiện | OPTIONS CORS bị từ chối | Network preflight, console | Sửa CORS API; giữ CSRF |
| POST nhận 403 nhưng không có CSRF exception | Authorization, method security, WAF, firewall, custom handler | Trace filter/correlation ID | Điều tra tầng từ chối thực |
| Cùng code local PASS, production FAIL | CDN cache HTML, proxy rewrite, session cluster, cookie Secure | So sánh origin/public path | Sửa cache/proxy/session, không mở quyền vô tội vạ |
| `with(csrf())` PASS nhưng browser POST 403 | Test helper bỏ qua frontend token loading | Browser E2E và GET token flow | Sửa cách token được tải/gửi |
| Form hidden token thay đổi sau reload | Token masked lại cho mỗi response | So sánh repo/session và handler | Không coi là lỗi rotate nếu expected token vẫn hợp lệ |
| Servlet test PASS, WebFlux test FAIL | Dùng nhầm repository/API hoặc chưa subscribe `Mono<CsrfToken>` | Kiểm tra `CsrfWebFilter` và token Mono | Dùng reactive API và endpoint subscribe đúng |
| Request `/csrf` trả token nhưng cache ở edge | Proxy/CDN cache response chứa token | Kiểm tra Cache-Control, Age, cache status | `no-store` và cấu hình CDN không cache |
| User đăng nhập bằng form POST 403 | Form login thiếu token; login page không expose | Inspect login HTML và POST login | Đưa CSRF token vào login form |
| Logout POST 403 | Logout request thiếu token hoặc dùng token đã hết hạn | Logout form/fetch và security chain | Gửi CSRF token hợp lệ, không mở logout qua GET |
| Basic/Bearer API GET 401, POST 403 | Authentication và CSRF có thể từ chối ở các bước khác nhau | Entry point, auth scheme, CSRF logs | Tách kiểm tra hai nguyên nhân |

Một dấu hiệu có thể có **nhiều nguyên nhân đồng thời**. Ví dụ POST không có CSRF header vì frontend quên gắn token, và session cookie cũng không đi cùng request; sửa một lỗi chưa chắc làm POST thành công. Phải kiểm tra lại luồng toàn bộ sau mỗi thay đổi.

## 21. Quy trình điều tra từng bước

~~~mermaid
flowchart TD
    A[POST/PUT/PATCH/DELETE thất bại] --> B{HTTP request thật tới API chưa?}
    B -- Chưa --> C[Browser CSP/CORS/mixed content/network]
    B -- Có --> D{Spring CSRF filter xử lý request?}
    D -- Không --> E[Security chain, proxy/WAF, firewall, auth, controller]
    D -- Có --> F{Expected token đã có trong repository?}
    F -- Chưa rõ/Chưa --> G[Deferred loading, GET token/form, session/cookie repository]
    F -- Có --> H{Client gửi token đúng tên/vị trí?}
    H -- Không --> I[Template hidden input / SPA bootstrap / header]
    H -- Có --> J{Token khớp expected qua request handler?}
    J -- Không --> K[Session mismatch, masking, rotation, stale cookie]
    J -- Có --> L[Kiểm tra authorization/controller và kết quả nghiệp vụ]
    G --> M[Test GET -> POST cùng session]
    I --> M
    K --> M
    M --> N[Browser E2E + regression test]
~~~

**Thứ tự sử dụng thực tế:**

1. **Xác nhận request và status:** browser có gửi POST thật không? Có preflight lỗi hoặc CSP chặn trước không?
2. **Xác định chain:** `CsrfFilter` Servlet hay `CsrfWebFilter` Reactive có ở chain đang xử lý?
3. **Xác định repository/handler:** session, cookie hay custom? Handler có dùng masking và đọc raw header không?
4. **Xác định token GET:** form HTML, GET `/csrf` hay cookie? Nó có được materialize không?
5. **Đối chiếu session/cookie:** expected token và request POST có thuộc cùng ngữ cảnh hiện tại không?
6. **Kiểm tra thời điểm:** request có xảy ra sau login/logout/session rotation không?
7. **Test có đối chứng:** thiếu token phải bị từ chối, token được tải đúng phải được chấp nhận.
8. **Giữ bảo vệ:** sửa nguồn token, CORS, cookie, handler hoặc cache — không tắt CSRF toàn bộ.

Đừng viết logic ở frontend kiểu **“nếu 403 thì tự lặp POST vô hạn”**. Điều đó có thể tạo thao tác lặp, che nguyên nhân và dẫn đến tác động không mong muốn. Với luồng hợp lệ bị token stale, có thể thiết kế refresh token và thử lại **có kiểm soát** khi đã xác định request chưa được xử lý, ưu tiên các thao tác idempotent hoặc dùng cơ chế chống lặp. Không tự retry một tác vụ thanh toán/đặt hàng chỉ vì 403.

## 22. Kiểm tra HTTP bằng curl và cookie jar

Các lệnh dưới đây dành cho **môi trường lab do bạn kiểm soát**; không phải yêu cầu thực thi trong STEP 4. Giả sử server chạy ở `http://localhost:8080`, endpoint `GET /csrf` trả JSON và endpoint `POST /profile` yêu cầu xác thực hợp lệ.

### Bước A — Lấy token và lưu cookie cùng request

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H 'Accept: application/json' \
  http://localhost:8080/csrf
~~~

Khi gọi, lưu lại từ JSON **tên header và token** theo cách bảo mật; không paste giá trị thật vào ticket. File `cookies.txt` chứa cookie có thể nhạy cảm, nên chỉ dùng trong thư mục test riêng, hạn chế truy cập và xóa an toàn khi kết thúc.

### Bước B — POST không token làm đối chứng

~~~bash
curl -i -b cookies.txt \
  -X POST http://localhost:8080/profile \
  -H 'Content-Type: application/json' \
  --data '{"displayName":"Demo"}'
~~~

Nếu request đi qua CSRF protection và không được miễn, thường nhận 403. Nhưng khi endpoint yêu cầu authentication, request còn có thể nhận 401 hoặc 302 tùy chain/entry point, nên kiểm tra log và không coi status là bằng chứng duy nhất.

### Bước C — POST có token đúng cách

Ví dụ **hình thức request**:

~~~http
POST /profile HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<same-session-cookie>
Content-Type: application/json
X-CSRF-TOKEN: <token-obtained-from-GET-csrf>

{"displayName":"Demo"}
~~~

Hai giá trị trong dấu `<...>` là placeholder, phải lấy từ đúng session và phản hồi server. Tên `X-CSRF-TOKEN` chỉ đúng với repository trả tên header tương ứng; CookieCsrfTokenRepository có thể dùng `X-XSRF-TOKEN`.

Nếu bạn muốn dùng `curl` để thực sự gửi request có token mà không lộ secret trên command line, có thể dùng file cấu hình/secret manager hoặc công cụ HTTP test có cơ chế giữ giá trị bí mật. Không đưa token trực tiếp vào câu lệnh ghi trong lịch sử shell hoặc chụp màn hình.

### Kiểm tra token được materialize nhưng không có cookie

Nếu GET `/csrf` trả token mà response không có session cookie, có thể:

- Repository là cookie repo hoặc storage custom, không phải HttpSession.
- HTTP client đã có session cookie từ request trước nên server không cần `Set-Cookie` mới.
- Token chưa thật sự được materialize dù JSON/serializer dự kiến cần.
- Cookie bị proxy/container xử lý hoặc bị chặn ở browser.

Để biết nguyên nhân, phải nhìn **toàn bộ request/response và repository config**, không chỉ sự hiện diện của `Set-Cookie` trên một response.

## 23. Kịch bản A — Form Thymeleaf không có token vì template không truy cập

**Bối cảnh:** ứng dụng đã có Spring Security CSRF, controller:

~~~java
@GetMapping("/profile")
public String profile() {
    return "profile";
}
~~~

Template mới chỉ có:

~~~html
<form action="/profile" method="post">
  <input type="text" name="displayName">
  <button type="submit">Lưu</button>
</form>
~~~

Ở đường render này, nếu không có tích hợp tự chèn token, HTML không chứa input CSRF. GET có thể vẫn trả 200 vì CSRF protection không yêu cầu token cho GET mặc định; POST thất bại.

**Thử điều tra:**

1. Xác minh response HTML của GET có input hidden CSRF không.
2. Kiểm tra template engine có tự tích hợp token hay không.
3. Xem POST form data đã gửi parameter token chưa.
4. Thêm input `th:name="${_csrf.parameterName}"` và `th:value="${_csrf.token}"` khi cần; tránh trùng input tự chèn.
5. Gửi lại POST với cùng session, xác nhận controller được gọi và authorization vẫn đúng.

**Kết luận:** lỗi không nhất thiết là repository không có khả năng sinh token. **Template không yêu cầu token** nên trình duyệt không có gì để gửi lại.

## 24. Kịch bản B — SPA cookie tồn tại nhưng POST vẫn bị 403

**Bối cảnh:** SPA tại `https://app.example.com` gọi Spring API ở cùng origin qua gateway. Backend dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()`. JS thấy cookie `XSRF-TOKEN` và gửi:

~~~http
X-XSRF-TOKEN: <raw-token-from-cookie>
~~~

Nhưng POST vẫn bị 403.

**Các khả năng phân biệt:**

1. Cookie ở đúng Path/Domain không? Browser đã gửi cookie khi POST chưa?
2. Token có được materialize sau login/logout không, hay cookie đang chứa giá trị cũ?
3. Header name có đúng `X-XSRF-TOKEN` theo repository không?
4. Server có `CsrfTokenRequestHandler` đang mong đợi **masked token** từ form, trong khi JS gửi **raw token** không?
5. GET token và POST có đi qua **cùng chain/repository** không?
6. Proxy có loại hoặc rewrite `X-XSRF-TOKEN` không?

**Sửa có chủ đích:** nếu dùng chiến lược raw cookie cho SPA, chọn request handler phù hợp, kiểm tra việc materialize token và refetch token sau auth/logout. Nếu chỉ cần GET JSON token, có thể dùng endpoint `/csrf` và gửi giá trị phù hợp với handler thay vì mở thêm cookie readable.

Không sửa bằng cách chấp nhận mọi giá trị token, so sánh raw token bằng JavaScript rồi bỏ qua validation server hoặc tắt `CsrfFilter`.

## 25. Kịch bản C — POST chỉ lỗi sau khi đăng nhập hoặc khi chuyển node

**Bối cảnh:** trang login có token hợp lệ, đăng nhập thành công, nhưng request đầu tiên tới `/profile` trả 403. Ở local một node thì ổn, qua load balancer nhiều node thì lỗi xảy ra ngẫu nhiên.

Có hai nhóm nguyên nhân cần tách:

**Nhóm 1 — Token/session chuyển trạng thái sau login**

~~~text
GET /csrf (anonymous/session A) -> token A
POST /login -> authentication success, session/token có thể bị clear/rotate
POST /profile (frontend dùng token A) -> mismatch
~~~

Sửa bằng cách cập nhật CSRF bootstrap sau login, chờ việc nhận token mới hoàn tất trước khi gửi request tiếp.

**Nhóm 2 — Session được lưu/tải không nhất quán qua cluster**

~~~text
GET /csrf tới node 1 -> lưu token trong session store của node 1
POST /profile tới node 2 -> không có expected token tương ứng
~~~

Trong thực hành, cần kiểm tra session storage và routing của load balancer. Nếu dự án dùng shared session store, xác minh các node thực sự đọc/ghi cùng dữ liệu; nếu dùng session affinity, kiểm tra cookie/routing. Không coi stickiness là thay thế cho thiết kế session bảo mật hoặc là bảo đảm khắc phục mọi tình huống.

**Bằng chứng cần thu:** request ID, node phục vụ từng request, trạng thái session (không ghi ID đầy đủ nếu không cần), thời điểm login/logout và loại exception CSRF. Nếu expected token không tồn tại ở node 2, thêm `ROLE_ADMIN` cho user không giải quyết vấn đề.

## 26. Quy tắc an toàn và các anti-pattern cần tránh

| Cách sửa sai | Vì sao rủi ro | Giải pháp thay thế |
|---|---|---|
| `http.csrf(csrf -> csrf.disable())` cho toàn hệ thống để hết 403 | Xóa hàng rào CSRF ở các endpoint dùng cookie/browser credentials | Sửa luồng materialize/transfer token |
| `permitAll()` để “bỏ qua CSRF” | Authorization và CSRF là hai cơ chế khác nhau | Giữ permit đúng nhu cầu, gửi token khi cần |
| Tạo một token cố định trong HTML/config | Token đoán được và không gắn đúng phiên/ngữ cảnh | Dùng repository do Spring Security quản lý |
| Đặt token vào query string của URL | Có thể rò vào lịch sử, log, referrer | Hidden input hoặc header phù hợp |
| Log toàn bộ CSRF token, session cookie | Lộ bí mật và dữ liệu người dùng | Log trạng thái, loại lỗi và correlation ID |
| Cho mọi origin đọc `GET /csrf` | Có thể làm lộ dữ liệu dùng để vượt CSRF trong mô hình không phù hợp | CORS hạn chế, SOP, auth/session phù hợp |
| Gắn readable cookie cho mọi ứng dụng | Tăng khả năng JavaScript đọc CSRF secret | Chọn endpoint JSON/hidden input hoặc policy cookie đúng nhu cầu |
| Trộn raw cookie với XOR handler không hỗ trợ | Token bị từ chối dù đã gửi | Dùng request handler phù hợp |
| Cache công khai HTML/JSON chứa token | Có nguy cơ phát token sai phiên, lộ nội dung | `no-store`, cấu hình CDN/cache có chủ đích |
| Đổi state bằng GET để tránh CSRF | GET có thể bị bên ngoài/preview/prefetch kích hoạt | Dùng unsafe method với CSRF protection |
| Tự retry POST vô hạn khi 403 | Có thể tạo request lặp, che lỗi và tác động nghiệp vụ | Refresh có kiểm soát sau khi xác minh |
| Tắt CORS hoặc thêm wildcard origin | Mở đọc cross-origin ngoài ý định | Cấu hình đúng Origin/method/headers |
| Tắt HttpOnly/SameSite/Secure bừa bãi | Giảm bảo vệ cookie/session | Chỉ thay theo mô hình đã review |
| Kết luận 403 luôn là CSRF | Authorization, WAF, CORS, firewall cũng tạo 403 | Tìm filter/exception thực sự từ chối |

## 27. Bài thực hành tổng hợp

**Bối cảnh:** xây dựng một ứng dụng Spring Boot có trang profile server-rendered và một client SPA cùng origin sử dụng session cookie. CSRF protection được bật và backend có endpoint GET `/csrf`. Mục tiêu là tái hiện và khắc phục lỗi token thiếu **mà không tắt lớp bảo vệ**.

1. **Servlet baseline:** tạo `POST /profile` cho user đã xác thực, trả 204 khi cập nhật thành công; cấu hình CSRF với repository mặc định phù hợp.
2. Tạo một template POST **không có hidden token** hoặc không được template processor bổ sung. GET trang rồi POST; quan sát 403 và CSRF exception.
3. Thêm cách expose token bằng Thymeleaf đúng cơ chế; kiểm tra HTML cuối cùng và Form Data của POST, xác nhận có token và controller thành công.
4. Tạo GET `/csrf` Servlet. Kiểm tra JSON có `token`/`headerName` và `Cache-Control: no-store`; bảo đảm GET materialize deferred token.
5. Viết SPA gọi GET token rồi POST với header tên động. Thử POST trước khi bootstrap hoàn tất để tái hiện lỗi.
6. Đổi sang `CookieCsrfTokenRepository.withHttpOnlyFalse()` trong môi trường lab; quan sát cookie `XSRF-TOKEN` có thực sự được phát không.
7. Thử raw cookie với handler không phù hợp để thấy lỗi, sau đó dùng chiến lược handler kết hợp/endpoint JSON đã được review. Không in token raw vào log.
8. Thử login/logout và kiểm tra token cũ có còn hợp lệ không; cập nhật frontend lấy token mới sau thay đổi phiên.
9. Chạy MockMvc với `with(csrf())` và `useInvalidToken()` để xác minh filter; sau đó viết integration test GET token → POST cùng session để kiểm tra **flow thực**.
10. Chuyển bài sang Reactive/WebFlux: cấu hình `CsrfWebFilter`, GET `/csrf` trả `Mono<CsrfToken>` và WebTestClient test CSRF enabled/disabled ở request.
11. Đặt SPA/API ở hai origin test có kiểm soát; thử preflight với header CSRF tùy chỉnh, phân biệt lỗi CORS với lỗi CSRF.
12. Đặt reverse proxy/load balancer trước ứng dụng, kiểm tra cookie/session và việc không cache response token.
13. Lập bảng kết quả gồm method, URL, security chain, repository, token location, cookie, exception/status, nguyên nhân và cách sửa.

### Câu hỏi tự đánh giá

1. Vì sao GET HTML trả 200 nhưng token chưa chắc được tạo trong Spring Security hiện đại?
2. Deferred CSRF token khác token được sinh/lưu và token được render ra client như thế nào?
3. Một form server-rendered cần cung cấp token cho browser bằng cách nào?
4. Khi Thymeleaf tự thêm hidden CSRF input, có nên tự thêm một input giống hệt nữa không?
5. GET `/csrf` có vai trò gì đối với SPA; vì sao endpoint nên tránh cache công khai?
6. Tại sao `with(csrf())` PASS không chứng minh frontend thật đã gọi GET để lấy token?
7. `HttpSessionCsrfTokenRepository` và `CookieCsrfTokenRepository` khác nhau ở điểm nào?
8. Khi nào `CookieCsrfTokenRepository.withHttpOnlyFalse()` có thể được cân nhắc, và rủi ro là gì?
9. Raw token trong cookie khác masked token trong form đối với `XorCsrfTokenRequestAttributeHandler` như thế nào?
10. Vì sao hai hidden token ở hai response có thể khác nhau dù expected token của repository không đổi?
11. Sau login/logout, vì sao SPA cần tải token mới trước khi gửi POST tiếp?
12. Token có mặt trong header nhưng POST vẫn 403 có thể do những lỗi nào ngoài việc header sai tên?
13. CORS preflight 403 có chứng minh CSRF filter của POST đã chạy không?
14. Tại sao `permitAll()` không tắt CSRF protection?
15. Vì sao `Mono<CsrfToken>` trong WebFlux phải được tiêu thụ để bảo đảm lazy token được materialize?
16. Khi nhiều security chains dùng repository khác nhau, làm sao xác định GET token và POST cùng chain/chính sách?
17. Vì sao local một node ổn nhưng sau load balancing lỗi CSRF có thể xảy ra ngẫu nhiên?
18. Nên dựa vào tín hiệu nào để phân biệt 403 do CSRF, 403 do authorization và 403 do WAF?

## 28. Ghi nhớ

**CSRF token thiếu không luôn nghĩa là Spring Security không biết tạo token.** Với cơ chế deferred/lazy, token có thể **chưa cần được materialize** cho tới khi template, controller hoặc endpoint của SPA thật sự đọc nó. Một form không render hidden input hoặc SPA không gọi GET token sẽ không có giá trị để gửi lại ở POST. Khi token đã được gửi nhưng vẫn 403, hãy kiểm tra repository, session/cookie, header name, masking chống BREACH, request handler, login/logout rotation và security chain thực tế.

Trong **Servlet**, tập trung vào `CsrfFilter`, `CsrfTokenRepository`, `CsrfTokenRequestHandler` và việc expose token qua Thymeleaf hoặc GET `/csrf`. Trong **Reactive/WebFlux**, chú ý `CsrfWebFilter`, `ServerCsrfTokenRepository` và `Mono<CsrfToken>` phải được tiêu thụ đúng cách. Dùng MockMvc/WebTestClient để xác minh filter, rồi kiểm thử **GET token → POST cùng phiên** qua browser và proxy; phân biệt CSRF với CORS, CSP, authentication, authorization, HTTP firewall và cache. Mục tiêu của `SPRING_SECURITY_HTTP_PROTECTION` là khắc phục lỗi đúng tầng trong khi giữ nguyên các lớp bảo vệ HTTP và session.
