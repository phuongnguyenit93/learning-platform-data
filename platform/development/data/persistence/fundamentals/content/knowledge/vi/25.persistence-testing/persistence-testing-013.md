# Kiểm thử phục hồi và đối soát sau sự cố

Trong một hệ thống Java dùng cơ sở dữ liệu quan hệ, lỗi không chỉ xuất hiện khi câu SQL chạy. Máy chủ có thể khởi động lại ngay lúc `COMMIT`, đường truyền đứt sau khi database đã lưu transaction nhưng trước khi ứng dụng nhận phản hồi, hoặc worker gửi sự kiện tới broker rồi chết trước khi đánh dấu đã gửi. Nếu ứng dụng chỉ thử “kết nối lại được” thì chưa chứng minh **dữ liệu không mất, tác động nghiệp vụ không bị lặp, và các hệ thống đã trở về trạng thái có thể tin cậy**.

**Kiểm thử phục hồi** (*recovery testing*) cố ý gây ra những lỗi có kiểm soát, rồi xác minh hệ thống khởi động, khôi phục và xử lý công việc còn dang dở. **Đối soát** (*reconciliation*) so sánh các bằng chứng bền vững như bản ghi nghiệp vụ, mã yêu cầu, sổ cái, outbox, inbox và trạng thái dịch vụ bên ngoài để phát hiện thiếu, trùng hoặc sai lệch; sau đó sửa theo quy tắc nghiệp vụ.

Trong chương **Kiểm thử lưu trữ** của **DATA_PERSISTENCE_FUNDAMENTALS**, nội dung này kết nối transaction, WAL/durability, replication, backup/PITR, ranh giới persistence Java, idempotency, retry và giám sát vận hành. Bài học hướng dẫn cách thiết kế *failure matrix*, xây ví dụ JUnit 5 + JDBC có thể kiểm chứng, lập kế hoạch fault injection và viết runbook đối soát sau sự cố.

**Nguyên tắc xuyên suốt:** “Không thấy lỗi khi chạy lại” không đủ. Phải kiểm tra **những gì đã commit, những gì chưa được xác nhận, những gì có thể phát lại và những bất biến nào vẫn đúng**.

## 1. Phân biệt phục hồi kỹ thuật và phục hồi nghiệp vụ

Một lần khôi phục thành công có nhiều tầng:

| Tầng | Câu hỏi kiểm chứng | Ví dụ kiểm thử |
| --- | --- | --- |
| **Process/availability** | JVM, pool và database có khởi động lại, phục vụ trong thời gian mục tiêu không? | Kill tiến trình test, restart rồi thử health/query |
| **Storage/crash recovery** | Các transaction đã commit có còn; transaction chưa commit có bị rollback không? | Dừng phiên đang ghi, so trạng thái sau mở lại |
| **Durability/RPO** | Mất bao nhiêu giao dịch đã được xác nhận so với mục tiêu? | So commit markers/ID với mốc phục hồi |
| **Transaction/invariants** | Số dư, tồn kho, khóa duy nhất, trạng thái và dữ liệu nhiều bảng còn đúng không? | Kiểm tra bằng SQL sau khi mọi recovery worker kết thúc |
| **Message integration** | Sự kiện đã commit có được phát; gửi lại có gây tác động trùng không? | Cắt kết nối sau publish, cho worker/consumer chạy lại |
| **Cross-service reconciliation** | Dịch vụ thanh toán, đơn hàng và broker có cùng cách hiểu một nghiệp vụ không? | Đối chiếu operation ID, outbox ID và ledger |
| **Operational recovery** | RTO, alert, runbook, quyền restore và khả năng khởi động ứng dụng đã được chứng minh chưa? | Diễn tập restore/PITR trên hạ tầng cách ly |

**Crash recovery** khác **backup restore**. Crash recovery thường dùng tệp dữ liệu và log hiện có của database để phục hồi sau khi process/máy dừng bất ngờ. Backup restore xây lại một hệ thống từ bản sao đã lưu; nếu dùng PITR thì còn replay log tới mốc được chọn. Một bản backup không có ranh giới nhất quán hoặc thiếu WAL có thể không dùng để phục hồi dù file copy có vẻ đầy đủ.

**Recovery thành công không đồng nghĩa mọi thao tác của thế giới bên ngoài được hoàn tác.** Email đã gửi, tiền đã thu hoặc message đã được xử lý không tự quay ngược khi restore PostgreSQL về mốc trước đó.

## 2. Những bảo đảm cần viết thành bất biến

Không thể kiểm thử câu chung chung “phục hồi đúng”. Hãy định nghĩa kết quả có thể đo:

1. **Atomicity:** thay đổi trong một transaction phải cùng commit hoặc cùng rollback, ví dụ ghi `orders.status='PAID'` và insert outbox.
2. **Durability theo cấu hình:** transaction mà DB đã xác nhận commit bền vững phải tồn tại sau sự cố thuộc phạm vi DB cam kết; với replica bất đồng bộ/failover, cần xác định RPO thực tế.
3. **At-most-once business effect:** cùng một `request_id` thanh toán không được thu tiền hoặc ghi sổ cái lần hai dù client retry.
4. **At-least-once integration intent:** mỗi outbox event đã commit còn ở trạng thái cho phép publisher gửi/retry, trừ khi đã có bằng chứng xử lý phù hợp.
5. **Referential/business invariants:** không có bản ghi mồ côi, không có tồn kho âm nếu chính sách cấm, không có hai booking dùng cùng ghế, không có ledger entry trùng khóa nghiệp vụ.
6. **Recoverability:** ứng dụng có thể kết nối DB vừa khôi phục bằng đúng role/schema/version và không tự động gây side effect tới production.

Ví dụ đặt đơn hàng gồm ba bảng:

```text
order_id=42, status=PENDING
       |
       v
Command PAY_ORDER, request_id=R
       |
       +-- TX: UPDATE orders.status='PAID'
       |       INSERT command_receipt(R)
       |       INSERT outbox_event(event_id=R)
       |       COMMIT
       |
       +-- Publisher gửi event R -> broker
       |
       +-- Consumer cập nhật ledger/projection và marker xử lý R
```

Những bằng chứng quan trọng là **ID ổn định qua retry**, bản ghi receipt, event ID, trạng thái đơn, kết quả commit và trạng thái consumer. Một API trả `200 OK` không đủ nếu record thực tế thiếu; ngược lại timeout HTTP không chứng minh DB đã rollback.

### Bộ test phải phân biệt kết quả hợp lệ

