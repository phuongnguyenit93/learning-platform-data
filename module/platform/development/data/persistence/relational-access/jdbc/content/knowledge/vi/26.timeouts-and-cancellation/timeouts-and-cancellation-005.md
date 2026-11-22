# Hủy câu lệnh bằng `Statement.cancel()` và kiểm tra hỗ trợ trong JDBC

Trong chương **Timeout và hủy**, đôi khi ứng dụng JDBC cần ngừng một câu SQL đang chạy quá lâu: người dùng đóng màn hình tìm kiếm, request HTTP hết hạn, truy vấn phân tích quét quá nhiều dữ liệu hoặc một `UPDATE` đang chờ khóa. Java không thể chỉ “ngừng đợi” rồi mặc định câu SQL đã dừng ở cơ sở dữ liệu. Để yêu cầu DBMS hủy thao tác đang thực thi, JDBC cung cấp **`Statement.cancel()`**.

Bài học này giải thích cách gọi `cancel()` trên `Statement` hoặc `PreparedStatement`, giới hạn của cơ chế hủy, cách kiểm tra driver/DBMS có thực sự hỗ trợ, và cách phối hợp với query timeout, network timeout, transaction và connection pool. Đây là một phần quan trọng khi làm chủ **JDBC** để ứng dụng Java truy cập cơ sở dữ liệu quan hệ qua driver, `DataSource`, `PreparedStatement`, `ResultSet` và các API chuẩn cho CRUD, batching, xử lý lỗi và hiệu năng.

Sau bài học, bạn có thể:

- Phân biệt **ngừng chờ ở Java** với **yêu cầu hủy câu lệnh tại DBMS**.
- Gọi `Statement.cancel()` từ một luồng khác khi câu SQL đang chạy, không chia sẻ JDBC object bừa bãi giữa các luồng.
- Hiểu tại sao `cancel()` là cơ chế **best effort**, không trả trạng thái xác nhận câu lệnh đã dừng.
- Xây dựng phép thử tích hợp an toàn để đánh giá khả năng hủy của driver, thay vì đoán từ tên DBMS.
- Chọn đúng `setQueryTimeout()`, `setNetworkTimeout()`, login timeout và deadline của ứng dụng.
- Xử lý transaction/connection sau hủy và tránh retry gây tác dụng phụ ngoài ý muốn.

## 1. `Statement.cancel()` thực sự làm gì?

JDBC định nghĩa phương thức:

~~~java
void cancel() throws SQLException;
~~~

Phương thức thuộc interface `java.sql.Statement`. Vì `PreparedStatement` và `CallableStatement` kế thừa `Statement`, chúng cũng có `cancel()`.

Ý nghĩa: **Yêu cầu hủy câu lệnh SQL mà đối tượng Statement này đang thực thi**, nếu cả DBMS và JDBC driver hỗ trợ cơ chế hủy. JDBC cho phép **một luồng gọi `cancel()` trên statement đang được một luồng khác thực thi**.

Ví dụ ý tưởng:

~~~text
Luồng A (thực thi SQL)         Luồng B (theo dõi thời gian)
         |                                  |
         |--- executeQuery() ------------->| DBMS
         |                                  |
         |       SQL còn chạy              |
         |                                  |--- timeout/deadline
         |                                  |--- statement.cancel()
         |<----- kết quả hoặc lỗi ---------| DBMS/driver
         |
         |--- đóng ResultSet/Statement
~~~

**`cancel()` không phải nút “kill” chắc chắn.** Một lời gọi trả về bình thường chỉ nói rằng phương thức không báo lỗi tại thời điểm đó; vì nó có kiểu trả về `void` nên **không có giá trị `true/false` xác nhận câu SQL đã thực sự dừng**.

Tình huống có thể gặp:

1. Driver gửi yêu cầu hủy và DBMS dừng câu đang chạy; luồng thực thi thường nhận `SQLException` hoặc ngoại lệ liên quan.
2. Câu SQL đã hoàn thành trước khi tín hiệu hủy tới; kết quả có thể trả về thành công.
3. DBMS hoặc driver không hỗ trợ hủy, hoặc không thực hiện hủy đúng thời điểm.
4. Kết nối mạng đang gặp sự cố nên tín hiệu hủy không tới server, đến chậm hoặc không biết đã được xử lý chưa.
5. `cancel()` ném `SQLException` vì kết nối, statement đã đóng hoặc cơ chế hủy không được hỗ trợ.

**Không đồng nhất “đã gọi `cancel()`” với “đã rollback transaction”.** Hủy câu SQL, hủy transaction và đóng connection là ba hành động khác nhau.

## 2. Phân biệt năm loại giới hạn thời gian thường gặp

Ứng dụng có thể có nhiều lớp timeout. Chúng phục vụ các mục đích khác nhau:

| Cơ chế | Đơn vị / API | Tác động chính | Có bảo đảm ngừng SQL trên DBMS? |
| --- | --- | --- | --- |
| **`Statement.cancel()`** | Yêu cầu hủy không có timeout riêng trong tham số | Thử hủy câu lệnh đang chạy trên statement | **Không**, phụ thuộc driver/DBMS và trạng thái thực thi |
| **Query timeout** | `Statement.setQueryTimeout(int seconds)` | Cho driver một giới hạn thời gian thực thi câu SQL | Không bảo đảm dừng tức thời; triển khai tùy driver |
| **Network timeout** | `Connection.setNetworkTimeout(Executor, int milliseconds)` | Giới hạn thời gian chờ thao tác mạng của connection theo driver | Không tương đương query cancellation; có thể khiến connection bị đóng |
| **Connection/login timeout** | `DataSource.setLoginTimeout(int seconds)` hoặc cấu hình driver/pool | Giới hạn khi thiết lập/lấy kết nối theo khả năng hỗ trợ | Không, xảy ra trước lúc query chạy |
| **Deadline của tầng Java** | `Future.get(timeout, unit)`, HTTP deadline, scheduler | Giới hạn thời gian **người gọi chờ** | Không; câu SQL có thể vẫn chạy trên server |

