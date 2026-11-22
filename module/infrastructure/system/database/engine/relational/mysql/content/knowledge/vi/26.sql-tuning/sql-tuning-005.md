# Tối ưu phân trang OFFSET lớn bằng khóa tiếp nối

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao `LIMIT ... OFFSET ...` ngày càng tốn kém khi OFFSET lớn.
- Dùng keyset pagination (seek pagination) để lấy trang tiếp theo dựa trên khóa của hàng cuối trang hiện tại.
- Thiết kế thứ tự sắp xếp ổn định bằng một hoặc nhiều cột, luôn có tie-breaker duy nhất.
- Viết điều kiện tiếp nối đúng cho thứ tự ASC, DESC và thứ tự trộn chiều.
- Thiết kế composite index phù hợp với bộ lọc và `ORDER BY`.
- Phân trang an toàn với prepared statement, cursor opaque và dữ liệu thời gian có độ chính xác cao.
- Xử lý trang trước, trang kế tiếp, bộ lọc, JOIN và dữ liệu thay đổi trong lúc người dùng duyệt.
- Xác minh hiệu quả bằng `EXPLAIN`, `EXPLAIN ANALYZE` và các tình huống kiểm thử biên.
- Nhận diện khi OFFSET vẫn phù hợp và khi keyset pagination là lựa chọn tốt hơn.

## 1. Vấn đề của OFFSET lớn

Phân trang bằng `LIMIT` và `OFFSET` là cách viết quen thuộc:

```sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
```

Trang tiếp theo có thể dùng `OFFSET 20`, trang thứ 100 dùng `OFFSET 1980`. Cú pháp đơn giản, dễ ánh xạ vào giao diện có số trang, nhưng chi phí tăng theo vị trí trang.

Để trả về 20 hàng ở `OFFSET 1980`, MySQL thường phải tìm và bỏ qua khoảng 1.980 hàng đứng trước rồi mới trả 20 hàng tiếp theo. Với OFFSET rất lớn, engine vẫn phải duyệt nhiều index entry hoặc hàng trước vị trí cần lấy. `LIMIT` giới hạn số hàng trả về, nhưng không loại bỏ chi phí bỏ qua OFFSET.

Ví dụ:

```sql
-- Trang đầu
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 0;

-- Trang rất sâu
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 1000000;
```

Truy vấn thứ hai có thể phải đi qua một lượng lớn entry trước khi tìm được 20 hàng cần trả về. Tốc độ thường giảm khi người dùng đi sâu hơn trong danh sách.

### 1.1. OFFSET còn có thể làm trang bị trùng hoặc thiếu hàng khi dữ liệu thay đổi

Giả sử trang đầu trả về các hàng 1–20. Trước khi người dùng yêu cầu trang thứ hai, một hàng mới được chèn lên đầu danh sách. Với `OFFSET 20`, vị trí của các hàng đã dịch chuyển; một hàng ở cuối trang đầu có thể xuất hiện lại ở trang thứ hai.

Tương tự, nếu hàng bị xóa hoặc thay đổi thứ tự, OFFSET có thể bỏ qua một hàng mà người dùng chưa từng thấy.

Đây không phải lỗi cú pháp. OFFSET xác định vị trí tương đối trong kết quả tại thời điểm mỗi statement chạy; nó không lưu lại danh tính hàng cuối cùng mà người dùng đã xem.

## 2. Keyset pagination là gì?

Keyset pagination (còn gọi là seek pagination hoặc cursor pagination) lấy trang tiếp theo dựa trên giá trị khóa sắp xếp của hàng cuối cùng trong trang hiện tại.

Thay vì nói “bỏ qua 1.000.000 hàng”, ứng dụng nói “lấy các hàng đứng sau hàng có khóa sắp xếp này”. MySQL có thể dùng index để seek đến vị trí cursor rồi đọc tiếp một số lượng nhỏ hàng.

Ví dụ danh sách đơn hàng được sắp xếp mới nhất trước:

```sql
ORDER BY created_at DESC, order_id DESC
```

Nếu hàng cuối trang hiện tại có:

```text
created_at = 2026-11-18 10:30:00
order_id   = 84521
```

Trang tiếp theo cần các hàng có khóa sắp xếp nhỏ hơn cặp khóa đó:

```sql
WHERE created_at < '2026-11-18 10:30:00'
   OR (created_at = '2026-11-18 10:30:00' AND order_id < 84521)
```

Sau đó dùng cùng thứ tự `ORDER BY` và `LIMIT`:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at < '2026-11-18 10:30:00'
   OR (created_at = '2026-11-18 10:30:00' AND order_id < 84521)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

`LIMIT 21` trong ví dụ minh họa trang có 20 hàng: lấy thêm một hàng để xác định còn trang sau hay không. Giá trị cursor thực tế phải được truyền bằng prepared statement.

## 3. Thứ tự sắp xếp phải xác định duy nhất

Keyset pagination chỉ đáng tin cậy khi mỗi hàng có một vị trí xác định trong thứ tự kết quả.

