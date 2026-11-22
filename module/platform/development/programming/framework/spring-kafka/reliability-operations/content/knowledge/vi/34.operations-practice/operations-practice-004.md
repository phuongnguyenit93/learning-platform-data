# Đồng bộ Kafka với database trong Spring Kafka: transaction, inbox, outbox và phục hồi

## 1. Bài toán thực tế

Một ứng dụng **Spring Kafka** thường không chỉ nhận hoặc gửi message. Nó còn **đọc/ghi database** để cập nhật trạng thái nghiệp vụ. Khi hai hệ thống cùng tham gia một luồng xử lý, câu hỏi quan trọng nhất là:

> Nếu Kafka thành công nhưng database thất bại, hoặc database đã commit nhưng Kafka chưa xác nhận, hệ thống làm thế nào để không mất dữ liệu và không tạo tác dụng nghiệp vụ trùng lặp?

Ví dụ dịch vụ thanh toán nhận một sự kiện `PaymentApproved`:

```text
                    Kafka topic
                 payment-approved
                        |
                        v
                @KafkaListener
                        |
                        v
                PostgreSQL
              payments / ledger
                        |
                        v
               Kafka topic
              payment-completed
```

Trong một lần chạy lý tưởng:

1. Consumer nhận sự kiện từ Kafka.
2. Ứng dụng validate và cập nhật bảng PostgreSQL.
3. Database commit.
4. Consumer commit offset.
5. Ứng dụng gửi sự kiện kết quả sang Kafka.

Nhưng process có thể chết ở **bất kỳ bước nào**. Network timeout cũng không chứng minh thao tác bên kia chưa thành công. Vì thế, triển khai “đồng bộ Kafka với database” không chỉ là thêm `@Transactional` vào listener.

**Mục tiêu của bài:** xây một mô hình dữ liệu và luồng vận hành chịu được retry, replay, rebalance, crash, duplicate và sự cố hạ tầng; đồng thời hiểu giới hạn của những cam kết “exactly once”.

**Phạm vi ví dụ:** Spring Boot 3.x, Spring Kafka 3.x, Java 17+, PostgreSQL, Kafka broker tương thích với stack này. Những đoạn code là các thành phần minh họa cần ghép với cấu hình, DTO và schema tương ứng trong dự án thực tế.

## 2. Ba hướng đồng bộ phải phân biệt

| Hướng | Tình huống | Rủi ro chính | Mẫu thường dùng |
|---|---|---|---|
| **Kafka → Database** | Nhận sự kiện để cập nhật bảng nghiệp vụ | DB commit xong nhưng offset chưa commit → đọc lại | Idempotent consumer + **transactional inbox** |
| **Database → Kafka** | Ghi đơn hàng rồi phát event | DB commit xong nhưng chưa gửi Kafka → mất event | **Transactional outbox** + publisher/CDC |
| **Kafka → Database → Kafka** | Nhận command, lưu trạng thái, phát result | Lỗi ở bất kỳ khoảng giữa ba hệ thống | Inbox + DB transaction + outbox |

Một lời giải có thể đúng cho một hướng nhưng không đủ cho hướng khác. Ví dụ `enable.idempotence=true` cải thiện độ tin cậy của Kafka producer khi gửi lại trong phạm vi client/broker, **không** làm giao dịch PostgreSQL và Kafka trở thành một transaction.

### 2.1. Những kết quả hệ thống cần giữ

Với một sự kiện có `eventId=evt-101`, ta thường muốn:

- **Không mất sự kiện:** nếu nguồn đã chấp nhận event, cuối cùng có đường xử lý hoặc phục hồi nó.
- **Không nhân đôi business effect:** hai lần giao lại `evt-101` không làm cộng tiền hai lần.
- **Có thể restart:** crash giữa chừng không buộc người vận hành sửa tay offset hoặc dữ liệu.
- **Không che xung đột:** cùng event ID nhưng payload khác nhau không được coi là duplicate vô hại.
- **Có khả năng đối soát:** tìm được event đang pending, đã xử lý, đang lỗi hoặc đã phát sang hệ thống khác.
- **Có giới hạn:** lỗi tạm thời retry có kiểm soát, lỗi dữ liệu không retry vô hạn.
- **Có owner vận hành:** biết phải kiểm tra DB, Kafka group, DLT hay outbox khi sự cố xảy ra.

Các yêu cầu cần được ghi thành **business invariants**, không chỉ đánh giá qua một lần listener chạy thành công.

## 3. Vì sao không có atomic commit tự nhiên giữa Kafka và DB?

Kafka quản lý bản ghi, consumer group offsets và Kafka transactions trong hệ thống Kafka. PostgreSQL quản lý các bảng, row locks và transaction qua JDBC/driver. Hai hệ thống có **transaction coordinator và failure domain khác nhau**.

Giả sử mã:

```java
@Transactional
public void process(PaymentEvent event) {
    paymentRepository.apply(event);
    kafkaTemplate.send("payment-completed", event.id(), json);
}
```

`@Transactional` thường gắn với một `PlatformTransactionManager` được chọn, chẳng hạn transaction của datasource PostgreSQL. Nó **không tự biến** việc gửi Kafka thành một phần atomic của transaction JDBC.

Có hai thứ tự dễ gặp, cả hai đều có “khoảng trống”:

**DB trước, Kafka sau:**

```text
DB COMMIT ------------------------> SEND KAFKA
      |                                  |
      +---- process chết ở đây ----------+
               DB có dữ liệu
               Kafka chưa có event
```

**Kafka trước, DB sau:**

```text
SEND KAFKA -----------------------> DB COMMIT
      |                                  |
      +---- process chết ở đây ----------+
             Consumer khác thấy event
             DB chưa cập nhật
```

Nếu hai thao tác xảy ra trong code liên tiếp với độ trễ rất thấp, crash vẫn có thể rơi đúng khoảng đó. Không nên thiết kế theo giả thiết “hai lệnh rất nhanh nên chắc không sao”.

### 3.1. Vì sao Kafka transaction chưa giải quyết DB?

Kafka có **transactional producer** và các cơ chế Kafka-to-Kafka exactly-once processing trong phạm vi hỗ trợ. Nhưng Kafka transaction không tự điều phối atomic commit với PostgreSQL.

Ngay cả khi ứng dụng dùng Kafka transaction và một DB transaction song song, vẫn tồn tại thứ tự commit; nếu commit thứ nhất thành công và commit thứ hai thất bại, chúng có thể lệch. Các cơ chế phối hợp transaction theo thứ tự có thể thu hẹp failure window nhưng **không phải XA/2PC atomicity giữa Kafka và database**.

**Khuyến nghị thực hành:** khi business state nằm trong DB, dùng database làm nguồn sự thật cho effect và một outbox/inbox idempotent để giao tiếp Kafka với mô hình **eventual consistency** đã được định nghĩa.

## 4. Trường hợp 1: Kafka → database

Giả sử topic `payment-approved.v1` có bản ghi:

```json
{
  "eventId": "evt-101",
  "sourceSystem": "payments",
  "paymentId": "pay-701",
  "version": 4,
  "status": "APPROVED"
}
```

Consumer cần cập nhật projection bảng `payment_projection` trong PostgreSQL.

### 4.1. Lỗi thường gặp: DB commit rồi crash trước offset commit

```text
1. KafkaConsumer poll offset 120
2. Listener cập nhật PostgreSQL
3. PostgreSQL COMMIT thành công
4. JVM chết trước Kafka offset commit
5. Rebalance/restart
6. Kafka giao lại offset 120
7. Listener thấy lại event evt-101
```

Đây là hành vi có thể xảy ra khi thiết kế **at-least-once**. Không phải bug Kafka. Muốn đảm bảo business state chỉ thay đổi đúng một lần, consumer phải **idempotent**.

### 4.2. Rủi ro ngược: commit offset trước khi DB hoàn tất

```text
1. KafkaConsumer poll offset 120
2. Offset được commit như đã xử lý
3. Database transaction thất bại
4. JVM chết
5. Restart bắt đầu tại offset 121
6. Event offset 120 có thể bị bỏ qua
```

Vì vậy không nên commit offset/ack trước khi business work đã hoàn tất và transaction DB đã commit, trừ khi có thiết kế riêng bảo đảm event đã được lưu bền vững vào nơi khác.

### 4.3. Nguyên tắc consumer an toàn

Đối với record listener ghi database:

1. Tắt Kafka client auto-commit.
2. Để service xử lý business work trong **một DB transaction**.
3. Chèn một **inbox key** (event ID) và cập nhật dữ liệu nghiệp vụ **trong cùng DB transaction**.
4. Khi DB transaction commit xong, listener mới trả về thành công; container commit offset theo ack policy.
5. Nếu offset commit thất bại, Kafka có thể giao lại; inbox giúp bỏ qua duplicate.
6. Nếu DB transaction thất bại, exception phải được đưa tới Spring Kafka error handler; không ack như thành công.
7. Nếu dữ liệu sai vĩnh viễn, áp dụng DLT/quarantine với quy tắc rõ; không retry vô hạn.

## 5. Cấu hình Spring Kafka consumer cho DB processing

Ví dụ `application.yml` với record listener:

```yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:localhost:9092}

    consumer:
      group-id: payment-projection-v1
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
      auto-offset-reset: earliest
      properties:
        "[max.poll.records]": 100
        "[max.poll.interval.ms]": 300000

    listener:
      ack-mode: record
      concurrency: 3
```

Đây là ví dụ cho **một cluster**, dùng String payload để minh họa. Những giá trị timeout, poll và concurrency cần được đo theo tải thực tế.

Các điểm cần hiểu:

- `enable-auto-commit: false` tắt cơ chế tự commit định kỳ của Kafka client, nhưng Spring Kafka listener container vẫn commit offsets theo **ack mode/error handling**.
- `ack-mode: record` có nghĩa container quản lý commit sau quá trình xử lý record theo semantics của container; listener method chỉ nên trả về bình thường sau khi công việc cần hoàn tất đã xong.
- `auto-offset-reset: earliest` chỉ áp dụng khi group **không có committed offset hợp lệ**; nó không tự reset group sau mỗi restart.
- `concurrency: 3` không đảm bảo ba records cùng partition được xử lý song song hoặc tăng throughput lên ba lần; phân phối phụ thuộc số partition và assignment.
- `max.poll.interval.ms` phải được tính với thời gian listener có thể bị block/retry; xử lý quá lâu có thể gây rebalance.
- Với record được ghi bởi **Kafka transactional producer**, có thể chọn `isolation.level=read_committed` nếu yêu cầu không đọc aborted transactions; nó không ảnh hưởng atomicity với DB.

