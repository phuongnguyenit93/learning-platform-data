# Không chứa mật khẩu, bí mật ứng dụng hoặc khóa riêng trong token

## 1. Nguyên tắc: token mang claims, không phải kho lưu credential

JSON Web Token (JWT) thường được dùng để mang claims về chủ thể, issuer, audience, thời hạn, scope hoặc ngữ cảnh ủy quyền. JWT cũng chính là một credential trong nhiều hệ thống: ai sở hữu bearer access token có thể sử dụng nó trong phạm vi và thời hạn được cấp.

Vì vậy, đưa thêm mật khẩu, bí mật ứng dụng hoặc khóa riêng vào payload/header của JWT làm tăng đáng kể hậu quả khi token bị lộ. Người nhận token có thể lấy được credential bên trong, còn token có thể được sao chép qua nhiều nơi như browser, mobile app, proxy, gateway, queue, cache, log, tracing, backup và hệ thống hỗ trợ.

Các dữ liệu tuyệt đối không nên nhúng vào token gồm:

- Mật khẩu người dùng, mật khẩu đã băm hoặc thông tin xác minh mật khẩu.
- Client secret, API key, database password và credential của dịch vụ.
- Khóa riêng dùng để ký hoặc giải mã.
- HMAC shared secret và các khóa đối xứng dùng để bảo vệ hệ thống.
- Mã OTP, seed MFA, recovery code và credential dùng một lần.
- Refresh token hoặc credential dài hạn khác được nhúng vào một token khác.

**JWT nên mang thông tin cần thiết để bên nhận đưa ra quyết định; credential bí mật phải được quản lý trong cơ chế lưu trữ và cấp phát credential chuyên dụng.**

## 2. Hiểu đúng những gì JWT bảo vệ

### 2.1. JWS ký dữ liệu nhưng không mã hóa payload

JWT thường được tuần tự hóa dưới dạng JWS Compact Serialization với ba phần:

~~~text
BASE64URL(protected-header)
.
BASE64URL(payload)
.
BASE64URL(signature)
~~~

Header và payload được mã hóa Base64URL để biểu diễn dữ liệu. Base64URL không phải mã hóa bảo mật. Bất kỳ ai có token đều có thể giải mã hai phần này và đọc nội dung mà không cần khóa ký.

JWS cung cấp tính toàn vẹn và xác thực nguồn ký theo khóa xác minh. Chữ ký giúp phát hiện dữ liệu bị sửa, nhưng không che giấu claims. Do đó, một mật khẩu hoặc secret trong payload vẫn có thể bị đọc bởi bất kỳ bên nào lấy được token.

### 2.2. JWE mã hóa nội dung nhưng không biến token thành kho bí mật an toàn

JSON Web Encryption (JWE) bảo vệ tính bí mật của nội dung bằng mã hóa. Chỉ bên có khả năng giải mã phù hợp mới đọc được plaintext.

Tuy nhiên, JWE không phải lý do để đưa mật khẩu, API key hoặc private key vào token:

- Bên nhận có quyền giải mã sẽ nhìn thấy credential.
- Token vẫn có thể được lưu ở queue, cache, log hoặc backup.
- Credential bên trong có thể bị lộ khi endpoint giải mã, máy chủ hoặc khóa giải mã bị xâm phạm.
- Token có thể được chuyển tiếp đến nhiều thành phần hơn dự kiến.
- Việc xoay/thu hồi credential bên trong khó hơn quản lý reference đến credential trong vault.

Mã hóa giảm khả năng đọc nội dung khi token bị chặn ở một số vị trí; nó không thay thế quản lý credential, giới hạn quyền truy cập hoặc vòng đời bí mật.

### 2.3. Nested JWT không làm thay đổi nguyên tắc

Nested JWT có thể kết hợp JWS và JWE, ví dụ ký trước rồi mã hóa. Cách này cung cấp các lớp bảo vệ phù hợp với profile, nhưng không biến credential nhúng bên trong thành dữ liệu nên được phát hành.

Nếu plaintext chứa một private key hoặc mật khẩu, bên có quyền giải mã vẫn có thể lấy được nó. Không đặt credential vào token chỉ vì token đang được mã hóa hoặc ký nhiều lớp.

## 3. Phân biệt claims với credential bí mật

