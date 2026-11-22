# Giới hạn cú pháp, chi phí sắp xếp và kiểm chứng kết quả

Window function giúp tính thứ hạng, tổng lũy kế, trung bình trượt và các giá trị ở hàng trước hoặc sau mà vẫn giữ từng hàng chi tiết. Tuy nhiên, truy vấn dùng hàm cửa sổ có những giới hạn cú pháp riêng và có thể phát sinh chi phí sắp xếp, lưu dữ liệu trung gian đáng kể.

Khi sử dụng window function trong MySQL, cần trả lời ba câu hỏi:

1. Hàm cửa sổ được phép xuất hiện ở vị trí nào trong câu SELECT và có những giới hạn nào?
2. MySQL phải phân vùng, sắp xếp và xử lý bao nhiêu hàng để tính cửa sổ?
3. Làm sao chứng minh kết quả đúng khi có dữ liệu trùng, NULL, ranh giới frame hoặc nhiều hàng cùng thứ tự?

Bài viết tập trung vào MySQL 8.0 trở lên. Khả năng cụ thể và cách optimizer lập kế hoạch có thể khác nhau giữa các bản phát hành; hãy kiểm tra đúng phiên bản đang triển khai.

## 1. Bảng dữ liệu dùng trong ví dụ

Các ví dụ dùng bảng đơn hàng sau:

~~~sql
CREATE TABLE sales_orders (
    order_id    BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at  DATETIME NOT NULL,
    status      VARCHAR(20) NOT NULL,
    total       DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_sales_customer (customer_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id      BIGINT UNSIGNED NOT NULL,
    product_id    BIGINT UNSIGNED NOT NULL,
    quantity      INT UNSIGNED NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_order (order_id),
    CONSTRAINT fk_order_items_sales_order
        FOREIGN KEY (order_id)
        REFERENCES sales_orders(order_id)
) ENGINE = InnoDB;

~~~

Nạp một tập dữ liệu nhỏ có hai khách hàng và một số đơn trùng thời điểm:

~~~sql
INSERT INTO sales_orders
    (order_id, customer_id, created_at, status, total)
VALUES
    (101, 1, '2026-01-01 09:00:00', 'PAID', 100.00),
    (102, 1, '2026-01-01 09:00:00', 'PAID',  50.00),
    (103, 1, '2026-01-02 10:00:00', 'PAID', 200.00),
    (201, 2, '2026-01-01 08:00:00', 'PAID',  80.00),
    (202, 2, '2026-01-03 11:00:00', 'PENDING', 120.00);

INSERT INTO order_items (order_id, product_id, quantity)
VALUES
    (101, 1, 1),
    (101, 2, 2),
    (102, 1, 1),
    (103, 3, 1),
    (201, 1, 2);
~~~

Đơn 101 và 102 có cùng customer_id và created_at. Đây là trường hợp quan trọng để kiểm tra thứ tự ổn định, peer rows và frame RANGE so với ROWS.

## 2. Window function nằm ở giai đoạn nào của SELECT?

Một cách hình dung thứ tự xử lý logic của SELECT:

~~~text
FROM / JOIN
     |
     v
WHERE
     |
     v
GROUP BY
     |
     v
HAVING
     |
     v
WINDOW FUNCTIONS
     |
     v
SELECT result
     |
     v
ORDER BY
     |
     v
LIMIT
~~~

Thứ tự này mô tả ngữ nghĩa truy vấn để xác định dữ liệu nào đi vào cửa sổ. Nó không phải lời khẳng định rằng MySQL luôn thực hiện vật lý từng bước theo đúng thứ tự; optimizer có thể biến đổi kế hoạch nếu kết quả vẫn đúng ngữ nghĩa SQL.

Hàm cửa sổ nhìn thấy tập hàng còn lại sau FROM, JOIN, WHERE, GROUP BY và HAVING. Sau đó nó tính giá trị cho từng hàng trong tập đó. Vì thế:

- WHERE lọc hàng trước khi window function tính toán.
- GROUP BY có thể làm thay đổi mức chi tiết của tập dữ liệu trước khi cửa sổ được tính.
- HAVING lọc các nhóm trước khi cửa sổ được tính trong cùng cấp truy vấn.
- ORDER BY cuối truy vấn sắp xếp kết quả trả về; ORDER BY bên trong OVER xác định thứ tự dùng để tính cửa sổ.
- LIMIT cuối truy vấn giới hạn kết quả sau khi window function đã được tính theo tập hàng của truy vấn.

## 3. Những vị trí không được dùng trực tiếp window function

Trong MySQL, window function được phép dùng trong danh sách SELECT và ORDER BY của truy vấn tương ứng. Không thể đặt trực tiếp hàm cửa sổ trong WHERE, GROUP BY hoặc HAVING của cùng cấp SELECT.

### 3.1. Không lọc trực tiếp bằng ROW_NUMBER trong WHERE

Ví dụ sau không hợp lệ:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_num
FROM sales_orders
WHERE row_num <= 2;
~~~

Có hai vấn đề: alias row_num chưa tồn tại ở giai đoạn WHERE, và window function không được phép xuất hiện trực tiếp trong WHERE của cùng cấp truy vấn.

Hãy tính giá trị cửa sổ ở truy vấn trong rồi lọc ở truy vấn ngoài:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        total,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS row_num
    FROM sales_orders
)
SELECT order_id, customer_id, created_at, total, row_num
FROM ranked_orders
WHERE row_num <= 2
ORDER BY customer_id, row_num;
~~~

