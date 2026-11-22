# Đo thời gian mượn kết nối, thực thi và ánh xạ kết quả trong JDBC

## 1. Vì sao cần tách thời gian trong một lời gọi JDBC?

Một API Java dùng JDBC có thể mất 500 ms để trả về dữ liệu, nhưng điều đó **không có nghĩa câu SQL chạy trên database trong 500 ms**. Độ trễ quan sát từ ứng dụng có thể đến từ nhiều đoạn:

1. **Mượn kết nối (connection acquisition):** chờ pool cấp một `Connection` hoặc tạo kết nối vật lý khi không có pool.
2. **Chuẩn bị và gửi truy vấn:** tạo `PreparedStatement`, gắn tham số, gửi lệnh và nhận phản hồi đầu tiên.
3. **Lấy dữ liệu (fetch/iteration):** JDBC driver đọc các hàng từ server, đợi mạng và di chuyển con trỏ `ResultSet`.
4. **Đọc cột và ánh xạ (mapping):** chuyển kiểu dữ liệu JDBC thành kiểu Java, tạo DTO/entity, thêm vào collection.
5. **Đóng tài nguyên và xử lý tiếp:** đóng `ResultSet`/statement, trả kết nối về pool, xử lý nghiệp vụ hoặc tạo HTTP response.

~~~mermaid
flowchart LR
    A[API nhận request] --> B[DataSource.getConnection]
    B --> C[prepare + bind + execute]
    C --> D[ResultSet.next]
    D --> E[getXXX + tạo DTO]
    E --> D
    E --> F[close + trả Connection]
    F --> G[Trả response]
~~~

Trong **JDBC (Java Database Connectivity)**, `Connection`, `PreparedStatement` và `ResultSet` là các API chuẩn để Java tương tác với cơ sở dữ liệu quan hệ. Driver và hệ quản trị cơ sở dữ liệu quyết định bao nhiêu công việc thực hiện ở mỗi lời gọi, nên đo từng đoạn có ý nghĩa thực tế hơn việc đặt đồng hồ quanh duy nhất `executeQuery()`.

**Mục tiêu:** Xây dựng phép đo có thể lặp lại để xác định thời gian đang mất ở kết nối, thực thi câu lệnh hay đọc/ánh xạ kết quả, rồi dùng bằng chứng để chọn bước tối ưu tiếp theo.

## 2. Những mốc thời gian và chỉ số cần thu thập

| Chỉ số | Bắt đầu | Kết thúc | Diễn giải |
| --- | --- | --- | --- |
| **Borrow time** | Ngay trước `DataSource.getConnection()` | Ngay sau khi lấy được `Connection` | Thời gian ứng dụng đợi kết nối, bao gồm đợi pool và có thể bao gồm tạo kết nối mới. |
| **Execute-call time** | Trước `prepareStatement`, bind tham số và `executeQuery` | Ngay khi `executeQuery()` trả `ResultSet` | Thời gian thiết lập và thực hiện lời gọi SQL ban đầu; không bảo đảm đã tải hết hàng. |
| **Time to first row** | Ngay trước chuẩn bị/thực thi SQL | Sau `next()` đầu tiên trả về một hàng | Độ trễ từ bắt đầu câu SQL đến lúc ứng dụng thấy hàng đầu tiên. |
| **Next/fetch time** | Trước mỗi `ResultSet.next()` | Sau mỗi `ResultSet.next()` | Tổng thời gian tiến con trỏ; có thể chứa đợi mạng và giải mã dữ liệu. |
| **Read + mapping time** | Trước `getLong`, `getString`, tạo đối tượng | Sau khi thêm đối tượng kết quả | Thời gian đọc cột, chuyển kiểu, cấp phát đối tượng và phần ánh xạ của ứng dụng. |
| **End-to-end JDBC time** | Trước khi mượn kết nối | Sau khi đóng toàn bộ tài nguyên JDBC | Độ trễ trọn đoạn truy cập dữ liệu, bao gồm khoảng trống và chi phí đóng tài nguyên. |

Lưu ý ba điểm:

- **Thời gian thực thi SQL trên server khác với thời gian `executeQuery()` ở client.** Thời gian ở client còn phụ thuộc gửi/nhận mạng, driver và cách fetch. Muốn xem riêng server, cần dữ liệu từ công cụ theo dõi DBMS hoặc execution plan thực tế.
- **Không tồn tại ranh giới fetch/mapping hoàn toàn thống nhất giữa mọi driver.** Một số driver lấy trước nhiều hàng khi `executeQuery()`; một số lấy theo lô khi `next()`; đọc cột qua `getXXX()` cũng có thể kích hoạt giải mã hoặc tải dữ liệu. Vì vậy, tên chỉ số “Next/fetch” và “Read + mapping” mô tả **đoạn lời gọi quan sát được** chứ không cam kết phân rã tuyệt đối thời gian CPU, database và mạng.
- **Thời gian mượn kết nối không đồng nghĩa thời gian tạo kết nối vật lý.** Nếu pool đang có kết nối rảnh, `getConnection()` có thể trả rất nhanh; nếu pool hết chỗ, phép đo chủ yếu phản ánh thời gian chờ.

### 2.1. Dùng đồng hồ nào?

Trong cùng một tiến trình Java, dùng `System.nanoTime()` để tính **khoảng thời gian**:

~~~java
long started = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - started;
double elapsedMillis = elapsedNanos / 1_000_000.0;
~~~

`System.nanoTime()` dành cho đo elapsed time và không bị thay đổi bởi việc điều chỉnh đồng hồ hệ thống như `System.currentTimeMillis()`. Nó **không bảo đảm phép đo chính xác đến từng nanosecond**: độ phân giải thực tế còn phụ thuộc nền tảng và bản thân việc đọc đồng hồ có chi phí. Không dùng giá trị `nanoTime()` như timestamp để so giữa các máy; khi cần mốc log theo ngày giờ, sử dụng đồng hồ wall-clock riêng.

## 3. Ví dụ Java: đo từng giai đoạn của một truy vấn

Giả sử hệ thống có bảng `app_user(id, name)` và `DataSource` đã được cấu hình đúng với driver JDBC. Ví dụ dưới đây dùng **Java 17+**, chỉ import API chuẩn Java/JDBC và nhận `DataSource` từ ứng dụng; bạn không cần chọn một pool cụ thể để dùng phép đo.

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public final class JdbcStageTimer {
    private JdbcStageTimer() {}

    public record UserRow(long id, String name) {}

    public record Metrics(
            long borrowNanos,
            long executeNanos,
            long firstRowNanos,  // -1 nếu truy vấn không có hàng nào
            long nextNanos,
            long mappingNanos,
            long totalNanos,
            int rowCount) {}

    public record Observation(List<UserRow> rows, Metrics metrics) {}

    public static Observation measure(
            DataSource dataSource, long fromId, long toId)
            throws SQLException {

        final String sql = """
                SELECT id, name
                FROM app_user
                WHERE id BETWEEN ? AND ?
                ORDER BY id
                """;

        List<UserRow> rows = new ArrayList<>();
        long borrowNanos = 0;
        long executeNanos = 0;
        long firstRowNanos = -1;
        long nextNanos = 0;
        long mappingNanos = 0;

        long totalStarted = System.nanoTime();
        try (Connection connection = dataSource.getConnection()) {
            borrowNanos = System.nanoTime() - totalStarted;

            // Bao gồm prepare, bind và execute trong thời gian gọi SQL.
            long queryStarted = System.nanoTime();

            try (PreparedStatement ps = connection.prepareStatement(sql)) {
                ps.setLong(1, fromId);
                ps.setLong(2, toId);

                try (ResultSet rs = ps.executeQuery()) {
                    executeNanos = System.nanoTime() - queryStarted;

                    while (true) {
                        long nextStarted = System.nanoTime();
                        boolean hasRow = rs.next();
                        long nextFinished = System.nanoTime();

                        nextNanos += nextFinished - nextStarted;

                        if (!hasRow) {
                            break;
                        }
                        if (firstRowNanos < 0) {
                            firstRowNanos = nextFinished - queryStarted;
                        }

                        long mappingStarted = System.nanoTime();

                        long id = rs.getLong(1);
                        String name = rs.getString(2);
                        rows.add(new UserRow(id, name));

                        mappingNanos += System.nanoTime() - mappingStarted;
                    }
                }
            }
        } // Đã đóng ResultSet, PreparedStatement và Connection.

        long totalNanos = System.nanoTime() - totalStarted;
        Metrics metrics = new Metrics(
                borrowNanos,
                executeNanos,
                firstRowNanos,
                nextNanos,
                mappingNanos,
                totalNanos,
                rows.size());

        return new Observation(List.copyOf(rows), metrics);
    }

    public static double millis(long nanos) {
        return nanos / 1_000_000.0;
    }
}
~~~