### 3.1. ORDER BY trên cột không duy nhất là chưa đủ

Giả sử chỉ sắp xếp theo `created_at`:

```sql
ORDER BY created_at DESC
```

Nhiều đơn hàng có thể được tạo trong cùng một microsecond hoặc cùng một giây. Khi nhiều hàng có cùng `created_at`, thứ tự giữa chúng không được xác định đầy đủ. Cursor chỉ chứa timestamp không thể phân biệt đã đọc đến hàng nào trong nhóm trùng thời gian.

Thêm một khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, order_id DESC
```

Nếu `order_id` là khóa duy nhất, cặp `(created_at, order_id)` tạo ra thứ tự toàn phần cho các hàng có `created_at` không NULL.

### 3.2. Tie-breaker phải được dùng nhất quán ở mọi nơi

Ba phần phải khớp nhau:

1. `ORDER BY` trong câu SELECT.
2. Điều kiện tiếp nối dựa trên cursor.
3. Các cột và thứ tự trong index hỗ trợ truy vấn.

Nếu `ORDER BY` là `(created_at DESC, order_id DESC)`, cursor phải lưu cả hai giá trị và predicate phải xét cả hai cột. Không thể chỉ dùng `created_at` nếu giá trị này có thể trùng.

### 3.3. Chọn cột sắp xếp ổn định

Ưu tiên các cột:

- Có giá trị xác định, thường là `NOT NULL`.
- Ít thay đổi sau khi bản ghi được tạo.
- Có thứ tự nghiệp vụ rõ ràng.
- Có thể được hỗ trợ bằng index.
- Kết hợp với tie-breaker để tạo thứ tự duy nhất.

Nếu dùng một cột thường xuyên thay đổi như `status`, `priority` hoặc `updated_at`, hàng có thể di chuyển qua vị trí cursor giữa hai request. Khi đó người dùng có thể thấy hàng trùng hoặc bỏ lỡ hàng. Chỉ dùng cột mutable khi nghiệp vụ chấp nhận sự thay đổi đó hoặc có cơ chế snapshot riêng.

## 4. Mẫu cơ bản: trang đầu và trang kế tiếp

Giả sử bảng đơn hàng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    tenant_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_tenant_created_id
        (tenant_id, created_at, order_id)
) ENGINE = InnoDB;
```

Index bắt đầu bằng `tenant_id` vì truy vấn luôn lọc theo tenant, sau đó là các cột dùng để sắp xếp và tiếp nối.

### 4.1. Lấy trang đầu

