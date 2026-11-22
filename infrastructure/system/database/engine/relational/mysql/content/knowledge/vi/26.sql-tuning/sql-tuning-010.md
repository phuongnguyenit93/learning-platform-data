# Tránh N+1, truy vấn lặp và số lần trao đổi mạng quá lớn

Một endpoint có thể chỉ trả về vài chục đơn hàng nhưng lại gửi hàng trăm câu SQL đến MySQL. Nguyên nhân thường gặp là ứng dụng tải danh sách bản ghi cha bằng một truy vấn, sau đó chạy thêm một truy vấn cho từng bản ghi để lấy dữ liệu liên quan. Mẫu này gọi là **N+1 query problem**: một truy vấn ban đầu cộng thêm N truy vấn lặp.

N+1 không chỉ làm tăng số câu SQL. Mỗi lần gọi database còn có chi phí gửi request, chờ mạng, parse/execute, lấy kết quả và chuyển dữ liệu về ứng dụng. Khi nhiều request cùng chạy, các truy vấn nhỏ lặp lại còn chiếm connection pool, tăng tải server và kéo dài thời gian giữ transaction. Cách xử lý thường là dùng `JOIN`, batch loading với `IN`, truy vấn tổng hợp, cache có phạm vi phù hợp hoặc batch ghi dữ liệu.

## Mục tiêu

Sau bài học, bạn có thể:

- Nhận biết N+1 và các dạng truy vấn lặp trong ORM hoặc tầng dịch vụ.
- Chọn giữa `JOIN`, batch loading và truy vấn tổng hợp theo hình dạng dữ liệu.
- Tránh lỗi phân trang khi join quan hệ một-nhiều.
- Giảm round trip khi đọc và ghi nhiều bản ghi.
- Dùng batch có kích thước hợp lý, prepared statement và index phù hợp.
- Đo số truy vấn, số hàng đọc, lượng dữ liệu trả về và độ trễ theo request.
- Giữ tính nhất quán khi thay một truy vấn lớn bằng nhiều truy vấn batch.

Các ví dụ giả định MySQL 8.0, InnoDB và ứng dụng sử dụng prepared statement. Tên hàm bind parameter có thể khác nhau tùy driver/ORM.

## 1. N+1 query problem là gì?

Giả sử hệ thống có hai bảng:

```sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    KEY ix_orders_customer_created
        (customer_id, created_at, order_id)
) ENGINE = InnoDB;

CREATE TABLE order_items (
    item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    KEY ix_order_items_order (order_id)
) ENGINE = InnoDB;
```

Ứng dụng cần hiển thị 50 đơn hàng gần nhất cùng danh sách sản phẩm trong mỗi đơn. Một cách triển khai ngây thơ:

```sql
-- Truy vấn 1: lấy 50 đơn hàng.
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

-- Với từng order_id, ứng dụng lại chạy:
SELECT item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id = ?;
```

Nếu có 50 đơn hàng, ứng dụng gửi tổng cộng 51 truy vấn: một truy vấn cha và 50 truy vấn con. Nếu mỗi truy vấn con mất trung bình 3 ms thời gian round trip, riêng phần chờ tuần tự có thể xấp xỉ 150 ms, chưa tính thời gian xử lý SQL và chuyển dữ liệu. Khi N tăng, chi phí tăng gần tuyến tính.

Mã ORM thường che giấu mẫu này bằng lazy loading:

```text
orders = queryOrders(customerId, limit=50)  // 1 query
for order in orders:
    order.items                         // 1 query cho mỗi order
```

Điểm đáng chú ý là dòng đọc `order.items` có vẻ đơn giản nhưng có thể kích hoạt một truy vấn mới. N+1 cũng có thể xuất hiện khi lặp qua khách hàng để tải địa chỉ, sản phẩm để tải danh mục, hoặc từng bản ghi để đếm số sự kiện liên quan.

## 2. Vì sao nhiều round trip lại đắt?

Một truy vấn database có nhiều thành phần chi phí:

1. Ứng dụng chuẩn bị câu lệnh và tham số.
2. Request đi qua driver, socket và mạng đến MySQL.
3. Server parse/execute hoặc tái sử dụng prepared statement, truy cập index/data page.
4. Kết quả được gửi về client và driver giải mã.
5. Ứng dụng chuyển dữ liệu thành object và tiếp tục xử lý.

Nhiều truy vấn nhỏ lặp lại làm các bước này xảy ra nhiều lần. Ngay cả khi mỗi câu `SELECT` chỉ đọc một hàng và chạy nhanh, tổng độ trễ vẫn có thể lớn do thời gian chờ mạng và chi phí cố định của mỗi lần gọi.

N+1 còn có thể gây ra:

- **Connection pool bị chiếm lâu:** request giữ connection trong khi chờ từng truy vấn.
- **Tải server tăng:** nhiều lần execute, lookup, ghi nhận Performance Schema và gửi kết quả.
- **Tính nhất quán khó dự đoán:** các truy vấn riêng có thể nhìn thấy dữ liệu ở những thời điểm khác nhau tùy transaction isolation.
- **Transaction dài hơn:** nếu tất cả truy vấn nằm trong một transaction, transaction có thể giữ snapshot hoặc khóa lâu hơn.
- **Payload dư thừa:** ứng dụng có thể tải cùng một đối tượng liên quan nhiều lần.

Không phải cứ giảm query count là tốt. Một câu SQL khổng lồ trả về hàng triệu dòng có thể tốn hơn vài truy vấn batch nhỏ. Mục tiêu là giảm round trip mà vẫn kiểm soát số hàng đọc, số byte trả về và chi phí xử lý.

## 3. Cách 1: dùng JOIN để lấy dữ liệu liên quan

Với quan hệ một đơn hàng có nhiều dòng chi tiết, có thể lấy dữ liệu bằng một câu lệnh:

```sql
SELECT o.order_id,
       o.created_at,
       o.status,
       o.total_amount,
       i.item_id,
       i.product_id,
       i.quantity,
       i.unit_price
FROM orders AS o
LEFT JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.customer_id = 42
ORDER BY o.created_at DESC,
         o.order_id DESC,
         i.item_id;
```

Ứng dụng nhận một tập kết quả. Các cột của đơn hàng lặp lại trên từng dòng chi tiết, nên tầng mapping cần gom các dòng theo `order_id` để dựng lại object cha và danh sách con.

Index `ix_orders_customer_created` hỗ trợ lọc và sắp xếp đơn hàng theo khách hàng; `ix_order_items_order` hỗ trợ tìm dòng chi tiết theo `order_id`. Cần kiểm tra kế hoạch bằng `EXPLAIN` với dữ liệu gần production.

### JOIN phù hợp khi nào?

- Dữ liệu liên quan cần dùng ngay trong cùng màn hình hoặc báo cáo.
- Số lượng hàng sau join có thể kiểm soát.
- Quan hệ và điều kiện join rõ ràng, có index phù hợp.
- Muốn một câu `SELECT` có snapshot nhất quán cho phần dữ liệu được đọc.

### Cẩn thận với nhân bản hàng cha

Trong quan hệ một-nhiều, mỗi đơn hàng xuất hiện một lần cho mỗi dòng `order_items`. Nếu một đơn có 5 mặt hàng, cột `total_amount` của đơn đó cũng xuất hiện 5 lần. Khi tính tổng sau join, có thể vô tình cộng trùng giá trị của bảng cha.

Ví dụ sau dễ cho kết quả sai:

```sql
SELECT o.customer_id,
       SUM(o.total_amount) AS customer_total
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.customer_id;
```

Mỗi đơn hàng bị lặp theo số dòng chi tiết, khiến `SUM(o.total_amount)` bị nhân lên. Nếu chỉ cần tổng đơn hàng, truy vấn trực tiếp bảng `orders`. Nếu cần tổng hợp cả hai cấp, hãy tổng hợp từng bảng trước rồi join các kết quả đã gom nhóm hoặc dùng truy vấn riêng.

