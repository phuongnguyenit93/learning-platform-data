# Login CSRF và ràng buộc hành động đăng nhập

## Mục tiêu bài học

Khi nhắc đến **Cross-Site Request Forgery (CSRF)**, ví dụ thường gặp là một trang ngoài cố khiến browser của người dùng đã đăng nhập thực hiện thao tác chuyển tiền hoặc đổi mật khẩu. Tuy nhiên, **đăng nhập cũng là hành động thay đổi trạng thái xác thực**. Ngay cả trước khi người dùng được xác thực, một yêu cầu **POST /login** thiếu ràng buộc có thể tạo ra phiên **không phải phiên mà người dùng chủ ý chọn**. Đây là tình huống **login CSRF**.

Bài thuộc chương **Đăng nhập và đăng xuất** của module **SPRING_SECURITY_HTTP_PROTECTION**: áp dụng các lớp phòng vệ HTTP và trình duyệt trong Spring Security — từ CSRF, CORS, security headers, CSP, HSTS, HTTP firewall đến session protection — trên cả **Servlet/Spring MVC** và **Reactive/Spring WebFlux**.

Sau bài học, bạn có thể:

1. Giải thích **login CSRF** là gì, vì sao nó khác với CSRF trên một request nghiệp vụ đã đăng nhập và khác với **session fixation**.
2. Mô tả một kịch bản browser bị đưa vào **tài khoản mà attacker kiểm soát** và hậu quả về quyền riêng tư, ghi dữ liệu, nhầm danh tính.
3. Thiết kế luồng **GET trang đăng nhập → cấp CSRF token trước xác thực → POST /login kèm token → xác thực → tạo/đổi session → redirect an toàn**.
4. Hiểu rõ **permitAll không đồng nghĩa bỏ CSRF**, **SameSite/CORS không thay thế CSRF** và những giới hạn của **Origin/Referer/Fetch Metadata**.
5. Cấu hình **Spring Security 6.x** với **HttpSecurity** và **ServerHttpSecurity**, bảo vệ form login, custom login và SPA login.
6. Ràng buộc đăng nhập liên kết **OAuth2/OIDC** bằng **state, PKCE, nonce, redirect URI và kiểm tra issuer/audience** theo đúng vai trò từng cơ chế.
7. Kiểm thử request thiếu/sai token, login thành công, session fixation, logout, OAuth callback lỗi và lỗi proxy/cookie trong môi trường thực tế.

## 1. Login CSRF là gì?

**Login CSRF** là một dạng CSRF nhằm **tạo hoặc thay đổi trạng thái đăng nhập của browser** mà người dùng không chủ ý phê chuẩn. Khác với các ví dụ CSRF truyền thống, nạn nhân **không nhất thiết phải đăng nhập trước**.

Ví dụ điển hình: kẻ tấn công có một tài khoản hợp lệ tại ứng dụng và tìm cách khiến browser của nạn nhân gửi yêu cầu đăng nhập **bằng tài khoản của chính kẻ tấn công**. Nếu ứng dụng chấp nhận POST login từ trang ngoài mà không có cơ chế chống CSRF thích hợp, browser nạn nhân có thể kết thúc với session thuộc về tài khoản attacker.

### 1.1. Kịch bản có thể xảy ra

Giả sử:

~~~text
Ứng dụng:          https://shop.example.com
Website ngoài:     https://outside.test
Tài khoản attacker: attacker-account
Tài khoản nạn nhân: victim-account (hoặc nạn nhân chưa đăng nhập)
~~~

Một chuỗi diễn biến:

1. Attacker có credential hợp lệ của **attacker-account** tại shop.example.com.
2. Nạn nhân truy cập website outside.test.
3. Website ngoài kích hoạt một biểu mẫu **POST /login** chứa credential của attacker-account.
4. Nếu endpoint không kiểm tra nguồn/CSRF và browser tiếp nhận cookie phiên được trả về, trạng thái đăng nhập ở shop.example.com có thể đổi sang **attacker-account**.
5. Nạn nhân quay lại shop.example.com, thấy giao diện đang đăng nhập nhưng **không nhận ra tài khoản không phải của mình**.
6. Nạn nhân thực hiện hành động như thêm địa chỉ, lưu số điện thoại, tải lên tài liệu, ghi nội dung nháp hoặc lưu thông tin giao dịch **vào tài khoản attacker-account**.
7. Attacker đăng nhập lại bằng tài khoản của mình và có thể đọc những dữ liệu đã bị ghi vào tài khoản đó, tùy chức năng và phân quyền ứng dụng.

Đây là **một kịch bản minh họa để phân tích phòng vệ**. Khả năng thành công phụ thuộc vào endpoint, session/cookie policy, bối cảnh browser và các lớp kiểm tra khác. Không phải mọi browser và ứng dụng có cùng hành vi Set-Cookie/điều hướng.

### 1.2. Điều gì khiến tình huống này nguy hiểm?

Attacker **không cần biết mật khẩu của nạn nhân**. Mục tiêu có thể là:

- Gây **nhầm lẫn danh tính**: người dùng tưởng đang làm việc trong tài khoản của mình.
- Khiến người dùng vô tình nhập dữ liệu riêng tư vào **tài khoản attacker kiểm soát**.
- Trộn dữ liệu hoặc trạng thái ứng dụng như lịch sử tìm kiếm, cấu hình, giỏ hàng, địa chỉ, tệp tải lên.
- Gây vấn đề liên kết tài khoản, đăng nhập liên kết hoặc liên kết một định danh bên ngoài vào tài khoản không mong muốn nếu flow thiếu ràng buộc.
- Làm hỏng các giả định về **ý định của user**: “browser đã có session” không chứng minh người dùng đã chọn danh tính trong session đó.

Đây không đơn thuần là lỗi giao diện hiển thị tên sai; đó là việc **trạng thái bảo mật được thay đổi qua một yêu cầu không được ràng buộc với luồng hợp lệ**.

### 1.3. Sơ đồ sequence

~~~mermaid
sequenceDiagram
    participant A as Attacker tại outside.test
    participant B as Browser nạn nhân
    participant S as Ứng dụng shop.example.com
    A->>B: Trang ngoài dẫn tới form POST /login
    B->>S: POST /login với credential của attacker
    Note over B,S: Chỉ thành công nếu thiếu các kiểm tra cần thiết
    S->>S: Xác thực attacker-account
    S-->>B: Set-Cookie/session cho attacker-account
    B->>S: User mở trang và nhập dữ liệu riêng tư
    S->>S: Lưu dữ liệu vào attacker-account
    Note over A,S: Attacker có thể xem dữ liệu của tài khoản mình
~~~

Điểm cần bảo vệ là **liên kết giữa browser, luồng đăng nhập đã được khởi tạo hợp lệ và danh tính kết quả**.

## 2. Phân biệt login CSRF với các lỗi gần giống

| Mối nguy | Attacker kiểm soát hoặc tác động gì? | Hậu quả đặc trưng | Phòng vệ chính |
| --- | --- | --- | --- |
| **Login CSRF** | Browser bị kích hoạt login không chủ ý; có thể dùng credential của attacker. | Nạn nhân nhận session của tài khoản không mong muốn. | CSRF token trước login; ràng buộc flow; kiểm tra nguồn bổ sung; OAuth state. |
| **CSRF nghiệp vụ** | Browser đã có session, attacker kích hoạt POST/PUT/PATCH/DELETE. | Thao tác trái ý user trên tài khoản đang xác thực. | CSRF token, phân quyền, SameSite bổ trợ, đúng HTTP method. |
| **Session fixation** | Attacker khiến browser sử dụng session ID đã biết hoặc được lựa chọn trước, rồi nạn nhân đăng nhập. | Attacker có thể lợi dụng ID còn hiệu lực sau khi user xác thực. | Rotate/change session ID khi auth, bảo vệ cookie/session store. |
| **Session hijacking** | Attacker đánh cắp session ID/token hợp lệ của nạn nhân. | Sử dụng trực tiếp phiên của nạn nhân. | HTTPS, Secure/HttpOnly, session revocation, giảm XSS, phát hiện rủi ro. |
| **Credential stuffing** | Attacker thử username/password đã lộ trên login endpoint. | Đăng nhập trực tiếp bằng credential của user. | Rate limiting, MFA, bảo vệ credential và phát hiện abuse. |
| **Login phishing** | User bị dẫn đến trang đăng nhập giả. | Lộ mật khẩu/token hoặc bị lừa xác nhận đăng nhập. | Kiểm soát origin, UX tin cậy, phishing-resistant MFA. |
| **OAuth login CSRF** | Authorization response/callback bị tráo hoặc không khớp request của browser. | Liên kết hoặc đăng nhập sai tài khoản. | state được ràng buộc với authorization request; kiểm tra callback; PKCE/nonce phù hợp. |
| **Open redirect sau login** | Attacker điều khiển URL chuyển hướng sau login. | Phishing hoặc làm lộ dữ liệu qua URL, mất kiểm soát luồng. | Allowlist redirect, chỉ dùng path nội bộ đã kiểm tra. |

Các lỗi có thể **xuất hiện đồng thời**, nhưng một giải pháp cho lỗi này không nhất thiết chặn lỗi khác. Ví dụ **đổi session ID sau login** giúp chống fixation nhưng không tự phát hiện việc browser đăng nhập vào tài khoản của attacker.

### 2.1. Login CSRF không cần “đánh cắp cookie”

Ở login CSRF, attacker thường muốn **browser của nạn nhân tự nhận session cho tài khoản attacker**, thay vì lấy session ID hiện tại của nạn nhân. Vì vậy chỉ thêm HttpOnly vào cookie không giải quyết nguyên nhân.

### 2.2. Session fixation không phải login CSRF

Một ứng dụng có thể đổi session ID khi đăng nhập nhưng vẫn xử lý một POST /login không có CSRF token. Khi đó:

~~~text
Browser bị ép POST /login bằng credential của attacker
   → server xác thực attacker-account
   → server tạo/đổi session ID rất an toàn
   → browser vẫn đăng nhập sai tài khoản
~~~

Session ID đã được bảo vệ trước fixation, nhưng **ý định chọn danh tính vẫn không được xác minh**.

Ngược lại, CSRF token hợp lệ ở login không bảo đảm server đã rotate session ID. Phải thiết kế **cả hai**.

## 3. Vì sao một form HTML bên ngoài có thể gửi login request?

**Same-Origin Policy (SOP)** hạn chế JavaScript của một origin đọc DOM/response của origin khác. Nhưng SOP không ngăn mọi **điều hướng, biểu mẫu HTML và tài nguyên nhúng** tạo request cross-origin.

Ví dụ cấu trúc biểu mẫu sau minh họa một **mẫu request có rủi ro** nếu login endpoint không có CSRF protection:

~~~html
<form action="https://shop.example.com/login" method="post">
  <input type="hidden" name="username" value="attacker-account">
  <input type="hidden" name="password" value="ATTACKER_OWN_TEST_PASSWORD">
  <button type="submit">Continue</button>
</form>
~~~

Một form POST thông thường có thể dùng **application/x-www-form-urlencoded**, thuộc các loại request có thể được gửi mà **không cần CORS preflight**. Trình duyệt có thể đưa response vào một lần điều hướng. Website ngoài không cần được CORS cho phép đọc response để một hành động server-side đã xảy ra.