Truy vấn trong tính row_num cho toàn bộ đơn đủ điều kiện. Truy vấn ngoài mới lọc hai hàng đầu tiên của từng khách hàng.

### 3.2. Không dùng window function trong GROUP BY hoặc HAVING cùng cấp

Không thể viết GROUP BY theo một biểu thức ROW_NUMBER() OVER (...), hoặc dùng trực tiếp điều kiện như HAVING RANK() OVER (...) <= 3.

Nếu cần nhóm hoặc lọc theo kết quả cửa sổ, hãy đặt phép tính cửa sổ trong CTE hoặc derived table rồi truy vấn lớp ngoài:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        total,
        DENSE_RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total DESC
        ) AS value_rank
    FROM sales_orders
)
SELECT customer_id, order_id, total, value_rank
FROM ranked
WHERE value_rank <= 3;
~~~

### 3.3. Không lồng trực tiếp window function trong window function khác

Không viết một window function làm đối số trực tiếp của một window function khác trong cùng biểu thức. Nếu phép tính thứ hai phụ thuộc kết quả cửa sổ thứ nhất, chia thành hai cấp truy vấn:

~~~sql
WITH first_pass AS (
    SELECT
        order_id,
        customer_id,
        total,
        SUM(total) OVER (
            PARTITION BY customer_id
        ) AS customer_total
    FROM sales_orders
)
SELECT
    order_id,
    customer_id,
    total,
    customer_total,
    RANK() OVER (
        ORDER BY customer_total DESC
    ) AS customer_rank
FROM first_pass;
~~~

CTE first_pass tạo cột customer_total. Cấp SELECT bên ngoài có thể dùng cột đó làm đầu vào cho RANK.

## 4. Các giới hạn cú pháp cần nhớ trong MySQL

### 4.1. DISTINCT không được hỗ trợ bên trong window aggregate

MySQL không hỗ trợ dạng COUNT(DISTINCT expression) OVER (...). Ví dụ sau không hợp lệ:

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT status) OVER (
        PARTITION BY customer_id
    ) AS distinct_status_count
FROM sales_orders;
~~~

Nếu cần đếm số trạng thái khác nhau theo khách hàng, có thể tính ở cấp GROUP BY:

~~~sql
SELECT
    customer_id,
    COUNT(DISTINCT status) AS distinct_status_count
FROM sales_orders
GROUP BY customer_id;
~~~

Nếu cần ghép kết quả đó trở lại từng hàng, tính riêng rồi JOIN:

~~~sql
WITH customer_status_counts AS (
    SELECT
        customer_id,
        COUNT(DISTINCT status) AS distinct_status_count
    FROM sales_orders
    GROUP BY customer_id
)
SELECT
    s.order_id,
    s.customer_id,
    s.status,
    c.distinct_status_count
FROM sales_orders AS s
JOIN customer_status_counts AS c
    ON c.customer_id = s.customer_id;
~~~

### 4.2. Frame có ROWS và RANGE

MySQL hỗ trợ hai đơn vị frame chính:

- ROWS xác định frame theo số hàng vật lý trước hoặc sau hàng hiện tại trong thứ tự cửa sổ.
- RANGE xác định frame theo giá trị của biểu thức ORDER BY và bao gồm các hàng peer có cùng giá trị sắp xếp ở ranh giới tương ứng.

Không nhầm hai đơn vị này. Khi hai đơn có cùng created_at, frame RANGE kết thúc tại CURRENT ROW có thể bao gồm cả hai đơn cùng thời điểm; frame ROWS có thể chỉ bao gồm các hàng đến vị trí hiện tại.

