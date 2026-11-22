# Tách lỗi dữ liệu, lỗi ràng buộc, lỗi kết nối và lỗi đồng thời

Một ứng dụng Java có thể gửi lệnh `INSERT`, `UPDATE` hoặc `SELECT` đúng cú pháp nhưng vẫn thất bại vì nhiều nguyên nhân khác nhau. Người dùng có thể gửi một số tiền không chuyển được thành `NUMERIC`; một dòng có thể vi phạm khóa ngoại; database có thể mất kết nối ngay lúc commit; hai giao dịch có thể cùng sửa một bản ghi và ghi đè kết quả của nhau.

Những lỗi này không nên bị gom chung thành một thông báo “Database error”. Mỗi nhóm có **nguyên nhân, cách phản hồi, khả năng thử lại và cách khôi phục transaction** khác nhau.

Bài học **“Tách lỗi dữ liệu, lỗi ràng buộc, lỗi kết nối và lỗi đồng thời”**, thuộc chương **SQL trong ứng dụng** của module **Database SQL**, hướng dẫn cách nhận diện và xử lý bốn nhóm lỗi ở ranh giới Java/JDBC và SQL:

1. **Lỗi dữ liệu:** giá trị đầu vào sai định dạng, sai kiểu hoặc vượt phạm vi.
2. **Lỗi ràng buộc:** dữ liệu có kiểu hợp lệ nhưng vi phạm quy tắc toàn vẹn như `NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `CHECK`.
3. **Lỗi kết nối:** không mở được kết nối, kết nối bị mất hoặc kết quả commit không xác định.
4. **Lỗi đồng thời:** giao dịch cạnh tranh, deadlock, serialization failure, lost update hoặc xung đột khi nhiều request cùng xử lý một tài nguyên.

Ví dụ chính dùng **Java JDBC và PostgreSQL**. JDBC cung cấp `SQLException`, SQLState và các lớp exception con; PostgreSQL có các mã SQLState cụ thể. Các DBMS khác thường dùng SQLState tương tự cho nhiều nhóm, nhưng mã chi tiết, hành vi transaction và thông tin vendor có thể khác.

> **Nguyên tắc cốt lõi:** Phân loại lỗi theo **SQLState và ngữ cảnh giao dịch**, không theo nội dung chuỗi thông báo. Chỉ retry khi biết lỗi có thể phục hồi, transaction trước đã được xử lý đúng và thao tác có thể thực hiện lại an toàn.

## 1. Bốn nhóm lỗi ở ranh giới ứng dụng và database

Một luồng ghi đơn hàng thường có các bước:

```text
HTTP/API request
      │
      ▼
Validate dữ liệu đầu vào
      │
      ▼
Chuyển kiểu Java (BigDecimal, UUID, LocalDate...)
      │
      ▼
JDBC PreparedStatement
      │
      ▼
Database transaction
      │
      ├── Lỗi dữ liệu
      ├── Lỗi ràng buộc
      ├── Lỗi kết nối
      └── Lỗi đồng thời
      │
      ▼
Commit / Rollback / Retry có kiểm soát
      │
      ▼
Domain result / API response
```

### 1.1. Lỗi dữ liệu

Ví dụ cột:

```sql
amount NUMERIC(12,2) NOT NULL
```

Ứng dụng nhận `"twelve dollars"` rồi gửi vào cột số. Database không thể phân tích chuỗi thành numeric và trả lỗi dữ liệu.

Đặc điểm:

- Giá trị không đúng định dạng hoặc kiểu.
- Giá trị vượt phạm vi kiểu SQL.
- Ngày tháng không hợp lệ.
- Chuỗi quá dài so với cột hoặc encoding không phù hợp.
- Lỗi có thể phát hiện trước khi gửi SQL, nhưng database vẫn cần kiểm tra vì ứng dụng không phải ranh giới tin cậy duy nhất.

### 1.2. Lỗi ràng buộc

Giá trị `amount = -10.00` là một số `NUMERIC` hợp lệ, nhưng có thể vi phạm:

```sql
CHECK (amount >= 0)
```

Đây là lỗi **toàn vẹn dữ liệu**, không phải lỗi cú pháp số.

Đặc điểm:

- Giá trị có thể chuyển thành kiểu SQL thành công.
- Quan hệ giữa các dòng hoặc quy tắc của bảng không được thỏa mãn.
- Ví dụ: khóa chính trùng, khóa ngoại không tồn tại, cột bắt buộc NULL, vi phạm CHECK hoặc exclusion constraint.
- Có thể xuất hiện do request sai hoặc do một giao dịch cạnh tranh đã thay đổi dữ liệu sau khi ứng dụng kiểm tra.

### 1.3. Lỗi kết nối

Ứng dụng có thể mất kết nối khi đang chạy:

```text
INSERT → database đã thực hiện
COMMIT → mạng đứt trước khi client nhận phản hồi
```

Client không biết chắc commit đã thành công hay chưa. Đây là tình huống **kết quả không xác định** (*unknown outcome*), rất khác với một lỗi dữ liệu chắc chắn bị từ chối.

### 1.4. Lỗi đồng thời

Hai request cùng đọc tồn kho là 1:

```text
Request A đọc stock = 1
Request B đọc stock = 1
Request A trừ 1 → stock = 0
Request B trừ 1 → stock = 0
```

Nếu mỗi request ghi giá trị tính từ bản đọc cũ, cả hai có thể báo thành công dù chỉ còn một sản phẩm. Đây là một dạng **lost update/race condition**.

Lỗi đồng thời cũng có thể được database phát hiện rõ ràng bằng deadlock hoặc serialization failure. Một số lỗi là xung đột nghiệp vụ cần trả về cho caller; một số có thể retry cả transaction.

## 2. SQLState: mã chuẩn để phân loại lỗi JDBC

`java.sql.SQLException` có phương thức:

```java
String state = exception.getSQLState();
int vendorCode = exception.getErrorCode();
```

**SQLState** thường là chuỗi năm ký tự. Hai ký tự đầu xác định lớp lỗi (*SQLState class*), ba ký tự tiếp theo xác định trạng thái cụ thể. Với driver hỗ trợ SQLState chuẩn, có thể phân loại ở mức tổng quát bằng hai ký tự đầu.

### 2.1. Các lớp quan trọng trong bài

| SQLState class | Nhóm | Ý nghĩa |
|---|---|---|
| `22` | Data exception | Giá trị dữ liệu không hợp lệ, chuyển kiểu hoặc phạm vi |
| `23` | Integrity constraint violation | Vi phạm ràng buộc toàn vẹn |
| `08` | Connection exception | Kết nối SQL gặp sự cố |
| `40` | Transaction rollback | Transaction bị rollback do xung đột hoặc lỗi giao dịch |
| `25` | Invalid transaction state | Trạng thái transaction hiện tại không cho phép thao tác |
| `55` | Object not in prerequisite state | Một số lỗi khóa/tài nguyên, ví dụ lock unavailable |
| `57` | Operator intervention | Một số lỗi hủy query hoặc can thiệp vận hành |

Không phải mọi lỗi SQL đều nằm trong bốn nhóm chính. Ví dụ lỗi cú pháp thường thuộc class `42`; thiếu bảng/cột cũng là lỗi schema/query, không phải lỗi dữ liệu đầu vào.

### 2.2. Các SQLState PostgreSQL thường gặp

| SQLState | Tên PostgreSQL | Cách hiểu |
|---|---|---|
| `22P02` | `invalid_text_representation` | Chuỗi không thể chuyển sang kiểu đích |
| `22003` | `numeric_value_out_of_range` | Giá trị số vượt phạm vi |
| `22001` | `string_data_right_truncation` | Chuỗi dài hơn giới hạn đích |
| `22007` | `invalid_datetime_format` | Định dạng ngày/giờ không hợp lệ |
| `22008` | `datetime_field_overflow` | Thành phần ngày/giờ vượt phạm vi |
| `23502` | `not_null_violation` | Vi phạm `NOT NULL` |
| `23503` | `foreign_key_violation` | Vi phạm khóa ngoại |
| `23505` | `unique_violation` | Vi phạm unique/primary key |
| `23514` | `check_violation` | Vi phạm `CHECK` |
| `23P01` | `exclusion_violation` | Vi phạm exclusion constraint |
| `08001` | `sqlclient_unable_to_establish_sqlconnection` | Không thiết lập được kết nối |
| `08003` | `connection_does_not_exist` | Kết nối không còn tồn tại |
| `08006` | `connection_failure` | Kết nối thất bại |
| `40001` | `serialization_failure` | Giao dịch không thể serialize |
| `40P01` | `deadlock_detected` | Deadlock |
| `55P03` | `lock_not_available` | Không lấy được khóa theo yêu cầu |
| `57014` | `query_canceled` | Query bị hủy, ví dụ statement timeout/cancel |
| `25P02` | `in_failed_sql_transaction` | Transaction đã ở trạng thái lỗi sau statement thất bại |

Mã chi tiết ở bảng là của PostgreSQL. Khi dùng DBMS khác, hãy kiểm tra danh mục SQLState và exception của driver tương ứng.

### 2.3. SQLState không phải vendor error code

Trong JDBC:

- `getSQLState()` trả mã trạng thái theo SQLState.
- `getErrorCode()` trả mã lỗi riêng của database/driver.

Không so sánh vendor code của PostgreSQL với SQL Server hoặc MySQL như thể chúng cùng một hệ mã. Khi cần mapping đa DBMS, ưu tiên SQLState và abstraction của ứng dụng; chỉ dùng vendor code khi cần xử lý đặc thù có tài liệu.

## 3. Hệ thống ví dụ PostgreSQL

Ta tạo một schema thử để các câu SQL có thể chạy độc lập. Không chạy các lệnh ghi ví dụ trên bảng production.

### 3.1. Bảng khách hàng và đơn hàng

```sql
CREATE TABLE IF NOT EXISTS app_error_lab_customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    CONSTRAINT uq_error_lab_customer_email UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS app_error_lab_orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT fk_error_lab_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES app_error_lab_customers(customer_id),
    CONSTRAINT ck_error_lab_order_amount
        CHECK (amount >= 0),
    CONSTRAINT ck_error_lab_order_status
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);
```

### 3.2. Nạp dữ liệu

```sql
INSERT INTO app_error_lab_customers (customer_id, email)
VALUES
    (1, 'an@example.test'),
    (2, 'binh@example.test')
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status, version_no)
VALUES
    (1001, 1, 120.50, 'PENDING', 0),
    (1002, 2,  75.00, 'PENDING', 0)
