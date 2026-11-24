# Break-glass account – tài khoản truy cập khẩn cấp trong IAM lifecycle

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích **break-glass account** là gì, khi nào được phép dùng và vì sao nó không phải một tài khoản quản trị thông thường.
- Phân biệt **tài khoản khẩn cấp**, **quy trình break-glass**, **Just-in-Time (JIT) privilege**, **Privileged Access Management (PAM)**, tài khoản dự phòng và quyền tự phục hồi của nhà cung cấp.
- Nhận diện các tình huống cần truy cập khẩn cấp như **IdP/SSO outage, lỗi MFA, khóa nhầm quản trị viên, hỏng federation, lỗi chính sách IAM** và sự cố production.
- Thiết kế việc tạo, quản trị, lưu bí mật, xác thực, phân quyền, kích hoạt, giám sát và thu hồi tài khoản khẩn cấp theo **least privilege, separation of duties, defense in depth**.
- Xây dựng luồng **kiểm soát trước/trong/sau sự cố**: xác nhận incident, cấp quyền sử dụng, logging, hậu kiểm, rotation, remediation và đối soát.
- Phân tích sự đánh đổi giữa **khả năng khôi phục khi hệ thống danh tính bị lỗi** và **nguy cơ tạo đường vòng truy cập đặc quyền thường trực**.
- Liên hệ break-glass account với **Joiner–Mover–Leaver (JML)**, **IdP, SSO, SCIM, RBAC/ABAC/PBAC**, tài khoản dịch vụ, session recording và kiểm toán.
- Áp dụng checklist, bảng tình huống, mẫu runbook và bài kiểm thử để giảm **quyền truy cập tồn dư** sau tình huống khẩn cấp.

## 1. Break-glass account là gì?

**Break-glass account (tài khoản truy cập khẩn cấp)** là danh tính hoặc tài khoản được **chuẩn bị và quản trị riêng** để những người được ủy quyền có thể khôi phục quyền kiểm soát hệ thống trong tình huống bất thường, khi **đường đăng nhập hoặc cấp quyền tiêu chuẩn không hoạt động hoặc không đáp ứng thời gian xử lý sự cố**.

Tên gọi bắt nguồn từ ý tưởng **“đập kính khi khẩn cấp”**: quyền này không dành cho vận hành hằng ngày. Một khi sử dụng, tổ chức phải **nhận biết, lưu chứng cứ, điều tra nếu cần và đưa hệ thống trở về trạng thái kiểm soát bình thường**.

Ví dụ:

- Sự cố cấu hình federation khiến mọi quản trị viên không đăng nhập được vào hệ quản lý danh tính qua SSO.
- Một thay đổi chính sách điều kiện truy cập chặn nhầm các tài khoản IAM administrator.
- Đường quản trị cloud bị gián đoạn, tổ chức cần account dự phòng đã chuẩn bị để sửa cấu hình.
- PAM gateway mất khả dụng, trong khi đội trực sự cố phải khôi phục dịch vụ production.
- MFA hoặc thiết bị bảo mật dành cho quản trị viên bị lỗi diện rộng, cần phương án dự phòng đã được phê duyệt.

**Break-glass account không phải tài khoản “được phép làm mọi việc mà không bị kiểm soát”.** Nó là một phần của thiết kế **khả dụng và phục hồi đặc quyền**, kèm những điều kiện bảo vệ tương xứng với rủi ro của chính quyền đó.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, break-glass nằm ở giao điểm của **quản lý danh tính, đặc quyền, xác thực, phân quyền và vòng đời Joiner–Mover–Leaver**. Nó phải tương thích với kiến trúc **IdP/SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, audit và reconciliation** nhưng tránh phụ thuộc hoàn toàn vào chính các thành phần có thể bị lỗi trong sự cố.

### 1.1. Bài toán cân bằng

Một tài khoản break-glass quá khó sử dụng có thể **không giúp cứu hệ thống khi cần**. Một tài khoản quá dễ sử dụng có thể trở thành **đường vòng bỏ qua IAM** và bị lạm dụng hằng ngày.

~~~text
Khả năng phục hồi           <---- đánh đổi ---->          Kiểm soát an ninh
Có thể đăng nhập khi SSO lỗi                       Không mở quyền vô thời hạn
Có cách lấy credential khi PAM lỗi                 Không tiết lộ secret tràn lan
Không phụ thuộc một nhân sự                         Có trách nhiệm và audit
Không bị automation khóa nhầm                      Không trở thành account mồ côi
~~~

Mục tiêu là **truy cập khi thật sự cần, bởi đúng người và vì đúng mục đích**, sau đó chấm dứt việc sử dụng bất thường và kiểm chứng trạng thái.

## 2. Phân biệt break-glass account với những cơ chế khác

| Cơ chế | Khi dùng | Điểm khác biệt |
| --- | --- | --- |
| **Tài khoản quản trị thông thường** | Công việc quản trị hằng ngày | Theo quy trình đăng nhập, approval và giám sát thông thường |
| **PAM/JIT privileged access** | Nhu cầu quản trị có thể lên kế hoạch | Thường cần broker, phê duyệt, TTL và hệ quản trị quyền hoạt động |
| **Break-glass account** | Đường quản trị chuẩn mất tác dụng hoặc khẩn cấp đặc biệt | Phải còn khả dụng trong failure mode đã thiết kế, có thủ tục riêng |
| **Emergency access procedure** | Toàn bộ quy trình ứng cứu | Bao gồm con người, tài khoản, credential, quyết định, vận hành, hậu kiểm |
| **Backup administrator** | Người quản trị dự phòng | Có thể vẫn phụ thuộc cùng IdP/SSO và MFA nên không phải break-glass độc lập |
| **Recovery key / token** | Khôi phục một thành phần cụ thể | Không nhất thiết là account có thể tạo session quản trị |
| **Service account** | Chạy ứng dụng, bot, job | Có identity và lifecycle máy, không phải account tương tác cho con người |
| **Disaster recovery environment** | Khôi phục hạ tầng/dữ liệu | Có thể cần break-glass nhưng không thay account governance |
| **Root/local superuser** | Quyền cao nhất ở hệ đích | Chỉ là loại account/quyền; cần kiểm soát đặc biệt nếu dùng làm khẩn cấp |

### 2.1. Break-glass không nhất thiết luôn là super-admin

Tài khoản khẩn cấp nên chỉ có **đặc quyền đủ để thực hiện mục tiêu phục hồi đã xác định**. Có tình huống cần quản trị tenant cloud, nhưng cũng có tình huống chỉ cần sửa federation configuration hoặc khôi phục quyền truy cập một dịch vụ.

**Quyền rộng phải có lý do cụ thể.** Không tạo một global administrator thường trực nếu một khả năng phục hồi hẹp và đáng tin đã giải quyết được failure mode.

### 2.2. Account thường trực và quyền kích hoạt tạm thời

Có thể thiết kế theo các cách:

1. **Tài khoản dự phòng tồn tại sẵn**, thông tin xác thực được bảo vệ và chỉ sử dụng khi có sự cố.
2. **Tài khoản tồn tại nhưng quyền khẩn cấp chỉ kích hoạt theo quy trình**, nếu nền tảng cho phép và không phụ thuộc vào hệ thống có thể mất khả dụng.
3. **Credential/capability khôi phục chuyên dụng**, ví dụ recovery identity hoặc quyền quản trị độc lập được nhà cung cấp hỗ trợ.
4. **Phương án truy cập vật lý/offline** theo threat model, đặc biệt với hệ on-premises.

Không có một thiết kế chung cho mọi IdP, cloud, database hay thiết bị mạng. Điều cốt yếu là **thử nghiệm trên đúng loại outage mà thiết kế cần vượt qua**.

## 3. Các tình huống kích hoạt hợp lệ

Break-glass nên có **danh mục use case được phê duyệt trước**, không để mỗi người tự định nghĩa “khẩn cấp”.

| Failure mode | Biểu hiện | Mục tiêu sử dụng khẩn cấp |
| --- | --- | --- |
| **IdP outage** | Không tạo được phiên quản trị SSO | Truy cập console phục hồi độc lập theo khả năng nền tảng |
| **Federation misconfiguration** | Trust/redirect/certificate sai | Khôi phục cấu hình federation hoặc đường quản trị |
| **MFA outage** | Admin không hoàn thành factor theo đường chuẩn | Dùng phương án factor/recovery độc lập đã được bảo vệ |
| **Conditional access lockout** | Chính sách mới khóa mọi admin | Vào bằng identity khẩn cấp để sửa chính sách |
| **PAM/bastion outage** | Không tới được target qua proxy | Thực hiện quy trình quản trị dự phòng có kiểm soát |
| **Directory disaster** | AD/LDAP hoặc replicated directory lỗi | Khôi phục dịch vụ bằng đường quản trị dự phòng |
| **Cloud control-plane incident** | Mất đường admin thông thường | Dùng recovery path do kiến trúc hỗ trợ |
| **Critical production incident** | Cần sửa ngay, approval tiêu chuẩn không khả dụng | Quyền khẩn cấp có scope/TTL và hậu kiểm |
| **Credential compromise / admin lockout** | Credential quản trị bị thu hồi hoặc khóa nhầm | Phục hồi quản trị qua kênh tin cậy khác |

### 3.1. Tình huống không đủ lý do

- Muốn tránh chờ approval cho thay đổi định kỳ.
- Không nhớ mật khẩu tài khoản công việc.
- Không muốn bật MFA hoặc sử dụng PAM trong vận hành hằng ngày.
- Muốn tạo quyền admin “cho tiện” khi chạy deployment.
- Quá hạn một access request không khẩn cấp.
- Muốn vượt SoD hoặc chính sách bảo vệ dữ liệu do owner từ chối.
- Muốn truy cập dữ liệu thuộc một tenant khác mà không có thẩm quyền.

**Break-glass không phải quy trình cấp quyền mặc định nhanh hơn.**

### 3.2. Incident có thể vẫn cần người xác nhận

Nếu hệ thống hoạt động bình thường, quy trình có thể yêu cầu incident commander, security on-call hoặc người có thẩm quyền xác nhận. Nhưng phải phân tích **dependency failure**: nếu chính công cụ phê duyệt đang lỗi, một yêu cầu approval trực tuyến bắt buộc có thể làm phương án dự phòng vô dụng.

