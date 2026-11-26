# Version sự kiện và phát hiện sự kiện đến sai thứ tự

Trong hệ thống bất đồng bộ dùng **RabbitMQ và Spring AMQP**, message có thể đến consumer khác thứ tự mà nghiệp vụ tạo ra. Nguyên nhân không chỉ nằm ở broker: có thể có nhiều publisher, nhiều consumer, `prefetch`, xử lý song song, retry, requeue, dead-letter hoặc một worker gửi lại sự kiện cũ sau khi mất kết nối.

Một giải pháp nền tảng là gắn **phiên bản sự kiện theo từng đối tượng nghiệp vụ** (thường gọi `aggregateVersion`) vào mỗi message. Consumer lưu phiên bản cuối đã áp dụng, so sánh phiên bản đến và quyết định **áp dụng ngay, bỏ qua bản trùng, chờ phiên bản còn thiếu hoặc cách ly sự kiện mâu thuẫn**.

Bài thuộc chương **Thứ tự và đồng thời** của module **SPRING_AMQP**. Ví dụ kết hợp `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding, xác nhận ACK/NACK, retry, dead-letter và dữ liệu bền vững để xử lý sự kiện đến sai thứ tự mà vẫn có thể phục hồi khi hệ thống lỗi.

## 1. Ví dụ: cập nhật tồn kho không theo thứ tự

Giả sử sản phẩm `P-100` bắt đầu có số lượng tồn kho bằng 0. Dịch vụ nguồn phát ba sự kiện thay đổi tồn kho:

| Sự kiện | `eventId` | `aggregateId` | `aggregateVersion` | Thay đổi | Tồn kho sau khi áp dụng đúng thứ tự |
|---|---|---|---:|---:|---:|
| Nhập hàng | `e1` | `P-100` | 1 | +10 | 10 |
| Xuất hàng | `e2` | `P-100` | 2 | −3 | 7 |
| Nhập thêm | `e3` | `P-100` | 3 | +7 | 14 |

Nếu consumer nhận lần lượt `e2, e3, e1, e2`, bản sao `e2` xuất hiện lần nữa sau cùng:

```text
Thứ tự ở dịch vụ nguồn:       e1(v1) ---- e2(v2) ---- e3(v3)
                                             |
Thứ tự tới consumer:         e2(v2) -> e3(v3) -> e1(v1) -> e2(v2)
                               |         |         |         |
                               v         v         v         v
Consumer lastVersion=0       GAP(1)    GAP(1)    ÁP DỤNG    TRÙNG
                               |         |      v1,v2,v3       |
                               v         v         |           v
                          Lưu tạm    Lưu tạm   last=3       Bỏ qua
                                                 stock=14
```

Vì phép cộng trừ trong ví dụ có thể cho cùng kết quả nếu đổi thứ tự, lỗi **thứ tự** đôi khi bị che khuất. Trong hệ thống thật, nhiều hành động không hoán đổi được, chẳng hạn:

- `OrderCreated → OrderPaid → OrderCancelled`: nhận `Cancelled` trước `Created` có thể khiến state machine sai hoặc thất lạc quyết định nghiệp vụ.
- `BalanceReserved → BalanceReleased`: giải phóng tiền trước khi đặt giữ tiền có thể làm số dư khả dụng không hợp lệ.
- `AccountEnabled → AccountDisabled`: áp dụng sự kiện cũ sau sự kiện mới có thể bật lại tài khoản ngoài ý muốn.
- Sự kiện delta `+10` và `-3` có thể bị kiểm tra điều kiện nghiệp vụ (`quantity >= 0`) khác nhau tùy thứ tự.

**Vấn đề cần giải:** Consumer phải nhận ra **lỗ hổng phiên bản** (version gap) và không được xem mọi sự kiện khác `eventId` là hợp lệ để áp dụng ngay.

## 2. Phân biệt các loại định danh và phiên bản

### 2.1. Bốn trường quan trọng

Một sự kiện miền (domain event) nên có những thông tin tối thiểu sau:

```json
{
  "eventId": "f8306bd6-c42a-4dd8-9d0a-a1e9f470f400",
  "eventType": "StockAdjusted",
  "schemaVersion": 1,
  "aggregateId": "45e97524-4553-4849-8301-1102bda4fdf6",
  "aggregateVersion": 12,
  "occurredAt": "2026-11-20T08:15:30Z",
  "data": {
    "delta": -3
  }
}
```

| Trường | Câu hỏi trả lời | Quy tắc |
|---|---|---|
| `eventId` | Đây là lần thay đổi/event logic nào? | **Giữ nguyên** khi relay retry hoặc broker redeliver; dùng chống xử lý trùng |
| `aggregateId` | Sự kiện thuộc đối tượng nghiệp vụ nào? | Căn cứ để xét thứ tự **trong cùng một aggregate** |
| `aggregateVersion` | Sau thay đổi này, aggregate đang ở phiên bản mấy? | Tăng **đơn điệu theo aggregate** trong transaction nghiệp vụ; consumer dùng phát hiện gap |
| `schemaVersion` | Payload tuân theo cấu trúc dữ liệu phiên bản nào? | Dùng để parse/migrate JSON; **không** phản ánh thứ tự sự kiện |

`occurredAt` hỗ trợ vận hành, truy vết và đo trễ nhưng **không thay `aggregateVersion` để sắp thứ tự**: đồng hồ các máy có thể lệch, timestamp có thể trùng nhau, thời điểm tạo object Java khác thời điểm DB commit.

Ví dụ: `schemaVersion=2` và `aggregateVersion=37` có nghĩa **định dạng message ở bản 2** nhưng **đối tượng nghiệp vụ đã thay đổi 37 lần**. Nhầm hai trường này sẽ làm logic gap/dedup sai.

### 2.2. Phạm vi đúng của version

`aggregateVersion` thường chỉ có ý nghĩa **trên một aggregateId**, không phải số thứ tự toàn hệ thống:

```text
Product A:  A(v1) -> A(v2) -> A(v3)
Product B:  B(v1) -> B(v2) -> B(v3)
                    \
                     Có thể xử lý A và B song song
                     nhưng phải kiểm soát thứ tự trong A, trong B