ON CONFLICT (order_id) DO NOTHING;
```

`ON CONFLICT (customer_id) DO NOTHING` ở đây giúp script có thể chạy lại trên bảng lab đã tồn tại. Nó không bỏ qua mọi lỗi khác: ví dụ email trùng nhưng customer_id khác vẫn có thể vi phạm unique.

### 3.3. Đọc trạng thái ban đầu

```sql
SELECT * FROM app_error_lab_customers ORDER BY customer_id;
SELECT * FROM app_error_lab_orders ORDER BY order_id;
```

Các bài sau dùng những dòng này để minh họa dữ liệu, constraint và giao dịch đồng thời.

## 4. Nhóm 1 — Lỗi dữ liệu

Lỗi dữ liệu xảy ra khi giá trị không thể được biểu diễn hoặc chuyển đổi theo kiểu SQL cần thiết.

### 4.1. Chuỗi không chuyển được sang số

```sql
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (2001, 1, 'twelve dollars', 'PENDING');
```

PostgreSQL không thể phân tích `twelve dollars` thành `NUMERIC`. Một SQLState thường gặp là:

```text
22P02 — invalid_text_representation
```

### 4.2. Số vượt phạm vi

```sql
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (2002, 1, 999999999999999999999999.99, 'PENDING');
```

Giá trị vượt khả năng lưu của `NUMERIC(12,2)`, thường phát sinh:

```text
22003 — numeric_value_out_of_range
```

### 4.3. Ngày không hợp lệ

```sql
SELECT DATE '2026-02-30';
```

Ngày 30/2 không tồn tại. PostgreSQL thường báo lỗi ngày/giờ với SQLState thuộc class `22`, chẳng hạn `22008` tùy trường hợp.

### 4.4. Chuỗi quá dài

Nếu cột được định nghĩa:

```sql
nickname VARCHAR(10)
```

và ứng dụng ghi chuỗi dài vượt giới hạn, PostgreSQL có thể trả:

```text
22001 — string_data_right_truncation
```

Hành vi cắt hay từ chối chuỗi còn phụ thuộc kiểu, ngữ cảnh và DBMS; không mặc định mọi hệ thống sẽ tự cắt dữ liệu.

### 4.5. Kiểm tra ở application và database

Java có thể xác thực trước:

```java
if (amount == null) {
    throw new IllegalArgumentException("amount is required");
}

if (amount.scale() > 2) {
    throw new IllegalArgumentException(
        "amount must have at most 2 decimal places"
    );
}
```

Nhưng validation phía Java không thay constraint ở database:

- Dữ liệu có thể đến từ service khác, batch job hoặc SQL client.
- Hai request đồng thời có thể làm thay đổi trạng thái giữa lúc kiểm tra và lúc ghi.
- Migration hoặc script vận hành có thể bỏ qua logic của application.

**Application validation giúp phản hồi sớm và thân thiện; database constraints bảo vệ tính toàn vẹn cuối cùng.**

### 4.6. Kiểu Java đúng giúp tránh một số lỗi trước JDBC

```java
BigDecimal amount = new BigDecimal("120.50");
LocalDate dueDate = LocalDate.of(2026, 11, 14);
UUID customerId = UUID.fromString(
    "550e8400-e29b-41d4-a716-446655440000"
);
```

Parse sai có thể được phát hiện trước khi gọi database. Tuy nhiên `BigDecimal` hợp lệ vẫn có thể vượt `NUMERIC(12,2)` hoặc vi phạm `CHECK (amount >= 0)`.

## 5. Nhóm 2 — Lỗi ràng buộc toàn vẹn

Constraint là hợp đồng mà database áp dụng cho mọi đường ghi dữ liệu.

### 5.1. `NOT NULL`

```sql
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (2101, 1, NULL, 'PENDING');
```

`amount` không được null, nên PostgreSQL trả:

```text
23502 — not_null_violation
```

Đây là lỗi ràng buộc, dù đầu vào `NULL` có thể bắt nguồn từ một lỗi dữ liệu ở application.

### 5.2. `UNIQUE` hoặc primary key

```sql
INSERT INTO app_error_lab_customers (customer_id, email)
VALUES (3, 'an@example.test');
```

Email đã tồn tại nên vi phạm:

```text
23505 — unique_violation
```

Đây có thể là:

- Người dùng đăng ký email đã có.
- Request bị gửi lặp.
- Hai request đồng thời cùng tạo một tài khoản.
- Một race condition giữa bước kiểm tra và insert.

Không thể phân loại nguyên nhân nghiệp vụ chỉ bằng mã `23505`; cần biết **constraint nào** bị vi phạm và thao tác nào đang chạy.

### 5.3. `FOREIGN KEY`

```sql
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (2102, 999999, 50, 'PENDING');
```

Không có customer `999999`, nên:

```text
23503 — foreign_key_violation
```

Đây có thể là ID sai, hoặc customer đã bị xóa giữa lúc ứng dụng kiểm tra và ghi.

### 5.4. `CHECK`

```sql
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (2103, 1, -10, 'PENDING');
```

`-10` chuyển thành numeric thành công, nhưng:

```text
23514 — check_violation
```

Do đó cần phân biệt:

```text
"twelve dollars" → không chuyển được thành NUMERIC → data exception
-10              → NUMERIC hợp lệ nhưng amount >= 0 sai → constraint violation
```

### 5.5. Exclusion constraint

PostgreSQL còn có exclusion constraint, thường dùng để ngăn các khoảng thời gian chồng lấn hoặc các cặp giá trị xung đột theo toán tử.

SQLState:

```text
23P01 — exclusion_violation
```

Đây vẫn là nhóm lỗi ràng buộc, không phải lỗi chuyển kiểu.

### 5.6. Constraint là ranh giới cuối cho race condition

Mẫu không an toàn:

```text
SELECT xem email đã tồn tại chưa
Nếu chưa:
    INSERT email
```

Hai transaction có thể cùng đọc “chưa tồn tại”, rồi cùng insert. `UNIQUE` constraint mới là cơ chế bảo vệ cuối cùng.

Có thể dùng:

```sql
INSERT INTO app_error_lab_customers (customer_id, email)
VALUES (3, 'an@example.test')
ON CONFLICT (email) DO NOTHING;
```

hoặc `ON CONFLICT ... DO UPDATE` nếu semantics nghiệp vụ cho phép. Không dùng `DO NOTHING` để âm thầm che một xung đột cần báo cho người dùng.

## 6. Nhóm 3 — Lỗi kết nối

Lỗi kết nối không nói rằng dữ liệu sai. Nó nói ứng dụng không thể giao tiếp với database theo cách cần thiết.

### 6.1. Các thời điểm lỗi có thể xuất hiện

```text
1. getConnection()
      └─ Không kết nối được host/port/authentication

2. executeQuery()/executeUpdate()
      └─ Connection bị reset, timeout hoặc server đóng

3. đọc ResultSet
      └─ Mạng đứt giữa lúc nhận các batch

4. commit()
      └─ Server đã commit nhưng phản hồi bị mất
         hoặc server chưa commit
         → client có thể không biết kết quả
```

### 6.2. SQLState class `08`

Một số mã PostgreSQL:

- `08001`: không thiết lập được kết nối.
- `08003`: connection không tồn tại.
- `08006`: connection failure.

Driver có thể báo thêm exception con, vendor code và cause cụ thể. Mất mạng, server restart, DNS, pool timeout và credential sai có thể có biểu hiện khác nhau.

### 6.3. Timeout không đồng nghĩa mọi trường hợp là connection failure

Ví dụ:

- Không lấy được connection từ pool trong thời gian chờ: lỗi ở pool/application layer, có thể chưa có SQLState.
- `connectTimeout`: không thiết lập được kết nối tới server.
- `socketTimeout`: đọc/ghi mạng quá thời gian, có thể làm mất connection.
- PostgreSQL `statement_timeout`: query bị hủy, thường SQLState `57014`, không nhất thiết connection đã mất.
- `lock_timeout`: chờ khóa quá lâu, thường `55P03`, không phải lỗi mạng.

Hãy phân loại theo **giai đoạn và exception thực tế**, không đổi mọi timeout thành “database down”.

### 6.4. Connection pool

Ứng dụng thường lấy logical connection:

```java
try (Connection connection = dataSource.getConnection()) {
    // Sử dụng connection.
}
```

Nếu kết nối vật lý hỏng, pool/driver cần đánh dấu hoặc loại bỏ connection đó theo cơ chế của thư viện. Không tự giữ connection lỗi trong biến singleton để dùng lại.

### 6.5. Không thử lại trên connection đã hỏng

Sau connection failure:

- Không tiếp tục chạy query trên cùng connection như chưa có gì xảy ra.
- Đóng/trả connection theo hợp đồng pool.
- Lấy connection mới cho lần thử lại nếu thao tác có thể retry an toàn.
- Không giả định transaction cũ còn trạng thái có thể sử dụng.

## 7. Nhóm 4 — Lỗi đồng thời và transaction rollback

PostgreSQL có class SQLState `40` cho transaction rollback.

### 7.1. Serialization failure — `40001`

Ở isolation level `SERIALIZABLE`, database bảo đảm kết quả tương đương một thứ tự tuần tự. Nếu các giao dịch cạnh tranh không thể được sắp xếp an toàn, PostgreSQL có thể hủy một giao dịch:

```text
40001 — serialization_failure
```

Đây là lỗi **có thể retry** trong nhiều trường hợp, nhưng phải retry **toàn bộ transaction** từ đầu, không chỉ statement cuối.

### 7.2. Deadlock — `40P01`

Ví dụ:

```text
Transaction A khóa row 1
Transaction B khóa row 2

A muốn khóa row 2 → chờ B
B muốn khóa row 1 → chờ A

