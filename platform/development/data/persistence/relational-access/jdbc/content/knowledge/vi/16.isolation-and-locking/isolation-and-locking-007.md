# Khóa bi quan qua câu SQL phù hợp với hệ quản trị

## 1. Khóa bi quan giải quyết vấn đề gì?

Trong ứng dụng Java sử dụng **JDBC**, nhiều transaction có thể cùng đọc và thay đổi một hàng dữ liệu. Nếu nghiệp vụ quyết định dựa trên giá trị vừa đọc, một transaction khác có thể cập nhật giá trị đó trước khi transaction thứ nhất ghi lại. **Khóa bi quan** (*pessimistic locking*) chủ động yêu cầu hệ quản trị cơ sở dữ liệu (DBMS) giữ khóa thích hợp trong khi thực hiện một chuỗi thao tác cần tính nhất quán.

Ví dụ hệ thống bán hàng có một sản phẩm còn **5** đơn vị. Hai yêu cầu đặt trước đồng thời:

- Giao dịch A muốn giữ **4** đơn vị.
- Giao dịch B muốn giữ **3** đơn vị.

Nếu cả hai cùng đọc được số lượng `5` mà không phối hợp, chúng có thể cùng cho rằng còn đủ hàng. Kết quả có nguy cơ bán vượt tồn kho (*overselling*).

```text
Không có phối hợp:
  A đọc available_qty = 5
  B đọc available_qty = 5
  A quyết định giữ 4
  B quyết định giữ 3
  => Hai quyết định cộng lại vượt tồn kho 5.

Khóa bi quan trên cùng hàng:
  A lấy khóa, đọc 5, giữ 4, cập nhật còn 1, COMMIT
  B chờ khóa; sau khi A hoàn tất, B đọc lại 1
  B từ chối giữ 3 vì không đủ hàng.
```

Với DBMS hỗ trợ khóa hàng, câu SQL phổ biến để khóa một hàng trước khi sửa là `SELECT ... FOR UPDATE`. Tuy nhiên **không phải DBMS nào cũng hỗ trợ cú pháp đó**, và một câu lệnh giống nhau có thể có phạm vi khóa, thời gian chờ và hành vi đồng thời khác nhau tùy hệ quản trị.

**Ý chính:** JDBC cung cấp `Connection`, `PreparedStatement` và cơ chế transaction; còn việc **đề nghị khóa cụ thể** được thể hiện qua cú pháp SQL phù hợp với DBMS và phụ thuộc cơ chế khóa của DBMS.

## 2. Khóa bi quan hoạt động trong ranh giới transaction

Đối với PostgreSQL và các DBMS hỗ trợ `SELECT ... FOR UPDATE`, quy trình thường là:

```mermaid
sequenceDiagram
    participant A as Transaction A
    participant DB as Cơ sở dữ liệu
    participant B as Transaction B
    A->>DB: SELECT ... FOR UPDATE (sku = A)
    DB-->>A: Cấp khóa hàng; available_qty = 5
    B->>DB: SELECT ... FOR UPDATE (sku = A)
    Note over B,DB: B chờ A nhả khóa
    A->>DB: UPDATE available_qty = 1
    A->>DB: INSERT reservation
    A->>DB: COMMIT
    DB-->>B: Cấp khóa; available_qty = 1
    B->>B: Không đủ hàng để giữ 3
    B->>DB: ROLLBACK
```

Các điểm quan trọng:

1. **Bắt đầu transaction trước khi đọc để khóa.** Trong JDBC thuần, cần gọi `connection.setAutoCommit(false)` trước câu SQL khóa. Nếu `autoCommit=true` và câu lệnh tự commit khi kết thúc, khóa có thể được giải phóng trước khi các bước nghiệp vụ kế tiếp chạy.
2. **Dùng cùng một `Connection`** để đọc có khóa, kiểm tra, cập nhật và ghi dữ liệu liên quan. Mở kết nối mới cho câu `UPDATE` sẽ làm mất phạm vi bảo vệ của transaction ban đầu.
3. **Đóng `ResultSet` không nhả khóa transaction.** Với khóa hàng của `SELECT ... FOR UPDATE` trên PostgreSQL, khóa vẫn được DBMS giữ đến khi transaction `COMMIT` hoặc `ROLLBACK`.
4. **Khóa chỉ bảo vệ phạm vi thực sự bị khóa.** Khóa hàng sản phẩm không tự bảo vệ mọi hàng trong các bảng khác, những predicate không có bản ghi, hay tác động bên ngoài DBMS.
5. **Transaction đồng thời có thể chờ hoặc bị lỗi.** Chờ khóa, timeout, deadlock và lỗi serialization đều là tình huống bình thường phải dự kiến khi vận hành.

