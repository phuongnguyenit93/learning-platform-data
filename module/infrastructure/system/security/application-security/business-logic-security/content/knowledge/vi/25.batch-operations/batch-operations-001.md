# Batch command authorization — Phân quyền lệnh xử lý hàng loạt

## 1. Một request chứa nhiều ID không tạo ra quyền mới

Trong chương **Batch Operations** của Business Logic Security, batch command authorization là việc xác định người gọi có được thực hiện một lệnh hàng loạt hay không, rồi kiểm tra quyền của lệnh đó trên từng đối tượng và trên toàn tập đối tượng liên quan.

Ví dụ, API cho phép người quản lý phê duyệt nhiều đơn mua hàng trong một lần gọi:

```http
POST /order-approval-batches
Content-Type: application/json

{
  "items": [
    { "orderId": "O-101", "expectedVersion": 7 },
    { "orderId": "O-102", "expectedVersion": 4 },
    { "orderId": "O-999", "expectedVersion": 2 }
  ]
}
```

Người gọi có quyền duyệt O-101 và O-102 nhưng O-999 thuộc đơn vị khác. Endpoint không được suy luận rằng quyền của hai đơn đầu áp dụng cho cả danh sách. Một tài khoản được sử dụng chức năng batch cũng không mặc nhiên được duyệt mọi đơn trong tenant.

Chủ đề này trực tiếp bảo vệ các quy tắc nghiệp vụ khỏi bỏ qua phê duyệt, sửa giá, vượt quyền đối tượng và gửi lệnh trùng. Mục tiêu là giữ nguyên yêu cầu an ninh của từng lệnh đơn, đồng thời bổ sung những điều kiện chỉ xuất hiện khi nhiều lệnh được gộp lại.

Theo [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/), thao tác sử dụng ID từ client cần kiểm tra người gọi có quyền thực hiện hành động trên bản ghi tương ứng. Với batch, nguyên tắc này phải được áp dụng cho toàn bộ các đối tượng được yêu cầu, kể cả ID nằm sâu trong body.

## 2. Ba tầng quyết định quyền

### 2.1. Quyền gọi chức năng batch

Đây là câu hỏi: actor có được dùng lệnh `BATCH_APPROVE_ORDER` không?

Ứng dụng có thể cho một nhân viên duyệt từng đơn nhưng chỉ cho trưởng nhóm dùng batch. Sự khác biệt này là lựa chọn nghiệp vụ hợp lệ, miễn được định nghĩa rõ. Kiểm tra ở tầng chức năng phải được thực hiện trên server, không phụ thuộc việc giao diện có hiện nút “Duyệt nhiều đơn” hay không.

Nguyên tắc từ chối mặc định và kiểm tra quyền tại mỗi yêu cầu được trình bày trong [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html). Trong thiết kế của bài, quyền batch là một điều kiện đầu vào, chưa phải toàn bộ quyết định cấp quyền.

### 2.2. Quyền trên từng đối tượng và thao tác

Với mỗi item, cần xác định ít nhất:

| Thành phần | Nguồn có thẩm quyền | Câu hỏi cần trả lời |
| --- | --- | --- |
| Actor | Session/token đã được xác minh và trạng thái tài khoản hiện hành | Ai thực sự yêu cầu lệnh? |
| Tenant | Ngữ cảnh tenant đã được xác thực và membership | Actor đang hành động trong phạm vi nào? |
| Đối tượng | Database, truy vấn có phạm vi tenant | Đơn nào sẽ bị tác động? |
| Action | Hợp đồng endpoint hoặc danh sách lệnh được cho phép | Đây là duyệt, gửi duyệt, hủy hay sửa? |
| Thuộc tính nghiệp vụ | Dữ liệu hiện hành của đơn và policy | Trạng thái, giá trị, đơn vị, người tạo có thỏa điều kiện không? |
| Quan hệ cấp quyền | Phân công và ủy quyền có hiệu lực | Actor có được thực hiện action trên đơn này không? |

Trong ví dụ, `APPROVE` cần đơn ở PENDING_APPROVAL, actor được phân công, actor khác người tạo và giá trị đơn nằm trong phạm vi phê duyệt. Một quyền `READ_ORDER` không thay thế quyền này.

