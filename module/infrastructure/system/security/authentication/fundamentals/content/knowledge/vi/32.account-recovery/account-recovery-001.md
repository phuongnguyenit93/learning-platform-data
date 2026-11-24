# Luồng recovery — Khôi phục quyền truy cập tài khoản an toàn

## 1. Account recovery là gì?

**Account recovery** (khôi phục tài khoản) là quy trình giúp người dùng lấy lại quyền truy cập khi họ không thể xác thực bằng các credential hoặc authenticator đang có. Nguyên nhân thường gặp gồm quên mật khẩu, mất điện thoại, mất passkey hoặc khóa bảo mật, mất quyền truy cập email/số điện thoại, thiết bị bị hỏng, tài khoản bị chiếm hoặc phương thức MFA không còn khả dụng.

Ví dụ: một nhân viên làm mất điện thoại có ứng dụng authenticator và không còn đăng nhập được vào cổng công ty. Hệ thống cần xác minh người yêu cầu thực sự là chủ tài khoản, thu hồi phương thức đã mất, cấp quyền đăng ký authenticator mới và bảo vệ các session/token cũ. Nếu chỉ gửi một liên kết đặt lại mật khẩu tới email mà attacker đã chiếm, quy trình recovery sẽ trao tài khoản cho attacker.

Trong chương **Account recovery** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, luồng recovery kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần mô hình hóa ranh giới tin cậy, chọn bằng chứng recovery phù hợp với mức rủi ro, phòng chống phishing, replay, social engineering và lạm dụng đăng nhập.

**Recovery là một quy trình xác thực và thay đổi bảo mật có rủi ro cao.** Người dùng chưa thể đăng nhập không có nghĩa hệ thống được phép hạ thấp tiêu chuẩn xác minh. Recovery phải chứng minh quyền kiểm soát tài khoản bằng bằng chứng phù hợp, giới hạn quyền trong thời gian khôi phục và kết thúc bằng việc thiết lập lại credential/session theo policy.

## 2. Phân biệt account recovery với các quy trình gần nhau

| Quy trình | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Password reset** | Đặt mật khẩu mới khi người dùng quên hoặc mật khẩu bị thu hồi. | Dùng recovery token để đặt mật khẩu mới. |
| **MFA/factor recovery** | Khôi phục hoặc thay thế authenticator đã mất. | Thu hồi điện thoại cũ và đăng ký passkey mới. |
| **Account recovery** | Khôi phục quyền kiểm soát tổng thể của tài khoản, có thể gồm password, MFA, email và session. | Người dùng mất mọi yếu tố đăng nhập và cần xác minh danh tính. |
| **Step-up recovery** | Giúp hoàn tất một yêu cầu xác thực nâng cấp khi yếu tố cần dùng không khả dụng. | Dùng khóa bảo mật dự phòng trước thao tác nhạy cảm. |
| **Account unlock** | Gỡ trạng thái khóa/tạm giữ theo policy sau khi xác minh. | Gỡ risk hold sau khi điều tra đăng nhập bất thường. |
| **Identity proofing** | Xác minh danh tính theo mức bảo đảm và quy trình được xác định. | Đối chiếu hồ sơ nhân sự hoặc quy trình xác minh trực tiếp. |

Một password reset thành công không nhất thiết có nghĩa toàn bộ account recovery đã hoàn tất. Nếu attacker đã thêm passkey, đổi email khôi phục hoặc tạo API key, chỉ đổi mật khẩu có thể không lấy lại được quyền kiểm soát. Recovery cần kiểm tra toàn bộ credential và trạng thái bảo mật liên quan.

## 3. Mục tiêu và nguyên tắc thiết kế

Một luồng recovery tốt cần đạt các mục tiêu:

1. **Xác minh đúng chủ thể:** người yêu cầu có bằng chứng đủ tin cậy để thay đổi tài khoản.
2. **Giới hạn quyền:** recovery transaction chỉ cho phép hành động đã được phê duyệt, không tạo một session quản trị toàn quyền.
3. **Chống replay:** token, mã xác minh và challenge chỉ được dùng một lần, có thời hạn và gắn đúng mục đích.
4. **Không tiết lộ tài khoản:** phản hồi công khai không giúp attacker dò tài khoản tồn tại hay trạng thái credential.
5. **Khôi phục credential có kiểm soát:** credential mới chỉ active sau khi được xác minh.
6. **Thu hồi đúng tài sản:** yếu tố bị mất, session và token liên quan được xử lý theo incident policy.
7. **Thông báo độc lập:** chủ tài khoản có thể phát hiện recovery trái phép qua kênh đã xác minh trước đó.
8. **Có khả năng audit:** ghi nhận actor, thời điểm, bằng chứng ở mức metadata, quyết định và thay đổi đã thực hiện.

Không có một phương thức recovery phù hợp cho mọi tài khoản. Bằng chứng cần thiết phụ thuộc mức nhạy cảm của tài khoản, hậu quả nếu attacker thành công, loại credential bị mất và các nguồn xác minh độc lập còn lại.

