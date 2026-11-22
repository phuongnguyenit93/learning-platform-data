# Phân quyền thao tác

## 1. Phân quyền thao tác trong DSL là gì?

Một DSL (*Domain-Specific Language*) có thể mô tả những thao tác ảnh hưởng đến dữ liệu, quy trình hoặc hệ thống bên ngoài: đọc hồ sơ, cập nhật đơn hàng, phê duyệt giao dịch, chạy workflow, gọi service, tạo tài nguyên hoặc xóa cấu hình. Không phải mọi người dùng hay thành phần runtime đều được phép thực hiện mọi thao tác đó.

**Phân quyền thao tác (*operation authorization*)** là cơ chế xác định một chủ thể có được phép thực hiện một hành động cụ thể trên một tài nguyên cụ thể trong một ngữ cảnh cụ thể hay không.

Ví dụ, trong DSL quản lý đơn hàng:

~~~text
operation "approveOrder" on Order {
    action: approve
    permission: "orders.approve"
}
~~~

Một policy có thể cho phép nhân viên thuộc nhóm quản lý đơn hàng phê duyệt đơn trong phạm vi chi nhánh của họ, nhưng không cho phép họ phê duyệt đơn thuộc chi nhánh khác.

Phân quyền cần trả lời các câu hỏi:
- Ai đang yêu cầu thao tác?
- Chủ thể đang đại diện cho người dùng, service hay hệ thống nào?
- Thao tác cụ thể là đọc, tạo, sửa, xóa, thực thi hay một hành động miền?
- Tài nguyên nào bị tác động?
- Tài nguyên thuộc tenant, tổ chức hoặc chủ sở hữu nào?
- Trạng thái và thuộc tính hiện tại của tài nguyên có cho phép thao tác không?
- Chủ thể có quyền trong phạm vi nào và trong khoảng thời gian nào?
- Quyền đến từ role, attribute, relationship hay capability nào?
- Nếu quyền bị từ chối, lý do và cách xử lý là gì?

Phân quyền là một phần của bảo mật DSL, nhưng quyết định cuối cùng thường cần được thực thi bởi runtime hoặc host application. Một dòng policy trong source không tự bảo vệ tài nguyên nếu các đường truy cập khác có thể bỏ qua policy đó.

## 2. Phân biệt authentication, authorization và access control

Ba khái niệm có liên quan nhưng không đồng nghĩa.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Authentication | Chủ thể là ai? | Xác minh session hoặc access token |
| Authorization | Chủ thể được phép làm gì? | User có quyền approve order này không? |
| Access control | Cơ chế thực thi và quản lý quyền | Policy engine chặn request không được phép |

Authentication xác lập danh tính hoặc principal. Authorization đánh giá quyền của principal đối với action và resource. Access control bao gồm policy, enforcement point, permission store, audit và các biện pháp bảo đảm mọi đường truy cập đều được kiểm tra.

Một token hợp lệ chỉ chứng minh danh tính hoặc quyền hạn được token đại diện; nó không tự động có nghĩa người giữ token được đọc mọi tài nguyên trong hệ thống.

### 2.1. Identity không đồng nghĩa với permission

Ví dụ một người dùng đã đăng nhập và có principal ID là user-42. Điều đó không tự động cấp quyền:
- Đọc tất cả khách hàng.
- Xóa đơn hàng.
- Chỉnh sửa policy.
- Thực thi operation quản trị.
- Truy cập dữ liệu của tenant khác.

Quyền phải được xác định từ policy và context phù hợp.

### 2.2. Authorization không phải UI hiding

Ẩn nút Delete trong giao diện chỉ cải thiện trải nghiệm. Client có thể gọi API trực tiếp hoặc sửa request. Server/runtime phải kiểm tra quyền tại điểm thực thi.

### 2.3. Policy declaration không thay thế enforcement

DSL có thể khai báo permission, role và policy. Nhưng nếu handler hoặc data access layer không kiểm tra quyết định, người dùng có thể đi đường khác để thực hiện cùng thao tác.

## 3. Mô hình quyết định: Principal, Action, Resource và Context

Một quyết định authorization thường được xây dựng từ bốn nhóm dữ liệu:

~~~text
Authorization Request
    |
    +-- Principal: ai yêu cầu?
    |
    +-- Action: muốn làm gì?
    |
    +-- Resource: tác động lên đối tượng nào?
    |
    +-- Context: trong điều kiện nào?
             |
             v
        Policy Evaluation
             |
             v
        Permit / Deny
~~~

### 3.1. Principal

Principal là danh tính được hệ thống dùng để đánh giá quyền. Principal có thể là:
- Người dùng cuối.
- Nhóm hoặc tổ chức.
- Service account.
- Workload identity.
- Job hoặc scheduler.
- System principal cho thao tác nội bộ.
- Delegated principal đại diện một chủ thể khác.

Principal nên có ID ổn định và issuer/trust domain rõ ràng. Không nên chỉ dùng display name hoặc email làm identity key vì các giá trị đó có thể đổi.

### 3.2. Action

Action mô tả thao tác được yêu cầu. Các action tổng quát thường gặp:
- read.
- create.
- update.
- delete.
- execute.
- approve.
- publish.
- export.
- administer.

DSL có thể định nghĩa action theo miền như `orders.approve`, `payment.refund` hoặc `workflow.cancel`. Action cần có semantics rõ, tránh tên chung chung như manage nếu nó gộp nhiều quyền khác nhau.

### 3.3. Resource

Resource là đối tượng chịu tác động:
- Một record.
- Một file hoặc module.
- Một workflow instance.
- Một API endpoint.
- Một configuration key.
- Một tenant.
- Một nhóm tài nguyên.
- Một operation được định nghĩa trong DSL.

Resource cần identity ổn định và loại tài nguyên. Policy cần phân biệt tài nguyên cụ thể với resource type hoặc collection.

### 3.4. Context

Context chứa dữ liệu bổ sung cho quyết định:
- Tenant ID.
- Organization hoặc department.
- Resource owner.
- Resource status.
- Request time.
- Network zone.
- Device posture.
- Authentication strength.
- Approval state.
- Environment.
- Purpose of access.
- Request origin.
- Transaction risk.

Context phải đến từ nguồn đáng tin cậy. Không được tin giá trị tenantId hoặc role do client tự gửi nếu server chưa xác minh.

