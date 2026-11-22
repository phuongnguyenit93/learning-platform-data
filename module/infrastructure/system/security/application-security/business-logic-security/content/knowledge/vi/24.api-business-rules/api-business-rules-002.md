# Business query endpoint: truy vấn có ngữ nghĩa nghiệp vụ

## 1. Query nghiệp vụ trả lời một câu hỏi, không chỉ đọc một hàng dữ liệu

Một API có thể trả số tiền đơn hàng, danh sách refund và các trạng thái riêng lẻ. Nhưng người dùng thực sự cần biết “hiện có thể yêu cầu hoàn bao nhiêu?” hoặc “hồ sơ này còn thiếu điều kiện gì để duyệt?”.

**Business query endpoint** là endpoint trả lời một câu hỏi có ý nghĩa domain bằng cách kết hợp dữ liệu, quan hệ và quy tắc cần thiết, trong phạm vi người gọi được phép biết.

Ví dụ:

- Xem ngữ cảnh phê duyệt của một đề nghị.
- Xem số tiền tối đa có thể yêu cầu hoàn theo snapshot hiện tại.
- Xem trạng thái một operation và bước xử lý còn chờ.
- Xem tổng chi phí của những hồ sơ thuộc phạm vi được phép.
- Xem các action phù hợp để dựng giao diện thao tác.

Các truy vấn này thường được dùng trước một command nhạy cảm. Nếu server hoặc client hiểu nhầm kết quả query là quyền thực thi lâu dài, kẻ lạm dụng có thể dùng snapshot cũ để vượt hạn mức, bỏ qua phê duyệt hoặc tiêu thụ cùng một giá trị nhiều lần.

Mục tiêu là trả lời đúng, đúng phạm vi, đủ rõ về độ mới và không để kết quả đọc trở thành đường bỏ qua kiểm tra khi ghi.

## 2. Phân biệt query, preview, reservation và command

| Loại | Ý nghĩa | Ví dụ |
|---|---|---|
| Query | Quan sát một câu hỏi nghiệp vụ theo dữ liệu được đọc | Hiện còn bao nhiêu tiền có thể hoàn? |
| Preview | Tính kết quả dự kiến của một ý định chưa được thực hiện | Nếu hoàn 100.000 thì phân bổ dự kiến ra sao? |
| Reservation/cam kết có thời hạn | Giữ một phần khả năng hoặc điều kiện theo hợp đồng | Giữ quyền dùng một suất ưu đãi đến hạn |
| Command | Yêu cầu thay đổi nghiệp vụ | Tạo yêu cầu hoàn tiền và giữ phần tiền tương ứng |

### 2.1. Preview không tự giữ được kết quả

Nếu query báo có thể hoàn 150.000, một command khác có thể giữ 100.000 trước khi người gọi xác nhận. Query không sai chỉ vì trạng thái thay đổi sau thời điểm đọc, nhưng API phải không hứa rằng 150.000 đã được giữ riêng.

Nếu nghiệp vụ cần giữ một điều kiện, thiết kế một hành động reservation hoặc cơ chế cam kết riêng, có scope, thời hạn và chống sử dụng trùng. Không ngầm tiêu thụ tài nguyên trong endpoint mang nghĩa xem trước.

### 2.2. GET không nên âm thầm thực hiện command

Một GET trạng thái không được tự phê duyệt, tạo payment mới hoặc sử dụng coupon. Ghi access log, metrics hay cache biểu diễn là tác dụng phụ phụ trợ khác với hành động nghiệp vụ được chấp nhận.

Một truy vấn phức tạp có thể dùng POST theo hợp đồng ứng dụng, nhưng POST không mặc định có ngữ nghĩa safe của HTTP. Dù chọn method nào, cần nói rõ endpoint chỉ tính/đọc hay tạo tác động.

### 2.3. Query và command có thể dùng chung quy tắc nhưng khác bảo đảm

Có thể tái sử dụng các hàm domain thuần để tính capacity hoặc đánh giá điều kiện. Tuy nhiên, query chạy trên snapshot không tự có bảo vệ nguyên tử mà command cần khi tiêu thụ capacity đó.

Không để command chỉ gọi lại một API preview ngoài transaction rồi tin cờ `eligible = true`. Kiểm tra và sử dụng phải được ràng buộc trong thiết kế nhất quán của command.

