# Xử lý giao dịch chỉ đọc và giới hạn của gợi ý `readOnly` trong JDBC

Trong chương **Giao dịch cơ bản**, một ứng dụng Java dùng JDBC thường có cả thao tác thay đổi dữ liệu (tạo đơn hàng, cập nhật số dư) và thao tác chỉ truy vấn (xem lịch sử, xuất báo cáo). Với nhóm truy vấn, `Connection.setReadOnly(true)` có thể giúp driver hoặc cơ sở dữ liệu tối ưu việc thực thi. Tuy nhiên, chữ **read-only** dễ tạo ra một hiểu nhầm nghiêm trọng: gọi phương thức này **không phải cam kết theo chuẩn JDBC rằng mọi câu lệnh ghi đều bị chặn**.

Bài học trình bày ý nghĩa của `readOnly`, thời điểm cấu hình kết nối, cách phối hợp `setAutoCommit(false)`, `commit()`, `rollback()`, mức cô lập (*isolation level*) và cách làm việc an toàn với `DataSource`/connection pool. Ví dụ dùng `PreparedStatement` và `ResultSet` cho một báo cáo gồm nhiều câu `SELECT`, sau đó phân tích giới hạn về nhất quán dữ liệu, quyền ghi và khả năng tối ưu.

## 1. `Connection.setReadOnly(true)` thật sự làm gì?

