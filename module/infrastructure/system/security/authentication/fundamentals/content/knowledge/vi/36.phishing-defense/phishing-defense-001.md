# Phishing threat: mối đe dọa phishing đối với xác thực danh tính

> **Chương:** Chống phishing  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này mô hình hóa phishing như một cuộc tấn công vào con người, credential, authenticator, token và phiên; phân tích các biến thể phổ biến cùng cách phòng vệ ở lớp giao thức, ứng dụng, thiết bị và quy trình vận hành.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích phishing và phân biệt credential phishing, session/token theft, MFA fatigue, OAuth consent phishing và business email compromise.
2. Mô hình hóa chuỗi tấn công từ dụ người dùng đến đánh cắp credential, chiếm phiên và duy trì quyền truy cập.
3. Nhận diện các giới hạn của password, OTP, SMS, push approval và các cơ chế MFA khác.
4. Giải thích vì sao passkey/WebAuthn có khả năng chống phishing tốt nhờ ràng buộc origin/RP ID.
5. Phân biệt phishing-resistant authentication với bảo vệ endpoint, recovery và authorization.
6. Thiết kế kiểm soát cho email/domain, browser, session, OAuth consent, recovery và helpdesk.
7. Phát hiện, báo cáo, containment và khôi phục sau phishing hoặc adversary-in-the-middle (AiTM).
8. Xây dựng kiểm thử và diễn tập phishing tập trung vào hành vi hệ thống, không chỉ nhận thức người dùng.

## 2. Phishing là gì?

**Phishing** là hình thức lừa người dùng hoặc hệ thống tin cậy thực hiện một hành động có lợi cho attacker, thường bằng cách giả mạo danh tính, thương hiệu, thông điệp hoặc ngữ cảnh giao tiếp. Trong hệ thống xác thực, mục tiêu thường là khiến nạn nhân:

- Nhập username/password vào trang giả.
- Cung cấp OTP hoặc mã recovery.
- Chấp thuận một push request không do họ khởi tạo.
- Quét QR code dẫn tới luồng đăng nhập hoặc liên kết tài khoản giả.
- Cấp quyền OAuth cho ứng dụng độc hại.
- Cài phần mềm hoặc extension có thể đọc dữ liệu phiên.
- Mở tệp hoặc liên kết khiến endpoint bị compromise.
- Tiết lộ thông tin cho helpdesk hoặc nhân viên hỗ trợ giả.

Phishing không chỉ là email giả. Nó có thể diễn ra qua SMS, cuộc gọi, chat, mạng xã hội, QR code, quảng cáo tìm kiếm, tài liệu chia sẻ, lịch họp hoặc thông báo giả trong ứng dụng.

Trong authentication security, phishing cần được xem là cuộc tấn công vào toàn bộ chuỗi tin cậy: user, browser, IdP, RP, authenticator, session, token, recovery và helpdesk.

## 3. Tài sản và mục tiêu attacker

Attacker có thể nhắm tới nhiều loại tài sản:

| Tài sản | Giá trị đối với attacker | Tác động nếu bị chiếm |
|---|---|---|
| Username/password | Đăng nhập hoặc thử credential reuse ở dịch vụ khác | Account takeover |
| OTP/TOTP code | Vượt qua một số luồng MFA | Đăng nhập trái phép trong cửa sổ mã |
| Push approval | Hoàn tất challenge nếu user chấp thuận | MFA bypass hoặc xác thực thay user |
| Session cookie | Duy trì phiên đã đăng nhập | Session hijacking |
| Access/refresh token | Gọi API hoặc xin token mới | Truy cập dữ liệu và hành động trái phép |
| OAuth consent/grant | Cấp quyền cho client độc hại | Truy cập mailbox, files, profile hoặc API |
| Recovery code/link | Đặt lại credential hoặc authenticator | Chiếm quyền lâu dài |
| Passkey enrollment flow | Thêm authenticator của attacker | Duy trì quyền truy cập sau khi password đổi |
| Helpdesk/admin workflow | Reset MFA, đổi email hoặc cấp lại quyền | Chiếm tài khoản đặc quyền |
| Endpoint/browser | Đọc token, cookie hoặc dữ liệu người dùng | Vượt qua nhiều lớp bảo vệ phía server |

Mục tiêu có thể là một tài khoản cá nhân, một tài khoản quản trị, một workload identity hoặc một người có quyền phê duyệt thanh toán. Tài khoản ít đặc quyền vẫn có thể là bước đệm để chiếm tài khoản cao hơn.

## 4. Chuỗi tấn công phishing

Một cuộc tấn công thường gồm nhiều bước. Chặn được một bước có thể ngăn attacker đi tiếp, nhưng cần hiểu toàn bộ chuỗi để không chỉ xử lý email ban đầu.

