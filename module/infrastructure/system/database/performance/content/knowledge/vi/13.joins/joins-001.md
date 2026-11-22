# Nested loop, hash join và merge join: điều kiện và đánh đổi

Phép nối (JOIN) kết hợp các dòng từ hai nguồn dữ liệu theo một điều kiện. Trong truy vấn thực tế, JOIN thường là nơi khối lượng dữ liệu tăng nhanh: một dòng ở bảng bên trái có thể khớp với nhiều dòng ở bảng bên phải, nhiều bảng có thể được nối liên tiếp, và một lựa chọn thuật toán không phù hợp có thể tạo ra hàng triệu lần tra cứu hoặc một lượng dữ liệu trung gian rất lớn.

Bộ tối ưu truy vấn (query optimizer) thường lựa chọn giữa các thuật toán như **nested loop join**, **hash join** và **merge join** dựa trên thống kê, ước lượng số dòng, chỉ mục, thứ tự dữ liệu, bộ nhớ và chi phí dự kiến. Mỗi thuật toán có vùng hoạt động hiệu quả riêng. Không có thuật toán JOIN nào luôn nhanh nhất.

Trong module **DATABASE_PERFORMANCE**, việc tối ưu hiệu năng cần dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Vì vậy, học cách phân biệt điều kiện và đánh đổi của ba thuật toán JOIN giúp ta đọc kế hoạch thực thi có cơ sở, tìm đúng nút thắt và kiểm chứng thay đổi trên workload đại diện.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích cách nested loop join, hash join và merge join xử lý hai tập dữ liệu.
- Nhận diện điều kiện dữ liệu và access path phù hợp với từng thuật toán.
- Đánh giá vai trò của cardinality, selectivity, index, sort order, memory và data skew.
- Đọc các dấu hiệu cơ bản của JOIN trong execution plan như actual rows, loops, hash batches, sort và spill.
- Phân biệt chi phí của từng JOIN khi dữ liệu nhỏ, dữ liệu lớn, đầu vào đã có thứ tự hoặc có chỉ mục phù hợp.
- Hiểu tác động của join order, outer join, duplicate rows và NULL đến kết quả.
- Đề xuất cách đo và kiểm chứng thay đổi JOIN trên tải thực tế.

## 1. JOIN làm gì trong một truy vấn?

Một phép JOIN lấy các dòng từ hai đầu vào và kết hợp những dòng thỏa điều kiện nối. Ví dụ, bảng orders lưu đơn hàng, còn order_items lưu các dòng sản phẩm trong mỗi đơn.

~~~sql
SELECT o.order_id,
       o.created_at,
       i.product_id,
       i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42;
~~~

Trong truy vấn này:

- orders là một đầu vào của JOIN.
- order_items là đầu vào còn lại.
- Điều kiện nối là o.order_id = i.order_id.
- Điều kiện tenant_id lọc bảng orders.
- Một đơn hàng có thể có nhiều dòng chi tiết, vì vậy một dòng orders có thể khớp với nhiều dòng order_items.

Nếu 1.000 đơn hàng được chọn và mỗi đơn có trung bình 4 dòng chi tiết, kết quả có thể có khoảng 4.000 dòng. Số dòng đầu ra phụ thuộc dữ liệu và điều kiện nối, không chỉ số dòng của hai bảng.

### 1.1. Phân biệt đầu vào, đầu ra và cardinality

Khi đọc plan, cần phân biệt:

- **Input rows:** số dòng mà mỗi phía đưa vào thuật toán JOIN.
- **Output rows:** số dòng JOIN tạo ra.
- **Cardinality estimate:** số dòng optimizer dự đoán tại mỗi bước.
- **Actual cardinality:** số dòng thực tế khi thực thi.

Optimizer có thể chọn sai thuật toán nếu ước lượng sai số dòng. Ví dụ, nó dự đoán phía ngoài chỉ có 20 dòng nhưng thực tế có 200.000 dòng. Nested loop với một lần lookup phía trong cho mỗi dòng có thể trở nên rất tốn kém.

Cardinality còn phụ thuộc tính duy nhất, khóa ngoại, NULL, duplicate và độ phân bố của khóa nối. Hai bảng có số dòng tương tự không có nghĩa phép JOIN sẽ tạo ra số dòng tương tự.

### 1.2. Logical JOIN và physical JOIN

SQL mô tả kết quả logic cần có, ví dụ INNER JOIN hoặc LEFT JOIN. Optimizer chọn cách vật lý để tạo kết quả đó, chẳng hạn nested loop, hash hoặc merge join.

Cùng một câu SQL có thể có plan khác nhau khi:

- Số dòng trong bảng thay đổi.
- Thống kê được cập nhật.
- Tham số lọc thay đổi.
- Index được tạo hoặc xóa.
- Bộ nhớ khả dụng thay đổi.
- DBMS chọn cách chạy song song.
- Phiên bản hoặc cấu hình optimizer thay đổi.

Vì vậy, không nên suy ra thuật toán JOIN chỉ từ cách viết SQL. Cần xem execution plan thực tế của DBMS đang sử dụng.

## 2. Nested loop join

### 2.1. Cách hoạt động

Nested loop join lấy từng dòng từ đầu vào bên ngoài (outer input), sau đó tìm các dòng khớp ở đầu vào bên trong (inner input). Có thể hình dung như hai vòng lặp lồng nhau:

