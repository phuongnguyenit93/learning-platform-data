# Privacy của login

## 1. Privacy trong đăng nhập là gì?

**Privacy của login** là cách thiết kế quy trình đăng nhập để chỉ thu thập, xử lý, chia sẻ và lưu giữ dữ liệu cá nhân cần thiết cho mục đích xác thực và bảo vệ tài khoản. Quy trình này phải bảo vệ bí mật credential, hạn chế khả năng suy luận danh tính hoặc trạng thái tài khoản, kiểm soát telemetry và cung cấp cách xử lý dữ liệu minh bạch trong toàn bộ vòng đời tài khoản.

Đăng nhập thường được xem là một thao tác kỹ thuật: người dùng nhập identifier và credential, hệ thống xác minh rồi tạo session. Trên thực tế, mỗi bước có thể tạo hoặc xử lý dữ liệu nhạy cảm: email, số điện thoại, địa chỉ IP, device identifier, vị trí ước lượng, dấu vân tay trình duyệt, thời gian đăng nhập, phương thức MFA, kết quả thất bại, token, session ID và lịch sử khôi phục. Nếu thu thập quá mức hoặc lưu không đúng cách, hệ thống có thể biến chức năng bảo vệ tài khoản thành nguồn rò rỉ dữ liệu.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, privacy của login liên quan trực tiếp đến credential, password, MFA, passkey, certificate, token, session, identity proofing và account recovery. Mục tiêu là bảo đảm hệ thống xác minh đúng principal nhưng không thu thập thêm thông tin, không tiết lộ account state cho người không có quyền và không giữ dữ liệu xác thực lâu hơn nhu cầu hợp lệ.

Sau bài học, người học có thể:

- Xác định dữ liệu cá nhân và dữ liệu xác thực phát sinh trong login flow.
- Áp dụng data minimization và purpose limitation.
- Phân biệt secret, personal data, security telemetry và public identifier.
- Thiết kế thông báo lỗi giảm account enumeration.
- Bảo vệ password, OTP, passkey metadata, token và session khỏi log/analytics.
- Đặt retention, access control và deletion policy cho login data.
- Đánh giá rủi ro từ third-party SDK, analytics, crash reporting và support tooling.
- Xử lý privacy trong MFA, device recognition, risk scoring và account recovery.
- Thiết kế audit có ích mà không ghi credential hoặc dữ liệu dư thừa.
- Kiểm thử privacy leakage trong response, URL, log, trace, backup và data export.

## 2. Login tạo ra những loại dữ liệu nào?

Một login flow có thể xử lý nhiều loại dữ liệu khác nhau. Không phải dữ liệu nào cũng nhạy cảm như nhau, nhưng cần xác định mục đích, nguồn, người nhận và thời hạn lưu cho từng loại.

| Nhóm dữ liệu | Ví dụ | Rủi ro privacy |
| --- | --- | --- |
| Account identifier | Email, username, số điện thoại, customer ID | Có thể liên kết hoạt động với một người hoặc tiết lộ họ có tài khoản |
| Authentication secret | Password, OTP, recovery code, client secret | Cho phép chiếm quyền nếu bị lộ |
| Cryptographic material | Private key, signing key, token secret | Có thể giả mạo principal hoặc client |
| Session/token | Session cookie, access token, refresh token, ID token | Có thể bị replay hoặc chiếm phiên |
| Device data | Device ID, model, OS version, app instance ID | Theo dõi thiết bị hoặc liên kết hoạt động |
| Network data | IP, ASN, proxy/VPN signal | Suy luận vị trí, tổ chức hoặc hành vi |
| Behavioral data | Tần suất đăng nhập, thời gian, pattern nhập liệu | Có thể tạo hồ sơ hành vi |
| Biometric data | Face/fingerprint template hoặc kết quả xác minh | Dữ liệu nhạy cảm, khó thay đổi nếu bị lộ |
| Security events | Login success/failure, MFA challenge, recovery event | Có thể tiết lộ trạng thái tài khoản và thói quen |
| Support/audit data | Ticket, admin action, correlation ID | Có thể chứa dữ liệu nhận diện hoặc lịch sử bảo mật |

### 2.1. Phân loại theo mức độ nhạy cảm

Một mô hình thực dụng:
- **Credential secret:** password, OTP, recovery code, private key, refresh token. Không được log hoặc chia sẻ ngoài cơ chế bảo vệ được thiết kế.
- **Session bearer material:** session cookie, access token hoặc token có thể dùng lại. Phải xử lý như credential.
- **Personal identifiers:** email, phone, user ID có thể liên kết với một người. Chỉ dùng ở nơi cần thiết và hạn chế hiển thị.
- **Security telemetry:** thời gian, kết quả, risk signal, IP hoặc device metadata. Cần giới hạn mục đích và retention.
- **Aggregated metrics:** số lượng thất bại theo thời gian hoặc tỷ lệ MFA. Có thể giảm khả năng nhận diện nếu aggregation và ngưỡng đủ tốt.
- **Public protocol metadata:** issuer, audience, algorithm hoặc key ID theo thiết kế. Dù không phải secret, vẫn có thể tiết lộ cấu trúc hệ thống.

Không gọi mọi thứ là “dữ liệu kỹ thuật” để bỏ qua privacy review. IP, device identifier và lịch sử đăng nhập có thể là dữ liệu cá nhân theo bối cảnh và luật áp dụng.

### 2.2. Data inventory và data flow

Với mỗi endpoint login, ghi rõ:
- Dữ liệu đầu vào.
- Nguồn dữ liệu.
- Mục đích xử lý.
- Thành phần nhận dữ liệu.
- Dữ liệu lưu bền vững và dữ liệu chỉ tồn tại trong bộ nhớ.
- Dữ liệu được gửi tới nhà cung cấp hoặc SDK nào.
- Retention và quy trình xóa.
- Vai trò/nhóm có quyền truy cập.

Data flow giúp phát hiện trường hợp password đi qua analytics, email xuất hiện trong URL, token lọt vào crash report hoặc IP được lưu vô thời hạn dù không còn mục đích.

