# Kiểm thử trùng lặp, sai thứ tự và hợp đồng schema

Một luồng event có thể nhận cùng một sự kiện nhiều lần, nhận sự kiện không theo thứ tự nghiệp vụ hoặc gặp payload được tạo từ phiên bản schema khác. Đây là các tình huống bình thường trong hệ thống phân tán: producer retry, consumer restart, broker redelivery, replay từ DLQ và triển khai producer/consumer lệch thời điểm đều có thể tạo ra chúng.

Kiểm thử Spring Cloud Stream vì thế cần vượt qua trường hợp “gửi một message và nhận một message”. Bài kiểm thử phải chứng minh consumer xử lý duplicate an toàn, phát hiện hoặc trì hoãn event sai thứ tự, và đọc được các phiên bản dữ liệu nằm trong phạm vi hợp đồng đã cam kết.

## 1. Ba vấn đề cần kiểm thử riêng

| Vấn đề | Biểu hiện | Câu hỏi cần trả lời |
|---|---|---|
| Duplicate delivery | Cùng một event được giao lại một hoặc nhiều lần | Side effect nghiệp vụ có bị áp dụng nhiều lần không? |
| Out-of-order delivery | Event có sequence sau được xử lý trước event trước đó | Trạng thái cuối có đúng và có phát hiện được khoảng trống không? |
| Schema incompatibility | Producer và consumer dùng cấu trúc dữ liệu khác phiên bản | Consumer cũ/mới có đọc được dữ liệu trong giai đoạn rollout không? |

Ba vấn đề có thể xuất hiện đồng thời. Ví dụ consumer nhận event sequence 12 trước sequence 11, xử lý 12 thất bại, broker redeliver 12 và sau đó DLQ replay lại 11. Nếu consumer không có idempotency, sequence guard và schema compatibility test, dữ liệu có thể bị cập nhật sai dù từng lần xử lý riêng lẻ đều không ném exception.

## 2. Vì sao một event có thể được giao nhiều lần?

Duplicate không nhất thiết là lỗi của broker. Nó thường xuất hiện từ các failure window giữa publish, xử lý nghiệp vụ và ghi nhận tiến độ:

- Producer gửi record nhưng không nhận được xác nhận kịp thời, nên retry. Broker có thể đã nhận lần gửi trước.
- Consumer hoàn tất cập nhật database rồi process dừng trước khi offset/ack được ghi nhận. Khi khởi động lại, record được giao lại.
- Consumer timeout hoặc mất kết nối trong khi broker chưa biết chắc ứng dụng đã xử lý xong.
- Retry policy, redelivery, DLQ replay hoặc thao tác vận hành phát lại cùng event.
- Producer phát cùng một event nghiệp vụ hai lần do retry ở tầng ứng dụng hoặc job chạy lại.

Vì vậy, không thể suy ra “một lần gửi” đồng nghĩa “một lần side effect”. Hãy thiết kế consumer theo hướng idempotent: cùng một event được xử lý lại nhiều lần vẫn tạo ra kết quả nghiệp vụ tương đương với xử lý một lần.

### 2.1. Event ID phải ổn định

Mỗi event nên có một định danh duy nhất và ổn định qua retry/replay, ví dụ `eventId`. Không tạo UUID mới mỗi lần producer retry cùng một thao tác nghiệp vụ; nếu làm vậy, consumer không nhận ra hai message là cùng một event.

Một envelope đơn giản:

```java
public record OrderPlaced(
        UUID eventId,
        String orderId,
        long sequence,
        int schemaVersion,
        Instant occurredAt,
        BigDecimal total,
        String currency) {
}
```

`eventId` nhận diện lần phát sinh event. `orderId` xác định aggregate nghiệp vụ. `sequence` biểu diễn thứ tự event trong phạm vi một đơn hàng. `schemaVersion` có thể giúp quan sát hoặc chọn cách chuyển đổi, nhưng không thay thế schema registry/version metadata của serializer. `occurredAt` là thời điểm nghiệp vụ, không nhất thiết là thời điểm consumer nhận message.

## 3. Idempotent consumer bằng Inbox/Processed Event

Một cách phổ biến là lưu `eventId` đã xử lý trong cùng database transaction với side effect nghiệp vụ. Bảng inbox cần unique constraint trên định danh event trong phạm vi consumer. Khi nhận event:

1. Thử ghi `eventId` vào inbox.
2. Nếu event đã tồn tại, coi đây là duplicate và kết thúc mà không lặp side effect.
3. Nếu event mới, cập nhật dữ liệu nghiệp vụ trong cùng transaction.
4. Commit transaction. Chỉ sau khi transaction này thành công, message mới được xem là đã xử lý ở tầng nghiệp vụ.