Khóa bi quan khác với **khóa lạc quan**: khóa lạc quan thường đọc mà không giữ khóa trong suốt quá trình xử lý, rồi khi cập nhật kiểm tra một cột phiên bản (`version`) hoặc giá trị cũ. Hai cách có thể cùng đúng; lựa chọn phụ thuộc tần suất xung đột, thời gian xử lý và yêu cầu nghiệp vụ.

## 3. Cú pháp khóa phụ thuộc hệ quản trị

Không nên viết một chuỗi SQL cố định rồi giả định chạy được trên mọi driver JDBC.

| Hệ quản trị | Ví dụ khóa dữ liệu để cập nhật | Lưu ý |
| --- | --- | --- |
| **PostgreSQL** | `SELECT ... FOR UPDATE` | Khóa hàng được chọn đến khi transaction kết thúc; hỗ trợ `NOWAIT` và `SKIP LOCKED` |
| **MySQL (InnoDB)** | `SELECT ... FOR UPDATE` | Phải dùng transaction; chỉ mục, điều kiện tìm kiếm và mức cô lập có thể ảnh hưởng số hàng/khoảng khóa |
| **Oracle Database** | `SELECT ... FOR UPDATE` | Có `NOWAIT`, `WAIT n`, `SKIP LOCKED`; có thể chỉ định bảng qua `FOR UPDATE OF ...` |
| **SQL Server** | `SELECT ... FROM ... WITH (UPDLOCK, ROWLOCK)` | Dùng *table hints* thay cho `FOR UPDATE`; `ROWLOCK` là gợi ý, không bảo đảm khóa luôn ở cấp hàng |
| **SQLite** | Không có `SELECT ... FOR UPDATE` | Có thể chủ động bắt đầu transaction ghi kiểu `BEGIN IMMEDIATE`; SQLite không cung cấp khóa hàng theo cách trên |

### 3.1. PostgreSQL

```sql
SELECT available_qty
FROM stock_items
WHERE sku = ?
FOR UPDATE;
```

Với một khóa chính `sku`, câu này yêu cầu khóa hàng đang được đọc để một transaction khác không đồng thời cập nhật/xóa hàng đó mà không đợi hoặc gặp lỗi. Có thể dùng `FOR UPDATE OF s` khi truy vấn ghép nhiều bảng và chỉ muốn khóa những hàng thuộc một bảng/alias cụ thể.

```sql
-- Lỗi ngay nếu không lấy được khóa:
SELECT available_qty
FROM stock_items
WHERE sku = ?
FOR UPDATE NOWAIT;

-- Bỏ qua hàng đang bị khóa (chủ yếu hữu ích khi lấy việc từ queue):
SELECT sku
FROM stock_items
WHERE available_qty > 0
ORDER BY sku
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` trả về tập kết quả **không đầy đủ** theo thời điểm khóa. Nếu hàng `SKU-A` không xuất hiện trong truy vấn có `SKIP LOCKED`, không thể kết luận sản phẩm đó không tồn tại hoặc đã hết hàng. Đối với quyết định giữ tồn kho theo mã cụ thể, mặc định chờ hoặc xử lý `NOWAIT` thường dễ diễn giải hơn.

PostgreSQL có thể đặt giới hạn đợi khóa trong một transaction:

```sql
SET LOCAL lock_timeout = '2s';
```

Thực thi câu này trên **chính kết nối đang dùng cho transaction**, trước câu lệnh khóa. `SET LOCAL` có hiệu lực trong transaction hiện hành; sau transaction, giá trị cấu hình được khôi phục. Đây là cú pháp PostgreSQL, không phải lệnh JDBC chung.

### 3.2. MySQL dùng InnoDB

```sql
SELECT available_qty
FROM stock_items
WHERE sku = ?
FOR UPDATE;
```

MySQL InnoDB hỗ trợ locking read trong transaction. Với điều kiện bằng khóa duy nhất có chỉ mục, phạm vi khóa thường được thu hẹp hơn so với truy vấn theo khoảng hoặc không có chỉ mục phù hợp. Ở mức cô lập mặc định `REPEATABLE READ` của InnoDB, *next-key/gap locks* có thể xuất hiện trong những truy vấn nhất định. Vì vậy, ngoài câu SQL, phải xem cả **chỉ mục và kế hoạch truy vấn**.