Trong môi trường thực tế, attacker không nhất thiết kiểm soát mật khẩu nạn nhân: họ có thể sử dụng credential của **tài khoản họ sở hữu** khi đánh giá login CSRF.

### 3.1. CORS không phải cơ chế bảo vệ login

CORS trả lời: **mã JavaScript thuộc origin nào được browser cho phép đọc response cross-origin và thực hiện các request thuộc phạm vi CORS?**

Nó **không** trả lời: “Đây có phải login mà user chủ ý thực hiện không?”

Một browser có thể gửi một form không preflight, server có thể nhận và xử lý POST, rồi website ngoài vẫn không đọc được response vì SOP/CORS. **Hành động thay đổi trạng thái đã có thể hoàn tất trước bước quyết định quyền đọc**.

Không khắc phục login CSRF chỉ bằng:

~~~http
Access-Control-Allow-Origin: https://shop.example.com
~~~

Header trên có thể là một phần chính sách CORS, nhưng **không ràng buộc yêu cầu login với một session/luồng đã được trang login chính thức khởi tạo**.

### 3.2. SameSite và cookie ở giai đoạn login

Cookie SameSite=Strict/Lax có thể làm giảm việc **cookie hiện có** được gửi trong nhiều request cross-site. Tuy nhiên login CSRF có điểm đặc biệt: request login **có thể dẫn tới việc server tạo hoặc thay đổi cookie phiên mới**, nên không thể dùng câu “cookie phiên cũ không được gửi” để kết luận an toàn.

Tùy loại điều hướng, xử lý Set-Cookie, chính sách third-party cookies và browser, kết quả có thể khác nhau. Với callback đăng nhập qua IdP, **top-level navigation GET** còn có thể mang cookie SameSite=Lax. Các chính sách cookie cũng thay đổi theo phiên bản browser.

**Kết luận thiết kế:** SameSite là lớp bổ trợ, không thay **CSRF token/state và kiểm tra luồng**.

### 3.3. Request Content-Type và custom header

Với một SPA login tự xây dựng, mã frontend có thể dùng JSON:

~~~javascript
await fetch("https://shop.example.com/login", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    username: "learner",
    password: "example-only"
  })
});
~~~

**Cảnh báo:** Bộ lọc form login mặc định của Spring Security thường mong đợi **form parameters username/password**, không tự đọc JSON body theo mẫu trên. Nếu muốn JSON login, ứng dụng phải xây dựng cơ chế authentication thích hợp và giữ CSRF/điều kiện session tương ứng.

Việc application/json thường kích hoạt **CORS preflight** khi fetch cross-origin không phải bằng chứng login đã được ràng buộc. Các endpoint có thể vẫn chấp nhận form POST, hoặc có những request không phải Fetch/XHR.

## 4. Nguyên tắc đúng: login là một chuyển đổi trạng thái nhạy cảm

Một luồng form login dùng cookie/session nên được xem là **state transition**:

~~~text
Trước login:
  Anonymous session / request context
  ↓
GET /login:
  Hiển thị form hợp lệ, browser nhận CSRF token do server cấp
  ↓
POST /login:
  Browser gửi credential + CSRF token của luồng hợp lệ
  ↓
Spring Security:
  Validate CSRF → xác thực credential → xử lý session fixation
  ↓
Sau login:
  Session gắn với principal đúng; CSRF token thay đổi/tái cấp khi phù hợp
  ↓
Browser:
  Kiểm tra user hiện tại và tiếp tục tới đích được kiểm soát
~~~

Điều quan trọng là **CSRF token cần sẵn sàng trước khi người dùng đăng nhập**. Cơ chế cấp CSRF token không nên yêu cầu người dùng đã xác thực, bởi mục đích của nó là bảo vệ chính yêu cầu đăng nhập ban đầu.

### 4.1. GET /login và POST /login có nhiệm vụ khác nhau

| Endpoint | Mục đích | Phòng vệ quan trọng |
| --- | --- | --- |
| **GET /login** | Hiển thị form/login UI, nhận token hoặc điều hướng bắt đầu flow. | Response an toàn, CSP, anti-clickjacking, HTTPS, không để dữ liệu nhạy cảm trong URL. |
| **POST /login** | Xác thực credential và thay đổi session/principal. | **CSRF token**, kiểm tra credential, session fixation protection, rate limiting, redirect hợp lệ. |
| **GET /login?error** | Hiển thị trạng thái lỗi an toàn. | Không phản chiếu input chưa escape, không lộ dữ liệu nhạy cảm. |
| **POST /logout** | Vô hiệu hóa session/credential theo chính sách. | CSRF token, invalidate session, xóa cookie đúng phạm vi. |
| **OAuth2 authorization callback** | Kết thúc flow đăng nhập liên kết. | **state** và các kiểm tra giao thức, không suy ra chỉ từ HTTP method. |

Một số giao thức đăng nhập liên kết sử dụng callback **GET** và vẫn tạo session. Đây là **ranh giới riêng được bảo vệ bằng state và kiểm tra OAuth2/OIDC**, không nên mở một GET endpoint tùy ý để đăng nhập user chỉ vì GET không cần CSRF token theo matcher mặc định.

### 4.2. Login phải xác nhận danh tính kết quả

Sau khi xác thực thành công, ứng dụng nên hiển thị **danh tính và ngữ cảnh đang hoạt động**, nhất là khi có nhiều tài khoản hoặc nhiều tenant:

- Tên/định danh account đã đăng nhập, tổ chức hoặc workspace.
- Cảnh báo khi user chuyển sang một account không mong đợi nếu UX có nhiều danh tính.
- Bước xác nhận lại hoặc **step-up authentication** đối với hành động đặc biệt nhạy cảm.
- Luồng đổi tài khoản rõ ràng, không tự động ghi dữ liệu riêng tư vào một account vừa thay đổi ngoài ý định.

Các biện pháp UX là **phòng vệ bổ sung**, không thay kiểm tra CSRF trước login hoặc authorization ở server.

## 5. Thiết kế CSRF token cho giai đoạn chưa đăng nhập

### 5.1. CSRF token không phải một password khác

CSRF token là giá trị bảo mật được ứng dụng cấp/kiểm tra để phân biệt một request đi qua luồng hợp lệ với request được website ngoài tự dựng. Nó không chứng minh tài khoản có quyền, không thay MFA và không cho phép bỏ kiểm tra mật khẩu.

Trong ứng dụng Servlet session-based, Spring Security thường sử dụng cơ chế liên kết token với session/repository. Khi login hoàn thành, session có thể được đổi ID và CSRF token có thể được làm mới theo chiến lược bảo vệ.

### 5.2. Token phải được lấy từ trang hoặc endpoint hợp lệ

Với form HTML do chính ứng dụng phục vụ:

~~~html
<form method="post" action="/login">
  <label for="username">Tài khoản</label>
  <input id="username" name="username" autocomplete="username">

  <label for="password">Mật khẩu</label>
  <input id="password" name="password" type="password"
         autocomplete="current-password">

  <input type="hidden" name="_csrf"
         value="TOKEN_DO_SPRING_SECURITY_CAP">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Giá trị TOKEN_DO_SPRING_SECURITY_CAP **chỉ là placeholder** trong tài liệu. Server phải tạo và kiểm tra token thực, không hard-code một chuỗi cố định trong mã HTML đã phát hành.

Các template engine tích hợp Spring MVC/Spring Security có thể tự chèn hidden field cho form POST; cần xác minh output HTML thực để tránh vừa thiếu vừa chèn trùng token.

### 5.3. Token trước login có thể tạo session ẩn danh

Một browser chưa đăng nhập có thể nhận cookie session ẩn danh khi GET /login tạo/ghi CSRF token. Điều này **không có nghĩa người dùng đã được xác thực**.

~~~text
GET /login
  → CSRF repository phát hoặc lưu token
  → browser có thể nhận session cookie của trạng thái ẩn danh

POST /login + token
  → CSRF filter kiểm tra token
  → Authentication filter kiểm tra mật khẩu
  → Session được thay đổi/định danh lại theo chính sách
~~~

Với Spring Security hiện đại, token có thể được tạo theo cơ chế **deferred/lazy**. Nếu frontend dùng trang login tùy chỉnh, phải bảo đảm token được **truy xuất/render** hoặc endpoint cấp token thực sự kích hoạt tạo token cần thiết. Không suy ra token luôn đã nằm trong session chỉ vì middleware CSRF đang bật.

### 5.4. Token phải gắn với ngữ cảnh phù hợp

Các yêu cầu thiết kế quan trọng:

1. **Khó đoán** và được tạo bằng cơ chế đáng tin của framework.
2. **Có phạm vi/quan hệ với phiên hoặc cơ chế repository** theo mô hình bảo vệ.
3. **Được kiểm tra ở server** khi xử lý POST /login; không chỉ kiểm tra tên field hiện diện.
4. **Không để lộ** qua URL, access log, analytics, Referer hoặc gửi đến website không đáng tin.
5. **Được tái cấp/điều chỉnh sau login/logout** nếu session/token lifecycle yêu cầu.
6. **Không dùng token của một phiên** cho một phiên mới rồi coi đó là lỗi CORS; phải điều tra token repository và session đúng.
7. **Không cache công khai** phản hồi chứa token cá nhân của người dùng.

Lưu ý Spring Security 6 sử dụng xử lý token có thể **mask token trả cho browser** để giảm rủi ro BREACH; đừng tự so khớp hai chuỗi token trong JavaScript rồi suy ra server đúng/sai. Luồng token phải tương thích với repository và handler được cấu hình.

### 5.5. CSRF token và password reset/MFA khác nhau

- CSRF token nhằm bảo vệ **request/state transition** khỏi bị khởi tạo ngoài luồng.
- Password reset token nhằm chứng minh quyền truy cập **kênh khôi phục** theo hợp đồng, thường có lifetime và one-time use riêng.
- OTP/MFA/WebAuthn giúp tăng bảo đảm về **danh tính hoặc xác thực**.
- OAuth2 state gắn **authorization response** với một login flow.
- OIDC nonce giúp liên kết **ID token** với authorization request theo những trường hợp yêu cầu.

Không dùng một loại token thay thế bừa bãi cho loại còn lại.

## 6. Spring Security Servlet: bảo vệ form login mặc định

Trong **Spring Security 6.x, Spring MVC/Servlet**, CSRF protection được bật theo cấu hình mặc định trừ khi bạn đã thay đổi. Mặc định Spring Security thường yêu cầu token cho các method unsafe như **POST/PUT/PATCH/DELETE** và không yêu cầu CSRF token cho **GET/HEAD/TRACE/OPTIONS**.

Vì đăng nhập bằng form dùng **POST /login**, nó thuộc nhóm request cần CSRF token. Điều này đúng **ngay cả khi user chưa đăng nhập**.

### 6.1. Cấu hình SecurityFilterChain cơ bản

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class FormLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation.changeSessionId()))
                .logout(logout -> logout
                        .invalidateHttpSession(true))
                .build();
    }
}
~~~

Giải thích từng thành phần:

- **formLogin(Customizer.withDefaults())** dùng form login của Spring Security, bao gồm đường dẫn xử lý login theo cấu hình mặc định. Nếu chưa cấu hình custom login page, Spring Security có thể cung cấp trang login mặc định.
- **csrf(Customizer.withDefaults())** giữ CSRF protection, bao gồm POST /login; không phải một lệnh “bỏ qua login”.
- **sessionFixation(changeSessionId())** làm rõ ý định đổi session ID khi login thành công trong Servlet container hỗ trợ, chống fixation.
- **logout(invalidateHttpSession(true))** yêu cầu vô hiệu hóa HttpSession theo cơ chế logout, không chỉ sửa trạng thái UI.
- **authorizeHttpRequests** quản lý quyền truy cập tài nguyên; việc GET /login được phép với anonymous không đồng nghĩa POST /login được bỏ CSRF.

Bật CSRF không đủ nếu trang login tùy chỉnh **không gửi token**, hoặc nếu ứng dụng đã thêm filter chain khác bỏ CSRF cho /login. Cần kiểm tra thực tế filter chain áp dụng cho endpoint.

### 6.2. permitAll chỉ xử lý authorization

Giả sử có cấu hình:

~~~java
.formLogin(form -> form
        .loginPage("/login")
        .loginProcessingUrl("/login")
        .permitAll())
~~~

**permitAll()** cho phép browser chưa được xác thực truy cập login page và xử lý login theo quyền được thiết lập; **nó không làm CsrfFilter bỏ kiểm tra POST /login**.

Đây là khác biệt quan trọng:

~~~text
POST /login
    ↓
CSRF filter: token có hợp lệ không?
    ↓
Authentication filter: username/password có đúng không?
    ↓
Session strategy: đổi/thiết lập phiên theo cấu hình
    ↓
Success/failure handler: phản hồi hoặc redirect hợp lệ
~~~

Thứ tự tổng thể trong từng filter chain có thể bao gồm thêm filter khác; sơ đồ nhấn mạnh **CSRF là một điều kiện tách biệt với quyền anonymous và xác thực mật khẩu**.

### 6.3. Trang login tùy chỉnh với Thymeleaf

Nếu chọn custom page, ví dụ Spring MVC controller:

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

Và template **login.html** dùng Thymeleaf tích hợp Spring MVC:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập</title>
</head>
<body>
  <form th:action="@{/login}" method="post">
    <label for="username">Tài khoản</label>
    <input id="username" name="username" autocomplete="username">

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password"
           autocomplete="current-password">

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
~~~

Với **Thymeleaf/Spring MVC integration**, form có **th:action** và method POST thường được Spring Security/Spring MVC hỗ trợ chèn hidden CSRF parameter qua **RequestDataValueProcessor**. **Cần xem HTML được render thật** và bảo đảm hidden field xuất hiện đúng tên/giá trị. Không vừa dựa vào auto-insert vừa chèn thêm trường thủ công mà không biết có trùng lặp hay không.

Nếu tự render HTML không qua integration này, bạn có thể phải cấp token từ CSRF request attribute và thêm hidden field phù hợp:

~~~html
<!-- Phương án minh họa khi tự quản lý CSRF field. -->
<input type="hidden"
       name="_csrf"
       value="TOKEN_DO_SERVER_CAP">
~~~

Giá trị trong ví dụ chỉ là placeholder, không dùng trong production. Với form HTML có content type thông thường, Spring Security mặc định có thể lấy token từ **request parameter** hoặc header theo cấu hình.

### 6.4. Trường hợp login bị 403 trước khi kiểm tra mật khẩu

Nếu trang hiển thị bình thường nhưng POST /login bị **403**, đừng kết luận mật khẩu sai. Kiểm tra:

1. Form có trường **_csrf** hoặc header CSRF đúng với cấu hình không?
2. Trường đó chứa token được server cấp cho **đúng browser/session** không?
3. Cookie session dùng để lưu/đọc token có được gửi ở POST không?
4. Token có hết hiệu lực do login/logout/session rotation hoặc server restart không?
5. Có **load balancer** chuyển request giữa hai session store không đồng bộ không?
6. Request POST có vào đúng SecurityFilterChain đang bật CSRF không?
7. Lỗi thực có do **CSRF** hay một bộ lọc khác trả 403? Xem log để xác minh.

Nếu không có token, Spring Security có thể từ chối trước khi UsernamePasswordAuthenticationFilter kiểm tra mật khẩu; điều này là **đúng mục đích bảo vệ login CSRF**.

### 6.5. Session cookie production

Ví dụ thuộc tính Spring Boot 3.x cho Servlet session trong môi trường HTTPS:

~~~yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        name: __Host-APPSESSION
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

**__Host-** yêu cầu Secure, Path=/ và không có Domain khi cookie được tạo. Cookie này phải được kiểm chứng qua DevTools ở môi trường triển khai thực. Giá trị **30m** là idle timeout ví dụ, không phải thời hạn tuyệt đối hoặc chính sách cố định.

Secure/HttpOnly/SameSite là những lớp bảo vệ session quan trọng. Nhưng **không thuộc tính nào tự chứng minh người dùng chủ ý chọn tài khoản khi login**. CSRF token và các kiểm tra flow vẫn cần thiết.

## 7. SPA login khác origin: token trước login, cookies và CORS

Nếu frontend HTML ở **https://app.example.com**, còn login backend ở **https://api.example.com**, bạn có ít nhất hai origin. CORS, cookie và CSRF cần thiết kế **ngay tại giai đoạn anonymous**.

### 7.1. Đường đi tổng quan

~~~mermaid
sequenceDiagram
    participant SPA as SPA app.example.com
    participant B as Browser
    participant API as Spring API api.example.com
    SPA->>B: Khởi tạo trang login
    B->>API: GET /csrf (credentials include)
    API-->>B: CSRF token + session cookie nếu cần
    B-->>SPA: Token nếu actual response có CORS đúng
    SPA->>B: User gửi username/password
    B->>API: OPTIONS preflight (nếu có custom header)
    API-->>B: CORS policy hợp lệ
    B->>API: POST /login + form fields + CSRF token + cookie
    API->>API: Kiểm tra CSRF, xác thực, session fixation
    API-->>B: Thành công/thất bại theo hợp đồng, Set-Cookie nếu phù hợp
    B->>API: GET /api/me bằng cookie mới
    API-->>SPA: User identity nếu CORS, auth, quyền hợp lệ
~~~

