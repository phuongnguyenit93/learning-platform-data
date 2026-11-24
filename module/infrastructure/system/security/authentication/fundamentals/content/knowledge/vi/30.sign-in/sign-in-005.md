# Failed login — Xử lý đăng nhập thất bại an toàn

## 1. Failed login là gì?

**Failed login** (đăng nhập thất bại) là một lần xác thực không đạt yêu cầu của hệ thống. Nguyên nhân có thể là mật khẩu sai, tài khoản không tồn tại, tài khoản bị khóa hoặc vô hiệu hóa, MFA không hợp lệ, passkey không hoàn tất, credential hết hạn, session không còn hiệu lực hoặc dịch vụ xác thực gặp lỗi.

Ví dụ: nhân viên nhập sai mật khẩu nhiều lần vào cổng công ty. Hệ thống cần phản hồi dễ hiểu để người dùng hợp lệ sửa lỗi, đồng thời hạn chế thử mật khẩu hàng loạt, credential stuffing và dò tìm tài khoản. Nếu phản hồi nói rõ “email này tồn tại nhưng mật khẩu sai”, attacker có thể thu thập danh sách tài khoản. Nếu khóa tài khoản ngay sau vài lần thử, attacker có thể cố tình khóa tài khoản của nhân viên khác.

Trong chương **Đăng nhập** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, failed login liên hệ trực tiếp với credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần thiết kế cách xử lý lỗi vừa bảo vệ ranh giới tin cậy, chống phishing, replay và lạm dụng đăng nhập, vừa giúp người dùng hợp lệ hiểu cách tiếp tục an toàn.

**Một lần đăng nhập thất bại không tự chứng minh có tấn công.** Người dùng có thể gõ nhầm, quên mật khẩu, dùng bàn phím khác layout hoặc gặp lỗi mạng. Hệ thống cần đánh giá hành vi theo ngữ cảnh, giữ thông tin nhạy cảm ở phía server và tránh để thông báo lỗi trở thành kênh tiết lộ dữ liệu.

## 2. Các loại thất bại trong luồng đăng nhập

Một luồng đăng nhập có nhiều bước, nên cần phân loại lỗi theo giai đoạn:

| Giai đoạn | Ví dụ thất bại | Cách xử lý |
| --- | --- | --- |
| **Nhận dạng tài khoản** | Tên đăng nhập sai định dạng, tài khoản không tìm thấy. | Phản hồi chung, kiểm tra đầu vào và giới hạn dò tìm. |
| **Kiểm tra credential** | Mật khẩu sai, credential không hợp lệ hoặc bị thu hồi. | Không tạo session; áp dụng rate limit và ghi audit an toàn. |
| **Trạng thái tài khoản** | Tài khoản bị disabled, suspended hoặc chưa hoàn tất bootstrap. | Áp dụng policy, không tiết lộ trạng thái nhạy cảm qua public response. |
| **MFA/step-up** | TOTP sai/hết hạn, push bị từ chối, passkey không hoàn tất. | Giữ trạng thái giao dịch đúng, giới hạn thử và cho phép phương án hợp lệ. |
| **Federation** | OIDC/SAML response sai issuer, audience, state, nonce hoặc chữ ký. | Từ chối response; không tạo RP session. |
| **Token/session** | Token hết hạn, session bị revoke hoặc cookie không hợp lệ. | Yêu cầu xác thực lại theo policy. |
| **Hạ tầng** | IdP, database, HSM hoặc session store không sẵn sàng. | Báo lỗi tạm thời phù hợp; không coi lỗi hệ thống là credential sai. |

### Lỗi xác thực khác lỗi authorization

- **401 Unauthorized** thường biểu thị request chưa có thông tin xác thực hợp lệ hoặc cần xác thực lại.
- **403 Forbidden** thường biểu thị chủ thể đã được xác thực nhưng không có quyền thực hiện hành động.

Ứng dụng cần dùng status code và response theo semantics của API, không dùng 403 để tiết lộ tài khoản tồn tại hay 401 để che giấu lỗi phân quyền. Với giao diện đăng nhập, thông báo công khai có thể được tổng quát hóa để tránh account enumeration.

### Lỗi người dùng và lỗi hệ thống