Các phiên bản MySQL 8.0 hỗ trợ biến thể `NOWAIT` và `SKIP LOCKED` trên locking read. Hành vi chính xác cũng phụ thuộc phiên bản và storage engine; ví dụ dùng bảng **InnoDB** hỗ trợ transaction.

### 3.3. Oracle Database

```sql
SELECT available_qty
FROM stock_items
WHERE sku = ?
FOR UPDATE WAIT 3;
```

`WAIT 3` yêu cầu chờ khóa trong khoảng tối đa ba giây; `NOWAIT` từ chối chờ, còn `SKIP LOCKED` bỏ qua hàng đã bị khóa. Với truy vấn join, Oracle cho phép `FOR UPDATE OF alias.column` để xác định bảng chứa cột cần khóa. Cú pháp `WAIT 3` ở đây là của Oracle, không dùng nguyên xi trên PostgreSQL hay SQL Server.

### 3.4. SQL Server

SQL Server không dùng `SELECT ... FOR UPDATE` theo cách của PostgreSQL. Một mẫu thường gặp:

```sql
SELECT available_qty
FROM stock_items WITH (UPDLOCK, ROWLOCK)
WHERE sku = ?;
```

`UPDLOCK` yêu cầu khóa cập nhật phục vụ ý định sửa dữ liệu và giữ khóa thích hợp đến cuối transaction. `ROWLOCK` gợi ý ưu tiên khóa hàng, nhưng bộ tối ưu và cơ chế khóa SQL Server có thể chọn hoặc leo thang khóa theo hoàn cảnh; không nên xem nó như bảo đảm tuyệt đối.

Nếu cần chống hiện tượng **phantom** trên một khoảng giá trị, một số thiết kế dùng `UPDLOCK, HOLDLOCK` và chỉ mục phù hợp để đạt ngữ nghĩa khóa phạm vi tương ứng với `SERIALIZABLE` cho truy vấn đó. Việc khóa một **hàng theo khóa chính đã tồn tại** và việc khóa **khoảng chứa cả những giá trị chưa tồn tại** là hai yêu cầu khác nhau.

SQL Server hỗ trợ cấu hình thời gian đợi khóa theo phiên với `SET LOCK_TIMEOUT`. Tùy thiết lập collation, row-versioning và isolation (chẳng hạn `READ_COMMITTED_SNAPSHOT`), hành vi đọc và khóa cũng khác; cần thử trên môi trường sử dụng thực tế.

### 3.5. SQLite

SQLite không có locking read cấp hàng thông qua `SELECT ... FOR UPDATE`. Với những tác vụ cần giành quyền ghi trước khi thực hiện chuỗi đọc rồi ghi, SQLite có dạng:

```sql
BEGIN IMMEDIATE;
-- Đọc và cập nhật trên cùng kết nối.
COMMIT;
```

`BEGIN IMMEDIATE` lấy quyền bắt đầu transaction ghi sớm hơn `BEGIN DEFERRED`; nó **không tạo khóa riêng cho từng hàng**. SQLite về cơ bản chỉ cho một writer thực thi tại một thời điểm; cách các reader cùng tồn tại với writer còn phụ thuộc journal mode, chẳng hạn WAL.

**Chú ý với JDBC:** Khi dùng driver SQLite, `connection.setAutoCommit(false)` có thể đã mở transaction theo cấu hình của driver. Không tùy ý chạy thêm `BEGIN IMMEDIATE` sau đó nếu transaction đã hoạt động; phải chọn chế độ transaction phù hợp qua cấu hình driver hoặc cách khởi tạo transaction được driver hỗ trợ.

## 4. Thiết lập schema và quy tắc giữ hàng

Ví dụ thực hành sau chọn **PostgreSQL**, dùng `VARCHAR` để lưu mã sản phẩm và các ràng buộc đơn giản cho tồn kho:

```sql
CREATE TABLE stock_items (
    sku VARCHAR(64) PRIMARY KEY,
    available_qty INTEGER NOT NULL,
    CONSTRAINT ck_stock_nonnegative CHECK (available_qty >= 0)
);

CREATE TABLE stock_reservations (
    reservation_id VARCHAR(64) PRIMARY KEY,
    sku VARCHAR(64) NOT NULL
        REFERENCES stock_items(sku),
    quantity INTEGER NOT NULL,
    CONSTRAINT ck_reservation_positive CHECK (quantity > 0)
);

INSERT INTO stock_items (sku, available_qty)
VALUES ('SKU-A', 5);
```

