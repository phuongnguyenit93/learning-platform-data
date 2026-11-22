# Chọn JOIN hay truy vấn con dựa trên ngữ nghĩa và kế hoạch thực thi trong Oracle

Khi cần lấy khách hàng cùng đơn hàng, ta có thể viết một câu JOIN. Khi chỉ cần biết khách hàng có ít nhất một đơn đã thanh toán hay không, ta có thể viết EXISTS. Khi cần tổng số đơn của từng khách hàng, ta có thể tổng hợp bảng đơn hàng trước rồi JOIN, hoặc dùng một scalar subquery tương quan. Những cách viết này có vẻ gần nhau, nhưng **không phải lúc nào chúng cũng trả cùng số dòng hoặc cùng giá trị**.

Vì vậy, câu hỏi “JOIN hay subquery nhanh hơn?” không có một đáp án cố định. Trước tiên phải chọn cách diễn đạt đúng nghiệp vụ: có cần cột từ cả hai bảng không, có cần giữ các hàng trùng không, chỉ cần kiểm tra tồn tại hay cần tính một giá trị, và NULL có thể xuất hiện ở đâu? Sau đó mới xem Oracle optimizer biến đổi truy vấn thành kế hoạch nào và đo chi phí thực tế.

Bài học thuộc nhóm **JOIN và truy vấn con** của Oracle Database. Nội dung so sánh JOIN, EXISTS, IN, NOT EXISTS, NOT IN, scalar subquery, correlated subquery và inline view; giải thích cardinality, NULL, duplicate rows, subquery unnesting, join methods và cách đọc execution plan.

Sau bài này, bạn có thể:

- Chọn JOIN khi cần kết hợp dữ liệu và cột từ nhiều nguồn.
- Chọn EXISTS/NOT EXISTS khi nghiệp vụ là kiểm tra có hoặc không có dòng liên quan.
- Phân biệt IN với EXISTS, NOT IN với NOT EXISTS, đặc biệt khi có NULL.
- Dùng scalar subquery khi cần một giá trị đơn và hiểu điều gì xảy ra nếu subquery trả nhiều dòng.
- Nhận biết correlated subquery và không mặc định nó luôn chạy lặp vật lý cho từng hàng.
- Hiểu cách Oracle có thể unnest subquery thành semi-join/anti-join hoặc biến đổi query block.
- Đọc execution plan, so sánh estimated rows với actual rows và chọn cách viết dựa trên dữ liệu đo được.

> **Phạm vi ví dụ:** Các câu SQL dùng cú pháp Oracle Database 19c. Bảng lab được tạo trong schema/PDB thực hành do bạn quản lý. Không chạy DDL hoặc truy vấn thử tải lớn trên schema ứng dụng đang hoạt động. Kết quả execution plan phụ thuộc phiên bản, thống kê, dữ liệu, bind values, cấu hình và quyền truy cập; bài học không giả định một plan cố định cho mọi hệ thống.

## 1. Bắt đầu từ ý nghĩa nghiệp vụ

Giả sử có hai bảng:

- CUSTOMERS: một dòng cho mỗi khách hàng.
- ORDERS: nhiều dòng đơn hàng có thể thuộc cùng một khách hàng.

Một khách hàng có thể có 0, 1 hoặc nhiều đơn hàng. Đây là quan hệ **một-nhiều (1:N)**.

~~~text
CUSTOMERS                         ORDERS
+-------------+                   +------------------+
| customer_id | 1 ------------- N | order_id         |
| name        |                   | customer_id      |
+-------------+                   | status           |
                                  | amount           |
                                  +------------------+
~~~

Từ quan hệ này có các yêu cầu khác nhau:

| Yêu cầu | Kết quả mong muốn | Cách diễn đạt thường phù hợp |
| --- | --- | --- |
| Hiển thị từng khách hàng cùng từng đơn hàng | Một khách hàng có thể xuất hiện nhiều dòng | JOIN |
| Lấy khách hàng có ít nhất một đơn PAID | Mỗi khách hàng chỉ cần xuất hiện một lần | EXISTS |
| Lấy khách hàng không có đơn PAID | Chỉ các khách hàng không tìm thấy đơn thỏa điều kiện | NOT EXISTS |
| Lấy tổng số đơn của mỗi khách hàng | Một dòng mỗi khách hàng và một giá trị đếm | GROUP BY rồi JOIN, hoặc scalar aggregate subquery |
| Lấy ngày đơn hàng gần nhất của mỗi khách hàng | Một giá trị ngày cho mỗi khách hàng | MAX trong subquery hoặc aggregate view |
| Lấy toàn bộ thông tin của đơn hàng mới nhất | Một dòng đơn hàng được chọn theo quy tắc xác định | ROW_NUMBER()/analytic query |

Đừng bắt đầu bằng việc đoán cú pháp nào nhanh hơn. Hãy mô tả trước **một dòng kết quả đại diện cho điều gì** và liệu một khách hàng có thể xuất hiện nhiều lần hay không.

## 2. JOIN: kết hợp các dòng từ nhiều nguồn

### 2.1. JOIN trả về cặp dòng thỏa điều kiện

Ví dụ lấy thông tin khách hàng và từng đơn hàng:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.status,
    o.amount
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Nếu khách hàng 10 có ba đơn hàng, khách hàng đó xuất hiện ba dòng. Đây là hành vi đúng của quan hệ 1:N: mỗi cặp khách hàng/đơn hàng thỏa điều kiện JOIN tạo một dòng kết quả.

### 2.2. JOIN có thể nhân số dòng

Giả sử:

| Customer ID | Customer |
| ---: | --- |
| 1 | An |
| 2 | Bình |

| Order ID | Customer ID | Amount |
| ---: | ---: | ---: |
| 101 | 1 | 100 |
| 102 | 1 | 200 |
| 103 | 1 | 300 |

INNER JOIN trả:

| Customer ID | Customer | Order ID | Amount |
| ---: | --- | ---: | ---: |
| 1 | An | 101 | 100 |
| 1 | An | 102 | 200 |
| 1 | An | 103 | 300 |

Khách hàng 2 không xuất hiện vì không có đơn hàng khớp. Khách hàng 1 xuất hiện ba lần vì có ba đơn.

Nếu chỉ muốn danh sách khách hàng có đơn hàng, JOIN có thể tạo nhiều dòng trùng customer:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id;
~~~

