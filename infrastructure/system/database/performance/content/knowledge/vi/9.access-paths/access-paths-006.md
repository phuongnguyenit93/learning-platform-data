# Quét bitmap và kết hợp nhiều chỉ mục theo hệ quản trị

Một truy vấn có nhiều điều kiện lọc không nhất thiết phải dùng một chỉ mục ghép duy nhất. Một số hệ quản trị có thể đọc nhiều chỉ mục riêng, kết hợp các tập dòng tìm được bằng phép AND hoặc OR, rồi truy cập bảng để lấy dữ liệu. Cách làm này thường được gọi là kết hợp chỉ mục (index combination, index merge) hoặc truy cập bằng bitmap (bitmap access path).

Cơ chế cụ thể khác nhau giữa các hệ quản trị. PostgreSQL có thể tạo bitmap từ một hoặc nhiều lần quét chỉ mục rồi dùng Bitmap Heap Scan; MySQL có chiến lược Index Merge; Oracle hỗ trợ bitmap index và các phép toán bitmap trong kế hoạch truy vấn. Các thuật ngữ gần nhau nhưng không phải lúc nào cũng chỉ cùng một cấu trúc vật lý.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Bài học này giải thích cách quét bitmap hoạt động, cách hệ quản trị kết hợp nhiều chỉ mục, khi nào phương án đó có lợi, khi nào chỉ mục ghép hoặc quét tuần tự phù hợp hơn, và cách kiểm chứng bằng execution plan.

## 1. Đường truy cập dữ liệu và vị trí của bitmap

Khi thực hiện điều kiện WHERE, bộ tối ưu có nhiều cách tìm dòng phù hợp:

- **Table scan / sequential scan:** đọc tuần tự các trang của bảng và kiểm tra điều kiện.
- **Index seek / index range scan:** dùng cấu trúc chỉ mục để tìm khóa hoặc một khoảng khóa, sau đó lấy dòng tương ứng.
- **Index-only / covering access:** trả kết quả từ chỉ mục khi chỉ mục chứa đủ dữ liệu cần thiết và hệ quản trị có thể xác minh tính hợp lệ mà không phải đọc bảng cho từng dòng.
- **Bitmap access:** tạo tập hợp vị trí dòng cần đọc, có thể kết hợp nhiều tập vị trí, sau đó truy cập các trang dữ liệu theo thứ tự phù hợp.
- **Partition pruning:** loại bỏ các phân vùng chắc chắn không chứa dòng phù hợp trước khi quét hoặc dùng chỉ mục bên trong các phân vùng còn lại.

Bitmap là một cách biểu diễn tập hợp vị trí dòng hoặc trang dữ liệu. Thay vì đi theo từng mục chỉ mục và lập tức truy cập bảng, hệ quản trị có thể thu thập các vị trí cần thiết trước, hợp nhất chúng rồi đọc các trang dữ liệu theo thứ tự vật lý hoặc theo cách giảm truy cập lặp.

Điểm quan trọng: bitmap access không có nghĩa là toàn bộ dữ liệu trả về nằm trong bitmap. Bitmap thường giúp xác định vị trí cần đọc; hệ quản trị vẫn có thể phải truy cập bảng để lấy cột còn thiếu và kiểm tra điều kiện.

## 2. Bitmap biểu diễn tập dòng như thế nào?

Hãy hình dung bảng orders được lưu trên nhiều trang dữ liệu. Một chỉ mục trên status có thể tìm ra các dòng có status = 'PAID'. Một chỉ mục khác trên region có thể tìm ra các dòng có region = 'NORTH'.

Mỗi lần quét chỉ mục tạo ra một tập vị trí dòng (row identifier hoặc tuple identifier). Có thể biểu diễn giản lược bằng bitmap:

~~~text
Vị trí dòng:    1 2 3 4 5 6 7 8 9 10
status = PAID:  1 0 1 1 0 1 0 0 1  0
region = NORTH: 0 1 1 1 0 0 1 0 1  0

AND:            0 0 1 1 0 0 0 0 1  0
OR:             1 1 1 1 0 1 1 0 1  0
~~~

- Phép AND giữ các dòng thỏa mãn cả hai điều kiện.
- Phép OR giữ các dòng thỏa mãn ít nhất một điều kiện.
- Sau khi kết hợp, hệ quản trị lấy dữ liệu từ các vị trí còn lại và có thể kiểm tra lại điều kiện.