Nghiệp vụ **giữ `4` đơn vị của `SKU-A`** cần thỏa cả hai điều kiện:

1. `stock_items.available_qty` giảm từ `5` còn `1`.
2. `stock_reservations` có đúng một hàng lưu mã yêu cầu và số lượng đã giữ.

Nếu câu `INSERT` thất bại vì trùng mã yêu cầu hoặc lỗi ràng buộc, câu `UPDATE` giảm tồn kho cũng phải rollback. Mã `reservation_id` duy nhất hỗ trợ kiểm tra yêu cầu lặp, nhưng **không tự biến các lần thử lại thành thành công idempotent**; ứng dụng phải đối chiếu kết quả đã lưu.

## 5. Code JDBC: giữ khóa rồi mới cập nhật và ghi lịch sử

Lớp sau dùng `DataSource` do ứng dụng cấu hình với **driver PostgreSQL** và các bảng ở mục 4. Ví dụ yêu cầu **Java 17 trở lên** để sử dụng SQL text block và `String.isBlank()`. Nó chủ động mở transaction, khóa đúng hàng sản phẩm theo `sku`, xác nhận còn đủ hàng rồi thực hiện các câu SQL trong cùng `Connection`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class StockReservationService {
    private final DataSource dataSource;

    public StockReservationService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void reserve(String reservationId, String sku, int quantity)
            throws SQLException {
        if (reservationId == null || reservationId.isBlank()
                || reservationId.length() > 64) {
            throw new IllegalArgumentException("Mã yêu cầu không hợp lệ");
        }
        if (sku == null || sku.isBlank() || sku.length() > 64) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean oldAutoCommit = connection.getAutoCommit();
            if (!oldAutoCommit) {
                throw new SQLException(
                        "Ví dụ yêu cầu Connection chưa có transaction");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            Throwable primaryFailure = null;

            try {
                int available = readAndLockStock(connection, sku);
                if (available < quantity) {
                    throw new IllegalStateException(
                            "Không đủ tồn kho để giữ hàng");
                }

                int changed = decrementStock(connection, sku, quantity);
                if (changed != 1) {
                    throw new IllegalStateException(
                            "Không cập nhật được đúng một sản phẩm");
                }

                insertReservation(
                        connection, reservationId, sku, quantity);

                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                primaryFailure = failure;
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                // Tránh setAutoCommit(true) khi rollback chưa thành công:
                // thao tác đó có thể kết thúc transaction theo cách không muốn.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(oldAutoCommit);
                    } catch (SQLException resetFailure) {
                        if (primaryFailure != null) {
                            primaryFailure.addSuppressed(resetFailure);
                        } else {
                            throw resetFailure;
                        }
                    }
                }
            }
        }
    }

    private static int readAndLockStock(Connection connection, String sku)
            throws SQLException {
        String sql = """
                SELECT available_qty
                FROM stock_items
                WHERE sku = ?
                FOR UPDATE
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, sku);
            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException(
                            "Không tìm thấy sản phẩm: " + sku);
                }
                return rs.getInt("available_qty");
            }
        }
    }

    private static int decrementStock(
            Connection connection, String sku, int quantity)
            throws SQLException {
        String sql = """
                UPDATE stock_items
                SET available_qty = available_qty - ?
                WHERE sku = ? AND available_qty >= ?
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setString(2, sku);
            statement.setInt(3, quantity);
            return statement.executeUpdate();
        }
    }

    private static void insertReservation(
            Connection connection, String reservationId,
            String sku, int quantity) throws SQLException {
        String sql = """
                INSERT INTO stock_reservations
                    (reservation_id, sku, quantity)
                VALUES (?, ?, ?)
                """;

        try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, reservationId);
            statement.setString(2, sku);
            statement.setInt(3, quantity);

            if (statement.executeUpdate() != 1) {
                throw new SQLException("Không ghi được yêu cầu giữ hàng");
            }
        }
    }
}
```

Sử dụng khi đã khởi tạo `dataSource`:

```java
StockReservationService service = new StockReservationService(dataSource);
service.reserve("RES-001", "SKU-A", 4);
// Khi commit thành công: available_qty = 1 và có reservation RES-001.
```

Giải thích từng API JDBC:

| API / đoạn mã | Vai trò |
| --- | --- |
| `DataSource.getConnection()` | Mượn một kết nối dùng xuyên suốt transaction |
| `setAutoCommit(false)` | Giữ câu `SELECT FOR UPDATE` và các thao tác tiếp theo trong cùng transaction |
| `PreparedStatement.setString(1, sku)` | Truyền SKU như tham số, tránh nối SQL |
| `executeQuery()` + `ResultSet.getInt(...)` | Lấy số lượng **sau khi đã yêu cầu khóa hàng** |
| `executeUpdate()` | Kiểm tra số hàng bị thay đổi; không nhầm `0` hàng với thành công |
| `commit()` / `rollback()` | Kết thúc transaction và giải phóng khóa theo DBMS |
| `try-with-resources` | Đóng `ResultSet`, `PreparedStatement`, `Connection` khi hoàn tất hoặc có lỗi |

Điều kiện `AND available_qty >= ?` trong `UPDATE` là một lớp bảo vệ bổ sung, dù đã khóa hàng. Nó giúp giữ quy tắc không xuất kho âm sát nơi ghi dữ liệu. Ràng buộc `CHECK` trong bảng cũng bảo vệ các đường ghi khác không đi qua service này.

**Lưu ý về xử lý lỗi kết thúc transaction:** Nếu `commit()` báo lỗi do đứt kết nối đúng thời điểm DBMS đã nhận commit, trạng thái cuối cùng có thể **chưa xác định**. Một lời gọi `rollback()` sau lỗi commit không bảo đảm đảo ngược commit đã xảy ra. Nếu `setAutoCommit(true)` thất bại sau commit thành công, service cũng có thể ném lỗi dù dữ liệu đã được lưu. Khi thử lại, cần tra cứu `reservation_id` và đối chiếu nội dung yêu cầu, tránh trừ tồn kho hai lần.

## 6. Khóa chờ, từ chối chờ và bỏ qua hàng bị khóa

Có ba chính sách khác nhau; không nên dùng chúng thay thế nhau mà không xét hành vi sản phẩm:

| Chính sách | Cách thực hiện ví dụ trên PostgreSQL | Khi nên dùng |
| --- | --- | --- |
| **Chờ khóa** | `FOR UPDATE` | Đơn hàng giữ một SKU cụ thể; chờ transaction trước hoàn tất rồi đánh giá tồn kho mới |
| **Không chờ** | `FOR UPDATE NOWAIT` | Giao diện muốn báo nhanh “dữ liệu đang bận”; ứng dụng tự quyết định thử lại |
| **Bỏ qua hàng khóa** | `FOR UPDATE SKIP LOCKED` | Nhiều worker lấy các công việc chưa bị worker khác giữ |

Một ví dụ hàng đợi xử lý ở PostgreSQL:

```sql
SELECT job_id
FROM jobs
WHERE status = 'READY'
ORDER BY job_id
FOR UPDATE SKIP LOCKED
LIMIT 10;
```

`jobs` là bảng giả định khác, không thuộc schema tồn kho ở mục 4. Mỗi worker có thể lấy một nhóm hàng chưa bị khóa, sau đó **cập nhật trạng thái hoặc quyền sở hữu công việc trong cùng transaction trước commit**. Nếu chỉ SELECT rồi commit mà không ghi trạng thái, worker khác sẽ lại chọn cùng job sau khi khóa được nhả.

`SKIP LOCKED` không bảo đảm tính công bằng hoặc thứ tự xử lý tuyệt đối: một công việc bị khóa lâu có thể bị bỏ qua qua nhiều lượt. Với quyết định “SKU này có còn hàng không?”, bỏ qua hàng đang bị khóa thường trả về một kết luận dễ gây hiểu nhầm.

## 7. Khóa trên hàng hiện có khác khóa trên tập giá trị chưa tồn tại

Một bẫy thiết kế là suy nghĩ: “Tôi đã chạy `SELECT ... FOR UPDATE`, nên không ai có thể thêm dữ liệu làm thay đổi kết quả truy vấn của tôi.”

Ví dụ một hệ thống đặt chỗ truy vấn xem **có bản ghi đang giữ một ghế hay không**:

```sql
SELECT reservation_id
FROM seat_reservations
WHERE seat_id = ?
  AND status = 'ACTIVE'