Không được ghi nhận mọi lỗi thành “password incorrect”. Nếu IdP không truy cập được, khóa ký không tải được hoặc session store gặp sự cố, hệ thống phải phân loại đó là lỗi vận hành. Phân loại nội bộ chính xác giúp điều tra và cảnh báo mà không tiết lộ chi tiết cho attacker.

## 3. Account enumeration và thông báo lỗi chung

**Account enumeration** là việc attacker xác định tài khoản nào tồn tại thông qua khác biệt trong phản hồi đăng nhập, đăng ký, recovery hoặc MFA.

Ví dụ phản hồi không an toàn:

- “Không tìm thấy email này.”
- “Tài khoản tồn tại nhưng mật khẩu sai.”
- “Tài khoản này chưa bật MFA.”
- “Người dùng đã bị khóa.”

Các thông báo này giúp attacker xây dựng danh sách tài khoản hoặc xác định trạng thái bảo mật của nạn nhân.

Một thông báo công khai an toàn hơn:

> Không thể đăng nhập bằng thông tin đã cung cấp. Hãy kiểm tra lại và thử lại, hoặc sử dụng quy trình khôi phục tài khoản.

Với tài khoản chưa kích hoạt hoặc bị vô hiệu hóa, giao diện có thể hướng người dùng tới kênh hỗ trợ chính thức mà không tiết lộ trạng thái nội bộ cụ thể.

### Không chỉ nội dung phản hồi mới tiết lộ tài khoản

Attacker có thể phân biệt tài khoản qua:

- HTTP status code khác nhau.
- Response body hoặc kích thước khác nhau.
- Redirect khác nhau.
- Thời gian phản hồi khác biệt rõ.
- Số lần gửi OTP hoặc thông báo khác nhau.
- CAPTCHA chỉ xuất hiện với tài khoản tồn tại.
- Thông báo “đã gửi email” chỉ khi địa chỉ có trong hệ thống.

Các endpoint đăng nhập, quên mật khẩu, resend activation và kiểm tra username cần được rà soát như một nhóm. Không sửa riêng trang login nhưng để endpoint recovery tiết lộ danh sách tài khoản.

### Cân bằng thời gian phản hồi

Không thể bảo đảm mọi nhánh xử lý có thời gian tuyệt đối giống nhau, nhưng có thể giảm khác biệt có thể khai thác:

- Dùng quy trình xác minh có chi phí tương đương ở nhánh tài khoản không tồn tại khi phù hợp, ví dụ thực hiện password-hash verification với một dummy hash có cấu hình tương đương.
- Tránh trả response sớm quá khác biệt chỉ vì không tìm thấy user.
- Không tạo delay đồng bộ quá lớn để “làm đều thời gian”; cách này có thể gây DoS và làm giảm khả năng phục vụ.
- Đo phân phối thời gian ở môi trường kiểm thử và production để phát hiện khác biệt rõ ràng.

Thông báo chung không có nghĩa là bỏ thông tin hữu ích. Người dùng đã xác thực qua kênh riêng hoặc đã vượt một bước xác minh phù hợp có thể nhận hướng dẫn cụ thể hơn.

## 4. Credential stuffing, password spraying và brute force

Ba kiểu tấn công thường bị nhầm lẫn:

| Kiểu tấn công | Cách thực hiện | Dấu hiệu |
| --- | --- | --- |
| **Brute force** | Thử nhiều mật khẩu cho một tài khoản hoặc một tập tài khoản. | Nhiều lần thử dồn dập, pattern đoán mật khẩu. |
| **Password spraying** | Thử một vài mật khẩu phổ biến trên rất nhiều tài khoản. | Mỗi tài khoản có ít lần sai nhưng tổng thể nhiều tài khoản bị thử. |
| **Credential stuffing** | Dùng cặp username/password bị lộ từ dịch vụ khác. | Nhiều tài khoản bị thử bằng credential có vẻ hợp lệ; phân tán theo IP/device. |

Biện pháp phòng thủ:

- Rate limit nhiều chiều: tài khoản, IP/ASN, thiết bị, client, endpoint và toàn hệ thống.
- Theo dõi pattern phân tán; không chỉ đếm số lần sai trên từng username.
- Dùng mật khẩu dài, duy nhất và kiểm tra mật khẩu đã bị lộ theo cách bảo vệ quyền riêng tư.
- Khuyến khích password manager và passkey.
- MFA chống phishing cho tài khoản nhạy cảm.
- Phát hiện bot và tự động hóa nhưng có cơ chế accessible cho người dùng hợp lệ.
- Cảnh báo đăng nhập bất thường và cung cấp session/credential management.

Không dựa vào một IP duy nhất: attacker có thể dùng botnet, proxy hoặc mạng dân dụng; nhiều người dùng hợp lệ cũng có thể dùng chung NAT.

## 5. Rate limiting, throttling và backoff

Rate limiting giới hạn số lần thử trong một khoảng thời gian. Throttling làm chậm hoặc hạn chế hoạt động khi rủi ro tăng. Backoff tăng thời gian chờ sau các lần thất bại liên tiếp.

Một policy có thể kết hợp:

- Giới hạn theo account identifier đã chuẩn hóa, kể cả khi tài khoản không tồn tại.
- Giới hạn theo IP/ASN và subnet với ngưỡng phù hợp môi trường.
- Giới hạn theo device/session/client khi có tín hiệu đáng tin.
- Giới hạn toàn cục để bảo vệ tài nguyên xác minh mật khẩu và MFA.
- Exponential backoff có trần, jitter và reset theo điều kiện an toàn.
- Cảnh báo khi có pattern password spraying hoặc credential stuffing.

Ví dụ backoff minh họa:

~~~text
delay = min(baseDelay * 2^consecutiveFailures, maximumDelay)
delay = addSmallRandomJitter(delay)
~~~

Đây chỉ là ví dụ, không phải ngưỡng khuyến nghị cho mọi hệ thống. Delay nên được thực hiện bằng cơ chế hàng đợi/rate limit phù hợp, không giữ worker hoặc thread bằng sleep đồng bộ. Cần giới hạn cả chi phí tài nguyên và tác động tới người dùng.

### Đếm lỗi theo nhiều chiều

Không chỉ đếm sai mật khẩu theo tài khoản. Nếu attacker thử một mật khẩu trên 20.000 tài khoản, bộ đếm từng tài khoản có thể không chạm ngưỡng. Kết hợp tín hiệu account, IP, subnet, ASN, client, thiết bị, tốc độ và thời gian giúp phát hiện hành vi phân tán.

Không dùng fingerprint trình duyệt hoặc IP làm định danh cứng. Chúng là tín hiệu có thể thay đổi/giả mạo, cần đánh giá cùng các dữ liệu khác.

## 6. Account lockout và nguy cơ từ chối dịch vụ

Khóa tài khoản sau một số lần đăng nhập sai có thể hạn chế brute force, nhưng cũng tạo cơ hội **account lockout DoS**: attacker cố tình nhập sai để khóa tài khoản nạn nhân.

Không nên áp dụng khóa vĩnh viễn chỉ dựa vào số lần sai mật khẩu từ một nguồn không đáng tin. Có thể kết hợp:

- Throttling theo account và nguồn.
- Backoff tạm thời, có trần và khả năng phục hồi.
- Risk-based challenge hoặc step-up khi hành vi bất thường.
- Thông báo cho chủ tài khoản về hoạt động đáng ngờ.
- Khôi phục truy cập qua kênh đã xác minh.
- Chính sách khóa nghiêm ngặt hơn cho tài khoản đặc quyền, có quy trình hỗ trợ.

### Khóa tạm thời và khóa quản trị

Phân biệt:

- **Temporary throttling:** giới hạn tốc độ trong thời gian ngắn.
- **Risk hold:** tạm giữ yêu cầu cần xác minh thêm.
- **Administrative suspension:** tài khoản bị quản trị viên vô hiệu hóa theo quy trình.
- **Compromise response:** thu hồi credential/session khi có dấu hiệu chiếm quyền.

Không dùng cùng một thông báo hoặc cơ chế cho tất cả. Trạng thái nội bộ phải rõ để vận hành; giao diện công khai cần tránh tiết lộ thông tin nhạy cảm.

## 7. Xử lý mật khẩu sai an toàn

