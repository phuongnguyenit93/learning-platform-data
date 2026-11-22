# Kiểm tra read, update, delete và action trên object

Object authorization là việc quyết định một principal cụ thể có được thực hiện một thao tác trên một đối tượng dữ liệu cụ thể hay không. Trong API, kiểm tra người dùng đã đăng nhập hoặc có một role chung không đủ để bảo vệ object. Một người dùng có thể được phép đọc đơn hàng của mình nhưng không được đọc đơn hàng của người khác; có thể sửa địa chỉ giao hàng nhưng không được thay đổi chủ sở hữu hoặc trạng thái thanh toán; có thể hủy đơn khi đơn còn chờ xử lý nhưng không được hủy sau khi đã giao.

Mỗi thao tác trên object cần được đánh giá riêng: read, update, delete và các action nghiệp vụ như approve, cancel, refund, publish, assign hoặc archive. Quyền có thể phụ thuộc vào chủ sở hữu, tenant, quan hệ chia sẻ, vai trò, thuộc tính của object, trạng thái hiện tại, dữ liệu được yêu cầu thay đổi và ngữ cảnh nghiệp vụ.

Lỗi thiếu kiểm tra này thường được gọi là Broken Object Level Authorization (BOLA), trước đây thường được mô tả bằng IDOR. Kẻ gọi API thay một object ID trong path, query hoặc body để truy cập hoặc thao tác trên dữ liệu của người khác. ID khó đoán có thể giảm khả năng dò tìm nhưng không thay thế authorization ở server.

## 1. Xây dựng chính sách quyền theo object và thao tác

Trước khi triển khai endpoint, cần xác định ai có thể làm gì trên loại object nào và trong điều kiện nào. Không nên gộp mọi quyền vào một câu hỏi chung như “người dùng có role USER hay không”.

Một policy thường xét các yếu tố:

- **Principal:** danh tính đã xác thực, tenant, role, nhóm hoặc các thuộc tính tin cậy lấy từ security context.
- **Action:** thao tác cụ thể như read, update, delete, approve, refund hoặc export.
- **Object:** loại object, ID, owner, tenant, trạng thái, mức phân loại và các quan hệ liên quan.
- **Context:** thời điểm, kênh truy cập, trạng thái quy trình, quan hệ được ủy quyền hoặc điều kiện kiểm soát bổ sung.
- **Requested change:** các field mà client muốn thay đổi và giá trị mới dự kiến.

Có thể kết hợp nhiều mô hình:

| Mô hình | Cách quyết định | Ví dụ |
|---|---|---|
| RBAC | Dựa trên role hoặc permission được gán cho principal | Nhân viên hỗ trợ có quyền xem yêu cầu hỗ trợ |
| Ownership | So sánh principal với chủ sở hữu object | Khách hàng chỉ đọc hồ sơ của mình |
| Tenant isolation | Giới hạn object theo tenant của principal | Tenant A không truy cập hóa đơn của tenant B |
| ABAC | Dựa trên thuộc tính principal, object, action và context | Quản lý chỉ duyệt khoản chi thuộc đơn vị mình và dưới hạn mức |
| Relationship-based access | Dựa trên quan hệ giữa principal và object | Thành viên được chia sẻ một tài liệu có thể đọc tài liệu đó |

Các mô hình có thể phối hợp. Ví dụ nhân viên có role SUPPORT chỉ được đọc ticket khi ticket thuộc tenant mà nhân viên được phân công; một số field chỉ hiển thị khi nhân viên có quan hệ xử lý ticket. Role trả lời quyền chức năng tổng quát, còn policy theo object xác định phạm vi dữ liệu cụ thể.

### 1.1. Lập ma trận quyền trước khi viết endpoint

Một ma trận đơn giản giúp phát hiện những thao tác chưa có quy tắc rõ ràng:

| Principal | Read | Update | Delete | Action |
|---|---|---|---|---|
| Chủ sở hữu | Đọc object thuộc quyền xem | Sửa field được phép khi trạng thái cho phép | Xóa khi policy và trạng thái cho phép | Thực hiện action được nghiệp vụ cho phép |
| Người cùng tenant | Chỉ đọc nếu có quan hệ hoặc quyền được cấp | Chỉ sửa khi được giao trách nhiệm | Thường không có quyền mặc định | Chỉ thực hiện action được cấp |
| Nhân viên hỗ trợ | Đọc object được phân công | Sửa field phục vụ hỗ trợ | Thường cần quyền riêng | Có thể thêm ghi chú hoặc chuyển người phụ trách |
| Quản trị nghiệp vụ | Đọc theo phạm vi quản trị | Sửa theo policy và audit | Có thể cần phê duyệt bổ sung | Action quản trị được cấp và được ghi nhận |
| Principal ngoài tenant | Từ chối | Từ chối | Từ chối | Từ chối |

