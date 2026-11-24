# Role mapping

> **Chương:** Authorization boundary  
> **Module:** SECURITY_AUTHENTICATION_FUNDAMENTALS  
> **Trọng tâm:** Chuyển thông tin danh tính và membership từ identity provider thành role nội bộ có phạm vi rõ ràng, kiểm soát vòng đời quyền và giữ ranh giới giữa authentication với authorization.

## 1. Role mapping là gì?

**Role mapping (ánh xạ vai trò)** là quá trình chuyển các thuộc tính danh tính, nhóm hoặc entitlement từ một nguồn tin cậy thành role mà ứng dụng sử dụng để quyết định quyền. Nguồn có thể là identity provider (IdP), hệ thống quản lý nhân sự, thư mục doanh nghiệp hoặc một hệ thống cấp quyền nội bộ. Đích là role được định nghĩa theo nghiệp vụ của ứng dụng, chẳng hạn Viewer, SupportAgent, BillingOperator hoặc TenantAdmin.

Ví dụ, IdP xác thực nhân viên Minh và phát hành token có subject ổn định cùng nhóm finance-approvers. Ứng dụng thanh toán có role nội bộ PaymentApprover. Một quy tắc mapping đã được quản trị viên phê duyệt có thể ánh xạ nhóm này sang role đó trong Tenant A. Khi Minh truy cập khoản thanh toán, ứng dụng vẫn phải kiểm tra Minh có role trong đúng tenant, có quyền trên khoản thanh toán cụ thể và có đáp ứng yêu cầu phê duyệt bổ sung hay không.

Role mapping không phải là việc tin mọi claim có tên role trong token. Nó là một chính sách chuyển đổi có nguồn gốc, phạm vi, phiên bản, người quản trị và vòng đời rõ ràng. Nếu mapping sai, người dùng có thể được cấp quyền quá mức dù quá trình đăng nhập hoàn toàn hợp lệ.

### Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt identity claim, group membership, entitlement, role và permission.
- Thiết kế mapping từ IdP group/claim sang role ứng dụng.
- Ràng buộc role với issuer, subject, tenant và resource.
- Chọn mô hình RBAC phù hợp và tránh role explosion.
- Ngăn nâng quyền qua claim hoặc header do client tự gửi.
- Quản lý cấp, thay đổi, hết hạn và thu hồi role.
- Kiểm thử mapping, tenant isolation, default deny và separation of duties.

## 2. Identity claim, group, role và permission khác nhau thế nào?

Các khái niệm này liên quan nhưng không thể thay thế cho nhau.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Identity claim** | Thuộc tính được issuer khẳng định về một subject | Subject ID, issuer, email đã xác minh, authentication context |
| **Group membership** | Quan hệ một subject thuộc một nhóm trong hệ thống quản lý | finance-approvers |
| **Entitlement** | Quyền hoặc gói quyền được cấp từ một hệ thống quản lý | Có quyền truy cập ứng dụng Finance |
| **Role** | Tập hợp trách nhiệm/quyền được định nghĩa trong một ứng dụng hoặc miền nghiệp vụ | PaymentApprover |
| **Permission** | Quyền thực hiện một hành động trên loại hoặc đối tượng tài nguyên | payment.approve |
| **Policy** | Quy tắc quyết định có cho phép hành động trong ngữ cảnh cụ thể không | Approver không được tự duyệt khoản do mình tạo |

Một claim như department=finance không tự động có nghĩa người dùng được phê duyệt thanh toán. Phòng ban có thể là dữ liệu HR, nhưng quyền phê duyệt phải được cấp theo quy trình và phạm vi được phê duyệt.

Tương tự, group membership không tự nó là permission. Nhóm có thể được dùng làm đầu vào cho mapping, nhưng ứng dụng phải biết nhóm đến từ issuer nào, tenant nào, được quản lý ra sao và có còn hiệu lực không.

## 3. Vì sao cần role mapping?

IdP thường quản lý danh tính và nhóm ở cấp tổ chức. Mỗi ứng dụng lại có ngôn ngữ nghiệp vụ và mô hình quyền riêng. Role mapping giúp ứng dụng sử dụng role có ý nghĩa với nghiệp vụ mà không phải phụ thuộc trực tiếp vào tên nhóm kỹ thuật của từng IdP.

