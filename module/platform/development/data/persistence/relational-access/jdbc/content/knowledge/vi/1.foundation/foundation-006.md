# Các kiến thức SQL và giao dịch cần có trước khi học JDBC

**JDBC (Java Database Connectivity)** là API Java dùng để kết nối và làm việc với cơ sở dữ liệu quan hệ. Để sử dụng `Connection`, `PreparedStatement` và `ResultSet` hiệu quả, người học cần hiểu dữ liệu được tổ chức như thế nào, câu SQL thực hiện công việc gì và lúc nào thay đổi dữ liệu được xác nhận hoặc hoàn tác.

Trong chương **Nền tảng**, bài này hệ thống hóa các kiến thức SQL và giao dịch cần dùng khi viết chương trình JDBC. Các ví dụ SQL minh họa cú pháp phổ biến; giữa PostgreSQL, MySQL, SQL Server, Oracle, H2 và các hệ quản trị khác có thể có khác biệt về kiểu dữ liệu, từ khóa và hành vi giao dịch.

## 1. Cơ sở dữ liệu quan hệ: bảng, dòng, cột và khóa

Một **bảng** (*table*) tập hợp các dòng (*row*) có cùng cấu trúc. Mỗi **cột** (*column*) có tên và kiểu dữ liệu. Chẳng hạn, hệ thống bán hàng lưu khách hàng trong bảng `customers` và đơn hàng trong bảng `orders`.

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Bảng | Tập hợp các bản ghi cùng cấu trúc | `customers` |
| Dòng | Một bản ghi cụ thể | Khách hàng có mã `1` |
| Cột | Thuộc tính của bản ghi | `email` |
| Kiểu dữ liệu | Miền giá trị có thể lưu | `BIGINT`, `VARCHAR`, `DECIMAL`, `TIMESTAMP` |
| Khóa chính (PK) | Định danh duy nhất từng dòng | `customers.customer_id` |
| Khóa ngoại (FK) | Tham chiếu đến khóa của bảng khác | `orders.customer_id` |
| Ràng buộc | Quy tắc bảo vệ tính hợp lệ dữ liệu | `NOT NULL`, `UNIQUE`, `CHECK` |

Ví dụ tạo hai bảng (DDL):

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(255) UNIQUE
);

