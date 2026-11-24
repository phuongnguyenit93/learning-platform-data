# User activation — Kích hoạt tài khoản an toàn

## 1. User activation là gì?

**User activation** (kích hoạt tài khoản người dùng) là quá trình chuyển một tài khoản mới từ trạng thái chờ sang trạng thái được phép tham gia các luồng xác thực và sử dụng dịch vụ theo chính sách. Trước khi kích hoạt, tài khoản có thể đã được tạo từ đăng ký, lời mời của tổ chức hoặc hệ thống provisioning, nhưng chưa hoàn tất điều kiện bắt buộc như xác minh email, chấp nhận lời mời hoặc hoàn thành bước thiết lập ban đầu.

Ví dụ: một nhân viên mới được quản trị viên mời vào cổng nội bộ. Hệ thống tạo bản ghi tài khoản ở trạng thái pending, gửi lời mời tới địa chỉ công ty đã được ghi nhận trong hồ sơ nhân sự và yêu cầu người nhận xác nhận. Khi người nhận hoàn tất xác minh, hệ thống kiểm tra lời mời còn hiệu lực, đúng tài khoản và đúng tổ chức, sau đó kích hoạt tài khoản theo policy. Người dùng tiếp tục thiết lập passkey hoặc MFA trước khi truy cập các chức năng nhạy cảm.

Trong chương **Account lifecycle** của module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, user activation kết nối credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Người học cần hiểu activation là một chuyển trạng thái có kiểm soát, mô hình hóa ranh giới tin cậy và phòng chống phishing, replay, lạm dụng đăng ký cũng như chiếm quyền tài khoản.

**Kích hoạt tài khoản không tự chứng minh danh tính pháp lý và cũng không tự động có nghĩa người dùng đã đăng nhập.** Xác minh email chỉ cho biết người thực hiện có khả năng truy cập hộp thư tại thời điểm xác minh. Authentication xác minh chủ thể khi đăng nhập; authorization quyết định chủ thể được phép làm gì.

## 2. Phân biệt activation, registration, verification và authentication

Các bước thường xuất hiện gần nhau trong vòng đời tài khoản nhưng có mục đích khác nhau:

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Registration** | Tạo yêu cầu hoặc bản ghi tài khoản mới. | Người dùng điền tên, email và thông tin đăng ký. |
| **Verification** | Xác minh một thuộc tính hoặc bằng chứng cụ thể. | Xác minh quyền truy cập hộp thư bằng liên kết một lần. |
| **Activation** | Chuyển tài khoản sang trạng thái được phép tiếp tục theo policy. | Kích hoạt account sau khi lời mời được chấp nhận. |
| **Authentication** | Xác minh chủ thể đang đăng nhập. | Người dùng chứng minh bằng passkey hoặc mật khẩu + MFA. |
| **Authorization** | Quyết định quyền trên tài nguyên và hành động. | Nhân viên chỉ được truy cập dữ liệu thuộc tenant của mình. |
| **Identity proofing** | Xác minh danh tính theo mức bảo đảm đã định. | Đối chiếu hồ sơ nhân sự hoặc quy trình xác minh trực tiếp. |

Một tài khoản có thể được tạo nhưng chưa active; có thể active nhưng chưa có mật khẩu hoặc passkey; cũng có thể active nhưng bị suspended do rủi ro. Không nên gộp tất cả thành một cờ boolean nếu hệ thống cần phân biệt trạng thái và lý do.

### Xác minh email không đồng nghĩa xác minh danh tính

Người dùng bấm liên kết gửi tới email chứng minh họ có quyền truy cập hộp thư hoặc kênh nhận thư tại thời điểm đó. Nó không chứng minh:

- Hộp thư thuộc đúng một cá nhân theo danh tính pháp lý.
- Người dùng là nhân viên đang được tổ chức cho phép.
- Người dùng có quyền vào tenant hoặc nhóm cụ thể.
- Hộp thư chưa bị chiếm hoặc chuyển tiếp.
- Người bấm liên kết là người đã bắt đầu đăng ký.

Vì vậy, ứng dụng cần kết hợp email verification với invitation, provisioning, identity proofing hoặc policy phù hợp khi tài khoản có rủi ro cao.

## 3. Các mô hình tạo tài khoản và kích hoạt

Tài khoản có thể đến từ nhiều nguồn:

| Mô hình | Ai khởi tạo? | Điều kiện activation thường gặp |
| --- | --- | --- |
| **Self-service registration** | Người dùng | Xác minh kênh liên hệ, chấp nhận điều khoản và hoàn thành bước bảo vệ bắt buộc. |
| **Invitation-based** | Admin, manager hoặc người dùng được cấp quyền mời | Chấp nhận invitation gắn đúng người nhận, tenant và vai trò. |
| **Workforce provisioning** | HR/IdP/SCIM hoặc hệ thống quản lý nhân sự | Nguồn authoritative xác nhận người dùng đủ điều kiện; người dùng hoàn tất bootstrap. |
| **Partner/customer provisioning** | Đối tác hoặc hệ thống nghiệp vụ | Xác minh tổ chức, hợp đồng, domain và người đại diện theo policy. |
| **Administrator-created** | Quản trị viên | Phê duyệt, ghi audit và bootstrap credential an toàn. |

Không dùng cùng một luồng cho mọi loại tài khoản. Tài khoản khách tự đăng ký có thể cần xác minh email; tài khoản nhân viên cần liên kết với hồ sơ nhân sự và tenant; tài khoản quản trị cần phê duyệt và phương thức chống phishing mạnh.

### Domain email không phải bằng chứng đủ để cấp quyền

Việc email kết thúc bằng một domain của công ty không tự chứng minh người dùng là nhân viên hoặc được phép vào mọi ứng dụng. Domain có thể có nhà thầu, cựu nhân viên, alias hoặc hộp thư dùng chung. Hãy kiểm tra membership từ nguồn authoritative và áp dụng least privilege.

## 4. Trạng thái tài khoản và state machine

Một mô hình trạng thái có thể gồm:

| Trạng thái | Ý nghĩa | Được đăng nhập? |
| --- | --- | --- |
| **Invited** | Có lời mời đang chờ người nhận chấp nhận. | Không, trừ trang invitation giới hạn. |
| **Pending verification** | Đã tạo account nhưng chưa xác minh điều kiện bắt buộc. | Không vào tài nguyên bảo vệ. |
| **Pending setup** | Đã xác minh bước đầu nhưng còn yêu cầu bootstrap như đặt credential/MFA. | Chỉ vào luồng setup giới hạn. |
| **Active** | Đủ điều kiện account-level để đăng nhập theo policy. | Có thể, nếu authentication thành công. |
| **Suspended** | Tạm đình chỉ do policy, rủi ro hoặc quyết định quản trị. | Không hoặc bị giới hạn theo policy. |
| **Disabled** | Tài khoản bị vô hiệu hóa. | Không. |
| **Expired** | Invitation hoặc quyền truy cập có thời hạn đã hết. | Không qua luồng tương ứng. |
| **Deprovisioned** | Nguồn authoritative đã thu hồi quan hệ/tài khoản. | Không; cần xử lý session và credential liên quan. |

~~~mermaid
stateDiagram-v2
    [*] --> Invited: Tạo lời mời
    [*] --> PendingVerification: Đăng ký
    Invited --> PendingVerification: Chấp nhận lời mời
    PendingVerification --> PendingSetup: Xác minh điều kiện ban đầu
    PendingVerification --> Expired: Hết hạn
    PendingSetup --> Active: Hoàn tất bootstrap
    PendingSetup --> Suspended: Vi phạm policy / rủi ro
    Active --> Suspended: Tạm đình chỉ
    Active --> Disabled: Quản trị vô hiệu hóa
    Active --> Deprovisioned: Nguồn authoritative thu hồi
    Suspended --> Active: Gỡ đình chỉ có kiểm soát
    Disabled --> Active: Tái kích hoạt được phê duyệt
    Expired --> [*]
    Deprovisioned --> [*]
~~~

Đây là mô hình tham khảo; hệ thống có thể có trạng thái riêng. Điều quan trọng là mỗi chuyển trạng thái có điều kiện, actor được phép, audit event và tác động tới session/token rõ ràng. Không cho client tự gửi trạng thái mới trong request.

### Account status khác authentication status

Tài khoản có thể active nhưng người dùng chưa xác thực. Người dùng cũng có thể đã xác thực thành công ở IdP nhưng RP phải từ chối vì account bị suspended hoặc tenant membership đã bị thu hồi. Mỗi request cần kiểm tra trạng thái account và policy hiện tại, không chỉ tin session cũ.

## 5. Luồng activation tổng quát

Một luồng activation an toàn thường gồm:

1. **Create:** tạo bản ghi ở trạng thái invited/pending với dữ liệu tối thiểu.
2. **Bind:** gắn account với tenant, invitation hoặc nguồn provisioning đã được xác minh.
3. **Issue:** tạo activation transaction/token có entropy cao, purpose và expiry.
4. **Deliver:** gửi hướng dẫn qua kênh phù hợp đã được xác định.
5. **Verify:** người nhận chủ động xác nhận; server kiểm tra token, transaction và điều kiện.
6. **Activate/setup:** chuyển trạng thái bằng thao tác nguyên tử hoặc chuyển sang pending setup.
7. **Protect:** thiết lập credential/MFA theo policy trước khi cấp quyền nhạy cảm.
8. **Notify/audit:** thông báo và ghi nhận thay đổi.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Browser
    participant A as Account service
    participant D as Account store
    participant N as Notification service
    U->>B: Đăng ký hoặc mở invitation
    B->>A: Yêu cầu tạo/chấp nhận tài khoản
    A->>A: Kiểm tra policy, tenant và quyền inviter
    A->>D: Tạo account pending + activation transaction
    A->>N: Gửi liên kết/mã qua kênh phù hợp
    N-->>U: Hướng dẫn activation
    U->>B: Mở liên kết và xác nhận
    B->>A: POST transaction + token + CSRF binding
    A->>A: Kiểm tra purpose, expiry, replay và recipient
    A->>D: Consume token và chuyển trạng thái nguyên tử
    A-->>B: Active hoặc pending setup
    A->>N: Gửi thông báo kết quả
~~~

Không nhất thiết mọi tài khoản đều đi qua email link. Với workforce provisioning, nguồn authoritative có thể tạo account pending setup; người dùng đăng ký passkey qua luồng bootstrap của tổ chức. Dù mô hình nào, server phải xác minh nguồn và điều kiện trước khi chuyển trạng thái.

## 6. Activation token và invitation token

Activation token là bearer secret: ai có token có thể thử thực hiện hành động được token cho phép. Vì vậy, token phải được bảo vệ như credential:

- Sinh bằng CSPRNG với entropy đủ cao.
- Gắn với account, tenant, purpose và transaction cụ thể.
- Có thời hạn ngắn, attempt limit và one-time use.
- Lưu verifier/hash của token ở server nếu kiến trúc cho phép.
- Không đưa token vào log, analytics, crash report hoặc ticket hỗ trợ.
- Không cho token của activation được dùng để reset password, thêm passkey hay đổi email.
- Thu hồi token cũ khi phát hành token mới hoặc khi invitation bị hủy.

Invitation token còn cần ràng buộc với người nhận, tổ chức, vai trò được mời và người có quyền mời. Không dùng token chung cho nhiều người hoặc nhiều lần chấp nhận.

### Token không phải session

Activation token chỉ cho phép một thao tác giới hạn, ví dụ xác nhận invitation hoặc xác minh kênh liên hệ. Nó không nên tự trở thành session authenticated toàn quyền. Sau activation, người dùng cần thực hiện authentication bằng credential đã thiết lập hoặc tiếp tục bootstrap theo policy.

## 7. Liên kết activation và email security scanner

Một số hệ thống email tự động mở URL để kiểm tra phishing/malware. Nếu server kích hoạt tài khoản ngay khi nhận GET request, scanner có thể tiêu thụ token trước người dùng.

Thiết kế an toàn:

1. GET chỉ hiển thị trang xác nhận và kiểm tra sơ bộ; không thay đổi trạng thái.
2. Trang giải thích tài khoản/tổ chức hoặc mục đích invitation ở mức phù hợp.
3. Người dùng chủ động nhấn nút xác nhận.
4. Browser gửi POST có CSRF binding và transaction reference.
5. Server xác minh token, recipient, purpose, expiry và trạng thái.
6. Server consume token và cập nhật trạng thái nguyên tử.

Trang chứa token cần:

- HTTPS và HSTS theo cấu hình hệ thống.
- Referrer-Policy hạn chế rò rỉ URL.
- Không tải analytics, quảng cáo hoặc script bên thứ ba không cần thiết.
- Redact token ở reverse proxy, access log, APM và error reporting.
- Không hiển thị token trong DOM lâu hơn cần thiết.

Không thực hiện activation bằng GET. Không chuyển token sang một URL tùy ý sau khi xác minh; nếu cần chuyển trang, dùng session/transaction reference an toàn và xóa thông tin nhạy cảm khỏi URL.

## 8. Xác minh email và số điện thoại

### Email verification

Email verification chứng minh quyền truy cập hộp thư tại thời điểm xác minh. Một luồng thường có token một lần, thời hạn, account binding và thông báo kết quả. Hệ thống cần chuẩn hóa email nhất quán nhưng tránh tự ý biến đổi local-part theo quy tắc riêng của từng nhà cung cấp.

Các điểm cần lưu ý:

- Xử lý domain quốc tế hóa (IDN) và so sánh domain theo thư viện chuẩn.
- Không tự xóa dấu chấm hoặc phần +tag của local-part; hành vi này không phổ quát.
- Tránh tiết lộ email đầy đủ trong giao diện hoặc response công khai.
- Khi đổi email sau activation, dùng luồng thay đổi email riêng có step-up và xác minh địa chỉ mới.
- Không cho email mới vừa thêm tự xác minh ngược quyền sở hữu tài khoản cũ.

### SMS/phone verification

OTP SMS có thể xác minh khả năng nhận tin nhắn trên số điện thoại tại thời điểm đó. Nó có rủi ro SIM swap, chuyển tiếp, phishing và phụ thuộc nhà mạng. Không coi SMS là bằng chứng danh tính mạnh hoặc phương thức chống phishing.

OTP cần ngắn hạn, giới hạn số lần thử/gửi lại và gắn đúng account/purpose. Không gửi mã tới số điện thoại do client thay đổi trong cùng transaction mà chưa xác minh quyền thay đổi.

## 9. Invitation-based activation

Với tài khoản tổ chức, invitation cần thể hiện rõ:

- Tổ chức/tenant mời.
- Ứng dụng hoặc phạm vi truy cập.
- Vai trò/quyền được đề nghị.
- Người hoặc hệ thống tạo lời mời.
- Người nhận dự kiến và thời hạn.
- Hướng dẫn liên hệ nếu lời mời không được mong đợi.

### Kiểm tra phía server

- Inviter có quyền mời người dùng vào đúng tenant không?
- Role/scope có nằm trong phạm vi inviter được phép cấp không?
- Email/subject người nhận có khớp lời mời không?
- Invitation còn pending, chưa hết hạn và chưa bị thu hồi không?
- Tài khoản có tồn tại ở tenant khác hoặc có xung đột danh tính cần xử lý không?
- Người nhận có phải hoàn tất identity proofing hoặc MFA bootstrap không?

Không cho inviter tự cấp quyền cao hơn quyền của họ. Không coi người biết invitation URL là đã được phép tham gia tenant nếu token không ràng buộc recipient và scope.

### Chấp nhận invitation

Người nhận cần xác minh kênh/identity theo policy rồi mới chấp nhận. Nếu đã có tài khoản, hệ thống phải xác thực tài khoản hiện tại và liên kết membership vào đúng tenant. Không tạo tài khoản trùng chỉ vì email hiển thị giống nhau; cũng không tự hợp nhất account chỉ dựa vào email.

## 10. Workforce provisioning và activation

Trong môi trường doanh nghiệp, tài khoản có thể được tạo bởi HR, directory, IdP hoặc SCIM provisioning. Nguồn authoritative có thể cung cấp trạng thái nhân sự, department, manager, tenant và nhóm.

Các nguyên tắc:

- Xác định nguồn authoritative cho từng thuộc tính; không để người dùng tự sửa thuộc tính do HR quản lý.
- Provisioning create/update/disable phải được xác thực nguồn và kiểm tra quyền.
- Activation của người dùng mới có thể yêu cầu hoàn tất bootstrap như passkey/MFA, thiết lập recovery method và chấp nhận policy.
- Không cấp quyền production chỉ vì bản ghi đã được provision.
- Khi nguồn authoritative gửi disable/deprovision, xử lý session, refresh token và credential liên quan theo policy.
- Idempotency và event ordering phải được xử lý để message retry không tạo nhiều account hoặc đảo ngược trạng thái mới hơn.

### SCIM và trạng thái người dùng

SCIM có thể truyền trạng thái user như active/inactive cùng thuộc tính provisioning. Ứng dụng phải hiểu semantics của nguồn và ánh xạ sang state machine nội bộ. Không dùng một trường active đơn lẻ để suy ra người dùng đã xác minh email, đã đăng ký MFA hoặc đã hoàn tất authentication.

## 11. Bootstrap credential sau activation

Sau khi điều kiện activation đạt, người dùng có thể cần thiết lập credential:

| Credential | Bootstrap an toàn |
| --- | --- |
| **Mật khẩu** | Thiết lập qua HTTPS, password hashing chuyên dụng, kiểm tra mật khẩu yếu/bị lộ và không gửi mật khẩu qua email. |
| **Passkey** | WebAuthn registration với challenge mới, origin/RP ID đúng và xác minh user presence/verification theo policy. |
| **TOTP** | Sinh secret riêng, hiển thị provisioning QR trong session đúng và chỉ active sau khi xác minh mã. |
| **Security key** | Đăng ký credential qua WebAuthn, kiểm tra challenge và lưu public key. |
| **Client certificate** | Provision private key trong môi trường phù hợp, xác minh certificate chain, subject/SAN và policy PKI. |
| **Recovery codes** | Sinh mã ngẫu nhiên dùng một lần, hiển thị một lần và lưu verifier an toàn. |