Muốn mỗi khách hàng chỉ xuất hiện một lần, người viết thường thêm DISTINCT:

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id;
~~~

Câu này có thể cho kết quả nghiệp vụ mong muốn, nhưng đang thực hiện một phép kết hợp tạo nhiều dòng rồi loại trùng. Nếu mục tiêu chỉ là “có ít nhất một đơn hàng”, EXISTS thể hiện ý định trực tiếp hơn và tránh phải yêu cầu kết quả duy nhất bằng DISTINCT.

### 2.3. JOIN khi cần dữ liệu từ cả hai bảng

Nếu báo cáo cần mã đơn, ngày đặt và tên khách hàng, JOIN là cách tự nhiên:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.amount,
    c.customer_name
FROM orders o
JOIN customers c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
~~~

Ở đây cần cột từ cả ORDERS và CUSTOMERS; JOIN là mô hình dữ liệu đúng với kết quả cần trả.

## 3. EXISTS: kiểm tra sự tồn tại thay vì lấy cột của bảng con

### 3.1. Cú pháp cơ bản

EXISTS trả kết quả TRUE nếu subquery tạo ra ít nhất một dòng; nếu không có dòng nào, nó trả FALSE:

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Ý nghĩa: trả mỗi khách hàng có ít nhất một đơn PAID. Khách hàng có 1 đơn PAID hay 100 đơn PAID vẫn chỉ xuất hiện một lần vì truy vấn ngoài đọc từ CUSTOMERS; subquery chỉ trả lời câu hỏi tồn tại.

### 3.2. Vì sao SELECT 1 trong EXISTS?

Trong EXISTS, Oracle chỉ cần biết subquery có tạo ra hàng hay không. Giá trị trong select list không được dùng để tạo cột kết quả:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
)
~~~

Về ý nghĩa kiểm tra tồn tại, các cách SELECT 1, SELECT o.order_id hoặc SELECT * trong subquery EXISTS thường tương đương. SELECT 1 là quy ước dễ đọc để nhấn mạnh rằng **ta không lấy dữ liệu cột, chỉ kiểm tra có dòng hay không**. Nó không phải mẹo đảm bảo nhanh hơn SELECT *; optimizer không cần đọc giá trị select list chỉ để đánh giá EXISTS.

### 3.3. EXISTS không nhân bản hàng ngoài

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Ngay cả khi một khách hàng có nhiều đơn hàng phù hợp, điều kiện EXISTS vẫn chỉ là một điều kiện đúng/sai cho dòng khách hàng đó. Vì vậy truy vấn trả tối đa một dòng cho mỗi dòng CUSTOMERS ở query block ngoài (trừ khi query ngoài tự JOIN thêm bảng khác làm nhân dòng).

### 3.4. EXISTS với nhiều điều kiện

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status IN ('PAID', 'SHIPPED')
      AND o.created_at >= DATE '2026-01-01'
);
~~~

Subquery chỉ cần tìm một đơn đáp ứng đồng thời tất cả điều kiện. Điều kiện trong subquery xác định **dòng nào được coi là đối tác hợp lệ**.

## 4. IN: kiểm tra giá trị có nằm trong tập kết quả hay không

### 4.1. IN với danh sách giá trị

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE status IN ('ACTIVE', 'TRIAL');
~~~

IN kiểm tra một biểu thức có bằng một trong các giá trị của danh sách theo quy tắc so sánh SQL.

### 4.2. IN với subquery

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = 'PAID'
);
~~~

Ý nghĩa: customer_id của khách hàng nằm trong tập customer_id của các đơn PAID. Trong trường hợp khóa so sánh là non-NULL và subquery chỉ dùng để kiểm tra membership, câu này thường cho cùng tập khách hàng với ví dụ EXISTS tương ứng:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

### 4.3. IN và EXISTS khác nhau ở cách diễn đạt

- IN: giá trị của dòng ngoài có thuộc tập giá trị subquery trả về không?
- EXISTS: có tồn tại dòng trong subquery thỏa quan hệ với dòng ngoài không?

Với một quan hệ khóa đơn giản, hai cách thường tương đương về kết quả. Nhưng cần cẩn thận với NULL, biểu thức so sánh phức tạp và việc sử dụng kết quả trong biểu thức lớn hơn. Không chọn IN hoặc EXISTS chỉ theo khẩu quyết “một cái nhanh hơn”.

### 4.4. IN không nhân bản dòng ngoài

Subquery của IN có thể trả nhiều giá trị trùng, nhưng việc kiểm tra membership không làm nhân bản dòng ngoài:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

Nếu customer_id 1 xuất hiện 20 lần trong subquery, khách hàng 1 vẫn chỉ xuất hiện một lần từ query ngoài, giả sử CUSTOMERS.CUSTOMER_ID là khóa duy nhất. Điều này tương tự ý nghĩa membership của EXISTS, khác với JOIN trực tiếp tạo một dòng cho mỗi cặp khớp.

## 5. NOT EXISTS: tìm những dòng không có đối tác

### 5.1. Cú pháp

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Truy vấn trả khách hàng không có bất kỳ đơn hàng nào. Nếu có một đơn hàng phù hợp, NOT EXISTS là FALSE và khách hàng bị loại.

### 5.2. Thêm điều kiện nghiệp vụ

Tìm khách hàng không có đơn PAID:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Khách hàng có đơn PENDING nhưng không có đơn PAID vẫn được trả về. Đây là lý do phải đưa điều kiện status = 'PAID' vào subquery: ta đang phủ định sự tồn tại của **một đơn PAID**, không phủ định sự tồn tại của mọi đơn.

### 5.3. NOT EXISTS và LEFT JOIN ... IS NULL

Có thể viết anti-join bằng LEFT JOIN:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
LEFT JOIN orders o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE o.order_id IS NULL;
~~~

ORDER_ID phải là cột được đảm bảo NOT NULL ở mọi đơn hàng thật (ví dụ primary key). Khi không có đơn PAID khớp, Oracle tạo hàng NULL mở rộng cho phía orders và o.order_id IS NULL giữ khách hàng đó.

Hai cách NOT EXISTS và LEFT JOIN ... IS NULL thường thể hiện cùng ý nghĩa anti-join khi điều kiện và cột kiểm tra được đặt đúng. NOT EXISTS thường dễ đọc hơn vì không phải chọn một cột phía phải để kiểm tra NULL.

