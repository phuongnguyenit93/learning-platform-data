# Phân trang theo khóa (keyset pagination) và điều kiện truy vấn tiếp theo

## Mục tiêu bài học

Khi một API hoặc màn hình cần hiển thị dữ liệu theo từng trang, cách làm quen thuộc là dùng `LIMIT` kết hợp `OFFSET`. Cách này đơn giản, nhưng càng đi đến trang sâu, cơ sở dữ liệu thường phải đọc và bỏ qua càng nhiều dòng trước khi trả về trang cần thiết. Dữ liệu được thêm hoặc xóa trong lúc người dùng chuyển trang cũng có thể làm các dòng bị lặp hoặc bị bỏ sót.

**Keyset pagination** (phân trang theo khóa, còn gọi là seek pagination) dùng giá trị khóa của dòng cuối trang hiện tại để xác định vị trí bắt đầu trang tiếp theo. Truy vấn tiếp tục bằng một điều kiện so sánh trên các cột sắp xếp, thay vì đếm và bỏ qua một số lượng dòng lớn.

Trong chương **Phân trang và tìm kiếm** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn cách thiết kế thứ tự sắp xếp ổn định, tạo continuation predicate, chọn chỉ mục và xử lý thay đổi dữ liệu giữa các lần gọi trang. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy cần kiểm chứng keyset pagination bằng `EXPLAIN`, số dòng đọc, độ trễ và tính đúng đắn khi dữ liệu thay đổi.

Sau bài học, bạn có thể:

- Giải thích giới hạn hiệu năng và tính nhất quán của phân trang bằng `OFFSET`.
- Thiết kế keyset pagination với thứ tự sắp xếp xác định và khóa phân biệt duy nhất.
- Viết điều kiện tiếp tục cho khóa đơn, khóa ghép và thứ tự có chiều tăng/giảm khác nhau.
- Chọn chỉ mục phù hợp với bộ lọc và thứ tự phân trang.
- Thiết kế cursor an toàn, ổn định và gắn với truy vấn.
- Xử lý trang trước, dữ liệu thay đổi đồng thời và các cột sắp xếp có thể nhận `NULL`.
- Đo và so sánh hiệu năng trước/sau trên dữ liệu đại diện.

## 1. Phân trang bằng OFFSET và giới hạn của nó

Một truy vấn phân trang truyền thống có thể viết như sau:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Truy vấn yêu cầu lấy 20 dòng sau khi bỏ qua 100.000 dòng đầu theo thứ tự. `order_id` là khóa phá hòa để thứ tự phân trang xác định khi nhiều đơn có cùng `created_at`. Để xác định đúng vị trí, hệ quản trị thường phải đi qua hoặc xử lý một lượng lớn dòng trước khi trả kết quả. Chỉ mục có thể hỗ trợ thứ tự và điều kiện lọc, nhưng `OFFSET` lớn vẫn thường làm tăng công việc vì các dòng bị bỏ qua phải được xác định.

### 1.1. Chi phí tăng theo độ sâu trang

Giả sử mỗi trang có 20 dòng:

| Trang | OFFSET | Dòng cần bỏ qua trước khi lấy 20 dòng |
|---:|---:|---:|
| 1 | 0 | 0 |
| 10 | 180 | 180 |
| 1.000 | 19.980 | 19.980 |
| 5.000 | 99.980 | 99.980 |

Đây là số dòng logic phải bỏ qua theo yêu cầu, không phải số lần đọc đĩa chính xác. Cache, index, filter và kế hoạch thực thi quyết định số trang vật lý thực tế. Dù vậy, khi OFFSET tăng lớn, thời gian và tài nguyên xử lý thường tăng theo.

### 1.2. Dữ liệu thay đổi giữa các trang

Giả sử trang đầu trả về các dòng được sắp xếp mới nhất trước. Trước khi người dùng yêu cầu trang thứ hai, một dòng mới được thêm vào đầu danh sách. Khi truy vấn trang hai dùng `OFFSET 20`, vị trí của các dòng cũ đã dịch chuyển; một dòng ở cuối trang đầu có thể xuất hiện lại. Ngược lại, nếu dòng bị xóa, một dòng có thể bị bỏ qua.

OFFSET phù hợp khi:

- Tập dữ liệu nhỏ hoặc độ sâu trang được giới hạn.
- Người dùng cần nhảy trực tiếp tới một số trang bất kỳ.
- Dữ liệu ít thay đổi hoặc ứng dụng chấp nhận sai lệch khi dữ liệu thay đổi.
- Đã đo và xác nhận chi phí ở độ sâu trang thực tế vẫn đáp ứng SLA.