Ngoài ra, DBMS thường có những cấu hình timeout riêng như thời gian chạy câu lệnh, chờ khóa hoặc thời gian giao dịch. Cú pháp và hành vi **không portable** giữa các hệ quản trị.

### `setQueryTimeout()` khác `cancel()`

~~~java
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT id, status FROM orders WHERE status = ?")) {

    ps.setQueryTimeout(10); // giây, không phải mili giây.
    ps.setString(1, "PENDING");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            consumeOrder(rs.getLong("id"), rs.getString("status"));
        }
    }
}
~~~

`setQueryTimeout(10)` yêu cầu driver giới hạn thời gian thực thi câu SQL theo giây. `0` nghĩa là không đặt giới hạn query timeout theo API này; không có nghĩa query sẽ không chịu timeout khác ở DBMS hoặc network.

Khi driver xác định query timeout bị vượt quá và đã ít nhất thử hủy câu lệnh đang chạy, JDBC có thể ném `SQLTimeoutException`. Một driver khác có thể báo `SQLException` theo cách riêng, hoặc không hỗ trợ timeout đúng như mong đợi. **Không coi mọi `SQLException` là query timeout.**

Lời gọi `cancel()` thì được kích hoạt **chủ động** từ code, ví dụ khi người dùng bấm “Hủy”. Có thể phối hợp cả hai: query timeout làm “hàng rào” phía JDBC, còn `cancel()` phản ứng với deadline hoặc thao tác người dùng.

### `Future.get(timeout)` không phải JDBC cancel

~~~java
Future<Integer> job = executor.submit(() -> slowDatabaseCall());
int result = job.get(5, TimeUnit.SECONDS);
~~~

Nếu `get(5, SECONDS)` ném `TimeoutException`, điều đó chỉ có nghĩa **luồng gọi không nhận kết quả đúng hạn**. Tác vụ trong executor **có thể vẫn chạy** và giữ connection, lock hoặc tài nguyên DBMS.

Tương tự, `Future.cancel(true)` yêu cầu interrupt Java thread nếu tác vụ đang chạy, **không phải bảo đảm driver sẽ gửi lệnh hủy SQL tới DBMS**. Hãy chủ động gắn một cơ chế gọi `Statement.cancel()` và quản lý connection nếu cần hành vi đó.

## 3. Gọi `cancel()` từ luồng khác: mô hình thực thi đúng

Một luồng bị chặn trong `executeQuery()` có thể không có cơ hội tự gọi `cancel()`. Vì vậy, luồng giám sát thời gian hoặc nhận tín hiệu từ người dùng thường phải gọi `cancel()`.

Cần **chỉ chia sẻ quyền hủy một statement đang chạy**, không biến `Connection` hoặc `PreparedStatement` thành đối tượng được nhiều luồng dùng SQL tùy ý.

~~~mermaid
sequenceDiagram
    participant C as Luồng điều khiển
    participant W as Luồng JDBC
    participant DB as DBMS
    C->>W: Submit công việc đọc
    W->>DB: executeQuery()
    Note over W,DB: SQL đang thực thi hoặc chờ khóa
    C->>C: Deadline hết hạn
    C->>W: Lấy tham chiếu Statement đang hoạt động
    C->>DB: statement.cancel() qua driver
    DB-->>W: Kết quả / SQLException / có thể vẫn tiếp tục
    W->>W: Đóng ResultSet, Statement, Connection khi kết thúc
    Note over C,W: Cancel đã yêu cầu, không đồng nghĩa đã dừng thành công
~~~

Tham chiếu statement chia sẻ giữa hai luồng phải có **công bố an toàn về bộ nhớ** (*safe publication*), chẳng hạn `AtomicReference<PreparedStatement>`. Không dùng biến thường không có đồng bộ rồi giả định luồng điều khiển luôn nhìn thấy nó kịp thời.

### Ví dụ Java 17+: deadline bên Java và yêu cầu hủy có kiểm soát

Ví dụ sau dùng **mỗi tác vụ một `Connection`, một `PreparedStatement`**, chạy câu `SELECT` chỉ đọc trong executor do ứng dụng quản lý. Luồng điều khiển gọi `cancel()` nếu chờ quá hạn.

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public final class CancelableQueryService {
    private final DataSource dataSource;
    private final ExecutorService jdbcWorkers;

    public CancelableQueryService(
            DataSource dataSource, ExecutorService jdbcWorkers) {
        this.dataSource = Objects.requireNonNull(dataSource);
        this.jdbcWorkers = Objects.requireNonNull(jdbcWorkers);
    }

    public long countPending(Duration waitLimit)
            throws InterruptedException, ExecutionException,
                   TimeoutException {

        if (waitLimit == null || waitLimit.isZero()
                || waitLimit.isNegative()) {
            throw new IllegalArgumentException(
                "waitLimit phải lớn hơn 0");
        }

        // Tham chiếu này chỉ phục vụ cancel từ luồng điều khiển.
        AtomicReference<PreparedStatement> active =
            new AtomicReference<>();

        Future<Long> running = jdbcWorkers.submit(() -> {
            String sql = """
                SELECT COUNT(*) FROM orders WHERE status = ?
                """;

            // Luồng JDBC tự sở hữu và đóng các tài nguyên của mình.
            try (Connection conn = dataSource.getConnection();
                 PreparedStatement ps = conn.prepareStatement(sql)) {

                ps.setString(1, "PENDING");
                ps.setQueryTimeout(20); // Hàng rào phụ nếu hỗ trợ.

                active.set(ps);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException(
                            "Truy vấn COUNT không trả hàng");
                    }
                    return rs.getLong(1);

                } finally {
                    // Không cho luồng điều khiển hủy statement
                    // sau khi tác vụ đã rời pha thực thi truy vấn.
                    active.compareAndSet(ps, null);
                }
            }
        });

        try {
            return running.get(
                waitLimit.toMillis(), TimeUnit.MILLISECONDS);

        } catch (TimeoutException | InterruptedException deadline) {
            PreparedStatement ps = active.get();

            if (ps != null) {
                try {
                    ps.cancel(); // Gọi từ luồng khác.
                } catch (SQLException cancelError) {
                    deadline.addSuppressed(cancelError);
                }
            }

            if (deadline instanceof InterruptedException) {
                Thread.currentThread().interrupt();
            }

            // Không khẳng định worker đã ngừng ở thời điểm này.
            throw deadline;
        }
    }
}
~~~