### 3.5. Authorization tuple

Có thể biểu diễn request bằng tuple:

~~~text
principal = user:42
action    = orders.approve
resource  = order:ORD-100
context   = {
    tenant: tenant:acme,
    branch: branch:north,
    time: 2026-11-15T10:00:00Z
}
~~~

Policy engine đánh giá tuple này và trả decision cùng metadata giải thích.

## 4. Permission, role, policy và scope

Các khái niệm thường bị dùng lẫn lộn:

- **Permission:** quyền thực hiện một action trên một loại hoặc instance resource.
- **Role:** tập hợp permission được gán cho principal hoặc group.
- **Policy:** quy tắc quyết định khi principal yêu cầu action trên resource trong context.
- **Scope:** giới hạn phạm vi mà permission hoặc role có hiệu lực.
- **Entitlement:** quyền lợi hoặc khả năng được cấp cho một principal theo một nguồn quản lý.
- **Capability:** bằng chứng hoặc reference mang quyền thực hiện một thao tác cụ thể.

Ví dụ:

~~~text
permission "orders.read"
permission "orders.approve"

role "OrderViewer" {
    grant "orders.read"
}

role "OrderApprover" {
    grant "orders.read"
    grant "orders.approve"
}
~~~

Role giúp quản lý tập quyền theo trách nhiệm. Policy có thể thêm điều kiện theo resource hoặc context. Một role OrderApprover không nhất thiết được phê duyệt mọi đơn hàng trên mọi tenant.

### 4.1. Permission granularity

Permission quá rộng như `orders.manage` có thể cấp nhiều quyền hơn nhu cầu. Permission quá nhỏ lại khó quản trị.

Nên thiết kế theo action có ý nghĩa nghiệp vụ và tách riêng các hành động có rủi ro khác nhau. Ví dụ read, approve, refund và delete thường không nên gộp thành một permission.

### 4.2. Scope

Một permission có thể giới hạn:
- Toàn hệ thống.
- Một tenant.
- Một organization.
- Một project.
- Một resource collection.
- Một resource cụ thể.
- Một môi trường như staging hoặc production.

Scope phải được kiểm tra ở server/runtime. Việc chỉ gắn scope trong giao diện không đủ bảo vệ tài nguyên.

## 5. Role-Based Access Control (RBAC)

RBAC cấp quyền thông qua role. Principal được gán một hoặc nhiều role; mỗi role chứa permission.

Mô hình cơ bản:

~~~text
User ---- assigned role ----> Role
                                  |
                                  v
                             Permissions
                                  |
                                  v
                           Resource actions
~~~

Ví dụ:

~~~text
role "OrderReader" {
    grant "orders.read"
}

role "OrderOperator" {
    grant "orders.read"
    grant "orders.update"
}

role "OrderManager" {
    grant "orders.read"
    grant "orders.update"
    grant "orders.approve"
}

assign role "OrderManager" to user:42
within tenant:acme
~~~

### 5.1. Role assignment

Một role assignment nên có:
- Principal hoặc group.
- Role ID.
- Scope.
- Thời điểm bắt đầu.
- Thời điểm hết hạn.
- Người hoặc hệ thống cấp.
- Lý do cấp.
- Trạng thái assignment.

Role có thể được cấp trực tiếp hoặc thông qua group membership. Cần xác định cách xử lý khi principal rời group hoặc assignment hết hạn.

### 5.2. Role hierarchy

Một số hệ thống hỗ trợ role kế thừa:

~~~text
role "OrderManager" inherits "OrderOperator"
role "OrderOperator" inherits "OrderReader"
~~~

Khi đó OrderManager nhận permission của các role cha theo quy tắc inheritance.

Cần phát hiện vòng lặp trong role hierarchy và quy định liệu inheritance có truyền scope, expiry và deny rules hay không.

### 5.3. Separation of duties

Một số thao tác yêu cầu người tạo và người phê duyệt phải khác nhau. Đây là separation of duties.

Ví dụ:
- Người tạo payment không được tự approve payment đó.
- Người deploy policy không được tự approve thay đổi production.
- Người yêu cầu hoàn tiền không được tự phê duyệt refund vượt hạn mức.

Điều kiện này cần dựa trên actor identity và audit context, không chỉ role.

### 5.4. Ưu điểm và giới hạn

RBAC dễ hiểu, dễ audit và phù hợp tổ chức có trách nhiệm ổn định. Tuy nhiên, số lượng role có thể tăng nhanh nếu phải biểu diễn mọi tổ hợp tenant, resource ownership, thời gian và thuộc tính.

Khi quyền phụ thuộc nhiều vào resource context, có thể kết hợp RBAC với ABAC hoặc relationship-based policy.

## 6. Attribute-Based Access Control (ABAC)

ABAC quyết định quyền dựa trên thuộc tính của principal, resource, action và environment.

Ví dụ policy:

~~~text
policy "approve-own-branch-orders" {
    permit when
        principal.hasRole("OrderApprover")
        and principal.branchId == resource.branchId
        and resource.status == "PENDING"
        and context.environment == "production"
}
~~~

Một policy ABAC có thể kiểm tra:
- Principal thuộc department nào.
- Resource có owner là ai.
- Amount có vượt ngưỡng không.
- Tài nguyên đang ở trạng thái nào.
- Request được gửi trong thời gian nào.
- Thiết bị có đạt security posture không.

### 6.1. Subject attributes

Thuộc tính chủ thể có thể gồm role, department, tenant, clearance level hoặc employment status.

### 6.2. Resource attributes

Thuộc tính tài nguyên có thể gồm ownerId, classification, tenantId, status, region hoặc sensitivity.

### 6.3. Action attributes

Action có thể có risk level, required assurance, side-effect category hoặc approval requirement.

### 6.4. Environment attributes

Environment có thể gồm time, network zone, deployment environment, device state hoặc incident mode.

### 6.5. Attribute trust

Không phải mọi attribute đều đáng tin như nhau. Cần ghi nguồn và thời điểm xác minh. Ví dụ branchId lấy từ directory service đáng tin cậy hơn branchId do request body tự gửi.

### 6.6. Ưu điểm và giới hạn

ABAC biểu đạt được điều kiện chi tiết mà không cần tạo role cho mọi trường hợp. Đổi lại, policy có thể phức tạp và khó dự đoán nếu attribute schema, source và evaluation semantics không rõ.