Cách sử dụng khi đã có `dataSource`:

~~~java
JdbcStageTimer.Observation observation =
        JdbcStageTimer.measure(dataSource, 1_000L, 1_499L);

JdbcStageTimer.Metrics m = observation.metrics();

System.out.printf(
        "rows=%d, borrow=%.2f ms, execute=%.2f ms, " +
        "firstRow=%.2f ms, next=%.2f ms, map=%.2f ms, total=%.2f ms%n",
        m.rowCount(),
        JdbcStageTimer.millis(m.borrowNanos()),
        JdbcStageTimer.millis(m.executeNanos()),
        m.firstRowNanos() < 0
                ? -1.0
                : JdbcStageTimer.millis(m.firstRowNanos()),
        JdbcStageTimer.millis(m.nextNanos()),
        JdbcStageTimer.millis(m.mappingNanos()),
        JdbcStageTimer.millis(m.totalNanos()));
~~~

**Cách hiểu và giới hạn của ví dụ:**

- `borrowNanos` chỉ đo `getConnection()`; nó không tính thời gian xây dựng `DataSource` hay khởi động pool.
- `executeNanos` đo cả tạo statement, bind tham số và gọi `executeQuery()`; trong ví dụ này, không tách từng bước nhỏ vì mục tiêu là phân biệt ba nhóm nguyên nhân chính.
- `firstRowNanos` tính **từ lúc bắt đầu câu SQL**, nên có thể bao gồm phần `executeNanos`. Đây là **chỉ số chồng lấn**, không cộng nó với các giai đoạn khác để ra tổng.
- `nextNanos` tính cả lần `next()` cuối cùng trả về `false`. Giá trị này bao gồm chi phí duyệt con trỏ và fetch tùy driver.
- `mappingNanos` bao gồm `getXXX()`, tạo `UserRow` và thêm vào `ArrayList`. Phần `List.copyOf(rows)` chạy sau khi kết thúc đo `totalNanos`, vì đây là thao tác tạo kết quả trả về của ví dụ. Nếu muốn đo toàn bộ repository method, đặt đồng hồ ở tầng gọi bao trùm cả thao tác này.
- `totalNanos` gồm thời gian đóng tài nguyên do `try-with-resources` thực hiện. Tổng của các stage đo chi tiết có thể nhỏ hơn `totalNanos` do các đoạn chưa được bấm giờ.
- Ví dụ trả về mọi hàng khớp khoảng ID đã chỉ định. Trên dữ liệu lớn, nên giới hạn phạm vi theo nghiệp vụ hoặc dùng phân trang ở server; tránh tải không giới hạn chỉ để benchmark.

**Lưu ý về lỗi:** Đoạn mã minh họa trả exception cho người gọi; nếu `getConnection()` hoặc `executeQuery()` thất bại, nó chưa xuất bản một mẫu metrics thành công. Ở production, đặt instrumentation trong `try/finally` để ghi cả thời gian thất bại và phân loại `outcome` phù hợp, trong khi vẫn đóng tài nguyên và giữ nguyên exception.

## 4. Đọc kết quả phép đo mà không nhầm lẫn

Giả sử một lần chạy cho ra các số **minh họa**:

| Chỉ số | Giá trị |
| --- | ---: |
| Mượn kết nối | 3 ms |
| Prepare/bind/execute | 6 ms |
| Thời gian đến hàng đầu tiên | 15 ms |
| Tổng thời gian gọi `ResultSet.next()` | 24 ms |
| Đọc cột và ánh xạ | 8 ms |
| Tổng JDBC tính cả đóng tài nguyên | 44 ms |
| Số hàng | 500 |