## 3. Data minimization và purpose limitation

**Data minimization** yêu cầu chỉ thu thập dữ liệu cần thiết để đạt mục đích đã xác định. **Purpose limitation** yêu cầu sử dụng dữ liệu cho mục đích phù hợp, có thông báo và cơ sở xử lý thích hợp.

Ví dụ:
- Nếu email đủ để định danh account, không bắt buộc thu thêm ngày sinh chỉ để login.
- Nếu cần phát hiện credential stuffing, có thể lưu counter và tín hiệu abuse với retention giới hạn thay vì lưu toàn bộ nội dung request.
- Nếu cần nhận biết thiết bị đã đăng ký, dùng device credential reference hoặc key ID thay vì fingerprint phần cứng không cần thiết.
- Nếu cần thống kê MFA adoption, dùng số liệu tổng hợp thay vì giữ danh sách chi tiết từng prompt lâu dài.
- Nếu cần gửi cảnh báo đăng nhập, chỉ dùng địa chỉ liên hệ đã đăng ký và không chia sẻ lịch sử đăng nhập với analytics vendor.

### 3.1. Thu thập theo từng bước

Không nên yêu cầu tất cả dữ liệu ngay ở màn hình đăng nhập. Thu thập khi có nhu cầu thực tế:
- Login cơ bản cần identifier và credential hoặc authorization response.
- Risk-based authentication có thể cần một số tín hiệu thiết bị/network, nhưng phải có purpose và retention.
- Recovery có thể cần proofing bổ sung; chỉ yêu cầu khi recovery được kích hoạt.
- Enrollment MFA cần thông tin authenticator phù hợp, không cần lưu dữ liệu sinh trắc học.
- Audit cần actor, action, result và correlation reference, không cần raw credential.

Nếu một trường dữ liệu không ảnh hưởng đến authentication, security, support hoặc nghĩa vụ hợp lệ đã xác định, cân nhắc bỏ nó.

### 3.2. Không tái sử dụng dữ liệu ngoài mục đích

Dữ liệu thu thập để chống fraud không tự động được phép dùng để quảng cáo, phân tích hành vi hoặc profiling cho mục đích khác. Trước khi tái sử dụng, đánh giá mục đích, tính tương thích, thông báo, cơ sở xử lý và quyền của người dùng.

Không gắn login telemetry với marketing profile chỉ vì cả hai hệ thống cùng có customer ID.

## 4. Identifier và account enumeration

Login endpoint có thể tiết lộ email hoặc username có tồn tại hay không. Attacker có thể gửi nhiều identifier rồi so sánh response, timing hoặc hành vi UI để xây dựng danh sách account.

Ví dụ response không an toàn:
- “Email này chưa được đăng ký.”
- “Password của tài khoản tồn tại không đúng.”
- “Tài khoản đã bị khóa do có quá nhiều lần thử.”
- “Người dùng này đã bật MFA bằng số điện thoại kết thúc 1234.”

Các thông báo này có thể giúp attacker xác nhận danh tính, trạng thái hoặc phương thức bảo vệ của account.

### 4.1. Response normalization

Với login thất bại, dùng thông báo bên ngoài nhất quán, ví dụ: “Không thể đăng nhập bằng thông tin đã cung cấp.” Cùng một cấu trúc status/body cho identifier không tồn tại và credential sai, trừ khi có lý do UX và threat model đã đánh giá.

Không tiết lộ:
- Account có tồn tại hay không.
- Account đang active, suspended hay pending.
- Có bao nhiêu factor đã đăng ký.
- Email/phone recovery đầy đủ.
- Số lần thất bại chính xác hoặc ngưỡng lockout.
- Provider đăng nhập nào đã được liên kết.

Thông tin chi tiết có thể được cung cấp sau khi người dùng chứng minh quyền kiểm soát account hoặc qua support workflow đã xác minh.

### 4.2. Timing và side channel

Ngay cả khi message giống nhau, thời gian phản hồi có thể khác. Ví dụ:
- Account không tồn tại bị từ chối ngay.
- Account tồn tại thực hiện password hash verification tốn thời gian.
- Account bị disabled đi qua nhánh code khác.
- Account có MFA tạo thêm lookup hoặc network call.

Có thể giảm khác biệt dễ khai thác bằng fake password verifier, response path tương đương và giới hạn request. Không cần làm mọi request có timing giống tuyệt đối, nhưng cần đánh giá side channel trong threat model.

Không dùng một fake verifier yếu hơn nhiều so với password hashing thật; mục tiêu là tránh khác biệt quá rõ mà không làm endpoint dễ bị CPU exhaustion.

### 4.3. Recovery và registration cũng có enumeration risk

Các endpoint sau cũng có thể tiết lộ account existence:
- Forgot password.
- Resend verification.
- MFA recovery.
- Invite acceptance.
- Account linking.
- Username availability.
- SSO discovery.

Dùng response chung, cooldown và gửi thông báo qua kênh đã đăng ký. Không gửi thông báo tới email do attacker vừa nhập nếu chưa xác minh quan hệ với account.

## 5. Bảo vệ password và credential input

Password là secret người dùng cung cấp. Hệ thống cần bảo vệ nó trong toàn bộ đường đi từ browser/app tới verifier.

Nguyên tắc:
- Chỉ truyền qua TLS.
- Không ghi password vào access log, application log, trace hoặc analytics.
- Không đưa password vào URL, query string hoặc redirect parameter.
- Không lưu plaintext hoặc mã hóa có thể giải ngược để xác minh.
- Dùng password hashing chuyên dụng với salt riêng và cost phù hợp.
- Giới hạn quyền đọc password verifier database.
- Tránh gửi password sang third-party SDK.
- Không hiển thị password trong crash report hoặc support bundle.
- Không lưu password trong client persistent storage để tự điền ngoài cơ chế password manager của nền tảng.

### 5.1. Password hashing và privacy

Password verifier thường chứa salt và hash từ password, cùng tham số thuật toán. Hash không phải password plaintext, nhưng vẫn là dữ liệu bảo mật có giá trị cao vì attacker có thể thực hiện offline guessing nếu database bị lộ.