```

Version của A và B có thể trùng nhau hoàn toàn, vì vậy khóa dedup/ordering phải bao gồm `aggregateId`. Đừng so sánh `A(v3)` với `B(v2)` để kết luận B đến trễ.

Quy ước phiên bản là lựa chọn domain:

1. Nếu **mỗi thay đổi trạng thái phát đúng một sự kiện**, version có thể tăng 1 trên mỗi thay đổi.
2. Nếu **một transaction phát nhiều sự kiện cho một aggregate**, chỉ dùng `aggregateVersion` có thể khiến các event cùng version. Khi đó cần thêm `eventSequence` riêng hoặc thiết kế một envelope mang tất cả thay đổi của version đó.
3. Nếu chỉ phát **một phần** thay đổi, version nguồn có thể bỏ qua những bước không phát event; consumer không thể đòi nhận mọi số liên tiếp trừ khi hợp đồng bảo đảm mọi version đều có sự kiện.
4. Nếu dữ liệu được **snapshot/rebuild**, cần xác định version khởi đầu từ snapshot và quy tắc tiếp nhận message cũ.

Trong phần thực hành, ta dùng hợp đồng rõ ràng: **mỗi thao tác điều chỉnh tồn kho phát đúng một sự kiện, version tăng chính xác 1**, bắt đầu từ version 0.

## 3. Vì sao RabbitMQ không tự bảo đảm thứ tự nghiệp vụ?

Một queue RabbitMQ có thứ tự enqueue/delivery theo các quy tắc của broker, nhưng điều đó **không phải cam kết mọi tác dụng phụ ở consumer luôn hoàn tất theo thứ tự phiên bản nghiệp vụ**.

### 3.1. Các nguồn làm đảo thứ tự

| Nguyên nhân | Biểu hiện |
|---|---|
| Nhiều producer/channel | Hai event được tạo theo thứ tự DB nhưng đến exchange từ hai kết nối khác nhau theo thứ tự khác |
| Message relay của transactional outbox chạy song song | Worker gửi v2 trước khi worker đang retry v1 |
| Queue có nhiều consumer | Consumer A nhận v1 nhưng xử lý chậm; consumer B hoàn tất v2 trước |
| `prefetch > 1` và xử lý async | Nhiều delivery chưa ACK; completion hoặc tác dụng phụ có thể lệch thứ tự |
| `basic.nack`/`basic.reject` với requeue | Message thất bại có thể được giao lại sau khi message mới hơn đã được xử lý |
| TTL, retry queue, dead-letter và replay DLQ | Message cũ quay về queue làm việc sau một khoảng trễ |
| Message priority, chuyển queue hoặc restart | Thứ tự delivery có thể khác FIFO đơn giản |
| Network timeout và publisher retry | Một publish cũ có thể được gửi lại sau publish mới; gây duplicate hoặc đến muộn |

Một queue duy nhất và một consumer xử lý tuần tự làm giảm mạnh nguy cơ đảo thứ tự **ở đường delivery bình thường**. Tuy nhiên, cần xử lý redelivery, duplicate, khôi phục sau lỗi và thứ tự phát từ phía producer. Tối ưu hiệu năng bằng nhiều consumer thường làm yêu cầu thứ tự trở thành bài toán cần giải ở tầng ứng dụng.

### 3.2. Single Active Consumer và phân vùng theo khóa

RabbitMQ có cơ chế **Single Active Consumer (SAC)**: một queue có nhiều consumer đăng ký nhưng tại một thời điểm broker chọn một consumer đang active để nhận delivery. Cấu hình queue có thể dùng argument `x-single-active-consumer=true` khi tạo queue:

```java
Queue ordered = QueueBuilder.durable("stock.adjusted.serial")
        .withArgument("x-single-active-consumer", true)
        .build();
```

SAC có ích khi cần serialize tiêu thụ của **một queue**, nhưng không bảo đảm message **được publish** theo version đúng hoặc ngăn callback của listener tự đẩy việc xử lý sang nhiều thread và hoàn tất lệch thứ tự. Ngoài ra, requeue/replay vẫn đòi idempotency.

Khi cần mở rộng throughput đồng thời giữ thứ tự **theo sản phẩm**, có thể chia message vào các queue/partition ổn định theo `hash(aggregateId) % N`, xử lý tuần tự từng partition, hoặc dùng một routing layer bảo đảm cùng key vào cùng queue. Việc thay N, chuyển partition, failover và nhiều producer đều cần chính sách tương ứng. Phân vùng là **tối ưu luồng**, còn đối chiếu `aggregateVersion` là **bảo vệ tính đúng đắn**.

## 4. Phát hành version đúng dưới cập nhật đồng thời

### 4.1. Không tăng version chỉ bằng biến Java

Giả sử hai instance cùng đọc version 7 và đều thực hiện:

```java
long nextVersion = currentVersion + 1; // cả hai cùng tính ra 8
rabbitTemplate.convertAndSend("stock.events", "stock.adjusted", ...);
```

Hai message khác nhau cùng mang `aggregateVersion=8`. Consumer lúc này không thể xác định thứ tự đúng chỉ từ version; đó là **xung đột phiên bản nguồn**.

Version phải gắn với **transaction commit** của trạng thái nguồn. Thực tế thường dùng optimistic locking (`UPDATE ... WHERE version = expectedVersion`), row lock (`SELECT ... FOR UPDATE`), hoặc event store có unique constraint trên `(aggregate_id, sequence)`.

### 4.2. Ví dụ PostgreSQL: atomic update và outbox

Ta có một bảng nguồn và bảng outbox. Mỗi cập nhật thành công chỉ tăng version một lần:

```sql
CREATE TABLE stock_source (
    product_id         uuid PRIMARY KEY,
    quantity           bigint NOT NULL,
    aggregate_version  bigint NOT NULL DEFAULT 0,
    CONSTRAINT stock_quantity_nonnegative CHECK (quantity >= 0)
);