Có thể thiết kế **ủy quyền từ trước, dual control hoặc cơ chế offline có kiểm toán hậu kỳ** tùy risk. Không giả vờ những hệ thống đã chết vẫn có thể trả approval thời gian thực.

## 4. Threat model của tài khoản khẩn cấp

Phải trả lời: **điều gì cần sống sót, ai có thể lạm dụng, và kiểm soát nào còn hoạt động khi xảy ra sự cố?**

### 4.1. Các mối đe dọa thường gặp

| Mối đe dọa | Cách xảy ra | Tác động |
| --- | --- | --- |
| Credential bị lộ | Lưu password trong ticket/chat hoặc vault cấp quyền rộng | Attacker truy cập đặc quyền |
| Người cũ còn biết secret | Nhân viên Leaver từng giữ bản sao khôi phục | Quyền tồn dư ngoài SSO |
| Bypass cơ chế giám sát | Login trực tiếp thay vì PAM | Giảm accountability |
| Tài khoản khẩn cấp dùng hằng ngày | Admin muốn giảm số bước | Permanent privilege và phát tán credential |
| Bị disable vì automation | SCIM/offboarding hoặc policy chung vô hiệu hóa nhầm | Không phục hồi được khi IdP lỗi |
| Account bị chiếm qua recovery | Phục hồi password/factor yếu | Takeover quyền cao |
| Một người nắm toàn bộ yếu tố | Không có SoD hoặc custody độc lập | Khó phát hiện lạm dụng |
| Nhiều bản sao secret không kiểm soát | Copy vào máy cá nhân, wiki hoặc shell history | Khó revoke hoàn toàn |
| Không có audit độc lập | SIEM/PAM cùng bị lỗi | Mất dấu vết truy cập |
| Quyền vượt quá nhu cầu | Account có global admin + quyền mọi dữ liệu | Blast radius lớn |

### 4.2. Trust boundary

~~~mermaid
flowchart LR
    OP["Người trực sự cố"] --> CHECK["Kiểm incident và thẩm quyền"]
    CHECK --> CUSTODY["Credential custody / dual control"]
    CUSTODY --> AUTH["Emergency authentication path"]
    AUTH --> TARGET["Management plane / target"]
    TARGET --> REC["Native audit / emergency evidence"]
    REC --> POST["Hậu kiểm và reconciliation"]
    HR["HRIS / JML state"] --> CHECK
    POLICY["Security / PAM policy"] --> CHECK
    POLICY --> POST
~~~

**Đây là luồng logic.** Trong sự cố, một số thành phần như ticketing, PAM hoặc IdP có thể không hoạt động; runbook phải nêu rõ **đường thay thế được phê duyệt**, cách ghi chứng cứ tối thiểu và cách đồng bộ sau phục hồi.

## 5. Nguyên tắc thiết kế bảo mật và khả dụng

### 5.1. Independence – tránh phụ thuộc cùng một điểm hỏng

Một emergency account dùng **chính federated SSO** vừa bị outage sẽ không giải quyết sự cố đó. Một recovery secret chỉ nằm trong vault được mở bằng **cùng IdP** cũng có thể không lấy được.

Cần lập dependency map:

~~~text
Normal administration:
  Workstation -> IdP -> MFA provider -> PAM -> Cloud console

Emergency path (ví dụ):
  Designated responder
    -> independent credential custody
    -> supported native/recovery authentication
    -> minimal management functions
    -> local/native evidence
~~~

**Không được hiểu “độc lập IdP” là “bỏ xác thực mạnh”.** Nên dùng những phương thức bảo vệ độc lập được nền tảng hỗ trợ, ví dụ yếu tố phần cứng dự phòng được quản lý thích hợp, thay vì một mật khẩu dễ đoán được chia cho nhiều người.

### 5.2. Separation of duties – tránh một người kiểm soát mọi khâu

Có thể phân vai:

- **Emergency access custodian:** bảo quản credential/factor.
- **Incident commander hoặc approver:** xác nhận điều kiện khẩn cấp.
- **Authorized operator:** thực hiện thao tác phục hồi.
- **Independent reviewer:** kiểm tra thao tác và bằng chứng.
- **IAM/PAM owner:** quản lý account, thử nghiệm và rotation.
- **Auditor/security:** theo dõi usage và ngoại lệ.

Với tổ chức nhỏ, một số vai trò có thể kiêm nhiệm theo risk, nhưng cần **bù kiểm soát và hậu kiểm độc lập khi khả thi**.

### 5.3. Least privilege và time bounded use

- Chỉ truy cập target và hành động cần phục hồi.
- Không dùng account để đọc dữ liệu nghiệp vụ nếu không liên quan incident.
- Giảm thời gian session, quyền và credential có thể dùng.
- Tách account khẩn cấp theo **failure domain** khi cần.
- Giới hạn nguồn mạng/thiết bị hoặc phương tiện truy cập nếu không làm mất khả dụng của recovery path.
- Sau sự cố, thu hồi grant/capability tạm thời, chấm dứt session và xác minh trạng thái.

### 5.4. Deny by default, nhưng có ngoại lệ thiết kế sẵn

Trong trạng thái bình thường, việc sử dụng break-glass account nên **bị hạn chế và cảnh báo mạnh**. Trong sự cố, quyền chỉ được dùng theo **kịch bản đã phê duyệt**. Nếu policy engine/PIP hỏng, tổ chức cần một fallback rõ ràng thay vì **mặc định PERMIT mọi người**.

## 6. Tạo và quản lý vòng đời break-glass account

Không tạo emergency account tạm bợ khi toàn bộ quản trị đã bị khóa. Nó phải được **chuẩn bị trước**, với owner và quy trình kiểm soát.

### 6.1. Các thuộc tính nên quản trị

| Thuộc tính | Ví dụ | Lý do |
| --- | --- | --- |
| **emergencyAccountId** | `emg-cloud-tenant-a-01` | Định danh ổn định, không dựa email đơn thuần |
| **accountType** | `BREAK_GLASS_INTERACTIVE` | Phân biệt tài khoản thông thường |
| **targetRealm/tenant** | `cloud-tenant-a` | Khoanh phạm vi phục hồi |
| **failureScenario** | `FEDERATION_OUTAGE` | Account được thiết kế cho tình huống nào |
| **accountableOwner** | `iam-security-team` | Trách nhiệm tổ chức |
| **credentialCustodian** | Vai trò/nhóm có kiểm soát | Ai có thể truy cập bí mật |
| **authorizedResponders** | Nhóm on-call hợp lệ | Người được phép sử dụng |
| **privilegeScope** | `identity-policy-recovery` | Không cấp quyền tùy tiện |
| **authenticationMethod** | Recovery method được nền tảng hỗ trợ | Độ tin cậy và khả dụng |
| **approvalMode** | `dual-control-or-offline-exception` | Cách xử lý khi công cụ online lỗi |
| **loggingSources** | `native-audit`, `security-log` | Nguồn chứng cứ |
| **lastVerifiedAt** | Timestamp | Lần thử nghiệm gần nhất |
| **lastCredentialRotationAt** | Timestamp | Theo dõi secret/factor |
| **accountStatus** | `READY`, `IN_USE`, `REVIEW_REQUIRED` | Trạng thái vận hành |
| **policyVersion** | `emergency-access/v3` | Chính sách đang áp |

**Các trường là mô hình minh họa**, không phải schema chuẩn. Khi triển khai phải dùng các thuộc tính thực sự được nền tảng hỗ trợ.

### 6.2. Vì sao cần ít nhất một người chịu trách nhiệm?

Một emergency account không có owner rất dễ bị bỏ quên: credential hết hiệu lực, factor bị mất, quyền sai, logging tắt hoặc người đã nghỉ vẫn biết bí mật.

Owner chịu trách nhiệm **kiểm readiness, thử nghiệm, rotation, quyền, exception và hậu kiểm**, không có nghĩa chủ thể đó được tùy ý đăng nhập trong mọi tình huống.

### 6.3. Hai tài khoản dự phòng có tốt hơn một?

Nhiều tổ chức cần **đường dự phòng tránh single point of failure**, ví dụ hai emergency identities/custody routes độc lập. Tuy nhiên mỗi account tăng thêm **attack surface và chi phí kiểm soát**.

Không có số lượng bắt buộc chung. Xác định theo tenant, failure domains, coverage, khả năng truy cập factors và capacity để tránh một credential bị lỗi khiến toàn bộ phương án phục hồi thất bại.

### 6.4. Tên tài khoản không phải biện pháp bảo mật

Dùng tên khó đoán không thay thế yếu tố xác thực mạnh, logging, quyền hẹp và custody. Cũng không nên đưa username/secret thật của account khẩn cấp vào bài hướng dẫn công khai.

## 7. Credential custody và khôi phục khi PAM/Vault lỗi

**Credential custody** quy định bí mật hoặc yếu tố xác thực khẩn cấp được tạo, cất giữ, truy xuất, xoay vòng và kiểm toán như thế nào.

### 7.1. Các yêu cầu thiết kế

- **Không lưu plaintext password** trong email, wiki, ticket hoặc chat nhóm.
- Dùng vault/bộ lưu trữ bí mật được bảo vệ, hoặc phương án offline/khôi phục được duyệt nếu vault có thể cùng bị lỗi.
- Tách quyền **xem, sử dụng, thay đổi và xóa** credential khi kiến trúc cho phép.
- Có **quy trình bàn giao** khi custodian/owner Mover hoặc Leaver.
- Lập bản đồ **thiết bị phần cứng/MFA factors**, cách thay thế khi mất hoặc hỏng.
- Định nghĩa khả năng tiếp cận khi **mất mạng, mất điện hoặc IdP unavailable**.
- Ghi **ai truy xuất, lúc nào, vì sự cố gì**; với offline phải nhập audit sau.
- Đổi hoặc vô hiệu hóa bí mật đã có nguy cơ lộ theo risk và hỗ trợ nền tảng.

### 7.2. “Chia đôi bí mật” có áp dụng được không?

Một số tổ chức sử dụng **dual control**: hai người hoặc hai thiết bị cùng cần tham gia để truy xuất credential. Cách này giảm rủi ro một người tự ý dùng quyền nhưng có thể làm tăng **khó khăn khôi phục** nếu cả hai người không liên lạc được.

