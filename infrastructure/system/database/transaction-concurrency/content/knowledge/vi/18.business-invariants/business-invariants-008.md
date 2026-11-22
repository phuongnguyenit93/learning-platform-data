# Trạng thái đơn hàng và chuyển trạng thái nguyên tử có điều kiện

Một đơn hàng không chỉ là tập hợp các cột có thể cập nhật tùy ý. Nó đi qua một quy trình có thứ tự: được tạo, chờ thanh toán, đã thanh toán, đang xử lý, đã gửi và cuối cùng được giao hoặc bị hủy. Mỗi trạng thái cho phép một số hành động nhất định; những hành động khác phải bị từ chối.

Khi nhiều request hoặc worker cùng xử lý một đơn hàng, việc đọc trạng thái rồi cập nhật ở hai câu lệnh riêng có thể tạo race condition. Hai bên có thể cùng đọc `PENDING`, cùng tin rằng mình được phép xử lý, rồi thực hiện hai chuyển trạng thái không tương thích. Cách bảo vệ quan trọng là **đưa trạng thái nguồn và các điều kiện nghiệp vụ vào chính câu lệnh cập nhật**, để database kiểm tra điều kiện và thay đổi trạng thái như một thao tác nguyên tử.

Ví dụ, chỉ một worker được phép nhận đơn hàng đang chờ xử lý:

```sql
UPDATE orders
SET status = 'PROCESSING',
    processing_started_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PAID';
```

Nếu câu lệnh cập nhật một hàng, worker đã giành quyền chuyển đơn từ `PAID` sang `PROCESSING`. Nếu cập nhật không hàng nào, đơn không tồn tại hoặc không còn ở trạng thái `PAID`; worker không được tiếp tục xử lý như thể đã nhận đơn.

## 1. Trạng thái đơn hàng là một máy trạng thái

Một **máy trạng thái** (*state machine*) mô tả các trạng thái hợp lệ và những chuyển đổi được phép giữa chúng. Đối với đơn hàng, trạng thái phản ánh tiến trình nghiệp vụ và giúp hệ thống xác định hành động nào có thể xảy ra tiếp theo.

Ví dụ một quy trình đơn giản:

```text
CREATED -> PENDING_PAYMENT -> PAID -> PROCESSING -> SHIPPED -> DELIVERED
   |              |
   | hủy          | hủy hoặc hết hạn
   v              v
              CANCELLED
```

Tùy chính sách, đơn `PAID` hoặc `PROCESSING` có thể được hủy theo một quy trình riêng; đơn `SHIPPED` có thể cần hoàn hàng thay vì chuyển ngược về `PAID`. Sơ đồ chỉ minh họa một tập chuyển đổi. Điều quan trọng là các chuyển đổi phải được xác định rõ theo nghiệp vụ.

Một bảng chuyển trạng thái có thể giúp diễn đạt quy tắc:

| Trạng thái hiện tại | Trạng thái đích | Điều kiện hoặc sự kiện |
|---|---|---|
| `CREATED` | `PENDING_PAYMENT` | Đơn đã được xác nhận và cần thanh toán. |
| `CREATED` | `CANCELLED` | Khách hủy trước khi thanh toán. |
| `PENDING_PAYMENT` | `PAID` | Thanh toán được xác minh thành công. |
| `PENDING_PAYMENT` | `CANCELLED` | Hủy hoặc hết hạn thanh toán theo chính sách. |
| `PAID` | `PROCESSING` | Worker nhận đơn để chuẩn bị hàng. |
| `PROCESSING` | `SHIPPED` | Đơn đã được bàn giao cho vận chuyển. |
| `SHIPPED` | `DELIVERED` | Có xác nhận giao hàng hợp lệ. |

Các trạng thái cuối như `CANCELLED` và `DELIVERED` thường không cho phép chuyển đổi tùy ý. Nếu có hoàn tiền, hoàn hàng hoặc mở lại đơn, nên biểu diễn đó là quy trình nghiệp vụ riêng với trạng thái và lịch sử rõ ràng.

### Vì sao không nên sửa status tùy ý?

