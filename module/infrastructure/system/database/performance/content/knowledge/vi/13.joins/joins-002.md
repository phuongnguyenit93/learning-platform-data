# Kích thước hai phía nối, số vòng lặp và lượng dữ liệu trung gian

Hiệu năng của phép nối (JOIN) phụ thuộc nhiều vào số dòng ở cả hai phía, số dòng thực sự khớp, số lần một nhánh được thực thi và lượng dữ liệu trung gian phải tạo ra. Một truy vấn có thể nối hai bảng bằng khóa hợp lệ nhưng vẫn chậm nếu đầu vào lớn hơn dự kiến, một phía bị lặp lại hàng nghìn lần, hoặc mỗi dòng ở phía này khớp với quá nhiều dòng ở phía kia. Khi kết quả trung gian phình to, DBMS phải dùng thêm CPU, bộ nhớ, bộ đệm và I/O; thao tác sort hoặc hash còn có thể tràn ra tệp tạm.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Phép nối** giúp người học phân tích kích thước hai phía nối, số vòng lặp và lượng dữ liệu trung gian. Bài học tập trung vào cách ước lượng cardinality, đọc số dòng thực tế và loops trong execution plan, hiểu fanout và many-to-many join, so sánh nested loop, hash join và merge join, đồng thời tìm cách giảm dữ liệu phải xử lý mà vẫn giữ nguyên ngữ nghĩa truy vấn.

Sau bài học, người học có thể:

- Giải thích cardinality của hai đầu vào và số dòng đầu ra của phép nối.
- Nhận diện fanout, quan hệ một-nhiều và nhiều-nhiều làm kết quả trung gian tăng nhanh.
- Đọc actual rows, estimated rows và loops để xác định nhánh bị thực thi lặp.
- Phân biệt chi phí của nested loop, hash join và merge join theo kích thước đầu vào.
- Nhận diện sort/hash spill, skew và sai lệch ước lượng cardinality.
- Giảm lượng dữ liệu trung gian bằng lọc, chiếu cột, pre-aggregation hoặc thay đổi thứ tự nối khi ngữ nghĩa cho phép.
- Kiểm chứng thay đổi bằng execution plan và phép đo dưới tải đại diện.

## 1. Kích thước hai phía nối quyết định khối lượng công việc

### 1.1. Cardinality của đầu vào và đầu ra

Cardinality là số dòng của một tập kết quả hoặc một quan hệ trung gian. Với phép nối giữa hai đầu vào A và B, cần phân biệt ba đại lượng:

- Cardinality đầu vào A: số dòng mà nhánh A cung cấp cho phép nối.
- Cardinality đầu vào B: số dòng mà nhánh B cung cấp cho phép nối.
- Cardinality đầu ra: số cặp dòng thỏa điều kiện nối.

Nếu A có 10.000 dòng và B có 50.000 dòng, điều đó không có nghĩa phép nối tạo ra 60.000 dòng. Số dòng đầu ra phụ thuộc vào khóa nối, phân bố giá trị, số dòng trùng khóa, điều kiện lọc và loại phép nối.

Với equi-join theo một khóa, có thể hình dung số cặp khớp như sau: với mỗi giá trị khóa v, lấy số lần xuất hiện của v trong A nhân với số lần xuất hiện của v trong B, rồi cộng các tích đó trên các giá trị khớp. Công thức khái niệm:

\[
|A \bowtie B| = \sum_{v} f_A(v) \times f_B(v)
\]

Trong đó f_A(v) và f_B(v) là số dòng mang giá trị v ở hai phía. Công thức này giúp thấy vì sao dữ liệu lệch hoặc khóa trùng nhiều có thể làm kết quả lớn hơn nhiều so với trực giác dựa trên số dòng bảng.

Nếu mỗi dòng A khớp trung bình với 5 dòng B, thì 100.000 dòng A có thể tạo khoảng 500.000 dòng đầu ra. Nếu mỗi dòng A khớp với 100 dòng B, đầu ra có thể lên tới 10 triệu dòng. Kết quả trung gian lớn làm tăng chi phí ở các bước tiếp theo, kể cả khi ứng dụng cuối cùng chỉ cần một phần nhỏ kết quả.

### 1.2. Quan hệ một-một, một-nhiều và nhiều-nhiều

Kiểu quan hệ giữa hai phía ảnh hưởng trực tiếp đến fanout:

| Quan hệ | Đặc điểm | Tác động thường gặp |
|---|---|---|
| Một-một | Mỗi dòng bên A khớp tối đa một dòng bên B | Cardinality đầu ra thường không vượt quá số dòng phía có ít nhất một đối tượng khớp |
| Một-nhiều | Một dòng A khớp nhiều dòng B | Số dòng đầu ra có thể tăng theo số dòng con trung bình |
| Nhiều-nhiều | Nhiều dòng A và nhiều dòng B cùng mang khóa nối | Mỗi nhóm khóa có thể tạo tích số cặp dòng |
| Không khớp | Một số dòng không có đối tác | INNER JOIN loại chúng; OUTER JOIN có thể giữ lại dòng phía được bảo toàn |

Ví dụ, một khách hàng có 12 đơn hàng và mỗi đơn hàng có 4 dòng chi tiết. Nối khách hàng với đơn hàng tạo 12 dòng cho khách hàng đó; nối tiếp với chi tiết đơn hàng tạo 48 dòng. Đây là kết quả đúng của quan hệ một-nhiều nối tiếp.

Nhưng nếu nối thêm bảng sự kiện thanh toán có 3 sự kiện cho mỗi đơn hàng, mỗi dòng chi tiết có thể bị lặp 3 lần. Một khách hàng khi đó tạo 144 dòng. Nếu báo cáo cộng tổng tiền đơn hàng sau phép nối này, tổng có thể bị nhân lên sai vì mỗi đơn hàng xuất hiện nhiều lần.