## 6. NOT IN và bẫy NULL

Đây là khác biệt ngữ nghĩa quan trọng nhất khi chọn truy vấn con.

### 6.1. NOT IN với tập không có NULL

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

Nếu subquery chỉ trả các giá trị non-NULL, NOT IN có thể biểu diễn ý nghĩa không nằm trong tập. Nhưng nếu subquery có NULL, kết quả logic thay đổi.

### 6.2. Tại sao một NULL có thể làm NOT IN không trả hàng?

Giả sử subquery trả tập:

~~~text
(1, 2, NULL)
~~~

Với customer_id = 3, biểu thức:

~~~sql
3 NOT IN (1, 2, NULL)
~~~

tương đương logic phủ định của:

~~~sql
3 = 1 OR 3 = 2 OR 3 = NULL
~~~

Hai phép so sánh đầu là FALSE; phép 3 = NULL là UNKNOWN. FALSE OR FALSE OR UNKNOWN cho UNKNOWN. WHERE chỉ giữ TRUE, nên hàng customer_id 3 không được trả về.

Vì vậy:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);
~~~

có thể trả **không dòng nào** nếu subquery có ít nhất một NULL, dù có khách hàng không có đơn hàng.

### 6.3. NOT EXISTS thường an toàn hơn với NULL

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Ở đây NULL trong o.customer_id không tạo ra một quan hệ bằng với customer_id non-NULL; nó không làm phủ định mọi dòng ngoài. Với yêu cầu “không tồn tại hàng có khóa bằng khóa khách hàng”, NOT EXISTS thường là cách rõ và an toàn hơn.

### 6.4. Khi nào NOT IN dùng được?

Nếu cột trong subquery được đảm bảo NOT NULL bằng constraint hoặc có điều kiện lọc NULL:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
~~~

thì bẫy NULL từ tập con được loại bỏ. Tuy vậy, cần hiểu cả trường hợp giá trị phía ngoài là NULL: NULL NOT IN (...) không trở thành TRUE; nếu nghiệp vụ cần giữ khách hàng có ID NULL (thường khóa chính không cho phép), phải xử lý riêng.

## 7. Scalar subquery: truy vấn con trả về một giá trị

### 7.1. Scalar subquery trong SELECT

Một scalar subquery là subquery được dùng ở vị trí cần một giá trị đơn:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers c
ORDER BY c.customer_id;
~~~

Subquery tương quan với khách hàng bên ngoài và trả một số đếm cho mỗi khách hàng. Vì COUNT(*) không có GROUP BY, nó luôn trả đúng một dòng, kể cả khi không có đơn (giá trị 0).

### 7.2. Scalar subquery trả 0, 1 hoặc nhiều dòng

Quy tắc:

| Số dòng subquery trả về | Hành vi scalar |
| ---: | --- |
| 0 | Giá trị scalar là NULL |
| 1 | Giá trị của dòng đó |
| Nhiều hơn 1 | Lỗi ORA-01427: single-row subquery returns more than one row |

Ví dụ có thể lỗi:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT o.status
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS one_order_status
FROM customers c;
~~~

Nếu một khách hàng có nhiều đơn, subquery trả nhiều dòng và scalar context không biết phải chọn status nào. Không giải quyết bằng cách thêm FETCH FIRST 1 ROW ONLY tùy tiện; trước hết phải xác định nghiệp vụ muốn đơn nào (mới nhất, cũ nhất, ưu tiên trạng thái...) và viết ORDER BY phù hợp.

### 7.3. Scalar subquery với aggregate

Các aggregate không có GROUP BY thường trả đúng một dòng:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.created_at)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customers c;
~~~

Nếu không có đơn, MAX trả NULL. Đây là cách gọn khi chỉ cần một giá trị tổng hợp cho mỗi dòng ngoài.

### 7.4. Scalar subquery có thể thay JOIN nhưng phải xét số dòng

Một cách khác là tổng hợp bảng orders trước rồi LEFT JOIN:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(s.order_count, 0) AS order_count,
    s.latest_order_at
FROM customers c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        MAX(created_at) AS latest_order_at
    FROM orders
    GROUP BY customer_id
) s
    ON s.customer_id = c.customer_id;
~~~

So với scalar COUNT:

- Scalar subquery diễn đạt “tính một giá trị cho từng khách hàng”.
- Inline view tạo tập tổng hợp một dòng cho mỗi customer_id rồi kết hợp bằng LEFT JOIN.
- Cả hai có thể cho cùng kết quả khi khóa và điều kiện tương ứng.
- Oracle có thể biến đổi/đánh giá hai hình thức khác nhau tùy query, thống kê và phiên bản.

Không có quy tắc rằng scalar subquery luôn chậm hoặc JOIN luôn nhanh.

## 8. Correlated và uncorrelated subquery

### 8.1. Correlated subquery

Subquery tương quan tham chiếu cột từ query block bên ngoài:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Điều kiện o.customer_id = c.customer_id tham chiếu alias c bên ngoài, nên subquery là correlated.

### 8.2. Uncorrelated subquery

Subquery không tham chiếu dòng ngoài:

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_id IN (
    SELECT customer_id
    FROM orders
    WHERE status = 'PAID'
);
~~~

Subquery chỉ dựa trên bảng orders và điều kiện PAID. Về mặt logic, nó tạo tập customer_id của các đơn PAID rồi query ngoài kiểm tra membership.

### 8.3. Correlated không có nghĩa chắc chắn chạy tuần tự một lần cho mỗi dòng

Cách mô tả logic là subquery được đánh giá trong ngữ cảnh của dòng ngoài. Nhưng Oracle optimizer có thể **unnest** subquery, biến đổi nó thành semi-join, anti-join hoặc một dạng kế hoạch khác. Vì thế không nên nhìn chữ correlated rồi kết luận database chắc chắn thực thi hàng ngoài × subquery theo cách lặp ngây thơ.

Ngược lại, cũng không giả định mọi subquery đều được unnest. Cấu trúc truy vấn, aggregate, DISTINCT, ROWNUM/FETCH, analytic function, phép set, hint, phiên bản và điều kiện khác có thể hạn chế biến đổi. Cần xem execution plan thực tế.

## 9. Semi-join và anti-join: cách optimizer có thể thực hiện EXISTS/IN

