# Account modification

**Account modification** là quá trình thay đổi có kiểm soát các thuộc tính, liên kết, phương thức xác thực hoặc trạng thái của một account trong suốt vòng đời sử dụng. Các thay đổi có thể rất nhỏ, như cập nhật tên hiển thị, hoặc có ảnh hưởng lớn tới ranh giới tin cậy, như đổi định danh đăng nhập, thay email khôi phục, thêm passkey, liên kết một Identity Provider mới, chuyển tenant, cấp role quản trị, khóa hoặc mở lại account.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, người học tìm hiểu cách xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục account. Vì vậy, account modification cần được xem là một phần của bảo mật xác thực: thay đổi thông tin có thể làm thay đổi cách hệ thống tìm ra chủ thể, xác minh họ, khôi phục quyền truy cập và quyết định họ được phép làm gì.

Điểm cốt lõi: **một phiên đăng nhập hợp lệ không tự động trao quyền thay đổi mọi thuộc tính của account**. Mỗi thay đổi cần đúng actor, đúng account đích, thẩm quyền phù hợp, bằng chứng xác minh tương xứng với rủi ro và một bản ghi audit có thể kiểm tra. Các thay đổi nhạy cảm phải được ràng buộc với đúng yêu cầu và được áp dụng nhất quán để tránh race condition, account takeover hoặc cấp quyền nhầm.

## 1. Account modification là gì?

Account là đối tượng quản lý trong một hệ thống. Nó có thể gắn với một người dùng, tổ chức, workload hoặc một principal khác. Account thường chứa hoặc tham chiếu tới:

- Định danh nội bộ ổn định.
- Tên đăng nhập và các thuộc tính hiển thị.
- Email, số điện thoại hoặc địa chỉ liên hệ.
- Tenant, tổ chức, nhóm và quan hệ quản lý.
- Trạng thái hoạt động, đình chỉ hoặc đóng.
- Credential và authenticator đã đăng ký.
- Recovery methods và các liên kết identity provider.
- Role, permission, entitlement và policy áp dụng.
- Session, token grant hoặc metadata liên quan.

Account modification là một thao tác thay đổi một hoặc nhiều thuộc tính trên đối tượng đó. Hệ thống cần phân biệt thuộc tính nào chỉ phục vụ hiển thị, thuộc tính nào dùng để định danh, thuộc tính nào dùng để xác thực/khôi phục và thuộc tính nào ảnh hưởng authorization.

### 1.1. Những loại thay đổi thường gặp

| Nhóm thay đổi | Ví dụ | Ảnh hưởng bảo mật |
| --- | --- | --- |
| **Profile** | Tên hiển thị, ngôn ngữ, múi giờ. | Thường thấp nếu không dùng làm căn cứ định danh hoặc cấp quyền. |
| **Login identifier** | Username, email đăng nhập, số điện thoại đăng nhập. | Có thể thay đổi cách account được tìm thấy và tạo nguy cơ chiếm account. |
| **Contact/recovery** | Email khôi phục, số điện thoại khôi phục. | Có thể tạo đường reset password hoặc bypass MFA. |
| **Authenticator** | Thêm/xóa passkey, TOTP, security key, smart card. | Thay đổi cách chứng minh quyền kiểm soát account. |
| **Federation/linking** | Liên kết hoặc gỡ IdP, thay issuer/subject mapping. | Thay đổi nguồn danh tính được tin cậy. |
| **Access/role** | Thêm nhóm, role, quyền tenant hoặc quyền ứng dụng. | Thay đổi những hành động account được phép thực hiện. |
| **Ownership/tenant** | Chuyển account sang tổ chức khác, đổi sponsor. | Có thể làm thay đổi phạm vi dữ liệu và authority. |
| **Lifecycle status** | Suspend, reactivate, disable, close. | Quyết định account có thể xác thực và sử dụng tài nguyên hay không. |

Không nên xử lý mọi thay đổi qua một endpoint chung với cùng mức kiểm soát. Cập nhật tên hiển thị và thêm recovery method có hậu quả rất khác nhau.

### 1.2. Account, identity và credential không phải một thứ

- **Identity** biểu diễn chủ thể được nhận diện trong một miền tin cậy.
- **Account** là bản ghi hoặc đối tượng mà một hệ thống dùng để quản lý chủ thể và quyền truy cập.
- **Credential/authenticator** là phương tiện chứng minh quyền kiểm soát trong quá trình xác thực.
- **Login identifier** là dữ liệu giúp tìm account, chẳng hạn username hoặc email; nó không nhất thiết là định danh bền vững.
- **Session** là trạng thái đăng nhập được thiết lập sau khi xác thực.
- **Role/permission** xác định hành động được phép sau khi principal được nhận diện.

Thay đổi email không nhất thiết tạo identity mới. Thêm passkey không tạo account mới. Liên kết một IdP không nên tự động hợp nhất hai account chỉ vì email giống nhau. Hệ thống phải có quy tắc rõ về định danh ổn định và liên kết account.

## 2. Ai có quyền sửa account?

Account có thể được sửa bởi chính người dùng, quản trị viên, helpdesk, hệ thống nguồn hoặc quy trình tự động. Quyền sửa phải được giới hạn theo actor, target, thuộc tính và tenant.

### 2.1. Self-service modification

Người dùng có thể tự cập nhật một số thông tin như tên hiển thị, ngôn ngữ hoặc tùy chọn giao diện. Với thông tin ảnh hưởng đăng nhập, recovery, credential hoặc quyền, hệ thống cần thêm bước xác minh.

