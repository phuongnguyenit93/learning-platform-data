# Case account takeover

**Account takeover (ATO)** là tình huống một người không được phép giành quyền kiểm soát tài khoản của người khác và sử dụng tài khoản đó như chủ tài khoản hợp lệ. Một vụ ATO có thể bắt đầu từ password bị tái sử dụng, phishing, MFA fatigue, thiết bị bị mất, session/token bị đánh cắp, recovery process bị lạm dụng hoặc identity provider bị liên kết trái phép. Vì vậy, điều tra ATO không thể chỉ hỏi “password có đúng không?”; cần dựng lại toàn bộ vòng đời xác thực, phiên, credential, recovery và hành động được thực hiện sau khi đăng nhập.

Case study này mô phỏng một sự cố tại StudyHub, một nền tảng học trực tuyến có web app, mobile app, passkey, password, MFA, OAuth/OIDC, refresh token rotation và account recovery. Một giảng viên báo rằng có người thay đổi thông tin liên hệ, tải tài liệu lớp học và thêm một phương thức đăng nhập mà họ không nhận ra. Nhóm bảo mật phải xác định cách tài khoản bị chiếm, giới hạn tác động, khôi phục quyền kiểm soát và loại bỏ nguyên nhân gốc.

Đây là tình huống giả định phục vụ học tập. Các mốc thời gian, số liệu, tên dịch vụ và account reference đều là dữ liệu minh họa, không mô tả một sự cố có thật. Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, giúp người học hiểu credential, password, MFA, passkey, certificate, token, session, identity linking và account recovery; đồng thời mô hình hóa trust boundary, chống phishing/replay và thiết kế authentication flow an toàn. Trong chương **Case study**, bài này tập trung vào một vụ account takeover từ tín hiệu ban đầu đến điều tra, containment, recovery và phòng ngừa tái diễn.

## 1. Mục tiêu học tập

Sau khi phân tích case, người học có thể:

1. Dựng timeline từ authentication event, session event, token event, recovery event và audit record.
2. Phân biệt dấu hiệu, bằng chứng xác nhận và giả thuyết chưa được kiểm chứng.
3. Xác định trust boundary bị vượt qua và credential/session nào có thể đã bị lộ.
4. Phân tích cách password, MFA, passkey, OAuth/OIDC, refresh token và recovery tương tác trong một vụ ATO.
5. Xác định hành động của attacker sau khi chiếm session và mức tác động đến dữ liệu/quyền.
6. Chọn containment theo phạm vi: session, token family, credential, identity link, account và device.
7. Khôi phục tài khoản với assurance phù hợp mà không dựa vào kênh liên hệ có thể đã bị chiếm.
8. Thiết kế notification, support workflow và communication an toàn cho chủ tài khoản.
9. Đề xuất remediation kỹ thuật, vận hành và UX có thể đo lường.
10. Xây dựng bộ test chứng minh đường tấn công bị chặn và credential cũ không thể được dùng lại.

## 2. Bối cảnh hệ thống StudyHub

StudyHub cung cấp khóa học, lớp trực tuyến, bài tập và kho tài liệu cho học viên/giảng viên. Một tài khoản có thể đăng nhập từ web và mobile, liên kết với một external identity provider và đăng ký nhiều authenticator.

### 2.1. Thành phần liên quan

| Thành phần | Vai trò | Dữ liệu hoặc quyết định quan trọng |
| --- | --- | --- |
| Web App | UI đăng nhập và quản lý tài khoản | Session cookie, CSRF transaction, redirect state. |
| Mobile App | Đăng nhập và truy cập nội dung trên điện thoại | Access token, refresh token, OS secure storage. |
| Identity Service | Điều phối authentication | Password verification, MFA policy, account state. |
| Credential Store | Lưu verifier và credential metadata | Password hash, passkey public key, factor reference. |
| MFA Service | TOTP và push challenge | Challenge state, factor status, attempt limits. |
| Authorization Server | OAuth/OIDC và token lifecycle | Authorization code, access/refresh token, grant. |
| Session Store | Quản lý web sessions và revoke | Session reference, expiry, revoked state. |
| Recovery Service | Khôi phục tài khoản | Recovery transaction, proof, cooldown. |
| Identity Link Service | Liên kết external identity | Issuer, subject reference, linking state. |
| Risk Engine | Đánh giá tín hiệu bất thường | Risk decision, step-up/deny signal. |
| Audit Pipeline | Thu thập authentication/security event | Actor, subject, outcome, correlation và timestamp. |
| Course API | Cấp quyền truy cập tài liệu/lớp học | Authorization theo role, tenant và resource. |
| Notification Service | Gửi cảnh báo bảo mật | Email/push đã xác minh, delivery status. |

### 2.2. Authentication flow bình thường

Người dùng có thể:
- Đăng nhập bằng password rồi hoàn tất MFA nếu policy yêu cầu.
- Đăng nhập bằng passkey đã đăng ký.
- Dùng OIDC SSO qua issuer đã cấu hình.
- Nhận web session cookie hoặc mobile access/refresh token.
- Thêm hoặc gỡ authenticator sau re-authentication/step-up.
- Khôi phục tài khoản qua recovery factor đã đăng ký và quy trình kiểm soát.

Web app sử dụng session cookie có Secure, HttpOnly và SameSite theo flow. Mobile app lưu refresh token trong secure storage của hệ điều hành. Refresh token rotation được bật; reuse detection có thể revoke token family. Passkey server-side chỉ lưu credential ID, public key và metadata. Password được lưu dưới dạng password verifier bằng password hashing chuyên dụng.

### 2.3. Tài sản cần bảo vệ

