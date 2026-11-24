# Recertification là gì? Rà soát và tái xác nhận quyền truy cập trong vòng đời danh tính IAM

## 1. Khái niệm Recertification

Trong **Identity and Access Management (IAM)**, **Access Recertification** là quá trình **xem xét lại những quyền truy cập đã tồn tại**, để người hoặc bộ phận có thẩm quyền xác nhận các quyền đó **có còn cần thiết, đúng chủ thể, đúng phạm vi, đúng chính sách và đúng thời hạn** hay không. Quá trình này thường được gọi là **access certification**, **access review**, **user access review** hoặc **entitlement recertification**, tùy phạm vi và sản phẩm.

Ví dụ, kỹ sư Huy từng được cấp **RepositoryAdmin** cho Dự án Atlas để xử lý sự cố. Ba tháng sau, Huy chuyển sang công việc phân tích dữ liệu tại Nova. Khi rà soát định kỳ, người phụ trách thấy role RepositoryAdmin vẫn tồn tại ở hệ thống mã nguồn. Recertification yêu cầu xác minh **Huy có còn công việc và phê duyệt nào cần quyền đó không**; nếu không, phải quyết định thu hồi, thực thi tại ứng dụng và kiểm chứng quyền thực sự đã bị chặn.

Recertification không chỉ là việc một quản lý bấm nút **Keep** trên danh sách tài khoản. Một chiến dịch có chất lượng cần đủ:

1. **Phạm vi:** danh tính, tài khoản, role, nhóm, ACL, token/grant và hệ thống nào được rà soát.
2. **Ngữ cảnh:** công việc, organization, chủ sở hữu tài nguyên, dữ liệu nhạy cảm, thời hạn và nguồn cấp quyền.
3. **Người quyết định:** reviewer có thẩm quyền và không xung đột lợi ích.
4. **Quyết định rõ ràng:** giữ, thu hẹp, thu hồi, yêu cầu giải trình hoặc ngoại lệ có hạn.
5. **Thực thi:** kết quả rà soát được chuyển thành thay đổi IAM/IdP/SCIM/ứng dụng.
6. **Bằng chứng:** đọc lại quyền tại hệ thống đích và kiểm tra quyền hiệu lực khi cần.
7. **Kiểm toán:** giải thích được ai xác nhận quyền nào, khi nào, dựa trên dữ liệu gì.

Mục tiêu là **giảm quyền truy cập không còn căn cứ** và phát hiện **privilege creep**, đặc biệt trong vòng đời **Joiner–Mover–Leaver (JML)**. Một tài khoản có thể vẫn đăng nhập SSO bình thường nhưng giữ quyền không còn phù hợp; recertification giúp phát hiện sai lệch đó.

## 2. Vì sao tổ chức cần tái xác nhận quyền?

Quyền truy cập hiếm khi đứng yên. Một người có thể đổi phòng ban, chuyển dự án, kết thúc hợp đồng hoặc được cấp quyền tạm thời nhưng quên thu hồi. Ứng dụng cũng đổi role, group mapping, cơ chế chia sẻ và hệ thống quản trị.

Các nguyên nhân thường gặp:

| Sự kiện | Rủi ro quyền truy cập |
| --- | --- |
| **Joiner** được cấp baseline và nhiều quyền bổ sung | Role cấp mặc định quá rộng hoặc phê duyệt thiếu |
| **Mover** đổi vị trí hoặc dự án | Chỉ thêm quyền mới, giữ quyền cũ |
| **Leaver** kết thúc quan hệ làm việc | Local account, ACL, PAT hoặc phiên còn dùng được |
| **Quyền tạm thời** không được thu hồi đúng hạn | Ngoại lệ trở thành standing privilege |
| **Role/group mapping** thay đổi | Một group bắt đầu mang thêm entitlement không ai rà soát |
| **Người quản lý tài nguyên** đổi vị trí | Quyền thiếu owner có trách nhiệm kiểm soát |
| **Workload** ngừng hoạt động hoặc đổi đội phụ trách | Service account có đặc quyền không còn nhu cầu |
| **Tài khoản đối tác** không có ngày hết hạn | Quyền tồn dư sau dự án hoặc hợp đồng |
| **Quyền trực tiếp** cấp ngoài quy trình IGA | Group IdP đã xóa nhưng ứng dụng vẫn cho truy cập |

Recertification còn giúp người sở hữu dữ liệu trả lời một câu hỏi quan trọng: **“Ai hiện đang có thể làm gì với tài nguyên của tôi, và điều đó có còn hợp lệ không?”**

Tuy nhiên, **recertification không thay thế kiểm soát truy cập thời gian thực**. Nếu HRIS xác nhận một người đã nghỉ việc hôm nay, tổ chức không nên chờ đến chiến dịch review quý sau mới thu hồi quyền.

## 3. Phân biệt Recertification với những quy trình IAM liên quan

| Quy trình | Câu hỏi cần trả lời | Khi nào áp dụng |
| --- | --- | --- |
| **Identity proofing/enrollment** | Chủ thể này là ai, đã được xác minh chưa? | Khi thiết lập hoặc xác minh danh tính |
| **Access request** | Người đó muốn xin quyền nào, vì sao? | Khi có nhu cầu quyền mới hoặc thay đổi |
| **Approval workflow** | Yêu cầu mới có được người có thẩm quyền chấp thuận không? | Trước khi cấp quyền cần phê duyệt |
| **Provisioning/deprovisioning** | Account, group, role đã được tạo/sửa/thu hồi chưa? | Khi thực thi trạng thái quyền mong muốn |
| **Access reconciliation** | Quyền hiện tại tại target có khớp trạng thái mong muốn không? | Sau thay đổi và theo lịch |
| **Access recertification** | Quyền đang tồn tại có còn cần, đúng phạm vi, đúng owner và đúng chính sách không? | Định kỳ hoặc theo sự kiện |
| **Authentication review** | Tài khoản và phương thức đăng nhập còn an toàn không? | Theo chính sách xác thực và vòng đời authenticator |
| **Policy/role review** | Chính định nghĩa role/policy có còn đúng và ít quyền không? | Khi thay đổi sản phẩm, role, quy trình hoặc theo lịch |

**Reconciliation là đối chiếu kỹ thuật**, có thể phát hiện ứng dụng còn role chưa thu hồi. **Recertification là quyết định quản trị về tính hợp lệ và nhu cầu nghiệp vụ** của quyền. Hai bước cần phối hợp: recertification phải dùng dữ liệu quyền thực tế, còn quyết định thu hồi phải được reconciliation xác nhận đã có hiệu lực.

Một quyền được reviewer **Keep** không chứng minh kỹ thuật rằng API đã giới hạn đúng phạm vi. Ngược lại, một role bị reviewer **Revoke** nhưng connector chưa thực thi thành công thì vẫn có thể tồn tại ở target.

## 4. Recertification kiểm tra những gì?

Phạm vi có thể là một hoặc nhiều nhóm sau:

| Đối tượng review | Câu hỏi điển hình |
| --- | --- |
| **User account** | Tài khoản có còn chủ sở hữu và quan hệ làm việc hợp lệ không? |
| **Application role** | Role Viewer/Editor/Admin còn cần cho nhiệm vụ hiện tại không? |
| **Group membership** | Thành viên nhóm IdP/SCIM/ứng dụng có hợp lý không? |
| **Direct entitlement/ACL** | Quyền cấp riêng có approval, owner và thời hạn không? |
| **Privileged access** | Admin, production role hoặc khả năng cấp quyền tiếp có cần duy trì không? |
| **Service/workload identity** | Bot có còn chạy, có owner, scope và credential phù hợp không? |
| **Third-party/guest access** | Quan hệ sponsor và thời hạn hợp đồng còn hợp lệ không? |
| **OAuth authorization grant** | Client/scope/consent có vượt nhu cầu hoặc còn sau dự án không? |
| **PAT/API key/credential** | Có đường truy cập độc lập cần thu hồi/đổi chủ không? |
| **Ownership/role delegation** | Quyền sở hữu tài nguyên, quyền phê duyệt hoặc ủy quyền còn đúng không? |
| **Role/policy composition** | Group hoặc role có phát sinh quyền quá rộng do kế thừa không? |

