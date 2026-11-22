# Thời hạn cookie, khóa ký và bảo vệ dữ liệu token lưu phía máy chủ (Remember-me)

> **Mục tiêu:** Trong mô-đun **Ghi nhớ đăng nhập** của Spring Security, hiểu rõ tuổi thọ cookie remember-me, vai trò của **key** trong xác minh remember-me, và các biện pháp bảo vệ **persistent token** trong cơ sở dữ liệu. Thiết kế sao cho token bị lộ, đổi mật khẩu, thu hồi tài khoản, khởi động lại ứng dụng hoặc chạy nhiều máy chủ đều có hành vi được kiểm soát và kiểm thử.

## 1. Remember-me giải quyết vấn đề gì?

**Remember-me** cho phép trình duyệt nhận diện lại người dùng sau khi phiên thông thường kết thúc mà không yêu cầu nhập mật khẩu trên mỗi lần quay lại. Đây là một **bằng chứng đăng nhập dài hạn**, không chỉ là lựa chọn đặt Max-Age của **JSESSIONID**.

Dòng xử lý của ứng dụng Servlet điển hình:

~~~text
Người dùng gửi POST /login (username/password + CSRF)
    |
    +-- Xác thực mật khẩu hợp lệ
    |
    +-- Nếu chọn "Ghi nhớ đăng nhập":
    |       - phát cookie remember-me có thời hạn
    |       - với persistent-token: lưu series/token vào kho phía server
    |
    +-- Tạo session hiện tại (JSESSIONID)
    |
    v
Trình duyệt dùng ứng dụng với session

Sau này session cũ hết hạn / browser được khởi động lại:
    |
    | Cookie remember-me vẫn còn hợp lệ
    v
RememberMeAuthenticationFilter
    |
    +-- Lấy remember-me cookie
    +-- RememberMeServices xác minh token / gọi UserDetailsService
    +-- ProviderManager kiểm tra RememberMeAuthenticationToken
    +-- Tạo RememberMeAuthenticationToken trong SecurityContext
    |
    v
Người dùng được nhận diện nhờ remember-me, không phải vừa nhập mật khẩu
~~~

Khi session còn có **Authentication** hợp lệ, remember-me thường không cần chạy lại. Nếu không có Authentication và có cookie remember-me, **RememberMeAuthenticationFilter** có thể thử tự đăng nhập. Chỉ xác thực khi cookie hợp lệ và tài khoản vẫn đủ điều kiện theo policy.

**Khác biệt quan trọng:**

| Cơ chế | Phía client giữ gì? | Phía server giữ gì? | Thời gian / thu hồi |
| --- | --- | --- | --- |
| **Session** | Cookie JSESSIONID (ID phiên) | Session và SecurityContext | Idle timeout; invalidate session |
| **Remember-me hash-based** | Cookie chứa username, expiration và chữ ký theo thuật toán | UserDetails + thông tin mật khẩu đã mã hóa và key | Đến expiration; thay password hash/key có thể vô hiệu token |
| **Remember-me persistent-token** | Cookie chứa **series** và **token** dạng opaque | Bản ghi persistent_logins có username, series, token và last_used | Kiểm tra thời hạn qua server; có thể xóa/thu hồi bản ghi và xoay token |
| **Remember-me mặc định không bật** | Không có cookie remember-me | Không có token remember-me | Người dùng phải đăng nhập lại khi session kết thúc |

**Remember-me cookie không được dùng làm mật khẩu thay thế vô thời hạn.** Ai chiếm được cookie hợp lệ có thể mạo danh trong thời gian cookie còn sử dụng được. Đặc biệt, ứng dụng xử lý tiền, đổi mật khẩu, bật/tắt MFA hoặc thay đổi thông tin bảo mật cần cân nhắc **yêu cầu xác thực đầy đủ trở lại** thay vì tin cậy remember-me cho hành động nhạy cảm.

## 2. Hai chiến lược tích hợp sẵn trong Spring Security

Spring Security Servlet cung cấp hai hướng remember-me chính:

### 2.1. TokenBasedRememberMeServices — chữ ký dẫn xuất từ user, thời hạn và key

Theo tài liệu Spring Security, dữ liệu cookie về mặt ý tưởng gồm:

~~~text
Base64(
  username + ":" +
  expirationTime + ":" +
  algorithmName + ":" +
  algorithmHex(
    username + ":" + expirationTime + ":" +
    storedPassword + ":" + key
  )
)
~~~

Ở đây **storedPassword** là giá trị password mà **UserDetailsService** trả về, thường là hash đã mã hóa bởi PasswordEncoder, **không** phải mật khẩu rõ do client nhập. Đoạn trên mô tả logic của Spring Security; không phải định dạng JWT và **Base64 không phải mã hóa bí mật**.

Quá trình kiểm tra:

1. Đọc cookie, tách username, thời điểm hết hạn, thuật toán và signature.
2. Kiểm tra định dạng, thời điểm hết hạn và thuật toán được chấp nhận.
3. Tải **UserDetails** theo username từ nguồn server tin cậy.
4. Tạo lại signature với password đã lưu và **key** đúng.
5. So sánh kết quả; chỉ chấp nhận khi thông tin khớp và account state hợp lệ.

Trong dòng Spring Security 6.5, cách này dùng **SHA-256 theo mặc định** cho token signature mới; Spring hỗ trợ cấu hình thuật toán match riêng cho việc chuyển đổi legacy tokens. Đừng tự triển khai signature riêng bằng cách ghép Base64 hoặc chọn MD5 chỉ vì ví dụ cũ trên Internet có nó.

**Ưu điểm:** không cần bảng token riêng để triển khai. **Giới hạn:** cookie bị đánh cắp có thể dùng lại cho đến khi hết hạn hoặc thông tin liên quan thay đổi; không dễ thu hồi **một thiết bị cụ thể**. Đổi password hash hoặc key có thể làm vô hiệu nhiều cookie cùng lúc. Nếu password hash được băm lại mỗi lần chạy dù mật khẩu không đổi, remember-me hash-based cũng có thể mất hiệu lực sau khởi động lại.

### 2.2. PersistentTokenBasedRememberMeServices — series + token và cơ sở dữ liệu

Chiến lược persistent-token lưu **một bản ghi** phía server cho từng series. Cookie không cần mang username; server tra username qua series.

~~~text
Browser cookie (Base64 của series:token)
   |
   +--> series: định danh chuỗi login
   +--> token: giá trị ngẫu nhiên chứng minh quyền sở hữu
                    |
                    v
           PersistentTokenRepository
              persistent_logins
              username
              series (PRIMARY KEY)
              token
              last_used
                    |
          trùng series và token?
               /            \
          Có / hợp lệ       Không trùng
             |                 |
       tạo token mới       từ chối, xử lý
       cập nhật DB         nghi ngờ token bị dùng lại
       phát cookie mới
~~~

Khi tự động đăng nhập thành công, triển khai mặc định **xoay giá trị token**, cập nhật token/last_used trong repository và phát cookie mới. Điều này có tác dụng giới hạn thời gian token cũ còn sử dụng được sau khi bị thay thế. Bản ghi có thể bị xóa khi logout hoặc bị thu hồi theo user, tùy flow.

