# Truy vấn chỉ từ chỉ mục: điều kiện thực tế và giới hạn kiểm tra tính hiển thị

## Mục tiêu bài học

Một truy vấn có thể lấy các cột cần thiết ngay từ chỉ mục mà không phải đọc lại bản ghi trong bảng. Cách truy cập này thường được gọi là *index-only scan* trong PostgreSQL hoặc *covering index access* trong nhiều hệ quản trị khác. Nó có thể giảm số lần đọc trang dữ liệu, nhưng chỉ mục chứa đủ cột vẫn chưa bảo đảm truy vấn luôn tránh được việc truy cập bảng.

Trong chương **Cơ chế truy cập** của module **DATABASE_PERFORMANCE**, bài học này giải thích điều kiện để truy vấn được phục vụ từ chỉ mục, vai trò của visibility map trong PostgreSQL và giới hạn của việc kiểm tra tính hiển thị theo MVCC. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy quyết định tạo covering index phải dựa trên kế hoạch thực thi, số lần đọc thực tế, trạng thái dữ liệu và chi phí ghi phát sinh.

Sau bài học, bạn có thể:

- Phân biệt index scan thông thường với index-only scan.
- Xác định các cột và điều kiện truy vấn cần được đáp ứng từ chỉ mục.
- Giải thích vì sao PostgreSQL vẫn có thể phải đọc heap dù kế hoạch là `Index Only Scan`.
- Đọc `Heap Fetches`, buffer statistics và các chỉ số trong `EXPLAIN (ANALYZE, BUFFERS)`.
- Đánh giá ảnh hưởng của VACUUM, cập nhật dữ liệu, transaction kéo dài và thiết kế chỉ mục.
- Kiểm chứng lợi ích của truy vấn chỉ từ chỉ mục trên tải đọc/ghi đại diện.

## 1. Truy vấn chỉ từ chỉ mục là gì?

Khi thực hiện truy vấn, hệ quản trị cần lấy giá trị của các cột dùng để lọc, nối, sắp xếp, nhóm và trả kết quả. Với một index scan thông thường, chỉ mục giúp tìm vị trí các dòng phù hợp, sau đó engine thường truy cập bản ghi trong bảng để lấy những cột còn thiếu hoặc kiểm tra thông tin cần thiết.

Với truy vấn chỉ từ chỉ mục, tất cả giá trị cần thiết cho kế hoạch có thể được lấy từ các mục trong chỉ mục. Nếu hệ quản trị có thể xác nhận bản ghi phù hợp mà không đọc trang dữ liệu bảng, nó tránh được các lần truy cập heap hoặc clustered data page tương ứng.

Ví dụ, ứng dụng thường xuyên lấy các đơn hàng gần nhất của một khách hàng:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Một chỉ mục có `customer_id` và `created_at` làm khóa, đồng thời chứa `order_id`, `status`, `total_amount` như các cột dữ liệu đi kèm, có thể cung cấp toàn bộ giá trị cần thiết cho truy vấn. Nếu điều kiện về tính hiển thị cũng được đáp ứng, PostgreSQL có thể sử dụng `Index Only Scan`.

### 1.1. Index scan và index-only scan

| Đặc điểm | Index Scan | Index Only Scan |
|---|---|---|
| Vai trò của chỉ mục | Tìm vị trí các dòng phù hợp | Tìm dòng và cung cấp các giá trị cần thiết từ chính chỉ mục |
| Đọc bảng/heap | Thường truy cập heap để lấy dữ liệu hoặc kiểm tra tính hiển thị | Có thể bỏ qua heap khi trang heap được xác nhận all-visible |
| Điều kiện về cột | Cột đầu ra hoặc điều kiện có thể lấy từ heap | Các cột cần cho kế hoạch phải có thể lấy từ chỉ mục |
| Phụ thuộc trạng thái dữ liệu | Có | Có; riêng PostgreSQL còn phụ thuộc visibility map |
| Kết quả kỳ vọng | Giảm phạm vi tìm kiếm so với quét toàn bảng | Có thể giảm thêm truy cập heap và I/O |