## 4. Tránh lỗi phân trang khi JOIN một-nhiều

Không nên đặt `LIMIT 50` trực tiếp lên kết quả join nếu ý nghĩa cần lấy 50 đơn hàng. `LIMIT` sẽ giới hạn 50 dòng sau join, không phải 50 đơn hàng. Một đơn có nhiều item có thể chiếm phần lớn giới hạn và làm thiếu các đơn khác.

Hãy phân trang tập cha trước rồi mới join chi tiết:

```sql
WITH page_orders AS (
    SELECT order_id, customer_id, created_at, status, total_amount
    FROM orders
    WHERE customer_id = 42
    ORDER BY created_at DESC, order_id DESC
    LIMIT 50
)
SELECT p.order_id,
       p.created_at,
       p.status,
       p.total_amount,
       i.item_id,
       i.product_id,
       i.quantity,
       i.unit_price
FROM page_orders AS p
LEFT JOIN order_items AS i
  ON i.order_id = p.order_id
ORDER BY p.created_at DESC,
         p.order_id DESC,
         i.item_id;
```

CTE `page_orders` xác định đúng 50 đơn hàng trước khi join. Sau đó, mọi dòng chi tiết của 50 đơn đó được trả về. Cần nhớ số dòng cuối cùng có thể lớn hơn 50; ứng dụng nên có giới hạn hợp lý về số item hoặc dùng batch nếu một đơn có quá nhiều chi tiết.

Thứ tự phân trang cần có cột phân định duy nhất ở cuối `ORDER BY`, ở đây là `order_id`, để tránh thứ tự không ổn định khi nhiều đơn có cùng `created_at`.

## 5. Cách 2: batch loading bằng IN

Một lựa chọn khác là chạy một truy vấn lấy danh sách cha, rồi một truy vấn lấy tất cả con của các cha đó:

```sql
-- Query 1: lấy trang đơn hàng.
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

-- Query 2: lấy chi tiết của tất cả đơn trong trang.
SELECT order_id, item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id IN (?, ?, ?, ...)
ORDER BY order_id, item_id;
```

Ứng dụng thu thập 50 `order_id`, tạo danh sách placeholder và bind từng giá trị bằng prepared statement. Sau đó gom các item theo `order_id` trong bộ nhớ. Tổng số truy vấn vẫn là hai, bất kể trang có 5 hay 50 đơn.

### Vì sao IN thường tốt hơn N+1?

`IN` cho phép một câu lệnh tìm các hàng thuộc nhiều khóa. Với index trên `order_items(order_id)`, MySQL có thể tìm các vùng index tương ứng. Driver gửi một request và nhận kết quả của nhiều đơn hàng trong một lần trao đổi.

Không nối trực tiếp giá trị ID vào chuỗi SQL. Hãy tạo placeholder `?` tương ứng với số ID và bind tham số để tránh SQL injection và lỗi escape. Một số ORM có sẵn `select-in loading`, `prefetch_related`, `include` hoặc cơ chế batch loader tương tự.

### Chia batch khi danh sách quá lớn

Không nên tạo một `IN` list vô hạn. Batch quá lớn có thể làm câu SQL dài, tăng chi phí parse, sử dụng nhiều placeholder và trả về quá nhiều dữ liệu trong một lần. Hãy chia thành các nhóm có kích thước đo được, chẳng hạn 200-1000 khóa tùy kích thước hàng, độ trễ, driver và tải hệ thống.

```text
orderIds = [ ... 5000 IDs ... ]
for each chunk of 500 IDs:
    query order_items WHERE order_id IN (chunk)
    append/group results
```

Kích thước 500 chỉ là ví dụ để bắt đầu benchmark, không phải giới hạn cố định của MySQL. Hãy đo p95 latency, kích thước payload, số hàng và thời gian xử lý trong ứng dụng.

