# Xác minh khả năng phục hồi sau khi cơ sở dữ liệu khởi động lại

Một dịch vụ Java có thể chạy ổn định hàng tháng, nhưng cơ sở dữ liệu vẫn cần khởi động lại vì bảo trì, cập nhật phiên bản, sự cố tài nguyên hoặc chuyển đổi hạ tầng. Sau khi database hoạt động trở lại, **ứng dụng JDBC không tự nhiên được xem là đã phục hồi** chỉ vì cổng TCP mở hoặc `DataSource.getConnection()` không còn báo lỗi. Các kết nối vật lý được tạo trước khi database restart có thể đã hỏng; connection pool cần phát hiện và thay thế chúng; request đang chạy có thể bị lỗi; và một transaction vừa gửi `COMMIT` trước khi mất kết nối có thể để lại **kết quả chưa xác định**.

Vì vậy, kiểm thử phục hồi phải trả lời được một câu hỏi cụ thể: **Sau khi database khởi động lại, ứng dụng có tự quay về khả năng phục vụ các thao tác JDBC đúng và an toàn mà không cần khởi động lại chính ứng dụng không?** Ta cần quan sát **đường đi nghiệp vụ thật**, không chỉ tín hiệu “database process đã chạy”.

Bài học thuộc chương **Giám sát vận hành** của module **JDBC**. Nội dung kết hợp `DataSource`, connection pool, `Connection`, `PreparedStatement`, `ResultSet`, transaction, timeout, SQLState, health check và fault-injection có kiểm soát để thiết kế một phép thử phục hồi có thể lặp lại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả vòng đời của connection trước, trong và sau khi DB restart.
2. Phân biệt database **đã chạy**, **sẵn sàng nhận kết nối** và **ứng dụng đã phục hồi nghiệp vụ**.
3. Thiết kế kiểm thử khởi động lại database trong môi trường test, có baseline, fault window và recovery assertions.
4. Xác minh pool không tiếp tục phát connection vật lý đã hỏng, và những connection mới có thể truy vấn thành công.
5. Kiểm tra `Connection.isValid(...)`, query thực tế và commit được quan sát từ connection độc lập.
6. Phân biệt lỗi kết nối với lỗi SQL thông thường; hiểu giới hạn của phân loại `SQLException`/SQLState.
7. Kiểm soát timeout và số lần retry để ứng dụng không treo hoặc tạo **retry storm** khi DB chưa sẵn sàng.
8. Nhận diện và xử lý transaction có **commit outcome bất định** bằng idempotency và đối soát.
9. Định nghĩa tiêu chí phục hồi, metric, cảnh báo và thời gian phục hồi có thể đo.
10. Viết một kịch bản integration test có thể chạy trong CI hoặc diễn tập vận hành được cấp phép.

## 2. Điều gì xảy ra với JDBC khi database restart?

Giả sử service sử dụng connection pool. Trước sự cố, pool giữ một số connection vật lý tới DBMS:

~~~mermaid
flowchart LR
    A["Java service"] --> P["Connection pool"]
    P --> C1["Connection A"]
    P --> C2["Connection B"]
    C1 --> D["Database process"]
    C2 --> D
~~~

Khi database process bị dừng rồi chạy lại, các session cũ thường không còn hợp lệ. Tùy hạ tầng mạng, client có thể thấy socket bị đóng, nhận lỗi I/O ngay, hoặc tiếp tục chờ cho tới khi timeout phát hiện được mất kết nối.

~~~mermaid
flowchart TD
    S["Trước restart: connection còn hợp lệ"] --> F["DB dừng / session cũ mất hiệu lực"]
    F --> E["Request đang chạy nhận lỗi, timeout hoặc outcome bất định"]
    F --> I["Idle connection trong pool có thể đã hỏng"]
    I --> B["Pool validate khi mượn / driver phát hiện lỗi"]
    B --> R["Loại connection hỏng, tạo connection vật lý mới"]
    R --> H["DB đã sẵn sàng nhận SQL"]
    H --> V["Đọc/ghi và commit thành công qua JDBC"]
    V --> G["Phục hồi ổn định theo tiêu chí đo"]
~~~

**Điểm cốt lõi:** Reference Java kiểu `Connection` không tương đương một session database còn sống. Một connection được mượn trước khi restart **không được mặc định sử dụng lại**. Một connection pool tốt có thể tự hủy và tạo lại connection vật lý, nhưng hành vi cụ thể phụ thuộc pool, driver, cấu hình validation và thời điểm lỗi.

### Ba trạng thái không nên đánh đồng

| Trạng thái | Dấu hiệu minh họa | Điều **chưa** chứng minh |
| --- | --- | --- |
| Database process chạy | Container/process báo running | DB đã nạp xong schema, hoàn tất recovery và nhận truy vấn |
| Có thể kết nối tới DB | TCP connect/login hoặc `getConnection()` thành công | Mọi câu SQL, bảng, quyền, transaction và pool đều lành mạnh |
| Ứng dụng thực sự phục hồi | Đường truy vấn và giao dịch JDBC thật thành công, lặp lại ổn định | Mọi nghiệp vụ phức tạp đều đúng nếu chưa test các đường đó |

Một phép thử chỉ gọi `SELECT 1` là **liveness smoke check cho đường SQL**, không phải kiểm chứng đủ một nghiệp vụ có bảng, quyền, mapping, transaction và commit.

## 3. Xác định tiêu chí phục hồi trước khi gây sự cố

Trước khi restart database test, hãy viết rõ **điều kiện nào khiến phép thử được xem là PASS**. Nếu chỉ đợi đến khi không còn exception, kết quả có thể là dương tính giả.

Ví dụ hợp đồng phục hồi:

- **R1 — Trước sự cố:** cùng đường JDBC có thể đọc bản ghi fixture và ghi một thao tác thử đã commit.
- **R2 — Khi DB không khả dụng:** request thất bại có giới hạn thời gian; không treo vô thời hạn hoặc giữ toàn bộ thread của pool.
- **R3 — DB lên lại:** ứng dụng **không cần restart** vẫn mượn được connection sử dụng được từ cùng `DataSource`.
- **R4 — Đọc:** truy vấn vào bảng nghiệp vụ trả đúng dữ liệu được commit **trước restart** (nếu DB dùng lưu trữ bền vững).
- **R5 — Ghi:** một transaction **mới**, có khóa thao tác duy nhất, được commit và quan sát lại từ một connection khác.
- **R6 — Tài nguyên:** pool dần loại kết nối cũ bị hỏng; không còn dấu hiệu tăng không giới hạn số connection pending/active hoặc số thread JDBC bị kẹt.
- **R7 — Ổn định:** nhiều truy vấn liên tiếp trong một khoảng quan sát đều thành công, không chỉ một lần ngay khi DB vừa mở.
- **R8 — Bất định:** các thao tác ghi bị gián đoạn trong lúc restart **không bị retry mù** và có cách kiểm tra trạng thái bằng idempotency key.

Có thể định nghĩa một khoảng chờ phục hồi tối đa cho môi trường test, ví dụ **60 giây**, rồi đo thực tế thay vì mặc định cứ đúng 60 giây là đạt. Giá trị này là ngưỡng minh họa: DBMS có recovery log hoặc migration dài có thể cần cấu hình khác.

### RTO và RPO liên quan nhưng khác nhau

