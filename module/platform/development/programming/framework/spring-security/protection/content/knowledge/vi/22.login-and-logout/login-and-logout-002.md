# Logout CSRF và lựa chọn phương thức thay đổi trạng thái

## Mục tiêu bài học

**Đăng xuất (logout)** là hành động thay đổi trạng thái xác thực: phiên đang được phép truy cập tài nguyên trở thành phiên không còn được chấp nhận, hoặc một số thông tin đăng nhập liên quan bị thu hồi. Vì vậy, một liên kết GET có khả năng đăng xuất ngay có thể tạo ra **Logout Cross-Site Request Forgery (Logout CSRF)**: một website khác, tác nhân xem trước liên kết hoặc luồng điều hướng không mong muốn khiến browser thực hiện đăng xuất mà người dùng không chủ ý.

Bài thuộc chương **Đăng nhập và đăng xuất** của module **SPRING_SECURITY_HTTP_PROTECTION**. Mục tiêu xuyên suốt là áp dụng các lớp phòng vệ HTTP và trình duyệt bằng Spring Security — **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session** — với ví dụ trên **Servlet/Spring MVC** và **Reactive/Spring WebFlux**.

Sau bài học, bạn có thể:

1. Giải thích **Logout CSRF**, tác động và sự khác biệt với **Login CSRF**, CSRF nghiệp vụ, session fixation và session hijacking.
2. Chọn phương thức HTTP đúng: **GET để xem trang xác nhận/trạng thái, POST để thực hiện logout**; không nhầm method safe với idempotent.
3. Phân tích vì sao **SameSite, SOP, CORS, Content-Type và preflight** không thay thế CSRF token cho logout dựa trên cookie/session.
4. Mô tả hành vi mặc định của **Spring Security Servlet** với GET /logout và POST /logout khi CSRF bật, cùng rủi ro khi tắt hoặc tùy chỉnh sai matcher.
5. Sử dụng **SecurityFilterChain/HttpSecurity**, form HTML/Thymeleaf và cấu hình SPA logout đúng CSRF.
6. Triển khai logout **Reactive/WebFlux** qua ServerHttpSecurity, phân biệt xóa SecurityContext với **vô hiệu hóa WebSession**.
7. Làm rõ phạm vi logout: **browser cookie, server session, remember-me, access/refresh token, IdP SSO, nhiều tab và nhiều thiết bị**.
8. Kiểm thử âm tính với **MockMvc, WebTestClient, DevTools, curl** và chẩn đoán lỗi cấu hình production.

## 1. Logout CSRF: ai có thể khiến phiên của người khác kết thúc?

Giả sử người dùng đang đăng nhập tại **https://account.example.com**. Session cookie được browser lưu và tự gửi trong những ngữ cảnh phù hợp. Một ứng dụng thiết kế endpoint như sau:

~~~http
GET /logout HTTP/1.1
Host: account.example.com
Cookie: __Host-APPSESSION=opaque-id
~~~

Nếu **GET /logout thực sự vô hiệu hóa session**, một trang ngoài có thể đưa người dùng đến URL đó, hoặc chính một cơ chế truy cập liên kết có thể kích hoạt URL mà không phải thao tác đăng xuất có chủ đích.

Ví dụ **liên kết ngoài**:

~~~html
<a href="https://account.example.com/logout">
  Xem thông báo
</a>
~~~

Ở một số ngữ cảnh, user có thể bị chuyển tới endpoint logout thay vì trang thông báo. Khi **SameSite=Lax** và đây là điều hướng top-level GET cross-site, browser có thể gửi cookie session đủ điều kiện. Server nhìn thấy request hợp lệ về mặt cookie nhưng không có bằng chứng user đã chủ ý đăng xuất.

### 1.1. Mô hình tấn công

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser của người dùng
    participant E as Website bên ngoài
    participant S as Ứng dụng Spring
    U->>S: Đăng nhập hợp lệ
    S-->>B: Set-Cookie: session=opaque; Secure; HttpOnly; SameSite=Lax
    U->>E: Mở trang ngoài
    E->>B: Kích hoạt điều hướng tới GET /logout
    B->>S: GET /logout + Cookie nếu browser cho phép
    alt Endpoint GET thực hiện logout sai thiết kế
        S->>S: Invalidate session
        S-->>B: Redirect tới login
    else GET chỉ hiển thị xác nhận
        S-->>B: Trang xác nhận, không đổi session
    end
~~~

Mục tiêu cơ bản của logout CSRF **không nhất thiết là chiếm quyền phiên**. Nó thường nhằm **ép đăng xuất hoặc gây gián đoạn**, có thể kéo theo mất công việc chưa lưu, gián đoạn một giao dịch, nhầm lẫn tài khoản hoặc tạo cơ hội cho các kịch bản social engineering khác. Mức nghiêm trọng phụ thuộc tính năng và tác động thực tế.

Logout CSRF không tự làm lộ mật khẩu, token hoặc biến user thành tài khoản attacker. Nếu có những hành vi đó, cần đánh giá lỗ hổng khác phối hợp.

### 1.2. Các nguồn request không nên được coi là hành động logout hợp lệ

| Nguồn | Vì sao GET có thể bị kích hoạt? | Rủi ro khi GET có side effect |
| --- | --- | --- |
| **Người dùng bấm liên kết từ site ngoài** | Điều hướng bình thường trên browser | Browser có thể mang session cookie, gây logout ngoài ý định. |
| **Trang nội bộ hiển thị link trong UI** | Link là hành động đọc/điều hướng theo kỳ vọng HTTP | Một cú click nhầm hoặc tác nhân tự động có thể vô hiệu hóa phiên. |
| **Link preview, bot hoặc crawler** | Có thể truy cập URL để xem nội dung, dù không phải mọi tác nhân đều mang cookie | Không nên để GET làm thay đổi trạng thái, đặc biệt khi có cookie jar. |
| **Prefetch/prerender hoặc tính năng tối ưu điều hướng** | Browser/ứng dụng có thể chuẩn bị đường dẫn trước | Chỉ vì URL được tải không có nghĩa user đồng ý đăng xuất. |
| **Ảnh/iframe/tài nguyên nhúng** | Browser có thể tạo một số request cross-origin theo chính sách | Cookie có gửi hay không tùy SameSite và loại request; vẫn không nên để GET có side effect. |
| **HTTP client ngoài browser** | Có thể gọi trực tiếp endpoint | CORS không bảo vệ endpoint khỏi client này; cần auth/rate limit theo mục tiêu. |

Không khẳng định **mọi** loại prefetch/link preview đều gửi cookie session hoặc chắc chắn tạo logout; chính sách browser, URL và môi trường khác nhau. Nguyên tắc thiết kế vẫn là **GET không được thực hiện hành động vô hiệu hóa phiên**.

### 1.3. Logout CSRF khác các loại CSRF/chiếm phiên khác

| Khái niệm | Điều bị tác động | Phòng vệ cần quan tâm |
| --- | --- | --- |
| **Logout CSRF** | Nạn nhân bị kết thúc phiên ngoài ý định. | POST logout có CSRF token; giữ GET không thay đổi phiên. |
| **Login CSRF** | Nạn nhân bị đưa vào trạng thái đăng nhập không chủ ý, có thể là tài khoản của attacker. | CSRF token trước login, OAuth2/OIDC state/correlation. |
| **CSRF nghiệp vụ** | Nạn nhân đang đăng nhập bị ép thực hiện thao tác đổi trạng thái như hủy đơn. | CSRF token, đúng method, authorization tài nguyên. |
| **Session fixation** | Session ID có thể bị chọn/biết trước authentication. | Đổi/rotate session ID sau login. |
| **Session hijacking** | Credential phiên bị đánh cắp hoặc tái sử dụng. | TLS, Secure/HttpOnly, chống XSS, timeout và revocation. |
| **Open redirect sau logout** | URL chuyển hướng bị attacker điều khiển. | Redirect đích được phép, không dùng input tự do làm URL. |

Hệ thống có thể bảo vệ tốt CSRF logout nhưng vẫn bị session hijacking nếu session ID bị lộ. **Một lớp phòng vệ không chứng minh tất cả những lớp còn lại đã đúng**.

## 2. Chọn HTTP method: safe, idempotent và state transition

Để thiết kế logout, cần phân biệt ba ý:

- **Safe method** theo HTTP: client không yêu cầu tác động thay đổi trạng thái nghiệp vụ; ví dụ **GET** và **HEAD**.
- **Idempotent method**: thực hiện cùng một request nhiều lần có **hiệu ứng mong muốn** tương đương một lần; ví dụ **PUT** và **DELETE** theo ngữ nghĩa HTTP.
- **CSRF-protected state transition**: hành động thay đổi trạng thái, dựa vào credential browser tự gửi, phải có cơ chế xác nhận request được khởi tạo hợp lệ.

**Safe và idempotent không đồng nghĩa nhau.** POST có thể được ứng dụng thiết kế để xử lý lặp một cách ổn định, nhưng POST **không phải HTTP idempotent method theo định nghĩa mặc định của giao thức**.

### 2.1. Ma trận method cho logout và thao tác liên quan

| HTTP method | Safe theo HTTP? | Idempotent theo HTTP? | Có nên dùng để logout session? |
| --- | --- | --- | --- |
| **GET** | Có | Có | **Không** thực hiện logout; có thể hiển thị trang xác nhận hoặc trạng thái. |
| **HEAD** | Có | Có | **Không** thực hiện logout. |
| **OPTIONS** | Có | Có | Không dùng để kết thúc phiên; browser có thể gửi OPTIONS CORS preflight. |
| **TRACE** | Có về ngữ nghĩa HTTP | Có | Không dùng logout; nhiều hệ thống tắt TRACE vì rủi ro triển khai. |
| **POST** | Không | Không mặc định | **Lựa chọn thông dụng cho logout**, có CSRF token khi dựa vào cookie/session. |
| **PUT** | Không | Có | Không phải hợp đồng logout thông thường; chỉ dùng nếu thiết kế API có tài nguyên cụ thể và kiểm tra đầy đủ. |
| **PATCH** | Không | Không mặc định | Không phải lựa chọn mặc định; có thể thay đổi trạng thái nhưng cần bảo mật riêng. |
| **DELETE** | Không | Có | Có thể phù hợp một API quản lý session resource rõ ràng, nhưng không tự chống CSRF và không trùng mặc định của Spring Security. |

Lưu ý: **CORS-safelisted methods** gồm GET, HEAD và POST. Chúng **khác** với khái niệm HTTP safe method; POST có thể thay đổi trạng thái nhưng vẫn không cần preflight nếu điều kiện CORS khác phù hợp.

### 2.2. Vì sao GET không phù hợp dù logout thường là hành động “có thể lặp”?