Nếu mọi API đều có thể chạy `UPDATE orders SET status = :status`, bất kỳ caller nào cũng có thể bỏ qua bước nghiệp vụ. Một đơn có thể chuyển thẳng từ `CREATED` sang `SHIPPED`, hoặc từ `CANCELLED` sang `DELIVERED`, dù các điều kiện trung gian chưa từng được thỏa mãn.

Ứng dụng nên cung cấp các hành động có tên theo nghiệp vụ như `confirmPayment`, `startProcessing`, `shipOrder`, `cancelOrder` thay vì cho caller gửi một giá trị status tùy ý. Database vẫn phải kiểm tra trạng thái nguồn trong câu lệnh cập nhật để xử lý cạnh tranh.

## 2. Race condition khi đọc trạng thái rồi mới cập nhật

Giả sử đơn hàng `#5001` đang ở trạng thái `PAID`. Hai worker cùng muốn nhận đơn để xử lý.

Một cách triển khai dễ mắc lỗi:

```text
Worker A: SELECT status -> PAID
Worker B: SELECT status -> PAID

Worker A: kiểm tra PAID, quyết định xử lý
Worker B: kiểm tra PAID, quyết định xử lý

Worker A: UPDATE status = PROCESSING
Worker B: UPDATE status = PROCESSING

Worker A: bắt đầu đóng gói
Worker B: cũng bắt đầu đóng gói
```

Hai worker cùng dựa trên một trạng thái cũ. Nếu câu `UPDATE` không có điều kiện trạng thái nguồn, cả hai đều có thể cập nhật thành công và thực hiện công việc trùng lặp.

Vấn đề nằm ở khoảng thời gian giữa kiểm tra và sử dụng dữ liệu (*time-of-check to time-of-use*, TOCTOU). Trạng thái có thể thay đổi sau câu `SELECT` và trước câu `UPDATE`.

### Chuyển trạng thái có điều kiện

Đưa điều kiện trạng thái nguồn vào `WHERE`:

```sql
UPDATE orders
SET status = 'PROCESSING',
    processing_started_at = CURRENT_TIMESTAMP
WHERE id = 5001
  AND status = 'PAID';
```

Database kiểm tra điều kiện và cập nhật hàng trong cùng một statement. Nếu hai worker cùng chạy, một statement có thể cập nhật hàng trước. Khi statement còn lại được xử lý, trạng thái không còn là `PAID`, nên điều kiện không khớp và không cập nhật hàng.

Kết quả:

| Worker | Số hàng cập nhật | Kết quả |
|---|---:|---|
| A | `1` | Được quyền nhận đơn theo chuyển đổi `PAID → PROCESSING`. |
| B | `0` | Không được nhận đơn bằng trạng thái cũ; phải dừng hoặc đọc trạng thái hiện tại để xử lý theo chính sách. |

Đây là phép **compare-and-set** (*so sánh rồi đặt*) ở cấp hàng: chỉ thay đổi nếu giá trị hiện tại vẫn bằng giá trị mà hành động yêu cầu.

## 3. Thiết kế câu UPDATE cho chuyển trạng thái nguyên tử

Một câu lệnh chuyển trạng thái nên chứa tối thiểu:

1. Khóa định danh của đơn hàng.
2. Trạng thái nguồn được phép chuyển.
3. Các điều kiện nghiệp vụ có thể kiểm tra trực tiếp trong câu lệnh.
4. Trạng thái đích và các dữ liệu đi kèm cần được ghi cùng lúc.

Ví dụ chuyển đơn từ `PENDING_PAYMENT` sang `PAID` sau khi server xác minh thanh toán:

```sql
UPDATE orders
SET status = 'PAID',
    paid_at = CURRENT_TIMESTAMP,
    payment_reference = :paymentReference
WHERE id = :orderId
  AND status = 'PENDING_PAYMENT';
```

Chỉ request có trạng thái nguồn phù hợp mới được chuyển. Thời điểm thanh toán và mã tham chiếu được ghi cùng statement với status để tránh một hàng ở trạng thái `PAID` nhưng thiếu thông tin thanh toán do hai bước ghi tách rời.