### 2.3. Điều kiện trên toàn batch

Có những quy tắc không thể kiểm tra bằng cách xét từng item riêng lẻ:

- Tổng giá trị phê duyệt trong một batch không vượt hạn mức được giao.
- Một batch chỉ thuộc một tenant và một loại lệnh.
- Không dùng cùng một bằng chứng phê duyệt để đáp ứng hai vị trí bắt buộc độc lập.
- Các đơn phụ thuộc nhau phải ở trạng thái tương thích.
- Cùng một đối tượng không được xuất hiện nhiều lần để làm tăng số lượt phê duyệt hoặc gây hoàn tác lặp.

Có thể biểu diễn hợp đồng của một batch nguyên tử như sau:

```text
Cho phép batch khi:
  actor có quyền dùng chức năng batch
  VÀ mọi item đều được cấp quyền cho đúng action
  VÀ mọi item đều thỏa điều kiện chuyển trạng thái
  VÀ toàn tập item thỏa các invariant chung
```

Điều kiện “mọi item” không được thay bằng “tồn tại ít nhất một item hợp lệ”. Nếu có hạn mức tích lũy theo ngày, kiểm tra tổng của request hiện tại cũng chưa đủ; phải cập nhật phần hạn mức đã sử dụng một cách nhất quán với các batch cạnh tranh.

## 3. Những cách triển khai dễ bị lạm dụng

### 3.1. Chỉ kiểm tra phần tử đầu tiên

```java
Order first = repository.findById(command.items().get(0).orderId());
policy.requireApprove(actor, first);
repository.approveAll(command.orderIds());
```

Kẻ tấn công đặt một ID được phép ở đầu rồi trộn ID ngoài phạm vi vào giữa hoặc cuối danh sách. Đổi thứ tự input là một biến thể kiểm thử quan trọng vì một số đoạn mã vô tình lấy tenant hoặc owner từ phần tử đầu làm ngữ cảnh cho tất cả.

### 3.2. Kiểm tra quyền đọc thay cho quyền ghi

Một API tìm được toàn bộ đơn “có thể xem”, sau đó duyệt tất cả. Người xem báo cáo có thể đọc đơn của nhiều bộ phận nhưng chỉ được phê duyệt một phạm vi hẹp. Sử dụng kết quả truy vấn đọc làm tập đối tượng được ghi đã làm mất ý nghĩa action.

### 3.3. Kiểm tra đúng rồi ghi một tập rộng hơn

Luồng kiểm tra dùng `allowedIds`, còn câu lệnh cập nhật lại dùng `request.ids`. Một biến thể khác là worker chạy lại bộ lọc sau vài phút và lấy thêm những đơn chưa từng được kiểm tra. Vấn đề nằm ở việc tập đã được cấp quyền khác tập thực sự bị tác động.

### 3.4. Cộng gộp quyền giữa các item

Không thể dùng quyền trên O-101 để duyệt O-102, hoặc lấy thuộc tính `manager=true` của một item làm quyết định cho cả batch. Tương tự, hai tài khoản cùng gửi request không tự tạo thành hai người duyệt độc lập nếu chúng đại diện cùng một chủ thể theo quy tắc tách biệt nhiệm vụ.

## 4. Thiết kế hợp đồng request trước khi tối ưu

### 4.1. Chỉ nhận dữ liệu cần thiết cho ý định của client

Với endpoint chuyên phê duyệt, mỗi item thường chỉ cần ID, phiên bản kỳ vọng và dữ liệu nghiệp vụ được phép cung cấp như lý do duyệt. Không lấy các field sau làm giá trị có thẩm quyền:

```text
actorId, approvedBy, tenantId, ownerId,
authorizationPassed, currentStatus, committedPrice
```

Tenant chọn trên giao diện vẫn phải được đối chiếu với membership hiện hành. Nếu API cho phép quản trị viên hành động xuyên tenant, cần một policy riêng, giới hạn phạm vi rõ và ghi nhận lý do; không dùng field `crossTenant=true` để bật khả năng đó.

Nếu batch nhận nhiều loại action, phải kiểm tra từng bộ `(actor, action, resource)` và các tổ hợp action được phép. Thiết kế một endpoint chuyên cho một lệnh thường giúp việc xét quyền và kiểm thử dễ hiểu hơn.