## 3. Thiết kế câu hỏi và hợp đồng dữ liệu

### 3.1. Đặt tên theo ý nghĩa người dùng cần hiểu

Ví dụ các tài nguyên truy vấn:

```http
GET /tenants/{tenantId}/expense-requests/{expenseId}/approval-context
GET /tenants/{tenantId}/orders/{orderId}/refund-preview
GET /tenants/{tenantId}/payment-operations/{operationId}
GET /tenants/{tenantId}/expense-requests/summary
```

Tên endpoint cần được giải thích bằng hợp đồng. `approval-context` có thể gồm căn cứ đang xét, trạng thái vòng duyệt và những điều kiện được phép tiết lộ; nó không tự ghi một phiếu duyệt.

`refund-preview` có thể nhận số tiền dự kiến theo query để tính toán, nhưng không vì vậy mà số tiền client muốn hoàn trở thành quyền hoàn tương ứng.

### 3.2. Response có ngữ nghĩa, không chỉ field thô

Một response minh họa:

```json
{
  "orderId": "order-17",
  "orderVersion": 18,
  "refundLedgerVersion": 7,
  "currency": "VND",
  "maximumRefundable": "150000",
  "requestedAmount": "100000",
  "eligibility": "ELIGIBLE_AT_SNAPSHOT",
  "createsReservation": false,
  "dataAsOf": "2026-11-22T02:30:00Z"
}
```

Đây là ví dụ định dạng, không phải kết quả chạy thực tế. Trường thời gian phải phản ánh căn cứ nguồn theo định nghĩa của API, không chỉ lấy giờ hiện tại để tạo cảm giác dữ liệu vừa được đồng bộ.

`createsReservation = false` và trạng thái có điều kiện giúp client hiểu đây là quan sát tại snapshot. Các thông tin nội bộ chỉ nên trả khi cần cho quyết định hoặc xử lý tiếp theo của client.

### 3.3. Tránh boolean làm mất trạng thái chưa biết

Một `canRefund = false` có thể nghĩa là không đủ điều kiện, hoặc chỉ là dịch vụ đánh giá tạm thời lỗi. Hai tình huống cần cách xử lý khác nhau.

Có thể dùng các trạng thái như đủ điều kiện tại snapshot, không đủ điều kiện, cần dữ liệu bổ sung hoặc chưa đánh giá được theo hợp đồng.

Điều này chỉ áp dụng khi quyền đọc dữ liệu đã được xác lập. Nếu chính authorization cho việc xem không đánh giá được, không được trả dữ liệu nhạy cảm rồi gắn một nhãn `UNKNOWN` để thay kiểm tra truy cập.

## 4. Quyền đọc theo tenant, đối tượng và field

### 4.1. Query an toàn về tác động vẫn có thể rò rỉ dữ liệu

Số dư, hạn mức, trạng thái phê duyệt, người nhận tiền hoặc số lượng hồ sơ đều có thể nhạy cảm. Không dùng GET hoặc chữ “preview” làm lý do bỏ authentication/authorization.

Quyền trong tenant A không được dùng để truy vấn B. Biết order ID, operation ID hay một cursor không tạo quyền đọc.

### 4.2. Phân biệt quyền xem với quyền thực hiện action

Một người có thể được xem hồ sơ nhưng không được duyệt. Query có thể trả thông tin phù hợp để UI hiển thị thao tác bị hạn chế, nhưng không nên tiết lộ mọi rule nội bộ hoặc danh tính người có quyền.

Một người được phép đọc refund preview cũng không tự được hoàn tiền. Command refund cần permission riêng cùng các guards hiện hành.

`availableActions` trong response chỉ là kết quả đánh giá phục vụ ngữ cảnh tại thời điểm đọc. Không nhận danh sách đó trở lại rồi coi như một capability có thẩm quyền.

### 4.3. Giới hạn projection theo quyền dữ liệu

Đừng serialize toàn bộ entity và đồ thị quan hệ. Một query về tình trạng hồ sơ không nhất thiết được trả tài khoản ngân hàng, tài liệu nhân sự hoặc tất cả audit nội bộ.

