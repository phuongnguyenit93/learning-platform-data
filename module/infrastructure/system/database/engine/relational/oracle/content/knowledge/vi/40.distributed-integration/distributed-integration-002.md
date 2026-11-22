# Đẩy điều kiện lọc, giảm dữ liệu truyền và đọc kế hoạch truy vấn phân tán

Trong hệ thống Oracle phân tán, một câu SQL có thể truy cập bảng ở database hiện tại và bảng ở database khác thông qua database link. Khi thực hiện truy vấn, Oracle chia câu lệnh thành các phần có thể chạy tại từng site. Remote database thực thi phần SQL được gửi tới nó, trả kết quả qua network, rồi local database tiếp tục join, lọc, aggregate hoặc xử lý phần còn lại trước khi trả dữ liệu cho ứng dụng.

Vì vậy, hiệu năng của distributed query không chỉ phụ thuộc vào index hoặc execution plan tại một database. Nó còn phụ thuộc vào **số dòng được gửi qua network, số cột được truyền, số lần gọi remote, vị trí thực hiện join/aggregate, độ trễ mạng, thống kê optimizer và tải của từng database**.

Nguyên tắc tuning quan trọng nhất là để dữ liệu được lọc và xử lý ở nơi đang lưu trữ nó, sau đó chỉ truyền phần kết quả cần thiết về query execution site. Oracle gọi một kỹ thuật quan trọng cho mục tiêu này là **collocated inline views**: gom các bảng cùng nằm trên một remote database vào một inline view để remote site thực hiện join và filter tại chỗ. Khi cần, có thể dùng NO_MERGE để giữ ranh giới inline view và DRIVING_SITE để chỉ định site thực thi truy vấn. Mọi thay đổi phải được xác minh bằng execution plan và số liệu thực tế.

Bài học thuộc nhóm **Tích hợp phân tán** của Database Engine Relational Oracle. Nội dung tập trung vào predicate pushdown, projection pushdown, giảm dữ liệu truyền, collocated inline views, cost-based optimization, hints, database links và cách đọc kế hoạch truy vấn phân tán.

Sau bài này, bạn có thể:

- Giải thích Oracle phân tách distributed query thành local và remote SQL như thế nào.
- Nhận diện chi phí network trong một câu truy vấn dùng database link.
- Đẩy điều kiện WHERE tới remote site khi điều kiện có thể đánh giá ở đó.
- Chỉ lấy các cột cần thiết thay vì SELECT *.
- Thực hiện join và aggregate tại remote site bằng collocated inline views.
- Dùng NO_MERGE để giữ inline view khi đã có lý do tuning rõ ràng.
- Dùng DRIVING_SITE để điều khiển site thực thi khi phù hợp.
- Hiểu vai trò của optimizer statistics ở cả local và remote database.
- Đọc operation REMOTE và SQL gửi tới remote database trong execution plan.
- So sánh estimated rows/bytes với số liệu thực thi và SQL*Net statistics.
- Phân biệt EXPLAIN PLAN với execution plan thực tế.
- Nhận biết các trường hợp predicate không thể hoặc không nên đẩy xuống remote.
- Đánh giá ảnh hưởng của database link, bind variables, NLS và network latency.
- Xây dựng quy trình benchmark trước/sau khi viết lại distributed SQL.

> **Phạm vi ví dụ:** Các ví dụ chủ yếu theo Oracle Database 19c. Giả sử database hiện tại là LOCALDB và remote database được truy cập qua database link SALES_LINK. Tên schema, bảng, cột, service và link chỉ là ví dụ. Hãy thay bằng đối tượng thật trong môi trường lab. Tuning distributed query cần so sánh kết quả dữ liệu, execution plan, số dòng/bytes truyền và thời gian thực thi; không kết luận chỉ từ một hint hoặc cost.

## 1. Distributed query hoạt động như thế nào?

Một distributed query là câu SQL tham chiếu dữ liệu ở nhiều database. Oracle dùng database link để tạo remote session và gửi SQL đến remote database.

### 1.1. Ví dụ đơn giản

~~~sql
SELECT
    employee_id,
    first_name,
    salary
FROM employees@sales_link
WHERE department_id = 50;
~~~

Trong ví dụ này:

- SQL được gửi từ LOCALDB.
- EMPLOYEES nằm ở remote database.
- SALES_LINK cung cấp kết nối tới remote database.
- Remote database có thể lọc DEPARTMENT_ID = 50.
- Chỉ các dòng kết quả được gửi về local site.

Nếu remote database có index phù hợp, remote optimizer có thể dùng index để tìm các dòng cần thiết trước khi truyền kết quả.

### 1.2. Câu truy vấn có nhiều site

~~~sql
SELECT
    l.region_name,
    r.customer_name,
    r.total_amount
FROM local_regions l
JOIN (
    SELECT
        c.region_id,
        c.customer_name,
        SUM(o.amount) AS total_amount
    FROM customers@sales_link c
    JOIN orders@sales_link o
      ON o.customer_id = c.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY c.region_id, c.customer_name
) r
  ON r.region_id = l.region_id
WHERE l.is_active = 'Y';
~~~

Remote database chứa CUSTOMERS và ORDERS. Local database chứa LOCAL_REGIONS. Oracle có thể:

1. Gửi SQL tới SALES_LINK để remote site join CUSTOMERS với ORDERS, lọc theo ngày và aggregate.
2. Nhận kết quả đã thu gọn.
3. Join kết quả đó với LOCAL_REGIONS ở local site.

Đây thường là cách tiếp cận tốt vì hai bảng remote được xử lý tại cùng một database, và dữ liệu truyền về đã được giảm.

### 1.3. Vai trò của local và remote site

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| Local site | Database nơi client phát hành câu SQL |
| Remote site | Database được truy cập qua database link |
| Remote query | Phần SQL được gửi tới remote database |
| Query execution site | Site thực hiện phần xử lý chính của distributed query |
| Database link | Kết nối cho phép truy cập object ở database khác |
| Collocated tables | Các bảng cùng nằm trên một database |

Local site không nhất thiết phải thực hiện mọi join. Optimizer có thể đẩy các phần xử lý tới remote site hoặc chọn remote site làm nơi thực thi truy vấn.

### 1.4. Một remote session có thể được tái sử dụng

Khi user session local lần đầu truy cập một database link, Oracle tạo remote session tương ứng. Remote connection/session có thể tồn tại trong suốt local user session, trừ khi được đóng rõ ràng hoặc local session kết thúc.

Do đó, một distributed query không phải lúc nào cũng tạo một TCP connection mới cho mỗi lần đọc remote table. Tuy vậy, mỗi lần gọi remote và lượng dữ liệu trao đổi vẫn có chi phí.

## 2. Vì sao distributed query dễ chậm?

Một truy vấn local có thể đọc dữ liệu qua memory hoặc storage cục bộ. Distributed query còn phải gửi request và dữ liệu qua network.

### 2.1. Các thành phần chi phí

Tổng thời gian có thể chịu ảnh hưởng bởi:

- Thời gian parse và tối ưu SQL ở local database.
- Thời gian parse và tối ưu remote SQL.
- CPU và I/O tại local database.
- CPU và I/O tại remote database.
- Network round trips.
- Số bytes truyền từ remote về local.
- Số bytes truyền từ local sang remote.
- Độ trễ của database link.
- Thời gian chờ remote database xử lý.
- Phần join, sort, group by hoặc filter còn lại tại local site.

Một query có thể rất nhanh trên remote database nhưng vẫn chậm ở local vì hàng triệu dòng được truyền qua network trước khi local filter.

### 2.2. Chi phí truyền dữ liệu