~~~text
for each row in outer_input:
    find matching rows in inner_input
    emit each matching pair
~~~

Nếu inner input có index trên cột nối, DBMS có thể thực hiện index lookup cho từng dòng outer. Nếu không có index, một số dạng nested loop có thể phải scan lại inner input nhiều lần, khiến chi phí tăng rất nhanh.

Ví dụ, lấy đơn hàng của một tenant rồi tìm chi tiết tương ứng:

~~~sql
SELECT o.order_id, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42;
~~~

Nếu điều kiện tenant_id chỉ chọn 20 đơn hàng và order_items có index trên order_id, nested loop có thể rất hiệu quả: đọc 20 đơn rồi tra cứu chi tiết cho từng đơn.

### 2.2. Khi nào nested loop phù hợp?

Nested loop thường phù hợp khi:

- Đầu vào outer nhỏ sau khi lọc.
- Inner input có index hỗ trợ điều kiện nối.
- Mỗi lần lookup trả về ít dòng.
- Truy vấn cần dừng sớm sau một số dòng, ví dụ kết hợp ORDER BY và LIMIT trong plan phù hợp.
- Dữ liệu inner thường nằm trong cache hoặc số lần truy cập thấp.
- JOIN là một phần của transaction OLTP cần độ trễ thấp và truy cập ít dòng.

Một outer input rất nhỏ có thể khiến nested loop rẻ hơn việc xây dựng hash table hoặc sắp xếp cả hai đầu vào.

### 2.3. Chi phí và điểm yếu

Chi phí khái niệm của nested loop phụ thuộc số dòng outer và chi phí tìm kiếm phía trong:

~~~text
Chi phí gần đúng
  ≈ chi phí đọc outer
  + số dòng outer × chi phí tìm matching rows ở inner
~~~

Đây là mô hình trực quan, không phải công thức cost chính xác của DBMS. Nếu inner lookup dùng B-tree index, mỗi lần tìm có thể cần đi qua nhiều trang index và truy cập thêm trang bảng. Nếu outer có hàng trăm nghìn dòng, số lần lookup có thể rất lớn.

Các rủi ro thường gặp:

- Outer input lớn hơn nhiều so với ước lượng.
- Inner không có index phù hợp.
- Mỗi lookup phải truy cập nhiều trang rời rạc.
- Inner lookup lặp lại nhiều lần cho các khóa trùng.
- Cache miss và random I/O tăng.
- Một node nested loop có actual loops rất cao.
- Truy vấn có thể trở nên nhạy với tham số vì số dòng outer thay đổi lớn.

Nếu plan cho thấy nested loop với 500.000 loops, hãy xem mỗi vòng lặp làm gì, số dòng trả về mỗi lần và số buffer reads. Không phải cứ nhiều loops là xấu: 500.000 lookup có thể hợp lý nếu inner lookup rất rẻ và dữ liệu nằm trong cache, nhưng cần bằng chứng.

### 2.4. Index cho nested loop

Index trên cột nối ở inner input thường rất quan trọng. Ví dụ:

~~~sql
CREATE INDEX idx_order_items_order_id
ON order_items (order_id);
~~~

Index này giúp tìm các dòng chi tiết theo order_id. Nếu truy vấn còn lọc theo product_id hoặc cần trả quantity, có thể xem xét index ghép hoặc cột bao phủ tùy DBMS và workload.

Tuy nhiên, không nên thêm index chỉ vì thấy nested loop. Cần kiểm tra:

- Index lookup có thực sự là phần tốn thời gian không?
- Inner input có bị truy cập quá nhiều lần không?
- Cột nối có độ chọn lọc và phân bố thế nào?
- Index hiện có đã hỗ trợ lookup chưa?
- Chi phí duy trì index đối với INSERT/UPDATE/DELETE có chấp nhận được không?

### 2.5. Nested loop và dữ liệu trùng

Nếu outer có nhiều dòng cùng khóa nối, inner lookup có thể được lặp lại. Một số DBMS có cơ chế cache kết quả lookup hoặc biến đổi plan, nhưng không nên giả định luôn có. Nếu dữ liệu outer có nhiều khóa trùng và inner lookup tốn kém, hash join có thể hiệu quả hơn vì có thể xử lý tập dữ liệu theo lô.

## 3. Hash join

### 3.1. Cách hoạt động

Hash join thường có hai pha:

1. **Build:** DBMS đọc một đầu vào, thường chọn đầu vào nhỏ hơn theo ước lượng, rồi tạo hash table theo khóa nối.
2. **Probe:** DBMS đọc đầu vào còn lại, tính hash của khóa nối và tìm các dòng khớp trong hash table.

Mô hình khái niệm:

~~~text
hash_table = build_hash_table(build_input)

for each row in probe_input:
    key = hash(row.join_key)
    find matching rows in hash_table
    emit matching pairs
~~~

Hash join thường được dùng cho equi-join, tức điều kiện nối bằng nhau như a.customer_id = b.customer_id. Một số DBMS hỗ trợ các biến thể hoặc điều kiện bổ sung, nhưng không nên giả định hash join phù hợp với mọi phép so sánh phạm vi.

### 3.2. Khi nào hash join phù hợp?

Hash join thường phù hợp khi:

- Hai đầu vào tương đối lớn.
- Điều kiện nối là phép bằng trên các kiểu dữ liệu hỗ trợ hashing.
- Không có index đủ hiệu quả để nested loop.
- Dữ liệu không sẵn có theo thứ tự khóa để merge join.
- Có đủ memory để giữ hash table hoặc ít nhất giảm được số lần partition/spill.
- Truy vấn xử lý theo lô, báo cáo hoặc workload phân tích.