Ví dụ gọi:

~~~java
ExecutorService workers = Executors.newFixedThreadPool(4);

CancelableQueryService service =
    new CancelableQueryService(dataSource, workers);

try {
    long pending =
        service.countPending(Duration.ofSeconds(5));
    System.out.println("Số đơn đang chờ: " + pending);

} catch (TimeoutException timeout) {
    System.err.println(
        "Đã yêu cầu hủy truy vấn quá hạn, trạng thái thực tế cần theo dõi"
    );
}
~~~

`workers` là executor do ứng dụng sở hữu; khi dừng ứng dụng, phải đóng/shutdown theo lifecycle phù hợp. Ví dụ là **mô hình giải thích cơ chế hủy**, chưa phải triển khai production đầy đủ về quota, graceful shutdown, hard timeout và giám sát các truy vấn không chịu hủy.

**Những chi tiết quan trọng trong mã:**

1. `Future.get(...)` giới hạn thời gian **người gọi chờ**, còn `ps.cancel()` là một yêu cầu riêng tới JDBC driver.
2. `AtomicReference` giúp luồng điều khiển có thể nhìn thấy statement đã tạo. Nó **không khóa** việc đóng statement; nếu query vừa kết thúc, `cancel()` có thể chạy đua với `close()` và ném `SQLException`. Đoạn mã ghi nhận lỗi thay vì tuyên bố đã hủy.
3. Nếu deadline hết hạn khi công việc **chưa bắt đầu**, `active.get()` có thể bằng `null`; lúc ấy chưa có statement để hủy. Cần quản lý hàng đợi executor và deadline của toàn tác vụ ở tầng điều phối nếu muốn có giới hạn cứng.
4. Nếu DBMS **phớt lờ cancellation**, worker vẫn có thể chạy sau khi phương thức `countPending()` đã ném `TimeoutException`. Không được tự ghi log “SQL đã hủy thành công” chỉ dựa vào timeout.
5. Chỉ luồng worker đóng `ResultSet`, `Statement` và `Connection` của mình khi thoát. Luồng điều khiển **không** đồng thời dùng connection đó cho một câu SQL khác.
6. Ví dụ chỉ chạy `SELECT COUNT(*)`, hạn chế nguy cơ tác dụng phụ nghiệp vụ nếu cancellation đến quá muộn. Với `UPDATE`/`INSERT`, cần chính sách transaction và đối soát riêng.

Để hoàn thiện cho sản xuất, cần theo dõi tác vụ còn chạy sau cancel, giới hạn tổng số connection/task không phản hồi, cơ chế cưỡng chế ngắt kết nối theo driver/pool nếu cần và tránh tạo executor riêng cho từng request.

## 4. Các cuộc đua thời gian (race) khi hủy

Một cơ chế cancel đáng tin phải chấp nhận nhiều thứ tự sự kiện:

| Tình huống | Điều có thể xảy ra | Cách ứng dụng phản ứng |
| --- | --- | --- |
| Gọi `cancel()` **trước** `executeQuery()` | Statement chưa thực thi, lời gọi có thể không ảnh hưởng truy vấn về sau | Theo dõi trạng thái tác vụ; không dựa vào cancel sớm để chặn SQL sắp chạy |
| Gọi `cancel()` đúng lúc query đang chạy | DBMS có thể dừng query hoặc từ chối hủy | Chờ worker trả về và quan sát kết quả/ngoại lệ |
| Query hoàn thành **ngay trước** cancel | `executeQuery()` có thể thành công, cancel không còn gì để hủy | Kết quả thành công có thể đến sau deadline; áp dụng chính sách nghiệp vụ |
| Query hoàn thành và statement bị đóng | `cancel()` có thể ném `SQLException` | Ghi nhận race, không coi SQL đã chạy lỗi |
| Driver không truyền được tín hiệu hủy | Worker vẫn chờ hoặc network đang lỗi | Giới hạn thời gian, quản lý/loại kết nối lỗi |
| Dùng lại Statement quá sớm | Lệnh cancel muộn có thể ảnh hưởng thao tác không mong muốn | Không tái sử dụng cùng statement cho một công việc khác khi kết quả cancel chưa rõ |

**Khuyến nghị:** Một statement đang chạy chỉ thuộc **một thao tác nghiệp vụ**, được tạo và đóng theo scope của thao tác đó. Không tạo shared statement dùng lại giữa các request; như vậy rủi ro cancel chéo giảm đáng kể.

Nếu một UI có nút “Hủy”, nên định nghĩa rõ ba trạng thái:

~~~text
RUNNING → CANCEL_REQUESTED → FINISHED
                         ↘ CANCELLED_OR_FAILED
                         ↘ STILL_RUNNING / UNKNOWN
~~~

