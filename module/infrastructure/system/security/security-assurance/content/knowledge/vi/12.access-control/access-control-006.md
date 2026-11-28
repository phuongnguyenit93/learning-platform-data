# Permission review – Rà soát và tái chứng nhận quyền truy cập

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **permission review** (rà soát quyền truy cập), **access recertification**, **entitlement review** và sự khác nhau giữa việc xem danh sách quyền với việc xác minh **quyền hiệu lực thực tế**.
- Xác định phạm vi cần review: người dùng, tài khoản dịch vụ, nhóm, role, tài nguyên, hành động, tenant, quyền quản trị, quyền tạm thời và những đường truy cập gián tiếp.
- Thiết kế quy trình **thu thập dữ liệu → chuẩn hóa quyền → đối chiếu nhu cầu → quyết định giữ/sửa/thu hồi → thực thi → kiểm tra lại → lưu bằng chứng**.
- Áp dụng **least privilege**, **need-to-know**, **separation of duties (SoD)** và quy tắc vòng đời nhân sự **joiner–mover–leaver (JML)** vào kết quả rà soát.
- Lập lịch kiểm tra định kỳ và kích hoạt theo sự kiện; giải quyết tình huống dữ liệu không đầy đủ, người phê duyệt không phù hợp, quyền không rõ chủ hoặc không thể thu hồi ngay.
- Xây dựng hồ sơ chứng minh hiệu lực control trong chương trình **security assurance**, liên kết với yêu cầu bảo mật, test, audit, finding, khắc phục và đánh giá rủi ro còn lại.
- Thực hành phân tích permissions của một dịch vụ Java/Spring Boot đa tenant và viết kiểm thử xác nhận quyền sau khi thay đổi.

## 1. Permission review là gì, và vì sao không chỉ là xem role?

**Permission review** là hoạt động đánh giá có kiểm soát xem **một chủ thể còn nên được phép thực hiện những hành động nào trên những tài nguyên nào, với điều kiện nào, tại thời điểm và môi trường đang xét**. Kết quả phải dẫn tới một **quyết định có trách nhiệm** và, khi cần, một hành động điều chỉnh quyền có thể kiểm chứng.

Ví dụ, một nhân sự chuyển từ nhóm vận hành sang nhóm phân tích. Trước đây người này cần quyền sửa cấu hình production; hiện chỉ cần xem dashboard. Permission review phải xác định các đường cấp quyền trực tiếp/gián tiếp, yêu cầu người được ủy quyền xác nhận nhu cầu mới, thu hồi quyền không còn hợp lệ và kiểm tra quyền sửa cấu hình **thực sự không còn hiệu lực**.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu không chỉ “đã có quy trình rà soát hằng quý” mà là **có bằng chứng hợp lý hệ thống đáp ứng mục tiêu bảo mật**. Việc review kết nối phân tích rủi ro, yêu cầu và security controls với **kiểm thử thực tế, audit, finding, remediation và security assurance liên tục**.

Một access review có thể được **hoàn thành đúng lịch nhưng không đạt hiệu lực**: ví dụ người duyệt ký toàn bộ danh sách mà không biết các quyền ngầm từ group, hoặc đã yêu cầu revoke nhưng token cũ vẫn được chấp nhận. Vì vậy cần tách **hoạt động đã thực hiện**, **chất lượng quyết định** và **kết quả quyền sau xử lý**.

### Các thuật ngữ cần phân biệt

| Thuật ngữ | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Identity / principal** | Ai/cái gì đang được cấp quyền? | Nhân viên, contractor, service account, workload identity |
| **Authentication** | Chủ thể được xác nhận danh tính bằng cách nào? | Đăng nhập SSO/MFA, token workload |
| **Authorization** | Hành động cụ thể trên tài nguyên có được phép không? | User A được export report R thuộc tenant A |
| **Entitlement / permission** | Quyền hoặc khả năng hành động được cấp theo policy là gì? | `report:export`, quyền ghi object storage |
| **Role** | Nhóm quyền phục vụ chức năng hoặc trách nhiệm | `REPORT_VIEWER`, `REPORT_ADMIN` |
| **Direct grant** | Quyền gán trực tiếp cho principal | User được cấp quyền vào bucket cụ thể |
| **Inherited / indirect access** | Quyền đến qua group, role hierarchy, federation hoặc delegation | User trong group có quyền deploy production |
| **Effective permission** | Kết quả quyền thực tế sau khi đánh giá tất cả policy, điều kiện và ưu tiên | User có thể đọc dữ liệu trong giờ làm việc, ở tenant A |
| **Provisioning / deprovisioning** | Cấp hoặc thu hồi quyền theo yêu cầu/sự kiện | Thêm user vào group; xóa quyền khi nghỉ việc |
| **Permission review / recertification** | Đánh giá lại quyền có còn phù hợp không | Owner quyết định giữ hoặc thu hồi grant đã tồn tại |
| **Access request** | Xin cấp hoặc thay đổi quyền mới | Đề nghị quyền xem báo cáo trong 30 ngày |
| **Access control test** | Thử xem hành vi cho phép/từ chối có đúng không | User A bị từ chối khi sửa báo cáo B |

**Có quyền được ghi trong IAM chưa chắc đã dùng được**, do điều kiện, deny policy, session, ranh giới tenant hoặc lớp authorization ở ứng dụng. Ngược lại, **không có grant trực tiếp** không chứng minh user không có quyền, vì quyền có thể được kế thừa hoặc ủy quyền.

## 2. Permission review bảo vệ mục tiêu và rủi ro nào?

Permission review đặc biệt hữu ích để giảm **quyền dư thừa theo thời gian** và phát hiện sai lệch giữa vai trò công việc với quyền đã cấp.

| Kịch bản rủi ro | Nguyên nhân/điều kiện | Hậu quả có thể xảy ra | Mục tiêu của review |
| --- | --- | --- | --- |
| Nhân viên đổi nhóm vẫn có quyền production | JML không thu hồi đầy đủ các grant gián tiếp | Thay cấu hình, lộ dữ liệu hoặc sửa giao dịch ngoài nhiệm vụ | Loại bỏ quyền không còn nhu cầu |
| Contractor đã kết thúc hợp đồng vẫn còn tài khoản | Không có owner/thời điểm hết hạn, nhiều identity | Truy cập trái phép sau khi kết thúc công việc | Xác minh account lifecycle và hết hạn |
| Service account có quyền `storage:*` | Role dùng chung hoặc cấp quyền rộng vì tiện triển khai | Nếu workload bị chiếm, blast radius lớn | Thu hẹp quyền theo tài nguyên/hành động |
| Một nhân viên vừa tạo vừa duyệt thanh toán | Vai trò xung đột, thiếu SoD | Gian lận hoặc lỗi không có lớp kiểm tra độc lập | Phát hiện và xử lý xung đột chức năng |
| User có role đọc báo cáo toàn tenant | Role mapping không xét resource ownership | Truy cập dữ liệu khách hàng khác | Đối chiếu quyền cấp đối tượng và policy tenant |
| Break-glass account có phiên hoạt động lâu | Quyền khẩn cấp không thu hồi sau sự cố | Duy trì đường truy cập đặc quyền ngoài quy trình | Review mọi lần cấp và trạng thái sau sử dụng |
| Admin có quyền qua group lồng nhau | Reviewer chỉ xem quyền trực tiếp | Bỏ sót đường đến dữ liệu nhạy cảm | Tìm mọi đường cấp quyền hiệu lực |

Nhưng review không thay thế enforcement. Một quyền được giữ hợp lệ vẫn cần **xác thực, kiểm tra quyền theo request, bảo vệ dữ liệu, logging và giám sát**. Nếu API có lỗi phân quyền ở cấp đối tượng (*broken object level authorization*), một chiến dịch rà soát group không tự sửa được lỗi đó.

### Các nguyên tắc thiết kế

- **Least privilege:** chỉ cấp những quyền cần thiết, ở phạm vi tài nguyên, hành động và thời gian phù hợp.
- **Need-to-know:** chỉ truy cập thông tin cần cho trách nhiệm được giao, đặc biệt dữ liệu nhạy cảm.
- **Default deny:** không tự cấp thêm quyền khi không có quy tắc cho phép phù hợp; mọi exception phải được xét theo policy.
- **Separation of duties:** những nhiệm vụ có khả năng tự phê duyệt hoặc lạm dụng không nên tập trung vào một actor nếu rủi ro yêu cầu phân tách.
- **Time-bound access:** quyền tạm thời cần có hạn và cơ chế thu hồi khi hết mục đích.
- **Traceability:** người cấp/duyệt, lý do, thời điểm, phạm vi và kết quả có thể truy ngược.

“Ít quyền hơn” không tự động là tốt nếu làm hỏng hoạt động nghiệp vụ quan trọng hoặc buộc dùng tài khoản chung. Quyết định cần gắn quyền với **nhu cầu đã kiểm tra**, đồng thời xử lý rủi ro availability và vận hành.

## 3. Phạm vi của một chiến dịch permission review

### 3.1. Những loại principal không được bỏ sót