Ví dụ:
- Đổi tên hiển thị: thường chỉ cần session hợp lệ và kiểm tra dữ liệu.
- Đổi email đăng nhập: cần xác minh địa chỉ mới và có thể yêu cầu re-authentication.
- Thay email recovery: cần xác minh mạnh hơn và thông báo tới kênh cũ.
- Thêm passkey: cần chứng minh quyền kiểm soát account hiện tại và xác minh WebAuthn ceremony.
- Xóa authenticator cuối cùng: cần kiểm tra recovery và tránh khóa account.
- Tự thêm role administrator: không được phép chỉ vì người dùng đang đăng nhập.

### 2.2. Administrator modification

Quản trị viên có thể sửa account trong phạm vi tenant hoặc ứng dụng được giao. Quyền admin không đồng nghĩa quyền sửa mọi account ở mọi tenant.

Server cần kiểm tra:
- Actor đã xác thực bằng phương thức phù hợp.
- Role và scope hiện tại của actor.
- Actor có quyền trên target account và tenant.
- Thay đổi có nằm trong quyền được ủy quyền không.
- Có cần phê duyệt độc lập hoặc dual control không.
- Actor có đang sửa account của chính mình hoặc cấp quyền cho chính mình trái policy không.

Không tin account ID, tenant ID, role hoặc email approver do client tự khai. Server phải resolve target và authority từ dữ liệu đáng tin cậy.

### 2.3. Helpdesk và delegated administration

Helpdesk có thể hỗ trợ sửa thông tin hoặc recovery, nhưng cần phân tách quyền hỗ trợ khỏi quyền tự do thay đổi danh tính. Nhân viên hỗ trợ không nên được yêu cầu bỏ qua proofing chỉ vì người gọi biết một số thông tin hồ sơ.

Với thao tác rủi ro cao, cần:
- Ticket hoặc lý do nghiệp vụ có thể kiểm toán.
- Xác minh requester qua kênh đã đăng ký trước.
- Phê duyệt độc lập nếu policy yêu cầu.
- Giới hạn loại thay đổi helpdesk được phép thực hiện.
- Thông báo tới account owner qua kênh độc lập.
- Ghi lại actor, approver, request ID và kết quả.

### 2.4. System-to-system modification

Một hệ thống HR, directory hoặc tenant management có thể là nguồn có thẩm quyền cho thuộc tính nhất định. Cần xác định field nào do hệ thống nguồn quản lý và field nào do người dùng tự quản lý.

Ví dụ, trạng thái nhân viên và mã nhân sự có thể được đồng bộ từ HR; tên hiển thị có thể được người dùng tùy chỉnh theo policy. Không để một client bất kỳ ghi đè thuộc tính được bảo vệ bởi nguồn có thẩm quyền.

## 3. Phân loại rủi ro trước khi thay đổi

Rủi ro của một thay đổi phụ thuộc vào hậu quả nếu attacker thực hiện được, khả năng phát hiện, khả năng khôi phục và phạm vi ảnh hưởng.

| Mức tham khảo | Ví dụ | Kiểm soát phù hợp |
| --- | --- | --- |
| **Thấp** | Ngôn ngữ, múi giờ, tên hiển thị không dùng cho proofing. | Session hợp lệ, validation và audit cơ bản. |
| **Trung bình** | Đổi username, email liên hệ không dùng recovery, cập nhật thông tin tổ chức. | Re-authentication phù hợp, xác minh dữ liệu mới, notification. |
| **Cao** | Đổi login identifier, recovery method, thêm/xóa authenticator, liên kết IdP. | Step-up bằng phương thức đã đăng ký trước, xác minh kênh mới, delay/notification hoặc approval theo policy. |
| **Rất cao** | Cấp quyền admin, đổi tenant owner, thay trust anchor, reset MFA cho admin, disable security control. | Phishing-resistant authentication, dual control, review độc lập, audit và kiểm tra lại trước activation. |

Đây là ma trận ví dụ, không phải chuẩn chung. Tổ chức phải xác định mức theo tài sản, threat model và yêu cầu assurance.

### 3.1. Đánh giá cả actor, session và target

Một thay đổi profile do người dùng tự thực hiện trên session mới xác thực bằng passkey có thể có rủi ro thấp. Cùng thay đổi đó nếu được helpdesk thực hiện cho account quản trị từ ticket bất thường có thể cần kiểm soát cao hơn.

Các yếu tố cần xem xét:
- Actor là owner, admin, helpdesk hay service identity.
- Account đích có quyền gì và thuộc tenant nào.
- Session được tạo khi nào, bằng phương thức nào, có user verification không.
- Context thiết bị/mạng có đáng tin và còn mới không.
- Thay đổi có thể tạo thêm đường đăng nhập hoặc recovery không.
- Có thể đảo ngược và phát hiện thay đổi trái phép dễ đến đâu.
- Thay đổi ảnh hưởng một account hay nhiều người dùng.

## 4. Xác minh trước khi thay đổi

Một session đang hoạt động chỉ chứng minh hệ thống đang chấp nhận session credential. Với thao tác nhạy cảm, cần xác minh rằng actor vẫn kiểm soát account và có đủ assurance.

### 4.1. Re-authentication và step-up

Re-authentication yêu cầu xác thực lại. Step-up yêu cầu phương thức hoặc mức bảo đảm phù hợp hơn. Policy nên xác định:
- Authenticator nào được chấp nhận.
- Có yêu cầu chống phishing không.
- Có yêu cầu user verification không.
- Authentication phải mới trong bao lâu.
- Có cần dùng authenticator đã đăng ký trước thay vì credential vừa thêm không.
- Kết quả step-up gắn với action cụ thể nào và hết hạn khi nào.