Claims mô tả chủ thể, ngữ cảnh hoặc quyền mà issuer muốn bên nhận sử dụng. Credential bí mật là dữ liệu có thể được dùng trực tiếp để xác thực, ký, giải mã hoặc lấy quyền.

| Dữ liệu | Vai trò | Có nên đưa vào JWT? |
| --- | --- | --- |
| Subject ID | Định danh chủ thể trong issuer | Có thể, nếu cần cho consumer |
| Issuer và audience | Xác định nguồn phát hành và bên nhận | Có, theo profile |
| Expiration | Giới hạn thời gian token | Có, theo profile |
| Scope/permission | Mô tả phạm vi quyền đã cấp | Có thể, nếu đúng audience và tối thiểu |
| Tenant/resource ID | Ngữ cảnh tài nguyên | Có thể, nếu cần và không làm lộ dữ liệu quá mức |
| Password | Bí mật xác thực người dùng | Không |
| Password hash | Dữ liệu xác minh password có giá trị cao | Không |
| Client secret/API key | Credential xác thực ứng dụng/dịch vụ | Không |
| Private signing key | Khả năng tạo chữ ký | Không |
| HMAC secret | Bí mật dùng chung để tạo/xác minh MAC | Không |
| Private decryption key | Khả năng giải mã dữ liệu | Không |
| OTP seed/recovery code | Bí mật khôi phục hoặc xác thực đa yếu tố | Không |
| Refresh token | Credential dài hạn để lấy access token mới | Không nhúng vào access token/JWT khác |

Một claim như scope hoặc role vẫn là dữ liệu nhạy cảm theo ngữ cảnh. Dù không phải secret có thể dùng trực tiếp để đăng nhập, nó có thể tiết lộ quyền, cấu trúc nội bộ hoặc thông tin riêng tư. Chỉ đưa claim mà consumer thực sự cần.

## 4. Không đưa mật khẩu hoặc password hash vào token

### 4.1. Mật khẩu là credential xác thực

Mật khẩu được dùng để chứng minh người dùng biết một bí mật. Nếu JWT chứa mật khẩu, bất kỳ nơi nào đọc được token đều có thể lấy mật khẩu đó và thử xác thực trực tiếp với hệ thống khác.

Các lỗi thường gặp:

- Đưa password vào claim để worker đăng nhập thay người dùng.
- Đưa password vào JWT mã hóa rồi gửi qua nhiều dịch vụ.
- Đưa password tạm thời hoặc mật khẩu mặc định vào token bootstrap.
- Đưa password vào header tùy biến hoặc trường metadata của token.

Không có trường hợp thông thường nào cần resource server lấy mật khẩu từ access token. Sau khi xác thực, issuer nên phát hành token với subject và claims cần thiết; consumer không cần biết mật khẩu gốc.

### 4.2. Password hash cũng không phù hợp

Password hash thường được lưu ở hệ thống xác thực để kiểm tra mật khẩu. Hash có salt và thuật toán phù hợp vẫn là dữ liệu có giá trị cao: kẻ tấn công có thể thực hiện password cracking offline mà không cần gửi request đến hệ thống.

Đưa password hash vào JWT làm lộ dữ liệu xác minh mật khẩu đến mọi nơi nhận token. Không nhúng hash, salt, password verifier hoặc thông tin nội bộ của quy trình xác thực vào claims.

### 4.3. Cách thiết kế đúng

Sau khi xác thực thành công, token chỉ cần chứa định danh chủ thể và các claims theo profile:

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://api.orders.example.org",
  "exp": 1893456900,
  "scope": "orders:read"
}
~~~

API dùng subject để xác định principal và dùng scope/policy để kiểm tra quyền. Khi cần xác thực lại, client thực hiện flow đăng nhập phù hợp với authorization server; API không lấy password từ JWT.

## 5. Không nhúng client secret, API key hoặc credential của dịch vụ

### 5.1. Client secret và API key

Client secret và API key thường cho phép ứng dụng hoặc dịch vụ xác thực trực tiếp với một hệ thống. Nếu nhúng chúng vào JWT, token trở thành phương tiện phân phối credential đến tất cả consumer có thể đọc token.

Ví dụ không an toàn:

~~~json
{
  "sub": "report-worker",
  "aud": "https://api.reports.example.org",
  "client_secret": "app-secret-value",
  "analytics_api_key": "key-value"
}
~~~

