# Tìm kiếm điểm và quét phạm vi bằng chỉ mục B-tree

Chỉ mục B-tree giúp hệ quản trị tìm dữ liệu theo khóa mà không phải đọc toàn bộ bảng. Hai cách truy cập phổ biến là **tìm kiếm điểm** (point lookup), dùng điều kiện xác định một khóa hoặc một nhóm khóa rất nhỏ, và **quét phạm vi** (range scan), dùng điều kiện xác định một khoảng khóa. Hiểu cấu trúc B-tree và cách bộ tối ưu chuyển điều kiện SQL thành đường truy cập giúp kỹ sư thiết kế chỉ mục phù hợp, giảm lượng dữ liệu phải đọc và đánh giá đúng chi phí của truy vấn.

Bài học thuộc chương **Cơ chế truy cập** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; các chủ đề liên quan gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, nội dung tập trung vào cách B-tree phục vụ truy vấn, cách đọc dấu hiệu seek/scan trong kế hoạch và cách đo lợi ích cùng chi phí vận hành của chỉ mục.

## 1. B-tree lưu trữ và tìm khóa như thế nào?

B-tree là cấu trúc chỉ mục dạng cây cân bằng, được thiết kế để giảm số lần truy cập trang khi tìm kiếm trên tập dữ liệu lớn. Trong nhiều hệ quản trị quan hệ, chỉ mục được triển khai theo dạng B+tree: các nút trong giữ khóa phân cách và con trỏ đến nút con; các nút lá chứa khóa chỉ mục cùng thông tin định vị hàng hoặc dữ liệu hàng; các nút lá thường được liên kết để hỗ trợ duyệt tuần tự theo thứ tự khóa. Chi tiết triển khai có thể khác giữa sản phẩm.

Một cây B-tree có các đặc điểm quan trọng:

- **Cân bằng:** các đường đi từ gốc đến lá có độ sâu tương đương, giúp thời gian tìm kiếm ổn định khi dữ liệu tăng.
- **Nhiều nhánh:** mỗi trang có thể chứa nhiều khóa và con trỏ, nên cây thường có chiều cao nhỏ hơn cây nhị phân thông thường.
- **Khóa có thứ tự:** các khóa trong cây được sắp theo thứ tự xác định bởi kiểu dữ liệu và collation.
- **Trang lá:** lưu mục chỉ mục và thông tin để tìm hàng; trong B+tree, các lá thường hỗ trợ duyệt liên tiếp theo thứ tự khóa.
- **Tách/gộp trang:** khi thêm, xóa hoặc cập nhật khóa, hệ quản trị có thể phải chia trang, phân phối lại mục hoặc cập nhật cấu trúc cây.

Ví dụ khái niệm dưới đây minh họa một cây có các khóa phân cách ở nút gốc và các dải khóa ở các trang lá:

```text
                         [ 40 | 80 ]
                       /      |      \
                      /       |       \
             [10 20 30]  [50 60 70]  [90 100 110]
                 <------ liên kết lá ------>
```

Đây là sơ đồ giản lược để minh họa thứ tự khóa. Cấu trúc trang, cách lưu con trỏ và cách biểu diễn khóa trùng phụ thuộc hệ quản trị; không nên xem sơ đồ là định dạng vật lý chính xác của một sản phẩm cụ thể.

## 2. Tìm kiếm điểm (point lookup)

Tìm kiếm điểm là truy cập chỉ mục bằng điều kiện xác định một giá trị khóa, thường là phép so sánh bằng (`=`) trên khóa duy nhất hoặc khóa có độ chọn lọc cao.

Ví dụ:

```sql
SELECT customer_id, full_name, email
FROM customers
WHERE customer_id = 50128;
```

Nếu có B-tree index trên `customer_id`, hệ quản trị có thể bắt đầu ở trang gốc, đi qua các nút trong theo khoảng khóa, đến trang lá chứa khóa `50128`, sau đó lấy hàng tương ứng. Với khóa duy nhất, kết quả thường tối đa một hàng. Với khóa không duy nhất, một giá trị khóa có thể tương ứng nhiều hàng nên hệ quản trị phải đọc toàn bộ mục phù hợp.

Chi phí khái quát của một lần tìm kiếm gồm:

1. Đi qua các mức của cây để định vị khóa.
2. Đọc mục khóa ở trang lá.
3. Nếu chỉ mục không chứa đủ cột cần trả về, truy cập thêm hàng trong bảng hoặc chỉ mục lưu trữ dữ liệu.