CREATE TABLE stock_outbox (
    event_id           uuid PRIMARY KEY,
    aggregate_id       uuid NOT NULL,
    aggregate_version  bigint NOT NULL,
    event_type         varchar(100) NOT NULL,
    schema_version     integer NOT NULL,
    payload            jsonb NOT NULL,
    status             varchar(20) NOT NULL DEFAULT 'NEW',
    created_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (aggregate_id, aggregate_version)
);
```

Unique constraint `(aggregate_id, aggregate_version)` phù hợp với **hợp đồng một sự kiện cho mỗi thay đổi** ở bài này; nếu dự án cho phép nhiều event cùng version phải thiết kế thêm sequence/event ordinal thay vì sao chép constraint nguyên xi.

Payload Java:

```java
public record StockAdjusted(
        UUID eventId,
        UUID productId,
        long aggregateVersion,
        long delta,
        Instant occurredAt) {
}
```

Code service thực hiện update có kiểm tra version và ghi outbox trong **cùng transaction database**:

```java
@Service
public class StockCommandService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public StockCommandService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @Transactional
    public StockAdjusted adjust(
            UUID productId, long expectedVersion, long delta) {

        int updated = jdbc.update("""
            UPDATE stock_source
            SET quantity = quantity + ?,
                aggregate_version = aggregate_version + 1
            WHERE product_id = ?
              AND aggregate_version = ?
              AND quantity + ? >= 0
            """,
            delta, productId, expectedVersion, delta);

        if (updated != 1) {
            throw new OptimisticLockingFailureException(
                    "Version đã thay đổi hoặc điều chỉnh không hợp lệ");
        }

        StockAdjusted event = new StockAdjusted(
                UUID.randomUUID(), productId,
                expectedVersion + 1, delta, Instant.now());

        try {
            jdbc.update("""
                INSERT INTO stock_outbox (
                    event_id, aggregate_id, aggregate_version,
                    event_type, schema_version, payload
                )
                VALUES (?, ?, ?, 'StockAdjusted', 1, CAST(? AS jsonb))
                """,
                event.eventId(),
                event.productId(),
                event.aggregateVersion(),
                mapper.writeValueAsString(event));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Không tạo được JSON event", ex);
        }

        return event;
    }
}
```

Các import chính: `java.util.UUID`, `java.time.Instant`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.dao.OptimisticLockingFailureException`, `org.springframework.stereotype.Service`, `com.fasterxml.jackson.databind.ObjectMapper` và `com.fasterxml.jackson.core.JsonProcessingException`.

Với hai request đều kỳ vọng version 7:

- Transaction A update được một row, tạo event version 8 và ghi outbox.
- Transaction B không cập nhật được row vì version nguồn đã đổi; B rollback và phải đọc lại trạng thái mới trước khi quyết định thử lại, **không tự publish một event version 8 khác**.
- Nếu việc insert outbox lỗi, cả update quantity lẫn version đều rollback.
- Message relay chỉ publish các outbox row **đã commit**, giữ nguyên `eventId` và `aggregateVersion` qua mọi lần retry.

**Ghi chú:** Nếu transaction có thể cập nhật state nhưng không tạo event vì điều kiện khác, hợp đồng “mỗi version có đúng một event” phải được giữ nhất quán. Version không thể tự lấp các sự kiện mà producer cố tình không phát.

### 4.3. Không dùng thứ tự của ID hoặc timestamp thay version

`UUID.randomUUID()` không thể dùng để suy thứ tự. Timestamp `occurredAt` có thể bị clock skew, trùng nhau hoặc được tạo trước commit. Ngay cả sequence ID toàn cục do database cấp cũng không nhất thiết phản ánh **thứ tự commit** khi nhiều transaction cạnh tranh. Cần định nghĩa rõ thứ tự **theo aggregate** ở nguồn và cưỡng chế nó bằng transaction/locking.

## 5. Thuật toán phát hiện duplicate, gap và conflict ở consumer

Consumer duy trì `lastAppliedVersion` cho từng `aggregateId`. Khi nhận message version `v`, so với phiên bản cuối đã áp dụng `last`:

| Điều kiện | Phân loại | Hành động an toàn |
|---|---|---|
| `v == last + 1` | Đúng phiên bản tiếp theo | Áp dụng sự kiện, lưu version mới và dấu vết event trong **một DB transaction** |
| `v > last + 1` | **Gap / đến trước** | Lưu vào **pending store bền vững** hoặc defer có backoff; không áp dụng nếu cần tuần tự |
| `v <= last` và event/version đã xử lý khớp | **Duplicate hoặc late arrival** | Bỏ qua tác dụng phụ và ACK |
| `v <= last` nhưng event ID/payload không khớp lịch sử cùng version | **Conflict** | Báo động/cách ly; không âm thầm ACK như duplicate hợp lệ |
| `v == last + 1` nhưng payload/schema sai | **Invalid/poison event** | Không tăng version; retry/DLQ theo chính sách |
| `aggregateId` chưa có state/snapshot | **Thiếu baseline** | Tạo state ban đầu đã định nghĩa hoặc yêu cầu snapshot, không giả định v1 là hợp lệ cho mọi aggregate |

Để tránh nhầm lẫn, **`eventId` và `aggregateVersion` là hai trục khác nhau**. Một event có thể bị gửi lại với cùng ID; hai event khác ID nhưng cùng aggregate version lại là mâu thuẫn theo hợp đồng bài này.

Đoạn pseudocode cốt lõi:

```text
handle(event):
    lock state của event.aggregateId
    last = state.lastAppliedVersion

    if event.version <= last:
        kiểm tra applied ledger và eventId
        nếu trùng hợp lệ: return SUCCESS
        nếu mâu thuẫn: quarantine / alert

    else:
        lưu event vào pending bền vững, kiểm tra trùng version
        while tồn tại pending event có version = last + 1:
            apply domain change
            lưu eventId + version vào applied ledger
            xóa pending vừa áp dụng
            last = last + 1

    commit DB transaction
    ACK delivery sau khi commit thành công
```

**Vì sao phải lock state?** Nếu hai listener cùng đọc `last=4`, một listener áp dụng v5 còn listener kia xử lý v6 hoặc v5 khác, các thao tác phải được serialize theo aggregate. Có thể dùng `SELECT ... FOR UPDATE` trong PostgreSQL hoặc optimistic compare-and-swap với retry. Chỉ để một biến `ConcurrentHashMap<UUID, Long>` trong JVM không đủ khi có nhiều replicas và không bền sau restart.

