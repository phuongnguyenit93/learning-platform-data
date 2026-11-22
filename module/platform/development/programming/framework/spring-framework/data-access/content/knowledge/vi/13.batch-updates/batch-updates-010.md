# Kiểm chứng lợi ích batch với trình điều khiển JDBC thực tế

> **Bối cảnh:** Spring Framework Data Access → Cập nhật theo lô (batch updates). Trọng tâm là **đo và kiểm chứng** lợi ích của batch với cơ sở dữ liệu và JDBC driver thật, thay vì mặc định rằng gọi `batchUpdate()` sẽ nhanh hơn trong mọi điều kiện.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt việc gom lệnh tại tầng Spring/JDBC với tối ưu hoá thực tế của trình điều khiển và máy chủ cơ sở dữ liệu.
2. Thiết kế phép đo công bằng giữa `executeUpdate()` từng dòng, `executeBatch()` theo nhóm và batch có bật tuỳ chọn tối ưu của driver.
3. Chạy thí nghiệm có thể lặp lại trên **PostgreSQL thật + pgJDBC**, kiểm tra dữ liệu sau mỗi lượt, đo tổng thời gian bao gồm `COMMIT` và tính thông lượng/tỷ lệ tăng tốc.
4. Đưa kết quả trở lại một luồng `JdbcTemplate.batchUpdate(...)` trong Spring và giải thích khi nào batch có ích, khi nào không.
5. Nhận biết các sai số đo, giới hạn kích thước batch, tác động của transaction, ràng buộc dữ liệu và kiểu đếm số dòng do JDBC trả về.

## 2. Batch đang tối ưu điều gì?

Với cùng câu SQL tham số hoá, hai cách gửi dữ liệu khác nhau:

- **Từng dòng:** chuẩn bị cùng một `PreparedStatement`, gán tham số rồi gọi `executeUpdate()` N lần.
- **JDBC batch:** gán tham số, gọi `addBatch()` N lần và gửi theo từng nhóm bằng `executeBatch()`. Spring `JdbcTemplate.batchUpdate()` xây trên khả năng này.
- **Driver rewrite:** một số driver nhận ra batch `INSERT ... VALUES (?, ?)` và chuyển thành ít câu `INSERT ... VALUES (...), (...), ...` lớn hơn. Đây là tối ưu **phụ thuộc driver, cấu hình và dạng SQL**; batch không tự đồng nghĩa với một câu SQL duy nhất.

Luồng cần quan sát:

```text
Ứng dụng/Spring JDBC
       │
       ├─ 10 000 lần update() / executeUpdate()
       │         hoặc
       └─ nhiều addBatch() → executeBatch() theo nhóm
                         ↓
                   JDBC driver
                   (có/không rewrite)
                         ↓
                   Giao thức mạng
                         ↓
                 PostgreSQL thực tế
                 (parse/plan/execute/WAL/index/commit)
```

Batch thường giảm overhead gọi lệnh và giao tiếp với DB; driver có thể gom hoặc pipeline các lệnh, nên **không được suy ra chính xác số round trip chỉ từ số lần gọi API**. Nếu thời gian bị chi phối bởi kiểm tra ràng buộc, index, trigger, I/O, lock hoặc WAL, lợi ích có thể nhỏ. Batch quá lớn cũng có thể tăng bộ nhớ, thời gian giữ transaction và chi phí khi lỗi. Mục tiêu bài này là **đo trên đúng driver/workload**, rồi mới quyết định.

## 3. Thiết kế phép đo có đối chứng

Dùng một workload **10 000 bản ghi INSERT** có cùng cấu trúc, một bảng và cùng khoá chính; tất cả bản ghi được tạo **trước khi bắt đầu bấm giờ**. Đo ba cấu hình chính:

| Kịch bản | Cách gọi tại ứng dụng | `reWriteBatchedInserts` của pgJDBC | Ý nghĩa |
| --- | --- | --- | --- |
| A | `PreparedStatement.executeUpdate()` từng dòng | `false` | Mốc gốc có tái sử dụng prepared statement |
| B | `addBatch()/executeBatch()`, 500 dòng/nhóm | `false` | Hiệu quả của JDBC batch khi chưa rewrite |
| C | Như B, cùng 500 dòng/nhóm | `true` | Hiệu quả cộng thêm khi pgJDBC rewrite được INSERT |

Đối chiếu A và B **trong cùng một lần chạy với cờ `false`**; đối chiếu B và C giữa hai lần chạy giống hệt nhau ngoại trừ cờ driver. Có thể đo thêm A trong lần chạy `true` để chắc chắn baseline ổn định. Việc so sánh phải thoả các điều kiện:

- **Cùng phiên bản PostgreSQL, pgJDBC, JVM, cấu trúc bảng, chỉ mục, dữ liệu, số hàng, SQL, máy chủ, mạng và số luồng**. Ghi lại các phiên bản; một kết quả của localhost không đại diện cho DB qua mạng có độ trễ lớn.
- **Cùng phạm vi transaction:** cả hai cách ghi dùng `autoCommit=false`, mỗi workload có một lần `COMMIT`. Không so sánh 10 000 lần tự động commit với một batch có một commit rồi kết luận chênh lệch chỉ do batch.
- Cả hai cách dùng **một connection**, tái sử dụng **một `PreparedStatement`** cho workload; thời gian đo gồm tạo/đóng statement và `COMMIT`, nhưng không gồm khởi tạo dữ liệu, `TRUNCATE` hoặc truy vấn kiểm chứng.
- Có lượt **warm-up**, nhiều lượt đo, thay phiên thứ tự A/B, dùng **median** thay vì chọn lượt nhanh nhất. Đảm bảo không có tác vụ khác đang tải DB.
- Sau **mỗi** lượt, kiểm tra số bản ghi, tổng khoá và giá trị payload đúng; lỗi dữ liệu hoặc exception phải khiến lượt đo thất bại thay vì được ghi nhận là nhanh.
- Ghi riêng `batchSize`, tuỳ chọn driver và kích thước dữ liệu. Không đánh đồng benchmark đơn luồng này với throughput toàn ứng dụng khi nhiều request cùng ghi DB.

Công thức:

```text
elapsed_ms   = (endNano - startNano) / 1_000_000
throughput   = số dòng đã xác minh / (elapsed_ms / 1_000)
speedup      = median_ms(baseline) / median_ms(candidate)
```

`speedup > 1` cho biết candidate nhanh hơn baseline trong điều kiện thí nghiệm; `speedup < 1` là chậm hơn. Đây là **kết quả đo theo môi trường**, không phải thuộc tính bảo đảm của `batchUpdate()`.

## 4. Thí nghiệm chạy được: PostgreSQL + pgJDBC + Java 17+

### 4.1. Khởi động cơ sở dữ liệu thật

Yêu cầu: JDK 17+, Docker, công cụ tải tệp và một PostgreSQL JDBC driver. Ví dụ dùng PostgreSQL 16 trong container cục bộ; cổng `54329` giúp tránh trùng cổng 5432 của máy phát triển.

```bash
docker run --rm -d --name pg-batch-lab \
  -e POSTGRES_DB=batch_lab \
  -e POSTGRES_USER=lab \
  -e POSTGRES_PASSWORD=labpass \
  -p 54329:5432 postgres:16

docker exec pg-batch-lab pg_isready -U lab -d batch_lab
```

Chỉ chạy benchmark khi `pg_isready` báo chấp nhận kết nối. Nếu không dùng Docker, trỏ JDBC URL tới một PostgreSQL thử nghiệm riêng, có quyền tạo bảng và `TRUNCATE`; **không chạy lệnh này trên dữ liệu sản xuất**.

Trong thư mục thực hành riêng, tải bản pgJDBC đã xác minh trên Maven Central:

```bash
curl -L -o postgresql-42.7.7.jar https://repo.maven.apache.org/maven2/org/postgresql/postgresql/42.7.7/postgresql-42.7.7.jar
```

