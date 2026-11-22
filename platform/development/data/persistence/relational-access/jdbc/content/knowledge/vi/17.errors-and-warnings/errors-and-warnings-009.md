# Giữ ngữ cảnh SQL và loại tham số mà không ghi bí mật

## 1. Bài toán: cần đủ thông tin để sửa lỗi, nhưng không làm lộ dữ liệu

Trong ứng dụng Java dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ, một thao tác thường trải qua `DataSource`, `Connection`, `PreparedStatement`, cơ sở dữ liệu và đôi khi `ResultSet`. Khi câu lệnh thất bại, đội vận hành cần xác định **thao tác nào lỗi, hình dạng tham số nào được truyền, lỗi thuộc nhóm nào và xảy ra trong ngữ cảnh giao dịch nào**.

Ví dụ, một yêu cầu cập nhật trạng thái đơn hàng thất bại do ràng buộc dữ liệu. Nếu chỉ ghi “Database error”, người kiểm tra khó xác định cần tìm ở đâu. Ngược lại, nếu ghi toàn bộ câu SQL đã gắn giá trị và mọi thông điệp từ driver, nhật ký có thể chứa tên, email, số tài khoản, token hoặc dữ liệu nội bộ.

Mục tiêu là giữ **ngữ cảnh kỹ thuật có ích** mà không biến log thành một bản sao dữ liệu nhạy cảm:

- Mã thao tác cố định như `orders.update-status.v1`, dùng để tra ra mẫu SQL trong mã nguồn.
- Hình dạng câu lệnh: `UPDATE` một hàng, dự kiến ảnh hưởng tối đa một hàng, số tham số và **kiểu JDBC theo vị trí**.
- Thông tin lỗi có cấu trúc: `SQLState`, vendor error code, lớp ngoại lệ, vị trí lỗi trong chuỗi `SQLException`.
- Thời gian chạy, kết quả cập nhật, ID tương quan do ứng dụng tạo và giai đoạn transaction, nếu các trường đó được phép ghi.
- Thông tin cảnh báo từ `SQLWarning`, nhưng vẫn áp dụng cùng nguyên tắc loại bỏ bí mật.

**Không ghi mặc định**: giá trị bind vào `PreparedStatement`, SQL có giá trị cụ thể, nội dung `ResultSet`, mật khẩu kết nối, chuỗi kết nối chứa thông tin xác thực, toàn bộ thông điệp lỗi hoặc stack trace chưa được kiểm soát.

Sau bài này, bạn sẽ viết được mã JDBC tham số hóa và hàm ghi log an toàn, diễn giải `SQLException`/`SQLWarning`, giữ ngữ cảnh theo mã câu lệnh và loại tham số, xử lý lỗi batch và đánh giá các đường có thể rò rỉ dữ liệu.

## 2. Những thông tin nào cần giữ lại?

Xét thao tác:

```sql
UPDATE orders
SET status = ?
WHERE id = ?
  AND tenant_id = ?
  AND status = 'PENDING';
```

Các dấu `?` được gắn giá trị ở JDBC, ví dụ: vị trí 1 là trạng thái mới, vị trí 2 là ID đơn, vị trí 3 là ID tenant. Log an toàn **không cần biết** các giá trị thực tế; nó cần biết API đã cố thực thi thao tác nào và đã dùng những loại tham số nào.

| Trường | Ví dụ minh họa | Có nên ghi? |
|---|---|---|
| Mã thao tác | `orders.update-status.v1` | Có, nếu mã do lập trình viên định nghĩa, không lấy tùy ý từ người dùng. |
| Loại thao tác | `UPDATE` | Có. |
| Kiểu tham số theo vị trí | `p1:VARCHAR, p2:BIGINT, p3:BIGINT` | Có, lấy từ hợp đồng bind tham số. |
| Số tham số | `3` | Thường có ích; xác nhận không vô tình ghi giá trị. |
| Số dòng bị ảnh hưởng | `0` hoặc `1` | Thường có ích; giải thích theo nghiệp vụ. |
| `SQLState` | `23505` (ví dụ mã lỗi unique violation trong PostgreSQL) | Có, sau khi chuẩn hóa và kiểm tra định dạng. |
| Vendor error code | `getErrorCode()` | Có, dùng cùng thông tin driver/DB để giải nghĩa. |
| Thời gian chạy | `durationMs=18` | Có, nếu không tiết lộ dữ liệu hạn chế khác. |
| Mã tương quan | ID request ngẫu nhiên do hệ thống sinh | Có, theo chính sách lưu giữ và phân quyền log. |
| Giá trị tham số | Email, token, ID người dùng, nội dung ghi chú | Không ghi mặc định. |
| SQL đã nội suy giá trị | `... WHERE email = '...'` | Không ghi. |
| `SQLException.getMessage()` nguyên văn | Có thể chứa SQL, tên cột, dữ liệu lỗi hoặc thông tin hệ thống | Không ghi vào luồng log chung khi chưa kiểm duyệt. |
| Chuỗi kết nối | URL JDBC có thể chứa credential hoặc thông tin hạ tầng | Không ghi nguyên văn. |

