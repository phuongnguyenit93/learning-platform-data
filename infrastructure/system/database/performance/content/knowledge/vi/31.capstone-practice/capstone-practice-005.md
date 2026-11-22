# Tối ưu phép nối và tổng hợp có dữ liệu trung gian lớn

## 1. Bài toán: kết quả chỉ có vài nghìn dòng nhưng truy vấn xử lý hàng trăm triệu dòng

Một báo cáo có thể chỉ trả về vài trăm khách hàng, vài chục nhóm sản phẩm hoặc một tổng doanh thu theo tháng. Tuy nhiên, để tạo kết quả đó, database có thể phải nối nhiều bảng chi tiết, tạo tập dữ liệu trung gian rất lớn, sắp xếp hoặc băm hàng triệu dòng rồi mới nhóm và loại bỏ phần lớn dữ liệu.

Hiện tượng này thường xuất hiện khi:

- Nối các bảng có quan hệ một-nhiều hoặc nhiều-nhiều mà không kiểm soát độ nhân bản của dòng.
- Áp dụng bộ lọc quá muộn, sau khi join đã tạo ra nhiều dòng không cần thiết.
- Tổng hợp sau khi nối nhiều bảng chi tiết độc lập, làm số đo bị nhân lên và dữ liệu trung gian phình to.
- Optimizer ước lượng sai số dòng do statistics cũ, dữ liệu lệch hoặc tương quan giữa các cột.
- Chọn join algorithm không phù hợp với kích thước đầu vào hoặc access path.
- Hash aggregate, hash join hoặc sort không đủ bộ nhớ và phải spill ra vùng tạm.

Trong module DATABASE_PERFORMANCE, mục tiêu là tối ưu hiệu năng dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Bài thực hành tổng hợp này tập trung vào cách đọc và kiểm soát cardinality, giảm dữ liệu trung gian, chọn thứ tự và thuật toán join, tổng hợp trước khi nối khi ngữ nghĩa cho phép, thiết kế index, nhận diện memory spill và kiểm chứng kết quả. Một truy vấn nhanh hơn chỉ có giá trị khi kết quả vẫn đúng với quy tắc nghiệp vụ.

## 2. Phân biệt kích thước kết quả với khối lượng xử lý

Có ba đại lượng cần tách biệt:

1. **Output cardinality:** số dòng truy vấn trả về cuối cùng.
2. **Intermediate cardinality:** số dòng được tạo ra ở các operator giữa execution plan, chẳng hạn sau join hoặc trước aggregate.
3. **Work volume:** tổng lượng công việc để tạo ra các dòng đó, gồm số dòng đọc, số lần truy cập, số byte, phép so sánh, hash, sort, spill và I/O.

Một truy vấn trả về 500 dòng vẫn có thể tạo 50 triệu dòng sau join rồi mới GROUP BY. Khi đó output nhỏ không chứng minh truy vấn hiệu quả.

Ngoài số dòng, cần xem **row width** (độ rộng dòng). Một tập 2 triệu dòng chỉ chứa khóa và vài số nguyên có thể nhẹ hơn nhiều so với 2 triệu dòng chứa JSON, văn bản dài hoặc nhiều cột không cần thiết. Khi hash hoặc sort, bộ nhớ phụ thuộc cả số dòng, độ rộng, cấu trúc nội bộ và overhead của engine.

Khi đọc execution plan, không chỉ nhìn operator cuối cùng. Hãy tìm nơi số dòng tăng đột biến, nơi estimate bắt đầu lệch và nơi dữ liệu được sort/hash hoặc ghi ra vùng tạm.

## 3. Cardinality của phép nối và hiện tượng row explosion

### 3.1. Quan hệ một-một, một-nhiều và nhiều-nhiều

Giả sử:

- Một khách hàng có nhiều đơn hàng.
- Một đơn hàng có nhiều dòng hàng.
- Một đơn hàng có thể có nhiều lần thanh toán.

Join Customers với Orders thường tạo một dòng cho mỗi đơn hàng của khách hàng. Join tiếp OrderItems làm mỗi đơn hàng lặp lại theo số dòng hàng. Nếu nối thêm Payments, mỗi dòng hàng có thể lặp lại theo số lần thanh toán của đơn đó.

Nếu một đơn có 8 dòng hàng và 3 lần thanh toán, nối trực tiếp hai bảng chi tiết có thể tạo 8 × 3 = 24 dòng cho một đơn. Nếu báo cáo tính tổng doanh thu từ OrderItems và tổng tiền thanh toán từ Payments sau phép nối này, mỗi giá trị sẽ bị nhân theo số dòng của bảng chi tiết còn lại.

### 3.2. Công thức cardinality của equijoin

Với phép nối bằng khóa K, số dòng đầu ra có thể mô tả gần đúng bằng:

\[
|A \bowtie B| = \sum_{k} f_A(k) \times f_B(k)
\]

Trong đó f_A(k) và f_B(k) là số dòng mang khóa k ở mỗi phía. Công thức cho thấy một vài khóa có tần suất rất cao có thể chi phối toàn bộ kết quả.

Nếu khóa là duy nhất ở A, mỗi dòng B chỉ khớp tối đa một dòng A. Nếu cả hai phía đều có nhiều dòng cho cùng khóa, join có thể tạo tích số dòng theo từng khóa. Vì vậy, cần biết tính duy nhất và multiplicity của khóa, không chỉ tổng số dòng hai bảng.

### 3.3. Ví dụ về nhân bản dữ liệu

| Bảng | Dòng cho order_id = 900 |
|---|---:|
| Orders | 1 |
| OrderItems | 8 |
| Payments | 3 |
| Kết quả Orders JOIN OrderItems JOIN Payments | 24 |

Nếu mỗi dòng hàng có giá trị 100.000 và mỗi lần thanh toán có số tiền khác nhau, phép nối thô sẽ lặp từng dòng hàng ba lần và lặp từng khoản thanh toán tám lần. SUM sau join có thể sai dù SQL hợp lệ và execution plan chạy đúng.

### 3.4. Kiểm tra multiplicity trước khi tối ưu

Trước khi thay đổi SQL, hãy xác định:

- Khóa nối có unique ở một phía hay cả hai phía?
- Một thực thể có thể có bao nhiêu dòng chi tiết?
- Có bảng bridge cho quan hệ nhiều-nhiều không?
- NULL có xuất hiện ở khóa nối không?
- Có điều kiện lọc làm thay đổi multiplicity không?
- Kết quả mong muốn là một dòng cho mỗi order, mỗi customer, mỗi item hay mỗi payment?

Có thể dùng truy vấn kiểm tra:

~~~sql
SELECT order_id, COUNT(*) AS row_count
FROM order_items
GROUP BY order_id
HAVING COUNT(*) > 1
ORDER BY row_count DESC;
~~~

Thực hiện tương tự với Payments và các bảng chi tiết khác. Những khóa có nhiều dòng nhất thường là điểm cần kiểm tra về skew và row explosion.

## 4. Xác định grain của báo cáo trước khi viết SQL

**Grain** là cấp độ mà một dòng trong kết quả đại diện. Ví dụ:

- Một dòng cho mỗi order.
- Một dòng cho mỗi customer trong một tháng.
- Một dòng cho mỗi product trong một warehouse.
- Một dòng cho mỗi invoice line.

Mọi phép join và aggregate phải bảo toàn grain dự kiến. Nếu kết quả cần một dòng mỗi customer nhưng truy vấn nối thêm nhiều bảng chi tiết, phải biết mỗi phép nối có thể nhân số dòng bao nhiêu lần.

Hãy viết ra grain của từng nguồn:

| Nguồn | Grain ví dụ | Khóa tự nhiên/logic |
|---|---|---|
| Orders | Một dòng mỗi đơn hàng | order_id |
| OrderItems | Một dòng mỗi dòng hàng | order_item_id; order_id không duy nhất |
| Payments | Một dòng mỗi giao dịch thanh toán | payment_id; order_id không duy nhất |
| Customers | Một dòng mỗi khách hàng | customer_id |
| Item totals | Một dòng mỗi đơn hàng | order_id |
| Payment totals | Một dòng mỗi đơn hàng | order_id |

Khi OrderItems và Payments được tổng hợp riêng thành một dòng mỗi order_id, hai tập kết quả có thể nối với Orders mà không nhân chéo dữ liệu chi tiết. Grain rõ ràng cũng giúp phát hiện lỗi double counting.

## 5. Đọc join order và tìm điểm bùng nổ dữ liệu

Optimizer thường có quyền sắp xếp lại thứ tự join để giảm chi phí. SQL viết bảng A trước bảng B không đảm bảo engine thực thi theo đúng thứ tự văn bản. Khi đọc plan, theo dõi:

1. Số dòng đầu vào của từng nhánh.
2. Số dòng sau mỗi join.
3. Số dòng ước lượng và số dòng thực tế.
4. Điều kiện join nào có selectivity thấp.
5. Bộ lọc nào chỉ được áp dụng sau join.
6. Có nhánh nào tạo ra nhiều dòng trùng trước khi aggregate không.

Nếu đầu vào mỗi phía đều lớn và nhiều khóa lặp, hash join hoặc merge join có thể tạo đầu ra lớn dù mỗi bảng chỉ được đọc một lần. Nếu một nhánh rất chọn lọc nhưng filter bị áp dụng muộn, engine có thể làm việc nhiều hơn cần thiết.

Không ép join order ngay khi thấy thứ tự chưa tối ưu. Trước tiên kiểm tra statistics, predicate, index, cardinality và plan stability. Hint hoặc force order có thể giúp một workload cụ thể nhưng cũng có thể làm truy vấn khác hoặc dữ liệu tăng trưởng chạy tệ hơn.

## 6. Các thuật toán join và khi nào phù hợp

### 6.1. Nested loop join

Nested loop lấy từng dòng từ outer input rồi tìm dòng khớp ở inner input. Nó phù hợp khi outer input nhỏ và inner side có index/access path hiệu quả.

Ví dụ, tìm chi tiết của 20 order_id đã được lọc từ một tập Orders lớn có thể dùng nested loop với index trên OrderItems(order_id). Nhưng nếu outer input có 5 triệu dòng và inner lookup phải thực hiện hàng triệu lần, chi phí random access có thể rất lớn.

Khi thấy nested loop chậm, kiểm tra:

- Outer actual rows có lớn hơn estimate không?
- Inner operator thực hiện bao nhiêu lần (loops)?
- Mỗi lần lookup đọc bao nhiêu page?
- Index có hỗ trợ đúng khóa và filter không?
- Có thể giảm outer input trước join không?

### 6.2. Hash join

Hash join thường xây dựng hash table từ một input rồi dò input còn lại theo join key. Nó hữu ích cho equijoin với hai tập lớn khi không có thứ tự sẵn và index lookup không phù hợp.

Chi phí phụ thuộc kích thước build side, row width, hash key, memory grant và độ phân bố khóa. Nếu estimate sai hoặc build side quá lớn, hash join có thể chia nhiều batch và spill xuống vùng tạm.

Kiểm tra build/probe side, số dòng thực tế, hash batches, memory grant, temp I/O và skew. Giảm cột không cần thiết, lọc sớm và pre-aggregate có thể làm hash table nhỏ hơn.

### 6.3. Merge join

Merge join đọc hai input đã được sắp xếp theo join key và tiến đồng thời qua chúng. Nó phù hợp khi dữ liệu đã có thứ tự từ index hoặc sort cần thiết đã được thực hiện.

Nếu phải sort hai tập lớn trước merge join, chi phí sort có thể cao. Xem plan có sort operator hay không, sort có spill không và index có thể cung cấp thứ tự phù hợp không.

### 6.4. Không có thuật toán tốt nhất cho mọi truy vấn

Nested loop, hash join và merge join đều có vùng sử dụng tốt. Hãy đánh giá kích thước đầu vào, độ chọn lọc, thứ tự dữ liệu, index, memory và số lần lặp. Một thay đổi làm optimizer chuyển từ hash join sang nested loop có thể tốt khi tập ngoài nhỏ, nhưng rất xấu khi cardinality tăng đột biến.

