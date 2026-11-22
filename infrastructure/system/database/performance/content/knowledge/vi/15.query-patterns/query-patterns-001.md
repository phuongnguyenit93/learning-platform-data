# Truy vấn con tương quan và số lần thực thi lặp

Truy vấn con tương quan (correlated subquery) tham chiếu một hoặc nhiều cột từ truy vấn bên ngoài. Sự phụ thuộc này khiến kết quả của truy vấn con gắn với từng dòng hoặc từng giá trị tham số từ truy vấn ngoài. Trong một số kế hoạch, DBMS thực hiện nhánh truy vấn con nhiều lần; một thao tác nhỏ ở mỗi lần gọi vẫn có thể trở thành nút thắt khi số dòng bên ngoài lớn. Ở những trường hợp khác, optimizer có thể biến đổi truy vấn con thành phép nối, semi-join, anti-join, aggregate hoặc dùng bộ nhớ đệm để tránh tính toán lặp.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng phải dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Mẫu truy vấn** giúp người học nhận diện truy vấn con tương quan, hiểu số lần thực thi lặp và đánh giá chi phí phát sinh theo số dòng của truy vấn ngoài. Bài học tập trung vào cách đọc execution plan, phân biệt subquery thực sự chạy lặp với subquery được tối ưu thành dạng khác, lựa chọn EXISTS, NOT EXISTS, JOIN, LATERAL hoặc window function theo ngữ nghĩa, và kiểm chứng thay đổi mà không làm sai kết quả.

Sau bài học, người học có thể:

- Phân biệt correlated subquery với truy vấn con không tương quan.
- Giải thích scalar subquery, EXISTS, NOT EXISTS, IN và các khác biệt về NULL.
- Đọc loops, actual rows, actual executions và các dấu hiệu SubPlan/Dependent Subquery trong execution plan.
- Ước lượng tổng công việc khi một nhánh truy vấn con được gọi nhiều lần.
- Nhận diện khi nào optimizer decorrelate, dùng semi-join/anti-join, materialize hoặc cache kết quả.
- Viết lại truy vấn con thành JOIN, aggregate, LATERAL/APPLY hoặc window function khi giữ nguyên ngữ nghĩa.
- Chọn index hỗ trợ truy vấn con và đánh giá tác động đến bộ nhớ, I/O, concurrency.
- Đo trước/sau bằng workload đại diện và xác nhận tính đúng đắn của kết quả.

## 1. Truy vấn con tương quan là gì?

### 1.1. Truy vấn con không tương quan

Một truy vấn con không tương quan (uncorrelated subquery) không tham chiếu cột của truy vấn bên ngoài. Về mặt logic, kết quả của nó độc lập với từng dòng bên ngoài.

Ví dụ:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE region_id = (
    SELECT region_id
    FROM regions
    WHERE region_code = 'NORTH'
);
~~~

Truy vấn con tìm region_id của vùng NORTH. Giá trị này không phụ thuộc vào từng dòng customers. DBMS có thể thực hiện phần truy vấn con một lần, coi nó như một giá trị hoặc một kết quả trung gian rồi sử dụng trong truy vấn ngoài. Cách thực thi thực tế còn tùy optimizer và kế hoạch.

Một truy vấn con không tương quan vẫn có thể tốn kém nếu nó quét bảng lớn hoặc trả về nhiều dữ liệu. Điểm khác biệt là nó không cần nhận một giá trị mới từ mỗi dòng truy vấn ngoài.

### 1.2. Truy vấn con tương quan

Truy vấn con tương quan tham chiếu một cột của truy vấn ngoài. Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PENDING'
);
~~~

Điều kiện trong truy vấn con sử dụng c.customer_id. Giá trị này đến từ dòng hiện tại của truy vấn ngoài. Về mặt ngữ nghĩa, câu truy vấn kiểm tra với từng khách hàng xem có ít nhất một đơn PENDING hay không.

Mô hình khái niệm:

~~~text
Đọc một dòng customers
        |
        v
Lấy customer_id của dòng đó
        |
        v
Kiểm tra orders có đơn PENDING?
        |
        +---- Có ----> Giữ khách hàng
        |
        +---- Không -> Bỏ khách hàng
        |
        v
Đọc dòng customers tiếp theo
~~~

Đây là cách giải thích logic, không khẳng định DBMS phải thực hiện đúng từng bước tuần tự. Optimizer có thể chuyển đổi EXISTS thành semi-join hoặc một kế hoạch tương đương xử lý tập hợp.

### 1.3. Tương quan không đồng nghĩa chắc chắn chạy lại toàn bộ

Một lỗi diễn giải thường gặp là cho rằng cứ có correlated subquery thì DBMS chắc chắn chạy truy vấn con một lần cho mỗi dòng bên ngoài. Điều đó không đúng trong mọi trường hợp.

Optimizer có thể:

- Chuyển truy vấn con thành JOIN hoặc semi-join.
- Biến đổi thành aggregate rồi nối.
- Dùng hash table hoặc materialization để tái sử dụng kết quả.
- Dùng Memoize hoặc cơ chế cache theo bộ tham số.
- Chạy truy vấn con lặp lại khi kế hoạch giữ dạng parameterized scan.
- Tận dụng index để mỗi lần tra cứu chỉ cần đọc một lượng dữ liệu nhỏ.

Vì vậy, phải đọc execution plan thực tế. Cú pháp SQL thể hiện ngữ nghĩa; kế hoạch cho biết DBMS đã chọn cách thực thi nào.

## 2. Các dạng truy vấn con tương quan phổ biến

### 2.1. Scalar subquery

Scalar subquery trả về một giá trị đơn để dùng trong biểu thức. Ví dụ, lấy ngày tạo đơn gần nhất của mỗi khách hàng:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customers AS c;
~~~

Truy vấn con phụ thuộc customer_id của dòng ngoài. Hàm MAX tạo một giá trị cho mỗi khách hàng. Với bảng orders lớn, nếu customers có nhiều dòng, DBMS có thể phải tính MAX nhiều lần hoặc biến đổi thành aggregate theo customer_id rồi nối.