Một người có thể lập luận: “Sau logout, gọi thêm lần nữa vẫn là đã logout, vậy GET cũng được”. Lập luận này **nhầm idempotency với safety**.

- GET là lời yêu cầu **truy xuất**, có thể được browser, crawler hoặc prefetch tải để xem trước.
- Việc session bị vô hiệu hóa là **một thay đổi trạng thái bảo mật** có thể làm hỏng luồng làm việc.
- Kể cả khi gọi logout lần hai không có hậu quả thêm, **lần gọi thứ nhất vẫn phải là hành động có chủ đích**.
- POST biểu đạt rõ hành động xử lý, nhưng **chỉ chọn POST chưa đủ chống CSRF**: website ngoài vẫn có thể gửi form POST trong những điều kiện phù hợp.

Một logout endpoint được thiết kế tốt có thể **xử lý lần gọi POST thứ hai vô hại** hoặc trả kết quả rõ ràng sau khi session đã hết. Đây là mục tiêu idempotency ở **tầng nghiệp vụ**, không biến POST thành phương thức idempotent ở HTTP spec.

### 2.3. Mô hình URL phù hợp

Một thiết kế thường gặp:

~~~text
GET  /logout     → Hiển thị màn hình xác nhận/CSRF token, KHÔNG đăng xuất.
POST /logout     → Kiểm tra CSRF token rồi thực hiện logout.
GET  /login?logout → Trang thông báo đã đăng xuất, không làm logout tiếp.
~~~

Có thể dùng **POST /account/logout** với URL tùy chỉnh, nhưng phải đồng bộ code frontend, matcher trong Spring Security, CORS policy và test. Khi dùng GET để hiển thị trang xác nhận, response đó chỉ đọc/render, không invalidate session.

### 2.4. PRG và redirect sau logout

Với giao diện form truyền thống, một chuỗi thường gặp:

~~~text
POST /logout + _csrf hợp lệ
  → Spring Security xóa trạng thái phiên
  → 302/303 redirect tới /login?logout
  → Browser GET trang đã đăng xuất
~~~

**POST–Redirect–GET** giúp trang đích hiển thị được và tránh việc refresh một response POST trong giao diện thông thường. Redirect không phải cơ chế thay thế CSRF; CSRF được xác minh **trước** khi logout xảy ra.

Nếu thiết kế redirect tùy chỉnh, tránh nhận trực tiếp một URL cross-origin bất kỳ từ query string như next, returnTo, redirect, vì có thể tạo **open redirect** hoặc luồng phishing.

## 3. Cookie, SameSite, SOP và CORS không thay thế CSRF logout

### 3.1. Vì sao cookie HttpOnly vẫn có thể tham gia CSRF?

Giả sử ứng dụng đặt:

~~~http
Set-Cookie: __Host-APPSESSION=opaque-value; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

- **HttpOnly** ngăn JavaScript bình thường đọc cookie bằng document.cookie.
- **Secure** giới hạn gửi cookie theo kênh an toàn theo browser policy, chủ yếu HTTPS.
- **SameSite=Lax** giới hạn nhiều ngữ cảnh cross-site, nhưng có thể cho cookie đi cùng **top-level navigation GET** cross-site.
- **Path=/** và không có Domain phù hợp với ràng buộc của tiền tố **__Host-**.
- Cookie có thể được browser **tự gửi mà script không cần biết giá trị**.

Do đó, HttpOnly giúp giảm nguy cơ đọc trực tiếp mã phiên nhưng **không ngăn một request do browser gửi khi đủ điều kiện**. CSRF cần được xét độc lập.

### 3.2. SameSite khác Same-Origin Policy

Ví dụ:

~~~text
https://app.example.com    → origin A, site https://example.com
https://api.example.com    → origin B, site https://example.com
https://untrusted.example.com → origin C, site https://example.com
https://outside.test       → origin D, site https://outside.test
~~~

A, B, C là **khác origin** nhưng thường **same-site** theo schemeful site. Một subdomain không đáng tin có thể tạo request same-site đến API. **SameSite không phải ranh giới bảo mật tuyệt đối giữa các subdomain**.

| Chính sách | Hỗ trợ giảm rủi ro gì? | Điều còn cần |
| --- | --- | --- |
| **SameSite=Strict** | Giảm gửi cookie trong nhiều request cross-site. | CSRF token, xử lý flow same-site từ subdomain không đáng tin. |
| **SameSite=Lax** | Hạn chế cookie ở nhiều cross-site POST/form; cho một số điều hướng GET cấp cao nhất. | Tuyệt đối không để GET thực hiện logout. |
| **SameSite=None; Secure** | Cho phép một số tích hợp cross-site khi cookie policy khác cho phép. | CSRF token, third-party cookie restrictions và thiết kế tích hợp phù hợp. |

Không nên dựa vào thuộc tính SameSite **mặc định** không được khai báo. Browser có thể có các ngoại lệ/biến thể tương thích; hãy khai báo chính sách rõ và kiểm thử.

### 3.3. Form HTML có thể gửi POST mà không cần CORS preflight

Website bên ngoài có thể tạo form:

~~~html
<form method="post" action="https://account.example.com/logout">
  <button type="submit">Continue</button>
</form>
~~~

HTML form thông thường có thể gửi POST cross-origin mà không cần một OPTIONS preflight như fetch JSON có custom header. CORS có thể khiến JavaScript của website ngoài **không được đọc response**, nhưng request có thể đã đến server.

Với thiết kế đúng, **POST /logout thiếu CSRF token phải bị từ chối**, bất kể website ngoài đọc response được hay không.

### 3.4. Custom header có thể tạo preflight nhưng không thay token

Một SPA hợp lệ có thể gửi:

~~~javascript
await fetch("https://api.example.com/logout", {
  method: "POST",
  credentials: "include",
  headers: {
    "X-CSRF-TOKEN": csrfToken
  }
});
~~~

Header **X-CSRF-TOKEN** thường khiến fetch cross-origin cần OPTIONS preflight vì nó không thuộc CORS safelist. Nhưng:

- **OPTIONS đạt** chỉ chứng minh browser được phép tiếp tục theo CORS policy.
- **POST thực** vẫn phải có token hợp lệ, session và các điều kiện bảo mật cần thiết.
- Nếu server chỉ kiểm tra header X-CSRF-TOKEN **có tồn tại** mà không xác minh giá trị, đó không phải CSRF protection đầy đủ.
- **Credential mode include** không vượt qua Domain/Path/Secure/SameSite hoặc chính sách cookie bên thứ ba.

### 3.5. Origin, Referer và Fetch Metadata chỉ là lớp bổ sung

Browser có thể gửi:

~~~http
Origin: https://app.example.com
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
~~~

Các header này giúp phân loại nguồn/ngữ cảnh request trong browser hỗ trợ. Chúng **không phải bằng chứng danh tính đã xác thực**, vì HTTP client ngoài browser có thể tự khai giá trị tương tự.

**Origin** có thể vắng mặt hoặc có giá trị null trong một số ngữ cảnh. **Referer** chịu referrer policy và có thể bị rút gọn. **Sec-Fetch-Site: same-site** không chứng minh mọi subdomain đều đáng tin. Nếu dùng làm lớp bổ trợ, cần chính sách **fallback, ngoại lệ hợp lệ và so sánh origin chính xác**.

Không thay CSRF token trên logout session-based bằng điều kiện đơn giản “Origin chứa example.com”.

## 4. Spring Security Servlet: mặc định GET là xác nhận, POST mới logout

Trong ứng dụng Spring Security Servlet sử dụng cơ chế logout mặc định và **CSRF đang bật**, nên hiểu hai URL có cùng path nhưng **khác method**:

- **GET /logout**: khi trang logout do Spring Security cung cấp được bật, trình duyệt nhận **trang xác nhận đăng xuất**, chứa cơ chế gửi yêu cầu POST với CSRF token. **Chưa vô hiệu hóa phiên chỉ vì GET**.
- **POST /logout**: khi có **CSRF token hợp lệ**, Spring Security chạy **LogoutFilter** và các handlers được cấu hình để hoàn tất logout.
- **POST /logout thiếu/sai token**: bị CSRF protection từ chối, thường 403, không thực hiện logout.
- **Sau logout**: cơ chế Servlet mặc định thường redirect tới **/login?logout**, trừ khi ứng dụng thay success handler.

### 4.1. Dòng xử lý

~~~mermaid
flowchart TD
    A["Browser gửi request /logout"] --> B{"HTTP method?"}
    B -->|GET| C["Hiển thị trang xác nhận, không invalidate session"]
    B -->|POST| D{"CSRF token hợp lệ?"}
    D -->|Không| E["403 / từ chối, session còn"]
    D -->|Có| F["LogoutFilter + LogoutHandlers"]
    F --> G["Invalidate session / dọn SecurityContext và token liên quan"]
    G --> H["LogoutSuccessHandler"]
    H --> I["Redirect hoặc trả 204 cho SPA"]
~~~

Sơ đồ nêu **hành vi mong đợi với Spring Security Servlet và CSRF bật**. Với filter chain hoặc logout matcher tùy chỉnh, phải kiểm tra ứng dụng đang thực hiện đúng logic đó, không suy từ tên method/URL.

### 4.2. Điều nguy hiểm khi tắt CSRF

Nếu cấu hình Servlet tắt CSRF một cách rộng:

~~~java
// Không phù hợp nếu ứng dụng còn dùng cookie/session để xác thực.
http.csrf(csrf -> csrf.disable());
~~~

thì hành vi mặc định GET /logout của Spring Security có thể chuyển từ **hiển thị xác nhận** sang **thực hiện logout ngay**, vì ràng buộc POST theo CSRF không còn được áp dụng theo cách mặc định. Đây là một điểm dễ gây bất ngờ khi di chuyển từ API thử nghiệm sang ứng dụng có form login/session.

**Không tắt CSRF toàn bộ ứng dụng chỉ để API POST chạy được.** Hãy phân loại API nào thực sự dựa vào credentials được browser tự gửi, API nào chỉ dùng Bearer token không tự gắn và endpoint nào có yêu cầu kỹ thuật đặc biệt; chỉ cân nhắc ngoại lệ **hẹp** sau khi phân tích threat model.

### 4.3. Tùy chỉnh logout matcher sai có thể mở lại GET

Ngay cả khi CSRF bật, lập trình viên có thể thay một matcher POST thành matcher không giới hạn method, hoặc tạo một MVC GET handler tự gọi invalidate session. Khi đó, logout CSRF có thể xuất hiện trở lại.

**Nguyên tắc:** đường dẫn phù hợp chỉ là một phần điều kiện; matcher logout cần tính cả **HTTP method** và CSRF protection. Hãy đọc cấu hình **đang áp dụng thực** của từng SecurityFilterChain, không chỉ nhìn tên /logout.