~~~mermaid
flowchart TD
    A["Reconnaissance and target selection"] --> B["Lure: email, SMS, QR, voice or chat"]
    B --> C["Victim opens link or attachment"]
    C --> D["Credential capture / OAuth consent / malware"]
    D --> E["MFA relay, push approval or session theft"]
    E --> F["Attacker obtains account or session access"]
    F --> G["Persistence: add authenticator, OAuth app or recovery channel"]
    G --> H["Abuse: mailbox, files, admin actions or data exfiltration"]
    H --> I["Detection, containment and recovery"]
~~~

Ví dụ: An nhận email giả thông báo tài liệu cần ký. Trang giả yêu cầu password và OTP. Attacker dùng thông tin đó trong một luồng đăng nhập thật, lấy được phiên hoặc token. Sau khi vào được tài khoản, attacker có thể thêm phương thức recovery, cấp consent OAuth hoặc tạo phiên mới.

Vì vậy, đổi password có thể chưa đủ. Cần xác định attacker đã lấy được session/token nào, đã thêm authenticator hay consent nào và có truy cập tài nguyên downstream hay không.

## 5. Credential harvesting

Credential harvesting là việc dụ người dùng cung cấp credential cho một bên giả mạo. Các dấu hiệu thường gặp:

- Domain gần giống domain thật hoặc dùng ký tự nhìn giống nhau.
- Trang đăng nhập giả dùng logo, màu sắc và nội dung giống nhà cung cấp.
- Liên kết chuyển hướng qua nhiều domain.
- Thông báo khẩn cấp, đe dọa khóa tài khoản hoặc yêu cầu xác minh bất thường.
- Tệp đính kèm giả hóa đơn, tài liệu hoặc thông báo nội bộ.
- Trang giả yêu cầu cả password lẫn OTP để relay ngay sang dịch vụ thật.

HTTPS và biểu tượng khóa chỉ chứng minh kết nối được mã hóa tới domain đang mở; chúng không chứng minh domain đó thuộc tổ chức đúng. Attacker cũng có thể lấy certificate TLS hợp lệ cho domain giả.

### Phòng vệ

- Dùng passkey/WebAuthn cho đăng nhập tương tác khi có thể.
- Dùng password manager có domain matching để giảm nguy cơ điền password vào domain giả.
- Không yêu cầu user gửi password/OTP qua email, chat hoặc cuộc gọi.
- Dùng domain đăng nhập nhất quán và thông báo rõ kênh chính thức.
- Bảo vệ email bằng SPF, DKIM, DMARC và giám sát domain lookalike.
- Dùng URL allowlist và redirect URI chính xác trong các luồng authentication.
- Đào tạo người dùng báo cáo message đáng ngờ mà không yêu cầu họ tự điều tra liên kết độc hại.

Password manager có thể giúp nhận diện domain không khớp, nhưng không bảo vệ khỏi endpoint bị compromise, OAuth consent phishing hoặc người dùng tự copy/paste secret vào nơi không an toàn.

## 6. Adversary-in-the-middle (AiTM) và session theft

Trong phishing kiểu AiTM, attacker đặt một proxy trung gian giữa browser của nạn nhân và dịch vụ thật. Nạn nhân có thể nhìn thấy một trang đăng nhập gần giống luồng thật, trong khi attacker chuyển tiếp các request/response tới dịch vụ thật.

Nếu luồng xác thực dùng password và OTP có thể relay, attacker có thể thu thập kết quả xác thực và session cookie sau khi đăng nhập thành công. Session cookie bị đánh cắp có thể cho phép attacker truy cập mà không cần biết password hoặc thực hiện MFA lại ngay lập tức.

Điểm cần hiểu:

- MFA dựa trên OTP có thể bị relay theo thời gian thực.
- TLS bảo vệ từng kết nối nhưng không tự bảo đảm người dùng đang kết nối tới đúng dịch vụ.
- Cookie Secure/HttpOnly/SameSite giảm một số kiểu đánh cắp hoặc gửi cookie sai ngữ cảnh, nhưng không ngăn mọi AiTM.
- Token lifetime ngắn giảm cửa sổ sử dụng nhưng không loại bỏ token theft.
- DPoP/mTLS có thể ràng buộc token với khóa/certificate của sender trong use case phù hợp.
- WebAuthn ràng buộc proof với origin/RP ID, khiến trang giả trên domain khác không thể tạo assertion hợp lệ cho RP thật.

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant Browser
    participant Proxy as Attacker-controlled relay
    participant IdP as Real identity provider

    User->>Browser: Open deceptive sign-in link
    Browser->>Proxy: Login request through lookalike site
    Proxy->>IdP: Relay request to real IdP
    IdP-->>Proxy: Authentication challenge
    Proxy-->>Browser: Forward challenge
    User->>Browser: Enter password / OTP
    Browser->>Proxy: Submit response
    Proxy->>IdP: Relay response
    IdP-->>Proxy: Authenticated response and session
    Proxy-->>Browser: Forward page while attacker may capture session material
~~~