## 6. Hai chiến lược khi gặp một khoảng trống phiên bản

### 6.1. Giữ message ở broker và retry có delay

Khi nhận `v=9` nhưng `last=7`, consumer có thể báo lỗi có kiểm soát để message thử lại sau đó. **Không nên `basicNack(requeue=true)` liên tục**: message có thể được giao lại ngay trong vòng nóng, làm tăng CPU và cản trở các message khác.

Nếu dùng retry queue với TTL + DLX hoặc application republish:

- Giới hạn tổng số lần retry và dùng backoff.
- Giữ nguyên `eventId` và `aggregateVersion` khi publish lại.
- Đảm bảo message v8 bị thiếu có cơ hội đến consumer.
- Sau deadline, đưa sự kiện vào parking queue/đầu mối điều tra, **không coi nó là đã áp dụng**.
- Theo dõi việc requeue/republish có thể làm đảo thứ tự nhiều hơn, không được mặc định rằng retry tự giải quyết ordering.

**Lưu ý:** Cần cân nhắc ACK của delivery nguồn khi republish, publisher confirms/returns và tính idempotent. Trong lúc publish thành công nhưng ACK thất bại có thể có nhiều bản cùng event.

### 6.2. Lưu event đến trước vào pending store của consumer

Thay vì retry vô hạn ở RabbitMQ, consumer có thể **ghi event tới sớm vào DB** như một sự kiện `PENDING` rồi ACK delivery nguồn sau khi commit DB. Khi version thiếu xuất hiện, consumer xử lý tất cả pending liên tiếp.

Ưu điểm: tránh nóng queue; message v9 không phải giữ broker unacked trong thời gian dài. Nhược điểm: phải vận hành **pending store**, giám sát những gap không được lấp, giới hạn backlog và có cơ chế đối soát/replay.

Ví dụ:

```text
last = 4
nhận v6   -> lưu PENDING(v6), ACK
nhận v7   -> lưu PENDING(v7), ACK
nhận v5   -> apply(v5), apply(v6), apply(v7), commit, ACK
nhận lại v6 -> lookup applied ledger, bỏ qua, ACK
```

**Điểm không thể bỏ:** Nếu chỉ giữ v6/v7 trong RAM rồi ACK, ứng dụng crash sẽ làm mất chúng. Cần ghi pending trong **transaction DB** và chỉ ACK sau commit.

Phần tiếp theo xây chiến lược pending bền vững bằng Java và Spring AMQP.

## 7. Ví dụ end-to-end: consumer lưu pending và áp dụng theo version

Chúng ta xử lý `StockAdjusted` từ `RabbitTemplate` qua exchange `stock.events` và queue `stock.projector`. Consumer ghi projection tồn kho trong PostgreSQL và dùng bảng pending/applied để phát hiện out-of-order, duplicate và conflict.

### 7.1. Schema cho projection, pending và applied ledger

```sql
CREATE TABLE stock_projection (
    product_id    uuid PRIMARY KEY,
    quantity      bigint NOT NULL DEFAULT 0,
    last_version  bigint NOT NULL DEFAULT 0
);

CREATE TABLE stock_pending_events (
    product_id         uuid NOT NULL,
    aggregate_version  bigint NOT NULL,
    event_id           uuid NOT NULL UNIQUE,
    delta              bigint NOT NULL,
    received_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, aggregate_version)
);

CREATE TABLE stock_applied_events (
    product_id         uuid NOT NULL,
    aggregate_version  bigint NOT NULL,
    event_id           uuid NOT NULL UNIQUE,
    applied_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, aggregate_version)
);

CREATE INDEX stock_pending_oldest_idx
    ON stock_pending_events (received_at, product_id);
```

- `stock_projection.last_version` lưu **version đã thực sự áp dụng**, không phải version lớn nhất từng nhìn thấy.
- `stock_pending_events` giữ payload tối thiểu đủ để áp dụng khi gap được lấp.
- `stock_applied_events` lưu cặp version/event ID đã áp dụng, giúp phát hiện redelivery hợp lệ và xung đột từ producer.
- Unique key ngăn hai sự kiện khác nhau cùng `aggregateId + aggregateVersion` xuất hiện như hai pending events “hợp lệ”.
- Khi dọn bảng applied vì retention, không thể phát hiện mọi xung đột lịch sử; cần quy tắc snapshot/compaction và phạm vi dedup rõ ràng.

Trong hệ thống thật, bổ sung `eventType`, `schemaVersion`, checksum/payload, original headers và trạng thái điều tra để phát hiện xung đột dữ liệu kể cả khi event ID được tái sử dụng sai. Ví dụ này tập trung vào đúng cấu trúc `StockAdjusted` gồm ID/version/delta.

### 7.2. Code lưu event đến trước và drain các version liên tiếp

Phương thức dưới đây giữ lock trên `stock_projection` của **một sản phẩm**; nhiều sản phẩm vẫn có thể được xử lý đồng thời. Cả insert pending, apply delta, ghi applied ledger và cập nhật version diễn ra trong một DB transaction.

