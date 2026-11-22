# Thời hạn cookie, khóa ký và chính sách bảo vệ dữ liệu lưu trữ — Remember-me trong Spring Security Servlet

Trong ứng dụng web có tính năng **“Ghi nhớ đăng nhập” (remember-me)**, trình duyệt có thể quay lại sau khi HTTP session hết hạn và vẫn được nhận diện mà không phải nhập lại mật khẩu. Tính tiện lợi đó tạo ra **một credential tồn tại lâu hơn phiên đăng nhập thông thường**. Nếu cookie bị đánh cắp, khóa ký bị lộ hoặc database chứa token bị truy cập trái phép, một phiên remember-me có thể trở thành đường quay lại tài khoản của người dùng.

Vì vậy khi thiết kế remember-me với **Spring Security Servlet**, ba câu hỏi phải được quyết định cùng nhau:

1. **Thời hạn:** cookie và token được chấp nhận bao lâu? Đó là thời hạn tuyệt đối hay được gia hạn khi dùng? Điều gì xảy ra khi browser đóng, session hết hạn, người dùng đổi mật khẩu hoặc bị khóa tài khoản?
2. **Khóa ký và bí mật:** cơ chế nào dùng khóa ký/HMAC hoặc giá trị ngẫu nhiên để chống giả mạo? Khóa lưu ở đâu, làm sao chia sẻ giữa nhiều node, rotate ra sao và có thể vô hiệu cookie đã phát không?
3. **Lưu trữ và thu hồi:** token/key được lưu ở browser, server hoặc DB như thế nào? Ai được đọc chúng? Logout, “đăng xuất khỏi mọi thiết bị” và incident response có hiệu lực đến đâu?

Bài này làm rõ hai mô hình remember-me mà Spring Security thường cung cấp: **token-based remember-me** dùng cookie có chữ ký kiểm tra được từ server-side key và thông tin user; **persistent-token remember-me** dùng cặp series/token ngẫu nhiên và repository phía server. Các ví dụ dùng Spring Security 6.x, Java 17+, Spring Boot 3.3.5 và Servlet-based form login. Phần Java/Gradle ở mục thực hành thiết kế cho môi trường học cục bộ, không thay thế hệ thống quản trị session và secret của production.

## 1. Nhận diện đúng remember-me

Một tài khoản có thể được truy cập qua nhiều cơ chế:

| Cơ chế | Credential chính | Vòng đời thường gặp | Ý nghĩa |
| --- | --- | --- | --- |
| Form login thông thường | Username/password ở request đăng nhập | Server xác thực rồi có thể tạo HTTP session | Người dùng chủ động xác thực đầy đủ |
| HTTP session sau đăng nhập | Session cookie, thường là `JSESSIONID` | Theo session policy, timeout, invalidation | Dùng lại SecurityContext đã thiết lập |
| Remember-me | Cookie riêng, thường tên `remember-me` | Thường lâu hơn session; ví dụ vài ngày/tuần | Khôi phục Authentication khi thiếu full session |
| OAuth2 access token | Bearer token hoặc sender-constrained token | Theo issuer/authorization policy | Dùng truy cập API, không tự đồng nghĩa remember-me |
| Refresh token | Token để cấp lại access token theo chính sách issuer | Theo OAuth2 lifecycle | Không phải cookie remember-me của form login |

**Remember-me cookie không phải session cookie.** Có thể xóa hoặc hết hạn HTTP session nhưng cookie remember-me vẫn tồn tại, khiến Spring Security xác thực tự động khi một request sau đi qua security filter chain.

Cũng không nên coi remember-me là login với assurance giống nhập password mới. Spring Security có thể phân biệt **remember-me authentication** với **fully authenticated** khi khai báo authorization rules, giúp yêu cầu người dùng xác thực lại trước thao tác nhạy cảm.

### 1.1. Ranh giới bảo mật chính

- Kẻ có remember-me cookie hợp lệ có thể dùng cookie để thử khôi phục tài khoản nếu không có ràng buộc chống replay khác.
- Thuộc tính `HttpOnly` giảm khả năng JavaScript đọc cookie trực tiếp, nhưng không ngăn một XSS cùng origin thực hiện request thay người dùng.
- `Secure` yêu cầu cookie chỉ gửi qua HTTPS; nó không tự ngăn browser bị nhiễm mã độc hoặc secret bị lộ trong backup.
- `SameSite` có thể hạn chế một số CSRF, không thay thế CSRF protection cho các request thay đổi trạng thái.
- Token-based remember-me không có danh sách token hợp lệ theo từng thiết bị ở server; persistent-token có dữ liệu server nên hỗ trợ quản lý/thu hồi chi tiết hơn, nhưng tăng trách nhiệm bảo vệ DB.

## 2. Luồng remember-me trong Servlet filter chain

Khi người dùng chủ động đăng nhập bằng form và chọn checkbox “Ghi nhớ đăng nhập”, Spring Security có thể phát thêm cookie remember-me bên cạnh session hiện tại. Về sau, khi không có authentication từ session, cơ chế remember-me có thể đọc cookie rồi tạo `Authentication` mới nếu kiểm chứng thành công.

~~~text
Lần đầu người dùng đăng nhập:
Browser -> GET /login -> HTML form có CSRF token
Browser -> POST /login
  username + password + _csrf + remember-me=on
      |
      v
CsrfFilter -> UsernamePasswordAuthenticationFilter
      |
AuthenticationManager kiểm tra mật khẩu thành công
      |
RememberMeServices.loginSuccess(...)
      |
Tạo cookie remember-me và/hoặc bản ghi persistent token
      |
Gửi Set-Cookie cho browser

Sau này, session không còn:
Browser -> GET /account
  Cookie: remember-me=<giá trị đã cấp>
      |
      v
SecurityContext không có fully authenticated principal
      |
RememberMeAuthenticationFilter
      |
RememberMeServices.autoLogin(...)
      |
Kiểm chứng cookie/signature hoặc repository series+token
      |
RememberMeAuthenticationToken -> SecurityContext
      |
Authorization rule:
  authenticated()       -> thường cho qua
  fullyAuthenticated()  -> yêu cầu xác thực đầy đủ
~~~

Đây là sơ đồ khái niệm, không phải chuỗi lớp cố định ở mọi phiên bản. `RememberMeServices` cũng phối hợp với logout và có thể xóa cookie khi authentication thất bại. Nếu cookie hết hạn, không hợp lệ hoặc user bị từ chối, browser phải đăng nhập lại theo flow ứng dụng.

**Chọn checkbox phải thực sự có ý nghĩa**: không bật `alwaysRemember(true)` cho ứng dụng nhạy cảm chỉ để tránh việc user quên tích vào checkbox. Nếu product yêu cầu remember-me mặc định, đó phải là quyết định có threat model, chính sách consent và khả năng tắt/revoke rõ ràng.

## 3. Thời hạn cookie: ba đồng hồ khác nhau

Nói “cookie sống 14 ngày” chưa đủ. Ít nhất cần phân biệt:

1. **Cookie Max-Age/Expires trong browser:** browser được hướng dẫn giữ cookie trong bao lâu. Đây là cơ chế phía client, không thể là nguồn xác nhận duy nhất của server.
2. **Hạn hợp lệ được server kiểm tra:** server có chấp nhận credential ở thời điểm request hay không, ngay cả khi browser vẫn gửi cookie đã cũ?
3. **Chính sách phiên và quyền truy cập:** có yêu cầu đăng nhập lại sau một khoảng thời gian tuyệt đối, sau đổi mật khẩu, khi đánh dấu thiết bị không tin cậy hoặc trước giao dịch nhạy cảm không?