Database phát hiện chu trình chờ
→ hủy một transaction
→ 40P01 deadlock_detected
```

Transaction bị chọn làm nạn nhân bị rollback. Ứng dụng có thể retry toàn transaction theo chính sách có giới hạn.

### 7.3. Lock unavailable — `55P03`

Nếu câu lệnh dùng `NOWAIT` hoặc cơ chế chờ khóa hết thời gian, PostgreSQL có thể trả:

```text
55P03 — lock_not_available
```

Đây không phải deadlock. Ứng dụng phải quyết định chờ lại, trả conflict hoặc bỏ qua bản ghi theo nghiệp vụ.

### 7.4. Query canceled — `57014`

Ví dụ query bị hủy do `statement_timeout` hoặc lệnh cancel:

```text
57014 — query_canceled
```

Đừng tự retry vô hạn. Cần biết query bị hủy do timeout, người dùng cancel, vận hành shutdown hay chính sách tài nguyên.

### 7.5. Transaction đã lỗi — `25P02`

Trong PostgreSQL, sau một statement lỗi bên trong transaction tường minh, các statement tiếp theo thường bị từ chối:

```text
25P02 — in_failed_sql_transaction
```

Phải `ROLLBACK` transaction hoặc rollback về savepoint đã tạo trước lỗi. Không coi `25P02` là nguyên nhân gốc; hãy tìm **exception đầu tiên** xảy ra trước đó.

## 8. SQLState và các lớp exception JDBC

JDBC định nghĩa các lớp con hữu ích:

| Lớp Java | Ý nghĩa tổng quát |
|---|---|
| `SQLDataException` | Vấn đề dữ liệu |
| `SQLIntegrityConstraintViolationException` | Vi phạm ràng buộc toàn vẹn |
| `SQLTransientConnectionException` | Lỗi kết nối có thể tạm thời |
| `SQLNonTransientConnectionException` | Lỗi kết nối không thể tiếp tục dùng như hiện tại |
| `SQLRecoverableException` | Có thể phục hồi bằng hành động như lấy connection mới |
| `SQLTransactionRollbackException` | Transaction bị rollback |
| `SQLTimeoutException` | Timeout trong thao tác JDBC |
| `BatchUpdateException` | Batch update thất bại, có thông tin update counts |

Driver không phải lúc nào cũng tạo đúng lớp con mong đợi cho mọi lỗi. Vì vậy, nên đọc **SQLState**, kiểm tra exception subclass và giữ lại vendor information.

### 8.1. Ví dụ kiểm tra SQLState

```java
import java.sql.SQLException;

static String sqlStateClass(SQLException exception) {
    String state = exception.getSQLState();
    if (state == null || state.length() < 2) {
        return "UNKNOWN";
    }
    return state.substring(0, 2);
}
```

### 8.2. Không phân loại bằng message

Không nên:

```java
if (exception.getMessage().contains("duplicate")) {
    // Duplicate key?
}
```

Thông báo có thể đổi theo:

- DBMS và phiên bản.
- Ngôn ngữ/cấu hình server.
- Driver.
- Tên bảng/cột/constraint.
- Nội dung dữ liệu do người dùng gửi.

SQLState ổn định hơn để phân loại tổng quát. Với PostgreSQL, nếu cần tên constraint cụ thể, có thể dùng extension/vendor API của driver (ví dụ `PSQLException`/server error detail) nhưng nên cô lập phần phụ thuộc đó.

## 9. Đọc toàn bộ exception chain

Một `SQLException` có:

- `getNextException()` — chuỗi SQL exception.
- `getCause()` — nguyên nhân Java.
- `getSQLState()` — SQLState.
- `getErrorCode()` — vendor code.

Ví dụ helper log:

```java
static void logSqlException(SQLException exception) {
    for (SQLException current = exception;
         current != null;
         current = current.getNextException()) {

        System.err.printf(
            "SQLState=%s, vendorCode=%d, type=%s%n",
            current.getSQLState(),
            current.getErrorCode(),
            current.getClass().getSimpleName()
        );
    }

    Throwable cause = exception.getCause();
    if (cause != null) {
        System.err.println(
            "Cause type=" + cause.getClass().getName()
        );
    }
}
```

Không log toàn bộ SQL parameter chứa mật khẩu, token, dữ liệu cá nhân hoặc payload nhạy cảm. Log mã lỗi, operation, correlation ID và thông tin đã masking.

### 9.1. `BatchUpdateException`

Khi batch thất bại:

```java
catch (BatchUpdateException exception) {
    int[] counts = exception.getUpdateCounts();
    // Kiểm tra SQLState, counts và transaction state.
}
```

Các giá trị trong update counts có thể là số dòng đã cập nhật, `Statement.SUCCESS_NO_INFO` hoặc `Statement.EXECUTE_FAILED`. Hành vi dừng/tiếp tục batch phụ thuộc driver.

**Không được suy luận** rằng một phần batch đã commit chỉ vì `getUpdateCounts()` có vài số dương. Nếu đang trong transaction, có thể toàn bộ transaction vẫn bị rollback. Cần xem autocommit, driver và trạng thái transaction thực tế.

## 10. Mô hình phân loại lỗi trong Java

Ứng dụng nên có một lớp phân loại nội bộ, không để mọi tầng tự kiểm tra chuỗi SQLState.

Ví dụ:

```java
enum DatabaseFailureKind {
    DATA,
    CONSTRAINT,
    CONNECTION,
    CONCURRENCY,
    TIMEOUT_OR_CANCELED,
    TRANSACTION_STATE,
    OTHER
}
```

### 10.1. Phân loại tổng quát bằng SQLState

```java
import java.sql.SQLException;

static DatabaseFailureKind classify(SQLException exception) {
    String state = exception.getSQLState();

    if (state == null || state.length() < 2) {
        return DatabaseFailureKind.OTHER;
    }

    String stateClass = state.substring(0, 2);

    return switch (stateClass) {
        case "22" -> DatabaseFailureKind.DATA;
        case "23" -> DatabaseFailureKind.CONSTRAINT;
        case "08" -> DatabaseFailureKind.CONNECTION;
        case "40" -> DatabaseFailureKind.CONCURRENCY;
        case "55", "57" ->
            DatabaseFailureKind.TIMEOUT_OR_CANCELED;
        case "25" -> DatabaseFailureKind.TRANSACTION_STATE;
        default -> DatabaseFailureKind.OTHER;
    };
}
```

Đây là **phân loại sơ bộ**. Trong production, không nên gộp mọi class `55` hoặc `57` thành cùng một chính sách. Cần xét SQLState cụ thể, thao tác và trạng thái transaction.

### 10.2. Phân biệt deadlock và serialization failure

```java
static boolean isRetryableTransactionConflict(SQLException exception) {
    String state = exception.getSQLState();
    return "40001".equals(state) || "40P01".equals(state);
}
```

Với PostgreSQL, đây là hai trường hợp thường được cân nhắc retry toàn transaction.

### 10.3. Constraint cụ thể

```java
static boolean isUniqueViolation(SQLException exception) {
    return "23505".equals(exception.getSQLState());
}

static boolean isForeignKeyViolation(SQLException exception) {
    return "23503".equals(exception.getSQLState());
}

static boolean isCheckViolation(SQLException exception) {
    return "23514".equals(exception.getSQLState());
}
```

Những mã trên là PostgreSQL. Với DBMS khác, tạo adapter tương ứng thay vì dùng các hằng này như quy tắc portable.

## 11. Validation trước SQL và constraint tại database

Hai lớp bảo vệ phục vụ mục tiêu khác nhau.

### 11.1. Validation tại API/domain

Ví dụ:

```java
if (request.amount() == null) {
    throw new ValidationException("amount is required");
}

if (request.amount().signum() < 0) {
    throw new ValidationException("amount must not be negative");
}
```

Ưu điểm:

- Phản hồi sớm, thông báo dễ hiểu.
- Giảm round-trip không cần thiết.
- Có thể kiểm tra quy tắc phụ thuộc ngữ cảnh request.

### 11.2. Constraint tại database

```sql
amount NUMERIC(12,2) NOT NULL
    CHECK (amount >= 0)
```

Ưu điểm:

- Bảo vệ mọi đường ghi, kể cả batch job/service khác.
- Ngăn race condition trong một số quy tắc như unique/FK.
- Giữ dữ liệu đúng ngay cả khi application có bug.

### 11.3. Đừng dựa vào SELECT kiểm tra trước constraint

Không an toàn:

```sql
SELECT 1
FROM app_error_lab_customers
WHERE email = 'new@example.test';

-- Nếu không thấy thì INSERT.
```

Hai transaction có thể cùng không thấy. `UNIQUE` constraint mới quyết định cuối cùng.

Nếu cần tạo hoặc lấy một bản ghi theo khóa duy nhất, cân nhắc:

```sql
INSERT INTO app_error_lab_customers (customer_id, email)
VALUES (10, 'new@example.test')
ON CONFLICT (email) DO NOTHING
RETURNING customer_id;
```

Nếu không có dòng trả về, ứng dụng có thể cần query bản ghi đã tồn tại hoặc trả conflict theo nghiệp vụ.

### 11.4. Không nuốt constraint violation

Mẫu xấu:

```java
try {
    repository.insert(order);
} catch (SQLException ignored) {
    // Cứ tiếp tục như thể insert thành công.
}
```

Nó khiến application và database lệch trạng thái. Chỉ xử lý riêng lỗi có semantics rõ, ví dụ duplicate request được nhận diện bằng idempotency key; các lỗi khác phải được truyền/ánh xạ đúng.

## 12. Transaction bị lỗi: vì sao phải rollback?

Trong PostgreSQL, nếu một statement thất bại trong transaction block, transaction chuyển sang trạng thái aborted.

Ví dụ:

```sql
BEGIN;

INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (3001, 1, -5, 'PENDING');
-- CHECK violation.

SELECT * FROM app_error_lab_orders;
-- 25P02: transaction đã ở trạng thái lỗi.

ROLLBACK;
```

### 12.1. Rollback toàn transaction

Khi lỗi khiến công việc all-or-nothing không thể tiếp tục:

```java
try {
    connection.setAutoCommit(false);

    // Nhiều câu SQL.

    connection.commit();
} catch (SQLException exception) {
    try {
        connection.rollback();
    } catch (SQLException rollbackException) {
        exception.addSuppressed(rollbackException);
    }
    throw exception;
}
```

Không gọi `commit()` trong nhánh catch chỉ để “giải phóng connection”.

### 12.2. Rollback không có nghĩa mọi side effect được hoàn tác

Nếu trong transaction ứng dụng còn:

- Gửi email.
- Gọi API thanh toán.
- Upload tệp lên object storage.
- Publish message trực tiếp.

thì rollback SQL không tự thu hồi các hành động ngoài database. Hãy dùng outbox, saga hoặc cơ chế bù trừ thích hợp.

## 13. Savepoint: xử lý một lỗi con mà vẫn giữ transaction

Đôi khi import 1000 dòng và muốn từ chối riêng một số dòng lỗi, vẫn tiếp tục với các dòng còn lại. Trong PostgreSQL, sau một statement lỗi, cần rollback tới savepoint để transaction thoát trạng thái aborted.

### 13.1. SQL minh họa

```sql
BEGIN;