**Ưu điểm:** server có dữ liệu để thu hồi và kiểm soát token; có khả năng phát hiện việc dùng lại token đã xoay khi series còn được lưu. **Giới hạn:** cần database khả dụng, quyền truy cập chặt chẽ, backup an toàn, cleanup, xử lý request đồng thời và cách vận hành nhiều instance.

**Đừng nhầm “persistent token” với “JWT được ký”**: cookie persistent của triển khai mặc định không phải JWT và không tự được mã hóa bằng key. Nó là **bearer credential**: ai nắm đúng series và token có khả năng dùng lại. Do vậy database chứa cột token cũng là dữ liệu nhạy cảm.

### 2.3. So sánh lựa chọn

| Tiêu chí | Hash-based token | Persistent token |
| --- | --- | --- |
| Cần bảng lưu riêng? | Không | Có |
| Key ảnh hưởng trực tiếp tới signature cookie? | **Có** | Cookie không dùng cùng công thức hash-based; key chủ yếu phục vụ tin cậy remember-me Authentication bên trong Spring Security |
| Thay đổi password hash làm token cũ mất hiệu lực? | **Có**, vì chữ ký dựa trên password đã lưu | **Không bảo đảm**: phải chủ động thu hồi persistent tokens khi đổi mật khẩu |
| Có thể thu hồi một series/thiết bị? | Không dễ, nếu giữ kiến trúc mặc định | Có thể thiết kế chức năng xóa một series; API repository mặc định tập trung xóa theo user |
| Có thể nhận biết token bị dùng lại? | Không có token rotation dựa trên bảng | Có kiểm tra mismatch/rotation; cần chú ý race condition |
| Nếu DB rò rỉ | Có thể ảnh hưởng đến dữ liệu user, nhưng không có bảng token | Giá trị series/token trong bảng phải xem như secret có thể bị replay |
| Phù hợp | Rủi ro thấp và hiểu rõ giới hạn thu hồi | Ứng dụng cần quản lý/thu hồi phiên nhớ đăng nhập tốt hơn |

**Khuyến nghị thực hành:** chọn **persistent-token** nếu thực sự cần remember-me và muốn kiểm soát thu hồi; nếu ứng dụng rất nhạy cảm, cân nhắc không cho remember-me hoặc giới hạn chỉ dùng để nhận diện ban đầu rồi yêu cầu đăng nhập đầy đủ.

## 3. Thời hạn cookie: ba đồng hồ khác nhau

Để thiết kế nhớ đăng nhập chính xác, cần tách **cookie lifetime**, **remember-me server-side validity** và **session idle timeout**.

| Đồng hồ | Điều khiển ở đâu | Ví dụ | Điều gì xảy ra khi hết hạn? |
| --- | --- | --- | --- |
| **Cookie Max-Age/Expires** | Header Set-Cookie / trình duyệt | Max-Age=1209600 (14 ngày) | Browser ngừng gửi cookie đó |
| **Remember-me token validity** | RememberMeServices.tokenValiditySeconds | 1.209.600 giây | Server từ chối token remember-me quá hạn dù browser còn giữ |
| **HTTP session timeout** | Servlet container / Spring Session | 15 phút không hoạt động | Session JSESSIONID không còn dùng được; có thể thử remember-me nếu cookie còn hợp lệ |

Cấu hình ví dụ **tokenValiditySeconds(14 * 24 * 60 * 60)** là **14 ngày**. Cookie mặc định thường được phát với **Max-Age** phù hợp giá trị này. Nhưng đừng đồng nhất các đồng hồ: browser có thể xóa cookie sớm, user logout, server revoke token hoặc repository hết hiệu lực trước khi Max-Age kết thúc.

### 3.1. Ví dụ theo thời gian

~~~text
Ngày 1, 08:00:
  Login thành công, chọn remember-me.
  JSESSIONID: session 15 phút idle (ví dụ).
  remember-me: cookie sống tối đa ~14 ngày, token nằm trong DB.

Ngày 1, 08:20:
  Session đã hết idle; browser vẫn gửi remember-me cookie.
  RememberMeAuthenticationFilter xác minh token, phục hồi danh tính.
  Với persistent-token: tạo token mới, cập nhật DB, phát cookie mới.

Ngày 5:
  Người dùng đổi mật khẩu và policy thu hồi mọi remember-me tokens.
  DB xóa tokens của user; cookie còn trong browser không còn hiệu lực.

Ngày 16:
  Nếu không được gia hạn/đăng nhập lại, remember-me đã quá hạn.
  Browser hoặc server từ chối; cần credential tương tác mới.
~~~

Trong triển khai **PersistentTokenBasedRememberMeServices**, mỗi lần auto-login thành công có thể **làm mới token và cookie**, và **last_used** trong DB được cập nhật. Vì vậy hiệu lực thực tế có thể có tính chất gia hạn theo lần sử dụng (**sliding validity**), không phải luôn là một deadline cố định tính từ ngày cấp đầu tiên.

Nếu chính sách yêu cầu **absolute lifetime** (ví dụ mỗi thiết bị phải nhập lại mật khẩu ít nhất 30 ngày một lần), hãy lưu và kiểm tra thêm **issued_at / original_authenticated_at** trong thiết kế custom. **last_used** của bảng mặc định không tự chứng minh bạn đã áp dụng hard absolute expiry.

### 3.2. Cấu hình thời hạn đúng chỗ

Mẫu Spring Security DSL cho remember-me:

~~~java
.rememberMe(remember -> remember
    .tokenValiditySeconds(14 * 24 * 60 * 60)
    .rememberMeParameter("remember-me")
    .rememberMeCookieName("remember-me")
    .useSecureCookie(true))
~~~

Đoạn này **chỉ là phần của SecurityFilterChain**, không phải class Java biên dịch độc lập. Khi có persistent token, cần bổ sung **tokenRepository(...)**, **UserDetailsService** và key theo cấu hình đầy đủ ở phần sau.

Đừng dùng:

~~~properties
server.servlet.session.timeout=14d
~~~

để thay cho thời hạn remember-me. Property trên điều khiển **HTTP session**, không phải thời hạn remember-me cookie. Cũng đừng chỉ đặt **server.servlet.session.cookie.max-age=14d** để hy vọng nhớ đăng nhập: khi session server hết hạn, cookie JSESSIONID cũ không tự phục hồi một Authentication hợp lệ.

### 3.3. Giá trị mặc định và giá trị âm

Trong các implementation remember-me tiêu chuẩn, thời hạn mặc định thường là **14 ngày**, nhưng hãy **đặt tường minh** giá trị phù hợp với policy và phiên bản đang dùng. API của **TokenBasedRememberMeServices** cũng có trường hợp **tokenValiditySeconds âm** nhằm tạo cookie không lưu lâu ở browser nhưng vẫn sử dụng thời hạn nội bộ riêng; không dùng số âm làm mẹo cho production nếu chưa đọc chính xác Javadoc/version. Trong ví dụ sẽ dùng số dương để hành vi rõ ràng.