Ví dụ dòng chẩn đoán đã giới hạn trường:

```text
jdbc.error op=orders.update-status.v1 kind=UPDATE
  params=[p1:VARCHAR,p2:BIGINT,p3:BIGINT] elapsedMs=18
  sqlState=23505 vendorCode=0 exceptionType=SQLException
```

Đây là **minh họa định dạng**, không phải kết quả của cơ sở dữ liệu đang chạy. Mã `23505` gắn với PostgreSQL; hệ quản trị khác có thể dùng SQLState hoặc vendor code khác. Log này không chứa giá trị ID, trạng thái, SQL đã điền tham số hay nội dung lỗi gốc.

**Phân biệt hai khái niệm:** “loại tham số” là kiểu SQL/JDBC như `VARCHAR`, `BIGINT`, `DECIMAL`, `TIMESTAMP` hoặc `BOOLEAN`; “giá trị tham số” là nội dung cụ thể do chương trình truyền. Giữ **kiểu và vị trí** thường đủ để phát hiện sai kiểu bind mà không phải lưu thông tin nghiệp vụ.

## 3. Dùng mã định danh thao tác thay cho SQL nguyên văn

Trong mã nguồn, đặt một mã ổn định cho mỗi mẫu SQL quan trọng:

```java
private static final String OPERATION = "orders.update-status.v1";
private static final String SQL = """
        UPDATE orders
        SET status = ?
        WHERE id = ?
          AND tenant_id = ?
          AND status = 'PENDING'
        """;
```

Người điều tra có thể tìm `OPERATION` trong repository để đọc mẫu SQL, kiểm tra vị trí bind và đối chiếu thay đổi theo phiên bản mã. Điều này cho phép log chỉ ghi `orders.update-status.v1`, thay vì copy SQL vào log.

Một mã tốt có đặc điểm: cố định ở mã nguồn, duy nhất trong phạm vi ứng dụng, mô tả hành động và có thể tăng phiên bản khi mẫu SQL thay đổi đáng kể. Tránh dùng chuỗi do người dùng nhập, tên bảng lấy động không kiểm soát, hoặc giá trị trường dữ liệu làm `operationId`.

**Ngay cả SQL mẫu có dấu `?` vẫn chưa chắc an toàn để log.** Mẫu SQL có thể chứa literal, comment, tên tài nguyên nội bộ hay SQL xây dựng động. Nếu cần ghi mẫu SQL để gỡ lỗi ở môi trường giới hạn, phải đánh giá và loại bỏ các phần nhạy cảm trước, dùng cơ chế được cấp quyền riêng. Phương án mặc định là chỉ ghi **mã truy vấn** và thông tin kỹ thuật đã chọn.

```text
operationId="orders.update-status.v1"
SQL template: tra trong mã nguồn hoặc hệ thống quản lý phiên bản
Log: chỉ lưu operationId + metadata được phép
```

## 4. Giữ **loại tham số** ngay tại chỗ bind

`PreparedStatement` giúp truyền giá trị bằng các setter có kiểu:

```java
ps.setString(1, newStatus);  // p1: VARCHAR
ps.setLong(2, orderId);     // p2: BIGINT
ps.setLong(3, tenantId);    // p3: BIGINT
```

Ứng dụng nên mô tả metadata theo đúng hợp đồng SQL:

```java
import java.sql.JDBCType;
import java.util.List;

private static final List<JDBCType> PARAMETER_TYPES = List.of(
        JDBCType.VARCHAR,
        JDBCType.BIGINT,
        JDBCType.BIGINT
);
```

Với cấu trúc này, log được `p1:VARCHAR, p2:BIGINT, p3:BIGINT` mà không phải giữ lại các đối tượng chứa giá trị bind. Nếu đổi câu SQL hoặc thứ tự setter, phải sửa metadata tương ứng. Có thể thiết kế một lớp binding để gắn kiểu và giá trị ở một vị trí chung; ví dụ đơn giản ở đây dùng danh sách tĩnh để dễ theo dõi.

### Tại sao không dựa hoàn toàn vào `ParameterMetaData`?