### 1.3. Fanout và độ khuếch đại dữ liệu

Fanout mô tả số dòng ở phía trong hoặc phía sau mà một dòng đầu vào có thể tạo ra hoặc khớp tới. Fanout cao làm tăng số lần xử lý và kích thước tập kết quả.

Fanout có thể đến từ:

- Khóa nối không duy nhất ở cả hai phía.
- Điều kiện nối thiếu một phần khóa tổng hợp.
- Dữ liệu có nhiều giá trị trùng.
- Một bảng con lưu nhiều bản ghi lịch sử hoặc sự kiện cho cùng thực thể.
- Điều kiện lọc được áp dụng quá muộn.
- Join theo phạm vi hoặc điều kiện không tương đương có thể khớp nhiều dòng.

Nếu một bảng có khóa chính ghép (tenant_id, order_id) nhưng truy vấn chỉ nối theo order_id, dữ liệu giữa tenant có thể bị ghép nhầm và số dòng tăng ngoài dự kiến. Nối trên đầy đủ khóa nghiệp vụ vừa bảo đảm đúng kết quả vừa hạn chế fanout không cần thiết.

### 1.4. Cardinality đầu ra quan trọng hơn số dòng bảng riêng lẻ

Một bảng có hàng triệu dòng vẫn có thể nối hiệu quả nếu điều kiện lọc thu hẹp mỗi đầu vào xuống vài trăm dòng và khóa nối có độ chọn lọc tốt. Ngược lại, hai bảng tương đối nhỏ có thể tạo kết quả rất lớn nếu khóa có ít giá trị phân biệt và nhiều dòng trùng.

Vì vậy, không nên chọn thuật toán JOIN chỉ dựa trên kích thước toàn bảng. Cần xem kích thước sau lọc, số dòng thực tế đi vào phép nối, số dòng khớp và kích thước kết quả mà các bước sau phải xử lý.

## 2. Dữ liệu trung gian phình to như thế nào?

### 2.1. Mỗi phép nối có thể tạo một quan hệ trung gian

Optimizer thường xây dựng kế hoạch theo cây. Đầu ra của một nút JOIN có thể trở thành đầu vào cho JOIN tiếp theo, GROUP BY, DISTINCT, ORDER BY hoặc window function.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
JOIN payment_events AS pe
    ON pe.order_id = o.order_id
GROUP BY c.customer_id;
~~~

Giả sử mỗi đơn hàng có 4 dòng order_items và 3 dòng payment_events. Khi nối cả hai bảng con chỉ bằng order_id, mỗi đơn hàng có thể tạo 4 × 3 = 12 dòng trung gian. Giá trị từng dòng chi tiết bị lặp 3 lần; phép SUM sau đó có thể tính doanh thu cao gấp 3 lần.

Vấn đề ở đây không chỉ là hiệu năng. Kết quả nghiệp vụ cũng sai do phép nối làm nhân bản dòng trước khi tổng hợp. Cần xem lại mục tiêu: nếu chỉ cần xác nhận đơn có thanh toán, có thể dùng EXISTS; nếu cần tổng hợp từng phía, hãy tổng hợp độc lập theo order_id trước khi nối.

### 2.2. Ví dụ tránh nhân bản bằng tổng hợp trước khi nối

Nếu mục tiêu là lấy doanh thu chi tiết theo khách hàng và số sự kiện thanh toán, có thể tổng hợp từng bảng con riêng:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS order_total
    FROM order_items
    GROUP BY order_id
),
payment_counts AS (
    SELECT
        order_id,
        COUNT(*) AS payment_event_count
    FROM payment_events
    GROUP BY order_id
)
SELECT
    o.customer_id,
    SUM(it.order_total) AS revenue,
    SUM(COALESCE(pc.payment_event_count, 0)) AS payment_events
FROM orders AS o
JOIN item_totals AS it
    ON it.order_id = o.order_id
LEFT JOIN payment_counts AS pc
    ON pc.order_id = o.order_id
GROUP BY o.customer_id;
~~~

Mỗi CTE tạo tối đa một dòng cho mỗi order_id. Khi nối với orders, cardinality không bị nhân lên bởi số dòng chi tiết và số sự kiện thanh toán cùng lúc.

Đây là một cách viết có thể làm giảm lượng dữ liệu trung gian và bảo đảm phép tổng hợp đúng. Tuy nhiên, không phải mọi trường hợp đều cần CTE hoặc pre-aggregation. Optimizer có thể inline CTE, đẩy phép toán hoặc chọn kế hoạch khác tùy DBMS và phiên bản. Cần kiểm tra execution plan thực tế và bảo đảm tổng hợp trước không làm thay đổi ngữ nghĩa.

### 2.3. Chi phí của dữ liệu trung gian

Một tập trung gian lớn có thể gây ra:

- Nhiều phép so sánh khóa và kiểm tra điều kiện nối.
- Tăng cấp phát bộ nhớ cho hash table hoặc sort.
- Tăng số trang phải đọc hoặc ghi.
- Temporary I/O khi sort/hash không vừa bộ nhớ.
- Tăng số dòng truyền giữa các nút kế hoạch.
- Tăng CPU cho GROUP BY, DISTINCT hoặc window function ở phía sau.
- Tăng dữ liệu truyền về ứng dụng nếu kết quả không được thu hẹp.

Nếu đầu ra của JOIN lớn hơn nhiều so với kết quả cuối, cần tìm xem có thể loại bỏ dòng sớm hơn hay không. Nhưng phải giữ đúng ngữ nghĩa: lọc sai vị trí có thể làm mất dòng cần thiết trong OUTER JOIN hoặc thay đổi kết quả tổng hợp.