Trong sơ đồ, GET /csrf không đòi user đã login, nhưng có thể cần cookie phiên **anonymous** cho repository. **CORS phải cho phép GET /csrf và POST /login**, không chỉ /api/**.

### 7.2. Expose token trong Spring MVC

Một ví dụ endpoint sử dụng CsrfToken do Spring Security cung cấp:

~~~java
import java.util.Map;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PreLoginCsrfController {

    @GetMapping("/csrf")
    Map<String, String> csrf(CsrfToken csrfToken) {
        return Map.of(
                "headerName", csrfToken.getHeaderName(),
                "parameterName", csrfToken.getParameterName(),
                "token", csrfToken.getToken());
    }
}
~~~

Với repository/handler phù hợp, việc truy cập **getToken()** làm rõ nhu cầu lấy giá trị token được server cấp. Phải đánh giá cơ chế **deferred token**, biểu diễn token để giảm BREACH và token rotation theo phiên bản Spring Security đang dùng.

**Endpoint này cần được gọi từ một frontend đã được CORS cho phép**. Không mở đọc response token cho mọi origin với credentials. Phản hồi token cần tránh cache công khai; không log token và không đưa token vào URL.

### 7.3. Cấu hình Servlet cho SPA login

Một cấu hình minh họa với Spring Security 6.x:

~~~java
import java.util.List;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class SpaLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/csrf").permitAll()
                        .requestMatchers("/assets/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form
                        .loginProcessingUrl("/login")
                        .successHandler((request, response, authentication) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT))
                        .failureHandler((request, response, exception) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED))
                        .permitAll())
                .csrf(Customizer.withDefaults())
                .sessionManagement(session -> session
                        .sessionFixation(fixation -> fixation.changeSessionId()))
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/csrf", cors);
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Ở đây response **204 No Content** sau login thành công là **hợp đồng minh họa do ứng dụng đặt**, không phải mặc định formLogin. Response **401** cho credential sai cũng là lựa chọn minh họa; hệ thống thực tế cần xử lý lỗi tránh tiết lộ thông tin.

Vì formLogin mặc định dùng **form parameters** cho username/password, frontend phải gửi dữ liệu theo định dạng tương thích hoặc bạn phải tự xây dựng authentication filter/handler hỗ trợ JSON. Không nhầm việc thêm application/json vào headers với khả năng parser mặc định đọc JSON.

**Lưu ý quan trọng về mã Java:** Cấu hình Servlet cơ bản ở mục 6 và cấu hình SPA ở đây là **hai phương án minh họa cho hai ứng dụng/chiến lược khác nhau**. Không đưa hai bean SecurityFilterChain trùng matcher vào cùng ứng dụng rồi kỳ vọng chúng tự hợp nhất. Chọn và hoàn chỉnh theo kiến trúc thực tế.

### 7.4. Frontend gửi form parameters và CSRF token

Một ví dụ SPA:

~~~javascript
const apiBase = "https://api.example.com";

async function login(username, password) {
  // Nhận token khi chưa xác thực, nhưng vẫn dùng cùng browser cookie jar.
  const csrfResponse = await fetch(apiBase + "/csrf", {
    credentials: "include",
    cache: "no-store"
  });
  if (!csrfResponse.ok) {
    throw new Error("Không khởi tạo được phiên login");
  }

  const csrf = await csrfResponse.json();
  const body = new URLSearchParams({ username, password });

  const loginResponse = await fetch(apiBase + "/login", {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      [csrf.headerName]: csrf.token
    },
    body,
    redirect: "follow"
  });

  if (!loginResponse.ok) {
    throw new Error("Đăng nhập không thành công");
  }

  // Không suy ra user identity chỉ từ status của POST.
  const meResponse = await fetch(apiBase + "/api/me", {
    credentials: "include",
    cache: "no-store"
  });
  if (!meResponse.ok) {
    throw new Error("Không xác minh được phiên sau login");
  }

  return meResponse.json();
}
~~~

Ví dụ giả định backend áp dụng **204 cho login thành công**, endpoint **GET /api/me** đã được triển khai và trả dữ liệu danh tính của phiên. Nếu backend dùng redirect 302 mặc định của formLogin, fetch sẽ xử lý redirect theo quy tắc Fetch, nhưng **không tự điều hướng document như form browser**; không dùng response.redirected hoặc một 200 từ HTML login page để kết luận user đã xác thực.

**Không log username/password/CSRF token** trong production telemetry, không lưu password trong localStorage và không đưa credential vào URL query.

### 7.5. Một số lỗi SPA đặc trưng

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra |
| --- | --- | --- |
| GET /csrf trả 401. | Endpoint cấp token bị yêu cầu đã đăng nhập. | Cho phép anonymous đúng endpoint, giữ CSRF ở POST /login. |
| GET /csrf không lưu cookie phù hợp. | Secure, Domain, Path, SameSite, credentials hoặc third-party cookie policy. | DevTools Storage/Network và cookie blocked reasons. |
| POST /login trả 403. | CSRF token thiếu/sai, không cùng phiên hoặc request vào chain khác. | Log CsrfFilter, Cookie, header token và repository. |
| OPTIONS /login 401/403. | Preflight bị authentication/gateway chặn trước CORS. | CORS filter/allowed Origin/method/header, thứ tự proxy. |
| POST /login trả 200 nhưng vẫn chưa login. | Request có thể bị redirect tới trang login HTML hoặc handler tùy chỉnh. | Kiểm tra redirect chain và gọi GET /api/me. |
| POST thành công nhưng JS không đọc response. | Actual response thiếu CORS phù hợp. | Xem response thực cả 204/401/403; không mở wildcard. |
| Một request sau login bị 403 CSRF. | Token đã được rotate/xóa khi authentication thành công. | Lấy CSRF token mới sau login, dùng cùng session hiện tại. |
| Cookie sau login không ổn định giữa nhiều máy chủ. | Session repository chưa chia sẻ hoặc proxy/cookie config sai. | Redis/Spring Session, routing và session TTL. |

### 7.6. Không dùng CORS làm allowlist danh tính user

Ngay cả khi API trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
~~~

một script XSS chạy ngay trong app.example.com cũng có thể gọi API qua browser nếu các điều kiện tương ứng phù hợp. **CORS không chống XSS ở origin được tin**. Đồng thời, một HTTP client ngoài browser không chịu SOP/CORS như JavaScript.

API cần kiểm tra session, quyền tài nguyên, CSRF token và dữ liệu request bất kể Origin có nằm trong allowlist hay không.

## 8. Reactive/WebFlux: login CSRF với ServerHttpSecurity

**Spring Security WebFlux** sử dụng **SecurityWebFilterChain** và **ServerHttpSecurity**, không dùng HttpSecurity/HttpSession của Servlet. Tuy nhiên mô hình browser **vẫn giống nhau**: login bằng cookie/WebSession là một state transition cần được bảo vệ.

### 8.1. Cấu hình WebFlux form login

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveLoginSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/assets/**").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Các điểm cốt lõi:

- Form login mặc định xử lý credential theo cơ chế của Spring Security WebFlux.
- **CSRF không bị tắt**: login POST vẫn cần token theo matcher mặc định.
- WebFlux dùng **WebSession** và reactive CSRF repository, không phải HttpSessionCsrfTokenRepository của Servlet.
- Trang login hoặc endpoint cấp token **phải hỗ trợ người dùng chưa xác thực** nếu frontend tùy chỉnh yêu cầu.
- Phải kiểm tra token có được đưa vào HTML/form/SPA và gửi lại đúng cách.
- Việc thực thi login thành công phải tạo/duy trì trạng thái xác thực theo session strategy của WebFlux; không suy ra thiết lập session fixation Servlet tự áp dụng y hệt ở WebFlux.

### 8.2. Trang login tùy chỉnh trong WebFlux

Khi tự thiết kế trang login WebFlux, cần chú ý CSRF token có thể được lưu/đặt trong **ServerWebExchange** dưới dạng **Mono<CsrfToken>**. Template/rendering cần thực sự resolve giá trị này để tạo trường hidden trong form.

Một form minh họa:

~~~html
<form method="post" action="/login">
  <label for="username">Tài khoản</label>
  <input id="username" name="username">
  <label for="password">Mật khẩu</label>
  <input id="password" name="password" type="password">
  <input type="hidden" name="_csrf"
         value="TOKEN_LAY_TU_REACTIVE_CSRF_REPOSITORY">
  <button type="submit">Đăng nhập</button>
</form>
~~~

Đây **không phải template production hoàn chỉnh**. Token phải lấy từ cơ chế CSRF hiện hành, không được cố định như placeholder. Nếu dùng Thymeleaf/WebFlux hoặc thư viện khác, kiểm tra integration để render token reactive chính xác.

### 8.3. WebFlux CORS khi SPA ở origin khác

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveLoginCorsConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/csrf", cors);
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Khi dùng cấu hình CORS nguồn này, **SecurityWebFilterChain** phải tích hợp nó qua cấu hình CORS thích hợp, ví dụ:

~~~java
// Bổ sung bên trong cấu hình ServerHttpSecurity cho SPA/WebFlux:
http.cors(cors -> cors.configurationSource(corsConfigurationSource()));
~~~

**Không trộn** lớp Servlet UrlBasedCorsConfigurationSource với gói **org.springframework.web.cors.reactive**. Phải xác định cách tạo WebSession cookie, CSRF repository và cách trao token trong stack reactive tương ứng.

CORS preflight OPTIONS thường không mang session cookie, nên phải được xử lý trước những bước authentication có thể chặn vì thiếu phiên. **POST /login thực** vẫn cần CSRF token.

### 8.4. Session cookie của WebFlux

Trong hệ thống HTTPS, có thể đặt thuộc tính cookie của WebSession:

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

Với **__Host-**, không đặt Domain. Nếu WebSessionIdResolver đã được Spring Session hoặc cấu hình khác đăng ký, phải lựa chọn một chủ sở hữu cấu hình để tránh bean trùng. WebFlux không dùng **server.servlet.session.*** như Servlet.

### 8.5. Bảo vệ login như một flow, không như một kết quả 302 đơn lẻ

Cả Servlet và WebFlux cần kiểm thử:

1. Anonymous GET /login hoặc /csrf nhận form/token hợp lệ theo thiết kế.
2. POST /login thiếu token bị từ chối.
3. POST /login sai token bị từ chối.
4. POST /login đúng token nhưng sai mật khẩu bị từ chối.
5. POST /login đúng token và đúng mật khẩu tạo đúng session/principal.
6. Session không bị cố định vào ID attacker đã biết.
7. Sau logout, session cũ không được chấp nhận.
8. User không thể gửi một custom header để tự đổi danh tính hoặc tenant.

## 9. OAuth2/OIDC login CSRF: ràng buộc authorization response với request ban đầu

Một ứng dụng không dùng form username/password trực tiếp có thể đăng nhập qua **OAuth2 Authorization Code Flow** hoặc **OpenID Connect (OIDC)**. Khi đó, browser chuyển qua **Identity Provider (IdP)** rồi quay lại **callback** của ứng dụng. Rủi ro login CSRF vẫn tồn tại nếu một authorization response **không được liên kết đúng với flow do browser này bắt đầu**.

### 9.1. Ranh giới tin cậy của login liên kết

Giả sử:

~~~text
Ứng dụng:  https://app.example.com
IdP:       https://identity.partner.test
Callback:  https://app.example.com/login/oauth2/code/partner
~~~

Luồng minh họa:

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring OAuth2 Client
    participant I as Identity Provider
    B->>A: Bắt đầu đăng nhập với IdP
    A->>A: Tạo request state, PKCE; lưu ngữ cảnh flow
    A-->>B: Redirect tới authorization endpoint
    B->>I: Authorization request
    I->>I: Xác thực user, consent nếu cần
    I-->>B: Redirect về callback với code và state
    B->>A: GET /login/oauth2/code/partner?code=...&state=...
    A->>A: Kiểm tra state và request gốc của browser
    A->>I: Back-channel code exchange + PKCE verifier
    I-->>A: Token response
    A->>A: Xác minh issuer/audience/signature/nonce nếu OIDC
    A-->>B: Tạo hoặc cập nhật session ứng dụng
~~~

**Browser là kênh vận chuyển front-channel**, không phải bằng chứng cho thấy bất kỳ callback nào cũng hợp lệ. Attacker có thể thử đưa browser đến một callback chứa code/state từ flow khác. Nếu app xử lý callback mà không kiểm tra sự ràng buộc, có nguy cơ **đăng nhập/liên kết sai tài khoản**.

### 9.2. State dùng để làm gì?

**state** là giá trị có đủ tính khó đoán do OAuth2 client tạo khi bắt đầu authorization request, được liên kết với ngữ cảnh login mà client lưu. Khi nhận callback, client phải xác minh **state nhận được trùng với request đang chờ** và xử lý đúng một flow hợp lệ.

Nguyên tắc:

- State được tạo mới theo request/flow và khó đoán.
- State được lưu hoặc ràng buộc với browser/session bằng repository thích hợp.
- State phải được kiểm tra trước khi chấp nhận authorization response.
- Không dùng một hằng số state cố định cho tất cả người dùng.
- Không chấp nhận callback không có request khởi tạo tương ứng.
- Quản lý vòng đời request/state để chống dùng lại và nhầm lẫn giữa nhiều flow.
- Không đưa state chứa dữ liệu nhạy cảm dạng plain text không cần thiết vào URL.

Trong Spring Security Servlet, authorization request mặc định thường được lưu qua repository gắn với HttpSession khi dùng các cấu hình OAuth2 client tiêu chuẩn. Nếu tùy chỉnh **AuthorizationRequestRepository**, phải giữ cơ chế ràng buộc an toàn; không chuyển sang một cookie tùy ý không bảo vệ toàn vẹn rồi bỏ kiểm tra state.

### 9.3. PKCE không thay state

**Proof Key for Code Exchange (PKCE)** ràng buộc authorization code với **code verifier** mà client đã tạo lúc bắt đầu flow. Nó đặc biệt quan trọng để hạn chế **authorization code interception/injection** và là cơ chế bảo vệ được khuyến nghị cho authorization code flow hiện đại.

Nhưng:

- PKCE không phải một allowlist redirect URI.
- PKCE không tự xác nhận user được phép truy cập tài nguyên.
- PKCE không cho phép bỏ qua kiểm tra state/correlation theo kiến trúc login.
- PKCE không thay các điều kiện OIDC ID token validation.

**State và PKCE có thể hỗ trợ nhau**, nhưng bảo vệ những thuộc tính khác nhau của luồng.

### 9.4. OIDC nonce và ID token

Nếu dùng OIDC, một số flow cần hoặc sử dụng **nonce** để liên kết ID token với authorization request và hạn chế replay/substitution theo quy tắc giao thức. Khi xác minh ID token, kiểm tra:

- Chữ ký và thuật toán được cho phép.
- **iss** đúng IdP tin cậy.
- **aud** đúng client ID, cùng các điều kiện liên quan nếu có nhiều audience.
- **exp**, iat và các điều kiện thời gian áp dụng.
- **nonce** nếu được gửi/yêu cầu theo flow.
- Các điều kiện OIDC khác như azp khi liên quan và cách xử lý issuer/provider mix-up.

**ID token chứng minh danh tính cho OIDC client theo điều kiện giao thức**, không phải access token có quyền gọi mọi API. Đừng lấy chỉ một giá trị sub trong token rồi bỏ qua issuer, audience hoặc chữ ký.

### 9.5. Redirect URI và mix-up

Callback hợp lệ phải đến đường dẫn đã được cấu hình cho client/IdP:

~~~text
https://app.example.com/login/oauth2/code/partner
~~~

Không chấp nhận một tham số redirect_uri hoặc next bất kỳ từ browser để thay thế callback đã được đăng ký. Cũng không dùng chính sách “URL chứa example.com” để cho phép redirect, vì chuỗi đó có thể xuất hiện trong hostname của attacker.

Hệ thống kết nối nhiều IdP cần phân biệt **provider/issuer nào phát hành response** và không nhầm authorization response của IdP A với request dành cho IdP B. Việc issuer mix-up có thể dẫn tới quyết định tin sai token/endpoint dù callback trông hợp lệ.

### 9.6. Callback GET không được bảo vệ bằng CSRF matcher mặc định như POST /login

Một callback OAuth2/OIDC thường sử dụng **GET** và có thể làm thay đổi session sau khi xác thực. Spring Security mặc định không yêu cầu **CSRF form token** cho GET, do đó không thể chỉ dựa vào CsrfFilter để bảo vệ callback.

Ranh giới này cần được bảo vệ bằng **state, PKCE, redirect URI, token validation và ngữ cảnh authorization request**. Đây là lý do không được suy luận “GET callback không có CSRF token nên hoàn toàn không có cơ chế chống login CSRF”.

Trong một số tích hợp, **response_mode=form_post** khiến IdP POST callback qua browser. Khi đó cần đánh giá riêng **SameSite cookie, state correlation, matcher CSRF và endpoint callback**. Nếu cần ngoại lệ CSRF cho đúng callback giao thức, nó phải **rất hẹp** và được thay bằng đầy đủ validation của flow; không tắt CSRF toàn ứng dụng.

### 9.7. Cấu hình Spring Security OAuth2 login

Với Spring MVC/Servlet, cấu hình đăng nhập liên kết có thể bắt đầu bằng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OidcLoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Cấu hình trên còn cần **spring-security-oauth2-client**, client registration và provider metadata, redirect URI đã đăng ký, các scope phù hợp. Khi sử dụng OIDC còn cần cấu hình/validator đúng để thực hiện OpenID Connect login.

**Đây là phương án thay thế cho formLogin password-based ở các ví dụ trước**, không phải một yêu cầu phải bật cả hai để login CSRF được bảo vệ. Một ứng dụng hỗ trợ nhiều phương thức đăng nhập cần thiết kế UX và ranh giới của từng flow.

Với WebFlux, cấu trúc tương đương về mặt ý tưởng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveOidcLoginSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
~~~

Cả hai đoạn đều giữ CSRF cho những thao tác khác dùng session/cookie. Không suy ra chỉ vì đăng nhập qua OAuth2 mà toàn bộ POST của ứng dụng không cần CSRF.

## 10. Ràng buộc login với đúng browser, account và session

Một triển khai an toàn cần nhìn **toàn bộ vòng đời** thay vì chỉ endpoint /login.

### 10.1. Trước đăng nhập: anonymous context

Trang login có thể cần tạo CSRF token trước authentication. Anonymous session tồn tại ở server nếu repository yêu cầu, nhưng chưa có principal đã đăng nhập.

Cần hạn chế **session fixation** và không chấp nhận client tự chọn session ID rồi dùng nguyên ID ấy sau xác thực. Nếu có remember-me cookie hoặc một phương thức đăng nhập tự động khác, chính sách chuyển đổi trạng thái user cũng phải được xác định.

### 10.2. Khi đăng nhập thành công: session fixation strategy

Một session-based application nên sử dụng bảo vệ fixation thích hợp:

~~~text
Trước login:
  Session ID A (anonymous)
  ↓
POST /login + CSRF token hợp lệ + credential đúng
  ↓
Spring Security xác thực
  ↓
Session fixation protection
  ↓
Sau login:
  Session ID B (authenticated), theo strategy cấu hình
~~~

Trong Servlet container hiện đại, **changeSessionId** là một chiến lược có sẵn. Điều này **khác** với việc đòi CSRF token: cả hai bảo vệ những điều kiện khác nhau.

Một lưu ý kỹ thuật: **CSRF token trước login có thể bị xóa/đổi sau khi auth thành công** theo CsrfAuthenticationStrategy hoặc repository/handler đã cấu hình. SPA không nên giữ một token trước login để gửi mãi cho mọi POST về sau; cần có cách lấy token mới sau khi đổi phiên khi cần.

### 10.3. Khi người dùng có nhiều tài khoản

Nếu ứng dụng hỗ trợ switching accounts hoặc multiple tenants:

- Hiển thị rõ **user/tenant hiện tại** trước thao tác nhạy cảm.
- Không tự động nhập dữ liệu người dùng vào một tài khoản vừa bị đổi ngoài ý định.
- Không dùng X-Account-Id/X-Tenant-Id do frontend tự đặt làm bằng chứng danh tính.
- Không chấp nhận “tài khoản đã đăng nhập” là bằng chứng user được phép truy cập đơn của người khác.
- Có bước xác nhận/reauthentication phù hợp khi liên kết tài khoản, đổi email, thêm phương thức thanh toán hoặc xác nhận hành động nhạy cảm.
- Đánh giá ranh giới session và token khi user **đổi tài khoản trong cùng browser**.

### 10.4. Redirect sau login không được do attacker tùy ý chọn

Một tham số như:

~~~text
/login?next=https://outside.test/collect
~~~

nếu được server dùng thẳng cho redirect có thể tạo **open redirect** hoặc phishing. Khi dùng SavedRequest/RequestCache trong Spring Security, hãy hiểu cơ chế lưu yêu cầu ban đầu và nơi user được chuyển sau login.

Với redirect do ứng dụng tự thiết kế, ưu tiên **path nội bộ đã kiểm tra** hoặc allowlist origin/route. Không cho query string hoặc header tùy ý tạo redirect đến host của attacker.

### 10.5. Login success handler không được lộ credential

Không đặt session ID, refresh token, access token hoặc CSRF token vào:

- Query string của URL chuyển hướng.
- Log hoặc analytics.
- Tên tệp/đường dẫn tạo download.
- Thông báo lỗi hiển thị cho mọi người.
- postMessage đến targetOrigin "*" khi thông tin nhạy cảm.
- Response dành cho một origin không được CORS allowlist phù hợp.

Nếu dùng session cookie **Secure, HttpOnly**, frontend thường không cần đọc mã phiên trực tiếp; browser tự gửi theo các điều kiện cookie. Khi cần biết trạng thái login, frontend gọi một endpoint **/api/me** được bảo vệ để lấy danh tính theo quyền.