Một cookie browser hết hạn thì browser thông thường không gửi nữa. Nhưng attacker đã sao chép giá trị cookie có thể tự tạo HTTP request mang cookie đó. **Server vẫn phải kiểm tra expiration** thay vì tin rằng browser sẽ không bao giờ gửi giá trị hết hạn.

### 3.1. tokenValiditySeconds là gì?

Trong Spring Security remember-me configuration, `tokenValiditySeconds(int)` thường dùng để đặt thời hạn tính bằng **giây**, chẳng hạn:

~~~java
.rememberMe(remember -> remember
    .tokenValiditySeconds(7 * 24 * 60 * 60))
~~~

Ví dụ trên đặt 604.800 giây, tương ứng **7 ngày**, và chỉ là một mảnh cấu hình thuộc `HttpSecurity`. Giá trị 7 ngày mang tính học tập; không có “7 ngày luôn an toàn” hoặc “14 ngày luôn chuẩn” cho mọi hệ thống.

Thời hạn lý tưởng phụ thuộc:

- Dữ liệu có nhạy cảm không: ngân hàng, y tế, quản trị viên, thay đổi mật khẩu, chuyển tiền.
- Thiết bị là của riêng user hay máy dùng chung.
- Có MFA/step-up authentication hay không.
- Rủi ro cookie theft, khả năng giám sát và thu hồi.
- Kỳ vọng UX của người dùng và chi phí hỗ trợ.
- Có cơ chế absolute lifetime riêng hoặc idle timeout theo policy không.

### 3.2. Thời hạn tuyệt đối và gia hạn trượt

Hai khái niệm dễ bị nhầm:

| Kiểu | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Absolute lifetime | Credential phát ngày 1, hết hạn ngày 8 dù đã dùng thường xuyên | Giới hạn rủi ro kéo dài tối đa |
| Sliding/idle lifetime | Mỗi lần sử dụng hợp lệ có thể gia hạn theo chính sách | Tốt cho UX nhưng credential có thể tồn tại lâu |
| Session inactivity timeout | Session kết thúc sau 30 phút không hoạt động | Không đồng nghĩa remember-me hết hạn |
| Browser session cookie | Cookie không có Max-Age dài hạn | Không đủ để định nghĩa thời hạn hợp lệ phía server |

Token-based remember-me thường mang expiration time trong giá trị đã được ký; server xác minh thời điểm đó và không mặc nhiên cấp lại cookie ở mỗi request theo cách làm expiration tuyệt đối trượt đi mãi.

Persistent-token remember-me có state trong repository với `last_used`, cơ chế đổi token khi auto-login và thời hạn do dịch vụ quy định. Vì vậy cách “gia hạn” thực tế phải kiểm tra theo implementation, policy cookie và dữ liệu server. **Đừng giả định đặt Max-Age 7 ngày sẽ tự tạo absolute limit 7 ngày cho mọi thiết bị nếu server có logic đổi/gia hạn token.** Nếu sản phẩm cần absolute max lifetime, hãy thiết kế và lưu mốc `created_at / expires_at` đáng tin riêng hoặc dùng cơ chế phù hợp.

### 3.3. Thiết kế thời hạn theo hành động

Một chính sách minh họa:

- Đọc dashboard thông thường: remember-me có thể chấp nhận trong 7 ngày trên thiết bị cá nhân, tùy threat model.
- Đổi password, thêm phương thức thanh toán, xuất dữ liệu mật, thay đổi quyền admin: **yêu cầu fully authenticated**, xác thực lại hoặc step-up MFA.
- Tài khoản bị khóa/nghi lộ: ngừng chấp nhận remember-me theo trạng thái server.
- User chọn “không ghi nhớ”: không cấp remember-me cookie.
- User chọn “đăng xuất khỏi mọi thiết bị”: vô hiệu các remembered credentials theo thiết kế; token-based stateless không cung cấp điều này từng thiết bị nếu không bổ sung state.

Đừng dùng `authentication.isAuthenticated()` đơn thuần để xác định “đã nhập password gần đây”. Remember-me authentication thường cũng có cờ authenticated, nhưng framework cho phép phân biệt bằng `fullyAuthenticated()` và trust resolver.

## 4. Token-based remember-me: cookie được ký như thế nào?

Spring Security có `TokenBasedRememberMeServices`. Nó có thể phát cookie chứa thông tin để server **tự kiểm chứng bằng khóa ký**, không cần một bảng token per-device cho từng cookie.

Một định dạng token-based remember-me thường biểu diễn (sau base64) các phần như:

~~~text
username : expiryTime : algorithmName : signature
~~~

Chữ ký được tính từ dữ liệu người dùng, hạn sử dụng, password hash và **application key** theo cơ chế cụ thể của Spring Security. Không nên sao chép công thức hoặc “tự ký giống Spring Security” vào ứng dụng khác: định dạng/thuật toán và cách migration có thể phụ thuộc phiên bản.

### 4.1. Chữ ký bảo vệ tính toàn vẹn, không mã hóa nội dung

Trong token-based design:

- **Signature/MAC** giúp server phát hiện username/expiry bị sửa mà không có khóa.
- **Base64 không phải encryption**; dữ liệu như username hoặc thời hạn có thể bị nhìn thấy.
- Cookie bearer bị **đánh cắp** vẫn có thể được replay trước khi hết hạn; không cần attacker sửa signature.
- Secret key bị lộ có thể cho phép giả mạo token theo cơ chế thuật toán/khóa và dữ liệu liên quan, làm ảnh hưởng nhiều tài khoản.
- Thay đổi password hash có thể khiến token-based remember-me cũ không còn hợp lệ vì hash là một phần dữ liệu liên quan tới signature.

Không lưu password hoặc signing key trong cookie. Đừng log token nguyên vẹn. Nếu cần correlation, log một id không bí mật và đã được phê duyệt, thay vì hash tùy tiện toàn bộ cookie vào log có thể trở thành định danh theo dõi.

### 4.2. Khóa ký phải ổn định và đủ mạnh

Trong Spring Security DSL, `.key(...)` đặt một secret dùng cho remember-me token-based services và để cấu hình thành phần xác thực remember-me tương ứng.

**Yêu cầu vận hành:**

1. Sinh key bằng nguồn ngẫu nhiên mật mã; không dùng `"mySecret"` hoặc chuỗi đoán được.
2. Đặt key trong secret manager/KMS hoặc environment được bảo vệ, **không commit vào repository**.
3. Phân tách key theo môi trường dev/staging/prod, giữa các ứng dụng và trust domains.
4. Tất cả node cùng phục vụ remember-me cookie tương ứng phải có key nhất quán trong thời gian vận hành; nếu node A và B khác key, browser có thể login ở A rồi bị từ chối trên B.
5. Có quyền truy cập tối thiểu, audit và quy trình rotation khẩn cấp.
6. Không biến logging, health endpoint, startup exception hoặc config debug thành nơi in secret.
7. Theo dõi phạm vi ảnh hưởng nếu key lộ: có thể phải rotate key, buộc tái xác thực, điều tra nơi token có thể bị giả mạo.

