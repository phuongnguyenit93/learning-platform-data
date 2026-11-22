# Resource authorization — Kiểm tra quyền trên đúng tài nguyên

## 1. Được gọi chức năng chưa có nghĩa được thao tác mọi tài nguyên

**Resource authorization** là việc xác định một chủ thể có được thực hiện một hành động cụ thể trên một tài nguyên cụ thể, trong ngữ cảnh hiện tại hay không.

Ví dụ, người có chức năng xem đơn mua hàng chưa chắc được xem đơn của phòng ban khác. Người được đọc một đơn chưa chắc được sửa giá hoặc phê duyệt nó. Một reviewer có quyền tại tenant A không tự có quyền trên đơn thuộc tenant B.

Bài thuộc chương **Authorization Rules** của module `SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY`. Trọng tâm là bảo vệ quy tắc nghiệp vụ trước thao tác sai quyền, sửa dữ liệu quan trọng, bỏ qua phê duyệt và gửi yêu cầu trùng. Quyền theo tài nguyên phải phối hợp với business invariants, state machine, transaction và idempotency.

Xét API:

```http
POST /projects/{projectId}/purchase-orders/{orderId}/approve
```

Kiểm tra `hasRole("REVIEWER")` mới cho biết người gọi có thể sử dụng một loại chức năng. Backend còn phải xác minh:

- Đơn tồn tại trong đúng tenant và thực sự thuộc project trên đường dẫn.
- Người gọi có quan hệ hoặc grant cho phép `APPROVE` trên chính đơn đó.
- Quyền/grant vẫn phù hợp với chính sách tại thời điểm quyết định.
- Điều kiện nghiệp vụ như trạng thái nguồn, người duyệt độc lập và hạn mức vẫn đúng.
- Lệnh không được thực hiện thêm lần nữa chỉ vì client retry.