FOR UPDATE;
```

Nếu **chưa có bản ghi** thỏa điều kiện, PostgreSQL không có hàng kết quả để khóa bằng `FOR UPDATE`. Hai transaction có thể đều thấy “chưa đặt” rồi cùng chèn một bản ghi, trừ khi có cơ chế khác.

Các giải pháp thường gặp:

- Tạo **ràng buộc duy nhất** thích hợp cho quyền đặt chỗ đang hoạt động. Trên PostgreSQL có thể dùng unique index có điều kiện theo nghiệp vụ; trên DBMS khác phải chọn thiết kế tương đương.
- Khóa một **hàng cha ổn định** đại diện cho ghế trước khi kiểm tra và chèn; hàng cha phải thực sự tồn tại.
- Dùng isolation `SERIALIZABLE` hoặc cơ chế khóa khoảng khi được DBMS hỗ trợ, kèm xử lý lỗi retry và kiểm thử phù hợp.

Ràng buộc duy nhất là chốt chặn cuối cùng khi nhiều đường ghi truy cập DBMS, ngay cả khi service đã khóa một hàng cha. Đừng xem `FOR UPDATE` trên **tập rỗng** là một mutex toàn cục.

Ngoài ra, truy vấn join có thể khóa nhiều bảng hơn dự kiến nếu dùng cú pháp chung. Với PostgreSQL hoặc Oracle, `FOR UPDATE OF ...` giúp thể hiện rõ bảng muốn khóa; cần xem tài liệu đúng phiên bản để biết khóa nào thực sự được lấy. Cũng cần lưu ý một số DBMS không cho dùng `FOR UPDATE` trực tiếp với các dạng truy vấn `GROUP BY`, tổng hợp hay `DISTINCT`; hãy xác định hàng gốc cần khóa.

## 8. Khóa bi quan và mức cô lập transaction

Mức cô lập (*isolation level*) quyết định cách transaction nhìn dữ liệu và những hiện tượng đồng thời được phép. Khóa bi quan là một lựa chọn SQL **bổ sung** để bảo vệ một tập hàng cụ thể.

| Mức JDBC | Điều cần biết khi dùng khóa |
| --- | --- |
| `TRANSACTION_READ_COMMITTED` | Có thể thấy dữ liệu mới được commit ở những lần đọc sau; `SELECT FOR UPDATE` trên PostgreSQL sẽ chờ hàng đang bị sửa và đọc trạng thái phù hợp khi giành được khóa |
| `TRANSACTION_REPEATABLE_READ` | Cách triển khai khác nhau; PostgreSQL có thể báo lỗi khi khóa hàng đã đổi kể từ snapshot của transaction, còn InnoDB có ngữ nghĩa locking read riêng |
| `TRANSACTION_SERIALIZABLE` | Hướng tới kết quả tương đương thực thi tuần tự; có thể buộc một transaction hủy và thử lại khi phát hiện xung đột |

Trong JDBC:

```java
int original = connection.getTransactionIsolation();