### 4.2. Xác định quy tắc với ID trùng

Trong hợp đồng minh họa, ID trùng bị từ chối ngay ở bước xác thực cấu trúc. Không âm thầm đếm một ID hai lần để tăng số quyết định hoặc tính hạn mức sai.

Có thể chọn chuẩn hóa thành tập nếu nghiệp vụ cho phép, nhưng phải công bố rõ ảnh hưởng đến thứ tự, kết quả và fingerprint idempotency. Hai item cùng ID nhưng có phiên bản hoặc nội dung khác nhau cần được coi là xung đột, không chọn tùy tiện phần tử đầu hay cuối.

### 4.3. Giới hạn đầu vào và đối tượng tham chiếu

Đặt giới hạn số item, kích thước body và số đối tượng liên quan cần đọc. Một item có thể tham chiếu nhiều tài nguyên như đơn, kho, tài khoản chi phí và người nhận. Không chỉ kiểm tra `orderId` rồi tin rằng `warehouseId` hoặc `budgetAccountId` khách gửi cũng thuộc đúng phạm vi.

Giới hạn batch giúp kiểm soát chi phí kiểm tra quyền, thời gian giữ lock và lượng dữ liệu kết quả. Rate limit theo số request đơn thuần có thể cho phép một request chứa lượng công việc lớn hơn nhiều request đơn.

## 5. Chọn rõ nguyên tử hay thành công từng phần

### 5.1. Batch nguyên tử

Trong mô hình **all-or-nothing**, nếu một item không đủ quyền hoặc không thỏa nghiệp vụ, không item nào được áp dụng. Với ví dụ O-101, O-102, O-999, hai đơn đầu vẫn phải giữ nguyên khi O-999 làm batch thất bại.

Một transaction database là một phần của cách thực hiện, nhưng chưa bao phủ lời gọi ngoài như gửi email hoặc yêu cầu thanh toán. Nếu đã phát lệnh ngoài trước khi phát hiện item sai quyền, rollback dữ liệu nội bộ không thu hồi lệnh ngoài đó. Có thể ghi outbox trong transaction rồi để consumer thực thi sau commit, kèm cơ chế chống xử lý trùng.

### 5.2. Batch thành công từng phần

Trong mô hình **best-effort**, từng item có thể thành công hoặc bị từ chối độc lập theo hợp đồng. Item không đủ quyền vẫn không được thực thi. Response cần ánh xạ kết quả tới tham chiếu item ổn định, không chỉ trả một dòng “batch thành công”.

Không tự biến API nguyên tử thành best-effort bằng cách lọc bỏ ID bị cấm rồi xử lý phần còn lại. Client cần biết rõ mô hình nào được áp dụng để quyết định thử lại, đối soát và hiển thị trạng thái.

### 5.3. Invariant quyết định đơn vị transaction

Nếu nhiều item cùng tiêu thụ một hạn mức chung hoặc cùng tạo một kết quả phê duyệt, chúng có thể không độc lập. Chia chúng vào các transaction riêng không tự bảo vệ invariant của cả nhóm.

Hãy xác định đơn vị nghiệp vụ cần được chấp nhận hoặc từ chối cùng nhau. Nếu chỉ hỗ trợ batch nguyên tử nhỏ, từ chối batch quá lớn và yêu cầu chia theo quy tắc được công bố; đừng âm thầm commit từng chunk rồi vẫn báo rằng cả request là nguyên tử.

## 6. Đặt quyết định quyền sát với thời điểm thực thi

Luồng khuyến nghị cho một batch nguyên tử nhỏ:

```text
Xác thực actor và tenant
  → kiểm tra quyền chức năng batch
  → xác thực cấu trúc, số lượng, ID trùng
  → bắt đầu transaction nghiệp vụ
  → đọc/khóa tập đối tượng đúng tenant
  → xác minh nhận đủ tập đã yêu cầu
  → kiểm tra quyền, trạng thái, phiên bản của mọi item
  → kiểm tra invariant chung
  → áp dụng chuyển trạng thái + quyết định + outbox
  → commit
  → trả receipt của batch
```