Với cây có chiều cao `h`, phần tìm vị trí cần khoảng `h` lần truy cập trang trong trường hợp không có cache; số lần đọc thực tế có thể thấp hơn khi trang gốc và các trang trong đã nằm trong bộ nhớ. Chi phí còn phụ thuộc số hàng trùng khóa, số lần lookup bổ sung và mức ngẫu nhiên của truy cập dữ liệu.

### 2.1. Tìm kiếm điểm không phải lúc nào cũng rẻ

Một `Index Seek` hoặc thao tác tìm khóa có vẻ rất cụ thể, nhưng vẫn có thể tốn kém nếu:

- Điều kiện không đủ chọn lọc và một giá trị khớp với rất nhiều hàng.
- Truy vấn thực hiện lookup về bảng cho từng hàng được tìm thấy.
- Câu SQL được gọi với tần suất rất cao, khiến chi phí nhỏ trên mỗi lần cộng dồn thành lớn.
- Các trang dữ liệu cần đọc không nằm trong cache và truy cập phát sinh nhiều I/O ngẫu nhiên.
- Chỉ mục lớn, nhiều mức hoặc có độ phân mảnh làm tăng số trang phải truy cập.

Do đó, hãy xem số hàng thực tế, logical reads, physical reads, số lần lookup và tần suất truy vấn thay vì kết luận chỉ từ tên toán tử.

## 3. Quét phạm vi (range scan)

Quét phạm vi dùng B-tree để tìm điểm bắt đầu của một khoảng khóa, sau đó duyệt các mục kế tiếp cho đến khi vượt qua giới hạn cuối. Điều kiện thường gặp gồm:

- So sánh lớn hơn hoặc lớn hơn/bằng (`>`, `>=`).
- So sánh nhỏ hơn hoặc nhỏ hơn/bằng (`<`, `<=`).
- Khoảng dùng `BETWEEN`.
- Một số mẫu tiền tố chuỗi có thể khai thác thứ tự B-tree, tùy collation và hệ quản trị.
- Điều kiện kết hợp với `ORDER BY` và `LIMIT` để lấy một đoạn đầu của thứ tự khóa.

Ví dụ lấy các đơn hàng trong một khoảng thời gian:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at;
```

Với chỉ mục B-tree trên `created_at`, hệ quản trị có thể tìm trang lá đầu tiên có khóa từ thời điểm bắt đầu rồi duyệt các mục liên tiếp cho đến trước thời điểm kết thúc. Cách viết khoảng nửa mở `[bắt đầu, kết thúc)` tránh phải đoán giá trị thời gian nhỏ nhất hoặc độ chính xác của phần giây ở cuối ngày/tháng.

Chi phí quét phạm vi có thể mô tả gần đúng là chi phí định vị điểm đầu cộng chi phí đọc các mục/trang thuộc phạm vi. Nếu phạm vi chứa `k` hàng, phần xử lý sau khi định vị tăng theo lượng dữ liệu cần duyệt. Khi phạm vi chiếm tỷ lệ lớn của bảng, bộ tối ưu có thể chọn quét bảng vì đọc tuần tự ít tốn kém hơn nhiều lần truy cập ngẫu nhiên.

### 3.1. Khoảng mở, khoảng đóng và biên dữ liệu

Điều kiện biên ảnh hưởng trực tiếp đến kết quả và số hàng được đọc:

| Điều kiện | Ý nghĩa |
|---|---|
| `x >= a AND x <= b` | Bao gồm cả hai đầu mút |
| `x > a AND x < b` | Loại cả hai đầu mút |
| `x >= a AND x < b` | Bao gồm đầu đầu, loại đầu cuối |
| `x BETWEEN a AND b` | Thông thường tương đương bao gồm cả `a` và `b` |

Với dữ liệu thời gian, thường nên dùng khoảng nửa mở để tránh lỗi do độ chính xác timestamp. Ví dụ lấy dữ liệu tháng 10 bằng `created_at >= ngày_đầu_tháng_10 AND created_at < ngày_đầu_tháng_11`, thay vì tự tạo mốc `23:59:59.999...` ở ngày cuối tháng.

Kiểu dữ liệu của tham số nên tương thích với kiểu cột. Ép kiểu cột trong điều kiện có thể làm mất khả năng dùng chỉ mục hoặc khiến hệ quản trị phải xử lý nhiều hàng hơn. Nếu cần chuyển đổi, hãy cân nhắc chuyển tham số sang kiểu phù hợp thay vì áp hàm lên cột, đồng thời xác minh ngữ nghĩa và kế hoạch.

## 4. Tìm điểm và quét phạm vi trên chỉ mục ghép

Chỉ mục ghép (composite index) sắp xếp theo nhiều cột theo thứ tự khai báo. Ví dụ:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
```

