# CSRF là gì và vì sao trình duyệt có thể gửi yêu cầu ngoài ý muốn?

> **Chủ đề:** Spring Security – fundamentals → **CSRF** (Cross-Site Request Forgery, giả mạo yêu cầu liên trang). Bài học dành cho Java 17+, Spring Boot 3.x và Spring Security 6.x. Trọng tâm: giải thích cơ chế trình duyệt **tự gửi credential** trong request do bên ngoài kích hoạt, điều kiện khiến ứng dụng dễ bị CSRF, cách chống CSRF bằng token và các lớp phòng thủ khác, cấu hình Servlet/WebFlux và kiểm thử.

## 1. CSRF là gì?

**Cross-Site Request Forgery (CSRF)** là kiểu tấn công làm cho trình duyệt của người dùng đang có thông tin xác thực với website A **gửi một yêu cầu không mong muốn tới website A** từ một ngữ cảnh do kẻ tấn công kiểm soát, chẳng hạn website B, email hoặc nội dung nhúng. Nếu website A chỉ nhìn vào cookie/session hợp lệ mà không xác minh tính hợp lệ của request, server có thể thực hiện hành động do attacker chọn dưới danh tính của người dùng.

CSRF không đòi attacker phải **biết mật khẩu**, **đọc session cookie**, hay **đọc được response** của website đích. Điều kiện quyết định là browser có thể **tự gửi credential** kèm một request mà người dùng không chủ động cho phép.

**Ví dụ:** Alice đăng nhập `https://accounts.example`, sau đó mở `https://other.example`. Trang ngoài gửi một form POST để đổi email trong tài khoản Alice. Khi browser tự đính kèm cookie phiên hợp lệ (nếu chính sách cookie cho phép) và accounts.example không có CSRF defense, hệ thống có thể chấp nhận request như do Alice gửi.

Phân biệt:

- **Authentication:** Request thuộc user nào? Cookie/session xác định Alice.
- **Authorization:** Alice có quyền đổi email tài khoản mình không? Có thể là có.
- **CSRF protection:** Yêu cầu đổi email này có thực sự xuất phát từ một luồng đáng tin, với bằng chứng mà trang ngoài không thể giả mạo không? Đây là lớp kiểm tra bị thiếu trong ví dụ tấn công.

Một session được xác thực **không chứng minh ý định cụ thể của người dùng**.

## 2. Quy trình tấn công từng bước

Giả sử ứng dụng đích có endpoint `POST /account/change-email`, chỉ kiểm tra cookie phiên trước khi ghi dữ liệu.

1. Alice đăng nhập tại `https://accounts.example`; server phát session cookie như `JSESSIONID=opaque`. Browser lưu cookie và gắn lại khi request phù hợp.
2. Alice truy cập `https://other.example` do attacker điều khiển; trang này có form với `action` trỏ về `https://accounts.example/account/change-email`.
3. Trang attacker khiến browser gửi form POST chứa `email=attacker-controlled@example.net`.
4. **Nếu** SameSite/Domain/Path/Secure và chính sách browser cho phép, browser gắn cookie phiên của accounts.example vào request đến chính accounts.example. Attacker không cần đọc cookie.
5. Nếu server chỉ kiểm tra session và quyền user, không kiểm tra CSRF token hoặc nguồn request, email có thể bị đổi mà Alice không chủ động làm.
6. Dù Same-Origin Policy ngăn attacker đọc nội dung response từ accounts.example, hành động đổi email đã có thể hoàn tất.

Minh họa request mà browser có thể gửi trong điều kiện cookie phù hợp:

```http
POST /account/change-email HTTP/1.1
Host: accounts.example
Cookie: JSESSIONID=opaque-session
Content-Type: application/x-www-form-urlencoded

email=attacker-controlled@example.net
```

Minh họa HTML form được host ở site ngoài:

```html
<form action="https://accounts.example/account/change-email"
      method="post">
    <input type="hidden" name="email"
           value="attacker-controlled@example.net">
    <button type="submit">Continue</button>
</form>
```

Đây là ví dụ để **hiểu cơ chế**, không phải khẳng định mọi trình duyệt đều đính kèm session cookie vào cross-site POST. Cookie `SameSite=Lax` khai báo tường minh thường **không được gửi** trong cross-site form POST; `SameSite=Strict` còn hạn chế hơn. Nhưng nếu có `SameSite=None; Secure` hoặc các trường hợp browser/kiến trúc khác cho phép credentials, thiếu CSRF guard vẫn là vấn đề nghiêm trọng.

Sơ đồ quyết định:

```text
Trang ngoài (other.example)
       |
       | Tạo form POST tới accounts.example
       v
Trình duyệt của Alice
       |
       | Có thể tự gắn cookie của accounts.example
       v
Spring Security / server
       |
       +-- Chỉ kiểm tra session? --> Nguy cơ nhận request giả mạo
       |
       +-- Có CSRF token hợp lệ? --NO--> Từ chối
                                  |
                                 YES
                                  |
                                  v
                    Kiểm tra quyền và nghiệp vụ
                                  |
                                  v
                         Thực hiện action
```