- Quyền truy cập tài khoản và nội dung cá nhân.
- Quyền giảng viên quản lý lớp, điểm và tài liệu.
- Thông tin liên hệ và recovery factor.
- Password verifier, TOTP seed, passkey public key và credential metadata.
- Session cookie, access token, refresh token và token family.
- Identity link tới external IdP.
- Audit event và bằng chứng điều tra.
- Quyền quản trị tenant và thay đổi authentication policy.

## 3. Sự cố được báo cáo

Lúc 09:12 giờ địa phương, một giảng viên liên hệ support: họ không thể đăng nhập bằng password quen thuộc, nhận email báo thay đổi recovery email và thấy một thiết bị mới trong danh sách tài khoản. Họ nói không thực hiện những thay đổi đó. Trước đó khoảng một giờ, họ nhận nhiều push notification yêu cầu phê duyệt đăng nhập nhưng đã từ chối.

Support xác minh người báo cáo qua quy trình hiện có, mở incident mức độ cao và chuyển Security Operations. Tài khoản được xác định có quyền truy cập nhiều lớp học và tài liệu nội bộ. Nhóm phản ứng phải trả lời:

- Có phải tài khoản đã bị chiếm thật hay chỉ là nhầm lẫn do đổi thiết bị?
- Attacker đã vượt qua password, MFA, recovery hay session boundary?
- Có authenticator hoặc external identity mới được liên kết không?
- Session/token nào còn hoạt động?
- Dữ liệu nào đã được xem, tải hoặc thay đổi?
- Có tài khoản khác bị ảnh hưởng bởi cùng chiến dịch không?

### 3.1. Thông tin ban đầu

| Thuộc tính | Giá trị giả định |
| --- | --- |
| Account reference | acct_73A19 |
| Role | Instructor |
| Tenant | studyhub-partner-04 |
| Report time | 09:12 ICT |
| First suspicious signal | 08:03 ICT |
| Known devices | Laptop cá nhân và điện thoại đã đăng ký |
| Known authenticators | Password, TOTP, một passkey |
| New factor reported | Push-capable mobile installation chưa nhận diện |
| Sensitive changes | Recovery email đổi; external identity link mới |
| Business impact | Có thể truy cập tài liệu và dữ liệu lớp học |

Các giá trị trên chỉ giúp người học theo dõi case. Không sử dụng chúng như định dạng ID production.

## 4. Dữ kiện điều tra và timeline

Nhóm điều tra thu thập authentication events, token/session records, account audit, notification delivery và Course API audit. Các nguồn được lưu read-only trong incident evidence store; raw password, OTP, cookie và token không được sao chép vào ticket.

### 4.1. Timeline đã chuẩn hóa

| Thời gian ICT | Event | Kết quả ghi nhận | Mức độ chắc chắn |
| --- | --- | --- | --- |
| 07:48 | Login failures trên nhiều account | Một nhóm source thử nhiều cặp account/password; có account bị thử nhiều lần | Đã xác nhận |
| 07:56 | Login failure của acct_73A19 | Password verification thất bại nhiều lần | Đã xác nhận |
| 08:01 | Password login của acct_73A19 | Password verification success từ browser context chưa thấy trước đó | Đã xác nhận |
| 08:02 | Push MFA challenge issued | Nhiều challenge trong thời gian ngắn | Đã xác nhận |
| 08:03 | Push challenge denied/timeout | Có nhiều lần deny/timeout, không phải success | Đã xác nhận |
| 08:05 | MFA challenge success | Một challenge được chấp nhận; nguồn client mới | Đã xác nhận |
| 08:06 | Session created | Web session mới được tạo | Đã xác nhận |
| 08:09 | Recovery email changed | Địa chỉ recovery thay đổi qua account settings | Đã xác nhận |
| 08:11 | External identity linked | Một issuer/subject reference mới được liên kết | Đã xác nhận |
| 08:14 | Passkey enrollment started | Enrollment transaction được tạo | Đã xác nhận |
| 08:15 | Passkey enrollment completed | Credential mới active | Đã xác nhận |
| 08:19 | Refresh token rotated | Mobile client nhận token mới trong một token family | Đã xác nhận |
| 08:26 | Course API access | Tài liệu của ba lớp được đọc/tải | Đã xác nhận |
| 08:41 | Notification delivered | Cảnh báo recovery email và authenticator mới được gửi | Đã xác nhận |
| 09:12 | User report | Chủ tài khoản báo không thực hiện thay đổi | Đã xác nhận |
| 09:18 | Incident declared | Security Operations bắt đầu containment | Đã xác nhận |

### 4.2. Dữ kiện không được diễn giải quá mức

- Một IP hoặc geolocation mới không chứng minh attacker; người dùng có thể dùng VPN, mạng di động hoặc đi du lịch.
- Một browser fingerprint khác không phải bằng chứng danh tính.
- Push challenge success chứng minh challenge đã được chấp nhận theo protocol, không chứng minh chủ tài khoản là người chấp nhận.
- Password verification success không chứng minh toàn bộ authentication flow hợp lệ nếu MFA hoặc risk policy có lỗi.
- Passkey enrollment thành công chứng minh server đã nhận proof hợp lệ cho transaction đó; nó không chứng minh người khởi tạo là chủ tài khoản hợp pháp nếu session trước đó đã bị chiếm.
- Email notification đã được gửi không chứng minh người dùng đã đọc hoặc kiểm soát mailbox nhận thông báo.
- API read event cho thấy dữ liệu được truy cập; không tự động chứng minh dữ liệu đã bị phát tán ra ngoài.

## 5. Dựng lại attack path