### 5.1. Vì sao listener không nên nuốt exception?

Sai:

```java
@KafkaListener(topics = "payment-approved.v1")
public void onEvent(String json) {
    try {
        service.process(json);
    } catch (Exception ex) {
        log.error("Processing failed", ex);
        // Trả về bình thường: container có thể coi là xử lý thành công.
    }
}
```

Nếu business effect chưa commit nhưng listener trả thành công, offset có thể được commit theo policy và event bị mất về mặt nghiệp vụ.

Cách đúng là **để exception đi tới error handler**, hoặc có một cơ chế recover bền vững và chỉ coi record hoàn tất khi recovery đã được xác nhận:

```java
@KafkaListener(topics = "payment-approved.v1")
public void onEvent(String json) throws Exception {
    PaymentEvent event = mapper.readValue(
            json, PaymentEvent.class);

    service.applyEvent(event);
    // Return chỉ sau khi service transaction đã hoàn tất.
}
```

`mapper` là Jackson `ObjectMapper`, `service` là một Spring-managed bean. Nếu `applyEvent` mang `@Transactional`, lời gọi phải đi **qua proxy Spring**, không phải tự gọi một method trong chính object bị bypass proxy.

## 6. Transactional inbox: lưu khóa event cùng business update

**Transactional inbox** là một bảng lưu event identity đã được xử lý. Nó phải dùng **cùng database transaction** với thay đổi nghiệp vụ. Nếu chỉ đánh dấu đã xử lý bằng cache/Redis ngoài DB transaction, có thể xảy ra:

```text
Redis SET eventId=processed
          |
          v
PostgreSQL UPDATE lỗi / rollback
          |
          v
Kafka giao lại event
          |
          v
Redis báo đã xử lý -> mất business update
```

Do đó, một bảng inbox trong DB chứa business state là lựa chọn trực tiếp cho nhiều hệ thống.

### 6.1. Schema PostgreSQL

```sql
CREATE TABLE processed_kafka_events (
    source_system VARCHAR(80) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_system, event_id)
);

CREATE TABLE payment_projection (
    payment_id VARCHAR(120) PRIMARY KEY,
    current_version BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Trong đó:

- `(source_system, event_id)` là idempotency key cho **message event**.
- `payload_hash` dùng phát hiện trường hợp **cùng ID nhưng nội dung khác nhau**, không tự thay nội dung gốc.
- `payment_id` là khóa của **business entity**, không thay thế event ID.
- `current_version` hỗ trợ nhận diện update cũ/newer khi event là snapshot thay vì lệnh cộng dồn.

Cột `payload_hash` nên được tính từ **canonical payload** hoặc chuỗi byte có quy tắc nhất quán. Hash không tự giải quyết xung đột semantics khi các field thay đổi thứ tự trong JSON. Nếu cần so khớp tuyệt đối, lưu hoặc truy xuất payload phiên bản gốc trong audit bảo mật.

### 6.2. DTO và ràng buộc dữ liệu

```java
public record PaymentEvent(
        String sourceSystem,
        String eventId,
        String paymentId,
        long version,
        String status,
        String payloadHash
) {
}
```

Đây là một event biểu diễn **trạng thái snapshot** của payment. Nếu một event thực tế là delta kiểu `AddBalance(100)`, không thể áp dụng logic “version mới ghi đè snapshot” một cách máy móc.

`payloadHash` trong ví dụ giả định được upstream tạo đúng contract hoặc được application tính lại từ payload canonical đáng tin. **Không tin mọi hash nằm trong message mà không kiểm chứng** nếu nguồn ngoài có thể giả mạo.

### 6.3. Service transactional bảo vệ business effect

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class PaymentProjectionService {

    private final JdbcTemplate jdbc;

    public PaymentProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void applyEvent(PaymentEvent event) {
        validate(event);

        int inserted = jdbc.update("""
                INSERT INTO processed_kafka_events (
                    source_system,
                    event_id,
                    payload_hash
                ) VALUES (?, ?, ?)
                ON CONFLICT (source_system, event_id)
                DO NOTHING
                """,
                event.sourceSystem(),
                event.eventId(),
                event.payloadHash());

        if (inserted == 0) {
            String existingHash = jdbc.queryForObject("""
                    SELECT payload_hash
                      FROM processed_kafka_events
                     WHERE source_system = ?
                       AND event_id = ?
                    """,
                    String.class,
                    event.sourceSystem(),
                    event.eventId());

            if (!event.payloadHash().equals(existingHash)) {
                throw new ConflictingEventException(
                        "Same event ID has different payload");
            }

            return; // Replay chính cùng một event: no-op.
        }

        jdbc.update("""
                INSERT INTO payment_projection (
                    payment_id,
                    current_version,
                    status
                ) VALUES (?, ?, ?)
                ON CONFLICT (payment_id) DO UPDATE
                  SET current_version = EXCLUDED.current_version,
                      status = EXCLUDED.status,
                      updated_at = CURRENT_TIMESTAMP
                WHERE payment_projection.current_version
                      < EXCLUDED.current_version
                """,
                event.paymentId(),
                event.version(),
                event.status());
    }

    private static void validate(PaymentEvent event) {
        if (event == null
                || event.sourceSystem() == null
                || event.sourceSystem().isBlank()
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.paymentId() == null
                || event.paymentId().isBlank()
                || event.payloadHash() == null
                || event.payloadHash().length() != 64
                || event.version() < 0) {
            throw new InvalidPaymentEventException(
                    "Invalid payment event");
        }
    }
}
```

`ConflictingEventException` và `InvalidPaymentEventException` là các `RuntimeException` do ứng dụng tự định nghĩa. Cần bổ sung allowlist `status` và giới hạn độ dài/nguồn trong validation production. Ví dụ trên chủ yếu thể hiện transaction và idempotency.

**Điều kiện bắt buộc:** `JdbcTemplate` dùng đúng `DataSource` và `PlatformTransactionManager` mà `@Transactional` quản lý. Nếu inbox ở database A còn projection ở database B mà không có transaction chung, tính atomic trong ví dụ không còn đúng.

### 6.4. Vì sao insert inbox trước projection update?

`INSERT ... ON CONFLICT DO NOTHING` là phép thao tác atomic nhờ unique constraint của PostgreSQL. Khi có hai consumer race cùng event ID, một transaction lấy được quyền insert; transaction kia sẽ phụ thuộc kết quả commit/rollback của transaction cạnh tranh theo cơ chế database. Sau đó chỉ transaction được chấp nhận xử lý business update.

Nếu business update thất bại và transaction rollback, **inbox insert cũng rollback**, nên lần Kafka redelivery vẫn có thể xử lý lại.

```text
BEGIN
  INSERT inbox(eventId)
  UPDATE payment_projection
COMMIT

Nếu UPDATE lỗi:
  ROLLBACK inbox + projection
  Kafka redelivery -> có thể thử lại an toàn
```

Không dùng một lệnh update cache `seenEvents.add(eventId)` trước database rồi giả định cache rollback khi PostgreSQL rollback.

### 6.5. Phân biệt duplicate và stale version

Ví dụ:

```text
eventId=evt-101, paymentId=P-9, version=4  -> apply
eventId=evt-102, paymentId=P-9, version=3  -> inbox ghi nhận, projection giữ v4
eventId=evt-101, paymentId=P-9, version=4  -> duplicate event, no-op
eventId=evt-101, paymentId=P-9, version=8  -> conflict cùng event ID, fail
```

Với **snapshot state**, có thể chọn policy `highest version wins`. Với **ledger/financial delta**, không được bỏ event v3 chỉ vì v4 đã tới nếu mỗi delta có ý nghĩa cộng dồn. Khi đó nên phát hiện sequence gap, chờ/cách ly event và áp dụng theo đúng thứ tự nghiệp vụ.

**Một business entity có nhiều events hợp lệ**: dùng `paymentId` đơn lẻ để dedup sẽ bỏ nhầm các lần cập nhật hợp lệ. Inbox key nên mô tả **event occurrence**, còn bảng projection dùng business entity key.

## 7. Spring Kafka listener gọi service transactional

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public final class PaymentProjectionListener {

    private final ObjectMapper mapper;
    private final PaymentProjectionService service;

    public PaymentProjectionListener(
            ObjectMapper mapper,
            PaymentProjectionService service) {

        this.mapper = mapper;
        this.service = service;
    }

    @KafkaListener(
            topics = "payment-approved.v1",
            groupId = "payment-projection-v1")
    public void onMessage(String json) throws Exception {
        PaymentEvent event =
                mapper.readValue(json, PaymentEvent.class);

        service.applyEvent(event);
    }
}
```

Luồng vận hành:

```text
Kafka poll
   |
   v
Listener parses event
   |
   v
Spring @Transactional service
   |
   +-- INSERT inbox
   |
   +-- UPDATE projection
   |
   +-- DB COMMIT
   |
   v
Listener returns normally
   |
   v
Container commits offset according to AckMode
```

Giữa `DB COMMIT` và `offset commit` vẫn có failure window. Ta **không loại bỏ được nó** bằng đoạn code trên; ta thiết kế inbox để redelivery là an toàn.

### 7.1. Manual acknowledgment có tốt hơn không?

Có thể dùng `AckMode.MANUAL`/`MANUAL_IMMEDIATE` và `Acknowledgment.acknowledge()` **sau** khi service transactional trả về. Nhưng manual ack không tự biến hai commit thành atomic.

```java
@KafkaListener(
        topics = "payment-approved.v1",
        containerFactory = "manualAckFactory")
