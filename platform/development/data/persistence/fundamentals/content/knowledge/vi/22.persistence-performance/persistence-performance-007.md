# Kích thước giao dịch và đánh đổi giữa thông lượng với thời gian giữ khóa

Khi tối ưu tầng persistence, một đề xuất thường gặp là **“gom nhiều câu SQL vào một transaction để tăng hiệu năng”**. Cách này có thể giảm số lượt commit và tăng số hàng xử lý mỗi giây. Nhưng nếu transaction kéo dài, những khóa mà nó nắm giữ cũng có thể tồn tại lâu hơn; các transaction khác phải chờ, độ trễ cuối (p95/p99) tăng, thậm chí xuất hiện deadlock hoặc pool cạn.

Đề xuất ngược lại — **“commit sau mỗi hàng để giảm thời gian giữ khóa”** — cũng không phải luôn đúng. Quá nhiều transaction nhỏ có thể tăng chi phí commit, WAL, kết nối và round trip, làm thông lượng xử lý khối lượng lớn giảm. Nghiêm trọng hơn, tách một nghiệp vụ cần nguyên tử thành nhiều transaction có thể làm mất tính nhất quán.

Bài thuộc chương **Hiệu năng** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Trọng tâm là cách ứng dụng Java xác định ranh giới transaction trong cơ sở dữ liệu quan hệ, kiểm soát đồng thời, xử lý lỗi/retry, quản lý JDBC Connection và đo hiệu năng bằng dữ liệu thực. Ví dụ sử dụng **PostgreSQL và Java JDBC**; tính chất khóa, WAL, group commit và DDL của DBMS khác có thể không giống PostgreSQL.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **kích thước giao dịch**, **thời gian giao dịch**, **số hàng mỗi commit** và **thời gian giữ khóa**.
2. Giải thích vì sao transaction lớn có thể giúp **throughput theo hàng/giây** nhưng làm giảm khả năng đồng thời.
3. Phân tích chi phí **WAL/COMMIT, network round trip, row lock, MVCC, bộ nhớ và rollback**.
4. Chọn ranh giới transaction theo **bất biến nghiệp vụ** trước khi chọn batch size.
5. Viết Java JDBC thực hiện **transaction theo lô có giới hạn**, quản lý lỗi và Connection an toàn.
6. Thiết kế backfill/import nhiều lô mà vẫn có **checkpoint/idempotency**.
7. Đo **TPS, rows/s, latency p95/p99, lock wait, pool pending, replication lag** để chọn trade-off.
8. Nhận biết những trường hợp không được chia transaction, như chuyển tiền nguyên tử hoặc ghi nhiều bảng có ràng buộc cùng commit.

## 2. Kích thước giao dịch không chỉ là số hàng

Một transaction có thể lớn theo nhiều chiều:

| Chiều đo | Ví dụ | Hệ quả |
|---|---|---|
| **Số hàng đọc/ghi** | UPDATE 50.000 hàng | Nhiều row versions, WAL và khóa |
| **Số câu SQL** | 500 lệnh UPDATE trên một Connection | Nhiều round trip hoặc xử lý lặp |
| **Lượng dữ liệu thay đổi** | Cập nhật cột JSON lớn trên 1.000 hàng | WAL/I/O lớn dù số hàng không quá nhiều |
| **Thời gian mở transaction** | BEGIN rồi chờ dịch vụ HTTP 20 giây | Giữ connection/snapshot và khóa đã lấy trong thời gian chờ |
| **Số đối tượng tranh chấp** | Cập nhật hàng cùng khóa nóng với nhiều request khác | Độ trễ lock wait tăng mạnh |
| **Số thao tác nghiệp vụ** | Ghi nhiều sự kiện độc lập trong một batch | Tăng lượng công việc phải rollback nếu lỗi |

**Một transaction chạm 5 hàng nhưng giữ khóa 30 giây có thể gây hại hơn một transaction xử lý 1.000 hàng trong 100 ms**, nếu 5 hàng đầu là những khóa mà nhiều request khác cần. Vì vậy cần đo cả **kích thước** và **thời gian**, kèm mức tranh chấp.

### 2.1. Phân biệt batch và transaction

**Batch** là cách gom nhiều thao tác để gửi/thực hiện hiệu quả hơn. **Transaction** là ranh giới nguyên tử được commit hoặc rollback như một đơn vị.

- Một **JDBC executeBatch()** có thể thực thi nhiều SQL trong **một transaction** nếu Connection được cấu hình phù hợp.
- Một batch logic gồm 10.000 bản ghi có thể được xử lý bằng **100 transaction**, mỗi transaction 100 bản ghi.
- Nếu vẫn bật auto-commit, không được mặc định toàn bộ batch là một transaction nguyên tử; chi tiết phụ thuộc JDBC driver và cách thực thi.
- Gộp dữ liệu vào **một câu UPDATE ... WHERE** có thể giảm round trip nhưng câu lệnh vẫn có thể cập nhật rất nhiều hàng và giữ khóa tới khi transaction kết thúc.

**“Batch size = 500” không tự trả lời “đơn vị nào phải commit cùng nhau?”**.

## 3. Vòng đời transaction và thời gian giữ khóa

Với PostgreSQL, những **row lock do UPDATE/DELETE hoặc SELECT FOR UPDATE lấy được** thường được giữ tới khi transaction kết thúc bằng **COMMIT** hoặc **ROLLBACK**, không tự giải phóng ngay khi một câu SQL hoàn tất. Chi tiết từng lock mode và trường hợp rollback về savepoint phụ thuộc ngữ cảnh; điều cần nhớ ở đây là **thời điểm kết thúc transaction** quyết định thời gian nắm giữ nhiều khóa quan trọng.

~~~text
T0          T1              T2            T3               T4
|-----------|---------------|-------------|----------------|
BEGIN       UPDATE row A    Gọi dịch vụ   UPDATE row B      COMMIT
            lấy row lock A  bên ngoài                      nhả khóa
                            mất 3 giây

Khoảng giữ khóa A: từ T1 -------------------------------- T4
Khoảng giữ Connection/transaction: T0 ------------------- T4
~~~

Gọi một HTTP API, chờ message broker, ghi file hoặc sleep trong khoảng T1–T4 không làm gì hữu ích cho database nhưng có thể khiến hàng A tiếp tục bị khóa.

### 3.1. Khóa hàng, khóa bảng và MVCC khác nhau

PostgreSQL có **MVCC (Multi-Version Concurrency Control)**. Một câu **SELECT thông thường** dưới các điều kiện phổ biến không cần lấy row lock như SELECT FOR UPDATE; đọc và ghi có thể cùng hoạt động nhờ các phiên bản hàng.

Tuy nhiên:

- **UPDATE/DELETE** trên cùng hàng có thể phải chờ row lock của transaction khác.
- **SELECT FOR UPDATE** chủ động giữ khóa hàng.
- Câu SQL còn có thể lấy **table-level locks** với các mode khác nhau; không phải mọi table lock đều chặn SELECT/INSERT.
- **Transaction chỉ đọc kéo dài** có thể giữ snapshot và cản việc dọn một số phiên bản cũ bằng VACUUM, ngay cả khi nó không khóa trực tiếp các hàng như UPDATE.
- Thao tác DDL như ALTER TABLE có thể cần khóa mạnh khác với row lock của DML.

Vì vậy **“PostgreSQL dùng MVCC nên transaction dài không làm ảnh hưởng ai”** là kết luận sai.

### 3.2. Một khóa nóng làm giới hạn thông lượng

Giả sử nhiều transaction đều cần cập nhật **cùng một hàng tồn kho**. Nếu mỗi transaction giữ khóa hàng đó trung bình **100 ms**, phần xử lý nối tiếp trên hàng nóng có trần xấp xỉ 10 transaction/giây trong mô hình đơn giản. Nếu code giữ khóa ấy **500 ms** vì xử lý thêm công việc không liên quan, trần xấp xỉ giảm xuống 2 transaction/giây.

Đây là **mô hình minh họa**, không phải dự báo hiệu năng chính xác: thời gian chờ, scheduler, lock acquisition, commit, khả năng xử lý song song ở phần không tranh chấp và hệ điều hành đều ảnh hưởng. Ý nghĩa quan trọng là **giảm thời gian giữ tài nguyên đang bị tranh chấp có thể quan trọng hơn tăng batch size**.

## 4. Thông lượng và độ trễ không đồng nghĩa

Cần nói rõ đang đo **đơn vị nào**.

- **TPS (transactions per second):** số transaction commit hoặc được xử lý mỗi giây theo cách đo được xác định.
- **Rows/s:** số hàng nhập/cập nhật thành công mỗi giây.
- **Requests/s:** số HTTP/API request hoàn tất mỗi giây.
- **Latency:** thời gian một transaction/request từ bắt đầu đến hoàn tất.
- **Lock wait:** thời gian request chờ khóa do giao dịch khác giữ.
- **Tail latency (p95/p99):** độ trễ của những request chậm nhất ở các phân vị tương ứng.

Nếu chuyển từ **1 hàng/transaction** sang **100 hàng/transaction**, TPS có thể **giảm** trong khi rows/s **tăng mạnh**. Không thể gọi tối ưu là thất bại chỉ vì TPS giảm, hoặc thành công chỉ vì rows/s tăng, nếu p99 API giao dịch đang xấu đi.

### 4.1. Định luật Little và số công việc đồng thời

Trong một hệ thống ổn định, định luật Little cho biết:

\[
L = \lambda W
\]

Trong đó \(L\) là số công việc trung bình có mặt trong hệ thống, \(\lambda\) là thông lượng hoàn tất trung bình và \(W\) là thời gian trung bình mỗi công việc ở trong hệ thống.

Giả sử 200 request/giây có thời gian xử lý phần database trung bình 0,05 giây, số request đồng thời trong chặng đó xấp xỉ **10**. Nếu thời gian tăng lên 0,5 giây mà hệ thống còn duy trì được 200 request/giây, nhu cầu đồng thời xấp xỉ **100**. Một pool có 16 Connection sẽ bắt đầu có áp lực chờ.

Ví dụ chỉ là trực giác trong **trạng thái ổn định**, không phải công thức đảm bảo kết quả khi hệ thống đã bão hòa, timeout hoặc bỏ request. Nó cho thấy **transaction dài có thể làm pool cạn trước cả khi database đạt mức CPU tối đa**.

## 5. Vì sao gom nhiều hàng vào một transaction có thể nhanh hơn?

Một transaction có chi phí cố định hoặc gần cố định, bên cạnh chi phí của từng hàng:

1. Bắt đầu và kết thúc đơn vị giao dịch.
2. Ghi nhận trạng thái commit, quản lý WAL và các thao tác flush phù hợp cấu hình.
3. Lượt trao đổi JDBC/DBMS để gửi SQL, commit và nhận phản hồi.
4. Xử lý transaction metadata, lock và tài nguyên.
5. Ứng dụng kiểm tra lỗi, tạo statement và quản lý kết nối.

Khi gom nhiều hàng vào một transaction, phần chi phí cố định được **phân bổ trên nhiều hàng**, đặc biệt với các workload import/backfill độc lập.

Một mô hình tư duy đơn giản:

\[
T(B) \approx C_{\text{commit}} + B \times C_{\text{row}} + C_{\text{contention}}(B)
\]

Với \(B\) là số hàng trong một transaction, \(C_{\text{commit}}\) là chi phí nền của mỗi commit, \(C_{\text{row}}\) là chi phí xử lý một hàng, và \(C_{\text{contention}}(B)\) là phần tăng do tranh chấp, khóa, cache và độ phức tạp khi batch lớn.

Mô hình này **không phải công thức chính xác của PostgreSQL**. WAL có thể được gom qua group commit; một lệnh SQL có thể cập nhật nhiều hàng; commit latency và chi phí row không tuyến tính. Nhưng nó cho thấy lý do tồn tại **điểm tối ưu ở giữa**, thay vì “batch càng lớn càng tốt”.

### 5.1. WAL, durability và group commit

Trong PostgreSQL, transaction ghi có thể cần flush WAL liên quan đến commit theo mức **synchronous_commit** đang dùng. Nhiều transaction có thể được hưởng cơ chế **group commit**, giúp gộp một số lượt ghi/flush, nên **không được giả định mỗi COMMIT luôn gây một lần fsync vật lý riêng biệt**.

Khi batch quá nhỏ:

- Có thể có nhiều lần round trip cho commit hơn.
- Có thêm overhead quản lý transaction.
- Số hàng xử lý mỗi lượt commit ít, nhất là trên đường truyền có độ trễ cao.

Nhưng batch quá lớn:

- Tạo nhiều WAL và dirty pages trước khi kết thúc.
- Giữ khóa lâu và tăng độ trễ của các transaction cạnh tranh.
- Làm tăng công việc cần rollback nếu lỗi.
- Có thể tạo áp lực WAL storage, replication lag và thời gian phục hồi trong một số tình huống.

**Đánh đổi cần đo thực tế** với storage, driver, DBMS version, replication và workload cụ thể.

## 6. Giao dịch quá lớn gây những vấn đề gì?