Mã Java sau chỉ dùng `java.sql` tại thời điểm biên dịch. JAR pgJDBC cần nằm trên **runtime classpath** để `DriverManager` tìm được driver.

### 4.2. Chương trình đo đầy đủ

Lưu vào tệp `BatchProbe.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public class BatchProbe {
    private static final int ROWS = 10_000;
    private static final int CHUNK = 500;
    private static final int WARMUPS = 2;
    private static final int ROUNDS = 8;

    private static final String INSERT =
            "INSERT INTO batch_probe(id, payload) VALUES (?, ?)";

    record Item(int id, String payload) {}

    private static List<Item> createItems() {
        List<Item> items = new ArrayList<>(ROWS);
        for (int id = 1; id <= ROWS; id++) {
            items.add(new Item(id, "item-" + id));
        }
        return items;
    }

    private static void createTable(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("""
                CREATE TABLE IF NOT EXISTS batch_probe (
                    id INTEGER PRIMARY KEY,
                    payload VARCHAR(100) NOT NULL
                )
                """);
        }
        connection.commit();
    }

    private static void resetTable(Connection connection) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute("TRUNCATE TABLE batch_probe");
        }
        connection.commit();
    }

    private static void checkCounts(int[] counts, int expected)
            throws SQLException {
        if (counts.length != expected) {
            throw new SQLException("Wrong batch count length: " + counts.length);
        }
        for (int count : counts) {
            // Rewritten INSERT may report SUCCESS_NO_INFO (-2).
            if (count != 1 && count != Statement.SUCCESS_NO_INFO) {
                throw new SQLException("Unexpected batch update count: " + count);
            }
        }
    }

    private static void verifyRows(Connection connection, int size)
            throws SQLException {
        String sql = """
            SELECT COUNT(*),
                   COALESCE(SUM(id), 0),
                   COUNT(*) FILTER (WHERE payload <> 'item-' || id)
            FROM batch_probe
            """;
        try (Statement statement = connection.createStatement();
             ResultSet resultSet = statement.executeQuery(sql)) {
            if (!resultSet.next()) {
                throw new SQLException("No aggregate result");
            }
            long count = resultSet.getLong(1);
            long sumIds = resultSet.getLong(2);
            long mismatchedPayload = resultSet.getLong(3);
            long expectedSum = (long) size * (size + 1) / 2;
            if (count != size || sumIds != expectedSum
                    || mismatchedPayload != 0) {
                throw new SQLException("Data verification failed: count="
                        + count + ", sumIds=" + sumIds
                        + ", badPayload=" + mismatchedPayload);
            }
        }
        connection.commit();
    }

    private static long run(Connection connection, List<Item> items,
                            boolean batched) throws SQLException {
        // Reset có commit riêng; không tính vào thời gian insert.
        resetTable(connection);
        long started = System.nanoTime();
        try (PreparedStatement statement =
                     connection.prepareStatement(INSERT)) {
            int pending = 0;
            for (Item item : items) {
                statement.setInt(1, item.id());
                statement.setString(2, item.payload());

                if (batched) {
                    statement.addBatch();
                    pending++;
                    if (pending == CHUNK) {
                        checkCounts(statement.executeBatch(), pending);
                        pending = 0;
                    }
                } else {
                    if (statement.executeUpdate() != 1) {
                        throw new SQLException("Single insert affected != 1");
                    }
                }
            }
            if (batched && pending > 0) {
                checkCounts(statement.executeBatch(), pending);
            }
            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            connection.rollback();
            throw ex;
        }
        long elapsed = System.nanoTime() - started;
        verifyRows(connection, items.size()); // Ngoài thời gian đo.
        return elapsed;
    }

    private static double median(List<Long> nanos) {
        List<Long> sorted = new ArrayList<>(nanos);
        Collections.sort(sorted);
        int middle = sorted.size() / 2;
        return sorted.size() % 2 == 0
                ? (sorted.get(middle - 1) + sorted.get(middle)) / 2.0
                : sorted.get(middle);
    }

    public static void main(String[] args) throws Exception {
        String url = System.getenv().getOrDefault(
                "DB_URL", "jdbc:postgresql://localhost:54329/batch_lab");
        String user = System.getenv().getOrDefault("DB_USER", "lab");
        String password = System.getenv().getOrDefault(
                "DB_PASSWORD", "labpass");

        List<Item> items = createItems(); // Trước khi đo.
        List<Long> singles = new ArrayList<>();
        List<Long> batches = new ArrayList<>();

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {
            connection.setAutoCommit(false);
            System.out.println("Driver: "
                    + connection.getMetaData().getDriverName() + " "
                    + connection.getMetaData().getDriverVersion());
            if (!connection.getMetaData().supportsBatchUpdates()) {
                throw new IllegalStateException("Driver has no JDBC batch support");
            }

            createTable(connection);

            for (int round = 0; round < WARMUPS + ROUNDS; round++) {
                boolean batchFirst = round % 2 == 0;
                long first = run(connection, items, batchFirst);
                long second = run(connection, items, !batchFirst);

                if (round >= WARMUPS) {
                    if (batchFirst) {
                        batches.add(first);
                        singles.add(second);
                    } else {
                        singles.add(first);
                        batches.add(second);
                    }
                }
            }
        }

        double singleMs = median(singles) / 1_000_000.0;
        double batchMs = median(batches) / 1_000_000.0;
        System.out.printf(Locale.ROOT,
                "single median: %.2f ms%n", singleMs);
        System.out.printf(Locale.ROOT,
                "batch  median: %.2f ms%n", batchMs);
        System.out.printf(Locale.ROOT,
                "single throughput: %.0f rows/s%n", ROWS * 1_000.0 / singleMs);
        System.out.printf(Locale.ROOT,
                "batch  throughput: %.0f rows/s%n", ROWS * 1_000.0 / batchMs);
        System.out.printf(Locale.ROOT,
                "batch speedup: %.2fx%n", singleMs / batchMs);
    }
}
```