Từ các dữ kiện hiện có, nhóm điều tra xây dựng giả thuyết chính: attacker có được password của nạn nhân, sau đó gây áp lực bằng nhiều push challenge. Một challenge được chấp nhận, có thể do người dùng nhầm lẫn hoặc do thiết bị/session notification bị lạm dụng. Khi có session, attacker thay recovery email, liên kết external identity và thêm passkey của họ để duy trì quyền truy cập. Sau đó attacker sử dụng session/token hợp lệ để đọc tài liệu.

Giả thuyết này phù hợp timeline nhưng vẫn cần kiểm tra thêm nguồn password exposure, thiết bị đã chấp nhận push, context của MFA transaction và nguồn identity link.

~~~mermaid
flowchart TD
    A[Password bị lộ hoặc tái sử dụng] --> B[Password login thành công]
    B --> C[Nhiều push challenge]
    C --> D[Một challenge được chấp nhận]
    D --> E[Session hợp lệ được tạo]
    E --> F[Recovery email bị thay đổi]
    F --> G[External identity được liên kết]
    G --> H[Passkey mới được enroll]
    H --> I[Refresh token/session tiếp tục hoạt động]
    I --> J[Course API truy cập tài liệu]
    J --> K[Chủ tài khoản phát hiện và báo cáo]
~~~

### 5.1. Giai đoạn 1 — Credential exposure

Các login failure trước đó có thể liên quan credential stuffing hoặc một chiến dịch thử password. Một lần password verification success sau chuỗi failure là tín hiệu đáng điều tra, đặc biệt khi context client mới.

Những khả năng cần kiểm tra:
- Password bị tái sử dụng từ một dịch vụ khác đã bị lộ.
- Người dùng nhập password vào trang phishing.
- Malware hoặc extension độc hại thu thập credential.
- Password được chia sẻ hoặc lưu trên thiết bị không an toàn.
- Attacker đoán được password yếu.

Không kết luận nguồn lộ chỉ dựa trên login event. Cần xem telemetry chiến dịch, threat intelligence phù hợp, user report và các dấu hiệu endpoint/mailbox nếu có.

### 5.2. Giai đoạn 2 — MFA approval

Push MFA có nhiều challenge liên tiếp. Người dùng có thể bị mệt mỏi và chấp nhận một yêu cầu để thông báo dừng lại. Đây là dạng MFA fatigue. Cũng cần kiểm tra khả năng notification bị chuyển tiếp, thiết bị nhận push bị chiếm hoặc challenge binding không đủ chặt.

Một push approval an toàn phải:
- Gắn với đúng login transaction và challenge.
- Có expiry, nonce và replay protection.
- Hiển thị context đủ để người dùng nhận biết yêu cầu bất thường.
- Dùng number matching hoặc transaction detail khi phù hợp.
- Có rate limit/cooldown và giới hạn số challenge.
- Ghi nhận deny, timeout và approve thành event riêng.

Không nên suy ra “MFA đã được dùng nên ATO không thể xảy ra”. MFA là một lớp kiểm soát; enrollment, recovery, push UX và session lifecycle cũng phải an toàn.

### 5.3. Giai đoạn 3 — Session takeover và persistence

Sau khi MFA hoàn tất, session mới được tạo. Attacker sử dụng quyền trong session để thay recovery email, link external identity và enroll passkey. Các thay đổi này biến một lần đăng nhập trái phép thành khả năng duy trì truy cập lâu dài.

Các câu hỏi quan trọng:
- Những hành động này có yêu cầu step-up gần thời điểm thực hiện không?
- Step-up có dùng factor độc lập đã đăng ký trước incident không?
- Proof có gắn với từng transaction hay có thể tái sử dụng?
- Có cảnh báo qua kênh liên hệ đã xác minh trước đó không?
- Có cooldown cho recovery contact hoặc factor mới không?
- Session có được rotate sau thay đổi credential không?
- Token family cũ có bị revoke khi recovery email, factor hoặc identity link thay đổi không?

### 5.4. Giai đoạn 4 — Token và dữ liệu

Refresh token rotation ghi nhận một lần rotate sau các thay đổi tài khoản. Điều tra cần xác định:
- Token family thuộc client nào.
- Refresh request diễn ra trước hay sau factor changes.
- Có token reuse hoặc session concurrency bất thường không.
- Refresh token có được lưu trong secure storage của mobile app không.
- API access được authorize theo role/resource hiện hành hay chỉ dựa vào session.
- Các hành động read/download nào đã xảy ra và dữ liệu nào bị thay đổi.

Không log raw token để điều tra. Dùng token family reference, grant reference, session reference và event correlation.

## 6. Trust boundary bị vượt qua

Sự cố có thể bao gồm nhiều trust boundary liên tiếp:

| Trust boundary | Kỳ vọng | Dấu hiệu trong case | Câu hỏi điều tra |
| --- | --- | --- | --- |
| User ↔ Login UI | Người dùng gửi credential tới origin tin cậy | Password login từ context mới | Có phishing hoặc endpoint giả không? |
| Client ↔ Identity Service | TLS và transaction state bảo vệ request | Login/MFA được xử lý | Client context và challenge có được ràng buộc không? |
| MFA device ↔ MFA Service | Chỉ chủ factor chấp nhận đúng challenge | Nhiều deny rồi một approve | Number matching/context có đủ không? |
| Session ↔ Account settings | Thay đổi nhạy cảm cần re-auth/step-up | Recovery email và identity link đổi | Step-up freshness và transaction binding ra sao? |
| Identity Link ↔ External IdP | Issuer/subject phải được xác minh và liên kết có chủ đích | Identity mới được link | Có xác nhận qua identity đang đăng nhập không? |
| Authenticator ↔ Credential Store | Chỉ credential được xác minh mới active | Passkey mới được enroll | Challenge/origin/account binding và step-up có hợp lệ không? |
| Token ↔ Resource API | Token hợp lệ và authorization đúng resource | Tài liệu được đọc/tải | Token/session có bị revoke và policy được áp dụng không? |
| Audit ↔ Incident response | Event đủ tin cậy và có thể truy vết | Timeline được dựng | Có event loss, clock skew hoặc thiếu actor/subject không? |

