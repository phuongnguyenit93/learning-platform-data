# Mô hình tấn công CSRF và điều kiện trình duyệt tự gửi thông tin xác thực

> **Phạm vi:** CSRF (Cross-Site Request Forgery) trong ứng dụng Spring Security trên Servlet stack. Bài học tập trung vào cách một trang ngoài khởi phát yêu cầu mang danh tính người dùng, **điều kiện thực tế để trình duyệt tự gửi credential** và cách máy chủ kiểm tra ý định của yêu cầu.

## 1. CSRF là gì và khai thác điều gì?

**CSRF** là kiểu tấn công khiến **trình duyệt của người dùng đã xác thực** gửi yêu cầu mà người đó không chủ động mong muốn tới ứng dụng đích. Khi server chấp nhận yêu cầu chỉ vì nó mang cookie phiên hoặc credential được trình duyệt đính kèm tự động, thao tác có thể được thực hiện dưới danh tính nạn nhân.

Ví dụ: nạn nhân đang đăng nhập `https://bank.example`, rồi mở một trang do kẻ tấn công quản lý. Trang đó gây ra yêu cầu `POST https://bank.example/transfer`. Trình duyệt có thể gắn cookie phiên của `bank.example` vào yêu cầu tùy chính sách và ngữ cảnh. Nếu server kiểm tra phiên mà **không kiểm tra token CSRF hoặc bằng chứng ý định đáng tin**, server có thể thực hiện thao tác.

Cần tách ba vấn đề:

- **Authentication:** “Yêu cầu có danh tính của ai?” Cookie phiên có thể trả lời câu hỏi này.
- **Authorization:** “Danh tính đó được phép thao tác gì?” Kiểm tra quyền vẫn cần thiết.
- **CSRF protection:** “Yêu cầu thay đổi trạng thái có xuất phát từ luồng hợp lệ mà server đã chuẩn bị cho người dùng này không?”

Kẻ tấn công thường **không biết mật khẩu**, **không đọc được cookie HttpOnly** và **không cần đọc phản hồi**. Họ lợi dụng cơ chế trình duyệt mang quyền xác thực sẵn có (`ambient authority`). Tấn công chỉ đạt mục đích khi các điều kiện cần xảy ra; một form cross-site đơn lẻ không mặc nhiên thành công.

## 2. Ba chủ thể và trình tự tấn công

Giả định:

- **Ứng dụng đích:** `bank.example` có endpoint `POST /transfer`, yêu cầu phiên đã đăng nhập.
- **Nạn nhân:** người dùng đã có phiên hợp lệ trong trình duyệt.
- **Trang tấn công:** `evil.example` có thể hiển thị HTML/JavaScript tùy ý nhưng không có quyền đọc cookie hay DOM của `bank.example`.

```mermaid
sequenceDiagram
    participant V as Nạn nhân / Trình duyệt
    participant B as bank.example
    participant E as evil.example
    V->>B: Đăng nhập hợp lệ
    B-->>V: Set-Cookie: JSESSIONID=...; các thuộc tính cookie
    V->>E: Mở trang do kẻ tấn công tạo
    E-->>V: HTML có form tự submit tới bank.example
    Note over V: Browser xét host/path, Secure, SameSite, kiểu request
    V->>B: POST /transfer (cookie nếu được phép gửi)
    alt Không có bảo vệ CSRF hiệu quả
        B-->>V: Có thể thực thi nghiệp vụ dưới phiên nạn nhân
    else Có kiểm tra token CSRF
        B-->>V: Thường 403 nếu thiếu/sai token
    end
```

**Điểm quyết định:** trang độc hại tạo request; **browser** quyết định gửi credential theo cookie/chính sách; **server** quyết định request có được thực hiện. Không bên nào trong sơ đồ được phép mặc định thay cho bước kiểm tra của bên kia.

### Ví dụ form giả mạo

Đây là HTML minh họa trên miền của kẻ tấn công, với tài khoản và endpoint giả định:

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Minh họa cơ chế CSRF</title>
</head>
<body>
  <form id="request" method="POST" action="https://bank.example/transfer">
    <input type="hidden" name="to" value="attacker-account">
    <input type="hidden" name="amount" value="100">
  </form>
  <script>
    document.getElementById("request").submit();
  </script>
