# Remember-me khác với giữ một HttpSession tồn tại lâu hơn

## 1. Vấn đề: “Ghi nhớ đăng nhập” không đồng nghĩa “giữ nguyên phiên”

Trong ứng dụng Spring Security Servlet, người dùng thường mong muốn hai trải nghiệm khác nhau:

- **Phiên đăng nhập hiện tại:** Sau khi nhập đúng username/password, trình duyệt gửi cookie phiên (thường là `JSESSIONID`), server tìm `HttpSession` và khôi phục `SecurityContext`. Phiên có timeout, có thể bị vô hiệu khi logout hoặc bị xóa khi session store không còn dữ liệu.
- **Remember-me:** Người dùng **chủ động đồng ý ghi nhớ đăng nhập**. Ứng dụng cấp một cookie *remember-me* riêng có thời hạn dài hơn. Về sau, khi không còn phiên đã xác thực, một filter có thể kiểm tra cookie đó và **xác thực tự động** mà không cần yêu cầu nhập lại mật khẩu ở thao tác thông thường.

Hai cách đều có thể khiến user không phải gõ mật khẩu thường xuyên, nhưng **khác hoàn toàn về nơi lưu trạng thái, vòng đời credential, cơ chế khôi phục và khả năng thu hồi**.

| Tiêu chí | Kéo dài HTTP session | Spring Security remember-me |
| --- | --- | --- |
| Thứ được browser gửi | Cookie ID phiên, thường `JSESSIONID` | Cookie riêng, mặc định thường là `remember-me` |
| Server xác minh thế nào? | Tra session ID trong session store; lấy `SecurityContext` đã lưu | Kiểm tra token/cookie remember-me qua `RememberMeServices` và `UserDetailsService` |
| Khi session cũ đã hết hạn | Không thể khôi phục `Authentication` chỉ từ ID session đã hết hạn | **Có thể** xác thực lại tự động nếu remember-me token còn hợp lệ |
| Dữ liệu session ứng dụng | Có thể giữ giỏ hàng, CSRF, wizard… lâu hơn | **Không** tự hồi sinh dữ liệu của `HttpSession` cũ |
| Trạng thái xác thực | Thường do form login tương tác thành công tạo ra | Spring Security có thể tạo `RememberMeAuthenticationToken` |
| Mức tin cậy để truy cập chức năng nhạy cảm | Có thể là fully authenticated tùy cơ chế tạo phiên | Có thể bị yêu cầu đăng nhập lại bằng `fullyAuthenticated()` |
| Tác động khi token bị đánh cắp | Kẻ có session ID sống có thể chiếm phiên | Kẻ có remember-me cookie còn hợp lệ cũng có thể thử đăng nhập tự động |
| Thu hồi | Invalidate session / session store, chính sách đăng xuất | Xóa cookie và/hoặc thu hồi token server-side tùy implementation |
| Timeout/cookie expiration | Session timeout và tuổi thọ cookie cần đồng bộ | `tokenValiditySeconds` và cơ chế token/cookie riêng |
| Phù hợp nhất | Duy trì trạng thái đăng nhập của phiên đang diễn ra | Cho phép quay lại sau khi phiên cũ đã kết thúc |

**Chốt ý:** Remember-me là một **cơ chế xác thực bằng credential riêng để có thể khôi phục login giữa các phiên**. Nó **không** phải cấu hình `server.servlet.session.timeout` thật lớn và **không** đơn giản là đặt `Max-Age` dài cho `JSESSIONID`.

Bài học tập trung vào **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC/Servlet và form login dùng HttpSession**. Các API WebFlux/Reactive có cách cấu hình khác. Với API token-based stateless, không mặc định áp dụng cơ chế remember-me của trình duyệt.

## 2. HttpSession và JSESSIONID thực sự làm việc ra sao?

Khi ứng dụng dùng form login tiêu chuẩn:

~~~text
Lần đăng nhập trực tiếp

Browser                         Servlet + Spring Security
   |                                   |
   | POST /login + user/password       |
   |---------------------------------->|
   |     AuthenticationManager xác thực|
   |     SessionAuthenticationStrategy |
   |     lưu Authentication vào        |
   |     SecurityContext/session       |
   |<----------------------------------|
   | Set-Cookie: JSESSIONID=<S1>       |
   |                                   |
   | GET /account/me                   |
   | Cookie: JSESSIONID=<S1>           |
   |---------------------------------->|
   | Server tìm session S1, khôi phục  |
   | SecurityContext và username       |
   |<----------------------------------|
   | 200 JSON                          |
~~~

Server nhận `JSESSIONID=S1`, tra session store để biết phiên S1 hiện có hay không và `SecurityContext` của phiên còn chứa danh tính đã xác thực không. Browser không cần đọc cookie bằng JavaScript nếu cookie có `HttpOnly`.

### 2.1. Có ba thời hạn khác nhau

Không nhầm:

1. **Session idle timeout**: phiên trên server hết hạn sau một khoảng thời gian không hoạt động (ví dụ 30 phút). Trên Servlet, `HttpSession.getMaxInactiveInterval()` và cấu hình của container/session store quyết định điều này.
2. **Cookie lifetime**: browser quyết định còn lưu cookie đến khi nào dựa vào `Max-Age`/`Expires` hoặc cookie phiên (session cookie) theo chính sách browser.
3. **Mức độ/tính hợp lệ của Authentication trong phiên**: có thể bị thay đổi bởi logout, vô hiệu hóa tài khoản, sự kiện bảo mật, chính sách session, hoặc thay đổi session store.

Cookie hết hạn nhanh có thể khiến browser quên ID trước khi server xóa session. Ngược lại, cookie còn lâu nhưng **session trên server đã hết hạn** thì cookie chỉ chứa một ID không còn khôi phục được danh tính.

Ví dụ:

~~~properties
# Minh họa cấu hình session dài; KHÔNG nên dùng chỉ để giả lập remember-me.
server.servlet.session.timeout=30d
server.servlet.session.cookie.max-age=30d
~~~

Cấu hình này có thể làm **cửa sổ tồn tại của cùng một session ID kéo dài**, nhưng không tạo remember-me token mới, không thiết kế thu hồi theo thiết bị và không đảm bảo phiên tồn tại đủ 30 ngày nếu restart/eviction/session store có chính sách khác. Session timeout là **thời gian không hoạt động**, không nhất thiết là thời gian tồn tại tối đa tuyệt đối.

### 2.2. Các rủi ro khi “nới timeout cho tiện”

- Session ID bị lộ có thể còn giá trị lâu hơn: hậu quả của session hijacking kéo dài.
- Server/session store phải giữ nhiều bản ghi phiên lâu hơn, có thể làm tăng chi phí và ảnh hưởng eviction.
- Một trình duyệt công cộng/thiết bị dùng chung có thể giữ quyền truy cập lâu nếu người dùng quên logout.
- Khi server xóa session dù cookie vẫn còn, user vẫn bị buộc đăng nhập; vấn đề UX không thực sự được giải quyết.
- Session lâu tồn tại có thể chứa dữ liệu nhạy cảm hoặc state không còn phù hợp.
- Tăng tuổi thọ cookie **không** tự tăng tuổi thọ session server; tăng timeout server **không** tự bảo đảm browser tiếp tục gửi cookie.

**Không dùng `JSESSIONID` làm “remember-me token”.** Một session ID là credential để truy cập trạng thái đang lưu trên server; remember-me nên có credential với vòng đời, giới hạn và cơ chế validation riêng.

## 3. Remember-me hoạt động khi phiên hiện tại không còn

