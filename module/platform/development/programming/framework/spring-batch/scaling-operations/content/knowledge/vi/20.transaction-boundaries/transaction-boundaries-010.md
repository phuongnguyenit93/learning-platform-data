# Outbox khi cần phát message bền vững trong Spring Batch

## Mục tiêu bài học

Giả sử một Spring Batch job chuẩn hóa 20 triệu đơn hàng. Mỗi khi ghi thành công trạng thái đơn hàng vào database, hệ thống phải phát sự kiện `order.normalized.v1` để dịch vụ tìm kiếm, kho dữ liệu hoặc hệ thống downstream nhận biết thay đổi. Nếu writer **commit database rồi mới gửi message**, worker có thể chết đúng giữa hai thao tác và message mất vĩnh viễn. Nếu **gửi message trước khi commit**, consumer có thể nhận sự kiện về một thay đổi mà database sau đó rollback.

**Transactional Outbox** giải quyết bài toán này bằng cách ghi **business change và event cần phát vào cùng một transaction database**, rồi dùng một publisher riêng đọc outbox và chuyển event ra broker. Cách này bảo đảm rằng event intent được lưu bền vững cùng business state, nhưng **không tự bảo đảm broker chỉ nhận event đúng một lần**. Publisher có thể gửi lại nếu ACK thất lạc, vì vậy consumer thường phải idempotent.

Bài **“Outbox khi cần phát message bền vững”** thuộc chương **Transaction boundary**, module **SPRING_BATCH_SCALING_OPERATIONS**. Module tìm hiểu mở rộng Spring Batch qua multi-threaded step, parallel steps, partitioning và xử lý phân tán, đồng thời đo nút thắt, bảo đảm thread safety, retry/restart và vận hành job với tài nguyên thực tế. Outbox là một ranh giới quan trọng khi một chunk vừa thay đổi database vừa cần thông báo đáng tin cho các hệ thống khác.

Sau bài học, bạn có thể:

- Giải thích lỗi **dual write** và lý do một transaction JDBC không tự bao trùm message broker.
- Vẽ luồng business write → outbox insert → commit → publisher → broker → consumer.
- Thiết kế bảng PostgreSQL outbox có event ID, business version, payload, trạng thái và retry metadata.
- Dùng Spring Batch 5.x để ghi business state và outbox atomically bằng cùng DataSource/transaction manager.
- Chọn publisher polling hoặc Change Data Capture (CDC), hiểu giới hạn của từng phương án.
- Dùng `FOR UPDATE SKIP LOCKED`, lease và fencing token khi nhiều publisher cùng chạy.
- Phân biệt broker ACK, database commit, delivery at-least-once và business idempotency.
- Bảo toàn thứ tự theo aggregate khi nghiệp vụ yêu cầu.
- Thiết kế inbox/dedup, retry, DLQ/quarantine, restart, backpressure, cleanup và observability.
- Kiểm thử các cửa sổ crash quan trọng và đánh giá throughput hữu ích thay vì số lần gửi.

## 1. Vấn đề dual write: hai hệ thống, hai lần commit

Một writer naïve thường làm:

~~~java
saveOrderToDatabase(order);
kafkaTemplate.send("order-events", order.id(), event);
~~~

Nhìn có vẻ hợp lý, nhưng có ít nhất hai nơi lưu trạng thái: **database** và **broker**. Hai nơi không mặc nhiên cùng một transaction.

| Thứ tự | Cửa sổ lỗi | Hậu quả |
| --- | --- | --- |
| DB commit → publish | Worker chết sau commit, trước publish | DB có dữ liệu, consumer không bao giờ biết |
| Publish → DB commit | DB rollback sau khi broker đã nhận | Consumer thấy event cho thay đổi chưa tồn tại |
| Publish trong DB transaction | Broker nhận rồi DB transaction rollback | Broker không tự rollback cùng JDBC |
| DB commit → publish → ghi “đã gửi” | Broker nhận, worker chết trước ghi trạng thái | Publisher sau restart có thể gửi trùng |
| Gửi lại khi timeout | Broker đã nhận nhưng ACK bị mất | Có thể phát trùng một event |

Lỗi không chỉ đến từ JVM crash. DB failover, broker partition, process kill, network timeout, pod eviction và rolling deploy đều có thể xảy ra giữa hai thao tác.

### Vì sao bọc bằng `@Transactional` chưa đủ?

Spring `@Transactional` với `DataSourceTransactionManager` hoặc `JdbcTransactionManager` thường điều phối **database transaction** được cấu hình. Nó không tự biến broker publish thành một phần của cùng một atomic commit. Nếu cần transaction phân tán thực sự, phải có giao thức/coordinator và các resource managers hỗ trợ; không được suy điều đó từ annotation.

Với đa số batch event-driven, Outbox là giải pháp thực dụng để không cần một transaction XA xuyên database–broker, đổi lại chấp nhận **eventual publication** và xử lý duplicate.

## 2. Ba bất biến của Transactional Outbox

Thiết kế phải bảo vệ ít nhất ba bất biến:

**Bất biến A — Atomic intent:** nếu business change commit, một event intent phù hợp được lưu trong outbox **cùng commit**; nếu transaction rollback, cả hai cùng rollback.

**Bất biến B — Durable retry:** sau business commit, publisher có thể dừng/restart mà event chưa gửi vẫn còn trong storage để thử lại.

**Bất biến C — Duplicate-safe downstream:** nếu cùng event được gửi lại, consumer không áp dụng business side effect hai lần.

Bất biến A phụ thuộc **cùng database transaction thực**; B phụ thuộc lưu trữ bền, polling/CDC và retention policy; C phụ thuộc business ID, uniqueness, inbox/idempotency và transaction tại consumer.

**Outbox không mặc nhiên bảo đảm:**

- Broker delivery đúng một lần trong mọi failure window.
- Độ trễ phát event bằng 0.
- Thứ tự toàn cục giữa mọi aggregate hoặc mọi partition.
- Hai database khác nhau tự commit atomically.
- Consumer side effect HTTP hoặc email tự tham gia transaction DB.
- Không mất dữ liệu nếu operator xóa nhầm outbox row trước khi publish.

## 3. Kiến trúc end-to-end

~~~mermaid
flowchart LR
    IN[["Input của Spring Batch"]] --> S["Chunk Step"]
    S --> TX[["Một business DB transaction"]]
    TX --> B[("Business tables")]
    TX --> O[("Outbox events")]
    O --> PUB["Outbox Publisher / CDC"]
    PUB --> MQ[["Kafka / RabbitMQ"]]
    MQ --> C["Consumer service"]
    C --> I[("Inbox / Consumer DB")]
    C --> DOWN["Business side effect"]
~~~

Điểm cốt lõi là hai nhánh từ `TX` đến `B` và `O` cùng thuộc **một transaction database**. Nhánh `O → PUB → MQ` diễn ra **sau commit**, có retry độc lập với StepExecution ban đầu.

### Vì sao publisher tách khỏi writer?

Nếu Spring Batch writer gọi network publish trong transaction, transaction phải chờ broker. Điều đó vừa tăng thời gian giữ DB connection/row locks, vừa không làm network operation trở thành atomic với DB.

Tách publisher giúp:

- Chunk transaction ngắn hơn.
- Worker job hoàn thành độc lập với broker outage ngắn.
- Broker failure không bắt toàn bộ business data rollback sau khi đã commit.
- Publisher tự scale/retry theo backlog.
- Event bền vững có thể được đối soát và phát lại có kiểm soát.

Đổi lại, hệ thống phải quản lý **outbox backlog, thứ tự, duplication, cleanup và trạng thái “business committed nhưng event chưa phát”**.

## 4. Phân biệt transaction của Step, JobRepository và publisher

Trong Spring Batch có thể tồn tại nhiều transaction boundaries:

| Boundary | Phạm vi | Điều cần xác minh |
| --- | --- | --- |
| **Chunk transaction** | Reader/processor/writer theo Step configuration | Business write và outbox insert có thực sự cùng resource manager? |
| **JobRepository metadata** | StepExecution, read/write counts, ExecutionContext checkpoint | Có cùng DB/transaction hay một DataSource khác? |
| **Publisher claim transaction** | Claim outbox rows để gửi | Kết thúc trước network send |
| **Publisher publish operation** | Broker client và ACK/confirm | Không mặc định atomic với outbox state |
| **Publisher mark-SENT transaction** | Ghi kết quả phát ở DB | ACK có thể đến trước transaction này |
| **Consumer transaction** | Inbox/dedup và downstream DB write | Có cùng DB transaction không? |

Nếu JobRepository nằm ở database A còn business tables và outbox ở database B, việc Step metadata update và business write **không mặc nhiên có một atomic transaction xuyên hai DB**. Cơ chế restart/idempotency phải chịu được metadata checkpoint chưa phản ánh business commit hoặc ngược lại, tùy cấu hình.

**Transaction boundary đúng cho Outbox:** business update và insert outbox phải dùng **cùng DataSource connection/transaction manager** hoặc một cơ chế transaction phân tán thực sự được chứng minh. Một annotation `@Transactional` trên service không đủ nếu hai repository dùng transaction managers khác nhau.

## 5. Khi nào Outbox là lựa chọn phù hợp?

**Nên cân nhắc Outbox khi:**

- Business state **phải được lưu** ngay cả khi broker tạm ngừng hoạt động.
- Mỗi commit hợp lệ phải tạo một event có thể phát về sau.
- Event có downstream quan trọng: search index, accounting ledger, analytics pipeline, integration service.
- Hệ thống cần retry publication sau worker crash/pod eviction.
- Có thể chấp nhận event được phát **sau commit một khoảng thời gian**.
- Consumer có thể thực hiện idempotency/dedup.

**Không phải mọi sự kiện đều cần Outbox:**

- Progress/debug metric có thể mất một vài điểm đo mà không vi phạm nghiệp vụ.
- Log có thể xuất qua hệ logging tập trung, không cần business outbox.
- Notification best-effort được tuyên bố rõ có thể chọn cơ chế khác.
- Nếu application chỉ lưu trạng thái vào một transactional broker hoặc chỉ vào một DB, vấn đề dual write có thể không tồn tại theo cùng cách.

**Câu hỏi quyết định:** nếu worker commit DB thành công nhưng không phát message, business correctness có bị vi phạm? Nếu có, outbox là ứng viên mạnh.

## 6. Mô hình dữ liệu PostgreSQL

Ví dụ dùng **PostgreSQL**; production cần điều chỉnh index, partitioning, retention và quyền truy cập. Bảng business:

~~~sql
CREATE TABLE order_projection (
    order_id BIGINT PRIMARY KEY,
    source_version BIGINT NOT NULL,
    normalized_status TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_version >= 0)
);
~~~