**Vì sao mã này công bằng hơn so sánh ngây thơ?** Cả hai nhánh tái sử dụng `PreparedStatement`, chạy một transaction cho 10 000 insert, có cùng dữ liệu và cùng `COMMIT`. Mỗi lượt được xoá bảng trước khi đo để tránh vi phạm khoá chính. Chương trình kiểm tra dữ liệu đã commit, bao gồm giá trị payload, **trước khi chấp nhận thời gian đo**. Mỗi cặp A/B đảo thứ tự; median lấy từ tám lượt đo sau hai lượt warm-up. Các tham số `ROWS`, `CHUNK`, `WARMUPS`, `ROUNDS` có thể thay đổi để khảo sát trường hợp khác.

Lệnh biên dịch và chạy trong **PowerShell/Windows** (dùng dấu `;` trong Java classpath):

```powershell
javac --release 17 BatchProbe.java

$env:DB_USER = 'lab'
$env:DB_PASSWORD = 'labpass'

# A so với B: JDBC batch, chưa bật rewrite
$env:DB_URL = 'jdbc:postgresql://localhost:54329/batch_lab?reWriteBatchedInserts=false'
java -cp '.;postgresql-42.7.7.jar' BatchProbe

# Đo lại với cùng dữ liệu, cùng chương trình: C
$env:DB_URL = 'jdbc:postgresql://localhost:54329/batch_lab?reWriteBatchedInserts=true'
java -cp '.;postgresql-42.7.7.jar' BatchProbe
```

Trên Linux/macOS, dấu phân cách classpath là `:` thay cho `;`, và biến môi trường có thể khai báo bằng `export`. Tên tệp và tên lớp `BatchProbe` phải khớp. Dòng `Driver: ...` là bằng chứng chương trình thực sự dùng pgJDBC, không dùng driver nhúng như H2. Những dòng `single median`, `batch median`, `throughput`, `speedup` là **số đo thực tế của lần chạy**, không có stdout thời gian cố định để sao chép. Ví dụ này là benchmark minh hoạ thao tác và phương pháp đo; nếu cần đánh giá ở quy mô sản xuất, còn phải đo trên hạ tầng và dữ liệu đại diện.

