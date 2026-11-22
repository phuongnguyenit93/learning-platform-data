# So sánh OFFSET với phân trang theo khóa trên dữ liệu tăng dần

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích cách `OFFSET` và keyset pagination chọn vị trí bắt đầu của một trang.
- Phân tích vì sao chi phí `OFFSET` thường tăng khi người dùng đi sâu vào tập dữ liệu lớn.
- Thiết kế thứ tự sắp xếp ổn định với khóa phụ duy nhất để tránh hàng bị trùng hoặc bỏ sót.
- Viết truy vấn keyset cho thứ tự tăng dần, giảm dần và khóa sắp xếp ghép.
- Thiết kế composite index khớp với filter và order của truy vấn phân trang.
- Đánh giá ảnh hưởng của INSERT, DELETE và UPDATE đồng thời đến tính nhất quán giữa các trang.
- Chọn chiến lược phù hợp cho API, màn hình có số trang, feed liên tục và dữ liệu tăng nhanh.
- Benchmark hai phương pháp bằng execution plan, logical reads, latency và tải đồng thời.

## 1. Bối cảnh: dữ liệu tăng dần làm trang sâu ngày càng đắt

Giả sử một hệ thống lưu hàng chục triệu đơn hàng và mỗi ngày tiếp tục nhận thêm dữ liệu. API cần hiển thị danh sách theo thời gian tạo mới nhất, mỗi trang 50 đơn. Ở trang đầu, cả `OFFSET` lẫn keyset pagination thường có thể trả kết quả nhanh. Khi người dùng đi đến trang thứ 10.000, hai cách bắt đầu có chi phí rất khác nhau.

OFFSET yêu cầu database bỏ qua một số lượng hàng đứng trước vị trí cần lấy rồi mới trả page. Với page size 50 và offset 499.950, engine thường vẫn phải đi qua lượng lớn entry trước khi trả 50 hàng cuối. Keyset pagination dùng giá trị khóa của hàng cuối trang trước làm mốc, sau đó tìm các hàng tiếp theo theo thứ tự index.

Trong module DATABASE_PERFORMANCE, đây là một bài toán access path: cách viết predicate, thứ tự sắp xếp, composite index, cardinality và dữ liệu tăng theo thời gian quyết định lượng công việc database phải làm. Phân trang cũng ảnh hưởng đến bytes truyền, thời gian giữ connection và latency phía Java.

## 2. OFFSET pagination hoạt động thế nào?