**Khóa ký khác password encoder**. Spring Security có thể dùng BCrypt/Argon2 để lưu password, còn remember-me token-based dùng application key để chống sửa cookie. Thay đổi `PasswordEncoder` cũng có thể tác động đến token-based signatures nếu password hash đã lưu đổi; không coi đây là chiến lược thu hồi thay thế hệ thống revoke bài bản.

### 4.3. Key rotation làm mất remember-me cũ hay không?

Với token-based model đơn giản và chỉ một key đang được chấp nhận, **thay key thường khiến các cookie ký bằng key cũ không xác minh được**. Đây có thể là biện pháp “đăng xuất remember-me hàng loạt” trong sự cố lộ khóa, nhưng có tác động UX tới toàn bộ user.

Nếu muốn có giai đoạn chấp nhận key cũ/key mới, cần thiết kế **version/key-id** và lớp verifier tương thích có hạn ngắn, audit và mốc loại bỏ old key. Spring Security DSL cơ bản không tự tạo hệ thống key ring/rollover phức tạp cho ứng dụng của bạn.

Không rotate key hàng ngày rồi bất ngờ phá kỳ vọng “ghi nhớ 7 ngày” nếu chưa thông báo và chưa có test multi-node. Ngược lại, khi nghi key đã lộ, **không giữ old key được chấp nhận quá lâu chỉ để bảo toàn UX**.

### 4.4. Thu hồi từng thiết bị khó hơn persistent token

Một token-based cookie được verify từ signature/expiry có thể hợp lệ mà server không biết danh sách “thiết bị A, B, C đang giữ token nào”. Vì vậy:

- Logout hiện tại có thể xóa cookie **trong browser gửi logout**, nhưng bản sao bị attacker giữ trước đó có thể còn được chấp nhận tới expiry nếu không có điều kiện revoke khác.
- Đổi mật khẩu có thể vô hiệu token dựa trên old password hash, nhưng cần kiểm thử chính xác cách ứng dụng lưu UserDetails và reset.
- Khóa account có thể từ chối auto-login nếu UserDetailsService và account-status checks được thực thi đúng.
- Muốn revoke từng thiết bị hoặc “logout all sessions” có thể cần state/denylist/credential version hoặc chuyển sang persistent-token model.

**Không quảng cáo “logout đã thu hồi mọi token” chỉ vì HTTP response có Set-Cookie xóa remember-me cookie trên một trình duyệt.**

## 5. Persistent-token remember-me: series + token trong database

Spring Security có `PersistentTokenBasedRememberMeServices` và `PersistentTokenRepository`. Khi user chọn remember-me, server cấp một cặp ngẫu nhiên gồm:

- **series**: định danh chuỗi token, giúp tìm record thuộc thiết bị/phiên remembered.
- **token**: secret hiện tại cần khớp với record trong repository.
- **username/last_used** và metadata khác do implementation/DB chính sách quản lý.

Cookie thường mang cặp series/token dưới dạng mã hóa biểu diễn (ví dụ base64), **không phải encrypted storage**. Khi request hợp lệ đến, server tra series, kiểm tra token và thông thường **thay token** trong record, cấp cookie mới để giảm khả năng dùng lại token đã được sử dụng.

~~~text
Browser:
  Cookie: remember-me = encode(series_A, token_1)
                |
                v
PersistentTokenBasedRememberMeServices
                |
                v
PersistentTokenRepository:
  lookup series_A -> username, current token_1, last_used
                |
      +---------+----------+
      |                    |
token mismatch           token match
      |                    |
reject + xử lý          load user, expiry/status checks
nghi ngờ reuse            |
                           v
                     rotate token_1 -> token_2
                     UPDATE repository
                           |
                           v
                     Authentication
                     Set-Cookie(new token_2)
~~~

Đây là mô hình cơ chế, không phải contract rằng mọi failure đều có cùng HTTP status hoặc response. Implementation có cơ chế xử lý token mismatch như dấu hiệu có thể có cookie theft, và có thể xóa các token của user; các request đồng thời/multiple tabs cần test để tránh false positive do token rotation race.

### 5.1. Tại sao persistent token có lợi cho thu hồi?

Vì server giữ record, bạn có thể:

- Xóa remember-me tokens của một tài khoản sau đổi password hoặc nghi ngờ sự cố.
- Xóa token của một series/thiết bị nếu repository và service quản lý device được mở rộng phù hợp.
- Đặt policy khóa account, hết hạn, idle lifetime và audit theo device/session.
- Phân tích token reuse bất thường để cảnh báo rủi ro.
- Áp dụng thu hồi mà không phải đổi global signing key cho toàn bộ user.

**Nhưng:** SQL schema mặc định không lưu toàn bộ thông tin thiết bị, absolute expiration hoặc nhiều trường policy đặc thù. Muốn giao diện “xem tất cả thiết bị được nhớ”, trạng thái active/revoked và audit tin cậy, cần bổ sung schema và service được thiết kế rõ.

### 5.2. PersistentTokenRepository không làm token tự động an toàn trong DB

Một SQL schema phổ biến mà Spring Security dùng cho JDBC repository:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

`JdbcTokenRepositoryImpl` mặc định sử dụng các trường tương tự cho series/token. **Giá trị token lưu trong bảng là credential nhạy cảm theo cơ chế**; ở kiểu triển khai mặc định, không nên giả định token đã được hash một chiều. Nếu DB, SQL logs, dumps hoặc backups bị đọc trái phép, nguy cơ replay và chiếm phiên remember-me phải được xem xét.

Để bảo vệ lưu trữ:

- Mã hóa database disk/volume/backups **at rest**, và encrypt in transit tới DB.
- Hạn chế `SELECT`, đặc biệt ở bảng token, bằng service account có quyền tối thiểu; không dùng DB credentials quyền admin trong app.
- Không trả `series/token` trong API response quản trị, exports hoặc support tooling.
- Không in table rows trong access logs, query logs, traces, exception output, backup samples.
- Bảo vệ backup và retention/restore, giới hạn thời gian lưu dữ liệu hết hạn/revoked.
- Nếu threat model yêu cầu token **không xuất hiện plaintext trong DB**, hãy thiết kế custom repository/service hỗ trợ xác minh bằng hash/HMAC phù hợp **và rotation**, kiểm thử với framework; không chỉ thay cột token thành hash rồi vẫn dùng `JdbcTokenRepositoryImpl` mặc định vì logic so sánh của dịch vụ có thể không còn khớp.
- Cân nhắc khóa mã hóa ngoài DB với KMS/secret manager nếu lưu encrypted token; quản lý recovery/rotation và backup keys.

### 5.3. Token mismatch và concurrent requests

Persistent-token rotation có một trade-off quan trọng:

1. Request 1 và request 2 gần như cùng lúc đều mang cookie token_1.
2. Request 1 được xử lý trước: token_1 hợp lệ → DB cập nhật thành token_2.
3. Request 2 đến sau với token_1: repository hiện ghi token_2 → mismatch.
4. Framework có thể coi mismatch là dấu hiệu cookie bị đánh cắp/replay và làm sạch tokens để bảo vệ user.

Vì vậy không nên xây logic **bỏ qua token mismatch** chỉ để các tab không bị logout; điều đó làm suy yếu phát hiện replay. Thay vào đó, cần test request concurrency, chiến lược retry/UX và đánh giá implementation/chính sách theo yêu cầu thực. Nếu ứng dụng rất nhạy cảm, hãy chấp nhận một số re-login an toàn thay vì fail-open.