Lợi ích:

- **Tách nguồn danh tính khỏi mô hình ứng dụng:** thay IdP hoặc đổi cấu trúc group không buộc mọi ứng dụng viết lại authorization.
- **Dùng ngôn ngữ nghiệp vụ:** ứng dụng dùng PaymentApprover thay vì phải hiểu tên group nội bộ.
- **Quản lý tập trung:** có thể quản lý mapping và phê duyệt ở một nơi.
- **Giới hạn quyền:** một group lớn có thể được ánh xạ sang role hẹp theo từng ứng dụng.
- **Kiểm toán:** giải thích được vì sao một principal nhận role nào.
- **Hỗ trợ nhiều nguồn:** kết hợp IdP, HR, partner identity và quyền được cấp trực tiếp theo chính sách.

Mapping không nên biến mọi thông tin hồ sơ thành role. Chỉ dùng thuộc tính có mục đích, nguồn đáng tin, độ mới phù hợp và người chịu trách nhiệm.

## 4. Luồng role mapping

Một luồng điển hình:

~~~mermaid
flowchart LR
    U["User / Workload"] --> I["Identity Provider"]
    I --> T["Verified identity token / claims"]
    T --> M["Identity and group mapping"]
    M --> R["Application roles"]
    R --> P["Authorization policy"]
    P --> D["Allow / Deny"]
    A["Admin approval / Access governance"] --> M
    H["HR / Directory lifecycle"] --> I
    M --> L["Mapping audit"]
    P --> L
~~~

Các bước:

1. IdP xác thực subject và phát hành token/assertion.
2. Ứng dụng xác minh issuer, chữ ký, audience, thời hạn và profile.
3. Hệ thống lấy subject identifier ổn định và group/entitlement cần thiết.
4. Mapping engine chọn quy tắc phù hợp với ứng dụng, issuer, tenant và ngữ cảnh.
5. Role nội bộ được tạo hoặc tra cứu từ kết quả mapping.
6. Authorization policy kiểm tra role, permission, resource, tenant và điều kiện bổ sung.
7. Quyết định và nguồn cấp role được ghi audit.

Role mapping và authorization là hai bước riêng. Mapping cho biết principal có role nào; authorization quyết định role đó có đủ điều kiện cho hành động cụ thể hay không.

## 5. Xác định principal ổn định trước khi mapping

Role phải gắn với đúng principal. Không dùng một thuộc tính dễ thay đổi làm định danh duy nhất.

### Dùng issuer và subject

Trong token liên kết, cặp issuer và subject thường là cơ sở để xác định external principal. Subject ID có thể chỉ duy nhất trong phạm vi issuer, vì vậy không bỏ qua issuer khi lưu liên kết.

Email có thể thay đổi, được tái cấp cho người khác hoặc có thể là alias. Tên hiển thị cũng không ổn định. Không tự động hợp nhất hai principal chỉ vì email giống nhau.

### Ánh xạ sang internal principal

Ứng dụng có thể lưu một bản ghi liên kết:

| Trường | Mục đích |
|---|---|
| issuer | Nguồn phát hành danh tính |
| subject | Identifier ổn định do issuer cung cấp |
| internal_principal_id | Principal nội bộ |
| tenant_id | Phạm vi tổ chức nếu quan hệ có tính tenant |
| linked_at | Thời điểm liên kết |
| link_status | Active, suspended hoặc revoked |

Liên kết cần có quy trình xác minh và audit. Khi user rời tổ chức, external identity bị vô hiệu hóa hoặc tài khoản được unlink, các role dựa trên liên kết đó phải được đánh giá và thu hồi theo policy.

## 6. Mapping group từ IdP sang role ứng dụng

Một mapping rule nên khai báo rõ nguồn, điều kiện và role đích. Ví dụ:

| Nguồn đã xác minh | Ứng dụng | Tenant | Role đích |
|---|---|---|---|
| IdP Corp, group finance-viewers | Finance Portal | Tenant A | FinanceViewer |
| IdP Corp, group finance-approvers | Payment App | Tenant A | PaymentApprover |
| IdP Partner, entitlement support-tier-1 | Support Console | Partner tenant | SupportAgent |
| Workload issuer, subject invoice-worker | Invoice API | Service scope | InvoiceProcessor |

Các tên nhóm và role trong bảng là ví dụ. Mapping thật phải dựa trên group ID hoặc identifier ổn định theo hợp đồng IdP, không phụ thuộc vào display name có thể đổi.

### Tránh mapping theo chuỗi tùy tiện

Một quy tắc như “nếu tên group chứa từ admin thì cấp Admin” rất nguy hiểm. Attacker hoặc thay đổi cấu hình có thể tạo group tên gần giống để kích hoạt role đặc quyền.

Nên dùng:

- Issuer allowlist.
- Group ID/identifier ổn định.
- Application/client context.
- Tenant hoặc organization ID đã xác minh.
- Quy tắc exact match hoặc biểu thức đã kiểm soát, review.
- Version và owner cho mỗi mapping rule.

Không dùng claim do frontend gửi hoặc request parameter làm nguồn group membership.

## 7. RBAC và thiết kế role

Role-Based Access Control (RBAC) nhóm permission thành role, sau đó gán role cho principal. RBAC giúp đơn giản hóa quản trị khi các công việc có trách nhiệm tương đối ổn định.

Ví dụ:

| Role | Permission minh họa |
|---|---|
| OrderViewer | order.read |
| OrderOperator | order.read, order.update |
| PaymentInitiator | payment.read, payment.create |
| PaymentApprover | payment.read, payment.approve |
| TenantAdmin | tenant.user.manage, tenant.policy.manage |
| SecurityAuditor | audit.read |

Không nên đặt mọi quyền vào một role Admin chung. Hãy phân tách quyền quản trị người dùng, cấu hình, dữ liệu và audit khi mức rủi ro khác nhau.

### Role hierarchy

Một số hệ thống cho phép role kế thừa role khác, chẳng hạn OrderOperator bao gồm OrderViewer. Nếu dùng hierarchy, cần hiểu rõ quyền được kế thừa và tránh chu trình.

Role hierarchy không nên tự động làm mọi role đặc quyền trở thành cha của role thông thường. Đặc biệt, TenantAdmin không nên mặc định có quyền truy cập mọi tenant hoặc bypass mọi policy.

### Role explosion

Nếu tạo role cho mọi tổ hợp phòng ban, khu vực, tenant, loại dữ liệu và hành động, số role tăng nhanh và khó kiểm toán.

Có thể giảm bằng cách:

- Dùng role cho trách nhiệm ổn định.
- Dùng attribute/context cho tenant, resource, location hoặc mức nhạy cảm.
- Dùng policy condition cho quan hệ và trạng thái nghiệp vụ.
- Chỉ tạo role mới khi nó biểu diễn một trách nhiệm có ý nghĩa và được quản trị.

## 8. Phân biệt role mapping với ABAC

Attribute-Based Access Control (ABAC) quyết định quyền dựa trên thuộc tính của subject, resource, action và environment. Role mapping có thể là một phần của mô hình kết hợp RBAC/ABAC.

Ví dụ, Minh có role PaymentApprover trong Tenant A. Điều đó chưa đủ để duyệt mọi khoản thanh toán. Policy có thể yêu cầu:

- Payment thuộc Tenant A.
- Trạng thái hiện tại là PendingApproval.
- Minh không phải người tạo payment.
- Số tiền dưới giới hạn của Minh.
- Minh đã hoàn tất step-up authentication gần đây.
- Không có dấu hiệu rủi ro hoặc xung đột lợi ích.

Role xác định năng lực chung; ABAC/policy condition giới hạn theo ngữ cảnh cụ thể.

### Không biến claim thành quyết định cuối cùng

Claim department=finance có thể là một thuộc tính dùng cho policy, nhưng không nên tự động cấp mọi quyền tài chính. Claim authentication method có thể giúp xác định mức xác thực, nhưng không tự cấp quyền nghiệp vụ. Mỗi thuộc tính phải được diễn giải theo định nghĩa issuer và policy của ứng dụng.