## 3. Vì sao trình duyệt có thể gửi request ngoài ý muốn?

Browser được thiết kế để tải các tài nguyên, điều hướng và submit HTML form. Trang A có thể gây ra một số request đến trang B. **Same-Origin Policy (SOP) thường kiểm soát khả năng script đọc dữ liệu/response ở origin khác**, chứ không chặn tất cả loại request đi ra trước khi gửi.

Hãy tách ba bước:

1. Trang ngoài **kích hoạt request** (form, navigation hoặc request khác).
2. Browser **xem xét việc đính kèm credential** theo destination URL và chính sách cookie/HTTP authentication.
3. Server **quyết định có xử lý request** sau khi xác thực, phân quyền và kiểm tra CSRF.

Một trang ngoài không cần đọc response thành công; chỉ cần server thay đổi dữ liệu là đã có tác động. Cũng cần chú ý attacker có thể khiến victim click link hoặc mở form hợp lệ về kỹ thuật nhưng sai ý định nghiệp vụ.

### 3.1. Ambient credentials

**Ambient credentials** là thông tin xác thực browser có thể tự gắn với request khi có điều kiện thích hợp:

| Credential | Browser có thể tự đính kèm? | Ý nghĩa CSRF |
|---|---|---|
| Session cookie | Có, theo Domain/Path/SameSite/Secure/browser policy | Nguy cơ điển hình |
| HTTP Basic đã được browser cache | Có thể, theo HTTP protection space/client | Basic cũng có thể bị CSRF trong browser |
| Client certificate | Có thể, theo TLS/browser configuration | Cần xem xét ngữ cảnh browser |
| Bearer token do JavaScript chủ động gắn vào header | Không mặc nhiên theo cơ chế cookie/form | Nguy cơ CSRF truyền thống có thể thấp hơn; XSS/token theft vẫn cần phòng |
| JWT lưu trong cookie tự gửi | Có, theo cookie policy | Chữ ký JWT không ngăn CSRF |
| API key chỉ có trong server-to-server request header | Thông thường không bị browser tự gửi | CSRF truyền thống không giống mô hình session; vẫn cần authentication và kiểm tra chữ ký |

**JWT không phải cơ chế chống CSRF**: điều quan trọng là token được browser **tự động** gửi qua cookie hay được client đáng tin **chủ động** thêm vào header.

### 3.2. Secure và HttpOnly không chặn CSRF

`Secure` đảm bảo cookie chỉ được gửi qua HTTPS theo chính sách browser. Nó bảo vệ transport, **không chứng minh request đến từ giao diện đáng tin**.

`HttpOnly` hạn chế JavaScript đọc trực tiếp cookie. Browser vẫn có thể tự gửi cookie đó trong request phù hợp. Attacker **không cần đọc cookie** để dùng cơ chế CSRF, nên `HttpOnly` không phải lời giải CSRF.

`SameSite` là lớp bảo vệ khác, sẽ phân tích riêng; nó hữu ích nhưng có giới hạn về safe methods, subdomain và tương thích.

## 4. Điều kiện để CSRF thành công

CSRF không tự thành công chỉ vì có một form cross-site. Phải xét các điều kiện:

| Điều kiện | Ví dụ | Nếu thiếu thì sao? |
|---|---|---|
| Target có action thay đổi trạng thái | Đổi email, thêm địa chỉ, chuyển tiền, cấp quyền | Không có side effect có ích cho attacker |
| Nạn nhân có authentication với target | Session cookie hợp lệ | Server không có phiên của nạn nhân |
| Browser gửi được credential trong request bị kích hoạt | Cookie phù hợp SameSite và scope | Yêu cầu có thể là anonymous hoặc bị chặn |
| Attacker có thể hình thành request phù hợp endpoint | Method, path, form fields | Server không chấp nhận request |
| Không có CSRF defense hợp lệ | Không cần token; Origin không kiểm tra | Server có thể tin nhầm request |

Không phải API nào cũng giống nhau. Một API nghiêm ngặt chỉ nhận `Content-Type: application/json` với custom header và CORS allowlist đúng có thể khó bị tấn công bằng HTML form. Tuy nhiên không kết luận “API JSON chắc chắn miễn nhiễm”: phải kiểm tra content-type fallback, CORS cấu hình sai, request đơn giản, subdomain không tin cậy, XSS và mọi cơ chế tự gửi credentials.

CSRF có thể khiến user **đổi mật khẩu, cập nhật thông tin liên hệ, tạo giao dịch, đăng ký subscription, cấp quyền, liên kết tài khoản, đăng nhập vào tài khoản của attacker (login CSRF) hoặc bị ép logout**. Tác động bị giới hạn bởi những chức năng target cho phép và quyền mà nạn nhân có.