### 5.4. Tên key trong persistent services dễ gây nhầm

Trong một số constructor/configuration, persistent remember-me cũng yêu cầu `key` để tạo/kiểm tra `RememberMeAuthenticationToken` cùng remember-me authentication provider. Nhưng **cặp series/token ngẫu nhiên và repository mới là yếu tố cốt lõi để kiểm tra persistent cookie**, không phải giả định rằng mỗi persistent cookie đều được MAC bằng key giống token-based mode.

Hệ quả: đổi signing key **không tự động thay thế việc xóa persistent token records**. Để bảo đảm revoke persistent remembered clients, phải xử lý repository/session lifecycle. Đừng dùng rotation key như lời hứa “đã xóa mọi cookie của thiết bị bị mất” nếu DB vẫn chấp nhận series/token cũ.

## 6. So sánh token-based và persistent-token

| Tiêu chí | Token-based (stateless signature) | Persistent-token (stateful series/token) |
| --- | --- | --- |
| Cookie mang gì? | Thông tin xác thực tự kiểm chứng + expiry + signature | Series và secret token ngẫu nhiên |
| Bản ghi theo cookie ở DB? | Không bắt buộc | Có |
| Cơ sở xác minh | Key + dữ liệu người dùng + expiry/signature | Repository record + token match + user status |
| Thời hạn | Thường expiry ký trong cookie | Token validity + last-used/rotation theo service |
| Thu hồi từng thiết bị | Khó nếu không thêm state | Khả thi khi mở rộng repository/device records |
| Đăng xuất mọi thiết bị | Cần invalidation rộng hoặc bổ sung state | Có thể xóa tất cả persistent tokens của user |
| Ảnh hưởng key signing bị lộ | Rất nghiêm trọng với việc giả mạo token-based | Key vẫn cần bảo vệ; token records/repository là ranh giới chính |
| DB token leak | Không có bảng token riêng mặc định | Phải xem như rò rỉ credential nhạy cảm |
| Request concurrent | Thường không có rotation DB mỗi lần | Có thể gặp token-rotation race |
| Multi-node | Phải chia sẻ key/password user store nhất quán | Phải chia sẻ DB/repository và config nhất quán |
| Quy mô vận hành | Đơn giản về storage, khó revoke riêng | Có DB/cleanup/caching, đổi lại quản lý lifecycle tốt hơn |
| Khi phù hợp | Web app nhỏ, rủi ro chấp nhận được, TTL ngắn và không cần device revoke | Ứng dụng cần quản lý remembered sessions, revoke theo device/account |

**Không chọn token-based chỉ vì “không phải dùng DB” nếu product yêu cầu logout mọi thiết bị, thu hồi tức thời hoặc audit theo thiết bị.** Ngược lại, không chọn persistent-token mà quên bảo vệ DB, vì lúc đó bạn đã tạo một kho bearer credentials mới.

## 7. Chính sách cookie: Secure, HttpOnly, SameSite, Path, Domain

Một remember-me cookie là credential. Cookie attributes giúp giảm bề mặt tấn công, nhưng **không một flag nào biến cookie thành không thể bị đánh cắp**.

| Thuộc tính | Ý nghĩa | Lưu ý triển khai |
| --- | --- | --- |
| `Secure` | Browser chỉ gửi cookie qua HTTPS | Bắt buộc trong production HTTPS; kiểm tra reverse proxy/TLS termination |
| `HttpOnly` | JavaScript bình thường không đọc trực tiếp cookie | XSS vẫn có thể tạo request cùng origin; không thay thế XSS defense |
| `SameSite=Lax/Strict/None` | Giới hạn một số tình huống gửi cookie cross-site | Chọn theo login/SSO/navigation; `None` thường yêu cầu `Secure` |
| `Path` | Giới hạn URL path browser gửi cookie | Hạn chế scope không cần thiết; không xem là ranh giới ứng dụng độc lập |
| `Domain` | Quy định cookie host/subdomain scope | Tránh chia sẻ cho toàn bộ subdomains nếu không có lý do |
| `Max-Age/Expires` | Browser giữ cookie tới hạn được hướng dẫn | Server phải tự reject token hết hạn/thu hồi |
| Cookie name | Phân biệt remember-me với session/cookie khác | Cần thống nhất logout cleanup, proxy và các app cùng domain |

### 7.1. HTTPS qua reverse proxy

Một sự cố thường gặp: TLS kết thúc ở load balancer, Spring app nhận request HTTP nội bộ và không nhận ra original scheme là HTTPS. Nếu framework dựa vào request secure status để quyết định cookie `Secure`, cookie có thể bị set sai.

Cần kiểm soát trusted forwarded headers/proxy configuration theo Spring Boot infrastructure policy và kiểm tra **Set-Cookie header thật** từ browser qua HTTPS. Không blindly tin các forwarded headers do client public tự gửi; gateway phải strip/overwrite headers trước khi chuyển nội bộ.

### 7.2. Session cookie settings không nhất thiết áp dụng remember-me cookie

Thuộc tính như:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

thường điều khiển **session cookie** do servlet container quản lý. **Không mặc định cho rằng chúng đã cấu hình đầy đủ cookie `remember-me`** do RememberMeServices phát hành. Cần kiểm tra API/cookie settings của Spring Security version và Set-Cookie response thực tế.

Nếu dùng custom `RememberMeServices`, phải kiểm soát flags, maxAge, path, domain và SameSite theo chính sách; không thêm Set-Cookie header thứ hai cùng tên sai thuộc tính rồi gây shadowing.

### 7.3. SameSite và CSRF

Remember-me cookie có thể được browser tự gửi, tương tự session cookie, nên một ứng dụng form login dùng cookie vẫn phải đánh giá CSRF. SameSite giúp hạn chế một số cross-site interactions nhưng không thay thế token CSRF cho state-changing endpoints.

Đặc biệt, tính năng remember-me có thể khôi phục Authentication từ cookie trên request mà user chưa nhập lại password. Nếu API POST dùng cookie auth và không có CSRF protection phù hợp, attacker có thể tìm cách gây thao tác trái ý trong bối cảnh browser.

## 8. Ví dụ Spring Boot 3.3.5: remember-me token-based cho form login

Ví dụ thực hành tạo một web app có:

- `GET /login`: trang HTML/Thymeleaf và checkbox `remember-me`.
- `POST /login`: Spring Security xử lý password, CSRF và lựa chọn remember-me.
- `GET /account`: cho phép người dùng fully authenticated **hoặc** remember-me authenticated xem thông tin thông thường.
- `GET /sensitive`: yêu cầu `fullyAuthenticated()`, không chỉ có remember-me.
- `POST /logout`: logout đúng flow CSRF, xóa cookie ở browser.
- Một user in-memory `learner/demo-pass` chỉ dành cho local test.

**Điểm cần hiểu trước:** demo in-memory user dùng BCrypt hash mới mỗi lần ứng dụng restart, nên hash thay đổi và cookie token-based cũ có thể không còn hợp lệ sau restart. Đây là đặc điểm dữ liệu demo, **không phải lỗi cần tắt key signing**. Production phải dùng persistent user store với password hashes ổn định, kết hợp signing key ổn định giữa các instance.

### 8.1. Cấu trúc project

