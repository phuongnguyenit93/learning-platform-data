# User enrollment — Đăng ký và thiết lập danh tính người dùng an toàn

> **Chương:** Enrollment  
> **Chủ đề:** User enrollment

**User enrollment** là quy trình đưa một người dùng mới vào hệ thống danh tính: tiếp nhận yêu cầu đăng ký, xác minh thông tin cần thiết, tạo hoặc liên kết tài khoản, thiết lập phương thức xác thực ban đầu và kích hoạt quyền truy cập theo chính sách. Enrollment là điểm bắt đầu của vòng đời danh tính; nếu quy trình này yếu, kẻ tấn công có thể tạo tài khoản giả, chiếm tài khoản của người khác, đăng ký credential do họ kiểm soát hoặc tự nhận quyền trong một tổ chức.

Đăng ký tài khoản không chỉ là thu thập email và password. Một hệ thống cần xác định **người đang đăng ký là ai theo mức bảo đảm nào, họ có quyền tham gia tenant/tổ chức nào, credential được gắn với tài khoản ra sao, và ai có thể thay đổi hoặc thu hồi các liên kết đó**. Mức xác minh phải phù hợp với rủi ro và mục đích sử dụng; xác minh email chứng minh quyền truy cập hộp thư tại thời điểm kiểm tra, không tự chứng minh danh tính pháp lý hay tư cách thành viên của tổ chức.

Bài học thuộc module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, kết nối enrollment với credential, password, MFA, passkey, certificate, token, session, SSO, account linking và recovery. Trọng tâm là mô hình hóa ranh giới tin cậy trong đăng ký, chống chiếm dụng danh tính, bảo vệ enrollment token, thiết lập credential an toàn và quản lý vòng đời tài khoản.

## 1. Kết quả học tập

Sau bài học, người học có thể:

1. Phân biệt account registration, identity proofing, credential enrollment, authentication và authorization.
2. Chọn mức xác minh phù hợp với mục đích tài khoản và tác động nếu danh tính bị giả mạo.
3. Thiết kế luồng đăng ký có invitation, email/phone verification, approval hoặc identity proofing khi cần.
4. Bảo vệ enrollment token, activation link, OTP và transaction chống replay, brute force và account enumeration.
5. Thiết lập password, passkey, MFA hoặc client certificate với xác thực lại và ràng buộc đúng tài khoản.
6. Ngăn account pre-hijacking, duplicate identity, tenant confusion và account linking sai.
7. Thiết kế trạng thái tài khoản, audit, thông báo, deprovisioning và recovery.
8. Xây dựng test plan cho enrollment abuse, credential binding và các race condition.

## 2. Enrollment khác gì với đăng ký một biểu mẫu?

Một biểu mẫu có thể thu thập tên, email, số điện thoại và password, nhưng những dữ liệu này chưa đủ để kết luận một người có danh tính hoặc quyền truy cập như họ khai báo.

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Registration** | Có yêu cầu tạo tài khoản mới không? | Người dùng gửi biểu mẫu đăng ký |
| **Identity proofing** | Bằng chứng nào cho thấy người này là người/đối tượng họ khai? | Kiểm tra giấy tờ hoặc đối chiếu nguồn có thẩm quyền khi cần |
| **Contact verification** | Người đăng ký có kiểm soát kênh liên hệ không? | Xác minh email hoặc số điện thoại |
| **Credential enrollment** | Phương thức nào được gắn vào tài khoản? | Tạo password, đăng ký passkey, MFA hoặc certificate |
| **Account activation** | Điều kiện nào phải đạt trước khi tài khoản hoạt động? | Xác minh email và được quản trị viên duyệt |
| **Authorization/provisioning** | Người dùng được truy cập tenant, nhóm và tài nguyên nào? | Gán vai trò học viên cho lớp đã được duyệt |
| **Authentication** | Người dùng chứng minh quyền kiểm soát credential ra sao ở lần đăng nhập? | Dùng passkey hoặc password + MFA |

Các bước có thể diễn ra trong một trải nghiệm liền mạch, nhưng phải giữ rõ mục đích và bằng chứng của từng bước. **Email verified không đồng nghĩa identity verified; account created không đồng nghĩa access granted.**

## 3. Xác định mức bảo đảm cần có

Không phải mọi tài khoản đều cần cùng mức xác minh. Một tài khoản đọc tài liệu công khai có thể chỉ cần xác minh kênh liên hệ; tài khoản truy cập hồ sơ học viên, dữ liệu thanh toán hoặc quyền quản trị cần bằng chứng mạnh hơn.

### 3.1. Đánh giá rủi ro enrollment

Trước khi thiết kế luồng, xác định:

- Tài khoản đại diện cho cá nhân, nhân viên, học viên, thiết bị hay workload?
- Dữ liệu và hành động nào tài khoản có thể truy cập?
- Nếu đăng ký sai người, thiệt hại là gì?
- Tổ chức nào có quyền mời, xác minh hoặc phê duyệt?
- Có nguồn dữ liệu có thẩm quyền để kiểm tra tư cách không?
- Tài khoản có thể được tạo tự do hay phải có invitation/approval?
- Credential ban đầu có thể bị kẻ khác đăng ký trước không?
- Người dùng có thể tự phục hồi khi mất credential không, và recovery mạnh tới đâu?

### 3.2. Mức kiểm tra theo bối cảnh

| Mức kiểm tra | Bằng chứng ví dụ | Phù hợp khi |
| --- | --- | --- |
| **Contact control** | Link email hoặc OTP điện thoại | Chức năng rủi ro thấp, cần xác nhận kênh liên hệ |
| **Organization membership** | Invitation dùng một lần hoặc xác nhận từ quản trị viên | Tài khoản thuộc trường, doanh nghiệp hoặc tenant |
| **Account-to-person binding** | Đối chiếu mã hồ sơ nội bộ với kênh đã xác minh | Cần liên kết tài khoản với bản ghi người dùng có sẵn |
| **Identity proofing** | Kiểm tra bằng chứng định danh và đối chiếu theo quy trình phù hợp | Dịch vụ cần mức bảo đảm danh tính cao |
| **Credential assurance** | Passkey, MFA, certificate hoặc thiết bị quản lý | Cần chứng minh quyền kiểm soát authenticator sau khi xác minh danh tính |