Đây là mô hình khái niệm. Cách lưu bitmap thực tế có thể dùng bitset, danh sách vị trí nén, cấu trúc theo trang hoặc biểu diễn lai. Một số hệ quản trị tạo bitmap tạm từ B-tree index; hệ quản trị khác lưu bitmap index như một loại chỉ mục riêng.

### Vì sao gom vị trí trước khi đọc bảng?

Nếu một truy vấn cần hàng nghìn dòng nằm rải rác trên nhiều trang, việc truy cập bảng ngay sau mỗi lần tìm khóa có thể tạo nhiều lần đọc ngẫu nhiên hoặc truy cập lặp cùng trang. Gom vị trí rồi sắp xếp theo trang giúp hệ quản trị:

1. Loại trùng các vị trí dòng được tìm thấy từ nhiều chỉ mục.
2. Nhóm các dòng theo trang dữ liệu.
3. Đọc một trang một lần để lấy nhiều dòng cần thiết trên trang đó.
4. Giảm số lần chuyển qua lại giữa các trang và cải thiện tính cục bộ của I/O.

Bitmap không đảm bảo luôn nhanh hơn index scan. Nếu chỉ có vài dòng khớp và chúng nằm trên ít trang, một index lookup trực tiếp có thể rẻ hơn việc tạo bitmap. Nếu phần lớn bảng phù hợp, sequential scan có thể là lựa chọn hiệu quả hơn.

## 3. Kết hợp nhiều chỉ mục bằng AND và OR

Giả sử bảng orders có các cột tenant_id, status, region và created_at. Ứng dụng thường tìm đơn theo tenant, trạng thái và khu vực.

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND region = 'NORTH';
~~~

Nếu có các chỉ mục riêng trên tenant_id, status và region, hệ quản trị có thể:

- Quét từng chỉ mục để tìm tập vị trí phù hợp.
- Kết hợp các tập vị trí bằng phép AND.
- Truy cập bảng để lấy order_id, created_at và total_amount.
- Kiểm tra lại các điều kiện nếu cần.

Đối với điều kiện OR:

~~~sql
SELECT order_id, customer_id, status
FROM orders
WHERE status = 'PENDING'
   OR region = 'NORTH';
~~~

hệ quản trị có thể hợp nhất tập vị trí từ chỉ mục status và chỉ mục region. Các dòng xuất hiện trong cả hai tập cần được loại trùng để tránh trả kết quả hai lần.

### Điều kiện AND và OR không giống nhau về độ chọn lọc

Với AND, mỗi điều kiện bổ sung thường thu hẹp tập kết quả. Nếu các điều kiện chọn lọc tốt, giao của các tập vị trí có thể nhỏ hơn đáng kể so với từng tập ban đầu.

Với OR, mỗi điều kiện bổ sung thường mở rộng tập kết quả. Nếu một nhánh đã khớp phần lớn bảng, hợp bitmap có thể gần bằng toàn bộ bảng và không còn lợi thế so với scan.

Độ chọn lọc còn phụ thuộc tương quan dữ liệu. Ví dụ tenant_id = 42 và region = 'NORTH' có thể tương quan mạnh nếu tenant đó chỉ hoạt động tại miền Bắc. Không thể luôn nhân xác suất của hai điều kiện như thể chúng độc lập. Thống kê và số dòng thực tế giúp optimizer ước lượng kích thước tập giao hoặc hợp.

## 4. PostgreSQL: Bitmap Index Scan, BitmapAnd và Bitmap Heap Scan

PostgreSQL có đường truy cập bitmap tạm được xây dựng từ kết quả quét chỉ mục. Một kế hoạch có thể gồm các node:

- **Bitmap Index Scan:** đọc một chỉ mục và tạo bitmap các tuple identifier phù hợp.
- **BitmapAnd:** lấy giao của nhiều bitmap.
- **BitmapOr:** lấy hợp của nhiều bitmap.
- **Bitmap Heap Scan:** dùng bitmap để truy cập các trang của bảng và lấy tuple cần thiết.

### Ví dụ kết hợp nhiều chỉ mục bằng AND

Giả sử có hai chỉ mục riêng:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);

CREATE INDEX idx_orders_status
ON orders (status);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
~~~

PostgreSQL có thể chọn một kế hoạch dạng khái niệm:

~~~text
Bitmap Heap Scan on orders
  Recheck Cond: (tenant_id = 42 AND status = 'PAID')
  -> BitmapAnd
       -> Bitmap Index Scan on idx_orders_tenant
       -> Bitmap Index Scan on idx_orders_status
