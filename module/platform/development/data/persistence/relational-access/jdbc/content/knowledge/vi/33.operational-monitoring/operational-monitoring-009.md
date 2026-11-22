# Chẩn đoán rò rỉ tài nguyên JDBC mà không làm tăng tải quá mức

Trong chương **Giám sát vận hành**, hệ thống Java sử dụng JDBC cần phát hiện các kết nối hoặc tài nguyên cơ sở dữ liệu không được giải phóng đúng lúc. Một `Connection` mượn từ pool nhưng không trả có thể khiến request mới chờ đến khi timeout. Một `ResultSet` lớn chưa đọc xong hoặc transaction giữ khóa lâu cũng có thể gây triệu chứng tương tự. Tuy nhiên, nếu để chẩn đoán mà bật ghi log từng câu SQL, ghi stack trace của mọi lần mượn kết nối hoặc liên tục truy vấn các bảng giám sát của DB, chính hệ thống quan sát có thể làm ứng dụng chậm thêm.

Mục tiêu là **thu đủ bằng chứng để phân biệt rò rỉ thật với thao tác hợp lệ nhưng chậm, trong khi chi phí quan sát được kiểm soát**. Bài này trình bày vòng đời `Connection`, `PreparedStatement`, `ResultSet` và luồng BLOB/CLOB; cách đọc chỉ số pool; thiết kế metric có nhãn ít biến thiên; lấy mẫu và giới hạn tốc độ log; cách dùng leak detection của pool khi cần; đối chiếu với thông tin phía DB; cùng một quy trình chẩn đoán theo mức độ thay vì bật mọi công cụ ngay từ đầu.

Các ví dụ sử dụng API JDBC chuẩn (`DataSource`, `Connection`, `PreparedStatement`, `ResultSet`) và một số ví dụ **được đánh dấu riêng cho HikariCP hoặc PostgreSQL**. Không nên coi cơ chế chẩn đoán do một thư viện hoặc một DB cung cấp là đặc tính bắt buộc của mọi driver.

## 1. “Rò rỉ tài nguyên” là gì trong một ứng dụng JDBC?

Cần phân biệt các loại tài nguyên có vòng đời liên quan nhưng không hoàn toàn giống nhau:

| Tài nguyên | Tạo hoặc mượn bằng | Khi nào nên giải phóng | Triệu chứng khi giữ sai |
| --- | --- | --- | --- |
| `Connection` | `DataSource.getConnection()` | Kết thúc đơn vị công việc sở hữu kết nối; với Spring transaction do framework quản lý | Active connection tăng, hết connection rảnh, request chờ |
| `PreparedStatement`/`Statement` | `connection.prepareStatement(...)` | Sau khi thực thi và đọc hết kết quả do statement sở hữu | Cursor, statement handle hoặc tài nguyên driver/DB tồn tại lâu |
| `ResultSet` | `executeQuery()`, `getGeneratedKeys()` | Sau khi tiêu thụ kết quả, trước khi đóng statement | Giữ cursor, bộ đệm, đôi khi giữ connection lâu |
| `InputStream`/`Reader` lấy từ LOB | `rs.getBinaryStream(...)` hoặc `getCharacterStream(...)` | Đọc xong khi `ResultSet` còn hợp lệ | Giữ phiên DB, I/O và bộ nhớ, hoặc lỗi do nguồn đóng sớm |
| Transaction | `setAutoCommit(false)` hoặc transaction manager | `commit`/`rollback` khi đơn vị nghiệp vụ kết thúc | Giữ khóa, snapshot, session `idle in transaction` |
| Tài nguyên pool/driver | Pool hoặc driver tạo và quản lý | Theo chính sách pool/driver | Nhiều kết nối vật lý, socket hoặc bộ nhớ ngoài heap |

**Rò rỉ thật (*leak*)** là đường code không giải phóng tài nguyên mà nó có trách nhiệm giải phóng. **Giữ quá lâu (*long hold*)** là tài nguyên cuối cùng vẫn được trả nhưng bị giữ lâu hơn nhu cầu hợp lý. Hai hiện tượng có thể cùng làm cạn pool nhưng cách chữa khác nhau: leak đòi sửa quyền sở hữu hoặc nhánh cleanup; long hold thường đòi thu hẹp transaction, cải thiện SQL hoặc xử lý kết quả sớm hơn.

Với pool, `Connection.close()` thường **trả connection logic** về pool, không đóng socket vật lý ngay. Pool có thể giữ connection vật lý ở trạng thái *idle* để tái sử dụng. Vì vậy, nhìn thấy nhiều session từ ứng dụng trong DB **không tự chứng minh có leak**.

### Vòng đời chuẩn và nơi dễ sai

```text
Request / job
    |
    v
DataSource.getConnection()
    |  active +1 theo cách pool đo
    v
prepareStatement -> execute -> ResultSet.next/getXxx
    |                               |
    |                               +--> có thể fetch thêm qua mạng
    |                               +--> có thể đọc luồng BLOB/CLOB
    v
close ResultSet -> close Statement -> close Connection
                                            |
                                            v
                                     trả về pool
                                     active -1
```