```java
@Service
public class StockProjectionService {
    private final JdbcTemplate jdbc;

    public StockProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private record Pending(UUID eventId, long delta) {}

    @Transactional
    public void accept(StockAdjusted event) {
        if (event.eventId() == null
                || event.productId() == null
                || event.aggregateVersion() < 1) {
            throw new IllegalArgumentException("Event thiếu ID/version");
        }

        // Tạo dòng state ban đầu; không tự thay đổi version nếu đã tồn tại.
        jdbc.update("""
            INSERT INTO stock_projection (product_id, quantity, last_version)
            VALUES (?, 0, 0)
            ON CONFLICT (product_id) DO NOTHING
            """, event.productId());

        // Serialize consumer cùng aggregate qua row lock của PostgreSQL.
        Long last = jdbc.queryForObject("""
            SELECT last_version
            FROM stock_projection
            WHERE product_id = ?
            FOR UPDATE
            """, Long.class, event.productId());

        if (last == null) {
            throw new IllegalStateException("Không tìm thấy projection");
        }

        if (event.aggregateVersion() <= last) {
            List<UUID> previouslyApplied = jdbc.query("""
                SELECT event_id
                FROM stock_applied_events
                WHERE product_id = ? AND aggregate_version = ?
                """,
                (rs, n) -> rs.getObject("event_id", UUID.class),
                event.productId(), event.aggregateVersion());

            if (previouslyApplied.size() == 1
                    && previouslyApplied.get(0).equals(event.eventId())) {
                return; // Duplicate/stale hợp lệ: không áp dụng lần thứ hai.
            }
            throw new IllegalStateException(
                    "Xung đột eventId tại version đã áp dụng");
        }

        int inserted = jdbc.update("""
            INSERT INTO stock_pending_events (
                product_id, aggregate_version, event_id, delta
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT DO NOTHING
            """,
            event.productId(), event.aggregateVersion(),
            event.eventId(), event.delta());

        if (inserted == 0) {
            List<Pending> existing = jdbc.query("""
                SELECT event_id, delta
                FROM stock_pending_events
                WHERE product_id = ? AND aggregate_version = ?
                """,
                (rs, n) -> new Pending(
                        rs.getObject("event_id", UUID.class),
                        rs.getLong("delta")),
                event.productId(), event.aggregateVersion());

            if (existing.size() != 1
                    || !existing.get(0).eventId().equals(event.eventId())
                    || existing.get(0).delta() != event.delta()) {
                throw new IllegalStateException(
                        "Hai nội dung khác nhau tại cùng một version");
            }
        }

        long next = last + 1;
        while (true) {
            List<Pending> ready = jdbc.query("""
                SELECT event_id, delta
                FROM stock_pending_events
                WHERE product_id = ? AND aggregate_version = ?
                """,
                (rs, n) -> new Pending(
                        rs.getObject("event_id", UUID.class),
                        rs.getLong("delta")),
                event.productId(), next);

            if (ready.isEmpty()) {
                break; // Có gap hoặc đã drain hết các version sẵn có.
            }

            Pending pending = ready.get(0);

            jdbc.update("""
                UPDATE stock_projection
                SET quantity = quantity + ?,
                    last_version = ?
                WHERE product_id = ?
                """, pending.delta(), next, event.productId());

            jdbc.update("""
                INSERT INTO stock_applied_events (
                    product_id, aggregate_version, event_id
                )
                VALUES (?, ?, ?)
                """, event.productId(), next, pending.eventId());

            jdbc.update("""
                DELETE FROM stock_pending_events
                WHERE product_id = ? AND aggregate_version = ?
                """, event.productId(), next);

            next++;
        }
    }
}
```

Các import chính: `java.util.UUID`, `java.util.List`, `org.springframework.jdbc.core.JdbcTemplate`, `org.springframework.stereotype.Service` và `org.springframework.transaction.annotation.Transactional`.

Với event v3 đến trước v1, `stock_pending_events` lưu v3 và `last_version` vẫn bằng 0. Khi v1 đến, nó được áp dụng; nếu v2 chưa tới, v3 vẫn nằm pending. Khi v2 tới, vòng `while` áp dụng lần lượt v2 rồi v3 trong **cùng DB transaction**, bất kể thứ tự delivery ban đầu.

**Tại sao không cập nhật `last_version = max(last_version, v)`?** Làm vậy khi nhận v3 trước v1 sẽ ghi last=3, khiến consumer coi v1/v2 là stale; projection mất các thay đổi còn thiếu. Version chỉ được tăng **sau khi áp dụng đủ sự kiện liền trước**.

**Điểm cần điều chỉnh trong hệ thống thực:** Hàm `while` có thể drain quá nhiều sự kiện pending trong một transaction dài. Nên giới hạn batch/transaction, dùng cơ chế tiếp tục xử lý khi còn pending, phân loại những sự kiện có validation lỗi và theo dõi lock contention. Ví dụ cố ý đơn giản để quan sát tính đúng đắn.

### 7.3. Rabbit topology và listener Spring AMQP

```java
@Configuration
@EnableRabbit
public class StockProjectionAmqpConfig {

    @Bean
    Declarables stockTopology() {
        DirectExchange input = new DirectExchange("stock.events");
        DirectExchange deadExchange = new DirectExchange("stock.dlx");

        Queue work = QueueBuilder.durable("stock.projector")
                .deadLetterExchange("stock.dlx")
                .deadLetterRoutingKey("stock.failed")
                .build();

        Queue dead = QueueBuilder.durable("stock.projector.dead").build();

        return new Declarables(
                input, deadExchange, work, dead,
                BindingBuilder.bind(work)
                        .to(input).with("stock.adjusted"),
                BindingBuilder.bind(dead)
                        .to(deadExchange).with("stock.failed"));
    }

    @Bean("stockListenerFactory")
    SimpleRabbitListenerContainerFactory stockListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();

        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.AUTO);
        factory.setConcurrentConsumers(4);
        factory.setMaxConcurrentConsumers(8);
        factory.setPrefetchCount(16);
        factory.setDefaultRequeueRejected(false);
        return factory;
    }
}
```

```java
@Component
public class StockProjectionListener {
    private final ObjectMapper mapper;
    private final StockProjectionService projection;

    public StockProjectionListener(
            ObjectMapper mapper, StockProjectionService projection) {
        this.mapper = mapper;
        this.projection = projection;
    }

    @RabbitListener(
            queues = "stock.projector",
            containerFactory = "stockListenerFactory")
    public void consume(Message message) throws JsonProcessingException {
        StockAdjusted event =
                mapper.readValue(message.getBody(), StockAdjusted.class);
        projection.accept(event);
    }
}
```

Các kiểu cần import: `org.springframework.amqp.core.*`, `org.springframework.amqp.rabbit.annotation.EnableRabbit`, `org.springframework.amqp.rabbit.annotation.RabbitListener`, `org.springframework.amqp.rabbit.connection.ConnectionFactory`, `org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.stereotype.Component`, `com.fasterxml.jackson.databind.ObjectMapper`, `com.fasterxml.jackson.core.JsonProcessingException`.