Trạng thái `CANCEL_REQUESTED` chỉ nghĩa ứng dụng đã thử gửi tín hiệu. Để đánh dấu đã thực sự dừng, phải quan sát **tác vụ JDBC đã thoát** và xử lý trạng thái transaction/connection. Nếu chưa có phản hồi, thể hiện đúng là `STILL_RUNNING` hoặc `UNKNOWN`.

## 5. Kiểm tra hỗ trợ `cancel()`: không có một cờ portable duy nhất

Đây là điểm dễ nhầm: trong API `java.sql.DatabaseMetaData` chuẩn, **không có một phương thức chung như `supportsStatementCancel()` hoặc `supportsCancel()`** để hỏi driver có thực sự hủy được mọi truy vấn hay không.

Các phương thức metadata như `supportsTransactions()`, `supportsBatchUpdates()`, `supportsStatementPooling()` hoặc `supportsResultSetType()` mô tả những khả năng khác. Chúng **không chứng minh `Statement.cancel()` có hoạt động hay không**.

Một chiến lược kiểm tra thực tế gồm ba lớp:

1. **Tài liệu chính thức** của đúng DBMS, phiên bản JDBC driver và phiên bản server; đọc giới hạn của `cancel()` đối với truy vấn đang chạy, chờ khóa, batch, thủ tục lưu trữ và network.
2. **Thử nghiệm tích hợp** trên cơ sở dữ liệu thử nghiệm, với một thao tác được biết chắc đang chờ hoặc chạy lâu; gọi `cancel()` từ luồng khác rồi quan sát nó có kết thúc hay không.
3. **Theo dõi hành vi production** bằng metric (cancellation requested, query stopped, duration, still-running, failures, connection evictions), không biến một lần thử nghiệm thành cam kết tuyệt đối.

### `cancel()` trả về bình thường có nghĩa hỗ trợ không?

**Chưa đủ.** Nó có thể trả về khi statement chưa chạy, query đã kết thúc hoặc driver gửi yêu cầu nhưng DBMS không kịp phản hồi. Phải **quan sát luồng thực thi SQL** để đánh giá hiệu quả.

### Ném `SQLFeatureNotSupportedException` hoặc `SQLException` có nghĩa gì?

Đó là tín hiệu cho thấy thao tác thất bại hoặc không được hỗ trợ trong tình huống này; đọc `SQLState`, mã lỗi và tài liệu driver. Tuy nhiên, một lần lỗi kết nối hoặc statement đã đóng **không đủ để kết luận mọi truy vấn đều không thể hủy**.

## 6. Kịch bản integration test an toàn bằng hai connection

SQL chuẩn không có một hàm “sleep” portable chung giữa mọi DBMS. Dựa trên cơ chế khóa của DBMS, ta có thể tạo một tình huống **chờ khóa có kiểm soát** để đánh giá cancel mà không cần truy vấn ngẫu nhiên tốn tài nguyên.

Bảng thử nghiệm độc lập:

~~~sql
CREATE TABLE jdbc_cancel_probe (
    id BIGINT PRIMARY KEY,
    counter_value BIGINT NOT NULL
);

INSERT INTO jdbc_cancel_probe (id, counter_value)
VALUES (1, 0);
~~~

Chỉ thực hiện trong **cơ sở dữ liệu test**. Không tạo lock wait trên dữ liệu sản xuất hoặc kết nối của người dùng thật.

### Các bước kiểm thử

| Thứ tự | Connection A | Connection B / luồng khác |
| --- | --- | --- |
| 1 | `setAutoCommit(false)` | `setAutoCommit(false)` |
| 2 | `UPDATE jdbc_cancel_probe SET counter_value = counter_value + 1 WHERE id = 1`, giữ transaction chưa commit | — |
| 3 | Giữ khóa hàng `id = 1` | Chạy `UPDATE` cùng hàng; với DBMS hỗ trợ row locks, thao tác thường phải chờ A |
| 4 | Giữ transaction mở trong giới hạn test | Sau khi xác nhận B đang chờ, luồng điều khiển gọi `statementB.cancel()` |
| 5 | — | Ghi thời gian và xem `executeUpdate()` có kết thúc/throw exception không |
| 6 | — | `rollback()` transaction B; kiểm tra connection có dùng lại an toàn không |
| 7 | `rollback()` transaction A để nhả khóa | — |
| 8 | Kiểm tra dữ liệu về trạng thái ban đầu, dọn bảng test | — |

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant A as Connection A
    participant B as Connection B (worker)
    participant M as Luồng monitor
    participant DB as DBMS thử nghiệm
    A->>DB: UPDATE id=1 (giữ khóa)
    B->>DB: UPDATE id=1 (chờ khóa A)
    Note over B,DB: Cần xác nhận B thực sự đang chờ
    M->>B: statementB.cancel()
    DB-->>B: Có thể SQLException / kết thúc / chưa phản hồi
    B->>DB: ROLLBACK khi đã thoát pha execute
    A->>DB: ROLLBACK, nhả khóa
    M->>DB: Kiểm tra giá trị, log và trạng thái connection
~~~

**Điều kiện đánh giá kết quả:**

- Phải có bằng chứng B thực sự đang chạy/chờ (từ server monitoring, log hoặc công cụ quan sát DBMS), không chỉ đoán sau một `Thread.sleep()`.
- Test phải có **deadline và đường dọn tài nguyên** ngay cả khi driver không phản hồi. Có thể dùng network timeout, timeout phía server hoặc quy trình cưỡng chế đóng kết nối thử nghiệm phù hợp DBMS.
- Nếu B tự hết lock timeout trước khi `cancel()` tới, bài thử **không chứng minh cancel hoạt động**.
- Nếu A nhả khóa trước lúc thử hủy, B có thể tự hoàn thành: kết quả cũng **không đủ kết luận**.
- Cơ chế lock và mức độ blocking của `UPDATE` phụ thuộc DBMS, storage engine, isolation và query plan. Nếu một DBMS không khóa theo cách trên, phải thiết kế tình huống tương đương đúng với DBMS đó.
- Sau khi hủy, kiểm tra không còn transaction treo hoặc connection lỗi trong pool; không coi việc `cancel()` trả về là kết thúc test.