MySQL không hỗ trợ GROUPS frame. Khi thiết kế frame, hãy chọn ROWS hoặc RANGE theo đúng ý nghĩa nghiệp vụ.

### 4.3. Không phải mọi hàm đều dùng frame theo cùng cách

Các hàm tổng hợp dùng với OVER như SUM, AVG, COUNT, MIN và MAX có thể chịu ảnh hưởng của frame. FIRST_VALUE, LAST_VALUE và NTH_VALUE cũng làm việc với frame.

Các hàm như ROW_NUMBER, RANK, DENSE_RANK, LAG và LEAD có quy tắc riêng và không dùng frame theo cách các hàm tổng hợp sử dụng. Không nên thêm frame clause với giả định nó sẽ thay đổi mọi loại window function.

### 4.4. Không được bỏ qua thứ tự cần thiết

Một số hàm cần ORDER BY để có ý nghĩa ổn định. ROW_NUMBER không có ORDER BY vẫn có thể gán số thứ tự, nhưng thứ tự hàng không được xác định. Không dùng thứ tự đó làm quy tắc nghiệp vụ.

Nếu nhiều hàng có cùng giá trị sắp xếp, hãy thêm khóa duy nhất làm tie-breaker khi cần thứ tự xác định:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
)
~~~

Ở đây order_id là khóa chính nên phân biệt được các hàng có cùng created_at.

## 5. ORDER BY trong OVER khác ORDER BY cuối truy vấn

ORDER BY bên trong OVER xác định thứ tự để tính window function. Nó không đảm bảo kết quả được trả về theo thứ tự đó.

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_num
FROM sales_orders;
~~~

row_num được tính theo thứ tự created_at và order_id trong từng khách hàng, nhưng thứ tự các hàng trong kết quả cuối không được bảo đảm nếu không có ORDER BY ở cấp ngoài.

Nếu giao diện cần hiển thị theo khách hàng và thứ tự vừa đánh số, viết:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_num
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

Đừng dựa vào thứ tự vật lý của clustered index, thứ tự đọc index hoặc thứ tự xuất hiện trong một lần chạy trước đó.

## 6. Hiểu đúng PARTITION, ORDER và frame

Một window specification có thể gồm:

~~~sql
OVER (
    PARTITION BY expression_list
    ORDER BY expression_list
    frame_clause
)
~~~

- PARTITION BY chia tập đầu vào thành các nhóm độc lập. Hàm cửa sổ được tính riêng trong từng nhóm.
- ORDER BY xác định thứ tự các hàng trong mỗi partition cho các hàm cần thứ tự.
- Frame giới hạn phần hàng được dùng để tính các hàm có hỗ trợ frame.

Nếu không có PARTITION BY, toàn bộ tập đầu vào thuộc một partition. Nếu không có ORDER BY, các hàm thứ hạng hoặc vị trí không có thứ tự nghiệp vụ xác định.

### 6.1. Frame mặc định có thể tạo kết quả bất ngờ

Với aggregate window có ORDER BY nhưng không khai báo frame, frame mặc định trong MySQL là RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW. RANGE có thể bao gồm toàn bộ peer rows có cùng giá trị ORDER BY với hàng hiện tại.

Ví dụ:

~~~sql
SELECT
    order_id,
    created_at,
    total,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at
    ) AS running_total
FROM sales_orders
WHERE customer_id = 1
ORDER BY created_at, order_id;
~~~

Hai đơn 101 và 102 cùng created_at là peer rows. Với frame RANGE mặc định, tổng lũy kế ở cả hai hàng có thể cùng là 150.00 vì frame chứa cả hai hàng cùng giá trị ORDER BY.

Nếu yêu cầu tính lần lượt từng hàng, hãy dùng ROWS và thêm tie-breaker:

~~~sql
SELECT
    order_id,
    created_at,
    total,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE customer_id = 1
ORDER BY created_at, order_id;
~~~

Kết quả mong đợi cho khách hàng 1:

| order_id | total | running_total |
|---:|---:|---:|
| 101 | 100.00 | 100.00 |
| 102 | 50.00 | 150.00 |
| 103 | 200.00 | 350.00 |

Đây là khác biệt về ngữ nghĩa frame, không phải lỗi tính toán của MySQL.

### 6.2. Frame trượt

Trung bình của ba đơn gần nhất theo thứ tự tạo:

~~~sql
SELECT
    customer_id,
    order_id,
    created_at,
    total,
    AVG(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

Frame chứa tối đa ba hàng: hàng hiện tại và hai hàng trước trong cùng partition. Ở đầu partition, frame chỉ chứa số hàng hiện có; nó không tự tạo thêm hàng giả để đủ ba phần tử.

### 6.3. LAST_VALUE và frame

LAST_VALUE trả giá trị ở hàng cuối của frame hiện tại, không mặc nhiên là hàng cuối của toàn partition.

Ví dụ sau có thể trả về giá trị của hàng hiện tại:

~~~sql
SELECT
    customer_id,
    order_id,
    total,
    LAST_VALUE(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS last_value_in_frame
FROM sales_orders;
~~~

Nếu mục tiêu là lấy giá trị ở hàng cuối của toàn partition theo thứ tự đã chọn, khai báo frame đầy đủ:

~~~sql
SELECT
    customer_id,
    order_id,
    total,
    LAST_VALUE(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_order_total
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

Frame toàn partition cho phép LAST_VALUE nhìn đến hàng cuối cùng, dù hàng hiện tại đang ở đầu partition.

## 7. Chi phí sắp xếp và phân vùng

Window function không chỉ là một phép tính trên từng hàng. Để tính đúng, MySQL có thể phải:

1. Đọc tập hàng đầu vào sau các điều kiện lọc và phép nối.
2. Phân chia hàng theo PARTITION BY.
3. Sắp xếp hàng theo ORDER BY của cửa sổ.
4. Duy trì trạng thái hoặc vùng hàng trung gian để tính frame.
5. Trả kết quả theo thứ tự mà truy vấn cuối cùng yêu cầu.

Sắp xếp là một nguồn chi phí đáng chú ý. Nếu tập đầu vào lớn, có nhiều partition hoặc hàng có kích thước lớn, việc sort và lưu dữ liệu trung gian có thể tiêu tốn CPU, bộ nhớ và I/O.

### 7.1. Kích thước đầu vào ảnh hưởng trực tiếp đến chi phí

So sánh:

~~~sql
SELECT
    order_id,
    customer_id,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders;
~~~

với truy vấn có bộ lọc:

~~~sql
SELECT
    order_id,
    customer_id,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

Truy vấn thứ hai tính cửa sổ trên tập đơn đã lọc. Tuy nhiên, điều này cũng thay đổi ý nghĩa: tổng lũy kế chỉ tính các đơn PAID trong tháng 1, không phải tất cả đơn của khách hàng trong lịch sử. Chỉ đẩy điều kiện xuống trước cửa sổ khi đó đúng với yêu cầu nghiệp vụ.

### 7.2. Số partition và độ lớn partition

PARTITION BY customer_id tạo một cửa sổ độc lập cho mỗi khách hàng. Nếu một khách hàng có hàng triệu đơn, partition của khách hàng đó vẫn rất lớn dù số partition tổng thể nhiều.

Độ lớn partition quan trọng vì các hàng trong partition cần được sắp xếp theo thứ tự cửa sổ. Một số ít partition cực lớn có thể tạo ra chi phí và độ trễ đáng kể.

Hãy kiểm tra phân bố dữ liệu:

~~~sql
SELECT customer_id, COUNT(*) AS order_count
FROM sales_orders
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 20;
~~~

Truy vấn này giúp nhận diện các partition lớn nhất. Nếu workload có khách hàng đặc biệt lớn, hãy đo riêng trường hợp đó thay vì chỉ benchmark với khách hàng trung bình.

### 7.3. Nhiều window specification có thể cần nhiều lần sort

Hai cửa sổ có thứ tự khác nhau có thể yêu cầu các thứ tự sắp xếp khác nhau:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS chronological_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC
    ) AS amount_rank
FROM sales_orders;
~~~

Cửa sổ đầu sắp xếp theo created_at, order_id; cửa sổ thứ hai theo total DESC. MySQL có thể cần xử lý các yêu cầu thứ tự khác nhau và phát sinh thêm công việc sort.

Nếu nhiều hàm dùng cùng một window specification, khai báo named window giúp thể hiện chúng dùng chung định nghĩa:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total,
    ROW_NUMBER() OVER w AS row_no,
    SUM(total) OVER w AS running_total,
    AVG(total) OVER w AS running_average
FROM sales_orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY created_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

Named window giúp tránh lặp định nghĩa và giảm nguy cơ các hàm vô tình dùng thứ tự hoặc frame khác nhau. Việc optimizer có chia sẻ sort hay cấu trúc trung gian trong kế hoạch cụ thể cần được xác nhận bằng EXPLAIN; không mặc định mọi cửa sổ đều được hợp nhất.

### 7.4. Sắp xếp cuối truy vấn có thể là một công việc riêng

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_no
FROM sales_orders
ORDER BY total DESC;
~~~

Window yêu cầu thứ tự theo customer_id, created_at, order_id; kết quả cuối yêu cầu sắp xếp theo total DESC. Hai yêu cầu khác nhau nên MySQL có thể cần thêm một bước sắp xếp cuối.

Nếu kết quả cuối cần cùng thứ tự với cửa sổ, khai báo ORDER BY ngoài tương ứng. Dù vậy, vẫn phải đọc kế hoạch thực thi để biết server có tái sử dụng thứ tự hay cần sort thêm.

## 8. Index có thể giúp gì cho window function?

Một index phù hợp với cột lọc, phân vùng và thứ tự cửa sổ có thể giúp giảm lượng dữ liệu đọc hoặc cung cấp thứ tự hữu ích cho một số kế hoạch.

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE customer_id = 1;
~~~

Index:

~~~sql
CREATE INDEX idx_sales_customer_time
ON sales_orders (customer_id, created_at, order_id);
~~~

có thứ tự cột phù hợp với việc lọc customer_id và đọc các đơn theo created_at, order_id. Đây là cấu trúc đáng thử cho truy vấn này.

Tuy nhiên, không có bảo đảm rằng index sẽ loại bỏ toàn bộ sort hoặc mọi chi phí của window function. Khả năng tận dụng index phụ thuộc điều kiện lọc, thứ tự cột, hướng sắp xếp, các cột được chọn, số partition và phiên bản optimizer.

Nguyên tắc thiết kế:

- Xem xét các cột lọc bằng trước.
- Sau đó xem xét cột PARTITION BY.
- Tiếp theo là các cột ORDER BY theo đúng thứ tự.
- Chọn thêm cột phủ (covering) chỉ khi lợi ích đọc dữ liệu bù được kích thước index.
- Đo kế hoạch trước và sau khi thêm index.

Không tạo index riêng cho mọi window. Index làm tăng dung lượng và chi phí ghi, đồng thời có thể không giúp ích nếu truy vấn phải sắp xếp theo biểu thức hoặc thứ tự khác.

## 9. Giảm lượng dữ liệu và độ rộng hàng trước khi tính cửa sổ

Nếu chỉ cần một số cột, tránh đưa nhiều cột lớn không cần thiết qua các bước trung gian:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders;
~~~

Chỉ chọn các cột cần cho đầu ra và tính cửa sổ. Nếu bảng có JSON hoặc cột văn bản lớn, đừng chọn chúng vào truy vấn nếu không cần.

Có thể dùng CTE hoặc derived table để lọc và chiếu các cột trước cửa sổ, nhưng phải giữ đúng tập hàng và ngữ nghĩa. CTE không chứa window function có thể được optimizer merge hoặc materialize tùy cấu trúc và phiên bản. Derived table hoặc CTE có chứa window function trong MySQL phải được materialize; điều này có thể cần bộ nhớ hoặc dung lượng tạm.

Nếu cần cửa sổ trên toàn lịch sử rồi mới hiển thị một khoảng nhỏ, lọc ở truy vấn ngoài:

~~~sql
WITH numbered AS (
    SELECT
        order_id,
        customer_id,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
        ) AS row_no
    FROM sales_orders
)
SELECT order_id, customer_id, created_at, row_no
FROM numbered
WHERE row_no BETWEEN 10 AND 20;
~~~

Nếu đưa điều kiện giới hạn dữ liệu vào CTE, row_no sẽ được đánh lại trên tập nhỏ hơn và kết quả có thể khác. Hãy phân biệt lọc trước cửa sổ với lọc sau cửa sổ.

## 10. Đọc kế hoạch bằng EXPLAIN

Bắt đầu với EXPLAIN:

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID';
~~~

Tùy phiên bản và định dạng EXPLAIN, thông tin về windowing, sort, temporary table, access path và số hàng ước lượng được thể hiện ở mức chi tiết khác nhau. Có thể dùng:

~~~sql
EXPLAIN FORMAT=JSON
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID';
~~~

Và trên phiên bản hỗ trợ:

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    created_at,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
WHERE status = 'PAID';
~~~

EXPLAIN ANALYZE thực sự chạy câu SELECT và báo số liệu thực tế của các iterator. Tính năng này có trong MySQL 8.0.18 trở lên. Chỉ chạy trên môi trường phù hợp với khối lượng truy vấn đã được đánh giá.

Khi đọc kế hoạch, chú ý:

1. Access path của bảng nguồn và index được chọn.
2. Số hàng ước lượng so với số hàng thực tế.
3. Bước sort phục vụ PARTITION BY và ORDER BY.
4. Bước sort cuối truy vấn nếu ORDER BY ngoài khác thứ tự cửa sổ.
5. Temporary table hoặc materialization nếu xuất hiện.
6. Số vòng lặp và thời gian của iterator trong EXPLAIN ANALYZE.

Không suy luận chi phí chỉ từ việc truy vấn có chữ OVER. Một window trên vài trăm hàng có thể rất nhẹ; một window trên hàng chục triệu hàng với nhiều thứ tự khác nhau có thể rất tốn kém.

## 11. Kiểm chứng tính đúng đắn bằng dữ liệu nhỏ

Trước khi benchmark dữ liệu lớn, hãy tạo tập dữ liệu nhỏ mà có thể tính kết quả bằng tay. Tập dữ liệu nên có:

- Hai partition trở lên.
- Hai hàng trùng giá trị ORDER BY.
- Một partition chỉ có một hàng.
- Giá trị bằng nhau để kiểm tra RANK và DENSE_RANK.
- NULL nếu cột nghiệp vụ cho phép NULL.
- Hàng ở đầu và cuối frame.

Với dữ liệu đã nạp ở phần đầu, kiểm tra tổng lũy kế:

~~~sql
SELECT
    order_id,
    customer_id,
    created_at,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
    ) AS row_no,
    SUM(total) OVER (
        PARTITION BY customer_id
        ORDER BY created_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM sales_orders
ORDER BY customer_id, created_at, order_id;
~~~

Kết quả mong đợi:

| order_id | customer_id | row_no | running_total |
|---:|---:|---:|---:|
| 101 | 1 | 1 | 100.00 |
| 102 | 1 | 2 | 150.00 |
| 103 | 1 | 3 | 350.00 |
| 201 | 2 | 1 | 80.00 |
| 202 | 2 | 2 | 200.00 |

Nếu thứ tự cửa sổ bỏ order_id khỏi ORDER BY, hai hàng 101 và 102 có cùng created_at và không có thứ tự xác định giữa chúng. Tổng lũy kế theo ROWS khi đó có thể được gán cho hai hàng theo thứ tự không ổn định.

## 12. Kiểm chứng thứ hạng và trường hợp đồng hạng

ROW_NUMBER, RANK và DENSE_RANK có ngữ nghĩa khác nhau khi nhiều hàng có cùng giá trị sắp xếp.

~~~sql
SELECT
    order_id,
    customer_id,
    total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC, order_id
    ) AS row_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC
    ) AS rank_no,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC
    ) AS dense_rank_no