Đây chỉ là ví dụ. Quyền thực tế phải xuất phát từ nghiệp vụ và phân loại dữ liệu. Không được suy ra rằng mọi người cùng tenant đều có quyền đọc hoặc sửa mọi object trong tenant.

## 2. Xác định object và principal từ nguồn đáng tin cậy

Object ID thường xuất hiện ở nhiều vị trí:

- Path parameter, ví dụ /orders/{orderId}.
- Query parameter, ví dụ ?accountId=...
- Request body, ví dụ orderId, ownerId hoặc documentId.
- Object lồng nhau, ví dụ /projects/{projectId}/members/{memberId}.
- Danh sách ID trong batch request.
- Header hoặc token tham chiếu đến một tài nguyên.

Mọi ID do client gửi chỉ là dữ liệu định danh để tìm object. ID không chứng minh client có quyền với object đó. UUID, số ngẫu nhiên hoặc ID khó đoán không phải là cơ chế phân quyền.

Principal phải được lấy từ thông tin xác thực đã được xác minh, chẳng hạn security context do middleware xác thực tạo ra. Không lấy userId, tenantId, role hoặc quyền từ request body để quyết định truy cập. Nếu client gửi ownerId hoặc tenantId, server cần bỏ qua, từ chối hoặc chỉ dùng trong một quy trình quản trị được ủy quyền rõ ràng.

Với quan hệ lồng nhau, cần xác minh cả quan hệ cha-con. Ví dụ người gọi có quyền với project không đồng nghĩa họ có quyền với mọi invoice được tham chiếu trong project. Tương tự, có quyền với order không tự động cấp quyền với payment, shipment hoặc customer profile liên quan.

## 3. Kiểm tra quyền read

Read authorization phải được áp dụng cho mọi cách đọc dữ liệu: lấy một object, danh sách, tìm kiếm, xem chi tiết, export, download, thống kê, autocomplete và các endpoint trả dữ liệu dẫn xuất.

### 3.1. Đọc một object theo phạm vi được phép

Một lỗi phổ biến là tìm object chỉ bằng ID, sau đó trả về mà không kiểm tra chủ sở hữu hoặc tenant:

~~~java
Order order = orderRepository.findById(orderId)
    .orElseThrow(NotFoundException::new);
return orderMapper.toResponse(order);
~~~

Nếu ID thuộc người dùng khác, endpoint có thể trở thành BOLA. Cần giới hạn truy vấn theo phạm vi principal hoặc kiểm tra policy trên object trước khi trả dữ liệu.

Ví dụ truy vấn theo tenant và owner:

~~~java
Order order = orderRepository
    .findByIdAndTenantIdAndOwnerId(orderId, caller.tenantId(), caller.userId())
    .orElseThrow(NotFoundException::new);

return orderMapper.toResponse(order);
~~~

Ví dụ này phù hợp khi policy chỉ cho chủ sở hữu đọc. Nếu nhân viên hỗ trợ hoặc người được chia sẻ cũng có quyền, repository có thể trả object trong phạm vi tenant rồi một policy service đánh giá quan hệ tương ứng. Điều quan trọng là mọi nhánh thành công đều có kiểm tra quyền rõ ràng.

### 3.2. Giới hạn kết quả danh sách và tìm kiếm

Không thể bảo vệ endpoint chi tiết mà bỏ qua endpoint danh sách. Các truy vấn list, search, count, autocomplete và export phải áp dụng cùng phạm vi truy cập:

- Lọc theo tenant và phạm vi dữ liệu được cấp.
- Áp dụng quan hệ owner, assignment hoặc sharing nếu policy yêu cầu.
- Chỉ trả các field mà principal được xem.
- Tính total count trên tập dữ liệu được phép, tránh làm lộ số lượng object ngoài phạm vi.
- Áp dụng quyền trước pagination và aggregation để không rò rỉ qua thứ tự, số trang hoặc thống kê.

