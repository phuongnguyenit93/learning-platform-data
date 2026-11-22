# Thiết lập mức cô lập và kiểm tra giá trị đang có hiệu lực

Trong **JDBC (Java Database Connectivity)**, khi nhiều giao dịch cùng đọc hoặc ghi dữ liệu của một cơ sở dữ liệu quan hệ, kết quả mà mỗi giao dịch quan sát được phụ thuộc vào **mức cô lập giao dịch** (*transaction isolation level*). JDBC cung cấp hai API chính trên `java.sql.Connection`:

- `setTransactionIsolation(int level)`: yêu cầu đặt mức cô lập cho kết nối.
- `getTransactionIsolation()`: đọc mức cô lập mà đối tượng kết nối JDBC hiện báo cáo.

Bài học thuộc chương **Quản lý kết nối**. Bạn sẽ học cách chọn mức cô lập, kiểm tra driver và cơ sở dữ liệu có hỗ trợ hay không, xác minh giá trị sau khi thiết lập, đặt mức cô lập **trước khi bắt đầu giao dịch**, và tránh làm rò rỉ cấu hình khi dùng connection pool.

## 1. Vì sao mức cô lập là thuộc tính của Connection?

Một ứng dụng quản lý đơn hàng có thể đồng thời xử lý hai giao dịch:

~~~text
Thời gian ──────────────────────────────────────────────────→

Giao dịch A                       Giao dịch B
────────────────────             ────────────────────────
Đọc số lượng tồn kho
                                 Cập nhật số lượng tồn kho
                                 COMMIT
Đọc lại số lượng tồn kho
COMMIT

Câu hỏi: Hai lần đọc ở A phải thấy cùng một giá trị hay có thể khác?
~~~

Điều đó tùy **mức cô lập**, hành vi cụ thể của hệ quản trị (DBMS), thời điểm giao dịch bắt đầu và các lệnh SQL liên quan. JDBC định nghĩa các mức cô lập chuẩn để ứng dụng yêu cầu với driver. Driver thực hiện yêu cầu bằng cơ chế của cơ sở dữ liệu, chẳng hạn khóa hoặc *multiversion concurrency control* (MVCC).

`Connection` mang trạng thái liên quan đến giao dịch như `autoCommit`, mức cô lập, chế độ chỉ đọc và các cấu hình phiên khác. `Statement` hoặc `PreparedStatement` được tạo từ kết nối đó thường thực thi trong ngữ cảnh giao dịch của chính `Connection`.

Do vậy, khi cần mức cô lập nhất định cho một nhóm lệnh SQL, bạn phải bảo đảm **các lệnh đó dùng cùng một Connection và nằm trong đúng giao dịch**. Đặt mức cô lập trên kết nối A không tự thay đổi mức cô lập của kết nối B.

## 2. Bốn mức cô lập chuẩn trong JDBC

JDBC định nghĩa các hằng số của `java.sql.Connection`:

| Hằng số | Ý nghĩa tiêu biểu | Những hiện tượng có thể xảy ra theo mô hình JDBC |
| --- | --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | Mức cô lập thấp nhất trong bốn mức thông dụng | Có thể đọc dữ liệu chưa commit, đọc không lặp lại và phantom |
| `TRANSACTION_READ_COMMITTED` | Không đọc các thay đổi chưa commit của giao dịch khác | Có thể đọc không lặp lại và phantom |
| `TRANSACTION_REPEATABLE_READ` | Một hàng đã đọc không bị thay đổi theo kiểu non-repeatable read trong giao dịch | Theo mô hình chuẩn, phantom vẫn có thể xảy ra |
| `TRANSACTION_SERIALIZABLE` | Mạnh nhất trong bốn mức chuẩn; bảo đảm hiệu ứng tương đương một thứ tự thực thi tuần tự hợp lệ | Ngăn ba hiện tượng điển hình theo mô hình chuẩn; vẫn có thể phải xử lý xung đột/retry |