</body>
</html>
```

Form HTML được phép gửi request tới origin khác. Kẻ tấn công không cần gọi `document.cookie` của ứng dụng đích; nếu điều kiện cookie thỏa mãn, **browser tự đính kèm cookie của host đích**. JavaScript của trang độc hại không cần đọc HTTP response để request gây thay đổi. Tuy nhiên, nếu cookie `SameSite` bị chặn, phiên hết hạn, token CSRF thiếu hoặc server từ chối nghiệp vụ, form không đạt mục đích.

## 3. Phân biệt “origin” và “site”

**Origin** được xác định bằng bộ ba `scheme + host + port`. Hai URL khác một trong các thành phần này là khác origin. **Same-Origin Policy (SOP)** giới hạn việc trang thuộc origin này đọc nội dung và thao tác tài nguyên của origin khác. SOP **không đồng nghĩa cấm mọi HTTP request khác origin**.

**Site** phục vụ `SameSite` hiện đại (`schemeful same-site`), về cơ bản xét scheme và miền đăng ký được (`registrable domain`, thường gọi eTLD+1). Hai subdomain có thể **khác origin nhưng cùng site** nếu scheme khớp. Một số hostname đặc biệt có quy tắc khác.

| URL 1 và URL 2 | Same-origin? | Same-site? |
| --- | --- | --- |
| `https://app.example.com` và `https://app.example.com:8443` | Không: port khác | Có |
| `https://app.example.com` và `https://admin.example.com` | Không: host khác | Có |
| `http://app.example.com` và `https://app.example.com` | Không: scheme khác | Không (schemeful) |
| `https://evil.example` và `https://bank.example` | Không | Không |

**Hệ quả bảo mật:** một subdomain kém tin cậy có thể tạo request `cross-origin` nhưng `same-site`. SameSite lúc đó không nhất thiết chặn cookie. Dù cùng site, cookie vẫn phải khớp với **host/Domain, Path, Secure và ngữ cảnh đích**.

## 4. Trình duyệt tự gửi credential trong những điều kiện nào?

### 4.1. Cookie là trường hợp quan trọng nhất

Ví dụ cookie phiên ứng dụng có thể đặt khi đăng nhập:

```http
HTTP/1.1 200 OK
Set-Cookie: JSESSIONID=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=None
```

Các điều kiện liên quan:

1. Cookie **tồn tại và còn hiệu lực**; session phía server cũng còn hợp lệ. Cookie đã hết hạn/bị xóa hoặc session đã logout không thể tự xác thực request.
2. **Host/Domain:** nếu cookie không có `Domain`, thường chỉ được gửi đến host đã thiết lập cookie (`host-only`). Nếu có `Domain` hợp lệ, phạm vi host có thể rộng hơn. Cookie của `bank.example` không bị gửi tới `evil.example`; nó được browser cân nhắc khi tạo request **đến `bank.example`**.
3. **Path:** request đích phải phù hợp path scope. `Path` điều khiển việc gửi cookie, nhưng không tạo ranh giới bảo mật đáng tin giữa các ứng dụng cùng host.
4. **Secure:** cookie `Secure` chỉ được gửi trên kết nối phù hợp (thông thường HTTPS); thuộc tính này không chứng minh người dùng chủ động tạo thao tác.
5. **HttpOnly:** ngăn mã JavaScript đọc cookie qua `document.cookie`, nhưng **không ngăn browser gắn cookie vào request**. Đây là khác biệt then chốt của CSRF.
6. **SameSite:** quyết định gửi cookie trong bối cảnh cross-site nào, chịu ảnh hưởng của loại request và điều hướng.
7. **Chính sách browser:** hạn chế cookie bên thứ ba, partitioned cookies, cài đặt riêng tư và cơ chế cấp quyền truy cập cookie có thể làm kết quả thay đổi.

Một cookie phù hợp các thuộc tính trên mới là **ứng viên được gửi**; server còn phải chấp nhận nó là phiên hợp lệ. Không thể kết luận từ việc người dùng “đang mở tab đăng nhập” rằng mọi POST cross-site đều mang session.

### 4.2. SameSite=Strict, Lax, None