## 5. CSRF, CORS và Same-Origin Policy khác nhau

| Cơ chế | Bảo vệ điều gì? | Điều không đảm bảo |
|---|---|---|
| **SOP** | Hạn chế script origin A đọc/truy cập tài nguyên origin B | Không cấm mọi request cross-origin được gửi |
| **CORS** | Kiểm soát JavaScript cross-origin access và preflight/response sharing | Không chặn mọi HTML form submission hoặc thay thế CSRF token |
| **CSRF token** | Kiểm tra client có bằng chứng request hợp lệ thay vì chỉ tự gửi credential | Không thay thế xác thực, phân quyền hay chống XSS |
| **SameSite cookie** | Giới hạn cookie trong ngữ cảnh cross-site | Không giải quyết mọi same-site subdomain và GET thay đổi trạng thái |
| **CSP/đối phó XSS** | Giảm khả năng script độc hại chạy trong origin thật | Không thay thế CSRF defense của request từ origin khác |

### 5.1. Vì sao “API không bật CORS” vẫn có thể bị CSRF?

Một HTML form truyền thống có thể gửi cross-origin request với content type như `application/x-www-form-urlencoded`, `multipart/form-data` hoặc `text/plain` mà không cần JavaScript đọc response qua CORS. Nếu backend nhận request, kiểm tra session rồi thực hiện side effect, request vẫn có thể gây hại.

Các request cross-origin có custom header hoặc content type không được CORS safelist thường cần preflight, và chính sách CORS đúng có thể làm chúng thất bại. Nhưng **ngăn đọc response** không đồng nghĩa **ngăn mọi dạng gửi request**.

### 5.2. `fetch` không đại diện cho HTML form

`fetch` mặc định dùng `credentials: "same-origin"`, nên cross-origin fetch thường không kèm cookie trừ khi code chọn `credentials: "include"`. HTML form/navigations có quy tắc khác. Vì thế test một request fetch không gửi cookie **không chứng minh** một form cross-site cũng không thể gửi cookie.

### 5.3. CORS credentials

Khi frontend và API khác origin mà cần cookie, browser `fetch` có thể dùng `credentials: "include"`; server phải cấu hình CORS cho **origin cụ thể được tin cậy** và credentials. Response credentialed CORS không thể sử dụng `Access-Control-Allow-Origin: *` theo cách bình thường. Mở origin allowlist quá rộng (đặc biệt subdomain chưa quản lý) có thể vô hiệu hóa những lớp bảo vệ dựa trên custom header/preflight.

## 6. SameSite: lợi ích và giới hạn

`SameSite` phân biệt request theo **site** (thường dựa trên scheme và registrable domain), không hoàn toàn giống origin (scheme, host, port).

Ví dụ `https://app.example.com` và `https://api.example.com` **khác origin** nhưng thường **cùng site**. Nếu một subdomain cùng site bị chiếm quyền, SameSite có thể **không** cản cookie trong request đến subdomain khác thuộc cùng site.

| Thuộc tính | Cross-site top-level GET | Cross-site form POST thông thường | Ghi chú |
|---|---|---|---|
| `SameSite=Strict` | Không đính kèm cookie | Không đính kèm cookie | Bảo vệ mạnh hơn, có thể ảnh hưởng UX khi click link từ bên ngoài |
| `SameSite=Lax` khai báo rõ | Thường gửi cookie với navigation GET | Thường không gửi | GET có side effect vẫn nguy hiểm |
| `SameSite=None; Secure` | Có thể gửi | Có thể gửi | Còn tùy third-party cookie blocking/browser policy |

**Không phụ thuộc vào mặc định browser:** khi không khai báo SameSite, một số browser áp dụng cơ chế kiểu Lax và có thể cho phép một số top-level cross-site POST trong khoảng ngắn sau khi cookie mới được tạo. Điều này **khác** `SameSite=Lax` khai báo tường minh. Hãy đặt thuộc tính rõ và test trên browser thực tế.

SameSite **không phải phép kiểm tra đầy đủ về ý định request**, nhất là ứng dụng có subdomain không đáng tin hoặc state-changing GET. Dùng nó làm defense in depth cùng CSRF token/Origin/Fetch Metadata theo threat model.

## 7. Vì sao phương thức HTTP safe phải thực sự read-only?

Spring Security mặc định **không yêu cầu CSRF token** cho phương thức HTTP safe như `GET`, `HEAD`, `OPTIONS`, `TRACE`. Nó thường yêu cầu token cho `POST`, `PUT`, `PATCH`, `DELETE`. Điều này dựa trên nguyên tắc **safe methods không thay đổi trạng thái nghiệp vụ theo yêu cầu của client**.

**Thiết kế nguy hiểm:**