Tên `Index Only Scan` trong kế hoạch PostgreSQL thể hiện loại toán tử được chọn. Nó không khẳng định rằng mọi dòng đều được xử lý mà không đọc heap. Một toán tử index-only vẫn có thể thực hiện heap fetch để kiểm tra visibility khi cần.

### 1.2. Covering index là điều kiện về dữ liệu, không phải lời hứa về kế hoạch

Thuật ngữ *covering index* mô tả chỉ mục có thể cung cấp các cột mà một truy vấn cần. Khả năng tận dụng chỉ mục đó phụ thuộc bộ tối ưu, kiểu chỉ mục, điều kiện truy vấn và cơ chế nhất quán của hệ quản trị.

Một truy vấn chỉ có thể được phục vụ từ chỉ mục nếu:

1. Chỉ mục có thể trả về tất cả cột cần thiết cho các toán tử trong kế hoạch, bao gồm cột lọc, nối, sắp xếp, nhóm và kết quả.
2. Kiểu chỉ mục và operator class hỗ trợ lấy lại giá trị cần thiết.
3. Các điều kiện của truy vấn tương thích với khóa chỉ mục, biểu thức chỉ mục hoặc điều kiện của partial index.
4. Cơ chế kiểm tra tính hiển thị của hệ quản trị cho phép xác nhận bản ghi mà không cần đọc bảng, hoặc chấp nhận số lần truy cập bảng còn lại.
5. Bộ tối ưu đánh giá đường truy cập này có chi phí thấp hơn các phương án khác.

Ngay cả khi đáp ứng các điều kiện kỹ thuật, optimizer vẫn có thể chọn sequential scan nếu bảng nhỏ, truy vấn đọc phần lớn dữ liệu, hoặc chi phí truy cập chỉ mục cộng heap không có lợi.

## 2. Các cột cần thiết phải có trong chỉ mục

Trước khi tạo covering index, hãy đọc toàn bộ truy vấn và xác định cột nào cần trong từng giai đoạn. Không chỉ nhìn danh sách `SELECT`.

Với truy vấn:

```sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Các cột có vai trò:

| Cột | Vai trò |
|---|---|
| `customer_id` | Lọc các đơn hàng theo khách hàng |
| `status` | Lọc đơn hàng đã thanh toán |
| `created_at` | Sắp xếp đơn hàng mới nhất |
| `order_id`, `total_amount` | Trả kết quả |

Một phương án chỉ mục PostgreSQL có thể là:

```sql
CREATE INDEX idx_orders_customer_created_cover
ON orders (customer_id, created_at DESC)
INCLUDE (status, order_id, total_amount);
```

Trong B-tree PostgreSQL, các cột trong danh sách khóa như `customer_id`, `created_at` tham gia cấu trúc sắp xếp và tìm kiếm. Các cột `INCLUDE` được lưu như payload để trả dữ liệu nhưng không tham gia điều hướng B-tree hoặc xác định thứ tự khóa. Vì `status` là cột lọc nhưng không nằm trong khóa, engine có thể phải kiểm tra điều kiện trên payload sau khi tìm các mục theo `customer_id`; hiệu quả còn phụ thuộc số đơn hàng của mỗi khách hàng và số mục phải đọc.

Nếu `status` có độ chọn lọc và thứ tự truy cập phù hợp, một thiết kế khác có thể đưa nó vào khóa:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_id, total_amount);
```

Không có công thức thứ tự khóa đúng cho mọi hệ thống. Hãy cân nhắc:

- Điều kiện bằng (`=`) và điều kiện phạm vi (`<`, `>`, `BETWEEN`).
- Thứ tự sắp xếp và khả năng đáp ứng `ORDER BY` từ chỉ mục.
- Số dòng được chọn và phân bố giá trị của từng cột.
- Các truy vấn khác cùng dùng chỉ mục.
- Chi phí ghi, kích thước chỉ mục và khả năng cache.

### 2.1. INCLUDE và giới hạn của payload

Trong PostgreSQL, `INCLUDE` trên B-tree cho phép lưu thêm các cột không phải khóa trong các mục chỉ mục. Cách này hữu ích khi cần trả về một số cột mà không cần dùng chúng để tìm kiếm hoặc sắp xếp.

Không nên đưa mọi cột của bảng vào `INCLUDE`:

- Chỉ mục lớn hơn, chiếm nhiều dung lượng và bộ nhớ đệm.
- `INSERT`, `UPDATE`, `DELETE` phải duy trì thêm dữ liệu chỉ mục.
- Cập nhật cột payload cũng có thể làm phát sinh ghi chỉ mục và giảm cơ hội HOT update trong PostgreSQL nếu cột được cập nhật nằm trong chỉ mục.
- Cột có giá trị lớn làm tăng kích thước tuple chỉ mục và có thể chạm giới hạn kích thước mục chỉ mục.
- Chỉ mục rộng có thể làm giảm số mục trên mỗi trang, tăng số trang phải đọc và làm giảm hiệu quả cache.

Chỉ thêm các cột có giá trị rõ ràng đối với truy vấn quan trọng. Nếu truy vấn chỉ trả về một vài dòng, đọc thêm vài heap page có thể rẻ hơn duy trì một chỉ mục rất rộng.

### 2.2. Partial index và điều kiện truy vấn

Partial index chỉ chứa các dòng thỏa một điều kiện. Ví dụ, nếu ứng dụng thường xuyên đọc các đơn hàng đang chờ xử lý:

```sql
CREATE INDEX idx_orders_pending_customer
ON orders (customer_id, created_at DESC)
INCLUDE (order_id, total_amount)
WHERE status = 'PENDING';
```

Truy vấn cần có điều kiện mà bộ tối ưu chứng minh được là bao hàm điều kiện của chỉ mục:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'PENDING'
  AND customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Nếu truy vấn không chứng minh được điều kiện `status = 'PENDING'`, partial index có thể không được dùng. Khả năng chứng minh phụ thuộc cách viết biểu thức và khả năng suy luận của optimizer; tham số hóa một điều kiện có thể khiến bộ tối ưu không chứng minh được predicate tại thời điểm lập kế hoạch trong một số trường hợp. Luôn xác nhận bằng `EXPLAIN`.

## 3. Vì sao PostgreSQL vẫn cần kiểm tra tính hiển thị?

Điểm quan trọng của PostgreSQL là dữ liệu được quản lý theo MVCC (Multi-Version Concurrency Control). Khi một dòng được cập nhật, PostgreSQL có thể tạo phiên bản tuple mới thay vì ghi đè trực tiếp phiên bản cũ. Các transaction khác nhau có thể nhìn thấy các phiên bản khác nhau tùy snapshot và quy tắc visibility.

Các mục trong B-tree chứa khóa và thông tin định vị tuple trong heap. Chúng không mang đầy đủ thông tin MVCC để tự quyết định phiên bản heap có hiển thị đối với snapshot của transaction hiện tại hay không. Do đó, ngay cả khi chỉ mục chứa đủ các cột đầu ra, executor vẫn có thể cần đọc heap để xác minh tuple có nhìn thấy được hay không.

Đây là lý do PostgreSQL có thể hiển thị toán tử `Index Only Scan` nhưng vẫn báo `Heap Fetches` lớn hơn 0.

### 3.1. Visibility map

PostgreSQL duy trì **visibility map (VM)** cho từng bảng. Visibility map lưu thông tin ở mức trang heap, không phải từng tuple. Hai trạng thái quan trọng là:

- **All-visible:** tất cả tuple trên trang được xác định là hiển thị đối với mọi transaction có thể cần xét theo quy tắc MVCC hiện hành. Khi bit all-visible được bật, index-only scan có thể bỏ qua việc truy cập heap để kiểm tra visibility cho các mục trên trang đó.
- **All-frozen:** các tuple trên trang đã được freeze theo quy tắc tuổi transaction của PostgreSQL, giúp giảm công việc kiểm tra transaction ID trong tương lai. All-frozen là trạng thái mạnh hơn; index-only scan cần bit all-visible, không bắt buộc bit all-frozen.

Visibility map nhỏ hơn heap rất nhiều và thường dễ nằm trong cache. Khi executor đọc một mục chỉ mục:

1. Lấy TID (tuple identifier) trỏ đến vị trí tuple trong heap.
2. Kiểm tra bit all-visible của trang heap tương ứng.
3. Nếu bit all-visible được bật, có thể dùng dữ liệu từ index mà không đọc heap để xác minh visibility.
4. Nếu bit chưa bật, executor phải truy cập heap để kiểm tra tuple có hiển thị đối với snapshot hiện tại hay không.