Consumer không nên nhận các credential này. Nếu worker cần gọi dịch vụ phân tích, nó phải lấy credential của chính workload từ secret manager hoặc dùng workload identity/token riêng có audience phù hợp.

### 5.2. Không dùng token làm nơi chuyển tiếp bí mật

Một số thiết kế đưa credential vào JWT để tránh phải cấu hình secret store cho từng dịch vụ. Cách này chuyển vấn đề quản lý bí mật sang mọi nơi nhận token và làm tăng bề mặt lộ lọt:

- Token có thể được lưu trong cache hoặc queue.
- Token có thể bị ghi vào log hoặc trace khi debug.
- Consumer không cần credential vẫn có thể đọc token.
- Credential có thể bị sao chép sang môi trường khác.
- Khi secret bị xoay, token cũ vẫn mang giá trị secret cũ cho đến khi bị xóa/thu hồi ở mọi nơi.

Token không phải secret manager, vault, key store hay kênh bootstrap credential.

### 5.3. Cách cung cấp credential cho workload

Tùy nền tảng và trust boundary, có thể dùng:

- Workload identity để cấp danh tính cho service mà không phân phối secret tĩnh.
- Client credentials với secret được giữ trong secret manager và token có thời hạn ngắn.
- Private-key JWT hoặc mutual TLS để xác thực client theo cấu hình tin cậy.
- Secret manager/KMS/HSM để lưu, truy xuất và xoay credential.
- Token exchange để cấp token hẹp cho audience/resource đích khi cần delegation.

Dù chọn cơ chế nào, token được cấp cho worker chỉ nên có quyền và thời hạn cần thiết. Không nhúng credential gốc dùng để tạo token vào chính token đó.

## 6. Tuyệt đối không đưa private key hoặc HMAC secret vào token

### 6.1. Private signing key có thể tạo token giả

Khóa riêng ký JWT là credential có giá trị rất cao. Nếu attacker lấy được khóa riêng, họ có thể tạo chữ ký mới mà verifier tin cậy, từ đó giả mạo claims theo phạm vi issuer/key.

Ví dụ một JWK RSA có thể chứa các tham số công khai như:

~~~json
{
  "kty": "RSA",
  "kid": "signing-key-2026",
  "n": "public-modulus",
  "e": "AQAB"
}
~~~

Các tham số công khai như modulus và exponent có thể được công bố để xác minh chữ ký. Tham số private như d, p, q, dp, dq, qi không được đưa vào JWT hoặc JWKS công khai.

Đối với EC, tham số tọa độ công khai x/y có thể được phân phối; tham số private d phải được bảo vệ. Với khóa đối xứng JWK, giá trị k chính là secret và không được công bố trong token/header/JWKS công khai.

### 6.2. HMAC secret không được nhúng vào JWT

Với HS256, HS384 hoặc HS512, issuer và verifier dùng chung một secret. Nếu secret xuất hiện trong token, bất kỳ bên nào đọc được token đều có thể tạo MAC hợp lệ và giả mạo token.

Đây là lỗi nghiêm trọng hơn việc chỉ lộ một claim nhạy cảm: attacker có thể tạo token mới với nội dung tùy ý trong phạm vi verifier tin secret đó.

Không đưa HMAC secret vào payload, JOSE header, JWK hoặc một claim mã hóa Base64URL. Không có cách đổi tên trường hay mã hóa biểu diễn nào làm cho secret trở nên an toàn khi nó vẫn được phân phối cùng token.

### 6.3. Public key có thể xuất hiện trong một số profile

Không phải mọi key material đều là bí mật. Một số profile có thể mang public JWK trong JOSE header, ví dụ DPoP dùng public key để verifier xác minh proof và tính thumbprint. Certificate chain công khai cũng có thể xuất hiện trong header theo profile.

Điều kiện:

- Chỉ chứa tham số công khai, không có private parameter hoặc symmetric secret.
- Verifier phải áp dụng đúng profile và kiểm tra thuật toán/key type.
- Public key do token tự mang không tự chứng minh issuer đáng tin; trust/binding phải được xác lập theo giao thức.
- Không dùng public key trong token để tự động thay thế trust anchor đã cấu hình.

Public key có thể được công bố; private key và shared secret thì không.

## 7. Không nhúng OTP seed, recovery code hoặc bí mật MFA