Ba hiện tượng cần phân biệt:

1. **Dirty read**: giao dịch A đọc dữ liệu B đã ghi nhưng **chưa commit**; B sau đó rollback nên giá trị A thấy không được xác nhận.
2. **Non-repeatable read**: trong cùng một giao dịch A, đọc lại **cùng một hàng** cho kết quả khác vì giao dịch khác đã commit thay đổi liên quan.
3. **Phantom read**: A thực hiện lại một truy vấn theo **điều kiện tìm kiếm**, rồi thấy tập hàng phù hợp thay đổi vì giao dịch khác đã commit thêm/xóa/sửa các hàng khớp điều kiện.

~~~text
Ví dụ non-repeatable read
A: SELECT price FROM products WHERE id = 1;    → 100
B: UPDATE products SET price = 120 WHERE id = 1;
B: COMMIT;
A: SELECT price FROM products WHERE id = 1;    → 120 (nếu mức cô lập cho phép)

Ví dụ phantom
A: SELECT COUNT(*) FROM orders WHERE status = 'NEW'; → 10
B: INSERT INTO orders(status) VALUES ('NEW');
B: COMMIT;
A: SELECT COUNT(*) FROM orders WHERE status = 'NEW'; → 11 (nếu cho phép)
~~~

**Các bảng trên mô tả mô hình ANSI/JDBC, không phải dự đoán chính xác cho mọi DB.** Nhiều hệ quản trị dùng MVCC có ngữ nghĩa riêng: một DB có thể thực thi `READ_UNCOMMITTED` gần giống `READ_COMMITTED`; một DB khác có thể chặn phantom ở `REPEATABLE_READ` theo snapshot. Ngay cả `SERIALIZABLE` vẫn có thể làm giao dịch thất bại vì xung đột; ứng dụng phải xử lý và có thể cần retry *toàn bộ giao dịch*.

JDBC còn có `Connection.TRANSACTION_NONE`, nghĩa là **kết nối không hỗ trợ giao dịch**. Đây là giá trị đặc biệt có thể đọc được ở một số môi trường, **không phải mức cô lập để chọn bằng `setTransactionIsolation(...)`**.

## 3. Thiết lập mức cô lập bằng `setTransactionIsolation`

Chọn một hằng số do JDBC định nghĩa:

~~~java
import java.sql.Connection;
import java.sql.SQLException;

public static void configureIsolation(Connection connection)
        throws SQLException {

    connection.setTransactionIsolation(
            Connection.TRANSACTION_REPEATABLE_READ
    );
}
~~~

Bạn cũng có thể chọn:

~~~java
connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
connection.setTransactionIsolation(Connection.TRANSACTION_READ_UNCOMMITTED);
~~~

`setTransactionIsolation(int level)` yêu cầu driver cập nhật mức cô lập của kết nối. Nếu driver/cơ sở dữ liệu không hỗ trợ mức đó, hoặc cấu hình bị từ chối, API có thể ném `SQLException`. Đừng viết code âm thầm giả định lệnh luôn thành công.

**Thời điểm rất quan trọng:** JDBC quy định rằng gọi `setTransactionIsolation(...)` **trong khi giao dịch đang hoạt động** sẽ có kết quả phụ thuộc triển khai. Do đó, hãy đặt mức cô lập **trước khi thực hiện câu SQL đầu tiên của giao dịch**; lý tưởng nhất là ngay sau khi lấy kết nối và trước khi chuyển `autoCommit` sang `false` để bắt đầu một giao dịch tường minh.

~~~text
Lấy Connection
    │
    ├─ Kiểm tra hỗ trợ mức cô lập
    ├─ setTransactionIsolation(level)
    ├─ getTransactionIsolation() để kiểm tra
    ├─ setAutoCommit(false)
    │
    ├─ Thực thi các câu SQL trong giao dịch
    ├─ commit() hoặc rollback()
    │
    └─ Đóng Connection / trả về pool