Ví dụ, tổng hợp doanh thu theo khách hàng cần nối orders với customers trên tập dữ liệu lớn:

~~~sql
SELECT c.region, SUM(o.total) AS revenue
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-12-01 00:00:00'
GROUP BY c.region;
~~~

Nếu khoảng thời gian chọn nhiều đơn hàng và không có access path giúp nested loop rẻ, hash join có thể xây dựng bảng băm từ customers rồi dò từng đơn hàng.

### 3.3. Chi phí và bộ nhớ

Hash join cần memory cho hash table và các cấu trúc phụ. Kích thước phụ thuộc số dòng build, kích thước khóa, payload và overhead của hash table. Nếu dữ liệu không vừa vùng memory được cấp, DBMS có thể chia thành nhiều batch hoặc partition và ghi dữ liệu tạm ra storage.

Khi hash join spill:

- Tăng temporary I/O.
- Có thể phải đọc và ghi dữ liệu nhiều lượt.
- Thời gian thực thi tăng mạnh.
- Các truy vấn khác có thể cạnh tranh bộ nhớ và storage.
- Độ trễ p95/p99 có thể xấu đi khi concurrency cao.

Không nên chỉ tăng memory limit cho mọi truy vấn. Một cấu hình đủ cho một hash join riêng lẻ có thể làm nhiều truy vấn đồng thời tiêu thụ quá nhiều RAM. Cần xem memory grant, số batch, temp reads/writes và tổng số truy vấn đang chạy.

### 3.4. Hash join và data skew

Nếu nhiều dòng có cùng một khóa nối, hash table có thể có bucket lớn hoặc một partition trở nên mất cân bằng. Skew làm một phần công việc xử lý lâu hơn phần còn lại, đặc biệt trong plan song song.

Ví dụ, một tenant chiếm 60% đơn hàng. Nếu join theo tenant_id, một khóa lớn có thể chi phối lượng dữ liệu. Hãy kiểm tra phân bố khóa, số dòng thực tế theo nhóm và mức cân bằng giữa worker hoặc partition.

### 3.5. Hash join không luôn cần scan toàn bảng

Optimizer có thể lọc dữ liệu trước khi build hoặc probe. Predicate pushdown, partition pruning và projection giúp giảm kích thước đầu vào. Nếu build side nhỏ sau lọc, hash join có thể rất hiệu quả. Vì vậy, khi đọc plan, hãy xem số dòng đầu vào sau filter, không chỉ kích thước bảng gốc.

## 4. Merge join

### 4.1. Cách hoạt động

Merge join đọc hai đầu vào theo thứ tự của khóa nối và tiến hành ghép các dòng có khóa khớp. Nếu cả hai đầu vào đã được sắp xếp theo khóa, DBMS có thể tiến hành merge tuần tự, di chuyển qua từng đầu vào mà không cần tạo hash table lớn.

Mô hình khái niệm:

~~~text
read next key from left_input
read next key from right_input

compare keys:
  if left_key < right_key: advance left
  if left_key > right_key: advance right
  if equal: emit matching row pairs and advance through matching groups
~~~

Khi một khóa xuất hiện nhiều lần ở cả hai phía, merge join phải tạo đủ các cặp khớp theo semantics JOIN. Ví dụ 3 dòng cùng khóa ở bên trái và 4 dòng cùng khóa ở bên phải có thể tạo 12 cặp kết quả.

### 4.2. Khi nào merge join phù hợp?

Merge join thường phù hợp khi:

- Điều kiện nối dựa trên thứ tự khóa tương thích.
- Cả hai đầu vào đã có thứ tự phù hợp nhờ index hoặc bước xử lý trước đó.
- Dữ liệu lớn và cần xử lý tuần tự.
- Sort order có thể được tái sử dụng cho ORDER BY hoặc bước tiếp theo.
- Hash table lớn có nguy cơ spill hoặc memory hạn chế.
- Cả hai đầu vào được đọc theo thứ tự từ index hoặc cấu trúc lưu trữ phù hợp.

Ví dụ, nếu orders và order_items đều có index trên order_id và DBMS có thể đọc theo thứ tự đó, merge join có thể tránh bước sort riêng. Nhưng phải xem plan thực tế: index tồn tại không có nghĩa optimizer chắc chắn chọn cách đọc theo index.

### 4.3. Chi phí sort

Nếu đầu vào chưa được sắp xếp, DBMS có thể phải sort một hoặc cả hai phía trước khi merge. Sort tiêu thụ CPU và memory; nếu dữ liệu vượt bộ nhớ, nó có thể spill ra storage.

Do đó, merge join không tự động rẻ hơn hash join. So sánh:

- Chi phí đọc đầu vào.
- Chi phí sort cần thiết.
- Khả năng index cung cấp thứ tự.
- Số dòng và độ rộng mỗi dòng.
- Bộ nhớ và temp I/O.
- Khả năng tái sử dụng thứ tự cho ORDER BY hoặc GROUP BY phía sau.

Một merge join có hai sort lớn có thể kém hiệu quả hơn hash join. Ngược lại, nếu đầu vào đã có thứ tự, merge join có thể thực hiện với bộ nhớ nhỏ và I/O tuần tự.