### 2.4. Projection: chỉ giữ cột cần thiết

Mỗi dòng trung gian có chiều rộng (row width). Nếu truy vấn mang theo nhiều cột không cần thiết qua nhiều JOIN, DBMS phải lưu và di chuyển nhiều byte hơn.

Ví dụ, nếu bước sau chỉ cần order_id và customer_id, việc mang theo mô tả sản phẩm dài, JSON hoặc cột nhị phân qua hash join có thể làm hash table lớn hơn đáng kể.

Hãy chỉ chọn cột cần thiết ở từng giai đoạn. Điều này không có nghĩa phải tạo subquery cho mọi bảng; optimizer có thể tự loại bỏ cột không dùng khi có đủ thông tin. Nhưng viết truy vấn rõ ràng, tránh SELECT * và tránh đưa payload lớn vào tập trung gian giúp giảm nguy cơ phình bộ nhớ, đồng thời làm ý định truy vấn dễ kiểm tra.

## 3. Số vòng lặp trong kế hoạch thực thi

### 3.1. Vì sao loops quan trọng?

Một nút trong execution plan có thể được thực hiện nhiều lần. Điều này thường xuất hiện trong nested loop join, correlated subquery hoặc các nhánh được gọi theo từng dòng từ phía ngoài.

Nếu một inner index scan đọc trung bình 3 dòng trong mỗi lần gọi nhưng được thực hiện 100.000 lần, tổng số dòng qua nút đó có thể xấp xỉ 300.000. Một thao tác nhìn rẻ ở mỗi lần gọi có thể trở nên đắt khi loops lớn.

Cần đọc đồng thời:

- Actual rows: số dòng thực tế mà nút tạo ra trong mỗi lần thực hiện theo cách DBMS báo cáo.
- Loops hoặc Actual Number of Executions: số lần nút được thực thi.
- Actual time: thời gian thực tế của nút, cần hiểu cách DBMS tổng hợp khi có nhiều loops.
- Buffers hoặc logical reads: lượng trang được truy cập.
- Rows Removed by Filter: số dòng bị loại tại nút nếu DBMS hiển thị.

Không nên nhìn actual rows mà bỏ qua loops.

### 3.2. Cách đọc loops trong PostgreSQL

PostgreSQL EXPLAIN ANALYZE hiển thị actual rows và loops. Khi loops lớn hơn 1, số rows và thời gian ở nhiều dòng plan được báo dưới dạng trung bình mỗi lần thực hiện. Có thể ước lượng tổng số dòng được tạo bằng actual rows nhân với loops, nhưng cần nhớ đây là phép tính xấp xỉ từ số trung bình đã làm tròn.

Ví dụ:

~~~text
Nested Loop
  (actual time=0.080..420.000 rows=250000 loops=1)
  -> Seq Scan on selected_customers
       (actual time=0.020..8.000 rows=50000 loops=1)
  -> Index Scan using idx_orders_customer on orders
       (actual time=0.003..0.006 rows=5 loops=50000)
       Index Cond: (customer_id = selected_customers.customer_id)
~~~

Nhánh trong được gọi 50.000 lần. Mỗi lần trung bình trả về 5 dòng, tổng khoảng 250.000 dòng. Nếu mỗi lần index scan cần một hoặc nhiều heap lookup, tổng số lần truy cập có thể đáng kể dù một lần riêng lẻ rất nhanh.

Trong PostgreSQL, actual time ở nút có loops lớn cũng cần được đọc theo quy tắc hiển thị của EXPLAIN ANALYZE; không cộng thời gian ở tất cả các nút vì thời gian nút cha bao gồm thời gian của nút con. Tương tự, BUFFERS ở nút cha có thể bao gồm hoạt động của nút con, nên cộng tất cả các dòng sẽ đếm trùng.

### 3.3. SQL Server và MySQL hiển thị số lần thực thi

Trong SQL Server actual execution plan, các thuộc tính như Actual Number of Executions, Actual Number of Rows và số liệu theo thread giúp thấy nhánh được gọi bao nhiêu lần. Cần phân biệt số dòng trung bình mỗi lần với tổng số dòng tùy cách công cụ hiển thị.

MySQL EXPLAIN ANALYZE có thể hiển thị actual rows và loops cho từng iterator. Cách hiển thị và ý nghĩa chi tiết phụ thuộc phiên bản. Hãy đọc đúng output của engine đang dùng thay vì áp dụng nguyên xi cách diễn giải PostgreSQL.

Dù tên trường khác nhau, câu hỏi chung vẫn là: nhánh nào được gọi lặp lại, mỗi lần xử lý bao nhiêu dòng và tổng lượng công việc là bao nhiêu?

### 3.4. Correlated subquery có thể tạo vòng lặp

Một correlated subquery tham chiếu cột của truy vấn bên ngoài có thể được thực thi cho mỗi dòng bên ngoài nếu optimizer không chuyển đổi thành semi-join hoặc dạng kế hoạch khác.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c
WHERE c.region_id = 10;
~~~

Nếu vùng có 200.000 khách hàng và mỗi lần subquery phải scan nhiều dữ liệu, tổng công việc có thể lớn. Một index phù hợp trên orders(customer_id) có thể giúp mỗi lần tra cứu rẻ hơn; trong một số trường hợp, viết lại thành JOIN và GROUP BY có thể giúp optimizer xử lý theo tập hợp.

Không nên mặc định correlated subquery luôn chậm. Nếu truy vấn ngoài chỉ trả vài dòng và inner lookup có index tốt, nested execution có thể rất hiệu quả. Cần xem actual loops và thời gian.

## 4. Nested loop join và kích thước hai phía

### 4.1. Cách hoạt động