Nếu chọn cách này, cần kiểm thử các trường hợp **người trực không đến được, người đang Leaver, thiết bị bị thất lạc và một trung tâm dữ liệu bị cách ly**. Không tuyên bố dual control tự đảm bảo an toàn hay sẵn sàng.

### 7.3. Credential ngắn hạn và bí mật dài hạn

Khuyến khích credential ngắn hạn khi hệ thống hỗ trợ. Tuy nhiên **một tài khoản khẩn cấp độc lập** đôi khi cần phương án đăng nhập bền vững để sống sót qua sự cố của dịch vụ cấp token.

Vì vậy không áp máy móc yêu cầu “mọi break-glass password hết hạn hằng ngày” nếu điều đó khiến tài khoản không sử dụng được lúc khẩn cấp. Thay vào đó quản trị **độ mạnh, cất giữ, rotation khi cần, kỳ kiểm thử và cảnh báo** theo hướng dẫn nền tảng và threat model.

## 8. MFA và phương án authentication dự phòng

Một tài khoản đặc quyền có thể có nguy cơ cao khi chỉ dùng mật khẩu. Nhưng nếu mọi factor phụ thuộc **cùng MFA service outage**, break-glass sẽ thất bại.

### 8.1. Nguyên tắc chọn factor

- Ưu tiên **phương thức xác thực mạnh, chống phishing** và độc lập phù hợp khi nền tảng hỗ trợ.
- Có **yếu tố dự phòng** tránh hỏng một thiết bị hoặc một người giữ.
- Không buộc mọi phương thức cứu hộ đi qua cùng federation/conditional access vừa gây khóa.
- Kiểm chính sách ngoại lệ MFA/conditional access đúng **failure scenario** và giới hạn account.
- Thử nghiệm xem việc thay đổi policy thông thường có vô tình **vô hiệu hóa emergency path** không.
- Gắn rõ người thực sử dụng và bước phê chuẩn, không chỉ thấy account khẩn cấp.

### 8.2. Phương án không có MFA mạnh

Nếu một hệ thống cũ không hỗ trợ factor phù hợp, cần đánh giá rủi ro còn lại và áp **compensating controls**: vị trí truy cập, dual custody, physical controls, alert bất thường, recording/native logs, thời hạn dùng và hậu kiểm.

Không có phương án hoàn hảo, nhưng **“do khẩn cấp nên không cần xác thực”** là một kết luận sai.

## 9. Break-glass trong cloud, IdP, on-prem và ứng dụng

| Môi trường | Khả năng phục hồi cần xem xét | Lưu ý thiết kế |
| --- | --- | --- |
| **Cloud tenant** | Truy cập management plane khi SSO/federation lỗi | Native emergency identity hoặc recovery path được hỗ trợ |
| **IdP/SSO** | Sửa policy, federation, factor/conditional access | Không để account bị cùng rule khóa nhầm |
| **Active Directory/LDAP** | Khôi phục directory/DC | Domain/local recovery identity, physical/network boundary |
| **Linux/Windows host** | Truy cập khi PAM/bastion outage | Host/native logs, credential và kết nối ngoài PAM phải được quản trị |
| **Database** | Sửa schema/grants hoặc khôi phục dịch vụ | Audit, transaction controls và quyền phục hồi hẹp |
| **Network equipment** | Khôi phục routing/firewall | Console/recovery access với custody và change logs |
| **Kubernetes/control plane** | Khôi phục cluster khi identity integration lỗi | Admin recovery capability, API audit và credential lifetime |
| **SaaS critical admin** | Khôi phục cấu hình/owner của ứng dụng | Cân nhắc native admin fallback và support recovery |
| **Secrets management** | Khôi phục vault/key service | Recovery/quorum/key custody độc lập nếu được hỗ trợ |

**Không có một “break-glass account cho cả doanh nghiệp” tự nhiên truy cập mọi nền tảng.** Mỗi hệ có identity store, boundary và recovery mechanism riêng.

### 9.1. IdP outage và chuỗi phụ thuộc vòng tròn

Ví dụ thất bại:

~~~text
IdP lỗi
  -> Admin không vào được PAM
  -> Password break-glass chỉ lưu trong vault mở bằng SSO
  -> Không lấy được credential
  -> Không đăng nhập được IdP để sửa lỗi
~~~

Bài toán là **circular dependency**. Giải pháp phải được thiết kế trước bằng phương án custody và authentication không cùng điểm lỗi, có kiểm soát bù phù hợp.

### 9.2. Local emergency account có rủi ro riêng

Tài khoản local có thể sống sót khi domain/SSO down, nhưng cũng có thể bị dùng ngoài PAM và khó quy trách nhiệm khi shared credential. Cần hardening, quản lý key, network access, nhật ký local, rotation và mapping người sử dụng theo incident.

## 10. Quy trình sử dụng: trước, trong và sau sự cố

~~~mermaid
sequenceDiagram
    autonumber
    actor O as Incident operator
    participant IC as Incident authority
    participant C as Credential custodian
    participant SYS as Emergency target
    participant AUD as Evidence / Audit
    participant IAM as IAM / Reconciliation

    O->>IC: Xác nhận incident và nhu cầu phục hồi
    IC-->>O: Ủy quyền/ngoại lệ theo policy
    O->>C: Yêu cầu recovery credential/factor
    C->>AUD: Ghi nhận custody, incidentRef
    C-->>O: Cấp phương tiện truy cập theo quy trình
    O->>SYS: Emergency authentication
    SYS->>AUD: Native login/action events khi khả dụng
    O->>SYS: Hành động khôi phục trong scope
    O->>IC: Báo kết quả, mốc phục hồi
    O->>SYS: Đóng phiên và thoát emergency mode
    IC->>IAM: Hậu kiểm, review và revoke/rotate
    IAM->>SYS: Xác minh đặc quyền/session còn tồn dư
    IAM->>AUD: Ghi closure/evidence và lessons learned
~~~

Đây là **luồng tham chiếu**, không phải các bước luôn khả dụng online. Khi thành phần audit/ticketing bị outage, người trực phải dùng **phương án ghi nhận offline được bảo vệ**, rồi đồng bộ và xác minh sau khi phục hồi.

### 10.1. Điều kiện bắt đầu

- Có incident hoặc failure mode thuộc phạm vi được phép.
- Xác định target, tác vụ cần thực hiện, mức tác động và người chịu trách nhiệm.
- Đường admin thường đã lỗi hoặc không đáp ứng yêu cầu khẩn cấp được chứng minh.
- Người trực và custodian có danh tính/thẩm quyền theo danh sách hiện hành.
- Ghi rõ **tại sao không thể dùng PAM/JIT bình thường**.
- Xác định giới hạn thời gian và cơ chế hậu kiểm.

### 10.2. Trong khi sử dụng

- Dùng tài khoản chỉ cho **mục đích phục hồi**.
- Chỉ thực hiện thay đổi cần thiết, không dùng để đọc/khai thác dữ liệu ngoài scope.
- Ghi mốc đăng nhập, mục đích, lệnh/thay đổi quan trọng, target và kết quả.
- Theo dõi native audit, SIEM hoặc session recording nếu còn hoạt động.
- Thông báo nhóm phản ứng sự cố về hành động rủi ro cao.
- Tránh chuyển credential cho người khác qua kênh không được phê duyệt.
- Đánh giá trạng thái mới trước khi thực hiện thay đổi đặc quyền tiếp theo.

### 10.3. Khi kết thúc

- Thoát và **chấm dứt emergency session**; kiểm target connections còn sống không.
- Thu hồi quyền JIT/capability tạm thời và credential phát sinh.
- Xoay vòng hoặc thay credential/factor theo risk và chính sách; đặc biệt nếu đã được tiết lộ.
- Kiểm cấu hình IAM/SSO/conditional access đã được đưa về trạng thái hợp lệ.
- So desired-vs-observed privileges, account roles, cloud grants, local accounts và service tokens.
- Bảo toàn log, recording và incident evidence.
- Reviewer độc lập đánh giá scope, SoD, thời điểm và kết quả.
- Trả trạng thái **READY** chỉ sau khi kiểm tra phương án dự phòng còn sử dụng được.

## 11. Mô hình trạng thái break-glass

Nên tách **trạng thái tài khoản** và **trạng thái một lần sử dụng**.

### 11.1. Account lifecycle

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> READY: Test và custody verified
    READY --> IN_USE: Authorized emergency activation
    IN_USE --> POST_USE_REVIEW: Session ended
    POST_USE_REVIEW --> READY: Review + rotation/verification passed
    POST_USE_REVIEW --> REPAIR_REQUIRED: Credential/permission issue
    REPAIR_REQUIRED --> READY: Fixed and tested
    READY --> DECOMMISSION_PENDING: Recovery design replaced
    DECOMMISSION_PENDING --> DECOMMISSIONED: Alternate path verified
    DECOMMISSIONED --> [*]
~~~

Trạng thái trên là **mẫu logic**, không có một chuẩn chung. `READY` không có nghĩa credential đang được nhiều người cầm; nó thể hiện đường phục hồi đã được kiểm chứng theo policy.

### 11.2. Usage lifecycle

~~~text
EMERGENCY_REQUESTED
  -> AUTHORITY_VERIFIED
  -> CREDENTIAL_RELEASED / SESSION_OPENED
  -> RECOVERY_ACTIONS
  -> SESSION_CLOSED
  -> ACCESS_REVOKED_OR_SECURED
  -> EVIDENCE_VERIFIED
  -> POST_INCIDENT_REVIEW
  -> CLOSED

Khi không đủ thẩm quyền hoặc không đúng tình huống:
  DENIED / EXCEPTION_REQUIRED
~~~

**Không tự ghi CLOSED chỉ vì người dùng đóng cửa sổ console.** Có thể còn token, background job, phiên target hoặc thay đổi cấp quyền chưa được gỡ.

## 12. Least privilege trong quyền phục hồi

### 12.1. Phân vùng nhiệm vụ

Một tổ chức có thể cần các khả năng khác nhau:

| Khả năng | Ví dụ | Nên tách khi có thể |
| --- | --- | --- |
| Khôi phục federation/SSO | Sửa trust hoặc policy đăng nhập | Tránh đọc dữ liệu nghiệp vụ |
| Khôi phục directory | Sửa membership hoặc dịch vụ directory | Giới hạn phạm vi domain/forest |
| Khôi phục cloud control plane | Gỡ cấu hình khóa admin | Không tự mở quyền mọi tenant |
| Khôi phục database | Sửa lỗi quyền hoặc trạng thái DB | Cần audit native và SoD |
| Khôi phục PAM/vault | Sửa hệ điều phối quyền | Cần custody độc lập |
| Khôi phục mạng | Sửa firewall/routing | Chỉ thiết bị và cấu hình thiết yếu |

Không phải mọi nền tảng hỗ trợ vai trò phục hồi hẹp. Nếu chỉ có cấp quyền cao, cần **tăng kiểm soát về người dùng, cách lưu, thời hạn, hành vi, giám sát và hậu kiểm**.

### 12.2. Không dùng break-glass để “cấp lại mọi role”

Một tình huống khẩn cấp có thể yêu cầu sửa một policy gây khóa. Sau khi policy được khôi phục, không nên để các role admin mở rộng cho cả nhóm trực sự cố. Tất cả quyền tạm thời phải có **owner, lý do, hạn xử lý và bằng chứng đã thu hồi**.

## 13. JIT/PAM, approval và break-glass khác nhau ở đâu?

Trong điều kiện bình thường:

~~~text
Admin -> IdP/SSO + MFA -> PAM/JIT approval
      -> quyền hẹp có TTL -> target -> logging -> revoke
~~~

Trong sự cố mà IAM/PAM gặp lỗi:

~~~text
Authorized responder -> emergency custody / authentication path
                     -> recovery privilege -> target
                     -> native/offline evidence -> post-review
                     -> restore PAM/JIT -> revoke/rotate
~~~

### 13.1. Không phụ thuộc PAM để cứu chính PAM

Nếu credential chỉ được lấy khi PAM đang hoạt động, tài khoản không giúp khi PAM outage. Phải có **cơ chế khôi phục PAM** riêng hoặc backup trust chain phù hợp, nhưng không mở đường truy cập trực tiếp vô điều kiện.

### 13.2. Có thể vẫn yêu cầu phê duyệt

Tùy mức độ:

- **Online approval:** dùng khi công cụ workflow còn hoạt động và thời gian cho phép.
- **Dual-control physical/offline:** hai người xác nhận/giữ yếu tố.
- **Preauthorized emergency role:** nhóm on-call đã được duyệt theo policy, sử dụng rồi được hậu kiểm.
- **Incident commander exception:** một cơ chế khẩn cấp giới hạn, có trách nhiệm rõ.

**Không tồn tại quy tắc phổ quát bắt mọi break-glass phải được phê duyệt online trước khi truy cập**, vì bản thân hệ thống phê duyệt có thể nằm trong sự cố.

## 14. Attribution: tài khoản dùng chung nhưng ai đã thao tác?

Một emergency account đôi khi được thiết kế như account kỹ thuật dự phòng, không gắn trực tiếp một người như account hằng ngày.

Nếu log chỉ cho thấy `emergency-admin` đăng nhập, tổ chức có thể không biết **ai đang thực sự thao tác**.

### 14.1. Chuỗi chứng cứ nên lưu

~~~text
Incident ID
  -> Incident authority / commander
  -> Responder identityId
  -> Credential custodian identityId
  -> Credential release/custody event
  -> Emergency account ID
  -> Target login/session ID
  -> Native activity/change logs
  -> Post-incident reviewer
  -> Credential/privilege restoration evidence
~~~

### 14.2. Nhiều người cùng có credential

Nếu hai người đồng thời biết cùng mật khẩu, việc phân biệt actor qua timestamp có thể không đáng tin. Cần **quy trình phân tách session, kiểm điểm người sử dụng, credential checkout và logs**; khi nền tảng cho phép, nên ưu tiên cơ chế **broker/session attribution hoặc recovery identity cá nhân**.

**Một tài khoản break-glass không nên trở thành shared-admin credential lưu trong nhiều máy trạm.**

### 14.3. Credential release khác session login

Có thể có event mở vault nhưng người dùng không đăng nhập, hoặc đăng nhập từ một bản sao secret bị lộ mà không có checkout event. Hai loại dữ liệu cần **đối chiếu**, không tự đồng nhất.

## 15. Audit, cảnh báo và session recording

Một phiên khẩn cấp cần được giám sát mạnh hơn bình thường khi có thể, vì privilege thường cao và kiểm soát chuẩn có thể tạm bị bỏ qua.

### 15.1. Các lớp bằng chứng

| Lớp | Ví dụ sự kiện | Hạn chế |
| --- | --- | --- |
| **Credential custody** | Ai nhận được yếu tố/secret | Không chứng minh đã dùng |
| **IdP/native authentication** | Login/failure/thiết bị/IP | Có thể không có nếu hệ thống đó outage |
| **PAM/session recording** | Terminal/video phiên | Có thể bị bypass hoặc không hoạt động |
| **OS/native target audit** | Lệnh, process, thay đổi cấu hình | Phụ thuộc logging ở đích |
| **Cloud control-plane audit** | API calls và kết quả | Không phải screen recording |
| **Database audit** | DDL/DML/grants/commit outcome | Không nhất thiết gắn human ID nếu dùng account chung |
| **Incident journal** | Người chịu trách nhiệm, lý do, timeline | Có thể nhập offline rồi bổ sung sau |
| **SIEM/detection** | Cảnh báo bất thường và correlation | Có thể trễ hoặc không khả dụng |

### 15.2. Cảnh báo nên kích hoạt

- Bất kỳ **successful authentication** tới emergency account nào ngoài kỳ kiểm thử đã công bố.
- Nhiều **failed login attempts** vào emergency account.
- Thay credential/factor, recovery method, role hoặc conditional access exception.
- Truy cập ngoài khung incident hay từ thiết bị/nguồn mạng bất thường.
- Sử dụng tài khoản đồng thời ở nhiều vị trí.
- Không có native audit/recording khi policy kỳ vọng có.
- Account khẩn cấp bị disable, xóa, đổi owner hoặc mất một factor.
- Usage chưa được review/đóng trong hạn của tổ chức.

**Bật cảnh báo phải đi kèm người nhận và quy trình phản ứng**, không chỉ gửi log vào nơi không ai theo dõi.

### 15.3. Khi SIEM hoặc PAM cũng bị lỗi

Dùng audit tại đích, lưu log local được bảo vệ và incident journal offline khi cần, rồi **đẩy và đối chiếu sau phục hồi**. Trạng thái bản ghi nên phân biệt **COMPLETE, PARTIAL và UNAVAILABLE**, không đánh dấu thành công khi chưa thu được chứng cứ.

## 16. Tài khoản break-glass trong Joiner–Mover–Leaver

**Joiner–Mover–Leaver** thường quản lý **danh tính nhân sự**: người mới, thay vai trò và kết thúc quan hệ. Break-glass account lại thường là **danh tính kỹ thuật khẩn cấp** có vòng đời riêng, nhưng những **con người được phép sử dụng nó** vẫn thay đổi theo JML.

Phải phân biệt:

1. **Emergency account lifecycle:** tạo, kiểm tra, bảo quản, sẵn sàng, sử dụng, phục hồi và decommission.
2. **Responder lifecycle:** ai là người on-call/custodian, có đủ quyền và training không, họ có Mover/Leaver không.
3. **Temporary privilege lifecycle:** quyền/role/session được kích hoạt riêng cho mỗi incident.
4. **Credential lifecycle:** yếu tố xác thực, recovery key, secret, factor backup và các bản sao đã được cấp.
5. **Target resource lifecycle:** tenant, dịch vụ hoặc hệ thống đích còn tồn tại và owner còn hợp lệ không.

### 16.1. Một thiết kế phản ví dụ

~~~text
Người A tạo tài khoản emergency-admin khi còn là IAM Lead.
A giữ bản sao mật khẩu trong thiết bị cá nhân.
A chuyển bộ phận, sau đó nghỉ việc.
SCIM chỉ gỡ account thông thường của A.
Emergency-admin vẫn hoạt động với cùng password.

Kết quả:
  - Offboarding của A có thể báo COMPLETE
  - Nhưng A có thể vẫn biết credential khẩn cấp
  - Không có bằng chứng rotation hoặc thu hồi quyền truy cập bản sao
~~~

Bài học: **Leaver của con người không tự đồng nghĩa đã thu hồi khả năng sử dụng một emergency account kỹ thuật**. Phải quản lý custody, factors và chứng cứ bàn giao riêng.

## 17. Joiner: thêm người trực khẩn cấp đúng điều kiện

Khi một nhân viên mới vào nhóm IAM/SRE/SOC, việc bổ nhiệm họ làm người được phép dùng break-glass phải là một bước **được phê duyệt và kiểm chứng riêng**, không tự động cấp chỉ vì họ có role “Administrator”.

### 17.1. Quy trình gợi ý

1. HRIS/identity registry xác nhận người mới, identityId, workerType, quan hệ việc làm và effectiveAt.
2. Identity proofing hoàn tất theo mức độ cần thiết.
3. IdP/SSO tạo account công việc và phương thức xác thực bình thường.
4. Security/IAM owner xác định người đó có **emergency responder eligibility** không.
5. Reviewer có thẩm quyền phê duyệt vai trò, scope target và điều kiện SoD.
6. Nhân viên hoàn thành training: khi nào dùng, cách báo incident, custody, ghi evidence và xử lý bí mật.
7. Người mới được thêm vào **danh sách responder/custodian hiện hành**, không nhất thiết biết secret trước khi sử dụng.
8. Thử quy trình dưới hình thức kiểm soát; không để người chưa được đào tạo tự dùng recovery credential.
9. Audit và access certification rà lại eligibility định kỳ.

### 17.2. Preboarding không cho phép lấy credential khẩn cấp

Một người có account IdP trước ngày nhận việc không mặc nhiên được nhận yếu tố break-glass. Nên kiểm **effectiveAt và eligibility**, đồng thời giới hạn quyền vào vault/offline custody.

### 17.3. Người mới là account owner hay operator?

**Accountable owner** của emergency identity có thể là một team; **operator** là người dùng thực tế trong incident; **custodian** là bên giữ phương tiện truy cập. Không tự gộp các vai trò chỉ vì cùng bộ phận.