~~~text
remember-me-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/remember/
    │   │   ├── RememberMeApplication.java
    │   │   ├── SecurityConfiguration.java
    │   │   └── PageController.java
    │   └── resources/
    │       ├── application.properties
    │       └── templates/login.html
    └── test/java/example/remember/
        └── RememberMeTests.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'remember-me-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp `src/main/resources/application.properties`:

~~~properties
# Ứng dụng không khởi động nếu thiếu biến môi trường APP_REMEMBER_ME_KEY.
# Secret phải do môi trường cung cấp, không ghi vào Git.
app.remember-me.key=${APP_REMEMBER_ME_KEY}
~~~

Để chạy local, gán một signing key đủ dài và ngẫu nhiên trong environment. Ví dụ trên Linux/macOS có OpenSSL:

~~~bash
export APP_REMEMBER_ME_KEY="$(openssl rand -hex 32)"
gradle test
gradle bootRun
~~~

Trong PowerShell trên Windows, có thể tạo 32 byte từ CSPRNG của .NET:

~~~powershell
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$env:APP_REMEMBER_ME_KEY = [System.BitConverter]::ToString($bytes).Replace("-", "")
gradle test
gradle bootRun
~~~

Các ví dụ trên tạo key trong môi trường **của lần chạy hiện tại**; không ghi key vào source repo. Với deployment thật, sử dụng secret manager và thực hiện rotation theo quy trình kiểm soát truy cập. Cả test bên dưới cũng cấu hình key riêng chỉ dùng cho test.

### 8.2. Main class

Tệp `src/main/java/example/remember/RememberMeApplication.java`:

~~~java
package example.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberMeApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberMeApplication.class, args);
    }
}
~~~

### 8.3. SecurityConfiguration

Tệp `src/main/java/example/remember/SecurityConfiguration.java`:

~~~java
package example.remember;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    private static final int REMEMBER_FOR_SECONDS = 7 * 24 * 60 * 60;

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UserDetailsService users,
            @Value("${app.remember-me.key}") String signingKey)
            throws Exception {

        if (signingKey.length() < 32) {
            throw new IllegalStateException(
                "Remember-me signing key is too short");
        }

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/sensitive").fullyAuthenticated()
                .requestMatchers("/account").authenticated()
                .anyRequest().denyAll())

            .formLogin(form -> form
                .loginPage("/login")
                .defaultSuccessUrl("/account", true)
                .permitAll())

            .rememberMe(remember -> remember
                .rememberMeParameter("remember-me")
                .userDetailsService(users)
                .key(signingKey)
                .tokenValiditySeconds(REMEMBER_FOR_SECONDS))

            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout"))

            // Không tắt CSRF: POST /login, POST /logout cần token.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}
~~~

**Giải thích chính sách cấu hình:**

- `tokenValiditySeconds(REMEMBER_FOR_SECONDS)` đặt thời hạn nhớ ở mức 7 ngày trong demo. Cookie browser không phải nguồn xác định duy nhất; remember-me service cũng kiểm tra token.
- `.key(signingKey)` cung cấp key do môi trường đưa vào; không sinh key ngẫu nhiên mới ở mỗi lần khởi động nếu bạn muốn cookie tồn tại qua restart/multi-node.
- `userDetailsService(users)` giúp remember-me tìm user và kiểm tra trạng thái/chi tiết cần thiết.
- Checkbox `remember-me` phải được gửi đúng parameter. Không dùng `alwaysRemember(true)`, tránh tự cấp remember-me cookie khi user không chọn.
- `/account` chỉ yêu cầu `authenticated()`, có thể nhận một RememberMeAuthenticationToken.
- `/sensitive` yêu cầu `fullyAuthenticated()`, nên remember-me-only không đủ; phải đi qua bước xác thực đầy đủ theo policy.
- Không cấu hình `csrf().disable()`, nên form login/logout vẫn được bảo vệ.

**Chú ý khi dùng demo trên HTTP localhost:** trong production phải chạy HTTPS và bảo đảm remember-me cookie có Secure/HttpOnly/SameSite theo policy. Đừng để ví dụ localhost trở thành lý do phát cookie không Secure trên internet. Có thể cần cấu hình `useSecureCookie`/cookie settings của RememberMeServices và kiểm tra reverse proxy forwarded headers tùy phiên bản.

### 8.4. MVC Controller

Tệp `src/main/java/example/remember/PageController.java`:

~~~java
package example.remember;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ResponseBody;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/account")
    @ResponseBody
    public String account(Authentication authentication) {
        return authentication.getName()
            + ":" + authentication.getClass().getSimpleName();
    }

    @GetMapping("/sensitive")
    @ResponseBody
    public String sensitive() {
        return "fully-authenticated-only";
    }
}
~~~

Trong `/account`, output của Authentication class là để **học**, không phải response API production nên công khai mọi thông tin về security implementation. Dùng class name giúp thấy sự khác nhau giữa full login và remembered login; ứng dụng thật nên trả về dữ liệu tối thiểu được phép.

### 8.5. Thymeleaf login.html