Đây là các nhóm kiểm soát khái quát, không phải thang cấp độ pháp lý. Nếu sản phẩm cần tuân thủ một tiêu chuẩn identity assurance cụ thể, phải áp dụng đúng tiêu chuẩn và quy trình được tổ chức phê duyệt. Không tự gán mức assurance chỉ từ việc người dùng tải ảnh giấy tờ hoặc hoàn tất một cuộc gọi video.

### 3.3. Thu thập dữ liệu tối thiểu

Chỉ yêu cầu thuộc tính phục vụ mục đích đã xác định. Nếu chỉ cần tài khoản đăng nhập bằng email, không thu thập ngày sinh, địa chỉ nhà hoặc ảnh giấy tờ một cách mặc định. Nếu cần đối chiếu học viên với hồ sơ do trường quản lý, ưu tiên mã định danh nội bộ hoặc luồng invitation thay vì sao chép nhiều dữ liệu nhạy cảm.

## 4. Các mô hình enrollment phổ biến

### 4.1. Self-service registration

Người dùng tự tạo tài khoản qua trang đăng ký. Hệ thống có thể xác minh email, yêu cầu password/passkey và giới hạn quyền ban đầu. Phù hợp sản phẩm cho phép người dùng tự tham gia.

Rủi ro chính là bot, spam, email giả, account enumeration, đăng ký trước danh tính người khác và lạm dụng trial/quota. Cần rate limit, abuse detection, xác minh contact và quy trình xử lý duplicate.

### 4.2. Invitation-based enrollment

Quản trị viên hoặc tổ chức mời người dùng. Invitation gắn với tenant, vai trò ban đầu, người mời, thời hạn và địa chỉ/kênh nhận. Người nhận phải chứng minh kiểm soát invitation và hoàn tất các bước credential theo policy.

Invitation không được tự động cấp quyền cao chỉ vì link còn hiệu lực. Cần kiểm tra người nhận có phù hợp với danh tính đã được mời và quyền đã được phê duyệt hay không.

### 4.3. Admin-assisted enrollment

Nhân viên hỗ trợ tạo tài khoản hoặc hỗ trợ người dùng đăng ký. Cần phân quyền rõ: ai được tạo, ai được duyệt, bằng chứng nào phải ghi nhận, và nhân viên có được biết password/OTP của người dùng hay không. Nhân viên không nên đặt password dùng chung hoặc yêu cầu người dùng đọc OTP qua điện thoại.

### 4.4. Federated/SSO enrollment

Người dùng đăng nhập qua IdP của tổ chức. RP xác minh kết quả OIDC/SAML rồi tạo hoặc liên kết tài khoản theo issuer + subject/NameID và tenant policy. Thành công ở IdP không tự chứng minh người dùng được cấp membership trong mọi tenant của RP.

### 4.5. Just-in-time provisioning

JIT provisioning tạo tài khoản khi người dùng lần đầu đăng nhập SSO. Cần xác định nguồn thuộc tính đáng tin, quyền mặc định, tenant mapping, duplicate policy và trạng thái khi IdP deactivate người dùng. Không cấp role đặc quyền chỉ vì IdP gửi một group claim chưa được ánh xạ/cho phép.

## 5. Luồng enrollment an toàn tổng quát

Một luồng có thể gồm các giai đoạn sau:

~~~mermaid
flowchart TD
    A["Bắt đầu đăng ký / nhận invitation"] --> B["Kiểm tra eligibility và rate limit"]
    B --> C["Thu thập dữ liệu tối thiểu"]
    C --> D["Xác minh contact / invitation"]
    D --> E["Identity proofing hoặc organization approval nếu cần"]
    E --> F["Tạo hoặc liên kết account"]
    F --> G["Enrollment credential ban đầu"]
    G --> H["Áp dụng policy MFA / passkey / certificate"]
    H --> I["Kích hoạt account theo policy"]
    I --> J["Tạo session giới hạn và thông báo"]
    J --> K["Theo dõi, audit và quản lý vòng đời"]
~~~

Không phải sản phẩm nào cũng cần tất cả bước. Hãy bỏ bước không phục vụ mục đích, nhưng không bỏ bằng chứng mà rủi ro yêu cầu. Nếu invitation hoặc approval chưa đạt, tài khoản có thể ở trạng thái pending và chưa có quyền truy cập dữ liệu.

### 5.1. Transaction enrollment

Mỗi lần đăng ký nên có transaction ID ngẫu nhiên, purpose rõ, subject/tenant dự kiến, thời điểm tạo/hết hạn và trạng thái. Link verification, OTP, invitation và credential enrollment phải gắn với đúng transaction; không để một token xác minh email được dùng để thay đổi password hoặc thêm passkey ngoài mục đích ban đầu.

### 5.2. Tách bước xác minh khỏi bước kích hoạt

Một email được xác minh có thể chỉ đánh dấu contact là verified. Account vẫn có thể pending approval, chưa có tenant membership hoặc chưa được phép truy cập dữ liệu. Trạng thái phải thể hiện rõ và server-side policy phải kiểm tra trước khi cấp session/quyền.

## 6. Xác minh email và số điện thoại

Contact verification chứng minh người đăng ký có khả năng nhận thông điệp tại một địa chỉ/kênh tại thời điểm kiểm tra. Nó không chứng minh chắc chắn chủ sở hữu pháp lý, nhân viên hiện tại hay người được trường cấp quyền.

### 6.1. Email verification link

Một link xác minh nên:

- Chứa token ngẫu nhiên đủ mạnh, khó đoán;
- Được lưu server-side dưới dạng hash hoặc tham chiếu không tiết lộ token;
- Gắn với account/enrollment transaction và purpose cụ thể;
- Có thời hạn ngắn, giới hạn lần thử và chỉ sử dụng một lần;
- Được tiêu thụ nguyên tử để hai request đồng thời không cùng xác minh;
- Không chứa email, user ID nhạy cảm hoặc quyền trong URL;
- Không tự động tạo session đặc quyền chỉ vì link được mở.