OFFSET pagination chọn một vị trí bằng số hàng cần bỏ qua và số hàng cần trả về. Cú pháp thường gặp:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 100;
```

Truy vấn này yêu cầu bỏ qua 100 hàng theo thứ tự đã chọn, rồi trả 50 hàng tiếp theo. Với PostgreSQL và MySQL, `LIMIT ... OFFSET ...` là cú pháp phổ biến. SQL Server dùng `ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`.

```sql
-- SQL Server
SELECT order_id, created_at, status, total_amount
FROM dbo.orders
WHERE tenant_id = @tenant_id
ORDER BY created_at DESC, order_id DESC
OFFSET 100 ROWS FETCH NEXT 50 ROWS ONLY;
```

OFFSET thường thuận tiện cho giao diện có số trang: người dùng nhập trang 1, 2, 3 hoặc nhảy đến trang 500. Nó cũng đơn giản khi cần tổng số trang và kết quả có thể thay đổi ít.

### Vì sao OFFSET sâu tốn kém?

Database vẫn cần xác định thứ tự và đi qua các hàng bị bỏ qua. Nếu truy vấn cần 50 hàng ở offset 500.000, lượng entry cần duyệt có thể xấp xỉ 500.050, dù chỉ 50 hàng được gửi cho ứng dụng. Tùy execution plan, index, filter và engine, chi phí có thể khác nhau; nhưng phần bỏ qua thường không miễn phí.

Với dữ liệu tăng liên tục, trang sâu thường chậm dần theo vị trí. Nếu filter không có index phù hợp, engine còn có thể scan/sort lượng dữ liệu lớn trước khi áp dụng OFFSET.

Không nên mô tả mọi OFFSET là luôn O(n) theo một công thức tuyệt đối, vì optimizer và access path khác nhau. Tuy nhiên, với truy vấn tuần tự qua một index, lượng entry phải đi qua thường tăng theo offset; đây là lý do thực tế khiến deep pagination suy giảm.

## 3. ORDER BY phải xác định một thứ tự duy nhất

Phân trang cần một thứ tự ổn định. Truy vấn chỉ sắp xếp theo `created_at` có thể không xác định thứ tự giữa các hàng có cùng timestamp.

Ví dụ:

```sql
ORDER BY created_at DESC
```

Nếu 20 đơn hàng có cùng `created_at`, database có thể trả chúng theo thứ tự khác nhau giữa hai lần chạy, nhất là khi plan hoặc dữ liệu thay đổi. Khi kết hợp với OFFSET, một hàng có thể xuất hiện ở hai trang hoặc không xuất hiện ở trang nào.

Hãy thêm một tie-breaker duy nhất, thường là primary key:

```sql
ORDER BY created_at DESC, order_id DESC
```

Ở đây `order_id` phân định thứ tự giữa các hàng cùng thời điểm. Với điều kiện `order_id` là duy nhất, cặp `(created_at, order_id)` xác định thứ tự toàn phần.

Nguyên tắc:

- Mọi truy vấn phân trang phải có `ORDER BY` rõ ràng.
- Thứ tự nên kết thúc bằng một cột hoặc tổ hợp cột duy nhất.
- Các trang phải dùng cùng biểu thức sắp xếp, collation và quy tắc NULL.
- Cursor phải chứa đủ mọi giá trị cần để tiếp tục sau hàng cuối.

## 4. Dữ liệu thay đổi giữa các lần lấy trang

OFFSET có thể bị dịch chuyển khi dữ liệu thay đổi giữa request trang trước và request trang sau.

Ví dụ ban đầu, danh sách giảm dần:

```text
Trang 1: 100, 99, 98, 97, 96
Trang 2:  95, 94, 93, 92, 91
```

Người dùng đã xem trang 1. Trước khi họ lấy trang 2, một hàng mới có khóa 101 được chèn vào đầu danh sách:

```text
Danh sách mới: 101, 100, 99, 98, 97, 96, 95, ...
```

Truy vấn trang 2 với `OFFSET 5` giờ trả 96, 95, 94, 93, 92. Hàng 96 bị lặp lại so với trang 1. Nếu có xóa hàng trước vị trí offset, một hàng có thể bị bỏ qua.

Ngay cả khi có ORDER BY duy nhất, OFFSET vẫn dựa trên vị trí đếm được tại thời điểm mỗi request. Thứ tự ổn định không cố định vị trí của các hàng khi tập dữ liệu thay đổi.

## 5. Keyset pagination là gì?

Keyset pagination, còn gọi là seek pagination hoặc cursor pagination, dùng giá trị khóa của hàng cuối trang hiện tại làm điều kiện tìm trang kế tiếp. Thay vì yêu cầu database bỏ qua N hàng, ứng dụng nói: 'lấy các hàng đứng sau mốc này theo thứ tự đã chọn'.

Giả sử trang hiện tại kết thúc ở:

```text
created_at = 2026-11-19 10:30:00
order_id  = 850120
```

Với thứ tự giảm dần `(created_at DESC, order_id DESC)`, trang tiếp theo chứa các hàng có cặp khóa nhỏ hơn cặp cursor:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Predicate này biểu diễn thứ tự từ điển của cặp khóa theo chiều giảm dần. Database có thể dùng index để seek đến vùng gần cursor rồi đọc tiếp các entry phù hợp.

### Trang đầu không cần cursor

Trang đầu có thể dùng cùng filter và ORDER BY nhưng bỏ predicate cursor:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Ứng dụng lấy cặp `(created_at, order_id)` của hàng cuối để tạo cursor cho request tiếp theo. Nên lấy thêm một hàng so với page size để biết còn trang sau hay không; ví dụ yêu cầu 51 hàng, trả 50 và dùng hàng thứ 51 để xác định `hasNext`.

## 6. Predicate cho thứ tự tăng dần và giảm dần

Với một khóa duy nhất `id`:

```sql
-- Tăng dần: trang sau có id lớn hơn cursor
SELECT id, created_at, payload
FROM events
WHERE id > :last_id
ORDER BY id ASC
LIMIT 50;

-- Giảm dần: trang sau có id nhỏ hơn cursor
SELECT id, created_at, payload
FROM events
WHERE id < :last_id
ORDER BY id DESC
LIMIT 50;
```

Với khóa ghép, cần so sánh theo đúng thứ tự ưu tiên.

Ví dụ `(created_at DESC, order_id DESC)`:

```sql
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at AND order_id < :last_order_id)
```

Ví dụ `(score ASC, item_id DESC)` có hướng sort khác nhau:

```sql
WHERE score > :last_score
   OR (score = :last_score AND item_id < :last_item_id)