Dùng thuật toán password hashing phù hợp như Argon2id, scrypt, bcrypt hoặc PBKDF2 theo môi trường và chuẩn áp dụng. Chọn tham số đủ tốn kém, có benchmark và kế hoạch nâng cấp. Không dùng SHA-256 đơn lẻ làm password hash.

Salt không cần giữ bí mật nhưng phải duy nhất/ngẫu nhiên theo yêu cầu thuật toán. Pepper nếu dùng phải lưu riêng trong secret manager/HSM và có rotation/recovery plan.

### 5.2. Không log request body login

Một middleware ghi toàn bộ request body có thể vô tình lưu:
- Password.
- OTP.
- Recovery code.
- New password trong reset flow.
- Client secret.
- Assertion hoặc authorization code.

Đánh dấu field nhạy cảm và redact ở lớp logging/tracing trước khi serialize. Tốt hơn là allowlist field an toàn cần ghi thay vì denylist một vài tên field dễ bị bỏ sót.

### 5.3. Password manager và autofill

Ứng dụng nên hỗ trợ password manager và autofill của hệ điều hành/browser. Không ép người dùng copy password vào clipboard hoặc vô hiệu hóa paste. Clipboard có thể bị đọc bởi ứng dụng khác hoặc sync qua cloud tùy nền tảng; tránh tự động copy credential.

Không ghi giá trị autofill vào analytics hoặc event tracking. Không dùng password field như một input thông thường được đo thời gian gõ hoặc ghi lại keystroke.

## 6. OTP, MFA và recovery code

OTP, TOTP, push approval và recovery code đều là dữ liệu xác thực nhạy cảm.

Không log:
- OTP gửi qua SMS/email.
- TOTP code.
- TOTP seed hoặc provisioning URI.
- Push approval secret hoặc challenge material.
- Recovery code.
- Backup code set.
- QR code enrollment có chứa secret.

Có thể ghi sự kiện như “MFA verification succeeded” cùng factor type và correlation ID nếu cần audit, nhưng không ghi giá trị mã.

### 6.1. TOTP enrollment

TOTP secret cần được hiển thị trong quá trình enrollment theo cách có kiểm soát. QR code chứa secret; ai chụp được QR có thể tạo mã trong tương lai. Không đưa QR vào screenshot support, crash report hoặc telemetry.

Sau enrollment:
- Lưu secret mã hóa và hạn chế quyền truy cập.
- Không gửi secret tới analytics.
- Cung cấp recovery codes một lần và chỉ hiển thị theo cách an toàn.
- Thông báo khi factor được thêm/xóa.
- Không cho phép support agent xem seed.

### 6.2. Push MFA privacy

Push notification có thể tiết lộ người dùng đang đăng nhập, thời gian hoặc thiết bị. Nội dung notification trên lock screen nên tối thiểu, tránh hiển thị dữ liệu giao dịch hoặc thông tin cá nhân quá mức.

Audit cần phân biệt approve, deny, timeout và user-reported prompt. Không coi push delivered là proof người dùng đã chấp thuận.

### 6.3. Recovery codes

Recovery code là credential một lần. Chỉ hiển thị khi tạo/rotate, lưu verifier/hash phù hợp, consume atomically và không gửi lại qua support. Nếu người dùng mất bộ code, cần recovery flow xác minh danh tính theo policy.

Không ghi recovery code vào clipboard hoặc log mặc định. Hướng dẫn người dùng lưu ở password manager hoặc nơi an toàn phù hợp.

## 7. Passkey và biometric privacy

Passkey/WebAuthn cho phép server xác minh chữ ký từ authenticator. Server thường lưu credential ID, public key, sign counter/metadata phù hợp và trạng thái credential; không cần lưu fingerprint hoặc face template.

Biometric matching trên thiết bị được OS/authenticator quản lý. App không nên:
- Upload ảnh khuôn mặt hoặc vân tay để xác minh passkey.
- Lưu template sinh trắc học.
- Log kết quả sensor chi tiết.
- Dùng biometric template như account identifier.
- Chia sẻ biometric data với analytics vendor.

### 7.1. Những metadata passkey có thể nhạy cảm

Credential ID, authenticator type, AAGUID/attestation metadata, transports, backup eligibility/state và thời điểm đăng ký có thể tiết lộ loại thiết bị hoặc hệ sinh thái người dùng. Chỉ thu thập và giữ trường cần thiết cho security/compatibility.

Nếu không cần attestation để đáp ứng policy, cân nhắc không yêu cầu hoặc không lưu attestation data dư thừa. Attestation có thể tạo dấu vết thiết bị; cần đánh giá privacy và purpose trước khi dùng.

### 7.2. User verification không phải biometric disclosure

WebAuthn user verification flag cho biết authenticator đã thực hiện user verification theo cơ chế hỗ trợ. Nó không tiết lộ dấu vân tay, khuôn mặt hay PIN cụ thể. Server không cần biết phương thức cục bộ nào đã được dùng nếu policy chỉ yêu cầu UV.

Không suy luận danh tính sinh trắc học từ cờ UV.

## 8. Token và session privacy

Access token, refresh token, ID token và session cookie là dữ liệu bảo mật. Token có thể chứa personal claims hoặc metadata về user, client, tenant, scope, authentication context và thời hạn.

Nguyên tắc:
- Không log token thô hoặc Authorization header.
- Không đưa token vào URL query hoặc fragment nếu flow không yêu cầu.
- Không gửi token tới analytics, crash reporting hoặc support tool.
- Dùng audience và scope tối thiểu.
- Hạn chế claims cá nhân trong token.
- Dùng opaque identifier thay email nếu API không cần email.
- Đặt expiry và refresh policy phù hợp.
- Bảo vệ token tại rest và in transit.
- Thu hồi hoặc xử lý session khi có compromise.

### 8.1. Token claims và data minimization