Khi người dùng nhập mật khẩu, server cần:

1. Chuẩn hóa username/email theo quy tắc nhất quán và không gây nhầm tài khoản.
2. Tra cứu account theo nguồn dữ liệu tin cậy.
3. Nếu không có account, thực hiện nhánh phản hồi tương đương theo thiết kế chống enumeration.
4. Nếu có account, xác minh password hash bằng thư viện được duy trì.
5. Áp dụng rate limit và kiểm tra trạng thái tài khoản.
6. Chỉ tạo session sau khi toàn bộ yêu cầu xác thực đạt.

### Lưu trữ mật khẩu

- Dùng password hashing chuyên dụng như Argon2id, scrypt hoặc bcrypt với cấu hình phù hợp.
- Mỗi mật khẩu có salt ngẫu nhiên riêng.
- Có thể dùng pepper được quản lý tách biệt nếu kiến trúc hỗ trợ.
- Không dùng SHA-256/MD5 trực tiếp làm password hash.
- Không lưu mật khẩu bản rõ, không log password hoặc gửi lại mật khẩu trong response.
- Theo dõi cấu hình hash và nâng cấp khi người dùng đăng nhập thành công nếu cần rehash.

### Thông báo mật khẩu sai

Không nói mật khẩu đúng/sai riêng khi username chưa được xác minh. Với tài khoản không tồn tại và mật khẩu sai, phản hồi công khai nên tương đương. Không tiết lộ password policy nội bộ hoặc trạng thái credential của tài khoản khác.

Nếu mật khẩu đã bị lộ trong các tập dữ liệu vi phạm đã biết, có thể yêu cầu đổi mật khẩu theo policy. Không bắt buộc đổi mật khẩu định kỳ vô lý nếu không có dấu hiệu rủi ro; ưu tiên mật khẩu dài, duy nhất, MFA và phát hiện lộ lọt.

## 8. MFA failure và chống MFA fatigue

MFA có thể thất bại vì mã sai/hết hạn, thiết bị không khả dụng, push không tới hoặc người dùng từ chối. Cần phân biệt:

- **Invalid response:** mã hoặc chữ ký không hợp lệ.
- **Expired challenge:** challenge hết hạn.
- **User denied:** người dùng chủ động từ chối.
- **Authenticator unavailable:** thiết bị/kênh không thể dùng.
- **Risk rejection:** policy từ chối vì tín hiệu rủi ro.
- **Service error:** hệ thống MFA không sẵn sàng.

### TOTP

- Giới hạn số lần nhập mã.
- Kiểm tra time window vừa đủ để xử lý lệch đồng hồ.
- Không chấp nhận lại cùng mã/time-step khi policy yêu cầu replay protection.
- Không log OTP hoặc TOTP secret.

### Push

- Có cooldown và giới hạn số push.
- Hiển thị ngữ cảnh, ứng dụng và thao tác đang yêu cầu.
- Dùng number matching hoặc xác nhận ý định khi phù hợp.
- Cho phép từ chối/báo cáo yêu cầu không do mình khởi tạo.
- Không gửi push liên tục để người dùng vô tình bấm chấp thuận.

### Passkey/WebAuthn

- Kiểm tra challenge, origin, RP ID, chữ ký và credential status.
- Phân biệt người dùng hủy thao tác với lỗi xác minh.
- Không fallback âm thầm sang phương thức yếu hơn nếu policy yêu cầu phishing resistance.

## 9. Failed login trong OIDC, SAML và OAuth

Đăng nhập liên kết có nhiều nơi có thể thất bại:

- IdP từ chối credential hoặc yêu cầu MFA bổ sung.
- Authorization request sai client, redirect URI hoặc scope.
- State/nonce/PKCE không khớp.
- ID token sai chữ ký, issuer, audience, nonce hoặc hết hạn.
- SAML assertion sai audience, destination, InResponseTo hoặc replay.
- Token endpoint không sẵn sàng hoặc client authentication thất bại.

RP phải xác minh response trước khi tạo local session. Nếu callback lỗi, cần tiêu thụ/hủy transaction đúng cách, xóa dữ liệu tạm phù hợp và hiển thị thông báo an toàn. Không chuyển người dùng tới redirect URI tùy ý hoặc giữ authorization code để thử lại vô hạn.