### 4.4. Merge join và duplicate keys

Khi khóa nối không duy nhất, merge join cần xử lý nhóm dòng có cùng khóa ở cả hai phía. Số dòng đầu ra có thể là tích của số dòng trong hai nhóm trùng khóa. Điều này ảnh hưởng đến bộ nhớ tạm, thời gian và lượng kết quả.

Không được giả định khóa join là duy nhất nếu schema không bảo đảm bằng PRIMARY KEY hoặc UNIQUE constraint. Optimizer có thể dùng thống kê để ước lượng số dòng, nhưng duplicate distribution phức tạp có thể làm sai lệch dự đoán.

## 5. So sánh ba thuật toán

| Tiêu chí | Nested loop join | Hash join | Merge join |
|---|---|---|---|
| Cơ chế chính | Lặp outer, tìm match ở inner | Build hash rồi probe | Ghép hai đầu vào theo thứ tự |
| Điều kiện thường phù hợp | Outer nhỏ, inner lookup rẻ | Equi-join trên tập dữ liệu lớn | Đầu vào đã có hoặc dễ tạo thứ tự |
| Vai trò index | Rất hữu ích ở inner input | Không bắt buộc để join | Có thể cung cấp thứ tự đầu vào |
| Nhu cầu memory | Thường thấp đến vừa | Cần memory cho hash table | Thấp nếu đã có thứ tự; sort cần thêm memory |
| Rủi ro chính | Nhiều loops và random lookup | Hash spill, skew, memory pressure | Sort lớn, duplicate groups |
| I/O thường gặp | Lookup lặp lại, có thể random | Scan/build/probe, temp I/O khi spill | Đọc tuần tự; sort I/O nếu cần |
| Mẫu workload | OLTP, point lookup, outer nhỏ | Join dữ liệu lớn, báo cáo | Join dữ liệu lớn có thứ tự phù hợp |
| Có thể dừng sớm? | Có thể trong một số plan | Thường cần build trước probe | Có thể stream theo thứ tự nhưng còn tùy plan |

Bảng trên mô tả xu hướng phổ biến, không phải luật bắt buộc. Mỗi DBMS có các biến thể, thuật toán lai, khả năng song song và quy tắc cost riêng.

## 6. Điều kiện nối và khả năng dùng từng thuật toán

### 6.1. Equi-join

Equi-join dùng phép so sánh bằng:

~~~sql
ON a.customer_id = b.customer_id
~~~

Đây là điều kiện phù hợp phổ biến cho cả nested loop, hash join và merge join. Thuật toán nào tốt hơn phụ thuộc kích thước đầu vào, index, thứ tự, memory và cardinality.

### 6.2. Non-equi join

Non-equi join dùng các điều kiện như lớn hơn, nhỏ hơn, khoảng hoặc điều kiện bất đẳng thức:

~~~sql
SELECT e.employee_id, r.rate_plan
FROM employees AS e
JOIN rate_ranges AS r
  ON e.salary >= r.min_salary
 AND e.salary < r.max_salary;
~~~

Hash join truyền thống không phù hợp trực tiếp với điều kiện range như vậy vì không có một khóa bằng để hash. Nested loop có thể kiểm tra các dòng ứng viên, đặc biệt khi một phía nhỏ hoặc có access path hỗ trợ. Một số DBMS có thể dùng merge join hoặc thuật toán chuyên biệt cho một số non-equi condition. Phải dựa trên plan thực tế và tài liệu DBMS.

### 6.3. Nhiều điều kiện trong ON

Ví dụ:

~~~sql
ON a.customer_id = b.customer_id
AND b.is_active = TRUE
~~~

Điều kiện b.is_active có thể lọc đầu vào b trước khi join, hoặc được đánh giá trong quá trình join. Nếu có index phù hợp hoặc partial index cho tập dòng active, access path có thể thay đổi. Tuy nhiên, vị trí điều kiện trong plan phụ thuộc optimizer và semantics JOIN.

### 6.4. Kiểu dữ liệu và chuyển đổi

Hai cột nối nên có kiểu dữ liệu tương thích. Nếu DBMS phải chuyển kiểu một phía, so sánh có thể tốn CPU và có thể hạn chế index access hoặc hash/sort strategy. Ví dụ nối varchar với integer có thể cần implicit cast.

Hãy kiểm tra kiểu cột, collation, precision và biểu thức chuyển đổi trong plan. Không thay đổi kiểu dữ liệu hoặc thêm CAST tùy tiện nếu điều đó làm thay đổi semantics hay ngăn sử dụng index.

## 7. INNER JOIN, OUTER JOIN và semantics

Ba thuật toán vật lý phải bảo toàn ngữ nghĩa JOIN logic. Một optimizer có thể thực hiện LEFT JOIN bằng các biến thể nested loop, hash hoặc merge join tùy DBMS. Việc chọn thuật toán không được làm mất dòng không khớp ở phía cần bảo toàn.

### 7.1. INNER JOIN

INNER JOIN chỉ trả về các cặp có dòng khớp:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
INNER JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Nếu một khách hàng không có đơn hàng, khách hàng đó không xuất hiện. Nếu có nhiều đơn hàng, khách hàng xuất hiện nhiều lần.

### 7.2. LEFT JOIN

LEFT JOIN giữ tất cả dòng bên trái; nếu không có dòng bên phải khớp, các cột bên phải nhận NULL:

~~~sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id;
~~~