Đóng connection có thể khiến statement/result set liên quan không còn hợp lệ, nhưng **đừng dựa vào đóng cấp cha để bỏ qua mọi cấp con**: dùng `try-with-resources` đúng thứ tự làm trách nhiệm rõ ràng và giúp giải phóng cursor/stream sớm.

## 2. Đừng nhầm triệu chứng pool cạn với kết luận leak

Các chỉ số phổ biến trên nhiều thư viện connection pool gồm:

| Chỉ số | Ý nghĩa | Câu hỏi cần hỏi tiếp |
| --- | --- | --- |
| **Active / borrowed / in-use** | Connection hiện được ứng dụng mượn | Chúng có thuộc request đang chạy, job dài hay nhánh quên đóng? |
| **Idle / available** | Connection sẵn sàng mượn | Pool ít idle vì tải cao nhất thời hay vì bị giữ bất thường? |
| **Total** | Số connection pool đang quản lý | Có gần giới hạn cấu hình và số session DB cho phép không? |
| **Pending / awaiting** | Lượt hoặc thread đang chờ kết nối | Thời gian chờ kéo dài đến mức nào? |
| **Acquisition duration** | Thời gian lấy connection từ pool | Chậm do chờ pool, kiểm tra kết nối hay tạo kết nối vật lý? |
| **Hold/usage duration** | Thời gian từ mượn thành công đến trả | Thao tác nào giữ lâu và vì sao? |
| **Timeout/error count** | Số lần không lấy được connection hoặc lỗi JDBC | Có tăng tương ứng với active/pending không? |

Không phải pool nào cũng cung cấp cùng tên metric hoặc định nghĩa giống nhau. Một ảnh chụp `active=max`, `idle=0` trong lúc tải tăng có thể hoàn toàn bình thường. Ngược lại, **active không giảm khi request/job đã kết thúc và lưu lượng về gần 0** là tín hiệu đáng điều tra, nhưng vẫn cần xem background task, stream hoặc transaction chưa kết thúc.

### Ba dạng chuỗi thời gian minh họa

```text
A. Tăng rồi phục hồi (có thể chỉ là tải hợp lệ)
active: 1 -> 5 -> 10 -> 6 -> 1
waiting:0 -> 0 ->  3 -> 0 -> 0

B. Tăng mà không phục hồi sau khi tải ngừng (nghi leak)
active: 1 -> 3 -> 6 -> 9 -> 9 -> 9
waiting:0 -> 0 -> 1 -> 5 -> 0 -> 0

C. Giữ lâu nhưng có trả (nghi query/transaction/stream chậm)
active: 1 -> 10 -> 10 -> 10 -> 3 -> 1
hold p99: tăng mạnh trong khoảng giữa
```

Các số chỉ mô tả hình dạng, **không phải ngưỡng cảnh báo đề xuất**. Đối chiếu với throughput, request đang chạy, transaction age và thời điểm deploy. Đặc biệt, `waiting=0` khi không còn request **không phủ định** khả năng connection đã bị rò rỉ.

## 3. Quan sát theo tầng: bắt đầu bằng tín hiệu rẻ

Một thiết kế quan sát ít tốn kém thường có thứ tự:

1. **Metric tổng hợp có sẵn từ pool:** active, idle, pending, timeout; đọc theo chu kỳ vừa phải thay vì gọi mỗi hàng dữ liệu.
2. **Metric cấp thao tác JDBC:** thời gian mượn/trả, số lượng query lỗi, số lượng transaction dài; dùng tên thao tác cố định.
3. **Trace được lấy mẫu:** chỉ thu thập một tỷ lệ request hoặc những request chậm; tránh thêm span vào từng `ResultSet.next()`.
4. **Log có điều kiện và giới hạn tốc độ:** chỉ khi vượt ngưỡng giữ kết nối, xuất hiện timeout hoặc một nhóm lỗi cần điều tra.
5. **Chẩn đoán sâu có thời hạn:** stack trace nơi mượn, thread dump, số liệu DB, SQL trace ở mức giới hạn; tắt hoặc hạ mức sau khi đủ bằng chứng.

Điểm mấu chốt là **phần lớn request bình thường không cần tạo stack trace hoặc ghi log chi tiết**.