Nếu cần batch hàng chục nghìn hoặc hàng trăm nghìn khóa, cân nhắc đưa khóa vào temporary table hoặc staging table rồi join:

```sql
CREATE TEMPORARY TABLE requested_orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
) ENGINE = InnoDB;

INSERT INTO requested_orders (order_id)
VALUES (1001), (1002), (1003);

SELECT i.order_id, i.item_id, i.product_id, i.quantity
FROM requested_orders AS r
JOIN order_items AS i
  ON i.order_id = r.order_id
ORDER BY i.order_id, i.item_id;
```

Temporary table thuộc session, vì vậy các bước tạo, nạp và join phải dùng cùng connection. Với connection pool, cần bảo đảm dọn temporary table trước khi trả connection về pool hoặc dùng tên riêng và quy trình cleanup an toàn.

## 6. Cách 3: tổng hợp nhiều bản ghi trong một truy vấn

Một N+1 thường chỉ dùng từng truy vấn con để đếm hoặc tính tổng cho từng bản ghi cha. Thay vì chạy `COUNT(*)` N lần, hãy gom nhóm một lần:

```sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_spent,
       MAX(created_at) AS latest_order_at
FROM orders
WHERE customer_id IN (?, ?, ?, ...)
GROUP BY customer_id;
```

Nếu cần số lượng item cho từng đơn:

```sql
SELECT order_id,
       COUNT(*) AS item_count,
       SUM(quantity) AS total_quantity
FROM order_items
WHERE order_id IN (?, ?, ?, ...)
GROUP BY order_id;
```

Kết quả có tối đa một dòng cho mỗi khóa nhóm. Ứng dụng map kết quả vào object cha; nếu một khóa không có dòng kết quả, gán giá trị mặc định phù hợp như 0.

Không nên dùng correlated subquery một cách máy móc để thay N+1. Optimizer có thể biến đổi một số subquery, nhưng cần kiểm tra `EXPLAIN` và số hàng thực tế. Truy vấn `GROUP BY` rõ ràng thường giúp cả người đọc lẫn optimizer hiểu mục tiêu tổng hợp.

## 7. Cách 4: batch ghi và cập nhật nhiều hàng

N+1 không chỉ xảy ra khi đọc. Ứng dụng có thể chạy một `INSERT` cho từng dòng:

```sql
INSERT INTO order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES (1, 7001, 10, 2, 15.00);

INSERT INTO order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES (2, 7001, 11, 1, 25.00);
```

Với nhiều dòng, dùng multi-row insert:

```sql
INSERT INTO order_items
    (item_id, order_id, product_id, quantity, unit_price)
VALUES
    (?, ?, ?, ?, ?),
    (?, ?, ?, ?, ?),
    (?, ?, ?, ?, ?);
```

Batch insert giảm số lần round trip và chi phí execute. Hãy chia batch nếu payload lớn hoặc transaction giữ quá nhiều khóa. Bảo đảm xử lý lỗi duplicate key và kiểm tra số dòng thành công theo chính sách nghiệp vụ.

Để cập nhật nhiều hàng với các giá trị khác nhau, có thể dùng bảng staging rồi join:

```sql
CREATE TEMPORARY TABLE inventory_changes (
    product_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    quantity_delta INT NOT NULL
) ENGINE = InnoDB;

INSERT INTO inventory_changes (product_id, quantity_delta)
VALUES (10, -2), (11, 5), (12, -1);

UPDATE inventory AS i
JOIN inventory_changes AS c
  ON c.product_id = i.product_id
SET i.available = i.available + c.quantity_delta;
```

Nếu cần bảo đảm tồn kho không âm, thêm điều kiện phù hợp và kiểm tra số hàng bị ảnh hưởng; không dùng batch update này mà bỏ qua bất biến dữ liệu. Các thao tác staging và update cần chạy trong transaction phù hợp trên cùng connection.

## 8. DataLoader và cache theo request