## 4. Ranh giới tin cậy và các thành phần

Recovery có thể liên quan người dùng, browser/app, recovery service, IdP, kho credential, kênh thông báo và helpdesk:

~~~mermaid
flowchart LR
    U["Người dùng"]
    C["Browser / ứng dụng"]
    R["Recovery service<br/>policy + transaction"]
    I["Identity provider<br/>xác minh credential"]
    D[("Account / credential store")]
    N["Notification service"]
    H["Helpdesk / approver"]
    A[("Audit / risk engine")]
    U <--> C
    C <--> R
    R <--> I
    R <--> D
    R --> N
    H -->|"Quy trình có kiểm soát"| R
    R --> A
    N --> U
~~~

**Người dùng/client** khởi tạo yêu cầu và gửi bằng chứng. Client không được tự xác định account ID, trạng thái recovery hoặc kết quả xác minh.

**Recovery service** tạo transaction, áp dụng policy, xác minh bằng chứng và điều phối thay đổi. Nó phải lấy principal từ dữ liệu tin cậy, không từ tham số do client tự khai.

**IdP/credential service** xác minh credential, quản lý authenticator và phát hành context đã kiểm chứng.

**Credential store** lưu trạng thái mật khẩu, passkey, TOTP, certificate, recovery code và các yếu tố khác. Thay đổi phải có kiểm soát nguyên tử.

**Notification service** gửi thông báo tới kênh đã xác minh trước đó. Kênh vừa được thay đổi trong recovery không được mặc định là kênh đáng tin để cảnh báo chủ tài khoản.

**Helpdesk/approver** chỉ tham gia khi policy yêu cầu. Nhân viên hỗ trợ không được tự bỏ qua xác minh hoặc yêu cầu người dùng đọc mật khẩu, OTP, recovery code hay private key.

## 5. Phân loại trường hợp recovery

Trước khi chọn luồng, hệ thống cần phân loại điều gì đã mất và những phương thức nào còn kiểm soát được:

| Trường hợp | Phương thức còn lại | Hướng recovery thường dùng |
| --- | --- | --- |
| Quên mật khẩu | Passkey hoặc MFA còn hoạt động | Xác thực bằng yếu tố còn lại rồi đặt mật khẩu mới. |
| Mất điện thoại TOTP | Passkey/khóa bảo mật dự phòng hoặc recovery code | Xác minh bằng phương thức dự phòng, thu hồi binding cũ và đăng ký lại. |
| Mất passkey trên một thiết bị | Passkey khác hoặc authenticator dự phòng | Dùng credential còn active, xác nhận thiết bị mất và thu hồi credential cũ. |
| Mất mọi yếu tố MFA | Recovery code hoặc helpdesk/identity proofing | Recovery tăng cường, có thể có dual control và thời gian chờ. |
| Mất quyền truy cập email | Passkey/MFA hoặc kênh độc lập | Xác minh qua phương thức khác; không gửi recovery link tới email không còn kiểm soát. |
| Tài khoản bị chiếm | Có thể không còn yếu tố nào đáng tin | Incident recovery: khóa tạm, thu hồi session/token, xác minh độc lập và rà soát thay đổi. |
| Tài khoản bị khóa do risk policy | Credential còn nhưng bị tạm giữ | Xác minh hoạt động, xử lý risk hold và mở khóa có audit. |
| Tài khoản tổ chức | Quản trị danh tính/nhân sự và thiết bị được quản lý | Quy trình nội bộ có phê duyệt, tách người yêu cầu và người duyệt. |

Không để người dùng tự chọn phương thức yếu nhất chỉ vì tiện. Recovery policy quyết định phương thức nào được chấp nhận cho từng loại tài khoản và hành động.

## 6. Vòng đời recovery transaction

Một recovery transaction nên có trạng thái rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> Requested
    Requested --> PendingVerification: Tạo transaction
    PendingVerification --> Verified: Bằng chứng đạt
    PendingVerification --> Rejected: Bằng chứng không đạt
    PendingVerification --> Expired: Hết hạn
    PendingVerification --> Cancelled: Hủy
    Verified --> RecoveryInProgress: Cho phép thay đổi được duyệt
    RecoveryInProgress --> Completed: Commit credential/session
    RecoveryInProgress --> Failed: Lỗi cần xử lý
    Completed --> [*]
    Rejected --> [*]
    Expired --> [*]
    Cancelled --> [*]
    Failed --> PendingVerification: Bắt đầu lại theo policy
~~~

Các trạng thái có ý nghĩa:

- **Requested:** nhận yêu cầu, chưa chứng minh quyền kiểm soát tài khoản.
- **PendingVerification:** đang chờ mã, credential, approval hoặc identity proofing.
- **Verified:** bằng chứng đã đạt policy cho một mục đích cụ thể; chưa mặc nhiên cấp session đầy đủ.
- **RecoveryInProgress:** đang thay thế/reset credential hoặc thu hồi yếu tố.
- **Completed:** các thay đổi được phép đã commit và người dùng nhận hướng dẫn tiếp theo.
- **Rejected/Expired/Cancelled:** transaction đóng; token/challenge không được tái sử dụng.
- **Failed:** lỗi xử lý; phải xác định có thể retry an toàn hay cần transaction mới.