- **RTO (Recovery Time Objective):** thời gian mục tiêu để dịch vụ trở lại khả năng đáp ứng nghiệp vụ chấp nhận được.
- **RPO (Recovery Point Objective):** lượng dữ liệu có thể mất tối đa theo chính sách khôi phục.

Một **restart thông thường trên lưu trữ bền vững** kỳ vọng dữ liệu đã commit vẫn còn; mất dữ liệu đã commit không phải kết quả chấp nhận được cho test này. Nhưng nếu bài kiểm thử cố ý xóa volume, khôi phục backup hoặc chuyển sang replica có độ trễ, nó đã trở thành một bài toán **disaster recovery/failover** với giả định RPO khác, không chỉ là restart database.

## 4. Thiết kế phép thử theo ba giai đoạn

Một kịch bản diễn tập rõ ràng:

| Giai đoạn | Hoạt động | Dữ liệu quan sát |
| --- | --- | --- |
| **Baseline** | Khởi động app và DB test, tạo fixture đã commit, đọc/ghi thành công | ID bản ghi, marker, pool metric, latency |
| **Fault window** | Restart có kiểm soát DB, đồng thời phát request đọc và một số thao tác có chủ đích | SQLException, thời gian timeout, trạng thái thread/pool |
| **Recovery** | DB báo sẵn sàng, service vẫn chạy, retry đọc **có giới hạn**, thực hiện giao dịch ghi mới | Đọc đúng marker cũ, ghi mới được commit, ổn định qua nhiều lần |
| **Cleanup/Report** | Dừng fault injection, dọn fixture, thu log/metric và phân loại kết quả | Mốc thời gian, PASS/FAIL, tài nguyên rò rỉ |

~~~mermaid
sequenceDiagram
    participant T as Test orchestrator
    participant A as Java service/JDBC
    participant DB as Test database
    T->>DB: Seed fixture, COMMIT
    T->>A: Baseline read/write
    A->>DB: SELECT / INSERT / COMMIT
    DB-->>A: Success
    T->>DB: Restart DB (test only)
    T->>A: Thử đường JDBC khi outage
    A--xDB: Connection lỗi / timeout
    Note over A: Xử lý lỗi, đóng connection hỏng
    T->>DB: Đợi database ready
    T->>A: Recovery probe bằng DataSource hiện có
    A->>DB: Borrow/validate/new SELECT
    DB-->>A: Marker đã commit
    A->>DB: INSERT token mới + COMMIT
    DB-->>A: Success
    T->>A: Quan sát lại từ connection độc lập
    A->>DB: SELECT theo token
    DB-->>A: Bản ghi đã commit
~~~

**Không khởi động lại Java service cùng lúc với DB** nếu mục tiêu là kiểm chứng khả năng tự hồi phục của connection pool đang chạy. Khi cả hai cùng restart, ứng dụng chỉ chứng minh được nó *khởi động sạch*, không chứng minh xử lý được các connection stale trong một tiến trình sống lâu.

## 5. Chuẩn bị schema và fixture có thể đối soát

Ví dụ một schema test tối giản, tương đối phổ biến giữa các DBMS:

~~~sql
CREATE TABLE jdbc_recovery_marker (
    marker_id BIGINT PRIMARY KEY,
    marker_text VARCHAR(100) NOT NULL
);

CREATE TABLE jdbc_recovery_operation (
    operation_key VARCHAR(64) PRIMARY KEY,
    payload VARCHAR(100) NOT NULL
);
~~~

Các nguyên tắc sử dụng:

1. **Tạo bảng qua migration hoặc test setup trước kịch bản**; không chạy `DROP TABLE`/`CREATE TABLE` trong lúc đo restart.
2. Dùng **database hoặc schema test có phân quyền**; không dùng bảng production.
3. Dùng `marker_id` và `operation_key` duy nhất cho từng lần diễn tập để tránh test khác tác động nhầm.
4. Seed marker bằng `PreparedStatement` và **commit thành công trước restart**.
5. Dữ liệu lưu trên volume bền vững, không phải container filesystem tạm bị xóa cùng lúc DB restart.
6. Sau restart, không chỉ kiểm tra server đáp ứng mà còn kiểm tra **marker cũ còn nguyên**.
7. Xóa fixture sau test bằng transaction rõ ràng; nếu có lỗi ghi giữa restart, **đối soát trước khi cleanup**.

Ví dụ seed có bind tham số:

~~~java
String sql = "INSERT INTO jdbc_recovery_marker "
           + "(marker_id, marker_text) VALUES (?, ?)";

try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql)) {
    ps.setLong(1, markerId);
    ps.setString(2, "baseline-v1");
    if (ps.executeUpdate() != 1) {
        throw new SQLException("Không tạo được recovery marker");
    }
}
~~~

Đoạn seed dùng giả định `DataSource` cấp connection ở `autoCommit=true` và statement kết thúc bình thường. Trong hạ tầng test có transaction manager hoặc pool đặt auto-commit khác, **phải commit tường minh** trước khi bắt đầu fault injection. Không dùng trạng thái “seed đã gọi hàm” thay cho xác nhận đã commit.

### Vì sao cần operation key duy nhất?

Một request ghi có thể đến DB ngay trước khi mất mạng, nhưng client không nhận được phản hồi. Nếu client chạy lại `INSERT` bằng **khóa mới**, nó có thể tạo tác động trùng. Dùng `operation_key` làm **idempotency key**, và đối chiếu payload sau khi kết nối mới hoạt động, sẽ giúp xác định liệu thao tác trước đó đã lưu hay chưa.

Khóa duy nhất trong database là một phần của cơ chế idempotency; ứng dụng vẫn phải có chính sách khi cùng khóa nhưng payload khác nhau, hoặc khi outcome chưa thể xác minh.

## 6. Ví dụ Java: recovery probe đọc qua cùng DataSource

Đoạn mã sau dùng Java 8+ và **API JDBC chuẩn**. Nó **không restart DB bằng JDBC**; phần restart do test orchestrator (container, CI hoặc công cụ vận hành được cấp quyền) thực hiện ở mục sau.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class JdbcRecoveryProbe {
    private final DataSource dataSource;

    public JdbcRecoveryProbe(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    public String readCommittedMarker(long markerId)
            throws SQLException {
        String sql = "SELECT marker_text "
                   + "FROM jdbc_recovery_marker "
                   + "WHERE marker_id = ?";

        // Dùng CHÍNH DataSource đang được ứng dụng sử dụng.
        try (Connection c = dataSource.getConnection()) {
            // isValid() là phép kiểm tra bổ sung, không thay
            // cho việc thực thi truy vấn nghiệp vụ.
            if (!c.isValid(2)) {
                throw new SQLException(
                        "Connection không hợp lệ sau khi mượn");
            }

            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setLong(1, markerId);
                ps.setQueryTimeout(5);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException(
                                "Thiếu marker đã commit trước restart");
                    }

                    String marker = rs.getString(1);
                    if (marker == null) {
                        throw new SQLException(
                                "Marker không được phép NULL");
                    }

                    if (rs.next()) {
                        throw new SQLException(
                                "Trùng marker_id bất thường");
                    }
                    return marker;
                }
            }
        }
    }

    public String findOperation(String operationKey)
            throws SQLException {
        String sql = "SELECT payload "
                   + "FROM jdbc_recovery_operation "
                   + "WHERE operation_key = ?";

        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setString(1, operationKey);
            ps.setQueryTimeout(5);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null; // Chưa tìm thấy thao tác.
                }
                return rs.getString(1);
            }
        }
    }
}
~~~