Nested loop, hash và merge join đều có thể có biến thể outer join, nhưng cách triển khai cụ thể phụ thuộc DBMS. Khi đọc plan, cần xác định node có bảo toàn dòng không khớp hay không.

### 7.3. Điều kiện ở ON và WHERE

Với outer join, chuyển predicate giữa ON và WHERE có thể thay đổi kết quả:

~~~sql
-- Giữ khách hàng ngay cả khi không có đơn PAID.
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
~~~

Nếu chuyển o.status = 'PAID' sang WHERE, dòng không có đơn sẽ có o.status = NULL và bị loại. Điều này có thể làm kết quả gần với INNER JOIN. Vì vậy, không rewrite JOIN chỉ để optimizer chọn thuật toán khác nếu chưa xác minh semantics.

### 7.4. NULL trong điều kiện nối

Phép so sánh bằng với NULL không trả TRUE. Hai dòng có join key NULL không tự khớp nhau theo phép bằng thông thường. Một số DBMS cung cấp toán tử null-safe equality, nhưng semantics khác nhau.

Khi benchmark hoặc so sánh hai cách viết JOIN, phải đưa dữ liệu NULL vào bộ kiểm thử nếu cột nối cho phép NULL.

## 8. Join order và kích thước đầu vào

Một truy vấn có nhiều bảng JOIN có thể có nhiều thứ tự kết hợp. Optimizer thường tìm một thứ tự có chi phí ước lượng thấp. Thuật toán JOIN được chọn ở từng cạnh của plan phụ thuộc số dòng trung gian và access path.

Ví dụ:

~~~sql
SELECT o.order_id, c.region, p.category
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN products AS p
  ON p.product_id = o.product_id
WHERE o.created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND c.region = 'NORTH';
~~~

Nếu điều kiện thời gian và region lọc được dữ liệu mạnh, optimizer có thể muốn giảm tập orders hoặc customers trước khi join. Một sai lệch cardinality ở bước đầu có thể làm các bước sau chọn nested loop quá lớn hoặc hash table quá lớn.

Khi phân tích join order:

- Xem estimated rows và actual rows sau từng filter/join.
- Xác định bước nào tạo ra chênh lệch lớn.
- Kiểm tra thống kê trên từng cột và tương quan giữa các cột.
- Xem join key có unique hay không.
- Kiểm tra index và partition pruning.
- Đánh giá kích thước intermediate result.

Không nên ép thứ tự JOIN bằng hint trước khi hiểu nguyên nhân. Hint có thể giúp trong một trường hợp cụ thể nhưng dễ trở thành ràng buộc lỗi thời khi dữ liệu và workload thay đổi.

## 9. Đọc execution plan của JOIN

### 9.1. Các dấu hiệu cần xem

| Dấu hiệu trong plan | Ý nghĩa cần kiểm tra |
|---|---|
| Nested Loop / Nested Loops | Outer rows, inner lookup, actual loops |
| Hash Join / Hash Match | Build/probe side, memory, batches, spill |
| Merge Join | Thứ tự đầu vào, sort node, duplicate keys |
| Index Seek/Scan | Điều kiện seek, số dòng, lookup bổ sung |
| Sort | Số dòng và bytes cần sắp xếp, temp I/O |
| Filter | Số dòng bị loại và vị trí lọc |
| Estimated vs actual rows | Độ chính xác thống kê |
| Parallel workers | Mức cân bằng và lượng công việc mỗi worker |

### 9.2. Ví dụ PostgreSQL

Có thể dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT o.order_id, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42;
~~~

Trong PostgreSQL, plan có thể hiển thị Nested Loop, Hash Join hoặc Merge Join cùng với các node scan bên dưới. Hãy chú ý:

- actual time, rows và loops.
- Estimated rows so với actual rows.
- Buffers: shared hit/read và temp blocks nếu có.
- Hash batches và memory usage nếu plan cung cấp.
- Sort method và disk usage.
- Filter và Rows Removed by Filter.

Thời gian của node có thể được tính theo cách pipeline và lồng nhau; không cộng máy móc thời gian mọi node. EXPLAIN ANALYZE thực sự chạy truy vấn và tạo tải thật. Với truy vấn ghi, có thể làm thay đổi dữ liệu. Chỉ dùng trong môi trường và điều kiện an toàn phù hợp.

### 9.3. Ví dụ MySQL

MySQL 8.0.18 trở lên hỗ trợ EXPLAIN ANALYZE cho truy vấn SELECT:

~~~sql
EXPLAIN ANALYZE
SELECT o.order_id, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42;
~~~

Kết quả iterator tree có thể cho biết thời gian, số dòng và số vòng lặp. Dùng thêm EXPLAIN dạng truyền thống hoặc JSON để xem access type và key được chọn. Cú pháp và trường hiển thị phụ thuộc phiên bản.

### 9.4. Ví dụ SQL Server

SQL Server Actual Execution Plan có thể hiển thị Nested Loops, Hash Match hoặc Merge Join, cùng actual rows, estimated rows, executions, memory grant và spill warning. Có thể kết hợp STATISTICS IO/TIME để đo I/O và CPU/thời gian:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT o.order_id, i.product_id, i.quantity
FROM dbo.orders AS o
JOIN dbo.order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

Các ví dụ trên chỉ minh họa cách đọc công cụ; tên toán tử và cách tính metric không hoàn toàn giống nhau giữa DBMS.

## 10. Thống kê và sai lệch ước lượng