### Ràng buộc transaction

Mỗi transaction cần được gắn với:

- Principal/account và tenant đã xác định từ nguồn tin cậy.
- Mục đích cụ thể: reset password, replace factor, recover account hoặc unlock.
- Session hoặc context khởi tạo nếu có.
- Bằng chứng được yêu cầu và mức assurance tối thiểu.
- Transaction ID ngẫu nhiên, challenge/token verifier và thời hạn.
- Attempt counter, resend counter và giới hạn nguồn.
- Trạng thái hiện tại và policy version.
- Kênh thông báo đã xác minh trước recovery.

Một token reset mật khẩu không được dùng để thay email, thêm passkey hoặc tạo API key nếu transaction không cho phép. Purpose binding ngăn recovery token trở thành credential tổng quát.

## 7. Khởi tạo recovery mà không tiết lộ tài khoản

Trang recovery công khai không nên tiết lộ tài khoản có tồn tại hay không. Ví dụ, người dùng nhập email hoặc username; hệ thống trả thông báo chung:

> Nếu thông tin này liên kết với tài khoản đủ điều kiện, hướng dẫn khôi phục sẽ được gửi qua kênh đã xác minh. Hãy kiểm tra hộp thư hoặc phương thức liên hệ đã đăng ký.

Không trả các thông báo khác nhau như “email không tồn tại”, “tài khoản chưa bật MFA” hoặc “địa chỉ này đã bị khóa” trước khi người dùng được xác minh phù hợp.

### Kiểm soát enumeration

- Đồng nhất status code và nội dung phản hồi cho account tồn tại/không tồn tại khi phù hợp.
- Tránh khác biệt thời gian quá rõ giữa các nhánh.
- Rate limit theo identifier đã chuẩn hóa, nguồn và toàn hệ thống.
- Không gửi OTP/email quá nhiều lần; có cooldown và chống abuse.
- Không hiển thị số điện thoại/email đầy đủ; nếu cần, chỉ hiển thị phần che sau khi đã qua bước xác minh phù hợp.
- Không để endpoint kiểm tra username, resend code hoặc recovery status trở thành API enumeration.

Thông báo chung không có nghĩa bỏ qua thông tin hữu ích. Sau khi người dùng chứng minh được quyền kiểm soát kênh hoặc credential, hệ thống có thể cung cấp hướng dẫn cụ thể hơn.

## 8. Chọn bằng chứng recovery

Bằng chứng cần độc lập với yếu tố đã mất và phải đủ mạnh cho hậu quả của hành động:

| Bằng chứng | Giá trị | Hạn chế |
| --- | --- | --- |
| Passkey/khóa bảo mật dự phòng | Bằng chứng mật mã gắn với RP/origin. | Chỉ hữu ích nếu credential còn active và người dùng còn kiểm soát thiết bị. |
| TOTP authenticator khác | Chứng minh kiểm soát secret đã đăng ký. | Có thể bị phishing/replay trong cửa sổ thời gian nếu thiếu kiểm soát. |
| Recovery code | Bí mật dự phòng được cấp trước, thường dùng một lần. | Bearer secret có thể bị sao chép hoặc lưu không an toàn. |
| Email đã xác minh trước đó | Chứng minh quyền truy cập hộp thư tại thời điểm xác minh. | Hộp thư có thể bị chiếm hoặc dùng chung với quy trình khác. |
| Số điện thoại/SMS | Chứng minh khả năng nhận mã qua số hiện tại. | SIM swap, chuyển tiếp và phishing; không phải bằng chứng mạnh chống phishing. |
| Thiết bị được quản lý | Có thể cung cấp device identity/posture theo policy. | Thiết bị hợp lệ không tự chứng minh người cầm máy là chủ tài khoản. |
| Helpdesk/identity proofing | Có thể xác minh qua nguồn độc lập và quy trình tổ chức. | Tốn thời gian, dễ bị social engineering hoặc insider abuse nếu kiểm soát yếu. |

Không cộng cơ học hai kênh yếu thành một bằng chứng mạnh. Ví dụ email và SMS có thể cùng bị chiếm thông qua một thiết bị hoặc một tài khoản nhà mạng. Hãy đánh giá sự độc lập thực tế và mức bảo đảm của từng yếu tố.

## 9. Recovery bằng liên kết hoặc mã dùng một lần

Với password reset hoặc xác minh kênh, hệ thống có thể cấp token ngẫu nhiên:

- Tạo token bằng CSPRNG, đủ entropy.
- Lưu verifier/hash của token thay vì token bản rõ nếu kiến trúc cho phép.
- Gắn token với account, purpose, transaction và expiry.
- Chỉ cho phép dùng một lần; consume nguyên tử.
- Không đặt token vào log, analytics hoặc referrer.
- Không cho phép token đổi account hoặc purpose qua tham số client.
- Thu hồi token khi transaction bị hủy, thay thế hoặc phát hiện rủi ro.