Sơ đồ mô tả rủi ro ở mức khái niệm, không phải hướng dẫn dựng proxy. Phòng vệ phải giảm khả năng relay credential và bảo vệ session/token sau khi xác thực.

## 7. MFA không đồng nghĩa phishing-resistant

MFA làm tăng số loại bằng chứng cần có, nhưng không phải mọi phương thức MFA đều chống phishing:

| Phương thức | Có thể bị phishing/relay? | Nhận xét |
|---|---|---|
| Password | Có | Secret có thể bị nhập vào trang giả hoặc tái sử dụng |
| SMS OTP | Có | Mã có thể bị relay; còn rủi ro SIM swap và interception |
| Email OTP | Có | Phụ thuộc bảo mật mailbox; mã có thể bị relay |
| TOTP | Có | Mã dùng trong thời gian ngắn nhưng có thể bị lấy và relay ngay |
| Push approval | Có | User có thể bị lừa chấp thuận; push fatigue làm tăng nguy cơ |
| Push number matching | Giảm một số kiểu nhầm lẫn | Vẫn có thể bị lừa nếu user chủ động nhập mã vào prompt giả |
| FIDO2/WebAuthn passkey | Có khả năng chống phishing mạnh | Proof ràng buộc với RP ID/origin; vẫn phụ thuộc endpoint và recovery |
| Client certificate/mTLS | Chống một số kiểu credential relay | Phù hợp môi trường quản lý; cần bảo vệ private key và PKI |

Không tuyên bố “đã bật MFA” là đã giải quyết phishing. Cần xem phương thức, khả năng relay, độ độc lập, cách recovery và việc session/token được bảo vệ ra sao.

## 8. Passkey và WebAuthn chống phishing như thế nào?

Passkey/WebAuthn dùng public-key cryptography. Trong registration, authenticator tạo key pair và RP lưu public key. Trong authentication, RP tạo challenge; authenticator ký dữ liệu liên quan bằng private key.

Một assertion hợp lệ được ràng buộc với:

- Challenge do RP tạo.
- RP ID hash.
- Origin của browser.
- Credential ID/public key đã đăng ký.
- Client data và authenticator data.

Một trang giả trên domain khác không thể yêu cầu authenticator tạo assertion hợp lệ cho RP thật vì origin/RP ID không khớp.

### Lợi ích

- User không phải nhập password hoặc OTP vào trang web.
- Private key không được gửi tới RP.
- Proof gắn với origin/RP ID giúp ngăn credential harvesting và AiTM relay giữa các domain.
- Có thể yêu cầu user verification bằng PIN hoặc sinh trắc học cục bộ.

### Giới hạn

- Malware hoặc remote control trên endpoint có thể thao túng phiên sau khi user đã xác thực.
- Recovery yếu có thể cho attacker thêm passkey của họ.
- Helpdesk có thể bị lạm dụng để reset authenticator.
- User có thể bị lừa đăng nhập vào đúng domain của attacker trong một dịch vụ khác hoặc cấp OAuth consent.
- Attacker có thể chiếm session/token bằng malware hoặc extension độc hại sau authentication.
- Passkey sync và account ecosystem có trust model riêng; cần bảo vệ account đồng bộ.

Passkey làm phishing credential khó hơn rất nhiều, nhưng không thay thế endpoint security, session protection, recovery policy và authorization.

## 9. MFA fatigue và push bombing

MFA fatigue xảy ra khi attacker gửi nhiều yêu cầu push để người dùng mệt mỏi, nhầm lẫn hoặc chấp thuận một prompt không do họ khởi tạo.

Rủi ro tăng khi:

- Prompt không hiển thị ứng dụng, vị trí hoặc ngữ cảnh đăng nhập.
- Người dùng được khuyến khích bấm Approve theo phản xạ.
- Không có rate limit hoặc cooldown.
- Một push approval có thể hoàn tất mọi loại action.
- Người dùng không có nút từ chối/báo cáo dễ thấy.

Kiểm soát:

- Number matching và hiển thị context rõ ràng.
- Rate limit theo account/session và phát hiện nhiều challenge bất thường.
- Cooldown hoặc tạm ngừng push sau nhiều lần từ chối.
- Push chỉ phê duyệt đúng request đã tạo, có transaction/session binding.
- Không dùng push đơn giản làm fallback cho action yêu cầu phishing-resistant MFA.
- Hướng dẫn user từ chối prompt không do họ khởi tạo và báo cáo ngay.

Number matching giúp giảm approve nhầm, nhưng không biến push thành phishing-resistant. Nếu attacker điều khiển luồng giả và hướng dẫn user nhập số, user vẫn có thể bị lừa.

## 10. OAuth consent phishing

OAuth consent phishing không nhất thiết đánh cắp password. Attacker dụ user cấp quyền cho một ứng dụng OAuth độc hại. Sau khi user consent, ứng dụng có thể nhận access/refresh token hoặc quyền truy cập theo scope đã được chấp thuận.