## 7. Đẩy predicate xuống sớm (predicate pushdown)

Predicate pushdown là áp dụng điều kiện lọc càng gần nguồn dữ liệu càng tốt để giảm số dòng phải tham gia join hoặc aggregate. Optimizer có thể tự đẩy predicate nếu phép biến đổi bảo toàn ngữ nghĩa và truy vấn viết đủ rõ.

Ví dụ, báo cáo chỉ cần Orders trong một khoảng thời gian và trạng thái nhất định:

~~~sql
SELECT ...
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
  AND o.status = 'COMPLETED';
~~~

Index phù hợp trên Orders có thể giúp database chỉ đọc các order cần thiết trước khi tìm OrderItems. Nếu điều kiện lọc nằm trên OrderItems, hãy đánh giá access path tương ứng.

### 7.1. Sargability

Predicate có thể dùng index hiệu quả khi biểu thức giữ được khả năng tìm kiếm theo thứ tự hoặc cấu trúc index. Ví dụ, điều kiện:

~~~sql
WHERE created_at >= :day_start
  AND created_at < :next_day
~~~

thường dễ dùng index hơn:

~~~sql
WHERE DATE(created_at) = :day
~~~

Vì biểu thức áp dụng hàm lên cột có thể ngăn index seek thông thường, trừ khi có expression/function-based index phù hợp.

Tránh chuyển kiểu dữ liệu ngầm giữa hai cột join. Kiểu dữ liệu khác nhau có thể làm phát sinh conversion, giảm khả năng dùng index và làm cardinality estimate kém chính xác.

### 7.2. Filter trên outer join

Đẩy predicate qua LEFT JOIN phải bảo toàn ngữ nghĩa. Ví dụ:

~~~sql
SELECT ...
FROM orders AS o
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED';
~~~

Giữ điều kiện payment_status trong ON cho phép order không có payment settled vẫn xuất hiện với cột payment là NULL. Nếu chuyển điều kiện đó xuống WHERE, các dòng NULL bị loại và kết quả có thể tương đương INNER JOIN đối với điều kiện đó.

Không di chuyển predicate chỉ vì muốn “lọc sớm”. Kiểm tra outer join, NULL semantics và tập kết quả cần giữ.

## 8. Pre-aggregation: tổng hợp trước khi nối

### 8.1. Ý tưởng

Nếu báo cáo cần tổng số tiền theo order nhưng nguồn chi tiết có nhiều dòng cho cùng order, có thể tổng hợp từng nguồn về đúng grain trước khi join.

Thay vì nối OrderItems với Payments ở grain chi tiết, tạo:

- ItemTotals: một dòng mỗi order_id, chứa tổng tiền hàng.
- PaymentTotals: một dòng mỗi order_id, chứa tổng tiền đã thanh toán.

Sau đó nối hai tập tổng hợp với Orders. Cardinality giảm từ tích số dòng chi tiết xuống tối đa một dòng mỗi order ở mỗi nhánh.

### 8.2. Khi nào có thể tổng hợp trước?

Pre-aggregation phù hợp khi:

- Kết quả cần tổng hợp ở grain cao hơn dữ liệu chi tiết.
- Điều kiện join và group key cho phép giữ nguyên quan hệ cần thiết.
- Không cần dùng từng dòng chi tiết từ nhiều bảng cùng lúc.
- Các phép tổng hợp có thể kết hợp đúng thứ tự và đúng ngữ nghĩa.

Phải cẩn thận khi:

- Có filter phụ thuộc cột ở bảng khác.
- Cần chọn một dòng cụ thể theo thời gian hoặc trạng thái.
- Dùng COUNT(DISTINCT), median, percentile hoặc phép tổng hợp không thể phân rã đơn giản.
- Join nhiều-nhiều có trọng số hoặc phân bổ giá trị.
- Cần giữ các dòng không có bản ghi ở bảng phụ.

### 8.3. Tổng hợp có thể kết hợp

SUM, COUNT, MIN và MAX thường có thể tính theo nhóm nhỏ rồi tổng hợp tiếp nếu giữ đúng key và filter. AVG cần giữ cả SUM và COUNT để tính lại chính xác:

\[
AVG(x) = \frac{SUM(x)}{COUNT(x)}
\]

Không được lấy trung bình của các trung bình con nếu số dòng mỗi nhóm khác nhau, trừ khi có trọng số đúng. COUNT(DISTINCT) thường không thể cộng số distinct của các partition/group nếu cùng một giá trị xuất hiện ở nhiều nhóm.

## 9. Tránh double counting khi nối nhiều bảng chi tiết

### 9.1. Truy vấn dễ sai

Giả sử một order có nhiều dòng hàng và nhiều payment. Truy vấn sau nối hai bảng chi tiết trực tiếp:

~~~sql
SELECT
    o.customer_id,
    SUM(oi.quantity * oi.unit_price) AS item_revenue,
    SUM(p.amount) AS paid_amount
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED'
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
GROUP BY o.customer_id;
~~~

Nếu order có 8 item và 3 payment settled, mỗi item xuất hiện 3 lần và mỗi payment xuất hiện 8 lần. Hai tổng đều có thể sai. Thêm DISTINCT vào SUM không phải cách sửa chung vì hai dòng hợp lệ có thể có cùng amount hoặc cùng giá trị dòng hàng.

### 9.2. Truy vấn đã tổng hợp theo order

~~~sql
WITH item_totals AS
(
    SELECT
        oi.order_id,
        SUM(oi.quantity * oi.unit_price) AS item_revenue,
        COUNT(*) AS item_line_count
    FROM order_items AS oi
    GROUP BY oi.order_id
),
payment_totals AS
(
    SELECT
        p.order_id,
        SUM(p.amount) AS paid_amount,
        COUNT(*) AS settled_payment_count
    FROM payments AS p
    WHERE p.payment_status = 'SETTLED'
    GROUP BY p.order_id
)
SELECT
    o.customer_id,
    COUNT(*) AS order_count,
    SUM(COALESCE(it.item_revenue, 0)) AS item_revenue,
    SUM(COALESCE(pt.paid_amount, 0)) AS paid_amount