Không đưa toàn bộ hồ sơ user vào access token chỉ vì tiện cho microservice. Claims thường cần thiết gồm subject, issuer, audience, expiry, scope và một số context theo profile. Các dữ liệu như địa chỉ nhà, ngày sinh, số điện thoại hoặc thông tin nhân sự không nên được thêm nếu resource server không cần.

JWT có thể được decode bởi bên sở hữu token nếu không được mã hóa. Chữ ký bảo vệ integrity, không che nội dung. Không đưa secret hoặc personal data không cần thiết vào JWT.

### 8.2. Session identifier

Session ID nên là giá trị ngẫu nhiên khó đoán, không mã hóa user ID hoặc email theo dạng có thể đọc. Server lưu mapping session-principal ở phía tin cậy. Khi session bị lộ, attacker có thể impersonate user, do đó cookie cần Secure/HttpOnly/SameSite và session lifecycle rõ.

Không ghi session ID đầy đủ vào log. Nếu cần correlation, dùng keyed hash hoặc reference không thể dùng như bearer credential.

## 9. Device recognition và fingerprinting

Hệ thống có thể dùng device recognition để phát hiện login bất thường hoặc giảm friction. Nhưng fingerprinting có thể tạo khả năng theo dõi người dùng qua thời gian và dịch vụ.

Các tín hiệu có thể gồm:
- Device model và OS version.
- App instance ID.
- Browser version và user-agent.
- IP/ASN.
- Cookie hoặc device-bound key.
- Locale/timezone.
- Sensor hoặc hardware characteristics.

Không phải tín hiệu nào cũng cần thu thập. Browser fingerprint có thể thay đổi, bị giả mạo và không phải identity proof. Không dùng fingerprint như một yếu tố xác thực duy nhất.

### 9.1. Ưu tiên device-bound credential

Nếu cần nhận biết thiết bị đã đăng ký, cân nhắc key pair hoặc credential do nền tảng bảo vệ thay vì thu thập nhiều thuộc tính fingerprint. Server có thể nhận proof-of-possession từ key đã đăng ký mà không cần tạo profile phần cứng chi tiết.

Device key cũng có lifecycle: enrollment, rotation, revoke và recovery. Public key không phải secret nhưng mapping tới user/device vẫn là dữ liệu cần kiểm soát.

### 9.2. IP và vị trí ước lượng

IP có thể hỗ trợ phát hiện abuse nhưng không phải vị trí chính xác hay bằng chứng danh tính. VPN, NAT, mobile carrier và corporate proxy có thể làm sai lệch suy luận. Tránh hiển thị cảnh báo “đăng nhập từ thành phố X” như một sự thật chắc chắn nếu dữ liệu chỉ là geolocation ước lượng.

Chỉ lưu IP đầy đủ khi có mục đích security hợp lệ và retention phù hợp. Có thể dùng prefix, keyed hash hoặc aggregate khi không cần địa chỉ đầy đủ. Cân nhắc rằng hashing IP không tự động biến nó thành dữ liệu không thể nhận diện.

## 10. Risk scoring và behavioral analytics

Risk engine có thể phân tích:
- Số lần thất bại.
- Tốc độ thử identifier.
- Device familiarity.
- IP/ASN reputation.
- Thời gian và pattern login.
- Thay đổi credential gần đây.
- Recovery event.
- Token/session anomaly.

Những tín hiệu này có thể cải thiện bảo mật nhưng cũng tạo hồ sơ hành vi. Policy cần xác định:
- Mục đích security cụ thể.
- Tín hiệu nào thực sự cần.
- Dữ liệu nào được lưu và trong bao lâu.
- Ai có thể xem risk score.
- Có dùng automated decision ảnh hưởng đáng kể tới người dùng không.
- Cách xử lý false positive và khiếu nại.
- Cách xóa hoặc giảm dữ liệu sau khi hết mục đích.

Không dùng risk score làm lý do duy nhất để đưa ra quyết định tác động lớn mà không có kiểm soát, giải thích và cơ chế review phù hợp.

### 10.1. Không tạo fingerprint không giới hạn

Kết hợp nhiều tín hiệu nhỏ có thể tạo fingerprint rất riêng. Không thêm canvas, font, sensor hoặc hardware signal chỉ vì có thể thu thập. Mỗi tín hiệu cần có purpose, necessity, retention và privacy review.

### 10.2. False positive và fairness

Người dùng đi du lịch, đổi thiết bị, dùng mạng di động hoặc công cụ hỗ trợ có thể bị đánh giá rủi ro cao. Hệ thống nên cung cấp phương thức step-up/recovery công bằng, tránh khóa account tự động chỉ vì một tín hiệu network/device.

Theo dõi tỷ lệ challenge/deny theo nhóm thiết bị, khu vực hoặc điều kiện mạng để phát hiện tác động bất cân xứng, đồng thời giới hạn việc suy luận thuộc tính nhạy cảm.

## 11. Error message và privacy

Error message là một phần của privacy boundary. Nó có thể tiết lộ account existence, credential state, MFA enrollment hoặc recovery contact.

Ví dụ thông báo an toàn hơn:
- Login: “Không thể đăng nhập bằng thông tin đã cung cấp.”
- Password reset: “Nếu thông tin phù hợp với một tài khoản, hướng dẫn sẽ được gửi qua kênh đã đăng ký.”
- MFA: “Không thể hoàn tất xác minh. Hãy thử lại hoặc dùng phương thức khôi phục được cung cấp.”
- Account recovery: “Yêu cầu đã được tiếp nhận. Chúng tôi sẽ hướng dẫn qua kênh phù hợp nếu có thể xác minh.”

Thông báo phải trung thực, không hứa gửi khi hệ thống không thực hiện. Nội dung ngoài không nên phân biệt account không tồn tại với account tồn tại nhưng bị từ chối.

### 11.1. Support channel

Support agent có thể cần thông tin để hỗ trợ login, nhưng không nên xem password, OTP, private key hoặc token. Quy trình support cần:
- Xác minh người yêu cầu qua kênh phù hợp.
- Không hỏi người dùng đọc OTP/password cho agent.
- Không gửi credential qua email/chat.
- Dùng công cụ reset/revoke có audit.
- Hạn chế dữ liệu account hiển thị theo role.
- Ghi nhận admin action và reason.
- Có quy trình xử lý yêu cầu khẩn cấp và escalation.