public void onMessage(
        String json,
        Acknowledgment ack) throws Exception {

    PaymentEvent event =
            mapper.readValue(json, PaymentEvent.class);

    service.applyEvent(event);
    ack.acknowledge();
}
```

Đoạn này yêu cầu `manualAckFactory` được cấu hình đúng manual ack mode. Không gọi `acknowledge()` trong `finally`, và không ack trước DB commit. Kể cả `acknowledge()` được gọi, crash/rebalance/commit failure vẫn cần idempotency.

Với ứng dụng chỉ cần record listener DB processing đơn giản, `AckMode.RECORD` thường dễ suy luận hơn manual ack tùy tiện.

## 8. Bảng tình huống crash: Kafka → DB

| Điểm lỗi | DB đã commit? | Offset đã commit? | Sau restart | Cơ chế bảo vệ |
|---|---|---|---|---|
| Trước khi bắt đầu DB transaction | Không | Không | Event đọc lại | Retry |
| Sau insert inbox nhưng trước business update, transaction rollback | Không | Không | Event đọc lại | Cùng DB transaction |
| Sau business update nhưng trước DB commit, transaction rollback | Không | Không | Event đọc lại | DB atomicity |
| Sau DB commit, trước offset commit | Có | Không | Event có thể đọc lại | Inbox idempotency |
| Offset commit đã thành công | Có | Có | Thường đọc tiếp offset sau | Commit policy + audit |
| DB commit rồi process chết trong lúc offset commit chưa rõ kết quả | Có | Không rõ | Có thể replay hoặc tiếp tục | Inbox idempotency |
| DLT publish/offset recovery thất bại | Tùy lỗi | Tùy container | Có thể retry/replay | Recoverer fail đúng + giám sát |

**Cốt lõi:** “Kafka giao lại event” không nên dẫn đến business effect lần thứ hai. Điều này cần unique key/transaction ở DB, không thể chỉ dựa vào log “đã từng xử lý”.

## 9. Retry, poison message và DLT

Khi business service ném exception, listener container chuyển việc xử lý cho error handler theo cấu hình.

Không phải lỗi nào cũng retry:

- **Transient:** mất kết nối DB, deadlock, broker/network thoáng qua → retry có giới hạn và backoff.
- **Permanent:** JSON thiếu trường bắt buộc, event version không được hỗ trợ, cùng event ID nhưng payload khác nhau → quarantine/DLT hoặc fail theo policy.
- **Unknown:** lỗi code, schema mismatch diện rộng → thường nên fail/alert, không che bằng `catch(Exception)`.

Ví dụ `DefaultErrorHandler`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.kafka.listener.DefaultErrorHandler;
import org.springframework.kafka.listener.DeadLetterPublishingRecoverer;
import org.springframework.util.backoff.FixedBackOff;

@Bean
DefaultErrorHandler paymentErrorHandler(
        KafkaTemplate<Object, Object> dltKafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltKafkaTemplate);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );

    handler.addNotRetryableExceptions(
            InvalidPaymentEventException.class,
            ConflictingEventException.class
    );

    return handler;
}
```

`InvalidPaymentEventException` và `ConflictingEventException` là các class nghiệp vụ do ứng dụng tạo. `dltKafkaTemplate` phải trỏ đúng cluster, topic, serializers và ACL của DLT. Đoạn code minh họa policy, **không tự cấu hình mọi bảo đảm publish DLT**.

### 9.1. Offset sau DLT

Nếu recoverer đã xử lý thành công theo semantics error handler, container có thể tiến qua message lỗi và commit offset theo cấu hình. Điều này có nghĩa:

- Record **không còn được xử lý ở luồng chính**.
- DLT/quarantine phải trở thành một **đường phục hồi có owner**.
- Nếu DLT publish thất bại, cần để handler/recoverer báo lỗi phù hợp, không âm thầm ghi log rồi bỏ record.
- Nếu DLT record được replay, replay phải tuân theo idempotency và business ordering.

Không mặc định DLT là bảo đảm “không mất dữ liệu” nếu không xác minh send result, topic retention và khả năng truy hồi.

### 9.2. Deserialization error xảy ra trước listener

Nếu Kafka value deserializer không tạo được object, listener method có thể **chưa được gọi**. Spring Kafka có `ErrorHandlingDeserializer` để đưa một số lỗi deserialization vào error handling path của container. Vì vậy test chỉ mock `@KafkaListener` không đủ cho các lỗi payload thực.

Với JSON không tin cậy, giới hạn payload size, trusted packages/type headers và schema compatibility là vấn đề riêng cần được thiết kế.

## 10. Trường hợp 2: Database → Kafka

Giả sử REST API nhận lệnh tạo đơn hàng:

```text
POST /orders
    |
    v
OrderService
    |
    +-- INSERT orders
    |
    +-- KafkaTemplate.send("order-created")
```

Một cách thực hiện ngây thơ:

```java
@Transactional
public void createOrder(Order order) {
    jdbc.update("INSERT INTO orders ...");
    kafkaTemplate.send("order-created.v1", order.id(), payload);
}
```

Rủi ro:

- `send` bất đồng bộ; method có thể return mà broker chưa ACK.
- Database rollback nhưng event đã được Kafka phát.
- Database commit nhưng ứng dụng chết trước khi event được gửi.
- Broker ACK bị mất; publisher gửi lại, tạo duplicate event nghiệp vụ.
- Kafka transaction (nếu bật) và DB transaction vẫn không cùng một atomic coordinator.

**Giải pháp phổ biến:** transactional outbox.

## 11. Transactional outbox: nguyên tắc

**Outbox** là bảng chứa sự kiện cần xuất Kafka, được ghi **trong cùng DB transaction với business state**.

```text
           HTTP command / business action
                       |
                       v
                 DB transaction
               +---------------+
               | orders        |
               | outbox_events |
               +---------------+
                       |
                    COMMIT
                       |
                       v
             Outbox Publisher / CDC
                       |
                       v
                  Kafka broker
                       |
                       v
                Downstream consumer
```

Với cùng database transaction:

- Nếu business update rollback, outbox insert rollback.
- Nếu business update commit, outbox event cũng tồn tại bền vững.
- Nếu publisher đang ngừng, outbox vẫn giữ event pending để gửi sau.
- Nếu publisher gửi thành công nhưng crash trước khi đánh dấu delivered, event có thể gửi lại. Consumer downstream cần idempotent.
- Sự kiện có thể được gửi **trễ** so với DB commit, nên hệ thống vận hành theo **eventual consistency**.

Outbox **không tự tạo exactly-once publish**. Nó bảo đảm có một nguồn bền vững để retry, thường cho hành vi **at-least-once**.

## 12. Schema PostgreSQL cho outbox

```sql
CREATE TABLE orders (
    order_id VARCHAR(120) PRIMARY KEY,
    status VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(120) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    topic_name VARCHAR(160) NOT NULL,
    message_key VARCHAR(160) NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claimed_until TIMESTAMPTZ NULL,
    claim_token UUID NULL
);

CREATE INDEX idx_outbox_pending
ON outbox_events (next_attempt_at, created_at, event_id)
WHERE published_at IS NULL;
```

Ý nghĩa:

- `event_id` là định danh **ổn định của event**, truyền qua Kafka để downstream dedup.
- `aggregate_id` và `message_key` thường dùng cùng business entity key để định tuyến partition ổn định.
- `created_at` hỗ trợ quan sát tuổi event và sắp xếp trong publisher.
- `published_at` thể hiện trạng thái ứng dụng đã xác nhận gửi thành công theo policy.
- `attempts` và `next_attempt_at` dùng cho bounded retry/backoff.
- `claimed_until` và `claim_token` hỗ trợ nhiều publisher cạnh tranh qua lease.

**Không lưu dữ liệu cá nhân hoặc credential vào payload nếu hợp đồng topic không cho phép.** Với payload nhạy cảm, cần schema, encryption, retention và ACL phù hợp. Outbox là data store phải quản lý backup/retention, không chỉ một queue tạm trong RAM.

### 12.1. Vì sao outbox cần event ID cố định?

Nếu publisher tạo `UUID.randomUUID()` mỗi lần nó gửi lại một dòng outbox, cùng sự kiện nghiệp vụ sẽ có **ID khác nhau** sau retry. Downstream không thể nhận biết đây là replay của cùng event.

Phải tạo `eventId` khi business transaction tạo event, ghi bền trong outbox, và dùng lại **chính ID đó** cho mọi lần publish.

## 13. Ghi business state và outbox trong một transaction

Ví dụ record đầu vào:

```java
public record CreateOrderCommand(
        String requestId,
        String orderId
) {
}
```

`requestId` giúp nhận diện yêu cầu tạo đơn. Trong production, cần thêm logic chống xử lý hai request có cùng ID theo business contract; `orderId` cũng có unique constraint.

### 13.1. Service Spring có @Transactional

```java
import java.util.UUID;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class OrderCreationService {

    private final JdbcTemplate jdbc;

    public OrderCreationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void createOrder(
            String orderId,
            String eventPayloadJson) {

        jdbc.update("""
                INSERT INTO orders(order_id, status)
                VALUES (?, 'CREATED')
                """,
                orderId);

        UUID eventId = UUID.randomUUID();

        jdbc.update("""
                INSERT INTO outbox_events (
                    event_id,
                    aggregate_type,
                    aggregate_id,
                    event_type,
                    topic_name,
                    message_key,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                eventId,
                "Order",
                orderId,
                "OrderCreated",
                "order-created.v1",
                orderId,
                eventPayloadJson);
    }
}
```

Ở đây `eventPayloadJson` phải được tạo bởi serializer/schema do ứng dụng kiểm soát, và **nên chứa chính `eventId` đã tạo** hoặc cho phép đưa event ID vào Kafka header để downstream dedup. Phiên bản production nên tạo DTO event, ID và payload **cùng một chỗ** trước khi insert, tránh mismatch giữa payload và outbox metadata.

### 13.2. Mở rộng production: chống lặp business command

Nếu caller gửi lại `createOrder(orderId)` do timeout:

- `orders.order_id` unique sẽ ngăn tạo hai đơn.
- Nhưng ứng dụng cần xác định duplicate request là **thành công idempotent** hay là **xung đột payload**.
- Có thể tạo bảng `processed_commands(request_id PRIMARY KEY, payload_hash, result_reference)` trong cùng DB transaction.
- Khi request ID đã tồn tại, kiểm tra hash: nếu cùng yêu cầu, trả cùng kết quả; nếu khác payload, báo conflict.
- Không tự swallow mọi unique-constraint exception thành “ok”, vì một lỗi khác cũng có thể gây constraint violation.

**Quan trọng:** Một event ID được sinh mới cho **một business operation mới**, không sinh mới mỗi lần retry publisher.