FROM sales_orders
ORDER BY customer_id, total DESC, order_id;
~~~

- ROW_NUMBER cấp số khác nhau cho từng hàng; order_id tạo thứ tự xác định khi total bằng nhau.
- RANK cho các hàng đồng hạng cùng thứ hạng và để lại khoảng trống ở thứ hạng tiếp theo.
- DENSE_RANK cho các hàng đồng hạng cùng thứ hạng nhưng không để lại khoảng trống.

Trong ví dụ, hai khách hàng có dữ liệu riêng. Nếu kiểm tra đồng hạng theo total, hãy cố ý tạo hai đơn cùng total để quan sát sự khác biệt. Không thêm khóa duy nhất vào ORDER BY của RANK nếu nghiệp vụ muốn các giá trị total bằng nhau được xem là đồng hạng; thêm tie-breaker chỉ cho ROW_NUMBER hoặc cho thứ tự hiển thị khi phù hợp.

## 13. Kiểm chứng tổng lũy kế với tổng nhóm

Một phép kiểm tra hữu ích là so sánh tổng cuối partition với tổng thông thường của cùng tập hàng.

Tổng theo khách hàng:

~~~sql
SELECT customer_id, SUM(total) AS grouped_total
FROM sales_orders
GROUP BY customer_id;
~~~