Ví dụ quyền có thể bao gồm:

- Đọc email hoặc tệp.
- Đọc profile và danh bạ.
- Gửi email hoặc thay đổi dữ liệu.
- Duy trì quyền truy cập thông qua refresh token nếu policy cho phép.

Kiểm soát:

- Giới hạn user consent cho ứng dụng chưa được xác minh hoặc scope nhạy cảm.
- Dùng admin consent workflow và app allowlist.
- Hiển thị publisher, client identity và scope dễ hiểu.
- Giám sát app registration, consent grant và refresh token bất thường.
- Có khả năng revoke consent/grant và thu hồi token liên quan.
- Kiểm tra redirect URI, issuer, audience và client configuration.
- Đào tạo user không cấp quyền chỉ vì một trang yêu cầu “Continue” hoặc “Accept”.

OAuth là cơ chế ủy quyền; consent hợp lệ không có nghĩa ứng dụng được cấp quyền là đáng tin. Cần quản lý client và scope như một bề mặt tấn công riêng.

## 11. QR phishing (quishing), SMS và voice phishing

### QR phishing

QR code có thể che giấu domain đích vì người dùng không nhìn thấy URL trước khi quét. QR có thể xuất hiện trong email, poster, tài liệu, hóa đơn hoặc nơi công cộng.

Phòng vệ:

- Dùng camera/browser hiển thị domain trước khi mở.
- Không đăng nhập hoặc nhập OTP sau khi quét QR từ nguồn không xác minh.
- Dùng passkey và kiểm tra domain/RP context.
- Với QR đăng nhập thiết bị, hiển thị rõ thiết bị/phiên đang được liên kết và yêu cầu xác nhận trên thiết bị đã đăng nhập.
- Có thể thu hồi liên kết thiết bị nếu user báo không phải yêu cầu của họ.

### SMS phishing (smishing)

Tin nhắn giả giao hàng, ngân hàng, cơ quan nhà nước hoặc thông báo tài khoản có thể dẫn tới trang credential harvesting hoặc cài ứng dụng giả. Không dùng số điện thoại hiển thị làm bằng chứng sender vì có thể bị giả mạo.

### Voice phishing (vishing)

Attacker gọi điện giả nhân viên IT, ngân hàng, helpdesk hoặc quản lý để yêu cầu đọc OTP, cài công cụ hỗ trợ từ xa, đổi MFA hoặc cấp quyền. Caller ID và thông tin nội bộ không đủ xác minh người gọi.

Quy tắc vận hành:

- Không đọc OTP, recovery code hoặc password cho người gọi.
- Kết thúc cuộc gọi và gọi lại qua số chính thức đã biết.
- Helpdesk không yêu cầu user chia sẻ secret.
- Thay đổi MFA/admin phải đi qua workflow có xác thực và audit.

## 12. Business email compromise và giả mạo nội bộ

Business Email Compromise (BEC) thường lợi dụng mailbox bị chiếm hoặc giả mạo danh tính quản lý/đối tác để yêu cầu:

- Chuyển tiền hoặc đổi thông tin tài khoản nhận.
- Gửi tài liệu, dữ liệu khách hàng hoặc credential.
- Cấp quyền ứng dụng hoặc phê duyệt OAuth consent.
- Thay đổi email/phone recovery.
- Reset MFA hoặc cấp certificate/API key.

Phòng vệ:

- Quy trình xác minh out-of-band cho thay đổi thanh toán hoặc recovery contact.
- Dual approval cho giao dịch và thao tác đặc quyền.
- Tách người yêu cầu, người phê duyệt và người thực hiện.
- SPF, DKIM, DMARC và kiểm soát domain lookalike.
- Cảnh báo thay đổi mailbox rule, forwarding và OAuth app grant.
- Audit hành động nhạy cảm và thông báo qua kênh độc lập.

Không xác nhận yêu cầu nhạy cảm chỉ dựa vào email, display name hoặc chuỗi hội thoại có vẻ quen thuộc.

## 13. Phishing nhắm vào recovery và enrollment

Attacker thường nhắm vào các luồng có thể thay đổi gốc tin cậy:

- Password reset.
- Thay email hoặc số điện thoại recovery.
- Xóa TOTP hoặc passkey.
- Thêm authenticator mới.
- Cấp lại recovery code.
- Helpdesk reset MFA.
- Enroll thiết bị hoặc certificate mới.

Các kiểm soát:

1. Yêu cầu step-up bằng phương thức hiện có khi có thể.
2. Recovery có assurance riêng, không chỉ dựa trên email/SMS.
3. Grant gắn purpose, account, session và thời hạn.
4. Thay đổi recovery channel cần thông báo kênh cũ.
5. Cooling-off cho hành động rủi ro cao.
6. Thêm/xóa authenticator phải có notification và audit.
7. Revoke session/token cũ khi nghi compromise.
8. Không cho một recovery token dùng để reset MFA nếu chỉ được cấp cho password reset.