**Điểm quan trọng về acknowledgment:** Khi `StockProjectionService.accept` đi qua Spring proxy và **commit DB thành công**, listener trả về bình thường và container ở `AUTO` mode có thể ACK message. Nếu DB lỗi và ném exception lên listener, container xử lý fail/reject tùy cấu hình. ACK của RabbitMQ **không nằm trong một transaction nguyên tử** với PostgreSQL; sau commit DB nhưng trước ACK, crash có thể khiến message được giao lại. `stock_applied_events` và pending unique keys làm việc replay an toàn.

Trong ví dụ, `defaultRequeueRejected(false)` ngăn requeue nóng cho lỗi không xử lý được; với DLX hợp lệ, message có thể vào `stock.projector.dead`. Để dùng trong production, cần **retry hữu hạn có backoff cho lỗi DB tạm thời**, phân biệt poison/conflict với lỗi hạ tầng, và quy trình điều tra DLQ. Một event gap **không bị reject** trong code này: nó được lưu bền vững rồi ACK.

### 7.4. Mặt phát event dùng RabbitTemplate

Relay lấy JSON từ outbox đã commit và gửi với cùng event ID qua mọi lần retry:

```java
rabbitTemplate.convertAndSend(
        "stock.events",
        "stock.adjusted",
        jsonPayload,
        msg -> {
            msg.getMessageProperties().setMessageId(eventId.toString());
            msg.getMessageProperties()
                    .setContentType(MessageProperties.CONTENT_TYPE_JSON);
            msg.getMessageProperties()
                    .setDeliveryMode(MessageDeliveryMode.PERSISTENT);
            return msg;
        });
```

Đây là **đoạn minh họa publish**. Khi triển khai relay thật, cần publisher confirms, mandatory returns khi có nguy cơ unroutable, retry và chỉ đánh dấu outbox `SENT` sau khi publish được xác nhận phù hợp. `convertAndSend` trả về bình thường **không bảo đảm** message đã đến queue đích; timeout confirm cũng không chứng minh broker chưa nhận message. Retry vì thế phải giữ `eventId`/`aggregateVersion` ổn định.

## 8. Khôi phục khi phiên bản bị thiếu quá lâu

Lưu event tới sớm vào pending store giải quyết việc **đến sai thứ tự tạm thời**. Nhưng nếu v5 thực sự bị mất, các event v6, v7, ... có thể mắc kẹt lâu dài.

Một quy trình vận hành cần có:

1. **Phát hiện gap:** tìm product có pending version nhỏ nhất `min_pending_version > last_version + 1`.
2. **Theo dõi tuổi gap:** đo từ `received_at` đầu tiên và phát cảnh báo nếu vượt SLA, ví dụ nhiều phút tùy nghiệp vụ.
3. **Đối soát với nguồn:** query event store hoặc outbox nguồn theo `aggregateId` và version bị thiếu, so sánh `eventId`/checksum. Nếu nguồn có sự kiện v5, replay đúng sự kiện gốc với cùng ID.
4. **Sử dụng snapshot có version khi cần:** nếu event lịch sử đã được compact, lấy snapshot có revision được xác nhận, cập nhật projection theo quy tắc reconciliation rồi chỉ drain pending version sau snapshot.
5. **Cách ly xung đột:** nếu cùng aggregate/version xuất hiện hai payload khác nhau, dừng áp dụng trên aggregate đó và điều tra; không chọn ngẫu nhiên message “đến sau” hoặc “đến trước”.
6. **Giới hạn tài nguyên:** đặt quota số pending events và thời gian lưu; vượt ngưỡng phải cảnh báo/backpressure, không xóa im lặng.

SQL kiểm tra gap minh họa cho PostgreSQL:

```sql
SELECT
    p.product_id,
    p.last_version,
    MIN(e.aggregate_version) AS first_pending_version,
    MIN(e.received_at) AS oldest_pending_at
FROM stock_projection p
JOIN stock_pending_events e
    ON e.product_id = p.product_id
GROUP BY p.product_id, p.last_version
HAVING MIN(e.aggregate_version) > p.last_version + 1
ORDER BY oldest_pending_at;
```

Một số event pending có thể đến đủ version nhưng chưa được drain vì lần trước gặp lỗi DB; cần thêm kiểm tra `MIN(aggregate_version) = last_version + 1` để tự kích hoạt drain lại, thay vì chỉ cảnh báo thiếu event.

## 9. Không phải mọi loại event đều cần buffer nghiêm ngặt

Việc chọn chiến lược phụ thuộc **ngữ nghĩa payload**, không chỉ phiên bản:

| Kiểu sự kiện | Ví dụ | Cách xử lý thường thích hợp |
|---|---|---|
| **Delta / command-result phụ thuộc trước đó** | `StockAdjusted(delta=-3)` | Áp dụng version liên tiếp; buffer gap |
| **Snapshot đầy đủ, latest-state-wins** | `ProductProfileSnapshot(version=12, fullState=...)` | Có thể bỏ snapshot version thấp hơn và áp dụng version cao nhất nếu hợp đồng cho phép |
| **Event state-machine** | `OrderPaid`, `OrderCancelled` | Kiểm tra transition + version; buffer/reconcile khi gap |
| **Sự kiện độc lập, giao hoán** | `ViewCountIncrement` có event ID riêng | Có thể xử lý khác thứ tự, nhưng vẫn dedup theo event ID |
| **Sự kiện đa aggregate** | Chuyển tiền giữa hai tài khoản | Version riêng từng aggregate **chưa đủ** mô tả một thứ tự toàn hệ thống; cần transaction/workflow và liên kết correlation |

Ví dụ với snapshot đầy đủ, nếu consumer nhận v7 sau khi đã áp dụng snapshot v8, có thể bỏ qua v7 **nếu** v8 bao trùm mọi trạng thái cần thiết. Nhưng với delta, bỏ v7 khiến projection bị thiếu dữ liệu; không được áp dụng quy tắc latest-wins cho tất cả sự kiện.

Nếu domain có nhiều loại event trong cùng stream, cần xử lý `eventType`, payload schema và các transition hợp lệ; chỉ nhìn `aggregateVersion` có thể chưa đủ.

## 10. Retry, DLQ và ordering: cần điều phối đồng thời