// Chỉ minh họa. Nên đặt trước khi bắt đầu công việc transaction.
connection.setTransactionIsolation(
        Connection.TRANSACTION_READ_COMMITTED);

// Sau transaction, khôi phục khi phù hợp với chủ sở hữu Connection/pool.
connection.setTransactionIsolation(original);
```

Đừng đổi isolation giữa transaction đang chạy mà không hiểu hành vi của DBMS/driver. Với PostgreSQL, nếu phải chọn mức cô lập, hãy đặt khi bắt đầu transaction trước các truy vấn nghiệp vụ. Một số DBMS có mặc định và mức hỗ trợ khác; `DatabaseMetaData.supportsTransactionIsolationLevel(...)` có thể hỗ trợ kiểm tra nhưng không thay được thử nghiệm concurrency thực tế.

Khóa bi quan còn có giới hạn: nó không tự xử lý sự nhất quán với API ngoài DBMS, không bảo đảm khóa được ưu tiên theo thứ tự gọi, và không ngăn mọi bất thường nếu nghiệp vụ phụ thuộc nhiều hàng hoặc tập giá trị chưa tồn tại.

## 9. Giảm deadlock và thời gian giữ khóa

Khóa khiến transaction cần chờ nhau. **Deadlock** xảy ra khi các transaction tạo thành vòng chờ khóa; DBMS thường chọn một bên để hủy, trả lỗi cho ứng dụng.

```text
Transaction A: khóa SKU-A, sau đó chờ SKU-B.
Transaction B: khóa SKU-B, sau đó chờ SKU-A.
                         => vòng chờ (deadlock)