## 7. Relationship-Based Access Control (ReBAC)

ReBAC quyết định quyền dựa trên quan hệ giữa principal và resource.

Ví dụ:
- User là owner của document.
- User là member của project.
- User là manager của employee.
- Team được gán vào workspace.
- Organization sở hữu repository.

Một quan hệ có thể được mô tả:

~~~text
relation "owner" from User to Document
relation "member" from User to Project
relation "parent" from Project to Organization

policy "project-document-read" {
    permit read Document when
        principal is owner of resource
        or principal is member of resource.project
}
~~~

### 7.1. Quan hệ trực tiếp và gián tiếp

User có thể không trực tiếp được gán quyền trên document nhưng là member của project chứa document. Policy có thể kế thừa quyền qua graph quan hệ.

### 7.2. Relationship graph

Một graph có thể gồm:
- Principal nodes.
- Group/team nodes.
- Resource nodes.
- Relation edges.
- Parent/child relations.

Policy engine truy vấn graph để xác định principal có đường quan hệ hợp lệ đến resource hay không.

### 7.3. Cycle và inheritance

Quan hệ có thể lồng nhau hoặc có cycle. Hệ thống cần quy định traversal, depth limit, cycle detection và cách cache kết quả.

### 7.4. Khi nào dùng ReBAC?

ReBAC phù hợp với:
- Document sharing.
- Project/workspace membership.
- Organization hierarchy.
- Team-owned resources.
- Collaborative systems.

Nó có thể kết hợp với RBAC: role xác định action, relationship xác định resource scope.

## 8. Capability-Based Access Control

Capability là một quyền được biểu diễn bằng token, handle hoặc object reference có khả năng cấp phép một thao tác cụ thể.

Ví dụ một service nhận capability chỉ cho phép đọc một artifact:

~~~text
capability "artifact-reader" {
    resource: artifact:build-42
    actions: ["read"]
    expiresAt: 2026-11-15T12:00:00Z
}
~~~

Capability có thể được truyền cho một thành phần thay vì để thành phần đó tra cứu toàn bộ role của người dùng.

### 8.1. Least authority

Capability nên cấp đúng quyền cần thiết, trên đúng resource và trong khoảng thời gian ngắn nhất cần thiết.

### 8.2. Delegation

Một capability có thể được delegate nếu policy cho phép. Delegation không nên làm tăng quyền so với capability gốc. Cần giới hạn depth, expiry và khả năng further delegation.

### 8.3. Revocation

Capability dạng bearer token có thể khó thu hồi trước expiry nếu không có revocation list hoặc online validation. Có thể dùng short-lived token, reference token hoặc revocation registry tùy yêu cầu.

### 8.4. Capability không thay thế identity

Capability chứng minh quyền được cấp cho thao tác/resource cụ thể. Hệ thống vẫn có thể cần xác minh người hoặc service sử dụng capability để audit và áp dụng context bổ sung.

## 9. Kết hợp RBAC, ABAC và ReBAC

Một hệ thống thực tế có thể dùng nhiều mô hình cùng lúc.

Ví dụ:
- RBAC xác định user có role OrderApprover.
- ReBAC xác định user là member của branch sở hữu order.
- ABAC kiểm tra order đang PENDING và amount dưới hạn mức của user.
- Context kiểm tra request đến từ môi trường được phép.

Một policy tổng hợp:

~~~text
policy "approve-order" {
    permit when
        principal.hasRole("OrderApprover")
        and principal.belongsTo(resource.branch)
        and resource.status == "PENDING"
        and resource.amount <= principal.approvalLimit
}
~~~

Cần định nghĩa rõ thứ tự hoặc cách kết hợp. Một điều kiện permit từ RBAC không nên vô tình bỏ qua deny từ ABAC hoặc resource boundary.

## 10. Policy evaluation và decision semantics

Policy engine thường trả một trong các kết quả:

| Decision | Ý nghĩa |
|---|---|
| Permit | Thao tác được phép |
| Deny | Thao tác bị từ chối |
| NotApplicable | Không policy nào áp dụng |
| Indeterminate | Không thể đưa ra kết quả đáng tin cậy |

Một số hệ thống gộp NotApplicable và Deny ở lớp API, nhưng vẫn nên phân biệt nội bộ để diagnostics rõ hơn.

### 10.1. Default deny

Nếu không có policy nào cho phép, mặc định phải từ chối. Đây là nguyên tắc fail-safe.

Không nên mặc định cho phép chỉ vì policy chưa được tải hoặc không tìm thấy resource attribute.

### 10.2. Deny overrides

Một chính sách phổ biến là deny-overrides: nếu có policy áp dụng và đưa ra deny, kết quả tổng hợp là deny ngay cả khi policy khác permit.

### 10.3. Permit overrides

Permit-overrides cho phép một permit thắng deny khác theo semantics đã định nghĩa. Chỉ dùng khi business/security model cho phép rõ ràng.

### 10.4. First applicable

First-applicable chọn kết quả từ policy đầu tiên áp dụng. Thứ tự policy trở thành một phần semantics và phải được version, test và review.

### 10.5. Indeterminate

Indeterminate có thể xảy ra khi:
- Attribute provider lỗi.
- Policy không thể evaluate.
- Resource không resolve được.
- Context thiếu dữ liệu bắt buộc.
- Timeout hoặc policy version không sẵn sàng.

Đối với thao tác nhạy cảm, Indeterminate nên được xử lý như deny. Không được chuyển lỗi kỹ thuật thành permit.

### 10.6. Obligations và advice

Một decision có thể kèm obligation:
- Redact một số field.
- Ghi audit event.
- Yêu cầu MFA step-up.
- Áp dụng watermark.
- Giới hạn export.
- Thông báo cho data owner.

Obligation bắt buộc phải được thực hiện trước hoặc trong thao tác được phép. Nếu obligation không thể thực hiện, enforcement point cần từ chối hoặc xử lý theo policy fail-safe.

## 11. Cấu trúc policy DSL

Policy DSL cần đủ biểu đạt nhưng vẫn dễ đọc và có thể kiểm tra tĩnh.

Một ví dụ minh họa:

~~~text
policy "read-customer" {
    effect: permit
    actions: ["customer.read"]
    resources: ["Customer"]

    when:
        principal.tenantId == resource.tenantId
        and (
            principal.id == resource.ownerId
            or principal.hasRole("CustomerSupport")
        )
}
~~~

