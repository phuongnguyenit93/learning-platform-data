# JDBC trong Java: Tự đóng Connection, Statement và ResultSet

## 1. Vì sao đóng tài nguyên JDBC là một phần của tính đúng đắn?

Một ứng dụng đọc thông tin khách hàng qua JDBC thường phải mở **ba lớp tài nguyên**:

1. `Connection`: kết nối logic tới database, thường được cấp qua `DataSource` hoặc connection pool.
2. `Statement` hoặc `PreparedStatement`: câu lệnh SQL, có thể giữ các tài nguyên phía JDBC driver/database.
3. `ResultSet`: tập kết quả/cursor, có thể giữ buffer, stream hoặc server-side cursor.

Nếu một method trả kết quả sớm, phát sinh exception hoặc bị ngắt trước khi gọi `close()`, những tài nguyên này có thể tồn tại lâu hơn mức cần thiết, dẫn tới connection-pool exhaustion, cursor leak, locks không được nhả đúng lúc, memory pressure và request timeout.

Từ **Java 7**, cú pháp **try-with-resources** hỗ trợ tự gọi `close()` trên các object triển khai `AutoCloseable`. Các giao diện JDBC **`Connection`, `Statement`, `PreparedStatement` và `ResultSet`** đều phù hợp với cơ chế này trong Java hiện đại.

Mẫu cần nhớ:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT name FROM customers WHERE id = ?")) {
    statement.setLong(1, customerId);
    try (ResultSet results = statement.executeQuery()) {
        while (results.next()) {
            System.out.println(results.getString("name"));
        }
    }
}
```

Đây là **đoạn minh họa trong phương thức có xử lý `SQLException`**, với `dataSource` và `customerId` đã được khai báo. Khi thoát các khối — kể cả khi ném exception — Java tự đóng theo thứ tự **ResultSet trước, PreparedStatement sau, Connection cuối cùng**.

**Điểm quan trọng:** try-with-resources quản lý **vòng đời Java/JDBC resource**; nó **không** tự quyết định commit hay rollback transaction đúng cho nghiệp vụ, cũng không bảo đảm rằng việc đóng một pooled `Connection` là đóng physical TCP connection tới database.

Bài này tập trung đúng đề tài **“Tự đóng Connection, Statement và ResultSet”**, gồm cú pháp, thứ tự đóng, ngoại lệ bị suppressed, transaction và connection pooling, lỗi thường gặp và cách kiểm thử. Những API đề cập **vẫn còn áp dụng**; không dùng `Class.forName("...")` bắt buộc thủ công theo mẫu driver cũ hoặc API JDBC deprecated.

## 2. Ba tài nguyên phụ thuộc nhau như thế nào?

Quan hệ thường gặp:

```text
DataSource / connection pool
          |
          v
Connection c
    |
    +-- PreparedStatement ps
            |
            +-- ResultSet rs
                    |
                    +-- đọc từng row, column, stream/LOB
```

Trong sơ đồ này, lifetime của `rs` phụ thuộc `ps`, còn `ps` phụ thuộc `c`. Vì vậy tài nguyên **tạo sau cùng cần được đóng trước**.

### 2.1. Connection

`Connection` đại diện cho một phiên JDBC có thể tạo statement, quản lý auto-commit/transaction và giải phóng các tài nguyên JDBC. Khi không còn cần dùng, phải đóng **logical connection** càng sớm càng hợp lý.

Với ứng dụng server:

- Ưu tiên lấy connection từ **`DataSource`/pool** thay vì giữ một global `Connection` dùng chung.
- Chỉ giữ connection trong scope cần truy vấn hoặc transaction.
- Khi gọi `close()` lên connection do pool cấp, thường là **trả logical connection cho pool**, không phải đóng ngay physical socket của database. Hành vi cụ thể phụ thuộc pool/provider.
- Không giữ `Connection` hoặc resource con vượt ra khỏi scope đã đóng.
- Không coi `isClosed()==false` là một kiểm tra sức khỏe end-to-end thay cho thử thao tác JDBC hoặc validation được provider hỗ trợ.

### 2.2. Statement và PreparedStatement

`Statement` dùng để thực thi SQL, `PreparedStatement` hỗ trợ câu lệnh có tham số và thường là lựa chọn an toàn, rõ ràng hơn khi dữ liệu do người dùng cung cấp.

```java
PreparedStatement ps = connection.prepareStatement(
        "SELECT name FROM customers WHERE id = ?");
ps.setLong(1, customerId);
```

Đây là đoạn minh họa, **chưa có try-with-resources**; trong thực tế nên đặt khai báo `ps` trong danh sách tài nguyên của `try`. `PreparedStatement` là subinterface của `Statement` và triển khai `AutoCloseable`.

**Không ghép tham số trực tiếp vào SQL bằng nối chuỗi** để tránh SQL injection. Try-with-resources giải quyết resource lifetime, còn parameter binding giải quyết an toàn dữ liệu đầu vào; hai trách nhiệm khác nhau và đều cần.

### 2.3. ResultSet

`ResultSet` chứa con trỏ và dữ liệu từ query. Với `executeQuery()`:

```java
try (ResultSet rs = statement.executeQuery()) {
    while (rs.next()) {
        String name = rs.getString("name");
        // Chuyển thành DTO hoặc kết quả nghiệp vụ.
    }
}
```

Đoạn minh họa có `statement` còn mở và phương thức xử lý `SQLException`. `rs.next()` di chuyển cursor; kết thúc vòng lặp không nhất thiết đồng nghĩa cursor đã được đóng **ngay lúc đó**. Đóng scope giúp release sớm hơn.

**Không trả trực tiếp `ResultSet` ra khỏi method nếu method sẽ đóng `Statement`/`Connection` trước khi caller đọc.** Thay vào đó, đọc các row trong scope và trả DTO/list/map đã tách khỏi tài nguyên JDBC.

## 3. Try-with-resources đóng tài nguyên ra sao?

Cú pháp Java 7:

```java
try (ResourceType r = acquire()) {
    use(r);
}
```

Đây là cú pháp minh họa, với `ResourceType` triển khai `AutoCloseable`; `acquire` và `use` là phương thức ứng dụng tự định nghĩa.

JVM/compiler quản lý:

1. Khởi tạo resource trong ngoặc `try(...)` theo **thứ tự trái sang phải**.
2. Thực hiện phần thân.
3. Khi thoát scope, gọi `close()` theo **thứ tự ngược lại**.
4. Tiếp tục thử đóng **các resource còn lại** ngay cả nếu một lời gọi `close` ném exception.
5. Nếu body đã ném exception và close cũng ném lỗi, **exception từ body vẫn là primary**; các lỗi close được gắn vào `getSuppressed()`.

### 3.1. Thứ tự đóng trong JDBC

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    // Dùng rs.
}
```