Trong GraphQL hoặc tầng service, nhiều resolver có thể cùng yêu cầu một loại dữ liệu. **DataLoader pattern** gom các khóa được yêu cầu trong một khoảng thực thi thành một batch, truy vấn một lần và phân phối kết quả cho từng resolver.

Luồng khái niệm:

```text
Resolver A yêu cầu items(order 1) ---+
Resolver B yêu cầu items(order 2) ---+--> Batch loader
Resolver C yêu cầu items(order 3) ---+        |
                                              v
                                  SELECT ... WHERE order_id IN (...)
                                              |
                                              v
                              Map kết quả theo order_id
                                              |
                     +------------------------+------------------+
                     v                        v                  v
                  Resolver A              Resolver B          Resolver C
```

DataLoader thường có cache theo request để nếu nhiều resolver yêu cầu cùng một khóa, dữ liệu chỉ cần nạp một lần. Cache theo request có vòng đời ngắn và dễ kiểm soát hơn cache toàn cục. Nếu dùng cache dài hạn, cần chính sách invalidation, TTL và xử lý dữ liệu thay đổi.

Cache không thay thế batch loading cho các khóa khác nhau. Cũng không nên cache dữ liệu nhạy cảm hoặc dữ liệu thay đổi nhanh mà không xác định rõ quyền truy cập và độ mới.

## 9. Tính nhất quán khi chia một truy vấn thành nhiều batch

Một câu `SELECT` join thường đọc dữ liệu trong một statement snapshot. Nếu thay bằng hai hoặc nhiều truy vấn batch, dữ liệu có thể thay đổi giữa các lần đọc.

Ví dụ, truy vấn đầu lấy danh sách đơn hàng; trước khi truy vấn thứ hai lấy `order_items`, một transaction khác thêm hoặc xóa item. Kết quả dựng trong ứng dụng có thể phản ánh hai thời điểm khác nhau.

Nếu nghiệp vụ cần một snapshot nhất quán, có thể chạy các truy vấn đọc trong cùng transaction InnoDB ở mức `REPEATABLE READ`:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 50;

SELECT order_id, item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id IN (?, ?, ?, ...)
ORDER BY order_id, item_id;