| Cơ chế | Chi phí thường gặp | Cách giảm tác động |
| --- | --- | --- |
| Đọc metric active/idle/pending từ pool | Thấp, nhưng có chi phí đồng bộ/thu thập | Lấy mẫu theo chu kỳ, không gọi trong vòng đọc từng hàng |
| Bộ đếm lỗi theo loại | Thấp nếu nhãn ổn định | Không đưa SQL/ID/raw exception vào label |
| Histogram thời gian mượn/trả | Chi phí đo đồng hồ và ghi nhận mẫu | Dùng thư viện metric hiệu quả, cấu hình bucket phù hợp |
| Log một dòng cho mọi câu SQL | Chi phí format, I/O, lưu trữ và truyền log đáng kể | Chỉ log khi chậm/lỗi, có sampling và rate limit |
| Stack trace của mọi lần `getConnection()` | Cấp phát object/CPU, áp lực GC | Chỉ bật chẩn đoán leak khi cần hoặc lấy mẫu ít |
| Truy vấn liên tục các view thống kê DB | Tăng tải và lưu lượng DB | Giới hạn tần suất, phạm vi, số hàng và thời gian chạy |
| Full tracing từng statement/row | Nhiều span và dữ liệu telemetry | Trace theo request và SQL operation, không theo row |

## 4. Sửa vòng đời tài nguyên trước khi tăng mức giám sát

Đo lường không thay thế được việc đóng tài nguyên. Trong repository tự sở hữu connection, mẫu cơ bản cần rõ ràng:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class CustomerReader {
    private final DataSource dataSource;

    public CustomerReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findEmail(long id) throws SQLException {
        String sql = "SELECT email FROM customer WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.ofNullable(rs.getString("email"));
            }
        }
    }
}
```

`ResultSet` đóng trước, tiếp đến `PreparedStatement` rồi `Connection`. Dù `executeQuery()`, `getString()` hoặc một nhánh `return` ném lỗi, `try-with-resources` vẫn cố giải phóng các tài nguyên tương ứng. Trường hợp `close()` cũng lỗi, Java giữ thông tin lỗi cleanup dưới dạng *suppressed exception* khi có lỗi chính.

**Không trả `ResultSet` còn mở ra ngoài phạm vi vừa đóng `Connection`.** Nếu cần danh sách nhỏ, ánh xạ thành DTO khi còn kết nối; nếu cần dữ liệu lớn, thiết kế streaming có vòng đời minh bạch và giám sát thời gian giữ connection. Luồng `InputStream` lấy từ `ResultSet` phải được đọc trong khi kết quả và tài nguyên JDBC liên quan còn hợp lệ.

### Với Spring JDBC thì ai đóng connection?

Trong Spring có `@Transactional`, `JdbcTemplate` hay transaction manager có thể sở hữu connection. Lúc đó, DAO **không tự `commit()`, `rollback()` hoặc `connection.close()`** trên connection được framework quản lý. Ưu tiên `JdbcTemplate`; nếu cần JDBC thuần hãy dùng cặp `DataSourceUtils.getConnection(...)` / `DataSourceUtils.releaseConnection(...)` đúng ngữ cảnh. DAO vẫn có trách nhiệm đóng statement/result set tự tạo. Việc tự đóng “để chữa leak” có thể phá giao dịch và gây lỗi mới.

## 5. Đo thời gian mượn và giữ connection mà không trace mọi câu SQL

Một phép đo đủ nhẹ cho repository thường chỉ cần **hai mốc**:

- **Acquisition duration:** từ trước `dataSource.getConnection()` đến lúc mượn thành công.
- **Hold duration:** từ lúc mượn thành công đến khi khối sở hữu đã trả connection.

`System.nanoTime()` phù hợp để đo khoảng thời gian. Dùng `System.currentTimeMillis()` khi cần timestamp lịch, không dùng làm nguồn chính cho phép đo latency.

Ví dụ sử dụng một giao diện metric nhỏ để phần truy vấn không phụ thuộc vào thư viện quan sát cụ thể:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class TimedLookup {
    public interface TimingMetrics {
        void recordAcquireNanos(String operation, long nanos);
        void recordHoldNanos(String operation, long nanos);
    }

    private final DataSource dataSource;
    private final TimingMetrics metrics;

    public TimedLookup(DataSource dataSource, TimingMetrics metrics) {
        this.dataSource = Objects.requireNonNull(dataSource);
        this.metrics = Objects.requireNonNull(metrics);
    }

    public long countCustomers() throws SQLException {
        long acquireStarted = System.nanoTime();
        Connection connection = dataSource.getConnection();
        long borrowedAt = System.nanoTime();

        try (connection) { // Java 9+: biến connection effectively final.
            // Không đưa ID/SQL thô vào label: giữ số chuỗi thời gian thấp.
            // Ghi metric bên trong try để vẫn đóng connection nếu callback lỗi.
            metrics.recordAcquireNanos(
                    "customer_count", borrowedAt - acquireStarted);
            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT COUNT(*) FROM customer");
                 ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("COUNT(*) không trả hàng");
                }
                return rs.getLong(1);
            }
        } finally {
            // Chạy sau khi try-with-resources đã gọi connection.close().
            metrics.recordHoldNanos(
                    "customer_count", System.nanoTime() - borrowedAt);
        }
    }
}
```

Giao diện `TimingMetrics` chỉ mô tả API; production cần triển khai bằng registry hoặc công cụ metrics đang sử dụng. **Bộ ghi metric phải nhanh, không block, không ném exception**, vì nếu observer thất bại nó không được làm mất kết quả JDBC hoặc che `SQLException` chính. Cũng không ghi log cho từng mẫu tại đây; để backend metric gom số lượng và phân phối thời gian.