Điểm mấu chốt: credential đúng ở một bước không tự động cấp quyền thay đổi toàn bộ các yếu tố khôi phục và authenticator của tài khoản. Mỗi hành động có tác động lâu dài phải có authorization riêng và bằng chứng xác thực phù hợp.

## 7. Phân biệt bằng chứng, giả thuyết và khoảng trống

Trong incident, nhóm không nên biến giả thuyết thành kết luận. Dùng evidence ledger:

| Nhận định | Loại | Bằng chứng cần có | Trạng thái |
| --- | --- | --- | --- |
| Password của tài khoản đã được sử dụng thành công | Fact | Password verification event | Confirmed |
| Attacker có password từ credential stuffing | Hypothesis | Campaign correlation, nguồn lộ, user/device evidence | Chưa kết luận |
| Người dùng đã bấm approve push | Hypothesis | MFA device audit, interaction evidence nếu có và user interview | Chưa kết luận |
| Session mới đã được tạo | Fact | Session created event và session reference | Confirmed |
| Recovery email đã đổi | Fact | Account audit record | Confirmed |
| External identity đã link | Fact | Identity link event, issuer/subject reference | Confirmed |
| Passkey mới đã active | Fact | Credential store/audit state | Confirmed |
| Tài liệu ba lớp đã được truy cập | Fact | Course API audit | Confirmed |
| Dữ liệu đã bị tải ra ngoài | Hypothesis | Egress/download evidence và recipient context | Chưa kết luận |
| Có nhiều tài khoản bị ảnh hưởng | Hypothesis | Campaign correlation và account event search | Đang điều tra |

Nếu không có dữ liệu chứng minh một hành động, ghi rõ “unknown”. Không suy diễn từ một signal đơn lẻ. Giữ nguyên log nguồn, hash evidence export và ghi người truy cập để bảo toàn chain of custody.

## 8. Containment — giới hạn tác động

Khi xác suất ATO cao và có thay đổi credential trái phép, containment cần nhanh nhưng đúng phạm vi. Trước tiên bảo toàn evidence cần thiết, sau đó chặn khả năng tiếp tục truy cập.

### 8.1. Các bước containment

1. Xác minh người báo cáo qua quy trình hỗ trợ độc lập, không dựa vào recovery email vừa bị thay.
2. Đánh dấu account ở trạng thái incident/restricted để ngăn thay đổi bảo mật mới trong lúc xử lý.
3. Revoke session mới và các session có dấu hiệu liên quan.
4. Revoke refresh token family/grant liên quan; kiểm tra token propagation tới mọi region.
5. Vô hiệu passkey vừa enroll và external identity link mới sau khi xác nhận không hợp lệ.
6. Đưa recovery email mới vào trạng thái untrusted; khôi phục contact bằng quy trình xác minh độc lập.
7. Thu hồi push factor/device installation đáng ngờ nếu xác định được.
8. Yêu cầu password reset sau khi xác minh chủ tài khoản và đánh giá các thiết bị có thể bị compromise.
9. Chặn hoặc step-up các hành động nhạy cảm trong thời gian recovery.
10. Bảo toàn event, API audit, notification delivery và identity-link evidence.

Không xóa toàn bộ credential hợp lệ một cách mù quáng. Nếu nạn nhân vẫn kiểm soát một passkey hoặc security key đáng tin, có thể giữ nó làm factor cho recovery sau khi xác minh. Nếu không chắc factor nào an toàn, revoke phạm vi rộng hơn và chuyển qua proofing/recovery có kiểm soát.

### 8.2. Phạm vi revoke

| Đối tượng | Hành động | Kiểm tra sau revoke |
| --- | --- | --- |
| Web session | Revoke session reference và invalidate server-side | Replay cookie cũ bị từ chối ở mọi region. |
| Refresh token | Revoke token family/grant | Refresh token cũ và token descendant bị từ chối. |
| Access token | Chờ expiry ngắn hoặc revoke/introspect theo thiết kế | API nhạy cảm không chấp nhận token bị thu hồi sau SLA. |
| Passkey mới | Mark revoked/disabled | Assertion mới từ credential bị từ chối. |
| External identity link | Disable link và yêu cầu xác minh lại | Login qua identity link đó không còn vào account. |
| Push factor/device key | Revoke factor binding | Challenge gửi tới thiết bị đó không thể hoàn tất. |
| Recovery contact | Đóng băng thay đổi và xác minh lại | Kênh mới không được dùng để reset account trước xác minh. |
| Password | Reset sau identity verification | Password cũ không còn xác thực được. |

### 8.3. Vì sao không chỉ đổi password?

Đổi password không tự động revoke:
- Web session đã tồn tại.
- Refresh token đã cấp.
- Passkey attacker đã enroll.
- External identity link trái phép.
- Push factor hoặc recovery contact mới.
- Token cache hoặc session replica ở region khác.

Một quy trình recovery phải rà soát mọi đường đăng nhập và persistence path, không chỉ credential ban đầu.

## 9. Khôi phục tài khoản và xác minh chủ sở hữu

Recovery là bước rủi ro cao. Attacker có thể đã thay email/phone hoặc thêm authenticator của họ; vì vậy không dùng kênh mới làm proof duy nhất.

### 9.1. Recovery flow đề xuất