Giá trị tổng lũy kế cuối cùng:

~~~sql
WITH running AS (
    SELECT
        customer_id,
        order_id,
        SUM(total) OVER (
            PARTITION BY customer_id
            ORDER BY created_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_total,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS reverse_row_no
    FROM sales_orders
)
SELECT customer_id, running_total AS window_total
FROM running
WHERE reverse_row_no = 1;
~~~

Hai kết quả phải khớp theo từng customer_id nếu cùng dùng toàn bộ hàng, cùng điều kiện lọc và total không NULL. Nếu khác nhau, kiểm tra:

- Điều kiện WHERE có giống nhau không?
- Có hàng bị nhân bản bởi JOIN trước cửa sổ không?
- Có hàng bị loại trước khi tính cửa sổ không?
- PARTITION BY có đúng khóa nhóm không?
- ORDER BY có tie-breaker ổn định không?
- Frame có bao phủ toàn bộ partition ở hàng cuối không?

Đây là cách kiểm tra độc lập giữa phép tổng hợp nhóm và window aggregate.

## 14. Kiểm chứng khi có JOIN trước window function

Một lỗi thường gặp là JOIN làm nhân bản hàng trước khi tính cửa sổ. Ví dụ, nếu một đơn có nhiều dòng chi tiết, JOIN orders với order_items tạo một hàng cho mỗi sản phẩm. SUM(o.total) OVER (...) khi đó có thể cộng total đơn hàng lặp lại theo số dòng chi tiết.

Ví dụ cần đếm số dòng sản phẩm của mỗi đơn và giữ thứ hạng đơn theo khách hàng:

~~~sql
WITH item_counts AS (
    SELECT
        order_id,
        COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
),
order_level AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.created_at,
        o.total,
        COALESCE(ic.item_count, 0) AS item_count
    FROM sales_orders AS o
    LEFT JOIN item_counts AS ic
        ON ic.order_id = o.order_id
)
SELECT
    order_id,
    customer_id,
    total,
    item_count,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY total DESC, order_id
    ) AS amount_position
