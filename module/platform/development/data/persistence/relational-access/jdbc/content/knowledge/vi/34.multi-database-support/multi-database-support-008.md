# Kiểm tra khác biệt fetchSize, batch và nhiều kết quả giữa các hệ quản trị JDBC

## 1. Tại sao cùng mã JDBC lại có hành vi khác nhau?

Một ứng dụng Java có thể sử dụng cùng giao diện `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và chạy trên nhiều hệ quản trị cơ sở dữ liệu quan hệ. JDBC tạo ra **hợp đồng lập trình chung**, nhưng không làm tất cả driver, giao thức mạng, bộ tối ưu SQL và cơ chế cursor trở nên giống hệt nhau.

Ba khu vực dễ gặp sai khác khi chuyển cơ sở dữ liệu hoặc nâng cấp JDBC driver là:

1. **`fetchSize`:** gợi ý driver nên lấy bao nhiêu hàng trong một đợt; cách truyền dữ liệu, đệm trong JVM hay dùng cursor phía server không được tiêu chuẩn hóa hoàn toàn.
2. **Batch:** `addBatch()`/`executeBatch()` có thể được driver gộp lệnh, dừng hoặc tiếp tục sau lỗi; mảng update counts không phải bằng chứng những thay đổi đã commit.
3. **Nhiều kết quả:** một lần `execute()` có thể cho `ResultSet`, update count hoặc nhiều kết quả liên tiếp, nhưng cú pháp stored procedure, số kết quả, thứ tự trả về và khả năng giữ các `ResultSet` đồng thời khác nhau theo hệ quản trị.

Ví dụ, đoạn mã:

```java
ps.setFetchSize(200);
try (ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        consume(rs);
    }
}
```

**không bảo đảm** mọi driver sẽ lấy chính xác 200 hàng qua mỗi round-trip. Tương tự, đoạn:

```java
int[] counts = ps.executeBatch();
```

không bảo đảm driver gửi mỗi phần tử thành một statement riêng, và số `1` trong `counts` không chứng minh giao dịch đã commit.

Bài thuộc chương **Đa hệ quản trị** của module **JDBC**: làm chủ driver, `DataSource`, `PreparedStatement`, `ResultSet`, SQL tham số hóa, CRUD, kết nối, transaction, batching, lỗi và hiệu năng bằng API Java chuẩn. Mục đích không phải ghi nhớ một “mẹo” cho từng DB, mà là **thiết kế phép kiểm tra có thể tái lập trên tổ hợp DB–driver–pool thật**, phân biệt bảo đảm từ JDBC với hành vi riêng của nhà cung cấp.

Sau bài học, bạn có thể lập bảng khả năng hỗ trợ, viết probe cho fetch size, batch và multiple results, kiểm chứng kết quả giao dịch bằng kết nối mới, lựa chọn fallback và xây dựng bộ kiểm thử đa hệ quản trị.

## 2. Ba tầng hợp đồng cần phân biệt

Khi đánh giá một tính năng JDBC, hãy tách:

| Tầng | Quy định/ảnh hưởng | Ví dụ |
|---|---|---|
| **JDBC API** | Phương thức, tham số, hằng, exception và hợp đồng chung | `Statement.setFetchSize(int)`, `BatchUpdateException`, `getMoreResults()` |
| **JDBC driver + cấu hình** | Tối ưu hóa, giao thức, chế độ đệm, hỗ trợ tính năng | Cursor streaming, batch rewrite, xử lý stored procedure |
| **Database + schema + workload** | Transaction, ràng buộc, optimizer, cú pháp procedure, server resources | Commit/rollback, index, lock, số hàng, kết quả nhiều loại |

Một câu hỏi như “`setFetchSize(500)` có giảm RAM không?” không thể trả lời đầy đủ chỉ bằng tài liệu API chuẩn. Cần biết driver nào, phiên bản nào, `autoCommit`, kiểu `ResultSet`, câu SQL, số lượng/độ rộng hàng và cách driver nhận dữ liệu.

Tương tự, “batch có nguyên tử không?” phải được trả lời bằng **ranh giới transaction** và cách DB xử lý statement, không phải chỉ dựa vào việc API có tên `executeBatch`.

### 2.1. Ba mục tiêu kiểm tra độc lập

| Mục tiêu | Câu hỏi chính | Phép đo/xác nhận |
|---|---|---|
| **Khả năng dùng được** | Driver nhận API và trả kết quả đúng không? | Metadata + thực thi trên DB thật |
| **Ngữ nghĩa** | Khi lỗi, tiếp tục, rollback hoặc trả nhiều result thì điều gì xảy ra? | Fixture, counts, query sau transaction, kiểm tra trạng thái cursor |
| **Hiệu năng/tài nguyên** | Bộ nhớ, thời gian, round-trip, pool và DB cursor có phù hợp không? | Benchmark dữ liệu đại diện, metric JVM/pool/DB |

Không dùng kết quả “code chạy không ném exception” để suy ra “streaming thật” hoặc “không rò transaction”.

## 3. Tạo hồ sơ môi trường trước khi thử nghiệm

Khả năng của một tính năng phụ thuộc **tổ hợp cụ thể**. Một báo cáo kiểm thử cần ghi ít nhất:

- DB product và version: ví dụ PostgreSQL, MySQL, SQL Server, Oracle hoặc hệ quản trị khác.
- JDBC driver name/version và phiên bản Java/JDBC API mà ứng dụng dùng.
- `DataSource` loại đơn giản hay do connection pool bọc; những thuộc tính driver/pool liên quan.
- Cấu hình `autoCommit`, isolation, holdability và loại `ResultSet`.
- SQL dialect, schema/ràng buộc, transaction engine và kích thước dữ liệu.
- Có bật tùy chọn batch rewrite, server cursor, prepared statement cache hay không.
- Độ đồng thời, topology mạng, TLS, thời hạn chờ và tài nguyên cấp cho JVM/DB.

Không ghi URL chứa credentials hay password vào báo cáo.

### 3.1. Probe DatabaseMetaData bằng JDBC chuẩn

`DatabaseMetaData` có thể cho biết khả năng mà driver công bố:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;

public final class JdbcCapabilityReport {
    private JdbcCapabilityReport() {}

    public record Capabilities(
            String databaseName,
            String databaseVersion,
            String driverName,
            String driverVersion,
            boolean batchUpdates,
            boolean multipleResultSets,
            boolean multipleOpenResults,
            boolean forwardOnlyReadOnly
    ) {}

    public static Capabilities inspect(DataSource dataSource)
            throws SQLException {
        Objects.requireNonNull(dataSource, "dataSource");

        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData md = connection.getMetaData();

            return new Capabilities(
                    md.getDatabaseProductName(),
                    md.getDatabaseProductVersion(),
                    md.getDriverName(),
                    md.getDriverVersion(),
                    md.supportsBatchUpdates(),
                    md.supportsMultipleResultSets(),
                    md.supportsMultipleOpenResults(),
                    md.supportsResultSetConcurrency(
                            ResultSet.TYPE_FORWARD_ONLY,
                            ResultSet.CONCUR_READ_ONLY)
            );
        }
    }
}
```

Ví dụ sử dụng:

```java
JdbcCapabilityReport.Capabilities capabilities =
        JdbcCapabilityReport.inspect(configuredDataSource);

System.out.println(capabilities);
```

`configuredDataSource` là đối tượng ứng dụng đã cấu hình, không phải biến có sẵn của JDBC.

Ba phương thức metadata đáng chú ý:

- `supportsBatchUpdates()`: driver tuyên bố có hỗ trợ batch updates.
- `supportsMultipleResultSets()`: driver tuyên bố có thể nhận nhiều `ResultSet` từ một lần thực thi khi câu lệnh/DB hỗ trợ.
- `supportsMultipleOpenResults()`: driver tuyên bố có thể giữ nhiều `ResultSet` của **cùng một statement** mở đồng thời.

