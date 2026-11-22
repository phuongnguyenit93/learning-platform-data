# Ưu tiên SQL xử lý theo tập hợp trước khi dùng vòng lặp

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận diện bài toán có thể giải quyết bằng một câu SQL xử lý theo tập hợp.
- Thay vòng lặp đọc từng hàng bằng `UPDATE ... JOIN`, `INSERT ... SELECT`, `DELETE ... JOIN`, aggregate và biểu thức `CASE`.
- Dùng CTE, derived table và window function để biến đổi dữ liệu theo nhóm.
- Chọn cách chia batch khi một statement quá lớn hoặc giữ lock quá lâu.
- Giải thích khi nào cursor trong stored program thực sự cần thiết.
- Sử dụng đúng vòng đời `DECLARE`, `OPEN`, `FETCH`, `CLOSE` của cursor MySQL.
- Xử lý `NOT FOUND`, lỗi SQL và đóng cursor an toàn.
- Tránh các lỗi phổ biến như N+1 query, handler `NOT FOUND` bắt nhầm `SELECT INTO` và transaction kéo dài.
- Đo hiệu quả bằng execution plan, số hàng bị ảnh hưởng, lock và thời gian thực thi.

Bài học tập trung vào MySQL 8.0/8.4 và stored procedure. Các ví dụ dùng bảng minh họa; hãy điều chỉnh tên cột, kiểu dữ liệu và điều kiện nghiệp vụ theo schema thật.

## 1. Tư duy xử lý theo tập hợp

SQL được thiết kế để mô tả kết quả cần có trên một tập hàng. Bạn nêu điều kiện và phép biến đổi; optimizer quyết định cách đọc index, join, lọc, nhóm và ghi dữ liệu.

Ví dụ cần tăng giá 5% cho toàn bộ sản phẩm thuộc một danh mục:

```sql
UPDATE products
SET price = ROUND(price * 1.05, 2)
WHERE category_id = 12
  AND status = 'ACTIVE';
```

Một vòng lặp ở tầng ứng dụng thường phải:

1. SELECT danh sách sản phẩm.
2. Đọc từng hàng.
3. Tính giá mới ở ứng dụng.
4. Gửi một UPDATE cho từng sản phẩm.

Một câu `UPDATE` theo tập hợp diễn đạt toàn bộ công việc. MySQL có thể chọn kế hoạch truy cập phù hợp và thực hiện thao tác trong một statement.

### 1.1. Vì sao nên ưu tiên set-based SQL?

- **Ít round trip:** ứng dụng gửi ít câu lệnh hơn qua mạng.
- **Optimizer có tầm nhìn rộng:** MySQL có thể tối ưu join, filter, grouping và index trên toàn truy vấn.
- **Ít mã điều phối:** giảm trạng thái vòng lặp, biến tạm và nhánh lỗi ở ứng dụng.
- **Tính nhất quán rõ hơn:** một statement thường có ranh giới thực thi và lỗi dễ hiểu hơn nhiều statement rời rạc.
- **Dễ quan sát:** có thể dùng `EXPLAIN`, `EXPLAIN ANALYZE`, `ROW_COUNT()` và Performance Schema để đo.

Set-based không có nghĩa mọi thao tác đều rẻ hoặc luôn nhanh. Một câu UPDATE lớn có thể khóa nhiều hàng, tạo undo/redo lớn hoặc gây replication lag. Khi đó cần index, điều kiện lọc tốt hoặc chia batch; không mặc định chuyển sang cursor.

### 1.2. Câu hỏi đầu tiên trước khi viết loop

Hãy tự hỏi:

1. Có thể biểu diễn tập hàng cần xử lý bằng `WHERE` không?
2. Có thể nối dữ liệu nguồn bằng `JOIN` không?
3. Có thể tính kết quả bằng `CASE`, aggregate hoặc window function không?
4. Có thể ghi trực tiếp bằng `INSERT ... SELECT`, `UPDATE` hoặc `DELETE` không?
5. Có cần thứ tự xử lý từng hàng vì mỗi bước phụ thuộc kết quả bước trước không?
6. Có tác dụng phụ riêng cho từng hàng mà SQL không thể biểu diễn hợp lý không?

Chỉ khi câu trả lời cho các câu hỏi cuối cho thấy cần điều phối tuần tự, mới cân nhắc cursor hoặc vòng lặp ở ứng dụng.

## 2. Thay vòng lặp bằng UPDATE theo tập hợp

Giả sử bảng:

```sql
CREATE TABLE products (
    product_id BIGINT UNSIGNED NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    stock INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    stock_state VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_category_status (category_id, status)
) ENGINE = InnoDB;
```

### 2.1. Cập nhật cùng một quy tắc cho nhiều hàng

Thay vì lấy từng sản phẩm rồi cập nhật riêng:

```sql
UPDATE products
SET status = 'INACTIVE',
    updated_at = CURRENT_TIMESTAMP(6)
WHERE category_id = 12
  AND stock = 0
  AND status = 'ACTIVE';
```

Điều kiện lọc xác định tập hàng. Mỗi hàng trong tập được cập nhật theo cùng quy tắc.

### 2.2. Nhiều nhánh nghiệp vụ bằng CASE

Nếu từng hàng nhận giá trị khác nhau tùy điều kiện, không nhất thiết phải dùng IF trong loop:

```sql
UPDATE products
SET stock_state = CASE
        WHEN stock = 0 THEN 'OUT_OF_STOCK'
        WHEN stock < 10 THEN 'LOW_STOCK'
        ELSE 'AVAILABLE'
    END,
    updated_at = CURRENT_TIMESTAMP(6)
WHERE status = 'ACTIVE';
```

`CASE` đánh giá điều kiện cho từng hàng trong cùng statement. Hãy đặt các nhánh theo thứ tự ưu tiên: điều kiện cụ thể hơn nên đứng trước điều kiện tổng quát hơn.

### 2.3. Cập nhật từ bảng khác bằng UPDATE JOIN

Giả sử cần đồng bộ hạn mức của khách hàng từ bảng chính sách:

```sql
UPDATE customers AS c
JOIN customer_policies AS p
  ON p.policy_id = c.policy_id
SET c.credit_limit = p.credit_limit,
    c.updated_at = CURRENT_TIMESTAMP(6)
WHERE c.policy_id IS NOT NULL
  AND c.credit_limit <> p.credit_limit;
```

Một `UPDATE ... JOIN` thay cho việc đọc từng khách hàng, truy vấn chính sách tương ứng rồi UPDATE từng dòng.

Điều kiện `<>` bỏ qua các hàng không đổi để giảm ghi không cần thiết. Nếu cột có thể NULL, cần dùng điều kiện null-safe phù hợp, chẳng hạn `NOT (c.credit_limit <=> p.credit_limit)`.

### 2.4. Cập nhật từ kết quả aggregate

Giả sử bảng `orders` chứa tổng tiền đơn hàng. Cần cập nhật tổng doanh thu đã thanh toán theo khách hàng:

```sql
UPDATE customer_summary AS s
JOIN (
    SELECT
        customer_id,
        SUM(total_amount) AS paid_total
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS x
  ON x.customer_id = s.customer_id
SET s.paid_total = x.paid_total,
    s.updated_at = CURRENT_TIMESTAMP(6);
```

Derived table tính tổng theo khách hàng, sau đó JOIN để cập nhật summary. Nếu cần đặt tổng về 0 cho khách hàng không có đơn đã thanh toán, dùng `LEFT JOIN` từ bảng khách hàng/summary và `COALESCE`, đồng thời xác định rõ tập khách hàng cần đồng bộ.

### 2.5. Lưu ý khi UPDATE JOIN

- Điều kiện JOIN phải xác định đúng một giá trị nguồn cho mỗi hàng đích; nếu một hàng đích khớp nhiều hàng nguồn với giá trị khác nhau, kết quả có thể không như nghiệp vụ mong đợi.
- Tạo index cho cột JOIN và filter phù hợp.
- Kiểm tra số hàng bị ảnh hưởng trước khi chạy trên production.
- Với thao tác rủi ro, chạy SELECT cùng điều kiện JOIN để xem trước tập hàng.
- Không bỏ điều kiện tenant, phạm vi ngày hoặc trạng thái khi chuyển logic từ ứng dụng sang SQL.

## 3. Thay vòng lặp bằng INSERT ... SELECT

Nếu cần tạo bản ghi tổng hợp hoặc chuyển dữ liệu từ bảng nguồn sang bảng đích, dùng `INSERT ... SELECT`.

Ví dụ bảng báo cáo ngày:

```sql
CREATE TABLE daily_customer_sales (
    sales_date DATE NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(18,2) NOT NULL,
    PRIMARY KEY (sales_date, customer_id)
) ENGINE = InnoDB;
```

Tạo tổng hợp cho một ngày:

```sql
INSERT INTO daily_customer_sales (
    sales_date,
    customer_id,
    order_count,
    total_amount
)
SELECT
    DATE(created_at) AS sales_date,
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00'
GROUP BY DATE(created_at), customer_id;
```

Không cần vòng lặp theo từng khách hàng. MySQL nhóm dữ liệu và chèn kết quả trực tiếp.

### 3.1. Tránh xử lý trùng khi chạy lại

Nếu job có thể retry, cần xác định cách idempotent. Với bảng tổng hợp, có thể xóa phạm vi ngày rồi nạp lại trong một transaction phù hợp:

```sql
START TRANSACTION;

DELETE FROM daily_customer_sales
WHERE sales_date = '2026-11-01';

INSERT INTO daily_customer_sales (
    sales_date,
    customer_id,
    order_count,
    total_amount
)
SELECT
    DATE(created_at),
    customer_id,
    COUNT(*),
    SUM(total_amount)
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00'
GROUP BY DATE(created_at), customer_id;

COMMIT;
```

Nếu câu lệnh thất bại, ứng dụng xử lý lỗi và `ROLLBACK`. Cách này phù hợp khi phạm vi ngày đủ nhỏ và các bảng dùng transactional engine như InnoDB.

### 3.2. Upsert khi có khóa duy nhất

Nếu cần ghi đè hoặc cộng dồn trên khóa duy nhất, có thể dùng `INSERT ... ON DUPLICATE KEY UPDATE`. Cần thiết kế phép cập nhật để retry không cộng trùng. Ví dụ gán giá trị tổng mới có tính idempotent hơn việc cộng thêm cùng một tổng mỗi lần job chạy lại.