| Thuộc tính cookie | Cross-site form POST | Cross-site top-level GET navigation | Điểm cần nhớ |
| --- | --- | --- | --- |
| `SameSite=Strict` | Thông thường không gửi | Thông thường không gửi | Hạn chế cross-site mạnh; có thể ảnh hưởng các luồng điều hướng hợp lệ |
| `SameSite=Lax` (khai báo tường minh) | Thông thường không gửi | Có thể gửi khi điều hướng top-level bằng phương thức an toàn | GET gây thay đổi dữ liệu vẫn nguy hiểm |
| `SameSite=None; Secure` | Có thể gửi khi browser cho phép | Có thể gửi khi browser cho phép | Cần bảo vệ CSRF độc lập; không bảo đảm cookie bên thứ ba luôn được phép |

**Lưu ý ngoại lệ:** khi cookie *không khai báo* `SameSite`, một số trình duyệt mặc định áp dụng biến thể Lax linh hoạt, có thể cho phép POST top-level trong khoảng ngắn sau khi đặt cookie. Điều này khác `SameSite=Lax` khai báo rõ ràng. **Không dựa vào ngoại lệ thời gian để thiết kế bảo mật**, và kiểm chứng trên trình duyệt thực tế.

`SameSite=None` trong trình duyệt hiện đại thường yêu cầu `Secure`. Ngoài ra, chính sách chặn cookie bên thứ ba hoặc partitioning có thể hạn chế việc gửi cookie ngay cả khi `SameSite=None`. SameSite áp dụng theo **site**, vì vậy các trang subdomain cùng site có thể kích hoạt request mà cookie vẫn được gửi nếu các điều kiện khác thỏa mãn.

### 4.3. Loại request và hành vi browser

| Nguồn phát sinh | Request có thể được gửi? | Credential có tự đi kèm? |
| --- | --- | --- |
| Form HTML `method="POST"` sang origin khác | Có, với form hợp lệ | Cookie của **đích** theo quy tắc cookie, không phải cookie của trang nguồn |
| Click link / điều hướng top-level `GET` | Có | Cookie `Lax` có thể được gửi; GET phải không đổi trạng thái |
| `<img>`, `<script>`, iframe, tài nguyên nhúng | Có thể khởi phát request tải tài nguyên | Tùy ngữ cảnh, SameSite, cookie/third-party policy; không nên dùng GET gây tác dụng phụ |
| `fetch(url)` cross-origin mặc định | Có thể khởi phát theo SOP/CORS | Mặc định `credentials: "same-origin"`, nên **không gửi** cookie cross-origin theo cơ chế mặc định này |
| `fetch(url, { credentials: "include" })` | Có thể gửi nếu chính sách cho phép | Browser có thể thêm cookie phù hợp; JavaScript vẫn chịu kiểm soát CORS khi đọc response |
| `fetch` với JSON cross-origin, header không “simple” | Thường cần CORS preflight | Preflight từ chối có thể ngăn request thực tế; không suy ra mọi request đều preflight |

**Form POST** dùng các kiểu encoding thông thường như `application/x-www-form-urlencoded`, `multipart/form-data` và `text/plain`. Những kiểu request đơn giản này không nhất thiết phải qua CORS preflight. Ngay cả khi browser chặn JavaScript đọc phản hồi, request có thể **đã được server xử lý**.

### 4.4. Các cơ chế xác thực ngoài cookie

- **HTTP Basic/Digest do browser quản lý:** trình duyệt có thể nhớ và tự sử dụng credential trong phạm vi challenge/realm thích hợp. Có tự gửi trên một request cụ thể hay không còn tùy cache, challenge, origin và ngữ cảnh; không mặc nhiên đúng cho mọi request cross-site.
- **Chứng chỉ TLS client (mTLS):** credential do browser quản lý có thể được chọn/gửi ở lớp kết nối. Nếu server coi đó là xác thực tự động cho thao tác, vẫn cần đánh giá khả năng yêu cầu bị kích hoạt ngoài ý muốn.
- **Bearer token trong bộ nhớ JavaScript, chỉ được client tin cậy chủ động thêm vào header `Authorization`:** form ở origin khác không sở hữu token và không thể tự yêu cầu browser thêm header tùy ý như một cookie. Đường tấn công CSRF dựa vào ambient credential giảm, nhưng vẫn cần chống XSS và xác minh không có đường xác thực cookie song song.
- **JWT/Bearer token trong cookie:** dù gọi ứng dụng là REST API hay `stateless`, nếu browser tự gửi cookie chứa token thì CSRF vẫn là một vấn đề cần đánh giá.
- **Hệ thống có nhiều cách xác thực:** xem xét mọi credential server chấp nhận (session, remember-me, Basic, mTLS, bearer cookie), kể cả nếu tài liệu chỉ nói về một cách chính.