~~~

Mặc định phần lớn kết nối JDBC mới ở `autoCommit=true`: mỗi câu SQL có thể được xác nhận thành một giao dịch riêng theo quy tắc JDBC và driver. Khi muốn **nhiều câu SQL cùng thuộc một giao dịch**, cần chuyển `autoCommit=false` rồi kết thúc bằng `commit()` hoặc `rollback()`. Chỉ đặt `setTransactionIsolation(...)` mà vẫn dùng nhiều câu SQL ở auto-commit **không tạo ra một giao dịch kéo dài qua tất cả câu SQL đó**.

## 4. Đọc mức cô lập hiện tại với `getTransactionIsolation`

Sau khi yêu cầu thay đổi, hãy đọc lại:

~~~java
int requested = Connection.TRANSACTION_REPEATABLE_READ;

connection.setTransactionIsolation(requested);

int observed = connection.getTransactionIsolation();

if (observed != requested) {
    throw new SQLException(
            "Isolation mismatch: requested=" + requested
            + ", observed=" + observed
    );
}
~~~

`getTransactionIsolation()` trả về một giá trị nguyên tương ứng với hằng số `Connection.TRANSACTION_...`, ví dụ:

| Hằng số | Giá trị nguyên |
| --- | ---: |
| `Connection.TRANSACTION_NONE` | `0` |
| `Connection.TRANSACTION_READ_UNCOMMITTED` | `1` |
| `Connection.TRANSACTION_READ_COMMITTED` | `2` |
| `Connection.TRANSACTION_REPEATABLE_READ` | `4` |
| `Connection.TRANSACTION_SERIALIZABLE` | `8` |

Giá trị số **không phải thứ hạng dùng để tính toán**, và không được giả định driver hỗ trợ tất cả mức nằm giữa. Hãy so sánh bằng **hằng số**, không dùng các “magic number” như `4` rải rác trong mã.

Có thể viết hàm chuyển mã sang tên dễ đọc để log:

~~~java
import java.sql.Connection;

public static String isolationName(int isolation) {
    switch (isolation) {
        case Connection.TRANSACTION_NONE:
            return "NONE";
        case Connection.TRANSACTION_READ_UNCOMMITTED:
            return "READ_UNCOMMITTED";
        case Connection.TRANSACTION_READ_COMMITTED:
            return "READ_COMMITTED";
        case Connection.TRANSACTION_REPEATABLE_READ:
            return "REPEATABLE_READ";
        case Connection.TRANSACTION_SERIALIZABLE:
            return "SERIALIZABLE";
        default:
            return "UNKNOWN(" + isolation + ")";
    }
}
~~~

Khi chẩn đoán, ghi tên mức cô lập và dữ liệu định danh giao dịch phù hợp sẽ hữu ích hơn chỉ ghi một con số.

### “Đang có hiệu lực” có nghĩa gì?

`getTransactionIsolation()` cho biết **mức cô lập mà đối tượng `Connection`/driver báo cáo hiện tại**. Trong đường đi dùng API JDBC tiêu chuẩn, đọc sau khi đặt là cách kiểm tra quan trọng.

Tuy nhiên, giá trị này **không tự chứng minh toàn bộ hành vi thực tế của một giao dịch trên server**. Một số DB có mặc định ở phía máy chủ, alias/ánh xạ các mức cô lập, mức cô lập theo giao dịch, hoặc có lệnh SQL riêng để thay đổi isolation trực tiếp. Nếu dùng lệnh SQL đặc thù như `SET TRANSACTION ...` ngoài API JDBC, chưa chắc `getTransactionIsolation()` đồng bộ với thay đổi đó. Khi cần xác nhận chi tiết trạng thái giao dịch **phía DB**, kiểm tra thêm biến/khung nhìn hệ thống hoặc lệnh introspection *đúng nhà cung cấp*; không có một lệnh SQL kiểm tra mức cô lập phổ quát cho mọi hệ quản trị.