JDBC có `PreparedStatement.getParameterMetaData()` với các phương thức như `getParameterCount()` và `getParameterType(int)`. Tuy nhiên, khả năng trả metadata có thể khác nhau theo driver và câu SQL, thậm chí ném `SQLFeatureNotSupportedException`. Một số trường hợp driver không xác định được kiểu chính xác trước khi thực thi.

Vì vậy, khi mục tiêu là tạo log đáng tin cậy, **kiểu dự kiến do ứng dụng khai báo cạnh chỗ bind** thường rõ ràng hơn. `ParameterMetaData` có thể bổ sung kiểm tra trong môi trường driver hỗ trợ, nhưng không nên là nguồn duy nhất để xây dựng toàn bộ chẩn đoán.

### Tham số `NULL` và các kiểu đặc biệt

Đối với cột nullable, truyền null theo kiểu JDBC phù hợp:

```java
import java.sql.Types;

if (approvedAt == null) {
    ps.setNull(4, Types.TIMESTAMP);
} else {
    ps.setTimestamp(4, approvedAt);
}
```

Metadata lúc ghi lỗi vẫn có thể là `p4:TIMESTAMP`. **Không cần ghi tham số có null hay không** nếu thông tin đó có thể tiết lộ một trạng thái riêng tư. Với `DECIMAL`, `BLOB`, `CLOB` hoặc dữ liệu JSON, log tên kiểu đã quy ước, không đọc hoặc chuyển nội dung thành chuỗi để “phục vụ debug”.

Nếu sử dụng `setObject(index, value)`, phải xác định kiểu SQL kỳ vọng theo hợp đồng truy vấn (hoặc dùng biến thể `setObject` có `SQLType` khi phù hợp). `value.getClass().getSimpleName()` chỉ cho biết kiểu Java của đối tượng và có thể không phản ánh chính xác kiểu cột SQL. Khi `value` là null, gọi `getClass()` còn gây lỗi.

## 5. Đọc ngữ cảnh lỗi có cấu trúc từ `SQLException`

JDBC cung cấp nhiều tín hiệu hữu ích mà không cần log toàn bộ exception:

```java
import java.sql.SQLException;

String sqlState = error.getSQLState();
int vendorCode = error.getErrorCode();
String exceptionType = error.getClass().getSimpleName();
SQLException next = error.getNextException();
```

- `getSQLState()` trả mã trạng thái lỗi SQL theo quy ước mà driver cung cấp, thường gồm năm ký tự; giá trị có thể là `null` nếu driver không cung cấp.
- `getErrorCode()` trả mã lỗi riêng của hệ quản trị/driver; có thể bằng `0` khi không có mã cụ thể. Không diễn giải code mà thiếu ngữ cảnh DB.
- `getClass().getSimpleName()` có thể cho biết lớp lỗi JDBC như `SQLIntegrityConstraintViolationException`, `SQLTimeoutException`, `SQLTransactionRollbackException`; loại cụ thể phụ thuộc driver.
- `getNextException()` liên kết nhiều `SQLException`, chẳng hạn khi driver cung cấp thêm lỗi máy chủ hoặc khi chạy batch. Không bỏ qua chuỗi này trong quá trình phân tích.
- `getCause()` trả nguyên nhân theo cơ chế `Throwable`, đôi khi hữu ích cho chẩn đoán nội bộ. Tuy nhiên, message và stack trace của nguyên nhân cũng có thể chứa thông tin nhạy cảm.

Một số lớp mã `SQLState` thường gặp:

| Hai ký tự đầu của SQLState | Nhóm lỗi thường liên quan | Hành động xem xét |
|---|---|---|
| `08` | Lỗi kết nối | Xác định trạng thái kết nối và transaction; cân nhắc khả năng kết quả commit không rõ. |
| `22` | Lỗi giá trị dữ liệu / chuyển đổi | Kiểm tra hợp đồng kiểu dữ liệu, validation và SQL. |
| `23` | Vi phạm ràng buộc toàn vẹn | Kiểm tra khóa ngoại, unique, not-null; không log giá trị vi phạm. |
| `40` | Transaction rollback / xung đột đồng thời | Phân tích deadlock, serialization và chính sách retry transaction. |
| `42` | Lỗi cú pháp hoặc quyền truy cập theo hệ quản trị | Kiểm tra phiên bản schema, SQL và quyền được cấp. |

Bảng là định hướng chung; SQLState thực tế và diễn giải từng mã cụ thể tùy DB/driver. Chẳng hạn `40001` thường biểu thị lỗi serialization, nhưng chiến lược retry phải phụ thuộc ngữ cảnh nghiệp vụ và khả năng lặp an toàn.