### Không biến lỗi federation thành lỗi mật khẩu

Nếu token endpoint timeout hoặc JWKS không tải được, đó là lỗi hạ tầng/issuer trust. Không nên hiển thị “sai mật khẩu” hoặc ghi nhận người dùng thất bại credential. Phân loại sai có thể khóa nhầm tài khoản và làm sai lệch dữ liệu bảo mật.

## 10. Session và token sau đăng nhập thất bại

Nguyên tắc cơ bản: **không tạo session authenticated khi xác thực chưa hoàn tất**.

- Session ẩn danh có thể tồn tại để bảo vệ CSRF hoặc lưu giao dịch, nhưng phải được phân biệt với phiên đã xác thực.
- Sau đăng nhập thành công, xoay session ID để chống session fixation.
- Khi MFA chưa hoàn tất, chỉ lưu trạng thái pending authentication với thời hạn ngắn và quyền hạn giới hạn.
- Khi challenge hết hạn hoặc bị từ chối, hủy trạng thái pending phù hợp.
- Không phát hành access token/refresh token trước khi policy xác thực và authorization grant đạt.
- Nếu token đã phát hành rồi phát hiện credential/session bị xâm phạm, áp dụng revoke policy cho session/token liên quan.

Một lỗi phổ biến là đặt cookie authenticated trước khi hoàn tất MFA rồi chỉ kiểm tra MFA ở frontend. Server phải giữ trạng thái xác thực chưa hoàn tất và không cấp quyền protected resource cho tới khi toàn bộ bước cần thiết đạt.

## 11. Recovery sau nhiều lần đăng nhập thất bại

Khi người dùng quên mật khẩu hoặc bị throttling, recovery cần an toàn và không trở thành đường vòng cho attacker:

- Dùng recovery flow riêng với token ngắn hạn, purpose-bound và one-time.
- Không tiết lộ account existence trong phản hồi công khai.
- Gửi thông báo qua kênh đã xác minh trước đó.
- Không cho kênh vừa được đổi tự động chứng minh quyền sở hữu tài khoản cũ.
- Sau reset mật khẩu hoặc MFA, xem xét thu hồi session/refresh token cũ theo policy.
- Với tài khoản đặc quyền, yêu cầu quy trình xác minh/approval mạnh hơn.
- Không yêu cầu người dùng gửi mật khẩu, OTP hoặc recovery code cho helpdesk.

Nếu tài khoản bị throttling do attacker, người dùng hợp lệ cần con đường khôi phục mà không buộc họ hạ mức bảo mật. Hỗ trợ phải có xác minh độc lập và audit.

## 12. Risk-based authentication và CAPTCHA

Hệ thống có thể điều chỉnh phản hồi dựa trên rủi ro:

- Tốc độ thử tăng đột biến.
- Nhiều tài khoản bị thử từ một nguồn.
- Một tài khoản bị thử từ nhiều nguồn.
- Thiết bị/browser mới hoặc bất thường.
- Địa lý/ASN thay đổi đáng kể.
- Credential xuất hiện trong dữ liệu lộ lọt đã biết.
- Nhiều lần MFA bị từ chối hoặc push bất thường.

Các tín hiệu này không chứng minh chắc chắn có tấn công. Cần kết hợp với context, giảm false positive và tránh phân biệt đối xử hoặc khóa nhầm người dùng đi qua VPN/mạng di động.

### CAPTCHA

CAPTCHA hoặc bot challenge có thể tăng chi phí tự động hóa, nhưng:

- Không thay thế password hashing, MFA hoặc rate limit.
- Có thể gây khó khăn cho người dùng khuyết tật hoặc thiết bị hỗ trợ.
- Có thể bị giải tự động hoặc thuê người giải.
- Không nên bật chỉ cho tài khoản tồn tại theo cách tạo account enumeration.
- Cần phương án accessible và cơ chế challenge theo rủi ro.

Không coi việc vượt CAPTCHA là bằng chứng danh tính. Nó chỉ là một tín hiệu/challenge chống tự động hóa.

## 13. Logging, audit và quyền riêng tư

