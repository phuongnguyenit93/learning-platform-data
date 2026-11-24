# Recovery abuse: nhận diện và ngăn chiếm đoạt tài khoản qua khôi phục

> **Chương:** Account recovery  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này phân tích cách attacker lạm dụng quy trình recovery để chiếm tài khoản, vượt MFA, thay authenticator hoặc duy trì quyền truy cập; đồng thời trình bày cách thiết kế recovery có assurance phù hợp, thông báo, trì hoãn thay đổi nhạy cảm và thu hồi credential bị ảnh hưởng.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao account recovery là một đường xác thực có rủi ro cao và có thể trở thành điểm yếu nhất của hệ thống.
2. Nhận diện các kiểu recovery abuse: email takeover, SIM swap, helpdesk social engineering, account enumeration, recovery code theft và MFA reset abuse.
3. Phân biệt recovery, authentication, re-authentication, identity proofing và authenticator enrollment.
4. Thiết kế recovery policy dựa trên assurance, loại tài khoản, tài sản cần bảo vệ và bằng chứng độc lập.
5. Bảo vệ recovery token/code bằng entropy, hashing, expiry, one-time use và chống replay.
6. Áp dụng rate limit, delay, notification, review và risk signal để giảm takeover.
7. Thu hồi session, refresh token, authenticator và quyền downstream sau recovery hoặc khi nghi compromise.
8. Xây dựng quy trình helpdesk/admin recovery có phân tách nhiệm vụ và audit.
9. Triển khai recovery flow trong Java/Spring và xây dựng ma trận kiểm thử abuse.

## 2. Account recovery là gì?

**Account recovery** là quy trình khôi phục quyền truy cập khi người dùng mất, hỏng hoặc không còn kiểm soát phương thức xác thực đã đăng ký. Ví dụ: quên mật khẩu, mất điện thoại chứa TOTP, mất passkey, mất security key hoặc không còn truy cập được email/điện thoại recovery.

Recovery có thể cho phép người dùng:

- Đặt lại mật khẩu.
- Đăng ký authenticator mới.
- Xóa hoặc thay thế authenticator bị mất.
- Khôi phục phiên đăng nhập.
- Cập nhật email/điện thoại khôi phục.
- Mở khóa tài khoản.
- Khôi phục quyền quản trị hoặc tài khoản tổ chức.

Đây là thao tác thay đổi gốc tin cậy của tài khoản. Nếu recovery yếu, attacker không cần phá passkey hoặc MFA; họ chỉ cần lạm dụng đường khôi phục để thay authenticator của nạn nhân bằng phương thức do mình kiểm soát.

Recovery không đồng nghĩa với việc người dùng chứng minh được danh tính ở mức cao nhất. Hệ thống phải xác định recovery flow đang chứng minh điều gì, bằng chứng nào được chấp nhận và quyền nào được mở lại sau khi hoàn tất.

## 3. Vì sao recovery trở thành mục tiêu tấn công?

Đăng nhập thường yêu cầu một authenticator đã được đăng ký và kiểm tra proof theo giao thức. Recovery phải hoạt động ngay cả khi user không còn authenticator đó. Vì vậy, hệ thống thường tạo ra đường thay thế qua email, SMS, câu hỏi bảo mật, helpdesk hoặc giấy tờ.

Những đường thay thế này có thể yếu hơn:

- Email recovery có thể bị chiếm độc lập với tài khoản chính.
- SMS có thể bị SIM swap, chuyển tiếp hoặc social engineering nhà mạng.
- Câu hỏi bảo mật thường có đáp án đoán được hoặc tìm được trên mạng.
- Helpdesk có thể bị thao túng bằng thông tin cá nhân công khai hoặc hồ sơ giả.
- Recovery code có thể bị chụp, lưu trong cloud hoặc gửi qua chat.
- Một phiên yếu có thể được dùng để thay đổi kênh recovery rồi chiếm tài khoản lâu dài.

Recovery abuse xảy ra khi attacker khai thác quy trình hoặc bằng chứng khôi phục để giành quyền truy cập trái phép, làm suy yếu MFA hoặc thay đổi thông tin kiểm soát tài khoản.

## 4. Threat model và trust boundary

Recovery thường đi qua nhiều bên: user, browser/mobile app, recovery service, email/SMS provider, helpdesk, identity provider và các ứng dụng phụ thuộc. Mỗi bên tạo thêm một ranh giới tin cậy.

~~~mermaid
flowchart TD
    U["Account owner"] --> C["Browser / mobile client"]
    C --> R["Recovery service"]
    R --> P["Recovery policy and evidence verifier"]
    P --> E["Email / SMS / recovery code"]
    P --> H["Helpdesk / identity proofing"]
    P --> I["Identity and authenticator store"]
    I --> S["Session and token revocation"]
    I --> N["Security notification"]
    S --> A["Relying apps and APIs"]
    X["Attacker: phishing, SIM swap,<br/>social engineering, automation"] -.-> E
    X -.-> H
    X -.-> C
~~~

Các câu hỏi cần trả lời:

1. Ai có quyền bắt đầu recovery và cho account nào?
2. Bằng chứng nào chứng minh người yêu cầu kiểm soát tài khoản?
3. Bằng chứng đó độc lập với credential đang bị mất hay không?
4. Ai có quyền phê duyệt reset MFA hoặc thay đổi recovery channel?
5. Recovery token được ràng buộc với account, purpose, session và thời hạn thế nào?
6. Sau recovery, session/token/authenticator cũ được xử lý ra sao?
7. User được thông báo qua kênh nào và có thể phản đối giao dịch không?
8. Nếu recovery provider hoặc helpdesk bị compromise, phạm vi ảnh hưởng là gì?

## 5. Phân biệt recovery với các hoạt động khác

| Hoạt động | Mục đích | Điều kiện chính |
|---|---|---|
| Authentication | Chứng minh đang kiểm soát authenticator đã đăng ký | Proof hợp lệ từ credential |
| Re-authentication | Xác minh lại gần thời điểm thao tác | Authenticator hiện có và freshness policy |
| Account recovery | Khôi phục quyền truy cập khi mất phương thức | Recovery evidence theo assurance policy |
| Identity proofing | Xác minh danh tính ngoài đời hoặc thuộc tính định danh | Bằng chứng và quy trình proofing được xác định |
| Authenticator enrollment | Liên kết authenticator mới với account | Session đủ tin cậy và proof đăng ký |
| Password reset | Thay password hiện tại | Recovery grant/token có purpose phù hợp |
| MFA reset | Xóa/thay authenticator MFA | Assurance cao hơn hoặc review bổ sung |

Một email link có thể cho phép đặt lại mật khẩu theo policy, nhưng không tự động đủ để xóa mọi passkey hoặc khôi phục quyền admin. Mỗi hành động cần baseline assurance riêng.

## 6. Các kiểu recovery abuse thường gặp

### 6.1. Email account takeover

Attacker chiếm hộp thư recovery bằng phishing, password reuse, malware hoặc recovery yếu của chính nhà cung cấp email. Sau đó attacker yêu cầu reset password và lấy link recovery.

Kiểm soát:

- Không coi email là bằng chứng duy nhất cho recovery nhạy cảm.
- Bảo vệ email recovery bằng MFA/passkey và thông báo thay đổi.
- Gửi thông báo tới kênh cũ khi email recovery thay đổi.
- Không cho phép thay email recovery rồi reset MFA ngay trong cùng một phiên yếu.
- Dùng delay/review cho thay đổi có tác động lớn.

### 6.2. SIM swap và SMS interception

Attacker thuyết phục nhà mạng chuyển số điện thoại sang SIM/eSIM do attacker kiểm soát, hoặc lợi dụng chuyển tiếp/đánh cắp mã. SMS recovery khi đó có thể đến tay attacker.

Kiểm soát:

- Không dùng SMS làm phương thức duy nhất cho tài khoản nhạy cảm hoặc admin.
- Dùng passkey/security key hoặc phương thức mạnh hơn làm recovery path khi có thể.
- Theo dõi thay đổi số điện thoại/SIM signal nếu có nguồn hợp pháp và đáng tin, nhưng coi đây là risk signal.
- Thông báo qua kênh đã đăng ký trước đó khi số điện thoại thay đổi.
- Có thời gian chờ trước khi số mới được dùng cho recovery nhạy cảm.

### 6.3. Helpdesk social engineering

Attacker gọi hỗ trợ, giả làm nhân viên hoặc chủ tài khoản, viện lý do mất thiết bị, đi công tác hoặc khẩn cấp để yêu cầu reset MFA.

Kiểm soát:

- Không dựa vào thông tin cá nhân công khai làm bằng chứng.
- Có quy trình xác minh nhiều bước, dựa trên hồ sơ và bằng chứng độc lập.
- Tách người tiếp nhận yêu cầu khỏi người phê duyệt reset đặc quyền.
- Ghi âm/ghi log theo chính sách và bảo vệ dữ liệu.
- Không cho nhân viên hỗ trợ tự bỏ qua control vì áp lực thời gian.
- Có callback tới số/kênh đã đăng ký trước, không dùng số attacker vừa cung cấp làm bằng chứng.
- Giới hạn quyền helpdesk theo vai trò và phạm vi account.

### 6.4. Account enumeration

Attacker thử nhiều email/username để tìm account tồn tại, có recovery channel nào hoặc có MFA nào được đăng ký.

Kiểm soát:

- Response công khai đồng nhất về nội dung và cấu trúc.
- Tránh khác biệt thời gian xử lý dễ suy ra account tồn tại.
- Rate limit theo nhiều chiều, không chỉ IP.
- Không hiển thị đầy đủ email/phone recovery; chỉ che một phần theo policy.
- Không tiết lộ số lượng authenticator hoặc loại factor đã đăng ký cho người chưa xác thực.

### 6.5. Recovery code theft

Recovery code bị chụp màn hình, lưu trong cloud drive, gửi qua chat hoặc lấy từ thiết bị đã bị xâm nhập.