## 9. Role theo tenant và phạm vi tài nguyên

Trong ứng dụng multi-tenant, một principal có thể là Viewer ở Tenant A, Approver ở Tenant B và không có quyền ở Tenant C.

Role assignment cần có scope:

- Global: áp dụng toàn hệ thống, chỉ dành cho quyền thật sự toàn cục.
- Tenant: áp dụng trong một tổ chức/tenant.
- Resource: áp dụng trên một project, workspace, account hoặc đối tượng cụ thể.
- Time-bound: chỉ có hiệu lực trong một khoảng thời gian.

Ví dụ, role ProjectAdmin trên Project X không được suy rộng thành TenantAdmin. Một user là admin ở tenant này không mặc nhiên là admin ở tenant khác.

### Kiểm tra resource ownership

Không chỉ kiểm tra token có role PaymentApprover. Service cần xác định payment thuộc tenant nào, role assignment có scope tới tenant đó không và action có được phép trong trạng thái nghiệp vụ hiện tại không.

Không tin tenant ID chỉ vì client đặt trong header hoặc body. Tenant phải được xác minh qua membership, token/grant tin cậy hoặc quan hệ resource đã lưu.

## 10. Nguồn dữ liệu và độ tin cậy của claim

Mỗi thuộc tính dùng trong mapping cần có nguồn và ngữ nghĩa rõ.

| Nguồn | Ví dụ | Kiểm soát cần có |
|---|---|---|
| Identity provider | issuer, subject, authentication context | Verify token/assertion, issuer và audience |
| Enterprise directory | group membership | Xác thực kết nối, quyền đọc và độ mới |
| HR system | employment status, department | Owner dữ liệu, đồng bộ và xử lý thay đổi |
| Access governance | approved entitlement | Workflow phê duyệt, expiry và audit |
| Application database | internal role assignment | Access control, change log và review |
| Client/browser | form field, URL parameter, custom header | Không dùng làm nguồn quyền đáng tin |

Không phải claim nào trong token cũng có cùng độ tin cậy. Một token có chữ ký hợp lệ chỉ chứng minh issuer đã phát hành nội dung đó; ứng dụng vẫn phải biết issuer có thẩm quyền khẳng định thuộc tính đó hay không.

### Group overage và claim bị lược bỏ

Một số IdP không đưa toàn bộ group vào token khi người dùng thuộc quá nhiều nhóm. Token có thể chứa dấu hiệu cho biết cần truy vấn directory/API khác. Ứng dụng không được xem danh sách group bị thiếu là danh sách đầy đủ, hoặc tự cấp quyền dựa trên giá trị fallback.

Nếu cần truy vấn thêm:

- Dùng API và credential service-to-service được cho phép.
- Giới hạn tenant, subject và số lượng group cần lấy.
- Kiểm tra pagination và lỗi partial response.
- Không fail-open khi không lấy được membership.
- Ghi nhận thời điểm và nguồn của dữ liệu được dùng.

## 11. Quy tắc mapping xác định và an toàn

Khi nhiều rule cùng khớp, hệ thống cần quy tắc ưu tiên rõ ràng. Không để kết quả phụ thuộc vào thứ tự ngẫu nhiên của group trong token hoặc thứ tự đọc database.

### Mẫu rule

Một mapping rule có thể gồm:

- Rule ID và version.
- Issuer hoặc source system.
- Subject/group/entitlement identifier.
- Application/client target.
- Tenant hoặc scope.
- Role đích.
- Điều kiện bổ sung.
- Thời hạn hiệu lực.
- Owner và approver.
- Trạng thái active/suspended/revoked.

### Xử lý xung đột

- Quyền bị từ chối hoặc thu hồi phải có precedence theo policy rõ.
- Không để một rule rộng ghi đè rule deny có chủ đích.
- Khi dữ liệu nguồn mâu thuẫn hoặc thiếu, áp dụng default deny cho quyền bảo vệ.
- Ghi audit khi rule được thay đổi hoặc kết quả mapping khác trước.
- Có quy trình review trước khi kích hoạt mapping đặc quyền.