Nếu hỗ trợ `fields`, `include` hoặc mở rộng quan hệ, mỗi lựa chọn phải nằm trong allowlist và phạm vi dữ liệu người gọi được biết. Định danh field không phải quyền truy cập field.

### 4.4. Lỗi truy vấn không được làm lộ đối tượng ngoài phạm vi

Với người không được biết tài nguyên tồn tại, có thể trả `404` theo chính sách. Với người được biết nhưng không có quyền xem phần cụ thể, xử lý theo hợp đồng thích hợp.

Không trả tên owner, số tiền hoặc trạng thái của tenant khác chỉ để giải thích query không được phép. Log và công cụ hỗ trợ cũng cần quyền phù hợp.

## 5. Đặt đúng công thức và nguồn dữ liệu nghiệp vụ

### 5.1. Ví dụ số tiền còn có thể hoàn

Trong một mô hình đơn giản không có các điều chỉnh khác:

```text
khả năng hoàn còn lại
    = tiền đã thu theo căn cứ được dùng
    - tiền đã hoàn thành công
    - phần đã được giữ cho các refund đang chờ
```

Giả sử đã thu 300.000, đã hoàn 100.000 và đang giữ 50.000 cho một refund chưa kết thúc. Capacity còn lại là 150.000, không phải 200.000.

Thực tế phải xác định đủ các loại điều chỉnh của ledger và policy. Không trộn số tiền khách đã trả với số ròng bên bán nhận sau phí, hoặc cộng các loại tiền khác nhau như cùng đơn vị.

Khi một refund chuyển từ đang chờ sang thành công, không được trừ hai lần vì nó vẫn bị tính ở cả hai nhóm. Trạng thái operation và sổ dữ liệu phải có ngữ nghĩa nhất quán.

### 5.2. Tồn kho và ngân sách cũng cần phân biệt dữ kiện

Nếu `available` đã trừ reservation, query không được trừ reservation lần nữa. Nếu chỉ có `onHand`, cần biết phần đã giữ và quy tắc buffer nếu có.

Tương tự, tổng chi đã thanh toán khác tổng nghĩa vụ đã cam kết nhưng chưa trả. Một query quyết định khả năng dùng ngân sách phải dùng đại lượng phù hợp câu hỏi, không chỉ `SUM` những hàng thuận tiện.

### 5.3. Quorum không phải số hàng APPROVE

Một query ngữ cảnh duyệt cần xét đúng vòng, basis, quyết định có hiệu lực, danh tính độc lập và vai trò theo policy. Không đếm tất cả phiếu trong lịch sử.

Việc role của người duyệt thay đổi sau này có làm quyết định cũ còn được tính hay không phải do quy tắc hiệu lực quyết định xác định. Không mặc định mọi phiếu cũ bị xóa nghĩa, hoặc mọi phiếu đã ghi luôn hợp lệ mãi.

### 5.4. Thiếu dữ liệu không phải giá trị 0

Không đọc được ledger không có nghĩa đã hoàn 0. Không tải được reservation không có nghĩa toàn bộ tồn kho đều rảnh. Không đánh giá được role không có nghĩa không tồn tại điều kiện chặn.

Nếu thiếu một nguồn bắt buộc, trả lỗi dịch vụ hoặc kết quả chưa đầy đủ theo hợp đồng đã cho phép và quyền đọc đã xác lập. Không trả một con số chắc chắn gây hiểu sai.

## 6. Bộ lọc, tổng hợp và phân trang phải cùng giữ scope

### 6.1. Filter chỉ thu hẹp phạm vi đã được phép

`ownerId`, `departmentId` hoặc `scope=all` trong query là yêu cầu chọn dữ liệu, không phải bằng chứng người gọi được xem phạm vi đó.

Có thể hiểu:

```text
kết quả = phạm vi người gọi được phép xem
          giao với điều kiện lọc hợp lệ
```

Không bỏ predicate quyền khi client không truyền filter. Không dùng thiếu tenant như chế độ toàn hệ thống của một endpoint tenant.

### 6.2. Lọc trước khi đếm và tổng hợp

Nếu API lọc từng dòng sau khi đã tính `totalCount`, tổng tiền hoặc các nhóm thống kê, phần tổng hợp có thể làm lộ dữ liệu ngoài quyền.

