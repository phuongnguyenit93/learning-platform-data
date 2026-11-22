# Khử trùng bằng event ID và lưu dấu xử lý bền vững

Kafka consumer thường phải chấp nhận khả năng một record được giao lại. Ví dụ, consumer đã cập nhật database thành công nhưng process dừng trước khi commit offset; khi khởi động lại, Kafka giao record đó lần nữa. Nếu ứng dụng thực hiện side effect mà không kiểm tra, đơn hàng có thể bị cộng tiền hai lần, số dư bị cập nhật lặp hoặc một thông báo bị gửi nhiều lần.

Một cách phổ biến để xử lý là **khử trùng bằng event ID** và lưu dấu đã xử lý trong một kho bền vững. Consumer kiểm tra event ID trước khi áp dụng nghiệp vụ. Việc ghi dấu và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction của database để không tạo ra trạng thái “đã đánh dấu nhưng chưa xử lý” hoặc “đã xử lý nhưng không có dấu”.

## 1. Vì sao Kafka có thể giao lại cùng một event?

Kafka lưu record trong partition và theo dõi tiến độ consumer group bằng committed offset. Việc xử lý record và commit offset là hai thao tác riêng biệt nếu ứng dụng ghi kết quả sang database bên ngoài Kafka.

Một luồng xử lý điển hình:

1. Consumer đọc record tại offset 120.
2. Ứng dụng cập nhật database thành công.
3. Process dừng trước khi commit offset 121.
4. Consumer khởi động lại và đọc lại offset 120.
5. Ứng dụng nhận cùng event lần thứ hai.

Đây là tình huống thường gặp trong ngữ nghĩa **at-least-once**: ứng dụng ưu tiên không bỏ qua record, nên có thể xử lý lại khi chưa chắc tiến độ đã được commit. Consumer cần chuẩn bị cho duplicate thay vì giả định mỗi record chỉ đến đúng một lần.

Những nguyên nhân khác cũng có thể tạo duplicate:

- Producer gửi lại cùng một event do retry ở tầng ứng dụng.
- Một event được publish lại trong quy trình phục hồi hoặc replay.
- Consumer group reset offset về vị trí cũ.
- Rebalance khiến record chưa commit được giao cho member mới.
- Một pipeline trung gian phát lại record sang topic khác.
- Hệ thống nguồn gửi lại cùng thông điệp vì không nhận được phản hồi.

Idempotent producer giúp tránh duplicate do retry trong phạm vi producer session và cơ chế Kafka hỗ trợ, nhưng không loại bỏ mọi lần gửi độc lập cùng một event. Deduplication ở consumer vẫn cần thiết khi side effect phải an toàn trước replay hoặc duplicate từ nguồn khác.

## 2. Event ID là gì và nên tạo ở đâu?

`eventId` là định danh ổn định của một sự kiện nghiệp vụ cụ thể. Mỗi sự kiện mới có ID riêng; khi cùng sự kiện được retry hoặc phát lại, ID phải được giữ nguyên.

Ví dụ payload:

```json
{
  "eventId": "evt-01JCV7YQ9K4M8R2N6T3A",
  "eventType": "PaymentAuthorized",
  "orderId": "ORD-2048",
  "amount": 1250000,
  "currency": "VND",
  "occurredAt": "2026-11-20T09:15:00Z"
}
```

Event ID có thể là UUID, ULID hoặc định danh do hệ thống nguồn cấp. Điều quan trọng là ID phải ổn định và duy nhất trong phạm vi đã quy định.

Các nguyên tắc thiết kế:

- Sinh ID tại nơi tạo ra sự kiện nghiệp vụ, không sinh lại mỗi lần consumer nhận record.
- Giữ nguyên ID khi producer retry hoặc ứng dụng phát lại cùng event.
- Nếu ID chỉ duy nhất trong một nguồn, lưu cả `eventSource` hoặc tenant trong khóa deduplication.
- Không dùng Kafka offset làm event ID: offset chỉ có ý nghĩa trong một partition và thay đổi khi event được publish sang topic/partition khác.
- Không dùng correlation ID thay event ID. Correlation ID nhóm nhiều event trong một quy trình; event ID nhận diện một event riêng lẻ.
- Không dựa hoàn toàn vào header tùy ý nếu payload không có định danh bền vững hoặc header có thể bị thay đổi trong pipeline.