### Default deny

Không có mapping phù hợp nghĩa là principal không nhận role qua mapping đó. Không tự cấp role mặc định như UserAdmin hoặc Member có quyền rộng chỉ để tránh lỗi trải nghiệm. Nếu cần quyền cơ bản, định nghĩa role mặc định hẹp và gán có chủ đích.

## 12. Cấp role trực tiếp và quản trị quyền

Không phải mọi role đều đến từ IdP group. Một số quyền cần workflow nội bộ, đặc biệt là quyền đặc biệt hoặc theo thời hạn.

Quy trình cấp role nên có:

1. Người yêu cầu và lý do nghiệp vụ.
2. Resource/tenant và quyền cụ thể.
3. Owner hoặc manager phê duyệt.
4. Kiểm tra xung đột lợi ích và separation of duties.
5. Thời hạn hoặc ngày review.
6. Ghi nhận nguồn cấp và policy version.
7. Thông báo cho người được cấp và owner.
8. Thu hồi khi hết hạn, đổi vai trò hoặc không còn nhu cầu.

### Just-in-time privilege

Với quyền admin hoặc vận hành nhạy cảm, có thể cấp role tạm thời khi người dùng yêu cầu, xác thực lại, nêu lý do và được phê duyệt. Role tự hết hạn sau thời gian ngắn và mọi hành động được audit.

Không để tài khoản sử dụng hàng ngày luôn giữ quyền admin chỉ vì đôi lúc cần hỗ trợ. Dùng tài khoản/role tách biệt hoặc cơ chế elevation có kiểm soát.

## 13. Vòng đời role mapping

Role mapping phải thay đổi cùng vòng đời nhân sự, nhóm, ứng dụng và tổ chức.

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Reviewed
    Reviewed --> Active
    Reviewed --> Rejected
    Active --> Suspended
    Active --> Expired
    Active --> Revoked
    Suspended --> Active
    Suspended --> Revoked
    Expired --> [*]
    Revoked --> [*]
    Rejected --> [*]
~~~

### Các sự kiện cần xử lý

- Nhân viên mới vào: tạo principal và cấp role theo quy trình.
- Chuyển phòng ban: đánh giá group/claim và role cũ, mới.
- Thay đổi vị trí: thu hồi quyền không còn cần và cấp quyền phù hợp.
- Nhân viên nghỉ việc: vô hiệu hóa principal, session và quyền liên quan theo chính sách.
- Nhóm bị đổi tên hoặc xóa: mapping theo identifier ổn định và xử lý membership mất hiệu lực.
- Tenant đóng hoặc sáp nhập: review role theo scope mới.
- IdP bị compromise: tạm ngừng trust/mapping từ issuer liên quan và đánh giá quyền đã cấp.

### Đồng bộ và cache

Nếu role được cache trong session hoặc token, thay đổi membership có thể không có hiệu lực ngay. Thiết kế cần xác định:

- TTL của cache và thời điểm refresh.
- Sự kiện push khi membership thay đổi.
- Cơ chế invalidate session/token hoặc yêu cầu reauthentication.
- Cách xử lý khi directory/IdP không khả dụng.
- Thời gian tối đa quyền cũ còn hiệu lực sau khi bị thu hồi.

Không tuyên bố quyền đã thu hồi tức thì nếu downstream token hoặc cache vẫn chứa role cũ.

## 14. Quyền đặc quyền, separation of duties và chống nâng quyền

Role mapping có thể tạo ra quyền mạnh hơn dự kiến nếu group hoặc rule quá rộng.

### Separation of duties

Một người không nên tự tạo và tự phê duyệt cùng một giao dịch nếu policy yêu cầu kiểm soát hai người. Role Initiator và Approver cần tách biệt; có thể cấm một principal giữ đồng thời cả hai role trong cùng phạm vi hoặc trong cùng workflow.

### Các lỗi nâng quyền thường gặp