| Kết quả quan sát | Có thể có ý nghĩa gì? | Phản ứng phù hợp |
| --- | --- | --- |
| SQL lỗi trước commit, rollback xác nhận được | Thay đổi chưa được commit | Có thể retry **toàn transaction** nếu an toàn và lỗi có tính tạm thời |
| Commit thành công, response trả về đầy đủ | Thay đổi đã commit theo chính sách durability | Kiểm tra state/outbox và không phát lại command với ID mới |
| Mất connection trong lúc commit/ACK | **Kết quả chưa rõ**: có thể commit hoặc chưa | Đối soát bằng request ID từ nguồn đủ nhất quán trước khi quyết định |
| DB restart, transaction dở dang biến mất | Crash recovery đã rollback phần chưa commit | Đọc lại từ DB, xác minh invariant, retry nếu nghiệp vụ cho phép |
| Broker nhận message, publisher mất ACK | Có thể đã giao nhưng chưa đánh dấu SENT | Publish lại cùng event ID; consumer phải idempotent |
| Consumer commit rồi mất ACK broker | Message có thể được giao lại | Marker chống trùng và hiệu ứng local cùng transaction |
| Restore về mốc cũ | Một số commit sau target bị mất chủ ý theo RPO | Đối soát log/operation ID với các hệ thống ngoài, không giả định mọi thứ tự khôi phục |

## 3. Xây failure matrix: gây lỗi ở đâu, mong đợi điều gì?

Một *failure matrix* nên được viết **trước** khi đưa fault injection vào CI hoặc diễn tập. Ví dụ:

| Mốc lỗi | Cách mô phỏng trong môi trường test | Điều cần kiểm tra sau recovery |
| --- | --- | --- |
| **F1: trước câu SQL ghi** | Ném lỗi có chủ đích trong service | Không có thay đổi, không có outbox |
| **F2: sau UPDATE nhưng trước COMMIT** | Đóng/terminate session DB khi transaction còn mở | Toàn bộ transaction bị rollback; không có trạng thái nửa vời |
| **F3: ngay tại COMMIT/đường trả ACK** | Proxy mạng/fault injector làm rớt kết nối ở cửa sổ được kiểm soát | Xem DB thực tế đã commit chưa, retry cùng idempotency key, không tạo tác động kép |
| **F4: sau commit nhưng trước HTTP response** | Tiêm exception ở tầng transport sau khi service trả thành công | Client retry cùng ID nhận kết quả đã thực thi; version/outbox không tăng lần hai |
| **F5: publisher đã gửi, chưa đánh dấu SENT** | Ngắt worker sau broker ACK và trước update outbox | Có thể publish lại; consumer không làm hiệu ứng lần hai |
| **F6: consumer đã commit, chưa ACK broker** | Ngắt consumer sau DB commit | Redelivery không nhân đôi ledger/projection |
| **F7: DB primary failover** | Dừng primary trong cụm test có election/fencing | Kết nối cũ lỗi phù hợp, leader duy nhất, RPO/read freshness đo được |
| **F8: mất data volume hoặc thao tác ghi nhầm** | Restore từ backup/PITR trên hệ thống tách biệt | Schema, WAL, quyền, dữ liệu và mốc phục hồi được kiểm chứng |
| **F9: phụ thuộc chậm/không khả dụng** | Tăng delay/timeout tới DB, broker hoặc object store | Backoff, queue bounded, circuit breaker, không giữ connection vô ích |
| **F10: event trùng/đến sai thứ tự** | Phát lại cùng ID, hoán đổi thứ tự version | Dedupe, version guard hoặc logic xử lý gap đúng hợp đồng |

**Không thử các cách phá hủy này trên production hoặc môi trường có dữ liệu thật.** Dùng PostgreSQL/container, database test có thể reset, broker giả lập hoặc sandbox riêng, đảm bảo traffic và secret không hướng sang dịch vụ thật. Diễn tập production failover có quyền phê duyệt và runbook riêng, không phải bước mặc định của unit test.

## 4. Ví dụ schema PostgreSQL có bằng chứng phục hồi