## 14. Outbox publisher: gửi sau commit

Publisher độc lập đọc các dòng chưa publish, gửi vào Kafka, đợi broker ACK (qua future) và đánh dấu thành công.

### 14.1. DTO outbox

```java
import java.util.UUID;

public record OutboxRow(
        UUID eventId,
        String topicName,
        String messageKey,
        String payloadJson
) {
}
```

### 14.2. Ví dụ publisher đơn giản, một instance

```java
import java.util.List;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public final class SimpleOutboxPublisher {

    private final JdbcTemplate jdbc;
    private final KafkaTemplate<String, String> kafka;

    public SimpleOutboxPublisher(
            JdbcTemplate jdbc,
            KafkaTemplate<String, String> kafka) {

        this.jdbc = jdbc;
        this.kafka = kafka;
    }

    @Scheduled(fixedDelayString = "${app.outbox.poll-ms:1000}")
    public void publishPending() {
        List<OutboxRow> rows = jdbc.query("""
                SELECT event_id, topic_name, message_key, payload_json
                  FROM outbox_events
                 WHERE published_at IS NULL
                   AND next_attempt_at <= CURRENT_TIMESTAMP
                 ORDER BY created_at, event_id
                 LIMIT 100
                """,
                (rs, index) -> new OutboxRow(
                        rs.getObject("event_id", java.util.UUID.class),
                        rs.getString("topic_name"),
                        rs.getString("message_key"),
                        rs.getString("payload_json")
                ));

        for (OutboxRow row : rows) {
            try {
                kafka.send(
                        row.topicName(),
                        row.messageKey(),
                        row.payloadJson()
                ).get(10, TimeUnit.SECONDS);

                jdbc.update("""
                        UPDATE outbox_events
                           SET published_at = CURRENT_TIMESTAMP
                         WHERE event_id = ?
                           AND published_at IS NULL
                        """,
                        row.eventId());

            } catch (Exception failure) {
                // Giữ pending để retry; production cần classify lỗi,
                // backoff, logging/metrics và giới hạn thời gian.
                reportOutboxFailure(row.eventId(), failure);
            }
        }
    }
}
```

`reportOutboxFailure(...)` là method nghiệp vụ minh họa. Cần cung cấp triển khai và cấu hình `@EnableScheduling` (khi không được bật bởi cấu hình khác) nếu muốn schedule chạy.

**Giới hạn quan trọng của ví dụ:**

- Chỉ phù hợp để **giải thích nguyên lý hoặc thử nghiệm một publisher instance**.
- Chưa có atomic claim/lease; nếu chạy nhiều pod cùng lúc, nhiều publisher có thể cùng gửi một dòng.
- Chưa cập nhật `attempts`, `next_attempt_at` hay phân loại lỗi; cần bổ sung before production.
- Chờ `future.get(...)` là cách đơn giản để biểu diễn “broker ACK trước khi mark”; hệ thống lưu lượng lớn có thể cần concurrent/asynchronous publisher giới hạn in-flight và backpressure.
- `published_at` được cập nhật **sau** Kafka ACK, nhưng việc này vẫn là transaction DB riêng. Crash giữa ACK và update có thể phát lại event.
- Đánh dấu `published_at` không có nghĩa mọi consumer downstream đã xử lý message.

### 14.3. Vì sao không mark published trước khi gửi?

Sai:

```text
1. UPDATE outbox_events SET published_at = NOW()
2. COMMIT
3. KafkaTemplate.send(...)
4. JVM chết trước khi broker nhận

=> Outbox bị xem là đã gửi, event có thể mất.
```

Thứ tự an toàn hơn:

```text
1. Read pending event
2. Send to Kafka
3. Wait for broker acknowledgment
4. UPDATE published_at
5. COMMIT update

Nếu chết trước (4), event gửi lại.
Downstream idempotent consumer xử lý replay.
```

Đây là lựa chọn chấp nhận **duplicate** thay cho **loss** khi không có atomic transaction giữa Kafka và DB.

## 15. Outbox nhiều publisher: claim/lease và SKIP LOCKED

Khi chạy nhiều pod publisher, query `SELECT ... WHERE published_at IS NULL` đơn giản có thể khiến hai pod lấy cùng row. Điều này không nhất thiết làm mất dữ liệu nếu downstream idempotent, nhưng gây duplicate và tốn băng thông.

Một mô hình phổ biến dùng **claim với thời hạn lease**.

### 15.1. SQL claim atomic trong PostgreSQL

Ví dụ minh họa:

```sql
WITH candidates AS (
    SELECT event_id
      FROM outbox_events
     WHERE published_at IS NULL
       AND next_attempt_at <= CURRENT_TIMESTAMP
       AND (
            claimed_until IS NULL
            OR claimed_until < CURRENT_TIMESTAMP
       )
     ORDER BY created_at, event_id
     FOR UPDATE SKIP LOCKED
     LIMIT 100
)
UPDATE outbox_events AS o
   SET claim_token = :claimToken,
       claimed_until = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
       attempts = attempts + 1
  FROM candidates AS c
 WHERE o.event_id = c.event_id
RETURNING
    o.event_id,
    o.topic_name,
    o.message_key,
    o.payload_json;
```

Đoạn này dùng PostgreSQL syntax và `:claimToken` là một UUID do publisher tạo cho **lượt claim**; truyền qua named parameter binding. Claim được thực hiện trong **transaction DB ngắn**, commit trước khi gọi Kafka.

**Không giữ row lock hoặc DB transaction mở trong suốt thời gian chờ Kafka ACK.** Làm vậy có thể giữ lock lâu, ảnh hưởng throughput và làm tăng contention.

### 15.2. Mark sau ACK với claim token

```sql
UPDATE outbox_events
   SET published_at = CURRENT_TIMESTAMP,
       claimed_until = NULL,
       claim_token = NULL
 WHERE event_id = :eventId
   AND claim_token = :claimToken
   AND published_at IS NULL;
```

Nếu update count bằng 0, publisher không nên tự kết luận “event đã được mark” — có thể lease đã hết và một worker khác claim lại. Cần log/metric và đối soát.

### 15.3. Lease không loại bỏ duplicate

Giả sử publisher A claim row với lease 60 giây, Kafka gửi chậm 80 giây. Lease hết, publisher B claim và gửi lại. Cả hai có thể publish cùng event.

Vì vậy:

- Lease thời gian phải tính tới send timeout/backpressure.
- Consumer downstream vẫn cần idempotency.
- Có thể gia hạn lease khi xử lý lâu.
- Dùng stable `eventId` để duplicate được nhận diện.
- Outbox state sau send failure phải cho phép retry có backoff; không để row kẹt vĩnh viễn ở trạng thái “in progress”.

**Claim giúp giảm cạnh tranh, không chứng minh exactly-once.**

### 15.4. Backoff và row lỗi dai dẳng

Một outbox row với payload vượt giới hạn topic hoặc serialization không hợp lệ sẽ thất bại liên tục. Không nên retry với 1 ms vô hạn.

Cần lưu:

```text
event_id
attempts
next_attempt_at
last_error_code
state = PENDING / CLAIMED / PUBLISHED / QUARANTINED
```

Nếu vượt ngưỡng, có thể chuyển row sang `QUARANTINED` và báo alert, nhưng **không được xóa trước khi có đường xử lý**. Event critical cần runbook replay/repair.

## 16. CDC outbox: Debezium thay poller

Một lựa chọn khác là sử dụng **Change Data Capture (CDC)** để đọc thay đổi từ transaction log database. Với PostgreSQL, các hệ như Debezium có thể đọc WAL qua logical replication và đưa outbox inserts sang Kafka.

```text
Business DB transaction:
    INSERT orders
    INSERT outbox_events
    COMMIT
             |
             v
   PostgreSQL WAL / logical decoding
             |
             v
      Debezium Connector
             |
             v
          Kafka topic
```

Mẫu này có ưu điểm:

- Không cần ứng dụng tự poll table theo vòng lặp.
- Quan sát commit order từ database log theo khả năng connector.
- Giảm polling queries nếu cấu hình phù hợp.
- Có thể dùng Debezium Outbox Event Router SMT để map field event từ outbox row sang Kafka topic/key.

Nhưng CDC **không miễn phí**:

- Cần quản lý Kafka Connect/connector và plugin/version.
- PostgreSQL logical replication slot có thể giữ WAL lâu nếu connector chậm.
- Cần quyền replication, snapshot strategy và retention phù hợp.
- Connector có thể retry/restart và phát lại event; consumer vẫn cần idempotency.
- Tên topic, event key, headers, schema và routing SMT cần version hóa.
- Error handling, poison outbox row và backup/restore phải có runbook.

### 16.1. Chọn poller hay CDC?

| Tiêu chí | Application polling | CDC / Debezium |
|---|---|---|
| Triển khai ban đầu | Dễ với service nhỏ | Cần Kafka Connect/CDC infra |
| Độ trễ | Theo lịch poll/backoff | Theo replication/log và connector |
| Tải database | SELECT/UPDATE pending | Đọc transaction log, vẫn có chi phí |
| Ordering | Cần tự thiết kế, nhất là khi nhiều worker | Phụ thuộc commit order/connector routing |
| Retry | Ứng dụng quản lý | Connector/Kafka Connect quản lý |
| Vận hành | Service team sở hữu poller | Platform/Connect owner |
| Idempotency | Vẫn cần | Vẫn cần |
| Giám sát | Pending age, attempts | Connector lag, replication slot, WAL retained |
| Recovery | Replay outbox rows | Connector offsets/snapshot/replay |

Không có lựa chọn tốt nhất cho mọi hệ thống. Nếu đã có Kafka Connect đáng tin, CDC có thể rất phù hợp. Nếu hệ thống nhỏ và muốn ít hạ tầng, poller rõ ràng và được kiểm chứng có thể đơn giản hơn.

## 17. Trường hợp 3: Kafka → DB → Kafka

Nhiều service nhận message, cập nhật DB rồi xuất một event mới:

```text
Kafka topic A
      |
      v
@KafkaListener
      |
      v
DB transaction
  - inbox event ID
  - business state
  - outbox output event
      |
    COMMIT
      |
      v
Container offset commit (Kafka A)
      |
      v
Outbox Publisher
      |
      v
Kafka topic B
```