## 5. Điều kiện cần và đủ về mặt thực tế để CSRF gây hại

Một cuộc tấn công điển hình cần đồng thời thỏa các điều kiện:

1. **Phiên nạn nhân có hiệu lực:** có credential được server chấp nhận; nạn nhân có quyền thực hiện hành động.
2. **Kẻ tấn công kích hoạt request:** bằng form, link, điều hướng, tài nguyên nhúng hoặc cơ chế browser phù hợp; nạn nhân phải tải/tương tác với nội dung tấn công ở mức cần thiết.
3. **Request có thể mô tả thao tác:** biết endpoint, phương thức và tham số đủ dùng; tấn công không đòi hỏi đọc bí mật nếu dữ liệu đã biết hoặc dự đoán được.
4. **Browser thực sự gửi credential của đích:** cookie match host/path/transport và SameSite, hoặc cơ chế tự động khác cho phép.
5. **Server nhận request là hợp lệ và cho phép thay đổi:** không có CSRF token hợp lệ bắt buộc, hoặc cấu hình bypass sai; không có xác minh ý định bổ sung đủ mạnh.
6. **Nghiệp vụ không chặn:** phân quyền, ràng buộc giao dịch, dữ liệu đầu vào, xác thực lại hoặc chống lặp không từ chối thao tác.

Thiếu một mắt xích thì đích tấn công không đạt được. **CSRF không vượt qua authorization:** nó lợi dụng các quyền mà nạn nhân thực sự có. Một trang ngoài gửi được request cũng **không có nghĩa** kẻ tấn công đọc được phản hồi hay tự gửi được credential.

Ba câu hỏi chẩn đoán:

- Ai **khởi tạo ý định**: luồng thật của ứng dụng hay nội dung do trang ngoài điều khiển?
- Credential được **gắn bởi ai**: browser tự gửi hay mã client tin cậy chủ động thêm token bí mật?
- Server **kiểm tra gì ngoài phiên**: token CSRF, Origin/Referer, Fetch Metadata, xác nhận giao dịch và quyền nghiệp vụ?

## 6. Vì sao SOP, CORS, HttpOnly và chỉ dùng POST không đủ?

**SOP** chủ yếu là rào chắn đọc/truy cập dữ liệu giữa các origin. Nó không cấm mọi request cross-origin. Trang độc hại có thể submit form, dù không đọc được phản hồi. Việc không đọc được kết quả **không hoàn tác thay đổi đã xảy ra**.

**CORS** kiểm soát việc JavaScript cross-origin được đọc response và yêu cầu preflight cho các request nhất định. Form POST đơn giản vẫn có thể đến server. **Không khai báo CORS cho origin ngoài không tự bảo vệ endpoint trước CSRF**. Ngay cả lỗi CORS trên console cũng chưa chắc nghĩa là server chưa xử lý request.

**HttpOnly** chặn đọc cookie từ JavaScript; nó không ngăn browser tự gửi cookie. **Secure** bảo vệ vận chuyển cookie qua kết nối phù hợp; nó không chứng minh ý định. Hai thuộc tính này có giá trị bảo mật riêng, nhưng không thay thế CSRF token.

**Chỉ chuyển endpoint từ GET sang POST** là cần thiết vì GET phải “safe”, nhưng HTML form vẫn gửi POST được. Dùng GET cho thao tác xóa, chuyển tiền, thay đổi email hoặc bật/tắt cấu hình còn tạo thêm đường tấn công qua link, điều hướng và tài nguyên nhúng.

**Ẩn nút giao diện, đổi tên endpoint, tin vào AJAX hoặc kiểm tra hostname bằng chuỗi con** cũng không thay thế xác minh CSRF. Bất kỳ request có thể mô tả bằng HTTP đều phải được server kiểm tra độc lập với giao diện.

