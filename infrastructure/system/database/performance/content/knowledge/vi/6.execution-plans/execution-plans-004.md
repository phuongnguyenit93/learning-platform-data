# Nhận diện quét bảng, quét chỉ mục, tìm kiếm chỉ mục và truy xuất hàng

## Vai trò của kế hoạch thực thi

Kế hoạch thực thi (execution plan) mô tả cách hệ quản trị cơ sở dữ liệu dự định hoặc đã thực hiện để lấy dữ liệu và trả kết quả cho một câu SQL. Kế hoạch cho biết hệ thống chọn quét bảng, quét chỉ mục, tìm kiếm theo khóa, kết hợp nhiều nguồn dữ liệu, sắp xếp, tổng hợp hay truy xuất thêm hàng từ bảng gốc. Đọc đúng kế hoạch giúp xác định dữ liệu được đọc ở đâu, bao nhiêu hàng được xử lý và chi phí nào đang chi phối thời gian truy vấn.

Trong tối ưu hiệu năng cơ sở dữ liệu, không thể kết luận một truy vấn chậm chỉ từ độ dài câu SQL hoặc số lượng chỉ mục hiện có. Cần kết hợp tải thực tế, thống kê, kế hoạch thực thi, cơ chế truy cập dữ liệu, mức sử dụng bộ nhớ và I/O. Một kế hoạch có thao tác quét không mặc nhiên là xấu; một kế hoạch có thao tác tìm kiếm chỉ mục cũng không mặc nhiên là tốt. Quyết định đúng phụ thuộc vào số hàng cần đọc, độ chọn lọc của điều kiện, kích thước dữ liệu, thứ tự truy cập và chi phí truy xuất hàng.

Bài học này tập trung phân biệt bốn nhóm thao tác thường gặp:

- **Quét bảng (table scan):** đọc các trang dữ liệu của bảng để tìm hàng thỏa điều kiện.
- **Quét chỉ mục (index scan):** duyệt một phần hoặc toàn bộ cấu trúc chỉ mục theo thứ tự của chỉ mục.
- **Tìm kiếm chỉ mục (index seek hoặc thao tác tìm kiếm tương ứng theo thuật ngữ của từng hệ quản trị):** định vị một khóa hoặc một khoảng khóa trong chỉ mục, rồi đọc các mục phù hợp.
- **Truy xuất hàng (row lookup, key lookup hoặc bookmark lookup):** dùng khóa hoặc địa chỉ hàng lấy từ chỉ mục để đọc thêm dữ liệu của hàng trong cấu trúc lưu trữ chính.

Các tên toán tử có thể khác nhau giữa SQL Server, PostgreSQL, MySQL và những hệ quản trị khác. Cần đọc ý nghĩa của thao tác trong hệ quản trị đang dùng, thay vì suy diễn chỉ từ tên gọi.

## Cách dữ liệu được tổ chức và truy cập

### Bảng và trang dữ liệu

Cơ sở dữ liệu thường lưu dữ liệu theo trang (page hoặc block). Một bảng có thể gồm nhiều trang; mỗi trang chứa nhiều hàng. Khi cần đọc hàng, hệ quản trị phải xác định trang chứa hàng đó, đưa trang vào bộ nhớ nếu chưa có sẵn, rồi tìm vị trí hàng bên trong trang.

Quét bảng thường đi qua nhiều trang của bảng. Nếu bảng nhỏ hoặc truy vấn cần phần lớn hàng, việc đọc tuần tự các trang có thể hiệu quả hơn tìm từng hàng riêng lẻ qua chỉ mục. Nếu bảng lớn nhưng chỉ cần vài hàng, quét toàn bảng có thể đọc lượng dữ liệu không cần thiết.

Không nên đồng nhất quét bảng với việc luôn đọc đĩa vật lý. Trang có thể đã nằm trong buffer cache hoặc bộ nhớ hệ điều hành. Kế hoạch có thao tác quét vẫn có thể được phục vụ phần lớn từ bộ nhớ. Khi phân tích chi phí, hãy phân biệt số trang được truy cập, logical reads, physical reads và thời gian chờ I/O theo khả năng quan sát của hệ quản trị.

### Chỉ mục B-tree

Nhiều chỉ mục quan hệ phổ biến sử dụng cấu trúc B-tree hoặc biến thể B+ tree. Cấu trúc này được tổ chức thành các mức:

1. Trang gốc (root) định hướng tìm kiếm.
2. Các trang nhánh (intermediate pages) dẫn đến vùng khóa phù hợp.
3. Các trang lá (leaf pages) chứa khóa chỉ mục và thông tin định vị hàng, hoặc chứa thêm các cột dữ liệu tùy thiết kế.