Một thiết kế đơn giản dùng `request_receipts` và `outbox_events` để làm điểm đối soát. Ví dụ giả định **một request thành công tạo một event duy nhất**, và `event_id = request_id`:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
           CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE request_receipts (
    request_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    operation VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    request_id UUID NOT NULL UNIQUE
               REFERENCES request_receipts(request_id),
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    event_type VARCHAR(60) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Bảng local phía consumer khi xử lý event (ở DB consumer).
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);
```

Trong source transaction phải có thứ tự:

1. Insert receipt với khóa duy nhất `request_id` và kiểm tra xem cùng ID có từng dùng với input khác không.
2. Nếu chưa xử lý, cập nhật `orders` theo điều kiện nghiệp vụ; nếu không hợp lệ thì rollback.
3. Insert `outbox_events` với ID đã quy định.
4. Commit **toàn bộ** trên một connection/transaction.

Nếu có lỗi trước commit, không được để receipt tồn tại mà trạng thái đơn/outbox lại thiếu. Nếu lỗi xảy ra tại commit, receipt là điểm để đối soát **sau khi kết nối tới nguồn dữ liệu đáng tin cậy được phục hồi**. Không dùng một replica bất đồng bộ đang trễ để kết luận receipt chưa tồn tại.

**Lưu ý:** Một receipt chỉ nói command đã được ghi nhận theo cách triển khai. Nếu command có kết quả thất bại hoặc cần lưu response tương ứng cho idempotency, schema nên lưu thêm `request_hash`, loại kết quả, phiên bản hoặc response token và thời hạn giữ; ví dụ dưới đây chỉ lưu receipt của command **thực sự thành công**.

## 5. Ví dụ Java/JDBC: xác nhận lại một yêu cầu khi mất phản hồi

Giả sử client gọi `PAY_ORDER(orderId=42, requestId=R)`. Server đã commit nhưng rớt kết nối HTTP trước khi trả response. Client không biết thành công hay chưa nên gửi lại **cùng request ID**.

Ví dụ JUnit 5 + Testcontainers + PostgreSQL JDBC sau chứng minh rằng **mất phản hồi sau commit** không tạo một transaction nghiệp vụ thứ hai. Nó **không giả lập việc mất ACK của chính câu `COMMIT` tại tầng TCP**; bài test mạng đó được thiết kế riêng ở phần sau.

### 5.1. Fixture và command service tối giản

Code dùng Java 17+, PostgreSQL test container và các dependency test JUnit Jupiter, Testcontainers PostgreSQL/JUnit Jupiter, PostgreSQL JDBC driver. Mỗi lần gọi service dùng một connection mới qua `DriverManager`; production nên dùng `DataSource`/pool được cấu hình đúng ranh giới transaction.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.io.IOException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class RecoveryAndReconciliationIT {
    @Container
    static final PostgreSQLContainer<?> DB =
            new PostgreSQLContainer<>("postgres:16-alpine");

    enum CommandResult { APPLIED, ALREADY_APPLIED }

    private Connection open() throws SQLException {
        return DriverManager.getConnection(
                DB.getJdbcUrl(), DB.getUsername(), DB.getPassword());
    }

    @BeforeEach
    void resetFixture() throws SQLException {
        try (Connection c = open(); Statement s = c.createStatement()) {
            s.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id BIGINT PRIMARY KEY,
                    status VARCHAR(20) NOT NULL,
                    version BIGINT NOT NULL DEFAULT 0)
                """);
            s.execute("""
                CREATE TABLE IF NOT EXISTS request_receipts (
                    request_id UUID PRIMARY KEY,
                    order_id BIGINT NOT NULL REFERENCES orders(order_id),
                    operation VARCHAR(40) NOT NULL)
                """);
            s.execute("""
                CREATE TABLE IF NOT EXISTS outbox_events (
                    event_id UUID PRIMARY KEY,
                    request_id UUID UNIQUE NOT NULL
                        REFERENCES request_receipts(request_id),
                    order_id BIGINT NOT NULL REFERENCES orders(order_id),
                    event_type VARCHAR(60) NOT NULL)
                """);
            s.execute(
                    "TRUNCATE outbox_events, request_receipts, orders");
            s.execute("""
                INSERT INTO orders(order_id, status, version)
                VALUES (42, 'PENDING', 0)
                """);
        }
    }

    private CommandResult pay(long orderId, UUID requestId)
            throws SQLException {
        if (requestId == null) {
            throw new IllegalArgumentException("Thiếu requestId");
        }
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                int inserted;
                try (PreparedStatement ps = c.prepareStatement("""
                    INSERT INTO request_receipts(
                        request_id, order_id, operation)
                    VALUES (?, ?, 'PAY_ORDER')
                    ON CONFLICT (request_id) DO NOTHING
                    """)) {
                    ps.setObject(1, requestId);
                    ps.setLong(2, orderId);
                    inserted = ps.executeUpdate();
                }

                if (inserted == 0) {
                    // Đã xử lý requestId: không thực thi nghiệp vụ lần nữa.
                    verifyExistingReceipt(c, orderId, requestId);
                    c.rollback();
                    return CommandResult.ALREADY_APPLIED;
                }

                int changed;
                try (PreparedStatement ps = c.prepareStatement("""
                    UPDATE orders
                    SET status='PAID', version=version+1
                    WHERE order_id=? AND status='PENDING'
                    """)) {
                    ps.setLong(1, orderId);
                    changed = ps.executeUpdate();
                }
                if (changed != 1) {
                    throw new IllegalStateException(
                            "Không thể thanh toán đơn không PENDING");
                }

                try (PreparedStatement ps = c.prepareStatement("""
                    INSERT INTO outbox_events(
                        event_id, request_id, order_id, event_type)
                    VALUES (?, ?, ?, 'ORDER_PAID')
                    """)) {
                    ps.setObject(1, requestId);  // một event/command
                    ps.setObject(2, requestId);
                    ps.setLong(3, orderId);
                    ps.executeUpdate();
                }
                c.commit();
                return CommandResult.APPLIED;
            } catch (SQLException | RuntimeException failure) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }

    private void verifyExistingReceipt(
            Connection c, long orderId, UUID requestId)
            throws SQLException {
        try (PreparedStatement ps = c.prepareStatement("""
                SELECT order_id, operation
                FROM request_receipts WHERE request_id=?
                """)) {
            ps.setObject(1, requestId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next() || rs.getLong("order_id") != orderId
                        || !"PAY_ORDER".equals(rs.getString("operation"))) {
                    throw new IllegalArgumentException(
                            "requestId đã dùng với tham số khác");
                }
            }
        }
    }

    private long scalarLong(String query) throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(query)) {
            assertTrue(rs.next());
            return rs.getLong(1);
        }
    }

    @Test
    void lostResponseAfterCommitDoesNotDuplicateWrite()
            throws Exception {
        UUID requestId = UUID.randomUUID();
        assertEquals(CommandResult.APPLIED, pay(42, requestId));

        // Mô phỏng tầng HTTP không trả được response SAU DB commit.
        IOException responseLost = assertThrows(IOException.class,
                () -> simulateLostHttpResponse());
        assertEquals("response lost", responseLost.getMessage());

        // Client retry đúng requestId, không tạo UUID mới.
        assertEquals(CommandResult.ALREADY_APPLIED,
                pay(42, requestId));

        assertEquals(1, scalarLong(
                "SELECT version FROM orders WHERE order_id=42"));
        assertEquals(1, scalarLong(
                "SELECT COUNT(*) FROM request_receipts"));
        assertEquals(1, scalarLong(
                "SELECT COUNT(*) FROM outbox_events"));
    }

    private void simulateLostHttpResponse() throws IOException {
        throw new IOException("response lost");
    }

    @Test
    void sameIdWithDifferentOrderIsRejected() throws Exception {
        UUID requestId = UUID.randomUUID();
        assertEquals(CommandResult.APPLIED, pay(42, requestId));
        assertThrows(IllegalArgumentException.class,
                () -> pay(99, requestId));
        assertEquals(1, scalarLong(
                "SELECT COUNT(*) FROM outbox_events"));
    }
}
```

**Điểm cần đọc đúng từ kết quả:** lần đầu cập nhật trạng thái và outbox trong **một transaction**; lần gọi lại có cùng ID thấy receipt đã commit và không phát sinh UPDATE/event mới. Kiểm tra cùng ID nhưng input khác bị từ chối, thay vì vô tình hợp thức hóa một request khác.

Test dùng bảng chung và `TRUNCATE` trong `@BeforeEach`; **không chạy những test này song song trên cùng database/fixture**. Khi mở rộng suite, tách schema/database cho từng test hoặc tắt JUnit parallel execution đối với fixture dùng chung. Các ví dụ không chạy thử ngay trong bài học; khi tích hợp thật cần cấu hình phụ thuộc, version và CI.

### 5.2. Cửa sổ COMMIT chưa rõ không được mô phỏng sai