CREATE TABLE orders (
    order_id     BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL CHECK (total_amount >= 0),
    status       VARCHAR(20) NOT NULL DEFAULT 'NEW',
    created_at   TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_customers
        FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
```

Đây là quan hệ **một khách hàng – nhiều đơn hàng**: một `customers.customer_id` có thể xuất hiện ở nhiều dòng `orders`, nhưng mỗi `orders.customer_id` phải tham chiếu khách hàng hợp lệ.

Một số điểm cần biết trước khi thao tác từ Java:

- `BIGINT` thường dùng cho ID số nguyên lớn; `VARCHAR(n)` lưu chuỗi có độ dài giới hạn; `DECIMAL(p, s)` phù hợp với giá trị tiền cần độ chính xác thập phân.
- `PRIMARY KEY` không chấp nhận giá trị trùng và không được `NULL`; `FOREIGN KEY` giúp bảo đảm tính toàn vẹn tham chiếu.
- `NOT NULL` yêu cầu có giá trị, `UNIQUE` hạn chế giá trị trùng, còn `CHECK` kiểm tra điều kiện. Cách xử lý `NULL` trong `UNIQUE` và hỗ trợ một số ràng buộc có thể khác nhau giữa các DBMS.
- `DEFAULT 'NEW'` được áp dụng khi lệnh chèn bỏ qua cột `status`. Nó không đồng nghĩa việc chủ động truyền giá trị `NULL`.
- `TIMESTAMP` là kiểu thời gian của SQL. Cách biểu diễn múi giờ phụ thuộc kiểu cụ thể và DBMS; khi sang Java cần chọn kiểu ngày giờ phù hợp.

> Trong ứng dụng thật, ID thường được sinh bằng identity, sequence hoặc cơ chế khác của DBMS. Ví dụ dùng ID nhập tường minh để tập trung vào cách đọc SQL.

## 2. Bốn nhóm lệnh SQL thường gặp

| Nhóm | Mục đích | Ví dụ |
|---|---|---|
| DDL (*Data Definition Language*) | Định nghĩa hoặc thay đổi cấu trúc | `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` |
| DML (*Data Manipulation Language*) | Thêm, sửa, xóa dữ liệu | `INSERT`, `UPDATE`, `DELETE` |
| Truy vấn dữ liệu | Đọc dữ liệu từ bảng | `SELECT` |
| Điều khiển giao dịch | Xác nhận hoặc hoàn tác thay đổi | `COMMIT`, `ROLLBACK`, `SAVEPOINT` |

Một số tài liệu xếp `SELECT` vào DQL (*Data Query Language*) và tách DCL (*Data Control Language*) cho `GRANT`/`REVOKE`. Đây là cách phân nhóm để học, không thay đổi cú pháp mà JDBC gửi đến cơ sở dữ liệu.

### 2.1. INSERT – thêm dòng

```sql
INSERT INTO customers (customer_id, full_name, email)
VALUES (1, 'Lan Nguyen', 'lan@example.test');

INSERT INTO customers (customer_id, full_name, email)
VALUES (2, 'Minh Tran', 'minh@example.test');

INSERT INTO orders (order_id, customer_id, total_amount, status, created_at)
VALUES (101, 1, 250000.00, 'NEW', CURRENT_TIMESTAMP);

INSERT INTO orders (order_id, customer_id, total_amount, status, created_at)
VALUES (102, 1, 125000.00, 'PAID', CURRENT_TIMESTAMP);
```

Nên nêu **danh sách cột** trong `INSERT`. Điều này giúp câu lệnh ít phụ thuộc vào thứ tự cột của bảng và dễ kiểm tra khi schema thay đổi.

### 2.2. SELECT – đọc và lọc dữ liệu

```sql
SELECT order_id, total_amount, status
FROM orders
WHERE customer_id = 1
  AND total_amount >= 100000.00
ORDER BY total_amount DESC, order_id ASC;
```

Các thành phần:

- `SELECT` chọn những cột cần lấy, tránh `SELECT *` khi ứng dụng chỉ cần vài trường.
- `FROM` xác định bảng hoặc nguồn dữ liệu.
- `WHERE` lọc từng dòng bằng điều kiện.
- `ORDER BY` xác định thứ tự trả về. **Nếu thiếu `ORDER BY`, không có bảo đảm về thứ tự dòng.**

Các toán tử phổ biến là `=`, `<>`, `>`, `>=`, `<`, `<=`, `AND`, `OR`, `NOT`, `IN`, `BETWEEN` và `LIKE`. Khi kết hợp `AND` và `OR`, nên dùng ngoặc để biểu đạt rõ ý định.

### 2.3. UPDATE – thay đổi dòng hiện có

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 101
  AND status = 'NEW';
```

Điều kiện `WHERE` giới hạn tập dòng bị sửa. Trong JDBC, `executeUpdate()` trả về số dòng chịu tác động, giúp nhận biết thao tác có tìm thấy bản ghi và đáp ứng điều kiện mong đợi hay không.

**Đặc biệt cẩn thận:** `UPDATE orders SET status = 'PAID'` không có `WHERE` sẽ tác động đến tất cả dòng mà DBMS cho phép cập nhật.

### 2.4. DELETE – xóa dòng

```sql
DELETE FROM orders
WHERE order_id = 102;
```

Không có `WHERE`, lệnh `DELETE FROM orders` cố gắng xóa mọi dòng của bảng. Ràng buộc khóa ngoại có thể ngăn một lệnh `DELETE`; cơ chế `ON DELETE CASCADE` nếu được định nghĩa có thể khiến các dòng liên quan cũng bị xóa.

## 3. JOIN, tổng hợp dữ liệu và NULL

### 3.1. JOIN nối dữ liệu giữa các bảng

```sql
SELECT o.order_id,
       c.full_name,
       o.total_amount,
       o.status
FROM orders AS o
INNER JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'PAID';
```

`INNER JOIN` chỉ trả về những cặp dòng khớp điều kiện nối. `LEFT JOIN` giữ mọi dòng ở phía trái, kể cả khi phía phải không có dòng khớp:

```sql
SELECT c.customer_id,
       c.full_name,
       o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id;
```

Với khách hàng chưa có đơn, các cột lấy từ `orders` có thể là `NULL`. Nếu mỗi khách hàng có nhiều đơn, kết quả `JOIN` có thể có nhiều dòng cho một khách hàng; đây không phải là bản ghi bị nhân đôi trong bảng gốc.

### 3.2. GROUP BY và HAVING

Muốn tính tổng tiền đơn hàng của từng khách hàng:

```sql
SELECT c.customer_id,
       c.full_name,
       COUNT(o.order_id) AS order_count,
       COALESCE(SUM(o.total_amount), 0) AS total_spent
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
HAVING COUNT(o.order_id) >= 1;
```

- `COUNT(o.order_id)` đếm các dòng có mã đơn không `NULL`, khác với `COUNT(*)` khi dùng `LEFT JOIN`.
- `SUM`, `AVG`, `MIN`, `MAX` là các hàm tổng hợp thông dụng.
- `GROUP BY` tạo nhóm; `HAVING` lọc sau khi tổng hợp, còn `WHERE` lọc dòng trước khi tổng hợp.
- `COALESCE(SUM(...), 0)` thay kết quả tổng rỗng bằng 0. Ở ví dụ có `HAVING`, khách hàng không có đơn bị loại khỏi kết quả.

### 3.3. NULL không phải 0 hoặc chuỗi rỗng

`NULL` biểu thị giá trị thiếu hoặc chưa xác định. Không dùng phép so sánh `= NULL` để tìm dòng:

```sql
-- Đúng: tìm khách hàng chưa có địa chỉ email.
SELECT customer_id, full_name
FROM customers
WHERE email IS NULL;

-- Đúng: tìm khách hàng đã có email.
SELECT customer_id, full_name
FROM customers
WHERE email IS NOT NULL;
```

SQL dùng **logic ba giá trị**: `TRUE`, `FALSE`, `UNKNOWN`. Khi so sánh với `NULL` bằng các toán tử như `=` hoặc `<>`, kết quả thường là `UNKNOWN`; `WHERE` chỉ giữ những dòng có điều kiện đánh giá thành `TRUE`. Điều này ảnh hưởng đến truy vấn, nhất là khi có `NOT` hoặc `NOT IN`.

Khi đọc dữ liệu qua JDBC, một cột SQL `NULL` thường được ánh xạ thành `null` khi dùng `ResultSet.getObject(...)`; với getter trả về kiểu nguyên thủy như `getInt(...)`, cần kiểm tra `wasNull()` nếu muốn phân biệt SQL `NULL` với số 0.

## 4. Kiểu dữ liệu và ràng buộc cần chú ý

| Kiểu SQL điển hình | Dữ liệu thường lưu | Java thường dùng |
|---|---|---|
| `INTEGER` / `BIGINT` | ID, số lượng | `int` / `long` hoặc wrapper nếu cho phép `NULL` |
| `VARCHAR` / `CHAR` | Tên, mã, email | `String` |
| `DECIMAL(p, s)` | Giá tiền, số cần độ chính xác thập phân | `BigDecimal` |
| `BOOLEAN` | Giá trị đúng/sai | `boolean` / `Boolean` |
| `DATE` | Ngày không kèm giờ | `LocalDate` |
| `TIME` | Giờ trong ngày | `LocalTime` |
| `TIMESTAMP` | Ngày giờ | `LocalDateTime` hoặc kiểu có offset phù hợp |
| `BLOB` / kiểu nhị phân | Dữ liệu nhị phân | `byte[]`, `InputStream` |

Đây là ánh xạ gợi ý, không phải quy tắc áp dụng cho mọi driver. Ví dụ, các loại timestamp có hay không có thông tin múi giờ cần được xử lý đúng với DBMS và ngữ nghĩa dữ liệu của hệ thống.

**Tính toàn vẹn dữ liệu** nên được bảo vệ cả trong Java lẫn tại cơ sở dữ liệu: ứng dụng kiểm tra đầu vào để trả lỗi rõ ràng, còn `PRIMARY KEY`/`FOREIGN KEY`/`CHECK`/`UNIQUE` giúp phòng ngừa trạng thái không hợp lệ kể cả khi có nhiều ứng dụng cùng ghi.

Chỉ mục (**index**) giúp tăng tốc các truy vấn phù hợp, nhất là các điều kiện `WHERE` và `JOIN`; tuy nhiên chỉ mục cũng tốn dung lượng và làm tăng công việc của thao tác ghi. Không suy luận rằng mọi điều kiện lọc đều tự động nhanh: hiệu năng còn phụ thuộc thống kê, kích thước bảng và kế hoạch thực thi của DBMS.

## 5. Transaction là gì?

**Giao dịch** (*transaction*) là một đơn vị công việc gồm một hay nhiều câu SQL cần được quản lý cùng nhau. Thao tác **`COMMIT`** xác nhận thay đổi trong giao dịch; **`ROLLBACK`** yêu cầu hoàn tác những thay đổi chưa được commit.

Ví dụ chuyển 100.000 đồng từ tài khoản A sang B phải thực hiện cả hai bước:

1. Trừ 100.000 khỏi số dư A.
2. Cộng 100.000 vào số dư B.

Nếu bước trừ thành công nhưng bước cộng thất bại, ứng dụng phải hoàn tác bước trừ. Hai câu `UPDATE` cần nằm trong **cùng một transaction** và dùng cùng kết nối giao dịch.

```text
Giao dịch bắt đầu
    |
    +-- UPDATE accounts: trừ tiền A
    |
    +-- UPDATE accounts: cộng tiền B
    |
    +-- Cả hai thành công? ---- Có ---> COMMIT
                    |
                   Không
                    |
                 ROLLBACK
```

Một cách mô tả luồng SQL là:

```sql
-- Cú pháp bắt đầu transaction có thể khác nhau theo DBMS.
BEGIN;

UPDATE accounts
SET balance = balance - 100000.00
WHERE account_id = 1
  AND balance >= 100000.00;

UPDATE accounts
SET balance = balance + 100000.00
WHERE account_id = 2;

COMMIT;
```

**Chưa nên dùng trực tiếp đoạn SQL này trong nghiệp vụ thực tế:** cần kiểm tra số dòng thay đổi của **cả hai** lệnh, bảo đảm tài khoản tồn tại, và `ROLLBACK` nếu bất kỳ bước nào thất bại. `BEGIN` là cú pháp thường gặp; JDBC có cách điều khiển giao dịch bằng `Connection` phù hợp hơn cho mã Java.

### 5.1. Bốn tính chất ACID

| Tính chất | Ý nghĩa thực hành |
|---|---|
| **Atomicity** (nguyên tử) | Các thay đổi của transaction cùng thành công hoặc cùng được hoàn tác theo ranh giới giao dịch. |
| **Consistency** (nhất quán) | Giao dịch phải đưa dữ liệu từ trạng thái hợp lệ này sang trạng thái hợp lệ khác, theo những ràng buộc và quy tắc đã định nghĩa. |
| **Isolation** (cô lập) | Các transaction đồng thời nhìn thấy và tác động lên nhau theo mức cô lập do hệ quản trị cung cấp. |
| **Durability** (bền vững) | Thay đổi đã commit được hệ quản trị bảo toàn theo cam kết độ bền của hệ thống. |

ACID không tự động chứng minh rằng mọi quy tắc nghiệp vụ đều được kiểm tra đúng. Chẳng hạn, nếu ứng dụng quên kiểm tra số dư không âm thì tính nguyên tử vẫn có thể được bảo đảm, nhưng dữ liệu có thể không thỏa yêu cầu nghiệp vụ.

### 5.2. Auto-commit và ranh giới giao dịch trong JDBC

Theo mặc định JDBC, kết nối mới thường ở chế độ **auto-commit**: mỗi câu SQL riêng lẻ được commit khi hoàn tất theo quy tắc của JDBC và driver. Muốn nhóm nhiều thao tác trong cùng giao dịch, ứng dụng tắt auto-commit:

```java
connection.setAutoCommit(false);

try {
    // Thực hiện các câu SQL cần thành công cùng nhau.
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
```

Khi bật auto-commit, việc gọi từng `UPDATE` riêng lẻ không tạo ra giao dịch bao trùm hai lệnh. Khi tắt auto-commit, phải có đường kết thúc rõ ràng: `commit()` hoặc `rollback()`, kể cả lúc phát sinh ngoại lệ.

**Không bật lại auto-commit trước khi kết thúc transaction:** theo hợp đồng JDBC, thay đổi `setAutoCommit(...)` từ `false` sang `true` trong lúc giao dịch đang hoạt động có thể khiến giao dịch được commit.

## 6. Isolation: các transaction đồng thời thấy gì?

Nhiều người dùng có thể đọc và cập nhật cùng bảng cùng thời điểm. Nếu không quản lý đồng thời hợp lý, ứng dụng dễ gặp các tình huống sau:

- **Dirty read:** transaction A đọc thay đổi chưa commit của B; sau đó B rollback nên dữ liệu A đã đọc chưa từng được xác nhận.
- **Non-repeatable read:** trong một transaction, A đọc lại cùng một dòng và thấy giá trị khác vì transaction khác đã commit thay đổi.
- **Phantom read:** trong một transaction, A chạy lại truy vấn theo điều kiện và thấy tập dòng khác do transaction khác đã thêm, xóa hoặc thay đổi các dòng phù hợp.
- **Lost update:** hai luồng cùng đọc một giá trị cũ rồi ghi đè thay đổi của nhau vì không có cơ chế kiểm soát xung đột phù hợp.

SQL và JDBC thường đề cập bốn mức cô lập sau (hành vi thực tế tùy DBMS):

| Isolation level | Bảo đảm cốt lõi và điều cần nhớ |
|---|---|
| `READ_UNCOMMITTED` | Mức yếu nhất theo mô hình chuẩn; có thể cho phép dirty read. Một số DBMS không thực sự cung cấp dirty read dù chọn mức này. |
| `READ_COMMITTED` | Không đọc dữ liệu chưa commit; giá trị có thể đổi khi đọc lại và có thể xuất hiện phantom. |
| `REPEATABLE_READ` | Ngăn non-repeatable read theo ngữ nghĩa chuẩn; cách xử lý phantom và xung đột ghi khác nhau giữa các DBMS. |
| `SERIALIZABLE` | Yêu cầu kết quả thực thi tương đương một thứ tự chạy tuần tự hợp lệ; có thể phải chờ, deadlock hoặc báo lỗi để ứng dụng thử lại. |

Chọn isolation cao hơn có thể thay đổi mức độ tranh chấp và thông lượng, nhưng không có một mức tối ưu cho mọi hệ thống. Phải xét nghiệp vụ, loại truy vấn, hỗ trợ thực tế của DBMS và cách xử lý retry.

JDBC cung cấp các hằng:

```java
Connection.TRANSACTION_READ_UNCOMMITTED
Connection.TRANSACTION_READ_COMMITTED
Connection.TRANSACTION_REPEATABLE_READ
Connection.TRANSACTION_SERIALIZABLE
```

Kiểm tra và thiết lập mức cô lập trên kết nối:

```java
int currentLevel = connection.getTransactionIsolation();
boolean supported = connection.getMetaData().supportsTransactionIsolationLevel(
        Connection.TRANSACTION_READ_COMMITTED);

if (supported) {
    // Thiết lập trước khi thực thi các câu SQL của transaction.
    connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
}
```

Việc thay đổi isolation giữa lúc transaction đang hoạt động có thể bị từ chối hoặc có tác động đặc thù theo DBMS; nên thiết lập trước khi bắt đầu công việc trong transaction, và khi dùng connection pool cần thống nhất cách phục hồi cấu hình.

## 7. Khóa, ghi đồng thời và kiểm soát mất cập nhật

Hệ quản trị dùng khóa và/hoặc cơ chế đa phiên bản (*MVCC*) để điều phối truy cập đồng thời. Khóa không chỉ xuất hiện khi ứng dụng viết `SELECT ... FOR UPDATE`; ngay cả `UPDATE` và `DELETE` cũng có thể giữ khóa cho đến khi transaction kết thúc, tùy DBMS.

Một tình huống dễ sai:

1. Giao dịch A đọc số lượng tồn kho = 10.
2. Giao dịch B cũng đọc = 10.
3. A tính và ghi 9.
4. B tính và ghi 8 hoặc 9 dựa trên số cũ.

Cách an toàn hơn trong nhiều trường hợp là để cơ sở dữ liệu thực hiện phép trừ có điều kiện ngay trong `UPDATE`:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity >= 1;
```

Ứng dụng phải kiểm tra **số dòng được cập nhật**. Nếu bằng 0, sản phẩm không tồn tại hoặc không còn đủ hàng; không được coi là đặt hàng thành công.

Với **optimistic locking**, bảng có thể có cột `version`, và lệnh cập nhật dùng cả phiên bản đã đọc:

```sql
UPDATE inventory
SET quantity = ?, version = version + 1
WHERE product_id = ?
  AND version = ?;
```

Nếu có giao dịch khác đã thay đổi phiên bản, lệnh có thể trả về 0 dòng; ứng dụng cần đọc lại dữ liệu và quyết định retry hoặc báo xung đột. Với **pessimistic locking**, ứng dụng yêu cầu khóa trước khi sửa, nhưng cú pháp và hành vi như `SELECT ... FOR UPDATE` khác nhau giữa các DBMS.

Giữ giao dịch ngắn, truy cập tài nguyên theo thứ tự nhất quán và xử lý được lỗi deadlock/timeout giúp hạn chế tranh chấp. Không giữ một transaction mở trong lúc chờ người dùng nhập liệu hoặc gọi dịch vụ bên ngoài kéo dài.

## 8. Liên hệ SQL với API JDBC

| Nhu cầu trong SQL | Công cụ JDBC thường dùng |
|---|---|
| Mở phiên làm việc với DB | `DataSource.getConnection()` hoặc `DriverManager.getConnection(...)` |
| Chạy `SELECT` có tham số | `PreparedStatement.executeQuery()` và `ResultSet` |
| Chạy `INSERT`/`UPDATE`/`DELETE` | `PreparedStatement.executeUpdate()` |
| Chạy câu SQL khác, không biết trước dạng kết quả | `Statement.execute()` / `PreparedStatement.execute()` |
| Truyền giá trị động vào SQL | `PreparedStatement.setLong(...)`, `setString(...)`, `setBigDecimal(...)`... |
| Điều khiển transaction | `Connection.setAutoCommit(false)`, `commit()`, `rollback()` |
| Chọn isolation | `Connection.setTransactionIsolation(...)` |
| Giải phóng tài nguyên | `try-with-resources` cho `Connection`, `Statement`, `ResultSet` |

### 8.1. Dùng PreparedStatement để truyền tham số

Ví dụ lấy đơn hàng của một khách hàng, chỉ lấy những đơn có tổng tiền đạt mức tối thiểu:

```java
String sql = """
        SELECT order_id, total_amount, status
        FROM orders
        WHERE customer_id = ? AND total_amount >= ?
        ORDER BY order_id
        """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);
    statement.setBigDecimal(2, new BigDecimal("100000.00"));

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long id = result.getLong("order_id");
            BigDecimal amount = result.getBigDecimal("total_amount");
            String status = result.getString("status");
            System.out.printf("Đơn %d, tiền %s, trạng thái %s%n",
                    id, amount, status);
        }
    }
}
```

Đoạn mã dùng Java 15+ cho text block và giả định đã có `DataSource dataSource`, biến `long customerId`, cùng các import `java.sql.*` và `java.math.BigDecimal`. Với Java cũ hơn, có thể nối chuỗi SQL thông thường.

**Vì sao không nối chuỗi giá trị vào SQL?** Xây dựng truy vấn từ chuỗi nhập của người dùng dễ tạo lỗ hổng SQL injection và gây lỗi escape, định dạng ngày giờ hoặc số. `?` là vị trí tham số cho **giá trị**, không thay thế trực tiếp tên bảng/cột hoặc từ khóa SQL.

### 8.2. Ví dụ transaction JDBC đầy đủ: chuyển tiền

Giả sử có bảng:

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance    DECIMAL(18, 2) NOT NULL CHECK (balance >= 0)
);
```