Một số hệ thống email security scanner tự động mở link. Vì vậy, không nên để HTTP GET đơn thuần lập tức tiêu thụ token và kích hoạt account theo cách khiến scanner có thể hoàn tất thao tác. Có thể hiển thị trang xác nhận và yêu cầu thao tác chủ động bằng POST, đồng thời bảo vệ CSRF và kiểm tra transaction.

### 6.2. OTP qua SMS/email

OTP cần:

- Được sinh ngẫu nhiên, có entropy phù hợp độ dài;
- Có TTL ngắn và giới hạn số lần thử;
- Gắn với đúng account, purpose và transaction;
- Chỉ dùng một lần;
- Không ghi plaintext vào log;
- Rate limit theo account, destination, IP/device signal và toàn dịch vụ;
- Không gửi mã mới liên tục mà không có cooldown.

OTP ngắn có thể bị đoán nếu không giới hạn thử. Không dùng cùng một OTP cho xác minh email, reset password và thêm MFA. Nếu dùng SMS, đánh giá rủi ro SIM swap, chuyển tiếp tin nhắn và chiếm số điện thoại; SMS không nên là lựa chọn mạnh nhất cho tài khoản đặc quyền.

### 6.3. Thông báo lỗi và account enumeration

Thông báo như “email này đã có tài khoản” có thể giúp attacker dò danh sách người dùng. Cân nhắc phản hồi chung ở điểm công khai, ví dụ thông báo rằng nếu địa chỉ đủ điều kiện thì hướng dẫn tiếp theo sẽ được gửi. Trải nghiệm hỗ trợ có thể cung cấp thêm thông tin sau khi người dùng chứng minh quyền kiểm soát kênh.

## 7. Invitation và mã tham gia tổ chức

Invitation thường cấp quyền bắt đầu enrollment trong một tenant hoặc nhóm. Nó là một credential tạm thời và cần được bảo vệ như vậy.

### 7.1. Thuộc tính invitation

Một invitation record nên gắn:

- Invitation ID và token hash;
- Tenant/organization;
- Người mời và quyền mời;
- Email hoặc subject dự kiến nếu policy yêu cầu ràng buộc;
- Vai trò/quyền dự kiến, tốt nhất ở mức tối thiểu;
- Purpose và thời điểm hết hạn;
- Trạng thái pending, accepted, expired, revoked;
- Account/subject đã chấp nhận và thời điểm.

### 7.2. Quy tắc chấp nhận

1. Xác minh token tồn tại, còn hạn và chưa bị thu hồi/tiêu thụ.
2. Xác minh người chấp nhận đúng recipient hoặc đáp ứng chính sách tổ chức.
3. Kiểm tra tenant vẫn active và người mời còn quyền cấp invitation.
4. Hiển thị tổ chức và vai trò dự kiến để người dùng hiểu họ đang tham gia đâu.
5. Tạo/liên kết account theo policy; không gộp chỉ vì email giống nhau.
6. Tiêu thụ invitation và gán membership trong một transaction nguyên tử.
7. Ghi audit và thông báo cho người mời/người nhận theo policy.

### 7.3. Mã tham gia dùng chung

Mã lớp hoặc mã tổ chức dùng chung tiện lợi nhưng dễ bị phát tán. Nếu dùng, giới hạn thời hạn, quota, quyền mặc định và khả năng thu hồi; không cho mã đó tự cấp vai trò quản trị. Có thể yêu cầu quản trị viên duyệt membership sau khi người dùng nhập mã.

## 8. Identity proofing và xác minh tư cách

Khi hệ thống cần biết người đăng ký là một cá nhân cụ thể hoặc có tư cách tham gia tổ chức, contact verification không đủ. Cần nguồn bằng chứng phù hợp.

### 8.1. Các loại bằng chứng

- Hồ sơ người dùng đã có trong hệ thống của tổ chức;
- Invitation do quản trị viên có thẩm quyền gửi;
- Mã nhân viên/học viên được đối chiếu với nguồn authoritative;
- Xác minh qua IdP doanh nghiệp/trường học đã được tin cậy;
- Giấy tờ hoặc quy trình kiểm tra danh tính khi mục đích và quy định yêu cầu;
- Xác nhận trực tiếp từ người có trách nhiệm.

Không có một loại bằng chứng phù hợp mọi trường hợp. Dữ liệu giấy tờ có thể giả, lỗi OCR hoặc không còn cập nhật; email tổ chức có thể được tái cấp; invitation có thể bị chuyển tiếp. Kết hợp các tín hiệu theo rủi ro và quy trình xử lý ngoại lệ.

### 8.2. Human review

Nếu cần người duyệt, xác định rõ:

- Reviewer có quyền và được đào tạo không;
- Reviewer nhìn thấy bằng chứng tối thiểu nào;
- Có yêu cầu phân tách người đề nghị và người phê duyệt không;
- Cách xử lý xung đột hoặc hồ sơ nghi ngờ;
- Lý do duyệt/từ chối và audit được lưu ra sao;
- Cách người dùng khiếu nại hoặc bổ sung bằng chứng.

Không để nhân viên hỗ trợ tự nâng quyền chỉ bằng việc người gọi biết email, tên hoặc vài thông tin công khai.

### 8.3. Quyền riêng tư

Identity proofing có thể thu thập dữ liệu nhạy cảm. Chỉ thu thập những gì cần, giải thích mục đích, hạn lưu, ai có thể truy cập và cách xóa. Không giữ bản sao giấy tờ lâu hơn yêu cầu; nếu chỉ cần kết quả kiểm tra, cân nhắc lưu trạng thái/bằng chứng tối thiểu thay vì toàn bộ hình ảnh.

## 9. Tạo tài khoản và xử lý danh tính trùng

Trước khi tạo account, cần kiểm tra xem đã có principal tương ứng chưa và nguồn nào có thẩm quyền xác định uniqueness.

### 9.1. Không dựa riêng vào email