Tệp `src/main/resources/templates/login.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
    <h1>Đăng nhập</h1>

    <p th:if="${param.error}">Đăng nhập không thành công.</p>
    <p th:if="${param.logout}">Đã đăng xuất.</p>

    <form th:action="@{/login}" method="post">
        <label>
            Tên tài khoản:
            <input type="text" name="username" required>
        </label>
        <label>
            Mật khẩu:
            <input type="password" name="password" required>
        </label>
        <label>
            <input type="checkbox" name="remember-me" value="on">
            Ghi nhớ đăng nhập trên thiết bị này
        </label>
        <button type="submit">Đăng nhập</button>
    </form>
</body>
</html>
~~~

Tích hợp Thymeleaf + Spring MVC thường tự thêm hidden CSRF field cho form dùng `th:action`. Hãy kiểm tra HTML **được render thật** trong browser; không chỉ nhìn source template. Một POST thiếu CSRF token có thể trả 403 dù password đúng. Checkbox là opt-in: nếu không tích, request không có `remember-me=on`.

Logout trong demo dùng Spring Security POST /logout (thay vì tự viết endpoint GET). Nếu cần nút logout trên trang account, thêm một form POST /logout có CSRF token được render đúng; không đổi logout thành GET để tránh lỗi 403.

## 9. MockMvc: chứng minh “ghi nhớ” khác “đang có session”

Tệp `src/test/java/example/remember/RememberMeTests.java`:

~~~java
package example.remember;

import jakarta.servlet.http.Cookie;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties =
    "app.remember-me.key=test-only-long-remember-me-key-not-for-prod-2026")
@AutoConfigureMockMvc
class RememberMeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void loginWithoutCheckboxDoesNotIssueRememberMeCookie()
            throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();

        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void checkboxIssuesCookieWithConfiguredMaxAge() throws Exception {
        MvcResult result = rememberedLogin();

        Cookie cookie = result.getResponse().getCookie("remember-me");
        assertNotNull(cookie);
        assertEquals(7 * 24 * 60 * 60, cookie.getMaxAge());
    }

    @Test
    void rememberMeCookieAloneRestoresIdentityWithoutSession()
            throws Exception {
        MvcResult login = rememberedLogin();
        Cookie rememberCookie =
            login.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        // Chỉ gửi remember-me cookie, KHÔNG gửi MockHttpSession.
        mockMvc.perform(get("/account").cookie(rememberCookie))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "learner:RememberMeAuthenticationToken"));
    }

    @Test
    void sensitiveEndpointRejectsRememberedIdentity()
            throws Exception {
        MvcResult login = rememberedLogin();
        Cookie rememberCookie =
            login.getResponse().getCookie("remember-me");
        assertNotNull(rememberCookie);

        mockMvc.perform(get("/sensitive").cookie(rememberCookie))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void missingCookieCannotAccessAccount() throws Exception {
        mockMvc.perform(get("/account"))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void forgedCookieDoesNotAuthenticate() throws Exception {
        Cookie forged = new Cookie("remember-me", "not-a-valid-token");

        mockMvc.perform(get("/account").cookie(forged))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void badPasswordDoesNotIssueRememberMeCookie()
            throws Exception {
        MvcResult result = mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "bad-pass")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?error"))
            .andReturn();

        assertNull(result.getResponse().getCookie("remember-me"));
    }

    @Test
    void loginWithoutCsrfIsDenied() throws Exception {
        mockMvc.perform(post("/login")
                .param("username", "learner")
                .param("password", "demo-pass")
                .param("remember-me", "on"))
            .andExpect(status().isForbidden());
    }

    private MvcResult rememberedLogin() throws Exception {
        return mockMvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo-pass")
                .param("remember-me", "on"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/account"))
            .andReturn();
    }
}
~~~

**Điều test chứng minh:**

- Không chọn checkbox → không có cookie remember-me được phát từ login thành công.
- Chọn checkbox → response có cookie và Max-Age kỳ vọng 604.800 giây.
- Chỉ dùng remember-me cookie, **không mang session từ lần login**, vẫn có thể khôi phục danh tính khi token hợp lệ.
- `fullyAuthenticated()` không coi remembered-only authentication là đủ cho endpoint nhạy cảm.
- Cookie sai/giả và password sai không cấp quyền.
- CSRF vẫn có hiệu lực ở POST login.

**Điều test chưa chứng minh:** key rotation giữa nhiều node, cookie theft/replay ở browser thật, expiry theo đồng hồ thời gian dài, cách Secure/SameSite được set sau reverse proxy, persistent-token database behavior, hoặc signing key đã được quản lý bằng KMS. Những nội dung đó cần kiểm thử triển khai phù hợp riêng.

### 9.1. Chạy thử

Trên Linux/macOS, sau khi cấp biến môi trường key:

~~~bash
gradle test
gradle bootRun
~~~

Nếu có wrapper thì dùng `./gradlew test` / `./gradlew bootRun`. Trên Windows dùng `gradlew.bat test` / `gradlew.bat bootRun`. Code mẫu phụ thuộc Spring Boot jars nên không thể chạy đơn thuần bằng `javac`/`java` không có classpath.

Dùng browser mở `http://localhost:8080/login`, nhập `learner / demo-pass`, tích checkbox và đăng nhập. Mở DevTools → Application/Cookies để xem cookie remember-me. Trong môi trường học có thể xóa riêng JSESSIONID rồi truy cập `/account` để quan sát remember-me khôi phục danh tính.

Không gửi token/cookie thật qua ảnh chụp hoặc chat. Trên HTTPS production, kiểm tra Set-Cookie có flags đáp ứng policy, đặc biệt `Secure`, `HttpOnly`, `SameSite`, domain/path và max-age.

## 10. Tích hợp persistent-token khi có database

Nếu sản phẩm cần revoke remembered devices, có thể sử dụng `PersistentTokenRepository` và `JdbcTokenRepositoryImpl`. Đây là **biến thể cấu hình**, không ghép tự động vào demo token-based ở mục 8. Cần datasource, schema migration và access control DB.

### 10.1. Repository bean

~~~java
@Bean
PersistentTokenRepository persistentTokenRepository(
        DataSource dataSource) {

    JdbcTokenRepositoryImpl repository =
        new JdbcTokenRepositoryImpl();
    repository.setDataSource(dataSource);
    return repository;
}
~~~

Đây là mảnh code cần import `javax.sql.DataSource`, `PersistentTokenRepository`, `JdbcTokenRepositoryImpl` và `@Bean`. Đừng bật tạo bảng tự động trên startup production nếu cơ sở dữ liệu đang dùng Flyway/Liquibase hoặc DBA quản lý schema.

### 10.2. Đổi remember-me DSL

~~~java
.rememberMe(remember -> remember
    .rememberMeParameter("remember-me")
    .userDetailsService(users)
    .tokenRepository(persistentTokenRepository)
    .key(signingKey)
    .tokenValiditySeconds(14 * 24 * 60 * 60))
~~~

Đây là mảnh cấu hình nằm trong `SecurityFilterChain` có bean `PersistentTokenRepository` và nguồn user phù hợp. Khi có `tokenRepository(...)`, Spring Security có thể dùng persistent-token services thay vì token-based services, nhưng cần kiểm tra actual filter/services trên phiên bản đang deploy.

**Quan trọng:** tham số `key` không biến series/token cookie thành MAC stateless giống token-based. Nếu muốn revoke token cụ thể, phải quản lý repository; **thay key alone không phải API revoke toàn bộ series**.

### 10.3. Migration database

Một schema tối thiểu:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Dùng migration version, index/constraints và policy quyền của DB. Không để người dùng ứng dụng truy cập trực tiếp bảng này qua API/ORM generic. Bảng chứa credentials và dấu vết authentication; cần retention/data deletion policy theo yêu cầu sản phẩm/pháp lý.

### 10.4. Logout và revoke có thật sự xảy ra không?

- **Logout ở browser hiện tại:** service có thể xóa cookie và persistent records theo logic của Spring Security, tùy configuration. Kiểm thử logout handler thực tế.
- **Logout khỏi mọi thiết bị:** thường yêu cầu xóa mọi persistent-token records thuộc username/account hoặc áp dụng credential version/revocation state trên server; không chỉ xóa cookie browser hiện tại.
- **Đổi password:** đặt chính sách xóa/rotate remember-me records khi password thay đổi nếu muốn chặn cookie cũ.
- **Khóa user/bị nghi compromise:** chặn auto-login, xóa token records và có cơ chế thông báo.
- **Xóa tài khoản:** xóa records và backup/retention theo policy; không để token orphaned.

Đừng chỉ dựa vào `Cookie Max-Age=0` để tuyên bố server đã revoke mọi bản sao cookie bị đánh cắp. Browser nhận lệnh xóa cookie không thể xóa token mà attacker đã lưu ở nơi khác.

## 11. Kiểm soát bảo vệ dữ liệu lưu trữ

Chính sách đầy đủ phải xét cả **client-side storage**, **server-side persistent tokens** và **signing keys**.

### 11.1. Browser và thiết bị

- Ưu tiên remember-me qua cookie do server cấp với flags đúng; không chuyển secret sang `localStorage` chỉ vì frontend dễ đọc.
- `HttpOnly` giúp JS khó đọc trực tiếp nhưng vẫn cần chống XSS.
- `Secure` và HSTS/TLS giảm nguy cơ token đi qua HTTP; bảo đảm reverse proxy tin cậy.
- `SameSite` hợp lý theo UX/SSO và CSRF threat model.
- Không đặt remember-me trên máy dùng chung nếu policy và consent không cho phép.
- Thiết kế UI có checkbox rõ, chức năng xem/xóa thiết bị remembered, cảnh báo trên trình duyệt công cộng khi phù hợp.
- Thời hạn cookie và retention phải được giải thích phù hợp với người dùng và chính sách riêng tư.

### 11.2. Server-side token store