## 11. Đăng xuất và đăng nhập lại: một chuỗi trạng thái liên quan

Login CSRF liên quan trực tiếp đến logout và tái xác thực:

~~~text
Anonymous → Login thành công → Authenticated
Authenticated → Logout → Anonymous
Anonymous → Login lại → Authenticated (có thể là account khác)
~~~

Các chuyển đổi phải được bảo vệ đúng:

- **POST /login**: không bỏ CSRF chỉ vì chưa có principal.
- **POST /logout**: là hành động làm thay đổi trạng thái xác thực; thường được CSRF bảo vệ khi bật mặc định.
- **GET /logout**: không nên trở thành endpoint tự vô hiệu hóa session chỉ vì dễ tạo thẻ liên kết.
- **OAuth callback**: ràng buộc authorization request/state thay cho việc coi callback GET tùy ý là an toàn.
- **Remember-me hoặc IdP SSO**: sau logout, browser có thể còn credential giúp tái xác thực theo chính sách, nên phải xác định rõ mức độ “đăng xuất”.

### 11.1. Logout phải thu hồi session server-side

Ví dụ form logout trong ứng dụng server-rendered:

~~~html
<form method="post" action="/logout">
  <input type="hidden" name="_csrf"
         value="TOKEN_DO_SERVER_CAP">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Token là placeholder để minh họa. Framework/template integration có thể tự chèn CSRF field tương ứng.

Không chỉ xóa cookie và ẩn UI. **Server phải invalidate session**; nếu có remember-me token, refresh token hoặc các session khác thuộc chính sách logout, cần xử lý chúng riêng.

### 11.2. Trạng thái login ở nhiều tab

Hai tab cùng origin có thể giữ UI state khác nhau, trong khi cookie jar được chia sẻ trong browser profile. Khi một tab login sang account khác:

- Tab còn lại có thể tiếp tục hiển thị tên user cũ trong cache/UI.
- Request mới có thể sử dụng cookie session mới, dẫn đến khác biệt giữa “user hiển thị” và “user server xác thực”.
- SPA cần cơ chế **revalidate principal** khi tab được focus, sau login/logout hoặc khi nhận tín hiệu thay đổi auth state.
- Với thao tác nhạy cảm, server phải kiểm tra quyền hiện tại thay vì tin danh tính cache ở frontend.

Có thể dùng BroadcastChannel để đồng bộ UX giữa tab cùng origin, nhưng **BroadcastChannel không phải bằng chứng xác thực và không tự thu hồi session**.

### 11.3. CSP, frame policy và bảo vệ giao diện login

Trang đăng nhập chứa password fields và trạng thái xác thực nên được bảo vệ bằng các lớp phù hợp:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Cache-Control: no-store
~~~

Chính sách chỉ minh họa cho **HTML login do ứng dụng phục vụ**. Một frontend khác origin cần chính sách CSP tại chính host phục vụ trang HTML. Nếu login qua IdP hoặc có các asset/redirect hợp lệ khác, phải kiểm thử và tinh chỉnh các directive.

**frame-ancestors** giúp hạn chế clickjacking bằng cách ngăn trang login bị nhúng tùy ý. CSP không thay CSRF token, và TLS/HSTS bảo vệ kênh truyền chứ không xác nhận user chủ ý login.

### 11.4. Bảo vệ credential stuffing và account enumeration

CSRF protection không chặn kẻ tấn công gửi hàng loạt request đăng nhập trực tiếp bằng HTTP client. Cần biện pháp độc lập như:

- Rate limiting theo nhiều tín hiệu với chính sách chống gây khóa tài khoản hàng loạt.
- Phát hiện password spraying và đăng nhập bất thường.
- MFA/WebAuthn khi phù hợp.
- Lưu mật khẩu an toàn bằng password hashing phù hợp, không log password.
- Hạn chế tiết lộ account tồn tại qua message hoặc timing khi khả thi.
- Chính sách khôi phục tài khoản và reset password an toàn.
- Giới hạn truy cập trang admin và các điểm rủi ro cao theo cơ chế thích hợp.

**Chống brute-force và login CSRF là hai mô hình đe dọa khác nhau**. Không giảm CSRF chỉ vì ứng dụng đã có CAPTCHA hoặc MFA.

## 12. Origin, Referer và Fetch Metadata: tín hiệu bổ sung cho login

Ngoài CSRF token/state, ứng dụng có thể xét những header do browser quản lý để đánh giá ngữ cảnh request. Tuy nhiên, chúng **không nên là bằng chứng xác thực duy nhất**.

### 12.1. Origin

Ví dụ browser gửi:

~~~http
POST /login HTTP/1.1
Host: shop.example.com
Origin: https://shop.example.com
Content-Type: application/x-www-form-urlencoded

username=learner&password=...
~~~

Với một login request đến từ trang cùng origin, Origin có thể phản ánh origin hợp lệ. Nếu request từ **outside.test**, browser có thể gửi Origin của outside.test theo những quy tắc áp dụng.

Để dùng Origin làm tín hiệu phụ:

- So sánh chính xác **scheme + host + port** với allowlist; không chỉ tìm chuỗi example.com.
- Không mặc định **Origin: null** là tin cậy.
- Có chính sách cho request thiếu Origin theo loại client/browser/flow.
- Tách trường hợp cùng origin, khác origin nhưng cùng site, và cross-site.
- Không dùng Origin để xác thực password, OAuth token hoặc quyền user.

Một HTTP client ngoài browser có thể tự đặt Origin, vì vậy Origin không được dùng thay authentication/authorization.

### 12.2. Referer

Referer có thể chỉ ra URL nguồn:

~~~http
Referer: https://shop.example.com/login
~~~

Nhưng Referer có thể **vắng mặt hoặc bị rút gọn** bởi Referrer-Policy, quyền riêng tư hoặc loại request. Không dùng một phép so substring với URL, cũng không suy ra thiếu Referer chắc chắn là kẻ tấn công.

