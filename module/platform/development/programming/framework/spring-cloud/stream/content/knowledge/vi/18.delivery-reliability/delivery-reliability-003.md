# Bảng inbox, khóa duy nhất và kiểm soát thông điệp trùng lặp

Broker trong hệ thống event thường giao message theo mô hình ít nhất một lần (at-least-once). Nếu consumer xử lý xong nhưng bị dừng trước khi xác nhận message hoặc commit offset, broker có thể giao lại message đó. Retry, rebalance, reconnect và replay từ DLQ cũng có thể khiến cùng một event xuất hiện nhiều lần.

Bảng **inbox** lưu dấu event mà một consumer logic đã xử lý. Khóa duy nhất trên định danh event giúp nhiều instance cùng consumer không thực hiện một thay đổi dữ liệu hai lần. Khi bản ghi inbox và thay đổi nghiệp vụ được commit trong cùng transaction cơ sở dữ liệu, redelivery có thể được nhận diện an toàn.

Inbox không biến broker thành hệ thống giao message đúng một lần. Nó tạo ra tính idempotent cho các hiệu ứng nằm trong cùng transaction dữ liệu, đồng thời giúp ứng dụng phục hồi khi broker giao lại message.

## 1. Vì sao consumer phải chịu được message trùng?

Một luồng xử lý phổ biến gồm nhận message, cập nhật database rồi xác nhận với broker:

~~~text
Broker
  |
  v
Consumer nhận event
  |
  v
Cập nhật database
  |
  v
Commit transaction
  |
  v
Ack message / commit offset
~~~

Giả sử database commit thành công nhưng tiến trình dừng trước khi acknowledgment hoặc offset commit hoàn tất. Broker không biết nghiệp vụ đã hoàn tất nên có thể giao lại event. Consumer nhận lần thứ hai và nếu không kiểm tra idempotency, nó có thể cộng tồn kho lần nữa, tạo hóa đơn thứ hai hoặc gửi email lặp.

Một số nguồn gây redelivery/duplicate:

- Consumer xử lý xong nhưng mất kết nối trước khi ack.
- Kafka consumer bị rebalance khi xử lý hoặc commit offset chưa hoàn tất.
- RabbitMQ giao lại message chưa được acknowledge sau khi consumer đóng.
- Pulsar redeliver message chưa được acknowledge hoặc sau negative acknowledgment/ack timeout.
- Producer gửi lại do timeout mà không biết broker đã nhận lần trước hay chưa.
- DLQ được replay hoặc dữ liệu được nạp lại từ một bản sao lưu.

Do đó, “một lần gửi” và “một lần xử lý hiệu ứng nghiệp vụ” là hai khái niệm khác nhau. Consumer cần nhận diện cùng một event qua mọi lần giao lại.

## 2. Phân biệt event ID, message ID và khóa deduplication

Không dùng ID của đối tượng message nội bộ trong framework làm định danh nghiệp vụ. Một message có thể được đóng gói lại hoặc tạo mới khi retry, trong khi event nghiệp vụ vẫn là một sự kiện duy nhất.

| Định danh | Phạm vi | Có phù hợp làm khóa inbox? |
|---|---|---|
| Event ID | Một sự kiện nghiệp vụ do producer tạo | Có, nếu ổn định qua retry/replay |
| Source + Event ID | Một event trong namespace của producer | Có, phù hợp khi nhiều producer có thể trùng ID |
| Spring MessageHeaders.ID | Một đối tượng message trong Spring Messaging | Không nên dùng làm ID nghiệp vụ |
| Kafka offset | Vị trí record trong một topic-partition | Chỉ nhận diện vị trí trong log đó; không phải ID event dùng chung |
| Rabbit delivery tag | Một delivery trên channel | Không ổn định qua lần giao lại |
| Pulsar message ID | Vị trí message theo broker/topic | Có thể dùng để chẩn đoán broker, nhưng contract liên hệ nhiều hệ thống nên có event ID riêng |
| Correlation ID | Nhóm các event trong một quy trình | Không; nhiều event khác nhau có cùng correlation ID |