Tìm kiếm một khóa thường đi từ gốc xuống các trang nhánh rồi đến trang lá. Sau khi tìm được khóa, hệ quản trị có thể lấy dữ liệu ngay từ chỉ mục nếu chỉ mục chứa đủ cột cần thiết, hoặc phải truy xuất hàng trong bảng.

Chỉ mục không miễn phí. Mỗi chỉ mục chiếm dung lượng, cần được duy trì khi dữ liệu thay đổi và có thể làm tăng chi phí INSERT, UPDATE, DELETE. Chỉ mục quá rộng cũng làm tăng số trang phải lưu trữ và đọc.

Một số hệ quản trị còn có loại chỉ mục khác như hash, bitmap, GiST, GIN hoặc full-text. Cơ chế tìm kiếm và toán tử kế hoạch của chúng có thể khác B-tree. Những nguyên tắc về độ chọn lọc, chi phí đọc và việc lấy dữ liệu hàng vẫn hữu ích, nhưng phải đối chiếu với tài liệu của loại chỉ mục cụ thể.

### Vị trí hàng trong cấu trúc lưu trữ

Chỉ mục cần một cách tham chiếu đến hàng tương ứng. Cách tham chiếu này khác nhau tùy hệ quản trị và kiểu bảng:

- Với bảng dạng heap, chỉ mục phụ có thể lưu một row identifier hoặc địa chỉ vật lý để tìm hàng trong heap.
- Với bảng có chỉ mục clustered, khóa của chỉ mục clustered có thể xác định vị trí dữ liệu hàng; các chỉ mục phụ thường giữ khóa clustered làm phần định vị.
- Trong InnoDB, trang lá của secondary index chứa khóa chỉ mục và khóa chính của hàng; việc lấy cột không có trong secondary index có thể cần tra cứu lại clustered index theo khóa chính.
- PostgreSQL có thể dùng vị trí tuple trong heap (TID/CTID) từ chỉ mục để truy cập hàng; Index Only Scan vẫn cần kiểm tra khả năng hiển thị phiên bản hàng theo cơ chế MVCC.

Vì vậy, khi thấy một toán tử truy xuất hàng sau thao tác chỉ mục, hãy xem đó là một bước bổ sung trong đường đi dữ liệu. Không giả định mọi hệ quản trị đều dùng cùng một loại row locator.

## Phân biệt các thao tác truy cập

### Quét bảng (Table Scan hoặc Sequential Scan)

Quét bảng đọc các trang của bảng để kiểm tra hàng nào thỏa điều kiện. Tùy hệ quản trị, tên thao tác có thể là Table Scan, Seq Scan hoặc Full Table Scan.

Quét bảng thường hợp lý khi:

- Bảng nhỏ, số trang ít.
- Truy vấn cần phần lớn hàng hoặc phần lớn cột.
- Điều kiện lọc có độ chọn lọc thấp, tức trả về tỷ lệ lớn hàng.
- Chỉ mục không phù hợp với điều kiện lọc hoặc thứ tự truy cập.
- Đọc tuần tự ít tốn kém hơn nhiều lần truy xuất ngẫu nhiên qua chỉ mục.
- Thống kê cho thấy chi phí dùng chỉ mục cao hơn chi phí quét.

Ví dụ:

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE status <> 'CANCELLED';
~~~

Nếu phần lớn đơn hàng không bị hủy, truy vấn có thể cần đọc gần như toàn bộ bảng. Một chỉ mục chỉ trên status có thể không giúp nhiều, nhất là khi mỗi hàng phù hợp còn cần nhiều cột khác từ bảng. Hệ quản trị có thể chọn quét bảng vì đây là đường đi ít tốn kém hơn.

Quét bảng có thể đáng nghi khi bảng rất lớn nhưng truy vấn chỉ trả về một tỷ lệ rất nhỏ hàng, và có chỉ mục phù hợp mà kế hoạch không sử dụng. Khi đó cần kiểm tra điều kiện lọc, kiểu dữ liệu, thống kê, độ chọn lọc, phân vùng và chi phí thực tế trước khi kết luận.

### Quét chỉ mục (Index Scan)

Quét chỉ mục duyệt các mục trong cấu trúc chỉ mục. Có thể là toàn bộ chỉ mục hoặc một phần liên tục của nó. Vì chỉ mục thường nhỏ hơn bảng và có thể chứa các cột cần thiết, quét chỉ mục đôi khi rẻ hơn quét bảng.

Quét chỉ mục có thể phù hợp khi:

- Chỉ mục hẹp hơn đáng kể so với bảng.
- Truy vấn cần các cột có sẵn trong chỉ mục.
- Thứ tự của chỉ mục đáp ứng ORDER BY hoặc hỗ trợ một bước tiếp theo.
- Điều kiện lọc cho phép bỏ qua một số vùng, dù không định vị đến một khóa đơn lẻ.
- Hệ quản trị có thể duyệt các mục theo thứ tự cần thiết mà không phải sort lại.