Giả sử remote table có 10 triệu dòng, mỗi dòng trung bình 200 bytes. Nếu local chỉ cần 5.000 dòng và 3 cột, truyền toàn bộ table là lãng phí lớn.

Ví dụ minh họa:

| Cách thực hiện | Số dòng truyền | Kích thước trung bình | Dữ liệu xấp xỉ |
| --- | ---: | ---: | ---: |
| Lấy toàn bộ remote table | 10.000.000 | 200 bytes | 2.000 MB |
| Lọc tại remote | 5.000 | 200 bytes | 1 MB |
| Lọc và chỉ lấy 3 cột | 5.000 | 40 bytes | 0,2 MB |

Số liệu chỉ để minh họa. Kích thước thực tế phụ thuộc kiểu dữ liệu, encoding, protocol và cách fetch.

### 2.3. Network round trips

Ngoài bytes, số lần round trip cũng quan trọng. Nếu ứng dụng hoặc execution plan thực hiện nhiều remote calls nhỏ, tổng thời gian có thể bị chi phối bởi network latency.

Ví dụ:

- Một remote query trả 1 triệu dòng trong vài batch fetch.
- Một plan khác gọi remote query lặp lại hàng nghìn lần, mỗi lần lấy một dòng.

Ngay cả khi tổng bytes tương đương, plan có nhiều round trips thường có latency cao hơn.

### 2.4. Join sai vị trí

Nếu bảng lớn ở remote nhưng local site kéo dữ liệu về rồi mới join với bảng khác, lượng dữ liệu truyền có thể rất lớn.

Ngược lại, nếu remote site chỉ có bảng nhỏ và local site có phần lớn dữ liệu cần xử lý, kéo bảng nhỏ về local có thể hợp lý hơn. Mục tiêu không phải luôn chạy join ở remote mà là chọn nơi giảm tổng chi phí.

## 3. Predicate pushdown là gì?

Predicate pushdown là đưa điều kiện lọc đến gần nơi dữ liệu được lưu trữ để loại bỏ các dòng không cần thiết trước khi truyền qua network.

### 3.1. Ví dụ chưa tối ưu

~~~sql
SELECT
    customer_id,
    customer_name,
    status,
    region_id
FROM customers@sales_link;
~~~

Nếu local chỉ cần khách hàng ACTIVE ở region 10, lấy toàn bộ bảng rồi lọc ở local sẽ truyền nhiều dữ liệu không cần thiết.

### 3.2. Đưa điều kiện vào remote query

~~~sql
SELECT
    customer_id,
    customer_name,
    status,
    region_id
FROM customers@sales_link
WHERE status = 'ACTIVE'
  AND region_id = 10;
~~~

Oracle có thể gửi predicate tới remote database. Remote optimizer lọc dòng trước khi trả kết quả.

### 3.3. Filter theo thời gian

Ưu tiên predicate dạng range trên cột ngày:

~~~sql
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

Điều kiện nửa mở giúp bao phủ toàn bộ ngày cuối mà không cần dựa vào thời điểm 23:59:59. Nó cũng tránh bọc cột bằng hàm TRUNC trong predicate, nhờ đó remote optimizer có thể sử dụng index/range access nếu có index phù hợp.

### 3.4. Tránh bọc cột bằng hàm khi không cần

Ví dụ:

~~~sql
WHERE TRUNC(order_date) = DATE '2026-01-15'
~~~

Cách viết này có thể làm khó việc sử dụng index thường trên ORDER_DATE. Viết lại:

~~~sql
WHERE order_date >= DATE '2026-01-15'
  AND order_date <  DATE '2026-01-16'
~~~

Predicate pushdown và index access là hai vấn đề liên quan nhưng khác nhau:

- Predicate pushdown quyết định filter chạy ở site nào.
- Index access quyết định remote database tìm dòng phù hợp bằng cách nào.

Predicate được đẩy xuống remote nhưng remote vẫn có thể full scan nếu optimizer thấy đó là phương án tốt hơn.

### 3.5. Điều kiện kết hợp local và remote

Giả sử điều kiện chỉ phụ thuộc cột remote:

~~~sql
WHERE c.status = 'ACTIVE'
  AND o.order_date >= :from_date
~~~

Hai điều kiện có thể được áp dụng ở remote site vì tất cả cột nằm tại remote.

Nếu điều kiện phụ thuộc bảng local:

~~~sql
WHERE c.region_id = l.region_id
  AND l.enabled = 'Y'
~~~

Điều kiện liên quan LOCAL_REGIONS không thể được đánh giá độc lập trên remote site nếu remote không có dữ liệu đó. Optimizer có thể phải gửi một tập key từ local sang remote, kéo dữ liệu về local hoặc chọn một execution site khác.

## 4. Projection pushdown: chỉ lấy cột cần thiết

Projection pushdown là chỉ chọn những cột cần dùng trong kết quả cuối cùng hoặc trong join/filter/aggregate.

### 4.1. Tránh SELECT *

Không nên:

~~~sql
SELECT *
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01';
~~~

Nếu ứng dụng chỉ cần ORDER_ID, CUSTOMER_ID và AMOUNT:

~~~sql
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01';
~~~

Các cột CLOB, BLOB, XMLTYPE hoặc cột văn bản lớn có thể làm bytes truyền tăng đáng kể. Không lấy những cột đó nếu query không cần.

### 4.2. Cột phục vụ join/filter vẫn phải được giữ

Nếu outer query cần join theo CUSTOMER_ID, remote inline view phải trả CUSTOMER_ID dù cột này không xuất hiện trong kết quả cuối.

~~~sql
SELECT
    r.customer_name,
    l.region_name
FROM (
    SELECT
        customer_id,
        customer_name,
        region_id
    FROM customers@sales_link
    WHERE status = 'ACTIVE'
) r
JOIN local_regions l
  ON l.region_id = r.region_id;
~~~

Không loại bỏ cột join key khi tối ưu projection.

### 4.3. Projection giảm bytes, không nhất thiết giảm số rows

Nếu vẫn trả 1 triệu dòng nhưng bỏ 10 cột lớn, network bytes có thể giảm nhiều. Vì vậy cần theo dõi cả:

- Số dòng trả về.
- Số cột.
- Độ rộng dữ liệu.
- Số bytes truyền.

## 5. Giảm dữ liệu bằng aggregation, DISTINCT và semi-join

Ngoài WHERE và danh sách cột, có thể giảm dữ liệu bằng cách thực hiện phép tổng hợp tại remote site.

### 5.1. Aggregate tại remote

Không tối ưu:

~~~sql
SELECT
    region_id,
    SUM(amount)
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY region_id;
~~~

Optimizer có thể đã đẩy GROUP BY xuống remote. Nhưng khi query phức tạp, hãy kiểm tra execution plan thay vì giả định.

Nếu cần viết rõ remote query block:

~~~sql
SELECT
    r.region_id,
    r.total_amount
FROM (
    SELECT
        region_id,
        SUM(amount) AS total_amount
    FROM orders@sales_link
    WHERE order_date >= DATE '2026-01-01'
      AND order_date <  DATE '2026-02-01'
    GROUP BY region_id
) r;
~~~

Remote site chỉ cần trả một dòng cho mỗi region thay vì mọi order.

### 5.2. DISTINCT tại nơi phù hợp

Nếu local chỉ cần danh sách customer IDs duy nhất:

~~~sql
SELECT customer_id
FROM (
    SELECT DISTINCT customer_id
    FROM orders@sales_link
    WHERE order_date >= DATE '2026-01-01'
);
~~~