**Không ghi `error.getMessage()`, `error.toString()`, `printStackTrace()` hoặc truyền thẳng `Throwable` vào logger trong log chia sẻ** nếu chưa có cơ chế che dữ liệu phù hợp. Thông điệp lỗi cơ sở dữ liệu có thể chèn vào chính giá trị bị từ chối, SQL nguyên văn, đường dẫn hoặc thông tin máy chủ.

## 6. Triển khai logger an toàn bằng API Java chuẩn

Ví dụ sau cố ý dùng `java.util.logging.Logger` để minh họa mà không cần thư viện logging bên ngoài. Nó chỉ ghi các trường đã duyệt trước: mã thao tác, nhóm lệnh, loại tham số, thời gian, `SQLState`, vendor code và tên lớp ngoại lệ.

```java
import java.sql.JDBCType;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class SafeJdbcLog {
    private static final Logger LOG =
            Logger.getLogger(SafeJdbcLog.class.getName());
    private static final int MAX_CHAIN_ENTRIES = 5;

    private SafeJdbcLog() {}

    public static void logFailure(
            String operationId,
            String statementKind,
            List<JDBCType> parameterTypes,
            SQLException error,
            long elapsedNanos) {

        // Chỉ truyền operationId/statementKind từ hằng số do ứng dụng quản lý.
        String types = describeTypes(parameterTypes);
        long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                Math.max(0L, elapsedNanos));

        SQLException current = error;
        int chainIndex = 0;
        while (current != null && chainIndex < MAX_CHAIN_ENTRIES) {
            String state = safeSqlState(current.getSQLState());
            String exceptionType =
                    current.getClass().getSimpleName();

            LOG.log(Level.WARNING,
                    "jdbc.failure op={0} kind={1} params={2} " +
                    "elapsedMs={3} chainIndex={4} sqlState={5} " +
                    "vendorCode={6} exceptionType={7}",
                    new Object[]{
                            operationId,
                            statementKind,
                            types,
                            elapsedMs,
                            chainIndex,
                            state,
                            current.getErrorCode(),
                            exceptionType
                    });

            current = current.getNextException();
            chainIndex++;
        }
    }

    private static String describeTypes(List<JDBCType> types) {
        List<String> parts = new ArrayList<>();
        for (int index = 0; index < types.size(); index++) {
            parts.add("p" + (index + 1) + ":" + types.get(index).getName());
        }
        return "[" + String.join(",", parts) + "]";
    }

    private static String safeSqlState(String state) {
        if (state == null || !state.matches("[A-Z0-9]{5}")) {
            return "UNAVAILABLE";
        }
        return state;
    }
}
```

Đặc điểm cần giữ của hàm này:

1. **Không nhận danh sách giá trị bind** nên không có gì để vô tình in ra từ các tham số nghiệp vụ.
2. Kiểu tham số được lấy từ enum `JDBCType` do code định nghĩa; không dựa trên `toString()` của đối tượng chứa dữ liệu.
3. `SQLState` được kiểm tra định dạng và giới hạn độ dài; nếu không có giá trị hợp lệ, log ghi `UNAVAILABLE`.
4. Chuỗi `getNextException()` được đọc tối đa năm phần tử để tránh log quá lớn hoặc trường hợp bất thường; mã vendor và vị trí trong chuỗi hỗ trợ điều tra.
5. Không ghi `getMessage()`, `getCause()`, nguyên SQL hay chính đối tượng `SQLException`. Các ngoại lệ vẫn được giữ để mã tầng trên xử lý theo giao thức của ứng dụng.
6. `operationId` và `statementKind` **phải là chuỗi cố định đã được xem xét**; nếu nhận dữ liệu tùy ý từ HTTP hoặc database, cần cơ chế giới hạn/chuẩn hóa tương ứng.

Logger trong ứng dụng thật có thể là SLF4J, Log4j hoặc nền tảng observability. Dù thư viện nào, nguyên tắc vẫn là khai báo **trường được phép ghi**, truyền giá trị có cấu trúc và tránh cơ chế tự động ghi toàn bộ đối tượng lỗi, request hoặc tham số.

## 7. Gắn logging vào một repository JDBC

Xét ví dụ cập nhật đơn hàng theo `tenant_id` và trạng thái `PENDING`:

```java
import java.sql.Connection;
import java.sql.JDBCType;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderRepository {
    private static final String OPERATION = "orders.update-status.v1";
    private static final String STATEMENT_KIND = "UPDATE";
    private static final List<JDBCType> PARAMETER_TYPES =
            List.of(JDBCType.VARCHAR, JDBCType.BIGINT, JDBCType.BIGINT);

    private static final String UPDATE_SQL = """
            UPDATE orders
            SET status = ?
            WHERE id = ?
              AND tenant_id = ?
              AND status = 'PENDING'
            """;

    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public boolean updateStatusIfPending(
            long orderId, long tenantId, String newStatus)
            throws SQLException {

        long startedAt = System.nanoTime();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(UPDATE_SQL)) {

            ps.setString(1, newStatus);
            ps.setLong(2, orderId);
            ps.setLong(3, tenantId);

            int affectedRows = ps.executeUpdate();
            if (affectedRows > 1) {
                // Với khóa chính id, đây là kết quả bất thường.
                throw new SQLException("Unexpected update count", "HY000");
            }

            // Không log newStatus, orderId hay tenantId.
            return affectedRows == 1;
        } catch (SQLException error) {
            SafeJdbcLog.logFailure(
                    OPERATION,
                    STATEMENT_KIND,
                    PARAMETER_TYPES,
                    error,
                    System.nanoTime() - startedAt);
            throw error;
        }
    }
}
```

Ứng dụng gọi `updateStatusIfPending(...)` sẽ nhận:

- `true` nếu SQL báo cập nhật một hàng;
- `false` nếu không có hàng thỏa cả `id`, `tenant_id` và trạng thái `PENDING`;
- `SQLException` nếu truy cập database thất bại hoặc kết quả bất thường.

**Không coi `affectedRows == 0` là lỗi SQL cần log cảnh báo** trong mọi trường hợp: nó có thể là tình huống nghiệp vụ bình thường, ví dụ trạng thái đã thay đổi. Khi cần quan sát kết quả từ chối, ghi một sự kiện nghiệp vụ riêng với mã kết quả đã chuẩn hóa, không thêm giá trị tham số.

Phương thức trên minh họa **một câu lệnh độc lập**, giả định connection được cấp trong chế độ auto-commit thích hợp. Nếu dùng transaction bao nhiều bước, kết quả `executeUpdate()` chưa chứng minh toàn bộ nghiệp vụ đã commit; transaction owner phải xử lý commit/rollback và ghi nhận trạng thái cuối cùng.

`throw error` giữ exception để tầng gọi quyết định xử lý transaction, đổi thành kết quả API hoặc phân loại retry. Tuy nhiên, các tầng đó cũng không nên tự động log nguyên exception qua middleware/handler chia sẻ nếu mục tiêu là tránh rò rỉ thông tin. Cần áp dụng chính sách logging an toàn xuyên suốt.

## 8. `SQLWarning`: giữ chẩn đoán mà không hiểu nhầm là lỗi

Ngoài `SQLException`, JDBC còn có `SQLWarning` để biểu diễn tình huống cảnh báo từ kết nối, statement hoặc result set. Tùy driver, cảnh báo có thể liên quan đến dữ liệu bị cắt, hành vi chuyển đổi hoặc các vấn đề không làm câu lệnh thất bại ngay.

Các API liên quan:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLWarning;

// Đọc cảnh báo của statement sau khi thực thi:
SQLWarning warning = statement.getWarnings();

// Đọc cảnh báo thuộc connection:
SQLWarning connectionWarning = connection.getWarnings();

// Khi thích hợp, xóa các cảnh báo đã được xử lý:
statement.clearWarnings();
connection.clearWarnings();
```

`SQLWarning` kế thừa `SQLException`, nên có `getSQLState()`, `getErrorCode()` và có thể có chuỗi cảnh báo qua `getNextWarning()`. Khi ghi log, áp dụng cùng danh sách trường cho phép: **mã thao tác, nơi phát cảnh báo, SQLState, vendor code và lớp cảnh báo**, không ghi nguyên message. Nên giới hạn số phần tử của chuỗi cảnh báo để tránh sự kiện log quá lớn.

Ví dụ helper ghi từng cảnh báo một cách giới hạn:

```java
import java.sql.SQLWarning;
import java.util.logging.Level;
import java.util.logging.Logger;

final class SafeWarningLog {
    private static final Logger LOG =
            Logger.getLogger(SafeWarningLog.class.getName());

    private SafeWarningLog() {}