Ví dụ, khi đổi recovery email, chỉ gửi OTP tới email mới chưa chứng minh người thực hiện là chủ account. Kẻ tấn công có thể đã kiểm soát session và tự nhập địa chỉ của mình. Có thể yêu cầu passkey đã tồn tại trước khi thay đổi, xác minh email mới, rồi thông báo tới kênh cũ.

### 4.2. Proof of control cho giá trị mới

Một thay đổi chỉ nên được kích hoạt sau khi hệ thống chứng minh actor hoặc account thực sự kiểm soát giá trị mới theo mục đích sử dụng.

| Giá trị được thay đổi | Bằng chứng phù hợp |
| --- | --- |
| Email liên hệ mới | Link/challenge xác minh gửi tới địa chỉ mới. |
| Số điện thoại mới | OTP hoặc phương thức xác minh số theo policy; không dùng nó làm proofing pháp lý. |
| Passkey mới | WebAuthn registration ceremony hợp lệ, challenge mới, origin/RP ID đúng. |
| TOTP mới | Xác minh một mã được tạo từ seed vừa provision; seed không được log. |
| Client certificate | Kiểm tra CSR/proof of possession, identity, CA policy và key usage. |
| IdP mới | Xác minh issuer, metadata, signing keys, tenant và authority của admin. |
| Tenant ownership | Bằng chứng thẩm quyền tổ chức và quy trình chuyển giao đã được phê duyệt. |

Bằng chứng kiểm soát giá trị mới không thay thế xác minh quyền trên account hiện tại. Cần cả hai khi thay đổi ảnh hưởng danh tính hoặc recovery.

### 4.3. Không dùng kênh mới để tự xác minh chính nó

Nếu người dùng yêu cầu thay email recovery từ địa chỉ A sang B, gửi mã xác minh tới B chỉ chứng minh họ truy cập được B. Nó không chứng minh họ có quyền thay đổi account A. Cần xác thực bằng một phương thức đã được tin cậy trước đó hoặc recovery proofing độc lập.

## 5. Thay đổi login identifier và contact information

Email, username và số điện thoại thường được dùng làm login identifier hoặc thông tin liên hệ. Chúng có thể thay đổi, tái cấp hoặc bị chiếm; không nên dùng chúng làm khóa identity bất biến.

### 5.1. Phân biệt email đăng nhập và email khôi phục

Một account có thể có:
- Email dùng để đăng nhập.
- Email nhận thông báo.
- Email recovery.
- Email công việc được đồng bộ từ directory.

Các trường này có mục đích khác nhau. Nếu dùng chung một địa chỉ, phải hiểu rằng thay đổi nó có thể ảnh hưởng nhiều luồng. Không cho phép một email mới tự động trở thành recovery channel trước khi được xác minh và policy chấp thuận.

### 5.2. Quy trình đổi email an toàn

Một quy trình tham khảo:

1. Người dùng yêu cầu thay email và xác định mục đích.
2. Server kiểm tra session, account status và quyền sửa field.
3. Yêu cầu re-authentication/step-up phù hợp.
4. Tạo pending change có challenge ngẫu nhiên, TTL ngắn và gắn với account/request.
5. Gửi link xác minh tới email mới.
6. Thông báo tới email cũ hoặc kênh độc lập đã xác minh.
7. Khi challenge hợp lệ, kiểm tra lại request, trạng thái account và policy.
8. Áp dụng thay đổi nguyên tử; xử lý uniqueness và collision.
9. Hủy challenge, ghi audit và thông báo kết quả.

Không đổi email ngay khi người dùng nhập địa chỉ mới. Trạng thái pending giúp tránh account bị gắn với một địa chỉ chưa được chứng minh.

### 5.3. Username và collision

Username có thể cần unique trong tenant hoặc toàn hệ thống. Khi đổi:
- Chuẩn hóa theo quy tắc nhất quán trước khi kiểm uniqueness.
- Tránh phân biệt Unicode/hoa thường theo cách gây nhầm lẫn.
- Không tiết lộ quá nhiều thông tin về account khác qua lỗi “username đã tồn tại”.
- Giữ internal account ID ổn định; không dùng username làm khóa chính.
- Có policy về alias cũ, thời gian giữ chỗ và khả năng tái sử dụng.
- Ghi audit nhưng tránh đưa dữ liệu nhạy cảm vào log.

Nếu username cũ được tái cấp cho người khác quá sớm, thông báo, liên kết hoặc quy trình recovery cũ có thể bị nhầm sang account mới.

## 6. Thay đổi authenticator và recovery method

Thêm hoặc xóa authenticator là thay đổi trực tiếp cách hệ thống xác thực chủ thể. Đây là mục tiêu hấp dẫn trong account takeover: attacker đã có session yếu có thể thêm credential của họ rồi loại bỏ credential của chủ account.

### 6.1. Thêm passkey hoặc security key

Một quy trình an toàn cần:
- Xác thực actor và account đích.
- Tạo WebAuthn challenge ngẫu nhiên, dùng một lần và có TTL.
- Ràng buộc challenge với user, RP ID, origin, session và transaction.
- Xác minh client data, challenge, origin, RP ID hash, credential public key và user verification theo policy.
- Lưu credential ID/public key và metadata cần thiết.
- Chỉ kích hoạt sau các approval bắt buộc.
- Thông báo cho account owner qua kênh độc lập.