Dọn môi trường thử nghiệm khi xong:

```bash
docker stop pg-batch-lab
```

### 4.3. Đọc kết quả theo ba tầng

1. Nếu **B nhanh hơn A**, cơ chế gom batch của JDBC/driver có ích với workload này dù chưa dùng rewrite.
2. Nếu **C nhanh hơn B**, cờ `reWriteBatchedInserts=true` đang bổ sung lợi ích cho dạng `INSERT` tương thích. Đừng quy toàn bộ lợi ích của C cho Spring: cả benchmark ở trên đều dùng JDBC thuần.
3. Nếu **không chênh lệch rõ**, xem độ trễ mạng, giới hạn I/O/WAL, index/trigger, CPU DB, trạng thái bộ đệm, tải song song, kích thước mỗi bản ghi và khả năng driver thực sự tối ưu dạng SQL đó. Cần lặp lại và xem độ phân tán thay vì khẳng định batch vô ích từ một lượt.

Với pgJDBC, `reWriteBatchedInserts` mặc định là `false`; tuỳ chọn này có thể chuyển **compatible INSERT VALUES** thành multi-values INSERT. Nó **không phải cơ chế rewrite chung cho UPDATE/DELETE** và có các ngoại lệ như `RETURNING`/lấy generated keys. Khi bật rewrite, `executeBatch()` có thể trả `Statement.SUCCESS_NO_INFO` (`-2`) thay vì một số dòng chính xác cho từng phần tử. **Không cộng các số âm vào tổng số dòng đã ghi**; kết quả phải được kiểm chứng riêng trong DB.

## 5. Đưa phép đo về Spring `JdbcTemplate`

Bài học ở tầng JDBC kiểm chứng hành vi driver; ứng dụng Spring thường gọi `JdbcTemplate`. Đo thêm vòng Spring để biết hiệu quả **end-to-end của mã thực tế**. Trong một ứng dụng đã có `spring-jdbc` và `DataSource` PostgreSQL, lớp sau có hai lối ghi cùng dữ liệu, cùng transaction. Đây là lớp có thể biên dịch trong dự án Spring; phần đo/chuẩn bị bảng áp dụng như mục 4, không đưa vào lớp này.

```java
import java.sql.Statement;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringBatchWriter {
    public record Item(int id, String payload) {}

    private static final String INSERT =
            "INSERT INTO batch_probe(id, payload) VALUES (?, ?)";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public SpringBatchWriter(DataSource dataSource) {
        this.jdbc = new JdbcTemplate(dataSource);
        this.transaction = new TransactionTemplate(
                new DataSourceTransactionManager(dataSource));
    }

    public void writeSeparately(List<Item> items) {
        transaction.executeWithoutResult(status -> {
            for (Item item : items) {
                jdbc.update(INSERT, item.id(), item.payload());
            }
        });
    }

    public void writeInBatches(List<Item> items) {
        transaction.executeWithoutResult(status -> {
            int[][] counts = jdbc.batchUpdate(
                    INSERT,
                    items,
                    500,
                    (ps, item) -> {
                        ps.setInt(1, item.id());
                        ps.setString(2, item.payload());
                    });
            for (int[] oneBatch : counts) {
                for (int count : oneBatch) {
                    if (count == Statement.EXECUTE_FAILED) {
                        throw new IllegalStateException(
                                "A JDBC batch entry failed");
                    }
                }
            }
        });
    }
}
```

**Cơ chế:** overload `JdbcTemplate.batchUpdate(sql, Collection<T>, int batchSize, ParameterizedPreparedStatementSetter<T>)` tự chia danh sách thành các batch tối đa 500 phần tử và trả `int[][]` (mỗi nhóm một mảng update counts). Biến thể `batchUpdate(sql, BatchPreparedStatementSetter)` trả `int[]` và thường dùng khi tự kiểm soát số phần tử. Spring có thể **fallback thành nhiều update riêng** nếu driver báo không hỗ trợ JDBC batch; chỉ thấy API Spring được gọi **chưa đủ** để kết luận mạng/DB nhận batch được tối ưu.

