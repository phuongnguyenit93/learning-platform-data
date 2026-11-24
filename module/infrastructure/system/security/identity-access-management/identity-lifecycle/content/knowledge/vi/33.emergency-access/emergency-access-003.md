# Điều kiện kích hoạt Emergency access trong vòng đời danh tính IAM

> **Chương: Emergency access.** **Điều kiện kích hoạt (activation conditions)** xác định **khi nào** một chủ thể được phép mở đường **truy cập khẩn cấp** (emergency access, thường gọi là break-glass), **ai** đủ tư cách sử dụng, **quyền và tài nguyên nào** được phép, **bằng chứng nào** phải có và **khi nào** quyền khẩn cấp bắt buộc chấm dứt. Đây là cơ chế dự phòng cho những tình huống được tổ chức định nghĩa trước khi **đường truy cập thông thường không đáp ứng một nhu cầu ứng cứu đủ mức độ nghiêm trọng**, chứ không phải đặc quyền vô điều kiện hoặc cách bỏ qua phê duyệt vì tiện. Trong IAM Identity Lifecycle, các điều kiện kích hoạt phải gắn với **Joiner–Mover–Leaver**, nguồn danh tính, IdP/SSO, SCIM, RBAC/ABAC/PBAC, PAM/PIM, kiểm toán và thu hồi quyền tồn dư.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **sự cố khẩn cấp**, **điều kiện đủ để kích hoạt**, **điều kiện phủ quyết**, **điều kiện duy trì** và **điều kiện kết thúc** của emergency access.
2. Thiết kế **activation policy** gồm severity, impact, phương án bình thường không khả dụng, identity eligibility, authority, scope, approval, expiry và evidence.
3. Nhận biết những tình huống **có thể kích hoạt** và những tình huống **không nên kích hoạt**, bao gồm outage IdP/PAM, khôi phục sản xuất, sự cố bảo mật, kỳ hạn xử lý công việc và diễn tập.
4. Phân biệt **kích hoạt emergency account, kích hoạt emergency role/entitlement, cấp credential tạm và mở privileged session**.
5. Phân tích rủi ro **MFA/SSO/PAM cùng bị lỗi**, thiết kế đường khôi phục độc lập có kiểm soát và không dùng fallback `permit-all`.
6. Áp dụng **least privilege, time-bound access, SoD, JIT/JEA**, kiểm tra điều kiện theo JML và các danh tính máy.
7. Xây dựng quy trình kích hoạt, kiểm chứng tại PEP/target, kết thúc, hậu kiểm, test và audit có bằng chứng.

## 1. Bài toán mở đầu: khi nào được phá kính?

Giả sử dịch vụ thanh toán production bị gián đoạn, đội vận hành cần sửa cấu hình. Quy trình thông thường yêu cầu đăng nhập qua IdP, xác thực nhiều yếu tố và xin kích hoạt role có thời hạn trong PAM/PIM.

Hai trường hợp trông gần giống nhau nhưng **không nên có cùng kết quả**:

| Tình huống | Bối cảnh | Có thể kích hoạt emergency access? |
| --- | --- | --- |
| **A — Sự cố nghiêm trọng, đường bình thường không dùng được** | Production ngừng xử lý thanh toán, IdP/PAM không khả dụng; người phụ trách ứng cứu đã xác nhận và cần một thao tác khôi phục cụ thể. | **Có thể**, nếu đáp ứng policy và còn cơ chế khôi phục độc lập, đủ quyền, ghi nhận và kiểm soát. |
| **B — Công việc có kế hoạch nhưng chưa xin approval** | Kỹ sư cần deploy phiên bản mới, workflow phê duyệt vẫn hoạt động, chỉ muốn bỏ qua chờ duyệt. | **Không**, trừ khi policy khẩn cấp thực sự được kích hoạt bởi một sự kiện rủi ro độc lập. |
| **C — SSO lỗi nhưng hệ thống không bị ảnh hưởng cần ứng cứu ngay** | Nhân viên muốn xem dashboard thông thường vì SSO lỗi ngắn hạn. | **Không mặc nhiên**; chỉ outage không đủ để mở đặc quyền cao. |
| **D — Phát hiện xâm nhập tài khoản admin** | Các phiên admin bị nghi chiếm đoạt; đội ứng cứu cần quyền cách ly tài nguyên trong môi trường bị ảnh hưởng. | **Có thể** qua đường ứng cứu chuyên dụng nếu identity, kênh và thiết bị khẩn cấp đáng tin. |
| **E — Diễn tập được phê duyệt** | Đội kiểm thử khả năng sử dụng account khẩn cấp theo kế hoạch và giới hạn an toàn. | **Có thể dưới chế độ diễn tập**, không được coi là sự cố thực hoặc tự mở rộng quyền. |

**Điểm cốt lõi:** một sự cố nghiêm trọng là **tín hiệu cần xem xét**, không phải điều kiện duy nhất đủ để Permit. Kích hoạt đòi **một tổ hợp điều kiện**, đồng thời không có điều kiện phủ quyết.

## 2. Emergency access, break-glass và privileged access khác nhau thế nào?

| Thuật ngữ | Diễn giải | Quan hệ với điều kiện kích hoạt |
| --- | --- | --- |
| **Emergency access** | Khả năng sử dụng đường truy cập đặc biệt để khắc phục tình huống khẩn cấp được định nghĩa. | Phải có trigger, eligibility, scope, time bound, audit và kết thúc. |
| **Break-glass** | Mô hình/biện pháp dự phòng khi quy trình truy cập thường lệ không hoạt động hoặc không đáp ứng tình huống nghiêm trọng. | Không đồng nghĩa bypass mọi guard; điều kiện phải được quy định trước. |
| **Privileged access** | Quyền có ảnh hưởng lớn đến hệ thống, dữ liệu hoặc danh tính khác. | Có thể thuộc luồng bình thường (PAM/JIT) hoặc khẩn cấp. |
| **JIT/PIM activation** | Kích hoạt quyền đặc quyền theo yêu cầu, thường có hạn và approval. | Không phải mọi JIT activation đều là emergency. |
| **Emergency account** | Account được chuẩn bị để hỗ trợ đường khôi phục khi thành phần thường lệ bị lỗi. | Có thể tồn tại liên tục nhưng việc sử dụng phải bị hạn chế, báo động và hậu kiểm. |
| **Emergency entitlement** | Vai trò/quyền khẩn cấp chỉ được phép khi policy cho phép. | Cần kiểm tra scope và thời hạn dù account đăng nhập thành công. |
| **Emergency session** | Phiên thực hiện các thao tác ứng cứu. | Phải gắn với người/workload, resource, tình huống và cơ chế kết thúc. |

Một emergency account có thể được **tạo sẵn và cất giữ an toàn** để không phụ thuộc hệ thống đang lỗi; điều đó khác với **quyền được tùy tiện sử dụng mọi lúc**. Ở nền tảng khác, emergency role được cấp qua just-in-time và hoàn toàn không cần account riêng. Thiết kế phải theo **khả năng thực tế của target**.

### Không đồng nhất account ACTIVE với emergency access đang kích hoạt

~~~text
accountExists          = true
accountUsableForRoutine = false theo policy
emergencyAuthorized     = false trước khi có điều kiện kích hoạt
emergencySessionActive  = false

Khi sự cố đủ điều kiện:
    emergencyAuthorized = true theo workflow
    emergencySessionActive = true nếu xác thực và guard đạt

Sau kết thúc:
    emergencyAuthorized = false
    emergencySessionActive = false hoặc được xử lý theo policy/khả năng target
~~~

Trạng thái trên là **khái niệm**, không phải đặc tả của một hệ thống cụ thể. Có nền tảng emergency account luôn có thể đăng nhập về mặt kỹ thuật; khi đó cần các biện pháp bảo vệ ngoài luồng như custody, alert, kiểm tra sử dụng bất thường và hậu kiểm.

## 3. Mô hình năm lớp điều kiện kích hoạt

Một thiết kế tốt phân biệt:

1. **Trigger condition (điều kiện sự kiện):** có tình huống khẩn cấp thuộc loại được định nghĩa và có mức ảnh hưởng cần ứng cứu.
2. **Necessity condition (điều kiện cần thiết):** đường thường lệ không khả dụng hoặc không đáp ứng yêu cầu ứng cứu trong giới hạn rủi ro, và không có phương án ít quyền hơn có thể dùng hợp lý.
3. **Eligibility/authority condition (điều kiện chủ thể):** người/workload đang yêu cầu phù hợp danh sách được ủy quyền, có chứng cứ identity đáng tin và không bị thu hồi theo JML.
4. **Scope/control condition (điều kiện giới hạn):** phạm vi, thời hạn, tài nguyên, loại thao tác, authentication, SoD, giám sát và approval/kiểm soát bù đạt chính sách.
5. **Termination/review condition (điều kiện chấm dứt):** có owner, sự kiện hết hạn/khắc phục, quy trình vô hiệu phiên/credential và hậu kiểm độc lập.

### Biểu thức quyết định minh họa

~~~text
CAN_ACTIVATE =
    emergencyTriggerVerified
    AND necessityEstablished
    AND actorIdentityTrustedAndEligible
    AND authorityCoversIncidentAndResource
    AND requestedScopeWithinEmergencyPolicy
    AND requiredIndependentControlSatisfied
    AND workableAuthenticationAndCustodySatisfied
    AND activationWindowValid
    AND noMandatoryVeto
~~~

Biểu thức không phải cú pháp của RBAC/ABAC, XACML hay PAM. Tùy kịch bản, một vài điều kiện có thể được **tiền phê duyệt trước** và kích hoạt bằng quy trình khẩn cấp offline, nhưng điều đó phải được thiết kế **trước khi sự cố xảy ra**. Không tự bỏ điều kiện khi một dịch vụ kiểm tra bị lỗi.

### Phân biệt “cần”, “đủ” và “phủ quyết”

| Kiểu | Ví dụ | Tác động |
| --- | --- | --- |
| **Điều kiện cần** | Có incident ID hoặc bằng chứng sự cố được kênh ứng cứu hợp lệ xác nhận. | Thiếu thì chưa đủ cơ sở cho kích hoạt thông thường. |
| **Điều kiện cần nhưng không đủ** | IdP không hoạt động. | Không tự động mở quyền GlobalAdmin. |
| **Điều kiện đủ theo policy tổng hợp** | Incident nghiêm trọng + normal path unavailable + responder đủ authority + scope/TTL hợp lệ + control bắt buộc đạt. | Có thể kích hoạt đúng vai trò/phạm vi. |
| **Điều kiện phủ quyết** | Account đã Leaver, actor không được xác minh hoặc resource nằm ngoài scope được phép. | Không sử dụng đường khẩn cấp đó. |
| **Điều kiện dừng** | Incident đóng, thời gian hết, owner thu hồi, nghi lộ credential hoặc xuất hiện dấu hiệu lạm dụng. | Ngừng quyền, cô lập/revoke và hậu kiểm theo chính sách. |

## 4. Tín hiệu sự kiện: những nguyên nhân kích hoạt có thể hợp lệ

### 4.1. IdP/SSO bị gián đoạn

Nếu luồng đăng nhập liên kết không khả dụng và tổ chức cần khôi phục một thành phần trọng yếu, **emergency sign-in path** có thể được cho phép để tránh lockout toàn bộ quản trị. Tuy nhiên cần phân biệt:

- IdP lỗi nhưng production không có nhu cầu can thiệp đặc quyền ngay.
- IdP lỗi khiến không thể phục hồi các cấu hình trust hoặc xác thực.
- SSO lỗi trong một SaaS nhưng SaaS còn một admin đường local đặc biệt.
- Sự cố mạng chặn IdP từ một vùng, trong khi đường truy cập khác vẫn an toàn.