Ví dụ schema cho PostgreSQL:

```sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Khóa chính gồm `consumer_name` và `event_id` vì cùng một event có thể được nhiều consumer độc lập xử lý một lần. Nếu mỗi consumer có database hoặc inbox riêng, `event_id` đơn lẻ cũng có thể đủ; hãy chọn uniqueness scope phù hợp với kiến trúc.

```java
@Service
public class OrderProjectionService {

    private final JdbcTemplate jdbc;

    public OrderProjectionService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean applyOnce(OrderPlaced event) {
        int inserted = jdbc.update("""
                INSERT INTO processed_event
                    (consumer_name, event_id, event_type, processed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (consumer_name, event_id) DO NOTHING
                """,
                "order-projection",
                event.eventId(),
                "OrderPlaced",
                OffsetDateTime.now(ZoneOffset.UTC));

        if (inserted == 0) {
            return false; // Event này đã được áp dụng trước đó.
        }

        jdbc.update("""
                UPDATE orders
                   SET total = ?, last_event_sequence = ?
                 WHERE order_id = ?
                """,
                event.total(), event.sequence(), event.orderId());

        return true;
    }
}
```

Đoạn SQL dùng cú pháp PostgreSQL `ON CONFLICT`. Với database khác, dùng cơ chế insert-if-absent tương ứng nhưng vẫn phải dựa vào unique constraint ở database. Không chỉ gọi `existsById()` rồi mới `save()`: hai consumer đồng thời có thể cùng thấy “chưa tồn tại” và cùng áp dụng side effect nếu database không bảo vệ uniqueness.

Consumer Spring Cloud Stream có thể nhận payload hoặc `Message<T>`:

```java
@Bean
Consumer<OrderPlaced> projectOrder(OrderProjectionService service) {
    return service::applyOnce;
}
```

Với `Consumer<T>`, return value của service không trở thành output message. Nếu cần log duplicate, metric hoặc phân loại event, có thể dùng `Consumer<Message<OrderPlaced>>` và đọc `eventId` từ payload/header. Không đưa toàn bộ payload hoặc thông tin nhạy cảm vào log.

### 3.1. Transaction phải bao phủ inbox và side effect

Ghi inbox ở transaction A rồi cập nhật đơn hàng ở transaction B tạo ra failure window: inbox có thể được commit nhưng cập nhật nghiệp vụ thất bại. Lần redelivery tiếp theo thấy event đã có trong inbox và bỏ qua, khiến nghiệp vụ không bao giờ được cập nhật.

Ngược lại, cập nhật nghiệp vụ trước rồi ghi inbox ở transaction khác có thể khiến side effect bị lặp nếu process dừng giữa hai bước. Hãy đặt cả hai thao tác trong cùng transaction database, dùng cùng transaction manager và bảo đảm method được gọi qua Spring proxy. Với side effect bên ngoài database như thanh toán, email hoặc REST API, cần idempotency key ở dịch vụ đích hoặc một workflow/outbox phù hợp.

### 3.2. Idempotency ở producer không thay thế idempotency ở consumer

Kafka producer idempotence có thể giảm duplicate do retry ở producer protocol trong phạm vi producer session/sequence semantics. Nó không deduplicate event nghiệp vụ được phát lại sau restart, từ một job chạy lại, từ DLQ hoặc từ một producer khác. RabbitMQ publisher confirms và Pulsar producer send acknowledgements cũng không tự bảo đảm side effect consumer chỉ xảy ra một lần.

Hãy giữ event ID ổn định và thiết kế consumer idempotent ngay cả khi producer/broker có tính năng chống duplicate riêng.

## 4. Kiểm thử duplicate bằng Test Binder

Test Binder cho phép gửi cùng một payload nhiều lần vào input binding để kiểm tra logic idempotency mà không cần broker thật. Ví dụ test gửi cùng `eventId` hai lần và xác nhận projection chỉ được cập nhật một lần.

```java
@SpringBootTest(properties = {
        "spring.cloud.function.definition=projectOrder"
})
@Import(TestChannelBinderConfiguration.class)
class DuplicateOrderEventTest {