Đây là **kết hợp inbox + outbox**.

Một thiết kế như vậy xử lý được ba khoảng lỗi chính:

1. **Trước DB commit:** transaction rollback; Kafka có thể giao lại input.
2. **Sau DB commit, trước input offset commit:** input có thể giao lại; inbox nhận diện duplicate, không ghi business/outbox lần thứ hai.
3. **Sau output Kafka ACK, trước mark outbox published:** output có thể gửi lại; downstream dedup bằng stable event ID.

### 17.1. Khi cùng cluster Kafka

Dù input và output ở **cùng Kafka cluster**, nếu business state phải commit trong PostgreSQL, ta vẫn cần suy luận khoảng lỗi DB/Kafka. Kafka transaction có thể hỗ trợ Kafka-to-Kafka exactly-once trong phạm vi riêng, nhưng không tự mở rộng thành atomic DB+Kafka transaction.

### 17.2. Khi khác cluster Kafka

Nếu input ở Kafka A, output sang Kafka B, không có một Kafka transaction chung bao phủ offset A và record B. Inbox/outbox đặc biệt hữu ích vì nó không phụ thuộc vào giả định cross-cluster transaction.

### 17.3. Ghi outbox trong cùng service transaction

Bổ sung vào service `applyEvent` đã giới thiệu:

```java
@Transactional
public void handleAndPlanOutput(PaymentEvent event) {
    // 1. Claim event ID trong inbox (unique key).
    // 2. Apply business change.
    // 3. Insert outbox với stable output eventId.
    // 4. Commit tất cả trong cùng database transaction.
}
```

Điểm quan trọng là **output event chỉ được tạo khi input thực sự là event mới hoặc đáp ứng policy phát output**. Nếu listener nhìn thấy input duplicate và lại tạo outbox UUID mới, downstream có thể thấy hai event kết quả cho một business action.

Có thể dùng deterministic output ID từ `(sourceSystem, inputEventId, outputEventType)` khi hợp đồng cho phép, hoặc lưu mapping `inputEventId → outputEventId` trong DB. Tránh tính ID chỉ từ timestamp hiện tại mỗi lần retry.

## 18. Từ “exactly once” đến invariant nghiệp vụ

Các cách diễn đạt thường gặp:

| Phát biểu | Có đúng mặc định không? | Điều kiện |
|---|---|---|
| Kafka consumer có thể đọc một record nhiều lần | Có thể | Offset chưa commit, rebalance, seek/replay |
| Producer `enable.idempotence=true` ngăn application gửi event hai lần | Không | Chỉ giải quyết một số duplicate retry nội bộ producer |
| `@Transactional` trên service khiến DB write atomic | Trong DB transaction đúng | Mọi thao tác phải tham gia cùng DB TX |
| `@Transactional` làm Kafka send + DB atomic | Không | Kafka và DB không tự có một coordinator chung |
| Kafka transactions hỗ trợ Kafka-to-Kafka EOS | Có theo cấu hình/phạm vi | Same cluster, transaction setup, offset handling |
| Inbox giúp database effect idempotent | Có theo thiết kế | Event ID đúng, unique key và cùng TX |
| Outbox ngăn event bị mất sau DB commit | Có theo model | Outbox durable, publisher/recovery vẫn vận hành |
| Outbox publisher chỉ gửi đúng một lần | Không | ACK/mark không atomic; có thể resend |
| DLT là bảo đảm event cuối cùng được xử lý thành công | Không | Cần replay owner và monitoring |
| Trace/metric báo success là bằng chứng exactly once | Không | Cần reconciliation/business evidence |

**Mục tiêu thực tế:** đạt **effectively-once business outcome** trong phạm vi dữ liệu được định nghĩa, thông qua at-least-once delivery + idempotent effects + cơ chế phục hồi. Đừng dùng nhãn “exactly once end-to-end” khi chưa mô tả và chứng minh tất cả external side effects.

## 19. Ordering: cùng aggregate và cùng partition

Kafka bảo đảm thứ tự records **trong một partition** theo log order, không bảo đảm tổng thứ tự trên mọi partition hoặc mọi topic.

Giả sử một đơn hàng có:

```text
OrderCreated(version=1)
OrderPaid(version=2)
OrderCancelled(version=3)
```

Nếu producer chọn Kafka key bằng `orderId`, các event của cùng order có khả năng vào cùng partition theo partitioner nhất quán. Điều này giúp consumer thấy thứ tự log nếu không có thay đổi partition/routing gây lệch. Nhưng:

- Các producer độc lập có thể gửi events theo thứ tự nghiệp vụ khác nhau.
- Consumer có retry/seek hoặc batch processing gây replay.
- Outbox publisher nhiều worker có thể gửi event version 3 trước version 2.
- Thay đổi số partition/topic routing có thể ảnh hưởng mapping key.
- Event từ nhiều nguồn không nhất thiết có một thứ tự chuẩn.

### 19.1. Thiết kế ordering rõ ràng

Với sự kiện snapshot:

- Lưu `aggregateVersion`.
- Chỉ áp dụng nếu version mới hơn.
- Nếu version bằng nhau nhưng payload khác, coi là conflict.
- Nếu yêu cầu không được skip gap, kiểm tra `version == currentVersion+1` và có cơ chế chờ/retry/quarantine.

Với sự kiện delta:

- Không chỉ dùng `MAX(version)` rồi bỏ qua các version trước.
- Cần apply theo thứ tự hoặc có phép toán commutative/associative được chứng minh.
- Có thể sử dụng bảng inbox + pending events theo aggregate và dispatcher theo sequence.

### 19.2. Outbox publish order

Query `ORDER BY created_at, event_id` cho thứ tự chọn có thể dự đoán, nhưng **không đảm bảo Kafka nhận cùng thứ tự** nếu nhiều publisher gửi concurrent hoặc các Kafka partitions khác nhau.

Nếu cần per-aggregate order:

1. Mỗi aggregate dùng Kafka message key ổn định.
2. Chốt thứ tự business bằng `aggregateVersion` hoặc sequence.
3. Publisher chọn/claim theo aggregate hoặc kiểm soát không gửi v+1 khi v đang pending.
4. Downstream kiểm tra version và giải quyết out-of-order.
5. Test concurrent publishing/restart, không chỉ happy path một worker.

## 20. Event ID, business key và idempotency key khác nhau

Một lỗi phổ biến là dùng cùng một trường cho mọi nghĩa.

| Key | Ví dụ | Dùng để |
|---|---|---|
| `eventId` | `evt-101` | Dedup một event được giao lại |
| `aggregateId` | `pay-701` | Xác định entity/thứ tự per entity |
| `commandId/requestId` | `req-19` | Dedup một yêu cầu API/job command |
| `transactionId` | `bank-txn-88` | Unique cho giao dịch nghiệp vụ |
| `traceId` | `abc...` | Liên kết telemetry, **không phải** business identity |
| Kafka `(topic,partition,offset)` | `payment-approved,2,120` | Vị trí record trong log |

Nếu event được copy sang topic khác, `topic/partition/offset` mới có thể thay đổi, nên không phải lúc nào cũng phù hợp làm idempotency key xuyên pipeline. Một `eventId` ổn định từ nguồn thường tốt hơn.

Nếu cùng business transaction được phát bằng **hai event ID khác nhau**, chỉ inbox event ID không ngăn được ghi hai giao dịch; cần thêm business uniqueness như `UNIQUE(sourceSystem,transactionId)` và policy xung đột.

## 21. Metadata, schema và các field cần giữ khi đi qua DB

Một event được đưa vào DB/outbox không nên mất những thông tin cần cho recovery:

```json
{
  "eventId": "evt-101",
  "eventType": "PaymentApproved",
  "schemaVersion": 1,
  "aggregateId": "pay-701",
  "aggregateVersion": 4,
  "occurredAt": "2025-05-12T10:00:00Z",
  "sourceSystem": "payments",
  "correlationId": "corr-19",
  "data": {
    "status": "APPROVED"
  }
}
```

Nên định nghĩa hợp đồng cho:

- Event ID có toàn cục hay chỉ duy nhất trong source?
- `occurredAt` là event time hay time publisher tạo?
- Version là schema version hay aggregate version? **Hai field này khác nhau.**
- Headers nào cần propagate: trace context, event type, correlation ID?
- Khi replay DLT, giữ nguyên event ID hay tạo ID mới? Thông thường giữ nguyên identity nếu đó vẫn là cùng event.
- Có cho phép thay đổi payload nhưng giữ ID không? Nếu không, phát hiện conflicting duplicate.
- Được phép lưu thông tin nhạy cảm ở payload/headers không?

Schema evolution phải được kiểm thử giữa producer/consumer deploy khác phiên bản. Không giả định tất cả service luôn deploy đồng thời.

## 22. Database transaction boundaries và @Transactional pitfalls

Một vài trường hợp làm thiết kế inbox/outbox sai dù mã có annotation:

### 22.1. Self-invocation bỏ qua proxy

```java
@Service
public class PaymentService {

    public void handle(PaymentEvent event) {
        saveTransactional(event); // self-invocation có thể bỏ qua proxy.
    }

    @Transactional
    public void saveTransactional(PaymentEvent event) {
        // JDBC updates...
    }
}
```

Với Spring proxy-based transaction management thông thường, gọi method trong cùng object không đi qua proxy, nên annotation có thể không được áp dụng như người viết kỳ vọng.

Giải pháp: để listener gọi một Spring-managed transactional service bean khác, hoặc dùng `TransactionTemplate` khi cần transaction boundary tường minh.

### 22.2. Bắt exception rồi return

```java
@Transactional
public void apply(PaymentEvent event) {
    try {
        jdbc.update(...);
    } catch (DataAccessException ex) {
        log.warn("Failed", ex);
        // Return bình thường có thể khiến transaction được commit
        // nếu không có rollback-only state từ tầng khác.
    }
}
```

Nếu lỗi buộc phải rollback, hãy rethrow phù hợp hoặc đánh dấu rollback-only theo policy. Không swallow rồi coi event hoàn tất.

### 22.3. Gọi HTTP/Kafka trong DB transaction

Nếu chờ Kafka ACK hoặc external API trong một DB transaction đang giữ row locks, throughput và lock contention có thể xấu đi. Tệ hơn, external side effect không rollback theo DB.