## 5. Kiểm tra khả năng hỗ trợ trước khi thiết lập

JDBC cung cấp `java.sql.DatabaseMetaData` để hỏi khả năng mà driver/DB công bố:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public static void showIsolationSupport(Connection connection)
        throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("Supports transactions: "
            + meta.supportsTransactions());

    System.out.println("Database default: "
            + isolationName(meta.getDefaultTransactionIsolation()));

    int[] levels = {
            Connection.TRANSACTION_READ_UNCOMMITTED,
            Connection.TRANSACTION_READ_COMMITTED,
            Connection.TRANSACTION_REPEATABLE_READ,
            Connection.TRANSACTION_SERIALIZABLE
    };

    for (int level : levels) {
        System.out.println(isolationName(level) + ": "
                + meta.supportsTransactionIsolationLevel(level));
    }

    System.out.println("Connection currently reports: "
            + isolationName(connection.getTransactionIsolation()));
}
~~~

Có ba câu hỏi khác nhau:

- `supportsTransactions()`: hệ quản trị/driver có công bố hỗ trợ giao dịch không?
- `supportsTransactionIsolationLevel(level)`: có công bố hỗ trợ **mức cô lập được yêu cầu** không?
- `getDefaultTransactionIsolation()`: **mức mặc định của cơ sở dữ liệu** theo metadata; khác với `connection.getTransactionIsolation()` là mức của **kết nối đang xét**.

Giá trị mặc định có thể khác mức hiện tại vì code ứng dụng, connection pool hoặc framework đã thay đổi isolation sau khi tạo kết nối. Đừng dùng `getDefaultTransactionIsolation()` thay thế cho kiểm tra mức cô lập thực tế của `Connection` đang dùng.

`supportsTransactionIsolationLevel(level)` giúp phát hiện sớm mức không được hỗ trợ; **kết quả `true` không thay thế bước `setTransactionIsolation()` và đọc lại**. Vì vậy, quy trình hợp lý là **kiểm tra hỗ trợ → yêu cầu đặt → đọc lại → thực thi giao dịch**.

## 6. Ví dụ hoàn chỉnh: giao dịch dùng mức cô lập được yêu cầu

Phương thức bên dưới minh họa dùng **kết nối riêng** do `DriverManager` tạo ra. Nó yêu cầu `REPEATABLE_READ` trước khi bắt đầu giao dịch, xác minh giá trị, đọc số đơn hàng đang chờ rồi `commit()` hoặc `rollback()`:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Properties;

public final class OrderStatistics {