Ví dụ, truy vấn hóa đơn theo tenant cần có điều kiện tenant trong truy vấn database, thay vì tải tất cả hóa đơn rồi lọc sau trong bộ nhớ. Cách lọc sau vừa tốn tài nguyên vừa dễ bỏ sót một đường trả dữ liệu.

### 3.3. Field-level read authorization

Được đọc một object không có nghĩa được xem mọi field của object. Hồ sơ khách hàng có thể chứa địa chỉ liên hệ, thông tin định danh, ghi chú nội bộ và đánh giá rủi ro. Response cần được tạo theo allowlist hoặc projection phù hợp với policy.

Ví dụ:

- Khách hàng xem thông tin liên hệ của chính mình.
- Nhân viên hỗ trợ xem thông tin cần thiết để xử lý ticket được phân công.
- Nhân viên kiểm soát rủi ro xem dữ liệu đánh giá theo nhiệm vụ được giao.
- Principal không đủ quyền không nhận field nhạy cảm trong JSON, dù giao diện client có thể ẩn field đó.

Không gửi toàn bộ object rồi dựa vào JavaScript hoặc ứng dụng mobile để ẩn dữ liệu. Một khi response đã đến client, người dùng có thể đọc payload qua network hoặc công cụ debug.

### 3.4. Cache, file và dữ liệu dẫn xuất

Cache cần đưa principal hoặc phạm vi authorization vào khóa cache khi response phụ thuộc vào người dùng, tenant hoặc role. Nếu cache chỉ theo object ID, response đã tạo cho nhân viên có quyền cao có thể bị trả cho người dùng thông thường.

Download file, ảnh, tài liệu và signed URL cũng là một phần của read authorization. Cần kiểm tra quyền trước khi cấp URL hoặc stream nội dung; URL có thời hạn và phạm vi hẹp, đồng thời không được dùng URL đoán được làm cơ chế kiểm soát duy nhất.

Các dữ liệu dẫn xuất như dashboard, báo cáo, tổng số, gợi ý và kết quả export phải tuân theo phạm vi của dữ liệu nguồn. Việc một endpoint không trả object thô không có nghĩa kết quả tổng hợp không thể tiết lộ thông tin của tenant khác.

## 4. Kiểm tra quyền update

Update phức tạp hơn read vì quyết định quyền phụ thuộc cả object hiện tại lẫn thay đổi mà client đề nghị. Cần xác minh:

1. Principal có quyền cập nhật object này không?
2. Principal có quyền sửa từng field được gửi lên không?
3. Giá trị mới có hợp lệ với trạng thái và quy tắc nghiệp vụ không?
4. Thay đổi có làm phát sinh tác động lên object hoặc tenant khác không?

### 4.1. Chỉ cho phép cập nhật field được phép

Không bind request trực tiếp vào entity có nhiều field nội bộ. Một request có thể thêm ownerId, tenantId, role, status, approvedBy, balance hoặc isAdmin để cố thay đổi dữ liệu nhạy cảm.

Hãy dùng DTO dành riêng cho thao tác và allowlist field:

~~~java
public record UpdateShippingAddressRequest(
    @NotBlank String recipient,
    @NotBlank String address,
    @NotBlank String phone
) {}
~~~

~~~java
@Transactional
public void updateShippingAddress(
        String orderId,
        UpdateShippingAddressRequest request,
        Caller caller) {
    Order order = orderRepository
        .findByIdAndTenantId(orderId, caller.tenantId())
        .orElseThrow(NotFoundException::new);

    authorization.requireCanUpdateShippingAddress(caller, order);
    order.requireShippingAddressEditable();

    order.updateShippingAddress(
        request.recipient(),
        request.address(),
        request.phone()
    );
}
~~~

Trong ví dụ, caller lấy từ security context; DTO không có ownerId hoặc tenantId; service kiểm tra quyền và trạng thái trước khi thay đổi. Policy có thể cho phép người nhận hoặc nhân viên vận hành cập nhật địa chỉ trong những điều kiện khác nhau.

### 4.2. Quyền update có thể khác nhau theo field

Không nên dùng một quyền update chung cho mọi thuộc tính. Ví dụ:

| Field | Người dùng | Nhân viên hỗ trợ | Quản trị nghiệp vụ |
|---|---|---|---|
| Display name | Có thể sửa | Không mặc định | Theo phạm vi |
| Shipping address | Có thể sửa trước khi đóng gói | Có thể sửa khi được phân công | Theo policy |
| Order status | Không tự đặt tùy ý | Chỉ qua action được cấp | Theo workflow |
| Owner/tenant | Không | Không | Chỉ qua quy trình quản trị đặc biệt |
| Internal risk note | Không | Chỉ khi có nhiệm vụ phù hợp | Theo quyền chuyên biệt |