Các dữ liệu sau có thể cho phép attacker vượt qua bước xác thực đa yếu tố hoặc khôi phục tài khoản:

- TOTP/HOTP shared secret hoặc seed.
- Recovery code/backup code.
- Mã xác minh dùng một lần còn hiệu lực.
- Secret dùng để đăng ký thiết bị hoặc khôi phục MFA.
- Credential reset password hoặc link token có khả năng đổi thông tin xác thực.

Không đưa chúng vào access token, ID Token, message JWT hoặc claim tùy biến. Nếu client cần hoàn tất một flow xác minh, hãy dùng protocol endpoint và credential dùng một lần với audience, thời hạn, trạng thái tiêu thụ và khả năng thu hồi rõ ràng.

Một claim như mfa=true hoặc amr có thể mô tả phương thức/độ mạnh xác thực theo profile. Nó không phải seed MFA và không cho phép consumer tạo mã OTP.

## 8. Refresh token và access token không được lồng credential vào nhau

Refresh token thường có thời hạn dài và quyền cấp access token mới. Nó là credential có giá trị cao, dù được biểu diễn bằng chuỗi opaque hay JWT.

Không nhúng refresh token vào access token hoặc ID Token để worker/client có thể lấy lại sau. Nếu access token bị lộ, attacker khi đó có thể lấy luôn credential dài hạn và kéo dài quyền truy cập.

Thay vào đó:

- Client lưu refresh token theo chính sách bảo vệ phù hợp với loại client.
- Authorization server quản lý trạng thái, rotation/reuse detection hoặc sender constraint theo threat model.
- Worker dùng workload identity hoặc delegated authorization được cấp riêng.
- Khi cần token mới cho resource khác, sử dụng flow/token exchange được authorization server hỗ trợ.

Không đặt refresh token trong JWT claim, custom header hoặc payload mã hóa chỉ để giảm số lần gọi token endpoint.

## 9. Không nhầm dữ liệu nhạy cảm với khóa ký của chính JWT

Một JWT được ký bằng private key hoặc HMAC secret, nhưng khóa dùng để ký không nằm trong token. Verifier nhận token và sử dụng khóa được lấy từ trust configuration hoặc JWKS phù hợp.

Phân biệt:

| Thành phần | Vị trí đúng |
| --- | --- |
| JWT payload claims | Trong token, chỉ gồm thông tin consumer cần |
| JWS signature | Trong token, được tạo bằng khóa ký |
| Public verification key | JWKS/metadata hoặc trust store phù hợp |
| Private signing key | KMS/HSM hoặc kho khóa được bảo vệ tại issuer |
| HMAC shared secret | Secret manager/key store được giới hạn cho issuer và verifier được phép |
| Private decryption key | KMS/HSM hoặc kho khóa của recipient |
| Client secret/API key | Secret manager hoặc cơ chế workload identity |
| User password/password hash | Hệ thống xác thực chuyên dụng |

Không thêm private key vào payload để verifier có thể tự xác minh; điều đó làm lộ khả năng ký. Không thêm HMAC secret để verifier có thể tự kiểm tra; verifier phải lấy secret từ cấu hình tin cậy riêng.

## 10. Ví dụ payload: từ thiết kế nguy hiểm sang thiết kế tối thiểu

### 10.1. Payload nguy hiểm

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://api.internal.example.org",
  "exp": 1893456900,
  "password": "user-password",
  "password_hash": "password-verifier",
  "client_secret": "application-secret",
  "database_password": "database-password",
  "hmac_secret": "shared-signing-secret",
  "private_key": "-----BEGIN PRIVATE KEY-----..."
}
~~~

Payload này trộn claims định danh với credential có thể xác thực hoặc cấp quyền trực tiếp. Nếu token bị lộ, attacker có thể lấy nhiều bí mật có giá trị cao. Nếu token được mã hóa, mọi recipient có thể giải mã vẫn nhận được toàn bộ credential.

### 10.2. Payload tối thiểu hơn

~~~json
{
  "iss": "https://identity.example.org",
  "sub": "user-42",
  "aud": "https://api.internal.example.org",
  "exp": 1893456900,
  "scope": "reports:read"
}
~~~

Consumer dùng subject để xác định principal, audience để xác định token dành cho dịch vụ nào, thời hạn để giới hạn vòng đời và scope để kiểm tra loại thao tác. Credential của database, client hoặc issuer được lấy qua cơ chế riêng.