```

Một số thực hành hữu ích:

1. **Giữ thứ tự khóa nhất quán.** Khi cần khóa nhiều SKU, sắp thứ tự mã (ví dụ theo `sku` tăng dần) rồi khóa lần lượt cùng một thứ tự ở mọi luồng nghiệp vụ. Cách này giảm nguy cơ deadlock nhưng không loại bỏ mọi trường hợp.
2. **Giữ transaction ngắn.** Không chờ thao tác HTTP, gửi email hay tương tác người dùng khi đang giữ khóa. Chuẩn bị dữ liệu trước, khóa gần thời điểm cập nhật và commit/rollback sớm.
3. **Dùng predicate và chỉ mục phù hợp.** Truy vấn khóa theo khóa chính giúp xác định chính xác hàng cần xử lý; truy vấn quét nhiều hàng có thể làm tăng phạm vi khóa hoặc lượng công việc.
4. **Đặt timeout phù hợp với trải nghiệm sản phẩm.** Phân biệt timeout đợi khóa, timeout thực thi statement và timeout mạng. JDBC `Statement.setQueryTimeout(...)` không bảo đảm cùng ngữ nghĩa với `lock_timeout` trên mọi driver.
5. **Retry có kiểm soát.** Với deadlock hoặc serialization failure có thể thử lại **toàn bộ transaction**, không chỉ chạy lại lệnh SQL cuối cùng. Có giới hạn số lần, khoảng nghỉ ngắn có thay đổi và sử dụng mã yêu cầu ổn định.
6. **Phân biệt lỗi chờ khóa với lỗi nghiệp vụ.** Timeout không có nghĩa sản phẩm đã hết hàng; DBMS chỉ cho biết chưa lấy được khóa trong giới hạn thời gian.

Trong PostgreSQL, mã SQLSTATE phổ biến gồm `55P03` (không lấy được khóa, ví dụ `NOWAIT` hoặc lock timeout), `40P01` (deadlock) và `40001` (serialization failure). Ở các DBMS khác mã lỗi và cách chẩn đoán có thể khác; nên kiểm tra `SQLException.getSQLState()`, `getErrorCode()` và log của DBMS thay vì so khớp mù quáng thông điệp lỗi.

Khi lỗi xảy ra trong transaction PostgreSQL, transaction có thể rơi vào trạng thái *aborted*. Trước khi thử một lệnh nghiệp vụ khác trên cùng connection, phải rollback transaction thất bại (hoặc rollback về savepoint hợp lệ khi thật sự có thiết kế sử dụng savepoint).

## 10. Có khi không cần `SELECT ... FOR UPDATE` riêng

Với quy tắc đơn giản “giảm số lượng nếu còn đủ”, một câu `UPDATE` có điều kiện cũng có thể bảo vệ thao tác **đọc điều kiện và ghi** mà không cần khóa trước:

```sql
UPDATE stock_items
SET available_qty = available_qty - ?
WHERE sku = ?
  AND available_qty >= ?;