```http
GET /account/delete?id=42 HTTP/1.1
Host: accounts.example
Cookie: JSESSIONID=opaque
```

Trình duyệt có thể đi tới GET từ một link ngoài; SameSite Lax vẫn thường cho phép cookie trong top-level navigation GET. Vì vậy không nên thiết kế xóa tài khoản, cập nhật email, thanh toán hay cấp quyền bằng GET.

**Thiết kế phù hợp hơn:** dùng `POST`/`PUT`/`PATCH`/`DELETE` cho action làm thay đổi trạng thái, kiểm tra CSRF token nếu dùng browser ambient credentials, sau đó xác minh authentication, authorization và quyền trên object. **Đổi HTTP method mà không bật CSRF guard chưa phải giải pháp hoàn chỉnh**.

Một số GET có thể tạo log hoặc cache nội bộ phục vụ hệ thống; điều quan trọng là không để GET thực thi hành động nghiệp vụ mà kẻ tấn công có thể chủ động lợi dụng.

## 8. CSRF token là gì và hoạt động ra sao?

**Synchronizer Token Pattern** là một mô hình phổ biến trong ứng dụng session-based:

1. Server tạo một CSRF token đủ khó đoán, liên kết với session hoặc một nguồn kỳ vọng đáng tin.
2. Trang/form hợp lệ nhận token qua HTML, request attribute hoặc endpoint/bootstrap tin cậy.
3. Khi gửi request thay đổi trạng thái, client gửi token **tường minh** qua hidden form field hoặc custom header.
4. Server so sánh token mà client trình với giá trị kỳ vọng trước khi thực hiện action.
5. Request thiếu/sai token bị từ chối, dù session cookie vẫn hợp lệ.

Ví dụ một request chứa token:

```http
POST /account/change-email HTTP/1.1
Host: accounts.example
Cookie: JSESSIONID=opaque-session
Content-Type: application/x-www-form-urlencoded

email=alice-new@example.com&_csrf=token-created-for-this-session
```

Một trang attacker có thể tạo form POST, nhưng theo SOP nó không tự đọc được token của session Alice trong trang thật của accounts.example. Khi token đủ khó đoán và server xác minh đúng, attacker thiếu bằng chứng cần thiết để forge request.

**Không chỉ kiểm tra cookie token:** nếu browser tự gửi `XSRF-TOKEN` cookie và server coi sự xuất hiện của cookie là đủ, attacker cũng có thể lợi dụng việc cookie tự gửi. Cần client **chủ động trình token** qua header/field theo policy, và backend kiểm tra với nguồn tin cậy.

### 8.1. CSRF token khác session cookie

- **Session cookie:** credential xác thực do browser tự gửi khi phù hợp.
- **CSRF token:** giá trị mà trang/client hợp lệ phải biết và gửi lại tường minh cho unsafe request.
- **Authorization:** quyết định authenticated user có quyền làm hành động hay không.

Có CSRF token đúng nhưng không có session/permission vẫn không được phép thực hiện nghiệp vụ protected.

### 8.2. Synchronizer token và double-submit

| Pattern | Ý nghĩa | Rủi ro cần xét |
|---|---|---|
| Synchronizer token | Token kỳ vọng lưu trong server session; client gửi field/header | Token lifecycle/session timeout |
| Naive double-submit | So sánh token trong cookie và header/field | Có thể bị cookie injection, đặc biệt qua sibling subdomain |
| Signed double-submit | MAC ràng buộc token với session/giá trị ngẫu nhiên | Cần key management và validation chuẩn |
| Origin/Referer/Fetch Metadata | Dựa vào browser headers để nhận diện cross-site | Cần fallback hợp lý, trusted origin và reverse proxy correctness |

OWASP khuyến nghị **synchronizer token** với trạng thái session và **signed double-submit cookie** trong nhiều thiết kế stateless. Không tự tạo bộ phát/so sánh token đơn giản từ `Math.random()`; dùng thành phần bảo mật đã được kiểm thử.

### 8.3. Không đưa token vào URL

CSRF token có thể lộ qua browser history, proxy/access log, Referer, analytics hoặc bản chụp hỗ trợ nếu nằm trong query string. Dùng hidden form field/header, HTTPS và không log nguyên token.

## 9. Spring Security Servlet: `CsrfFilter` bật mặc định

Trong ứng dụng Spring Security Servlet/MVC, CSRF protection được bật mặc định cho unsafe HTTP methods. Các thành phần:

- `CsrfFilter`: xác định request cần CSRF guard, lấy token client trình và xác minh trước khi cho vào business flow.
- `HttpSessionCsrfTokenRepository`: repository mặc định lưu token kỳ vọng trong `HttpSession`.
- `CsrfTokenRequestHandler`: expose/resolve token, tên parameter/header.
- `XorCsrfTokenRequestAttributeHandler`: handler thường là mặc định trong Spring Security 6.x để hỗ trợ giảm rủi ro BREACH khi đưa token vào response.
- `CookieCsrfTokenRepository`: lựa chọn khi SPA cần cơ chế token qua cookie; yêu cầu integration đúng cho deferred token/masking.
- `AccessDeniedHandler`: cách xử lý request thiếu hoặc sai token, thường trả HTTP **403 Forbidden**.

Cấu hình Servlet đơn giản:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
```

Đây là class Spring configuration trong ứng dụng Java 17+/Spring Boot 3.x, **không phải source độc lập cho `javac`** vì cần dependency Spring. `.csrf(Customizer.withDefaults())` chỉ khai báo tường minh **hành vi mặc định**. Không cần tắt CSRF để bật form login.

**`permitAll()` không tắt `CsrfFilter`.** Ví dụ `POST /public/register` được permitAll về authorization nhưng vẫn có thể phải trình CSRF token vì là unsafe method.

### 9.1. Ma trận mặc định theo HTTP method

| HTTP method | CSRF token thường bắt buộc? | Lưu ý |
|---|---|---|
| `GET` | Không | Phải read-only |
| `HEAD` | Không | Không gây tác dụng phụ nghiệp vụ |
| `OPTIONS` | Không | Không dùng để đổi dữ liệu |
| `TRACE` | Không | Không dùng để thay đổi dữ liệu; cân nhắc hạn chế TRACE riêng |
| `POST` | Có | Kiểm tra token |
| `PUT` | Có | Kiểm tra token |
| `PATCH` | Có | Kiểm tra token |
| `DELETE` | Có | Kiểm tra token |

Đây là **mặc định**. Nếu có custom matcher/chain, hãy test theo cấu hình thực tế, không suy luận từ bảng nếu đã sửa rule.

### 9.2. Form HTML và AJAX

Server-rendered form dùng CSRF token trong hidden field. Ví dụ HTML sau mô tả **header/body sau khi server đã render token hợp lệ**, không phải một form tĩnh chứa token thật:

```html
<form action="/account/change-email" method="post">
  <input name="email" type="email" required>
  <input name="_csrf" type="hidden"
         value="the-session-specific-token-rendered-by-server">
  <button type="submit">Save</button>
</form>
```

Trong Thymeleaf với Spring Security integration, `th:action` và `RequestDataValueProcessor` có thể tự tích hợp hidden CSRF field. Nếu tự xây form template, lấy token từ request attribute `_csrf` theo tài liệu của framework; tránh chèn trùng field khi view layer đã tự tạo.

Trong SPA/fetch, dùng request header được server chỉ định, ví dụ:

```javascript
// csrfToken được lấy từ endpoint/bootstrap đáng tin của app.
await fetch("/api/profile", {
  method: "PATCH",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ displayName: "Alice" })
});
```

Không dùng một chuỗi token hardcoded cho mọi user. Với API khác origin, chỉ gửi token tới trusted destination, xem lại CORS/credentials và cookie policy.

### 9.3. SPA và `CookieCsrfTokenRepository`

Spring Security Servlet có `CookieCsrfTokenRepository`, thường sử dụng cookie `XSRF-TOKEN`, header `X-XSRF-TOKEN` hoặc form parameter `_csrf` theo repository/config. Nếu JavaScript thật sự cần đọc token cookie, có thể dùng:

```java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Trích đoạn bên trong cấu hình HttpSecurity Servlet:
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

**Chỉ cookie CSRF token cần JS đọc** trong thiết kế này; session cookie vẫn nên `HttpOnly=true`. Ngoài repository, ứng dụng Spring Security 6.x có **deferred tokens, BREACH masking và rotation/clearing token sau authentication/logout**; SPA cần xử lý chính xác theo tài liệu phiên bản, không copy một dòng là đủ.

## 10. Demo Spring Boot MVC và MockMvc: request có hoặc thiếu CSRF token

Ví dụ dùng Java 17, Spring Boot **3.5.7** và Spring Security 6.x (dependency do Boot quản lý). Endpoint POST **không thực thi giao dịch thật**: chỉ trả một chuỗi để minh họa filter. Mật khẩu trong source chỉ dùng local, không dùng production.

Cấu trúc project:

```text
csrf-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/csrf/
    │   ├── CsrfDemoApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/com/example/csrf/
        └── CsrfDemoTests.java
```

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
    <artifactId>csrf-demo</artifactId>
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

Tệp `CsrfDemoApplication.java`:

```java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
```

Tệp `SecurityConfig.java`:

```java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form.permitAll())
            .csrf(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build()
        );
    }
}
```

Tệp `DemoController.java`:

```java
package com.example.csrf;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public/ping")
    public String ping() {
        return "pong";
    }

    @GetMapping("/api/status")
    public String status() {
        return "read-only";
    }

    @PostMapping("/api/submit")
    public String submit() {
        return "accepted";
    }
}
```