Nested loop chọn một phía làm outer input. Với mỗi dòng outer, DBMS tìm các dòng khớp ở inner input. Inner input có thể là một index scan, một bảng đã được materialize hoặc một nhánh kế hoạch khác.

Mô hình công việc khái quát:

\[
\text{Work} \approx |Outer| \times \text{Cost of one inner execution}
\]

Nếu outer nhỏ và inner có index phù hợp, nested loop thường hiệu quả vì chỉ cần tra cứu một số ít khóa. Nếu outer lớn và inner phải scan lại nhiều lần, chi phí có thể tăng rất nhanh.

### 4.2. Khi nested loop phù hợp

Nested loop thường phù hợp khi:

- Một phía sau lọc có ít dòng.
- Phía còn lại có index hỗ trợ điều kiện nối.
- Mỗi lần inner lookup trả về ít dòng.
- Truy vấn có LIMIT và có thể dừng sớm sau khi tìm đủ kết quả.
- Phép nối có tính chọn lọc cao và không cần đọc phần lớn hai bảng.

Ví dụ, tìm thông tin khách hàng cho 20 đơn hàng đã chọn theo order_id có thể dùng nested loop và index lookup rất nhanh.

### 4.3. Khi nested loop trở nên đắt

Nested loop có thể trở thành vấn đề khi:

- Outer input lớn hơn nhiều estimate.
- Inner scan không có index phù hợp.
- Inner node bị thực hiện hàng trăm nghìn hoặc hàng triệu lần.
- Mỗi lần lookup gây I/O ngẫu nhiên.
- Mỗi dòng outer khớp nhiều dòng inner.
- Inner input phải sort hoặc tính toán lại trong mỗi lần gọi.

Nếu inner branch là Seq Scan với loops rất lớn, cần kiểm tra vì sao optimizer không dùng index hoặc không chọn thuật toán khác. Có thể thiếu index, estimate sai, điều kiện nối không sargable hoặc thống kê không phản ánh dữ liệu.

### 4.4. Chẩn đoán bằng số liệu

Khi thấy nested loop, hãy ghi:

1. Actual rows của outer.
2. Loops của inner.
3. Actual rows trung bình mỗi lần inner.
4. Buffer/logical reads của inner.
5. Số dòng đầu ra của join.
6. Thời gian của nút và thời gian toàn truy vấn.
7. Số dòng ước lượng so với thực tế.

Ví dụ, outer 100 dòng, inner 1 dòng mỗi lần và 100 loops có thể là kế hoạch tốt. Outer 500.000 dòng, inner 8 dòng mỗi lần và 500.000 loops tạo khoảng 4 triệu dòng đầu ra; nếu có thêm heap lookup, chi phí sẽ cao hơn đáng kể.

## 5. Hash join và kích thước build/probe

### 5.1. Hai phía của hash join

Hash join thường có hai vai trò:

- **Build side:** DBMS đọc một đầu vào và xây dựng hash table theo khóa nối.
- **Probe side:** DBMS đọc đầu vào còn lại, tính hash cho từng dòng và tìm các dòng khớp trong hash table.

Build side cần đủ bộ nhớ cho hash table và các thông tin cần thiết. Probe side quyết định số lần dò hash. Một đầu vào nhỏ hơn thường phù hợp để build, nhưng optimizer còn xét cardinality, row width, điều kiện, phân bố và chi phí đọc.

Kích thước build side không chỉ là số dòng. Một triệu dòng có khóa nhỏ và payload gọn có thể cần ít bộ nhớ hơn một trăm nghìn dòng mang nhiều cột chuỗi dài hoặc JSON.

### 5.2. Khi hash join phù hợp

Hash join thường phù hợp khi:

- Hai đầu vào có kích thước trung bình hoặc lớn.
- Điều kiện nối là equality có thể băm.
- Không có index lookup rẻ cho từng dòng outer.
- Một phía có thể được đưa vào hash table trong bộ nhớ.
- Truy vấn cần xử lý phần lớn các dòng của hai đầu vào.

Hash join thường tránh phải lặp lại một scan toàn bộ inner cho mỗi dòng outer. Thay vào đó, nó xây dựng hash table một lần rồi probe bằng các dòng phía kia.

### 5.3. Hash spill và nhiều batch

Nếu hash table không vừa bộ nhớ được cấp, DBMS có thể chia dữ liệu thành nhiều batch hoặc partition và ghi dữ liệu trung gian ra đĩa. Điều này làm tăng temporary I/O và thời gian thực thi.

Trong PostgreSQL, EXPLAIN ANALYZE có thể hiển thị số Batches, Memory Usage và temporary blocks. Nếu Batches lớn hơn 1, hash join hoặc hash operation có thể đã phải xử lý nhiều batch. Trong SQL Server, actual plan có thể hiển thị memory grant và cảnh báo hash spill. MySQL có cơ chế và cách báo cáo riêng tùy phiên bản.

Khi thấy spill, hãy kiểm tra:

- Estimated rows và actual rows của build side.
- Row width của đầu vào.
- Số dòng sau lọc.
- Mức memory grant hoặc work memory.
- Số batch và lượng temporary read/write.
- Mức đồng thời của các truy vấn cùng sử dụng bộ nhớ.

Không nên chỉ tăng bộ nhớ ngay. Nếu estimate sai hoặc đầu vào quá lớn do join fanout, sửa thống kê hoặc giảm dữ liệu đầu vào có thể tốt hơn. Tăng bộ nhớ cho một truy vấn có thể làm nhiều truy vấn đồng thời thiếu RAM.

### 5.4. Skew trong hash join

Data skew xảy ra khi một số giá trị khóa xuất hiện nhiều hơn rất nhiều so với phần còn lại. Một số partition hoặc bucket có thể nhận phần lớn dữ liệu, làm thời gian xử lý không cân bằng.