DISTINCT tại remote có thể giảm mạnh số dòng truyền. Tuy nhiên, nếu cần giữ từng order hoặc phép DISTINCT có semantics phụ thuộc kiểu dữ liệu/collation, phải bảo đảm kết quả tương đương.

### 5.3. EXISTS và semi-join

Khi chỉ cần kiểm tra tồn tại, tránh kéo toàn bộ dữ liệu của bảng phụ:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers@sales_link c
WHERE c.status = 'ACTIVE'
  AND EXISTS (
      SELECT 1
      FROM orders@sales_link o
      WHERE o.customer_id = c.customer_id
        AND o.order_date >= DATE '2026-01-01'
  );
~~~

Vì hai bảng cùng remote site, Oracle có cơ hội thực hiện semi-join tại remote database. Execution plan cần xác nhận phép xử lý thực sự được đẩy xuống.

### 5.4. COUNT thay vì truyền rows

Nếu ứng dụng chỉ cần số lượng:

~~~sql
SELECT COUNT(*)
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

Remote database có thể tính COUNT và chỉ trả một giá trị thay vì truyền toàn bộ order rows.

### 5.5. Top-N và pagination

Nếu chỉ cần 20 kết quả đầu:

~~~sql
SELECT
    order_id,
    order_date,
    amount
FROM orders@sales_link
WHERE status = 'OPEN'
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Đưa ORDER BY và FETCH FIRST vào remote query block có thể giúp remote site chỉ trả các dòng cần thiết. Phải dùng thứ tự xác định, ví dụ thêm ORDER_ID làm tie-breaker, để kết quả ổn định.

Với pagination nhiều trang, keyset pagination thường tránh chi phí lớn của OFFSET:

~~~sql
SELECT
    order_id,
    order_date,
    amount
FROM orders@sales_link
WHERE status = 'OPEN'
  AND (
       order_date < :last_order_date
       OR (
           order_date = :last_order_date
           AND order_id < :last_order_id
       )
  )
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Chỉ dùng cách này khi thứ tự và điều kiện so sánh phù hợp với yêu cầu nghiệp vụ.

## 6. Collocated inline views

Oracle khuyến nghị gom các bảng nằm trên cùng một database vào một inline view để remote database thực hiện join và filter tại chỗ. Kỹ thuật này được gọi là collocated inline view.

### 6.1. Collocated là gì?

Hai hoặc nhiều bảng được gọi là collocated khi chúng nằm trên cùng một database.

Ví dụ:

- ORDERS nằm tại SALES database.
- CUSTOMERS cũng nằm tại SALES database.
- LOCAL_CAMPAIGN_RULES nằm tại LOCALDB.

ORDERS và CUSTOMERS có thể được join tại SALES database. LOCAL_CAMPAIGN_RULES không collocated với hai bảng đó.

### 6.2. Inline view là gì?

Inline view là một SELECT nằm trong FROM clause và được dùng như một bảng trong query cha.

~~~sql
SELECT x.customer_id, x.total_amount
FROM (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM orders@sales_link
    GROUP BY customer_id
) x;
~~~

### 6.3. Collocated inline view là gì?

Một inline view chỉ truy cập các bảng thuộc cùng một remote database. Remote database có thể join, filter, group và trả về kết quả đã thu gọn.

### 6.4. Ví dụ nhiều bảng remote và một bảng local

Giả sử:

- SALES_LINK trỏ tới remote database.
- ORDERS và CUSTOMERS đều ở remote.
- LOCAL_CAMPAIGN_RULES ở local.
- Mỗi cặp CAMPAIGN_CODE/REGION_ID trong bảng local là duy nhất.

Query:

~~~sql
SELECT
    r.segment,
    SUM(r.order_count) AS order_count,
    SUM(r.revenue) AS revenue
FROM (
    SELECT /*+ NO_MERGE */
        c.region_id,
        c.segment,
        COUNT(*) AS order_count,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= :from_date
      AND o.order_date <  :to_date
      AND c.status = 'ACTIVE'
    GROUP BY c.region_id, c.segment
) r
JOIN (
    SELECT DISTINCT region_id
    FROM local_campaign_rules
    WHERE campaign_code = :campaign_code
      AND enabled = 'Y'
) p
  ON p.region_id = r.region_id
GROUP BY r.segment;
~~~

Phần trong inline view đầu tiên có thể được thực thi tại SALES database:

1. Lọc ORDERS theo ngày.
2. Lọc CUSTOMERS theo trạng thái.
3. Join hai bảng remote theo CUSTOMER_ID.
4. Aggregate theo REGION_ID và SEGMENT.
5. Trả kết quả đã thu gọn về local.

Local site chỉ cần join kết quả với danh sách region được phép.

Điều kiện DISTINCT ở LOCAL_CAMPAIGN_RULES tránh nhân bản kết quả nếu một region có nhiều rule trùng campaign. Nếu nghiệp vụ cho phép nhiều dòng rule và cần giữ multiplicity, phải thiết kế lại phép join/aggregate để giữ đúng semantics.

### 6.5. Vì sao kỹ thuật này hiệu quả?

Giả sử ORDERS có 50 triệu dòng, CUSTOMERS có 2 triệu dòng, nhưng sau filter và group by chỉ còn 30 region/segment combinations. Remote database chỉ trả vài chục dòng aggregate về local thay vì hàng triệu order/customer rows.

Điểm lợi đến từ:

- Giảm số rows qua network.
- Giảm số bytes qua network.
- Giảm số lần remote access.
- Tận dụng CPU, memory và index ở remote site.
- Giảm join/sort/aggregate workload ở local site.

### 6.6. Optimizer có thể tự rewrite

Oracle cost-based optimizer có thể tự rewrite nhiều distributed queries để tận dụng collocated inline views. Không phải lúc nào cũng cần tự viết inline view.

Tuy nhiên, Oracle 19c documentation lưu ý CBO distributed query rewrite không hiệu quả với một số trường hợp có aggregate, subquery hoặc SQL phức tạp. Trong các trường hợp đó, có thể viết collocated inline view và dùng NO_MERGE để ngăn view bị merge vào query block không collocated.

## 7. NO_MERGE hint

NO_MERGE yêu cầu optimizer không merge inline view được chỉ định vào query block cha.

### 7.1. Vì sao cần NO_MERGE?

Khi viết collocated inline view, mục tiêu là giữ các bảng cùng remote site trong một query block để remote database xử lý chúng cùng nhau.

Nếu optimizer merge view vào query cha, query có thể trở thành một distributed statement phức tạp hơn và mất lợi ích của cách nhóm remote tables.

### 7.2. Dùng alias của inline view

~~~sql
SELECT /*+ NO_MERGE(r) */
    l.region_name,
    r.total_amount
FROM local_regions l
JOIN (
    SELECT
        region_id,
        SUM(amount) AS total_amount
    FROM orders@sales_link
    WHERE order_date >= :from_date
      AND order_date <  :to_date
    GROUP BY region_id
) r
  ON r.region_id = l.region_id;
~~~

Hint đặt trong query block cha và tham chiếu alias R của inline view.

### 7.3. Đặt hint trong query block inline view

~~~sql
SELECT
    l.region_name,
    r.total_amount
FROM local_regions l
JOIN (
    SELECT /*+ NO_MERGE */
        region_id,
        SUM(amount) AS total_amount
    FROM orders@sales_link
    WHERE order_date >= :from_date
      AND order_date <  :to_date
    GROUP BY region_id
) r
  ON r.region_id = l.region_id;
~~~

Hai cách đều minh họa cách đặt NO_MERGE. Chỉ dùng hint sau khi đã hiểu query transformation và xác minh plan.

### 7.4. NO_MERGE không phải lệnh đẩy mọi predicate