Nếu cần kiểm tra thêm điều kiện, có thể đưa chúng vào `WHERE`:

```sql
UPDATE orders
SET status = 'PROCESSING',
    processing_started_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PAID'
  AND payment_reference IS NOT NULL
  AND total_amount > 0;
```

Đây chỉ là ví dụ về điều kiện trên cùng hàng. Các quy tắc cần truy vấn bảng khác hoặc tính tổng nhiều hàng cần cơ chế concurrency phù hợp riêng; không phải mọi điều kiện nghiệp vụ đều có thể an toàn đưa vào một `WHERE` đơn giản.

### Đọc số hàng bị ảnh hưởng

Với cập nhật một đơn hàng theo khóa chính:

- `1` hàng: điều kiện khớp và statement đã chuyển trạng thái.
- `0` hàng: không có đơn nào thỏa toàn bộ điều kiện. Có thể đơn không tồn tại, trạng thái đã thay đổi hoặc một điều kiện nghiệp vụ không còn đúng.

Không nên coi `0` là thành công. Cũng không nên mặc định nó luôn có nghĩa “đã có worker khác nhận đơn”; có thể có nguyên nhân khác.

Nếu API cần phân biệt lỗi cụ thể, có thể thực hiện một truy vấn đọc trạng thái sau khi cập nhật không thành công, trong transaction mới hoặc theo cách phù hợp với isolation level. Kết quả đọc sau đó chỉ dùng để giải thích phản hồi; quyết định cập nhật vẫn phải dựa trên câu lệnh có điều kiện.

Ví dụ xử lý ở tầng service:

```java
int changed = orderRepository.startProcessing(orderId);

if (changed == 1) {
    return StartResult.started();
}

return StartResult.notTransitioned();
```

Repository có thể thực hiện native update hoặc câu lệnh cập nhật tương đương. Nếu dùng ORM, cần chú ý bulk update có thể bỏ qua persistence context hoặc versioning tự động; hãy đồng bộ entity trong bộ nhớ và transaction theo semantics của ORM.

## 4. Bảo vệ các điều kiện chuyển trạng thái quan trọng

Trạng thái nguồn chỉ là một phần của bất biến. Một chuyển đổi còn có thể cần kiểm tra số tiền, quyền, thời hạn, tồn kho hoặc quan hệ với dữ liệu khác.

### Hủy đơn khi chưa thanh toán

Nếu khách chỉ được hủy đơn đang chờ thanh toán:

```sql
UPDATE orders
SET status = 'CANCELLED',
    cancelled_at = CURRENT_TIMESTAMP,
    cancellation_reason = :reason
WHERE id = :orderId
  AND customer_id = :customerId
  AND status IN ('CREATED', 'PENDING_PAYMENT');
```

Điều kiện `customer_id` giúp giới hạn hành động vào đơn của khách hàng đang gọi API; kiểm tra quyền ở tầng ứng dụng vẫn cần thiết. Điều kiện status bảo đảm một request hủy không ghi đè đơn đã thanh toán hoặc đang giao.

Nếu thanh toán thành công và yêu cầu hủy xảy ra đồng thời, hai thao tác cạnh tranh trên cùng hàng. Chỉ một chuyển đổi từ trạng thái nguồn phù hợp có thể thắng theo thứ tự database thực thi. Nếu thanh toán thắng trước, câu hủy không còn khớp; nếu hủy thắng trước, câu đánh dấu `PAID` không còn khớp. Quy trình xử lý tiền thực tế còn cần đối soát với cổng thanh toán, nhưng trạng thái trong database không bị hai câu cập nhật vô điều kiện ghi đè lẫn nhau.

### Chỉ giao hàng khi đã được xử lý

```sql
UPDATE orders
SET status = 'SHIPPED',
    shipped_at = CURRENT_TIMESTAMP,
    tracking_number = :trackingNumber
WHERE id = :orderId
  AND status = 'PROCESSING';
```