Từ số liệu đó có thể nói:

- Pool cấp kết nối trong 3 ms ở **lần đo này**; không có dấu hiệu chờ lớn trong riêng mẫu đó.
- Phần gọi `executeQuery()` mất 6 ms, nhưng truy vấn và tải hàng **chưa chắc đã kết thúc** ở thời điểm trả `ResultSet`.
- `next()` cộng dồn 24 ms; đây là hướng điều tra quan trọng nếu truy vấn trả nhiều hàng hoặc driver fetch theo lô.
- `firstRow=15 ms` đo từ lúc bắt đầu câu SQL, **đã bao gồm `execute=6 ms`** nên không cộng thêm 15 ms vào tổng.
- 8 ms ánh xạ cho 500 hàng là quan sát trong bối cảnh dữ liệu này. Nếu số hàng tăng gấp nhiều lần thì tổng thời gian ánh xạ cũng có thể tăng dù mỗi hàng xử lý nhanh.

**Cảnh báo về tổng thời gian:** `borrow + execute + next + mapping` chỉ là gần đúng của những đoạn đã bấm giờ, còn `firstRow` chồng lên `execute` và `next`. Không cộng tất cả cột rồi kết luận stopwatch sai. Nếu tổng dao động, trước hết xem các khoảng thời gian chưa được đo, số hàng thực tế và tác động của garbage collection/luồng khác.

### 4.1. Phân biệt độ trễ và lưu lượng

Hai truy vấn có cùng 50 ms nhưng một truy vấn trả 2 hàng, truy vấn kia trả 10.000 hàng thì tính chất hiệu năng khác nhau. Bên cạnh latency, ghi **row count**, kích thước dữ liệu (nếu có thể đo một cách an toàn), loại tác vụ và số truy vấn cho mỗi request.

Tham số chẩn đoán hữu ích:

~~~text
mapping_time_per_row ≈ mappingNanos / rowCount  (nếu rowCount > 0)
next_time_per_row    ≈ nextNanos / rowCount     (ước lượng thô)
queries_per_request  = số lần gọi truy vấn của một request
rows_per_request     = tổng số hàng xử lý của request
~~~

Phép chia theo số hàng chỉ giúp so sánh workload tương tự; nó **không biến next time thành chính xác “thời gian mạng trên mỗi hàng”**. Một `next()` có thể lấy cả lô hàng còn nhiều lần kế tiếp chỉ đọc buffer.

## 5. Đo trong môi trường có connection pool

`DataSource.getConnection()` của một pool (ví dụ HikariCP) thường trả về một **logical/proxy connection**. Khi gọi `close()`, ứng dụng thông thường trả connection cho pool để tái sử dụng. Cần tách ba khái niệm:

| Phép đo | Ý nghĩa |
| --- | --- |
| **Acquire/borrow latency** | Request chờ đến khi `getConnection()` trả về, kể cả chờ pool. |
| **Connection usage/hold time** | Khoảng thời gian từ lúc mượn cho đến lúc trả kết nối, gồm SQL, mapping và thao tác Java khi còn giữ `Connection`. |
| **Physical connection creation** | Thời gian TCP/TLS/xác thực và khởi tạo session DB khi pool thực sự tạo connection mới. |

Một borrow time cao có thể do pool hết kết nối rảnh, connection bị giữ quá lâu, truy vấn tốn thời gian hoặc DB chấp nhận kết nối mới chậm. Chỉ nhìn một con số không phân biệt được các nguyên nhân trên.

Khi quan sát pool, theo dõi thêm các chỉ số do **pool thực tế cung cấp**: tổng kết nối, active, idle, số luồng đang pending, timeout khi mượn và thời gian giữ kết nối. Kiểm tra tên metric trong phiên bản thư viện/registry đang dùng; không giả định mọi pool phát ra cùng tên.

Nếu request vừa thực hiện I/O bên ngoài vừa giữ connection, usage time có thể cao dù execute time ngắn. Giải pháp có thể là **rút ngắn phạm vi giữ `Connection`**, không nhất thiết phải tăng kích thước pool. Việc tăng pool quá mức còn có thể tăng áp lực lên DB server.