Với luồng duyệt tuần tự như bảng tin, lịch sử giao dịch hoặc danh sách sự kiện, keyset pagination thường phù hợp hơn.

## 2. Nguyên lý keyset pagination

Keyset pagination dựa trên giá trị sắp xếp của dòng cuối cùng đã trả về. Truy vấn trang tiếp theo chỉ yêu cầu các dòng đứng sau khóa đó trong cùng thứ tự.

Điều kiện tiên quyết là thứ tự phải **xác định và duy nhất**. Nếu chỉ sắp xếp theo `created_at` mà nhiều dòng có cùng thời điểm, cơ sở dữ liệu không có đủ thông tin để phân định thứ tự giữa các dòng đồng thời. Hãy thêm một khóa duy nhất, thường là primary key, làm tiêu chí phá hòa.

Ví dụ, sắp xếp đơn hàng mới nhất trước:

```sql
ORDER BY created_at DESC, order_id DESC
```

`created_at` xác định thứ tự nghiệp vụ; `order_id` duy nhất làm thứ tự ổn định khi nhiều đơn có cùng thời điểm.

### 2.1. Trang đầu tiên

Trang đầu không cần điều kiện tiếp tục:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Ví dụ dùng page size 20 và lấy thêm một dòng (21) để xác định còn trang tiếp theo hay không. Nếu nhận đủ 21 dòng, ứng dụng trả 20 dòng đầu và đặt `has_next = true`. Nếu chỉ nhận tối đa 20 dòng, không còn dòng tiếp theo tại thời điểm truy vấn.

### 2.2. Trang tiếp theo bằng khóa ghép

Giả sử dòng cuối cùng của trang hiện tại có:

- `created_at = '2026-10-15 10:30:00+00'`
- `order_id = 8500`

Vì cả hai cột được sắp xếp giảm dần, các dòng tiếp theo có cặp khóa nhỏ hơn cặp khóa cursor. PostgreSQL hỗ trợ so sánh hàng theo thứ tự từ trái sang phải:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-15 10:30:00+00', 8500)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Điều kiện `(created_at, order_id) < (cursor_created_at, cursor_order_id)` có nghĩa:

1. Lấy dòng có `created_at` nhỏ hơn thời điểm cursor; hoặc
2. Nếu `created_at` bằng thời điểm cursor, lấy dòng có `order_id` nhỏ hơn cursor.

Đó chính là thứ tự tiếp tục sau dòng cuối trang khi cả hai khóa cùng sắp xếp DESC. Nếu dùng ASC cho cả hai cột, điều kiện tiếp tục sẽ dùng `>`.

### 2.3. Tạo cursor từ dòng cuối được trả về

Cursor tiếp theo phải được tạo từ dòng cuối cùng trong **20 dòng được trả về**, không phải dòng thứ 21 dùng để kiểm tra `has_next`. Nếu lấy khóa từ dòng thứ 21, lần gọi sau sẽ bắt đầu sau dòng đó và bỏ mất một dòng chưa từng được trả cho client.

Quy trình ở tầng ứng dụng:

1. Truy vấn `page_size + 1` dòng.
2. Nếu có dòng dư, đặt `has_next = true` và loại dòng dư khỏi payload trả về.
3. Lấy giá trị của toàn bộ cột sắp xếp từ dòng cuối cùng được trả về.
4. Mã hóa các giá trị đó thành cursor cho yêu cầu tiếp theo.
5. Nếu không có dòng dư, không cần tạo cursor tiếp theo.

## 3. Xây dựng continuation predicate

Continuation predicate là điều kiện xác định dòng nào đứng sau cursor theo đúng thứ tự `ORDER BY`. Công thức phải phản ánh đầy đủ từng cột sắp xếp, chiều ASC/DESC, quy tắc NULL và khóa phá hòa.

### 3.1. Một cột sắp xếp

Với thứ tự tăng dần:

```sql
ORDER BY created_at ASC
```

điều kiện trang tiếp theo là:

```sql
WHERE created_at > :cursor_created_at
```

Với thứ tự giảm dần:

```sql
ORDER BY created_at DESC
```

điều kiện tiếp theo là:

```sql
WHERE created_at < :cursor_created_at
```