FROM order_level;
~~~

CTE item_counts tổng hợp chi tiết về một hàng cho mỗi order_id trước khi JOIN với cấp đơn hàng. Cấp order_level vì vậy vẫn có một hàng cho mỗi đơn; window function không vô tình tính lặp tổng tiền đơn.

Khi kiểm chứng, hãy xác nhận cấp hạt (grain) của dữ liệu đầu vào cửa sổ: một hàng đại diện cho đơn hàng, dòng chi tiết hay một tổ hợp JOIN? Đây là điều kiện quan trọng để SUM, COUNT và ROW_NUMBER mang đúng ý nghĩa.

## 15. Kiểm chứng kết quả sau khi thay đổi truy vấn

Khi tối ưu một truy vấn có window function, không chỉ so sánh thời gian. Cần xác nhận truy vấn mới trả cùng kết quả theo nghiệp vụ.

Một quy trình có thể áp dụng:

1. Lưu truy vấn và tập tham số ban đầu.
2. Ghi nhận số hàng kết quả và các khóa định danh.
3. Chạy truy vấn mới trên cùng snapshot hoặc cùng dữ liệu ổn định.
4. So sánh tập khóa, số lượng hàng và các giá trị tính toán.
5. Kiểm tra riêng các partition lớn, hàng đồng hạng và ranh giới frame.
6. Đo kế hoạch và thời gian sau khi kết quả đã được xác nhận.

Đối với hai truy vấn cần cho cùng tập hàng, có thể dùng hai chiều NOT EXISTS để phát hiện chênh lệch:

~~~sql
WITH old_result AS (
    SELECT order_id
    FROM sales_orders
    WHERE status = 'PAID'
),
new_result AS (
    SELECT order_id
    FROM sales_orders
    WHERE status = 'PAID'
      AND total >= 0
)
SELECT 'missing_from_new' AS difference_type, o.order_id
FROM old_result AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM new_result AS n
    WHERE n.order_id = o.order_id
)
UNION ALL
SELECT 'extra_in_new' AS difference_type, n.order_id
FROM new_result AS n
WHERE NOT EXISTS (
    SELECT 1
    FROM old_result AS o
    WHERE o.order_id = n.order_id
);
~~~

Ví dụ này minh họa mẫu so sánh hai tập khóa; điều kiện truy vấn mới chỉ tương đương truy vấn cũ nếu dữ liệu thỏa total >= 0. Trong kiểm chứng thực tế, thay hai CTE bằng truy vấn cũ và truy vấn mới cần đối chiếu. Kết quả rỗng cho thấy không có khóa thiếu hoặc thừa, nhưng vẫn cần so sánh các cột giá trị tính toán.

Nếu kết quả có thể chứa nhiều hàng trùng khóa hoặc không có khóa duy nhất, cần so sánh theo toàn bộ khóa nghiệp vụ hoặc dùng cách đối chiếu có xét số lần xuất hiện. So sánh bằng DISTINCT có thể che giấu lỗi nhân bản hàng.

## 16. Các bẫy thường gặp

