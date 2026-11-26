# Idempotent ItemWriter

> **Chương:** Idempotency
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình xử lý phân tán. Bài học tập trung vào cách thiết kế `ItemWriter` chịu được ghi lặp khi retry/restart, tránh tác dụng phụ trùng và kiểm soát tải khi nhiều worker cùng ghi.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa tính **idempotent** của một thao tác ghi theo kết quả nghiệp vụ quan sát được.
2. Phân biệt retry, restart, re-run và xử lý trùng do parallel steps/partitioning, từ đó chọn khóa idempotency ổn định.
3. Xây dựng `ItemWriter` dùng unique constraint và `INSERT ... ON CONFLICT` để ghi an toàn khi cùng item xuất hiện nhiều lần.
4. Nhận biết khi nào thao tác `UPDATE`, gửi API, phát sự kiện hoặc cập nhật số dư **không** idempotent, dù writer không ném exception.
5. Kiểm tra, đo lường và vận hành idempotent writer trong workload lớn, bao gồm các tình huống rollback, restart và ghi đồng thời.

## 1. Idempotent ItemWriter là gì?

Trong Spring Batch, `ItemWriter<T>` nhận một **chunk** các item đã được đọc và xử lý rồi thực hiện ghi ra đích. Với Spring Batch 5.x trở lên, phương thức cốt lõi có dạng:

~~~java
void write(Chunk<? extends T> chunk) throws Exception;
~~~

Một thao tác ghi là **idempotent** khi áp dụng lại **cùng một yêu cầu nghiệp vụ** không làm thay đổi kết quả nghiệp vụ cuối cùng ngoài kết quả của lần áp dụng hợp lệ đầu tiên. Diễn đạt theo trạng thái:

\[
W(W(S, x), x) = W(S, x)
\]

Trong đó `S` là trạng thái đích, `x` là một item có định danh ổn định và `W` là hiệu ứng của writer. Công thức nói về **trạng thái/hiệu ứng nghiệp vụ**, không đòi số lần gọi hàm, log hay số lần retry đều giống nhau.

Ví dụ:

| Thao tác trên cùng item | Idempotent? | Giải thích |
| --- | --- | --- |
| `SET order_status = 'PAID'` | Thường có, nếu không tạo thêm side effect | Gán cùng giá trị hai lần cho cùng kết quả lưu trữ |
| `INSERT ... ON CONFLICT DO NOTHING` theo event ID ổn định | Có, đối với bảng được bảo vệ bởi unique key | Chỉ lần đầu tạo bản ghi, lần sau bỏ qua |
| `balance = balance + 100` | Không | Cùng item chạy lại làm tăng số dư thêm 100 |
| `INSERT` sinh khóa tự tăng mới mỗi lần | Không | Một sự kiện có thể tạo nhiều hàng |
| Gọi API tạo lệnh thanh toán mới mỗi lần | Không, trừ khi phía nhận dedupe đúng | Retry có thể tạo nhiều giao dịch |
| `UPDATE ... SET updated_at = now()` | Không hoàn toàn | Ghi lặp làm đổi thời gian và có thể kích hoạt trigger/event |

**Idempotency là đặc tính của toàn bộ hiệu ứng nghiệp vụ**: key, dữ liệu, transaction, điều kiện ghi, trigger, downstream event và hệ thống bên ngoài. Một hàm writer thuần Java không tự trở thành idempotent chỉ nhờ chạy trong Spring Batch.

## 2. Vì sao writer có thể được gọi lặp?

Spring Batch hỗ trợ transaction và cơ chế restart, nhưng điều đó **không** đồng nghĩa tất cả tác dụng phụ của một chunk chỉ xảy ra đúng một lần.

~~~mermaid
sequenceDiagram
    participant B as Spring Batch
    participant W as ItemWriter
    participant D as Database/đích
    B->>W: write(chunk A)
    W->>D: Ghi item 101, 102
    D-->>W: Thành công
    Note over B,D: Sự cố trước khi hoàn tất/ghi nhận kết quả
    B->>W: Thử lại hoặc chạy lại chunk A
    W->>D: Ghi lại item 101, 102
    Note over D: Đích cần xử lý ghi lặp đúng cách