Ví dụ, một chỉ mục trên (created_at, order_id) có thể được duyệt để lấy các đơn hàng theo thời gian trong một khoảng rộng. Nếu truy vấn cần nhiều cột không có trong chỉ mục, hệ quản trị có thể phải truy xuất hàng cho từng mục phù hợp.

Tên Index Scan không có cùng ý nghĩa chính xác ở mọi sản phẩm. Trong SQL Server, Index Scan thường duyệt các trang lá của chỉ mục. Trong PostgreSQL, Index Scan thường là một thao tác dùng điều kiện để lấy TID từ chỉ mục rồi đọc hàng trong heap; nó không nhất thiết có nghĩa duyệt toàn bộ chỉ mục. Hãy xem điều kiện index condition, số hàng, số trang và toán tử con thay vì chỉ dựa vào nhãn.

### Tìm kiếm chỉ mục (Index Seek)

Index Seek là cách gọi phổ biến, đặc biệt trong SQL Server, cho thao tác định vị một khóa hoặc một khoảng khóa trong chỉ mục dựa trên điều kiện tìm kiếm. PostgreSQL thường thể hiện các thao tác tương ứng bằng Index Scan với Index Cond; MySQL có các access type như ref, range hoặc const tùy tình huống.

Ví dụ:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE order_id = 742018;
~~~

Nếu order_id là khóa chính hoặc có chỉ mục phù hợp, hệ quản trị có thể đi qua các mức của chỉ mục để định vị hàng cần tìm. Với B-tree, tìm một khóa chính xác thường có chi phí tăng chậm theo số lượng khóa nhờ cấu trúc cân bằng.

Tìm kiếm theo khoảng cũng có thể sử dụng chỉ mục:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00';
~~~

Nếu chỉ mục bắt đầu bằng created_at, hệ quản trị có thể định vị đầu khoảng rồi duyệt các mục cho đến cuối khoảng. Tuy vậy, nếu tháng đó chứa phần lớn dữ liệu, quét chỉ mục kèm nhiều lần truy xuất hàng có thể đắt hơn quét bảng.

**Index Seek không phải bằng chứng tự động rằng truy vấn đã tối ưu.** Một seek có thể trả về hàng trăm nghìn mục, sau đó phát sinh rất nhiều lần lookup. Cần xem số hàng thực tế, số lần lặp, số trang đọc và tổng thời gian.

### Truy xuất hàng (Row Lookup, Key Lookup hoặc Bookmark Lookup)

Khi chỉ mục dùng để tìm các khóa nhưng không chứa đủ cột truy vấn cần, hệ quản trị phải quay lại cấu trúc lưu trữ chính để lấy phần dữ liệu còn thiếu. Bước này có thể được gọi là Key Lookup, RID Lookup, Bookmark Lookup hoặc heap fetch tùy sản phẩm.

Ví dụ:

~~~sql
SELECT order_id, customer_id, created_at, total_amount, shipping_address
FROM orders
WHERE status = 'READY';
~~~

Giả sử có chỉ mục trên status nhưng không chứa shipping_address và các cột còn lại. Hệ quản trị có thể tìm các mục status = 'READY' trong chỉ mục rồi truy xuất từng hàng để lấy dữ liệu đầy đủ.

Truy xuất hàng thường có chi phí đáng kể khi:

- Điều kiện lọc trả về nhiều hàng.
- Mỗi hàng phù hợp cần một lần truy cập riêng vào bảng hoặc clustered index.
- Các hàng nằm rải rác trên nhiều trang, gây nhiều truy cập ngẫu nhiên.
- Buffer cache không chứa sẵn các trang cần thiết.
- Toán tử lookup được lặp lại rất nhiều lần trong Nested Loops.

Một lookup cho một hàng thường không đáng lo. Hàng chục nghìn lookup trong một truy vấn có thể tạo ra nhiều logical reads và độ trễ đáng kể. Khi thấy lookup, cần xác định số lần thực hiện và lượng dữ liệu phải lấy thêm.

## So sánh đường đi dữ liệu