Một luồng remember-me điển hình:

~~~text
Ngày 1
Browser chọn checkbox "Remember me"
  └─ POST /login + username/password + remember-me=on
       ├─ Xác thực tương tác thành công
       ├─ Tạo/lưu SecurityContext trong session S1
       └─ RememberMeServices.loginSuccess
            └─ phát cookie remember-me=R1

Một thời điểm sau
Session S1 hết hạn / bị xóa khỏi session store
Browser vẫn giữ cookie remember-me=R1
  └─ GET /account/me
       ├─ SecurityContext ban đầu trống (không có S1 hợp lệ)
       ├─ RememberMeAuthenticationFilter
       │     └─ RememberMeServices.autoLogin(R1)
       │           ├─ R1 hợp lệ → tạo Authentication dạng remember-me
       │           └─ R1 sai/hết hạn → từ chối auto-login, xóa cookie nếu cần
       ├─ AuthenticationManager kiểm tra RememberMeAuthenticationToken
       ├─ SecurityContext được thiết lập cho request
       └─ Authorization quyết định endpoint được truy cập hay không
~~~

Điểm then chốt:

- Khi **SecurityContext đã có Authentication**, remember-me filter thông thường không cần tự login lại. Remember-me là **đường khôi phục**, không thay mọi request của phiên đầy đủ bằng xác thực khác.
- Nếu session cũ hết hạn, remember-me có thể giúp tạo ra danh tính đã xác thực trên request mới và một phiên mới có thể được tạo/lưu tùy cấu hình session/context repository. Đây **không phải phục hồi session S1** với giỏ hàng và tất cả attributes cũ.
- Cookie remember-me có thể còn hiệu lực lâu hơn thời gian idle của session. Nhưng nếu cookie cũng mất/hết hạn hoặc token bị thu hồi, phải đăng nhập tương tác lại.
- Nếu người dùng **không chọn remember-me**, form login thường không cấp cookie dài hạn đó, ngay cả khi ứng dụng đã bật remember-me.
- Nếu browser tự phục hồi session cookie sau khi mở lại, user có thể thấy vẫn đăng nhập nhờ **session còn sống**, không phải nhờ remember-me. Muốn kiểm chứng phải thử request chỉ có remember-me cookie, không có cookie phiên cũ.

### 3.1. Các thành phần Spring Security

| Thành phần | Vai trò |
| --- | --- |
| `UsernamePasswordAuthenticationFilter` | Xử lý form login; thông báo thành công/thất bại cho `RememberMeServices` qua hooks. |
| `RememberMeServices` | Hợp đồng tạo cookie sau login, xử lý thất bại và thử auto-login. |
| `RememberMeAuthenticationFilter` | Khi thiếu `Authentication` hiện hành, kiểm tra cơ hội xác thực qua cookie remember-me. |
| `TokenBasedRememberMeServices` | Lựa chọn token cookie có chữ ký/hàm băm, không cần bảng DB riêng. |
| `PersistentTokenBasedRememberMeServices` | Lựa chọn token ngẫu nhiên có bản ghi trong kho lưu trữ; hỗ trợ token rotation. |
| `RememberMeAuthenticationToken` | Biểu diễn kết quả xác thực bằng remember-me. |
| `RememberMeAuthenticationProvider` | Provider kiểm tra token remember-me dựa trên key phù hợp. |
| `UserDetailsService` | Tải user/authorities để phục hồi danh tính; hai implementation chuẩn của remember-me cần nó. |
| `LogoutFilter` / `LogoutHandler` | Xóa trạng thái phiên và gọi handler để dọn cookie/token remember-me tùy implementation. |
| `SecurityContextRepository` | Quản lý lưu/khôi phục `SecurityContext`; không phải kho remember-me token. |

Hợp đồng `RememberMeServices` có ba hành vi chủ chốt:

~~~java
Authentication autoLogin(
    HttpServletRequest request,
    HttpServletResponse response
);

void loginSuccess(
    HttpServletRequest request,
    HttpServletResponse response,
    Authentication successfulAuthentication
);

void loginFail(
    HttpServletRequest request,
    HttpServletResponse response
);
~~~

Đây là **chữ ký API minh họa**, không phải file Java độc lập. `autoLogin` có thể trả một `Authentication` hoặc `null`. `loginSuccess` được gọi từ cơ chế interactive authentication thành công. `loginFail` xử lý một lần thử login trực tiếp thất bại; nó không đồng nghĩa mọi 401 từ mọi endpoint đều xóa remember-me token.

## 4. Khác nhau về độ tin cậy: remembered và fully authenticated

Một tài khoản được xác thực nhờ cookie nhớ đăng nhập có thể truy cập các trang thông thường, nhưng ứng dụng nên yêu cầu **đăng nhập lại** trước thao tác nhạy cảm (đổi password, thanh toán, thay đổi MFA, xóa tài khoản...).

Spring Security có thể phân biệt:

- **Anonymous**: không có danh tính đăng nhập thực sự.
- **Remember-me authenticated**: có `Authentication` từ remember-me, được `AuthenticationTrustResolver` nhận diện.
- **Fully authenticated**: đã qua cơ chế tương tác đầy đủ theo chính sách kiểm tra của Spring Security, không phải anonymous hoặc remember-me.

Trong DSL:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account/sensitive").fullyAuthenticated()
    .requestMatchers("/account/**").authenticated()
    .anyRequest().permitAll()
);
~~~

Một request chỉ có cookie remember-me hợp lệ thường được cho vào `/account/me`, nhưng **không** được vào `/account/sensitive` cho tới khi user login trực tiếp. Với form login, khi người dùng nhớ đăng nhập truy cập endpoint yêu cầu đầy đủ, Spring Security thường bắt đầu lại entry point login (chẳng hạn redirect tới `/login`), chứ không nhất thiết trả `403`.

**`Authentication.isAuthenticated()==true` chưa có nghĩa fully authenticated.** Một `RememberMeAuthenticationToken` có thể có cờ authenticated và authorities của user, nhưng vẫn bị `fullyAuthenticated()` từ chối. Do vậy không nên tự viết một check kiểu `if (authentication.isAuthenticated())` rồi bỏ qua điều kiện re-auth đối với hành động nhạy cảm.

Có thể kiểm tra bằng:

~~~java
AuthenticationTrustResolver trustResolver =
    new AuthenticationTrustResolverImpl();

boolean remembered = trustResolver.isRememberMe(authentication);
boolean anonymous = trustResolver.isAnonymous(authentication);
boolean fullyAuthenticated = trustResolver.isFullyAuthenticated(authentication);
~~~

Đoạn trên là **logic minh họa**, giả định biến `authentication` đã được lấy an toàn từ `SecurityContext`. `AuthenticationTrustResolver` kiểm tra loại authentication; một ứng dụng cần mức bảo đảm cao hơn (MFA vừa hoàn thành, thao tác trong vòng 5 phút gần đây) phải có chính sách step-up riêng, không chỉ dựa vào `fullyAuthenticated()`.

## 5. Hai implementation phổ biến: hash-based và persistent token

Spring Security cung cấp hai cách remember-me chuẩn. Cả hai sử dụng cookie như credential để xác thực lại; **không** giữ nguyên HTTP session cũ.

### 5.1. TokenBasedRememberMeServices: cookie được ký/kiểm chứng

Ý tưởng là tạo cookie có các trường như username, thời điểm hết hạn, thuật toán và chữ ký dựa trên thông tin user cùng một **server-side secret key**. Theo đặc tả thực thi hash-based của Spring Security 6, cấu trúc khái niệm:

~~~text
base64(username : expirationTime : algorithmName : signature)

signature = hash(username : expirationTime : password : key)
~~~

Đây là **biểu diễn khái niệm**, không phải hướng dẫn tự viết thuật toán cookie. Mặc định các phiên bản 6.x hiện đại sử dụng SHA-256 để tạo signature; có API riêng cho migration thuật toán.

Ưu điểm:

- Không nhất thiết phải có bảng remember-me token riêng.
- Dễ bật trong form-login demo và các hệ thống nhỏ.
- Thay đổi password hoặc key dùng để ký có thể làm token cũ hết hiệu lực.

Hạn chế và rủi ro:

- Cookie đã bị đánh cắp có thể được **phát lại từ browser khác** đến khi hết hạn hoặc đến khi password/key thay đổi.
- Không có bản ghi token riêng cho từng thiết bị để thu hồi một token cụ thể theo cách trực tiếp.
- Logout thông thường xóa cookie ở browser hiện tại, nhưng **không tự thu hồi mọi bản sao bị đánh cắp** của hash-based token.
- Key phải đủ ngẫu nhiên, dài và ổn định qua restart; mất/thay key sẽ làm cookie cũ hết hiệu lực.
- Không được đưa key, raw password, cookie/token vào log hoặc frontend.

Vì thế đây là cách tiện để học khái niệm remember-me, **không phải lựa chọn mặc định tốt nhất cho mọi hệ thống cần kiểm soát nhiều thiết bị**.

### 5.2. PersistentTokenBasedRememberMeServices: series + token lưu DB

Thay vì chỉ dựa vào một cookie có chữ ký không có state riêng, persistent token dùng dữ liệu ngẫu nhiên trong cookie và một bản ghi trên server:

~~~text
Cookie: remember-me = encode(series, token)

Database persistent_logins:
  username | series (primary key) | token | last_used
~~~

Khi nhận cookie và không có session authenticated:

1. Đọc `series` và `token` từ cookie.
2. Tra record theo `series` trong `PersistentTokenRepository`.
3. So sánh token từ cookie với token ở server và kiểm tra thời hạn.
4. Nếu hợp lệ: cấp `RememberMeAuthenticationToken`, sinh token **mới**, cập nhật DB và gửi cookie mới (giữ nguyên series).
5. Nếu cookie đã cũ hoặc sai: auto-login thất bại; tùy tình huống, cookie bị hủy. Với **series có trong DB nhưng token không khớp**, Spring Security coi là dấu hiệu có thể bị đánh cắp, ném `CookieTheftException` và xóa token của user.

Một schema thường dùng (cần điều chỉnh theo DB dialect và migration của hệ thống):

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

So với hash-based:

| Tiêu chí | Hash-based | Persistent token |
| --- | --- | --- |
| Lưu riêng remember-me token ở server | Không bắt buộc | Có, qua `PersistentTokenRepository` |
| Token sau auto-login | Không có cơ chế series/token DB rotation tương tự | Token được xoay khi xác thực bằng cookie thành công |
| Thu hồi cụ thể | Hạn chế; thường dựa vào hết hạn, password/key thay đổi | Có thể xóa bản ghi token theo chính sách/repository |
| Khi cookie bị đánh cắp | Cookie có thể replay cho đến hết hạn | Mismatch sau rotation có thể phát hiện dấu hiệu dùng lại; không bảo đảm phát hiện mọi lần đánh cắp |
| Vận hành | Ít thành phần hơn | Cần DB/session/token cleanup, xử lý lỗi đồng thời |
| Phù hợp | Demo/đơn giản, rủi ro thấp đã đánh giá | Sản phẩm cần khả năng thu hồi/quản lý token rõ hơn |

**Điểm tinh tế về logout:** Trong implementation `PersistentTokenBasedRememberMeServices` của Spring Security, logout handler khi nhận được `Authentication` phù hợp có thể gọi `removeUserTokens(username)`, nghĩa là **thu hồi các persistent remember-me token của user**, không chỉ cookie trên thiết bị hiện tại. Đừng mặc định nó chỉ thu hồi một thiết bị. Nếu muốn tính năng “đăng xuất riêng thiết bị này”, phải thiết kế repository và logout flow có mục tiêu rõ ràng. Nếu logout request thiếu Authentication hoặc chạy ở một luồng không cấu hình handler thích hợp, kết quả thu hồi server-side có thể khác kỳ vọng; phải test.

**Giới hạn concurrency:** Với persistent token rotation, hai request song song cùng mang một cookie cũ có thể cạnh tranh: request đầu xoay token, request thứ hai cầm token trước đó thấy mismatch và có thể kích hoạt xử lý nghi bị đánh cắp. Cần kiểm thử ứng dụng có nhiều tab, AJAX song song, retry và cách phản hồi để không làm người dùng bị logout không mong muốn. Token rotation giúp bảo vệ hơn nhưng không phải bằng chứng tuyệt đối rằng một cookie chưa từng bị lộ.

**Đừng quên cleanup:** Hết hạn trong logic xác minh không đồng nghĩa bảng `persistent_logins` được tự động dọn sạch mọi bản ghi. Cần chính sách cleanup an toàn theo lưu lượng/tuổi thọ và điều kiện vận hành.

## 6. Form login chuẩn tích hợp remember-me như thế nào?

Form-login filter có hooks báo cho `RememberMeServices` biết login tương tác thành công hoặc thất bại. Khi người dùng tick checkbox, ứng dụng có thể cấp cookie dài hạn ngoài session cookie.

~~~text
Form login:
  username + password + remember-me=on
         |
         v
UsernamePasswordAuthenticationFilter
         |
         +-- Auth FAIL → rememberMeServices.loginFail(...)
         |
         +-- Auth SUCCESS
               |
               +-- Session authentication và SecurityContext
               |
               +-- rememberMeServices.loginSuccess(...)
                     |
                     +-- Chọn remember-me? YES
                           → Set-Cookie: remember-me=<signed-token>
                     +-- NO
                           → Không cấp cookie nhớ login
~~~

Khi người dùng quay lại không có `Authentication` trong `SecurityContext`, `RememberMeAuthenticationFilter` dùng `autoLogin` để thử khôi phục danh tính. Sau đó request vẫn đi qua authorization rules.

Một điều kiện quan trọng: cả hai implementation chuẩn đều cần `UserDetailsService`. Nếu ứng dụng xác thực bằng provider đặc biệt không dựa trên `UserDetailsService` (ví dụ một LDAP integration), phải cung cấp service tương ứng để remember-me có thể tải lại user và authorities, hoặc dùng một implementation/luồng khác phù hợp. Không nghĩ rằng bật `rememberMe()` tự tương thích với mọi loại login.

### 6.1. Cài đặt default cookie riêng và checkbox

Trong form login do Spring Security tạo, remember-me thường sử dụng tham số POST `remember-me` (checkbox) và cookie mặc định tên `remember-me`. Tên, key, thời hạn có thể được tùy chỉnh. Nếu dùng form HTML riêng, checkbox phải có `name` phù hợp:

~~~html
<form method="post" action="/login">
  <input name="username" autocomplete="username">
  <input name="password" type="password" autocomplete="current-password">
  <label>
    <input type="checkbox" name="remember-me">
    Ghi nhớ đăng nhập trên thiết bị này
  </label>
  <!-- Khi CSRF bật, form thật phải có CSRF hidden input hợp lệ. -->
  <button type="submit">Đăng nhập</button>
</form>
~~~