Origin/Referer có thể giúp phát hiện flow không mong muốn khi CSRF token không hợp lệ, nhưng logic fallback cần được thiết kế và kiểm thử rõ ràng.

### 12.3. Sec-Fetch-Site và các header Fetch Metadata

Một browser hiện đại có thể gửi:

~~~http
Sec-Fetch-Site: same-origin
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
~~~

Các header có thể giúp server phân biệt điều hướng, request API, hoặc nguồn same-origin/same-site/cross-site.

Những giới hạn:

- **same-site khác same-origin**: một subdomain không đáng tin có thể cùng site với ứng dụng.
- Một số request từ bookmark, thanh địa chỉ hoặc browser cũ có thể thiếu header hoặc có **Sec-Fetch-Site: none**.
- OAuth2/OIDC callback thường xuất phát từ **IdP khác site**, nên nếu từ chối mù quáng mọi login-related cross-site navigation, ứng dụng có thể làm hỏng đăng nhập liên kết hợp lệ.
- Header Fetch Metadata không phải bằng chứng mật mã; HTTP client ngoài browser có thể tự đặt chuỗi này.

Hãy dùng Fetch Metadata như một **resource isolation policy bổ sung**, có ngoại lệ được xác định cho các flow thực sự cần thiết, và vẫn giữ CSRF token/state ở nơi cần.

### 12.4. CSP form-action và frame-ancestors

Trên **HTML trang login**, một chính sách như:

~~~http
Content-Security-Policy: form-action 'self'; frame-ancestors 'none'
~~~

giúp browser hạn chế điểm đến form và việc trang bị nhúng vào iframe. Đây là lớp giảm thiểu thao tác ngoài ý muốn/clickjacking đối với chính trang ứng dụng.

Tuy nhiên, website ngoài có thể dựng **form của nó** với action trỏ đến ứng dụng; CSP của **trang login ở shop.example.com** không điều khiển form được tạo trong document outside.test. Vì vậy **form-action không thay CsrfFilter** trên POST /login.

## 13. Kiểm thử login CSRF và ràng buộc session

Các kịch bản dưới đây dành cho **môi trường test do bạn kiểm soát**. Không thử đăng nhập người khác hoặc tạo nhầm dữ liệu cá nhân trên production.

### 13.1. Kết quả mong đợi theo trạng thái

| Kịch bản | Trạng thái trước request | Request | Kết quả mong đợi |
| --- | --- | --- | --- |
| Mở trang login | Chưa xác thực | GET /login | Trang/token hợp lệ được cấp theo cấu hình. |
| Thiếu CSRF token | Chưa xác thực | POST /login có credential đúng, không token | **Bị từ chối** do CSRF (thường 403) trước khi tạo authenticated session. |
| CSRF token sai | Chưa xác thực | POST /login có token sai | Bị từ chối; không đổi principal. |
| CSRF token đúng, password sai | Chưa xác thực | POST /login hợp lệ về CSRF | Authentication thất bại; không tạo authenticated principal. |
| Token đúng, password đúng | Chưa xác thực | POST /login | Đăng nhập đúng user, xử lý session fixation và trả response theo hợp đồng. |
| Login từ form ngoài không có token | Browser có thể có anonymous cookie | Cross-site POST /login | Không đổi sang tài khoản mà bên ngoài chọn. |
| User đã login A, yêu cầu login B không CSRF | Đã xác thực A | POST /login do bên ngoài tạo | Không được đổi A thành B theo request thiếu token. |
| Sau login | Vừa được xác thực | POST nghiệp vụ với CSRF token cũ đã bị invalidate | Có thể bị 403; frontend cần lấy token mới theo flow. |
| OAuth callback sai state | Có request OAuth đang chờ | Callback có state không khớp | Từ chối callback; không tạo session user không mong muốn. |
| OAuth callback không có request khởi tạo | Không có flow đang chờ | Callback chỉ có code/state từ nơi khác | Từ chối. |
| Session fixation | Anonymous session ID đã có | Login hợp lệ | ID được rotate/đổi theo session strategy phù hợp. |
| Logout | Đang xác thực | POST /logout hợp lệ | Session/credential theo chính sách bị vô hiệu hóa. |

### 13.2. MockMvc: login thiếu hoặc sai token

Với **spring-security-test** và Spring MVC được cấu hình, có thể viết test:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class LoginCsrfMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCsrfDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "test-secret"))
            .andExpect(status().isForbidden());
    }

    @Test
    void invalidCsrfDoesNotAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .with(csrf().useInvalidToken())
                .param("username", "learner")
                .param("password", "test-secret"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndCredentialsCanAuthenticate() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "test-secret"))
            .andExpect(authenticated().withUsername("learner"));
    }
}
~~~

**Điều kiện của ví dụ:** Cấu hình test phải có một user **learner** với password kiểm thử **test-secret**, formLogin và CsrfFilter đang hoạt động. Không sử dụng password trên trong production. Nếu login success handler hoặc endpoint xử lý khác, điều chỉnh assertion phù hợp.

Mục tiêu là kiểm tra **token CSRF là điều kiện bắt buộc ngay cả khi credential hợp lệ**. Test nên bổ sung xác minh **session không được gắn principal** sau request thiếu/sai token, không chỉ xem HTTP status.

### 13.3. Kiểm thử đổi session ID

Trong Servlet test, cần kiểm tra luồng:

1. Browser truy cập GET /login và nhận anonymous session cookie nếu CSRF repository tạo session.
2. Ghi nhận session ID bằng cơ chế test an toàn, không log bí mật đầy đủ.
3. Gửi POST /login kèm token hợp lệ và credential test.
4. Xác nhận session đã gắn đúng principal và **ID được thay đổi** theo session fixation strategy đang dùng.
5. Dùng ID/session cũ đã không còn quyền như trước, xác nhận hành vi theo repository.
6. Sau logout, xác minh session ID cũ không còn truy cập được tài nguyên được bảo vệ.

Không đồng nhất session fixation test với CSRF test: **cả hai phải có kịch bản riêng**.

### 13.4. WebTestClient: login thiếu và có CSRF

Với WebFlux, ví dụ đoạn test sử dụng **spring-security-test**:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.BodyInserters;

// webTestClient đã được bind tới ứng dụng/chain trong test.
webTestClient
    .post()
    .uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData("username", "learner")
            .with("password", "test-secret"))
    .exchange()
    .expectStatus().isForbidden();

webTestClient
    .mutateWith(csrf())
    .post()
    .uri("/login")
    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
    .body(BodyInserters.fromFormData("username", "learner")
            .with("password", "test-secret"))
    .exchange()
    .expectStatus().is3xxRedirection();
~~~

Đây là **đoạn minh họa**, chưa phải lớp test hoàn chỉnh; giả định login thành công sẽ redirect theo formLogin mặc định và user test hợp lệ. Nếu ứng dụng có custom success handler trả 204, assertion cần đổi theo hợp đồng. Còn phải kiểm tra **principal sau login**, không chỉ redirect status.

### 13.5. Không dùng oauth2Login() mock thay cho protocol test

Spring Security Test có thể cung cấp request post-processors để mô phỏng user OIDC/OAuth2 đã xác thực. Chúng hữu ích cho **authorization tests**, nhưng **không tự chứng minh** authorization code flow, state, PKCE, nonce, issuer validation hoặc redirect URI được bảo vệ ở runtime.

Để kiểm tra **login CSRF trong OAuth2/OIDC**, cần các kịch bản tích hợp với test IdP hoặc môi trường mô phỏng giao thức thực:

- Authorization response **không có state**.
- State **không khớp** với authorization request browser đã khởi tạo.
- Code được phát hành cho **client/redirect URI** khác.
- Callback khi **không có request đang chờ**.
- ID token từ **issuer không đáng tin** hoặc **audience sai**.
- Nonce sai nếu flow yêu cầu nonce.
- User bị đổi danh tính giữa các bước flow ngoài ý định.
- Login/logout nhiều tab làm mất correlation session/state.

Phải xác minh server **không tạo authenticated session** từ những callback không hợp lệ.

### 13.6. Kiểm tra form login bằng DevTools

Trong **DevTools → Network → Application/Storage**:

1. Mở GET /login, tìm **CSRF hidden field** trong DOM/form đã render nếu dùng HTML form.
2. Kiểm tra response có **Set-Cookie** và browser có lưu anonymous session cookie hay không.
3. Thực hiện login test hợp lệ; xem POST /login có **Cookie** và CSRF parameter/header đúng không.
4. Quan sát HTTP status, **Location redirect** (nếu có), session cookie sau auth và dữ liệu **/api/me**.
5. Kiểm tra cookie có **Secure, HttpOnly, SameSite, Path, Domain** phù hợp.
6. Nếu login từ SPA khác origin, xem OPTIONS preflight và actual response CORS.
7. Kiểm tra JS/HTML không log password, token, session ID hoặc response chứa bí mật.
8. Đăng xuất và thử lại API bằng cookie cũ trong môi trường test.

Một **GET /login có Set-Cookie** không nhất thiết là lỗi: nó có thể chỉ phục vụ một anonymous session/CSRF token. Vấn đề là liệu **POST /login được kiểm tra token** và **trạng thái authenticated** có chỉ xuất hiện sau các điều kiện hợp lệ hay không.

### 13.7. curl giúp đọc HTTP, nhưng không chứng minh behavior browser

Ví dụ trên endpoint thử nghiệm:

~~~bash
curl -i "https://shop.example.com/login"
~~~

Một POST giả lập thiếu CSRF token để xác minh server từ chối, chỉ sử dụng account test và endpoint được phép:

~~~bash
curl -i -X POST "https://shop.example.com/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=learner" \
  --data-urlencode "password=test-secret"
~~~

Kết quả có thể là 403 khi CSRF filter đang hoạt động, nhưng nếu thiếu cookie/session hoặc có security filter khác, mã lỗi có thể khác. **curl không thực thi SOP/CORS, SameSite hay cơ chế browser cookie giống browser thật**. Dùng curl để kiểm tra HTTP/headers, rồi dùng browser/DevTools để kiểm tra kịch bản login CSRF end-to-end.

Không đưa credential thật vào terminal history, script chia sẻ hoặc log production; ví dụ chỉ dùng dữ liệu giả trong môi trường kiểm thử.

## 14. Chẩn đoán các lỗi hay bị nhầm với login CSRF