## 7. Phòng vệ trong Spring Security Servlet

Trong Spring Security 6 trên Servlet stack, cấu hình `HttpSecurity` thông thường **bật CSRF protection mặc định**. `CsrfFilter` yêu cầu token hợp lệ với các phương thức thay đổi trạng thái (ví dụ POST, PUT, PATCH, DELETE); mặc định GET, HEAD, TRACE, OPTIONS được coi là phương thức an toàn và không bắt buộc token CSRF.

Luồng xét duyệt:

1. HTTP request vào `SecurityFilterChain` trên Servlet.
2. `CsrfFilter` xác định phương thức/request có cần kiểm tra CSRF.
3. Nếu cần, filter nhận token kỳ vọng qua `CsrfTokenRepository`, so sánh với token client đưa trong form parameter hoặc header.
4. Request thiếu/sai token bị từ chối, **thường HTTP 403**, ngay cả khi browser đã đính kèm cookie phiên hợp lệ.
5. Request qua bước CSRF vẫn cần authentication, authorization và các luật nghiệp vụ khác.

Mặc định, `HttpSessionCsrfTokenRepository` lưu token CSRF trong HTTP session. Spring Security 6 sử dụng cơ chế xử lý request token có lưu ý đến BREACH, và có tải token trì hoãn. Vì vậy không nên tự suy ra rằng token lưu trong cookie giống token được render ở trang hoặc tự thay handler mặc định khi chưa hiểu luồng tích hợp.

### 7.1. Cấu hình Java 17+ minh họa

Đây là **tập tin cấu hình trong một ứng dụng Spring Boot 3.x đã có `spring-boot-starter-security`**, không phải chương trình Java độc lập có thể biên dịch bằng `javac` không kèm thư viện Spring.

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

`SecurityConfig` giữ bảo vệ CSRF mặc định vì **không gọi `csrf.disable()`**. Giả sử có controller `@PostMapping("/transfer")` trong cùng ứng dụng: request POST thiếu token sẽ bị chặn trước khi gọi handler. Một request POST có token đúng vẫn phải qua kiểm tra đăng nhập, phân quyền và dữ liệu. Cấu hình này dùng cho ứng dụng có form login; các endpoint public cũng có thể cần token CSRF nếu thay đổi trạng thái và nhận credential browser tự gửi.

### 7.2. Form hợp lệ phải mang token của server

Server render token theo thông tin từ `CsrfToken` vào form. Đây là ví dụ **HTML kết quả mong đợi**, trong đó chuỗi minh họa `TOKEN_DO_SERVER_SINH` phải là giá trị thực tế của request/phiên, không được hardcode hay tái sử dụng giữa người dùng:

```html
<form method="post" action="/transfer">
  <input type="hidden" name="to" value="trusted-recipient">
  <input type="hidden" name="amount" value="100">
  <input type="hidden" name="_csrf" value="TOKEN_DO_SERVER_SINH">
  <button type="submit">Xác nhận</button>
</form>
```

Tên tham số thường là `_csrf` nhưng nên lấy từ `CsrfToken`; tích hợp Spring MVC / template engine có thể tự thêm hidden field. **Kiểm tra HTML thực tế** để chắc chắn token đã đi theo form.

Với AJAX/SPA, ứng dụng tin cậy có thể gửi CSRF token trong header như `X-CSRF-TOKEN` hoặc `X-XSRF-TOKEN` tùy cấu hình. Nếu dùng `CookieCsrfTokenRepository` để hỗ trợ SPA, cần xử lý đúng cách client lấy token và cách Spring Security 6 resolve token (đặc biệt biểu diễn token chống BREACH và tải trì hoãn). **Cookie token chỉ có ích nếu server thực sự đối chiếu token độc lập được client gửi trong header/form**; chỉ thiết lập cookie token không chặn CSRF.

Không vô hiệu hóa CSRF chỉ vì API dùng JSON, ứng dụng không render HTML, có JWT hoặc đặt `SessionCreationPolicy.STATELESS`. Trước khi loại trừ endpoint, phải chứng minh **không đường xác thực nào của endpoint sử dụng credential được browser tự gửi**, và xem xét cả login/logout, remember-me, Basic hoặc cookie song song.