Producer nên tạo event ID một lần khi tạo event và giữ nguyên ID trong mọi lần publish lại. Nếu ID chỉ duy nhất trong phạm vi producer, dùng cặp `(source, eventId)` làm khóa. Ví dụ `orders-service + evt-1001`.

Không sinh event ID mới cho mỗi lần retry cùng một bản ghi outbox. Nếu ID thay đổi, consumer sẽ xem mỗi lần gửi là một event mới và không thể deduplicate.

## 3. Mô hình bảng inbox

Một bảng inbox cơ bản lưu consumer logic, nguồn phát, event ID và thời điểm xử lý:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(120) NOT NULL,
    source        VARCHAR(200) NOT NULL,
    event_id      VARCHAR(200) NOT NULL,
    payload_hash  CHAR(64) NOT NULL,
    received_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    processed_at  TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (consumer_name, source, event_id)
);
~~~

Khóa chính tổng hợp bảo đảm một consumer logic chỉ ghi nhận một lần cho mỗi event trong namespace nguồn. `payload_hash` giúp phát hiện trường hợp producer tái sử dụng cùng event ID nhưng gửi nội dung khác. `received_at` và `processed_at` phục vụ điều tra, đo độ trễ và chính sách lưu giữ.

Trong mô hình transaction ngắn được trình bày ở bài này, hàng inbox chỉ được commit cùng transaction với thay đổi nghiệp vụ. Nếu nghiệp vụ thất bại và transaction rollback, hàng inbox cũng rollback. Vì vậy, sự tồn tại của hàng inbox có nghĩa hiệu ứng database đã commit thành công.

Tên consumer phải đại diện cho **nhiệm vụ logic**, không phải tên máy hoặc ID instance:

- Các replica của `inventory-projection` dùng cùng `consumer_name`.
- Consumer gửi thông báo dùng `notification-dispatcher` riêng.
- Consumer analytics dùng `sales-analytics` riêng.

Nếu tất cả service dùng chung một consumer name, một service có thể đánh dấu event đã xử lý và khiến service khác bỏ qua event đó. Nếu mỗi replica dùng tên khác nhau, mỗi instance có thể xử lý cùng event một lần.

## 4. Tạo event envelope có định danh ổn định

Ví dụ event envelope mang source và event ID:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record EventEnvelope<T>(
    String eventId,
    String source,
    String eventType,
    Instant occurredAt,
    T data
) {}

public record OrderPlaced(
    String orderId,
    BigDecimal total,
    String currency
) {}
~~~

Producer tạo event ID khi hình thành sự kiện nghiệp vụ:

~~~java
import java.time.Instant;
import java.util.UUID;

public EventEnvelope<OrderPlaced> createOrderEvent(Order order) {
    return new EventEnvelope<>(
        UUID.randomUUID().toString(),
        "orders-service",
        "OrderPlaced",
        Instant.now(),
        new OrderPlaced(
            order.publicId(),
            order.total(),
            order.currency()
        )
    );
}
~~~

Ví dụ trên chỉ gọi một lần cho một event mới. Nếu ứng dụng dùng transactional outbox, hãy lưu envelope cùng transaction nghiệp vụ. Relay đọc lại đúng bản ghi đó và publish với cùng `eventId` và payload khi retry.

Nếu event được tạo lại từ một command đã nhận trước đó, cần bảo đảm command idempotency hoặc lưu event ID đã tạo. Chỉ gọi UUID ngẫu nhiên mỗi lần request đến sẽ tạo event mới khi client gửi lại cùng command.

## 5. Gắn inbox với consumer Spring Cloud Stream

Spring Cloud Stream có thể nhận envelope bằng một bean `Consumer`. Consumer chuyển công việc cho một service có transaction riêng:

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumers {

    @Bean
    Consumer<EventEnvelope<OrderPlaced>> orderPlacedConsumer(
            OrderInboxService inboxService) {
        return inboxService::handle;
    }
}
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: orderPlacedConsumer

    stream:
      bindings:
        orderPlacedConsumer-in-0:
          destination: orders.placed
          group: inventory-projection
          content-type: application/json
~~~

Mọi replica của nhiệm vụ inventory dùng cùng group và cùng consumer name trong bảng inbox. Nếu có một consumer logic khác cần nhận event độc lập, nó có group và inbox namespace riêng.