Đây là **minh họa HTML form**; nó chưa bao gồm CSRF token, do đó không đủ để POST thành công với CSRF protection mặc định. Khi dùng login page do Spring Security tạo, framework hỗ trợ form và token. Với trang custom, phải xuất CSRF token an toàn và đưa vào request.

Không đặt `alwaysRemember(true)` nếu sản phẩm yêu cầu người dùng chủ động đồng ý. Mặc định checkbox/tín hiệu opt-in có ý nghĩa bảo mật và UX, đặc biệt với thiết bị dùng chung.

## 7. Demo Spring Boot 3.x / Java 17+: session ngắn và remember-me dài

Ta xây ứng dụng có:

- HTTP session timeout ngắn, ví dụ **30 phút** idle.
- Remember-me cookie thời hạn **14 ngày** (chỉ là giá trị minh họa).
- `GET /account/me`: cho phép user đăng nhập trực tiếp **hoặc** khôi phục qua remember-me.
- `GET /account/sensitive`: yêu cầu fully authenticated, không cho một remember-me token một mình đủ quyền.
- Form login mặc định `/login` và logout `/logout`.
- User demo dùng BCrypt, không yêu cầu database ngoài.

Để giữ ví dụ dễ chạy, ta dùng **hash-based remember-me**. Sau đó mục 9 giải thích cách chuyển sang persistent token với JDBC, không trộn hai implementation trong cùng cấu hình.

### 7.1. Dependencies và cấu trúc tệp

Trong Spring Boot Gradle project có plugin và dependency management, cần:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn bổ sung cho dự án Boot** (không phải toàn bộ `build.gradle`). Các tệp:

~~~text
src/main/java/com/example/rememberdemo/
  RememberDemoApplication.java
  SecurityConfig.java
  AccountController.java
src/main/resources/
  application.properties
src/test/java/com/example/rememberdemo/
  RememberMeBehaviorTest.java
~~~

### 7.2. RememberDemoApplication.java

~~~java
package com.example.rememberdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberDemoApplication.class, args);
    }
}
~~~

### 7.3. SecurityConfig.java

~~~java
package com.example.rememberdemo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            @Value("#{systemEnvironment['REMEMBER_ME_KEY'] ?: 'unsafe-local-demo-key-change-me'}")
            String rememberMeKey) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .requestMatchers("/account/sensitive").fullyAuthenticated()
                .requestMatchers("/account/**").authenticated()
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED)
            )
            .formLogin(Customizer.withDefaults())
            .rememberMe(remember -> remember
                .key(rememberMeKey)
                .userDetailsService(users)
                .rememberMeParameter("remember-me")
                .tokenValiditySeconds(14 * 24 * 60 * 60)
            )
            .logout(Customizer.withDefaults());

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("student")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }
}
~~~

**Lưu ý về key demo:** `unsafe-local-demo-key-change-me` trong fallback chỉ để chương trình chạy trên máy phát triển. Trong production, **bắt buộc** cấp `REMEMBER_ME_KEY` là secret ngẫu nhiên đủ mạnh, ổn định giữa các lần khởi động và thống nhất giữa các node. Đừng lưu key thật trong Git hoặc cho phép fallback dễ đoán ở production. Khi đổi key, hash-based remember-me cookies ký bằng key cũ sẽ không còn hợp lệ.

Spring Expression `@Value("#{systemEnvironment['REMEMBER_ME_KEY'] ?: 'unsafe-local-demo-key-change-me'}")` cho phép inject môi trường trước khi cấu hình `rememberMe`. Nếu tổ chức dùng secret manager, thay cơ chế inject nhưng giữ ý nghĩa “secret chỉ server biết và ổn định”.

**Vì sao không kéo dài session lên 14 ngày?** Ta giữ `SessionCreationPolicy.IF_REQUIRED` và session timeout riêng. Remember-me token có thời hạn khác với session. Cookie được cấp chỉ khi login thành công và người dùng chọn option tương ứng.

**Vì sao `fullyAuthenticated()`?** `/account/sensitive` không cho remember-me token một mình đủ điều kiện. Quy tắc này phù hợp thao tác có rủi ro cao nhưng không thay yêu cầu MFA hoặc xác nhận lại mật khẩu theo chính sách sản phẩm.

### 7.4. AccountController.java

~~~java
package com.example.rememberdemo;

import java.util.Map;

import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.annotation.CurrentSecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {
    private final AuthenticationTrustResolver trust =
        new AuthenticationTrustResolverImpl();

    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of("message", "public");
    }

    @GetMapping("/account/me")
    public Map<String, Object> me(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "remembered", trust.isRememberMe(authentication),
            "fullyAuthenticated", trust.isFullyAuthenticated(authentication)
        );
    }

    @GetMapping("/account/sensitive")
    public Map<String, String> sensitive(
            @CurrentSecurityContext(expression = "authentication")
            Authentication authentication) {
        return Map.of("sensitiveFor", authentication.getName());
    }
}
~~~

Controller đọc `Authentication` do Spring Security xác thực. Nó **không** tự so sánh remember-me cookie với `JSESSIONID`, không giải token bằng JavaScript và không tự cấp quyền nhạy cảm. Rule `fullyAuthenticated()` đặt tại filter chain để bảo vệ endpoint trước khi controller chạy.

Với login tương tác thông thường, response `GET /account/me` có thể là:

~~~json
{
  "username": "student",
  "remembered": false,
  "fullyAuthenticated": true
}
~~~

Khi **chỉ** cookie remember-me khôi phục danh tính:

~~~json
{
  "username": "student",
  "remembered": true,
  "fullyAuthenticated": false
}
~~~

Đó là các kết quả **mong đợi theo luồng demo**, không phải dữ liệu ghi nhận từ ứng dụng đã chạy.

### 7.5. application.properties

~~~properties
server.servlet.session.timeout=30m
server.servlet.session.cookie.http-only=true

# Local HTTP chỉ cho demo. Production HTTPS phải cấu hình Secure.
# Không cố tình kéo dài max-age của JSESSIONID bằng 14 ngày.
~~~

Khi triển khai production HTTPS:

~~~properties
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

Thuộc tính `Secure` đảm bảo cookie session chỉ được gửi qua HTTPS (browser có thể xử lý `localhost` khác). `SameSite=Lax` là ví dụ thường phù hợp cho web cùng site, không thay thế CSRF token. **Cấu hình cookie session này không tự động bảo đảm mọi attribute của cookie remember-me giống hệt.** Hãy kiểm tra cả hai cookie thực tế qua DevTools và cấu hình remember-me cookie/response theo chính sách ứng dụng.

### 7.6. Chạy bằng Gradle và dùng form

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Ở browser vào `http://localhost:8080/account/me` khi chưa đăng nhập; trang có thể chuyển sang `/login`. Đăng nhập tài khoản demo `student` / `demo-pass`.

- **Không tick Remember me:** có phiên đăng nhập, nhưng không cấp remember-me cookie dài hạn. Khi phiên mất, user cần login lại.
- **Tick Remember me:** form login vẫn có session như bình thường, đồng thời được cấp thêm cookie remember-me. Khi session mất nhưng remember-me token còn, request mới có thể được xác thực tự động.
- **Thử `/account/sensitive` sau khi chỉ còn remember-me:** ứng dụng yêu cầu login tương tác thay vì coi token nhớ đăng nhập là fully authenticated.

Đừng sử dụng credential demo ngoài localhost. Token remember-me thực tế là secret, không in giá trị trong log/screenshots/ticket.

## 8. MockMvc kiểm tra hai đời sống tách biệt