### 11.1. Policy metadata

Một policy nên có:
- Stable policy ID.
- Name và description.
- Effect.
- Actions.
- Resource types hoặc resource selector.
- Condition.
- Scope.
- Version.
- Owner.
- Validity interval.
- Priority hoặc combining metadata nếu có.
- Audit metadata.

### 11.2. Typed attributes

Attribute cần có type như String, Boolean, Integer, DateTime hoặc ResourceReference. Type checking giúp phát hiện so sánh không hợp lệ trước runtime.

### 11.3. Null và missing attributes

DSL cần phân biệt:
- Attribute không tồn tại.
- Attribute có giá trị null.
- Attribute provider không trả lời.
- Attribute không được phép đọc.

Không nên coi missing attribute là true hoặc tự chuyển thành empty string. Semantics cần rõ và an toàn.

### 11.4. Pure policy expressions

Policy expression nên là biểu thức thuần, không có side effect. Policy engine không nên gửi email, ghi database hoặc gọi operation thay đổi trạng thái trong lúc quyết định quyền.

Nếu cần obligation, enforcement point thực hiện nó sau khi nhận decision.

### 11.5. Không dùng dynamic eval tùy ý

Không nên cho policy gọi arbitrary host methods, reflection hoặc script không giới hạn. Chỉ expose một tập function được kiểm soát, typed và có resource budget.

## 12. Phân quyền theo trạng thái và workflow

Quyền có thể thay đổi theo lifecycle của resource.

Ví dụ đơn hàng:

~~~text
state DRAFT {
    allow "orders.update" to role "OrderOwner"
    allow "orders.submit" to role "OrderOwner"
}

state PENDING {
    allow "orders.approve" to role "OrderApprover"
    allow "orders.reject" to role "OrderApprover"
}

state APPROVED {
    allow "orders.ship" to role "WarehouseOperator"
}

state CANCELLED {
    deny "*"
}
~~~

Đây là cú pháp minh họa. Runtime phải kiểm tra trạng thái hiện tại ngay trước thao tác.

### 12.1. State-based permission

Một user có thể được phép sửa resource ở trạng thái DRAFT nhưng chỉ được đọc khi đã APPROVED. Policy cần kết hợp role và state.

### 12.2. Transition authorization

Không chỉ kiểm tra quyền truy cập state; cần kiểm tra quyền thực hiện transition:
- submit.
- approve.
- reject.
- cancel.
- reopen.

Transition có thể có precondition và permission riêng.

### 12.3. Time-of-check/time-of-use

Nếu quyền được kiểm tra khi hiển thị nút nhưng resource đổi trạng thái trước khi request được gửi, quyết định cũ không còn hợp lệ. Enforcement point cần kiểm tra lại trong transaction hoặc ngay trước commit.

### 12.4. Approval workflow

Thao tác nhạy cảm có thể yêu cầu nhiều bước:
- Người yêu cầu tạo request.
- Manager approve.
- Security officer approve nếu vượt ngưỡng.
- Runtime mới thực hiện action.

Authorization và approval workflow có liên quan nhưng không đồng nghĩa. Có quyền gửi yêu cầu không có nghĩa đã có quyền thực hiện hành động cuối cùng.

## 13. Phân quyền ở nhiều mức tài nguyên

Một DSL có thể cần kiểm soát quyền ở nhiều granularity.

### 13.1. API/operation-level

Cho phép hoặc từ chối gọi một operation như `orders.create` hoặc `payments.refund`.

### 13.2. Resource-level

Cùng operation có thể được phép với resource thuộc user nhưng bị từ chối với resource của người khác.

### 13.3. Field-level

Principal có thể đọc customer name nhưng không được đọc national ID hoặc payment token. Với update, principal có thể sửa address nhưng không sửa riskScore.

Field-level policy có thể:
- Ẩn field.
- Redact field.
- Từ chối toàn request nếu field bị cấm.
- Bỏ qua field bị cấm theo policy rõ ràng.

Không nên âm thầm bỏ qua field nhạy cảm nếu client cần biết update không được áp dụng.

### 13.4. Row-level và collection-level

Khi truy vấn danh sách, policy cần lọc từng resource hoặc chuyển điều kiện thành query an toàn ở data layer. Chỉ kiểm tra quyền trên endpoint không bảo đảm từng row được phép trả về.

### 13.5. Property access trong DSL

Nếu DSL cho phép expression đọc object property, runtime cần enforce field visibility. Nếu không, người dùng có thể truy cập dữ liệu nhạy cảm qua expression, template hoặc log action dù API chính đã che field.

## 14. Phân quyền thao tác bên trong DSL runtime

DSL có thể cung cấp built-in operations hoặc extension functions như:
- readFile.
- writeFile.
- callService.
- publishEvent.
- executeQuery.
- sendNotification.
- modifyResource.
- invokePlugin.

Mỗi operation có thể tạo side effect hoặc truy cập tài nguyên. Runtime cần một capability registry hoặc operation registry mô tả quyền cần thiết.

Ví dụ:

~~~text
operation "publishEvent" {
    requiredCapability: "events.publish"
    resourceType: "EventChannel"
    effects: ["network", "external-write"]
}
~~~

### 14.1. Operation registry

Registry nên chứa:
- Operation ID.
- Input/output schema.
- Required permission/capability.
- Resource types.
- Side-effect classification.
- Timeout và resource budget.
- Allowed environments.
- Audit requirement.
- Implementation binding.

### 14.2. Least privilege cho built-ins

Không nên cấp cho mọi DSL program quyền filesystem, network hoặc database mặc định. Chỉ cấp capability cần thiết cho operation được phép.

### 14.3. Plugin operations

Plugin hoặc extension có thể thêm operation mới. Việc cài plugin không nên tự động cấp quyền cho mọi DSL program. Host application phải kiểm soát:
- Plugin identity và trust.
- Operation permissions.
- Resource scope.
- User consent hoặc administrator approval khi cần.
- Version và revocation.
- Audit.

### 14.4. Sandbox

Sandbox giới hạn khả năng của DSL runtime. Có thể áp dụng:
- Không truy cập filesystem ngoài vùng cho phép.
- Network allowlist.
- Không gọi process execution tùy ý.
- Memory/CPU/time limits.
- Không reflection hoặc native code.
- Capability-based API thay vì quyền hệ điều hành rộng.