1. **Nhân viên:** tài khoản IdP, ứng dụng, database, cloud và công cụ vận hành.
2. **Contractor, vendor và đối tác:** quyền theo hợp đồng, sponsor, ngày kết thúc, tenant và bộ phận phụ trách.
3. **Tài khoản quản trị/break-glass:** quyền đặc biệt, identity owner, thời hạn cấp và dấu vết sử dụng.
4. **Service account/workload identity:** CI runner, Kubernetes service account, cloud role, machine-to-machine token và cron job.
5. **Tài khoản chia sẻ hoặc kỹ thuật cũ:** cần kế hoạch quy trách nhiệm và loại bỏ nếu không đáp ứng khả năng truy vết.
6. **External/federated identity:** quyền thông qua SSO, group federation, khách hàng đa tenant hoặc cơ chế trust giữa tổ chức.
7. **Non-human secrets:** khóa API, credential ứng dụng và chứng chỉ có khả năng đại diện cho identity khác.

Không được lấy **danh sách HR** làm population duy nhất: HR thường không chứa robot account, workload, tài khoản ngoài tổ chức hoặc quyền kế thừa từ cloud federation.

### 3.2. Những lớp quyền cần đánh giá

| Lớp | Ví dụ | Rủi ro khi chỉ xem một lớp |
| --- | --- | --- |
| IdP / directory | Group, app assignment, SSO session | Không thấy quyền local role trong ứng dụng |
| Cloud/IAM | Role, policy, trust relationship, resource grant | Bỏ sót tài nguyên trực tiếp hoặc delegation |
| Kubernetes / platform | ClusterRole/RoleBinding, namespace, workload identity | Không thấy quyền ngoài namespace hoặc cluster-admin |
| Application | `REPORT_VIEWER`, `EXPORT_ADMIN`, policy tenant | Không thấy quyền suy ra từ dữ liệu/quan hệ nghiệp vụ |
| Database / storage | Table role, DB grants, object/bucket policy | Một service có đường đọc trực tiếp bỏ qua app |
| CI/CD / source control | Push repo, approve release, deploy production | Non-prod có thể dẫn tới thay đổi production |
| Secret manager / KMS | Đọc secret, giải mã, sửa policy, rotate key | Cấp quyền đọc khóa mở ra nhiều tài sản |
| SaaS / vendor | Workspace admin, export dữ liệu, API integration | Quyền ngoài IAM trung tâm không được rà soát |
| API token / session | Scope, expiry, revocation, refresh token | Revoke group nhưng token cũ còn hiệu lực |

### 3.3. Chọn population đúng và có thể tái lập

Một chiến dịch cần xác định:

- **As-of time:** snapshot trạng thái quyền tại thời điểm nào? Sau đó có delta nào?
- **Asset scope:** dịch vụ, account, tenant, namespace, database, môi trường nào?
- **Principal population:** những identity có quyền trực tiếp hoặc gián tiếp đến tài sản trong phạm vi.
- **Entitlement population:** những quyền/hành động nào, gồm tài nguyên và điều kiện cấp quyền.
- **Dữ liệu nguồn:** IdP, cloud IAM, application DB, service catalog, HR/vendor, secret registry, inventory.
- **Nguồn sự thật & sai khác:** nếu HR ghi user đã nghỉ nhưng IdP vẫn active thì xử lý thế nào?
- **Owner:** ai giải thích nhu cầu nghiệp vụ của entitlement, ai điều hành việc revoke?
- **Exclusion:** các loại quyền ngoài phạm vi và ai phê duyệt loại trừ.

**Không coi danh sách rỗng là “không có quyền nguy hiểm”** trước khi xác nhận connector/collector có đủ quyền đọc population. Đây là nguồn false assurance phổ biến.

## 4. Quyền hiệu lực: điều reviewer thực sự phải hiểu

Quyền hiệu lực là kết quả của **cơ chế authorization cụ thể**, không phải công thức cộng nhóm áp dụng cho mọi sản phẩm.

### 4.1. Các đường nhận quyền

~~~mermaid
flowchart LR
    USER["User / workload"] --> DIRECT["Direct grant"]
    USER --> GROUP["Group / nested groups"]
    USER --> ROLE["Role / role hierarchy"]
    USER --> DELEGATE["Delegation / federation"]
    DIRECT --> ENGINE["Policy evaluation theo nguồn quyền"]
    GROUP --> ENGINE
    ROLE --> ENGINE
    DELEGATE --> ENGINE
    RESOURCE["Resource policy / ACL / tenant"] --> ENGINE
    CONTEXT["Session, device, time, deny, conditions"] --> ENGINE
    ENGINE --> DECISION{"Effective allow / deny / unknown"}
    DECISION --> ASSET["Tài sản và action"]
~~~

**Ví dụ:** User A không có quyền `EXPORT_REPORT` được gán trực tiếp, nhưng nằm trong group `FinancePowerUsers`; group này kế thừa role `REPORT_ADMIN` và role có quyền xuất dữ liệu. Báo cáo chỉ liệt kê direct grants sẽ bỏ sót.

Ngược lại, user có role `REPORT_ADMIN` nhưng một policy ở tài nguyên cấm xuất dữ liệu tenant B. Không nên kết luận user có thể xuất dữ liệu tenant B chỉ từ role name. Khi cần khẳng định, reviewer phải **đối chiếu policy hiệu lực, điều kiện và test theo actor/resource/action**.

### 4.2. RBAC, ABAC và quan hệ tài nguyên

| Mô hình | Nguồn quyền thường gặp | Câu hỏi trong permission review |
| --- | --- | --- |
| **RBAC** | Role → permissions; user/group → roles | Ai đang có role nào, role đã thay đổi quyền chưa? |
| **ABAC** | Thuộc tính actor, resource, environment và action | Attribute/policy có còn đúng không, có trường hợp policy nới quá rộng? |
| **ReBAC / object relationship** | Quan hệ sở hữu, thành viên, chia sẻ hoặc ủy quyền | User còn là chủ sở hữu/thành viên của report hay project không? |
| **ACL / resource policy** | Grant gắn trực tiếp với từng tài nguyên | Có public hoặc external grant không còn nhu cầu? |
| **Cloud IAM policy evaluation** | Identity policy, resource policy, boundary, deny, session và điều kiện theo nền tảng | Quyền nào có hiệu lực với cấu hình hiện tại, cần công cụ/logic đánh giá nào? |

Một số hệ thống áp dụng **explicit deny, permission boundary, session constraint, context hoặc resource-based policy**. Không được lấy hợp `permission A ∪ permission B` rồi gọi là “effective permissions” khi sản phẩm có quy tắc ưu tiên/điều kiện phức tạp. Sử dụng công cụ đánh giá quyền hiệu lực hoặc hành vi thử từ chính nền tảng, đồng thời ghi giới hạn của phương pháp.

### 4.3. “Quyền chưa dùng” có được tự xóa?

Dữ liệu last-used hữu ích để ưu tiên, nhưng không đủ để tự quyết định:

- Tài khoản DR hoặc break-glass có thể **hiếm dùng nhưng rất cần khi sự cố**.
- Log usage không đầy đủ có thể gây kết luận sai.
- Quyền dùng gián tiếp qua workload hoặc delegation có thể không được ghi đúng identity gốc.
- Một nhiệm vụ định kỳ cuối quý/năm không xuất hiện trong khung 30 ngày.
- Quyền tồn tại chỉ vì nghiệp vụ chuyển người nhưng chưa có cập nhật HR.

Vì thế “không được sử dụng trong 90 ngày” nên là **tín hiệu cần review** theo policy, không phải bằng chứng quyền phải bị tự động revoke trong mọi trường hợp. Phải xét owner, nghiệp vụ, độ tin cậy dữ liệu và kế hoạch vận hành.

## 5. Quy trình permission review end-to-end

Một chiến dịch đáng tin nên có những giai đoạn và điểm kiểm soát sau.

### Bước 1 — Xác định mục tiêu và nguyên tắc ra quyết định

Ghi control objective, asset scope, mức rủi ro, loại quyền ưu tiên, reviewer authority, hạn hoàn thành, điều kiện ngoại lệ và phiên bản policy. Ví dụ: “Mọi quyền đọc dữ liệu khách hàng tại production phải có owner nghiệp vụ xác nhận và không vượt phạm vi nhiệm vụ, kể cả quyền gián tiếp”.

### Bước 2 — Lấy snapshot từ các nguồn liên quan

Lấy dữ liệu đúng thời điểm, môi trường và định danh; bao gồm cả:
- Identity đang hoạt động, bị khóa, nghỉ việc hoặc hết hợp đồng.
- Direct grants, group membership, nested group, role inheritance.
- Resource policies, quyền theo tenant/project, workload account.
- Thời gian cấp/đổi quyền, người phê duyệt, ticket ban đầu.
- Usage telemetry và các giới hạn coverage.
- Session/token đặc biệt có thể duy trì quyền sau khi revoke.

Snapshot phải có **ID, timestamp, collector, query/config version, phạm vi và số lượng**. Chỉ xuất CSV không có ngữ cảnh khó tái hiện và dễ thiếu dữ liệu.

### Bước 3 — Chuẩn hóa danh tính và entitlement

Một người có thể sở hữu nhiều identity, tài khoản kỹ thuật hoặc account theo môi trường; không nên hợp nhất bằng tên hiển thị. Dùng **ID ổn định** và quan hệ owner đã được xác minh. Quyền phải mô tả **principal → action → resource → conditions → grant path** thay vì “user có role A”.