## 4. Thay vòng lặp bằng DELETE JOIN

Giả sử cần xóa các session đã hết hạn của người dùng bị khóa:

```sql
DELETE s
FROM user_sessions AS s
JOIN users AS u
  ON u.user_id = s.user_id
WHERE u.account_status = 'LOCKED'
  AND s.expires_at < CURRENT_TIMESTAMP;
```

`DELETE ... JOIN` chọn và xóa tập hàng đích bằng một statement. Trước khi chạy, có thể kiểm tra bằng SELECT:

```sql
SELECT s.session_id, s.user_id, s.expires_at
FROM user_sessions AS s
JOIN users AS u
  ON u.user_id = s.user_id
WHERE u.account_status = 'LOCKED'
  AND s.expires_at < CURRENT_TIMESTAMP;
```

Nếu cần xóa theo batch để giảm thời gian giữ lock, có thể giới hạn số hàng mỗi statement bằng `ORDER BY ... LIMIT` trong single-table DELETE, hoặc chọn khóa chính theo batch rồi xóa JOIN với tập khóa đó. Đừng chuyển sang cursor chỉ vì bảng có nhiều hàng.

## 5. Aggregate, CTE và window function thay vòng lặp tính toán

### 5.1. Aggregate thay bộ đếm trong loop

Không cần đọc từng đơn hàng để cộng doanh thu:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount,
    AVG(total_amount) AS average_order_amount
FROM orders
WHERE status = 'PAID'
GROUP BY customer_id;
```

`GROUP BY` thực hiện gom nhóm ở database. Nếu cần ghi kết quả, kết hợp với `INSERT ... SELECT` hoặc UPDATE JOIN.

### 5.2. CTE để tách các bước logic

CTE làm truy vấn nhiều bước dễ đọc mà không cần tạo biến cho từng hàng:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS paid_total
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id
), ranked_customers AS (
    SELECT
        customer_id,
        paid_total,
        DENSE_RANK() OVER (ORDER BY paid_total DESC) AS revenue_rank
    FROM customer_totals
)
SELECT customer_id, paid_total, revenue_rank
FROM ranked_customers
WHERE revenue_rank <= 10;
```

Truy vấn xếp hạng top khách hàng bằng window function thay cho việc duyệt từng khách hàng và duy trì thứ hạng trong biến ứng dụng.

### 5.3. Window function thay biến chạy

Ví dụ tính tổng lũy kế theo tài khoản:

```sql
SELECT
    account_id,
    entry_id,
    posted_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY account_id
        ORDER BY posted_at, entry_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_balance_change
FROM ledger_entries;
```

Thứ tự phải ổn định. `entry_id` là tie-breaker khi nhiều giao dịch có cùng `posted_at`.

### 5.4. UPDATE từ CTE hoặc derived result

Khi cần ghi trạng thái dựa trên xếp hạng, có thể dùng CTE trước UPDATE trên MySQL 8.0:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS salary_position
    FROM employees
)
UPDATE employees AS e
JOIN ranked AS r
  ON r.employee_id = e.employee_id
SET e.salary_band = CASE
        WHEN r.salary_position = 1 THEN 'TOP'
        WHEN r.salary_position <= 3 THEN 'HIGH'
        ELSE 'STANDARD'
    END;
```

Hãy kiểm tra cú pháp trên phiên bản MySQL mục tiêu và đánh giá execution plan khi tập dữ liệu lớn.

## 6. N+1 query: vòng lặp thường nằm ở tầng ứng dụng

Một dạng lặp phổ biến không dùng cursor SQL mà xuất hiện trong code ứng dụng:

1. SELECT 100 khách hàng.
2. Với từng khách hàng, chạy một SELECT lấy đơn hàng.
3. Với từng đơn hàng, chạy thêm SELECT lấy chi tiết.

Nếu có 100 khách hàng, số round trip có thể tăng lên hàng trăm. Đây là vấn đề N+1 query.

Có thể thay bằng JOIN:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
WHERE c.tenant_id = ?
ORDER BY c.customer_id, o.created_at DESC, o.order_id DESC;
```

Hoặc lấy hai tập dữ liệu theo batch và ghép ở ứng dụng nếu JOIN làm nhân số hàng quá lớn hoặc các aggregate cần xử lý riêng. Điểm quan trọng là giảm round trip và tránh truy vấn lặp theo từng ID.

## 7. Chia batch khi set-based statement quá lớn

Một statement set-based có thể xử lý hàng triệu bản ghi. Dù ít round trip, nó vẫn có thể giữ lock lâu, tạo nhiều undo/redo, tăng replication lag hoặc gây áp lực lên buffer pool.

Chia batch là cách giữ set-based SQL trong từng phần nhỏ.

### 7.1. Mẫu UPDATE theo batch

Ví dụ mỗi lần cập nhật tối đa 1.000 đơn hàng cũ:

```sql
UPDATE orders
SET archive_candidate = 1
WHERE archive_candidate = 0
  AND created_at < '2025-01-01 00:00:00'
ORDER BY order_id
LIMIT 1000;
```

Ứng dụng hoặc job điều phối lặp lại statement này trong các transaction ngắn:

1. `START TRANSACTION`.
2. Chạy UPDATE batch.
3. Lấy số hàng thay đổi bằng `ROW_COUNT()` ngay sau UPDATE.
4. `COMMIT`.
5. Nếu số hàng bằng 0, kết thúc; nếu chưa, chạy batch tiếp theo.

Mỗi batch commit riêng giúp nhả lock và giới hạn lượng undo. Điều kiện `archive_candidate = 0` làm cho hàng đã xử lý không bị chọn lại. Cần bảo đảm không có tiến trình khác liên tục thêm hàng thỏa điều kiện khiến job chạy mãi.

### 7.2. Vì sao không dùng OFFSET để chia batch?

`LIMIT 1000 OFFSET 500000` vẫn phải bỏ qua nhiều hàng. Với bảng lớn, hãy dùng khóa tiếp nối hoặc một điều kiện khóa chính có index:

```sql
SELECT order_id
FROM orders
WHERE order_id > ?
  AND created_at < '2025-01-01 00:00:00'
ORDER BY order_id
LIMIT 1000;
```

Ứng dụng lưu `last_order_id` từ batch đã xử lý và dùng nó cho batch tiếp theo. Nếu cần xử lý đồng thời nhiều worker, phải có cơ chế claim batch an toàn, ví dụ trạng thái claim, khóa hàng hoặc chiến lược phân vùng khóa; không chỉ chia cùng một cursor cho nhiều worker.

### 7.3. Chọn kích thước batch bằng đo lường

Batch quá nhỏ làm tăng round trip và chi phí commit. Batch quá lớn giữ lock lâu và tạo áp lực I/O. Bắt đầu với kích thước vừa phải, đo thời gian, số hàng, lock wait, redo/undo và replication lag rồi điều chỉnh.

### 7.4. Bảo đảm tính nhất quán khi batch qua nhiều transaction

Nhiều batch commit riêng không tạo một snapshot duy nhất cho toàn bộ công việc. Dữ liệu mới có thể xuất hiện giữa các batch; hàng có thể thay đổi điều kiện lọc. Cần xác định:

- Có chốt phạm vi bằng high-water mark không?
- Hàng mới được thêm trong lúc chạy có thuộc job hiện tại không?
- Nếu một batch thất bại, chạy lại có an toàn không?
- Có lưu checkpoint để tiếp tục không?
- Có cần idempotency key hoặc bảng job progress không?

## 8. Khi nào vòng lặp thực sự cần thiết?

Vòng lặp phù hợp khi quy trình có phụ thuộc tuần tự hoặc điều phối từng phần tử mà không thể biểu diễn hợp lý bằng một câu SQL.

Ví dụ:

- Mỗi đối tượng cần gọi một stored procedure chuyên biệt với quy tắc nhiều bước khác nhau.
- Thuật toán phân bổ có trạng thái còn lại sau mỗi lần cấp phát và thứ tự xử lý là một phần nghiệp vụ.
- Cần dừng sớm theo điều kiện phụ thuộc kết quả của hàng trước.
- Một bước cần xử lý lỗi riêng theo từng phần tử và ghi nhận kết quả thành công/thất bại độc lập.
- Cần tương tác với tài nguyên ngoài database; trường hợp này thường phù hợp với vòng lặp ở ứng dụng hơn là giữ cursor và transaction trong MySQL.

Trước khi chọn cursor, hãy kiểm tra xem window function, recursive CTE, bảng staging, queue có trạng thái hoặc batch keyset có giải quyết được bài toán đơn giản hơn không.

### 8.1. Cursor không phải cách thay thế mặc định cho SELECT

Cursor đọc từng hàng từ result set để stored program xử lý. Mỗi lần `FETCH` đưa giá trị vào biến cục bộ; logic tiếp theo chạy theo từng hàng.

Cursor có thể hữu ích, nhưng thường có thêm:

- Trạng thái cursor và handler kết thúc.
- Mã điều khiển `OPEN`, `FETCH`, `CLOSE`.
- Chi phí xử lý từng hàng.
- Rủi ro giữ transaction/lock lâu nếu logic đọc và ghi kéo dài.
- Áp lực bộ nhớ hoặc temporary table nếu result set lớn.

Nếu một `UPDATE JOIN` hoặc `INSERT ... SELECT` diễn đạt được cùng nghiệp vụ, hãy ưu tiên statement đó.

## 9. Đặc điểm cursor trong MySQL

Cursor trong stored program MySQL có ba đặc tính quan trọng:

- **Asensitive:** server có thể dùng bản sao nội bộ của result set; ứng dụng không nên dựa vào việc thay đổi bảng nền sẽ làm thay đổi các hàng đang duyệt.
- **Read-only:** không dùng cursor để cập nhật trực tiếp hàng hiện tại theo cú pháp positioned update.
- **Nonscrollable:** chỉ `FETCH` tiến về phía trước; không nhảy lùi hoặc di chuyển đến vị trí tùy ý.

MySQL cursor được dùng trong stored program. Cursor được khai báo cho một câu SELECT; không phải cursor client-side tùy ý có thể cuộn hoặc cập nhật.

### 9.1. Vòng đời cursor

```text
DECLARE cursor
      |
      v
    OPEN
      |
      v
    FETCH -----> xử lý hàng
      |              |
      |              +----> FETCH tiếp
      v
   NOT FOUND
      |
      v
    CLOSE
```