Không dùng câu hỏi bảo mật có câu trả lời dễ đoán hoặc dễ tìm trên mạng làm bằng chứng recovery.

## 12. Logging và telemetry privacy

Log rất cần để phát hiện credential stuffing, brute force, token misuse và account takeover. Nhưng log cũng là nơi dễ làm lộ credential và personal data.

### 12.1. Những gì không được log

Không log:
- Password hoặc password confirmation.
- OTP/TOTP code và seed.
- Recovery code.
- Session cookie.
- Authorization header hoặc bearer token thô.
- Refresh token và ID token thô.
- Client secret, HMAC secret, private key.
- Full WebAuthn assertion nếu chứa dữ liệu không cần thiết.
- QR enrollment secret.
- Raw biometric image/template.
- Full reset/activation link chứa token.
- Request body nhạy cảm không được redact.

### 12.2. Những gì có thể log có kiểm soát

Có thể ghi:
- Event type: login success/failure, MFA challenge, recovery requested.
- Timestamp.
- Principal reference đã pseudonymize.
- Client/service reference.
- Authentication method category.
- Result/reason code tổng quát.
- Correlation ID.
- Risk decision category.
- Source network signal đã giảm nhạy cảm.
- Token ID hoặc session reference không thể dùng làm credential.

Không ghi thêm identifier raw nếu correlation ID hoặc keyed reference đã đủ. Nếu cần email để support, lưu ở hệ thống có quyền riêng và retention rõ thay vì copy vào mọi log pipeline.

### 12.3. Redaction tại nguồn

Redact trước khi dữ liệu rời process hoặc trước khi middleware serialize. Redact ở dashboard cuối pipeline là quá muộn nếu raw event đã được gửi tới log vendor, queue hoặc archive.

Dùng allowlist field an toàn. Test log output bằng các giá trị canary giả lập password, OTP và token để xác nhận không có secret lọt qua.

## 13. Third-party SDK và data sharing

Login screen có thể chứa analytics SDK, crash reporting, advertising SDK, session replay hoặc customer support widget. Những thành phần này có thể quan sát input, URL, DOM, network metadata hoặc screen recording.

Rủi ro:
- SDK ghi password field hoặc OTP.
- Session replay chụp màn hình chứa email/phone.
- Crash report chứa token trong exception hoặc memory snapshot.
- Analytics nhận URL có reset token.
- Third-party script đọc CSRF token hoặc form value.
- Vendor nhận IP/device identifier ngoài mục đích cần thiết.
- SDK cập nhật thay đổi hành vi sau khi tích hợp.

Biện pháp:
- Không chạy session replay trên login, recovery hoặc MFA screen nếu không thể mask đáng tin cậy.
- Mask input nhạy cảm ở cả DOM và network capture.
- Tắt auto-capture cho authentication route.
- Không đưa credential vào event property.
- Hạn chế script bên thứ ba và dùng CSP/SRI khi phù hợp.
- Review vendor, subprocessor, retention và data transfer.
- Quản lý SDK version và quyền truy cập.
- Kiểm thử bằng network inspection và synthetic secrets.
- Dùng privacy notice/consent theo yêu cầu pháp lý và mục đích.

Không cho rằng SDK “chỉ thu analytics” nên không cần review. Bất kỳ code chạy trong login origin hoặc process đều có thể tiếp cận dữ liệu theo quyền của nó.

## 14. Retention, deletion và data lifecycle

Dữ liệu login nên có thời hạn lưu theo mục đích. Không giữ toàn bộ login event vô hạn chỉ vì storage rẻ.

Một ma trận retention cần chỉ rõ:
- Loại dữ liệu.
- Mục đích.
- Cơ sở lưu giữ.
- Retention period.
- Owner.
- Cách xóa/ẩn danh hóa.
- Backup/archive behavior.
- Legal hold hoặc incident exception nếu có.

| Dữ liệu | Mục đích có thể có | Cách quản lý |
| --- | --- | --- |
| Password verifier | Xác minh password | Giữ khi credential active; xóa/thay khi credential được đổi hoặc account bị xóa theo policy |
| Active session | Duy trì phiên | Expiry, revoke và cleanup |
| Access/refresh token | Truy cập API/lấy token mới | TTL, revoke, rotation và xóa theo lifecycle |
| Login audit event | Security investigation | Retention theo risk/legal policy, access giới hạn |
| IP/device signal | Abuse detection | Retention ngắn nhất đáp ứng mục đích; aggregate khi có thể |
| Recovery request | Xử lý account recovery | Xóa hoặc giảm định danh sau khi hoàn tất và hết thời gian cần thiết |
| Biometric template | OS quản lý local | Không lưu trong backend ứng dụng |
| Support ticket | Hỗ trợ người dùng | Retention theo support/legal purpose, redact secret |

### 14.1. Xóa không chỉ là DELETE một row

Dữ liệu có thể tồn tại trong:
- Primary database.
- Read replica.
- Search index.
- Data warehouse.
- Log aggregation.
- Queue/dead-letter queue.
- Backup.
- Crash report vendor.
- Support ticket.
- Analytics export.

Cần có deletion workflow và retention policy cho từng nơi. Với backup bất biến, có thể không xóa từng record ngay; cần bảo đảm dữ liệu không được phục hồi vào hệ thống hoạt động sau khi đã xử lý deletion và hết thời hạn backup.

### 14.2. Pseudonymization và anonymization

Pseudonymization thay identifier trực tiếp bằng mã/reference; vẫn có thể liên kết lại nếu giữ mapping hoặc key. Anonymization cần giảm khả năng nhận diện thực tế, không chỉ hash email.

Ví dụ, hash email không salt có thể bị dò từ danh sách email phổ biến. Keyed HMAC với key được bảo vệ có thể tạo reference ổn định cho correlation mà khó đảo ngược hơn, nhưng vẫn cần xem như pseudonymous data nếu tổ chức còn khả năng liên kết.