Đặt điều kiện scope vào tập dữ liệu đầu vào của phép đếm/tổng hợp. Cũng cần xét metadata phân trang và bộ lọc gợi ý, không chỉ danh sách item cuối cùng.

### 6.3. Ví dụ truy vấn hồ sơ riêng của membership

Với policy minh họa chỉ cho xem hồ sơ mình sở hữu:

```sql
SELECT id, state, version, created_at, amount, currency
FROM expense_request
WHERE tenant_id = :authorized_tenant_id
  AND owner_membership_id = :verified_membership_id
  AND (:validated_state IS NULL OR state = :validated_state)
ORDER BY created_at DESC, id DESC
LIMIT :validated_page_size;
```

Cú pháp phân trang cụ thể phụ thuộc hệ quản trị triển khai. Tenant và membership ở đây lấy từ ngữ cảnh đã xác minh, không phải một owner ID tự khai được tin trực tiếp.

Query đếm phải dùng cùng phạm vi. Nếu policy có chia sẻ hoặc quyền phòng ban, cần biểu diễn đầy đủ policy đó thay vì dùng ví dụ owner-only như giải pháp chung.

Các join tới dữ liệu tenant riêng phải giữ liên kết tenant/đối tượng tương ứng. Không join bảng con chỉ theo một ID cục bộ có thể trùng giữa các tenant.

### 6.4. Sort, cursor và giới hạn truy vấn

Allowlist trường sắp xếp, giới hạn page size, cửa sổ thời gian, độ sâu quan hệ và độ phức tạp cần thiết. Safe read vẫn có thể tiêu tốn tài nguyên đáng kể.

Cursor có thể giữ vị trí và điều kiện truy vấn, nhưng không tự cho quyền đọc trang tiếp theo. Kiểm tra scope hiện tại và các ràng buộc cursor theo hợp đồng, kể cả khi cursor có chữ ký.

Nếu quyền/snapshot đổi khiến phân trang không còn đáp ứng cam kết, có thể yêu cầu bắt đầu lại hoặc xử lý theo semantics đã định. Không dùng cursor cũ để khôi phục phạm vi quyền đã mất.

## 7. Độ mới và tính nhất quán của kết quả đọc

### 7.1. GeneratedAt khác dataAsOf

Response vừa được tạo không chứng minh mọi dữ liệu bên trong vừa được cập nhật. Một projection có thể đang chậm hơn nguồn ghi.

Phân biệt thời điểm dựng response, thời điểm/phiên bản dữ liệu đã được nguồn xác nhận và vị trí projection nếu được dùng. Chỉ công bố watermark hoặc version khi hệ thống thực sự hiểu nó bảo đảm điều gì.

### 7.2. Transaction đọc không tự là snapshot toàn hệ thống

Một transaction có thể đọc hai bảng ở những trạng thái không phù hợp nhau tùy isolation và cách truy vấn. Cần hợp đồng snapshot hoặc cơ chế nhất quán phù hợp cho câu hỏi.

Với nhiều service, timestamp giống nhau không tạo một snapshot nguyên tử xuyên hệ thống. Có thể cần giới hạn độ mới, version từng thành phần hoặc một read model được thiết kế cho ý nghĩa cụ thể.

### 7.3. Projection trễ không được làm command tin capacity cũ

Read model có thể chấp nhận độ trễ cho dashboard. Command hoàn tiền vẫn phải kiểm tra ledger/reservation có thẩm quyền khi tạo nghĩa vụ mới.

Không dùng một query nhanh nhưng trễ làm điều kiện duy nhất để duyệt, chi trả hoặc cấp quyền. Nếu một màn hình cần thông tin gần hiện hành hơn, chọn đường đọc đáp ứng yêu cầu đó và thể hiện trạng thái chờ khi chưa có căn cứ.

### 7.4. Read-your-writes và response đến ngược thứ tự

Sau khi command commit, request đọc qua replica có thể chưa thấy thay đổi. Client không nên tự suy command thất bại rồi tạo lệnh mới.

Có thể dùng nguồn đọc, consistency bookmark hoặc cơ chế chờ có giới hạn phù hợp kiến trúc để đáp ứng cam kết. Client cũng cần tránh để response version cũ đến muộn ghi đè kết quả mới hơn trong ngữ cảnh phù hợp.