Scalar subquery có quy tắc quan trọng:

- Nếu truy vấn con trả về một dòng và một cột, giá trị đó được dùng.
- Nếu không có dòng, kết quả scalar thường là NULL.
- Nếu trả về nhiều hơn một dòng trong ngữ cảnh yêu cầu scalar, DBMS thường báo lỗi.

Do đó, khi thay scalar subquery bằng JOIN, phải giữ đúng tính chất một giá trị cho mỗi dòng ngoài. Nếu JOIN trực tiếp với nhiều đơn hàng, dòng khách hàng có thể bị nhân bản.

### 2.2. EXISTS

EXISTS chỉ kiểm tra có ít nhất một dòng phù hợp hay không. DBMS không cần trả toàn bộ các dòng của truy vấn con cho ứng dụng.

Ví dụ:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PENDING'
);
~~~

Ngữ nghĩa là semi-join: giữ dòng phía ngoài nếu tồn tại ít nhất một dòng khớp. Khi đã tìm được một dòng phù hợp, engine có thể dừng tìm cho dòng ngoài đó, tùy kế hoạch và điều kiện.

EXISTS phù hợp khi câu hỏi nghiệp vụ là “có tồn tại hay không”, không phải “có bao nhiêu dòng” hoặc “trả tất cả dòng khớp”.

### 2.3. NOT EXISTS

NOT EXISTS kiểm tra không có dòng nào thỏa điều kiện:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Ngữ nghĩa là anti-join: giữ khách hàng không có đơn hàng. Optimizer có thể thực hiện bằng anti-join hoặc một kế hoạch tương đương.

NOT EXISTS thường là cách diễn đạt rõ ràng khi cần kiểm tra không tồn tại. Cần bảo đảm điều kiện tương quan đúng và có index hỗ trợ nếu tập ngoài lớn.

### 2.4. IN và NOT IN

IN có thể dùng với truy vấn con:

~~~sql
SELECT customer_id
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PENDING'
);
~~~

Với tập giá trị phù hợp, IN có ngữ nghĩa gần với kiểm tra membership và optimizer có thể chuyển thành semi-join.

NOT IN cần chú ý NULL. Nếu tập con chứa NULL, biểu thức so sánh có thể cho kết quả UNKNOWN thay vì TRUE hoặc FALSE. Ví dụ, nếu subquery trả về một giá trị NULL và không có giá trị bằng customer_id, điều kiện NOT IN không nhất thiết trả TRUE. Trong mệnh đề WHERE, UNKNOWN cũng bị loại.

Ví dụ:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders AS o
);
~~~

Nếu orders.customer_id có thể NULL, kết quả có thể khác với mong đợi. Một cách thường dễ kiểm soát hơn là NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Hai cách chỉ tương đương trong điều kiện NULL phù hợp. Không thay NOT IN bằng NOT EXISTS hoặc ngược lại mà chưa kiểm tra nullability và ngữ nghĩa mong muốn.

### 2.5. Subquery trong SELECT, WHERE và FROM

Truy vấn con tương quan có thể xuất hiện ở nhiều vị trí:

- Trong SELECT để tính một giá trị cho mỗi dòng ngoài.
- Trong WHERE để kiểm tra điều kiện tồn tại hoặc so sánh.
- Trong FROM thông qua LATERAL hoặc APPLY để sử dụng cột từ quan hệ đứng trước.
- Trong biểu thức CASE hoặc phép tính khác.

Vị trí cú pháp không tự quyết định hiệu năng. Cần xác định số dòng đầu ngoài, số lần subquery được gọi, khả năng tái sử dụng kết quả và lượng dữ liệu trả về.

## 3. Số lần thực thi lặp và chi phí tổng

### 3.1. Một lần chạy rẻ có thể đắt khi lặp nhiều

Giả sử truy vấn con thực hiện một index lookup mất trung bình 0,2 ms. Nếu truy vấn ngoài trả 10 dòng, chi phí này có thể không đáng kể. Nếu truy vấn ngoài trả 500.000 dòng, cùng lookup có thể được gọi 500.000 lần.

Mô hình ước lượng đơn giản:

\[
\text{Tổng công việc} \approx
\text{Số lần thực thi} \times
\text{Chi phí trung bình mỗi lần}
\]

Đây chỉ là mô hình khái quát. Thời gian thực tế có thể không bằng phép nhân đơn giản do cache, song song, batching, I/O chờ, concurrency, early termination hoặc cache kết quả theo tham số.

Tuy nhiên, số lần thực thi là một tín hiệu quan trọng. Một inner scan chỉ đọc vài dòng nhưng loops rất lớn vẫn có thể tạo nhiều buffer access, CPU và I/O.

### 3.2. Ví dụ correlated scalar subquery

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c
WHERE c.region_id = 5;
~~~

Giả sử bộ lọc region_id trả về 80.000 khách hàng. Nếu subquery được thực thi riêng cho từng khách hàng, nhánh orders có thể chạy 80.000 lần. Nếu mỗi lần đều quét bảng orders, chi phí có thể rất lớn.

Nếu có index trên orders(customer_id), mỗi lần lookup có thể nhanh hơn. Nhưng 80.000 lượt index lookup vẫn có chi phí; số trang được truy cập, cache locality và số đơn trung bình mỗi khách hàng quyết định tổng công việc.

Một phương án khác là tính số đơn theo customer_id một lần trên tập dữ liệu phù hợp rồi nối:

~~~sql
SELECT
    c.customer_id,
    COALESCE(o.order_count, 0) AS order_count
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS o
    ON o.customer_id = c.customer_id
WHERE c.region_id = 5;
~~~