    public static long countPendingOrders(
            String jdbcUrl, Properties credentials, long customerId)
            throws SQLException {

        String sql = """
                SELECT COUNT(*)
                FROM orders
                WHERE customer_id = ? AND status = 'PENDING'
                """;

        int targetLevel = Connection.TRANSACTION_REPEATABLE_READ;

        try (Connection connection =
                     DriverManager.getConnection(jdbcUrl, credentials)) {

            if (!connection.getMetaData()
                    .supportsTransactionIsolationLevel(targetLevel)) {
                throw new SQLFeatureNotSupportedException(
                        "REPEATABLE_READ is not supported");
            }

            // Đặt và đọc lại trước khi bắt đầu giao dịch.
            connection.setTransactionIsolation(targetLevel);

            int actualLevel = connection.getTransactionIsolation();
            if (actualLevel != targetLevel) {
                throw new SQLException(
                        "Unexpected isolation: " + isolationName(actualLevel));
            }

            // Các câu SQL sau đây cùng thuộc một giao dịch tường minh.
            connection.setAutoCommit(false);

            try {
                long count;

                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {

                    statement.setLong(1, customerId);

                    try (ResultSet rows = statement.executeQuery()) {
                        rows.next(); // COUNT(*) trả một hàng khi truy vấn thành công.
                        count = rows.getLong(1);
                    }
                }

                connection.commit();
                return count;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        } // Đóng Connection; không tái sử dụng connection này.
    }

    private static String isolationName(int level) {
        switch (level) {
            case Connection.TRANSACTION_READ_UNCOMMITTED:
                return "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED:
                return "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ:
                return "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE:
                return "SERIALIZABLE";
            case Connection.TRANSACTION_NONE:
                return "NONE";
            default:
                return "UNKNOWN(" + level + ")";
        }
    }
}
~~~

*Ví dụ dùng Java text block (Java 15 trở lên). Có thể thay text block bằng chuỗi SQL thông thường trên Java cũ hơn. Bảng `orders` và các tham số kết nối chỉ dùng để minh họa.*

Những điều cần chú ý:

1. `jdbcUrl` và `credentials` được cung cấp từ cấu hình, không ghi cứng mật khẩu trong nguồn.
2. `setTransactionIsolation(...)` diễn ra **trước** `setAutoCommit(false)` và trước SQL đầu tiên.
3. `getTransactionIsolation()` được dùng để **xác minh giá trị JDBC** sau khi đặt.
4. `PreparedStatement` dùng `?` để truyền dữ liệu, không ghép trực tiếp `customerId` vào SQL.
5. `commit()` hoặc `rollback()` kết thúc giao dịch **trước khi** kết nối đóng; lỗi rollback được giữ trong `getSuppressed()` của ngoại lệ ban đầu.
6. Vì đây là kết nối riêng được mở và đóng trong hàm, ví dụ **không trả lại kết nối này cho pool**. Khi làm việc với pool, cần thêm quy tắc khôi phục cấu hình tại ranh giới trả về pool như mục sau.

**Không hiểu nhầm ví dụ:** Chỉ có một câu `SELECT COUNT(*)` nên `REPEATABLE_READ` chưa thể hiện rõ lợi ích của việc đọc lặp lại; mục đích chính của code là minh họa việc **đặt, xác minh và giữ isolation trong giao dịch**. Để quan sát khác biệt, cần có hai hoặc nhiều giao dịch đồng thời và nhiều lần đọc.

## 7. Điều gì thay đổi khi dùng connection pool?

Trong server, `Connection` thường đến từ `DataSource` có pool (chẳng hạn HikariCP). Khi ứng dụng gọi `connection.close()`, thao tác đó thường **trả kết nối logic về pool**, để request khác có thể mượn. Những thay đổi trên trạng thái kết nối như `autoCommit`, isolation, read-only hoặc schema có thể ảnh hưởng đến lần mượn kế tiếp nếu không được reset đúng.

Một quy trình an toàn cần chú ý:

~~~text
Pool cấp Connection
    │
    ├─ Đọc isolation ban đầu
    ├─ Thiết lập isolation cho thao tác hiện tại
    ├─ Xác minh isolation
    ├─ Bắt đầu giao dịch
    ├─ SQL / commit hoặc rollback
    ├─ Khôi phục isolation ban đầu khi giao dịch đã kết thúc an toàn
    └─ close() để trả Connection về pool
~~~

Nhiều pool hiện đại có cơ chế theo dõi và khôi phục một số trạng thái JDBC khi trả kết nối. Dù vậy, ứng dụng cần hiểu hợp đồng của pool: **không dựa vào việc một lệnh SQL thay đổi session ở phía DB sẽ luôn được pool nhận biết và reset**, nhất là khi lệnh đó bypass các setter JDBC. Nếu pool/framework quản lý isolation theo cấu hình hoặc transaction interceptor, hãy để thành phần đó quản lý thay đổi và phục hồi.

### Ví dụ khôi phục sau một thao tác không bắt đầu giao dịch

Đoạn ngắn dưới đây minh họa trường hợp chỉ muốn đổi isolation trên một connection còn ở trạng thái auto-commit, **không thực thi SQL trong thời gian thay đổi**:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void inspectAtSerializable(DataSource dataSource)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        if (!connection.getAutoCommit()) {
            throw new SQLException(
                    "Expected a Connection without an active transaction");
        }