Những cơ chế này hỗ trợ trải nghiệm; server vẫn phải giữ invariants khi command tiếp theo được gửi.

## 8. Minh họa Java cho refund preview không tạo reservation

Ví dụ chọn mô hình order và refund ledger có thể đọc trong một snapshot cục bộ phù hợp. Các dependency là hợp đồng ứng dụng, không phải API thư viện có sẵn.

```java
RefundPreview getRefundPreview(
        UUID tenantId,
        UUID orderId,
        RefundPreviewQuery query) {

    ActorContext actor = identity.requireTenantActor(tenantId);
    validateQueryShape(query);

    return transactions.readSnapshot(() -> {
        OrderSnapshot order = orders
                .findByTenantAndId(actor.tenantId(), orderId)
                .orElseThrow(NotFound::new);

        refundReadPolicy.requireCanViewPreview(actor, order);

        RefundLedgerSnapshot ledger = refunds.readForPreview(
                actor.tenantId(), order.id());

        RefundCapacity capacity = refundRules.calculateCapacity(
                order, ledger);

        RequestedRefund requested = refundRules.validatePreviewIntent(
                query.requestedAmount(), order.currency());

        EligibilityAtSnapshot eligibility = refundEligibility.evaluate(
                actor, order, ledger, capacity, requested, clock.instant());

        return new RefundPreview(
                order.id(), order.version(), ledger.version(),
                capacity.amount(), requested.amount(), order.currency(),
                eligibility, ledger.confirmedDataAsOf(), false);
    });
}
```

Các hợp đồng cần được triển khai đúng:

- `readSnapshot` thực sự cung cấp tính nhất quán cục bộ cần thiết theo cơ sở dữ liệu/isolation đã chọn; tên hàm không tự tạo bảo đảm đó.
- `requireCanViewPreview` kiểm tra quyền đọc và giới hạn field trước khi trả dữ liệu nhạy cảm.
- Ledger bao gồm đúng tiền đã thu, refund hoàn tất và reservation còn hiệu lực theo mô hình; không chỉ đọc tổng các dòng thành công.
- Số tiền client yêu cầu là đầu vào để đánh giá, không thay capacity hay tạo quyền hoàn.
- `refundEligibility` có thể trả trạng thái chưa đánh giá được nếu phần đánh giá action là tùy chọn theo hợp đồng; không được dùng cách này để bỏ quyền đọc bắt buộc.
- Không có insert refund, reservation, outbox chi trả hoặc chuyển trạng thái nghiệp vụ trong query này.
- Thời điểm/phiên bản trả về có nguồn và ý nghĩa rõ. Nếu dữ liệu thiếu bắt buộc, không tạo snapshot giả với số tiền 0.

### 8.1. Command phải kiểm tra lại trong ranh giới ghi

Khi client yêu cầu hoàn 100.000 sau preview, command cần authentication/authorization, order/currency đúng, capacity hiện hành và cơ chế giữ/tiêu thụ capacity nguyên tử.

Ví dụ sau preview 150.000, một refund khác giữ thêm 100.000. Command mới không được hoàn 100.000 chỉ vì client gửi lại preview. Nó cần xử lý capacity mới theo hợp đồng, không tự giảm số tiền yêu cầu hoặc bỏ qua xung đột.

Có thể dùng các expected version như điều kiện xác nhận căn cứ, nhưng version không tạo quyền. Việc so version cũng phải bao phủ ledger/reservation có thể đổi mà order version không đổi.

### 8.2. Muốn cam kết thì dùng cơ chế cam kết rõ ràng

Nếu sản phẩm muốn giữ một capacity hoặc báo giá cho khách, tạo reservation/quote có phạm vi và lifetime phù hợp. Command sau đó kiểm tra căn cứ đó và quy tắc tiêu thụ.

Chỉ thêm `previewId` hoặc chữ ký vào response không tự biến preview thành reservation. Cần định nghĩa phía server điều gì đã được giữ, cho ai và việc dùng đồng thời được bảo vệ ra sao.

## 9. Available actions, workflow context và query không ràng buộc

### 9.1. Available actions hỗ trợ UI, không thay policy thực thi

Một query có thể trả `submit`, `withdraw` hoặc `approve` dựa trên trạng thái và quyền tại snapshot. Client dùng nó để dựng giao diện dễ hiểu hơn.