Cách này có thể giảm số lần lặp, nhưng có thể phải aggregate một phần lớn bảng orders dù chỉ cần một vùng khách hàng. Một cách viết khác có thể lọc khách hàng đủ điều kiện trước rồi chỉ tổng hợp orders cho tập đó. Optimizer có thể biến đổi truy vấn theo nhiều cách; phải đo actual plan.

### 3.3. Tác động của số dòng ngoài

Số dòng ngoài thường quyết định số lần một subquery parameterized được gọi nếu kế hoạch giữ dạng lặp. Cần xem số dòng sau lọc, không chỉ số dòng toàn bảng.

Ví dụ:

| Số dòng truy vấn ngoài | Số dòng trung bình subquery | Tổng dòng con gần đúng |
|---:|---:|---:|
| 100 | 2 | 200 |
| 10.000 | 2 | 20.000 |
| 100.000 | 2 | 200.000 |
| 100.000 | 50 | 5.000.000 |

Bảng minh họa cho thấy cùng một subquery có thể thay đổi mức chi phí theo quy mô tập ngoài và fanout. Khi cả số lần gọi và số dòng mỗi lần tăng, lượng công việc tăng nhanh.

### 3.4. Early termination

Một số dạng subquery chỉ cần tìm một dòng đầu tiên:

- EXISTS có thể dừng khi tìm thấy dòng phù hợp.
- NOT EXISTS có thể dừng khi tìm thấy bằng chứng tồn tại, vì khi đó điều kiện “không tồn tại” đã sai.
- Scalar subquery có thể cần đọc đủ dữ liệu nếu dùng MAX, COUNT hoặc phép tổng hợp khác, trừ khi index và kế hoạch hỗ trợ lấy kết quả hiệu quả.
- Subquery có ORDER BY và LIMIT có thể dừng sau khi tìm đủ số dòng, nếu access path cung cấp thứ tự phù hợp.

Do đó, không phải subquery nào cũng phải đọc toàn bộ tập dữ liệu con ở mỗi lần gọi. Hãy xác định phép toán có thể dừng sớm hay cần xử lý tất cả dòng.

## 4. Đọc execution plan để tìm truy vấn con chạy lặp

### 4.1. Những dấu hiệu cần tìm

Khi phân tích kế hoạch, hãy tìm:

- SubPlan, InitPlan hoặc node tương đương.
- Dependent subquery trong MySQL.
- Nested Loops, Apply hoặc parameterized scan.
- Actual rows và loops.
- Actual Number of Executions trong SQL Server.
- Số buffer/logical reads ở nhánh con.
- Rows Removed by Filter và thời gian mỗi lần thực hiện.
- Materialize, Memoize hoặc Hash node cho thấy khả năng tái sử dụng.

Tên node khác nhau theo DBMS và phiên bản. Điều quan trọng là xác định một nhánh có phụ thuộc tham số từ dòng ngoài hay không và được thực hiện bao nhiêu lần.

### 4.2. PostgreSQL: SubPlan và InitPlan

PostgreSQL EXPLAIN có thể hiển thị SubPlan cho một số truy vấn con tương quan. Nếu subplan được thực hiện theo từng dòng ngoài, phần EXPLAIN ANALYZE có thể cho thấy loops lớn.

Ví dụ minh họa:

~~~text
Seq Scan on customers c
  (actual time=0.020..850.000 rows=80000 loops=1)
  Filter: (SubPlan 1)
  SubPlan 1
    -> Index Scan using idx_orders_customer on orders o
         (actual time=0.003..0.006 rows=1 loops=80000)
         Index Cond: (customer_id = c.customer_id)
~~~

SubPlan được gọi 80.000 lần, trung bình trả một dòng. Mỗi lần index scan nhanh, nhưng tổng số lần tra cứu lớn. Cần xem buffer statistics, tổng thời gian và khả năng biến đổi thành semi-join hoặc aggregate.

InitPlan thường được dùng cho truy vấn con không phụ thuộc dòng ngoài và có thể được thực hiện một lần để tạo giá trị dùng lại. Tuy nhiên, không nên chỉ dựa vào tên node; hãy đọc vị trí và thông tin loops trong toàn bộ kế hoạch.

PostgreSQL có thể dùng Memoize cho một số nested-loop parameterized scan. Memoize lưu kết quả theo giá trị tham số để các lần gọi lặp lại cùng tham số có thể lấy lại từ cache. Khi có node Memoize, hãy xem cache hits, misses, evictions và số lần gọi để hiểu lợi ích thực tế. Tính năng và chi tiết output phụ thuộc phiên bản.

### 4.3. SQL Server: Actual Number of Executions và Apply

Trong SQL Server actual execution plan, một correlated subquery có thể được biểu diễn qua Nested Loops, Apply, scalar operator hoặc một dạng kế hoạch đã được biến đổi. Thuộc tính Actual Number of Executions giúp xác định số lần một nhánh được chạy.

Cần xem thêm:

- Actual Number of Rows và số dòng mỗi lần gọi.
- Estimated Number of Rows.
- Logical Reads từ SET STATISTICS IO.
- Actual plan warnings và memory grant.
- Key Lookup hoặc Index Seek lặp lại.
- Có spool/materialization để tái sử dụng kết quả không.

Một Table Spool hoặc Index Spool có thể lưu kết quả trung gian để giảm công việc lặp, nhưng spool cũng tiêu thụ bộ nhớ hoặc tempdb. Hãy xem số lần rebind/rewind và lượng dữ liệu được lưu nếu plan cung cấp.

### 4.4. MySQL: dependent subquery và loops

MySQL EXPLAIN có thể đánh dấu một số truy vấn con là DEPENDENT SUBQUERY hoặc hiển thị iterator trong EXPLAIN ANALYZE với actual rows và loops. Điều này giúp nhận diện subquery phụ thuộc giá trị từ truy vấn ngoài.

Nếu outer query trả nhiều dòng, subquery có thể được thực thi lặp. Tuy nhiên, MySQL cũng có thể chuyển đổi một số IN/EXISTS thành semijoin hoặc áp dụng materialization tùy cấu trúc truy vấn và phiên bản.