Thứ tự khóa tạo ra một trật tự dạng từ điển: trước hết theo `customer_id`, sau đó theo `created_at` trong từng nhóm khách hàng. Chỉ mục này phù hợp với truy vấn tìm một khách hàng rồi quét đơn hàng trong một khoảng thời gian:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 50128
  AND created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
ORDER BY created_at;
```

Hệ quản trị có thể định vị nhóm `customer_id = 50128`, sau đó quét phạm vi `created_at` bên trong nhóm đó. Đây là mẫu kết hợp equality trên tiền tố và range trên cột kế tiếp.

### 4.1. Vì sao thứ tự cột quan trọng?

Với chỉ mục `(customer_id, created_at)`, các hàng được nhóm theo `customer_id` trước. Truy vấn lọc theo khách hàng và khoảng thời gian thường tận dụng tốt cấu trúc này.

Truy vấn chỉ lọc theo `created_at` có thể không tận dụng trực tiếp chỉ mục ghép này như một chỉ mục bắt đầu bằng `created_at`, vì các giá trị thời gian không được sắp xếp toàn cục độc lập với khách hàng. Một số hệ quản trị có kỹ thuật skip scan hoặc tối ưu khác trong điều kiện nhất định, nhưng không nên giả định mọi hệ quản trị đều dùng được hậu tố chỉ mục hiệu quả.

Hãy thiết kế thứ tự cột dựa trên các mẫu truy vấn thực tế:

- Các điều kiện equality thường được cân nhắc ở các cột đầu.
- Cột range thường được đặt sau các cột equality phù hợp khi truy vấn cần kết hợp chúng.
- Cột dùng để sắp xếp có thể được đưa vào chỉ mục nếu thứ tự khóa hỗ trợ `ORDER BY`.
- Độ chọn lọc, số giá trị phân biệt, phân bố dữ liệu và các truy vấn khác cũng ảnh hưởng quyết định.

Đây là hướng dẫn thiết kế, không phải quy tắc tuyệt đối. Bộ tối ưu, kiểu truy vấn, biểu thức, collation, phân vùng và đặc tính dữ liệu có thể làm thay đổi lựa chọn hiệu quả.

### 4.2. Equality ở tiền tố, range ở cột kế tiếp

Một mẫu phổ biến là:

```sql
WHERE tenant_id = :tenant
  AND event_time >= :from_time
  AND event_time < :to_time
```

Chỉ mục `(tenant_id, event_time)` có thể định vị một tenant rồi quét khoảng thời gian trong tenant đó. Nếu đổi thứ tự thành `(event_time, tenant_id)`, hệ quản trị có thể quét khoảng thời gian trên toàn bộ tenant rồi lọc tenant, tùy điều kiện và thống kê. Lựa chọn phù hợp phụ thuộc tỷ lệ tenant, độ rộng khoảng thời gian, phân bố dữ liệu và các truy vấn cần phục vụ.

## 5. Kết hợp B-tree với ORDER BY và LIMIT

B-tree duy trì thứ tự khóa, vì vậy một chỉ mục phù hợp có thể giúp trả kết quả theo thứ tự mà không cần sort riêng. Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 50128
ORDER BY created_at DESC
LIMIT 20;
```

Chỉ mục `(customer_id, created_at)` có thể cho phép tìm nhóm khách hàng và đọc từ phía cuối hoặc theo chiều đảo của phạm vi khóa để lấy 20 hàng mới nhất. Khả năng tận dụng chiều tăng/giảm và thứ tự nhiều cột phụ thuộc hệ quản trị cùng định nghĩa chỉ mục.

Điểm có lợi là hệ quản trị có thể dừng sớm sau khi tìm đủ 20 hàng, thay vì đọc toàn bộ đơn hàng của khách hàng rồi sắp xếp. Nhưng lợi ích chỉ xuất hiện khi thứ tự chỉ mục tương thích với điều kiện lọc và `ORDER BY`, đồng thời không có biểu thức hoặc collation làm thay đổi thứ tự cần thiết.