1. Đưa account vào recovery/restricted state.
2. Xác định các factor đã tồn tại trước thời điểm nghi ngờ compromise.
3. Xác minh người dùng bằng factor độc lập còn tin cậy hoặc quy trình identity proofing phù hợp.
4. Nếu dùng support-assisted recovery, áp dụng separation of duties, callback tới contact đã xác minh trước đó và audit đầy đủ.
5. Thu hồi session, token family, factor và identity link trái phép.
6. Khôi phục recovery contact từ dữ liệu đã xác minh, có thông báo và cooldown theo policy.
7. Yêu cầu tạo password mới nếu password có thể bị lộ.
8. Yêu cầu đăng ký lại MFA/passkey trên thiết bị do người dùng kiểm soát.
9. Cung cấp recovery codes mới và vô hiệu bộ cũ.
10. Giới hạn hành động nhạy cảm trong thời gian cooling-off nếu risk policy cần.
11. Thông báo các thay đổi qua kênh đã xác minh độc lập.
12. Đóng recovery chỉ khi account state, credential inventory và session inventory đã được kiểm tra.

### 9.2. Assurance và recovery

Recovery không được tự động có assurance thấp hơn login thông thường. Nếu hệ thống không còn factor đáng tin, có thể cần identity proofing, xác minh tổ chức hoặc quy trình thủ công được kiểm soát. Người hỗ trợ không nên có quyền tự ý bỏ qua mọi bước.

### 9.3. Tránh lockout và recovery loop

- Giải thích bước tiếp theo và thời gian xử lý.
- Không yêu cầu người dùng lặp lại một proof đã thất bại vô hạn.
- Cho phép cung cấp evidence bổ sung qua kênh được phê duyệt.
- Không tiết lộ account tồn tại qua response quá chi tiết.
- Có escalation khi người dùng mất mọi factor.
- Ghi rõ factor nào đã bị revoke và factor nào còn active.
- Sau recovery, xác nhận người dùng có thể đăng nhập bằng phương thức mới và biết cách bảo vệ recovery code.

## 10. Điều tra tác động và phạm vi

Sau containment, nhóm đánh giá những gì attacker đã làm.

### 10.1. Account activity

Kiểm tra:
- Profile và recovery contact changes.
- Passkey/MFA enrollment/removal.
- Identity link/unlink.
- Password reset và session creation.
- Course enrollment, grade, payment hoặc role changes.
- File view/download/export.
- Admin actions và API token creation.
- Notification delivery và mailbox changes.

### 10.2. Data impact

Phân loại:
- Dữ liệu chỉ được xem.
- Dữ liệu được tải xuống hoặc export.
- Dữ liệu bị thay đổi/xóa.
- Dữ liệu được chia sẻ với người khác.
- Dữ liệu thuộc tenant/lớp học khác.
- Dữ liệu cá nhân hoặc nội dung có nghĩa vụ thông báo.

Không khẳng định dữ liệu bị exfiltrate chỉ vì có download event. Kết hợp API logs, storage access logs, network egress và bằng chứng downstream. Nếu không đủ telemetry, ghi rõ giới hạn kết luận.

### 10.3. Scope expansion

Tìm kiếm:
- Login failure/success pattern cùng campaign trên nhiều account.
- Nhiều push challenge hoặc factor enrollment bất thường.
- Cùng external issuer/subject hoặc client ID xuất hiện bất thường.
- Recovery email changes từ cùng flow/client.
- Refresh token reuse và session context bất thường.
- Credential stuffing signals ở các tenant khác.
- Support ticket hoặc notification report liên quan.

Chỉ mở rộng containment khi evidence/risk justify. Tránh khóa hàng loạt account chỉ vì một IP hoặc user-agent trùng nhau.

## 11. Root cause và contributing factors

Giả thuyết root cause ban đầu gồm ba lớp:

**Credential compromise:** password có thể đã bị tái sử dụng hoặc bị lộ qua phishing. Các login failure và success sau đó phù hợp với khả năng credential stuffing nhưng chưa chứng minh nguồn.

**MFA approval weakness:** push UX cho phép nhiều challenge và không hiển thị đủ transaction context hoặc number matching. Người dùng có thể bị fatigue và chấp nhận nhầm.

**Post-authentication persistence:** các thay đổi recovery email, identity link và passkey enrollment có thể được thực hiện từ một session mới mà không yêu cầu step-up đủ mới hoặc thông báo/cooldown có hiệu quả.

### 11.1. Control gap cần xác minh

| Control | Kỳ vọng | Gap giả định cần điều tra |
| --- | --- | --- |
| Password defense | Password hashing, breached-password screening, rate limit | Password reuse và campaign detection chưa đủ. |
| MFA push | Transaction context, number matching, challenge rate limit | Nhiều challenge không tạo đủ friction/alert. |
| Step-up | Factor độc lập, freshness và transaction binding | Session mới có thể thay đổi recovery settings quá dễ. |
| Identity linking | Re-authentication, issuer validation, explicit confirmation | External identity link mới không có confirmation độc lập. |
| Passkey enrollment | Challenge/origin/account binding và recent step-up | Enrollment dựa trên session đã bị chiếm. |
| Recovery contact change | Step-up, cooldown, old-channel notification | Kênh mới có thể được dùng quá sớm. |
| Session lifecycle | Rotation, idle/absolute timeout, revoke | Session/token cũ có thể tồn tại sau thay đổi bảo mật. |
| Token lifecycle | Rotation, reuse detection, revoke propagation | Chưa đối soát đầy đủ token family và descendants. |
| Monitoring | Event correlation và risk detection | Tín hiệu được ghi nhưng không alert kịp thời. |
| Support recovery | Independent proof, dual control, audit | Cần xác minh không có support override yếu. |