Worker vận chuyển không thể chuyển một đơn còn `PENDING_PAYMENT` sang `SHIPPED` bằng câu lệnh này. `tracking_number` và `shipped_at` được ghi cùng trạng thái đích.

### Kiểm tra số lượng trước khi nhận đơn

Nếu việc nhận đơn còn phụ thuộc một hàng tồn kho hoặc hàng phân công, một điều kiện trên `orders` không đủ để bảo vệ dữ liệu ở bảng khác. Cần phối hợp các thay đổi trong cùng transaction, sử dụng cập nhật có điều kiện hoặc khóa thích hợp cho từng tài nguyên.

Ví dụ, transaction có thể:

1. Chuyển đơn `PAID → PROCESSING` bằng câu lệnh có điều kiện.
2. Trừ tồn kho bằng `UPDATE inventory ... WHERE available >= :quantity`.
3. Nếu một bước không thành công, rollback toàn bộ transaction.
4. Chỉ commit khi cả chuyển trạng thái và trừ kho đều thành công.

Không được commit trạng thái `PROCESSING` nếu bước trừ kho thất bại mà nghiệp vụ yêu cầu hai thay đổi cùng thành công.

## 5. Lưu lịch sử chuyển trạng thái cùng transaction

Chỉ lưu status hiện tại giúp truy vấn nhanh, nhưng không cho biết ai đã chuyển, khi nào và vì sao. Một bảng lịch sử (*order status history*) có thể ghi lại từng chuyển đổi:

```sql
CREATE TABLE order_status_history (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    changed_at TIMESTAMP NOT NULL,
    changed_by VARCHAR(100),
    reason VARCHAR(500),
    CONSTRAINT fk_order_history_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
);
```

Khi chuyển trạng thái, ghi hàng hiện tại và hàng lịch sử trong cùng transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'PROCESSING',
    processing_started_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PAID';

-- Chỉ INSERT history nếu UPDATE ở trên cập nhật đúng một hàng.
INSERT INTO order_status_history (
    id, order_id, from_status, to_status,
    changed_at, changed_by, reason
)
VALUES (
    :historyId, :orderId, 'PAID', 'PROCESSING',
    CURRENT_TIMESTAMP, :actor, 'Worker nhận đơn'
);

COMMIT;
```

Ứng dụng phải kiểm tra row count trước khi insert history. Nếu update bằng `0`, không được ghi một sự kiện lịch sử giả như thể chuyển đổi đã thành công. Nếu insert history thất bại, transaction cần rollback để status không đổi một mình.

Có thể dùng `UPDATE ... RETURNING` ở PostgreSQL hoặc `OUTPUT` ở SQL Server để lấy trạng thái cũ/mới hoặc xác định hàng đã cập nhật, nhưng cú pháp khác nhau theo engine. Một lựa chọn portable hơn là kiểm tra row count trong cùng transaction rồi insert history.

### Lịch sử là dữ liệu nghiệp vụ

Không nên cập nhật hoặc xóa lịch sử tùy tiện. Nếu cần sửa một sai sót, cân nhắc thêm sự kiện điều chỉnh có người thực hiện, lý do và thời điểm. Lịch sử bất biến giúp điều tra tranh chấp, đối soát và kiểm toán.

## 6. Chuyển trạng thái có điều kiện kết hợp version

Kiểm tra status nguồn thường đủ để ngăn hai worker cùng chuyển từ `PAID` sang `PROCESSING`. Nhưng nếu nhiều trường khác cũng ảnh hưởng quyết định, có thể thêm cột `version` để phát hiện bất kỳ cập nhật nào trên hàng kể từ lúc client đọc.

```sql
UPDATE orders
SET status = 'PROCESSING',
    version = version + 1,
    processing_started_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PAID'
  AND version = :expectedVersion;