Command vẫn đánh giá lại action với căn cứ được bảo vệ. Không nhận `availableActions` hoặc `canApprove` từ client như kết quả authorization có thẩm quyền.

Người dùng gọi trực tiếp API mà không qua query trước vẫn phải được kiểm tra đủ. Query không phải bước cấp phép ngầm bắt buộc mà server không xác minh được.

### 9.2. Lý do chưa đủ điều kiện cũng là dữ liệu cần bảo vệ

Có thể cho người được phép biết hồ sơ thiếu chứng từ hoặc cần xác nhận lại. Không mặc định được trả danh tính mọi người duyệt, hạn mức cá nhân hoặc rule nội bộ cho mọi người xem hồ sơ.

Thiết kế mã lý do và chi tiết theo đối tượng nhận. Không dùng việc giải thích eligibility để mở một API dò quyền của người khác.

### 9.3. Business query không phải lối tắt qua workflow

Không đánh dấu bước đã hoàn tất vì client đã gọi preview hoặc đã tải trang điều kiện. Một query có thể tính bước tiếp theo nhưng không tự ghi rằng người dùng đã chấp nhận.

Nếu cần một lời xác nhận, dùng command rõ với actor, basis, thời điểm và guards. “Đã xem” không tự đồng nghĩa “đã duyệt”.

### 9.4. Chia sẻ code domain nhưng giữ khác biệt hợp đồng

Các hàm tính capacity, kiểm tra căn cứ hoặc dựng breakdown có thể dùng chung giữa preview và command để giảm lệch rule. Command bổ sung kiểm soát đồng thời và ghi nhận tác động.

Không sao chép một công thức khác vào frontend rồi coi nó là nguồn quyết định. Cũng không coi phản hồi của query cũ là cách tái sử dụng code domain đáng tin ở lần ghi sau.

## 10. Cache, export, lỗi và audit

### 10.1. Cache theo đúng quyền và nguồn dữ liệu

Một response có thể phụ thuộc tenant, actor, scope dữ liệu, filter, locale/currency và phiên bản nguồn/policy liên quan. Key chỉ có resource ID hoặc URL chưa chắc đủ.

Không trả response cache của A cho B. Kiểm tra quyền nhận dữ liệu theo hợp đồng trước khi dùng bản sao có thể không còn phù hợp sau thu hồi hoặc đổi owner.

Nếu query có ETag/conditional response, quyền đọc vẫn phải được kiểm tra trước khi trả dữ liệu hoặc `304`. ETag không phải credential.

### 10.2. Export là nhiều ranh giới quyền

Một export job có thể được tạo bằng command, sau đó query trạng thái và tải artifact. Cần policy cho từng bước, không cho mọi người biết job ID được tải kết quả.

Nếu quyền đổi giữa lúc tạo và tải, xử lý theo hợp đồng rõ. Artifact cũ không tự mang quyền chia sẻ rộng hơn dữ liệu nguồn.

### 10.3. Không biến lỗi thành con số có vẻ chắc chắn

Lỗi ledger, projection chưa bắt kịp hoặc không có dữ liệu bắt buộc cần outcome phù hợp. Không trả `maximumRefundable = 0` như dữ kiện đầy đủ chỉ để tránh lỗi API.

Phân biệt không có dòng phù hợp thật với không thể đọc nguồn. Một danh sách rỗng có thể là kết quả hợp lệ; nó không phải fallback đúng cho mọi lỗi dependency.

### 10.4. Quan sát truy vấn mà không đổi nghiệp vụ

Có thể ghi audit truy cập dữ liệu nhạy cảm, thời gian xử lý, nguồn dữ liệu và độ trễ projection theo chính sách. Không log token, secret hoặc nguyên response riêng tư chỉ để debug.

Một access log không thay được decision record. Nếu đọc dữ liệu phải tạo một xác nhận nghiệp vụ có hệ quả, đó là hành động riêng cần quyền và ý định rõ.

## 11. Kiểm thử business query endpoint