### 10.1. Sự kiện đến muộn khác với sự kiện hỏng

**Gap** nghĩa là có event hợp lệ nhưng đang thiếu phiên bản trước; **poison** nghĩa là payload không thể xử lý, schema không hợp lệ, hoặc tạo xung đột version. Hai lỗi cần đường xử lý khác nhau:

- Gap tạm thời: buffer bền vững hoặc delayed retry; không liên tục requeue nóng.
- Database tạm hỏng: retry có giới hạn/backoff; giữ idempotency; nếu hết retry cần cảnh báo/parking.
- Event không hợp đồng: đưa vào DLQ/quarantine kèm metadata, không tăng `last_version`.
- Duplicate đã được ghi nhận: ACK bình thường, tăng bộ đếm duplicate.
- Conflict cùng version: cảnh báo mức cao và cần đối soát nguồn, không tự bỏ qua như duplicate.

### 10.2. Không tự động tăng version khi đưa vào DLQ

Giả sử v5 bị chuyển DLQ còn v6/v7 nằm pending. Consumer **không được** “nhảy” `last_version` từ 4 lên 7 chỉ để hết backlog: điều đó làm mất tác dụng của v5 nếu sau này replay. Có thể chọn chính sách skip một sự kiện **sau quyết định nghiệp vụ rõ ràng và audit đầy đủ**, nhưng đó là reconciliation có kiểm soát, không phải xử lý lỗi tự động.

Khi replay từ DLQ, hãy giữ `eventId`, `aggregateId`, `aggregateVersion` nguyên bản, bảo đảm không áp dụng tác dụng phụ lần hai và theo dõi sự kiện từ nguồn đến projection.

## 11. Quan sát đồng thời và thứ tự trong hệ thống

Để biết queue đang đảo thứ tự hay consumer đang xử lý thiếu event, cần kết hợp metrics của Spring AMQP, RabbitMQ và database:

| Metric / dữ liệu | Giải thích |
|---|---|
| `stock_event_gap_total` | Số lần gặp event version vượt `last + 1` |
| `stock_event_duplicate_total` | Số event đã áp dụng bị giao lại |
| `stock_event_conflict_total` | Số mâu thuẫn `eventId`/version hoặc payload |
| `stock_pending_events_count` | Backlog pending chưa áp dụng |
| `stock_oldest_gap_age_seconds` | Khoảng thời gian thiếu phiên bản lâu nhất |
| `stock_projection_version_lag` | Chênh lệch version nguồn mới nhất với projection |
| `stock_projection_apply_latency` | Thời gian từ `occurredAt` đến lúc consumer commit apply |
| `rabbitmq_messages_ready / unacknowledged` | Message ở queue đang đợi hoặc chưa ACK |
| `rabbitmq_redelivered_total` | Số lần giao lại; chỉ báo khả năng duplicate và ordering biến động |
| `spring_listener_processing_time` | Thời gian listener chạy, phụ thuộc DB lock/preload |
| `db_lock_wait_duration` | Cạnh tranh row lock khi nhiều consumer xử lý cùng aggregate |

Log có thể gồm `eventId`, `aggregateId`, `aggregateVersion`, `lastAppliedVersion`, `correlationId` và loại quyết định: `APPLIED`, `BUFFERED`, `DUPLICATE`, `CONFLICT`. Không gán aggregate ID hoặc event ID vào metric label có cardinality cao; dùng structured logs/tracing để tra cứu từng sự kiện.

Một biểu đồ hữu ích là **last applied version theo thời gian**: đối với mỗi aggregate, đường version phải không giảm, không nhảy qua gap chưa được xử lý. Queue throughput cao **không đồng nghĩa** projection đang theo kịp dữ liệu nguồn.

## 12. Bài thực hành kiểm chứng

Dùng PostgreSQL + RabbitMQ + Spring Boot, tạo queue và projection theo mục 7. Test bằng event ID cố định, mỗi event có `aggregateVersion` và delta. Các thao tác quan sát nên kiểm tra **cả database và message ACK/DLQ**, không chỉ log console.

### Thực hành 1 — Thứ tự đúng

Gửi v1(+10), v2(−3), v3(+7) theo thứ tự. Kỳ vọng `stock_projection.quantity=14`, `last_version=3`, bảng pending rỗng, bảng applied có ba event.

### Thực hành 2 — Giao sai thứ tự

Gửi **v2 trước, sau đó v3, rồi v1**. Khi mới nhận v2/v3, DB phải có hai pending row, `last_version=0`. Sau v1, consumer drain v1/v2/v3 và đạt `quantity=14`, `last_version=3`, pending rỗng.

### Thực hành 3 — Giao lại message cũ

Gửi lại đúng v2 với cùng `eventId` và delta. Kỳ vọng listener ACK mà không cập nhật quantity/version lần nữa; metric duplicate tăng.

### Thực hành 4 — Mâu thuẫn version

Gửi một event khác có cùng `aggregateId`/version 2 nhưng `eventId` khác. Consumer phải phát hiện conflict, không thay thế event đã áp dụng và không sửa projection; message đi theo chính sách quarantine/DLQ, log có correlation để điều tra.

### Thực hành 5 — Xử lý đồng thời

Cấu hình nhiều consumer và `prefetchCount>1`. Publish v1..v100 nhưng chủ động làm chậm một số message. Kỳ vọng version projection **không vượt quá các version liên tiếp đã áp dụng**. Khi các gap cuối cùng được lấp, projection đạt version 100; quan sát tăng lock waits và thời gian pending.

### Thực hành 6 — Crash sau commit nhưng trước ACK

Cho `StockProjectionService.accept` commit DB thành công rồi mô phỏng mất connection/channel trước khi ACK. Sau broker redelivery, unique ledger phải khiến event được nhận dạng là duplicate; không tăng quantity hai lần.

### Thực hành 7 — Phiên bản vĩnh viễn bị thiếu

Gửi v1 và v3 nhưng cố ý không gửi v2. Consumer giữ v3 pending, `last_version` dừng ở 1. Sau ngưỡng SLA, cảnh báo gap xuất hiện. Replay v2 từ outbox/event store nguồn với **cùng event ID**, projection drain tiếp tới v3.