FROM orders AS o
LEFT JOIN item_totals AS it
  ON it.order_id = o.order_id
LEFT JOIN payment_totals AS pt
  ON pt.order_id = o.order_id
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
  AND o.status = 'COMPLETED'
GROUP BY o.customer_id;
~~~

Mỗi CTE tạo tối đa một dòng cho mỗi order_id. Nếu orders cũng có đúng một dòng mỗi order_id, các phép LEFT JOIN không nhân dòng order. COUNT(*) vì vậy đếm số order trong phạm vi lọc.

Đây là một mẫu minh họa; query tối ưu thực tế có thể lọc Orders trước rồi mới aggregate chi tiết theo danh sách order phù hợp, tùy optimizer và engine. Nếu CTE bị materialize hoặc scan toàn bộ bảng chi tiết, cần xem plan và cân nhắc cách viết khác.

### 9.3. Phải định nghĩa đúng ý nghĩa của tiền

Item revenue và paid amount không nhất thiết cùng một khoảng thời gian hoặc cùng một trạng thái:

- Doanh thu có thể dựa trên ngày tạo order, ngày giao hàng hoặc ngày ghi nhận kế toán.
- Paid amount có thể dựa trên paid_at, payment status hoặc settlement date.
- Refund có thể là bảng riêng hoặc payment có amount âm.
- Một order có thể có partial payment, retry, reversal hoặc chargeback.

Nếu báo cáo yêu cầu khoản thanh toán trong một khoảng thời gian, filter paid_at phải được áp dụng ở payment_totals. Nếu báo cáo yêu cầu tổng thanh toán gắn với các order được tạo trong kỳ, có thể lọc Orders theo created_at rồi tổng hợp Payments của các order đó. Hai định nghĩa cho kết quả khác nhau.

## 10. Semi join và anti join khi không cần cột từ bảng phụ

Nếu chỉ cần kiểm tra có tồn tại bản ghi phù hợp, dùng EXISTS thường biểu đạt đúng mục tiêu hơn join chi tiết rồi DISTINCT:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS
(
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'COMPLETED'
);
~~~

Đây là semi join về mặt logic: mỗi customer xuất hiện tối đa một lần nếu có ít nhất một order phù hợp, bất kể có bao nhiêu order.