~~~

Các nguồn phát sinh ghi lặp phổ biến:

- **Retry trong step:** Lỗi tạm thời khi xử lý/ghi có thể khiến cùng item hoặc một nhóm item được thử lại, tùy chính sách retry, rollback và buffering.
- **Restart sau sự cố:** Job tiếp tục từ trạng thái checkpoint; những thao tác ngoài transaction hoặc những chunk chưa được ghi nhận commit có thể được thực hiện lại.
- **Re-run với cùng tập nguồn:** Người vận hành chạy lại job bằng tham số mới, lịch scheduler gọi lại, hoặc hệ thống nguồn phát lại event.
- **Nhiều worker/partition:** Partition giao thoa, thông điệp gửi lại, hoặc hai job cùng lấy chung tập bản ghi có thể ghi cùng business key.
- **Không rõ kết quả đích:** Đích đã nhận thao tác nhưng mạng đứt trước khi trả response; phía gửi không thể suy rằng request chưa thành công.

Nếu reader, processor và writer đều thao tác trên **cùng database** và cùng transaction chunk, lỗi trước commit thường dẫn đến rollback phần ghi chưa commit. Tuy nhiên, một job vẫn cần quy tắc xử lý replay, nhất là với **I/O ngoài transaction**, re-run input, lỗi sau commit nhưng trước khi caller nhận kết quả và hệ thống phân tán. Retry/restart là cơ chế điều hành xử lý; idempotency là bảo vệ tính đúng đắn tại đích.

## 3. Chọn khóa idempotency trước khi viết code

Không thể chống trùng nếu hệ thống không xác định được **hai yêu cầu nào thực sự là cùng một tác vụ nghiệp vụ**.

| Loại dữ liệu | Khóa gợi ý | Lưu ý |
| --- | --- | --- |
| Event từ hệ thống nguồn | `(source_system, source_event_id)` | Event ID phải được giữ nguyên qua retry và phát lại |
| Import đơn hàng theo phiên bản | `(source_system, order_id, version)` | Cùng order ID nhưng version mới có thể là thay đổi hợp lệ |
| Yêu cầu chuyển tiền/thanh toán | `business_request_id` hoặc idempotency key do caller cấp | Không được tạo UUID mới cho mỗi lần retry |
| Dòng dữ liệu trong file bất biến | `(file_identity, row_id)` | `file_identity` phải là định danh lô dữ liệu nguồn ổn định |
| Ghi trạng thái hiện tại của entity | Khóa thực thể + version/quy tắc upsert | Phải định nghĩa rõ bản cập nhật mới ghi đè bản cũ ra sao |

Một số sai lầm thường gặp:

- Dùng `JobExecutionId`, timestamp hiện tại hoặc UUID sinh **ngay trong mỗi lần gọi writer**: các lần retry có key khác nhau nên không thể nhận diện trùng.
- Dùng số dòng đơn lẻ khi file có thể được thay mới, sắp xếp lại hoặc thay đổi giữa các lần chạy.
- Chỉ dùng `order_id` khi nghiệp vụ cho phép nhiều phiên bản/event hợp lệ của cùng một đơn hàng.
- Dedupe bằng `HashSet` trong RAM: không bảo vệ restart, nhiều JVM hoặc nhiều partition.
- Kiểm tra `SELECT EXISTS` trước rồi mới `INSERT` nhưng thiếu unique constraint: hai thread có thể cùng thấy “chưa tồn tại” và đều ghi.

**Điều kiện nền:** key phải ổn định, có phạm vi uniqueness rõ ràng và được lưu tại nơi tất cả worker cùng quan sát được. Với hệ thống dữ liệu lớn, unique index/constraint trong database thường là chốt chặn quan trọng nhất khi nhiều job hoặc partition ghi đồng thời.

## 4. Ví dụ thực hành: JdbcBatchItemWriter ghi event một lần

Giả sử job nhận event giao dịch từ hệ thống upstream. Mỗi event có `sourceSystem`, `eventId`, `orderId`, `amountCents` và `payloadHash`. Nếu upstream phát lại cùng event, ta chỉ muốn lưu **một** bản ghi. Ví dụ sử dụng PostgreSQL và API Spring Batch 5.x.