Optimizer dùng statistics để ước lượng số dòng sau filter và JOIN. Nếu ước lượng sai, thuật toán và join order có thể không phù hợp.

Các loại thống kê quan trọng gồm:

- Tổng số dòng và kích thước bảng.
- Số giá trị phân biệt của join key.
- Histogram hoặc phân bố giá trị.
- Tỷ lệ NULL.
- Unique constraint, primary key và foreign key.
- Thống kê tương quan giữa các cột nếu DBMS hỗ trợ.
- Phân bố dữ liệu giữa partition.

Ví dụ, optimizer ước lượng một tenant có 100 đơn hàng nhưng thực tế có 2 triệu. Nested loop có thể bị chọn vì outer được cho là nhỏ. Nếu thực tế lớn, số inner lookups có thể bùng lên.

Khi actual rows khác xa estimated rows:

1. Xác định node đầu tiên có sai lệch lớn.
2. Kiểm tra thống kê và thời điểm cập nhật.
3. Xem skew hoặc tương quan giữa các cột.
4. Kiểm tra giá trị tham số và plan cache.
5. Cập nhật statistics theo cơ chế DBMS nếu cần.
6. Đo lại plan với nhiều tham số đại diện.

Không nên tạo index hoặc ép join algorithm để che giấu mọi vấn đề cardinality. Sửa chất lượng thống kê có thể giúp optimizer chọn plan tốt hơn cho nhiều truy vấn cùng lúc.

## 11. Bộ nhớ, I/O và chạy song song

### 11.1. Memory của hash join

Hash join cần bộ nhớ để lưu hash table và metadata. Nếu memory grant thấp hoặc build side lớn, dữ liệu có thể bị chia batch và spill ra storage. Kiểm tra temp I/O, batch count, memory grant và concurrency.

Tăng memory có thể giúp một truy vấn nhưng làm tổng mức tiêu thụ RAM tăng theo số truy vấn đồng thời. Cần đánh giá ở mức hệ thống, không chỉ một session.

### 11.2. Memory của merge join

Nếu đầu vào đã được sắp xếp, merge join có thể dùng bộ nhớ tương đối thấp. Nếu phải sort trước, memory cần cho sort có thể lớn. Sort spill làm tăng I/O và thời gian.

Index có thứ tự phù hợp có thể loại bỏ sort, nhưng index đó lại tạo chi phí ghi. Hãy đo tổng workload.

### 11.3. I/O của nested loop

Nested loop với nhiều lookup ngẫu nhiên có thể tạo physical I/O cao nếu inner pages không ở cache. Nếu inner lookup lặp lại trên cùng vùng dữ liệu, cache có thể làm chi phí thấp hơn. Hãy quan sát buffer hits, reads và storage latency.

### 11.4. Parallel JOIN

Một số DBMS có thể chạy hash join hoặc merge join song song; nested loop cũng có thể được hỗ trợ trong một số plan. Parallelism có thể tăng throughput nhưng tiêu thụ thêm CPU, memory và I/O, đồng thời có overhead phối hợp worker.

Khi đọc plan song song, kiểm tra số worker thực tế, worker bị thiếu, mất cân bằng dữ liệu và lượng công việc mỗi worker. Một hash join song song nhưng một partition bị skew vẫn có thể khiến một worker kéo dài toàn truy vấn.

## 12. Những tình huống dễ làm JOIN chậm

### 12.1. Nối trước khi lọc

Nếu bảng lớn được JOIN trước khi áp dụng predicate chọn lọc, số dòng trung gian có thể tăng. Optimizer thường có thể push predicate, nhưng subquery, outer join, aggregate hoặc biểu thức có thể giới hạn biến đổi.

Kiểm tra filter có được áp dụng gần scan không và actual rows ở đầu vào JOIN có lớn bất thường không.

### 12.2. Nối bằng biểu thức hoặc chuyển kiểu

Điều kiện:

~~~sql
ON CAST(a.customer_code AS INTEGER) = b.customer_id
~~~

có thể làm giảm khả năng dùng index trên customer_code hoặc làm tăng CPU. Tốt nhất hai cột join có kiểu tương thích từ thiết kế schema. Nếu cần chuyển đổi, hãy xem DBMS có thể dùng expression index hoặc computed/generated column hay không, và kiểm tra plan.

### 12.3. Nối nhiều-nhiều ngoài dự kiến

Nếu join key không duy nhất ở cả hai phía, một nhóm khóa có thể tạo tích số dòng. Ví dụ 100 dòng bên trái và 200 dòng bên phải cùng key có thể tạo 20.000 dòng kết quả cho key đó.

Hãy kiểm tra tính duy nhất, constraint và phân bố duplicate. Nếu nghiệp vụ chỉ cần kiểm tra tồn tại, EXISTS hoặc semi-join có thể phù hợp hơn JOIN thông thường.

### 12.4. Thiếu index ở inner side

Nested loop có thể trở nên đắt nếu inner side không có access path phù hợp. Tuy nhiên, thêm index phải được cân nhắc với chi phí ghi và các truy vấn khác. Với hai đầu vào lớn, hash hoặc merge join có thể phù hợp hơn.

### 12.5. Sort hoặc hash spill

Sort lớn trước merge join hoặc hash table lớn có thể spill. Kiểm tra memory grant, temp I/O, số dòng đầu vào và khả năng lọc sớm. Không mặc định tăng memory là giải pháp duy nhất.