### Ma trận thử nghiệm cần có

Một lần thử với `SELECT` không đại diện cho mọi thao tác. Hãy kiểm thử một số nhóm phù hợp workload:

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| Truy vấn đọc dài | `cancel()` có làm query trả về sớm không? |
| Câu `UPDATE` đang chờ khóa | Có dừng chờ và giải phóng tài nguyên liên quan không? |
| Batch `executeBatch()` | Nếu hủy giữa chừng, update counts, transaction và rollback ra sao? |
| `ResultSet` đang được đọc dở | Driver có phản ứng khi hủy lúc fetch/`next()` không? |
| Lỗi mạng hoặc DBMS không phản hồi | Cancel có bị chặn hoặc không tới server không? |
| Sau hủy | Statement/connection có tiếp tục sử dụng an toàn hay phải bỏ? |

Không tự viết test “chạy SQL vô hạn” mà không có hạn mức và quy trình dọn dẹp. Mục tiêu là **kiểm chứng có kiểm soát**, không tạo tải nguy hiểm.

## 7. Sau `cancel()`, transaction đang ở trạng thái nào?

`Statement.cancel()` **không phải** `Connection.rollback()`. Khi ứng dụng đang ở chế độ `autoCommit = false`, sau khi một câu SQL bị hủy có thể xảy ra các tình huống:

- DBMS hủy riêng câu đang thực thi nhưng **giữ transaction đang mở**.
- DBMS đánh dấu transaction **aborted/failed**, yêu cầu rollback trước khi tiếp tục.
- Một loại lỗi nghiêm trọng khiến toàn transaction bị DBMS rollback.
- Kết nối lỗi hoặc mất mạng, ứng dụng **không biết chắc** server đã thực hiện đến đâu.

Vì vậy, **không có quy tắc JDBC phổ quát rằng mọi cancellation tự rollback toàn transaction**.

### Ví dụ DBMS khác nhau

Với **PostgreSQL**, một câu bị hủy thường có thể báo `SQLSTATE 57014` (`query_canceled`). Trong transaction thủ công, sau lỗi câu lệnh transaction có thể chuyển vào trạng thái bị đánh dấu lỗi; các lệnh thông thường sau đó có thể nhận `25P02` cho tới khi rollback hoặc rollback tới savepoint hợp lệ trước lỗi.

Với **MySQL**, thông báo “Query execution was interrupted” thường gắn với mã nhà cung cấp `1317` và SQLSTATE như `70100` trong những tình huống/driver nhất định. Nhưng trạng thái transaction sau hủy phụ thuộc engine, loại lệnh, cấu hình và cách hủy; không mang quy tắc PostgreSQL áp nguyên sang MySQL.

**Không hard-code chính sách dựa vào một mã duy nhất cho mọi DBMS.** `SQLException.getSQLState()` và `getErrorCode()` giúp chẩn đoán, nhưng phải kết hợp đúng driver/DBMS.

### Chính sách an toàn cho thao tác ghi

Nếu nghiệp vụ có nhiều bước bắt buộc và một `UPDATE`/`INSERT`/batch bị hủy:

1. Dừng đơn vị nghiệp vụ và không gửi thêm SQL trên connection đó cho tới khi xác định trạng thái.
2. Đợi **luồng đang thực thi** trả về hoặc thoát khỏi pha JDBC; tránh gọi rollback đồng thời từ luồng monitor nếu driver không hỗ trợ sử dụng connection đa luồng.
3. Khi connection còn khả dụng, gọi `rollback()` toàn transaction nếu nghiệp vụ yêu cầu tất cả hoặc không có gì.
4. Nếu rollback lỗi, ghi nhận cả lỗi gốc và lỗi rollback; xem connection là **không đáng tin** và xử lý theo cơ chế pool/driver.
5. Chỉ retry trong transaction mới khi xác định được tình trạng kết quả và tính idempotent của thao tác.

Đoạn xử lý thông thường trong **luồng sở hữu connection**:

~~~java
conn.setAutoCommit(false);
try {
    // Thực thi câu SQL/batch có thể bị luồng khác cancel().
    runBusinessStatements(conn);
    conn.commit();

} catch (SQLException | RuntimeException failure) {
    try {
        conn.rollback();
    } catch (SQLException rollbackFailure) {
        failure.addSuppressed(rollbackFailure);
    }
    throw failure;
}
~~~

Đây là mô hình đơn giản để thấy rollback thuộc trách nhiệm **transaction owner**. Mã hoàn chỉnh cần quản lý việc khôi phục `autoCommit`, vòng đời connection, lỗi commit không rõ kết quả và tương tác pool. Không đặt `conn.setAutoCommit(true)` vô điều kiện trước khi rollback thành công: thay đổi chế độ khi transaction còn mở có thể commit phần chưa mong muốn.

### Khi đang bật `autoCommit = true`

Mỗi câu lệnh có ranh giới commit tự động theo quy tắc JDBC. Nếu một câu SQL hoặc batch có một phần công việc đã commit trước khi cancellation đến, `rollback()` **không thể đảo ngược phần đã commit**. Đặc biệt, một thao tác “cancel request” **không thay thế cơ chế nghiệp vụ bù trừ**.

Với các thao tác ghi quan trọng như thanh toán hoặc tạo đơn, cancellation đến sau deadline có thể xảy ra **khi DBMS đã commit nhưng Java chưa thấy kết quả**. Cần idempotency key, ràng buộc `UNIQUE` và đối soát bằng connection lành mạnh trước khi retry.