Hãy kiểm tra EXPLAIN FORMAT=TREE hoặc EXPLAIN ANALYZE ở phiên bản hỗ trợ, cùng Performance Schema nếu cần thống kê tổng thể. Không kết luận từ nhãn dependent duy nhất; xem số loops và actual rows.

### 4.5. Không cộng thời gian của mọi node

Trong nhiều execution plan, thời gian ở node cha bao gồm thời gian của node con. Nếu cộng tất cả thời gian node, kết quả sẽ bị đếm trùng. PostgreSQL actual time khi loops lớn còn có quy tắc hiển thị theo trung bình mỗi lần thực thi ở các node phù hợp.

Tương tự, buffer statistics ở node cha có thể bao gồm hoạt động của node con. Hãy dùng số liệu ở node gốc để hiểu tổng truy vấn và đi xuống cây để xác định nhánh đóng góp chi phí. Không cộng máy móc mọi giá trị.

## 5. Khi nào optimizer có thể decorrelate?

### 5.1. Decorrelate là gì?

Decorrelate là quá trình optimizer biến đổi một truy vấn con có tham chiếu dòng ngoài thành một dạng xử lý khác, thường là JOIN, semi-join, anti-join hoặc aggregate. Mục tiêu là cho phép DBMS xử lý theo tập hợp thay vì thực hiện một truy vấn con riêng cho từng dòng ngoài.

Ví dụ EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PENDING'
);
~~~

Optimizer có thể biến đổi thành semi-join. Khi đó, kế hoạch có thể dùng hash semi-join, nested-loop semi-join hoặc phương án tương đương. SQL vẫn giữ ngữ nghĩa “có ít nhất một đơn phù hợp”.

### 5.2. Các yếu tố ảnh hưởng khả năng biến đổi

Khả năng decorrelate phụ thuộc vào:

- Loại subquery: scalar, EXISTS, IN, NOT EXISTS hay phép tổng hợp.
- Điều kiện tương quan có thể biểu diễn thành equality hoặc predicate hỗ trợ không.
- Có LIMIT, OFFSET, window function hoặc phép toán phụ thuộc thứ tự không.
- Có aggregate, DISTINCT hoặc GROUP BY làm thay đổi cardinality không.
- Có volatile function hoặc side effect không.
- Có OUTER JOIN và yêu cầu giữ dòng không khớp không.
- Khả năng optimizer và phiên bản DBMS.

Không có quy tắc cú pháp đơn giản bảo đảm mọi correlated subquery được decorrelate. Cần kiểm tra kế hoạch và kết quả thực tế.

### 5.3. Khi optimizer không decorrelate

Nếu kế hoạch giữ một subplan phụ thuộc, có thể có lý do:

- Truy vấn con có semantics khó chuyển thành join đơn giản.
- Kết quả scalar phải được tính riêng theo dòng ngoài.
- Subquery có LIMIT/ORDER BY hoặc phép toán đặc biệt.
- Optimizer ước lượng rằng repeated lookup rẻ hơn materialize toàn bộ.
- Thống kê hoặc metadata không đủ để chọn biến đổi tốt.
- Phiên bản DBMS không hỗ trợ biến đổi mong muốn.

Trong trường hợp đó, hãy đánh giá index, số dòng ngoài, cache, memoization, materialization hoặc viết lại truy vấn nếu có thể giữ nguyên kết quả.

## 6. Chọn JOIN, EXISTS hay aggregate theo ngữ nghĩa

### 6.1. EXISTS thay cho JOIN khi chỉ cần kiểm tra tồn tại

Giả sử muốn liệt kê khách hàng có ít nhất một đơn PENDING.

Dạng EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PENDING'
);
~~~

Dạng JOIN:

~~~sql
SELECT DISTINCT c.customer_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PENDING';
~~~

Nếu một khách hàng có nhiều đơn PENDING, JOIN tạo nhiều dòng khách hàng rồi DISTINCT phải loại trùng. EXISTS biểu đạt trực tiếp yêu cầu tồn tại và có thể tránh tạo các dòng trùng trung gian.

Hai dạng có thể cho cùng tập customer_id trong điều kiện phù hợp, nhưng chi phí và kế hoạch có thể khác. Nếu cần đếm hoặc trả từng đơn hàng, JOIN có thể là lựa chọn đúng. Đừng thêm DISTINCT để che một phép nối có ngữ nghĩa không rõ.

### 6.2. Aggregate trước rồi JOIN khi cần một giá trị tổng hợp

Nếu cần số đơn mỗi khách hàng, scalar COUNT có thể được viết thành aggregate:

~~~sql
SELECT
    c.customer_id,
    COALESCE(o.order_count, 0) AS order_count
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS o
    ON o.customer_id = c.customer_id;
~~~

Dạng này tạo tối đa một dòng aggregate cho mỗi customer_id rồi nối với customers. Có thể phù hợp khi cần kết quả cho nhiều khách hàng.

Nếu chỉ cần một nhóm nhỏ khách hàng, aggregate toàn bộ orders có thể xử lý nhiều dữ liệu không cần thiết. Có thể lọc tập customers trước và nối với orders để giới hạn phần aggregate. Hãy so sánh kế hoạch thực tế.

### 6.3. Scalar subquery với MAX/MIN

Lấy ngày đơn hàng mới nhất:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customers AS c;
~~~

Một index trên (customer_id, created_at) có thể giúp truy cập các đơn của từng khách hàng. Một số DBMS có thể tận dụng thứ tự index để lấy giá trị phù hợp hiệu quả; cách thực thi cụ thể cần xem plan.

Dạng aggregate:

~~~sql
SELECT
    c.customer_id,
    o.latest_order_at
FROM customers AS c
LEFT JOIN (
    SELECT customer_id, MAX(created_at) AS latest_order_at
    FROM orders
    GROUP BY customer_id
) AS o
    ON o.customer_id = c.customer_id;
~~~