| Thao tác | Cách tìm dữ liệu | Trường hợp thường phù hợp | Điều cần kiểm tra |
|---|---|---|---|
| Table/Sequential Scan | Duyệt các trang dữ liệu của bảng | Bảng nhỏ hoặc cần phần lớn hàng | Số trang, số hàng đọc, số hàng trả về |
| Index Scan | Duyệt các mục của chỉ mục theo thứ tự | Chỉ mục hẹp, cần nhiều mục hoặc tận dụng thứ tự | Phạm vi duyệt, số hàng, có phải lookup không |
| Index Seek / Index Cond | Định vị khóa hoặc khoảng khóa bằng điều kiện | Điều kiện chọn lọc, khóa hoặc khoảng phù hợp | Seek predicate, residual predicate, số hàng thực tế |
| Row/Key/Bookmark Lookup | Dùng row locator để lấy thêm dữ liệu hàng | Chỉ mục tìm được hàng nhưng thiếu cột cần | Số lần lookup, logical reads, chi phí truy cập ngẫu nhiên |
| Index Only / Covering Access | Trả kết quả từ dữ liệu có trong chỉ mục khi điều kiện cho phép | Chỉ mục chứa đủ cột và hệ quản trị xác nhận dữ liệu đọc được | Độ rộng chỉ mục, visibility hoặc điều kiện nhất quán |

Các thao tác này có thể xuất hiện kết hợp. Ví dụ, một kế hoạch có thể tìm kiếm trên chỉ mục, dùng Nested Loops để truy xuất hàng nhiều lần, rồi sắp xếp kết quả. Khi đánh giá, hãy xem toàn bộ cây kế hoạch và luồng dữ liệu, không chỉ một toán tử nổi bật.

## Hiểu điều kiện tìm kiếm và điều kiện lọc còn lại

### Seek Predicate và Residual Predicate

Một điều kiện có thể được dùng để định vị vùng khóa trong chỉ mục; đó là phần điều kiện truy cập (seek predicate hoặc index condition). Một điều kiện khác có thể chỉ được kiểm tra sau khi đã đọc mục hoặc hàng; đó là residual predicate hoặc filter.

Ví dụ có chỉ mục B-tree trên (customer_id, created_at):

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 315
  AND created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
  AND total_amount > 1000000;
~~~

Hai điều kiện customer_id và khoảng created_at có thể định vị một vùng khóa liên tục. Điều kiện total_amount có thể không được dùng để thu hẹp vùng tìm kiếm nếu cột này không thuộc chỉ mục; hệ quản trị phải đọc mục hoặc hàng rồi lọc tiếp.

Nếu một truy vấn đọc 50.000 hàng nhưng chỉ trả về 120 hàng, cần xem phần chênh lệch đến từ residual predicate, ước lượng sai hay điều kiện chưa được hỗ trợ bởi chỉ mục. Đưa thêm cột vào chỉ mục có thể giảm số lần truy xuất hàng, nhưng cũng làm chỉ mục rộng hơn và tăng chi phí ghi. Hãy đánh giá bằng workload thực tế.

### SARGable và điều kiện có thể dùng chỉ mục

Một điều kiện SARGable (Search ARGument Able) có dạng giúp hệ quản trị tìm kiếm hiệu quả trên chỉ mục. Khả năng sử dụng chỉ mục còn phụ thuộc loại chỉ mục, thứ tự cột, kiểu dữ liệu, collation, thống kê và cách viết biểu thức.

Ví dụ điều kiện trực tiếp trên cột thường dễ dùng chỉ mục hơn:

~~~sql
-- Có thể dùng chỉ mục trên created_at
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00'
~~~

Một biểu thức áp dụng hàm lên cột có thể khiến chỉ mục thông thường khó được dùng để định vị:

~~~sql
-- Cú pháp minh họa kiểu MySQL; hệ quản trị khác có thể dùng CAST hoặc biểu thức tương đương
WHERE DATE(created_at) = '2026-11-19'
~~~

Có thể viết lại thành khoảng thời gian như ví dụ đầu, hoặc dùng expression/function-based index nếu hệ quản trị hỗ trợ và workload thực sự cần. Không áp dụng máy móc: cách viết lại phải giữ đúng ngữ nghĩa, múi giờ và quy tắc biên thời gian.

Một số nguyên nhân khiến điều kiện không tận dụng được chỉ mục như mong đợi:

- Ép kiểu ngầm giữa cột và tham số, đặc biệt khi chuyển đổi được áp dụng lên cột.
- Hàm hoặc phép tính trên cột không có expression index tương ứng.
- So khớp chuỗi có wildcard ở đầu, ví dụ LIKE '%abc', với B-tree thông thường.
- Dùng sai collation hoặc phép so sánh không tương thích với định nghĩa chỉ mục.
- Chỉ mục ghép có thứ tự cột không phù hợp với điều kiện truy vấn.
- Biểu thức OR hoặc điều kiện phức tạp khiến bộ tối ưu chọn đường đi khác; một số hệ quản trị có thể kết hợp nhiều chỉ mục.
- Thống kê lỗi thời khiến hệ quản trị ước lượng sai số hàng.

Không phải mọi hàm, OR hoặc LIKE đều làm mất khả năng dùng chỉ mục. Hãy kiểm tra toán tử và kế hoạch thực tế của hệ quản trị đang sử dụng.

## Thiết kế chỉ mục ghép và chỉ mục bao phủ