Trong test trên, ta **biết chắc** `c.commit()` đã trả về bình thường rồi mới ném lỗi HTTP. Đây là lỗi **mất phản hồi sau commit**, dùng để kiểm tra hành vi client retry; nó không chứng minh cách ứng dụng xử lý khi `commit()` tự ném `SQLException` vì socket bị ngắt.

Để thử **commit-result-unknown**, cần fault injection ở ranh giới mạng thực:

```text
Java/JDBC -> proxy có thể inject fault -> PostgreSQL test

Case A: ngắt trước khi COMMIT được gửi
    => kỳ vọng transaction không commit (xác minh DB)

Case B: gửi COMMIT tới DB, chặn/mất ACK trên chiều về
    => Java có thể nhận lỗi; DB có thể đã commit
    => chỉ đối soát request ID mới phân biệt kết quả

Case C: ngắt kết nối sau khi commit trả ACK
    => dùng làm đối chứng với lỗi sau commit chắc chắn
```

Chọn proxy/fault injector có thể cắt hoặc làm trễ **đúng kết nối được thử**; phải lưu bằng chứng vị trí fault vì việc cắt theo thời gian ngẫu nhiên không bảo đảm trúng cửa sổ ACK. Không viết test chỉ `throw new SQLException()` ngay trước `commit()` rồi gọi đó là “unknown commit”: như vậy chưa có khả năng commit. Kết quả kiểm thử cần dựa trên **trạng thái đã commit đọc lại từ DB**, không đoán từ loại exception.

Trong thực tế có thể có đồng thời **lỗi JDBC và trạng thái DB hợp lệ**. Với kết quả chưa rõ, API không được tự chạy lại lệnh có side effect bằng một request ID mới. Ưu tiên reconnect, tra cứu receipt theo khóa ổn định ở primary/nguồn đọc đủ nhất quán, rồi quyết định báo thành công cũ hay thực thi lại một cách an toàn.

## 6. Kiểm thử rollback transaction đang dở dang

Một fault dễ kiểm soát hơn lỗi ACK là kết thúc session **trước commit** để kiểm tra atomicity. Trên PostgreSQL test, tạo một connection độc lập, mở transaction và ghi cả hai bảng, nhưng chưa commit:

```sql
-- Session T1 trên DB TEST; chưa commit.
BEGIN;
UPDATE orders SET status='PAID', version=version+1
WHERE order_id=42;
INSERT INTO request_receipts(request_id, order_id, operation)
VALUES ('00000000-0000-4000-8000-000000000042',
        42, 'PAY_ORDER');
SELECT pg_backend_pid(); -- ghi PID riêng của session test này

-- Session T2 của bộ test:
-- Chỉ khi biết chắc PID thuộc session test vừa tạo:
SELECT pg_terminate_backend(<pid_cua_T1>);

-- Session T3 mới: kiểm tra không có nửa transaction commit.
SELECT status, version FROM orders WHERE order_id=42;
SELECT COUNT(*) FROM request_receipts
WHERE request_id='00000000-0000-4000-8000-000000000042';
```

Trong PostgreSQL thực tế, lời gọi `pg_terminate_backend` cần quyền phù hợp và tham số PID phải thay bằng integer lấy từ **chính session của bài test**. Không gửi nguyên văn ký hiệu `<pid_cua_T1>` vào SQL. Không chạy thao tác terminate trên production hoặc session của người khác.

**Kết quả kỳ vọng:** transaction chưa commit bị rollback, `orders` vẫn là `PENDING`/version cũ và receipt không có. Nếu thao tác ghi bị đưa ra **hai connection auto-commit riêng** thay vì một transaction, bài test có thể lộ trạng thái nửa vời; đó là bug cần sửa tại ranh giới persistence.

**Giới hạn:** terminate một backend là kiểm thử mất **session/transaction**, chưa chứng minh recovery sau khi toàn bộ process PostgreSQL hoặc máy chủ mất điện. Muốn kiểm tra crash recovery/WAL, phải có test riêng cố ý dừng DB test bằng sự cố không graceful, giữ data volume hợp lệ, restart và xác minh những transaction đã commit/chưa commit.

## 7. Kiểm thử crash recovery, restart và failover

### 7.1. Crash recovery trên cùng database

Kịch bản trên container/VM tách biệt:

1. Seed một tập đơn hàng và ghi lại ID/version của những transaction đã **nhận commit ACK**.
2. Mở một transaction ghi khác nhưng cố ý giữ chưa commit, với marker riêng.
3. Gây dừng **không graceful** cho DB process trong môi trường test, bảo đảm volume dữ liệu và WAL được giữ nguyên.
4. Khởi động lại DB, đợi trạng thái healthy với deadline, không tự xóa/khởi tạo volume mới trong quá trình khởi động.
5. Kiểm tra mọi transaction đã được xác nhận commit còn đủ theo bảo đảm durability đang cấu hình; marker chưa commit không xuất hiện.
6. Kiểm tra constraint, outbox, trạng thái ứng dụng, rồi ghi một giao dịch mới để xác nhận DB có thể tiếp tục phục vụ.

Nếu test framework luôn tạo một container **mới với volume rỗng** khi restart, đó không phải kiểm thử recovery dữ liệu cũ. Phải kiểm chứng việc giữ nguyên volume và WAL thật sự diễn ra theo thiết kế.

PostgreSQL cần đủ WAL và metadata để chạy recovery. Không tự suy rằng thao tác `docker stop` graceful giống mất điện, hay rằng `kill -9` một kết nối ứng dụng giống DB crash. Đặt tên đúng mức fault đã được inject trong báo cáo.

### 7.2. Failover primary–replica

Với hệ có replica bất đồng bộ, một commit đã ACK trên primary **có thể chưa kịp đến replica** trước khi primary hỏng. Phải xác định chế độ đồng bộ/ACK và RPO cho phép; không mặc định mọi failover là zero data loss.

```text
Primary P: commit event E1 --ACK--> Java client
                       \
                        \  replication trễ
                         X  P hỏng
                          \
Replica R được promote ----> Có thể chưa có E1
```

Kiểm tra:

- Cụm test có cơ chế election/fencing chống **hai primary cùng nhận ghi**.
- Ứng dụng xử lý connection cũ hỏng, DNS/proxy/cấu hình pool được cập nhật tới leader mới.
- Đo chính xác những commit ID nào có/không có trên primary mới, thay vì nhìn số lượng hàng tổng quát.
- Nếu chính sách cho phép RPO lớn hơn 0, báo cáo số và phạm vi giao dịch bị mất, cách client/consumer đối soát.
- Kiểm tra read-your-writes: đọc replica đang lag có thể không thấy receipt vừa commit; kết luận “chưa thực hiện” từ một replica trễ có thể gây retry sai.