Dạng aggregate có thể quét và nhóm tập orders một lần. Dạng scalar có thể hiệu quả khi outer nhỏ và index hỗ trợ tốt. Chọn theo số dòng ngoài, kích thước bảng con, cache và độ chọn lọc.

### 6.4. Lưu ý về COUNT và dòng không có đối tác

Scalar COUNT(*) trên tập rỗng trả về 0 vì aggregate COUNT tạo kết quả. Nhưng nếu chuyển thành LEFT JOIN với bảng aggregate, không có dòng aggregate sẽ tạo NULL ở cột order_count; cần COALESCE về 0 nếu muốn giữ đúng kết quả.

Các aggregate khác như SUM, AVG, MIN và MAX thường trả NULL khi không có dòng đầu vào (trừ khi có quy tắc khác trong biểu thức). Khi viết lại, phải giữ đúng xử lý NULL và kiểu dữ liệu.

## 7. LATERAL và APPLY cho truy vấn con theo từng dòng

### 7.1. LATERAL

Trong PostgreSQL và một số hệ quản trị tương thích, LATERAL cho phép một subquery trong FROM tham chiếu cột từ các quan hệ đứng trước.

Ví dụ, lấy ba đơn hàng mới nhất của mỗi khách hàng:

~~~sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 3
) AS recent ON TRUE;
~~~

Đây là truy vấn con tương quan có thể được thực thi theo từng khách hàng. Nếu có index phù hợp trên (customer_id, created_at DESC), DBMS có thể tìm đến vùng đơn của khách hàng và lấy ba dòng đầu theo thứ tự, thay vì quét toàn bộ đơn của từng khách hàng.

Nếu outer có hàng triệu khách hàng và mỗi lần inner lookup đều tốn kém, kế hoạch có thể vẫn chậm. LATERAL diễn đạt rõ quan hệ phụ thuộc nhưng không tự làm truy vấn nhanh.

### 7.2. SQL Server CROSS APPLY và OUTER APPLY

SQL Server dùng CROSS APPLY hoặc OUTER APPLY cho một số truy vấn con tương quan ở FROM.

Ví dụ:

~~~sql
SELECT
    c.CustomerId,
    recent.OrderId,
    recent.CreatedAt
FROM dbo.Customers AS c
OUTER APPLY (
    SELECT TOP (3)
        o.OrderId,
        o.CreatedAt
    FROM dbo.Orders AS o
    WHERE o.CustomerId = c.CustomerId
    ORDER BY o.CreatedAt DESC
) AS recent;
~~~

CROSS APPLY chỉ giữ dòng bên trái khi phía áp dụng trả dòng phù hợp; OUTER APPLY giữ dòng bên trái và điền NULL khi phía phải không có kết quả. Điều này gần với khác biệt INNER/LEFT trong một số tình huống, nhưng cần kiểm tra ngữ nghĩa cụ thể.

### 7.3. Index hỗ trợ top-N theo từng nhóm

Với truy vấn top-N theo từng khách hàng, index có thể cần:

- Cột tương quan để giới hạn nhóm, ví dụ customer_id.
- Cột sắp xếp tiếp theo, ví dụ created_at DESC.
- Các cột trả về nếu có thể bao phủ mà không làm index quá rộng.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC)
INCLUDE (order_id);
~~~

Cú pháp INCLUDE và khả năng hỗ trợ khác nhau giữa DBMS. Nếu index bao phủ không đáng kể hoặc cột trả về rộng, chi phí duy trì có thể lớn hơn lợi ích.

### 7.4. Khi window function có thể phù hợp hơn

Một cách khác là đánh số thứ tự đơn hàng trong từng nhóm rồi lọc top 3:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM orders AS o
)
SELECT
    c.customer_id,
    r.order_id,
    r.created_at
FROM customers AS c
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
   AND r.rn <= 3;
~~~

Window function có thể xử lý tập orders theo nhóm trong một luồng, nhưng có thể cần sort hoặc xử lý toàn bộ phần dữ liệu tham gia. LATERAL/APPLY với index có thể hiệu quả hơn khi chỉ cần một nhóm nhỏ hoặc N nhỏ. Window function có thể tốt hơn khi cần top-N cho hầu hết nhóm. Cần đo trên dữ liệu và workload thật.

## 8. Index và dữ liệu hỗ trợ truy vấn con

### 8.1. Index trên cột tương quan

Một correlated subquery thường có predicate tham chiếu giá trị ngoài:

~~~sql
WHERE o.customer_id = c.customer_id
~~~

Index trên orders(customer_id) có thể giúp inner lookup tìm nhanh các dòng liên quan. Nếu có thêm điều kiện status, có thể cân nhắc composite index:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Thứ tự cột cần dựa trên các predicate và thứ tự truy cập thực tế. Với truy vấn top-N, có thể cần thêm cột thời gian sau cột customer_id. Không nên tạo index nhiều cột chỉ vì truy vấn có nhiều điều kiện; hãy xem selectivity, kế hoạch và chi phí ghi.

### 8.2. Partial/filtered index

Nếu truy vấn con chỉ tìm đơn PENDING và đây là một tập nhỏ, partial index trong PostgreSQL hoặc filtered index trong SQL Server có thể giảm kích thước:

~~~sql
CREATE INDEX idx_orders_pending_customer
ON orders (customer_id)
WHERE status = 'PENDING';
~~~

Khi status thay đổi vào hoặc ra khỏi PENDING, index cần được cập nhật. Vì vậy, index nhỏ hơn nhưng vẫn có chi phí ghi trên những dòng thay đổi trạng thái.

Optimizer chỉ dùng partial/filtered index khi có thể chứng minh predicate truy vấn phù hợp. Cần kiểm tra kế hoạch với câu lệnh và tham số thực tế.

### 8.3. Covering index và chi phí lookup

Nếu truy vấn con cần trả order_id và created_at, index có thể chứa các cột này để tránh truy cập bảng đầy đủ trong một số engine. Tuy nhiên, index rộng hơn làm tăng dung lượng, buffer cache footprint và chi phí duy trì.