Authorization ở cấp DSL không thay thế sandbox ở cấp process/OS.

## 15. Policy enforcement architecture

Một kiến trúc phổ biến tách decision khỏi enforcement.

~~~text
Client / DSL Runtime
        |
        v
Policy Enforcement Point (PEP)
        |
        +---- principal/action/resource/context
        |
        v
Policy Decision Point (PDP)
        |
        +---- Policy Store
        +---- Attribute Providers
        +---- Relationship Store
        |
        v
Permit / Deny / Indeterminate
        |
        v
PEP enforces decision and obligations
        |
        v
Resource / Operation Handler
~~~

### 15.1. Policy Enforcement Point (PEP)

PEP nằm ở nơi thao tác được thực hiện:
- API gateway.
- Service handler.
- DSL operation dispatcher.
- Data access layer.
- File/resource service.
- Workflow transition handler.

PEP phải kiểm tra mọi đường truy cập có thể tác động đến tài nguyên.

### 15.2. Policy Decision Point (PDP)

PDP evaluate policy và trả decision. Nó nên độc lập với UI và không tự thực hiện operation được yêu cầu.

### 15.3. Policy Administration Point (PAP)

PAP quản lý tạo, sửa, review, publish và rollback policy. Người có quyền chạy operation không mặc nhiên có quyền sửa policy.

### 15.4. Policy Information Point (PIP)

PIP cung cấp attribute và relationship data cho PDP, ví dụ directory, tenant registry, resource metadata hoặc device posture provider.

PIP cần xác thực nguồn dữ liệu, freshness và lỗi truy cập.

### 15.5. Complete mediation

Mọi thao tác truy cập tài nguyên được bảo vệ phải qua enforcement point. Nếu một handler nội bộ hoặc plugin có thể gọi thẳng data store mà không kiểm tra quyền, hệ thống có đường bypass.

## 16. Deny-by-default và fail-safe behavior

Một hệ thống bảo mật nên mặc định từ chối khi không có bằng chứng cho phép.

Các trường hợp cần fail-safe:
- Policy store không truy cập được.
- Attribute provider timeout.
- Relationship graph chưa sẵn sàng.
- Principal không xác thực được.
- Resource ownership không xác định.
- Policy version không hợp lệ.
- Decision cache không đáng tin.
- Obligation bắt buộc không thực hiện được.

### 16.1. Fail closed

Fail closed nghĩa là lỗi khi đánh giá quyền không được biến thành permit. Với một số thao tác ít rủi ro, hệ thống có thể có degraded mode được thiết kế riêng, nhưng phải được policy và risk owner phê duyệt rõ ràng.

### 16.2. NotApplicable không phải Permit

Không policy nào áp dụng không có nghĩa request được phép. Nếu combining algorithm không trả permit rõ ràng, default deny phải được áp dụng.

### 16.3. Availability và security

PDP là dependency quan trọng. Cần thiết kế cache, redundancy và timeout để vừa giữ availability vừa không mở đường bypass khi PDP lỗi.

## 17. Delegation, impersonation và service identity

### 17.1. Delegation

Một principal có thể ủy quyền một số thao tác cho principal khác. Delegation cần xác định:
- Ai ủy quyền?
- Ai nhận quyền?
- Action nào được ủy quyền?
- Resource scope.
- Thời hạn.
- Có được ủy quyền tiếp không?
- Cách thu hồi.

Quyền được delegate không nên vượt quyền mà delegator đang có.

### 17.2. Impersonation

Impersonation cho phép service thực hiện thao tác trong danh nghĩa user. Phải lưu cả:
- Actor thực tế là service.
- Subject được impersonate.
- Lý do.
- Approval hoặc ticket.
- Scope và expiry.

Không nên thay thế actor identity bằng user identity vì sẽ làm mất dấu nguồn thực hiện thao tác.

### 17.3. On-behalf-of

Một service có thể gọi service khác thay mặt user. Token exchange hoặc delegated credential cần giữ chain of delegation và audience đúng.

### 17.4. Service-to-service authorization

Service account cần quyền riêng theo workload identity. Không nên dùng chung một admin credential cho mọi service.

### 17.5. Background jobs

Job chạy sau khi user gửi request cần quyết định:
- Quyền được snapshot tại thời điểm enqueue hay kiểm tra lại lúc execute?
- Nếu role bị thu hồi trong lúc chờ, job có được tiếp tục không?
- Job chạy dưới user identity, service identity hay delegated context?
- Ai chịu trách nhiệm audit?

Với thao tác nhạy cảm, thường cần kiểm tra lại quyền và trạng thái resource khi thực thi.

## 18. Multi-tenancy và isolation

Trong hệ thống multi-tenant, tenant boundary là một phần của authorization.

Policy cần kiểm tra tenant của principal và resource:

~~~text
permit read Document when
    principal.tenantId == resource.tenantId
~~~

### 18.1. Tenant context

Tenant context phải được xác định từ authentication/session hoặc trusted routing metadata. Không tin tenant ID chỉ vì client đưa vào query hoặc request body.

### 18.2. Cross-tenant operations

Thao tác cross-tenant như support access hoặc global administration cần permission đặc biệt, scope hẹp, thời hạn và audit đầy đủ.

### 18.3. Data isolation

Authorization cần kết hợp với data isolation ở storage layer. Một query thiếu tenant predicate có thể làm lộ dữ liệu ngay cả khi endpoint policy đã kiểm tra tenant ở một bước khác.

### 18.4. Cache isolation

Decision cache phải bao gồm tenant, principal, resource, action, policy version và các attribute ảnh hưởng quyết định. Không được dùng cache key quá rộng khiến permit của tenant này áp dụng sang tenant khác.

## 19. Policy versioning và lifecycle

Policy là logic bảo mật nên cần được quản lý như code quan trọng.

Lifecycle có thể gồm:

~~~text
Draft
  |
  v
Review
  |
  v
Test / Simulate
  |
  v
Approve
  |
  v
Publish
  |
  v
Monitor
  |
  +----> Rollback
~~~

### 19.1. Immutable policy version

Mỗi lần publish nên tạo version bất biến. Execution cần ghi policy version được dùng để có thể giải thích và tái lập quyết định.