Bảng outbox:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CLAIMED', 'SENT', 'DEAD')),
    attempts INTEGER NOT NULL DEFAULT 0
        CHECK (attempts >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    leased_by TEXT,
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (aggregate_type, aggregate_id,
            aggregate_version, event_type)
);
~~~

Index gợi ý cho polling:

~~~sql
CREATE INDEX idx_outbox_pending_schedule
    ON outbox_event (next_attempt_at, created_at, event_id)
    WHERE status = 'PENDING';

CREATE INDEX idx_outbox_claimed_lease
    ON outbox_event (lease_until, event_id)
    WHERE status = 'CLAIMED';

CREATE INDEX idx_outbox_aggregate_order
    ON outbox_event (aggregate_type, aggregate_id,
                     aggregate_version);
~~~

### Ý nghĩa các cột

| Cột | Mục đích |
| --- | --- |
| `event_id` | Identity bền vững của một logical event; không đổi giữa retry |
| `aggregate_type/id` | Loại và khóa của business entity |
| `aggregate_version` | Phiên bản business state để kiểm soát ordering/stale event |
| `event_type` | Tên event có version theo schema contract |
| `payload` | Nội dung event cần phát, được lưu cùng transaction |
| `status` | PENDING/CLAIMED/SENT/DEAD cho polling |
| `attempts` | Số lượt publisher claim/thử theo policy |
| `next_attempt_at` | Mốc đủ điều kiện retry |
| `leased_by/lease_token/lease_until` | Quyền claim tạm thời khi nhiều publisher |
| `published_at` | Lúc application ghi nhận broker ACK/confirm |
| `created_at` | Thời gian enqueue phục vụ backlog và latency |

**Lưu ý:** unique key (aggregate,version,type) ngụ ý **tối đa một event của loại đó tại mỗi phiên bản**. Nếu business contract cho phép nhiều event khác nhau cùng type/version, phải thay ràng buộc bằng business event ID/version/subsequence phù hợp.

### Schema không thay thế domain contract

Không để payload tùy ý mà không có version/schema. Nếu một event lưu JSON nhưng consumer không biết cách parse sau deploy, publisher có thể gửi bền vững nhưng pipeline vẫn lỗi. Cần contract backward compatibility và DLQ/quarantine.

## 7. Ghi business state và outbox trong **một SQL transaction**

Một mẫu PostgreSQL hữu ích là dùng data-modifying CTE: chỉ tạo outbox event khi state thực sự được insert hoặc nâng version.

~~~sql
WITH changed AS (
    INSERT INTO order_projection (
        order_id, source_version, normalized_status
    )
    VALUES (
        :orderId, :sourceVersion, :normalizedStatus
    )
    ON CONFLICT (order_id)
    DO UPDATE SET
        source_version = EXCLUDED.source_version,
        normalized_status = EXCLUDED.normalized_status,
        updated_at = now()
    WHERE order_projection.source_version
          < EXCLUDED.source_version
    RETURNING order_id, source_version, normalized_status
)
INSERT INTO outbox_event (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    payload
)
SELECT
    :eventId,
    'order',
    c.order_id,
    c.source_version,
    'order.normalized.v1',
    jsonb_build_object(
        'orderId', c.order_id,
        'sourceVersion', c.source_version,
        'normalizedStatus', c.normalized_status
    )
FROM changed AS c;
~~~

Câu SQL này **phải chạy trong cùng transaction** với các thao tác business liên quan của chunk. Nếu `changed` không trả row vì source version đã xử lý hoặc mới hơn, không có outbox event mới được insert.

**Vì sao đây là cơ chế atomic?**

- CTE thay đổi `order_projection` và `INSERT outbox_event` cùng một SQL statement.
- Nếu insert outbox gặp unique violation hoặc DB error, statement/transaction rollback theo DB semantics, tránh commit business state thiếu event.
- Khi chunk transaction commit thành công, state và event intent cùng bền vững.

### Giới hạn business semantics

- Đây là **snapshot theo source_version**, không phải event delta bắt buộc cộng mọi bước.
- Nếu cùng `sourceVersion` nhưng payload khác nhau, predicate sẽ không ghi bản sau; phải có **conflict detection** nếu nghiệp vụ coi đó là lỗi.
- `eventId` phải **ổn định theo business operation** qua retry/restart. Không gọi `UUID.randomUUID()` trong mỗi lần writer được retry.
- Nếu một event đã tồn tại vì duplicate eventId nhưng business update khác chưa commit, unique constraint có thể khiến transaction fail; đó là tín hiệu cần điều tra, không nên `ON CONFLICT DO NOTHING` tùy tiện để giấu mất event.
- Ví dụ chưa xử lý record deletion hoặc nhiều event types trên cùng version; cần mở rộng contract nếu nghiệp vụ yêu cầu.

## 8. Spring Batch 5.x: ItemWriter dùng chung transaction

Ví dụ Java 17, Spring Batch 5.x và Spring JDBC. `OrderNormalization` là dữ liệu **đã chuẩn hóa**, có event ID ổn định từ nguồn/công đoạn trước.

~~~java
import java.util.UUID;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

record OrderNormalization(
        long orderId,
        long sourceVersion,
        String normalizedStatus,
        UUID eventId) {}