## 6. Thu thập nhiều mẫu với Micrometer hoặc OpenTelemetry

Bấm giờ bằng `System.nanoTime()` phù hợp khi phân tích cục bộ. Để theo dõi lâu dài, cần chuyển kết quả sang **timer/histogram** hoặc **trace span** có gắn nhãn hữu ích.

Ví dụ một wrapper dùng Micrometer, giả sử `Timer` đã được đăng ký trước và dùng lại:

~~~java
import io.micrometer.core.instrument.Timer;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

public static Connection borrowMeasured(
        DataSource dataSource, Timer borrowTimer) throws SQLException {
    long started = System.nanoTime();
    try {
        return dataSource.getConnection();
    } finally {
        borrowTimer.record(
                System.nanoTime() - started,
                TimeUnit.NANOSECONDS);
    }
}
~~~

Wrapper ghi lại cả lần mượn thất bại; tuy nhiên, nếu muốn biết tỉ lệ lỗi, nên ghi thêm counter/tag `outcome=success|failure` ở tầng instrumentation tương ứng. Một `Timer` có thể được tạo ở lúc cấu hình ứng dụng và tái sử dụng; không cần xây metric mới trong từng request.

Với trace, có thể dùng các span mang tên tác vụ như `db.borrow`, `db.execute`, `db.iterate`, `db.map` để thấy đường đi của một request. Nếu hệ thống đã bật tự động instrumentation cho JDBC hoặc pool, **kiểm tra các span/metric có sẵn trước**, tránh đo trùng làm tăng overhead và khó hiểu số liệu.

Các nhãn nên có số lượng giá trị hữu hạn: tên **tác vụ logic** (`findUsers`, `loadOrders`), pool, loại DBMS, kết quả thành công/lỗi, môi trường. **Không dùng nguyên câu SQL chứa dữ liệu, literal ID, username, URL kèm secret hay request ID làm label**; chúng làm tăng cardinality, phí lưu trữ và có thể lộ dữ liệu.

### 6.1. Vì sao phải xem p50, p95, p99?

Một con số trung bình che được các request cực chậm. Với mỗi loại thao tác, nên xem:

- **p50 (median):** một nửa số mẫu nhanh hơn hoặc bằng giá trị này.
- **p95:** khoảng 95% số mẫu nhanh hơn hoặc bằng giá trị này; 5% còn lại chậm hơn.
- **p99:** gần nhóm chậm nhất, hữu ích để nhận biết timeout/pool contention bất thường.

Lưu ý số liệu percentile cần **đủ mẫu trong khoảng quan sát**, cách xuất histogram được thiết lập phù hợp, và tập request có tính chất tương đồng. Không kết luận từ p99 của một nhóm chỉ có vài mẫu. Ghi cùng số mẫu, tỉ lệ lỗi, throughput và phân bố row count để tránh diễn giải sai.

## 7. Quy trình benchmark giúp kết quả đáng tin

Một quy trình có thể lặp lại gồm các bước:

1. **Chọn workload đại diện.** Cố định phiên bản Java, driver, database, schema/index, dữ liệu và tham số SQL; tách tác vụ trả ít hàng và nhiều hàng.
2. **Khởi động trước khi đo.** Cho JIT, class loading và pool khởi tạo trong một giai đoạn warm-up. Nếu mục tiêu là hiệu năng khởi động lạnh, hãy đo riêng cold-start.
3. **Giữ ổn định cấu hình.** Ghi pool size, query timeout, fetch size, transaction mode, cấu hình TLS, số request đồng thời và mức tải cơ sở dữ liệu.
4. **Thu thập nhiều mẫu.** Đo theo từng loại query, ở nhiều mức concurrency, cùng tỉ lệ lỗi; xuất latency histogram/p50/p95/p99, không chỉ một kết quả đẹp nhất.
5. **So sánh có kiểm soát.** Chỉ đổi **một yếu tố mỗi lần**, chẳng hạn fetch size, giới hạn số hàng hoặc cách map; đo lại với cùng workload.
6. **Đối chiếu với phía database.** Nếu execute/fetch lớn, xem query plan, scan, lock wait, I/O, buffer cache và các chỉ số server tương ứng.
7. **Kiểm tra tác động end-to-end.** Một tối ưu giảm mapping time nhưng tăng memory allocation, khiến GC tăng và p99 request xấu đi, chưa chắc là cải thiện toàn hệ thống.