Đây chỉ là ví dụ minh họa. Schema thực tế phải tuân theo token profile, issuer, audience và nhu cầu của consumer; không thêm claim chỉ vì có sẵn dữ liệu trong hệ thống.

## 11. JWT header cũng là nơi có thể vô tình làm lộ bí mật

Không chỉ payload mới cần kiểm tra. JOSE header cũng có thể bị đọc khi token là JWS:

- Không đặt secret trong trường tùy biến.
- Không đưa private JWK vào header.
- Không nhúng private key trong trường x5c hoặc certificate metadata.
- Không đưa credential vào kid, typ, cty hoặc trường header khác.
- Không dùng URL tùy ý trong jku/x5u để trỏ tới kho khóa bí mật.

kid chỉ nên là định danh khóa, không chứa secret hoặc dữ liệu nội bộ nhạy cảm. jwk nếu profile cho phép nên chỉ chứa public key. Các tham số khóa riêng phải được loại bỏ trước khi public key được công bố.

## 12. Claims tối thiểu hóa và bảo vệ dữ liệu cá nhân

Không phải mọi dữ liệu không phải secret đều nên đưa vào JWT. Claims có thể chứa dữ liệu cá nhân hoặc thông tin nội bộ:

- Email, số điện thoại, địa chỉ hoặc ngày sinh.
- Nhóm người dùng, vai trò, tenant và cấu trúc tổ chức.
- Mã nhân viên, mã khách hàng hoặc định danh nội bộ.
- Trạng thái tài khoản, rủi ro hoặc thông tin thiết bị.
- Chi tiết giao dịch hoặc dữ liệu nghiệp vụ.

Các thông tin này có thể bị đọc nếu token là JWS, hoặc bị lộ qua recipient/log/cache nếu token là JWE. Payload lớn cũng làm tăng băng thông, giới hạn header/cookie và nguy cơ bị ghi vào hệ thống quan sát.

Áp dụng nguyên tắc data minimization:

1. Xác định consumer thực sự cần dữ liệu nào.
2. Chỉ phát hành claims cần thiết cho đúng audience.
3. Dùng định danh/reference khi consumer có thể truy vấn dữ liệu từ nguồn có kiểm soát.
4. Tránh nhúng dữ liệu thay đổi nhanh nếu consumer có thể lấy trạng thái hiện hành.
5. Đặt thời hạn token phù hợp với độ nhạy và độ mới của dữ liệu.
6. Đánh giá việc tiết lộ claim ngay cả khi token chỉ được gửi qua TLS.

Nếu claim có thể làm lộ dữ liệu nhạy cảm hoặc tạo rủi ro liên kết danh tính, hãy cân nhắc pseudonymous identifier hoặc reference thay vì dữ liệu trực tiếp.

## 13. Quản lý credential đúng nơi

| Loại credential | Cơ chế quản lý phù hợp |
| --- | --- |
| User password | Hệ thống xác thực; lưu password hash bằng thuật toán chuyên dụng, salt riêng và tham số phù hợp |
| Client secret/API key | Secret manager, giới hạn quyền đọc, rotation và audit |
| Private signing key | KMS/HSM hoặc dịch vụ ký; hạn chế export và quyền sử dụng |
| HMAC secret | Secret manager/key store; phân phối tối thiểu đến verifier cần thiết |
| Private decryption key | KMS/HSM hoặc kho khóa của recipient |
| OTP seed/recovery material | Kho MFA/credential riêng với kiểm soát truy cập và lifecycle |
| Refresh token | Kho lưu trữ phía client phù hợp và trạng thái/rotation phía authorization server |
| Job delegation reference | Kho trạng thái server-side, gắn với job, actor, workload, scope và deadline |

Credential store phải có phân quyền, audit, backup/restore và quy trình rotation/revocation. Không sao chép bí mật vào JWT chỉ để các dịch vụ truy cập thuận tiện hơn.

## 14. Giảm rò rỉ token và credential qua hệ thống trung gian

Ngay cả JWT không chứa secret vẫn là credential có giá trị. Cần bảo vệ token trên toàn đường đi:

- Chỉ truyền qua TLS và không gửi token qua URL query string.
- Không ghi Authorization header, cookie hoặc raw JWT vào application log.
- Redact token trong tracing, APM, crash report, analytics và support ticket.
- Giới hạn quyền đọc message queue, DLQ, cache, backup và database có lưu token.
- Đặt retention ngắn cho bản sao không cần thiết.
- Không gửi token qua chat, email hoặc tài liệu vận hành thông thường.
- Giới hạn audience, scope và thời hạn token.
- Có cơ chế thu hồi token/session khi phát hiện lộ lọt.

Token trong URL đặc biệt dễ bị lộ qua browser history, reverse proxy log, referrer và công cụ analytics. Không dùng URL để vận chuyển bearer credential trừ khi một giao thức cụ thể quy định cách xử lý an toàn và đã được đánh giá.

## 15. Khi secret đã bị đưa vào token: xử lý như một sự cố credential

Nếu phát hiện một JWT có password, client secret, API key, HMAC secret hoặc private key, hãy coi dữ liệu đó có thể đã bị lộ. Chữ ký JWT hợp lệ không làm bí mật an toàn hơn.

Quy trình xử lý nên gồm:

1. Xác định loại credential, issuer, token profile, audience và thời gian token được phát hành.
2. Xác định token đã đi qua những client, API, queue, log, trace, backup và môi trường nào.
3. Thu hồi token hoặc phiên chứa credential theo cơ chế phù hợp.
4. Xoay credential bị lộ: đổi password, revoke API key/client secret, thay HMAC secret hoặc thu hồi private key.
5. Nếu private signing key bị lộ, thu hồi key ID tương ứng và xử lý mọi token được ký bằng khóa đó theo quy trình key compromise.
6. Xóa/redact bản sao credential khỏi log, queue, cache và nơi lưu trữ có thể kiểm soát; bảo toàn bằng chứng cần cho điều tra theo quy trình.
7. Kiểm tra log truy cập để xác định credential có bị sử dụng trái phép không.
8. Phát hành token/schema mới không chứa credential và bổ sung kiểm tra ngăn tái diễn.

Không mặc định mọi secret nằm trong token đều có nghĩa khóa ký JWT cũng bị lộ. Nếu chỉ lộ một API key trong payload, cần thu hồi API key đó và token chứa nó; chỉ thu hồi signing key khi chính khóa ký bị xâm phạm hoặc có căn cứ cho rằng attacker có thể tạo token giả.

## 16. Kiểm tra tự động để ngăn credential lọt vào token

Có thể bổ sung kiểm tra trong quy trình phát hành token, kiểm thử và CI:

- Allowlist claim được phép phát hành theo token profile.
- Schema validation để từ chối trường không được định nghĩa.
- Denylist tên trường rủi ro như password, secret, private_key, api_key, access_token, refresh_token.
- Kiểm tra dữ liệu nhạy cảm trong JOSE header và payload trước khi ký.
- Secret scanning trên log, fixture, token mẫu và artifact kiểm thử.
- Kiểm tra không có JWK private parameter trong JWKS công khai hoặc token header.
- Kiểm tra token không xuất hiện trong URL, log, trace và DLQ.
- Giới hạn kích thước payload và số lượng claims.

Denylist theo tên trường chỉ là lớp phòng vệ bổ sung. Một secret có thể được đặt dưới tên tùy biến hoặc mã hóa thành chuỗi khác; kiểm soát chính phải là schema/allowlist và nguồn dữ liệu claims có thẩm quyền.

Ví dụ kiểm tra ở tầng phát hành:

~~~text
claims = buildClaims(subject, audience, permissions)

assert claims conforms to token-profile-schema
assert claims contains no credential material
assert header contains no private key or shared secret

token = sign(claims, configuredSigningKey)
~~~

Không đưa secret vào claims rồi trông chờ scanner phát hiện ở bước cuối. Nên thiết kế API tạo token chỉ nhận các trường được phép và không nhận một object cấu hình tùy ý chứa credential.