### Không để activation link trở thành credential lâu dài

Activation token có thời hạn và purpose riêng. Sau khi người dùng xác nhận, token phải được consume; người dùng tiếp tục đăng ký credential mới qua một transaction riêng. Không tái sử dụng activation token làm password reset token hoặc bearer session.

### MFA bootstrap cho tài khoản nhạy cảm

Tài khoản quản trị, tài khoản tài chính hoặc tài khoản truy cập dữ liệu nhạy cảm có thể phải đăng ký passkey/MFA trước khi được cấp quyền sử dụng ứng dụng. Nếu MFA enrollment thất bại, giữ tài khoản ở pending setup hoặc trạng thái giới hạn; không tự bỏ qua policy để hoàn tất activation.

## 12. Activation không tự động đăng nhập

Sau khi bấm activation link, người dùng có thể được đưa tới trang đăng nhập hoặc trang setup. Việc có token activation không tự chứng minh họ đã hoàn tất authentication:

- Token có thể được chuyển tiếp hoặc bị lấy từ hộp thư.
- Email có thể đang mở trên thiết bị dùng chung.
- Người bấm liên kết có thể không phải người đã khởi tạo registration.
- Activation chỉ xác minh một điều kiện; nó không chứng minh password/passkey hiện tại.

Một số sản phẩm có thể thiết kế passwordless magic-link sign-in, nhưng đó là một authentication flow riêng. Nếu dùng, phải áp dụng semantics, transaction binding, expiry, one-time use, session issuance và risk controls của đăng nhập; không gọi đơn giản là activation.

Sau activation, nếu tự động tạo session giới hạn cho bootstrap, session đó phải có quyền rất hẹp, thời hạn ngắn và không truy cập protected resources trước khi hoàn tất authentication/MFA policy.

## 13. Chống account enumeration và lạm dụng activation

Kẻ tấn công có thể dùng registration/invitation/resend endpoint để dò tài khoản, spam email/SMS hoặc chiếm tên người dùng:

- Dùng phản hồi công khai chung cho tài khoản tồn tại/không tồn tại khi phù hợp.
- Rate limit theo identifier đã chuẩn hóa, IP/ASN, thiết bị, client và toàn hệ thống.
- Có cooldown và giới hạn số lần gửi lại.
- Không cho phép resend vô hạn hoặc gửi OTP tới địa chỉ tùy ý.
- Dùng CAPTCHA/risk challenge như một lớp chống automation có phương án accessible; không coi đó là bằng chứng danh tính.
- Không hiển thị trạng thái activation hoặc credential của người khác.
- Phát hiện invitation hàng loạt, domain giả mạo và hành vi tạo account bất thường.
- Chặn việc tự mời hoặc tự cấp role vượt quyền.

Không khóa vĩnh viễn account chỉ vì có nhiều activation request. Attacker có thể cố tình spam hoặc làm hết hạn invitation của nạn nhân. Dùng throttling và quy trình cấp lại invitation có kiểm soát.

## 14. Race condition, replay và idempotency

Activation có thể nhận request đồng thời từ người dùng, link scanner, retry mạng hoặc nhiều instance server. Nếu token không được consume nguyên tử, cùng một token có thể kích hoạt nhiều lần hoặc gắn sai trạng thái.

Các bất biến:

- Token chỉ thuộc một account, tenant, purpose và transaction.
- Token chỉ được consume một lần.
- Chỉ một state transition hợp lệ được commit.
- Account activation không cấp role/scope ngoài invitation/provisioning đã xác minh.
- Retry sau khi commit trả kết quả idempotent, không tạo thêm session hoặc credential.
- Transaction hết hạn/hủy không thể quay lại trạng thái active bằng token cũ.

Sử dụng transaction database, unique constraint, compare-and-swap hoặc cơ chế atomic state transition phù hợp. Không dựa vào kiểm tra “đã dùng chưa” rồi cập nhật bằng hai thao tác tách rời có race.

## 15. Thông báo và bảo vệ chủ tài khoản

Sau khi activation hoàn tất, hệ thống nên gửi thông báo qua kênh đã xác minh hoặc kênh tổ chức đã provision:

- Tài khoản đã được kích hoạt.
- Tenant/tổ chức và ứng dụng liên quan.
- Thời điểm và loại phương thức bootstrap đã hoàn tất ở mức metadata.
- Hướng dẫn báo cáo nếu người dùng không thực hiện.
- Liên kết tới trang quản lý session/credential chính thức.

Không gửi password, OTP, recovery code, private key, activation token hoặc QR provisioning trong thông báo sau khi sử dụng. Nếu thông báo không gửi được, ghi nhận lỗi và retry có kiểm soát; không rollback account state mù quáng nếu activation đã commit.