## 18. Mover: thay đổi vai trò không được để lại quyền cứu hộ cũ

Khi người trực từ nhóm IAM chuyển sang một nhóm khác, họ có thể không còn nhiệm vụ phục hồi quản trị. Nếu chỉ cập nhật HRIS/SCIM mà không xử lý custody, họ vẫn có thể biết bí mật hoặc nắm factor.

### 18.1. Luồng Mover

~~~mermaid
flowchart TD
    HR["HRIS: Mover event"] --> IGA["IGA: xác định eligibility mới"]
    IGA --> ACCESS["Rà responder list, owner và delegation"]
    ACCESS --> CRED["Kiểm secret/factor đã được tiếp cận"]
    ACCESS --> ROLE["Gỡ quyền khẩn cấp không còn hợp lệ"]
    CRED --> ROT["Rotation/rekey theo policy và rủi ro"]
    ROLE --> VERIFY["Readback / effective access verification"]
    ROT --> VERIFY
    VERIFY --> AUD["Audit: custody transfer và closure"]
~~~

### 18.2. Những việc phải phân biệt

- **Gỡ role của người cũ** trong công cụ quản trị không tự thu hồi password đã từng biết.
- **Thay owner** ở registry không tự thay emergency credential.
- **Xoay vòng credential** không chứng minh đã gỡ bản sao cũ nếu hệ đích vẫn chấp nhận khóa khác.
- **Account vẫn READY** có thể phù hợp nếu tổ chức còn cần phục hồi, nhưng phải chuyển trách nhiệm và hạn chế người dùng.

### 18.3. Mover trong lúc có incident

Nếu một responder Mover đang tham gia incident, cần xác định **thẩm quyền còn hiệu lực cho phần công việc nào**. Có thể bàn giao nhiệm vụ theo incident commander, nhưng không tự tiếp tục sử dụng credential chỉ vì session chưa hết hạn.

## 19. Leaver: chặn đường truy cập của người đã rời tổ chức

Leaver của một responder/custodian là sự kiện rủi ro cao đối với emergency access.

### 19.1. Checklist thu hồi liên quan Leaver

- Xóa quyền cá nhân trong team on-call, incident escalation và emergency account custodian roster.
- Gỡ quyền xem vault, sử dụng recovery key và quản trị MFA factors.
- Xác định **người cũ đã tiếp cận những secret/factor nào**; có kế hoạch rotation/rekey phù hợp.
- Thu hồi hoặc thay physical token, niêm phong vật liệu offline, kiểm quyền thay đổi recovery information.
- Kiểm các bản sao credential hoặc alternate recovery methods còn hiệu lực.
- Gỡ quyền privileged cloud/PAM/local account liên quan cá nhân.
- Thu hồi session/token và credential riêng của người Leaver.
- Bàn giao ownership và trách nhiệm thử nghiệm phương án khẩn cấp.
- Reconciliation xác minh **khả năng truy cập hiệu lực** chứ không chỉ ID đã bị disable.

### 19.2. Không xóa bừa tài khoản phục hồi chung

Nếu account là **recovery identity của doanh nghiệp**, Leaver của người từng quản lý nó thường **không có nghĩa phải xóa account** và để toàn bộ công ty không thể phục hồi. Cần **thu hồi con người, rotate/rekey credential và bàn giao custodian**, bảo toàn khả năng cứu hộ.

### 19.3. Nhiều quan hệ làm việc

Một người kết thúc hợp đồng ở pháp nhân A nhưng tiếp tục có trách nhiệm hợp lệ ở B. Quyền với tenant-A phải được thu hồi; quyền với tenant-B cần đánh giá theo quan hệ và policy phù hợp. Không dùng email chung để quyết định mọi quyền.

## 20. Break-glass và tài khoản dịch vụ/workload

**Service accounts, bots, CI/CD identities, workload federation** có quyền riêng và không nên được xem là tài khoản con người dùng để đăng nhập cứu hộ.

### 20.1. Khác biệt cốt lõi

| Loại | Mục đích | Bằng chứng và quản trị |
| --- | --- | --- |
| **Interactive emergency account** | Người trực can thiệp vào management plane | Operator attribution, custody, session/audit, post-review |
| **Recovery automation identity** | Chạy playbook phục hồi đã chuẩn bị | Workload principal, job ID, artifact hash, API audit, owner |
| **Routine service account** | Chạy tác vụ sản xuất thường xuyên | Least privilege, credential rotation, inventory |
| **Cloud managed identity** | Workload lấy token truy cập API | Issuer/audience/scope, permission tại resource |
| **Break-glass script/tool** | Công cụ phục hồi không nhất thiết là identity | Cần xác thực actor và kiểm soát capability riêng |

### 20.2. Khi automation cần emergency privilege

Một workflow tự động khôi phục có thể cần quyền cao khi hệ kiểm soát bình thường không hoạt động. Điều này tạo rủi ro đặc biệt: nếu automation bị chiếm, quyền cao có thể được sử dụng **không cần tương tác**.

Nên yêu cầu:

- **Workload owner và resource owner** rõ ràng.
- Điều kiện incident, target, action và TTL được định nghĩa trước.
- Chứng thực workload hoặc artifact được kiểm soát.
- Không lưu long-lived global admin secret trong pipeline variables thường trực.
- API-level audit và job provenance, không giả định có video phiên người dùng.
- Thử thất bại an toàn, khả năng dừng workflow và hậu kiểm.
- Bàn giao owner, rà key/trust và rotation khi người phụ trách Mover/Leaver.

### 20.3. Không dùng emergency account làm identity ứng dụng

Một ứng dụng production không nên thường xuyên chạy bằng credential khẩn cấp của quản trị viên vì thuận tiện. Hành vi này tạo **một điểm thất bại, khó phân quyền, khó rotate và khó quy trách nhiệm**.

## 21. IdP/SSO, SCIM và break-glass: tránh hai cực đoan

### 21.1. Chặn nhầm bởi automation

Một emergency account native có thể cần được **loại trừ có kiểm soát khỏi một số policy/federation/automation** để sống sót qua failure mode dự kiến. Nhưng không phải loại trừ toàn bộ governance.

Ví dụ:

- Account không phụ thuộc vào SSO khi SSO outage.
- Có thể không chịu một rule conditional access gây lockout toàn bộ admin, tùy hướng dẫn nền tảng.
- Không bị SCIM deprovision vì thiếu HR employee record nếu nó là tài khoản kỹ thuật đặc thù.
- **Vẫn phải có owner, inventory, credential lifecycle, monitoring, access review và audit**.

**“Ngoại lệ kỹ thuật để tồn tại khi sự cố” khác hoàn toàn “tài khoản không ai quản lý”.**

### 21.2. Authentication không phải authorization

Một emergency account đăng nhập thành công mới chứng minh **có credential được hệ đích chấp nhận**. Nó không tự chứng minh sự cố hợp lệ hay người sử dụng được phê duyệt.

Runbook, custody, incident verification và post-review là lớp điều khiển bổ sung. Khi nền tảng cho phép, **PDP/PEP/RBAC/ABAC** vẫn giới hạn hành động/tài nguyên trong phạm vi phục hồi.

### 21.3. SCIM không phải công cụ thu hồi mọi emergency path

SCIM quản lý user/group theo capability của hệ đích. Nếu account khẩn cấp là native/local account không nằm trong SCIM, quy trình phải có **native lifecycle và reconciliation riêng**. Không kết luận mọi quyền đã hết chỉ vì SCIM `/Users` trả trạng thái inactive.

### 21.4. Session và token

Ngay cả khi password đã rotate, một **access token, cookie, API credential hoặc target session** được tạo trước đó có thể vẫn hợp lệ. Cần xử lý session/token revocation, short TTL, introspection/current-state checks khi nền tảng hỗ trợ, và kiểm tra đường truy cập còn sống.

## 22. PBAC/RBAC/ABAC và thực thi chính sách emergency access

Có thể mô tả điều kiện sử dụng bằng policy, nhưng phải phân biệt **thẩm quyền sử dụng ở tình huống khẩn cấp** với **quyền kỹ thuật vốn có trong native account**.

### 22.1. Policy logic minh họa

~~~text
ALLOW emergency.activate WHEN
    incident.isConfirmed
    AND incident.category in allowedRecoveryScenarios
    AND responder.isCurrentlyAuthorized
    AND responder.relationship.isActive
    AND target in emergencyAccount.approvedTargets
    AND action within approvedRecoveryPurpose
    AND emergencyAccount.status == READY
    AND requiredCustodyEvidenceIsSatisfied
ELSE DENY
~~~

Mã giả này chỉ áp dụng khi những nguồn thông tin và policy engine còn khả dụng. Khi chúng bị outage, quy trình cần **fallback có thẩm quyền** được chuẩn bị trước.

### 22.2. Mẫu phối hợp online và offline

| Điều kiện | Chính sách điều khiển | Lưu ý |
| --- | --- | --- |
| IAM/PAM bình thường | JIT/PAM/PEP, manager/security approval theo risk | Không dùng break-glass |
| IdP/SSO lỗi, kho credential độc lập hoạt động | Native emergency login + incident custody | Cần bảo vệ yếu tố và hậu kiểm |
| PAM + workflow lỗi | Offline dual control hoặc preauthorized responder | Không bịa approval online |
| SIEM lỗi | Native logs, journal offline, post-ingestion | Evidence có thể PARTIAL |
| Target không xác minh được identity | Không tùy tiện coi login thành công là đủ | Đánh giá biện pháp phục hồi được hỗ trợ |
| Suspected compromise of emergency credential | Quarantine/rotate/recover theo runbook | Giữ phương án phục hồi khác tránh lockout |

### 22.3. Không dùng claim role stale để bảo vệ account

Nếu người sử dụng đã Mover/Leaver, claim `EmergencyResponder` trong token cũ không thể là căn cứ duy nhất. Khi các nguồn online không có sẵn, tổ chức phải có **roster/custody có kiểm soát và được cập nhật**; hậu kiểm đối soát trạng thái nhân sự thực tế.

## 23. Đóng phiên và thu hồi quyền sau khẩn cấp

Khi công việc phục hồi hoàn thành, tài khoản hoặc grant khẩn cấp không được bị bỏ lại trong trạng thái **đang sử dụng**.