Hai khả năng multiple result sets và multiple **open** results khác nhau: có thể duyệt từng kết quả liên tiếp mà không được giữ tất cả kết quả mở cùng lúc.

**Metadata là điểm bắt đầu, không phải phép kiểm chứng hoàn tất.** Driver có thể có giới hạn theo kiểu SQL, stored procedure, quyền DB hoặc cấu hình. `DatabaseMetaData` cũng không có một cờ chung bảo đảm “`setFetchSize` sẽ dùng server cursor và không đệm toàn bộ”. Vì vậy cần probe thực tế.

## 4. fetchSize: gợi ý của JDBC và giới hạn của hợp đồng

### 4.1. Hành vi tiêu chuẩn

`Statement.setFetchSize(int rows)` và `ResultSet.setFetchSize(int rows)` đưa ra **gợi ý** số hàng mà driver nên lấy khi cần thêm dữ liệu. Có thể đọc giá trị qua `getFetchSize()`. Đơn vị là **số hàng**, không phải byte, mili giây hay số lượt round-trip.

```java
PreparedStatement ps = connection.prepareStatement(
        sql,
        ResultSet.TYPE_FORWARD_ONLY,
        ResultSet.CONCUR_READ_ONLY
);

ps.setFetchSize(250);
int reported = ps.getFetchSize();
```

Điểm quan trọng:

- `0` thường biểu thị driver dùng hành vi mặc định cho fetch size, theo hợp đồng API.
- Giá trị **dương** yêu cầu/gợi ý driver dùng kích thước lấy hàng cụ thể; driver vẫn có quyền tối ưu hóa khác.
- Không xem số âm là cách cấu hình JDBC khả chuyển. Một số driver có **mẹo riêng với giá trị đặc biệt**, nhưng đó không phải hợp đồng chung.
- `getFetchSize() == 250` chỉ chứng minh thuộc tính được báo là 250, **không chứng minh** mạng truyền đúng từng gói 250 hàng hay heap chứa tối đa 250 hàng.
- `TYPE_FORWARD_ONLY` nghĩa là định hướng con trỏ một chiều, **không tự kích hoạt streaming**.
- `setMaxRows(250)` có ý nghĩa **giới hạn tổng số hàng kết quả** và không thay thế `setFetchSize(250)`.

### 4.2. fetchSize thay đổi những gì?

```text
Application             JDBC driver              Database
    |                         |                       |
    | executeQuery()          | SQL / protocol        |
    |------------------------>|---------------------->|
    |                         |                       |
    | ResultSet               | buffer/cursor?        |
    |<------------------------|<----------------------|
    |                         |                       |
    | next()                  |                       |
    |------------------------>| fetch thêm nếu cần?   |
    |                         |---------------------->|
    | row                     |<----------------------|
    |<------------------------|                       |
    |                         |                       |
    | ...                     | ...                   |
```

Dấu hỏi trong sơ đồ có chủ đích: việc driver lấy hàng **theo đợt**, dùng **cursor phía server**, hay đã **đệm gần như toàn bộ** có thể khác nhau.

| Kỳ vọng của lập trình viên | Thực tế cần kiểm chứng |
|---|---|
| `setFetchSize(100)` thì luôn đúng 100 hàng/round-trip | Hint có thể được diễn giải khác hoặc bỏ qua |
| Đọc một hàng thì chỉ tải một hàng | Driver có thể prefetch nhiều hàng |
| Fetch size nhỏ luôn nhanh hơn | Có thể làm tăng lượt mạng và tổng latency |
| Fetch size lớn luôn nhanh hơn | Có thể tăng heap, GC và dữ liệu đệm |
| Đọc bằng vòng `while(rs.next())` đồng nghĩa streaming | Driver có thể đã buffer toàn bộ kết quả |
| Đóng `ResultSet` sẽ giải phóng mọi tài nguyên tức thì | Cleanup/cursor/network còn phụ thuộc driver và DB |

### 4.3. Một số khác biệt thường gặp theo driver

Bảng sau dùng để **xác định điểm cần thử**, không phải cam kết cho mọi phiên bản:

| Hệ quản trị / driver | Điểm cần kiểm tra |
|---|---|
| **PostgreSQL / pgJDBC** | Fetch qua server cursor thường yêu cầu `autoCommit=false`, fetch size dương và forward-only result; một số tình huống SQL/cursor có giới hạn riêng |
| **MySQL / Connector/J** | Fetch/cursor phụ thuộc các thuộc tính như `useCursorFetch` và chế độ prepared statement của phiên bản; một số cách streaming cũ dùng sentinel giá trị riêng, không khả chuyển |
| **Microsoft SQL Server / JDBC Driver** | Buffering kết quả, `responseBuffering`/chế độ cursor và fetch size có thể chi phối chi phí; cần kiểm tra behavior của loại result set và driver thực tế |
| **Oracle / Oracle JDBC** | Row prefetch/fetch size tương tác với cơ chế prefetch của driver; cần đo round-trip, độ rộng hàng và bộ nhớ theo phiên bản |
| **H2 / database in-memory** | Có thể phù hợp test logic nhưng không đại diện đầy đủ cho cursor, network và transaction của DB production khác |

Các tên thuộc tính vendor-specific có thể thay đổi ngữ nghĩa, giá trị mặc định hoặc điều kiện kích hoạt theo phiên bản. Không hardcode bộ thuộc tính của một DB rồi gán cho DB khác. Trong tài liệu triển khai thật, luôn ghi **phiên bản driver cùng tài liệu cấu hình đã kiểm chứng**.

## 5. Probe fetchSize bằng phép đọc có kiểm soát

### 5.1. Dữ liệu và SQL mẫu

Giả sử có bảng chứa nhiều hàng:

```sql
CREATE TABLE reading_samples (
    sample_id BIGINT PRIMARY KEY,
    category  VARCHAR(20) NOT NULL,
    payload   VARCHAR(300) NOT NULL
);
```

Test setup phải nạp đủ dữ liệu: ví dụ 100, 10.000, rồi 500.000 hàng với độ dài `payload` đại diện. Không chỉ tạo 10 hàng rồi kết luận về streaming. Cú pháp tạo số lượng lớn có thể khác nhau giữa DB nên fixture nên có phần seed riêng cho mỗi hệ quản trị hoặc dùng prepared batch với transaction.

Câu SQL:

```sql
SELECT sample_id, category, payload
FROM reading_samples
WHERE sample_id > ?
ORDER BY sample_id
```

Thứ tự `ORDER BY sample_id` giúp đối chiếu checksum và số hàng giữa các lượt. Tránh `SELECT *` nếu schema có BLOB/CLOB không cần thiết.

### 5.2. Java 17+: tách vòng đời connection khỏi phép quét

Một phép probe an toàn nhận `Connection` còn mở do caller sở hữu, không tự commit/rollback kết nối của caller:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

public final class FetchSizeProbe {
    public record Result(
            long rows,
            long checksum,
            int requestedFetchSize,
            int reportedFetchSize,
            long elapsedMillis
    ) {}

    private static final String SQL = """
            SELECT sample_id, category, payload
            FROM reading_samples
            WHERE sample_id > ?
            ORDER BY sample_id
            """;

    private FetchSizeProbe() {}