### 6.1. Không bỏ qua item biến mất sau truy vấn

Một truy vấn `WHERE tenant_id = :tenant AND id IN (:ids)` có thể trả ít dòng hơn input. Đừng coi đó là lý do bỏ qua các ID còn thiếu trong batch nguyên tử. So sánh tập ID duy nhất được yêu cầu với tập kết quả thực nhận, rồi từ chối theo chính sách thông tin của API nếu không khớp.

Tuy nhiên, đếm đủ dòng chỉ chứng minh đã lấy được tập dữ liệu, chưa chứng minh quyền `APPROVE`. Các kiểm tra phân công, người tạo, trạng thái và hạn mức vẫn phải chạy.

### 6.2. Chống khoảng trống giữa kiểm tra và sử dụng

Một đơn có thể đổi chủ, đổi trạng thái hoặc giá trị sau khi kiểm tra. Khóa dòng, kiểm tra phiên bản tại câu lệnh ghi, hoặc cơ chế đồng thời khác cần bảo vệ những thuộc tính có ảnh hưởng đến quyết định.

Khóa dòng đơn không tự khóa bảng phân công duyệt hay chính sách quyền. Nếu yêu cầu thu hồi quyền có hiệu lực ngay trước commit, cần phối hợp với thao tác thu hồi: chẳng hạn khóa bản ghi quyền liên quan hoặc kiểm tra policy version bằng điều kiện nguyên tử tại điểm ghi. Nếu hệ thống chọn điểm quyết định khác, phải định nghĩa rõ trong hợp đồng và kiểm thử theo điểm đó.

Với hạn mức dùng chung, hai batch cùng đọc “còn 100” rồi mỗi batch dùng 80 có thể đều qua kiểm tra. Phần cập nhật hạn mức phải có cơ chế chống vượt tổng, ví dụ cập nhật có điều kiện hoặc khóa bản ghi hạn mức cùng transaction.

## 7. Minh họa Java: phân quyền toàn tập trước khi áp dụng

Đoạn mã sau minh họa một batch nguyên tử đồng bộ, kích thước nhỏ. Các kiểu repository, policy và domain là thành phần ứng dụng cần hiện thực; ví dụ không bao gồm toàn bộ API, cơ chế idempotency hoặc hệ thống IAM.

```java
public record ApproveItem(UUID orderId, long expectedVersion) {}
public record ApproveBatch(List<ApproveItem> items) {}

@Service
public class BatchApprovalService {
    private final CurrentActor currentActor;
    private final BatchInputValidator inputValidator;
    private final OrderRepository orders;
    private final ApprovalPolicy policy;
    private final ApprovalDecisionRepository decisions;
    private final OutboxRepository outbox;

    // Constructor injection omitted.

    @Transactional(rollbackFor = Exception.class)
    public BatchReceipt approve(ApproveBatch command) {
        Actor actor = currentActor.requireAuthenticatedActor();
        policy.requireBatchApprovalCapability(actor);

        List<ApproveItem> requested = inputValidator.validate(command.items());
        // Validates non-empty, size limit, nulls and duplicate order IDs.
        List<UUID> ids = requested.stream()
            .map(ApproveItem::orderId)
            .sorted()
            .toList();

        List<Order> locked = orders.lockAllInTenant(actor.tenantId(), ids);
        Map<UUID, Order> byId = locked.stream().collect(
            Collectors.toMap(Order::id, Function.identity()));

        if (!byId.keySet().equals(new HashSet<>(ids))) {
            throw new BatchNotProcessableException();
        }

        ApprovalPolicyScope scope = policy.acquireStableScope(actor, locked);
        for (ApproveItem item : requested) {
            Order order = byId.get(item.orderId());
            policy.requireApprove(scope, actor, order);
            order.requirePendingApproval();
            order.requireVersion(item.expectedVersion());
        }
        policy.requireBatchInvariants(scope, actor, locked);

        UUID batchId = UUID.randomUUID();
        for (Order order : locked) {
            ApprovalDecision decision = order.approveBy(actor.id(), batchId);
            decisions.append(decision);
            outbox.append(OrderApproved.from(order, decision));
        }
        orders.flush();
        return BatchReceipt.approved(batchId, ids);
    }
}
```