- Mapping group all-employees sang role Admin.
- Dùng display name của group thay vì immutable group ID.
- Chấp nhận role claim do browser gửi.
- Gộp role từ nhiều issuer mà không phân biệt nguồn.
- Không giới hạn tenant của role.
- Không thu hồi role khi user rời nhóm.
- Cấp role admin theo email domain.
- Fallback sang quyền rộng khi directory lookup lỗi.
- Cho phép user tự sửa role assignment qua API thiếu authorization.

### Quy tắc phòng vệ

- Mapping đặc quyền cần phê duyệt và review định kỳ.
- Dùng allowlist issuer, group ID và application target.
- Scope role theo tenant/resource.
- Dùng default deny và deny precedence rõ.
- Áp dụng MFA/step-up cho quản trị role.
- Ghi audit người yêu cầu, approver, nguồn và kết quả.
- Tự động phát hiện role assignment bất thường hoặc không có owner.

## 15. Ví dụ mapping cho ứng dụng thanh toán

**Bối cảnh:** Doanh nghiệp dùng IdP quản lý nhân viên và group. Payment App cần role Viewer, Initiator, Approver và Auditor. Quyền phụ thuộc tenant và có quy tắc một người không được tự duyệt khoản mình tạo.

### Thiết kế

1. Xác minh token từ issuer doanh nghiệp và lấy subject ổn định.
2. Tra group membership bằng identifier đã đăng ký, không dùng display name.
3. Mapping group payment-readers sang PaymentViewer trong tenant được cấp.
4. Mapping group payment-initiators sang PaymentInitiator theo scope tenant.
5. Mapping group payment-approvers sang PaymentApprover; quyền này cần phê duyệt access governance.
6. Role PaymentAuditor được cấp theo workflow riêng, chỉ có quyền đọc audit.
7. Policy kiểm tra tenant, payment status, transaction limit và subject không phải người tạo.
8. Khi user rời group hoặc employment status chuyển inactive, role tương ứng được thu hồi.
9. Audit lưu issuer, subject, group ID, mapping rule/version, role, tenant và thời điểm.

### Một request cụ thể

Minh có PaymentApprover ở Tenant A nhưng tạo khoản thanh toán PAY-17. Dù role mapping thành công, policy từ chối Minh tự phê duyệt khoản do chính Minh tạo. Một approver khác có role phù hợp, trong cùng tenant và đáp ứng step-up, có thể tiếp tục.

### Nếu IdP group claim bị thiếu?

Nếu token báo group overage hoặc lookup directory lỗi, không suy luận rằng user không thuộc nhóm và cũng không tự cấp role. Áp dụng trạng thái không xác định theo policy, từ chối hành động nhạy cảm và ghi sự kiện để xử lý.

## 16. Ví dụ mapping rule

Ví dụ JSON dưới đây mô tả một rule giả lập. Đây là dữ liệu cấu hình minh họa; hệ thống thật cần schema validation, phê duyệt, versioning và kiểm soát quyền sửa.

~~~json
{
  "rule_id": "map-payment-approver-tenant-a",
  "version": 3,
  "source": {
    "issuer": "https://idp.example.org",
    "group_id": "grp-9a31"
  },
  "target": {
    "application": "payment-app",
    "tenant_id": "tenant-a",
    "role": "PaymentApprover"
  },
  "conditions": {
    "principal_status": "active",
    "approval_required": true
  },
  "validity": {
    "not_before": "2026-11-22T00:00:00Z",
    "expires_at": "2027-02-22T00:00:00Z"
  },
  "owner": "access-governance"
}
~~~

Không coi JSON nhận từ browser là rule tin cậy. Rule phải nằm trong kho cấu hình được bảo vệ, được phê duyệt và được áp dụng bởi mapping service có quyền phù hợp.

## 17. Kiểm thử role mapping