Kiểm soát:

- Mỗi code dùng một lần và có entropy cao.
- Chỉ lưu verifier/hash; không lưu plaintext để xem lại.
- Hiển thị bộ code một lần, yêu cầu user lưu an toàn.
- Khi tạo bộ mới, vô hiệu toàn bộ code cũ.
- Thông báo khi code được sử dụng hoặc bộ code được tái tạo.

### 6.6. MFA reset abuse

Attacker dùng một recovery flow yếu để xóa authenticator mạnh của nạn nhân rồi đăng ký authenticator của attacker.

Kiểm soát:

- MFA reset có assurance cao hơn password reset.
- Yêu cầu bằng chứng độc lập hoặc review cho trường hợp mất toàn bộ factor.
- Gửi cảnh báo tới kênh cũ.
- Thu hồi session/token hiện có và áp dụng delay cho thay đổi nhạy cảm.
- Không để recovery grant dùng được cho cả password reset, MFA reset và email change.

## 7. Recovery evidence và assurance

Không có một phương thức recovery phù hợp cho mọi tài khoản. Policy cần xét mức độ nhạy cảm, giá trị tài sản, khả năng mất mát và hậu quả khi cấp nhầm quyền.

| Bằng chứng | Giá trị và giới hạn |
|---|---|
| Passkey/security key còn kiểm soát | Bằng chứng mạnh nếu assertion hợp lệ và credential chưa bị compromise |
| Recovery code chưa dùng | Có thể dùng theo policy; là bearer secret cần chống replay |
| Email link | Chứng minh kiểm soát mailbox ở thời điểm đó, không chứng minh chắc chắn danh tính |
| SMS OTP | Có thể hỗ trợ recovery rủi ro thấp; chịu SIM swap/interception |
| Helpdesk knowledge questions | Yếu nếu dựa vào dữ liệu công khai hoặc dễ đoán |
| Identity document/proofing | Có thể hỗ trợ proofing theo quy trình; cần chống giả mạo và bảo vệ PII |
| Manager approval | Là một yếu tố quy trình, không tự động là bằng chứng danh tính |
| Device/session context | Tín hiệu hỗ trợ; không thay proof-of-possession |

Không cộng nhiều yếu tố yếu có cùng nguồn compromise rồi gọi đó là assurance mạnh. Ví dụ email và SMS có thể cùng bị kiểm soát qua một cuộc social engineering; hai kênh không nhất thiết độc lập.

### Recovery assurance phải theo hành động

- Reset password: có thể dùng recovery proof theo risk tier.
- Thêm passkey mới: cần ràng buộc enrollment với account/session và step-up phù hợp.
- Xóa toàn bộ MFA: cần assurance cao, review hoặc proofing bổ sung.
- Khôi phục tài khoản admin: yêu cầu quy trình đặc biệt, phê duyệt độc lập và audit.
- Thay đổi email/phone recovery: cần bảo vệ kênh cũ và delay trước khi kênh mới có hiệu lực cho recovery nhạy cảm.

## 8. Recovery token an toàn

Recovery link thường mang token bearer. Ai có token còn hiệu lực có thể thử hoàn tất hành động recovery tương ứng.

Token cần:

- Được sinh bằng CSPRNG với entropy đủ lớn.
- Gắn với account cụ thể và purpose cụ thể.
- Có thời hạn ngắn phù hợp với rủi ro.
- Dùng một lần và được tiêu thụ nguyên tử.
- Không chứa PII hoặc thông tin quyền hạn có thể đọc trực tiếp.
- Chỉ lưu hash/verifier phía server nếu có thể.
- Không được ghi vào log, analytics, referrer hoặc ticket.
- Bị vô hiệu khi password/recovery state thay đổi hoặc khi có token mới thay thế theo policy.

~~~text
Recovery grant:
  account_id = A-104
  purpose = PASSWORD_RESET
  token_hash = SHA256(random_token)
  created_at = server_timestamp
  expires_at = short_deadline
  consumed_at = null
  state_version = 12
~~~

Token cho PASSWORD_RESET không được dùng để REMOVE_ALL_AUTHENTICATORS. Purpose binding giúp ngăn một bằng chứng recovery bị dùng cho hành động mạnh hơn.

### Hash token

Recovery token thường có entropy ngẫu nhiên cao; lưu hash an toàn giúp giảm tác động khi database bị đọc. Khi user gửi token, server hash token nhận được và so khớp với verifier đang lưu.

Không dùng hash yếu hoặc token entropy thấp. Nếu token là mã ngắn có thể đoán, cần dùng password-hashing/KDF hoặc cơ chế rate limit phù hợp; tốt hơn là thiết kế token có entropy cao để không thể brute force thực tế.

## 9. Recovery flow và one-time consumption

Một flow khôi phục có thể gồm:

1. User yêu cầu recovery.
2. Server trả response không tiết lộ account tồn tại hay không.
3. Server đánh giá rate limit, trạng thái account và recovery policy.
4. Server tạo grant riêng cho purpose và account, lưu hash và expiry.
5. Gửi thông báo qua kênh đã xác minh theo policy.
6. User mở link hoặc cung cấp code.
7. Server kiểm tra hash, expiry, purpose, account state và risk constraints.
8. User thực hiện hành động được phép.
9. Server tiêu thụ grant atomically và cập nhật credential/account state.
10. Server thu hồi session/token phù hợp, gửi thông báo và ghi audit.

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant App as Recovery UI
    participant R as Recovery service
    participant Store as Recovery store
    participant Notify as Verified channel

    User->>App: Request recovery
    App->>R: Submit identifier
    R->>R: Apply generic response and rate limits
    R->>Store: Create purpose-bound one-time grant
    R->>Notify: Send recovery link/code if policy allows
    Notify-->>User: Recovery instruction
    User->>App: Present token and complete proof
    App->>R: Submit recovery token + new credential
    R->>Store: Lock and validate pending grant
    R->>R: Verify purpose, expiry, account and risk policy
    R->>Store: Consume grant and update account
    R->>Store: Revoke sessions/tokens as required
    R-->>App: Recovery result
    R->>Notify: Send completion/security alert
~~~

One-time consumption phải được thực hiện bằng transaction hoặc conditional update. Nếu hai request đồng thời cùng gửi token, chỉ một request được phép hoàn tất.

## 10. Password reset không tự động reset MFA

Một lỗi thiết kế phổ biến là gom mọi thao tác recovery vào một flow chung. Password reset, thay email, reset MFA và khôi phục admin có mức tác động khác nhau.

Policy nên phân biệt:

| Hành động | Rủi ro | Kiểm soát bổ sung |
|---|---|---|
| Đặt lại password | Attacker có thể chiếm đăng nhập password | Token purpose-bound, rate limit, revoke phiên theo policy |
| Thay email recovery | Attacker kiểm soát kênh recovery tương lai | Xác minh kênh mới và thông báo kênh cũ; delay |
| Reset TOTP | Bỏ một factor khỏi tài khoản | Assurance cao hơn, revoke seed cũ, thông báo |
| Xóa toàn bộ passkey/security key | Mất lớp chống phishing | Proof/review mạnh, không chỉ email link |
| Khôi phục admin | Có thể chiếm control plane | Dual control, identity proofing và break-glass policy |

Một grant được cấp cho password reset không được nâng quyền bằng cách gửi thêm field action=RESET_MFA trong request body. Server phải lấy purpose từ record đã lưu và kiểm tra policy riêng.

## 11. Recovery delay và cooling-off period

**Recovery delay** là khoảng thời gian chờ trước khi một thay đổi nhạy cảm có hiệu lực. Nó tạo cơ hội để chủ tài khoản nhận cảnh báo và phản đối khi không yêu cầu recovery.

Có thể áp dụng delay cho:

- Thay email/phone recovery.
- Xóa toàn bộ authenticator.
- Đăng ký authenticator mới sau recovery yếu.
- Khôi phục tài khoản admin.
- Tăng quyền sau khi thay đổi credential.

Delay không phải bằng chứng xác thực và không thay thế step-up. Nó là một biện pháp containment để giảm lợi ích tức thời của attacker.

Policy cần xác định:

- Thời gian delay theo mức rủi ro và loại tài khoản.
- Sự kiện nào được phép hủy hoặc đóng băng yêu cầu.
- Kênh thông báo cũ và mới.
- Những action nào bị hạn chế trong thời gian chờ.
- Cách xử lý khi user mất luôn kênh thông báo cũ.
- Cách xử lý trường hợp khẩn cấp có review độc lập.

Không dùng delay dài một cách máy móc cho mọi user; nó có thể khóa người dùng hợp lệ khỏi tài khoản. Cần recovery route thay thế có kiểm soát và đánh giá theo tác động.

## 12. Notification và cơ chế phản đối recovery

Thông báo cần được gửi khi:

- Có yêu cầu recovery.
- Recovery token được sử dụng.
- Password được reset.
- MFA/passkey bị xóa hoặc thêm.
- Email/phone recovery thay đổi.
- Recovery bị hủy hoặc bị chặn do nghi ngờ abuse.

Thông báo nên:

- Gửi tới kênh đã xác minh trước đó khi có thể.
- Không chứa recovery token, OTP hoặc secret.
- Nêu hành động, thời gian và cách liên hệ qua kênh chính thức.
- Có cách báo cáo “Tôi không thực hiện yêu cầu này”.
- Không chứa link có thể trực tiếp reset MFA nếu user chỉ cần báo cáo.

Nếu user báo yêu cầu không phải của họ, hệ thống cần có quy trình containment: tạm giữ thay đổi, revoke recovery grant, thu hồi session nghi ngờ, yêu cầu xác thực lại và chuyển review nếu cần.

Thông báo tới kênh mới vừa được thêm không đủ; attacker có thể đã chiếm chính kênh đó. Kênh cũ là nguồn cảnh báo quan trọng, nhưng cũng cần xem xét trường hợp kênh cũ đã mất kiểm soát.