**Warm cache và cold cache:** Truy vấn đầu tiên có thể chậm vì buffer cache, page cache, statement compilation hoặc connection setup. Chỉ so sánh kết quả của hai môi trường khi đã ghi điều kiện cache rõ ràng. Không trộn kết quả cold-start với steady-state rồi dùng một giá trị trung bình.

**Kiểm soát tính công bằng:** Nếu so sánh hai driver, dùng cùng phiên bản database, cùng JDK, workload, cấu hình fetch/pool/TLS và điều kiện cache. Khác biệt hiệu năng của một bản driver không tự động áp dụng cho các bản hay loại truy vấn khác.

## 8. Diễn giải các dạng kết quả thường gặp

| Quan sát | Giả thuyết cần kiểm tra | Hướng điều tra có căn cứ |
| --- | --- | --- |
| **Borrow p95 cao**, execute thấp | Pool chờ vì hết kết nối rảnh; giữ connection lâu; tạo connection mới chậm. | Quan sát active/idle/pending, timeout, hold time; kiểm tra ranh giới transaction và DB connection limit. |
| **Execute-call cao** | Query plan tốn kém, chờ lock, network round-trip hoặc server trả kết quả đầu muộn. | Dùng DB tracing/query statistics, kiểm tra execution plan và lock wait; thử query chỉ trả một ít hàng. |
| **Execute thấp nhưng next/fetch cao** | Server/driver truyền dữ liệu theo lô, mạng chậm, hàng nhiều hoặc fetch size chưa phù hợp. | Đếm hàng/bytes, thử fetch size với cùng workload, quan sát mạng và thời gian nhận từng lô. |
| **Mapping cao theo số hàng** | Chuyển kiểu, khởi tạo object, reflection, format ngày/giờ, giải mã LOB/JSON hoặc GC. | Profile CPU/allocation; kiểm tra cách gọi `getXXX()`, DTO và số trường được đọc. |
| **Total cao hơn nhiều tổng các đoạn** | Có nhiều chi phí chưa bấm giờ: close, transaction, logic khác, log đồng bộ, GC hoặc thread scheduling. | Bổ sung timer riêng cho khoảng còn thiếu; kiểm tra traces/profiler. |
| **Latency một request cao nhưng từng query ngắn** | Nhiều lời gọi JDBC tuần tự (mẫu N+1), xử lý nghiệp vụ/serialization hoặc gọi dịch vụ khác. | Đếm queries/request; đo repository method và request end-to-end. |
| **Chỉ p99 tăng khi concurrency cao** | Pool contention, DB saturation, GC hoặc lock khi tải tăng. | Tăng tải theo bước, đối chiếu queue/pending, CPU, lock, throughput và lỗi timeout. |

Không sửa bằng cách tăng `maximumPoolSize` hoặc tăng `fetchSize` theo cảm tính: một thay đổi có thể đẩy nghẽn từ ứng dụng sang DB server, tăng RAM hoặc làm một nhóm truy vấn khác chậm đi.

## 9. Fetch size, lượng dữ liệu và cách ánh xạ

`PreparedStatement.setFetchSize(int)` cung cấp **gợi ý** về số hàng driver nên lấy trong một lần tương tác, nhưng hành vi thực tế phụ thuộc driver, DBMS, transaction và thuộc tính connection. Không giả định gọi `setFetchSize(100)` sẽ luôn làm driver lấy chính xác 100 hàng mỗi round-trip.

~~~java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setFetchSize(100); // Gợi ý; cần xác minh trên driver thực tế.
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc và xử lý từng hàng.
        }
    }
}
~~~

Một số lựa chọn ảnh hưởng cả fetch và mapping:

- **Chỉ SELECT các cột cần thiết**, thay vì `SELECT *`. Ít bytes trên mạng và ít giá trị cần chuyển kiểu.
- **Dùng phân trang/giới hạn ở server** theo cú pháp DBMS khi nghiệp vụ chỉ cần một phần kết quả.
- **Tránh tạo nhiều đối tượng trung gian** hoặc dùng reflection nặng trong vòng lặp lớn khi profiler cho thấy đó là nút thắt.
- **Xử lý dữ liệu theo luồng** khi cần duyệt lượng hàng lớn và driver hỗ trợ; hiểu rõ việc `ResultSet` và transaction có thể phải giữ mở suốt thời gian xử lý.
- **Cẩn trọng với LOB và giá trị lớn**: thời gian đọc `getBytes()`, `getBinaryStream()` hoặc chuyển đổi JSON có thể chứa I/O và cấp phát lớn; không gọi tất cả là “CPU mapping”.
- **Giữ fetch size, kiểu ResultSet và transaction mode nhất quán** giữa các lượt benchmark; một số driver có cách streaming khác nhau khi auto-commit bật/tắt.

Ví dụ, nếu 200.000 hàng được kéo về ứng dụng chỉ để đếm chúng, nên cân nhắc có thể dùng `SELECT COUNT(*)` (theo đúng điều kiện nghiệp vụ) thay vì tối ưu vòng lặp Java. Đo đạc có mục tiêu để biết **lượng dữ liệu cần truyền** cũng quan trọng như tốc độ của mapper.

## 10. Những lỗi đo đạc dễ gây kết luận sai

### 10.1. Chỉ đo `executeQuery()`

~~~java
long start = System.nanoTime();
ResultSet rs = ps.executeQuery();
long sqlMillis = (System.nanoTime() - start) / 1_000_000;
// Đọc hàng ở nơi khác mà không đo.
~~~

Đoạn này chỉ phản ánh thời gian trả về `ResultSet`. Với driver fetch dần, phần lớn thời gian truy vấn có thể xuất hiện ở `rs.next()`/`rs.getXXX()`. Cách khắc phục là bấm giờ đến khi **đã đọc xong kết quả**, rồi tách nhỏ nếu cần.

### 10.2. Đo mỗi hàng nhưng quên chi phí instrumentation

Hai lần gọi `nanoTime()`, cập nhật biến đếm và ghi log trong từng hàng có thể làm sai phép đo khi mapping cực nhanh. Để khảo sát ban đầu, đo **toàn bộ vòng lặp**:

~~~java
long started = System.nanoTime();
int count = 0;
while (rs.next()) {
    consumeRow(rs);
    count++;
}
long iterationAndMappingNanos = System.nanoTime() - started;
~~~

Sau khi phát hiện vòng lặp đáng kể, mới bật đo chi tiết `next` và `mapping` trên **một tỉ lệ request nhỏ** để xác định thành phần. Không log từng hàng ở production. Các phép đo chi tiết cũng khiến dữ liệu không hoàn toàn tương đương với request không được đo.

### 10.3. Không đo hoặc không đóng khi xảy ra exception

Một lời gọi `getConnection()` timeout có thể tạo ra **mẫu chậm quan trọng nhất**, nhưng cách viết chỉ ghi metric trên nhánh thành công sẽ bỏ mất nó. Dùng `try/finally` để record thời gian đã trôi qua và phân loại lỗi; dùng `try-with-resources` để đóng đúng `ResultSet`, `Statement` và `Connection`. Nếu bỏ sót `close()`, pool có thể cạn kết nối và làm méo toàn bộ lần benchmark sau.

### 10.4. Đổ mọi độ trễ cho JDBC driver

`executeQuery()` chạy lâu có thể do **lock wait**, SQL thiếu index hoặc server quá tải. `getConnection()` lâu có thể do pool hết chỗ vì ứng dụng giữ transaction dài. `getString()` chậm có thể do chuyển dữ liệu lớn hoặc GC. Driver chỉ là **một thành phần** trong đường đi; xem cả số liệu DBMS, pool, JVM và mạng trước khi kết luận thay driver.

### 10.5. Đo thời gian SQL nhưng bỏ qua transaction và request