Event ID nằm trong contract envelope nên service có thể đọc được mà không phụ thuộc vào header do binder hoặc Spring Messaging tạo. Nếu hệ thống đặt event ID trong header, hãy bảo đảm header đó được truyền qua binder và kiểm tra nó có mặt trước khi xử lý. Không dùng `MessageHeaders.ID` thay thế event ID nghiệp vụ.

## 6. Ghi inbox và thay đổi nghiệp vụ trong cùng transaction

Quy tắc quan trọng nhất là **insert inbox và cập nhật dữ liệu nghiệp vụ phải cùng transaction cơ sở dữ liệu**. Không commit inbox trước rồi mới xử lý nghiệp vụ ở transaction khác, vì tiến trình có thể dừng giữa hai bước: lần giao sau thấy inbox đã có và bỏ qua event dù hiệu ứng nghiệp vụ chưa xảy ra.

Ví dụ sau dùng cú pháp PostgreSQL `ON CONFLICT DO NOTHING`. Đây là cách insert nguyên tử; với database khác cần dùng cú pháp upsert/insert-ignore tương ứng.

~~~java
import java.util.Objects;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderInboxService {

    private static final String CONSUMER = "inventory-projection";

    private final JdbcTemplate jdbc;
    private final OrderRepository orders;
    private final PayloadFingerprint fingerprint;

    public OrderInboxService(
            JdbcTemplate jdbc,
            OrderRepository orders,
            PayloadFingerprint fingerprint) {
        this.jdbc = jdbc;
        this.orders = orders;
        this.fingerprint = fingerprint;
    }

    @Transactional
    public void handle(EventEnvelope<OrderPlaced> event) {
        String hash = fingerprint.sha256(event.data());

        int inserted = jdbc.update("""
            INSERT INTO consumer_inbox (
                consumer_name, source, event_id, payload_hash,
                received_at, processed_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (consumer_name, source, event_id) DO NOTHING
            """,
            CONSUMER,
            event.source(),
            event.eventId(),
            hash
        );

        if (inserted == 0) {
            String previousHash = jdbc.queryForObject("""
                SELECT payload_hash
                FROM consumer_inbox
                WHERE consumer_name = ?
                  AND source = ?
                  AND event_id = ?
                """,
                String.class,
                CONSUMER,
                event.source(),
                event.eventId()
            );

            if (!Objects.equals(previousHash, hash)) {
                throw new EventIdentityConflictException(
                    "Same source/eventId arrived with a different payload"
                );
            }

            // Event đã được xử lý trước đó: không lặp thay đổi tồn kho.
            return;
        }

        // Thay đổi nghiệp vụ nằm trong cùng transaction với inbox insert.
        orders.applyPlacedEvent(event.data());
    }
}
~~~

`PayloadFingerprint` là một adapter ứng dụng tạo SHA-256 từ biểu diễn payload chuẩn hóa:

~~~java
public interface PayloadFingerprint {
    String sha256(Object payload);
}
~~~

Khi triển khai, cần dùng serialization canonical hoặc quy tắc chuẩn hóa ổn định để cùng một payload luôn tạo cùng hash. Không băm trực tiếp một JSON có thứ tự field hoặc định dạng số thay đổi ngẫu nhiên giữa các lần serialize.

Ví dụ exception khi cùng event ID có nội dung khác:

~~~java
public class EventIdentityConflictException extends RuntimeException {
    public EventIdentityConflictException(String message) {
        super(message);
    }
}
~~~

Nếu `inserted == 1`, event mới được ghi nhận và thay đổi nghiệp vụ tiếp tục. Nếu `inserted == 0`, khóa đã tồn tại. Cùng hash nghĩa là redelivery/replay của cùng nội dung; service bỏ qua side effect. Hash khác nghĩa là producer đã tái sử dụng event ID cho payload khác hoặc có lỗi contract; cần cảnh báo và cách ly thay vì coi đó là duplicate bình thường.

Đặt `EventIdentityConflictException` trong file Java riêng cùng package. Các kiểu `OrderRepository`, `OrderPlaced`, `EventEnvelope` và `PayloadFingerprint` cũng là các thành phần ứng dụng được định nghĩa riêng.