Email có thể thay đổi, được tái cấp, có alias hoặc dùng chung. Một email giống nhau không đủ chứng minh hai yêu cầu đăng ký thuộc cùng một người. Với OIDC, identity key thường là issuer + sub; với SAML, dùng issuer/entity ID kết hợp NameID theo format/namespace; với tài khoản nội bộ, dùng ID bất biến do hệ thống cấp.

### 9.2. Unique constraint và race

Hai request đăng ký cùng email hoặc cùng external subject có thể đến đồng thời. Kiểm tra rồi insert không có transaction có thể tạo duplicate. Dùng unique constraint ở database cho khóa danh tính đã chọn, transaction và xử lý conflict rõ ràng.

Không tự động chuyển một account đã có sang người đăng ký mới chỉ vì email vừa được xác minh. Nếu email được tái cấp, cần quy trình đổi chủ hoặc liên kết có xác thực lại.

### 9.3. Account linking

Khi người dùng thêm IdP hoặc credential khác vào tài khoản hiện có:

1. Yêu cầu reauthentication với tài khoản hiện tại bằng phương thức phù hợp;
2. Tạo linking transaction có purpose, state/nonce và TTL;
3. Xác minh IdP/credential mới theo đúng giao thức;
4. Kiểm tra danh tính mới chưa thuộc account khác;
5. Yêu cầu xác nhận rõ hành động liên kết;
6. Ghi liên kết nguyên tử và audit;
7. Thông báo qua kênh đã đăng ký;
8. Cung cấp cách gỡ liên kết có xác thực lại và không làm mất phương thức đăng nhập cuối cùng ngoài ý muốn.

Không liên kết account chỉ vì người dùng đăng nhập bằng một email trùng. Nếu xung đột, yêu cầu quy trình support có xác minh và lưu dấu vết.

## 10. Enrollment password an toàn

Nếu hệ thống cho phép password, enrollment phải bảo vệ password ngay khi nhận:

- Gửi qua HTTPS và không ghi password vào log/analytics;
- Kiểm tra độ dài và blocklist password phổ biến/bị lộ theo policy;
- Không áp đặt quy tắc composition vô ích khiến người dùng chọn password dễ đoán;
- Không yêu cầu đổi password định kỳ nếu không có dấu hiệu compromise hoặc yêu cầu chính sách;
- Hash bằng password KDF chuyên dụng với salt riêng và tham số phù hợp;
- Không dùng SHA-256 đơn lẻ hoặc mã hóa reversible để lưu password;
- Không trả password ban đầu qua email hoặc cho nhân viên hỗ trợ biết.

Nếu user được cấp temporary password, bắt buộc đổi sau lần đăng nhập đầu tiên và bảo vệ quy trình chuyển giao. Tốt hơn, dùng activation link ngắn hạn để người dùng tự thiết lập password hoặc passkey.

## 11. Enrollment passkey/WebAuthn

Passkey là credential khóa công khai. Khi đăng ký, authenticator tạo key pair; private key được giữ trong authenticator, server lưu public key và credential metadata. Server cần xác minh registration response theo WebAuthn, không chỉ lưu public key client gửi.

### 11.1. Trước khi đăng ký

- Người dùng phải đang ở đúng account và có session đủ assurance;
- Với tài khoản mới, enrollment transaction phải gắn với account vừa được xác minh;
- Thêm passkey vào account hiện có cần reauthentication hoặc step-up;
- UI phải giải thích passkey sẽ được gắn với tài khoản nào và tên thiết bị là gì.

### 11.2. Luồng đăng ký khái quát

~~~mermaid
sequenceDiagram
    participant U as Người dùng / Browser
    participant R as RP server
    participant A as Authenticator
    U->>R: Bắt đầu thêm passkey
    R->>R: Kiểm tra session, quyền và purpose
    R->>R: Tạo challenge ngẫu nhiên, lưu transaction
    R-->>U: PublicKeyCredentialCreationOptions
    U->>A: Tạo credential
    A->>A: Tạo key pair và giữ private key
    A-->>U: Attestation/registration response
    U->>R: Gửi registration response
    R->>R: Kiểm tra challenge, origin, RP ID hash, flags, credential ID
    R->>R: Xác minh attestation theo policy nếu yêu cầu
    R->>R: Lưu public key và credential metadata
    R-->>U: Passkey được đăng ký
~~~

### 11.3. Kiểm tra registration response

Server cần xác minh theo WebAuthn:

- Challenge khớp transaction đang chờ và chưa dùng;
- Origin đúng allowlist của RP;
- RP ID hash khớp RP ID dự kiến;
- Type và dữ liệu client/authenticator hợp lệ;
- User presence/user verification flags đáp ứng policy;
- Credential ID chưa bị gắn với principal khác theo uniqueness policy;
- Public key và credential data được parse bằng thư viện chuẩn;
- Attestation được xử lý theo policy, không mặc định tin mọi attestation.

Attestation không phải lúc nào cũng cần thiết hoặc có thể xác định chính xác danh tính người dùng. Nhiều passkey consumer dùng attestation none/anonymized; mức xác minh danh tính vẫn đến từ enrollment/proofing riêng.

### 11.4. Bảo vệ thao tác thêm passkey

Attacker chiếm session có thể thêm passkey của họ rồi duy trì quyền sau khi password được đổi. Vì vậy, thêm passkey cần xác thực lại đủ mạnh, thông báo qua kênh đã đăng ký và audit. Gỡ passkey cuối cùng hoặc thay phương thức recovery cũng cần kiểm soát tương đương.

## 12. Enrollment MFA và authenticator khác

MFA enrollment gắn một authenticator với account để dùng ở lần đăng nhập sau. Đây là thao tác thay đổi credential và cần ràng buộc với đúng người dùng.

### 12.1. TOTP authenticator

Server tạo secret TOTP riêng cho account, hiển thị QR/provisioning URI qua một phiên bảo mật, rồi yêu cầu người dùng nhập mã hiện tại để xác nhận họ đã cấu hình ứng dụng. Sau khi xác minh, server mới kích hoạt credential. Secret TOTP phải được lưu có bảo vệ vì server cần dùng để xác minh mã.