## 13. Rate limiting và anti-automation

Recovery endpoint thường dễ bị abuse ở quy mô lớn:

- Thử nhiều username/email để enumerate account.
- Gửi lượng lớn email/SMS để gây chi phí hoặc làm phiền.
- Brute force mã OTP/recovery code.
- Tạo nhiều recovery grant cho cùng account.
- Tấn công phân tán qua nhiều IP.
- Dùng bot để thử token hoặc gây khóa tài khoản.

Kiểm soát:

- Rate limit theo account identifier đã chuẩn hóa, IP/network, device/session và toàn hệ thống.
- Giới hạn số recovery grant active cho một account.
- Cooldown giữa các yêu cầu gửi email/SMS.
- Giới hạn số lần thử token/code và áp dụng backoff.
- Response công khai đồng nhất để giảm enumeration.
- Giám sát phân tán và phát hiện pattern theo nhiều account.
- Chống SMS/email bombing bằng quota và abuse detection.
- Không khóa account vĩnh viễn chỉ vì attacker cố tình gửi nhiều request recovery.

Rate limit theo IP đơn lẻ không đủ vì attacker có thể dùng botnet; ngược lại, rate limit chỉ theo account có thể bị lợi dụng để khóa nạn nhân. Cần kết hợp nhiều chiều và có cơ chế mở khóa an toàn.

## 14. Helpdesk và recovery thủ công

Helpdesk có thể là con đường recovery hợp lệ cho tài khoản doanh nghiệp, nhưng thường là mục tiêu social engineering. Người hỗ trợ không nên tự quyết định danh tính dựa trên sự tự tin, chức danh hoặc thông tin nội bộ mà attacker có thể biết.

### Kiểm soát quy trình

1. Xác định loại yêu cầu và mức quyền cần khôi phục.
2. Kiểm tra account ownership bằng nguồn độc lập đã phê duyệt.
3. Không dùng manager name, employee ID, ngày sinh hoặc thông tin công khai làm bằng chứng duy nhất.
4. Dùng callback tới contact đã đăng ký trước hoặc quy trình proofing có kiểm soát.
5. Tách agent tiếp nhận và approver cho reset đặc quyền.
6. Giới hạn helpdesk chỉ tạo recovery request; service/policy engine mới quyết định có cấp grant hay không.
7. Ghi audit agent, approver, lý do, bằng chứng loại nào đã kiểm tra và kết quả.
8. Thông báo user qua kênh cũ khi có thay đổi.
9. Thu hồi quyền tạm thời và kiểm tra sau khi hoàn tất.

### Dual control

Với tài khoản admin hoặc hệ thống có tác động lớn, có thể yêu cầu hai người độc lập phê duyệt. Dual control giảm nguy cơ một nhân viên bị thao túng hoặc bị compromise, nhưng không thay identity proofing và không nên trở thành phê duyệt hình thức.

## 15. Recovery cho passkey và security key

Passkey có thể được đồng bộ giữa thiết bị qua credential provider hoặc gắn với authenticator cụ thể tùy hệ sinh thái. Người dùng có thể mất một thiết bị nhưng vẫn còn passkey trên thiết bị khác hoặc khóa dự phòng.

Recovery nên hướng người dùng:

- Thử authenticator/passkey khác đã đăng ký.
- Dùng security key dự phòng nếu có.
- Kiểm tra thiết bị đồng bộ passkey còn kiểm soát.
- Dùng recovery code hoặc quy trình proofing đã được phê duyệt nếu không còn authenticator.

Không tự động xóa mọi passkey khi user báo mất một thiết bị. Nếu nghi thiết bị bị đánh cắp hoặc account compromise, thu hồi credential liên quan theo phạm vi, revoke session/token và yêu cầu xác thực lại.

Với WebAuthn, server lưu public key và credential metadata. Khi credential bị thu hồi, đánh dấu không còn active ở server; không cần và không thể xóa private key trên authenticator từ xa trong mọi trường hợp.

## 16. Recovery code và mã dự phòng

Recovery code thường được tạo theo một bộ. Mỗi mã cần:

- Đủ ngẫu nhiên và không suy đoán được.
- Chỉ dùng một lần.
- Được lưu dạng hash/verifier.
- Có trạng thái used/revoked.
- Được vô hiệu toàn bộ khi tạo bộ mới.
- Không được gửi lại plaintext sau lần hiển thị đầu tiên.

Nếu user mất bộ mã, hệ thống phải chạy recovery flow khác; không có chức năng “xem lại recovery code cũ” từ database.

Recovery code không nên trở thành phương thức dùng hằng ngày hoặc được hỗ trợ qua helpdesk bằng cách đọc mã trong hệ thống. Nếu user nghi bộ mã bị lộ, revoke toàn bộ và tạo bộ mới sau khi xác thực đủ mạnh.

## 17. Session, token và authenticator sau recovery

Sau recovery, cần quyết định credential cũ nào còn đáng tin:

- Session hiện tại có thể bị revoke để buộc đăng nhập lại.
- Các session khác có thể cần revoke all nếu recovery xảy ra do compromise.
- Refresh token family cần revoke để attacker không xin token mới.
- Access token self-contained có thể còn hiệu lực tới exp nếu không có introspection/denylist/version check.
- TOTP seed cũ phải bị vô hiệu khi reset TOTP.
- Passkey/security key bị mất phải được đánh dấu revoked.
- Recovery code cũ phải bị tiêu thụ hoặc revoke.
- API key, app password hoặc credential downstream có thể cần rotation nếu có liên quan.

Không phải mọi password reset đều bắt buộc logout mọi thiết bị trong mọi hệ thống; policy cần dựa trên lý do recovery và rủi ro. Nhưng khi nghi account takeover, nên ưu tiên containment và thu hồi phiên/credential có khả năng bị attacker kiểm soát.

### Recovery không được giữ lại session của attacker

Nếu attacker đã tạo session trước khi nạn nhân recovery, việc chỉ thay password có thể không kết thúc session attacker. Cần revoke session hiện có theo policy, tăng account/session version hoặc dùng cơ chế tương đương để chặn credential cũ.

## 18. Risk-based recovery và thời gian chờ

Recovery service có thể kết hợp:

- Lần recovery gần nhất.
- Thay đổi email/phone gần đây.
- Thay đổi authenticator hoặc password gần đây.
- Số lần recovery thất bại.
- Session age và authentication freshness.
- Device-bound credential còn hoạt động.
- Tín hiệu abuse từ email/SMS/helpdesk.
- Loại tài khoản và mức đặc quyền.

Tín hiệu như IP, vị trí, User-Agent chỉ là risk signal; không chứng minh danh tính. Không khóa account chỉ vì người dùng đi du lịch hoặc đổi mạng.

Policy có thể:

| Tình huống | Hành động gợi ý |
|---|---|
| User còn passkey khác đã đăng ký | Xác thực bằng passkey đó rồi xử lý phương thức bị mất |
| User có recovery code hợp lệ | Cho recovery trong phạm vi code được phép, sau đó thông báo |
| Email recovery vừa thay đổi | Delay trước khi dùng email mới cho reset MFA |
| Nhiều yêu cầu recovery từ nguồn bất thường | Rate limit, restrict hoặc review |
| Account admin mất mọi factor | Quy trình proofing và dual control |
| Credential compromise được xác nhận | Containment, revoke session/token và recovery có assurance cao |

## 19. Java/Spring: mô hình recovery grant

Ví dụ sau minh họa lưu recovery grant với purpose, account, token hash và expiry. Đây là cấu trúc ứng dụng; việc gửi email/SMS và xác minh proof phải tích hợp provider phù hợp.

~~~java
enum RecoveryPurpose {
    PASSWORD_RESET,
    TOTP_RESET,
    AUTHENTICATOR_REPLACEMENT,
    RECOVERY_CONTACT_CHANGE
}

enum RecoveryStatus {
    PENDING,
    CONSUMED,
    REVOKED,
    EXPIRED
}

record RecoveryGrant(
    UUID id,
    UUID accountId,
    RecoveryPurpose purpose,
    byte[] tokenHash,
    Instant expiresAt,
    RecoveryStatus status,
    long accountSecurityVersion
) {}
~~~

### Tạo token recovery

~~~java
@Service
class RecoveryGrantService {
    private final SecureRandom random = new SecureRandom();
    private final RecoveryGrantRepository grants;
    private final RecoveryNotifier notifier;

    RecoveryGrantService(
            RecoveryGrantRepository grants,
            RecoveryNotifier notifier) {
        this.grants = grants;
        this.notifier = notifier;
    }

    void requestRecovery(UUID accountId, RecoveryPurpose purpose) {
        byte[] raw = new byte[32];
        random.nextBytes(raw);

        String token = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(raw);

        byte[] tokenHash = sha256(token);
        Instant expiresAt = Instant.now().plus(Duration.ofMinutes(15));

        RecoveryGrant grant = grants.createPending(
            accountId,
            purpose,
            tokenHash,
            expiresAt
        );

        notifier.sendRecoveryInstruction(grant, token);
    }