### 4.1. Ràng buộc uniqueness tại database

~~~sql
CREATE TABLE ingested_order_events (
    source_system  VARCHAR(40)  NOT NULL,
    event_id       VARCHAR(120) NOT NULL,
    order_id       VARCHAR(120) NOT NULL,
    amount_cents   BIGINT       NOT NULL,
    payload_hash   CHAR(64)     NOT NULL,
    PRIMARY KEY (source_system, event_id)
);
~~~

Primary key đảm bảo hai transaction đồng thời không thể commit hai hàng có cùng cặp `(source_system, event_id)`. `payload_hash` có thể dùng để **phát hiện cùng ID nhưng nội dung khác**, thay vì coi mọi conflict là bản sao hợp lệ.

### 4.2. Writer dùng upsert với nhánh bỏ qua trùng

~~~java
import javax.sql.DataSource;
import org.springframework.batch.item.database.JdbcBatchItemWriter;
import org.springframework.batch.item.database.builder.JdbcBatchItemWriterBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;

record OrderEvent(
        String sourceSystem,
        String eventId,
        String orderId,
        long amountCents,
        String payloadHash) {}

@Configuration
class ImportWriterConfig {

    @Bean
    JdbcBatchItemWriter<OrderEvent> idempotentEventWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<OrderEvent>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO ingested_order_events
                        (source_system, event_id, order_id,
                         amount_cents, payload_hash)
                    VALUES
                        (:sourceSystem, :eventId, :orderId,
                         :amountCents, :payloadHash)
                    ON CONFLICT (source_system, event_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(item ->
                    new MapSqlParameterSource()
                        .addValue("sourceSystem", item.sourceSystem())
                        .addValue("eventId", item.eventId())
                        .addValue("orderId", item.orderId())
                        .addValue("amountCents", item.amountCents())
                        .addValue("payloadHash", item.payloadHash()))
                .assertUpdates(false)
                .build();
    }
}
~~~

**Vì sao cần `assertUpdates(false)`?** Khi PostgreSQL xử lý một hàng trùng bằng `DO NOTHING`, số hàng thay đổi có thể bằng **0**. `JdbcBatchItemWriter` mặc định có thể coi batch không cập nhật hàng nào là lỗi nếu còn bật kiểm tra số hàng cập nhật; tắt kiểm tra này là phù hợp khi **0 hàng được ghi** là kết quả nghiệp vụ hợp lệ. Cần theo dõi hàng thực sự chèn bằng metric hoặc truy vấn riêng.

Ví dụ dùng cú pháp `ON CONFLICT` của **PostgreSQL**; MySQL, SQL Server và các database khác có cơ chế UPSERT/merge riêng, với hành vi khóa và độ an toàn cần kiểm tra theo sản phẩm. `JdbcBatchItemWriter` không tự cung cấp logic dedupe nếu câu SQL không định nghĩa nó.

**Transaction:** Gắn writer này vào chunk step dùng `PlatformTransactionManager` quản lý **cùng DataSource/transaction** với câu ghi. Tránh tự mở transaction độc lập cho mỗi item: nếu một phần chunk commit riêng rồi phần còn lại thất bại, mô hình rollback của step sẽ khác dự kiến.

**Phạm vi idempotency:** Ví dụ đảm bảo “ghi một hàng event có key này tối đa một lần” tại bảng đích. Nếu sau đó còn cập nhật số dư, trừ tồn kho hoặc gọi API, những tác dụng phụ đó phải có cơ chế idempotency riêng hoặc được kết hợp đúng trong transaction.

### 4.3. Đừng âm thầm bỏ qua xung đột nội dung

`DO NOTHING` cũng sẽ bỏ qua bản ghi mang **cùng event ID nhưng amount/hash khác**. Nếu nghiệp vụ không chấp nhận chuyện này, cần có bước phát hiện và xử lý riêng:

1. Chuẩn hóa payload và tính hash theo quy tắc cố định ở upstream/processor.
2. Khi gặp conflict, đối chiếu hash và các trường quan trọng với bản ghi đã lưu; nếu khác, chuyển vào vùng điều tra hoặc báo lỗi dữ liệu.
3. Chỉ coi bản ghi lặp là thành công nếu key **và nội dung nghiệp vụ** khớp quy tắc đã thống nhất.

Một số hệ thống dùng `ON CONFLICT DO UPDATE SET ...` để cập nhật trạng thái mới nhất. Cách này chỉ idempotent khi cập nhật cùng input không sinh thêm hiệu ứng quan sát được; trigger, audit row, `updated_at = NOW()` và publish event mỗi lần UPDATE đều có thể phá tính chất đó.

## 5. Trường hợp khó hơn: cập nhật cộng dồn một lần

Giả sử một event yêu cầu **trừ 500 đơn vị** khỏi số dư. Không thể làm writer idempotent bằng cách lặp câu SQL sau:

~~~sql
UPDATE accounts
SET balance_cents = balance_cents - 500
WHERE account_id = 123;
~~~

Mỗi lần chạy lại đều trừ thêm. Cần ghi nhận event đã xử lý và áp dụng thay đổi **trong cùng transaction**:

~~~sql
CREATE TABLE processed_debits (
    event_id      VARCHAR(120) PRIMARY KEY,
    account_id    BIGINT NOT NULL,
    amount_cents  BIGINT NOT NULL
);
~~~

Một ví dụ writer thực hiện logic ở tầng JDBC:

~~~java
import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.JdbcTemplate;

record DebitEvent(String eventId, long accountId, long amountCents) {}

final class DebitOnceWriter implements ItemWriter<DebitEvent> {
    private final JdbcTemplate jdbc;

    DebitOnceWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(Chunk<? extends DebitEvent> chunk) {
        for (DebitEvent event : chunk) {
            int inserted = jdbc.update("""
                INSERT INTO processed_debits
                    (event_id, account_id, amount_cents)
                VALUES (?, ?, ?)
                ON CONFLICT (event_id) DO NOTHING
                """,
                event.eventId(),
                event.accountId(),
                event.amountCents());

            // Chỉ sự kiện được chấp nhận lần đầu mới tác động số dư.
            if (inserted == 1) {
                int updated = jdbc.update("""
                    UPDATE accounts
                    SET balance_cents = balance_cents - ?
                    WHERE account_id = ? AND balance_cents >= ?
                    """,
                    event.amountCents(),
                    event.accountId(),
                    event.amountCents());

                if (updated != 1) {
                    throw new IllegalStateException(
                        "Tài khoản không tồn tại hoặc không đủ số dư");
                }
            }
        }
    }
}
~~~

Mã này là **minh họa nguyên tắc**, giả định `event_id` là duy nhất toàn hệ thống, số tiền hợp lệ (dương), bảng `accounts` tồn tại, và cả hai câu SQL được thực thi trên **cùng database và cùng transaction chunk**. Khi cập nhật số dư thất bại và exception dẫn tới rollback, hàng `processed_debits` cũng phải rollback. Nếu writer tự tạo transaction khác, hoặc hai bảng nằm ở hai hệ thống không chia sẻ transaction, kết luận này không còn đúng. Trong ứng dụng tiền tệ, cần thêm kiểm tra quyền, quy tắc phí, định danh giao dịch và bất biến nghiệp vụ theo thiết kế riêng.

Hai worker cùng nhận một `eventId` sẽ tranh chấp trên unique key; tối đa một transaction tạo bản ghi `processed_debits` thành công. Nhờ đó chỉ worker thắng mới tiến hành giảm số dư. Việc cập nhật tài khoản có điều kiện cũng giúp kiểm soát số dư khi các **event khác nhau** diễn ra đồng thời. Vẫn cần quyết định nghiệp vụ đối với event có cùng key nhưng khác nội dung: không được tự động coi là bản sao hợp lệ.

**Nguyên tắc:** Dedupe bằng bảng ledger và thay đổi trạng thái chính phải có **ranh giới atomic**. Nếu chỉ chèn “đã xử lý” rồi gọi hệ thống khác, crash nằm giữa hai thao tác có thể khiến event bị đánh dấu xong nhưng hiệu ứng thực tế chưa xảy ra.