Trong PostgreSQL, Index Only Scan còn phụ thuộc visibility map; có thể vẫn có Heap Fetches. Trong SQL Server, INCLUDE có thể giữ cột payload ở tầng lá. Trong InnoDB, secondary index chứa primary key và có thể cần tra cứu clustered index để lấy cột chưa có trong index.

Hãy xem actual plan và số lần lookup thay vì giả định covering index chắc chắn loại bỏ mọi truy cập bảng.

### 8.4. Tính chọn lọc và số dòng ngoài

Index có thể giúp mỗi lần gọi subquery rẻ hơn, nhưng không giải quyết được mọi vấn đề nếu số lần gọi rất lớn. Nếu outer có 2 triệu dòng và mỗi lần lookup phải đọc nhiều trang, tổng chi phí vẫn cao.

Cần xem cả hai phía:

- Giảm số dòng ngoài nếu có điều kiện lọc hợp lệ.
- Giảm số dòng con bằng predicate phù hợp.
- Dùng index để tra cứu theo tham số.
- Tái sử dụng kết quả khi nhiều dòng ngoài dùng cùng giá trị tham số.
- Chuyển sang xử lý theo tập hợp nếu điều đó giảm công việc tổng thể.

## 9. Materialization, Memoize và tái sử dụng kết quả

### 9.1. Materialization

Materialization là việc tính kết quả trung gian rồi lưu lại để dùng nhiều lần, trong bộ nhớ hoặc vùng lưu trữ tạm. Cách này có thể tránh chạy lại cùng một phép tính, nhưng tạo chi phí xây dựng, lưu trữ và đọc lại.

Nếu truy vấn con không tương quan, materialization có thể hữu ích khi kết quả được dùng nhiều lần. Với truy vấn tương quan, nếu các dòng ngoài lặp lại cùng giá trị tham số, cache theo tham số có thể hữu ích hơn việc materialize toàn bộ kết quả.

Không phải mọi CTE đều được materialize. Một số DBMS có thể inline CTE hoặc tối ưu theo quy tắc riêng. Cần đọc execution plan và tài liệu đúng phiên bản.

### 9.2. Memoize theo tham số

Memoize là cơ chế cache kết quả của một nhánh parameterized theo giá trị tham số. Nếu cùng một customer_id xuất hiện nhiều lần ở outer input, DBMS có thể dùng kết quả đã tính thay vì gọi lại inner scan.

Ví dụ, outer input có 100.000 dòng nhưng chỉ có 1.000 customer_id phân biệt. Nếu kế hoạch có cache hiệu quả theo customer_id, số lần inner thực sự phải chạy có thể gần số khóa phân biệt hơn là tổng số dòng ngoài.

Hiệu quả phụ thuộc:

- Số giá trị tham số phân biệt.
- Kích thước kết quả mỗi tham số.
- Tỷ lệ cache hit/miss.
- Bộ nhớ được cấp và số lần eviction.
- Sự ổn định của dữ liệu trong thời gian thực thi.
- Hỗ trợ của optimizer và phiên bản DBMS.

Nếu mỗi dòng ngoài có một tham số khác nhau, Memoize có thể ít tác dụng. Nếu kết quả mỗi khóa lớn, cache cũng có thể tốn bộ nhớ.

### 9.3. Không giả định cache luôn có lợi

Cache có chi phí quản lý và có thể làm tăng memory pressure. Nếu tỷ lệ hit thấp, DBMS có thể phải lưu nhiều entry nhưng ít được tái sử dụng. Nếu dữ liệu thay đổi liên tục hoặc truy vấn cần semantics mới nhất theo transaction, cách tái sử dụng phải tuân theo visibility và isolation.

Hãy xem hit, miss, eviction, memory usage và loops. Đánh giá trong tải đồng thời vì nhiều truy vấn cùng dùng cache có thể làm tăng áp lực bộ nhớ.

## 10. Ví dụ chẩn đoán truy vấn con chạy lặp

### 10.1. Tình huống

Một dashboard liệt kê khách hàng và số đơn đang mở:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
          AND o.status IN ('NEW', 'PROCESSING')
    ) AS open_order_count
FROM customers AS c
WHERE c.region_id = 12;
~~~

Giả sử vùng có 150.000 khách hàng. Kế hoạch cho thấy SubPlan chạy 150.000 lần. Mỗi lần index scan đọc trung bình 6 dòng. Tổng số dòng được đọc qua nhánh con có thể khoảng 900.000, chưa tính các lần truy cập trang index và heap.

### 10.2. Các câu hỏi cần đặt ra

- Dashboard có cần hiển thị cả 150.000 khách hàng không?
- Có thể phân trang hoặc lọc theo trạng thái khách hàng trước không?
- Index có phù hợp với customer_id và status không?
- Số dòng orders trung bình và cực đại mỗi khách hàng là bao nhiêu?
- Có nhiều khách hàng không có đơn mở không?
- Có thể aggregate tập đơn mở một lần rồi nối không?
- Outer có lặp lại customer_id khiến Memoize hữu ích không?
- Thời gian truy vấn con chiếm bao nhiêu phần trăm tổng thời gian?

### 10.3. Phương án aggregate theo tập

~~~sql
SELECT
    c.customer_id,
    COALESCE(o.open_order_count, 0) AS open_order_count
FROM customers AS c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS open_order_count
    FROM orders
    WHERE status IN ('NEW', 'PROCESSING')
    GROUP BY customer_id
) AS o
    ON o.customer_id = c.customer_id
WHERE c.region_id = 12;
~~~

Phương án này tổng hợp các đơn mở theo customer_id rồi nối với khách hàng. Nếu tập orders mở nhỏ hoặc được lọc hiệu quả, có thể giảm repeated execution. Nếu orders rất lớn và chỉ một nhóm nhỏ khách hàng ở region 12, aggregate toàn bộ đơn mở có thể làm nhiều công việc không cần thiết.