Tạo: `Connection → PreparedStatement → ResultSet`.

Đóng: `ResultSet → PreparedStatement → Connection`.

Đây là cấu trúc hợp lý với dependency graph. Trong ứng dụng thật, SQL có bind parameters thì thường cần `ps.set...` trước khi gọi `executeQuery`; khi đó dùng **khối try lồng** như ví dụ ở mục 1 hoặc dùng khai báo tài nguyên theo phạm vi phù hợp.

### 3.2. Không cần catch chỉ để close thủ công

Trước đây người ta thường viết nhiều `finally` lồng nhau và gọi `close()` thủ công cho từng resource, dễ quên cleanup hoặc vô tình để exception từ close che mất lỗi thực sự.

Trong Java hiện đại, thường **không cần**:

```java
Connection c = null;
PreparedStatement ps = null;
ResultSet rs = null;
// ... hàng loạt kiểm tra null rồi close trong finally ...
```

Đây là ví dụ **anti-pattern trình bày ngắn**. Dùng try-with-resources giúp lifecycle ngắn gọn và quản lý suppressed exceptions đúng hơn.

### 3.3. Nếu khởi tạo tài nguyên thứ hai thất bại

Giả sử `dataSource.getConnection()` thành công, nhưng `connection.prepareStatement(sql)` ném `SQLException`.

Với:

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql)) {
    // ...
}
```

Java tự đóng `c` đã khởi tạo thành công, dù `ps` chưa được gán. **Không bắt buộc chuẩn bị một `finally` riêng chỉ để đóng connection trong trường hợp này**.

Nếu việc đóng `c` tiếp tục lỗi, ngoại lệ close sẽ được xử lý theo quy tắc suppressed exceptions của try-with-resources.

### 3.4. Nếu có return hoặc break sớm

```java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    if (!rs.next()) {
        return java.util.Optional.empty();
    }
    return java.util.Optional.of(rs.getString(1));
}
```

Đây là đoạn minh họa từ method trả `Optional<String>`, có `dataSource`, `sql` phù hợp và `throws SQLException`. Khi method `return`, Java **vẫn đóng** ba resource trước khi thực sự trả về caller.

Điều này cũng áp dụng khi body ném unchecked exception, miễn việc khởi tạo resource đã thành công.

### 3.5. ResultSet đã tự đóng khi Statement.close, vậy còn cần khai báo?

Theo Javadoc, `ResultSet` được statement tạo ra **tự động đóng** khi statement đó đóng, được thực thi lại hoặc chuyển sang result tiếp theo theo hợp đồng JDBC. Tuy nhiên, khai báo `ResultSet` trong try-with-resources vẫn tốt khi:

- Muốn giải phóng cursor **ngay sau khi đọc xong**, trước khi statement/connection kết thúc.
- Muốn làm rõ ownership và scope của cursor.
- Cần quản lý lỗi `ResultSet.close()` riêng và có thể quan sát suppressed exceptions.
- Muốn tránh phụ thuộc vào việc một statement được giữ mở lâu nhưng result set đã không còn dùng.

**Không khẳng định kết quả chỉ được đóng nếu gọi rs.close trực tiếp:** statement.close cũng tự đóng current ResultSet theo JDBC. Và **không** dựa vào garbage collector để đóng đúng lúc.

## 4. Mẫu SQL query nên dùng trong service

Ví dụ một method trả danh sách tên khách hàng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = java.util.Objects.requireNonNull(dataSource);
    }

    public List<String> namesByStatus(String status) throws SQLException {
        List<String> names = new ArrayList<>();
        String sql = "SELECT name FROM customers WHERE status = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setString(1, status);

            try (ResultSet rows = statement.executeQuery()) {
                while (rows.next()) {
                    names.add(rows.getString("name"));
                }
            }
        }
        return List.copyOf(names);
    }
}
```

Đây là **class Java có thể biên dịch**, nhưng để **chạy với database thật** cần `DataSource`/driver phù hợp, schema có bảng `customers` và cột `name/status`. Không có DB cấu hình trong bài nên **không tuyên bố đã chạy SQL thật**. Ví dụ executable test double không cần database ở mục 10.

### 4.1. Thứ tự thao tác

1. Pool cấp connection.
2. JDBC chuẩn bị SQL có parameter placeholder.
3. Bind `status` vào parameter thứ nhất.
4. Execute query, tạo ResultSet.
5. Đọc hết rows và map thành Java strings.
6. Thoát khối ResultSet: đóng cursor.
7. Thoát khối ngoài: đóng statement rồi connection theo thứ tự.
8. Trả immutable list cho caller sau khi resource đã đóng.

### 4.2. Không kéo ResultSet ra ngoài scope

Sai:

```java
ResultSet loadRows(Connection connection) throws SQLException {
    try (PreparedStatement ps =
            connection.prepareStatement("SELECT name FROM customers")) {
        return ps.executeQuery();
    }
}
```

Đây là một method Java hợp lệ về cú pháp nhưng **sai về lifetime**: `ps` đã đóng trước khi caller sử dụng `ResultSet`, và JDBC thường đóng result set đó cùng statement.

Đúng: tạo DTO trong scope rồi trả ra hoặc chuyển ownership của **toàn bộ các tài nguyên liên quan** cho một abstraction có `close` rõ ràng. Với code service thông thường, chọn DTO/list là dễ an toàn nhất.

### 4.3. Đừng trả Stream lazy dựa trên ResultSet đã đóng

Một `Stream` có pipeline thực thi sau khi method trả về có thể cố đọc ResultSet/connection đã đóng. Nếu muốn streaming result lớn, dùng API abstraction có ownership/cancellation/close rõ ràng, hoặc callback nhận row trong scope, không đơn giản bọc `ResultSet` thành Stream rồi đóng resource ngay.

### 4.4. PreparedStatement không an toàn nếu share tùy tiện giữa threads

Một `PreparedStatement` có mutable state như parameters, current result set, execution status. Không biến nó thành global singleton và chia sẻ cross-thread rồi tin `try-with-resources` xử lý mọi race. Thường **mỗi operation/request** sở hữu statement của riêng mình trong connection scope tương ứng.

## 5. Statement.closeOnCompletion() — tính năng Java 7 hiện hành

Ngoài try-with-resources, JDBC còn có:

- `Statement.closeOnCompletion()`
- `Statement.isCloseOnCompletion()`

Đây là API **từ Java 7, vẫn còn trong Java SE hiện đại**. `closeOnCompletion()` yêu cầu statement **tự đóng khi mọi ResultSet phụ thuộc đã đóng**. Nếu execution không tạo result set, lời gọi đó không có tác dụng đóng ngay.

Mô hình:

```java
try (Connection c = dataSource.getConnection();
     Statement st = c.createStatement()) {
    st.closeOnCompletion();

    try (ResultSet rs = st.executeQuery("SELECT name FROM customers")) {
        while (rs.next()) {
            System.out.println(rs.getString(1));
        }
    }
    // Khi ResultSet cuối đã đóng, statement có thể đã tự đóng.
}
```

Đây là đoạn minh họa trong method có `throws SQLException` và `DataSource` đã khai báo. Tính năng này **không thay thế quy tắc đóng Connection**, và có thể làm statement kết thúc sớm hơn dự định nếu code muốn thực hiện query khác sau khi ResultSet cuối đóng.

### 5.1. Khi nào không cần closeOnCompletion?

Trong mẫu phổ biến:

```java
try (Connection c = ...;
     PreparedStatement ps = ...) {
    try (ResultSet rs = ps.executeQuery()) {
        // ...
    }
}
```

try-with-resources đã đảm bảo statement đóng khi ra khỏi scope. `closeOnCompletion` **không bắt buộc** chỉ để tránh leak trong trường hợp này. Chỉ bật nó khi lifetime statement **đúng là** kết thúc cùng với ResultSet cuối và đã hiểu hành vi của driver/provider.

### 5.2. Statement.close không tự đóng Connection

Cần phân biệt hai liên hệ:

- Khi **`Statement.close()`**, current `ResultSet` liên quan được đóng theo JDBC.
- Khi **`Statement.closeOnCompletion()`**, statement tự đóng khi các dependent result sets đã đóng.
- Cả hai **không** có nghĩa JDBC sẽ tự đóng Connection ngay khi statement đóng.

Connection vẫn cần owner và lifecycle riêng.

### 5.3. Re-execute Statement cũng có thể đóng ResultSet hiện tại

Theo Javadoc, mặc định một statement thường chỉ giữ một current result set; gọi execute lại hoặc chuyển sang result tiếp theo có thể làm result set cũ tự đóng. Nếu code cần nhiều result sets sống đồng thời, cần nghiên cứu khả năng driver/database, JDBC `getMoreResults`/holdability và thường dùng những statements độc lập.

Đừng dùng một `ResultSet` như tập dữ liệu sống mãi trong memory sau khi statement đã được tái sử dụng.

## 6. SQLException, suppressed exceptions và nextException

Điều làm try-with-resources đáng giá nhất là **không để lỗi cleanup che lấp lỗi chính**.

Giả sử:

- Body SQL đang đọc rows thì ném `SQLException("query failed")`.
- `ResultSet.close()` ném `SQLException("close result")`.
- `Statement.close()` ném `SQLException("close statement")`.
- `Connection.close()` ném `SQLException("close connection")`.

Khi đó:

- `SQLException("query failed")` là **primary exception**, được ném ra ngoài.
- Các lỗi close nằm trong mảng `primary.getSuppressed()` theo thứ tự đóng: result, statement, connection.
- Java **vẫn thử đóng** statement và connection dù close của ResultSet thất bại.

Đây là ngữ nghĩa cấp **ngôn ngữ Java** của try-with-resources. JDBC driver có thể cung cấp thêm thông tin chi tiết qua `SQLException.getNextException()`; đó là cơ chế **khác** với `Throwable.getSuppressed()`.

### 6.1. Đọc suppressed exceptions

```java
try {
    performDatabaseWork();
} catch (SQLException error) {
    System.err.println(error.getMessage());
    for (Throwable suppressed : error.getSuppressed()) {
        System.err.println("Suppressed during close: "
                + suppressed.getMessage());
    }
    throw error;
}
```

Đoạn này thuộc method có `throws SQLException` và hàm `performDatabaseWork` do ứng dụng định nghĩa. Không log credentials hoặc sensitive SQL parameters trong exception message.

**Đừng nuốt suppressed exceptions** nếu chúng báo một vấn đề cleanup quan trọng, nhưng cũng đừng thay lỗi query chính bằng lỗi đóng secondary.

### 6.2. Nếu body không ném lỗi nhưng close ném lỗi

Một lỗi `close()` sẽ là primary. Nếu nhiều lời gọi close đều thất bại, các lỗi close còn lại trở thành suppressed của lỗi close primary, theo thứ tự ngược khi tài nguyên được khai báo.

Vì vậy **không** được suy: “try-with-resources chỉ có thể ném exception từ executeQuery”. Nó cũng có thể ném từ `close`, kể cả khi SQL body hoàn tất.

### 6.3. SQLException.getNextException() khác getSuppressed()

`SQLException` có linked chain để JDBC driver có thể gắn thêm các lỗi cơ sở dữ liệu. `getNextException()` không phải bản sao của `getSuppressed()`.

Khi chẩn đoán:

- Xem primary `SQLException`: message, SQLState, vendor error code.
- Xem `getSuppressed()`: các lỗi cleanup được Java gắn vào trong try-with-resources.
- Xem `getNextException()` nếu driver cung cấp chuỗi lỗi SQL bổ sung.
- Xem `getCause()` để thấy causal chain chung.

Đừng cố khẳng định mọi driver đều tạo cả bốn loại thông tin trong mọi lỗi.

### 6.4. Lỗi đóng tài nguyên cần được báo theo policy

Khi close connection lỗi, pool có thể đã đánh dấu logical connection không còn dùng được hoặc gặp lỗi mạng. Tầng repository nên propagate hoặc ghi telemetry đủ thông tin; không tự xử lý lại toàn bộ transaction một cách mù quáng khi chưa biết lệnh SQL có commit hay chưa.

## 7. Transaction: close KHÔNG thay commit và rollback

Khi `Connection` hoạt động ở `autoCommit=false`, ứng dụng có trách nhiệm hoàn tất transaction bằng `commit` hoặc `rollback` theo nghiệp vụ.

Javadoc `Connection.close()` nhấn mạnh ứng dụng **nên commit hoặc rollback active transaction trước khi close**. Nếu đóng khi transaction còn hoạt động, kết quả là **implementation-defined**.

Vì vậy:

- **Không** mặc định `Connection.close` tự rollback cho mọi JDBC driver/pool.
- **Không** mặc định `try-with-resources` tự commit thành công.
- **Không** viết `finally { c.close(); }` thay cho transaction state management.
- Nếu là pooled connection, đừng dựa vào chính sách reset của pool để thay giao thức transaction của ứng dụng.

### 7.1. Mẫu transaction có commit/rollback tường minh

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, long amount)
            throws SQLException {
        try (Connection c = dataSource.getConnection()) {
            c.setAutoCommit(false);
            try {
                String debitSql =
                        "UPDATE accounts SET balance = balance - ? " +
                        "WHERE id = ? AND balance >= ?";
                String creditSql =
                        "UPDATE accounts SET balance = balance + ? " +
                        "WHERE id = ?";

                try (PreparedStatement debit =
                             c.prepareStatement(debitSql);
                     PreparedStatement credit =
                             c.prepareStatement(creditSql)) {
                    debit.setLong(1, amount);
                    debit.setLong(2, fromId);
                    debit.setLong(3, amount);

                    credit.setLong(1, amount);
                    credit.setLong(2, toId);

                    if (debit.executeUpdate() != 1
                            || credit.executeUpdate() != 1) {
                        throw new SQLException(
                                "Transfer rejected or account absent");
                    }
                }
                c.commit();
            } catch (SQLException | RuntimeException error) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
    }
}
```

Đây là **ví dụ class về transaction lifecycle**, không phải mẫu nghiệp vụ ngân hàng production đầy đủ. Để chạy thực tế cần DB, schema, ràng buộc amount dương, đơn vị tiền tệ, isolation level, phòng đồng thời chuyển khoản, deadlock retry, idempotency và quyền truy cập. Không dùng trực tiếp cho tài chính thật mà chưa thiết kế đúng.

Các điểm về resource:

1. `Connection` là resource ngoài cùng, tự đóng cuối.
2. Hai `PreparedStatement` tự đóng khi khối trong kết thúc.
3. Commit **sau khi statements hoàn thành**, **trước khi Connection đóng**.
4. Nếu query/update hoặc close của statement ném `SQLException`, code rollback trước khi đóng connection.
5. Nếu rollback cũng thất bại, lỗi rollback được thêm vào `error.getSuppressed()` rồi lỗi chính được ném tiếp.

**Chú ý:** nếu `c.setAutoCommit(false)` thất bại trước khối `try` bên trong, try-with-resources vẫn đóng connection. Nếu có transaction đang hoạt động theo một state ngoài dự kiến, cần policy riêng của provider. Ví dụ mô tả đường đi phổ biến chứ không bao quát mọi failure mode của một distributed transaction.

### 7.2. Vì sao không đặt commit trong finally?

Nếu luôn `commit()` trong `finally`, bạn có thể commit các thay đổi nửa chừng khi business logic đã ném lỗi. Phải commit ở **nhánh thành công**; rollback ở **nhánh lỗi** theo contract của transaction.

### 7.3. Nếu đang dùng framework quản lý transaction

Trong Spring/Jakarta EE hoặc một transaction manager khác, framework có thể là **owner của Connection và transaction**. Khi đó, đừng tự đóng connection do framework cung cấp theo cách phá vỡ active transaction; dùng API/framework quản lý scope mà thành phần đó quy định. Try-with-resources vẫn thích hợp cho những JDBC resources mà chính code của bạn thật sự sở hữu.

**Ownership quan trọng hơn việc ép mọi object vào try-with-resources.**

## 8. Connection pool và phạm vi request

### 8.1. Câu “đóng connection” có hai nghĩa

Với `DriverManager.getConnection` không qua pool, `Connection.close` thường đóng kết nối JDBC/physical resource. Với `DataSource` có pool, `close` trên connection wrapper thường **trả logical connection về pool** cho request khác, physical connection được giữ để tái sử dụng.

Bởi vậy, quy tắc production vẫn là **luôn close logical Connection đúng lúc**, ngay cả khi pool không thực sự đóng network socket.

### 8.2. Pool leak nguy hiểm hơn một truy vấn chậm

Nếu code mượn 10 connections từ pool 10 slots rồi không trả lại, request thứ 11 có thể bị chặn tới timeout dù database khỏe. Leak thường xuất hiện trong nhánh exception/early return — đúng nơi try-with-resources có ích nhất.

Đo:

- Active/idle/pending connections theo pool metrics.
- Thời gian mượn connection.
- SQL duration, số result sets/cursors mở.
- Lỗi execute và lỗi close.
- Transaction commit/rollback outcome.

Không dựa vào garbage collection để trả connection về pool đúng thời điểm.

### 8.3. Ai sở hữu Connection?

| Nguồn cấp | Owner thường gặp | Cách đóng |
| --- | --- | --- |
| Repository tự gọi `dataSource.getConnection()` | Repository/method đó | TWR quanh Connection |
| Framework transaction context cung cấp Connection | Framework/transaction manager | Tuân contract framework, không tự ý close |
| Method nhận Connection từ caller | Caller hoặc hợp đồng rõ | Không close trong callee nếu không sở hữu |
| Test double Connection | Test harness | TWR và assertions theo contract giả lập |

Một method nhận `Connection c` từ caller **không mặc nhiên** được đóng nó: caller có thể còn cần dùng cho transaction nhiều statement. Nên ghi rõ quyền sở hữu ở API.

### 8.4. Không giữ connection trong singleton field

`private final Connection connection` sống suốt đời dịch vụ có thể trở thành điểm tranh chấp, giữ transaction state ngoài mong đợi và cản connection pool. Thường giữ `DataSource` trong repository, rồi mượn và trả connection theo scope cần thiết.

## 9. Những điểm tinh tế với ResultSet, Statement và I/O

### 9.1. ResultSet có thể bị đóng do Statement re-execute

`Statement.executeQuery`, `execute` hoặc thao tác chuyển result có thể đóng current `ResultSet` do statement đang quản lý. Vì vậy:

```java
ResultSet old = statement.executeQuery("SELECT id FROM a");
ResultSet newer = statement.executeQuery("SELECT id FROM b");
// old thường đã bị đóng khi statement thực thi query thứ hai.
```

Đây là đoạn minh họa **không có cleanup đúng** để nhấn mạnh lifetime. Trong production, dùng riêng statements/scopes thích hợp và đóng đúng tài nguyên.

### 9.2. getGeneratedKeys cũng trả một ResultSet

Sau một lệnh insert, `statement.getGeneratedKeys()` trả về `ResultSet`. Cần đọc và đóng đúng scope như result set của `executeQuery`. Việc không đóng generated keys cursor có thể gây leak.

```java
try (ResultSet keys = statement.getGeneratedKeys()) {
    while (keys.next()) {
        long generatedId = keys.getLong(1);
        // Lưu ID vào DTO/kết quả.
    }
}
```

Đây là đoạn minh họa; phải chuẩn bị statement với generated-key mode mà driver hỗ trợ và method xử lý `SQLException`.

### 9.3. BLOB/CLOB/streams phụ thuộc ResultSet và Connection

Nếu code nhận `InputStream` hoặc `Reader` từ dữ liệu cột, vòng đời dữ liệu streaming có thể phụ thuộc cursor và connection. Không gửi stream đang lazy-read ra ngoài try-with-resources rồi đóng ResultSet/Connection trước khi caller đọc.

Khi cần trả bytes/text, hãy xử lý/đọc dữ liệu trong scope, hoặc chuyển ownership của toàn bộ resource chain qua một abstraction có `close` rõ ràng.

### 9.4. Không cần đóng mọi thứ hai lần

`ResultSet.close` và `Statement.close` đã có hành vi khi đã đóng theo Javadoc. Nhưng trong code thông thường, tránh gọi thủ công rồi lại đóng qua TWR nếu không có yêu cầu cụ thể; điều đó tạo noise và có thể làm lẫn thứ tự/logging.

Để scope rõ ràng, viết resource declaration và để Java close tự động.

### 9.5. Không có ResultSet cho mọi câu SQL

`executeUpdate` trả row count, không phải `ResultSet`. `execute` có thể trả result set hoặc update count, cần logic đúng với từng loại. **Đừng tạo giả một ResultSet chỉ để đủ ba resource trong TWR**; chỉ đóng cái gì thực sự đã được tạo và do mình sở hữu.

### 9.6. ResultSet metadata không phải ResultSet

`ResultSetMetaData` là một abstraction thông tin metadata; không tự giả định nó có `close()` như `ResultSet`. Đọc dữ liệu metadata trong scope ResultSet khi cần, không cố ép mọi object JDBC vào try-with-resources nếu nó không triển khai `AutoCloseable`.

### 9.7. closeOnCompletion không tự auto-commit

Đóng Statement khi ResultSet cuối đóng **không** đồng nghĩa transaction đã commit. Commit/rollback thuộc Connection hoặc transaction manager; không trộn lifecycle cursor với finalization of transaction.

## 10. Chương trình Java 17+ chạy được không cần database thật

Để kiểm tra **ngữ nghĩa Java try-with-resources và hợp đồng interface JDBC** mà không phụ thuộc server/driver, chương trình `JdbcResourceLifecycleDemo.java` dùng **dynamic proxy** triển khai tối thiểu `Connection`, `PreparedStatement` và `ResultSet`.

Đây là một **test double**: nó giả lập việc trả một dòng tên "Ada", và ghi nhận thứ tự các lời gọi `close`. Nó **không** xác minh JDBC driver/database thật thực hiện SQL đúng, không test network/pool behavior và không cung cấp đầy đủ mọi phương thức JDBC. Khi muốn kiểm thử truy vấn SQL thật, dùng test database/driver được cấu hình hoặc integration test phù hợp.

Bài demo gồm:

1. Chạy một method repository gọi `prepareStatement`, `setLong`, `executeQuery`, `next` và `getString`.
2. Thoát try-with-resources, xác minh **ResultSet, PreparedStatement, Connection** được đóng theo thứ tự ngược.
3. Tạo một test double khác có `close` của **cả ba tài nguyên** đều cố tình ném `SQLException`.
4. Trong phần thân try, cố tình ném `SQLException("body failure")`.
5. Xác minh exception từ body vẫn primary, cả ba `close` vẫn được thử và có đúng ba suppressed exceptions theo thứ tự đóng.
6. In sáu dòng trạng thái ổn định.

### 10.1. Mã đầy đủ: JdbcResourceLifecycleDemo.java

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class JdbcResourceLifecycleDemo {
    @FunctionalInterface
    interface ConnectionSupplier {
        Connection open() throws SQLException;
    }

    private static void check(boolean condition, String reason) {
        if (!condition) throw new AssertionError(reason);
    }

    static List<String> findNames(ConnectionSupplier source, long customerId)
            throws SQLException {
        List<String> names = new ArrayList<>();
        try (Connection connection = source.open();
             PreparedStatement statement = connection.prepareStatement(
                     "SELECT name FROM customers WHERE id = ?")) {
            statement.setLong(1, customerId);
            try (ResultSet results = statement.executeQuery()) {
                while (results.next()) {
                    names.add(results.getString("name"));
                }
            }
        }
        return names;
    }

    static final class Session implements InvocationHandler {
        final List<String> closeOrder = new ArrayList<>();
        final boolean failClose;
        final Connection connection;
        final PreparedStatement statement;
        final ResultSet results;
        private boolean firstRow = true;

        Session(boolean failClose) {
            this.failClose = failClose;
            connection = proxy(Connection.class);
            statement = proxy(PreparedStatement.class);
            results = proxy(ResultSet.class);
        }

        private <T> T proxy(Class<T> type) {
            return type.cast(Proxy.newProxyInstance(
                    type.getClassLoader(), new Class<?>[] {type}, this));
        }

        @Override
        public Object invoke(Object proxy, Method method, Object[] arguments)
                throws Throwable {
            String methodName = method.getName();
            if ("prepareStatement".equals(methodName)) return statement;
            if ("setLong".equals(methodName)) return null;
            if ("executeQuery".equals(methodName)) return results;
            if ("next".equals(methodName)) {
                boolean result = firstRow;
                firstRow = false;
                return result;
            }
            if ("getString".equals(methodName)) return "Ada";
            if ("close".equals(methodName)) {
                String type;
                if (proxy == connection) type = "Connection";
                else if (proxy == statement) type = "PreparedStatement";
                else type = "ResultSet";
                closeOrder.add(type);
                if (failClose) throw new SQLException("close " + type);
                return null;
            }
            if ("toString".equals(methodName)) return "JDBC test double";
            throw new UnsupportedOperationException(
                    "Test double: " + methodName);
        }
    }

    public static void main(String[] args) throws Exception {
        Session normal = new Session(false);
        List<String> names = findNames(() -> normal.connection, 7);
        check(names.equals(List.of("Ada")), "query row result");
        check(normal.closeOrder.equals(
                        List.of("ResultSet", "PreparedStatement", "Connection")),
                "resources must close in reverse order");
        System.out.println("query mapped = Ada");
        System.out.println(
                "close order = ResultSet,PreparedStatement,Connection");

        Session failures = new Session(true);
        SQLException primary = null;
        try (Connection c = failures.connection;
             PreparedStatement st = c.prepareStatement("SELECT 1");
             ResultSet rs = st.executeQuery()) {
            check(rs != null, "expected test ResultSet");
            throw new SQLException("body failure");
        } catch (SQLException expected) {
            primary = expected;
        }
        check(primary != null
                        && "body failure".equals(primary.getMessage()),
                "body exception must remain primary");
        check(failures.closeOrder.equals(
                        List.of("ResultSet", "PreparedStatement", "Connection")),
                "failed closes should still run in order");

        Throwable[] suppressed = primary.getSuppressed();
        check(suppressed.length == 3,
                "all close failures must be suppressed");
        List<String> messages = Arrays.stream(suppressed)
                .map(Throwable::getMessage).toList();
        check(messages.equals(List.of(
                        "close ResultSet", "close PreparedStatement",
                        "close Connection")), "suppressed close order");

        System.out.println("body exception stayed primary = true");
        System.out.println("three close exceptions suppressed = true");
        System.out.println("all close attempts performed = true");
        System.out.println("checks = PASS");
    }
}
```