Liên kết recovery thường được gửi qua kênh đã xác minh trước đó. Trang nhận token phải dùng HTTPS, hạn chế tài nguyên bên thứ ba, đặt Referrer-Policy phù hợp và không tải script không cần thiết có thể đọc URL chứa token.

### Tránh token bị tiêu thụ bởi link scanner

Một số hệ thống email tự động mở liên kết để kiểm tra an toàn. Nếu GET request lập tức tiêu thụ recovery token và đổi mật khẩu, link scanner có thể làm người dùng không dùng được liên kết.

Thiết kế tốt hơn:

1. GET chỉ mở trang xác nhận và kiểm tra sơ bộ, không thực hiện thay đổi bảo mật.
2. Người dùng chủ động xác nhận qua thao tác POST.
3. Server xác minh token, transaction và CSRF binding rồi consume token nguyên tử.
4. Trang không đưa token vào analytics/referrer hoặc tài nguyên bên thứ ba.

Không dùng GET để thực hiện hành động thay đổi trạng thái.

## 10. Password recovery và đặt lại mật khẩu

Một luồng reset mật khẩu có thể gồm:

1. Người dùng gửi yêu cầu recovery.
2. Server trả phản hồi chung và kiểm tra rate limit.
3. Nếu account đủ điều kiện, server tạo token ngắn hạn gắn với account và purpose.
4. Gửi liên kết tới kênh đã xác minh trước đó.
5. Người dùng mở liên kết và chủ động xác nhận trên trang HTTPS.
6. Server xác minh token chưa hết hạn/chưa dùng, transaction còn hợp lệ và yêu cầu CSRF phù hợp.
7. Người dùng đặt mật khẩu mới theo password policy.
8. Server hash mật khẩu bằng thuật toán password hashing chuyên dụng và commit thay đổi.
9. Thu hồi token reset, session và refresh token theo policy; thông báo thay đổi.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant R as Recovery service
    participant D as Account store
    participant N as Notification
    U->>B: Yêu cầu đặt lại mật khẩu
    B->>R: Identifier + request metadata
    R->>R: Rate limit và phản hồi chung
    R->>D: Kiểm tra eligibility
    R->>R: Tạo token purpose-bound
    R->>N: Gửi link tới kênh đã xác minh
    N-->>U: Hướng dẫn recovery
    U->>B: Mở link và xác nhận
    B->>R: POST token + transaction + CSRF
    R->>R: Verify và consume token nguyên tử
    R->>D: Lưu password hash mới
    R->>D: Thu hồi trạng thái cũ theo policy
    R-->>B: Hoàn tất và hướng dẫn đăng nhập
~~~

### Password policy

- Cho phép mật khẩu dài và passphrase; tránh giới hạn độ dài quá thấp.
- Kiểm tra mật khẩu phổ biến hoặc đã bị lộ bằng cơ chế bảo vệ quyền riêng tư.
- Dùng Argon2id, scrypt hoặc bcrypt với cấu hình phù hợp và salt riêng.
- Không dùng MD5/SHA-256 trực tiếp để lưu mật khẩu.
- Không gửi mật khẩu mới qua email hoặc tin nhắn.
- Không log password hoặc password hash trong hệ thống telemetry.

Không bắt buộc đổi mật khẩu định kỳ vô lý nếu không có dấu hiệu lộ lọt hoặc yêu cầu policy. Sau recovery, người dùng nên được hướng dẫn dùng password manager và bật passkey/MFA.

## 11. MFA và passkey recovery

### Mất TOTP authenticator

- Dùng passkey/khóa bảo mật dự phòng hoặc recovery code đã cấp trước.
- Xác minh bằng chứng, thu hồi TOTP binding cũ và đăng ký secret mới.
- Secret mới chỉ active sau khi người dùng nhập mã hợp lệ.
- Không gửi lại secret TOTP cũ qua email hoặc helpdesk.

### Mất passkey/khóa bảo mật

- Xác minh bằng passkey khác hoặc recovery flow được phê duyệt.
- Kiểm tra credential ID và trạng thái ở server.
- Thu hồi credential trên thiết bị mất sau khi xác minh quyền.
- Đăng ký passkey mới bằng WebAuthn registration ceremony.
- Gửi thông báo qua kênh đã xác minh trước đó.

### Mất push authenticator

- Xác minh bằng yếu tố độc lập đã đăng ký.
- Thu hồi device binding cũ và registration key/token liên quan.
- Đăng ký thiết bị mới qua challenge có thời hạn.
- Giới hạn push và tránh phê duyệt chỉ vì người dùng đang ở trong session cũ.

### Khôi phục nhiều yếu tố