**Outage chỉ là điều kiện về khả dụng**, không chứng minh người muốn truy cập đang có authority hoặc nên được cấp quyền rộng.

### 4.2. PAM/PIM hoặc workflow cấp đặc quyền không khả dụng

Một sự cố ở PAM/PIM có thể khiến JIT activation, vault checkout hoặc session brokering bị chặn. Phải xác định:

1. Có hoạt động ứng cứu thật sự cần quyền không?
2. Có đường normal/standby ít rủi ro hơn không?
3. Khả năng cấp emergency credential có phụ thuộc cùng PAM đang lỗi không?
4. Có kiểm soát độc lập nào giúp bảo đảm attribution và log sau sự cố không?
5. Có cách giới hạn scope/action và revoke sau khi PAM phục hồi không?

**Không dùng điều kiện `PAM_TIMEOUT => ADMIN_PERMIT`**. Một timeout không thể là bằng chứng phê duyệt.

### 4.3. Sự cố production nghiêm trọng

Ví dụ database control plane không hoạt động, mất kết nối tới hệ thống critical hoặc cần khôi phục cấu hình bảo mật để tránh gián đoạn kéo dài. Những tín hiệu có thể gồm **mức độ ảnh hưởng tới dịch vụ, phạm vi khách hàng, mất tính toàn vẹn hoặc thời gian khôi phục được phép**.

Quyền mở ra nên gắn với **nhiệm vụ sửa lỗi xác định**, ví dụ restart một dịch vụ hoặc khôi phục một cấu hình trong project, chứ không mặc nhiên là quyền admin toàn tổ chức.

### 4.4. Incident an ninh

Khi nghi ngờ compromise IAM administrator, mất kiểm soát khóa hoặc cần cô lập tài nguyên, đường emergency có thể giúp đội ứng cứu:

- Thu hồi token/session bị nghi lộ theo khả năng nền tảng.
- Khóa một trust hoặc role bị chiếm quyền.
- Chặn thao tác nguy hiểm, khôi phục đường xác thực tin cậy.
- Bảo toàn/thu thập bằng chứng cần thiết theo quy trình ứng cứu.

Một **account/thiết bị/kênh vừa bị nghi compromise không phải nguồn đáng tin để tự xác nhận emergency activation**. Nên xác minh qua kênh và identity độc lập, theo playbook đã định.

### 4.5. Disaster recovery và lockout quản trị

Khi môi trường chính mất khả dụng và đường khôi phục phải hoạt động ngoài một dependency bị lỗi, policy có thể cho phép account/credential emergency trong cơ chế dự phòng. Activation phải đi kèm **thẩm quyền phục hồi, scope của vùng disaster recovery, ghi nhận và bảo đảm không tạo trust trái phép**.

### 4.6. Diễn tập, kiểm chứng và kiểm thử định kỳ

Diễn tập là một **loại activation được lập kế hoạch riêng**; cần quyết định trước:

- Ngày/giờ và môi trường kiểm thử hoặc thao tác production vô hại được phê duyệt.
- Chủ thể, người giám sát và expected alerts.
- Quyền nào có thể thử và hành động nào bị cấm.
- Cách xác nhận không làm thay đổi dữ liệu production ngoài mục tiêu test.
- Cách đóng phiên, reseal/rotate credential và lập báo cáo.

Không dùng **mã sự cố giả** để mở quyền ngoài phạm vi diễn tập đã duyệt.

## 5. Tình huống không đủ điều kiện và các dấu hiệu lạm dụng

| Tín hiệu | Vì sao không đủ hoặc có nguy cơ | Cách xử lý tốt hơn |
| --- | --- | --- |
| “Tôi quên xin quyền trước deadline.” | Không phải sự cố hệ thống được xác nhận. | Quy trình access request/JIT bình thường hoặc urgent approval hợp lệ. |
| “Manager đang nghỉ phép.” | Thiếu approver không tự chứng minh emergency. | Delegation/escalation có thẩm quyền. |
| “SSO bị chậm một lúc.” | Outage chưa gắn nhu cầu can thiệp trọng yếu. | Incident triage và lựa chọn đường ít quyền. |
| “Admin chính nghỉ việc nên tôi cần mật khẩu cũ.” | Dùng account đã Leaver hoặc shared secret trái JML. | Chuyển owner, account/role khẩn cấp đã chuẩn bị. |
| “Tôi là kỹ sư nhiều năm kinh nghiệm.” | Uy tín không chứng minh authority hiện hành. | Kiểm tra identity, roster, phạm vi và policy. |
| “Không có ticket, sau này bổ sung.” | Thiếu evidence và dễ bị lạm dụng. | Emergency record tối thiểu qua kênh dự phòng, bổ sung hậu kiểm theo policy. |
| “PDP không trả lời nên cứ Permit.” | Fail-open không xác minh rủi ro. | Đường cứu hộ riêng với guard và logging được thiết kế trước. |
| “Cần luôn GlobalAdmin cho nhanh.” | Phạm vi không tương xứng nhu cầu. | Giới hạn hành động, tài nguyên, thời gian, số phiên. |
| “Account break-glass vẫn đăng nhập được.” | Khả năng kỹ thuật không phải chấp thuận sử dụng. | Kích hoạt chỉ theo playbook và cảnh báo bất thường. |

**Điều kiện kích hoạt không được mô tả chung chung như “khi cần”**. Mỗi loại emergency nên có tiêu chí, người quyết định và phạm vi áp dụng đủ rõ để kiểm tra độc lập.

## 6. Mức độ nghiêm trọng, ảnh hưởng và tính cần thiết

Một activation policy có thể chia mức sự cố, nhưng tên **SEV-1, SEV-2...** là quy ước nội bộ, không phải chuẩn toàn ngành bắt buộc.

| Mức minh họa | Tác động | Ví dụ quyết định |
| --- | --- | --- |
| **Critical / SEV-1** | Dịch vụ trọng yếu ngừng, mất kiểm soát bảo mật quan trọng hoặc có nguy cơ tổn hại lớn. | Có thể xét emergency path ưu tiên, với authority và giới hạn vẫn bắt buộc. |
| **High / SEV-2** | Suy giảm lớn nhưng còn đường bình thường hoặc xử lý thay thế khả dụng. | Đánh giá necessity; có thể vẫn phải dùng normal JIT/approval. |
| **Medium / SEV-3** | Sự cố có phương án xử lý thông thường trong thời gian chấp nhận được. | Thường không mở emergency privilege. |
| **Low / Routine** | Bảo trì, thay đổi lên lịch, truy cập tiện ích. | Normal workflow. |

Một SEV-1 **không tự cấp quyền cho mọi responder**. Phải kiểm tra họ thuộc **incident team/role được phép**, đúng tenant, tài nguyên và công việc.

### Necessity test gồm ba câu hỏi

1. **Có nhu cầu ứng cứu thực?** Xác minh tác động và mục tiêu rõ, không chỉ một cảnh báo tự động chưa kiểm chứng.
2. **Đường thường lệ có đáp ứng kịp và an toàn?** Nếu còn đường JIT, backup operator hoặc delegated approver hợp lệ, cần cân nhắc trước.
3. **Có đường ít đặc quyền hơn không?** Một API restart service được kiểm soát có thể phù hợp hơn mở quyền GlobalAdmin.

**Tính cần thiết** nên được ghi thành lý do gắn với incident, không chỉ checkbox không có chứng cứ.

### Emergency activation khác emergency change

Một sự cố có thể cần **thay đổi cấu hình khẩn cấp** nhưng người thực hiện vẫn đăng nhập qua normal PAM. Trong trường hợp đó, **emergency change approval** có thể xảy ra mà không cần kích hoạt break-glass account.

Ngược lại, **IdP outage** có thể cần emergency login để sửa trust nhưng không có lý do cho phép người đó triển khai một thay đổi production không liên quan. Cần phân biệt **quyền vào hệ thống** với **quyền thực hiện thay đổi cụ thể**.

## 7. Eligibility: ai được phép kích hoạt?

Một responder cần **danh tính đáng tin và thẩm quyền hiện hành**. Một số hệ thống thiết kế emergency accounts cho danh sách nhỏ các nhân sự được chỉ định từ trước; những hệ thống khác kích hoạt role qua PAM/PIM khi đáp ứng policy.

### Thuộc tính eligibility đề xuất

| Thuộc tính | Nguồn có thẩm quyền | Lý do |
| --- | --- | --- |
| identityId / principalId | IAM identity registry hoặc workload registry. | Tránh nhầm người hoặc service. |
| lifecycleStatus | HR/nguồn hợp đồng và IAM. | Không cấp quyền cho Leaver/Suspended trái policy. |
| emergency responder assignment | Incident response roster có owner. | Chứng minh người đó thuộc nhóm ứng cứu được giao. |
| resource/tenant authority | Resource owner, platform owner, security policy. | Không dùng role ở tenant này mở tài nguyên tenant khác. |
| approved emergency capability | PAP/IGA/PAM policy, đã được phê duyệt. | Chỉ hành động đã chuẩn bị cho tình huống đó. |
| credential/custody eligibility | Vault hoặc cơ chế bảo quản độc lập. | Không để bất kỳ User nào lấy emergency secret. |
| current incident relation | Incident commander hoặc runbook có thẩm quyền. | Gắn người dùng với một vụ việc thực tế. |
| authentication assurance | IdP hoặc đường recovery độc lập được phê duyệt. | Bảo vệ việc xác minh chủ thể trong hoàn cảnh outage. |
| last review/expiry | IAM/IGA, owner registry. | Loại bỏ người được chỉ định từ lâu nhưng không còn nhiệm vụ. |

### Kiểm tra theo identity, không theo account name

~~~text
HR identity         : HRIS:EMP-2041
IAM identity        : IAM:ID-2041
Normal IdP account  : issuer-a/sub-88
Privileged login    : cloud-tenant-b/admin-2041
Emergency custody   : escrow-authorized/ID-2041
~~~

Các định danh là các **namespace khác nhau**. Phải có account correlation đáng tin; một email hoặc username đơn lẻ không đủ để suy ra một người được phép truy cập mọi emergency account.

### Separation of Duties khi kích hoạt

Với quyền nhạy cảm, tổ chức có thể yêu cầu **hai người độc lập**: người đề nghị/kích hoạt và người xác nhận; hoặc dual custody của credential. Tuy nhiên phương án phải thực tế trong khi IdP/PAM bị lỗi.

- Một người dùng hai admin account **không phải hai người độc lập**.
- Approver đã Leaver, mất ownership hoặc không còn authority không được tính là phiếu hợp lệ.
- Dual control có thể thực hiện thông qua kênh/thiết bị dự phòng nếu hệ thống approval chính là thành phần bị lỗi.
- Nếu nguy cơ cần hành động tức thời và không thể chờ duyệt trực tuyến, phải có **preapproved emergency procedure** cụ thể và kiểm soát bù/hậu kiểm đã được phê duyệt trước.

**Không dùng quy tắc “nếu không ai phản hồi, requester tự approve”** cho đặc quyền khẩn cấp.

## 8. Scope điều kiện kích hoạt: tối thiểu về resource, action và thời gian

Một quyết định emergency không nên được biểu diễn bằng cờ `emergency=true` rồi mở toàn hệ thống. Cần định nghĩa **scope ràng buộc**.

| Chiều scope | Ví dụ | Kiểm soát |
| --- | --- | --- |
| **Tenant/organization** | tenant-b | Không tự suy ra tenant-a. |
| **Environment** | production/payment | Staging grant không tự dùng ở production. |
| **Resource** | service payment-gateway-01 | Không cấp toàn cluster nếu chỉ cần service. |
| **Action** | config.read, service.restart | Không tự thêm iam.policy.write, secret.export. |
| **Data sensitivity** | Chỉ metadata, không raw PII | Giới hạn dữ liệu có thể đọc/export. |
| **Session** | Một phiên ứng cứu định danh | Không để credential được dùng nhiều nơi không kiểm soát. |
| **Time window** | 30 phút, có giới hạn gia hạn | Không auto-extend vô hạn. |
| **Network/device** | Đường admin/thiết bị đáp ứng emergency profile | Không mở từ máy bị nghi compromise. |
| **Maximum privilege** | ServiceOperator scoped | Không tự tăng lên GlobalAdmin. |
| **Incident binding** | INC-2026-411 | Không dùng cho việc không liên quan sự cố. |