## 8. `cancel()` khi đang đọc `ResultSet` hoặc xử lý batch

### 8.1. Đọc `ResultSet` lớn

Một câu `SELECT` có thể kết thúc giai đoạn `executeQuery()` nhưng driver vẫn phải truyền dữ liệu khi ứng dụng liên tục gọi `rs.next()`. Nếu ứng dụng muốn hủy lúc đang fetch, hiệu quả của `Statement.cancel()` **phụ thuộc cách driver/server thực hiện fetch**:

~~~java
try (PreparedStatement ps = conn.prepareStatement(
        "SELECT id, payload FROM archive ORDER BY id")) {

    ps.setFetchSize(200);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            consumeRow(rs.getLong("id"), rs.getString("payload"));
        }
    }
}
~~~

`setFetchSize(200)` chỉ là **gợi ý số hàng mỗi đợt fetch**, không phải timeout hoặc cơ chế hủy. Khi `consumeRow(...)` đang chạy mã Java riêng và không có JDBC I/O, gọi `cancel()` có thể không làm nó dừng. Cần bổ sung cờ hủy ở tầng xử lý ứng dụng, ví dụ `AtomicBoolean stopRequested`, và kiểm tra cờ giữa các hàng/chunk.

**Dữ liệu đã gửi tới client hoặc đã xử lý bên ngoài DBMS không thể “rút lại” bằng `cancel()`.** Nếu đã ghi ra file, gọi API ngoài hoặc xử lý nửa báo cáo, phải thiết kế dọn dẹp/đánh dấu kết quả dở dang ở tầng ứng dụng.

### 8.2. Hủy `executeBatch()`

Khi chạy batch, `Statement.cancel()` có thể yêu cầu dừng câu SQL đang thực thi, nhưng **không bảo đảm toàn bộ batch đã bị hoàn tác**. Driver có thể đã chạy một số lệnh; kết quả có thể là `BatchUpdateException`, `SQLException`, timeout hoặc diễn biến khác.

Nếu nghiệp vụ yêu cầu batch nguyên tử:

~~~java
conn.setAutoCommit(false);
try (PreparedStatement ps = conn.prepareStatement(
        "UPDATE inventory SET available = available - ? WHERE id = ?")) {

    for (InventoryChange change : changes) {
        ps.setInt(1, change.quantity());
        ps.setLong(2, change.productId());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    verifyCounts(counts); // Bắt lỗi nghiệp vụ nếu cần.
    conn.commit();

} catch (SQLException failure) {
    // Mô hình: transaction owner rollback sau khi execute đã thoát.
    try {
        conn.rollback();
    } catch (SQLException rollbackError) {
        failure.addSuppressed(rollbackError);
    }
    throw failure;
}
~~~

`InventoryChange`, `changes` và `verifyCounts` là các thành phần minh họa của nghiệp vụ. Mục tiêu là thể hiện rằng **cancellation không thay thế kiểm tra kết quả batch và rollback**.

Với `BatchUpdateException`, `getUpdateCounts()` có thể cho biết những câu đã thực thi/được thử, nhưng không chứng minh chúng đã commit. `Statement.SUCCESS_NO_INFO` không có nghĩa thất bại; `Statement.EXECUTE_FAILED` biểu thị lệnh lỗi trong một số chế độ driver tiếp tục batch.

## 9. Khi `cancel()` không dừng được: bước leo thang

Trong môi trường production, cần chính sách cho trường hợp **cancel không có hiệu lực** hoặc mất quá nhiều thời gian:

~~~mermaid
flowchart TD
    A["Deadline vượt ngưỡng"] --> B["Gửi Statement.cancel() một lần"]
    B --> C{"Luồng JDBC đã thoát?"}
    C -- "Có" --> D["Đọc kết quả/lỗi; xử lý transaction"]
    C -- "Chưa" --> E["Theo dõi trong khoảng grace có giới hạn"]
    E --> F{"Luồng đã thoát?"}
    F -- "Có" --> D
    F -- "Không" --> G["Đánh dấu connection không đáng tin"]
    G --> H["Thực thi chính sách network timeout / abort / pool eviction"]
    H --> I["Quan sát trạng thái server và đối soát nếu có ghi dữ liệu"]
~~~

Những công cụ có thể dùng:

- **`Connection.setNetworkTimeout(Executor, milliseconds)`**: một cơ chế JDBC để giới hạn thao tác mạng theo hỗ trợ driver. Nó có thể dẫn đến việc đóng connection, **không phải một cách tương đương với cancel từng câu SQL**.
- **`Connection.abort(Executor)`**: yêu cầu chấm dứt connection, một hành động mạnh hơn cancel statement. Cần hiểu tác động lên transaction đang chạy và khả năng driver hỗ trợ.
- **Connection pool eviction** hoặc loại bỏ connection lỗi: phụ thuộc pool cụ thể, không có một lời gọi chung bằng JDBC chuẩn cho tất cả pool.
- **Timeout/cancellation phía server**: ví dụ thiết lập giới hạn thực thi câu SQL/chờ khóa hoặc công cụ hủy session theo DBMS, cần kiểm soát quyền và phạm vi.
- **Giới hạn concurrency và circuit breaker**: tránh mỗi request timeout vẫn để lại một query/server session đang chạy mãi.

**Không coi `Connection.close()` gọi từ một luồng khác như một cách hủy tức thời portable.** Tương tác đóng connection khi query đang chạy khác nhau giữa driver; một số thao tác có thể chờ, gây lỗi hoặc ảnh hưởng transaction. Việc chấm dứt cứng phải là chính sách riêng, được kiểm thử với môi trường thực tế.

Khi query không chịu cancel, không trả connection ấy về pool như một kết nối khỏe mạnh rồi cho request mới dùng ngay. Cần xử lý từ tầng sở hữu connection/pool theo khả năng driver và ghi nhận số connection cần loại bỏ.

### Tránh “retry storm” sau cancellation

Nếu nhiều request đồng thời timeout vì DBMS đang quá tải, lập tức retry tất cả sẽ tạo thêm tải và làm tình trạng xấu hơn. Với các trường hợp được phép retry, cần:

- Giới hạn số attempt và tổng thời gian.
- Backoff có jitter và giới hạn số task JDBC đồng thời.
- Chỉ retry khi thao tác là idempotent hoặc đã xác minh transaction trước không commit.
- Phân biệt lỗi do người dùng hủy chủ động với lỗi hệ thống.
- Không retry câu SQL không hợp lệ hoặc lỗi constraint có tính quyết định.

## 10. Giám sát và chẩn đoán trong ứng dụng

Để biết `Statement.cancel()` hoạt động thực sự đến đâu, nên ghi nhận **hành động yêu cầu hủy** và **kết quả thực thi** là hai sự kiện khác nhau.

| Metric/log | Mục đích |
| --- | --- |
| `query_started` | Tổng số tác vụ JDBC đã bắt đầu |
| `cancel_requested` | Có bao nhiêu yêu cầu hủy đã được gửi |
| `cancel_call_failed` | `cancel()` ném lỗi bao nhiêu lần |
| `query_finished_after_cancel` | Worker đã thoát sau yêu cầu cancel |
| `query_still_running_after_grace` | Query không phản hồi trong ngưỡng cho phép |
| `query_timeout_count` | Số truy vấn hết hạn theo driver/server hoặc deadline ứng dụng, ghi rõ nguồn |
| `transaction_rollback_failed` | Tình huống dọn trạng thái transaction không thành công |
| `connection_evicted_after_cancel` | Số connection bị loại bỏ vì không còn đáng tin |
| `time_to_stop_after_cancel` | Độ trễ từ yêu cầu hủy tới khi SQL thực sự kết thúc |

Các trường log hữu ích:

~~~text
operation=search_orders
request_id=...
driver=...
dbms=...
elapsed_ms=...
query_timeout_seconds=...
cancel_requested=true
cancel_call_error=none
execution_outcome=sql_exception|success|still_running|unknown
sql_state=...
vendor_code=...
transaction_outcome=rolled_back|committed|unknown
~~~

**Không ghi nguyên văn SQL kèm tham số nhạy cảm**. Với SQL tham số hóa, ưu tiên tên truy vấn, định danh nghiệp vụ không nhạy cảm, correlation ID và metadata phục vụ điều tra.

Đừng đưa tất cả các trạng thái dưới nhãn duy nhất “timeout”: query bị hủy khi user bấm nút, driver query timeout, socket/network timeout, lock timeout ở DBMS và deadline ở Java có nguyên nhân/tác động khác nhau.

## 11. Những sai lầm thường gặp

| Cách làm sai | Hậu quả | Cách đúng |
| --- | --- | --- |
| Chỉ gọi `Future.get(timeout)` rồi cho rằng DB đã ngừng | SQL có thể vẫn chạy và giữ connection | Gửi `Statement.cancel()`, theo dõi worker và cleanup |
| Chỉ gọi `Future.cancel(true)` để hủy JDBC | Interrupt thread không bảo đảm gửi cancel tới DBMS | Dùng cơ chế JDBC/driver đã kiểm thử |
| Coi `cancel()` trả bình thường là hủy thành công | API trả `void`, query có thể đã xong hoặc vẫn chạy | Quan sát kết quả luồng thực thi |
| Gọi `cancel()` trên statement dùng chung bởi nhiều request | Nguy cơ hủy nhầm thao tác khác | Mỗi công việc dùng statement riêng |
| Cho nhiều luồng chạy SQL đồng thời trên cùng connection | Tranh chấp trạng thái, hành vi driver khó đoán | Một luồng sở hữu transaction, luồng khác chỉ yêu cầu cancel |
| Gọi `rollback()` ngay từ luồng monitor khi worker còn dùng connection | Có thể gây race và lỗi không xác định | Đợi luồng thực thi thoát, rồi transaction owner rollback |
| Coi cancel tự rollback transaction | Transaction có thể còn mở hoặc aborted | Kiểm tra và rollback theo quy tắc DBMS |
| Đổi `autoCommit = true` khi rollback chưa thành công | Có nguy cơ commit phần dữ liệu chưa mong muốn | Kết thúc giao dịch an toàn trước khi khôi phục |
| Không kiểm tra support, chỉ dựa tên driver | Hành vi khác theo phiên bản/query/DBMS | Đọc tài liệu và làm integration test |
| Dùng `setQueryTimeout(5000)` với ý nghĩa 5 giây | Đơn vị là **giây**, không phải ms | Đặt 5 nếu muốn 5 giây |
| Nhầm `setNetworkTimeout` với query timeout | Có thể đóng connection ngoài ý muốn | Chọn cơ chế đúng lớp timeout |
| Dùng cancel như một cách chống SQL injection | Cancel không kiểm tra an toàn câu SQL | Dùng `PreparedStatement` tham số hóa |
| Retry ngay sau cancel một lệnh ghi đã auto-commit | Có thể tạo dữ liệu trùng | Idempotency và đối soát trạng thái |
| Dùng `Thread.sleep()` rồi kết luận cancel được hỗ trợ | Query có thể chưa bắt đầu hoặc đã tự kết thúc | Kiểm thử có quan sát trạng thái server |
| Ghi log “CANCELLED” ngay khi gọi cancel | Gây hiểu nhầm trong giám sát | Phân biệt requested, stopped và unknown |

## 12. Tình huống luyện tập

**Tình huống A.** Một `PreparedStatement.executeQuery()` đang chờ lâu. Luồng giao diện gọi `statement.cancel()` và không nhận ngoại lệ. Có thể lập tức hiển thị “SQL đã bị hủy chắc chắn” không?

**Đáp án:** Không. `cancel()` không trả xác nhận hủy thành công. Phải theo dõi luồng thực thi SQL kết thúc, đọc kết quả hoặc ngoại lệ và kiểm tra tài nguyên.

**Tình huống B.** `Future.get(3, SECONDS)` ném `TimeoutException` nhưng không gọi `Statement.cancel()`. Connection vẫn đang chạy query trên DBMS. Đây có phải hành vi trái với JDBC không?

**Đáp án:** Không. Timeout của `Future.get` chỉ ngừng chờ ở phía Java, không tự hủy SQL tại server.

**Tình huống C.** `DatabaseMetaData.supportsBatchUpdates()` trả `true`. Có thể dựa vào đó kết luận `Statement.cancel()` hoạt động trên mọi batch không?

**Đáp án:** Không. Hỗ trợ batch và khả năng hủy là hai tính năng khác nhau. JDBC metadata không có một cờ `supportsCancel()` portable chung; phải kiểm thử đúng driver/DBMS.

**Tình huống D.** Một `UPDATE` trong manual transaction bị hủy; PostgreSQL trả SQLSTATE `57014`. Luồng tiếp theo chạy `SELECT` trên cùng transaction và nhận `25P02`. Nên làm gì?

**Đáp án:** Transaction đang ở trạng thái lỗi. Cần rollback toàn phần, hoặc rollback tới savepoint hợp lệ được lập trước lỗi nếu nghiệp vụ cho phép; không lặp lại SQL vô hạn trên transaction đã aborted.

**Tình huống E.** User bấm Hủy khi câu `INSERT` đã commit trước đó. `cancel()` có thể hoàn tác bản ghi đã lưu không?

**Đáp án:** Không. Cancellation không phải rollback những transaction đã commit; phải dùng quy trình bù trừ hoặc thao tác nghiệp vụ có kiểm soát nếu cần.

**Tình huống F.** Luồng worker vừa đóng statement, cùng lúc monitor giữ tham chiếu và gọi `cancel()`, nhận `SQLException`. Có nhất thiết truy vấn đã lỗi không?

**Đáp án:** Không. Có thể là race khi statement đã kết thúc và đóng. Ghi nhận sự kiện và kiểm tra kết quả worker để xác định tình trạng truy vấn.

**Tình huống G.** Query timeout được đặt `ps.setQueryTimeout(5)` và phía ứng dụng đặt deadline 2 giây. Hai giới hạn giống nhau không?

**Đáp án:** Không. `setQueryTimeout(5)` là 5 giây theo API JDBC cho việc thực thi câu SQL, còn deadline 2 giây giới hạn việc người gọi chờ. Khi deadline hết, ứng dụng vẫn cần quyết định có gửi cancel và chờ cleanup không.

**Tình huống H.** Một câu `SELECT` đã trả về `ResultSet` nhưng ứng dụng còn xử lý dữ liệu trong `consumeRow()` rất lâu. `cancel()` có dừng ngay phần tính toán Java này không?

**Đáp án:** Không. Cancel nhằm vào hoạt động SQL/JDBC mà driver hỗ trợ, không hủy tùy ý mã Java đang xử lý. Cần thêm tín hiệu dừng ở vòng lặp ứng dụng.

**Tình huống I.** Sau khi gọi `cancel()`, driver không phản hồi thêm 30 giây và connection vẫn bị giữ. Có nên trả connection đó cho pool để dùng lại?

**Đáp án:** Không. Phải theo dõi, áp dụng hard timeout/abort hoặc chính sách loại kết nối lỗi đã kiểm thử. Không tái sử dụng connection đang có thao tác chưa kết thúc.

**Tình huống J.** Một truy vấn đang chờ khóa ở kết nối B; bạn muốn chứng minh driver hỗ trợ cancel. Chỉ cần ngủ 100 ms rồi cancel được không?

**Đáp án:** Chưa đủ. Phải xác nhận B thực sự đang chờ, A vẫn giữ khóa, gọi cancel từ luồng khác, theo dõi thời điểm B thoát và cleanup cả hai transaction. Nếu truy vấn tự kết thúc thì test chưa kết luận được.

## Ghi nhớ

- **`Statement.cancel()` là yêu cầu hủy câu SQL đang thực thi**, có thể gọi từ luồng khác; không phải cơ chế hủy transaction hay ngắt Java thread chắc chắn.
- **Cancel là best effort:** API trả `void`; phải kiểm tra luồng thực thi SQL đã kết thúc, lỗi/kết quả trả về và trạng thái connection.
- **Không có một `DatabaseMetaData.supportsCancel()` portable**. Hãy đọc tài liệu driver và kiểm thử tích hợp với truy vấn thực sự đang chạy/chờ khóa.
- **`setQueryTimeout()` dùng giây, `setNetworkTimeout()` dùng mili giây**; `Future.get(timeout)` chỉ giới hạn thời gian chờ ở Java.
- **Chia sẻ statement chỉ cho mục đích cancel có kiểm soát**, không chạy nhiều câu SQL đồng thời trên cùng statement/connection.
- **Sau hủy thao tác ghi, transaction owner phải xử lý rollback và đối soát**. Không retry mù nếu không biết lệnh hoặc commit trước đó đã thành công hay chưa.
- **Khi cancel không hiệu quả, cần đường leo thang có giới hạn**: quan sát, network timeout/abort/loại connection, giới hạn concurrency và ghi nhận kết quả thực tế.