Không lưu private key của passkey trên server. Attestation chỉ nên được yêu cầu khi threat model cần và phải cân nhắc privacy/interoperability.

### 6.2. Thêm hoặc xóa TOTP

TOTP enrollment cần provision seed qua kênh an toàn và xác minh một mã hợp lệ trước khi kích hoạt. Seed là bí mật và không được gửi trong ticket, email hoặc audit log.

Khi xóa TOTP:
- Xác minh actor bằng phương thức còn tin cậy.
- Đảm bảo account không bị mất mọi phương thức đăng nhập/recovery ngoài ý muốn.
- Nếu đây là authenticator cuối cùng, yêu cầu recovery/alternate enrollment trước hoặc quy trình hỗ trợ có proofing.
- Thu hồi session hoặc yêu cầu re-authentication nếu policy đánh giá cần.

### 6.3. Thay recovery method

Recovery email, phone, recovery code hoặc helpdesk path có thể giúp lấy lại account khi mất authenticator. Chúng cũng là đường bypass nếu được thay đổi dễ dàng.

Cần:
- Step-up bằng authenticator đã đăng ký trước nếu có.
- Xác minh kênh mới độc lập.
- Delay có kiểm soát đối với account rủi ro cao.
- Notification tới kênh cũ.
- Thu hồi recovery code cũ khi cấp bộ mới.
- Không để helpdesk tự thêm recovery channel chỉ dựa vào dữ liệu hồ sơ công khai.
- Audit và cung cấp cách báo cáo thay đổi không được yêu cầu.

## 7. Thay đổi identity linking và federation

Account có thể liên kết với một hoặc nhiều IdP. Thêm hoặc gỡ liên kết thay đổi cách external identity được ánh xạ vào account nội bộ.

### 7.1. Không tự link chỉ bằng email

Email có thể không duy nhất, có thể thay đổi, có thể được tái cấp hoặc được một IdP xác minh theo policy khác. Nếu tự động link hai danh tính chỉ vì email trùng nhau, attacker có thể chiếm account hiện có.

Nên dùng định danh issuer và subject đã xác minh, ví dụ cặp (issuer, subject), cùng quy trình chứng minh quyền kiểm soát account đích. Account linking cần ghi rõ:
- Issuer/IdP được tin cậy.
- Subject hoặc external identifier ổn định.
- Account nội bộ đích.
- Tenant và client context.
- Thời điểm, actor, phương thức proofing và approval.
- Cách unlink và xử lý session/token liên quan.

### 7.2. Thay issuer hoặc metadata

Đổi issuer, JWKS URI, signing key, SAML entity ID hoặc endpoint có thể làm thay đổi trust boundary. Đây không phải cập nhật profile thông thường. Cần admin authority, kiểm tra metadata provenance, issuer exact match, signing keys, endpoint allowlist, tenant binding và review độc lập theo policy.

### 7.3. Unlink có thể làm account mất đường đăng nhập

Trước khi gỡ IdP hoặc credential federation:
- Xác định các phương thức đăng nhập còn lại.
- Xác minh owner có thể tiếp tục truy cập.
- Thu hồi session/grant liên quan theo policy.
- Xóa mapping đúng account và tenant.
- Không xóa account nội bộ nếu chỉ yêu cầu unlink external identity.
- Thông báo kết quả và ghi audit.

## 8. Thay đổi role, group và tenant membership

Role và membership không chỉ là thuộc tính hồ sơ. Chúng trực tiếp quyết định authorization.

### 8.1. Authentication không cấp quyền

Người dùng xác thực thành công chỉ chứng minh họ kiểm soát credential hợp lệ theo policy. Điều đó không có nghĩa họ được thêm vào nhóm quản trị hoặc đọc dữ liệu của tenant khác.

Mỗi thay đổi role cần kiểm tra:
- Ai có authority cấp role đó.
- Role có tồn tại trong tenant/resource đích không.
- Người được cấp có đủ điều kiện nghiệp vụ không.
- Có cần ticket, manager approval hoặc dual control không.
- Thời hạn và phạm vi của quyền.
- Quyền có xung đột với separation of duties không.

### 8.2. Least privilege và time-bound access

Ưu tiên cấp đúng quyền tối thiểu cần thiết. Với quyền đặc quyền tạm thời, có thể dùng time-bound elevation: quyền tự hết hạn, cần phê duyệt lại khi gia hạn và có audit cho từng lần sử dụng.

Không gộp role toàn cục vào token nếu quyền cần được kiểm tra theo tenant hoặc resource. Resource server phải kiểm tra object-level authorization và trạng thái membership mới nhất theo yêu cầu nhất quán.

### 8.3. Chuyển tenant

Chuyển account giữa tenant có thể ảnh hưởng dữ liệu, policy, IdP, role và ownership. Cần quy trình chuyển giao được phê duyệt từ bên liên quan, xác định dữ liệu được giữ/chuyển, gỡ membership cũ, cấp membership mới và kiểm tra token/session cũ. Không chỉ cập nhật một trường tenant ID trong account record.

## 9. Thay đổi trạng thái account

Account lifecycle thường có các trạng thái như pending, active, suspended, disabled, locked hoặc closed. Tên và semantics phụ thuộc sản phẩm; điều quan trọng là mọi trạng thái phải có quy tắc xác thực và authorization rõ.