Đây là mẫu đo **khi việc lấy connection thành công**. Nếu `getConnection()` thất bại do timeout, phép đo phải được ghi trong nhánh `catch` riêng quanh acquisition, kèm bộ đếm lỗi mượn. `hold duration` bao gồm xử lý SQL, duyệt kết quả và một phần chi phí đóng/trả connection; nó **không** phải thời gian thực thi SQL thuần.

Đối với thao tác trả nhiều hàng, có thể đo thêm một khoảng `executeQuery()` và một khoảng `ResultSet.next()/getXxx()`, nhưng chỉ tại **ranh giới thao tác**, không đo/ghi metric riêng cho mỗi hàng nếu không có lý do cụ thể. Không tính lại kích thước payload bằng cách đọc `ResultSet` thêm một lần chỉ để phục vụ telemetry.

## 6. Nhãn metric: tránh cardinality và thông tin nhạy cảm

Metric có thể rẻ lúc tạo nhưng cực kỳ đắt khi số tổ hợp nhãn tăng không giới hạn. Mỗi giá trị nhãn mới có thể sinh một chuỗi thời gian khác trong hệ thống thu thập.

| Nên dùng nhãn ít biến thiên | Không nên dùng làm nhãn |
| --- | --- |
| `operation=customer_lookup` | SQL đầy đủ chứa giá trị tham số |
| `pool=main_rw` | `connectionId` duy nhất của mỗi connection |
| `outcome=success/timeout/error` | `userId`, `tenantId`, email, số tài khoản |
| `error_category=connection/constraint/timeout/other` | Nguyên văn `SQLException.getMessage()` |
| `db_role=reader/writer` | URL JDBC chứa thông tin đăng nhập |

Nếu có 10 endpoint và mỗi endpoint gắn thêm 10.000 tenant ID, hệ thống có thể phải lưu số chuỗi thời gian lớn hơn nhiều so với chỉ theo dõi endpoint. Con số thực còn phụ thuộc số nhãn khác và cách metric backend tạo series; điều cần kiểm soát là **số giá trị khác nhau của mỗi nhãn**.

Khi cần liên kết một request cụ thể với sự cố, dùng **trace/correlation ID trong log được kiểm soát**, không đặt correlation ID thành nhãn metric. Log có thể chứa tên thao tác an toàn, thời lượng và SQLState; tránh lưu raw SQL chứa tham số hoặc nội dung ResultSet. Nếu phải thu thập câu SQL để chẩn đoán, ưu tiên fingerprint hoặc mẫu SQL đã được che dữ liệu và giới hạn thời gian lưu.

### Chiến lược mức độ quan sát

| Tín hiệu | Thu thập bình thường | Khi nghi ngờ có leak |
| --- | --- | --- |
| Active/idle/pending | Theo chu kỳ, số liệu tổng hợp | Tăng tần suất có giới hạn trong thời gian ngắn |
| Acquisition/hold histogram | Luôn bật nếu chi phí phù hợp | Phân tích p95/p99, theo tên thao tác |
| SQL error counter | Theo lớp lỗi ổn định | Đối chiếu SQLState/vendor code, không ghi dữ liệu bí mật |
| Log warning | Chỉ bất thường quan trọng | Bật log chậm có rate limit |
| Stack tại checkout | Thường tắt hoặc sampling rất thấp | Bật leak detection của pool tạm thời với ngưỡng hợp lý |
| DB session/wait inspection | Lấy mẫu định kỳ vừa phải | Truy vấn có điều kiện khi alert đang xảy ra |

**Lưu ý:** p95/p99 cần đủ mẫu đại diện. Khi lưu lượng ít, một vài mẫu rất chậm có thể làm percentile biến động; dùng thêm số lượng mẫu và bối cảnh request.

## 7. Leak detection ở pool: hữu ích nhưng không phải kết luận cuối

`DataSource` của JDBC chuẩn không định nghĩa API “bật leak detection”. Một ví dụ cụ thể là HikariCP với cấu hình `leakDetectionThreshold`, tính theo mili giây:

```java
import com.zaxxer.hikari.HikariConfig;

HikariConfig config = new HikariConfig();
config.setJdbcUrl(System.getenv("JDBC_URL"));
config.setUsername(System.getenv("DB_USER"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setMaximumPoolSize(10);
config.setConnectionTimeout(3_000);
config.setLeakDetectionThreshold(15_000); // Ngưỡng ví dụ: 15 giây.
```

Đoạn mã phụ thuộc thư viện **`com.zaxxer:HikariCP`**. Giá trị trong ví dụ chỉ để minh họa, không phải cấu hình khuyên dùng cho mọi hệ thống. HikariCP có quy tắc hợp lệ và giá trị mặc định của ngưỡng tùy phiên bản; phải kiểm tra tài liệu phiên bản đang chạy. Khi một connection được mượn quá ngưỡng, pool có thể ghi cảnh báo và stack nơi mượn; nó **không tự chứng minh connection sẽ không bao giờ được trả** và không phải cơ chế tự sửa leak.