SAVEPOINT before_order;

INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (4001, 1, -10, 'PENDING');
-- CHECK violation.

ROLLBACK TO SAVEPOINT before_order;

INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (4002, 1, 50, 'PENDING');

COMMIT;
```

### 13.2. Savepoint trong JDBC

```java
connection.setAutoCommit(false);

try {
    Savepoint savepoint = connection.setSavepoint("before_row");

    try {
        insertOneRow(connection, row);
    } catch (SQLException exception) {
        connection.rollback(savepoint);

        if (isExpectedRowLevelError(exception)) {
            recordRejectedRow(row, exception.getSQLState());
        } else {
            throw exception;
        }
    }

    connection.commit();
} catch (SQLException exception) {
    connection.rollback();
    throw exception;
}
```

Đây là skeleton; cần bảo đảm savepoint được tạo trước thao tác có thể lỗi, và xử lý lỗi rollback/release savepoint phù hợp.

### 13.3. Không phải lỗi nào cũng nên tiếp tục

Có thể cân nhắc savepoint cho lỗi dữ liệu/ràng buộc **riêng từng dòng** trong import. Nhưng không nên tiếp tục như bình thường khi:

- Connection đã mất.
- Transaction bị deadlock/serialization failure.
- Schema/query sai khiến mọi dòng đều thất bại.
- Lỗi hệ thống hoặc quyền truy cập.

Với lỗi kết nối, không thể tin rằng savepoint còn dùng được trên connection đã đứt.

### 13.4. Savepoint có chi phí

Tạo savepoint cho từng dòng hàng triệu bản ghi có overhead. Có thể gom theo batch, phân vùng lỗi, hoặc staging table rồi validate theo tập hợp.

## 14. Lỗi đồng thời: lost update

Một ví dụ phổ biến là cập nhật tồn kho bằng cách đọc rồi ghi:

```java
int stock = readStock(productId);
if (stock > 0) {
    writeStock(productId, stock - 1);
}
```

Nếu hai request chạy đồng thời, cả hai có thể đọc cùng một giá trị cũ.

### 14.1. Sơ đồ race condition

```text
Time       Transaction A         Transaction B
----       --------------         --------------
t1         SELECT stock = 1
t2                                SELECT stock = 1
t3         UPDATE stock = 0
t4                                UPDATE stock = 0
t5         COMMIT
t6                                COMMIT
```

Hai giao dịch đều có thể nghĩ mình đã trừ một sản phẩm, trong khi số lượng cuối chỉ giảm một lần.

### 14.2. Cập nhật nguyên tử

Nếu logic chỉ là “trừ một khi còn hàng”, viết một statement:

```sql
UPDATE inventory
SET stock = stock - 1
WHERE product_id = ?
  AND stock > 0
RETURNING stock;
```

Ứng dụng kiểm tra số dòng trả về:

- Có một dòng: đã trừ thành công.
- Không có dòng: không tồn tại sản phẩm hoặc không còn hàng (có thể cần query/logic phân biệt).

Đây là cách tốt hơn đọc rồi ghi bằng hai statement không khóa.

### 14.3. Constraint bảo vệ giá trị

```sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_stock_nonnegative
CHECK (stock >= 0);
```

Constraint là lớp bảo vệ cuối, còn câu `UPDATE ... WHERE stock > 0` thể hiện logic cạnh tranh an toàn hơn.

## 15. Optimistic locking bằng cột version

Khi nhiều người có thể sửa cùng bản ghi, có thể dùng **optimistic concurrency control**: đọc phiên bản hiện tại, chỉ cập nhật nếu phiên bản vẫn đúng.

### 15.1. Bảng có version

```sql
CREATE TABLE app_error_lab_profile (
    profile_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 0
);

INSERT INTO app_error_lab_profile
    (profile_id, display_name, version_no)
VALUES (1, 'An', 0)
ON CONFLICT (profile_id) DO NOTHING;
```

### 15.2. Update có điều kiện version

```sql
UPDATE app_error_lab_profile
SET display_name = 'An Nguyen',
    version_no = version_no + 1
WHERE profile_id = 1
  AND version_no = 0;