Sơ đồ khái quát:

```text
                 Đọc mục chỉ mục
                        |
                        v
               Lấy TID của tuple
                        |
                        v
             Kiểm tra visibility map
                  /           \
        all-visible             chưa all-visible
             |                         |
             v                         v
      Dùng giá trị index       Đọc heap để kiểm tra MVCC
             |                         |
             +------------+------------+
                          |
                          v
                Trả tuple nếu hiển thị
```

VM là thông tin tóm tắt theo trang. Nếu một trang có một tuple chưa thể xác nhận all-visible, bit all-visible của trang không được bật, dù phần lớn tuple khác trên trang đã ổn định. Vì vậy, một truy vấn chỉ đọc các dòng cũ vẫn có thể phát sinh heap fetch nếu những dòng đó nằm trên trang có cập nhật gần đây.

### 3.2. Khi nào bit all-visible bị xóa hoặc chưa được thiết lập?

Khi trang heap bị thay đổi theo cách có thể ảnh hưởng visibility, PostgreSQL phải xóa bit all-visible tương ứng để tránh bỏ qua bước kiểm tra cần thiết. Một số tình huống thường gặp:

- `INSERT`, `UPDATE` hoặc `DELETE` tạo ra thay đổi trên trang.
- Trang có phiên bản tuple mới chưa thể xác nhận hiển thị với mọi snapshot liên quan.
- VACUUM chưa đi qua trang sau thay đổi hoặc chưa thể đánh dấu trang all-visible.
- Transaction kéo dài hoặc snapshot cũ khiến một số tuple chưa thể được xem là hiển thị với mọi transaction cần xét.

Một bảng có tỷ lệ ghi cao có thể liên tục làm mất bit all-visible trên các trang nóng. Vì vậy, dù chỉ mục bao phủ toàn bộ cột cần thiết, truy vấn vẫn có thể phải đọc heap thường xuyên.

### 3.3. Vai trò của VACUUM và autovacuum

VACUUM dọn dẹp phiên bản tuple không còn cần thiết theo snapshot, cập nhật visibility map khi điều kiện cho phép và giúp duy trì sức khỏe của bảng. Autovacuum tự động thực hiện công việc bảo trì dựa trên ngưỡng và cấu hình.

Ví dụ trong môi trường kiểm thử hoặc cửa sổ bảo trì phù hợp:

```sql
VACUUM (ANALYZE) orders;
```

- `VACUUM` thực hiện dọn dẹp và cập nhật thông tin visibility có thể xác nhận.
- `ANALYZE` thu thập thống kê để optimizer ước lượng số dòng và chọn kế hoạch.

VACUUM không thể đánh dấu mọi trang all-visible trong mọi tình huống. Nó phải tôn trọng snapshot còn tồn tại và các giới hạn an toàn của transaction ID. Transaction mở lâu, prepared transaction, replication slot hoặc standby feedback giữ lại horizon cũ có thể cản trở việc dọn dẹp và làm giảm khả năng đánh dấu all-visible.

Không nên chạy VACUUM liên tục chỉ để cố đưa `Heap Fetches` về 0. Hãy kiểm tra tuổi transaction, trạng thái autovacuum, dead tuples, tốc độ ghi, thời gian chạy VACUUM và replication lag. VACUUM tiêu thụ I/O và CPU; cần duy trì lịch bảo trì phù hợp với workload.

## 4. Đọc kế hoạch thực thi và Heap Fetches

Trong PostgreSQL, dùng `EXPLAIN` để xem kế hoạch mà optimizer dự kiến. Dùng `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp để thực thi truy vấn và quan sát số dòng, thời gian cùng hoạt động buffer.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Một kết quả minh họa có thể có dạng:

```text
Index Only Scan using idx_orders_customer_created_cover on orders
  Index Cond: (customer_id = 42)
  Heap Fetches: 0
  Buffers: shared hit=8