JDBC định nghĩa `Connection.setReadOnly(boolean readOnly)` là cách đặt kết nối vào chế độ chỉ đọc **như một gợi ý cho driver để bật tối ưu hóa cơ sở dữ liệu**, nếu có. Phương thức `Connection.isReadOnly()` cho biết trạng thái chỉ đọc của kết nối theo JDBC.

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setReadOnly(true);
    System.out.println(connection.isReadOnly());
    // Có thể là true, nhưng không chứng minh DB đã chặn mọi câu lệnh ghi.
}
```

`setReadOnly(true)` có thể dẫn tới các hành vi khác nhau:

- Driver chuyển trạng thái read-only xuống phiên làm việc hoặc transaction của DB, để DB áp dụng chế độ chỉ đọc riêng.
- Driver dùng cờ này cho một số tối ưu, định tuyến hoặc cách chuẩn bị câu lệnh.
- Driver không có tối ưu tương ứng, hoặc chỉ xử lý một phần, nên ứng dụng không nhận được hiệu quả hay hạn chế ghi như mong đợi.
- Một số driver/DB có thể báo `SQLException` khi không áp dụng được cấu hình.

Vì vậy, **`readOnly` là ý định sử dụng kết nối**, không phải cơ chế phân quyền truy cập dữ liệu. Nếu ứng dụng thực sự phải cấm ghi, cần dùng quyền trên DB hoặc một giao dịch read-only do chính hệ quản trị cưỡng chế, đồng thời kiểm chứng hành vi thực tế.

### Ba khái niệm thường bị nhầm

| Cơ chế | Mục đích | Có bảo đảm chặn ghi không? |
| --- | --- | --- |
| `connection.setReadOnly(true)` (JDBC) | Gợi ý cho driver về ý định chỉ đọc; có thể kích hoạt tối ưu | **Không được chuẩn JDBC bảo đảm** |
| Transaction read-only ở cấp DB | Yêu cầu DB giới hạn thao tác của một transaction | Tùy DB, lệnh SQL, bảng/đối tượng và các ngoại lệ của hệ quản trị |
| Tài khoản DB chỉ có quyền `SELECT` | Phân quyền trên đối tượng dữ liệu | Được DB thực thi theo hệ thống quyền; là ranh giới bảo vệ phù hợp hơn |

Ví dụ, PostgreSQL hỗ trợ transaction ở chế độ `READ ONLY`; MySQL cũng có cú pháp khởi tạo transaction chỉ đọc, nhưng các quy tắc và ngoại lệ khác nhau. Hai cách này thuộc SQL/hành vi của từng DB, không thể suy từ riêng lời gọi `setReadOnly(true)` rằng mọi DB đều thực thi giống nhau.

## 2. Tại sao thời điểm gọi `setReadOnly` quan trọng?

Theo hợp đồng `java.sql.Connection`, **không được gọi `setReadOnly(...)` khi một transaction đang diễn ra**. Vì thế, với transaction do ứng dụng quản lý, hãy quyết định cờ chỉ đọc **trước khi bắt đầu transaction hoặc thực hiện SQL**. Cách an toàn là cấu hình ngay khi mượn kết nối mới và trước `setAutoCommit(false)`.

```java
try (Connection connection = dataSource.getConnection()) {
    // Thiết lập khi chưa chạy câu lệnh nào và chưa bắt đầu transaction.
    connection.setReadOnly(true);
    connection.setAutoCommit(false);

    try {
        // Các câu SELECT bằng PreparedStatement/ResultSet.
        connection.commit();
    } catch (SQLException failure) {
        connection.rollback();
        throw failure;
    }
}
```

Đoạn trên minh họa **thứ tự**; ví dụ hoàn chỉnh ở phần 4 xử lý thêm lỗi rollback, khôi phục trạng thái kết nối và SQL thực tế.

Không nên viết:

```java
connection.setAutoCommit(false);
// Đã có thao tác SQL trong transaction...
connection.setReadOnly(true); // Sai thời điểm theo hợp đồng JDBC.
```

Khi dùng connection pool, kết nối lấy từ `DataSource` có thể đã được cấu hình `autoCommit=false` hoặc read-only theo chính sách của pool. Đừng tiếp quản một transaction mà tầng gọi đang sở hữu; cần làm rõ ai điều khiển transaction và ai có trách nhiệm khôi phục trạng thái kết nối.

## 3. `readOnly` và `autoCommit` là hai cấu hình khác nhau

JDBC dùng `autoCommit` để quyết định ranh giới transaction:

- Với `autoCommit=true`, mỗi statement được commit theo quy tắc JDBC khi statement hoàn thành. Một câu `SELECT` đơn lẻ vẫn có thể dùng `setReadOnly(true)` làm gợi ý.
- Với `autoCommit=false`, ứng dụng tự kết thúc transaction bằng `commit()` hoặc `rollback()`. Nhiều câu `SELECT` có thể được gom vào cùng một transaction.
- `setReadOnly(true)` không tự chuyển `autoCommit` thành `false`, không tự gọi `commit` và không quyết định isolation level.
- `setAutoCommit(true)` khi đang ở chế độ `false` **có thể commit transaction đang hoạt động**. Không dùng thao tác đổi cờ như một cách thay cho `commit()`/`rollback()` rõ ràng.

Sơ đồ một lượt truy vấn báo cáo nhiều bước:

```text
Mượn Connection từ DataSource
    |
    v
Kiểm tra quyền sở hữu transaction
    |
    v
setReadOnly(true)   (trước transaction)
    |
    v
setAutoCommit(false)
    |
    v
SELECT A --> SELECT B
    |          |
    +----------+
    |
    +---- thành công ----> commit()
    |
    +---- lỗi -----------> rollback()
    |
    v
Khôi phục cấu hình sau khi transaction kết thúc
    |
    v