    static void logWarnings(
            String operationId, String location, SQLWarning first) {
        int index = 0;
        for (SQLWarning current = first;
             current != null && index < 5;
             current = current.getNextWarning(), index++) {
            String state = current.getSQLState();
            String safeState = state != null && state.matches("[A-Z0-9]{5}")
                    ? state : "UNAVAILABLE";
            LOG.log(Level.WARNING,
                    "jdbc.warning op={0} source={1} index={2} " +
                    "sqlState={3} vendorCode={4} warningType={5}",
                    new Object[]{
                            operationId,
                            location,
                            index,
                            safeState,
                            current.getErrorCode(),
                            current.getClass().getSimpleName()
                    });
        }
    }
}
```

`location` cũng phải là một giá trị cố định như `statement` hoặc `connection`. Theo JDBC, cảnh báo có thể được xóa hoặc thay đổi khi thực thi lệnh tiếp theo; hãy đọc chúng vào thời điểm phù hợp. Không giả định mọi driver tạo warnings cho mọi tình huống dữ liệu bất thường.

**Cảnh báo khác ngoại lệ:** SQL warning không tự đồng nghĩa với rollback. Ứng dụng cần xem ý nghĩa warning theo DB và nghiệp vụ để quyết định có thể tiếp tục, trả kết quả hay coi nó là điều kiện phải dừng.

## 9. Transaction, batch và các tín hiệu nên đưa vào ngữ cảnh

### 9.1. Giai đoạn transaction

Với nghiệp vụ gồm nhiều câu SQL, cùng một ngoại lệ có ý nghĩa khác nhau tùy thời điểm:

```text
operation=orders.place.v2 stage=reserve-stock   result=FAILED
operation=orders.place.v2 stage=insert-order    result=NOT_EXECUTED
operation=orders.place.v2 stage=rollback        result=SUCCEEDED
```

Ở đây `stage` và `result` là các giá trị từ tập hằng cố định. Chúng giúp xác định transaction đã rollback hay chưa mà không cần ghi số lượng mua, ID, hoặc giá trị tham số SQL.

Lưu ý:

- Một lệnh `executeUpdate()` báo `1` chỉ có nghĩa SQL đã tác động một hàng tại thời điểm đó; transaction vẫn có thể rollback.
- Nếu `commit()` thất bại do mất kết nối, có trường hợp không thể biết chắc DB đã commit hay chưa. Log trạng thái **UNKNOWN** và dùng cơ chế đối soát phù hợp; không tự suy “đã rollback”.
- Đừng ghi nguyên `Connection`, `DataSource`, JDBC URL hay đối tượng transaction vào log; `toString()` của chúng có thể làm lộ chi tiết kết nối.
- Nếu ghi request ID, nên dùng mã được hệ thống tạo với định dạng và độ dài kiểm soát; không dùng cookie, session token hay access token làm correlation ID.

### 9.2. `BatchUpdateException` và số lệnh đã thực thi

Với `PreparedStatement.addBatch()` và `executeBatch()`, khi có lỗi JDBC có thể ném `BatchUpdateException`. Ngoài `SQLState` và vendor code, nó chứa `getUpdateCounts()` cho biết kết quả những lệnh driver báo đã xử lý.

```java
import java.sql.BatchUpdateException;
import java.sql.Statement;