```

Các dòng trên chỉ minh họa cấu trúc, không phải số liệu benchmark thực tế.

### 4.1. Ý nghĩa của Heap Fetches

`Heap Fetches` trong node `Index Only Scan` cho biết số lần executor phải truy cập heap để kiểm tra tuple visibility trong quá trình xử lý. Cách hiểu thực tế:

- `Heap Fetches: 0`: trong lần thực thi đó, executor không cần heap fetch để kiểm tra visibility cho các mục đã xử lý. Đây là dấu hiệu tốt cho index-only scan, nhưng không bảo đảm các lần chạy sau cũng bằng 0.
- `Heap Fetches` thấp so với số dòng xử lý: một phần trang heap đã all-visible; phần còn lại vẫn cần xác minh tại heap.
- `Heap Fetches` cao: nhiều mục phải kiểm tra heap. Có thể do trang chứa dữ liệu mới thay đổi, visibility map chưa được cập nhật, hoặc snapshot còn hạn chế việc đánh dấu all-visible.

Heap fetch không đồng nghĩa chắc chắn có physical disk read. Trang heap có thể đã nằm trong shared buffers nên lần truy cập chỉ là buffer hit. Hãy đọc cùng `Buffers: shared hit/read`, số dòng thực tế, thời gian thực thi và thống kê I/O để xác định chi phí thực tế.

### 4.2. Ví dụ kế hoạch có heap fetch

Giả sử truy vấn dùng đúng covering index nhưng bảng vừa nhận nhiều cập nhật. Kế hoạch có thể vẫn là:

```text
Index Only Scan using idx_orders_customer_created_cover on orders
  Index Cond: (customer_id = 42)
  Heap Fetches: 17
  Buffers: shared hit=24 read=2