~~~

Node BitmapAnd kết hợp hai bitmap. Bitmap Heap Scan đọc các trang của orders có chứa những dòng phù hợp. Kế hoạch thực tế có thể khác tùy thống kê, dữ liệu, chỉ mục và chi phí ước lượng.

### Ví dụ kết hợp bằng OR

~~~sql
SELECT order_id, status, region
FROM orders
WHERE status = 'PENDING'
   OR region = 'NORTH';
~~~

Nếu có chỉ mục phù hợp trên hai cột, PostgreSQL có thể chọn BitmapOr:

~~~text
Bitmap Heap Scan on orders
  Recheck Cond: (status = 'PENDING' OR region = 'NORTH')
  -> BitmapOr
       -> Bitmap Index Scan on idx_orders_status
       -> Bitmap Index Scan on idx_orders_region
~~~

BitmapOr hợp nhất các vị trí dòng từ hai nhánh. Một dòng thỏa mãn cả hai điều kiện chỉ được trả về một lần.

### Đọc số liệu Bitmap Heap Scan

Khi dùng EXPLAIN ANALYZE, BUFFERS, PostgreSQL có thể hiển thị thông tin như:

- **Heap Blocks: exact:** số trang heap được bitmap xác định chính xác các tuple offset cần đọc.
- **Heap Blocks: lossy:** số trang chỉ được đánh dấu ở mức trang, nên hệ quản trị phải xem các tuple trên trang và kiểm tra lại điều kiện.
- **Rows Removed by Index Recheck:** số dòng bị loại sau bước kiểm tra lại điều kiện.
- **Buffers:** số lần truy cập buffer, phân biệt hit và read theo định dạng kế hoạch.
- **Actual rows và loops:** số dòng thực tế và số lần node được thực thi.

Bitmap có thể trở thành lossy khi cấu trúc bitmap chi tiết không thể giữ trong bộ nhớ được cấp. Khi đó hệ quản trị đánh dấu cả trang thay vì lưu từng tuple identifier. Bitmap Heap Scan phải kiểm tra lại điều kiện trên các tuple của trang đó; số dòng phải kiểm tra có thể lớn hơn số dòng cuối cùng trả về.

Tham số work_mem ảnh hưởng đến bộ nhớ của một số thao tác như bitmap, sort và hash. Tăng work_mem có thể giảm bitmap lossy trong một workload, nhưng cần tính đến số thao tác đồng thời và số phiên. Đặt quá cao trên toàn hệ thống có thể làm tổng mức dùng RAM vượt khả năng máy chủ.

### Vì sao có Recheck Cond?

Recheck Cond là điều kiện được dùng để xác minh các dòng khi bitmap yêu cầu kiểm tra lại. Điều này đặc biệt quan trọng với bitmap lossy, nhưng việc có dòng Recheck Cond trong plan không tự nó chứng minh bitmap đã lossy. Hãy xem Heap Blocks exact/lossy và Rows Removed by Index Recheck để hiểu số liệu thực tế.

### Bitmap scan có giữ thứ tự của chỉ mục không?

Bitmap Heap Scan thường đọc các trang heap theo thứ tự trang, không duy trì thứ tự khóa của chỉ mục gốc. Nếu truy vấn cần ORDER BY, hệ quản trị có thể phải thêm Sort. Một index scan đơn có thể có lợi thế nếu nó trả dòng theo thứ tự cần thiết và chỉ phải đọc ít dữ liệu.

Đây là một đánh đổi quan trọng: bitmap có thể giảm truy cập trang ngẫu nhiên, nhưng có thể mất thứ tự sẵn có từ B-tree.

## 5. MySQL: Index Merge

MySQL InnoDB có chiến lược Index Merge cho phép kết hợp kết quả từ nhiều range scan trên các chỉ mục của cùng một bảng. Đây là cơ chế kết hợp chỉ mục ở tầng optimizer; không nên mặc định nó giống hệt Bitmap Heap Scan của PostgreSQL.

Các dạng Index Merge thường gặp:

- **Intersection:** giao các tập row identifier, thường có thể áp dụng cho điều kiện AND.
- **Union:** hợp các tập row identifier, thường có thể áp dụng cho điều kiện OR.
- **Sort-union:** thu thập row identifier từ các nhánh, sắp xếp và loại trùng trước khi truy cập các dòng.

### Ví dụ Index Merge intersection

Giả sử có các chỉ mục riêng:

~~~sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);