Failover và crash recovery không giống nhau. Crash recovery khôi phục **một DB từ log của chính nó**; failover còn liên quan lựa chọn replica, trạng thái sao chép, fencing và định tuyến lưu lượng.

## 8. Kiểm thử restore/PITR: bản sao hợp lệ phải dùng được

Một job backup báo thành công không chứng minh bản sao có thể phục hồi ứng dụng. Với PostgreSQL có thể kiểm thử logical restore qua `pg_dump/pg_restore`, hoặc physical restore từ base backup cộng WAL; PITR replay đến target đã chọn.

### Quy trình restore drill ở môi trường cách ly

1. **Chốt một mốc phục hồi:** backup ID, timestamp/LSN hoặc restore target theo cơ chế được hỗ trợ; lưu manifest gồm phiên bản DB, schema, role, extension, WAL range và secret/key cần thiết.
2. **Cách ly toàn bộ side effect:** mạng, broker, email, cổng thanh toán, object store và job nền phải trỏ đến sandbox hoặc bị vô hiệu hóa. Không cho worker restored tự gửi event thật.
3. **Khôi phục bằng công cụ chính thức:** dùng đúng phiên bản/cấu hình, backup đủ các thành phần, verify manifest/checksum rồi phục hồi.
4. **Chạy recovery và chờ ready:** xác định DB đã replay xong đến target và không còn ở chế độ bất ngờ (read-only, timeline sai, thiếu tablespace).
5. **Kiểm tra quyền và schema:** database role, migration version, index, constraint, sequence, extension và khả năng kết nối từ Java.
6. **Kiểm tra bất biến nghiệp vụ:** dữ liệu nhiều bảng, request receipts, outbox, ledger, foreign keys, tổng số đơn theo mốc và tính duy nhất.
7. **Đối soát các hệ thống ngoài:** xác định phần nào đã tồn tại sau target tại broker/payment và quyết định replay hay bù trừ an toàn.
8. **Đo RPO/RTO thật:** tính chênh lệch commit có thể phục hồi và thời gian từ sự cố tới lúc dịch vụ phục vụ use case thiết yếu.

Ví dụ chạy logical restore trong một database thử nghiệm đã chuẩn bị sẵn:

```bash
# Chỉ trên RESTORE LAB, không ghi đè DB thật.
# Credential được cấp qua kênh an toàn, không truyền password trên CLI.
pg_restore \
  --host=restore-db.internal.example \
  --username=restore_operator \
  --dbname=restore_lab \
  --no-owner \
  --no-acl \
  --exit-on-error \
  /secure/backups/orders_001.dump
```

Các cờ `--no-owner --no-acl` có thể giúp diễn tập dữ liệu/schema trong lab khi role nguồn không tồn tại, nhưng **không được xem là phép thử phục hồi quyền production**. Diễn tập đầy đủ phải có kế hoạch phục hồi role/ACL, extension, encryption key, sequence và các dependency liên quan.

Với PITR, cần đủ **base backup + chuỗi WAL liên tục tới target**; chỉ có bản base backup thì không suy ra khôi phục được mọi thời điểm sau đó. Phải xác nhận timeline/recovery target và khả năng giải mã/đọc dữ liệu. Không dùng restore drill để thử một thao tác phá hủy dữ liệu trên primary đang phục vụ.

## 9. Đối soát sau restore: so cái gì với cái gì?

Đối soát hiệu quả cần một **nguồn sự thật, mốc thời gian/phiên bản và khóa đối chiếu**. Không nên chỉ so `COUNT(*)` giữa DB nguồn lúc 14:00 và bản restore tại 13:00 rồi coi số khác nhau là dữ liệu hỏng; hai nguồn vốn có ranh giới thời gian khác nhau.

Một manifest kiểm tra có thể gồm:

```text
backup_id:      backup-2026-11-22-001     (minh họa)
source_db:      orders-primary
schema_version: 27
snapshot_marker: <LSN hoặc ID do hệ thống backup ghi>
restore_target: <mốc phục hồi đã chọn>
checked_orders: 1,000,000              (giá trị minh họa)
checks:
  - receipts liên kết tới order hợp lệ
  - mỗi receipt thành công có một outbox event theo hợp đồng
  - không có event ID trùng
  - mỗi operation ID ledger không bị áp dụng hai lần
  - constraints và migrations đủ cho ứng dụng phục hồi
```

**Không đưa giá trị giả trong manifest mẫu thành báo cáo đo thật.** Khi có dữ liệu production, chọn snapshot/histogram an toàn về riêng tư và ghi nguồn tạo mỗi mốc.

### 9.1. Đối soát nội bộ cùng database

Với schema ví dụ ở phần 4, mọi receipt của command thành công phải có outbox tương ứng:

```sql
SELECT r.request_id, r.order_id
FROM request_receipts r
LEFT JOIN outbox_events e
  ON e.request_id = r.request_id
WHERE r.operation = 'PAY_ORDER'
  AND e.event_id IS NULL;
```

Kết quả kỳ vọng là **không hàng nào** nếu hợp đồng thiết kế là “mọi receipt thành công tạo đúng một event”. Nếu có hàng trả về, cần điều tra vì sao một transaction có thể ghi receipt nhưng thiếu event, hoặc quy trình migration/cleanup có xóa event cũ hay không. Không tự sửa bằng cách phát sự kiện mới khi chưa xác minh nguồn và trạng thái của consumer.

Kiểm tra tính hợp lệ của khóa tham chiếu và phiên bản:

```sql
SELECT o.order_id, o.status, o.version
FROM orders o
WHERE o.version < 0
   OR o.status NOT IN ('PENDING', 'PAID', 'CANCELLED');

SELECT e.event_id, e.order_id
FROM outbox_events e
LEFT JOIN orders o ON o.order_id = e.order_id
WHERE o.order_id IS NULL;
```

Trong schema có check và FK, các truy vấn có thể trả rỗng nhờ DB đã bảo vệ dữ liệu; chúng vẫn giúp nêu rõ **bất biến cần kiểm tra**. Không dùng `orders.status = 'PAID'` hiện tại làm điều kiện bắt buộc cho mọi event `ORDER_PAID` trong quá khứ, vì đơn có thể hợp lệ chuyển sang trạng thái khác sau khi event được phát. Với dữ liệu có lịch sử, phải đối soát **trình tự/sự kiện tại mốc phù hợp**, không so một event lịch sử với trạng thái cuối một cách máy móc.