    private byte[] sha256(String token) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
~~~

Ví dụ dùng token ngẫu nhiên 256-bit nên SHA-256 verifier phù hợp với token entropy cao; không áp dụng cách lưu này cho password hoặc mã ngắn dễ đoán. Token thô chỉ được truyền tới notifier để gửi một lần, không lưu plaintext và không ghi log.

### Tiêu thụ token một lần

~~~java
@Transactional
void completePasswordReset(String rawToken, String newPassword) {
    byte[] suppliedHash = sha256(rawToken);
    RecoveryGrant grant = grants.lockPendingByHash(suppliedHash)
        .orElseThrow(InvalidRecoveryException::new);

    if (grant.purpose() != RecoveryPurpose.PASSWORD_RESET
            || grant.status() != RecoveryStatus.PENDING
            || grant.expiresAt().isBefore(Instant.now())) {
        throw new InvalidRecoveryException();
    }

    accountSecurity.requireVersion(
        grant.accountId(),
        grant.accountSecurityVersion()
    );

    passwordService.setNewPassword(grant.accountId(), newPassword);
    grants.consumeAtomically(grant.id());
    sessionService.revokeSessionsByRecoveryPolicy(grant.accountId());
    refreshTokenService.revokeByRecoveryPolicy(grant.accountId());
    audit.recordRecovery(grant.accountId(), "PASSWORD_RESET", "COMPLETED");
}
~~~

Đây là pseudocode: repository phải khóa/consume grant bằng conditional update để chỉ một request thành công; passwordService phải dùng password hashing phù hợp; session/token revocation có thể là hệ thống phân tán nên cần outbox/retry và trạng thái partial. Không truyền raw token vào audit. Không cho request body thay đổi purpose của grant.

## 20. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Email là bằng chứng duy nhất cho reset MFA | Email takeover dẫn tới chiếm toàn bộ account | Recovery assurance cao hơn và bằng chứng độc lập |
| Password reset tự động xóa MFA | Attacker bypass factor mạnh | Tách purpose và policy cho từng hành động |
| Token recovery không hết hạn | Link bị lộ có thể dùng lâu dài | TTL ngắn và revoke khi state thay đổi |
| Recovery token dùng nhiều lần | Replay và reset lặp | One-time atomic consumption |
| Lưu token plaintext | Database leak tạo recovery capability | Lưu hash/verifier |
| Response tiết lộ account tồn tại | Account enumeration | Generic response và rate limit |
| Helpdesk reset MFA chỉ bằng thông tin cá nhân | Social engineering takeover | Independent proofing, dual control và audit |
| Chỉ clear cookie sau recovery | Attacker giữ session cũ | Server-side session/token revocation |
| Email/phone mới dùng ngay cho mọi recovery | Attacker đổi kênh rồi tự reset MFA | Verify, notify old channel và cooling-off |
| SMS được coi là phishing-resistant | SIM swap/interception | Dùng passkey/security key cho assurance cao |
| Recovery code lưu plaintext | Lộ database làm lộ mã dự phòng | Hash, one-time use và rotation |
| Không có notification | Chủ account khó phát hiện takeover | Alert tới kênh đã xác minh trước |
| Rate limit chỉ theo IP | Botnet bypass hoặc khóa nhầm user | Multi-dimensional throttling và abuse detection |
| Không có partial-failure handling | User tưởng token/session đã revoke hết | Outbox/retry, trạng thái pending và audit |

## 21. Ma trận kiểm thử recovery abuse

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Identifier không tồn tại được gửi tới recovery | Response không tiết lộ account tồn tại |
| Nhiều recovery request cho cùng account | Rate limit/cooldown và giới hạn grant pending |
| Token recovery sai | Từ chối, không thay đổi account |
| Token hết hạn | Từ chối |
| Token đã dùng được gửi lại | Từ chối |
| Hai request dùng cùng token đồng thời | Chỉ một request thành công |
| Token PASSWORD_RESET dùng cho TOTP_RESET | Từ chối |
| Account security version thay đổi sau khi cấp token | Token cũ bị vô hiệu theo policy |
| Email recovery vừa thay đổi | Cooling-off hoặc step-up theo policy |
| SMS code sau SIM-swap signal | Áp dụng risk policy, không coi SMS là bằng chứng duy nhất |
| Helpdesk agent tự reset admin MFA không có approver | Từ chối |
| Recovery code đã sử dụng | Từ chối lần tiếp theo |
| Tạo bộ recovery code mới | Bộ code cũ bị revoke |
| Password reset sau account takeover nghi ngờ | Session/token bị revoke theo containment policy |
| Refresh token cũ sau recovery | Authorization server từ chối nếu đã revoke |
| Access JWT cũ sau recovery | Bị xử lý theo revocation/version/introspection/lifetime policy |
| User báo recovery không phải của họ | Pending change có thể bị hold/revoke và incident được tạo |
| Email/SMS provider timeout | Không đánh dấu recovery hoàn tất khi chưa gửi/verify cần thiết |
| Notification gửi tới kênh mới duy nhất | Test phát hiện thiếu cảnh báo tới kênh cũ theo policy |
| Recovery grant bị log | Secret scanner phát hiện; log phải được redaction |
| Attacker thử nhiều account từ nhiều IP | Multi-dimensional abuse controls phát hiện |
| User hợp lệ đổi mạng hoặc đi du lịch | Không tự động khóa chỉ dựa vào IP/geolocation |
| Recovery admin account | Yêu cầu proofing/dual control và audit |
| Partial token revocation failure | UI/API báo pending/partial, retry có giám sát |

Kiểm thử trong môi trường test bằng account, email, số điện thoại và token giả lập. Không đưa recovery link, OTP, recovery code hoặc dữ liệu định danh thật vào ticket/log.

## 22. Tình huống phân tích

### Tình huống A: email takeover dẫn tới MFA reset

An dùng email làm kênh recovery duy nhất. Attacker chiếm mailbox, reset password, xóa TOTP rồi đăng ký passkey của mình.

**Phân tích:** recovery chain có cùng một trust root là email. Cần tách password reset khỏi MFA reset, yêu cầu assurance cao hơn để xóa authenticator, thông báo tới kênh cũ và thu hồi session/token cũ.

### Tình huống B: helpdesk bị thao túng

Attacker gọi hỗ trợ, biết tên quản lý và mã nhân viên của An. Nhân viên helpdesk reset MFA sau khi nghe câu chuyện mất điện thoại.

**Phân tích:** thông tin nội bộ không phải bằng chứng độc lập. Cần quy trình proofing, callback tới contact đã đăng ký, dual control cho account nhạy cảm và audit agent/approver.

### Tình huống C: recovery token bị replay

Một link password reset bị ghi trong proxy log. Attacker dùng token sau khi user đã đặt mật khẩu mới.

**Phân tích:** token phải one-time và được tiêu thụ nguyên tử. Sau khi reset, tăng security version hoặc revoke grant cũ; redaction log và đánh giá phạm vi token đã lộ.

### Tình huống D: attacker thay email recovery rồi chờ

Attacker có phiên yếu, thay email recovery thành mailbox của họ. Hệ thống cho email mới có hiệu lực ngay lập tức.

**Phân tích:** cần xác minh email mới, thông báo kênh cũ và cooling-off cho hành động nhạy cảm. Nếu có tín hiệu compromise, hold thay đổi và revoke session nghi ngờ.

### Tình huống E: người dùng mất toàn bộ authenticator

Một admin mất điện thoại và security key. Helpdesk đề nghị chỉ gửi SMS để reset MFA.

**Phân tích:** tài khoản admin có blast radius cao. Dùng quy trình proofing đặc biệt, dual approval, phương thức break-glass được kiểm soát và thông báo/audit. SMS không nên tự động thay thế assurance mạnh.

## 23. Quy trình thiết kế và vận hành

Trước khi phát hành recovery flow, hãy xác định:

1. Những tình huống recovery nào được hỗ trợ và hành động nào có thể được thực hiện?
2. Mỗi purpose có assurance baseline và bằng chứng độc lập nào?
3. Email, SMS, recovery code, helpdesk và identity proofing có trust boundary nào?
4. Response có chống account enumeration không?
5. Recovery token có entropy, hash, TTL, purpose binding và one-time consumption không?
6. Có giới hạn số grant active, rate limit và cooldown đa chiều không?
7. Thay đổi email/phone/MFA có notification tới kênh cũ và cooling-off không?
8. Recovery vừa hoàn tất có bị giới hạn thêm trước khi enrollment authenticator mới không?
9. Session, refresh token, access token và authenticator cũ được revoke theo policy nào?
10. Helpdesk có phân tách nhiệm vụ, dual control và audit không?
11. Recovery service/provider lỗi có trạng thái partial/pending và retry an toàn không?
12. Có đường báo cáo recovery không do user yêu cầu và quy trình containment không?
13. Có bảo vệ PII, recovery code, token và log theo retention policy không?
14. Có diễn tập email takeover, SIM swap, helpdesk social engineering và MFA reset abuse không?

## 24. Ghi nhớ trọng tâm

- **Recovery là một đường xác thực quan trọng.** Nếu yếu hơn quá nhiều so với đăng nhập, attacker sẽ nhắm vào recovery để bypass MFA.
- **Tách purpose và assurance.** Password reset không tự động cho phép reset MFA, thay recovery channel hoặc khôi phục admin.
- **Email/SMS/helpdesk có giới hạn.** Không dùng một kênh yếu làm bằng chứng duy nhất cho hành động có tác động lớn.
- **Recovery token phải ngẫu nhiên, purpose-bound, ngắn hạn và dùng một lần.** Lưu verifier/hash, tiêu thụ nguyên tử và chống replay.
- **Thông báo kênh cũ và cooling-off giúp phát hiện/giảm tác động takeover.** Chúng không thay thế proofing.
- **Helpdesk cần quy trình và phân tách nhiệm vụ.** Không phê duyệt dựa trên thông tin cá nhân công khai hoặc áp lực khẩn cấp.
- **Sau recovery cần xem xét session, refresh token, access token và authenticator cũ.** Đổi password không tự động chặn session attacker.
- **Rate limit phải chống automation nhưng không tạo lockout dễ bị lạm dụng.**
- **Risk signal không phải bằng chứng danh tính.** IP và geolocation chỉ hỗ trợ policy.
- **Recovery cho tài khoản đặc quyền cần assurance và audit cao hơn.**

Account recovery an toàn phải khôi phục đúng chủ thể với quyền vừa đủ, đồng thời làm mất hiệu lực các đường truy cập mà attacker có thể đang kiểm soát. Khi purpose, evidence, token, delay, notification và revocation được thiết kế như một vòng đời thống nhất, recovery không còn là lối tắt để vượt qua hệ thống xác thực.