Nếu người dùng mất đồng thời mật khẩu, email và MFA, các bằng chứng này không còn độc lập. Có thể cần identity proofing hoặc quy trình tổ chức có phê duyệt. Không cho phép đặt lại lần lượt mọi yếu tố qua cùng một hộp thư đang bị nghi chiếm.

## 12. Identity proofing và recovery có helpdesk

Khi người dùng không còn yếu tố dự phòng, hệ thống có thể cần xác minh danh tính qua nguồn độc lập:

- Hồ sơ nhân sự hoặc hệ thống danh tính tổ chức đã được bảo vệ.
- Quản trị viên/manager xác nhận theo quy trình có phân tách nhiệm vụ.
- Thiết bị doanh nghiệp đã provision và được quản lý.
- Quy trình xác minh trực tiếp hoặc nhà cung cấp identity proofing được phê duyệt.
- Đối chiếu hồ sơ theo mức bảo đảm cần thiết và yêu cầu pháp lý.

Không mặc định giấy tờ tùy thân hoặc thông tin cá nhân dễ tra cứu là bằng chứng đủ mạnh. Dữ liệu cá nhân có thể bị lộ; quy trình cần xác minh tính xác thực, chống giả mạo và có đánh giá privacy.

### Helpdesk controls

- Xác minh yêu cầu qua kênh hỗ trợ chính thức.
- Không hỏi password, OTP, recovery code hoặc private key.
- Tách người khởi tạo và người phê duyệt với thao tác rủi ro cao (dual control).
- Cấp recovery invitation/token có TTL ngắn, purpose/account-bound và one-time use.
- Giới hạn quyền nhân viên hỗ trợ; không cho phép xem secret hoặc tự tạo session của người dùng.
- Ghi audit actor, approver, lý do, thời gian và kết quả.
- Thông báo cho chủ tài khoản qua kênh độc lập đã xác minh.

Nếu không đủ bằng chứng, helpdesk phải từ chối hoặc chuyển cấp xác minh. Áp lực công việc, chức danh người gọi hoặc thông tin cá nhân không thay thế quy trình.

## 13. Thời gian chờ và thông báo sau recovery

Một số thay đổi có rủi ro cao có thể cần thời gian chờ trước khi được dùng cho hành động nhạy cảm:

- Thêm passkey sau helpdesk recovery.
- Thay email/số điện thoại khôi phục.
- Tắt MFA hoặc thay đổi phương thức bảo vệ.
- Tạo credential quản trị hoặc API key.
- Chuyển tài khoản sang thiết bị mới khi các yếu tố cũ bị mất.

Trong thời gian chờ:

- Thông báo tới kênh đã xác minh trước recovery.
- Hiển thị loại thay đổi, thời gian và thiết bị ở mức không lộ bí mật.
- Cho phép chủ tài khoản báo cáo nếu không thực hiện yêu cầu.
- Có thể giới hạn giao dịch nhạy cảm hoặc thu hồi các session nghi bị chiếm.
- Không gửi token, QR, OTP, recovery code hoặc secret trong thông báo.

Thời gian chờ không thay thế xác minh danh tính. Nó là lớp giảm thiệt hại và tạo cơ hội phát hiện recovery trái phép. Thời hạn và ngoại lệ cần theo risk policy, không đặt một con số chung cho mọi tài khoản.

## 14. Session, token và credential sau recovery

Recovery phải xem xét toàn bộ tài sản có thể cho phép attacker tiếp tục truy cập:

| Tài sản | Hành động theo policy |
| --- | --- |
| Mật khẩu cũ | Thay password hash; từ chối credential cũ. |
| Passkey/TOTP/push bị mất | Thu hồi binding hoặc credential tương ứng. |
| Recovery token/code | Consume, revoke hoặc thay bộ mã; không cho replay. |
| Session đang hoạt động | Thu hồi session nghi bị chiếm hoặc toàn bộ session theo incident policy. |
| Refresh token family | Thu hồi nếu có khả năng token bị lộ hoặc gắn với session bị chiếm. |
| Access token | Dùng TTL ngắn, introspection/denylist hoặc cơ chế revoke nếu cần hiệu lực sớm. |
| API key/client credential | Kiểm tra credential do tài khoản tạo; thu hồi key không nhận diện hoặc không còn cần thiết. |
| Recovery transaction | Đóng, consume hoặc expire; không tái sử dụng challenge. |

Thu hồi mật khẩu hoặc một authenticator không tự động làm mọi session và access token đã phát hành mất hiệu lực. Credential, session và token có vòng đời riêng. Cần định nghĩa sự kiện nào làm thu hồi loại tài sản nào và đảm bảo mọi verifier áp dụng trạng thái mới.

### Session sau recovery

Một số hệ thống cho phép người dùng tạo session mới sau khi recovery hoàn tất. Session đó nên được tạo từ authentication event mới, có assurance phù hợp và ID mới. Không nâng session cũ thành authenticated chỉ vì recovery transaction chuyển verified.

Với sự cố nghiêm trọng, có thể thu hồi tất cả phiên và yêu cầu đăng nhập lại trên từng thiết bị. Người dùng cần được thông báo rõ, đồng thời có thể xem và thu hồi các phiên/credential còn lại.