Để tìm khách hàng chưa có order, có thể dùng NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS
(
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

NOT EXISTS thường tránh một số vấn đề NULL của NOT IN khi subquery trả về NULL. Optimizer có thể chuyển EXISTS thành semi join hoặc anti join. Hãy kiểm tra plan, index và semantics NULL.

## 11. Tối ưu GROUP BY và các phép tổng hợp

### 11.1. Giảm đầu vào trước aggregate

Aggregate càng ít dòng càng ít CPU, memory và sort/hash work. Hãy áp dụng filter trước khi group nếu điều đó không đổi ngữ nghĩa. Chỉ chọn các cột cần thiết để giảm row width.

### 11.2. Hash aggregate và sort aggregate

Hash aggregate nhóm dòng bằng hash table; nó phù hợp khi cần gom nhóm và đủ bộ nhớ. Sort aggregate cần input theo thứ tự group key hoặc phải sort trước. Nếu group cardinality lớn, hash table có thể spill hoặc sort có thể ghi ra vùng tạm.

Xem:

- Số nhóm thực tế và ước lượng.
- Số dòng vào aggregate.
- Row width và số cột group key.
- Hash batches, memory grant, sort spill hoặc temp read/write.
- Có index nào cung cấp thứ tự group hữu ích không.

### 11.3. DISTINCT và COUNT DISTINCT

DISTINCT có thể cần sort hoặc hash để loại trùng. Nếu nó được dùng chỉ để sửa lỗi nhân bản do join, hãy sửa grain và join trước. COUNT(DISTINCT) có thể tốn nhiều memory và CPU; kiểm tra liệu nghiệp vụ thực sự cần distinct ở grain đó không.

### 11.4. Window function

Window function có thể tránh self-join hoặc nhiều aggregate phụ, nhưng cũng có thể cần sort theo PARTITION BY/ORDER BY. Chỉ giữ partition và cột cần thiết; kiểm tra sort spill và cardinality. Window function không tự giảm số dòng như GROUP BY.

## 12. Index cho join và aggregate

Index có thể giảm số dòng phải đọc, hỗ trợ join key, filter hoặc thứ tự dữ liệu. Thiết kế dựa trên access path thực tế:

- Index trên foreign key hoặc join key ở bảng chi tiết giúp tìm dòng liên quan.
- Composite index nên bắt đầu từ các cột filter/join phù hợp với selectivity và cách truy vấn sử dụng.
- Covering index có thể giảm lookup nếu bao gồm đủ cột cần thiết, nhưng làm index rộng hơn.
- Index theo group key có thể hỗ trợ thứ tự hoặc range access trong một số plan.
- Partition-local index và global index có trade-off riêng theo engine.

Ví dụ ứng viên cần đánh giá:

~~~sql
CREATE INDEX ix_orders_status_created
    ON orders (status, created_at, order_id);

CREATE INDEX ix_items_order
    ON order_items (order_id);

CREATE INDEX ix_payments_order_status
    ON payments (order_id, payment_status);
~~~

Không áp dụng máy móc thứ tự cột trong ví dụ. Nếu query lọc theo tenant_id trước, tenant_id có thể cần nằm trong index. Nếu payment_status rất chọn lọc và filter thường được áp trước khi join theo order_id, thứ tự khác có thể tốt hơn. Đo bằng execution plan, logical reads, physical reads, write cost và kích thước index.

Index không làm biến mất row explosion do join sai grain. Nó có thể làm phép nối sai chạy nhanh hơn một chút nhưng kết quả vẫn sai và lượng dữ liệu trung gian vẫn lớn.

## 13. Statistics, skew và ước lượng cardinality

Optimizer dựa vào statistics để ước lượng số dòng qua filter, join và aggregate. Estimate sai có thể làm chọn join order hoặc algorithm không phù hợp, cấp memory quá ít hoặc quá nhiều.

Các nguyên nhân phổ biến:

- Statistics đã cũ sau bulk load hoặc phân bố dữ liệu thay đổi.
- Histogram không mô tả đủ các giá trị hiếm hoặc phổ biến.
- Hai cột có tương quan nhưng optimizer giả định độc lập.
- Một vài khóa có tần suất lớn (data skew).
- Parameter sniffing hoặc bind peeking khiến plan được tối ưu theo giá trị tham số không đại diện.
- Statistics trên partition không phản ánh phân bố toàn cục hoặc partition mới.

### 13.1. Tìm điểm estimate bắt đầu sai

Trong actual plan, so sánh estimated rows và actual rows tại từng operator. Tìm operator đầu tiên có sai lệch lớn; các sai lệch ở phía sau có thể là hệ quả của nó.

Ví dụ, optimizer ước lượng filter trả 100 dòng nhưng thực tế 500.000 dòng. Nested loop với 100 lần lookup có thể được chọn, nhưng thực tế cần 500.000 lần lookup. Tối ưu index mà không sửa estimate có thể không giải quyết được lựa chọn plan.

### 13.2. Xử lý skew

Với dữ liệu lệch, cần kiểm tra histogram, most common values, multi-column statistics hoặc extended statistics tùy engine. Có thể dùng query specialization cho các giá trị cực phổ biến nếu plan chung không phù hợp, nhưng phải kiểm soát plan cache và tính đúng.

Không cập nhật statistics toàn bộ database theo phản xạ. Cập nhật đúng object/cột liên quan, kiểm tra sampling và cân nhắc chi phí analyze trên bảng lớn.

## 14. Memory grant và spill ra vùng tạm

Join và aggregate trên tập dữ liệu lớn cần bộ nhớ:

- Hash join cần hash table cho build side.
- Hash aggregate cần bảng nhóm.
- Sort cần vùng nhớ để sắp xếp.
- Một số operator khác cần memory grant hoặc workspace.

Nếu bộ nhớ cấp không đủ, engine có thể spill dữ liệu ra tempdb, temporary tablespace hoặc file tạm. Spill làm tăng I/O, latency và cạnh tranh với workload khác.

### 14.1. Dấu hiệu

- PostgreSQL: hash batches lớn hơn một, temp blocks read/written hoặc log báo sort/hash disk.
- SQL Server: spill warning trong execution plan, memory grant thiếu, tempdb I/O tăng.
- MySQL: temporary table trên disk, sort merge passes hoặc temp table usage tăng.
- Oracle: workarea thực thi ở TEMP thay vì optimal memory; theo dõi workarea và temp usage.

Tên metric và cách hiển thị khác nhau theo phiên bản. Cần dùng actual plan và công cụ giám sát đúng engine.

### 14.2. Cách giảm spill

1. Giảm cardinality trước hash/sort bằng predicate pushdown.
2. Thu hẹp row width, bỏ cột không cần.
3. Pre-aggregate khi đúng ngữ nghĩa.
4. Cải thiện statistics để memory estimate sát hơn.
5. Giảm số nhóm hoặc độ lớn build side.
6. Điều chỉnh memory grant/work_mem theo giới hạn concurrency, không tăng vô hạn.
7. Tách báo cáo nặng sang workload pool hoặc replica phù hợp nếu kiến trúc cho phép.

Tăng memory cho một query có thể làm nhiều query đồng thời thiếu memory. Đánh giá tổng concurrency và p95/p99 của toàn hệ thống.

## 15. Partitioning và partition pruning

Partitioning chia một bảng lớn thành các phần theo range, list hoặc hash. Khi truy vấn lọc theo partition key, partition pruning có thể loại bỏ partition không cần đọc, giảm scan và dữ liệu trung gian.

Ví dụ bảng Orders partition theo created_at có thể chỉ đọc partition của một khoảng thời gian. Tuy nhiên:

- Predicate phải cho phép engine suy ra partition cần thiết.
- Join giữa các bảng partition cần partition key và distribution phù hợp.
- Partitioning không tự giảm row explosion nếu join multiplicity vẫn lớn.
- Quá nhiều partition có thể tăng metadata và planning overhead.
- Statistics từng partition và toàn bảng phải được quản lý.

Nếu hai bảng partition theo khóa/thời gian tương thích, engine có thể tận dụng partition-wise join trong một số hệ quản trị. Kiểm tra plan thay vì giả định partitioning luôn làm join nhanh hơn.

## 16. CTE, derived table và materialization

CTE hoặc derived table giúp thể hiện logic lọc và tổng hợp theo từng bước. Tuy nhiên, chúng không phải lúc nào cũng là temporary table vật lý. Optimizer có thể inline, merge hoặc materialize tùy engine và phiên bản.

Sử dụng CTE để làm rõ grain:

~~~sql
WITH monthly_orders AS
(
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    WHERE created_at >= :month_start
      AND created_at < :next_month
    GROUP BY customer_id
)
SELECT c.customer_id, c.customer_name, m.order_count
FROM customers AS c
JOIN monthly_orders AS m
  ON m.customer_id = c.customer_id;
~~~

Nếu kết quả trung gian được dùng nhiều lần, materialize có thể tránh tính lại; nhưng nó cũng cần ghi/đọc temp và có thể làm mất cơ hội predicate pushdown. Nếu cần thống kê riêng cho tập trung gian lớn, temporary table có index/statistics có thể phù hợp hơn. Quyết định dựa trên plan và workload.

Không dùng CTE chỉ để hy vọng database thực thi tuần tự theo thứ tự viết. SQL là khai báo; optimizer có quyền biến đổi khi ngữ nghĩa cho phép.

## 17. Bài thực hành xuyên suốt: báo cáo doanh thu và thanh toán theo khách hàng

### 17.1. Mô hình dữ liệu

Giả sử có các bảng:

| Bảng | Grain | Quan hệ |
|---|---|---|
| customers | Một dòng mỗi customer | customer_id là khóa |
| orders | Một dòng mỗi order | customer_id tham chiếu customers |
| order_items | Một dòng mỗi item trong order | order_id lặp |
| payments | Một dòng mỗi lần thanh toán | order_id lặp |

Yêu cầu: với các order hoàn tất được tạo trong một khoảng thời gian, tính số order, doanh thu theo dòng hàng và số tiền thanh toán đã settled theo customer.

### 17.2. Xác định định nghĩa nghiệp vụ

Trước khi viết SQL, thống nhất:

- Chỉ lấy order có status COMPLETED.
- Khoảng thời gian áp dụng cho orders.created_at.
- Item revenue là SUM(quantity × unit_price) của tất cả item thuộc order được chọn.
- Paid amount là tổng các payment SETTLED của các order đó, bất kể paid_at nằm ở ngày nào.
- Order không có item hoặc payment vẫn được giữ và giá trị tổng tương ứng bằng 0.
- Mỗi order chỉ được đếm một lần.

Nếu yêu cầu paid amount theo ngày thanh toán, cần thêm điều kiện paid_at trong nhánh payment_totals. Đó là một báo cáo khác về mặt ngữ nghĩa.

### 17.3. Phiên bản dễ sai và tốn tài nguyên

~~~sql
SELECT
    o.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price) AS item_revenue,
    SUM(p.amount) AS paid_amount