    @Autowired
    InputDestination input;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void appliesSameEventOnlyOnce() {
        UUID eventId = UUID.fromString("d8f6aeb0-34a1-4f30-a94f-4e2f65dcb210");
        OrderPlaced event = new OrderPlaced(
                eventId, "order-42", 1, 1,
                Instant.parse("2026-11-24T08:00:00Z"),
                new BigDecimal("250000"), "VND");

        input.send(new GenericMessage<>(event), "projectOrder-in-0");
        input.send(new GenericMessage<>(event), "projectOrder-in-0");

        await().atMost(Duration.ofSeconds(3)).untilAsserted(() -> {
            Integer count = jdbc.queryForObject("""
                    SELECT COUNT(*) FROM processed_event
                     WHERE consumer_name = 'order-projection' AND event_id = ?
                    """, Integer.class, eventId);
            assertThat(count).isEqualTo(1);
        });
    }
}
```

Ví dụ dùng Awaitility (`await`) và AssertJ (`assertThat`); cần thêm các thư viện test tương ứng nếu dự án chưa có. Test context phải dùng database test được cô lập và dọn dữ liệu giữa các test. Với function đồng bộ trong Test Binder, assertion có thể chạy ngay sau `send`; dùng điều kiện chờ hữu hạn nếu channel hoặc side effect được xử lý bất đồng bộ.

Test này xác nhận logic consumer xử lý hai lần gửi cùng event. Nó không chứng minh broker thật sẽ redeliver record sau crash, cũng không xác nhận offset/ack được commit đúng. Những hành vi đó cần integration test với broker tương ứng.

## 5. Phát hiện event sai thứ tự bằng sequence

Ordering cần được xác định theo phạm vi nghiệp vụ. Thông thường, ta cần bảo toàn thứ tự của các event thuộc cùng aggregate, chẳng hạn cùng `orderId` hoặc `accountId`, chứ không cần một thứ tự toàn cục cho mọi event trong hệ thống.

Mỗi aggregate có thể tăng `sequence` đơn điệu:

| Event | Aggregate | Sequence | Ý nghĩa |
|---|---|---:|---|
| `OrderPlaced` | `order-42` | 1 | Đơn hàng được tạo |
| `OrderPaid` | `order-42` | 2 | Thanh toán thành công |
| `OrderPacked` | `order-42` | 3 | Đã đóng gói |
| `OrderShipped` | `order-42` | 4 | Đã giao cho vận chuyển |

Nếu consumer nhận sequence 3 trước sequence 2, có thể nó đang thiếu event cần thiết để chuyển trạng thái hợp lệ. Chỉ dựa vào timestamp không đủ vì đồng hồ giữa producer có thể lệch và event có thể đến muộn.

Quy tắc xử lý cơ bản khi trạng thái hiện tại có `lastSequence`:

| Điều kiện | Diễn giải | Hành động thường dùng |
|---|---|---|
| `incoming == lastSequence + 1` | Event kế tiếp đúng thứ tự | Áp dụng và tăng sequence |
| `incoming <= lastSequence` | Duplicate hoặc event cũ | Bỏ qua an toàn nếu đã xử lý/được supersede theo hợp đồng |
| `incoming > lastSequence + 1` | Có khoảng trống sequence | Chưa áp dụng; lưu chờ, retry hoặc yêu cầu replay event thiếu |

Không phải mọi event đều cần sequence liên tục. Nếu producer phát nhiều loại event độc lập hoặc sequence tăng theo một phạm vi khác, consumer phải hiểu đúng hợp đồng sequence trước khi dùng quy tắc trên.

### 5.1. Kiểm tra sequence nguyên tử

Kiểm tra `lastSequence` rồi update trong hai câu lệnh không có khóa/điều kiện có thể bị race khi hai worker xử lý cùng aggregate đồng thời. Dùng optimistic locking, row lock hoặc câu lệnh update có điều kiện để bảo vệ chuyển trạng thái.

Ví dụ SQL minh họa cập nhật chỉ khi sequence đầu vào là kế tiếp:

```sql
UPDATE order_projection
   SET status = :new_status,
       last_sequence = :incoming_sequence
 WHERE order_id = :order_id
   AND last_sequence = :incoming_sequence - 1;