Tuy nhiên, nếu `created_at` không duy nhất, hai điều kiện trên có thể bỏ sót các dòng có cùng thời điểm cursor. Vì vậy, trong thực tế thường cần thêm khóa duy nhất.

### 3.2. Nhiều cột cùng chiều sắp xếp

Với thứ tự:

```sql
ORDER BY created_at DESC, order_id DESC
```

điều kiện tiếp tục tương ứng:

```sql
(created_at, order_id) < (:cursor_created_at, :cursor_order_id)
```

Với thứ tự:

```sql
ORDER BY created_at ASC, order_id ASC
```

điều kiện tiếp tục là:

```sql
(created_at, order_id) > (:cursor_created_at, :cursor_order_id)
```

Row comparison trong PostgreSQL thực hiện so sánh từ trái sang phải theo thứ tự từ điển. Cách viết gọn này đặc biệt hữu ích khi các cột có cùng chiều sắp xếp và có quy tắc NULL rõ ràng.

### 3.3. Thứ tự có chiều tăng/giảm hỗn hợp

Không thể dùng một phép so sánh tuple đơn giản với cùng toán tử khi các cột có hướng sắp xếp khác nhau. Ví dụ:

```sql
ORDER BY score DESC, order_id ASC
```

Với cursor `(score = 95, order_id = 700)`, các dòng tiếp theo là:

- Dòng có `score` nhỏ hơn 95; hoặc
- Dòng có `score` bằng 95 và `order_id` lớn hơn 700.

Predicate tương ứng:

```sql
WHERE score < :cursor_score
   OR (score = :cursor_score AND order_id > :cursor_order_id)
```

Đây là dạng mở rộng từ điển tổng quát: ở mỗi vị trí, dùng toán tử theo chiều sắp xếp của cột đó; các cột đứng trước phải bằng giá trị cursor.

Với ba cột `a ASC, b DESC, c ASC`, điều kiện tiếp tục có dạng:

```sql
WHERE a > :a
   OR (a = :a AND b < :b)
   OR (a = :a AND b = :b AND c > :c)
```

Khi có nhiều cột, hãy tạo predicate theo đúng thứ tự `ORDER BY`, rồi kiểm tra bằng các trường hợp có giá trị bằng nhau ở một hoặc nhiều cột. Một sai dấu so sánh có thể gây lặp hoặc bỏ sót dòng.

### 3.4. Xử lý cột có thể NULL

So sánh tuple có thể cho kết quả UNKNOWN nếu một thành phần là NULL. Do đó, cách viết `(sort_key, id) < (...)` không đủ nếu `sort_key` có thể NULL và truy vấn có quy tắc `NULLS FIRST` hoặc `NULLS LAST`.

Giải pháp đơn giản nhất là dùng các cột cursor `NOT NULL`. Nếu nghiệp vụ cần giá trị NULL, phải đưa trạng thái NULL vào thứ tự và predicate một cách tường minh.

Ví dụ với PostgreSQL:

```sql
ORDER BY published_at DESC NULLS LAST, article_id DESC
```

Nếu `cursor_published_at` khác NULL, các dòng sau cursor gồm thời điểm nhỏ hơn, cùng thời điểm với `article_id` nhỏ hơn, và mọi dòng có `published_at IS NULL`:

```sql
WHERE published_at < :cursor_published_at
   OR (published_at = :cursor_published_at
       AND article_id < :cursor_article_id)
   OR published_at IS NULL
```

Nếu cursor đã nằm trong nhóm NULL ở cuối thứ tự, chỉ còn các dòng NULL có ID nhỏ hơn:

```sql
WHERE published_at IS NULL
  AND article_id < :cursor_article_id
```

Ứng dụng có thể chọn một trong hai dạng truy vấn dựa trên trạng thái cursor. Với thứ tự NULL phức tạp hơn hoặc nhiều cột nullable, hãy biểu diễn thứ tự NULL thành một khóa phụ rõ ràng (ví dụ cờ `is_null`) hoặc viết predicate theo từng nhánh và kiểm thử đầy đủ. Không thay NULL bằng một giá trị sentinel tùy tiện nếu giá trị đó có thể xuất hiện trong dữ liệu thật.

## 4. Thiết kế chỉ mục cho keyset pagination

Keyset pagination phát huy lợi ích khi cơ sở dữ liệu có thể tìm đến vị trí cursor bằng index rồi đọc tiếp các dòng theo thứ tự yêu cầu. Chỉ đổi `OFFSET` thành điều kiện `WHERE` mà không có access path phù hợp chưa chắc cải thiện hiệu năng.