FROM orders AS o
JOIN order_items AS oi
  ON oi.order_id = o.order_id
LEFT JOIN payments AS p
  ON p.order_id = o.order_id
 AND p.payment_status = 'SETTLED'
WHERE o.created_at >= :from_time
  AND o.created_at < :to_time
  AND o.status = 'COMPLETED'
GROUP BY o.customer_id;
~~~

COUNT(DISTINCT) có thể làm order_count đúng, nhưng hai SUM vẫn bị nhân bản khi một order có nhiều item và nhiều payment. DISTINCT không thể sửa tổng tiền một cách tổng quát. Database cũng phải tạo tập join chi tiết lớn rồi mới aggregate.

### 17.4. Tổng hợp riêng từng nhánh

~~~sql
WITH selected_orders AS
(
    SELECT order_id, customer_id
    FROM orders
    WHERE created_at >= :from_time
      AND created_at < :to_time
      AND status = 'COMPLETED'
),
item_totals AS
(
    SELECT
        oi.order_id,
        SUM(oi.quantity * oi.unit_price) AS item_revenue
    FROM order_items AS oi
    JOIN selected_orders AS so
      ON so.order_id = oi.order_id
    GROUP BY oi.order_id
),
payment_totals AS
(
    SELECT
        p.order_id,
        SUM(p.amount) AS paid_amount
    FROM payments AS p
    JOIN selected_orders AS so
      ON so.order_id = p.order_id
    WHERE p.payment_status = 'SETTLED'
    GROUP BY p.order_id
)
SELECT
    so.customer_id,
    COUNT(*) AS order_count,
    SUM(COALESCE(it.item_revenue, 0)) AS item_revenue,
    SUM(COALESCE(pt.paid_amount, 0)) AS paid_amount
FROM selected_orders AS so
LEFT JOIN item_totals AS it
  ON it.order_id = so.order_id
LEFT JOIN payment_totals AS pt
  ON pt.order_id = so.order_id
GROUP BY so.customer_id;
~~~

Hai nhánh chi tiết được giới hạn theo selected_orders và tổng hợp về một dòng mỗi order trước khi nối với nhau. Do selected_orders có một dòng mỗi order, kết quả cuối không bị nhân theo số item hoặc payment.

Optimizer có thể inline CTE và chọn cách thực thi khác với hình thức văn bản. Điều cần xác nhận là actual plan giảm số dòng ở các join và aggregate, không nhất thiết phải có một operator materialize riêng.

### 17.5. Kiểm tra tính đúng bằng đối soát

Chọn một vài order đại diện:

- Order có một item và một payment.
- Order có nhiều item nhưng một payment.
- Order có một item nhưng nhiều payment.
- Order có nhiều item và nhiều payment.
- Order không có payment settled.
- Order không có item do dữ liệu bất thường hoặc quy tắc cho phép.

Tính tổng item và payment riêng từng order bằng truy vấn độc lập, sau đó đối chiếu với báo cáo. Kiểm tra tổng toàn cục và tổng theo customer có khớp với nguồn authoritative không.

### 17.6. Tối ưu thêm theo quy mô

Nếu selected_orders rất nhỏ, nested loop với index trên order_items(order_id) và payments(order_id, payment_status) có thể hiệu quả. Nếu phạm vi chọn hàng lớn, hash join với pre-aggregation có thể tốt hơn. Nếu bảng Orders partition theo created_at, filter thời gian có thể prune partition.

Nếu báo cáo chạy thường xuyên và khoảng thời gian cố định, cân nhắc summary table hoặc materialized view được cập nhật có kiểm soát. Phải xác định freshness, refresh cost, xử lý late-arriving data và cách đối soát với bảng gốc.

## 18. Đọc actual execution plan theo trình tự

### 18.1. Bắt đầu ở operator có sai lệch đầu tiên

Đọc từ các leaf/source operator lên:

1. So sánh estimated rows với actual rows tại từng nguồn.
2. Xem filter có giảm được số dòng như kỳ vọng không.
3. Xem join đầu tiên có tạo số dòng lớn bất thường không.
4. Xem số lần lặp của inner side trong nested loop.
5. Xem hash build side, hash batches và spill.
6. Xem sort/aggregate có spill hoặc xử lý nhiều dòng hơn cần thiết không.
7. Xem số dòng và row width cuối cùng.

Sai lệch đầu tiên thường là nơi cần tìm nguyên nhân: statistics, skew, predicate hoặc tương quan cột. Các operator sau có thể chỉ đang khuếch đại sai lệch đó.

### 18.2. PostgreSQL

Dùng EXPLAIN để xem plan ước lượng và EXPLAIN ANALYZE để thực thi truy vấn, đo actual rows, loops và thời gian. Ví dụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT ...;
~~~

EXPLAIN ANALYZE thực sự chạy statement. Chỉ dùng trên truy vấn đọc an toàn hoặc môi trường kiểm thử; với DML cần hiểu rõ tác động và transaction rollback không đảo ngược mọi side effect ngoài database. Xem shared/local/temp blocks, rows, loops, hash batches và sort method.