### 7.3. Defense in depth

- **SameSite hợp lý:** ưu tiên `Lax` hoặc `Strict` khi luồng hợp lệ cho phép; `None; Secure` chỉ khi cần liên thông cross-site. Vẫn giữ CSRF token cho ứng dụng dùng session cookie.
- **Origin/Referer:** đối chiếu chính xác origin tin cậy đối với request thay đổi trạng thái; có chiến lược rõ cho header bị thiếu, `null`, proxy và nguồn cùng site nhưng không tin cậy. Tránh kiểm tra bằng tìm chuỗi con trên URL.
- **Fetch Metadata:** `Sec-Fetch-Site` có thể phân biệt `same-origin`, `same-site`, `cross-site`, `none`; có thể chặn cross-site unsafe request. Cần chính sách fallback cho browser/khách HTTP không gửi header, và xem xét các subdomain cùng site.
- **Không thay đổi trạng thái bằng GET:** áp dụng cả logout có tác dụng phụ, thay đổi quyền, cập nhật hồ sơ, kích hoạt/vô hiệu tài nguyên.
- **Xác nhận lại hành động nhạy cảm:** mật khẩu, MFA hoặc cơ chế xác nhận giao dịch nếu nghiệp vụ yêu cầu. Đây là lớp bổ sung cho thao tác nguy cơ cao.
- **Bảo vệ XSS:** script chạy trong origin của ứng dụng có thể lấy token được render hoặc phát request như chính ứng dụng; CSRF token không giải quyết XSS.
- **Phân quyền và validation ở server:** kiểm tra từng request, không tin giao diện đã ẩn nút hay client đã kiểm tra đủ.

## 8. Phân tích sáu tình huống để không kết luận quá mức

**A. Cookie phiên khai báo `SameSite=None; Secure`, trang ngoài submit form POST.** Browser *có thể* gửi cookie của đích nếu Domain/Path, HTTPS và chính sách cookie cho phép. Nếu server không kiểm tra token, có nguy cơ CSRF. Nếu `CsrfFilter` yêu cầu token hợp lệ, form giả mạo bị từ chối.

**B. Cookie khai báo `SameSite=Lax`, form POST từ một site khác.** Cookie thông thường không đi cùng request. Tuy nhiên không suy ra ứng dụng miễn CSRF trong mọi tình huống: còn ngữ cảnh same-site subdomain, cấu hình cookie khác nhau và ngoại lệ Lax-by-default của cookie không khai báo SameSite.

**C. Cookie `SameSite=Lax`, endpoint `GET /delete?id=42` gây thay đổi dữ liệu.** Điều hướng top-level cross-site dạng GET có thể mang cookie. Lỗi chủ yếu ở thiết kế GET không an toàn. Di chuyển nghiệp vụ sang phương thức thay đổi trạng thái phù hợp và yêu cầu xác minh ý định.

**D. SPA chỉ dùng bearer token trong bộ nhớ và JavaScript tin cậy thêm header `Authorization`.** Form ngoài không tự có token hoặc header đó, nên đường CSRF dựa trên credential tự gửi giảm mạnh. Vẫn cần xử lý XSS, CORS và mọi đường cookie/Basic khác server chấp nhận.

**E. `https://promo.example.com` gửi POST đến `https://app.example.com`.** Khác origin nhưng có thể cùng site. SameSite cho phép cookie gắn với host/path đích nếu các điều kiện thỏa; vì thế subdomain bị chiếm quyền có thể là nguồn request không tin cậy.

**F. Browser quản lý Basic credential hoặc TLS client certificate.** Cần kiểm tra thực tế browser gắn credential vào request nào. Nếu credential mang danh tính mà không có ý định người dùng, server vẫn phải chống request giả mạo.

## 9. Cách kiểm chứng bằng môi trường thử nghiệm

Dùng **hai origin thử nghiệm tự quản lý**, một Spring Security Servlet app có endpoint POST cập nhật trạng thái giả lập và một trang gửi form ngoài. Tránh dùng hệ thống hoặc tài khoản thật.