### Thứ tự cột trong chỉ mục ghép

Với B-tree ghép trên (A, B, C), nhiều hệ quản trị có thể tìm kiếm hiệu quả theo tiền tố trái của khóa, chẳng hạn A hoặc A kết hợp B. Điều kiện chỉ trên C thường không tận dụng được phần đầu của chỉ mục để định vị một vùng liên tục, dù hệ quản trị có thể chọn các chiến lược khác như skip scan tùy sản phẩm và phiên bản.

Giả sử truy vấn thường dùng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 315
  AND status = 'READY'
ORDER BY created_at DESC;
~~~

Một chỉ mục ghép có thể cân nhắc là (customer_id, status, created_at), tùy phân bố dữ liệu và khả năng xử lý thứ tự của hệ quản trị. Hai cột điều kiện bằng thường được đặt trước cột phạm vi hoặc thứ tự trong nhiều tình huống, nhưng thứ tự tối ưu phải được xác nhận bằng workload và kế hoạch. Không có quy tắc “cột có độ chọn lọc cao nhất luôn đứng đầu” áp dụng cho mọi truy vấn và mọi hệ quản trị.

Cần xem cả các truy vấn khác dùng cùng chỉ mục. Chỉ mục tối ưu cho một câu lệnh có thể không hữu ích cho các câu lệnh có điều kiện khác hoặc tạo chi phí ghi quá lớn.

### Chỉ mục bao phủ (Covering Index)

Một chỉ mục bao phủ chứa các cột cần cho điều kiện tìm kiếm, phép nối, sắp xếp và phần kết quả của truy vấn, giúp hệ quản trị có thể trả dữ liệu mà không phải truy xuất hàng ở bảng chính trong một số điều kiện.

Ví dụ truy vấn cần customer_id, status, created_at, order_id và total_amount. Có thể thiết kế chỉ mục chứa các cột phù hợp, tùy cú pháp hỗ trợ:

~~~sql
-- Cú pháp minh họa kiểu SQL Server
CREATE INDEX IX_orders_customer_status_created
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_id, total_amount);
~~~

Trong PostgreSQL, có thể dùng INCLUDE cho cột payload ở một số loại chỉ mục; trong các hệ quản trị khác, cách lưu cột bổ sung khác nhau. Chỉ mục bao phủ không phải lúc nào cũng loại bỏ hoàn toàn việc đọc bảng. Ví dụ PostgreSQL cần kiểm tra visibility map để xác định phiên bản hàng có hiển thị với snapshot hiện tại hay không; nếu trang chưa được đánh dấu all-visible, hệ quản trị vẫn có thể phải truy cập heap.

Lợi ích của chỉ mục bao phủ:

- Giảm số lần truy xuất hàng từ cấu trúc bảng.
- Giảm logical reads hoặc truy cập ngẫu nhiên trong các workload phù hợp.
- Có thể tránh một số thao tác lookup lặp lại.
- Có thể hỗ trợ trả kết quả theo thứ tự chỉ mục mà không cần sort bổ sung.

Đánh đổi:

- Chỉ mục rộng hơn, chiếm nhiều dung lượng và bộ nhớ cache.
- Ghi và cập nhật tốn kém hơn vì nhiều cột phải được duy trì.
- Cột thay đổi thường xuyên có thể làm tăng page split, write amplification hoặc giảm cơ hội tối ưu lưu trữ.
- Chỉ mục bao phủ quá rộng làm tăng chi phí bảo trì và có thể gây hại tổng thể.

Chỉ thêm cột khi có bằng chứng truy vấn thường xuyên cần chúng và chi phí lookup đáng kể. Không sao chép mọi cột của bảng vào chỉ mục chỉ để loại một toán tử khỏi kế hoạch.

## Đọc kế hoạch thực thi có ước lượng và số liệu thực tế

### Kế hoạch ước lượng và kế hoạch thực tế

Kế hoạch ước lượng (estimated plan) được bộ tối ưu tạo ra dựa trên câu SQL, schema, chỉ mục, thống kê và ước lượng cardinality. Kế hoạch thực tế (actual plan) được ghi nhận khi câu lệnh chạy, thường bổ sung số hàng thực tế, số lần lặp, thời gian hoặc thông tin I/O tùy hệ quản trị.

Hãy tập trung vào các thông tin sau:

- **Estimated Rows:** số hàng bộ tối ưu dự đoán toán tử sẽ tạo ra.
- **Actual Rows:** số hàng toán tử thực sự tạo ra.
- **Rows Read:** số hàng hoặc mục đã đọc trước khi lọc, nếu hệ quản trị cung cấp.
- **Loops/Executions:** số lần toán tử được thực hiện.
- **Logical Reads và Physical Reads:** số lần đọc trang từ buffer hoặc lưu trữ theo cách hệ quản trị báo cáo.
- **Predicate/Filter:** điều kiện nào được dùng để định vị, điều kiện nào lọc sau.
- **Actual Time:** thời gian đo tại toán tử, cần hiểu cách hệ quản trị cộng dồn hoặc báo cáo thời gian.
- **Memory Grant, Sort/Hash Spill:** bộ nhớ được cấp và dấu hiệu tràn ra lưu trữ tạm nếu có.