Nếu client gửi field không được phép, API nên từ chối rõ ràng hoặc xử lý theo contract đã công bố. Không âm thầm chấp nhận field nhạy cảm rồi bỏ qua một cách không nhất quán giữa các endpoint.

### 4.3. Kiểm tra trạng thái và transition

Một principal có thể có quyền sửa một field nhưng chỉ trong một số trạng thái. Ví dụ khách hàng được sửa địa chỉ khi đơn ở trạng thái DRAFT hoặc PENDING, nhưng không được sửa sau khi đơn đã SHIPPED.

Policy update nên xét:

- Trạng thái hiện tại của object.
- Trạng thái hoặc giá trị mới được đề nghị.
- Thời hạn nghiệp vụ, ví dụ thời điểm chốt đơn.
- Quan hệ giữa principal và object tại thời điểm cập nhật.
- Các điều kiện đồng bộ với object liên quan.

Các chuyển trạng thái nhạy cảm như PAID, APPROVED hoặc CLOSED thường nên được thực hiện bằng action riêng thay vì cho client cập nhật một field status tùy ý.

### 4.4. Chống race condition và kiểm tra quyền trong transaction

Nếu kiểm tra quyền ở một thời điểm rồi cập nhật object ở thời điểm khác, trạng thái hoặc quan hệ có thể đã thay đổi. Đây là rủi ro time-of-check to time-of-use (TOCTOU).

Với thao tác nhạy cảm, cần thực hiện kiểm tra và cập nhật trong cùng transaction, sử dụng optimistic locking, row lock hoặc điều kiện cập nhật nguyên tử phù hợp. Ví dụ truy vấn cập nhật có thể giới hạn đồng thời theo ID, tenant, owner và trạng thái hiện tại:

~~~sql
UPDATE orders
SET shipping_address = :address,
    version = version + 1
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND owner_id = :callerId
  AND status IN ('DRAFT', 'PENDING')
  AND version = :expectedVersion;
~~~

Nếu số dòng cập nhật bằng 0, không được giả định cập nhật thành công. Ứng dụng cần xác định theo chính sách liệu object không tồn tại, không thuộc phạm vi, đã đổi trạng thái hay version đã cũ; response phải tránh tiết lộ thông tin không cần thiết.

Không phải mọi update đều cần khóa pessimistic. Chọn cơ chế dựa trên mức độ tranh chấp và tác động nghiệp vụ, nhưng phải bảo đảm policy được đánh giá trên dữ liệu nhất quán và không có đường cập nhật bỏ qua kiểm tra.

## 5. Kiểm tra quyền delete

Delete là thao tác có tác động lớn và cần quyền riêng. Quyền read hoặc update không tự động bao gồm quyền xóa.

### 5.1. Kiểm tra phạm vi và điều kiện xóa

Trước khi xóa, cần xác minh:

- Principal có quyền delete trên đúng object không?
- Object có thuộc tenant hoặc phạm vi mà principal quản lý không?
- Object đang ở trạng thái có thể xóa không?
- Có quan hệ phụ thuộc, nghĩa vụ lưu trữ hoặc yêu cầu audit không?
- Xóa object có ảnh hưởng tới object của principal hoặc tenant khác không?

Ví dụ người dùng có thể xóa bản nháp của mình nhưng không được xóa hóa đơn đã phát hành. Nhân viên hỗ trợ có thể đóng ticket nhưng không có quyền xóa lịch sử xử lý. Quản trị viên hệ thống cũng không nên mặc nhiên có quyền xóa dữ liệu nghiệp vụ nếu nhiệm vụ đó cần một vai trò riêng.

### 5.2. Soft delete, hard delete và cascade

Soft delete đánh dấu object đã xóa hoặc ẩn; hard delete loại bỏ dữ liệu khỏi kho lưu trữ theo chính sách. Cần xác định rõ:

- Object đã soft delete có còn đọc được bởi quản trị hoặc audit không?
- Có cho phép restore không và ai được restore?
- Quan hệ cascade có xóa dữ liệu liên quan thuộc người khác hoặc tenant khác không?
- Dữ liệu nào phải giữ lại theo yêu cầu pháp lý, kế toán hoặc điều tra?
- Cache, search index, file và bản sao dữ liệu được xử lý ra sao?