ORDER BY score ASC, item_id DESC
```

Không dùng một dấu `>` hoặc `<` chung cho mọi cột khi sort direction khác nhau. Predicate phải phản ánh đúng thứ tự từ điển của từng thành phần.

### Row-value comparison

Một số hệ quản trị hỗ trợ row-value comparison ngắn gọn. Ví dụ PostgreSQL:

```sql
WHERE (created_at, order_id) < (:last_created_at, :last_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Với các cột cùng chiều giảm dần, biểu thức này tương đương điều kiện OR ở trên khi các cột không NULL. Khả năng tối ưu và cú pháp row comparison khác nhau giữa engine; hãy xem execution plan và kiểm thử đúng phiên bản.

## 7. Thiết kế composite index cho keyset

Keyset pagination đạt hiệu quả khi index hỗ trợ cả filter lẫn thứ tự. Với truy vấn:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Một index cần đánh giá có thể là:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, order_id DESC);
```

Thứ tự cột thường đặt equality predicates trước, sau đó là các cột sắp xếp/seek. Đây là điểm xuất phát, không phải quy tắc bất biến: selectivity, range predicate, join, include columns và engine có thể làm lựa chọn khác đi.

### Vì sao thứ tự cột quan trọng?

- `tenant_id` giới hạn phạm vi dữ liệu của một tenant.
- `status` lọc một nhóm trạng thái trong tenant.
- `created_at` xác định vị trí thời gian và thứ tự trang.
- `order_id` phân định các hàng có cùng timestamp.

Nếu truy vấn không lọc `status`, index có `status` nằm giữa `tenant_id` và `created_at` có thể không hỗ trợ thứ tự toàn cục theo thời gian trong phạm vi tenant như mong muốn. Khi có nhiều query pattern, có thể cần index khác hoặc thay đổi query contract.

### Covering index và chi phí ghi

Có thể cân nhắc include các cột output nhỏ để giảm lookup về bảng chính, nếu engine hỗ trợ. Nhưng index càng rộng thì càng tốn storage, cache và chi phí INSERT/UPDATE/DELETE.

Không đưa các payload lớn vào index chỉ để tránh một lookup. Đo bytes đọc, logical reads, index size và write throughput trước/sau.

## 8. OFFSET vẫn có trường hợp phù hợp

OFFSET không phải lúc nào cũng sai. Nó phù hợp khi:

- Tập dữ liệu nhỏ hoặc có giới hạn cứng.
- Chỉ cần các trang đầu và offset luôn thấp.
- Giao diện cần nhảy đến số trang bất kỳ.
- Người dùng cần tổng số trang hoặc vị trí trang cụ thể.
- Dữ liệu ít thay đổi trong thời gian người dùng duyệt.
- Truy vấn có index và workload đã chứng minh deep offset vẫn trong ngân sách.

Keyset phù hợp khi:

- Người dùng đi tuần tự qua feed hoặc danh sách lớn.
- Dữ liệu tăng nhanh theo thời gian.
- Cần latency ổn định hơn ở trang sâu.
- Có thể dùng khóa sắp xếp làm cursor.
- API chấp nhận điều hướng bằng next/previous cursor thay vì nhảy đến trang bất kỳ.

Thực tế có thể kết hợp: OFFSET cho trang đầu hoặc các trang nông, keyset cho cuộn sâu; hoặc cung cấp hai API khác nhau cho màn hình và export.

## 9. Keyset không tự tạo snapshot nhất quán

Keyset giảm vấn đề dịch chuyển vị trí do insert ở đầu danh sách, nhưng không tự bảo đảm mọi trang thuộc cùng một snapshot dữ liệu.

Với thứ tự giảm dần theo thời gian:

- Hàng mới được chèn trước cursor thường không xuất hiện ở các trang tiếp theo, vì cursor chỉ tìm các khóa nhỏ hơn mốc đã xem.
- Hàng bị xóa trước khi đến lượt sẽ không còn được trả về.
- Nếu một hàng chưa xem bị cập nhật sort key từ nhỏ hơn cursor sang lớn hơn cursor, nó có thể bị bỏ qua.
- Nếu một hàng đã xem bị cập nhật sort key từ lớn hơn cursor sang nhỏ hơn cursor, nó có thể xuất hiện lại.

Keyset thường ổn định hơn OFFSET với dữ liệu append-only và sort key bất biến, nhưng không tương đương một snapshot transaction.

### High-water mark cho dữ liệu tăng dần

Với bảng append-only có ID tăng đơn điệu, trang đầu có thể ghi nhận một mốc tối đa `max_id`. Các trang sau thêm điều kiện `id <= :high_water_mark` để loại bản ghi mới hơn mốc đó:

```sql
SELECT id, created_at, event_type
FROM events
WHERE id <= :high_water_mark
  AND id < :last_id