Ý nghĩa của các thành phần quan trọng:

- `CurrentActor` lấy danh tính từ ngữ cảnh xác thực phía server, không đọc actor từ body.
- `lockAllInTenant` giới hạn tenant và khóa theo một thứ tự ổn định được repository thực thi. Việc truyền danh sách đã sắp xếp không tự bảo đảm database lấy lock đúng thứ tự.
- `acquireStableScope` đại diện cơ chế giữ quyết định quyền/hạn mức nhất quán với chính sách thu hồi và cạnh tranh của ứng dụng. Đây là phần cần hiện thực, không phải API sẵn có của Spring.
- Vòng kiểm tra hoàn tất trên mọi item trước vòng áp dụng. Điều này tránh tác động sớm và giúp lỗi quyền dễ hiểu hơn.
- Transaction vẫn phải rollback nếu lỗi xảy ra trong vòng áp dụng hoặc khi flush/commit. Kiểm tra trước không thay thế ràng buộc database.
- Quyết định, thay đổi đơn và outbox phải tham gia cùng transaction/resource phù hợp. `append` ở đây không phải gọi dịch vụ ngoài ngay lập tức.

Với Spring, cấu hình rollback mặc định không coi mọi checked exception là nguyên nhân rollback. Ví dụ khai báo `rollbackFor = Exception.class` để thể hiện rõ yêu cầu của luồng minh họa; cần kiểm tra cấu hình thực tế. Xem [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring/reference/7.0/data-access/transaction/declarative/rolling-back.html).