### 23.1. Các lớp cần kiểm

1. **Session:** logout, terminate RDP/SSH/console và kiểm reconnect.
2. **Token:** revoke/invalidate khi có hỗ trợ, xem thời hạn tồn dư.
3. **Credential:** rotate/rekey hoặc xác minh secret chưa phơi lộ theo policy.
4. **Temporary role:** gỡ entitlement đã thêm vào user, group hoặc workload.
5. **Resource policy:** hoàn tác những lối mở tạm thời trên firewall, IAM, ACL, tenant.
6. **Trust settings:** kiểm federation/conditional access được khôi phục an toàn.
7. **Owner/delegation:** gỡ quyền điều phối khẩn cấp cấp tạm.
8. **Automation:** dừng job/tunnel, xoá temporary artifact/secret không còn cần.
9. **Evidence:** ghi đầy đủ incident, thay đổi, bản ghi, kết quả và hậu kiểm.
10. **Readiness:** test account vẫn sẵn sàng cho sự cố tiếp theo nếu không decommission.

### 23.2. Không đồng nhất “logout” với “hoàn tất”

Một người logout khỏi cloud console có thể đã tạo access key dài hạn hoặc cấp thêm một role admin. **Quyền mới có thể sống lâu hơn phiên khẩn cấp**.

Vì vậy cần **diff quyền và cấu hình trước/sau**, kiểm audit API, role grants, local accounts và các credential phát sinh.

## 24. Hậu kiểm, rotation và vòng đời bí mật

### 24.1. Sau mỗi lần sử dụng

Một post-use review có thể yêu cầu:

- Xác minh incident và lý do dùng đúng chính sách.
- Xác định **người sử dụng thực**, account, target, thời gian.
- Đối chiếu log và những thay đổi đã thực hiện.
- Đánh giá có truy cập resource ngoài phạm vi không.
- Kiểm còn session/token/role/credential được tạo thêm không.
- Xác định mức phơi lộ credential, có cần rotation/rekey khẩn cấp không.
- Ghi event rotation/change và kiểm phương án mới hoạt động.
- Cập nhật runbook và điểm yếu đã phát hiện.
- Reviewer độc lập chấp thuận đóng hồ sơ.

### 24.2. Rotation không chỉ là đổi password

Có thể có:

- Password native.
- Hardware security key hoặc MFA recovery method.
- Recovery codes/seed/certificate.
- API key hoặc client secret dùng trong recovery workflow.
- SSH keys và trust của host.
- Các bản sao vật liệu khôi phục offline.

Đổi một password nhưng để alternate factor cũ không kiểm soát có thể vẫn còn **đường truy cập tồn dư**. Tùy nền tảng, cần revocation, re-enrollment hoặc thay bộ recovery factors.

### 24.3. Rotation phải được thử nghiệm

Sau khi rotation, nếu emergency account không đăng nhập được, tổ chức đã vô tình phá đường phục hồi. Nên dùng **quy trình kiểm tra có kiểm soát**, tránh gây lockout và giữ fallback độc lập.

### 24.4. Khi nghi lộ secret

Đánh giá ngay credential có thể đã bị xem/sao chép bởi ai, kiểm các đăng nhập bất thường, giới hạn sử dụng, thay credential/factor khi an toàn và mở incident bảo mật theo policy. Không xóa bằng chứng gốc trước khi điều tra.

## 25. Thiết kế runbook truy cập khẩn cấp

Runbook phải **thực thi được khi một phần hạ tầng đang lỗi**, không chỉ là đường link tới portal có thể mất khả dụng.

### 25.1. Mẫu runbook (không chứa credential thật)

~~~yaml
runbookId: IAM-EMERGENCY-ACCESS-01
version: 3
purpose: Restore critical administrative access
scenario: SSO_OR_FEDERATION_LOCKOUT
scope:
  - identity-management-tenant
incidentRequirement:
  severity: critical
  incidentRefRequired: true
authorizedRoles:
  - incident-commander
  - emergency-responder
  - credential-custodian
approvalMode:
  normal: approved-online-workflow
  fallback: documented-offline-dual-control
authentication:
  recoveryMethodRef: controlled-recovery-custody
  mustNotDependOnFailedIdP: true
recording:
  preferred: native-audit-and-managed-session
  fallback: protected-offline-journal-and-native-logs
postUse:
  - terminate-privileged-session
  - review-changes-and-new-privileges
  - revoke-temporary-grants
  - rotate-or-resecure-credentials
  - verify-emergency-readiness
  - independent-post-incident-review
~~~

Đây là **metadata mẫu, không chứa secret hoặc hướng dẫn bypass cụ thể**. Trường `mustNotDependOnFailedIdP` cần được xác minh bằng bài test thực tế, không chỉ khai báo.

### 25.2. Những nội dung runbook cần trả lời

- Kịch bản nào được phép kích hoạt?
- Ai ra quyết định và ai thực thi?
- Khi IdP/PAM/ticketing/SIEM lỗi, làm sao tìm đúng runbook?
- Vật liệu credential được cất ở đâu theo cơ chế quản lý (không phải ghi trực tiếp secret)?
- Làm sao xác minh người sử dụng?
- Target nào được phép và hành động nào cần approval bổ sung?
- Có phương án **không thể dùng đường phục hồi chính** không?
- Khi nào kết thúc, ai review, chứng cứ tối thiểu nào phải lưu?
- Khi một factor/custodian mất, ai chịu trách nhiệm sửa phương án?
- Có kiểm tra expiry, quyền mới được cấp, role chưa thu hồi và account readiness không?

### 25.3. Runbook có thể cần bản offline được kiểm soát

Nếu mọi hướng dẫn chỉ nằm trong wiki yêu cầu SSO, lúc SSO outage không ai mở được. Có thể chuẩn bị **bản offline có quản trị version/custody**; bản đó không nên chứa mật khẩu plaintext hoặc những dữ liệu quá nhạy cảm không cần thiết.

## 26. Thử nghiệm định kỳ và diễn tập failure modes

**Một break-glass account chưa được thử nghiệm không nên được coi là đã sẵn sàng.**

### 26.1. Các loại thử nghiệm

| Loại | Mục tiêu | Yêu cầu an toàn |
| --- | --- | --- |
| **Inventory review** | Account/owner/custodian còn đúng | Không tiết lộ secret |
| **Authentication test** | Recovery method vẫn hoạt động | Kiểm soát thời gian, target và phạm vi |
| **Dependency outage exercise** | Đường cứu hộ vẫn dùng được nếu SSO/PAM lỗi | Dùng lab/simulation hoặc test có kiểm soát |
| **MFA/factor recovery test** | Một factor hỏng vẫn có phương án được duyệt | Không hủy toàn bộ yếu tố còn hoạt động |
| **Privilege scope test** | Account có đủ quyền phục hồi, không quá rộng | Không sửa production ngoài kế hoạch |
| **Alert test** | Usage kích hoạt SOC notification | Phân biệt test với incident thật |
| **Audit/replay test** | Session/native logs được thu và xem lại | Kiểm quyền truy cập evidence |
| **Rotation test** | Credential mới hoạt động, bản cũ hết hiệu lực | Tránh gây lockout |
| **Leaver/Mover test** | Người cũ không còn custody/khả năng dùng | Dựa danh tính/secret lifecycle |
| **Restore-to-normal test** | Kết thúc emergency session và gỡ grant | Readback target và reconciliation |

### 26.2. Tránh “test” phá môi trường production

Không nên thử phá federation thật hoặc vô hiệu hóa toàn bộ admin trong môi trường production chỉ để chứng minh recovery. Ưu tiên **lab, staging, chaos scenario có guardrails hoặc diễn tập theo quy trình thay đổi được phê duyệt**.

Đối với hệ không có môi trường giả lập đầy đủ, cần test ở mức có thể chấp nhận rủi ro, kèm phương án khôi phục và người chịu trách nhiệm.

### 26.3. Điểm cần đo

- Account có thể đăng nhập với phương thức dự phòng được hỗ trợ không?
- Có cần phụ thuộc một identity provider đang giả lập lỗi không?
- Cần bao nhiêu người/thiết bị và họ có sẵn theo lịch trực không?
- Cảnh báo có tới người phụ trách không?
- Bằng chứng có đầy đủ và không lộ secret không?
- Sau test, quyền/phiên có được thu hồi và account trở về READY không?

### 26.4. Kỳ thử nghiệm

Không có chu kỳ phổ quát cho mọi tổ chức. Lịch nên phụ thuộc **mức rủi ro, tốc độ thay đổi tenant/IdP, policy, đội on-call và yêu cầu kiểm toán**. Cần thử lại sau những thay đổi quan trọng: cập nhật MFA, thay đổi federation, đổi vault, owner Mover/Leaver hoặc sửa conditional access.

## 27. Sự cố thực tế giả định: khóa toàn bộ IAM admin

### 27.1. Bối cảnh

Một doanh nghiệp sử dụng SSO cho cloud admin. Trong một đợt rollout, policy conditional access mới chặn cả nhóm quản trị khỏi management console. Đội vận hành không thể rollback qua đường tiêu chuẩn.

### 27.2. Các bước xử lý

1. SOC/on-call phát hiện nhiều login denied và nhận dạng sự cố có thể thuộc use case khẩn cấp.
2. Incident commander xác minh phạm vi, ghi incident ID và chọn runbook đã được duyệt.
3. Hai custodian/authorized responders (theo policy) xác nhận yêu cầu sử dụng recovery identity.
4. Người trực dùng **đường xác thực native dự phòng đã được chuẩn bị**, không phụ thuộc vào federation vừa bị lỗi.
5. Chỉ thao tác để xác định policy sai và khôi phục đường quản trị.
6. Native control-plane audit ghi login và thay đổi; nếu PAM/SIEM unavailable thì lưu thêm journal bảo vệ.
7. Sau khi admin bình thường hoạt động, kiểm những quyền/ngoại lệ tạm.
8. Đóng emergency session, xử lý credential/factor, kiểm active tokens và role changes.
9. Independent reviewer xem sự kiện, đánh giá nguyên nhân và khả năng lạm dụng.
10. Thực hiện readiness test và quay lại quy trình JIT/PAM thông thường.