Log failed login cần giúp điều tra mà không tạo thêm nơi rò rỉ credential.

### Nên ghi

- Thời điểm và request/correlation ID.
- Kết quả tổng quát và mã lý do nội bộ.
- Account reference đã pseudonymize hoặc định danh nội bộ có kiểm soát.
- Client/app, issuer và tenant nếu liên quan.
- IP/ASN/device signals đã giảm thiểu theo chính sách.
- Bộ đếm/rate-limit decision và policy version.
- Kết quả MFA/step-up ở mức metadata, không chứa mã bí mật.

### Không ghi

- Mật khẩu, password hash nếu không cần cho mục đích vận hành.
- OTP, TOTP secret, recovery code hoặc QR provisioning.
- Session cookie, access token, refresh token, authorization code.
- Private key, client secret hoặc certificate private material.
- Toàn bộ request body chứa dữ liệu cá nhân không cần thiết.

Log phải có kiểm soát truy cập, retention, integrity và cảnh báo. Không dùng log công khai hoặc dashboard rộng quyền để hiển thị email đầy đủ, token hay dữ liệu định danh nhạy cảm.

### Sự kiện audit cần phân biệt

| Event | Ý nghĩa |
| --- | --- |
| login_failed_invalid_credential | Credential không hợp lệ theo kiểm tra nội bộ. |
| login_throttled | Yêu cầu bị giới hạn tốc độ. |
| login_challenge_required | Cần thêm challenge/step-up. |
| mfa_failed | Bằng chứng MFA không hợp lệ hoặc bị từ chối; ghi outcome cụ thể ở mức an toàn. |
| federation_validation_failed | Response OIDC/SAML không đạt xác minh. |
| login_service_unavailable | Hệ thống xác thực không sẵn sàng. |
| account_recovery_started/completed | Recovery được bắt đầu/hoàn tất. |

Không gộp mọi event thành một mã chung trong hệ thống quan sát nội bộ; phân loại đúng giúp phát hiện sự cố và tránh hành động sai.

## 14. Mã giả: xử lý đăng nhập thất bại

Mã giả dưới đây minh họa luồng kiểm tra, không thay thế framework xác thực hoặc thư viện password hashing:

~~~text
login(request):
    identifier = normalizeIdentifier(request.identifier)
    risk = evaluateRequestSignals(request, identifier)

    if globalAbuseLimitExceeded(risk):
        recordSafeEvent("login_throttled", risk)
        return genericLoginFailure()

    account = lookupAccount(identifier)

    if account is missing:
        verifyAgainstConfiguredDummyHash(request.password)
        applyIdentifierAndSourceLimits(identifier, risk)
        recordSafeEvent("login_failed", risk)
        return genericLoginFailure()

    if account.status != "active":
        performEquivalentSafeVerificationPath(request, account)
        applyAccountAndSourceLimits(account, risk)
        recordSafeEvent("login_failed", risk)
        return genericLoginFailure()

    if not verifyPasswordWithPasswordHashLibrary(
        request.password,
        account.passwordHash
    ):
        applyAccountAndSourceLimits(account, risk)
        recordSafeEvent("login_failed", risk)
        return genericLoginFailure()

    if policy.requiresMfa(account, risk):
        pending = createShortLivedPendingAuthentication(account)
        return requireMfa(pending)

    atomically:
        clearEligibleFailureCounters(account)
        createNewAuthenticatedSession(account)
        rotateSessionIdentifier()

    recordSafeEvent("login_succeeded", risk)
    return success()
~~~

Các điểm cần lưu ý:

- Không trả về chi tiết account missing/disabled/password wrong ở public response.
- Không dùng dummy hash tùy tiện; cấu hình phải tương đương thuật toán/cost để giảm timing discrepancy.
- Bộ đếm phải cập nhật an toàn trong hệ thống phân tán.
- Không xóa bộ đếm rủi ro chỉ vì một request thành công nếu còn tín hiệu tấn công khác.
- Pending MFA không có quyền như session authenticated.
- Không ghi password hoặc token vào event.

## 15. Tình huống thực tế: password spraying trên cổng nhân viên