Điểm quan trọng:

- `dataSource` được **tiêm từ ứng dụng đang chạy**, không tạo một pool mới trong mỗi lần probe. Nếu tạo pool mới, test có thể pass mà không kiểm tra pool cũ có loại stale connection hay không.
- `Connection.isValid(2)` yêu cầu driver kiểm tra connection với timeout tính bằng **giây**, nếu được hỗ trợ. Kết quả `true` vẫn **không chứng minh** bảng/permission/transaction hoạt động; vì vậy tiếp tục thực thi `SELECT` thật.
- `ps.setQueryTimeout(5)` dùng **giây** và phụ thuộc khả năng hỗ trợ của driver. Nó không giới hạn thời gian `dataSource.getConnection()` chờ pool.
- `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` kể cả khi `SQLException` xảy ra. Với pool, `Connection.close()` thường trả logical connection về pool; pool/driver phải chịu trách nhiệm loại bỏ connection vật lý đã hỏng.
- Nếu `marker_id` không tồn tại, probe **thất bại** thay vì trả “ready” giả.
- Không log nguyên giá trị marker, SQL parameter hoặc thông tin kết nối nếu chúng có thể chứa dữ liệu nhạy cảm.

**Quan trọng về độ trễ:** Khi driver đang kẹt ở network I/O, thời gian thực tế để phát hiện lỗi còn phụ thuộc connect/socket/network timeout của driver và cơ chế pool. `isValid(2)` hoặc `setQueryTimeout(5)` không bảo đảm toàn bộ lời gọi trả về trong 2 hoặc 5 giây trong mọi hoàn cảnh.

## 7. Giao dịch ghi sau restart: xác minh từ connection độc lập

Một phép đọc thành công là điều kiện cần, nhưng chưa đủ nếu nghiệp vụ của ứng dụng còn **ghi dữ liệu**. Cần kiểm tra một transaction **mới bắt đầu sau khi DB đã hồi phục**, rồi đọc kết quả đã commit từ connection khác.

Ví dụ trong cùng lớp `JdbcRecoveryProbe`, hoặc một helper test riêng:

~~~java
public void insertCommittedOperation(
        String operationKey, String payload) throws SQLException {

    String sql = "INSERT INTO jdbc_recovery_operation "
               + "(operation_key, payload) VALUES (?, ?)";

    try (Connection c = dataSource.getConnection()) {
        c.setAutoCommit(false);

        boolean commitAttempted = false;

        try {
            try (PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setString(1, operationKey);
                ps.setString(2, payload);
                ps.setQueryTimeout(5);

                if (ps.executeUpdate() != 1) {
                    throw new SQLException(
                            "INSERT không tác động đúng một dòng");
                }
            }

            commitAttempted = true;
            c.commit();

        } catch (SQLException | RuntimeException failure) {
            // Rollback best effort khi còn connection; không suy
            // rằng rollback làm kết quả commit đã thử trở nên chắc chắn.
            try {
                if (!c.isClosed()) {
                    c.rollback();
                }
            } catch (SQLException rollbackError) {
                failure.addSuppressed(rollbackError);
            }

            if (commitAttempted) {
                // Đánh dấu outcome có thể chưa xác định ở
                // tầng điều phối test/nghiệp vụ, KHÔNG retry mù.
            }
            throw failure;
        }
    }
}
~~~

**Cách sử dụng và xác minh:**

~~~java
String token = "recovery-run-20261117-01"; // Duy nhất mỗi test run.
String payload = "post-restart-write";

probe.insertCommittedOperation(token, payload);

// findOperation mở một connection độc lập sau commit.
String stored = probe.findOperation(token);

if (!payload.equals(stored)) {
    throw new AssertionError(
            "Dữ liệu ghi sau restart không được commit đúng");
}
~~~

Khối `insertCommittedOperation` được đặt **bên trong lớp `JdbcRecoveryProbe`** ở mục 6, trước dấu `}` cuối. Các giá trị ví dụ phải được thay bằng token duy nhất cho mỗi lần chạy. Nếu bản ghi đã tồn tại vì một test trước, không bỏ qua lỗi duplicate để tuyên bố “write mới thành công”.

**Vì sao cần observer mới?** Writer có thể tự đọc thấy thay đổi chưa commit. Test cần chứng minh database đã lưu thay đổi khi transaction writer kết thúc và một session khác có thể nhìn thấy nó.

### Không đồng nhất lỗi ghi với rollback chắc chắn

Khi `commit()` ném `SQLException` vì mất phản hồi, database có thể đã commit nhưng client không nhận được xác nhận. Gọi `rollback()` trong `catch` chỉ là **best effort**, không biến kết quả thành “chưa commit”. Trước khi retry, cần đối soát `operation_key` trên một connection lành mạnh và áp dụng chính sách idempotency. Một lần `SELECT` không thấy bản ghi trong khi transaction cũ vẫn có thể đang hoàn tất cũng **chưa đủ** để kết luận an toàn cho mọi kiến trúc; cần biết quá trình recovery/failover đã ổn định và quy tắc nghiệp vụ cụ thể.

## 8. Poll có giới hạn: chờ đúng điều kiện, không chờ vô hạn

Sau khi DB process chạy lại, service có thể cần thời gian để pool loại connection cũ và tạo kết nối mới. Một recovery test nên thử lại **phép đọc an toàn** trong một khoảng thời gian hữu hạn.

~~~java
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

public final class RecoveryAwait {
    private RecoveryAwait() { }

    public static void awaitReadable(
            JdbcRecoveryProbe probe,
            long markerId,
            String expected,
            long timeoutSeconds)
            throws InterruptedException {

        if (timeoutSeconds <= 0) {
            throw new IllegalArgumentException(
                    "timeoutSeconds phải dương");
        }

        long deadline = System.nanoTime()
                + TimeUnit.SECONDS.toNanos(timeoutSeconds);

        SQLException lastFailure = null;

        while (System.nanoTime() - deadline < 0) {
            try {
                String actual =
                        probe.readCommittedMarker(markerId);

                if (!expected.equals(actual)) {
                    throw new AssertionError(
                            "Marker đã commit bị thay đổi sau restart");
                }
                return;

            } catch (SQLException transientFailure) {
                lastFailure = transientFailure;
                // Chỉ thao tác SELECT thuần được thử lại.
                // Không suy quy tắc này sang INSERT/UPDATE.
            }

            Thread.sleep(250L);
        }

        throw new AssertionError(
                "Không phục hồi đọc JDBC trong thời hạn",
                lastFailure);
    }
}
~~~

Ví dụ này biểu diễn cơ chế polling **theo trạng thái**, thay vì `Thread.sleep(30000)` rồi mặc định DB đã sẵn sàng.

**Những giới hạn cần nêu rõ:**

1. `timeoutSeconds` là **ngân sách vòng polling**, nhưng một lần `getConnection()` hay network read có thể vẫn chặn lâu hơn. Vì vậy phải cấu hình **pool acquisition timeout**, driver connect/socket/network timeout và query timeout tương ứng.
2. Không bắt `AssertionError` về marker bị thay đổi rồi tiếp tục retry. Đây là sai lệch dữ liệu, phải fail ngay.
3. Không bắt mọi `RuntimeException` rồi xem như DB chưa sẵn sàng. Lỗi lập trình/validation không phải lỗi recovery tạm thời.
4. Một lần thành công chứng minh đường đọc đã hoạt động **tại thời điểm đó**, chưa chứng minh độ ổn định. Có thể thêm các vòng đo thành công liên tiếp, theo dõi tỷ lệ lỗi và pool metric.
5. `Thread.sleep` ở đây chỉ là **backoff**, không phải điều kiện đúng sai. Dùng `System.nanoTime` cho deadline đơn điệu, không dùng đồng hồ hệ thống có thể bị chỉnh giờ.
6. Không dùng đoạn này để tự retry một thao tác thanh toán hay thay đổi dữ liệu chưa có idempotency.