Nếu truy vấn yêu cầu:

```sql
ORDER BY created_at DESC, order_id DESC
```

và `created_at` có thể trùng nhau, việc bổ sung khóa phụ `order_id` giúp xác định thứ tự ổn định. Chỉ mục và câu SQL cần thống nhất thứ tự các cột nếu muốn tránh thao tác sort hoặc đảm bảo phân trang nhất quán.

## 6. Lookup hàng và chỉ mục bao phủ

Chỉ mục B-tree thường lưu các cột khóa và một tham chiếu hoặc cách định vị hàng. Nếu câu truy vấn cần cột không có trong chỉ mục, hệ quản trị có thể phải thực hiện thêm lookup vào bảng hoặc chỉ mục lưu trữ dữ liệu. Tùy sản phẩm, thao tác này có tên như Key Lookup, Bookmark Lookup hoặc heap/table fetch.

Ví dụ chỉ mục:

```sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
```

Truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 50128;
```

Nếu chỉ mục không chứa `created_at` và `total_amount`, hệ quản trị có thể phải quay lại hàng gốc cho từng kết quả. Khi số hàng khớp lớn, nhiều lần lookup có thể tốn kém.

Một chỉ mục bao phủ (covering index) chứa đủ các cột cần thiết cho một truy vấn để hệ quản trị có thể trả kết quả từ chỉ mục mà không phải truy cập hàng gốc trong trường hợp phù hợp. Cách khai báo cột bổ sung khác nhau giữa các hệ quản trị. Ví dụ SQL Server hỗ trợ `INCLUDE`; PostgreSQL và MySQL có cơ chế và giới hạn riêng.

Không nên đưa mọi cột của bảng vào khóa chỉ mục chỉ để bao phủ một truy vấn. Chỉ mục rộng hơn chiếm thêm dung lượng, giảm số mục trên mỗi trang, tăng chiều cao hoặc số trang cần đọc, tăng chi phí ghi và bảo trì. Chọn cột bao phủ dựa trên workload có giá trị và đo tác động tổng thể.

## 7. Điều kiện để B-tree hỗ trợ truy vấn hiệu quả

### 7.1. Điều kiện có thể khai thác thứ tự chỉ mục

Điều kiện truy vấn cần tương thích với biểu diễn và thứ tự khóa. Những mẫu thường thuận lợi gồm:

```sql
WHERE customer_id = :id
```

```sql
WHERE created_at >= :start_time
  AND created_at < :end_time
```

```sql
WHERE customer_id = :id
  AND created_at >= :start_time
  AND created_at < :end_time
```

Ngược lại, áp dụng hàm lên cột có thể làm bộ tối ưu khó dùng chỉ mục B-tree thông thường:

```sql
-- Có thể không tận dụng chỉ mục B-tree thông thường trên created_at
WHERE DATE(created_at) = DATE '2026-10-15'
```

Có thể viết lại thành khoảng thời gian tương đương:

```sql
WHERE created_at >= TIMESTAMP '2026-10-15 00:00:00'
  AND created_at <  TIMESTAMP '2026-10-16 00:00:00'