Các bước:

1. `DECLARE CURSOR FOR SELECT ...` khai báo truy vấn cursor.
2. `OPEN cursor_name` thực thi truy vấn và mở cursor.
3. `FETCH cursor_name INTO ...` lấy hàng kế tiếp vào biến.
4. Khi không còn hàng, MySQL phát condition `NOT FOUND` với SQLSTATE class `02`.
5. `CLOSE cursor_name` giải phóng cursor.

### 9.2. Quy tắc thứ tự DECLARE

Trong một block `BEGIN ... END`, thứ tự khai báo là:

1. Biến cục bộ và condition.
2. Cursor.
3. Handler.

Ví dụ:

```sql
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_customer_id BIGINT UNSIGNED;

    DECLARE cur_customers CURSOR FOR
        SELECT customer_id
        FROM customers
        WHERE account_status = 'REVIEW'
        ORDER BY customer_id;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    -- OPEN, FETCH, CLOSE ở phần thân block
END;
```

Không đặt `DECLARE CURSOR` sau một câu lệnh thực thi hoặc sau handler trong cùng block.

### 9.3. SELECT cursor nên có thứ tự ổn định

Nếu logic yêu cầu xử lý theo thứ tự, câu SELECT phải có `ORDER BY` với tie-breaker duy nhất:

```sql
SELECT account_id
FROM accounts
WHERE needs_review = 1
ORDER BY priority DESC, account_id ASC;
```

Không dựa vào thứ tự vật lý của hàng hoặc thứ tự index ngẫu nhiên. Nếu thứ tự không phải yêu cầu nghiệp vụ, vẫn nên có thứ tự ổn định để việc kiểm thử và khôi phục dễ dự đoán.

## 10. Ví dụ cursor có handler và cleanup

Giả sử mỗi tài khoản cần chạy một stored procedure riêng `sp_reconcile_one_account`. Routine con chứa logic nghiệp vụ đã được tách riêng. Ví dụ sau minh họa vòng đời cursor và xử lý lỗi; nó không phải gợi ý thay một UPDATE JOIN đơn giản bằng cursor.

```sql
DELIMITER $$

CREATE PROCEDURE sp_process_reconciliation_batch(
    IN p_batch_limit INT
)
BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_cursor_open BOOLEAN DEFAULT FALSE;
    DECLARE v_account_id BIGINT UNSIGNED;

    DECLARE cur_accounts CURSOR FOR
        SELECT account_id
        FROM accounts
        WHERE needs_reconciliation = 1
        ORDER BY account_id
        LIMIT p_batch_limit;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_done = TRUE;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        IF v_cursor_open THEN
            CLOSE cur_accounts;
        END IF;
        RESIGNAL;
    END;

    IF p_batch_limit IS NULL OR p_batch_limit < 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'p_batch_limit must be greater than zero';
    END IF;

    OPEN cur_accounts;
    SET v_cursor_open = TRUE;

    read_loop: LOOP
        FETCH cur_accounts INTO v_account_id;

        IF v_done THEN
            LEAVE read_loop;
        END IF;

        CALL sp_reconcile_one_account(v_account_id);
    END LOOP;

    CLOSE cur_accounts;
    SET v_cursor_open = FALSE;
END$$

DELIMITER ;
```

Các điểm cần hiểu:

- `v_done` bắt tín hiệu hết result set.
- `v_cursor_open` cho phép handler biết cursor đã mở để đóng khi có lỗi.
- `EXIT HANDLER FOR SQLEXCEPTION` cleanup cursor rồi `RESIGNAL` để caller nhận lỗi gốc.
- `LIMIT p_batch_limit` giới hạn số hàng được đưa vào batch cursor.
- `ORDER BY account_id` làm thứ tự ổn định.
- Routine con cần có hợp đồng rõ ràng về transaction và lỗi; không nên tự commit nếu caller đang sở hữu transaction.

### 10.1. Transaction do caller sở hữu

Procedure ở trên không tự `START TRANSACTION`, `COMMIT` hoặc `ROLLBACK`. Caller quyết định ranh giới transaction:

```sql
START TRANSACTION;
CALL sp_process_reconciliation_batch(100);
COMMIT;
```

Nếu `CALL` báo lỗi, caller cần `ROLLBACK` thay vì COMMIT. Ứng dụng nên dùng cấu trúc try/catch/finally để rollback khi procedure thất bại và trả connection về pool ở trạng thái sạch.

Không thêm `START TRANSACTION` tùy tiện bên trong procedure đang được gọi khi transaction của caller còn mở. Bắt đầu transaction mới có thể kết thúc transaction đang hoạt động bằng implicit commit. Hãy chọn rõ một bên sở hữu transaction.

### 10.2. Nếu cần transaction theo từng batch

Procedure ví dụ giữ transaction do caller mở trong toàn bộ batch. Với khối lượng lớn, có thể cần commit sau mỗi batch để nhả lock. Khi đó, ứng dụng/job scheduler nên điều phối từng batch bằng keyset hoặc trạng thái claim và mở transaction mới cho mỗi batch.

Đừng chỉ đặt `COMMIT` bên trong vòng lặp mà không thống nhất hợp đồng với caller. Việc đó có thể commit cả công việc khác của caller trên cùng connection.