Với invitation không mong đợi, người nhận cần có cách từ chối hoặc báo cáo. Không bắt người nhận đăng nhập để xem nội dung invitation nếu điều đó làm lộ thông tin tenant hoặc tổ chức cho người không liên quan.

## 16. Session, token và account state sau activation

Activation thay đổi trạng thái account-level, nhưng session và token có vòng đời riêng:

| Tài sản | Nguyên tắc |
| --- | --- |
| **Activation token** | Consume/revoke sau khi hoàn tất; không dùng lại cho authentication. |
| **Invitation** | Đánh dấu accepted/revoked/expired; không cho dùng lại. |
| **Pending setup transaction** | Chỉ cho phép bootstrap cần thiết; TTL ngắn và quyền hạn giới hạn. |
| **Authenticated session** | Chỉ tạo sau authentication đạt policy; xoay session ID sau đăng nhập. |
| **Access/refresh token** | Chỉ phát hành theo grant và policy; gắn audience/scope/client đúng. |
| **Credential mới** | Chỉ active sau khi registration/verification hoàn tất. |
| **Account state** | Được kiểm tra tại các điểm truy cập quan trọng; không chỉ tin cookie cũ. |

Nếu account bị suspended hoặc deprovisioned sau activation, ứng dụng cần ngăn request mới và xử lý session/token theo chính sách. Không cho session tồn tại vô hạn chỉ vì tài khoản từng active.

## 17. Các tấn công nhắm vào user activation

| Rủi ro | Kịch bản | Biện pháp |
| --- | --- | --- |
| **Activation token theft** | Token bị lộ trong URL, log, Referer hoặc analytics. | HTTPS, Referrer-Policy, redaction, TTL ngắn và one-time use. |
| **Link scanner consumption** | Email scanner mở GET và kích hoạt trước người dùng. | GET chỉ hiển thị; POST chủ động mới consume token. |
| **Invitation hijacking** | Người khác lấy invitation URL và chấp nhận thay người nhận. | Recipient binding, token purpose-bound, xác minh kênh và tenant. |
| **Account enumeration** | Endpoint tiết lộ email/tài khoản tồn tại. | Response chung, rate limit và kiểm tra timing/status. |
| **Registration spam** | Attacker tạo hàng loạt account/invitation hoặc gửi OTP. | Throttling đa chiều, abuse detection và quota. |
| **Role escalation** | Inviter cấp role vượt quyền hoặc client sửa role. | Server-side authorization, role allowlist và least privilege. |
| **Domain confusion** | Email cùng domain bị coi là đủ điều kiện vào tenant. | Kiểm tra membership từ nguồn authoritative. |
| **Replay** | Activation token đã dùng được gửi lại. | Atomic consume, expiry và trạng thái transaction. |
| **Race condition** | Hai request đồng thời kích hoạt hoặc accept invitation. | Atomic state transition và idempotency. |
| **Session confusion** | Activation token bị dùng như bearer session. | Tách token purpose; không cấp session toàn quyền. |
| **Bootstrap downgrade** | Tài khoản nhạy cảm bỏ qua MFA vì activation gặp lỗi. | Giữ pending setup và assurance floor. |
| **Provisioning replay/order** | Message cũ ghi đè trạng thái account mới hơn. | Event versioning, source authority và idempotent processing. |
| **Notification tampering** | Attacker đổi kênh rồi nhận thông báo activation. | Kênh đã xác minh trước, audit và step-up khi đổi kênh. |

## 18. Mã giả: kích hoạt bằng token một lần

Mã giả dưới đây mô tả logic khái niệm, không thay thế thư viện mật mã hoặc hệ thống transaction đã được kiểm thử:

~~~text
requestActivation(identifier, requestContext):
    applyRegistrationAndResendLimits(identifier, requestContext)
    account = lookupEligiblePendingAccount(identifier)

    if account exists:
        tx = createTransaction(
            accountId = account.id,
            tenantId = account.tenantId,
            purpose = "activate_account",
            recipientBinding = verifiedExpectedRecipient(account),
            expiresAt = shortExpiry(),
            status = "pending"
        )
        token = generateHighEntropyToken()
        storeTokenVerifierBoundToTransaction(token, tx)
        sendActivationInstructionToExpectedChannel(account, token)

    return genericPublicResponse()