### Có nên retry mọi SQLException?

Không. Demo trên retry `SELECT` trong một **kịch bản test đang biết DB sẽ restart**. Trong ứng dụng production, phải phân loại lỗi thận trọng:

- Có thể thử lại thao tác đọc **idempotent** khi lỗi kết nối tạm thời và còn ngân sách deadline.
- Không tự động thử lại vô hạn khi schema sai, thiếu quyền, dữ liệu không hợp lệ hay constraint violation.
- Không coi mọi lỗi SQLState nhóm `08` là bảo đảm rằng việc ghi trước đó chưa được áp dụng.
- Với `SQLTransientConnectionException`, `SQLNonTransientConnectionException` hoặc `SQLRecoverableException`, hiểu đó là tín hiệu phân loại từ driver, không phải lời bảo đảm giao dịch an toàn để replay.
- `SQLTimeoutException` có thể liên quan query timeout hoặc các loại timeout khác tùy driver; cần đối chiếu ngữ cảnh và mã lỗi.
- Dùng retry có giới hạn, exponential backoff có jitter khi cần tránh nhiều instance cùng retry một thời điểm.

## 9. Kết nối cũ, connection pool và connection validation

Mục tiêu quan trọng của bài test là chứng minh pool **loại bỏ session cũ bị hỏng và phục hồi khả năng cho mượn connection**.

### 9.1. Connection đang mượn trước restart

Một request có thể đang giữ `Connection` khi DB restart. Đừng thiết kế application theo kiểu:

~~~java
// Không nên giữ connection này như một session bất tử.
Connection cachedConnection = dataSource.getConnection();

// ... DB restart ...

cachedConnection.prepareStatement("SELECT ...");
~~~

Connection vật lý có thể đã bị đóng ở server hoặc network. Sau lỗi liên quan mất kết nối, hãy đóng/discard connection qua vòng đời thích hợp và để pool cấp một connection **mới, đã được kiểm chứng**. Không chia sẻ một `Connection` như singleton toàn service.

### 9.2. Idle connection bị stale

Pool có thể giữ nhiều connection idle từ trước restart. Một số pool kiểm tra khi mượn và bỏ kết nối chết, một số phụ thuộc vào validation/driver signal. Sau database restart, **lần mượn đầu tiên** có thể thất bại hoặc bị chậm trước khi pool loại hết stale connections.

Phép thử nên quan sát:

- Sau restart, một số request đầu có gặp lỗi kết nối không?
- Pool có tiếp tục phân phối cùng physical connection đã hỏng không?
- Mất bao lâu để tỉ lệ lỗi đọc/ghi trở về mức chấp nhận được?
- Số connection đang mượn, idle, pending có ổn định không?
- Có connection leak vì code bỏ qua `close()` sau exception không?
- Pool có tiếp tục mở kết nối mới quá nhanh khiến DB vừa lên lại bị quá tải không?

### 9.3. `isClosed`, `isValid` và câu SQL thật

| Công cụ | Có ích cho | Không đủ để kết luận |
| --- | --- | --- |
| `Connection.isClosed()` | Trạng thái đóng mà JDBC object biết | Session server thực sự còn khỏe |
| `Connection.isValid(seconds)` | Kiểm tra validity theo driver trong thời gian chỉ định | Schema, quyền, dữ liệu nghiệp vụ, transaction commit |
| `SELECT 1` hoặc validation query | Smoke test SQL đơn giản nếu dialect hỗ trợ | Bảng nghiệp vụ và quyền cụ thể |
| Query vào marker fixture | Kiểm chứng đường đọc thực, dữ liệu trước restart | Đường ghi/commit và nghiệp vụ khác |
| `INSERT` + `COMMIT` + observer khác | Kiểm chứng đường ghi và commit | Mọi transaction hoặc nghiệp vụ phức tạp |
| Metrics của pool/driver | Phát hiện tái tạo connection, lỗi và backlog | Tính đúng đắn dữ liệu nếu không có assertion |

**Không dùng `isClosed()==false` làm bằng chứng DB session còn hoạt động.** Một lỗi mạng có thể chưa được phát hiện cho tới khi thực hiện I/O tiếp theo.

### 9.4. Cấu hình pool cần được kiểm thử, không phỏng đoán

Một số tham số thường liên quan:

| Nhóm cấu hình | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| Acquisition timeout | Không chờ mượn connection vô hạn | Tên thuộc tính theo HikariCP/DBCP/pool khác |
| Connection validation | Kiểm tra trước hoặc trong khi mượn connection | Dùng `isValid` hoặc query kiểm tra theo pool |
| Max pool size | Giới hạn kết nối đồng thời tới DB | Pool quá lớn gây tải nặng khi reconnect |
| Max lifetime / idle timeout | Chu kỳ thay thế connection | Không bảo đảm riêng lẻ phát hiện sự cố restart tức thì |
| Connect/login timeout | Hạn chế chờ thiết lập session mới | Cấu hình JDBC driver và `DataSource` |
| Socket/network timeout | Hạn chế các thao tác chờ network I/O | Hành vi theo driver; `setNetworkTimeout` là cơ chế JDBC ở cấp connection |
| Keepalive / health checks | Phát hiện idle connection bị hỏng trước khi dùng | Chi phí ping và hỗ trợ tùy pool/driver |

Không có một bộ tên property hoặc giá trị mặc định áp dụng được cho mọi pool. Hãy dùng **tài liệu phiên bản pool/driver đang triển khai** và kiểm thử thực tế thay vì sao chép nguyên cấu hình trên Internet.

## 10. Readiness, liveness và hành vi khi DB chưa sẵn sàng

Giám sát vận hành cần phân biệt sức khỏe của **tiến trình Java** với khả năng **phục vụ request có DB**.

| Kiểm tra | Ý nghĩa | Có nên phụ thuộc DB? |
| --- | --- | --- |
| **Liveness** | Tiến trình Java còn sống và có thể tiếp tục hoạt động | Thường **không**; DB outage không nên gây restart-loop app |
| **Readiness** | Instance hiện có thể nhận loại request được giao | Có thể kiểm tra DB nếu API thực sự phụ thuộc DB |
| **Startup probe** | Ứng dụng đã hoàn tất bước khởi động cần thiết | Tùy yêu cầu khởi động/migration |
| **Synthetic business probe** | Đọc/ghi qua đường nghiệp vụ thực | Nên chạy có giới hạn ở môi trường phù hợp, không phải mỗi lần liveness |

Nếu liveness thất bại mỗi khi database tạm dừng, nền tảng orchestration có thể liên tục restart service trong lúc DB đang khởi động, làm tăng tải reconnect và khiến việc phục hồi khó hơn.

Ngược lại, readiness có thể báo **not ready** trong giai đoạn DB không khả dụng, để ngừng đưa request phụ thuộc DB tới instance. Nhưng một probe SQL liên tục cũng tạo tải: cần timeout ngắn, cadence phù hợp, tài khoản ít quyền và giới hạn số phép thử khi có nhiều instance.