## 11. NOT FOUND và lỗi SELECT ... INTO

`NOT FOUND` không chỉ xuất hiện khi cursor hết hàng. Nó còn xuất hiện khi một câu `SELECT ... INTO` không trả hàng.

Đây là nguồn lỗi phổ biến:

```sql
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_done = TRUE;
```

Nếu cùng block vừa FETCH cursor vừa thực hiện `SELECT ... INTO`, một truy vấn phụ không có kết quả có thể đặt `v_done = TRUE`. Vòng lặp sẽ kết thúc dù cursor vẫn còn hàng.

### 11.1. Cách an toàn: dùng block lồng với handler riêng

```sql
read_loop: LOOP
    FETCH cur_customers INTO v_customer_id;

    IF v_done THEN
        LEAVE read_loop;
    END IF;

    BEGIN
        DECLARE v_missing BOOLEAN DEFAULT FALSE;
        DECLARE v_customer_name VARCHAR(160);
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_missing = TRUE;

        SELECT customer_name
          INTO v_customer_name
          FROM customers
         WHERE customer_id = v_customer_id;

        IF v_missing THEN
            -- Xử lý trường hợp không còn bản ghi phù hợp.
            SET v_customer_name = NULL;
        END IF;
    END;

    -- Tiếp tục xử lý hàng cursor hiện tại.
END LOOP;
```

Handler trong block con chỉ xử lý `NOT FOUND` của truy vấn phụ. Handler cursor ở block ngoài vẫn quản lý việc FETCH hết hàng.

### 11.2. Cách tốt hơn nếu có thể: đưa dữ liệu vào SELECT cursor

Nếu cursor cần tên khách hàng, hãy JOIN ngay trong câu SELECT:

```sql
DECLARE cur_customers CURSOR FOR
    SELECT c.customer_id, c.customer_name
    FROM customers AS c
    WHERE c.account_status = 'REVIEW'
    ORDER BY c.customer_id;
```

Sau đó FETCH cả hai cột. Cách này giảm truy vấn lặp cho từng hàng và tránh handler phụ.

## 12. Đóng cursor và xử lý exception

Cursor cần được đóng khi xử lý bình thường và khi có lỗi.

### 12.1. Đóng bình thường

```sql
OPEN cur_customers;

read_loop: LOOP
    FETCH cur_customers INTO v_customer_id;
    IF v_done THEN
        LEAVE read_loop;
    END IF;

    -- Xử lý hàng hiện tại.
END LOOP;

CLOSE cur_customers;
```

### 12.2. Đóng khi có lỗi

Nếu routine có thể phát sinh SQL exception sau khi mở cursor, dùng EXIT handler để cleanup:

```sql
DECLARE EXIT HANDLER FOR SQLEXCEPTION
BEGIN
    IF v_cursor_open THEN
        CLOSE cur_customers;
    END IF;
    RESIGNAL;
END;
```

Đặt `v_cursor_open = TRUE` ngay sau OPEN thành công và đặt lại FALSE sau CLOSE. Nếu OPEN thất bại, handler không cố đóng cursor chưa mở.

### 12.3. RESIGNAL giữ nguyên lỗi cho caller

`RESIGNAL` phát lại condition đang được handler xử lý. Nếu handler chỉ ghi log rồi nuốt lỗi, caller có thể tưởng batch thành công dù một phần công việc thất bại.

Nếu cần ghi log lỗi, hãy thiết kế bảng log, transaction và quy tắc lỗi rõ ràng. Một INSERT log trong cùng transaction sẽ bị rollback cùng dữ liệu nghiệp vụ; nếu cần log tồn tại sau rollback, phải cân nhắc cơ chế ghi nhận riêng và tác động tới replication.

## 13. Transaction, lock và cursor dài

Cursor không tự động tạo transaction riêng. Nó hoạt động trong session và transaction context hiện tại.

Nếu mở transaction rồi duyệt hàng nghìn hoặc hàng triệu bản ghi, transaction có thể kéo dài và gây:

- Lock được giữ lâu nếu routine có UPDATE/DELETE.
- Undo history tăng và purge bị chậm.
- Lock wait hoặc deadlock khi các transaction khác xử lý cùng dữ liệu.
- Replica lag nếu batch ghi nhiều thay đổi.
- Tài nguyên temporary table tăng do cursor result set.

### 13.1. Tách đọc và ghi có chủ đích

Nếu cursor chỉ đọc danh sách ID rồi gọi procedure ghi từng ID, cần xác định dữ liệu có thể thay đổi giữa thời điểm mở cursor và thời điểm xử lý hay không.

Cursor là asensitive; không dựa vào việc các hàng nguồn thay đổi sẽ tự cập nhật danh sách cursor đang mở. Nếu cần xác minh lại trạng thái trước khi ghi, routine con phải kiểm tra điều kiện hiện tại và xử lý trường hợp hàng đã bị thay đổi hoặc xóa.

### 13.2. Chọn isolation level theo yêu cầu

Không nâng isolation level chỉ để “làm cursor an toàn”. Hãy xác định cần snapshot nhất quán, khóa hàng để claim công việc hay chỉ cần xử lý các hàng còn đủ điều kiện tại thời điểm UPDATE.