Nếu Estimated Rows khác xa Actual Rows, bộ tối ưu có thể chọn sai kiểu join hoặc đường truy cập. Nguyên nhân có thể là thống kê lỗi thời, dữ liệu lệch, tương quan giữa các cột không được mô hình hóa, tham số không đại diện hoặc biểu thức khó ước lượng.

Không chỉ nhìn phần trăm cost trong giao diện kế hoạch. Nhiều sản phẩm hiển thị cost tương đối theo mô hình nội bộ của optimizer, không phải thời gian thực tế và không nên so sánh trực tiếp giữa các hệ quản trị. Hãy đối chiếu số hàng, số trang đọc, thời gian, CPU, I/O và số lần thực thi.

### Phát hiện lookup quá nhiều

Giả sử kế hoạch có Index Seek trả về 40.000 khóa, sau đó Key Lookup được gọi 40.000 lần để lấy các cột còn thiếu. Dù thao tác tìm kiếm ban đầu rất nhanh, tổng chi phí lookup có thể lớn hơn quét bảng hoặc dùng chỉ mục bao phủ.

Các dấu hiệu cần chú ý:

- Số lần thực thi của toán tử lookup rất cao.
- Logical reads tăng mạnh ở bảng hoặc clustered index được tra cứu.
- Số hàng đọc lớn hơn nhiều số hàng cuối cùng trả về.
- Thời gian tăng khi lượng dữ liệu phù hợp tăng.
- Lookup gây nhiều truy cập ngẫu nhiên hoặc cache miss.
- Kế hoạch dùng Nested Loops với nhánh trong được gọi lặp lại nhiều lần.

Giải pháp có thể là tạo chỉ mục bao phủ, giảm số hàng trước khi lookup, viết lại truy vấn để chỉ lấy cột cần thiết hoặc chấp nhận scan nếu tỷ lệ hàng phù hợp lớn. Phải đo lại cả chi phí ghi và dung lượng sau khi thay đổi.

### Bitmap và các chiến lược kết hợp chỉ mục

Một số hệ quản trị có thể kết hợp nhiều chỉ mục để tìm tập hàng thỏa nhiều điều kiện. PostgreSQL có thể dùng Bitmap Index Scan kết hợp Bitmap Heap Scan. Cách này gom vị trí hàng trước rồi đọc các trang heap, có thể hiệu quả khi mỗi điều kiện riêng lẻ trả về nhiều mục và việc gom theo trang giúp giảm truy cập ngẫu nhiên.

Không nên coi Bitmap Heap Scan là dấu hiệu lỗi. Hãy kiểm tra số trang heap được đọc, số hàng bị loại sau khi truy xuất, exact/lossy bitmap nếu có và lượng bộ nhớ sử dụng. Nếu bitmap trở thành lossy hoặc cần recheck nhiều hàng, hiệu năng có thể bị ảnh hưởng.

## Ví dụ đọc và cải thiện một kế hoạch

Giả sử bảng orders có hàng chục triệu hàng. Ứng dụng thường truy vấn danh sách đơn hàng đã sẵn sàng của một khách hàng trong một khoảng thời gian:

~~~sql
SELECT order_id, created_at, total_amount, shipping_address
FROM orders
WHERE customer_id = 315
  AND status = 'READY'
  AND created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00'
ORDER BY created_at DESC;
~~~

Một kế hoạch chưa phù hợp có thể có các dấu hiệu:

- Quét bảng hoặc quét một chỉ mục rộng.
- Đọc hàng triệu mục nhưng chỉ trả về vài trăm hàng.
- Sort lớn trước khi trả kết quả.
- Truy xuất hàng lặp lại cho nhiều mục chỉ mục.
- Estimated Rows thấp hơn nhiều Actual Rows.

Trước khi tạo chỉ mục, cần kiểm tra thống kê và phân bố dữ liệu. Có thể truy vấn của một khách hàng lớn trả về hàng trăm nghìn đơn, trong khi khách hàng khác chỉ có vài chục đơn. Tham số 315 có thể không đại diện cho mọi trường hợp.

Một chỉ mục ứng viên có thể bắt đầu bằng customer_id, status rồi đến created_at để hỗ trợ điều kiện bằng và khoảng thời gian. Có thể đưa order_id, total_amount và shipping_address vào phần dữ liệu bao phủ nếu workload chứng minh lookup đang tốn kém. Tuy nhiên shipping_address có thể là cột rộng; đưa nó vào chỉ mục có thể làm chỉ mục lớn đáng kể. Có thể cần cân nhắc lấy địa chỉ sau khi đã xác định trang kết quả nhỏ, tùy yêu cầu ứng dụng.