### 12.6. Thống kê cũ hoặc skew

Thống kê không phản ánh phân bố thực tế khiến optimizer chọn sai join order và algorithm. Kiểm tra actual/estimated rows và các tham số có độ chọn lọc khác nhau.

## 13. Cách lựa chọn thuật toán trong thực tế

Không nên tự chọn thuật toán chỉ dựa trên kích thước bảng tổng thể. Hãy xem kích thước đầu vào **sau lọc** và chi phí access path.

| Tình huống | Thuật toán đáng xem xét đầu tiên | Lý do |
|---|---|---|
| Outer chỉ còn vài dòng, inner có index trên join key | Nested loop | Ít lookup, có thể truy cập trực tiếp |
| Hai đầu vào lớn, equi-join, không có thứ tự phù hợp | Hash join | Xây dựng hash và dò theo lô |
| Hai đầu vào đã có thứ tự theo join key | Merge join | Tránh chi phí sort và hash table lớn |
| Một đầu vào lớn nhưng được lọc rất mạnh | Nested loop hoặc hash join | Phụ thuộc số dòng còn lại và index |
| Cả hai đầu vào cần sort lớn | So sánh hash với merge | Chi phí sort có thể làm merge kém lợi |
| Hash join thường xuyên spill | Nested loop hoặc merge nếu access/order phù hợp | Giảm áp lực memory/temp I/O |
| Nested loop có rất nhiều random lookup | Hash hoặc merge nếu đầu vào đủ lớn | Giảm số lần tra cứu lặp |

Bảng này chỉ giúp hình thành giả thuyết. Optimizer có thể chọn phương án khác vì chi phí storage, parallelism, cache, join semantics hoặc thống kê. Đừng ép thuật toán bằng hint trước khi có plan và số liệu.

## 14. Quy trình điều tra và cải thiện JOIN

### Bước 1: Xác định query fingerprint quan trọng

Dùng slow query log, query statistics hoặc trace để tìm truy vấn có tổng thời gian cao, latency p95/p99 xấu hoặc tiêu thụ nhiều CPU/I/O. Xác định tham số đại diện.

### Bước 2: Lấy execution plan

Thu estimated plan và actual plan trong môi trường phù hợp. Ghi nhận thuật toán JOIN, join order, actual rows, estimated rows, loops, buffer reads, sort, hash batches và temp I/O.

### Bước 3: Tìm điểm phát sinh chi phí

Xác định node đầu tiên có chênh lệch cardinality lớn hoặc tiêu thụ nhiều tài nguyên. Kiểm tra filter, index, join key, duplicate, NULL và thứ tự dữ liệu.

### Bước 4: Hình thành giả thuyết

Ví dụ:

- Nested loop quá nhiều vòng do outer input lớn hơn ước lượng.
- Hash join spill vì build side lớn hơn memory grant.
- Merge join tốn sort vì cả hai đầu vào chưa có thứ tự.
- Join tạo quá nhiều dòng vì khóa không duy nhất như giả định.
- Predicate bị áp dụng muộn khiến đầu vào JOIN quá lớn.

Mỗi giả thuyết cần gắn với dấu hiệu đo được.

### Bước 5: Thử một thay đổi có kiểm soát

Có thể thử cập nhật statistics, bổ sung index, sửa predicate, giảm cột trung gian, thay đổi cấu trúc truy vấn hoặc điều chỉnh memory trong phạm vi phù hợp. Thay một yếu tố mỗi lần để xác định nguyên nhân của khác biệt.

Không viết lại SQL chỉ để ép nested loop thành hash join hoặc ngược lại nếu optimizer đã chọn đúng thuật toán. SQL nên mô tả yêu cầu nghiệp vụ rõ ràng; plan được đánh giá bằng kết quả thực tế.

### Bước 6: Kiểm tra tính đúng đắn

So sánh kết quả trước/sau trên cùng dữ liệu, bao gồm:

- Số dòng và duplicate rows.
- Dòng không khớp trong LEFT/RIGHT/FULL JOIN.
- Giá trị NULL ở join key.
- Quan hệ một-một, một-nhiều và nhiều-nhiều.
- Tham số có độ chọn lọc khác nhau.
- ORDER BY, LIMIT và các điều kiện biên.

### Bước 7: Benchmark lại trên workload đại diện

Đo p50/p95/p99, throughput, CPU, memory, I/O, temp usage và lock wait ở nhiều mức concurrency. Kiểm tra tác động lên các truy vấn khác cùng dùng bảng và index.

### Bước 8: Theo dõi sau triển khai

Quan sát query digest, plan regression, tài nguyên và lỗi trong giờ thấp điểm lẫn cao điểm. Nếu lợi ích không ổn định hoặc có tác dụng phụ, thực hiện rollback theo kế hoạch.

## 15. Ví dụ phân tích ba thuật toán với cùng một bài toán

Giả sử cần nối tập orders đã lọc với order_items:

~~~sql
SELECT o.order_id, i.product_id, i.quantity
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = 42
  AND o.created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND o.created_at < TIMESTAMP '2026-11-02 00:00:00';
~~~

### Trường hợp A: một tenant nhỏ, khoảng thời gian hẹp

Điều kiện lọc chỉ trả về 15 đơn hàng. order_items có index trên order_id và mỗi đơn có ít dòng chi tiết.