```

Sau đó JDBC kiểm tra `executeUpdate() == 1`. DBMS phải lấy khóa ghi để thực hiện `UPDATE`; với engine hỗ trợ transaction và xử lý đồng thời thích hợp, cách này thường gọn và giảm một lượt trao đổi mạng so với `SELECT FOR UPDATE` rồi `UPDATE`.

Tuy nhiên, nếu nghiệp vụ cần đọc thêm nhiều thuộc tính của cùng hàng để quyết định, phối hợp nhiều câu lệnh hoặc khóa trước một quá trình tính toán ngắn, `SELECT ... FOR UPDATE` có thể giúp diễn đạt ý định rõ ràng. Ngay cả khi dùng `UPDATE` có điều kiện, phải đặt **INSERT reservation** vào cùng transaction để bảo đảm hai thay đổi commit/rollback cùng nhau.

Không có lựa chọn nào thay thế việc xác định đúng invariant nghiệp vụ và kiểm tra concurrency thực tế.

## 11. Kiểm thử với hai kết nối độc lập

Kiểm thử khóa bi quan không thể chỉ gọi service tuần tự. Cần **hai transaction trên hai kết nối vật lý/phiên DB khác nhau**, cùng tác động một SKU:

| Bước | Transaction A | Transaction B | Kỳ vọng |
| --- | --- | --- | --- |
| 1 | Bắt đầu transaction; khóa `SKU-A` với `FOR UPDATE` | — | A lấy khóa, đọc `5` |
| 2 | Giữ khóa, chưa commit | Bắt đầu transaction; thực thi `FOR UPDATE` cùng SKU | B phải chờ hoặc nhận lỗi theo `NOWAIT`/timeout |
| 3 | Giảm `5 → 1`, thêm `RES-A`, commit | Tiếp tục sau khi lấy khóa | B đọc trạng thái mới `1` ở `READ COMMITTED` PostgreSQL |
| 4 | — | Muốn giữ `3`; từ chối và rollback | Không có `RES-B`; số lượng còn `1` |

Các trường hợp khác cũng cần kiểm thử:

- **Rollback của A:** B được tiếp tục và đọc lại giá trị chưa bị trừ (`5`); B có thể giữ hàng nếu thỏa điều kiện.
- **`NOWAIT`:** B nhận lỗi nhanh thay vì chờ; xác định đúng SQLSTATE/error code của DBMS.
- **`SKIP LOCKED`:** B không nhận hàng đang khóa; không diễn giải đó là “không còn hàng”.
- **Hai SKU:** hai transaction giữ khóa theo thứ tự trái ngược để kiểm tra deadlock và quy trình retry.
- **Không có SKU:** `FOR UPDATE` không khóa được hàng không tồn tại; xử lý kết quả rỗng đúng với nghiệp vụ.
- **Lỗi `INSERT reservation`:** nếu mã `reservation_id` trùng, cả thay đổi tồn kho phải rollback.
- **Mất kết nối quanh `commit`:** trạng thái commit có thể chưa xác định; tra cứu mã yêu cầu duy nhất trước khi retry.

Trong kiểm thử, dùng cơ chế phối hợp có kiểm soát (ví dụ latch hoặc barrier ở lớp kiểm thử) để chắc chắn A đã lấy khóa trước khi B cố lấy khóa; không dựa vào `Thread.sleep` rồi suy đoán thứ tự. Cấu hình timeout ngắn để kiểm thử không treo vô hạn và kiểm tra dữ liệu đã commit bằng một kết nối riêng.

## 12. Checklist triển khai

Trước khi sử dụng khóa bi quan trong JDBC, hãy xác nhận:

1. **DBMS và storage engine** có hỗ trợ transaction/loại khóa cần dùng.
2. **Câu SQL đúng dialect:** `FOR UPDATE` ở PostgreSQL/MySQL/Oracle; locking hints ở SQL Server; cách mở transaction ghi riêng ở SQLite.
3. **Transaction rõ ràng:** `autoCommit=false` trước câu khóa, cùng `Connection` cho mọi thao tác nghiệp vụ, `commit` hoặc `rollback` ở điểm kết thúc.
4. **Khóa đúng đối tượng:** predicate theo khóa/chỉ mục; xem xét join, phạm vi và tình huống tập kết quả rỗng.
5. **Chính sách chờ rõ ràng:** chờ, `NOWAIT` hay `SKIP LOCKED` phù hợp ý nghĩa nghiệp vụ.
6. **Các đường ghi khác được bảo vệ:** ràng buộc DB, `UPDATE` có điều kiện và kiểm tra số hàng giúp đảm bảo invariant khi có code không dùng cùng câu khóa.
7. **Chịu được lỗi đồng thời:** timeout, deadlock, serialization failure, lỗi commit chưa rõ và retry có giới hạn.
8. **Kiểm thử trên DBMS thật:** concurrency, khóa được nhả sau `COMMIT/ROLLBACK`, chính sách timeout và tính nhất quán sau lỗi.

**Ghi nhớ:** Khóa bi quan trong JDBC là sự kết hợp giữa **SQL khóa theo dialect của DBMS**, **một transaction bao trọn nhiều bước trên cùng `Connection`** và **quy tắc xử lý khi tranh chấp**. `SELECT ... FOR UPDATE` rất hữu ích trên PostgreSQL, MySQL và Oracle, nhưng SQL Server và SQLite cần cách tiếp cận khác. Sử dụng đúng cú pháp, khóa đúng phạm vi và kiểm thử hai kết nối đồng thời mới giúp quyết định nghiệp vụ dựa trên dữ liệu đáng tin cậy.