```

Việc viết lại phải giữ đúng múi giờ, kiểu dữ liệu, độ chính xác và ngữ nghĩa nghiệp vụ. Nếu ứng dụng cần lọc theo biểu thức, một số hệ quản trị hỗ trợ expression index hoặc computed/generated column; cần cân nhắc và đo riêng.

### 7.2. Điều kiện trên chuỗi

Một điều kiện tiền tố như:

```sql
WHERE product_code LIKE 'AB12%'
```

có thể khai thác B-tree trong một số hệ quản trị và collation vì các chuỗi có cùng tiền tố tạo thành một phạm vi khóa. Điều kiện chứa ký tự đại diện ở đầu:

```sql
WHERE product_code LIKE '%AB12'
```

thường không thể dùng thứ tự B-tree thông thường để tìm điểm bắt đầu của một khoảng hữu ích. Hỗ trợ còn phụ thuộc collation, kiểu dữ liệu, operator class và cấu hình. Nếu cần tìm kiếm chuỗi con, hãy đánh giá full-text index, trigram hoặc cơ chế chuyên biệt thay vì giả định B-tree sẽ giải quyết tốt.

### 7.3. NULL, collation và thứ tự tăng/giảm

Thứ tự của `NULL`, quy tắc so sánh chuỗi, phân biệt hoa thường, dấu và thứ tự tăng/giảm có thể khác giữa hệ quản trị hoặc cấu hình. Các điều kiện `IS NULL`, phép so sánh chuỗi và `ORDER BY` cần được kiểm tra trên đúng hệ thống. Chỉ mục có thể hỗ trợ truy vấn nhưng không nhất thiết đáp ứng chính xác thứ tự yêu cầu nếu collation hoặc hướng sắp xếp khác nhau.

## 8. Chọn giữa Index Seek, Index Range Scan và Table Scan

Tên toán tử trong execution plan khác nhau giữa các sản phẩm. Về mặt khái niệm:

| Cách truy cập | Khi thường phù hợp | Điểm cần đo |
|---|---|---|
| Point lookup / seek | Tìm một khóa duy nhất hoặc ít hàng | Số lần seek, số hàng trả về, lookup bổ sung |
| Index range scan | Quét một khoảng khóa hẹp hoặc có thứ tự | Độ rộng phạm vi, số trang lá, số hàng bị loại |
| Index scan | Đọc phần lớn hoặc toàn bộ chỉ mục | Kích thước chỉ mục, cột có sẵn, số trang và khả năng bao phủ |
| Table/heap/clustered scan | Truy vấn cần phần lớn dữ liệu hoặc bảng nhỏ | Số trang đọc, tuần tự/ngẫu nhiên, tỷ lệ hàng cần trả |

Không có một tỷ lệ phần trăm cố định để quyết định lúc nào seek tốt hơn scan. Điểm hòa vốn phụ thuộc kích thước bảng, kích thước hàng, mức chọn lọc, cache, tốc độ lưu trữ, chi phí lookup, tính tuần tự của truy cập và mức đồng thời.

Một truy vấn tìm 10 hàng trong bảng hàng triệu hàng thường có lợi khi dùng chỉ mục phù hợp. Một báo cáo cần 80% số hàng có thể chạy nhanh hơn với table scan. Một range scan trên chỉ mục nhỏ bao phủ truy vấn đôi khi hiệu quả hơn quét bảng, dù số hàng trả về khá lớn. Cần đo trên dữ liệu và workload thực tế.

## 9. Ví dụ thiết kế và kiểm chứng chỉ mục

Giả sử một ứng dụng thường truy vấn đơn hàng theo khách hàng trong một khoảng thời gian và lấy mới nhất trước:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC
LIMIT 50;
```

Ta đặt giả thuyết chỉ mục ghép `(customer_id, created_at)` có thể định vị nhóm khách hàng, quét khoảng thời gian theo thứ tự và dừng khi đủ 50 hàng. Trước khi tạo chỉ mục, cần xác định:

- Tần suất truy vấn và tỷ trọng trong workload đọc/ghi.
- Số đơn hàng trung bình và cực đại trên mỗi khách hàng.
- Độ rộng khoảng thời gian thường dùng.
- Phân bố dữ liệu theo khách hàng và thời gian.
- Kế hoạch hiện tại, estimated rows, actual rows, số trang đọc và sort.

Quy trình kiểm chứng:

1. Thu thập baseline với các tham số đại diện: khách hàng ít đơn, trung bình và nhiều đơn; khoảng thời gian ngắn và dài.
2. Lưu kế hoạch ước lượng và thực tế nếu có thể lấy an toàn.
3. Tạo chỉ mục thử nghiệm theo cú pháp của hệ quản trị.
4. Cập nhật hoặc xác nhận thống kê theo quy trình quản trị.
5. Chạy lại cùng workload, dữ liệu, tốc độ tải và trạng thái cache có thể so sánh.
6. Kiểm tra kế hoạch có dùng chỉ mục, có bỏ được sort hay giảm lookup không.
7. Đối chiếu p50/p95/p99, throughput, logical reads, physical reads và CPU.
8. Đo thêm chi phí ghi, dung lượng chỉ mục, thời gian tạo và bảo trì.
9. Kiểm tra kết quả trả về và thứ tự dữ liệu trước/sau không thay đổi.