```

Nếu một dòng được cập nhật, request đã ghi thành công. Nếu `row count = 0`, có thể:

- Bản ghi không tồn tại.
- Version đã thay đổi do người khác cập nhật.

Ứng dụng có thể query phân biệt hai tình huống hoặc trả conflict theo API contract.

### 15.3. JDBC

```java
String sql = """
    UPDATE app_error_lab_profile
    SET display_name = ?, version_no = version_no + 1
    WHERE profile_id = ? AND version_no = ?
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, newName);
    statement.setLong(2, profileId);
    statement.setInt(3, expectedVersion);

    int updated = statement.executeUpdate();
    if (updated == 0) {
        throw new OptimisticLockException(
            "Profile was changed or no longer exists"
        );
    }
}
```

### 15.4. Vì sao không phải retry tự động?

Nếu version đã đổi, dữ liệu đầu vào của request có thể dựa trên một trạng thái cũ. Tự chạy lại cùng `UPDATE` với version mới có thể ghi đè thay đổi của người khác. Thông thường cần trả conflict để client tải lại dữ liệu hoặc áp dụng merge theo nghiệp vụ.

Optimistic locking rất hữu ích khi xung đột hiếm, không cần giữ lock trong lúc người dùng chỉnh sửa.

## 16. Pessimistic locking: `SELECT ... FOR UPDATE`

Khi cần khóa bản ghi trước khi đọc/sửa trong cùng transaction, PostgreSQL hỗ trợ:

```sql
BEGIN;

SELECT stock
FROM inventory
WHERE product_id = 10
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction.

UPDATE inventory
SET stock = stock - 1
WHERE product_id = 10;

COMMIT;
```

### 16.1. Khóa tồn tại tới đâu?

Row lock thông thường được giữ tới khi transaction kết thúc (`COMMIT`/`ROLLBACK`). Vì vậy không nên:

```text
BEGIN
SELECT ... FOR UPDATE
đợi người dùng xác nhận trong 30 giây
UPDATE
COMMIT
```

Transaction mở lâu có thể làm request khác chờ, gây deadlock hoặc giảm throughput.

### 16.2. `NOWAIT`

```sql
SELECT *
FROM inventory
WHERE product_id = 10
FOR UPDATE NOWAIT;
```

Nếu không lấy được khóa ngay, PostgreSQL có thể trả `55P03`. Ứng dụng có thể trả “đang được xử lý, thử lại sau” hoặc một conflict phù hợp.

### 16.3. `SKIP LOCKED`

```sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 10;
```

Worker bỏ qua các dòng đang bị khóa bởi worker khác. Cách này thường dùng cho queue có nhiều worker, nhưng cần transaction cập nhật trạng thái và commit nhanh.

`SKIP LOCKED` **không bảo đảm thứ tự hoàn thành**, và không phù hợp mọi truy vấn nghiệp vụ. Nó có thể bỏ qua một job đang khóa và lấy job sau.

## 17. Deadlock và cách giảm nguy cơ

Deadlock xảy ra khi các transaction giữ tài nguyên mà transaction kia cần, tạo thành chu trình chờ.

### 17.1. Ví dụ hai hàng

```text
A: lock row 1
B: lock row 2
A: chờ row 2
B: chờ row 1
```

Database phát hiện deadlock và chọn một transaction bị hủy, thay vì chờ vô hạn.

### 17.2. Khóa theo cùng thứ tự

Nếu nhiều transaction cần khóa hai account, luôn khóa theo thứ tự `account_id` tăng dần:

```sql
SELECT *
FROM accounts
WHERE account_id IN (10, 20)
ORDER BY account_id
FOR UPDATE;
```

Các thao tác khác cũng phải tuân theo quy tắc thứ tự nhất quán. Điều này giảm khả năng hai transaction khóa ngược chiều.

### 17.3. Transaction ngắn

- Không gọi HTTP/email trong khi đang giữ row lock.
- Không đợi input từ người dùng.
- Chỉ khóa những dòng cần.
- Tạo index cho predicate khóa phù hợp để tránh quét/chờ không cần thiết.
- Chọn isolation level theo yêu cầu.

### 17.4. Retry deadlock

`40P01` thường có thể retry **toàn bộ transaction** với giới hạn lần thử và backoff. Không chỉ retry statement cuối vì các quyết định trước đó có thể dựa trên trạng thái đã thay đổi.

## 18. Isolation level và serialization failure

JDBC có các mức isolation chuẩn:

| JDBC | Ý nghĩa |
|---|---|
| `TRANSACTION_READ_UNCOMMITTED` | Đọc chưa commit theo định nghĩa chuẩn; PostgreSQL xử lý tương đương `READ COMMITTED` |
| `TRANSACTION_READ_COMMITTED` | Mỗi statement đọc snapshot phù hợp tại đầu statement trong PostgreSQL |
| `TRANSACTION_REPEATABLE_READ` | Snapshot nhất quán trong transaction; PostgreSQL ngăn một số anomaly nhưng vẫn có thể có write skew |
| `TRANSACTION_SERIALIZABLE` | Bảo đảm kết quả tương đương thực thi tuần tự; có thể hủy transaction với `40001` |

### 18.1. Chọn isolation không phải càng cao càng tốt

Isolation cao hơn có thể phát hiện/xử lý nhiều xung đột hơn, nhưng tăng khả năng transaction bị hủy và phải retry. Chọn theo invariant nghiệp vụ:

- Có thể chấp nhận đọc trạng thái mới theo từng statement?
- Có cần giữ snapshot ổn định?
- Hai thao tác có thể ghi lệch nhau nhưng vẫn thỏa constraint từng dòng?
- Có cần đảm bảo một quy tắc trên toàn tập dữ liệu?

### 18.2. JDBC đặt isolation

```java
connection.setTransactionIsolation(
    Connection.TRANSACTION_SERIALIZABLE
);
connection.setAutoCommit(false);

try {
    performBusinessTransaction(connection);
    connection.commit();
} catch (SQLException exception) {
    connection.rollback();
    throw exception;
}
```

Việc đặt isolation trên connection pool có thể thay đổi trạng thái connection; hãy bảo đảm reset theo framework/pool. Trong PostgreSQL, có thể dùng `SET TRANSACTION ISOLATION LEVEL ...` trước câu query đầu tiên trong transaction.

### 18.3. Serialization failure phải retry từ đầu

Một transaction serializable:

```text
BEGIN
READ A
READ B
UPDATE A
COMMIT → 40001
```

phải bắt đầu lại toàn bộ quy trình trên snapshot mới, không chỉ gọi `commit()` lần nữa.

## 19. Quy tắc retry: lỗi nào được thử lại?

Retry là một quyết định về **ngữ nghĩa nghiệp vụ**, không phải chỉ nhìn exception có vẻ tạm thời.

### 19.1. Ma trận khuyến nghị tổng quát

| Nhóm/lỗi | Thường nên retry tự động? | Hướng xử lý |
|---|---|---|
| `22` — data exception | Không | Trả validation error; sửa dữ liệu |
| `23` — constraint violation | Thường không | Phân biệt duplicate/FK/check; xử lý theo nghiệp vụ |
| `08` — connection exception khi chưa gửi lệnh | Có thể | Lấy connection mới, retry thao tác idempotent |
| `08` — mất kết nối khi execute/commit | Không mù quáng | Xác định outcome; dùng idempotency/reconciliation |
| `40001` | Thường có, giới hạn | Rollback và retry toàn transaction |
| `40P01` | Thường có, giới hạn | Rollback và retry toàn transaction |
| `55P03` | Tùy chính sách | Trả conflict hoặc chờ/thử lại ngắn |
| `57014` | Thường không mặc định | Xác định timeout/cancel; sửa query hoặc phản hồi |
| `25P02` | Không | Rollback transaction hoặc rollback savepoint |
| Lỗi cú pháp/schema `42` | Không | Sửa SQL/deployment/schema |

Đây là ma trận tham khảo cho PostgreSQL/JDBC; DBMS và driver có thể khác.

### 19.2. Backoff và jitter

Nếu retry deadlock hoặc serialization failure, tránh cho hàng trăm request retry cùng một thời điểm:

```text
Lần 1: đợi khoảng 50 ms + jitter
Lần 2: đợi khoảng 100 ms + jitter
Lần 3: đợi khoảng 200 ms + jitter
Sau đó dừng và trả lỗi
```

Con số chỉ minh họa. Cần cấu hình theo latency/SLA và giới hạn tải. Jitter giúp các request không đồng bộ retry lại cùng lúc.

### 19.3. Giới hạn số lần retry

Không retry vô hạn. Cần:

- Số lần thử tối đa.
- Deadline tổng.
- Backoff có jitter.
- Metrics số lần retry.
- Logging nguyên nhân SQLState.
- Cơ chế circuit breaker nếu database đang quá tải.

Retry làm tăng tải database; một outage có thể tệ hơn nếu mọi request cứ thử lại liên tục.

## 20. Mất kết nối lúc commit: outcome không xác định

Đây là tình huống khó nhất:

```text
Application             Database
-----------             --------
INSERT order
                        INSERT thành công
COMMIT ---------------->
                        COMMIT thành công
<----- response bị mất
Socket timeout
```

Ứng dụng nhận exception và không biết commit đã thành công. Nếu retry một `INSERT` không có idempotency, có thể tạo hai đơn hàng.

### 20.1. Đừng suy ra rollback từ connection exception

Mất kết nối không chứng minh transaction đã rollback. Server có thể đã commit trước khi phản hồi bị mất.

### 20.2. Idempotency key

Một request tạo đơn có thể mang `request_id` duy nhất:

```sql
CREATE TABLE app_error_lab_requests (
    request_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL UNIQUE,
    result_status TEXT NOT NULL
);
```

Trong cùng transaction, ghi idempotency key và dữ liệu nghiệp vụ:

```sql
BEGIN;

INSERT INTO app_error_lab_requests
    (request_id, order_id, result_status)
VALUES
    ('550e8400-e29b-41d4-a716-446655440001',
     5001, 'CREATED');

INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES
    (5001, 1, 100, 'PENDING');

COMMIT;
```

Nếu client không nhận phản hồi, nó gửi lại **cùng request_id**. Ứng dụng có thể query bảng request để xác định kết quả đã commit hay chưa.

### 20.3. Không chỉ dùng idempotency key ở tầng Java

Để đảm bảo đồng thời, key cần được bảo vệ bằng `PRIMARY KEY`/`UNIQUE` ở database. Nếu chỉ query “đã thấy request id chưa?” rồi insert mà không có unique constraint, hai request đồng thời vẫn có thể tạo trùng.

### 20.4. Idempotency không tự giải quyết mọi side effect

Nếu transaction đã ghi đơn và outbox nhưng email được gửi ngoài transaction, retry cần bảo đảm email không gửi lặp. Thường dùng outbox + consumer idempotent hoặc một khóa deduplication cho từng side effect.

## 21. Retry cả transaction trong Java

Một skeleton PostgreSQL:

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;

public final class TransactionRunner {
    private final javax.sql.DataSource dataSource;

    public TransactionRunner(javax.sql.DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public <T> T runWithRetry(SqlWork<T> work) throws SQLException {
        int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection connection = dataSource.getConnection()) {
                connection.setAutoCommit(false);
                connection.setTransactionIsolation(
                    Connection.TRANSACTION_READ_COMMITTED
                );

                try {
                    T result = work.execute(connection);
                    connection.commit();
                    return result;
                } catch (SQLException failure) {
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }

                    if (!isRetryableTransactionConflict(failure)
                            || attempt == maxAttempts) {
                        throw failure;
                    }
                }
            }

            sleepWithBackoff(attempt);
        }

        throw new SQLException("Transaction retry exhausted");
    }

    private static boolean isRetryableTransactionConflict(
            SQLException exception) {
        String state = exception.getSQLState();
        return "40001".equals(state) || "40P01".equals(state);
    }

    private static void sleepWithBackoff(int attempt) throws SQLException {
        long baseMillis = 50L * (1L << (attempt - 1));
        long jitter = ThreadLocalRandom.current()
            .nextLong(0, Math.max(1, baseMillis / 2));

        try {
            Thread.sleep(baseMillis + jitter);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new SQLException("Retry interrupted", interrupted);
        }
    }

    @FunctionalInterface
    public interface SqlWork<T> {
        T execute(Connection connection) throws SQLException;
    }
}
```

Đây là skeleton để minh họa **retry transaction conflict**:

- Mỗi lần thử lấy connection mới.
- Mỗi lần chạy lại toàn bộ `work`.
- Chỉ retry `40001`/`40P01`.
- Rollback trước khi thử lại.
- Có số lần thử và backoff.

### 21.1. Giới hạn quan trọng của skeleton

Không dùng đoạn này để retry mọi lỗi kết nối. Nếu `commit()` ném connection exception, kết quả transaction có thể không xác định; cần idempotency/reconciliation riêng. Ngoài ra:

- `work` không được gửi email/gọi thanh toán bên ngoài như side effect không idempotent.
- Không được nuốt exception bên trong rồi trả kết quả thành công giả.
- Cần áp deadline tổng và cấu hình pool/statement timeout.
- Khi rollback thất bại, connection nên được pool/driver loại bỏ nếu trạng thái không đáng tin.

## 22. Phân biệt retry statement và retry transaction

Giả sử:

```sql
BEGIN;
SELECT balance FROM accounts WHERE id = 1;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
INSERT INTO audit_log (...);
COMMIT;
```

Nếu commit báo `40001`, không chỉ chạy lại `COMMIT` hoặc `UPDATE`. Các quyết định phụ thuộc `balance` trước đó phải được tính lại từ snapshot mới.

```text
Sai:
  retry statement cuối

Đúng:
  rollback transaction cũ
  mở transaction mới
  đọc lại dữ liệu
  tính lại quyết định
  chạy toàn bộ ghi
  commit
```

## 23. Phân biệt lỗi đồng thời và lỗi constraint

Một request insert email đã tồn tại có thể nhận `23505`. Nguyên nhân có thể là:

- Email đã tồn tại trước request.
- Hai request đăng ký cùng lúc.

Trong cả hai trường hợp database trả **constraint violation**, không nhất thiết `40001`.

Tương tự, một `UPDATE` có thể trả `23514` vì giá trị âm; không phải cứ transaction bị ảnh hưởng bởi cạnh tranh thì SQLState sẽ thuộc class `40`.

### 23.1. Mỗi mã lỗi phản ánh điều gì?

| Tình huống | SQLState thường gặp | Phân loại chính |
|---|---|---|
| Hai request cùng insert unique key | `23505` | Constraint conflict |
| Hai transaction deadlock | `40P01` | Transaction rollback |
| Serializable transaction không thể commit | `40001` | Transaction rollback |
| `SELECT ... FOR UPDATE NOWAIT` không lấy được lock | `55P03` | Lock/resource conflict |
| `UPDATE ... WHERE version_no=?` không cập nhật dòng nào | Không có SQL exception | Optimistic conflict ở logic ứng dụng |

Không thể chỉ nhìn “có cạnh tranh” để chọn một mã lỗi; phải đọc cách database biểu diễn sự kiện.

## 24. Batch import và tách dòng lỗi

Giả sử import 1000 đơn:

- 970 dòng hợp lệ.
- 20 dòng có số tiền sai format.
- 5 dòng thiếu customer.
- 5 dòng trùng order ID.

Một thiết kế tốt cần trả kết quả **theo dòng**, không chỉ “batch thất bại”.

### 24.1. Staging table

```sql
CREATE TABLE app_order_import_stage (
    batch_id UUID NOT NULL,
    row_no INTEGER NOT NULL,
    raw_order_id TEXT,
    raw_customer_id TEXT,
    raw_amount TEXT,
    raw_status TEXT,
    PRIMARY KEY (batch_id, row_no)
);
```

Nạp raw values trước, rồi validate và chuyển kiểu theo một quy trình có thể kiểm tra. Có thể ghi:

```text
row_no | status       | reason
-------+--------------+------------------------
12     | INVALID      | AMOUNT_NOT_NUMERIC
18     | INVALID      | CUSTOMER_NOT_FOUND
27     | INVALID      | DUPLICATE_ORDER_ID
```

### 24.2. Vì sao staging hữu ích?

- Lưu dữ liệu gốc để điều tra.
- Không để một dòng xấu phá cả quá trình parse trước khi biết dòng nào sai.
- Có thể kiểm tra trùng trong batch bằng SQL set-based.
- Tách validation lỗi dữ liệu khỏi lỗi constraint khi ghi bảng chính.
- Có thể chạy lại một batch theo policy rõ ràng.

### 24.3. Không biến mọi lỗi thành lỗi dòng

Nếu database mất kết nối giữa lúc import, đó là lỗi hạ tầng, không phải 1000 dòng dữ liệu sai. Không ghi từng dòng thành “INVALID” chỉ vì batch không thể tiếp tục.

## 25. JDBC batch và transaction

Ví dụ:

```java
String sql = """
    INSERT INTO app_error_lab_orders
        (order_id, customer_id, amount, status)
    VALUES (?, ?, ?, ?)
    """;

connection.setAutoCommit(false);

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    for (OrderRow row : rows) {
        statement.setLong(1, row.orderId());
        statement.setLong(2, row.customerId());
        statement.setBigDecimal(3, row.amount());
        statement.setString(4, row.status());
        statement.addBatch();
    }

    int[] counts = statement.executeBatch();
    connection.commit();
} catch (BatchUpdateException exception) {
    connection.rollback();
    throw exception;
} catch (SQLException exception) {
    connection.rollback();
    throw exception;
}
```

### 25.1. BatchUpdateException không có nghĩa các dòng trước đã commit

Trong transaction explicit, lỗi có thể làm transaction bị aborted. Dù driver báo update counts cho một số phần tử, rollback toàn transaction có thể hoàn tác các thay đổi.

### 25.2. Khi muốn tiếp tục với dòng hợp lệ

Có thể:

- Validate trước và chỉ batch dòng hợp lệ.
- Chia thành các batch nhỏ.
- Dùng savepoint cho từng nhóm.
- Dùng staging table và `INSERT ... SELECT` sau validation.

Đừng tự giả định driver luôn dừng tại dòng đầu tiên hoặc luôn tiếp tục hết batch; hành vi cụ thể phụ thuộc driver.

## 26. Ánh xạ lỗi database sang lỗi domain/API

Không nên để tầng controller nhận `SQLException` rồi tự đọc message. Tầng repository/service nên chuyển thành lỗi domain có ý nghĩa.

Ví dụ:

```java
sealed class AppDatabaseException extends RuntimeException
    permits InvalidDataException,
            ConstraintConflictException,
            DatabaseUnavailableException,
            ConcurrentUpdateException {

    AppDatabaseException(String message, Throwable cause) {
        super(message, cause);
    }
}

final class InvalidDataException extends AppDatabaseException {
    InvalidDataException(String message, Throwable cause) {
        super(message, cause);
    }
}

final class ConstraintConflictException extends AppDatabaseException {
    ConstraintConflictException(String message, Throwable cause) {
        super(message, cause);
    }
}

final class DatabaseUnavailableException extends AppDatabaseException {
    DatabaseUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}

final class ConcurrentUpdateException extends AppDatabaseException {
    ConcurrentUpdateException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Đây là mô hình minh họa; có thể dùng checked exception, record result hoặc exception hierarchy của framework hiện có.

### 26.1. Mapper theo SQLState

```java
static RuntimeException toDomainException(SQLException exception) {
    String state = exception.getSQLState();

    if (state == null) {
        return new DatabaseUnavailableException(
            "Database operation failed",
            exception
        );
    }

    if (state.startsWith("22")) {
        return new InvalidDataException(
            "A value could not be stored",
            exception
        );
    }

    if (state.startsWith("23")) {
        return new ConstraintConflictException(
            "The operation conflicts with a data constraint",
            exception
        );
    }

    if ("40001".equals(state) || "40P01".equals(state)) {
        return new ConcurrentUpdateException(
            "The transaction conflicted with another transaction",
            exception
        );
    }

    if (state.startsWith("08")) {
        return new DatabaseUnavailableException(
            "Database connection failed",
            exception
        );
    }

    return new RuntimeException("Database operation failed", exception);
}
```

Không gộp mọi class `40` vào cùng domain error nếu một mã có semantics khác. Tương tự, SQLState null không chứng minh database down; có thể driver không cung cấp SQLState hoặc lỗi nằm ở tầng khác.

### 26.2. HTTP mapping là quyết định của API

Một API REST có thể cân nhắc:

| Lỗi domain | HTTP thường cân nhắc | Ghi chú |
|---|---:|---|
| Input không hợp lệ | `400` hoặc `422` | Theo contract API |
| Unique/business conflict | `409` | Có thể cần mã lỗi cụ thể |
| Optimistic version conflict | `409` | Client cần tải lại/merge |
| Database tạm không sẵn sàng | `503` | Có thể kèm Retry-After nếu phù hợp |
| Timeout | `504` hoặc lỗi nội bộ theo kiến trúc | Xem request đi qua gateway nào |
| Lỗi hệ thống không phân loại | `500` | Không lộ SQL nội bộ |

Không trả nguyên message PostgreSQL, SQL statement, schema name hoặc stack trace cho client. Log nội bộ có kiểm soát; client nhận mã lỗi ổn định và thông báo an toàn.

## 27. Phân biệt lỗi dữ liệu với lỗi nghiệp vụ

Không phải mọi giá trị không mong muốn đều là SQL exception.

Ví dụ:

```text
amount = -10.00
```

có thể:

- Là dữ liệu sai theo hợp đồng → validation error.
- Là số âm hợp lệ cho hoàn tiền → domain operation khác.
- Bị database từ chối bởi CHECK → constraint violation.

Tương tự:

```text
customer_id = 999
```

có thể là ID sai định dạng, customer không tồn tại, customer bị xóa, hoặc user không có quyền nhìn thấy customer.

### 27.1. Lỗi nghiệp vụ không nên được suy ra chỉ từ SQLState

`23503` cho biết FK không thỏa, nhưng không tự nói nên trả “khách hàng không tồn tại”, “đơn vị bị xóa” hay “không có quyền”. Service cần biết ngữ cảnh nghiệp vụ và tránh tiết lộ thông tin nhạy cảm.

### 27.2. Tránh dò tồn tại trái phép

Nếu API trả thông báo quá chi tiết cho FK/unique, kẻ tấn công có thể dùng nó để dò email, tài khoản hoặc ID. Có những hệ thống cố ý dùng thông báo chung và logging nội bộ để giảm rò rỉ.

## 28. Observability: log, metrics và correlation

Khi phân loại lỗi, mục tiêu không chỉ là catch exception mà còn phải trả lời:

- Lỗi gì xảy ra?
- Tại operation nào?
- Với request/batch nào?
- Tần suất tăng hay giảm?
- Có phải một DB instance hoặc một constraint cụ thể?
- Retry có thành công không?

### 28.1. Log fields gợi ý

```text
timestamp
service
operation
request_id / correlation_id
transaction_attempt
sql_state
vendor_code
exception_class
constraint_name (nếu có, đã kiểm soát)
database_name/instance alias (không lộ credential)
duration_ms
retry_count
```

Không log raw password, access token, full payment payload, PII không cần thiết hoặc toàn bộ SQL parameters nếu chúng nhạy cảm.

### 28.2. Metrics

Có thể theo dõi số lượng theo class/mã:

```text
db_errors_total{class="22"}
db_errors_total{class="23"}
db_errors_total{class="08"}
db_errors_total{class="40"}
db_transaction_retries_total{reason="40001"}
db_transaction_retries_total{reason="40P01"}
db_connection_acquire_timeout_total
db_statement_timeout_total
```

Không gắn giá trị tự do như email, SQL text, customer ID vào label metrics vì cardinality tăng cao và có thể lộ dữ liệu.

### 28.3. Phân biệt lỗi gốc và lỗi phát sinh khi rollback

Nếu query ban đầu báo `23505`, nhưng `rollback()` tiếp theo cũng lỗi vì connection đã mất, hãy giữ cả hai:

- Exception gốc: lý do transaction thất bại.
- Suppressed/rollback exception: việc cleanup cũng gặp sự cố.

Không ghi đè nguyên nhân gốc bằng lỗi cleanup.

## 29. Timeout theo từng lớp

Các timeout khác nhau bảo vệ tài nguyên khác nhau.

| Timeout | Vị trí | Ý nghĩa |
|---|---|---|
| Pool acquire timeout | Connection pool | Chờ connection khả dụng quá lâu |
| Connect timeout | JDBC driver/network | Không mở được kết nối trong hạn |
| Socket/read timeout | Driver/network | Không nhận dữ liệu kịp |
| JDBC query timeout | `Statement.setQueryTimeout` | Driver yêu cầu hủy query sau thời gian |
| PostgreSQL `statement_timeout` | Server | Hủy statement chạy quá hạn |
| PostgreSQL `lock_timeout` | Server | Hủy khi chờ khóa quá hạn |
| Transaction timeout (nếu hệ thống hỗ trợ) | Transaction manager/DB | Giới hạn transaction mở lâu |

### 29.1. `setQueryTimeout`

```java
try (PreparedStatement statement =
        connection.prepareStatement("SELECT ...")) {
    statement.setQueryTimeout(5); // giây, theo JDBC API
    try (ResultSet result = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
```

Driver có thể triển khai timeout theo cách riêng. Không đồng nhất query timeout với connection timeout.

### 29.2. PostgreSQL `statement_timeout` và `lock_timeout`

```sql
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '500ms';
```

`SET LOCAL` có hiệu lực trong transaction hiện tại. `statement_timeout` giới hạn thời gian statement; `lock_timeout` giới hạn thời gian chờ lock. Đặt lock timeout nhỏ hơn statement timeout thường giúp lỗi chờ khóa được nhận diện trước khi tổng thời gian statement hết.

Không cấu hình timeout quá thấp đến mức các query hợp lệ thường xuyên bị hủy, cũng không để timeout vô hạn mà không có lý do vận hành.

## 30. Một quy trình xử lý lỗi trong repository

Một luồng JDBC nên có các bước:

```text
1. Nhận dữ liệu đã validate
2. Lấy connection
3. Mở transaction
4. Thực hiện SQL
5. Nếu thành công: commit
6. Nếu lỗi:
     ├─ đọc SQLState/exception chain
     ├─ rollback nếu transaction còn có thể rollback
     ├─ đóng resource
     ├─ phân loại domain error
     └─ retry chỉ khi policy cho phép
7. Ghi log/metric đã masking
8. Trả response ổn định
```

### 30.1. Mẫu helper không che exception gốc

```java
static void rollbackQuietly(
        Connection connection,
        SQLException original) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        original.addSuppressed(rollbackFailure);
    }
}
```

Tên `rollbackQuietly` ở đây không có nghĩa bỏ qua cleanup error; nó giữ lỗi rollback trong `getSuppressed()`.

### 30.2. Không catch `Exception` rồi tiếp tục

Mẫu nguy hiểm:

```java
try {
    repository.save(order);
} catch (Exception ignored) {
}

return "success";
```

Nó biến lỗi dữ liệu, constraint, connection và concurrency thành thành công giả. Chỉ bắt lỗi khi có hành động phục hồi rõ ràng; nếu không, truyền lên tầng chịu trách nhiệm.

## 31. Các kịch bản tích hợp

### 31.1. Request ghi số tiền sai

```text
Input amount = "abc"
       ↓
BigDecimal parse thất bại
       ↓
Validation error
       ↓
Không mở transaction/không gửi SQL
```

Nếu dữ liệu vẫn tới DB qua một đường khác, PostgreSQL có thể trả `22P02`.

### 31.2. Hai request đăng ký cùng email

```text
Request A ─┐
           ├── UNIQUE(email) tại DB
Request B ─┘

Một request thành công
Một request nhận 23505
```

Service ánh xạ thành duplicate/conflict theo API contract. Không retry cùng email một cách mù quáng.

### 31.3. Worker lấy cùng một job

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 1;

UPDATE job_queue
SET status = 'PROCESSING'
WHERE job_id = ?;

COMMIT;
```

Worker khác bỏ qua row đã khóa và lấy job khác. Sau commit, worker xử lý công việc ngoài DB; kết quả nên được ghi với idempotency hoặc state transition rõ.

### 31.4. Mất kết nối khi commit đơn hàng

```text
Client gửi request_id
       ↓
DB transaction ghi request_id + order
       ↓
COMMIT response mất
       ↓
Client gửi lại cùng request_id
       ↓
Service tra cứu kết quả hoặc nhận duplicate key
       ↓
Không tạo đơn thứ hai
```

Đây là vai trò của idempotency key và unique constraint, không phải retry mọi `SQLException`.

## 32. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| Bắt mọi `SQLException` rồi trả “input sai” | Che lỗi kết nối và concurrency | Phân loại SQLState |
| Phân loại bằng message | Phụ thuộc ngôn ngữ/driver/version | SQLState + exception chain |
| Nhầm `22` với `23` | Không biết lỗi cast hay constraint | Đọc class/mã cụ thể |
| Nhầm `23505` là lỗi dữ liệu format | Xử lý sai duplicate/race | Kiểm tra unique constraint |
| Retry `23505` vô hạn | Cùng dữ liệu vẫn thất bại | Trả conflict hoặc idempotency logic |
| Retry `40001` chỉ ở statement cuối | Quyết định cũ vẫn dựa snapshot cũ | Retry toàn transaction |
| Retry connection exception lúc commit ngay | Có thể tạo bản ghi trùng | Reconcile outcome + idempotency |
| Cho rằng rollback exception là nguyên nhân đầu tiên | Mất dấu lỗi gốc | Giữ suppressed exception |
| Sau SQL error tiếp tục chạy PostgreSQL transaction | `25P02` | Rollback hoặc rollback savepoint |
| Catch lỗi constraint rồi coi như insert thành công | App và DB lệch | Chỉ xử lý duplicate khi semantics rõ |
| SELECT kiểm tra unique trước INSERT | Race condition | UNIQUE constraint/ON CONFLICT |
| Đọc rồi ghi tồn kho bằng hai statement không khóa | Lost update | Atomic UPDATE/locking/version |
| Retry optimistic conflict tự động bằng version mới | Có thể ghi đè chỉnh sửa người khác | Trả conflict/merge |
| Giữ row lock khi gọi HTTP | Deadlock/chờ lâu | Transaction ngắn |
| Không có thứ tự khóa nhất quán | Tăng deadlock | Khóa theo thứ tự ổn định |
| Dùng `SKIP LOCKED` nhưng không quản lý trạng thái job | Job có thể bị bỏ/quay lại | State machine, lease, retry |
| Dùng savepoint cho lỗi connection | Connection đã hỏng | Reconnect và xác định outcome |
| Giả định batch partial counts đã commit | Dữ liệu không nhất quán | Xem transaction và rollback |
| Retry vô hạn | Bão tải database | Bounded retry + backoff + jitter |
| Log toàn bộ SQL và parameters | Lộ PII/secret | Masking, SQLState, correlation ID |
| Trả message database cho API | Lộ schema/implementation | Domain error an toàn |

## 33. Bài tập tự luyện

Các bài tập sử dụng PostgreSQL, JDBC và các bảng `app_error_lab_*` ở mục 3. Với thao tác có thể làm thay đổi dữ liệu, hãy dùng database test và transaction rollback thích hợp.

### Bài 1 — Phân loại SQLState

Xác định nhóm cho các mã:

```text
22P02
23505
08006
40001
40P01
25P02
55P03
57014
```

### Bài 2 — Data hay constraint?

Phân loại:

1. `'twelve'` ghi vào `NUMERIC`.
2. `-10` ghi vào cột có `CHECK (amount >= 0)`.
3. `NULL` ghi vào `NOT NULL`.
4. Số quá lớn ghi vào `NUMERIC(12,2)`.

### Bài 3 — Unique race

Hai request cùng đăng ký `email='a@example.test'`. Vì sao `SELECT` kiểm tra trước rồi `INSERT` không đủ? Cơ chế database nào bảo vệ cuối cùng?

### Bài 4 — Foreign key

Ghi `customer_id=999999` khi không có customer. SQLState PostgreSQL thường gặp là gì? Đây có nhất thiết là lỗi cú pháp dữ liệu không?

### Bài 5 — Check constraint

Viết một câu `INSERT` tạo lỗi `23514` trên bảng lab. Giải thích tại sao giá trị vẫn là numeric hợp lệ.

### Bài 6 — SQLState trong JDBC

Viết Java lấy `getSQLState()`, hai ký tự đầu và `getErrorCode()` từ một `SQLException`.

### Bài 7 — Không phân loại bằng message

Nêu ít nhất ba lý do vì sao `getMessage().contains("duplicate")` không đáng tin để xác định unique violation.

### Bài 8 — Exception chain

Viết vòng lặp đọc `SQLException.getNextException()` và nêu thông tin nên log.

### Bài 9 — Connection exception

Phân biệt:

1. Không lấy được connection từ pool.
2. Không connect được database.
3. Mất socket khi đọc ResultSet.
4. Mất phản hồi ngay sau COMMIT.

Trường hợp nào có outcome không xác định?

### Bài 10 — Transaction aborted

Trong PostgreSQL, một câu lệnh vi phạm CHECK bên trong `BEGIN` thất bại. Vì sao câu `SELECT` tiếp theo báo `25P02`? Làm sao khôi phục?

### Bài 11 — Savepoint

Viết SQL tạo savepoint, thử insert amount âm, rollback về savepoint, rồi insert dòng hợp lệ và commit.

### Bài 12 — Retry

Những lỗi nào trong các lỗi sau thường được cân nhắc retry toàn transaction: `22P02`, `23505`, `40001`, `40P01`, `08006`?

### Bài 13 — Lost update

Hai transaction cùng đọc stock 1, rồi đều ghi stock 0. Giải thích lỗi và viết câu `UPDATE` nguyên tử chỉ trừ khi stock > 0.

### Bài 14 — Optimistic locking

Viết `UPDATE ... WHERE version_no=?` và cách nhận biết xung đột bằng update count.

### Bài 15 — Pessimistic locking

Viết câu `SELECT ... FOR UPDATE` và giải thích vì sao không nên giữ transaction trong lúc gọi HTTP.

### Bài 16 — Deadlock

Mô tả deadlock hai transaction khóa hai dòng theo thứ tự ngược nhau. Nêu cách giảm nguy cơ và SQLState PostgreSQL.

### Bài 17 — Serialization

SQLState `40001` có nghĩa gì? Vì sao retry chỉ câu lệnh cuối là không đủ?

### Bài 18 — NOWAIT và SKIP LOCKED

Phân biệt `FOR UPDATE NOWAIT` với `FOR UPDATE SKIP LOCKED`. Mỗi cách phù hợp tình huống nào?

### Bài 19 — Commit outcome không chắc chắn

Ứng dụng gửi `COMMIT`, mạng đứt trước khi nhận response. Vì sao không được kết luận transaction rollback? Đề xuất cơ chế idempotency.

### Bài 20 — JDBC batch

`BatchUpdateException.getUpdateCounts()` có một số phần tử thành công. Có thể kết luận chúng đã commit không? Vì sao?

### Bài 21 — Savepoint và connection loss

Vì sao không thể dùng `ROLLBACK TO SAVEPOINT` sau khi connection vật lý đã mất?

### Bài 22 — Domain mapping

Đề xuất ánh xạ lỗi SQLState `22`, `23`, `08`, `40` sang các lỗi domain/API. Vì sao không trả nguyên message database cho client?

### Bài 23 — Retry backoff

Thiết kế retry tối đa ba lần cho `40001`/`40P01`, có backoff và jitter. Nêu vì sao retry vô hạn nguy hiểm.

### Bài 24 — Idempotency key

Thiết kế một bảng chứa `request_id UUID PRIMARY KEY` và mô tả cách dùng khi client không biết request trước đã commit hay chưa.

### Bài 25 — Timeout

Phân biệt pool acquire timeout, connect timeout, statement timeout và lock timeout. `57014` có luôn đồng nghĩa database mất kết nối không?

### Bài 26 — Phân biệt lỗi constraint và xung đột optimistic

`23505` và update count bằng 0 trong optimistic locking khác nhau thế nào? Trường hợp nào không có `SQLException`?

### Bài 27 — Import dữ liệu

Một batch có 1000 dòng, trong đó có 20 dòng sai số tiền, 5 dòng thiếu customer và 5 dòng duplicate ID. Đề xuất staging/validation/insert để báo lỗi theo từng dòng.

### Bài 28 — Logging an toàn

Đề xuất các field log và metrics cho lỗi DB. Nêu dữ liệu nào không nên đưa vào log hoặc metric label.

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:**

| Mã | Nhóm |
|---|---|
| `22P02` | Lỗi dữ liệu |
| `23505` | Vi phạm unique |
| `08006` | Lỗi kết nối |
| `40001` | Serialization failure |
| `40P01` | Deadlock |
| `25P02` | Transaction đang ở trạng thái lỗi |
| `55P03` | Không lấy được lock |
| `57014` | Query bị hủy |

**Bài 2:**

1. `'twelve'` → data exception `22P02`.
2. `-10` → CHECK violation `23514`.
3. `NULL` → NOT NULL violation `23502`.
4. Số quá lớn → numeric out of range `22003`.

**Bài 3:** Hai request có thể cùng thấy email chưa tồn tại. `UNIQUE(email)` trong database là lớp bảo vệ cuối. Xử lý `23505` hoặc dùng `ON CONFLICT` theo semantics.

**Bài 4:** `23503`, foreign key violation. Đây là lỗi tham chiếu/toàn vẹn, không phải lỗi cú pháp SQL; nguyên nhân nghiệp vụ cần xem ngữ cảnh.

**Bài 5:**

```sql
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES (9001, 1, -1, 'PENDING');
```

`-1` là numeric hợp lệ; constraint `amount >= 0` bị vi phạm.

**Bài 6:**

```java
String state = exception.getSQLState();
String stateClass =
    state != null && state.length() >= 2
        ? state.substring(0, 2)
        : "UNKNOWN";
int vendorCode = exception.getErrorCode();
```

**Bài 7:** Message phụ thuộc DBMS/driver/version, ngôn ngữ và chi tiết constraint/dữ liệu; không phải mã ổn định. SQLState `23505` phù hợp hơn trong PostgreSQL.

**Bài 8:**

```java
for (SQLException e = exception; e != null; e = e.getNextException()) {
    log(e.getSQLState(), e.getErrorCode(),
        e.getClass().getName());
}
```

Log thêm operation, correlation ID, duration và retry count; mask dữ liệu nhạy cảm.

**Bài 9:** Pool timeout là chưa lấy được logical connection; connect timeout là không mở được connection; socket loss là mất liên lạc trong khi thao tác; mất response sau COMMIT có thể không xác định transaction đã commit hay chưa. Trường hợp cuối rõ nhất có outcome không xác định; socket loss trong execute cũng có thể cần reconciliation tùy thời điểm.

**Bài 10:** Statement lỗi làm transaction PostgreSQL aborted. Statement tiếp theo nhận `25P02`; chạy `ROLLBACK` toàn transaction hoặc `ROLLBACK TO SAVEPOINT` đã tạo trước lỗi.

**Bài 11:**

```sql
BEGIN;
SAVEPOINT s1;
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES (9002, 1, -5, 'PENDING');
ROLLBACK TO SAVEPOINT s1;
INSERT INTO app_error_lab_orders
    (order_id, customer_id, amount, status)
VALUES (9003, 1, 5, 'PENDING');
COMMIT;
```

**Bài 12:** `40001` và `40P01` thường được cân nhắc retry toàn transaction. `22P02`/`23505` thường không; `08006` không retry mù quáng vì outcome có thể không rõ, đặc biệt lúc commit.

**Bài 13:** Cả hai đọc stock cũ 1 nên ghi đè nhau. Câu nguyên tử:

```sql
UPDATE inventory
SET stock = stock - 1
WHERE product_id = ?
  AND stock > 0
RETURNING stock;
```

Kiểm tra có dòng trả về.

**Bài 14:**

```sql
UPDATE profile
SET display_name = ?, version_no = version_no + 1
WHERE profile_id = ? AND version_no = ?;
```

`executeUpdate()` bằng 0 cho biết không có dòng khớp; có thể do version đã thay đổi hoặc ID không tồn tại.

**Bài 15:**

```sql
BEGIN;
SELECT stock FROM inventory WHERE product_id = 10 FOR UPDATE;
-- Kiểm tra/cập nhật trong cùng transaction.
COMMIT;
```

Giữ lock khi gọi HTTP khiến transaction/row lock lâu, làm request khác chờ và tăng deadlock.

**Bài 16:** A khóa row 1 rồi row 2; B khóa row 2 rồi row 1. Khóa theo cùng thứ tự ID, transaction ngắn. PostgreSQL báo `40P01`.

**Bài 17:** `40001` là serialization failure; toàn transaction bị hủy vì các quyết định dựa snapshot không còn có thể serialize. Phải đọc lại dữ liệu và thực hiện lại toàn bộ.

**Bài 18:** `NOWAIT` lỗi ngay nếu không lấy được lock; `SKIP LOCKED` bỏ qua dòng đang khóa và lấy dòng khác, phù hợp worker queue.

**Bài 19:** Server có thể commit trước khi response mất. Dùng request UUID có unique constraint, ghi request và dữ liệu nghiệp vụ trong cùng transaction; khi retry cùng key, query kết quả đã ghi thay vì tạo bản ghi mới.

**Bài 20:** Không. Update counts phản ánh kết quả driver báo cho từng phần tử batch, không khẳng định commit. Transaction có thể bị rollback toàn bộ.

**Bài 21:** Savepoint nằm trong transaction trên connection đó; khi connection vật lý mất, session/transaction không còn để rollback tới savepoint.

**Bài 22:** `22` → validation/data error; `23` → constraint/business conflict; `08` → service unavailable hoặc reconciliation; `40` → retry transaction hoặc concurrency conflict. Không trả nguyên SQL message vì lộ schema/chi tiết nội bộ.

**Bài 23:** Tối đa 3 lần, exponential backoff ngắn + jitter; retry toàn transaction. Retry vô hạn tạo bão tải, tăng latency và làm outage kéo dài.

**Bài 24:**

```sql
CREATE TABLE request_dedup (
    request_id UUID PRIMARY KEY,
    result_payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Ghi request ID và kết quả nghiệp vụ trong cùng transaction; request gửi lại cùng ID sẽ tra cứu hoặc xử lý duplicate theo hợp đồng.

**Bài 25:** Pool timeout là chờ connection; connect timeout là thiết lập kết nối; statement timeout là query chạy quá lâu; lock timeout là chờ khóa quá lâu. `57014` là query canceled, không tự chứng minh connection mất.

**Bài 26:** `23505` là database ném constraint exception. Optimistic update count 0 là câu SQL chạy hợp lệ nhưng không tìm thấy dòng có version mong đợi; không nhất thiết có `SQLException`.

**Bài 27:** Nạp raw vào staging với `batch_id`/`row_no`; validate parse số, customer existence và duplicate trong batch; ghi reason cho từng dòng; chỉ insert các dòng valid, vẫn giữ unique/FK/check ở bảng chính để xử lý race.

**Bài 28:** Log SQLState, vendor code, operation, correlation ID, duration, attempt, constraint name khi an toàn; metrics theo class/state. Không log password, token, raw PII, full payload hoặc dùng email/ID tự do làm metric label.

</details>

## 34. Checklist xử lý một SQLException

Khi gặp `SQLException`, thực hiện theo trình tự:

1. **Xác định giai đoạn:** lấy connection, execute, đọc result, commit hay rollback?
2. **Lấy SQLState và exception chain:** không chỉ đọc message đầu tiên.
3. **Phân loại:** data (`22`), constraint (`23`), connection (`08`), transaction rollback (`40`) hay nhóm khác?
4. **Kiểm tra transaction state:** PostgreSQL có thể đang aborted (`25P02`); có cần rollback toàn bộ hoặc về savepoint?
5. **Xác định khả năng retry:** lỗi có tạm thời không? Retry statement hay toàn transaction? Outcome commit có chắc chắn không?
6. **Bảo vệ tính đúng:** unique key, idempotency, version, lock và transaction có đủ không?
7. **Ánh xạ domain:** phản hồi có thể hiểu được nhưng không tiết lộ chi tiết DB.
8. **Ghi log/metrics:** có correlation ID, SQLState và thông tin đã masking.
9. **Đóng tài nguyên:** ResultSet, Statement, Connection; không trả connection hỏng vào pool như connection khỏe.
10. **Kiểm thử tình huống cạnh tranh và lỗi mạng:** không chỉ test đường chạy thành công.

## 35. Kết luận

Tách lỗi dữ liệu, lỗi ràng buộc, lỗi kết nối và lỗi đồng thời giúp ứng dụng biết **điều gì đã thất bại, transaction đang ở trạng thái nào và hành động tiếp theo có an toàn hay không**.

```text
SQLState 22 → dữ liệu/kiểu/phạm vi
SQLState 23 → toàn vẹn/constraint
SQLState 08 → kết nối
SQLState 40 → transaction conflict/rollback

                    │
                    ▼
           Phân loại + ngữ cảnh
                    │
         ┌──────────┼───────────┐
         ▼          ▼           ▼
      Reject      Rollback    Reconcile/
      input       / Savepoint  Retry có điều kiện
         │          │           │
         └──────────┼───────────┘
                    ▼
             Domain response
```

Hãy nhớ bốn nguyên tắc:

1. **Lỗi dữ liệu khác lỗi ràng buộc:** chuỗi không parse được là data exception; giá trị numeric âm bị CHECK từ chối là integrity violation.
2. **Lỗi kết nối có thể để lại kết quả không xác định:** mất phản hồi sau commit không chứng minh rollback; dùng idempotency key và cơ chế đối soát.
3. **Lỗi đồng thời cần chiến lược rõ:** atomic update, optimistic version, row lock, thứ tự khóa, isolation và retry toàn transaction khi phù hợp.
4. **Không retry tất cả SQLException:** đọc SQLState, transaction state, exception chain và ý nghĩa nghiệp vụ trước khi hành động.

Khi application có thể phân biệt **dữ liệu nào cần sửa, constraint nào bị vi phạm, connection nào phải thay, transaction nào cần chạy lại và xung đột nào cần trả về caller**, việc xử lý lỗi database trở nên có thể dự đoán, quan sát và vận hành an toàn hơn.