Nếu producer tạo event ID mới mỗi lần retry cùng một thao tác nghiệp vụ, consumer không thể nhận ra đó là cùng sự kiện. Vì vậy, event ID phải được tạo và lưu cùng bản ghi nghiệp vụ nguồn trước khi publish, hoặc được tạo theo một khóa nghiệp vụ ổn định có quy tắc rõ ràng.

## 3. Bảng inbox/processed events để lưu dấu bền vững

Consumer có thể lưu event ID đã xử lý trong một bảng database. Mẫu thường dùng được gọi là **Inbox Pattern** hoặc processed-message table.

Ví dụ PostgreSQL:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(200) NOT NULL,
    event_source  VARCHAR(200) NOT NULL,
    event_id      VARCHAR(200) NOT NULL,
    payload_hash  VARCHAR(128) NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_source, event_id)
);
```

Các cột có ý nghĩa:

| Cột | Mục đích |
|---|---|
| `consumer_name` | Tên logic ổn định của handler hoặc projection cần deduplicate |
| `event_source` | Nguồn phát event, dùng khi event ID không duy nhất toàn hệ thống |
| `event_id` | Định danh của sự kiện |
| `payload_hash` | Hash payload chuẩn hóa để phát hiện cùng ID nhưng nội dung khác |
| `processed_at` | Thời điểm dấu xử lý được commit |

Khóa chính bảo đảm cùng một event chỉ được ghi dấu một lần cho một consumer logic. Dùng `consumer_name` giúp hai ứng dụng độc lập có thể xử lý cùng event theo mục đích riêng. Nếu dùng Kafka group ID làm namespace, cần cân nhắc việc đổi group ID hoặc tạo group replay mới: tên group mới có thể làm cùng event được xử lý lại theo namespace mới.

Nếu event ID duy nhất toàn hệ thống, có thể bỏ `event_source`; nếu một consumer xử lý nhiều projection độc lập, mỗi projection nên có namespace riêng. Thiết kế khóa phải phản ánh phạm vi “chỉ xử lý một lần” của nghiệp vụ.

## 4. Ghi dấu và cập nhật nghiệp vụ trong cùng transaction

Quy tắc quan trọng nhất là **insert processed marker và thay đổi dữ liệu nghiệp vụ phải commit hoặc rollback cùng nhau**.

Luồng đúng:

1. Bắt đầu transaction database.
2. Thử insert `(consumer_name, event_source, event_id)` vào bảng `processed_events`.
3. Nếu insert thành công, áp dụng thay đổi nghiệp vụ trong cùng transaction.
4. Commit transaction database.
5. Chỉ sau khi transaction database thành công, mới commit Kafka offset.

Nếu insert gặp khóa trùng, event đã được xử lý trước đó. Consumer có thể bỏ qua side effect nghiệp vụ và trả về thành công để tiến offset, sau khi xác minh bản ghi trùng là cùng event.

Ví dụ SQL PostgreSQL:

```sql
INSERT INTO processed_events (
    consumer_name, event_source, event_id, payload_hash
)
VALUES (
    :consumer_name, :event_source, :event_id, :payload_hash
)
ON CONFLICT (consumer_name, event_source, event_id) DO NOTHING;
```

Ứng dụng kiểm tra số dòng được insert:

- `1`: event ID mới; tiếp tục cập nhật nghiệp vụ.
- `0`: khóa đã tồn tại; không áp dụng lại side effect.

Với PostgreSQL, `ON CONFLICT DO NOTHING` giúp xử lý race giữa hai consumer cùng thử insert một event ID. Unique constraint là hàng rào cuối cùng; không chỉ dùng câu `SELECT` trước rồi mới `INSERT`, vì hai transaction có thể cùng đọc thấy chưa tồn tại và cùng tiếp tục xử lý.

### Vì sao phải cùng transaction?

Nếu commit dấu xử lý trước rồi mới cập nhật nghiệp vụ, process có thể dừng ở giữa. Lần nhận lại, consumer thấy marker và bỏ qua event, trong khi dữ liệu nghiệp vụ chưa từng được cập nhật.

Nếu cập nhật nghiệp vụ trước rồi commit dấu sau bằng transaction riêng, process có thể dừng giữa hai bước. Lần nhận lại, consumer không thấy marker và áp dụng nghiệp vụ lần nữa.

Khi marker và nghiệp vụ nằm trong cùng transaction, database bảo đảm cả hai cùng xuất hiện hoặc cùng rollback.

## 5. Ví dụ Java: deduplication với JDBC

Ví dụ sau dùng PostgreSQL và `JdbcTemplate`. Phần insert marker và cập nhật đơn hàng chạy trong cùng transaction Spring.

```java
public enum ProcessingResult {
    PROCESSED,
    DUPLICATE
}
```

Service xử lý:

```java
@Service
public class PaymentEventHandler {