```

Nếu số hàng cập nhật bằng 1, event được áp dụng. Nếu bằng 0, đọc trạng thái hiện tại để phân loại duplicate/stale hay gap. Thao tác ghi inbox và cập nhật projection vẫn phải nằm trong transaction thống nhất; nếu phát hiện gap, không đánh dấu event là đã xử lý xong trừ khi đã lưu nó vào một bảng pending có thể phục hồi.

## 6. Xử lý sequence gap thay vì bỏ mất event

Giả sử consumer đã xử lý sequence 1 và nhận sequence 3. Có một số chiến lược:

1. **Retry có giới hạn:** giữ record chưa được xác nhận và thử lại sau khi event 2 có thể đã tới. Cách này cần chú ý partition blocking và retry semantics của broker.
2. **Durable pending inbox:** lưu sequence 3 vào bảng pending trong transaction, sau đó chờ sequence 2. Khi sequence 2 đến, xử lý tiếp các event liên tiếp đang chờ.
3. **Replay từ nguồn:** yêu cầu producer/event store phát lại sequence còn thiếu.
4. **Cách ly:** đưa event vào luồng xử lý lỗi có metadata đầy đủ nếu gap kéo dài hoặc vi phạm hợp đồng.

Không nên xác nhận sequence 3 rồi bỏ nó chỉ vì sequence 2 chưa tới. Nếu đã ack/commit và không lưu bền vững, event 3 có thể mất khỏi luồng xử lý dù broker không còn giao lại.

Một pending table có thể dùng unique key `(aggregate_id, sequence)` để ngăn cùng một sequence được lưu hai lần. Khi sequence kế tiếp tới, worker xử lý theo thứ tự và xóa pending record sau khi side effect đã commit. Cần giới hạn số pending event, tuổi gap và chính sách cảnh báo để một event thiếu không làm backlog tăng vô hạn.

Điểm quan trọng là phân biệt **đã nhận bền vững** với **đã áp dụng nghiệp vụ**. Nếu sequence 3 đến trước sequence 2, có thể ghi sequence 3 vào `pending_event` rồi xác nhận message sau khi transaction lưu pending commit. Không ghi sequence 3 vào bảng `processed_event` dành cho event đã áp dụng; nếu làm vậy, khi worker quay lại xử lý sequence 3 sau sequence 2, deduplication sẽ bỏ qua nó. Khi sequence 2 tới, transaction áp dụng sequence 2, tìm event kế tiếp trong pending, áp dụng sequence 3 và chuyển từng event sang trạng thái completed. Việc cập nhật projection, trạng thái pending và processed marker phải có ranh giới transaction rõ ràng.

## 7. Ordering phụ thuộc partition và concurrency

Broker thường bảo đảm thứ tự trong phạm vi hẹp, không phải thứ tự toàn hệ thống:

| Broker | Phạm vi ordering cần thiết kế |
|---|---|
| Kafka | Thứ tự record trong một partition. Dùng key ổn định để các event của cùng aggregate được đưa về cùng partition. Không có total order giữa các partition. |
| RabbitMQ | Queue giữ thứ tự enqueue/delivery theo semantics của queue, nhưng nhiều consumer, redelivery/requeue, priority và xử lý đồng thời có thể làm thứ tự hoàn tất nghiệp vụ khác thứ tự nhận. |
| Pulsar | Ordering phụ thuộc subscription type, partitioned topic, producer batching và key-based routing. Nếu cần ordering theo key, chọn chế độ/key phù hợp và xác minh với cấu hình cụ thể. |

Với Kafka, key thường là `orderId` hoặc `accountId`, không phải một UUID ngẫu nhiên cho mỗi event. Nếu key thay đổi giữa các event của cùng aggregate, chúng có thể vào partition khác nhau và mất ordering theo aggregate.

Concurrency cũng ảnh hưởng thứ tự hoàn tất. Một consumer có thể nhận record A trước B nhưng chuyển A và B sang hai worker thread; B hoàn tất trước A. Nếu nghiệp vụ yêu cầu tuần tự theo key, xử lý tuần tự theo partition/key hoặc dùng cơ chế sequencing/pending state. Không giả định thứ tự nhận luôn bằng thứ tự side effect hoàn tất.

## 8. Kiểm thử out-of-order và gap

Một bộ test nên đưa event theo nhiều thứ tự khác nhau:

| Kịch bản | Input | Kết quả mong đợi |
|---|---|---|
| Đúng thứ tự | 1, 2, 3 | Trạng thái cuối phản ánh 3 |
| Duplicate | 1, 2, 2, 3 | Event 2 chỉ áp dụng một lần |
| Đảo hai event | 1, 3, 2 | 3 được giữ chờ; sau 2 có thể áp dụng tiếp 3 |
| Event cũ đến muộn | 1, 2, 1 | Event 1 không làm lùi trạng thái |
| Gap không được lấp | 1, 3 rồi hết thời gian | 3 vẫn được lưu pending/cách ly và có cảnh báo |
| Hai aggregate xen kẽ | A1, B1, A2, B2 | Mỗi aggregate giữ đúng sequence độc lập |
| Concurrent duplicate | Hai worker cùng nhận event 2 | Unique constraint/locking chỉ cho một side effect |

Với Test Binder, có thể gửi các message theo thứ tự mong muốn để kiểm tra logic state machine. Để kiểm tra ordering theo partition, competing consumers, redelivery và concurrency thực tế, cần broker integration test. Đặc biệt, hãy test một key có nhiều event và nhiều key độc lập để tránh vô tình tuần tự hóa toàn bộ hệ thống.

## 9. Hợp đồng schema giữa producer và consumer

Schema mô tả cấu trúc payload mà producer phát và consumer chấp nhận. Hợp đồng nên xác định:

- Tên event và ý nghĩa nghiệp vụ.
- Field bắt buộc, field tùy chọn, kiểu dữ liệu và đơn vị.
- Quy tắc nullability và default.
- Event ID, aggregate ID, sequence và timestamp.
- Cách thêm, đổi tên hoặc loại bỏ field.
- Phiên bản serializer/schema và chính sách tương thích.
- Cách consumer xử lý field chưa biết hoặc giá trị enum mới.

Ví dụ JSON event:

```json
{
  "eventId": "d8f6aeb0-34a1-4f30-a94f-4e2f65dcb210",
  "eventType": "OrderPlaced",
  "schemaVersion": 2,
  "orderId": "order-42",
  "sequence": 1,
  "occurredAt": "2026-11-24T08:00:00Z",
  "total": 250000,
  "currency": "VND"
}
```

Không để mỗi consumer tự suy đoán schema từ payload hiện tại. Producer và consumer cần chia sẻ một hợp đồng được version hóa và có test xác nhận.

## 10. Backward, forward và full compatibility

Các registry/schema tooling thường định nghĩa các chế độ tương thích. Cách diễn đạt chính xác phụ thuộc công cụ, nhưng ý nghĩa tổng quát như sau:

| Chế độ | Câu hỏi chính | Ý nghĩa trong rollout |
|---|---|---|
| Backward | Consumer dùng schema mới có đọc được dữ liệu được ghi bằng schema cũ không? | Có thể triển khai consumer mới trước producer mới |
| Forward | Consumer cũ có đọc được dữ liệu được ghi bằng schema mới không? | Có thể triển khai producer mới trước khi mọi consumer được nâng cấp |
| Full | Schema cũ và mới đọc được dữ liệu của nhau theo hai chiều không? | Hỗ trợ rollout hỗn hợp linh hoạt hơn |

Một số registry áp dụng kiểm tra với phiên bản gần nhất hoặc toàn bộ lịch sử (`BACKWARD`/`BACKWARD_TRANSITIVE` và các biến thể). Hãy đọc đúng định nghĩa của registry đang dùng; không suy ra chính sách triển khai chỉ từ tên mode.

### 10.1. Thêm field mới

Thêm một field tùy chọn thường an toàn hơn field bắt buộc mới. Consumer mới cần xử lý trường hợp record cũ không có field. Nếu dùng Avro, reader schema có thể cần default để đọc record được ghi bằng schema cũ. Với JSON Schema, `default` thường là annotation; validator không tự chèn giá trị mặc định vào payload. Ứng dụng phải tự áp dụng fallback khi field vắng mặt.

### 10.2. Xóa hoặc đổi tên field

Xóa field có thể làm consumer mới không còn đọc được record cũ nếu code vẫn kỳ vọng field đó. Đổi tên thường tương đương xóa field cũ và thêm field mới; không giả định registry tự hiểu hai tên là một. Cách an toàn hơn là giai đoạn chuyển tiếp: thêm field mới, producer ghi cả hai trong thời gian tương thích, consumer chuyển sang đọc field mới, sau đó mới ngừng field cũ theo chính sách.

### 10.3. Đổi kiểu dữ liệu hoặc ý nghĩa field

Đổi `amount` từ integer sang string, đổi đơn vị từ đồng sang xu, hoặc đổi timezone/ý nghĩa timestamp có thể phá hợp đồng ngay cả khi JSON vẫn parse được. Thay đổi ý nghĩa nghiệp vụ thường nguy hiểm hơn thay đổi cú pháp. Hãy dùng field/version mới hoặc event type mới khi semantics không còn tương thích.

## 11. Quy tắc riêng của Avro, JSON Schema và Protobuf

| Format | Điểm cần kiểm tra khi evolution |
|---|---|
| Avro | Writer/reader schema resolution, default cho field mới, union/nullability, tên record/namespace và compatibility của registry |
| JSON Schema | `required`, `additionalProperties`, type/format, enum, nullable và cách ứng dụng xử lý field vắng mặt; `default` không tự sửa payload |
| Protobuf | Không tái sử dụng field number đã xóa; dùng `reserved` cho number/name cũ; kiểm tra wire compatibility và semantics của enum/oneof |

Không dùng một quy tắc chung cho mọi format. Ví dụ thêm field có default trong Avro khác với thêm `default` annotation trong JSON Schema. Protobuf có thể giữ wire compatibility theo field number nhưng vẫn có thể thay đổi ý nghĩa nghiệp vụ nếu tái sử dụng một field theo cách sai.

## 12. Message conversion và native Serde là hai lớp khác nhau

Spring Cloud Stream có thể chuyển đổi payload dựa trên `content-type` và message converter. Với Kafka, ứng dụng cũng có thể dùng native Kafka serializer/deserializer hoặc Serde, đặc biệt khi dùng Kafka Streams Binder. Với Pulsar và RabbitMQ, serializer/converter cũng có thể được cấu hình theo binder.

Một test gửi trực tiếp Java object vào `InputDestination` có thể bỏ qua một phần đường đi serialize/deserialize trên wire. Vì vậy, cần phân biệt:

- Test business function với object đã được tạo sẵn.
- Test message conversion với payload bytes/String và content type thực tế.
- Test serializer/Serde với đúng implementation mà producer/consumer production dùng.
- Test schema registry authentication, schema lookup và compatibility bằng môi trường registry tương đương production.

Không kết luận schema contract an toàn chỉ vì function nhận được object trong Test Binder. Test Binder không tự chứng minh serializer, schema registry hoặc broker native Serde đang dùng đúng schema.

## 13. Kiểm thử schema contract bằng fixture phiên bản

Lưu fixture đại diện cho các phiên bản schema còn được hỗ trợ, ví dụ `order-placed-v1.json` và `order-placed-v2.json`. Test consumer mới đọc các fixture cũ và mới; test producer mới xác nhận payload phát ra đáp ứng schema hiện hành.

Ví dụ test deserialization với Jackson:

```java
class OrderPlacedSchemaTest {