COMMIT;
```

Hai câu `SELECT` thông thường dùng cùng read view. Hãy giữ transaction ngắn; không chờ người dùng hoặc gọi HTTP trong khi transaction mở. Nếu nghiệp vụ không yêu cầu snapshot thống nhất, có thể chấp nhận kết quả gần thời điểm hiện tại và tránh mở transaction dài.

Ở `READ COMMITTED`, mỗi consistent read có snapshot mới, nên hai câu lệnh trong cùng transaction có thể nhìn thấy các commit khác nhau. Chọn isolation level theo yêu cầu nghiệp vụ, không chỉ để giảm query count.

`SET SESSION TRANSACTION ISOLATION LEVEL` thay đổi cấu hình của connection hiện tại. Nếu ứng dụng dùng connection pool và thay đổi mức cô lập theo request, hãy khôi phục cấu hình chuẩn trước khi trả connection về pool hoặc quản lý mức cô lập tập trung trong cấu hình pool.

## 10. Chọn JOIN, batch hay tổng hợp?

| Tình huống | Chiến lược thường phù hợp | Lưu ý |
|---|---|---|
| Quan hệ một-một hoặc nhiều-một | `JOIN` | Tránh tải lại cùng dữ liệu liên quan |
| Một trang cha với nhiều hàng con | Batch `IN` hoặc join sau khi phân trang cha | Kiểm soát số hàng con và payload |
| Đếm/tổng hợp theo nhiều khóa cha | `GROUP BY` với `IN` hoặc join | Tránh cộng trùng do join một-nhiều |
| Ghi nhiều dòng cùng cấu trúc | Multi-row `INSERT` | Chia batch và xử lý lỗi từng batch |
| Cập nhật nhiều khóa với giá trị khác nhau | Staging table + `UPDATE JOIN` | Bảo vệ bất biến và transaction |
| Nhiều resolver cùng yêu cầu cùng loại dữ liệu | DataLoader/batch loader | Cache trong phạm vi request |
| Khóa đầu vào rất lớn | Temporary/staging table + join | Cùng session và cleanup rõ ràng |

Không có một chiến lược duy nhất tốt cho mọi trường hợp. `JOIN` giảm round trip nhưng có thể nhân bản dữ liệu cha; batch `IN` dễ map object nhưng cần nhiều hơn một statement; aggregate giảm payload nhưng không trả về chi tiết từng dòng.

## 11. Đo N+1 và truy vấn lặp

### Đo ở tầng ứng dụng

Gắn số truy vấn vào từng request hoặc transaction nghiệp vụ. Ghi nhận:

- Số câu SQL được thực thi.
- Digest hoặc fingerprint của câu SQL và số lần lặp.
- Tổng thời gian và p50/p95/p99.
- Số hàng trả về, số hàng đọc ước lượng và kích thước payload.
- Endpoint, resolver hoặc service tạo ra truy vấn.

Nếu một endpoint trả 50 đơn hàng mà có 51 câu SQL với cùng một mẫu `WHERE order_id = ?`, đó là dấu hiệu điển hình của N+1. Query count theo request giúp phát hiện chính xác hơn số liệu tổng hợp toàn server.

### Xem thống kê statement trong Performance Schema

MySQL tổng hợp các câu lệnh theo digest trong `performance_schema.events_statements_summary_by_digest`:

```sql
SELECT DIGEST_TEXT,
       COUNT_STAR,
       ROUND(SUM_TIMER_WAIT / 1000000000000, 3) AS total_seconds,
       ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS avg_seconds,
       SUM_ROWS_SENT,
       SUM_ROWS_EXAMINED
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY SUM_TIMER_WAIT DESC
LIMIT 20;
```

`COUNT_STAR` cho biết số lần thực thi của digest; `SUM_TIMER_WAIT` là tổng thời gian tính bằng picosecond trong bộ đếm. Một digest có số lần chạy rất lớn nhưng thời gian trung bình thấp vẫn có thể là ứng viên N+1. Đối chiếu `SUM_ROWS_SENT`, `SUM_ROWS_EXAMINED` và trace ứng dụng để biết nó thuộc endpoint nào.

Thống kê digest là số liệu tổng hợp theo server/schema, không tự chỉ ra request cụ thể gây ra truy vấn. Performance Schema có thể bị giới hạn dung lượng history và cấu hình instrument; hãy kiểm tra quyền truy cập và cấu hình trước khi kết luận.

### Dùng EXPLAIN cho từng truy vấn sau khi batch

Sau khi giảm N+1, vẫn cần kiểm tra câu SQL mới:

```sql
EXPLAIN
SELECT order_id, item_id, product_id, quantity, unit_price
FROM order_items
WHERE order_id IN (1001, 1002, 1003)
ORDER BY order_id, item_id;
```

Xác nhận index trên `order_id` được cân nhắc, số hàng ước lượng phù hợp và không đọc quá nhiều dữ liệu ngoài phạm vi. Khi cần số liệu thực tế, có thể dùng `EXPLAIN ANALYZE` trên môi trường phù hợp; lệnh này thực thi truy vấn.

## 12. Các sai lầm khi tối ưu N+1

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Thay N+1 bằng một JOIN không giới hạn | Kết quả có thể nhân bản hàng và tạo payload khổng lồ | Phân trang cha trước, giới hạn phạm vi và map quan hệ rõ ràng |
| Đặt LIMIT trên kết quả join một-nhiều | Nhận thiếu bản ghi cha hoặc thiếu item | Giới hạn parent trong CTE/subquery trước khi join |
| Dùng `SELECT *` cho mọi bảng | Trả nhiều cột không cần thiết | Chọn cột thực sự hiển thị hoặc xử lý |
| Tạo `IN` list quá lớn | SQL dài, parse và payload lớn | Chia batch hoặc dùng staging table |
| Ghép ID trực tiếp vào SQL | Nguy cơ SQL injection và lỗi định dạng | Dùng prepared statement và bind parameter |
| Dùng cache toàn cục không invalidation | Dữ liệu cũ hoặc rò rỉ giữa người dùng/tenant | Dùng cache theo request hoặc chính sách invalidation rõ ràng |
| Bỏ qua transaction khi cần snapshot | Dữ liệu cha/con có thể đến từ thời điểm khác nhau | Dùng transaction/isolation phù hợp và giữ ngắn |
| Chỉ nhìn query count | Một query khổng lồ vẫn có thể rất chậm | Đo rows, bytes, latency và CPU/I/O |

## 13. Quy trình xử lý một endpoint bị N+1

1. Ghi trace một request đại diện và đếm số câu SQL.
2. Gom các truy vấn theo digest; tìm mẫu câu lặp với tham số chỉ khác khóa.
3. Xác định quan hệ dữ liệu: một-một, nhiều-một, một-nhiều hay tổng hợp.
4. Chọn `JOIN`, batch `IN`, `GROUP BY` hoặc DataLoader theo hình dạng kết quả.
5. Nếu có phân trang, giới hạn tập cha trước khi join dữ liệu một-nhiều.
6. Kiểm tra index và `EXPLAIN` cho câu truy vấn mới.
7. So sánh số query, rows examined, rows sent, payload và p95 latency trước/sau.
8. Kiểm tra transaction/isolation nếu nhiều batch phải phản ánh cùng snapshot.
9. Chạy thử với kích thước trang và phân phối dữ liệu gần production; kiểm tra cả trường hợp một cha có rất nhiều con.
10. Theo dõi sau triển khai để xác nhận query count giảm mà tải database và ứng dụng không tăng ở nơi khác.

## 14. Bài thực hành

Với bảng `orders` và `order_items` ở phần 1:

1. Viết vòng lặp giả lập tải 50 đơn hàng rồi tải item theo từng `order_id`. Đếm số câu SQL và tính tổng thời gian round trip.
2. Viết lại bằng `LEFT JOIN`. Dựng lại danh sách item theo `order_id` và giải thích vì sao dữ liệu cột đơn hàng bị lặp.
3. Viết lại bằng hai truy vấn batch: một truy vấn lấy đơn hàng, một truy vấn lấy item với `IN`. So sánh query count và số byte trả về.
4. Thử đặt `LIMIT 50` trực tiếp trên join một-nhiều rồi so sánh với CTE phân trang đơn hàng trước khi join.
5. Viết truy vấn `GROUP BY order_id` để tính `item_count` và `total_quantity` cho toàn bộ đơn hàng trong trang.
6. Thêm 1.000 `order_id` vào batch. So sánh một `IN` list lớn với nhiều batch nhỏ và temporary table.
7. Chạy các batch đọc trong transaction `REPEATABLE READ`, sau đó thử `READ COMMITTED` với một session khác cập nhật item giữa hai câu đọc. Quan sát khác biệt snapshot.
8. Xem `events_statements_summary_by_digest`, tìm digest có `COUNT_STAR` cao và đối chiếu với trace request của ứng dụng.

## Ghi nhớ

- N+1 là một truy vấn lấy tập cha cộng thêm một truy vấn lặp cho mỗi bản ghi cha.
- `JOIN`, batch `IN`, `GROUP BY` và DataLoader giúp giảm round trip theo từng dạng quan hệ.
- Với quan hệ một-nhiều, hãy phân trang cha trước khi join và tránh cộng trùng dữ liệu cha.
- Chia batch theo kích thước đo được; dùng prepared statement và staging table khi danh sách khóa lớn.
- Nhiều truy vấn batch có thể nhìn thấy snapshot khác nhau; dùng transaction/isolation khi nghiệp vụ yêu cầu nhất quán.
- Đo query count theo request cùng latency, rows examined, rows sent và payload; không tối ưu chỉ dựa vào số câu SQL.