Ví dụ sau thực hiện hai câu `UPDATE` trong **một transaction**, kiểm tra số dòng của từng bước và hoàn tác toàn bộ nếu có lỗi:

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class MoneyTransferExample {

    public static void transfer(DataSource dataSource,
                                long fromId,
                                long toId,
                                BigDecimal amount) throws SQLException {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Thông tin chuyển tiền không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            boolean transactionFinished = false;

            try {
                connection.setAutoCommit(false);

                try {
                    int debited;
                    try (PreparedStatement statement = connection.prepareStatement(
                            "UPDATE accounts "
                          + "SET balance = balance - ? "
                          + "WHERE account_id = ? AND balance >= ?")) {
                        statement.setBigDecimal(1, amount);
                        statement.setLong(2, fromId);
                        statement.setBigDecimal(3, amount);
                        debited = statement.executeUpdate();
                    }
                    if (debited != 1) {
                        throw new SQLException("Tài khoản nguồn không tồn tại hoặc thiếu tiền");
                    }

                    int credited;
                    try (PreparedStatement statement = connection.prepareStatement(
                            "UPDATE accounts "
                          + "SET balance = balance + ? "
                          + "WHERE account_id = ?")) {
                        statement.setBigDecimal(1, amount);
                        statement.setLong(2, toId);
                        credited = statement.executeUpdate();
                    }
                    if (credited != 1) {
                        throw new SQLException("Tài khoản đích không tồn tại");
                    }

                    connection.commit();
                    transactionFinished = true;
                } catch (SQLException | RuntimeException error) {
                    try {
                        connection.rollback();
                        transactionFinished = true;
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }
                    throw error;
                }
            } finally {
                // Chỉ phục hồi auto-commit sau commit/rollback thành công.
                // Bật auto-commit quá sớm có thể commit phần việc còn dở.
                if (transactionFinished) {
                    connection.setAutoCommit(originalAutoCommit);
                }
            }
        }
    }
}
```

Điều cần quan sát trong ví dụ:

1. Cả hai `UPDATE` dùng **cùng một `Connection`**.
2. Điều kiện `balance >= ?` ngăn việc trừ tiền khi số dư không đủ; số dòng cập nhật là tín hiệu kiểm tra.
3. Nếu tài khoản đích không tồn tại, ngoại lệ khiến `rollback()` hoàn tác cả phần đã trừ ở nguồn.
4. Chỉ sau khi hai thao tác đều hợp lệ, chương trình mới gọi `commit()`.
5. `try-with-resources` đóng `PreparedStatement` và `Connection`; cấu hình auto-commit chỉ được phục hồi nếu giao dịch đã kết thúc thành công bằng commit hoặc rollback. Nếu rollback cũng thất bại, kết nối cần được xem là không an toàn để tái sử dụng.

Đây là ví dụ học tập về tính nguyên tử. Nghiệp vụ tiền thật cần thêm kiểm soát idempotency, giới hạn giao dịch, quyền truy cập, quy tắc ghi sổ, retry khi lỗi đồng thời và phương án xử lý khi không biết chắc kết quả `commit()` do mất kết nối.

## 9. Savepoint và rollback một phần

Khi giao dịch gồm nhiều bước mà một bước **không bắt buộc**, JDBC cho phép đặt **savepoint** trước bước đó:

```java
connection.setAutoCommit(false);