| Vấn đề | Cơ chế | Dấu hiệu |
|---|---|---|
| **Lock wait tăng** | Nhiều khóa được giữ lâu tới commit | Request cạnh tranh chờ, p95/p99 tăng |
| **Deadlock phức tạp hơn** | Transaction chạm nhiều hàng/bảng theo thứ tự khác nhau | SQLSTATE 40P01 tăng |
| **Pool cạn** | Connection bị mượn lâu | Active gần tối đa, pending tăng |
| **WAL/I/O cao** | Cập nhật lượng lớn dữ liệu và index | WAL tăng, disk busy, replica lag |
| **Rollback đắt hơn** | Nhiều thay đổi phải bị loại bỏ hoặc phục hồi trạng thái | Transaction thất bại mất nhiều thời gian/tài nguyên |
| **Snapshot cũ tồn tại lâu** | Transaction dài giữ snapshot MVCC | Dead tuples chưa thu dọn, bloat tăng trong điều kiện phù hợp |
| **Timeout/cancel khó dự đoán** | Truy vấn hoặc commit chạm nhiều tài nguyên | Statement/lock timeout, request deadline hết |
| **Khó checkpoint tiến độ job** | Một transaction duy nhất cho cả khối lượng lớn | Lỗi cuối job khiến phải làm lại nhiều việc |
| **Ảnh hưởng workload khác** | Một batch dùng nhiều I/O/khóa cùng lúc | API giao dịch chậm khi job nền chạy |

Không phải transaction lớn nào cũng tạo hết các hậu quả này. Ví dụ **INSERT độc lập vào các hàng khác nhau** có thể ít tranh chấp row lock hơn **UPDATE cùng một hàng nóng**. Cần nhìn khóa, kế hoạch truy vấn và mẫu truy cập.

### 6.1. Khi thời gian dài nguy hiểm hơn số hàng

~~~text
Transaction A:
    BEGIN
    UPDATE inventory SET quantity = quantity - 1 WHERE sku = 'SKU-1'
    gọi hệ thống giao hàng qua HTTP, chờ 8 giây
    COMMIT

Transaction B:
    BEGIN
    UPDATE inventory ... WHERE sku = 'SKU-1'
    -- Chờ khóa A
~~~

A chỉ cập nhật một hàng nhưng lại giữ khóa qua lời gọi HTTP chậm. B bị chặn dù bản thân B không làm truy vấn đắt. Thiết kế tốt hơn là **tách phần gọi mạng ra khỏi transaction** khi nghiệp vụ cho phép, hoặc dùng outbox/điều phối bất đồng bộ để tránh giữ row lock xuyên mạng.

## 7. Giao dịch quá nhỏ cũng có chi phí

Một vòng lặp xử lý 100.000 bản ghi mà **commit sau mỗi hàng** có thể tạo nhiều transaction, round trip và WAL commit record, trong khi mỗi hàng đều độc lập.

~~~text
100.000 bản ghi
    |
    +--> 100.000 transaction x 1 hàng
    |
    +--> 1.000 transaction x 100 hàng
    |
    +--> 100 transaction x 1.000 hàng
~~~

Chọn phương án nào phụ thuộc throughput, thời gian giữ khóa, tính nguyên tử và chi phí làm lại khi lỗi. **Không thể suy ra phương án 100 transaction là nhanh nhất** mà không benchmark.

Một vấn đề nghiêm trọng hơn hiệu năng: nếu một nghiệp vụ cập nhật **số dư tài khoản nguồn** ở transaction đầu rồi cập nhật **tài khoản đích** ở transaction sau, hệ thống có thể commit chỉ nửa nghiệp vụ. Bất biến tiền tệ phải ưu tiên hơn tối ưu số hàng/batch.

### 7.1. Chọn ranh giới theo bất biến nghiệp vụ

| Nghiệp vụ | Ranh giới transaction gợi ý | Lý do |
|---|---|---|
| Chuyển tiền giữa hai tài khoản cùng DB | Một transaction bao trọn debit và credit | Cần nguyên tử, không chấp nhận ghi nửa |
| Tạo đơn hàng và các dòng hàng | Một transaction nếu DB và invariant yêu cầu | Đơn không nên tồn tại thiếu thành phần bắt buộc |
| Ghi telemetry độc lập có event ID duy nhất | Có thể gom nhiều event theo lô | Mỗi sự kiện độc lập, có cơ chế chống trùng |
| Backfill cột trên hàng triệu bản ghi | Nhiều batch transaction có checkpoint | Giới hạn khóa/WAL và có khả năng tiếp tục |
| Tính báo cáo theo snapshot lớn | Ranh giới đọc phụ thuộc consistency | Tránh snapshot/Connection quá dài nếu không cần |
| Một UPDATE để thay đổi chính sách trên nhiều hàng | Có thể một transaction lớn nếu bất biến cần atomicity | Cần lên lịch, đo và đánh giá lock trước |

**Không chia transaction mà không có thiết kế thay thế nếu các bước thực sự phải nguyên tử.**

## 8. Thực hành SQL: hai transaction tranh chấp cùng một hàng

Tạo bảng trong **môi trường thử nghiệm**:

~~~sql
CREATE TABLE inventory (
    sku TEXT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory(sku, quantity)
VALUES ('SKU-1', 100);
~~~

Mở **hai session PostgreSQL** riêng biệt.

**Session A**:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-1' AND quantity > 0;

-- Chưa COMMIT; đừng thực hiện thử nghiệm này trên production.
-- Giữ transaction mở một lúc để quan sát session B.
~~~

**Session B**, chạy trong lúc A chưa commit:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'SKU-1' AND quantity > 0;

-- Câu UPDATE có thể phải chờ A nhả khóa hàng.
~~~

Khi A **COMMIT**, B có thể tiếp tục và đánh giá lại điều kiện cập nhật phù hợp quy tắc isolation của PostgreSQL, hoặc gặp một lỗi khác tùy cấu hình/isolation. Cuối cùng kết thúc cả hai transaction:

~~~sql
COMMIT;
~~~

**Cảnh báo:** ví dụ có khả năng tạo lock wait có chủ đích. Chỉ dùng test database không chứa dữ liệu thật; nếu quên kết thúc transaction, session B và các thao tác khác có thể bị giữ lại.

### 8.1. Giữ khóa không giống số lần chạy SQL

Câu UPDATE trong A có thể hoàn tất trong vài mili giây. Nhưng nếu A chờ người vận hành 30 giây mới COMMIT, row lock vẫn tồn tại trong thời gian đó. Đây là khác biệt giữa **statement execution time** và **transaction lifetime/lock hold time**.

## 9. Thực hành JDBC: nhập dữ liệu theo batch transaction

Giả sử nhận dữ liệu sự kiện độc lập từ một pipeline và lưu vào PostgreSQL. Mỗi sự kiện có **event_id** duy nhất để hỗ trợ gửi lại. Dữ liệu ví dụ:

~~~sql
CREATE TABLE telemetry_events (
    event_id VARCHAR(80) PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);
~~~

Ý tưởng: batch 10.000 sự kiện có thể được chia thành **100 transaction, mỗi transaction 100 sự kiện**, thay vì một transaction dài 10.000 sự kiện. Việc chia nhỏ **chỉ hợp lệ vì các sự kiện trong ví dụ là độc lập và mỗi sự kiện có danh tính ổn định**.

### 9.1. Code Java JDBC có giới hạn mỗi transaction

Đoạn dưới dùng Java 17 trở lên. Nó nhận một danh sách sự kiện, chia thành các lát cắt tối đa **batchSize** và commit từng lát cắt trên một Connection mới.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import javax.sql.DataSource;

public final class TelemetryBatchWriter {
    private final DataSource dataSource;

    public TelemetryBatchWriter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record Event(
            String eventId,
            long tenantId,
            String eventType,
            Instant createdAt,
            String jsonPayload) {}

    public void writeAll(List<Event> events, int batchSize)
            throws SQLException {
        if (events == null || batchSize < 1 || batchSize > 1000) {
            throw new IllegalArgumentException("Batch size không hợp lệ");
        }

        for (int start = 0; start < events.size(); start += batchSize) {
            int end = Math.min(start + batchSize, events.size());
            writeChunk(events.subList(start, end));
        }
    }

    private void writeChunk(List<Event> chunk) throws SQLException {
        String sql = """
                INSERT INTO telemetry_events
                    (event_id, tenant_id, event_type, created_at, payload)
                VALUES (?, ?, ?, ?, CAST(? AS jsonb))
                ON CONFLICT (event_id) DO NOTHING
                """;

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Ví dụ yêu cầu Connection tự sở hữu transaction");
            }
            connection.setAutoCommit(false);

            boolean commitAttempted = false;
            boolean transactionEnded = false;
            try {
                try (PreparedStatement insert =
                             connection.prepareStatement(sql)) {
                    for (Event event : chunk) {
                        insert.setString(1, event.eventId());
                        insert.setLong(2, event.tenantId());
                        insert.setString(3, event.eventType());
                        insert.setTimestamp(4,
                                Timestamp.from(event.createdAt()));
                        insert.setString(5, event.jsonPayload());
                        insert.addBatch();
                    }
                    insert.executeBatch();
                }

                commitAttempted = true;
                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                if (!commitAttempted) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            } finally {
                if (transactionEnded) {
                    connection.setAutoCommit(true);
                }
                // Nếu COMMIT không rõ kết quả, không tự bật
                // autoCommit: pool/driver phải loại hoặc dọn
                // connection theo hợp đồng an toàn.
            }
        }
    }
}
~~~

**Điều đoạn code minh họa:**

- Một **chunk = một transaction**, còn toàn bộ danh sách có thể được commit từng phần.
- Sử dụng **PreparedStatement.addBatch/executeBatch** để giảm overhead gọi JDBC.
- Đóng PreparedStatement/Connection bằng try-with-resources; không giữ Connection trong khi đợi giữa các chunk.
- **ON CONFLICT(event_id) DO NOTHING** giúp việc nhận lại cùng một event ID không tạo một hàng thứ hai trong PostgreSQL.
- Khi có SQLException **trước** lúc gọi commit, code cố gắng rollback chunk hiện tại.
- Nếu lỗi xảy ra **trong** commit, kết quả chunk có thể chưa rõ; không coi mọi lỗi commit là chắc chắn rollback.

**Các giới hạn quan trọng của ví dụ:**

1. **Không kiểm tra nội dung xung đột**: nếu cùng event_id nhưng payload khác, DO NOTHING có thể che giấu dữ liệu mâu thuẫn. Production phải xác minh dữ liệu của event_id đã tồn tại có cùng thuộc tính bất biến hoặc báo lỗi. Chống trùng phải gắn với **định danh và nội dung nghiệp vụ**.
2. **Không phải transaction cho toàn bộ writeAll**: nếu chunk 1 đã commit và chunk 2 thất bại, chunk 1 vẫn còn trong DB. Thiết kế chỉ phù hợp khi từng event/chunk có thể chấp nhận tiến độ từng phần.
3. **Retry quanh COMMIT cần đối soát**: việc gửi lại cùng event_id và UNIQUE có thể là một phần giao thức idempotent, nhưng phải biết nguồn dữ liệu có thẩm quyền, đặc biệt trong failover/replication async.
4. **setTimestamp và JSON** là ví dụ mapping cho PostgreSQL; timezone/Instant, JSON validity và driver cần được kiểm chứng. Thao tác kiểu này có thể đòi cấu hình khác theo DBMS.
5. **batchSize <= 1000** chỉ là giới hạn minh họa để chặn giá trị cực lớn, **không phải kích thước tối ưu** được khuyến nghị chung.
6. **Connection pool state** cần được reset hoặc loại an toàn theo hợp đồng triển khai; cách dọn connection gặp lỗi phải được kiểm thử riêng.
7. Đừng gọi side effect bên ngoài (email/HTTP) bên trong transaction như ví dụ để tránh nhân đôi khi retry.

### 9.2. Vì sao mỗi chunk là transaction riêng?

Với một import 10.000 hàng, nếu chunk 100 thì có thể đã commit được 3.500 hàng trước lúc job gặp lỗi. Khi chạy lại, ID ổn định và quy tắc idempotency cho phép tiếp tục mà không chèn trùng những hàng đã commit. Cách này giảm chi phí làm lại và thời gian giữ khóa trong một chunk.

Nhưng **không được dùng tiến độ từng phần nếu nghiệp vụ bắt buộc tất cả 10.000 hàng commit cùng nhau**. Khi đó cần thiết kế staging table, publish/activation flag hoặc transaction nguyên tử phù hợp thay vì âm thầm chia nhỏ.

## 10. Batch size tối ưu phải được đo, không suy từ con số cố định

Một lựa chọn có hệ thống là thử nhiều giá trị **batchSize** trong staging với dữ liệu và concurrency đại diện, giữ nguyên các yếu tố khác.

Bảng sau là **dữ liệu giả định để minh họa cách đọc kết quả**, hoàn toàn không phải benchmark của PostgreSQL:

| Hàng/transaction | Rows/s | Transaction p95 | Lock wait p95 của API khác | Nhận định |
|---:|---:|---:|---:|---|
| 1 | 3.000 | 6 ms | 3 ms | Nhiều lần commit |
| 50 | 16.000 | 38 ms | 6 ms | Tăng hiệu quả batch |
| 200 | 22.000 | 110 ms | 14 ms | Thông lượng cao, chờ khóa tăng |
| 1.000 | 24.000 | 640 ms | 130 ms | Rows/s chỉ tăng ít, API khác bị ảnh hưởng |
| 5.000 | 21.000 | 4.200 ms | 850 ms | Batch quá lớn cho workload minh họa |