Đây là các gap giả định để nhóm kiểm chứng, không phải kết luận mặc định. Root cause cuối cùng chỉ được chốt sau khi đối chiếu policy, implementation, event và interview.

## 12. Remediation kỹ thuật

### 12.1. Password và login abuse

- Dùng password hashing chuyên dụng với salt riêng và cost được benchmark.
- Kiểm tra password đã xuất hiện trong danh sách bị lộ theo privacy-safe design.
- Rate limit theo account, client và nguồn; không chỉ dựa vào IP.
- Phát hiện credential stuffing/password spraying qua correlation.
- Hỗ trợ password manager và passkey; không chặn paste.
- Thông báo password reset qua kênh đã xác minh.

### 12.2. MFA chống fatigue

- Giới hạn challenge theo account/device/time window.
- Dùng number matching hoặc transaction details khi phù hợp.
- Có cooldown sau nhiều deny/timeout.
- Phân biệt issued, delivered, denied, timeout và approved event.
- Không cho approval áp dụng sang transaction khác.
- Thông báo khi có nhiều challenge không mong muốn.
- Cung cấp passkey/security key làm factor chống phishing khi khả thi.

### 12.3. Bảo vệ hành động sau login

Các hành động sau cần step-up phù hợp:
- Thay password hoặc recovery contact.
- Thêm/gỡ passkey, TOTP, push factor hoặc security key.
- Liên kết/gỡ external identity.
- Tạo API key hoặc token grant.
- Thay đổi role, payout/payment hoặc quyền lớp học.
- Tắt MFA hoặc thay authentication policy.

Step-up phải gắn với action, subject, transaction, challenge, client/origin và thời hạn. Không cho một lần xác thực cũ được tái sử dụng vô thời hạn.

### 12.4. Session và token

- Rotate session ID sau login và privilege change.
- Revoke session khi password, MFA hoặc recovery factor thay đổi theo policy.
- Refresh token rotation có token family và reuse detection.
- Single-flight refresh ở mobile để tránh race.
- Xử lý timeout mơ hồ theo contract, không blind-retry token cũ.
- Có revocation propagation SLA và test đa region.
- Không log raw cookie, access token hoặc refresh token.
- Với API nhạy cảm, xác minh audience, scope, issuer, expiry và current authorization.

### 12.5. Identity linking

- Chỉ link identity từ session đã step-up.
- Xác minh issuer và subject theo OIDC.
- Không tự động link chỉ vì email trùng.
- Yêu cầu user confirmation về account/provider sẽ liên kết.
- Có re-authentication với account hiện tại và proof từ provider mới.
- Thông báo qua kênh đã xác minh trước đó.
- Ghi audit actor, subject, issuer reference và outcome.
- Có unlink/revoke flow và kiểm thử account collision.

## 13. Remediation UX và vận hành

### 13.1. Người dùng cần nhìn thấy điều gì?

Trang Security nên hiển thị:
- Session/device đang hoạt động và lần sử dụng gần nhất.
- Authenticator/passkey đã đăng ký.
- External identity provider đang liên kết.
- Recovery contact và trạng thái xác minh.
- Hành động gần đây có ý nghĩa bảo mật.
- Nút revoke/logout theo phạm vi dễ hiểu.
- Hướng dẫn khi nhận push challenge không do mình khởi tạo.

Thông báo cần cụ thể nhưng không tiết lộ bí mật. Ví dụ: “Một passkey mới đã được thêm vào tài khoản của bạn. Nếu bạn không thực hiện, hãy mở trang Security từ ứng dụng hoặc website chính thức để thu hồi và liên hệ hỗ trợ.” Không nhúng token hoặc session ID vào link notification.

### 13.2. Support workflow

- Support không yêu cầu password, OTP, recovery code hoặc private key.
- Xác minh người dùng qua quy trình độc lập.
- Không dùng recovery email vừa đổi làm kênh xác minh duy nhất.
- Yêu cầu dual approval cho các override có tác động lớn.
- Mọi hành động support phải có actor, subject, reason, approval và ticket reference.
- Không cho support đọc raw credential.
- Có escalation cho account đặc quyền và tenant admin.

### 13.3. Monitoring

Detection rule có thể kết hợp:
- Login failure burst rồi success từ context mới.
- Nhiều push challenge deny/timeout rồi một approve.
- Recovery contact change ngay sau login mới.
- Identity link hoặc passkey enrollment sau MFA fatigue signal.
- Token refresh hoặc session creation sau các thay đổi trên.
- API download/read bất thường ngay sau enrollment.
- Account có nhiều thay đổi security trong một cửa sổ ngắn.

Mỗi alert cần confidence, severity, owner và runbook. Không tự động kết luận ATO chỉ từ một IP hoặc geolocation khác.