- DB role truy cập tối thiểu; dùng tài khoản riêng cho authentication component khi khả thi.
- Token table có phân vùng logic theo tenant hoặc access rules chặt, tránh cross-tenant query.
- Bảo vệ backup snapshots, restore copies, staging/test clones; không sao chép production persistent tokens sang staging.
- Bật encryption at rest, database transport encryption và secret rotation.
- Không log token, series/token values hay SQL bind parameters nhạy cảm.
- Có cleanup job cho token expired/revoked, retention có hạn và audit phù hợp.
- Nếu custom token hashing/encryption, phải kiểm chứng compatibility với compare/rotation/reuse-detection, không tự “hash một cột” rồi chấm dứt.
- Nếu có cache token state, xác định TTL/invalidation để revoke phản ánh đúng.
- Có cơ chế điều tra và xử lý token reuse do bị đánh cắp hoặc do concurrent requests gây nghi vấn.

### 11.3. Signing key và secrets

- Đặt secret trong secret manager/KMS hoặc environment được bảo vệ, không hardcode trong Git hoặc image.
- Chia quyền: app có thể đọc đúng key cần dùng, người dùng và dịch vụ khác không cần được đọc.
- Rotation có runbook, canary, rollback window và kế hoạch buộc re-login nếu cần.
- Không đưa key vào logs/stack traces/dump, dashboard cấu hình, metrics labels.
- Đảm bảo multi-node chia sẻ đúng key; triển khai key mới theo thứ tự kiểm soát để tránh cookie bỗng nhiên vô hiệu ở một số node.
- Không nhầm remember-me signing key với JWT signing key, CSRF token, session ID, password pepper hoặc database encryption key: **mỗi bí mật có phạm vi và hậu quả lộ khác nhau**.
- Nếu key lộ, điều tra khả năng giả mạo cookie đã phát và cân nhắc revoke/reset diện rộng; không chỉ “đổi key rồi xong” khi các account/token khác vẫn rủi ro.

### 11.4. Chính sách quyền riêng tư và lưu giữ

Series/token records thường gắn với username, timestamp và có thể device metadata bổ sung. Khi thu thập dữ liệu đó:

1. Xác định mục đích chống gian lận/bảo vệ tài khoản và thời gian retention.
2. Tránh lưu fingerprint không cần thiết hoặc metadata định danh quá mức.
3. Cung cấp chức năng revoke/xóa remembered devices theo product requirements.
4. Phân quyền admin/support có thể xem **metadata an toàn**, không thấy raw token.
5. Đảm bảo quy trình xóa tài khoản và backup retention phù hợp chính sách tổ chức/pháp luật áp dụng.
6. Có audit thay đổi settings/rotation/revocation nhưng không ghi chính bí mật.

## 12. Các tình huống vận hành phải giải quyết trước production

### 12.1. App restart khiến remember-me mất hiệu lực

**Token-based + key mới mỗi lần boot:** cookie cũ không verify → người dùng phải login lại. Giải pháp: key ổn định do secret manager cấp, multi-node nhất quán.

**Token-based + BCrypt in-memory được tạo lại:** password hash thay đổi dù raw password giống → cookie cũ có thể fail. Demo chủ ý như vậy; production cần user store bền vững.

**Persistent-token + database mỗi lần restart bị reset:** series/token record biến mất → cookie cũ không còn hợp lệ. Giải pháp: persistent DB và migrations, không dùng H2 in-memory cho production.

### 12.2. Người dùng đổi mật khẩu

Nếu chính sách yêu cầu logout remembered clients, hãy bảo đảm:

- Token-based: thay đổi password hash và các điều kiện xác minh thực sự invalidates cookies cần thiết; kiểm thử không chỉ suy luận.
- Persistent: explicit revoke records của account, không tin password change tự xóa mọi record.
- Session hiện có và refresh tokens ở hệ thống khác có thể cần revoke riêng; remember-me không bao phủ mọi auth mechanism.
- Đổi mật khẩu là thao tác nhạy cảm, thường cần `fullyAuthenticated()` hoặc recent login/step-up MFA.

### 12.3. User mất điện thoại hoặc laptop

Nếu sử dụng persistent tokens, user nên có khả năng revoke device/series hoặc all remembered devices. Với token-based signature không có state theo device, thường cần invalidate rộng qua key/pwd change hoặc bổ sung server-side state.

Không biến “xóa cookie khi user logout” thành bảo đảm đã vô hiệu **bản sao cookie trên thiết bị bị mất**.

### 12.4. Mở nhiều tab khiến persistent token mismatch

Do rotating series/token, nhiều request đồng thời có thể cùng gửi token cũ. Một request refresh cookie, request khác đọc record đã đổi. Điều này có thể bị nhìn như replay. Cần test concurrency trên backend, hiểu behavior của `PersistentTokenBasedRememberMeServices` và thiết kế UX re-login; **không fail-open** chỉ để tránh race.

### 12.5. Người dùng nhớ đăng nhập, nhưng giao dịch nhạy cảm được bảo vệ

Áp dụng rule:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/account").authenticated()
    .requestMatchers("/sensitive").fullyAuthenticated()
    .anyRequest().denyAll())
~~~

Đây là mảnh code. Một remembered user có thể xem nội dung bình thường ở `/account` nhưng cần nhập lại password/chuyển qua full authentication để gọi `/sensitive`. Không dùng chỉ `isAuthenticated()` như một proxy cho “user vừa nhập lại mật khẩu”.

## 13. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Không có remember-me cookie sau login | Checkbox không tích, tên field sai, login thất bại, handler/config chưa được gọi | Network POST login, form parameter, success handler, RememberMeServices |
| Cookie phát nhưng browser không lưu | Secure/HTTPS mismatch, Domain/Path/SameSite, browser privacy policy | Set-Cookie response và browser storage |
| Vừa restart app đã mất remember-me | Signing key hoặc password hash thay đổi, DB token mất | Secret source, user store, persistent repository |
| Một node nhận, node khác không | Key/config hoặc user store không nhất quán | Multi-node secrets, shared DB, routing |
| Cookie Max-Age còn nhưng server từ chối | Server expiry, account status, signature invalid, record revoked | Đọc trạng thái an toàn, không log token |
| Logout browser nhưng cookie bị đánh cắp vẫn dùng được | Token-based stateless không có per-token revoke | Thiết kế revoke/credential version/persistent token |
| User đổi password nhưng persistent cookie vẫn hoạt động | Token records chưa được xóa | Revoke on password change |
| Remembered user bị redirect ở endpoint nhạy cảm | `fullyAuthenticated()` yêu cầu full login | Phân biệt authenticated vs remembered |
| Persistent cookie thường xuyên bị lỗi khi nhiều tab | Token rotation race hoặc reuse detection | Concurrency tests, policy re-login |
| Remember-me token bị lộ qua support logs | Log nguyên Cookie/Set-Cookie hoặc DB dumps | Redaction và quyền đọc |
| Session cookie Secure đúng, remember-me cookie sai | Settings session cookie không áp dụng remember-me service | Kiểm tra riêng Set-Cookie của remember-me |
| DB đã mã hóa nhưng token vẫn lộ qua SQL logs | At-rest encryption không xử lý logging/dump | Secret redaction và log policy |
| Rotate key xong người dùng đồng loạt phải login | Old token-based signatures bị từ chối | Rotation plan và UX |
| Thu hồi persistent key nhưng record vẫn còn | Key không phải công cụ revoke series/token | Xóa repository records |
| User chọn không nhớ nhưng cookie vẫn phát | Có cấu hình luôn remember hoặc reused cookie | Policy opt-in/opt-out và test cookie issuance |