Tách ghi outbox vào transaction ngắn, sau đó publisher gửi bất đồng bộ sẽ giúp rõ ranh giới.

### 22.4. Hai DataSource

Nếu inbox và business tables ở **hai database hoặc hai datasources dùng transaction manager khác**, `@Transactional` mặc định chỉ điều phối một manager phù hợp. Đừng tuyên bố chúng atomic khi chưa có một cơ chế transaction thực sự hỗ trợ.

Thường đơn giản hơn khi inbox và business state có thể nằm trong cùng DB; nếu không, cần thiết kế consistency, compensating actions và reconciliation riêng.

## 23. Kafka transaction trong Spring Kafka: dùng đúng phạm vi

Spring Kafka hỗ trợ producer transactions khi cấu hình `transactionIdPrefix` và transaction manager phù hợp.

Ví dụ một producer transaction config theo Spring Boot:

```yaml
spring:
  kafka:
    producer:
      transaction-id-prefix: payment-tx-
      acks: all
      properties:
        "[enable.idempotence]": true
```

Cấu hình thực tế còn phụ thuộc số instance và cách quản lý transactional IDs để tránh fencing không mong muốn. Mỗi instance thường cần prefix/ID allocation phù hợp để các transactional producers không ghi đè nhau.

**Quan trọng:** bật Kafka producer transaction không đủ để một `@KafkaListener` dùng Kafka-to-Kafka EOS; cần đúng container, transactional producer, offset sending và isolation level ở downstream theo contract.

Nếu DB là source of truth, outbox thường đơn giản hơn việc ghép Kafka transaction với JDBC transaction rồi cố tuyên bố toàn bộ atomic.

### 23.1. Kafka EOS không bao gồm external DB theo mặc định

Một Kafka-to-Kafka processing topology có thể commit output records và consumed offsets trong cùng Kafka transaction, giúp tránh một số duplicate output trong phạm vi Kafka. Nhưng:

```text
Kafka input offset 120
  -> Kafka output event (transactional)
  -> PostgreSQL UPDATE
```

Không có bảo đảm tự động rằng PostgreSQL UPDATE rollback khi Kafka transaction abort hoặc ngược lại.

### 23.2. Một số transaction synchronization vẫn có failure window

Spring có cơ chế phối hợp các transaction manager và synchronization, nhưng commit của resource A rồi resource B vẫn có khoảng lỗi giữa hai bước. Cần đọc tài liệu API đúng phiên bản và có failure-injection tests; nếu yêu cầu atomicity tuyệt đối trên Kafka+DB, không được coi hai annotation `@Transactional` là bằng chứng.

## 24. Duplicate delivery là điều cần thiết kế, không chỉ kiểm thử một lần

Nguồn duplicate thường gặp:

- Kafka consumer restart trước offset commit.
- Rebalance khi xử lý lâu.
- Error handler retry cùng record.
- Producer application gửi lại sau timeout không rõ ACK.
- Outbox publisher crash sau ACK trước mark delivered.
- CDC connector restart/replay.
- Vận hành reset consumer group offset để reprocess.
- Hai scheduler/HTTP request cùng tạo một business command.
- Replay DLT sau khi khôi phục dữ liệu.

Một hệ thống idempotent nên chịu được ít nhất những lần phát lại trong phạm vi hợp đồng. Với các effect tài chính, **business unique constraint** là lớp bảo vệ cuối khi event ID không đủ.

### 24.1. Idempotency và conflicting duplicate

Hai event có cùng `eventId` nhưng payload khác là lỗi chất lượng dữ liệu:

```json
{"eventId":"evt-101","paymentId":"P-1","status":"APPROVED"}
{"eventId":"evt-101","paymentId":"P-1","status":"REJECTED"}
```

Đừng chỉ `ON CONFLICT DO NOTHING` rồi bỏ bản thứ hai mà không kiểm tra; hệ thống có thể che xung đột nghiêm trọng. Lưu payload hash, source/schema version và đưa conflict vào quarantine hoặc fail theo policy.

Nếu cùng `paymentId` nhưng event ID khác, có thể là một state transition hợp lệ. Đừng dedup mọi event theo entity key.

## 25. Reconciliation: tìm event bị kẹt giữa hai hệ thống

Inbox/outbox là thiết kế recovery; **đối soát** cho phép phát hiện khi recovery không tiến.

### 25.1. Outbox pending

```sql
SELECT
    COUNT(*) AS pending_events,
    MIN(created_at) AS oldest_pending_at,
    MAX(attempts) AS max_attempts
FROM outbox_events
WHERE published_at IS NULL;
```

Nếu oldest pending age vượt SLA, hệ thống có thể đang lỗi producer, Kafka broker, credentials, serialization hoặc publisher scheduler. Không nên chỉ nhìn consumer lag.

### 25.2. Các event outbox bị lỗi nhiều lần

```sql
SELECT
    event_id,
    aggregate_type,
    aggregate_id,
    event_type,
    attempts,
    next_attempt_at
FROM outbox_events
WHERE published_at IS NULL
  AND attempts >= 10
ORDER BY attempts DESC, created_at
LIMIT 100;
```

Nếu hệ thống có `QUARANTINED` state, query cần xét riêng trạng thái đó. Không xóa event chỉ vì đạt retry limit; cần xác nhận có quy trình sửa/replay.

### 25.3. Inbox và business state

```sql
SELECT COUNT(*) AS processed_event_count
FROM processed_kafka_events;
```

Con số inbox cho biết số event IDs đã được ghi nhận theo transaction. Nó **không nhất thiết bằng** số dòng `payment_projection` vì nhiều events có thể cập nhật cùng payment, và một stale event có thể được ghi inbox nhưng không thay đổi projection.

Muốn đối soát chính xác, cần định nghĩa phương trình theo event outcome:

```text
received_attempts
  = processing_attempts + deserialization_failures
  (theo cách instrumentation cụ thể)

unique_events
  = applied
  + stale
  + quarantined
  + pending
  (khi các nhóm được định nghĩa loại trừ nhau)
```

Đây là **mẫu khái niệm**, không thể lấy số client consumed rate làm phương trình business tuyệt đối nếu có retry, rebalance và DLT. Quy tắc đếm phải được xác minh theo nơi phát sinh counter.

### 25.4. Không suy ra consistency chỉ từ Spring Kafka metrics

Một listener Timer nhanh chỉ cho biết callback mất ít thời gian. Kafka producer send rate cao chỉ cho biết client gửi record. Chứng minh consistency cần đọc **nguồn sự thật của business state**, inbox/outbox status và các thông tin nguồn Kafka phù hợp.

## 26. Observability cho luồng Kafka–database

Một dashboard reliability nên phân biệt:

| Tín hiệu | Nguồn | Mục đích |
|---|---|---|
| Consumer group lag | Kafka exporter/admin monitoring | Phát hiện backlog |
| Listener duration/error | Micrometer Observation | Đo xử lý callback |
| DB transaction latency | JDBC/pool/DB metrics | Phát hiện bottleneck DB |
| Inbox duplicate count | Business metric | Theo dõi redelivery/replay |
| Inbox conflicting events | Business audit/metric | Phát hiện payload xung đột |
| Outbox pending count/age | PostgreSQL query/gauge | Phát hiện event chưa gửi |
| Outbox attempts/failures | Publisher metric | Biết producer đang retry |
| Kafka producer errors/ACK latency | Kafka client metric/future | Đường gửi Kafka có vấn đề |
| DLT published/pending | Recoverer + DLT monitoring | Quản lý poison messages |
| Event end-to-end age | Timestamp contract + telemetry | Đo SLO thực tế |
| Trace correlation | Micrometer Tracing/OTel | Kết nối consumer → DB → outbox publisher |

### 26.1. Tránh metric cardinality cao

Không dùng `eventId`, `paymentId`, `orderId` hay Kafka offset từng record làm Prometheus labels. Các giá trị đó có cardinality lớn. Dùng tags ổn định:

```text
application=payment-worker
topic=payment-approved.v1
source=payments
outcome=applied|duplicate|conflict|failed
error_class=validation|transient_db|serialization|unknown
```

Event ID cụ thể nên nằm trong **structured log/audit** có retention và quyền truy cập phù hợp. Tracing headers cũng không phải chứng cứ authentication.

### 26.2. Event age không bằng listener duration

Một event có thể chờ Kafka 20 phút rồi listener xử lý trong 30 ms. Listener Timer 30 ms là bình thường nhưng business end-to-end latency đã vi phạm SLO. Cần đo thêm event age, consumer lag và outbox oldest pending age.

## 27. Vận hành: consumer lag tăng thì điều tra đâu?

Khi Kafka → DB processing chậm, có thể là:

1. Producer tạo event nhanh hơn consumer capacity.
2. Listener đang retry một poison event.
3. PostgreSQL lock waits, slow query hoặc connection pool hết.
4. Consumer rebalance liên tục.
5. Partition skew khiến một partition có nhiều dữ liệu.
6. Group ID/offset config bị thay.
7. Listener bị pause/stop.
8. DLT publish hoặc error handler đang kẹt.
9. DB unique conflicts tăng do replay/duplicate dữ liệu nguồn.

Quy trình kiểm tra:

```text
Alert: group lag tăng
    |
    v
Xem partitions / assignment / consumer liveness
    |
    v
Xem listener duration và error/retry counters
    |
    +-- DB chậm? -> pool/locks/queries/transactions
    |
    +-- Poison record? -> error handler/DLT/quarantine
    |
    +-- Producer rate tăng? -> capacity/partitioning
    |
    +-- Rebalance? -> poll interval/pod lifecycle
    |
    v
Xác nhận lag giảm và business outcomes trở lại bình thường
```

Không reset offsets chỉ để “xóa lag”. Reset có thể bỏ qua records hoặc replay một lượng lớn dữ liệu. Cần có kế hoạch reprocessing và idempotency.

## 28. Vận hành: outbox tồn đọng thì điều tra đâu?

Khi `outbox_pending` tăng:

- **Kiểm tra scheduler/publisher:** poller đang chạy hay bị pause?
- **Kiểm tra Kafka destination:** bootstrap, topic, ACL, broker availability.
- **Kiểm tra send failures:** timeout, message too large, serialization, producer buffer pressure.
- **Kiểm tra DB:** query pending có chậm, row lock/lease có kẹt?
- **Kiểm tra claim expiry:** quá nhiều rows bị claim nhưng không có worker xử lý?
- **Kiểm tra CDC nếu sử dụng:** connector status, replication slot, WAL retention, connector offsets.
- **Kiểm tra tốc độ:** outbox create rate vượt publish throughput?
- **Kiểm tra payload lỗi lâu dài:** cùng row fail liên tục cần quarantine.

Một runbook hữu ích:

```text
1. Xác nhận số pending, oldest age và attempts.
2. Tìm event IDs representative trong audit.
3. Đối chiếu logs producer/connector và Kafka cluster status.
4. Sửa nguyên nhân mà không xóa outbox row.
5. Cho publisher resume/retry với stable event IDs.
6. Quan sát pending giảm và downstream nhận event.
7. Đối soát business effect; chú ý duplicate do resend.
```

Nếu publisher gửi event trùng sau recovery, đó có thể là hành vi được thiết kế. Mục tiêu là **không làm duplicate trở thành duplicate business effect**.

## 29. Vận hành: database unavailable

Nếu DB không sẵn sàng:

- Kafka consumer listener sẽ có lỗi. Error handler có thể retry với backoff hoặc pause/stop theo policy.
- Consumer lag có thể tăng, nhưng đó là điều dễ hiểu khi nguồn sự thật không hoạt động.
- Không nên ack event chưa xử lý thành công chỉ để giữ lag thấp.
- Khi DB hồi phục, consumer replay có thể chứa duplicate; inbox bảo vệ.
- Nếu producer outbox cũng dùng DB đó, publisher không thể lấy pending events; không nên giả định Kafka output tự tiếp tục.
- Cần capacity để bắt kịp backlog và kiểm tra DB pool tránh một đợt retry thác lũ.

Có thể sử dụng exponential backoff, circuit-breaker/pausing consumer hoặc điều phối tốc độ theo thiết kế. Không có một retry count chung phù hợp mọi SLA.

## 30. Vận hành: Kafka unavailable

Nếu Kafka input cluster không truy cập được, consumer tạm ngừng nhận dữ liệu. Database business state cũ có thể vẫn ổn, nhưng dữ liệu mới sẽ không được áp dụng.

Nếu Kafka output cluster unavailable:

- DB transaction tạo outbox vẫn có thể commit nếu business contract cho phép eventual publish.
- Outbox pending tăng, cần alert và retention.
- Khi Kafka hồi phục, publisher bắt kịp.
- Nếu output event phải được phát trong một deadline cứng, cần policy chặn một số thao tác hoặc cảnh báo business degradation, không chỉ đợi vô thời hạn.

Hãy ghi rõ **thời hạn tối đa chấp nhận pending** và dữ liệu nào không được công bố trước khi downstream xác nhận.

## 31. Deployment và schema migration an toàn

Một thay đổi nhỏ ở event schema hoặc bảng inbox/outbox có thể làm consumer/publisher lỗi hàng loạt.

### 31.1. Migration bảng outbox

Nếu cần thêm cột:

- Ưu tiên migration **backward compatible** với bản ứng dụng hiện tại.
- Áp dụng schema trước khi deploy code đọc/ghi field bắt buộc mới.
- Có giá trị default hoặc dual-read trong giai đoạn chuyển đổi nếu cần.
- Không xóa cột `event_id`/`payload` mà publisher cũ vẫn cần.
- Kiểm tra rows pending từ phiên bản trước có thể được publish bằng phiên bản mới.
- Khi CDC, kiểm tra connector/SMT có chịu schema change không.

### 31.2. Migration consumer group và offset

Thay `group.id` thường tạo **consumer group mới** với offset riêng. Nếu `auto.offset.reset=earliest`, group mới có thể đọc lại retained records. Nếu `latest`, group mới có thể bỏ dữ liệu trước thời điểm bắt đầu.

Kế hoạch deploy phải chỉ rõ:

- Giữ hay đổi group ID?
- Có cần backfill/replay không?
- Inbox retention có đủ dài để dedup replay?
- Business version/sequence có tương thích với event cũ?
- DLT cũ được xử lý thế nào?

### 31.3. Inbox retention

Không xóa inbox keys quá sớm. Nếu Kafka retention là 30 ngày nhưng inbox chỉ lưu 1 ngày, một message được replay sau 7 ngày có thể không còn key để dedup.

Thời gian giữ key phải phản ánh **cửa sổ replay thực tế**, DLT replay và yêu cầu nghiệp vụ. Với giao dịch tài chính cần chống tác động trùng dài hạn, business uniqueness và audit có thể phải được lưu lâu hơn Kafka retention.

### 31.4. Outbox cleanup

Chỉ dọn những rows đã được xác nhận published theo policy và đã qua thời gian audit/retention. Không dọn pending rows chỉ vì chúng đã cũ.

Một phương án là archive published events theo ngày, đồng thời giữ đủ metadata để đối soát sau sự cố.

## 32. Kiểm thử unit: idempotency và conflicting duplicate

Một bộ test nhỏ cần cho thấy:

- Event mới được apply.
- Cùng event ID + cùng payload được coi là replay, không apply hai lần.
- Cùng event ID + payload khác bị báo conflict.
- DB transaction rollback khi business update lỗi.
- Projection version cũ không ghi đè version mới.
- Null/malformed event không được xem là thành công.

### 32.1. Unit test cho validation

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PaymentEventValidationTest {

    @Test
    void rejectsMissingIdentity() {
        PaymentEvent invalid = new PaymentEvent(
                "payments",
                "",
                "pay-701",
                4L,
                "APPROVED",
                "a".repeat(64)
        );

        assertThrows(
                InvalidPaymentEventException.class,
                () -> PaymentProjectionService.validate(invalid)
        );
    }
}
```

Đoạn test cần điều chỉnh visibility của `validate` trong ví dụ (đang `private`) hoặc tách validator thành class riêng để test trực tiếp. Đây là **mẫu ý tưởng** kiểm tra contract, không phải class chạy độc lập ngay khi copy.

### 32.2. Vì sao mock repository không đủ?

Mock `JdbcTemplate.update(...)` có thể trả 1/0 và chứng minh nhánh logic, nhưng **không** chứng minh:

- PostgreSQL unique constraint giải quyết race giữa hai transactions.
- Inbox/projection rollback cùng nhau.
- Transaction proxy hoạt động.
- Kafka offset được commit đúng sau DB commit.

Các yêu cầu này cần integration test với database và Kafka broker tương tự môi trường production.

## 33. Integration test: Kafka → PostgreSQL

Đề xuất dùng **Testcontainers Kafka + PostgreSQL**, `spring-kafka-test` và Spring Boot test. Có thể dùng Awaitility hoặc các synchronization primitive có timeout hữu hạn; tránh `Thread.sleep(...)` tùy ý.

### 33.1. Kịch bản chuẩn

Fixture:

```text
Kafka topic: payment-approved.v1
Event:
  eventId=evt-101
  sourceSystem=payments
  paymentId=pay-701
  version=4
  status=APPROVED
```

Các bước:

1. Khởi tạo PostgreSQL schema và Kafka topic.
2. Gửi event `evt-101`.
3. Chờ projection DB đạt `APPROVED/version=4`.
4. Gửi lại chính event `evt-101`.
5. Xác nhận `processed_kafka_events` chỉ có một row cho key.
6. Xác nhận projection không bị cập nhật nghiệp vụ hai lần (nếu là delta, kiểm tra tổng không tăng thêm).
7. Xác nhận listener tiếp tục nhận event mới.

### 33.2. Lỗi sau DB commit trước offset commit

Đây là test failure injection quan trọng:

```text
Execution A:
  consume evt-101
  DB transaction COMMIT
  force crash / prevent offset commit

Execution B:
  consumer restart
  Kafka re-delivers evt-101
  inbox conflict -> no-op
  offset committed when listener returns
```

Có thể mô phỏng bằng test harness kiểm soát container lifecycle, ack mode và crash point, hoặc reset offset đến cùng record rồi xác nhận idempotent effect. **Reset offset là mô phỏng replay**, không chứng minh mọi race timing của production; cần ghi rõ phạm vi test.

### 33.3. Lỗi trước DB commit

Kích hoạt một exception sau insert inbox nhưng trước projection update/commit:

```text
BEGIN
  insert inbox evt-101
  throw exception
ROLLBACK
```

Assert inbox **không có key** và projection **chưa đổi**. Cho Kafka redelivery rồi xử lý lại thành công.

### 33.4. Concurrency

Cho hai listener/transactions xử lý cùng event ID song song và xác nhận unique constraint bảo vệ. Điều này đặc biệt cần thiết nếu có nhiều pod, nhiều partitions hoặc replay từ nhiều nguồn.

Không suy ra test một consumer đơn đã chứng minh concurrency safety.

## 34. Integration test: PostgreSQL → Kafka

### 34.1. Happy path

1. Tạo đơn hàng trong một DB transaction.
2. Xác nhận order và outbox row cùng tồn tại sau commit.
3. Cho publisher chạy.
4. Xác nhận Kafka nhận message đúng `eventId`, `message_key` và payload.
5. Xác nhận `published_at` được ghi sau ACK.
6. Xác nhận downstream idempotent khi cùng event được gửi lại.

### 34.2. Business transaction rollback

Giả lập lỗi ngay sau outbox insert, trước commit:

```text
BEGIN
  insert orders
  insert outbox
  throw error