CREATE INDEX idx_orders_status
ON orders (status);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
~~~

MySQL có thể chọn Index Merge intersection nếu chi phí ước lượng thấp hơn các đường truy cập khác. Trong EXPLAIN truyền thống, có thể thấy:

- type = index_merge.
- key liệt kê nhiều chỉ mục.
- Extra có nội dung dạng Using intersect(...).

### Ví dụ Index Merge union

~~~sql
SELECT order_id, status
FROM orders
WHERE status = 'PENDING'
   OR region = 'NORTH';
~~~

Nếu cả hai nhánh có đường truy cập chỉ mục phù hợp, MySQL có thể dùng Index Merge union. EXPLAIN có thể hiển thị type = index_merge và Extra dạng Using union(...).

Với sort_union, hệ quản trị phải thu thập và sắp xếp các row identifier trước khi hợp nhất. Chi phí sắp xếp có thể đáng kể khi các nhánh trả về nhiều vị trí.

### Kiểm tra kế hoạch trong MySQL

Có thể bắt đầu bằng:

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
~~~

Tùy phiên bản và định dạng EXPLAIN, hãy xem:

- type: có phải index_merge hay không.
- key: những chỉ mục được sử dụng.
- rows: số dòng ước lượng.
- filtered: tỷ lệ dòng còn lại ước lượng sau điều kiện.
- Extra: Using intersect, Using union hoặc Using sort_union.

Các phiên bản hỗ trợ EXPLAIN ANALYZE có thể cung cấp số liệu thực thi thực tế. Cần kiểm tra khả năng của phiên bản đang dùng và cân nhắc rằng EXPLAIN ANALYZE thực thi câu truy vấn.

### Giới hạn và tính chọn lọc

Index Merge không được dùng cho mọi tổ hợp AND/OR. Optimizer phải xác định các điều kiện có thể tạo range scan tương thích và đánh giá tổng chi phí. Một điều kiện không thể dùng chỉ mục, kiểu ép dữ liệu, hàm trên cột hoặc tập kết quả quá rộng có thể khiến chiến lược này không còn phù hợp.

Không nên cố ép Index Merge chỉ vì bảng có nhiều chỉ mục. Nếu một chỉ mục ghép phù hợp có thể lọc và trả dữ liệu hiệu quả hơn, nó có thể là lựa chọn tốt hơn.

## 6. Oracle: Bitmap Index và các phép toán bitmap

Oracle hỗ trợ bitmap index như một loại chỉ mục riêng. Bitmap index lưu biểu diễn bitmap cho các giá trị khóa và ánh xạ chúng đến rowid của các dòng tương ứng.

Loại chỉ mục này thường phù hợp với workload phân tích, đọc nhiều, có các cột độ phân biệt thấp hoặc vừa phải và ít cập nhật đồng thời. Ví dụ các cột như channel, region, gender_code hoặc status có thể phù hợp trong một số kho dữ liệu, tùy kích thước bảng và mẫu truy vấn.

### Kết hợp bitmap index

Giả sử bảng sales có các bitmap index trên channel và region. Truy vấn:

~~~sql
SELECT product_id, sale_date, amount
FROM sales
WHERE channel = 'ONLINE'
  AND region = 'NORTH';
~~~

Oracle có thể kết hợp bitmap của channel và region bằng phép AND, sau đó chuyển kết quả thành rowid để truy cập bảng. Với điều kiện OR, optimizer có thể dùng phép OR giữa các bitmap.

Trong execution plan, có thể gặp các operation như:

- BITMAP INDEX SINGLE VALUE hoặc BITMAP INDEX RANGE SCAN.
- BITMAP AND.
- BITMAP OR.
- BITMAP CONVERSION TO ROWIDS.
- BITMAP CONVERSION FROM ROWIDS.

Tên operation cụ thể phụ thuộc kế hoạch, phiên bản và đường truy cập được chọn.

### Khi nào bitmap index phù hợp?

Bitmap index thường có lợi khi:

- Cột có số lượng giá trị khác nhau tương đối thấp so với số dòng.
- Workload có nhiều điều kiện lọc kết hợp AND/OR.
- Truy vấn phân tích đọc nhiều dòng nhưng vẫn loại bỏ được phần đáng kể dữ liệu.
- Dữ liệu chủ yếu được nạp theo batch hoặc cập nhật với mức đồng thời ghi thấp.
- Không gian lưu trữ và chi phí duy trì bitmap có thể chấp nhận.