### 18.3. SQL Server

Dùng Actual Execution Plan cùng SET STATISTICS IO ON và SET STATISTICS TIME ON để xem actual rows, logical reads, CPU và elapsed time. Kiểm tra memory grant, spill warnings, hash/sort operator, parallelism và parameter sensitivity. Query Store giúp so sánh plan và runtime statistics qua thời gian.

### 18.4. MySQL

EXPLAIN ANALYZE trong phiên bản hỗ trợ cung cấp actual timing/rows cho iterator tree và thực thi truy vấn. Kết hợp EXPLAIN FORMAT=JSON, Performance Schema và session status để xem rows examined, temporary tables, sort merge passes và handler activity. Xác minh version trước khi dùng cú pháp.

### 18.5. Oracle

Dùng DBMS_XPLAN.DISPLAY_CURSOR với thống kê runtime phù hợp, chẳng hạn ALLSTATS LAST khi đã thu thập row source statistics. Xem E-Rows so với A-Rows, Starts, Buffers, TempSpc, join method và workarea. Kiểm tra SQL Monitor cho statement dài nếu tính năng và quyền được hỗ trợ.

## 19. Benchmark trước và sau tối ưu

Không so sánh hai lần chạy trong điều kiện khác nhau rồi kết luận query mới tốt hơn. Dùng cùng:

- Dataset và phân bố dữ liệu.
- Khoảng thời gian, tenant hoặc filter parameter.
- Cache state hoặc ghi rõ cold-cache/warm-cache.
- Số client đồng thời và request mix.
- Phiên bản database, cấu hình và statistics.
- Mức tải nền và trạng thái replica/storage.

Ghi nhận:

| Chỉ số | Mục đích |
|---|---|
| Elapsed time p50/p95/p99 | Thời gian phản hồi |
| CPU time | Chi phí xử lý |
| Logical reads | Lượng page truy cập qua buffer/cache |
| Physical reads | Lượng đọc từ storage |
| Rows examined/actual rows | Khối lượng dữ liệu được xử lý |
| Intermediate rows | Kích thước dữ liệu qua join/aggregate |
| Temp read/write và spill | Áp lực vùng tạm |
| Memory grant/work_mem use | Bộ nhớ cho hash/sort |
| Throughput | Số báo cáo hoặc request hoàn thành |
| Concurrency impact | Ảnh hưởng tới workload khác |

Chạy nhiều lần và so sánh phân vị, không chỉ một lần tốt nhất. Một query giảm thời gian đơn lẻ nhưng làm tăng memory pressure và khiến các query khác chậm hơn có thể không phải cải thiện tổng thể.

## 20. Kiểm chứng tính đúng của kết quả

Tối ưu join và aggregate luôn có rủi ro đổi semantics. Trước khi phát hành:

1. Xác nhận grain của kết quả và từng nguồn.
2. So sánh row count theo khóa nhóm.
3. Đối chiếu SUM/COUNT/MIN/MAX với truy vấn tham chiếu trên tập dữ liệu nhỏ.
4. Kiểm tra order không có dòng chi tiết và order có nhiều dòng chi tiết.
5. Kiểm tra NULL, duplicate key, dữ liệu thiếu và giá trị âm.
6. Kiểm tra outer join và predicate ON/WHERE.
7. Kiểm tra DISTINCT, COUNT DISTINCT và phép chia AVG.
8. Kiểm tra timezone, boundary của khoảng thời gian và late-arriving data.
9. Kiểm tra concurrent insert/update nếu báo cáo chạy trên dữ liệu đang thay đổi.
10. Xác định isolation/snapshot để hai lần đối soát nhìn cùng một tập dữ liệu.

Có thể dùng EXCEPT/MINUS hoặc full outer join trên hai kết quả để tìm nhóm có giá trị khác. Với dữ liệu lớn, so sánh theo partition hoặc key range để tránh tạo thêm một phép đối soát quá nặng.

## 21. Các dấu hiệu và hướng điều tra nhanh

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Join output lớn hơn nhiều so với input | Nhiều-nhiều, khóa trùng hoặc thiếu điều kiện join | Kiểm tra grain, multiplicity và join predicate |
| Aggregate nhận hàng triệu dòng nhưng trả vài trăm nhóm | Filter muộn hoặc aggregate sau join chi tiết | Predicate pushdown, pre-aggregation, semi join |
| Nested loop có loops rất lớn | Outer cardinality lớn hoặc estimate sai | Actual rows, inner index lookup và statistics |
| Hash join có nhiều batch | Build side lớn hoặc thiếu memory | Row width, filter, pre-aggregate, memory grant |
| Sort/aggregate spill | Sort/hash lớn, estimate sai hoặc concurrency cao | Temp I/O, group count, statistics, memory |
| Estimate sai từ đầu plan | Statistics, skew, correlation hoặc parameter sensitivity | Histogram, extended stats, plan theo tham số |
| CPU cao nhưng I/O thấp | Hash/sort/aggregate hoặc join work lớn | Operator cost, rows, loops và parallelism |
| Kết quả SUM bị nhân lên | Join fanout giữa nhiều bảng chi tiết | Đối chiếu grain, tổng hợp từng nhánh |
| Query nhanh trên dữ liệu nhỏ, chậm trên production | Skew, cardinality, cache hoặc memory spill | Dữ liệu đại diện và actual plan |

## 22. Các lỗi tối ưu thường gặp