### 4.4. LogoutFilter, authorization và permitAll

Trong Servlet, **LogoutFilter** thường nằm trước **AuthorizationFilter**. Vì thế logout endpoint được Spring Security cung cấp qua logout DSL **thường không cần khai báo permitAll chỉ để filter thực hiện logout**.

Một **trang kết quả** do MVC phục vụ sau logout (ví dụ GET /signed-out) có thể cần được phép truy cập anonymous, bởi session đã hết. Điều này **không có nghĩa phải tắt CSRF cho POST /logout**.

### 4.5. Các việc Spring Security Servlet thực hiện mặc định

Khi POST logout hợp lệ và cấu hình mặc định được sử dụng, chuỗi xử lý có thể bao gồm:

- **SecurityContextLogoutHandler**: invalidate HttpSession, xóa trạng thái authentication/security context và xử lý repository tương ứng.
- **Remember-me cleanup** nếu ứng dụng bật remember-me và các services/handlers liên quan được tích hợp.
- **CsrfLogoutHandler**: xóa token CSRF lưu trước đó theo repository.
- **LogoutSuccessEvent**: phát sự kiện logout theo cơ chế framework.
- **LogoutSuccessHandler**: chuyển hướng đến URL thành công (thường /login?logout) hoặc trả HTTP status tùy cấu hình.

Cần phân biệt **những hành động mặc định của ứng dụng Servlet/session** với những credential không tự thuộc quản lý LogoutFilter, như refresh token được ứng dụng tự lưu, server-side device sessions khác hoặc phiên của IdP.

## 5. Cấu hình Servlet và form logout an toàn

Ví dụ Java cho **Spring Boot 3.x / Spring Security 6.x / Servlet**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletLogoutSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**", "/login", "/signed-out")
                            .permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessUrl("/signed-out")
                        .invalidateHttpSession(true)
                        .clearAuthentication(true)
                        .permitAll())
                .build();
    }
}
~~~

Đây là **một cấu hình minh họa hoàn chỉnh về ý tưởng**, giả định authentication provider/login page và tài nguyên liên quan đã được cấu hình trong ứng dụng thực tế. **/signed-out** cần có endpoint/view GET thực sự để hiển thị trạng thái, hoặc cấu hình redirect tới một trang đã tồn tại.

Các lựa chọn:

1. **csrf(Customizer.withDefaults())**: giữ cơ chế CSRF, bao gồm POST /logout.
2. **logoutUrl("/logout")**: chọn đường dẫn của logout filter; với CSRF bật, cơ chế mặc định đòi method POST.
3. **logoutSuccessUrl("/signed-out")**: điều hướng tới trang thông báo, không phải hành động đăng xuất mới.
4. **invalidateHttpSession(true)**: làm rõ yêu cầu vô hiệu hóa session.
5. **clearAuthentication(true)**: làm rõ yêu cầu xóa trạng thái authentication trong security context.
6. **permitAll()** trong logout DSL: giúp cho phép các URL liên quan mà logout cấu hình; **không bỏ kiểm tra CSRF**.

Với Spring Security cấu hình mặc định, nhiều lựa chọn trên đã được xử lý phù hợp sẵn; đưa chúng ra để người học thấy **trách nhiệm từng phần**.

### 5.1. HTML form logout dùng POST

~~~html
<!-- Ví dụ form HTML đã được server render, với CSRF token thật. -->
<form method="post" action="/logout">
  <input type="hidden" name="_csrf"
         value="TOKEN_DO_SPRING_SECURITY_CAP">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Giá trị token là **placeholder**, không được hardcode trong ứng dụng. Server/template integration cần tạo và render token đúng theo **CsrfTokenRepository** và request handler được cấu hình. Trình duyệt gửi POST cùng session cookie và token; Spring Security xác minh token rồi mới thực hiện logout.

### 5.2. Thymeleaf và tự chèn hidden CSRF field

Nếu dùng Spring MVC + Thymeleaf với integration phù hợp:

~~~html
<form th:action="@{/logout}" method="post">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Cơ chế Spring MVC **RequestDataValueProcessor** có thể chèn hidden CSRF field cho form POST sử dụng th:action. Nhưng không nên **đoán** rằng mọi template engine đều làm điều đó; hãy kiểm tra **HTML đã render trong DevTools**. Nếu không có field token, cần expose CsrfToken và thêm field thủ công phù hợp, không chèn trùng khi integration đã tự chèn.

### 5.3. Muốn dùng một liên kết thay nút POST thì sao?

Một liên kết:

~~~html
<a href="/logout">Đăng xuất</a>
~~~

với Spring Security Servlet mặc định và CSRF bật thường **dẫn đến trang xác nhận** thay vì đăng xuất ngay. Đó là một lựa chọn hợp lệ cho người dùng không có JavaScript: GET chỉ hiển thị form xác nhận, sau đó **POST có CSRF token** mới hoàn tất logout.

Nếu muốn một nút trông giống liên kết nhưng thực hiện logout khi bấm, hãy tạo **form POST** và style nút theo thiết kế UI. Không đổi logout handler thành GET chỉ để giữ một thẻ a.

### 5.4. Trang xác nhận không cần thực hiện side effect

Một trang GET có thể hiển thị:

~~~html
<h1>Xác nhận đăng xuất</h1>
<p>Đăng xuất sẽ kết thúc phiên làm việc trên trình duyệt này.</p>
<form method="post" action="/logout">
  <input type="hidden" name="_csrf"
         value="TOKEN_HOP_LE_CUA_PHIEN">
  <button type="submit">Xác nhận đăng xuất</button>
</form>
~~~

GET không gọi invalidate session, không xóa token và không xóa cookie. Chỉ khi **POST hợp lệ** mới thực hiện state transition. Nếu session đã hết hạn trước khi user xác nhận, ứng dụng cần trả trạng thái rõ ràng hoặc yêu cầu làm mới phiên; đừng bỏ CSRF vì một token cũ hết hạn.
## 6. Logout không chỉ là xóa cookie: vòng đời phiên và LogoutHandler

Một logout thành công cần định nghĩa rõ: **credential nào sẽ không còn được server chấp nhận**, dữ liệu nào phải xóa ở browser và user còn có thể tự đăng nhập lại qua cơ chế nào.

### 6.1. Ba lớp cần dọn dẹp

~~~mermaid
flowchart LR
    B["Browser: cookie + state UI"] --> S["Spring Security: SecurityContext + session"]
    S --> R["Session repository / remember-me / refresh token store"]
    R --> I["IdP hoặc dịch vụ nhận diện bên ngoài"]
    L["POST /logout + CSRF hợp lệ"] --> S
    S --> B
    S --> R
    R -.->|"Không tự động logout"| I
~~~

Trong mô hình session:

1. **Browser** có thể còn cookie phiên, ngay cả khi session server đã mất hiệu lực.
2. **Server** phải vô hiệu hóa session hoặc xóa authentication sao cho request mới không được xác thực bằng phiên cũ.
3. **Remember-me và refresh token** là credential dài hạn riêng, cần thu hồi theo chính sách.
4. **SSO session tại IdP** là một vùng tin cậy khác, không tự kết thúc khi app logout.
5. **localStorage/IndexedDB/Cache Storage** có thể vẫn giữ dữ liệu nếu frontend không dọn dẹp.

Đừng chỉ xóa cookie trong JavaScript rồi tuyên bố đã logout ở server. Một session ID bị sao chép trước đó có thể còn dùng được nếu session repository chưa bị invalidate.

### 6.2. Dọn SecurityContext và HttpSession trong Servlet

Trong Servlet, **SecurityContextLogoutHandler** có thể invalidate HttpSession và xóa SecurityContext. **Ưu tiên logout DSL** để giữ chuỗi handlers mặc định. Nếu buộc phải tạo endpoint MVC riêng, phải gọi thành phần logout thực sự:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomLogoutController {
    private final SecurityContextLogoutHandler handler =
            new SecurityContextLogoutHandler();

    // Chỉ minh họa giải pháp tối thiểu, không thay logout DSL đầy đủ.
    @PostMapping("/custom-logout")
    void customLogout(Authentication authentication,
            HttpServletRequest request,
            HttpServletResponse response) {
        handler.logout(request, response, authentication);
    }
}
~~~

**Cảnh báo:** Mẫu này chưa tái tạo tất cả việc dọn remember-me, CSRF token, audit event và success handler. Endpoint vẫn cần **CSRF protection**, authorization/routing phù hợp và cleanup các credential khác. Một controller chỉ sửa UI hoặc xóa cookie **không phải logout an toàn**.

### 6.3. LogoutHandler khác LogoutSuccessHandler

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **LogoutFilter** | Nhận dạng URL/method của logout request và gọi chuỗi xử lý. | POST /logout. |
| **LogoutHandler** | Dọn session/security state. | Invalidate HttpSession, remember-me token cleanup. |
| **LogoutSuccessHandler** | Trả response sau khi dọn dẹp. | Redirect, 204, thông báo logout. |
| **CsrfFilter** | Xác minh CSRF token trên POST logout. | Thiếu/sai token thì từ chối. |
| **Session repository** | Quản lý vòng đời session phía server. | HttpSession, Spring Session/Redis. |

Một success handler trả 204 không tự chứng minh session đã bị invalidate nếu chain logout tùy chỉnh không làm việc cần thiết.

### 6.4. Cookie phải được xóa đúng tên và phạm vi

~~~http
Set-Cookie: __Host-APPSESSION=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Việc xóa cần khớp **cookie name, Domain (nếu có) và Path**. Nếu lúc tạo dùng Path=/app nhưng lúc xóa dùng Path=/ thì cookie cũ có thể vẫn tồn tại. Tiền tố **__Host-** bắt buộc Secure, Path=/ và không có Domain khi browser chấp nhận cookie.

Có thể thêm vào logout DSL:

~~~java
// Bên trong cấu hình HttpSecurity cho ứng dụng dùng cookie này.
.logout(logout -> logout
        .deleteCookies("__Host-APPSESSION")
        .invalidateHttpSession(true))
~~~

**deleteCookies không được bảo đảm hoạt động hoàn toàn giống nhau trên mọi servlet container/cookie configuration**. Kiểm tra response Set-Cookie trên DevTools, và quan trọng hơn, xác minh server **không còn chấp nhận ID phiên cũ**.

### 6.5. Clear-Site-Data hữu ích nhưng phạm vi có thể rộng

Logout response có thể yêu cầu browser dọn cookie, storage hoặc cache:

~~~http
Clear-Site-Data: "cookies", "storage"
~~~

Spring Security Servlet hỗ trợ header writer khi logout:

~~~java
import org.springframework.security.web.authentication.logout.HeaderWriterLogoutHandler;
import org.springframework.security.web.header.writers.ClearSiteDataHeaderWriter;
import org.springframework.security.web.header.writers.ClearSiteDataHeaderWriter.Directive;