### Quyền được duyệt là giao của nhiều giới hạn

~~~text
effectiveEmergencyScope =
    intersection(
        incidentRequiredActions,
        actorEmergencyAuthority,
        resourceOwnerAllowedScope,
        emergencyPolicyMaxScope,
        targetAvailableEnforcement
    )

activationEndAt =
    min(
        incidentApprovedWindowEnd,
        credentialOrRoleExpiration,
        emergencyPolicyMaxDuration,
        anyCurrentIdentityContractBoundary
    )
~~~

Đây là cách tư duy; không phải mọi nền tảng hỗ trợ phép giao role tự động. Nếu target chỉ có role admin toàn quyền, cần nhận diện **scope thực tế rộng hơn mong muốn**, đánh giá rủi ro, áp kiểm soát bù và ghi rõ giới hạn thay vì tuyên bố least privilege giả.

### Gia hạn quyền khẩn cấp

Nếu hết hạn nhưng incident chưa đóng, **không tự kéo dài vô hạn**. Gia hạn nên:

1. Xác minh incident vẫn cần xử lý.
2. Kiểm tra responder vẫn eligible và không bị JML thay đổi.
3. Reassess actions/resources, thu hẹp quyền khi có thể.
4. Có authority hợp lệ theo policy gia hạn.
5. Phát token/session/credential mới theo khả năng, ghi audit và thời hạn mới.

## 9. Bằng chứng và căn cứ trước kích hoạt

Các hệ thống khẩn cấp phải cân bằng hai yêu cầu: **đủ bằng chứng** và **không phụ thuộc duy nhất vào hệ thống đang lỗi**.

### Emergency activation record tối thiểu

| Trường | Nội dung |
| --- | --- |
| activationId / correlationId | Định danh duy nhất cho lần kích hoạt. |
| incidentId / incidentSource | Vụ việc và nguồn xác minh (online/offline). |
| severity / impact | Mức ảnh hưởng và lý do cần khẩn cấp. |
| normalPathFailureEvidence | Bằng chứng đường bình thường không đáp ứng. |
| necessityJustification | Vì sao không dùng đường ít quyền hơn. |
| responder identityId | Người/workload được chỉ định. |
| authority/approval reference | Căn cứ và cơ chế ra quyết định. |
| requested action/resource/tenant | Chính xác phạm vi. |
| startAt/endAt | Cửa sổ và thời điểm bắt buộc kết thúc. |
| authentication/custody control | Loại xác minh và bảo quản credential. |
| session/credential reference | Tham chiếu, **không ghi secret**. |
| expected audit channel | Nơi giám sát và cơ chế bù nếu mất hệ thống log. |
| exit/verification owner | Ai đóng và xác minh quyền đã bị thu hồi. |

### Mẫu record JSON

~~~json
{
  "activationId": "EA-2026-0042",
  "incidentId": "INC-2026-0411",
  "incidentType": "IDENTITY_PROVIDER_OUTAGE",
  "severity": "CRITICAL",
  "necessity": "RESTORE_IDENTITY_TRUST_CONFIGURATION",
  "normalPathStatus": "UNAVAILABLE_CONFIRMED",
  "actorIdentityId": "IAM:ID-2041",
  "emergencyAuthorityRef": "RECOVERY-RESPONDER-TENANT-B",
  "target": "IdentityPlatform:tenant-b",
  "allowedActions": ["trust.read", "trust.restore"],
  "requestedAt": "2026-12-01T09:00:00+07:00",
  "expiresAt": "2026-12-01T09:30:00+07:00",
  "approvalMode": "PREAPPROVED_OFFLINE_DUAL_CONTROL",
  "status": "REQUESTED"
}
~~~

Đây là **schema minh họa**, không phải định dạng chuẩn OAuth/OIDC/SCIM hay sản phẩm PAM. Trong sự cố không có ticketing, record có thể được tạo qua **kênh dự phòng đã được phê duyệt**, đồng bộ sau sự cố mà giữ nguyên dấu thời gian và nguồn.

### Không đòi chứng cứ bất khả thi

Nếu IdP outage làm mất quyền truy cập ticketing thì policy không nên buộc mọi activation chỉ được xác nhận **qua chính ticketing dựa trên IdP**. Thay vào đó, thiết kế evidence theo **degraded-mode**: incident log/kênh liên lạc đã kiểm soát, danh sách responder offline được ký trước, authority đã chuẩn bị, hậu kiểm bắt buộc.

**Degraded-mode không đồng nghĩa không cần bằng chứng**. Nó là một cơ chế chứng thực thay thế có giới hạn và nguồn độc lập.

## 10. Dependency failure: bảo đảm đường cứu hộ thực sự độc lập

Một đường emergency hoạt động được khi đường thường lệ lỗi **phải loại bỏ được phụ thuộc chung có thể làm tê liệt cả hai**.

### Sơ đồ lỗi phụ thuộc

~~~mermaid
flowchart TD
    I["Admin thông thường"] --> S["SSO / IdP"]
    S --> M["MFA dựa trên IdP"]
    M --> P["PAM/PIM activation"]
    P --> T["Target resource"]
    E["Emergency responder"] --> C["Preauthorized custody<br/>và identity verification"]
    C --> B["Independent emergency path"]
    B --> T
    X["Incident control / audit"] -.-> C
    X -.-> B
    X -.-> T
~~~

Sơ đồ chỉ là **mô hình logic**; “independent” không đương nhiên nghĩa là account không có MFA. Nó nghĩa là các **phụ thuộc có thể lỗi đồng thời** được hiểu và kiểm soát. Ví dụ, nếu IdP là thành phần bị lỗi, một MFA flow chỉ hoạt động sau SSO của chính IdP đó sẽ không giúp khôi phục.

### Bảng phân tích phụ thuộc

| Dependency đang lỗi | Nếu emergency path cũng phụ thuộc | Rủi ro | Lựa chọn thiết kế |
| --- | --- | --- | --- |
| IdP chính | Emergency account đăng nhập bắt buộc qua cùng IdP | Lockout. | Đường xác thực dự phòng/local theo khả năng nền tảng, có custody mạnh. |
| PAM chính | Lấy emergency secret chỉ từ vault đang lỗi | Không checkout được credential. | Cơ chế escrow/custody được phê duyệt, bảo vệ và kiểm thử độc lập. |
| Primary network | Chỉ có một VPN qua vùng hỏng | Không tới được target. | Mạng/đường khôi phục thay thế trong threat model. |
| Ticket/approval app | Cần ticket online trước emergency login | Không thể tạo chứng cứ đúng lúc. | Incident record và authority qua kênh dự phòng có thể audit. |
| Central logging | Chỉ một logging pipeline bị lỗi | Thiếu quan sát hoặc giám sát. | Local/alternate protected logs và reconciliation sau phục hồi. |
| Primary MFA device | Chỉ một authenticator duy nhất | Người được chỉ định không đăng nhập được. | Backup authenticator/recovery profile an toàn đã được duyệt. |

### Không “chữa” outage bằng việc mở đường không kiểm soát

Những phương án như **tắt toàn bộ xác thực, chia sẻ root password trong chat, vô hiệu logging, cấp GlobalAdmin vô thời hạn** có thể phục hồi nhanh một chức năng nhưng tạo rủi ro không chấp nhận được. Đường dự phòng nên **được chuẩn bị và thử nghiệm trước**, không sáng tạo trong lúc sự cố.

## 11. Authentication và custody: cách xác minh người kích hoạt

Một đường emergency cần vừa **sẵn sàng** vừa **đủ tin cậy về danh tính**. Với thao tác đặc quyền trọng yếu, nên ưu tiên xác thực chống phishing hoặc các kiểm soát tương đương phù hợp nền tảng và dependency được dự liệu.

### Các tình huống đặc thù

- **IdP hoạt động, PAM gặp lỗi:** có thể vẫn dùng IdP/phishing-resistant MFA để xác minh nhưng cần đường session/credential dự phòng nếu được phê duyệt.
- **IdP lỗi:** có thể cần đường đăng nhập độc lập được chuẩn bị; không thể yêu cầu một bước xác thực hoàn toàn phụ thuộc IdP đang lỗi.
- **MFA device thất lạc:** emergency recovery phải dựa trên proofing/dual control đã định, không dựa vào việc helpdesk tin một cuộc gọi không xác minh.
- **Nghi account compromise:** không nên tin phiên hoặc recovery channel đang bị nghi chiếm đoạt để kích hoạt emergency.
- **Recovery credential dùng chung:** nếu không thể tránh tài khoản built-in, phải có custody, attribution theo người thực, theo dõi checkout và rotate sau dùng.

### Bảo quản credential

| Kiểm soát | Lý do |
| --- | --- |
| Giới hạn người được quyền tiếp cận | Giảm khả năng dùng emergency secret trái phép. |
| Escrow/vault/thiết bị bảo quản hợp lệ | Tránh secret nằm trong chat/wiki/source code. |
| Dual custody khi rủi ro yêu cầu | Ngăn một người tự ý lấy và sử dụng. |
| Định danh người thực khi sử dụng account chung | Có bằng chứng ai vận hành. |
| Không log password, key, seed MFA | Tránh chính hệ thống audit thành nguồn rò rỉ. |
| Rotation/reseal sau sử dụng theo policy | Giảm khả năng credential đã phơi lộ còn được dùng lại. |
| Backup và diễn tập | Không để phụ thuộc đơn điểm không được phát hiện. |

**Account có MFA mạnh không tự có authority emergency.** Authentication chỉ trả lời **ai đang đăng nhập**; activation cần trả lời **có được sử dụng quyền đó cho incident và resource này không**.

## 12. SoD, multi-party authorization và điều kiện thay thế

Emergency thường tạo áp lực bỏ bước duyệt. Tuy nhiên SoD vẫn quan trọng khi một người có thể **tự tạo sự cố, tự cấp quyền và tự xóa chứng cứ**.

### Các lựa chọn kiểm soát

1. **Preapproved responder roster + dual custody:** hai người có nhiệm vụ khác nhau cùng mở khóa/tiếp cận credential; có thể hoạt động khi approval app lỗi.
2. **Independent authorization:** incident commander hoặc security officer duyệt scope qua kênh đáng tin còn hoạt động.
3. **Emergency role có giới hạn:** policy đã phê duyệt sẵn việc dùng một số action mà không cần approval trực tuyến từng lần, đổi lại alert và hậu kiểm.
4. **Segregation of action:** người thao tác không đồng thời được sửa/xóa audit logs hoặc tự hợp thức hóa giao dịch nhạy cảm.
5. **Compensating review:** kiểm tra độc lập sau khi thực thi, đối chiếu session/command/target changes.

### Không có một quy tắc hai người cho mọi loại emergency

Trong tình huống cứu hộ đặc biệt khẩn cấp, yêu cầu liên lạc trực tuyến với hai approver có thể làm mất khả năng phục hồi. Tổ chức cần **phân cấp trước**:

| Tình huống | Hướng kiểm soát minh họa |
| --- | --- |
| Hệ thống workflow vẫn hoạt động, có thời gian xác nhận | Độc lập phê duyệt trước dùng quyền. |
| Workflow lỗi, còn kênh liên lạc dự phòng | Preapproval policy + dual control qua kênh dự phòng. |
| Sự cố nghiêm trọng không có kênh online | Cơ chế custody và emergency runbook được ký duyệt từ trước, alert/local audit khi có thể, hậu kiểm bắt buộc. |
| Sự cố không cấp thiết, thiếu approver | Không mở emergency; dùng escalation hợp lệ. |