Một attacker thử một mật khẩu phổ biến trên hàng nghìn tài khoản nhân viên. Mỗi tài khoản chỉ nhận một hoặc hai lần thử, nên cơ chế khóa sau năm lần sai trên từng tài khoản không phát hiện sớm.

### Dấu hiệu

- Nhiều account identifier bị thử trong khoảng thời gian ngắn.
- Nhiều request đến từ một số ASN/proxy hoặc một tập nguồn phân tán.
- Một mật khẩu hoặc pattern lỗi lặp lại trên nhiều tài khoản.
- Tỷ lệ đăng nhập thất bại tăng so với baseline.
- Một vài tài khoản thành công bất thường sau chuỗi thử.

### Phản ứng

1. Áp dụng rate limit tổng thể và theo nguồn/account; không khóa hàng loạt tài khoản chỉ dựa trên số lần sai.
2. Tăng challenge/risk verification cho traffic bất thường.
3. Bảo vệ tài khoản đặc quyền bằng passkey/MFA chống phishing.
4. Theo dõi các đăng nhập thành công từ pattern đáng ngờ và kiểm tra session mới.
5. Nếu phát hiện credential bị lộ, yêu cầu reset theo policy và thu hồi session/token liên quan.
6. Thông báo người dùng bị ảnh hưởng qua kênh đã xác minh.
7. Điều tra log đã giảm thiểu, cập nhật rule và đánh giá false positive.

### Chỉ số theo dõi

| Chỉ số | Mục đích |
| --- | --- |
| Failed login rate | Phát hiện tăng đột biến so với baseline. |
| Distinct accounts per source | Nhận diện password spraying. |
| Distinct sources per account | Nhận diện brute force phân tán. |
| Credential stuffing signal | Phát hiện pattern dùng credential bị lộ. |
| MFA denial/push rate | Phát hiện MFA fatigue hoặc lạm dụng step-up. |
| Successful login after failures | Ưu tiên rà soát session mới và hành vi tiếp theo. |
| False positive / challenge rate | Đảm bảo kiểm soát không chặn quá mức người dùng hợp lệ. |

## 16. Kiểm thử failed login

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Username không tồn tại | Thông báo công khai tương đương credential sai; không tạo session. |
| Username tồn tại, mật khẩu sai | Không tiết lộ trạng thái account; ghi event nội bộ phù hợp. |
| Account disabled | Không tạo session; public response không tiết lộ trạng thái nhạy cảm. |
| Nhiều lần thử một tài khoản | Throttling/backoff theo policy, không khóa vĩnh viễn dễ bị DoS. |
| Một nguồn thử nhiều tài khoản | Phát hiện password spraying ở mức tổng thể. |
| Nhiều nguồn thử một tài khoản | Phát hiện brute force phân tán và áp dụng risk policy. |
| Credential stuffing | Rate limit, risk challenge và cảnh báo theo pattern. |
| TOTP sai/hết hạn/replay | Từ chối, giới hạn thử, không tạo authenticated session. |
| Push bị từ chối nhiều lần | Cooldown/cảnh báo; không spam push. |
| WebAuthn origin/challenge sai | Từ chối response. |
| OIDC state/nonce/issuer/audience sai | Không tạo RP session. |
| Token hết hạn hoặc revoked | Yêu cầu xác thực lại theo policy. |
| Session store không sẵn sàng | Không fail-open cho tài nguyên cần kiểm tra session. |
| Password hash service lỗi | Báo lỗi dịch vụ phù hợp; không phân loại thành mật khẩu sai. |
| Log và trace | Không chứa mật khẩu, OTP, cookie, token hoặc recovery secret. |
| Recovery endpoint | Không tiết lộ account existence qua status, body hoặc timing rõ rệt. |
| CAPTCHA/challenge | Có phương án accessible và không được coi là xác thực danh tính. |

### Kiểm thử khả năng chịu tải

Rate limit, password hashing và MFA verification đều tiêu thụ tài nguyên. Cần kiểm thử tải để bảo đảm:

- Attacker không thể làm cạn worker/CPU bằng request xác thực đắt đỏ.
- Throttling phân tán hoạt động nhất quán giữa nhiều instance.
- Dependency timeout không làm request bị treo vô hạn.
- Bộ đếm và nonce/challenge được cập nhật nguyên tử.
- Người dùng hợp lệ có đường thử lại và recovery rõ ràng.