### Thực hành 8 — Kiểm tra optimistic locking ở producer

Hai thread gọi `StockCommandService.adjust` với cùng `expectedVersion`. Chỉ một thao tác cập nhật và insert outbox thành công ở phiên bản kế tiếp; thao tác còn lại phải đọc lại trạng thái rồi retry nếu hợp lệ. Không được tạo hai sự kiện khác nhau cùng `(aggregateId, aggregateVersion)`.

**Tiêu chí đạt:** Version nguồn tăng theo transaction commit; consumer không apply vượt gap; duplicate không tạo tác dụng phụ; conflict được quan sát/cách ly; restart và redelivery không làm sai projection; gap quá hạn có đường đối soát.

## 13. Những nhầm lẫn thường gặp

- **“Queue FIFO nên không cần version.”** FIFO không tự giải quyết concurrent publishers, consumers, retries, delayed deliveries và thứ tự tác dụng phụ.
- **“`eventId` là số thứ tự.”** UUID định danh một event; không mô tả thứ tự thay đổi theo aggregate.
- **“`schemaVersion` chính là `aggregateVersion`.”** Schema version dùng diễn giải payload; aggregate version dùng kiểm tra thứ tự state transitions.
- **“Đến v10 thì cứ đặt `lastVersion=10`.”** Nếu event là delta, làm vậy có thể bỏ mất tác dụng của các phiên bản chưa đến.
- **“Gặp gap, cứ NACK requeue ngay đến khi hết.”** Dễ tạo retry loop nóng; không bảo đảm message thiếu sẽ đến đúng lúc.
- **“Lưu pending trong memory rồi ACK là an toàn.”** Process crash sẽ làm mất event đã ACK. Pending phải được commit bền vững trước ACK.
- **“Cùng version nhưng eventId khác vẫn là duplicate.”** Với hợp đồng một event cho mỗi version, đó là conflict cần điều tra.
- **“Publisher confirm ACK nghĩa là consumer đã xử lý đúng thứ tự.”** Confirm chỉ phản ánh broker xử lý publish, không phải commit DB downstream.
- **“Một thread listener đủ để có exactly-once.”** Sau broker crash/connection loss, event vẫn có thể được redeliver; idempotent consumer luôn cần.
- **“Event timestamp đủ để tái tạo thứ tự.”** Đồng hồ không tạo ra thứ tự commit đáng tin cậy trên nhiều máy.

## 14. Câu hỏi tự kiểm tra

1. Sự khác nhau giữa `eventId`, `aggregateVersion` và `schemaVersion` là gì?
2. Nếu `lastVersion=5` và nhận `v=7`, consumer có nên áp dụng ngay không? Trường hợp nào ngoại lệ?
3. Nếu đã áp dụng `v=7` rồi nhận lại chính event v6, làm sao phân biệt duplicate hợp lệ với conflict?
4. Vì sao hai event cùng aggregate có thể đến khác thứ tự mặc dù đều đi qua một RabbitMQ exchange?
5. Làm thế nào để hai producer không tự phát hai event khác nhau cùng version 8?
6. Vì sao cần đặt insert pending, apply projection và ghi applied ledger vào cùng DB transaction?
7. Sau DB commit nhưng trước RabbitMQ ACK, mất kết nối có hậu quả gì và cơ chế nào xử lý?
8. Nếu version 4 mãi không đến, có nên tự tăng `lastVersion` từ 3 lên 5 để giải phóng pending không?

**Đáp án gợi ý:** (1) ID xác định sự kiện; aggregateVersion xác định thứ tự trạng thái theo aggregate; schemaVersion mô tả định dạng payload. (2) Không với delta/state-machine cần thứ tự, có thể với full snapshot latest-wins theo hợp đồng. (3) Đối chiếu ledger version/eventId. (4) Nhiều publisher, queue/consumer song song, retry/requeue/TTL. (5) Cập nhật source bằng optimistic lock/transaction và outbox chung DB. (6) Tránh trạng thái pending/applied không nhất quán khi crash. (7) Có thể redelivery, consumer phải idempotent. (8) Không, chỉ reconciliation có quyết định nghiệp vụ/audit mới cho phép skip.

## 15. Tổng kết

**Version sự kiện** là công cụ để kiểm tra thứ tự **theo aggregate**, trong khi `eventId` dùng nhận diện bản trùng và `schemaVersion` dùng mô tả cấu trúc message. Producer phải sinh version trong transaction cập nhật trạng thái, lý tưởng là ghi outbox cùng transaction để lưu ý định gửi bền vững. RabbitMQ và Spring AMQP giúp chuyển message và ACK/NACK, nhưng các cơ chế này **không tự bảo đảm** tác dụng phụ nghiệp vụ hoàn tất theo thứ tự khi có retry và concurrency.

Consumer cần phát hiện **event đúng tiếp theo, gap, duplicate, conflict**, lưu pending bền vững hoặc retry với backoff, chỉ tăng `lastAppliedVersion` khi các event được áp dụng liên tiếp trong một DB transaction. Để xây hệ thống bất đồng bộ đáng tin cậy, hãy kết hợp versioning, idempotency, giới hạn song song theo khóa, DLQ/reconciliation và quan sát backlog/gap theo SLA.

### Tài liệu tham khảo

- [RabbitMQ — Queues](https://www.rabbitmq.com/docs/queues): đặc tính thứ tự và các trường hợp nhiều consumer/requeue ảnh hưởng đến delivery.
- [RabbitMQ — Consumers](https://www.rabbitmq.com/docs/consumers): consumer acknowledgements, Single Active Consumer, xử lý delivery.
- [RabbitMQ — Consumer Acknowledgements and Publisher Confirms](https://www.rabbitmq.com/docs/confirms): phân biệt confirm phía publisher với ACK phía consumer và redelivery.
- [Spring AMQP — Listener Concurrency](https://docs.spring.io/spring-amqp/reference/amqp/listener-concurrency.html): cấu hình `concurrentConsumers`, `maxConcurrentConsumers` và các container.
- [Spring AMQP — Receiving Messages](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages.html): `@RabbitListener`, listener container và cách nhận message.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox): ghi event intent trong DB transaction và vấn đề relay/duplicate.