Điều kiện cụ thể phải dựa trên **risk acceptance của tổ chức**. Không được để một fallback tự do cho requester tự quyết mọi quyền nhạy cảm.

## 13. Điều kiện kích hoạt dưới RBAC, ABAC và PBAC

RBAC cho biết **ai có vai trò emergency responder**. ABAC thêm **tài nguyên, môi trường, thời điểm và tín hiệu sự cố**. PBAC giúp quản trị và kết hợp những quy tắc thành quyết định rõ ràng.

### Policy minh họa

~~~text
PERMIT emergency.trust.restore KHI
    subject.lifecycleStatus == ACTIVE
    AND subject.hasApprovedRole("IdentityRecoveryResponder")
    AND incident.status == CONFIRMED_ACTIVE
    AND incident.type == IDENTITY_PLATFORM_OUTAGE
    AND incident.severity meets emergencyPolicyThreshold
    AND incident.normalRecoveryPath == UNAVAILABLE
    AND subject.assignedToIncident(incident.id)
    AND target.tenantId in subject.emergencyApprovedTenants
    AND requestedAction in policy.allowedRecoveryActions
    AND now within policy.activationWindow
    AND requiredCustodyOrApprovalSatisfied
    AND trustedEmergencyAuthenticationSatisfied
    AND NOT anyMandatoryVeto

ELSE: NO_PERMIT
~~~

Đây là **pseudo-policy**, không phải ngữ pháp sản phẩm. Trong mode offline, một số thuộc tính phải được phát hành/xác minh từ trước hoặc bởi kênh dự phòng. **Không dùng claim incident/severity do client tự truyền** làm nguồn có thẩm quyền.

### Hard guards cần thiết

~~~text
DENY emergency.* nếu actor không được định danh đáng tin
DENY emergency.* nếu actor đã Leaver/không còn eligible theo policy
DENY emergency.* nếu resource ngoài tenant/environment được cho phép
DENY emergency.* nếu activation hết hạn hoặc đã bị revoke
DENY emergency.* nếu credential/session bị xác định compromise
DENY action ngoài recovery scope đã phê duyệt
~~~

Cách enforcement phụ thuộc kiến trúc. Với account offline có quyền kỹ thuật rất rộng, một số guard **không thể cưỡng chế tự động tại mọi action**; phải công bố rủi ro còn lại và áp **custody, procedure, monitoring, hậu kiểm**. Không ghi “Deny được bảo đảm” nếu PEP thực tế không có khả năng kiểm điều kiện.

### Đánh giá đủ dữ liệu

| Kết quả | Ý nghĩa | Hành vi phù hợp |
| --- | --- | --- |
| **Permit** | Đủ điều kiện theo policy có thể thực thi. | Chỉ dùng đúng scope, thời hạn và nghĩa vụ. |
| **Deny** | Có guard cấm hoặc điều kiện không đạt. | Chặn truy cập. |
| **NotApplicable** | Không thuộc phạm vi chính sách đang xét. | Không tự mở quyền; default deny/route khác đã duyệt. |
| **Indeterminate** | Không đánh giá được vì lỗi hoặc thiếu thuộc tính. | Không tự Permit; dùng recovery path có thẩm quyền nếu được định nghĩa trước. |

Tên trạng thái gắn với các mô hình policy như XACML, không nhất thiết là API của mọi hệ thống. Quan trọng nhất là không biến **lỗi nguồn dữ liệu** thành **bằng chứng cho phép đặc quyền**.

## 14. State machine kích hoạt Emergency access

Một state machine giúp phân biệt **được xét, được chấp thuận, thực sự kích hoạt, đang sử dụng và đã kết thúc**.

~~~mermaid
stateDiagram-v2
    [*] --> DETECTED
    DETECTED --> TRIAGED: Xác minh incident và tác động
    TRIAGED --> REJECTED: Không đủ trigger/necessity
    TRIAGED --> ELIGIBILITY_CHECKED: Có nhu cầu theo policy
    ELIGIBILITY_CHECKED --> REJECTED: Không đủ identity/authority/SoD
    ELIGIBILITY_CHECKED --> AUTHORIZED: Scope, custody, approval đạt
    AUTHORIZED --> ACTIVATING: Cấp session/credential/quyền
    ACTIVATING --> ACTIVE: Target xác nhận đường truy cập
    ACTIVATING --> FAILED: Không thể kích hoạt an toàn
    ACTIVE --> CLOSING: Hết hạn/incident đóng/revocation
    ACTIVE --> CLOSING: Nghi lạm dụng/compromise
    CLOSING --> REVOKE_PENDING: Thu hồi role/session/credential
    REVOKE_PENDING --> VERIFIED_CLOSED: Readback + xác minh boundary
    REVOKE_PENDING --> PARTIAL_FAILURE: Còn đường truy cập chưa xử lý
    PARTIAL_FAILURE --> REVOKE_PENDING: Retry/containment
    VERIFIED_CLOSED --> POST_REVIEWED: Hậu kiểm và remediation
    POST_REVIEWED --> [*]
    REJECTED --> [*]
    FAILED --> [*]
~~~

Các trạng thái là **mô hình tham khảo**, không phải enum chuẩn. Một emergency account có thể tồn tại và có quyền trước trạng thái ACTIVE do giới hạn nền tảng; khi đó phải theo dõi **thời điểm sử dụng thực tế** bên cạnh trạng thái workflow.

### Quy tắc chuyển trạng thái

| Chuyển | Tiền điều kiện | Hành vi khi thất bại |
| --- | --- | --- |
| DETECTED → TRIAGED | Incident nhận diện và nguồn đáng tin. | Chưa được cấp quyền. |
| TRIAGED → ELIGIBILITY_CHECKED | Đạt trigger + necessity; xác định resource và nhiệm vụ. | REJECTED hoặc chờ đánh giá. |
| ELIGIBILITY_CHECKED → AUTHORIZED | Identity, authority, SoD và custody đạt. | REJECTED/REVIEW. |
| AUTHORIZED → ACTIVE | Đường credential/session/role đúng, đủ tin cậy. | FAILED, không coi “đã xin” là “đang có quyền”. |
| ACTIVE → CLOSING | EndAt, incident kết thúc, owner revoke hoặc tín hiệu compromise. | Bắt đầu thu hồi ngay theo policy. |
| REVOKE_PENDING → VERIFIED_CLOSED | Kiểm chứng effective access không còn trong scope. | PARTIAL_FAILURE, tiếp tục containment. |

**Đừng để ACTIVE là trạng thái không có điểm thoát.** Mọi activation phải biết **deadline, người đóng, ràng buộc điều kiện dừng và cách xác minh** ngay từ lúc tạo.

## 15. Luồng kích hoạt end-to-end: từ sự cố tới phiên có quyền

Điều kiện được mô tả trong policy chỉ hữu ích nếu **từng hệ thống** thực hiện đúng trách nhiệm. Luồng sau giả định vẫn có một kênh ứng cứu được tin cậy; khi một thành phần bị lỗi, tổ chức có thể dùng **đường thay thế được chuẩn bị trước**, không bỏ qua bước xác minh người dùng hoặc quyền.

~~~mermaid
sequenceDiagram
    actor R as Responder
    participant IR as Incident Coordinator
    participant IAM as IAM / Emergency Policy
    participant C as Custody / Alternate Channel
    participant T as Target PEP / Platform
    participant A as Audit / Verification
    R->>IR: Báo incident, tác động, hành động cần thiết
    IR->>IR: Xác minh severity, necessity, ownership
    IR-->>IAM: Incident authority, scope, window
    IAM->>IAM: Eligibility, JML, SoD, emergency policy
    alt Path tự động còn hoạt động
        IAM->>T: Activate scoped emergency role/session
    else Primary IdP/PAM không khả dụng
        IAM-->>C: Áp preapproved offline policy
        C->>C: Identity proofing + custody/dual control
        C->>T: Dùng emergency login/credential được bảo vệ
    end
    T-->>R: Phiên/truy cập được giới hạn theo khả năng
    R->>T: Thao tác phục hồi có căn cứ
    T-->>A: Audit/alternate protected evidence
    IR->>IAM: Incident resolved hoặc endAt đến
    IAM->>T: Close/revoke quyền, phiên, credential
    T-->>A: Target readback + effective access verification
    A-->>IR: VERIFIED / PARTIAL_FAILURE + post-review
~~~

### Điểm kiểm soát tại từng chặng

| Giai đoạn | Điều kiện bắt buộc | Dấu hiệu cần điều tra |
| --- | --- | --- |
| **Incident triage** | Xác minh nguồn tin, ảnh hưởng và necessity. | Activation chỉ vì requester nói “gấp” mà không có bằng chứng. |
| **Authorization** | Responder còn authority, đúng resource, phạm vi và cửa sổ. | Một người tự cấp mọi tenant hoặc làm vượt incident. |
| **Credential/session establishment** | Kênh xác thực và custody được chuẩn bị cho loại outage. | Secret bị gửi trong chat hoặc dùng account không owner. |
| **Execution** | Action giới hạn, có giám sát và transaction guard khi cần. | Tắt logging, tạo tài khoản ẩn, mở privilege vô hạn. |
| **Termination** | Incident đóng/hết hạn/revoke → kích hoạt thu hồi. | Không có owner đóng phiên hoặc gia hạn im lặng. |
| **Verification** | Đọc lại grants, phiên/token và kết quả resource theo scope. | Báo xong chỉ vì connector trả thành công. |
| **Post-review** | So sánh action đã làm với mục tiêu, lý do, bằng chứng. | Không có audit hoặc evidence bị người thao tác tự xóa. |

### Hành vi sau khi activation thành công

**Kích hoạt xong không có nghĩa được làm bất kỳ thao tác nào.** Với một phiên phục hồi, API hoặc thiết bị đích vẫn cần cưỡng chế action và resource policy khi kiến trúc hỗ trợ. Nếu đường khẩn cấp là built-in admin toàn quyền không có PEP chi tiết, phải áp **giám sát thao tác, quy trình cụ thể và kiểm soát bù**; không giả định scope tự động được giới hạn.

## 16. Ma trận quyết định kích hoạt theo nguyên nhân và giới hạn

| Tình huống | Trigger được xác minh? | Necessity? | Scope hợp lý | Quyết định minh họa |
| --- | --- | --- | --- | --- |
| IdP down, cần phục hồi federation để hệ thống hoạt động | Có | Có, không còn normal path | Sửa trust/cấu hình IdP liên quan | Có thể ACTIVATE với responder đủ điều kiện. |
| PAM down, hệ thống production khỏe và không cần sửa ngay | Có outage PAM | Không chứng minh được | Không có action khẩn cấp | Không ACTIVATE. |
| Incident cloud compromise, cần revoke malicious keys | Có từ kênh ứng cứu | Có | Khóa identity/trust bị ảnh hưởng, tài nguyên cụ thể | Có thể ACTIVATE qua kênh/thiết bị tin cậy. |
| Công việc deploy thường lệ bị chậm do chờ approval | Không | Không | Có thể deploy nhưng không khẩn cấp | Không ACTIVATE; escalation bình thường. |
| Nhân viên bị TERMINATED biết secret dự phòng | Có thể có outage | Không đủ eligibility | Bất kỳ quyền nào | DENY theo policy và rotate/contain credential. |
| Responder hợp lệ nhưng xin GlobalAdmin cho sự cố một namespace | Có | Có | Namespace/operator là đủ nếu target hỗ trợ | Giảm scope hoặc yêu cầu đánh giá rủi ro nâng cấp. |
| Incident đã kết thúc nhưng session còn mở | Trigger lịch sử có | Không còn | Không còn hành động ứng cứu | TERMINATE/REVOKE. |
| Diễn tập approved trên tài nguyên sandbox | Test mode có | Có theo mục tiêu diễn tập | Sandbox/no destructive actions | ACTIVATE chỉ theo runbook diễn tập. |
| System offline và không đọc được incident register online | Có bằng chứng qua channel dự phòng | Cần xét | Chỉ route offline đã chuẩn bị | Có thể theo preapproval/custody, không tự Permit. |
| Responder bị nghi session hijack | Có incident | Có nhu cầu bảo vệ | Không dùng session bị nghi compromise | REJECT compromised session; dùng kênh identity thay thế. |