### Phân biệt “DB đã start” và “app phục hồi”

Một container có thể chuyển trạng thái `running` trước khi DBMS:

- Hoàn tất crash recovery hoặc replay log.
- Mở endpoint nhận SQL.
- Áp dụng cấu hình quyền, schema hoặc migration.
- Sẵn sàng phục vụ nhiều connection đồng thời.
- Hoàn tất failover/leader election nếu hệ thống có HA.

Vì vậy đừng đợi process status duy nhất rồi tuyên bố PASS. Hãy **đợi readiness của DB**, sau đó chạy probe **qua cùng DataSource của app** và xác minh truy vấn/commit.

## 11. Xử lý transaction đang chạy khi restart

Đây là phần cần đặc biệt thận trọng. Cùng một “connection lost” có thể dẫn tới nhiều kết quả nghiệp vụ khác nhau, tùy lúc sự cố xảy ra.

### 11.1. Restart trước khi COMMIT được gửi

Nếu transaction đang ghi DML nhưng chưa gửi commit, database thường hủy phần chưa commit khi session mất, theo cơ chế phục hồi của DBMS hỗ trợ transaction. Tuy nhiên ứng dụng vẫn phải xử lý connection hỏng, và nếu có hệ thống ngoài DB đã nhận side effect (email, HTTP, message), rollback JDBC **không hoàn tác** những side effect đó.

### 11.2. Restart giữa COMMIT và phản hồi

~~~mermaid
sequenceDiagram
    participant A as Java service
    participant DB as Database
    A->>DB: UPDATE business record
    DB-->>A: Statement success
    A->>DB: COMMIT
    Note over DB: Có thể đã durable commit
    Note over A,DB: DB restart / response bị mất
    A--xDB: SQLException hoặc timeout
    Note over A: Outcome không xác định
~~~

Khi `Connection.commit()` báo lỗi vì mất kết nối, **không thể kết luận database chưa commit**. Database có thể đã hoàn tất commit rồi nhưng phản hồi bị mất. `rollback()` trên connection đã chết cũng không thể chứng minh rollback thành công.

Nếu ứng dụng retry cùng một thao tác bằng **khóa mới**, có thể xảy ra ghi trùng. Với thanh toán, chuyển tiền hoặc tạo đơn hàng, hậu quả có thể nghiêm trọng.

### 11.3. Thiết kế retry với idempotency key

Một hướng phổ biến:

1. Caller cấp hoặc server tạo một **operation key ổn định** cho một ý định nghiệp vụ.
2. Database lưu operation key trong một bảng có **UNIQUE/PRIMARY KEY** cùng kết quả/tác động nghiệp vụ.
3. Nếu có lỗi mạng sau khi gửi write/commit, **không tự kết luận fail**.
4. Khi DB và connection mới đã sẵn sàng, tra cứu operation key và xác minh payload/trạng thái.
5. Nếu key tồn tại với cùng nội dung và trạng thái đã commit, trả lại kết quả hoặc đánh dấu đã hoàn tất.
6. Nếu key tồn tại nhưng payload khác, báo xung đột; không tự ghi đè.
7. Nếu chưa thấy key, quyết định replay phải dựa trên quy tắc transaction/failover đã ổn định, idempotency và khả năng thao tác trước còn đang chạy; không xem một lần đọc vắng mặt là bằng chứng phổ quát.

Ở nơi lưu trạng thái, có thể phân biệt `PENDING`, `COMMITTED`, `FAILED` và `UNKNOWN` theo mô hình nghiệp vụ. Cơ chế xác nhận phải được thiết kế phù hợp với hệ thống thật.

### 11.4. Retry cho READ khác retry cho WRITE

| Thao tác | Khi mất kết nối | Cách xử lý gợi ý |
| --- | --- | --- |
| `SELECT` thuần, không side effect | Có thể thử lại bằng connection mới nếu còn deadline | Bounded retry, kiểm tra kết quả, không retry vô hạn |
| `UPDATE` có khóa idempotency và điều kiện rõ | Có thể cần đối soát trước khi retry | Chỉ retry theo contract nghiệp vụ |
| `INSERT` tạo bản ghi bằng ID tự tăng | Có nguy cơ tạo hai bản ghi nếu lần đầu đã commit | Dùng operation key/unique constraint |
| `COMMIT` báo lỗi network | Outcome có thể không xác định | Tra cứu trạng thái khi DB phục hồi |
| `rollback()` thất bại | Không chắc transaction đã được hoàn tác | Không dùng connection cũ, ghi nhận và đối soát |
| `SAVEPOINT` trong transaction chết | Không thể coi savepoint là nơi khôi phục session mới | Bắt đầu transaction mới theo logic nghiệp vụ |

**Không lấy việc SQLState bắt đầu bằng `08` làm giấy phép replay một giao dịch ghi.** Nhóm SQLState 08 thường nói về lỗi kết nối, không chứng minh transaction cuối cùng chưa được commit.

## 12. Timeouts và tránh “retry storm” khi DB vừa lên

Sau restart, nhiều instance Java có thể cùng phát hiện DB hoạt động trở lại và đồng loạt tạo connection hoặc replay request. Nếu retry không giới hạn, DB vừa phục hồi có thể bị quá tải.

Một chính sách hợp lý cần đồng bộ:

- **Pool acquisition timeout**: hạn chế chờ connection khi pool đang khôi phục.
- **Login/connect timeout**: hạn chế thời gian mở session mới.
- **Statement query timeout**: hạn chế thời gian thực thi SQL, theo khả năng driver.
- **Connection network/socket timeout**: xử lý network I/O treo, theo JDBC/driver.
- **Request/job deadline**: giới hạn tổng thời gian nghiệp vụ, không chỉ một câu SQL.
- **Số lần retry tối đa** và **backoff có jitter**: giảm thundering herd.
- **Circuit breaker/load shedding** khi cần: từ chối có kiểm soát thay vì để toàn bộ request chiếm thread.
- **Quy tắc idempotency**: đặc biệt quan trọng với thao tác ghi.

### Ví dụ các ngưỡng chỉ để thảo luận

| Giới hạn | Giá trị ví dụ | Thực chất áp dụng |
| --- | ---: | --- |
| Pool acquisition | 2 giây | Tùy connection pool |
| Connect/login | 5 giây | Tùy driver/`DataSource` |
| Statement query | 3 giây | `Statement.setQueryTimeout(3)` |
| Network | 10 giây | `Connection.setNetworkTimeout(executor, 10_000)` khi hỗ trợ |
| Tổng recovery polling | 60 giây | Test harness theo `System.nanoTime` |
| Khoảng backoff ban đầu | 250 ms | Policy test/retry; production nên có jitter |

Không cộng các số trên thành một deadline chính xác. Một request có thể mượn connection nhiều lần, thực thi nhiều statement hoặc fetch kết quả qua nhiều yêu cầu mạng. Network timeout không phải tổng thời gian request, và `setQueryTimeout` không bảo đảm giới hạn bước `getConnection()`.

**Cẩn trọng khi shutdown executor của network timeout:** Nếu ứng dụng dùng `setNetworkTimeout(Executor, ms)`, executor cần còn hoạt động khi driver có thể cần hủy connection. Không tạo executor mới mỗi request rồi `shutdown()` trong khi connection còn mở.

## 13. Kịch bản integration test điều phối DB restart