Phishing-resistant login không bảo vệ được tài khoản nếu attacker có thể thuyết phục helpdesk xóa passkey rồi đăng ký passkey mới cho họ.

## 14. Email và domain protection

Email là kênh phân phối nhiều phishing lure và recovery link. Các biện pháp domain/email giúp giảm spoofing và phát hiện giả mạo:

- **SPF:** xác định máy chủ được phép gửi email cho domain theo policy DNS.
- **DKIM:** ký email để người nhận kiểm tra chữ ký và tính toàn vẹn của một số header/body.
- **DMARC:** yêu cầu alignment giữa domain hiển thị ở From với SPF hoặc DKIM và công bố policy xử lý.
- **MTA-STS/DANE TLS reporting:** có thể hỗ trợ bảo vệ hoặc giám sát một số khía cạnh truyền tải email theo môi trường.
- **Domain monitoring:** phát hiện domain lookalike, typo-squatting và certificate mới đáng ngờ.
- **Brand protection:** phối hợp registrar, hosting provider và abuse contact để xử lý domain giả.

SPF/DKIM/DMARC không ngăn được mọi phishing. Email hợp lệ từ mailbox đã bị chiếm vẫn có thể lừa người nhận; domain gần giống cũng có thể có SPF/DKIM riêng. Cần kết hợp xác thực người gửi, anti-malware, URL analysis, user reporting và quy trình phê duyệt out-of-band.

## 15. Browser, session và token protection

Phishing có thể lấy được session sau khi user đăng nhập. Vì vậy, bảo vệ browser/session là lớp quan trọng:

- Cookie session dùng Secure, HttpOnly và SameSite phù hợp.
- Không lưu session token dài hạn trong localStorage nếu có kiến trúc BFF/server-side session phù hợp hơn.
- Dùng Content Security Policy để giảm một số nguy cơ XSS.
- Giới hạn extension và quyền browser trên thiết bị quản lý.
- Dùng session rotation sau login/step-up và revoke phía server khi logout/incident.
- Giới hạn token lifetime và scope/audience.
- Dùng refresh token rotation/reuse detection khi phù hợp.
- Cân nhắc DPoP/mTLS sender-constraining cho client/API có khả năng giữ khóa.
- Không log Authorization header, cookie hoặc token.
- Có khả năng revoke session/token sau phishing.

HttpOnly giảm khả năng JavaScript đọc cookie, nhưng không ngăn mọi hành động XSS thay mặt user. CSP là defense-in-depth; không thay output encoding, input handling và kiểm thử XSS.

## 16. OAuth/OIDC và chống login phishing

Trong OIDC Authorization Code Flow:

- Dùng Authorization Code Flow với PKCE.
- Tạo state ngẫu nhiên, lưu server-side và ràng buộc với browser transaction.
- Dùng nonce và so khớp trong ID token.
- So khớp issuer chính xác; xác minh chữ ký, audience, expiry và authorized party khi cần.
- Đăng ký redirect URI chính xác, không wildcard tùy tiện.
- Không tự động tin IdP hoặc issuer do callback input quyết định.
- Bảo vệ client secret ở backend; public client không nhúng secret vào app.
- Dùng consent policy và client allowlist cho scope nhạy cảm.

~~~text
OIDC transaction state:
  expected_issuer = configured issuer
  client_id = registered client
  redirect_uri = exact registered URI
  state = random one-time value
  nonce = random one-time value
  pkce_verifier = client-held secret
  browser_session = current transaction owner
  expires_at = short deadline
~~~

Những tham số này bảo vệ các phần khác nhau của luồng. PKCE không thay state/nonce; state không thay issuer/audience validation; HTTPS không thay domain verification.

## 17. Detection: nhận biết dấu hiệu compromise

Không chỉ tìm email đáng ngờ. Sau phishing, attacker có thể để lại dấu vết ở IdP, RP, mailbox, OAuth grants và endpoint.

### Tín hiệu đáng giám sát

- Đăng nhập thành công ngay sau nhiều lần thất bại hoặc từ nguồn bất thường.
- Đăng nhập mới sau khi user báo đã nhập OTP vào trang giả.
- Thêm passkey/security key/TOTP hoặc thay recovery contact bất thường.
- MFA reset/helpdesk override không theo quy trình.
- Tạo OAuth app, consent grant hoặc scope nhạy cảm mới.
- Refresh token reuse hoặc token exchange bất thường.
- Session mới đồng thời ở vị trí/thiết bị không phù hợp.
- Mailbox forwarding rule, inbox rule hoặc delegated access mới.
- API call/download lớn sau đăng nhập bất thường.
- Tạo client secret, API key hoặc certificate ngoài change window.
- Tắt logging, thay đổi MFA policy hoặc thêm admin role.

### Correlate sự kiện