        int original = connection.getTransactionIsolation();

        try {
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE);

            System.out.println(
                    isolationName(connection.getTransactionIsolation()));
        } finally {
            // Chưa có câu SQL / giao dịch mới trong phạm vi thay đổi.
            connection.setTransactionIsolation(original);
        }
    }
}
~~~

*Trong ví dụ này, `isolationName(...)` là hàm chuyển tên mức cô lập ở mục 4. Kết nối từ pool được lấy để minh họa trạng thái; thực tế không cần nâng isolation chỉ để in tên.*

Nếu thực hiện **giao dịch thật**, hãy tuân thủ thêm các bước: kết thúc bằng `commit()` hoặc `rollback()`; chỉ khôi phục isolation sau khi giao dịch đã kết thúc an toàn; khôi phục `autoCommit` đúng contract nếu chính bạn đã thay đổi; đóng connection trong mọi trường hợp. Nếu rollback thất bại và trạng thái giao dịch không rõ, **không tự chuyển `autoCommit` về `true` một cách mù quáng**, vì chuyển từ `false` sang `true` có thể commit giao dịch đang hoạt động. Cần để cơ chế quản lý pool/transaction loại hoặc xử lý connection không còn tin cậy.

## 8. Isolation và AutoCommit: vì sao dễ nhầm?

Giả sử ứng dụng viết:

~~~java
connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ);

// autoCommit vẫn bằng true.
readStock(connection);
readStock(connection);
~~~

Nếu `autoCommit=true`, hai lần gọi có thể thực thi thành **hai giao dịch độc lập**. Vì thế, lựa chọn isolation không tự bảo đảm hai lần đọc nhìn cùng một snapshot.

Để hai lần đọc cùng nằm trong một giao dịch:

~~~java
connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ);

connection.setAutoCommit(false);
try {
    readStock(connection);
    readStock(connection);
    connection.commit();
} catch (SQLException | RuntimeException error) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        error.addSuppressed(rollbackError);
    }
    throw error;
}
~~~

Trong đoạn ví dụ, `readStock(connection)` là hàm truy vấn do ứng dụng định nghĩa và phải **không tự đóng connection hoặc tự commit/rollback**. Cơ chế MVCC, snapshot, locking và khả năng phát sinh xung đột vẫn do DB quyết định.

**Tránh thay đổi isolation giữa chừng:** Nếu đã bắt đầu giao dịch và thực thi câu SQL, không gọi `setTransactionIsolation(...)` để “nâng mức” rồi mặc nhiên coi mọi câu trước đó đã chịu mức mới. JDBC xem kết quả gọi setter giữa giao dịch là *implementation-defined*. Khi cần một mức mạnh hơn, hãy bắt đầu giao dịch mới từ đầu với isolation tương ứng.

## 9. Isolation của kết nối, mặc định DB và mức theo giao dịch

Trong quá trình debug, ba loại thông tin thường dễ bị đánh đồng:

| Nguồn thông tin | Trả lời câu hỏi gì? | Không bảo đảm điều gì? |
| --- | --- | --- |
| `DatabaseMetaData.getDefaultTransactionIsolation()` | DB/driver báo mức cô lập **mặc định** nào | Không bảo đảm connection hiện tại đang ở mặc định |
| `Connection.getTransactionIsolation()` | Driver báo mức cô lập **hiện tại của Connection** nào | Không chứng minh mọi truy vấn đã chạy trong cùng một transaction |
| Lệnh kiểm tra transaction/session riêng của DB | Phía DB báo cấu hình session/transaction gì | Không có một cú pháp SQL di động qua mọi DB |