Test đầy đủ dùng `MockMvc` và `spring-security-test`. Tệp `CsrfDemoTests.java`:

```java
package com.example.csrf;

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
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfDemoTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getWithUserDoesNotNeedCsrf() throws Exception {
        mvc.perform(get("/api/status").with(user("alice")))
            .andExpect(status().isOk())
            .andExpect(content().string("read-only"));
    }

    @Test
    void postWithUserButNoCsrfIsDenied() throws Exception {
        mvc.perform(post("/api/submit").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfTokenIsDenied() throws Exception {
        mvc.perform(post("/api/submit")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfTokenAndAuthenticationSucceed() throws Exception {
        mvc.perform(post("/api/submit")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("accepted"));
    }
}
```

Lệnh chạy (JDK 17+ và Maven):

```bash
mvn test
mvn spring-boot:run
```

Phân tích test:

- `.with(user("alice"))` tạo authentication mock; **không kiểm tra form-login password**.
- `.with(csrf())` thêm token hợp lệ trong `MockMvc` để kiểm tra CSRF filter; `.useInvalidToken()` mô phỏng token sai.
- GET authenticated không cần token, POST thiếu/sai token bị **403**, POST authenticated có token hợp lệ được vào controller.
- Token hợp lệ **không đủ nếu user chưa xác thực/thiếu quyền**. Nếu muốn kiểm tra anonymous, test riêng theo form login entry point (có thể redirect) thay vì mặc định luôn là 401.
- Demo test tập trung security chain, **không mô phỏng trình duyệt SameSite/CORS**. Browser-level tests phải được thêm khi triển khai thật.

## 11. Java 17 độc lập: mô hình hóa hai kiểu server

Chương trình dưới đây dùng Java thuần để so sánh **server yếu chỉ nhìn credential** với **server đòi CSRF token cho action thay đổi trạng thái**. Nó chỉ là mô hình học tập, không phát sinh cookie/token thật và không thay thế thư viện bảo mật.

Tệp `CsrfDecisionDemo.java`:

```java
public class CsrfDecisionDemo {

    record Request(boolean credentialSent,
                   boolean stateChanging,
                   boolean validCsrfToken) {}

    static boolean vulnerableServerAccepts(Request request) {
        return request.credentialSent();
    }

    static boolean protectedServerAccepts(Request request) {
        return request.credentialSent()
            && (!request.stateChanging() || request.validCsrfToken());
    }

    static void show(String name, Request request) {
        System.out.println(name
            + " vulnerable=" + vulnerableServerAccepts(request)
            + ", protected=" + protectedServerAccepts(request));
    }

    public static void main(String[] args) {
        show("GET authenticated",
            new Request(true, false, false));
        show("POST with browser cookie, no token",
            new Request(true, true, false));
        show("POST with cookie and valid token",
            new Request(true, true, true));
        show("POST with token, no credential",
            new Request(false, true, true));
    }
}
```

Biên dịch và chạy:

```bash
javac CsrfDecisionDemo.java
java CsrfDecisionDemo
```

Stdout chính xác theo chương trình:

```text
GET authenticated vulnerable=true, protected=true
POST with browser cookie, no token vulnerable=true, protected=false
POST with cookie and valid token vulnerable=true, protected=true
POST with token, no credential vulnerable=false, protected=false
```

Chương trình **không nói browser luôn gửi cookie cho mọi cross-site POST**. Đầu vào `credentialSent=true` chỉ mô tả một tình huống cookie/credential đã được gửi. Trong thực tế còn cần xét SameSite, browser policy, CSRF token generation/validation và business authorization. Đây là minh họa quyết định chứ không phải mã production.

## 12. Spring WebFlux: bảo vệ CSRF trong reactive pipeline

Với Spring Security WebFlux, `ServerHttpSecurity` và `SecurityWebFilterChain` thay cho builder/filter chain Servlet. CSRF support **được bật mặc định**; `WebSessionServerCsrfTokenRepository` dùng WebSession lưu token theo tài liệu Spring Security. Những thành phần reactive không nên bị ép bằng `block()` hoặc `subscribe()` thủ công.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **cấu hình cho ứng dụng WebFlux riêng**, không phải Java class tự chạy bằng `javac`. HTTP Basic ở browser có thể tự gửi credential đã cache, nên vẫn phải đánh giá CSRF. Với SPA, có thể dùng `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` nếu JavaScript cần đọc cookie **CSRF token**; không tắt HttpOnly trên session cookie chỉ vì nhu cầu này.

Trích đoạn test với `WebTestClient` đã bind đúng vào Spring Security và endpoint thật:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockUser;

webTestClient
    .mutateWith(mockUser("alice"))
    .mutateWith(csrf())
    .post()
    .uri("/api/submit")
    .exchange()
    .expectStatus().is2xxSuccessful();