```sql
SELECT order_id, customer_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Nếu giao diện cần 20 hàng, truyền `LIMIT 21`. Ứng dụng:

1. Kiểm tra số hàng trả về.
2. Nếu có 21 hàng, đặt `hasNextPage = true`.
3. Chỉ trả 20 hàng đầu cho client.
4. Tạo cursor từ hàng thứ 20, tức hàng cuối cùng thực sự hiển thị.
5. Không tạo cursor từ hàng thứ 21 vì hàng này chưa được hiển thị; dùng nó làm cursor sẽ bỏ qua hàng đó ở trang kế tiếp.

Nếu truy vấn trả về tối đa 20 hàng, `hasNextPage = false`.

### 4.2. Lấy trang kế tiếp

Giả sử cursor chứa `created_at` và `order_id` của hàng cuối trang hiện tại. Với thứ tự giảm dần trên cả hai cột:

```sql
SELECT order_id, customer_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = ?
  AND (
       created_at < ?
       OR (created_at = ? AND order_id < ?)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Tham số lần lượt là:

1. `tenant_id` của người dùng hiện tại.
2. `created_at` từ cursor.
3. Cùng giá trị `created_at` từ cursor.
4. `order_id` từ cursor.
5. `page_size + 1`.

Điều kiện có nghĩa:

- Lấy hàng có thời gian nhỏ hơn cursor; hoặc
- Nếu thời gian bằng cursor, lấy hàng có `order_id` nhỏ hơn cursor.

Vì cả hai cột đều sắp xếp DESC, giá trị nhỏ hơn nằm sau cursor.

### 4.3. Tại sao dùng LIMIT page_size + 1?

Nếu chỉ lấy đúng `page_size`, ứng dụng không biết có còn hàng tiếp theo hay không nếu không chạy thêm truy vấn. Lấy thêm một hàng giúp xác định `hasNextPage` trong cùng lần đọc.

Ví dụ `page_size = 20`:

- 0–20 hàng: không có hàng thứ 21, có thể kết luận không còn trang kế tiếp.
- 21 hàng: trả 20 hàng đầu, đặt `hasNextPage = true`.

Cursor cho request tiếp theo luôn được tạo từ hàng thứ 20 đã trả, không phải hàng thứ 21.

## 5. Điều kiện tiếp nối cho ASC và DESC

Điều kiện so sánh phụ thuộc chiều sắp xếp.

### 5.1. ASC trên một khóa duy nhất

Với:

```sql
ORDER BY order_id ASC
```

Trang kế tiếp sau `last_order_id`:

```sql
WHERE order_id > ?
ORDER BY order_id ASC
LIMIT ?;
```

Giá trị lớn hơn nằm sau cursor.

### 5.2. DESC trên một khóa duy nhất

Với:

```sql
ORDER BY order_id DESC
```

Trang kế tiếp sau `last_order_id`:

```sql
WHERE order_id < ?
ORDER BY order_id DESC
LIMIT ?;
```

Giá trị nhỏ hơn nằm sau cursor.

### 5.3. ASC trên hai khóa

Với:

```sql
ORDER BY created_at ASC, order_id ASC
```

Predicate tiếp nối:

```sql
WHERE created_at > ?
   OR (created_at = ? AND order_id > ?)
```

### 5.4. DESC trên hai khóa

Với:

```sql
ORDER BY created_at DESC, order_id DESC
```

Predicate tiếp nối:

```sql
WHERE created_at < ?
   OR (created_at = ? AND order_id < ?)
```

### 5.5. Quy tắc tổng quát cho nhiều cột

Với thứ tự:

```sql
ORDER BY a ASC, b DESC, c ASC, id DESC
```

Predicate “nằm sau cursor” là một chuỗi các nhánh OR. Mỗi nhánh giữ các cột trước bằng giá trị cursor, rồi so sánh cột hiện tại theo chiều tương ứng:

```sql
WHERE a > :a
   OR (a = :a AND b < :b)
   OR (a = :a AND b = :b AND c > :c)
   OR (a = :a AND b = :b AND c = :c AND id < :id)
```

Quy tắc:

- Cột `ASC`: giá trị lớn hơn nằm sau cursor, dùng `>`.
- Cột `DESC`: giá trị nhỏ hơn nằm sau cursor, dùng `<`.
- Mọi cột đứng trước cột đang xét phải bằng giá trị cursor.
- Cột cuối cùng nên là khóa duy nhất để phân biệt mọi hàng.

Đây là cách tổng quát để tránh sai logic khi trộn chiều sắp xếp.

## 6. Xử lý thứ tự trộn chiều

Nhiều danh sách cần sắp xếp theo một cột giảm dần và cột khác tăng dần. Không thể dùng một toán tử so sánh duy nhất cho tất cả cột.

Ví dụ danh sách ticket ưu tiên cao trước, ticket cùng ưu tiên thì cũ trước:

```sql
ORDER BY priority DESC, created_at ASC, ticket_id ASC
```

Giả sử cursor là `(priority = 5, created_at = '2026-11-01 10:00:00', ticket_id = 900)`.

Predicate tiếp nối:

```sql
WHERE priority < 5
   OR (
       priority = 5
       AND created_at > '2026-11-01 10:00:00'
   )
   OR (
       priority = 5
       AND created_at = '2026-11-01 10:00:00'
       AND ticket_id > 900
   )
```

SQL dùng tham số:

```sql
SELECT ticket_id, priority, created_at, subject
FROM tickets
WHERE tenant_id = ?
  AND (
       priority < ?
       OR (priority = ? AND created_at > ?)
       OR (priority = ? AND created_at = ? AND ticket_id > ?)
  )
ORDER BY priority DESC, created_at ASC, ticket_id ASC
LIMIT ?;
```

Index có thể được thiết kế theo cùng thứ tự:

```sql
CREATE INDEX idx_tickets_tenant_priority_created_id
ON tickets (tenant_id, priority DESC, created_at ASC, ticket_id ASC);
```

MySQL 8.0 hỗ trợ descending index key parts. Với các cột cùng chiều, InnoDB cũng có thể đọc index theo chiều ngược; với thứ tự trộn chiều, hướng của từng key part có thể quan trọng để tránh sort bổ sung. Hãy xác nhận bằng `EXPLAIN` thay vì chỉ dựa vào định nghĩa index.

## 7. Composite index cho keyset pagination

Keyset pagination phát huy hiệu quả khi predicate và thứ tự sắp xếp được index hỗ trợ.

### 7.1. Equality filter đứng trước sort key

Nếu mọi truy vấn đều lọc một tenant:

```sql
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
```

index phù hợp thường bắt đầu bằng cột equality filter:

```sql
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at, order_id);
```

Sau khi cố định `tenant_id`, MySQL có thể đọc các entry theo `created_at, order_id`.

### 7.2. Không có equality filter

Nếu danh sách toàn hệ thống không lọc tenant:

```sql
ORDER BY created_at DESC, order_id DESC
```

index có thể là:

```sql
CREATE INDEX idx_orders_created_id
ON orders (created_at, order_id);
```

Không nên thêm `tenant_id` vào đầu index nếu truy vấn không cố định tenant mà vẫn cần đọc theo toàn cục `created_at`; cột đầu không được cố định có thể phá thứ tự cần thiết.

### 7.3. Filter status có thể làm index phức tạp hơn

Nếu truy vấn:

```sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, order_id DESC
```

có thể cân nhắc:

```sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at, order_id);
```

Index này phù hợp khi `tenant_id` và `status` đều là equality filter. Nếu status là nhiều giá trị bằng `IN (...)`, hoặc filter là range trên một cột khác, thứ tự index cần đánh giá kỹ vì có thể không giữ được một luồng sắp xếp toàn cục theo `created_at`.

### 7.4. Đừng tạo index riêng cho mọi biến thể filter

Mỗi index tăng dung lượng và chi phí ghi. Hãy thống kê các dạng truy vấn chính, tần suất, độ chọn lọc và số hàng trả về. Ưu tiên index cho những đường truy cập quan trọng nhất.

### 7.5. InnoDB secondary index chứa primary key

Với bảng InnoDB, mỗi secondary index entry chứa khóa chính để định vị clustered record. Nếu `order_id` là primary key, index `(tenant_id, created_at)` có thể đã chứa `order_id` ở phần khóa phụ nội bộ. Tuy nhiên, việc khai báo tường minh `(tenant_id, created_at, order_id)` có thể giúp thể hiện rõ thứ tự index cần dùng và hỗ trợ các plan/order cụ thể. Hãy kiểm tra index thực tế và EXPLAIN trước khi giữ cả hai index gần giống nhau.

## 8. Row constructor comparison và predicate tường minh

MySQL hỗ trợ so sánh row constructor:

```sql
WHERE (created_at, order_id) < (?, ?)
```

Với thứ tự DESC trên cả hai cột, biểu thức này có cùng ý nghĩa từ điển với:

```sql
WHERE created_at < ?
   OR (created_at = ? AND order_id < ?)
```

Có thể viết:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT ?;
```

Tuy nhiên, không phải mọi row-constructor comparison đều được optimizer tận dụng index tối ưu như predicate tường minh. Với một số composite index, điều kiện row constructor có thể chỉ sử dụng được một phần key range. Hãy so sánh:

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (created_at, order_id) < ('2026-11-18 10:30:00.000000', 84521)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

với:

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (
       created_at < '2026-11-18 10:30:00.000000'
       OR (created_at = '2026-11-18 10:30:00.000000' AND order_id < 84521)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Nếu predicate tường minh tạo access plan tốt hơn trên phiên bản mục tiêu, dùng dạng đó. Đừng giả định cú pháp ngắn hơn luôn có plan tốt hơn.

## 9. Cursor phải giữ chính xác giá trị sắp xếp

Cursor là trạng thái để tiếp tục truy vấn. Nó phải chứa mọi giá trị cần thiết để xác định duy nhất vị trí cuối trang.

Với `ORDER BY created_at DESC, order_id DESC`, cursor cần ít nhất:

```json
{
  "created_at": "2026-11-18T10:30:00.123456",
  "order_id": 84521
}
```

### 9.1. Giữ độ chính xác thời gian

Nếu cột là `DATETIME(6)`, cursor phải giữ đủ microsecond. Làm tròn thành giây có thể khiến nhiều hàng cùng timestamp bị xem như một vị trí và dẫn đến lặp hoặc bỏ sót.

Giá trị truyền vào prepared statement phải được parse và bind đúng kiểu. Không chuyển đổi timestamp qua timezone hoặc format làm mất độ chính xác.

### 9.2. Cursor nên opaque với client

API có thể mã hóa cursor thành token Base64URL chứa JSON, nhưng Base64 không phải mã hóa bảo mật. Nếu cursor chứa tenant ID, filter hoặc dữ liệu nhạy cảm, cần bảo vệ tính toàn vẹn bằng chữ ký HMAC hoặc cơ chế token có xác thực.

Ví dụ payload nội bộ:

```json
{
  "v": 1,
  "sort": "created_desc_id_desc",
  "created_at": "2026-11-18T10:30:00.123456",
  "order_id": 84521,
  "filter_hash": "..."
}
```

Server nên:

- Xác thực chữ ký và phiên bản cursor.
- Kiểm tra cursor thuộc đúng loại sort đang được yêu cầu.
- Ràng buộc cursor với tenant/user được xác thực ở server.
- Không tin `tenant_id` trong token để thay thế kiểm tra quyền truy cập.
- Từ chối cursor sai định dạng, hết hạn hoặc không tương thích.

### 9.3. Bộ lọc phải giữ nhất quán giữa các trang

Cursor được tạo cho một bộ lọc cụ thể. Nếu trang đầu lọc `status = 'PAID'` nhưng request sau bỏ status hoặc đổi thành `PENDING`, vị trí cursor không còn cùng tập kết quả.

API nên giữ filter trong request tiếp theo hoặc lưu fingerprint của filter trong cursor để phát hiện client đổi điều kiện giữa chừng.

## 10. Trang trước (Previous page)

Keyset pagination không có số trang tự nhiên như OFFSET. Tuy nhiên, có thể hỗ trợ nút “Trang trước” nếu lưu cursor của trang hiện tại.

Giả sử thứ tự hiển thị DESC:

```sql
ORDER BY created_at DESC, order_id DESC
```

Để lấy các hàng đứng trước cursor hiện tại, predicate đổi chiều:

```sql
WHERE created_at > ?
   OR (created_at = ? AND order_id > ?)
```

Truy vấn tạm thời đọc theo chiều ASC để lấy các hàng gần cursor nhất:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = ?
  AND (
       created_at > ?
       OR (created_at = ? AND order_id > ?)
  )
ORDER BY created_at ASC, order_id ASC
LIMIT ?;
```

Ứng dụng lấy tối đa `page_size + 1`, bỏ hàng dư nếu có, rồi đảo thứ tự mảng kết quả trước khi hiển thị để giao diện vẫn giữ DESC.

Với sort trộn chiều, cần đảo từng chiều khi tìm trang trước và xây dựng predicate tương ứng. Hãy kiểm thử riêng vì điều kiện OR nhiều cột dễ sai.

### 10.1. Lưu cursor của các trang đã đi qua

Nếu UI cần quay lại đúng trang vừa xem, có thể lưu cursor đầu/cuối của từng trang trong lịch sử điều hướng phía client hoặc server. Không cần lưu số OFFSET. Nếu người dùng tải lại trang hoặc mở link mới, API có thể yêu cầu cursor được cung cấp.

## 11. Dữ liệu thay đổi trong lúc phân trang

Keyset pagination giảm vấn đề dịch chuyển vị trí do chèn/xóa ở đầu danh sách, nhưng không tự tạo snapshot nhất quán xuyên nhiều HTTP request.

### 11.1. Hàng mới được chèn trước cursor

Với thứ tự mới nhất trước, hàng mới thường có `created_at` lớn hơn cursor trang hiện tại. Trang tiếp theo dùng predicate nhỏ hơn cursor nên không bị đẩy vị trí và không lặp lại hàng cũ. Hàng mới thường chỉ xuất hiện khi người dùng tải lại từ đầu.

### 11.2. Hàng mới được chèn sau cursor

Nếu ứng dụng cho phép chèn dữ liệu có timestamp cũ hơn cursor, hàng đó có thể xuất hiện ở một trang tiếp theo dù chưa tồn tại khi người dùng mở trang đầu. Đây không phải lỗi của keyset; đó là dữ liệu mới nằm sau vị trí cursor.

### 11.3. Hàng bị xóa

Hàng đã bị xóa trước khi request tiếp theo chạy sẽ không xuất hiện. Keyset không giữ bản ghi đã xóa trong kết quả.

### 11.4. Sort key bị cập nhật

Nếu `created_at`, `priority` hoặc cột sắp xếp khác thay đổi sau khi hàng đã được hiển thị, hàng có thể di chuyển qua cursor. Nó có thể xuất hiện lại hoặc bị bỏ qua tùy hướng di chuyển.

Ưu tiên sort key bất biến. Nếu nghiệp vụ yêu cầu snapshot nhất quán tuyệt đối, cần một cơ chế snapshot/version riêng hoặc một transaction consistent read được duy trì xuyên suốt quá trình duyệt; cách sau thường không phù hợp với HTTP pagination dài vì giữ transaction và connection lâu.

### 11.5. Giới hạn bằng high-water mark

Một API có thể ghi lại khóa lớn nhất ở trang đầu làm high-water mark để ngăn hàng mới hơn xuất hiện trong các trang tiếp theo. Ví dụ, nếu sắp xếp theo `created_at DESC`, lưu timestamp/id đầu trang và thêm điều kiện upper bound cố định vào mọi request.

High-water mark chỉ ổn định phạm vi phía trên. Nó không ngăn hàng mới được chèn với timestamp cũ hơn, cũng không ngăn sort key bị cập nhật. Hãy xem đây là giới hạn tập dữ liệu, không phải snapshot hoàn chỉnh.

## 12. Keyset pagination với JOIN

JOIN một-nhiều có thể làm phân trang sai cấp dữ liệu.

Giả sử một đơn hàng có nhiều dòng hàng. Truy vấn:

```sql
SELECT o.order_id, o.created_at, i.item_id, i.product_id
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = ?
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
```

`LIMIT 20` áp dụng trên hàng sau JOIN. Một đơn có 10 item chiếm 10 vị trí; trang có thể chỉ chứa vài đơn hàng và cắt giữa danh sách item của một đơn.

Nếu mục tiêu là phân trang đơn hàng, hãy lấy trang order ID trước, sau đó mới JOIN chi tiết:

```sql
WITH page_orders AS (
    SELECT order_id, created_at
    FROM orders
    WHERE tenant_id = ?
      AND (
           created_at < ?
           OR (created_at = ? AND order_id < ?)
      )
    ORDER BY created_at DESC, order_id DESC
    LIMIT ?
)
SELECT
    o.order_id,
    o.created_at,
    o.customer_id,
    i.item_id,
    i.product_id,
    i.quantity
FROM page_orders AS p
JOIN orders AS o
  ON o.order_id = p.order_id
JOIN order_items AS i
  ON i.order_id = o.order_id
ORDER BY p.created_at DESC, p.order_id DESC, i.item_id;
```

Truy vấn minh họa trang tiếp theo. Trang đầu bỏ predicate cursor. CTE giới hạn tập đơn hàng trước khi mở rộng sang các item.

Nếu chỉ cần kiểm tra có bản ghi con hay không, cân nhắc `EXISTS` thay vì JOIN làm nhân số hàng.

## 13. Keyset pagination với DISTINCT, GROUP BY và kết quả tổng hợp

Khi truy vấn trả về các nhóm hoặc giá trị distinct, cursor phải dựa trên khóa sắp xếp của kết quả sau tổng hợp, không phải tùy tiện lấy khóa của bảng nguồn.

Ví dụ phân trang tổng doanh thu theo khách hàng:

```sql
SELECT
    customer_id,
    SUM(total_amount) AS revenue
FROM orders
WHERE tenant_id = ?
GROUP BY customer_id
ORDER BY revenue DESC, customer_id ASC
LIMIT ?;
```

Cursor cần chứa cả `revenue` và `customer_id`. Predicate trang tiếp theo phải theo đúng thứ tự trộn chiều:

```sql
HAVING SUM(total_amount) < ?
    OR (SUM(total_amount) = ? AND customer_id > ?)
```

Tuy nhiên, aggregate có thể cần tính lại nhiều dữ liệu ở mỗi trang và không nhất thiết có index hỗ trợ trực tiếp. Với báo cáo lớn, cân nhắc bảng tổng hợp/materialized summary hoặc snapshot kết quả để phân trang hiệu quả.

## 14. Đếm tổng số hàng

Keyset pagination không tự cung cấp tổng số trang hoặc số trang hiện tại. Nếu UI cần tổng số hàng:

```sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = ?;
```

COUNT có thể tốn kém trên tập dữ liệu lớn, đặc biệt khi filter không được hỗ trợ tốt bằng index. Không nên chạy COUNT cho mọi request nếu giao diện chỉ cần nút “Có thêm” hoặc “Tải thêm”.

Các lựa chọn:

- Dùng `page_size + 1` để xác định `hasNextPage`.
- Chỉ chạy COUNT khi người dùng thực sự cần tổng số.
- Cache count nếu dữ liệu thay đổi không quá nhanh và nghiệp vụ chấp nhận độ trễ.
- Duy trì bảng tổng hợp nếu count là yêu cầu quan trọng, có tần suất cao.

## 15. So sánh OFFSET và keyset pagination

| Tiêu chí | LIMIT/OFFSET | Keyset/seek pagination |
|---|---|---|
| Trang đầu | Đơn giản, nhanh khi tập dữ liệu nhỏ | Cũng đơn giản, cần thứ tự ổn định |
| Trang sâu | Phải bỏ qua nhiều hàng trước vị trí cần lấy | Seek theo cursor và đọc tiếp số hàng giới hạn |
| Nhảy trực tiếp đến trang N | Hỗ trợ tự nhiên | Không hỗ trợ tự nhiên nếu không biết cursor trước đó |
| Thứ tự sắp xếp | Nên có ORDER BY ổn định | Bắt buộc có thứ tự toàn phần và tie-breaker |
| Dữ liệu chèn ở đầu | Có thể làm dịch chuyển offset, gây trùng/thiếu | Ít bị ảnh hưởng đối với các trang tiếp theo sau cursor |
| Dữ liệu xóa/sửa sort key | Có thể dịch chuyển vị trí | Vẫn có thể thay đổi kết quả nếu sort key mutable |
| Tổng số trang | Dễ kết hợp COUNT và số trang | Thường dùng cursor và hasNextPage |
| API phù hợp | Giao diện cần số trang/nhảy trang | Feed, timeline, log, danh sách lớn, tải thêm |

Không cần thay OFFSET ở mọi nơi. OFFSET nhỏ, bảng nhỏ hoặc giao diện bắt buộc nhảy đến trang cụ thể vẫn có thể là lựa chọn phù hợp. Hãy ưu tiên keyset cho truy vấn có thể đi sâu và có thứ tự sắp xếp/index phù hợp.

## 16. Quy trình triển khai API cursor

Một luồng API thường gồm:

1. Client gọi endpoint với filter, sort và `limit`.
2. Server xác thực người dùng và xác định tenant từ session/token đã xác thực.
3. Nếu không có cursor, server chạy truy vấn trang đầu.
4. Nếu có cursor, server xác thực token, kiểm tra sort/filter tương ứng và giải mã giá trị khóa.
5. Server bind giá trị cursor và filter vào prepared statement.
6. Query lấy `limit + 1` hàng theo predicate keyset.
7. Server bỏ hàng dư, tạo cursor từ hàng cuối cùng được trả về.
8. Server trả `items`, `nextCursor` và `hasNextPage`.

Ví dụ response:

```json
{
  "items": [
    {
      "order_id": 84521,
      "created_at": "2026-11-18T10:30:00.123456",
      "total_amount": "1250000.00"
    }
  ],
  "nextCursor": "eyJ2IjoxLCJjcmVhdGVkX2F0IjoiLi4uIn0.signature",
  "hasNextPage": true
}
```

Đây là cấu trúc minh họa; token thực tế cần chữ ký hoặc cơ chế xác thực tương đương. Không dùng dữ liệu tenant từ cursor làm nguồn xác thực quyền truy cập.

### 16.1. Giới hạn page size

Server nên đặt page size tối đa, ví dụ 100 hoặc một giới hạn phù hợp với payload và tải database. Không để client yêu cầu hàng triệu bản ghi bằng cách truyền `limit` lớn.

### 16.2. Bind tham số, không nối chuỗi

Cursor và filter phải được bind qua prepared statement. Tên cột và hướng sort thường không thể bind như giá trị; nếu API cho phép nhiều sort mode, ánh xạ chúng qua whitelist cố định ở server.

Ví dụ không an toàn là nối trực tiếp giá trị cursor hoặc chuỗi sort do client gửi vào SQL. Hãy parse, validate và chọn template truy vấn đã định nghĩa.

### 16.3. Cursor có phiên bản

Đưa version vào payload giúp server từ chối hoặc xử lý token cũ khi thay đổi cấu trúc cursor. Không âm thầm diễn giải một cursor cũ theo thứ tự sort mới.

## 17. Đo hiệu năng

### 17.1. So sánh OFFSET sâu với keyset

OFFSET:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Keyset:

```sql
EXPLAIN ANALYZE
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (
       created_at < '2026-11-18 10:30:00.123456'
       OR (
           created_at = '2026-11-18 10:30:00.123456'
           AND order_id < 84521
       )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

So sánh:

- Số hàng/iterator thực tế.
- Số vòng lặp và thời gian mỗi iterator.
- Index được chọn.
- Có filesort hay không.
- Số hàng đọc trước khi đạt LIMIT.
- Latency khi cursor ở đầu, giữa và gần cuối dữ liệu.

`EXPLAIN ANALYZE` thực sự chạy truy vấn. Hãy dùng dữ liệu đại diện và môi trường phù hợp, tránh chạy thử tải nặng không kiểm soát trên production.

### 17.2. Đọc EXPLAIN truyền thống

```sql
EXPLAIN
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 10
  AND (
       created_at < '2026-11-18 10:30:00.123456'
       OR (created_at = '2026-11-18 10:30:00.123456' AND order_id < 84521)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Kiểm tra `key`, `type`, `key_len`, `rows`, `filtered` và `Extra`. Nếu optimizer không dùng index như dự kiến, xem lại thứ tự cột, predicate OR, statistics và dữ liệu. Có thể thử row constructor comparison để so sánh plan, nhưng quyết định dựa trên đo lường.

### 17.3. Statistics và dữ liệu thử nghiệm

Optimizer có thể chọn plan khác nhau khi bảng nhỏ, statistics cũ hoặc dữ liệu phân bố lệch. Hãy dùng tập dữ liệu gần production, cập nhật statistics khi cần bằng `ANALYZE TABLE` và đo nhiều vị trí cursor.

## 18. Các trường hợp biên cần kiểm thử

- Nhiều hàng có cùng timestamp.
- Cursor trỏ vào hàng cuối cùng của một nhóm timestamp trùng.
- Trang đầu có ít hơn page size.
- Không có hàng nào sau cursor.
- Cursor sai định dạng hoặc bị sửa.
- Cursor được dùng với tenant hoặc filter khác.
- Cột sort có NULL.
- Sort key có độ chính xác microsecond.
- Hàng bị xóa giữa hai request.
- Hàng mới được chèn trước hoặc sau cursor.
- Sort key bị cập nhật giữa hai request.
- Filter dùng `IN`, JOIN hoặc cột có cardinality thấp.
- Truy vấn có JOIN một-nhiều.
- Sort trộn ASC/DESC.
- Trang trước cần đảo predicate và đảo kết quả đúng cách.
- Cursor từ phiên bản API cũ được gửi sau khi thay đổi sort definition.

## 19. NULL trong cột sắp xếp

NULL làm logic tiếp nối phức tạp vì phép so sánh `=`, `<` và `>` với NULL trả về UNKNOWN. Nếu cột sort nullable, predicate keyset thông thường có thể bỏ sót nhóm NULL hoặc không đi qua ranh giới giữa NULL và non-NULL đúng như mong muốn.

Ưu tiên dùng sort key `NOT NULL`. Nếu nghiệp vụ bắt buộc nullable, hãy chuẩn hóa thứ tự NULL một cách tường minh, chẳng hạn thêm biểu thức phân loại NULL vào thứ tự và cursor:

```sql
ORDER BY
    (completed_at IS NULL) ASC,
    completed_at DESC,
    task_id DESC
```

Khi đó cursor phải chứa cả giá trị phân loại NULL, `completed_at` và `task_id`; predicate tiếp nối phải tuân theo từng chiều sort. Có thể cân nhắc generated column hoặc functional index nếu cần hỗ trợ biểu thức, nhưng phải xác minh cú pháp và plan trên phiên bản MySQL mục tiêu.

Đừng dùng `COALESCE(completed_at, 'một ngày giả')` tùy tiện. Giá trị thay thế có thể trùng dữ liệu hợp lệ hoặc làm sai thứ tự nghiệp vụ.

## 20. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| ORDER BY không có tie-breaker | Hàng có cùng sort key không có vị trí ổn định | Thêm primary/unique key vào cuối ORDER BY |
| Cursor chỉ chứa cột không unique | Có thể bỏ sót hàng trong nhóm giá trị trùng | Lưu toàn bộ sort key và tie-breaker |
| Dùng `>` cho thứ tự DESC | Trang tiếp theo đi sai hướng | Với DESC dùng `<`; với ASC dùng `>` |
| Sort trộn chiều nhưng dùng một toán tử cho mọi cột | Predicate không khớp thứ tự hiển thị | Tạo nhánh OR theo từng cột và chiều sort |
| Tạo cursor từ hàng dư `page_size + 1` | Hàng dư bị bỏ qua ở request tiếp theo | Tạo cursor từ hàng cuối thực sự trả cho client |
| Index không khớp filter/order | MySQL quét nhiều hàng hoặc sort bổ sung | Thiết kế composite index theo equality prefix rồi sort key |
| Dùng row constructor mà không xem plan | Optimizer có thể chỉ tận dụng một phần composite index | So sánh với predicate lexicographic tường minh |
| Sort key có thể thay đổi | Hàng di chuyển qua cursor, gây trùng/thiếu | Ưu tiên sort key bất biến hoặc dùng snapshot/version |
| Cursor mất microsecond | So sánh không còn chính xác | Giữ nguyên precision của DATETIME/TIMESTAMP |
| Cột sort nullable | Predicate so sánh không xử lý NULL đúng | Dùng NOT NULL hoặc thiết kế thứ tự NULL tường minh |
| JOIN một-nhiều trước LIMIT | Phân trang theo hàng JOIN thay vì entity gốc | Phân trang ID trước rồi JOIN chi tiết |
| Mong nhảy thẳng đến trang 500 | Keyset không có offset/page number tự nhiên | Dùng cursor đã lưu, hoặc OFFSET khi yêu cầu random page là bắt buộc |
| Tin cursor do client gửi | Có thể sửa khóa, tenant hoặc filter | Token opaque có chữ ký và kiểm tra quyền ở server |

## 21. Checklist trước khi đưa vào production

- [ ] Đã xác định rõ sort order và tie-breaker duy nhất.
- [ ] Các sort key ưu tiên `NOT NULL` và ít thay đổi.
- [ ] Cursor chứa đầy đủ mọi cột trong thứ tự sắp xếp.
- [ ] Predicate tiếp nối đúng chiều ASC/DESC của từng cột.
- [ ] Index bắt đầu bằng các equality filter rồi đến sort key phù hợp.
- [ ] Đã xem xét chi phí index và workload ghi.
- [ ] Truy vấn dùng prepared statement và page size có giới hạn.
- [ ] Server xác thực cursor, sort mode, filter và tenant.
- [ ] Cursor giữ chính xác kiểu dữ liệu và precision của sort key.
- [ ] `LIMIT page_size + 1` được dùng đúng và cursor lấy từ hàng cuối đã trả.
- [ ] Đã định nghĩa hành vi khi dữ liệu được chèn, xóa hoặc cập nhật giữa các request.
- [ ] JOIN một-nhiều được xử lý sau khi chọn trang entity gốc.
- [ ] Đã kiểm thử trang trước, trang kế tiếp, sort trộn chiều và NULL.
- [ ] Đã so sánh OFFSET sâu với keyset bằng EXPLAIN/EXPLAIN ANALYZE.
- [ ] Có fallback phù hợp nếu UI bắt buộc nhảy đến trang bất kỳ.

## 22. Kết luận

OFFSET lớn buộc MySQL bỏ qua nhiều hàng trước vị trí cần trả về, vì vậy chi phí tăng theo độ sâu trang. Keyset pagination thay vị trí OFFSET bằng khóa của hàng cuối trang hiện tại. Với thứ tự ổn định, predicate tiếp nối có thể cho phép MySQL seek qua composite index và chỉ đọc một lượng hàng gần với page size.

Thiết kế đúng cần có tie-breaker duy nhất, predicate khớp chiều ASC/DESC, index theo equality filter và sort key, cursor giữ chính xác giá trị, cùng quy tắc rõ ràng khi dữ liệu thay đổi. Keyset rất phù hợp cho feed, timeline và danh sách lớn; OFFSET vẫn hữu ích cho trang nông hoặc giao diện cần nhảy trang tùy ý. Hãy xác minh bằng execution plan và đo trên dữ liệu gần production trước khi triển khai.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: LIMIT Query Optimization](https://dev.mysql.com/doc/refman/8.4/en/limit-optimization.html)
- [MySQL 8.4 Reference Manual: Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html)
- [MySQL 8.4 Reference Manual: Row Constructor Expression Optimization](https://dev.mysql.com/doc/refman/8.4/en/row-constructor-optimization.html)
- [MySQL 8.4 Reference Manual: EXPLAIN Output Format](https://dev.mysql.com/doc/refman/8.4/en/explain-output.html)