## 15. Account linking và danh tính liên kết trong recovery

Một người có thể đăng nhập qua nhiều IdP hoặc có nhiều tài khoản liên kết. Recovery cần tránh nhầm danh tính:

- Dùng cặp issuer + subject đã xác minh làm định danh federation ổn định theo contract.
- Không liên kết tài khoản chỉ vì email giống nhau; email có thể thay đổi, tái cấp hoặc chưa được xác minh.
- Thay đổi/unlink IdP cần xác thực lại và audit.
- Không cho recovery token của tài khoản A liên kết credential của tài khoản B.
- Khi IdP bị xâm nhập hoặc tài khoản liên kết bị thu hồi, đánh giá các session và liên kết phụ thuộc.
- Với multi-tenant, xác minh membership và quyền trong đúng tenant.

Nếu người dùng mất quyền truy cập IdP bên ngoài, ứng dụng RP không nên tự tạo một danh tính mới cùng email rồi hợp nhất dữ liệu tự động. Cần quy trình liên kết/recovery có xác minh chủ thể và phê duyệt theo rủi ro.

## 16. Các tấn công nhắm vào account recovery

| Rủi ro | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Recovery phishing** | Trang giả lấy token, OTP hoặc recovery code. | Domain chính thức, purpose-bound token, thông báo và hướng dẫn không chia sẻ mã. |
| **Account enumeration** | Endpoint tiết lộ tài khoản tồn tại qua response hoặc timing. | Phản hồi chung, rate limit và kiểm tra side-channel. |
| **Email takeover** | Attacker chiếm hộp thư rồi reset mật khẩu/MFA. | Bằng chứng độc lập; không dùng email làm recovery duy nhất cho tài khoản assurance cao. |
| **SIM swap** | Attacker chiếm số điện thoại để nhận OTP. | Không phụ thuộc SMS duy nhất; step-up và thông báo kênh độc lập. |
| **Helpdesk social engineering** | Attacker giả danh nhân viên yêu cầu reset MFA. | Dual control, xác minh độc lập, least privilege và audit. |
| **Token replay** | Recovery link/token đã dùng được gửi lại. | TTL ngắn, one-time use và consume nguyên tử. |
| **Token leakage** | Token xuất hiện trong URL, log, Referer hoặc analytics. | Redaction, Referrer-Policy, không tải script bên thứ ba ở trang token. |
| **Recovery chaining** | Một kênh yếu được dùng để thay email, rồi email mới reset MFA. | Không cho kênh vừa đổi tự chứng minh tài khoản cũ; assurance floor và cooldown. |
| **Session hijacking** | Attacker dùng session bị chiếm để bắt đầu recovery. | Step-up, risk check, session binding và thông báo độc lập. |
| **Credential persistence** | Attacker đã thêm passkey/API key nhưng nạn nhân chỉ đổi mật khẩu. | Inventory credential, thu hồi yếu tố/key lạ và session/token liên quan. |
| **Race condition** | Hai request cùng consume token hoặc thay credential. | Atomic transaction, unique constraint và idempotency. |
| **Notification suppression** | Attacker đổi kênh thông báo trước recovery. | Gửi cảnh báo tới kênh cũ/độc lập và có thời gian phản đối. |
| **Insider abuse** | Nhân viên nội bộ tự ý recovery tài khoản. | Phân tách nhiệm vụ, audit bất biến và cảnh báo hành vi hỗ trợ bất thường. |

**Recovery chaining** đặc biệt nguy hiểm: attacker chiếm một kênh yếu, dùng nó thay kênh thứ hai, rồi dùng kênh thứ hai để thay mọi credential còn lại. Policy phải đánh giá sự độc lập của bằng chứng và lịch sử thay đổi, không chỉ xác minh từng bước riêng lẻ.

## 17. Mã giả: recovery transaction an toàn

Mã giả dưới đây minh họa nguyên tắc xử lý; không thay thế thư viện mật mã, identity proofing hoặc hệ thống giao dịch đã được kiểm thử:

~~~text
requestRecovery(identifier, purpose, requestContext):
    applyGlobalAndIdentifierRateLimits(identifier, requestContext)
    account = lookupAccountWithoutPublicDisclosure(identifier)

    if account is eligible:
        tx = createRandomTransaction(
            accountId = account.id,
            tenantId = account.tenantId,
            purpose = allowlistedPurpose(purpose),
            requiredAssurance = recoveryPolicy(account, purpose),
            expiresAt = shortExpiry(),
            status = "pending_verification"
        )
        token = generateHighEntropyOneTimeToken()
        storeTokenVerifierBoundToTransaction(token, tx)
        notifyPreviouslyVerifiedChannel(account, token)

    return genericPublicResponse()