Không dựa vào cascade mặc định của ORM nếu chưa hiểu toàn bộ quan hệ. Một thao tác xóa project có thể ảnh hưởng task, invoice, comment hoặc file được chia sẻ; mỗi quan hệ cần policy và hành vi được thiết kế rõ.

### 5.3. Bulk delete và thao tác lặp lại

Endpoint xóa hàng loạt phải kiểm tra quyền cho từng object hoặc thực hiện truy vấn có scope bảo đảm tất cả object đều nằm trong tập được phép. Không nên chỉ kiểm tra quyền trên object đầu tiên rồi xóa cả danh sách ID do client gửi.

Đối với request chứa một phần ID hợp lệ và một phần ID không hợp lệ, contract cần định nghĩa rõ hành vi: từ chối toàn bộ, xử lý từng phần với kết quả riêng, hoặc tạo job có báo cáo. Tránh trả kết quả mơ hồ khiến client nghĩ mọi object đã được xóa.

Delete thường cần idempotency ở mức nghiệp vụ. Gọi lại cùng thao tác không được tạo ra tác động phụ không mong muốn. Tuy nhiên, việc object đã xóa có trả 404, 204 hay kết quả idempotent khác phải nhất quán với contract và không làm lộ sự tồn tại của object ngoài phạm vi.

## 6. Kiểm tra quyền với action nghiệp vụ

Nhiều thao tác không thể biểu diễn an toàn bằng update field thông thường. Approve, reject, cancel, refund, transfer, publish, archive, assign, lock và reopen là các action có ý nghĩa nghiệp vụ riêng.

Một action cần kiểm tra tối thiểu:

- Principal có permission thực hiện action không?
- Principal có quyền trên object cụ thể không?
- Object có đang ở trạng thái cho phép action không?
- Các điều kiện nghiệp vụ như hạn mức, thời gian, người phê duyệt hoặc trạng thái liên quan có thỏa mãn không?
- Action có cần người thứ hai phê duyệt hoặc separation of duties không?
- Request có bị gửi lặp lại hoặc replay không?

### 6.1. Tách action khỏi update tùy ý

Không nên cho phép client gửi PATCH status=APPROVED nếu việc duyệt cần kiểm tra vai trò, hạn mức và workflow. Hãy thiết kế endpoint action rõ ràng, chẳng hạn:

~~~http
POST /expenses/{expenseId}/approve
POST /orders/{orderId}/cancel
POST /payments/{paymentId}/refund
~~~

Endpoint riêng giúp thể hiện intent, gắn permission cụ thể, audit và kiểm tra transition. Nó không tự động bảo đảm an toàn; server vẫn phải kiểm tra object và điều kiện nghiệp vụ.

### 6.2. Kiểm tra action dựa trên trạng thái và hạn mức

Ví dụ một khoản chi chỉ được approve nếu:

- Người duyệt thuộc đơn vị quản lý của khoản chi.
- Người duyệt có permission APPROVE_EXPENSE.
- Người tạo khoản chi không đồng thời là người duyệt nếu chính sách yêu cầu separation of duties.
- Khoản chi đang ở trạng thái SUBMITTED.
- Số tiền không vượt hạn mức của người duyệt.
- Chứng từ bắt buộc đã được xác minh.

Nếu số tiền vượt hạn mức, workflow có thể yêu cầu cấp duyệt cao hơn. Không được chỉ dựa vào role ADMIN hoặc một field do client gửi.

### 6.3. Ví dụ service cho action approve

~~~java
@Transactional
public void approveExpense(String expenseId, Caller caller) {
    Expense expense = expenseRepository
        .findByIdAndTenantIdForUpdate(expenseId, caller.tenantId())
        .orElseThrow(NotFoundException::new);

    authorization.requireCanApprove(caller, expense);
    expense.requireState(ExpenseState.SUBMITTED);
    expense.requireApproverIsNotCreator(caller.userId());
    approvalPolicy.requireWithinLimit(caller, expense.amount());

    expense.approve(caller.userId(), clock.instant());
    audit.recordExpenseApproved(expense, caller);
}
~~~

Đây là ví dụ cấu trúc. Repository cần dùng cơ chế khóa hoặc kiểm soát version phù hợp; policy phải lấy thông tin principal đã xác thực; audit nên được ghi trong cùng transaction hoặc qua transactional outbox nếu cần đồng bộ với hệ thống khác.