| Triệu chứng | Khả năng cần kiểm tra | Phương pháp xác minh |
| --- | --- | --- |
| POST /login trả 403 trước khi kiểm tra password. | Thiếu/sai CSRF token, session không khớp hoặc CsrfFilter từ chối. | Request token, Cookie, log Spring Security, CSRF repository. |
| POST /login báo lỗi từ SPA, nhưng server đã xác thực. | Response redirect/CORS không phù hợp với fetch. | Kiểm tra actual response, cookies và GET /api/me. |
| GET /csrf trả 401. | Endpoint cấp token bị bảo vệ như endpoint authenticated. | Cho anonymous đúng endpoint, không bỏ CSRF ở POST login. |
| OPTIONS /login trả 401, không thấy POST. | CORS preflight bị authentication/gateway chặn. | Xem Origin/Access-Control-Request-* và cấu hình CORS trước auth. |
| Browser không lưu cookie sau login. | Secure, SameSite, Domain/Path, prefix __Host-, third-party policy. | DevTools Cookies/Issues và Set-Cookie response. |
| GET /login không thấy trường CSRF. | Custom template không render token hoặc integration không hoạt động. | Kiểm tra HTML đã render, Thymeleaf RequestDataValueProcessor. |
| Token hợp lệ trước login, POST nghiệp vụ sau login bị 403. | CSRF token bị rotate sau authentication. | Lấy token mới, kiểm tra repository/handler. |
| Request đến instance A login được, sang instance B mất session. | Session store không chia sẻ/sticky session không phù hợp. | Xem Session repository, load balancer, TTL, secret/config. |
| OAuth callback báo invalid state. | Browser mất session cookie, flow đã hết hạn, callback từ tab khác hoặc state thực sự sai. | Authorization request repository, cookie, redirect chain, timeouts. |
| OAuth login trở lại nhanh sau logout. | IdP còn SSO session, dù app session đã bị hủy. | Phân biệt cookie app và cookie IdP, logout policy. |
| User bị đăng nhập vào account không mong muốn. | Login CSRF, account switch hoặc liên kết SSO không đúng flow. | Audit login intent, POST /login token, state/correlation và session principal. |
| Login lỗi sau thay đổi proxy HTTPS. | Forwarded headers/host/scheme sai, cookie Secure bị bỏ hoặc redirect URI lệch. | TLS termination, trusted proxies, redirect URI và Set-Cookie. |
| Link /login?next=... chuyển tới website lạ. | Open redirect/saved request không được kiểm soát. | Kiểm tra success handler, allowlist host/path. |
| Login page CSP chặn script hoặc form submit. | CSP script-src/form-action quá chặt so với tính năng hợp lệ. | Console CSP violation của **HTML login document**. |
| Một URL POST hoạt động với curl nhưng không hoạt động trong browser. | Browser policy: CORS, cookie SameSite/credentials, CSP hoặc Mixed Content. | DevTools, không quy tất cả thành CSRF. |
| POST /login từ origin khác site không có cookie phiên cũ. | SameSite/cookie policy, nhưng request có thể vẫn tới login endpoint. | Không kết luận an toàn chỉ từ absence of Cookie. |
| User có session nhưng sửa account khác được. | Lỗi authorization, không phải lỗi login CSRF duy nhất. | Kiểm tra principal và owner/tenant ở backend. |

### 14.1. Điều tra đúng thứ tự

Đối với login không thành công hoặc hành vi tài khoản bất thường:

1. Xác định **đúng endpoint, method và origin** đã khởi tạo login.
2. Xem **request thật** đã được browser gửi chưa hay bị preflight/CSP chặn.
3. Kiểm tra **CSRF token** trước login được cấp từ đâu, có về đúng session không.
4. Nếu liên kết IdP, kiểm tra **state, correlation, redirect URI và issuer**, không chỉ một HTTP status callback.
5. Xem **principal kết quả** ở server và session ID lifecycle.
6. Kiểm tra **cookie và session repository**, không suy từ UI.
7. Xem bước redirect/logout/account switch có bị input từ bên ngoài chi phối không.
8. Xác định **tác dụng nghiệp vụ**: dữ liệu đã lưu vào account nào, có phát sinh truy cập trái quyền không.
9. Chỉ thay đổi CORS/CSRF/security headers khi đã xác định nguyên nhân; không tắt các lớp bảo vệ để làm login “hết lỗi”.

### 14.2. Proxy, HSTS và Host header

Trong môi trường production sau reverse proxy, browser có thể truy cập HTTPS còn backend thấy HTTP nội bộ. Server cần xác định đúng **public scheme/host** để sinh redirect URI, callback và cookie.

Những header như **Forwarded** hoặc **X-Forwarded-Proto/Host** chỉ nên được tin sau khi proxy đã **làm sạch header client có thể tự đặt** và chỉ backend kết nối qua proxy đáng tin. Không dùng bất cứ Host hoặc X-Forwarded-Host nào do HTTP client tùy ý gửi để sinh URL login/callback/reset password.

**HSTS** giúp browser ưu tiên HTTPS theo chính sách đã nhận, nhưng không giải quyết login CSRF hoặc state mismatch. CSP, CORS, cookie policy, TLS và CSRF là các lớp độc lập.

## 15. Bài tập tình huống

### Tình huống A — Browser bị đăng nhập vào tài khoản của attacker

Nạn nhân chưa đăng nhập shop. Website ngoài khiến browser gửi POST /login với username/password của attacker. Shop không kiểm tra CSRF và sau đó browser hiển thị tài khoản attacker. Nạn nhân lưu địa chỉ cá nhân vào hồ sơ tài khoản đó. Đây là loại lỗi gì?

**Đáp án:** **Login CSRF**. Attacker không cần biết mật khẩu nạn nhân; họ muốn nạn nhân ghi dữ liệu vào tài khoản attacker kiểm soát. Cần bảo vệ POST /login bằng CSRF token/flow hợp lệ và hiển thị danh tính kết quả rõ ràng.

### Tình huống B — Anonymous request vẫn cần CSRF?

Một developer cho rằng chỉ người dùng đã đăng nhập mới cần CSRF token; vì /login phải permitAll nên thêm ignoringRequestMatchers("/login"). Có phù hợp không?

**Đáp án:** Không. Login tự làm thay đổi trạng thái xác thực và có nguy cơ login CSRF khi chưa có principal. **permitAll là authorization**, không phải lý do bỏ CSRF trên POST /login.

### Tình huống C — Đổi session ID có chống được login CSRF?

Ứng dụng luôn rotate session ID sau khi xác thực. Nhưng nó vẫn nhận POST /login từ trang ngoài không có CSRF token. Có còn rủi ro login CSRF không?

**Đáp án:** Có. Rotation chống session fixation; nó không chứng minh nạn nhân đã chọn account mà request đang đăng nhập.

### Tình huống D — Cookie HttpOnly và SameSite=Lax

Team đặt Secure, HttpOnly, SameSite=Lax cho session cookie rồi tắt CSRF trên /login. Có thể coi đã loại hết login CSRF không?

**Đáp án:** Không. Các cookie flags giảm bề mặt tấn công nhưng không ràng buộc login với CSRF token/session/authorization flow. POST login có thể tạo trạng thái xác thực mới; phải kiểm thử thực tế và giữ biện pháp chống login CSRF.

### Tình huống E — CORS không cho website ngoài

API chỉ trả Access-Control-Allow-Origin cho frontend chính thức. Website ngoài vẫn có thể kích hoạt form POST tới /login mà không đọc được response. Có phải CORS đã bảo vệ login hoàn toàn không?

**Đáp án:** Không. CORS hạn chế quyền đọc response cross-origin, không chặn mọi form POST hoặc hành động server-side. POST login cần CSRF token.

### Tình huống F — Form Spring Security tùy chỉnh thiếu _csrf

GET /login hiển thị form đẹp, username/password đúng, nhưng POST /login luôn trả 403. Template dùng HTML form action thuần và không có hidden CSRF field. Nên sửa thế nào?

**Đáp án:** Bảo đảm trang login cung cấp CSRF token thực và form gửi đúng field/header. Nếu dùng Thymeleaf với th:action và integration Spring Security, kiểm tra hidden token được tự chèn; nếu tự render, cấp token từ repository và thêm field đúng.

### Tình huống G — Credential sai nhưng CSRF đúng

POST /login có CSRF token hợp lệ nhưng password sai. Có phải Spring Security bắt buộc tạo session xác thực vì token đúng không?

**Đáp án:** Không. CSRF chỉ vượt qua một lớp kiểm tra. Authentication vẫn phải xác minh username/password, MFA nếu áp dụng và chính sách tài khoản. Credential sai không được tạo authenticated principal.

### Tình huống H — SPA cần CSRF trước login nhưng GET /csrf trả 401

SPA đặt login backend ở origin khác; nó chỉ lấy được CSRF token sau khi login nên rơi vào vòng lặp. Cần làm gì?

**Đáp án:** Cho phép anonymous truy cập đúng endpoint cấp CSRF token hoặc trang login hợp lệ, vẫn bảo vệ POST /login bằng token. Cấu hình CORS cho cả /csrf và /login, xác minh cookie/session phù hợp.

### Tình huống I — SPA gửi JSON đến formLogin mặc định

Frontend POST application/json với trường username/password đến /login nhưng Spring Security không xác thực. Team cho rằng lỗi do CSRF. Có nguyên nhân nào khác?

**Đáp án:** Form login mặc định thường mong **form parameters**, không tự parse JSON body. Cần gửi URL-encoded form theo hợp đồng hoặc triển khai authentication mechanism hỗ trợ JSON, song vẫn giữ CSRF nếu cookie/session có thể được tự gửi.

### Tình huống J — OPTIONS /login không có cookie

Khi SPA gọi API cross-origin với X-CSRF-TOKEN, browser gửi OPTIONS trước và nhận 401 do không có session cookie. Có nên tắt CSRF hoặc ép frontend thêm Cookie vào OPTIONS?

**Đáp án:** Không. OPTIONS preflight thường không mang session cookie. Cấu hình CORS xử lý trước auth trên endpoint hợp lệ. POST thực vẫn phải kiểm tra session, CSRF và credential.

### Tình huống K — Đăng nhập thành công nhưng POST tiếp theo 403

SPA dùng cùng một CSRF token trước login để gửi POST đổi hồ sơ sau login; request bị 403. Có thể vì sao?

**Đáp án:** CSRF token có thể bị rotate/invalidate khi authentication thành công. Phải lấy token mới theo cơ chế của ứng dụng và bảo đảm session mới được browser gửi đúng.

### Tình huống L — State ở OAuth callback không khớp

Browser đang bắt đầu login với IdP; callback trả về code nhưng state khác request đã lưu. Có nên bỏ kiểm tra state vì code hợp lệ và PKCE đang bật?

**Đáp án:** Không. Phải ràng buộc authorization response với authorization request đang chờ của browser; state mismatch cần từ chối theo flow. PKCE là lớp ràng buộc code riêng, không được dùng như lý do chấp nhận mọi callback.

### Tình huống M — ID token đã ký, nhưng audience khác

IdP gửi ID token có chữ ký hợp lệ nhưng aud không phải client ID của ứng dụng. App có nên tạo session user vì chữ ký đúng?

**Đáp án:** Không. Phải kiểm tra issuer, audience, chữ ký, thời hạn và nonce/những điều kiện OIDC thích hợp. Chữ ký hợp lệ không bảo đảm token được phát hành cho client này.

### Tình huống N — OIDC callback GET tạo session

Đội ngũ cho rằng GET không bao giờ được tạo session, nên callback OAuth2/OIDC dùng GET chắc chắn không an toàn và phải đổi thành POST với CSRF form field. Nhận định có đầy đủ không?

**Đáp án:** Chưa đầy đủ. Callback front-channel của authorization code flow thường dùng GET và được bảo vệ bằng **state, PKCE, redirect URI và token validation**. Không thể tùy ý đổi method nếu IdP/giao thức không hỗ trợ; và không thể thay state bằng CSRF form field của ứng dụng.

### Tình huống O — OAuth form_post và cookie SameSite

IdP gửi callback qua form_post từ site khác, trong khi cookie chứa authorization request của ứng dụng được đặt SameSite=Lax. Callback không tìm được flow cũ. Đây là lỗi gì cần xem?

**Đáp án:** Cần kiểm tra cookie SameSite trên cross-site POST, cách lưu/correlate authorization request và response_mode thực tế. Không mở toàn bộ cookies/CSRF bừa bãi; thiết kế callback riêng tương thích và vẫn xác minh state/nonce/PKCE đúng giao thức.