Chúng ta tách rõ **thao tác điều khiển môi trường** và **xác minh JDBC**.

### 13.1. Test orchestrator chịu trách nhiệm gì?

Test harness có quyền trên **database test được cấp phép** cần:

1. Khởi động DB test ở trạng thái sạch nhưng **không xóa dữ liệu bền vững** giữa các lần restart.
2. Khởi chạy hoặc giữ nguyên ứng dụng/JVM chứa `DataSource`.
3. Seed marker, xác minh baseline, ghi thời điểm bắt đầu fault.
4. Thực hiện một lệnh restart DB bằng công cụ test môi trường (container/process/service).
5. Chờ DB không khả dụng đủ để test quan sát failure, nếu cần kịch bản outage.
6. Cho phép DB khởi động lại và đợi cơ chế readiness của DB.
7. Gọi recovery probe **qua cùng DataSource/JVM đang sống**.
8. Xác minh marker cũ, giao dịch mới được commit và kết quả đọc bằng connection mới.
9. Lặp lại truy vấn cho giai đoạn ổn định, thu pool metric, dọn fixture và xuất báo cáo.

**JDBC không có API chuẩn “restart database server”.** Không đưa quyền restart production vào ứng dụng nghiệp vụ. Trong CI có thể dùng Testcontainers hoặc một môi trường tích hợp tương đương; trong diễn tập vận hành cần phê duyệt và phương án khôi phục rõ.

### 13.2. Pseudocode JUnit 5 có ranh giới rõ

~~~java
// Pseudocode test harness: RestartController và
// TestDatabaseContext là thành phần do dự án triển khai.
// KHÔNG có sẵn trong JDBC hay JUnit.

@Test
void sameApplicationRecoversAfterDatabaseRestart()
        throws Exception {

    // Context giữ một DataSource/JVM xuyên suốt bài test.
    TestDatabaseContext context =
            TestDatabaseContext.startPersistentTestDatabase();

    try {
        JdbcRecoveryProbe probe =
                new JdbcRecoveryProbe(context.applicationDataSource());

        long markerId = context.uniqueMarkerId();
        context.seedAndCommitMarker(markerId, "baseline-v1");

        assertEquals("baseline-v1",
                probe.readCommittedMarker(markerId));

        // Restart database test, KHÔNG restart Java service.
        context.restartDatabaseOnly();
        context.awaitDatabaseReady();

        RecoveryAwait.awaitReadable(
                probe, markerId, "baseline-v1", 60);

        String token = context.uniqueOperationKey();
        probe.insertCommittedOperation(token, "after-restart");
        assertEquals("after-restart",
                probe.findOperation(token));

        context.assertPoolRecovered();
        context.assertStableReads(probe, markerId);

    } finally {
        context.close();
    }
}
~~~

Ví dụ này thể hiện **kiến trúc của phép thử**, không thể biên dịch chỉ với JDK/JUnit vì các method `TestDatabaseContext` là test harness giả định. Khi triển khai, phải bảo đảm:

- `restartDatabaseOnly()` thực sự restart **cùng DB dùng storage bền vững**, không tạo database rỗng mới.
- `applicationDataSource()` trả về **cùng một instance pool** mà app dùng trước restart. Nếu context tạo pool mới ở giai đoạn recovery, test sẽ không kiểm tra được stale pool.
- `awaitDatabaseReady()` không chỉ kiểm tra process running.
- `context.close()` dọn fixture và hạ tầng đúng phạm vi; nếu test thất bại phải giữ thông tin lỗi gốc và ghi nhận lỗi cleanup.

### 13.3. Có nên dùng Thread.sleep để xác nhận phục hồi?

Không dùng `Thread.sleep(30000)` làm **oracle**. Có thể sử dụng delay ngắn có giới hạn làm **backoff giữa các lần probe** như mục 8, nhưng quyết định PASS phải dựa trên **đọc/ghi thật thành công** và các assertion dữ liệu.

### 13.4. Phân biệt hard restart và graceful restart

Cần chạy ít nhất hai loại fault nếu hệ thống có yêu cầu độ tin cậy cao:

| Kịch bản | Vì sao hữu ích |
| --- | --- |
| **Graceful DB restart** | Server có thể đóng session có thứ tự, cho transaction hoàn tất trước khi dừng |
| **Abrupt process stop/crash** | Kiểm tra mất socket bất ngờ, crash recovery, rollback transaction chưa commit |
| **Network interruption** | Client có thể treo mà DB vẫn đang chạy; kiểm tra socket/network timeout khác với restart |
| **HA failover** | Endpoint/leader có thể thay đổi; cần kiểm tra DNS, proxy, role và khả năng ghi |
| **Application restart** | Kiểm tra startup sạch, nhưng **không thay** bài test DB restart khi app giữ pool cũ |

Từng kịch bản cần phạm vi và chỉ tiêu riêng. Không suy kết quả của graceful restart sang crash hoặc failover.

## 14. Kịch bản in-flight: request đang chạy lúc DB biến mất

Chỉ kiểm tra đọc sau restart chưa đủ để mô tả hành vi trong **khoảng lỗi**. Có thể cần ít nhất những biến thể:

### 14.1. Truy vấn đọc đang chạy

1. Bắt đầu một truy vấn có thời gian đủ dài hoặc một `ResultSet` đang fetch từ server test.
2. Orchestrator restart DB giữa lúc truy vấn.
3. Xác minh Java không kẹt mãi, lỗi được trả lên/tạo response thất bại có kiểm soát.
4. Đóng `ResultSet`, `PreparedStatement`, `Connection` nhờ `try-with-resources`.
5. Mượn **connection mới** sau recovery để đọc lại.
6. Không coi một phần dữ liệu đã xuất là một báo cáo hoàn chỉnh.

### 14.2. Transaction có thay đổi chưa commit

1. Bắt đầu transaction `setAutoCommit(false)`.
2. Ghi DML và **chưa commit**.
3. Restart DB.
4. Sau recovery, mở connection mới, xác minh các thay đổi chưa commit không được lưu nếu DBMS bảo đảm rollback phần chưa commit khi crash.
5. Không thử dùng lại connection/savepoint của transaction trước restart.

### 14.3. Commit vừa được gửi

Đây là kịch bản khó kiểm soát timing nhất. Test harness cần fault injection đúng vị trí và **operation key** để đối chiếu. Kết quả hợp lệ của test không nên mặc định là “mọi lần commit lỗi đều rollback”. Thay vào đó, assert hệ thống **không tạo trùng thao tác và có cách phân loại outcome** sau khi DB đã hoạt động ổn định.

### 14.4. Nhiều request đồng thời

Một connection pool có thể hoạt động ổn với một request thử nhưng thất bại khi nhiều request cùng reconnect:

- Cần kiểm tra giới hạn pool và số thread pending.
- Request không được giữ connection hỏng trong một vòng retry không giới hạn.
- Có biện pháp giảm tải khi DB chưa ready.
- Sau hồi phục, lượng connection mới không vượt ngân sách DBMS.
- Có cơ chế quan sát latency, lỗi và hồi phục, không chỉ một phép SELECT thành công.

Dùng test concurrency có giới hạn thread và deadline. Không tạo hàng nghìn request vô hạn chỉ để “thử tải” lên một hạ tầng chưa được chuẩn bị.

## 15. Metric cần thu để chứng minh recovery

Một phép thử vận hành tốt cần **mốc thời gian và số liệu** để so sánh các lần chạy.