### 6.4. Refund, transfer và action có tác động tài chính

Với action tài chính, cần kiểm tra thêm:

- Object nguồn và object đích đều thuộc phạm vi được phép.
- Người gọi có quyền trên cả hai phía của giao dịch.
- Số tiền, đơn vị tiền tệ, hạn mức và số dư được kiểm tra phía server.
- Không tin amount, account owner hoặc fee do client tự quyết định.
- Idempotency key hoặc mã tham chiếu nghiệp vụ ngăn xử lý lặp.
- Giao dịch có tính nguyên tử và được audit.

Ví dụ chuyển tiền cần authorization trên tài khoản nguồn, kiểm tra tài khoản đích theo chính sách và xác minh trạng thái của cả hai. Có quyền trên tài khoản nguồn không đồng nghĩa có quyền chuyển tiền vào bất kỳ tài khoản đích nào.

## 7. Đặt authorization ở đúng lớp

Controller có thể kiểm tra đăng nhập và permission chức năng tổng quát, nhưng object authorization nên được bảo đảm ở service hoặc domain layer nơi có đầy đủ object và ngữ cảnh nghiệp vụ. Nếu chỉ kiểm tra ở controller, một service có thể được gọi từ scheduled job, message consumer hoặc endpoint khác mà bỏ qua policy.

Một luồng tham khảo:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Authenticate principal]
    B --> C[Validate request shape]
    C --> D[Load object within allowed scope]
    D --> E[Evaluate action and object policy]
    E --> F[Check state and business constraints]
    F --> G[Apply change in transaction]
    G --> H[Write audit event]
    H --> I[Build permitted response]
~~~

Các lớp có trách nhiệm riêng:

- **Gateway/filter:** xác thực token, áp dụng giới hạn request và permission thô nếu phù hợp.
- **Controller:** xác định endpoint, validate định dạng, chuyển principal và request vào service.
- **Service/domain:** thực hiện policy theo object, field, trạng thái và luồng nghiệp vụ.
- **Repository/query:** giới hạn truy vấn theo tenant, owner hoặc phạm vi truy cập khi có thể.
- **Audit:** ghi nhận action nhạy cảm, actor, object, thời điểm và kết quả theo chính sách.

Không nên dựa vào việc client ẩn nút hoặc không hiển thị endpoint. Người dùng có thể tự tạo request. Cũng không nên chỉ dùng annotation ở controller như @PreAuthorize kiểm tra role chung rồi bỏ qua quyền trên object; annotation có thể là lớp bảo vệ bổ sung nhưng policy vẫn phải xét object cụ thể.

## 8. Xử lý response khi không có quyền

Khi từ chối truy cập, API cần thống nhất cách phản hồi:

| Trường hợp | Response có thể dùng | Lưu ý |
|---|---|---|
| Đã xác thực nhưng không có quyền trên object | 403 Forbidden | Thể hiện principal không được phép thực hiện action |
| Object không tồn tại hoặc được cố ý che giấu | 404 Not Found | Có thể dùng để tránh xác nhận sự tồn tại của object |
| Chưa xác thực hoặc credential không hợp lệ | 401 Unauthorized | Không tiết lộ thông tin object |
| Request sai định dạng hoặc thiếu điều kiện contract | 400 Bad Request hoặc 422 theo contract | Không thay thế kiểm tra authorization |

Chọn 403 hay 404 theo chính sách bảo vệ thông tin và giữ hành vi nhất quán giữa các endpoint. Nếu dùng 404 để che giấu object ngoài phạm vi, cần cân nhắc cả thời gian phản hồi, số lượng kết quả, thông báo lỗi và log để tránh side channel xác nhận sự tồn tại.

Không trả message như “object tồn tại nhưng thuộc về user khác” cho principal không có quyền. Log nội bộ có thể ghi nguyên nhân chi tiết với quyền truy cập phù hợp, nhưng không đưa thông tin đó vào response công khai.

## 9. Kiểm thử object authorization theo ma trận

Kiểm thử phải bao phủ principal, object, action và trạng thái. Chỉ test một tài khoản có quyền truy cập object của chính mình là chưa đủ.

### 9.1. Ma trận principal và object

Tối thiểu nên tạo dữ liệu kiểm thử cho:

- User A và object A thuộc user A.
- User B và object B thuộc user B.
- Hai user trong cùng tenant nhưng không có quan hệ chia sẻ.
- User thuộc tenant khác.
- Nhân viên có assignment hoặc quyền hỗ trợ cụ thể.
- Quản trị nghiệp vụ với phạm vi được giới hạn.

Sau đó kiểm tra các tổ hợp:

| Principal | Object | Kỳ vọng |
|---|---|---|
| User A | Object A | Cho phép theo policy |
| User A | Object B của user B cùng tenant | Từ chối nếu không có quan hệ được cấp |
| User A | Object của tenant khác | Từ chối |
| User B | Object A | Từ chối nếu không có quyền chia sẻ |
| Nhân viên hỗ trợ được phân công | Ticket được phân công | Cho phép đúng thao tác |
| Nhân viên hỗ trợ không được phân công | Ticket của người khác | Từ chối |

### 9.2. Kiểm thử riêng từng action

Với mỗi loại object, cần test riêng:

- **Read:** xem chi tiết, list, search, export, download và field nhạy cảm.
- **Update:** sửa field cho phép, gửi field cấm, đổi owner/tenant, sửa object ngoài phạm vi và update sai trạng thái.
- **Delete:** xóa object của người khác, xóa object có phụ thuộc, bulk delete trộn ID và gọi lại thao tác.
- **Action:** approve, cancel, refund, publish, assign hoặc action khác với principal không đủ quyền, sai trạng thái và vượt hạn mức.

Một permission update không được dùng làm bằng chứng cho permission delete hoặc approve. Mỗi action cần assertion riêng trong test.

### 9.3. Test ID được gửi ở mọi vị trí

Thử thay ID trong:

- Path parameter.
- Query parameter.
- Request body.
- Object lồng nhau và danh sách ID.
- Header hoặc reference được API hỗ trợ.

Đừng chỉ kiểm tra /orders/{id}; một endpoint batch hoặc nested route có thể chứa lỗ hổng tương tự. Với nested route, hãy gửi child ID thuộc parent khác để xác minh quan hệ cha-con được kiểm tra.

### 9.4. Test update và action có cạnh tranh

Với thao tác nhạy cảm, cần test hai request đồng thời hoặc trạng thái bị thay đổi giữa lúc kiểm tra và lúc ghi:

- Hai người cùng approve một khoản chi.
- Một người hủy đơn trong khi worker đang đánh dấu đơn đã giao.
- Quyền assignment bị thu hồi trong lúc người dùng đang cập nhật ticket.
- Hai request dùng cùng idempotency key hoặc cùng version.

Kết quả phải tuân theo transaction và state machine; không được có hai transition trái ngược cùng thành công hoặc một request tiếp tục dùng quyền đã bị thu hồi khi policy yêu cầu kiểm tra lại.

### 9.5. Ví dụ test service

~~~java
@Test
void userCannotUpdateAnotherUsersOrder() {
    Caller caller = caller("user-a", "tenant-a");
    Order order = orderOwnedBy("user-b", "tenant-a");

    when(orderRepository.findByIdAndTenantId(order.id(), "tenant-a"))
        .thenReturn(Optional.of(order));

    assertThrows(
        AccessDeniedException.class,
        () -> orderService.updateShippingAddress(
            order.id(),
            validAddressRequest(),
            caller
        )
    );

    verify(orderRepository, never()).save(any());
}
~~~

Ví dụ minh họa cần được điều chỉnh theo repository và service thực tế. Ngoài unit test policy, nên có integration test qua HTTP để xác nhận principal được tạo từ token, object ID được bind đúng và response không rò rỉ dữ liệu.

## 10. Audit và giám sát thao tác trên object

Các thao tác nhạy cảm cần có audit trail để hỗ trợ điều tra và truy vết:

- Actor/principal thực hiện thao tác.
- Action và loại object.
- Object ID hoặc mã tham chiếu được phép ghi nhận.
- Tenant hoặc phạm vi nghiệp vụ liên quan.
- Thời điểm, kết quả cho phép/từ chối và request correlation ID.
- Các field thay đổi ở mức phù hợp với chính sách dữ liệu.

Không ghi token, mật khẩu, secret hoặc toàn bộ object vào audit log. Với dữ liệu cá nhân, cần hạn chế field được lưu, thời gian retention và quyền truy cập log.