- **Chỉ nhìn số dòng cuối:** bỏ qua intermediate cardinality và row width.
- **Nối nhiều bảng detail rồi mới GROUP BY:** tạo fanout và double counting.
- **Dùng DISTINCT để che lỗi join:** tốn sort/hash và có thể xóa các dòng hợp lệ.
- **Ép join order quá sớm:** làm optimizer mất khả năng chọn plan theo dữ liệu thực.
- **Thêm index theo mọi cột join:** tăng chi phí ghi, storage và maintenance.
- **Chỉ tối ưu nested loop bằng cách thêm index:** outer input có thể vẫn quá lớn.
- **Tăng memory vô hạn để hết spill:** gây memory pressure khi nhiều query chạy đồng thời.
- **Dùng CTE với giả định luôn materialize:** behavior phụ thuộc optimizer và phiên bản.
- **Đẩy predicate qua LEFT JOIN mà không kiểm tra NULL:** vô tình biến outer join thành inner join.
- **Cộng các AVG con:** cho kết quả sai nếu số lượng phần tử mỗi nhóm khác nhau.
- **Cộng COUNT DISTINCT từng nhóm:** sai nếu cùng giá trị xuất hiện ở nhiều nhóm.
- **Không tính late-arriving data hoặc refund:** tối ưu kỹ thuật nhưng sai định nghĩa báo cáo.
- **So sánh benchmark khác cache hoặc tải nền:** kết luận không đáng tin.
- **Chỉ kiểm tra tốc độ:** không đối soát tính đúng của tổng và số dòng.

## 23. Quy trình capstone từ yêu cầu tới xác nhận

1. **Viết hợp đồng dữ liệu:** grain, filter, thời gian, NULL, duplicate và định nghĩa từng chỉ số.
2. **Lập sơ đồ quan hệ:** cardinality, unique key, foreign key và quan hệ một-nhiều/nhiều-nhiều.
3. **Chạy baseline:** actual plan, runtime, reads, CPU, memory, temp và kết quả nghiệp vụ.
4. **Tìm row explosion:** xác định join/aggregate có intermediate rows lớn nhất.
5. **Tìm estimate divergence:** operator đầu tiên lệch giữa estimated và actual cardinality.
6. **Chọn phép biến đổi:** filter sớm, pre-aggregate, semi/anti join, sửa join predicate hoặc chia query.
7. **Đánh giá index:** join key, filter key, covering và write cost.
8. **Đánh giá memory/parallelism:** hash/sort spill, grant, temp và concurrency.
9. **Viết phiên bản tối ưu:** giữ rõ grain bằng CTE/derived table hoặc staging phù hợp.
10. **Đối soát kết quả:** so sánh nhóm, tổng, số dòng và edge case với nguồn tham chiếu.
11. **Benchmark cùng điều kiện:** nhiều lần chạy, tải đại diện, p95/p99 và throughput.
12. **Triển khai có kiểm soát:** canary, theo dõi plan regression và rollback SQL nếu cần.
13. **Ghi lại bằng chứng:** query version, plan, parameters, metrics và quy tắc nghiệp vụ.

## 24. Bài tập tự kiểm tra

**Bài 1.** Một order có 6 item và 4 payment. Nối trực tiếp hai bảng chi tiết theo order_id tạo tối đa bao nhiêu dòng cho order đó? Hai SUM sau join có thể sai thế nào?

*Gợi ý:* Có thể tạo 24 dòng. Tổng item bị nhân 4 lần và tổng payment bị nhân 6 lần.

**Bài 2.** Báo cáo chỉ cần customer có ít nhất một order hoàn tất. Dùng JOIN rồi DISTINCT hay EXISTS? Vì sao?

*Gợi ý:* EXISTS biểu đạt semi join, không nhân customer theo số order và không cần DISTINCT để khử trùng.

**Bài 3.** Vì sao COUNT(DISTINCT order_id) có thể đúng trong khi SUM(item_amount) vẫn sai?

*Gợi ý:* DISTINCT chỉ sửa phép đếm order; các giá trị amount vẫn bị lặp theo số payment hoặc item của bảng detail còn lại.

**Bài 4.** Actual plan có nested loop với outer actual rows 800.000 và inner index lookup chạy 800.000 lần. Bạn điều tra gì?

*Gợi ý:* Kiểm tra estimate outer, filter có thể đẩy sớm, index lookup cost, pre-aggregation hoặc hash/merge join phù hợp hơn.

**Bài 5.** Hash join spill ra temp. Hãy nêu bốn hướng giảm áp lực.

*Gợi ý:* Lọc sớm, giảm row width, pre-aggregate, sửa statistics, giảm build side hoặc điều chỉnh memory trong giới hạn concurrency.

**Bài 6.** Khi nào có thể tổng hợp từng nhánh trước khi join?

*Gợi ý:* Khi mỗi nhánh có thể được gom về cùng join grain và filter/quan hệ không đòi hỏi giữ từng dòng chi tiết. Phải bảo toàn NULL, outer join và semantics của phép tổng hợp.

**Bài 7.** Vì sao AVG của các nhóm con không thể luôn lấy trung bình đơn giản để ra AVG toàn cục?

*Gợi ý:* Nhóm có số dòng khác nhau. Phải cộng SUM và COUNT rồi chia tổng SUM cho tổng COUNT.

**Bài 8.** Một CTE tổng hợp có vẻ giảm dữ liệu nhưng actual plan vẫn scan toàn bộ bảng detail. Bạn kiểm tra gì?

*Gợi ý:* CTE có bị inline, predicate pushdown có hoạt động, join với selected key có dùng index, statistics và plan có chọn scan hợp lý theo phạm vi hay không.

## 25. Ghi nhớ khi tối ưu

Hiệu năng join và aggregate phụ thuộc vào grain, multiplicity, cardinality, row width, access path, statistics, memory và concurrency. Một kết quả nhỏ có thể được tạo ra từ tập trung gian rất lớn. Join nhiều bảng detail độc lập có thể nhân dòng và làm tổng bị sai; hãy tổng hợp từng nhánh về đúng grain hoặc dùng EXISTS khi chỉ cần kiểm tra sự tồn tại.

Đọc actual execution plan từ nguồn dữ liệu lên, tìm nơi số dòng tăng đột biến và operator đầu tiên có estimate sai. Chọn nested loop, hash join hoặc merge join theo kích thước và đặc tính đầu vào. Đẩy filter sớm khi semantics cho phép, dùng index có mục tiêu, kiểm soát spill và xem xét partitioning/materialization bằng số liệu.

Mỗi thay đổi phải được đối soát về số dòng và giá trị nghiệp vụ, sau đó benchmark trên dữ liệu và tải đại diện. Mục tiêu cuối cùng là giảm work volume và latency mà vẫn giữ đúng grain, tổng hợp, NULL semantics và quy tắc nghiệp vụ.