| Trạng thái | Ý nghĩa tham khảo | Hành vi bảo mật |
| --- | --- | --- |
| **Pending** | Account đang chờ proofing, xác minh hoặc phê duyệt. | Không cấp quyền vượt quá onboarding cần thiết. |
| **Active** | Account đủ điều kiện sử dụng theo policy. | Cho phép authentication; authorization vẫn kiểm tra riêng. |
| **Suspended** | Tạm ngừng do review, rủi ro hoặc yêu cầu quản trị. | Từ chối đăng nhập mới và xử lý session hiện có theo policy. |
| **Disabled** | Account bị vô hiệu hóa bởi nguồn có thẩm quyền hoặc admin. | Không chấp nhận credential/session mới; revoke session/token theo yêu cầu. |
| **Locked** | Tạm khóa do chính sách bảo vệ đăng nhập. | Có quy trình unlock an toàn; tránh để attacker gây lockout DoS. |
| **Closed/Deleted** | Quan hệ account kết thúc hoặc account được đóng. | Xử lý retention, token, credential, dữ liệu và khả năng khôi phục theo policy. |

Không dùng một trạng thái duy nhất cho mọi lý do. Ví dụ locked do brute force có thể tự hết hạn; suspended do điều tra bảo mật cần quyết định của người có thẩm quyền; disabled từ HR có thể cần hiệu lực ngay.

### 9.1. Disable account cần xử lý các phiên hiện có

Chặn login mới không đủ nếu session hoặc access token cũ vẫn hoạt động. Tùy kiến trúc:
- Revoke server-side sessions.
- Thu hồi refresh token/grant.
- Đánh dấu account/session version để resource server kiểm tra.
- Giới hạn thời gian access token còn hiệu lực.
- Vô hiệu API key/certificate hoặc credential thuộc account nếu policy yêu cầu.
- Dừng workload/job được gắn với account.
- Ghi audit và thông báo đúng đối tượng.

Với JWT được xác minh offline, token có thể còn hiệu lực đến exp nếu resource server không có cơ chế kiểm tra trạng thái. Hệ thống cần thiết kế thời hạn ngắn hoặc trạng thái online cho các quyền cần thu hồi nhanh.

### 9.2. Reactivation cần kiểm tra lại

Mở lại account không nên chỉ đảo trạng thái disabled thành active. Cần xác minh:
- Lý do đình chỉ đã được giải quyết.
- Actor có quyền re-enable.
- Credential có còn tin cậy hay phải reset/re-enroll.
- Session/token cũ có bị revoke và không được khôi phục.
- Role, tenant membership và recovery method còn đúng.
- Có cần thông báo hoặc review bảo mật sau khi mở lại.

Không tự động kích hoạt lại credential đã bị revoke chỉ vì account được mở.

## 10. Workflow thay đổi có trạng thái và snapshot

Một yêu cầu thay đổi nên có trạng thái riêng để không áp dụng dữ liệu mới trước khi xác minh hoàn tất.

Luồng tham khảo:

    Người yêu cầu
        |
        v
    Tạo change request
        |
        v
    Resolve actor, target account và tenant
        |
        v
    Kiểm tra authority và risk
        |
        v
    Re-authentication / proof of control
        |
        v
    Pending verification hoặc approval
        |
        v
    Kiểm tra lại snapshot và policy
        |
        v
    Apply change atomically
        |
        v
    Revoke/refresh session nếu cần
        |
        v
    Notification + audit

### 10.1. Trạng thái change request

| Trạng thái | Ý nghĩa | Chuyển tiếp hợp lệ |
| --- | --- | --- |
| draft | Đang chuẩn bị thay đổi. | submitted hoặc cancelled. |
| submitted | Đã gửi yêu cầu. | verifying, pending_approval hoặc rejected. |
| verifying | Đang xác minh actor/giá trị mới. | pending_approval, approved hoặc rejected. |
| pending_approval | Đang chờ approver có thẩm quyền. | approved, rejected hoặc expired. |
| approved | Đã được duyệt cho snapshot cụ thể. | applied hoặc expired. |
| applied | Thay đổi đã được commit. | Có thể tạo request mới để thay đổi tiếp. |
| rejected | Bị từ chối. | Request mới nếu có căn cứ. |
| expired | Challenge hoặc approval hết hạn. | Tạo transaction mới. |
| cancelled | Người yêu cầu hủy trước khi áp dụng. | Request mới nếu cần. |

Không cho client tự gửi status cuối. Server phải kiểm tra điều kiện và thực hiện state transition nguyên tử.

### 10.2. Snapshot và fingerprint

Approval cần gắn với nội dung đã xem xét, gồm:
- Account ID ổn định và tenant.
- Actor/requester và target.
- Field thay đổi cùng giá trị cũ/mới hoặc reference an toàn.
- Loại hành động và mục đích.
- Credential ID/public key fingerprint hoặc issuer/subject nếu liên quan.
- Scope/role/resource nếu có.
- Policy version, risk result và thời hạn.
- Approver, thời điểm và quyết định.

Nếu target, tenant, field hoặc credential thay đổi sau khi duyệt, approval cũ không còn áp dụng. Có thể tạo hash/fingerprint trên canonical snapshot và kiểm tra lại trước commit. Không đưa secret hoặc dữ liệu cá nhân thô vào fingerprint log.

## 11. Áp dụng thay đổi an toàn trong hệ thống phân tán

Account modification có thể liên quan nhiều dịch vụ: directory, authentication server, session store, authorization service, IdP, email/SMS provider và audit pipeline. Một thay đổi không thể được coi là hoàn tất chỉ vì một database row đã cập nhật.