Ví dụ, một pool có thể khởi tạo connection và gán `READ_COMMITTED` theo cấu hình, trong khi metadata của DB cho biết mức mặc định khác. Hai giá trị đó không mâu thuẫn: một bên là **default**, bên kia là **trạng thái hiện tại của connection**.

Tương tự, nếu có framework quản lý transaction (ví dụ Spring với khai báo isolation trên transaction), framework có thể thay đổi isolation cho giao dịch rồi khôi phục khi kết thúc. Trong trường hợp đó, code repository nên lấy connection trong ngữ cảnh transaction được quản lý và tránh tự thay isolation giữa chừng, vì có thể làm mất sự nhất quán với transaction manager.

## 10. Chọn mức cô lập theo yêu cầu nghiệp vụ

Không có mức “mạnh nhất luôn tốt nhất” trong mọi tình huống. Mức cô lập cao hơn thường cần cân bằng giữa **tính nhất quán**, **khả năng đồng thời**, chi phí khóa/chụp phiên bản dữ liệu và xác suất phải retry.

| Tình huống | Cân nhắc | Lưu ý |
| --- | --- | --- |
| Báo cáo chỉ đọc thông thường, chấp nhận thay đổi giữa các truy vấn | `READ_COMMITTED` thường là điểm bắt đầu hợp lý | Chọn theo mặc định của DB và tính đúng đắn nghiệp vụ |
| Một giao dịch cần đọc đi đọc lại cùng một dữ liệu | Cân nhắc `REPEATABLE_READ` | Định nghĩa snapshot và phantom tùy DB |
| Nghiệp vụ cần hành vi tương đương thực thi tuần tự | Cân nhắc `SERIALIZABLE` | Xung đột có thể làm transaction thất bại; cần chính sách retry |
| Giảm chi phí đọc và chấp nhận giá trị chưa commit | `READ_UNCOMMITTED` trong hệ DB hỗ trợ | Có thể đọc dữ liệu bị rollback; nhiều DB không hỗ trợ hoặc ánh xạ khác |
| Cần khóa một hàng trước khi cập nhật | Có thể kết hợp isolation với `SELECT ... FOR UPDATE` hay locking phù hợp | Cú pháp/ý nghĩa khóa phụ thuộc DB; isolation một mình chưa thay thế mọi ràng buộc nghiệp vụ |

Ví dụ, chuyển từ `READ_COMMITTED` lên `SERIALIZABLE` có thể làm một số thao tác báo lỗi serialization/transaction conflict thay vì trả kết quả không mong muốn. Khi đó, ứng dụng cần **retry cả đơn vị giao dịch** (sau rollback và lấy trạng thái cần thiết), với giới hạn số lần thử và tránh lặp hiệu ứng ngoài DB không thể rollback, thay vì chỉ lặp lại một câu SQL thất bại.

## 11. Chẩn đoán lỗi đặt mức cô lập

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `setTransactionIsolation(...)` ném `SQLException` | Mức không được hỗ trợ, giao dịch đang hoạt động, driver/DB từ chối | Kiểm tra `supportsTransactionIsolationLevel`, thời điểm gọi, SQLState và thông báo driver |
| Getter không khớp mức yêu cầu | Driver chuyển đổi mức, trạng thái connection bị thay, logic cấu hình khác can thiệp | Đọc lại sau setter, ghi tên mức, kiểm tra pool/framework và trạng thái DB |
| Dùng `getDefaultTransactionIsolation()` thấy khác getter | Connection đã được cấu hình khác mặc định | Phân biệt default của DB với hiện tại của connection |
| Đọc hai lần vẫn khác dù đặt `REPEATABLE_READ` | Hai câu SQL không cùng transaction; DB có semantics riêng; transaction bị commit ở giữa | Kiểm tra `autoCommit`, transaction boundary, driver/DB |
| Request sau nhận mức cô lập ngoài dự kiến | Connection pool hoặc code trước chưa reset trạng thái | Theo dõi lifecycle của connection, cấu hình pool và transaction manager |
| `SERIALIZABLE` gây lỗi xung đột khi tải cao | DB phát hiện transaction không thể đồng thời commit hợp lệ | Rollback rồi retry đơn vị giao dịch có giới hạn |
| Thay isolation bằng SQL riêng không hiện trong getter | Driver không đồng bộ trạng thái SQL server-side vào trạng thái JDBC | Dùng một cơ chế thống nhất; kiểm tra session/transaction ở DB nếu cần |