Không ghi provisioning URI hoặc secret vào log, analytics hay screenshot support. Nếu người dùng chưa hoàn tất xác nhận, giữ enrollment ở trạng thái pending và xóa secret pending sau TTL.

### 12.2. Push authenticator

Thiết bị cần được liên kết qua ứng dụng đã xác thực và transaction enrollment. Hiển thị context, number matching nếu có, chống push fatigue và giới hạn số lần thử. Không cho phép đăng ký thiết bị mới chỉ bằng một push gửi tới thiết bị chưa được tin cậy.

### 12.3. Security key và client certificate

Security key/WebAuthn cần xác minh challenge/origin/RP ID theo giao thức. Client certificate cần quy trình cấp phát PKI, kiểm tra subject/SAN, bảo vệ private key và mapping principal. Một thiết bị được enrollment không tự chứng minh người đang sử dụng nó là người dùng cụ thể.

### 12.4. Recovery code

Recovery code nên được sinh ngẫu nhiên, chỉ hiển thị một lần, lưu dạng hash nếu chỉ cần xác minh và tiêu thụ một lần. Người dùng cần được hướng dẫn lưu an toàn. Tạo bộ recovery code mới phải vô hiệu bộ cũ và thông báo.

## 13. Enrollment token, activation link và OTP

Các token tạm thời trong enrollment là credential có thời hạn. Mỗi token phải gắn đúng purpose, account, transaction và trạng thái.

### 13.1. Token design

Một token enrollment nên:

- Có entropy cao từ CSPRNG;
- Không chứa dữ liệu cá nhân hoặc quyền ở dạng đọc được;
- Lưu hash hoặc tham chiếu an toàn phía server;
- Có TTL ngắn, một lần và có thể revoke;
- Gắn với account/tenant/purpose cụ thể;
- Bị tiêu thụ nguyên tử;
- Không được dùng lại cho reset password, link account hoặc thay MFA nếu purpose khác.

### 13.2. Tránh token leakage

- Dùng HTTPS;
- Không đặt token trong URL query nếu có thể tránh; nếu link cần token, giảm rò rỉ qua Referer, analytics và access log;
- Trang activation dùng Referrer-Policy phù hợp và không tải tài nguyên bên thứ ba không cần thiết;
- Không hiển thị token trong log hoặc error message;
- Sau khi xác minh, chuyển sang URL sạch và xóa token khỏi browser history khi có thể;
- Không để token xuất hiện trong screenshot/ticket support.

### 13.3. One-time consumption

Nếu hai request cùng dùng activation token, chỉ một request được phép thành công. Kiểm tra trạng thái và đánh dấu consumed phải nguyên tử. Request thứ hai phải nhận kết quả đã dùng/hết hạn và không tạo session hoặc lặp lại tác vụ.

## 14. Chống account pre-hijacking và enrollment abuse

**Account pre-hijacking** xảy ra khi attacker tạo hoặc chiếm trước một tài khoản dựa trên thông tin của nạn nhân, rồi chờ nạn nhân hoàn tất đăng ký hoặc liên kết dịch vụ. Một số biến thể liên quan tới email chưa được xác minh, password do attacker đặt trước hoặc federation account linking sai.

### 14.1. Kịch bản thường gặp

- Attacker đăng ký email của nạn nhân và đặt password; nạn nhân sau đó xác minh email và tưởng tài khoản là của mình;
- Attacker mời địa chỉ email sai hoặc chuyển tiếp invitation;
- RP tự động liên kết account theo email, khiến IdP của attacker được gắn vào account nạn nhân;
- Attacker tạo tenant membership trước khi người có thẩm quyền xác minh;
- Bot tạo hàng loạt account và chiếm quota hoặc tên người dùng.

### 14.2. Kiểm soát

- Không cấp quyền hoặc coi account là đã thuộc về một người trước khi hoàn tất xác minh cần thiết;
- Với account pre-created từ dữ liệu tổ chức, dùng invitation/activation gắn với subject và tenant, không cho người biết email tự nhận account;
- Không cho phép password do một bên đặt trước được giữ sau khi người dùng thật nhận account mà không có quy trình reset/claim an toàn;
- Không tự động account-link theo email;
- Giới hạn số lần đăng ký, gửi OTP và tạo invitation;
- Có cảnh báo khi credential hoặc IdP mới được thêm;
- Xử lý duplicate và conflict bằng quy trình có xác minh.

### 14.3. Rate limit và bot defense

Áp dụng quota theo IP/source, account identifier đã chuẩn hóa, destination, tenant, device signal và toàn dịch vụ. CAPTCHA hoặc challenge bổ sung có thể giúp chống bot nhưng không thay thế rate limit và không nên là bằng chứng danh tính. Tránh khóa cứng một email chỉ vì nhiều request; attacker có thể dùng cơ chế đó để gây DoS cho nạn nhân.

## 15. Trạng thái tài khoản và kích hoạt

Account lifecycle cần trạng thái rõ ràng để không cấp quyền trước khi điều kiện enrollment hoàn tất.

~~~mermaid
stateDiagram-v2
    [*] --> Requested: Đăng ký hoặc invitation
    Requested --> PendingVerification: Chờ xác minh contact/bằng chứng
    PendingVerification --> PendingApproval: Contact/proofing đạt, cần duyệt
    PendingVerification --> Rejected: Bằng chứng không đạt
    PendingApproval --> Active: Được phê duyệt
    PendingApproval --> Rejected: Bị từ chối
    Requested --> Active: Luồng tự đăng ký rủi ro thấp đạt policy
    Active --> Suspended: Vi phạm/rủi ro/tạm ngừng
    Active --> Deprovisioned: Rời tổ chức hoặc đóng account
    Suspended --> Active: Khôi phục theo quy trình
    Suspended --> Deprovisioned: Chấm dứt
    Rejected --> [*]
    Deprovisioned --> [*]
~~~

Tên trạng thái có thể khác nhau theo hệ thống. Phải xác định hành động nào được phép ở từng trạng thái:

| Trạng thái | Đăng nhập? | Truy cập dữ liệu? | Hành động tiếp theo |
| --- | --- | --- | --- |
| **Requested** | Không | Không | Xác minh hoặc hủy |
| **Pending verification** | Chỉ vào luồng enrollment giới hạn | Không | Hoàn tất contact/proofing |
| **Pending approval** | Có thể cho session giới hạn nếu cần | Không hoặc rất hạn chế | Chờ reviewer/admin |
| **Active** | Có theo policy | Theo authorization | Sử dụng bình thường |
| **Suspended** | Từ chối hoặc chỉ vào recovery/support | Không | Điều tra/khôi phục |
| **Rejected** | Không | Không | Khiếu nại hoặc đăng ký lại theo policy |
| **Deprovisioned** | Không | Không | Retention/xóa theo chính sách |

Không chỉ ẩn nút trên UI. Backend phải kiểm tra account state ở các endpoint đăng nhập, session refresh, API và thay đổi credential.

## 16. Phân quyền ban đầu và tenant membership

Tạo account và cấp quyền nên là hai quyết định riêng. Một user có thể có account toàn cục nhưng chưa thuộc tenant nào, hoặc thuộc nhiều tenant với role khác nhau.

### 16.1. Quyền tối thiểu

- Account mới không mặc định là admin;
- Invitation chỉ cấp role đã được người mời có thẩm quyền phê duyệt;
- Group/role claim từ IdP phải qua mapping allowlist;
- Tenant được xác định từ trust registry hoặc invitation server-side;
- Người dùng không thể tự gửi tenant ID/role trong form để tự cấp quyền;
- Quyền nhạy cảm cần approval/step-up riêng.

### 16.2. Ví dụ nền tảng học tập

Một học viên có thể tự đăng ký tài khoản nhưng chỉ được xem nội dung công khai. Để vào lớp của trường A, học viên cần invitation hoặc mã hồ sơ được trường xác minh. Giáo viên cần được quản trị viên trường phê duyệt vai trò; không được cấp role instructor chỉ vì người đăng ký chọn “Teacher” trong biểu mẫu.

### 16.3. Tài khoản dịch vụ và workload

Service account/workload enrollment khác người dùng. Không tạo service credential qua biểu mẫu self-service dành cho con người. Cần workload identity, quyền tạo principal được kiểm soát, certificate/token ngắn hạn, scope tối thiểu và deprovisioning khi workload bị xóa.

## 17. Thông báo, audit và bảo vệ quyền riêng tư

Enrollment làm thay đổi bề mặt xác thực của account. Người dùng và tổ chức cần biết khi credential hoặc liên kết mới được thêm.

### 17.1. Sự kiện nên ghi

- Enrollment request được tạo, duyệt, từ chối hoặc hết hạn;
- Email/phone được xác minh (không lưu OTP);
- Invitation được phát hành/thu hồi/chấp nhận;
- Identity proofing result và reviewer reference;
- Password/passkey/MFA/certificate được thêm hoặc gỡ;
- Account linking/unlinking và tenant membership thay đổi;
- Account activation, suspension, deprovisioning;
- Session/token được tạo hoặc thu hồi trong các thao tác nhạy cảm.

### 17.2. Không ghi bí mật

Không ghi password, OTP, activation token, invitation token, private key, TOTP secret, recovery code, session cookie hoặc access/refresh token nguyên dạng. Log nên dùng event ID, subject reference, key ID/credential ID đã được bảo vệ và reason code.

### 17.3. Thông báo người dùng

Thông báo qua kênh đã đăng ký khi:

- Account được kích hoạt;
- Passkey/MFA/certificate mới được thêm;
- Email/phone/recovery channel thay đổi;
- IdP mới được liên kết;
- Invitation được chấp nhận vào tenant;
- Account bị suspend hoặc có thay đổi nhạy cảm.

Thông báo không nên chứa credential hay link có quyền quá rộng. Nếu cần link xử lý sự cố, link phải có purpose, TTL và xác thực bổ sung.

## 18. Recovery và thay đổi sau enrollment

Enrollment tốt cần tính đến tình huống người dùng mất thiết bị hoặc không còn truy cập email/phone ban đầu.

- Đăng ký nhiều phương thức xác thực dự phòng khi phù hợp;
- Sinh recovery code sau khi account được kích hoạt;
- Có quy trình đổi email/phone yêu cầu xác minh kênh mới và kiểm tra kênh cũ;
- Thay recovery channel hoặc gỡ authenticator cuối cùng cần reauthentication/step-up;
- Helpdesk không được bypass MFA chỉ dựa trên thông tin công khai;
- Recovery phải audit, thông báo và có thời gian chờ/kiểm soát bổ sung nếu rủi ro cao;
- Sau recovery do compromise, thu hồi session/token/credential đáng ngờ.

Recovery không nên yếu hơn đáng kể so với enrollment và authentication. Nếu người dùng có thể bỏ qua passkey mạnh bằng cách trả lời vài câu hỏi công khai, kẻ tấn công sẽ nhắm vào recovery.

## 19. Provisioning và deprovisioning trong tổ chức

Với tổ chức, enrollment thường gắn với vòng đời nhân sự/học viên:

- **Pre-provisioning:** tạo account record từ nguồn authoritative trước ngày bắt đầu;
- **Claim/activation:** người dùng chứng minh quyền nhận account và thiết lập credential;
- **Provisioning:** tạo membership/group/role theo policy;
- **Update:** đổi tên, tenant, department hoặc trạng thái;
- **Deprovisioning:** thu hồi membership, credential, session và token khi người dùng rời tổ chức.

SCIM có thể đồng bộ user/group lifecycle giữa IdP và ứng dụng, nhưng SCIM provisioning không tự chứng minh người dùng đang đăng nhập là chủ thể hợp lệ. RP vẫn cần xác thực qua OIDC/SAML hoặc phương thức phù hợp.

Khi deprovision, không chỉ đặt cờ inactive. Cần xử lý session cục bộ, refresh token, access token còn hạn, API key, certificate, linked identity và quyền ở tenant theo SLA.

## 20. Ví dụ xuyên suốt: enrollment cho nền tảng học tập