Ví dụ, 90% bản ghi có tenant_id thuộc một tenant lớn, còn các tenant khác chỉ có vài trăm dòng. Một hash partition có thể lớn bất thường. Trong xử lý song song, một worker có thể phải xử lý nhiều dữ liệu hơn các worker khác, làm thời gian toàn truy vấn bị chi phối bởi worker chậm nhất.

Cần xem histogram, most common values, actual rows theo phân vùng hoặc thread nếu DBMS cung cấp, và độ lệch của dữ liệu. Không nên giả định phân bố đều chỉ vì cột có nhiều giá trị phân biệt.

## 6. Merge join và thứ tự dữ liệu

### 6.1. Cách hoạt động

Merge join đọc hai đầu vào theo thứ tự khóa nối và tiến qua chúng để tìm các giá trị bằng nhau. Nếu đầu vào đã được sắp xếp phù hợp, DBMS có thể tránh một số chi phí sort. Nếu chưa, kế hoạch có thể cần sort một hoặc cả hai phía.

Merge join có thể hiệu quả với tập dữ liệu lớn, đặc biệt khi hai đầu vào đã có thứ tự phù hợp từ index hoặc từ bước trước. Tuy nhiên, sort có thể tạo dữ liệu trung gian lớn và spill nếu không đủ bộ nhớ.

### 6.2. Khóa trùng và nhóm giá trị

Nếu một giá trị khóa xuất hiện nhiều lần ở cả hai phía, merge join phải tạo tất cả cặp phù hợp trong nhóm đó. Một nhóm có 100 dòng ở A và 200 dòng ở B có thể tạo 20.000 cặp đầu ra. Thuật toán merge không loại bỏ fanout; nó chỉ tổ chức cách tìm cặp theo thứ tự.

Vì vậy, dù kế hoạch có Merge Join, cardinality đầu ra vẫn có thể rất lớn nếu dữ liệu nhiều-nhiều.

### 6.3. Sort đầu vào và chi phí bộ nhớ

Nếu hai đầu vào không có thứ tự phù hợp, DBMS có thể thêm Sort node trước Merge Join. Hãy xem:

- Số dòng và row width trước sort.
- Sort Method hoặc thông tin memory grant.
- Temporary I/O và spill warning.
- Có index hỗ trợ thứ tự cần thiết không.
- Thứ tự index có phù hợp với điều kiện lọc và hướng sort không.

Một index để tránh sort có thể làm tăng chi phí ghi và dung lượng. Hãy so sánh chi phí đọc, ghi và cache của toàn workload trước khi thêm.

## 7. Join order và tác động của kích thước trung gian

### 7.1. Thứ tự nối thay đổi kích thước dữ liệu

Với ba hoặc nhiều bảng, cùng một tập điều kiện JOIN có thể được thực hiện theo nhiều thứ tự. Một thứ tự có thể tạo tập trung gian nhỏ, trong khi thứ tự khác tạo tập rất lớn trước khi lọc.

Ví dụ, một truy vấn nối customers, orders và order_items. Nếu chỉ có 1% khách hàng thuộc một khu vực cần báo cáo, lọc customers trước khi nối có thể giảm đáng kể số orders và items cần xử lý, nếu điều kiện và ngữ nghĩa cho phép.

Optimizer thường tự chọn join order dựa trên thống kê và chi phí. Nhưng nếu thống kê thiếu hoặc dữ liệu có tương quan, optimizer có thể ước lượng sai và chọn thứ tự không tốt.

### 7.2. Ưu tiên giảm đầu vào sớm khi hợp lệ

Các cách giảm lượng dữ liệu có thể gồm:

- Đẩy điều kiện lọc xuống gần scan nếu ngữ nghĩa cho phép.
- Chỉ lấy các cột cần thiết.
- Giới hạn tập khóa ở phía đầu vào trước khi nối.
- Tổng hợp bảng con theo khóa nối trước khi kết hợp với bảng khác.
- Dùng EXISTS khi chỉ cần biết có dòng khớp.
- Loại bỏ join không cần thiết nếu không ảnh hưởng kết quả.

Không phải mọi predicate đều có thể đẩy qua mọi JOIN. Với LEFT JOIN, điều kiện trong WHERE có thể loại các dòng không khớp và biến kết quả thành hành vi gần INNER JOIN. Nếu cần giữ dòng bên trái không có đối tác, phải hiểu sự khác nhau giữa điều kiện trong ON và WHERE.

Ví dụ:

~~~sql
-- Giữ khách hàng kể cả khi không có đơn hàng PENDING
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PENDING';
~~~

So với:

~~~sql
-- Điều kiện WHERE loại các dòng không có order khớp
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PENDING';
~~~

Hai truy vấn có ngữ nghĩa khác nhau. Không di chuyển predicate chỉ vì muốn giảm cardinality mà chưa xác nhận kết quả nghiệp vụ.

### 7.3. EXISTS và semi-join

Nếu chỉ cần biết một dòng bên A có ít nhất một dòng phù hợp bên B, dùng EXISTS có thể biểu đạt đúng ý định và tránh nhân bản dòng A theo số lượng dòng khớp.

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

Đây là dạng semi-join về mặt ngữ nghĩa. DBMS có thể chuyển đổi thành semi-join plan hoặc cách thực thi tương đương. Nó chỉ cần xác định có ít nhất một dòng phù hợp, không cần trả tất cả cặp dòng như INNER JOIN.

Nếu cần kiểm tra không tồn tại, NOT EXISTS thường diễn đạt anti-join rõ ràng. Cần chú ý khác biệt về NULL khi so sánh NOT IN với NOT EXISTS.

### 7.4. Pre-aggregation và bảo toàn ngữ nghĩa