### 9.2. Đối soát hai hệ thống

Nếu `orders` nằm ở DB A và thanh toán ở DB B, SQL JOIN trực tiếp có thể không có hoặc không phản ánh cùng thời điểm. Một quy trình hợp lý:

1. Xuất các **operation ID đã commit** ở A tới một mốc/watermark được xác nhận.
2. Xuất các **payment/ledger operation ID đã xử lý** ở B tới mốc tương ứng, kèm trạng thái và số tiền.
3. So hai tập khóa theo tenant và operation type, đánh dấu: `missing-in-A`, `missing-in-B`, `mismatch-amount`, `duplicate`, `pending-within-lag-window`.
4. **Chờ giới hạn eventual consistency** đã định trước khi phân loại thiếu thật; sự kiện đang trên đường truyền không phải lúc nào cũng là lỗi.
5. Với mỗi chênh lệch, xác định **nguồn có thẩm quyền**, hành động cần làm (replay, bù trừ, chuyển xử lý thủ công) và audit trail.

Không dùng một phép `COUNT(*)` bằng nhau để chứng minh hai tập dữ liệu giống nhau: hai bên có thể thiếu những ID khác nhau mà tổng số vẫn trùng. Không sửa thẳng ledger bằng UPDATE khi chưa có quy trình điều chỉnh có kiểm toán.

### 9.3. Đối soát outbox và inbox khi replay

Nếu DB nguồn restore về trước khi publisher đã gửi sự kiện E, row outbox có thể trở về trạng thái `PENDING` dù broker/consumer **đã nhận E**. Lần publish sau là **redelivery hợp lệ** của cùng event ID.

- Consumer cần marker độc nhất như `(consumer_name, event_id)`, được commit **trong cùng transaction với hiệu ứng local**.
- Event payload phải có version/operation ID ổn định; nếu có out-of-order, xử lý theo hợp đồng (chỉ áp dụng snapshot mới hơn hoặc xếp hàng delta chờ đủ thứ tự).
- Nếu DB consumer cũng được restore về trước lúc xử lý E, marker có thể mất trong khi email/thanh toán ngoài DB đã xảy ra. Khi ấy, chỉ marker nội bộ **không đủ**; cần idempotency key ở hệ thống ngoài và đối soát tác động đã thực hiện.
- Bản backup phục hồi có thể mang các sự kiện đã được phát hoặc chưa được phát theo một mốc khác với broker, nên phải ghi lại offset/watermark/correlation ID nếu kiến trúc sử dụng được.

## 10. Kịch bản kiểm thử idempotent consumer

Giả sử dịch vụ B xử lý event `ORDER_PAID` và ghi bản ghi ledger local. Sự kiện có `event_id` ổn định; bảng `processed_events` giúp phân biệt delivery lại.

```sql
CREATE TABLE payment_ledger (
    ledger_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id UUID NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Mẫu transaction local:

```sql
BEGIN;

INSERT INTO processed_events(consumer_name, event_id)
VALUES ('payment-ledger', :event_id)
ON CONFLICT DO NOTHING;
-- Chỉ tiếp tục INSERT ledger khi số hàng vừa thêm bằng 1.

INSERT INTO payment_ledger(ledger_id, order_id, amount)
VALUES (:event_id, :order_id, :amount);