## 14. Kế hoạch kiểm thử sau remediation

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| ATO-01 | Password bị thử nhiều lần trên một account | Rate limit và event failure được ghi nhận. |
| ATO-02 | Password spraying trên nhiều account | Detection correlation phát hiện pattern đa account. |
| ATO-03 | Login mới rồi nhiều push challenge | Cooldown/rate limit và cảnh báo được kích hoạt. |
| ATO-04 | Push approve không đúng transaction | MFA service từ chối. |
| ATO-05 | Password đúng nhưng MFA chưa hoàn tất | Không tạo authenticated session. |
| ATO-06 | Session cũ thêm passkey không có step-up | Enrollment bị từ chối. |
| ATO-07 | Step-up proof dùng lại cho transaction khác | Bị từ chối do transaction binding/one-time challenge. |
| ATO-08 | Recovery email đổi từ session rủi ro cao | Yêu cầu step-up/cooldown và thông báo old channel. |
| ATO-09 | Identity link dựa trên email trùng | Không tự động link; yêu cầu proof hai phía. |
| ATO-10 | Passkey response có origin/RP ID sai | Server từ chối và không lưu credential. |
| ATO-11 | Server commit enrollment nhưng response bị mất | Client kiểm tra transaction state; không tạo credential trùng. |
| ATO-12 | Refresh token cũ được reuse | Token family bị revoke theo policy và alert phát ra. |
| ATO-13 | Password thay đổi | Session/token liên quan bị revoke theo policy. |
| ATO-14 | Recovery factor bị thay | Session review và notification được kích hoạt. |
| ATO-15 | Logout/revoke ở region A | Region B từ chối trong revocation SLA. |
| ATO-16 | Raw token xuất hiện trong log | Security test thất bại; redaction phải chặn tại nguồn. |
| ATO-17 | Support agent tự reset MFA | Bị chặn nếu thiếu approval/dual control. |
| ATO-18 | Recovery dùng email vừa bị thay | Không đủ proof để khôi phục account. |
| ATO-19 | Account recovery hoàn tất | Credential inventory, session inventory và notification được đối soát. |
| ATO-20 | API truy cập sau revoke | Token/session cũ bị từ chối theo SLA. |
| ATO-21 | Account có role giảng viên | Authorization kiểm tra resource/tenant, không chỉ login success. |
| ATO-22 | Alert do IP thay đổi đơn lẻ | Chỉ tăng risk signal; không tự động kết luận ATO. |
| ATO-23 | Nhiều thay đổi security liên tiếp | Correlation alert và step-up được kích hoạt. |
| ATO-24 | Audit pipeline gián đoạn | Critical event được buffer hoặc action nhạy cảm bị chặn theo policy. |

### 14.1. Kiểm thử bằng chứng sau containment

Một incident test chỉ pass khi chứng minh được:
- Session reference bị revoke không còn được chấp nhận.
- Refresh token family và descendants bị revoke.
- Passkey/identity link trái phép không còn đăng nhập được.
- Recovery contact chưa xác minh không thể reset account.
- Các region/resource server tuân thủ revocation SLA.
- Audit timeline đầy đủ, không có raw secret.
- Người dùng hợp pháp khôi phục được quyền truy cập bằng factor đáng tin.
- Các hành động Course API sau thời điểm revoke bị từ chối.

## 15. Incident response runbook

### 15.1. Detect và declare

- Xác nhận report qua kênh hỗ trợ đã xác minh.
- Mở incident ID và phân công incident commander.
- Bảo toàn authentication, token, session, recovery và API audit.
- Xác định account, tenant, role và dữ liệu nhạy cảm.
- Tách facts khỏi hypotheses.

### 15.2. Contain

- Restrict account và ngăn security settings thay đổi thêm.
- Revoke session/token/factor/link nghi ngờ.
- Chặn API access nhạy cảm theo policy.
- Xác minh propagation trên mọi region.
- Không xóa evidence hoặc raw event nguồn.

### 15.3. Eradicate và recover

- Xác định nguồn credential exposure nếu có thể.
- Reset password sau proofing.
- Re-enroll factor trên thiết bị đáng tin.
- Khôi phục recovery contact.
- Kiểm tra identity links và device inventory.
- Thông báo người dùng và tenant owner khi cần.
- Kiểm tra quyền/resource và các thay đổi nghiệp vụ.

### 15.4. Post-incident

- Lập timeline và root cause đã được chứng minh.
- Xác định data impact và nghĩa vụ thông báo.
- Review detection gap và response time.
- Tạo remediation owner/deadline.
- Kiểm thử regression và tabletop.
- Cập nhật runbook, support script và user guidance.
- Theo dõi action item đến khi có bằng chứng hoàn thành.

## 16. Bài tập nhóm: quyết định trong 30 phút đầu

Chia nhóm thành Incident Commander, Identity Engineer, Security Analyst, Support Lead và Product Owner. Mỗi nhóm nhận cùng dữ kiện nhưng chịu trách nhiệm quyết định khác nhau.

### Tình huống A — MFA fatigue

Nạn nhân nói đã nhận 12 push notification và bấm Approve một lần vì tưởng là đăng nhập của mình.

- Bạn cần thu thập bằng chứng gì?
- Có nên revoke tất cả session ngay không?
- Có nên khóa push factor hay giữ nó để hỗ trợ recovery?
- Làm sao phân biệt approve của người dùng với notification bị điều khiển?

### Tình huống B — Recovery email đã đổi

Email mới được thêm trước khi người dùng báo cáo 40 phút. Notification đã gửi tới email cũ nhưng chưa biết người dùng có đọc.

- Email cũ có còn được tin cậy không?
- Có thể dùng email cũ làm một phần proof không?
- Có cần cooling-off period?
- Ai phê duyệt khôi phục contact?

### Tình huống C — Passkey mới được enroll

Passkey mới active nhưng provider có thể đồng bộ credential. Server không biết chính xác bản sao đang nằm trên thiết bị nào.

- Bạn có thể revoke gì ở phía dịch vụ?
- Bạn không thể khẳng định điều gì về bản sao trong provider?
- Người dùng cần được hướng dẫn ra sao?
- Có cần revoke toàn bộ passkey hay chỉ credential reference mới?

### Tình huống D — API download

Course API ghi nhận tài liệu của ba lớp được tải. Storage egress log không đầy đủ.

- Có thể kết luận exfiltration không?
- Cần bảo toàn evidence nào?
- Có cần thông báo tenant ngay hay chờ xác minh thêm?
- Làm sao ghi nhận giới hạn của kết luận?

### Tình huống E — Refresh token timeout

Trong lúc containment, token endpoint timeout sau một request refresh có thể đã commit rotation.