Aggregation cần ngưỡng đủ lớn để tránh lộ một cá nhân trong nhóm quá nhỏ. Không công bố metric “một nhân viên vừa login thất bại” theo dimension quá chi tiết.

## 15. Access control và separation of duties

Không phải mọi người vận hành đều cần xem mọi login data. Phân quyền theo nhiệm vụ:
- Authentication service đọc verifier cần thiết.
- Security operations xem event đã giảm nhạy cảm.
- Support xem trạng thái account ở mức tối thiểu.
- Data analyst chỉ nhận aggregate hoặc pseudonymous dataset.
- Platform admin quản lý hạ tầng nhưng không mặc định đọc secret.
- Privacy/legal team xử lý yêu cầu dữ liệu theo quy trình được phê duyệt.

Tách quyền:
- Quản trị policy.
- Truy cập secret.
- Truy cập log.
- Thay đổi account state.
- Export dữ liệu.
- Xem support ticket.

Admin action cần audit, reason và approval cho hành động có tác động lớn. Không cho support agent lấy OTP hoặc reset MFA mà không có quy trình xác minh độc lập.

### 15.1. Break-glass access

Quyền khẩn cấp có thể cần trong incident, nhưng phải:
- Có lý do và thời hạn.
- Được phê duyệt hoặc ghi nhận theo emergency process.
- Giới hạn phạm vi dữ liệu.
- Ghi audit bất biến phù hợp.
- Review sau sự kiện.
- Thu hồi ngay khi hết nhu cầu.

Không dùng break-glass như quyền truy cập thường xuyên.

## 16. Privacy trong account recovery

Recovery thường yêu cầu thêm dữ liệu để chứng minh người yêu cầu có quyền kiểm soát account. Đây là nơi dễ thu thập quá mức hoặc vô tình tiết lộ thông tin.

Nguyên tắc:
- Chỉ hỏi thông tin cần thiết cho proofing cụ thể.
- Không yêu cầu password cũ nếu đã có phương thức an toàn hơn và policy không cần.
- Không hỏi OTP qua support chat.
- Không tiết lộ email/phone recovery đầy đủ.
- Dùng masked destination khi hiển thị.
- Gửi thông báo qua kênh đã xác minh.
- Hạn chế lưu ảnh giấy tờ hoặc video nếu không cần.
- Nếu cần identity document, đặt retention, access và deletion policy riêng.
- Ghi audit về người thực hiện và quyết định.
- Cho phép người dùng biết cách khôi phục và khi nào dữ liệu bị xóa theo chính sách.

### 16.1. Recovery request enumeration

Response cho email không tồn tại và email có account nên tương tự. Có thể trả “Nếu có tài khoản phù hợp, hướng dẫn sẽ được gửi qua kênh đã đăng ký.” Không xác nhận email hoặc phone nào đang gắn với account.

### 16.2. Support-assisted recovery

Support không nên yêu cầu người dùng cung cấp secret. Dùng workflow xác minh độc lập, approval, delay hoặc notification theo risk. Ghi lại action nhưng tránh lưu bản sao giấy tờ hoặc credential trong ticket nếu hệ thống proofing chuyên dụng đã quản lý.

## 17. Privacy trong SSO và federation

SSO có thể chia sẻ identity attributes giữa identity provider (IdP), relying party (RP) và service provider. Cần giới hạn attribute release theo nhu cầu của ứng dụng.

Ví dụ:
- Ứng dụng chỉ cần subject identifier ổn định, không cần email.
- Partner cần biết user thuộc tổ chức, không cần toàn bộ profile.
- API cần role/scope, không cần ngày sinh hoặc địa chỉ.
- Pairwise pseudonymous identifier có thể giảm khả năng liên kết người dùng giữa nhiều RP.

### 17.1. Pairwise subject

Một IdP có thể phát subject identifier khác nhau cho từng relying party hoặc sector. Điều này hạn chế các dịch vụ liên kết hoạt động của cùng một người bằng một identifier toàn cục.

Nếu ứng dụng cần account linking, phải có quy trình rõ ràng và không tự động liên kết chỉ vì email giống nhau. Email có thể thay đổi hoặc được tái cấp; liên kết cần proof và consent phù hợp.

### 17.2. Attribute minimization

Chỉ yêu cầu claim/attribute cần cho chức năng:
- subject.
- tenant/organization membership nếu cần.
- email verified nếu cần gửi thông báo.
- role/scope nếu authorization cần.
- authentication context nếu policy cần.

Không yêu cầu profile đầy đủ từ IdP chỉ vì metadata hỗ trợ.

## 18. Privacy trong device binding và certificate authentication

Device-bound key, client certificate và workload identity giúp xác thực mà không cần password, nhưng metadata vẫn có thể liên kết với người hoặc thiết bị.

Cần:
- Lưu public key/certificate reference thay private key.
- Không thu thập hardware serial nếu không cần.
- Giới hạn certificate subject/SAN metadata trong log.
- Có rotation và revoke.
- Xóa device association khi account unlink/retire theo policy.
- Không dùng device identifier để theo dõi ngoài mục đích security.
- Kiểm soát attestation metadata và vendor-specific identifier.

Certificate serial hoặc public key fingerprint có thể được dùng làm correlation ID, nhưng mapping tới user/device vẫn cần quyền truy cập và retention.

## 19. Error handling và privacy by design

Error response cần cân bằng giữa usability và privacy. Người dùng cần biết cách tiếp tục; attacker không cần biết chi tiết account hoặc policy.

| Tình huống | Thông báo bên ngoài có thể dùng | Thông tin nội bộ |
| --- | --- | --- |
| Identifier không tồn tại/password sai | Không thể đăng nhập bằng thông tin đã cung cấp | Unknown principal / password mismatch |
| Recovery request | Nếu có tài khoản phù hợp, hướng dẫn sẽ được gửi | Account lookup và delivery status |
| MFA thất bại | Không thể hoàn tất xác minh | Factor failure reason |
| Account bị risk hold | Không thể hoàn tất đăng nhập ngay lúc này | Risk rule và investigation reference |
| Token invalid | Yêu cầu xác thực lại | Signature/issuer/audience/expiry reason |
| Session hết hạn | Phiên đã hết hạn, vui lòng đăng nhập lại | Session expiry event |