### 9.1. Semi-join

Khi truy vấn yêu cầu chỉ giữ dòng bên trái nếu tồn tại dòng bên phải:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Oracle có thể chọn một **semi-join**. Về ý nghĩa, semi-join chỉ cần xác định bên phải có ít nhất một đối tác; nó không cần trả tất cả các cặp dòng như inner join thông thường. Điều này phù hợp với semantics của EXISTS/IN.

### 9.2. Anti-join

Với NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

Oracle có thể dùng **anti-join** để giữ các dòng bên trái không tìm thấy đối tác bên phải.

### 9.3. Các phương pháp join có thể xuất hiện trong plan

Ngay cả khi SQL viết bằng EXISTS, plan vẫn có thể chứa hoạt động join:

| Operation thường thấy | Ý tưởng |
| --- | --- |
| NESTED LOOPS SEMI | Với mỗi dòng phía ngoài, tìm đối tác phù hợp; khi tìm thấy có thể dừng kiểm tra tồn tại |
| HASH JOIN SEMI | Dùng cấu trúc hash để kiểm tra membership giữa hai tập |
| MERGE JOIN SEMI | Ghép hai tập đã được sắp xếp theo khóa phù hợp |
| HASH JOIN ANTI | Giữ dòng ngoài không có đối tác theo hash anti-join |
| NESTED LOOPS ANTI | Tìm và loại dòng ngoài nếu tồn tại đối tác |

Tên operation cụ thể phụ thuộc Oracle version và plan. Điểm quan trọng: **cú pháp EXISTS không bắt buộc Oracle phải chạy một vòng lặp subquery vật lý**. Optimizer có thể chọn phương pháp khác để bảo toàn kết quả.

## 10. JOIN, EXISTS, IN và scalar subquery: chọn theo kết quả cần có

### 10.1. Bảng quyết định

| Nếu cần... | Ưu tiên cân nhắc | Lý do |
| --- | --- | --- |
| Cột từ cả hai bảng và mọi cặp khớp | JOIN | Kết quả là các cặp dòng |
| Dòng ngoài nếu có ít nhất một dòng phù hợp | EXISTS | Không nhân dòng ngoài theo số đối tác |
| Dòng ngoài nếu không có dòng phù hợp | NOT EXISTS | Diễn đạt anti-join, tránh bẫy NULL của NOT IN |
| Kiểm tra giá trị thuộc một tập | IN (subquery) | Membership theo giá trị |
| Một giá trị đơn cho mỗi dòng ngoài | Scalar subquery | Phù hợp aggregate hoặc quan hệ bảo đảm một dòng |
| Một dòng tổng hợp cho mỗi khóa rồi kết hợp dữ liệu | Inline view/CTE + JOIN | Tách bước tổng hợp và bước trình bày |
| Top/latest row theo quy tắc thứ tự | Analytic ROW_NUMBER() hoặc subquery có thứ tự rõ | Chọn một hàng xác định |

### 10.2. Cùng một yêu cầu, nhiều cách viết

Yêu cầu: khách hàng có ít nhất một đơn PAID.

**Cách A — EXISTS:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = :status
);
~~~

**Cách B — JOIN DISTINCT:**

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = :status;
~~~

**Cách C — IN:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = :status
);
~~~

Trong mô hình khóa chính customer_id không NULL, cả ba cách có thể cho cùng tập khách hàng. Nhưng:

- Cách A diễn đạt trực tiếp kiểm tra tồn tại.
- Cách B tạo các cặp khách hàng/đơn trước, rồi cần DISTINCT để bỏ lặp.
- Cách C diễn đạt membership trong tập customer_id.

Oracle có thể biến đổi C và A thành plan semi-join tương tự. B có thể được tối ưu khác; DISTINCT có thể yêu cầu hash/sort unique hoặc được optimizer loại bỏ khi chứng minh không cần. Hãy xem plan thay vì đoán từ số dòng SQL.

### 10.3. Khi nào JOIN và EXISTS không tương đương?

Nếu bỏ DISTINCT:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
~~~

khách hàng có nhiều đơn PAID xuất hiện nhiều lần. Trong khi EXISTS trả mỗi dòng khách hàng tối đa một lần. Đây là khác biệt **cardinality** chứ không phải khác biệt hiệu năng.

Nếu sau đó truy vấn có COUNT(*), SUM(...), FETCH FIRST, hoặc logic phân trang, sự khác biệt duplicate rows có thể làm kết quả sai nghiêm trọng.

## 11. Ví dụ tổng hợp: số đơn và đơn mới nhất của mỗi khách hàng

### 11.1. Tổng hợp trước rồi JOIN

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(s.order_count, 0) AS order_count,
    s.latest_order_at
FROM customers c
LEFT JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        MAX(created_at) AS latest_order_at
    FROM orders
    GROUP BY customer_id
) s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Inline view s tạo tối đa một dòng cho mỗi customer_id có đơn hàng. LEFT JOIN giữ khách hàng không có đơn; NVL hiển thị count 0. Đây là một mẫu rõ ràng khi cần nhiều chỉ số tổng hợp từ cùng bảng con.

### 11.2. Scalar subquery cho từng chỉ số

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT MAX(o.created_at)
        FROM orders o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customers c
ORDER BY c.customer_id;
~~~

Hai scalar subquery có thể diễn đạt đúng cùng dữ liệu. Nhưng chúng lặp lại điều kiện quan hệ và về mặt SQL có hai biểu thức subquery riêng. Optimizer có thể áp dụng transformation/caching phù hợp, nhưng không nên giả định nó luôn gom tất cả thành một lần đọc. Khi cần nhiều aggregate trên cùng tập con, inline view/CTE thường làm ý định rõ hơn.

### 11.3. Lấy toàn bộ đơn hàng mới nhất

MAX(created_at) chỉ trả ngày giờ lớn nhất, không tự trả ORDER_ID và các cột khác của đúng dòng có ngày đó. Nếu hai đơn cùng thời điểm lớn nhất, JOIN lại theo MAX có thể trả nhiều dòng.

Dùng analytic:

~~~sql
SELECT customer_id, order_id, created_at, amount
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        o.amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM orders o
)
WHERE rn = 1;
~~~

