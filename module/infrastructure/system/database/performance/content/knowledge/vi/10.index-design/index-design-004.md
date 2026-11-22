# Chỉ mục bao phủ và các cột bổ sung theo hệ quản trị

Chỉ mục bao phủ (covering index) là chỉ mục chứa đủ các cột mà một truy vấn cần đọc để lọc, nối, sắp xếp hoặc trả kết quả. Khi dữ liệu cần thiết đã có trong chỉ mục, hệ quản trị có thể tránh truy cập thêm vào trang dữ liệu của bảng để lấy các cột còn thiếu. Điều này thường giảm số lần đọc trang, I/O và chi phí lookup, đặc biệt với truy vấn chạy thường xuyên trên bảng lớn.

Trong thiết kế chỉ mục cho DATABASE_PERFORMANCE, cần phân biệt cột khóa (key column) với cột bổ sung (included column hoặc cột payload). Cột khóa quyết định thứ tự của chỉ mục và khả năng tìm kiếm theo tiền tố; cột bổ sung được lưu để phục vụ truy vấn nhưng không tham gia thứ tự khóa. Một số hệ quản trị hỗ trợ cú pháp INCLUDE riêng, một số khác tạo chỉ mục bao phủ bằng cách đưa tất cả cột cần thiết vào chỉ mục ghép. Cơ chế vật lý và điều kiện để tránh đọc bảng cũng khác nhau theo engine.

## 1. Chỉ mục bao phủ giải quyết vấn đề gì?

Xét truy vấn lấy trạng thái và số tiền của các đơn hàng theo khách hàng trong một khoảng thời gian:

~~~sql
SELECT status, total_amount
FROM orders
WHERE customer_id = 125
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

Giả sử bảng orders có hàng chục triệu bản ghi và đang có chỉ mục trên customer_id. Chỉ mục giúp tìm các đơn của khách hàng 125, nhưng mỗi mục chỉ mục có thể chưa chứa status và total_amount. Engine phải dùng row locator (RID, row ID hoặc khóa chính) để truy cập trang dữ liệu của bảng và lấy hai cột còn thiếu. Với nhiều hàng kết quả, các lần truy cập bổ sung này có thể gây nhiều I/O ngẫu nhiên.

Nếu chỉ mục chứa customer_id, created_at, status và total_amount, engine có thể lấy các giá trị cần thiết trực tiếp từ chỉ mục trong những điều kiện phù hợp. Khi đó, truy vấn có cơ hội trở thành index-only access hoặc covering index access.

Chỉ mục bao phủ đặc biệt hữu ích khi:

- Truy vấn được gọi thường xuyên và nằm trên đường đi quan trọng của ứng dụng.
- Predicate chọn lọc đủ tốt để chỉ mục đọc một phần nhỏ dữ liệu.
- Truy vấn trả về nhiều hàng và lookup từng hàng vào bảng tạo chi phí đáng kể.
- Tập cột cần đọc tương đối ổn định, hẹp và có thể lưu trong chỉ mục với chi phí hợp lý.
- Có thể giảm đáng kể logical reads, physical reads hoặc thời gian truy cập bảng.

Không phải cứ thêm đủ cột vào chỉ mục là truy vấn chắc chắn nhanh hơn. Chỉ mục lớn hơn chiếm cache và storage, làm tăng công việc khi INSERT, UPDATE, DELETE và có thể làm chậm các truy vấn khác. Cần chứng minh lợi ích bằng execution plan và phép đo trước/sau.

## 2. Phân biệt cột khóa và cột bổ sung

### 2.1. Cột khóa (key columns)

Cột khóa tạo thứ tự trong cấu trúc chỉ mục, thường là B-tree. Thứ tự cột ảnh hưởng đến:

- Khả năng tìm kiếm theo tiền tố của chỉ mục ghép.
- Điều kiện equality và range có thể được dùng để định vị vùng dữ liệu.
- Thứ tự hàng mà chỉ mục cung cấp cho ORDER BY hoặc một số phép GROUP BY.
- Khả năng hỗ trợ join theo khóa.
- Tính duy nhất nếu chỉ mục được khai báo UNIQUE.