### Chọn ngưỡng để không tạo “bão” cảnh báo

- Bắt đầu từ **phân phối hold duration bình thường** ở cùng workload, không chọn ngưỡng nhỏ tùy tiện.
- Với báo cáo/streaming hợp lệ có thời gian giữ dài, một ngưỡng chung quá thấp sẽ tạo nhiều false positive. Cần phân tích cách tách workload hoặc thu hẹp transaction.
- Dùng log có **rate limit**, thời hạn bật chẩn đoán rõ ràng, kích thước và retention phù hợp.
- Khi thấy cảnh báo, đối chiếu **thời điểm mượn, nơi mượn, thao tác đang làm và thời điểm connection được trả**. Nếu connection sau đó được trả, đó là một long hold hoặc một sự cố tạm thời chứ chưa đủ kết luận leak vĩnh viễn.
- Khi không có cảnh báo, không thể kết luận chắc chắn hệ thống không có leak: có thể ngưỡng quá cao, tính năng tắt, log bị lọc hoặc đường code chưa được chạy.

HikariCP còn cung cấp chỉ số trạng thái tức thời qua `HikariPoolMXBean`:

```java
import com.zaxxer.hikari.HikariDataSource;
import com.zaxxer.hikari.HikariPoolMXBean;

public static void inspectPool(HikariDataSource pool) {
    HikariPoolMXBean state = pool.getHikariPoolMXBean();
    if (state == null) {
        return;
    }

    System.out.printf("active=%d idle=%d total=%d waiting=%d%n",
            state.getActiveConnections(),
            state.getIdleConnections(),
            state.getTotalConnections(),
            state.getThreadsAwaitingConnection());
}
```

Đọc các getter liên tiếp **không bảo đảm ảnh chụp nguyên tử**: trạng thái có thể thay đổi giữa các lần gọi. Đây là API **HikariCP**, không ép kiểu một `DataSource` bất kỳ thành `HikariDataSource`. Trong production, dùng tích hợp JMX/metrics theo chu kỳ thay vì gọi `inspectPool` cho từng request.

## 8. Đối chiếu phía DB: hỏi ít nhưng đúng câu

Chỉ số pool cho biết connection đang bị mượn, nhưng thường không cho biết **cơ sở dữ liệu đang chờ khóa, thực thi SQL hay chỉ giữ một transaction mở**. DB có các view và công cụ theo dõi riêng; cần dùng chúng như bước đối chiếu khi dấu hiệu từ pool đã đủ mạnh.

Ví dụ PostgreSQL: xem **số lượng session theo trạng thái**, không đọc mọi SQL statement đang chạy:

```sql
-- PostgreSQL: truy vấn tổng hợp, dùng trong công cụ giám sát có phân quyền.
SELECT state,
       wait_event_type,
       COUNT(*) AS session_count
FROM pg_stat_activity
WHERE datname = current_database()
  AND backend_type = 'client backend'
GROUP BY state, wait_event_type
ORDER BY session_count DESC;
```

`pg_stat_activity` là công cụ đặc thù PostgreSQL; cột, quyền xem session khác và ngữ nghĩa trạng thái thay đổi theo phiên bản. Có thể cần quyền giám sát được cấp riêng. `state='idle'` ở DB không nhất thiết nghĩa connection đã rảnh trong pool: một request có thể đang **giữ connection nhưng chưa chạy SQL**. Ngược lại, pool idle có thể vẫn giữ session DB mở để tái sử dụng.

Nếu thấy nhiều session ở `idle in transaction`, điều tra transaction chưa kết thúc, đoạn code gọi mạng trong transaction hoặc xử lý luồng chậm. Nếu có nhiều session chờ lock, xem transaction chặn trước khi tăng pool size.

**Để tránh tăng tải quan sát:**

1. Dùng một công cụ giám sát được kiểm soát, không thực hiện query giám sát trong mỗi request nghiệp vụ.
2. Chọn bộ lọc, cột và phép tổng hợp cần thiết; tránh liên tục tải mọi câu SQL, query text, danh sách khóa hoặc stack về application.
3. Dùng chu kỳ quan sát vừa phải và chỉ tăng tạm khi có sự cố. Tần suất phải dựa trên chi phí đo và yêu cầu vận hành thực tế.
4. Không chạy `EXPLAIN ANALYZE` tùy tiện trên câu `UPDATE`/`DELETE` production để tìm leak: lệnh có thể thực thi thật và ảnh hưởng dữ liệu.
5. Tránh thao tác `pg_terminate_backend` hoặc đóng hàng loạt connection chỉ để “xóa cảnh báo” khi chưa xác minh tác động lên transaction; đây là biện pháp can thiệp cần quy trình sự cố riêng.