### Hạn chế khi ghi đồng thời

Bitmap index có thể làm tăng tranh chấp khi nhiều giao dịch cập nhật các dòng khác nhau nhưng các dòng đó thuộc cùng phạm vi bitmap. Việc thay đổi bitmap có thể ảnh hưởng đến nhiều rowid, khiến mức khóa và đồng thời ghi không thuận lợi như B-tree index thông thường trong workload OLTP.

Do đó, không nên tạo bitmap index tùy tiện cho bảng giao dịch có cập nhật đồng thời cao. Với workload OLTP, B-tree index thường là lựa chọn phổ biến hơn; quyết định vẫn cần dựa trên đặc điểm dữ liệu, phiên bản Oracle và phép đo.

### Bitmap index không đồng nghĩa với bitmap scan tạm

Cần phân biệt hai khái niệm:

- PostgreSQL có thể tạo bitmap tạm từ B-tree index để gom tuple identifier và truy cập heap theo trang.
- Oracle bitmap index lưu cấu trúc bitmap như một loại chỉ mục riêng.

Cả hai đều dùng bitmap để kết hợp điều kiện, nhưng cấu trúc lưu trữ, chi phí cập nhật và đặc điểm concurrency khác nhau.

## 7. So sánh cơ chế giữa các hệ quản trị

| Hệ quản trị | Cơ chế thường gặp | Cách kết hợp | Điểm cần quan sát |
|---|---|---|---|
| PostgreSQL | Bitmap Index Scan và Bitmap Heap Scan | BitmapAnd, BitmapOr từ các chỉ mục | Heap Blocks exact/lossy, recheck, buffers, sort |
| MySQL InnoDB | Index Merge | Intersection, union, sort-union | type=index_merge, key, rows, Extra |
| Oracle | Bitmap index và bitmap operations | Bitmap AND/OR, chuyển bitmap sang rowid | Operation trong plan, cardinality, chi phí cập nhật và concurrency |
| SQL Server | Có thể kết hợp index access trong kế hoạch; bitmap filter thường là bộ lọc runtime | Index intersection hoặc bitmap filter tùy kế hoạch | Actual plan, residual predicate, row count và parallelism |

Với SQL Server, bitmap filter thường là bộ lọc runtime được tạo trong một số kế hoạch hash join hoặc parallel query để loại sớm dòng không có khả năng khớp. Nó không tương đương với bitmap index lưu trữ như Oracle, cũng không nên mặc định tương đương với chuỗi Bitmap Index Scan/Bitmap Heap Scan của PostgreSQL. Khi đọc kế hoạch SQL Server, hãy xác định rõ operator đang dùng bitmap filter hay đang kết hợp nhiều index.

## 8. Kết hợp nhiều chỉ mục hay tạo chỉ mục ghép?

Giả sử truy vấn thường dùng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Có hai hướng thiết kế:

1. Dùng các chỉ mục riêng trên tenant_id và status rồi để optimizer kết hợp chúng.
2. Tạo chỉ mục ghép theo mẫu truy vấn, ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Không có lựa chọn đúng cho mọi hệ thống. Cần xét các tiêu chí sau:

| Tiêu chí | Kết hợp nhiều chỉ mục | Chỉ mục ghép |
|---|---|---|
| Điều kiện lọc | Linh hoạt khi truy vấn dùng nhiều tổ hợp điều kiện | Tối ưu cho các tổ hợp và thứ tự cột được thiết kế |
| Số lần quét index | Có thể phải quét nhiều chỉ mục rồi hợp nhất | Có thể dùng một lần range scan |
| Thứ tự kết quả | Bitmap thường không giữ thứ tự khóa; có thể cần sort | Có thể cung cấp thứ tự theo các cột trong index |
| Dữ liệu trả về | Có thể vẫn cần truy cập bảng nhiều lần | Có thể bao phủ truy vấn nếu chứa đủ cột và điều kiện visibility phù hợp |
| Chi phí ghi | Duy trì nhiều chỉ mục riêng | Duy trì một index rộng hơn; vẫn có chi phí cập nhật |
| Dung lượng | Nhiều chỉ mục riêng có thể cộng dồn dung lượng đáng kể | Index ghép có thể lớn tùy số cột và độ rộng |
| Tính tái sử dụng | Có thể phục vụ nhiều mẫu điều kiện khác nhau | Phụ thuộc tiền tố và thứ tự cột của index |

### Khi nào kết hợp nhiều chỉ mục có lợi?