Sau khi tạo chỉ mục hoặc sửa truy vấn, hãy kiểm tra:

1. Kế hoạch có dùng đúng điều kiện tìm kiếm trên các cột mong muốn không?
2. Số hàng đọc và số hàng trả về có gần nhau hơn không?
3. Sort có được loại bỏ hoặc giảm đáng kể không?
4. Key Lookup hoặc heap fetch có giảm không?
5. Estimated Rows có gần Actual Rows hơn không?
6. Logical reads, CPU và p95/p99 có giảm trong workload đại diện không?
7. INSERT/UPDATE/DELETE có chậm hơn không?
8. Dung lượng chỉ mục, cache và tác động lên truy vấn khác có chấp nhận được không?

Một kế hoạch mới có ít toán tử hơn chưa chắc tốt hơn. Kết quả cần được xác nhận bằng tải và số liệu thực tế.

## Quy trình chẩn đoán theo từng bước

Khi nhận một truy vấn có dấu hiệu chậm, có thể áp dụng quy trình sau:

1. **Xác định câu truy vấn và workload.** Thu thập fingerprint, tần suất, tham số đại diện, tỷ lệ đọc/ghi, số hàng trả về và mức độ quan trọng của truy vấn.
2. **Đo baseline.** Ghi nhận độ trễ p50/p95/p99, throughput, CPU, logical reads, physical reads, I/O wait và lock wait trong điều kiện tải phù hợp.
3. **Lấy kế hoạch.** Dùng estimated plan để hiểu lựa chọn của optimizer; dùng actual plan hoặc thống kê thực thi để xác nhận số hàng và số lần thực hiện.
4. **Tìm điểm lệch.** Kiểm tra scan, seek, filter, sort, lookup, join, ước lượng cardinality, số trang và các thao tác tràn bộ nhớ.
5. **Xác định cơ chế.** Trả lời truy vấn đang đọc quá nhiều dữ liệu, tìm kiếm thiếu chọn lọc, lookup quá nhiều, chờ khóa hay chờ I/O.
6. **Đề xuất một thay đổi có giả thuyết.** Ví dụ sửa điều kiện để SARGable, điều chỉnh thứ tự cột chỉ mục, bổ sung cột bao phủ, cập nhật thống kê hoặc giảm số hàng cần lấy.
7. **Kiểm tra tác động.** Chạy lại cùng workload, so sánh kế hoạch và các chỉ số; kiểm tra cả chi phí ghi, dung lượng và truy vấn khác.
8. **Theo dõi sau triển khai.** Quan sát đủ thời gian để phát hiện hồi quy do dữ liệu tăng, cache thay đổi hoặc workload khác xuất hiện.

### Khi nào nên chấp nhận quét bảng?

Không nên cố loại bỏ mọi Table Scan hoặc Sequential Scan. Một lần quét tuần tự có thể là lựa chọn tối ưu khi truy vấn cần phần lớn dữ liệu, bảng nhỏ, hoặc chỉ mục sẽ gây nhiều lần truy xuất hàng. Việc ép optimizer dùng chỉ mục trong những trường hợp đó có thể làm tăng thời gian, I/O và CPU.

Chỉ nên xem scan là vấn đề khi có bằng chứng rằng nó đọc nhiều dữ liệu không cần thiết so với kết quả và một đường truy cập khác có thể giảm tổng chi phí. Hãy xác định tỷ lệ hàng phù hợp, số trang đọc, kích thước hàng, khả năng cache và cách dữ liệu được phân bố.

## Khác biệt thuật ngữ giữa các hệ quản trị

| Khái niệm | SQL Server | PostgreSQL | MySQL/InnoDB |
|---|---|---|---|
| Quét bảng | Table Scan, có thể Clustered Index Scan tùy cấu trúc | Seq Scan | Table scan, thường thấy access type ALL trong EXPLAIN |
| Tìm qua chỉ mục | Index Seek | Index Scan với Index Cond, hoặc Index Only Scan | ref, range, const và các access type khác |
| Quét chỉ mục | Index Scan | Index Scan có thể duyệt vùng chỉ mục | Index scan hoặc access type index tùy kế hoạch |
| Truy xuất hàng từ chỉ mục phụ | Key Lookup hoặc RID Lookup | Heap Fetch trong một số đường đi | Tra cứu clustered index theo khóa chính |
| Dữ liệu có sẵn trong chỉ mục | Included columns có thể tạo covering index | Index Only Scan khi điều kiện visibility cho phép | Covering index khi các cột cần thiết có trong secondary index |