**Max-Age=0** mang nghĩa yêu cầu browser xóa cookie; nó không phải cách đặt “cookie phiên”. Khi cần thu hồi, phải đồng thời xử lý dữ liệu token phía server chứ không chỉ gửi Max-Age=0.

## 4. Khóa ký / key: vai trò, vòng đời và khả năng xoay khóa

### 4.1. Key của remember-me không phải session ID và không phải password

Spring Security có cấu hình **rememberMe().key(...)** hoặc constructor **RememberMeServices(key, ...)**. Key là một bí mật server phải được bảo vệ, nhất quán với cấu hình **RememberMeAuthenticationProvider** tương ứng.

Với **hash-based remember-me**, key là một phần đầu vào của công thức signature. Nếu attacker biết key và có đủ dữ liệu liên quan, độ an toàn của signature có thể suy giảm nghiêm trọng. Không đặt key như **"myKey"**, **"springRocks"**, tên ứng dụng, ngày tháng hay một chuỗi cố định trong source code.

Với **persistent-token remember-me**, cookie mặc định chứa series/token random và được đối chiếu với database; key **không tự động mã hóa hay ký các cột token trong DB**. Nó vẫn liên quan tới việc Spring Security phát hành/xác minh RememberMeAuthenticationToken bên trong quá trình xác thực. **Đổi key không phải thao tác thu hồi đầy đủ các cookie persistent-token đang nằm trong database**: muốn thu hồi, cần xóa những bản ghi tương ứng.

### 4.2. Tạo và giữ key ở server

Ví dụ sinh một secret ngẫu nhiên mạnh cho môi trường dev hoặc quá trình cấp phát secret:

~~~bash
openssl rand -hex 32
~~~

Lệnh tạo **32 byte ngẫu nhiên**, biểu diễn thành **64 ký tự hex**; output mỗi lần đều khác. Không dùng trực tiếp ví dụ hard-coded để thay secret. Có thể dùng Secret Manager, Kubernetes Secret có biện pháp bảo vệ thích hợp, KMS hoặc dịch vụ quản lý secrets của tổ chức. Chỉ cấp quyền đọc key cho dịch vụ cần thiết, không đưa vào log, exception, metrics, URL hay repository.

Đặt biến môi trường, chẳng hạn:

~~~bash
export REMEMBER_ME_KEY="<secret-được-cấp-từ-Secret-Manager>"
~~~

Trên PowerShell:

~~~powershell
$env:REMEMBER_ME_KEY = "<secret-được-cấp-từ-Secret-Manager>"
~~~

Giá trị trong dấu ngoặc góc là **chỗ mô tả**, không phải một khóa thật. Khi triển khai cần sử dụng secret thực sự do hệ thống cấp an toàn.

**Nhiều instance:** cùng một ứng dụng sau load balancer phải dùng cấu hình trust tương thích. Với hash-based strategy, key khác giữa các node có thể khiến cookie vừa được node A cấp không được node B chấp nhận. Với persistent strategy, các instance phải truy cập **cùng persistent token store** và tuân thủ chính sách đồng bộ; key cho remember-me authentication phải được cấu hình nhất quán để giảm bất ngờ vận hành.

### 4.3. Key rotation phải có kế hoạch

| Thao tác | Hash-based remember-me | Persistent-token remember-me |
| --- | --- | --- |
| Thay key signature | Thường làm cookie cũ không kiểm chứng được | Không đủ để thu hồi mọi token còn trong DB |
| Đổi password hash | Cookie ký dựa trên password hash cũ có thể không hợp lệ | Phải chủ động xóa token persistent theo user nếu muốn logout khỏi các thiết bị |
| Xóa row token khỏi DB | Không áp dụng vì không có bảng token | Cookie tương ứng trở nên không hợp lệ |
| Thay DB encryption key nếu có | Không liên quan trực tiếp | Có thể phải giải mã/mã hóa lại dữ liệu hoặc quản lý key version |
| Sự cố lộ key | Thay key, đánh giá rủi ro và invalidate theo mô hình | Đánh giá cả dữ liệu persistent token; thu hồi DB tokens khi cần |

Với hash-based, hệ thống đổi key theo version thường cần chính sách kiểm tra key cũ trong giai đoạn ngắn hoặc chọn **đăng nhập lại toàn bộ** nếu ưu tiên an toàn. Đừng giữ key đã lộ trong “grace period” quá dài. Spring Security remember-me mặc định không cung cấp một kho multi-key rotation đầy đủ; nếu muốn hỗ trợ nhiều key, phải thiết kế và test custom implementation.

Với persistent-token, key phải được bảo vệ nhưng **thu hồi do compromise** chủ yếu phải thao tác vào **token store**. Đổi key chưa đồng nghĩa một cookie có series/token hợp lệ trở nên vô dụng.

## 5. Bảo vệ persistent token lưu phía server

### 5.1. Schema mặc định và ý nghĩa từng trường

Spring Security cung cấp **JdbcTokenRepositoryImpl** cho persistent remember-me. Schema tiêu biểu:

~~~sql
CREATE TABLE persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

| Cột | Chức năng | Mức nhạy cảm |
| --- | --- | --- |
| username | Gắn bản ghi với người dùng để tìm và revoke | Dữ liệu định danh |
| series | ID duy nhất của chuỗi token; tra cứu record | Nhạy cảm khi đi cùng token; không xem như public ID tùy ý |
| token | Bằng chứng ngẫu nhiên hiện hành, dùng để so khớp cookie | **Credential dài hạn**: phải xem như bí mật |
| last_used | Mốc kiểm tra hiệu lực, cập nhật khi xoay token | Thông tin hành vi đăng nhập, cần hạn chế truy cập |

**Điểm dễ bỏ sót:** triển khai JDBC chuẩn lưu token theo định dạng mà **PersistentTokenBasedRememberMeServices** so sánh trực tiếp với giá trị cookie; nó **không tự băm mật mã cột token theo cùng cách lưu password BCrypt**. Vì thế một bản backup/database dump có đủ series và token có thể bị dùng để mạo danh nếu bị rò.

**Không đơn giản đổi cột token thành BCrypt hash trong JdbcTokenRepositoryImpl** rồi kỳ vọng hệ thống tiếp tục hoạt động. Service mặc định cần so sánh token mà repository trả về với token từ cookie; thay representation mà không thay service có thể làm mọi auto-login thất bại. Muốn lưu token ở dạng một chiều, cần một **custom token protocol/service** thực hiện hash/verify/rotation đúng cách hoặc thiết kế tương thích có kiểm thử chặt. Một hướng khác là **mã hóa cột token ở lớp lưu trữ** và giải mã trong adapter tin cậy, với khóa nằm ngoài DB, nhưng cần threat model, key rotation và quản lý lỗi giải mã.

### 5.2. Các lớp bảo vệ tối thiểu cho token store