Đóng/trả Connection cho pool
```

Gọi `commit()` sau các truy vấn có ý nghĩa kết thúc transaction và giải phóng tài nguyên liên quan; nó **không chứng minh các truy vấn đã nhìn cùng một snapshot dữ liệu**. Điều đó còn phụ thuộc isolation level và cách DB thực hiện.

## 4. Ví dụ hoàn chỉnh: báo cáo nhiều truy vấn trong transaction chỉ đọc

Giả sử cơ sở dữ liệu có bảng đơn hàng:

```sql
CREATE TABLE purchase_order (
    id           BIGINT PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL
);
```

Ứng dụng cần lấy số đơn hàng và tổng số tiền của một khách hàng. Các lệnh `SELECT` được tham số hóa, dữ liệu tiền được đọc bằng `BigDecimal`:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderReportRepository {
    private final DataSource dataSource;

    public OrderReportRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    // Ví dụ dùng record của Java 16+.
    public record OrderReport(long orderCount, BigDecimal totalAmount) {}

    public OrderReport loadReport(long customerId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Phương thức sở hữu một kết nối mới, không tham gia transaction
            // do caller hoặc framework bên ngoài đang quản lý.
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu kết nối đang ở autoCommit=true");
            }

            boolean oldReadOnly = connection.isReadOnly();
            connection.setReadOnly(true);  // Đặt trước khi bắt đầu transaction.

            boolean manualTransactionStarted = false;
            boolean transactionEnded = false;
            try {
                connection.setAutoCommit(false);
                manualTransactionStarted = true;

                long count;
                try (PreparedStatement ps = connection.prepareStatement(
                        "SELECT COUNT(*) FROM purchase_order WHERE customer_id = ?")) {
                    ps.setLong(1, customerId);
                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next(); // Truy vấn COUNT(*) luôn trả một dòng.
                        count = rs.getLong(1);
                    }
                }

                BigDecimal total;
                try (PreparedStatement ps = connection.prepareStatement(
                        """
                        SELECT COALESCE(SUM(total_amount), 0)
                        FROM purchase_order
                        WHERE customer_id = ?
                        """)) {
                    ps.setLong(1, customerId);
                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        total = rs.getBigDecimal(1);
                    }
                }

                connection.commit();
                transactionEnded = true;
                return new OrderReport(count, total);

            } catch (SQLException | RuntimeException failure) {
                if (manualTransactionStarted && !transactionEnded) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            } finally {
                if (!manualTransactionStarted || transactionEnded) {
                    // Chỉ khôi phục autoCommit sau khi đã kết thúc transaction.
                    try {
                        if (manualTransactionStarted) {
                            connection.setAutoCommit(true);
                        }
                    } finally {
                        connection.setReadOnly(oldReadOnly);
                    }
                }
                // Nếu rollback thất bại, tránh setAutoCommit(true) vì thao
                // tác này có thể commit một transaction chưa rõ trạng thái.
                // Connection vẫn sẽ được đóng bởi try-with-resources.
            }
        }
    }
}
```

Ví dụ dùng **Java 16+** vì có `record` và SQL *text block*; các phiên bản Java cũ hơn có thể thay `record` bằng lớp dữ liệu thông thường và dùng chuỗi SQL một dòng. Một số điểm đáng chú ý:

1. `setReadOnly(true)` được gọi **trước** `setAutoCommit(false)` và trước mọi câu SQL.
2. `PreparedStatement` dùng `?` thay cho ghép `customerId` vào câu SQL. `ResultSet`, statement và kết nối được đóng bằng `try-with-resources`.
3. Nhánh thành công gọi `commit()` rõ ràng; nhánh lỗi thử `rollback()` và giữ lại lỗi rollback dưới dạng *suppressed exception* nếu cần.
4. Sau khi transaction kết thúc, trạng thái `autoCommit` và `readOnly` được khôi phục để tránh rò rỉ cấu hình khi trả kết nối về pool.
5. Nếu rollback thất bại, trạng thái transaction có thể không xác định. Ứng dụng cần để tầng quản lý pool/driver xử lý kết nối không còn tin cậy; **không được giả định rollback đã thành công**. Đối với hệ thống nghiêm ngặt, cấu hình pool phải có chiến lược loại bỏ kết nối hỏng.