Với job nhiều worker, có thể dùng queue table với trạng thái `READY`, `PROCESSING`, `DONE`, lease/timeout và khóa claim. Việc claim phải atomic để hai worker không xử lý cùng một hàng ngoài ý muốn.

### 13.3. Ưu tiên batch ngắn

Nếu nghiệp vụ cho phép, xử lý mỗi batch trong transaction ngắn, commit và lưu checkpoint. Cursor mở cho cả một tập lớn thường không phải cách tốt để triển khai job dài hạn.

## 14. Index và execution plan vẫn quan trọng với set-based SQL

Set-based SQL không tự động nhanh nếu thiếu index hoặc điều kiện không sargable.

Ví dụ truy vấn:

```sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-12-01 00:00:00';
```

Index có thể phù hợp:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
```

Thứ tự cột phụ thuộc workload thực tế. Hai cột equality filter thường đứng trước range column, nhưng cần xem độ chọn lọc, truy vấn khác và chi phí ghi.

### 14.1. Tránh bọc cột lọc bằng hàm khi không cần

Điều kiện:

```sql
WHERE DATE(created_at) = '2026-11-01'
```

có thể làm giảm khả năng dùng range access trên index `created_at`. Dùng khoảng thời gian nửa mở:

```sql
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-11-02 00:00:00'
```

### 14.2. Kiểm tra EXPLAIN

```sql
EXPLAIN FORMAT=JSON
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = 1001
  AND status = 'PAID'
  AND created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-12-01 00:00:00';
```

Kiểm tra index được chọn, ước lượng hàng, filter, join order và filesort. Với truy vấn SELECT có thể chạy an toàn trên môi trường phù hợp, dùng `EXPLAIN ANALYZE` để so sánh ước lượng với số liệu thực tế; lệnh này thực sự thực thi truy vấn.

### 14.3. Đo cả statement và workload

Khi so sánh cursor với set-based:

- Đo thời gian end-to-end, không chỉ thời gian SQL server.
- Đếm số round trip và số statement.
- Đo số hàng đọc/ghi và số hàng thay đổi.
- Kiểm tra lock wait, deadlock và replication lag.
- Đo mức sử dụng CPU, I/O, temporary table và memory.
- Dùng dữ liệu có phân bố gần production.

## 15. Các mẫu nên tránh

### 15.1. SELECT rồi UPDATE từng hàng

Mẫu kém hiệu quả:

```text
SELECT id, value FROM source_rows;
FOR EACH row:
    new_value = calculate(row.value)
    UPDATE target_rows SET value = new_value WHERE id = row.id;
```

Nếu phép tính có thể biểu diễn bằng SQL, dùng UPDATE JOIN hoặc CASE.

### 15.2. Cursor chỉ để đếm hoặc cộng tổng

Không duyệt từng hàng để tăng biến đếm hoặc cộng tiền. Dùng `COUNT(*)`, `SUM()`, `GROUP BY` hoặc window function.

### 15.3. Cursor chỉ để copy hàng

Không FETCH rồi INSERT từng hàng nếu có thể dùng `INSERT INTO target (...) SELECT ... FROM source ...`.

### 15.4. Cursor để xóa theo điều kiện

Không FETCH ID rồi DELETE từng hàng nếu có thể dùng `DELETE ... WHERE` hoặc `DELETE ... JOIN`.

### 15.5. Loop không có điều kiện dừng rõ ràng

Mọi loop cần có điều kiện kết thúc có thể chứng minh. Với cursor, kiểm tra `v_done` ngay sau FETCH trước khi dùng biến được FETCH.

### 15.6. Nuốt exception

Handler rỗng hoặc chỉ đặt cờ rồi tiếp tục có thể làm routine báo thành công dù dữ liệu chỉ được xử lý một phần. Chỉ tiếp tục khi đã định nghĩa rõ loại lỗi có thể bỏ qua và cách ghi nhận.

## 16. Bảng quyết định: SQL set-based, batch hay cursor?

| Nhu cầu | Lựa chọn ưu tiên | Lý do |
|---|---|---|
| Cập nhật nhiều hàng cùng quy tắc | `UPDATE ... WHERE` | Một statement xử lý toàn tập |
| Cập nhật theo dữ liệu bảng khác | `UPDATE ... JOIN` | Tránh SELECT/UPDATE từng hàng |
| Tạo dữ liệu tổng hợp | `INSERT ... SELECT` + `GROUP BY` | Database nhóm và ghi trực tiếp |
| Xóa theo quan hệ | `DELETE ... JOIN` | Không cần loop ID |
| Tính thứ hạng hoặc tổng lũy kế | Window function | Xử lý thứ tự theo partition |
| Tập dữ liệu quá lớn cho một transaction | Batch set-based với checkpoint | Giới hạn lock và undo |
| Mỗi hàng cần quy trình tuần tự phụ thuộc hàng trước | Cursor hoặc loop có kiểm soát | Có trạng thái tuần tự thật sự |
| Cần gọi dịch vụ ngoài cho từng hàng | Vòng lặp ở ứng dụng/worker | Không giữ cursor và transaction DB trong lúc chờ mạng |
| Cần xử lý đồng thời nhiều worker | Queue/claim theo batch | Phân phối công việc an toàn và có thể phục hồi |

## 17. Thực hành: chuyển một loop thành set-based SQL

### 17.1. Bài toán

Mỗi đêm, hệ thống cần đặt `review_required = 1` cho khách hàng có ít nhất ba đơn hàng bị hoàn tiền trong 90 ngày gần nhất.

### 17.2. Cách tiếp cận bằng vòng lặp

Một cách làm chưa tối ưu là SELECT từng khách hàng, đếm số đơn refund bằng một truy vấn riêng rồi UPDATE từng khách hàng. Cách này tạo nhiều round trip và truy vấn lặp.

### 17.3. Cách set-based

```sql
UPDATE customers AS c
JOIN (
    SELECT customer_id
    FROM orders
    WHERE status = 'REFUNDED'
      AND refunded_at >= CURRENT_DATE - INTERVAL 90 DAY
    GROUP BY customer_id
    HAVING COUNT(*) >= 3
) AS r
  ON r.customer_id = c.customer_id