ORDER_ID được giả định duy nhất, làm tie-breaker nếu nhiều đơn cùng created_at. Nếu nghiệp vụ muốn trả **tất cả đơn đồng thời gian mới nhất**, dùng RANK() theo created_at và lọc rank = 1, không thêm order_id vào tiêu chí rank.

## 12. Oracle optimizer: SQL viết thế nào và chạy thế nào

SQL là ngôn ngữ khai báo: bạn mô tả **kết quả cần có**, còn Oracle optimizer chọn kế hoạch thực thi dựa trên thông tin có sẵn. Hai câu SQL khác cú pháp có thể được biến đổi về plan tương tự; hai câu trông gần giống nhau cũng có thể có plan khác khi predicate hoặc dữ liệu khác.

### 12.1. Các bước khái niệm

~~~text
SQL statement
     |
     v
PARSE / SEMANTIC CHECK
     |
     v
QUERY TRANSFORMATION
  - subquery unnesting
  - view merging
  - predicate pushing
  - other transformations
     |
     v
COST-BASED OPTIMIZATION
  - join order
  - join method
  - access path
     |
     v
EXECUTION PLAN
     |
     v
ROWS / BUFFERS / CPU / ELAPSED TIME
~~~

Đây là sơ đồ khái quát. Oracle có nhiều pha tối ưu hóa và các biến đổi có điều kiện; không phải mọi câu SQL đều đi qua đúng cùng một chuỗi thao tác hoặc đều áp dụng tất cả transformation.

### 12.2. Subquery unnesting

Một subquery tương quan như:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

có thể được optimizer unnest thành semi-join. Điều đó cho phép optimizer cân nhắc join order, join method và access path trên các bảng liên quan như những phần của một query block rộng hơn.

Không phải mọi subquery đều được unnest. Một số cấu trúc hoặc semantics có thể ngăn cản/giới hạn transformation; ví dụ aggregate, ROWNUM, row limiting, analytic hoặc các yếu tố khác cần được đánh giá theo trường hợp và phiên bản. Không viết lại SQL chỉ để ép unnest khi chưa hiểu plan và kết quả.

### 12.3. Join method

Oracle thường chọn một trong các phương pháp sau, tùy dữ liệu và access path:

| Join method | Cách hoạt động khái quát | Trường hợp thường có lợi |
| --- | --- | --- |
| Nested loops | Lấy một dòng/tập nhỏ phía ngoài rồi tìm dòng khớp ở phía trong | Tập ngoài nhỏ, phía trong có index/selective access |
| Hash join | Xây hash structure từ một tập rồi dò tập còn lại | Join tập lớn, điều kiện equality, bộ nhớ phù hợp |
| Sort merge join | Sắp xếp hai tập theo khóa rồi merge | Dữ liệu đã có thứ tự hoặc chi phí sort/merge phù hợp |

Không có join method nào luôn nhanh nhất. Nested loops có thể rất tốt với vài khách hàng và index ORDERS(CUSTOMER_ID); có thể rất tốn kém nếu phía ngoài có hàng triệu dòng và mỗi dòng gây truy cập lặp. Hash join có thể hiệu quả với tập lớn nhưng cần tài nguyên và có thể spill ra TEMP nếu thiếu memory. Sort merge cũng phụ thuộc chi phí sort và đặc điểm dữ liệu.

### 12.4. Semi/anti join là ngữ nghĩa, join method là cách thực hiện

Đừng nhầm:

- **Semi-join/anti-join** mô tả kiểu quan hệ kết quả: có đối tác/không có đối tác.
- **Nested loops/hash/merge** mô tả thuật toán thực hiện join.

Ví dụ HASH JOIN SEMI vừa là semi-join về semantics, vừa dùng hash join làm phương pháp vật lý. NESTED LOOPS SEMI cũng là semi-join nhưng dùng nested loops.

## 13. Đọc execution plan để quyết định

### 13.1. EXPLAIN PLAN: kế hoạch ước lượng

Có thể xem kế hoạch dự kiến:

~~~sql
EXPLAIN PLAN FOR
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN lưu kế hoạch được tạo cho câu lệnh vào plan table (thường là PLAN_TABLE) và DBMS_XPLAN.DISPLAY hiển thị. Nó hữu ích để hiểu optimizer dự định làm gì, nhưng không phải bằng chứng về số hàng và thời gian thực tế của một lần chạy cụ thể.

### 13.2. Thu thập thống kê thực thi

Để xem runtime statistics cho một lần chạy trong session:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Hint GATHER_PLAN_STATISTICS yêu cầu thu thập thống kê thực thi cho câu lệnh. DISPLAY_CURSOR đọc cursor trong shared SQL area; quyền xem cursor/plan có thể cần quyền phù hợp. Nếu truy vấn không còn cursor hoặc session khác, NULL cho SQL ID/child number có thể không trỏ tới câu lệnh bạn định kiểm tra; hãy xác định SQL ID/cursor đúng khi cần.

### 13.3. Các cột quan trọng trong output

| Cột | Ý nghĩa | Cách đọc |
| --- | --- | --- |
| E-Rows | Số hàng optimizer ước lượng | So với số hàng thực tế để phát hiện sai cardinality |
| A-Rows | Số hàng thực tế ở operation, khi đã thu thập | Cho biết operation thực sự tạo/đưa ra bao nhiêu hàng |
| Starts | Số lần operation được khởi chạy | Giá trị cao có thể cho thấy operation bên trong nested loops chạy lặp |
| Buffers | Logical I/O/buffer gets | Hữu ích để so khối lượng truy cập buffer |
| A-Time | Thời gian thực thi được ghi nhận ở operation | Có thể bị ảnh hưởng bởi cách đo và quan hệ cha/con; không cộng đơn giản mọi dòng |
| Predicate Information | Điều kiện access/filter | Xem predicate được dùng ở đâu |
| Operation | Loại thao tác plan | Ví dụ TABLE ACCESS, INDEX RANGE SCAN, HASH JOIN SEMI |

E-Rows và A-Rows là dữ liệu quan trọng khi đánh giá plan. Nếu optimizer ước lượng 10 hàng nhưng thực tế là 500.000, join order/method có thể không phù hợp vì thống kê hoặc selectivity estimate không chính xác.

### 13.4. Starts cao không tự chứng minh truy vấn sai