## 6. Khi writer gọi API hoặc gửi message

Database transaction của Spring Batch thường **không** rollback được lệnh HTTP, email, thanh toán hoặc sự kiện đã gửi sang broker. Có hai tình huống đối nghịch:

| Thứ tự xử lý | Cửa sổ lỗi | Hậu quả |
| --- | --- | --- |
| Gọi API trước, sau đó ghi checkpoint | API thành công nhưng job chết trước checkpoint | Retry có thể gọi API lần nữa |
| Đánh dấu đã xử lý trước, sau đó gọi API | Job chết sau khi đánh dấu, trước khi API thành công | Event có thể bị bỏ sót |

### 6.1. Nếu phía API hỗ trợ idempotency key

Chọn một key **cố định theo yêu cầu nghiệp vụ** và gửi lại đúng key đó qua mọi retry:

~~~http
POST /payments
Idempotency-Key: payment-request-8cf2
Content-Type: application/json

{"orderId":"O-1842","amountCents":50000}
~~~

Ví dụ chỉ mang tính minh họa: endpoint phải **thực sự** định nghĩa và lưu kết quả theo `Idempotency-Key`; chỉ thêm header ở client không tạo ra bảo đảm. Kiểm tra phạm vi key (theo tài khoản/merchant), thời hạn lưu dedupe, hành vi khi cùng key nhưng khác payload, mã response khi request đang xử lý và cách retry sau timeout. Không sinh key mới khi gặp lỗi mạng.

### 6.2. Nếu cần gửi event ra broker: Transactional Outbox

Thay vì gọi broker trực tiếp trong `ItemWriter`, writer ghi dữ liệu nghiệp vụ cùng một hàng outbox có `event_id` duy nhất trong transaction database. Một tiến trình riêng gửi message từ outbox và đánh dấu trạng thái phát:

~~~mermaid
flowchart LR
    R["Chunk writer"] --> TX["DB transaction:<br/>business state + outbox"]
    TX --> O[("Outbox")]
    O --> P["Publisher<br/>retry khi lỗi"]
    P --> Q["Broker / API"]
    Q --> I["Consumer: inbox / unique event_id<br/>chống xử lý trùng"]
~~~

Outbox giúp tránh mất sự kiện giữa việc cập nhật database và việc gửi message, **nhưng publisher vẫn có thể gửi lại** khi broker đã nhận mà response/ack bị mất. Consumer nên có inbox/dedupe theo event ID hoặc xử lý nghiệp vụ idempotent. Đây là thiết kế **at-least-once delivery với xử lý trùng có kiểm soát**, không phải cam kết “exactly once” cho mọi hệ thống liên quan.

## 7. Thread safety và partitioning: hai trục thiết kế độc lập

Một writer có thể idempotent nhưng **không thread-safe**; ngược lại, một writer hoàn toàn thread-safe vẫn có thể ghi trùng hợp lệ về mặt đồng thời.

- **Thread safety:** Hai lời gọi `write()` đồng thời có làm hỏng bộ đệm, danh sách trạng thái hay kết nối đang chia sẻ của đối tượng writer không?
- **Idempotency:** Hai lời gọi xử lý **cùng business event** có tạo thêm hiệu ứng nghiệp vụ hay không?

Ví dụ, một custom writer lưu `lastWrittenId` vào field chung không đồng bộ có thể bị race dù database đã có unique key. Với writer dùng JDBC, nên tránh giữ mutable per-chunk state trên singleton; dùng biến cục bộ trong `write()` và giao giới hạn concurrent update cho transaction/unique constraint ở database. Khi chạy partitioning, mỗi partition có `StepExecution` riêng nhưng **tất cả partition ghi cùng đích vẫn cần quy tắc dedupe chung**.