// Thực hiện phần bắt buộc A.
Savepoint beforeOptionalStep = connection.setSavepoint("before_optional");

try {
    // Thực hiện phần tùy chọn B.
} catch (SQLException expectedOptionalError) {
    connection.rollback(beforeOptionalStep);
    // Chỉ tiếp tục nếu nghiệp vụ cho phép bỏ qua B.
}

// Tiếp tục phần bắt buộc C, rồi commit nếu mọi điều kiện hợp lệ.
connection.commit();
```

Savepoint có tên qua `setSavepoint("name")` hoặc không tên qua `setSavepoint()` đều trả về đối tượng `Savepoint`. `rollback(savepoint)` quay về mốc trong **cùng** transaction, còn `rollback()` không tham số hoàn tác toàn bộ transaction. Savepoint không tự commit, và cần được DBMS/driver hỗ trợ. Đoạn mã trên minh họa ý tưởng, chưa phải khuôn mẫu xử lý đầy đủ mọi ngoại lệ.

## 10. Những sai lầm thường gặp trước khi viết JDBC

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Nối trực tiếp dữ liệu người dùng vào chuỗi SQL | SQL injection, lỗi dấu nháy, ép kiểu | Truyền giá trị bằng `PreparedStatement` và tham số `?` |
| Quên `WHERE` trong `UPDATE`/`DELETE` | Thay đổi quá nhiều dòng | Rà soát điều kiện và kiểm tra số dòng cập nhật |
| Tin rằng `SELECT` luôn trả về dòng theo thứ tự cố định | Kết quả hiển thị/trang dữ liệu không ổn định | Dùng `ORDER BY` với khóa phụ phù hợp |
| Dùng `= NULL` | Điều kiện không hoạt động như mong đợi | Dùng `IS NULL` / `IS NOT NULL` |
| Dùng `double` để tính tiền | Sai số nhị phân không mong muốn | Dùng `DECIMAL` ở SQL và `BigDecimal` ở Java |
| Thực hiện nhiều bước phụ thuộc nhau trong auto-commit | Bước đầu đã commit dù bước sau thất bại | Tắt auto-commit, quản lý `commit()/rollback()` |
| Quên xem `executeUpdate()` trả về bao nhiêu dòng | Có thể coi cập nhật 0 dòng là thành công | Kiểm tra theo điều kiện nghiệp vụ |
| Mở transaction quá lâu | Khóa lâu, tăng nguy cơ tranh chấp | Giữ công việc DB ngắn và có điểm kết thúc rõ |
| Giả định mọi DBMS hỗ trợ isolation/savepoint giống nhau | Khác biệt kết quả và lỗi khi triển khai | Kiểm tra driver/metadata và thử nghiệm trên DBMS đích |
| Dùng một `Connection` giao dịch đồng thời ở nhiều luồng | Ranh giới transaction và dữ liệu có thể bị can thiệp | Dùng kết nối riêng theo đơn vị công việc |

Một lưu ý quan trọng: cách DDL tương tác với transaction khác nhau giữa các DBMS. Một số hệ quản trị tự động commit hoặc không cho rollback một số lệnh DDL. Đừng áp dụng ví dụ rollback dữ liệu cho thao tác thay đổi schema nếu chưa kiểm chứng trên hệ cơ sở dữ liệu đang dùng.

## 11. Bài tập tự kiểm tra

**Bài 1 – SQL cơ bản.** Viết câu SQL liệt kê `order_id`, `total_amount` của các đơn thuộc khách hàng `1` có trạng thái `PAID`, sắp theo `order_id` giảm dần.

```sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 1 AND status = 'PAID'
ORDER BY order_id DESC;
```

**Bài 2 – Hiểu NULL.** Vì sao `WHERE email = NULL` không tìm thấy khách hàng thiếu email?  
**Gợi ý đáp án:** Phép so sánh với `NULL` cho kết quả `UNKNOWN`; phải dùng `WHERE email IS NULL`.

**Bài 3 – Transaction.** Một ứng dụng trừ tiền tài khoản A, sau đó cộng tiền tài khoản B, nhưng bước cộng bị lỗi. Khi dùng một transaction và chưa commit, cần gọi gì?  
**Gợi ý đáp án:** Gọi `connection.rollback()` để hoàn tác cả bước trừ, sau đó xử lý hoặc ném lại lỗi.

**Bài 4 – Dòng cập nhật.** Lệnh `UPDATE orders SET status = 'PAID' WHERE order_id = 999` trả về 0 dòng cập nhật. Điều này chứng minh điều gì?  
**Gợi ý đáp án:** Không có dòng nào được cập nhật; cần kiểm tra ID và các điều kiện khác trước khi kết luận nghiệp vụ thành công.

**Bài 5 – Isolation.** Tại sao mức `READ_COMMITTED` có thể chưa đủ nếu nghiệp vụ yêu cầu đọc một dòng hai lần trong cùng transaction và phải thấy giá trị nhất quán?  
**Gợi ý đáp án:** Mức này có thể cho phép **non-repeatable read**; cần chọn cơ chế cô lập hoặc khóa phù hợp với DBMS và yêu cầu nghiệp vụ.

**Bài 6 – PreparedStatement.** Trong câu `SELECT * FROM orders WHERE customer_id = ?`, dấu `?` dùng làm gì? Có dùng `?` thay tên bảng `orders` được không?  
**Gợi ý đáp án:** Dùng để bind giá trị đầu vào theo thứ tự tham số; không thay trực tiếp định danh SQL như tên bảng.

Khi đã nắm vững bảng, khóa, ràng buộc, `SELECT`/`INSERT`/`UPDATE`/`DELETE`, `JOIN`, `NULL` và ranh giới transaction, bạn có thể học JDBC theo một chuỗi rõ ràng: **mở kết nối → chuẩn bị SQL có tham số → thực thi → đọc kết quả/số dòng → commit hoặc rollback → đóng tài nguyên**.