## 7. Vì sao phải dùng unique constraint thay vì SELECT rồi INSERT?

Một cách làm tưởng như đơn giản là:

1. SELECT xem event ID đã có chưa.
2. Nếu chưa có thì INSERT.
3. Thực hiện nghiệp vụ.

Cách này có race condition khi hai instance nhận cùng event gần như đồng thời:

~~~text
Instance A                    Instance B
    |                             |
    | SELECT -> chưa có            |
    |                             | SELECT -> chưa có
    | INSERT                      |
    |                             | INSERT
    |                             |
    v                             v
Có thể cả hai cùng chạy side effect
~~~

Unique constraint ở database là trọng tài cuối cùng. Nó bảo đảm chỉ một transaction có thể tạo khóa `(consumer_name, source, event_id)`. Với PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` cho phép xử lý trường hợp cạnh tranh mà không cần bắt lỗi unique violation như luồng điều khiển bình thường.

Khi dùng database khác:

- Chọn cú pháp insert-ignore/upsert có semantics nguyên tử.
- Hoặc dùng một cơ chế insert có kiểm soát lỗi duplicate phù hợp với transaction manager và driver.
- Không giả định một câu SELECT trước INSERT đủ để bảo vệ khi nhiều instance chạy song song.
- Kiểm tra mức isolation, unique index và cách database xử lý transaction cạnh tranh.

Không bắt một lỗi constraint rồi tiếp tục dùng transaction nếu database hoặc JPA provider đã đánh dấu transaction rollback-only. Cần dùng câu lệnh upsert nguyên tử hoặc cơ chế transaction/savepoint phù hợp.

## 8. Điều gì xảy ra ở các failure window?

Bảng dưới mô tả cách inbox phối hợp với transaction và broker acknowledgment:

| Thời điểm sự cố | Trạng thái database | Khi broker giao lại |
|---|---|---|
| Trước khi insert inbox | Chưa có inbox, chưa có side effect | Consumer xử lý như event mới |
| Sau insert nhưng trước cập nhật nghiệp vụ, transaction rollback | Inbox insert rollback | Consumer xử lý lại từ đầu |
| Sau cập nhật nghiệp vụ nhưng trước database commit, transaction rollback | Cả inbox và nghiệp vụ rollback | Consumer xử lý lại từ đầu |
| Sau database commit nhưng trước broker ack/offset commit | Inbox và nghiệp vụ đã commit | Unique key phát hiện duplicate, bỏ qua side effect |
| Sau broker ack/offset commit | Inbox và nghiệp vụ đã commit | Không cần giao lại trong luồng bình thường |

Điều kiện để bảng này đúng là transaction inbox và nghiệp vụ thật sự dùng cùng database transaction manager, còn broker acknowledgment chỉ được hoàn tất sau khi handler/transaction thành công theo semantics binder đang cấu hình. Không có transaction phân tán tự động giữa database và broker chỉ vì dùng `@Transactional`.

Hãy kiểm tra ack/commit mode của binder và thử nghiệm failure window thực tế. Với Kafka, quan sát offset commit và redelivery sau khi kill consumer. Với RabbitMQ, quan sát acknowledgment và redelivery. Với Pulsar, kiểm tra acknowledgment và redelivery theo subscription. Không tuyên bố exactly-once end-to-end chỉ từ một bảng inbox.

## 9. Consumer identity và phạm vi deduplication

Khóa inbox phải phản ánh đơn vị công việc logic. Cùng event có thể cần được nhiều consumer xử lý độc lập:

~~~text
Event evt-1001
      |
      +---- inventory-projection / evt-1001
      |
      +---- notification-dispatcher / evt-1001
      |
      +---- sales-analytics / evt-1001
~~~

Mỗi consumer có một khóa inbox riêng. Nhờ vậy, inventory xử lý xong không làm notification bỏ qua event.

Giữ `consumer_name` ổn định khi deploy phiên bản mới nếu đó vẫn là cùng một nhiệm vụ và cần tiếp tục deduplicate. Nếu đổi consumer name, database coi đó là một consumer mới; event cũ có thể được xử lý lại. Điều này có thể hữu ích khi cố ý dựng read model mới, nhưng phải dùng bảng/schema đích riêng hoặc có kế hoạch replay và side effect rõ ràng.

Không gắn tên pod, hostname, process ID hoặc instance ID vào consumer name. Các giá trị này thay đổi khi scale/restart và làm mỗi instance có một vùng deduplication riêng, phá vỡ mục tiêu chia sẻ idempotency giữa các replica.

## 10. Event ID trùng nhưng payload khác là lỗi contract

Một event ID duy nhất không được đại diện cho hai nội dung khác nhau. Nếu cùng `source` và `eventId` xuất hiện với hash khác, có thể xảy ra:

- Producer tạo event ID không ổn định hoặc tái sử dụng ID.
- Hai producer dùng chung source dù không cùng namespace.
- Relay/outbox bị cập nhật payload sau khi event đã được công bố.
- Dữ liệu bị biến đổi trên đường truyền hoặc có producer gửi sai contract.

Không bỏ qua trường hợp này như duplicate thông thường. Ghi metric riêng, lưu dấu vết event gốc và event mới theo chính sách bảo mật, sau đó điều tra producer. Không ghi đè payload hash cũ để “sửa” inbox vì sẽ che giấu vi phạm định danh.

Hash chỉ là kiểm tra nhất quán bổ sung. Nó không thay thế schema validation, chữ ký hoặc cơ chế xác thực nguồn nếu hệ thống có yêu cầu bảo mật cao.

## 11. Side effect bên ngoài database cần cơ chế riêng

Transaction inbox chỉ bảo vệ hiệu ứng nằm trong cùng transaction database. Nếu consumer gọi API thanh toán, gửi email hoặc publish một event mới, database rollback không thể hoàn tác hành động bên ngoài đã thành công.

Ví dụ nguy hiểm:

~~~text
BEGIN DB TRANSACTION
  INSERT inbox
  CALL payment API  ---> API đã trừ tiền thành công
  UPDATE order
  DB COMMIT thất bại
ROLLBACK
~~~

Broker giao lại event. Inbox insert đã rollback nên consumer gọi payment API lần nữa. Khách hàng có thể bị trừ tiền hai lần.

Các cách xử lý:

- **Idempotency key của dịch vụ đích:** gửi khóa ổn định như `consumerName:source:eventId`; API đích phải lưu và deduplicate khóa đó.
- **Transactional outbox:** ghi lệnh/event cần phát vào outbox cùng transaction với inbox và thay đổi nghiệp vụ; relay gửi sau commit.
- **Workflow/saga có trạng thái:** lưu trạng thái từng bước, retry và đối soát khi kết quả API không rõ.
- **Inbox state machine:** với tác vụ dài, lưu trạng thái nhận, đang xử lý, hoàn tất, số lần thử và lease để worker khác có thể phục hồi.

Không giữ transaction database mở trong thời gian chờ một API chậm nếu có thể tránh. Với tác vụ dài, dùng state machine có lease và idempotency ở dịch vụ đích. Chỉ đánh dấu hoàn tất sau khi có kết quả có thể xác minh.

## 12. Tách inbox và outbox để bảo đảm luồng event hai chiều

Inbox ghi nhận event đã nhận; outbox ghi nhận event hoặc command cần phát. Khi một consumer xử lý event đầu vào và cần phát event tiếp theo, có thể ghi cả inbox, cập nhật domain và outbox trong cùng transaction:

~~~text
Một database transaction
  |
  +-- INSERT consumer_inbox
  |
  +-- UPDATE orders
  |
  +-- INSERT outbox_events
          |
          v
       COMMIT
          |
          v
    Outbox relay publish
          |
          v
        Broker
~~~

Nếu transaction rollback, cả inbox, thay đổi domain và outbox đều rollback. Nếu commit thành công nhưng relay chưa gửi, outbox vẫn còn để gửi sau. Nếu relay gửi xong nhưng chưa đánh dấu đã gửi, nó có thể publish lại; consumer tiếp theo vẫn cần inbox/idempotency.

Inbox và outbox giải quyết hai hướng khác nhau của cùng ranh giới tích hợp. Chúng không loại bỏ mọi duplicate; chúng giúp biến duplicate thành thao tác an toàn và có thể phục hồi.

## 13. Trường hợp xử lý dài: trạng thái, lease và phục hồi

Với công việc ngắn có thể hoàn tất trong một transaction database, mô hình insert inbox + business update cùng transaction là đơn giản nhất. Với công việc kéo dài, không nên giữ transaction mở trong suốt thời gian xử lý. Có thể dùng bảng inbox mở rộng:

| Trường | Mục đích |
|---|---|
| `consumer_name, source, event_id` | Khóa duy nhất |
| `status` | RECEIVED, PROCESSING, COMPLETED hoặc FAILED |
| `attempt_count` | Số lần worker thử |
| `lease_owner` | Worker đang giữ quyền xử lý |
| `lease_until` | Thời điểm lease hết hạn |
| `last_error_code` | Mã lỗi gần nhất |
| `received_at, updated_at` | Theo dõi vòng đời |

Worker claim bản ghi bằng thao tác nguyên tử, chỉ lấy bản ghi chưa xử lý hoặc lease đã hết hạn. Sau khi claim, worker thực hiện bước có idempotency key. Khi thành công, nó chuyển trạng thái sang COMPLETED; nếu thất bại, tăng attempt và đặt lịch thử lại.

Lease cần được gia hạn cho tác vụ dài và có thời hạn để worker chết không giữ khóa vĩnh viễn. Tuy nhiên, lease hết hạn có thể khiến hai worker cùng thực hiện nếu worker cũ vẫn đang chạy. Do đó, vẫn cần fencing token hoặc idempotency key tại side effect đích; lease một mình không bảo đảm không có xử lý đồng thời.

Không đánh dấu COMPLETED ngay khi vừa nhận message. Nếu worker dừng trước side effect, lần giao lại sẽ thấy hoàn tất và bỏ qua công việc. Cập nhật trạng thái phải theo đúng ranh giới hoàn thành có thể xác minh.

## 14. Retention và replay của inbox

Inbox cần được lưu đủ lâu để bao phủ khoảng thời gian event có thể được giao lại hoặc replay:

- Kafka topic retention và thời gian offset có thể được reset.
- RabbitMQ message có thể được giữ trong queue/DLQ hoặc được publish lại từ kho lưu trữ.
- Pulsar subscription backlog và retention có thể cho phép đọc lại.
- Vận hành có thể replay event từ object storage, backup hoặc outbox cũ.

Nếu xóa inbox record trước khi event cũ có thể xuất hiện lại, consumer sẽ coi event đó là mới và chạy side effect lần nữa. Vì vậy, retention phải dựa trên chính sách replay, thời gian lưu DLQ, thời hạn backup và yêu cầu nghiệp vụ.

Có thể phân vùng bảng theo thời gian hoặc dọn dữ liệu theo batch, nhưng phải bảo đảm unique key còn hiệu lực trong cửa sổ deduplication. Nếu cần lưu dấu lâu hơn nhưng muốn giảm kích thước, có thể chuyển sang kho lưu trữ lịch sử hoặc giữ tombstone/compact record chỉ chứa khóa và hash.

Không xóa inbox theo TTL tùy ý chỉ vì bảng lớn. Hãy xác định thời hạn tối thiểu, đo kích thước, lập kế hoạch archive và kiểm thử replay sau cleanup.

## 15. Kiểm thử idempotency và concurrency

Các test quan trọng:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Gửi cùng event hai lần tuần tự | Side effect database chỉ xảy ra một lần |
| Hai instance nhận cùng event đồng thời | Unique key chỉ cho một transaction thực hiện side effect |
| Lỗi trước commit | Inbox và thay đổi nghiệp vụ cùng rollback |
| DB commit xong nhưng broker ack thất bại | Redelivery được nhận diện là duplicate |
| Cùng event ID nhưng payload khác | Báo event identity conflict, không âm thầm bỏ qua |
| Consumer khác nhận cùng event | Consumer đó vẫn xử lý vì có namespace riêng |
| Replay sau deploy | Cùng consumer name giữ deduplication |
| Replay sau khi cleanup inbox | Kiểm tra chính sách retention có cho phép duplicate side effect không |
| API ngoài thành công nhưng consumer crash | Idempotency key ở API đích ngăn thực hiện hai lần |

Ví dụ unit/integration test cho duplicate:

~~~java
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;

class OrderInboxServiceTest {

    @Test
    void duplicateEventDoesNotApplyOrderTwice() {
        EventEnvelope<OrderPlaced> event = sampleEvent("evt-1001");

        inboxService.handle(event);
        inboxService.handle(event);

        verify(orderRepository, times(1))
            .applyPlacedEvent(event.data());
    }
}
~~~

Test trên cần database thật hoặc Testcontainers để xác minh unique constraint và transaction. Mock repository đơn thuần không chứng minh được tính nguyên tử của `INSERT ... ON CONFLICT`.

Với concurrency test, gửi cùng event tới hai transaction/instance đồng thời và xác nhận chỉ một lần cập nhật nghiệp vụ. Với failure-window test, dừng consumer sau database commit nhưng trước broker ack rồi xác nhận redelivery không tạo side effect lần hai.

## 16. Quan sát inbox trong production

Theo dõi các metric có cardinality giới hạn:

- Số inbox insert mới theo consumer.
- Số duplicate được bỏ qua.
- Số event identity conflict.
- Số transaction rollback khi xử lý event.
- Số bản ghi ở trạng thái PROCESSING quá thời hạn (nếu dùng state machine).
- Tuổi bản ghi inbox chưa hoàn tất.
- Số lần retry và số lần redelivery.
- Kích thước bảng, tốc độ tăng và thời gian cleanup.

Log có cấu trúc nên chứa `consumer_name`, `source`, `event_id`, `event_type`, kết quả `NEW/ DUPLICATE/CONFLICT` và correlation ID nếu có. Không dùng event ID làm metric label vì số lượng giá trị gần như không giới hạn. Không ghi toàn bộ payload hoặc thông tin nhạy cảm nếu không cần cho điều tra.

Cảnh báo khi duplicate tăng bất thường, identity conflict xuất hiện, inbox backlog hoặc PROCESSING lease quá hạn tăng, hoặc cleanup không theo kịp tốc độ ghi.

## 17. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện bài tập với consumer cập nhật tồn kho:

1. Định nghĩa event envelope có `source`, `eventId` và payload `OrderPlaced`.
2. Tạo bảng inbox với khóa chính `(consumer_name, source, event_id)`.
3. Viết consumer Spring Cloud Stream nhận envelope.
4. Dùng một transaction để insert inbox và cập nhật tồn kho.
5. Gửi cùng event hai lần; xác nhận tồn kho chỉ thay đổi một lần.
6. Chạy hai instance cùng consumer group và gửi cùng event đồng thời; xác nhận unique constraint bảo vệ side effect.
7. Mô phỏng database rollback; xác nhận inbox record không được commit.
8. Mô phỏng database commit thành công nhưng broker ack/offset commit thất bại; xác nhận redelivery bị bỏ qua.
9. Gửi cùng event ID với payload khác; xác nhận identity conflict được cảnh báo.
10. Thêm một consumer logic khác và xác nhận nó có inbox namespace riêng.
11. Thử gửi email hoặc gọi API ngoài; bổ sung idempotency key hoặc outbox.
12. Định nghĩa retention và replay window trước khi dọn inbox.

Hoàn thành bài khi có thể giải thích vì sao message có thể được giao nhiều lần; thiết kế khóa duy nhất ổn định; xử lý insert inbox và side effect trong cùng transaction; chống race condition giữa các replica; và phân biệt hiệu ứng database được bảo vệ với side effect bên ngoài cần idempotency/outbox riêng.

## 18. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — consumer, binder, acknowledgment và cấu hình message handling.
- [Spring Cloud Stream — Consumer groups](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/consumer-groups.html) — consumer group và nhiều instance.
- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — ranh giới transaction với `@Transactional`.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — `ON CONFLICT` và insert nguyên tử.
- [Apache Kafka — Consumer configs](https://kafka.apache.org/documentation/#consumerconfigs) — offset commit và consumer behavior.
- [RabbitMQ — Consumer acknowledgements](https://www.rabbitmq.com/docs/confirms) — acknowledgment và redelivery.
- [Apache Pulsar — Messaging concepts](https://pulsar.apache.org/docs/concepts-messaging/) — subscription, acknowledgment và redelivery.