```

Một test đầy đủ còn cần **ca POST thiếu token** và kết quả từ chối; status thành công phụ thuộc handler/fixture thực. Không suy ra WebFlux xử lý giống hệt Servlet ở mọi chi tiết token lifecycle.

## 13. Các lớp phòng thủ bổ sung: Origin, Referer và Fetch Metadata

**Origin/Referer:** backend có thể so sánh chính xác `Origin` của unsafe request với **trusted origin**. Nếu Origin vắng mặt, có thể xét Referer theo fallback được định nghĩa. Không dùng so khớp chuỗi lỏng như `contains("accounts.example")` vì `accounts.example.attacker.net` là origin khác. Xử lý proxy/forwarded host/scheme đúng và quyết định fail-closed phù hợp khi header thiếu hoặc `Origin: null`.

**Fetch Metadata:** browser hiện đại có thể gửi `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest`. Server có thể từ chối unsafe request `cross-site` theo policy có ngoại lệ cho flow hợp pháp. Đây là tín hiệu rất hữu ích nhưng cần hỗ trợ client/browser không cung cấp headers và test các navigation/SSO flows.

**SameSite:** chọn `Lax` hoặc `Strict` có chủ đích nếu phù hợp; `SameSite=None` phải kèm `Secure`, nhưng có thể bị browser chặn third-party cookie. SameSite cùng origin là hai khái niệm khác nhau; kiểm soát các subdomain chung registrable domain.

**CSRF token:** trong web app stateful, đây là lớp mặc định nên giữ. Các lớp bổ sung không thay thế việc kiểm soát quyền theo owner/tenant và không xóa nguy cơ XSS.

## 14. Login CSRF, logout CSRF và token lifecycle

- **Login CSRF:** attacker khiến nạn nhân đăng nhập vào tài khoản do attacker chọn, rồi nạn nhân có thể vô tình đưa dữ liệu vào tài khoản đó. Spring Security Servlet hỗ trợ CSRF cho login POST mặc định.
- **Logout CSRF:** attacker ép user đăng xuất, gây gián đoạn hoặc lừa workflow. Khi CSRF protection bật, Spring Security Servlet mặc định yêu cầu POST logout (thay vì GET logout không bảo vệ).
- **Session timeout:** token kỳ vọng lưu trong session có thể hết hạn. Client gửi token cũ sẽ bị từ chối; cần UX lấy token mới hoặc yêu cầu đăng nhập lại.
- **Token rotation:** login/logout/session đổi có thể dẫn đến CSRF token mới; SPA cần refresh token theo quy trình đúng.
- **Nhiều tab:** nếu token hoặc session thay đổi, test tình huống tab cũ còn token không hợp lệ.
- **Không log token**; không đưa token vào URL hoặc analytics. Token là cơ chế request authenticity, không phải thứ để công bố tự do.

## 15. Khi nào cân nhắc ngoại lệ CSRF?

**Không tắt CSRF toàn cục chỉ để POST hết lỗi 403.** Nếu một endpoint **thực sự** không phụ thuộc credential browser tự gửi (ví dụ webhook có chữ ký request được xác thực, API service-to-service dùng bearer header riêng), có thể đánh giá một ngoại lệ có phạm vi hẹp:

```java
// Trích đoạn trong cấu hình Servlet; chỉ dùng sau threat-model review.
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider")
);
```

Webhook đó vẫn cần **verify signature/timestamp/replay protection** hoặc cơ chế authentication riêng; miễn CSRF không nghĩa là public request được thực thi vô điều kiện.

Nếu API dùng JWT **trong cookie**, về mặt CSRF nó giống cookie authentication; chữ ký JWT không tạo bằng chứng về ý định request. Nếu API chỉ dùng bearer header do client chủ động thêm và không có ambient credentials, CSRF truyền thống có thể không áp dụng theo cách đó, nhưng cần bảo vệ XSS, token theft, CORS, phân quyền và lưu token.

Đừng suy luận “`SessionCreationPolicy.STATELESS` tức là không có CSRF”, bởi browser HTTP Basic có thể cache credential và một ứng dụng stateless vẫn có thể nhận cookie/token do browser tự gửi.

## 16. Ma trận test và checklist

| Ca kiểm thử | Kỳ vọng theo policy phổ biến |
|---|---|
| Authenticated GET read-only không có CSRF token | Được qua CSRF filter, vẫn chịu authorization |
| Authenticated POST thiếu CSRF token | 403, không chạy business action |
| Authenticated POST có token sai/khác phiên | 403, không ghi dữ liệu |
| Authenticated POST có token đúng, đủ quyền | Được đi tiếp; status tùy handler |
| Anonymous POST có token hợp lệ | Vẫn không được gọi endpoint yêu cầu login |
| User có token hợp lệ nhưng thiếu role | Bị authorization từ chối |
| POST đổi email sau session timeout | Token/session cũ không hợp lệ; cần xử lý UX |
| GET vô tình thay đổi trạng thái | Phát hiện lỗi thiết kế, sửa method |
| Cross-site form POST và SameSite=Lax | Cookie thường không gửi, vẫn phải kiểm tra threat model |
| Cookie SameSite=None; Secure trong browser cho phép | Có thể gửi cross-site; CSRF token cần có |
| Subdomain cùng site bị chiếm | SameSite một mình có thể không ngăn |
| JSON API dùng custom header và CORS sai | Kiểm tra preflight/origin/credential policy |
| Logout hoặc login POST thiếu token | Cần được bảo vệ theo cấu hình |
| XSS chạy trong origin thật | CSRF token có thể bị vượt qua; phải chống XSS riêng |

**Checklist production:**

1. Xác định đúng client và cơ chế authentication, đặc biệt credential nào browser tự đính kèm.
2. Dùng unsafe HTTP methods cho thay đổi trạng thái, không dùng GET làm action xóa/chuyển tiền/cấp quyền.
3. Giữ CSRF protection của Spring Security cho browser cookie/session app; không tắt theo quán tính.
4. Gửi CSRF token qua hidden field/header, backend xác minh đúng token kỳ vọng và session/lifecycle.
5. Cookie session dùng `Secure`/`HttpOnly`/`SameSite` có chủ đích; kiểm thử browser thật.
6. CORS allowlist và Origin/Referer/Fetch Metadata checks đúng policy; không tin wildcard/subdomain lạ.
7. Bảo vệ login/logout, xử lý rotation, session timeout và multi-tab.
8. Không log token, session ID, mật khẩu; không đặt CSRF token trong query string.
9. Kiểm tra authorization, tenant/owner/state ngay cả khi token hợp lệ.
10. Có test âm tính thiếu/sai token, sai quyền, sai session; xác minh **không có side effect** khi request bị từ chối.

## 17. Sai lầm thường gặp

1. “Attacker không biết cookie thì không thể CSRF.” — Sai: browser tự đính kèm credential.
2. “CORS tắt thì mọi cross-site request bị chặn.” — Sai: form submission có thể vẫn tới server.
3. “`HttpOnly` ngăn CSRF.” — Sai: nó ngăn JavaScript đọc cookie, không ngăn browser gửi.
4. “HTTPS ngăn CSRF.” — Sai: TLS bảo vệ đường truyền, không xác minh nguồn request.
5. “`SameSite=Lax` bảo vệ mọi action.” — Sai: top-level GET vẫn có cookie; subdomain cùng site không bị chặn.
6. “CSRF chỉ xuất hiện khi dùng session.” — Sai: Basic cached credentials và JWT cookie có thể là ambient credentials.
7. “Bật `permitAll` cũng miễn CSRF.” — Sai: authorization và CSRF filter là hai lớp.
8. “Token CSRF đúng là đủ quyền.” — Sai: cần authentication và object-level authorization.
9. “Có `XSRF-TOKEN` cookie nghĩa là an toàn.” — Sai: phải kiểm tra token client trình tường minh.
10. “Một website dùng JSON chắc chắn không bị CSRF.” — Sai: phụ thuộc CORS/preflight, content-type, credential và mọi đường vào.
11. “`GET` đổi trạng thái vẫn được vì browser chỉ gọi GET.” — Sai: safe methods cần read-only.
12. “401 và 403 đều là do sai role.” — Sai: CSRF thường gây 403; login entry point có thể 401/redirect.
13. “Copy `CookieCsrfTokenRepository.withHttpOnlyFalse()` là xong SPA.” — Chưa chắc; cần xử lý deferred token, BREACH và lifecycle.
14. “Spring Security `STATELESS` thì CSRF không liên quan.” — Sai nếu browser tự gửi credential.
15. “Tắt CSRF giúp test pass, vậy production cũng nên tắt.” — Không an toàn nếu chưa đánh giá threat model.

## 18. Tài liệu tham khảo

- [OWASP – CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- [Spring Security 6.5 – Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html).
- [Spring Security – Reactive/WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html).
- [Spring Security – CSRF Threat Model](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html).
- [MDN – Same-Origin Policy](https://developer.mozilla.org/en-US/docs/Web/Security/Same-origin_policy).
- [MDN – Set-Cookie / SameSite](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).

**Ghi nhớ:** CSRF xảy ra vì browser có thể **gửi request từ ngữ cảnh không tin cậy và tự gắn credential của website đích**. Server nhìn thấy một user đã xác thực nhưng **không có bằng chứng request thuộc luồng hợp lệ**. Giữ CSRF token protection cho ứng dụng dựa trên session/cookie, dùng SameSite/Origin/Fetch Metadata như các lớp bổ sung, và đừng quên authorization trên dữ liệu thật.