- Có nên retry token cũ?
- Làm sao xác định token family state?
- Khi không thể biết kết quả, hành động an toàn nào phù hợp?
- Làm sao tránh mobile app tạo retry storm?

## 17. Câu hỏi tự đánh giá

1. Account takeover khác một lần login thất bại như thế nào?
2. Vì sao password verification success không đủ chứng minh user hợp pháp?
3. MFA fatigue có thể dẫn đến ATO ra sao?
4. Những event nào giúp dựng timeline của case?
5. Dữ kiện nào đã được xác nhận và dữ kiện nào vẫn là giả thuyết?
6. Vì sao recovery email change và passkey enrollment là hành động nhạy cảm?
7. Step-up cần gắn với transaction/account bằng cách nào?
8. Vì sao chỉ đổi password không đủ containment?
9. Revoke session, refresh token, passkey và identity link khác nhau ra sao?
10. Vì sao recovery không nên dùng contact vừa bị thay làm proof duy nhất?
11. Khi nào có thể kết luận dữ liệu đã bị exfiltrate?
12. Làm thế nào xác định phạm vi tenant/account bị ảnh hưởng?
13. Tại sao IP/geolocation không phải bằng chứng danh tính?
14. Làm sao kiểm tra revocation propagation đa region?
15. Những event nào không được ghi raw credential?
16. Làm sao bảo đảm support-assisted recovery không trở thành bypass?
17. Một detection rule tốt cần severity, confidence, owner và runbook ra sao?
18. Làm thế nào chứng minh remediation đã chặn lại đúng attack path?

## 18. Tiêu chí đánh giá case study

| Tiêu chí | Trọng số gợi ý | Bằng chứng đạt |
| --- | ---: | --- |
| Timeline và evidence quality | 15% | Timeline có nguồn, timestamp, correlation; facts tách hypotheses. |
| Attack path và trust boundary | 15% | Giải thích được credential, MFA, session, identity link và persistence. |
| Containment | 15% | Revoke đúng phạm vi, không bỏ sót token/factor/link. |
| Recovery | 15% | Proof độc lập, assurance phù hợp, tránh recovery takeover. |
| Root cause | 10% | Root cause dựa bằng chứng; contributing factors có owner. |
| Remediation | 10% | Controls cụ thể cho password, MFA, session, token và enrollment. |
| Monitoring/detection | 10% | Event taxonomy, correlation, severity và runbook. |
| Verification | 10% | Test chứng minh attack path bị chặn và revoke propagation đúng. |

Điểm số chỉ là gợi ý. Một phương án containment có thể không đạt nếu bỏ qua một đường persistence quan trọng, dù các phần khác có điểm cao.

## 19. Các bài học chính

- ATO là sự cố của toàn bộ authentication lifecycle, không chỉ password.
- MFA có thể bị lạm dụng qua fatigue, enrollment takeover hoặc recovery weakness.
- Session hợp lệ vẫn có thể thuộc về attacker nếu authentication trước đó bị chiếm.
- Recovery email, identity link và passkey mới có thể tạo persistence sau lần login đầu.
- Step-up cần đủ mới, đúng factor, gắn với transaction và không thể replay.
- Revoke phải bao phủ session, token family, factor, identity link và device binding theo phạm vi.
- Recovery phải dựa trên factor/kênh độc lập còn tin cậy.
- Event cần đủ để điều tra nhưng không được chứa raw credential.
- IP, geolocation và fingerprint là risk signals, không phải bằng chứng danh tính.
- Remediation phải có test chứng minh mọi đường truy cập cũ đã bị đóng.
- UX thông báo, danh sách thiết bị và support workflow là một phần của security control.
- Root cause phải được chứng minh; không biến giả thuyết hợp lý thành kết luận.

## 20. Tài liệu tham khảo và hướng đọc tiếp

- **NIST SP 800-63B — Digital Identity Guidelines:** authenticator, authentication assurance, lifecycle và recovery.
- **OWASP Authentication Cheat Sheet:** password, MFA, re-authentication và account controls.
- **OWASP Multifactor Authentication Cheat Sheet:** MFA enrollment, recovery và factor management.
- **OWASP Forgot Password Cheat Sheet:** recovery proof, reset token và account takeover prevention.
- **OWASP Session Management Cheat Sheet:** session rotation, expiry và invalidation.
- **OWASP OAuth 2.0 Cheat Sheet:** token handling, redirect validation và refresh token protection.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** bảo vệ OAuth flow.
- **OpenID Connect Core:** issuer, subject, nonce và identity validation.
- **WebAuthn specification:** passkey registration và assertion verification.
- **MITRE ATT&CK — Valid Accounts:** mô hình hóa hành vi lạm dụng tài khoản hợp lệ trong điều tra.
- **NIST SP 800-61 — Incident Response:** chuẩn bị, phát hiện, containment, recovery và lessons learned.

Khi áp dụng vào hệ thống thật, cần đối chiếu tiêu chuẩn hiện hành, kiến trúc và policy của tổ chức. Case này là mẫu thực hành; kết luận incident thực tế phải dựa vào evidence đã bảo toàn và được kiểm chứng.

**Kết luận:** Một vụ account takeover thường xảy ra khi nhiều lớp kiểm soát liên tiếp bị vượt qua: credential bị lộ, MFA bị lạm dụng, session được thiết lập và các yếu tố duy trì quyền truy cập bị thay đổi. Điều tra tốt dựng timeline từ event có cấu trúc, tách facts khỏi hypotheses và xác định đúng trust boundary. Containment phải revoke toàn bộ session/token/factor/link liên quan; recovery cần proof độc lập; remediation phải được xác minh bằng test để chứng minh attacker không thể tiếp tục truy cập qua đường persistence cũ.