**Bảng không thay thế chính sách của tổ chức.** Trong cùng một mức severity, một loại target có thể có emergency operation rất hẹp, còn target khác chỉ hỗ trợ admin toàn quyền; risk decision phải phản ánh **quyền kỹ thuật thực tế**.

### “Manual override” vẫn phải có owner

Đôi khi incident coordinator phải cấp quyền mà policy tự động không thể đánh giá vì mất nguồn. Một **manual emergency decision** cần:

1. Authority và trigger type được phê duyệt từ trước.
2. Bằng chứng actor, nguồn sự cố và necessity qua kênh tin cậy.
3. Phạm vi tối thiểu và thời hạn cụ thể.
4. Log quyết định và người thực hiện, kể cả offline.
5. Sau phục hồi, đối soát policy, session, grant và kiểm toán.

Một quyết định ngoài luồng không được biến thành **đặc quyền mới vĩnh viễn**.

## 17. Joiner: điều kiện trở thành người có thể kích hoạt Emergency access

Một **Joiner** mới được tuyển vào đội vận hành không nên tự nhiên có break-glass credential chỉ vì được thêm vào Group Operations.

### Điều kiện onboarding cho emergency responder

- Identity proofing và account linking hoàn tất.
- Trạng thái HR/contract đủ điều kiện theo startAt; không kích hoạt trước ngày hiệu lực trừ khi chính sách có ngoại lệ rõ cho onboarding.
- Có **chức trách incident responder** được giao và tài nguyên mà người đó được phép phục hồi.
- Chứng minh đào tạo/diễn tập cần thiết theo chính sách trước khi tiếp cận credential.
- Resource/security owner chấp thuận eligibility, không chỉ manager tổng quát.
- Enrollment phương thức xác thực, thiết bị quản trị hoặc custody dự phòng đúng chuẩn bị.
- Không có SoD conflict không được giải quyết.
- Bằng chứng và phạm vi được ghi vào **emergency roster/authority registry**.

### Ví dụ pre-provisioning

~~~text
Joiner identity created: 2026-11-27
HR startAt:             2026-12-01 09:00 +07:00
Responder roster:       preapproved, activation not before startAt
Emergency credential:   sealed and not yet released to joiner

Result before startAt:
    cannot activate emergency privilege

Result after startAt:
    still needs valid incident trigger + necessity + scope/controls
~~~

**Eligibility đã được đăng ký không tương đương một emergency session tự động.** Ngay cả sau ngày bắt đầu, một responder chỉ được sử dụng đường khẩn cấp khi chính sách kích hoạt thực sự đạt.

### Nếu Joiner bị hủy

Khi HR hủy tuyển dụng hoặc dời startAt:

1. Cập nhật roster/authority theo sự kiện có nguồn tin cậy.
2. Gỡ eligibility/đóng đường custody được cấp sớm.
3. Chặn các job onboarding cũ phát session/role.
4. Kiểm tra account đích không được sử dụng trước thời điểm hợp lệ.
5. Giữ audit về quyết định đã phê duyệt trước đó nhưng không tự dùng làm căn cứ kích hoạt.

## 18. Mover: khi người ứng cứu đổi vai trò hoặc phạm vi trách nhiệm

**Mover** có thể làm thay đổi cả **quyền nghiệp vụ, scope tài nguyên, responder roster, manager, approver và khả năng tiếp cận credential**. Nguy cơ là một người giữ cả quyền ứng cứu cũ và quyền mới, hoặc vẫn có emergency secret dù không còn phục trách nhiệm đó.

### Tình huống chuyển vai trò

Lan chuyển từ IdentityOps sang FinanceOps:

| Quyền/đường truy cập | Trước Mover | Sau Mover mong muốn |
| --- | --- | --- |
| Identity emergency responder eligibility | Được phép phục hồi IdP tenant B | Thu hồi nếu không còn trách nhiệm. |
| Finance application role | Không có | Cấp theo công việc Finance, approval riêng. |
| Emergency credential custody | Được quyền checkout/tiếp cận | Gỡ custody; xét reseal/rotation nếu đã biết secret. |
| PAM privileged activation | Eligible IdentityRecoveryAdmin | Thu hồi eligibility và các active grants tương ứng. |
| Old cloud token/session | Có thể còn hạn | Chặn trong boundary chính sách. |
| Incident task đang mở | Assigned cho Lan | Chuyển cho responder mới đủ thẩm quyền. |

### Phải rà soát hai loại “authority”

1. **Access authority:** quyền dùng tài nguyên khi đã kích hoạt.
2. **Activation authority:** quyền quyết định/mở một emergency path khi incident xảy ra.

Một Mover có thể đã mất quyền admin trực tiếp nhưng vẫn còn **được phép mở vault emergency secret**. Đây là quyền tồn dư nguy hiểm vì chỉ cần một sự cố giả hoặc lỗi kiểm soát là có thể kích hoạt lại admin.

### Phát hiện xung đột SoD khi Mover

Một người giữ **authority kích hoạt emergency admin** và đồng thời có quyền **tự thay đổi incident evidence/approval policy** có thể tạo đường lạm dụng. Cần phân tích **toxic combinations**, đặc biệt:

- Tự khai báo incident và tự phê duyệt escalation.
- Tự lấy credential và tự xóa audit logs.
- Quyền sửa danh sách responder và tự thêm mình.
- Quyền thay policy guard và quyền triển khai production.

**Không giữ eligibility cũ chỉ vì “chưa cần sử dụng”.** Điều kiện kích hoạt là một quyền tiềm tàng, phải được rà soát như entitlement có rủi ro cao.

## 19. Leaver, suspension, rehire và contractor: điều kiện phủ quyết

### Leaver

Khi một responder rời tổ chức:

1. HR/nguồn hợp đồng phát **Leaver** có effectiveAt và sourceVersion đáng tin.
2. IAM thu hồi responder assignment, emergency eligibility và quyền truy cập vault/custody.
3. IdP/SSO và SCIM/API/PAM xử lý account, Group, roles, activation và sessions theo scope.
4. Đánh giá emergency credential/secret mà người đó từng biết: rotate, reseal hoặc thay đường bảo vệ theo chính sách.
5. Tìm active emergency sessions, tokens, SSH keys, local emergency accounts hoặc vendor credential ngoài IdP.
6. Chuyển ownership của incident/playbook/tài nguyên cho người hiện hành.
7. **Readback và xác minh quyền hiệu lực** theo boundary đã định.

**Leaver override các approval/activation lịch sử** khi chính sách cấm người đã nghỉ sử dụng tài nguyên. Nếu một phiên/credential vẫn khả dụng do target không hỗ trợ thu hồi ngay, đó là **residual access** cần nhận diện và xử lý, không báo xong chỉ vì roster đã gỡ.

### Suspension

Trạng thái **SUSPENDED** thường phải dẫn tới **khóa hoặc hạn chế emergency eligibility** theo policy, dù một account có thể được giữ lại phục vụ điều tra. Ngoại lệ phục hồi do chính người đang bị đình chỉ sử dụng là kịch bản rủi ro cao, không được mặc định cho phép.

### Rehire

Khi nhân viên quay lại, không tự khôi phục quyền dùng emergency credential, responder role, approval hoặc exception từ lần làm việc trước. Phải xác minh identity đúng, vai trò mới và cấp lại eligibility theo quy trình hiện hành.

### Contractor/vendor

Với đối tác được quyền phục hồi sản phẩm:

| Điều kiện | Kiểm tra cần thiết |
| --- | --- |
| Internal sponsor | Có owner nội bộ chịu trách nhiệm. |
| Contract status/endAt | Quan hệ còn hiệu lực và cửa sổ truy cập không vượt hạn. |
| Tenant/resource scope | Chỉ các hệ thống được hợp đồng/ủy quyền cho phép. |
| Named identity | Có thể quy hành động về đúng người, không chia sẻ password bừa bãi. |
| Emergency purpose | Sự cố thực sự liên quan hệ thống vendor hỗ trợ. |
| Strong authentication/custody | Phù hợp với rủi ro và dependency. |
| Monitoring and termination | Có audit, session control và thu hồi hợp đồng. |

Không tự cho vendor GlobalAdmin toàn tổ chức khi chỉ cần phục hồi một dịch vụ có phạm vi hỗ trợ xác định.

## 20. Emergency access cho service account và workload identities

Không phải mọi hoạt động khẩn cấp do người tương tác trực tiếp. Một hệ thống có thể dùng **backup recovery service, disaster recovery automation, control-plane agent hoặc recovery pipeline** được kích hoạt trong incident.

### Khác biệt với responder con người

| Khía cạnh | Human emergency responder | Emergency workload |
| --- | --- | --- |
| Identity | IAM person và các account liên kết. | Workload/service principal có namespace riêng. |
| Authority | Roster, resource ownership, incident role. | Service owner, platform owner, workflow policy. |
| Authentication | MFA/passkey/credential custody theo target. | Workload federation, mTLS, short-lived credentials. |
| Trigger | Incident commander và nhu cầu ứng cứu. | Event/controller có nguồn đáng tin và gating. |
| Scope | Resource/action/tenant theo thao tác con người. | API audience, workload identity, environment, resource. |
| Termination | Revoke session, role và credential. | Stop job, revoke trust/role/token, rotate secrets nếu cần. |
| Audit | Người thực và account dùng. | Workload ID, source pipeline, service owner, initiating human. |

### Những điều kiện cần thêm cho automation

1. Event kích hoạt đến từ **nguồn có thẩm quyền**, không chỉ webhook không xác thực.
2. Workload có **mục đích phục hồi xác định**, không dùng chung identity của deployment thường lệ khi rủi ro cao.
3. Quyền chỉ hợp lệ với environment, cluster, project và target cần khôi phục.
4. Không để chính pipeline có quyền **tự viết điều kiện incident rồi tự cấp mình admin** nếu SoD cấm.
5. Credential có audience, expiry và trust conditions phù hợp.
6. Có kiểm soát để stop/revoke khi sự cố kết thúc hoặc phát hiện hành vi bất thường.
7. Service owner và runbook vẫn hợp lệ khi nhân viên từng vận hành nó đã Leaver.

### Ví dụ

~~~text
Trigger:
    disasterRecoveryController confirms region-a unavailable

Allowed:
    workload:dr-restorer
    action: restore.snapshot
    target: production/region-b/database-payments
    maxDuration: emergencyPolicyMaxDuration
    evidence: signed event + recovery plan + service owner

Not allowed:
    iam.assignGlobalAdmin across all tenants
    indefinite reusable API key issued to any CI runner
~~~

Việc xác định **nguồn kích hoạt đáng tin** là quan trọng: nếu một workflow có thể bị gọi tùy ý để mở secret/role admin, nó trở thành một privilege escalation path.

## 21. Session, token, credential và thời điểm điều kiện hết hiệu lực

Một activation endAt là **hạn của quyết định cho phép**, nhưng không mặc định làm mất hiệu lực mọi token/session/credential đã phát, nhất là trong môi trường nhiều nhà cung cấp.

### Các cửa sổ quyền cần phân biệt