| Metric / sự kiện | Mục đích |
| --- | --- |
| `db_restart_triggered_at` | Mốc orchestrator bắt đầu restart |
| `db_ready_at` | DB báo đã sẵn sàng |
| `first_successful_jdbc_read_at` | Lần đầu app đọc marker thành công |
| `first_successful_post_restart_commit_at` | Lần đầu ghi và commit mới được quan sát |
| `stable_recovery_at` | Mốc đáp ứng tiêu chí ổn định nhiều lần liên tiếp |
| JDBC connection failures | Phân biệt lỗi trong fault window với lỗi kéo dài sau recovery |
| Connection pool active/idle/pending | Phát hiện connection hỏng bị giữ, backlog và cạn pool |
| Connection creation/validation failures | Kiểm tra khả năng thay thế stale connection |
| Request error rate / latency | Đo tác động lên chức năng thực tế |
| Query timeout / pool timeout / network timeout | Phân biệt loại timeout thay vì gom chung |
| Thread đang chờ JDBC | Nhận diện yêu cầu treo hoặc leak |
| Pending/unknown operations | Theo dõi thao tác ghi cần đối soát sau restart |

Không phải pool nào cũng có cùng tên metric. Hãy lấy tên thực tế từ công cụ giám sát đang dùng và **định nghĩa phép đo** rõ ràng. Ví dụ “recovery duration” có thể đo từ lúc gây sự cố tới khi ổn định, hoặc từ lúc DB ready tới khi app phục hồi. Hai phép đo này trả lời **hai câu hỏi khác nhau**; không nên trộn mà không ghi nhãn.

### Định nghĩa một phép đo có thể so sánh

~~~text
T0 = lúc orchestrator bắt đầu restart DB
T1 = lúc DB readiness thành công
T2 = lúc probe đọc marker thành công lần đầu
T3 = lúc probe ghi/commit và observer xác nhận thành công
T4 = lúc giai đoạn ổn định đạt chuẩn

DB downtime        = T1 - T0
App recovery lag   = T4 - T1
End-to-end recovery = T4 - T0
~~~

Nếu T2 xảy ra trước khi pool xử lý xong các connection stale khác, chỉ đọc thành công một lần vẫn chưa chắc T4 đã đạt. Có thể yêu cầu ví dụ **10 lượt đọc liên tiếp thành công trong 10 giây** và một giao dịch ghi mới được xác nhận; ngưỡng là hợp đồng của môi trường/ứng dụng, không phải quy tắc JDBC cố định.

### Logging an toàn

Nên log:

- Query ID cố định, như `recovery.marker.read.v1`.
- Loại lỗi, thời điểm, SQLState và vendor error code nếu chính sách cho phép.
- Pool instance/role, thời gian chờ, số retry, trạng thái connection bị loại.
- Operation key **đã băm hoặc được quản lý theo chính sách**, tránh đưa định danh khách hàng làm metric labels.

Không log:

- Mật khẩu/URL chứa credential.
- SQL có tham số nhạy cảm được nội suy.
- Dữ liệu hàng hoặc payload nghiệp vụ.
- Full stack trace JDBC chưa được kiểm soát trong response HTTP.
- Raw operation ID/tenant/user ID làm nhãn metric high-cardinality.

## 16. Định nghĩa PASS/FAIL bằng trạng thái dữ liệu và tài nguyên

Một bảng kiểm định gợi ý:

| Điều kiện | PASS | FAIL |
| --- | --- | --- |
| Marker đã commit trước restart | Đọc lại đúng giá trị | Thiếu hoặc giá trị thay đổi |
| Pool phục hồi | Có connection mới dùng được qua cùng DataSource | Chỉ hoạt động sau khi restart app / tạo pool mới |
| Request trong outage | Có giới hạn thời gian và lỗi được kiểm soát | Treo vô hạn, cạn thread/pool không phục hồi |
| Giao dịch ghi sau restart | Commit thành công, observer mới đọc thấy | Chỉ writer nhìn thấy, hoặc kết quả không nhất quán |
| Connection cũ | Được đóng/loại khi phát hiện hỏng | Liên tục đưa session chết vào thao tác mới |
| Ổn định sau phục hồi | Đạt số lượt/độ trễ/tỉ lệ lỗi đã định | Chỉ một lần probe pass rồi lỗi trở lại |
| Ghi bị gián đoạn | Có đối soát/idempotency | Retry tạo bản ghi trùng hoặc mất theo dõi |
| Dọn tài nguyên | Không có dấu hiệu leak connection/thread | Pool pending/active tăng không giảm sau recovery |
| Quan sát | Có timeline và phân loại lỗi | Chỉ có log “DB started” |
| Phạm vi test | Chỉ trên môi trường được cấp quyền | Tác động dữ liệu/DB production ngoài kế hoạch |

Không nên thiết kế test **chỉ thành công nếu có một loại exception cụ thể** trong outage. Tùy thời điểm và driver, lỗi có thể xuất hiện ở `getConnection`, `isValid`, `executeQuery`, `ResultSet.next` hoặc `commit`. Oracle chính của phép thử là **thời gian thất bại có giới hạn, tài nguyên được giải phóng và sau recovery nghiệp vụ hoạt động đúng**.

## 17. Những lỗi thiết kế thường gặp

### 17.1. Restart ứng dụng cùng database

Nếu mỗi lần DB restart đều restart Java service, pool luôn được tạo mới. Test không chứng minh pool **tự phục hồi** sau stale connections. Phải để JVM và `DataSource` giữ nguyên trong kịch bản chính.

### 17.2. Chỉ kiểm tra `Connection.isClosed()`

~~~java
if (!connection.isClosed()) {
    // Sai: coi connection đã chắc chắn khỏe.
}
~~~

`isClosed()==false` không phải bằng chứng server-side session vẫn sống. Hãy dùng validation theo driver/pool và thao tác JDBC thật.

### 17.3. Tạo một DataSource mới riêng cho recovery probe

Nếu probe tạo pool mới sau restart, nó tránh được vấn đề stale connection trong pool cũ, làm test **dương tính giả**. Probe phải sử dụng cùng DataSource mà application đang dùng trước và sau sự cố.

### 17.4. Retry write vô hạn

~~~java
while (true) {
    try {
        createPayment();
        break;
    } catch (SQLException ignored) {
        // Nguy cơ tạo nhiều payment nếu lần trước đã commit.
    }
}
~~~

Mất phản hồi không chứng minh câu ghi thất bại. Dùng idempotency/đối soát và giới hạn retry, không loop vô hạn.

### 17.5. Xem `SELECT 1` là mọi nghiệp vụ đã khỏe

Một validation query có thể thành công trong khi bảng nghiệp vụ chưa có quyền, schema sai hoặc transaction ghi bị lỗi. Hãy kiểm tra **marker đã commit** và **ghi mới/đọc lại** theo phạm vi ứng dụng.

### 17.6. Không kiểm soát timeout mượn connection

`Statement.setQueryTimeout` không giúp khi thread đang chờ `DataSource.getConnection()` vì pool cạn. Pool acquisition và connect timeout phải được cấu hình riêng.

### 17.7. Dùng readiness lỗi để kích hoạt restart-loop

Nếu liveness phụ thuộc DB, orchestration có thể restart hàng loạt instance khi DB bảo trì ngắn. Tách readiness với liveness theo mục tiêu hệ thống.