Kết hợp thời gian, account, session ID dạng correlation, client ID, IP/ASN, device context, authentication method, token family ID và change event. Không ghi raw token/cookie để correlation; dùng ID nội bộ hoặc fingerprint an toàn theo policy.

Một tín hiệu đơn lẻ như IP mới không chứng minh compromise. Cần xem chuỗi sự kiện và tác động.

## 18. Incident response sau phishing

Khi user báo đã nhập password/OTP hoặc chấp thuận prompt lạ, phản ứng cần nhanh và theo phạm vi:

1. **Triage:** xác định user, thời điểm, domain/message, dữ liệu đã nhập và hành động đã chấp thuận.
2. **Contain session:** revoke session hiện tại và các phiên đáng ngờ; yêu cầu đăng nhập lại bằng phương thức đáng tin.
3. **Credential:** đổi password nếu đã lộ; revoke/re-enroll authenticator nếu bị ảnh hưởng.
4. **Token:** revoke refresh token/token family, OAuth grants và access token theo cơ chế hệ thống.
5. **Recovery/enrollment:** kiểm tra authenticator, email/phone recovery và passkey mới được thêm.
6. **OAuth:** thu hồi consent/app grant đáng ngờ và kiểm tra token đã cấp.
7. **Mailbox:** kiểm tra forwarding/inbox rules, delegates và suspicious sent items.
8. **Endpoint:** cô lập/kiểm tra thiết bị nếu có dấu hiệu malware, remote access hoặc extension độc hại.
9. **Downstream:** rà soát API, cloud, file access, data export và quyền đã sử dụng.
10. **Notify:** thông báo qua kênh đã xác minh và hướng dẫn user báo cáo hoạt động lạ.
11. **Preserve evidence:** giữ audit/log cần thiết, tránh lưu secret hoặc phát tán liên kết độc hại.
12. **Recover and monitor:** khôi phục quyền, xác minh lại authenticator và tăng giám sát sau sự cố.

Đổi password một mình không đủ nếu attacker đã có session cookie, refresh token, OAuth grant hoặc authenticator riêng. Cần thu hồi mọi cơ chế duy trì quyền truy cập đã bị ảnh hưởng.

~~~mermaid
flowchart TD
    A["Phishing report / suspicious sign-in"] --> B["Triage account, time and exposed data"]
    B --> C["Revoke suspicious sessions and refresh tokens"]
    C --> D["Reset exposed credentials and review authenticators"]
    D --> E["Revoke OAuth grants and suspicious app access"]
    E --> F["Inspect mailbox, endpoint and downstream activity"]
    F --> G["Restore trusted authentication methods"]
    G --> H["Notify user and monitor for recurrence"]
    H --> I["Lessons learned and control improvements"]
~~~

## 19. Java/Spring: bảo vệ session và security headers