SET c.review_required = 1,
    c.updated_at = CURRENT_TIMESTAMP(6)
WHERE c.review_required = 0;
```

Truy vấn con tìm khách hàng đủ điều kiện. UPDATE JOIN cập nhật toàn bộ tập kết quả. Nếu cần gỡ cờ cho khách hàng không còn đủ điều kiện, phải định nghĩa rõ quy tắc reset và viết một statement riêng hoặc đồng bộ cả tập bằng LEFT JOIN.

### 17.4. Kiểm tra trước khi chạy

```sql
SELECT
    customer_id,
    COUNT(*) AS refund_count
FROM orders
WHERE status = 'REFUNDED'
  AND refunded_at >= CURRENT_DATE - INTERVAL 90 DAY
GROUP BY customer_id
HAVING COUNT(*) >= 3;
```

Đối chiếu danh sách với nghiệp vụ, kiểm tra index và số lượng khách hàng dự kiến. Sau khi chạy UPDATE, ghi nhận số hàng thay đổi và thời gian thực thi.

## 18. Checklist trước khi dùng cursor

- [ ] Đã thử biểu diễn bài toán bằng `UPDATE`, `INSERT ... SELECT` hoặc `DELETE`.
- [ ] Đã xem xét JOIN, aggregate, CTE, `CASE` và window function.
- [ ] Đã xác định lý do cần xử lý tuần tự theo từng hàng.
- [ ] Đã giới hạn số hàng cursor đọc; không mở cursor không giới hạn trên tập rất lớn nếu không cần.
- [ ] Câu SELECT cursor có filter và `ORDER BY` ổn định khi thứ tự quan trọng.
- [ ] Đã khai báo biến/condition, cursor và handler đúng thứ tự.
- [ ] Có `NOT FOUND` handler và kiểm tra cờ ngay sau FETCH.
- [ ] Đã xem xét `SELECT ... INTO` có thể kích hoạt cùng handler `NOT FOUND` hay không.
- [ ] Có EXIT handler đóng cursor khi SQL exception xảy ra.
- [ ] Có `RESIGNAL` nếu caller cần biết thao tác thất bại.
- [ ] Transaction owner được xác định rõ giữa caller và procedure.
- [ ] Batch và checkpoint hỗ trợ retry an toàn.
- [ ] Đã kiểm tra index, execution plan, lock và replication lag.
- [ ] Đã thử trên dữ liệu gần production và đo end-to-end.

## 19. Kết luận

SQL set-based cho phép mô tả thao tác trên cả tập hàng để MySQL tối ưu filter, join, aggregate và ghi dữ liệu. Trước khi viết loop, hãy kiểm tra xem `UPDATE ... JOIN`, `INSERT ... SELECT`, `DELETE ... JOIN`, `CASE`, CTE hoặc window function có diễn đạt được nghiệp vụ hay không. Nếu một statement quá lớn, chia thành batch set-based với transaction ngắn và checkpoint.

Cursor chỉ nên xuất hiện khi cần điều phối tuần tự thực sự. Trong MySQL, cursor là asensitive, read-only và nonscrollable; vòng đời gồm `DECLARE`, `OPEN`, `FETCH`, `CLOSE`. Handler `NOT FOUND` phải được đặt đúng scope vì nó cũng có thể bắt trường hợp `SELECT ... INTO` không có hàng. Khi có exception, đóng cursor và `RESIGNAL`; đồng thời xác định rõ ai sở hữu transaction. Hãy dùng execution plan và số liệu workload để xác minh lựa chọn.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Cursors](https://dev.mysql.com/doc/refman/8.4/en/cursors.html)
- [MySQL 8.4 Reference Manual: DECLARE Statement](https://dev.mysql.com/doc/refman/8.4/en/declare.html)
- [MySQL 8.4 Reference Manual: FETCH Statement](https://dev.mysql.com/doc/refman/8.4/en/fetch.html)
- [MySQL 8.4 Reference Manual: Condition Handling](https://dev.mysql.com/doc/refman/8.4/en/condition-handling.html)
- [MySQL 8.4 Reference Manual: UPDATE Statement](https://dev.mysql.com/doc/refman/8.4/en/update.html)
- [MySQL 8.4 Reference Manual: INSERT ... SELECT Statement](https://dev.mysql.com/doc/refman/8.4/en/insert-select.html)
- [MySQL 8.4 Reference Manual: EXPLAIN Statement](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