1. **Phân quyền DB tối thiểu:** tài khoản ứng dụng chỉ được truy cập bảng và thao tác cần thiết; không cho tất cả service hay người vận hành tùy ý SELECT token.
2. **TLS trên kết nối DB** khi có đường truyền cần bảo vệ; endpoint và chứng chỉ DB phải được xác minh.
3. **Mã hóa dữ liệu lưu trữ và backup** theo chính sách. Full-disk/DB encryption giúp giảm rủi ro khi bị mất ổ đĩa/backup, nhưng không ngăn một tài khoản DB đã bị xâm nhập đọc giá trị plaintext qua SELECT.
4. **Không log token** dưới dạng cookie, SQL bind parameter, APM span, HTTP header, ORM debug, crash dump. Redact **Cookie** và **Set-Cookie**.
5. **Chống SQL injection:** dùng parameterized SQL/JDBC repository, không nối username/series từ request vào câu SQL.
6. **Bảo vệ DB dump và bản sao staging:** dùng dữ liệu giả/đã khử nhạy cảm, tuyệt đối không copy các persistent login tokens production sang test.
7. **Backup/restore có kiểm soát:** khôi phục backup cũ có thể vô tình làm sống lại token đã revoke nếu dữ liệu được restore sai mốc; cần chính sách sau khôi phục, có thể buộc đăng nhập lại.
8. **Giới hạn số thiết bị/series** và quan sát bất thường; bảng mặc định không áp dụng số lượng tối đa mỗi user.
9. **TTL cleanup** và retention có tài liệu: bản ghi hết hạn phải được dọn định kỳ, không giữ mãi.
10. **Audit tối giản:** lưu sự kiện tạo/revoke/rotation/cảnh báo và correlation ID theo chính sách, nhưng không lưu raw credential.

### 5.3. Xoay token, reuse detection và race condition

Trong persistent-token strategy thông thường:

- **Login tương tác hợp lệ, có chọn remember-me** → tạo **series** và **token** random; INSERT vào DB; phát cookie.
- **Auto-login hợp lệ** → tra series, so sánh token, sinh token random mới; UPDATE token và last_used; phát cookie mới.
- **Series có nhưng token mismatch** → có thể bị xem là token cũ bị dùng lại hoặc bị đánh cắp; Spring có thể phát hiện và xóa tokens theo user, đồng thời từ chối.
- **Hết hạn** → từ chối xác thực, ngay cả khi row DB chưa được dọn.
- **Logout hoặc revoke** → xóa token record theo chính sách, gửi Set-Cookie hết hạn để browser xóa cookie.

**Tình huống hai request đồng thời:** hai tab/bộ gọi cùng gửi cookie cũ trước khi browser nhận cookie mới. Một request làm token được xoay; request còn lại có thể nhìn thấy mismatch và bị coi là có nguy cơ theft. Đây là một dạng race condition cần test, nhất là với API tự động gọi song song. Không nên bỏ cơ chế kiểm tra token mismatch chỉ để “hết lỗi đăng nhập”; hãy thiết kế luồng request, chính sách thu hồi và điều phối phù hợp, hoặc cân nhắc thay kiến trúc remember-me nếu sản phẩm thường xuyên bị tình huống đó.

Nếu store replication có độ trễ, lần kiểm tra ở node khác có thể đọc token cũ hoặc không đọc được bản ghi. Với persistent token cần thống nhất **transaction isolation, consistency, uniqueness của series, cập nhật nguyên tử và lựa chọn DB primary/replica** cho đường xác thực. Không dựa trên cache stale để “cho qua” token mismatch.

### 5.4. Dọn token hết hạn không tự xảy ra

Javadoc của **PersistentTokenBasedRememberMeServices** lưu ý nó có kiểm tra hạn dùng theo thời gian token nhưng **không tự xóa tất cả bản ghi hết hạn** khỏi kho dữ liệu. Cần một job cleanup theo TTL được cấu hình.

Ví dụ SQL mang tính ý tưởng, **không chạy nguyên văn nếu DB không hỗ trợ named parameter**:

~~~sql
DELETE FROM persistent_logins
WHERE last_used < :cutoff_time;
~~~

Ở đây **cutoff_time** được ứng dụng tính bằng thời điểm hiện tại **trừ tokenValiditySeconds**. Với PostgreSQL, MySQL hoặc H2, SQL/scheduler có thể khác; chọn thống nhất UTC/timezone, chỉ dọn dựa trên điều kiện chính sách đã phê duyệt, có monitoring về số row xóa và bảo đảm không khóa bảng quá lâu.

Nếu có **absolute lifetime riêng** hoặc chính sách nghiêm hơn, cột last_used trong schema mặc định không đủ để thực hiện chính xác tất cả quy tắc; phải bổ sung dữ liệu/thiết kế repository.

## 6. Mẫu Spring Boot 3.x và Spring Security 6.x dùng JDBC persistent remember-me

Ví dụ dưới đây là **một dự án Maven Java 17+ chạy được** với Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet. Nó cố ý dùng **H2 file database chỉ cho local demo** để persistent token có thể tồn tại qua một lần khởi động lại. Trong production hãy thay bằng PostgreSQL/MySQL hoặc hệ thống DB phù hợp, migrations có kiểm soát, TLS, quyền DB tối thiểu, secret manager và HTTPS.

### 6.1. Dependencies

Tạo ứng dụng từ **Spring Initializr** với: **Spring Web**, **Spring Security**, **JDBC API**, **H2 Database** và **Spring Boot Starter Test**. Trong Maven, các dependency tiêu biểu:

~~~xml
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
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
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
~~~

Đây là **phần dependencies** trong pom.xml dự án đã có Spring Boot parent, version và plugin từ Initializr; không phải toàn bộ pom.xml độc lập. Không đặt version thủ công cho Spring Security lệch với Spring Boot BOM khi không có lý do.

### 6.2. Cấu hình datasource, remember-me key và HTTPS

Tệp **src/main/resources/application.properties**:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:./local-demo.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${TLS_KEYSTORE_PASSWORD}
server.ssl.key-alias=local-demo

# H2 file chỉ cho học tập: DB tồn tại giữa các lần restart.
spring.datasource.url=jdbc:h2:file:./rememberme-demo;DB_CLOSE_ON_EXIT=FALSE
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always

# Cookie phiên ngắn hạn, độc lập với remember-me cookie
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
server.servlet.session.timeout=15m

# Secret từ environment/secret manager, không commit
app.remember-me.key=${REMEMBER_ME_KEY}
demo.user.password=${DEMO_USER_PASSWORD}
~~~

H2 file **rememberme-demo.mv.db** tạo tại thư mục chạy ứng dụng; thêm file đó vào **.gitignore** và không chia sẻ trong repo. File chứa persistent tokens nhạy cảm. Nếu không cần dữ liệu qua restart, test dùng **H2 in-memory** và ghi rõ sự khác biệt.

Trong production, phải dùng HTTPS end-to-end theo mô hình triển khai và cấu hình cookie hợp lệ ở biên public. **SameSite** của JSESSIONID ở property trên **không tự đảm bảo SameSite cho remember-me cookie**, vì đó là cookie do Spring Security phát; ở đoạn Java bên dưới ta cấu hình trực tiếp bằng cookie customizer và cần xác nhận lại Set-Cookie thực tế.

### 6.3. Bảng persistent_logins