Tổng hợp trước khi nối có thể giảm số dòng, ví dụ tính tổng order_items theo order_id trước khi nối orders. Nhưng cần xác định phép tổng hợp có thể thực hiện độc lập hay không.

Nếu kết quả cần tính trung bình có trọng số, distinct count hoặc logic phụ thuộc các dòng từ nhiều bảng, tổng hợp sớm không đúng cách có thể làm thay đổi kết quả. Phải chứng minh rằng phép biến đổi bảo toàn ngữ nghĩa, rồi so sánh kết quả trên tập dữ liệu kiểm thử.

## 8. Sai lệch ước lượng cardinality

### 8.1. Optimizer dựa vào thống kê

Optimizer sử dụng số dòng bảng, số giá trị phân biệt, histogram, tần suất giá trị phổ biến, null fraction và các thống kê khác để ước lượng số dòng sau lọc và sau JOIN.

Nếu thống kê cũ hoặc không phản ánh phân bố thực tế, estimated rows có thể khác actual rows rất lớn. Hệ quả là optimizer có thể:

- Chọn nested loop trong khi outer thực tế rất lớn.
- Chọn hash join với build side lớn hơn khả năng bộ nhớ.
- Chọn sai join order.
- Đánh giá thấp fanout và kích thước trung gian.
- Cấp phát memory grant không phù hợp.
- Chọn scan hoặc index lookup không tối ưu.

### 8.2. Tương quan giữa các cột

Giả sử bảng orders có tenant_id và status. Một tenant lớn có tỷ lệ đơn PENDING cao hơn nhiều tenant khác. Nếu optimizer giả định hai cột độc lập, nó có thể đánh giá sai số dòng thỏa cả hai điều kiện.

Tương tự, hai bảng có khóa nối phân bố lệch giống nhau có thể tạo nhiều cặp khớp hơn ước lượng dựa trên phân bố trung bình.

Trong PostgreSQL, extended statistics có thể mô tả một số quan hệ giữa nhiều cột trong cùng bảng, chẳng hạn dependencies, ndistinct hoặc most-common-value combinations tùy phiên bản. Thống kê này không tự giải quyết mọi tương quan giữa hai bảng; cần đọc tài liệu và đo actual rows.

Trong SQL Server, statistics và histogram cung cấp thông tin cho optimizer, nhưng histogram cơ bản được xây dựng trên cột đầu tiên của statistics object. Thống kê đa cột và cách cardinality estimator xử lý tương quan có giới hạn riêng. MySQL và Oracle cũng có cơ chế histogram và thống kê riêng theo phiên bản.

### 8.3. So sánh estimated rows với actual rows

Khi đọc kế hoạch, tìm các nút có sai lệch lớn giữa estimate và actual. Ví dụ:

~~~text
Hash Join
  (cost=... rows=5000 ...)
  (actual time=... rows=850000 loops=1)
~~~

Nếu actual rows lớn gấp 170 lần estimate, các nút phía trên có thể đã được chọn dựa trên một mô hình dữ liệu sai. Hãy truy ngược xuống:

- Scan đầu vào có estimate sai không?
- Predicate có phân bố lệch không?
- Có tương quan giữa các cột không?
- Join key có trùng lặp nhiều không?
- Có thiếu điều kiện nối hoặc thiếu một phần composite key không?
- Thống kê có cũ hoặc sample chưa đại diện không?

Đừng chỉ nhìn nút gốc. Sai lệch đầu tiên xuất hiện ở một nút con thường là nơi hữu ích để bắt đầu chẩn đoán.

## 9. Ví dụ phân tích một kế hoạch JOIN

### 9.1. Truy vấn

Một báo cáo tìm khách hàng trong một vùng và nối với đơn hàng cùng chi tiết:

~~~sql
SELECT
    c.customer_id,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE c.region_id = 7
  AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
GROUP BY c.customer_id;
~~~

### 9.2. Dấu hiệu giả định

Kế hoạch PostgreSQL giả định có thể cho thấy:

~~~text
HashAggregate
  (actual rows=12000 loops=1)
  -> Nested Loop
       (actual rows=1800000 loops=1)
       -> Hash Join
            (actual rows=120000 loops=1)
            -> Seq Scan on orders
                 (actual rows=120000 loops=1)
            -> Hash
                 (actual rows=9000 loops=1)
                 -> Seq Scan on customers
                      Filter: (region_id = 7)
                      (actual rows=9000 loops=1)
       -> Index Scan using idx_order_items_order on order_items
            (actual rows=15 loops=120000)
~~~

Đây là đầu ra mô phỏng để minh họa cách đọc, không phải output của một hệ thống thật. Nhánh order_items được gọi 120.000 lần, mỗi lần trung bình trả 15 dòng, tạo khoảng 1,8 triệu dòng cho bước nối cuối. Nếu index lookup và buffer access lặp nhiều lần, chi phí có thể cao. Cấu trúc này minh họa Nested Loop ở bước nối order_items; Hash Join phía trong đã tạo tập orders phù hợp với customers.

### 9.3. Các câu hỏi chẩn đoán

- Có index phù hợp trên orders(customer_id) và order_items(order_id) không?
- Bộ lọc ngày có thể giảm số orders trước khi nối không?
- Có thể chỉ lấy order_id và customer_id trước khi nối chi tiết không?
- Số dòng trung gian 1,8 triệu có hợp lý với nghiệp vụ không?
- Estimate có gần actual rows không?
- Hash table hoặc sort phía sau có spill không?
- Cột và row width mang qua các join có cần thiết hết không?
- Workload có phân bố tenant hoặc khách hàng lệch không?

### 9.4. Một hướng viết lại

Nếu chỉ cần doanh thu theo khách hàng, có thể tổng hợp chi tiết theo order_id trước, rồi nối với orders đã lọc:

~~~sql
WITH filtered_orders AS (
    SELECT order_id, customer_id
    FROM orders
    WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
),
item_totals AS (
    SELECT
        oi.order_id,
        SUM(oi.quantity * oi.unit_price) AS order_total
    FROM order_items AS oi
    JOIN filtered_orders AS fo
        ON fo.order_id = oi.order_id
    GROUP BY oi.order_id
)
SELECT
    fo.customer_id,
    SUM(it.order_total) AS revenue
FROM filtered_orders AS fo
JOIN item_totals AS it
    ON it.order_id = fo.order_id
JOIN customers AS c
    ON c.customer_id = fo.customer_id
WHERE c.region_id = 7
GROUP BY fo.customer_id;
~~~

Đây là một phương án cần thử, không phải cam kết sẽ nhanh hơn. Optimizer có thể biến đổi CTE hoặc chọn lại thứ tự join. Nếu lọc customers trước giúp giảm orders đáng kể, một phương án khác là tạo tập customer đủ điều kiện rồi nối. Hãy so sánh actual plan, intermediate rows, loops, buffers, temp I/O và kết quả nghiệp vụ trước khi quyết định.

## 10. Quy trình chẩn đoán kích thước và loops

Khi một truy vấn có nhiều JOIN chậm, có thể thực hiện theo trình tự:

1. **Xác định kết quả mong muốn:** số dòng và grain của kết quả cuối là gì? Mỗi dòng đại diện khách hàng, đơn hàng hay chi tiết?
2. **Đếm cardinality đầu vào:** số dòng sau mỗi điều kiện lọc trước khi JOIN.
3. **Kiểm tra tính duy nhất của khóa:** khóa nối có duy nhất ở phía nào? Có thiếu thành phần composite key không?
4. **Đọc estimated và actual rows:** tìm nút đầu tiên có sai lệch lớn.
5. **Đọc loops:** xem inner branch hoặc subquery bị gọi bao nhiêu lần.
6. **Đo fanout:** số dòng trung bình và cực đại mà mỗi khóa tạo ra.
7. **Đọc thuật toán JOIN:** nested loop, hash join hay merge join; xem build/probe, sort và lookup.
8. **Đánh giá intermediate width:** có mang theo cột lớn hoặc cột không cần thiết không?
9. **Kiểm tra spill và I/O:** memory grant, hash batches, sort method, temp read/write, buffers.
10. **Thử thay đổi:** lọc sớm, index phù hợp, EXISTS, pre-aggregation hoặc join order khi ngữ nghĩa cho phép.
11. **Đo lại dưới tải tương đương:** giữ dữ liệu, tham số, cache policy và concurrency.
12. **Xác nhận tính đúng:** so sánh kết quả, đặc biệt với duplicate, NULL và OUTER JOIN.

### 10.1. Đo phân bố fanout bằng SQL

Một truy vấn thống kê có thể giúp phát hiện khóa nối có nhiều dòng ở phía con:

~~~sql
SELECT
    order_id,
    COUNT(*) AS child_rows
FROM order_items
GROUP BY order_id
ORDER BY child_rows DESC
LIMIT 20;
~~~

Để xem phân bố tổng quát:

~~~sql
WITH fanout AS (
    SELECT order_id, COUNT(*) AS child_rows
    FROM order_items
    GROUP BY order_id
)
SELECT
    COUNT(*) AS parent_keys,
    AVG(child_rows) AS avg_children,
    MAX(child_rows) AS max_children
FROM fanout;
~~~

Trung bình có thể che giấu một số khóa nóng có hàng nghìn dòng con. Hãy xem percentile hoặc histogram nếu cần, đồng thời chọn cửa sổ dữ liệu phù hợp với workload.

### 10.2. Kiểm tra khóa có bị thiếu thành phần không

Giả sử bảng orders có khóa duy nhất theo (tenant_id, order_id), bảng order_items cũng lưu cả hai cột. Nối chỉ bằng order_id có thể ghép dòng giữa các tenant nếu order_id không duy nhất toàn cục.

Một phép kiểm tra dữ liệu:

~~~sql
SELECT order_id, COUNT(DISTINCT tenant_id) AS tenant_count
FROM orders
GROUP BY order_id
HAVING COUNT(DISTINCT tenant_id) > 1;
~~~

Nếu kết quả có dòng, order_id riêng lẻ không đủ để định danh toàn cục. JOIN phải dùng đầy đủ tenant_id và order_id để bảo đảm tính đúng đắn và tránh fanout không mong muốn.

## 11. Những sai lầm thường gặp

**Chỉ nhìn số dòng của hai bảng gốc.**  
Kích thước sau lọc và cardinality đầu ra mới quyết định khối lượng công việc của JOIN.

**Cho rằng JOIN hai bảng nhỏ luôn tạo kết quả nhỏ.**  
Khóa trùng ở cả hai phía có thể tạo nhiều-nhiều và làm số cặp tăng theo tích số.

**Bỏ qua loops của inner node.**  
Một index lookup rẻ nhưng được gọi hàng trăm nghìn lần vẫn có thể trở thành nút thắt.

**Cho rằng nested loop luôn xấu.**  
Nested loop phù hợp khi outer nhỏ và inner lookup hiệu quả. Chỉ kết luận sau khi xem actual rows, loops và I/O.

**Cho rằng hash join luôn cần tăng bộ nhớ.**  
Hash spill có thể do estimate sai, đầu vào lớn hoặc row width lớn. Giảm đầu vào và sửa thống kê có thể hiệu quả hơn.

**Nối nhiều bảng con rồi mới tổng hợp.**  
Các quan hệ một-nhiều nối liên tiếp có thể nhân bản dòng và làm tổng hợp sai. Hãy xác định grain và pre-aggregate khi phù hợp.