Không phải mọi chiến dịch phải review tất cả cùng lúc. Tổ chức có thể triển khai các **campaign theo ứng dụng, mức rủi ro, nhóm danh tính hoặc loại quyền**; nhưng cần có danh sách vùng chưa được bao phủ và kế hoạch xử lý.

**Chỉ review group ở IdP sẽ bỏ sót quyền trực tiếp và token riêng ở ứng dụng.** Đó là giới hạn phạm vi phải được ghi nhận, không phải lý do kết luận toàn bộ quyền đã được xác nhận.

## 5. Bốn lớp dữ liệu: expected, assigned, effective và used access

Để tránh bấm giữ/thu hồi trên thông tin thiếu, cần phân biệt:

| Lớp | Ý nghĩa | Nguồn điển hình |
| --- | --- | --- |
| **Expected access** | Những quyền **nên tồn tại** theo nhiệm vụ và approval hiện hành | HRIS, IGA, resource owner, policy |
| **Assigned access** | Những quyền đã được cấu hình/gán | IdP groups, SCIM, SaaS roles, ACL, cloud IAM |
| **Effective access** | Hành động và tài nguyên mà hệ thống thực sự có thể **ALLOW** tại thời điểm đánh giá | PDP/PEP, policy engine, ứng dụng đích |
| **Used access** | Hoạt động được thấy trong nhật ký ở một cửa sổ quan sát | Audit/event logs, API telemetry |

Ví dụ:

~~~text
Expected:
    Huy chỉ có READ Nova

Assigned:
    NovaReader
    AtlasRepositoryAdmin trực tiếp tại SaaS

Effective:
    READ Nova
    READ, WRITE, MANAGE_ACCESS Atlas

Observed use trong 90 ngày:
    READ Nova: 156 lần
    WRITE Atlas: 0 lần được ghi nhận
~~~

Quyền Atlas là **ứng viên quyền thừa mạnh** vì vượt expected, không phải chỉ vì log báo không sử dụng. Nếu log chưa bao phủ mọi API, giá trị 0 không đủ chứng minh quyền chưa từng được dùng.

**Recertification tốt cần hiện rõ phần quyền phát sinh so với nhu cầu**, không chỉ hiển thị tên role mà reviewer có thể không hiểu.

## 6. Ai là người thực hiện và chịu trách nhiệm?

| Vai trò | Trách nhiệm |
| --- | --- |
| **IAM/IGA governance** | Thiết kế campaign, phạm vi, policy, tuyến reviewer và bằng chứng |
| **Manager** | Xác nhận công việc, quan hệ quản lý và nhu cầu người được rà soát |
| **Resource/application owner** | Xác nhận quyền trên tài nguyên/ứng dụng mình chịu trách nhiệm |
| **Data owner** | Quyết định quyền trên dữ liệu theo phân loại và trách nhiệm dữ liệu |
| **Security/privileged access owner** | Rà soát quyền admin, SoD, ngoại lệ và rủi ro |
| **Sponsor** | Xác nhận quan hệ hợp lệ của contractor, partner hoặc guest |
| **Service owner/team** | Xác nhận nhiệm vụ và quyền của workload/service account |
| **Reviewer/delegate** | Đưa ra quyết định trong phạm vi ủy quyền thực tế |
| **Provisioning operator/automation** | Thực thi kết quả review tại hệ thống đích |
| **Auditor/compliance** | Kiểm tra bằng chứng và hiệu quả kiểm soát, không mặc nhiên là người cấp quyền |

**Manager không phải luôn là người có thẩm quyền với mọi dữ liệu**. Manager có thể biết nhân viên còn làm dự án không, nhưng data owner mới có quyền phê duyệt đọc dữ liệu nhạy cảm. Với quyền rủi ro cao, có thể cần **nhiều lớp đánh giá**, tùy chính sách.

**Tránh self-certification** khi beneficiary đồng thời là reviewer trái quy định. Người có quyền admin không nên tự xác nhận quyền admin của mình mà thiếu kiểm soát độc lập.

## 7. Review theo người, theo ứng dụng và theo quyền

Có nhiều cách gom campaign:

| Cách tổ chức | Reviewer thuận tiện | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **User/manager review** | Manager | Xem toàn bộ quyền của một nhân viên | Có thể không hiểu quyền kỹ thuật |
| **Application review** | Application owner | Hiểu role và quyền trong sản phẩm | Có thể thiếu bối cảnh công việc người dùng |
| **Entitlement/privilege review** | Role/data/security owner | Tập trung quyền nhạy cảm | Có thể phân mảnh thông tin theo người |
| **Resource-centric review** | Chủ dữ liệu/dự án | Biết ai được xem đối tượng nhạy cảm | Có thể khó tổng hợp quyền xuyên hệ thống |
| **Workload review** | Service/platform owner | Đúng mô hình máy–máy | Log và identity ownership thường khác người dùng |
| **Event-driven review** | Owner liên quan đến biến động | Phát hiện nhanh sau Mover/project end | Phụ thuộc chất lượng sự kiện nguồn |

Thường nên kết hợp: **manager xác nhận nhu cầu nghiệp vụ**, **application/resource owner xác nhận permission**, và **security/IGA đánh giá SoD hoặc quyền đặc biệt**.

Một campaign được chia đúng reviewer sẽ giảm **rubber-stamping** — tình trạng bấm Keep hàng loạt không hiểu quyền và không xem bằng chứng.

## 8. Khi nào cần recertification?

Hai nhóm trigger chính:

### 8.1. Định kỳ theo lịch

Tổ chức chạy chiến dịch theo **mức rủi ro, quy định nội bộ và cam kết kiểm soát**. Ví dụ nội bộ có thể chọn review quyền đặc quyền **hàng quý**, quyền thông thường **nửa năm/hàng năm** và workload rủi ro cao thường xuyên hơn. Đây là **ví dụ thiết kế**, không phải chu kỳ bắt buộc chung cho mọi hệ thống hoặc một yêu cầu pháp lý mặc định.

### 8.2. Theo sự kiện

Các trigger có thể gồm:

- Nhân viên **Mover** sang phòng ban hoặc dự án mới.
- Hợp đồng/sponsorship đối tác gần hết hạn.
- Quyền **temporary/JIT** đạt mốc review hoặc có yêu cầu gia hạn.
- Tài nguyên đổi owner hoặc mức phân loại.
- Role/group được sửa nội dung permission.
- Phát hiện tài khoản không có owner, dormant hoặc privilege bất thường.
- Phát hiện **SoD conflict**, thông báo bảo mật hoặc thay đổi risk tier.
- Thay đổi chủ sở hữu workload hoặc decommission service.

**Leaver cần thu hồi theo mốc bắt buộc, không chờ chiến dịch**. Event-driven recertification có thể giúp kiểm tra lại những quyền liên quan, nhưng không được thay thế tiến trình deprovisioning khẩn hoặc theo lịch đã duyệt.

## 9. Tần suất theo rủi ro, không chỉ theo thói quen

Khi thiết kế cadence, có thể xét:

| Yếu tố | Rủi ro cao hơn khi |
| --- | --- |
| **Mức quyền** | Admin, sửa policy, tạo user hoặc cấp quyền tiếp |
| **Dữ liệu** | Dữ liệu tài chính, nhân sự, bí mật sản xuất |
| **Phạm vi** | Nhiều tenant, toàn organization hoặc production |
| **Credential** | PAT/API key dài hạn, không ràng buộc audience |
| **Danh tính** | Đối tác, ownerless service account hoặc quan hệ khó xác minh |
| **Thời gian** | Quyền standing, ngoại lệ không có expiry |
| **Lịch sử** | Finding tồn dư, SoD hoặc reviewer không phản hồi |
| **Khả năng đối soát** | Target không cung cấp API đọc quyền hoặc log thiếu |

Một role **ReadOnly** có thể vẫn rủi ro cao nếu đọc được credential hoặc dữ liệu rất nhạy cảm. **Không chỉ dựa tên role** để quyết định chu kỳ review.

Một campaign có thể ưu tiên **quyền đặc quyền, quyền xuyên tenant, quyền sau Mover, các tài khoản service không có owner và các grant quá hạn** trước khi rà soát số lượng lớn quyền ít rủi ro.

## 10. Chuẩn bị chiến dịch: xác định scope và snapshot

Trước khi gửi cho reviewer, IAM/IGA cần:

1. Chốt danh sách **hệ thống và tenant** thuộc phạm vi.
2. Lấy danh sách **account, role, group, ACL, ownership, OAuth grant** theo khả năng target.
3. Liên kết **target account → IAM identity → person/employment/workload** đã xác minh.
4. Bổ sung **expected access** từ nguồn có thẩm quyền và approval còn hiệu lực.
5. Tính hoặc lấy **effective access** khi khả thi, ghi rõ giới hạn không tính được.
6. Gắn **source version, extraction timestamp, policy version và dữ liệu sử dụng**.
7. Phân quyền reviewer theo chủ tài nguyên và giới hạn xung đột.
8. Chốt **campaign start/end, reminder, escalation, review SLA và cutoff**.
9. Kiểm tra dữ liệu nhạy cảm không bị hiển thị quá mức cho reviewer.
10. Khóa hoặc version hóa snapshot, đồng thời thiết kế cơ chế cập nhật khi HR/IGA thay đổi trong chiến dịch.

**Snapshot không phải sự thật vĩnh viễn.** Quyền tại target có thể đổi sau khi xuất dữ liệu. Trước khi thu hồi, cần revalidate target và không để kết luận trên snapshot cũ gây thay đổi sai người.

## 11. Dữ liệu tối thiểu của một review item

Một item tái xác nhận nên có đủ ngữ cảnh:

| Trường | Ví dụ | Vì sao cần? |
| --- | --- | --- |
| **identityId** | iam-482 | Liên kết danh tính quản trị |
| **employmentRelationId** | emp-org-a-01 | Gắn đúng quan hệ làm việc |
| **targetSystem/tenant** | reports-saas/org-a | Không nhầm phạm vi |
| **targetAccountId** | user-8f9e2c | Khóa tại hệ thống đích |
| **entitlementId** | reports.admin.v2 | Định danh kỹ thuật ổn định |
| **resourceScope** | project-atlas | Phạm vi tài nguyên |
| **grantPath** | direct-role, group nesting, ACL | Biết quyền có từ đâu |
| **businessDescription** | Quản trị báo cáo Atlas | Reviewer hiểu tác động |
| **riskTier** | HIGH | Ưu tiên rà soát |
| **sourceApproval** | ar-2026-1042 | Bằng chứng cấp ban đầu |
| **lastUsedAt/coverage** | Không thấy / log bao phủ 60 ngày | Tín hiệu sử dụng kèm giới hạn |
| **expectedAccessStatus** | DENY sau Mover | Căn cứ nghi ngờ quyền thừa |
| **reviewerId/authority** | atlas-resource-owner | Người đủ thẩm quyền |
| **snapshotVersion** | campaign-2026-q4-v1 | Chống quyết định trên dữ liệu không nhất quán |
| **decision/status** | PENDING, REVOKE... | Theo dõi xử lý |

Nếu reviewer chỉ thấy **roleId = x3-a17** mà không có mô tả quyền thực tế, họ có thể bấm Keep để tránh làm hỏng ứng dụng. Cần có **diễn giải permission, resource scope, nguồn grant và bối cảnh công việc**.

## 12. Identity correlation: không xác nhận quyền cho sai người

Trong IAM, thường có các thực thể khác nhau:

- **Person:** con người được xác minh.
- **Employment/worker relation:** quan hệ lao động hoặc bảo trợ cụ thể.
- **IAM identity:** danh tính số do tổ chức quản trị.
- **IdP subject:** định danh SSO của issuer nhất định.
- **Application account:** user record/role tại SaaS hay hệ thống nội bộ.
- **Workload identity:** danh tính máy, có service owner và mục đích riêng.

Không dùng **email, tên hiển thị hoặc username** làm bằng chứng duy nhất để ghép tài khoản: email có thể thay đổi/tái sử dụng, còn username có thể trùng ở các tenant. Với **OIDC**, cần xét **issuer + subject**. Với **SCIM**, **id do Service Provider cấp** khác **externalId do client quản lý**; ánh xạ phải có namespace và target rõ.

Nếu có nhiều account ứng viên, đừng gửi một danh sách mơ hồ rồi buộc manager tự đoán. Item nên được đưa vào **UNVERIFIED_ACCOUNT_LINK** và giao xử lý tương quan danh tính trước khi xác nhận/thu hồi.

Một người có thể có **nhiều employment hợp lệ**. Khi org-a chấm dứt hợp đồng nhưng org-b vẫn đang có quan hệ hợp lệ, không được tự thu hồi tất cả quyền thuộc org-b chỉ vì person xuất hiện trong danh sách Leaver của org-a.

## 13. Đánh giá entitlement thực tế, không chỉ tên role

Một role có thể mang nhiều quyền và thay đổi theo phiên bản:

~~~text
Role: ProjectEditor
  -> App role: DataEditor
     -> READ_REPORT
     -> UPDATE_REPORT
     -> EXPORT_REPORT
  -> Nested group: organization-collaborators
     -> READ_OTHER_PROJECTS
~~~

Nếu review chỉ hiển thị **ProjectEditor**, reviewer có thể không biết role còn cho **EXPORT** hoặc đọc dự án khác. Cần tính **effective permission expansion** khi vai trò, nhóm lồng nhau, ACL trực tiếp và ownership kết hợp.

Các nguồn quyền thường cần xét:

| Đường cấp quyền | Sai lệch cần tìm |
| --- | --- |
| IdP group | User còn trong nhóm công việc cũ |
| SCIM Group.members | SaaS chưa gỡ membership |
| Application local role | Grant thủ công ngoài IGA |
| Direct ACL/share | Quyền của người đã chuyển dự án vẫn còn |
| Nested/derived role | Role thấp kéo theo quyền quá rộng |
| Cloud IAM role/resource policy | Quyền wildcard hoặc trust chéo tài khoản |
| OAuth client grant/PAT | API vẫn chấp nhận token ngoài SSO |
| Ownership/delegation | Người cũ vẫn được quản trị tài nguyên |

**Một group đã được xác nhận hợp lệ không chứng minh mọi quyền phát sinh đều hợp lệ**. Nếu ứng dụng thay đổi mapping role, có thể cần chiến dịch **role/entitlement certification** bổ sung.

## 14. Quy trình Recertification từ đầu đến cuối

~~~mermaid
flowchart TD
    A["Xác định campaign và risk scope"] --> B["Thu thập target access và HR/IGA context"]
    B --> C["Identity correlation, chuẩn hóa, snapshot"]
    C --> D["Phân reviewer có thẩm quyền"]
    D --> E["Reviewer xem entitlement và evidence"]
    E --> F{"Quyết định?"}
    F -->|"KEEP"| G["Ghi căn cứ giữ và kỳ review tiếp theo"]
    F -->|"REVOKE"| H["Tạo remediation thu hồi"]
    F -->|"MODIFY"| I["Thu hẹp scope / role / thời hạn"]
    F -->|"EXCEPTION"| J["Approval ngoại lệ có hạn và owner"]
    F -->|"NEEDS_INFO"| K["Bổ sung nguồn dữ liệu, chưa đóng"]
    H --> L["Thực thi tại IdP/SCIM/SaaS/API"]
    I --> L
    J --> M["Ghi ngoại lệ, lịch hết hạn và kiểm soát bù"]
    G --> N["Kiểm tra quyết định hợp lệ theo policy"]
    M --> N
    K --> E
    L --> O["Readback và kiểm thử effective access"]
    O --> P{"Đạt trạng thái cần thiết?"}
    P -->|"Có"| N
    P -->|"Không / UNKNOWN"| Q["Exception có owner, deadline, rủi ro"]
    Q --> O
    N --> R["Audit, KPI, đóng item/campaign phù hợp"]
~~~

Sơ đồ cho thấy recertification **không kết thúc tại nút Revoke**. Một quyết định thu hồi còn cần triển khai và kiểm chứng; một quyết định Keep vẫn cần có căn cứ, reviewer hợp lệ và không vi phạm hard deny.

## 15. Các quyết định nên cho phép reviewer đưa ra