Tệp **src/main/resources/schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS persistent_logins (
    username VARCHAR(64) NOT NULL,
    series VARCHAR(64) PRIMARY KEY,
    token VARCHAR(64) NOT NULL,
    last_used TIMESTAMP NOT NULL
);
~~~

Tệp này có thể chạy khi ứng dụng start vì **spring.sql.init.mode=always**. Với production, không để SQL init runtime tự quản lý schema; dùng **Flyway/Liquibase** hoặc quy trình migration được kiểm soát. Khóa chính series giúp chống trùng series, nhưng bản thân việc có unique constraint không thay việc sinh token random an toàn.

### 6.4. Entry point

Tệp **src/main/java/com/example/remember/RememberApplication.java**:

~~~java
package com.example.remember;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RememberApplication {
    public static void main(String[] args) {
        SpringApplication.run(RememberApplication.class, args);
    }
}
~~~

### 6.5. Cấu hình security và remember-me persistent

Tệp **src/main/java/com/example/remember/SecurityConfig.java**:

~~~java
package com.example.remember;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Value;
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
import org.springframework.security.web.authentication.RememberMeServices;
import org.springframework.security.web.authentication.rememberme.JdbcTokenRepositoryImpl;
import org.springframework.security.web.authentication.rememberme.PersistentTokenBasedRememberMeServices;
import org.springframework.security.web.authentication.rememberme.PersistentTokenRepository;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(
            PasswordEncoder encoder,
            @Value("${demo.user.password}") String password) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode(password))
                        .roles("USER")
                        .build());
    }

    @Bean
    PersistentTokenRepository persistentTokenRepository(
            DataSource dataSource) {
        JdbcTokenRepositoryImpl repository = new JdbcTokenRepositoryImpl();
        repository.setDataSource(dataSource);
        // schema.sql đã tạo bảng; không bật setCreateTableOnStartup.
        return repository;
    }

    @Bean
    RememberMeServices rememberMeServices(
            UserDetailsService users,
            PersistentTokenRepository tokens,
            @Value("${app.remember-me.key}") String key) {

        var service = new PersistentTokenBasedRememberMeServices(
                key, users, tokens);

        service.setTokenValiditySeconds(14 * 24 * 60 * 60);
        service.setParameter("remember-me");
        service.setCookieName("remember-me");
        service.setUseSecureCookie(true);
        service.setCookieCustomizer(cookie -> {
            cookie.setAttribute("SameSite", "Lax");
            cookie.setHttpOnly(true);
            cookie.setSecure(true);
            cookie.setPath("/");
        });
        return service;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            RememberMeServices rememberServices,
            @Value("${app.remember-me.key}") String key)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public", "/error").permitAll()
                        .requestMatchers("/api/sensitive").fullyAuthenticated()
                        .anyRequest().authenticated())
                .formLogin(Customizer.withDefaults())
                .rememberMe(remember -> remember
                        .key(key)
                        .rememberMeServices(rememberServices))
                .logout(logout -> logout
                        .logoutSuccessUrl("/public?logout"))
                .build();
    }
}
~~~

**Giải thích từng cấu phần:**

- **JdbcTokenRepositoryImpl** sử dụng DataSource để tạo/cập nhật/lấy/xóa remember-me token. Đây là repository chung giữa các instance cùng DB.
- **PersistentTokenBasedRememberMeServices** sinh và xác minh token theo series, xoay token sau auto-login. Nó phụ thuộc **UserDetailsService** để tải user và authorities; một custom authentication provider không dùng UserDetailsService vẫn phải cung cấp dịch vụ này nếu muốn tích hợp remember-me chuẩn.
- **setTokenValiditySeconds(...)** điều khiển tuổi thọ remember-me; khác với **server.servlet.session.timeout**.
- **setUseSecureCookie(true)** buộc remember-me cookie có Secure ngay cả khi backend đứng sau TLS-terminating proxy.
- **setCookieCustomizer(...)** thiết lập SameSite=Lax, HttpOnly, Secure, Path=/ trên remember-me cookie. Thuộc tính này của cookie không thể được suy ra chỉ từ cấu hình JSESSIONID.
- **rememberMeServices(...)** gắn đúng service vào Spring Security; **key(...)** giữ key cho remember-me authentication provider nhất quán với service.
- **formLogin(...)** hỗ trợ checkbox/form parameter **remember-me**. Không tự cấp cookie cho mọi user khi họ không chọn ghi nhớ nếu chính sách không bật alwaysRemember.
- **fullyAuthenticated()** ở endpoint nhạy cảm yêu cầu xác thực đầy đủ, không chấp nhận chỉ có RememberMeAuthenticationToken. Người dùng được nhớ đăng nhập có thể cần nhập lại credentials để được truy cập đường dẫn này.

**Giới hạn triển khai mẫu:** user lưu InMemoryUserDetailsManager, token DB là H2 local, chưa có password change, quản lý thiết bị, xóa token định kỳ và cơ chế re-authentication UX riêng. Đây là ví dụ về tích hợp API tiêu chuẩn, không phải cấu hình production hoàn chỉnh. Bộ nhớ của user được tạo lại khi restart nhưng username/password và roles nhất quán; persistent remember-me dựa trên repository, không mặc nhiên bị invalidated bởi việc BCrypt rehash như hash-based scheme.

### 6.6. Controller quan sát remember-me và fully authenticated

Tệp **src/main/java/com/example/remember/ProfileController.java**:

~~~java
package com.example.remember;

import java.util.Map;
import org.springframework.security.authentication.RememberMeAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "remembered",
                authentication instanceof RememberMeAuthenticationToken);
    }

    @GetMapping("/api/sensitive")
    public Map<String, Object> sensitive() {
        return Map.of("allowed", true);
    }
}
~~~

Sau login bằng mật khẩu, **remembered=false**. Sau khi session mất nhưng remember-me cookie hợp lệ và được sử dụng để auto-login, **remembered=true**. Endpoint **/api/sensitive** đòi **fullyAuthenticated** nên remember-me đơn thuần không đủ; tùy entry point, browser có thể được chuyển về trang login để xác thực đầy đủ. Đây là điểm thực hành quan trọng: **remember-me xác minh danh tính ở mức độ khác với login tương tác gần nhất**.

### 6.7. HTTPS localhost và secret an toàn

Dùng JDK **keytool** để tạo certificate tự ký chỉ dành cho localhost:

~~~bash
keytool -genkeypair -alias local-demo -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore local-demo.p12 -storepass local-test-only -keypass local-test-only -dname "CN=localhost" -ext "SAN=dns:localhost"
keytool -exportcert -rfc -alias local-demo -keystore local-demo.p12 -storepass local-test-only -file local-demo.crt
~~~

Lệnh được chạy trong thư mục dự án. Không commit file **local-demo.p12** hoặc mật khẩu TLS. Chứng chỉ tự ký không dùng trong production.

Linux/macOS:

~~~bash
export TLS_KEYSTORE_PASSWORD=local-test-only
export DEMO_USER_PASSWORD=demo-pass
export REMEMBER_ME_KEY="$(openssl rand -hex 32)"
./mvnw spring-boot:run
~~~