### 11.1. Atomicity và optimistic concurrency

Hai admin có thể cùng sửa một account. Nếu không có concurrency control, thay đổi sau có thể ghi đè thay đổi trước hoặc làm mất một kiểm tra bảo mật.

Có thể dùng:
- Version number hoặc ETag cho account/change request.
- Conditional update chỉ khi version vẫn khớp.
- Database transaction cho các trường cần thay đổi cùng nhau.
- Idempotency key để retry không tạo nhiều side effect.
- Outbox/event để phát sự kiện sau khi commit.
- Reconciliation job để phát hiện service downstream chưa đồng bộ.

Ví dụ logic:

    applyAccountChange(request):
        current = loadAccountForUpdate(request.accountId)
        require current.status permits modification
        require request.version == current.version
        require request.snapshotFingerprint == approvedFingerprint
        require authorizationStillValid(request.actor, current, request.change)
        require proofingAndApprovalStillValid(request)

        updated = applyAllowedFields(current, request.change)
        updated.version = current.version + 1

        commitAccountAndAuditAtomically(updated, request)
        publishOutboxEventsAfterCommit(request.id)

Đây là pseudocode minh họa. Không thực hiện network call tới IdP, mail provider hoặc session service trong transaction database dài. Ghi event/outbox sau commit rồi retry downstream theo trạng thái rõ.

### 11.2. TOCTOU: kiểm tra rồi mới thay đổi

Time-of-check to time-of-use xảy ra khi điều kiện đúng lúc kiểm tra nhưng thay đổi trước lúc áp dụng. Ví dụ, approver bị thu hồi role sau khi yêu cầu được duyệt nhưng trước khi credential được kích hoạt.

Với thay đổi nhạy cảm, kiểm tra lại ngay trước commit:
- Actor/approver còn authority theo policy không.
- Account chưa bị suspend/disable.
- Target và tenant vẫn đúng.
- Snapshot chưa thay đổi.
- Challenge và approval còn hạn, chưa dùng.
- Credential proof vẫn khớp request.
- Không có incident flag mới yêu cầu hold.

### 11.3. Event ordering và idempotency

Sự kiện account có thể đến trễ hoặc lặp. Ví dụ event “email changed” đến sau event “account disabled”. Consumer không được kích hoạt account chỉ vì nhận event cũ.

Dùng event ID, aggregate version, occurred-at và idempotency key. Consumer bỏ qua event cũ theo version, xử lý duplicate an toàn và có dead-letter/reconciliation cho lỗi kéo dài. Không dùng timestamp client làm thứ tự duy nhất.

## 12. Notification, delay và khả năng đảo ngược

Thay đổi nhạy cảm cần thông báo cho account owner qua kênh đã xác minh trước đó. Kênh mới vừa được thêm không phải kênh độc lập đủ tin cậy để báo rằng chính nó vừa được thêm.

Notification nên nêu:
- Account/tenant được thay đổi.
- Loại thay đổi và thời điểm.
- Trạng thái pending hay applied.
- Thiết bị hoặc actor ở mức an toàn cần thiết.
- Request/ticket reference.
- Cách báo cáo nếu không phải người dùng yêu cầu.

Không gửi password, OTP, recovery code, private key hoặc token trong thông báo.

### 12.1. Delay cho thay đổi có rủi ro cao

Một số thay đổi có thể áp dụng sau thời gian chờ, ví dụ đổi recovery channel hoặc gỡ authenticator cũ. Delay tạo cơ hội cho chủ account phát hiện và phản đối. Tuy nhiên delay không thay thế xác minh hoặc approval, và không phù hợp cho mọi trường hợp.

Nếu có incident đang diễn ra, có thể cần hold ngay thay vì chờ. Với thay đổi hợp lệ nhưng khẩn cấp, policy có thể cung cấp đường xử lý đặc biệt có audit và approval rõ ràng.

### 12.2. Reversal và rollback

Không phải mọi thay đổi đều có thể đảo ngược hoàn toàn. Có thể:
- Hủy pending change trước khi áp dụng.
- Khôi phục giá trị cũ nếu còn hợp lệ và chưa được tái cấp cho người khác.
- Thu hồi credential mới và yêu cầu enrollment lại.
- Revoke session/token phát sinh từ thay đổi sai.
- Khôi phục role/membership từ audit snapshot sau khi kiểm tra quyền.
- Mở incident nếu dữ liệu đã bị truy cập hoặc chia sẻ.

Rollback phải là một thay đổi mới có audit, không xóa dấu vết lịch sử. Với email/username, giá trị cũ có thể đã được tái sử dụng; không tự động gắn lại nếu chưa kiểm tra collision và ownership.

## 13. Audit và bảo vệ dữ liệu account

Mỗi thay đổi cần tạo audit event đủ để tái dựng actor, target, lý do, quyết định và kết quả.

Một event minh họa:

    {
      "event_id": "evt-4c21",
      "occurred_at": "2026-11-22T06:30:00Z",
      "request_id": "chg-91ab",
      "actor_id": "staff-27",
      "target_account_id": "acct-57",
      "tenant_id": "org-7",
      "action": "account.recovery_email.change",
      "field": "recovery_email",
      "old_value_reference": "masked-or-protected-reference",
      "new_value_reference": "masked-or-protected-reference",
      "approval_id": "apr-93a1",
      "policy_version": "account-change-v4",
      "result": "applied"
    }