### 19.2. Policy change review

Thay đổi role, permission, condition hoặc combining algorithm có thể mở rộng quyền. Nên review:
- Ai được cấp thêm quyền?
- Resource scope có rộng hơn không?
- Có tạo conflict với deny policy không?
- Có ảnh hưởng tenant khác không?
- Có làm mất separation of duties không?

### 19.3. Simulation và dry run

Có thể chạy policy mới trên tập request mẫu hoặc log đã redacted để so sánh decision trước/sau mà chưa áp dụng. Kết quả simulation cần phân biệt rõ với decision thực tế.

### 19.4. Rollback

Rollback policy cần tạo revision mới tham chiếu version đã biết là an toàn, đồng thời audit ai yêu cầu và ai phê duyệt. Không xóa lịch sử policy gây sự cố.

### 19.5. Emergency access

Break-glass access cần:
- Permission rất hẹp.
- Expiry ngắn.
- MFA hoặc approval bổ sung.
- Lý do bắt buộc.
- Audit và alert.
- Review sau khi sử dụng.

Không nên tạo một role admin vĩnh viễn dùng cho mọi trường hợp khẩn cấp.

## 20. Caching và thu hồi quyền

Authorization decision có thể được cache để giảm latency, nhưng cache có thể giữ permit sau khi quyền đã bị thu hồi.

### 20.1. Cache key

Cache key cần bao gồm các thành phần ảnh hưởng quyết định:
- Principal ID.
- Action.
- Resource ID/type.
- Tenant.
- Policy version.
- Relevant attribute version.
- Context dimensions như environment hoặc time window.

### 20.2. TTL

TTL ngắn giảm thời gian stale nhưng tăng tải lên PDP. TTL phải phù hợp mức rủi ro và tốc độ thay đổi quyền.

### 20.3. Invalidation

Khi role assignment, resource ownership hoặc policy đổi, cần invalidation theo principal/resource/policy dependency. Pub/sub invalidation có thể hỗ trợ nhưng cần xử lý message bị mất hoặc trễ.

### 20.4. Revocation-sensitive operations

Đối với thao tác như payment, delete hoặc admin action, có thể cần re-check trực tiếp trước commit thay vì chỉ tin decision cache.

### 20.5. Time-based policies

Nếu policy phụ thuộc giờ làm việc hoặc expiry, cache entry không được sống quá thời điểm điều kiện thay đổi. Cache expiration cần xét policy boundary tiếp theo.

## 21. Audit và giải thích quyết định

Một authorization decision quan trọng nên có audit record.

Ví dụ:

~~~json
{
  "decisionId": "authz-42",
  "principal": "user:42",
  "action": "orders.approve",
  "resource": "order:ORD-100",
  "tenant": "tenant:acme",
  "decision": "DENY",
  "reasonCode": "BRANCH_SCOPE_MISMATCH",
  "policyVersion": "policy-18",
  "timestamp": "2026-11-15T10:00:00Z"
}
~~~

### 21.1. Decision explanation

Explanation có thể nêu:
- Policy nào áp dụng.
- Điều kiện nào đúng/sai.
- Role hoặc relationship nào được xét.
- Attribute nào thiếu hoặc không hợp lệ.
- Combining algorithm nào tạo kết quả cuối.
- Obligation nào cần thực hiện.

### 21.2. Không log quá nhiều dữ liệu

Audit cần đủ để điều tra nhưng không nên ghi password, token, secret hoặc toàn bộ request body nhạy cảm. Có thể lưu ID, reason code và reference đến record được bảo vệ.

### 21.3. Tamper resistance

Audit store nên có access control chặt, retention policy và integrity protection. Người có quyền sửa policy không nên có thể xóa dấu vết decision của chính mình.

### 21.4. Correlation

Decision ID có thể liên kết với request ID, workflow instance, transaction ID và execution trace. Nhờ đó có thể truy ngược từ sự kiện nghiệp vụ đến quyết định authorization.

## 22. Error handling và trải nghiệm người dùng

Khi bị từ chối, API hoặc DSL runtime cần trả kết quả nhất quán.

Các response có thể phân biệt:
- Unauthenticated: chưa xác thực hoặc credential không hợp lệ.
- Forbidden: đã xác thực nhưng không được phép.
- Not found: tài nguyên không tồn tại hoặc bị ẩn theo policy.
- Conflict: trạng thái tài nguyên không cho phép thao tác.
- Indeterminate: không thể đánh giá quyền do dependency lỗi.

Không nên tiết lộ policy nội bộ, tên role nhạy cảm hoặc attribute của người khác trong error message.

### 22.1. Reason codes

Có thể dùng code ổn định như:
- PERMISSION_MISSING.
- RESOURCE_SCOPE_MISMATCH.
- TENANT_MISMATCH.
- RESOURCE_STATE_NOT_ALLOWED.
- POLICY_EVALUATION_FAILED.
- OBLIGATION_NOT_SATISFIED.
- AUTHENTICATION_REQUIRED.

Message hiển thị cho user có thể đơn giản hơn explanation dành cho administrator.

### 22.2. Không tiết lộ resource existence

Trong một số hệ thống, trả 403 sẽ tiết lộ rằng resource tồn tại. Policy có thể trả 404 để che sự tồn tại. Đây phải là lựa chọn có chủ đích và nhất quán, không phải hành vi ngẫu nhiên.

### 22.3. Retry

Nếu decision bị từ chối do thiếu quyền, retry ngay thường không có ích. Nếu Indeterminate do timeout, client có thể retry theo policy. Cần phân biệt hai trường hợp.

## 23. Bảo vệ policy engine và policy language

Policy engine xử lý logic bảo mật, vì vậy bản thân nó cũng là bề mặt tấn công.

Các nguyên tắc:
- Policy syntax có grammar rõ.
- Static type checking cho attribute và operator.
- Không arbitrary code execution.
- Không reflection không kiểm soát.
- Không network/file I/O trực tiếp trong expression.
- Giới hạn evaluation time và recursion.
- Giới hạn graph traversal depth.
- Giới hạn số lượng policy và expression complexity.
- Escape và validate external input.
- Version policy và dependency.
- Không cho principal tự sửa attribute đáng tin cậy.
- Kiểm tra policy compiler/runtime compatibility.

### 23.1. Policy injection