### 17.8. Ghi nhầm kết quả ngay sau restart

Một lần `SELECT` thành công có thể xảy ra khi pool vẫn có nhiều connection stale hoặc DB vừa nhận một vài request rồi lại thất bại. Cần tiêu chí **ổn định liên tiếp**, đo lỗi và tài nguyên.

### 17.9. Thử trên database không có dữ liệu bền vững

Nếu test restart làm xóa volume hoặc tạo DB mới, marker trước restart sẽ mất vì test harness, không phải vì driver không phục hồi. Phải ghi rõ phạm vi restart giữ nguyên storage.

### 17.10. Nuốt mọi `SQLException` rồi trả dữ liệu mặc định

~~~java
try {
    return repository.load();
} catch (SQLException ignored) {
    return Collections.emptyList(); // Có thể che DB outage.
}
~~~

Đây là lỗi thiết kế nghiêm trọng nếu “không có bản ghi” có nghĩa nghiệp vụ khác với “DB đang không khả dụng”. Tầng service cần lỗi được chuẩn hóa và chính sách fallback có chủ đích.

## 18. Bài tập thực hành

### Bài 1 — Phân biệt ba loại sẵn sàng

Database container báo `running`, ứng dụng mượn được `Connection` nhưng query vào bảng `orders` ném lỗi vì migration chưa xong.

**Hỏi:** Có thể tuyên bố ứng dụng đã phục hồi nghiệp vụ chưa?

**Gợi ý:** Chưa. Process running và connection thành công không chứng minh schema/permission/business query đã sẵn sàng.

### Bài 2 — Stale connection pool

Service vẫn chạy; DB restart; pool giữ 20 connection idle từ trước restart. Sau đó một request dùng `isClosed()==false` để quyết định tiếp tục truy vấn.

**Hỏi:** Điều gì có thể sai? Test nên kiểm tra hành vi nào?

**Gợi ý:** Session thật có thể chết dù Java object chưa biết. Pool cần validation/loại connection hỏng rồi tạo mới; test qua cùng DataSource và SQL thật.

### Bài 3 — Đo thời gian phục hồi

Mốc `T0` là 10:00:00, DB ready ở `T1` 10:00:18, lần đọc đầu thành công `T2` 10:00:21, lần commit mới được xác minh `T3` 10:00:23, trạng thái ổn định `T4` 10:00:29.

**Hỏi:** App recovery lag và end-to-end recovery là bao nhiêu?

**Gợi ý:** `T4-T1 = 11 giây`; `T4-T0 = 29 giây`. Không dùng riêng T2 để tuyên bố đã ổn định.

### Bài 4 — Commit chưa chắc chắn

Ứng dụng gửi `COMMIT` cho một order, network bị ngắt và JDBC ném `SQLException`. Request được gửi lại.

**Hỏi:** Có nên tạo order mới ngay không? Cần thiết kế điều gì?

**Gợi ý:** Không retry mù. Dùng idempotency key/unique constraint và tra cứu trạng thái đã commit khi DB phục hồi, sau đó mới quyết định.

### Bài 5 — Vì sao query timeout không đủ?

Pool không có connection khả dụng; 100 thread chờ `getConnection()`. Mọi `PreparedStatement` đều có `setQueryTimeout(3)`.

**Hỏi:** Timeout đó có giải phóng các thread đang chờ pool không?

**Gợi ý:** Không; chưa tạo statement để áp dụng query timeout. Cần pool acquisition timeout, quản lý thread và backpressure.

### Bài 6 — Thiết kế fault injection

Hãy mô tả phép thử gồm hai biến thể: restart DB khi không có transaction đang chạy, và restart ngay lúc một transaction ghi chuẩn bị commit.

**Gợi ý:** Biến thể đầu xác minh pool reconnect, marker và giao dịch mới. Biến thể thứ hai phải có operation key và phép đối soát, không assert mọi lỗi commit đồng nghĩa rollback.

### Bài 7 — Health checks

Một hệ thống đặt liveness probe thực hiện `SELECT 1`. Khi DB bảo trì, toàn bộ pod Java tự restart liên tục.

**Hỏi:** Cách tách liveness/readiness phù hợp hơn là gì?

**Gợi ý:** Liveness kiểm tra tiến trình Java còn khỏe; readiness có thể phản ánh khả năng đáp ứng chức năng phụ thuộc DB. Synthetic business probe riêng kiểm tra sâu có tần suất/timeout phù hợp.

### Bài 8 — Phân tích số liệu

Sau DB ready, request error rate giảm về 0 nhưng `pool.pendingConnections` tiếp tục tăng và số thread chờ JDBC không giảm.

**Hỏi:** Có nên tuyên bố phục hồi hoàn toàn không?

**Gợi ý:** Chưa. Cần kiểm tra load, connection leak, acquire timeout, số thread bị kẹt và tiêu chí ổn định tài nguyên; error rate ngắn hạn có thể che backlog chưa xử lý.

## 19. Checklist diễn tập phục hồi an toàn

- [ ] Test được thực hiện trên **database test được cấp phép**, không gây restart production ngoài kế hoạch.
- [ ] Có bản sao/volume bền vững để dữ liệu đã commit tồn tại qua restart.
- [ ] Java service và **DataSource instance giữ nguyên** trong kịch bản chính.
- [ ] Có marker được seed/commit trước restart và mã định danh test run riêng.
- [ ] Có readiness của DB, nhưng không xem readiness đó là bằng chứng app recovery.
- [ ] Dùng `PreparedStatement` tham số hóa để đọc marker và ghi operation key.
- [ ] Có thời gian chờ mượn pool, connect/login, query và network phù hợp với driver.
- [ ] Probe đọc có retry **giới hạn** và không nuốt sai khác dữ liệu.
- [ ] Giao dịch ghi sau restart được **commit và kiểm tra qua connection khác**.
- [ ] Có kịch bản connection stale, in-flight read và transaction ghi bị gián đoạn.
- [ ] Không tự động replay thao tác ghi có **uncertain commit outcome**.
- [ ] Có idempotency key/unique constraint và chiến lược đối soát.
- [ ] Pool loại connection hỏng, không có leak hoặc backlog tăng không giới hạn.
- [ ] Liveness không gây restart-loop khi DB tạm không khả dụng.
- [ ] Có timeline T0..T4, metric pool, lỗi SQL và request latency.
- [ ] Dữ liệu log và metric không chứa credential, SQL parameters hay payload nhạy cảm.
- [ ] Fixture, pool và tài nguyên fault injection được dọn an toàn sau test.
- [ ] Kết quả PASS chỉ được tuyên bố khi **đọc, ghi và tiêu chí ổn định** cùng đạt.

**Kết luận:** Trong JDBC, **xác minh khả năng phục hồi sau khi cơ sở dữ liệu khởi động lại** không dừng ở việc quan sát DB process hay gọi `Connection.isValid()`. Một phép thử đáng tin cậy phải giữ **Java service và DataSource đang chạy**, gây restart có kiểm soát, xác nhận các connection cũ không còn được sử dụng sai, đo việc pool tạo kết nối lành mạnh, **đọc lại dữ liệu đã commit** và **ghi/commit dữ liệu mới được quan sát từ connection độc lập**. Khi kết hợp timeout, retry có giới hạn, idempotency, giám sát tài nguyên và tiêu chí ổn định rõ ràng, hệ thống mới có cơ sở để khẳng định đã phục hồi **đúng chức năng và an toàn dữ liệu**.