| Mô hình scale | Nguy cơ ghi lặp | Biện pháp nên ưu tiên |
| --- | --- | --- |
| Multi-threaded step | Retry chunk; processor/writer dùng shared state | Writer an toàn luồng, unique key, transaction, kiểm thử cạnh tranh |
| Parallel steps | Hai step cùng nhắm một business key | Ownership rõ ràng hoặc dedupe ở đích |
| Local partitioning | Range/file giao thoa; retry partition | Chia nguồn không chồng lấn, key bền vững, checkpoint từng partition |
| Remote partitioning/chunking | Message hoặc chunk được gửi/nhận lại | Stable message/event ID, durable dedupe ở đích, idempotent side effect |

Không nên dựa vào một cơ chế khóa in-memory trên writer để chặn duplicate khi job chạy ở nhiều JVM: khóa đó chỉ bảo vệ một tiến trình. Một unique constraint hoặc bảng dedupe dùng chung bền vững mới giải quyết bài toán cạnh tranh giữa nhiều worker.

## 8. Retry/restart: những điểm cần thiết kế và vận hành

Idempotent writer giúp thao tác ghi có thể lặp an toàn; nó **không thay thế** checkpoint reader, phân chia partition chính xác hay xử lý lỗi phù hợp.

1. **Xác định phạm vi replay:** Chunk nào có thể bị gọi lại khi rollback? Job chạy lại với `JobParameters` mới có dùng lại cùng ID của event nguồn không? Bản ghi nào có thể đến lại sau nhiều ngày?
2. **Kiểm soát transaction:** Đảm bảo bảng đích và ledger/dedupe cập nhật cùng transaction khi cần tính atomic. Với side effect ngoài DB, dùng key phía nhận hoặc outbox/inbox.
3. **Chọn chính sách conflict:** Duplicate giống hệt có thể no-op; duplicate khác payload cần ghi nhận là lỗi dữ liệu hoặc cập nhật có version. Đừng nuốt mọi lỗi unique constraint như “thành công”.
4. **Quản lý thời hạn dedupe:** Nếu xóa key cũ quá sớm hoặc API chỉ giữ key trong thời gian ngắn, một event phát lại muộn vẫn có thể tác động lần hai.
5. **Giới hạn tài nguyên:** Dedupe index, batch SQL, connection pool, lock contention và throughput cần được đo dưới số lượng worker thực tế.
6. **Phân biệt status Batch với trạng thái nghiệp vụ:** `COMPLETED` của Job/Step không tự chứng minh đã gửi đúng một email, charge đúng một lần hoặc insert đúng số lượng hàng đích.

### Metric cần theo dõi

Ghi nhận tổng item được đưa vào writer, số **insert mới**, số **duplicate hợp lệ**, số **conflict nội dung**, số retry/rollback, exception, độ trễ ghi, độ dài queue và contention của database. Với `ON CONFLICT DO NOTHING`, `writeCount` của Spring Batch **không nhất thiết bằng số hàng mới**: một item có thể được tính đã xử lý dù SQL no-op. Muốn đo số hàng được chèn thực sự, dùng update count phù hợp với JDBC driver hoặc phép đối soát bằng dữ liệu đích.

Theo dõi tốc độ ghi nên đi đôi với tính đúng đắn. Tăng thread có thể làm tăng số lần tranh chấp unique index và giảm throughput; phải đo batch size, kích thước connection pool, lock wait và CPU/I/O thay vì tăng concurrency không giới hạn.

## 9. Kịch bản kiểm thử bắt buộc trước khi tăng tải

Giả sử nguồn chứa 100.000 event duy nhất và 5.000 bản sao được phát lại. Dùng tập dữ liệu cố định, tạo key theo upstream và chạy các kịch bản:

| Kịch bản | Thao tác thử | Điều cần xác nhận |
| --- | --- | --- |
| Replay trực tiếp | Chạy writer hai lần với cùng chunk | Mỗi event hợp lệ chỉ có một hiệu ứng nghiệp vụ |
| Replay sau job restart | Dừng job ở giữa, chạy lại cùng input | Không mất và không nhân đôi dữ liệu đã commit |
| Cạnh tranh đồng thời | Hai thread/partition cùng ghi event ID | Unique key chỉ cho một hàng được chèn/áp dụng |
| Lỗi trước commit | Gây exception sau khi chèn ledger, trước khi cập nhật trạng thái chính | Transaction rollback toàn bộ; retry có thể áp dụng lại |
| Lỗi sau HTTP thành công | Timeout/mất ack rồi gửi lại cùng idempotency key | Phía nhận không nhân đôi tác dụng phụ |
| Trùng key nhưng payload khác | Hai event có ID giống nhưng amount khác | Báo conflict đúng quy tắc, không âm thầm bỏ qua |
| Replay muộn | Phát lại event sau thời gian lưu dedupe dự kiến | Chính sách retention đáp ứng thời gian replay thực tế |