**Các bước là tình huống giáo dục**, không phải hướng dẫn thao tác nhà cung cấp. Chi tiết recovery thực tế phải tuân theo sản phẩm, policy và runbook của tổ chức.

### 27.3. Những điều có thể đi sai

- Recovery password nằm trong vault đăng nhập bằng SSO đã hỏng.
- Emergency account bị chính conditional access policy mới chặn.
- Người giữ factor đã Leaver nhưng chưa bàn giao.
- Account bị deprovision do automation coi là nhân viên không hoạt động.
- Vì khẩn cấp, operator bật quyền admin cho nhiều nhóm rồi quên gỡ.
- Không có audit vì toàn bộ logging phụ thuộc PAM đang lỗi.
- Sau recovery, account bị khóa do một bài test MFA thất bại không có phương án thứ hai.

Giải pháp không chỉ là “giữ một tài khoản admin”, mà là **kiến trúc recovery, custody, quyền, evidence và lifecycle hoàn chỉnh**.

## 28. Tình huống giả định: PAM outage và truy cập hệ thống đích

Một database production cần xử lý sự cố, nhưng PAM gateway không hoạt động. Có đường truy cập dự phòng đã được security phê duyệt.

### 28.1. Cách tiếp cận an toàn

- Incident xác nhận đường PAM đang lỗi và tại sao không thể đợi phục hồi PAM.
- Kiểm target/operation được phép; không dùng account toàn quyền cho nhiều DB khác.
- Truy cập qua emergency path với credential custody và actor attribution.
- Bật native DB audit/OS audit trong phạm vi khả dụng.
- Ghi thao tác theo change/incident ID.
- Sau khi PAM hồi phục, đóng kết nối đặc quyền dự phòng, xử lý DB grants/keys và verify session.
- Đánh dấu evidence **PARTIAL** nếu không có session recording như thông thường.
- Security review mọi thay đổi và kiểm không còn direct access không kiểm soát.

### 28.2. Nguy cơ ngoài thời gian sự cố

Một direct management port được mở để cứu DB có thể còn tồn tại sau sự cố. **Chính mạng/ACL/tunnel được mở tạm cũng là quyền truy cập tồn dư**, không chỉ account và password.

## 29. Kiểm toán và dữ liệu sự kiện

Một mẫu **sự kiện sử dụng break-glass** nên giúp điều tra được ai dùng, khi nào, vì sao, quyền nào và kết quả.

~~~json
{
  "eventType": "EMERGENCY_ACCESS_USED",
  "incidentRef": "INC-2026-1041",
  "emergencyAccountRef": "emg-cloud-tenant-a-01",
  "operatorIdentityRef": "person-1042",
  "custodianIdentityRefs": ["person-501", "person-608"],
  "targetResourceRef": "cloud-tenant-a-management",
  "recoveryScenario": "FEDERATION_LOCKOUT",
  "authorizationMode": "PREAUTHORIZED_WITH_DUAL_CONTROL",
  "sessionRef": "emg-session-771",
  "privilegeScope": ["identity-policy-recovery"],
  "startedAt": "2026-11-23T10:15:00+07:00",
  "endedAt": "2026-11-23T10:47:00+07:00",
  "nativeAuditStatus": "AVAILABLE",
  "recordingStatus": "PARTIAL",
  "temporaryGrantsRemoved": true,
  "credentialFollowup": "REVIEWED",
  "postIncidentReviewRef": "review-884"
}
~~~

Đây là **dữ liệu minh họa**, không phải schema chuẩn. Đặc biệt, boolean `temporaryGrantsRemoved=true` chỉ nên được đặt khi có bằng chứng thực; không nhận giá trị này do operator tự khai mà không xác minh.

### 29.1. Decision khác execution

~~~text
Break-glass approved / authorized = YES
Actual emergency login = FAILED
Restoration operation = NOT_PERFORMED
Evidence status = LOGIN_FAILURE_RECORDED
~~~

Và:

~~~text
Emergency login = SUCCEEDED
Restoration operation = SUCCEEDED
Temporary admin role cleanup = INCOMPLETE
Incident status = OPEN_EXCEPTION
~~~

Không đánh dấu `SUCCESS` cho toàn bộ quy trình chỉ vì cuối cùng hệ thống đăng nhập lại được. **Phần cleanup và chứng cứ cũng là đầu ra bắt buộc**.

### 29.2. Những dữ liệu không nên lưu

- Password, OTP, recovery code, private key.
- Raw access/refresh tokens, session cookies.
- Thông tin bí mật về nơi cất yếu tố nếu không cần và chưa bảo vệ.
- Dữ liệu cá nhân hoặc business data không liên quan incident.

Audit lưu **tham chiếu và bằng chứng đủ để truy vết**, với encryption, access control, retention và chain of custody phù hợp.

## 30. Reconciliation sau emergency access

**Reconciliation** nhằm chứng minh trạng thái sau sự cố đúng với **desired access** và không có quyền khẩn cấp tồn dư.

### 30.1. Ba lớp cần đối chiếu

~~~text
DESIRED:
  Emergency account sẵn sàng, có owner và quyền phục hồi được duyệt
  Temporary grants = none ngoài incident active
  Responder roster = những người hiện hành
  Emergency sessions = closed

OBSERVED:
  Account/role, network path, secret/factor, session/token
  Native/cloud IAM grants và local privileged accounts
  Credential access log và actual audit events

EFFECTIVE:
  Người cũ có còn dùng được đường phục hồi không?
  Có role/token/tunnel/capability mới được giữ lại không?
  Account vẫn usable cho incident kế tiếp không?
~~~

### 30.2. Phân loại sai lệch

| Loại drift | Ví dụ | Hành động |
| --- | --- | --- |
| **RESPONDER_DRIFT** | Leaver còn tên trong custody roster | Thu hồi, rotation/rekey và review |
| **PRIVILEGE_DRIFT** | User bình thường giữ cloud admin sau incident | Gỡ role, rà scope |
| **CREDENTIAL_DRIFT** | Secret cũ/alternate factor còn hiệu lực | Rotate/revoke theo risk |
| **SESSION_RESIDUAL** | SSH/RDP/browser session còn sống | Terminate và verify |
| **NETWORK_PATH_RESIDUAL** | Direct port/tunnel vẫn mở | Đóng đường tạm |
| **ACCOUNT_NOT_READY** | Recovery account bị disable hoặc MFA hỏng | Sửa và retest |
| **AUDIT_GAP** | Usage không có native evidence | Incident exception và remediation |
| **OWNER_GAP** | Custodian/owner đã Leaver | Chỉ định owner, rà quyền |
| **OVER_PRIVILEGED_EMERGENCY_ACCOUNT** | Account được gán role quá rộng không có lý do | Giảm scope và kiểm availability |

### 30.3. Khi nào có thể đóng một sự cố?

Một incident có thể được đánh dấu phục hồi nghiệp vụ khi dịch vụ hoạt động. Nhưng **security cleanup** có thể chưa hoàn tất. Nên tách **service restored, emergency usage closed, privilege revoked, evidence preserved, post-review completed** để không che các ngoại lệ.

## 31. Chỉ số vận hành break-glass

| Chỉ số | Ý nghĩa | Điều cần tránh |
| --- | --- | --- |
| **Emergency account readiness coverage** | Tỷ lệ target/failure scenarios có đường recovery được kiểm | Chỉ đếm số account |
| **Test success rate** | Diễn tập truy cập thành công đúng kịch bản | Test chỉ login khi mọi hệ bình thường |
| **Dependency independence** | Recovery path không phụ thuộc thành phần gây outage | Một vault/IdP chung cho mọi đường |
| **Unauthorized use attempts** | Lần dùng không có incident hoặc authority | Coi mọi usage là hợp lệ |
| **Usage alert latency** | Từ login tới SOC/owner nhận cảnh báo | Log không có người xử lý |
| **Time to restore admin access** | Thời gian từ sự cố tới có đường quản trị an toàn | Mở quyền quá rộng để nhanh |
| **Post-use review completion** | Lần sử dụng có review độc lập đúng hạn | Đóng hồ sơ ngay sau login |
| **Credential resecure latency** | Từ kết thúc usage tới rotation/verification theo policy | Coi đổi password là đủ |
| **JML custody revocation latency** | Từ Mover/Leaver tới khi người cũ mất quyền tiếp cận | Chỉ gỡ group IdP |
| **Residual privilege count** | Role/token/session/tunnel còn sau incident | Không kiểm effective access |
| **Break-glass drift incidents** | Account bị disable, thiếu factor/owner hoặc scope sai | Không diễn tập định kỳ |
| **Audit completeness** | Có actor, target, incident, session, action, outcome | Lưu secret trong log |
| **Unplanned emergency usage** | Lần sử dụng ngoài use case được duyệt | Chuẩn hóa việc dùng hằng ngày |

Không có SLA chung cho mọi hệ. Đặt mục tiêu theo **criticality, recovery time objectives, môi trường, các phụ thuộc và khả năng nền tảng**.

## 32. Ma trận kiểm thử âm tính và kịch bản thất bại

| Kịch bản | Kỳ vọng |
| --- | --- |
| Người không thuộc responder roster xin credential | Bị từ chối, audit |
| Custodian đã Leaver vẫn dùng vault/token cũ | Không truy xuất được hoặc escalation/rotation |
| IdP outage nhưng emergency account dựa vào chính SSO | Test phát hiện thiết kế không sẵn sàng |
| PAM outage nhưng vault chỉ mở qua PAM | Phát hiện circular dependency, dùng fallback được duyệt |
| Factor chính bị mất | Có phương án dự phòng bảo vệ và được kiểm thử |
| Account khẩn cấp bị disable do SCIM rule chung | Cảnh báo readiness drift |
| Login vào emergency account ngoài incident | Alert và xử lý như nghi ngờ lạm dụng |
| Account dùng cho tác vụ thường lệ | Policy violation và remediation |
| Operator truy cập sai tenant/resource | Chặn theo scope hoặc audit/exception cấp cao |
| Người dùng sửa incidentRef trong client để tự hợp thức hóa | Backend/authority không tin client |
| Incident commander unavailable | Fallback thẩm quyền đã định hoặc không mở quyền trái policy |
| Recorder/SIEM lỗi | Native audit/offline evidence, ghi PARTIAL |
| Sau emergency logout nhưng role cloud mới còn | Phát hiện residual privilege |
| Password rotate nhưng alternate factor còn ở người cũ | Kiểm credential/factor lifecycle đầy đủ |
| SSH tunnel không đóng sau PAM outage | Detect/close network path |
| Emergency account chứa secret của ứng dụng đang chạy | Phát hiện sai thiết kế, tách service identity |
| Không có owner account và contact lỗi thời | Chặn trạng thái READY, sửa owner và test |
| Hai người đồng thời dùng shared credential | Alert, correlation và SoD/custody review |
| Sự cố khẩn cấp đã qua nhưng exception không hết hạn | Cleanup/reconciliation bắt buộc |
| Disabling account trước khi có recovery khác | Block decommission, đánh giá continuity |
| Restore thử trong production gây thay đổi không kế hoạch | Test failed, giữ evidence và cải thiện guardrails |
| Reviewer tự đánh giá hành động của chính mình ở quyền cao | Independent review theo SoD |
| Account có login success nhưng không có quyền sửa cấu hình cần thiết | Readiness failure; policy/role fix với approval |