Metric hữu ích gồm số lần authorization denial theo endpoint/action, số lần truy cập chéo tenant, tỷ lệ lỗi policy, action nhạy cảm theo trạng thái và số request bị từ chối do object không thuộc phạm vi. Cần tránh metric label chứa ID người dùng hoặc object tùy ý vì cardinality cao và nguy cơ lộ dữ liệu.

Một đợt tăng đột biến 403/404 trên endpoint đọc object, nhiều lần thay ID hoặc nhiều request bị từ chối trên action tài chính có thể là dấu hiệu dò tìm hoặc lạm dụng. Cảnh báo cần có ngưỡng, ngữ cảnh và quy trình xử lý để tránh nhầm với client lỗi hoặc thay đổi quyền hợp lệ.

## 11. Những sai lầm thường gặp

- **Chỉ xác thực:** token hợp lệ không chứng minh principal có quyền trên object được yêu cầu.
- **Chỉ kiểm tra role:** role USER hoặc ADMIN không thể hiện đầy đủ ownership, tenant, assignment và trạng thái.
- **Tin vào ID khó đoán:** UUID không ngăn được người dùng gọi một ID họ đã biết hoặc lấy từ nơi khác.
- **Chỉ kiểm tra read:** update, delete và action có thể thiếu policy riêng.
- **Chỉ kiểm tra object cha:** object con hoặc object được tham chiếu có thể thuộc tenant khác.
- **Lọc danh sách ở client:** dữ liệu đã được gửi ra ngoài và count/search vẫn có thể làm lộ thông tin.
- **Bind entity trực tiếp:** client có thể thay đổi field nhạy cảm hoặc thuộc tính nội bộ.
- **Dùng update để thực hiện mọi action:** client có thể bỏ qua workflow, hạn mức hoặc separation of duties.
- **Kiểm tra quyền ngoài transaction:** trạng thái hoặc quan hệ có thể thay đổi trước khi ghi dữ liệu.
- **Chỉ bảo vệ controller:** service được gọi từ job hoặc consumer khác có thể bỏ qua kiểm tra.
- **Quên cache và export:** dữ liệu đã được lọc đúng ở endpoint chính vẫn có thể rò rỉ qua cache hoặc luồng dẫn xuất.
- **Trả lỗi quá chi tiết:** response xác nhận object tồn tại hoặc tiết lộ owner và tenant.
- **Không audit:** khó xác định ai đã đọc, sửa, xóa hoặc thực hiện action trên object.

## 12. Checklist trước khi phát hành endpoint

- [ ] Xác định principal, action, object, context và requested change trong policy.
- [ ] Principal và tenant được lấy từ security context đã xác thực.
- [ ] Mọi object ID từ path, query, body, nested object và batch đều được kiểm tra quyền.
- [ ] Read có scope theo owner, tenant, sharing hoặc assignment.
- [ ] List, search, count, export, download và cache áp dụng cùng phạm vi authorization.
- [ ] Field nhạy cảm chỉ xuất hiện trong response khi policy cho phép.
- [ ] Update dùng DTO allowlist và kiểm tra quyền theo field.
- [ ] Update kiểm tra trạng thái, quan hệ và transition nghiệp vụ.
- [ ] Kiểm tra quyền và ghi dữ liệu được bảo vệ trước race condition trong transaction.
- [ ] Delete có permission riêng và kiểm soát cascade, soft delete, restore cùng bulk operation.
- [ ] Action nghiệp vụ có endpoint/command rõ ràng, policy riêng, state check và audit.
- [ ] Action tài chính có kiểm tra hai phía, hạn mức, idempotency và tính nguyên tử.
- [ ] 401, 403, 404 và lỗi validation được sử dụng nhất quán theo contract.
- [ ] Test có principal cùng tenant, khác tenant, owner, non-owner và người được phân công.
- [ ] Test riêng read, update, delete và từng action trên object.
- [ ] Test ID ở path, query, body, nested object và batch.
- [ ] Có test cạnh tranh, version conflict hoặc replay cho thao tác nhạy cảm.
- [ ] Audit và metric không lưu token hoặc dữ liệu nhạy cảm không cần thiết.

Object authorization phải được xem là một phần của từng thao tác nghiệp vụ. Khi read, update, delete và action được kiểm tra độc lập trên đúng object, đúng principal và đúng trạng thái, API giảm nguy cơ BOLA/IDOR và giữ được ranh giới dữ liệu ngay cả khi client biết hoặc thay đổi object ID.