| Decision | Khi nào chọn? | Hệ quả mong muốn |
| --- | --- | --- |
| **KEEP/ATTEST** | Quyền vẫn cần và phù hợp phạm vi, thời hạn | Ghi căn cứ, giữ theo chính sách |
| **REVOKE** | Quyền không còn cần, không có approval hợp lệ | Chuyển sang deprovisioning và readback |
| **MODIFY/REDUCE** | Quyền cần nhưng quá rộng về action/resource/duration | Thu hẹp role, ACL hoặc thời hạn |
| **REASSIGN_OWNER** | Workload/tài nguyên vẫn cần nhưng owner không còn đúng | Chuyển owner theo phê duyệt |
| **APPROVED_EXCEPTION** | Có căn cứ giữ khác baseline, được chủ thể có thẩm quyền phê duyệt | Gắn scope, expiry và kiểm soát bù |
| **NEEDS_MORE_INFO** | Thiếu dữ liệu, role mơ hồ, mapping không chắc chắn | Bổ sung bằng chứng, không coi là Keep |
| **ESCALATE** | Reviewer không có quyền quyết định hoặc vướng SoD | Chuyển tới đúng owner |

Một số sản phẩm chỉ hỗ trợ **Approve/Reject**. Trong trường hợp đó, tổ chức vẫn cần thiết kế workflow để biến **Reject** thành **removal task**, **Approve** thành **attestation record**, và quản lý **modify/exception** bên ngoài hoặc qua luồng liên quan. Không được để nút Approve trở thành gia hạn vô thời hạn nếu chính sách yêu cầu giới hạn thời gian.

## 16. Recertification không phải bỏ phiếu đa số

Quyền truy cập được xác nhận dựa trên **thẩm quyền và chính sách**, không chỉ vì có nhiều người bấm Keep.

Ví dụ:

- Manager xác nhận Lan cần làm việc ở Dự án Atlas.
- Data owner quyết định Lan có được **EXPORT báo cáo mật** không.
- Security owner kiểm tra role Admin có vi phạm **SoD** không.

Nếu policy yêu cầu cả data owner và security owner, một manager bấm Keep không đủ để duy trì quyền Exporter. Nếu một reviewer không có thẩm quyền ở tenant đích, quyết định phải được **REASSIGN/ESCALATE**, không được hợp thức hóa bằng số lượng approval.

**Phân tách nhiệm vụ (Separation of Duties — SoD)** cũng có thể buộc người xác nhận khác beneficiary, người cấp quyền hoặc người tạo yêu cầu. Ngoại lệ SoD cần có cơ chế độc lập và giới hạn.

## 17. Không thấy sử dụng không tự chứng minh quyền thừa

**Last used** là dữ liệu hữu ích nhưng thường không đầy đủ.

| Quan sát | Có thể giải thích thế nào? | Cần làm gì? |
| --- | --- | --- |
| Role Admin không dùng 90 ngày | Không còn cần hoặc chỉ dùng khi incident | Hỏi owner, xem khả năng JIT/PAM |
| Không có log API action | API chưa ghi loại sự kiện đó | Kiểm tra log coverage |
| Quyền Export chỉ dùng cuối quý | Cửa sổ 30 ngày bỏ sót chu kỳ | Xem lịch nhiệm vụ |
| Workload DR chưa từng chạy | Đường dự phòng được giữ đúng chính sách | Xác nhận owner, diễn tập, hạn và phạm vi |
| Quyền được dùng thường xuyên | Có thể hợp lệ hoặc vẫn quá rộng | So với nhiệm vụ và phê duyệt, không chỉ tần suất |

**Usage-based analytics tạo tín hiệu review**, không thay owner approval. Nên ghi **cửa sổ quan sát, nguồn log, tỷ lệ endpoint bao phủ và tình trạng retention**; nếu không có dữ liệu thì hiển thị **UNKNOWN**, không hiển thị “Never used” như sự thật đã xác minh.

## 18. Chú ý quyền đặc quyền và vi phạm SoD

Những đối tượng cần ưu tiên:

- **Global/cloud/organization admin** hoặc quyền sửa policy IAM.
- **Secret-reader**, quyền tạo credential hoặc quản lý khóa mã hóa.
- **Production deployer**, database superuser, cluster-admin.
- Quyền **tạo và phê duyệt cùng một giao dịch**.
- Quyền **tạo account và cấp đặc quyền** cho account đó.
- **Break-glass** và quyền tạm thời không có expiry.
- Quyền **cross-tenant** hoặc rộng theo wildcard.

Review cần phân biệt:

| Kiểm soát | Câu hỏi |
| --- | --- |
| **Least privilege** | Có thể giảm role thành tập action/resource hẹp hơn không? |
| **SoD tĩnh** | Người đó có đang giữ hai role không được kết hợp không? |
| **SoD động** | Workflow có ngăn tự phê duyệt giao dịch của mình không? |
| **PAM/JIT** | Có cần giữ quyền Admin thường trực hay có thể cấp khi cần? |
| **Step-up/MFA** | Hành động nhạy cảm có yêu cầu mức xác thực đủ mạnh không? |
| **Audit** | Mọi lần dùng đặc quyền có được ghi và review không? |

**Không tự động xóa một tài khoản break-glass đang cần cho phục hồi**, nhưng cũng không được coi nhãn break-glass là giấy phép giữ mọi đặc quyền mãi mãi. Cần owner, phương thức bảo quản, kiểm tra định kỳ, giới hạn sử dụng và báo động.

## 19. Recertification trong Joiner lifecycle

**Joiner** cần xác minh danh tính từ HRIS/nguồn bảo trợ, tạo account và cấp baseline theo job/organization. Recertification có thể được dùng để kiểm tra chất lượng sau onboarding hoặc khi lần đầu bước vào campaign.

Ví dụ:

1. HRIS xác nhận nhân viên mới thuộc Finance, project Atlas và start date.
2. IAM cấp role ReportViewer theo baseline đã duyệt.
3. Manager yêu cầu thêm ReportEditor; resource owner phê duyệt.
4. SCIM/API provisioning tạo account, group và role ở SaaS.
5. Chiến dịch review phát hiện user còn role **OrganizationAdmin** do cấu hình mặc định.
6. Reviewer xác định admin không thuộc nhiệm vụ, chọn **REVOKE**, sau đó IAM xác minh tại target.

**Recertification không thay việc kiểm tra Joiner ngay thời điểm cấp**. Không nên để quyền admin sai tồn tại nhiều tháng chờ đợt review đầu tiên.

Để tránh lỗi ngay từ đầu, quyền baseline phải được quản lý bằng **role catalog, approval, least privilege và readback**, còn recertification là **lớp xác nhận bổ sung**.

## 20. Recertification trong Mover lifecycle

**Mover** là điểm phát sinh quyền tích lũy phổ biến: thêm quyền mới nhưng không thu hồi quyền cũ.

Ví dụ Lan chuyển từ Atlas sang Nova:

| Quyền | Trước Mover | Sau Mover mong muốn | Phát hiện review |
| --- | --- | --- | --- |
| Atlas RepositoryAdmin | Có | Không | Vẫn có direct role |
| Atlas ReportReader | Có | Không | Vẫn còn trong nested group |
| Nova ReportReader | Chưa có | Có nếu được duyệt | Đã cấp thành công |
| Nova Admin | Không | Không | Không được tự thêm |

Recertification theo sự kiện nên:

1. Lấy **nguồn assignment, effectiveAt và sourceVersion** đúng.
2. Tính lại **expected access toàn phần**, không chỉ những quyền cần thêm.
3. Hiển thị các quyền cũ cho reviewer có hiểu biết về project/ứng dụng.
4. Phân biệt **quyền bàn giao có hạn** với quyền đã hết căn cứ.
5. Chuyển **REVOKE/REDUCE** cho những quyền tồn dư; xét token/ACL liên quan.
6. Kiểm thử **Atlas = DENY** và **Nova = ALLOW** cho các thao tác phù hợp.

Một ngoại lệ bàn giao cần **approval, phạm vi, owner và expiresAt**. Reviewer không nên chỉ chọn Keep rồi để role admin cũ tồn tại vô thời hạn.

## 21. Recertification trong Leaver lifecycle

**Leaver** yêu cầu rút quyền theo mốc quan hệ làm việc, không chờ kết quả campaign. Recertification hỗ trợ **xác minh độ đầy đủ sau deprovisioning** hoặc phát hiện quyền còn sót trong hệ thống không được tự động hóa.

Các điểm kiểm tra:

- Account IdP/SSO không còn cho xác thực theo chính sách.
- SCIM User/Group và role tại ứng dụng đích được cập nhật đúng.
- **Local account**, direct ACL, ownership và delegated access được xử lý.
- Session, refresh token, access token JWT, PAT/API key được thu hồi hoặc chặn theo cơ chế của từng sản phẩm.
- Những job Joiner/Mover retry cũ không **tái cấp quyền** sau khi đã Leaver.
- Dữ liệu audit cho phép chứng minh **thời điểm quyền thực tế bị chặn**.

**Disabled account ở IdP không đủ chứng minh mọi token và ứng dụng đã bị khóa**. Với JWT tự chứa, API có thể tiếp tục nhận token trước hạn nếu không có denylist, introspection, security epoch hoặc recheck phù hợp.

Nếu person có một employment hợp lệ tại org-b nhưng đã hết quan hệ org-a, cần **thu hồi đúng quyền org-a**. Không áp dụng trạng thái Leaver của một quan hệ để xóa nhầm quyền độc lập tại tổ chức khác.

## 22. Nhà thầu, đối tác và guest access

Tài khoản ngoài tổ chức có thể không tồn tại trong HRIS nhân viên. Nguồn có thẩm quyền có thể là **vendor management**, hệ thống quản lý hợp đồng hoặc **sponsor registry**.

Review cần xác nhận:

| Thuộc tính | Câu hỏi |
| --- | --- |
| **Sponsor** | Người chịu trách nhiệm còn làm việc và còn quyền bảo trợ không? |
| **Contract/end date** | Quan hệ hợp tác còn hiệu lực và đúng dự án không? |
| **Target tenant** | Đối tác được vào tổ chức hoặc workspace nào? |
| **Entitlement** | Chỉ đọc hay có quyền xuất/sửa/chia sẻ? |
| **Authentication** | SSO/federation/MFA đáp ứng chính sách không? |
| **Owner/expiry** | Ai xác nhận và khi nào phải thu hồi? |
| **External sharing** | Có direct ACL/file link nằm ngoài group chính không? |

Một guest không đăng nhập trong ba tháng chưa chắc không còn nhiệm vụ, nhưng **sponsor hết hiệu lực hoặc hợp đồng đã hết** là tín hiệu mạnh để thu hồi theo quy trình. Không gia hạn chỉ vì requester cũ vẫn có email hợp lệ.

## 23. Service account và workload identity

**Workload identity** gồm service account, CI/CD job, bot, managed identity hoặc OAuth client credentials. Chúng có vòng đời và nguồn thẩm quyền khác nhân viên.

Một chiến dịch cần thu thập:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **serviceId/workloadId** | Danh tính máy ổn định |
| **ownerTeam / technicalOwner** | Đơn vị chịu trách nhiệm |
| **businessPurpose** | Nhiệm vụ của service |
| **environment** | dev, staging, production |
| **targetResources/permissions** | Những tài nguyên và action được phép |
| **OAuth scopes/audience** | Khả năng token cho API đích |
| **credentialType/expiry** | Secret, certificate, federation, token |
| **lastActivity/coverage** | Tín hiệu dùng trong các kỳ vận hành |
| **lifecycleStatus** | ACTIVE, SUSPENDED, DECOMMISSIONED |
| **privilegeApproval** | Căn cứ cho quyền đặc biệt |

Nếu owner của một bot production đã Leaver, **không nhất thiết xóa bot đang vận hành hợp lệ**. Cần chuyển owner, đánh giá scope, secret mà người cũ có thể đã biết, và thu hồi PAT cá nhân. Một workload không có owner là phát hiện cần xử lý, không phải trường hợp tự động Keep.

**Không áp dụng MFA push của con người cho mọi lệnh máy–máy**. Bảo vệ workload bằng cơ chế phù hợp như workload federation, managed identity, certificate/secret quản lý an toàn, token ngắn hạn, least privilege và owner review.

## 24. OAuth/OIDC, IdP, SSO và SCIM liên quan ra sao?

Trong recertification, mỗi thành phần đóng một vai trò khác nhau:

| Thành phần | Vai trò | Giới hạn cần nhớ |
| --- | --- | --- |
| **HRIS/sponsor** | Căn cứ về quan hệ, start/end date, tổ chức | Không phản ánh mọi role target |
| **IAM/IGA** | Role catalog, campaign, approval và expected access | Approval không chứng minh target đã áp dụng |
| **IdP/SSO** | Danh tính đăng nhập, group, phiên và authenticator | Đăng nhập thành công không chứng minh entitlement |
| **OIDC** | Kết quả xác thực và một số claims theo contract | ID token không dùng thay access token tại API |
| **OAuth 2.0** | Token, scope, grant và audience cho API | Scope read không tự cho quyền đọc mọi tenant |
| **SCIM** | Provision/deprovision User/Group tại SP | Không bảo đảm mọi local ACL/token mất hiệu lực |
| **RBAC/ABAC/PBAC** | Chính sách role và điều kiện phân quyền | Quyền gán khác với quyền thực tế được ALLOW |
| **PDP/PEP/resource server** | Quyết định và thực thi authorization | Cần policy/attribute đủ mới |

Ví dụ, IGA quyết định **Revoke** role Editor. Connector gỡ Group qua SCIM, nhưng ứng dụng còn **direct role Editor** hoặc JWT cũ chứa claim quyền. Campaign chưa nên được ghi là hoàn tất kỹ thuật nếu hệ thống vẫn **ALLOW EDIT** trái chính sách.

## 25. Quyết định Keep: giữ quyền cũng cần bằng chứng

Một reviewer chọn **KEEP** nên có căn cứ đủ rõ:

1. Chủ thể và account đã được xác minh.
2. Quan hệ công việc hoặc sponsor vẫn hợp lệ.
3. Role, action và tài nguyên đúng với nhiệm vụ hiện tại.
4. Phạm vi tổ chức/tenant không vượt approval.
5. Không có SoD conflict hoặc hard deny chưa được giải quyết.
6. Nếu là đặc quyền, vẫn đáp ứng quy tắc PAM/JIT/MFA/expiry.
7. Mốc review tiếp theo hoặc thời hạn quyền được xác định theo policy.

**Keep không nhất thiết gia hạn expiresAt.** Nếu một entitlement có hạn đến ngày 31/12, reviewer chọn Keep ngày 01/12 không có nghĩa tự kéo dài tới năm sau. Gia hạn thời hạn là **quyết định riêng**, phải có policy và phê duyệt phù hợp.

Nếu quyền vừa bị bộ phận bảo mật đưa vào **emergency deny** hoặc employment đã TERMINATED, quyết định Keep cũ không được ghi đè trạng thái mới.

## 26. Quyết định Revoke hoặc Modify: phải thực thi đúng nguồn quyền

Khi reviewer chọn thu hồi hoặc thu hẹp, hệ thống cần xác định **đường cấp quyền thực tế**:

- Gỡ **IdP group** nếu group là nguồn cấp.
- Gỡ **SCIM Group.members** hoặc role tại SaaS theo contract.
- Xóa **direct ACL/share** khi quyền nằm ở tài nguyên.
- Giảm **cloud IAM policy**, resource policy hoặc role binding có phạm vi rộng.
- Hủy/thu hồi **OAuth grant, PAT, API key** hoặc phiên liên quan khi cần chặn hiệu lực.
- Đổi owner/delegate của workload hoặc tài nguyên trước khi xóa account liên quan.

Nếu chỉ gỡ một group nhưng quyền vẫn được cấp qua role khác, **effective access có thể không đổi**. Kết quả cần được xác minh bằng readback và policy/API test.

### Lưu ý về ảnh hưởng nghiệp vụ

Việc thu hồi một quyền có thể làm gián đoạn batch job, đóng sổ cuối kỳ hoặc xử lý sự cố. Trước những quyền có rủi ro vận hành cao, cần đánh giá tác động và chuẩn bị phương án thay thế ít quyền hơn, ví dụ **JIT/PAM**.

Tuy nhiên, **nguy cơ gián đoạn không phải lý do tự giữ quyền vượt chính sách vô thời hạn**. Với quyền trái policy có rủi ro cao, có thể cần chặn khẩn theo playbook đã được ủy quyền.

## 27. Không phản hồi review đúng hạn thì sao?

**Reviewer timeout** là vấn đề vận hành, không phải phê duyệt ngầm. Quy trình có thể:

1. Gửi reminder trước deadline.
2. Escalate tới owner có thẩm quyền hoặc delegate hợp lệ.
3. Kiểm tra người duyệt còn ACTIVE, còn quyền với tenant và không vi phạm SoD.
4. Đặt overall deadline và số lần escalation tối đa.
5. Theo risk policy, đưa item vào **OVERDUE/NEEDS_REVIEW** hoặc thực hiện **biện pháp an toàn đã được phê duyệt trước** cho một số quyền.
6. Ghi đầy đủ nguồn quyết định và người chịu trách nhiệm.

**Không tự coi sự im lặng là Keep**. Mặt khác, cũng không mặc định tự xóa toàn bộ tài khoản thiết yếu chỉ vì người duyệt nghỉ phép: những trường hợp có tác động vận hành cần dùng chính sách dự phòng rõ, phù hợp mức rủi ro.

Với quyền đặc quyền không có căn cứ, chính sách có thể yêu cầu **tạm đình chỉ/hạn chế** sau deadline; hành vi phải được phê duyệt từ trước, có audit và phương án phục hồi hợp lệ.

## 28. Quyết định đến muộn và race condition

Ví dụ:

~~~text
09:00  Reviewer chọn REVOKE AtlasAdmin trên snapshot v12
09:01  Hệ thống dự án xác nhận Lan chuyển sang Nova
09:02  IAM đã tự thu hồi role AtlasAdmin
09:03  Quy trình manual cấp lại role AtlasAdmin vì một ngoại lệ cũ
09:04  Worker recertification bắt đầu xử lý decision từ v12
~~~

Nếu chỉ chạy lệnh gỡ theo tên role không có kiểm soát, hệ thống có thể ghi sai trạng thái hoặc xóa nhầm quyền được cấp bởi một nguồn mới. Các nguyên tắc:

- Review item phải gắn **snapshotVersion, entitlement/grantId, targetTenant, roleVersion và decisionVersion**.
- Trước remediation, kiểm tra **state hiện hành** và **source of grant**.
- **Idempotency**: retry không làm mất thông tin hoặc thực hiện ngoài phạm vi.
- Sự kiện **Mover/Leaver mới hơn** không bị decision Keep cũ ghi đè.
- Nếu role đã đổi ý nghĩa/permission, cần **re-review** thay vì tự giữ theo tên cũ.
- Khi kết quả không rõ do timeout, **readback** target trước khi retry.

Không có giao dịch nguyên tử chung giữa HRIS, IGA, IdP, SCIM và mọi SaaS. Cần kiểm soát **eventual consistency và reconciliation** thay vì giả định tất cả thay đổi xảy ra cùng một lúc.

## 29. State machine của một review item

Một item nên có trạng thái quyết định và trạng thái thực thi **tách biệt**.

~~~mermaid
stateDiagram-v2
    [*] --> PREPARED
    PREPARED --> PENDING_REVIEW: Campaign phát hành
    PENDING_REVIEW --> NEEDS_INFO: Thiếu căn cứ
    NEEDS_INFO --> PENDING_REVIEW: Đã bổ sung dữ liệu
    PENDING_REVIEW --> OVERDUE: Quá hạn
    OVERDUE --> PENDING_REVIEW: Escalate / assign reviewer hợp lệ
    PENDING_REVIEW --> ATTESTED_KEEP: Quyết định KEEP hợp lệ
    PENDING_REVIEW --> DECIDED_REVOKE: Quyết định REVOKE
    PENDING_REVIEW --> DECIDED_MODIFY: Quyết định MODIFY
    PENDING_REVIEW --> APPROVED_EXCEPTION: Ngoại lệ có hạn
    DECIDED_REVOKE --> REMEDIATION_PENDING
    DECIDED_MODIFY --> REMEDIATION_PENDING
    REMEDIATION_PENDING --> REMEDIATION_UNVERIFIED: Đã gửi thay đổi
    REMEDIATION_UNVERIFIED --> VERIFIED_CLOSED: Readback đạt
    REMEDIATION_UNVERIFIED --> BLOCKED: Không thể xác minh
    BLOCKED --> REMEDIATION_UNVERIFIED: Khắc phục tiếp
    ATTESTED_KEEP --> VERIFIED_CLOSED: Bằng chứng/quy tắc đạt
    APPROVED_EXCEPTION --> VERIFIED_CLOSED: Ghi ngoại lệ và lịch expiry
    VERIFIED_CLOSED --> [*]
~~~

Sơ đồ minh họa. Trong triển khai thực tế, **KEEP/EXCEPTION** có thể không cần một tác vụ provisioning; **REVOKE/MODIFY** gần như luôn cần theo dõi kết quả thực thi. Campaign cũng có thể được đánh dấu **PARTIAL** nếu một số target chưa có bằng chứng, không tuyên bố tất cả item đã verified.

## 30. Mã giả xử lý một quyết định Recertification

Mã giả dưới đây minh họa **nghiệp vụ**, không phải SDK của một IGA cụ thể:

~~~text
submitRecertificationDecision(itemId, reviewer, decision, expectedVersion):
    item = loadItemWithConcurrencyControl(itemId, expectedVersion)
    campaign = loadCurrentCampaign(item.campaignId)

    if item.state not in [PENDING_REVIEW, ESCALATED_REVIEW]:
        return CONFLICT_STALE_ITEM

    if not reviewer.isAuthenticatedWithRequiredAssurance():
        return REQUIRE_AUTHENTICATION_OR_STEP_UP

    if not reviewer.hasAuthorityFor(item.role, item.resourceScope,
                                     item.targetTenant):
        return FORBIDDEN

    if violatesSoD(reviewer, item.beneficiary, item.grant):
        return FORBIDDEN_SOD

    if item.identityLink.isAmbiguous or item.targetGrant.isUnverified:
        return NEEDS_EVIDENCE

    currentState = loadCurrentIdentityAndGrantVersion(item)
    if currentState.isMateriallyDifferentFrom(item.snapshot):
        return REVALIDATION_REQUIRED

    if decision == KEEP:
        requireJustificationWhenPolicyRequires(item, reviewer)
        requireNoCurrentHardDeny(item.beneficiary, item.grant)
        recordAttestation(item, reviewer)
        return ATTESTED_KEEP

    if decision == REVOKE or decision == MODIFY:
        recordDecisionWithSourceAndScope(item, reviewer, decision)
        enqueueIdempotentRemediation(item, decision)
        return REMEDIATION_PENDING

    if decision == APPROVED_EXCEPTION:
        requireIndependentExceptionApprovalAndExpiry(item)
        recordLimitedException(item)
        return APPROVED_EXCEPTION

    return NEEDS_MORE_INFORMATION
~~~

Trước khi chạy job thu hồi ở target, worker phải **revalidate employment, grant source, tenant và phiên bản hiện hành**. Sau khi thay đổi, phải **readback**. Không gọi **COMPLETED** chỉ vì queue đã nhận một remediation event.

## 31. Mã giả đối soát sau quyết định thu hồi

~~~text
verifyRevocation(remediationId):
    job = getRemediation(remediationId)
    expected = calculateCurrentExpectedAccess(job.identity, job.target)
    observed = readTargetAccountsGrantsACLsAndTokens(job.target)

    if observed.isUnavailable:
        return UNVERIFIED_WITH_OWNER_AND_DEADLINE

    if expected.identityLinkIsAmbiguous:
        return MANUAL_IDENTITY_INVESTIGATION

    if observed.stillHasEffectiveAccess(
        job.subject, job.action, job.resource, job.tenant
    ):
        return REMEDIATION_NOT_COMPLETE

    if expected.otherNecessaryAccessLost:
        return BUSINESS_IMPACT_REVIEW

    recordVerifiedAtAndEvidence(job, observed)
    return VERIFIED_CLOSED
~~~

Một API kiểm tra quyền **DENY tại một thời điểm** không chứng minh tất cả đường truy cập đều bị chặn. Với quyền rủi ro cao, có thể cần kiểm tra nhiều endpoint, session/token, direct ACL và đường tài khoản cục bộ.

Nếu hệ thống không cung cấp cách đọc trạng thái token/PAT, ghi **UNKNOWN** và có kế hoạch kiểm chứng được phê duyệt, không tự suy quyền đã thu hồi.

## 32. Ví dụ bản ghi một review item

Ví dụ JSON sau là **dữ liệu thiết kế nội bộ minh họa**, không phải schema của SCIM hoặc chuẩn OIDC:

~~~json
{
  "campaignId": "recert-2026-q4-highrisk",
  "reviewItemId": "recert-item-0082",
  "beneficiaryIdentityId": "iam-482",
  "employmentRelationId": "emp-org-a-01",
  "targetSystem": "code-hosting-saas",
  "targetTenant": "org-a",
  "targetAccountId": "saas-user-482",
  "entitlementId": "repository.admin",
  "resourceScope": "project-atlas",
  "grantSource": "direct-application-role",
  "entitlementSnapshotVersion": "target-v21",
  "sourceApprovalId": "access-req-119",
  "currentExpectedDecision": "DENY",
  "riskTier": "HIGH",
  "usageWindowDays": 90,
  "usageCoverage": "PARTIAL",
  "reviewerId": "atlas-repository-owner",
  "decision": "REVOKE",
  "decisionAt": "2026-11-23T09:50:00+07:00",
  "decisionReason": "EMPLOYEE_MOVED_TO_NOVA",
  "remediationStatus": "PENDING",
  "verifiedEffectiveAccess": "UNKNOWN",
  "verifiedAt": null
}
~~~

**UNKNOWN** có ý nghĩa riêng với **DENY**: chưa có bằng chứng kỹ thuật đủ. Đặt verifiedAt = null khi chưa đọc lại không phải là xác nhận đã hoàn thành.

## 33. Kiểm toán của Recertification cần chứng minh gì?

Những câu hỏi kiểm toán:

1. **Chiến dịch nào**, phạm vi là gì, gồm và loại trừ những hệ thống nào?
2. **Danh tính, tài khoản, role, grant, tenant và tài nguyên** được xác định bằng khóa nào?
3. **Snapshot** được chụp khi nào, từ nguồn nào, có đầy đủ không?
4. **Ai là reviewer** và tại thời điểm quyết định họ có đủ thẩm quyền không?
5. **Quyết định gì**: Keep, Revoke, Modify, Exception, Needs Info?
6. **Vì sao** reviewer quyết định như vậy; có bằng chứng công việc/approval nào?
7. Có **SoD, self-review, role conflict hoặc hard deny** cần xử lý không?
8. Khi phải sửa quyền, **ai/connector nào** thực thi, ở hệ thống nào và khi nào?
9. **Quyền đã thực sự thay đổi chưa**, bằng readback nào và còn token/ACL khác không?
10. **Ngoại lệ, quá hạn, sự cố và giới hạn phạm vi** được báo cáo và theo dõi ra sao?

Không ghi **password, bearer token, refresh token, private key, OTP seed hoặc nguyên bản hồ sơ HR** trong audit. Những thông tin về role, nhóm nhạy cảm, dự án và organization cũng cần **tối thiểu hóa, phân quyền xem và chính sách lưu giữ**.

Một record chứng minh manager đã bấm Revoke **không tương đương** record chứng minh target đã thực thi Deny. Hai loại bằng chứng phải được liên kết nhưng giữ ý nghĩa riêng.

## 34. KPI và hiệu quả chương trình tái xác nhận

| KPI | Mục đích | Lưu ý diễn giải |
| --- | --- | --- |
| **Campaign coverage** | Phần hệ thống/quyền trong phạm vi được review | Cần ghi rõ hệ thống bị loại trừ |
| **On-time review rate** | Reviewer quyết định trước dueAt | Không thưởng cho việc bấm Keep hàng loạt |
| **Revocation decision rate** | Tỷ lệ item được chọn Revoke | Nhiều revoke không nhất thiết là chương trình tốt hơn |
| **Modification/reduction rate** | Quyền đã được thu hẹp | Cần kiểm tra effective scope |
| **Unverified entitlement ratio** | Những quyền không thể tính/readback | Không coi UNKNOWN là an toàn |
| **Time to verified removal** | Từ quyết định Revoke đến khi target Deny | Theo hệ thống và risk tier |
| **Overdue review items** | Công việc review chưa hoàn tất đúng hạn | Có owner và escalation |
| **Reviewer override/exception rate** | Quyền ngoài baseline được giữ | Kiểm tra scope, expiry và phê duyệt |
| **SoD conflicts found/resolved** | Tìm và xử lý quyền xung đột | Phân biệt exception hợp lệ |
| **Mover residual privileges** | Quyền cũ còn sau thay đổi vai trò | Gắn với effectiveAt |
| **Leaver residual access** | Quyền còn có thể dùng sau mốc cắt | Không chờ campaign, cần ưu tiên cao |
| **Ownerless workload identities** | Bot/service không có owner rõ | Theo dõi chuyển owner và quyền |
| **Regrant after revoke** | Quyền bị cấp lại ngoài căn cứ | Xem policy/event retry/role mapping |

### Công thức ví dụ

~~~text
On-time review rate
  = Số item được reviewer hợp lệ quyết định trước dueAt
    / Số item thuộc kỳ và đến hạn phải review

Verified revocation completion rate
  = Số quyết định REVOKE đã có readback/effective DENY đạt yêu cầu
    / Tổng quyết định REVOKE cần thực thi trong phạm vi đo
~~~

Cần công bố quy tắc xử lý **cancelled items, duplicate grants, unavailable targets, exceptions và thời điểm snapshot**. Một campaign có tỷ lệ completed 100% trên giao diện không đủ nếu nhiều lệnh thu hồi đang **REMEDIATION_UNVERIFIED**.

## 35. Những lỗi phổ biến khiến Recertification không hiệu quả

| Anti-pattern | Hậu quả | Cải thiện |
| --- | --- | --- |
| Review chỉ có nút Keep All | Rubber-stamping, không xem từng quyền | Risk-based presentation, mô tả permission và justification |
| Chỉ xuất user list từ IdP | Bỏ sót local ACL, PAT, workload | Inventory đa nguồn và ghi giới hạn |
| Gửi role kỹ thuật không giải thích | Reviewer không biết quyền nào nguy hiểm | Catalog mô tả action/resource/effective rights |
| Manager tự review quyền admin của mình | Xung đột lợi ích | SoD và reviewer độc lập |
| Reviewer chọn Revoke là đóng item | Quyền ở target có thể vẫn ALLOW | Remediation + readback |
| Không có owner hoặc approver đã Leaver | Task kẹt vô thời hạn | Escalation/delegation có authority |
| Không phản hồi được hiểu là Keep | Quyền cũ tồn tại không cần xác nhận | Overdue policy, không auto-attest |
| Quyền ít dùng bị xóa hàng loạt | Gián đoạn batch/DR/cuối kỳ | Xem business cycle, impact và JIT |
| Chỉ so theo email | Liên kết nhầm người/account | Stable ID và identity correlation |
| Không version hóa snapshot | Quyết định cũ ghi đè sự kiện mới | Source version, compare-and-set, revalidation |
| Role tên Reader nhưng mapping đã tăng quyền | Duy trì quyền vượt dự kiến | Role/permission expansion review |
| Campaign chỉ chạy mỗi năm cho mọi quyền | Bỏ sót rủi ro cao giữa hai kỳ | Event-driven và risk-based cadence |

**Số lượng chứng nhận không phải chất lượng chứng nhận.** Tổ chức phải xem hiệu quả giảm quyền tồn dư và sự đầy đủ của bằng chứng, không chỉ số click hoặc số campaign đã đóng.

## 36. Kịch bản thực hành: recertification phát hiện quyền Atlas còn sau Mover

**Bối cảnh:** Kỹ sư Huy có vai trò RepositoryAdmin tại Atlas và một **Personal Access Token (PAT)** để xử lý sự cố. Huy chuyển sang Nova từ ngày 01/12/2026. IAM đã cấp quyền đọc Nova, nhưng dữ liệu kiểm kê sau Mover cho thấy:

| Nguồn | Quan sát |
| --- | --- |
| HRIS/project registry | Huy đã được phân công Nova |
| IGA expected access | Atlas DENY, Nova READ |
| IdP groups | AtlasAdmin đã được gỡ |
| SaaS local role | RepositoryAdmin Atlas vẫn còn |
| PAT | Có token với khả năng gọi API Atlas |
| API kiểm thử được phép | WRITE Atlas vẫn ALLOW |

### Bước 1 — Tạo review item