Không thể xác định một connection JDBC cụ thể với session DB chỉ từ số lượng active/idle; nếu cần đối chiếu chi tiết, phải dùng thông tin an toàn và cơ chế gắn dấu đã được hệ thống thiết kế từ trước.

## 9. Những nguyên nhân dễ bị gắn nhãn “leak” sai

### Truy vấn lớn, fetch theo lô và streaming

Một `SELECT` trả hàng triệu dòng có thể được đọc tăng dần bằng `ResultSet.next()`. Điều này hạn chế peak heap nếu driver hỗ trợ, nhưng giữ connection suốt thời gian đọc. `setFetchSize(...)` chỉ là **gợi ý của JDBC**, không bảo đảm driver luôn fetch theo đúng kích thước hay không đệm toàn bộ kết quả.

Nếu response HTTP gửi chậm, việc truyền BLOB từ `ResultSet.getBinaryStream()` trực tiếp ra client cũng có thể kéo dài thời gian giữ connection dù SQL đã trả về hàng đầu tiên. Khi mục tiêu là giảm thời gian mượn, cân nhắc phân trang, xử lý theo đợt hoặc sao chép dữ liệu có giới hạn ra một tầng lưu trữ phù hợp; không chuyển toàn bộ BLOB lớn sang `byte[]` chỉ để đóng DB sớm.

### Transaction dài hoặc chờ khóa

Một transaction giữ connection tới lúc `commit`/`rollback`. Trong lúc chờ một transaction khác giải phóng khóa, pool vẫn thấy connection active. Nếu query chậm do lock, tạo thêm connection có thể làm tăng cạnh tranh và khiến DB tệ hơn.

Nếu Spring quản lý transaction, connection có thể được giữ cho đến **cuối phương thức `@Transactional`**, không chỉ đến cuối lời gọi `JdbcTemplate.update()`. Giảm phạm vi transaction khi nghiệp vụ cho phép; đừng tự `commit` hoặc `close` connection do Spring sở hữu.

### Batch lớn và xử lý CPU/I/O ngoài DB

`executeBatch()` lớn có thể giữ statement, transaction và connection lâu. Vòng lặp N+1 truy vấn nhiều lần cũng giữ connection dài dù mỗi câu SQL nhanh. Trong trường hợp khác, code mượn connection rồi gọi HTTP API bên ngoài hoặc tạo file PDF trước khi thực sự cần SQL. Tách các phần việc không cần DB khỏi phạm vi connection, nhưng vẫn bảo toàn tính nguyên tử và idempotency của nghiệp vụ.

### Task bất đồng bộ hoặc lỗi hủy tác vụ

Một task bị cancel, timeout hoặc ném exception ở nhánh hiếm có thể bỏ qua cleanup nếu không dùng `try-with-resources`/`finally`. Không chia sẻ một connection đang có transaction giữa thread và callback không đồng bộ một cách tùy tiện. Hãy xác định người **sở hữu quyền đóng** ngay từ lúc mượn tài nguyên.

## 10. Runbook: từ cảnh báo nhẹ đến phân tích sâu có thời hạn

Một quy trình phù hợp production không bắt đầu bằng việc bật toàn bộ debug log:

| Mức | Điều kiện kích hoạt | Hành động với chi phí có kiểm soát |
| --- | --- | --- |
| **0 – Bình thường** | Pool và DB ổn định | Metric tổng hợp, histogram mượn/giữ, error count |
| **1 – Nghi ngờ** | Active cao kéo dài, pending/timeout tăng | Xem baseline, request concurrency, hold p95/p99, transaction age |
| **2 – Khoanh vùng** | Xác định một workload hoặc khoảng thời gian gây nghẽn | Bật lấy mẫu trace/log chậm có lọc và rate limit; đối chiếu DB wait/lock |
| **3 – Chẩn đoán sâu** | Vẫn chưa biết điểm mượn bị giữ | Tạm bật leak detection/stack sampling của pool, lấy thread dump giới hạn |
| **4 – Xác minh sửa lỗi** | Đã sửa vòng đời/query/transaction | Kiểm thử hồi quy, so sánh metric trước/sau, tắt log chẩn đoán bổ sung |

**Ở mỗi mức cần ghi lại bằng chứng trước khi chuyển mức cao hơn**: khi nào xảy ra, workload nào, mức tải bao nhiêu, cấu hình pool, phiên bản driver/DB, số connection đang mượn, thời gian chờ và thời gian giữ. Không cần thu thập dữ liệu của tất cả request để trả lời từng câu hỏi.

### Quy trình chi tiết