try {
    statement.executeBatch();
} catch (BatchUpdateException error) {
    int[] counts = error.getUpdateCounts();
    int reported = counts.length;
    int failed = 0;
    int successWithoutCount = 0;

    for (int count : counts) {
        if (count == Statement.EXECUTE_FAILED) {
            failed++;
        } else if (count == Statement.SUCCESS_NO_INFO) {
            successWithoutCount++;
        }
    }

    // Các số đếm tổng hợp được duyệt chính sách mới được đưa vào log;
    // không ghi nội dung từng batch hoặc các giá trị đã bind.
    // reported, failed, successWithoutCount
    throw error;
}
```

Driver có thể dừng ở câu lệnh bị lỗi hoặc tiếp tục thực thi các câu khác trong batch. Vì vậy, `reported` không nhất thiết là tổng số câu lệnh đã thêm bằng `addBatch()`, và không thể tự suy ra bao nhiêu thao tác thực sự được commit chỉ từ các count. Trong transaction cần tất cả cùng thành công, hãy rollback khi một lệnh không đạt yêu cầu.

Nếu đơn vị xử lý cần log thống kê batch, nên ghi số lượng tổng hợp như `batchSize` và `reportedCounts` theo chính sách; không ghi danh sách giá trị từng bản ghi hoặc các exception message có dữ liệu lỗi.

## 10. Không chỉ code ứng dụng: nơi khác cũng có thể ghi bí mật

Ngay cả khi repository chỉ log metadata, dữ liệu vẫn có thể xuất hiện trong:

- Driver JDBC hoặc connection pool khi bật chế độ debug/trace có log SQL và giá trị bind.
- Công cụ quan sát hiệu năng (APM), tracing, SQL profiler hoặc proxy database khi tự thu thập query parameters.
- Log của DB server khi bật các tùy chọn ghi statement, tham số hoặc giá trị gây lỗi.
- Middleware HTTP tự ghi body request, query string, header ủy quyền hoặc exception có message.
- Ứng dụng vô tình log đối tượng domain, DTO, `ResultSet` hoặc thông tin `DataSource` bằng `toString()`.
- Nội dung exception được trả trực tiếp ra API, email hỗ trợ hoặc hệ thống ticket.

Vì vậy, **không ghi bí mật** phải được áp dụng theo đường đi của dữ liệu: cấu hình JDBC/driver, mã repository, xử lý exception ở tầng dịch vụ, logger, nền tảng thu thập log và quyền truy cập nhật ký. Một hàm logger an toàn không thể kiểm soát cơ chế ghi tự động của hệ thống khác.

Các biện pháp thực tế:

1. Mặc định tắt tính năng ghi bind values và SQL đầy đủ trên môi trường chứa dữ liệu thật; rà soát cấu hình khi bật debug.
2. Chỉ cho phép trường metadata đã định nghĩa; không serialize nguyên các đối tượng chứa dữ liệu nghiệp vụ hoặc exception vào hệ thống log chung.
3. Hạn chế người được đọc log, thời gian lưu và nơi chuyển tiếp log; thực hiện kiểm toán truy cập.
4. Kiểm thử bằng dữ liệu giả có chuỗi đánh dấu bí mật để chắc chắn không có chuỗi đó trong log ứng dụng, APM và output API.
5. Nếu bắt buộc lưu dữ liệu đặc biệt để điều tra, dùng luồng được phê duyệt và có kiểm soát bảo mật riêng, không tự thêm log giá trị tham số trong code thông thường.

### Vì sao thay giá trị bằng dấu `***` chưa đủ?

Lọc bằng regex sau khi log đã chứa đầy đủ dữ liệu thường không đáng tin cậy: email, token, dữ liệu nhị phân và format SQL có thể xuất hiện theo nhiều dạng; thông tin có thể đã bị chuyển tiếp trước khi bộ lọc chạy. Tốt hơn là **thiết kế dữ liệu chẩn đoán từ đầu chỉ gồm trường an toàn**, vì khi đó không có giá trị bí mật được truyền vào hàm logging.

Không dùng hash của giá trị nhạy cảm làm mặc định để “vừa giấu vừa tra cứu”: với dữ liệu có không gian giá trị nhỏ, hash có thể bị đoán bằng từ điển; ngay cả hash ổn định cũng có thể dùng để theo dõi người dùng qua nhiều yêu cầu. Khi cần định danh tương quan, dùng ID ngẫu nhiên do hệ thống tạo cho mỗi yêu cầu.

## 11. Phân loại lỗi mà không làm mất ngữ cảnh

Đội phát triển cần giữ đủ thông tin để xử lý, dù log đã loại bỏ bí mật. Có thể chia thành:

| Ngữ cảnh cần thiết | Cách lưu hoặc xử lý |
|---|---|
| SQL nào bị lỗi? | Ghi `operationId`; mẫu SQL nằm trong mã nguồn. |
| Bind có đúng kiểu không? | Ghi thứ tự và `JDBCType` từ hợp đồng câu lệnh. |
| Lỗi thuộc nhóm nào? | Ghi SQLState, vendor code và lớp `SQLException`. |
| Lỗi nằm trong batch hay transaction? | Ghi stage, trạng thái transaction và count tổng hợp theo chính sách. |
| Lỗi có lặp lại không? | Dùng request/correlation ID do hệ thống cấp, thời gian, số lần thử có giới hạn. |
| Có nên retry? | Quyết định dựa trên loại lỗi, trạng thái transaction, idempotency và nghiệp vụ; không chỉ dựa vào message. |
| Có cần biết giá trị gây lỗi? | Tái hiện trên dữ liệu thử nghiệm hoặc dùng quy trình điều tra có kiểm soát; không mở log giá trị hàng loạt. |

Đối với lỗi dữ liệu, kiểu tham số chỉ giúp phát hiện **một phần** nguyên nhân. Ví dụ, log `p1:VARCHAR` không cho biết một chuỗi quá dài hay sai định dạng. Đây là giới hạn được chấp nhận của luồng log mặc định; muốn tìm chính xác một giá trị gây lỗi, nên tái hiện bằng dữ liệu thử nghiệm và công cụ truy cập DB được cấp quyền.

Không nên nuốt mọi `SQLException` rồi trả thành công vì đã ghi log. Xử lý lỗi và chẩn đoán là hai trách nhiệm khác nhau: repository có thể ném lại exception để tầng điều phối rollback hoặc trả thông điệp phù hợp, còn logger chỉ ghi những trường được phép.

## 12. Kiểm tra triển khai bằng những tình huống cụ thể

Tại môi trường thử nghiệm, dùng dữ liệu giả và một chuỗi đánh dấu chẳng hạn `TEST_SECRET_MARKER_7F3` trong tham số `VARCHAR`. Chuỗi này đóng vai trò kiểm tra rò rỉ; **không sử dụng bí mật thật**.

1. **Lệnh thành công:** cập nhật đơn bằng `PreparedStatement`; xác nhận kết quả `executeUpdate()` được xử lý theo nghiệp vụ, log không chứa giá trị bind.
2. **Lệnh trả 0 hàng:** gọi cập nhật với một điều kiện `WHERE` không thỏa; xác nhận ứng dụng không đánh đồng `0` với lỗi kết nối hay exception.
3. **Vi phạm ràng buộc:** dùng dữ liệu thử nghiệm để tạo lỗi `UNIQUE` hoặc khóa ngoại. Kiểm tra log có `operationId`, danh sách kiểu tham số và SQLState/vendor code, nhưng không có giá trị vi phạm, `getMessage()` nguyên văn hoặc chuỗi đánh dấu.
4. **Sai kiểu dữ liệu:** thử binding không hợp lệ hoặc dữ liệu không chuyển đổi được theo DB; đảm bảo log cho biết cột vị trí/kiểu dự kiến qua hợp đồng, không in nội dung dữ liệu.
5. **Lỗi batch:** tạo batch có một mục thất bại. Kiểm tra code đọc `BatchUpdateException.getUpdateCounts()` an toàn và không in từng phần tử tham số.
6. **Cảnh báo:** nếu driver hỗ trợ tình huống tạo `SQLWarning`, kiểm tra vị trí, SQLState và mã lỗi được ghi mà không lưu message hay dữ liệu. Không giả định tất cả driver luôn sinh warning.
7. **Đường ghi tự động:** rà soát cấu hình driver, pool, APM và log DB xem có tự ghi full SQL/bind values không; một bài kiểm tra chỉ nhìn log Java là chưa đủ.

Ví dụ tiêu chí kiểm thử cho một dòng log an toàn:

```text
Phải có:
  op=orders.update-status.v1
  params=[p1:VARCHAR,p2:BIGINT,p3:BIGINT]
  sqlState=<mã hợp lệ hoặc UNAVAILABLE>