    public static Result scan(
            Connection connection,
            long afterId,
            int fetchSize
    ) throws SQLException {
        if (fetchSize < 0) {
            throw new IllegalArgumentException(
                    "fetchSize phải >= 0");
        }

        long started = System.nanoTime();
        long rows = 0;
        long checksum = 0;
        int reported;

        try (PreparedStatement ps = connection.prepareStatement(
                SQL,
                ResultSet.TYPE_FORWARD_ONLY,
                ResultSet.CONCUR_READ_ONLY)) {
            ps.setFetchSize(fetchSize);
            reported = ps.getFetchSize();
            ps.setLong(1, afterId);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("sample_id");
                    String category = rs.getString("category");
                    String payload = rs.getString("payload");

                    if (rs.wasNull() || category == null
                            || payload == null) {
                        throw new SQLException(
                                "Dữ liệu fixture không hợp lệ");
                    }

                    // Tiêu thụ các cột để phép đo có ý nghĩa;
                    // không tạo List giữ toàn bộ ResultSet.
                    checksum = checksum * 31 + id;
                    checksum = checksum * 31 + category.hashCode();
                    checksum = checksum * 31 + payload.hashCode();
                    rows++;
                }
            }
        }

        long millis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

        return new Result(
                rows,
                checksum,
                fetchSize,
                reported,
                millis);
    }
}
```

Hàm `scan` bao gồm thời gian tạo statement, thực thi, duyệt, mapping đơn giản và đóng statement/result set; **không** tính thời gian `getConnection()` hoặc `commit()` vì caller quản lý chúng. Ghi rõ ranh giới này khi báo cáo.

`rs.wasNull()` trong ví dụ áp dụng cho getter `getString("payload")` vừa gọi; `sample_id` là khóa chính không null theo schema. Nếu đo một cột có thể null, phải kiểm tra `wasNull()` ngay sau getter tương ứng.

### 5.3. Chạy dưới chế độ connection phù hợp

Nếu muốn khảo sát driver dùng server-side cursor trong transaction, có thể chạy probe bên trong transaction riêng của test:

```java
try (Connection connection = dataSource.getConnection()) {
    // Test này phải sở hữu connection và transaction.
    if (!connection.getAutoCommit()) {
        throw new SQLException(
                "Fixture yêu cầu autoCommit ban đầu là true");
    }

    connection.setAutoCommit(false);
    try {
        FetchSizeProbe.Result result =
                FetchSizeProbe.scan(connection, 0L, 200);

        // ResultSet/PreparedStatement đã đóng trước commit.
        connection.commit();
        System.out.println(result);
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Đoạn này giả định `dataSource` là đối tượng đã cấu hình trong test. Nếu dùng connection pool có `autoCommit=false` mặc định hoặc transaction manager, không áp đặt mẫu này; phải dùng owner transaction của framework/pool.

**Không commit giữa chừng khi `ResultSet` còn được đọc** nếu driver cần transaction giữ cursor. Sau khi commit, cursor có thể đóng theo holdability; đừng trông cậy vào hành vi giữ cursor trừ khi đã kiểm thử.

### 5.4. Những kịch bản cần đo

| Cấu hình | Số hàng | Câu hỏi |
|---|---:|---|
| Fetch size 0 (mặc định) | 100 / 10.000 / 500.000 | Driver mặc định đệm/lấy hàng thế nào? |
| Fetch size 50 | Cùng dataset | Latency, round-trip, heap có đổi không? |
| Fetch size 200 | Cùng dataset | Điểm cân bằng giữa network và RAM? |
| Fetch size 1.000 | Cùng dataset | Dữ liệu rộng có tăng GC/peak heap? |
| Auto-commit bật | Cùng dữ liệu | Cursor/fetch behavior khác không? |
| Auto-commit tắt | Cùng dữ liệu | Có kích hoạt server cursor hoặc giữ transaction lâu hơn không? |
| ResultSet scrollable | Cùng dữ liệu nếu được hỗ trợ | Driver có đệm nhiều hơn forward-only không? |
| Stop sau 10 hàng | Dataset rất lớn | Driver đã tải bao nhiêu dữ liệu trước khi caller dừng? |
| Tiêu thụ chậm | Dataset lớn | Connection/cursor bị giữ trong pool bao lâu? |

Một test có 500.000 hàng nhưng chỉ kiểm tra thời gian `executeQuery()` là chưa đủ; nhiều driver tiếp tục thực hiện I/O trong `ResultSet.next()`. Cần đo cả thời gian tiêu thụ, connection held duration, peak heap và tải DB.

**Không dùng một phép đo 3 ms trên H2 rồi suy ra MySQL, SQL Server hay PostgreSQL sẽ mất 3 ms.**

## 6. Batch JDBC: hợp đồng chung và những điều không được suy đoán

### 6.1. Chuỗi API cơ bản

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE reading_samples SET category = ? WHERE sample_id = ?")) {
    for (Change item : changes) {
        ps.setString(1, item.category());
        ps.setLong(2, item.id());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
```

`Change` và `changes` là model/list do ứng dụng cung cấp. `Connection` đang mở và được sở hữu bởi caller.

Những điều JDBC cung cấp:

- `addBatch()` thêm một bộ lệnh/tham số để thực thi sau.
- `executeBatch()` gửi batch và trả mảng update counts nếu thành công; nếu có lỗi SQL, driver có thể ném `BatchUpdateException`.
- `Statement.SUCCESS_NO_INFO` (giá trị `-2`) nghĩa là lệnh được báo thành công nhưng số hàng tác động không xác định.
- `Statement.EXECUTE_FAILED` (giá trị `-3`) nghĩa là lệnh được báo thất bại.
- `clearBatch()` xóa **các lệnh đã xếp hàng nhưng chưa thực thi** trong statement hiện tại; nó không rollback những thao tác DB đã chạy.
- `executeLargeBatch()` và `getLargeUpdateCounts()` hỗ trợ dạng số đếm `long` khi cần và được driver hỗ trợ.

Không dùng batch cho câu `SELECT` thông thường và kỳ vọng nhận một danh sách `ResultSet` tương ứng từng item: batch API chủ yếu phục vụ các câu cập nhật hoặc các lệnh trả update count theo hợp đồng JDBC; truy vấn trả result set trong batch có thể không được hỗ trợ.

### 6.2. Stop-on-error và continue-on-error

Giả sử một batch bốn thao tác insert:

```text
index:     0       1       2          3
item:      A       B       B(lỗi)     C
```

Một driver dừng tại lỗi có thể báo:

```text
BatchUpdateException.getUpdateCounts() == [1, 1]
```

Driver tiếp tục có thể báo:

```text
BatchUpdateException.getUpdateCounts() == [1, 1, -3, 1]
```

Tuy nhiên, nếu DB đánh dấu transaction đã lỗi sau phần tử vi phạm constraint, lệnh sau cũng có thể không được chấp nhận. Nếu driver rewrite nhiều insert thành một SQL, mảng counts có thể phản ánh granularity khác. **Không hardcode hình dạng mảng counts cho mọi driver**.

| Count | Hằng | Diễn giải đúng |
|---:|---|---|
| `0` | Không có | Lệnh được báo chạy và tác động 0 hàng; không nhất thiết lỗi |
| Số dương | Không có | Driver báo số hàng tác động; chưa chứng minh commit |
| `-2` | `SUCCESS_NO_INFO` | Driver báo success nhưng không có số hàng cụ thể |
| `-3` | `EXECUTE_FAILED` | Driver báo phần tử tương ứng thất bại |
| Không có phần tử trong mảng | Không có | Không đủ thông tin để kết luận chắc trạng thái commit của input tương ứng |

Chỉ dựa vào mảng counts để retry các item “chưa được báo” là nguy hiểm nếu lỗi xảy ra quanh network/commit và trạng thái thực thi chưa rõ.

### 6.3. Batch không tự làm một transaction nguyên tử

| Cấu hình | Điều phải kiểm tra |
|---|---|
| `autoCommit=true` | Một phần thay đổi có thể đã được commit; cách driver gộp statement ảnh hưởng kết quả |
| `autoCommit=false` + rollback thành công | Các thay đổi thuộc transaction được hoàn tác nếu DB/table hỗ trợ transaction |
| `autoCommit=false` + commit thành công | Các thay đổi được commit theo outcome của transaction |
| Lỗi connection lúc commit | Client có thể không biết DB đã commit hay chưa |
| Transaction chứa nhiều batch | Mọi batch cùng nằm trong transaction nếu cùng Connection và chưa commit |

**Tính nguyên tử thuộc về transaction của DB**, không thuộc về tên API `executeBatch()`. Một batch có thể bao gồm nhiều statement nhưng một transaction có thể bao nhiều batch; ranh giới cần được thiết kế tường minh.

## 7. Những tối ưu hóa batch riêng của driver

Cùng `PreparedStatement.executeBatch()`, driver có thể:

- Gửi từng bộ tham số thành nhiều lệnh.
- Gửi một protocol batch giúp giảm round-trip.
- Gộp nhiều lần `INSERT ... VALUES (?, ?)` thành một câu `INSERT ... VALUES (...), (...)`.
- Chia batch lớn thành những đoạn nhỏ do giới hạn server, parameter count hoặc packet size.
- Dùng prepared execution trên server hoặc client-side emulation theo cấu hình.
- Trả generated keys và update counts theo mức chi tiết khác nhau.

Ví dụ thuộc tính thường gặp:

| Driver | Điểm cấu hình cần xem |
|---|---|
| PostgreSQL JDBC | `reWriteBatchedInserts` có thể thay đổi cách tối ưu các lệnh INSERT phù hợp |
| MySQL Connector/J | `rewriteBatchedStatements` có thể thay đổi cách driver gom/rewrite batch |
| SQL Server JDBC | Cần kiểm tra khả năng batching của driver và cách server nhận statement/update counts |
| Oracle JDBC | Cần kiểm tra cách batching, round-trip và giới hạn theo phiên bản driver |
| Driver khác | Tra đúng tài liệu JDBC driver và thực nghiệm thay vì sao chép thuộc tính từ DB khác |

Các property này **không phải API JDBC chuẩn**; chỉ dùng khi đúng driver/phiên bản hỗ trợ. Một tính năng rewrite có thể chỉ áp dụng cho một số dạng SQL; đừng suy ra mọi `UPDATE`, `MERGE` hoặc stored procedure đều tự được rewrite giống `INSERT`.

### 7.1. Không gộp đánh giá throughput và tính đúng đắn vào một chỉ số

Khi so sánh bật/tắt rewrite, cần ghi:

- Tổng số item trong batch, kích thước payload và số lần `executeBatch()`.
- Số item được DB **commit thành công**, không chỉ số count driver báo.
- Số lần rollback, tỷ lệ constraint violation và cách phục hồi sau lỗi.
- Mapping generated keys nếu nghiệp vụ cần.
- SQLState/vendor code, lỗi connection và thời gian retry.
- Throughput, p95/p99 và thời gian giữ Connection trong pool.

Một cấu hình nhanh hơn trong happy path nhưng khó xác định item lỗi khi import có nhiều dữ liệu sai có thể không phải lựa chọn tốt nhất.

## 8. Ví dụ Java: chạy batch có ranh giới transaction rõ ràng

Đoạn mã dưới đây phục vụ tình huống **all-or-nothing** trên một bảng có transaction. Với ứng dụng đang dùng transaction manager của framework, cần tích hợp vào owner đó thay vì mở một transaction riêng.

```java
import javax.sql.DataSource;
import java.sql.BatchUpdateException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;
import java.util.Objects;

public final class CategoryBatchWriter {
    public record Change(long id, String category) {}

    private static final String SQL = """
            UPDATE reading_samples
            SET category = ?
            WHERE sample_id = ?
            """;

    private final DataSource dataSource;

    public CategoryBatchWriter(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public int[] updateAtomically(List<Change> changes)
            throws SQLException {
        Objects.requireNonNull(changes, "changes");

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu Connection mới ở autoCommit=true");
            }

            connection.setAutoCommit(false);

            try {
                int[] counts;

                try (PreparedStatement ps =
                             connection.prepareStatement(SQL)) {
                    for (Change change : changes) {
                        ps.setString(1, change.category());
                        ps.setLong(2, change.id());
                        ps.addBatch();
                    }

                    try {
                        counts = ps.executeBatch();
                    } catch (BatchUpdateException batchFailure) {
                        // Counts chỉ là chẩn đoán thực thi;
                        // không được coi như dữ liệu đã commit.
                        int[] reported = batchFailure.getUpdateCounts();
                        // reportDiagnostic(reported, batchFailure);
                        throw batchFailure;
                    }
                }

                connection.commit();
                return counts;
            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }

            // try-with-resources đóng/trả Connection về pool.
            // Việc khôi phục state/loại kết nối lỗi của pooled
            // Connection phải tuân theo chính sách pool.
        }
    }
}
```

Lưu ý khi sử dụng:

1. `PreparedStatement` được tạo và đóng **trong** transaction; cùng một `Connection` được dùng để chạy batch và commit.
2. Khi batch lỗi, mã thử rollback. Nếu rollback cũng lỗi, phải giữ lỗi gốc và xử lý connection có outcome chưa rõ.
3. Nếu `commit()` ném `SQLException`, thử rollback sau đó **không chứng minh** server chưa commit. Với thao tác ghi quan trọng, cần idempotency và cơ chế đối soát.
4. Mảng `counts` sau `commit()` thành công vẫn có thể chứa `SUCCESS_NO_INFO` hoặc update count `0`, cần diễn giải theo hợp đồng nghiệp vụ.
5. Ví dụ dựa vào chính sách `DataSource`/pool trả connection về trạng thái chuẩn khi close. Nếu tự viết pool hoặc quản lý Connection thủ công, phải thiết kế reset đúng cách **mà không bật auto-commit khi transaction còn chưa được giải quyết**.
6. Để benchmark hiệu năng, cần đo cả thời gian commit và cleanup; không chỉ thời gian `executeBatch()`.

Đối với batch chứa một item vi phạm ràng buộc, trạng thái cuối sau rollback phải được kiểm tra bằng **kết nối mới**, không suy đoán từ độ dài mảng `getUpdateCounts()`.

## 9. Thiết kế test batch đa hệ quản trị

### 9.1. Fixture chắc chắn có lỗi ở giữa

Tạo một bảng test riêng:

```sql
CREATE TABLE jdbc_batch_probe (
    probe_id BIGINT PRIMARY KEY,
    value_text VARCHAR(60) NOT NULL
);
```

Nạp bốn item theo thứ tự:

```text
index   probe_id      value_text
0       base + 1      first
1       base + 2      second
2       base + 2      duplicate   <-- vi phạm PRIMARY KEY
3       base + 3      last
```

Dùng `PreparedStatement` với `INSERT INTO jdbc_batch_probe (probe_id, value_text) VALUES (?, ?)`, chạy hai kịch bản khác nhau.

**A. Transaction tường minh:**

- Gọi `setAutoCommit(false)` trước khi thực thi.
- Ghi lại `BatchUpdateException`, counts, SQLState và vendor code.
- Rollback, đóng Connection ghi.
- Query các ID bằng **Connection mới**, xác nhận vùng ID test **không có hàng mới**.
- Không assert cố định driver phải trả `[1,1]` hay `[1,1,-3,1]`.

**B. Auto-commit mặc định:**

- Cấu hình và xác nhận `autoCommit=true`.
- Ghi counts nếu có; đóng Connection ghi.
- Query vùng ID từ Connection mới để xem thực sự còn những hàng nào.
- Không áp đặt tất cả driver phải commit hai hàng đầu; ghi kết quả theo tổ hợp driver/DB.
- Dọn dữ liệu test bằng fixture cô lập, không sử dụng ID trùng giữa các test song song.

### 9.2. Ma trận lỗi và đặc tính batch

| Kịch bản | Điều cần khẳng định |
|---|---|
| Toàn bộ item hợp lệ | Đúng số hàng được commit; loại count có thể khác |
| Constraint lỗi ở đầu | Không giả định item sau đã thử; rollback và kiểm tra DB |
| Constraint lỗi ở giữa | Ghi stop/continue behavior, rollback và dữ liệu cuối |
| Constraint lỗi ở cuối | Không mặc định các item trước đã commit khi manual tx |
| `SUCCESS_NO_INFO` | Không quy `-2` thành số hàng tác động |
| `UPDATE` tác động 0 hàng | Tùy nghiệp vụ, 0 có thể là thành công về SQL nhưng không đạt mục tiêu |
| Driver rewrite bật/tắt | So sánh counts, generated keys, dữ liệu và throughput |
| Batch lớn | Kiểm tra memory, packet/parameter limit và chunking |
| Deadlock/serialization failure | Transaction rollback và retry theo chính sách |
| Mất kết nối quanh commit | Không gắn nhãn rollback chắc chắn; đối soát idempotency |
| Generated keys | Kiểm tra thứ tự/độ đầy đủ với driver thực tế |
| Nhiều batch cùng transaction | Lỗi ở batch sau phải rollback cả thao tác trước |
| Pool bật/tắt | Không rò trạng thái auto-commit/transaction khi trả connection |
| DB không hỗ trợ tính năng | Fallback rõ ràng hoặc báo unsupported, không âm thầm bỏ kiểm thử |

**Đừng dùng H2 làm bằng chứng duy nhất** cho batch rewrite và partial commit của DB production khác. Unit test có thể xác nhận logic phân loại counts, nhưng integration test mới xác định hành vi driver, transaction và constraint thật.

## 10. “Nhiều kết quả” trong JDBC nghĩa là gì?

Trong JDBC, một lệnh thực thi bằng `Statement.execute(...)` hoặc `CallableStatement.execute()` có thể trả:

- Một `ResultSet`.
- Một **update count**: số hàng bị tác động bởi một thao tác cập nhật theo báo cáo của driver.
- **Nhiều kết quả nối tiếp**, gồm `ResultSet` và/hoặc update count, khi database/driver hỗ trợ.

Không đồng nhất điều đó với:

1. **Nhiều hàng trong một ResultSet**: đây vẫn là *một* result set.
2. **Nhiều câu SQL độc lập do Java lần lượt gọi**: đây là nhiều lần execute, không nhất thiết một execution có nhiều result.
3. **Một batch**: `executeBatch()` trả update counts cho các phần tử, không phải cùng API duyệt multiple results.
4. **Nhiều DB connection**: hoàn toàn không liên quan đến số result sets trong một statement.

Stored procedure là nguồn ví dụ điển hình cho multiple results. Một số DB còn có khả năng trả nhiều kết quả từ một lệnh/tập lệnh; cú pháp, cấu hình cho phép nhiều statements và mức hỗ trợ khác nhau.

**Không bật tùy chọn cho phép nối nhiều SQL statements từ input người dùng** chỉ để tạo nhiều kết quả. Truyền nhiều câu tùy ý trong một chuỗi SQL có thể mở rộng bề mặt SQL injection; nếu nghiệp vụ cần nhiều câu lệnh, dùng API có cấu trúc, giao dịch rõ ràng hoặc procedure do server định nghĩa và được kiểm soát.

## 11. State machine để duyệt ResultSet xen kẽ update count

### 11.1. Các phương thức chuẩn

| API | Ý nghĩa |
|---|---|
| `statement.execute(...)` / `call.execute()` | Thực thi; trả `true` nếu **kết quả đầu tiên** là `ResultSet` |
| `statement.getResultSet()` | Lấy `ResultSet` hiện tại nếu loại kết quả là ResultSet |
| `statement.getUpdateCount()` | Lấy count hiện tại nếu kết quả là update count; trả `-1` khi không có |
| `statement.getMoreResults()` | Chuyển sang kết quả tiếp theo; trả `true` nếu kết quả mới là ResultSet |
| `statement.getMoreResults(int current)` | Chọn cách xử lý ResultSet trước đó bằng hằng đóng/giữ, nếu driver hỗ trợ |
| `statement.getLargeUpdateCount()` | Dạng `long` để đọc count lớn, nếu được driver hỗ trợ |

**Sai lầm dễ mắc:** cho rằng `getMoreResults() == false` nghĩa là không còn kết quả nào. Nó cũng có thể có nghĩa **kết quả tiếp theo là update count**, cần gọi `getUpdateCount()` để phân biệt.

### 11.2. Mẫu vòng lặp đúng

```text
hasResultSet = execute()

while (true):
    if hasResultSet:
        đọc và đóng ResultSet hiện tại
    else:
        updateCount = getUpdateCount()
        if updateCount == -1:
            break  // không còn kết quả
        xử lý updateCount

    hasResultSet = getMoreResults()
```

Điều kiện **kết thúc** là: `hasResultSet == false` **và** `getUpdateCount() == -1` ở thời điểm hiện tại, sau khi đã chuyển qua các kết quả theo hợp đồng driver.

Nếu loop chỉ làm `while (statement.getMoreResults())`, nó có thể bỏ qua update counts và cả các ResultSet xuất hiện **sau một update count**.

### 11.3. Java: đọc kết quả theo từng loại

Ví dụ dưới đây gọi procedure đã được tạo trong database thử nghiệm, giả định procedure có một tham số IN và có thể trả nhiều loại kết quả. Cách **tạo** procedure là SQL dialect-specific; cú pháp gọi qua JDBC cũng phải kiểm thử trên driver.

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;

public final class MultiResultReader {
    public record Report(int resultSets, int updateResults,
                         long rowsRead) {}

    private MultiResultReader() {}

    /**
     * Connection thuộc caller; không tự commit/close Connection.
     * Procedure report_for_category phải có trong DB test.
     */
    public static Report callReport(
            Connection connection, String category
    ) throws SQLException {
        int resultSets = 0;
        int updateResults = 0;
        long rowsRead = 0;

        try (CallableStatement call = connection.prepareCall(
                "{call report_for_category(?)}")) {
            call.setString(1, category);
            boolean hasResultSet = call.execute();

            while (true) {
                if (hasResultSet) {
                    try (ResultSet rs = call.getResultSet()) {
                        if (rs == null) {
                            throw new SQLException(
                                    "Driver báo ResultSet nhưng trả null");
                        }

                        ResultSetMetaData md = rs.getMetaData();
                        int columns = md.getColumnCount();
                        resultSets++;

                        while (rs.next()) {
                            // Đọc mọi cột trong ví dụ chẩn đoán;
                            // không đưa giá trị ra log.
                            for (int i = 1; i <= columns; i++) {
                                rs.getObject(i);
                            }
                            rowsRead++;
                        }
                    }
                } else {
                    int count = call.getUpdateCount();

                    if (count == -1) {
                        break; // Không còn result/update count.
                    }

                    updateResults++;
                    // Báo count theo metadata event, không suy ra commit.
                }

                // false có thể nghĩa là update count kế tiếp;
                // vòng lặp phải kiểm tra getUpdateCount().
                hasResultSet = call.getMoreResults();
            }
        }

        return new Report(resultSets, updateResults, rowsRead);
    }
}
```

**Điểm quan trọng của ví dụ:**

- `CallableStatement` và mỗi `ResultSet` đều được đóng; không trả result set ra khỏi phạm vi Connection còn sống.
- Mẫu dùng `getMoreResults()` không tham số, thông thường đóng current result khi chuyển. Đối với ví dụ, ResultSet còn được đóng tường minh trong `try-with-resources`.
- `ResultSetMetaData` giúp xử lý các result set có số cột khác nhau. Trong sản phẩm thật, cần mapper riêng cho từng shape, kiểm tra tên cột/kiểu và tránh `getObject()` không cần thiết với BLOB lớn.
- `getUpdateCount()` trả `-1` khi không có update count hiện tại. Một update count bằng `0` **vẫn là kết quả hợp lệ**, không phải tín hiệu kết thúc.
- `getMoreResults()` có thể trả `false` giữa hai result set nếu có một update count xen vào.
- Procedure trong DB có thể tạo **kết quả khác nhau** do câu lệnh bên trong, tùy server/driver; không áp đặt một shape chung cho PostgreSQL, MySQL, SQL Server và Oracle.
- `rowsRead` là tổng số hàng duyệt qua các ResultSet; nó **không** là tổng số hàng bị UPDATE/INSERT và không chứng minh transaction đã commit.

Nếu procedure có **OUT parameters**, cần đăng ký tham số qua `registerOutParameter(...)` theo cú pháp/mapping của DB. Với những driver yêu cầu tiêu thụ hết các result sets/update counts trước khi đọc OUT parameters, phải tuân thủ thứ tự đó; không giả định OUT parameters luôn khả dụng ngay sau `execute()`.

## 12. getMoreResults(int): đóng hay giữ kết quả cũ?

JDBC có các hằng:

- `Statement.CLOSE_CURRENT_RESULT`: đóng ResultSet hiện tại khi chuyển.
- `Statement.KEEP_CURRENT_RESULT`: cố giữ ResultSet hiện tại còn mở.
- `Statement.CLOSE_ALL_RESULTS`: đóng các ResultSet trước đó đang mở.

Dạng:

```java
boolean another = statement.getMoreResults(
        Statement.CLOSE_CURRENT_RESULT);
```

có thể dùng khi muốn chỉ rõ chính sách đóng; nhưng driver có thể ném `SQLFeatureNotSupportedException` nếu biến thể hoặc khả năng tương ứng không được hỗ trợ. Phải kiểm tra `DatabaseMetaData.supportsMultipleOpenResults()` trước khi thiết kế xử lý cần `KEEP_CURRENT_RESULT`, rồi thực nghiệm xác minh.

**Đề xuất khả chuyển:** xử lý xong và đóng từng `ResultSet` **trước** khi gọi `getMoreResults()`. Việc giữ nhiều ResultSet đồng thời có thể làm driver/server phải buffer thêm dữ liệu hoặc giữ nhiều cursor; chỉ dùng khi thực sự cần và đã kiểm thử trên DB mục tiêu.

### 12.1. Update count không giống số hàng trong ResultSet

`getUpdateCount() == 3` cho biết driver báo một thao tác DML tác động ba hàng theo ngữ nghĩa của nó; không đồng nghĩa `getResultSet()` có ba hàng. Nếu stored procedure vừa cập nhật một bảng vừa trả một tập kết quả, phải ghi/kiểm chứng **hai loại thông tin riêng**.

### 12.2. Hệ quản trị có thể không trả mọi update count của procedure

Một số hệ quản trị/procedure có thiết lập không gửi update count của các statement nội bộ, hoặc driver điều chỉnh cách trả. Ví dụ các stored procedure trên SQL Server có thể sử dụng `SET NOCOUNT ON` để ảnh hưởng việc gửi row count của lệnh nội bộ. Không nên đưa con số “procedure trả đúng 2 update count rồi 1 ResultSet” thành assertion khả chuyển.

Trong môi trường thật, trước tiên phải xác định **hợp đồng trả kết quả** của procedure trên từng DB, sau đó mới tạo adapter/mapper phù hợp. Nếu ứng dụng đòi hỏi ba result sets theo thứ tự nhưng driver chỉ hỗ trợ một shape, nên chọn API khác (ví dụ các truy vấn tách riêng hoặc OUT parameter thích hợp) thay vì nuốt kết quả.

## 13. Kịch bản kiểm thử nhiều kết quả theo từng driver

Bộ kiểm thử nên có fixture **riêng cho từng SQL dialect**, nhưng phần code Java duyệt state machine có thể dùng chung.

| Trường hợp | Mục tiêu |
|---|---|
| Procedure trả một ResultSet | `execute() == true` và đọc được hàng |
| Procedure trả update count | `execute()` có thể `false`, `getUpdateCount() >= 0` |
| ResultSet rồi update count | Tiêu thụ ResultSet, nhận count tiếp theo |
| Update count rồi ResultSet | `getMoreResults() == true` sau count |
| Hai ResultSet liên tiếp | Có thể đọc lần lượt, không rò cursor |
| Update count bằng 0 | Loop không kết thúc sai |
| Không có kết quả | `getUpdateCount() == -1` và không còn result set |
| Có OUT parameter | Đọc đúng theo hợp đồng driver sau khi xử lý kết quả |
| `KEEP_CURRENT_RESULT` | Nếu hỗ trợ, thử giữ hai ResultSet; nếu không, fallback đóng trước |
| Procedure lỗi giữa các kết quả | Giữ exception chain, đóng resources, rollback theo owner |
| Procedure chỉ chạy SELECT | Không giả định DB phải hỗ trợ multi-statement text |
| Procedure thay đổi cấu trúc trả ra | Mapper phát hiện lỗi metadata thay vì đọc nhầm cột |
| Transaction commit giữa chừng | Xác minh holdability/cursor; không phụ thuộc behavior mặc định |
| Pool tái sử dụng Connection | Không còn ResultSet hoặc session state từ request trước |

Đừng dùng SQL kiểu `SELECT 1; SELECT 2` và kết luận đó là cách thử portable cho multiple results: việc gửi nhiều statement trong một chuỗi SQL có thể bị từ chối, yêu cầu tùy chọn bảo mật riêng hoặc có semantics khác với stored procedure.

## 14. Kết hợp ba tính năng: nơi khác biệt trở nên khó thấy

Giả sử ứng dụng gọi stored procedure sinh nhiều `ResultSet`, mỗi ResultSet có hàng trăm nghìn bản ghi; sau đó ghi một batch kết quả tổng hợp.

Những câu hỏi cần trả lời:

1. Fetch size áp dụng như thế nào cho **từng ResultSet** của procedure? Driver có prefetch toàn bộ kết quả đầu trước khi cho phép tiến tới kết quả sau không?
2. Có được giữ hai ResultSet mở cùng lúc không? `KEEP_CURRENT_RESULT` có thật sự được hỗ trợ?
3. Có được thực thi một `PreparedStatement` khác trên **cùng Connection** khi vẫn đang tiêu thụ ResultSet của procedure không? Không giả định mọi driver hỗ trợ hoạt động xen kẽ.
4. Batch ở cuối nằm trong **cùng transaction** với procedure hay mở Connection khác?
5. Nếu `executeBatch()` lỗi, các thay đổi mà procedure đã thực hiện có được rollback cùng batch không? Có lệnh commit nội bộ nào không?
6. Khi cursor tiêu thụ chậm, connection bị giữ bao lâu? Pool có đủ cho các request khác?
7. Nếu DB/driver trả lỗi khi lấy kết quả thứ hai, làm sao xác định transaction và các tác động ngoài DB đã phát sinh?

**Cách thiết kế dễ kiểm chứng hơn:** hoàn tất việc đọc/đóng từng ResultSet, sau đó chạy batch trong một ranh giới transaction đã được xác định rõ. Nếu phải giữ snapshot hoặc cần nguyên tử trong một transaction, owner giữ cùng Connection cho toàn bộ phần đó và chấp nhận chi phí tài nguyên; nếu công việc dài, xem xét chia chunk với checkpoint/idempotency.

Không biến kết quả trung gian thành `List` hàng triệu DTO chỉ để “tránh phụ thuộc driver” nếu ứng dụng có hạn mức RAM. Có thể thay thế bằng phân trang SQL, bảng staging, cursor đúng driver hoặc luồng xuất file có kiểm soát.

## 15. Những lỗi thường gặp khi chuyển DB

| Sai lầm | Hậu quả | Cách phòng |
|---|---|---|
| Chỉ gọi `setFetchSize(100)` rồi tuyên bố đang streaming | Có thể vẫn đệm toàn bộ | Đo heap/network/DB cursor và thử transaction config |
| Mang giá trị fetch size âm đặc thù MySQL sang driver khác | Lỗi API hoặc hành vi không xác định | Tách cấu hình vendor và kiểm tra loại driver |
| Dùng `TYPE_SCROLL_INSENSITIVE` khi cần server streaming | Driver có thể cache nhiều hàng hơn | Ưu tiên forward-only khi chỉ quét |
| Commit khi còn đang đọc cursor transaction-bound | ResultSet có thể bị đóng | Duyệt/đóng xong trước commit, kiểm tra holdability |
| Xem `executeBatch()` là transaction | Partial updates bất ngờ | Dùng transaction owner rõ ràng |
| `counts.length == batchSize` là bắt buộc trên mọi lỗi | Sai với stop-on-error | Test stop/continue theo driver |
| Cộng `SUCCESS_NO_INFO == -2` vào số hàng | Báo tổng sai | Tách trạng thái báo cáo và số hàng |
| Tự retry item không có count | Có thể ghi trùng | Đối soát DB/idempotency khi outcome chưa rõ |
| Bật batch rewrite rồi giữ assertion generated key cũ | Mapping sai | Test generated keys theo cấu hình |
| Cho rằng `execute() == false` là không có kết quả | Bỏ qua update count đầu tiên | Kiểm tra `getUpdateCount()` |
| Cho rằng `getMoreResults() == false` nghĩa là hết | Bỏ qua update count xen kẽ | State machine đúng |
| Giữ hai ResultSet mở mà không check driver | Exception hoặc tăng buffer | `supportsMultipleOpenResults()` + fallback |
| Chỉ dùng mock JDBC để xác nhận portability | Không thấy behavior DB/driver | Integration test engine/version thật |
| Giả định stored procedure có cú pháp/OUT giống nhau | Lỗi khi chuyển dialect | Adapter riêng theo DB |
| Không đóng statement/result set khi có lỗi | Rò cursor/connection và cạn pool | `try-with-resources` và owner transaction |
| Chỉ đo `executeQuery()` | Bỏ chi phí `next()`/mapping | Đo toàn bộ vòng đời và p95/p99 |
| Dùng `SELECT 1; SELECT 2` làm chuẩn mọi DB | Có thể bị từ chối hoặc yêu cầu cấu hình không an toàn | Procedure/fixture DB-specific |

## 16. Khung kiểm thử khả chuyển: chung API, riêng fixture

Thiết kế hợp lý là có một giao diện **fixture theo database** và một bộ assertion/đo dùng chung:

```text
                           +------------------------+
PostgreSQL fixture ------> |                        |
MySQL fixture -----------> | JDBC portability suite | --> report matrix
SQL Server fixture ------> |                        |
Oracle fixture ----------> |                        |
                           +------------------------+
                               |
                               +--> fetchSize probes
                               +--> batch failure/commit probes
                               +--> multiple results probes
```

Fixture riêng cung cấp:

- Cách tạo schema/tables, nạp dữ liệu.
- Cách tạo stored procedure trả những kết quả cần thử.
- JDBC URL/driver properties từ cấu hình bảo mật.
- Chính sách setup/teardown và cấp vùng ID cho test song song.
- Những đặc tính được DB hỗ trợ, không bịa tính năng mà DB không có.
- Script cập nhật optimizer statistics khi kiểm thử hiệu năng cần thiết.

Phần Java dùng chung xác minh:

- Tính đúng đắn của số hàng và checksum khi fetchSize thay đổi.
- `BatchUpdateException` và dữ liệu cuối sau commit/rollback.
- Thứ tự result sets/update counts theo **hợp đồng cụ thể của fixture**.
- Không rò `Connection`, statement và ResultSet trong nhánh lỗi.
- Khả năng chạy với `autoCommit`, kiểu `ResultSet`, pool và cấu hình driver đã báo cáo.

### 16.1. Không biến unsupported thành test “xanh” giả

Một số khả năng là tùy chọn. Nếu metadata báo không hỗ trợ hoặc probe ném `SQLFeatureNotSupportedException`:

- Với tính năng **bắt buộc theo yêu cầu sản phẩm**, test phải **thất bại rõ ràng** để chặn triển khai trên DB đó.
- Với tính năng **tối ưu tùy chọn**, test có thể đánh dấu **unsupported/skip có lý do**, đồng thời kiểm tra fallback hoạt động đúng.
- Không bỏ qua exception và trả thành công giả; báo cáo phải thể hiện điều gì đã/không được xác minh.

Một dòng kết quả nên có dạng:

```text
database=PostgreSQL
driver=<version thực tế>
feature=server-side-cursor-like-fetch
requestedFetchSize=200
autoCommit=false
status=PASS/FAIL/UNSUPPORTED/NOT_MEASURED
rows=<số đo>
peakHeap=<số đo>
notes=<bối cảnh cụ thể>
```

Các dấu `<...>` là placeholder trong **báo cáo minh họa**, không phải kết quả benchmark hoặc tên phiên bản thực.

## 17. Ma trận kiểm thử tích hợp tối thiểu

| Nhóm | Kịch bản | Kết quả kiểm tra |
|---|---|---|
| Metadata | `supportsBatchUpdates`, `supportsMultipleResultSets` | Ghi trạng thái hỗ trợ/không hỗ trợ |
| Fetch | `setFetchSize(0)` và số dương | SQL đúng, số hàng/checksum không đổi |
| Fetch | Auto-commit bật/tắt | Đo khác biệt memory/latency/cursor |
| Fetch | 100 hàng và 500.000 hàng | Không suy từ test nhỏ sang large result |
| Fetch | Dừng sớm sau một số hàng | Kiểm tra resource cleanup và prefetch |
| Fetch | ResultSet forward-only/scrollable | Ghi giới hạn driver, hiệu năng |
| Batch | Tất cả item hợp lệ | Dữ liệu tồn tại sau commit |
| Batch | Lỗi UNIQUE ở đầu/giữa/cuối | Đọc counts, không hardcode shape |
| Batch | Rollback transaction sau lỗi | Không có hàng mới khi kiểm tra từ Connection khác |
| Batch | Auto-commit sau lỗi | Quan sát hàng thực tồn tại; khác biệt được ghi nhận |
| Batch | Rewrite bật/tắt | So sánh update counts, generated keys, throughput |
| Batch | Lỗi lúc commit | Trạng thái UNKNOWN nếu không chắc server outcome |
| Multi results | ResultSet → update count → ResultSet | Vòng lặp không dừng sai khi getMoreResults false |
| Multi results | Update count 0 | Không hiểu thành hết kết quả |
| Multi results | Hai ResultSet liên tiếp | Duyệt và đóng theo đúng thứ tự |
| Multi results | `KEEP_CURRENT_RESULT` | Dùng nếu metadata và thực tế hỗ trợ |
| Multi results | OUT parameter và procedure | Mapping/cú pháp theo driver, đúng thứ tự đọc |
| Resource | SQLException giữa `ResultSet.next()` | Đóng statement/connection, xử lý rollback |
| Resource | Pool dùng lại Connection | Không rò autoCommit/isolation/cursor giữa test |
| Performance | Dữ liệu đại diện và đồng thời | p50/p95/p99, throughput, heap, pool wait |

### 17.1. Test tính đúng phải tách khỏi test hiệu năng

- **Unit test:** kiểm tra logic mapping counts và state machine điều hướng multiple results bằng fake responses, không kết luận behavior DB thật.
- **Integration test:** chạy DB/driver thật để kiểm chứng transaction, counts, cursor, stored procedure và cleanup.
- **Performance test:** nạp dữ liệu đại diện, đo nhiều lần sau warm-up, đánh giá heap/GC/network/pool/DB và các tình huống nóng/lạnh.
- **Fault test:** mô phỏng timeout, mất kết nối và lỗi commit trong môi trường cô lập; đánh giá idempotency/outcome không rõ.

Mock chỉ phù hợp test logic Java, không thay thế phép đo cursor hay batch rewrite thật.

## 18. Hướng xử lý khi một tính năng không khả chuyển

| Yêu cầu nghiệp vụ | Fallback cần cân nhắc |
|---|---|
| Cần đọc hàng triệu hàng nhưng driver không có cursor hiệu quả | Keyset pagination, chia trang bằng SQL và checkpoint |
| `setFetchSize` không cải thiện gì | Đo baseline; điều chỉnh SQL/projection/network hoặc dùng API riêng được hỗ trợ |
| Batch rewrite không an toàn/không hỗ trợ | Batch thường với transaction hoặc chia chunk; tối ưu số round-trip theo khả năng DB |
| Cần thành công từng item khi một batch có lỗi | Validation sớm, chunk nhỏ/per-item transaction hoặc savepoint khi hỗ trợ |
| Không xác định được generated keys tương ứng item | Dùng khóa nghiệp vụ ứng dụng cấp hoặc thiết kế RETURNING/OUTPUT riêng theo dialect |
| Không hỗ trợ multiple result sets | Tách thành nhiều truy vấn hoặc dùng OUT parameters/DTO/staging phù hợp |
| Không hỗ trợ giữ nhiều ResultSet mở | Xử lý lần lượt và đóng trước `getMoreResults()` |
| Stored procedure có kết quả không nhất quán giữa DB | Tạo adapter theo dialect và chuẩn hóa DTO ở tầng repository |
| Connection pool giữ cursor/transaction quá lâu | Rút gọn đơn vị công việc, backpressure hoặc chia transaction theo trang |
| DB khác không hỗ trợ SQL test fixture | Fixture riêng theo DB, không âm thầm bỏ toàn bộ test |

Fallback không nhất thiết giữ nguyên hiệu năng. Ví dụ chuyển từ cursor dài sang nhiều trang giúp giảm thời gian giữ connection nhưng có thể thay đổi tính nhất quán khi các trang được đọc ở các transaction khác nhau. Cần mô tả **đánh đổi nghiệp vụ**, không chỉ thay API.

## 19. Bài tập thực hành

### Bài 1 — So sánh fetchSize trên hai driver

Chọn hai DB/driver được phép dùng trong môi trường thử nghiệm:

1. Ghi phiên bản, `DatabaseMetaData`, chế độ auto-commit và thuộc tính pool.
2. Nạp 100.000+ hàng vào `reading_samples` với độ dài payload khác nhau.
3. Chạy `FetchSizeProbe.scan(...)` với `fetchSize=0, 50, 200, 1000`.
4. Chạy lặp lại sau warm-up, bảo đảm số hàng và checksum giống nhau.
5. So sánh elapsed time, peak heap và số connection bị giữ; không kết luận chỉ từ `getFetchSize()`.
6. Với driver có cơ chế cursor phụ thuộc transaction, thử `autoCommit=false` trên Connection do test sở hữu.
7. Viết rõ khác biệt được quan sát và điều chưa đo được (ví dụ số round-trip nếu thiếu metric mạng).

### Bài 2 — Batch lỗi giữa chừng

Dùng fixture `jdbc_batch_probe` và input `A, B, B, C`:

1. Chạy trong một transaction, bắt `BatchUpdateException`.
2. In ra mảng counts và SQLState/vendor code **không chứa dữ liệu nhạy cảm**.
3. Rollback, đóng connection, đọc lại bằng connection mới để xác nhận vùng ID rỗng.
4. Chạy với `autoCommit=true` ở vùng ID khác, quan sát những hàng còn tồn tại.
5. Nếu driver hỗ trợ rewrite, bật/tắt cấu hình trong **môi trường test** và so sánh.
6. Giải thích tại sao kết quả các driver có thể khác dù cùng code Java.

### Bài 3 — Duyệt nhiều kết quả đúng state machine

Trên DB test, tạo procedure theo dialect trả:

- Một ResultSet liệt kê vài hàng.
- Một update count bằng 0 hoặc lớn hơn.
- Một ResultSet tổng hợp khác.

Sau đó:

1. Gọi `MultiResultReader.callReport(...)` hoặc viết adapter tương ứng.
2. Xác nhận code không dừng khi `getMoreResults() == false` nhưng `getUpdateCount() >= 0`.
3. Đóng mỗi ResultSet và kiểm tra `supportsMultipleOpenResults()` trước khi thử giữ nhiều ResultSet.
4. Ghi rõ DB/driver có phát đủ update counts theo thiết kế fixture không.
5. Thêm OUT parameter nếu DB và driver cho phép; kiểm tra thời điểm có thể đọc.

### Bài 4 — Xây ma trận portability

Viết một báo cáo gồm các cột:

```text
DB | Driver version | Feature | JDBC API |
Metadata support | Actual behavior | Result correctness |
Resource/latency observation | Fallback | Decision
```

Cho từng dòng, phân biệt **PASS**, **FAIL**, **UNSUPPORTED**, **NOT_MEASURED**. Đừng nhập kết quả giả định vào cột “Actual behavior”.

### Bài 5 — Thiết kế fallback cho truy vấn lớn

Giả sử hệ thống phải xuất 5 triệu bản ghi, nhưng DB B không có fetch theo cursor ổn định:

1. Thiết kế truy vấn keyset theo khóa có thứ tự duy nhất.
2. Chia các trang thành transaction ngắn, ghi checkpoint theo khóa cuối xử lý thành công.
3. Giải thích tính nhất quán khi dữ liệu có thể chèn/xóa/cập nhật giữa các trang.
4. Thiết kế retry/idempotency cho thao tác xuất file hoặc gửi message.
5. So sánh chi phí giữ connection với một cursor dài trên DB A.

## 20. Checklist và ghi nhớ

- **`setFetchSize()` là hint, không phải bảo đảm dùng server cursor, không phải hard limit bộ nhớ, cũng không phải số hàng tối đa của query.**
- **Đo fetch theo đúng driver và điều kiện transaction**, đặc biệt `autoCommit`, `TYPE_FORWARD_ONLY`, độ rộng hàng và cơ chế prefetch.
- **Batch không phải transaction**. Đọc update counts để chẩn đoán, nhưng kiểm tra dữ liệu sau commit/rollback bằng connection độc lập.
- **`SUCCESS_NO_INFO` và `EXECUTE_FAILED` là trạng thái**, không được cộng như số hàng; driver có thể dừng hoặc tiếp tục sau lỗi.
- **Batch rewrite, generated keys, lỗi constraint và commit outcome** phụ thuộc driver/DB, phải có integration test trên phiên bản thực.
- **`execute() == false` hay `getMoreResults() == false` không đồng nghĩa hết kết quả**; phải xem `getUpdateCount() == -1`.
- **Tiêu thụ và đóng ResultSet trước khi lấy kết quả tiếp theo** để có khả năng tương thích tốt; chỉ dùng `KEEP_CURRENT_RESULT` khi thực sự được hỗ trợ.
- **Stored procedure, nhiều statement và multiple result sets là các khái niệm khác nhau**; cú pháp và thứ tự result là đặc điểm của từng DB.
- **Đừng suy từ metadata hoặc database giả lập sang hiệu năng sản xuất**. Dùng fixture theo dialect, đo đúng DB/driver/pool, dữ liệu đại diện và cả nhánh lỗi.
- **Giữ một báo cáo ma trận có thể tái lập**: version, tính năng, cấu hình, khả năng hỗ trợ, hành vi, dữ liệu cuối, hiệu năng, fallback và quyết định triển khai.