Không trả stack trace, database key, user status, factor enrollment hoặc chi tiết risk score. Internal reason code cần đủ để điều tra nhưng không đưa ra client.

### 19.1. Error timing

Nếu account tồn tại và password sai thì server có thể chạy password hash; account không tồn tại có thể dùng fake hash để giảm timing oracle. Rate limit trước bước tốn CPU để chống DoS. Không tạo phản hồi khác nhau về kích thước hoặc header một cách không cần thiết.

### 19.2. Accessibility và privacy

Challenge bảo mật cần có phương án tiếp cận cho người dùng khuyết tật. Không ép dùng camera hoặc biometric nếu có phương thức khác phù hợp. Tránh thu thập thêm dữ liệu sức khỏe hoặc thiết bị hỗ trợ chỉ để hoàn thành login nếu không cần thiết.

## 20. Threat model cho privacy của login

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Credential leakage** | Password/OTP/token lọt vào log hoặc analytics | Redaction tại nguồn, allowlist logging và synthetic-secret tests |
| **Account enumeration** | Response hoặc timing tiết lộ account existence | Generic response, fake verifier, rate limit |
| **Excessive collection** | Thu thập device/location/behavior không cần | Data inventory, minimization và purpose review |
| **Session replay** | Session cookie/access token bị lộ | Secure storage, TLS, expiry, revoke và sender constraint |
| **Biometric privacy breach** | SDK upload ảnh/template | OS-managed biometric, no-template policy và SDK review |
| **Third-party tracking** | Analytics/session replay quan sát login screen | Disable auto-capture, masking, CSP và vendor review |
| **Support misuse** | Agent xem secret hoặc reset factor trái phép | Separation of duties, verified workflow và audit |
| **Long retention** | Login event/IP/device data lưu vô thời hạn | Retention schedule, deletion automation và review |
| **Cross-service correlation** | Identifier toàn cục liên kết hoạt động nhiều dịch vụ | Pairwise subject, pseudonymization và minimization |
| **Risk profiling** | Device/behavior signals tạo hồ sơ rộng | Purpose, transparency, fairness và limited retention |
| **Recovery disclosure** | Response lộ email/phone hoặc account status | Masking và generic response |
| **Backup persistence** | Dữ liệu đã xóa còn trong archive/warehouse | End-to-end deletion workflow và backup expiry |
| **Insider access** | Người nội bộ xem login data không cần thiết | RBAC, audit, approval và break-glass controls |
| **Token claim overexposure** | JWT chứa profile cá nhân dư thừa | Claim minimization và audience-specific token |
| **URL leakage** | Reset/activation token nằm trong query hoặc Referer | One-time token handling, no third-party content và redaction |

## 21. Ví dụ: thiết kế privacy cho login của ứng dụng tài chính

Một ứng dụng tài chính cần xác thực người dùng, hỗ trợ passkey/MFA và phát hiện credential stuffing.

Thiết kế:
1. Login chỉ thu identifier và credential cần cho flow; không yêu cầu ngày sinh hoặc địa chỉ.
2. TLS bảo vệ request.
3. Password được xác minh bằng password hash; request body bị loại khỏi log.
4. Response lỗi dùng thông báo chung để giảm account enumeration.
5. Risk engine nhận account reference đã keyed, source signal và event type cần thiết.
6. IP/device data có retention ngắn và purpose chống abuse được ghi rõ.
7. MFA event ghi factor type và result, không ghi OTP hoặc seed.
8. Passkey server lưu credential ID/public key/metadata cần thiết; biometric template do OS quản lý.
9. Access token chỉ chứa subject, audience, expiry, scope và authentication context cần thiết.
10. Session cookie được bảo vệ và không ghi vào log.
11. Analytics không chạy auto-capture trên login, MFA hoặc recovery screen.
12. Support chỉ xem masked contact và trạng thái recovery; không xem secret.
13. Login audit được giữ theo retention security/legal policy và quyền đọc giới hạn.
14. Account deletion/recovery có workflow xử lý session, token, device key, log và backup theo policy.

~~~mermaid
flowchart TD
    A[Login request] --> B[TLS + input validation]
    B --> C[Authentication service]
    C --> D[Verify credential without logging secret]
    D --> E{Valid?}
    E -- No --> F[Generic response + privacy-safe event]
    E -- Yes --> G[Risk / MFA policy]
    G --> H[Issue minimal token/session]
    H --> I[API access]
    F --> J[Limited-retention security telemetry]
    I --> J
    K[Privacy controls] --> C
    K --> J
    K --> L[Retention / deletion / access review]
~~~

Không phải mọi event đều cần cùng retention. Fraud investigation có thể cần dữ liệu chi tiết trong thời hạn ngắn; dashboard vận hành có thể dùng aggregate. Phân tách các dataset giúp giảm quyền truy cập và giảm rủi ro.

## 22. Kiểm thử privacy của login

| Test case | Kết quả mong đợi |
| --- | --- |
| Password sai | Không xuất hiện trong log, trace hoặc response |
| OTP/TOTP sai | Giá trị code không được log |
| Recovery code dùng | Chỉ ghi event/reference, không ghi code |
| Token hợp lệ | Không có bearer token thô trong log |
| Session cookie | Không xuất hiện trong telemetry hoặc error report |
| Unknown account vs wrong password | Response bên ngoài tương đương |
| Timing account enumeration | Khác biệt không tạo oracle dễ khai thác |
| Password reset unknown email | Không xác nhận account existence |
| MFA enrollment | QR/seed không vào analytics hoặc crash report |
| Passkey enrollment | Không thu thập biometric template |
| Device fingerprinting | Chỉ thu tín hiệu có purpose và retention |
| IP retention | Có TTL và access control |
| Third-party session replay | Login/recovery input được mask hoặc capture disabled |
| URL inspection | Không có reset token, OTP hoặc secret trong URL |
| Error page | Không lộ stack trace, database ID hoặc factor details |
| Support access | Agent không xem password/OTP/private key |
| Admin reset MFA | Có verification, approval/audit và notification |
| JWT inspection | Không chứa personal claim dư thừa |
| Data export | Chỉ xuất dữ liệu phù hợp quyền và mục đích |
| Account deletion | Có quy trình cho DB, index, analytics, logs và backup |
| Backup restore | Dữ liệu đã hết retention không quay lại hệ thống hoạt động |
| Log access review | Chỉ role cần thiết được đọc |
| Synthetic secret test | Canary password/token không xuất hiện ở pipeline |
| Aggregate metric | Nhóm nhỏ không làm lộ một cá nhân |
| Third-party SDK update | Không bật lại auto-capture hoặc gửi input nhạy cảm |