Ví dụ dòng review:

~~~text
principal: uid-42
identity_owner: Business-Unit-X
environment: production
action: report:export
resource: tenant-A/reports/*
grant_path: idp-group:finance-leads -> application-role:REPORT_EXPORTER
grant_origin: CHG-0142
conditions: "only own-tenant reports"
last_verified_at: <TIMESTAMP>
~~~

### Bước 4 — Đánh giá rủi ro và phân nhóm ưu tiên

Ưu tiên những quyền:
- Quản trị IAM, secret, KMS, production, database và CI/CD.
- Cho phép xuất dữ liệu nhạy cảm, truy cập nhiều tenant hoặc chia sẻ công khai.
- Cấp qua group rộng, quyền wildcard, delegation hoặc tài khoản không owner.
- Đã hết hạn, không phù hợp vai trò hiện tại, trái SoD hoặc có incident/finding.
- Có khả năng tạo một đường tấn công qua nhiều hệ thống.

Tổ chức có thể dùng risk score nội bộ, nhưng điểm số không thay phân tích đường truy cập và hiệu lực policy. Một role `READ_ONLY` vẫn rủi ro cao nếu nó đọc được toàn bộ dữ liệu khách hàng.

### Bước 5 — Gửi quyết định tới reviewer có thẩm quyền

Người review cần nhận đủ **business context**, danh sách quyền hiệu lực, owner của người/tài nguyên, lý do cấp quyền, thời hạn và trạng thái sử dụng. Không gửi một bảng hàng nghìn role code khó hiểu rồi yêu cầu “Approve all” trong vài phút.

Các quyết định nên gồm:

| Quyết định | Ý nghĩa | Hành động tiếp |
| --- | --- | --- |
| **RETAIN** | Quyền vẫn cần thiết trong phạm vi hiện tại | Lưu rationale, reviewer, thời hạn review tiếp |
| **REVOKE** | Không còn nhu cầu hoặc không được phép | Thu hồi theo đường cấp quyền thực; xác minh quyền mất hiệu lực |
| **MODIFY** | Vẫn cần nhưng phải giới hạn action/resource/time | Thay quyền, test positive/negative, review lại |
| **INVESTIGATE** | Không rõ owner, grant path, purpose hoặc dữ liệu không đủ | Tạm quản lý như finding/unknown, bổ sung chứng cứ |
| **EXCEPTION** | Có lý do giữ tạm sai lệch theo quy trình | Risk decision có thẩm quyền, compensating controls, expiry |
| **NOT_APPLICABLE** | Quyền không thuộc phạm vi theo quy tắc rõ | Nêu căn cứ và người phê duyệt loại trừ |

**Không tự biến “reviewer im lặng” thành “RETAIN”** nếu policy không xác định rõ cơ chế đó và không có bảo vệ phù hợp. Quyền nhạy cảm cần cơ chế escalation khi owner không phản hồi, không phải được gia hạn vô thời hạn theo mặc định.

### Bước 6 — Kiểm tra SoD và quyền xung đột

Một quyết định retain có thể hợp lý nếu xét riêng từng role nhưng không hợp lý khi kết hợp:

| Quyền 1 | Quyền 2 | Rủi ro kết hợp |
| --- | --- | --- |
| Tạo nhà cung cấp mới | Phê duyệt thanh toán cho nhà cung cấp | Một actor có thể tạo và chi tiền không có kiểm tra độc lập |
| Viết mã nguồn nhạy cảm | Tự phê duyệt và deploy production không kiểm soát | Có thể thay logic và phát hành mà không được review |
| Tạo IAM role đặc quyền | Tự duyệt/grant role cho chính mình | Leo thang đặc quyền không có bước phê duyệt |
| Đổi log retention | Xóa audit records cùng hệ thống | Giảm khả năng điều tra thao tác của chính mình |

Tùy bối cảnh, SoD có thể là **ngăn phòng ngừa bằng policy**, **dual approval** hoặc **detective control có theo dõi**. Khi một tổ chức nhỏ buộc kiêm nhiệm, cần ghi quyết định rủi ro, control bù trừ và hạn xem xét; không tự tuyên bố xung đột đã biến mất.

### Bước 7 — Thực thi cấp/thu hồi và theo dõi lỗi

Bộ phận IAM/platform/application thực hiện thay đổi theo ticket, bảo vệ quy trình khỏi sai actor, sai tài sản hoặc nhầm môi trường. Một số quyền cần dỡ ở **nhiều lớp**: xóa group membership, local role, DB grant, secret/key, persistent session, API token hoặc resource ACL.

Kết quả công việc cần nêu:
- **Work item/change ID**, người thực hiện và quyền phê duyệt.
- Đường cấp quyền đã điều chỉnh và timestamp.
- Hệ thống trả lỗi hoặc trì hoãn đồng bộ, cần retry/escalation.
- Những token/phiên đang tồn tại có còn tác dụng hay không.
- Bằng chứng test quyền đúng/sai sau thay đổi.

“Đã xóa user khỏi group” có thể chưa đủ nếu ứng dụng cache role, token chứa claim cũ còn hiệu lực hoặc còn grant trực tiếp.

### Bước 8 — Xác minh lại effective permissions

Đây là bước tách permission review khỏi một chiến dịch **thu chữ ký**. Sau revoke hoặc modify:
1. Thu trạng thái quyền cập nhật từ cùng nguồn hoặc hệ thống thẩm quyền phù hợp.
2. Kiểm tra **các đường cấp quyền còn lại**, gồm group/role khác.
3. Thử hành vi với tài khoản và tài nguyên **được phép kiểm thử**.
4. Kiểm tra tác dụng của cache, session/token và thời gian lan truyền.
5. Xác nhận người dùng hợp lệ vẫn làm được công việc cần thiết.
6. Ghi lại kết quả, môi trường, version, actor và những giới hạn.

Một permission có thể đã biến mất khỏi bảng role nhưng một **quyền trực tiếp** vẫn cho phép truy cập. Một bản retest phải kiểm chứng **mục tiêu thật**: hành động trái phép bị từ chối.

### Bước 9 — Ghi finding, ngoại lệ và residual risk

Sai lệch chưa khắc phục, thông tin thiếu, owner không rõ hoặc test không đạt phải trở thành finding/issue có risk assessment và owner. Một ngoại lệ được duyệt có thể cho phép vận hành tạm nhưng **không đổi trạng thái kỹ thuật từ FAIL thành PASS**.

### Bước 10 — Review chất lượng chiến dịch và tạo trigger cho lần sau

Đối chiếu population đầu/cuối, các grant mới phát sinh sau snapshot, tỷ lệ quyết định đã được thực thi, các revoke chưa được xác minh, owner thiếu và xu hướng quyền đặc biệt. Từ đó cải thiện JML, quy trình cấp quyền, RBAC/ABAC policy và các kiểm tra tự động.

~~~mermaid
flowchart TD
    A["Định nghĩa scope, yêu cầu và reviewer"] --> B["Snapshot danh tính + grant paths + resources"]
    B --> C{"Nguồn dữ liệu/population đủ tin cậy?"}
    C -- "Không" --> U["INCONCLUSIVE / tìm nguyên nhân dữ liệu thiếu"]
    U --> B
    C -- "Có" --> D["Xác định quyền hiệu lực và rủi ro"]
    D --> E["Reviewer: retain / modify / revoke / investigate"]
    E --> F["Thực thi thay đổi theo grant path"]
    F --> G["Xác minh effective permission và security behavior"]
    G --> H{"Kết quả đạt yêu cầu?"}
    H -- "Không" --> I["Finding, remediation, retest, risk decision"]
    I --> F
    H -- "Có" --> J["Evidence, sign-off, owner và review trigger"]
~~~

## 6. Reviewer: ai nên có quyền quyết định?

Không phải mọi người quản trị IAM đều biết **quyền đó có còn cần cho nghiệp vụ**. Ngược lại, business owner có thể hiểu nhu cầu nhưng không biết technical role tạo ra quyền rộng tới mức nào. Hai góc nhìn phải được kết hợp.

| Vai trò | Trách nhiệm | Không nên giả định |
| --- | --- | --- |
| **Resource/Data Owner** | Quyết định ai cần hành động nào trên dữ liệu/tài sản và trong bao lâu | Mặc định hiểu mọi IAM grant path |
| **Line Manager / Sponsor** | Xác nhận người đó còn vai trò công việc, hợp đồng, nhiệm vụ phù hợp | Có quyền phê duyệt mọi entitlement nhạy cảm |
| **IAM / Platform Owner** | Giải thích entitlement, effective policy, thực thi thay đổi và thu evidence | Có quyền tự chấp nhận rủi ro nghiệp vụ |
| **Application Owner / Tech Lead** | Giải thích role nghiệp vụ, object authorization và đường tích hợp | Review một role đồng nghĩa xem hết quyền ở storage |
| **Security / AppSec / SOC** | Đánh giá rủi ro, SoD, privileged access và hiệu lực control, hỗ trợ phát hiện | Tự mình xác nhận nhu cầu nghiệp vụ của mọi user |
| **Risk Owner / Thẩm quyền phê duyệt** | Quyết định xử lý hoặc chấp nhận rủi ro còn lại theo chính sách | Một quyết định acceptance nghĩa là quyền đã an toàn |
| **Audit / Assessor** | Đánh giá tính đầy đủ và hiệu lực của review, bằng chứng và remediation | Chỉ có checklist ký tên là đủ kết luận |

Với quyền rất nhạy cảm, nên kiểm tra **conflict of interest**: user không tự phê duyệt quyền của chính mình; người thực thi grant nhạy cảm không tự duyệt toàn bộ; các trường hợp không thể phân tách phải được tài liệu hóa và áp dụng control phù hợp.

### Ví dụ RACI rút gọn

| Hoạt động | Data Owner | Manager | IAM/Platform | Security | Assessor |
| --- | --- | --- | --- | --- | --- |
| Định nghĩa quyền cần thiết | **A** | C | R/C | C | I |
| Xác nhận identity và nhu cầu | C | **R/A** | C | I | I |
| Xuất và giải thích quyền hiệu lực | C | I | **R/A** | C | I |
| Phê duyệt giữ/thu hồi trên tài sản | **R/A** | C | C | C | I |
| Triển khai revoke | I | I | **R/A** | C | I |
| Kiểm chứng kết quả theo risk | C | I | R | R/C | A khi cần độc lập |

**R** = thực hiện, **A** = chịu trách nhiệm cuối cùng, **C** = được tham vấn, **I** = nhận thông báo. Đây là mô hình minh họa; tổ chức cần xác định **một người/nhóm chịu trách nhiệm cuối cùng cho từng quyết định**, không gộp bừa vai trò khi quyền phê duyệt khác nhau.

## 7. Chu kỳ review và trigger ngoài lịch

Không có lịch cố định “mọi permission bắt buộc rà soát mỗi 90 ngày” áp dụng cho mọi tổ chức. Tần suất phải theo yêu cầu thực tế, mức rủi ro, tốc độ thay đổi, tài sản và nghĩa vụ áp dụng.

| Nhóm quyền | Hướng lập lịch minh họa | Trigger ngoài lịch |
| --- | --- | --- |
| Quyền thường ở ứng dụng nội bộ | Review định kỳ theo risk plan và owner | Nhân sự chuyển vai trò, đổi nhiệm vụ, đổi data classification |
| Privileged access sản xuất | Review với chu kỳ chặt chẽ hơn theo chính sách, giám sát thay đổi | Cấp quyền đặc biệt, incident, thay trust/policy, owner nghỉ việc |
| Break-glass và JIT elevation | Review **mỗi lần sử dụng/cấp**, cùng giám sát vòng đời và kiểm tra định kỳ | Sử dụng khẩn cấp, phiên kéo dài, lỗi thu hồi, không có owner |
| Service/workload identity | Review theo chu kỳ và khi code, policy, dependency hoặc data flow đổi | CI runner thay quyền, service dùng bucket mới, secret bị lộ |
| External/contractor | Có hạn gắn hợp đồng, review theo thay đổi chủ thể và tài sản | Hợp đồng kết thúc, sponsor thay, vendor access mới |
| Data exports / cross-tenant access | Đánh giá theo mức nhạy cảm, mỗi thay đổi lớn và định kỳ | Thêm endpoint export, share, tenant boundary thay đổi |
| SoD-sensitive roles | Review sau thay đổi quyền và định kỳ, kiểm tra xung đột | User được cấp thêm role đối nghịch, thay workflow duyệt |

Điểm cần nhớ: **review định kỳ không thay thế deprovisioning theo sự kiện JML**. Nếu nhân viên rời công ty hôm nay, quyền không nên đợi đến review tiếp theo mới được thu hồi khi policy yêu cầu xử lý ngay.

### Lịch và kỳ đánh giá cần nêu cụ thể

- Ngày chốt population và thời gian dành cho reviewer.
- Ngày phải hoàn thành quyết định, ngày phải thực thi và deadline retest.
- Đơn vị lịch (tháng lịch, quý lịch, 90 ngày…) và timezone.
- Nguyên tắc xử lý quyền mới phát sinh giữa snapshot và sign-off.
- Quy tắc escalations, người thay thế, ngoại lệ quá hạn.
- Kết quả review và bằng chứng phải được giữ bao lâu theo retention policy.

Lịch “hàng quý” không mặc định đồng nghĩa “cứ 90 ngày” hoặc “xong khi gửi email reviewer”.

## 8. Chuyển permission review thành security requirements có thể kiểm tra

Một chính sách “mọi quyền phải được review” quá mơ hồ để đánh giá. Viết thành tiêu chí có quan sát được.

| Requirement ID | Yêu cầu minh họa | Kiểm tra/evidence |
| --- | --- | --- |
| **REQ-PR-01** | Mọi principal có quyền production thuộc phạm vi được đưa vào population review, kể cả gián tiếp | Đối chiếu IdP, IAM, application, service identity; kiểm tra completeness |
| **REQ-PR-02** | Mỗi entitlement có owner/reviewer được ủy quyền và decision có rationale | Mẫu review record, authority mapping, sign-off |
| **REQ-PR-03** | Quyền không còn nhu cầu được revoke/giới hạn trong thời hạn đã phê duyệt | Ticket, policy/group diff, thời điểm thực hiện |
| **REQ-PR-04** | Sau revoke, đường truy cập trái phép phải bị chặn trong phạm vi được kiểm chứng | Negative tests theo actor/resource/action, session/token checks |
| **REQ-PR-05** | Quyền đặc biệt/break-glass có hạn và được review sau sử dụng | Privilege elevation records, expiry và audit trail |
| **REQ-PR-06** | Role SoD-sensitive không tạo xung đột chưa được xử lý hoặc được chấp nhận hợp lệ | Rule matrix, review conflict, exception và risk decision |
| **REQ-PR-07** | Mỗi đợt review có population snapshot, phiên bản tiêu chí, kết quả và người review | Evidence register, source snapshots, status |
| **REQ-PR-08** | Thay role membership/policy quan trọng kích hoạt đánh giá lại theo policy | Change event, ticket, alert và review ngoài chu kỳ |

**Không dùng tỷ lệ “100% reviewer đã click Approved” thay cho bằng chứng control đạt.** Nếu reviewer không có thông tin đủ hiểu entitlement, hoặc 30 tài khoản dịch vụ không có owner bị loại khỏi population, claim “mọi quyền đã được kiểm tra” là sai phạm vi.

## 9. Ví dụ thực tế: tài khoản và quyền trong hệ thống báo cáo đa tenant

### Kiến trúc

Ứng dụng `report-service` viết bằng Java/Spring Boot, sử dụng IdP cung cấp token, role mapping tại ứng dụng và một worker xuất báo cáo vào object storage. Người dùng thuộc các tenant A/B; có quản trị viên hỗ trợ khách hàng và tài khoản service để tạo CSV.

~~~mermaid
flowchart LR
    U["User / Support / Service Account"] --> IDP["IdP / JWT / Groups"]
    IDP --> API["Spring Boot Report API"]
    API --> AUTH["Authorization: actor + tenant + resource"]
    AUTH --> DB[("Reports Database")]
    API --> Q["Export Queue"]
    Q --> W["Export Worker Identity"]
    W --> DB
    W --> ST[("Object Storage")]
    IAM["IAM / Role / Resource policy"] --> W
    AUD["Permission review + evidence"] -. "Đánh giá IdP/App/IAM" .-> IDP
    AUD -. "Đánh giá quyền storage" .-> IAM
~~~

### Dữ liệu review minh họa

| Principal | Grant path | Quyền thực tế cần xác minh | Bối cảnh | Quyết định đề xuất |
| --- | --- | --- | --- | --- |
| **U-01** | Group `TENANT_A_REPORT_VIEWER` | Đọc báo cáo thuộc tenant A | Nhân sự tenant A, vẫn cần xem | RETAIN nếu policy và scope được xác minh |
| **U-02** | Group `SUPPORT_GLOBAL` → role `REPORT_ADMIN` | Xuất dữ liệu nhiều tenant | Đã chuyển khỏi bộ phận hỗ trợ | REVOKE hoặc MODIFY; kiểm tra token/role khác |
| **SA-03** | Cloud role của export-worker | Đọc nhiều bucket/tập dữ liệu | Chỉ phục vụ export theo tenant | MODIFY theo least privilege, kiểm tra quyền hiệu lực |
| **U-04** | Direct grant `REPORT_EXPORTER` | Export tenant A | Contractor đã hết hợp đồng | REVOKE, kiểm tra IdP và local grants |
| **BG-01** | Emergency admin | Sửa cấu hình, truy xuất hệ thống | Chỉ dùng xử lý sự cố | Review hạn/quy trình, không tự revoke nếu là control DR hợp lệ |
| **U-05** | Group lồng nhau cấp quyền deploy | Deploy production | Manager chỉ nghĩ U-05 có quyền xem logs | INVESTIGATE; làm rõ grant path và owner |

Một grant `REPORT_ADMIN` không tự chứng minh user có thể đọc tất cả report ở mọi tenant. Reviewer phải xem **effective authorization** ở application và storage. Ngược lại, nếu một API thiếu kiểm tra object-level permission, thu hồi role nguy hiểm vẫn **không sửa nguyên nhân kỹ thuật**; cần tạo finding riêng và test logic authorization.

### Review biến thành chuỗi hành động

**Với U-02**, Data Owner quyết định người dùng không còn nhu cầu export cross-tenant. IAM team gỡ U-02 khỏi group; application owner kiểm tra còn local role nào khác không; Ops kiểm tra token/session và đường API; assessor sử dụng account thử tương ứng để kiểm tra `POST /api/reports/export` với data test của tenant B bị từ chối.

**Với SA-03**, không thể chỉ yêu cầu “giữ vì worker cần chạy”. Cần giới hạn IAM role theo bucket/prefix/action được phép, đánh giá giới hạn ở tầng storage và kiểm thử worker được phép hoàn thành job hợp lệ nhưng bị từ chối khi truy cập dữ liệu ngoài phạm vi.

### Kịch bản hậu quả khi review thiếu

Nhóm quản lý có thể đánh dấu “all permissions certified”, nhưng U-02 vẫn có refresh token dùng được, hoặc SA-03 vẫn giữ quyền đọc mọi bucket. Nếu attack path tồn tại thì **assurance claim chưa được chứng minh**, dù file review có chữ ký. Đó là lý do test sau revoke quan trọng ngang với quyết định giữ/thu hồi.

## 10. Ví dụ SQL: lấy dữ liệu để review, không tự coi là effective permission

Giả sử ứng dụng có bảng `users`, `user_roles`, `roles`, `role_permissions` và `permissions` theo schema riêng. Query dưới đây chỉ minh họa **đường cấp role trực tiếp trong application RBAC**, không bao gồm nested groups, role hierarchy, external IAM, deny policy hoặc ràng buộc theo tenant.

~~~sql
-- Ví dụ schema giả định; điều chỉnh theo mô hình dữ liệu thực tế.
SELECT
    u.id AS principal_id,
    u.username,
    r.id AS role_id,
    r.code AS role_code,
    p.code AS permission_code,
    ur.granted_at,
    ur.grant_ticket_id
FROM users u
JOIN user_roles ur
    ON ur.user_id = u.id
JOIN roles r
    ON r.id = ur.role_id
JOIN role_permissions rp
    ON rp.role_id = r.id
JOIN permissions p
    ON p.id = rp.permission_id
WHERE u.status = 'ACTIVE'
ORDER BY u.id, r.code, p.code;
~~~

**Query này chưa đủ cho việc kết luận quyền hiệu lực** vì:

- Quyền qua IdP group, nested group, federation hoặc local overrides có thể không nằm trong database.
- Một permission code không mô tả được resource owner/tenant hay điều kiện theo thời điểm.
- Chỉ lọc `ACTIVE` có thể bỏ sót account đã khóa nhưng vẫn còn token, grant hoặc cần chứng minh đã thu hồi.
- Một permission có thể đến qua nhiều role; việc gỡ một role chưa chắc gỡ hết quyền.
- Một policy ở storage/cloud có thể độc lập với role ứng dụng.
- Query cho thấy snapshot tại một thời điểm, không đại diện mọi thay đổi trong kỳ.

Dữ liệu trích xuất phải được **bảo vệ**, phân loại, giới hạn quyền xem và có retention phù hợp. Không xuất secret, raw credential hoặc dữ liệu cá nhân không cần thiết vào tài liệu review.

## 11. Ví dụ Java 17: nhận diện grant cần xét lại

Một service phục vụ review có thể đánh dấu các grant lâu không được quan sát sử dụng hoặc đã hết hạn. Đoạn code **chỉ gắn cờ ưu tiên rà soát**, không tự thu hồi quyền và không tuyên bố một grant không dùng là bất hợp lệ.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Objects;

public final class PermissionReviewCandidate {
    public enum Flag {
        EXPIRED,
        NO_OWNER,
        STALE_USAGE,
        NEEDS_CONTEXT_REVIEW,
        NO_SIGNAL
    }

    public record Grant(
            String principalId,
            String resourceId,
            Instant expiresAt,
            Instant lastObservedUseAt,
            boolean ownerKnown,
            boolean usageTelemetryComplete) {}

    public static Flag classify(
            Grant grant, Clock clock, Duration inactivityThreshold) {
        Objects.requireNonNull(grant, "grant");
        Objects.requireNonNull(clock, "clock");
        Objects.requireNonNull(inactivityThreshold, "inactivityThreshold");

        if (inactivityThreshold.isZero() || inactivityThreshold.isNegative()) {
            throw new IllegalArgumentException("Ngưỡng phải dương");
        }

        Instant now = clock.instant();
        if (grant.expiresAt() != null && !now.isBefore(grant.expiresAt())) {
            return Flag.EXPIRED;
        }
        if (!grant.ownerKnown()) {
            return Flag.NO_OWNER;
        }
        if (!grant.usageTelemetryComplete()) {
            return Flag.NEEDS_CONTEXT_REVIEW;
        }
        if (grant.lastObservedUseAt() == null) {
            return Flag.NEEDS_CONTEXT_REVIEW;
        }
        if (!grant.lastObservedUseAt().isAfter(now.minus(inactivityThreshold))) {
            return Flag.STALE_USAGE;
        }
        return Flag.NO_SIGNAL;
    }
}
~~~

Các điểm cần nhớ:

- `EXPIRED` ở đây chỉ là tín hiệu grant **đã đến hạn theo metadata**, không tự chứng minh token/session đã mất quyền.
- `NO_OWNER` là lỗi dữ liệu/quản trị cần điều tra; không nên lấy người tạo tài khoản làm owner khi chưa xác nhận.
- `NEEDS_CONTEXT_REVIEW` ưu tiên xử lý khi telemetry thiếu; “không thấy truy cập” không đồng nghĩa “không dùng”.
- `STALE_USAGE` không tự cho phép revoke break-glass hoặc tài khoản DR.
- Kết quả `NO_SIGNAL` không chứng minh grant đã hợp lệ, an toàn hoặc đáp ứng SoD. Nó chỉ nói **không có tín hiệu theo các quy tắc sàng lọc trong ví dụ**.

Một số unit tests với JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

class PermissionReviewCandidateTest {
    private final Clock clock = Clock.fixed(
            Instant.parse("2026-11-28T00:00:00Z"), ZoneOffset.UTC);
    private final Duration threshold = Duration.ofDays(90);

    @Test
    void expiredGrantIsFlaggedAtBoundary() {
        var grant = new PermissionReviewCandidate.Grant(
                "u-01", "r-01",
                Instant.parse("2026-11-28T00:00:00Z"),
                Instant.parse("2026-11-27T00:00:00Z"),
                true, true);
        assertEquals(PermissionReviewCandidate.Flag.EXPIRED,
                PermissionReviewCandidate.classify(grant, clock, threshold));
    }

    @Test
    void missingUsageTelemetryIsNotProofOfInactivity() {
        var grant = new PermissionReviewCandidate.Grant(
                "u-01", "r-01", null, null, true, false);
        assertEquals(PermissionReviewCandidate.Flag.NEEDS_CONTEXT_REVIEW,
                PermissionReviewCandidate.classify(grant, clock, threshold));
    }

    @Test
    void oldObservedUseIsOnlyAReviewSignal() {
        var grant = new PermissionReviewCandidate.Grant(
                "u-01", "r-01", null,
                Instant.parse("2026-01-01T00:00:00Z"), true, true);
        assertEquals(PermissionReviewCandidate.Flag.STALE_USAGE,
                PermissionReviewCandidate.classify(grant, clock, threshold));
    }

    @Test
    void ownerMissingMustBeInvestigated() {
        var grant = new PermissionReviewCandidate.Grant(
                "u-01", "r-01", null,
                Instant.parse("2026-11-27T00:00:00Z"), false, true);
        assertEquals(PermissionReviewCandidate.Flag.NO_OWNER,
                PermissionReviewCandidate.classify(grant, clock, threshold));
    }
}
~~~

Đây là logic lọc ứng viên có thể tái kiểm tra với dữ liệu test. Nó **không thay** công cụ đánh giá policy hiệu lực, không kiểm tra đúng nghiệp vụ, không xác minh kết quả revoke và không phải thuật toán phê duyệt quyền. Trong hệ thống thật còn cần review job có audit, approval, concurrency control, bảo vệ dữ liệu và xử lý ngoại lệ.

## 12. Kiểm thử sau review: bằng chứng tốt khác với chữ ký

Một chiến dịch rà soát hiệu quả có **acceptance tests** dành cho quyền vừa thu hồi, giảm phạm vi hoặc các entitlement trọng yếu.

| Test ID | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- |
| **PR-T01** | User A còn role xem báo cáo tenant A | Vẫn xem được report hợp lệ theo policy |
| **PR-T02** | User A không được cấp quyền export tenant B | Export/tải tenant B bị từ chối, không trả dữ liệu |
| **PR-T03** | Thu hồi group của user nhưng còn session/token cũ | Truy cập sau revoke tuân thủ thời gian và cơ chế revoke được phê duyệt |
| **PR-T04** | Quyền export còn đến từ nested group khác | Phát hiện đường cấp quyền còn lại; không kết luận đã revoke toàn phần |
| **PR-T05** | Service account chỉ nên đọc bucket A | Đọc A được, đọc bucket B bị từ chối |
| **PR-T06** | Thử role conflict tạo và duyệt cùng giao dịch | Policy ngăn hoặc kích hoạt control bù trừ đúng thiết kế |
| **PR-T07** | Contractor hết hợp đồng có API token cũ | Token không còn tạo được hành động vượt phạm vi sau xử lý hợp lệ |
| **PR-T08** | Break-glass được cấp khi incident, sau đó hết hạn | Quyền đặc biệt bị thu hồi/kiểm soát, có dấu vết và phê duyệt |
| **PR-T09** | Snapshot nguồn IAM bị thiếu permissions do connector lỗi | Không ghi PASS; báo population/coverage INCONCLUSIVE hoặc FAIL theo tiêu chí |
| **PR-T10** | Quyền bị thay đổi ngay sau snapshot review | Có delta handling/event-triggered review hoặc limitation được ghi rõ |

### Kiểm tra authorization trong Spring Boot

Trong một ứng dụng Spring Security, `hasAuthority("REPORT_EXPORT")` có thể bảo vệ quyền **ở cấp chức năng**. Nhưng quyết định cuối cùng còn phụ thuộc **report thuộc tenant nào** và **chủ thể có quan hệ gì với report**. Review role không thay thế kiểm tra cấp đối tượng.

Ví dụ nghiệp vụ (giả định repository và policy service được triển khai riêng):

~~~java
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;

@Service
public class ReportExportService {
    private final ReportRepository reports;
    private final ReportPolicy policy;

    public ReportExportService(ReportRepository reports, ReportPolicy policy) {
        this.reports = reports;
        this.policy = policy;
    }

    public byte[] export(Authentication actor, long reportId) {
        Report report = reports.findById(reportId)
                .orElseThrow(() -> new AccessDeniedException("Not allowed"));

        if (!policy.mayExport(actor, report)) {
            throw new AccessDeniedException("Not allowed");
        }

        // Giá trị trả về là dữ liệu đã được tạo theo chính sách;
        // không đưa quyền hạn ở client vào quyết định này.
        return report.toCsv();
    }
}
~~~

Mã minh họa giả định `ReportRepository`, `ReportPolicy` và `Report` tồn tại với chữ ký tương ứng; **không phải ví dụ ứng dụng tự chạy độc lập**. `ReportPolicy.mayExport` phải thực hiện policy đáng tin (identity, role, tenant, owner, action, conditions), không chỉ so sánh một trường tenant từ header do client gửi. Với trường hợp actor bị revoke, cần bảo đảm quyết định authorization dựa trên trạng thái quyền đã có hiệu lực theo thiết kế.

### Kiểm chứng đường revoke ngoài ứng dụng

Một test API trả 403 **không chứng minh** người đó đã hết quyền đọc dữ liệu qua database, storage, API backup, CI runner hoặc tài khoản phụ. Assurance claim nên nêu **đúng phạm vi**: “đã revoke quyền export qua report-api và kiểm thử các đường liên quan được liệt kê”, thay vì “người dùng không thể truy cập bất kỳ dữ liệu nào” khi chưa kiểm tra toàn bộ hệ thống.

## 13. Hồ sơ permission review và traceability có thể audit

Một hồ sơ chỉ ghi “Reviewer = A, Status = Approved” là thiếu bối cảnh. Để audit có thể tái dựng **ai đã được cấp quyền gì, vì sao cần, quyết định thế nào, có được thực thi và kiểm tra hay không**.

### Từ rủi ro tới bằng chứng

~~~text
RISK-PR-01: Quyền export cross-tenant tồn đọng sau đổi vai trò
    -> OBJ-CONF-01: Bảo vệ bí mật dữ liệu giữa các tenant
    -> REQ-PR-03: Quyền không còn nhu cầu phải được thu hồi đúng hạn
    -> CTRL-PR-01: Permission review và JML-driven revoke
    -> TEST-PR-01: Kiểm tra hết quyền qua role/group và API export
    -> EV-PR-01: Snapshot, decision, IAM change, negative test, reviewer
    -> FIND-PR-01: Có đường kế thừa vẫn cho export (nếu phát hiện)
    -> RETEST-PR-01: Thu hồi đường còn lại, kiểm tra actual access
    -> RISK-REVIEW-01: Residual risk, ngoại lệ và quyết định tiếp theo
~~~

### Mẫu YAML bản ghi chiến dịch

Các giá trị trong dấu `<...>` là placeholder; YAML minh họa này **không phải bằng chứng đã thực thi**:

~~~yaml
campaign_id: PR-CAMPAIGN-001
control_id: CTRL-PR-01
module: SECURITY_SECURITY_ASSURANCE
title: "Production privileged and report-data access review"
environment: production
assessment_period:
  starts_at: "<ISO_8601_UTC>"
  ends_at: "<ISO_8601_UTC>"
as_of_time: "<SNAPSHOT_TIMESTAMP>"
owner: "<CONTROL_OWNER>"
risk_owner: "<AUTHORIZED_RISK_OWNER>"
scope:
  assets: ["report-api", "export-worker", "object-storage"]
  principals: ["human", "contractor", "workload", "break-glass"]
  entitlements: ["report:read", "report:export", "iam:admin"]
source_evidence:
  - system: "idp"
    snapshot_ref: "<IDP_GROUPS_AND_APP_ASSIGNMENTS>"
    completeness_check_ref: "<IDP_CONNECTOR_HEALTH>"
  - system: "application"
    snapshot_ref: "<ROLE_GRANTS_AND_TENANT_MAPPING>"
    completeness_check_ref: "<APP_POPULATION_VALIDATION>"
  - system: "cloud-iam"
    snapshot_ref: "<EFFECTIVE_POLICIES_AND_RESOURCE_PERMISSIONS>"
    completeness_check_ref: "<IAM_DISCOVERY_VALIDATION>"
population:
  principals_in_scope: "<COUNT>"
  entitlements_in_scope: "<COUNT>"
  exclusions: "<APPROVED_EXCLUSIONS>"
review_policy_version: "<APPROVED_VERSION>"
review_due_at: "<DUE_TIME>"
status: "<IN_PROGRESS_PASS_FAIL_INCONCLUSIVE_OVERDUE>"
decision_records_ref: "<PER_ENTITLEMENT_DECISIONS>"
remediation_records_ref: "<CHANGE_AND_REVOKE_TICKETS>"
verification_refs:
  - "<POST_REVOKE_POLICY_SNAPSHOT>"
  - "<NEGATIVE_AUTHORIZATION_TEST_REPORT>"
  - "<SESSION_TOKEN_REVOKE_VALIDATION>"
reviewer_signoff_ref: "<AUTHORIZED_REVIEWER_DECISION>"
findings: ["<OPEN_FINDING_IDS>"]
limitations: "<MISSING_SOURCES_OR_UNTESTED_PATHS>"
next_reassessment_trigger: "<DATE_CHANGE_OR_INCIDENT>"
~~~

### Bản ghi quyết định cho từng grant

~~~yaml
review_item_id: PR-ITEM-014
campaign_id: PR-CAMPAIGN-001
principal_id: "<STABLE_PRINCIPAL_ID>"
principal_type: human
identity_owner: "<CONFIRMED_MANAGER_OR_SPONSOR>"
resource_id: "tenant-A/reports"
action: "report:export"
grant_paths:
  - "<ROLE_GROUP_PATH_1>"
  - "<DIRECT_GRANT_OR_OTHER_PATH_IF_ANY>"
effective_permission_result: "<ALLOW_DENY_CONDITIONAL_UNKNOWN>"
business_justification: "<WHY_ACCESS_IS_NEEDED>"
risk_classification: "<APPROVED_RISK_CLASS>"
reviewer_id: "<AUTHORIZED_DATA_OWNER>"
reviewed_at: "<ISO_8601_UTC>"
decision: "<RETAIN_MODIFY_REVOKE_INVESTIGATE_EXCEPTION>"
decision_reason: "<EXPLICIT_RATIONALE>"
change_ticket: "<CHANGE_ID>"
implementation_result: "<APPLIED_FAILED_PENDING>"
post_change_verification: "<TEST_OR_POLICY_RESULT_ID>"
exception_ref: "<IF_APPROVED>"
outstanding_issue: "<FINDING_IF_ANY>"
next_review_trigger: "<DATE_OR_MATERIAL_CHANGE>"
~~~

Không chứa mật khẩu, secret, raw access token hoặc dữ liệu báo cáo thực trong YAML evidence. Hồ sơ cần được lưu với quyền truy cập phù hợp, lịch retention, kiểm soát tính toàn vẹn và lịch sử thay đổi.

### Ba lớp bằng chứng

| Lớp | Hiện vật | Điều chưa đủ chứng minh |
| --- | --- | --- |
| **Design evidence** | Quy trình review, role catalog, SoD policy, lịch và RACI | Chưa chứng minh đã review hoặc revoke |
| **Execution evidence** | Snapshot population, decision records, sign-off, ticket và IAM change | Chưa chứng minh quyền hiệu lực sau thay đổi |
| **Operating-effectiveness evidence** | Actual grants, negative tests, token/session checks, runtime policy, drift monitoring | Không bao phủ các nguồn/đường chưa kiểm tra và tương lai |

Một kết luận cần **thời điểm, phiên bản, môi trường, population, reviewer và limitation**. Nếu review chỉ bao phủ 80% tài khoản, phải nêu 20% còn lại; không biến tỷ lệ hoàn thành của phần đã quan sát thành “100% tổ chức đã review”.

## 14. Kết quả review và trạng thái control không giống nhau

| Trạng thái | Ý nghĩa | Quy tắc báo cáo |
| --- | --- | --- |
| **PASS** | Có bằng chứng đầy đủ trong phạm vi rằng quy trình review và hành động bắt buộc đã đáp ứng tiêu chí | Ghi population, kỳ và verification |
| **FAIL** | Phát hiện quyền sai/chưa thu hồi hoặc hoạt động review không đáp ứng yêu cầu | Finding, owner, deadline và retest |
| **INCONCLUSIVE** | Thiếu source, owner, dữ liệu, quyết định hoặc phạm vi thử để kết luận | Không tự chấm PASS; điều tra nguyên nhân |
| **NOT_RUN** | Hoạt động bắt buộc chưa thực hiện | Theo dõi lịch, escalation |
| **OVERDUE** | Vượt deadline review hoặc remediation đã duyệt | Báo trễ, đánh giá tác động của khoảng trống |
| **EXCEPTION_APPROVED** | Quyết định chấp nhận sai lệch trong phạm vi/thời hạn xác định | Không thay trạng thái kỹ thuật FAIL/INCONCLUSIVE |
| **REVOKE_PENDING** | Đã quyết định thu hồi nhưng chưa xác minh thực hiện | Không ghi “access removed” |
| **REVOKED_VERIFIED** | Sau thay đổi đã kiểm chứng quyền nằm trong scope bị từ chối | Gắn evidence, điều kiện và thời gian |

**Một tình huống quan trọng:** người duyệt quyết định `REVOKE` ngày thứ Hai, IAM team thực hiện ngày thứ Ba, nhưng token còn hiệu lực tới thứ Sáu. Với kịch bản rủi ro cần ngăn hành động ngay sau revoke, thời gian này là **khoảng exposure** cần đánh giá. Không dùng ngày ký decision làm ngày hết quyền nếu chưa có bằng chứng.

### Quyết định retain cũng cần đối chiếu

Ngay cả khi reviewer chọn `RETAIN`, cần xem quyền đang giữ có vượt nhu cầu hay tạo SoD conflict không. “Manager đã approve role ADMIN” chưa chứng minh role ADMIN phù hợp với tài sản và hành động. Các quyền có wildcard hoặc global access nên có bước giải thích scope và đánh giá riêng.

## 15. Những tình huống dễ gây false assurance

### 15.1. Kết quả dữ liệu đầu vào không đầy đủ

Một IAM collector mất quyền liệt kê group lồng nhau, trả 0 members. Dashboard hiển thị “Không có quyền đặc biệt chờ review”. Cách xử lý đúng: đối chiếu **connector health, expected counts, thay đổi population, quyền truy vấn và nguồn độc lập**; đánh dấu INCONCLUSIVE hoặc FAIL theo tiêu chí, không kết luận không có rủi ro.

### 15.2. Cấp quyền theo đường gián tiếp

Review gỡ role `REPORT_EXPORTER` khỏi user nhưng user vẫn ở group `FINANCE_POWER` có cùng action. Không được đánh dấu REVOKED_VERIFIED khi chưa xem **mọi grant path**.

### 15.3. Credential và session kéo dài

Ứng dụng sử dụng JWT lưu role trong claim. Nếu gỡ role ở directory nhưng ứng dụng tiếp tục chấp nhận access token cũ đến lúc hết hạn, review cần hiểu **mô hình revoke/session**, thời gian lan truyền và có biện pháp tương ứng khi rủi ro cần cắt quyền nhanh. Không giả định một thay đổi IdP đồng thời có hiệu lực với mọi token đã phát hành.

### 15.4. Service account không rõ owner

Một service account tên `integration-temp` dùng để gọi dữ liệu thật từ nhiều tháng trước, không có owner xác nhận. Cần điều tra workload và dependency thực; hạn chế quyền hoặc cô lập theo quyết định rủi ro. **Không xóa mù** một credential nếu việc đó có thể gây outage nghiêm trọng, nhưng cũng không mặc định giữ vĩnh viễn vì sợ ảnh hưởng.

### 15.5. Reviewer tự phê duyệt hoặc approve hàng loạt

Nếu chính người đang giữ quyền privileged được phép nhấn “Approve all” cho chính mình, SoD và tính độc lập suy yếu. Nếu khối lượng record quá lớn để xem xét thực chất, phải cải tiến **entitlement description, grouping theo nghiệp vụ, automation kiểm tra rule, phân tầng rủi ro và sampling hợp lý**, không biến thao tác click thành bằng chứng kiểm soát.

## 16. Quản lý finding và remediation

Một finding permission review phải có tối thiểu: ID, principal, resource/action, grant path, environment, risk scenario, owner, kết quả đã quan sát, quy định bị vi phạm, ngày phát hiện, hạn khắc phục, quyết định rủi ro và cách kiểm chứng sau sửa.

Quy trình ví dụ:

~~~mermaid
flowchart TD
    A["Finding: grant không còn nhu cầu hoặc sai SoD"] --> B["Xác nhận owner, blast radius và quyền hiệu lực"]
    B --> C["Đánh giá rủi ro, ưu tiên và kế hoạch giảm thiểu"]
    C --> D["Phê duyệt change/revoke hoặc ngoại lệ"]
    D --> E["Thực thi trên mọi grant path liên quan"]
    E --> F["Xác minh effective permission + API/storage behavior"]
    F --> G{"Kết quả đạt tiêu chí?"}
    G -- "Chưa" --> H["Giữ finding, bổ sung xử lý và retest"]
    H --> E
    G -- "Đạt" --> I["Lưu evidence, reviewer signoff, residual risk"]
    I --> J["Đóng finding có căn cứ, cập nhật review triggers"]
~~~

Khi có dấu hiệu quyền bị sử dụng trái phép, việc thu hồi nên phối hợp với **incident response** để bảo vệ bằng chứng và xác định phạm vi ảnh hưởng. Một ticket `REVOKE` không thay thế điều tra lạm dụng nếu log cho thấy dữ liệu đã được tải trước đó.

### So sánh ba quyết định khác nhau

- **Revoke/modify entitlement:** thay đổi trạng thái kỹ thuật của quyền.
- **Accept residual risk:** quyết định quản trị cho phần rủi ro vẫn tồn tại theo thẩm quyền.
- **Close finding:** kết luận rằng tiêu chí đóng đã được đáp ứng bằng evidence, hoặc có cách xử lý khác đúng policy.

Không dùng “đã có exception” để tự đánh dấu một permission vi phạm là “đã sửa”.

## 17. Permission review liên tục trong phát triển và vận hành

Permission review không nên tách khỏi release và vận hành hằng ngày. Những thay đổi có thể làm kết quả cũ không còn giá trị:

| Trigger | Việc cần đánh giá lại | Bằng chứng |
| --- | --- | --- |
| Joiner / mover / leaver | Quyền cấp mới, thay role, thu hồi theo nhiệm vụ | HR/sponsor event, IAM changes, verification |
| Role mới hoặc role được nới permission | Ai đã nhận thêm quyền gián tiếp, có tạo xung đột? | Role diff, group membership, test quyền |
| Thêm API/export route hoặc action mới | Role cũ có tự được phép hành động mới không? | API contract, policy mapping, negative tests |
| Thay tenant/resource ownership | User có còn đúng quyền ở ranh giới tenant? | Relationship/ACL data, authorization tests |
| Thay IAM trust, federation hoặc CI/CD | Có quyền liên môi trường, dùng chung credential hoặc quyền deploy không? | IAM snapshot, effective permission tests |
| Secret/token lộ hoặc session compromise | Thu hồi/rotate, phạm vi quyền và điều tra usage | Incident timeline, revoke/rotation logs |
| Admin/break-glass elevation | Đúng người/đúng hạn, có log và review sau sử dụng? | JIT grant, expiry, privileged event |
| Audit finding hoặc control FAIL | Review rộng hơn đối tượng phát hiện, khắc phục và retest | Finding ID, change, verification |
| Đổi data classification hoặc nghĩa vụ | Cần thu hẹp quyền với tài sản nhạy cảm hơn? | Data owner review, updated policy |
| Định kỳ theo risk plan | Dữ liệu nguồn còn đầy đủ, quyền còn cần thiết? | Full/differential snapshot, sign-off, exceptions |

Một **access certification theo lịch** nên đi kèm **continuous change monitoring** và **event-driven deprovisioning**; nếu chỉ kiểm tra một lần mỗi quý, quyền mới cấp sai có thể tồn tại nhiều tuần.

### Chỉ số cần theo dõi nhưng không được hiểu sai

| Chỉ số | Có ích để đo | Không chứng minh |
| --- | --- | --- |
| **Review completion rate** | Tỷ lệ record đã có quyết định đúng hạn | Quyền hiệu lực đều phù hợp |
| **Population coverage** | Tỷ lệ principal/entitlement có dữ liệu và owner | Không có đường quyền ẩn ngoài danh mục |
| **Revoke verification rate** | Tỷ lệ quyết định thu hồi đã xác minh kết quả | Những quyền được giữ đều an toàn |
| **Time to revoke** | Khoảng từ trigger/decision tới hiệu lực thực | Không có token/session tồn đọng ngoài scope |
| **Orphan/unknown-owner access** | Quyền thiếu người chịu trách nhiệm | Mọi grant khác đều hợp lý |
| **Privileged/SoD exceptions overdue** | Sai lệch cần escalations | Số exception thấp nghĩa là ít rủi ro |
| **Evidence freshness** | Bằng chứng còn gần trạng thái hiện tại không | Evidence mới là kết quả PASS |
| **Grant path visibility** | Mức truy vết direct/inherited/delegated permissions | Độ đúng của các quyết định nghiệp vụ |

Đừng đặt KPI “thu hồi càng nhiều quyền càng tốt”. Có thể gây gián đoạn và thúc đẩy người dùng chia sẻ tài khoản để làm việc. Mục tiêu phải là **quyền đúng người, đúng việc, đúng tài nguyên, đúng thời gian và được chứng minh**, không tối đa hóa số ticket đóng.

## 18. Bài tập thực hành: chiến dịch review production đa tenant

**Bối cảnh:** tổ chức sử dụng Spring Boot API quản lý đơn hàng và báo cáo khách hàng. Trong đợt review phát hiện:

- **U-100:** nhân viên đã chuyển sang Sales, nhưng còn group `FINANCE_ADMIN` cho quyền export toàn bộ báo cáo.
- **U-101:** contractor hết hợp đồng ba tuần trước, IdP account bị disable nhưng API token phát hành trước đó chưa được xác minh đã hết hiệu lực.
- **SA-200:** worker xuất CSV có quyền đọc nhiều bucket dữ liệu ngoài nhiệm vụ.
- **U-102:** user cần xem báo cáo tenant A nhưng role `REPORT_VIEWER` đang cho phép truy vấn mà không kiểm tra đúng tenant.
- **BG-01:** break-glass account chưa được dùng sáu tháng, vẫn cần cho kế hoạch khôi phục đã phê duyệt.
- **Collector:** công cụ rà soát chỉ export direct application roles; không có dữ liệu nested groups hoặc IAM resource policies.

### Yêu cầu

1. Viết **risk scenario** cho từng vấn đề theo tài sản, actor, đường quyền và hậu quả.
2. Xác định **population còn thiếu** và giải thích vì sao không thể ký “100% reviewed”.
3. Phân loại **RETAIN, REVOKE, MODIFY, INVESTIGATE hoặc EXCEPTION** cho các grant, giải thích ai có thẩm quyền quyết định.
4. Thiết kế ít nhất **sáu phép kiểm thử** về effective access, cross-tenant, token/session, bucket permission, nested group và break-glass.
5. Đề xuất **mốc kiểm tra theo sự kiện và định kỳ** cho user access, privileged access và service account.
6. Lập bằng chứng phục vụ audit trước và sau remediation, gồm snapshot, quyết định, change, retest, limitations và reviewer.
7. Nếu nhóm vận hành không thể thu hồi ngay quyền bucket của SA-200, nêu yêu cầu đối với ngoại lệ/compensating control và cách báo cáo residual risk.

### Hướng giải mẫu

| Trường hợp | Quyết định định hướng | Bằng chứng quan trọng |
| --- | --- | --- |
| **U-100** | REVOKE/MODIFY quyền không còn phù hợp; kiểm tra nhóm gián tiếp khác | Review owner, thay group, test export không còn quyền |
| **U-101** | INVESTIGATE/REVOKE quyền và token còn tác dụng, đồng thời xem xét incident risk nếu có dấu lạm dụng | IdP/session/token check, API negative test, revoke log |
| **SA-200** | MODIFY theo quyền cần thiết, xác định dependency trước thay đổi | Effective IAM policy, allowed/denied bucket tests, deployment |
| **U-102** | Tách finding **broken object-level authorization** khỏi review role; sửa code/policy và retest | Cross-tenant negative tests, PR, runtime deployment |
| **BG-01** | Không xóa chỉ vì ít dùng; xác nhận owner, hạn/quy trình và tính cần thiết | DR/runbook approval, test cấp/thu hồi, emergency-use audit |
| **Collector** | INCONCLUSIVE với toàn bộ claim hiệu lực; bổ sung nguồn group, IAM và kiểm tra completeness | Connector health, inventory cross-check, source snapshots |

**Kịch bản xử lý SA-200:** nếu giữ quyền rộng tạm, cần biết tài sản nào có thể bị ảnh hưởng, biện pháp giới hạn bổ sung (ví dụ network/tenant isolation, giám sát truy cập), cách kiểm thử chúng, người có thẩm quyền phê duyệt, thời hạn và kế hoạch sửa. **Quyền thực tế vẫn đang rộng**; không ghi PASS cho yêu cầu least privilege chỉ vì có ngoại lệ.

### Câu hỏi nâng cao

Một người dùng đã bị thu hồi `REPORT_ADMIN` trong IdP. Người dùng vẫn tải được báo cáo vì URL download do worker tạo trước đó còn hiệu lực. Đây là vấn đề của **permission review**, **authorization**, **session/token lifecycle** hay **storage access**?

**Định hướng:** có thể là **nhiều lớp cùng lúc**. Review phát hiện và yêu cầu thu hồi entitlement; authorization và cơ chế URL storage quyết định quyền sử dụng đường tải đã phát hành; TTL và revocation policy quyết định mức phơi lộ còn lại. Kết luận khắc phục cần xét toàn bộ đường gây hại và nghĩa vụ kỹ thuật, không chỉ gỡ role ở IdP.

## 19. Sai lầm thường gặp

| Ngộ nhận | Vì sao nguy hiểm? | Thực hành phù hợp |
| --- | --- | --- |
| “Đã có review sign-off là access an toàn.” | Quyền chưa chắc đã được thu hồi hoặc test | Theo dõi quyết định tới actual state và retest |
| “Chỉ xem direct roles là đầy đủ.” | Bỏ sót nested group, policy, delegation và local grants | Lập effective grant paths và kiểm tra completeness |
| “User đã nghỉ bị disable thì mọi token đều vô dụng.” | Token/session và service credential có vòng đời riêng | Kiểm tra khả năng dùng thực theo cơ chế revoke được duyệt |
| “Quyền không dùng 90 ngày bắt buộc xóa.” | DR và break-glass hiếm dùng; usage logs có thể thiếu | Dùng làm tín hiệu review, xác minh nghiệp vụ |
| “Approve all nhanh giúp đạt 100% KPI.” | Quyết định thiếu ngữ cảnh, dễ bỏ qua quyền nguy hiểm | Cung cấp entitlement meaning, rủi ro và owner có thẩm quyền |
| “Tên role READ_ONLY chắc chắn ít rủi ro.” | Có thể đọc mọi dữ liệu nhạy cảm | Đánh giá resource/action/tenant và blast radius |
| “IAM policy hiển thị Allow nên có quyền thật.” | Deny/boundary/context và app policy có thể thay kết quả | Dùng evaluation semantics đúng nền tảng và test |
| “Gỡ một group là hết quyền.” | Có thể còn nhiều grant paths và tài khoản phụ | Kiểm tra quyền hiệu lực sau thay đổi |
| “Quyền được giữ hợp lệ thì không cần test app.” | Broken authorization có thể bỏ qua toàn bộ permission | Negative tests theo actor, resource và action |
| “Không có account nguy hiểm trong scan tức là không tồn tại.” | Connector bị thiếu quyền hoặc population rỗng do lỗi | Đối chiếu nguồn và health, dùng INCONCLUSIVE |
| “Có exception nghĩa là least privilege đã đạt.” | Acceptance là quyết định quản trị, không thay đổi quyền | Giữ trạng thái gap và residual risk riêng |
| “Quarterly review đủ thay cho JML.” | User nghỉ việc/đổi vai trò cần xử lý theo event | Kết hợp deprovisioning theo sự kiện và review định kỳ |
| “Có ticket revoke Done là có thể đóng finding.” | Token, IAM sync và storage ACL có thể còn đường truy cập | Actual-state verification và test đầy đủ scope |
| “Một lần review áp dụng mãi mãi.” | Nhân sự, role, data, API và môi trường liên tục thay đổi | Event-driven reassessment, lịch và audit trail |

## Ghi nhớ

- **Permission review là đánh giá và tái chứng nhận quyền có căn cứ**, không phải chỉ thu chữ ký hoặc xuất danh sách role.
- Cần nhìn **principal → grant path → action → resource → conditions → effective access**, gồm cả group lồng nhau, service account, cloud resource policy, session và quyền cấp đối tượng.
- Quy trình đúng là **đầy đủ population → reviewer phù hợp → quyết định → thực thi → xác minh quyền thực tế → lưu bằng chứng**.
- **Least privilege và SoD** phải được xem xét ở cả quyền riêng lẻ lẫn các quyền kết hợp, đặc biệt với production, tài khoản đặc quyền và quyền liên tenant.
- Một **quyết định REVOKE chưa phải là REVOKED_VERIFIED**; kết quả thực tế sau thay đổi mới cho phép kết luận trong phạm vi test.
- Nếu dữ liệu nguồn thiếu hoặc chưa rõ owner, kết quả phải **INCONCLUSIVE/FAIL theo tiêu chí**, không mặc định PASS hoặc loại khỏi population.
- Permission review thuộc chuỗi security assurance **risk → requirement → control → test → evidence → finding → remediation/retest**, có lịch, trigger theo sự kiện, owner, trách nhiệm và quyết định rủi ro rõ ràng.