confirmActivation(txId, token, csrfProof):
    tx = loadTransaction(txId)
    require tx.status == "pending"
    require tx.notExpired
    require csrfProofMatchesCurrentBrowserTransaction(csrfProof, tx)
    require tokenVerifierMatches(token, tx)
    require tx.purpose == "activate_account"
    require recipientBindingStillValid(tx)
    require tenantAndInvitationPolicyStillAllows(tx)

    atomically:
        consumeActivationToken(tx)
        markTransaction(tx, "consumed")
        transitionAccountAccordingToPolicy(tx.accountId)
        markInvitationAcceptedIfApplicable(tx)

    notifyPreviouslyVerifiedChannel(tx.accountId)
    return activationSuccessOrPendingSetup()
~~~

Trong triển khai thực tế:

- Token phải có entropy cao, lưu verifier/hash và không xuất hiện trong log.
- GET không gọi confirmActivation; thao tác xác nhận cần POST chủ động.
- State transition và token consumption phải nguyên tử.
- Transaction phải kiểm tra lại account/tenant/invitation state trước commit.
- Retry sau commit cần trả kết quả idempotent.
- Activation không tự tạo authenticated session hoặc cấp role ngoài policy.

## 19. Tình huống thực tế: lời mời nhân viên mới

Một quản trị viên mời nhân viên mới vào tenant công ty với quyền xem tài liệu nội bộ. Hệ thống HR là nguồn authoritative xác nhận nhân viên và địa chỉ công ty.

### Kiểm tra trước khi gửi invitation

| Kiểm tra | Điều kiện |
| --- | --- |
| Inviter | Có quyền mời vào đúng tenant. |
| Recipient | Khớp hồ sơ nhân sự đã xác minh. |
| Tenant | Tổ chức đang active và cho phép onboarding. |
| Role | Nằm trong phạm vi quyền inviter được cấp. |
| Invitation | Pending, có expiry và token riêng. |
| Audit | Ghi người mời, thời điểm, tenant và role được đề nghị. |

### Khi người nhận chấp nhận

1. Mở trang HTTPS từ liên kết invitation.
2. Xem tên tổ chức và quyền được mời.
3. Chủ động xác nhận; server kiểm tra token, recipient binding, expiry và transaction.
4. Hệ thống liên kết membership với đúng principal; không tự hợp nhất account chỉ vì email trùng.
5. Chuyển account sang pending setup nếu cần đăng ký passkey/MFA.
6. Sau bootstrap, người dùng đăng nhập bằng credential riêng.
7. Hệ thống ghi audit và gửi thông báo.

Nếu invitation được chuyển tiếp cho người khác, recipient binding hoặc bước xác minh danh tính phải ngăn người nhận sai chấp nhận. Nếu nhân viên đã rời công ty trước khi chấp nhận, HR/IdP provisioning phải có quyền thu hồi invitation và ngăn activation.

## 20. Kiểm thử user activation

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Account pending và token đúng, còn hạn | Chuyển trạng thái theo policy; token bị consume. |
| Token sai, hết hạn hoặc đã dùng | Từ chối; account không active do request đó. |
| Token activation dùng để reset password | Từ chối do purpose mismatch. |
| Email scanner thực hiện GET | Không consume token, không kích hoạt account. |
| Người dùng chủ động POST xác nhận | Kiểm tra CSRF, recipient, purpose và state trước commit. |
| Invitation bị thu hồi trước khi accept | Từ chối dù token chưa hết hạn. |
| Người nhận khác recipient binding | Từ chối hoặc yêu cầu quy trình xác minh đúng người. |
| Inviter không đủ quyền cấp role | Không tạo invitation hoặc không cấp role đó. |
| Client sửa tenant/role/account ID | Server bỏ qua hoặc từ chối; không thay đổi dữ liệu trái phép. |
| Hai request accept đồng thời | Chỉ một state transition thành công; retry idempotent. |
| Account đã active | Không tạo credential/session mới ngoài policy; trả kết quả an toàn. |
| Account disabled/deprovisioned | Không kích hoạt từ invitation cũ. |
| Email/phone không tồn tại | Public response không tiết lộ account enumeration. |
| Resend liên tục | Rate limit/cooldown; token cũ được xử lý theo policy. |
| Notification service lỗi | Ghi nhận và retry; không rollback mù quáng hoặc báo gửi thành công. |
| MFA bootstrap chưa hoàn tất | Account giữ pending setup/limited; không truy cập chức năng yêu cầu MFA. |
| Provisioning event cũ tới muộn | Không ghi đè trạng thái mới hơn; dùng version/source authority. |
| Activation token xuất hiện trong log | Kiểm thử phải thất bại; token được redaction. |

### Kiểm thử vận hành và quyền riêng tư