    private final JdbcTemplate jdbcTemplate;

    public PaymentEventHandler(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public ProcessingResult handle(PaymentAuthorized event) {
        String payloadHash = sha256(canonicalPayload(event));

        int inserted = jdbcTemplate.update("""
            INSERT INTO processed_events (
                consumer_name, event_source, event_id, payload_hash
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT (consumer_name, event_source, event_id) DO NOTHING
            """,
            "payment-projection",
            event.source(),
            event.eventId(),
            payloadHash);

        if (inserted == 0) {
            verifyExistingPayloadHash(event, payloadHash);
            return ProcessingResult.DUPLICATE;
        }

        jdbcTemplate.update("""
            UPDATE orders
            SET payment_status = 'AUTHORIZED',
                paid_amount = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE order_id = ?
            """,
            event.amount(),
            event.orderId());

        return ProcessingResult.PROCESSED;
    }

    private void verifyExistingPayloadHash(
            PaymentAuthorized event, String incomingHash) {
        String storedHash = jdbcTemplate.queryForObject("""
            SELECT payload_hash
            FROM processed_events
            WHERE consumer_name = ?
              AND event_source = ?
              AND event_id = ?
            """,
            String.class,
            "payment-projection",
            event.source(),
            event.eventId());

        if (!storedHash.equals(incomingHash)) {
            throw new IllegalStateException(
                    "Event ID reused with different payload: " + event.eventId());
        }
    }

    // canonicalPayload() và sha256() là helper do ứng dụng triển khai.
}
```

Đây là ví dụ minh họa; `PaymentAuthorized`, `canonicalPayload()` và `sha256()` do ứng dụng định nghĩa. Payload hash nên được tính từ biểu diễn chuẩn hóa của nội dung nghiệp vụ, không phụ thuộc thứ tự field JSON hoặc metadata thay đổi như timestamp gửi lại.

Nếu event ID đã tồn tại nhưng payload hash khác, không nên im lặng xem đó là duplicate hợp lệ. Đây có thể là lỗi producer tái sử dụng ID, dữ liệu bị biến đổi hoặc vấn đề bảo mật. Ghi nhận lỗi và chuyển sang quy trình điều tra/DLQ phù hợp.

## 6. Consumer chỉ commit offset sau khi transaction database hoàn tất

Ví dụ consumer Java xử lý từng record đồng bộ:

```java
props.put(ConsumerConfig.ENABLE_AUTO_COMMIT_CONFIG, false);

try (KafkaConsumer<String, String> consumer = new KafkaConsumer<>(props)) {
    consumer.subscribe(List.of("payments.events"));

    while (running) {
        ConsumerRecords<String, String> records =
                consumer.poll(Duration.ofMillis(500));

        for (ConsumerRecord<String, String> record : records) {
            PaymentAuthorized event = deserialize(record.value());

            // Proxy Spring hoàn tất DB transaction trước khi method trả về.
            handler.handle(event);

            TopicPartition tp =
                    new TopicPartition(record.topic(), record.partition());
            consumer.commitSync(Map.of(
                    tp, new OffsetAndMetadata(record.offset() + 1)));
        }
    }
}
```

Trong ví dụ này, `handler` phải là Spring bean được inject qua proxy để `@Transactional` thực sự có hiệu lực. Không gọi method transactional bằng self-invocation trong cùng object nếu cơ chế proxy của ứng dụng không intercept lời gọi đó. `deserialize()` và `running` là phần ứng dụng tự triển khai.

Thứ tự là DB commit trước, Kafka offset commit sau. Nếu DB transaction rollback, exception phải thoát ra để ứng dụng không commit offset. Nếu DB commit thành công nhưng `commitSync()` thất bại hoặc process dừng, Kafka có thể giao lại record; bảng `processed_events` nhận diện duplicate và ngăn cập nhật nghiệp vụ lần hai.

Ví dụ commit từng record đơn giản và dễ hiểu nhưng có thể giảm throughput. Với batch, chỉ commit offset kế tiếp sau dãy record liên tục đã xử lý thành công ở từng partition. Nếu record giữa batch lỗi, không commit vượt qua record lỗi.

## 7. Crash matrix: điều gì xảy ra nếu process dừng?

| Thời điểm process dừng | Marker DB | Thay đổi nghiệp vụ | Kafka offset | Lần chạy lại |
|---|---|---|---|---|
| Trước transaction DB | Chưa có | Chưa có | Chưa commit | Đọc lại và xử lý bình thường |
| Sau insert marker nhưng trước DB commit | Transaction rollback | Transaction rollback | Chưa commit | Đọc lại; marker chưa tồn tại nên xử lý lại |
| Sau DB commit, trước offset commit | Đã có | Đã có | Chưa commit | Đọc lại; dedup phát hiện duplicate và bỏ qua side effect |
| Sau offset commit | Đã có | Đã có | Đã commit | Tiếp tục record kế tiếp |

Thiết kế này tạo ra khả năng xử lý lại an toàn khi DB đã commit nhưng offset chưa commit. Nó không tạo transaction phân tán giữa Kafka và database; thay vào đó, nó tận dụng at-least-once delivery cùng database transaction và deduplication.

Trường hợp nguy hiểm là commit Kafka offset trước khi DB transaction hoàn tất. Nếu offset đã tiến nhưng DB rollback hoặc process dừng trước khi ghi nghiệp vụ, record sẽ không được giao lại theo offset đã commit và side effect bị mất. Vì vậy, với mô hình này luôn phải commit database trước, offset sau.

## 8. Vì sao phải phát hiện cùng event ID nhưng payload khác?

Giả sử event `evt-100` lần đầu có nội dung `amount=100000`, nhưng lần sau producer gửi cùng event ID với `amount=900000`. Nếu consumer chỉ kiểm tra event ID rồi bỏ qua, nó sẽ che giấu lỗi dữ liệu nghiêm trọng.

Lưu `payload_hash` cho phép phân biệt:

- Cùng event ID, cùng payload hash: duplicate hợp lệ, có thể bỏ qua.
- Cùng event ID, khác payload hash: vi phạm hợp đồng định danh, cần cảnh báo và điều tra.

Hash phải được tính từ dữ liệu ổn định. Nếu JSON serializer đổi thứ tự field hoặc thêm metadata không ảnh hưởng nghiệp vụ, hash bytes thô có thể khác dù event có cùng nội dung. Có thể canonicalize JSON, hash các trường nghiệp vụ đã chuẩn hóa hoặc dùng schema-aware canonical representation.

Không nên lưu dữ liệu nhạy cảm nguyên văn trong bảng dedup chỉ để so sánh. Hash không thay thế mã hóa dữ liệu và vẫn có thể làm lộ thông tin đối với giá trị có không gian tìm kiếm nhỏ; áp dụng chính sách bảo vệ dữ liệu của hệ thống.

## 9. Khử trùng khi nhiều consumer xử lý đồng thời

Trong một consumer group, một partition tại một thời điểm chỉ được gán cho một member, nhưng duplicate vẫn có thể xuất hiện do replay, producer retry ở tầng ứng dụng, nhiều topic hoặc nhiều pipeline. Hai consumer khác nhau cũng có thể nhận cùng event ID nếu cùng event được publish vào hai partition/topic.

Unique constraint trong database bảo vệ trước race đồng thời. Hai transaction cùng insert một khóa dedup sẽ được database tuần tự hóa theo unique index; chỉ một transaction insert thành công. Transaction còn lại thấy conflict và không áp dụng side effect lần hai.

Không dùng quy trình chỉ đọc trước:

```sql
SELECT 1 FROM processed_events WHERE event_id = :event_id;
-- Nếu không có row thì mới INSERT và cập nhật nghiệp vụ.
```

Hai consumer có thể cùng chạy `SELECT` trước khi một bên insert. Cả hai đều thấy chưa có row và cùng thực hiện nghiệp vụ. Unique constraint phải là hàng rào cuối cùng và thao tác insert marker phải xảy ra trước side effect trong cùng transaction.

## 10. Deduplication với side effect bên ngoài database

Transaction database chỉ bảo vệ những thao tác tham gia cùng transaction đó. Nếu consumer gọi HTTP API, gửi email, trừ tiền qua payment gateway hoặc publish sang một hệ thống khác, database không thể tự rollback side effect bên ngoài.

Ví dụ không an toàn:

1. Gọi payment API thành công.
2. Ghi processed marker vào database.
3. Database transaction thất bại.
4. Kafka giao lại event và consumer gọi payment API lần nữa.

Các cách xử lý:

- **Idempotency key ở API đích:** gửi `eventId` làm idempotency key nếu nhà cung cấp hỗ trợ và bảo đảm cùng key trả về cùng kết quả.
- **Transactional outbox:** trong transaction DB, ghi processed marker, cập nhật nghiệp vụ và tạo một outbox command. Một dispatcher riêng gửi command ra ngoài; dispatcher có thể retry và cần idempotency ở đích.
- **Inbox ở dịch vụ nhận:** nếu hệ thống đích do mình quản lý, nó lưu event/command ID và side effect trong transaction riêng.
- **Saga và reconciliation:** với quy trình nhiều hệ thống không có transaction chung, theo dõi trạng thái, retry có kiểm soát và có bước bù/đối soát.

Không giữ transaction database mở trong lúc chờ HTTP call dài chỉ để hy vọng tạo được tính nguyên tử. Điều đó giữ lock lâu, tăng contention và vẫn không thể rollback một side effect đã xảy ra ở hệ thống ngoài.

## 11. Inbox và Transactional Outbox phối hợp với nhau

Inbox giúp consumer nhận diện event đã xử lý; outbox giúp một dịch vụ phát hành event/command ra ngoài một cách bền vững cùng với thay đổi database.

Ví dụ dịch vụ Order nhận `PaymentAuthorized`:

1. Mở transaction database.
2. Insert event ID vào inbox.
3. Cập nhật trạng thái đơn hàng.
4. Insert `OrderPaid` vào bảng outbox.
5. Commit database transaction.
6. Commit Kafka offset sau khi transaction database hoàn tất.
7. Outbox publisher đọc row chưa gửi và publish sang Kafka; sau khi nhận xác nhận, đánh dấu row đã gửi theo quy trình retry an toàn.

Outbox publisher có thể publish cùng một event nhiều lần nếu broker đã nhận nhưng publisher dừng trước khi đánh dấu row đã gửi. Consumer nhận downstream vẫn cần dedup bằng event ID. Inbox/outbox hỗ trợ giao nhận đáng tin cậy theo từng ranh giới hệ thống; chúng không tự tạo exactly-once xuyên mọi database, Kafka và HTTP service.

## 12. Phân biệt deduplication, idempotency và Kafka exactly-once

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Deduplication | Nhận diện và bỏ qua cùng một event đã được xử lý | Unique key `(consumer_name, event_id)` |
| Idempotent operation | Thực hiện lại cùng thao tác không làm thay đổi kết quả cuối | Upsert trạng thái theo event version hoặc API có idempotency key |
| Idempotent producer | Kafka broker nhận diện retry của cùng producer sequence để tránh duplicate do retry | `enable.idempotence=true` |
| Kafka transaction / exactly-once trong Kafka | Kết hợp output Kafka và input offsets trong một transaction Kafka | Consume-transform-produce với `sendOffsetsToTransaction()` |
| Exactly-once với database/API ngoài Kafka | Cần phối hợp transaction hoặc giao thức riêng tại các hệ thống liên quan | Inbox/outbox, unique constraint, idempotency key, saga |

Không nên quảng cáo bảng dedup như bảo đảm exactly-once cho mọi side effect. Nó bảo vệ đúng phạm vi mà transaction database bao phủ. Một API ngoài không hỗ trợ idempotency vẫn có thể nhận hai lần yêu cầu nếu consumer dừng ở thời điểm không xác định.

## 13. Spring Kafka: listener gọi transactional service

Một cấu hình cơ bản dùng manual database transaction và để listener container quản lý offset:

```yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
    listener:
      ack-mode: record
```

Listener gọi service transactional:

```java
@Component
public class PaymentListener {