NO_MERGE chỉ kiểm soát việc merge inline view. Nó không tự động bảo đảm:

- Tất cả predicate được đẩy xuống remote.
- Mọi join được thực hiện ở remote.
- Remote database dùng index.
- Số bytes truyền giảm.

Phải kiểm tra SQL remote thực tế và plan sau khi thêm hint.

### 7.5. Không dùng NO_MERGE cho mọi inline view

Giữ view có thể làm giảm khả năng optimizer kết hợp predicate hoặc chọn join order tốt hơn. Nếu view đã được tối ưu tự động và plan tốt, thêm NO_MERGE có thể làm query chậm hơn.

## 8. DRIVING_SITE hint

DRIVING_SITE chỉ định site mà Oracle nên thực hiện query. Mặc định, cost-based optimizer chọn site thực thi dựa trên chi phí ước tính. Hint này cho phép DBA override lựa chọn đó.

### 8.1. Ví dụ

~~~sql
SELECT /*+ DRIVING_SITE(d) */
    e.employee_id,
    e.last_name,
    d.department_name
FROM employees e
JOIN departments@sales_link d
  ON d.department_id = e.department_id;
~~~

Trong ví dụ này, hint chỉ định site liên quan đến alias D làm driving site. Khi thực thi ở remote site, local rows có thể được gửi tới remote để join; kết quả cuối được trả về local.

### 8.2. Khi nào có lợi?

DRIVING_SITE có thể hữu ích khi:

- Phần lớn dữ liệu nằm ở remote database.
- Remote database có index/statistics tốt hơn cho phép join cần thực hiện.
- Kết quả cuối cùng nhỏ hơn nhiều so với dữ liệu remote ban đầu.
- Chi phí gửi local input sang remote thấp hơn chi phí kéo remote data về local.

### 8.3. Khi nào có thể gây hại?

Không nên ép remote site nếu:

- Local table rất lớn.
- Remote database đang quá tải.
- Network từ local sang remote có latency cao.
- Query phải gửi nhiều local rows sang remote.
- Remote site không có đủ object hoặc quyền để thực hiện phần xử lý cần thiết.
- Optimizer đã chọn local site tốt hơn dựa trên thống kê chính xác.

### 8.4. DRIVING_SITE không đồng nghĩa với predicate pushdown

DRIVING_SITE chọn nơi thực thi query. Predicate pushdown là đưa điều kiện lọc đến site lưu dữ liệu. Hai kỹ thuật có thể hỗ trợ nhau nhưng không giống nhau.

### 8.5. Không mặc định hint sẽ được thực hiện như mong muốn

Hint có thể bị bỏ qua do alias sai, query transformation, cấu trúc SQL hoặc hạn chế của distributed query. Luôn kiểm tra plan và SQL remote sau khi thêm hint.

## 9. Cost-based optimization cho distributed query

Optimizer sử dụng thống kê và ước lượng chi phí để chọn cách thực thi distributed SQL.

### 9.1. CBO làm gì?

Oracle có thể:

1. Merge các view có thể merge.
2. Kiểm tra query block nào chứa các bảng collocated.
3. Rewrite query thành collocated inline views.
4. Chọn vị trí thực hiện các phép join/filter.
5. Ước lượng số rows và bytes cần truyền.
6. Chọn remote hoặc local execution site.

### 9.2. Statistics phải đúng ở từng site

Để CBO chọn plan tốt:

- Thu thập table/index statistics ở local database cho local objects.
- Kết nối tới remote database và thu thập statistics cho remote objects tại chính remote site.
- Kiểm tra stale statistics.
- Xem xét histogram khi phân bố dữ liệu lệch.
- Cập nhật statistics sau bulk load hoặc thay đổi dữ liệu lớn.

Ví dụ gather statistics tại remote database:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => 'SALES',
        tabname => 'ORDERS',
        cascade => TRUE
    );
END;
/
~~~

Phải kết nối trực tiếp tới remote database để thu thập statistics cho remote table. Không chỉ gather local schema statistics rồi kỳ vọng nó cập nhật statistics của object qua database link.

### 9.3. Optimizer không biết đầy đủ mọi biến động network

Cost model có thể không phản ánh chính xác:

- Latency network thay đổi theo thời điểm.
- Băng thông bị chia sẻ với workload khác.
- Remote server có CPU contention.
- Storage latency biến động.
- Connection bị giới hạn hoặc có packet loss.

Do đó, plan có cost thấp hơn không nhất thiết có elapsed time thấp hơn trong mọi thời điểm.

### 9.4. Bind variables và cardinality

Bind variable giúp giảm hard parse và tăng khả năng reuse cursor. Nhưng nếu dữ liệu phân bố rất lệch theo bind value, cardinality ước lượng có thể không đại diện cho mọi giá trị.

Với distributed query, sai cardinality có thể khiến optimizer chọn sai:

- Driving site.
- Join order.
- Join method.
- Số rows truyền qua database link.

Hãy kiểm tra actual rows và bind behavior trên cả local/remote khi query có nhiều biến thể dữ liệu.

## 10. Đọc execution plan của distributed query

Execution plan cho biết Oracle thực hiện những operation nào ở local site và phần nào được gửi tới remote database.

### 10.1. EXPLAIN PLAN

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'DIST_QUERY_01'
FOR
SELECT
    c.customer_id,
    c.customer_name
FROM customers@sales_link c
WHERE c.status = 'ACTIVE'
  AND c.region_id = 10;
~~~

Xem plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        'DIST_QUERY_01',
        'ALL'
    )
);
~~~

Hoặc dùng script SQL*Plus:

~~~text
SQL> @?/rdbms/admin/utlxpls.sql
~~~

### 10.2. Operation REMOTE

Một distributed execution plan thường có operation REMOTE. Đây là phần truy vấn được thực hiện ở remote site.

Ví dụ minh họa:

~~~text
--------------------------------------------------------------------------------
| Id | Operation          | Name       | Rows | Bytes | Cost |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT   |            |      |       |      |
|  1 |  REMOTE            |            |  500 | 25000 |  120 |
--------------------------------------------------------------------------------
~~~

Rows và Bytes ở REMOTE là ước lượng optimizer, không phải số liệu thực tế đã truyền. Cần so sánh với actual execution statistics và SQL*Net counters.

### 10.3. Đọc SQL gửi tới remote database

Oracle lưu SQL remote trong cột OTHER của PLAN_TABLE cho operation REMOTE.

~~~sql
SET LONG 1000000
SET LONGCHUNKSIZE 1000000

SELECT
    id,
    operation,
    options,
    other
FROM plan_table
WHERE statement_id = 'DIST_QUERY_01'
  AND operation = 'REMOTE'
ORDER BY id;
~~~

Đọc nội dung OTHER để xác định:

- Predicate có được gửi sang remote không?
- Remote query chỉ chọn các cột cần thiết không?
- Join remote tables có diễn ra ở remote site không?
- GROUP BY/COUNT/SUM có được thực hiện ở remote không?
- Local site còn phải nhận quá nhiều rows không?

### 10.4. Ví dụ SQL remote đã được đẩy filter

Remote SQL tốt có thể có dạng:

~~~sql
SELECT
    customer_id,
    customer_name
FROM customers
WHERE status = 'ACTIVE'
  AND region_id = 10
~~~

Nếu OTHER chỉ chứa:

~~~sql
SELECT customer_id, customer_name, status, region_id
FROM customers
~~~

thì predicate có thể chưa được đẩy xuống như mong muốn. Cần xem query transformation, remote plan và phần filter còn lại tại local.

### 10.5. Xem toàn bộ nội dung OTHER