- Kiểm tra email normalization, IDN và alias không bị hợp nhất sai.
- Kiểm tra status code, response body, redirect và timing cho enumeration.
- Kiểm tra invitation có thể bị thu hồi và hết hạn.
- Kiểm tra log/trace không chứa token, OTP, password hoặc QR.
- Kiểm tra thông báo gửi đúng kênh đã xác minh.
- Kiểm tra hỗ trợ người dùng từ chối invitation không mong đợi.
- Kiểm tra trạng thái account được áp dụng nhất quán ở API, UI và background job.

## 21. Checklist thiết kế user activation

- [ ] Phân biệt registration, verification, activation, authentication và authorization.
- [ ] Chọn mô hình self-service, invitation hoặc provisioning theo loại tài khoản.
- [ ] Xác định nguồn authoritative cho principal, tenant, membership và trạng thái nhân sự.
- [ ] State machine có trạng thái và chuyển đổi rõ ràng; client không tự sửa trạng thái.
- [ ] Activation/invitation token có entropy cao, purpose/account/tenant binding, TTL và one-time use.
- [ ] Lưu verifier/hash token; redaction ở log, analytics, proxy và APM.
- [ ] GET chỉ hiển thị; POST chủ động mới consume token và thay đổi trạng thái.
- [ ] Chống account enumeration ở registration, activation, resend và recovery endpoints.
- [ ] Rate limit và quota theo identifier, nguồn, client và toàn hệ thống.
- [ ] Invitation ràng buộc recipient, inviter, tenant, role và expiry.
- [ ] Không cấp role vượt quyền inviter; áp dụng least privilege.
- [ ] Email/phone verification không bị coi là identity proofing hoặc phishing-resistant MFA.
- [ ] Credential mới chỉ active sau khi bootstrap/registration được xác minh.
- [ ] Không biến activation token thành authenticated session hoặc token đa mục đích.
- [ ] Có thông báo qua kênh đã xác minh và audit thay đổi.
- [ ] Xử lý retry, replay, race condition và provisioning event ordering.
- [ ] Account disabled/deprovisioned không thể được kích hoạt bằng invitation cũ.
- [ ] Kiểm tra session/token và authorization theo account state hiện tại.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Activation khác authentication như thế nào?

**Gợi ý:** Activation chuyển trạng thái tài khoản sau khi điều kiện ban đầu đạt; authentication xác minh chủ thể trong một lần đăng nhập. Activation link không tự tạo bằng chứng đăng nhập đầy đủ.

**Câu 2.** Bấm liên kết xác minh email chứng minh điều gì?

**Gợi ý:** Chứng minh quyền truy cập hộp thư/kênh tại thời điểm xác minh, không chứng minh danh tính pháp lý hoặc quyền vào tenant.

**Câu 3.** Vì sao GET không nên kích hoạt tài khoản?

**Gợi ý:** Email scanner hoặc preview có thể tự mở liên kết. Cần thao tác xác nhận chủ động qua POST và consume token nguyên tử.

**Câu 4.** Vì sao invitation token phải gắn với recipient và tenant?

**Gợi ý:** Ngăn URL bị chuyển tiếp hoặc token bị dùng để tham gia sai tổ chức/tài khoản.

**Câu 5.** Tài khoản active có nghĩa người dùng đã đăng nhập và có quyền truy cập mọi chức năng không?

**Gợi ý:** Không. Authentication và authorization là bước riêng; account có thể active nhưng chưa có session hoặc không có role trên tài nguyên.

**Câu 6.** Vì sao không tự hợp nhất hai account chỉ vì email giống nhau?

**Gợi ý:** Email có thể thay đổi, tái cấp hoặc chưa được xác minh; cần liên kết danh tính theo issuer/subject và quy trình có xác thực.

**Câu 7.** Khi HR deprovision nhân viên, vì sao cần xử lý session/token?

**Gợi ý:** Account status thay đổi không tự động vô hiệu hóa mọi session/token đã phát hành; verifier phải áp dụng thu hồi theo policy.

## 23. Ghi nhớ

**User activation là một chuyển trạng thái tài khoản có kiểm soát, nằm giữa việc tạo tài khoản và khả năng sử dụng dịch vụ theo policy.** Hệ thống cần phân biệt registration, verification, activation, authentication và authorization; xác định nguồn authoritative; dùng activation/invitation token ngắn hạn, purpose-bound và one-time; không kích hoạt bằng GET; chống enumeration, replay, spam và role escalation; rồi yêu cầu bootstrap credential/MFA phù hợp trước khi cấp quyền nhạy cảm. Account state, credential, session và token có vòng đời riêng, nên phải được kiểm tra và thu hồi nhất quán khi invitation hết hạn, tài khoản bị đình chỉ hoặc nguồn provisioning deprovision người dùng.