completeRecovery(txId, token, evidence):
    tx = loadTransaction(txId)
    require tx.status == "pending_verification"
    require tx.notExpired
    require tokenMatchesTransactionAndPurpose(token, tx)
    require evidenceMeetsRecoveryPolicy(evidence, tx)
    require accountAndTenantStillEligible(tx)

    atomically:
        consumeTokenAndEvidence(tx, token, evidence)
        markTransaction(tx, "verified")
        applyOnlyApprovedCredentialChanges(tx)
        revokeLostFactorsAndRelatedSessionsAccordingToPolicy(tx)
        closeOrRevokeRelatedRecoveryTransactions(tx.accountId)

    notifyPreviouslyVerifiedChannel(tx.accountId)
    return recoveryCompletedWithNextSteps()
~~~

Trong triển khai thật:

- Token phải được xác minh qua verifier/hash, không so sánh bản rõ trong log.
- Token, evidence và transaction phải được consume nguyên tử để chống replay/race.
- Mỗi purpose có policy riêng; reset password không tự cho phép thay email hoặc thêm passkey.
- Không tạo session toàn quyền chỉ vì recovery đã verified.
- Nếu commit credential thành công nhưng notification thất bại, cần trạng thái xử lý có thể retry và audit; không rollback mù quáng hoặc báo hoàn tất sai.
- Không log identifier/token/secret thô; dùng correlation ID và account reference đã giảm thiểu.

## 18. Tình huống thực tế: tài khoản bị chiếm và mất MFA

Một nhân viên nhận cảnh báo đăng nhập lạ. Attacker có thể đã lấy mật khẩu và thêm một authenticator vào tài khoản. Nhân viên không còn truy cập điện thoại cũ và yêu cầu recovery.

### Những việc cần kiểm tra

| Thành phần | Câu hỏi |
| --- | --- |
| Password | Mật khẩu có khả năng bị lộ không? Có cần reset và kiểm tra credential reuse? |
| MFA inventory | Có authenticator mới hoặc thiết bị không nhận diện được không? |
| Recovery channels | Email/số điện thoại có bị thay đổi gần đây không? |
| Sessions | Có session từ thiết bị/nguồn bất thường cần revoke không? |
| Tokens/API keys | Có refresh token, API key hoặc client credential mới không? |
| Federation links | Có IdP/account link mới hoặc thay đổi subject không? |
| Audit | Ai đã thực hiện thay đổi, thời điểm và qua quy trình nào? |

### Luồng phản ứng

1. Tạm giữ thao tác nhạy cảm và mở incident recovery.
2. Xác minh nhân viên qua nguồn độc lập đã được tổ chức phê duyệt.
3. Khóa hoặc thu hồi authenticator, session và token có dấu hiệu bị attacker kiểm soát.
4. Đặt lại mật khẩu bằng recovery flow có token ngắn hạn và one-time use.
5. Kiểm tra và loại bỏ passkey, API key, certificate hoặc liên kết danh tính lạ.
6. Đăng ký lại MFA/passkey sau khi xác minh quyền kiểm soát thiết bị.
7. Tạo session mới với context phù hợp; không tái sử dụng session nghi bị chiếm.
8. Thông báo kết quả, cung cấp inventory credential và hướng dẫn kiểm tra hoạt động gần đây.

Chỉ đổi mật khẩu mà không kiểm tra authenticator/API key/session có thể để attacker tiếp tục truy cập. Recovery sau compromise cần xử lý toàn bộ đường duy trì quyền truy cập.

## 19. Kiểm thử account recovery

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Account identifier không tồn tại | Public response không tiết lộ trạng thái tài khoản. |
| Recovery token đúng, còn hạn, đúng purpose | Chỉ cho phép hành động được transaction phê duyệt. |
| Token sai/hết hạn/đã dùng | Từ chối; không thay đổi credential. |
| Token reset password dùng để thêm passkey | Từ chối do purpose mismatch. |
| Hai request dùng cùng token đồng thời | Chỉ một request consume thành công. |
| Client thay account/tenant ID | Server từ chối do transaction binding không khớp. |
| Link scanner mở GET | Không tiêu thụ token hoặc thay đổi credential. |
| Người dùng chủ động POST xác nhận | Xác minh token/CSRF rồi mới commit. |
| Email/phone vừa được đổi | Không dùng ngay làm bằng chứng duy nhất cho recovery tài khoản cũ. |
| Recovery code đã dùng | Từ chối replay. |
| Helpdesk thiếu approver | Không phát hành recovery token hoặc reset MFA. |
| Authenticator mới chưa được xác minh | Vẫn pending, không được dùng đăng nhập. |
| Credential lạ đã tồn tại | Recovery kiểm tra inventory và thu hồi theo incident policy. |
| Session/token cũ sau reset | Thu hồi/giới hạn theo policy; không mặc định tự hết hiệu lực. |
| Notification service lỗi | Retry có kiểm soát, audit rõ; không giả vờ đã gửi thành công. |
| Account bị disabled trong lúc recovery | Hủy/đình chỉ transaction theo policy. |
| IdP/credential store không sẵn sàng | Không fail-open hoặc tự đánh dấu verified. |
| Nhiều recovery request phân tán | Rate limit và risk detection hoạt động trên nhiều chiều. |