Bảng trên chỉ là hướng dẫn đối chiếu khái niệm, không thay thế tài liệu phiên bản cụ thể. Tên hiển thị và chi tiết kế hoạch có thể thay đổi theo phiên bản, loại bảng, loại chỉ mục và công cụ xem kế hoạch.

## Những sai lầm thường gặp

- **Cho rằng scan luôn xấu:** scan có thể là đường đi rẻ nhất khi cần nhiều hàng hoặc bảng nhỏ.
- **Cho rằng seek luôn tốt:** seek có thể tạo rất nhiều lookup hoặc trả về phần lớn bảng.
- **Chỉ nhìn tên toán tử:** phải xem điều kiện, số hàng, số lần lặp, số trang và các toán tử con.
- **Nhầm Index Scan giữa các hệ quản trị:** cùng tên có thể mô tả đường đi khác nhau.
- **Chỉ nhìn Estimated Cost:** cost là ước lượng theo mô hình optimizer, không phải thời gian thực tế.
- **Bỏ qua residual predicate:** hệ quản trị có thể tìm được một vùng chỉ mục nhưng vẫn đọc và loại bỏ rất nhiều hàng.
- **Thêm mọi cột vào chỉ mục:** chỉ mục rộng làm tăng chi phí ghi, lưu trữ và bộ nhớ.
- **Không kiểm tra thống kê:** optimizer có thể chọn sai vì ước lượng số hàng không chính xác.
- **Dùng một tham số để đại diện cho mọi workload:** dữ liệu lệch và parameter sensitivity có thể tạo kế hoạch khác nhau.
- **Đo truy vấn đơn lẻ rồi kết luận:** tải đồng thời, cache, khóa và tác vụ nền có thể làm kết quả production khác xa.

## Checklist đọc kế hoạch truy cập dữ liệu

- [ ] Xác định đúng hệ quản trị, phiên bản và loại bảng/chỉ mục.
- [ ] Phân biệt quét bảng, quét chỉ mục, tìm kiếm chỉ mục và truy xuất hàng.
- [ ] Kiểm tra điều kiện tìm kiếm và residual predicate.
- [ ] So sánh Estimated Rows với Actual Rows.
- [ ] Xem Rows Read, số lần lặp và logical/physical reads.
- [ ] Xác định lookup có lặp nhiều lần hoặc gây truy cập ngẫu nhiên không.
- [ ] Kiểm tra sort, join, spill và việc dùng thứ tự chỉ mục.
- [ ] Đánh giá độ chọn lọc, thứ tự cột và khả năng bao phủ của chỉ mục.
- [ ] Xem thống kê, phân bố dữ liệu và độ nhạy theo tham số.
- [ ] Đo lại dưới workload đại diện và kiểm tra tác động đến ghi, lưu trữ, cache cùng truy vấn khác.

## Thực hành: đọc đường đi của một truy vấn

Với truy vấn tra cứu đơn hàng ở ví dụ trên, hãy thực hiện các bước sau trong môi trường thử nghiệm hoặc trên bản sao dữ liệu phù hợp:

1. Chạy truy vấn với một khách hàng có ít đơn và một khách hàng có nhiều đơn.
2. Thu thập kế hoạch ước lượng và kế hoạch thực tế theo công cụ của hệ quản trị.
3. Ghi số hàng ước lượng, số hàng thực tế, số hàng đọc, số lần lookup, logical reads và thời gian.
4. Xác định thao tác nào đang tiêu tốn nhiều chi phí nhất: scan, seek, lookup, sort hay chờ tài nguyên.
5. Đề xuất một thay đổi có thể kiểm chứng, chẳng hạn chỉ mục ghép phù hợp hoặc giảm cột trả về.
6. Chạy lại cùng hai trường hợp tham số và so sánh cả kết quả đọc lẫn chi phí ghi.

Không giả định cùng một kế hoạch sẽ tối ưu cho mọi giá trị tham số. Nếu hai nhóm dữ liệu có độ chọn lọc khác nhau, hãy kiểm tra kế hoạch và số hàng thực tế của từng nhóm. Mục tiêu của bài thực hành là giải thích được vì sao optimizer chọn đường truy cập đó và dữ liệu nào chứng minh đường đi mới tốt hơn.

Khi đọc được mối quan hệ giữa scan, seek và lookup, người tối ưu có thể hiểu rõ hệ quản trị đang đọc dữ liệu như thế nào. Kết hợp kế hoạch với thống kê tải, độ chọn lọc, số hàng thực tế và chi phí tài nguyên giúp lựa chọn chỉ mục và cải thiện SQL có căn cứ, đồng thời tránh tạo chỉ mục dư thừa hoặc ép hệ quản trị đi theo một đường truy cập kém hiệu quả.