Một phương án khác là xác định trước tập khách hàng trong region 12, sau đó chỉ đọc orders liên quan. Tùy DBMS, optimizer có thể tự đẩy predicate hoặc materialize tập ngoài. Cần so sánh execution plan thay vì chọn theo hình thức SQL.

### 10.4. Đo trước và sau

| Chỉ số | Correlated subquery | Aggregate + JOIN |
|---|---:|---:|
| Số dòng customers | 150.000 | 150.000 |
| Số lần thực thi nhánh orders | 150.000 | Tùy kế hoạch, thường một nhánh aggregate |
| Dòng xử lý phía orders | 900.000 | 820.000 |
| p95 | 780 ms | 310 ms |
| Buffer reads | 28.000 | 11.000 |
| Temp I/O | 0 | 1.200 block |

Các số liệu chỉ minh họa. Dạng aggregate có thể nhanh hơn nhưng tạo temp I/O do hash aggregate hoặc sort; correlated subquery có index tốt có thể nhanh hơn khi outer nhỏ. Hãy xem cả p95, buffer reads, temp I/O, CPU và concurrency.

### 10.5. Kiểm tra tính đúng đắn

Trước khi kết luận, so sánh kết quả của hai truy vấn trên tập dữ liệu có:

- Khách hàng không có đơn nào.
- Khách hàng có một đơn.
- Khách hàng có nhiều đơn mở.
- Khách hàng có đơn ở trạng thái khác.
- Giá trị khóa có NULL nếu schema cho phép.
- Nhiều đơn có cùng timestamp hoặc các giá trị biên.

COUNT trong scalar subquery trả 0 cho tập rỗng. Khi viết lại thành LEFT JOIN với aggregate, phải dùng COALESCE nếu muốn giữ số 0 thay vì NULL. Nếu chuyển thành JOIN thường, khách hàng không có đơn có thể bị loại.

## 11. Quy trình kiểm tra và tối ưu correlated subquery

Một quy trình có thể lặp lại:

1. **Xác định ngữ nghĩa:** truy vấn con trả scalar, kiểm tra tồn tại, kiểm tra không tồn tại hay trả nhiều dòng?
2. **Xác định tập ngoài:** số dòng sau lọc và số giá trị tham số phân biệt.
3. **Đọc execution plan:** tìm SubPlan, Dependent Subquery, Apply, Nested Loop hoặc node tương đương.
4. **Đo số lần thực thi:** loops, Actual Number of Executions, rebind/rewind hoặc iterator loops.
5. **Đo chi phí mỗi lần:** actual rows, buffer/logical reads, thời gian, lookup và số dòng bị lọc.
6. **Kiểm tra khả năng tái sử dụng:** Memoize, spool, materialization, cache hits và misses.
7. **Đánh giá index:** cột tương quan, điều kiện lọc, thứ tự sort và các cột cần trả về.
8. **So sánh phương án:** EXISTS, NOT EXISTS, JOIN, aggregate, LATERAL/APPLY hoặc window function.
9. **Bảo toàn semantics:** kiểm tra duplicate, NULL, OUTER JOIN, scalar cardinality và trường hợp không có dòng.
10. **Đo dưới tải tương đương:** cùng dữ liệu, tham số, mức concurrency và cửa sổ đo.
11. **Kiểm tra tác dụng phụ:** bộ nhớ, temp I/O, chi phí ghi của index và các truy vấn khác.
12. **Ghi kết luận:** nêu số liệu, giả thuyết, thay đổi và điều kiện mà kết quả có hiệu lực.

### 11.1. Bảng đọc plan

| Dấu hiệu | Câu hỏi cần trả lời |
|---|---|
| SubPlan/Dependent Subquery | Có phụ thuộc giá trị dòng ngoài không? |
| InitPlan | Kết quả có thể được tính một lần không? |
| Loops/Executions | Nhánh được gọi bao nhiêu lần? |
| Actual rows | Mỗi lần trả bao nhiêu dòng? |
| Estimated rows | Optimizer dự đoán có sát thực tế không? |
| Index Scan/Seek | Có index hỗ trợ tham số tương quan không? |
| Memoize/Spool | Có tái sử dụng kết quả không? Cache hit/miss thế nào? |
| Buffers/Logical Reads | Mỗi lần gọi và toàn truy vấn chạm bao nhiêu trang? |
| Sort/Hash/Temp | Có tạo dữ liệu trung gian hoặc spill không? |
| Result semantics | Có giữ đúng NULL, duplicate và dòng không khớp không? |

## 12. Những sai lầm thường gặp

**Cho rằng mọi correlated subquery đều chạy một lần cho mỗi dòng ngoài.**  
Optimizer có thể decorrelate, dùng semi-join, materialize hoặc Memoize. Phải đọc plan.

**Cho rằng một index lookup nhanh nghĩa là subquery nhanh.**  
Nếu lookup chạy hàng trăm nghìn lần, tổng công việc vẫn có thể lớn.

**Viết lại EXISTS thành JOIN mà quên duplicate.**  
Một khách hàng có nhiều đơn phù hợp sẽ bị lặp dòng trong JOIN. EXISTS biểu đạt kiểm tra tồn tại.

**Dùng NOT IN mà bỏ qua NULL.**  
Một NULL trong tập con có thể làm kết quả UNKNOWN. Kiểm tra nullability và cân nhắc NOT EXISTS.

**Chuyển scalar subquery thành JOIN trực tiếp với bảng con nhiều dòng.**  
Dòng ngoài có thể bị nhân bản hoặc kết quả không còn là scalar. Cần aggregate hoặc bảo đảm tính duy nhất.

**Aggregate toàn bộ bảng khi chỉ cần một nhóm nhỏ.**  
Aggregate theo tập có thể giảm loops nhưng lại xử lý quá nhiều dữ liệu. Hãy lọc tập ngoài phù hợp.