ROLLBACK
```

Expected: không có cả order lẫn outbox row. Publisher không có gì để gửi.

### 34.3. Crash sau broker ACK trước mark published

Giả lập Kafka nhận message, nhưng test dừng publisher trước update `published_at`.

Khi publisher chạy lại, cùng `eventId` có thể được gửi lần nữa. Downstream consumer phải nhận diện replay và không gây business effect trùng.

### 34.4. Kafka không sẵn sàng

Tắt broker outbound trong test:

- Order + outbox commit theo policy.
- Publisher không mark row là published.
- Pending age/attempts tăng đúng policy.
- Khi broker trở lại, publisher gửi được row.
- Không xóa/đánh dấu giả event chỉ để bỏ cảnh báo.

### 34.5. Nhiều publisher

Chạy hai publisher cùng claim một tập outbox row. Assert atomic claim giảm tranh chấp và mọi event cuối cùng được gửi ít nhất một lần; **không** assert mỗi event chỉ có một Kafka record trong mọi crash scenario.

## 35. Test matrix: failure windows

| Điểm lỗi | Kỳ vọng |
|---|---|
| Consumer crash trước DB transaction | Kafka redelivery, không có business effect |
| Consumer crash trong DB transaction | DB rollback, retry an toàn |
| Consumer crash sau DB commit trước offset commit | Redelivery, inbox no-op |
| Consumer receives duplicate input event | Không apply duplicate |
| Input same ID khác payload | Conflict được phát hiện |
| Business event cũ đến sau version mới | Theo ordering/version policy |
| DB unavailable | Retry/backoff/stop theo policy, không ack sai |
| Kafka output unavailable | Outbox giữ pending |
| Outbox publisher crash sau ACK | Resend cùng event ID, downstream dedup |
| Hai publishers cùng claim | DB claim/lease bảo vệ concurrency, duplicate vẫn chịu được |
| Poison event JSON | DLT/quarantine theo policy và offset recovery |
| DLT producer thất bại | Không âm thầm bỏ record |
| Connector CDC ngừng | WAL/connector lag tăng và có alert |
| Kafka group ID đổi | Reprocessing plan/offset semantics được kiểm tra |
| Inbox keys hết retention | Không mất business uniqueness khi replay cũ |
| Schema mới/reader cũ | Compatibility hoặc fail/quarantine |
| Lost tracing/metrics | Business vẫn hoạt động, telemetry gap được phát hiện |

Một test suite đạt yêu cầu nghiệp vụ phải kiểm tra **database state, Kafka record identity, metadata offset và recovery behavior**. Chỉ assert `@KafkaListener` được gọi một lần trên happy path không chứng minh độ tin cậy.

## 36. Những anti-pattern cần tránh

| Anti-pattern | Rủi ro | Cách thay thế |
|---|---|---|
| Gọi `KafkaTemplate.send` trong `@Transactional` rồi tin tất cả atomic | DB và Kafka commit lệch | Transactional outbox |
| Commit/ack offset trước DB commit | Event có thể bị mất | Commit sau xử lý; inbox cho replay |
| Nuốt exception trong listener | Container coi như thành công | Propagate lỗi hoặc recovery bền vững |
| Dùng `HashSet` in-memory để dedup | Mất state qua crash, không rollback | Unique inbox key trong DB transaction |
| Inbox ở Redis ngoài DB TX | Mark processed nhưng DB rollback | Inbox cùng DB với business effect |
| Dùng `paymentId` để dedup mọi event | Bỏ mất cập nhật hợp lệ | Event ID và entity ID tách biệt |
| Không kiểm tra payload khi event ID trùng | Che conflicting duplicate | Hash/canonical payload + quarantine |
| Outbox mark published trước Kafka ACK | Mất event khi send thất bại | Mark sau ACK; cho phép resend |
| Outbox publisher tạo event ID mới mỗi retry | Downstream không nhận replay | Stable event ID từ outbox |
| Hai pollers SELECT pending không có coordination | Duplicate sends/race | Claim/lease, idempotent downstream |
| Giữ DB transaction mở khi chờ Kafka send | Locks dài, throughput thấp | Transaction ngắn, async outbox |
| DLT không có owner hoặc retention | Poison events bị bỏ quên | Runbook, monitoring, replay process |
| Xóa outbox pending để giảm backlog | Mất event | Sửa lỗi và retry/reconciliation |
| Retry lỗi schema vô hạn | Poison message chặn partition | Non-retryable classification và DLT |
| Dùng `enable.idempotence` như business exactly-once | Không bảo vệ DB/app resends | Inbox/outbox/business keys |
| Coi `read_committed` là DB transaction isolation | Hiểu sai phạm vi | Phân biệt Kafka transactions và JDBC |
| Dùng Kafka offset làm ID duy nhất qua nhiều topics | ID đổi khi forward/replay | Stable source event ID |
| Dùng tracing ID làm idempotency key | Trace không phải business identity | Event/command ID ổn định |
| Thay consumer group không kế hoạch | Replay hoặc skip records | Migration/reprocessing plan |
| Chỉ test embedded one-broker happy path | Không thấy dual-write crash windows | PostgreSQL + Kafka failure injection |
| Ghi payload/secret vào log/metric tags | Rò dữ liệu, high cardinality | Structured safe metadata + ACL |

## 37. Bài tập thực hành: đồng bộ thanh toán Kafka–PostgreSQL–Kafka

Xây dựng hệ thống `payment-settlement-service`:

- Nhận `PaymentApproved` từ `payment-approved.v1`.
- Ghi trạng thái thanh toán và lịch sử xử lý vào PostgreSQL.
- Phát `SettlementRequested` sang `settlement-requested.v1`.
- Hỗ trợ consumer restart, producer retry và ứng dụng chạy nhiều pod.

### Phần A — dữ liệu và transaction

1. Định nghĩa event ID, payment ID, aggregate version và schema version riêng.
2. Tạo `processed_kafka_events` với unique key theo source + event ID.
3. Tạo bảng `payments` có version hoặc business state transition rules.
4. Tạo `outbox_events` lưu stable output event ID, topic, key, payload, trạng thái pending.
5. Ghi inbox, business state và outbox **cùng một PostgreSQL transaction**.
6. Kiểm tra cùng input event ID + cùng payload là no-op; cùng ID khác payload là conflict.
7. Đặt unique business key phù hợp để ngăn hai event ID khác nhau tạo cùng effect trái phép.

### Phần B — consumer

8. Cấu hình `enable-auto-commit=false` và `AckMode.RECORD`.
9. Listener gọi một Spring-managed `@Transactional` service bean và không swallow exception.
10. Thêm `DefaultErrorHandler` với bounded retry và classify permanent error.
11. Cấu hình DLT với producer đúng cluster, kiểm tra recovery failure không bị bỏ qua.
12. Test DB commit rồi Kafka offset chưa commit; replay không nhân đôi effect.
13. Test DB rollback; inbox key cũng rollback để retry xử lý.

### Phần C — outbox publisher

14. Tạo publisher đọc pending rows, gửi `KafkaTemplate` với key ổn định và đợi ACK.
15. Chỉ mark `published_at` sau khi send future thành công.
16. Tạo case crash sau ACK trước mark; kiểm tra resend giữ nguyên event ID.
17. Mở rộng nhiều publisher bằng `FOR UPDATE SKIP LOCKED` + claim lease.
18. Bổ sung attempts/backoff/quarantine cho poison outbox rows.
19. So sánh poller và Debezium CDC theo latency, infra và recovery.
20. Nếu cần per-payment ordering, thiết kế aggregateVersion và publisher ordering policy.

### Phần D — quan sát và vận hành

21. Dashboard: consumer lag, listener error/retry, inbox duplicates/conflicts, outbox pending/oldest age, producer ACK failures.
22. Alert nếu outbox age vượt SLO hoặc Kafka group lag tăng liên tục.
23. Viết runbook khi PostgreSQL unavailable, outbound Kafka unavailable và Debezium connector ngừng.
24. Kiểm tra input/output topic ACL và tránh ghi dữ liệu nhạy cảm vào Kafka headers/logs.
25. Tạo integration test Kafka + PostgreSQL và các crash windows quan trọng.
26. Thử deploy thay `group.id`; giải thích cách inbox retention ảnh hưởng replay.
27. Thử event v5 đến trước v4; xác minh policy khác nhau giữa snapshot và delta events.
28. Tạo đối soát bảo đảm không có event outbox đã commit bị quên vĩnh viễn.

**Câu hỏi ôn tập 1:** Consumer đã update PostgreSQL thành công nhưng JVM chết trước offset commit. Kafka giao lại cùng record. Đây có phải lỗi Kafka không?

**Trả lời:** **Không.** Đây là failure window bình thường trong at-least-once processing. Inbox key cùng database transaction và idempotent business effect giúp replay an toàn.

**Câu hỏi ôn tập 2:** Nếu producer gửi Kafka thành công, nhưng ứng dụng chết trước khi cập nhật `outbox.published_at`, có được xóa row vì “chắc đã gửi rồi” không?

**Trả lời:** **Không nên.** Không có một commit atomic giữa broker ACK và cập nhật outbox. Publisher nên gửi lại cùng stable event ID khi cần; downstream dedup, sau đó đối soát và mark đúng.

**Câu hỏi ôn tập 3:** `@Transactional` + `KafkaTemplate` + `enable.idempotence=true` có đảm bảo chính xác một business effect trong cả PostgreSQL và Kafka không?

**Trả lời:** **Không.** Các cơ chế trên có phạm vi riêng. Khi cần consistency giữa DB và Kafka, phải thiết kế transaction boundaries, inbox/outbox, idempotency, failure recovery và kiểm chứng các crash windows.

## 38. Tài liệu tham khảo

- [Spring Kafka Reference — Exactly Once Semantics](https://docs.spring.io/spring-kafka/reference/kafka/exactly-once.html): Kafka transactions, offsets và phạm vi EOS.
- [Spring Kafka Reference — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): transactional producers, transaction synchronization và các giới hạn.
- [Spring Kafka Reference — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages.html): listener containers, offset management và acknowledgments.
- [Spring Kafka Reference — Handling Exceptions](https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html): `DefaultErrorHandler`, retry/recovery, DLT.
- [Spring Kafka Reference — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` và send futures.
- [Spring Boot Reference — Apache Kafka Support](https://docs.spring.io/spring-boot/reference/messaging/kafka.html): Boot consumer/producer/listener configuration.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, transaction manager và boundaries.
- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics): at-most-once, at-least-once và exactly-once trong Kafka.
- [PostgreSQL — INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): atomic uniqueness và upsert.
- [PostgreSQL — SELECT / SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html): khóa dòng và xử lý hàng chờ nhiều workers.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): thiết kế outbox với CDC và Kafka Connect.
- [Debezium — PostgreSQL Connector](https://debezium.io/documentation/reference/stable/connectors/postgresql.html): logical decoding, replication slots và connector operations.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): dual-write problem và outbox pattern.
- [Microservices.io — Idempotent Consumer](https://microservices.io/patterns/communication-style/idempotent-consumer.html): xử lý message redelivery bằng unique business key.