**Giới hạn về nhất quán:** Dù hai câu `SELECT` nằm trong cùng một transaction, ở mức `READ_COMMITTED` một transaction khác có thể chèn đơn hàng giữa hai lần đọc. Khi đó `count` và `total` có thể phản ánh hai thời điểm khác nhau. `readOnly=true` không tự sửa được hiện tượng này. Nếu cần snapshot nhất quán, hãy xem phần tiếp theo.

## 5. Chế độ chỉ đọc không thay thế isolation level

Một transaction được mô tả bởi nhiều thuộc tính độc lập:

| Thuộc tính | Câu hỏi nó trả lời |
| --- | --- |
| `autoCommit` | Ai quyết định lúc kết thúc transaction? |
| `readOnly` | Ứng dụng có thông báo ý định chỉ truy vấn cho driver không? |
| `transactionIsolation` | Những thay đổi đồng thời từ transaction khác có thể được nhìn thấy theo quy tắc nào? |
| Quyền DB | Tài khoản này có thể thực thi `INSERT`, `UPDATE`, `DELETE` hay không? |

JDBC cung cấp `Connection.setTransactionIsolation(...)` với các hằng như:

- `TRANSACTION_READ_COMMITTED`: thường cho phép một truy vấn sau nhìn thấy dữ liệu được transaction khác commit sau truy vấn trước, tùy ngữ nghĩa DB.
- `TRANSACTION_REPEATABLE_READ`: tăng tính ổn định khi đọc lại dữ liệu đã truy vấn, nhưng bảo đảm cụ thể và xử lý *phantom* phụ thuộc DB.
- `TRANSACTION_SERIALIZABLE`: mức cô lập mạnh nhất được JDBC đặt tên; có thể tốn chi phí hoặc gây lỗi xung đột phải retry toàn bộ transaction.