Ví dụ chỉ mục ghép:

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders (customer_id, created_at);
~~~

Chỉ mục này thường phù hợp với điều kiện customer_id bằng một giá trị và created_at là một khoảng. Nó cũng có thể hỗ trợ truy vấn chỉ lọc customer_id vì customer_id là cột đầu tiên. Truy vấn chỉ lọc created_at thường không tận dụng được đường tìm kiếm tiền tố một cách hiệu quả như chỉ mục bắt đầu bằng created_at, dù engine và thống kê có thể có các chiến lược khác.

### 2.2. Cột bổ sung (included hoặc payload columns)

Cột bổ sung được lưu trong phần dữ liệu của mục chỉ mục để truy vấn có thể đọc giá trị mà không cần lấy lại từ bảng. Với hệ quản trị có cú pháp INCLUDE, các cột này không quyết định thứ tự của chỉ mục và không phải là khóa tìm kiếm.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

Ở đây customer_id và created_at là cột khóa. status và total_amount là cột bổ sung. Hai cột bổ sung giúp trả về SELECT list, nhưng không mở rộng thứ tự khóa để tìm kiếm hoặc sắp xếp theo status hay total_amount.

Nếu status xuất hiện trong điều kiện lọc và cần được dùng để định vị vùng chỉ mục, chỉ đưa status vào INCLUDE thường không đủ để thực hiện seek theo status. Engine có thể phải đọc các mục đã tìm được rồi kiểm tra status như một residual predicate. Khi đó cần cân nhắc đưa status vào nhóm key columns, tùy độ chọn lọc và thứ tự truy vấn.

### 2.3. Chọn cột nào làm khóa, cột nào làm bổ sung?

Một cách phân loại thực tế:

| Vai trò của cột trong truy vấn | Cách cân nhắc |
|---|---|
| Điều kiện equality dùng để định vị dữ liệu | Thường xem xét làm key column |
| Điều kiện range | Thường đặt sau các cột equality phù hợp trong key |
| Cột join | Cân nhắc làm key nếu cần tìm kiếm theo cột đó |
| ORDER BY cần được cung cấp từ chỉ mục | Cần là key column với thứ tự phù hợp |
| GROUP BY cần tận dụng thứ tự chỉ mục | Cân nhắc làm key column nếu có lợi |
| Chỉ xuất hiện trong SELECT list | Có thể là included/payload column |
| Chỉ cần đọc để kiểm tra residual predicate | Có thể được lưu payload, nhưng không giúp seek theo cột đó |
| Cột rất rộng hoặc ít dùng | Tránh thêm nếu lợi ích không rõ ràng |

Không áp dụng máy móc quy tắc “cột chọn lọc cao luôn đứng đầu”. Cần xét dạng truy vấn thực tế, equality/range, tần suất gọi, khả năng tái sử dụng tiền tố và những chỉ mục hiện có. Một chỉ mục tốt cho một câu SQL có thể không phải chỉ mục tốt cho toàn workload.

## 3. SQL Server: INCLUDE trong nonclustered index

SQL Server hỗ trợ khai báo các cột không phải khóa bằng INCLUDE trong nonclustered index. Key columns được lưu trong cấu trúc chỉ mục để hỗ trợ tìm kiếm và thứ tự; included columns được lưu ở mức leaf để truy vấn có thể lấy thêm giá trị.

Ví dụ:

~~~sql
CREATE NONCLUSTERED INDEX IX_Orders_Customer_CreatedAt
ON dbo.Orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

Truy vấn:

~~~sql
SELECT status, total_amount
FROM dbo.Orders
WHERE customer_id = @customer_id
  AND created_at >= @from_time
  AND created_at < @to_time;
~~~

Nếu kế hoạch dùng chỉ mục này và mọi cột cần thiết đã có trong index, SQL Server có thể thực hiện Index Seek hoặc Index Scan trên nonclustered index mà không cần Key Lookup/ RID Lookup vào bảng hoặc clustered index để lấy các cột bổ sung.