Một request có thể thực hiện 100 truy vấn nhỏ. Nếu mỗi truy vấn 2 ms, tổng JDBC đã có thể lớn dù từng câu không chậm. Khi cần tối ưu API, bổ sung timer bao quanh **toàn bộ repository/service/request** và ghi số truy vấn trên mỗi request. Nếu truy vấn nằm trong transaction dài, cần đo cả thời gian giữ connection và lock để hiểu áp lực lên hệ thống.

## 11. Bài thực hành: tìm nguyên nhân khi request tăng từ 70 lên 400 ms

Giả sử tác vụ `loadCustomers` trước đây mất 70 ms nhưng giờ mất 400 ms ở tải cao. Bạn có thể làm như sau:

1. **Tạo baseline:** thu thập tối thiểu tên tác vụ, số hàng, borrow/execute/next/map/total time, số truy vấn cho mỗi request và số mẫu, theo cùng phạm vi dữ liệu.
2. **Đo ở tải thấp và tải cao:** giữ nguyên SQL, dữ liệu, DBMS, driver, JDK và cấu hình, chỉ tăng số request đồng thời; quan sát p50/p95 và tỉ lệ timeout.
3. **Nếu borrow tăng mạnh:** đối chiếu pool pending/active/hold time; kiểm tra nơi giữ connection vượt quá thời gian truy cập DB.
4. **Nếu execute tăng:** đối chiếu với lock, query plan, server CPU/I/O và execution time ở DBMS.
5. **Nếu next/map tăng:** so số hàng và bytes; xác minh có sự tăng dữ liệu/truyền tải, thay đổi fetch size hoặc cách đọc cột không.
6. **Thử một thay đổi duy nhất:** ví dụ giảm số cột trả về hoặc rút ngắn thời gian giữ connection; đo lại p95, throughput, error rate, GC và kết quả nghiệp vụ.
7. **Ghi quyết định:** lưu metric trước/sau, phiên bản driver, pool config, SQL/query ID, DB version và điều kiện benchmark để có thể tái hiện.

Một báo cáo tối thiểu có thể có cấu trúc:

~~~text
operation=loadCustomers
dbms=PostgreSQL
java=17
driver=<artifact-version>
concurrency=20
rows=500
samples=1000
borrow_p50=...
borrow_p95=...
execute_p95=...
next_p95=...
mapping_p95=...
jdbc_total_p95=...
timeout_count=...
notes=...
~~~

Các giá trị là chỗ trống để điền bằng số liệu thu được; không tự suy ra percentile từ một lần đo hay cộng các percentile của từng giai đoạn để thành “p95 tổng”.

## 12. Checklist trước khi kết luận về hiệu năng JDBC

- [ ] Đo từ **trước `getConnection()`** đến **sau khi đọc hết kết quả**, có đo tổng trọn đoạn JDBC.
- [ ] Tách ít nhất **borrow**, **prepare/execute**, **ResultSet iteration** và **mapping**; biết ranh giới nào phụ thuộc driver.
- [ ] Đếm **số hàng**, số truy vấn/request và có chỉ số timeout/lỗi.
- [ ] Dùng `System.nanoTime()` cho elapsed time, có warm-up và lấy đủ mẫu.
- [ ] Xem p50/p95/p99 trong **cùng loại workload**, kiểm tra pool, JVM và DBMS.
- [ ] So sánh ở môi trường/cấu hình gần production; hiểu rõ cache và concurrency.
- [ ] Bảo toàn cleanup trong mọi nhánh, không làm lộ SQL chứa secret hay dữ liệu người dùng khi xuất metric.
- [ ] Xác minh lại hiệu năng **end-to-end** sau tối ưu, kể cả lỗi và sử dụng tài nguyên.

**Ghi nhớ:** Muốn tối ưu JDBC có căn cứ, hãy đo **thời gian lấy kết nối**, **thời gian gọi câu SQL**, **thời gian duyệt/tải hàng** và **thời gian đọc/ánh xạ kết quả** như các giai đoạn khác nhau. Sau đó đối chiếu với pool, database, JVM và mạng. Các giai đoạn quan sát được chỉ ra **điều gì đang chậm trong ứng dụng**; để khẳng định nguyên nhân gốc, cần thêm bằng chứng từ thành phần liên quan.