Không nối chuỗi input người dùng vào policy source. Dùng typed parameters hoặc AST construction để tránh injection.

### 23.2. Confused deputy

Một service có quyền rộng có thể bị lừa thực hiện thao tác thay mặt user không có quyền. PEP cần truyền principal/actor context đúng và policy phải xét cả delegator lẫn service identity khi cần.

### 23.3. TOCTOU

Quyền có thể thay đổi giữa lúc check và lúc thao tác. Với update nhạy cảm, nên kiểm tra trong cùng transaction hoặc ràng buộc commit với version của resource/policy.

### 23.4. Policy denial of service

Policy expression hoặc relationship graph quá phức tạp có thể làm PDP tốn CPU và memory. Cần timeout, complexity budget, bounded traversal và cancellation.

## 24. Kiểm thử phân quyền

### 24.1. Unit tests cho policy

Mỗi policy cần test:
- Principal có role hợp lệ.
- Principal thiếu role.
- Resource thuộc cùng tenant.
- Resource thuộc tenant khác.
- Attribute boundary.
- Resource ở trạng thái cho phép và không cho phép.
- Context thiếu hoặc sai.

### 24.2. Role matrix tests

Tạo ma trận role/action/resource:

| Role | Read | Update | Approve | Delete |
|---|---:|---:|---:|---:|
| Viewer | Permit | Deny | Deny | Deny |
| Operator | Permit | Permit | Deny | Deny |
| Approver | Permit | Deny | Permit | Deny |
| Administrator | Permit | Permit | Permit | Permit theo scope |

Ma trận chỉ là ví dụ; cần kiểm tra thêm resource scope và tenant.

### 24.3. Negative tests

Negative tests quan trọng không kém positive tests:
- User không thuộc tenant.
- User bị thu hồi role.
- Token hết hạn.
- Resource owner thay đổi.
- Policy store lỗi.
- Attribute provider timeout.
- Context do client giả mạo.
- Capability hết hạn hoặc bị thu hồi.

### 24.4. Integration tests

Kiểm tra PEP ở từng đường truy cập:
- API endpoint.
- DSL operation dispatcher.
- Background job.
- Plugin call.
- Direct data access.
- Admin console.
- Batch execution.

Một policy unit test đúng không chứng minh mọi route đều enforce policy.

### 24.5. Property-based tests

Có thể kiểm tra các invariant:
- Không principal nào truy cập tenant khác nếu không có cross-tenant permission.
- Deny policy không bị permit policy ghi đè khi dùng deny-overrides.
- Quyền hết hạn không được cache quá thời điểm hết hạn.
- Delegation không mở rộng quyền.
- Resource state không hợp lệ luôn chặn transition tương ứng.

### 24.6. Policy regression tests

Khi policy thay đổi, chạy lại corpus request đại diện và so sánh decision trước/sau. Những thay đổi quyền bất ngờ cần được review.

### 24.7. Penetration và bypass tests

Thử gọi trực tiếp handler, sửa resource ID, đổi tenant, bỏ qua UI, gọi plugin hoặc sử dụng endpoint phụ để tìm đường bypass enforcement.

## 25. Hiệu năng và khả năng mở rộng

Authorization thường nằm trên đường request chính, vì vậy latency và throughput rất quan trọng.

Các điểm cần cân nhắc:
- Cache policy đã compile.
- Cache decision theo context đầy đủ.
- Batch attribute lookup.
- Batch relationship query.
- Index resource ownership và membership.
- Giới hạn graph traversal.
- Tránh gọi network tuần tự cho từng attribute.
- Hỗ trợ cancellation và deadline.
- Đo PDP latency p50/p95/p99.
- Theo dõi cache hit/miss và Indeterminate rate.

### 25.1. Decision caching và correctness

Cache không được bỏ qua policy version, tenant hoặc resource identity. Nếu thiếu một dimension, permit của request này có thể bị tái sử dụng sai cho request khác.

### 25.2. Batch authorization

Một API trả danh sách tài nguyên có thể cần kiểm tra quyền cho nhiều item. Batch API giảm round trips nhưng cần bảo đảm mỗi resource được kiểm tra độc lập và kết quả không làm lộ item ngoài quyền.

### 25.3. Attribute fetching

PIP có thể truy vấn nhiều nguồn. Có thể song song hóa các lookup độc lập, nhưng cần timeout, fallback semantics và nguồn authoritative rõ ràng.

### 25.4. Observability

Metric hữu ích:
- authorization_decisions_total theo decision/reason class.
- policy_evaluation_duration.
- policy_evaluation_errors.
- decision_cache_hit_ratio.
- attribute_lookup_duration.
- relationship_query_duration.
- obligation_failures.

Không nên dùng raw user ID hoặc resource ID làm metric label vì cardinality cao. Chi tiết theo request nên nằm trong audit/trace có kiểm soát.

## 26. Kiến trúc tổng thể cho phân quyền thao tác

Một kiến trúc khái niệm:

~~~text
DSL Source / Operation Definitions
              |
              v
      Parser and Type Checker
              |
              v
       Policy Model / AST
              |
              v
        Policy Compiler
              |
              v
         Policy Store
              |
              v
Request ---> PEP ---> PDP
                 |      |
                 |      +---- Policy evaluation
                 |      +---- Attribute providers
                 |      +---- Relationship store
                 |      +---- Role/permission data
                 |
                 v
         Permit / Deny
                 |
                 v
       Operation Dispatcher
                 |
                 v
       Resource / Host Service
                 |
                 v
           Audit / Trace
~~~

### 26.1. Policy compiler

Compiler kiểm tra syntax, type, references, role hierarchy và policy consistency. Có thể tạo executable policy representation đã được giới hạn.

### 26.2. Policy store

Lưu policy versions, status, owner, approval và deployment metadata.

### 26.3. Authorization service

PDP evaluate decision và có thể trả obligations. PEP enforce decision trước khi gọi handler.

### 26.4. Operation dispatcher

Dispatcher chỉ gọi operation sau khi authorization thành công. Operation handler không nên tin một boolean do client gửi.

### 26.5. Resource service

Data access layer cần bảo đảm resource scope và tenant filter được áp dụng ngay cả khi operation được gọi từ nhiều entry points.

### 26.6. Audit pipeline

Audit ghi decision, policy version, actor, action, resource và correlation ID theo retention/access policy.