Không ghi secret, password, OTP, TOTP seed, private key, recovery code, session cookie, access token hoặc refresh token. Với email/phone, chỉ ghi giá trị đã mask hoặc reference được bảo vệ nếu điều tra cần.

Audit nên được lưu ở nơi người thực hiện thay đổi không thể tự ý sửa/xóa. Phân quyền truy vấn và export audit cũng cần được kiểm soát.

### 13.1. Những trường audit quan trọng

- Event ID, request ID và correlation ID.
- Actor identity, role và tenant.
- Target account ID ổn định.
- Field/action thay đổi và lý do.
- Giá trị cũ/mới ở mức tối thiểu cần thiết.
- Proofing, step-up và approval reference.
- Policy version, risk decision và timestamp.
- Version trước/sau, kết quả downstream và trạng thái rollback.
- Nguồn request và thiết bị/context nếu có mục đích bảo mật rõ ràng.

## 14. API và quyền sửa theo field

Không nên có một API cho phép client gửi cả object account rồi ghi đè tùy ý. Dùng các thao tác có mục đích rõ, schema allowlist và authorization riêng cho từng nhóm field.

Ví dụ endpoint khái niệm:

    PATCH /v1/me/profile
    POST  /v1/me/login-email/change-requests
    POST  /v1/me/recovery-methods
    POST  /v1/me/authenticators/enrollments
    DELETE /v1/me/authenticators/{credentialId}
    POST  /v1/admin/accounts/{accountId}/suspend
    POST  /v1/admin/accounts/{accountId}/roles/change-requests

Server cần:
- Allowlist field được sửa trong từng endpoint.
- Từ chối field hệ thống như account ID, tenant owner, role hoặc status nếu actor không có quyền.
- Validate format và business constraints.
- Resolve target từ session/route và policy, không tin target do body tự chọn.
- Kiểm tra CSRF nếu dùng cookie authentication.
- Áp dụng rate limit cho email/phone verification và enrollment.
- Dùng idempotency key cho thao tác có side effect.
- Trả lỗi không tiết lộ account tồn tại hoặc dữ liệu của người khác.

## 15. Threat model cho account modification

| Mối đe dọa | Cách xảy ra | Tác động | Kiểm soát |
| --- | --- | --- | --- |
| **Account takeover qua recovery** | Attacker chiếm session rồi thay email/phone recovery. | Có đường khôi phục account lâu dài. | Step-up bằng phương thức cũ, verify kênh mới, notification tới kênh cũ, delay/review. |
| **Authenticator injection** | Thêm passkey/TOTP của attacker vào account bị chiếm. | Attacker có credential riêng bền vững. | Re-auth, registration ceremony, pending state, approval theo risk và notification. |
| **Self-privilege escalation** | Người dùng tự thêm role hoặc sửa tenant/owner field. | Vượt quyền quản trị. | Field-level authorization, independent approval, server-side authority check. |
| **Identity linking takeover** | Tự link IdP theo email trùng. | Chiếm account hoặc hợp nhất nhầm identity. | Issuer/subject mapping, proof of control account đích, review. |
| **Tenant confusion** | Sửa account trong tenant khác hoặc dùng event sai tenant. | Truy cập chéo tổ chức. | Tenant-scoped authorization, immutable target binding và audit. |
| **Stale session after disable** | Account bị disable nhưng session/token cũ còn hoạt động. | Truy cập tiếp sau khi mất quyền. | Revoke session/grant, account status check, token lifetime/revocation. |
| **Approval replay** | Dùng approval cũ cho credential/role khác. | Thực thi thay đổi chưa được duyệt. | Snapshot fingerprint, TTL, one-time approval và atomic consume. |
| **Race/TOCTOU** | Authority hoặc target đổi giữa kiểm tra và commit. | Áp dụng thay đổi không còn hợp lệ. | Recheck, version, transaction và conditional update. |
| **Enumeration** | API tiết lộ account tồn tại qua lỗi khác nhau. | Thu thập danh sách người dùng. | Response nhất quán, rate limit và kiểm soát truy cập. |
| **Audit tampering** | Actor tự sửa hoặc xóa log thay đổi. | Mất khả năng điều tra và trách nhiệm. | Audit store tách biệt, append-only và access review. |

## 16. Tình huống thực hành: attacker thay recovery email sau khi chiếm session

**Bối cảnh:** Nhân viên Bình đăng nhập trên máy cá nhân và để session mở. Attacker lấy được cookie session qua một lỗ hổng phía client. Attacker truy cập trang account settings, đổi recovery email sang mailbox của họ, xác minh mailbox mới, sau đó yêu cầu reset password và xóa passkey cũ.

**Phân tích:**

1. Session cookie hợp lệ chứng minh server đang chấp nhận session, nhưng không bảo đảm người gửi request là Bình.
2. Xác minh mailbox mới chỉ chứng minh attacker kiểm soát địa chỉ mới.
3. Nếu hệ thống không yêu cầu re-authentication bằng authenticator cũ, attacker có thể thay đường recovery.
4. Nếu không thông báo tới kênh cũ, Bình khó phát hiện.
5. Nếu thay recovery và xóa passkey được xử lý ngay, attacker có thể duy trì quyền kiểm soát sau khi session ban đầu bị thu hồi.

**Thiết kế lại:**