`TransactionTemplate` ở cả hai nhánh bảo đảm một transaction được commit khi callback thành công, rollback khi ném runtime exception. Nếu dùng `@Transactional` thay thế, cần gọi qua Spring proxy; việc cùng một bean tự gọi phương thức của chính nó có thể bỏ qua interceptor transaction. Đừng đo một nhánh dùng transaction Spring và nhánh kia dùng auto-commit riêng từng dòng.

Khi benchmark hai phương thức này, hãy tạo/khởi động `ApplicationContext`, `DataSource`, pool và dữ liệu **trước** khoảng thời gian đo; gọi từ một thành phần bên ngoài; xóa bảng và kiểm tra lại dữ liệu sau từng lượt. So sánh `writeSeparately` với `writeInBatches` là **đo hiệu quả ở tầng Spring**, khác với đối chứng JDBC thuần ở mục 4 (Spring còn chi phí tạo statement, ánh xạ tham số và tiện ích abstraction).

Nếu dùng `NamedParameterJdbcTemplate.batchUpdate()`, mỗi dòng nhận `SqlParameterSource`, chẳng hạn `SqlParameterSourceUtils.createBatch(items.toArray())`; vẫn cần kiểm chứng driver và transaction. Với tham số `null`, nên truyền JDBC type rõ ràng khi driver cần, vì tra cứu `ParameterMetaData` có thể thêm round trip; Spring 6.1.2+ có tối ưu đặc biệt cho PostgreSQL và MS SQL Server ở đường xử lý này.

## 6. Thu thập bằng chứng ở tầng driver và DB

`supportsBatchUpdates() == true` chỉ chứng minh driver công bố **hỗ trợ JDBC batch**, chưa chứng minh rằng INSERT được gộp thành một câu SQL. Kết hợp nhiều lớp quan sát:

| Lớp | Quan sát phù hợp | Điều có thể kết luận |
| --- | --- | --- |
| Ứng dụng | Median wall-clock, throughput, kết quả kiểm chứng, lỗi/rollback | Lợi ích nhìn từ người gọi |
| JDBC | Phiên bản driver, URL/cấu hình, `supportsBatchUpdates()`, `updateCounts` | Driver nào đang chạy, hỗ trợ và kết quả batch |
| PostgreSQL | Thống kê truy vấn, số lần gọi/độ trễ phía server, lock/WAL/I/O, slow query log trong môi trường thử nghiệm | Có giảm tải/đổi dạng SQL ở server hay chi phí bị đẩy sang nơi khác |
| Mạng (khi được phép) | Trace giao thức hoặc proxy quan sát số thông điệp, bytes và thời gian | Bằng chứng mức giao thức; tránh suy luận chỉ từ log Java |

Nếu bật extension `pg_stat_statements` trong môi trường thử nghiệm, hãy so sánh SQL chuẩn hoá, `calls` và `total_exec_time` trước/sau. Với rewrite, cùng một INSERT logic có thể xuất hiện dưới **nhiều dạng số tuple VALUES**, nên **không chỉ xem một dòng thống kê**. Đo chỉ số `pg_stat_statements` cần quyền và cấu hình DB thích hợp; không bắt buộc cho bài benchmark tự chạy ở mục 4.

Nếu dùng MySQL Connector/J, tuỳ chọn tương ứng là `rewriteBatchedStatements=true`, nhưng điều kiện kích hoạt và hành vi của nó **khác pgJDBC**. Không áp dụng tên cờ của PostgreSQL cho MySQL/MariaDB/Oracle/SQL Server, và không mặc định cùng một SQL được rewrite trên mọi driver. Kiểm chứng phiên bản, tài liệu driver, số liệu và SQL thực nhận ở từng hệ quản trị.