## 27. Ví dụ end-to-end: phê duyệt đơn hàng

Giả sử DSL định nghĩa:

~~~text
permission "orders.read"
permission "orders.approve"

role "OrderApprover" {
    grant "orders.read"
    grant "orders.approve"
}

policy "approve-order" {
    permit action "orders.approve"
    on resource Order
    when
        principal.hasRole("OrderApprover")
        and principal.tenantId == resource.tenantId
        and principal.branchId == resource.branchId
        and resource.status == "PENDING"
        and principal.id != resource.createdBy
}

operation "approveOrder" {
    resource: Order
    action: "orders.approve"
    authorization: "approve-order"
    handler: OrderService.approve
}
~~~

### 27.1. Request

User 42 yêu cầu approve order ORD-100. Context xác thực cho biết:
- User 42 có role OrderApprover.
- User thuộc tenant ACME.
- User thuộc branch NORTH.
- Order thuộc tenant ACME.
- Order thuộc branch NORTH.
- Order đang PENDING.
- User không phải người tạo order.

### 27.2. Decision

Tất cả điều kiện permit đều đúng. PDP trả Permit. PEP cho phép operation dispatcher gọi OrderService.approve.

### 27.3. Request bị từ chối

Nếu order thuộc branch SOUTH, policy trả Deny vì branch mismatch. PEP không gọi handler.

### 27.4. Kiểm tra lại trước commit

Nếu order chuyển sang APPROVED sau khi PDP đánh giá nhưng trước khi cập nhật, handler cần kiểm tra version/state trong transaction. Không được approve lần hai chỉ vì decision trước đó là Permit.

### 27.5. Audit

Audit event nên ghi:
- Actor user 42.
- Action orders.approve.
- Resource order ORD-100.
- Decision và reason code.
- Policy version.
- Resource version.
- Request/correlation ID.
- Operation result.

Không ghi toàn bộ token hoặc dữ liệu nhạy cảm của order.

## 28. Những sai lầm thường gặp

1. **Chỉ ẩn nút trên UI:** API hoặc runtime vẫn có thể bị gọi trực tiếp.
2. **Nhầm authentication với authorization:** user đã đăng nhập bị coi là có mọi quyền.
3. **Permission quá rộng:** một quyền manage gộp read, update, delete và approve.
4. **Không kiểm tra resource scope:** role hợp lệ nhưng truy cập nhầm tài nguyên.
5. **Tin attribute từ client:** tenant, owner hoặc role bị giả mạo.
6. **Không default deny:** policy không match lại được cho phép.
7. **Fail open khi PDP lỗi:** sự cố hạ tầng trở thành bypass.
8. **Chỉ kiểm tra ở API gateway:** internal handler hoặc plugin có thể bypass.
9. **Không phân biệt actor và subject:** audit mất dấu service impersonation.
10. **Cache decision thiếu context:** permit bị tái sử dụng sai tenant/resource.
11. **Không re-check khi commit:** TOCTOU làm thao tác vượt trạng thái hiện tại.
12. **Không thu hồi capability:** token cũ tiếp tục có quyền ngoài ý muốn.
13. **Role hierarchy không kiểm tra cycle:** permission inheritance sai hoặc vô hạn.
14. **Policy có side effect:** quyết định quyền làm thay đổi hệ thống trước khi enforcement.
15. **Không version policy:** không giải thích được quyết định trong quá khứ.
16. **Audit chứa secret:** log bảo mật trở thành nguồn rò rỉ dữ liệu.
17. **Không test negative path:** chỉ chứng minh user hợp lệ được phép.
18. **Bỏ qua background jobs:** job chạy sau khi quyền user đã bị thu hồi.

## 29. Quy trình triển khai phân quyền thao tác

Một quy trình triển khai có thể gồm:

1. **Liệt kê operations:** xác định action, resource type và side effects của từng operation.
2. **Xác định principal model:** user, group, service, workload và delegated identity.
3. **Thiết kế permission catalog:** dùng action rõ nghĩa và mức granularity phù hợp.
4. **Chọn access-control models:** RBAC, ABAC, ReBAC, capability hoặc kết hợp.
5. **Định nghĩa resource scopes:** tenant, owner, organization, project và instance.
6. **Thiết kế policy language:** typed attributes, pure expressions, default deny và combining semantics.
7. **Xác định enforcement points:** API, DSL dispatcher, data layer, plugin và background job.
8. **Xây PEP/PDP/PAP/PIP:** tách quyết định, thực thi, quản trị và attribute lookup.
9. **Bảo đảm fail-safe:** xử lý timeout, missing attributes, stale policy và Indeterminate.
10. **Thiết kế delegation và service identity:** giữ actor chain, scope và expiry.
11. **Tích hợp workflow state:** kiểm tra transition và re-check trước commit.
12. **Xây audit/explanation:** reason codes, policy version, correlation và tamper resistance.
13. **Quản lý policy lifecycle:** review, simulation, publish, monitor và rollback.
14. **Thiết kế cache/revocation:** cache key đầy đủ, TTL và invalidation.
15. **Kiểm thử:** positive, negative, tenant isolation, bypass, concurrency và policy regression.
16. **Đo vận hành:** latency, error rate, cache hit, attribute lookup và audit completeness.
17. **Triển khai theo phạm vi nhỏ:** quan sát decision trước, enforce có kiểm soát, rồi mở rộng theo resource/action.

## 30. Kết luận

Phân quyền thao tác trong DSL xác định chủ thể nào được thực hiện hành động nào trên tài nguyên nào trong một ngữ cảnh cụ thể. Một mô hình đáng tin cậy cần principal identity, action và resource rõ ràng, context đáng tin cậy, policy semantics xác định và enforcement tại mọi đường truy cập.

RBAC phù hợp để quản lý quyền theo vai trò; ABAC biểu đạt điều kiện theo thuộc tính; ReBAC kiểm tra quan hệ; capability cấp quyền hẹp cho một thao tác hoặc tài nguyên. Các mô hình có thể kết hợp, nhưng phải có default deny, fail-safe behavior, scope và combining rules rõ ràng. Policy cần được version, review, audit và kiểm thử cả đường được phép lẫn đường bị từ chối. Khi authorization được thực thi ở runtime, data layer và DSL operation dispatcher, hệ thống có thể bảo vệ dữ liệu và hành động một cách nhất quán.