```

Ở đây có hai điều kiện:

- `status = 'PAID'` bảo đảm chuyển đổi hợp lệ từ trạng thái nghiệp vụ hiện tại.
- `version = :expectedVersion` bảo đảm client đang thao tác trên revision mà nó đã đọc.

Không phải lúc nào cũng cần cả hai. Một worker chỉ cần giành quyền chuyển trạng thái hiện tại có thể dùng status làm điều kiện compare-and-set. Một giao diện chỉnh sửa nhiều trường có thể cần version để phát hiện bản đọc cũ ngay cả khi status chưa thay đổi.

Nếu câu lệnh cập nhật `0` hàng, ứng dụng cần phân biệt trạng thái đã đổi với version đã đổi hoặc hàng không tồn tại nếu nghiệp vụ yêu cầu. Việc đọc trạng thái sau đó chỉ giúp giải thích kết quả; không thay thế điều kiện nguyên tử.

## 7. Ràng buộc miền trạng thái ở database

Ngoài câu lệnh chuyển đổi, schema nên ngăn giá trị status không hợp lệ. Ví dụ:

```sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_orders_status
        CHECK (status IN (
            'CREATED',
            'PENDING_PAYMENT',
            'PAID',
            'PROCESSING',
            'SHIPPED',
            'DELIVERED',
            'CANCELLED'
        ))
);
```

`CHECK` bảo đảm status thuộc tập giá trị được phép. Nó không tự bảo đảm chuyển đổi hợp lệ giữa hai trạng thái. Ví dụ, cả `CREATED` và `SHIPPED` đều là giá trị hợp lệ riêng lẻ, nhưng `CREATED → SHIPPED` vẫn có thể sai quy trình. Quy tắc chuyển đổi cần được bảo vệ bằng câu lệnh có điều kiện, stored procedure, trigger được thiết kế đúng hoặc một cơ chế transaction tương đương.

Một cách tổ chức khác là bảng trạng thái và foreign key:

```sql
CREATE TABLE order_statuses (
    code VARCHAR(30) PRIMARY KEY,
    description VARCHAR(200) NOT NULL
);