Nếu SQL*Plus cắt nội dung:

~~~text
SQL> SET LONG 1000000
SQL> SET LONGCHUNKSIZE 1000000
~~~

Sau đó truy vấn lại PLAN_TABLE.OTHER.

### 10.6. Đọc các operation xung quanh REMOTE

Các operation phía trên REMOTE cho biết local site còn thực hiện gì sau khi nhận dữ liệu:

- HASH JOIN hoặc NESTED LOOPS: join tiếp tại local.
- SORT GROUP BY: aggregate/sort tại local.
- FILTER: predicate còn được kiểm tra tại local.
- VIEW: xử lý qua inline view.
- REMOTE: lấy dữ liệu từ remote site.

Không phải cứ có operation REMOTE là plan xấu. Điều quan trọng là remote operation trả về bao nhiêu rows/bytes và local còn phải làm gì.

## 11. EXPLAIN PLAN và execution plan thực tế

EXPLAIN PLAN tạo kế hoạch ước lượng cho câu SQL. Nó không thực thi query và không cung cấp actual rows/elapsed time.

### 11.1. Hạn chế của EXPLAIN PLAN

Kết quả có thể khác plan thực thi do:

- Bind values.
- Bind peeking/adaptive cursor sharing.
- Session parameters.
- Statistics thay đổi.
- Object metadata khác thời điểm thực thi.
- SQL được thực thi trong môi trường khác.

### 11.2. Thu thập actual plan

Có thể thêm GATHER_PLAN_STATISTICS:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
    c.customer_id,
    c.customer_name
FROM customers@sales_link c
WHERE c.status = 'ACTIVE'
  AND c.region_id = 10;
~~~

Ngay sau khi query chạy trong cùng session:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST'
    )
);
~~~

Tùy cách query được thực thi và phiên bản, thông tin remote SQL có thể được hiển thị trong phần Remote SQL Information của plan. Nếu không thấy đầy đủ, dùng EXPLAIN PLAN và PLAN_TABLE.OTHER để đọc SQL remote.

### 11.3. Các cột cần quan sát

| Cột | Ý nghĩa |
| --- | --- |
| E-Rows | Số rows optimizer ước lượng |
| A-Rows | Số rows thực tế |
| Starts | Số lần operation được khởi chạy |
| Buffers | Logical I/O |
| Reads | Physical reads |
| A-Time | Thời gian operation |
| OMem/1Mem | Bộ nhớ ước lượng hoặc sử dụng cho một số operation |

Nếu REMOTE operation có A-Rows lớn hơn nhiều so với kết quả cuối cùng, local site có thể đang nhận quá nhiều dữ liệu trước khi lọc/join.

### 11.4. Starts rất quan trọng

Nếu operation REMOTE có STARTS lớn, remote SQL có thể được gọi lặp lại nhiều lần. Một nested loops plan có thể gọi remote side cho mỗi dòng outer input.

Ví dụ:

- Local outer rows: 100.000.
- Remote lookup: một lần cho mỗi outer row.
- Starts ở remote: gần 100.000.

Trong tình huống này, dù mỗi remote call trả ít dữ liệu, network round trips có thể làm query rất chậm. Cần xem xét đổi join strategy, collocated query hoặc driving site phù hợp.

## 12. Đo network traffic và round trips

Để chứng minh query rewrite có hiệu quả, cần đo dữ liệu thực sự đi qua database link.

### 12.1. Session statistics

Chạy query trong một session riêng, ghi giá trị trước và sau khi query:

~~~sql
SELECT
    n.name,
    m.value
FROM v$mystat m
JOIN v$statname n
  ON n.statistic# = m.statistic#
WHERE n.name IN (
    'bytes sent via SQL*Net to dblink',
    'bytes received via SQL*Net from dblink',
    'SQL*Net roundtrips to/from dblink'
)
ORDER BY n.name;
~~~

Tính delta giữa hai lần đọc để ước lượng bytes và round trips phát sinh bởi query. Cần bảo đảm session không chạy workload khác giữa hai lần đo.

### 12.2. Các statistic cần hiểu

| Statistic | Ý nghĩa |
| --- | --- |
| bytes sent via SQL*Net to dblink | Bytes local gửi qua database link |
| bytes received via SQL*Net from dblink | Bytes local nhận qua database link |
| SQL*Net roundtrips to/from dblink | Số lượt trao đổi request/response qua database link |

### 12.3. Delta thay vì tổng tích lũy

Các statistic trong V$MYSTAT là số tích lũy theo session. Không so sánh trực tiếp giá trị của hai session có tuổi đời khác nhau. Hãy lấy snapshot trước/sau và tính delta.

### 12.4. Wait events

Có thể quan sát wait events liên quan:

- SQL*Net message to dblink.
- SQL*Net message from dblink.

Các wait này giúp hiểu thời gian session chờ trao đổi với remote database. Một wait event lớn không tự chứng minh network là nguyên nhân duy nhất; remote CPU, remote I/O, fetch pattern và ứng dụng cũng có thể ảnh hưởng.

### 12.5. SQL trace

SQL trace/TKPROF có thể giúp xem số lần execute/fetch và thời gian chờ. Trong môi trường production, chỉ bật trace theo session hoặc SQL cụ thể trong thời gian ngắn, có kiểm soát dung lượng và quyền truy cập trace files.

### 12.6. Không dùng AWR/ASH nếu chưa xác nhận license

AWR/ASH và một số tính năng SQL Monitoring có thể yêu cầu Oracle Diagnostics Pack hoặc Tuning Pack tùy chức năng. Xác nhận license của tổ chức trước khi sử dụng. Có thể dùng V$SESSION, V$MYSTAT, V$SESSTAT, V$SQL, SQL Trace và TKPROF theo quyền/cấu hình được phép.

## 13. Ví dụ tuning từ đầu đến cuối

Giả sử LOCALDB có bảng LOCAL_REGION_FILTER, còn SALES_LINK trỏ tới database chứa ORDERS và CUSTOMERS.

Mục tiêu: tính doanh thu theo segment trong một khoảng thời gian và chỉ lấy những region được phép trong campaign hiện tại.

### 13.1. Query ban đầu

~~~sql
SELECT
    c.segment,
    c.region_id,
    SUM(o.amount) AS revenue
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id
JOIN local_region_filter f
  ON f.region_id = c.region_id
WHERE o.order_date >= :from_date
  AND o.order_date <  :to_date
  AND c.status = 'ACTIVE'
  AND f.campaign_code = :campaign_code
  AND f.enabled = 'Y'
GROUP BY c.segment, c.region_id;
~~~

Optimizer có thể tự collocate hai bảng remote và xử lý filter tại remote. Tuy nhiên, do query có local table, aggregate và nhiều điều kiện, cần kiểm tra plan để biết thực tế.

### 13.2. Viết lại remote collocated view

~~~sql
SELECT
    r.segment,
    r.region_id,
    r.revenue
FROM (
    SELECT /*+ NO_MERGE */
        c.segment,
        c.region_id,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= :from_date
      AND o.order_date <  :to_date
      AND c.status = 'ACTIVE'
    GROUP BY c.segment, c.region_id
) r
JOIN (
    SELECT DISTINCT region_id
    FROM local_region_filter
    WHERE campaign_code = :campaign_code
      AND enabled = 'Y'
) f
  ON f.region_id = r.region_id;
~~~

Remote site thực hiện join, filter theo ngày/trạng thái và aggregate. Local site chỉ join tập kết quả đã thu gọn với danh sách region.

### 13.3. Kiểm tra semantics

Trước khi benchmark, xác nhận:

- LOCAL_REGION_FILTER có trùng REGION_ID hay không.
- Nếu có trùng, DISTINCT có đúng với nghiệp vụ không.
- NULL trong join keys có semantics phù hợp không.
- Cách tính SUM/COUNT có bị nhân bản do join không.
- Date range có cùng timezone/business meaning không.
- Kết quả trước và sau rewrite giống nhau.

### 13.4. Kiểm tra execution plan

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'DIST_BEFORE'
FOR
SELECT
    c.segment,
    c.region_id,
    SUM(o.amount) AS revenue
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id
JOIN local_region_filter f
  ON f.region_id = c.region_id
WHERE o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
  AND c.status = 'ACTIVE'
  AND f.campaign_code = 'JAN26'
  AND f.enabled = 'Y'
GROUP BY c.segment, c.region_id;
~~~

Sau đó explain plan cho query đã rewrite bằng STATEMENT_ID khác. So sánh:

- Số operation REMOTE.
- Rows/Bytes tại REMOTE.
- Predicate trong SQL remote.
- Join giữa ORDERS và CUSTOMERS có nằm trong remote SQL không.
- Aggregate có được thực hiện ở remote không.
- Số STARTS của remote operation.
- Join/sort còn lại ở local.

### 13.5. Đo thực tế

Chạy từng query trong session riêng:

1. Snapshot V$MYSTAT trước query.
2. Thực thi query với cùng bind values.
3. Fetch hết result set.
4. Snapshot V$MYSTAT sau query.
5. Tính delta bytes và round trips.
6. Lưu elapsed time, CPU, buffer gets và actual rows.
7. Chạy lặp lại nhiều lần trong điều kiện tương đương.

Không chỉ fetch vài dòng đầu rồi kết luận query nhanh; phải fetch hết kết quả nếu workload thật cũng cần toàn bộ rows.

## 14. Nhiều remote databases

Một distributed query có thể tham chiếu nhiều database links.

### 14.1. Các bảng cùng một remote site

~~~sql
SELECT *
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id;
~~~

Hai bảng cùng remote database nên có thể được join tại remote site.

### 14.2. Các bảng ở hai remote sites khác nhau

~~~sql
SELECT *
FROM orders@sales_link o
JOIN exchange_rates@finance_link x
  ON x.currency_code = o.currency_code;
~~~

ORDERS và EXCHANGE_RATES không collocated. Oracle phải điều phối việc trao đổi giữa các site và query execution site. Tùy dữ liệu, có thể:

- Lấy dữ liệu đã lọc từ SALES về local rồi join với FINANCE.
- Lấy dữ liệu đã lọc từ FINANCE về local rồi join với SALES.
- Chọn một remote site làm driving site nếu có thể và hợp lý.
- Tạo một bước staging/materialization nếu query quá phức tạp và chạy thường xuyên.

### 14.3. Gom xử lý tại từng site

Nếu mỗi site có nhiều bảng liên quan, nên tạo một collocated inline view cho từng site:

~~~sql
SELECT
    s.customer_id,
    s.sales_total,
    f.rate
FROM (
    SELECT /*+ NO_MERGE */
        o.customer_id,
        o.currency_code,
        SUM(o.amount) AS sales_total
    FROM orders@sales_link o
    WHERE o.order_date >= :from_date
      AND o.order_date <  :to_date
    GROUP BY o.customer_id, o.currency_code
) s
JOIN (
    SELECT /*+ NO_MERGE */
        currency_code,
        rate
    FROM exchange_rates@finance_link
    WHERE rate_date = :rate_date
) f
  ON f.currency_code = s.currency_code;
~~~

Mỗi remote site chỉ trả dữ liệu đã lọc/tổng hợp cần cho bước join cuối. Cần kiểm tra plan để xác nhận query block thực sự được thực hiện ở site dự kiến.

### 14.4. Không tạo remote-to-remote dependency tùy tiện

Nếu remote site A phải mở database link tiếp tới remote site B, kiến trúc có thể phát sinh thêm dependency, authentication và network path. Không mặc định remote database có thể truy cập link của local database hoặc một database thứ ba. Hãy thiết kế rõ site nào thực hiện mỗi phần truy vấn.

## 15. Khi predicate không thể hoặc không nên pushdown

Không phải mọi điều kiện đều có thể đẩy xuống remote.

### 15.1. Điều kiện phụ thuộc local table

Predicate dùng cột local không thể được đánh giá ở remote site nếu remote không có dữ liệu đó. Cần chọn cách gửi tập key, kéo kết quả về local hoặc đổi driving site.

### 15.2. Hàm hoặc expression không có ở remote

Nếu query gọi function chỉ tồn tại ở local database, remote site không thể thực hiện function đó trực tiếp. Function phải được hỗ trợ/có sẵn tại remote hoặc phần xử lý phải diễn ra local.

### 15.3. User-defined function

Một PL/SQL function local có thể không được đẩy xuống remote vì remote database không có function hoặc semantics thực thi không tương đương. Không giả định function trong WHERE luôn được thực hiện ở nơi bảng nằm.

### 15.4. Data type và conversion

Các kiểu dữ liệu hoặc expression có conversion khác nhau giữa database có thể làm hạn chế remote execution:

- CLOB/BLOB.
- Object types.
- User-defined types.
- NLS-sensitive conversion.
- Implicit conversion giữa character và number/date.
- Function có semantics khác theo character set/timezone.

### 15.5. Subquery, aggregate và SQL phức tạp

Oracle 19c documentation nêu cost-based distributed query rewrite không hiệu quả với một số query có aggregate, subquery hoặc SQL phức tạp. Khi gặp trường hợp này, hãy xem xét collocated inline view và NO_MERGE, sau đó xác minh plan.

### 15.6. Outer join và NULL semantics

Khi rewrite outer join, predicate đặt ở ON và WHERE có thể tạo kết quả khác nhau. Ví dụ:

~~~sql
SELECT *
FROM local_customers l
LEFT JOIN remote_orders@sales_link r
  ON r.customer_id = l.customer_id
 AND r.status = 'OPEN';
~~~

Nếu chuyển predicate R.STATUS = 'OPEN' xuống WHERE ở query cha, các dòng không có remote order có thể bị loại bỏ, làm LEFT JOIN hoạt động như INNER JOIN.

Luôn kiểm tra semantics trước khi đẩy predicate hoặc đổi join order.

## 16. Database link và session behavior

Distributed query còn chịu ảnh hưởng bởi vòng đời connection và transaction.

### 16.1. Remote session tồn tại trong local session

Oracle có thể tái sử dụng remote connection được tạo qua database link trong suốt local session. Vì vậy, nhiều câu SQL dùng cùng link có thể chia sẻ remote session.

### 16.2. Đóng database link

Khi không còn cần remote connection:

~~~sql
ALTER SESSION CLOSE DATABASE LINK sales_link;
~~~

Trước khi đóng:

- Đóng cursor đang dùng link.
- Kết thúc transaction có sử dụng link bằng COMMIT hoặc ROLLBACK.
- Cần quyền ALTER SESSION.

Không đóng link giữa lúc ứng dụng còn cursor hoặc transaction phụ thuộc vào nó.

### 16.3. SELECT qua database link và transaction

Oracle documentation lưu ý khi thực hiện SELECT qua database link, transaction lock được đặt trên undo segments; để giải phóng segment cần COMMIT hoặc ROLLBACK.

Trong ứng dụng, không để transaction phân tán mở lâu hơn cần thiết. Việc giữ remote connection và transaction kéo dài có thể làm tăng resource usage và gây khó khăn khi xử lý lỗi network.

### 16.4. Distributed transaction