Một trường triển khai portal cho học viên, giảng viên và quản trị viên. Tài khoản học viên được tạo từ danh sách do trường cung cấp; giảng viên cần được trưởng bộ môn phê duyệt; quản trị viên dùng passkey hoặc security key.

### 20.1. Học viên

1. Trường tạo invitation gắn với mã hồ sơ và tenant A.
2. Học viên mở link, hệ thống kiểm tra token còn hạn và chưa dùng.
3. Học viên xác minh email hoặc kênh được trường đăng ký.
4. RP đối chiếu mã hồ sơ với nguồn authoritative; không chỉ dựa trên email.
5. Học viên tạo passkey hoặc password theo policy.
6. Invitation được tiêu thụ nguyên tử, account active với role learner.
7. Hệ thống thông báo và ghi audit.

### 20.2. Giảng viên

1. Giảng viên được mời qua email tổ chức hoặc IdP của trường.
2. RP xác minh issuer + subject và tư cách thành viên.
3. Reviewer có thẩm quyền phê duyệt role instructor.
4. Giảng viên đăng ký passkey/MFA và xác thực lại để hoàn tất.
5. Role được gán từ nguồn approval server-side, không lấy từ form người dùng.

### 20.3. Quản trị viên

1. Account được tạo qua quy trình admin có phân tách nhiệm vụ.
2. Danh tính và quyền quản trị được xác minh qua nguồn authoritative.
3. Admin đăng ký passkey/security key; thao tác này yêu cầu session đủ assurance.
4. Có phương thức dự phòng được kiểm soát, recovery code và thông báo.
5. Mọi thay đổi credential/role đều được audit và có thể thu hồi.

## 21. Pseudocode enrollment tham khảo

~~~text
complete_enrollment(transaction_id, proof, credential_response):
    tx = load_enrollment_transaction_for_update(transaction_id)
    require tx exists
    require tx.status == PENDING
    require now < tx.expires_at
    require tx.purpose == USER_ENROLLMENT

    verify_required_contact_or_identity_proof(tx, proof)
    verify_tenant_and_invitation_authority(tx)

    identity_key = derive_authoritative_identity_key(tx)
    account = find_account_by_identity_key(identity_key)
    if account exists:
        return handle_duplicate_or_claim_flow(account, tx)

    verify_credential_enrollment_response(
        credential_response,
        account_context = tx,
        expected_origin = configured_origin
    )

    begin transaction
    create_account_with_minimum_privileges(identity_key, tx.tenant)
    bind_credential_to_account(credential_response)
    consume_invitation_or_enrollment_token(tx)
    set_account_state_according_to_policy()
    write_audit_event_without_secrets()
    commit

    notify_user_through_verified_channel()
~~~

Đây là pseudocode mô tả trách nhiệm, không phải mã production. Cần xử lý unique constraint, concurrent enrollment, transaction rollback, notification retry, credential verification theo giao thức và các trường hợp account đã tồn tại.

## 22. Kiểm thử user enrollment

Kiểm thử trong môi trường staging với tenant, invitation, email và credential thử nghiệm.

| Nhóm | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| Contact verification | Link email đúng, còn hạn | Đánh dấu contact verified cho đúng transaction |
| Expired token | Activation link hết hạn | Từ chối, không kích hoạt account |
| Replay | Dùng lại link/OTP đã tiêu thụ | Request sau bị từ chối |
| Concurrent consume | Hai request cùng dùng invitation | Chỉ một request chấp nhận |
| Wrong purpose | Dùng email token để reset password hoặc link IdP | Từ chối |
| Wrong recipient | Người khác nhận invitation gắn recipient cụ thể | Từ chối hoặc yêu cầu quy trình chuyển giao có duyệt |
| Tenant confusion | Invitation tenant A được dùng cho tenant B | Từ chối |
| Account enumeration | Thử email đã tồn tại và chưa tồn tại | Phản hồi công khai không làm lộ danh sách account |
| Duplicate identity | Hai request đồng thời tạo cùng identity key | Unique constraint/transaction ngăn duplicate |
| Pre-hijacking | Attacker tạo account trước chủ sở hữu email | Claim/activation flow không giữ credential do attacker đặt |
| Password storage | Kiểm tra database/log | Không có plaintext password; dùng password KDF |
| Passkey origin | Registration response từ origin khác | Từ chối |
| Passkey challenge | Challenge sai hoặc đã dùng | Từ chối |
| MFA enrollment | TOTP/push chưa xác minh | Credential vẫn pending, không active |
| Credential binding | Credential đã gắn với account khác | Từ chối hoặc xử lý conflict có xác minh |
| Role assignment | Người dùng tự gửi role admin trong form | Bị bỏ qua; role chỉ từ nguồn có thẩm quyền |
| Approval | Reviewer không có quyền duyệt | Từ chối |
| Rate limit | Bot gửi nhiều OTP/invitation request | Quota/cooldown được áp dụng |
| Notification | Thêm passkey hoặc đổi recovery channel | Gửi thông báo không chứa bí mật |
| Deprovision | User bị deactivate | Session/token/credential/membership được xử lý theo SLA |
| Logging | Bật debug và tracing | Không log password, OTP, token hoặc private key |

### 22.1. Bất biến bảo mật

- Không có account active hoặc quyền truy cập trước khi đạt điều kiện enrollment;
- Mỗi token chỉ dùng cho đúng purpose, subject, tenant và một lần;
- Credential mới chỉ gắn vào account sau khi xác minh response và transaction;
- Một external identity không thể bị gắn vào hai account ngoài policy;
- Người đăng ký không tự cấp role hoặc tenant bằng dữ liệu client gửi;
- Thêm/gỡ authenticator và recovery channel được xác thực lại, audit và thông báo;
- Request lặp hoặc đồng thời không tạo duplicate account/membership;
- Không ghi bí mật vào log hoặc thông báo.