Ví dụ cấu hình Spring Security minh họa một số lớp bảo vệ web:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**", "/login/**").permitAll()
            .anyRequest().authenticated())
        .sessionManagement(session -> session
            .sessionFixation(fixation -> fixation.changeSessionId()))
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                    "default-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "frame-ancestors 'none'"
                ))
            .frameOptions(frame -> frame.deny())
        )
        .build();
}
~~~

Đây là ví dụ nền tảng, không phải cấu hình đầy đủ cho mọi ứng dụng. CSP cần được kiểm thử theo tài nguyên thực tế, tránh thêm unsafe-inline/unsafe-eval nếu không cần. Session cookie Secure/HttpOnly/SameSite nên được cấu hình ở servlet container hoặc Spring Session theo môi trường HTTPS.

### OIDC login transaction

Khi dùng Spring Security OAuth2 Login, ưu tiên cơ chế state, nonce, PKCE và token validation của framework/provider đã được cấu hình đúng. Không tự parse JWT bằng cách chỉ decode payload rồi tin claim.

Các điểm cần kiểm tra trong cấu hình:

- Issuer URI trỏ tới IdP được phê duyệt.
- Client ID và redirect URI đúng.
- Client secret lấy từ secret manager nếu là confidential client.
- PKCE được bật theo profile/client type phù hợp.
- Session và authorization request repository được bảo vệ.
- Redirect sau login chỉ tới destination nội bộ được allowlist.
- Logout và token revocation có flow riêng.

### Không log credential

Application logging, HTTP tracing, exception reporting và reverse proxy cần redact:

- Password và OTP.
- Authorization header.
- Cookie/Set-Cookie.
- ID/access/refresh token.
- OAuth authorization code, state và PKCE verifier.
- Recovery link/code.

Correlation ID và event metadata đủ để điều tra trong đa số trường hợp; không dùng raw credential làm log context.

## 20. Quy trình báo cáo phishing cho người dùng

Một quy trình báo cáo dễ dùng giúp giảm thời gian attacker có quyền:

1. Có nút/report address hoặc chức năng báo cáo trong email client.
2. Cho phép user báo cáo ngay cả khi đã bấm link hoặc nhập credential.
3. Hướng dẫn rõ không forward email chứa token hoặc thông tin nhạy cảm qua kênh công khai.
4. Có kênh liên hệ chính thức để xác minh yêu cầu từ IT/helpdesk.
5. Sau khi báo cáo, phản hồi rằng yêu cầu đã được tiếp nhận và nêu bước tiếp theo.
6. Không trách móc người báo cáo; khuyến khích báo cáo sớm.
7. Tự động chuyển sự kiện tới SOC/identity team theo severity.

Nếu user đã nhập OTP hoặc password, không chỉ yêu cầu họ “đổi password khi rảnh”. Kích hoạt containment ngay theo incident policy.

## 21. Security awareness và diễn tập

Đào tạo người dùng có ích nhưng không thể là lớp phòng vệ duy nhất. Nội dung nên tập trung vào hành động:

- Kiểm tra domain trước khi nhập credential.
- Không chia sẻ password, OTP, recovery code hoặc push approval.
- Không chấp thuận prompt không do mình khởi tạo.
- Xác minh out-of-band yêu cầu chuyển tiền, đổi recovery hoặc reset MFA.
- Dùng password manager/passkey và thiết bị cập nhật.
- Báo cáo nhanh khi đã bấm link hoặc nhập thông tin.

Phishing simulation cần:

- Mục tiêu đào tạo rõ ràng, không gây xấu hổ hoặc trừng phạt người dùng.
- Không thu thập password thật hoặc OTP thật.
- Không cài payload độc hại lên thiết bị người học.
- Đo hành vi báo cáo, thời gian báo cáo và hiệu quả cải thiện.
- Có hướng dẫn ngay sau tình huống mô phỏng.
- Bảo vệ dữ liệu kết quả và hạn chế sử dụng để đánh giá cá nhân ngoài mục đích đã công bố.

Đo tỷ lệ click đơn lẻ không phản ánh đầy đủ năng lực phòng vệ. Tỷ lệ báo cáo, thời gian phát hiện, số credential bị nhập và thời gian containment có giá trị vận hành hơn.

## 22. Ma trận kiểm thử phishing defense

| Kiểm thử | Kết quả mong đợi |
|---|---|
| User nhập password trên domain giả | Passkey/domain controls giảm khả năng credential bị cung cấp; phát hiện/report flow hoạt động |
| OTP bị relay trong AiTM simulation | Phát hiện giới hạn OTP; ưu tiên phishing-resistant authentication |
| WebAuthn assertion từ origin sai | RP từ chối |
| WebAuthn RP ID hash sai | RP từ chối |
| Push prompt không do user khởi tạo | User có thể deny/report; rate limit và alert hoạt động |
| OAuth app yêu cầu scope nhạy cảm chưa được duyệt | Consent policy chặn hoặc yêu cầu admin approval |
| Redirect URI không đăng ký | Authorization server từ chối |
| OIDC state/nonce sai | RP từ chối callback |
| Recovery token dùng cho MFA reset dù purpose chỉ password reset | Recovery service từ chối |
| Helpdesk agent tự reset admin MFA | Dual control/policy chặn |
| Email spoofing không đạt DMARC alignment | Mail policy xử lý theo cấu hình và tạo telemetry |
| Domain lookalike xuất hiện | Domain monitoring tạo cảnh báo |
| Session cookie bị replay sau incident revoke | Server từ chối |
| Refresh token reuse sau rotation | Token family policy phát hiện và revoke theo profile |
| OAuth consent grant độc hại đã được cấp | Có thể revoke grant/token và audit downstream |
| Mailbox forwarding rule mới sau login bất thường | Alert/correlation được tạo |
| Token xuất hiện trong application log | Secret scanner phát hiện; log phải được redacted |
| User báo đã nhập OTP | Incident flow revoke session/token và hướng dẫn recovery |
| Browser back button sau logout | Không truy cập được dữ liệu nhạy cảm qua API |
| Risk signal chỉ là IP mới | Không tự động coi là identity proof hoặc khóa account |
| Endpoint nghi có malware | Incident workflow cô lập/đánh giá endpoint |
| Phishing simulation | Không thu credential thật; báo cáo và học tập được đo an toàn |

Kiểm thử phải xác minh cả control và hậu quả: attacker có lấy được session không, có thêm authenticator/OAuth grant được không, token cũ có bị chặn không và người dùng có báo cáo được không.

## 23. Tình huống phân tích

### Tình huống A: user nhập OTP vào trang giả

An nhận email giả từ bộ phận IT, mở liên kết và nhập password cùng TOTP. Vài phút sau, hệ thống phát hiện một session mới.

**Phân tích:** TOTP có thể bị relay trong thời gian mã còn hiệu lực. Revoke session/token đáng ngờ, reset password nếu lộ, kiểm tra authenticator/recovery changes và ưu tiên passkey/WebAuthn cho lần xác thực tiếp theo.

### Tình huống B: user chấp thuận push không rõ nguồn

An nhận nhiều push liên tiếp và bấm Approve để thông báo biến mất.

**Phân tích:** MFA fatigue. Thu hồi phiên đáng ngờ, kiểm tra thiết bị và đăng nhập, áp dụng rate limit/number matching/context, hướng dẫn user từ chối prompt không do họ tạo.

### Tình huống C: OAuth app xin quyền đọc mailbox

Một trang giả yêu cầu đăng nhập Microsoft/Google và hiển thị màn hình consent cho ứng dụng lạ.

**Phân tích:** Đây là consent phishing. Kiểm tra client/publisher/scope, revoke grant và refresh token, điều tra mailbox access và hạn chế user consent cho app chưa được duyệt.

### Tình huống D: passkey vẫn bị chiếm qua recovery

Attacker không thể phishing passkey nhưng gọi helpdesk, giả danh nhân viên và yêu cầu reset MFA. Helpdesk xóa passkey cũ và cho đăng ký passkey mới.

**Phân tích:** Điểm yếu nằm ở recovery/helpdesk. Cần identity proofing, dual control, callback tới contact đã đăng ký, notification kênh cũ và audit.

### Tình huống E: token bị lấy từ endpoint

User đăng nhập bằng passkey đúng domain nhưng thiết bị có extension độc hại đọc được dữ liệu phiên hoặc điều khiển browser.

**Phân tích:** Phishing-resistant authentication không bảo vệ endpoint đã compromise. Cần xử lý extension/device, revoke session/token, kiểm tra persistence và dùng sender-constrained token khi phù hợp.

## 24. Quy trình thiết kế và vận hành

Trước khi triển khai chống phishing, hãy xác định:

1. Tài khoản, credential, token và workflow nào là mục tiêu quan trọng?
2. Các kênh phishing nào đang được dùng: email, SMS, voice, QR, chat, quảng cáo hay OAuth consent?
3. Có thể triển khai passkey/WebAuthn cho nhóm tài khoản nào?
4. MFA hiện tại có relay được không; fallback có yếu hơn phương thức chính không?
5. Recovery, helpdesk và enrollment có thể bị lạm dụng để thêm authenticator không?
6. Domain/email protection, DMARC và lookalike monitoring đã được cấu hình ra sao?
7. OAuth app consent, scope và client registration có được quản trị không?
8. Session/token có thể revoke nhanh sau khi user báo phishing không?
9. Có log/audit đủ correlate mà không lưu raw secret không?
10. Mailbox rule, OAuth grant, authenticator change và API activity có được giám sát không?
11. User có kênh báo cáo dễ dùng và phản hồi kịp thời không?
12. Helpdesk có xác minh out-of-band, dual control và audit không?
13. Endpoint/browser/extension được quản lý và cập nhật thế nào?
14. Có diễn tập AiTM, push fatigue, OAuth consent phishing và recovery abuse không?
15. Có đo thời gian phát hiện, revoke, containment và khôi phục không?

## 25. Ghi nhớ trọng tâm

- **Phishing nhắm vào toàn bộ chuỗi xác thực.** Password, OTP, session, token, OAuth grant, recovery và helpdesk đều có thể bị lạm dụng.
- **HTTPS không chứng minh domain là thật.** Kiểm tra origin/domain và dùng cơ chế ràng buộc theo giao thức.
- **MFA không mặc định chống phishing.** SMS, email OTP, TOTP và push có thể bị relay hoặc lừa chấp thuận.
- **Passkey/WebAuthn có khả năng chống phishing mạnh** nhờ ràng buộc origin/RP ID, nhưng không thay endpoint security hoặc recovery controls.
- **Session/token theft có thể xảy ra sau authentication.** Logout/revoke cần xử lý server-side và trên các hệ thống downstream.
- **OAuth consent phishing không cần đánh cắp password.** Quản trị client, consent, scope và grant là bắt buộc.
- **Recovery và helpdesk là mục tiêu quan trọng.** Một quy trình reset MFA yếu có thể vô hiệu hóa passkey.
- **Email/domain controls giúp giảm spoofing nhưng không chặn mọi phishing.** Mailbox thật bị chiếm vẫn có thể gửi thông điệp độc hại.
- **Incident response phải thu hồi persistence.** Kiểm tra session, refresh token, OAuth grant, authenticator, recovery channel và mailbox rule.
- **User reporting và diễn tập phải an toàn, không trừng phạt.** Báo cáo sớm giúp giảm thời gian attacker có quyền.

Chống phishing hiệu quả cần nhiều lớp: phương thức xác thực chống phishing, domain và email protection, quản lý OAuth, bảo vệ browser/session, recovery có assurance, giám sát và incident response. Không có một cảnh báo hay một factor riêng lẻ nào đủ bảo vệ tài khoản nếu các đường duy trì quyền truy cập vẫn có thể bị attacker kiểm soát.