Trong nested loops, operation phía trong có thể được khởi chạy nhiều lần, nên Starts cao là điều có thể dự kiến. Hãy xem nó có gây nhiều buffer gets/elapsed time không, và số hàng mỗi lần ra sao. Với semi-join, engine có thể dừng sau khi tìm thấy một đối tác phù hợp; nhưng cách thực thi cụ thể cần đọc plan.

### 13.5. Cost không phải thời gian chạy

COST là ước lượng nội bộ của optimizer dùng để so sánh phương án, không phải mili giây hay số giây. Một plan cost thấp hơn không tự động có nghĩa response time thực tế thấp hơn trong mọi điều kiện. Cần đo với dữ liệu đại diện, cùng bind values, cùng môi trường và quan sát runtime metrics.

## 14. So sánh công bằng hai cách viết

Muốn biết EXISTS hay JOIN phù hợp hơn cho một truy vấn cụ thể, làm theo quy trình:

1. Viết cả hai câu SQL sao cho **ngữ nghĩa và tập kết quả giống hệt nhau**.
2. Dùng cùng predicate, cùng bind values, cùng projection và cùng yêu cầu sort.
3. Kiểm tra duplicate rows và NULL để bảo đảm không so hai truy vấn khác ý nghĩa.
4. Chạy với dữ liệu có phân bố gần production, không chỉ bảng vài dòng.
5. Thu thập actual plan/runtime statistics.
6. So A-Rows, Starts, Buffers, elapsed time và lượng TEMP/PGA nếu có.
7. Lặp lại đủ lần để giảm ảnh hưởng parse, cache và tải hệ thống; không lấy một lần chạy đơn lẻ làm kết luận chung.

### 14.1. Ví dụ hai truy vấn cùng ý nghĩa

**EXISTS:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = :status
);
~~~

**IN:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.status = :status
);
~~~

Với CUSTOMERS.CUSTOMER_ID là primary key NOT NULL, và subquery trả các customer_id liên quan theo cùng điều kiện, hai câu có cùng membership semantics. Hãy xem Oracle có tạo semi-join tương tự hay không; không đoán rằng một cách chắc chắn nhanh hơn.

### 14.2. Đừng so JOIN chưa loại trùng với EXISTS

Hai câu dưới đây **không nhất thiết cùng số dòng**:

~~~sql
-- Moi cap customer/order:
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';

-- Moi customer co it nhat mot order PAID:
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Nếu có nhiều đơn PAID, câu JOIN lặp khách hàng còn EXISTS không. Không được tuyên bố một câu nhanh hơn khi chúng đang giải quyết hai yêu cầu khác nhau.

### 14.3. Không thêm DISTINCT một cách vô thức

DISTINCT có thể yêu cầu sort/hash unique, tiêu tốn bộ nhớ hoặc TEMP. Nhưng nếu output thực sự cần loại trùng, đó là công việc nghiệp vụ phải làm. Không bỏ DISTINCT chỉ để plan đẹp hơn nếu kết quả sẽ sai; thay vào đó, chọn EXISTS khi yêu cầu thực sự chỉ là membership.

## 15. Index, thống kê và cardinality

### 15.1. Index có thể giúp cả JOIN lẫn subquery

Ví dụ:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Một index trên ORDERS(CUSTOMER_ID, STATUS) hoặc ORDERS(STATUS, CUSTOMER_ID) có thể hữu ích tùy selectivity, join order, cách truy cập và workload. Không có thứ tự cột index đúng cho mọi truy vấn. Nếu filter status rất chọn lọc, thứ tự index có thể khác trường hợp customer_id được dò theo từng khách hàng.

### 15.2. Không phải cứ có index là nhanh

- Nếu phần lớn bảng thỏa predicate, full table scan và hash join có thể rẻ hơn rất nhiều index lookups.
- Nếu bảng ngoài rất nhỏ và index bảng trong phù hợp, nested loops có thể tốt.
- Nếu cần nhiều cột không nằm trong index, truy cập table row qua ROWID có thể tăng I/O.
- Index tăng chi phí ghi và chiếm storage.
- Clustering factor và phân bố dữ liệu ảnh hưởng hiệu quả truy cập.

### 15.3. Thống kê optimizer

Optimizer dựa vào table/index statistics, histogram, column correlation và thông tin khác để ước lượng số hàng. Nếu dữ liệu thay đổi nhiều hoặc thống kê lỗi thời, E-Rows có thể khác xa A-Rows.

Không tự chạy DBMS_STATS trên schema production nếu không có quyền và kế hoạch DBA. Việc thu thập statistics có thể ảnh hưởng plan của nhiều câu SQL; hãy theo quy trình quản trị.

### 15.4. Bind variables và phân bố dữ liệu

Một query có bind :status có thể chạy với PAID (nhiều hàng) hoặc RARE_STATUS (rất ít hàng). Một plan duy nhất không phải lúc nào cũng tối ưu cho mọi giá trị. Oracle có các cơ chế như bind peeking và adaptive cursor sharing tùy điều kiện/version, nhưng không nên dựa vào giả định rằng mọi bind đều được tối ưu hoàn hảo.

Khi benchmark, thử các giá trị đại diện cho selectivity khác nhau và xem child cursor/plan phù hợp. Không thay bind bằng literal hàng loạt chỉ để ép mỗi giá trị có một plan nếu chưa đánh giá tác động cursor sharing.

## 16. Những mẫu truy vấn cần cân nhắc

### 16.1. Chỉ cần biết có ít nhất một dòng

Ưu tiên EXISTS:

~~~sql
SELECT p.product_id, p.product_name
FROM products p
WHERE EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.product_id = p.product_id
);
~~~

### 16.2. Cần lấy cột từ bảng con

Dùng JOIN:

~~~sql
SELECT p.product_id, p.product_name, i.order_id, i.quantity
FROM products p
JOIN order_items i
    ON i.product_id = p.product_id;
~~~

### 16.3. Cần biết không có dòng phù hợp

Ưu tiên NOT EXISTS:

~~~sql
SELECT p.product_id, p.product_name
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.product_id = p.product_id
);
~~~

### 16.4. Cần giá trị tổng hợp cho mỗi dòng ngoài

Scalar aggregate:

~~~sql
SELECT p.product_id,
       (SELECT SUM(i.quantity)
        FROM order_items i
        WHERE i.product_id = p.product_id) AS units_ordered
FROM products p;
~~~