## 23. Những lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Coi email verified là identity proofed | Người kiểm soát mailbox được cấp danh tính/quyền quá mức | Tách contact verification khỏi proofing và approval |
| Account active ngay khi tạo biểu mẫu | Tài khoản giả truy cập trước khi xác minh | Pending state và activation policy |
| Invitation không ràng buộc tenant/recipient | Link bị chuyển tiếp để nhận sai quyền | Token gắn tenant, recipient và purpose |
| Token không hết hạn hoặc dùng nhiều lần | Replay và account takeover | TTL, one-time atomic consumption |
| GET link tự kích hoạt ngay | Email scanner có thể tiêu thụ token | Trang xác nhận và thao tác chủ động |
| Gộp account theo email | Liên kết nhầm danh tính | Issuer + subject/identity key và xác thực lại |
| Thêm passkey không reauthenticate | Session bị chiếm có thể cài credential attacker | Step-up, thông báo và audit |
| OTP không rate limit | Brute force và SMS/email bombing | Attempt limit, quota và cooldown |
| Password lưu plaintext hoặc SHA-256 | Credential bị lộ khi DB compromise | Password KDF chuyên dụng |
| Role lấy từ form | Người dùng tự nâng quyền | Server-side approval và allowlist mapping |
| Tạo account rồi gán tenant từ body | Cross-tenant enrollment | Trust registry/invitation server-side |
| Không xử lý account pre-hijacking | Attacker đặt credential trước nạn nhân | Claim flow, credential reset và identity binding |
| Support tự đặt password | Nhân viên biết credential của người dùng | Activation link và self-service setup |
| Deprovision chỉ tắt login mới | Session/token cũ còn hoạt động | Revoke session/token/credential và membership |

## 24. Checklist production

1. **Purpose:** Account dành cho ai và phục vụ mục đích gì?
2. **Assurance:** Mức contact verification, organization proofing và identity proofing có phù hợp rủi ro?
3. **Data minimization:** Chỉ thu thập thuộc tính cần thiết; có retention/deletion policy?
4. **Enrollment model:** Self-service, invitation, admin-assisted, SSO/JIT hay workload enrollment?
5. **Eligibility:** Ai có quyền mời, duyệt và cấp tenant membership?
6. **Transaction:** Enrollment ID, purpose, subject, tenant và expiry được ràng buộc server-side?
7. **Tokens:** Activation/invitation/OTP có entropy, TTL, one-time use, rate limit và replay protection?
8. **Account uniqueness:** Có khóa identity ổn định, unique constraint và xử lý concurrent duplicate?
9. **Credential binding:** Password/passkey/MFA/certificate được xác minh trước khi active?
10. **Step-up:** Thêm/gỡ credential hoặc recovery channel có reauthentication phù hợp?
11. **Authorization:** Quyền ban đầu tối thiểu, role/group mapping có nguồn authoritative?
12. **Account state:** Pending, active, suspended, rejected và deprovisioned có semantics rõ?
13. **Anti-abuse:** Có chống bot, enumeration, pre-hijacking, invitation abuse và OTP bombing?
14. **Notifications/audit:** Thay đổi danh tính/credential được thông báo và audit không chứa bí mật?
15. **Recovery:** Người dùng mất thiết bị/kênh liên hệ có quy trình an toàn và không yếu hơn login?
16. **Lifecycle:** Provisioning, update, deprovisioning, session/token revocation có owner và SLA?
17. **Testing:** Có test replay, race, wrong tenant, credential binding, account linking và privilege escalation?

## 25. Bài tập tình huống

Một nền tảng học tập nhập danh sách học viên từ trường. Hệ thống tạo trước account bằng email và mã học viên, đặt password tạm thời giống nhau cho cả lớp rồi gửi qua email. Ai nhập email và mã học viên đều có thể kích hoạt account. Sau khi kích hoạt, người dùng tự chọn tenant và role trong form. Hệ thống tự động gộp account theo email. Người dùng có thể thêm passkey khi đang có session bình thường mà không xác thực lại.

**Yêu cầu:**

1. Xác định ít nhất **tám rủi ro** về identity proofing, invitation, pre-hijacking, credential exposure, tenant isolation và privilege assignment.
2. Thiết kế lại quy trình claim account từ dữ liệu pre-provisioned của trường.
3. Đề xuất cách gửi invitation và xác minh đúng recipient mà không chia sẻ password tạm.
4. Xác định nguồn authoritative cho tenant, student identity và role.
5. Thiết kế bước đăng ký passkey/MFA có reauthentication, challenge binding, audit và notification.
6. Viết test cho invitation replay, account duplicate, sai tenant, role injection và concurrent enrollment.

**Gợi ý đối chiếu:** dùng invitation/claim token có purpose, TTL và one-time use; xác minh mã học viên với nguồn của trường; không gửi password chung; tenant/role lấy từ server-side approval; account key ổn định; passkey enrollment yêu cầu step-up; request đồng thời phải được xử lý nguyên tử.

## 26. Ghi nhớ

- **User enrollment** thiết lập tài khoản, bằng chứng danh tính, credential và quyền truy cập ban đầu; đây là một phần của identity lifecycle.
- Xác minh email/số điện thoại chứng minh quyền kiểm soát kênh liên hệ, không tự chứng minh danh tính pháp lý hoặc tư cách tổ chức.
- Invitation, activation link và OTP là credential tạm thời: phải có entropy, purpose, subject/tenant binding, TTL và one-time consumption.
- Không gộp account chỉ vì email trùng; dùng identity key ổn định và quy trình account linking có xác thực lại.
- Password, passkey, MFA và certificate chỉ được gắn sau khi xác minh đúng transaction và account; thay đổi credential cần step-up, audit và notification.
- Account creation, activation, tenant membership và authorization là các quyết định riêng; quyền ban đầu phải tối thiểu.
- Enrollment cần chống account pre-hijacking, enumeration, bot abuse, replay, duplicate và race condition.
- Recovery, provisioning và deprovisioning phải tiếp nối enrollment để giữ danh tính và quyền truy cập đúng trong toàn bộ vòng đời.

Enrollment an toàn khi hệ thống có thể giải thích **ai được tạo tài khoản, bằng chứng nào gắn người đó với danh tính, credential nào được đăng ký, tenant/quyền nào được cấp và cách thu hồi mọi liên kết khi niềm tin thay đổi**.