## 7. Thử nghiệm thay đổi kích thước batch

Giữ N và transaction cố định, thay `CHUNK` lần lượt, ví dụ **1, 50, 100, 500, 1 000, 5 000**. Batch size 1 là phép kiểm tra điều kiện biên hữu ích; size càng lớn không nhất thiết càng nhanh. Sau khi sửa `CHUNK`, chạy lại đủ lượt warm-up/measurement, kiểm tra dữ liệu rồi ghi median và throughput cho **từng** mức.

Một số tác động cần diễn giải:

- Nhóm nhỏ: nhiều lần `executeBatch()` hơn, overhead lặp cao hơn nhưng ít tham số/bộ nhớ tồn đọng.
- Nhóm vừa: thường cân bằng overhead và chi phí bộ nhớ; nên tìm vùng lợi ích chững lại.
- Nhóm quá lớn: tăng bộ nhớ client, kích thước gói/lệnh, thời gian giữ lock, rủi ro timeout và xử lý lỗi. pgJDBC còn có giới hạn tham số giao thức khi tạo multi-values INSERT; driver tự quyết định nhóm rewrite hợp lệ.
- Batch gồm nhiều loại SQL không đồng nhất hoặc cần trả kết quả cho từng dòng có thể khiến tối ưu của driver bị vô hiệu.
- Với lô lớn, thiết kế **chunk + transaction boundary** theo yêu cầu nguyên tử; tách commit theo chunk thay đổi semantics khi gặp lỗi, nên phải đo và mô tả riêng, không ghép chung bảng so sánh transaction một lần.

Không chọn batch size chỉ từ bảng đo trên máy dev. Kích thước payload, index, mạng, số kết nối đồng thời và SLO của ứng dụng đều có thể đổi điểm tối ưu.

## 8. Tính đúng đắn và xử lý lỗi

Batch không thay đổi yêu cầu bảo toàn dữ liệu:

1. **Update counts:** JDBC dùng `Statement.SUCCESS_NO_INFO = -2` khi thành công nhưng không biết số dòng; `Statement.EXECUTE_FAILED = -3` chỉ ra thất bại ở vị trí tương ứng nếu driver tiếp tục xử lý. Số đếm không thay thế được truy vấn kiểm chứng dữ liệu.
2. **BatchUpdateException:** với một mục bị lỗi (ví dụ trùng khoá), driver có thể dừng hoặc tiếp tục các mục còn lại tuỳ DB/driver. `getUpdateCounts()` chỉ là manh mối về phần đã thử; cần quyết định rollback toàn transaction hay chiến lược retry/idempotency trước khi triển khai.
3. **Transaction:** trong ví dụ, một mục thất bại gây rollback toàn lượt. Nếu code bắt exception rồi vẫn commit, có thể lưu trạng thái một phần; không dùng benchmark để biện minh thay đổi tính nguyên tử.
4. **Ràng buộc và trigger:** kiểm chứng số hàng, nội dung cột, duplicate handling, thứ tự tác dụng nếu workload phụ thuộc thứ tự; đừng giả định `INSERT ... ON CONFLICT` hoặc generated keys trả kết quả giống nhau khi rewrite.
5. **Tài nguyên:** với dữ liệu đầu vào rất lớn, không giữ vô hạn phần tử trong RAM. Xử lý theo các chunk hữu hạn; theo dõi heap, kết nối pool, timeout, số giao dịch mở và phản ứng của DB.
6. **Tính lặp lại:** dữ liệu trong bảng phải được reset trước mỗi lượt; nếu đổi index/constraint, hardware, network, driver, pool size hoặc isolation level thì đó là một thí nghiệm **mới**.

Phép đo thành công khi đáp ứng đồng thời **đúng dữ liệu + thời gian có thể lặp lại + mô tả cấu hình**. Một chương trình kết thúc nhanh nhưng thiếu bản ghi hoặc chỉ đo thời gian gọi `addBatch()` mà không tính `executeBatch()/COMMIT` là kết quả không hợp lệ.

