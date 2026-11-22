# Derived table, bí danh và tổ chức truy vấn nhiều bước

Khi một truy vấn cần nhiều bước xử lý, việc viết tất cả phép lọc, nhóm, tính toán và nối bảng trong một SELECT duy nhất có thể khiến SQL khó đọc và khó kiểm tra. MySQL cho phép đặt một câu SELECT bên trong mệnh đề FROM. Kết quả của câu SELECT bên trong được dùng như một bảng ở truy vấn bên ngoài; cấu trúc này gọi là **derived table** (bảng dẫn xuất).

Derived table giúp chia truy vấn thành các bước có ranh giới rõ ràng: bước đầu tạo tập dữ liệu trung gian, bước tiếp theo lọc hoặc nối tập đó, bước cuối tổng hợp và trình bày kết quả. Bí danh (alias) đặt tên cho derived table và các cột của nó, giúp truy vấn dễ đọc và tránh mơ hồ khi có nhiều nguồn dữ liệu.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: làm chủ JOIN và truy vấn con, tổ chức truy vấn SQL nhiều bước, kiểm soát phạm vi bí danh, hiểu cách MySQL tối ưu derived table và đọc EXPLAIN để đánh giá hiệu năng.

## 1. Derived table là gì?

Derived table là một truy vấn con xuất hiện trong mệnh đề FROM. MySQL thực thi hoặc biến đổi truy vấn con đó để cung cấp một tập hàng cho truy vấn bên ngoài.

Cú pháp:

~~~sql
SELECT
    outer_alias.column_name
FROM (
    SELECT
        column_a,
        column_b
    FROM source_table
    WHERE condition
) AS outer_alias;
~~~

Phần trong ngoặc là truy vấn tạo tập dữ liệu. Tên ngay sau ngoặc là bí danh bắt buộc của derived table. Truy vấn bên ngoài xem kết quả đó như một nguồn bảng có các cột được SELECT từ truy vấn bên trong.

Ví dụ:

~~~sql
SELECT
    customer_totals.customer_id,
    customer_totals.order_count,
    customer_totals.total_amount
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS customer_totals
WHERE customer_totals.total_amount >= 1000
ORDER BY customer_totals.total_amount DESC;
~~~

Truy vấn được chia thành hai bước logic:

1. Derived table \`customer_totals\` nhóm đơn hàng theo customer_id, tính số đơn và tổng tiền của mỗi khách hàng.
2. Truy vấn ngoài lọc những khách hàng có tổng tiền từ 1.000 trở lên và sắp xếp theo tổng tiền giảm dần.

Derived table không phải bảng vật lý được tạo sẵn trong schema. Nó là nguồn dữ liệu nằm trong phạm vi một câu lệnh SQL. MySQL có thể materialize tập kết quả vào một cấu trúc tạm hoặc biến đổi truy vấn để không cần tạo bảng trung gian vật lý; phần tối ưu sẽ được giải thích ở các mục sau.

## 2. Bí danh của derived table là bắt buộc

MySQL yêu cầu derived table trong FROM có bí danh. Ví dụ sau thiếu alias:

~~~sql
SELECT *
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
);
~~~

Câu lệnh không hợp lệ vì truy vấn con trong FROM chưa được đặt tên.

Cách viết đúng:

~~~sql
SELECT *
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS customer_summary;
~~~

Có thể bỏ từ khóa AS:

~~~sql
SELECT *
FROM (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) customer_summary;
~~~

Dùng AS thường làm alias dễ nhận biết hơn. Nên đặt tên có ý nghĩa theo vai trò dữ liệu, chẳng hạn \`customer_summary\`, \`monthly_sales\`, \`latest_payment\` hoặc \`active_accounts\`, thay vì các tên quá chung như \`t1\`, \`x\`, \`tmp\`.

### 2.1. Alias giúp truy vấn ngoài tham chiếu cột

Sau khi đặt alias, truy vấn ngoài dùng dạng:

~~~sql
alias_name.column_name
~~~

Ví dụ:

~~~sql
SELECT
    monthly_sales.month_start,
    monthly_sales.revenue
FROM (
    SELECT
        DATE_FORMAT(created_at, '%Y-%m-01') AS month_start,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY DATE_FORMAT(created_at, '%Y-%m-01')
) AS monthly_sales;
~~~

Việc ghi đầy đủ alias trước tên cột đặc biệt hữu ích khi truy vấn có nhiều bảng cùng chứa cột \`id\`, \`name\`, \`created_at\` hoặc \`status\`.

### 2.2. Alias của bảng nguồn và alias của derived table khác nhau

Trong ví dụ:

~~~sql
SELECT
    customer_summary.customer_id,
    customer_summary.total_amount
FROM (
    SELECT
        o.customer_id,
        SUM(o.total_amount) AS total_amount
    FROM orders AS o
    GROUP BY o.customer_id
) AS customer_summary;
~~~

- \`o\` là alias của bảng orders bên trong truy vấn con.
- \`customer_summary\` là alias của derived table ở truy vấn ngoài.

Alias của bảng orders chỉ có phạm vi bên trong truy vấn con. Truy vấn ngoài không thể dùng \`o.customer_id\` sau khi truy vấn con kết thúc; nó chỉ nhìn thấy các cột mà derived table xuất ra.

### 2.3. Alias cột và tên cột kết quả

Nên đặt alias rõ ràng cho các biểu thức được tính toán:

~~~sql
SELECT
    summary.customer_id,
    summary.order_count,
    summary.average_amount
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        AVG(total_amount) AS average_amount
    FROM orders
    GROUP BY customer_id
) AS summary;
~~~

Nếu không đặt alias cho biểu thức, tên cột kết quả có thể khó tham chiếu hoặc không ổn định theo cách người đọc mong đợi. Đặt alias ngay trong truy vấn con tạo một giao diện cột rõ ràng cho truy vấn ngoài.

### 2.4. Danh sách alias cột của derived table

MySQL cũng hỗ trợ danh sách tên cột đặt sau alias của derived table. Cách này hữu ích khi muốn đổi tên cột kết quả tại ranh giới của bảng dẫn xuất:

~~~sql
SELECT
    customer_summary.customer_id,
    customer_summary.order_count
FROM (
    SELECT customer_id, COUNT(*)
    FROM orders
    GROUP BY customer_id
) AS customer_summary (customer_id, order_count);
~~~

Danh sách alias cột phải có số phần tử phù hợp với số cột truy vấn con trả về. Dù cú pháp này có thể dùng, đặt alias ngay trong SELECT bên trong thường dễ đọc hơn vì người viết nhìn thấy tên kết quả ngay tại biểu thức tạo ra nó.

## 3. Derived table hoạt động theo phạm vi truy vấn

Một derived table tạo ra tập cột riêng. Truy vấn ngoài chỉ có thể tham chiếu các cột mà SELECT bên trong xuất ra.

Ví dụ:

~~~sql
SELECT summary.customer_id, summary.total_amount
FROM (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS summary;
~~~

Truy vấn ngoài không thể tham chiếu \`orders.created_at\` vì cột đó không được xuất ra từ derived table.

Nếu truy vấn ngoài cần lọc theo tháng, hãy xuất cột tháng từ truy vấn con:

~~~sql
SELECT
    monthly_summary.customer_id,
    monthly_summary.month_start,
    monthly_summary.total_amount
FROM (
    SELECT
        customer_id,
        DATE_FORMAT(created_at, '%Y-%m-01') AS month_start,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY
        customer_id,
        DATE_FORMAT(created_at, '%Y-%m-01')
) AS monthly_summary
WHERE monthly_summary.month_start >= '2025-01-01';
~~~

Quy tắc thiết kế: derived table nên xuất đủ các cột mà bước tiếp theo cần, nhưng không cần đưa ra mọi cột của bảng nguồn.

### 3.1. Tên cột trùng nhau

Nếu derived table tạo ra hai cột cùng tên, việc tham chiếu có thể mơ hồ hoặc MySQL từ chối vì tên cột trong derived table không duy nhất.

Không nên:

~~~sql
SELECT *
FROM (
    SELECT
        c.id,
        o.id
    FROM customer AS c
    JOIN orders AS o ON o.customer_id = c.id
) AS joined_data;
~~~

Nên đặt alias riêng:

~~~sql
SELECT *
FROM (
    SELECT
        c.id AS customer_id,
        o.id AS order_id
    FROM customer AS c
    JOIN orders AS o ON o.customer_id = c.id
) AS joined_data;
~~~

Tên cột duy nhất làm cho giao diện derived table dễ sử dụng và tránh tham chiếu nhầm.

## 4. Dùng derived table để tách truy vấn nhiều bước

Derived table đặc biệt hữu ích khi bước sau cần dùng kết quả tổng hợp hoặc tính toán của bước trước.

### 4.1. Bước 1: tổng hợp, bước 2: lọc kết quả tổng hợp

Không thể dùng trực tiếp alias tổng hợp trong WHERE của cùng SELECT vì WHERE được xử lý trước bước tính toán nhóm. Derived table tạo ranh giới để truy vấn ngoài lọc kết quả đã tổng hợp.

~~~sql
SELECT
    customer_summary.customer_id,
    customer_summary.total_amount
FROM (
    SELECT
        customer_id,
        SUM(total_amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) AS customer_summary
WHERE customer_summary.total_amount >= 5000;
~~~

Có thể viết bằng HAVING ngay trong cùng SELECT:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
HAVING SUM(total_amount) >= 5000;
~~~

Hai cách có thể biểu đạt cùng một mục tiêu. Dùng HAVING khi chỉ cần lọc nhóm ngay tại bước tổng hợp. Dùng derived table khi kết quả tổng hợp còn cần JOIN với nguồn khác, tính tiếp, phân trang hoặc được dùng như một tập dữ liệu độc lập.

### 4.2. Bước 1: tính chỉ số, bước 2: phân loại

~~~sql
SELECT
    customer_metrics.customer_id,
    customer_metrics.order_count,
    customer_metrics.revenue,
    CASE
        WHEN customer_metrics.revenue >= 10000 THEN 'GOLD'
        WHEN customer_metrics.revenue >= 5000 THEN 'SILVER'
        ELSE 'STANDARD'
    END AS customer_tier
FROM (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED')
    GROUP BY customer_id
) AS customer_metrics
ORDER BY customer_metrics.revenue DESC;
~~~

Bước trong cùng tạo chỉ số cho mỗi khách hàng. Bước ngoài dùng các chỉ số đó để phân hạng. Cách tổ chức này giúp tránh lặp lại biểu thức SUM trong nhiều nơi.

### 4.3. Bước 1: tìm lần mua gần nhất, bước 2: lấy thông tin đơn hàng

~~~sql
SELECT
    latest_order.customer_id,
    latest_order.order_id,
    latest_order.created_at,
    latest_order.total_amount
FROM (
    SELECT
        customer_id,
        MAX(created_at) AS latest_created_at
    FROM orders
    GROUP BY customer_id
) AS latest_time
JOIN orders AS latest_order
  ON latest_order.customer_id = latest_time.customer_id
 AND latest_order.created_at = latest_time.latest_created_at;
~~~

Derived table tính thời điểm đặt đơn gần nhất theo khách hàng. Truy vấn ngoài nối lại bảng orders để lấy các cột chi tiết của đơn hàng.

Nếu một khách hàng có hai đơn cùng created_at lớn nhất, truy vấn có thể trả nhiều hàng. Nếu nghiệp vụ cần đúng một đơn, phải có tiêu chí phá hòa ổn định, chẳng hạn order_id lớn nhất, hoặc dùng ROW_NUMBER() trong MySQL 8.0.

### 4.4. Tổ chức báo cáo nhiều bước

Một báo cáo có thể chia thành:

1. Lọc các đơn hợp lệ.
2. Tổng hợp doanh thu theo khách hàng.
3. JOIN với bảng customer.
4. Phân nhóm khách hàng theo doanh thu.
5. Sắp xếp và giới hạn kết quả.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    s.order_count,
    s.revenue,
    CASE
        WHEN s.revenue >= 10000 THEN 'GOLD'
        WHEN s.revenue >= 5000 THEN 'SILVER'
        ELSE 'STANDARD'
    END AS tier
FROM customer AS c
JOIN (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status IN ('PAID', 'SHIPPED')
      AND created_at >= '2025-01-01'
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id
WHERE c.is_active = 1
ORDER BY s.revenue DESC
LIMIT 50;
~~~

Derived table \`s\` đóng vai trò kết quả tổng hợp, còn bảng customer cung cấp thuộc tính hồ sơ. Dùng INNER JOIN vì truy vấn chỉ cần khách hàng có đơn phù hợp. Nếu muốn giữ cả khách hàng chưa có đơn, cần thay bằng LEFT JOIN và xử lý NULL ở các cột tổng hợp.

## 5. Derived table kết hợp JOIN

Derived table có thể đứng cùng bảng thông thường trong FROM và được JOIN như một nguồn dữ liệu.

### 5.1. JOIN với tập kết quả đã tổng hợp

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(s.revenue, 0) AS revenue
FROM customer AS c
LEFT JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id;
~~~

Truy vấn giữ tất cả khách hàng, kể cả người chưa có đơn PAID. Với những hàng không có bản ghi khớp ở derived table, các cột s.revenue là NULL; COALESCE chuyển thành 0 để hiển thị.

Chỉ dùng COALESCE nếu nghiệp vụ coi không có giao dịch tương đương doanh thu bằng 0. Nếu cần phân biệt “không có dữ liệu” với “tổng bằng 0”, hãy giữ NULL.

### 5.2. Điều kiện lọc ở ON và WHERE

Với LEFT JOIN, vị trí điều kiện có thể làm thay đổi việc giữ hàng không khớp.

Ví dụ giữ tất cả khách hàng, chỉ lấy phần tổng hợp có doanh thu lớn:

~~~sql
SELECT
    c.customer_id,
    s.revenue
FROM customer AS c
LEFT JOIN (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id
 AND s.revenue >= 1000;
~~~

Nếu chuyển điều kiện \`s.revenue >= 1000\` xuống WHERE, các hàng không có kết quả tổng hợp sẽ bị loại vì NULL >= 1000 là UNKNOWN. Khi đó LEFT JOIN có thể hoạt động giống INNER JOIN đối với điều kiện này.

~~~sql
SELECT
    c.customer_id,
    s.revenue
FROM customer AS c
LEFT JOIN (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS s
  ON s.customer_id = c.customer_id
WHERE s.revenue >= 1000;
~~~

Hãy đặt điều kiện theo ý nghĩa: điều kiện giới hạn hàng được ghép thuộc ON; điều kiện lọc tập kết quả cuối thuộc WHERE. Với outer join, đừng chuyển điều kiện giữa hai vị trí mà không kiểm tra tác động lên hàng không khớp.

### 5.3. Nhiều derived table trong cùng truy vấn

Có thể JOIN nhiều tập dữ liệu trung gian:

~~~sql
SELECT
    c.customer_id,
    order_summary.order_count,
    payment_summary.paid_count
FROM customer AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) AS order_summary
  ON order_summary.customer_id = c.customer_id
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS paid_count
    FROM payment
    WHERE payment_status = 'SUCCESS'
    GROUP BY customer_id
) AS payment_summary
  ON payment_summary.customer_id = c.customer_id;
~~~

Mỗi derived table có một trách nhiệm riêng: tổng hợp đơn hàng và tổng hợp thanh toán. Cách này tránh nhân bản hàng do JOIN trực tiếp hai bảng chi tiết có quan hệ một-nhiều với cùng khách hàng.

Trước khi JOIN nhiều nguồn chi tiết, hãy xác định cardinality. Nếu một khách hàng có 3 đơn và 4 lần thanh toán, JOIN trực tiếp hai tập chi tiết có thể tạo 12 hàng và làm SUM/COUNT bị nhân lên. Tổng hợp từng nguồn về một hàng mỗi khách hàng trước khi JOIN giúp kiểm soát hiện tượng fan-out.

## 6. Derived table và CTE: hai cách tổ chức truy vấn nhiều bước

MySQL 8.0 hỗ trợ Common Table Expression (CTE) với mệnh đề WITH. CTE đặt tên cho một tập kết quả tạm trong phạm vi một câu lệnh.

Derived table:

~~~sql
SELECT
    summary.customer_id,
    summary.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS summary
WHERE summary.revenue >= 5000;
~~~

CTE tương đương:

~~~sql
WITH summary AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    summary.customer_id,
    summary.revenue
FROM summary
WHERE summary.revenue >= 5000;
~~~

### 6.1. Khi nào dùng derived table?

Derived table phù hợp khi:
- Tập trung gian chỉ được dùng một lần.
- Logic nằm ngay cạnh JOIN cần sử dụng nó.
- Truy vấn không quá dài và tên alias đủ rõ.
- Muốn hỗ trợ MySQL 5.7 trở xuống, nơi CTE chưa được hỗ trợ.

### 6.2. Khi nào dùng CTE?

CTE phù hợp khi:
- Truy vấn có nhiều bước và cần đặt tên cho từng bước.
- Một tập logic cần được tham chiếu nhiều lần trong cùng câu lệnh.
- Muốn tách phần chuẩn bị dữ liệu khỏi truy vấn cuối.
- Cần dùng recursive CTE cho cây phân cấp hoặc chuỗi quan hệ.

Ví dụ nhiều bước:

~~~sql
WITH paid_orders AS (
    SELECT customer_id, total_amount, created_at
    FROM orders
    WHERE status = 'PAID'
),
customer_summary AS (
    SELECT
        customer_id,
        COUNT(*) AS paid_order_count,
        SUM(total_amount) AS paid_revenue
    FROM paid_orders
    GROUP BY customer_id
),
ranked_customers AS (
    SELECT
        customer_id,
        paid_order_count,
        paid_revenue,
        DENSE_RANK() OVER (ORDER BY paid_revenue DESC) AS revenue_rank
    FROM customer_summary
)
SELECT
    customer_id,
    paid_order_count,
    paid_revenue,
    revenue_rank
FROM ranked_customers
WHERE revenue_rank <= 10
ORDER BY revenue_rank, customer_id;
~~~

CTE làm rõ từng bước: lọc đơn đã thanh toán, tổng hợp theo khách hàng, xếp hạng và lấy nhóm đầu. CTE không mặc định nhanh hơn derived table; optimizer có thể merge hoặc materialize tùy cấu trúc.

### 6.3. CTE có thể được tham chiếu nhiều lần

~~~sql
WITH customer_totals AS (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    (SELECT COUNT(*) FROM customer_totals) AS customer_count,
    (SELECT SUM(revenue) FROM customer_totals) AS total_revenue;
~~~

CTE giúp tránh viết lại cùng một định nghĩa truy vấn trong một câu lệnh. Tuy nhiên, cần kiểm tra kế hoạch thực thi để hiểu MySQL xử lý CTE và việc materialize ra sao.

## 7. Derived table và subquery tương quan

Derived table thông thường trong FROM không thể tham chiếu trực tiếp alias của bảng bên ngoài cùng cấp. Nó là một truy vấn độc lập, trừ khi được khai báo LATERAL.

Ví dụ sau không hợp lệ trong MySQL vì derived table tham chiếu \`c.customer_id\` nhưng không có LATERAL:

~~~sql
SELECT
    c.customer_id,
    recent.order_id
FROM customer AS c
JOIN (
    SELECT order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 1
) AS recent;
~~~

Muốn truy vấn con trong FROM tham chiếu bảng đứng trước nó, MySQL hỗ trợ LATERAL derived table từ MySQL 8.0.14.

### 7.1. LATERAL derived table

~~~sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at
FROM customer AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id,
        o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE;
~~~

LATERAL cho phép derived table tham chiếu c.customer_id từ hàng hiện tại của bảng customer. Với mỗi khách hàng, truy vấn con tìm đơn gần nhất và giới hạn một hàng.

- LEFT JOIN LATERAL giữ khách hàng chưa có đơn; các cột recent sẽ là NULL.
- CROSS JOIN LATERAL chỉ giữ khách hàng có kết quả từ derived table.
- ORDER BY có order_id làm tie-breaker để chọn ổn định khi thời điểm tạo trùng nhau.

Đây là kỹ thuật hữu ích cho top-N theo từng nhóm. Tuy nhiên, nó có thể thực hiện truy vấn con nhiều lần theo hàng bên trái; cần index phù hợp, ví dụ index trên \`(customer_id, created_at, order_id)\`, và kiểm tra EXPLAIN ANALYZE trên dữ liệu thực tế.

### 7.2. So sánh với correlated subquery trong SELECT

Một cách khác để lấy thời điểm đơn gần nhất:

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.created_at)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS latest_order_at
FROM customer AS c;
~~~

Đây là scalar correlated subquery trong danh sách SELECT. Nó trả một giá trị cho mỗi hàng customer. Derived table LATERAL có thể trả nhiều cột và nhiều hàng, còn scalar subquery phải trả một giá trị đơn (nếu trả nhiều hàng, MySQL báo lỗi).

Chọn cách viết theo số lượng dữ liệu cần lấy và kế hoạch thực thi.

## 8. Derived table và phép sắp xếp

Không được giả định derived table luôn giữ thứ tự hàng từ truy vấn con. SQL chỉ bảo đảm thứ tự kết quả cuối cùng khi SELECT ngoài cùng có ORDER BY.

Ví dụ:

~~~sql
SELECT *
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC
) AS ordered_orders;
~~~

Không nên dựa vào ORDER BY bên trong để bảo đảm thứ tự trả về của truy vấn ngoài. Optimizer có thể bỏ qua ORDER BY trong derived table nếu thứ tự đó không ảnh hưởng tới kết quả truy vấn.

Nếu mục tiêu là chọn một số hàng đầu, ORDER BY phải đi cùng LIMIT trong truy vấn con:

~~~sql
SELECT *
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 10
) AS latest_orders
ORDER BY latest_orders.created_at DESC, latest_orders.order_id DESC;
~~~

LIMIT làm cho thứ tự trong truy vấn con có ý nghĩa đối với việc xác định hàng được chọn. ORDER BY ngoài cùng vẫn cần thiết để bảo đảm thứ tự hiển thị cuối cùng.

## 9. Derived table và LIMIT, DISTINCT, GROUP BY

Một số mệnh đề làm thay đổi cách optimizer xử lý derived table. Ví dụ:

~~~sql
SELECT *
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS customer_summary
WHERE revenue >= 1000;
~~~

GROUP BY tạo một hàng cho mỗi nhóm, do đó tập kết quả có ngữ nghĩa tổng hợp riêng. MySQL không thể đơn giản bỏ GROUP BY như một truy vấn lọc thông thường.

Các đặc điểm như DISTINCT, GROUP BY, HAVING, LIMIT, UNION, window function và aggregate function có thể ngăn derived table được merge vào truy vấn ngoài, khiến MySQL cần materialize kết quả hoặc dùng chiến lược tối ưu khác.

Không cần tự đoán chính xác chiến lược từ cú pháp. Hãy dùng EXPLAIN để xem truy vấn có materialize hay không.

## 10. MySQL tối ưu derived table: merge và materialization

MySQL có thể xử lý derived table theo hai hướng chính:

1. **Merge:** hợp nhất truy vấn con vào query block bên ngoài, giúp optimizer tối ưu như một truy vấn lớn.
2. **Materialization:** thực thi truy vấn con và lưu kết quả vào một bảng tạm nội bộ để truy vấn ngoài đọc.

### 10.1. Merge derived table

Ví dụ:

~~~sql
SELECT
    d.customer_id,
    d.customer_name
FROM (
    SELECT customer_id, customer_name
    FROM customer
) AS d
WHERE d.customer_id = 10;
~~~

Derived table không có phép tổng hợp hoặc giới hạn đặc biệt. Optimizer có thể merge nó, tương đương về logic với:

~~~sql
SELECT customer_id, customer_name
FROM customer
WHERE customer_id = 10;
~~~

Khi merge, điều kiện từ truy vấn ngoài có thể được đưa xuống bảng cơ sở, giúp sử dụng index và tránh tạo bảng tạm không cần thiết.

### 10.2. Materialize derived table

Ví dụ có GROUP BY:

~~~sql
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

Kết quả tổng hợp có thể được materialize để truy vấn ngoài đọc. MySQL có thể tạo index nội bộ trên bảng tạm nếu điều đó giúp truy cập kết quả hiệu quả hơn.

Materialization không nhất thiết luôn xấu. Khi tập trung gian được tổng hợp mạnh, có ít hàng hơn bảng gốc hoặc được dùng nhiều lần, lưu kết quả trung gian có thể hợp lý.

### 10.3. Một số trường hợp cản merge

Các cấu trúc sau thường ngăn derived table được merge:

- Aggregate functions như SUM, COUNT, AVG, MIN, MAX.
- DISTINCT.
- GROUP BY.
- HAVING.
- LIMIT.
- UNION hoặc UNION ALL.
- Window functions.
- Subquery trong danh sách SELECT của derived table.
- Một số biểu thức gán biến người dùng.

Danh sách điều kiện tối ưu có thể thay đổi theo phiên bản MySQL. Hãy tham khảo manual của phiên bản đang chạy nếu cần dựa vào một quy tắc cụ thể.

### 10.4. Hint MERGE và NO_MERGE

MySQL hỗ trợ optimizer hint để gợi ý merge hoặc không merge một derived table/CTE trong các trường hợp phù hợp.

~~~sql
SELECT /*+ NO_MERGE(d) */
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d;
~~~

Hoặc:

~~~sql
SELECT /*+ MERGE(d) */
    d.customer_id,
    d.customer_name
FROM (
    SELECT customer_id, customer_name
    FROM customer
) AS d;
~~~

Hint không bảo đảm MySQL sẽ thực hiện đúng ý muốn trong mọi trường hợp. Một số cấu trúc không thể merge về mặt ngữ nghĩa, và optimizer có thể bỏ qua hint không áp dụng được. Không thêm hint trước khi đo; hãy so sánh kế hoạch và thời gian thực thi.

## 11. Derived condition pushdown

Trong một số trường hợp, MySQL có thể đẩy điều kiện từ truy vấn ngoài xuống derived table để giảm số hàng phải xử lý. Kỹ thuật này gọi là derived condition pushdown.

Ví dụ:

~~~sql
SELECT *
FROM (
    SELECT
        customer_id,
        status,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id, status
) AS d
WHERE d.customer_id = 10;
~~~

Điều kiện customer_id = 10 có thể được đẩy xuống trước bước GROUP BY vì customer_id là cột nhóm. Khi đó MySQL có thể chỉ tổng hợp đơn của khách hàng 10 thay vì tất cả khách hàng.

Điều kiện trên kết quả aggregate như revenue >= 5000 có thể được đẩy xuống HAVING thay vì WHERE vì nó phụ thuộc vào giá trị sau tổng hợp.

Derived condition pushdown được cải thiện trong các phiên bản MySQL 8.0; hỗ trợ và điều kiện áp dụng phụ thuộc phiên bản và cấu trúc truy vấn. Hãy kiểm tra optimizer trace hoặc EXPLAIN khi cần xác minh.

Không phải mọi điều kiện đều có thể đẩy xuống. Điều kiện chứa biểu thức không tương thích, phụ thuộc giá trị tổng hợp hoặc làm thay đổi ngữ nghĩa LIMIT/outer join có thể không được đẩy.

## 12. Đọc EXPLAIN cho derived table

EXPLAIN giúp xem MySQL dự định truy cập bảng cơ sở, merge hay materialize derived table.

Ví dụ:

~~~sql
EXPLAIN
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

Có thể xem dạng cây:

~~~sql
EXPLAIN FORMAT=TREE
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

Các dấu hiệu cần chú ý trong EXPLAIN:

- Có bước Materialize hoặc Materialize with deduplication hay không.
- Derived table có được merge hay không.
- Bảng nguồn dùng access type nào.
- Index nào được chọn.
- Số hàng ước tính ở từng bước.
- Có temporary table hoặc filesort hay không.

Với MySQL 8.0, EXPLAIN ANALYZE thực thi câu lệnh SELECT và cung cấp thời gian cùng số hàng thực tế ở các iterator:

~~~sql
EXPLAIN ANALYZE
SELECT
    d.customer_id,
    d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d
WHERE d.revenue >= 5000;
~~~

EXPLAIN ANALYZE thực sự chạy truy vấn. Hãy dùng trên môi trường phù hợp và tránh chạy thử tùy tiện với truy vấn quá nặng trên production.

## 13. Tối ưu truy vấn nhiều bước

### 13.1. Chỉ lấy cột cần thiết

Không dùng SELECT * trong derived table nếu truy vấn ngoài chỉ cần vài cột:

~~~sql
SELECT d.customer_id, d.revenue
FROM (
    SELECT *
    FROM orders
) AS d;
~~~

Nên viết:

~~~sql
SELECT d.customer_id, d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
) AS d;
~~~

Chọn đúng cột giúp giảm kích thước dữ liệu trung gian, tăng khả năng covering index và làm rõ hợp đồng giữa các bước.

### 13.2. Lọc sớm khi điều kiện không làm thay đổi ngữ nghĩa

~~~sql
SELECT d.customer_id, d.revenue
FROM (
    SELECT customer_id, SUM(total_amount) AS revenue
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= '2025-01-01'
    GROUP BY customer_id
) AS d;
~~~

Lọc các hàng không cần thiết trước khi tổng hợp có thể giảm dữ liệu cần xử lý. Tuy nhiên, không chuyển điều kiện từ ngoài vào trong nếu việc đó thay đổi ý nghĩa của GROUP BY, LIMIT, outer join hoặc kết quả tổng hợp.

### 13.3. Index cho bảng cơ sở

Nếu truy vấn lọc theo status và khoảng thời gian rồi nhóm theo customer_id, hãy đánh giá các index như:

~~~sql
CREATE INDEX idx_orders_status_created_customer
ON orders (status, created_at, customer_id);
~~~

Không có thứ tự index đúng cho mọi workload. Cần dựa vào điều kiện lọc, cardinality, thứ tự nhóm, cột cần đọc và chi phí ghi. EXPLAIN giúp kiểm tra optimizer có dùng index như mong đợi hay không.

### 13.4. Tránh lặp lại cùng một phép tổng hợp

Nếu cùng một tập tổng hợp được tham chiếu nhiều lần trong một câu lệnh, cân nhắc CTE hoặc derived table có tên để tránh lặp định nghĩa. Nhưng lưu ý CTE/derived table có thể được materialize hoặc merge theo chiến lược của optimizer. Đừng giả định viết một lần luôn đồng nghĩa tính một lần; hãy xem kế hoạch.

### 13.5. Không dùng derived table chỉ để đổi tên cột

Truy vấn:

~~~sql
SELECT d.customer_id
FROM (
    SELECT customer_id
    FROM customer
) AS d;
~~~

không mang lại lợi ích tổ chức đáng kể. Nếu không có bước lọc, nhóm, tính toán hoặc ranh giới logic cần thiết, truy vấn trực tiếp thường đơn giản hơn.

## 14. Derived table với window functions

Window function tạo giá trị theo một cửa sổ hàng nhưng vẫn giữ các hàng chi tiết. Derived table giúp lọc kết quả window ở truy vấn ngoài, vì không thể dùng trực tiếp alias window trong WHERE cùng query block.

Ví dụ lấy ba đơn hàng có giá trị cao nhất của mỗi khách hàng:

~~~sql
SELECT
    ranked_orders.customer_id,
    ranked_orders.order_id,
    ranked_orders.total_amount,
    ranked_orders.order_rank
FROM (
    SELECT
        customer_id,
        order_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS order_rank
    FROM orders
) AS ranked_orders
WHERE ranked_orders.order_rank <= 3
ORDER BY
    ranked_orders.customer_id,
    ranked_orders.order_rank;
~~~

Bước trong tính thứ hạng cho mỗi đơn trong nhóm khách hàng. Bước ngoài lọc rank từ 1 đến 3.

MySQL 8.0 hỗ trợ window functions. Nếu cần tương thích MySQL 5.7, phải dùng cách khác như correlated subquery, anti-join hoặc truy vấn tổng hợp phù hợp.

## 15. LATERAL derived table và top-N theo từng hàng

MySQL 8.0.14 trở lên hỗ trợ LATERAL derived table. Đây là trường hợp derived table được phép tham chiếu các bảng đứng trước nó trong FROM.

Ví dụ lấy hai lần thanh toán gần nhất của từng đơn hàng:

~~~sql
SELECT
    o.order_id,
    recent.payment_id,
    recent.paid_at,
    recent.amount
FROM orders AS o
LEFT JOIN LATERAL (
    SELECT
        p.payment_id,
        p.paid_at,
        p.amount
    FROM payment AS p
    WHERE p.order_id = o.order_id
    ORDER BY p.paid_at DESC, p.payment_id DESC
    LIMIT 2
) AS recent ON TRUE
WHERE o.created_at >= '2025-01-01'
ORDER BY o.order_id, recent.paid_at DESC;
~~~

Derived table LATERAL có thể đọc o.order_id và trả tối đa hai hàng thanh toán cho mỗi đơn. LEFT JOIN giữ cả đơn chưa có thanh toán.

Index có thể cần đánh giá:

~~~sql
CREATE INDEX idx_payment_order_paid
ON payment (order_id, paid_at, payment_id);
~~~

Nếu có nhiều đơn, truy vấn con có thể được thực thi theo từng hàng đơn hàng. Index theo order_id và thời điểm thanh toán giúp tìm các hàng liên quan và lấy top-N. Kiểm tra EXPLAIN ANALYZE trước khi sử dụng ở quy mô lớn.

## 16. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Derived table báo lỗi cú pháp | Thiếu alias sau ngoặc | Đặt alias cho mọi derived table |
| Truy vấn ngoài không tìm thấy cột | Cột không được SELECT ở truy vấn con | Xuất cột cần dùng từ derived table |
| Column ambiguous | Nhiều nguồn có cột cùng tên | Dùng alias bảng và tên cột đầy đủ |
| Alias bảng bên trong không dùng được ở ngoài | Alias chỉ có phạm vi query block bên trong | Tham chiếu alias derived table và cột được xuất |
| Alias SELECT không dùng được trong WHERE cùng cấp | WHERE được xử lý trước danh sách SELECT | Dùng derived table/CTE hoặc lặp predicate phù hợp |
| Derived table tham chiếu bảng ngoài nhưng báo lỗi | Derived table không LATERAL | Dùng LATERAL từ MySQL 8.0.14 nếu phù hợp |
| ORDER BY bên trong không giữ thứ tự đầu ra | Chỉ ORDER BY ngoài cùng bảo đảm thứ tự cuối | Đặt ORDER BY ở SELECT ngoài cùng |
| LEFT JOIN mất hàng không khớp | Điều kiện cột bên phải đặt ở WHERE | Xem xét đặt điều kiện giới hạn ghép trong ON |
| JOIN hai bảng chi tiết làm SUM bị nhân | Fan-out do quan hệ một-nhiều | Tổng hợp từng nguồn trước khi JOIN |
| Derived table tốn tài nguyên | Materialize tập trung gian lớn | Lọc sớm, giảm cột, kiểm tra merge và index |
| Dùng LIMIT nhưng kết quả không ổn định | ORDER BY không có tie-breaker duy nhất | Thêm khóa duy nhất vào ORDER BY |
| Cố ép optimizer merge một truy vấn không thể merge | Cấu trúc có GROUP BY, LIMIT hoặc đặc điểm cản merge | Hiểu điều kiện merge; không phụ thuộc hint mù quáng |

## 17. Quy trình tổ chức một truy vấn nhiều bước

Khi truy vấn bắt đầu có nhiều JOIN, phép tổng hợp và tính toán, hãy thực hiện theo trình tự:

1. Xác định kết quả cuối cần những cột nào và mỗi hàng đại diện cho thực thể nào.
2. Chia truy vấn thành các bước logic: lọc nguồn, tổng hợp, nối, phân loại, xếp hạng.
3. Chọn derived table nếu tập trung gian chỉ dùng tại một vị trí; chọn CTE nếu cần tên bước rõ ràng hoặc tham chiếu lại.
4. Đặt alias bảng, derived table và cột có ý nghĩa.
5. Kiểm tra mỗi derived table trả đúng một hàng cho mỗi khóa mà truy vấn ngoài mong đợi.
6. Xác định cardinality trước khi JOIN để tránh nhân bản hàng.
7. Chỉ xuất cột cần thiết và lọc sớm khi không thay đổi ngữ nghĩa.
8. Nếu cần tham chiếu bảng bên ngoài từ derived table, xác định có cần LATERAL hay correlated subquery.
9. Đặt ORDER BY ở query block bảo đảm thứ tự mà nghiệp vụ cần.
10. Kiểm tra merge/materialization, index và số hàng qua EXPLAIN.
11. Dùng dữ liệu biên: không có hàng khớp, nhiều hàng đồng hạng, NULL và nhóm rỗng.
12. So sánh kết quả với truy vấn kiểm chứng độc lập trước khi đưa vào ứng dụng.

## 18. Bài tập thực hành

### Bài 1: Tổng hợp rồi lọc

Tạo bảng orders có customer_id và total_amount. Viết derived table tính tổng tiền theo khách hàng, sau đó chỉ lấy khách có doanh thu từ 5.000 trở lên. Viết lại bằng GROUP BY/HAVING và so sánh.

### Bài 2: Alias và phạm vi cột

Tạo truy vấn JOIN customer với orders bên trong derived table. Đặt alias customer_id, order_id và revenue. Thử bỏ một cột khỏi SELECT con rồi tham chiếu ở ngoài để quan sát lỗi.

### Bài 3: Tổng hợp trước khi JOIN

Một khách hàng có nhiều đơn và nhiều thanh toán. Viết truy vấn JOIN trực tiếp hai bảng chi tiết và quan sát số hàng bị nhân. Sau đó tổng hợp orders và payment riêng theo customer_id rồi JOIN hai derived table.

### Bài 4: LEFT JOIN và vị trí điều kiện

Viết hai truy vấn LEFT JOIN derived table: một truy vấn đặt điều kiện doanh thu trong ON, một truy vấn đặt ở WHERE. So sánh khách hàng không có đơn và giải thích sự khác biệt.

### Bài 5: Derived table và CTE

Viết cùng một báo cáo bằng derived table và CTE. So sánh khả năng đọc, số bước logic và EXPLAIN. Nêu trường hợp nên chọn mỗi cách.

### Bài 6: Lấy đơn mới nhất

Dùng derived table tính MAX(created_at) theo khách hàng rồi JOIN lại orders. Tạo hai đơn có cùng created_at lớn nhất để quan sát kết quả nhiều hàng. Sau đó dùng ROW_NUMBER() với order_id làm tie-breaker.

### Bài 7: LATERAL top-N

Trên MySQL 8.0.14+, dùng LEFT JOIN LATERAL lấy hai đơn gần nhất theo từng khách hàng. Tạo index phù hợp và xem EXPLAIN ANALYZE. Thử bỏ index để so sánh.

### Bài 8: Merge và materialization

Viết một derived table chỉ chọn cột từ customer và một derived table có GROUP BY. Dùng EXPLAIN FORMAT=TREE để quan sát sự khác biệt. Thử hint MERGE/NO_MERGE khi phù hợp và ghi nhận optimizer có áp dụng hay không.

### Bài 9: Lọc và giới hạn

Tạo derived table chọn 10 đơn mới nhất bằng ORDER BY/LIMIT. Truy vấn ngoài tiếp tục lọc hoặc sắp xếp. Kiểm tra vị trí ORDER BY và giải thích vì sao thứ tự cuối cần được khai báo ở query block ngoài.

## 19. Checklist trước khi đưa derived table vào ứng dụng

- [ ] Mọi derived table đều có alias.
- [ ] Các cột được xuất từ truy vấn con đủ cho bước bên ngoài.
- [ ] Tên cột trong derived table không trùng nhau.
- [ ] Alias bảng và cột có ý nghĩa rõ ràng.
- [ ] Đã hiểu phạm vi alias theo từng query block.
- [ ] Đã kiểm tra số hàng mà derived table trả về cho mỗi khóa.
- [ ] Đã tránh fan-out khi JOIN nhiều nguồn một-nhiều.
- [ ] Đã xác định điều kiện phù hợp nằm ở ON hay WHERE.
- [ ] Đã dùng LATERAL chỉ khi cần tham chiếu bảng đứng trước và server hỗ trợ.
- [ ] Đã đặt ORDER BY ở truy vấn ngoài nếu cần thứ tự kết quả cuối.
- [ ] Đã dùng tie-breaker duy nhất khi LIMIT hoặc top-N.
- [ ] Đã chọn derived table hoặc CTE theo độ phức tạp và khả năng tái sử dụng.
- [ ] Đã xem merge/materialization và derived condition pushdown bằng EXPLAIN.
- [ ] Đã lọc sớm, giảm cột và đánh giá index của bảng cơ sở.
- [ ] Đã kiểm thử trường hợp rỗng, NULL, nhiều hàng đồng hạng và không có quan hệ.

## 20. Kết luận

Derived table là truy vấn con trong FROM, được đặt tên bằng alias và cung cấp một tập hàng cho truy vấn bên ngoài. Nó giúp tổ chức SQL thành các bước rõ ràng: lọc, tổng hợp, phân loại, JOIN và xếp hạng. Alias của derived table là bắt buộc; truy vấn ngoài chỉ nhìn thấy những cột được xuất ra từ truy vấn con.

Khi thiết kế, hãy kiểm soát phạm vi alias, đặt tên cột duy nhất, xác định cardinality trước khi JOIN và không dựa vào thứ tự của truy vấn con để bảo đảm thứ tự cuối. MySQL có thể merge derived table hoặc materialize kết quả; LATERAL cho phép tham chiếu bảng đứng trước từ MySQL 8.0.14. Hãy chọn cấu trúc theo mục tiêu đọc hiểu, sau đó kiểm tra EXPLAIN và dữ liệu thực tế để đánh giá hiệu năng.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Derived Tables](https://dev.mysql.com/doc/refman/8.4/en/derived-tables.html)
- [MySQL 8.4 Reference Manual – Lateral Derived Tables](https://dev.mysql.com/doc/refman/8.4/en/lateral-derived-tables.html)
- [MySQL 8.4 Reference Manual – Optimizing Derived Tables, View References, and CTEs](https://dev.mysql.com/doc/refman/8.4/en/derived-table-optimization.html)
- [MySQL 8.4 Reference Manual – Derived Condition Pushdown Optimization](https://dev.mysql.com/doc/refman/8.4/en/derived-condition-pushdown-optimization.html)
- [MySQL 8.4 Reference Manual – WITH (Common Table Expressions)](https://dev.mysql.com/doc/refman/8.4/en/with.html)
- [MySQL 8.4 Reference Manual – Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html)
- [MySQL 8.4 Reference Manual – JOIN Clause](https://dev.mysql.com/doc/refman/8.4/en/join.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizer Hints](https://dev.mysql.com/doc/refman/8.4/en/optimizer-hints.html)