Khi cần chọn isolation, cấu hình **trước khi transaction bắt đầu**, ví dụ:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setReadOnly(true);
    connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ);
    connection.setAutoCommit(false);
    // SELECT ...; commit/rollback ...; khôi phục trạng thái trước khi trả pool.
}
```

Đây là ví dụ thứ tự thiết lập, **không phải hàm quản lý transaction hoàn chỉnh**. Mức cô lập sẵn có, chi phí, cách tạo snapshot và khả năng thay đổi isolation trong transaction phụ thuộc DB/driver. Khi có nhu cầu báo cáo nhất quán, phải kiểm tra đồng thời kết quả trên engine thực tế. Đôi khi một truy vấn tổng hợp SQL duy nhất sẽ đơn giản hơn hai `SELECT` tách rời.

## 6. Những giới hạn và hiểu nhầm của `readOnly`

### Không phải cơ chế bảo mật hay khóa cứng quyền ghi

Giả sử ứng dụng gọi:

```java
connection.setReadOnly(true);
// Không được dựa vào cờ này để kết luận INSERT hoặc UPDATE chắc chắn bị chặn.
```

Nếu tài khoản DB vẫn có quyền `UPDATE`, một hệ quản trị hoặc driver chỉ xem `readOnly` là gợi ý có thể vẫn cho phép ghi. Ngược lại, DB thực thi read-only thật có thể từ chối một số lệnh ghi. **Đừng viết logic nghiệp vụ theo giả định một trong hai hành vi luôn xảy ra trên mọi hệ thống.**

Nếu chức năng xuất báo cáo tuyệt đối không được thay đổi dữ liệu, hãy dùng tài khoản chỉ có quyền đọc trên các bảng liên quan và thực thi truy vấn tham số hóa. Với hệ thống có replica chỉ đọc, cấu hình định tuyến và quyền DB cũng phải được kiểm chứng; bản thân `setReadOnly(true)` không bảo đảm kết nối được chuyển sang replica.

### Không mặc nhiên tăng hiệu năng

Một số DB tối ưu transaction đọc bằng cách giảm chi phí theo dõi thay đổi hoặc dùng chế độ điều phối phù hợp. Một số khác có thể không thay đổi đáng kể, hoặc cần cú pháp SQL riêng. Do đó, kết quả phải đo bằng thời gian truy vấn, kế hoạch thực thi và thống kê kết nối/DB thay vì kết luận chỉ từ giá trị `connection.isReadOnly()`.

Read-only transaction cũng vẫn có thể giữ snapshot, chiếm connection, bộ nhớ hoặc các dạng khóa đọc theo DB. Một transaction đọc kéo dài có thể ảnh hưởng tài nguyên và hoạt động ghi của hệ thống.

### Không làm dữ liệu trở nên bất biến trong toàn transaction

`readOnly` không mặc nhiên cung cấp snapshot cố định. Một mức cô lập cho phép *non-repeatable read* hoặc *phantom read* vẫn có thể quan sát giá trị khác giữa hai câu `SELECT`. Sự bất biến của dữ liệu đọc phụ thuộc isolation và triển khai cơ sở dữ liệu.

### Không áp đặt cho mọi thư viện quản lý transaction

Ở ứng dụng dùng framework như Spring, annotation `@Transactional(readOnly = true)` là chỉ dẫn ở tầng framework, có thể được chuyển xuống JDBC hoặc DB theo cách khác nhau tùy transaction manager và provider. Không nên coi hành vi này là tương đương tuyệt đối với lệnh SQL `START TRANSACTION READ ONLY` hoặc một tài khoản DB chỉ có quyền `SELECT`.

Khi tầng framework đã sở hữu transaction, code repository thông thường nên để tầng đó quản lý `commit`/`rollback` và các thuộc tính kết nối, tránh tự bật/tắt `autoCommit` hoặc `readOnly` bên trong transaction đang diễn ra.

## 7. Kiểm tra hỗ trợ và hành vi của driver/DB

`isReadOnly()` cho biết cờ của kết nối; nó **không phải phép kiểm thử việc DB đã từ chối một lệnh ghi**. `DatabaseMetaData.isReadOnly()` báo trạng thái chỉ đọc của cơ sở dữ liệu theo metadata driver, cũng không thay thế việc xác minh cơ chế read-only cho transaction cụ thể.

Để kiểm tra tính tương thích trên môi trường thử nghiệm:

1. Lấy tên và phiên bản của driver cùng sản phẩm DB từ `connection.getMetaData()`.
2. Tạo kết nối mới, gọi `setReadOnly(true)` **trước** khi thực thi SQL. Ghi nhận có `SQLException` hoặc `SQLFeatureNotSupportedException` hay không.
3. Kiểm tra `isReadOnly()`; chạy một truy vấn `SELECT` thực tế qua `PreparedStatement` và đọc `ResultSet`.
4. Trong môi trường thử nghiệm có thể xóa/rollback dữ liệu, xác nhận chính sách của DB bằng một thao tác ghi chủ động được kiểm soát. Nếu DB cho phép ghi, đừng coi cờ là rào chắn quyền; nếu DB từ chối, ghi rõ DB, driver, kiểu transaction và thông báo lỗi.
5. Thử nhiều câu `SELECT` dưới các isolation level cần dùng, với một kết nối khác ghi đồng thời, để xác nhận quy tắc snapshot theo nghiệp vụ.
6. Kiểm tra trạng thái kết nối trước và sau khi trả về pool, kể cả các nhánh lỗi; bảo đảm connection state được khôi phục hoặc kết nối bị lỗi được loại bỏ.

Ví dụ lấy metadata phục vụ chẩn đoán:

```java
DatabaseMetaData meta = connection.getMetaData();
System.out.printf("DB: %s %s%n",
        meta.getDatabaseProductName(), meta.getDatabaseProductVersion());
System.out.printf("Driver: %s %s%n",
        meta.getDriverName(), meta.getDriverVersion());