**Đối soát theo khóa nghiệp vụ**, không chỉ nhìn exception hoặc `writeCount`:

~~~sql
-- Ví dụ cho bảng ingested_order_events
SELECT COUNT(*) AS stored_events
FROM ingested_order_events;

-- Cặp source_system/event_id đã có PRIMARY KEY:
-- câu truy vấn này phải trả về 0 hàng.
SELECT source_system, event_id, COUNT(*)
FROM ingested_order_events
GROUP BY source_system, event_id
HAVING COUNT(*) > 1;
~~~

Trong kịch bản import event không filter/skip nghiệp vụ, kỳ vọng có **100.000 hàng duy nhất**, dù nguồn chuyển vào 105.000 lần. Với bài toán số dư, kiểm tra thêm số dư cuối, tổng giao dịch đã áp dụng, journal/audit và quy tắc bất biến của nghiệp vụ. Cần chủ động gây lỗi ở nhiều ranh giới transaction; kiểm thử “chạy thành công một lần” không chứng minh được idempotency.

## 10. Checklist lựa chọn cho hệ thống thực tế

Trước khi tăng số thread hoặc chuyển sang partitioning/remote processing, trả lời các câu hỏi:

- Cùng một item được nhận diện bằng **key nào**, và key có tồn tại ổn định qua retry, restart, re-run, nhiều JVM không?
- Hai item trùng key nhưng **payload khác nhau** có được coi là lỗi hay phiên bản mới?
- DB có unique constraint/ledger **atomic** để chặn cạnh tranh giữa nhiều worker không?
- Thay đổi trạng thái chính và ghi ledger có **cùng transaction** không?
- Writer có side effect ngoài database cần idempotency key tại đích hoặc outbox/inbox không?
- Khi replay, output có giữ nguyên các bất biến nghiệp vụ, bất kể thứ tự chunk/partition hoàn tất không?
- Metric có phân biệt **items nhận**, **items mới thực sự ghi** và **duplicate/conflict** không?

### Câu hỏi tự kiểm tra

Một job xử lý thanh toán theo các chunk 200 item. Writer hiện gọi API charge với UUID mới tạo trong `write()`. Sau timeout, step retry và khách hàng bị charge hai lần. Có thể giải quyết hoàn toàn vấn đề bằng cách tăng `retryLimit`, đánh dấu `@StepScope` cho writer, hoặc `synchronized` phương thức `write()` không?

**Định hướng trả lời:** Không. Retry nhiều lần tăng khả năng lặp hiệu ứng; `@StepScope` và khóa trong process không chống trùng qua restart hoặc nhiều worker. Cần một business request ID ổn định dùng làm idempotency key, phía API bảo đảm dedupe theo key, xử lý payload conflict và quy định retention. Nếu thao tác charge nối tiếp một giao dịch database, cần thiết kế transaction boundary/outbox hoặc cơ chế trạng thái nhất quán tương ứng.

## Tài liệu tham khảo

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): cơ chế đọc, xử lý, ghi và commit theo chunk.
- [Spring Batch API — JdbcBatchItemWriter](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/item/database/JdbcBatchItemWriter.html): writer JDBC và ý nghĩa cấu hình cập nhật.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps và partitioning.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): cú pháp và semantics xử lý conflict trong PostgreSQL.

> **Ghi nhớ:** Thiết kế `ItemWriter` idempotent dựa trên **khóa nghiệp vụ ổn định, ràng buộc ghi atomic tại đích và kiểm soát mọi side effect**. Retry/restart chỉ an toàn khi hệ thống biết nhận diện cùng một yêu cầu và thực thi lại mà không nhân đôi kết quả nghiệp vụ.