## 17. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Nghĩ Base64URL là mã hóa | Ai có token cũng đọc được payload JWS | Xem payload JWS là dữ liệu có thể công khai với người giữ token |
| Đưa password vào claim | Lộ credential đăng nhập | Chỉ đưa subject và claims cần thiết |
| Đưa password hash vào token | Tạo điều kiện password cracking offline | Giữ password verifier trong hệ thống xác thực |
| Đưa client secret/API key vào payload | Mọi consumer đọc token có thể lấy credential | Secret manager và workload identity |
| Nhúng private signing key | Attacker có thể tạo token giả | KMS/HSM và phân phối public key riêng |
| Đưa HMAC secret vào header | Người đọc token có thể ký token mới | Giữ shared secret ngoài token |
| Nghĩ JWE cho phép nhúng mọi bí mật | Recipient giải mã vẫn lấy được credential | Không dùng token làm secret transport |
| Đưa OTP seed/recovery code vào JWT | Có thể vượt MFA hoặc khôi phục tài khoản | Kho MFA và flow one-time riêng |
| Nhúng refresh token vào access token | Lộ access token kéo theo credential dài hạn | Quản lý refresh token riêng |
| Ghi raw JWT vào log | Mở rộng nơi có thể sử dụng bearer token | Redaction và logging an toàn |
| Dùng denylist tên trường làm kiểm soát duy nhất | Secret đổi tên có thể lọt qua | Allowlist schema và kiểm soát nguồn claims |

## 18. Tình huống tự kiểm tra

Một hệ thống phát hành JWT access token cho report worker. Để worker gọi dịch vụ lưu trữ, nhóm phát triển thêm các claims chứa storage API key và database password. Token được ký bằng RS256, có thời hạn 10 phút và gửi qua queue. Nhóm cho rằng token an toàn vì chỉ worker có public key để xác minh.

**Câu hỏi 1:** Việc dùng RS256 có làm API key và database password trong payload được bảo mật không?

**Trả lời:** Không. RS256 ký payload chứ không mã hóa nó. Bất kỳ thành phần nào đọc được token đều có thể Base64URL decode và lấy các credential.

**Câu hỏi 2:** Nếu đổi sang JWE thì có thể giữ nguyên thiết kế không?

**Trả lời:** Không nên. JWE chỉ giới hạn bên có thể giải mã; worker và mọi recipient có quyền giải mã vẫn nhìn thấy credential. Queue, cache, log và backup cũng làm tăng nơi lưu token. Worker nên dùng workload identity hoặc lấy credential cần thiết từ secret manager.

**Câu hỏi 3:** Nếu header chứa public JWK để xác minh DPoP proof thì có vi phạm nguyên tắc không?

**Trả lời:** Không, nếu profile yêu cầu public JWK và header chỉ chứa tham số công khai. Private parameter và shared secret tuyệt đối không được đưa vào token. Verifier vẫn phải kiểm tra proof binding và áp dụng đúng profile.

**Câu hỏi 4:** Nếu API key đã xuất hiện trong token được phát hành và ký hợp lệ, chỉ thu hồi token có đủ không?

**Trả lời:** Không nên giả định như vậy. API key có thể đã bị sao chép và sử dụng độc lập. Cần revoke/rotate API key, thu hồi token chứa nó, điều tra nơi token đã đi qua và loại bỏ bản sao có thể kiểm soát.

## 19. Ghi nhớ

JWT là phương tiện mang claims và bản thân bearer token đã là một credential. Không nhúng password, password hash, client secret, API key, HMAC secret, private signing/decryption key, OTP seed, recovery code hoặc refresh token vào payload hay JOSE header.

JWS ký nhưng không mã hóa payload; Base64URL chỉ là encoding. JWE bảo vệ tính bí mật cho recipient nhưng không biến token thành kho lưu credential. Public key có thể xuất hiện trong một số profile; private key và shared secret thì không.

Giữ bí mật trong secret manager/KMS/HSM hoặc hệ thống xác thực chuyên dụng. Giữ JWT tối thiểu theo audience và purpose, bảo vệ token khỏi log/queue/URL, và có quy trình thu hồi/rotation khi phát hiện lộ lọt.

**Nếu một dữ liệu có thể được dùng trực tiếp để đăng nhập, ký, giải mã hoặc lấy quyền, đừng đưa nó vào JWT.**

## Tài liệu tham khảo

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): cấu trúc JWS, protected header và chữ ký.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): mã hóa nội dung JOSE.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): tham số khóa công khai/riêng và JWKS.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): thuật toán chữ ký, MAC và mã hóa.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): Claims Set và cấu trúc JWT.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): thực hành an toàn khi tạo và xác minh JWT.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sử dụng public JWK trong proof và ràng buộc token với khóa của client.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ access token, refresh token và credential trong OAuth.