- Mỗi điều kiện có chỉ mục riêng và đủ chọn lọc.
- Các tổ hợp điều kiện thay đổi theo truy vấn.
- Tập giao hoặc hợp sau khi kết hợp nhỏ.
- Chi phí tạo và duy trì thêm chỉ mục ghép chưa được chứng minh.
- Hệ quản trị có chiến lược kết hợp chỉ mục hiệu quả cho workload đó.

### Khi nào chỉ mục ghép có thể tốt hơn?

- Một mẫu truy vấn quan trọng thường xuyên lọc theo cùng tổ hợp cột.
- Thứ tự cột trong index phù hợp với điều kiện lọc và ORDER BY.
- Có thể giảm số lần quét và chi phí hợp nhất bitmap.
- Index ghép có thể cung cấp dữ liệu cần thiết hoặc tránh sort.
- Độ chọn lọc theo tiền tố index phù hợp với các giá trị tham số thực tế.

Ví dụ, index (tenant_id, status, created_at) có thể hỗ trợ lọc theo tenant_id và status, đồng thời trả dữ liệu theo created_at trong phạm vi hai cột đầu cố định. Nhưng nó không tự động thay thế tốt cho mọi truy vấn chỉ lọc theo status hoặc region. Cần xét tiền tố trái và các truy vấn khác trong workload.

## 9. Các trường hợp bitmap kém hiệu quả

Bitmap hoặc index merge có thể kém hiệu quả trong những tình huống sau:

### Điều kiện quá ít chọn lọc

Nếu một nhánh trả về phần lớn dòng, bitmap phải chứa rất nhiều vị trí. Chi phí tạo và kết hợp bitmap có thể cao hơn việc quét tuần tự.

### Quá nhiều dòng nằm trên nhiều trang

Nếu tập dòng kết quả trải rộng trên phần lớn bảng, bitmap heap scan vẫn phải đọc rất nhiều trang. Sequential scan có thể đọc tuần tự và tận dụng I/O tốt hơn.

### Truy vấn cần thứ tự từ chỉ mục

Bitmap heap scan thường không giữ thứ tự của B-tree index. Nếu truy vấn có ORDER BY và LIMIT nhỏ, một index scan theo thứ tự có thể trả kết quả sớm hơn mà không cần sort.

### Bitmap lossy và recheck lớn

Khi bitmap phải dùng biểu diễn lossy, nhiều dòng trên trang được kiểm tra lại. Nếu số trang lossy và số dòng bị loại sau recheck tăng mạnh, chi phí CPU có thể đáng kể.

### Tập điều kiện tương quan hoặc ước lượng sai

Optimizer có thể ước lượng sai kích thước giao/hợp nếu thống kê không phản ánh tương quan dữ liệu. Kế hoạch kết hợp nhiều chỉ mục có thể được chọn dù thực tế tập dòng lớn hơn nhiều dự kiến.

### Chi phí tạo bitmap hoặc hợp nhất lớn

Đối với truy vấn chỉ trả vài dòng, một index lookup trực tiếp có thể rẻ hơn việc quét hai chỉ mục, xây bitmap, kết hợp và đọc heap.

### Dữ liệu cập nhật liên tục

Với các hệ quản trị dùng bitmap index lưu trữ như Oracle, chi phí ghi và concurrency có thể là vấn đề đáng kể. Cần xét tỷ lệ insert/update/delete và số giao dịch đồng thời.

## 10. Cách đọc execution plan khi nhiều chỉ mục được kết hợp

Khi thấy nhiều index scan trong cùng một kế hoạch, cần xác định chúng được kết hợp ở đâu và tổng chi phí sau kết hợp là bao nhiêu.

### Với PostgreSQL

Dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID';
~~~

Quan sát:

- Có BitmapAnd hay BitmapOr không?
- Mỗi Bitmap Index Scan trả bao nhiêu dòng?
- Bitmap Heap Scan đọc bao nhiêu heap block?
- Heap Blocks exact và lossy là bao nhiêu?
- Rows Removed by Index Recheck có lớn không?
- Có Sort sau bitmap scan không?
- Buffers hit/read và thời gian node ra sao?
- Actual rows có lệch estimated rows không?

Nếu có nhiều bitmap index scan nhưng tập kết quả cuối rất nhỏ, việc kết hợp có thể hợp lý. Nếu bitmap heap scan đọc gần hết bảng hoặc tạo nhiều recheck, hãy so sánh với sequential scan và chỉ mục ghép.