### 3.1. INCLUDE có tác dụng gì?

- Included columns không làm tăng số cấp của cây B-tree như việc mở rộng key ở các tầng điều hướng; chúng được lưu ở leaf level.
- Chúng có thể giúp bao phủ SELECT list và các giá trị cần đọc thêm.
- Chúng không quyết định thứ tự khóa, không tạo khả năng seek theo chính chúng và không cung cấp thứ tự sắp xếp theo chúng.
- Chúng không tham gia định nghĩa tính duy nhất của key trong unique nonclustered index.

Nếu một cột được dùng làm predicate cần seek hoặc làm ORDER BY, hãy đánh giá nó như key column. INCLUDE chỉ giúp engine có giá trị để đọc hoặc kiểm tra tại leaf; nó không thay thế vai trò định vị của khóa.

### 3.2. Key Lookup và lợi ích của covering index

Một kế hoạch SQL Server có thể gồm:

~~~text
Index Seek
  -> Key Lookup
  -> Nested Loops
~~~

Index Seek tìm các mục phù hợp trong nonclustered index. Key Lookup lấy các cột chưa có trong chỉ mục từ clustered index hoặc heap. Nếu số hàng lookup lớn, chi phí lặp có thể đáng kể.

Sau khi bổ sung INCLUDE phù hợp, kế hoạch có thể bỏ Key Lookup. Tuy nhiên, nếu predicate trả về phần lớn bảng, một scan khác hoặc kế hoạch khác vẫn có thể rẻ hơn. Đừng chỉ nhìn việc Key Lookup biến mất; hãy so sánh logical reads, CPU, elapsed time, số hàng và ảnh hưởng ghi.

### 3.3. Giới hạn và đánh đổi

SQL Server giới hạn số lượng và kích thước key columns; các cột INCLUDE có giới hạn riêng về số lượng và kiểu dữ liệu. Không cần ghi nhớ con số giới hạn cho mọi phiên bản, nhưng phải kiểm tra tài liệu phiên bản đang dùng khi thiết kế chỉ mục lớn.

Các điểm cần lưu ý:

- Cột bổ sung làm leaf page rộng hơn, giảm số mục trên mỗi trang và tăng kích thước chỉ mục.
- Cập nhật cột included vẫn cần cập nhật chỉ mục, dù cột đó không phải key.
- Cột lớn như chuỗi dài hoặc dữ liệu nhị phân có thể làm chỉ mục phình to.
- Clustered key được dùng làm row locator trong nonclustered index; cần tính đến các cột khóa cụm khi đánh giá kích thước và mức độ bao phủ.
- Một chỉ mục bao phủ cho một truy vấn có thể trùng lặp nhiều với chỉ mục khác.

## 4. PostgreSQL: INCLUDE và index-only scan

PostgreSQL hỗ trợ INCLUDE trong câu lệnh CREATE INDEX. Các cột sau INCLUDE là non-key columns: chúng được lưu trong chỉ mục nhưng không tham gia điều kiện tìm kiếm theo thứ tự khóa hoặc thứ tự sắp xếp của B-tree.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

Truy vấn:

~~~sql
SELECT status, total_amount
FROM orders
WHERE customer_id = 125
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at < TIMESTAMP '2026-02-01 00:00:00';
~~~

Nếu planner chọn chỉ mục này và các cột cần thiết có trong index, kế hoạch có thể dùng Index Only Scan.

### 4.1. Index Only Scan không có nghĩa luôn luôn không đọc heap

PostgreSQL dùng visibility map để xác định các heap page đã có trạng thái all-visible. Khi trang được đánh dấu all-visible, Index Only Scan có thể trả kết quả mà không cần truy cập heap để kiểm tra khả năng nhìn thấy phiên bản hàng. Nếu visibility map chưa đánh dấu trang, engine vẫn có thể phải truy cập heap.

Vì vậy, khi đọc EXPLAIN ANALYZE, cần xem:

- Operator có phải Index Only Scan không?
- Chỉ số Heap Fetches có bằng 0 hoặc thấp không?
- Số buffer hit/read có giảm không?
- Bảng có nhiều UPDATE/DELETE khiến visibility map khó giữ trạng thái all-visible không?
- Công việc VACUUM và mức độ cập nhật dữ liệu có phù hợp với kỳ vọng không?

Một truy vấn có Index Only Scan nhưng Heap Fetches rất cao vẫn có thể đọc nhiều heap page. Cần kiểm tra trạng thái bảo trì và workload cập nhật trước khi kết luận chỉ mục không hiệu quả.

### 4.2. Giới hạn của INCLUDE trong PostgreSQL

- Included columns không tham gia tìm kiếm hoặc thứ tự của key.
- Cột bổ sung làm tăng kích thước index tuple; giá trị quá rộng có thể vượt giới hạn kích thước mục chỉ mục.
- B-tree có các đặc tính tối ưu riêng; việc thêm payload có thể làm giảm khả năng nén/deduplication của chỉ mục.
- Chỉ mục lớn hơn tiêu thụ cache và tăng chi phí ghi.
- Index Only Scan còn phụ thuộc visibility map và loại access method/operator class.

Chỉ đưa các cột nhỏ, thường xuyên cần đọc và có giá trị rõ ràng vào INCLUDE. Với bảng cập nhật liên tục, cần đo số Heap Fetches và mức độ thay đổi của visibility map.

## 5. MySQL InnoDB: chỉ mục bao phủ bằng composite index

MySQL InnoDB không cung cấp cú pháp INCLUDE tách biệt như SQL Server hoặc PostgreSQL cho secondary index thông thường. Để tạo covering index, các cột truy vấn cần đọc thường được đưa vào danh sách cột của chỉ mục ghép.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_created_cover
ON orders (customer_id, created_at, status, total_amount);
~~~

Truy vấn:

~~~sql
SELECT status, total_amount
FROM orders
WHERE customer_id = 125
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Nếu các cột cần thiết có trong secondary index, InnoDB có thể lấy kết quả từ index record mà không cần truy cập clustered record cho từng hàng. EXPLAIN có thể hiển thị Using index trong cột Extra để biểu thị truy vấn được phục vụ bằng covering index.

### 5.1. Primary key được lưu trong secondary index

Trong InnoDB, bảng được tổ chức theo clustered primary key. Mỗi secondary index record chứa các cột khóa phụ cùng giá trị primary key cần thiết để tìm clustered record. Vì vậy, nếu truy vấn chỉ cần các cột của secondary index và primary key, có thể đã được bao phủ mà không cần thêm primary key vào định nghĩa chỉ mục một cách dư thừa.

Ví dụ, nếu orders có PRIMARY KEY (id) và secondary index trên (customer_id, created_at), một truy vấn chỉ lấy id, customer_id, created_at có thể được bao phủ bởi secondary index do id được lưu kèm trong leaf record của InnoDB.

### 5.2. Mọi cột thêm vào đều là key columns

Vì không có INCLUDE tách biệt, status và total_amount trong ví dụ đều là thành phần của composite index. Điều này có một số hệ quả:

- Chúng ảnh hưởng đến thứ tự khóa và kích thước key record.
- Chúng có thể mở rộng tiền tố tìm kiếm hoặc thứ tự nếu được sắp xếp đúng.
- Chúng làm chỉ mục lớn hơn trên các trang leaf và có thể làm giảm fan-out của B-tree.
- Chúng làm tăng chi phí khi các giá trị này thay đổi.
- Thứ tự cột cần được chọn cẩn thận theo các truy vấn thực tế.

Không đưa nhiều cột lớn vào index chỉ để đạt trạng thái Using index. Nếu chỉ mục quá rộng, chi phí đọc chỉ mục có thể lớn hơn lợi ích tránh clustered lookup.

### 5.3. Phân biệt Using index và Using index condition

Trong EXPLAIN của MySQL:

- **Using index** thường cho biết truy vấn có thể lấy các cột cần thiết từ index record, tức covering access.
- **Using index condition** cho biết Index Condition Pushdown được dùng để kiểm tra điều kiện ngay tại tầng storage engine, giúp giảm số lần đọc hàng đầy đủ trong một số trường hợp.

Using index condition không đồng nghĩa với covering index. Engine vẫn có thể phải truy cập clustered record để lấy các cột không có trong secondary index.

## 6. Oracle Database: covering index qua các cột của B-tree

Với B-tree index thông thường của Oracle Database, không có cú pháp INCLUDE tách biệt giống SQL Server hoặc PostgreSQL. Một chỉ mục có thể bao phủ truy vấn khi mọi cột cần thiết đều có mặt trong index key.

Ví dụ:

~~~sql
CREATE INDEX ix_orders_customer_created
ON orders (customer_id, created_at, status, total_amount);
~~~

Truy vấn:

~~~sql
SELECT status, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND created_at >= :from_time
  AND created_at < :to_time;
~~~

Nếu optimizer chọn index và không cần cột nào khác từ bảng, kế hoạch có thể dùng INDEX RANGE SCAN mà không cần TABLE ACCESS BY INDEX ROWID. Khi cần thêm cột không có trong index, Oracle thường phải dùng ROWID để truy cập bảng.

Vì mọi cột được thêm đều là thành phần khóa của B-tree, thứ tự cột ảnh hưởng đến khả năng range scan và thứ tự dữ liệu. Thêm cột chỉ để bao phủ làm index key rộng hơn, do đó cần cân nhắc kỹ với cột văn bản dài hoặc cột ít dùng.

## 7. Thiết kế chỉ mục bao phủ từ một truy vấn cụ thể

Hãy bắt đầu từ workload và truy vấn có số liệu, sau đó xác định vai trò của từng cột. Không bắt đầu bằng cách thêm tất cả cột của bảng vào một chỉ mục.

### 7.1. Phân tích truy vấn

Với mỗi truy vấn quan trọng, ghi:

1. Các cột trong WHERE và điều kiện equality/range.
2. Các cột dùng trong JOIN.
3. Các cột trong ORDER BY và GROUP BY.
4. Các cột trong SELECT list.
5. Số hàng dự kiến và thực tế trả về.
6. Tần suất truy vấn và tỷ trọng đọc/ghi của bảng.
7. Chi phí lookup, số logical reads và thời gian hiện tại.

### 7.2. Chọn key columns

Đặt các cột định vị và thứ tự vào phần key. Với truy vấn có equality trên customer_id và range trên created_at, một điểm bắt đầu hợp lý là:

~~~sql
ON orders (customer_id, created_at)
~~~

Nếu truy vấn cần lọc thêm status với độ chọn lọc cao, cần thử xem status nên đứng trước hay sau created_at. Trong B-tree, range trên một cột thường giới hạn khả năng dùng các cột tiếp theo để tiếp tục thu hẹp vùng tìm kiếm, dù các cột sau vẫn có thể giúp kiểm tra điều kiện hoặc bao phủ truy vấn. Quyết định phụ thuộc hệ quản trị, predicate và phân bố dữ liệu.

### 7.3. Chọn included/payload columns

Với SQL Server và PostgreSQL, các cột chỉ cần để trả kết quả hoặc kiểm tra thêm có thể phù hợp với INCLUDE. Ví dụ status và total_amount chỉ nằm trong SELECT list thì có thể là payload columns.

Với MySQL InnoDB và Oracle B-tree, các cột đó cần được thêm vào composite index nếu muốn bao phủ. Vì chúng trở thành key columns, cần đánh giá tác động lên thứ tự, kích thước và chi phí ghi.

### 7.4. Không bao phủ quá mức

Một chỉ mục bao phủ rộng có thể làm giảm hiệu quả tổng thể:

- Leaf pages chứa ít mục hơn nên phải đọc nhiều trang hơn.
- Chỉ mục chiếm nhiều bộ nhớ cache và storage.
- INSERT phải tạo mục chỉ mục rộng hơn.
- UPDATE các cột được lập chỉ mục phải ghi lại index entry.
- DELETE và các tác vụ bảo trì phải xử lý nhiều dữ liệu chỉ mục hơn.
- Một chỉ mục rộng có thể trùng lặp với các chỉ mục hiện có.

Nếu truy vấn chỉ trả về 5 hàng, lookup vào bảng có thể rẻ hơn việc duy trì một chỉ mục lớn cho mọi thao tác ghi. Covering index có giá trị nhất khi chi phí lookup được tránh lớn hơn chi phí bổ sung để duy trì payload.

## 8. Đọc execution plan để xác nhận chỉ mục có bao phủ

Tên operator và cách hiển thị phụ thuộc hệ quản trị:

| Hệ quản trị | Dấu hiệu thường gặp | Cần kiểm tra thêm |
|---|---|---|
| SQL Server | Index Seek/Scan trên nonclustered index, không còn Key Lookup/RID Lookup | Actual rows, logical reads, residual predicate và số lookup trước/sau |
| PostgreSQL | Index Only Scan | Heap Fetches, buffers, visibility map và actual rows |
| MySQL InnoDB | Extra hiển thị Using index | Phân biệt với Using index condition; xem access type, rows và actual iterator |
| Oracle | INDEX RANGE SCAN hoặc INDEX FAST FULL SCAN mà không có TABLE ACCESS BY INDEX ROWID | Predicate, số leaf blocks đọc và chi phí toàn kế hoạch |

Không chỉ dựa vào tên operator. Hãy xác nhận:

- Tất cả cột cần thiết của truy vấn có sẵn trong chỉ mục theo cơ chế của engine không?
- Có operator lookup hoặc table access bổ sung không?
- Số hàng thực tế có đủ chọn lọc để dùng index không?
- Số trang đọc và thời gian có giảm không?
- Truy vấn có phải đọc quá nhiều index page do index rộng không?
- Kế hoạch có thay đổi khi tham số hoặc trạng thái cache khác nhau không?

### Ví dụ so sánh trước và sau

Trước khi thêm cột bao phủ, SQL Server có thể có kế hoạch:

~~~text
Index Seek (IX_Orders_Customer)
  -> Nested Loops
      -> Key Lookup (Clustered)
~~~

Sau khi tạo nonclustered index có INCLUDE phù hợp, Key Lookup có thể biến mất:

~~~text
Index Seek (IX_Orders_Customer_CreatedAt)
~~~

Đây chỉ là hình minh họa. Cần đo logical reads, CPU, elapsed time và tác động ghi để xác nhận cải thiện. Nếu truy vấn trả về nhiều hàng hoặc predicate kém chọn lọc, optimizer có thể vẫn chọn scan.

## 9. Quy trình thử nghiệm chỉ mục bao phủ

1. **Chọn truy vấn mục tiêu:** lấy từ workload hoặc query statistics, xác định tần suất, độ trễ và số liệu đọc hiện tại.
2. **Lưu baseline:** SQL, tham số, execution plan, logical/physical reads, CPU, elapsed time, số hàng và trạng thái cache.
3. **Xác định cột cần thiết:** phân loại predicate, join, sort/group và projection.
4. **Rà soát chỉ mục hiện có:** xem tiền tố khóa, cột bao phủ, kích thước và truy vấn khác đang dùng.
5. **Thiết kế một phương án:** chọn key columns và payload/INCLUDE columns theo đúng cú pháp engine.
6. **Tạo chỉ mục trong môi trường phù hợp:** ghi lại thời gian tạo, kích thước và tác động đến tải.
7. **Đo lại cùng điều kiện:** dùng cùng snapshot, tham số, concurrency, cache state và phương pháp đo.
8. **Đọc kế hoạch mới:** xác nhận lookup được loại bỏ hoặc heap/table access giảm, đồng thời kiểm tra actual rows.
9. **Đánh giá chi phí ghi:** thử INSERT/UPDATE/DELETE đại diện, theo dõi dung lượng, I/O và thời gian bảo trì.
10. **Quyết định theo workload:** giữ chỉ mục khi lợi ích đọc tổng thể lớn hơn chi phí phát sinh và không làm suy giảm các luồng quan trọng khác.