Campaign tạo item **RepositoryAdmin / Atlas / Huy**, gắn **employmentRelationId, targetAccountId, grantSource và riskTier**. Reviewer là người có thẩm quyền với repository Atlas, không phải chỉ dựa vào tên manager hiện tại.

### Bước 2 — Xem bằng chứng

Resource owner thấy rằng Huy không còn nhiệm vụ tại Atlas, không có ngoại lệ bàn giao còn hiệu lực, và quyền admin có thể quản lý access của người khác. **Last used** có thể thiếu vì PAT không được log đầy đủ, nhưng **expected DENY và effective ALLOW** đã là bằng chứng mạnh cần xử lý.

### Bước 3 — Ra quyết định

Reviewer chọn **REVOKE** role admin, ghi lý do **Mover sang Nova**. IAM tạo remediation riêng cho **direct role, PAT và những ACL/session liên quan**. Không xóa quyền hợp lệ ở Nova.

### Bước 4 — Thực thi

Connector/đội được ủy quyền thu hồi direct role ở SaaS, xử lý PAT theo sản phẩm và cập nhật dữ liệu nguồn để ngăn tái cấp quyền. Khi token đã phát hành còn được API chấp nhận, cần cơ chế chặn theo **resource server/token lifecycle**, không chỉ gỡ group IdP.

### Bước 5 — Xác minh

~~~text
Huy READ Nova repository      -> ALLOW nếu có entitlement hợp lệ
Huy WRITE Atlas repository    -> DENY
Huy MANAGE_ACCESS Atlas       -> DENY
Huy WRITE Nova repository     -> DENY nếu role chỉ đọc
PAT cũ gọi Atlas API          -> DENY hoặc bị thu hồi theo cơ chế target
~~~

Chỉ sau khi có **target readback và effective access test** đạt phạm vi kiểm tra thì item mới chuyển **VERIFIED_CLOSED**. Nếu SaaS không cung cấp trạng thái PAT hoặc connector lỗi, ghi **UNVERIFIED/BLOCKED** với owner và deadline.

### Biến thể: quyền Atlas được phép giữ để bàn giao

Nếu resource owner xác nhận Huy còn nhiệm vụ bàn giao trong ba ngày, có thể chọn **MODIFY/EXCEPTION** theo quy trình: chỉ giữ quyền READ cần thiết, gắn deadline, approver và kiểm soát bù. Không giữ RepositoryAdmin toàn dự án chỉ vì có từ “bàn giao” trong ghi chú.

## 37. Câu hỏi tự kiểm tra

**Câu 1: Recertification khác Access request ở điểm nào?**

**Trả lời:** Access request xin/cấp quyền mới; recertification kiểm tra **quyền đang tồn tại có còn hợp lệ** và yêu cầu giữ, sửa hoặc thu hồi khi cần.

**Câu 2: Reviewer chọn Revoke có nghĩa API lập tức Deny không?**

**Trả lời:** Không. Cần remediation ở target, xử lý các đường quyền khác và readback.

**Câu 3: Không thấy quyền được dùng trong 90 ngày có đủ để thu hồi ngay không?**

**Trả lời:** Không chỉ dựa vào absence of logs. Cần xem coverage, chu kỳ nhiệm vụ, owner và rủi ro; có thể chuyển sang JIT thay standing privilege.

**Câu 4: Người Leaver cần chờ recertification để khóa quyền không?**

**Trả lời:** Không. Deprovisioning bắt buộc phải theo sự kiện/mốc hiệu lực; recertification hỗ trợ kiểm tra quyền còn sót.

**Câu 5: Vì sao không chỉ review group ở IdP?**

**Trả lời:** Vì SaaS có thể có direct role, ACL, PAT, session, OAuth grant hoặc local account ngoài group IdP.

**Câu 6: Ai review service account khi người vận hành cũ đã nghỉ?**

**Trả lời:** Service/team owner hoặc người được ủy quyền mới; cần chuyển owner và xem secret/quyền. Không tự coi bot là Leaver chỉ vì người sở hữu nghỉ việc.

**Câu 7: Người có quyền org-b còn hợp lệ nhưng đã Leaver org-a thì sao?**

**Trả lời:** Tách theo employment/organization; thu hồi đúng quyền org-a và giữ quyền org-b nếu vẫn được phê duyệt.

**Câu 8: Một campaign có 100% reviewer đã click nhưng 20% Revoke chưa readback có hoàn tất không?**

**Trả lời:** Hoàn tất về **decision** có thể đạt, nhưng **remediation verification** chưa đạt. Phải phân biệt KPI và trạng thái campaign.

## 38. Checklist triển khai Recertification

| Câu hỏi | Bằng chứng hoặc kiểm soát cần có |
| --- | --- |
| Có phạm vi campaign và risk tier rõ? | Danh sách target, tenant, role, ứng dụng, ngoại lệ |
| Đã xác định nguồn có thẩm quyền? | HRIS/sponsor, IGA approval, app entitlement |
| Identity/account mapping đã xác minh? | Person/employment/identity/target ID, không chỉ email |
| Có tính đúng quyền thực tế? | Assigned, effective, ACL, group, token và resource scope |
| Reviewer có hiểu role/action/tài nguyên? | Role catalog, permission expansion, business description |
| Reviewer có thẩm quyền và độc lập? | Resource/data owner, SoD, delegation hợp lệ |
| Có lịch review theo rủi ro và sự kiện? | Periodic + Mover/project expiry + privileged alerts |
| Có phân biệt Keep/Revoke/Modify/Exception? | Decision semantics và workflow thực thi |
| Có giới hạn thời hạn và external identity? | Sponsor, employment, contract, expiresAt |
| Có cảnh báo absence-of-logs không đáng tin? | Observation window và coverage |
| Có kiểm tra quyền đặc quyền/SoD? | Admin, IAM roles, toxic combinations, PAM/JIT |
| Có quản lý workload và owner? | ServiceId, ownerTeam, secret, environment, grant |
| Có quy tắc khi reviewer timeout? | Reminder, escalation, not auto-keep |
| Có chống decision/event đến trễ? | Snapshot version, state/version, revalidation |
| Có remediation theo đúng nguồn quyền? | IdP/SCIM/SaaS/ACL/PAT/role mapping |
| Có readback và effective access tests? | ALLOW/DENY ở tài nguyên thực theo phạm vi |
| Joiner có quyền baseline đúng? | Không đợi campaign mới phát hiện admin mặc định |
| Mover có thu hồi quyền cũ? | Review event-driven và đối soát assignment |
| Leaver được chặn không chờ campaign? | Deprovisioning SLA, token/session/ACL residual checks |
| Có trạng thái UNKNOWN/BLOCKED và owner? | Không đánh dấu hoàn tất khi thiếu bằng chứng |
| Có audit và KPI riêng cho quyết định/thực thi? | Reviewer, lý do, snapshot, timestamp, verifiedAt |

## 39. Tổng kết

**Recertification** là quá trình **tái xác nhận những quyền truy cập đang tồn tại** còn phù hợp với nhiệm vụ, tài nguyên, chính sách, người chịu trách nhiệm và thời hạn. Nó khác **Access request** ở chỗ không khởi đầu từ nhu cầu xin quyền mới; khác **reconciliation** ở chỗ cần **quyết định quản trị có thẩm quyền**, không chỉ đối chiếu cấu hình; và khác **provisioning** ở chỗ lựa chọn Keep/Revoke chưa tự tạo ra thay đổi kỹ thuật.

Trong vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** cung cấp căn cứ quan hệ làm việc; **IAM/IGA** tổ chức campaign và quản trị approval; **IdP/SSO/MFA** xác thực danh tính; **SCIM** hỗ trợ quản lý User/Group; **RBAC/ABAC/PBAC** giới hạn quyền theo role và ngữ cảnh; còn **resource server/PEP** quyết định quyền có thể thực thi. **Service/workload accounts** có owner và credential riêng, cũng phải được rà soát.

Một chương trình recertification hiệu quả cần **scope đầy đủ, reviewer đúng thẩm quyền, quyết định có lý do, cadence theo rủi ro, không tự Keep do im lặng, remediation có kiểm soát và bằng chứng readback tại target**. Chỉ khi cả quyết định quản trị **và** trạng thái quyền thực tế được xác minh, tổ chức mới có thể chứng minh việc áp dụng **least privilege**, giảm quyền thừa và hạn chế **quyền truy cập tồn dư** một cách đáng tin cậy.