## 17. Checklist thiết kế failed login

- [ ] Phân loại lỗi theo giai đoạn: credential, account, MFA, federation, session và hạ tầng.
- [ ] Thông báo công khai không tiết lộ account existence hoặc trạng thái bảo mật.
- [ ] Rà soát status code, body, redirect, timing và notification để chống enumeration.
- [ ] Dùng password hashing chuyên dụng, salt riêng và cấu hình phù hợp.
- [ ] Rate limit theo account, source, device/client và toàn hệ thống.
- [ ] Phát hiện brute force, password spraying và credential stuffing phân tán.
- [ ] Tránh account lockout vĩnh viễn dễ bị lợi dụng gây DoS.
- [ ] MFA failure có attempt limit, replay protection và chống push fatigue.
- [ ] Không tạo session/token authenticated trước khi hoàn tất toàn bộ xác thực.
- [ ] Phân biệt credential failure với lỗi dịch vụ/issuer.
- [ ] Recovery flow có purpose binding, TTL, one-time use và thông báo độc lập.
- [ ] Log đủ điều tra nhưng không ghi password, OTP, token, cookie hoặc private key.
- [ ] Có cảnh báo cho đăng nhập thành công bất thường sau nhiều lần thất bại.
- [ ] Kiểm thử timing, race condition, rate limit phân tán và khả năng chịu tải.
- [ ] Có phương án accessible cho CAPTCHA/challenge và hỗ trợ người dùng hợp lệ.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao không nên trả “tài khoản không tồn tại” trong trang đăng nhập?

**Gợi ý:** Phản hồi đó cho phép attacker thu thập danh sách tài khoản. Cần thông báo chung và rà soát cả status code, timing, redirect, notification.

**Câu 2.** Password spraying khác brute force như thế nào?

**Gợi ý:** Spraying thử ít mật khẩu trên nhiều tài khoản; brute force thường thử nhiều mật khẩu trên một hoặc một số tài khoản. Cần phát hiện ở nhiều chiều.

**Câu 3.** Vì sao khóa tài khoản sau vài lần sai có thể tạo DoS?

**Gợi ý:** Attacker có thể cố tình nhập sai để khóa tài khoản nạn nhân. Throttling/backoff và risk challenge thường linh hoạt hơn khóa cứng.

**Câu 4.** Nếu password hash service gặp lỗi, có nên báo mật khẩu sai không?

**Gợi ý:** Không. Đây là lỗi hạ tầng; phân loại sai có thể khóa nhầm người dùng và che giấu sự cố.

**Câu 5.** Vì sao không tạo session authenticated trước khi MFA hoàn tất?

**Gợi ý:** Attacker có thể truy cập protected resource bằng session chưa đạt toàn bộ policy; trạng thái pending phải tách biệt và giới hạn quyền.

**Câu 6.** CAPTCHA có chứng minh người dùng là chủ tài khoản không?

**Gợi ý:** Không. CAPTCHA chỉ tăng chi phí tự động hóa, không phải yếu tố xác thực danh tính.

**Câu 7.** Vì sao phải theo dõi số nguồn thử trên một tài khoản và số tài khoản bị thử từ một nguồn?

**Gợi ý:** Hai góc nhìn giúp phát hiện brute force phân tán và password spraying mà bộ đếm đơn lẻ có thể bỏ sót.

## 19. Ghi nhớ

**Failed login là một kết quả của quá trình xác thực cần được xử lý vừa an toàn vừa có khả năng phục hồi.** Ứng dụng nên dùng phản hồi công khai chung để chống account enumeration, nhưng phân loại lỗi nội bộ chính xác; kết hợp rate limit đa chiều, throttling, backoff và phát hiện brute force/password spraying/credential stuffing; tránh khóa tài khoản cứng dễ bị lợi dụng gây DoS. Mật khẩu phải được xác minh bằng password hashing chuyên dụng, MFA có giới hạn thử và chống replay, còn session/token chỉ được cấp sau khi toàn bộ policy xác thực hoàn tất. Recovery, logging, thông báo và giám sát đều phải bảo vệ secret và không tạo đường vòng hạ thấp assurance.