Khi so sánh cache, cần đo cả tình huống cache nóng và workload gần thực tế. Một chỉ mục lớn có thể nhanh trong lần chạy đơn lẻ nhưng chiếm cache của các trang dữ liệu hoặc chỉ mục khác khi nhiều truy vấn chạy đồng thời.

## 10. Các sai lầm thường gặp

- **Đưa mọi cột SELECT vào key:** làm khóa rộng không cần thiết, đặc biệt ở hệ quản trị có INCLUDE riêng.
- **Dùng INCLUDE cho cột cần seek hoặc order:** payload column không tạo thứ tự khóa và không thay thế key column.
- **Cho rằng covering index luôn tránh đọc bảng:** PostgreSQL còn phụ thuộc visibility map; các engine khác cũng có điều kiện thực thi và lựa chọn plan riêng.
- **Nhầm Using index condition với Using index trong MySQL:** index condition pushdown không đảm bảo toàn bộ cột đã được bao phủ.
- **Bỏ qua primary key trong InnoDB:** secondary index đã lưu khóa chính kèm theo, nên không phải lúc nào cũng cần thêm PK vào danh sách cột.
- **Thêm cột rất rộng:** làm tăng leaf page, storage, cache pressure và write amplification.
- **Không xem chỉ mục hiện có:** tạo index trùng lặp hoặc chỉ khác một payload column có thể làm tăng chi phí bảo trì.
- **Chỉ đo SELECT:** bỏ qua INSERT, UPDATE, DELETE và tải bảo trì chỉ mục.
- **Đánh giá theo một tham số:** chỉ mục có thể tốt với một khách hàng hoặc khoảng ngày nhưng kém với phân bố khác.
- **Chỉ nhìn Key Lookup biến mất:** cần kiểm tra tổng logical reads, thời gian và workload tổng thể.

## 11. Checklist thiết kế covering index

- [ ] Đã chọn truy vấn có số liệu và tần suất thực tế.
- [ ] Đã lưu baseline gồm execution plan, rows, reads, CPU và elapsed time.
- [ ] Đã phân loại cột WHERE, JOIN, ORDER BY, GROUP BY và SELECT.
- [ ] Đã chọn key columns theo điều kiện tìm kiếm và thứ tự cần thiết.
- [ ] Đã chọn payload columns chỉ khi lợi ích bao phủ đủ rõ.
- [ ] Đã dùng đúng cú pháp và cơ chế của SQL Server, PostgreSQL, MySQL hoặc Oracle.
- [ ] Đã kiểm tra điều kiện Index Only Scan/covering access của engine.
- [ ] Đã xem độ rộng chỉ mục, kích thước leaf pages và các chỉ mục trùng lặp.
- [ ] Đã đo lại trên cùng dữ liệu, tham số, cache và concurrency.
- [ ] Đã xác nhận lookup hoặc table access giảm bằng execution plan.
- [ ] Đã đo chi phí INSERT, UPDATE, DELETE và bảo trì chỉ mục.
- [ ] Đã kiểm tra tác động lên workload tổng thể trước khi giữ chỉ mục.

Chỉ mục bao phủ giúp giảm truy cập bổ sung vào bảng khi truy vấn có thể lấy đủ dữ liệu từ index. Để thiết kế đúng, hãy đặt các cột tìm kiếm và sắp xếp vào phần khóa, dùng cột bổ sung cho dữ liệu chỉ cần đọc khi hệ quản trị hỗ trợ INCLUDE, và hiểu rằng MySQL InnoDB cùng Oracle dùng cách tạo chỉ mục ghép. Luôn xác nhận bằng execution plan, số liệu đọc và chi phí ghi trên workload đại diện.