ORDER BY id DESC
LIMIT 100;
```

Điều này giúp một lượt duyệt không bị kéo dài vô hạn bởi dữ liệu mới. Tuy nhiên, high-water mark chỉ có ý nghĩa khi khóa phản ánh thứ tự thêm dữ liệu theo cách đã hiểu rõ. Với sequence có transaction cấp ID rồi commit muộn, hoặc dữ liệu được chèn backdated, `max_id` không nhất thiết là snapshot chính xác tại thời điểm bắt đầu.

### Snapshot nhất quán

Nếu yêu cầu tất cả trang phản ánh cùng một trạng thái dữ liệu, cần một cơ chế snapshot phù hợp:

- Giữ một transaction/snapshot xuyên suốt lượt đọc nếu database và thời lượng cho phép.
- Dùng temporal/versioned data hoặc snapshot ID ở tầng ứng dụng.
- Dùng immutable event stream và high-water mark có semantics rõ.
- Export dữ liệu sang một tập snapshot riêng rồi phân trang trên snapshot đó.

Giữ transaction mở trong thời gian người dùng đọc từng trang có thể giữ snapshot lâu, làm tăng version retention, vacuum/purge pressure hoặc connection usage. Không dùng long-lived transaction cho pagination tương tác nếu chưa đánh giá chi phí.

## 10. Sort key nên bất biến và có quy tắc NULL rõ ràng

Keyset pagination dễ dự đoán nhất khi sort key không thay đổi sau khi bản ghi được tạo. Ví dụ `created_at` và primary key thường ổn định hơn `status`, `priority` hoặc `updated_at`.

Nếu sort key thay đổi, một bản ghi có thể di chuyển từ phía sau cursor lên trước cursor hoặc ngược lại. Điều này có thể làm bỏ sót hoặc lặp bản ghi giữa các trang.

### Cột nullable

So sánh SQL với NULL tạo kết quả UNKNOWN, không phải TRUE/FALSE thông thường. Vì vậy, cursor trên cột nullable cần quy định thứ tự NULL rõ ràng.

Các cách xử lý:

- Dùng sort key NOT NULL nếu mô hình dữ liệu cho phép.
- Thêm biểu thức sort như `CASE WHEN sort_value IS NULL THEN 1 ELSE 0 END` và đưa giá trị đó vào cursor.
- Dùng generated/computed column hoặc expression index phù hợp với engine.
- Viết predicate cursor xử lý riêng nhánh NULL và non-NULL.

Ví dụ thứ tự `priority ASC NULLS LAST, item_id ASC` cần cursor chứa cả null rank, priority và item_id. Không chỉ lưu `priority` nếu giá trị có thể NULL.

### Collation và kiểu dữ liệu

Với phân trang theo text, thứ tự phụ thuộc collation, case sensitivity và quy tắc so sánh của database. Cursor phải được dùng cùng collation và expression sort như truy vấn ban đầu. Nếu collation hoặc kiểu dữ liệu thay đổi sau migration, cursor cũ có thể không còn hợp lệ.

## 11. Cursor là hợp đồng API

Cursor thường chứa các giá trị khóa của hàng cuối trang, phiên bản định dạng và có thể cả filter/sort context.

Ví dụ payload nội bộ:

```json
{
  "v": 1,
  "createdAt": "2026-11-19T10:30:00Z",
  "orderId": 850120,
  "sort": "created_desc",
  "filterHash": "..."
}
```

API có thể mã hóa payload bằng Base64 URL-safe để truyền trong query parameter. Base64 không phải mã hóa bảo mật và không ngăn người dùng sửa cursor.

### Ký và xác thực cursor

Nếu cursor ảnh hưởng đến phạm vi dữ liệu hoặc logic truy vấn, nên ký payload bằng HMAC hoặc cơ chế xác thực tương đương. Khi nhận cursor:

1. Giải mã và kiểm tra chữ ký.
2. Kiểm tra version và thời hạn nếu có.
3. Kiểm tra sort/filter context khớp request.
4. Xác thực tenant và quyền truy cập từ danh tính đã xác thực.
5. Kiểm tra kiểu, phạm vi và định dạng giá trị khóa.
6. Từ chối cursor không hợp lệ thay vì âm thầm dùng giá trị mặc định.

Không tin `tenant_id` hoặc quyền truy cập chỉ vì chúng nằm trong cursor do client gửi. Cursor không thay thế authorization.

### Cursor gắn với filter và sort

Cursor được tạo cho `status=PAID` và sort `created_at DESC` không nên được tái sử dụng cho `status=PENDING` hoặc sort khác. Nếu filter thay đổi, vị trí cursor không còn cùng tập kết quả.

Có thể đưa hash của filter đã chuẩn hóa, sort mode, tenant context và schema/version vào payload đã ký. Không nhất thiết đưa toàn bộ filter nhạy cảm vào cursor công khai.

## 12. Ví dụ API keyset trong Java

DTO response có thể chứa danh sách và cursor tiếp theo:

```java
public record OrderRow(
    long orderId,
    Instant createdAt,
    String status,
    BigDecimal totalAmount
) {}

public record CursorPage<T>(
    List<T> items,
    String nextCursor,
    boolean hasNext
) {}
```

Luồng xử lý khái quát:

```java
public CursorPage<OrderRow> findOrders(
        long tenantId, String cursorToken, int requestedSize) {
    int pageSize = Math.min(Math.max(requestedSize, 1), 100);

    Cursor cursor = cursorToken == null
        ? null
        : cursorCodec.verifyAndDecode(cursorToken);

    List<OrderRow> rows = repository.findNext(
        tenantId, cursor, pageSize + 1
    );

    boolean hasNext = rows.size() > pageSize;
    List<OrderRow> items = hasNext
        ? rows.subList(0, pageSize)
        : rows;

    String next = hasNext
        ? cursorCodec.encodeAndSign(items.get(items.size() - 1))
        : null;

    return new CursorPage<>(items, next, hasNext);
}
```

Đây là pseudocode. `cursorCodec` cần xác thực chữ ký, filter context và version. Repository phải dùng predicate seek đúng chiều sort và query projection chỉ lấy cột cần thiết. Không tạo cursor từ hàng dư thứ `pageSize + 1`; cursor phải dựa trên hàng cuối thực sự trả cho client.

## 13. Lấy trang trước bằng keyset

Keyset tự nhiên hỗ trợ đi tiếp. Để lấy trang trước, cần đảo điều kiện và thứ tự, lấy số hàng giới hạn rồi đảo danh sách trong ứng dụng.

Giả sử thứ tự hiển thị là `created_at DESC, order_id DESC`. Trang hiện tại bắt đầu tại cặp `(first_created_at, first_order_id)`. Các hàng trước trang hiện tại có cặp lớn hơn cursor đầu:

```sql
SELECT order_id, created_at, status
FROM orders
WHERE tenant_id = :tenant_id
  AND (
       created_at > :first_created_at
       OR (created_at = :first_created_at AND order_id > :first_order_id)
  )