| Cửa sổ | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| **Approval/authorization window** | Chính sách cho phép activation trong khoảng thời gian. | Một worker có thể dùng quyết định quá hạn nếu không kiểm. |
| **Role/JIT activation window** | Role đặc quyền active tại nền tảng. | Có thể được gia hạn sai hoặc còn entitlement trực tiếp. |
| **Session window** | Phiên SSH/RDP/console/app còn hoạt động. | Session có thể sống lâu hơn activation. |
| **Token lifetime** | Access token/certificate còn được chấp nhận. | Self-contained token không tự bị chặn khi role bị gỡ. |
| **Credential lifetime** | Mật khẩu/key/secret còn có thể dùng để đăng nhập. | Shared/built-in secret vẫn sử dụng được sau incident. |
| **Incident validity window** | Sự cố còn được xác minh là active. | Incident đóng nhưng quyền vẫn active. |

### Kiểm soát thời gian

- **TTL ngắn theo rủi ro:** giảm thời gian quyền tồn tại, nhưng đừng khẳng định mọi target có thể ngắt session tức thời.
- **Revalidation cho action nhạy cảm:** kiểm tra lifecycle, incident và grant hiện hành khi có thể.
- **Session kill/revocation:** áp theo khả năng target; xác minh có thực sự chặn action không.
- **Credential rotation:** đặc biệt cần đánh giá khi dùng emergency secret dạng tĩnh hoặc shared/built-in.
- **Refresh token handling:** thu hồi quyền lấy token mới nhưng không mặc nhiên vô hiệu mọi access token cũ.
- **Cleanup and reconcile:** xử lý temporary role, ACL, trust, SSH key, local account và còn sót từ emergency change.

### Token cũ sau khi Incident đóng

~~~text
Incident closes:       10:20
JIT role revoked:      10:21
JWT access token exp:  10:45

Nếu Resource Server chỉ kiểm chữ ký/exp và tin role claim cũ:
    Một số action có thể vẫn Permit tới 10:45.

Nếu chính sách yêu cầu chặn ngay:
    cần revocation/introspection/authorization lookup hoặc guard
    được thực thi ở API, trong phạm vi nền tảng hỗ trợ.
~~~

**Thu hồi quyền trên một dashboard không bằng chứng thu hồi quyền hiệu lực.** Phải định nghĩa và đo **thời gian tồn dư**.

## 22. Kết thúc kích hoạt: những điều kiện dừng bắt buộc

Activation policy không hoàn chỉnh nếu chỉ định nghĩa **cách bắt đầu**.

### Các trigger kết thúc

1. Incident được coordinator/owner xác nhận **đã khắc phục** hoặc không cần emergency path.
2. **EndAt/TTL** tới hạn, bất kể incident status; nếu cần tiếp tục phải xét gia hạn riêng.
3. Người kích hoạt bị **Mover/Leaver/Suspended** hoặc mất responder assignment/authority.
4. Role, resource, tenant hoặc scope được điều chỉnh, không còn phù hợp.
5. Có dấu hiệu **credential/session bị lộ hoặc sử dụng trái phạm vi**.
6. Normal path đã phục hồi và policy đòi quay lại phương thức chuẩn.
7. Một kiểm soát bắt buộc không còn duy trì được, ví dụ thiết bị trở nên không đáng tin.
8. Owner thực hiện emergency revocation hoặc yêu cầu lockdown.

### Quy trình đóng quyền

~~~mermaid
flowchart TD
    A["Incident resolved / TTL / Revocation signal"] --> B["Stop new emergency activations"]
    B --> C["Close/revoke active role & broker session"]
    C --> D["Revoke/rotate credentials, tokens, trust<br/>according to target capabilities"]
    D --> E["Remove temporary ACL, local accounts,<br/>policy overrides, grants"]
    E --> F["Readback target + verify effective access"]
    F --> G{"Đạt revocation boundary?"}
    G -->|Có| H["VERIFIED_CLOSED"]
    G -->|Không| I["PARTIAL_FAILURE + containment<br/>owner + retry"]
    H --> J["Evidence review, credential reseal,<br/>post-incident actions"]
~~~

### Khi không thể revoke tức thời

Một số built-in accounts, offline credentials hoặc service tokens khó thu hồi ngay mà không làm gián đoạn hệ thống. Khi đó:

- Nêu rõ **đường truy cập chưa thể vô hiệu**, khả năng bị lạm dụng và thời gian còn hiệu lực.
- Dùng containment khả thi: giảm network reachability, thay credential theo lịch an toàn, chặn action tại PEP nếu có.
- Gán owner, deadline và kiểm soát bù; không đóng trạng thái VERIFIED giả.
- Đánh giá nâng cấp kiến trúc để giảm rủi ro cho lần incident sau.

## 23. Xử lý race condition và stale activation decisions

Trong hệ thống bất đồng bộ, các sự kiện HR, incident và IAM có thể đến không đúng thứ tự:

~~~text
09:00 INC-411 confirmed ACTIVE
09:01 responder Lan approved for 30-minute emergency
09:04 HR Mover event revokes Lan's responder role
09:05 old activation job retries after network timeout

Required:
    the old activation approval must not re-grant Lan emergency role
    if current lifecycle/authority no longer permits.
~~~

### Những tình huống đồng thời

| Race | Rủi ro | Biện pháp |
| --- | --- | --- |
| Incident đóng khi grant đang provision | Session mở sau khi sự cố hết. | Revalidate incident/version trước commit, compensate nếu đã cấp. |
| Actor Leaver khi token đang phát | Cấp token cho người không eligible. | JML check tại thời điểm phát và target enforcement. |
| Hai người cùng lấy một emergency shared credential | Không biết ai thực hiện thao tác, custody bị phá. | Serialized checkout/attribution; kiểm soát theo thiết kế. |
| Approver mất authority trong khi task chờ | Duyệt bởi người không còn quyền. | Revalidate identity/authority khi decision commit. |
| Bản request sửa từ namespace thành GlobalAdmin | Approval bị áp vào scope khác đã xem. | Request version/hash, reapproval. |
| Job tạo role timeout rồi retry | Cấp trùng hoặc tạo role ngoài TTL. | Idempotency key, readback, expiry guard. |
| Incident ID tái sử dụng hoặc bị replay | Reopen emergency grant không có sự cố mới. | Unique activation ID, incident binding, anti-replay. |
| Hai policy version khác nhau ở PAM/target | Quyền được dùng qua rule cũ. | Policy version audit, rollout và reconciliation. |

### Versioning không đơn thuần dùng timestamp

Một event có thể có **effectiveAt** trước **receivedAt**; HR, IAM và incident system có thể sử dụng version theo namespace khác nhau. Phải định nghĩa **authority source, event ordering và cách đánh giá khi dữ liệu xung đột**. Không tự chọn event nhận sau làm “đúng nhất” nếu nó là retry cũ.

## 24. Pseudocode: xét điều kiện kích hoạt và thu hồi

Mã giả nhấn mạnh **điều kiện nghiệp vụ và các ranh giới tin cậy**; không phải mã triển khai PAM, API SCIM hoặc một policy engine cụ thể.

### Xét yêu cầu kích hoạt

~~~text
requestEmergencyActivation(actorAuthn, incidentRef, targetRef, action):
    actor = resolveTrustedIamIdentity(actorAuthn)
    if actor unresolved or actorAuthn is untrusted:
        return BLOCK_UNVERIFIED_IDENTITY

    incident = loadVerifiedIncidentOrApprovedOfflineEvidence(incidentRef)
    target = loadTrustedTarget(targetRef)
    if incident unresolved or target unresolved:
        return BLOCK_INDETERMINATE

    if not incident.isActiveOrApprovedDrill:
        return DENY_NO_VALID_TRIGGER
    if not incident.impactMeetsActivationPolicy:
        return DENY_INSUFFICIENT_IMPACT
    if not normalPathFailureOrNecessityEstablished(incident, target):
        return DENY_NORMAL_PATH_AVAILABLE

    lifecycle = loadCurrentAuthoritativeLifecycle(actor.identityId)
    authority = loadCurrentEmergencyResponderAuthority(actor.identityId)
    if lifecycle not eligible or authority not valid:
        return DENY_NOT_ELIGIBLE
    if not authority.covers(incident.type, target, action):
        return DENY_OUT_OF_SCOPE
    if violatesMandatorySoD(actor, incident, action):
        return DENY_SOD

    controls = selectPreapprovedActivationControlProfile(
        incident.failureMode, target.riskTier
    )
    if not verifyAuthenticationCustodyAndIndependentControls(controls):
        return BLOCK_CONTROLS_NOT_SATISFIED

    grantScope = narrowestApprovedScope(actor, incident, target, action)
    grantEndAt = minimumAllowedExpiry(
        incident.endAt, authority.endAt, policy.maxDuration
    )
    if grantScope empty or grantEndAt <= now:
        return DENY_INVALID_SCOPE_OR_WINDOW

    activation = recordVersionedActivationAndIncidentBinding(
        actor.identityId,
        incident.id,
        target.id,
        grantScope,
        grantEndAt,
        authority.version,
        incident.version
    )
    return ACTIVATE_SCOPED_PATH_WITH_READBACK(activation)
~~~

### Thực thi cấp quyền sau một approval

~~~text
activateEmergencyGrant(job):
    current = loadCurrentIncidentIdentityAndAuthority(job)
    if current.versionSupersedes(job.version):
        return SUPERSEDED_NO_GRANT
    if not current.incidentActive:
        return DENY
    if not current.actorEligible:
        return DENY
    if not current.approvedScope.contains(job.requestedScope):
        return DENY
    if job.endAt <= now:
        return DENY

    result = provisionIdempotently(job)
    observed = readBackGrantAtTarget(result)

    if not observed.matchesApprovedScope:
        revokeOrContainUnexpectedGrant(result)
        return PARTIAL_FAILURE

    recordAuditWithoutSecrets(job, observed)
    return ACTIVE_VERIFIED_FOR_GRANTED_SCOPE
~~~

### Kết thúc và hậu kiểm

~~~text
closeEmergencyActivation(activationId, closureTrigger):
    activation = loadCurrentActivation(activationId)
    if activation already VERIFIED_CLOSED:
        return IDEMPOTENT_PRIOR_RESULT

    blockNewUseOfActivation(activation)
    revokeGrantsSessionsTokensAndCredentialsWhenSupported(activation)
    removeTemporaryOverridesAndTrust(activation)
    actual = readBackAllRequiredTargetPaths(activation)

    if actual.meetsRevocationBoundary:
        markVerifiedClosed(activation, actual, closureTrigger)
        scheduleIndependentPostIncidentReview(activation)
        return VERIFIED_CLOSED

    markPartialFailure(activation, actual.unverifiedPaths)
    assignContainmentOwnerAndDeadline(activation)
    return PARTIAL_FAILURE
~~~

### Một giới hạn quan trọng

Nếu toàn bộ IdP/PAM/PDP không khả dụng, không thể thực hiện `loadCurrentAuthoritativeLifecycle` theo cách trực tuyến thông thường. Khi đó **đường offline phải có danh sách eligible được chứng thực và cơ chế cập nhật/thu hồi dự phòng**. Không lặng lẽ giả lập kết quả `ACTIVE` hoặc `APPROVED` cho bất kỳ tài khoản nào.

## 25. Ma trận kiểm thử điều kiện kích hoạt Emergency access

Kiểm thử nên được thực hiện bằng **tài khoản và môi trường được phép**, theo runbook và hạn chế thao tác phá hoại. Khi diễn tập trên production phải có change/risk approval riêng.

| ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| EA-A01 | IdP outage được xác minh, recovery responder đủ quyền, scope đúng. | Kích hoạt đúng đường dự phòng và audit. |
| EA-A02 | Có outage nhưng không có hành động khẩn cấp cần thực hiện. | Không tự kích hoạt đặc quyền. |
| EA-A03 | Routine deployment chưa được duyệt, requester chọn emergency. | Bị chặn, điều hướng normal approval. |
| EA-A04 | Incident severity thấp hơn ngưỡng, không có necessity. | Deny/review theo policy. |
| EA-A05 | Incident có thật nhưng actor không thuộc responder roster. | Không cho kích hoạt. |
| EA-A06 | Responder đã TERMINATED hoặc SUSPENDED. | Không sử dụng account/role khẩn cấp đó. |
| EA-A07 | Joiner được pre-register nhưng chưa startAt. | Không kích hoạt trước ngày hiệu lực. |
| EA-A08 | Mover mất IdentityRecovery responder role. | Authority cũ không được chấp nhận; gỡ custody/JIT. |
| EA-A09 | Rehire có emergency assignment lịch sử. | Không tự phục hồi eligibility cũ. |
| EA-A10 | Contractor endAt đã qua. | Không activate dù local account còn. |
| EA-A11 | Requester xin GlobalAdmin nhưng chỉ cần service.restart. | Giảm scope hoặc chặn nâng quyền không có căn cứ. |
| EA-A12 | User có authority tenant A, yêu cầu target tenant B. | Chặn cross-tenant request. |
| EA-A13 | MFA/SSO chính lỗi, fallback lại phụ thuộc cùng IdP. | Test phát hiện đường cứu hộ không độc lập. |
| EA-A14 | Recovery credential chỉ nằm trong PAM đang lỗi. | Không tuyên bố khôi phục khả dụng; thiết kế custody dự phòng. |
| EA-A15 | Approval app không dùng được nhưng kênh offline đã chuẩn bị. | Đường offline áp đúng preapproval và lưu evidence. |
| EA-A16 | Requester vừa là approver độc lập bắt buộc qua account khác. | SoD chặn self-approval. |
| EA-A17 | Credential bị nghi lộ. | Không sử dụng credential, containment/rotation và route tin cậy khác. |
| EA-A18 | Incident đã đóng khi job activation retry. | Không cấp mới; supersede. |
| EA-A19 | JIT endAt đã hết trước khi target cấp quyền. | Không cấp quyền. |
| EA-A20 | Gia hạn emergency khi incident không còn active. | Không auto-extend; chặn/đóng. |
| EA-A21 | Gia hạn trong incident còn active nhưng actor đã Mover. | Revalidate authority; không dùng approval cũ. |
| EA-A22 | Resource Server nhận access token cũ sau revoke. | Phát hiện residual access theo boundary. |
| EA-A23 | SCIM Group gỡ thành công nhưng app-local admin còn. | Không báo VERIFIED; xử lý đường local. |
| EA-A24 | Emergency built-in account có password dùng chung không attribution. | Audit phát hiện thiếu định danh người sử dụng; yêu cầu kiểm soát bù. |
| EA-A25 | Một automation nhận webhook giả để mở secret. | Không kích hoạt; validate trigger source/trust. |
| EA-A26 | Recovery workload staging gọi production ngoài scope. | Deny theo environment/audience/trust. |
| EA-A27 | Diễn tập có preapproval trên sandbox. | Chỉ action đã định, alert, đóng và kiểm chứng. |
| EA-A28 | Diễn tập vô ý thay đổi production ngoài scope. | Test FAIL, incident/containment và hậu kiểm. |
| EA-A29 | API grant timeout sau khi đã tạo role. | Idempotent retry có readback, không duplicate grant. |
| EA-A30 | Hai worker đồng thời activate/close cùng request. | Không có quyền sống sau close; version/transaction guard. |
| EA-A31 | Central logging outage trong emergency. | Evidence dự phòng có bảo vệ, reconcile sau khi phục hồi. |
| EA-A32 | User thao tác ngoài allowed actions trong phiên emergency. | PEP chặn nếu hỗ trợ; ghi nhận guard gap/violation nếu không. |
| EA-A33 | API trả Deny nhưng thao tác admin đã có side effect. | Test FAIL, sửa thời điểm authorization. |
| EA-A34 | Emergency role đã revoke nhưng SSH/RDP session còn hoạt động. | Không đánh dấu REVOKED_VERIFIED khi policy đòi chặn session. |
| EA-A35 | Role emergency chỉ có quyền ở tenant B nhưng một trust cho assume tenant A. | Phát hiện escalation path, đánh giá scope thực tế. |
| EA-A36 | Snapshot authority cache cũ sau Leaver. | Không tự Permit; kiểm soát freshness/revocation. |

### Gherkin

~~~gherkin
Feature: Emergency access activation is conditional and lifecycle-aware

  Scenario: Verified outage permits only scoped recovery
    Given a critical IdP outage is independently confirmed
    And normal privileged recovery is unavailable
    And Lan is an eligible recovery responder for tenant B
    And the required emergency custody controls are satisfied
    When Lan requests emergency trust restoration
    Then only the approved trust restoration scope is activated
    And the activation has an expiry and auditable incident binding

  Scenario: An outage alone is insufficient to grant GlobalAdmin
    Given the PAM service is temporarily unavailable
    And production services do not require emergency intervention
    When a user requests unrestricted GlobalAdmin access
    Then activation is denied or routed to ordinary approval
    And no privileged grant is created

  Scenario: A mover cannot reuse obsolete emergency eligibility
    Given Lan was a recovery responder for the identity platform
    And a trusted Mover event removed that duty
    When an old emergency activation job retries
    Then no new emergency grant becomes effective
    And stale authority is logged as superseded

  Scenario: Leaver blocks an existing emergency access path
    Given an emergency session was created for a human responder
    And an authoritative Leaver event becomes effective
    When the responder tries a protected administrative operation
    Then access is denied according to the revocation policy
    And remaining sessions and credentials are reconciled

  Scenario: A closed incident cannot silently extend privileges
    Given an emergency role was active for incident INC-411
    And the incident is now resolved
    When the role activation window expires
    Then the workflow closes and revokes the emergency grant
    And residual access is not reported as verified until checked
~~~

### Kiểm tra không chỉ status code

Một endpoint trả HTTP 403 nhưng đã thay đổi config **trước khi check PEP** là lỗi. Với lệnh khôi phục cần đọc lại trạng thái resource, so diff có thẩm quyền, kiểm tra quyền token/session sau khi kết thúc. Nếu một test cần hành động phá hoại, dùng **staging/sandbox hoặc dry-run đáng tin**, không làm gián đoạn production trái phạm vi cho phép.

## 26. Audit và giám sát activation

### Phải truy vết được ba câu hỏi

1. **Vì sao kích hoạt?** Incident gì, tác động nào, normal path vì sao không đủ?
2. **Ai và bằng thẩm quyền nào?** Responder, approver/authority, custody/identity verification, scope và thời hạn.
3. **Đã làm gì và đã đóng thực sự chưa?** Những session/action thay đổi gì, credential nào đã rotate và quyền hiệu lực còn tồn không?

### Event minh họa

~~~json
{
  "eventType": "IAM_EMERGENCY_ACCESS_ACTIVATED",
  "activationId": "EA-2026-0042",
  "incidentId": "INC-2026-0411",
  "responderIdentityId": "IAM:ID-2041",
  "target": "IdentityPlatform:tenant-b",
  "allowedActions": ["trust.read", "trust.restore"],
  "incidentEvidenceRef": "incident-record-0411",
  "necessity": "PRIMARY_IDP_AND_NORMAL_RECOVERY_UNAVAILABLE",
  "authorityRef": "RECOVERY-RESPONDER-TENANT-B",
  "policyVersion": "emergency-access-v7",
  "activationMode": "OFFLINE_DUAL_CUSTODY",
  "issuedAt": "2026-12-01T09:00:00+07:00",
  "expiresAt": "2026-12-01T09:30:00+07:00",
  "targetGrantRef": "recovery-session-88",
  "status": "ACTIVE",
  "correlationId": "ea-42-inc-411"
}
~~~

Một event đóng quyền nên tham chiếu cùng activationId và ghi **revoke request, target observation, effective access verification, verifiedAt, credential rotation và post-review owner**.

Không ghi **password, private key, recovery seed, token nguyên vẹn, session cookie** hoặc nội dung dữ liệu nhạy cảm không cần thiết. Session recording có thể chứa bí mật/tài liệu khách hàng; phải có quyền xem giới hạn, retention và chính sách phù hợp.

### Cảnh báo nên hoạt động khi nào?

- Emergency account đăng nhập **ngoài mọi activation đã ghi nhận**.
- Account được dùng khi **không có incident hợp lệ** hoặc sau khi incident đóng.
- Thao tác ngoài resource/action scope của runbook.
- Emergency login trên thiết bị, mạng hoặc khu vực bất thường theo threat model.
- Dùng credential built-in/shared từ hai nơi bất thường.
- Lặp nhiều lần activation hoặc kéo dài vượt giới hạn.
- Một người cố tự thay approval policy, disable logging hoặc xóa dấu vết.
- Responder không còn ACTIVE hoặc emergency roster đã thu hồi.
- Kết thúc rồi nhưng token, JIT role hoặc local session còn hoạt động.

Nếu đường alert chính phụ thuộc chính IdP/logging đang lỗi, cần cơ chế **alternate logging/alert hoặc kiểm tra sau phục hồi** được thiết kế trước. Thiếu khả năng alert real-time phải được nhận diện là **rủi ro còn lại**.

### Chỉ số vận hành

| Chỉ số | Điều cần hiểu |
| --- | --- |
| **Activation count by incident type** | Emergency path được dùng cho loại sự cố gì; có bị lạm dụng cho việc thường không? |
| **Unjustified activation attempts** | Bao nhiêu yêu cầu không đạt necessity hoặc scope? |
| **Break-glass logins without incident binding** | Có dấu hiệu sử dụng trái quy trình không? |
| **Mean time to recovery access** | Đường khẩn cấp có thực sự sẵn sàng khi normal path lỗi? |
| **Responder/owner freshness** | Bao nhiêu người trong roster vẫn còn đủ authority/JML hợp lệ? |
| **Scope overgrant incidents** | Có lần nào mở quyền rộng hơn action/resource được duyệt? |
| **Activation duration and extensions** | Thời gian quyền đặc biệt tồn tại có vượt mức cần thiết? |
| **Emergency session revocation lag** | Sau incident close, bao lâu token/session mới không thể sử dụng? |
| **Unverified closure rate** | Có bao nhiêu lần chỉ đóng ticket mà chưa chứng minh mất quyền? |
| **Credential rotation/reseal compliance** | Emergency secret được xử lý sau sử dụng đúng policy chưa? |
| **Drill success and dependency failures** | Đường cứu hộ có thể hoạt động khi giả định IdP/PAM/network lỗi? |
| **Independent post-review completion** | Có hậu kiểm các action và dấu vết được thực hiện không? |

Không tối ưu một chỉ số duy nhất như **“activation phải mất dưới X giây”** bằng cách bỏ các kiểm soát bắt buộc. Cần cân bằng **khả dụng, độ tin cậy danh tính, phạm vi quyền, điều kiện dừng và khả năng giải trình**.

## 27. Tình huống thực hành

### Tình huống A — IdP outage và đường khôi phục phụ thuộc cùng IdP

**Bối cảnh:** IdP down. Tài khoản emergency cloud admin được tạo từ lâu nhưng vẫn buộc SSO với chính IdP này.

**Câu hỏi:** Điều kiện kích hoạt đã đủ chưa?

**Phân tích:** Trigger/necessity có thể có, nhưng **đường khôi phục không sẵn sàng** do phụ thuộc chung. Cần thiết kế đường xác thực dự phòng hợp lệ, custody/identity verification và diễn tập; không mở password admin công khai để “chữa” lỗi.

### Tình huống B — Outage PAM nhưng chưa có nhu cầu ứng cứu