- Yêu cầu step-up bằng passkey đã đăng ký trước khi thay recovery.
- Gắn yêu cầu với account, giá trị mới và transaction ID; xác minh mailbox mới trong thời hạn ngắn.
- Giữ recovery email cũ hoạt động trong thời gian pending nếu policy cho phép.
- Gửi notification tới kênh cũ đã xác minh và cung cấp cách phản đối.
- Không cho xóa authenticator cuối cùng nếu chưa có phương thức thay thế đã được kích hoạt.
- Áp dụng delay/review cho thay đổi có rủi ro cao.
- Khi có dấu hiệu compromise, revoke session/token, hủy pending change và khởi động incident response.
- Ghi audit đầy đủ nhưng không lưu cookie, token hoặc mã xác minh.

**Câu hỏi:** Nếu Bình không còn passkey cũ vì mất thiết bị thì có nên cho phép đổi recovery email bằng OTP gửi tới email mới không? Không. Cần chuyển sang recovery proofing có thẩm quyền, xác minh độc lập theo mức rủi ro và áp dụng approval/delay tương xứng. Nếu không chứng minh được quyền kiểm soát account, giữ thay đổi ở trạng thái pending hoặc từ chối.

## 17. Checklist thiết kế account modification

- [ ] Phân biệt identity, account, login identifier, credential, session và authorization.
- [ ] Xác định nguồn có thẩm quyền cho từng field và actor được sửa field đó.
- [ ] Phân loại thay đổi theo hậu quả: profile, login, recovery, authenticator, federation, role, tenant và status.
- [ ] Kiểm tra actor, target account, tenant và field-level authorization phía server.
- [ ] Yêu cầu re-authentication/step-up theo độ nhạy và freshness.
- [ ] Xác minh quyền kiểm soát giá trị mới bằng challenge riêng; không dùng kênh mới tự xác minh chính nó.
- [ ] Giữ login identifier và internal account ID tách biệt; không dùng email làm khóa identity bất biến.
- [ ] Không tự link identity chỉ bằng email; ràng buộc issuer/subject và proof of control.
- [ ] Thêm authenticator qua ceremony chuẩn; không lưu private key hoặc seed trong log.
- [ ] Bảo vệ recovery method như một đường xác thực quan trọng.
- [ ] Tách requester, verifier, approver và executor cho thay đổi đặc quyền.
- [ ] Gắn approval với snapshot/fingerprint, TTL và one-time consume.
- [ ] Dùng pending state, verification, notification và delay phù hợp trước activation.
- [ ] Áp dụng thay đổi nguyên tử với version/ETag, idempotency và concurrency control.
- [ ] Recheck authority, account state, target và policy ngay trước commit.
- [ ] Khi disable/suspend, xử lý session, refresh token, API key và credential theo policy.
- [ ] Không tự kích hoạt lại credential đã revoked khi re-enable account.
- [ ] Ghi audit bất biến hoặc append-only; không ghi password, OTP, token, cookie hay private key.
- [ ] Có notification tới kênh cũ đã xác minh cho thay đổi nhạy cảm.
- [ ] Kiểm thử recovery takeover, authenticator injection, self-escalation, tenant confusion, approval replay và race condition.

## 18. Câu hỏi tự kiểm tra

**1. Account modification là gì?**  
Là thay đổi có kiểm soát các thuộc tính, credential, liên kết identity, quyền hoặc trạng thái của account trong vòng đời sử dụng.

**2. Vì sao một session hợp lệ không đủ để đổi recovery method?**  
Session có thể bị đánh cắp hoặc đã xác thực từ lâu. Thay recovery có thể tạo đường chiếm account nên cần step-up bằng phương thức đã tin cậy và proof of control.

**3. Email có nên là khóa identity bất biến không?**  
Không. Email có thể đổi hoặc tái cấp. Dùng internal account ID và mapping issuer/subject ổn định theo policy.

**4. Xác minh email mới có chứng minh người yêu cầu là chủ account không?**  
Không. Nó chỉ chứng minh quyền truy cập địa chỉ mới; cần xác minh độc lập quyền trên account hiện tại.

**5. Vì sao phải có pending state cho thay đổi email hoặc authenticator?**  
Để không kích hoạt giá trị chưa được xác minh hoặc phê duyệt, và cho phép hủy khi challenge hết hạn hoặc phát hiện rủi ro.

**6. Có thể tự thêm role admin vì đã đăng nhập thành công không?**  
Không. Authentication xác minh chủ thể; role change cần authorization và approval theo thẩm quyền.

**7. Account bị disable có cần revoke session không?**  
Thông thường có, theo policy và mức khẩn cấp. Nếu không, session hoặc token cũ có thể tiếp tục truy cập sau khi account mất quyền.

**8. Approval cũ có thể dùng cho credential khác không?**  
Không. Approval cần gắn với request snapshot/fingerprint, target, tenant và credential cụ thể; thay đổi nội dung cần review lại.

**9. Làm thế nào tránh hai admin ghi đè thay đổi của nhau?**  
Dùng version/ETag, conditional update, transaction và kiểm tra snapshot trước commit; xử lý event duplicate/out-of-order.

**10. Audit account modification cần bảo vệ dữ liệu nào?**  
Ghi actor, target, field/action, thời gian, approval và kết quả; không ghi password, OTP, recovery code, private key, cookie hoặc token.

**Ghi nhớ:** Account modification là một phần của bảo mật danh tính. Hãy xác định đúng authority và target, phân loại rủi ro của field, yêu cầu bằng chứng phù hợp, gắn approval với thay đổi cụ thể, áp dụng nguyên tử và thông báo qua kênh độc lập. Khi account hoặc quyền thay đổi, phải xem xét session, token, authenticator và liên kết identity liên quan để trạng thái mới được thực thi nhất quán trên toàn hệ thống.