    private final PaymentEventHandler handler;

    public PaymentListener(PaymentEventHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(topics = "payments.events", groupId = "payment-projection")
    public void listen(ConsumerRecord<String, String> record) {
        PaymentAuthorized event = deserialize(record.value());

        // Method trả về sau khi DB transaction commit.
        handler.handle(event);
    }
}
```

Với `AckMode.RECORD`, listener container commit offset sau khi listener xử lý thành công record theo cơ chế container. Nếu `handler.handle()` ném exception, listener không được xem là thành công; error handler/retry configuration quyết định việc retry, recover hoặc chuyển DLQ. Cần cấu hình error handler sao cho offset không bị commit trước khi lỗi được xử lý theo chính sách mong muốn.

Đừng bật Kafka transaction manager và giả định nó tự kết hợp nguyên tử với database transaction. Nếu cần đồng bộ hai resource, phải thiết kế thứ tự commit, recovery hoặc outbox/inbox; transaction manager riêng của Kafka và database không tự trở thành một distributed transaction chung.

## 14. Dùng `@Transactional` đúng cách

Một số điểm cần chú ý với Spring:

- Method transactional nên được gọi qua Spring proxy, thường từ một bean khác.
- Mặc định, runtime exception làm transaction rollback; checked exception cần cấu hình `rollbackFor` nếu muốn rollback.
- Không bắt exception rồi nuốt lỗi bên trong service trước khi transaction interceptor biết có lỗi, trừ khi chủ động đánh dấu rollback-only.
- Chỉ trả về listener sau khi transaction database đã commit.
- Không acknowledge hoặc commit offset trước khi service transactional hoàn tất.
- Nếu một batch xử lý nhiều event, cần quyết định transaction theo từng record hay toàn batch và bảo đảm offset tương ứng không vượt qua record lỗi.

Ví dụ nếu cần rollback cả checked exception:

```java
@Transactional(rollbackFor = Exception.class)
public ProcessingResult handle(PaymentAuthorized event) throws Exception {
    // Insert marker và cập nhật business state.
}
```

Chọn transaction boundary theo kích thước nghiệp vụ. Transaction quá lớn làm lock lâu; transaction quá nhỏ có thể khiến một event cần nhiều bảng được cập nhật không nguyên tử.

## 15. Thời gian lưu dedup marker và replay

Processed marker phải được giữ lâu ít nhất bằng khoảng thời gian hệ thống có thể nhận lại event. Nếu xóa marker sau 7 ngày nhưng operator có thể reset offset và replay dữ liệu 30 ngày, event cũ có thể được áp dụng lần nữa.

Khi thiết kế retention cho bảng dedup, cân nhắc:

- Retention của Kafka topic và khả năng replay từ backup/archive.
- Thời gian tối đa của retry ở producer, retry topic và DLQ.
- Quy trình vận hành reset offset hoặc backfill.
- Yêu cầu audit và thời gian lưu dữ liệu nghiệp vụ.
- Dung lượng bảng, index và chiến lược partition/archive database.
- Quy định bảo vệ dữ liệu và yêu cầu xóa dữ liệu cá nhân.

Nếu event có thể được replay vô thời hạn, cần lưu dấu dedup vô thời hạn hoặc có một cơ chế snapshot/checkpoint và version nghiệp vụ đủ mạnh để ngăn áp dụng lại. Xóa marker là một quyết định nghiệp vụ, không chỉ là tối ưu dung lượng.

## 16. Quan sát và vận hành deduplication

Nên theo dõi:

| Metric/log | Ý nghĩa |
|---|---|
| `events_processed_total` | Số event mới được xử lý thành công |
| `events_duplicate_total` | Số event bị bỏ qua do đã có marker |
| `event_id_payload_conflict_total` | Cùng event ID nhưng payload hash khác |
| `inbox_insert_latency` | Thời gian ghi marker/kiểm tra unique constraint |
| `db_transaction_failure_total` | Transaction ghi marker hoặc business state thất bại |
| `consumer_commit_failure_total` | DB có thể đã commit nhưng offset commit thất bại, dẫn đến replay |
| `inbox_table_rows` | Tốc độ tăng trưởng và dung lượng processed marker |

Log nên có `eventId`, `eventSource`, `consumerName`, topic, partition, offset và kết quả `PROCESSED`/`DUPLICATE`. Tránh ghi payload nhạy cảm vào log.

Tỷ lệ duplicate tăng đột biến có thể là dấu hiệu rebalance thường xuyên, producer retry ở tầng ứng dụng, consumer commit thất bại, replay đang chạy hoặc upstream phát lại event. Duplicate không nhất thiết là lỗi, nhưng cần quan sát để phân biệt hoạt động bình thường với sự cố.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Cùng event bị áp dụng nghiệp vụ hai lần | Chỉ kiểm tra trong memory hoặc không lưu event ID bền vững | Dùng unique constraint trong database và transaction chung với business update |
| Marker tồn tại nhưng business state chưa cập nhật | Commit marker trước side effect hoặc transaction boundary tách rời | Đặt marker và business update trong cùng transaction |
| Business state đã cập nhật nhưng marker không có | Business update commit trước marker trong transaction riêng | Gộp hai thao tác vào cùng DB transaction |
| Hai consumer cùng xử lý một event | Dùng `SELECT` trước `INSERT` mà không có unique constraint | Dùng unique key và atomic insert/upsert |
| Cùng event ID nhưng nội dung khác | Producer tái sử dụng ID hoặc event bị biến đổi | Lưu payload hash, báo conflict và điều tra; không coi là duplicate bình thường |
| Duplicate xuất hiện sau replay dài ngày | Dedup marker đã bị xóa trước replay horizon | Kéo dài retention hoặc dùng checkpoint/version nghiệp vụ |
| Email/API vẫn bị gọi hai lần | Side effect nằm ngoài transaction DB | Dùng idempotency key ở đích hoặc outbox/inbox và reconciliation |
| Offset commit thành công trước DB | Auto commit hoặc acknowledge quá sớm | Tắt auto commit, chỉ commit sau khi DB transaction hoàn tất |
| Bảng processed events tăng quá nhanh | Không có retention/archive phù hợp hoặc namespace quá rộng | Thiết kế retention theo replay horizon và partition/archive bảng |

## 18. Checklist thiết kế production

- Mỗi event có `eventId` ổn định và không đổi khi retry/replay.
- Xác định rõ phạm vi duy nhất của event ID; bổ sung source/tenant nếu cần.
- Namespace dedup theo consumer logic/projection, không dùng một marker chung cho mọi ứng dụng.
- Có unique constraint trên khóa deduplication.
- Insert marker và cập nhật business state trong cùng database transaction.
- Xử lý cùng ID nhưng payload khác như lỗi dữ liệu, có hash/canonicalization phù hợp.
- Commit Kafka offset sau khi DB transaction hoàn tất.
- Tắt auto commit nếu ứng dụng cần kiểm soát thứ tự DB commit/offset commit.
- Làm side effect bên ngoài database idempotent hoặc đưa qua outbox.
- Không nhầm producer idempotence/Kafka transaction với dedup side effect ở database.
- Giữ marker ít nhất bằng replay/retry horizon hoặc có cơ chế version/checkpoint thay thế.
- Theo dõi duplicate rate, payload conflict, DB failure và commit failure.
- Kiểm thử các crash window: trước DB commit, sau DB commit trước offset commit và khi hai consumer xử lý cùng ID.

## 19. Ghi nhớ

Event ID nhận diện một sự kiện cụ thể và phải giữ nguyên qua retry/replay. Consumer lưu dấu đã xử lý bằng bảng inbox/processed events có unique constraint. Insert marker và cập nhật dữ liệu nghiệp vụ phải nằm trong cùng transaction database; sau khi transaction thành công mới commit Kafka offset.

Nếu process dừng sau DB commit nhưng trước offset commit, Kafka có thể giao lại event. Marker bền vững giúp consumer nhận diện duplicate và bỏ qua side effect lần hai. Với side effect ngoài database, cần idempotency key ở hệ thống đích hoặc transactional outbox/inbox. Deduplication tạo khả năng xử lý at-least-once an toàn trong phạm vi được bảo vệ; nó không tự biến toàn bộ pipeline đa hệ thống thành exactly-once.