**Bối cảnh:** PAM chậm và vault checkout lỗi, nhưng các hệ thống nghiệp vụ hoạt động bình thường. Một nhân viên muốn truy cập server để xem log định kỳ.

**Câu hỏi:** Có nên Activate break-glass?

**Phân tích:** Chưa có **necessity**. Có thể ghi sự cố PAM và giải quyết qua vận hành bình thường, không kích hoạt admin khẩn cấp chỉ vì tiện.

### Tình huống C — Responder Mover còn quyền lấy secret

**Bối cảnh:** Minh chuyển sang team Finance nhưng vẫn có quyền checkout emergency credential của Identity Platform.

**Câu hỏi:** Kiểm soát nào thiếu?

**Phân tích:** Mover chưa thu hồi **activation authority/custody**. Phải gỡ khỏi roster/vault group, đánh giá credential đã biết, thu hồi JIT eligibility và readback.

### Tình huống D — Incident đóng, JWT vẫn có quyền

**Bối cảnh:** Incident đóng lúc 10:20. PIM role revoked 10:21 nhưng JWT tới 10:45 còn được API chấp nhận.

**Câu hỏi:** Có thể đánh dấu VERIFIED_CLOSED ngay lúc 10:21?

**Phân tích:** Không nếu policy yêu cầu chấm dứt quyền trước đó. Cần kiểm chứng Resource Server/revocation boundary, containment và đo residual window.

### Tình huống E — Người bị Leaver từng biết password khẩn cấp

**Bối cảnh:** Một quản trị viên nghỉ việc nhưng shared emergency password chưa được rotate.

**Câu hỏi:** Đã thu hồi quyền emergency chưa?

**Phân tích:** Gỡ khỏi roster chưa đủ. Cần đánh giá credential exposure, rotate/reseal khi an toàn, chặn đường local và kiểm tra quyền thực tế.

### Tình huống F — Break-glass cho incident an ninh nhưng thiết bị ứng cứu cũng bị nghi compromise

**Bối cảnh:** Một operator muốn dùng chính laptop bị nghi chiếm quyền để mở emergency console.

**Câu hỏi:** Điều kiện xác minh danh tính và thiết bị đạt chưa?

**Phân tích:** Chưa đủ. Dùng kênh/thiết bị đáng tin theo playbook, tránh gửi credential vào máy hoặc phiên bị nghi lộ.

### Tình huống G — Gia hạn nhiều lần không có review

**Bối cảnh:** Emergency access 30 phút được gia hạn liên tiếp trong hai ngày bằng một nút “extend” không cần đánh giá incident.

**Câu hỏi:** Rủi ro ở đâu?

**Phân tích:** Emergency trở thành standing privilege. Cần giới hạn số/lần gia hạn, revalidate incident/actor/scope, approval và có điểm kết thúc rõ.

### Tình huống H — Automation nhận alert giả

**Bối cảnh:** Recovery bot cấp quyền cloud admin khi nhận webhook `severity=critical` mà không xác minh nguồn gửi.

**Câu hỏi:** Có phải trigger hợp lệ?

**Phân tích:** Không. Severity tự khai báo từ nguồn không xác thực không tạo emergency authority; cần ký/xác minh nguồn, quy trình incident và giới hạn scope.

### Tình huống I — Built-in account toàn quyền, policy chỉ cho một action

**Bối cảnh:** Target chỉ có built-in super-admin, không hỗ trợ scope nhỏ. Incident cần sửa một trust setting.

**Câu hỏi:** Có thể nói quyền đã least-privilege không?

**Phân tích:** Không. Phải thừa nhận technical overprivilege, yêu cầu kiểm soát bù như dual custody, giám sát/hậu kiểm lệnh, giới hạn phiên/kênh và kế hoạch giảm phụ thuộc account toàn quyền.

### Tình huống J — Leaver vừa xảy ra khi emergency activation job đang chờ

**Bối cảnh:** Responder bị Leaver trước khi job cấp emergency role hoàn tất. Job retry sau khi target phục hồi.

**Câu hỏi:** Điều gì phải chặn?

**Phân tích:** Grant dựa trên approval/roster cũ bị supersede. Worker phải revalidate lifecycle và authority tại thời điểm thực thi, không tái cấp sau Leaver.

### Tình huống K — Diễn tập kích hoạt nhưng không đóng

**Bối cảnh:** Đội kỹ thuật thử emergency credential trên sandbox và để phiên/tạm quyền mở sau bài test.

**Câu hỏi:** Diễn tập đã thành công chưa?

**Phân tích:** Chưa hoàn tất. Test phải gồm timeout/revoke, readback, credential reseal/rotate theo policy, alert và post-review, không chỉ đăng nhập được.

### Tình huống L — Emergency change và emergency access bị đánh đồng

**Bối cảnh:** Production gặp sự cố. Team còn đăng nhập qua normal PAM, nhưng đề nghị mở account break-glass vì thay đổi cần phê duyệt khẩn.

**Câu hỏi:** Có bắt buộc mở break-glass?

**Phân tích:** Không. Có thể dùng normal privileged access kết hợp **emergency change process**. Chỉ dùng emergency access khi điều kiện necessity riêng của nó đạt.

## 28. Câu hỏi tự kiểm tra

**1. Chỉ cần IdP outage là đủ để bật GlobalAdmin khẩn cấp cho bất kỳ kỹ sư nào?**

Không. Cần nhu cầu ứng cứu cụ thể, identity và authority hợp lệ, scope, controls, thời hạn và không có điều kiện phủ quyết.

**2. Trigger condition khác necessity condition thế nào?**

Trigger mô tả sự kiện khẩn cấp xảy ra; necessity giải thích vì sao **phải dùng đường khẩn cấp** thay vì đường thường lệ hoặc đường ít đặc quyền hơn.

**3. Emergency account tồn tại sẵn có nghĩa là mọi lúc được quyền sử dụng không?**

Không. Account được chuẩn bị để khôi phục; việc sử dụng phải tuân activation conditions, custody/alert và policy.

**4. Một incident SEV-1 có thể chấp thuận mọi action trên mọi tenant không?**

Không. Severity là điều kiện rủi ro, không thay authority, resource scope, action limit và SoD.

**5. Vì sao không nên dùng ticketing dựa vào SSO đang lỗi làm điều kiện duy nhất?**

Vì có thể mất khả năng tạo bằng chứng/duyệt ngay khi cần khôi phục. Cần kênh offline dự phòng đã được phê duyệt và audit.

**6. Khi IdP lỗi, có nên đơn giản tắt MFA cho mọi administrator không?**

Không. Cần đường xác thực hoặc custody dự phòng được chuẩn bị, không biến sự cố thành một bypass phổ quát.

**7. Eligibility và authorization to activate có giống nhau không?**

Không. Eligibility cho biết chủ thể có thể được xét; activation còn cần sự cố hợp lệ, necessity, scope và các controls tại thời điểm dùng.

**8. Dùng hai tài khoản của cùng một người có thỏa dual control yêu cầu hai người độc lập không?**

Không. Phải tính theo identity con người được xác minh, không theo số account.

**9. Nếu responder Mover khỏi nhóm IdentityOps nhưng vẫn còn vault access, rủi ro gì?**

Activation authority và đường custody tồn dư có thể mở lại đặc quyền; cần thu hồi và kiểm tra credential đã biết.

**10. Khi Leaver có hiệu lực, một approval emergency từ hôm trước có còn cho phép job mới cấp role không?**

Không nếu lifecycle policy cấm. Job phải kiểm tra authority/JML mới nhất trước khi cấp.

**11. Gia hạn quyền emergency có thể auto-extend khi Incident vẫn mở không?**

Không mặc định. Cần kiểm tra necessity, scope, actor, endAt và approval đúng policy gia hạn.

**12. Vì sao phải review session/token sau khi role revoked?**

Vì token tự chứa, cookie hoặc SSH/RDP session có thể tiếp tục dùng được dù role/Group đã được gỡ ở IdP/PAM.

**13. Emergency workload có cần HR manager như một employee không?**

Không. Nó cần service/workload identity và owner/trust/authorization riêng; không tự đồng nhất bot với owner nhân sự.

**14. Khi nào có thể chấp nhận một đường offline emergency?**

Khi nó được phê duyệt trước, có identity/custody, scope, điều kiện sự cố, thời hạn, chứng cứ và quy trình hậu kiểm; không phải fallback tùy ý.

**15. Normal PAM còn hoạt động, nhưng team cần emergency change. Có cần break-glass account không?**

Không nhất thiết. Quy trình change khẩn cấp và đường truy cập khẩn cấp là hai quyết định khác nhau.

**16. Chỉ có log “user đăng nhập thành công” có đủ làm bằng chứng activation đúng không?**

Không. Cần incident/necessity, authority, scope, thời hạn, các action đã thực hiện và kết quả thu hồi/hậu kiểm.

**17. Vì sao không được coi API revoke 204 là xác minh mọi quyền đã mất?**

Vì app-local role, credential, token hoặc session khác có thể còn; phải readback target và effective access trong phạm vi.

**18. Điều kiện dừng khẩn cấp gồm những gì?**

Incident kết thúc, endAt, mất eligibility/authority, nghi compromise, thay đổi scope/resource, control không còn bảo đảm hoặc lệnh revoke của owner.

**19. Một tài khoản built-in admin không hỗ trợ action scope hẹp phải được xử lý ra sao?**

Ghi nhận quyền kỹ thuật quá rộng và áp custody, dual control, monitoring, giới hạn sử dụng, hậu kiểm và kế hoạch cải tiến; không khẳng định least privilege giả.

**20. Vì sao diễn tập phải kiểm tra cả đường đóng và thu hồi?**

Vì đăng nhập được không chứng minh account/role/session/credential không tồn dư sau incident. Recovery capability gồm cả khả dụng **và khả năng kiểm soát, giải trình, thu hồi**.

## Ghi nhớ

- **Điều kiện kích hoạt Emergency access** cần nhiều lớp: **trigger sự cố đã xác minh, necessity, eligibility/authority, scope và controls, thời hạn cùng điều kiện kết thúc**. Một outage hoặc chữ “gấp” **không tự cho phép** mọi đặc quyền.
- **Emergency account/role/session** khác nhau; có account dự phòng không đồng nghĩa có quyền tự sử dụng mọi lúc. Kích hoạt và hành động cần gắn với incident, identity, resource, action, tenant và cửa sổ thời gian cụ thể.
- **Đường cứu hộ phải chịu được dependency đang lỗi**: IdP/SSO, PAM/PIM, ticketing, MFA hoặc network. Cần kênh xác minh/custody đã chuẩn bị thay thế, **không phải fail-open/permit-all**.
- **SoD, multi-party authority, least privilege, JIT/JEA, phishing-resistant authentication khi thích hợp, emergency credential custody và audit** phải được thiết kế phù hợp kịch bản outage; những quyền built-in rộng cần thừa nhận giới hạn và kiểm soát bù.
- **Joiner** không tự có quyền emergency trước ngày hiệu lực; **Mover** phải gỡ cả responder/activation authority và quyền cũ; **Leaver** phải chặn đường sử dụng, thu hồi role, session, token, credential và ngăn job cũ tái cấp; **rehire** không tự khôi phục lịch sử.
- **IdP/SSO, SCIM, PAM/PIM, RBAC/ABAC/PBAC, PIP/PDP/PEP và service/workload identities** bảo vệ các lớp khác nhau; việc thu hồi một Group/role không bảo đảm mọi phiên/token đích đã mất quyền.
- **Kích hoạt có kiểm chứng, giới hạn thời hạn, audit, readback, effective-access verification, diễn tập và hậu kiểm độc lập** giúp emergency access vừa sẵn sàng cứu hộ, vừa không trở thành cửa hậu hoặc quyền truy cập tồn dư trong toàn bộ vòng đời danh tính IAM.