1. **Xác nhận cảnh báo có thật:** nhìn chuỗi thời gian, số mẫu và đường cơ sở; tránh báo động từ một snapshot ngẫu nhiên.
2. **Phân biệt chờ mượn và giữ lâu:** acquisition tăng hay hold tăng? Có đang tạo connection vật lý hoặc DB mất kết nối không?
3. **Tìm thao tác nổi bật:** dùng tên operation cố định, không cần lưu raw SQL hay thông tin khách hàng.
4. **Tìm nguyên nhân SQL hay ngoài SQL:** đo `execute` và thời gian đọc `ResultSet`; đối chiếu lock/wait và DB query plan khi cần.
5. **Khoanh vùng nhánh cleanup:** xem return sớm, exception, timeout, cancel, stream chưa đọc hết, nested transaction và worker bất đồng bộ.
6. **Chỉ nâng mức chẩn đoán tạm thời:** cấu hình ngưỡng phù hợp, giới hạn số log/trace, ghi rõ cách hoàn nguyên cấu hình.
7. **Sửa tại nguồn:** trả connection đúng quyền sở hữu, đóng statement/result set, rút ngắn transaction, tối ưu truy vấn hoặc điều chỉnh công suất dựa trên đo đạc.
8. **Xác minh sau sửa:** khi hết tải, active trở về mức hợp lý, waiting/timeout giảm, không xuất hiện lỗi transaction hoặc tăng CPU/GC/log volume.

Trong sự cố nghiêm trọng, ưu tiên bảo toàn dữ liệu và tính đúng đắn của transaction. Khởi động lại service có thể giải phóng connection bị giữ, nhưng **không giải quyết được đường code gây leak**; sự cố có thể tái diễn khi tải trở lại.

## 11. Kiểm thử leak có giới hạn, không làm ảnh hưởng môi trường thật

Có thể kiểm tra khả năng phát hiện và dọn tài nguyên trong **môi trường test độc lập** với pool nhỏ (ví dụ 2 connection) và thời gian chờ ngắn:

1. **Trường hợp đúng:** chạy nhiều lần repository dùng `try-with-resources`; sau khi tất cả task kết thúc, active phải về mức không có connection đang mượn nếu không có job nền khác.
2. **Trường hợp SQLException:** cố ý sử dụng SQL không hợp lệ trong test; bảo đảm statement/connection vẫn được đóng khi exception được ném.
3. **Trường hợp long hold:** giữ connection trong một thời gian ngắn có kiểm soát, sau đó đóng trong `finally`. Xem cảnh báo ngưỡng và xác nhận active giảm sau khi kết thúc.
4. **Trường hợp quên đóng mô phỏng:** một test cố ý giữ connection cho tới lúc quan sát pending/acquisition timeout, rồi **luôn đóng những connection đó trong finally**. Không để test “rò rỉ thật” tồn tại sau khi hoàn tất.
5. **Trường hợp khóa DB:** hai transaction cập nhật cùng hàng để mô phỏng chờ lock; đặt timeout và rollback, không để CI treo vô hạn.
6. **Trường hợp LOB/stream:** thử đọc dữ liệu lớn chậm, đo hold time và peak heap; phân biệt long hold hợp lệ với quên đóng stream.
7. **So overhead quan sát:** chạy cùng bài tải một lần với metric cơ bản, một lần với leak detection có giới hạn; so latency p95/p99, CPU, GC, số log/s và lượng telemetry.