Hoặc aggregate inline view + LEFT JOIN nếu cần nhiều chỉ số:

~~~sql
SELECT p.product_id,
       NVL(s.units_ordered, 0) AS units_ordered,
       NVL(s.order_line_count, 0) AS order_line_count
FROM products p
LEFT JOIN (
    SELECT product_id,
           SUM(quantity) AS units_ordered,
           COUNT(*) AS order_line_count
    FROM order_items
    GROUP BY product_id
) s
    ON s.product_id = p.product_id;
~~~

### 16.5. Cần kiểm tra một điều kiện trên nhiều cột

EXISTS có thể chứa nhiều điều kiện:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    JOIN order_items i
        ON i.order_id = o.order_id
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
      AND i.product_id = :product_id
);
~~~

Truy vấn trả khách hàng có ít nhất một đơn PAID chứa sản phẩm được chỉ định. Bảng order_items có thể có nhiều dòng phù hợp, nhưng EXISTS vẫn chỉ kiểm tra sự tồn tại cho mỗi khách hàng.

### 16.6. Cần một hàng con theo thứ tự

Dùng analytic ranking:

~~~sql
SELECT customer_id, order_id, created_at
FROM (
    SELECT o.customer_id,
           o.order_id,
           o.created_at,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.created_at DESC, o.order_id DESC
           ) AS rn
    FROM orders o
)
WHERE rn = 1;
~~~

Không dùng scalar subquery trả order_id mà không giới hạn về một hàng hoặc không có aggregate. Một khách hàng có nhiều đơn thì scalar subquery sẽ lỗi.

## 17. Bài thực hành tổng hợp

Phần lab tạo bảng khách hàng và đơn hàng có chủ đích chứa các trường hợp: khách hàng nhiều đơn PAID, khách hàng chỉ có đơn PENDING, khách hàng không có đơn và một dòng đơn hàng có CUSTOMER_ID NULL để minh họa NOT IN.

Chỉ chạy trong schema lab bạn sở hữu. Nếu tên bảng đã tồn tại, chọn tên khác; không xóa bảng có sẵn không rõ nguồn gốc.

### Bước 1 — Tạo bảng

~~~sql
CREATE TABLE join_subquery_customer_lab (
    customer_id NUMBER PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR) NOT NULL
);

CREATE TABLE join_subquery_order_lab (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    status VARCHAR2(12 CHAR) NOT NULL,
    amount NUMBER(10,2) NOT NULL,
    created_at DATE NOT NULL,
    CONSTRAINT fk_js_order_customer_lab
        FOREIGN KEY (customer_id)
        REFERENCES join_subquery_customer_lab(customer_id)
);
~~~

CUSTOMER_ID ở bảng đơn cho phép NULL để minh họa dữ liệu liên kết thiếu. Foreign key vẫn hợp lệ vì NULL không phải một giá trị khóa cần tham chiếu.

### Bước 2 — Thêm khách hàng

~~~sql
INSERT INTO join_subquery_customer_lab VALUES (1, 'An');
INSERT INTO join_subquery_customer_lab VALUES (2, 'Binh');
INSERT INTO join_subquery_customer_lab VALUES (3, 'Chi');
INSERT INTO join_subquery_customer_lab VALUES (4, 'Dung');

COMMIT;
~~~

### Bước 3 — Thêm đơn hàng

~~~sql
INSERT INTO join_subquery_order_lab
VALUES (101, 1, 'PAID', 100, DATE '2026-11-01');

INSERT INTO join_subquery_order_lab
VALUES (102, 1, 'PAID', 200, DATE '2026-11-03');

INSERT INTO join_subquery_order_lab
VALUES (103, 2, 'PENDING', 80, DATE '2026-11-04');

INSERT INTO join_subquery_order_lab
VALUES (104, 3, 'PAID', 150, DATE '2026-11-05');

INSERT INTO join_subquery_order_lab
VALUES (105, NULL, 'PAID', 50, DATE '2026-11-06');

COMMIT;
~~~

Mô hình dữ liệu:

| Customer | Đơn hàng |
| --- | --- |
| An (1) | 101 PAID, 102 PAID |
| Binh (2) | 103 PENDING |
| Chi (3) | 104 PAID |
| Dung (4) | Không có |
| *(không có customer)* | 105 PAID với CUSTOMER_ID NULL |

### Bước 4 — JOIN: lấy từng cặp khách hàng/đơn hàng

~~~sql
SELECT c.customer_id, c.customer_name,
       o.order_id, o.status, o.amount
FROM join_subquery_customer_lab c
JOIN join_subquery_order_lab o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Kết quả có bốn dòng: An xuất hiện hai lần, Binh một lần, Chi một lần; Dung không xuất hiện.

### Bước 5 — EXISTS: khách hàng có ít nhất một đơn PAID