Test nên cố ý tạo các request **không đính kèm session cũ** nhưng còn nhớ cookie. Nếu tất cả test đều gửi lại `JSESSIONID`, bạn chỉ đang kiểm tra session, chưa chứng minh remember-me hoạt động.

Tạo file `src/test/java/com/example/rememberdemo/RememberMeBehaviorTest.java`:

~~~java
package com.example.rememberdemo;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RememberMeBehaviorTest {

    @Autowired
    private MockMvc mvc;

    private MvcResult signIn(boolean remember) throws Exception {
        MockHttpSession existing = new MockHttpSession();

        var request = post("/login")
            .session(existing)
            .with(csrf())
            .param("username", "student")
            .param("password", "demo-pass");

        if (remember) {
            request.param("remember-me", "on");
        }

        return mvc.perform(request)
            .andExpect(status().is3xxRedirection())
            .andReturn();
    }

    private Cookie rememberCookie() throws Exception {
        Cookie cookie = signIn(true).getResponse().getCookie("remember-me");
        assertNotNull(cookie, "Tick remember-me phải cấp cookie");
        return cookie;
    }

    @Test
    void ordinaryLoginDoesNotIssueLongLivedRememberCookie() throws Exception {
        MvcResult result = signIn(false);
        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void rememberMeWorksWithoutSendingOldHttpSession() throws Exception {
        Cookie cookie = rememberCookie();

        // Không đính kèm JSESSIONID hoặc MockHttpSession từ lúc login.
        mvc.perform(get("/account/me").cookie(cookie))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"))
            .andExpect(jsonPath("$.remembered").value(true))
            .andExpect(jsonPath("$.fullyAuthenticated").value(false));
    }

    @Test
    void rememberMeAloneDoesNotSatisfySensitiveEndpoint() throws Exception {
        Cookie cookie = rememberCookie();

        mvc.perform(get("/account/sensitive").cookie(cookie))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void fullFormSessionCanEnterSensitiveEndpoint() throws Exception {
        MockHttpSession session = new MockHttpSession();

        mvc.perform(post("/login")
                .session(session)
                .with(csrf())
                .param("username", "student")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection());

        mvc.perform(get("/account/sensitive").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.sensitiveFor").value("student"));

        mvc.perform(get("/account/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.remembered").value(false))
            .andExpect(jsonPath("$.fullyAuthenticated").value(true));
    }

    @Test
    void invalidRememberCookieDoesNotAuthenticate() throws Exception {
        Cookie tampered = new Cookie("remember-me", "invalid-token");

        mvc.perform(get("/account/me").cookie(tampered))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

**Vì sao test thứ hai quan trọng nhất?** Nó đăng nhập có checkbox, lấy cookie remember-me rồi gọi `/account/me` **không gửi lại session cũ**. Nếu user vẫn được nhận diện và `remembered=true`, chúng ta chứng minh remember-me là một cơ chế xác thực riêng, không chỉ là kéo dài `JSESSIONID`.

Test thứ ba kiểm tra *step-up*: người dùng được “nhớ” nhưng phải login tương tác cho tài nguyên nhạy cảm. Test thứ tư cho thấy session đăng nhập qua form thực sự đáp ứng `fullyAuthenticated()`.

Trong bộ test, `MockHttpSession` được dùng để mô phỏng phiên. Nó không tái hiện toàn bộ thời gian 14 ngày hay hành vi lưu cookie thực tế của browser. Để kiểm tra expiration, restart, cookie attributes, cluster, nên thêm integration test với embedded container/browser và clock có thể kiểm soát.

Chạy bằng Gradle:

~~~bash
./gradlew test --tests com.example.rememberdemo.RememberMeBehaviorTest
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests com.example.rememberdemo.RememberMeBehaviorTest
~~~

Nếu project/versions/dependencies đúng và assertions pass, Gradle thường báo `BUILD SUCCESSFUL`. Đó là **kết quả mong đợi**, không phải stdout được xác nhận từ việc chạy thử ở đây. Những đoạn Java cần Spring Boot/Security trên classpath nên không thể dùng `javac` riêng lẻ thiếu dependencies.

### 8.1. Những phép thử bổ sung cho môi trường thực

Nên chạy thêm các tình huống:

| Case | Cách tạo | Kết quả mong đợi |
| --- | --- | --- |
| RM-01 | Login không tick checkbox | Không có cookie nhớ đăng nhập mới; chỉ còn phiên thường. |
| RM-02 | Login có tick checkbox | Cookie remember-me được cấp với thời hạn chính sách. |
| RM-03 | Xóa/để hết hạn session nhưng giữ remember cookie | User được nhận diện là **remembered**, không phải fully authenticated. |
| RM-04 | Mất cả session và remember cookie | Request vào endpoint bảo vệ phải login lại. |
| RM-05 | Cookie giả hoặc bị sửa | Auto-login thất bại, không tự cấp quyền. |
| RM-06 | Cookie nhớ hết hạn | Không đăng nhập lại tự động. |
| RM-07 | User đổi password khi dùng hash-based | Cookie cũ không còn hợp lệ nếu cấu trúc hash còn phụ thuộc password đó. |
| RM-08 | Remember-only gọi endpoint fully authenticated | Bị yêu cầu login tương tác/step-up. |
| RM-09 | Logout thông thường | Session bị hủy và cookie hiện tại được dọn; kiểm tra chính sách revocation riêng. |
| RM-10 | Persistent token được thu hồi ở DB | Dù browser còn cookie, token không còn được chấp nhận. |
| RM-11 | Concurrent requests cùng một persistent cookie cũ | Không tạo sự cố đăng xuất/“theft” giả ngoài khả năng xử lý vận hành. |
| RM-12 | Browser khác thiết bị | Không nhận danh tính nếu không có token; nếu bị đánh cắp token, đánh giá phát hiện và thu hồi. |

## 9. Chuyển sang persistent token bằng JDBC khi cần thu hồi tốt hơn

Phần này là một **lựa chọn thay thế** cho cấu hình hash-based ở mục 7, không phải cấu hình đặt đồng thời trên cùng một chain.

Cần có:

- `spring-boot-starter-jdbc` và JDBC driver phù hợp.
- `DataSource` đã khai báo, truy cập được.
- Bảng `persistent_logins` do migration tạo theo schema.
- Secret key ổn định.
- `UserDetailsService` và session/CSRF/cookie policy đã rõ.

Đoạn bean repository (thêm vào lớp `@Configuration` tương ứng):

~~~java
@Bean
PersistentTokenRepository persistentTokenRepository(DataSource dataSource) {
    JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
~~~

Imports cần thiết:

~~~java
import javax.sql.DataSource;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
~~~

Sau đó, **thay** phần `rememberMe(...)` trong bean `SecurityFilterChain` bằng:

~~~java
.rememberMe(remember -> remember
    .key(rememberMeKey)
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .rememberMeParameter("remember-me")
    .tokenValiditySeconds(14 * 24 * 60 * 60)
)
~~~

Biến `persistentTokenRepository` trong đoạn trên là dependency `PersistentTokenRepository` được inject vào method tạo bean chain; **đoạn này là fragment cấu hình**, không phải file Java độc lập. Khi có `tokenRepository(...)`, cấu hình remember-me dùng persistent-token service phù hợp thay vì hash-based mặc định.

Không dùng `InMemoryTokenRepositoryImpl` cho production: nó mất dữ liệu khi restart, không chia sẻ giữa các node và chỉ phù hợp test/demo. Dùng `JdbcTokenRepositoryImpl` hoặc repository production đã được thiết kế thích hợp.

### 9.1. Thu hồi và “logout tất cả thiết bị” phải được định nghĩa

Với persistent token:

- Token có record riêng, server có thể xóa record để vô hiệu hóa nó.
- Implementation Spring Security chuẩn có thể xóa **mọi token của một username** khi logout handler được gọi với `Authentication` phù hợp.
- Muốn thu hồi theo **một thiết bị** phải có device metadata và repository/flow được thiết kế hỗ trợ; schema mặc định chỉ có `username`, `series`, `token`, `last_used`, không tự là hệ thống quản lý thiết bị.
- Thu hồi remember-me token **không đồng nghĩa** tự hủy mọi HTTP session đã đăng nhập trên tất cả browser. Nếu yêu cầu “Logout everywhere”, phải phối hợp session registry/store, access tokens, remember-me tokens và các credential khác theo mô hình của ứng dụng.

**Rủi ro race:** Nếu hai request được gửi cùng một persistent cookie trước khi browser nhận cookie mới, vòng xoay token có thể khiến request sau thấy series/token mismatch và trigger logic nghi theft. Cần test với retry, nhiều tab, network delay, và ưu tiên quản lý phiên sau auto-login để giảm việc liên tục validate một cookie cũ.

### 9.2. Password reset và key rotation

Hash-based remember-me gắn với password/key như dữ liệu chữ ký, nên đổi password/key làm cookie cũ hết giá trị. Với persistent-token remember-me, record lưu riêng **không nhất thiết bị xóa chỉ vì hash mật khẩu thay đổi**; sau reset password hay đổi quyền/ngưng user, ứng dụng nên **chủ động thu hồi persistent tokens**. Tương tự, chính sách xoay secret key cần tính đến các token đang lưu và phiên hiện hữu.

Không để một user bị vô hiệu hóa tiếp tục được nhận danh tính do token nhớ đăng nhập chưa được thu hồi. Tải lại user/status/authorities đúng cách, và test trường hợp khóa tài khoản.

## 10. Cookie bảo mật cho remember-me không giống cấu hình cookie phiên

Hệ thống có thể nhận hai cookie khác nhau:

~~~http
Cookie: JSESSIONID=<short-session-id>; remember-me=<long-lived-token>
~~~

Mỗi cookie là **một secret** có giá trị độc lập. Các thuộc tính cần kiểm tra:

| Thuộc tính | Với session cookie | Với remember-me cookie |
| --- | --- | --- |
| `HttpOnly` | Nên bật để JS không đọc session ID | Nên bật khi JS không cần trực tiếp đọc token |
| `Secure` | Bắt buộc trên HTTPS production | Cũng phải bảo đảm cookie nhớ đăng nhập chỉ đi qua HTTPS |
| `SameSite` | Chọn theo site topology và CSRF policy | Chọn tương thích ngữ cảnh login, không mở cross-site vô cớ |
| `Domain`, `Path` | Chỉ gửi ID tới host/path cần thiết | Giới hạn phạm vi cookie remember-me |
| `Max-Age`/`Expires` | Có thể là session cookie hoặc persistent cookie theo policy | Thường persistent cookie với `tokenValiditySeconds` |
| Rotation/revocation | Session ID rotation/invalidate session | Token riêng; hash-based vs DB persistent có hành vi khác |
| Truy cập qua JS | Không cần đọc ID session | Không cần đọc remember-me token để login |

Cấu hình:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

đặt chính sách cho **session cookie** trong Spring Boot, nhưng **không nên mặc nhiên coi nó cũng cấu hình đầy đủ cookie remember-me**. Remember-me cookie được code `RememberMeServices` quản lý. Hãy xem response `Set-Cookie` thực tế và dùng API/configuration phù hợp phiên bản cho `Secure`, `HttpOnly`, `SameSite` và reverse proxy HTTPS.

Điều cần đánh giá:

1. **HTTPS end-to-end:** không phát token remember-me qua HTTP thật. Reverse proxy phải truyền đúng thông tin scheme, không làm suy giảm cookie security.
2. **Cross-site frontend:** `SameSite=None; Secure` có thể cần cho cookie cross-site, nhưng browser có thể chặn third-party cookie. Nếu khả thi, frontend và API nên chung site/origin để giảm phức tạp.
3. **CSRF:** Cookie remember-me được browser tự gửi, nên các thao tác POST/PUT/DELETE có thể có CSRF risk nếu application cho phép xác thực bằng nó. **Không tắt CSRF vì “chỉ dùng remember-me”.**
4. **XSS:** `HttpOnly` giảm rủi ro JS lấy token, nhưng XSS vẫn có thể thực hiện hành động dưới danh tính user trong browser. Cần chống XSS riêng.
5. **Thiết bị dùng chung:** checkbox nhớ đăng nhập phải là lựa chọn có chủ đích, không nên auto bật trên thiết bị kiosk/public.
6. **Timeout:** remember-me token dài hơn session timeout là ý đồ, nhưng không có nghĩa token được giữ vô hạn hay bỏ qua thời hạn server-side.
7. **Trình duyệt restore session:** đóng/mở browser không phải phép kiểm thử ổn định cho “session đã hết”: các browser có khả năng khôi phục session cookies. Hãy kiểm tra cookie cụ thể hoặc dùng test bỏ session ID rõ ràng.
8. **Cache response nhạy cảm:** bảo vệ dữ liệu nhạy cảm trong cache/browser/proxy không phụ thuộc mỗi cookie.

## 11. Logout: hết session và hết remember-me là hai chuyện khác nhau

Một logout có thể cần nhiều thao tác:

~~~text
POST /logout + CSRF token hợp lệ
       |
       ├─ SecurityContextLogoutHandler
       │    ├─ clear SecurityContext
       │    └─ invalidate HttpSession (theo cấu hình)
       |
       ├─ RememberMeServices logout handler
       │    ├─ xóa remember-me cookie phía browser
       │    └─ persistent implementation có thể xóa token DB
       |
       └─ LogoutSuccessHandler
            └─ redirect /login?logout hoặc response phù hợp
~~~

Các giới hạn:

- Hủy `JSESSIONID` **không tự** làm remember-me token không còn hợp lệ. Nếu remember-me cookie sống sót, browser có thể đăng nhập lại tự động ở request sau.
- Xóa cookie bằng `Set-Cookie: remember-me=; Max-Age=0` trên browser hiện tại không thu hồi bản sao token đã bị đánh cắp trong trường hợp hash-based.
- Với persistent service, logic logout server-side có thể xóa remember-me token của **tất cả phiên nhớ đăng nhập cùng username** nếu Authentication được truyền tới handler; không mặc định là thu hồi từng thiết bị.
- Nếu hệ thống dùng JSON login tự viết, filter không gọi `RememberMeServices.loginSuccess(...)` và logout handlers không tích hợp đúng, có thể không tạo/xóa cookie như kỳ vọng.
- Sau logout, browser vẫn có thể giữ dữ liệu cache hoặc cookie ở domain khác; cần thiết kế hợp đồng logout end-to-end.

**Cần kiểm thử logout bằng một cookie remember-me riêng** sau khi logout/session hết hạn và phân biệt rõ cơ chế hash-based với persistent-token. Không thể kết luận “logout thành công trên mọi nơi” chỉ từ HTTP 302 hoặc 204.

### 11.1. “Không dùng remember-me” và “xóa nhớ đăng nhập” cũng khác nhau

Khi checkbox **không được tick** trong lần login mới, ứng dụng không nhất thiết đã thu hồi mọi persistent token cấp ở các lần login trước. Cần một thao tác riêng “quên thiết bị này” hoặc policy chủ động thu hồi nếu sản phẩm yêu cầu. Với hash-based token, nếu browser vẫn giữ cookie cũ hợp lệ, nó có thể tiếp tục auto-login sau khi session mới hết hạn.

Yêu cầu sản phẩm nên định nghĩa tường minh: bỏ chọn checkbox chỉ **không cấp mới**, hay còn **thu hồi token từng được cấp**? Đừng mặc định hai hành vi tương đương.

## 12. Khi nào nên chọn phương án nào?

| Bài toán sản phẩm | Thiết kế phù hợp hơn | Lý do |
| --- | --- | --- |
| Người dùng chỉ cần giữ login trong một phiên làm việc ngắn | Session HTTP với idle timeout phù hợp | Ít credential dài hạn hơn, logout rõ ràng. |
| “Nhớ tôi 14 ngày” trên máy cá nhân | Remember-me cookie có opt-in và giới hạn phù hợp | Có thể tái xác thực sau khi session cũ kết thúc. |
| Quản lý/thu hồi thiết bị đã ghi nhớ | Persistent token + quản lý bản ghi, metadata thiết bị nếu cần | Có nền tảng server-side để thu hồi. |
| Đăng xuất mọi thiết bị ngay lập tức | Chính sách thu hồi token, hủy session, session registry/store | Không thể chỉ xóa một cookie ở browser hiện tại. |
| Truy cập giao dịch nhạy cảm | `fullyAuthenticated()`, thêm step-up/MFA theo mức độ rủi ro | Remember-me không nên là bảo đảm duy nhất. |
| API machine-to-machine | Token/API credential riêng với rotation, scopes, audience, revocation | Browser remember-me không phải session/token model phù hợp. |
| Sản phẩm có rủi ro cao hoặc thiết bị công cộng | Cân nhắc không cung cấp remember-me | Tránh tăng credential tồn tại lâu dài trên thiết bị. |
| Chỉ muốn user không bị timeout giữa một công việc đang làm | Điều chỉnh idle timeout hợp lý và UX lưu nháp | Không nhất thiết cần remember-me dài hạn. |

**Không có một con số timeout “đúng cho tất cả”.** Lựa chọn phải dựa vào loại dữ liệu, mức rủi ro, hành vi người dùng, khả năng thu hồi, chính sách thiết bị và các yêu cầu tuân thủ. Thời gian 30 phút/14 ngày trong demo chỉ để thấy hai vòng đời khác nhau.

## 13. Những nhầm lẫn và lỗi thường gặp

### Lỗi 1 — Đặt server.servlet.session.timeout=30d rồi gọi là “Remember me”

Đây chỉ là duy trì session lâu hơn, không thêm remember-me token/validation logic. Session store mất dữ liệu, browser mất cookie hoặc logout thì việc tự khôi phục không xảy ra.

### Lỗi 2 — Tăng cookie Max-Age nhưng quên timeout server

Cookie `JSESSIONID` còn 30 ngày không có nghĩa session trên server còn 30 ngày. Cookie có thể trỏ đến một ID đã bị invalidate/evict, tạo hiện tượng “browser vẫn có cookie nhưng lại phải login”.

### Lỗi 3 — User tick checkbox nhưng cookie không được cấp

Kiểm tra form có field đúng tên `remember-me` không; login có thật sự thành công không; `RememberMeServices` có được gắn vào authentication flow không; browser có chặn `Set-Cookie` do `Secure`/`SameSite`/domain/path không.

### Lỗi 4 — Dùng JSON login custom mà không thông báo RememberMeServices

Gọi `AuthenticationManager.authenticate(...)` rồi `saveContext(...)` có thể tạo session login thành công, nhưng **không bảo đảm tự cấp remember-me cookie**. Custom flow cần gọi `loginSuccess` / `loginFail` đúng điều kiện, áp dụng session authentication strategy, CSRF và logout integration. Tránh tự copy Base64 token algorithm vào controller.

### Lỗi 5 — Cookie remember-me có nhưng request vẫn redirect tới login

Kiểm tra: token hết hạn/sai, user không tồn tại hoặc bị khóa, key thay đổi giữa deployments, persistent token record bị thu hồi, request không gửi cookie vì scope/policy, chain không bật `rememberMe()`, hoặc endpoint yêu cầu `fullyAuthenticated()`.

### Lỗi 6 — “Remembered” nên được xem như fully authenticated

Sai. Spring Security phân biệt trust level. Những thao tác nhạy cảm nên yêu cầu xác thực tương tác lại, thậm chí MFA/step-up; không lấy `Authentication.isAuthenticated()` làm bằng chứng đã re-auth gần đây.

### Lỗi 7 — Logout xóa session nhưng lại tự login ngay

Có thể cookie nhớ đăng nhập chưa bị xóa hoặc service/logout handler không được cấu hình. Kiểm tra response `Set-Cookie` dọn cookie nhớ đăng nhập, trạng thái token persistent và request tiếp theo không kèm session.

### Lỗi 8 — Nghĩ xóa cookie đủ thu hồi hash-based token bị đánh cắp

Nếu kẻ khác đã sao chép cookie, browser hiện tại xóa cookie không đụng đến bản sao. Với hash-based, đổi password/key hoặc hết hạn mới làm bản sao không còn hợp lệ theo cơ chế đó; muốn thu hồi cụ thể nên cân nhắc persistent token.

### Lỗi 9 — Key remember-me thay đổi mỗi lần server restart

Các token đã ký bằng key cũ mất hiệu lực, khiến người dùng thỉnh thoảng phải login lại. Tất cả node phục vụ cùng ứng dụng phải đồng nhất key, quản lý bằng secret store và có kế hoạch rotation; không hardcode production secret trong source.

### Lỗi 10 — Persistent token mất khi restart

Sử dụng `InMemoryTokenRepositoryImpl` ở production khiến token không sống qua restart. Dùng JDBC/DB repository có storage bền vững và schema/migration đúng.

### Lỗi 11 — Có token DB nhưng không dọn dữ liệu hết hạn

Logic từ chối token cũ không bảo đảm tự xóa record khỏi bảng. Cần cleanup job có điều kiện và tránh xóa nhầm token còn hợp lệ.

### Lỗi 12 — Mọi tab đồng thời dùng cùng persistent token

Hai request vào cùng lúc có thể gây token mismatch sau rotation, thậm chí kích hoạt cơ chế nghi cookie theft. Cần test concurrency, browser retries và chọn chính sách UX/telemetry; không đơn giản xóa kiểm tra mismatch để “cho đỡ lỗi”.

### Lỗi 13 — Nhầm remember-me cookie với refresh token OAuth

Remember-me thường dành cho website/session-backed form login. Refresh token OAuth2 có protocol, audience, scopes, rotation và revocation riêng. Không đưa remember-me token vào JSON access token của SPA/mobile như một “JWT thay thế”.

### Lỗi 14 — Không bật CSRF vì user không cần nhập mật khẩu

Trình duyệt tự đính kèm cookie remember-me theo scope. Nó vẫn là credential có thể gây CSRF khi backend chấp nhận thao tác thay đổi state. Giữ CSRF protection phù hợp, kiểm tra SameSite và Origin, không coi CORS là cơ chế chặn CSRF.

### Lỗi 15 — Dùng token nhớ đăng nhập làm nhật ký định danh

Đừng log raw remember-me cookie, `JSESSIONID` hoặc token trong table. Dùng correlation ID không nhạy cảm; nếu cần theo dõi thiết bị, thiết kế mã định danh audit riêng. Token sống lâu có độ nhạy cảm cao.

## 14. Quy trình debug khi người dùng bị “quên đăng nhập”

Đi từ nguyên nhân dễ kiểm chứng đến khó:

1. **Có HTTP session hợp lệ không?** Kiểm tra request gửi `JSESSIONID`, server session store còn record và `SecurityContext` đã được lưu.
2. **Người dùng đã opt-in remember-me chưa?** Kiểm tra login form parameter `remember-me` và response có phát cookie nhớ đăng nhập không.
3. **Cookie nhớ đăng nhập có được browser lưu/gửi không?** Xem `Set-Cookie`, `Cookie` trong DevTools; không sao chép giá trị vào log.
4. **Cookie còn trong thời hạn không?** Kiểm tra `Max-Age`/token expiry, clock giữa server/node.
5. **Key có thay đổi không?** Với hash-based, key/password thay đổi có thể vô hiệu token.
6. **Token DB còn không?** Với persistent, tra repository theo series trong công cụ nội bộ đã che secret; xem token rotation/revoke/cleanup.
7. **Chain và filter có đúng không?** `RememberMeAuthenticationFilter` có mặt trong chain của endpoint không? Có filter khác kết thúc trước không?
8. **Endpoint cần fullyAuthenticated hay chỉ authenticated?** Nếu bị redirect vào login ở endpoint nhạy cảm, đó có thể là chính sách bảo vệ đúng.
9. **Có sự kiện logout/reset/khóa user không?** Một thao tác có thể chủ động thu hồi token hoặc session.
10. **Có race giữa nhiều request không?** Persistent-token rotation dễ bộc lộ trong các client gửi nhiều request đồng thời mà giữ cookie cũ.
11. **Có chính sách browser ngăn cookie không?** Cross-origin fetch thiếu `credentials`, SameSite, Secure và third-party cookie restrictions là nguyên nhân phổ biến.
12. **Có session store/cluster không nhất quán không?** Một node không nhìn thấy session/token của node khác có thể khiến login dường như ngẫu nhiên thất bại.

Bảng chẩn đoán:

| Quan sát | Khả năng cao | Bước kiểm tra |
| --- | --- | --- |
| Browser giữ JSESSIONID nhưng GET vẫn 302 | Session server hết hạn hoặc context không còn | Session store/timeout/cookie scope. |
| Có remember-me cookie, GET thường 200 nhưng GET nhạy cảm 302 | `fullyAuthenticated()` đang bảo vệ đúng | Kiểm tra trust level, yêu cầu re-auth. |
| Không thấy cookie nhớ đăng nhập sau login | Không opt-in, form param mismatch, cookie bị chặn | POST params và Set-Cookie. |
| Remember-me hết hiệu lực sau deploy | Hash key/password thay đổi hoặc DB repository mất | Secret consistency và DB persistence. |
| Logout rồi GET vẫn 200 | Cookie remember-me chưa được dọn hoặc token chưa thu hồi | Logout handlers, cookie và token repository. |
| Người dùng bị logout hàng loạt sau nhiều request | Persistent token rotation conflict hoặc chính sách revoke | Quan sát token mismatch và concurrency. |
| Browser khác vào được bằng cùng cookie nhớ đăng nhập | Credential đã bị sao chép và vẫn hợp lệ | Incident response, revoke/rotate/đổi password. |
| Cookie được gửi nhưng Spring không nhận identity | Sai chain/filter/expired token/user status | Security DEBUG có redaction, provider và token store. |

## 15. QA checklist trước khi bật Remember me ở production

| Câu hỏi | Tiêu chí đạt |
| --- | --- |
| Có phân biệt hai thời hạn? | `HttpSession` idle timeout và remember-me token validity được khai báo/kiểm thử riêng. |
| Người dùng có quyền opt-in? | Checkbox hoặc hành động tương đương rõ ràng; không auto remember trên thiết bị công cộng. |
| Cookie được bảo vệ? | HTTPS, Secure, HttpOnly, SameSite, Domain/Path, CORS/CSRF được kiểm tra thực tế. |
| Không cấp nhớ đăng nhập khi login sai? | Test invalid credential không tạo cookie nhớ đăng nhập hữu hiệu. |
| Session hết nhưng remember-me còn có tác dụng? | Test request **không gửi session cũ**, chỉ gửi cookie remember-me. |
| Có giới hạn quyền remember-me? | Endpoint nhạy cảm dùng `fullyAuthenticated()`/step-up phù hợp. |
| Có đường thu hồi? | Hash-based: thời hạn/password/key; persistent: DB revoke và policy logout rõ ràng. |
| Key/DB bền vững qua restart? | Key từ secret manager, cùng trên các node; repository bền vững nếu persistent. |
| Logout không tự auto-login lại? | Test dọn cookie và revoke thực tế, không chỉ xem HTTP 302. |
| Có yêu cầu logout tất cả thiết bị? | Chính sách hủy session, remember-me và các token khác được phối hợp. |
| Có nguy cơ concurrency? | Persistent token rotation được test với nhiều tab/network retries. |
| Không lộ secret? | Không log raw cookie/session/token, password, header Authentication. |
| Xác thực bằng user status còn hợp lệ? | UserDetailsService kiểm tra user hiện tại và quyền cập nhật. |
| Có quan sát và cleanup? | Báo lỗi bất thường, dọn token hết hạn, giới hạn vòng đời credential. |

## 16. Tóm tắt

**Kéo dài một HTTP session** giữ cùng cơ chế `JSESSIONID → HttpSession → SecurityContext` hoạt động lâu hơn. Nó không cung cấp login lại tự động nếu session không còn và có thể tăng thời gian rủi ro khi session ID bị lộ.

**Remember-me** cấp **cookie xác thực riêng** trong một lần login được người dùng cho phép. Khi session cũ không còn, `RememberMeAuthenticationFilter` và `RememberMeServices` có thể xác thực lại và tạo `RememberMeAuthenticationToken`. Việc này không hồi sinh toàn bộ dữ liệu session cũ, và **mức độ tin cậy thấp hơn đăng nhập tương tác** với các endpoint yêu cầu `fullyAuthenticated()`.

- Hash-based remember-me đơn giản nhưng hạn chế thu hồi từng token; đổi password/key/hết hạn là những cách vô hiệu phổ biến.
- Persistent token giữ series/token trên server, xoay token khi auto-login và hỗ trợ thu hồi, đổi lại phải vận hành DB và xử lý concurrency.
- Logout và “quên thiết bị” cần chính sách rõ ràng; xóa cookie session không tự xóa credential remember-me.
- Cookie `Secure`/`HttpOnly`/`SameSite`, HTTPS, CSRF, bảo vệ XSS, session timeout và kiểm tra re-auth vẫn cần thiết.

Khi thiết kế UX **“Ghi nhớ đăng nhập”**, hãy trả lời hai câu độc lập: **“Phiên hiện tại được giữ bao lâu?”** và **“Khi phiên kết thúc, browser được phép chứng minh lại danh tính bằng credential dài hạn nào, trong bao lâu, có thể thu hồi thế nào?”**. Đó là sự khác biệt nền tảng giữa Remember-me và một HttpSession sống lâu.

### Tài liệu tham khảo

- Spring Security 6.5 Reference — Remember-Me Authentication: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html
- Spring Security 6.5 Reference — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 Reference — Logout: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html
- Spring Security 6.5 Reference — CSRF: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 Reference — Database Schema (persistent_logins): https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html
- Spring Security 6.5 API — RememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html
- Spring Security 6.5 API — PersistentTokenBasedRememberMeServices: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