Nếu khoảng thời gian rộng hoặc khách hàng có rất nhiều đơn hàng, truy vấn có thể vẫn đọc nhiều mục. Bộ tối ưu có thể chọn một phương án khác và điều đó không nhất thiết là sai. Nếu số lần lookup vẫn lớn, hãy xem xét chỉ mục bao phủ nhưng phải cân nhắc chi phí lưu trữ và ghi. Nếu kế hoạch không chọn chỉ mục, hãy kiểm tra thống kê, độ chọn lọc, thứ tự cột và kiểu dữ liệu trước khi ép kế hoạch.

## 10. Tác động của ghi và bảo trì chỉ mục B-tree

Chỉ mục cải thiện một số đường đọc nhưng phải được duy trì khi dữ liệu thay đổi. Khi `INSERT`, `DELETE` hoặc cập nhật cột khóa, hệ quản trị cần thêm, xóa hoặc di chuyển mục chỉ mục. Các chi phí có thể gồm:

- Thêm I/O và CPU cho mỗi lần ghi.
- Tăng dung lượng lưu trữ và bộ nhớ cache cần thiết.
- Tách trang khi trang lá không còn đủ chỗ.
- Tạo phân mảnh hoặc giảm tính tuần tự của trang tùy mẫu ghi và cách triển khai.
- Tăng thời gian backup, phục hồi, cập nhật thống kê và bảo trì.
- Tăng cạnh tranh khóa/latch hoặc các đồng bộ nội bộ khi nhiều phiên cùng sửa cấu trúc liên quan.

Với chỉ mục ghép, mọi cột khóa đều góp phần vào kích thước mục chỉ mục. Cột có kiểu dữ liệu lớn hoặc giá trị dài có thể làm giảm số mục trên mỗi trang. Thêm cột bao phủ cũng làm chỉ mục rộng hơn. Vì vậy, không nên tạo chỉ mục riêng cho từng truy vấn mà không xem xét các chỉ mục hiện có và workload ghi.

## 11. Đọc execution plan để nhận diện truy cập B-tree

Khi đọc kế hoạch thực thi, hãy tìm các toán tử liên quan đến chỉ mục và xác định chính xác phần điều kiện được dùng để định vị khóa.

Các khái niệm cần phân biệt:

- **Seek condition / index condition:** điều kiện giúp xác định phạm vi khóa cần đọc.
- **Residual predicate / filter:** điều kiện còn phải kiểm tra sau khi các mục đã được truy cập; có thể khiến hệ quản trị đọc nhiều mục rồi loại phần lớn.
- **Lookup:** truy cập bổ sung vào hàng gốc hoặc cấu trúc khác để lấy cột chưa có trong chỉ mục.
- **Rows estimated/actual:** số hàng dự đoán và số hàng thực tế được xử lý hoặc trả ra.
- **Loops:** số lần toán tử được gọi; đặc biệt quan trọng ở nhánh trong của nested loop.
- **Logical/physical reads:** số trang được lấy từ cache và số lần cần đọc từ lưu trữ theo định nghĩa của hệ quản trị.

Ví dụ, kế hoạch có thể dùng seek trên `customer_id` nhưng vẫn đọc hàng trăm nghìn mục rồi lọc `created_at` ở residual predicate. Điều đó khác với việc dùng cả `customer_id` và khoảng `created_at` làm điều kiện định vị. Hãy kiểm tra chi tiết seek predicate/index condition thay vì chỉ nhìn tên `Index Seek`.

Một range scan có thể đọc nhiều mục hơn số hàng trả về nếu có residual filter, điều kiện join hoặc cột bị loại sau khi truy cập. Tỷ lệ giữa số mục đọc và số hàng trả về là tín hiệu hữu ích để đánh giá chất lượng đường truy cập.

## 12. Những giới hạn và lỗi thiết kế thường gặp