ORDER BY created_at ASC, order_id ASC
LIMIT 50;
```

Truy vấn lấy 50 hàng gần nhất trước cursor theo thứ tự đảo ngược. Ứng dụng đảo thứ tự kết quả để hiển thị lại theo `DESC`.

Điều này có thể hỗ trợ nút Previous nhưng không cung cấp nhảy tùy ý đến trang số 500. Muốn quay lại trang đã xem, client có thể lưu cursor của đầu/cuối từng trang trong navigation history.

## 14. Keyset với filter động

Filter phải được giữ nhất quán giữa các trang. Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size;
```

Index cần xem xét:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, order_id DESC);
```

Nếu `status` có nhiều giá trị và filter có thể bỏ qua status, có thể cần một index khác bắt đầu bằng tenant rồi đến created_at. Không thể một index duy nhất tối ưu mọi tổ hợp filter và sort.

Với filter động, API cursor nên gắn với filter hash để ngăn dùng cursor cũ cho tập dữ liệu khác. Hãy giới hạn số tổ hợp sort/filter được hỗ trợ để tránh bùng nổ index.

## 15. Tổng số hàng và COUNT

OFFSET pagination thường được kết hợp với `COUNT(*)` để hiển thị 'trang 3 trên 2.000'. Nhưng count trên bảng lớn có thể là một truy vấn đáng kể, đặc biệt khi filter rộng hoặc cần scan index/table.

Keyset pagination thường chỉ cần biết còn trang tiếp hay không. Yêu cầu thêm một hàng (`pageSize + 1`) giúp xác định `hasNext` mà không cần đếm toàn bộ.

Nếu sản phẩm bắt buộc hiển thị tổng số:

- Đo chi phí count riêng với truy vấn lấy page.
- Có thể cache hoặc cập nhật summary count nếu freshness cho phép.
- Có thể hiển thị tổng ước lượng hoặc bỏ tổng số chính xác ở feed lớn.
- Đảm bảo count và page dùng cùng filter semantics.

Không chạy COUNT toàn bảng trên mỗi lần cuộn chỉ vì giao diện muốn hiển thị tổng số trang. Hãy xác nhận giá trị đó có thực sự cần cho người dùng.

## 16. OFFSET và keyset trong dữ liệu tăng dần

Với dữ liệu append-only có khóa tăng dần:

- OFFSET ở trang sâu phải đi qua nhiều hàng trước vị trí cần lấy.
- Keyset dùng `id < :last_id` hoặc `id > :last_id` để seek đến vùng gần cursor.
- INSERT mới thường không làm dịch chuyển cursor keyset như cách nó làm dịch chuyển offset.
- Nếu dữ liệu được xóa hoặc sort key thay đổi, cả hai cách có thể phản ánh tập dữ liệu khác nhau qua các request.

Ví dụ bảng event:

```sql
CREATE INDEX idx_events_created_id
ON events (created_at DESC, event_id DESC);
```

Keyset:

```sql
SELECT event_id, created_at, event_type
FROM events
WHERE (created_at, event_id) < (:last_created_at, :last_event_id)
ORDER BY created_at DESC, event_id DESC
LIMIT 100;
```

Với hệ quản trị không tối ưu row comparison hoặc có yêu cầu portability, dùng biểu thức OR tương đương và kiểm tra execution plan.

### ID tăng dần không luôn đồng nghĩa thứ tự commit

Sequence/identity có thể cấp ID trước khi transaction commit. Transaction nhận ID nhỏ hơn có thể commit muộn hơn transaction nhận ID lớn. Nếu lượt duyệt dùng `max_id` làm high-water mark, bản ghi commit muộn với ID thấp hơn mốc có thể xuất hiện ở trang sau dù chưa tồn tại tại thời điểm lấy trang đầu.

Nếu yêu cầu snapshot chặt, cần một cơ chế xác định commit visibility hoặc snapshot dữ liệu, không chỉ dựa vào sequence. Với feed thông thường, semantics 'đọc các bản ghi hiện thấy sau cursor' có thể đủ; cần nói rõ hợp đồng đó.

## 17. Các vấn đề về timestamp và độ chính xác

Timestamp có thể có độ chính xác khác nhau giữa database, driver và ứng dụng. Nếu cursor chuyển timestamp qua chuỗi với độ chính xác bị cắt, predicate trang sau có thể bỏ sót hoặc lặp hàng.

Ví dụ database lưu microsecond nhưng API chỉ serialize millisecond. Hai hàng khác nhau trong microsecond có thể bị biến thành cùng giá trị cursor.

Cách xử lý:

- Giữ độ chính xác đầy đủ của kiểu dữ liệu khi encode/decode cursor.
- Luôn thêm khóa phụ duy nhất như ID.
- Dùng UTC và quy tắc timezone thống nhất.
- Không parse rồi làm tròn timestamp khi tạo cursor.
- Kiểm tra round-trip từ JDBC type đến cursor payload.

Với `TIMESTAMP WITH TIME ZONE` và kiểu tương đương, hiểu cách engine chuẩn hóa timezone. Không dùng chuỗi timestamp locale-dependent trong cursor.

## 18. Sort direction hỗn hợp và predicate phức tạp

Khi sort có nhiều cột với chiều khác nhau, predicate phải mô phỏng đúng thứ tự.

Ví dụ:

```sql
ORDER BY priority ASC, created_at DESC, task_id ASC
```

Với cursor `(p, t, id)`, điều kiện trang sau là:

```sql
WHERE priority > :p
   OR (priority = :p AND created_at < :t)
   OR (priority = :p AND created_at = :t AND task_id > :id)