Nếu một transaction cập nhật dữ liệu ở nhiều database, Oracle có thể dùng distributed transaction/two-phase commit. Tuning SELECT khác với tuning distributed DML. Khi một phần distributed update thất bại, phải xử lý transaction outcome và rollback theo quy trình; không chỉ tối ưu predicate.

## 17. Bind variables và dữ liệu remote

Bind variables giúp giảm hard parse và bảo vệ SQL khỏi nối chuỗi không an toàn. Với distributed query, cần xem xét bind values và remote cursor behavior.

### 17.1. Dùng bind variables

~~~sql
SELECT
    order_id,
    amount
FROM orders@sales_link
WHERE order_date >= :from_date
  AND order_date <  :to_date
  AND status = :status;
~~~

Bind giúp tái sử dụng SQL và giảm parse overhead.

### 17.2. Bind skew

Nếu một giá trị STATUS trả 100 dòng, giá trị khác trả 10 triệu dòng, cùng một plan có thể không tốt cho cả hai. Kiểm tra cardinality và actual rows với các bind values đại diện.

### 17.3. Không nối literal vào SQL

Tránh tạo SQL khác nhau cho từng giá trị bằng string concatenation nếu không cần. Điều đó có thể làm tăng hard parses và gây rủi ro SQL injection.

### 17.4. Kiểm tra remote SQL

SQL trong PLAN_TABLE.OTHER giúp xác định bind/predicate nào được gửi đến remote site. Khi cần điều tra sâu, kiểm tra cursor tương ứng tại remote database bằng SQL_ID hoặc SQL text theo quyền được phép.

## 18. NLS, timezone và semantics khi rewrite

Distributed SQL có thể chạy trên database có NLS settings, timezone hoặc character set khác nhau.

### 18.1. Tránh implicit conversion

Không nên:

~~~sql
WHERE order_date = '01/02/2026'
~~~

Chuỗi có thể được parse khác nhau theo NLS_DATE_FORMAT. Dùng DATE literal hoặc bind DATE:

~~~sql
WHERE order_date >= DATE '2026-02-01'
  AND order_date <  DATE '2026-02-02'
~~~

### 18.2. Timestamp with time zone

Nếu query lọc TIMESTAMP WITH TIME ZONE, xác định rõ timezone business. Không thay đổi predicate chỉ để pushdown nếu điều đó làm thay đổi khoảng thời gian được chọn.

### 18.3. Character comparison

Collation, character set và NLS_COMP/NLS_SORT có thể ảnh hưởng so sánh chuỗi. Khi local và remote có cấu hình khác nhau, kiểm tra kết quả trước/sau rewrite với dữ liệu có dấu, chữ hoa/thường và ký tự đặc biệt.

### 18.4. Đảm bảo kết quả tương đương

Tối ưu distributed query phải bảo toàn:

- NULL semantics.
- Duplicate rows.
- Outer join behavior.
- Aggregate behavior.
- Timezone conversion.
- Character comparison.
- Numeric precision/rounding.

## 19. SQL Plan Management và distributed query

SQL Profiles, SQL Plan Baselines, SQL Patches và stored outlines có thể không hoạt động như kỳ vọng với các câu query tham chiếu remote tables qua database links.

Ví dụ, local SQL plan baseline có thể không bảo đảm remote portion sử dụng đúng plan remote đã có khi baseline được tạo.

Vì vậy:

- Kiểm tra plan ở local execution site.
- Kiểm tra SQL remote và plan tại remote database.
- Không giả định baseline local khóa được mọi remote execution choice.
- Thu thập statistics ở remote site.
- Benchmark sau khi thay đổi query, hint hoặc remote indexes.

Đây là một khác biệt quan trọng so với tuning SQL chỉ chạy trong một database.

## 20. Checklist tuning distributed query

**Hiểu query**

- Những bảng nào nằm local?
- Những bảng nào nằm remote?
- Có bao nhiêu database links?
- Bảng nào lớn nhất?
- Kết quả cuối cần bao nhiêu rows/cột?
- Điều kiện nào chỉ phụ thuộc remote columns?
- Điều kiện nào phụ thuộc local data?

**Giảm dữ liệu**

- Có SELECT * không?
- Predicate remote có được gửi xuống remote không?
- Có thể aggregate trước khi truyền không?
- Có thể DISTINCT/EXISTS/semi-join tại remote không?
- Có thể giới hạn Top-N tại remote không?
- Join keys có được giữ lại đầy đủ không?

**Chọn execution site**

- Các bảng remote có collocated không?
- Có thể dùng collocated inline view không?
- NO_MERGE có thực sự cần thiết không?
- DRIVING_SITE có lợi với phân bố dữ liệu hiện tại không?
- Remote database có đủ CPU/I/O không?

**Đọc plan và đo**

- Có operation REMOTE không?
- SQL trong PLAN_TABLE.OTHER chứa predicate cần thiết không?
- Remote operation trả bao nhiêu E-Rows/A-Rows?
- Starts của REMOTE có quá cao không?
- Bytes sent/received qua database link là bao nhiêu?
- Network round trips thay đổi thế nào?
- Actual elapsed time có cải thiện không?

**Bảo toàn semantics**

- Outer join và NULL behavior còn đúng không?
- Duplicate rows có bị thay đổi không?
- Aggregate có bị nhân bản do join không?
- Date/timezone conversion có giống trước không?
- Kết quả trước/sau rewrite có bằng nhau không?

## 21. Bài thực hành tổng hợp

Lab giả lập một distributed query có dữ liệu tại remote database và local database. Cần có hai Oracle databases hoặc môi trường lab hỗ trợ database link.

### Bước 1 — Tạo database link

Ví dụ do DBA tạo trong schema lab:

~~~sql
CREATE DATABASE LINK sales_link
CONNECT TO sales_user
IDENTIFIED BY "Replace_With_Lab_Secret"
USING 'SALESDB';
~~~

Không ghi password thật vào repository hoặc script chia sẻ. Có thể dùng private/public database link theo chính sách của lab.

### Bước 2 — Kiểm tra remote connection

~~~sql
SELECT
    name,
    db_unique_name,
    database_role
FROM v$database@sales_link;
~~~

### Bước 3 — Chạy query chưa tối ưu

~~~sql
SELECT *
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01';
~~~

Ghi nhận số rows và SQL*Net statistics trước/sau.

### Bước 4 — Giảm projection và đẩy filter

~~~sql
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';
~~~

So sánh bytes received qua database link.

### Bước 5 — Tạo remote join

~~~sql
SELECT
    c.region_id,
    COUNT(*) AS order_count,
    SUM(o.amount) AS revenue
FROM orders@sales_link o
JOIN customers@sales_link c
  ON c.customer_id = o.customer_id
WHERE o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2026-02-01'
  AND c.status = 'ACTIVE'
GROUP BY c.region_id;
~~~

### Bước 6 — Viết collocated inline view

~~~sql
SELECT /*+ NO_MERGE(r) */
    r.region_id,
    r.order_count,
    r.revenue
FROM (
    SELECT
        c.region_id,
        COUNT(*) AS order_count,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
      AND c.status = 'ACTIVE'
    GROUP BY c.region_id
) r;
~~~

So sánh SQL remote trong plan và số rows/bytes.

### Bước 7 — Thử DRIVING_SITE

Nếu có bảng local để join:

~~~sql
SELECT /*+ DRIVING_SITE(r) */
    r.region_id,
    r.revenue,
    l.region_name
FROM (
    SELECT
        c.region_id,
        SUM(o.amount) AS revenue
    FROM orders@sales_link o
    JOIN customers@sales_link c
      ON c.customer_id = o.customer_id
    WHERE o.order_date >= DATE '2026-01-01'
      AND o.order_date <  DATE '2026-02-01'
    GROUP BY c.region_id
) r
JOIN local_regions l
  ON l.region_id = r.region_id;