- **Chỉ mục ghép sai thứ tự:** cột lọc quan trọng nằm sau cột có thứ tự không phù hợp với mẫu truy vấn.
- **Phạm vi quá rộng:** range scan đọc quá nhiều mục, khiến table scan hoặc một kế hoạch khác hiệu quả hơn.
- **Hàm trên cột:** điều kiện không còn tương thích trực tiếp với thứ tự khóa B-tree thông thường.
- **Ép kiểu ngầm:** chuyển đổi kiểu dữ liệu có thể ảnh hưởng khả năng seek và ước lượng.
- **Residual predicate lớn:** hệ quản trị đọc nhiều mục rồi loại phần lớn ở bước sau.
- **Lookup lặp lại:** seek tìm được nhiều hàng nhưng mỗi hàng phải truy cập bảng, làm chi phí tăng mạnh.
- **Chỉ mục quá rộng:** tốn dung lượng, cache, chi phí ghi và bảo trì.
- **Bỏ qua phân bố dữ liệu:** cùng một điều kiện có thể rất chọn lọc với giá trị này nhưng không chọn lọc với giá trị khác.
- **Giả định mọi hệ quản trị giống nhau:** cách hiển thị toán tử, lưu trữ hàng, hỗ trợ skip scan, index-only scan và thứ tự NULL có thể khác nhau.
- **Đánh giá bằng một lần chạy:** cache, tải nền và tham số có thể làm kết quả sai lệch.

## 13. Bài tập tự kiểm tra

### Bài tập 1: Chọn thứ tự cột cho chỉ mục ghép

Một bảng `events` có truy vấn thường xuyên lọc `tenant_id` bằng một giá trị, sau đó giới hạn `event_time` trong một khoảng. Hãy đề xuất thứ tự cột cho B-tree index và giải thích.

**Gợi ý trả lời:** có thể bắt đầu thử nghiệm với `(tenant_id, event_time)` vì điều kiện equality trên tenant xác định một nhóm khóa, sau đó range scan theo thời gian trong nhóm đó. Cần kiểm tra các truy vấn khác, độ chọn lọc, phân bố tenant và kế hoạch thực tế trước khi chốt.

### Bài tập 2: Tìm kiếm điểm hay quét phạm vi?

Truy vấn lọc `status = 'OPEN'` trả về 55% số hàng. Chỉ mục B-tree trên `status` tồn tại nhưng kế hoạch chọn table scan.

**Câu hỏi:** có thể kết luận bộ tối ưu chọn sai không?

**Gợi ý trả lời:** không. Vì tỷ lệ hàng cần đọc lớn, table scan có thể ít tốn kém hơn nhiều lần truy cập chỉ mục và lookup. Cần đo số trang, logical/physical reads, cache và workload trước khi quyết định.

### Bài tập 3: Phân tích residual predicate

Kế hoạch dùng index seek theo `customer_id`, đọc 100.000 mục, sau đó filter theo `created_at` và chỉ trả 40 hàng.

**Câu hỏi:** cần kiểm tra điều gì để giảm lượng dữ liệu đọc?

**Gợi ý trả lời:** kiểm tra cấu trúc chỉ mục có thể đưa `created_at` vào sau `customer_id` hay không, xem thống kê và độ chọn lọc, xác nhận điều kiện thời gian có thể trở thành range condition, rồi đo lại số mục đọc, số hàng trả về và chi phí ghi của chỉ mục mới.

### Checklist khi thiết kế và đánh giá B-tree

- [ ] Đã xác định truy vấn cần tìm một khóa hay quét một khoảng khóa.
- [ ] Đã hiểu thứ tự khóa và chiều của chỉ mục.
- [ ] Đã kiểm tra điều kiện equality, range, ORDER BY và LIMIT.
- [ ] Đã đánh giá thứ tự cột của chỉ mục ghép theo workload.
- [ ] Đã phân biệt seek condition với residual predicate.
- [ ] Đã đo số hàng/trang đọc, lookup, loops và độ trễ.
- [ ] Đã xem xét chỉ mục bao phủ và chi phí chỉ mục rộng.
- [ ] Đã đo tác động lên ghi, dung lượng, cache và bảo trì.
- [ ] Đã thử với nhiều tham số và độ rộng phạm vi đại diện.
- [ ] Đã xác nhận kết quả dữ liệu và thứ tự trả về vẫn đúng.

Tìm kiếm điểm và quét phạm vi là hai cách khai thác thứ tự của B-tree. Tìm kiếm điểm định vị một khóa hoặc nhóm khóa nhỏ; quét phạm vi định vị điểm đầu rồi duyệt các khóa liên tiếp. Khi thiết kế đúng thứ tự cột, điều kiện SQL tương thích với chỉ mục và kết quả được kiểm chứng trên workload thực tế, B-tree có thể giảm đáng kể lượng dữ liệu phải đọc. Quyết định cuối cùng vẫn cần cân bằng độ trễ đọc, thông lượng, chi phí ghi, bộ nhớ, I/O và khả năng bảo trì.