1. Đăng nhập bằng tài khoản thử nghiệm và xác nhận session hợp lệ.
2. Mở DevTools → Application/Storage, kiểm tra host/Domain, Path, Secure, HttpOnly, SameSite của cookie.
3. Mở trang ngoài chứa form. Trong DevTools → Network xem browser **có gửi request không**, có `Cookie`/`Authorization` không, `Origin`, `Sec-Fetch-Site` và lý do cookie bị loại (nếu trình duyệt cung cấp).
4. Với CSRF protection bật, POST thiếu token có kỳ vọng **403**, kể cả khi cookie session đã đi kèm. Kiểm tra controller không chạy.
5. Từ form hợp lệ do ứng dụng render với token đúng, xác nhận POST được xử lý khi đã đăng nhập và có quyền.
6. Thử `Strict`/`Lax`/`None`, cross-site POST và top-level GET, request từ subdomain cùng site, `fetch` mặc định và `credentials: "include"`. Ghi lại browser phiên bản, chính sách cookie và kết quả, tránh khẳng định một quy tắc tuyệt đối cho mọi trình duyệt.

| Request | Credential thực sự đi kèm? | Token CSRF | Kết quả mong đợi |
| --- | --- | --- | --- |
| Form ngoài POST đến app, cookie được phép gửi | Có | Thiếu/sai | 403 với CSRF filter hoạt động |
| Form hợp lệ của app, session và quyền đúng | Có | Đúng | Qua kiểm tra CSRF và nghiệp vụ được xử lý |
| Form ngoài POST, cookie bị SameSite chặn | Không | Thiếu | Không thể thực hiện dưới session nạn nhân |
| Cross-site top-level GET với cookie Lax | Có thể | Không yêu cầu cho GET mặc định | An toàn chỉ khi GET không gây thay đổi trạng thái |

**Không dùng `curl` để chứng minh SameSite sẽ gửi hay không gửi cookie trong trình duyệt.** Công cụ dòng lệnh có thể tạo yêu cầu mang cookie tùy ý, nhưng không mô phỏng đầy đủ site context, top-level navigation, SameSite, third-party cookie policy và CORS của browser. `curl` chỉ có thể hỗ trợ kiểm tra kết quả HTTP/CSRF phía server theo cookie/token được cấp thủ công.

## 10. Lỗi tư duy thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Cookie có HttpOnly nên không thể CSRF.” | Browser vẫn tự gửi cookie dù script không thể đọc cookie. |
| “SOP/CORS chặn origin lạ gửi POST.” | Form và một số request vẫn tới server; bị cấm đọc response không có nghĩa server chưa thực hiện thay đổi. |
| “Mọi request cross-site đều mang phiên.” | Phải thỏa Domain/Path, Secure, SameSite, loại request, chính sách browser và phiên còn hiệu lực. |
| “Same-origin giống Same-site.” | Khác nhau; subdomain khác origin có thể cùng site. |
| “Chỉ cần dùng POST thay GET.” | Form ngoài vẫn gửi được POST; token CSRF và kiểm tra nghiệp vụ là thiết yếu. |
| “JWT, API hoặc stateless thì không cần CSRF.” | Nếu cookie hoặc credential tự gửi còn được server chấp nhận, nguy cơ vẫn còn. |
| “CSRF token thay thế authorization.” | Không. Token chỉ hỗ trợ kiểm chứng request; quyền và ràng buộc nghiệp vụ vẫn phải kiểm tra. |
| “Bị 403 nghĩa là browser không gửi cookie.” | Có thể cookie đã gửi, và chính token CSRF thiếu/sai khiến Spring Security trả 403. |

### Ghi nhớ mô hình

**Trang ngoài tạo request → browser xét có gắn credential hay không → server kiểm tra authentication, CSRF token và authorization → nghiệp vụ quyết định có thay đổi trạng thái.** Để đánh giá nguy cơ chính xác, phải kiểm chứng *cả hai phía*: hành vi gửi credential của **trình duyệt** và cơ chế chấp nhận yêu cầu của **máy chủ**. Trong ứng dụng Spring Security Servlet dùng session cookie, hãy giữ CSRF protection, chỉ dùng GET cho thao tác an toàn, đặt cookie phù hợp và bổ sung kiểm tra Origin/Fetch Metadata khi cần.