```

Mỗi thành phần dùng dấu so sánh tương ứng chiều sort. Với nhiều cột, biểu thức OR có thể dài; row-value comparison không phải lúc nào cũng diễn tả trực tiếp mixed directions.

Trong một số hệ thống, có thể chuẩn hóa sort key thành một biểu thức duy nhất hoặc tạo computed/generated column, nhưng cần bảo đảm biểu thức giữ thứ tự chính xác và index hỗ trợ. Đừng dùng phép biến đổi số học có nguy cơ overflow hoặc thay đổi semantics.

## 19. Execution plan: xác nhận database đang seek

Keyset chỉ nhanh khi database có access path phù hợp. Một truy vấn có predicate cursor nhưng vẫn scan/sort lượng lớn dữ liệu thì lợi ích sẽ giảm.

Khi đọc execution plan, xem:

- Có dùng composite index theo filter và sort không?
- Có range/seek condition trên cursor key không?
- Số hàng thực tế đọc có gần với page size không?
- Có sort lớn hoặc temporary table không?
- Estimated rows có sai lệch lớn không?
- Có lookup về bảng chính cho từng hàng không?
- Có filter residual làm engine đọc nhiều entry hơn cần thiết không?

Ví dụ PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = 42
  AND (
       created_at < TIMESTAMPTZ '2026-11-19 10:30:00+00'
       OR (
           created_at = TIMESTAMPTZ '2026-11-19 10:30:00+00'
           AND order_id < 850120
       )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Xem actual rows, loops, buffers, sort và scan type. `EXPLAIN ANALYZE` thực thi truy vấn; dùng dữ liệu và môi trường phù hợp.

Với MySQL, dùng `EXPLAIN ANALYZE` ở phiên bản hỗ trợ để xem actual rows/loops và iterator time. Với SQL Server, xem actual execution plan, logical reads và elapsed/CPU time. Tên operator khác nhau nhưng mục tiêu giống nhau: xác nhận engine seek theo index thay vì làm việc tỷ lệ với vị trí trang.

## 20. Benchmark OFFSET và keyset công bằng

Không benchmark hai phương pháp trên dữ liệu nhỏ rồi kết luận cho dữ liệu production. Cần có bảng đủ lớn và các vị trí trang khác nhau.

### Chuẩn bị dữ liệu

- Dữ liệu có quy mô tương đương hoặc lớn hơn dự kiến.
- Index và statistics giống môi trường mục tiêu.
- Phân bố tenant/status/key đại diện.
- Timestamp có trùng lặp để kiểm tra tie-breaker.
- Dữ liệu tăng trong lúc benchmark để mô phỏng concurrent insert.
- Có delete/update nếu workload thực tế cho phép thay đổi sort key.

### Các vị trí cần đo

| Vị trí | OFFSET mẫu | Keyset tương ứng |
| --- | ---: | --- |
| Trang đầu | 0 | Không có cursor |
| Trang 10 | 450 | Cursor hàng cuối trang 9 |
| Trang 100 | 4.950 | Cursor hàng cuối trang 99 |
| Trang 1.000 | 49.950 | Cursor hàng cuối trang 999 |
| Trang 10.000 | 499.950 | Cursor hàng cuối trang 9.999 |

Với page size 50, các offset mẫu trên biểu diễn vị trí gần tương đương. Đối với keyset, lấy cursor thực từ lần đọc trước hoặc tạo cursor tương đương bằng một truy vấn chuẩn bị ngoài cửa sổ đo.

### Metric cần thu thập

- p50/p95/p99 latency của từng trang.
- Goodput/throughput và request rate.
- Logical reads, rows examined và rows returned.
- CPU time, elapsed time và temp/sort usage.
- Bytes truyền và thời gian ResultSet consume ở JDBC.
- Connection acquisition, pool pending và transaction duration.
- Lock wait, deadlock và replication lag nếu có ghi đồng thời.
- Kết quả đúng: không trùng hoặc bỏ sót theo semantics đã định.

### Thử nghiệm concurrent writes

Chạy writer chèn dữ liệu mới trong lúc client đọc các trang liên tiếp. So sánh:

- OFFSET có lặp hoặc bỏ sót hàng khi tập dữ liệu dịch chuyển ra sao?
- Keyset có giữ được vị trí tiếp tục khi insert trước cursor không?
- Update sort key có làm hàng di chuyển qua cursor không?
- Kết quả có đáp ứng consistency contract của sản phẩm không?

Đừng chỉ so latency. Một cách phân trang nhanh nhưng trả dữ liệu sai hoặc không đúng hợp đồng nhất quán không phải giải pháp tốt.

## 21. Ví dụ diễn giải kết quả benchmark

Giả sử page size là 50 và cùng filter/index:

| Trang | OFFSET p95 | Keyset p95 |
| --- | ---: | ---: |
| 1 | 12 ms | 12 ms |
| 10 | 18 ms | 13 ms |
| 100 | 65 ms | 13 ms |
| 1.000 | 410 ms | 14 ms |
| 10.000 | 2.800 ms | 15 ms |

Các số liệu chỉ minh họa. Kết quả cho thấy OFFSET tăng theo độ sâu trong khi keyset giữ thời gian gần ổn định vì truy vấn bắt đầu từ cursor key. Cần đối chiếu logical reads và execution plan để xác nhận nguyên nhân.

Nếu keyset vẫn tăng latency ở trang sâu, hãy kiểm tra:

- Cursor predicate có dùng index không?
- Filter có làm selectivity giảm mạnh ở vùng sau cursor không?
- Có sort hoặc residual filter lớn không?
- Index có phù hợp với thứ tự và equality predicates không?
- Có dữ liệu skew hoặc hot partition không?
- Có contention, cache miss hoặc storage pressure theo thời gian không?

## 22. Tích hợp Spring Data và ORM

Spring Data hỗ trợ các kiểu phân trang truyền thống như `Pageable`, thường biểu diễn OFFSET/LIMIT. Một số phiên bản Spring Data cung cấp scrolling/keyset window API; khả năng và cú pháp phụ thuộc phiên bản framework và store module.

Với JPA/Hibernate, có thể viết query keyset rõ ràng bằng predicate trên khóa cursor và trả DTO projection. Cách này giúp kiểm soát SQL và cột cần lấy.

Ví dụ repository method khái quát:

```java
@Query("""
    select new com.example.api.OrderRow(
        o.id, o.createdAt, o.status, o.totalAmount
    )
    from Order o
    where o.tenantId = :tenantId
      and (
           o.createdAt < :lastCreatedAt
           or (o.createdAt = :lastCreatedAt and o.id < :lastId)
      )
    order by o.createdAt desc, o.id desc
    """)