System.out.println("Connection readOnly = " + connection.isReadOnly());
System.out.println("Database metadata readOnly = " + meta.isReadOnly());
```

Đoạn này giả định `connection` đã được tạo. Không nên dùng kết quả `meta.isReadOnly()` làm phép thay thế kiểm thử lệnh SQL trên hệ thống cụ thể.

## 8. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Gọi `setReadOnly(true)` sau khi transaction đã bắt đầu | Vi phạm thời điểm gọi theo JDBC, có thể bị từ chối hoặc ứng xử khác nhau | Thiết lập trước transaction |
| Coi `readOnly=true` là quyền chỉ đọc | Dữ liệu vẫn có thể bị ghi nếu DB/driver không cưỡng chế | Dùng phân quyền DB và kiểm chứng transaction read-only ở DB |
| Quên `commit`/`rollback` vì “chỉ đọc thôi” | Transaction, snapshot hoặc khóa có thể tồn tại quá lâu | Kết thúc transaction rõ ràng |
| Đổi `setAutoCommit(true)` để “đóng transaction” khi chưa xác định kết quả | Có thể commit ngoài ý muốn | `commit`/`rollback` trước, rồi mới khôi phục `autoCommit` |
| Không khôi phục `readOnly` khi trả kết nối về pool | Yêu cầu ghi sau có thể bị lỗi, hoặc tối ưu sai cách | Khôi phục cờ sau transaction; kiểm tra chính sách reset của pool |
| Cho rằng hai `SELECT` luôn đọc cùng snapshot | Báo cáo có thể tự mâu thuẫn khi có transaction ghi đồng thời | Chọn isolation hoặc truy vấn tổng hợp phù hợp |
| Giữ transaction báo cáo quá lâu | Chiếm connection/tài nguyên DB, có thể ảnh hưởng hệ thống | Giới hạn thời gian và số thao tác, kết thúc sớm |
| Bỏ qua lỗi `rollback()` | Có thể trả về pool kết nối ở trạng thái không đáng tin | Ghi nhận lỗi, tránh commit vô ý, nhờ pool loại bỏ kết nối hỏng |
| Tự quản lý transaction bên trong phương thức đang tham gia transaction framework | Phá ranh giới transaction và quy tắc propagation | Để tầng sở hữu transaction điều khiển |

## 9. Tình huống thực hành

Một API báo cáo cần trả về **tổng số đơn** và **tổng số tiền** theo khách hàng. Nhóm phát triển dự định chỉ thêm:

```java
connection.setReadOnly(true);
```

Hãy đánh giá lần lượt:

1. Tại thời điểm gọi, kết nối đã chạy SQL hoặc đang tham gia transaction bên ngoài chưa?
2. Hai truy vấn dùng `PreparedStatement` hay đang ghép giá trị từ request vào SQL?
3. Ai sẽ gọi `commit()`/`rollback()` và ai khôi phục cờ trước khi trả kết nối về pool?
4. Nếu một đơn hàng được thêm giữa hai lần `SELECT`, kết quả báo cáo có cần cùng một snapshot không? Mức cô lập hiện tại có đáp ứng được không?
5. Nếu một đoạn code khác gọi `UPDATE` trên cùng kết nối, quyền DB có chặn thao tác đó không? Có dựa nhầm vào gợi ý `readOnly` để bảo vệ dữ liệu không?
6. Trong môi trường thử nghiệm, driver hiện tại có thật sự đem lại lợi ích hoặc từ chối thao tác ghi nào khi đặt `readOnly=true`?

**Ghi nhớ:** `Connection.setReadOnly(true)` là **gợi ý hiệu năng và ý định sử dụng kết nối** trong JDBC. Hãy đặt nó trước transaction, phối hợp đúng với `autoCommit`, `commit` và `rollback`, đồng thời kiểm tra isolation level khi cần tính nhất quán giữa nhiều truy vấn. Nếu cần **bảo đảm không ghi được dữ liệu**, hãy dùng cơ chế cưỡng chế của DB và quyền truy cập phù hợp; không dựa vào riêng cờ `readOnly`.