// Đoạn bên trong cấu hình HttpSecurity, không phải cả filter chain.
HeaderWriterLogoutHandler clearCookies =
        new HeaderWriterLogoutHandler(
                new ClearSiteDataHeaderWriter(Directive.COOKIES));

http.logout(logout -> logout.addLogoutHandler(clearCookies));
~~~

Clear-Site-Data có yêu cầu **secure context**, mức hỗ trợ browser và phạm vi dọn cookie/storage có thể ảnh hưởng những ứng dụng cùng site. Chỉ dùng directives cần thiết và kiểm thử. **Header này không thay thế session invalidation trên server, không tự revoke refresh token hay SSO session**.

### 6.6. Audit logout không được lộ bí mật

Có thể ghi user ID, tenant (nếu áp dụng), thời điểm, hình thức logout, kết quả cleanup và correlation ID được làm sạch. Tránh ghi đầy đủ session ID, CSRF token, refresh token hoặc signature vào log. IP nếu dùng phải được lấy theo **trusted proxy chain**, không tin X-Forwarded-For do client ngoài tự đặt.

## 7. SPA logout: POST có CSRF, status rõ ràng và CORS đúng phạm vi

SPA ở **https://app.example.com** gửi logout đến **https://api.example.com** dùng cookie session của API cần phối hợp:

- **CSRF token hợp lệ** được frontend nhận qua ứng dụng.
- **credentials: include** để browser cân nhắc gửi cookie cross-origin.
- **CORS** cho đúng origin, method, headers và actual response.
- **Dọn state frontend** sau khi server được xác nhận logout hoặc theo quy trình xử lý lỗi rõ ràng.

### 7.1. Trả 204 thay vì redirect HTML nếu frontend tự điều hướng

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Cache-Control: no-store
~~~

Một fetch đến API trả redirect 302 có thể tự đi theo redirect như request mạng nhưng **không tự điều hướng cửa sổ SPA**. Nếu response sau redirect thiếu CORS, frontend có thể báo lỗi **dù session ở server đã bị invalidate**.

### 7.2. Cấu hình Servlet cho SPA logout

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.HttpStatusReturningLogoutSuccessHandler;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class SpaLogoutServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutSuccessHandler(
                                new HttpStatusReturningLogoutSuccessHandler(
                                        HttpStatus.NO_CONTENT))
                        .invalidateHttpSession(true)
                        .deleteCookies("__Host-APPSESSION"))
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/logout", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Đây là **một phương án Servlet thay thế mục 5**, không khai báo hai SecurityFilterChain có matcher chồng nhau nếu không có điều phối rõ ràng. Cần thêm authentication provider, endpoint cấp token, cookie config và authorization thực tế. Nếu SPA cần GET /csrf, cấu hình CORS cho endpoint đó. **POST /logout vẫn cần CSRF token**.

### 7.3. Frontend gọi POST logout

~~~javascript
const apiBase = "https://api.example.com";

async function logout(csrf) {
  // csrf = {headerName, token} do backend cấp đúng session.
  const response = await fetch(apiBase + "/logout", {
    method: "POST",
    credentials: "include",
    headers: {
      [csrf.headerName]: csrf.token
    },
    cache: "no-store",
    redirect: "error"
  });

  if (!response.ok) {
    throw new Error("Logout chưa được xác nhận: " + response.status);
  }

  clearSensitiveClientState();
  navigateToLogin();
}
~~~

**clearSensitiveClientState** và **navigateToLogin** là hàm ứng dụng, không phải browser API dựng sẵn. **redirect: error** chỉ phù hợp nếu API thật sự dùng response 204 thay vì redirect mặc định; không dùng một giá trị CSRF random do client tạo.

### 7.4. Nếu logout response thất lạc hoặc bị CORS chặn đọc

~~~text
Browser gửi POST /logout hợp lệ
  → Server invalidate session
  → Response bị mất hoặc CORS trên actual response sai
  → fetch báo lỗi
~~~

Không thể suy từ lỗi fetch rằng server chưa logout. Có thể hiển thị trạng thái **chưa xác định**, hạn chế thao tác nhạy cảm và kiểm tra lại bằng một GET /api/me được bảo vệ. Nếu nhận 401 đúng hợp đồng, UI có thể chuyển sang trạng thái hết phiên. Khi offline, dọn dữ liệu nhạy cảm phía client theo chính sách nhưng **không tuyên bố đã thu hồi mọi credential ở server** nếu chưa xác minh.

Thiết kế xử lý gọi POST logout lặp sao cho không gây tác dụng phụ ngoài ý muốn. Đừng retry mù quáng những request giao dịch khác chỉ vì CORS error.

### 7.5. Nhiều tab và cache sau logout

Các tab cùng browser profile có thể chia sẻ cookie nhưng giữ UI state độc lập. BroadcastChannel có thể hỗ trợ đồng bộ:

~~~javascript
const channel = new BroadcastChannel("auth-events");

function announceLogout() {
  channel.postMessage({ type: "LOGGED_OUT" });
}

channel.addEventListener("message", (event) => {
  if (event.data?.type === "LOGGED_OUT") {
    clearSensitiveClientState();
    navigateToLogin();
  }
});
~~~

BroadcastChannel **không tự thu hồi session**, tab offline có thể không nhận sự kiện. Cần xử lý bfcache, IndexedDB, localStorage, Cache Storage và service worker đúng dữ liệu người dùng. **Cache-Control: no-store** hữu ích nhưng không tự xóa mọi dữ liệu do ứng dụng chủ động lưu.
## 8. Spring Security Reactive/WebFlux: POST logout và WebSession

**WebFlux** dùng **SecurityWebFilterChain**, **ServerHttpSecurity**, **LogoutWebFilter** và **WebSession**. Đây không phải Servlet HttpSession/LogoutFilter. Tuy vậy, browser áp dụng cùng quy tắc HTTP methods, CORS, SameSite và CSRF.

Với CSRF bật và logout mặc định, **LogoutWebFilter xử lý POST /logout**, còn GET có thể được dùng cho trang xác nhận nếu trang đó được framework/ứng dụng cung cấp.

### 8.1. SecurityWebFilterChain cơ bản

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveLogoutSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout.logoutUrl("/logout"))
                .build();
    }
}
~~~

Giải thích:

- **LogoutWebFilter** nhận POST /logout theo matcher mặc định, không cần MVC controller.
- **CSRF token** phải được gửi đúng WebSession/ServerCsrfTokenRepository.
- **ServerHttpSecurity** là API cho WebFlux; không dùng HttpSecurity để cấu hình stack này.
- **WebSession** có vòng đời riêng với Servlet HttpSession.
- Phải kiểm tra ứng dụng thực tế có trả trang xác nhận GET hay không nếu thiết kế dùng liên kết GET.

### 8.2. Vô hiệu hóa toàn bộ WebSession khi cần

Tài liệu Spring Security WebFlux lưu ý **logout mặc định dọn security context và CSRF repository**, nhưng nếu cần **invalidate WebSession**, có thể bổ sung **WebSessionServerLogoutHandler**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.HttpStatusReturningServerLogoutSuccessHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

@Configuration
@EnableWebFluxSecurity
class ReactiveFullLogoutConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        DelegatingServerLogoutHandler cleanup =
                new DelegatingServerLogoutHandler(
                        new SecurityContextServerLogoutHandler(),
                        new WebSessionServerLogoutHandler());

        return http
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                .csrf(Customizer.withDefaults())
                .logout(logout -> logout
                        .logoutUrl("/logout")
                        .logoutHandler(cleanup)
                        .logoutSuccessHandler(
                                new HttpStatusReturningServerLogoutSuccessHandler(
                                        HttpStatus.NO_CONTENT)))
                .build();
    }
}
~~~

Đây là **phương án khác** với mục 8.1, không khai báo hai bean SecurityWebFilterChain có matcher chồng nhau trong cùng ứng dụng. Đoạn code chọn **204 No Content** thay vì redirect để phù hợp SPA.

Một điểm quan trọng: do cấu hình này **chỉ định lại ServerLogoutHandler**, phải xem xét việc dọn **CSRF repository**, remember-me/credential tùy chỉnh và các tích hợp audit mà logout mặc định có thể xử lý khác. **WebSession bị invalidate** sẽ xóa dữ liệu phiên đó, nhưng không tự thu hồi mọi token lưu ở một repository độc lập.

### 8.3. CORS cho SPA logout trên WebFlux

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveLogoutCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/logout", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Tích hợp vào đúng SecurityWebFilterChain:

~~~java
// Thêm vào cấu hình ServerHttpSecurity đã chọn:
http.cors(cors -> cors.configurationSource(corsConfigurationSource()));
~~~

Không nhầm **org.springframework.web.cors.reactive** với các lớp CORS source của Servlet. Nếu cần GET /csrf để cấp token cho SPA, bổ sung path đó với CORS allowlist thích hợp. **OPTIONS preflight thường không mang cookie phiên**, nhưng POST logout thực phải qua CSRF và xử lý WebSession.

### 8.4. CSRF token WebFlux có thể được cung cấp bất đồng bộ

WebFlux dùng **ServerCsrfTokenRepository** và CsrfToken có thể được expose qua **Mono<CsrfToken>**; form tùy chỉnh phải render/resolve giá trị token đúng, không hard-code.

~~~html
<!-- Form minh họa, giá trị token phải do server cấp thật. -->
<form method="post" action="/logout">
  <input type="hidden" name="_csrf"
         value="TOKEN_TU_SERVER_CSRF_REPOSITORY">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Một ứng dụng Reactive cũng phải xem xét vòng đời WebSession/CSRF token sau login và logout: token của phiên cũ có thể không hợp lệ cho phiên mới.

### 8.5. Cookie ID của WebSession

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.server.session.CookieWebSessionIdResolver;
import org.springframework.web.server.session.WebSessionIdResolver;

@Configuration
class ReactiveSessionCookieConfig {

    @Bean
    WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();
        resolver.setCookieName("__Host-APPSESSION");
        resolver.addCookieInitializer(cookie -> cookie
                .path("/")
                .secure(true)
                .httpOnly(true)
                .sameSite("Lax"));
        return resolver;
    }
}
~~~

Đây là ví dụ cho **HTTPS production**. Tiền tố __Host- yêu cầu không có Domain, Secure và Path=/. Nếu Spring Session Reactive hoặc cấu hình hiện có đã định nghĩa resolver, phải chọn đúng bean và tránh xung đột. Không dùng **server.servlet.session.*** để cấu hình WebSession.

## 9. Logout theo từng loại credential và phạm vi

Từ **logout** có thể là hành động khác nhau tùy kiểu xác thực và yêu cầu sản phẩm:

| Credential hoặc trạng thái | Logout cần làm gì? | Điều không tự đạt được |
| --- | --- | --- |
| **HttpSession / WebSession** | Thu hồi/xóa trạng thái authentication/session server-side. | Không tự hủy session ở thiết bị khác nếu repository chưa được thiết kế cho yêu cầu đó. |
| **Cookie session** | Yêu cầu browser xóa cookie đúng phạm vi. | Không bảo đảm ID phiên đã bị vô hiệu hóa ở server. |
| **Remember-me** | Dọn cookie/token persistent theo remember-me service/repository. | Session timeout đơn thuần không xóa credential này. |
| **JWT access token** | Xóa khỏi client và thu hồi/giới hạn qua cơ chế server nếu cần. | Xóa localStorage không thu hồi bản sao JWT đã bị sao chép. |
| **Refresh token** | Thu hồi token hiện tại/token family theo chính sách. | Không tự mất hiệu lực chỉ vì access token hết hạn. |
| **SSO session tại IdP** | Dùng giao thức logout của IdP nếu cần. | Local app logout không mặc nhiên logout khỏi IdP. |
| **Dữ liệu cache/storage client** | Dọn dữ liệu nhạy cảm và phân biệt account/tenant. | Clear session không tự xóa IndexedDB hoặc Cache Storage. |

### 9.1. JWT Bearer khác cookie tự gửi

Một frontend chủ động gắn:

~~~http
Authorization: Bearer opaque-or-jwt-access-token
~~~

khác với browser tự gắn cookie phiên. Token trong localStorage/biến JS **không được browser tự đưa vào header Authorization** trên mọi website; mã ứng dụng chủ động làm việc đó.

Nhưng nếu access token đã bị sao chép và server chỉ kiểm tra chữ ký với exp, việc frontend xóa token không bảo đảm bản sao đó mất hiệu lực. Cần mô hình **short lifetime, revocation/denylist hoặc ràng buộc session/token** theo chính sách thực tế.

Nếu refresh token dùng **HttpOnly cookie tự gửi**, endpoint làm mới/thu hồi refresh token vẫn cần đánh giá CSRF dù access token được truyền bằng Bearer header.

### 9.2. Remember-me có thể đăng nhập lại sau logout

Nếu tính năng remember-me bật nhưng chỉ HttpSession bị invalidate:

~~~text
HttpSession kết thúc
  ↓
Remember-me credential còn hiệu lực
  ↓
Ứng dụng có thể xác thực lại theo remember-me policy
~~~

Servlet logout DSL tích hợp các RememberMeServices khi cấu hình đúng. Nếu user vừa logout nhưng tự đăng nhập lại không cần password, cần xác định **remember-me**, OIDC SSO và refresh token trước khi kết luận HttpSession invalidation thất bại.

### 9.3. Local app logout khác OIDC/SSO logout

Trong ứng dụng dùng OAuth2/OIDC login có thể tồn tại:

1. **Session của Spring ứng dụng**.
2. **SSO session của IdP**.
3. **Access/refresh token** được client/BFF lưu tại backend.
4. **Session của những ứng dụng khác** đăng nhập cùng IdP.

Logout local app chỉ giải quyết vùng ứng dụng nếu không có phối hợp thêm. Khi cần logout tại IdP, dùng **OIDC RP-Initiated Logout** hoặc cách provider hỗ trợ, cấu hình endpoint và post-logout redirect đúng. Không lấy URL đích do user tùy ý cung cấp, và không biến một GET /logout nội bộ thành lối kích hoạt mọi session logout.

**Front-channel logout** (qua browser) và **back-channel logout** (server nhận thông điệp có bảo vệ) khác request POST /logout của user. Nếu một IdP gửi back-channel logout token, phải xác minh **signature, issuer, audience, iat/exp/jti, sid/sub** và chống replay theo giao thức. Callback không dùng CSRF form token cần ngoại lệ hẹp với cơ chế xác thực riêng, không tắt CSRF trên toàn ứng dụng.

### 9.4. Logout một thiết bị hay toàn bộ thiết bị?

| Phạm vi | Dữ liệu có thể cần xử lý |
| --- | --- |
| **Tab hiện tại** | UI state tab, nhưng cookie jar/session có thể được tab khác dùng. |
| **Browser profile hiện tại** | Session cookie và server session gắn với profile. |
| **Một thiết bị** | Sessions/token families gắn với device, các tab và browser có liên quan. |
| **Tất cả thiết bị** | Toàn bộ active sessions và refresh tokens của account theo chính sách. |
| **Toàn hệ thống SSO** | Logout phối hợp với IdP và các ứng dụng liên kết nếu giao thức hỗ trợ. |

Không ghi “đã logout mọi nơi” chỉ vì browser hiện tại đã xóa cookie. Cần có cơ chế server-side lưu/thu hồi từng session hoặc token family để thực thi phạm vi đó.

## 10. Khi muốn dùng DELETE, GET confirmation hoặc hành động tự động

### 10.1. DELETE /sessions/current có thể là API hợp lệ

REST API có thể mô hình hóa phiên làm một tài nguyên:

~~~http
DELETE /api/sessions/current HTTP/1.1
Host: api.example.com
Cookie: __Host-APPSESSION=opaque
X-CSRF-TOKEN: valid-session-token
~~~

Đây có thể là một thiết kế API hợp lý nếu server xác minh **authentication, CSRF và quyền thu hồi phiên**. DELETE là idempotent về HTTP semantics, nhưng **không tự chống CSRF**. Nó không phải URL/method mặc định của Spring Security logout DSL; cần matcher/custom handler riêng có bảo vệ phù hợp.

Một client ngoài browser có thể gọi DELETE trực tiếp; CORS/preflight không phải authorization. Nếu cùng API còn chấp nhận cookie browser, phải đánh giá CSRF cho DELETE.

### 10.2. Logout vì timeout, đổi mật khẩu hoặc admin revoke

Một số phiên hết hiệu lực do **hành động server-side** không xuất phát từ browser POST /logout:

- **Idle timeout** hoặc absolute session lifetime.
- User đổi mật khẩu và chính sách yêu cầu thu hồi session khác.
- Admin khóa tài khoản.
- Risk engine phát hiện phiên đáng ngờ.
- IdP gửi back-channel logout được xác minh.

Không ép server phải tự gọi một HTTP GET/POST /logout như browser. Những cơ chế nội bộ có thể trực tiếp **invalidate session/revoke tokens** theo API tương ứng; các hành động này phải xác thực/quản lý quyền theo **nguồn phát lệnh** của chúng.

### 10.3. GET chỉ nên đọc trạng thái hoặc hiển thị xác nhận

GET /logout có thể là một **trang xác nhận** như trong mặc định Servlet, hoặc GET /session-status dùng để trả **trạng thái hiện tại** nếu được thiết kế an toàn. Chúng không được tự vô hiệu hóa phiên.

Trường hợp người dùng muốn logout bằng một cú click, hãy dùng **button trong form POST** hoặc JavaScript tạo POST kèm CSRF token. Không mở logout matcher nhận GET chỉ vì muốn dùng thẻ a.

### 10.4. Không tạo logout bằng cách “thử đăng xuất khi request 401”

Một SPA gặp 401 vì access token hết hạn không nên tự động gọi hàng loạt POST /logout hoặc xóa mọi session mà không phân biệt:

- 401 do token hết hạn cần refresh theo chính sách?
- 401 do session đã bị invalidated?
- 403 do CSRF token hoặc quyền?
- Lỗi CORS/CSP/network chặn frontend đọc response?
- Có cần hỏi user trước khi xóa những bản nháp chưa lưu không?

Hãy mô hình hóa state transitions có thể kiểm thử, tránh vòng lặp refresh–logout–login vô hạn.
## 11. Kiểm thử: logout chỉ xảy ra khi đủ điều kiện

Bộ test tốt không chỉ xác nhận POST /logout trả 302 hoặc 204. Cần chứng minh **request bị từ chối không làm mất phiên**, còn logout hợp lệ **thật sự chặn truy cập bằng phiên cũ**.

Các ví dụ dưới đây dùng **môi trường test do bạn kiểm soát**. Không chạy thao tác ảnh hưởng tài khoản thật, và không log session ID hay CSRF token thật vào báo cáo.

### 11.1. Ma trận kiểm thử chính

| Tình huống | Kết quả kỳ vọng | Điều phải chứng minh |
| --- | --- | --- |
| **GET /logout** khi CSRF bật và có confirmation page. | Hiển thị trang xác nhận, không logout. | Session vẫn hợp lệ cho request được phép sau GET. |
| **HEAD /logout**. | Không logout. | Không có invalidation dù client thăm dò URL. |
| **POST /logout thiếu CSRF**. | Thường 403. | Session vẫn còn nguyên, LogoutHandler không chạy. |
| **POST /logout sai CSRF**. | Thường 403. | Không thu hồi credential của user do request sai token. |
| **POST /logout có token hợp lệ**. | Redirect hoặc status success theo hợp đồng. | SecurityContext/session cũ không còn được chấp nhận. |
| **GET /logout sau khi tắt CSRF** trong cấu hình mặc định Servlet. | Có nguy cơ thực hiện logout. | Test phát hiện thiết kế GET side effect không mong muốn. |
| **Cross-site top-level GET** đến /logout. | Không logout với cấu hình an toàn. | SameSite=Lax không tạo lỗ hổng GET logout. |
| **Cross-site form POST thiếu token**. | Bị từ chối. | CORS không phải lớp bảo vệ duy nhất. |
| **SPA logout custom header**. | OPTIONS hợp lệ rồi POST thực đúng token. | Preflight không phải request logout; response thực có CORS. |
| **OPTIONS /logout từ origin không được phép**. | Không được cấp quyền CORS. | Allow-Origin không phản chiếu mọi origin. |
| **Logout thành công nhưng cookie vẫn hiện**. | Session cũ vẫn vô hiệu. | Phân biệt cookie jar và session store. |
| **Multiple tabs**. | Request mới ở tab khác không dùng được phiên cũ. | UI/cache có thể cũ nhưng server không cấp dữ liệu mới. |
| **Remember-me/refresh token còn**. | Hành vi theo chính sách logout đã công bố. | Không tự tái xác thực ngoài ý muốn. |
| **OIDC local logout**. | App session bị thu hồi; IdP session xử lý riêng. | Không tuyên bố logout toàn SSO khi chưa có flow. |

### 11.2. MockMvc: kiểm tra CSRF thiếu, sai và hợp lệ