List<OrderRow> findNextPage(
    long tenantId,
    Instant lastCreatedAt,
    long lastId,
    Pageable limit
);
```

Đây là minh họa JPQL; khi trang đầu chưa có cursor, nên dùng query riêng không chứa điều kiện cursor hoặc một predicate được xây dựng an toàn. `Pageable` có thể tự thêm sort/offset tùy cách framework dùng; không truyền một Pageable có offset sâu vào query keyset rồi nghĩ nó đã trở thành seek pagination. Dùng limit/page size theo API phù hợp và xác minh SQL thực tế.

### Không tải entity graph khi chỉ cần danh sách

Với endpoint danh sách, DTO projection giúp tránh hydrate toàn bộ entity và association. Truy vấn chỉ lấy ID, timestamp, status và vài cột hiển thị.

Không serialize entity có LAZY association trong vòng lặp trang; điều đó có thể tạo N+1 query và làm thời gian đọc ResultSet/JSON tăng.

## 23. API design: page number hay cursor token?

OFFSET thường phù hợp với API:

```http
GET /orders?page=12&size=50
```

Keyset thường phù hợp với API:

```http
GET /orders?limit=50&after=<cursor-token>
```

Cursor token nên là opaque với client. Client chỉ lưu và gửi lại token, không tự sửa giá trị sort key.

API cần xác định:

- Page size mặc định và tối đa.
- Cursor có hết hạn không?
- Filter/sort nào được hỗ trợ?
- Hành vi khi cursor không hợp lệ hoặc đã cũ.
- Có hỗ trợ previous cursor hay chỉ next?
- Dữ liệu mới xuất hiện trong khi duyệt có được đưa vào không?
- Có cần tổng count chính xác không?

Đừng để client tự gửi tên cột hoặc biểu thức ORDER BY tùy ý. Dùng danh sách sort mode được hỗ trợ và ánh xạ sang SQL cố định để tránh SQL injection và tránh query plan không kiểm soát.

## 24. Những trường hợp keyset không phù hợp hoặc cần thiết kế thêm

- Người dùng phải nhảy đến trang số bất kỳ mà không có cursor lịch sử.
- Thứ tự dựa trên nhiều trường thay đổi liên tục.
- Sort key không duy nhất và không có tie-breaker ổn định.
- Filter/sort có biểu thức phức tạp khó tạo index.
- Tập dữ liệu cần snapshot nhất quán nhưng không có snapshot token/version.
- Báo cáo cần tổng số và vị trí chính xác trên tập dữ liệu cố định.
- Dữ liệu có nhiều NULL hoặc collation đặc biệt nhưng cursor không mô tả được thứ tự.

Trong các trường hợp này, có thể:

- Dùng OFFSET cho các trang nông và giới hạn max offset.
- Tạo snapshot/report table rồi phân trang trên tập cố định.
- Dùng search index hỗ trợ sort/cursor phù hợp.
- Dùng materialized view hoặc read model cho báo cáo.
- Định nghĩa sort key bất biến hoặc bổ sung sequence riêng.

Không ép keyset vào một use case cần random access nếu điều đó làm API phức tạp và không đem lại lợi ích đo được.

## 25. Các lỗi triển khai thường gặp

- **ORDER BY không duy nhất.** Hàng có cùng sort key có thể đổi vị trí giữa các request.
- **Cursor chỉ chứa một phần sort key.** Tie-breaker bị thiếu dẫn đến trùng hoặc bỏ sót.
- **Dùng dấu so sánh sai chiều.** Trang tiếp theo trả ngược hoặc bỏ qua vùng dữ liệu.
- **Sort direction hỗn hợp nhưng dùng một predicate đơn giản.** Điều kiện không phản ánh thứ tự thực.
- **Timestamp bị làm tròn khi serialize.** Cursor không còn khớp khóa database.
- **Cột sort nullable nhưng không xử lý NULL.** Predicate SQL có thể không chọn đúng hàng.
- **Filter thay đổi nhưng dùng lại cursor cũ.** Vị trí cursor thuộc tập kết quả khác.
- **Tin cursor client gửi lên.** Có thể sửa tenant/key hoặc vượt quyền nếu không xác thực.
- **Cho rằng keyset tạo snapshot.** UPDATE/DELETE hoặc backdated insert vẫn có thể làm kết quả thay đổi.
- **Dùng Pageable offset cho query keyset.** Framework có thể thêm OFFSET ngoài ý muốn.
- **Không có index hỗ trợ cursor predicate.** Database vẫn scan/sort nhiều hàng.
- **Tạo index quá rộng.** Read nhanh hơn nhưng write cost và storage tăng.
- **Benchmark chỉ trang đầu.** Không phát hiện chi phí deep OFFSET.
- **Chỉ so latency.** Không kiểm tra tính đúng, logical reads và hành vi concurrent write.

## 26. Quy trình chọn và triển khai phương pháp phân trang

1. **Mô tả use case.** Xác định có cần nhảy trang, cuộn liên tục, tổng count hay snapshot.
2. **Đo quy mô và tăng trưởng.** Số hàng, tốc độ insert, filter phổ biến và độ sâu trang.
3. **Chọn thứ tự ổn định.** Có tie-breaker duy nhất, sort key ít thay đổi và quy tắc NULL rõ.
4. **Xây truy vấn OFFSET baseline.** Dùng cùng filter, ORDER BY và page size.
5. **Xây keyset predicate.** Tạo điều kiện seek đúng chiều cho toàn bộ sort key.
6. **Thiết kế composite index.** Equality filter trước, tiếp theo là sort/cursor key theo workload.
7. **Kiểm tra execution plan.** Xác nhận index seek/range scan, rows đọc, sort và lookup.
8. **Định nghĩa consistency contract.** Xử lý insert mới, delete, update sort key và high-water mark.
9. **Thiết kế cursor API.** Opaque token, ký, version, filter context và page size cap.
10. **Benchmark trang nông và sâu.** Đo p50/p95/p99, reads, CPU, bytes và concurrency.
11. **Kiểm thử concurrent changes.** Xác nhận không trùng/bỏ sót ngoài semantics đã công bố.
12. **Triển khai và theo dõi.** Theo dõi latency theo page depth, query fingerprint và index usage.

## 27. Danh sách kiểm tra trước khi phát hành

- [ ] Use case xác định rõ cần random page hay next/previous cursor.
- [ ] Query có ORDER BY xác định thứ tự toàn phần.
- [ ] Sort key kết thúc bằng tie-breaker duy nhất.
- [ ] Predicate keyset phản ánh đúng chiều sort của từng cột.
- [ ] NULL, collation, timestamp precision và kiểu dữ liệu được xử lý.
- [ ] Composite index hỗ trợ filter, cursor và ORDER BY.
- [ ] Execution plan đã được xác nhận trên dữ liệu có quy mô đại diện.
- [ ] Cursor chứa đủ khóa và filter/sort context.
- [ ] Cursor được xác thực và không thay thế authorization.
- [ ] Page size và max offset được giới hạn.
- [ ] API có semantics rõ với insert, delete và update đồng thời.
- [ ] High-water mark không bị nhầm với snapshot nếu dữ liệu commit muộn/backdated.
- [ ] Count query được đo riêng hoặc bỏ nếu không cần.
- [ ] Benchmark gồm trang đầu, trang nông và trang sâu.
- [ ] Có kiểm thử correctness với dữ liệu trùng sort key và concurrent writes.
- [ ] Telemetry ghi latency, rows, reads và lỗi theo query fingerprint.

## Kết luận

OFFSET đơn giản và phù hợp với tập dữ liệu nhỏ, trang nông hoặc giao diện cần nhảy theo số trang, nhưng chi phí thường tăng theo số hàng phải bỏ qua và vị trí trang có thể dịch chuyển khi dữ liệu thay đổi. Keyset pagination dùng giá trị khóa cuối trang làm cursor để seek đến vùng tiếp theo, thường giữ latency ổn định hơn trên dữ liệu lớn và tăng liên tục. Để đúng, nó cần thứ tự toàn phần với tie-breaker duy nhất, predicate khớp mọi chiều sort, composite index phù hợp và cursor gắn với filter/sort context. Keyset không tự tạo snapshot; UPDATE, DELETE và commit muộn vẫn cần consistency contract rõ ràng. Hãy benchmark trang nông lẫn sâu, kiểm tra execution plan, logical reads, p95/p99 và tính đúng dưới concurrent writes trước khi chọn chiến lược cho API.