### Tình huống P — Open redirect sau login

Ứng dụng lấy next từ query string rồi dùng làm URL chuyển hướng sau khi login thành công. Attacker cung cấp next=https://outside.test/phishing. Vấn đề gì?

**Đáp án:** **Open redirect** sau login, có thể hỗ trợ phishing hoặc rò dữ liệu URL. Chỉ cho phép path nội bộ hoặc origin/route được xác minh bằng allowlist, không tin URL tùy ý từ client.

### Tình huống Q — Multiple tabs đang ở hai tài khoản

Tab A hiển thị user A. Tab B vừa login sang user B; browser profile chia sẻ cookie mới. Tab A tiếp tục cho phép cập nhật đơn của A dựa trên tên user A còn cache. Vấn đề ở đâu?

**Đáp án:** Client UI không đồng bộ với session/principal hiện tại. Trước thao tác nhạy cảm, server phải kiểm tra quyền của **principal thực ở request mới**, không dựa vào tên/tài khoản cache; frontend nên revalidate trạng thái khi có auth change.

### Tình huống R — Login trên server A, tiếp tục trên server B

GET /login và CSRF token được tạo trên instance A; POST /login đến instance B dùng session store cục bộ nên token không tìm thấy. Có nên bỏ CSRF để fix không?

**Đáp án:** Không. Đây có thể là lỗi **session repository/load balancing**. Dùng shared session store/chiến lược session nhất quán; bảo đảm POST gặp đúng token từ anonymous session, rồi kiểm tra rotation sau login.

### Tình huống S — Đăng xuất qua GET link

Developer đổi /logout thành GET để người dùng chỉ cần bấm thẻ a; sau đó website khác có thể kích hoạt GET này. Có nguy cơ gì?

**Đáp án:** **Logout CSRF** và vi phạm ngữ nghĩa GET safe. Giữ logout là thao tác thay đổi trạng thái dùng POST với CSRF token khi session/cookie, invalidate phiên server-side.

### Tình huống T — OAuth login lại sau logout

User logout khỏi app nhưng vẫn còn SSO session tại IdP. Khi họ bấm login lại, IdP không yêu cầu nhập mật khẩu. Có chứng minh logout ứng dụng thất bại không?

**Đáp án:** Không nhất thiết. App session và IdP session độc lập. Cần kiểm tra app đã invalidate session đúng chưa, sau đó xác định chính sách IdP logout/SSO mong muốn.

### Tình huống U — CSRF token hợp lệ nhưng account không có quyền

Một user đăng nhập hợp lệ, có CSRF token đúng rồi gửi POST thay đổi email của user khác. Có thể thực hiện vì đủ token không?

**Đáp án:** Không. CSRF token không cấp quyền cho tài nguyên. Backend phải xác thực principal và authorization theo tài khoản/tenant, và cân nhắc xác thực lại cho hành động nhạy cảm.

### Tình huống V — Header Origin trông giống login page

Một HTTP client ngoài browser gửi Origin: https://shop.example.com trong POST /login, nhưng không có CSRF token. Có được cho qua vì Origin tin cậy không?

**Đáp án:** Không nên. HTTP client ngoài browser có thể tự đặt Origin. Origin là tín hiệu bổ sung; với mô hình session/form login, vẫn cần CSRF token hoặc biện pháp ràng buộc tương đương theo thiết kế.

### Tình huống W — Trang login nhận CSP trên JSON API

SPA HTML nằm ở app.example.com; API ở api.example.com đặt Content-Security-Policy: frame-ancestors 'none' trên JSON, rồi cho rằng HTML login đã được chống clickjacking. Đúng không?

**Đáp án:** Không. CSP bảo vệ document nhận policy; cần đặt CSP/frame-ancestors trên **response HTML của trang login/frontend**, không chỉ API JSON khác origin.

### Tình huống X — Form từ trang ngoài đăng nhập bằng tài khoản attacker

Tài khoản bị ép đăng nhập là tài khoản có quyền thấp, không có đặc quyền admin. Một đồng nghiệp kết luận login CSRF vô hại vì không làm nạn nhân thành admin. Đúng không?

**Đáp án:** Không. Nạn nhân vẫn có thể **đưa dữ liệu cá nhân, địa chỉ, tài liệu hoặc giao dịch** vào tài khoản attacker kiểm soát; quyền thấp không loại bỏ rủi ro nhầm danh tính và rò dữ liệu.

## 16. Checklist triển khai an toàn

### 16.1. Trước login

- [ ] Xác định luồng login là **state transition**, có thể bắt đầu từ user anonymous.
- [ ] GET /login hoặc endpoint /csrf có cách **cấp CSRF token hợp lệ trước xác thực**.
- [ ] Custom form có đúng field CSRF/token; kiểm tra HTML render, không hard-code token.
- [ ] Login page dùng HTTPS, CSP phù hợp, anti-clickjacking và không đưa secret vào URL.
- [ ] Không có endpoint GET tùy ý nhận username/password rồi tạo authenticated session.
- [ ] CORS dành cho SPA chỉ cho origin cụ thể và hỗ trợ /csrf, /login nếu khác origin.
- [ ] Session cookie có Secure, HttpOnly, SameSite, Path/Domain phù hợp; kiểm tra __Host- khi dùng.
- [ ] Password manager/autocomplete và thông báo lỗi được thiết kế không làm lộ account/password.

### 16.2. POST /login

- [ ] Không bỏ CSRF ở POST /login của session-based form login chỉ vì endpoint permitAll.
- [ ] Token được **server xác minh**, không chỉ kiểm tra tên header/field.
- [ ] Credential được kiểm tra bằng authentication provider tin cậy, password storage an toàn.
- [ ] Có cơ chế rate limiting/anti-abuse độc lập với CSRF.
- [ ] Login thành công áp dụng bảo vệ session fixation theo stack.
- [ ] Login thất bại không tạo authenticated session và không lộ thông tin quá mức.
- [ ] Redirect success/failure được kiểm soát, không chấp nhận URL ngoài tùy ý.
- [ ] Frontend kiểm tra principal kết quả thay vì chỉ nhìn một response 200/302.
- [ ] Không log password, session ID, CSRF token hoặc credential khác.

### 16.3. OAuth2/OIDC login

- [ ] Authorization request được liên kết với **state khó đoán và ngữ cảnh browser**.
- [ ] Callback không có request đang chờ hoặc state không khớp **bị từ chối**.
- [ ] PKCE được dùng và kiểm tra theo authorization code flow thích hợp.
- [ ] OIDC ID token được kiểm tra issuer, audience, chữ ký, thời gian và nonce khi áp dụng.
- [ ] Redirect URI được đăng ký/allowlist, không phụ thuộc query tùy ý.
- [ ] Phân biệt user session của app với SSO session của IdP.
- [ ] Test multiple IdPs, multiple tabs, flow expiry, issuer mix-up và state correlation.
- [ ] Nếu sử dụng callback form_post, đánh giá cookie SameSite và CSRF matcher riêng, không tắt CSRF toàn site.

### 16.4. Sau login và logout

- [ ] Session mới có đúng principal và quyền, không dựa vào client-supplied account ID.
- [ ] CSRF token được tái cấp sau auth/session rotation khi cần.
- [ ] Nhiều tab/account switch không khiến UI dùng principal cache để cấp quyền.
- [ ] POST /logout được bảo vệ thích hợp và invalidate server-side session.
- [ ] Refresh/remember-me tokens được thu hồi theo chính sách riêng.
- [ ] Token/session hết hạn được xử lý rõ ràng trong frontend, không lặp request nhạy cảm ngoài ý muốn.
- [ ] Dữ liệu riêng tư của account cũ không còn bị render/cached như account mới.
- [ ] Có log audit xác định account nào đã được login, thời điểm và nguồn sự kiện, nhưng tránh lưu secrets.

### 16.5. Kiểm thử âm tính trước release

- [ ] POST /login thiếu CSRF token không tạo authenticated session.
- [ ] POST /login token sai không thay đổi trạng thái user.
- [ ] Login hợp lệ phải yêu cầu **CSRF và credential đúng**.
- [ ] User A không bị đổi thành B do request từ website ngoài không được ràng buộc.
- [ ] OPTIONS /login không bị auth filter chặn trước khi CORS đánh giá.
- [ ] OAuth callback với state sai/thiếu, issuer hoặc audience sai bị từ chối.
- [ ] Session fixation strategy hoạt động như cấu hình.
- [ ] Logout session cũ không còn truy cập được endpoint bảo vệ.
- [ ] Không có open redirect từ login, login error hoặc saved request.
- [ ] Trường hợp proxy HTTPS, nhiều instance, cookie policy và CSP vẫn hoạt động nhất quán.
- [ ] QA kiểm tra server-state khi browser báo lỗi, không suy ra request thất bại chỉ từ CORS error.

## 17. Ghi nhớ

1. **Login CSRF là hành vi ép browser thay đổi trạng thái đăng nhập ngoài ý định**, thường bằng cách đưa nạn nhân vào tài khoản do attacker kiểm soát. Nó có thể gây **nhầm danh tính và rò dữ liệu** dù attacker không biết mật khẩu nạn nhân.
2. **POST /login cũng cần CSRF protection trong ứng dụng session-based**, dù user chưa đăng nhập. **permitAll** chỉ nói về authorization, không loại bỏ CsrfFilter.
3. Luồng form login đúng thường gồm **GET /login cấp token → POST /login gửi token + credential → xác thực → thay đổi session ID nếu phù hợp → kiểm tra account kết quả**.
4. **SameSite, Secure, HttpOnly, SOP và CORS** là lớp bổ trợ; CORS không chặn mọi form cross-origin và cookie flags không chứng minh user đã chọn tài khoản.
5. **Session fixation và login CSRF khác nhau**: đổi session ID không thay việc xác minh request login được khởi tạo hợp lệ.
6. Với **Spring Security Servlet**, giữ CSRF, dùng HttpSecurity/formLogin và bảo vệ session. Với **WebFlux**, dùng ServerHttpSecurity/formLogin/WebSession và bảo đảm token được render/resolve phù hợp.
7. Với **SPA login khác origin**, cho anonymous nhận CSRF token hợp lệ, cấu hình CORS cả token endpoint và login endpoint, gửi cookie theo chính sách browser, rồi xác minh principal sau login. **JSON login không phải mặc định của formLogin**.
8. **OAuth2/OIDC login** ràng buộc callback bằng **state**, dùng PKCE cho code flow, nonce khi OIDC yêu cầu, kiểm tra redirect URI, issuer/audience và token. Không tự coi một callback GET là an toàn vì không có CSRF form token.
9. **CSRF token không cấp quyền trên tài nguyên**. Backend vẫn phải xác thực, phân quyền theo account/tenant, kiểm tra dữ liệu nghiệp vụ và chống abuse.
10. **Đăng xuất** cần vô hiệu hóa session/credential theo chính sách và không nên có tác dụng phụ qua GET. Sau login/logout cần xử lý token rotation, session lifecycle và nhiều tab.
11. Khi điều tra sự cố, phân biệt **CSRF 403**, credential sai, cookie/session không khớp, CORS preflight, CSP, OAuth state mismatch và reverse proxy; đừng tắt cơ chế bảo vệ chỉ để che lỗi.