Nếu mục tiêu là xử lý job nền nhanh **mà vẫn giữ API thanh toán có p95 lock wait dưới 20 ms**, giá trị 200 có thể là điểm bắt đầu kiểm thử tiếp theo. Nếu yêu cầu p95 dưới 10 ms, batch 50 có thể phù hợp hơn. **Đây chỉ là cách suy luận từ số đo giả định**, không phải kết luận rằng 50 hay 200 là giá trị mặc định tối ưu.

### 10.1. Những biến phải kiểm soát khi benchmark

- Số instance/worker đang chạy và số Connection khả dụng.
- Số dòng/độ lớn payload trung bình, phân bố khóa nóng và mức độ cập nhật index.
- Có transaction cạnh tranh trên cùng hàng/bảng không.
- Network latency tới database.
- PostgreSQL version, storage, WAL/synchronous_commit và replication mode.
- Cache warm/cold, autovacuum, checkpoint, nền đọc/ghi khác.
- BatchSize, số request in-flight và thời gian chờ giữa batch.

Chỉ đo rows/s của job trong môi trường không có traffic khác có thể bỏ qua rủi ro quan trọng nhất: **thời gian giữ khóa làm tăng độ trễ của request người dùng**.

## 11. Lập ngân sách thời gian và khóa cho mỗi transaction

Thay vì chỉ đặt giới hạn hàng, có thể có **nhiều điều kiện dừng** cho một chunk:

- **Tối đa N hàng**.
- **Tối đa X byte payload**.
- **Tối đa Y ms thời gian thực thi của transaction/chunk** ở mức mục tiêu.
- **Không vượt deadline của job hoặc request**.
- **Giới hạn số worker/Connection đồng thời**.

Ví dụ một backfill có thể chọn batch 200 hàng và đo p95 thời gian thực thi. Nếu batch bắt đầu chậm, hệ thống giảm batch/concurrency hoặc hoãn công việc. Tuy nhiên, **không thể bảo đảm chính xác transaction sẽ kết thúc sau Y ms chỉ bằng cách kiểm tra đồng hồ ở Java**: câu SQL có thể bị chặn ở DB hoặc COMMIT có thể mất thời gian. Cần kết hợp **statement_timeout, lock_timeout**, transaction deadline và monitoring theo DBMS.

### 11.1. Không ngủ giữa transaction

**Sai:**

~~~java
connection.setAutoCommit(false);
updateSomeRows(connection);
Thread.sleep(1000);    // Vẫn giữ transaction/khóa/Connection.
updateMoreRows(connection);
connection.commit();
~~~

**Tốt hơn khi hai nhóm công việc thực sự độc lập:**

~~~text
Transaction A: cập nhật batch A -> COMMIT -> đóng Connection
    |
    +--> backoff/throttle (không giữ transaction)
    |
Transaction B: cập nhật batch B -> COMMIT -> đóng Connection
~~~

Chú ý: không tách hai batch nếu invariant nghiệp vụ đòi cả hai phải nguyên tử.

## 12. Backfill trong nhiều transaction mà không đánh mất tiến độ

Với cập nhật dữ liệu cũ, cách tiếp cận thông dụng là **từng dải khóa chính** hoặc **từng nhóm hàng được chọn có kiểm soát**.

Giả sử cột mới được thêm cho khách hàng:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name TEXT;
~~~

Backfill theo dải ID:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE id >= ?
  AND id < ?
  AND display_name IS NULL;
~~~

Hai dấu **?** là placeholder của JDBC, không phải cú pháp chạy trực tiếp trong SQL console. Điều kiện **display_name IS NULL** giúp chạy lại không ghi đè những hàng đã có giá trị mới, với giả định đó là quy tắc đúng của dữ liệu.

### 12.1. Checkpoint không được đi trước COMMIT

Ví dụ một job lưu tiến độ “đã đến ID 20.000” rồi mới commit batch chứa ID 19.000–20.000. Nếu commit thất bại nhưng checkpoint đã được lưu, lần chạy lại có thể **bỏ sót các hàng chưa được cập nhật**.

Thiết kế tốt hơn:

1. Chọn một dải ID chưa xử lý.
2. Bắt đầu transaction.
3. UPDATE dải ID đó.
4. **Ghi checkpoint tiến độ trong cùng transaction**, nếu checkpoint và dữ liệu cùng DB/ràng buộc.
5. COMMIT.
6. Chỉ sau khi COMMIT được xác nhận mới phát tín hiệu tiến độ đã hoàn tất.

Nếu job và checkpoint nằm ở hai hệ khác nhau, tính nguyên tử không còn tự động được bảo đảm; cần quy trình idempotency hoặc điều phối thích hợp.

### 12.2. Ví dụ checkpoint cùng transaction

Giả sử có bảng:

~~~sql
CREATE TABLE backfill_progress (
    job_name TEXT PRIMARY KEY,
    last_completed_id BIGINT NOT NULL
);

INSERT INTO backfill_progress(job_name, last_completed_id)
VALUES ('customers-display-name', 0);
~~~

Trong một transaction (ký hiệu **:from_id**, **:to_id** là tham số logic do ứng dụng bind, không phải SQL chạy nguyên văn):

~~~sql
BEGIN;

UPDATE customers
SET display_name = full_name
WHERE id >= :from_id
  AND id < :to_id
  AND display_name IS NULL;

UPDATE backfill_progress
SET last_completed_id = :to_id - 1
WHERE job_name = 'customers-display-name';

COMMIT;
~~~

**Quan trọng:** cập nhật checkpoint cũng cần kiểm tra số hàng ảnh hưởng và, nếu có nhiều worker, cần khóa/điều phối tiến độ để không có worker chậm ghi lùi progress. Một checkpoint đơn nhất chỉ phù hợp với cách chia dải và worker protocol tương ứng. Lệnh minh họa dùng tham số có tên theo ký hiệu ứng dụng; với JDBC trực tiếp dùng **?** và bind vào PreparedStatement, hoặc thay giá trị khi chạy trong console.

### 12.3. SKIP LOCKED là một lựa chọn worker queue, không phải phép màu

Với một bảng job có trạng thái rõ ràng, PostgreSQL có **FOR UPDATE SKIP LOCKED** để nhiều worker tránh chờ những hàng đang bị worker khác khóa.

~~~sql
BEGIN;