| Tình huống | Kỳ vọng |
|---|---|
| Người dùng xem query của tenant/owner khác | Không lộ dữ liệu hoặc metadata ngoài quyền |
| Có quyền xem nhưng không được command tương ứng | Query đúng phạm vi; không tự cấp quyền action |
| Filter xin owner/phòng ban ngoài phạm vi | Không mở rộng tập được phép |
| Danh sách đã lọc nhưng count/tổng vẫn toàn tenant | Test phát hiện rò rỉ qua aggregate/metadata |
| Join dữ liệu con hoặc membership tenant khác | Không trộn dữ liệu vào kết quả |
| Có refund pending/reservation | Capacity tính đúng, không bỏ sót hoặc trừ hai lần |
| Projection/ledger lỗi hoặc chưa đủ mới | Không trả số giả như dữ kiện chắc chắn |
| Preview hợp lệ rồi có command khác tiêu thụ capacity | Command sau vẫn kiểm tra nguyên tử, không tin preview cũ |
| Owner/role đổi sau response availableActions | Action không dùng kết quả query cũ để vượt quyền |
| Hai phiếu cùng người hoặc thuộc vòng/basis khác | Query quorum không chỉ đếm số hàng |
| Cursor hoặc ETag dùng sang account/tenant khác | Không bỏ authorization hoặc khôi phục scope cũ |
| Truy vấn trang lớn, range dài, expand sâu | Giới hạn tài nguyên và field được thực thi |
| GET preview/polling nhiều lần | Không tạo reservation, decision hoặc operation mới |
| Command commit rồi đọc qua nguồn trễ | Hành vi đúng cam kết, không báo sai rằng command chắc chắn chưa chạy |
| Query hợp lệ của actor đúng quyền | Trả kết quả có nghĩa, không chặn toàn bộ để tránh lỗi |

### 11.1. Oracle theo nghĩa nghiệp vụ

Tính expected từ dữ kiện và rule độc lập, không gọi cùng hàm đang được test để tạo expected capacity. Dùng trường hợp có pending, failed, released và completed để phát hiện tính thiếu/tính trùng.

Với tiền, kiểm tra currency/unit, breakdown và tổng theo công thức. Với scope, kiểm tra item, count, tổng hợp và field mở rộng cùng nhau.

### 11.2. Assertion về việc không có command ẩn

So business projection trước/sau query: state, basis, decision, reservation và operation không bị thay đổi ngoài hợp đồng. Log/cache phụ trợ có thể được ghi hợp lệ.

Quan sát cổng tác động bên ngoài khi cần. Một response GET đúng số tiền chưa chứng minh handler không âm thầm khởi tạo refund.

### 11.3. Snapshot, cache và race có điều khiển

Chèn thay đổi giữa các lần đọc liên quan để kiểm tra hợp đồng snapshot, không giả định mọi transaction mặc định đã nhất quán. Thử hai account dùng chung cache và quyền đổi giữa các trang.

Với cơ sở dữ liệu, isolation và query/filter thực tế, integration test có ý nghĩa hơn chỉ unit test một presenter. Với HTTP/DTO/authentication, thử qua ranh giới ứng dụng đang dùng.

## 12. Tự rà soát hợp đồng query nghiệp vụ

Trước khi công bố endpoint, hãy trả lời:

1. Câu hỏi domain chính xác là gì, và dữ kiện nào tạo nên câu trả lời?
2. Kết quả là quan sát/ước tính hay có cam kết giữ điều kiện nào?
3. Quyền đọc áp dụng theo tenant, đối tượng và field ra sao?
4. Bộ lọc, phân trang, count, aggregate và join có cùng scope không?
5. Công thức có bao gồm pending/reservation và tránh đếm trùng không?
6. Snapshot, dataAsOf, projection lag và version thực sự bảo đảm điều gì?
7. Khi một nguồn bắt buộc lỗi, API có tránh trả dữ liệu giả hoặc mở quyền không?
8. Available actions/preview có thể bị hiểu nhầm thành authorization cho command sau không?
9. Cache, ETag, cursor và artifact export có giữ đúng quyền nhận dữ liệu không?
10. Test có chứng minh cả ý nghĩa kết quả và việc không có tác động nghiệp vụ ẩn không?

Business query tốt trả lời đúng câu hỏi trong đúng phạm vi và nêu rõ giới hạn của căn cứ đọc. Kết quả đó giúp người dùng ra quyết định, còn command vẫn phải xác lập quyền, điều kiện hiện hành và tính nhất quán trước khi tạo tác động.