## 9. Chẩn đoán khi “batch không nhanh hơn”

| Hiện tượng | Giả thuyết cần kiểm tra | Phép kiểm tra |
| --- | --- | --- |
| A và B gần như giống nhau | DB ở cùng máy; chi phí thực thi/index chiếm ưu thế; driver không tạo lợi ích đáng kể | Đo DB qua mạng thử nghiệm có độ trễ đại diện, quan sát DB CPU/WAL và throughput |
| B cải thiện, C không thêm nhiều | Cấu trúc SQL không đủ điều kiện rewrite; batch bị giới hạn bởi I/O/constraint | Xác nhận đúng URL và pgJDBC; thử INSERT VALUES đơn giản như demo; xem thống kê SQL |
| C nhanh hơn nhưng update counts có `-2` | Rewrite làm mất số dòng chính xác cho từng entry | Dùng `COUNT`/kiểm chứng dữ liệu; xử lý `SUCCESS_NO_INFO` đúng |
| Batch size càng lớn càng chậm | Độ lớn statement/heap, lock, chi phí DB, quá nhiều tham số | Quét nhiều mức batch size và theo dõi tài nguyên |
| Lượt đầu chậm, các lượt sau nhanh | JIT, connection warm-up, buffer/cache, khởi tạo statement/DB | Warm-up, lặp lại, đảo thứ tự, thống kê median |
| Spring loop rất chậm còn JDBC loop ít chậm | Vòng Spring có overhead tạo statement, binding hoặc lấy connection; transaction/pool chưa đồng nhất | Đo JDBC thuần riêng và vòng Spring riêng, bảo đảm cùng connection/transaction |
| Lỗi trùng khoá hoặc thiếu dòng | Không reset đúng bảng, dữ liệu trùng, transaction/retry sai | Rollback và xác minh `COUNT`, checksum/nội dung, log nguyên nhân |

## 10. Tiêu chí hoàn thành và bài tự thực hành

Một báo cáo benchmark có thể kiểm chứng cần chỉ rõ: DB và driver thực tế cùng phiên bản; SQL/schema/index; số dòng và payload; `autoCommit` và số lần commit; loại phép đo và giới hạn thời gian; `batchSize`, cờ rewrite; số lượt warm-up và lượt đo; median, throughput, speedup; kết quả kiểm chứng dữ liệu; nhận định có điều kiện theo môi trường.

Tự thực hành theo thứ tự: (1) chạy A/B với rewrite `false`, (2) chạy B/C với rewrite `true`, (3) thay `CHUNK` thành 50, 100, 1 000, (4) thêm một index phụ hoặc thay kích thước payload và **đo lại**, (5) thử cố tình chèn một khoá trùng để quan sát rollback/exception, rồi (6) tái hiện hai phương pháp ghi bằng `SpringBatchWriter`. Mỗi thay đổi chỉ nên điều chỉnh một biến để hiểu vì sao kết quả khác trước.

**Kết luận kỹ thuật cần rút ra từ dữ liệu:** batch là một chiến lược giảm overhead có điều kiện; lợi ích cuối cùng phụ thuộc **mã gọi, transaction, driver, dạng SQL, cấu hình DB và workload**. Chỉ tối ưu khi phép đo trên driver thật chứng minh được cải thiện trong khi dữ liệu vẫn đúng.

## Nguồn tham khảo

- Spring Framework, *JDBC Batch Operations*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework, `JdbcTemplate` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- pgJDBC, *Initializing the Driver* (tham số `reWriteBatchedInserts`): https://jdbc.postgresql.org/documentation/use/
- pgJDBC, *Batch INSERT rewriting* (điều kiện rewrite và `updateCounts`): https://vlsi.github.io/pgjdbc/documentation/query/batch-inserts/
- Java SE, `Statement.executeBatch()`, `SUCCESS_NO_INFO`, `EXECUTE_FAILED`: https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html
- MySQL Connector/J, *Configuration Properties*: https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html