ALTER TABLE orders
ADD CONSTRAINT fk_orders_status
FOREIGN KEY (status) REFERENCES order_statuses(code);
```

Foreign key giúp quản lý tập status có thể cấu hình, nhưng vẫn chỉ bảo đảm status đích tồn tại. Nó không kiểm tra trạng thái nguồn hoặc cạnh chuyển đổi.

## 8. Khi nào cần bảng định nghĩa cạnh chuyển trạng thái?

Với quy trình phức tạp hoặc có thể cấu hình, có thể lưu các cạnh hợp lệ trong bảng:

```sql
CREATE TABLE allowed_order_transitions (
    from_status VARCHAR(30) NOT NULL,
    to_status VARCHAR(30) NOT NULL,
    PRIMARY KEY (from_status, to_status)
);
```

Ứng dụng có thể kiểm tra cặp trạng thái có tồn tại trong bảng này. Nhưng nếu chỉ chạy `SELECT` rồi `UPDATE` vô điều kiện, race condition vẫn tồn tại. Có thể dùng câu lệnh có điều kiện tham chiếu cạnh chuyển đổi, stored procedure hoặc khóa thích hợp để việc kiểm tra và cập nhật có cùng bảo đảm nguyên tử.

Không cần tạo bảng cạnh cho một state machine nhỏ và cố định. Enum trong code, bảng quy tắc hoặc stored procedure là lựa chọn thiết kế; điều quan trọng là một nguồn quy tắc rõ ràng và mọi đường chuyển đổi đều thực thi nó.

## 9. Idempotency khi nhận cùng một sự kiện nhiều lần

Trong hệ thống phân tán, cùng một webhook hoặc message có thể được gửi lại. Ví dụ cổng thanh toán gửi nhiều lần sự kiện `payment_succeeded` cho cùng payment. Chuyển trạng thái có điều kiện giúp không chuyển `PAID` lần thứ hai từ `PENDING_PAYMENT`, nhưng ứng dụng còn cần xử lý sự kiện trùng và ghi nhận kết quả.

Có thể lưu mã sự kiện đã xử lý:

```sql
CREATE TABLE processed_events (
    provider_event_id VARCHAR(120) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Trong một transaction:

1. Insert `provider_event_id` vào bảng `processed_events`.
2. Nếu insert thành công, thực hiện chuyển trạng thái có điều kiện và các cập nhật liên quan.
3. Nếu event ID đã tồn tại, xem đây là sự kiện đã được nhận trước đó và trả kết quả idempotent.
4. Commit việc đánh dấu event cùng với thay đổi nghiệp vụ.

Nếu việc chuyển trạng thái không thành công do trạng thái nguồn không hợp lệ, cần quyết định có giữ bản ghi event để tránh nhận lại hay rollback toàn bộ để xử lý sau. Quyết định phụ thuộc loại sự kiện, thứ tự sự kiện và khả năng đối soát. Không được đánh dấu sự kiện hoàn tất rồi bỏ qua thay đổi nghiệp vụ mà không có trạng thái xử lý rõ ràng.

Idempotency key hoặc event ID giúp phân biệt request mới với lần gửi lại cùng một ý định. Nó không thay thế điều kiện status; hai cơ chế bảo vệ hai vấn đề khác nhau.

## 10. Phát sự kiện sau khi chuyển trạng thái

Khi đơn chuyển sang `SHIPPED`, hệ thống có thể cần gửi thông báo cho khách, phát message cho dịch vụ vận chuyển hoặc cập nhật hệ thống phân tích. Không nên giả định transaction database có thể rollback một HTTP call hoặc message đã gửi.

Một quy trình dễ gặp lỗi:

```text
UPDATE order status = SHIPPED
Gửi message OrderShipped
COMMIT
```

Nếu message gửi thành công nhưng commit thất bại, hệ thống bên ngoài đã nhận một sự kiện cho thay đổi không tồn tại. Nếu commit thành công nhưng message gửi thất bại, đơn đã `SHIPPED` nhưng consumer không biết.

Có thể dùng **transactional outbox**: ghi hàng outbox cùng transaction với chuyển trạng thái:

```sql
BEGIN;

UPDATE orders
SET status = 'SHIPPED',
    shipped_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PROCESSING';

-- Chỉ ghi outbox khi UPDATE thành công.
INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    :eventId, :orderId, 'OrderShipped', :payload, CURRENT_TIMESTAMP
);

COMMIT;
```

Worker riêng đọc outbox và phát message sau commit. Nếu worker phát lại do crash sau khi gửi nhưng trước khi đánh dấu đã gửi, consumer cần idempotency hoặc deduplication theo `event_id`.

Điều này bảo đảm thay đổi trạng thái và ý định phát sự kiện được lưu cùng nhau. Nó không tạo một transaction phân tán nguyên tử giữa database và broker; delivery thường là at-least-once và cần xử lý trùng.

## 11. Chuyển trạng thái và cập nhật nhiều bảng

Một hành động như xác nhận đơn hàng có thể cập nhật nhiều đối tượng:

- `orders.status` chuyển sang `PAID`.
- `payments.status` chuyển sang `CAPTURED`.
- `inventory.available` giảm.
- `order_status_history` thêm sự kiện.
- `outbox_events` thêm thông điệp.

Nếu tất cả dữ liệu nằm trong cùng database và cần cùng thành công, hãy thực hiện chúng trong một transaction. Mỗi cập nhật quan trọng vẫn cần điều kiện phù hợp và row count phải được kiểm tra.

Ví dụ cấu trúc:

```text
BEGIN
  1. Claim payment/event theo ID và trạng thái mong đợi
  2. Chuyển order từ PENDING_PAYMENT sang PAID
  3. Cập nhật các hàng nghiệp vụ liên quan
  4. Ghi status history
  5. Ghi outbox event
  Nếu bất kỳ bước bắt buộc nào thất bại: ROLLBACK
COMMIT
```

Nếu một dịch vụ bên ngoài tham gia, transaction database không thể tự khóa hoặc rollback dữ liệu bên ngoài. Khi đó cần quy trình saga, outbox/inbox, idempotency và cơ chế bù trừ theo nghiệp vụ.

### Chú ý thứ tự khóa

Hai luồng chuyển trạng thái có thể khóa nhiều bảng. Nếu một luồng khóa `orders` rồi `inventory`, luồng khác khóa `inventory` rồi `orders`, deadlock có thể xảy ra. Xác định thứ tự truy cập bảng và hàng nhất quán cho các quy trình có thể tranh chấp; giữ transaction ngắn và xử lý deadlock bằng retry toàn bộ transaction khi phù hợp.

## 12. API nên phản hồi thế nào khi chuyển trạng thái không thành công?

Khi câu cập nhật có điều kiện ảnh hưởng `0` hàng, API cần phản hồi đúng ý nghĩa. Một số lựa chọn:

| Tình huống | Phản hồi có thể phù hợp |
|---|---|
| Đơn không tồn tại | `404 Not Found` |
| Caller không có quyền trên đơn | `403 Forbidden` hoặc `404` theo chính sách tránh lộ tài nguyên |
| Trạng thái hiện tại không cho phép hành động | `409 Conflict` |
| Dữ liệu request không hợp lệ | `400 Bad Request` hoặc `422 Unprocessable Content` |
| Version/ETag đã cũ | `409 Conflict` hoặc `412 Precondition Failed` khi dùng HTTP conditional request |
| Lỗi tạm thời database | Phản hồi lỗi tạm thời phù hợp, có thể cho phép retry theo hợp đồng API |

Không nên trả `200 OK` cho một thao tác chuyển trạng thái không thực sự xảy ra. Cũng không nên để client tự quyết định rằng một status bất kỳ là hợp lệ. Server phải kiểm tra quyền và chuyển đổi theo state machine.

Thông báo lỗi có thể nêu trạng thái hiện tại nếu caller được phép xem đơn. Nếu không, cần tránh tiết lộ thông tin của đơn thuộc người khác.

## 13. Kiểm thử chuyển trạng thái nguyên tử

Test đơn lẻ xác nhận `PAID → PROCESSING` thành công chưa đủ. Cần kiểm tra các cuộc đua giữa những hành động không tương thích.

### Hai worker cùng nhận một đơn

1. Chuẩn bị đơn ở `PAID`.
2. Dùng hai connection độc lập cùng gọi câu `UPDATE ... WHERE status = 'PAID'`.
3. Đồng bộ hai worker để chúng bắt đầu gần như cùng lúc.
4. Xác nhận tổng số hàng cập nhật bằng `1`.
5. Xác nhận chỉ một lịch sử `PAID → PROCESSING` và chỉ một công việc xử lý được tạo.

### Hủy và thanh toán đồng thời

Cho một transaction chuyển `PENDING_PAYMENT → CANCELLED`, transaction khác chuyển `PENDING_PAYMENT → PAID`. Chỉ một chuyển đổi từ cùng trạng thái nguồn được chấp nhận. Kiểm tra thêm quy trình đối soát nếu cổng thanh toán đã thu tiền nhưng transaction hủy thắng trong database.

### Sự kiện thanh toán trùng

Gửi cùng một provider event ID nhiều lần. Xác nhận chỉ có một lần xử lý nghiệp vụ, không tạo nhiều history/outbox event tương ứng với cùng ý định và kết quả trả về nhất quán.

### Rollback giữa các bước

Cho bước ghi history hoặc outbox thất bại sau khi câu update status đã chạy. Xác nhận transaction rollback khiến status trở lại trạng thái ban đầu và không để lại bản ghi history/outbox một phần.

### Trạng thái không hợp lệ

Thử chuyển `CREATED → SHIPPED`, `CANCELLED → PAID` hoặc một chuyển đổi không nằm trong bảng quy tắc. Xác nhận không có thay đổi và API trả lỗi nghiệp vụ phù hợp.

Để test cạnh tranh lặp lại được, dùng barrier/latch thay vì chỉ `sleep`. Kiểm tra cả trạng thái cuối, row count, lịch sử, outbox và tác dụng phụ được phát ra.

## 14. Những lỗi thiết kế thường gặp

- **Đọc status rồi cập nhật vô điều kiện:** tạo race giữa kiểm tra và ghi. Đặt status nguồn trong `WHERE`.
- **Coi `0` hàng cập nhật là thành công:** worker có thể tiếp tục làm việc dù không nhận được đơn. Phải kiểm tra row count.
- **Cho client gửi status đích tùy ý:** có thể bỏ qua state machine. Cung cấp hành động nghiệp vụ cụ thể và kiểm tra cạnh hợp lệ ở server.
- **Chỉ dùng `CHECK` để bảo vệ luồng chuyển đổi:** `CHECK` thường xác nhận giá trị status thuộc tập hợp, không bảo đảm cạnh chuyển từ trạng thái này sang trạng thái khác.
- **Ghi status và history ở hai transaction khác nhau:** có thể tạo trạng thái không có lịch sử hoặc lịch sử không tương ứng với trạng thái.
- **Phát message trước commit:** consumer có thể nhận sự kiện cho thay đổi bị rollback. Dùng outbox khi cần phối hợp bền vững.
- **Không xử lý sự kiện trùng:** webhook hoặc message redelivery có thể lặp hành động. Dùng event ID/idempotency và chuyển trạng thái có điều kiện.
- **Dùng một câu update cho một hàng nhưng bỏ qua bất biến nhiều hàng:** trạng thái hàng có thể đúng trong khi tồn kho, thanh toán hoặc giới hạn chung sai. Dùng transaction, constraint, khóa hoặc Serializable phù hợp.
- **Retry chỉ statement cuối sau deadlock:** dữ liệu đã đọc có thể cũ. Retry toàn bộ transaction bằng transaction mới.

## 15. Cách thiết kế một chuyển trạng thái

Khi thêm một hành động vào quy trình đơn hàng, hãy xác định:

1. Trạng thái nguồn nào được phép?
2. Trạng thái đích nào sẽ được ghi?
3. Ai có quyền thực hiện hành động này?
4. Điều kiện nghiệp vụ nào phải đúng tại thời điểm cập nhật?
5. Những bảng hoặc tài nguyên nào cần thay đổi cùng transaction?
6. Câu lệnh cập nhật có thể kiểm tra trạng thái nguồn và điều kiện trực tiếp trong `WHERE` không?
7. Ứng dụng diễn giải `row count = 0` như thế nào?
8. Lịch sử, idempotency record và outbox có cần ghi cùng transaction không?
9. Nếu có deadlock hoặc serialization failure, retry toàn bộ quy trình có an toàn không?
10. Những cặp hành động nào có thể chạy đồng thời và cần được kiểm thử?

Hãy giữ state machine ở một nơi dễ hiểu, nhưng thực thi điều kiện quan trọng ngay tại database. Với một hàng, conditional `UPDATE` thường là cách ngắn gọn để thực hiện compare-and-set. Với nhiều hàng hoặc dịch vụ, dùng transaction và cơ chế phối hợp rộng hơn; không giả định một điều kiện trên `orders` tự bảo vệ mọi tài nguyên liên quan.

## 16. Kết luận

Trạng thái đơn hàng biểu diễn tiến trình nghiệp vụ và các hành động được phép tiếp theo. Chuyển trạng thái phải tuân thủ state machine, có điều kiện nguồn rõ ràng và không được để hai request đồng thời cùng thực hiện một hành động chỉ vì chúng đã đọc cùng trạng thái cũ.

Đưa trạng thái nguồn và các điều kiện có thể kiểm tra trực tiếp vào câu `UPDATE` giúp database thực hiện so sánh và thay đổi như một thao tác nguyên tử. Kiểm tra số hàng bị ảnh hưởng để biết chuyển đổi có thành công hay không. Khi cần, kết hợp version, ghi lịch sử, idempotency và outbox trong cùng transaction. Với bất biến liên nhiều hàng hoặc dịch vụ, bổ sung constraint, khóa, Serializable hoặc saga phù hợp. Thiết kế như vậy giúp trạng thái đơn hàng, lịch sử và các tác dụng phụ liên quan phản ánh đúng một quy trình được kiểm soát khi nhiều giao dịch chạy đồng thời.