```

Điều này cho thấy executor đã phải kiểm tra heap cho một số mục. Không thể chỉ nhìn `Index Only Scan` rồi kết luận truy vấn đã hoàn toàn tránh heap. Cũng không thể kết luận 17 lần fetch gây 17 lần đọc đĩa; hai buffer read trong ví dụ là số liệu buffer của node/kế hoạch minh họa và cần được diễn giải trong toàn bộ output.

### 4.3. Các trường khác cần đọc cùng nhau

| Trường trong EXPLAIN | Cách sử dụng khi phân tích |
|---|---|
| `actual rows` và `loops` | Xác định số dòng thực tế và số lần node được thực thi; chú ý số dòng có thể được báo theo mỗi loop tùy cách hiển thị |
| `Heap Fetches` | Đánh giá số lần cần truy cập heap để kiểm tra visibility trong index-only scan |
| `Buffers: shared hit/read` | Phân biệt trang lấy từ shared buffers và trang phải đọc vào buffer trong lần đo |
| `Planning Time` | Thời gian PostgreSQL lập kế hoạch trong lần đo |
| `Execution Time` | Thời gian thực thi được báo cáo bởi EXPLAIN ANALYZE |
| `Rows Removed by Filter` | Nhận biết nhiều mục đã đọc nhưng bị loại bởi điều kiện lọc ở node |
| Estimated rows so với actual rows | Phát hiện sai lệch thống kê có thể dẫn đến lựa chọn đường truy cập không phù hợp |

Để xem chi phí heap fetch theo bối cảnh, hãy so sánh nhiều lần chạy trên dữ liệu đại diện, bao gồm thời điểm sau bảo trì và trong giai đoạn ghi nhiều. Không xóa cache hệ thống chỉ để tạo một phép đo lạnh nếu chưa có kế hoạch kiểm thử riêng.

## 5. Các giới hạn khác của index-only scan

Visibility map là một giới hạn đặc thù quan trọng của PostgreSQL, nhưng không phải yếu tố duy nhất quyết định hiệu quả.

### 5.1. Kiểu chỉ mục phải hỗ trợ trả về giá trị

Không phải mọi access method đều có thể cung cấp lại giá trị gốc từ chỉ mục. B-tree PostgreSQL hỗ trợ index-only scan. Một số operator class của GiST và SP-GiST cũng có thể hỗ trợ. GIN thường không thể trả lại giá trị gốc đầy đủ vì một mục chỉ mục có thể đại diện cho thành phần của giá trị phức hợp.

Khả năng hỗ trợ cụ thể phụ thuộc access method và operator class. Đừng suy ra rằng một chỉ mục có thể tìm kiếm biểu thức thì cũng có thể cung cấp toàn bộ dữ liệu cho index-only scan. Xem kế hoạch thực thi để xác nhận.

### 5.2. Truy vấn cần cột không có trong chỉ mục

Nếu truy vấn cần một cột không có trong chỉ mục, executor phải lấy giá trị từ heap hoặc optimizer chọn một access path khác. Ví dụ:

```sql
SELECT order_id, created_at, status, shipping_address
FROM orders
WHERE customer_id = 42;
```

Nếu `shipping_address` không nằm trong chỉ mục, truy vấn không thể lấy toàn bộ kết quả chỉ từ chỉ mục. Có thể thêm cột này vào payload nếu nó nhỏ và workload đọc đủ quan trọng, nhưng địa chỉ thường là dữ liệu dài và thay đổi ít/ nhiều tùy ứng dụng; cần cân nhắc kích thước, chi phí ghi và giới hạn tuple trước khi làm.

### 5.3. Index-only scan có thể không phải kế hoạch rẻ nhất

Với truy vấn trả về phần lớn bảng, sequential scan có thể rẻ hơn việc đọc nhiều trang chỉ mục và xác minh nhiều heap tuple. Với truy vấn chọn lọc thấp, một index-only scan vẫn có thể đọc nhiều trang chỉ mục và phát sinh heap fetch. Với bảng nhỏ, chi phí lập kế hoạch và truy cập chỉ mục có thể không đem lại lợi ích đáng kể.

Optimizer ước lượng chi phí dựa trên thống kê, cấu hình và mô hình lưu trữ. Nếu thống kê sai, nó có thể đánh giá không đúng số dòng hoặc số trang cần đọc. Do đó cần xem actual rows, buffers và thời gian thực tế, không ép buộc index-only scan chỉ vì tên toán tử nghe có vẻ tối ưu.

### 5.4. Cập nhật payload ảnh hưởng chi phí ghi

Một covering index rộng giúp một số truy vấn đọc nhanh hơn nhưng mọi thay đổi liên quan đến cột được lập chỉ mục đều có thể tăng chi phí bảo trì. Trong PostgreSQL, cập nhật cột thuộc index (bao gồm cột `INCLUDE`) có thể ngăn HOT update cho thay đổi đó. Nếu bảng có nhiều cập nhật, việc thêm payload có thể làm tăng số lần ghi index, WAL và dung lượng lưu trữ.

Vì vậy cần đo cả read benefit và write cost. Một chỉ mục cải thiện truy vấn báo cáo 5% nhưng làm tăng đáng kể thời gian ghi ở đường giao dịch có thể không phải lựa chọn phù hợp.

## 6. Khác biệt giữa PostgreSQL và các hệ quản trị khác

Ý tưởng covering index xuất hiện ở nhiều hệ quản trị, nhưng cơ chế xác minh dữ liệu và tên toán tử không giống nhau.

| Hệ quản trị | Cơ chế/thuật ngữ thường gặp | Điểm cần lưu ý |
|---|---|---|
| PostgreSQL | `Index Only Scan`, B-tree `INCLUDE`, visibility map | Heap tuple visibility thuộc MVCC; trang cần all-visible để bỏ qua heap fetch |
| SQL Server | Covering nonclustered index, `INCLUDE` columns | Nonclustered index có thể cung cấp cột cần thiết; cách xử lý row versioning và lookup phụ thuộc storage engine/isolation |
| MySQL InnoDB | Covering index | Secondary index có khóa chính và cột chỉ mục; cơ chế MVCC/consistent read có thể vẫn cần truy cập clustered record trong một số trường hợp |

Không áp dụng khái niệm visibility map của PostgreSQL cho SQL Server hoặc MySQL. Khi chuyển bài học sang hệ quản trị khác, hãy tra cơ chế MVCC, cấu trúc chỉ mục và loại operator trong tài liệu của đúng phiên bản.

## 7. Quy trình thiết kế và kiểm chứng covering index

Thực hiện theo quy trình sau để tránh tạo chỉ mục rộng mà không đem lại lợi ích tương xứng.

**Bước 1 — Chọn truy vấn mục tiêu.** Dùng thống kê workload để tìm câu SQL có tần suất, độ trễ hoặc tổng thời gian tiêu thụ tài nguyên đáng kể. Ghi nhận tham số, số dòng trả về, tần suất đọc/ghi và SLA.

**Bước 2 — Liệt kê cột cần thiết.** Xem `SELECT`, `WHERE`, `JOIN`, `ORDER BY`, `GROUP BY` và biểu thức. Phân biệt cột cần làm khóa tìm kiếm/sắp xếp với cột chỉ cần trả về.

**Bước 3 — Thiết kế chỉ mục nhỏ nhất có ích.** Chọn thứ tự khóa theo điều kiện lọc và thứ tự truy cập; cân nhắc `INCLUDE` cho cột payload. Xem chỉ mục hiện có để tránh tạo cấu trúc trùng lặp.

**Bước 4 — Kiểm tra tính tương thích.** Xác minh access method/operator class hỗ trợ index-only scan, truy vấn đáp ứng điều kiện của partial index và mọi cột cần thiết có thể lấy từ chỉ mục.

**Bước 5 — Đọc kế hoạch trước khi thay đổi.** Lưu output `EXPLAIN (ANALYZE, BUFFERS)` làm baseline. Ghi nhận node truy cập, estimated/actual rows, buffers, heap fetches nếu đã có index-only scan, planning time và execution time.

**Bước 6 — Tạo chỉ mục trong môi trường kiểm thử hoặc theo quy trình triển khai.** Dùng dữ liệu có phân bố gần production. Với bảng lớn, cân nhắc phương thức tạo chỉ mục ít ảnh hưởng đến hoạt động ghi theo phiên bản và quy trình vận hành của PostgreSQL; không tự ý thay đổi production.

**Bước 7 — Kiểm tra sau tạo chỉ mục và sau VACUUM.** Xem optimizer có chọn index-only scan không, `Heap Fetches` là bao nhiêu, số buffer đọc/đụng cache thay đổi ra sao. Đo ở cả dữ liệu ổn định và giai đoạn ghi nhiều.

**Bước 8 — Đánh giá toàn workload.** Đo latency p50/p95/p99, throughput đọc/ghi, CPU, I/O, WAL, kích thước chỉ mục và thời gian bảo trì. Kiểm tra các truy vấn khác có bị kế hoạch xấu đi không.

**Bước 9 — Giữ hoặc loại bỏ chỉ mục theo bằng chứng.** Chỉ giữ cấu trúc có lợi ích rõ ràng so với chi phí lưu trữ, ghi và vận hành. Ghi lại truy vấn mục tiêu, số liệu baseline và kết quả sau thay đổi.

## 8. Ví dụ thực tế: bảng đơn hàng có dữ liệu thay đổi thường xuyên

Giả sử hệ thống thương mại điện tử có bảng `orders` với hàng chục triệu dòng. Trang khách hàng thường lấy 20 đơn mới nhất. Một covering index trên `customer_id`, `created_at` và các cột đầu ra giúp PostgreSQL tránh truy cập heap khi trang heap liên quan đã all-visible.

Ngay sau đợt nhập đơn lớn, nhiều trang mới hoặc vừa cập nhật chưa có bit all-visible. Kế hoạch vẫn có thể là `Index Only Scan`, nhưng `Heap Fetches` tăng. Sau khi autovacuum hoặc VACUUM xử lý các trang đủ điều kiện, số heap fetch có thể giảm. Nếu transaction kéo dài vẫn giữ snapshot cũ hoặc bảng liên tục ghi, một số trang chưa thể được đánh dấu all-visible và heap fetch tiếp tục xuất hiện.

Một quy trình đo minh họa:

1. Ghi lại `EXPLAIN (ANALYZE, BUFFERS)` trước bảo trì và lưu số `Heap Fetches`, buffers, actual rows cùng execution time.
2. Kiểm tra autovacuum và transaction cũ để hiểu vì sao visibility map chưa phản ánh nhiều trang all-visible.
3. Trong môi trường kiểm thử hoặc cửa sổ bảo trì phù hợp, chạy `VACUUM (ANALYZE) orders`.
4. Chạy lại cùng truy vấn, cùng nhóm tham số và điều kiện tải; so sánh heap fetches và buffer activity.
5. Lặp lại phép đo trong thời gian có cập nhật để đánh giá độ ổn định của lợi ích.

Nếu số heap fetch giảm sau VACUUM nhưng truy vấn không nhanh hơn, có thể chi phí chính nằm ở đọc index, trả nhiều dòng, CPU, network hoặc chờ khác. Nếu heap fetch vẫn cao, hãy xem transaction horizon, tần suất ghi và các trang nóng trước khi tăng payload hoặc thay đổi index.

## 9. Những nhầm lẫn thường gặp

- **“Chỉ mục có đủ cột thì PostgreSQL không đọc heap.”** Còn phải xét visibility map; trang chưa all-visible có thể buộc executor kiểm tra tuple trong heap.
- **“Thấy node `Index Only Scan` nghĩa là Heap Fetches bằng 0.”** Hai thông tin khác nhau. Hãy đọc trường `Heap Fetches` trong kế hoạch thực tế.
- **“Heap Fetches là số lần đọc đĩa.”** Heap fetch là lần truy cập heap để kiểm tra visibility; trang có thể đã nằm trong shared buffers.
- **“VACUUM sẽ làm mọi trang all-visible ngay lập tức.”** Transaction cũ, dữ liệu thay đổi liên tục và giới hạn visibility có thể ngăn một số trang được đánh dấu.
- **“All-frozen là điều kiện bắt buộc cho index-only scan.”** Điều kiện liên quan trực tiếp là all-visible; all-frozen phục vụ thêm cho quản lý transaction ID.
- **“Càng nhiều cột INCLUDE càng tốt.”** Chỉ mục rộng tăng dung lượng, cache footprint, WAL và chi phí duy trì khi ghi.
- **“Index-only scan luôn nhanh hơn sequential scan.”** Khi truy vấn đọc phần lớn bảng hoặc chỉ mục có nhiều heap fetch, sequential scan có thể rẻ hơn.
- **“Có thể dùng cùng cách giải thích visibility map cho mọi database.”** Visibility map là cơ chế của PostgreSQL; các hệ quản trị khác có cơ chế riêng.

## 10. Checklist đánh giá truy vấn chỉ từ chỉ mục

- [ ] Đã xác định truy vấn quan trọng từ số liệu workload và SLA.
- [ ] Đã liệt kê cột trong `SELECT`, `WHERE`, `JOIN`, `ORDER BY`, `GROUP BY` và biểu thức.
- [ ] Đã phân biệt cột khóa chỉ mục với cột payload `INCLUDE`.
- [ ] Đã xác nhận access method/operator class có thể trả giá trị cần thiết.
- [ ] Đã kiểm tra partial index predicate và điều kiện truy vấn nếu có.
- [ ] Đã xem node thực thi và không chỉ dựa vào tên `Index Only Scan`.
- [ ] Đã đọc `Heap Fetches`, buffers, actual rows, loops và thời gian thực thi.
- [ ] Đã kiểm tra VACUUM/autovacuum, transaction kéo dài và trạng thái dữ liệu ghi nhiều.
- [ ] Đã đo cả lợi ích đọc lẫn chi phí ghi, WAL, dung lượng và bảo trì chỉ mục.
- [ ] Đã so sánh trước/sau trên dữ liệu, tham số và mức tải đại diện.

## Kết luận

Truy vấn chỉ từ chỉ mục có thể giảm truy cập heap khi chỉ mục cung cấp đủ giá trị cần thiết và bộ tối ưu đánh giá đường truy cập này có lợi. Trong PostgreSQL, MVCC khiến index entry không tự mang đủ thông tin để xác định tuple có hiển thị với snapshot hiện tại hay không. Visibility map cho phép bỏ qua heap khi trang được đánh dấu all-visible; nếu bit này chưa được thiết lập, executor phải đọc heap để xác minh và `Heap Fetches` có thể tăng.

Muốn khai thác covering index hiệu quả, hãy thiết kế khóa và payload theo truy vấn thực tế, duy trì VACUUM phù hợp, theo dõi transaction kéo dài và đọc kế hoạch cùng buffer statistics. Đo cả tải đọc lẫn chi phí ghi trước và sau thay đổi để xác định chỉ mục có thực sự cải thiện hiệu năng tổng thể hay không.