Bắt lỗi nên giữ nguyên nguyên nhân và thông tin chẩn đoán:

~~~java
try {
    connection.setTransactionIsolation(
            Connection.TRANSACTION_SERIALIZABLE);
} catch (SQLException error) {
    System.err.println("SQLState: " + error.getSQLState());
    System.err.println("Vendor code: " + error.getErrorCode());
    System.err.println("Reason: " + error.getMessage());
    throw error;
}
~~~

Không phải DB nào cũng báo lỗi serialization bằng cùng một loại exception; SQLState và vendor code cần được diễn giải theo tài liệu DB/driver. Đừng ghi mật khẩu hoặc toàn bộ URL kết nối khi thu thập log.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `Connection.getTransactionIsolation()` và `DatabaseMetaData.getDefaultTransactionIsolation()` có nhất thiết bằng nhau?

Không. Một phương thức đọc mức cô lập **hiện tại của kết nối**, phương thức kia cho biết **mức mặc định do DB/driver công bố**. Pool hoặc ứng dụng có thể đã thay đổi mức trên kết nối.

**Câu 2.** Nên gọi `setTransactionIsolation(...)` khi transaction đã có vài câu SQL chưa commit hay trước khi bắt đầu?

Nên gọi **trước giao dịch**. JDBC xác định kết quả gọi setter trong một giao dịch đang hoạt động là phụ thuộc cách triển khai, nên không được coi là thao tác nâng/hạ mức cô lập an toàn giữa chừng.

**Câu 3.** `supportsTransactionIsolationLevel(SERIALIZABLE)` trả về `true`. Có thể bỏ qua `setTransactionIsolation(...)` và `getTransactionIsolation()`?

Không. Kết quả `true` chỉ cho biết driver/DB **công bố hỗ trợ**. Bạn vẫn cần yêu cầu đặt mức trên đúng connection, rồi xác minh giá trị JDBC hiện báo cáo.

**Câu 4.** Hai lần SELECT trong `autoCommit=true`, dù đặt `REPEATABLE_READ`, có nhất thiết thấy cùng dữ liệu không?

Không. Chúng có thể thuộc hai giao dịch khác nhau. Muốn dùng tính nhất quán trong một giao dịch nhiều câu SQL, hãy đặt `autoCommit=false` và quản lý `commit()/rollback()` phù hợp.

**Câu 5.** Vì sao phải cẩn trọng khi dùng isolation trên connection pool?

Vì connection có thể được trả cho request khác. Cần bảo đảm isolation, `autoCommit` và trạng thái transaction được khôi phục/đóng đúng cách theo contract của pool hoặc framework.

**Câu 6.** `TRANSACTION_NONE` có phải là lựa chọn “nhẹ hơn” `READ_UNCOMMITTED` để tăng hiệu năng?

Không. `TRANSACTION_NONE` biểu thị **không hỗ trợ giao dịch**, không phải một mức cô lập để chọn khi bắt đầu transaction.

**Điểm cần nhớ:** Trong JDBC, hãy **kiểm tra hỗ trợ bằng `DatabaseMetaData` → gọi `Connection.setTransactionIsolation(level)` trước giao dịch → đọc `Connection.getTransactionIsolation()` → chạy SQL trong cùng transaction → `commit`/`rollback` rõ ràng**. Phân biệt giá trị JDBC driver báo cáo với hành vi thực tế phía DB, và luôn quản lý việc khôi phục trạng thái khi kết nối được pool tái sử dụng.