### 32.1. Test end-to-end

~~~text
Approved failure scenario
 -> named responder / custodian eligibility
 -> independent credential/factor retrieval
 -> native recovery authentication
 -> minimal privileged action
 -> audit / incident correlation
 -> session closure / credential resecure
 -> cleanup temporary IAM/network grants
 -> effective access verification
 -> independent review
 -> account readiness retest
~~~

Một bài test chỉ thử **đăng nhập** chưa chứng minh đường phục hồi có thể **sửa lỗi và quay lại trạng thái an toàn**.

## 33. Checklist thiết kế và vận hành

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Đã xác định các failure scenarios cần break-glass? | Threat model, BCP/DR plan |
| Account có owner, target scope và mục đích rõ? | Emergency identity inventory |
| Đường recovery hoạt động khi IdP/SSO lỗi? | Dependency map và test |
| Credential có thể truy xuất khi PAM/vault lỗi? | Custody fallback được duyệt |
| Có auth method/factor đủ mạnh và khả dụng? | Factor readiness test |
| Có phương án nếu một custodian hoặc thiết bị mất? | Backup custody test |
| Có danh sách responder hiện hành theo JML? | Identity/HRIS roster |
| Có kiểm quyền và SoD ở điều kiện bình thường? | Policy/approval runbook |
| Có giải pháp khi online approval không thể dùng? | Offline/preauthorized authority |
| Có giới hạn admin privilege tới mục tiêu phục hồi? | Role/permission mapping |
| Account có bị dùng trong automation thường lệ không? | Service account inventory |
| Có cảnh báo mọi usage và thay đổi factor/role? | Native/cloud audit và SOC delivery |
| Có log khi SIEM/session recording bị outage? | Native/offline evidence |
| Có phân biệt actor/custodian/account kỹ thuật? | Incident correlation IDs |
| Có retention và bảo vệ bằng chứng? | Access controls, audit policy |
| Có runbook được quản trị version và truy xuất khi outage? | Offline-safe instructions |
| Có thử kịch bản federation/conditional access lockout? | Exercise evidence |
| Có kiểm account không bị disable bởi automation sai? | SCIM/IAM exclusion review |
| Có kiểm token/session/role mới tạo sau sự cố? | Post-use diff |
| Có xử lý SSH tunnel, firewall rule mở tạm? | Target/network reconciliation |
| Có rotation/rekey khi secret/factor có nguy cơ lộ? | Credential follow-up record |
| Có bảo vệ alternate recovery methods không? | Recovery method inventory |
| Có người độc lập hậu kiểm? | Incident review approval |
| Có SLA xử lý quyền tồn dư và exception? | Owner/remediation tracking |
| Có lịch retest sau thay đổi lớn/Leaver của custodian? | Readiness change triggers |
| Khi decommission, có recovery path thay thế đã test? | Replacement verification |
| Có tách trạng thái restored/closed/verified? | Incident workflow states |

## 34. Những nhầm lẫn thường gặp

1. **“Break-glass là tài khoản Admin dùng khi muốn nhanh.”** Chỉ dùng trong kịch bản khẩn cấp có thẩm quyền.
2. **“Account đăng nhập qua chính SSO lỗi vẫn cứu được SSO.”** Cần independence phù hợp.
3. **“Để mật khẩu trong wiki cho mọi admin là an toàn vì tiện.”** Credential custody cần bảo vệ.
4. **“Đã dùng mật khẩu mạnh thì không cần risk controls khác.”** Cần monitoring, SoD, hậu kiểm.
5. **“Không có MFA là điều kiện bắt buộc cho mọi break-glass.”** Ưu tiên phương thức mạnh và độc lập khi có thể.
6. **“Dual control chắc chắn tăng availability.”** Có thể thành single point nếu không có người trực.
7. **“Account emergency nên được loại khỏi mọi IAM governance.”** Ngoại lệ kỹ thuật vẫn cần owner, audit, review.
8. **“SCIM disable mọi user khác tức đã xử lý emergency account.”** Native account có vòng đời riêng.
9. **“Một Leaver không biết credential nữa vì đã mất email.”** Bí mật có thể đã được sao chép.
10. **“Rotate password là mọi token/session đã hết.”** Cần xử lý session, key và alternate factor.
11. **“Dùng break-glass thì mọi hành động đều hợp lệ.”** Scope và purpose vẫn áp dụng.
12. **“Hệ thống hồi phục là incident hoàn tất.”** Còn cleanup, reconciliation và hậu kiểm.
13. **“Không có recording nghĩa không cần audit.”** Native logs và offline evidence vẫn quan trọng.
14. **“Tài khoản root là break-glass dù không có owner/runbook.”** Chỉ là account quyền cao chưa được quản trị.
15. **“Dùng emergency account cho CI/CD thì đơn giản hơn.”** Làm trộn human recovery và service workload.
16. **“Có hai account nhưng cùng một factor bị hỏng là đã dự phòng.”** Dự phòng cần xét failure domains.
17. **“MFA outage thì có thể bỏ hết chính sách xác thực.”** Phải chọn fallback có kiểm soát.
18. **“Account lâu không dùng thì có thể xóa mà không test thay thế.”** Có thể mất khả năng phục hồi.
19. **“Có audit login là biết chính xác người nào thao tác.”** Shared account cần attribution/custody evidence.
20. **“Cảnh báo tự động là đủ.”** Cần người tiếp nhận, phản ứng và review.

## 35. Câu hỏi tự đánh giá

1. Break-glass account khác PAM/JIT và tài khoản admin thường ở điểm nào?
2. Nêu ba sự cố thuộc phạm vi khẩn cấp và ba tình huống không nên dùng.
3. Vì sao credential recovery chỉ lưu trong vault dùng SSO có thể tạo circular dependency?
4. Independence có đồng nghĩa được bỏ MFA không? Giải thích.
5. Những vai trò nào có thể tham gia custody, vận hành và hậu kiểm?
6. Vì sao cần quản lý riêng account lifecycle, responder JML và credential lifecycle?
7. Khi custodian Mover sang bộ phận khác, những quyền và phương tiện nào phải rà lại?
8. Khi responder Leaver, vì sao chỉ disable IdP chưa đủ?
9. Vì sao không nên xóa luôn một emergency account chung khi người tạo nó nghỉ việc?
10. Làm thế nào tránh account khẩn cấp trở thành service account chạy thường xuyên?
11. Với một cloud tenant, dấu hiệu nào cho thấy emergency path có thể bị chính conditional access khóa?
12. Bảng audit nên chứa những trường nào để gắn actor với technical emergency account?
13. Native audit khác PAM session recording ở đâu?
14. Một người logout nhưng đã tạo access key mới: quy trình kết thúc cần xử lý gì?
15. Rotating password có tự revoke access token hoặc recovery factor khác không?
16. Test nào chứng minh account có thể phục hồi sau federation outage, không chỉ login khi SSO khỏe?
17. Cần làm gì khi SIEM và ticketing đều không khả dụng?
18. Vì sao cần kiểm quyền network/tunnel tạm sau khi phục hồi dịch vụ?
19. Một emergency account có quyền global admin thường trực có những rủi ro nào?
20. Hãy nêu các bước post-use review tối thiểu.
21. Đối soát desired và observed privilege cho break-glass gồm những nguồn nào?
22. Tại sao “100% break-glass test login success” chưa đủ chứng minh khả năng phục hồi?
23. Khi nghi credential bị lộ, nên xử lý bảo toàn chứng cứ và rotation thế nào?
24. Nêu các rủi ro khi sử dụng dual control nhưng chỉ một người giữ factor dự phòng.
25. Định nghĩa tiêu chí chuyển trạng thái account từ POST_USE_REVIEW về READY.

## 36. Ghi nhớ

**Break-glass account** là một **danh tính hoặc tài khoản truy cập khẩn cấp được chuẩn bị, bảo vệ và kiểm thử trước** để phục hồi quyền quản trị khi đường thông thường như **IdP/SSO, MFA, federation hoặc PAM** không khả dụng. Nó khác tài khoản quản trị hằng ngày ở **mục đích sử dụng ngoại lệ, phương án authentication/custody dự phòng, thẩm quyền, giới hạn phạm vi, giám sát và hậu kiểm**.

Trong quản lý danh tính theo **Joiner–Mover–Leaver**, phải đồng thời quản lý **emergency account, người trực/custodian, credential/factor, quyền tạm, session/token và resource access**. **IdP/SSO** xác thực theo đường thông thường, **SCIM/API** quản trị một số account/entitlement, **RBAC/ABAC/PBAC và PEP** giới hạn hành động khi khả dụng, còn **PAM, native audit, incident evidence và reconciliation** giúp phát hiện lạm dụng và quyền tồn dư. Để vận hành an toàn, phương án cứu hộ phải **độc lập với điểm lỗi cần phục hồi nhưng không đứng ngoài quản trị bảo mật**. Kết thúc sự cố không chỉ là đăng nhập lại được, mà còn phải **thu hồi đường truy cập tạm, bảo vệ credential, xác minh không còn đặc quyền tồn dư, lưu bằng chứng và kiểm tra account vẫn sẵn sàng cho lần khẩn cấp tiếp theo**.