**Lưu ý:** lệnh trên tạo key remember-me mới mỗi lần chạy shell. Nếu muốn kiểm tra cookie còn hợp lệ **qua restart**, cần cấp **một key ổn định** qua secret manager/local dev secret file được bảo vệ, không tạo lại trong mỗi lần khởi động.

Windows PowerShell minh họa:

~~~powershell
$env:TLS_KEYSTORE_PASSWORD = "local-test-only"
$env:DEMO_USER_PASSWORD = "demo-pass"
$env:REMEMBER_ME_KEY = "<secret-on-dinh-tu-secret-manager>"
.\mvnw.cmd spring-boot:run
~~~

Bảo vệ cookie bằng HTTPS thực tế. Ví dụ browser truy cập **https://localhost:8443/login** và lựa chọn **Ghi nhớ đăng nhập**. Một trình duyệt sẽ cần cấu hình tin cậy certificate local theo quy trình phát triển; đừng dùng tham số bỏ qua xác minh TLS cho đường sản phẩm.

### 6.8. Quan sát Set-Cookie bằng browser và curl

Sau khi login thành công có chọn remember-me, trong **Network → Response Headers** sẽ có một cookie dạng:

~~~http
Set-Cookie: remember-me=<opaque-cookie>; Path=/; Max-Age=1209600; Secure; HttpOnly; SameSite=Lax
~~~

**Đây chỉ là mẫu hình thái**, giá trị token và thứ tự thuộc tính thay đổi theo container/version; có thể có Expires. Để kiểm tra chính xác, nhìn vào header thực tế của ứng dụng và **Application/Storage → Cookies** trong browser. Cookie JSESSIONID có cấu trúc và thời gian sống riêng.

Với curl để kiểm tra API và HTTP status:

~~~bash
curl --cacert local-demo.crt -i -c cookies.txt https://localhost:8443/public
curl --cacert local-demo.crt -i -b cookies.txt https://localhost:8443/api/me
~~~

Request thứ hai khi chưa đăng nhập sẽ thường trả **302** đến /login. Muốn kiểm thử login qua curl phải lấy CSRF token từ form **GET /login**, giữ cookie session và POST username/password/_csrf/remember-me; browser hoặc MockMvc sẽ thuận tiện và ít sai hơn. Đừng gửi password thực trong câu lệnh có thể bị shell history ghi lại.

Sau khi login, thử xóa riêng **session cookie JSESSIONID** trong DevTools nhưng giữ remember-me cookie. Request tới **/api/me** sẽ kích hoạt auto-login nếu token còn hợp lệ; **remembered=true** cho request mới. Khi cookie nhớ đăng nhập bị xoay, browser phải lưu cookie mới từ Set-Cookie.

Đừng copy giá trị raw remember-me cookie vào log, ảnh chụp DevTools công khai hoặc hệ thống ticket: đó là một credential có thể bị replay.

## 7. Kiểm thử tự động các ranh giới quan trọng

**MockMvc** rất phù hợp để kiểm tra luồng form login và remember-me filter. Dù vậy, nó không phải browser và không đảm bảo mọi thuộc tính Set-Cookie được browser áp dụng giống production; hãy bổ sung một bài E2E HTTPS thực sự.

### 7.1. Test form login, auto-login và quyền nhạy cảm

Tệp **src/test/java/com/example/remember/RememberMeFlowTest.java**:

~~~java
package com.example.remember;

import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "server.ssl.enabled=false",
        "demo.user.password=demo-pass",
        "app.remember-me.key=local-test-key-for-unit-tests",
        "spring.datasource.url=jdbc:h2:mem:remember-tests;DB_CLOSE_DELAY=-1"
})
@AutoConfigureMockMvc
class RememberMeFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void rememberMeCookieRestoresUserAfterSessionIsGone()
            throws Exception {

        MvcResult login = mvc.perform(post("/login")
                        .with(csrf())
                        .param("username", "alice")
                        .param("password", "demo-pass")
                        .param("remember-me", "on"))
                .andExpect(status().is3xxRedirection())
                .andReturn();

        Cookie remembered =
                login.getResponse().getCookie("remember-me");

        assertNotNull(remembered);
        assertTrue(remembered.getSecure());
        assertTrue(remembered.isHttpOnly());
        assertEquals("/", remembered.getPath());
        assertEquals(14 * 24 * 60 * 60, remembered.getMaxAge());

        // Không chuyển session JSESSIONID từ request login.
        // Chỉ gửi cookie nhớ đăng nhập ở request mới.
        MvcResult autoLogin = mvc.perform(get("/api/me")
                        .cookie(remembered))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.remembered").value(true))
                .andReturn();

        // Với persistent remember-me, auto-login xoay cookie.
        Cookie rotated =
                autoLogin.getResponse().getCookie("remember-me");
        assertNotNull(rotated);
        assertNotEquals(remembered.getValue(), rotated.getValue());

        // Remember-me chưa phải xác thực đầy đủ.
        mvc.perform(get("/api/sensitive").cookie(rotated))
                .andExpect(status().is3xxRedirection());
    }

    @Test
    void withoutRememberMeParameterNoPersistentCookie()
            throws Exception {

        MockHttpServletResponse response =
                mvc.perform(post("/login")
                            .with(csrf())
                            .param("username", "alice")
                            .param("password", "demo-pass"))
                        .andExpect(status().is3xxRedirection())
                        .andReturn()
                        .getResponse();

        assertNull(response.getCookie("remember-me"));
    }

    @Test
    void incorrectPasswordDoesNotIssueRememberMeCookie()
            throws Exception {

        MockHttpServletResponse response =
                mvc.perform(post("/login")
                            .with(csrf())
                            .param("username", "alice")
                            .param("password", "wrong")
                            .param("remember-me", "on"))
                        .andExpect(status().is3xxRedirection())
                        .andReturn()
                        .getResponse();

        assertNull(response.getCookie("remember-me"));
    }
}
~~~

**Ý nghĩa:** test đầu đi từ credential thật qua filter đăng nhập, nhận remember-me cookie, bỏ session và dùng cookie trong request mới. Nó cũng xác minh token được xoay và endpoint nhạy cảm yêu cầu xác thực đầy đủ. **@WithMockUser** không thay thế được kiểm thử này vì nó bỏ qua khâu kiểm tra credential và phát cookie.

Trong test này HTTP server thật không chạy và **server.ssl.enabled=false** chỉ để MockMvc khởi tạo dễ hơn; ta vẫn yêu cầu remember-me cookie có **Secure=true** do cấu hình service. Đó không phải bằng chứng browser sẽ nhận/gửi cookie trên HTTP. Để kiểm thử thuộc tính **SameSite=Lax** thực sự từ container, hãy thực hiện một HTTP-level test đọc **Set-Cookie** qua embedded HTTPS server hoặc kiểm tra trong browser.

### 7.2. Kiểm thử hết hạn và thu hồi

Các ca nên bổ sung trong hệ thống thật:

| Tình huống | Kỳ vọng |
| --- | --- |
| Cookie và token còn hạn | Auto-login thành công, token persistent được xoay |
| Cookie quá Max-Age (browser) | Browser không gửi; user phải login lại |
| Token đã quá server-side validity | Server từ chối dù raw cookie được gửi bằng client thủ công |
| DB row bị xóa | Cookie cũ không xác thực được |
| User bị disabled/locked | Auto-login bị từ chối theo user details checker và policy |
| Password thay đổi | Với persistent token: gọi chức năng revoke; cookie cũ không được tự tái xác thực |
| Token mismatch sau rotation | Từ chối, xử lý nghi ngờ replay/theft theo triển khai |
| Hai request auto-login song song | Phát hiện race/false theft và thiết kế quy tắc hợp lý |
| DB unavailable/timeout | **Fail closed**, không cấp Authentication từ token chưa xác minh |
| App restart và key không đổi, DB có dữ liệu | Token vẫn hoạt động nếu đủ điều kiện |
| App restart nhưng DB bị xóa | Không thể phục hồi remember-me; cần login lại |
| Khóa ký hash-based bị đổi | Cookie hash-based cũ bị từ chối |
| Chỉ đổi key của persistent service, DB tokens còn | Không xem việc đổi key là revoke tuyệt đối; phải test và xóa token theo policy |
| Người dùng logout | Cookie bị xóa và server-side persistent tokens bị thu hồi theo behavior/thiết kế |
| Ủy quyền endpoint nhạy cảm | RememberMeAuthenticationToken không được thay thế xác thực đầy đủ |

**Không dùng Thread.sleep(14 ngày)** để test expiry. Thay bằng thời gian có thể kiểm soát (Clock của custom implementation, fixture row last_used cũ, TTL rất ngắn dành riêng cho test hoặc database test fixture) và xác minh tại ranh giới đúng. Với code mặc định, cách tạo fixture trong test phải phù hợp schema/version.

### 7.3. Test nguồn dữ liệu lưu bền không tự tương đương với bảo mật

Một test chứng minh “restart còn login” chỉ chứng minh DB giữ token; nó không chứng minh DB an toàn. Cần thêm test và kiểm tra cấu hình: quyền SELECT bảng, backup encryption, redaction, token reuse, lockout/rate limiting, input validation, rotation atomicity, audit và policy revoke.

Cũng không nên in token thật ra stdout để “chứng minh xoay token”. Có thể so sánh hai chuỗi **bằng assertion** mà không log giá trị.

## 8. Logout, đổi mật khẩu và thu hồi mọi thiết bị

### 8.1. Logout không chỉ là xóa cookie

Với remember-me persistent, một quy trình logout đúng cần:

1. Xác minh request logout thuộc user/session đang thao tác; với cookie session trong browser, kiểm tra CSRF.
2. Clear SecurityContext và invalidate HTTP session.
3. Gọi cơ chế logout của RememberMeServices để clear cookie remember-me.
4. Thu hồi những persistent tokens tương ứng theo chính sách của implementation (mặc định có hành vi thu hồi qua repository trong một số flow), **kiểm thử thực tế với version đang dùng**.
5. Không để bản ghi token còn hợp lệ vô tình khôi phục user ngay sau logout.

**Không giả định chỉ xóa cookie tại client là đủ.** Nếu attacker từng sao chép token, bản sao vẫn có thể tồn tại trong khi DB record chưa bị xóa. Server-side revocation mới là biện pháp quyết định với persistent-token.

### 8.2. Thay password và khoá tài khoản

Nếu người dùng đổi mật khẩu thành công, hệ thống nên xác định rõ chính sách:

- **Revoke all remembered devices**: xóa các persistent tokens của username ngay khi cập nhật mật khẩu.
- **Revoke current device only**: cần định danh series hiện tại và thiết kế repository/endpoint quản lý từng series; API mặc định **removeUserTokens(username)** xóa theo user, không cung cấp sẵn đầy đủ UI quản lý thiết bị.
- **Disable/lock account**: bảo đảm UserDetailsChecker hoặc bước tra cứu user chặn remember-me login dù token còn trong DB; có thể xóa tokens ngay để giảm tồn dư.
- **MFA re-enrollment / reset credentials**: thường nên vô hiệu remembered devices theo policy bảo mật, không chỉ chờ TTL.

Trong một service đổi mật khẩu có transaction với cùng datasource, thao tác thu hồi có thể gọi:

~~~java
// Trích đoạn tích hợp, KHÔNG phải class độc lập.
// userPasswordService là thành phần cập nhật BCrypt hash của ứng dụng.
@Transactional
public void changePassword(String username, String newPassword) {
    userPasswordService.updatePasswordHash(username, newPassword);
    persistentTokenRepository.removeUserTokens(username);
}
~~~

Cần import **@Transactional** của Spring và khai báo các dependency như **userPasswordService**, **persistentTokenRepository** trong service thực. Với nguồn user nằm ở dịch vụ khác DB, cần chiến lược nhất quán/liên hệ sự kiện và xử lý lỗi, không giả định transaction JDBC bao phủ remote system.

Lưu ý: ở **hash-based remember-me**, việc đổi password hash là một trong các cách vô hiệu token; ở **persistent-token**, **không mặc nhiên**. Đây là khác biệt cần đưa vào cả test và quy trình vận hành.

### 8.3. Khi nghi bị đánh cắp hoặc DB bị lộ

- Nếu lộ **cookie của một người dùng**, thu hồi persistent tokens liên quan, invalidate sessions khi cần và kiểm tra sự kiện bất thường.
- Nếu lộ **bảng persistent_logins**, giả định các cặp series/token có thể đã bị đọc. Phải thu hồi toàn bộ token có nguy cơ và yêu cầu đăng nhập lại theo incident policy; không chỉ đổi remember-me key.
- Nếu lộ **hash-based signing key**, đổi key và kiểm soát phạm vi ảnh hưởng; đồng thời đánh giá thông tin password hashes có bị lộ không.
- Nếu lộ **DB encryption key**, lên kế hoạch thay key, xem xét dữ liệu trong backup và điều tra liệu ciphertext/token từng bị exfiltrate.
- Thông báo cho đội bảo mật và thực hiện incident response theo quy trình; không chèn credential vào ticket.

## 9. Những lỗi triển khai thường gặp

**Lỗi 1 — Kéo JSESSIONID lên 30 ngày và gọi đó là remember-me.** Cookie dài hạn không phục hồi session đã bị xóa. **Cách đúng:** dùng RememberMeServices hoặc thiết kế token refresh rõ ràng, quản lý thời hạn server và cookie riêng.

**Lỗi 2 — Để remember-me key trong Git hoặc trong source.** Secret bị lộ khó thay đổi và không thể kiểm soát người đã đọc. **Cách đúng:** secret manager, quyền tối thiểu, xoay key có kế hoạch, log redaction.

**Lỗi 3 — Tự sinh key mới khi mỗi node khởi động.** Với hash-based nhớ đăng nhập, cookie cấp bởi node A có thể thất bại trên node B. **Cách đúng:** cấu hình key ổn định và tương thích qua cluster.