### Kiểm thử vận hành và quyền riêng tư

- Không log password, OTP, recovery token, recovery code, cookie hoặc private key.
- Thông báo gửi tới kênh đã xác minh trước đó.
- Có audit actor, approver, policy version, transaction reference và thay đổi.
- Người dùng có thể hủy recovery và báo cáo yêu cầu không do mình khởi tạo.
- Hỗ trợ viên không xem được secret và không thể tự bỏ qua dual control.
- Kiểm tra khả năng phục hồi khi email/SMS/IdP/notification service bị gián đoạn.
- Đo tỷ lệ recovery thành công, thời gian xử lý, fraud signal và false positive.

## 20. Checklist thiết kế luồng recovery

- [ ] Phân biệt password reset, MFA recovery, factor replacement, account recovery và account unlock.
- [ ] Phân loại nguyên nhân và credential còn kiểm soát được trước khi chọn policy.
- [ ] Phản hồi công khai chống account enumeration.
- [ ] Chọn bằng chứng recovery đủ độc lập và đạt assurance floor.
- [ ] Transaction gắn với principal, tenant, purpose, policy version và expiry.
- [ ] Token/challenge entropy cao, ngắn hạn, one-time use và consume nguyên tử.
- [ ] GET không thực hiện thay đổi bảo mật hoặc tiêu thụ recovery token.
- [ ] Kênh thông báo là kênh đã xác minh trước recovery; không tin kênh vừa đổi.
- [ ] Recovery không tự cấp session toàn quyền hoặc bỏ qua step-up.
- [ ] Mật khẩu mới được hash bằng thuật toán chuyên dụng; không gửi mật khẩu qua email.
- [ ] TOTP/passkey/push mới chỉ active sau khi xác minh enrollment.
- [ ] Helpdesk có xác minh độc lập, least privilege, dual control và audit.
- [ ] Có thời gian chờ/thông báo/quyền phản đối cho thay đổi rủi ro cao.
- [ ] Kiểm tra inventory credential, account links, API keys và certificate sau compromise.
- [ ] Thu hồi session, refresh token và credential bị mất theo policy rõ.
- [ ] Có kiểm thử replay, enumeration, recovery chaining, CSRF, IDOR và race condition.
- [ ] Log đủ điều tra nhưng không chứa secret hoặc token thô.

## 21. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao account recovery có thể nguy hiểm hơn một lần đăng nhập thông thường?

**Gợi ý:** Recovery cho phép thay đổi credential và phương thức duy trì quyền truy cập; attacker thành công có thể chiếm tài khoản lâu dài.

**Câu 2.** Vì sao recovery token cần gắn với purpose?

**Gợi ý:** Ngăn token đặt lại mật khẩu bị dùng để thay email, thêm passkey hoặc thực hiện hành động khác ngoài phạm vi đã duyệt.

**Câu 3.** Vì sao không nên gửi recovery link tới email vừa được thay đổi trong cùng recovery flow?

**Gợi ý:** Attacker có thể thay kênh liên hệ rồi dùng chính kênh đó để chứng minh quyền sở hữu tài khoản.

**Câu 4.** Vì sao GET không nên tiêu thụ recovery token?

**Gợi ý:** Email security scanner hoặc preview có thể tự mở link. Cần thao tác xác nhận chủ động qua POST và CSRF protection.

**Câu 5.** Sau khi reset mật khẩu, có cần kiểm tra passkey và API key không?

**Gợi ý:** Có. Attacker có thể đã thêm credential hoặc key khác; chỉ đổi mật khẩu không thu hồi các đường truy cập đó.

**Câu 6.** Vì sao helpdesk cần dual control cho recovery rủi ro cao?

**Gợi ý:** Giảm khả năng một nhân viên bị social engineering hoặc lạm quyền có thể tự cấp lại quyền kiểm soát tài khoản.

**Câu 7.** Recovery thành công có tự động có nghĩa người dùng đạt assurance cho mọi thao tác không?

**Gợi ý:** Không. Recovery evidence chỉ có ý nghĩa theo policy; hành động nhạy cảm vẫn cần authentication context và authorization tương ứng.

## 22. Ghi nhớ

**Account recovery là quy trình khôi phục quyền kiểm soát tài khoản bằng bằng chứng đủ tin cậy, không phải đường vòng bỏ qua xác thực.** Hệ thống cần phân loại credential đã mất, chọn recovery method đạt assurance floor, tạo transaction gắn với đúng principal/tenant/purpose, dùng token ngắn hạn và one-time, chống enumeration/replay/social engineering, rồi thay thế hoặc thu hồi credential có kiểm soát. Sau recovery phải kiểm tra toàn bộ authenticator, account link, session, refresh token và API key có thể bị lạm dụng; thông báo qua kênh độc lập, audit đầy đủ và yêu cầu step-up/authorization riêng trước hành động nhạy cảm.