### Với MySQL

Dùng EXPLAIN hoặc EXPLAIN ANALYZE nếu phiên bản hỗ trợ. Kiểm tra:

- type có phải index_merge không?
- key liệt kê những index nào?
- Extra cho biết intersect, union hay sort_union?
- rows và filtered có phù hợp với dữ liệu thực tế không?
- Có bước sort hoặc table access đáng kể sau khi hợp nhất không?
- Thời gian thực tế có cải thiện so với single-index access hoặc table scan không?

Nếu optimizer không chọn Index Merge, điều đó không tự chứng minh thiếu chỉ mục. Có thể một đường truy cập khác có chi phí thấp hơn.

### Với Oracle

Dùng DBMS_XPLAN để đọc execution plan, chẳng hạn:

~~~sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST'));
~~~

Tùy quyền và cấu hình thống kê thực thi, có thể xem operation bitmap, estimated rows, actual rows, buffers và các bước chuyển đổi rowid. Hãy kiểm tra số liệu thực tế của từng operation và tác động đến các truy vấn ghi.

### Phân biệt kế hoạch ước lượng và kế hoạch có số liệu thực tế

EXPLAIN thông thường có thể chỉ cho biết kế hoạch ước lượng. Để xác nhận bitmap có thật sự giảm công việc hay không, cần số liệu thực tế như actual rows, block reads, buffers, elapsed time và mức tải. Cách bật thống kê thực thi phụ thuộc hệ quản trị và có thể làm truy vấn thực sự chạy.

## 11. Quy trình đánh giá bitmap và index combination

Có thể áp dụng trình tự sau cho một truy vấn có nhiều điều kiện lọc:

1. **Xác định workload:** ghi nhận query fingerprint, tần suất gọi, p50/p95/p99, tham số phổ biến và tỷ lệ kết quả.
2. **Kiểm tra điều kiện:** xác định AND/OR, kiểu dữ liệu, NULL, hàm trên cột và điều kiện nào có thể dùng index.
3. **Kiểm tra chỉ mục:** lập danh sách index hiện có, cột, thứ tự cột, độ rộng và chi phí ghi.
4. **Đọc thống kê:** xem distinct count, histogram, giá trị phổ biến và tương quan giữa các điều kiện.
5. **Đọc kế hoạch:** tìm BitmapAnd/BitmapOr, Bitmap Heap Scan, Index Merge hoặc bitmap operations tương ứng.
6. **Đo tập trung gian:** xem số dòng từ từng index, số dòng sau hợp nhất, số trang đọc và số dòng phải recheck.
7. **So sánh phương án:** bitmap, single-index scan, composite index và sequential/table scan.
8. **Thử một thay đổi:** chỉ mục ghép, cập nhật thống kê, điều chỉnh SQL hoặc cấu hình phù hợp với hệ quản trị.
9. **Đo lại:** dùng cùng tham số, dữ liệu, mức tải và cửa sổ thời gian.
10. **Kiểm tra tác động phụ:** thời gian ghi, dung lượng index, bộ nhớ, temp I/O, sort và các truy vấn khác.

Nếu cần so sánh kế hoạch, hãy lưu lại phiên bản hệ quản trị, cấu hình liên quan và thống kê tại thời điểm đo. Điều này giúp giải thích khi optimizer thay đổi quyết định sau khi dữ liệu hoặc workload thay đổi.

## 12. Ví dụ thực tế: lọc đơn hàng theo nhiều điều kiện

Một hệ thống thương mại điện tử có bảng orders lớn. Ứng dụng có ba kiểu truy vấn:

- Tìm đơn theo tenant và status.
- Tìm đơn theo status hoặc region để tạo báo cáo.
- Tìm đơn mới nhất của một tenant theo created_at.

Ban đầu hệ thống có chỉ mục riêng trên tenant_id, status và region.

Với truy vấn tenant AND status, PostgreSQL có thể dùng BitmapAnd; MySQL có thể dùng Index Merge intersection. Nếu cả hai điều kiện đều chọn lọc, số dòng sau hợp nhất có thể nhỏ và đường truy cập có lợi.

Với truy vấn status OR region, PostgreSQL có thể dùng BitmapOr; MySQL có thể dùng Index Merge union hoặc sort_union. Nếu một trong hai điều kiện khớp phần lớn bảng, scan có thể rẻ hơn.

Với truy vấn tìm đơn mới nhất theo tenant:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 20;
~~~