OWASP gọi việc thao tác đối tượng ngoài phạm vi được cấp quyền thông qua ID là Broken Object Level Authorization, thường viết tắt BOLA. ID dạng UUID cũng có thể bị khai thác; biết hoặc đoán được ID không phải bằng chứng được phép truy cập. [OWASP API1: Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

## 2. Mô hình chủ thể, hành động, tài nguyên và ngữ cảnh

Có thể biểu diễn quyết định bằng hàm:

```text
authorize(subject, action, resource, context)
    -> ALLOW hoặc DENY, kèm căn cứ và ràng buộc cần thực thi.
```

| Thành phần | Ví dụ | Nguồn có thẩm quyền |
| --- | --- | --- |
| Subject — chủ thể | Principal đang đăng nhập, service được ủy quyền | Cơ chế xác thực đã kiểm chứng và ngữ cảnh danh tính tin cậy |
| Action — hành động | `READ`, `EDIT_DRAFT`, `APPROVE`, `EXPORT` | Operation backend đang xử lý; không nhận một cờ quyền tùy ý từ client |
| Resource — tài nguyên | Đơn mua hàng cụ thể với tenant, project, chủ thể yêu cầu, version | Dữ liệu server/database có thẩm quyền |
| Relationship — quan hệ | Người yêu cầu, reviewer được phân công, người được chia sẻ | Dữ liệu quan hệ/grant do hệ thống quản lý |
| Context — ngữ cảnh | Tenant đang hoạt động, thời gian, mức xác thực, policy version | Giá trị đã xác minh theo chính sách |

Client cung cấp ID để **chọn** tài nguyên muốn thao tác. Client không có quyền định nghĩa rằng tài nguyên đó thuộc tenant nào hoặc người gọi sở hữu nó.

Ví dụ request body chứa `owner_id`, `tenant_id`, `is_admin = true` hoặc `can_approve = true` không làm các thuộc tính đó trở thành sự thật. Backend phải lấy chủ sở hữu, tenant và quyền từ nguồn có thẩm quyền.

### 2.1. Kết hợp role với quan hệ và thuộc tính

- RBAC hỗ trợ quyền chức năng như được sử dụng chức năng phê duyệt.
- Quan hệ đối tượng xác định người này là requester hoặc reviewer của đơn nào.
- Thuộc tính tài nguyên và ngữ cảnh bổ sung điều kiện như tenant, độ nhạy cảm, số tiền hoặc thời hạn grant.

Một policy thực tế có thể dùng cả ba. Không cần chọn một nhãn mô hình rồi bỏ qua những dữ kiện nghiệp vụ còn lại.

### 2.2. Mặc định từ chối và thực thi nhất quán

Nếu không có quy tắc cho phép rõ ràng cho action/resource hiện tại thì từ chối. Action mới, loại tài nguyên mới hoặc dữ liệu quyền chưa đủ không được rơi vào một nhánh mặc định cho phép.

Quy tắc cũng cần áp dụng trên mọi đường gọi tạo ra cùng hành động: REST, GraphQL, giao diện quản trị, batch, job và service nội bộ. OWASP khuyến nghị deny by default và kiểm tra quyền trên mọi request, thay vì chỉ dựa vào việc giao diện có hiển thị chức năng hay không. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

## 3. Viết policy theo từng action trước khi viết endpoint

Giả sử hệ thống có tenant, project và đơn mua hàng. Chính sách minh họa:

| Action | Quyền/quan hệ trên tài nguyên | Điều kiện hoặc giới hạn bổ sung |
| --- | --- | --- |
| `READ` | Thành viên tenant đang hoạt động và là requester, reviewer còn được phân công hoặc có grant đọc trực tiếp | Chỉ trả các trường được phép xem |
| `EDIT_DRAFT` | Thành viên tenant đang hoạt động, có quyền sửa yêu cầu của mình và là requester của đơn | Đơn ở `DRAFT`; chỉ sửa tập trường được phép |
| `APPROVE` | Thành viên tenant đang hoạt động, có capability phê duyệt và assignment reviewer trên đơn | Kiểm tra trạng thái, tính độc lập, version nội dung, hạn mức và thời gian nếu policy yêu cầu |
| `EXPORT` | Có quyền xuất với phạm vi cụ thể | Mỗi tài nguyên phải nằm trong phạm vi xuất/đọc cho phép; dữ liệu xuất có projection phù hợp |
| `SHARE` | Có quyền quản lý chia sẻ trên tài nguyên | Không được cấp action hoặc thời hạn vượt thẩm quyền được phép cấp |
| `CREATE_ORDER` | Có quyền tạo trong project/collection đích | Server đặt tenant và creator; kiểm tra các tài nguyên được tham chiếu |

Trong ví dụ này, grant `READ` không hàm ý grant `APPROVE`. Quyền sửa draft không bao gồm sửa `tenant_id`, requester, trạng thái phê duyệt hay tổng tiền có thẩm quyền.

Chính sách của hệ thống khác có thể cho auditor đọc một tập tài nguyên rộng hơn. Khi đó quyền auditor phải có phạm vi rõ, ví dụ một tenant hoặc project, không biến thành quyền đọc toàn hệ thống vì một chuỗi role chung.

### 3.1. Quyền trên tài nguyên và invariant nghiệp vụ cùng phải đúng

Có thể diễn đạt:

```text
Chấp nhận một lần phê duyệt mới
    = có quyền APPROVE trên đúng đơn
    AND trạng thái/version/nội dung phù hợp
    AND các invariant nghiệp vụ được thỏa mãn
    AND lần ghi được thực hiện nhất quán dưới concurrency.
```

Một số hệ thống đưa trạng thái hoặc hạn mức vào policy authorization; hệ thống khác đặt ở domain rule. Cách tổ chức code có thể khác, nhưng không được có khoảng trống khiến một lớp giả định lớp khác đã kiểm tra mà thực tế không lớp nào làm.

Trả về `ALLOW` không có nghĩa được bỏ qua state machine hoặc transaction. Tương tự, lệnh chuyển trạng thái hợp lệ về mặt kỹ thuật vẫn phải bị chặn nếu người gọi không có quyền trên đối tượng.

## 4. Tenant, tài nguyên cha/con và ID do client cung cấp

### 4.1. Tenant được chọn phải được xác minh

Một người có thể tham gia nhiều tenant và chọn tenant hoạt động trong URL hoặc header. Giá trị được chọn vẫn là đầu vào cần kiểm tra:

1. Xác thực principal từ nguồn tin cậy.
2. Xác minh principal được phép làm việc trong tenant được chọn.
3. Truy vấn tài nguyên trong tenant đó.
4. Kiểm tra quyền action trên chính tài nguyên.

Không chỉ đọc `X-Tenant-Id` rồi coi đó là phạm vi đã được xác thực. Cũng không mặc định một JWT chứa danh tính người dùng đồng nghĩa mọi tenant ID trong request đều hợp lệ.

### 4.2. Quan hệ trên đường dẫn phải khớp dữ liệu thật

Với đường dẫn:

```text
/projects/P1/purchase-orders/O2/attachments/A3
```

Backend phải kiểm tra O2 thực sự thuộc P1 và A3 thực sự thuộc O2 trong đúng tenant. Kiểm tra quyền trên P1 rồi tải A3 bằng ID độc lập có thể làm lộ attachment của tài nguyên khác.

Truy vấn lấy đơn có thể giới hạn đồng thời:

```sql
SELECT o.*
FROM purchase_order o
WHERE o.tenant_id = :verified_tenant_id
  AND o.project_id = :project_id
  AND o.id = :order_id;
```

Truy vấn này xác minh phạm vi và quan hệ của ID. Nó **chưa tự chứng minh** người gọi được đọc hay phê duyệt đơn nếu policy còn yêu cầu owner, assignment hoặc grant.

Ở schema, composite foreign key như `(tenant_id, project_id)` có thể hỗ trợ ngăn một đơn tham chiếu project thuộc tenant khác. Ràng buộc quan hệ dữ liệu và quyền của principal là hai yêu cầu bổ sung cho nhau.

### 4.3. Mỗi ID tham chiếu có thể là một điểm cần kiểm tra quyền

Không chỉ ID trên URL mới quan trọng. Body có thể chứa `supplier_id`, `budget_account_id`, `attachment_id`, ID bản mẫu hoặc danh sách đơn cần thao tác.

Ví dụ tạo đơn trong project hợp lệ nhưng gắn tài khoản ngân sách của phòng ban khác vẫn có thể là lạm dụng nghiệp vụ. Backend phải kiểm tra quyền sử dụng tài nguyên được tham chiếu và tính hợp lệ của quan hệ, không chỉ kiểm tra ID có tồn tại.

Tương tự, clone cần quyền đọc nguồn và tạo ở đích. Chuyển tài nguyên sang project khác cần quyền phù hợp ở cả nguồn và đích, đồng thời xét tác động lên quyền chia sẻ và lịch sử.

## 5. Kiểm tra quyền cho đọc đơn lẻ và danh sách

### 5.1. Hai cách tổ chức phổ biến

**Truy vấn đã giới hạn quyền:** repository nhận principal, action và phạm vi đã xác minh, chỉ trả tài nguyên được phép. Cách này phù hợp với danh sách và nhiều đường đọc.

**Tải nội bộ rồi kiểm tra:** application service lấy dữ liệu cần thiết trong phạm vi tenant, đánh giá policy, sau đó mới trả dữ liệu hoặc tạo tác dụng. Cách này hữu ích khi policy phức tạp hoặc cần khóa để ghi.

Ở cách thứ hai, entity đã tải vẫn là dữ liệu nội bộ chưa được phép phát hành. Không serialize, đưa vào log đầy đủ hoặc gửi sang nơi khác trước khi kiểm tra quyền. Tên hàm như `findById` cũng không nên bị hiểu ngầm là “đã kiểm tra quyền”.

### 5.2. Ví dụ truy vấn danh sách có phạm vi quyền

Giả sử có các bảng:

- `purchase_order`: đơn với tenant, project và requester.
- `tenant_membership`: principal có còn là thành viên tenant hay không.
- `reviewer_assignment`: phân công reviewer đang hoạt động trên đơn.
- `resource_grant`: grant trực tiếp cho một principal, action và tài nguyên, có thời hạn/thu hồi.

Truy vấn dưới đây thể hiện policy `READ` của ví dụ:

```sql
SELECT o.id, o.project_id, o.state,
       o.total_minor_units, o.currency
FROM purchase_order o
WHERE o.tenant_id = :verified_tenant_id
  AND o.project_id = :project_id
  AND EXISTS (
      SELECT 1
      FROM tenant_membership tm
      WHERE tm.tenant_id = o.tenant_id
        AND tm.principal_id = :trusted_principal_id
        AND tm.state = 'ACTIVE'
  )
  AND (
      o.requester_principal_id = :trusted_principal_id
      OR EXISTS (
          SELECT 1
          FROM reviewer_assignment a
          WHERE a.tenant_id = o.tenant_id
            AND a.order_id = o.id
            AND a.principal_id = :trusted_principal_id
            AND a.active = true
      )
      OR EXISTS (
          SELECT 1
          FROM resource_grant g
          WHERE g.tenant_id = o.tenant_id
            AND g.resource_type = 'PURCHASE_ORDER'
            AND g.resource_id = o.id
            AND g.principal_id = :trusted_principal_id
            AND g.action = 'READ'
            AND g.revoked_at IS NULL
            AND g.valid_from <= :authorization_at
            AND (
                g.valid_until IS NULL
                OR :authorization_at < g.valid_until
            )
      )
  )
  AND (:after_id IS NULL OR o.id > :after_id)
ORDER BY o.id
LIMIT :page_size;
```

`:trusted_principal_id` đến từ xác thực; tenant đã được chọn/xác minh; `authorization_at` là thời gian server có thẩm quyền theo policy, không phải thời gian client tự khai. Page size có giới hạn. Các tham số được bind, không ghép chuỗi SQL từ đầu vào.

Trong policy này, requester hoặc reviewer vẫn phải có membership tenant đang hoạt động. Các nhánh `OR` được nhóm bên trong điều kiện tenant/membership bắt buộc. Viết sai thành `tenant = T AND owner = U OR reviewer = U` có thể làm nhánh reviewer thoát khỏi điều kiện tenant.

Đây là ví dụ truy vấn, không phải một schema hay chương trình hoàn chỉnh. Các grant khác, quyền kế thừa, explicit deny và trạng thái tài nguyên nếu được hỗ trợ phải được mô hình hóa nhất quán; không thêm một nhánh `OR admin` không có phạm vi.

### 5.3. Lọc trước khi phân trang và tổng hợp

Không tải một trang chứa tài nguyên của mọi người rồi lọc quyền ở Java. Cách đó dễ làm sai pagination, lộ tổng số và khiến những trang của người dùng bị thiếu dù còn bản ghi được phép ở phía sau.

`COUNT`, tìm kiếm, dashboard, báo cáo và export phải dùng phạm vi quyền tương ứng. Tổng tiền hoặc số lượng tài nguyên bị cấm cũng có thể là dữ liệu nhạy cảm dù không trả từng hàng.

Cursor chỉ là thông tin vị trí, không phải giấy phép truy cập. Mỗi lần lấy trang tiếp theo vẫn kiểm tra chủ thể, tenant và quyền hiện tại theo policy. Không cho cursor hoặc tham số sort/filter tùy ý mở đường đọc thuộc tính bị cấm.

Nếu truy vấn danh sách và hàm kiểm tra đơn lẻ dùng hai bản policy khác nhau, cần cơ chế duy trì tính tương đương và kiểm thử chéo. Một đường trả ít hơn có thể gây lỗi chức năng; một đường trả nhiều hơn có thể là lỗ hổng.

## 6. Quyền trên thuộc tính và dữ liệu trả về

### 6.1. Được đọc object không có nghĩa được đọc mọi field

Một reviewer có thể cần xem tổng tiền nhưng không được xem ghi chú điều tra nội bộ. Requester được sửa nội dung draft nhưng không được tự đặt `approved_by`, `approval_state` hoặc `tenant_id`.

OWASP phân biệt quyền trên thuộc tính đối tượng với quyền trên chính đối tượng; việc lộ field nhạy cảm hoặc cho phép cập nhật field không được phép đều là vấn đề cần kiểm soát. [OWASP API3: Broken Object Property Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/).

Áp dụng DTO và projection có chủ đích:

```java
public record EditDraftCommand(
    UUID orderId,
    long expectedVersion,
    List<RequestedLine> lines,
    String requesterComment
) {}
```

Command chỉ diễn tả dữ liệu được phép đề nghị thay đổi. Đơn giá có thẩm quyền, tổng tiền, tenant, creator và trạng thái phê duyệt được server xác định hoặc thay đổi qua action riêng.

Nếu nghiệp vụ cho sửa giá thủ công, đó phải là quyền/điều kiện được định nghĩa rõ, không phải hệ quả vô tình của việc bind mọi field từ JSON vào entity.

### 6.2. Ràng buộc đi kèm quyết định phải được thực thi

Policy có thể trả `ALLOW` kèm yêu cầu ẩn một số field, chỉ cho tải bản đã che dữ liệu hoặc giới hạn phạm vi export. Service tạo response phải thực thi những ràng buộc đó.

Nếu caller chỉ đọc boolean `allowed` rồi serialize toàn bộ entity, các ràng buộc trả về không có tác dụng. Có thể dùng kiểu kết quả phân biệt projection hoặc lớp mapping bắt buộc nhận quyết định quyền để giảm lỗi bỏ sót.

Không dùng cùng một response cache cho người có quyền xem đầy đủ và người chỉ được xem bản che. Tên field không xuất hiện trên UI cũng không bảo vệ nếu API vẫn trả field đó.

## 7. Kiểm tra quyền ở đường ghi và ranh giới transaction

### 7.1. Tránh kiểm tra một bản rồi ghi một bản khác

Luồng sau có khoảng trống:

```java
authorization.requireApprove(actor, orderRepository.findById(id));

// Có thể có thay đổi dữ liệu/quyền giữa hai bước.
orderRepository.approveWithoutVersionCheck(id);
```

Nếu tenant, assignment, số tiền hoặc version dữ liệu thay đổi, lần ghi có thể sử dụng một quyết định quyền không còn phù hợp. Bên cạnh đó, kiểm tra quyền và cập nhật trạng thái tách rời dễ khiến audit mô tả sai nội dung thực tế được duyệt.

Với mô hình một database, có thể giữ transaction ngắn, khóa tài nguyên cần thay đổi, đọc facts có thẩm quyền và ghi có điều kiện. Những bảng quyền liên quan cần mức nhất quán phù hợp chính sách thu hồi quyền của hệ thống.

### 7.2. Khung Java cho phê duyệt đơn

Ví dụ dùng `TransactionTemplate` của Spring; repository, resolver và policy là hợp đồng minh họa, chưa phải chương trình hoàn chỉnh có thể chép chạy ngay.

```java
public ApprovalReceipt approve(ApproveOrderCommand cmd, TrustedActor actor) {
    return transactions.execute(tx -> {
        VerifiedTenant tenant = tenantAccess.requireActiveMembership(
            actor, cmd.selectedTenantId());

        PurchaseOrder order = orders.lockByTenantAndProject(
            tenant.id(), cmd.projectId(), cmd.orderId());

        ResourceRights rights = rightsResolver.currentRights(
            actor, tenant, order);

        // Cho phép đọc kết quả lịch sử chỉ theo quyền đọc hiện tại.
        resourcePolicy.require(Action.READ, actor, order, rights);

        IdempotencyClaim claim = idempotency.claim(
            tenant.id(), actor.principalId(), "APPROVE_ORDER",
            cmd.idempotencyKey(), fingerprints.approveOrder(cmd));

        if (claim.isCompleted()) {
            return claim.originalReceipt();
        }

        resourcePolicy.require(Action.APPROVE, actor, order, rights);
        businessRules.requireApprovable(actor, order, rights);

        if (order.version() != cmd.expectedVersion()) {
            throw new StaleOrderException();
        }

        int changed = orders.approveIfPendingVersionMatches(
            tenant.id(), order.id(), order.version(), actor.principalId());

        if (changed != 1) {
            throw new ConcurrentOrderChangeException();
        }

        ApprovalReceipt receipt = audit.appendApproval(
            order, actor, rights.policyVersion(), rights.evidence());

        outbox.appendApprovalCommitted(receipt);
        idempotency.complete(claim, receipt);
        return receipt;
    });
}
```

Các điểm cần hiểu đúng:

- `selectedTenantId`, project ID và order ID là yêu cầu lựa chọn, không phải bằng chứng quyền. `requireActiveMembership` và truy vấn theo tenant/project phải xác minh chúng.
- `lockByTenantAndProject` chỉ tải nội bộ một đơn đúng quan hệ. `resourcePolicy` còn phải kiểm tra action cụ thể trên object; hàm tìm theo tenant đơn thuần chưa làm được việc đó.
- `currentRights` lấy assignment/grant/membership và dữ kiện cần thiết từ nguồn có thẩm quyền. Nó không dùng `canApprove` do body tự khai.
- `APPROVE` khác `READ`. `businessRules` còn kiểm tra trạng thái nguồn, nội dung server, hạn mức và sự độc lập giữa maker/reviewer theo policy.
- Lệnh idempotency ràng buộc tenant, principal, action và fingerprint của resource/version cùng dữ liệu nghiệp vụ có ý nghĩa. Cùng key nhưng đổi order hoặc nội dung không được trả nhầm kết quả.
- Audit, outbox, state và kết quả idempotency cùng transaction. Chỉ trả thành công khi transaction đã hoàn tất; exception lưu dữ liệu không được nuốt.

Trong policy ví dụ, reviewer của đơn có thể đọc đơn nên nhánh kiểm tra `READ` trước replay phù hợp. Nếu hệ thống có hành động chỉ được thực hiện mà không được đọc toàn bộ resource, phải định nghĩa quyền đọc receipt riêng, không sao chép điều kiện `READ` một cách máy móc.

### 7.3. Lệnh cập nhật vẫn cần tenant, state và version

```sql
UPDATE purchase_order
SET state = 'APPROVED',
    version = version + 1,
    approved_by = :trusted_principal_id
WHERE tenant_id = :verified_tenant_id
  AND id = :order_id
  AND state = 'PENDING_APPROVAL'
  AND version = :expected_version;
```

Kiểm tra số hàng cập nhật là bắt buộc. Câu SQL này bảo vệ một số điều kiện concurrency, không tự kiểm tra toàn bộ assignment hoặc quyền theo tài nguyên; nó thuộc giao thức đã kiểm tra quyền phía trên.

Khóa hàng đơn không tự khóa grant hoặc directory bên ngoài. Nếu nghiệp vụ yêu cầu thu hồi quyền có hiệu lực nguyên tử với hành động, cần cơ chế tuần tự hóa chung trên dữ liệu quyền, version/fence được kiểm tra tại nơi ghi hoặc giao thức tương ứng. Nếu chấp nhận snapshot quyền có độ trễ, phải xác định và kiểm thử cửa sổ đó thay vì hứa thu hồi tức thì.

### 7.4. Đừng tái sử dụng một kết quả ALLOW quá phạm vi

Một quyết định cho principal P, action `READ`, tài nguyên O1, tenant T1 và version quyền V không dùng được cho `APPROVE`, O2 hoặc tenant T2.

Nếu đóng gói tài nguyên đã được cấp quyền trong một wrapper nội bộ, wrapper cần giữ phạm vi action/ngữ cảnh và vòng đời sử dụng rõ. Một boolean `authorized = true` gắn vào session không thể thay cho authorization theo tài nguyên.

## 8. Những đường truy cập hay bị bỏ sót

### 8.1. Create, clone, chuyển chủ sở hữu và chia sẻ

Tạo mới chưa có object để kiểm tra owner, nhưng đã có collection/project đích và các đối tượng tham chiếu. Kiểm tra quyền tạo ở đích; server xác định creator/tenant, và quyền tạo hộ phải là action có kiểm soát.

Đổi owner, chuyển tenant/project hoặc chia sẻ có thể làm thay đổi toàn bộ phạm vi ai được phép truy cập. Chúng cần action riêng, quyền trên nguồn/đích và cập nhật nguyên tử phù hợp. Không để requester thực hiện qua một field được mass assignment trong API sửa mô tả.

### 8.2. Batch và bulk action

Với một danh sách ID, kiểm tra trên từng tài nguyên hoặc bằng một truy vấn scope tương đương. Không lấy quyền trên ID đầu tiên để áp dụng cho cả batch.

Chọn hợp đồng rõ:

- Tất cả hợp lệ thì thực hiện toàn bộ trong phạm vi nguyên tử đã định nghĩa.
- Hoặc cho phép kết quả từng phần, với quyền và kết quả riêng cho từng mục.

Không tạo một số tác dụng rồi mới phát hiện tài nguyên cuối không có quyền trong khi API hứa toàn bộ hoặc không gì cả. Với tài nguyên bị cấm, phản hồi từng phần cũng không được làm lộ thông tin ngoài quyền được biết.

### 8.3. File, thumbnail và URL tải xuống

Attachment, thumbnail, bản preview, metadata và endpoint `HEAD` có thể chứa thông tin nhạy cảm. Quyền đọc trang đơn không đủ nếu đường tải file lấy blob theo ID mà không kiểm tra đúng quan hệ/quyền.

Nếu dùng signed URL, việc cấp URL phải kiểm tra quyền trên đúng file/action và giới hạn thời hạn/phạm vi. Người cầm URL có thể có khả năng truy cập theo mô hình capability được chọn. Link không có kiểm tra thu hồi trực tuyến thường không tự mất hiệu lực ngay khi quyền tài khoản thay đổi; cần chọn mô hình phù hợp rủi ro.

### 8.4. GraphQL, WebSocket và cache resolver

Một endpoint GraphQL chung không làm quyền tự áp dụng cho mọi node hoặc field con. Resolver hoặc lớp nghiệp vụ dùng chung phải giữ đúng principal/tenant/action khi lấy dữ liệu.

Với subscription hoặc kết nối dài, quyền tại lúc bắt tay không mặc nhiên đủ cho mọi dữ liệu được đẩy về sau. Định nghĩa chính sách kiểm tra lại khi phát dữ liệu hoặc khi quyền thay đổi.

Cache dùng trong resolver, loader hoặc response cũng phải giữ đúng phạm vi. Dữ liệu đã tải cho người có quyền không được phát cho người khác chỉ vì dùng cùng resource ID làm cache key.

### 8.5. Job nền và service nội bộ

Kiểm tra quyền lúc đưa job vào hàng đợi không mặc nhiên đủ cho lúc job thực thi sau đó. Xác định job chạy theo quyền service riêng hay đại diện người dùng, phạm vi được giao và độ mới của quyền cần kiểm tra.

Không nhận `requested_by` trong message không được xác thực rồi coi đó là danh tính đáng tin. Service có quyền rộng cũng không được trở thành công cụ thực hiện mọi action mà client gửi qua một endpoint trung gian. Nó phải kiểm tra mục đích và phạm vi ủy quyền trước khi dùng quyền của mình.

## 9. Cache, thu hồi quyền và độ mới của quyết định

Cache quyền có thể giảm truy vấn, nhưng cache `ALLOW` cũ có thể cho phép hành động sau khi người dùng bị xóa khỏi tenant hoặc grant bị thu hồi.

Tùy policy, khóa cache có thể cần chứa:

```text
principal + tenant + action + resource type/id
    + version thuộc tính/quyền liên quan
    + policy version + ngữ cảnh ảnh hưởng kết quả.
```

Không có một khóa chung đúng cho mọi hệ thống. Nếu quyền đọc còn phụ thuộc projection, mức xác thực hoặc thời gian, các yếu tố đó cũng phải được xử lý. TTL không được vượt thời gian hiệu lực mà policy cho phép; không ghi access token nguyên văn vào cache key hoặc log.

Invalidation và TTL hỗ trợ kiểm soát độ trễ, nhưng không tự tạo bảo đảm thu hồi nguyên tử. Quy trình nhạy cảm có thể cần đọc lại nguồn quyền hoặc kiểm tra version tại điểm ghi. Cache của dữ liệu và cache của authorization cũng có vòng đời khác nhau.

HTTP conditional request như `If-None-Match` vẫn phải được kiểm tra quyền trước khi trả phản hồi liên quan tài nguyên. Không trả `304` hoặc kết quả cache như một lối tắt bỏ qua quyền hiện tại.

Khi policy engine hoặc nguồn facts không khả dụng, operation cần xử lý theo quy tắc đã định nghĩa. Với action nhạy cảm trong bài, thiếu đủ bằng chứng cấp quyền phải dẫn đến từ chối hoặc lỗi không thực thi, không chuyển sang `ALLOW` để “giữ hệ thống chạy”.

## 10. Row-Level Security và các lớp bảo vệ bổ sung

RLS của database có thể bổ sung cách ly hàng theo tenant hoặc principal. Nó hữu ích khi nhiều truy vấn cùng chạm một bảng, nhưng không tự định nghĩa mọi hành động nghiệp vụ và quyền trên từng field.

Trong PostgreSQL, khi bật row security mà không có policy cho phép thì normal row access chịu mặc định từ chối. Tuy nhiên, superuser và role có `BYPASSRLS` bỏ qua RLS; owner thường cũng bỏ qua nếu không áp dụng cơ chế phù hợp như `FORCE ROW LEVEL SECURITY`. [PostgreSQL: Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).

Khi triển khai cần xác minh role chạy ứng dụng thực sự chịu policy và cách kết hợp nhiều policy. Một policy rộng được kết hợp theo phép cho phép có thể làm phạm vi kết quả lớn hơn mong muốn.

Nếu application dùng một database account chung và truyền tenant qua session setting, ngữ cảnh đó phải do code tin cậy thiết lập, có vòng đời transaction/connection rõ và không rò sang request tiếp theo trong connection pool. Nó không phải lớp chống mọi kiểu SQL injection nếu cùng tài khoản có thể tự thay ngữ cảnh một cách không bị kiểm soát.

RLS cũng không thay cho kiểm tra `APPROVE`, giới hạn sửa giá, maker–checker, audit hoặc idempotency. Dùng các lớp bảo vệ với trách nhiệm rõ, kiểm thử bằng đúng database role của production thay vì chỉ bằng tài khoản owner.

## 11. Phản hồi, audit và khả năng điều tra

### 11.1. Không biến lỗi quyền thành kênh dò dữ liệu

Hợp đồng API có thể chọn phản hồi không phân biệt tài nguyên không tồn tại và tài nguyên không được phép biết. Chọn cách ánh xạ nhất quán với yêu cầu nghiệp vụ; tránh thông báo kiểu “đơn này thuộc tenant B, owner là X” cho người không có quyền.

Không chỉ response body mới có thể lộ dữ liệu. Tổng số, tên file, redirect tải xuống, thông báo lỗi foreign key hoặc log được người dùng truy cập cũng cần được xem xét.

### 11.2. Ghi căn cứ quyền đủ để điều tra

Một audit record phù hợp có thể chứa:

```text
principal/service thực hiện và tenant đã xác minh
action, resource type/id và version liên quan
kết quả ALLOW/DENY, reason code và policy version
tham chiếu assignment/grant hoặc version bằng chứng quyền
request/correlation/command ID và thời điểm quyết định
```

Không ghi toàn bộ token, bí mật, payload nhạy cảm hoặc mọi field của object chỉ để giải thích một lần từ chối. Quyền đọc audit cũng phải theo phạm vi dữ liệu phù hợp.

Phân biệt sự kiện bị từ chối với sự kiện nghiệp vụ đã commit. Nếu transaction rollback, cần cơ chế lưu attempt phù hợp; ngược lại, không để audit thành công tồn tại độc lập trước khi transaction nghiệp vụ thực sự hoàn tất.

Theo dõi việc một principal thử nhiều resource ID không thuộc phạm vi, nhiều tenant, nhiều action bị cấm hoặc endpoint phụ ít được sử dụng. Một lần từ chối có thể chỉ là client cũ hoặc thao tác nhầm; đánh giá cùng tần suất và ngữ cảnh.

## 12. Kiểm thử quyền bằng ma trận chủ thể–tài nguyên–hành động

Tạo dữ liệu với các chủ thể khác nhau:

- U1: requester của O1 ở tenant T1, project P1.
- U2: reviewer được phân công O1 trong T1.
- U3: thành viên T1 nhưng không có quan hệ/grant trên O1.
- U4: reviewer ở tenant T2.
- U5: có grant `READ` trực tiếp trên O1, không có `APPROVE`.
- U6: quản trị có phạm vi T1, không có quyền ngầm với T2.

Ma trận cơ sở theo policy ví dụ:

| Chủ thể với O1 | Đọc | Sửa draft | Phê duyệt |
| --- | --- | --- | --- |
| U1 requester | Cho phép field phù hợp | Chỉ khi đủ quyền sửa và đang draft | Từ chối nếu vi phạm quy tắc độc lập |
| U2 assigned reviewer | Cho phép field phù hợp | Không tự được sửa | Chỉ khi đủ capability và invariant |
| U3 cùng tenant, không quan hệ | Từ chối | Từ chối | Từ chối |
| U4 tenant khác | Từ chối | Từ chối | Từ chối |
| U5 chỉ có grant đọc | Cho phép field theo grant | Từ chối | Từ chối |
| U6 quản trị T1 | Theo quyền quản trị đã định nghĩa | Theo action/phạm vi đã định nghĩa | Không mặc nhiên bỏ qua invariant |

Các tình huống kiểm thử cần mở rộng:

| Tình huống | Điều phải xác minh |
| --- | --- |
| Thay order ID bằng ID người khác cùng tenant | Role hoặc membership chung không làm mở quyền object |
| Thay tenant/project ID nhưng giữ order ID | Quan hệ cha/con và phạm vi được kiểm tra |
| UUID hợp lệ nhưng không có quyền | Không coi ID khó đoán là cơ chế cấp quyền |
| Có quyền đọc rồi gọi action phê duyệt/xóa | Quyền được kiểm tra theo action |
| Gửi thêm tenant, owner, state, approved-by hoặc giá có thẩm quyền | Không mass assignment hoặc đổi quyền qua field |
| Đọc attachment/thumbnail/metadata bằng ID trực tiếp | Không vượt quyền của tài nguyên và quan hệ liên quan |
| List, count, search và export | Không lộ hàng, field hoặc số tổng ngoài phạm vi |
| Batch gồm ID được phép và bị cấm | Đúng hợp đồng nguyên tử/từng phần, không tác dụng ngoài quyền |
| Grant hết hạn, bị thu hồi hoặc membership bị xóa | Hành vi đúng cam kết về độ mới và cache |
| Assignment đổi đồng thời với lần ghi | Không sử dụng facts ngoài mức nhất quán đã chọn |
| Quyền bị thu hồi trước khi job chạy | Kiểm tra theo danh tính/phạm vi và policy thực thi của job |
| Retry key của người/tenant khác | Không lộ receipt hoặc thực thi thêm |
| Cùng key nhưng đổi resource/action | Từ chối xung đột, không tái dùng kết quả ALLOW |
| Cache, conditional GET hoặc resolver được dùng bởi hai người | Không trao dữ liệu/projection của người này cho người kia |
| Policy engine lỗi hoặc action chưa được định nghĩa | Không có tác dụng nghiệp vụ do nhánh mặc định cho phép |
| Chạy truy vấn bằng database role thực tế có RLS | Không bị owner/BYPASSRLS hoặc ngữ cảnh pool vô hiệu hóa cách ly |

Với thao tác bị từ chối, kiểm tra cả phản hồi lẫn việc database, outbox và các tác dụng ngoài không bị thay đổi trái phép. Với concurrency, dùng transaction/kết nối thật để tạo tranh chấp, không chỉ gọi tuần tự một hàm policy thuần.

Các bảng và khung mã trong bài là tài liệu thiết kế. Chúng chưa được chạy như một ứng dụng hoàn chỉnh và không thay thế kiểm thử tích hợp của hệ thống thực tế.

## 13. Bài tập áp dụng

Thiết kế quyền cho chức năng chuyển một đơn mua hàng có attachment từ project A sang project B, đồng thời giữ lại một số người được chia sẻ.

1. Chủ thể cần những action/quyền nào trên đơn, project nguồn và project đích?
2. Tenant, owner và quan hệ attachment được xác minh bằng dữ liệu nào?
3. Grant cũ nào còn hợp lệ, grant nào phải thu hồi hoặc xét lại sau khi chuyển?
4. Truy vấn list/count/export ở hai project thay đổi ra sao sau commit?
5. Làm thế nào tránh việc người dùng tự chuyển đơn vào phạm vi mình quản lý để mở quyền phê duyệt?
6. Nếu membership hoặc grant đổi trong lúc chuyển, hệ thống bảo đảm mức nhất quán nào?
7. Idempotency, audit và cache được ràng buộc với principal, action, tài nguyên và version như thế nào?

Một thiết kế tốt phải chỉ rõ ai được làm gì trên tài nguyên nào, dựa trên dữ liệu có thẩm quyền và ở thời điểm nào. Resource authorization có hiệu lực khi cùng quy tắc được áp dụng cho đường đọc, đường ghi, tài nguyên con và các tác vụ nền, đồng thời được giữ nhất quán với trạng thái và nội dung nghiệp vụ thực sự được sử dụng.