Ví dụ test với **Spring Security Servlet**, spring-security-test và cấu hình logout mặc định:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.logout;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutCsrfMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCsrfDoesNotLogout() throws Exception {
        mvc.perform(post("/logout")
                .with(user("learner")))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfDoesNotLogout() throws Exception {
        mvc.perform(post("/logout")
                .with(user("learner"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfCanLogout() throws Exception {
        // logout() của spring-security-test gửi POST và CSRF token hợp lệ.
        mvc.perform(logout())
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Ví dụ giả định logout success handler mặc định **redirect**. Nếu ứng dụng chọn **204** như mục 7, assertion cuối phải thành **isNoContent()**. Mục tiêu ở đây là kiểm tra **CSRF với logout method**, không khẳng định mọi ứng dụng đều trả cùng status.

**Bổ sung test quan trọng:** Dùng cùng một browser session test từ trước login, gọi **GET /api/me** được phép, thử POST logout thiếu/sai CSRF, sau đó GET /api/me **vẫn được phép**. Khi POST logout với CSRF đúng, GET /api/me bằng **session cũ** phải bị từ chối theo hợp đồng (401, redirect tới login hoặc phản hồi tương đương).

Mock principal tạo bởi **with(user(...))** trong từng request không tự chứng minh persistence/invalidation của session thật. Cần **integration test với cookie jar, HttpSession và session repository** để kiểm tra vòng đời hoàn chỉnh.

### 11.3. Kiểm thử GET /logout không gây side effect

Với cấu hình Servlet bật CSRF, trang xác nhận do framework cung cấp thường được truy cập bằng GET:

~~~java
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

// Đoạn minh họa bên trong test đã bind Spring Security.
mvc.perform(get("/logout"))
    .andExpect(status().isOk());
~~~

Assertion **isOk()** chỉ phù hợp khi **generated confirmation page đang bật**; một ứng dụng có custom logout page, security chain hoặc context path có thể trả kết quả khác. Điều quan trọng hơn status là **không logout khi GET**, cần xác minh session còn hiệu lực sau đó.

### 11.4. WebTestClient: POST có và không có CSRF

Một đoạn test **WebFlux** với spring-security-test:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

// webTestClient đã cấu hình security chain của ứng dụng.
webTestClient
    .mutateWith(mockUser("learner"))
    .post().uri("/logout")
    .exchange()
    .expectStatus().isForbidden();

webTestClient
    .mutateWith(mockUser("learner"))
    .mutateWith(csrf())
    .post().uri("/logout")
    .exchange()
    .expectStatus().isNoContent();
~~~

Test thứ hai giả định cấu hình **HttpStatusReturningServerLogoutSuccessHandler(HttpStatus.NO_CONTENT)** ở mục 8.2. Nếu dùng logout mặc định redirect, assertion cần đổi.

**mockUser** cấp principal giả lập cho từng test request, không thay một integration test chạy WebSession thật. Để xác minh logout WebFlux hoàn chỉnh, cần test cookie session được tái sử dụng qua nhiều request, WebSessionServerLogoutHandler đã invalidate session và GET tài nguyên sau logout không được xác thực.

### 11.5. DevTools: quan sát request thật

Trong **Network → Request Headers/Response Headers** và **Application/Storage → Cookies**:

1. Đăng nhập vào **tài khoản thử nghiệm** với cookie session hợp lệ.
2. Mở GET /logout, kiểm tra trang xác nhận. **Chưa được mất session**.
3. Gửi POST /logout thiếu token trong một luồng test và quan sát status (thường 403), không chạy cleanup.
4. Gửi POST với token hợp lệ từ form; xem status, Set-Cookie, Location, Clear-Site-Data nếu có.
5. Gọi lại **GET /api/me**: principal/session cũ không còn được chấp nhận.
6. Với SPA khác origin, kiểm tra **OPTIONS** có xảy ra do X-CSRF-TOKEN, method, origin và headers nào.
7. Kiểm tra **actual response** của POST có CORS hợp lệ để JS đọc được kết quả.
8. Nếu có remember-me hoặc refresh token, kiểm tra khả năng tái xác thực theo hợp đồng; phân biệt local app và IdP SSO.
9. Với nhiều tab, kiểm tra UI state của từng tab và request mới sau logout.
10. Nếu cookie vẫn còn trong Storage nhưng session đã invalid, không kết luận logout thất bại chỉ từ cookie.

### 11.6. curl: kiểm tra server-side, không mô phỏng đủ browser

Trong môi trường local hoặc staging được phép:

~~~bash
# POST thiếu CSRF token; với session-based CSRF thường bị từ chối.
curl -i -X POST "http://localhost:8080/logout"

# Kiểm tra GET logout không phải đường thực hiện cleanup.
curl -i "http://localhost:8080/logout"
~~~

Để test CSRF có ý nghĩa, phải sử dụng **cookie jar của cùng phiên đăng nhập thử nghiệm và CSRF token được cấp đúng phiên**. Nếu chỉ gọi curl không có session, kết quả có thể khác vì request chưa xác thực hoặc do chain routing.

**curl không thực thi browser SOP/CORS/SameSite/CSP và cookie policy đầy đủ**. Dùng curl để kiểm tra HTTP response, và **browser thật** để xác nhận tình huống logout CSRF do điều hướng hoặc form ngoài.

### 11.7. Kiểm tra CORS preflight riêng

~~~bash
curl -i -X OPTIONS "https://api.example.com/logout" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-csrf-token"
~~~

Với origin hợp lệ, response preflight cần cho phép method và header theo policy ứng dụng. Thử thêm origin không được phép:

~~~bash
curl -i -X OPTIONS "https://api.example.com/logout" \
  -H "Origin: https://outside.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-csrf-token"
~~~

Origin không được phép không nên nhận CORS access có credentials. **Cả hai OPTIONS request không được invalidate session**; chúng chỉ phục vụ đánh giá CORS. Khi browser gửi POST thực, CSRF/token/authorization vẫn cần được xử lý.

## 12. Chẩn đoán lỗi triển khai và xung đột lớp bảo mật

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| **Bấm liên kết GET /logout là logout ngay.** | CSRF bị tắt hoặc matcher/controller thực hiện logout khi GET. | Kiểm tra CsrfFilter, LogoutFilter matcher, security chain và route GET. |
| **GET /logout trả trang xác nhận.** | Hành vi mặc định khi CSRF bật. | Đây không phải lỗi; POST có token mới thực hiện logout. |
| **POST /logout trả 403.** | Token thiếu/sai, session token hết hạn hoặc chain áp dụng CSRF. | So khớp cookie session, csrf repository/handler và request headers. |
| **POST /logout có token nhưng 401/redirect login.** | Session hết hạn, URL sai matcher, authentication/routing custom. | Xem Network, logs và filter chain, không bỏ CSRF vội. |
| **SPA logout server thành công nhưng JavaScript báo CORS.** | Actual response thiếu Allow-Origin/Allow-Credentials hoặc redirect sang host khác. | Xem response POST thực, không chỉ OPTIONS. |
| **OPTIONS /logout trả 401/403.** | Proxy/auth filter chặn preflight hoặc CORS policy không cho phép. | Kiểm tra thứ tự CORS với security filters, Origin/method/headers. |
| **Cookie không có trên POST.** | credentials mode, Domain/Path/Secure/SameSite, third-party policy. | DevTools Cookies blocked reasons và URL đích. |
| **Cookie còn nhưng API đã 401.** | Session server bị invalidate, cookie jar chưa dọn. | Phân biệt browser cookie và session repository; test server state. |
| **Không xóa được cookie sau logout.** | Sai cookie name/Path/Domain hoặc servlet container. | Xem Set-Cookie thật, __Host- constraints, Clear-Site-Data nếu phù hợp. |
| **WebFlux POST logout xóa principal nhưng WebSession còn dữ liệu.** | Chưa tích hợp WebSessionServerLogoutHandler hoặc cleanup riêng. | Kiểm tra SecurityContext vs WebSession, handler composition. |
| **Logout xong lại tự login ngay.** | Remember-me, refresh token hoặc SSO session tại IdP còn hoạt động. | Phân biệt credential và policy logout. |
| **Tab B vẫn hiển thị dữ liệu sau khi tab A logout.** | UI cache/bfcache hoặc thiếu đồng bộ tab. | Gọi API mới, dọn storage, đồng bộ UI; không dựa vào hiển thị cũ. |
| **CSRF token cũ dùng lại sau logout bị 403.** | CsrfLogoutHandler xóa token hoặc session đã đổi/hết. | Lấy token mới theo flow, không tắt CSRF. |
| **GET /logout bị bot/crawler gọi.** | URL được phát hiện và tự tải. | GET không được logout, phải chỉ là confirmation/read. |
| **OIDC logout local xong IdP vẫn có session.** | Chưa thực hiện RP-initiated logout hoặc provider policy. | Phân biệt local logout/SSO logout và phạm vi thiết bị. |
| **Redirect logout tới host lạ.** | next/returnUrl hoặc Host/Forwarded không đáng tin. | Allowlist redirect, trusted proxy chain, public host config. |
| **Proxy trả 405/403 trước Spring.** | Gateway/WAF chặn method/path không nhất quán. | Kiểm tra logs theo tầng và allowlist đúng method. |
| **CSP chặn form submit hoặc fetch logout.** | form-action/connect-src của HTML frontend thiếu origin đích. | Xem CSP trên HTML document, Console, không chỉ JSON API headers. |

### 12.1. Thứ tự điều tra hữu ích

1. Xác định **method thực tế** của request logout và URL cuối sau mọi redirect.
2. Xác định **browser có gửi request chưa** hay CSP/CORS/Mixed Content chặn trước.
3. Xem **cookie phiên** có được gửi với request thực không.
4. Kiểm tra **CSRF token**, repository, trạng thái phiên và các filter đã áp dụng.
5. Nếu có OPTIONS, phân biệt **preflight** với **POST logout thực**.
6. Đọc **server logs** để biết LogoutHandler có chạy không, và repository đã invalidate session chưa.
7. Test **GET API bảo vệ bằng session ID cũ** sau logout để xác nhận quyền đã mất.
8. Xem remember-me/refresh token/IdP nếu user tự login lại.
9. Kiểm tra dọn cookie/cache/storage và đồng bộ các tab.
10. Chỉ điều chỉnh CSRF, CORS, CSP, HSTS, firewall hoặc proxy sau khi xác định đúng tầng gây lỗi.

### 12.2. HTTP firewall, proxy và HTTPS/HSTS

Khi Spring Boot đặt sau reverse proxy:

~~~text
Browser --HTTPS--> Proxy / Gateway --HTTP hoặc HTTPS nội bộ--> Spring
~~~

Lỗi logout có thể xuất hiện nếu:

- Proxy chỉ cho GET /logout nhưng chặn POST /logout hoặc OPTIONS /logout.
- HTTP firewall từ chối URL/method được mã hóa bất thường.
- Redirect URL được tạo bằng Host/X-Forwarded-Host giả.
- Header X-Forwarded-Proto không đáng tin khiến server nghĩ scheme public sai.
- Cookie Secure không được đặt hoặc browser không gửi đúng HTTPS.
- HSTS đã được browser biết làm thay đổi hành vi điều hướng HTTP→HTTPS.
- App và proxy áp dụng Content-Security-Policy hoặc CORS khác nhau trên response thực.

Cần thiết lập **trusted proxy chain**, làm sạch Forwarded/X-Forwarded-* và dùng public host allowlist. **HSTS không chống logout CSRF**; nó giúp browser dùng HTTPS theo chính sách. HTTP firewall không thay token, authorization hoặc kiểm tra session.
## 13. Bài tập tình huống

### Tình huống A — GET /logout từ liên kết ngoài

Người dùng có cookie SameSite=Lax và bấm một liên kết trên outside.test tới https://account.example.com/logout. Endpoint GET lập tức invalidate session. Đây có phải logout CSRF không?

**Đáp án:** Có thể là **logout CSRF** vì người dùng không chủ ý yêu cầu đăng xuất nhưng request GET đã kết thúc phiên. SameSite=Lax thường vẫn cho cookie trong top-level navigation GET cross-site. Cần giữ GET chỉ là trang xác nhận và yêu cầu **POST với CSRF token** cho logout thực.

### Tình huống B — GET chỉ mở trang xác nhận

GET /logout hiển thị form xác nhận; session vẫn tồn tại. Chỉ POST /logout có CSRF token hợp lệ mới invalidate session. Vậy liên kết GET tới trang này có vi phạm ngữ nghĩa HTTP không?

**Đáp án:** Không, nếu GET **không thay đổi trạng thái xác thực** mà chỉ render nội dung/CSRF token để xác nhận. Đây là cách dùng GET làm thao tác an toàn, POST làm state transition.

### Tình huống C — POST có phải tự động chống CSRF?

Ứng dụng đổi GET /logout sang POST /logout nhưng tắt CsrfFilter. Một trang ngoài tạo form POST trỏ đến endpoint. App đã chống logout CSRF tốt chưa?

**Đáp án:** Chưa. POST biểu đạt thao tác thay đổi trạng thái, nhưng **HTML form bên ngoài có thể gửi POST** trong những điều kiện phù hợp, không cần preflight. Logout session-based cần **CSRF token hợp lệ** và lớp bảo vệ khác theo threat model.

### Tình huống D — Tắt CSRF toàn site

Developer tắt CSRF để thử nghiệm API JSON. Sau thay đổi, GET /logout của Spring Security Servlet mặc định bắt đầu thực hiện logout thay vì trang xác nhận. Đó có phải kết quả cần xem xét không?

**Đáp án:** Có. Khi CSRF bị tắt, các ràng buộc mặc định của logout có thể thay đổi và làm GET trở thành logout có side effect. Phải kiểm tra lại security chain và **không tắt CSRF rộng** khi còn session/cookie browser.

### Tình huống E — HttpOnly ngăn logout CSRF?

Cookie session dùng Secure, HttpOnly và SameSite=Lax. Một lập trình viên nói website ngoài không thể đọc cookie nên không thể ép logout. Kết luận đúng không?

**Đáp án:** Không. CSRF không cần đọc cookie; browser có thể **tự gửi cookie** theo policy. HttpOnly giảm đọc session ID trực tiếp từ JavaScript, không chứng minh ý định logout.

### Tình huống F — Same-site subdomain

Website untrusted.example.com không đáng tin nhưng cùng schemeful site với api.example.com. API quyết định bỏ CSRF cho logout vì Sec-Fetch-Site: same-site. Có an toàn không?

**Đáp án:** Không. Same-site không chứng minh subdomain đáng tin. Fetch Metadata chỉ là tín hiệu bổ sung, và client ngoài browser có thể giả header. Cần CSRF protection phù hợp.

### Tình huống G — GET /logout do crawler tải

Một crawler hoặc tính năng preview truy cập GET /logout, không có người dùng bấm nút. Server vô hiệu hóa session. Tác dụng phụ này nói lên vấn đề gì?

**Đáp án:** Endpoint vi phạm **safe method semantics**. Một GET URL có thể bị truy cập vì mục đích đọc/xem trước, không nên gây thay đổi trạng thái. Crawler không nhất thiết có cookie user, nhưng thiết kế vẫn phải an toàn với GET.

### Tình huống H — GET /logout trả 200

MockMvc kiểm tra GET /logout trả 200 từ trang xác nhận. Có đủ chứng minh không tồn tại logout CSRF chưa?

**Đáp án:** Chưa. Phải **giữ cùng session qua request tiếp theo** để chứng minh GET không invalidate, và kiểm tra POST thiếu/sai CSRF không thực hiện logout. HTTP 200 không tự nói server có thay đổi trạng thái hay không.

### Tình huống I — POST thiếu token nhận 403

Browser đang đăng nhập, POST /logout thiếu _csrf trả 403. Frontend báo đây là lỗi cần sửa bằng cách tắt CSRF. Đúng không?

**Đáp án:** Không. Đây thường là hành vi đúng của **CsrfFilter**. Phải cấp token hợp lệ và gửi đúng cookie/CSRF repository. Không sửa một request thiếu token bằng cách bỏ lớp bảo vệ.

### Tình huống J — GET /logout có xác nhận nhưng SPA muốn một cú click

Đội frontend muốn một liên kết “Đăng xuất” mà chỉ cần bấm một lần. Có nên cho GET /logout thực hiện logout trực tiếp không?

**Đáp án:** Không. Dùng **button trong form POST** có CSRF token hoặc JavaScript gửi POST. Một liên kết GET có thể dẫn tới trang xác nhận; không chuyển side effect sang GET vì lý do UX.

### Tình huống K — CORS preflight thành công

Frontend gửi POST logout với X-CSRF-TOKEN, OPTIONS trả 204 cho phép origin và header. POST thực mang token sai nên trả 403. Có phải CORS thất bại?

**Đáp án:** Không. **CORS preflight thành công** không xác minh CSRF. POST thực bị từ chối vì token sai là kết quả hợp lý.

### Tình huống L — POST thành công nhưng fetch báo lỗi CORS

Server đã invalidate session và trả redirect mặc định đến HTML login; frontend fetch báo CORS error. Nên thử logout thêm nhiều lần và báo server chưa logout không?

**Đáp án:** Không. Lỗi đọc response **không chứng minh logout chưa xảy ra**. Kiểm tra actual response và session bằng GET /api/me; thiết kế success handler trả 204 cho SPA nếu phù hợp.

### Tình huống M — Cookie còn trong DevTools

POST /logout có CSRF hợp lệ đã invalidate HttpSession nhưng cookie cũ vẫn còn trong browser Storage. Có thể kết luận user chưa logout không?

**Đáp án:** Không. Cookie jar và session store độc lập. Nếu server không còn chấp nhận session ID cũ, session-based logout đã có hiệu lực; vẫn nên làm sạch cookie đúng Path/Domain để tránh confusion.

### Tình huống N — Cookie bị xóa nhưng session còn

App chỉ gửi Max-Age=0 xóa cookie mà không invalidate session server-side. Một bản sao session ID bị đánh cắp trước đó vẫn dùng được. Sai ở đâu?

**Đáp án:** Chỉ xóa client credential mà chưa thu hồi server session. Cần **invalidation tại server** để ngăn replay khi có bản sao ID.

### Tình huống O — LogoutHandler tùy chỉnh chỉ trả 204

Nhà phát triển tự viết controller POST /logout trả 204, không gọi SecurityContextLogoutHandler hay repository. Frontend đổi UI thành login. Có thực sự logout không?

**Đáp án:** Không bảo đảm. HTTP 204 là **response status**, không phải bằng chứng session đã được invalidate. Nên dùng logout DSL hoặc xử lý đầy đủ SecurityContext và session/token cleanup.

### Tình huống P — WebFlux xóa SecurityContext nhưng WebSession còn

Một ứng dụng Reactive có dữ liệu nhạy cảm trong WebSession. Logout mặc định dọn security context nhưng không invalidate toàn WebSession. Nếu yêu cầu xóa toàn bộ session thì phải làm gì?

**Đáp án:** Tích hợp **WebSessionServerLogoutHandler** cùng SecurityContextServerLogoutHandler qua DelegatingServerLogoutHandler hoặc cơ chế thích hợp, và kiểm thử session sau logout. Các token/repository riêng vẫn cần cleanup.

### Tình huống Q — JWT access token còn hiệu lực

SPA xóa JWT khỏi localStorage rồi hiển thị “Đã đăng xuất khỏi mọi thiết bị”. Một bản sao JWT bị đánh cắp vẫn có thể gọi API đến khi exp. Tuyên bố UI đúng không?

**Đáp án:** Không. Xóa localStorage chỉ ảnh hưởng một nơi lưu. Cần xác định **revocation/denylist, lifetime** và phạm vi logout thật; không tuyên bố thu hồi mọi thiết bị khi chưa có cơ chế server.

### Tình huống R — Remember-me tự đăng nhập lại

User logout HttpSession nhưng sau reload lại được xác thực bởi remember-me cookie. Có phải Spring Security không invalidate session?

**Đáp án:** Không nhất thiết. Remember-me là credential dài hạn độc lập; cần kiểm tra RememberMeServices, cleanup token repository và chính sách sau logout.

### Tình huống S — Logout app khác logout IdP

User logout khỏi app dùng OIDC nhưng mở lại login thì IdP cho vào ngay không hỏi mật khẩu. Có chứng minh app chưa logout không?

**Đáp án:** Không. App session và IdP SSO session tách biệt. Kiểm tra app session cũ đã bị invalidate chưa; nếu muốn logout IdP phải triển khai luồng được provider hỗ trợ.

### Tình huống T — OIDC back-channel logout

IdP gửi thông điệp logout server-to-server đã ký. Một developer yêu cầu CSRF form token của browser cho callback đó, rồi tắt CSRF trên toàn site khi callback lỗi. Có hợp lý không?

**Đáp án:** Không. Back-channel logout có mô hình xác thực riêng: **xác minh logout token/issuer/audience/signature/replay** theo giao thức. Nếu cần CSRF exception thì chỉ cho **đúng callback** và không tắt CSRF ở logout browser.

### Tình huống U — DELETE session không cần CSRF?

API định nghĩa DELETE /api/sessions/current, được browser gọi với cookie session. Team cho rằng DELETE idempotent nên không cần CSRF. Đúng không?

**Đáp án:** Không. Idempotency không chứng minh request do user chủ ý. DELETE là **unsafe method** về HTTP và cần CSRF protection khi dựa vào credential browser tự gửi. Endpoint cũng phải xác thực và xác định đúng session được thu hồi.

### Tình huống V — Refresh trang sau logout

Browser đã POST logout thành công, redirect tới GET /signed-out. Khi user reload trang này, ứng dụng lại gọi logout handler một lần nữa. Thiết kế có vấn đề gì?

**Đáp án:** GET trang thông báo **không nên tiếp tục có side effect**. Chỉ POST /logout thực hiện logout; GET /signed-out đơn thuần render kết quả.

### Tình huống W — POST logout ở nhiều tab

Tab A logout, tab B vẫn hiển thị hồ sơ cũ từ cache. GET /api/me mới trên tab B trả 401. Logout server thất bại không?

**Đáp án:** Không. Server đã từ chối session cũ; giao diện của tab B chưa đồng bộ. Cần dọn cached state, revalidate principal và đồng bộ UX qua cơ chế thích hợp.

### Tình huống X — Cookie SameSite=None cho đối tác

Ứng dụng có widget cross-site nên dùng SameSite=None; Secure cho session cookie. Có thể bỏ CSRF cho POST /logout vì CORS chỉ cho frontend chính thức không?

**Đáp án:** Không. Cross-site cookie có thể làm tăng bề mặt request tự mang credential. CORS không chặn mọi form POST. Giữ CSRF token hợp lệ và kiểm tra cookie policy thực tế.

### Tình huống Y — Request đi qua proxy

Proxy chặn OPTIONS /logout nhưng cho POST /logout, trong khi SPA có X-CSRF-TOKEN và cần preflight. Đội ngũ muốn bỏ header token để tránh OPTIONS. Nên xử lý thế nào?

**Đáp án:** Sửa **CORS/preflight routing** tại proxy/security filter và giữ CSRF protection. Nếu cần, dùng cơ chế gửi token trong form body hợp lệ đã được thiết kế; không bỏ xác minh CSRF chỉ để né preflight.

### Tình huống Z — Open redirect sau logout

App nhận returnTo=https://outside.test/phishing từ query và redirect tới đó sau khi logout. Rủi ro gì?

**Đáp án:** **Open redirect**, có thể tạo điều hướng lừa đảo sau một hành động nhạy cảm. Dùng path nội bộ đã kiểm tra hoặc allowlist origin/route, không chấp nhận URL tùy ý do client cung cấp.

## 14. Checklist triển khai an toàn

### 14.1. HTTP methods và CSRF

- [ ] **GET/HEAD/OPTIONS** không làm thay đổi trạng thái phiên hoặc nghiệp vụ.
- [ ] **POST /logout** là endpoint logout browser chính, yêu cầu CSRF token nếu ứng dụng dùng cookie/session.
- [ ] Không có matcher/logout controller **GET** gây invalidate session.
- [ ] GET /logout nếu có chỉ hiển thị trang xác nhận; GET /signed-out chỉ thông báo kết quả.
- [ ] Chưa tắt CSRF toàn ứng dụng để sửa lỗi 403, đặc biệt khi ứng dụng còn dùng form login/session.
- [ ] POST /logout thiếu/sai CSRF **không thay đổi session**.
- [ ] CSRF token được cấp/đọc từ repository đúng phiên, có cách tái cấp khi login/logout/session lifecycle thay đổi.
- [ ] Dùng đúng method và token với mọi endpoint thu hồi session, kể cả DELETE API được browser gọi bằng cookie.
- [ ] Không coi SameSite, CORS preflight hay Sec-Fetch-Site là phương án thay thế token theo mặc định.

### 14.2. Spring Security Servlet

- [ ] Kiểm tra **SecurityFilterChain** nào thực sự áp dụng cho /logout.
- [ ] Giữ **LogoutFilter** và các LogoutHandler cần thiết; không chỉ xóa UI/cookie ở controller.
- [ ] Session server được invalidate theo chính sách và SecurityContext được dọn.
- [ ] Remember-me cleanup được triển khai khi có remember-me.
- [ ] Xóa CSRF token cũ, xác định cách lấy token mới sau login/logout.
- [ ] Logout success URL được kiểm soát, không tạo open redirect.
- [ ] **GET /logout với CSRF bật** không thực hiện logout trong cấu hình mặc định.
- [ ] Nếu tùy chỉnh path /account/logout, frontend/template/test đều dùng đúng path.
- [ ] deleteCookies/Clear-Site-Data được kiểm tra trong browser thật và phạm vi không quá rộng.

### 14.3. Spring Security Reactive/WebFlux

- [ ] Dùng **SecurityWebFilterChain/ServerHttpSecurity**, không trộn servlet API.
- [ ] **LogoutWebFilter** nhận POST /logout và CSRF protection hoạt động.
- [ ] Token từ **ServerCsrfTokenRepository** được resolve và render đúng trong form/SPA.
- [ ] Khi yêu cầu vô hiệu hóa **toàn bộ WebSession**, cấu hình WebSessionServerLogoutHandler.
- [ ] Khi thay custom ServerLogoutHandler, kiểm tra việc dọn SecurityContext, CSRF, token store và events.
- [ ] Cookie WebSession (nếu dùng) có Secure, HttpOnly, SameSite, Path/Domain hợp lệ.
- [ ] Test WebSession/session ID cũ không còn quyền truy cập sau POST logout hợp lệ.

### 14.4. SPA và trình duyệt

- [ ] SPA gửi **POST** với CSRF token từ backend, credentials mode thích hợp.
- [ ] CORS chỉ cho **origin cụ thể**, không dùng wildcard Allow-Origin khi có credentials.
- [ ] OPTIONS được xử lý trước auth filter có thể chặn preflight, nhưng POST thực vẫn được xác minh CSRF.
- [ ] Chọn success handler trả **204/JSON** nếu frontend tự điều hướng; không nhầm fetch redirect với top-level navigation.
- [ ] Chẩn đoán lỗi mạng/CORS bằng Network và server logs trước khi kết luận trạng thái session.
- [ ] Giao diện dọn dữ liệu nhạy cảm từ các tab, storage, cache và service worker theo chính sách.
- [ ] Không log session ID, refresh token, CSRF token hoặc credential.
- [ ] Có cơ chế hiển thị danh tính/session hiện tại để tránh nhầm tài khoản sau logout và login lại.

### 14.5. Token, SSO và đa thiết bị

- [ ] Định nghĩa logout **tab, browser profile, thiết bị, tất cả thiết bị** hay toàn SSO.
- [ ] Thu hồi remember-me và refresh tokens theo chính sách thực tế.
- [ ] Với JWT, xác định liệu cần revocation/denylist, lifetime ngắn hay cơ chế tương đương.
- [ ] Phân biệt **local app session** và **IdP SSO session**.
- [ ] Dùng đúng cơ chế OIDC logout nếu cần, không mở GET /logout tùy ý.
- [ ] Back-channel logout có xác minh token/chữ ký/audience/replay riêng; mọi CSRF exception phải hẹp.
- [ ] Nhiều instance/session store đồng bộ invalidation, không chỉ xóa cache của một server.

### 14.6. Kiểm thử âm tính trước triển khai

- [ ] GET /logout **không invalidate session**.
- [ ] POST thiếu/sai CSRF bị từ chối và user vẫn đang đăng nhập.
- [ ] POST có CSRF hợp lệ làm mất quyền của session cũ.
- [ ] OPTIONS preflight **không chạy logout**.
- [ ] Origin không nằm trong allowlist **không được cấp CORS credentialed access**.
- [ ] Tab khác, browser restart, cached UI hoặc cookie tồn tại không giúp session cũ truy cập tài nguyên.
- [ ] Các token dài hạn/SSO xử lý đúng phạm vi logout đã công bố.
- [ ] Proxy, HTTP firewall, HSTS/CSP và HTTPS không làm GET logout hoặc POST logout hoạt động sai method.
- [ ] Không có open redirect hoặc lộ credential trong Location/Referer/log sau logout.
- [ ] Tất cả kết luận có chứng cứ từ **browser request thực và trạng thái session/token ở server**, không chỉ HTTP status.

## 15. Ghi nhớ

1. **Logout CSRF** là hành vi khiến browser của người dùng kết thúc phiên ngoài chủ đích. Tác động thường là gián đoạn/nhầm lẫn trạng thái, và có thể hỗ trợ kịch bản tấn công khác tùy ứng dụng.
2. **GET là HTTP safe method**, nên GET /logout không được invalidate session. Một GET **trang xác nhận** là hợp lý; **POST mới thực hiện logout**.
3. **POST không tự chống CSRF**: form HTML từ website ngoài có thể gửi POST mà không cần CORS preflight. Session-based logout phải xác minh CSRF token.
4. Trong **Spring Security Servlet với CSRF bật**, GET /logout mặc định hiển thị confirmation page, POST /logout hợp lệ mới chạy LogoutFilter. **Tắt CSRF có thể khiến GET /logout thực hiện logout ngay**.
5. **LogoutFilter/LogoutHandler** xử lý session và credential cleanup; **LogoutSuccessHandler** chỉ quyết định phản hồi sau đó. Redirect/status đẹp không chứng minh session cũ đã bị thu hồi.
6. **SameSite/HttpOnly/Secure, SOP/CORS, Origin/Referer/Fetch Metadata** là lớp bổ trợ. CORS hạn chế đọc response cross-origin, không thay CSRF hoặc authentication.
7. Với **SPA**, dùng POST kèm token và credentials đúng, CORS allowlist hẹp và response 204 nếu frontend tự điều hướng. Phân biệt **preflight** với request logout thực và kiểm tra trạng thái server khi lỗi mạng.
8. Với **WebFlux**, LogoutWebFilter và CSRF bảo vệ POST; muốn invalidate toàn **WebSession** có thể tích hợp WebSessionServerLogoutHandler cùng handler dọn SecurityContext.
9. **Logout local app, refresh token, remember-me, JWT access token và IdP SSO là các phạm vi khác nhau**. Không tuyên bố đã logout tất cả nơi nếu chỉ dọn cookie/session hiện tại.
10. **Xóa cookie không bằng thu hồi session**; cookie cũ có thể vẫn còn nhưng vô hiệu nếu server đã invalidate đúng. Cần test request dùng phiên cũ sau logout.
11. Khi xác định lỗi, kiểm tra **method, CSRF token, cookie/session, security chain, CORS actual response, CSP document, proxy và token lifecycle** theo đúng ranh giới.
12. Phép thử quan trọng nhất: **GET không đăng xuất; POST sai token không đăng xuất; POST đúng token kết thúc phiên; phiên cũ không còn truy cập được tài nguyên bảo vệ**.

## Tham khảo thêm

Các tài liệu chính thức của Spring Security cung cấp mô tả cơ chế và API theo phiên bản. Đối chiếu phiên bản framework đang dùng khi triển khai:

- [Spring Security — Servlet: Handling Logouts](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html)
- [Spring Security — Servlet: CSRF, Logging Out](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Reactive: Logout](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html)
- [Spring Security — Reactive: CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — Servlet: Testing Logout](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/logout.html)