### 10.2. Lệnh biên dịch/chạy

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 JdbcResourceLifecycleDemo.java
java JdbcResourceLifecycleDemo
```

Đã biên dịch không cảnh báo và chạy thành công trên JDK 17. **Stdout chính xác:**

```text
query mapped = Ada
close order = ResultSet,PreparedStatement,Connection
body exception stayed primary = true
three close exceptions suppressed = true
all close attempts performed = true
checks = PASS
```

Không có SQL database nào được kết nối thật trong lượt test này. Test double chỉ kiểm tra lời gọi và vòng đời tài nguyên Java; khi dùng driver thật, cần bổ sung bài test kết nối, truy vấn, transaction/pool behavior theo môi trường.

### 10.3. Vì sao dùng Proxy thay vì tạo một database giả?

`Connection`, `Statement` và `ResultSet` có nhiều phương thức bắt buộc. Dynamic proxy cho phép test double chỉ triển khai các phương thức sẽ gọi trong demo, ghi lại `close` theo thứ tự. Điều này phù hợp khi muốn kiểm tra **cơ chế của Java** mà không cần dependency bên ngoài.

Không khuyến nghị dùng test double chưa triển khai đầy đủ này để thay một database trong integration test; nó không kiểm tra SQL syntax, isolation, cursor behavior hoặc JDBC driver protocol.

### 10.4. Vì sao test primary exception khi body lỗi?

Nếu cả query và close đều thất bại, điều quan trọng là **nguyên nhân gốc của việc thực thi body không bị thay thế** chỉ vì cleanup cũng lỗi. `getSuppressed()` giữ các lỗi cleanup để quan sát/diagnose.

Trong demo, exception chính có message "body failure"; lần lượt các lỗi đóng result, statement, connection nằm trong suppressed array.

### 10.5. Test này chưa chứng minh điều gì?

Nó **chưa** kiểm thử:

- Pool trả logical Connection về pool.
- Server-side cursor trên một database cụ thể.
- Commit/rollback trong một transaction thật.
- SQL parameter binding đúng với schema thật.
- Statement reexecution có close current ResultSet theo behavior driver.
- Timeout mạng hoặc lỗi socket/server bị disconnect.

Đó là các bài integration/contract tests riêng khi dự án có driver và database thích hợp.

## 11. Chiến lược kiểm thử production code JDBC

### 11.1. Unit test

Với repository cho phép inject `DataSource` hoặc `ConnectionSupplier`:

- Test SQL được prepare và parameters được bind đúng.
- Test mapping `ResultSet` sang DTO.
- Test đóng resource trong nhánh thành công.
- Test đóng resource khi query/mapping ném exception.
- Test close ordering và suppressed exceptions khi cần.
- Test không trả ResultSet đã closed ra ngoài scope.

Dynamic proxy/mock phù hợp cho những assertion không cần DB thật.

### 11.2. Integration test với database thật

Dùng DB/driver phù hợp môi trường dự án để kiểm tra:

- Kết quả SQL và schema thực tế.
- Transaction commit/rollback, isolation, lock và timeout.
- Pool checkout/checkin, connection leak detection.
- Cursor/LOB streaming và đóng resource.
- Các exception SQLState/vendor code có thể xuất hiện.
- Prepared statement cache và behavior driver nếu dự án có dùng.

Unit test giả lập **không thay thế** test thực tế với DB.

### 11.3. Load test connection leaks

Dưới tải, đo active/idle/pending connections và thời gian checkout. Một repository có thể vượt unit tests mà vẫn leak khi có async callback hoặc stream giữ reference. Thiết kế cần ranh giới ownership rõ trong các đường lỗi hoặc cancellation.

### 11.4. Không dựa vào số lần close của driver như một invariant phổ quát

JDBC quy định một vài thao tác close là no-op khi đã đóng, và statement.close đóng ResultSet hiện tại. Driver/pool có thể thực hiện cleanup nội bộ khác nhau. Test ở tầng Java nên assert **số lời gọi close do code sở hữu** khi mock, nhưng không khẳng định mọi backend nhận đúng ba network messages close theo cùng thứ tự.

## 12. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Không đóng ResultSet | Có thể giữ cursor/buffer lâu | TWR scope ngắn |
| Chỉ close Connection khi query thành công | Nhánh exception leak connection | TWR bao toàn operation |
| Trả ResultSet từ method rồi đóng Statement | Caller nhận cursor đã đóng | Map DTO trong scope |
| Dùng `Statement` với SQL nối input | SQL injection | `PreparedStatement` + bind |
| Nghĩ ResultSet tự đóng chỉ khi tự gọi rs.close | JDBC còn auto-close khi statement đóng/reexecute | Hiểu dependency + đóng tường minh khi có ích |
| Nghĩ đóng ResultSet tự đóng Connection | Không có cam kết đó | Owner đóng Connection riêng |
| Nghĩ `closeOnCompletion` auto-commit transaction | Không liên quan commit | Commit/rollback qua Connection |
| Bật closeOnCompletion rồi dùng Statement tiếp | Statement có thể đã đóng | Chỉ dùng nếu lifecycle đúng |
| Dùng `try(Connection)` nhưng quên Statement | Có thể resource statement tồn tại đến khi connection đóng | Khai báo PS/RS TWR |
| Close mọi resource cùng chiều khai báo | Phụ thuộc sai | TWR đóng ngược thứ tự |
| Catch exception chỉ để ignore | Mất diagnostic và che lỗi chính | Propagate/log theo policy |
| Không xem getSuppressed | Bỏ sót lỗi cleanup | Inspect suppressed cùng primary |
| Nhầm getNextException với getSuppressed | Không tìm được lỗi đúng nơi | Hiểu JDBC exception chain |
| Close Connection và nghĩ tự rollback hết | Active transaction outcome implementation-defined | Commit/rollback tường minh |
| Đặt commit trong finally | Có thể commit phần việc lỗi | Commit nhánh thành công |
| Không rollback khi update một nửa thất bại | Dữ liệu không nhất quán | Transaction rollback |
| TWR Connection do framework sở hữu | Có thể phá active transaction | Tuân ownership contract |
| Singleton một Connection cho mọi request | Rủi ro contention/state/leak | Pool per-scope checkout |
| Không close pooled Connection vì muốn giữ socket | Pool bị cạn | Đóng logical wrapper để trả pool |
| Nghĩ Connection.close luôn đóng physical socket | Pool thường tái sử dụng physical DB link | Hiểu pool provider |
| Dùng ResultSet sau khi Statement reexecute | Cursor cũ thường đóng | Scope và statements phù hợp |
| Không đóng getGeneratedKeys | Leak result set/cursor | TWR với generated keys |
| Trả lazy Stream phụ thuộc cursor đã đóng | Lỗi đọc sau scope | Map trong scope hoặc ownership rõ |
| Share PreparedStatement mutable giữa threads | Parameter/result races | Statement theo operation |
| Dùng SQL mock rồi khẳng định DB thật đúng | Mock không có engine/driver | Integration test |
| Không xử lý close SQLException | Lỗi cleanup bị che | Propagate/telemetry, suppressed |
| Quên pool metrics | Leak không được quan sát | Checkout/active/pending metrics |
| Dùng JVM GC thay lifecycle | Không deterministic | TWR/explicit owner |
| Không tính cancellation/error path | Leak khi request bị hủy | TWR bao toàn flow |

## 13. Bài tập kèm đáp án

### Bài 1 — Ba resource

Các đối tượng JDBC nào nên có scope đóng tường minh cho một query đơn giản?

**Đáp án:** `Connection`, `Statement`/`PreparedStatement` và `ResultSet`, theo ownership của operation. TWR hỗ trợ `AutoCloseable` của cả ba.

### Bài 2 — Thứ tự close

Một TWR khai báo `Connection c`, `PreparedStatement ps`, `ResultSet rs` theo thứ tự đó. Khi thoát scope, thứ tự close?

**Đáp án:** `rs.close()` → `ps.close()` → `c.close()`.

### Bài 3 — Early return

Method `return` ngay trong khối ResultSet vì không có row. Các resource có tự đóng không?

**Đáp án:** Có. TWR đóng khi rời scope trước khi return thật sự hoàn tất.

### Bài 4 — Init failure

`getConnection()` thành công, `prepareStatement()` ném lỗi. Connection đã tạo có được tự đóng không?

**Đáp án:** Có. TWR đóng các resource được khởi tạo thành công trước đó.

### Bài 5 — ResultSet tự đóng

Nếu `Statement.close()` được gọi khi còn current ResultSet, JDBC có đóng ResultSet không?

**Đáp án:** Có, current ResultSet được statement đóng theo Javadoc. TWR ResultSet vẫn giúp scope ngắn và rõ hơn.

### Bài 6 — getMoreResults

Statement thực thi nhiều results. Có thể luôn tiếp tục dùng ResultSet cũ sau khi lấy result mới không?

**Đáp án:** Không mặc định. Execution/getMoreResults có semantics đóng current result tùy mode; phải tuân hợp đồng và driver support.

### Bài 7 — TWR với parameters

Tại sao ví dụ production thường lồng khối `ResultSet` trong khối PS/Connection?

**Đáp án:** Vì cần bind parameters trên `PreparedStatement` **trước khi** gọi `executeQuery()`, rồi đóng ResultSet ngay sau khi đọc xong.

### Bài 8 — closeOnCompletion

`closeOnCompletion()` dùng để làm gì?

**Đáp án:** Yêu cầu statement tự đóng khi tất cả dependent result sets đóng; nó không tự đóng Connection hoặc commit transaction.

### Bài 9 — Statement không tạo ResultSet

Đã gọi `closeOnCompletion()`, nhưng statement execution không trả ResultSet. Statement có phải đóng ngay do tính năng này không?

**Đáp án:** Không; theo Javadoc, khi execution không tạo ResultSet thì lời gọi không có tác dụng tự đóng như vậy.

### Bài 10 — Exception body

SQL body ném lỗi, rồi close ResultSet cũng ném lỗi. Exception nào primary?

**Đáp án:** Lỗi body primary; lỗi close được thêm vào `getSuppressed()`.

### Bài 11 — Close nhiều lỗi

ResultSet, Statement và Connection close đều ném lỗi sau body failure. TWR có dừng sau close ResultSet đầu không?

**Đáp án:** Không. Java tiếp tục thử đóng các resource còn lại; các lỗi cleanup được gắn suppressed.

### Bài 12 — Next exception

`SQLException.getNextException()` có chính là `Throwable.getSuppressed()` không?

**Đáp án:** Không. NextException là JDBC exception chain, suppressed là lỗi phụ gắn vào primary theo Java exception handling.

### Bài 13 — Auto-commit false

Đã gọi `c.setAutoCommit(false)` rồi thao tác thành công; chỉ ra khỏi TWR, không commit. Có bảo đảm các thay đổi được commit không?

**Đáp án:** Không. Active transaction khi close có outcome implementation-defined; phải explicit commit/rollback.

### Bài 14 — Rollback

Query thứ hai trong transaction thất bại. Có nên commit trong finally không?

**Đáp án:** Không. Rollback theo policy lỗi trước khi đóng Connection; commit chỉ khi toàn bộ transaction thành công.

### Bài 15 — Connection pool

Trong ứng dụng có pool, `Connection.close()` thường có tác dụng gì?

**Đáp án:** Trả logical connection cho pool/tái sử dụng, không nhất thiết đóng physical DB socket ngay.

### Bài 16 — Framework ownership

Một framework cấp Connection đang tham gia transaction do framework quản lý. Repository có nên luôn tự close nó?

**Đáp án:** Không tự ý. Phải tuân hợp đồng ownership/transaction của framework.

### Bài 17 — Trả ResultSet

`loadRows` trả `ResultSet` nhưng `PreparedStatement` được đóng trước method return. Caller có dùng được cursor đó không?

**Đáp án:** Không nên. Statement đóng sẽ đóng current ResultSet; trả DTO/list đã map trong scope.

### Bài 18 — getGeneratedKeys

Insert trả generated keys qua `ResultSet`. Có cần đóng result này không?

**Đáp án:** Có, nên đọc và đóng trong TWR scope tương ứng.

### Bài 19 — Lazy Stream

Một Stream lấy dữ liệu từ ResultSet được trả ra ngoài sau khi TWR đóng connection. Rủi ro?

**Đáp án:** Khi evaluate lazy stream, tài nguyên đã đóng. Cần map trong scope hoặc streaming abstraction giữ ownership và close hợp lệ.

### Bài 20 — PreparedStatement cross-thread

Có nên dùng một mutable PreparedStatement global cho nhiều concurrent requests?

**Đáp án:** Không khuyến nghị. Parameters/current result và lifetime có thể cạnh tranh. Dùng statement theo scope operation.

### Bài 21 — Không có database

Test dùng Proxy ghi close order thành công. Đã chứng minh SQL production chạy đúng trên PostgreSQL/MySQL chưa?

**Đáp án:** Chưa. Nó chỉ kiểm chứng ngữ nghĩa TWR và lời gọi interface; cần integration test với driver/database thật.

### Bài 22 — Test query không có row

Trong method TWR, `rs.next()` trả false ngay. Việc ResultSet rỗng có làm TWR bỏ qua close không?

**Đáp án:** Không. TWR đóng tài nguyên dù không có row.

### Bài 23 — isClosed

`Connection.isClosed()==false` có đảm bảo socket tới database còn healthy không?

**Đáp án:** Không. Phải dùng cơ chế validation/operation thực theo provider, không dùng isClosed như health-check đủ mạnh.

### Bài 24 — Lỗi ResultSet.close

Nếu ResultSet.close ném SQLException nhưng Statement/Connection.close thành công, TWR có thể vẫn throw không?

**Đáp án:** Có. Nếu body không có lỗi, close SQLException có thể là primary; cần xử lý/log theo policy.

## 14. Checklist áp dụng trong dự án

- [ ] Xác định **ai sở hữu** từng Connection/Statement/ResultSet.
- [ ] Ưu tiên `DataSource`/pool và connection scope ngắn trong server.
- [ ] Dùng `PreparedStatement` + bind parameters cho input thay vì SQL nối chuỗi.
- [ ] Khai báo resource trong `try(...)` để auto-close.
- [ ] Đóng theo thứ tự phụ thuộc: ResultSet → Statement → Connection.
- [ ] Dùng TWR kể cả khi code có return sớm hoặc có thể ném exception.
- [ ] Hiểu resource tạo thành công vẫn đóng khi khởi tạo resource sau bị lỗi.
- [ ] Đọc toàn bộ ResultSet cần dùng và map sang DTO trong scope.
- [ ] Không trả ResultSet/lazy Stream mà resource owner đã đóng.
- [ ] Không giữ một PreparedStatement mutable global cross-thread.
- [ ] Hiểu statement.close đóng current ResultSet; vẫn có thể close explicit sớm.
- [ ] Biết `closeOnCompletion`, không tự động bật nếu sẽ dùng statement tiếp.
- [ ] Đóng ResultSet từ `getGeneratedKeys` khi có.
- [ ] Không coi `close()` thay commit/rollback.
- [ ] Với autoCommit=false, explicit commit thành công và rollback lỗi trước close.
- [ ] Nếu rollback lỗi, lưu suppressed/telemetry mà không che lỗi chính.
- [ ] Phân biệt `getSuppressed`, `getNextException` và `getCause`.
- [ ] Không nuốt close SQLException quan trọng.
- [ ] Không tự close Connection do framework transaction sở hữu.
- [ ] Luôn trả logical pooled Connection đúng lúc qua close theo provider.
- [ ] Theo dõi pool active/idle/pending, checkout duration và leak metrics.
- [ ] Test happy path, early return, init failure, body failure và close failure.
- [ ] Test close order với unit doubles, test SQL thật riêng với database.
- [ ] Không dùng GC làm cơ chế cleanup.
- [ ] Không dùng API đã deprecated/legacy khi Java hiện đại có TWR/JDBC hiện hành.

## 15. Tài liệu Java SE chính thức

- [Java SE 17 — Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `close`, transaction, autoCommit, commit/rollback, `isClosed`.
- [Java SE 17 — Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html): `close`, đóng current ResultSet, `closeOnCompletion`, `getMoreResults`.
- [Java SE 17 — PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding và query/update.
- [Java SE 17 — ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html): `next`, `close`, cursor và dependency vào Statement.
- [Java SE 17 — SQLException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code và `getNextException`.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html): hợp đồng `close()` cho try-with-resources.
- [Java SE 17 — Java Language Specification, try-with-resources](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.3): thứ tự khởi tạo/đóng và suppressed exceptions.
- [Java SE 17 — DataSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html): abstraction lấy connection và dữ liệu cấu hình provider.

## 16. Tổng kết

Để viết JDBC code rõ ràng, an toàn về vòng đời tài nguyên, hãy đặt `Connection`, `PreparedStatement/Statement` và `ResultSet` trong **try-with-resources**, sao cho Java **đóng theo thứ tự ngược của khai báo** và không bỏ qua cleanup khi return, exception hoặc resource initialization lỗi. Dùng `PreparedStatement` cho SQL có tham số, đọc dữ liệu trong scope ResultSet và **trả DTO đã map**, không trả cursor đã bị đóng.

`Statement.close()` tự đóng current ResultSet, nhưng đóng ResultSet tường minh vẫn làm scope và thời điểm release rõ hơn. `Statement.closeOnCompletion()` là API Java 7 hiện hành khi thật sự muốn statement tự đóng cùng dependent result sets — không phải cách tự đóng Connection hay commit.

Với **transaction**, commit hoặc rollback **trước khi đóng Connection**; không giao kết quả transaction cho hành vi close implementation-defined. Với **connection pool**, close thường trả logical connection về pool; vẫn phải gọi close theo ownership. Khi gặp nhiều lỗi, Java giữ lỗi body làm primary và lưu lỗi close qua **suppressed exceptions** để điều tra đầy đủ.

Cuối cùng, test double JDBC có thể chứng minh ngữ nghĩa đóng của **Java**, nhưng kiểm tra driver/SQL/transaction/pool thực tế vẫn cần integration tests với database tương ứng. Tất cả các nguyên tắc này vẫn quan trọng với **Java 17+ và các phiên bản Java hiện hành**.