~~~sql
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE EXISTS (
    SELECT 1
    FROM join_subquery_order_lab o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả là An và Chi, mỗi người một dòng. An có hai đơn PAID nhưng không bị lặp.

### Bước 6 — JOIN DISTINCT và so sánh

~~~sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
JOIN join_subquery_order_lab o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
ORDER BY c.customer_id;
~~~

Kết quả phải có cùng hai khách hàng với Bước 5. Bỏ DISTINCT để quan sát An xuất hiện hai lần; giải thích vì sao hai truy vấn không còn cùng cardinality.

### Bước 7 — IN và NOT IN có NULL

~~~sql
-- IN: khach hang co ID nam trong tap ID cua don PAID.
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE c.customer_id IN (
    SELECT o.customer_id
    FROM join_subquery_order_lab o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;

-- NOT IN: quan sat anh huong cua NULL trong subquery.
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM join_subquery_order_lab o
    WHERE o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Truy vấn IN trả An và Chi. Subquery PAID còn có một giá trị NULL từ order 105; vì vậy NOT IN có thể không trả hàng nào do logic UNKNOWN.

### Bước 8 — NOT EXISTS: khách hàng không có đơn PAID

~~~sql
SELECT c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE NOT EXISTS (
    SELECT 1
    FROM join_subquery_order_lab o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Kết quả gồm Binh và Dung: Binh có đơn nhưng không có đơn PAID; Dung không có đơn nào. Dòng order có customer_id NULL không làm hỏng NOT EXISTS.

### Bước 9 — Scalar subquery đếm đơn

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM join_subquery_order_lab o
        WHERE o.customer_id = c.customer_id
    ) AS order_count,
    (
        SELECT MAX(o.created_at)
        FROM join_subquery_order_lab o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM join_subquery_customer_lab c
ORDER BY c.customer_id;
~~~

Kết quả có bốn dòng. Count của Dung là 0; MAX của Dung là NULL.

### Bước 10 — Aggregate inline view + LEFT JOIN

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    NVL(s.order_count, 0) AS order_count,
    s.total_amount
FROM join_subquery_customer_lab c
LEFT JOIN (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM join_subquery_order_lab
    GROUP BY customer_id
) s
    ON s.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả giữ cả Dung. Dòng order có customer_id NULL nằm trong nhóm NULL của inline view nhưng không ghép với khách hàng nào.

### Bước 11 — Quan sát execution plan

Chạy truy vấn EXISTS với thống kê:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id, c.customer_name
FROM join_subquery_customer_lab c
WHERE EXISTS (
    SELECT 1
    FROM join_subquery_order_lab o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Sau đó chạy câu IN tương ứng và xem plan của cursor đúng. Với bảng lab chỉ vài dòng, optimizer có thể chọn full scan hoặc một plan đơn giản; không kết luận cách viết nào nhanh hơn từ một bảng quá nhỏ.

### Bước 12 — Dọn bảng lab nếu không cần

~~~sql
-- Drop bang con truoc do co foreign key tham chieu bang cha.
DROP TABLE join_subquery_order_lab PURGE;
DROP TABLE join_subquery_customer_lab PURGE;
~~~

PURGE bỏ qua recycle bin. Chỉ chạy khi chắc chắn hai bảng là bảng lab do bạn tạo và không cần dữ liệu nữa.

## 18. Câu hỏi tự kiểm tra

1. Khi nào JOIN tạo nhiều dòng cho cùng một khách hàng?
2. Vì sao EXISTS không nhân bản dòng ngoài theo số đơn hàng phù hợp?
3. IN (subquery) trả lời câu hỏi logic nào?
4. Với khóa ngoài không NULL và cùng predicate, vì sao IN và EXISTS thường có cùng tập kết quả?
5. Tại sao NOT IN có thể trả rỗng nếu subquery có một NULL?
6. Vì sao NOT EXISTS thường an toàn hơn cho anti-join?
7. Một scalar subquery không có GROUP BY và dùng COUNT(*) trả bao nhiêu dòng khi không có bản ghi liên quan?
8. Scalar subquery trả nhiều hơn một dòng gây lỗi gì?
9. Tại sao MAX(created_at) không tự xác định toàn bộ dòng đơn hàng mới nhất?
10. Correlated subquery có chắc chắn được thực thi vật lý một lần cho mỗi dòng ngoài không?
11. Semi-join khác inner join ở mục tiêu kết quả nào?
12. Anti-join thường được optimizer sử dụng cho kiểu điều kiện nào?
13. Vì sao không thể kết luận EXISTS luôn nhanh hơn JOIN?
14. E-Rows và A-Rows trong DBMS_XPLAN biểu thị điều gì?
15. COST trong execution plan có phải thời gian mili giây không?
16. Vì sao phải so sánh hai câu SQL có cùng semantics trước khi benchmark?
17. Khi nào aggregate inline view + LEFT JOIN dễ quản lý hơn nhiều scalar subquery?
18. Tại sao index không phải lúc nào cũng tốt hơn full table scan?
19. Điều gì cần kiểm tra khi Starts của operation trong plan rất cao?
20. Vì sao không nên benchmark chỉ trên bảng lab vài dòng rồi áp kết luận cho production?

**Gợi ý trả lời:**

1. Khi một dòng khách hàng khớp nhiều dòng đơn hàng.
2. EXISTS chỉ đánh giá có/không có đối tác cho mỗi dòng ngoài; nó không chiếu các cặp.
3. Giá trị của dòng ngoài có thuộc tập kết quả subquery hay không.
4. Vì cùng kiểm tra membership; duplicate trong tập con không nhân bản dòng ngoài.
5. Phép so sánh với NULL tạo UNKNOWN; WHERE chỉ giữ TRUE.
6. NOT EXISTS kiểm tra không có dòng thỏa quan hệ mà không bị NULL trong tập con làm nhiễu theo cách NOT IN.
7. Một dòng, với COUNT(*) = 0.
8. ORA-01427.
9. MAX chỉ trả giá trị ngày giờ; có thể nhiều dòng cùng giá trị MAX và không có các cột khác của một dòng duy nhất.
10. Không; optimizer có thể unnest/biến đổi thành semi-join hoặc dạng khác.
11. Semi-join chỉ cần xác định có đối tác, không trả mọi cặp dòng phía phải.
12. NOT EXISTS/NOT IN tương ứng khi diễn đạt không tồn tại đối tác.
13. Optimizer, dữ liệu, thống kê, index và semantics quyết định plan/kết quả; không có quy tắc tốc độ cố định.
14. E-Rows là số hàng ước lượng; A-Rows là số hàng thực tế khi có runtime stats.
15. Không, cost là ước lượng nội bộ để optimizer so sánh phương án.
16. Nếu kết quả khác nhau, benchmark không so cùng một công việc.
17. Khi cần nhiều aggregate từ cùng bảng con và một dòng tổng hợp cho mỗi khóa.
18. Full scan có thể rẻ hơn khi predicate không chọn lọc hoặc phần lớn bảng cần đọc.
19. Số lần khởi chạy, buffers, rows mỗi lần, join method và thời gian operation.
20. Dữ liệu nhỏ không đại diện cardinality, selectivity, concurrency và I/O của production.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html): cú pháp JOIN và ngữ nghĩa các phép nối.
- [Oracle Database SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): điều kiện EXISTS và NOT EXISTS.
- [Oracle Database SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): phép kiểm tra membership và subquery.
- [Oracle Database SQL Language Reference — Scalar Subquery Expressions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Scalar-Subquery-Expressions.html): quy tắc subquery trả một giá trị, 0 dòng và nhiều dòng.
- [Oracle Database SQL Tuning Guide — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html): join order, join methods và tối ưu hóa phép nối.
- [Oracle Database SQL Tuning Guide — Query Transformations](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): subquery unnesting và các biến đổi query.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): hiển thị execution plan và runtime statistics.