Nested loop có thể phù hợp: đọc 15 đơn rồi lookup chi tiết từng đơn. Hash join có thể phải scan và build một tập lớn hơn mức cần thiết. Merge join có thể cần sort mà không đem lại lợi ích.

### Trường hợp B: tenant lớn, ngày cao điểm

Điều kiện lọc trả về 500.000 đơn hàng. Inner lookup theo order_id sẽ lặp rất nhiều lần. Nếu order_items cũng lớn, hash join có thể hiệu quả hơn bằng cách build một hash table từ một phía và probe phía còn lại.

Cần kiểm tra build side, memory grant, số batch và spill. Nếu hash table không vừa bộ nhớ, hiệu quả có thể giảm mạnh.

### Trường hợp C: cả hai đầu vào đã có thứ tự phù hợp

Nếu DBMS có thể đọc orders và order_items theo order_id mà không cần sort lớn, merge join có thể xử lý tuần tự. Nó có thể phù hợp với tập dữ liệu lớn, đặc biệt khi thứ tự này được tái sử dụng ở bước tiếp theo.

Tuy nhiên, nếu phải sort cả hai đầu vào, cần so sánh tổng chi phí sort với hash join. Không chọn merge join chỉ vì nó đọc dữ liệu tuần tự.

### Kết luận từ ví dụ

Cùng một câu SQL có thể có thuật toán tốt nhất khác nhau theo tenant, khoảng thời gian, số dòng chi tiết và trạng thái cache. Nếu query plan thay đổi theo tham số, hãy kiểm tra plan cho nhóm tham số đại diện và xem optimizer có xử lý được skew hay không.

## 16. Những ngộ nhận thường gặp

**Nested loop luôn chậm vì có hai vòng lặp.** Với outer nhỏ và inner index lookup rẻ, nested loop thường là lựa chọn rất hiệu quả.

**Hash join luôn tốt cho bảng lớn.** Hash join có thể spill khi thiếu memory, bị ảnh hưởng bởi skew hoặc phải xử lý đầu vào lớn không cần thiết.

**Merge join luôn nhanh vì dữ liệu được đọc tuần tự.** Nếu phải sort hai đầu vào lớn, chi phí sort có thể cao hơn lợi ích của merge.

**Có index thì optimizer phải dùng index.** Optimizer so sánh chi phí. Scan có thể rẻ hơn nếu cần nhiều dòng hoặc index lookup gây random I/O lớn.

**JOIN order trong SQL là thứ tự thực thi.** Optimizer có thể thay đổi thứ tự join nếu phép biến đổi bảo toàn semantics và DBMS cho phép.

**Số dòng hai bảng quyết định số dòng kết quả.** Cardinality kết quả phụ thuộc khóa nối, duplicate, tính duy nhất và phân bố dữ liệu.

**Một thuật toán tốt cho mọi tham số.** Skew và parameter sensitivity có thể khiến một plan phù hợp với nhóm giá trị này nhưng không phù hợp với nhóm khác.

**Estimated cost là thời gian thực tế.** Cost là ước lượng nội bộ của optimizer; cần actual plan và số đo tải để đánh giá.

## 17. Checklist khi phân tích JOIN chậm

- [ ] Đã xác định query fingerprint và tham số đại diện chưa?
- [ ] Đã thu estimated plan và actual plan chưa?
- [ ] Đã so sánh estimated rows với actual rows ở từng đầu vào và đầu ra JOIN chưa?
- [ ] Đã xác định thuật toán JOIN và join order chưa?
- [ ] Nếu nested loop, đã xem outer rows, inner lookup, loops và buffer reads chưa?
- [ ] Nếu hash join, đã xem build/probe side, memory, batches, skew và spill chưa?
- [ ] Nếu merge join, đã xem thứ tự đầu vào, sort cost và duplicate groups chưa?
- [ ] Đã kiểm tra index trên join key và predicate lọc chưa?
- [ ] Đã kiểm tra kiểu dữ liệu, implicit cast và collation của join key chưa?
- [ ] Đã kiểm tra NULL, duplicate và semantics của outer join chưa?
- [ ] Đã xem filter có được áp dụng sớm và intermediate result có quá lớn không?
- [ ] Đã đo CPU, memory, I/O, temp usage và concurrency chưa?
- [ ] Đã xác minh kết quả trước/sau không đổi chưa?
- [ ] Đã benchmark trên nhiều nhóm tham số và tải hỗn hợp chưa?

## Kết luận

Nested loop, hash join và merge join là ba cách phổ biến để thực hiện phép nối, mỗi cách phù hợp với điều kiện dữ liệu và access path khác nhau. Nested loop thường hiệu quả khi outer input nhỏ và inner lookup rẻ; hash join thường phù hợp với equi-join trên tập dữ liệu lớn khi có đủ memory; merge join có lợi khi hai đầu vào đã có thứ tự tương thích hoặc có thể tạo thứ tự với chi phí hợp lý.

Lựa chọn thực tế phụ thuộc số dòng sau lọc, index, cardinality, skew, memory, sort, I/O và mức đồng thời. Execution plan cho biết DBMS đã chọn cách nào; actual rows, loops, buffers, batches, spill và thời gian giúp giải thích kết quả. Hãy xác định node gây chi phí, kiểm tra thống kê và điều kiện nối, thay đổi từng yếu tố, xác minh semantics rồi benchmark lại trên workload đại diện. Đó là cách tối ưu JOIN dựa trên bằng chứng thay vì dựa vào tên thuật toán.