**Dùng DISTINCT để che kết quả bị nhân bản.**  
DISTINCT có thể tạo sort/hash lớn và che giấu lỗi điều kiện JOIN. Sửa khóa nối hoặc mô hình dữ liệu trước.

**Đẩy predicate qua OUTER JOIN mà không kiểm tra ngữ nghĩa.**  
Di chuyển điều kiện giữa ON và WHERE có thể làm thay đổi tập dòng được giữ lại.

**Tin estimated rows mà không kiểm tra actual rows.**  
Sai lệch cardinality có thể khiến optimizer chọn thuật toán và join order không phù hợp.

**Chỉ đo thời gian truy vấn mà không đo kết quả và tải.**  
Một kế hoạch nhanh hơn nhưng trả sai số dòng hoặc làm ghi, I/O và p99 của workload khác xấu đi không phải là tối ưu hợp lệ.

## 12. Mẫu ghi nhận khi review JOIN

| Hạng mục | Nội dung cần ghi |
|---|---|
| Mục tiêu truy vấn | Grain của mỗi dòng kết quả và yêu cầu nghiệp vụ |
| Hai phía nối | Số dòng trước/sau lọc, kích thước và row width |
| Khóa nối | Cột nối, uniqueness, NULL và thành phần khóa ghép |
| Fanout | Số dòng khớp trung bình, lớn nhất và phân bố |
| Cardinality | Estimated rows so với actual rows tại từng nút |
| Loops | Số lần thực thi của inner node/subquery |
| Thuật toán | Nested loop, hash join hoặc merge join |
| Bộ nhớ | Hash table, sort, memory grant/work memory |
| Dữ liệu tạm | Spill, batches, temp read/write |
| I/O | Buffer/logical reads, physical I/O và latency |
| Thay đổi | Filter, index, EXISTS, pre-aggregation hoặc join order |
| Kiểm chứng | Latency, throughput, lỗi, số dòng và tính đúng kết quả |

Một nhận định có cơ sở có thể viết như sau:

“Sau khi lọc, phía orders còn 80.000 dòng. Inner lookup sang order_items được thực hiện 80.000 lần, trung bình 12 dòng mỗi lần, tạo khoảng 960.000 dòng trung gian. Phân bố child_rows có một số order lớn bất thường. Cần kiểm tra liệu báo cáo có cần toàn bộ chi tiết hay có thể tổng hợp theo order_id trước khi nối; sau đó so sánh loops, temp I/O và kết quả tổng.”

Cách ghi này nêu rõ số liệu, giả thuyết và bước kiểm chứng. Nó giúp reviewer đánh giá nguyên nhân mà không phải dựa trên tên thuật toán JOIN đơn lẻ.

## 13. Kết luận

Hiệu năng JOIN phụ thuộc vào kích thước hai đầu vào sau lọc, số dòng thực sự khớp, fanout của từng khóa, số lần inner branch được gọi và lượng dữ liệu trung gian được truyền sang các bước tiếp theo. Nested loop có thể rất nhanh với outer nhỏ và index lookup tốt nhưng đắt khi loops lớn. Hash join xử lý tập lớn hiệu quả khi build side phù hợp bộ nhớ, nhưng có thể spill nếu cardinality hoặc row width vượt dự kiến. Merge join tận dụng thứ tự dữ liệu nhưng vẫn chịu ảnh hưởng của sort và nhóm khóa trùng.

Khi tối ưu, hãy xác định grain của kết quả, kiểm tra đầy đủ khóa nối, đo actual rows và loops, tìm nút đầu tiên có sai lệch cardinality, rồi giảm dữ liệu trung gian bằng lọc, projection, EXISTS hoặc pre-aggregation khi ngữ nghĩa cho phép. Luôn kiểm tra tác động của OUTER JOIN, NULL và duplicate để bảo toàn kết quả.

Một phép tối ưu chỉ được xác nhận khi execution plan và số liệu tải cho thấy lượng công việc giảm, độ trễ hoặc thông lượng cải thiện, bộ nhớ và I/O ổn định, đồng thời kết quả nghiệp vụ vẫn chính xác.

## Câu hỏi tự kiểm tra

1. Cardinality đầu vào và cardinality đầu ra của JOIN khác nhau như thế nào?
2. Vì sao một khóa trùng ở cả hai phía có thể tạo ra nhiều-nhiều và làm kết quả tăng theo tích số?
3. Một inner index scan có actual rows = 4 và loops = 50.000. Tổng số dòng gần đúng mà nút này tạo ra là bao nhiêu?
4. Khi nào nested loop phù hợp hơn hash join?
5. Hash join dùng build side và probe side để làm gì? Vì sao row width của build side quan trọng?
6. Merge join có loại bỏ fanout do khóa trùng hay không? Giải thích.
7. Vì sao nối order_items và payment_events cùng theo order_id có thể làm SUM doanh thu bị nhân bản?
8. EXISTS khác INNER JOIN như thế nào khi chỉ cần kiểm tra có dòng phù hợp?
9. Vì sao di chuyển điều kiện từ ON sang WHERE trong LEFT JOIN có thể thay đổi kết quả?
10. Hãy mô tả cách tìm nguyên nhân khi estimated rows của một Hash Join thấp hơn actual rows hàng trăm lần.

Khi đọc một kế hoạch JOIN, hãy luôn hỏi: mỗi phía đưa vào bao nhiêu dòng, một dòng có thể khớp bao nhiêu dòng, nhánh nào chạy lặp lại và dữ liệu trung gian lớn đến đâu. Bốn câu hỏi này tạo nền tảng để chọn access path và cải thiện truy vấn dựa trên bằng chứng.