**Tăng bộ nhớ để chữa mọi repeated execution.**  
Nếu nút thắt là số lần lookup hoặc fanout, tăng bộ nhớ không giải quyết nguyên nhân.

**Tin rằng LATERAL/APPLY tự động nhanh hơn.**  
Chúng biểu đạt quan hệ phụ thuộc; vẫn có thể tạo nested execution lặp. Xem loops và index.

**Dùng window function mà bỏ qua chi phí sort.**  
Window có thể xử lý toàn bộ tập dữ liệu và cần sort lớn. So sánh với top-N lookup theo từng nhóm.

**Cộng thời gian của mọi node trong plan.**  
Node cha thường bao gồm thời gian con; cộng máy móc sẽ đếm trùng.

**So sánh hai truy vấn nhưng không kiểm tra kết quả.**  
Viết lại có thể thay đổi NULL, duplicate, scalar cardinality hoặc hành vi OUTER JOIN. Phải xác nhận semantics.

## 13. Mẫu báo cáo review

Một báo cáo ngắn có thể ghi:

| Hạng mục | Nội dung |
|---|---|
| Truy vấn | Fingerprint và mục tiêu nghiệp vụ |
| Loại subquery | Scalar, EXISTS, NOT EXISTS, IN, LATERAL/APPLY |
| Tập ngoài | Số dòng sau lọc, số tham số phân biệt |
| Nhánh lặp | Node, loops/executions, actual rows mỗi lần |
| Chi phí | Buffers/logical reads, CPU, elapsed time, I/O |
| Tái sử dụng | Memoize, spool, materialization, hit/miss |
| Index | Khóa tương quan, predicate, sort, covering |
| Phương án | JOIN, aggregate, semi/anti join, window function |
| Ngữ nghĩa | NULL, duplicate, dòng không khớp, scalar result |
| Kết quả | p50/p95/p99, throughput, lỗi, temp I/O |
| Quyết định | Giữ truy vấn hiện tại hay viết lại; bằng chứng là gì? |

Ví dụ kết luận có cơ sở:

“Truy vấn ngoài trả 150.000 khách hàng. SubPlan được thực hiện 150.000 lần, mỗi lần trung bình đọc 6 dòng orders qua index. Nhánh con chiếm phần lớn buffer accesses. Thử aggregate theo customer_id rồi LEFT JOIN làm giảm số lần thực thi lặp, nhưng tạo 1.200 temporary blocks. p95 giảm trong workload thử và kết quả giữ khách hàng không có đơn nhờ COALESCE. Cần kiểm tra thêm tải ghi và mức đồng thời trước khi triển khai.”

Kết luận cần nêu rõ dữ liệu quan sát, phương án đã thử và giới hạn của phép đo. Tránh nói “JOIN luôn nhanh hơn subquery” hoặc “subquery luôn chậm” vì hiệu quả phụ thuộc cardinality, index, cache và thuật toán được chọn.

## 14. Kết luận

Truy vấn con tương quan biểu đạt một phép tính hoặc kiểm tra phụ thuộc vào giá trị từ truy vấn ngoài. Nếu DBMS thực thi nhánh con lặp lại, số dòng ngoài, số dòng mỗi lần gọi và chi phí truy cập quyết định tổng công việc. Một index lookup nhỏ vẫn có thể trở thành nút thắt khi loops lớn; ngược lại, correlated subquery có thể rất hiệu quả khi tập ngoài nhỏ, index phù hợp hoặc optimizer tái sử dụng kết quả.

Khi tối ưu, hãy xác định đúng ngữ nghĩa scalar, EXISTS, NOT EXISTS hoặc phép lấy nhiều dòng; đọc execution plan để tìm số lần thực thi và actual rows; xem optimizer có decorrelate, materialize, dùng spool hoặc Memoize không. Chỉ viết lại thành JOIN, aggregate, LATERAL/APPLY hay window function khi có thể bảo toàn duplicate, NULL, dòng không khớp và số lượng kết quả. Đo lại dưới workload tương đương để xác nhận độ trễ, throughput, bộ nhớ và I/O.

Một quyết định tốt dựa trên số liệu của kế hoạch thực thi và phép đo tải, đồng thời giữ nguyên kết quả nghiệp vụ.

## Câu hỏi tự kiểm tra

1. Correlated subquery khác uncorrelated subquery ở điểm nào?
2. Vì sao không thể kết luận mọi correlated subquery đều được thực thi một lần cho mỗi dòng ngoài?
3. Scalar subquery xử lý thế nào khi không có dòng, có một dòng hoặc có nhiều dòng?
4. EXISTS khác JOIN như thế nào khi chỉ cần kiểm tra tồn tại?
5. Vì sao NOT IN có thể cho kết quả khác NOT EXISTS khi tập con chứa NULL?
6. Một inner index scan có actual rows = 3 và loops = 80.000. Tổng số dòng gần đúng qua nhánh là bao nhiêu?
7. Decorrelate là gì và optimizer có thể biến đổi truy vấn con thành những dạng nào?
8. Memoize hoặc spool có thể giảm công việc lặp trong điều kiện nào?
9. Khi nào aggregate theo tập có thể nhanh hơn scalar subquery, và khi nào nó lại làm nhiều công việc hơn?
10. Vì sao LATERAL/APPLY vẫn có thể tạo kế hoạch nested execution tốn kém?
11. Cần kiểm tra những điều kiện nào trước khi thay correlated subquery bằng LEFT JOIN?
12. Hãy mô tả cách dùng execution plan để xác định một correlated subquery đang chiếm phần lớn thời gian truy vấn.

Khi đánh giá truy vấn con tương quan, hãy hỏi: giá trị nào được truyền từ dòng ngoài, nhánh con chạy bao nhiêu lần, mỗi lần đọc bao nhiêu dữ liệu và DBMS có tái sử dụng kết quả hay không. Những câu hỏi đó giúp tìm đúng chi phí và chọn cách viết truy vấn phù hợp với workload.