một chỉ mục ghép hoặc chỉ mục theo tenant_id và created_at có thể phù hợp hơn việc kết hợp chỉ mục tenant với một chỉ mục khác rồi sort. Truy vấn cần thứ tự và LIMIT nhỏ nên khả năng đọc theo thứ tự index có giá trị lớn.

Nhóm vận hành cần đo riêng từng kiểu truy vấn. Một chiến lược bitmap tốt cho báo cáo AND/OR không có nghĩa là tốt cho truy vấn top-N cần thứ tự.

## 13. Những sai lầm thường gặp

- **Coi bitmap scan luôn nhanh hơn index scan:** bitmap có chi phí xây dựng và có thể đọc nhiều trang.
- **Coi bitmap index và bitmap scan tạm là một:** Oracle bitmap index là loại chỉ mục lưu trữ; PostgreSQL có thể tạo bitmap tạm từ B-tree index.
- **Thấy nhiều chỉ mục thì optimizer chắc chắn kết hợp:** optimizer lựa chọn theo chi phí và giới hạn của từng hệ quản trị.
- **Thêm một chỉ mục cho mỗi cột:** có thể làm tăng dung lượng và chi phí ghi mà không cải thiện workload.
- **Bỏ qua ORDER BY:** bitmap access có thể làm mất thứ tự index và phát sinh sort.
- **Bỏ qua bitmap lossy:** cần xem Heap Blocks lossy và số dòng bị loại sau recheck.
- **Tăng work_mem quá mức:** mỗi thao tác và phiên đồng thời có thể tiêu thụ thêm bộ nhớ.
- **Dùng Oracle bitmap index cho bảng OLTP cập nhật dày:** có thể tạo tranh chấp và làm giảm khả năng ghi đồng thời.
- **So sánh kế hoạch ở các mức tải khác nhau:** kết quả benchmark không còn tương đương.
- **Ép optimizer dùng index combination mà không đo:** hint hoặc cấu hình ép buộc có thể làm kế hoạch xấu đi khi dữ liệu thay đổi.

## 14. Checklist thực hành

Khi đánh giá quét bitmap hoặc kết hợp nhiều chỉ mục, hãy trả lời:

1. Truy vấn dùng AND, OR hay kết hợp nhiều nhóm điều kiện?
2. Mỗi điều kiện có chỉ mục phù hợp và độ chọn lọc bao nhiêu?
3. Các điều kiện có tương quan hoặc dữ liệu lệch không?
4. Hệ quản trị đang dùng bitmap access, Index Merge hay bitmap index lưu trữ?
5. Những chỉ mục nào được kết hợp và bằng phép AND, OR, intersection hay union?
6. Số dòng từ mỗi nhánh và số dòng sau hợp nhất là bao nhiêu?
7. Có nhiều heap block hoặc rowid phải đọc không?
8. Bitmap có lossy, recheck hoặc sort phát sinh không?
9. Truy vấn có cần thứ tự hoặc LIMIT mà index scan đơn có thể phục vụ tốt hơn không?
10. Chỉ mục ghép có thể giảm số lần quét và giữ thứ tự kết quả không?
11. Chi phí ghi, dung lượng, bộ nhớ và concurrency thay đổi thế nào?
12. Sau điều chỉnh, latency, throughput, I/O và hiệu năng các truy vấn liên quan có cải thiện ở cùng mức tải không?

## Kết luận

Quét bitmap và kết hợp nhiều chỉ mục giúp hệ quản trị ghép các tập vị trí dòng từ nhiều điều kiện lọc trước khi truy cập dữ liệu. PostgreSQL tạo bitmap từ index scan và có thể kết hợp bằng BitmapAnd hoặc BitmapOr; MySQL dùng Index Merge với intersection, union và sort-union; Oracle có bitmap index cùng các phép toán bitmap riêng. Những cơ chế này khác nhau về cấu trúc lưu trữ, cách truy cập bảng và chi phí cập nhật.

Bitmap hoặc index combination có thể hiệu quả khi các điều kiện đủ chọn lọc, tập giao/hợp nhỏ và việc gom vị trí giúp giảm truy cập dữ liệu. Chỉ mục ghép hoặc scan tuần tự có thể tốt hơn khi truy vấn cần thứ tự, cần nhiều dòng hoặc workload có đặc điểm khác. Hãy dùng execution plan và số liệu thực tế để so sánh các phương án, rồi kiểm chứng cả hiệu năng đọc, ghi, bộ nhớ và I/O sau điều chỉnh.