### 22.1. Privacy test trong CI/CD

Có thể dùng giá trị canary giả lập như TEST_PASSWORD_DO_NOT_LOG hoặc TEST_TOKEN_DO_NOT_LOG trong test environment. Gửi request qua login, MFA, recovery và exception path; sau đó quét output log, trace, event, crash report và network payload để xác nhận canary không xuất hiện.

Không dùng credential thật hoặc dữ liệu cá nhân thật trong test. Test data cần được tạo tổng hợp và xóa theo pipeline.

## 23. Checklist review

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Có data inventory cho login? | Mỗi field có nguồn, purpose, recipient và retention |
| Có minimization? | Chỉ thu dữ liệu cần cho authentication/security |
| Identifier có được bảo vệ? | Mask/pseudonymize ở nơi không cần raw value |
| Error có chống enumeration? | Generic response và timing review |
| Password/OTP có bị log? | Redaction tại nguồn và synthetic tests |
| Token/session có được bảo vệ? | Không URL/log, expiry và revoke |
| Biometric privacy được bảo đảm? | OS matching, không upload template |
| Device fingerprint có purpose? | Tín hiệu tối thiểu và retention giới hạn |
| Risk scoring có governance? | Owner, transparency, false-positive review |
| Third-party SDK được review? | Masking, no auto-capture và vendor controls |
| Recovery có minimization? | Không lộ contact, không hỏi secret qua support |
| Retention có rõ? | TTL, owner, deletion và backup policy |
| Access control có phân tách? | Support, analyst, admin và security có quyền riêng |
| Audit có hữu ích? | Actor, action, result và correlation không có secret |
| SSO có attribute minimization? | Pairwise subject và claim cần thiết |
| JWT claims có tối thiểu? | Không đưa profile dư thừa vào token |
| Có deletion end-to-end? | DB, index, logs, warehouse, vendor và backup |
| Có privacy regression tests? | Canary secret, enumeration, URL và SDK capture |

### Tình huống tự kiểm tra

**Tình huống 1:** Login API ghi toàn bộ request body để debug. Có an toàn nếu log chỉ được lưu nội bộ?

**Trả lời:** Không. Log nội bộ vẫn có thể bị truy cập, sao chép hoặc lưu lâu. Password, OTP và token phải được loại khỏi log ngay tại nguồn.

**Tình huống 2:** Hệ thống hash email trong log. Có thể coi dữ liệu đó hoàn toàn anonymous không?

**Trả lời:** Không. Email có entropy thấp và có thể bị dò; hash ổn định vẫn có thể liên kết hoạt động. Cân nhắc keyed HMAC, access control và retention.

**Tình huống 3:** Passkey sử dụng Face ID. Server có cần lưu ảnh khuôn mặt không?

**Trả lời:** Không. Authenticator/OS xử lý biometric cục bộ. Server xác minh assertion và lưu public key/credential metadata cần thiết.

**Tình huống 4:** Login response không tiết lộ account existence nhưng thời gian phản hồi khác rõ rệt. Đã chống enumeration chưa?

**Trả lời:** Chưa đầy đủ. Cần đánh giá timing side channel và có thể dùng fake verifier hoặc response path tương đương.

**Tình huống 5:** Analytics SDK không thu password field theo cấu hình hiện tại. Có cần review sau khi SDK update không?

**Trả lời:** Có. SDK có thể thay đổi auto-capture, network collection hoặc crash behavior. Cần version governance và regression tests.

**Tình huống 6:** Một IP được lưu trong log security. Hash IP có tự động loại bỏ privacy risk không?

**Trả lời:** Không. Hash có thể ổn định và liên kết hoạt động; cần đánh giá khả năng tái nhận diện, purpose và retention.

**Tình huống 7:** Người dùng xóa account. Chỉ xóa row trong database chính có đủ không?

**Trả lời:** Không. Cần xét replica, search index, warehouse, log, vendor, support ticket và backup theo deletion/retention policy.

**Tình huống 8:** Support agent cần giúp người dùng khôi phục MFA. Có nên yêu cầu người dùng đọc OTP qua điện thoại không?

**Trả lời:** Không. Dùng recovery workflow đã xác minh, công cụ reset có audit và thông báo qua kênh đáng tin; support không cần biết OTP.

## 24. Ghi nhớ

**Privacy của login là bảo vệ dữ liệu phát sinh khi xác minh danh tính, từ lúc người dùng nhập credential đến khi session hết hạn hoặc account được khôi phục/xóa.** Hệ thống cần data inventory, minimization, purpose limitation, response normalization và retention rõ ràng. Password, OTP, recovery code, private key, token và session cookie không được đưa vào log, URL hoặc analytics.

Passkey/biometric nên để OS quản lý template; server chỉ lưu public key và metadata cần thiết. Device fingerprint, IP và risk telemetry cần mục đích cụ thể, giới hạn truy cập và thời hạn. Third-party SDK, support tooling, backup và data warehouse đều nằm trong data flow cần review. Audit nên ghi actor, action, result và correlation reference mà không lưu secret. Kiểm thử privacy bằng synthetic data, canary secret và review toàn bộ pipeline để tránh dữ liệu xác thực rò rỉ ngoài ý muốn.