Kiểm thử trong môi trường được phép với principal, issuer, group và tenant giả lập:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Token từ issuer không được allowlist | Không áp dụng mapping |
| Subject khác nhau nhưng email giống nhau | Không tự hợp nhất principal |
| Group ID được phép, đúng app và tenant | Ánh xạ role đúng |
| Group display name giống group đặc quyền nhưng ID khác | Không được cấp role đặc quyền |
| Client tự gửi role=Admin | Bị bỏ qua; role lấy từ nguồn tin cậy |
| User thuộc group nhưng employment inactive | Thu hồi/không cấp role theo policy |
| User rời group | Role bị thu hồi trong SLA đã định |
| Group claim bị overage | Lookup nguồn tin cậy hoặc fail closed |
| Directory lookup timeout | Không cấp role dựa trên dữ liệu chưa xác minh |
| Mapping rule hết hạn | Không tiếp tục cấp role |
| Hai rule xung đột | Áp dụng precedence đã định và audit |
| Không có rule khớp | Default deny hoặc role cơ bản hẹp đã định nghĩa |
| Role chỉ thuộc Tenant A được dùng ở Tenant B | Bị từ chối |
| ProjectAdmin truy cập tài nguyên ngoài project | Bị từ chối |
| User tự gán role qua API | Authorization từ chối |
| Một người tạo và duyệt cùng payment | Separation of duties từ chối |
| Role admin được cấp tạm thời | Tự hết hạn và có audit |
| Role bị revoke nhưng token/cache cũ còn | Kiểm tra propagation và giới hạn thời gian tồn tại |
| IdP bị compromise | Có khả năng đình chỉ issuer/mapping và điều tra |
| Mapping rule bị sửa trái phép | Change control/audit phát hiện và ngăn áp dụng |

### Chỉ số vận hành

- Số role assignment theo nguồn, tenant và ứng dụng.
- Tỷ lệ role assignment có owner, approver và expiry/review date.
- Thời gian từ thay đổi group đến thu hồi role ở ứng dụng.
- Số role đặc quyền được cấp ngoài workflow chuẩn.
- Số lần mapping bị từ chối do issuer/group/tenant không hợp lệ.
- Số principal có role không còn nhu cầu hoặc không có owner.
- Số lần cross-tenant authorization bị chặn.
- Số xung đột mapping và lỗi đồng bộ directory.

## 18. Checklist thiết kế role mapping

- [ ] Phân biệt identity claim, group, entitlement, role, permission và policy.
- [ ] Xác định principal bằng issuer và subject ổn định.
- [ ] Không tự động liên kết tài khoản chỉ dựa trên email.
- [ ] Mapping dùng issuer allowlist và group/entitlement ID ổn định.
- [ ] Mỗi rule có application, tenant/scope, role, owner, version và validity.
- [ ] Không tin role, group hoặc tenant do browser/client tự gửi.
- [ ] Role biểu diễn trách nhiệm; permission biểu diễn hành động cụ thể.
- [ ] Kết hợp RBAC với policy condition/ABAC khi cần.
- [ ] Role assignment được scope theo global, tenant, resource hoặc thời hạn.
- [ ] Có default deny và precedence rõ khi rule xung đột.
- [ ] Xử lý group overage và directory lookup failure an toàn.
- [ ] Có quy trình cấp, phê duyệt, review, hết hạn và thu hồi role.
- [ ] Đồng bộ HR/IdP/directory có SLA và xử lý offboarding.
- [ ] Role đặc quyền có step-up, approval và audit.
- [ ] Có separation of duties cho workflow nhạy cảm.
- [ ] Cache/session/token có cơ chế cập nhật hoặc thu hồi quyền cũ.
- [ ] Audit giải thích được nguồn và rule tạo ra từng role.
- [ ] Kiểm thử spoofing, tenant isolation, stale membership và privilege escalation.

## Ghi nhớ

Role mapping chuyển identity claim, group membership hoặc entitlement từ nguồn đã xác minh thành role có ý nghĩa trong ứng dụng. Mapping phải gắn với issuer, subject, application, tenant và resource scope; không dựa vào display name, email hoặc role header do client gửi.

Role chỉ là đầu vào cho authorization. Mỗi service vẫn phải kiểm tra permission, resource, tenant, trạng thái nghiệp vụ và separation of duties. Quản lý mapping như một chính sách có owner, phê duyệt, version, expiry, audit và quy trình thu hồi để thay đổi danh tính không biến thành nâng quyền ngoài ý muốn.