public final class OrderProjectionOutboxWriter
        implements ItemWriter<OrderNormalization> {

    private static final String SQL = """
        WITH changed AS (
            INSERT INTO order_projection (
                order_id, source_version, normalized_status
            )
            VALUES (:orderId, :sourceVersion, :normalizedStatus)
            ON CONFLICT (order_id)
            DO UPDATE SET
                source_version = EXCLUDED.source_version,
                normalized_status = EXCLUDED.normalized_status,
                updated_at = now()
            WHERE order_projection.source_version
                  < EXCLUDED.source_version
            RETURNING order_id, source_version, normalized_status
        )
        INSERT INTO outbox_event (
            event_id, aggregate_type, aggregate_id,
            aggregate_version, event_type, payload
        )
        SELECT
            :eventId, 'order', c.order_id, c.source_version,
            'order.normalized.v1',
            jsonb_build_object(
                'orderId', c.order_id,
                'sourceVersion', c.source_version,
                'normalizedStatus', c.normalized_status
            )
        FROM changed c
        """;

    private final NamedParameterJdbcTemplate jdbc;

    public OrderProjectionOutboxWriter(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void write(
            Chunk<? extends OrderNormalization> chunk) {

        for (OrderNormalization order : chunk.getItems()) {
            MapSqlParameterSource parameters =
                    new MapSqlParameterSource()
                    .addValue("orderId", order.orderId())
                    .addValue("sourceVersion",
                            order.sourceVersion())
                    .addValue("normalizedStatus",
                            order.normalizedStatus())
                    .addValue("eventId", order.eventId());

            jdbc.update(SQL, parameters);
        }
    }
}
~~~

### Vì sao writer không tự mở transaction?

Trong chunk-oriented step, `PlatformTransactionManager` được truyền vào `StepBuilder.chunk` để framework tạo transaction cho mỗi chunk. Với `NamedParameterJdbcTemplate` dùng đúng **DataSource đã được transaction manager quản lý**, các câu SQL writer tham gia transaction-bound connection.

**Sai lầm nguy hiểm:** gắn `REQUIRES_NEW` cho phần insert outbox hoặc dùng DataSource khác với phần ghi business state. Khi đó có thể xảy ra business rollback nhưng outbox commit, hoặc ngược lại.

### Điều cần kiểm chứng ở dự án thật

- Step đang dùng đúng `JdbcTransactionManager`/`DataSourceTransactionManager` cho business DB.
- `NamedParameterJdbcTemplate` thực sự trỏ cùng DataSource.
- Writer không mở connection riêng bằng `DriverManager.getConnection` ngoài transaction.
- Các stored procedures/triggers không có side effect ngoài transaction DB.
- Event ID không đổi nếu reader restart và item được replay.
- Nếu một chunk chứa nhiều bản ghi cùng aggregate, business version/order được xử lý có quy tắc rõ.
- Logging và metrics không tuyên bố message đã publish ngay sau khi outbox row insert.

**Giới hạn hiệu năng:** ví dụ gọi một statement mỗi item để dễ hiểu. Với throughput lớn, cân nhắc JDBC batch, multi-row SQL hoặc staging/merge; nhưng atomicity, uniqueness, ordering và transaction boundary vẫn phải được test.

## 9. Cấu hình chunk Step và TransactionManager

Ví dụ một worker step Spring Batch 5.x với transaction manager dành cho business DB:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step normalizeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTransactionManager,
        ItemReader<OrderNormalization> reader,
        ItemWriter<OrderNormalization> writer) {

    return new StepBuilder(
            "normalizeOrdersStep", jobRepository)
            .<OrderNormalization, OrderNormalization>chunk(
                    250, businessTransactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Các bean JobRepository, reader, writer, transaction manager và DataSource phải được định nghĩa trong ứng dụng. Đây là ví dụ **không phải dự án chạy độc lập**.

### Chính sách restart

Một chunk có thể được xử lý lại sau transaction rollback hoặc crash. Nếu CTE đã commit trước khi Step metadata cập nhật ở resource khác, replay cùng sourceVersion sẽ không tạo business update/event mới. Điều đó giúp chống duplicate ở mức state projection, nhưng phải kiểm tra **mọi side effect khác** trong writer/processor.

Không tự cho rằng `@StepScope` bảo đảm transaction atomicity hoặc thread safety. `@StepScope` là phạm vi StepExecution; với multi-threaded chunk, bean scoped có thể vẫn bị nhiều chunk threads cùng truy cập.

## 10. Idempotency key và event identity qua retry/restart

Một lỗi phổ biến:

~~~java
public void write(Order order) {
    UUID eventId = UUID.randomUUID();
    insertBusinessAndOutbox(order, eventId);
}
~~~

Khi writer được gọi lại sau timeout/restart, event ID thay đổi. Unique constraint theo event_id **không còn nhận ra** cùng một logical event.

### Chọn ID thế nào?

- Dùng business event ID ổn định từ upstream nếu nguồn cấp.
- Hoặc tính ID deterministic từ business identity, source version, event type và một namespace được định nghĩa.
- Không đưa JobExecutionId/StepExecutionId vào ID nếu mục tiêu dedup **xuyên restart**.
- Không dùng Kafka message ID do transport tạo mới làm business key mặc định.
- Với event delta, identity phải thể hiện **từng thao tác**, không chỉ aggregate ID; hai delta hợp lệ trên cùng aggregate phải có ID khác.

Ví dụ logical identity:

~~~text
businessEventId = upstream_event_uuid_42
aggregateType = order
aggregateId = 9000123
sourceVersion = 17
eventType = order.normalized.v1
~~~

**Quan trọng:** nếu payload khác nhau nhưng cùng businessEventId/version, phải phát hiện schema/data conflict. Không được chỉ “ON CONFLICT DO NOTHING” rồi âm thầm chấp nhận hai sự kiện khác nhau như một.

## 11. Retry của chunk khác retry của publisher

Cần tách hai workflow:

~~~mermaid
flowchart TD
    B["Spring Batch chunk"] --> X{"Business + outbox transaction"}
    X -->|Commit| COM["Outbox PENDING bền vững"]
    X -->|Rollback| RET["Chunk retry / fail"]
    COM --> PUB["Publisher độc lập"]
    PUB --> A{"Broker ACK/confirm?"}
    A -->|Có| SENT["Mark SENT trong DB"]
    A -->|Không/UNKNOWN| LATER["Retry theo policy"]
    LATER --> PUB
~~~

**Chunk retry** xảy ra trước business commit hoặc sau một lỗi mà transaction manager/JobRepository có thể nhận biết. **Publisher retry** xảy ra sau khi outbox row đã commit, có thể kéo dài sau khi JobExecution ban đầu đã `COMPLETED`.

### Những sai lầm cần tránh

- Bắt publisher lỗi rồi rollback business change đã commit: không thể rollback commit cũ như vậy.
- Khi publisher mất ACK thì sửa business state một lần nữa: không cần, chỉ retry publication.
- Khi business step rollback mà vẫn có event từ một `REQUIRES_NEW` outbox insert: đã phá atomicity.
- Coi `JobExecution COMPLETED` nghĩa mọi outbox event đã được broker nhận: **không đúng** nếu publication async.
- Coi `outbox status SENT` là consumer đã xử lý thành công: thường chỉ là producer đã nhận broker ACK/confirm.

## 12. Publisher polling và CDC: hai họ giải pháp

| Cách | Hoạt động | Ưu điểm | Rủi ro/chi phí |
| --- | --- | --- | --- |
| **Polling publisher** | Query/claim rows PENDING rồi gửi | Dễ kiểm soát retry, batching, rate limit | Polling load, lease/reclaim, ordering |
| **CDC / log tailing** | Theo dõi committed changes trong DB WAL/binlog | Không cần scan PENDING liên tục; có thể giữ thứ tự DB log | Connector, WAL retention, snapshot/schema evolution |
| **Application dual write trực tiếp** | Writer gọi DB và broker riêng | Đơn giản ban đầu | **Không có atomic intent** nếu không có transaction phân tán |
| **XA/2PC** | Phối hợp resource managers | Có thể atomic theo protocol tương ứng | Support/coordination/availability/complexity |

Một hệ thống có thể dùng polling publisher ở giai đoạn đầu, chuyển sang CDC khi volume tăng. Khi chuyển, phải xây kế hoạch cutover để không có **hai publisher cùng phát một event không kiểm soát**, đồng thời không bỏ sót khoảng chuyển tiếp.

### Polling vẫn là eventual consistency

Publisher có thể cần vài giây sau commit mới publish. Nếu SLA yêu cầu event tới consumer trong 100 ms, phải benchmark p95/p99 publication lag; thêm index và batch có thể chưa đủ nếu DB I/O, broker hoặc consumer đã bão hòa.

## 13. Polling: claim outbox rows với SKIP LOCKED

Khi có nhiều publisher workers, không nên để tất cả đọc cùng PENDING rows rồi cùng gửi.

Một mẫu PostgreSQL **claim trong transaction ngắn**:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_event
    WHERE (
        status = 'PENDING'
        AND next_attempt_at <= now()
    ) OR (
        status = 'CLAIMED'
        AND lease_until < now()
    )
    ORDER BY created_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT :batchSize
)
UPDATE outbox_event AS o
SET status = 'CLAIMED',
    leased_by = :publisherId,
    lease_token = :leaseToken,
    lease_until = now()
        + (:leaseSeconds * INTERVAL '1 second'),
    attempts = attempts + 1
FROM candidates AS c
WHERE o.event_id = c.event_id
RETURNING
    o.event_id, o.aggregate_id, o.aggregate_version,
    o.event_type, o.payload, o.lease_token, o.attempts;
~~~

### Cách dùng đúng

1. Mở một DB transaction cho **claim**.
2. Chạy query claim ở trên.
3. **Commit transaction claim ngay**, nhả row locks.
4. Gửi message đến broker **ngoài transaction claim**.
5. Khi có broker ACK/confirm được xác thực, đánh dấu SENT bằng một transaction ngắn khác.
6. Khi gửi lỗi, đặt lịch retry và nhả lease theo policy.

`FOR UPDATE SKIP LOCKED` hữu ích cho **work queue claim**: các publisher khác có thể bỏ qua rows đang bị khóa để chọn rows chưa claim. Nó không bảo đảm thứ tự phát tuyệt đối hay fairness.

**Không giữ transaction với row locks trong khi gọi Kafka/RabbitMQ**. Gửi network có thể block nhiều giây, gây DB contention và làm mục đích tách publisher thất bại.

### Giới hạn của ví dụ

- `:leaseToken` phải được tạo mới theo **mỗi lần claim/batch claim**, đủ phân biệt worker cũ và worker mới.
- Không chọn quá nhiều rows để lease hết hạn trước khi xử lý.
- `lease_until < now()` là điều kiện reclaim; producer cũ có thể vẫn đang gửi nếu chậm/hung.
- Từng event cần có max attempts, dead-letter/quarantine policy và thời gian retry.
- Với yêu cầu ordering per aggregate, query claim chung như trên **chưa đủ**; xem phần sau.

## 14. Lease, fencing và zombie publisher

Một publisher có thể nhận batch 100 events, rồi bị GC pause/network timeout dài hơn lease. Publisher mới reclaim event E42; sau đó publisher cũ tỉnh lại và cũng gửi E42.

~~~text
T0  Publisher A claim E42, token=A1, lease đến 10:00:30
T1  A bị pause trước hoặc trong publish
T2  Lease hết hạn
T3  Publisher B claim E42, token=B9
T4  B gửi E42
T5  A hồi phục và cũng gửi E42
~~~

**Lease không đảm bảo “chỉ gửi một lần”.** Nó giúp điều phối và thu hồi work, nhưng network side effect đã xảy ra không thể bị DB thu hồi chỉ bằng đổi token.

### Fencing token bảo vệ trạng thái DB

Khi đánh dấu SENT:

~~~sql
UPDATE outbox_event
SET status = 'SENT',
    published_at = now(),
    leased_by = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE event_id = :eventId
  AND status = 'CLAIMED'
  AND lease_token = :leaseToken;
~~~

Nếu Publisher A có token cũ, update trả **0 rows** sau khi B đã reclaim; A không được tự xóa/đổi trạng thái mới. Bảo vệ này là **fencing cho database update**, không ngăn A đã publish event ra broker. Vì thế consumer vẫn cần dedup.

### Nếu publish vượt lease

- Chọn lease dựa trên p99 publish+confirm time và batch size.
- Hoặc thực hiện heartbeat/extend lease **có fencing** nếu publisher còn active.
- Giới hạn inflight sends và concurrency.
- Khi update SENT trả 0, ghi metric/log và reconcile, không coi là success tuyệt đối.
- Không sử dụng đồng hồ riêng của mỗi JVM làm nguồn ordering của lease nếu có thể để DB time quản lý.

## 15. Broker ACK/confirm trước khi đánh dấu SENT

Một event ở trạng thái CLAIMED không được đánh dấu SENT **chỉ vì client đã gọi send() thành công ở local memory**. Cần chờ thông tin broker đã chấp nhận message theo semantics/ack level được cấu hình.

Với **Kafka**, cần hiểu producer send async/future, acknowledgment và `acks`/idempotent producer settings. Với **RabbitMQ**, dùng publisher confirms/returns/routing guarantees phù hợp topology. Broker accepted/ACK không đồng nghĩa consumer đã xử lý business effect.

Timeline:

~~~text
Publisher claim E42 → DB COMMIT claim
Publisher send E42 → Broker ACK/confirm
Publisher mark E42 SENT → DB COMMIT status
~~~

**Cửa sổ không thể xóa bằng polling alone:**

~~~text
Broker ACK thành công
    ↓
Publisher chết trước mark SENT
    ↓
Lease expire / retry
    ↓
Broker nhận E42 lần nữa
~~~

Đó là lý do delivery thường được mô tả **at-least-once** khi publication và retry được thiết kế đúng; không hứa **exactly-once broker delivery**.

### Broker ack có thể không đủ trong mọi cấu hình

- Kafka durability còn phụ thuộc replication/ISR/acks policy và broker vận hành.
- RabbitMQ publisher confirms báo broker xử lý publication theo contract; message có thể không được route tới queue mong muốn nếu routing sai và returns/mandatory policy không được kiểm tra.
- Broker retention/TTL hoặc compacted-topic policy có thể xóa message sau một thời gian; outbox không thay đổi retention downstream.
- Ack timeout thường tạo trạng thái **UNKNOWN**: không thể biết chắc broker có nhận không.

**Quy tắc:** nếu chưa có xác nhận đáng tin, không mark SENT; thử lại có thể tạo duplicate nên consumer idempotent là bắt buộc.

## 16. Publisher failure và retry scheduling

Một event có thể thất bại vì:

- Broker unavailable, DNS/TLS/permission lỗi.
- Invalid routing key/topic không tồn tại.
- Payload schema không được consumer/broker chấp nhận.
- Message vượt size limit.
- Throttling/quota.
- Worker crash sau claim.
- Publication succeeded nhưng ACK thất lạc.

Không nên retry cùng nhịp tức thì mọi lỗi.

Ví dụ cập nhật fail và lịch retry (trong transaction ngắn):

~~~sql
UPDATE outbox_event
SET status = CASE
        WHEN attempts >= :maxAttempts THEN 'DEAD'
        ELSE 'PENDING'
    END,
    next_attempt_at = :nextAttemptAt,
    leased_by = NULL,
    lease_token = NULL,
    lease_until = NULL
WHERE event_id = :eventId
  AND status = 'CLAIMED'
  AND lease_token = :leaseToken;
~~~

Sau lệnh này, Publisher phải kiểm tra affected rows; 0 rows có thể là lease đã bị reclaim, không nên ghi đè state của worker khác.

### Retry budget và poison event

| Loại lỗi | Gợi ý chính sách |
| --- | --- |
| Broker mất kết nối ngắn | Retry exponential backoff + jitter |
| Throttling | Tôn trọng quota và backoff |
| Message quá lớn/serialization không thể sửa | DEAD/quarantine với diagnostic |
| Topic/queue mapping sai | Cảnh báo triển khai, không retry nóng vô hạn |
| ACL/credential lỗi | Dừng publication hoặc BLOCKED cho publisher, sửa cấu hình |
| Broker ACK trạng thái UNKNOWN | Retry an toàn nếu consumer dedup |
| Row lease hết hạn | Reclaim có kiểm soát, không mất event |

`DEAD` ở đây nên được hiểu là **chưa phát thành công theo publisher policy, cần điều tra/replay**; không được xóa âm thầm. Việc replay cần giữ event identity, payload và audit trail.

### Jitter và đồng bộ retry

Nếu hàng nghìn publisher retries cùng timeout 2 giây, chúng có thể thức dậy đồng loạt. Backoff có jitter, giới hạn concurrency và circuit breaker giảm retry storm. Không bật 100 publisher threads chỉ vì backlog tăng khi broker đang down.

## 17. Chunk commit thành công nhưng publisher chưa chạy: trạng thái gì?

Một JobExecution Spring Batch có thể `COMPLETED` trong khi outbox vẫn còn hàng triệu rows PENDING.

Điều này **không nhất thiết là lỗi của job**, nếu contract được định nghĩa là: “job hoàn thành khi business state và event intent được commit; publication downstream là pipeline riêng”.

Tuy nhiên cần phân biệt hai SLA:

- **Business commit SLA:** thời gian các chunk ghi state/outbox đúng.
- **Event publication SLA:** khoảng từ `outbox.created_at` đến broker ACK hoặc consumer hoàn thành.

Nếu business contract yêu cầu **mọi event đã phát trước khi job được công bố hoàn thành**, có thể thêm một **barrier/wait step** sau writer để chờ outbox events thuộc **đúng business run/cutoff** đã SENT, với timeout và failure status rõ. Barrier này có thể biến broker outage thành job failure/timeout, nên phải chọn có chủ đích.

### Không chờ theo tổng outbox table vô hạn

Nếu liên tục có các jobs khác insert outbox, điều kiện “bảng outbox không còn row PENDING” có thể không bao giờ đạt. Cần một **runId/snapshot cutoff** để chỉ chờ events thuộc phạm vi job đang xét, hoặc một watermark rõ ràng.

## 18. Quản lý thứ tự event theo aggregate

Đối với cùng một order, có thể có events:

~~~text
order=9000123, version=17, status=PAID
order=9000123, version=18, status=SHIPPED
order=9000123, version=19, status=DELIVERED
~~~

Nếu publisher chạy song song, version 19 có thể được gửi trước version 18. Kafka partitioning theo order ID giúp các records được **lưu theo thứ tự producer append vào một partition**, nhưng **không tự sửa thứ tự publisher đã gửi sai**.

### Lựa chọn thiết kế

1. **Per-aggregate serialization:** chỉ cho một publisher xử lý các events của cùng aggregate theo version/sequence, rồi mới phát event kế tiếp.
2. **Keyed stream partitioning:** route tất cả event cùng aggregate ID vào cùng partition/consumer lane, kết hợp ordered publisher.
3. **Consumer version guard:** consumer không áp dụng stale version; có thể buffer hoặc yêu cầu replay event thiếu nếu nghiệp vụ cần đủ mọi event.
4. **Commutative/idempotent operations:** một số tổng hợp có thể chấp nhận out-of-order khi có tính chất toán học đã chứng minh.
5. **Snapshot event:** có thể dùng last-version-wins nếu chỉ cần trạng thái mới nhất và contract cho phép bỏ version trung gian.

**Query `SKIP LOCKED` claim chung ở phần 13 không đảm bảo ordering này.** Nếu cần per-aggregate order, phải thiết kế claim query/queue shard theo aggregate và kiểm tra mọi event trước đó đã được xử lý theo semantic phù hợp. Một global `ORDER BY created_at` cũng không đủ khi nhiều publisher gửi song song.

## 19. Producer idempotence và Kafka transactions có thay Outbox không?

Các tính năng Kafka như idempotent producer và transactions giúp bảo vệ một số tình huống **bên trong phạm vi Kafka**, ví dụ duplicate do producer retry hoặc atomic read-process-write giữa topics/offsets trong cấu hình đúng.

Nhưng khi **PostgreSQL là nguồn business truth**, Kafka transaction **không tự kéo JDBC commit vào cùng transaction**. Nếu database commit trước rồi Kafka transaction abort, dual-write gap vẫn có thể xảy ra. Nếu Kafka commit trước rồi database rollback, downstream có thể thấy event không có business state.

Outbox vẫn cần khi hai resources không được điều phối atomic đúng cách. Đừng gọi Kafka `enable.idempotence=true` là giải pháp exactly-once xuyên DB.

### Kafka key và version

Nên dùng `aggregate_id` làm message key khi cần affinity; giữ `event_id` và `aggregate_version` trong payload/headers để consumer dedup và kiểm soát stale event. Cần bảo đảm key serializer ổn định giữa versions.

## 20. RabbitMQ confirms và routing

Với RabbitMQ, publication có một số trạng thái khác nhau:

- Connection/channel hoạt động.
- Client gửi publish frame.
- Broker gửi publisher confirm.
- Message có được route tới ít nhất một queue theo routing key/bindings hay không.
- Consumer có nhận/ACK message hay không.

**Publisher confirm không thay thế consumer ACK**, và một publication không route được tới queue có thể bị mất theo topology nếu ứng dụng không xử lý return/mandatory routing. Cần kiểm tra cả confirms và returned/unroutable message theo cấu hình Spring AMQP/Integration đang dùng.

### Khi broker đang down

- Outbox rows vẫn PENDING/CLAIMED có lease hết hạn.
- Publisher backoff và giảm concurrency.
- Business Batch có thể tiếp tục commit intent nếu business DB còn năng lực và storage budget đủ.
- Nếu backlog vượt ngưỡng, cần backpressure/circuit breaker cho **khả năng ghi thêm outbox**, không để database tăng vô hạn.

Broker recovery cần kiểm thử cả **publication throughput** và **độ tuổi outbox lâu nhất**, không chỉ số connection được phục hồi.

## 21. Consumer Inbox: chống áp dụng event hai lần

Do publisher có thể gửi trùng, **consumer phải chấp nhận at-least-once delivery**. Một mẫu phổ biến là **Transactional Inbox**: cùng transaction ghi business state ở consumer và ghi lại event ID đã xử lý.

Ví dụ PostgreSQL ở consumer database:

~~~sql
CREATE TABLE consumed_event (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Quy trình transaction trong consumer:

~~~text
BEGIN consumer DB transaction

1. INSERT inbox(consumerName, eventId, payloadHash)
   ON CONFLICT DO NOTHING
2. Nếu row mới được insert:
      thực hiện business DB update
   Nếu eventId đã tồn tại:
      kiểm tra payloadHash/version để phát hiện conflict
      nếu đúng duplicate thì không apply business effect
3. COMMIT consumer DB transaction

Sau commit: ACK message / commit Kafka offset theo policy
~~~

### Vì sao inbox và business update phải cùng transaction?

Nếu inbox commit trước còn business update thất bại, lần nhận lại event sẽ bị coi là duplicate và bỏ qua side effect chưa xảy ra. Nếu business update commit trước mà inbox không commit, redelivery sẽ chạy lại business update.

Do đó **cùng database/transaction manager** là điều kiện để inbox bảo vệ DB side effect. Với hai database khác nhau lại phải thiết kế outbox/saga hoặc cơ chế transactional tương đương.

### PostgreSQL ví dụ theo event

~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO consumed_event (
        consumer_name, event_id, payload_hash
    )
    VALUES (
        'billing-projection',
        :eventId,
        :payloadHash
    )
    ON CONFLICT (consumer_name, event_id) DO NOTHING
    RETURNING event_id
)
UPDATE billing_order_projection
SET normalized_status = :normalizedStatus,
    source_version = :sourceVersion
WHERE order_id = :orderId
  AND EXISTS (SELECT 1 FROM accepted);

COMMIT;
~~~

Đây chỉ là minh họa logic. Bảng `billing_order_projection` và cách tạo row mới phải được định nghĩa cho nghiệp vụ thật. Quan trọng nhất: **không chỉ dựa vào affected rows** để phân biệt legitimate duplicate với event ID bị dùng lại cho payload khác; cần query/đối chiếu hash hoặc business version khi conflict.

### ACK sau business commit vẫn có cửa sổ duplicate

Consumer có thể commit DB rồi chết trước ACK/offset commit. Broker redeliver; inbox thấy event ID cũ và bỏ qua side effect. Sau đó consumer ACK theo policy. Cách này hướng tới **effectively-once business effect cho phạm vi transaction đã bảo vệ**, không tuyên bố transport exactly once trong mọi trường hợp.

## 22. Ma trận lỗi end-to-end và trạng thái đúng

| Điểm xảy ra lỗi | Business DB | Outbox | Broker | Hành động phục hồi |
| --- | --- | --- | --- | --- |
| Trước chunk commit | Không commit | Không commit | Chưa phát | Batch rollback/retry theo policy |
| Sau business+outbox commit, trước claim | Đã commit | PENDING | Chưa phát | Publisher đọc sau |
| Sau claim commit, trước send | Đã commit | CLAIMED | Chưa phát | Lease hết hạn/reclaim |
| Broker nhận, publisher không thấy ACK | Đã commit | CLAIMED/PENDING | Có thể đã có | Retry an toàn nhờ consumer dedup |
| Broker ACK, trước mark SENT | Đã commit | CLAIMED | Đã nhận | Gửi lại có thể duplicate |
| Mark SENT DB commit | Đã commit | SENT | Đã nhận theo confirm | Consumer tiếp tục xử lý |
| Consumer nhận rồi DB rollback | Đã commit ở nguồn | SENT | Event đã giao | Broker redelivery/consumer retry |
| Consumer DB commit, trước ACK | Đã commit ở hai phía | SENT | Có thể redeliver | Inbox ngăn side effect trùng |
| Event poison/invalid schema | Đã commit | DEAD hoặc quarantine | Chưa có business completion | Điều tra, sửa contract, replay |
| Outbox bị xóa trước publish | Đã commit | Mất row | Không có event | **Vi phạm bất biến**, cần audit/recovery đặc biệt |

**Nhìn vào ma trận:** Outbox bảo vệ **ý định phát event cùng business commit**. Nó không loại bỏ mọi cửa sổ phát trùng, không tự bảo vệ consumer không idempotent và không thay retention/backup của database.

## 23. Side effect ngoài database tại consumer

Một consumer có thể gửi email, gọi API thanh toán hoặc cập nhật hệ thống thứ ba. Transaction inbox + business DB **không tự bao trùm** side effect đó.

Ví dụ:

~~~text
Consumer ghi inbox DB
Consumer gọi API thanh toán → thành công
Consumer chết trước DB commit
Broker redeliver
Consumer gọi lại API thanh toán → có thể bị trừ hai lần
~~~

Nếu nghiệp vụ cần bảo đảm, các lựa chọn gồm:

- API bên ngoài hỗ trợ **idempotency key** bền vững gắn với business operation.
- Consumer lưu **một outbox thứ hai** cho lệnh gửi tới hệ thống bên ngoài, với publisher/retry riêng.
- Saga/state machine và compensation/reconciliation nếu không có atomic commit.
- Cơ chế đối soát kết quả API khi timeout trả `UNKNOWN`.

Đừng gắn nhãn “exactly once” chỉ vì cả nguồn và consumer đều có bảng outbox/inbox. Mỗi **external side effect boundary** cần được thiết kế cụ thể.

## 24. Java: skeleton publisher polling với transaction ngắn

Ví dụ Java 17, Spring Framework/Boot 3.x, Spring Kafka 3.x và Spring JDBC. Một publisher nhận **một event mỗi vòng** để giữ dễ hiểu và tránh lease của các event chờ trong batch bị hết hạn. Trong production có thể nâng batch/concurrency với giới hạn và heartbeat.

~~~java
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

record ClaimedOutboxEvent(
        UUID eventId,
        long aggregateId,
        long aggregateVersion,
        String eventType,
        String payload,
        UUID leaseToken) {}

@Component
public final class SimpleOutboxPublisher {

    private static final Logger log =
            LoggerFactory.getLogger(SimpleOutboxPublisher.class);

    private static final String CLAIM_SQL = """
        WITH candidate AS (
            SELECT event_id
            FROM outbox_event
            WHERE (
                status = 'PENDING'
                AND next_attempt_at <= now()
            ) OR (
                status = 'CLAIMED'
                AND lease_until < now()
            )
            ORDER BY created_at, event_id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE outbox_event AS e
        SET status = 'CLAIMED',
            leased_by = :publisherId,
            lease_token = :token,
            lease_until = now() + INTERVAL '60 seconds',
            attempts = attempts + 1
        FROM candidate AS c
        WHERE e.event_id = c.event_id
        RETURNING e.event_id, e.aggregate_id,
                  e.aggregate_version, e.event_type,
                  e.payload::text AS payload, e.lease_token
        """;

    private static final String MARK_SENT_SQL = """
        UPDATE outbox_event
        SET status = 'SENT',
            published_at = now(),
            leased_by = NULL,
            lease_token = NULL,
            lease_until = NULL
        WHERE event_id = :eventId
          AND status = 'CLAIMED'
          AND lease_token = :token
        """;

    private static final String RELEASE_SQL = """
        UPDATE outbox_event
        SET status = 'PENDING',
            next_attempt_at = now() + INTERVAL '5 seconds',
            leased_by = NULL,
            lease_token = NULL,
            lease_until = NULL
        WHERE event_id = :eventId
          AND status = 'CLAIMED'
          AND lease_token = :token
        """;

    private final TransactionTemplate dbTransactions;
    private final NamedParameterJdbcTemplate jdbc;
    private final KafkaTemplate<String, String> kafka;

    public SimpleOutboxPublisher(
            TransactionTemplate dbTransactions,
            NamedParameterJdbcTemplate jdbc,
            KafkaTemplate<String, String> kafka) {
        this.dbTransactions = dbTransactions;
        this.jdbc = jdbc;
        this.kafka = kafka;
    }

    @Scheduled(fixedDelay = 1000L)
    public void pollOnce() {
        UUID token = UUID.randomUUID();

        List<ClaimedOutboxEvent> events =
                dbTransactions.execute(status ->
                    jdbc.query(
                        CLAIM_SQL,
                        new MapSqlParameterSource()
                            .addValue("publisherId", "publisher-a")
                            .addValue("token", token),
                        (rs, rowNum) -> readEvent(rs)));

        if (events == null || events.isEmpty()) {
            return;
        }

        ClaimedOutboxEvent event = events.get(0);

        try {
            kafka.send(
                    "order.events",
                    Long.toString(event.aggregateId()),
                    event.payload())
                 .get(10, TimeUnit.SECONDS);

            Integer changed = dbTransactions.execute(status ->
                jdbc.update(
                    MARK_SENT_SQL,
                    eventParameters(event)));

            // Nếu changed != 1: lease đã đổi hoặc DB error;
            // không kết luận event chưa tới broker.
            if (changed == null || changed != 1) {
                throw new IllegalStateException(
                        "Outbox lease was lost");
            }

        } catch (InterruptedException ex) {
            try {
                releaseForRetry(event);
            } finally {
                Thread.currentThread().interrupt();
            }
            log.warn("Outbox send interrupted eventId={}",
                    event.eventId(), ex);
        } catch (Exception ex) {
            log.warn("Outbox send or mark-SENT failed eventId={}",
                    event.eventId(), ex);
            releaseForRetry(event);
        }
    }

    private void releaseForRetry(ClaimedOutboxEvent event) {
        dbTransactions.execute(status ->
            jdbc.update(
                RELEASE_SQL,
                eventParameters(event)));
    }

    private MapSqlParameterSource eventParameters(
            ClaimedOutboxEvent e) {
        return new MapSqlParameterSource()
                .addValue("eventId", e.eventId())
                .addValue("token", e.leaseToken());
    }

    private static ClaimedOutboxEvent readEvent(
            ResultSet rs) throws SQLException {
        return new ClaimedOutboxEvent(
                rs.getObject("event_id", UUID.class),
                rs.getLong("aggregate_id"),
                rs.getLong("aggregate_version"),
                rs.getString("event_type"),
                rs.getString("payload"),
                rs.getObject("lease_token", UUID.class));
    }
}
~~~

### Những điểm đúng về transaction boundary

- `dbTransactions.execute` ở lần claim kết thúc **trước** khi gọi `kafka.send`.
- `kafka.send(...).get(...)` chờ ACK/future outcome theo Kafka producer configuration; ví dụ không tự bảo đảm cluster broker đã được cấu hình durability đúng.
- Mark SENT là transaction DB khác; crash trước nó có thể khiến duplicate.
- `WHERE lease_token = :token` ngăn publisher cũ ghi đè trạng thái của publisher đã reclaim.
- `@Scheduled` cần `@EnableScheduling` hoặc cấu hình scheduling tương ứng để hoạt động.
- `TransactionTemplate` phải dùng **transaction manager của cùng outbox DataSource**.

### Đây chưa phải publisher production hoàn chỉnh

- `publisher-a` cần thay bằng instance identity cấu hình thật, không dùng cùng string cố định cho mọi instance.
- Retry delay cố định 5 giây cần đổi thành exponential backoff + jitter, max attempts và trạng thái DEAD.
- Polling từng event/giây không đáp ứng workload lớn; cần batching, parallelism, pool và deadline được tính kỹ.
- 60 giây lease và 10 giây send timeout chỉ là giả định, cần đo p99 broker confirms và DB transaction latency.
- `event_type`/`event_id`/`aggregate_version` nên được gửi vào **headers hoặc envelope** theo schema protocol; code này chỉ gửi JSON payload. Dùng source event identity phải nhất quán với payload.
- Nếu một publisher thread bị `InterruptedException`, production có thể cần dừng schedule/đóng ứng dụng theo lifecycle thay vì chỉ release row.
- Khi đánh dấu SENT thất bại vì DB outage, đoạn catch có thể không release được; lease expiry/reclaim phải phục hồi.
- Skeleton không bảo vệ **ordering per aggregate**. Chỉ dùng khi business contract cho phép hoặc đã có ordered claim routing.

**Lý do trình bày skeleton:** thấy rõ *ba ranh giới* claim DB → publish network → mark DB, không biến toàn bộ thành một transaction giữ lock trong lúc chờ broker.

## 25. CDC (Change Data Capture) và Debezium Outbox Event Router

Thay vì poll hàng PENDING, một kiến trúc khác sử dụng **CDC**:

~~~mermaid
flowchart LR
    B["Batch chunk transaction"] --> D[("Business + Outbox DB")]
    D --> WAL[["DB WAL / change log"]]
    WAL --> CDC["CDC connector"]
    CDC --> K[["Kafka topics"]]
    K --> C["Consumers"]
~~~

Với PostgreSQL, CDC dùng logical replication/log decoding theo cấu hình. Debezium có cơ chế **Outbox Event Router** để route outbox events thành records phù hợp. Phải đọc tài liệu/version thực khi cấu hình schema và transform; các tên field trong bảng ví dụ **không mặc nhiên trùng** schema mặc định mà Event Router mong đợi.

### Ưu điểm

- Không cần các publisher worker liên tục scan outbox `PENDING`.
- Có thể dùng database commit log để quan sát những insert đã commit.
- Hữu ích khi tần suất events lớn và workload write được tối ưu đúng.
- Có thể tận dụng Kafka Connect ecosystem cho monitoring và restart.

### Các rủi ro

- Logical replication slot bị lag làm WAL giữ lại, có thể đầy disk nếu connector outage.
- Snapshot/initialization và recovery phải bảo đảm không bỏ qua events.
- Schema evolution có thể làm connector/consumer lỗi.
- Outbox event update statuses không nên bị phát như business events ngoài ý muốn; cần filter và route đúng.
- CDC connector/restart vẫn có thể redeliver; downstream dedup vẫn cần.
- Kafka transaction/connector không tự bảo đảm consumer DB exactly once.
- Thứ tự commit log không đồng nghĩa mọi consumers hoàn thành cùng thứ tự giữa topics/partitions.

### Polling vs CDC: chọn theo ngữ cảnh

Nếu workload vừa phải, đội ngũ chưa vận hành CDC và muốn policy retry/quarantine rõ ở DB, polling là lựa chọn dễ kiểm soát. Nếu throughput cao, cần giảm polling scans và đã có hạ tầng Kafka Connect/Debezium, CDC có thể phù hợp hơn. **Không nên bật đồng thời hai con đường publish cùng outbox rows** trừ khi có mục đích và dedup/route contract được chứng minh.

## 26. Scaling publisher: workers, partition keys, database budget

Tăng số publisher JVM có thể tăng throughput đến khi gặp giới hạn ở:

- DB claim/update QPS và index scans.
- Broker publish rate, partition count, ACK latency và quotas.
- Network bandwidth, CPU serialization, TLS.
- JVM heap và số events inflight.
- DB connection pool của outbox.
- Consumer throughput và backlog downstream.
- Chính sách ordering per aggregate.

Một mô hình sơ bộ:

\[
R_{\mathrm{publication}}
\leq \min(R_{\mathrm{DB\ claim}},
          R_{\mathrm{broker}},
          R_{\mathrm{network}},
          R_{\mathrm{consumer\ sustainable}})
\]

Trong đó `R_consumer sustainable` không giới hạn khả năng broker nhận ngay trong mọi trường hợp, nhưng là giới hạn để **toàn pipeline không tích backlog vô hạn**.

### Tăng publishers không sửa ordering

Nếu có 20 publishers cùng claim outbox không xét aggregate ID, chúng có thể gửi version 20 trước version 19. Để scale có ordering:

- Chia publisher lanes theo `hash(aggregate_id)` hoặc shard ID ổn định.
- Trong mỗi lane, phát các versions của một aggregate theo thứ tự.
- Hoặc thêm database query guard đảm bảo prior version đã được mark SENT trước version kế tiếp, kèm replay policy khi có gap.
- Với Kafka, route same aggregate key vào cùng partition và tránh concurrent sends làm đảo thứ tự theo business sequence.
- Với RabbitMQ, xem queue ordering/concurrent consumer/priority semantics; FIFO broker không tự bảo đảm effect order.

**Một aggregate nóng có thể giới hạn throughput của lane riêng**, không thể đạt linear scaling chỉ bằng thêm worker.

## 27. Outbox trong multi-threaded step

Trong multi-threaded step, nhiều chunk threads có thể thực hiện writer cùng một StepExecution và cùng DataSource pool.

Các câu hỏi cần trả lời:

1. Reader có thread-safe và checkpoint đúng không?
2. Processor/writer có mutable shared state không?
3. Hai chunks có thể cập nhật cùng order ID/source version không?
4. Event ID có ổn định khi chunk retry/rollback không?
5. SQL upsert/version predicate có xử lý concurrency xung đột không?
6. DB pool có đủ cho các chunk transactions và JobRepository không?
7. Publisher có độc lập với chunk threads, không giữ DB locks khi publish không?

### `@StepScope` không bảo đảm mỗi chunk một writer instance

Scope này theo StepExecution. Nếu nhiều threads cùng chạy một StepExecution, một scoped writer có thể được truy cập concurrent. Writer ví dụ ở phần 8 không giữ per-chunk state trong singleton field, nhưng DB/driver, ItemReader và dependencies khác vẫn phải được kiểm tra.

### Thứ tự chunk commit

Các chunks có thể commit đảo thứ tự đầu vào. Nếu outbox aggregate versions phải liên tiếp, writer dùng version guard và publisher/consumer có ordered delivery/reconstruction policy. Không suy từ số chunk `readCount` để tạo event sequence.

## 28. Outbox trong local/remote partitioning

Với partitioning, manager tạo input ranges, worker StepExecutions ghi business data và outbox rows bằng transactions ở worker.

~~~mermaid
flowchart TB
    M["Manager Partitioner"] --> A["Worker partition A"]
    M --> B["Worker partition B"]
    A --> DB[("Business DB + Outbox")]
    B --> DB
    DB --> P["Independent Publisher"]
    P --> K[["Broker"]]
~~~

### Ranh giới đúng

- Mỗi worker step dùng cùng DB resource cho business+outbox trong **chunk transaction tương ứng**.
- Worker không cần publish trực tiếp qua broker trong transaction.
- Manager không cần tự tạo event thay worker nếu event phản ánh business commit ở worker.
- Partition names và ExecutionContexts phải ổn định qua restart.
- Nếu hai partition overlap/hot keys, unique constraints/version guard giúp chống một số duplicate nhưng không thay thiết kế phân vùng chính xác.

### Remote partitioning

Manager có thể mất reply sau khi worker đã commit một hoặc nhiều chunks. Khi StepExecution được khôi phục/replayed, idempotent business write và outbox identity ổn định giúp tránh sự kiện trùng ở cấp domain. **Không tự giao cùng StepExecution cho worker khác khi worker cũ có thể còn chạy**; ownership/fencing và JobRepository vẫn phải được quản lý.

### Resource budget toàn cluster

Nếu có tám worker JVM mỗi worker HikariCP max 12, tổng trần worker là 96 connections; publisher instances và manager còn dùng thêm pool riêng. Auto-scale worker mà không tính publisher/JobRepository pool có thể làm DB cạn connections, tăng lock wait và chậm publication.

## 29. Remote chunking: manager đọc, worker ghi intent

Trong remote chunking, manager thường đọc và gửi chunk messages, worker xử lý/ghi rồi reply. Nếu writer của worker sở hữu business commit, **outbox row nên được tạo trong cùng DB transaction ở worker**, không dựa vào manager đã gửi request.

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant Q as Chunk request queue
    participant W as Worker
    participant D as Business DB/Outbox
    participant P as Publisher
    participant K as Broker downstream

    M->>Q: Chunk request
    Q->>W: Deliver chunk
    W->>D: BEGIN → business UPDATE + outbox INSERT
    D-->>W: COMMIT
    W-->>M: Chunk reply
    P->>D: Claim committed outbox
    P->>K: Publish event
~~~

**Vấn đề kép:** có thể xảy ra duplicate ở request queue **và** ở publisher→broker. Idempotency phải bảo vệ từng logical event/operation. Không dùng chunk correlation ID ngẫu nhiên làm khóa domain nếu một business event có thể nằm trong chunk khác sau restart.

### Worker commit xong nhưng manager timeout

Manager có thể chưa biết worker đã commit; retry/redelivery làm worker nhận lại chunk. SQL version guard/outbox unique event ID có thể biến replay thành no-op an toàn, nhưng business state và consumer effect phải được kiểm chứng theo contract.

### Ordering giữa chunks

Nếu cùng aggregate được xử lý trong hai chunks khác nhau và worker concurrency cao, chunk sau có thể commit trước chunk trước. Cần key affinity, sequence guard hoặc tính chất snapshot/commutativity phù hợp, không dựa vào FIFO broker như bảo đảm duy nhất.

## 30. Backpressure khi broker down lâu

Outbox giúp **business commit không phải chờ broker tức thì**, nhưng không có nghĩa hệ thống có thể ghi events vô hạn khi broker down nhiều ngày.

Nếu đầu vào tạo 10.000 events/s, mỗi payload trung bình 1 KiB:

\[
10.000\times1\ \mathrm{KiB}
=10.000\ \mathrm{KiB/s}
\approx 9{,}77\ \mathrm{MiB/s}
\]

Chưa tính indexes, WAL, row overhead, replication hay storage bloat. Sau một giờ, riêng raw payload có thể đạt khoảng **34 GiB** theo giả định này. Dung lượng DB thật thường lớn hơn đáng kể.

### Chính sách cần quyết định

- Outbox table có tối đa bao nhiêu hàng/dung lượng cho phép?
- “Oldest PENDING event age” còn bao nhiêu trước khi vi phạm publication SLA?
- Khi broker down, có cho Batch tiếp tục ghi business state/outbox không?
- Khi backlog quá ngưỡng, có dừng job admission hoặc throttle reader không?
- Khi publisher hồi phục, tốc độ drain tối đa có ảnh hưởng DB writers đang chạy không?
- Có được ưu tiên event loại nào không và ordering bị ảnh hưởng thế nào?
- Khi nào alert, khi nào giảm concurrency, khi nào chuyển chế độ degraded?

**Backpressure cần đặt theo cả business SLA và storage budget**. Không chỉ cấu hình queue thật lớn, rồi phát hiện outbox làm đầy ổ đĩa database khiến cả business transaction ngừng commit.

## 31. Metrics và logging cho Outbox

Một dashboard phân biệt **business write throughput** với **publication throughput**.

| Metric | Ý nghĩa |
| --- | --- |
| `outbox_inserted_total` | Số events intent mới commit |
| `outbox_pending_count` | Số rows chờ phát |
| `outbox_oldest_pending_age_seconds` | Độ tuổi event lâu nhất chưa phát |
| `outbox_claimed_count` | Số events đang được publisher giữ |
| `outbox_expired_lease_total` | Claim phải phục hồi vì lease hết |
| `outbox_publish_attempts_total` | Tổng attempts gồm retries |
| `outbox_published_total` | Số events đã mark SENT thành công |
| `outbox_dead_total` | Poison/events cần can thiệp |
| `outbox_publication_lag_seconds` | Khoảng commit intent đến broker confirm/mark SENT |
| `outbox_claim_latency_seconds` | Thời gian query/transaction claim |
| `broker_publish_ack_latency` | Latency broker acknowledgment |
| `publisher_fenced_updates_total` | Số mark SENT thất bại do token cũ |
| `business_unique_commits_total` | Work nghiệp vụ hữu ích hoàn thành |
| `consumer_inbox_duplicates_total` | Duplicate delivery được dedup |
| `consumer_processing_failures_total` | Event không áp dụng thành công ở downstream |

Các tên metric chỉ minh họa, không phải tất cả được Spring Batch/Actuator tự sinh.

### Log có cấu trúc

~~~text
event=outbox_publish_attempt
eventId=99fc...a21
aggregateType=order
aggregateId=9000123
aggregateVersion=17
publisherInstance=outbox-publisher-2
attempt=3
leaseToken=lease-opaque
broker=Kafka
topic=order.events
outcome=ACK_UNKNOWN
elapsedMs=1250
~~~

Trong production, hạn chế log full payload/PII và dùng opaque IDs theo policy. Tránh đưa eventId/aggregateId/leaseToken vào metric labels có **high cardinality**; dùng structured logs/traces để truy vấn từng event.

### Hai số nên xem cùng nhau

Nếu `outbox_pending_count` giảm nhưng `outbox_oldest_pending_age` vẫn tăng, có thể publisher đang bỏ qua một số events cũ/poison hoặc ưu tiên sai. Không kết luận “backlog đang hồi phục” chỉ từ tổng count.

## 32. Cleanup, retention và bảng Outbox tăng trưởng

Nếu mọi event SENT đều giữ mãi, database sẽ tiếp tục tăng. Nếu xóa quá sớm, mất khả năng audit/replay khi consumer gặp sự cố.

Một retention policy phải xác định:

- SENT events giữ ít nhất bao lâu sau broker confirm?
- Có business/audit/legal retention độc lập không?
- Consumer cần replay từ broker hay từ outbox?
- Publication lag tối đa dự kiến và lease expiration là bao nhiêu?
- Khi message broker retention ngắn, xóa outbox SENT có làm mất khả năng recovery không?
- Có archive theo partition ngày/tháng hoặc object storage không?
- Consumer inbox giữ ID bao lâu so với retry/redelivery/replay window?

### Không xóa trạng thái chưa hoàn tất

Không dùng cleanup kiểu:

~~~sql
DELETE FROM outbox_event
WHERE created_at < now() - INTERVAL '7 days';
~~~

vì lệnh có thể xóa **PENDING, CLAIMED hoặc DEAD events** chưa được xử lý. Một cleanup tối thiểu an toàn hơn:

~~~sql
DELETE FROM outbox_event
WHERE status = 'SENT'
  AND published_at < now() - INTERVAL '30 days';
~~~

Ví dụ chỉ mô tả predicate; production phải dùng **batch delete/partition-drop/archival có kiểm soát** để không giữ transaction cực lớn, tạo WAL/lock/bloat. Cần xem SLA/audit trước khi chọn 30 ngày.

### Outbox và inbox retention là một bài toán end-to-end

Nếu producer có thể replay một event sau 90 ngày nhưng consumer inbox chỉ giữ dedup ID 7 ngày, một event cũ bị phát lại có thể áp dụng side effect lần nữa. Hoặc phải giới hạn replay semantics, hoặc giữ business idempotency record lâu hơn, hoặc dùng version/business guard độc lập.

## 33. Schema evolution, security và quyền phát message

Outbox payload có thể chứa dữ liệu đơn hàng, khách hàng hoặc thanh toán. Việc nó nằm trong DB và broker làm tăng số nơi dữ liệu được lưu.

### Schema contract

- Dùng `event_type` có version: `order.normalized.v1`.
- Định nghĩa producer/consumer compatibility (additive fields, default values, deprecation).
- Test old events còn tồn khi deploy consumer version mới.
- Không thay đổi ý nghĩa field âm thầm dù JSON key vẫn giống.
- Có cách quarantine event không parse được và khôi phục sau sửa schema.
- Với CDC, bảo đảm event router/connector schema khớp bảng thực.

### Bảo mật

- Không đưa password, token hoặc dữ liệu nhạy cảm không cần thiết vào outbox payload.
- Nếu cần PII, áp dụng encryption/field minimization, retention và access controls theo chính sách.
- Publisher chỉ cần quyền SELECT/UPDATE bảng outbox, không nhất thiết có quyền sửa toàn bộ bảng business.
- Consumer phải xác minh tính hợp lệ của message/schema/source khi có threat model phù hợp.
- Tránh log raw payload, JDBC URL có secrets và broker credentials.
- Replay tool phải có audit, phân quyền và giới hạn tốc độ để không tạo duplicated payment/notification.

**Event ID không phải capability token.** Biết event ID không được tự cấp quyền publish/replay/truy cập dữ liệu.

## 34. Integration test: business + outbox commit atomic

Bài test đầu tiên không cần broker. Mục tiêu là chứng minh ranh giới transaction.

**Kịch bản A — Commit thành công:**

1. Seed một order input mới với `sourceVersion=17` và `eventId=E17`.
2. Chạy Spring Batch chunk với đúng business transaction manager.
3. Assert `order_projection` chứa version 17.
4. Assert đúng một `outbox_event` với eventId E17 và payload/version tương ứng.
5. Assert JobRepository StepExecution status và write count theo contract.

**Kịch bản B — Outbox insert lỗi:**

1. Chuẩn bị unique conflict có chủ đích hoặc fault injection trước insert.
2. Chạy chunk/writer.
3. Assert transaction rollback: **business state không được commit mới** và không có event mới sai.
4. Nếu Step có retry, assert retry đúng exception/budget; không pass chỉ vì exception bị swallow.

**Kịch bản C — Input duplicate/restart:**

1. Chạy lại cùng sourceVersion/eventId.
2. Assert không tạo thêm business update/event mới.
3. Thử cùng event ID với payload/version mâu thuẫn; assert conflict được phát hiện theo business policy.
4. Kiểm tra restart cùng JobInstance/identifying parameters và checkpoint.

### Lưu ý khó: JobRepository có thể ở DB khác

Nếu JobRepository và business outbox nằm trên hai DataSources, cần test crash **giữa business commit và metadata update**; worker replay phải an toàn. Đừng chỉ test happy path của một transaction trên một connection rồi suy ra restart của toàn job an toàn.

## 35. Fault injection: broker, publisher, consumer

Với Testcontainers PostgreSQL và Kafka/RabbitMQ phù hợp production transport, dựng ít nhất một worker job, một publisher và một consumer có inbox.

| Điểm inject lỗi | Kỳ vọng |
| --- | --- |
| Worker crash trước chunk commit | Không business change/outbox event mới |
| Worker crash sau business+outbox commit | PENDING event vẫn còn để publish |
| Publisher chết sau claim trước send | Lease expire rồi reclaim |
| Publisher chết sau broker ACK trước mark SENT | Có thể duplicate, consumer dedup |
| Publisher lease hết khi send còn chạy | Fencing chặn ghi SENT bằng token cũ |
| Broker down 10 phút | Backlog được giữ, không xóa outbox |
| Broker ACK timeout dù message đã được append | Retry có thể duplicate nhưng không nhân đôi effect |
| Consumer DB rollback trước ACK | Event được xử lý lại an toàn |
| Consumer DB commit trước ACK/offset commit | Inbox ngăn áp dụng lại |
| Publisher poison event | DEAD/quarantine, alert và replay có kiểm soát |
| Hai publishers đồng thời | Không cùng giữ claim hợp lệ tại một thời điểm, nhưng redelivery vẫn xử lý |
| Event versions 17,18,19 phát đảo | Ordering/version guard xử lý đúng contract |
| Cleanup chạy song song publisher | Không xóa PENDING/CLAIMED/DEAD trái chính sách |
| Consumer upgrade schema | Old events vẫn parse hoặc quarantine rõ |

**Kết quả test phải gồm DB state và business reconciliation**, không chỉ số message được gửi/nhận. Thêm deadlines/polling theo điều kiện thay vì `Thread.sleep` cố định để giảm flaky CI.

### Một lỗi rất dễ bỏ qua

Nếu publisher gửi ACK thành công và test kết thúc ngay sau đó, chưa kiểm tra được **mark SENT DB commit** hoặc consumer inbox/side effect. Fault injection phải đo đúng thứ tự các transaction boundaries.

## 36. Case study: 30 triệu đơn hàng trong 50 phút

Một hệ thống chuẩn hóa **30.000.000 đơn hàng** vào PostgreSQL, cần phát `order.normalized.v1` cho downstream analytics. SLA business commit là **50 phút**, publication lag p99 mục tiêu dưới một khoảng được business chấp nhận (giả sử 90 giây trong bài toán này).

Throughput business tối thiểu lý tưởng:

\[
R_{\mathrm{required}}=
\frac{30.000.000}{50\times60}
=10.000\ \mathrm{orders/s}
\]

Đây là cận trước khi tính startup, retries, tail partition và checkpoint overhead.

### Thiết kế ban đầu

Manager chia thành 48 partitions, tám worker JVM ghi PostgreSQL. Writer trước đây làm:

~~~text
UPDATE business projection → COMMIT
then publish Kafka message
~~~

Khi Kafka outage ngắn xảy ra giữa job, một số business rows đã commit nhưng **không có event**. Worker restart không dễ phát hiện những rows đã bị bỏ qua và có thể tạo duplicates nếu replay toàn bộ thiếu idempotency.

### Chuyển sang Outbox

1. Mỗi worker chunk ghi business projection và event intent trong một DB transaction.
2. Event ID/version giữ ổn định qua restart.
3. Publisher claim/sends theo pool riêng, broker ACK rồi mark SENT.
4. Consumer dùng inbox dedup và aggregate version guard.
5. Khi Kafka outage, publisher backoff, outbox backlog tăng có đo/alert.
6. Manager/worker admission có policy nếu outbox storage vượt budget.
7. Cleanup chỉ xử lý SENT theo retention/audit contract.

### Benchmark giả định

| Phương án | Business commit throughput | Publish throughput | Độ an toàn |
| --- | ---: | ---: | --- |
| Dual write trực tiếp, không retry | 12.000 orders/s | 12.000 attempts/s | Có cửa sổ mất event |
| Dual write, retry nhiều | 10.800 orders/s | 12.500 attempts/s | Duplicate/loss vẫn có thể |
| Outbox, một publisher polling chậm | 10.200 orders/s | 4.000 events/s | Intent bền, backlog tăng |
| Outbox, nhiều publishers bounded | 10.100 orders/s | 12.000 events/s | Có thể drain backlog |
| Outbox + CDC đã benchmark | 10.300 orders/s | 12.500 events/s | Intent bền, vẫn cần dedup |

**Mọi số liệu đều giả định**, không phải benchmark của Spring Batch/PostgreSQL/Kafka hay Debezium. Publication throughput lớn hơn business throughput chỉ khi còn backlog cần drain hoặc nguồn khác, không phải broker “tự tạo thêm event”.

### Đo kết quả đúng cách

- Business JobExecution phải hoàn thành trong SLA.
- Mỗi logical business update có đúng intent phù hợp đã commit.
- Không event intent nào bị mất khi worker chết trước/ sau chunk commit.
- Publisher lag p99 và oldest pending age thỏa SLA phụ.
- Consumer nhận duplicate nhưng business state không bị áp dụng hai lần.
- Backlog dần giảm sau khi Kafka hồi phục, DB không vượt connection/disk budget.
- Schema evolution không làm kẹt poison events lâu vô hạn.

**Bài học:** Outbox chuyển vấn đề “không biết đã mất event nào” thành **một hàng đợi bền vững có thể đo, retry và đối soát**. Đó là thay đổi quan trọng về correctness, không chỉ là tối ưu tốc độ.

## 37. Runbook xử lý Outbox backlog

Khi `outbox_oldest_pending_age` vượt ngưỡng, không tăng publisher replicas ngay theo phản xạ.

**Bước 1 — Xác định trạng thái.** Đếm PENDING/CLAIMED/DEAD, oldest event, leases expired và rate inserted vs published.

**Bước 2 — Kiểm tra broker.** Kafka topic/partitions/ISR/acks, RabbitMQ confirms/routing, network/TLS, quotas và broker-side throttling.

**Bước 3 — Kiểm tra publisher.** Claims/s, publish p95/p99, retry reasons, dead rows, stale leases và fencing update failures.

**Bước 4 — Kiểm tra DB.** Query plan của claim index, CPU/IOPS/WAL, connection pool wait, locks, table bloat, CDC slot lag nếu dùng CDC.

**Bước 5 — Kiểm tra ordering.** Có một aggregate/hot key làm tắc lane? Có version gap hoặc consumer chờ event trước?

**Bước 6 — Chọn biện pháp.** Sửa broker/config/schema, giảm retry storm, tăng bounded publisher concurrency nếu downstream còn capacity, hoặc throttle Batch writers khi outbox storage gần giới hạn.

**Bước 7 — Khôi phục poison events.** Ghi audit, fix payload/schema, replay đúng event ID hoặc tạo compensating event theo policy; không xóa row thất bại rồi tuyên bố xong.

**Bước 8 — Đối soát.** So business committed changes với outbox intents, outbox SENT với broker/consumer evidence, và business downstream effect.

### Khi nào không nên tăng publisher?

- DB claim/update đã bão hòa.
- Kafka partition count/quota đã là bottleneck.
- Một aggregate phải giữ order tuyệt đối.
- Consumer downstream không theo kịp và broker backlog tăng.
- Poison messages khiến publisher liên tục retry vô ích.

## 38. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Outbox giúp gửi broker đúng một lần.” | Có thể gửi trùng sau ACK-before-SENT, thường là at-least-once. |
| “@Transactional bao trùm JDBC và Kafka tự động.” | Không có atomic dual-resource commit nếu không thiết kế riêng. |
| “Outbox INSERT có thể REQUIRES_NEW để chắc bền.” | Có thể phát event dù business transaction rollback. |
| “Job COMPLETED nghĩa mọi message tới consumer.” | Publication thường chạy async sau commit. |
| “Status SENT là consumer đã xử lý.” | Thường chỉ broker ACK/confirm được ghi nhận. |
| “Publisher confirm = RabbitMQ message đã tới đúng queue.” | Phải kiểm tra routing/returns và topology tương ứng. |
| “Kafka idempotent producer loại bỏ DB dual write.” | Chỉ bảo vệ những phạm vi Kafka hỗ trợ; không atomic với JDBC. |
| “Lease đảm bảo không duplicate publish.” | Old publisher có thể gửi sau lease expiry. |
| “SKIP LOCKED đảm bảo event đúng thứ tự.” | Nó phục vụ claim concurrency, không bảo đảm ordering. |
| “Đẩy tất cả events vào một Kafka partition giải quyết mọi thứ.” | Có thể tạo throughput bottleneck; ordering cần theo business key. |
| “Event ID ngẫu nhiên mỗi retry là ổn.” | Làm mất khả năng dedup logical event. |
| “Consumer ACK trước DB commit cho nhanh.” | Crash có thể làm mất business effect. |
| “Inbox INSERT riêng transaction là đủ.” | Có thể đánh dấu processed trước khi business update commit. |
| “Outbox không cần cleanup.” | Storage/index/WAL sẽ tăng không giới hạn. |
| “Xóa mọi row cũ hơn 7 ngày là an toàn.” | Có thể xóa PENDING/DEAD chưa publish. |
| “CDC loại bỏ mọi duplicate.” | Connector/restart/consumer vẫn có at-least-once failure windows. |
| “Tăng worker giải quyết backlog.” | DB/broker/consumer hoặc ordering lane có thể là bottleneck. |
| “Outbox bảo đảm dữ liệu consumer đúng dù có API bên ngoài.” | External side effects vẫn cần idempotency/saga. |

## 39. Checklist thiết kế production

- [ ] Đã xác định business events thực sự bắt buộc phát bền vững.
- [ ] Business update và outbox insert **cùng transaction DB thật**.
- [ ] Không publish broker trực tiếp bên trong chunk transaction như cách duy nhất bảo đảm event.
- [ ] Writer dùng cùng DataSource/transaction manager cho business+outbox.
- [ ] JobRepository/DataSource ranh giới được hiểu rõ, nhất là khác DB.
- [ ] Event ID ổn định theo business operation qua retry/restart.
- [ ] Duplicate source version/payload conflict được xử lý theo business policy.
- [ ] Outbox schema có payload version, uniqueness, retries, schedule và trạng thái audit.
- [ ] Publisher claim DB transaction ngắn, gửi network **ngoài** transaction.
- [ ] Nhiều publishers dùng SKIP LOCKED/lease/fencing có giới hạn.
- [ ] Publisher chỉ mark SENT sau ACK/confirm theo broker configuration đã kiểm chứng.
- [ ] Broker ACK unknown được xử lý bằng retry **duplicate-safe**.
- [ ] RabbitMQ routing/return hoặc Kafka acks/replication được cấu hình phù hợp.
- [ ] Retry có backoff/jitter, max attempts và poison quarantine.
- [ ] Không xóa DEAD/PENDING rows bằng retention job chung.
- [ ] Có ordering policy theo aggregate nếu business yêu cầu.
- [ ] Consumer dùng inbox/dedup/sequence guard trong transaction phù hợp.
- [ ] External API side effects có idempotency key hoặc saga/outbox bổ sung.
- [ ] Remote chunking/partitioning replay không nhân đôi business event.
- [ ] Có concurrency/pool budget toàn worker/publisher cluster.
- [ ] Có limit cho outbox backlog, storage/WAL và oldest pending age.
- [ ] Có sự phân biệt SLA business commit và SLA publication.
- [ ] Schema evolution/CDC snapshot/recovery được kiểm thử.
- [ ] Metrics đo inserted, claimed, SENT, DEAD, lease expiry, publish latency.
- [ ] Log có eventId, aggregateVersion, phase và không lộ payload nhạy cảm.
- [ ] Đã test crash trước/sau DB commit và trước/sau broker ACK.
- [ ] Đã test consumer DB commit trước ACK/offset commit.
- [ ] Có replay/cleanup/runbook với audit và quyền truy cập phù hợp.
- [ ] Đối soát business keys, events và consumer effect; không chỉ đếm message attempts.

## 40. Câu hỏi tự kiểm tra

**1. Vì sao Spring Batch commit DB rồi gọi Kafka send chưa đủ an toàn?**

Vì JVM có thể chết sau DB commit nhưng trước Kafka publish. Không có event bền vững để tự động retry nếu chỉ ghi business table.

**2. Outbox atomicity nằm ở đâu?**

Ở cùng transaction database ghi business state và outbox event intent. Publisher→broker là một transaction boundary khác.

**3. Nếu outbox insert thất bại trong cùng chunk transaction, business update nên ra sao?**

Nó phải rollback cùng transaction. Nếu business đã commit trước đó, hệ thống đã không giữ đúng outbox invariant.

**4. Vì sao không sinh UUID mới mỗi lần writer retry?**

Vì logical event sẽ có ID khác và consumer/inbox không nhận ra duplicate theo event ID.

**5. Vì sao publisher không nên giữ row lock khi chờ Kafka ACK?**

Vì network wait kéo dài DB transaction/lock và giảm throughput, thậm chí gây deadlock/pool exhaustion.

**6. SKIP LOCKED và lease bảo vệ điều gì?**

Giúp các publisher claim work có kiểm soát và reclaim sau crash. Chúng không bảo đảm broker chỉ nhận event một lần.

**7. Broker ACK đã thành công nhưng publisher chết trước mark SENT. Điều gì xảy ra?**

Outbox có thể được gửi lại sau lease expire; consumer phải dedup theo event identity bền vững.

**8. Mark SENT có nghĩa consumer đã commit business state không?**

Không. Nó thường phản ánh producer đã nhận broker ACK/confirm. Consumer có thể còn lag hoặc fail.

**9. Inbox phải nằm chung transaction với thao tác nào?**

Business DB side effect của consumer. Nếu chỉ insert inbox rồi commit riêng, crash có thể làm mất business update.

**10. Nếu consumer gọi API thanh toán ngoài DB, inbox có giải quyết hết duplicate không?**

Không. API có thể đã thực hiện trước khi inbox transaction commit; cần API idempotency key, outbox khác, saga hoặc reconciliation.

**11. Kafka partition theo aggregate key có tự đảm bảo event versions được phát đúng thứ tự không?**

Không. Nó giữ thứ tự append trong partition, nhưng publisher song song có thể gửi version sau trước; cần ordered publishing hoặc consumer sequence guard.

**12. Outbox và CDC có thể bật song song vô điều kiện không?**

Không. Hai publisher paths có thể phát cùng event; cần kế hoạch cutover, dedup và filter/routing rõ.

**13. Khi JobExecution COMPLETED mà Outbox còn 100.000 PENDING, có phải bug?**

Phụ thuộc contract. Nếu job chỉ chịu trách nhiệm commit business state+event intent, publication async có thể tiếp tục. Nhưng publication SLA/backlog phải được giám sát.

**14. Vì sao không cleanup toàn bộ events quá 7 ngày?**

Có thể có PENDING, CLAIMED, DEAD chưa được publish; xóa chúng sẽ làm mất durable intent.

**15. Mỗi giây tạo 10.000 events, publisher chỉ gửi 4.000. Điều gì xảy ra?**

Outbox backlog tăng khoảng 6.000 events/s (trong giả định ổn định). Cần nâng năng lực sustainable, giảm arrival rate hoặc thực hiện backpressure trước khi storage/SLA bị vi phạm.

**16. Ở remote chunking, một chunk được redeliver sau worker commit thì Outbox giúp gì?**

Stable business event ID/version và atomic upsert/outbox ngăn replay tạo intent mới sai; consumer dedup bảo vệ những lần publish trùng khác.

**17. Vì sao status DEAD cần audit?**

Vì business state đã commit nhưng event không publish được theo retry budget; nếu xóa im lặng, downstream có thể mãi không nhận thay đổi.

**18. Điều kiện cuối cùng để coi thiết kế Outbox đạt production là gì?**

Business state đúng, mỗi change có durable event intent, publication phục hồi được qua crash/outage, consumer effect idempotent, ordering theo contract, resource/backlog trong budget và SLA thực được kiểm chứng.

---

**Ghi nhớ:** Transactional Outbox không làm DB và broker trở thành một transaction chung. Nó **ghi business change và ý định phát event atomically trong database**, rồi phát message sau commit qua publisher/CDC có thể retry. Do ACK, lease expiry, restart và network failure, duplicate delivery vẫn có thể xảy ra: cần **event identity ổn định, consumer inbox/idempotency, ordering theo aggregate, retry bounded và đối soát**. Với Spring Batch scaling, hãy giữ chunk transaction ngắn, tách network publish, tính pool/backlog toàn cluster và kiểm thử **cả trước/sau DB commit lẫn trước/sau broker ACK**. Thiết kế đúng là thiết kế **không làm mất event intent khi gặp sự cố, có thể phục hồi và hoàn thành business effect đúng trong SLA**.