~~~

Kiểm tra hint có được áp dụng không và local input được gửi đi bao nhiêu.

### Bước 8 — Explain plan

~~~sql
EXPLAIN PLAN
    SET STATEMENT_ID = 'LAB_DISTRIBUTED'
FOR
SELECT
    order_id,
    customer_id,
    amount
FROM orders@sales_link
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01';

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY(
        NULL,
        'LAB_DISTRIBUTED',
        'ALL'
    )
);
~~~

### Bước 9 — Đọc remote SQL

~~~sql
SET LONG 1000000

SELECT id, operation, other
FROM plan_table
WHERE statement_id = 'LAB_DISTRIBUTED'
  AND operation = 'REMOTE';
~~~

### Bước 10 — Đo SQL*Net

Chụp V$MYSTAT trước và sau query. Tính delta của bytes sent, bytes received và round trips.

### Bước 11 — So sánh kết quả

| Chỉ số | Query gốc | Query rewrite |
| --- | ---: | ---: |
| Rows returned |  |  |
| Bytes received from dblink |  |  |
| Bytes sent to dblink |  |  |
| Round trips |  |  |
| Elapsed time |  |  |
| CPU time |  |  |
| REMOTE Starts |  |  |
| Remote estimated rows |  |  |

### Bước 12 — Xác nhận tính đúng

So sánh số dòng, aggregate values, NULLs và duplicate rows giữa hai query. Chỉ chấp nhận rewrite khi kết quả tương đương và số liệu cho thấy hiệu quả.

## 22. Câu hỏi tự kiểm tra

1. Distributed query là gì?
2. Local site và remote site khác nhau thế nào?
3. Oracle chia distributed query thành các phần nào?
4. Predicate pushdown có mục tiêu gì?
5. Projection pushdown giảm chi phí nào?
6. Vì sao SELECT * thường không phù hợp với remote table lớn?
7. Collocated tables là gì?
8. Collocated inline view là gì?
9. Vì sao nên join các remote tables cùng site trước khi truyền dữ liệu?
10. NO_MERGE dùng để làm gì?
11. NO_MERGE có bảo đảm mọi predicate được pushdown không?
12. DRIVING_SITE chọn điều gì?
13. Khi nào DRIVING_SITE có thể gây hại?
14. Cost-based optimizer có thể rewrite distributed query thế nào?
15. Những loại SQL nào có thể hạn chế distributed query rewrite tự động?
16. Vì sao cần statistics ở remote database?
17. Operation REMOTE trong plan có ý nghĩa gì?
18. Cột OTHER trong PLAN_TABLE chứa thông tin gì?
19. E-Rows và A-Rows khác nhau thế nào?
20. Vì sao REMOTE Starts lớn có thể là vấn đề?
21. Những SQL*Net statistics nào giúp đo dữ liệu truyền?
22. Vì sao phải lấy delta trước/sau query?
23. EXPLAIN PLAN khác actual execution plan thế nào?
24. Vì sao outer join cần cẩn thận khi chuyển predicate?
25. Vì sao cần dùng date range thay TRUNC(date_column)?
26. Nhiều remote database links ảnh hưởng query ra sao?
27. Vì sao không nên giả định remote site có thể truy cập database link khác?
28. DBMS_STATS cho remote table nên được chạy ở đâu?
29. SQL Plan Baseline local có bảo đảm remote portion giữ nguyên plan không?
30. Điều kiện nào để chấp nhận một query rewrite?

**Gợi ý trả lời:**

1. SQL truy cập dữ liệu ở nhiều database.
2. Local là nơi phát hành SQL; remote là database được truy cập qua link.
3. Local SQL, remote SQL và phần post-processing tại execution site.
4. Lọc dữ liệu tại nơi lưu trữ trước khi truyền về.
5. Số cột và bytes truyền.
6. Vì truyền thêm cột không cần thiết, đặc biệt LOB/large columns.
7. Các bảng cùng nằm trên một database.
8. Inline view chỉ truy cập các bảng của cùng một database.
9. Remote site có thể join/filter/aggregate tại chỗ và trả kết quả nhỏ hơn.
10. Ngăn optimizer merge inline view vào query block cha.
11. Không; cần đọc remote SQL và execution plan.
12. Site nơi query được thực thi.
13. Khi local data lớn phải gửi sang remote hoặc remote đang quá tải/network chậm.
14. Merge view, kiểm tra collocation rồi rewrite thành collocated inline views.
15. Aggregate, subquery và complex SQL có thể hạn chế rewrite.
16. Optimizer cần cardinality/selectivity/cost chính xác tại site lưu bảng.
17. Phần truy vấn được thực hiện ở remote database.
18. SQL statement gửi tới remote site.
19. E-Rows là ước lượng; A-Rows là thực tế.
20. Có thể là remote query bị gọi lặp lại nhiều lần, tăng network round trips.
21. Bytes sent/received via SQL*Net to/from dblink và roundtrips to/from dblink.
22. Vì statistic là số tích lũy của session.
23. EXPLAIN PLAN chỉ ước lượng; actual plan có runtime statistics.
24. Vì predicate ở WHERE có thể loại dòng NULL-extended và đổi outer join thành inner join.
25. Để tạo range predicate dễ dùng index và không mất phần thời gian trong ngày.
26. Có nhiều remote sites, query phải điều phối và chọn nơi join.
27. Vì remote link, credentials và network path không tự động được chia sẻ.
28. Kết nối trực tiếp tới remote database.
29. Không; remote portion có thể dùng plan khác.
30. Kết quả phải tương đương và đo được giảm bytes/round trips hoặc elapsed time trong workload đại diện.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Administrator's Guide — Tuning Distributed Queries](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/developing-applications-for-a-distributed-database-system.html): collocated inline views, cost-based optimization, hints và phân tích execution plan.
- [Oracle Database 19c Administrator's Guide — Using Collocated Inline Views](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/developing-applications-for-a-distributed-database-system.html): cách nhóm các bảng cùng remote site để giảm network traffic.
- [Oracle Database 19c SQL Language Reference — DRIVING_SITE Hint](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Comments.html): điều khiển site thực thi distributed query.
- [Oracle Database 19c SQL Tuning Guide — SQL Tuning Concepts and Execution Plans](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/introduction-to-sql-tuning.html): đọc và phân tích execution plan.
- [Oracle Database 19c Database Reference — V$MYSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-MYSTAT.html): session statistics hiện tại.
- [Oracle Database 19c Database Reference — V$SESSTAT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SESSTAT.html): thống kê sử dụng theo session.
- [Oracle Database 19c SQL Language Reference — ALTER SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-SESSION.html): đóng database link trong session.

**Nguyên tắc cần nhớ:** Distributed query nhanh khi remote database xử lý càng nhiều công việc phù hợp tại nơi dữ liệu đang nằm và chỉ gửi phần kết quả cần thiết về local. Đẩy predicate, giảm projection, aggregate tại remote và gom bảng cùng site bằng collocated inline views. NO_MERGE giữ inline view khi cần; DRIVING_SITE điều khiển nơi thực thi khi có bằng chứng phù hợp. Hãy đọc operation REMOTE và SQL trong PLAN_TABLE.OTHER, đo rows/bytes/round trips bằng execution statistics và SQL*Net counters, rồi so sánh kết quả trước/sau rewrite. Không chấp nhận một hint chỉ vì plan trông đẹp; phải bảo toàn semantics và chứng minh cải thiện bằng số liệu thực tế.