COMMIT;
-- ACK broker chỉ sau commit thành công.
```

Đoạn trên là **pseudocode điều kiện**: JDBC phải kiểm tra affected rows của câu insert marker và **bỏ qua INSERT ledger nếu marker đã tồn tại**. Không được chạy nguyên văn cả hai câu INSERT bất kể kết quả, vì như vậy event lặp có thể gây vi phạm unique key hoặc lặp hiệu ứng ở bảng không có constraint. Các placeholder `:event_id` được viết để giải thích, không phải cú pháp `PreparedStatement` thuần.

Các bước test:

1. Đưa event E tới consumer lần đầu; xác nhận marker và ledger commit.
2. Cố ý **không ACK** broker sau DB commit để broker giao lại E.
3. Giao lại đúng event ID và cùng payload; xác nhận ledger chỉ có một record, marker chỉ một record.
4. Gửi lại cùng ID nhưng payload khác; **không âm thầm xem như trùng hợp lệ**. Cần kiểm tra payload hash/khóa nghiệp vụ theo hợp đồng và cảnh báo sự kiện giả mạo hoặc schema mismatch.
5. Thử lỗi trước commit; marker và ledger phải cùng rollback, redelivery sau đó thực sự xử lý được.

Một consumer gửi HTTP/SMS hoặc thực hiện thanh toán ở bên ngoài transaction local cần chiến lược riêng (outbox bên consumer, idempotency từ provider, đối soát); bảng `processed_events` **không làm cho cuộc gọi ngoài DB trở thành atomic**.

## 11. RPO, RTO và mốc khôi phục phải được đo

| Chỉ số | Định nghĩa cho test | Cách thu chứng cứ |
| --- | --- | --- |
| **RPO** (*Recovery Point Objective*) | Mức mất dữ liệu đã được xác nhận tối đa có thể chấp nhận sau một loại sự cố | So tập transaction/operation ID đã ACK với tập được khôi phục tại target |
| **RTO** (*Recovery Time Objective*) | Thời gian mục tiêu từ sự cố tới khi dịch vụ thiết yếu hoạt động được | Ghi timestamp fault, restore, schema validation, health và giao dịch thử |
| **Recovery duration** | Thời gian thực thi từng bước restore/replay | Log backup fetch, giải mã, restore, WAL replay, startup |
| **Consistency error rate** | Số vi phạm bất biến nội bộ và chênh lệch không thể giải thích | SQL checks, reconciliation reports, audit |
| **Outbox lag/backlog** | Độ tuổi và số event chưa hoàn tất | Pending/claimed/retry count, thời gian publish và ACK |
| **Duplicate business effects** | Số lần operation ID gây hiệu ứng thực ngoài mong đợi | Unique ledger key, provider idempotency, đối soát |
| **Failover data gap** | Những commit có ở leader cũ mà không có ở leader mới | So commit receipts hoặc log/LSN theo hỗ trợ DB |

Một công thức diễn giải cho sự cố tại thời điểm `T_fault`, và transaction commit mới nhất còn được khôi phục tại `T_recoverable`:

\[
\text{Actual recovery gap} \approx T_{\text{fault}} - T_{\text{recoverable}}
\]

Chỉ là phép ước lượng theo thời gian khi các mốc đồng hồ đáng tin cậy và có định nghĩa phù hợp. Khi hệ thống có đồng hồ lệch, lưu lượng lớn hoặc transaction xuyên vùng, **danh sách operation ID/commit markers** đáng tin cậy hơn chỉ so timestamp. Phân biệt **RPO mục tiêu** với **mất mát quan sát được**; một lần không mất dữ liệu không chứng minh mọi lần failover sẽ không mất.

RTO cũng phải tính **thời gian kiểm chứng và chuyển lưu lượng ứng dụng**, không chỉ thời gian database mở cổng TCP. DB “healthy” nhưng Java service không chạy được vì sai schema/role/certificate thì chưa phải phục hồi nghiệp vụ.

## 12. Runbook kiểm thử phục hồi theo từng pha

| Pha | Việc thực hiện | Điều kiện vượt qua |
| --- | --- | --- |
| **1. Chuẩn bị** | Chọn kịch bản F1–F10, xác định SLO/RPO/RTO, DB/worker test, quyền hạn và người chịu trách nhiệm | Có manifest, rollback và môi trường cách ly |
| **2. Seed** | Tạo dữ liệu và operation ID có thể đối soát; ghi snapshot/LSN phù hợp | Biết chính xác dữ liệu ban đầu và invariants |
| **3. Đưa hệ thống vào trạng thái cần kiểm** | Mở transaction, đợi một mốc sau UPDATE/COMMIT/publish theo lịch | Có bằng chứng đạt đúng điểm chèn lỗi |
| **4. Inject fault** | Ngắt connection, stop container, failover hoặc chặn ACK theo kịch bản | Fault chỉ tác động tài nguyên test được cho phép |
| **5. Khôi phục** | Reconnect, restart/replay WAL, promote replica hoặc restore backup; bật lại thành phần có kiểm soát | DB và application đạt trạng thái phục vụ trong deadline |
| **6. Verify local** | Kiểm tra commit/rollback, receipt, version, FK, unique, outbox | Không có nửa transaction hoặc bất biến bị phá |
| **7. Reconcile external** | Đối chiếu event ID, inbox, ledger, payment operation, mốc lag | Chênh lệch được phân loại và có hành động an toàn |
| **8. Report** | Lưu RPO/RTO đo được, lỗi, trace và bước đã thực hiện; rút ra điều chỉnh | Kết quả tái lập được, có owner theo dõi |

**Ngưỡng dừng** phải được định nghĩa từ đầu: test kéo dài quá hạn, tài nguyên lưu trữ thấp, bộ phát lỗi không còn kiểm soát, hoặc kết nối bất ngờ hướng vào môi trường ngoài sandbox thì phải dừng và bảo vệ dữ liệu. Không tiếp tục phá lỗi chỉ để lấy một biểu đồ đẹp.

### Những dấu hiệu kết quả thử nghiệm không đáng tin

- Worker ghi SQL trên database khác với DB mà bài test kiểm tra sau đó.
- Sau khi “restart” lại tạo volume mới thay vì recovery dữ liệu cũ.
- Đọc đối soát từ replica đang lag mà không kiểm tra mốc replay.
- Chỉ kiểm tra số hàng, không kiểm tra ID, tổng ledger, version hoặc outbox.
- Fault injector ném lỗi trước commit nhưng báo đã kiểm tra mất ACK **sau commit**.
- Cho worker restored phát email/thu tiền thật trong lúc diễn tập.
- Test không có timeout/cleanup, hoặc exception bị nuốt và vẫn báo pass.
- RPO/RTO chỉ tính khôi phục DB, bỏ qua schema migration, secret và application readiness.

## 13. Thiết kế quan sát và bằng chứng sau sự cố

Một bản ghi đủ dùng cho phân tích nên chứa các **ID không bí mật** và mốc xử lý:

```text
test_run_id=it-recovery-0042
fault_case=F4_AFTER_COMMIT_BEFORE_HTTP_REPLY
request_id=8e2a...          (ID minh họa/rút gọn)
order_id=42
db_commit_ack_observed=true
http_reply_delivered=false
retry_same_request_id=true
receipt_rows=1
outbox_rows=1
order_version=1
result=PASS
```

Đây chỉ là ví dụ cấu trúc báo cáo, **không phải kết quả test đã chạy**. Trong môi trường thực, lưu toàn bộ UUID trong kho log có kiểm soát nếu cần đối soát, nhưng không log mật khẩu, token, số thẻ, dữ liệu khách hàng hay JDBC URL chứa credential.

Nên thu thêm:

- JDBC/connection pool: lỗi SQLSTATE, số connection đang hoạt động/chờ, connection timeout và thời lượng transaction.
- Database: WAL/replay progress, restart recovery log, leader/replica role, lock wait, thời gian lên healthy.
- Publisher/consumer: số event pending, leased, retry, sent, processed, failed; tuổi event lâu nhất và số redelivery.
- Application: HTTP error/timeout, số retry, circuit breaker, queue depth, idempotency conflict, p95/p99 sau recovery.
- Ops: manifest backup, checksum, mốc snapshot/LSN, quyền restore, schema version, RPO/RTO và kết quả validation.

Để tránh “test pass vì không có request”, bài test phải chứng minh **đã phát đủ lượng công việc**, có thành phần thực sự gặp fault và đã nhận đủ kết quả hoặc timeout được phân loại. Tổng `attempted`, `completed`, `failed` và `unknown` cần được ghi riêng.

## 14. Các kiểu đối soát và hành động sửa chữa

Không phải chênh lệch nào cũng được phép “sửa cho bằng nhau” bằng UPDATE. Cần phân loại:

| Chênh lệch | Ví dụ | Hành động có thể đúng |
| --- | --- | --- |
| **Chưa xử lý nhưng còn hợp lệ** | Outbox chờ sau restart | Retry publish cùng event ID, có backoff/deadline |
| **Trùng delivery** | Broker giao E hai lần | Dedupe ở consumer; không ghi ledger lần hai |
| **Thiếu event do bug nguồn** | Receipt thành công nhưng không có outbox | Điều tra transaction boundary; tái tạo qua quy trình audit có xác minh |
| **Mất commit sau failover bất đồng bộ** | Client đã thấy ACK, leader mới thiếu receipt | Đối chiếu RPO, dữ liệu nguồn cũ nếu còn, reprocess bằng ID và chính sách nghiệp vụ |
| **Nguồn restore cũ, đích ngoài vẫn mới** | DB đơn hàng thiếu thanh toán đã thu | Đối soát provider và ledger; replay hoặc nghiệp vụ bù trừ có audit |
| **Payload cùng ID nhưng không khớp** | Event E có hai giá trị tiền khác nhau | Quarantine/alert, không tự xem là idempotent hợp lệ |
| **Chênh lệch trong cửa sổ lag** | Read model chưa bắt kịp watermark | Đợi theo giới hạn; không tạo thay đổi kép |
| **Vi phạm bất biến lịch sử** | Ledger tổng không cân dù mọi ID có mặt | Điều tra quy tắc nghiệp vụ, đối chiếu sổ cái/biên lai, sửa bằng bút toán điều chỉnh |

Người vận hành cần biết **ai có thẩm quyền quyết định** replay, bù trừ, hủy hoặc điều chỉnh thủ công. Đặc biệt với thanh toán, bù trừ thường là một giao dịch nghiệp vụ **mới** có mã riêng và audit trail, không phải xóa transaction lịch sử để làm báo cáo đẹp.

## 15. Bài tập thực hành

### Bài tập 1: mất response sau commit

API xác nhận đơn đã commit và có receipt/outbox; trước khi HTTP response gửi tới client, tiến trình lỗi. Client retry và tạo UUID mới cho request. Rủi ro là gì?

**Đáp án:** ứng dụng có thể không nhận diện được đây là cùng nghiệp vụ, dẫn đến xử lý lặp hoặc kết quả khó đối soát. Client/service nên dùng **idempotency key ổn định**; khi retry phải kiểm tra receipt với **cùng ID và cùng input**, sau đó trả kết quả thích hợp. Không suy thất bại từ việc response mất.

### Bài tập 2: lỗi trước và trong COMMIT

Một test ném `SQLException` trước khi gọi `commit()` rồi tuyên bố đã mô phỏng “commit unknown”. Nhận định này sai ở đâu?

**Đáp án:** chưa có COMMIT nào được gửi nên test chỉ chứng minh lỗi **trước commit**. Để có kết quả chưa rõ, phải có khả năng DB đã nhận/xử lý commit nhưng client không nhận ACK; dùng proxy/fault injection tại connection thực, và tra DB bằng request ID để phân biệt.

### Bài tập 3: crash recovery và volume

Test dừng container PostgreSQL, sau đó tạo container mới với database rỗng; mọi test query đều chạy được. Có thể kết luận WAL recovery thành công không?

**Đáp án:** không. Test đã khởi tạo DB khác chứ không restart **cùng data directory/WAL**. Phải giữ volume cũ, phân biệt transaction ACK và chưa commit, restart rồi đối chiếu markers.

### Bài tập 4: hai hệ thống restore lệch mốc

DB A đơn hàng restore về 10:00, DB B thanh toán giữ đến 10:10. B có payment ID P, A chưa có bản ghi tương ứng. Có nên xóa payment ở B?

**Đáp án:** không tự động. Xác định payment P đã thu tiền thật hay chỉ ghi nhận dự kiến, nguồn dữ liệu có thẩm quyền và khả năng replay record A. Nếu cần hoàn tiền, đó là **bù trừ có audit**, không phải xóa lịch sử nhằm làm hai bảng có số dòng bằng nhau.

### Bài tập 5: outbox được phát lại

Trước backup đã có event E được consumer xử lý. Restore nguồn về trước lúc đánh dấu E SENT nên publisher gửi lại E. Có vi phạm mô hình outbox không?

**Đáp án:** không nhất thiết; at-least-once cho phép gửi lại. Consumer cần marker unique theo `event_id` trong cùng transaction với hiệu ứng local, hoặc dùng downstream idempotency nếu tác động nằm ngoài DB. Nếu inbox marker cũng bị restore mất, cần đối soát với nguồn ngoài.

### Bài tập 6: đo RTO đúng

Database phục hồi sau 90 giây, nhưng ứng dụng Java phải cập nhật truststore/migration và chỉ phục vụ lại sau 7 phút. RTO quan sát được cho nghiệp vụ thiết yếu nên báo là bao nhiêu?

**Đáp án:** khoảng **7 phút** nếu tính từ mốc sự cố tới khi nghiệp vụ được kiểm chứng phục vụ lại. 90 giây chỉ là một bước của quá trình khôi phục DB, không phải RTO đầy đủ của dịch vụ.

### Checklist trước khi công nhận bài test phục hồi đạt yêu cầu

- Đã phân biệt **lỗi trước commit, commit chưa rõ, lỗi sau commit** và fault injector chèn đúng mốc chưa?
- Test có DB/volume test độc lập, data seed/ID ổn định, ranh giới transaction và kỳ vọng atomic rõ không?
- Có kiểm tra transaction đã ACK và chưa commit trên DB sau crash/restart, không chỉ xem service healthy không?
- Với failover, đã kiểm tra leader duy nhất, replication lag, khả năng mất commit theo RPO và kết nối pool mới chưa?
- Với restore/PITR, có đủ backup/WAL, manifest, schema/role/secret, và môi trường không gửi side effect thật không?
- Có đối soát bằng **operation/event ID**, version, ledger và invariant — thay vì chỉ `COUNT(*)` — chưa?
- Retry dùng cùng idempotency key, consumer dedupe đúng transaction và xử lý payload trùng ID khác nội dung chưa?
- Có giới hạn deadline, backoff, cleanup, log SQLSTATE, số request unknown và evidence của fault đã inject chưa?
- RPO/RTO và sự khác biệt giữa DB recovery với business recovery có được đo và báo cáo rõ chưa?
- Sau khi tìm ra lệch, có runbook replay/bù trừ với quyền, audit và cơ chế rollback/forward-fix phù hợp chưa?

**Kết luận:** Kiểm thử phục hồi và đối soát sau sự cố phải bao trùm **từ transaction và WAL tới thông điệp, request và tác động nghiệp vụ**. Một hệ thống đáng tin không cần giả định mọi lỗi đều biến mất: nó phải biết phân loại kết quả commit, retry bằng khóa ổn định, phục hồi từ backup/log đúng phạm vi và đối soát theo bằng chứng bền vững. Chỉ khi các bất biến, RPO/RTO, trạng thái các dịch vụ và quy trình sửa chênh lệch được kiểm chứng, ta mới có căn cứ nói rằng ứng dụng Java đã **phục hồi đúng**, chứ không chỉ “chạy lại được”.