Không được có:
  TEST_SECRET_MARKER_7F3
  token, password, JDBC URL có credential
  SQL nội suy giá trị, dữ liệu ResultSet, exception message chưa kiểm soát
```

### Câu hỏi tự đánh giá

- Vì sao `SQLException.getMessage()` không nên mặc định đưa nguyên văn vào log chia sẻ?
- Giữ `p1:VARCHAR` khác gì với lưu nội dung chuỗi được truyền bằng `setString(1, ...)`?
- Khi lỗi xuất hiện trong batch, vì sao `getUpdateCounts()` không chứng minh toàn bộ transaction đã commit?
- Tại sao câu SQL mẫu có dấu `?` vẫn có thể chứa thông tin không nên ghi?
- Nếu cần tìm lỗi trong một request mà không ghi ID người dùng, nên dùng loại correlation ID nào?
- Ngoài logger ở repository, còn những thành phần nào có thể tự ghi giá trị bind?

### Ghi nhớ

Với JDBC, một bản ghi chẩn đoán tốt nên trả lời được **“lệnh nào, kiểu tham số gì, lỗi thuộc nhóm nào, xảy ra ở giai đoạn nào?”** mà không cần biết **“người dùng đã truyền giá trị cụ thể nào?”**. Hãy giữ mã định danh thao tác, thứ tự và `JDBCType` của tham số, `SQLState`, vendor code, thông tin transaction/batch đã chuẩn hóa và ID tương quan phù hợp. Đặt `PreparedStatement` để tham số hóa SQL, phân loại `SQLException` và `SQLWarning`, đồng thời bảo vệ toàn bộ đường ghi log khỏi thông điệp lỗi, SQL có literal, dữ liệu kết quả và các cơ chế ghi tự động không kiểm soát. Những thông tin nhạy cảm cần phục vụ điều tra phải đi qua quy trình riêng được cấp quyền, không xuất hiện mặc định trong nhật ký vận hành.