    private final ObjectMapper mapper = new ObjectMapper()
            .findAndRegisterModules();

    @Test
    void readsSupportedV1Payload() throws Exception {
        String json = Files.readString(
                Path.of("src/test/resources/contracts/order-placed-v1.json"));

        OrderPlaced event = mapper.readValue(json, OrderPlaced.class);

        assertThat(event.orderId()).isEqualTo("order-42");
    }

    @Test
    void readsCurrentV2Payload() throws Exception {
        String json = Files.readString(
                Path.of("src/test/resources/contracts/order-placed-v2.json"));

        OrderPlaced event = mapper.readValue(json, OrderPlaced.class);

        assertThat(event.sequence()).isEqualTo(1);
        assertThat(event.currency()).isEqualTo("VND");
    }
}
```

Đoạn code minh họa fixture-based deserialization; model và mapper phải phản ánh chính xác cấu hình production, bao gồm unknown fields, date/time module và null handling. Nếu dùng JSON Schema, thêm bước validate fixture và payload producer bằng đúng schema validator. Nếu dùng Avro/Protobuf, dùng serializer/deserializer thực tế và schema tương ứng thay vì chỉ parse JSON.

### 13.1. Kiểm thử compatibility trong CI

Pipeline có thể thực hiện các bước:

1. Validate schema mới theo cú pháp và rule của format.
2. Kiểm tra schema mới với compatibility mode đã cấu hình trong registry.
3. Serialize payload mẫu bằng serializer production.
4. Deserialize payload cũ bằng consumer version mới.
5. Nếu rollout cần producer mới/consumer cũ cùng chạy, kiểm thử chiều ngược lại.
6. Kiểm tra enum, null, default, unknown fields và boundary values.
7. Chỉ publish/register schema sau khi compatibility check thành công theo quy trình release.

Nếu registry hỗ trợ compatibility check qua API/CLI, dùng chính registry hoặc phiên bản test tương thích để CI kiểm tra. Không hard-code một kết luận compatibility dựa trên vài fixture; fixture bổ sung bằng chứng cho các trường hợp nghiệp vụ quan trọng, còn registry kiểm tra rule của schema.

## 14. Contract test ở ranh giới producer/consumer

Producer contract xác nhận event được phát với field, kiểu, event type và semantics đúng. Consumer contract xác nhận ứng dụng đọc được các payload mà producer được phép phát trong giai đoạn tương thích.

Một bảng contract có thể ghi:

| Field | Bắt buộc? | Ý nghĩa | Quy tắc evolution |
|---|---|---|---|
| `eventId` | Có | ID ổn định để deduplicate | Không đổi format/ý nghĩa |
| `orderId` | Có | Aggregate key | Không được tái sử dụng cho đơn khác |
| `sequence` | Có nếu cần ordering | Thứ tự event trong một order | Tăng đơn điệu trong phạm vi order |
| `occurredAt` | Có | Thời điểm nghiệp vụ UTC | Giữ định dạng và đơn vị rõ ràng |
| `total` | Có | Tổng tiền | Không đổi đơn vị âm thầm |
| `currency` | Có | Mã tiền tệ | Giá trị thuộc enum/code set đã công bố |
| `note` | Không | Ghi chú tùy chọn | Consumer phải xử lý khi thiếu/null |

Contract test cần kiểm tra cả cấu trúc và ý nghĩa. Một payload có `total: 250000` vẫn hợp lệ về JSON nhưng sai nghiệp vụ nếu producer hiểu là đồng còn consumer hiểu là xu. Tài liệu schema nên nêu đơn vị, timezone, range và semantics của field.

## 15. Kiểm thử với Test Binder và broker thật

Mỗi lớp test trả lời một câu hỏi khác nhau:

| Lớp test | Có thể xác minh | Không nên dùng để kết luận |
|---|---|---|
| Unit test | Idempotency rule, sequence guard, state transition | Broker redelivery hoặc schema registry thật |
| Spring Cloud Stream Test Binder | Function binding, message conversion cơ bản, duplicate payload gửi nhiều lần | Offset, partition, broker ack, transaction hoặc redelivery sau crash |
| Schema/contract test | Compatibility của schema, fixture cũ/mới, serializer/deserializer | Broker topology và delivery guarantee |
| Broker integration test | Partition/key ordering, retry, redelivery, ack/offset, DLQ và serializer thật | Hành vi production ở tải lớn nếu chưa load test |
| Failure/load test | Crash window, concurrency, throughput, backlog và phục hồi | Tính đúng của mọi schema nếu không chạy contract test |

Test Binder rất hữu ích để kiểm tra function và message contract nhanh. Để xác nhận duplicate do redelivery, cần khởi chạy broker test, gửi record, cho consumer xử lý side effect rồi dừng process trước/giữa bước commit offset theo kịch bản có kiểm soát. Sau restart, xác nhận record có thể được giao lại nhưng side effect chỉ xuất hiện một lần.

## 16. Broker integration test cho duplicate và ordering

Với Kafka, test có thể tạo topic nhiều partition, publish các event cùng key và xác nhận chúng được xử lý theo thứ tự trong partition. Sau đó thử nhiều key để xác nhận các partition có thể xử lý song song. Để test redelivery, mô phỏng process dừng sau database commit nhưng trước offset commit; xác nhận event được đọc lại và inbox unique constraint chặn side effect trùng.

Với RabbitMQ, kiểm thử queue topology, manual ack/nack, requeue, competing consumers và concurrency. Với nhiều consumer hoặc retry, xác nhận thứ tự hoàn tất có thể khác thứ tự enqueue; nếu nghiệp vụ cần ordering, dùng chiến lược queue/consumer phù hợp và sequence guard ở ứng dụng.

Với Pulsar, kiểm thử subscription type, acknowledgement timeout, negative acknowledgement, redelivery và key-based ordering theo cấu hình producer/consumer. Không suy luận hành vi ordering chỉ từ tên subscription; xác minh bằng binder và broker version đang triển khai.

Các tình huống nên có:

- Producer gửi cùng event ID nhiều lần.
- Consumer commit database rồi bị dừng trước khi broker ghi nhận ack/offset.
- Consumer lỗi trước khi commit database.
- Hai event cùng aggregate được xử lý đồng thời.
- Event sequence sau tới trước event sequence trước.
- Replay từ DLQ tạo duplicate của event đã xử lý.
- Producer schema mới phát payload trong khi consumer cũ vẫn đang chạy.
- Consumer mới đọc record được tạo bởi producer schema cũ.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Duplicate làm tăng số dư hoặc tạo đơn hai lần | Không có event ID ổn định hoặc inbox không có unique constraint | Dùng idempotency key và transaction inbox + side effect |
| Hai worker cùng áp dụng một event | Kiểm tra tồn tại rồi ghi không nguyên tử | Dựa vào unique constraint và xử lý conflict trong transaction |
| Event mới đến trước event cũ làm trạng thái lùi | Không kiểm tra sequence hoặc timestamp không đáng tin | Dùng sequence theo aggregate và conditional update |
| Sequence gap bị mất | Consumer ack event sau rồi bỏ event chưa đủ điều kiện | Lưu pending bền vững hoặc retry/replay trước khi đánh dấu hoàn tất |
| Cùng aggregate nằm ở nhiều partition | Key thay đổi hoặc partitioning không nhất quán | Dùng aggregate ID làm key và kiểm tra partitioner |
| Consumer nhận đúng thứ tự nhưng side effect hoàn tất sai thứ tự | Xử lý bất đồng bộ/concurrency không giữ thứ tự | Tuần tự hóa theo key hoặc dùng sequence guard |
| Consumer mới không đọc record cũ | Schema evolution không backward compatible hoặc thiếu default/converter | Thêm compatibility test với fixture và schema registry |
| Consumer cũ lỗi khi producer thêm field | Consumer từ chối unknown field hoặc schema mode không phù hợp | Kiểm tra `additionalProperties`, unknown-field policy và rollout order |
| JSON parse thành công nhưng dữ liệu sai | Field đổi đơn vị/semantics mà không đổi contract | Version hóa semantics và test boundary/domain rules |
| Test Binder pass nhưng broker vẫn redeliver | Test Binder không mô phỏng offset/ack và crash semantics | Bổ sung broker integration test có failure injection |

## 18. Quy trình kiểm thử trước khi phát hành

1. Xác định event ID, aggregate key và sequence semantics cho từng event type.
2. Kiểm tra consumer dùng inbox/idempotency hoặc một cơ chế deduplicate tương đương.
3. Kiểm tra inbox và side effect cùng commit trong transaction database.
4. Xác định ordering cần thiết theo key/partition và cách xử lý gap.
5. Gửi test event theo thứ tự đúng, duplicate, đảo thứ tự và thiếu sequence.
6. Xác định schema format, version và compatibility mode.
7. Chạy contract test với fixture của các phiên bản còn được hỗ trợ.
8. Chạy serializer/deserializer test bằng implementation production.
9. Chạy Test Binder test cho function và message conversion.
10. Chạy broker integration test cho redelivery, ack/offset, partition ordering, retry và DLQ.
11. Mô phỏng restart/concurrency và xác nhận side effect không trùng, state không lùi.
12. Theo dõi duplicate rate, sequence gap, schema validation error và DLQ trong canary rollout.

## 19. Danh sách kiểm tra trước khi triển khai

- [ ] Event có `eventId` ổn định qua retry và replay.
- [ ] Consumer deduplicate bằng unique constraint hoặc cơ chế atomic tương đương.
- [ ] Inbox và side effect database nằm trong cùng transaction.
- [ ] External side effect có idempotency key/workflow riêng.
- [ ] Aggregate key và sequence được định nghĩa rõ.
- [ ] Ordering requirement được giới hạn đúng phạm vi key/partition.
- [ ] Consumer xử lý duplicate, stale event và sequence gap có chủ đích.
- [ ] Pending/gap storage có giới hạn, timeout và cảnh báo.
- [ ] Schema có contract, version và compatibility policy.
- [ ] Có fixture của các schema version còn được hỗ trợ.
- [ ] Serializer/deserializer production được kiểm thử, không chỉ Java object qua Test Binder.
- [ ] CI kiểm tra schema compatibility và producer/consumer contract.
- [ ] Broker integration test bao phủ redelivery, ordering, retry và DLQ.
- [ ] Monitoring có duplicate count, gap age, schema errors và replay outcomes.

Duplicate delivery là đặc tính cần dự liệu của event-driven system; consumer phải idempotent để cùng event không tạo side effect lặp. Ordering cần được xác định theo aggregate/key và được bảo vệ bằng partitioning cùng sequence guard, vì broker không cung cấp một thứ tự toàn cục cho mọi luồng. Schema contract cần được version hóa, kiểm tra backward/forward compatibility và thử bằng serializer thực tế. Kết hợp unit test, Test Binder, contract test và broker integration test giúp phát hiện lỗi ở cả business logic lẫn delivery semantics trước khi phát hành.

## Tài liệu tham khảo

- [Spring Cloud Stream — Testing](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/testing.html)
- [Spring Cloud Stream — Kafka Binder](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/)
- [Apache Kafka — Message Delivery Semantics](https://kafka.apache.org/documentation/#semantics)
- [Apache Avro — Schema Resolution](https://avro.apache.org/docs/current/specification/)
- [Protocol Buffers — Updating A Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