**Lỗi 4 — Nghĩ đổi key sẽ xóa mọi persistent-token.** Cookie persistent dựa trên series/token và DB; key không tự mã hóa cột token. **Cách đúng:** chủ động revoke records, đặc biệt trong incident.

**Lỗi 5 — Lưu persistent tokens vào database nhưng coi đó là dữ liệu không nhạy cảm.** SQL dump hoặc backup có thể bị replay. **Cách đúng:** DB ACL, mã hóa/backup, redaction, rotation, key custody và kiểm soát nhà vận hành.

**Lỗi 6 — Thay token DB bằng BCrypt hash ngay trong JdbcTokenRepositoryImpl.** Service mặc định cần so khớp token từ cookie với token repository; thay format có thể làm hỏng auto-login. **Cách đúng:** thiết kế custom service xác minh hash an toàn hoặc encryption adapter tương thích, test cả rotation/revocation.

**Lỗi 7 — Không dọn row đã quá hạn.** Tồn dư token làm tăng dữ liệu nhạy cảm và khó vận hành. **Cách đúng:** job cleanup theo TTL, monitoring và policy retention.

**Lỗi 8 — Không thu hồi token khi đổi mật khẩu/khóa tài khoản.** Persistent tokens có thể tiếp tục xác thực nếu source vẫn cho phép hoặc policy không revoke. **Cách đúng:** gắn revoke vào lifecycle của account.

**Lỗi 9 — Chỉ test bằng @WithMockUser.** Test authorization có thể xanh dù không có cookie nhớ đăng nhập nào được phát hoặc verify. **Cách đúng:** test form login thực, cookie, auto-login, DB store và failure cases.

**Lỗi 10 — Bật Secure cho JSESSIONID nhưng quên remember-me cookie.** Hai cookie có thể do hai thành phần phát khác nhau. **Cách đúng:** dùng **setUseSecureCookie(true)** và kiểm tra Set-Cookie của từng cookie tại public ingress.

**Lỗi 11 — Mặc định nhớ đăng nhập là fully authenticated.** Một remember-me credential đã nhiều ngày tuổi không phù hợp với mọi thao tác nhạy cảm. **Cách đúng:** dùng **fullyAuthenticated()**, re-authentication, step-up MFA khi cần.

**Lỗi 12 — Xử lý mismatch do hai tab bằng cách bỏ toàn bộ reuse detection.** Điều đó làm suy yếu khả năng phát hiện replay. **Cách đúng:** tìm hiểu race condition, quy trình phát/nhận cookie và cơ chế kiểm soát đồng thời, rồi thiết kế policy có test.

## 10. Checklist production và kiểm thử nghiệm thu

- [ ] Lựa chọn hash-based hay persistent-token dựa trên threat model; nếu rủi ro cao, cân nhắc không bật remember-me.
- [ ] Remember-me chỉ phát khi user chủ động chọn, trừ khi product policy có cơ chế khác rõ ràng.
- [ ] Cookie remember-me có **Secure**, **HttpOnly**, SameSite và Path phù hợp; kiểm chứng bằng browser HTTPS thực.
- [ ] **tokenValiditySeconds** được cấu hình rõ; phân biệt với JSESSIONID timeout và absolute session lifetime.
- [ ] Key đủ ngẫu nhiên, được quản lý như secret, thống nhất qua deployment và có kế hoạch rotate.
- [ ] Hiểu key rotation của hash-based khác server-side revocation của persistent-token.
- [ ] Persistent store có schema/unique series, transaction, consistency và quyền DB tối thiểu.
- [ ] Cột token và DB backup được coi là credential nhạy cảm; không log raw token, Cookie hay Set-Cookie.
- [ ] Có lựa chọn mã hóa at-rest hoặc thiết kế custom hash-at-rest được kiểm thử; không thay format cột token tùy tiện.
- [ ] Có cơ chế **revoke on password change**, disable/lock, logout, security incident và xử lý reset MFA.
- [ ] Có cleanup expired rows, TTL rõ và đánh giá sliding vs absolute expiry.
- [ ] Có test remember-me sau session expiry, token rotation, tamper/reuse, DB outage, request song song và cluster.
- [ ] Endpoint nhạy cảm yêu cầu fullyAuthenticated/step-up thay vì coi remembered user như fresh login.
- [ ] Kết nối TLS, CORS/CSRF và session cookie thông thường vẫn được kiểm soát độc lập với remember-me.
- [ ] CI có test thật đi qua filter và token repository, không chỉ dùng security context giả.

## 11. Tự kiểm tra kiến thức

**1. Nếu JSESSIONID hết hạn sau 15 phút nhưng remember-me cookie còn 14 ngày, có thể đăng nhập tự động không?** Có, nếu remember-me token còn hợp lệ, repository/nguồn user sẵn sàng và policy cho phép. Đây là một lần xác thực remember-me mới, không phải session cũ tự sống lại.

**2. Xoay key có xóa mọi persistent token không?** Không bảo đảm. Persistent token được đối chiếu với bản ghi ở server; cần xóa/revoke tokens trong repository nếu muốn hủy chúng.

**3. Vì sao token trong bảng DB phải coi là bí mật?** Vì cookie mang series/token có thể dùng như bearer credential. Ai có đủ dữ liệu có thể cố replay để mạo danh user.

**4. PersistentTokenBasedRememberMeServices có tự xóa row hết hạn không?** Theo Javadoc, nó từ chối token quá hạn nhưng không tự làm sạch toàn bộ expired rows; nên có job cleanup.

**5. Vì sao remember-me không nên mở endpoint đổi mật khẩu nhạy cảm?** Bằng chứng remember-me có thời hạn dài, có thể đã bị sao chép; yêu cầu xác thực đầy đủ/step-up giúp giảm rủi ro.

**6. Vì sao cùng một cookie persistent có thể tạo lỗi khi hai tab gửi request đồng thời?** Auto-login có token rotation; tab thứ hai có thể mang token cũ sau khi tab thứ nhất đã xoay token, tạo token mismatch. Cần kiểm thử và xử lý đồng thời đúng.

## 12. Tài liệu tham khảo

- [Spring Security 6.5 — Remember-Me Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/rememberme.html): hai chiến lược, chữ ký hash-based, persistent tokens, UserDetailsService, schema.
- [Spring Security 6.5 — RememberMeConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/RememberMeConfigurer.html): key, tokenRepository, tokenValiditySeconds, rememberMeParameter, useSecureCookie.
- [Spring Security 6.5 — AbstractRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/AbstractRememberMeServices.html): cookie customizer, thời hạn, Secure, checker tài khoản.
- [Spring Security 6.5 — PersistentTokenBasedRememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/rememberme/PersistentTokenBasedRememberMeServices.html): rotate token, kiểm tra hạn dùng, cleanup row hết hạn.
- [Spring Security 6.5 — Database Schema](https://docs.spring.io/spring-security/reference/6.5/servlet/appendix/database-schema.html): bảng persistent_logins.
- [Spring Security 6.5 — Authorization](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): fullyAuthenticated() và quyền truy cập.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie): Secure, HttpOnly, SameSite, Path, Max-Age.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): bảo vệ session tokens, cookies và revocation.