WITH picked AS (
    SELECT id
    FROM work_items
    WHERE status = 'PENDING'
    ORDER BY id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE work_items AS w
SET status = 'CLAIMED'
FROM picked
WHERE w.id = picked.id
RETURNING w.id;

COMMIT;
~~~

Đây là ví dụ giả định bảng work_items(id, status) và giao thức worker được thiết kế. **SKIP LOCKED không bảo đảm thứ tự toàn cục hoặc fairness**, có thể bỏ qua một số hàng đang khóa. Nếu COMMIT rồi worker chết trước khi xử lý, những hàng **CLAIMED** có thể bị kẹt nếu không có lease/timeout/reclaim. Nếu muốn thực thi job và đánh dấu DONE nguyên tử, còn phải tính đến công việc có tác dụng ngoài database và thời lượng transaction. Không coi SKIP LOCKED là giải pháp chung để chia mọi transaction lớn.

## 13. Khóa nóng, thứ tự lấy khóa và giảm phạm vi tranh chấp

Một transaction có thể nhỏ nhưng vẫn làm nhiều request phải chờ nếu chúng cùng cập nhật một **hot row**. Ví dụ hàng tồn kho của một sản phẩm đang được đặt mua liên tục.

Cách dễ gây race condition:

~~~text
SELECT quantity FROM inventory WHERE sku = ?
Java: if quantity > 0
UPDATE inventory SET quantity = quantity - 1 WHERE sku = ?
~~~

Nếu không có khóa, isolation hoặc điều kiện ghi phù hợp, nhiều request có thể đọc cùng số lượng ban đầu và đưa ra quyết định sai.

Một lựa chọn trên PostgreSQL là **cập nhật có điều kiện trong một statement**:

~~~sql
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = ?
  AND quantity > 0
RETURNING sku, quantity;
~~~

Dấu **?** là placeholder JDBC. Nếu không có hàng được trả về, SKU có thể không tồn tại hoặc số lượng không còn dương; business logic cần phân biệt nếu hợp đồng yêu cầu. Điều kiện UPDATE và CHECK(quantity >= 0) giúp bảo vệ bất biến, nhưng những transaction cùng cập nhật một SKU vẫn phải phối hợp trên hàng đó. Không nên kỳ vọng tăng pool size sẽ biến một row lock nóng thành tài nguyên ghi song song vô hạn.

### 13.1. Quy tắc thứ tự khóa nhất quán

Hai giao dịch chuyển tiền có thể cập nhật tài khoản 101 và 102 theo thứ tự đối nghịch:

~~~text
Transaction A: lock 101 -> chờ 102
Transaction B: lock 102 -> chờ 101
                 |
               Deadlock
~~~

Chuẩn hóa **lấy khóa theo ID tăng dần**, dù chuyển tiền theo hướng nào, có thể giảm một loại deadlock. Biện pháp này không loại bỏ mọi deadlock trong hệ thống phức tạp. Cần giữ transaction ngắn và xử lý SQLSTATE **40P01** đúng cách.

### 13.2. Đặt việc không cần khóa ra ngoài transaction

Trước khi mở transaction, có thể xử lý việc parse JSON, kiểm tra cú pháp, tính toán không phụ thuộc dữ liệu đang đồng thời thay đổi hoặc chuẩn bị payload. Không gọi API giao hàng qua HTTP, upload file hay sleep trong khi đang giữ row lock nếu có cách thiết kế khác, chẳng hạn **transactional outbox**.

Ngược lại, **không đẩy bước kiểm tra số dư cần nhất quán ra ngoài transaction** chỉ để giảm độ dài transaction. Ranh giới hiệu năng vẫn phải giữ các bất biến nghiệp vụ.

## 14. Transaction chỉ đọc dài cũng có chi phí

PostgreSQL sử dụng **MVCC**, nên SELECT thông thường không lấy row lock như SELECT FOR UPDATE. Nhưng một transaction chỉ đọc với snapshot kéo dài vẫn có thể khiến VACUUM chưa thể dọn những phiên bản hàng cũ cần được snapshot ấy nhìn thấy.

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT COUNT(*) FROM orders;

-- Giữ transaction mở trong khi Java tạo báo cáo rất lâu.

COMMIT;
~~~

Điều này không có nghĩa mọi SELECT ngắn dưới READ COMMITTED đều gây bloat. Ảnh hưởng phụ thuộc mức isolation, snapshot, số bản ghi bị cập nhật/xóa đồng thời và cách ứng dụng giữ transaction.

Những hướng giảm áp lực:

- Đóng read transaction ngay khi không còn cần snapshot.
- Dùng phân trang và transaction ngắn **nếu hợp đồng cho phép mỗi trang nhìn thấy trạng thái dữ liệu khác nhau**.
- Với báo cáo phải thấy một snapshot nhất quán, cân nhắc replica/warehouse và chấp nhận chi phí có chủ đích.
- Tránh giữ transaction/Connection khi ghi file, nén báo cáo hoặc gửi email.
- Theo dõi **idle in transaction**, transaction age, dead tuples và autovacuum.

**Chia read-only transaction thành nhiều đoạn có thể thay đổi tính nhất quán của kết quả.** Đó cũng là trade-off, không phải tối ưu không có giá phải trả.

## 15. Lỗi, retry và kết quả COMMIT chưa rõ

Transaction càng lớn thì một lần phải retry thường tốn nhiều tài nguyên và làm lại nhiều việc hơn. Retry chỉ hợp lý với lỗi **được phân loại chính xác** và **đơn vị công việc có thể chạy lại an toàn**.

| SQLSTATE PostgreSQL | Ý nghĩa | Hành động |
|---|---|---|
| **40001** | Serialization failure | Retry **toàn bộ transaction** với giới hạn nếu nghiệp vụ cho phép |
| **40P01** | Deadlock detected | Có thể retry toàn transaction; sửa thứ tự khóa |
| **55P03** | Lock not available | Xem NOWAIT/lock_timeout, không retry ngay vô hạn |
| **57014** | Query canceled | Xác định nguyên nhân hủy và trạng thái công việc |
| **08xxx** | Lỗi connection | Bỏ Connection lỗi; phân biệt lỗi tại SQL hay COMMIT |
| **23505** | Unique violation | Thường là xung đột dữ liệu hoặc idempotency cần đối soát |

Quy tắc retry:

1. Có **allowlist** lỗi tạm thời và chính sách theo loại nghiệp vụ.
2. Mỗi attempt mới phải mở transaction mới, đọc và ra quyết định lại nếu cần.
3. Dọn transaction và trả Connection trước khi backoff có jitter.
4. Giới hạn số attempts và deadline; không retry khi DB đang bão hòa.
5. Ghi nhận số lần retry, rows đã commit, error rate và độ trễ tổng.

### 15.1. SQLException ở COMMIT không có nghĩa tất cả bản ghi chưa được lưu

~~~text
Java                          PostgreSQL
 |--- INSERT batch ----------->|
 |<-- executeBatch thành công -|
 |--- COMMIT ----------------->|
 |                       Có thể đã commit
 X mất đường mạng              |
 |<-- phản hồi không tới ------|
~~~

Một batch có thể **đã commit** dù Java nhận lỗi kết nối đúng lúc commit. Nếu chạy lại với event ID hoặc operation ID mới, dữ liệu có thể bị nhân đôi.

Cần **ID ổn định, ràng buộc UNIQUE, kiểm tra payload khi trùng và đối soát** trên nguồn có thẩm quyền. Nếu hệ thống dùng replication bất đồng bộ, một replica mới sau failover có thể chưa nhận đủ thay đổi; không coi SELECT thiếu bản ghi trên replica là bằng chứng tuyệt đối giao dịch trước chưa commit.

## 16. Quan sát transaction và khóa bằng PostgreSQL

### 16.1. Tìm transaction mở lâu

~~~sql
SELECT pid,
       application_name,
       state,
       now() - xact_start AS transaction_age,
       now() - query_start AS query_age,
       wait_event_type,
       wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

**transaction_age** là thời gian đã mở transaction, không phải thời gian chính xác nắm giữ một row lock cụ thể. **query_age** phải được diễn giải cùng **state**; session idle không có nghĩa câu SQL vẫn đang thực thi. Các trường **wait_event_type/wait_event** giúp phân biệt chờ lock, I/O và các loại chờ được quan sát.

### 16.2. Xem session nào đang chặn

~~~sql
SELECT pid AS blocked_pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock';
~~~

Kết quả là **ảnh chụp ở thời điểm truy vấn**, không phải toàn bộ lịch sử lock wait. Quyền xem session người khác có thể bị hạn chế; nên kết hợp log và monitoring.

### 16.3. Counter commit, rollback và hàng thay đổi

~~~sql
SELECT datname,
       xact_commit,
       xact_rollback,
       tup_inserted,
       tup_updated,
       tup_deleted,
       deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

Đây là **counter tích lũy**, không phải tốc độ rows/s hoặc TPS trực tiếp. Lấy chênh lệch ở hai thời điểm rồi chia cho thời gian đo để tính tốc độ. **xact_commit** là số giao dịch DBMS ghi nhận theo phạm vi thống kê, không phải số nghiệp vụ HTTP thành công.

### 16.4. WAL và replica lag

Ở các phiên bản PostgreSQL có **pg_stat_wal**:

~~~sql
SELECT wal_records, wal_fpi, wal_bytes
FROM pg_stat_wal;
~~~

Nếu có standby và quyền phù hợp, trên primary có thể quan sát:

~~~sql
SELECT application_name,
       state,
       sent_lsn,
       write_lsn,
       flush_lsn,
       replay_lsn,
       write_lag,
       flush_lag,
       replay_lag
FROM pg_stat_replication;
~~~

Các cột lag có thể NULL; cần diễn giải theo replication mode và tình trạng kết nối. Batch rất lớn có thể tạo đợt WAL và làm replica theo không kịp; nhưng WAL tăng **không tự chứng minh** có lock contention. Hãy đo chúng riêng.

### 16.5. Timeout cần đặt đúng mục đích

- **statement_timeout:** giới hạn thời gian của statement theo DBMS.
- **lock_timeout:** giới hạn chờ **để lấy khóa**, không giới hạn thời gian giữ khóa sau khi lấy được.
- **idle_in_transaction_session_timeout:** giảm nguy cơ session bỏ quên transaction mở.
- **transaction_timeout:** ở các phiên bản PostgreSQL hỗ trợ, giới hạn thời gian transaction theo cơ chế DBMS.

Không áp dụng các giá trị rất thấp vào production mà không test; timeout có thể hủy transaction hợp lệ và gây thêm retry/rollback.

## 17. Metric ở Java và connection pool

| Chỉ số cần có | Cách sử dụng |
|---|---|
| **rows_processed_per_second** | Thông lượng khối lượng lớn |
| **transaction_duration_p95/p99** | Theo dõi transaction dài |
| **query_duration_p95/p99** | Phân biệt chậm SQL với chờ pool |
| **connection_acquire_duration** | Mượn Connection từ pool có chậm không |
| **pool_active / idle / pending** | Pool có bị cạn do transaction giữ lâu không |
| **lock_wait_duration** | Ảnh hưởng của transaction lên request khác |
| **batch_rows_actual** | Mỗi chunk thực tế có bao nhiêu hàng |
| **commit_duration** | Bước kết thúc transaction có chậm không |
| **retry_count_by_sqlstate** | Chi phí do deadlock/serialization |
| **unknown_commit_outcome_count** | Những lượt ghi cần đối soát |
| **backfill_rows_remaining** | Tiến độ của job nền |
| **api_latency_p95/p99** | Người dùng có bị ảnh hưởng không |

Tên metric là ví dụ đặt tên, không phải mọi thư viện xuất ra cùng tên. Tránh đưa user ID, event ID hoặc dữ liệu cá nhân vào label gây cardinality cao và rò rỉ thông tin.

**Connection hold duration** khác **transaction duration**: ứng dụng có thể mượn Connection trước khi BEGIN hoặc tiếp tục giữ sau COMMIT. Cần đo cả hai để tìm vị trí lãng phí.

## 18. Quy trình chọn kích thước giao dịch trong thực tế

**Bước 1 — Xác định tính nguyên tử.** Liệt kê những hàng và thao tác bắt buộc phải commit cùng nhau. Với dữ liệu độc lập nhưng consumer không được thấy import dở, có thể dùng **staging table và activation flag** để nhập theo chunk rồi công bố một lần.

**Bước 2 — Lấy baseline.** Đo rows/s, TPS, duration p95/p99, lock wait, API p99, pool pending và WAL/replication lag.

**Bước 3 — Thử một biến mỗi lần.** Ví dụ batch size 10, 50, 200, 1.000 với dữ liệu đại diện, giữ nguyên số worker và tải nền.

**Bước 4 — Chạy workload cạnh tranh.** Đo cả API cập nhật tồn kho hoặc thanh toán trong lúc import; đừng chỉ đo throughput của job một mình.

**Bước 5 — Kiểm thử failure/restart.** Mô phỏng lỗi trước COMMIT, gần COMMIT, giữa các chunk; xác minh checkpoint và idempotency, không đánh dấu tiến độ khi dữ liệu chưa commit.

**Bước 6 — Đặt guardrails.** Giới hạn batch size, số worker đồng thời, byte mỗi batch, timeout, điều kiện dừng job khi API p99 hoặc replica lag vượt ngưỡng.

Một batch size được chọn bằng benchmark **chỉ có hiệu lực trong phạm vi workload và điều kiện đo**. Khi dữ liệu, index, số instance hoặc storage đổi, cần đo lại.

## 19. Các sai lầm thường gặp

| Sai lầm | Vì sao gây hại | Cách cải thiện |
|---|---|---|
| “Batch càng lớn càng tốt.” | Giữ khóa, tăng WAL và rollback cost | Đo p99/lock wait cùng rows/s |
| “Ít hàng là transaction ngắn.” | Có thể chờ mạng khi đã lấy khóa | Đo duration và bỏ công việc ngoài DB |
| “Mỗi hàng commit riêng luôn an toàn.” | Có thể phá nghiệp vụ nguyên tử | Xác định invariant trước |
| “executeBatch tự commit cả nhóm nguyên tử.” | Phụ thuộc Connection/auto-commit | Kiểm soát transaction rõ ràng |
| “MVCC loại bỏ mọi row lock.” | UPDATE cùng hàng vẫn tranh chấp | Đo khóa nóng và rút ngắn critical section |
| “Tăng pool là chữa được lock wait.” | Thêm transaction chờ cùng một hàng | Giảm contention và concurrency |
| “Checkpoint ngoài DB có thể ghi trước.” | Có thể bỏ sót hàng chưa commit | Checkpoint cùng transaction hoặc đối soát |
| “SKIP LOCKED bảo đảm đúng một lần.” | Worker chết sau claim, có thể xử lý lặp | Lease/reclaim/idempotency |
| “Read transaction dài không tốn tài nguyên.” | Snapshot có thể cản VACUUM | Giới hạn vòng đời snapshot |
| “Deadlock chỉ retry câu UPDATE cuối.” | Transaction đã bị hủy, dữ liệu cần đọc lại | Retry toàn transaction |
| “COMMIT timeout chứng minh chưa ghi.” | Server có thể đã commit | Operation ID và đối soát |
| “Rows/s tăng nghĩa là toàn hệ thống nhanh hơn.” | p99 API có thể tăng mạnh | Đo user latency và throughput cùng lúc |
| “Rollback transaction lớn hoàn toàn miễn phí.” | Công việc đã thực hiện cần loại bỏ/làm lại | Chọn chunk hợp lệ với nghiệp vụ |

## 20. Bài tập tự kiểm tra

**Bài 1 — Thời gian giữ khóa.** Một UPDATE hoàn tất sau 10 ms, nhưng Java giữ transaction mở thêm 5 giây khi gọi HTTP. Transaction khác cập nhật cùng hàng có thể bị ảnh hưởng như thế nào?

*Gợi ý:* row lock thường được giữ tới COMMIT/ROLLBACK, không chỉ trong thời gian câu UPDATE chạy.

**Bài 2 — TPS và rows/s.** Job xử lý 500 transaction/giây × 1 hàng, sau đó chuyển sang 100 transaction/giây × 30 hàng. Chỉ số nào tăng và giảm?

*Gợi ý:* TPS giảm 500 xuống 100, nhưng rows/s tăng 500 lên 3.000. Cần xem latency của request khác.

**Bài 3 — Tính nguyên tử.** Có nên chia debit và credit trong một chuyển tiền cùng DB thành hai transaction để giảm thời gian giữ khóa?

*Gợi ý:* không nếu nghiệp vụ phải nguyên tử. Cần tối ưu nội dung của một transaction thay vì phá ranh giới.

**Bài 4 — Backfill.** Job xử lý 1 triệu hàng theo chunk 200. Chunk thứ 2.001 lỗi. Các chunk đã commit có bị rollback không?

*Gợi ý:* không, nếu mỗi chunk là transaction riêng. Thiết kế phải cho phép tiến độ từng phần và resume.

**Bài 5 — Checkpoint.** Job ghi checkpoint “xong ID 50.000”, sau đó COMMIT batch tương ứng thất bại. Điều gì có thể xảy ra khi chạy lại?

*Gợi ý:* bỏ sót các hàng chưa thực sự commit. Cần đồng bộ tiến độ với transaction.

**Bài 6 — SKIP LOCKED.** Worker claim 100 job và commit trạng thái CLAIMED, sau đó chết. Có thể bảo đảm job đã hoàn tất không?

*Gợi ý:* không; cần lease, reclaim, retry và xử lý trùng.

**Bài 7 — Read snapshot.** Một transaction REPEATABLE READ chỉ đọc giữ snapshot 45 phút. Nó có thể ảnh hưởng VACUUM không?

*Gợi ý:* có thể giữ các phiên bản hàng cũ còn cần cho snapshot.

**Bài 8 — Chọn batch size.** Trong số đo giả định, batch 200 cho 22.000 rows/s, lock wait p95 14 ms; batch 1.000 cho 24.000 rows/s, lock wait p95 130 ms. API cần lock wait p95 dưới 20 ms. Nên làm gì?

*Gợi ý:* ưu tiên batch 200 hoặc benchmark quanh mức này; không đánh đổi SLO lấy ít rows/s tăng thêm.

**Bài 9 — Deadlock.** Transaction A khóa tài khoản 101 rồi 102, B khóa 102 rồi 101. Biện pháp giảm rủi ro?

*Gợi ý:* chuẩn hóa thứ tự khóa, giảm transaction duration và xử lý deadlock bằng retry toàn transaction.

**Bài 10 — COMMIT mất phản hồi.** Java gửi COMMIT batch 100 event rồi mất kết nối. Có được tạo event ID mới và gửi lại tất cả không?

*Gợi ý:* không; commit cũ có thể đã thành công. Cần ID ổn định và đối soát.

## 21. Ghi nhớ và áp dụng

**Kích thước giao dịch** không chỉ là số dòng, mà còn là lượng dữ liệu thay đổi, số SQL, thời lượng transaction và mức tranh chấp. Batch nhiều hàng có thể tăng throughput nhờ giảm round trip/commit overhead, nhưng **khóa được giữ lâu hơn có thể khiến API khác chờ và làm tăng p95/p99**.

**Tính nguyên tử của nghiệp vụ là giới hạn ưu tiên.** Không chia chuyển tiền thành hai transaction chỉ vì muốn nhanh hơn. Với dữ liệu import/backfill độc lập, chia chunk vừa phải, lưu checkpoint phù hợp, hỗ trợ resume/idempotency và throttle ngoài transaction. Không giữ lock trong lúc gọi HTTP hoặc sleep nếu có phương án thiết kế an toàn.

**Tối ưu thực sự** là đạt rows/s đủ cao **đồng thời** duy trì latency, tính đúng, durability và khả năng phục hồi. Hãy đo lock wait, transaction age, WAL, replication lag và pool metrics dưới tải đại diện, rồi điều chỉnh batch size/concurrency từ dữ liệu đo chứ không dựa vào một con số mặc định cho mọi hệ thống.