**“ORDER BY trong OVER sắp xếp luôn kết quả cuối.”** Không. Nó chỉ xác định thứ tự của cửa sổ. Muốn sắp xếp đầu ra phải có ORDER BY ở cấp truy vấn ngoài.

**“ROW_NUMBER tự tạo thứ tự ổn định.”** Không. Nếu ORDER BY không phân biệt được các hàng, thứ tự giữa chúng không được xác định. Thêm khóa duy nhất làm tie-breaker khi cần.

**“Frame mặc định luôn là từng hàng một.”** Không. Với ORDER BY, frame mặc định của aggregate window là RANGE từ UNBOUNDED PRECEDING đến CURRENT ROW; peer rows có thể cùng nằm trong frame.

**“LAST_VALUE luôn lấy hàng cuối của partition.”** Không. Nó lấy hàng cuối của frame hiện tại. Muốn toàn partition, khai báo frame đến UNBOUNDED FOLLOWING.

**“Có thể lọc ROW_NUMBER trong WHERE cùng cấp.”** Không. Tính cửa sổ ở CTE hoặc derived table rồi lọc ở truy vấn ngoài.

**“Mọi window function đều dùng frame.”** Không. ROW_NUMBER, RANK, DENSE_RANK, LAG và LEAD không dùng frame theo cách aggregate window dùng.

**“Thêm index là chắc chắn bỏ được sort.”** Không. Index chỉ có thể hỗ trợ một số access path và thứ tự; hãy xem kế hoạch thực tế.

**“Một truy vấn có nhiều OVER luôn chỉ sort một lần.”** Không. Các cửa sổ có thứ tự khác nhau có thể cần nhiều bước sort. Named window giúp chia sẻ định nghĩa, nhưng vẫn cần xác nhận kế hoạch.

**“CTE luôn được materialize.”** Không. CTE không chứa window function có thể được merge hoặc materialize tùy cấu trúc. CTE/derived table chứa window function trong MySQL phải materialize.

**“Tối ưu nhanh hơn là đủ.”** Không. Phải xác nhận kết quả không đổi, nhất là với peer rows, NULL, frame và JOIN có thể nhân bản hàng.

## 17. Checklist trước khi phát hành truy vấn window

- [ ] Đã xác định đúng tập hàng đầu vào sau WHERE, JOIN, GROUP BY và HAVING.
- [ ] Window function chỉ xuất hiện ở vị trí cú pháp được MySQL hỗ trợ.
- [ ] Không lồng trực tiếp window function hoặc dùng DISTINCT trong window aggregate.
- [ ] PARTITION BY phản ánh đúng nhóm nghiệp vụ.
- [ ] ORDER BY có tie-breaker khi cần thứ tự xác định.
- [ ] Frame được khai báo rõ nếu kết quả phụ thuộc ROWS hay RANGE.
- [ ] Đã kiểm tra peer rows và giá trị ở đầu/cuối partition.
- [ ] ORDER BY cuối truy vấn được khai báo nếu giao diện cần thứ tự cụ thể.
- [ ] Đã kiểm tra JOIN có làm nhân bản hàng trước khi tính cửa sổ không.
- [ ] Đã xem xét index theo bộ lọc, partition và thứ tự cửa sổ.
- [ ] Đã đọc EXPLAIN; dùng EXPLAIN ANALYZE khi môi trường và phiên bản phù hợp.
- [ ] Đã so sánh kết quả với tập dữ liệu nhỏ có thể tính bằng tay.
- [ ] Đã đối chiếu tập khóa và giá trị tính toán sau khi tối ưu.
- [ ] Đã đo với partition lớn và phân bố dữ liệu đại diện cho production.

## Kết luận

Window function trong MySQL có giới hạn vị trí sử dụng: tính toán trong SELECT hoặc ORDER BY, không lọc trực tiếp trong WHERE, GROUP BY hay HAVING cùng cấp; không lồng trực tiếp các window function và không hỗ trợ DISTINCT trong window aggregate. Khi cần lọc theo kết quả cửa sổ, hãy dùng CTE hoặc derived table.

Chi phí chủ yếu phụ thuộc số hàng đầu vào, kích thước partition, thứ tự sort, số window specification và dữ liệu trung gian. Index phù hợp có thể giúp một số kế hoạch nhưng không bảo đảm loại bỏ mọi sort. Hãy kiểm tra EXPLAIN, đo thực tế và xác nhận kết quả với dữ liệu có peer rows, ranh giới frame, NULL và JOIN. Cách làm này giúp truy vấn vừa đúng ngữ nghĩa vừa có hiệu năng có thể giải thích và kiểm chứng.