### 4.1. Chỉ mục ghép theo bộ lọc và thứ tự

Với truy vấn:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND (created_at, order_id) < (:cursor_created_at, :cursor_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

một B-tree PostgreSQL có thể được xem xét:

```sql
CREATE INDEX idx_orders_customer_created_order
ON orders (customer_id, created_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Ý nghĩa thiết kế:

- `customer_id` đứng đầu vì truy vấn lọc bằng một khách hàng cụ thể.
- `created_at` và `order_id` theo đúng thứ tự phân trang.
- `INCLUDE` có thể giúp trả một số cột mà không cần lấy chúng từ heap khi các điều kiện index-only scan được đáp ứng; đây là lựa chọn có chi phí ghi và dung lượng.

Đây chỉ là một phương án để kiểm thử. Nếu workload lọc thêm trạng thái, thời gian hoặc tenant, thứ tự cột có thể cần thay đổi. Không đưa mọi cột đầu ra vào `INCLUDE` nếu điều đó làm chỉ mục quá rộng.

### 4.2. Bộ lọc bằng và khóa sắp xếp

Một nguyên tắc thiết kế thường dùng là đặt các điều kiện bằng có tính ổn định trước, tiếp theo là các cột phạm vi/thứ tự theo mẫu truy vấn. Tuy nhiên, cần cân nhắc nhiều truy vấn cùng sử dụng index và độ chọn lọc thực tế.

Ví dụ, nếu mọi truy vấn đều giới hạn `tenant_id` và `status`, sau đó phân trang theo thời gian:

```sql
CREATE INDEX idx_orders_tenant_status_page
ON orders (tenant_id, status, created_at DESC, order_id DESC);
```

Chỉ mục này có thể hỗ trợ truy vấn lọc bằng `tenant_id`, `status` và tiếp tục theo cặp khóa. Nếu `status` không phải điều kiện luôn có mặt, vị trí cột này có thể làm giảm tính hữu ích cho một số truy vấn khác. Hãy thiết kế theo tập truy vấn thực tế, không áp dụng máy móc quy tắc “cột lọc luôn đứng trước”.

### 4.3. Hướng ASC/DESC trong index

B-tree có thể được quét xuôi hoặc ngược. Với các cột cùng hướng, index có thể hỗ trợ thứ tự ngược bằng backward scan. Với thứ tự hỗn hợp, hướng từng cột trong index có thể quan trọng. Ví dụ `score DESC, order_id ASC` có thể cần index:

```sql
CREATE INDEX idx_orders_score_page
ON orders (score DESC, order_id ASC);
```

Khi có bộ lọc bằng ở phía trước, thêm các cột lọc vào đầu index theo workload. Xác nhận planner có dùng index để vừa lọc vừa cung cấp thứ tự hay vẫn phải sort.

### 4.4. Kiểm tra bằng EXPLAIN

Trong PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-15 10:30:00+00', 8500)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Hãy xem:

- `Index Cond`: điều kiện cursor có được dùng để định vị trong B-tree hay không.
- `Index Scan` hoặc `Index Only Scan`: đường truy cập được chọn.
- `Sort`: có phải sắp xếp thêm hay không; nếu có, kiểm tra số dòng trước sort.
- `actual rows` và `loops`: số dòng thực sự được đọc/trả và số lần node chạy.
- `Buffers: shared hit/read`: số buffer cache hit và read.
- `Planning Time` và `Execution Time`: chi phí lập kế hoạch và thực thi.

Một truy vấn keyset tốt thường bắt đầu từ vị trí khóa cursor và chỉ đọc số dòng gần với page size, nhưng điều đó còn phụ thuộc predicate, index, độ chọn lọc và kế hoạch. Nếu bộ lọc khác quá chọn lọc hoặc có biểu thức không tận dụng index, engine vẫn có thể phải xét nhiều dòng.

## 5. Thiết kế cursor ở tầng ứng dụng

Cursor là điểm tiếp tục của truy vấn, thường chứa các giá trị khóa sắp xếp ở dòng cuối trang. Nó không nhất thiết phải là ID của dòng cuối; nếu thứ tự có nhiều cột, cursor phải chứa tất cả các giá trị cần thiết để tái tạo continuation predicate.

Ví dụ payload logic:

```json
{
  "v": 1,
  "sort": "created_at_desc_order_id_desc",
  "created_at": "2026-10-15T10:30:00.000000Z",
  "order_id": 8500
}
```

Payload này chỉ minh họa cấu trúc. Trong API thực tế, cursor thường được mã hóa Base64 URL-safe hoặc định dạng tương đương để client không phải xử lý các trường bên trong.

### 5.1. Cursor cần có những gì?

- **Giá trị của mọi cột sắp xếp:** thiếu một cột có thể khiến thứ tự tiếp tục không xác định.
- **Phiên bản cursor:** hỗ trợ thay đổi cấu trúc cursor trong tương lai.
- **Định danh thứ tự:** cho biết chiều sắp xếp và quy tắc NULL đang áp dụng.
- **Ngữ cảnh bộ lọc:** có thể chứa fingerprint hoặc phiên bản của bộ lọc để tránh dùng cursor với truy vấn khác.
- **Ràng buộc thời gian hoặc snapshot nếu nghiệp vụ cần:** ví dụ mốc dữ liệu tối đa của một phiên duyệt.

Không cần đưa toàn bộ dữ liệu dòng vào cursor. Chỉ giữ các giá trị cần thiết để tiếp tục truy vấn và xác minh ngữ cảnh.

### 5.2. Cursor opaque và chống sửa đổi

Client nên xem cursor là chuỗi opaque, không tự sửa giá trị. Nếu payload có thể bị client thay đổi, người dùng có thể gửi khóa tùy ý, tạo truy vấn bất thường hoặc vượt qua ràng buộc nghiệp vụ ở tầng điều hướng.

Một cách triển khai là ký payload bằng HMAC hoặc dùng cơ chế token có xác thực. Khi nhận cursor:

1. Giải mã và xác minh chữ ký.
2. Kiểm tra phiên bản, kiểu dữ liệu và giới hạn kích thước.
3. Xác nhận cursor thuộc đúng endpoint, bộ lọc và thứ tự sắp xếp.
4. Áp dụng lại quyền truy cập và điều kiện tenant của người dùng hiện tại.
5. Dùng giá trị cursor làm tham số SQL có kiểu, không nối trực tiếp vào câu lệnh.

Cursor không phải cơ chế cấp quyền. Mỗi yêu cầu trang tiếp theo vẫn phải kiểm tra xác thực và phân quyền theo dữ liệu hiện hành.

### 5.3. Ràng buộc page size

Giới hạn page size ở phía server, ví dụ tối đa 100 dòng. Không tin trực tiếp giá trị `limit` do client gửi vì page size rất lớn có thể làm tăng bộ nhớ, I/O và thời gian giữ kết nối. Page size cũng nên được ràng buộc trong cursor nếu API yêu cầu tính nhất quán về kích thước trang.

## 6. Dữ liệu thay đổi giữa các yêu cầu trang

Keyset pagination giảm hiện tượng dịch chuyển vị trí do `OFFSET`, nhưng không tự tạo ra một snapshot nhất quán xuyên nhiều HTTP request.

### 6.1. Dòng mới được chèn

Với thứ tự mới nhất trước (`created_at DESC, id DESC`), sau khi trang đầu trả về cursor, một dòng mới có thời gian lớn hơn cursor được thêm vào đầu danh sách. Truy vấn trang tiếp theo dùng điều kiện nhỏ hơn cursor nên dòng mới đó không làm dịch chuyển các dòng cũ phía sau. Đây là một ưu điểm quan trọng so với OFFSET.

Nếu dòng mới được chèn với khóa sắp xếp nhỏ hơn cursor (ví dụ dữ liệu nhập trễ có timestamp cũ), nó có thể xuất hiện ở một trang tiếp theo. Hành vi này phù hợp với truy vấn “đọc tiếp theo thứ tự hiện tại”, nhưng có thể không phù hợp nếu nghiệp vụ yêu cầu ảnh chụp dữ liệu cố định.

### 6.2. Dòng bị xóa

Nếu một dòng chưa được đọc bị xóa trước khi đến trang của nó, dòng đó sẽ không xuất hiện. Keyset không thể trả một dòng đã bị xóa và cũng không bảo đảm mọi trang là một bản chụp tại thời điểm trang đầu.

### 6.3. Khóa sắp xếp bị cập nhật

Nếu `created_at`, `score` hoặc cột sắp xếp khác thay đổi sau khi một dòng đã được trả về, dòng có thể di chuyển qua ranh giới cursor. Điều này có thể gây lặp hoặc bỏ sót. Với luồng duyệt ổn định, nên dùng khóa sắp xếp bất biến hoặc gần như bất biến, chẳng hạn `created_at` được ghi một lần và primary key không thay đổi.

Nếu nghiệp vụ bắt buộc một snapshot nhất quán qua nhiều trang, cần một chiến lược riêng: giữ transaction/snapshot trong phạm vi phù hợp, dùng mốc phiên bản dữ liệu hoặc snapshot timestamp, hoặc tạo tập kết quả cố định. Giữ transaction dài qua nhiều request web thường gây áp lực lên connection pool, vacuum và tài nguyên; không nên làm nếu chưa thiết kế rõ vòng đời và giới hạn.

### 6.4. High-water mark cho phiên duyệt

Một lựa chọn nhẹ hơn snapshot đầy đủ là ghi nhận mốc cao nhất khi bắt đầu duyệt. Ví dụ với thứ tự mới nhất trước, lưu `max_created_at` hoặc một khóa đơn điệu làm giới hạn trên:

```sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = :customer_id
  AND created_at <= :session_high_water_mark
  AND (created_at, order_id) < (:cursor_created_at, :cursor_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Điều kiện high-water mark ngăn một số dòng mới hơn mốc ban đầu chen vào phiên duyệt. Nó không ngăn cập nhật/xóa dòng cũ, cũng không tạo snapshot MVCC đầy đủ. Nếu có thể nhập dữ liệu trễ với timestamp nhỏ hơn mốc, các dòng đó vẫn có thể xuất hiện; hãy chọn khóa mốc phù hợp với đặc tính dữ liệu.

## 7. Lấy trang trước (backward pagination)

Keyset cũng có thể lấy trang trước mà không dùng OFFSET. Giả sử thứ tự hiển thị là:

```sql
ORDER BY created_at DESC, order_id DESC
```

Cursor của trang hiện tại là dòng đầu tiên trên trang, tức ranh giới để tìm các dòng mới hơn. Truy vấn ngược thứ tự để lấy các dòng gần cursor nhất:

```sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = :customer_id
  AND (created_at, order_id) >
      (:first_created_at, :first_order_id)
ORDER BY created_at ASC, order_id ASC
LIMIT 21;
```

Ứng dụng lấy tối đa 20 dòng, bỏ dòng dư nếu có, rồi đảo thứ tự danh sách trước khi trả về để khớp thứ tự hiển thị DESC ban đầu. Cần dùng cursor của dòng đầu trang hiện tại, không dùng cursor cuối trang.

Với thứ tự hỗn hợp hoặc có NULL, điều kiện và thứ tự đảo phải được xây dựng theo đúng từng cột. Hãy kiểm thử qua ranh giới nhiều dòng có cùng giá trị sort key.

## 8. Keyset pagination qua phép nối

Truy vấn phân trang thường nối thêm bảng để lấy tên hoặc thông tin hiển thị. Hãy xác định khóa sắp xếp thuộc bảng nào và bảo đảm phép nối không nhân bản dòng trước khi áp dụng giới hạn.

Ví dụ lấy đơn hàng cùng tên khách hàng:

```sql
SELECT o.order_id, o.created_at, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id = :customer_id
  AND (o.created_at, o.order_id) <
      (:cursor_created_at, :cursor_order_id)
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 21;
```

Nếu `customers.customer_id` là khóa duy nhất, phép nối này không nhân bản đơn hàng. Nhưng nếu nối với bảng có nhiều dòng cho mỗi đơn (ví dụ lịch sử trạng thái), giới hạn có thể áp dụng lên dòng đã nhân bản thay vì đơn hàng. Khi đó, cần xác định tập khóa đơn hàng trước rồi mới lấy chi tiết, hoặc dùng `LATERAL`/subquery phù hợp để lấy một bản ghi liên quan theo quy tắc rõ ràng.

Một dạng lấy khóa trước:

```sql
WITH page_orders AS (
    SELECT order_id, created_at, customer_id
    FROM orders
    WHERE customer_id = :customer_id
      AND (created_at, order_id) <
          (:cursor_created_at, :cursor_order_id)
    ORDER BY created_at DESC, order_id DESC
    LIMIT 21
)
SELECT p.order_id, p.created_at, c.customer_name
FROM page_orders AS p
JOIN customers AS c
  ON c.customer_id = p.customer_id
ORDER BY p.created_at DESC, p.order_id DESC;
```

CTE ở đây thể hiện rõ ranh giới trang khóa. Optimizer có thể inline CTE tùy hệ quản trị và cấu trúc truy vấn; điều quan trọng là đảm bảo `LIMIT` được áp dụng lên tập đơn hàng duy nhất trước phép nối có khả năng nhân dòng. Nếu cần vật hóa, hãy đo chi phí và xem kế hoạch.

## 9. Đo lường và so sánh OFFSET với keyset

Không nên kết luận keyset nhanh hơn chỉ dựa trên lý thuyết. Hãy đo bằng dữ liệu có kích thước, phân bố và điều kiện lọc gần với production.

### 9.1. Kịch bản thử nghiệm

Chọn cùng một page size, cùng bộ lọc và cùng thứ tự sắp xếp. So sánh ít nhất:

- Trang đầu.
- Trang ở độ sâu trung bình.
- Trang rất sâu.
- Trường hợp nhiều dòng có cùng sort key.
- Trường hợp bộ lọc chọn lọc cao và thấp.
- Tải đồng thời tương tự giờ cao điểm.

Với OFFSET:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 21 OFFSET 100000;
```

Với keyset:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-15 10:30:00+00', 8500)
ORDER BY created_at DESC, order_id DESC
LIMIT 21;
```

Hai truy vấn cần dùng cùng một ranh giới logic khi so sánh. Nếu dữ liệu thay đổi trong lúc đo, kết quả không còn tương đương; dùng dữ liệu thử ổn định hoặc kiểm soát thời điểm lấy mẫu.

### 9.2. Các chỉ số cần theo dõi

| Chỉ số | Điều cần quan sát |
|---|---|
| Execution Time | Thời gian truy vấn ở các độ sâu trang khác nhau |
| Actual rows | Số dòng scan và số dòng trả về |
| Buffers hit/read | Lượng truy cập buffer và đọc vào cache |
| Rows Removed by Filter | Dòng bị loại sau khi đã đọc; giá trị cao có thể chỉ ra access path chưa phù hợp |
| Sort Method / Disk | Có phát sinh sort hoặc spill hay không |
| Planning Time | Chi phí lập kế hoạch, nhất là với SQL động nhiều biến thể |
| p50/p95/p99 | Độ trễ ở mức workload và trải nghiệm người dùng |
| Throughput và CPU/I/O | Ảnh hưởng tổng thể khi nhiều client phân trang đồng thời |

Một kế hoạch keyset tốt thường có index condition trên bộ khóa cursor, không cần sort lớn và chỉ đọc số dòng gần page size. Nếu actual rows hoặc buffers vẫn rất cao, hãy xem lại thứ tự index, filter, độ chọn lọc và việc join có nhân dòng hay không.

## 10. Các lỗi thiết kế thường gặp

- **Sắp xếp bằng cột không duy nhất:** dòng có cùng giá trị sort key không có thứ tự ổn định; thêm khóa duy nhất làm tie-breaker.
- **Cursor thiếu một cột sắp xếp:** điều kiện tiếp tục không thể tái tạo đúng thứ tự của `ORDER BY`.
- **Dùng sai dấu so sánh:** với DESC cần lấy giá trị nhỏ hơn; với ASC cần lấy giá trị lớn hơn, xét riêng từng cột trong thứ tự hỗn hợp.
- **Bỏ qua NULL:** row comparison có thể trả UNKNOWN; phải xử lý NULL theo đúng `NULLS FIRST/LAST`.
- **Cursor lấy từ dòng dư:** dùng dòng `page_size + 1` làm cursor sẽ bỏ qua dòng chưa được trả.
- **Sắp xếp trên cột hay thay đổi:** cập nhật sort key có thể làm dòng di chuyển qua ranh giới cursor.
- **Chỉ thay OFFSET bằng predicate nhưng không có index:** truy vấn vẫn có thể phải quét nhiều dòng.
- **Join nhân bản dòng trước LIMIT:** page size lúc này đếm dòng join, không phải thực thể nghiệp vụ mong muốn.
- **Dùng cursor cho bộ lọc khác:** cùng giá trị cursor nhưng filter hoặc sort khác có thể gây thiếu/lặp dữ liệu; gắn cursor với ngữ cảnh truy vấn.
- **Tin cursor như quyền truy cập:** cursor không thay thế xác thực, phân quyền hoặc tenant filter.
- **Kỳ vọng snapshot cố định:** keyset giảm dịch chuyển do chèn ở đầu danh sách nhưng không giữ một snapshot MVCC qua nhiều request.

## 11. Quy trình triển khai keyset pagination

**Bước 1 — Xác định trải nghiệm điều hướng.** Người dùng chỉ đi tới/lùi tuần tự hay cần nhảy tới trang bất kỳ? Keyset phù hợp nhất với điều hướng tuần tự theo cursor.

**Bước 2 — Chọn thứ tự tổng thể.** Chọn cột nghiệp vụ có thứ tự rõ ràng, thêm khóa duy nhất làm tie-breaker và quyết định quy tắc NULL.

**Bước 3 — Viết continuation predicate.** Tạo điều kiện theo đúng chiều ASC/DESC của từng cột. Kiểm thử trường hợp nhiều dòng trùng sort key, giá trị biên và NULL.

**Bước 4 — Thiết kế index.** Đặt các bộ lọc bằng và các cột sắp xếp theo thứ tự phù hợp với workload. Cân nhắc độ rộng index và chi phí ghi.

**Bước 5 — Thiết kế cursor.** Chứa mọi giá trị sort key, phiên bản và ngữ cảnh filter/sort cần thiết. Mã hóa/ký token và kiểm tra dữ liệu đầu vào.

**Bước 6 — Xây dựng truy vấn trang đầu và trang tiếp.** Lấy `page_size + 1`, tạo cursor từ dòng cuối được trả về và giới hạn page size phía server.

**Bước 7 — Xử lý thay đổi dữ liệu.** Quyết định có chấp nhận dữ liệu mới/xóa giữa các trang không; nếu cần tập cố định, thiết kế high-water mark hoặc snapshot phù hợp.

**Bước 8 — Kiểm tra phép nối.** Đảm bảo LIMIT áp dụng lên thực thể cần phân trang trước khi phép nối có thể nhân dòng.

**Bước 9 — Đo và xác nhận.** So sánh OFFSET/keyset ở trang sâu, đọc EXPLAIN, đo p95/p99, buffer, I/O và throughput. Kiểm tra không có dòng lặp hoặc bỏ sót trong kịch bản dữ liệu đại diện.

## 12. Checklist phân trang theo khóa

- [ ] Đã xác định keyset có phù hợp với nhu cầu điều hướng tuần tự hay không.
- [ ] Đã có thứ tự `ORDER BY` xác định và khóa duy nhất làm tie-breaker.
- [ ] Cursor chứa đủ mọi giá trị sắp xếp và đúng kiểu dữ liệu.
- [ ] Continuation predicate đúng với từng chiều ASC/DESC.
- [ ] Các cột nullable được xử lý theo đúng quy tắc `NULLS FIRST/LAST`.
- [ ] Cursor được tạo từ dòng cuối thực sự trả về, không phải dòng dư.
- [ ] Page size được giới hạn ở server.
- [ ] Cursor được kiểm tra chữ ký, phiên bản và ngữ cảnh filter/sort.
- [ ] Quyền truy cập và điều kiện tenant được áp dụng lại ở mỗi request.
- [ ] Chỉ mục hỗ trợ bộ lọc và thứ tự phân trang đã được kiểm chứng bằng EXPLAIN.
- [ ] Phép nối không nhân bản thực thể trước khi áp dụng LIMIT.
- [ ] Đã xác định cách xử lý insert, delete và cập nhật khóa sắp xếp giữa các trang.
- [ ] Đã đo trang đầu, trang sâu và tải đồng thời bằng dữ liệu đại diện.

## Kết luận

Keyset pagination dùng khóa của dòng cuối trang để tìm phần dữ liệu tiếp theo, giúp tránh chi phí bỏ qua hàng chục nghìn hoặc hàng triệu dòng của OFFSET. Để hoạt động đúng, truy vấn cần một thứ tự xác định, khóa phá hòa duy nhất và continuation predicate phản ánh chính xác chiều sắp xếp của từng cột.

Hiệu năng phụ thuộc vào chỉ mục phù hợp với bộ lọc và thứ tự, cũng như khả năng optimizer định vị trực tiếp từ cursor. Cursor cần chứa đủ giá trị, được gắn với bộ lọc/thứ tự và xác thực ở tầng ứng dụng. Keyset giảm ảnh hưởng của việc chèn dòng ở đầu danh sách nhưng không tạo snapshot cố định qua nhiều request; cần chọn rõ chính sách dữ liệu thay đổi theo yêu cầu nghiệp vụ. Cuối cùng, hãy đo bằng EXPLAIN, buffer, độ trễ và tải đồng thời trước khi triển khai.