### 13.1. Debug theo thứ tự

1. Request POST login có CSRF token hợp lệ, username/password đúng và checkbox value đúng không?
2. Spring Security đã gọi remember-me login success chưa? Response có Set-Cookie đúng tên không?
3. Max-Age/Expires, Secure, HttpOnly, SameSite, Path và Domain có đúng trên môi trường thật không?
4. Browser có lưu/gửi cookie trên request sau không? Có bị privacy settings chặn?
5. Có session đang tồn tại khiến remember-me filter chưa cần chạy không?
6. Khi chỉ gửi remember-me cookie, service có xác minh signature hay repository record thành công không?
7. Với token-based, key và user password hash có nhất quán giữa các node/restart không?
8. Với persistent, repository/series/token/last_used có đúng lifecycle và bị rotate/revoked không?
9. Authorization rule là `authenticated()` hay `fullyAuthenticated()`?
10. User status/tenant/permissions/reauth policy có thay đổi không?
11. Có log/telemetry nào vô tình thu thập raw tokens, headers hoặc secrets không?
12. Nếu nghi cookie theft, đã có playbook invalidate, notification và audit phù hợp chưa?

Trong môi trường học, có thể bật log Spring Security ở mức DEBUG có kiểm soát, nhưng **không** bật body/header/token dumps. Không in toàn bộ `Authentication` hoặc `Cookie` vào log vì implementation/metadata có thể chứa thông tin nhạy cảm.

## 14. Bài tập thực hành

1. Vì sao remember-me cookie là một credential riêng và nguy hiểm hơn nếu bị lộ so với một cookie session rất ngắn hạn?
2. Giải thích khác nhau giữa `JSESSIONID` và cookie `remember-me`. Xóa riêng session cookie có thể dẫn đến điều gì?
3. Khi cấu hình 7 ngày, vì sao chỉ đặt `Set-Cookie: Max-Age=604800` mà không có server-side expiration check là chưa đủ?
4. So sánh absolute lifetime với sliding/idle lifetime trong trường hợp người dùng truy cập mỗi ngày.
5. Mô tả dữ liệu thường nằm trong token-based cookie, vì sao signature bảo vệ integrity nhưng không bảo vệ confidentiality.
6. Giải thích vai trò khóa ký `rememberMe().key(...)` và rủi ro khi key được hardcode vào Git.
7. Nếu key thay đổi sau deploy, các cookie token-based đã phát có thể bị ảnh hưởng như thế nào?
8. Vì sao token-based logout chỉ xóa cookie hiện tại chưa chắc vô hiệu bản copy bị attacker đánh cắp?
9. Trong persistent-token, series dùng để làm gì, token dùng để làm gì, và tại sao token có thể được rotate?
10. Vì sao bảng `persistent_logins` cần bảo vệ như một kho credentials, không phải chỉ là bảng audit bình thường?
11. Tại sao không thể tự thay cột token bằng SHA-256 digest mà vẫn giữ nguyên `JdbcTokenRepositoryImpl` và mong rotation/lookup hoạt động?
12. Hai tab gửi token_1 cùng lúc, tab A đã đổi thành token_2. Tab B sẽ thấy điều gì và hệ thống nên ứng xử ra sao?
13. Viết MockMvc test chứng minh checkbox không tích sẽ không phát remember-me cookie.
14. Viết test chứng minh chỉ mang remember-me cookie (không mang session) có thể truy cập endpoint `authenticated()` nhưng không đi qua endpoint `fullyAuthenticated()`.
15. Tại sao test dùng `@WithMockUser` không chứng minh được cookie remember-me thực sự được ký/kiểm tra?
16. So sánh ảnh hưởng của password change với token-based và persistent token, nêu rõ giả định và hành động revoke cần thiết.
17. Đặt remember-me cookie qua reverse proxy HTTPS. Những cấu hình forwarded headers và Secure flag nào cần kiểm tra?
18. Vì sao settings `server.servlet.session.cookie.same-site` chưa đủ để kết luận remember-me cookie có SameSite theo chính sách?
19. Khi user muốn “logout mọi thiết bị”, hãy thiết kế UI + repository + server revocation, phân biệt với logout browser hiện tại.
20. Lập policy cho một trang tin tức và một trang quản lý tài chính, gồm TTL, consent, sensitive reauth, max devices, rotation, incident handling.

## 15. Checklist đưa remember-me vào production

- [ ] Mô tả rõ remember-me khác full session và có mức độ xác thực yếu hơn re-login.
- [ ] Chỉ phát remember-me cookie khi user đã chủ động chọn hoặc policy được phê duyệt.
- [ ] Có TTL server-side, không chỉ dựa browser Max-Age; rõ absolute/idle policy.
- [ ] Endpoint nhạy cảm dùng `fullyAuthenticated()` hoặc step-up/recent-auth policy.
- [ ] Cookie có Secure/HttpOnly/SameSite/Path/Domain phù hợp; đã kiểm tra Set-Cookie qua reverse proxy thật.
- [ ] HTTPS, chống XSS/CSRF và logging redaction cho Cookie/Set-Cookie.
- [ ] Signing key entropy cao, nằm trong secret manager, tách theo environment, nhất quán nhiều node.
- [ ] Có key rotation/revocation incident playbook; chấp nhận hoặc xử lý tác động tới cookie cũ.
- [ ] Nếu token-based, có chính sách invalidate cookie sau password change/account compromise.
- [ ] Nếu persistent, repo bền vững, schema migration, DB permissions, encrypted backups và retention.
- [ ] Persistent tokens không bị lộ qua SQL logs/dumps/support screens.
- [ ] Thiết kế thu hồi remembered devices, all-device logout và revoke on password reset nếu sản phẩm yêu cầu.
- [ ] Kiểm thử concurrent rotation/reuse detection; không chuyển lỗi thành allow.
- [ ] Multi-node/shared secrets/repository và deploy rollback đã được test.
- [ ] Có test cookie issuance, no-checkbox, malformed cookie, session-less restore, TTL, fully-auth restriction, logout.
- [ ] Có monitoring đăng nhập tự động bất thường, incident response và thông báo user phù hợp.
- [ ] Không dùng demo key/password hardcoded trong môi trường thật.

## 16. Kết luận

**Cookie Max-Age không phải toàn bộ chính sách hết hạn; khóa ký không thay thế thu hồi; và dữ liệu persistent token không phải thông tin vô hại trong DB.** Token-based remember-me giúp vận hành gọn hơn nhưng khó vô hiệu cookie từng thiết bị, còn persistent-token giúp quản lý trạng thái và thu hồi tốt hơn với chi phí phải bảo vệ một kho bearer credentials và xử lý rotation.

Trước khi bật tính năng “Ghi nhớ đăng nhập” trong Spring Security Servlet, hãy quyết định **TTL phía browser và server, cách gia hạn, quyền truy cập khi remembered-only, cách lưu/rotate signing keys, bảo mật token store, thu hồi khi logout/password change và cách ứng phó khi cookie/DB bị lộ**. Chỉ khi các yếu tố đó nhất quán, remember-me mới mang lại UX tốt mà không tạo một tuyến xác thực dài hạn ngoài tầm kiểm soát.