### Ví dụ cố ý giữ connection, nhưng luôn dọn trong test

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public static void simulateLongHold(DataSource dataSource)
        throws SQLException, InterruptedException {
    try (Connection connection = dataSource.getConnection()) {
        // Chỉ dùng trong test cô lập; không sleep với Connection ở production.
        Thread.sleep(1_500);
    } // Connection được trả về pool dù có InterruptedException.
}
```

Nếu đặt ngưỡng cảnh báo lớn hơn 1,5 giây, test này có thể **không** phát sinh cảnh báo: cần chọn thời gian/threshold của môi trường kiểm thử một cách hợp lệ, không suy ra rằng logic leak detection không hoạt động. Dùng `CountDownLatch` và timeout cho bài kiểm tra đồng thời; hạn chế test phụ thuộc `Thread.sleep(...)` khi cần ổn định trên CI.

**Không bật thử nghiệm rò rỉ cố ý trên production**: chỉ vài request giữ connection cũng có thể khiến người dùng thật gặp timeout. Không chụp full heap hoặc thread dump hàng loạt theo mỗi request; công cụ này có tác động tài nguyên và phải được vận hành theo quy trình riêng.

## 12. Dấu hiệu chẩn đoán sai và cách sửa

| Kết luận vội | Vì sao sai | Cách kiểm chứng tốt hơn |
| --- | --- | --- |
| “Active bằng max là leak” | Pool có thể đang phục vụ tải hợp lệ | Xem load, pending, hold duration và khả năng phục hồi |
| “DB có 50 session nên rò rỉ 50 connection” | Pool giữ kết nối vật lý idle | So trạng thái pool với session DB và chính sách pool |
| “Leak warning chắc chắn không có close” | Ngưỡng chỉ xác định hold quá lâu | Xem connection có được trả sau cảnh báo không |
| “Không thấy cảnh báo nghĩa là không leak” | Chẩn đoán có thể tắt hoặc ngưỡng quá cao | Xem active sau khi hết tải, test nhánh lỗi |
| “`rs.next()` chậm là do Java” | Driver có thể fetch dữ liệu qua mạng tại `next()` | Tách SQL/fetch/network/CPU khi có đủ bằng chứng |
| “Tăng pool size giải quyết leak” | Chỉ trì hoãn cạn pool hoặc làm DB quá tải | Sửa ownership, query và transaction trước |
| “Bật log mọi SQL để tìm lỗi” | Tạo thêm I/O, lộ dữ liệu và nhiễu | Log lỗi/chậm có rate limit, metrics/trace sampling |
| “Đóng Connection ngay khi DAO kết thúc là luôn đúng” | Spring có thể sở hữu transaction | Dùng `JdbcTemplate` hoặc `DataSourceUtils.releaseConnection` |
| “Tăng polling DB sẽ phát hiện chắc hơn” | Chính polling làm DB chịu thêm tải | Tăng tạm thời có giới hạn, lọc và tổng hợp |
| “Một metric gắn tenant ID giúp dễ tìm vấn đề” | Cardinality tăng mạnh | Dùng operation/pool cố định; tra correlation ID ở log bảo mật |

## 13. Bài thực hành: lập kế hoạch giám sát có chi phí đo được

Giả sử dịch vụ JDBC có ba workload: `customer_lookup` (ngắn), `daily_report` (trả nhiều hàng) và `attachment_download` (đọc BLOB). Pool dùng một triển khai có metrics active/idle/pending; application có hệ thống log và dashboard.

1. **Liệt kê tài nguyên:** ở mỗi workload, ai gọi `getConnection()`, ai đóng, có `ResultSet`/LOB stream nào sống lâu hơn phương thức truy vấn không?
2. **Xây baseline:** thu thập active/idle/pending và histogram acquisition/hold, theo ba tên operation cố định. Không gắn tenant/user ID.
3. **Phân biệt tính chất:** `customer_lookup` có thể giữ connection ngắn; `daily_report` và `attachment_download` có thể giữ lâu do fetch/streaming. Đừng dùng một ngưỡng “có leak” tùy ý cho cả ba.
4. **Thêm log có điều kiện:** chỉ ghi khi thời gian giữ vượt ngưỡng đã nghiên cứu, hoặc khi timeout. Giới hạn log/s và tránh SQL parameter, credential, dữ liệu khách hàng.
5. **Tạo ca lỗi trong test:** cố ý ném `SQLException` ở giữa xử lý và xác nhận active trở lại mức ban đầu sau khi task kết thúc.
6. **Đo overhead:** so CPU, GC, latency và telemetry volume trước/sau khi bật metrics, trace sampling hoặc leak detection. Nếu chi phí quan sát đáng kể, hạ tần suất hoặc phạm vi.
7. **Đối chiếu DB khi có dấu hiệu:** kiểm tra transaction age/lock wait trong khoảng có pending tăng, không chạy truy vấn giám sát liên tục trong request.
8. **Kiểm tra Spring ownership nếu có:** DAO dùng `JdbcTemplate`/`DataSourceUtils` không tự `close()` connection mà framework quản lý.
9. **Viết runbook:** nêu ngưỡng vào từng mức chẩn đoán, người phụ trách, nơi lưu bằng chứng, cách tắt chẩn đoán sâu và tiêu chí hoàn tất sự cố.

**Câu hỏi tự kiểm tra:**

- Vì sao một cảnh báo leak detection có thể là long hold chứ không phải connection không bao giờ được trả?
- Số connection vật lý ở DB có luôn bằng số connection active trong pool không?
- Tại sao gọi `System.nanoTime()` cho hai mốc borrow/return thường rẻ hơn ghi stack trace cho mọi lần mượn?
- Khi nào `ResultSet.next()` có thể đang chờ DB/mạng chứ không phải CPU Java?
- Vì sao đưa `tenantId` vào nhãn metric dễ tăng tải hệ thống giám sát?
- Nếu dùng Spring `@Transactional`, tại sao “sửa leak” bằng `connection.close()` trực tiếp có thể gây lỗi nghiêm trọng?
- Khi gặp pool timeout, bạn cần bằng chứng nào trước khi quyết định tăng pool size?
- Vì sao phải đo cả overhead của chính công cụ quan sát trong bài test?

**Ghi nhớ:** Để chẩn đoán rò rỉ JDBC hiệu quả, hãy **bắt đầu từ vòng đời tài nguyên đúng và metric tổng hợp rẻ**, phân biệt **leak thật** với **connection bị giữ lâu**, rồi chỉ nâng mức quan sát khi có bằng chứng. Đo acquisition/hold, xem active/idle/pending, dùng nhãn ít biến thiên, sampling và rate limit log; chỉ bật stack-based leak detection hoặc truy vấn giám sát DB sâu **có thời hạn và phạm vi rõ**. Đừng để việc tìm nguyên nhân làm tăng CPU, heap, I/O, tải database hoặc rò rỉ dữ liệu nhiều hơn chính sự cố cần xử lý.