Phương thức cũng phải được gọi qua cơ chế transaction đã cấu hình. Trong proxy mode, gọi nội bộ `this.approve(...)` không tự kích hoạt transaction qua proxy. Chi tiết nằm trong [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

## 8. Bulk SQL không được làm rộng tập đã cấp quyền

Đây là lỗi phổ biến sau một lần tối ưu hiệu năng:

```sql
UPDATE purchase_order
SET status = 'APPROVED'
WHERE id IN (:request_ids);
```

Câu lệnh không thể hiện tenant, trạng thái, phiên bản hay phân công. Nếu phần kiểm tra trước đó chỉ bao phủ một tập con, câu lệnh sẽ ghi rộng hơn tập được cấp quyền.

Một thiết kế dùng bulk update cần giữ được những bảo đảm tương đương luồng domain:

1. Tập ID đem ghi chính là tập đã được xác thực, không lấy lại từ một bộ lọc có thể thay đổi.
2. Tenant lấy từ ngữ cảnh tin cậy được ràng buộc trong truy vấn.
3. Phiên bản và trạng thái được bảo vệ tại thời điểm ghi.
4. Các điều kiện quyền không bị mất khi chuyển từ Java sang SQL.
5. Số dòng và danh tính dòng bị tác động được đối chiếu với kỳ vọng; thiếu một dòng làm rollback batch nguyên tử.
6. Bản ghi quyết định, hạn mức và outbox vẫn nhất quán với những dòng đã đổi.

Dùng tham số bind cho giá trị và danh sách; không nối trực tiếp ID hoặc biểu thức lọc từ client thành SQL. Với JPA bulk update, cũng cần quản lý sự nhất quán của persistence context theo API ORM đang dùng; đừng đọc lại entity cũ trong cùng context rồi kết luận trạng thái đúng.

Nếu triển khai thêm row-level security, hãy coi đó là một lớp bảo vệ và kiểm tra quyền database của kết nối ứng dụng. Nó không tự hiện thực tách biệt nhiệm vụ hay hạn mức phê duyệt của domain. PostgreSQL mô tả các trường hợp owner, superuser hoặc role có khả năng bỏ qua row security trong [Row Security Policies](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).

## 9. Job bất đồng bộ và thao tác “chọn tất cả”

### 9.1. Quyền submit job khác quyền thực thi item

Job có thể chạy khi session gốc đã hết hạn, quyền đã bị thu hồi hoặc đơn đã đổi trạng thái. Lưu actor, tenant, action và phạm vi yêu cầu trong bản ghi job do server quản lý. Worker không được tự thay actor bằng tài khoản dịch vụ có toàn quyền rồi duyệt mọi ID.

Chọn rõ một trong các mô hình:

| Mô hình | Điều phải xác định |
| --- | --- |
| Xét quyền hiện hành khi thực thi | Worker tải và kiểm tra quyền phù hợp trước khi áp dụng từng đơn vị công việc |
| Ủy quyền có thời hạn | Phạm vi, action, thời hạn, cơ chế thu hồi và việc sử dụng delegation được xác minh |
| Snapshot quyền theo điểm quyết định được công bố | Chấp nhận rõ rủi ro thay đổi quyền sau thời điểm đó và giới hạn phạm vi đã được chấp thuận |

Không chỉ lưu `authorized=true` mà không có chủ thể, phạm vi, thời điểm và cơ chế kiểm chứng. Trạng thái nghiệp vụ, phiên bản và invariant vẫn cần được kiểm tra ở thời điểm áp dụng ngay cả khi có delegation hợp lệ.

Quyền xem tiến độ, tải kết quả, thử lại và hủy job cũng phải được kiểm tra theo job cụ thể. Một `jobId` khó đoán không thay thế kiểm soát quyền.

### 9.2. “Tất cả kết quả tìm kiếm” là một lệnh có phạm vi

Client có thể gửi bộ lọc “mọi đơn đang chờ”, nhưng không được tự quyết định rằng bộ lọc đó bao phủ mọi tenant hoặc mọi bộ phận. Server phải giao phạm vi bộ lọc với phạm vi hành động được phép.

Để tránh tập thay đổi giữa lúc xem trước và chạy, có thể tạo selection manifest do server quản lý: actor, tenant, action, danh sách ID/phiên bản, thời hạn và định danh lựa chọn. Manifest giúp cố định ý định, không thay thế kiểm tra quyền hiện hành khi thực thi theo chính sách đã chọn.

Nếu dùng lựa chọn động thay vì snapshot, phải công bố rõ rằng đối tượng mới phù hợp có thể được xét tới và vẫn kiểm tra từng đối tượng. Không để một bộ lọc vốn dành cho xuất báo cáo được tái sử dụng trực tiếp làm quyền duyệt hàng loạt.

## 10. Gửi lại, kết quả lỗi và dấu vết kiểm toán

### 10.1. Idempotency không thay thế authorization

Với một batch nguyên tử có idempotency key, phạm vi lưu kết quả cần gắn tenant, actor, action và fingerprint nội dung được định nghĩa ổn định. Cùng key nhưng đổi tập ID hoặc phiên bản phải bị xử lý như xung đột theo hợp đồng.

Khi trả lại receipt cũ, vẫn kiểm tra người gọi có quyền truy xuất kết quả đó theo chính sách hiện hành. Key của actor A không được giúp actor B đọc danh sách đơn hoặc kết quả phê duyệt của A.

Một key mới cũng không cho phép duyệt lại đơn đã hoàn tất. State machine, ràng buộc quyết định duy nhất và cơ chế khử trùng consumer tiếp tục bảo vệ domain.

### 10.2. Lỗi không được trở thành API dò tìm đối tượng

Batch chứa ID không được phép có thể làm lộ đơn của tenant khác nếu response trả chi tiết owner, giá hoặc trạng thái. Thiết kế mã lỗi theo mức thông tin actor được biết.

Ví dụ, với ID không tồn tại hoặc ngoài phạm vi, ứng dụng có thể trả cùng một kết quả “không thể xử lý đối tượng”. Với đơn mà actor được đọc nhưng không được duyệt, có thể cho biết lý do nghiệp vụ ở mức phù hợp. Đây là lựa chọn hợp đồng, không phải yêu cầu trả cùng mã cho mọi lỗi.

Audit phía server nên ghi actor, tenant, action, batch ID, số item và quyết định cấp quyền cần thiết để điều tra. Không ghi nguyên token hoặc toàn bộ dữ liệu nhạy cảm của các đơn bị từ chối. Audit từ chối có thể được giữ dù transaction nghiệp vụ rollback; không nhầm bản ghi đó với một quyết định phê duyệt đã thành công.

## 11. Kiểm thử tình huống tấn công logic

Mỗi nhóm ca âm cần một positive control với actor, dữ liệu và định dạng hợp lệ trên fixture riêng. Chụp dữ liệu trước và đọc lại bằng transaction mới sau request; không chỉ so status HTTP hoặc dùng entity JPA đang được quản lý làm cả hai bản chụp.

| Tình huống | Biến thể nên thử | Oracle cần chứng minh |
| --- | --- | --- |
| Trộn ID bị cấm | Đặt ID ở đầu, giữa, cuối | Batch nguyên tử không đổi bất kỳ đơn nào |
| Khác tenant | Một ID tenant B trong batch tenant A | Không tác động hoặc lộ dữ liệu của B |
| Sai action | Actor có quyền đọc nhưng không có quyền duyệt | Không tạo quyết định duyệt |
| Tự duyệt | Một item do actor tạo giữa các item khác | Quy tắc tách biệt nhiệm vụ vẫn áp dụng |
| ID trùng | Lặp cùng ID, hoặc khác expectedVersion | Xử lý theo hợp đồng; không tăng số quyết định |
| Vượt tổng | Từng đơn dưới hạn mức nhưng tổng vượt | Không lách invariant toàn batch |
| Cạnh tranh hạn mức | Hai batch cùng tiêu thụ một phần hạn mức | Tổng sau commit không vượt trần |
| Đổi trạng thái | Một item được xử lý bởi request khác sau precheck | Không ghi theo trạng thái cũ |
| Thu hồi quyền | Thu hồi trong khoảng giữa submit và worker | Hành vi đúng mô hình quyền đã công bố |
| Lỗi khi ghi item cuối | Gây lỗi persistence sau các thay đổi trước | Batch nguyên tử không còn dữ liệu hoặc outbox dở |
| Replay | Cùng key/cùng payload, cùng key/khác payload | Không tạo quyết định hoặc receipt nhầm phạm vi |
| Ghi ngoài database | Fake consumer xử lý outbox liên quan | Không phát sinh tác động từ batch bị từ chối |

Với test race, dùng barrier/latch tại điểm cạnh tranh được kiểm soát, không dựa vào một khoảng sleep. Với luồng bất đồng bộ, kiểm tra cả lệnh đã enqueue và tác động sau khi consumer xử lý; một lần đọc ngay sau response chưa đủ chứng minh không có tác động muộn.

Nếu test dùng session cookie và bật CSRF, cung cấp token hợp lệ khi mục tiêu là authorization. Thiếu CSRF có thể làm request bị chặn trước khi đi tới lỗi quyền cần phát hiện. Tương tự, body phải hợp lệ để một lỗi parse không tạo ra ca âm giả.

## 12. Bài tập thiết kế

Một trưởng nhóm được duyệt các đơn của bộ phận A, trừ đơn do chính mình tạo. Hạn mức mỗi batch là 100 triệu đồng và hạn mức còn lại trong ngày là 150 triệu đồng. Những con số này chỉ phục vụ mô hình kiểm thử kỹ thuật.

Batch X chứa ba đơn: 40 triệu được phép, 30 triệu do trưởng nhóm tự tạo và 20 triệu thuộc bộ phận B. Batch Y và Z chạy đồng thời, mỗi batch chứa các đơn hợp lệ có tổng 90 triệu.

Hãy xác định:

1. Quyền chức năng, quyền từng đối tượng và invariant toàn batch nằm ở đâu?
2. Với mô hình nguyên tử, sau X dữ liệu nào bắt buộc giữ nguyên?
3. Cần bảo vệ bản ghi hạn mức thế nào để Y và Z không cùng vượt phần còn lại trong ngày?
4. Nếu chuyển sang job bất đồng bộ, worker cần biết những thông tin tin cậy nào và kiểm tra lại điều gì?
5. Response và audit nào giúp điều tra mà không lộ thông tin của bộ phận B?
6. Ca kiểm thử nào chứng minh việc tối ưu bằng bulk SQL vẫn ghi đúng tập đã cấp quyền?

Batch command authorization được thực hiện đúng khi một request chứa nhiều item vẫn phải đáp ứng đủ quyền và điều kiện của từng lệnh đơn, đồng thời giữ được các invariant của toàn nhóm tại thời điểm thực thi.
