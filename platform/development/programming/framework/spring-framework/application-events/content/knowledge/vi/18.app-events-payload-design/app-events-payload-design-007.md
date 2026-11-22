# Thời điểm tạo và correlation ID trong thiết kế event payload

## 1. Mục tiêu của metadata trong domain event

Một domain event không chỉ cần nói **điều gì đã xảy ra**, mà còn nên cho consumer biết **sự việc xảy ra khi nào** và **nó thuộc luồng xử lý nghiệp vụ nào**.

Ví dụ, một đơn được đặt rồi bắt đầu đóng gói:

~~~text
HTTP request / command  (correlationId = A)
           |
           v
      OrderPlaced
        eventId = E1
        correlationId = A
        causationId = commandId
        occurredAt = T1
           |
           v
      PackingStarted
        eventId = E2
        correlationId = A
        causationId = E1
        occurredAt = T2
~~~

Hai event khác nhau vì `eventId` khác nhau, nhưng vẫn thuộc **cùng một luồng nghiệp vụ** vì cùng `correlationId`. `causationId` giúp chỉ ra sự kiện/lệnh nào đã trực tiếp kích hoạt sự việc tiếp theo. `occurredAt` cho biết thời gian của từng sự thật nghiệp vụ, không phải thời gian consumer nhận được event.

Những metadata này đặc biệt hữu ích cho audit, phân tích lỗi, distributed workflow, replay và tích hợp với hệ thống bên ngoài. Tuy nhiên, cần đặt **ngữ nghĩa rõ ràng**: chỉ có một trường tên `timestamp` hoặc `id` là chưa đủ để người nhận biết phải hiểu nó như thế nào.

## 2. Phân biệt occurredAt, createdAt, publishedAt, committedAt và processedAt

Các mốc thời gian sau có thể trùng nhau trong ví dụ nhỏ nhưng **không nên coi là đồng nghĩa**.

| Trường / mốc | Nghĩa nên quy ước | Ai biết và ghi nhận? |
| --- | --- | --- |
| `occurredAt` | Thời điểm **sự việc nghiệp vụ xảy ra**, theo định nghĩa domain | Domain/application service khi xác nhận chuyển trạng thái |
| `createdAt` hoặc `envelopedAt` | Thời điểm tạo object event hoặc metadata envelope | Mã tạo event/envelope |
| `publishedAt` | Thời điểm event được công bố cho bus/broker hoặc hệ thống listener cụ thể | Publisher/adapter vận chuyển |
| `committedAt` | Thời điểm transaction chứa dữ liệu nghiệp vụ được commit, nếu có cách ghi nhận đáng tin | Database/transaction layer; không mặc định có trong payload |
| `receivedAt` | Thời điểm consumer nhận event | Consumer |
| `processedAt` | Thời điểm consumer hoàn thành xử lý theo quy ước của consumer | Consumer |

Một tình huống có thể như sau (chỉ để minh họa thứ tự tương đối):

~~~text
10:00:00.100  Nghiệp vụ chấp nhận đơn hàng  -> occurredAt
10:00:00.102  Tạo payload/event envelope     -> createdAt
10:00:00.150  DB transaction commit          -> committedAt
10:00:00.350  Publisher gửi broker            -> publishedAt
10:00:01.000  Consumer đọc message            -> receivedAt
10:00:01.250  Consumer xử lý xong             -> processedAt
~~~

Nếu dùng outbox, event có thể được tạo **trong transaction T1** rồi lưu vào outbox cùng dữ liệu đơn hàng. Worker gửi broker **sau khi T1 commit**. Như vậy `occurredAt` của sự việc được giữ nguyên qua các lần retry; không được thay bằng `Instant.now()` mỗi lần gửi lại.

**Lưu ý về tính xác thực:** nếu transaction rollback, không được công bố ra ngoài một `OrderPlaced` như thể đơn đã commit. Có thể tạo *candidate/pending domain event* khi domain thay đổi bên trong T1, nhưng chỉ xử lý như fact đã commit theo chiến lược nhất quán đã chọn (ví dụ listener `AFTER_COMMIT` hoặc outbox).

### Spring ApplicationEvent.getTimestamp() có phải occurredAt của domain không?

**Không nên tự động đồng nhất.** Khi khởi tạo subclass của `org.springframework.context.ApplicationEvent`, constructor thường gán timestamp từ `System.currentTimeMillis()`; cũng có overload nhận `Clock`. Vì thế `getTimestamp()` phản ánh thời điểm **tạo object ApplicationEvent theo clock được dùng**, chứ không tự biết lúc database commit hoặc lúc sự việc xảy ra trong domain.

Khi ứng dụng publish một **payload object thông thường** qua `ApplicationEventPublisher.publishEvent(Object)`, Spring có thể bọc nó trong `PayloadApplicationEvent`. Metadata timestamp của wrapper cũng thuộc về object event mà Spring tạo, không thay thế trường `occurredAt` có ngữ nghĩa nghiệp vụ trong payload.

Do đó, nếu người dùng cần một mốc thời gian dùng cho audit/tích hợp, hãy khai báo **`Instant occurredAt` trong domain event hoặc envelope có hợp đồng rõ ràng**. `ApplicationEvent.getTimestamp()` vẫn hữu ích để hiểu vòng đời của object Spring event nhưng không phải bản cam kết về thời điểm commit.

## 3. Chọn kiểu thời gian và quy tắc ghi nhận

### Ưu tiên Instant hoặc thời điểm có offset rõ ràng

`java.time.Instant` biểu diễn một thời điểm trên UTC timeline, dễ serialize thành ISO-8601:

~~~json
{
  "type": "OrderPlaced",
  "orderId": 101,
  "occurredAt": "2026-02-03T10:15:30Z"
}
~~~

`OffsetDateTime` cũng phù hợp nếu hợp đồng cần giữ offset. Tránh dùng `LocalDateTime` để biểu diễn thời điểm toàn cục khi event đi qua nhiều timezone: `2026-02-03T10:15:30` không nói thời gian đó ở đâu.

Lưu ý:

- Ghi rõ **đơn vị** khi dùng epoch: epoch milliseconds khác epoch seconds và microseconds. Đối với Java, `Instant.toString()`/ISO-8601 giúp giảm nhập nhằng.
- Dùng `Clock` được inject để thử nghiệm có thể cố định thời gian; tránh gọi trực tiếp `Instant.now()` ở nhiều nơi khiến test khó lặp lại.
- Khi cùng một workflow sinh hai event rất nhanh, timestamp có thể **bằng nhau** do độ phân giải clock. Không dùng timestamp đơn lẻ làm khóa duy nhất.
- Clock của nhiều máy có thể bị **lệch (clock skew)**, nên không suy luận causal order tuyệt đối từ `occurredAt` của các host khác nhau. Nếu cần thứ tự của một aggregate, cân nhắc version/sequence do nguồn có thẩm quyền gán; nếu cần biết sự kiện nào gây ra sự kiện nào, dùng `causationId`.
- Chỉ gán `occurredAt` khi sự việc thật sự được xác nhận theo ngữ nghĩa domain. Việc gọi `new Event(...)` không tự làm một chuyển trạng thái nghiệp vụ thành công.

### Nên ghi timestamp trong payload hay envelope?

Cả hai đều có thể hợp lý nếu hợp đồng nhất quán:

~~~text
Envelope:
    eventId
    eventType
    correlationId
    causationId
    publishedAt / schemaVersion (nếu cần)

Payload:
    orderId
    customerId
    occurredAt
    totalAmount
~~~

Nếu một contract thống nhất rằng `occurredAt` thuộc envelope thay vì payload, consumer vẫn có thể dùng đúng ngữ nghĩa. Quan trọng là **tránh hai trường cùng tên nhưng diễn đạt hai thời điểm khác nhau** hoặc để cơ chế vận chuyển âm thầm ghi đè thời điểm nghiệp vụ.

## 4. Correlation ID là gì?

`correlationId` là một định danh giúp **gom các thao tác thuộc cùng một luồng xử lý**: từ request ban đầu qua service, command, event và các bước tích hợp khác.

Ví dụ checkout:

~~~text
correlationId = C-123
    |
    +-- CheckoutRequested  (commandId = CMD-1)
    +-- OrderPlaced        (eventId = EVT-1, causationId = CMD-1)
    +-- PaymentCaptured    (eventId = EVT-2, causationId = EVT-1)
    +-- ShipmentRequested  (commandId = CMD-2, causationId = EVT-2)
    +-- ShipmentDispatched (eventId = EVT-3, causationId = CMD-2)
~~~

Mỗi sự việc có ID riêng; **correlation ID được giữ ổn định** để điều tra toàn bộ hành trình. Một correlation ID có thể gắn với nhiều event, nhiều request/message hoặc nhiều service. Nó **không phải primary key của từng event**.

Một số trường hợp tổ chức correlation:

1. **Request HTTP đầu vào:** boundary có thể tiếp nhận correlation ID đáng tin đã có hoặc tạo mới nếu chưa có; phải validate định dạng, kích thước và chính sách tin cậy của header.
2. **Command đầu tiên:** gắn correlation ID vào command và truyền xuống các application/domain service.
3. **Domain event:** sao chép correlation ID từ ngữ cảnh nghiệp vụ/command **chứ không tạo ID mới cho từng event**.
4. **Handler sinh command/event kế tiếp:** giữ correlation ID ban đầu, nhưng tạo `eventId` mới cho mỗi sự việc mới và đặt `causationId` trỏ tới đối tượng trực tiếp kích hoạt nó.
5. **Đi qua queue hoặc service khác:** đưa correlation ID vào metadata message/payload theo contract, không mong `ThreadLocal` hoặc MDC tự truyền qua process.

UUID là một lựa chọn thường gặp cho các ID này; có hệ thống dùng ULID, chuỗi có tiền tố hay định danh khác. **Không có yêu cầu của Spring rằng correlation ID bắt buộc là UUID.** Điều bắt buộc là các thành phần thống nhất kiểu và ý nghĩa.

## 5. Phân biệt eventId, correlationId, causationId, traceId và aggregateId

| Trường | Phạm vi nhận diện | Quy tắc quan trọng |
| --- | --- | --- |
| `eventId` | **Một sự việc/event cụ thể** | Sinh mới cho sự việc mới; khi retry phát lại **chính event đó**, giữ nguyên ID |
| `correlationId` | **Một workflow hoặc chuỗi liên quan** | Giữ ổn định qua các bước cần liên kết |
| `causationId` | **Thông điệp/lệnh/event trực tiếp gây ra bước này** | Có thể trỏ tới `commandId` hoặc `eventId` của parent; nếu không có nguồn trực tiếp, có thể bỏ trống |
| `traceId` | **Một distributed trace của hạ tầng observability** | Do tracing system như OpenTelemetry quản lý; không mặc định đồng nghĩa correlation ID nghiệp vụ |
| `aggregateId`, `orderId` | **Đối tượng nghiệp vụ bị tác động** | Nhiều event khác nhau của một order có thể có cùng `orderId` nhưng thuộc các workflow khác nhau |

Một quy tắc dễ nhớ:

~~~text
eventId       : “Đây là sự kiện nào?”
correlationId : “Nó thuộc hành trình nghiệp vụ nào?”
causationId   : “Điều gì trực tiếp dẫn đến sự kiện này?”
traceId       : “Lần thực thi phân tán nào được hệ thống trace?”
orderId       : “Đơn hàng nào đang được nói đến?”
~~~

**Không dùng `correlationId` làm khóa deduplication cho từng event.** Vì nhiều event hợp lệ có thể cùng correlation ID, consumer dùng khóa đó để bỏ trùng sẽ vô tình làm mất event. Đối với retry/at-least-once delivery, thường dùng `eventId` kết hợp phạm vi consumer, hoặc một business idempotency key phù hợp.

`traceId` có thể thay đổi khi workflow chạy qua nhiều lần retry hoặc tồn tại nhiều giờ/ngày, trong khi `correlationId` nghiệp vụ vẫn giữ nguyên. Có thể ghi cả hai khi cần, nhưng không buộc chúng phải là một giá trị.

## 6. Mẫu payload Java 17+ rõ ngữ nghĩa

Một record event có thể chứa các trường:

~~~java
import java.time.Instant;
import java.util.UUID;

// Đoạn minh họa kiểu dữ liệu, không phải file chạy độc lập.
public record OrderPlaced(
    UUID eventId,
    UUID correlationId,
    UUID causationId,
    long orderId,
    Instant occurredAt
) {}
~~~

Ý nghĩa:

- `eventId`: danh tính của **OrderPlaced cụ thể này**.
- `correlationId`: cùng giá trị được đưa vào từ command/request tạo ra đơn hàng.
- `causationId`: ID của command `PlaceOrder`, nếu workflow có command ID.
- `orderId`: danh tính aggregate; một order có thể có nhiều event khác nhau.
- `occurredAt`: thời điểm đặt hàng được domain chấp nhận.

**Không tạo tất cả ID bằng một `UUID.randomUUID()` và gán chung cho mọi trường.** Có thể cùng kiểu UUID nhưng mỗi trường có ý nghĩa riêng. Nếu không có quan hệ nhân quả trực tiếp, một trường causation có thể để `null` theo contract, hoặc sử dụng `Optional`/envelope phù hợp thay vì dựng ID giả.

Trong production, cân nhắc schema version, giá trị tiền, phạm vi định danh tenant, loại event và bảo mật dữ liệu. Không gửi cả entity JPA có thể biến đổi/lazy-loading như payload để tránh thay đổi lịch sử của một sự việc đã xảy ra.

## 7. Ví dụ Java 17+ Spring: hai event, một correlation ID, hai event ID

Demo độc lập dưới đây dùng **Spring Framework 6.2.18** và event publisher đồng bộ mặc định. Một command `PlaceOrder` tạo `OrderPlaced`; listener bắt đầu công việc đóng gói **trong bộ nhớ** rồi phát `PackingStarted`.

Mục tiêu là quan sát metadata:

- Hai event có `eventId` **khác nhau**.
- Hai event có cùng `correlationId`.
- `OrderPlaced.causationId` là `commandId`; `PackingStarted.causationId` là `OrderPlaced.eventId`.
- Hai event có cùng `occurredAt` trong **test clock cố định**, chứng minh không thể suy luận thứ tự từ timestamp.
- Một command trùng ID bị từ chối và không sinh event thứ ba.

Đây là **demo không có database, không có transaction, không có broker**. Cơ chế lưu dữ liệu trong `HashSet` không phù hợp cho xử lý đồng thời hoặc độ bền production.

### Tệp settings.gradle

~~~groovy
rootProject.name = 'event-metadata-demo'
~~~

### Tệp build.gradle

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.EventMetadataDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### Tệp src/main/java/demo/EventMetadataDemo.java

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EventMetadataDemo {

    // ID cố định chỉ để stdout và kiểm thử có thể đối chiếu.
    private static final UUID COMMAND_ID =
        UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final UUID CORRELATION_ID =
        UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    private static final UUID ORDER_EVENT_ID =
        UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final UUID PACKING_EVENT_ID =
        UUID.fromString("33333333-3333-3333-3333-333333333333");

    // Command chứa ID của lệnh và correlation của workflow.
    public record PlaceOrder(
        UUID commandId,
        UUID correlationId,
        long orderId
    ) {}

    // Hai fact nghiệp vụ có schema metadata giống nhau.
    public record OrderPlaced(
        UUID eventId,
        UUID correlationId,
        UUID causationId,
        long orderId,
        Instant occurredAt
    ) {}

    public record PackingStarted(
        UUID eventId,
        UUID correlationId,
        UUID causationId,
        long orderId,
        Instant occurredAt
    ) {}

    public static final class OrderService {
        private final Set<Long> orders = new HashSet<>();
        private final ApplicationEventPublisher events;
        private final Clock clock;

        OrderService(ApplicationEventPublisher events, Clock clock) {
            this.events = events;
            this.clock = clock;
        }

        public void place(PlaceOrder command) {
            Objects.requireNonNull(command);
            Objects.requireNonNull(command.commandId());
            Objects.requireNonNull(command.correlationId());

            if (command.orderId() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            if (!orders.add(command.orderId())) {
                throw new IllegalStateException("Duplicate order");
            }

            events.publishEvent(new OrderPlaced(
                ORDER_EVENT_ID,
                command.correlationId(),
                command.commandId(),
                command.orderId(),
                Instant.now(clock)
            ));
        }

        public int orderCount() {
            return orders.size();
        }
    }

    public static final class PackingListener {
        private final Set<Long> started = new HashSet<>();
        private final ApplicationEventPublisher events;
        private final Clock clock;

        PackingListener(ApplicationEventPublisher events, Clock clock) {
            this.events = events;
            this.clock = clock;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println(
                "OrderPlaced: order=" + event.orderId()
                    + ", at=" + event.occurredAt()
            );
            System.out.println(
                "  eventId=" + event.eventId()
                    + ", correlationId=" + event.correlationId()
                    + ", causationId=" + event.causationId()
            );

            // Trong demo: ghi nhận trạng thái bắt đầu đóng gói
            // trong bộ nhớ trước khi phát fact tương ứng.
            if (started.add(event.orderId())) {
                events.publishEvent(new PackingStarted(
                    PACKING_EVENT_ID,
                    event.correlationId(), // GIỮ correlationId
                    event.eventId(),       // Nối quan hệ nhân quả
                    event.orderId(),
                    Instant.now(clock)
                ));
            }
        }

        @EventListener
        public void onPackingStarted(PackingStarted event) {
            System.out.println(
                "PackingStarted: order=" + event.orderId()
                    + ", at=" + event.occurredAt()
            );
            System.out.println(
                "  eventId=" + event.eventId()
                    + ", correlationId=" + event.correlationId()
                    + ", causationId=" + event.causationId()
            );
        }
    }

    @Configuration
    public static class DemoConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                Instant.parse("2026-02-03T10:15:30Z"),
                ZoneOffset.UTC
            );
        }

        @Bean
        OrderService orderService(
                ApplicationEventPublisher events, Clock clock) {
            return new OrderService(events, clock);
        }

        @Bean
        PackingListener packingListener(
                ApplicationEventPublisher events, Clock clock) {
            return new PackingListener(events, clock);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {

            var service = ctx.getBean(OrderService.class);

            service.place(new PlaceOrder(
                COMMAND_ID, CORRELATION_ID, 101L
            ));

            // Cùng orderId: bị từ chối, không công bố event mới.
            try {
                service.place(new PlaceOrder(
                    UUID.fromString(
                        "44444444-4444-4444-4444-444444444444"
                    ),
                    CORRELATION_ID,
                    101L
                ));
            } catch (IllegalStateException ignored) {
                System.out.println("duplicate rejected");
            }

            System.out.println("orders=" + service.orderCount());
        }
    }
}
~~~

Chạy trong thư mục dự án bằng JDK 17+ và Gradle hoặc Gradle Wrapper sẵn có:

~~~bash
gradle run --quiet
# Linux/macOS nếu đã có wrapper: ./gradlew run --quiet
# Windows nếu đã có wrapper: gradlew.bat run --quiet
~~~

Các dòng do chương trình tự in (không tính logging của môi trường):

~~~text
OrderPlaced: order=101, at=2026-02-03T10:15:30Z
  eventId=22222222-2222-2222-2222-222222222222, correlationId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, causationId=11111111-1111-1111-1111-111111111111
PackingStarted: order=101, at=2026-02-03T10:15:30Z
  eventId=33333333-3333-3333-3333-333333333333, correlationId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, causationId=22222222-2222-2222-2222-222222222222
duplicate rejected
orders=1
~~~

Giải thích trình tự:

1. `OrderService.place(...)` ghi nhận đơn vào `Set` và phát `OrderPlaced`. Listener nhận payload qua `@EventListener`.
2. `PackingListener` in metadata rồi ghi nhận bắt đầu đóng gói vào một `Set` riêng. Nếu đây là lần đầu, nó phát **`PackingStarted` mới**.
3. `PackingStarted` có **event ID mới**, giữ `correlationId` của `OrderPlaced` và dùng `OrderPlaced.eventId` làm `causationId`.
4. `Clock.fixed` khiến hai event cùng thời điểm `2026-02-03T10:15:30Z`. Dù timestamp bằng nhau, **chuỗi nhân quả vẫn rõ** nhờ ID và cách luồng được triển khai.
5. Command tạo lại order ID 101 bị từ chối, nên không có thêm `OrderPlaced` hay `PackingStarted`. Kết quả chỉ có một order trong bộ nhớ.

Giải pháp demo sử dụng `ApplicationEventPublisher` và multicaster đồng bộ mặc định. Khi chạy thật với executor bất đồng bộ, queue hoặc broker, thứ tự callback và cách mang context có thể khác. **Giá trị UUID cố định chỉ dành cho demo; hệ thống thật phải tạo ID duy nhất cho từng sự việc mới**, đồng thời giữ nguyên `eventId` khi phát lại cùng một event.

## 8. Phát event trong transaction: timestamp và correlation không bảo đảm commit

Dù metadata đẹp, vẫn có thể sai nếu thông báo được gửi **trước khi sự việc được commit**.

Giả sử mã nghiệp vụ:

~~~java
// Anti-pattern minh họa; đây không phải chương trình độc lập.
@Transactional
public void placeOrder(PlaceOrder command) {
    orderRepository.save(new Order(...));
    eventPublisher.publishEvent(new OrderPlaced(...));
    // Nếu có lỗi sau đó, T1 có thể rollback.
}
~~~

Nếu consumer được gọi ngay và thực hiện side effect bên ngoài T1, nó có thể xử lý một fact không có trong DB sau rollback. `occurredAt` hoặc `correlationId` **không làm event trở nên transactional**.

Nếu chỉ cần hành động phụ sau khi T1 commit thành công, một tùy chọn là:

~~~java
// Đoạn minh họa dùng event type và Spring beans phù hợp.
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // T1 đã commit. Gọi xử lý hậu commit tùy use case.
}
~~~

Lưu ý, `@TransactionalEventListener` mặc định chỉ chạy khi event được publish trong transaction phù hợp. Callback sau commit **không tự mở transaction mới** cho thao tác ghi DB; nếu cần ghi DB từ listener, thường cần transaction độc lập đúng cơ chế `REQUIRES_NEW`. Với reactive transaction, dùng cơ chế truyền `TransactionContext` của Spring như `TransactionalEventPublisher`.

Với yêu cầu **chuyển event đáng tin cậy ra broker**, dùng transactional outbox:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox(
    event_id,
    correlation_id,
    causation_id,
    occurred_at,
    event_type,
    payload
  )
COMMIT T1

Outbox worker (về sau):
  đọc bản ghi đã commit
  gửi message
  đánh dấu đã gửi hoặc retry nếu lỗi
~~~

Đoạn trên là **pseudocode**, không phải SQL chuẩn cho một schema cụ thể. Hệ thống production cần quy định lock/claim, retry, khả năng gửi trùng và tiêu chí hoàn tất riêng. Điểm quan trọng là **outbox giữ nguyên `eventId`, `correlationId` và `occurredAt` khi retry**, còn `publishedAt` (nếu có) có thể phản ánh từng lần publish hoặc lần đầu publish theo contract.

Không nhầm timestamp event với thời gian commit: commit có thể đến sau `occurredAt`, và không phải mọi DB đều cung cấp commit timestamp đáng tin cậy theo cùng một cách.

## 9. Truyền correlation ID qua HTTP, async và message broker

Một thiết kế điển hình:

- **Ingress (HTTP/RPC):** đọc correlation header theo chính sách tin cậy hoặc tạo ID; đưa vào request context/command rõ ràng.
- **Application service:** tạo event từ nghiệp vụ, sao chép `correlationId` vào event/envelope và gán `eventId` mới.
- **Event handler:** dùng correlation ID đã nhận nếu tạo công việc kế tiếp; dùng event hiện tại làm causation.
- **Broker adapter:** đưa correlation ID vào message headers hoặc payload với key/casing đã được thống nhất; khi consumer nhận, giải mã và truyền xuống nghiệp vụ.
- **Logger/tracer:** có thể đưa correlation ID vào MDC/log fields hoặc tracing baggage phù hợp, nhưng metadata nghiệp vụ nên tiếp tục được truyền một cách tường minh, không phụ thuộc chỉ vào logging context.

Lưu ý quan trọng về luồng bất đồng bộ:

- ThreadLocal/MDC **không tự đi theo** mọi `@Async`, executor task, Reactor subscription, queue hoặc process boundary. Cần cấu hình context propagation hoặc truyền ID qua payload/headers.
- Tracing và correlation có thể liên kết với nhau nhưng có vòng đời khác nhau. Ví dụ trace của HTTP request ban đầu có thể kết thúc, trong khi correlation của luồng xử lý đơn hàng kéo dài nhiều giờ.
- Không lấy một correlation ID có thể do client cung cấp làm bằng chứng xác thực/ủy quyền. Nó là metadata để liên kết, **không phải access token**. Giới hạn độ dài, ký tự, cardinality log và xử lý dữ liệu nhạy cảm.
- Không tự ý đưa thông tin cá nhân như email, tên khách hàng, token vào `correlationId` để “dễ đọc log”; dùng ID vô danh hoặc định danh được kiểm soát.
- Nếu một event được phát lại do retry, giữ nguyên `eventId` của sự việc cũ; tạo mới `attemptId` hoặc metadata vận chuyển nếu cần theo dõi từng lần thử mà không phá deduplication.

### Một workflow có nhiều correlation ID thì sao?

Thông thường chọn **một correlation ID** theo một giao dịch/luồng nghiệp vụ có phạm vi đủ rõ. Nhưng khi các workflow hợp nhất hoặc một event kích hoạt nhiều workflow mới, có thể bắt đầu correlation mới và **lưu liên kết với correlation nguồn** bằng một metadata/hợp đồng khác. Đừng áp dụng máy móc “một correlation ID cho mọi thứ mãi mãi”; phạm vi correlation cần do domain và mục tiêu truy vết quyết định.

## 10. Kiểm thử thiết kế timestamp và correlation

Một bộ kiểm thử có giá trị nên kiểm tra:

| Ca kiểm thử | Điều cần xác nhận |
| --- | --- |
| Một command hợp lệ | Event có `occurredAt` từ `Clock`/thời điểm domain được quy ước |
| Hai event trong một workflow | `correlationId` giống nhau, `eventId` khác nhau |
| Event B do event A kích hoạt | `B.causationId == A.eventId` |
| Command bị từ chối | Không phát fact nói rằng command đã thành công |
| Gửi lại cùng một event | Giữ `eventId`, `occurredAt`, `correlationId`, payload gốc |
| Transaction rollback | Không công bố ra ngoài fact như đã commit; strategy after-commit/outbox hoạt động đúng |
| Listener khác thread/process | Correlation ID còn nguyên qua payload/header, không dựa vào MDC đơn thuần |
| Hai clock có cùng/lệch timestamp | Không dùng thời điểm làm khóa dedupe hay bằng chứng nhân quả duy nhất |
| Tích hợp qua version/schema | Contract vẫn parse được `occurredAt` và metadata theo quy tắc đã công bố |

Các lỗi thực tế thường gặp:

1. **Tạo correlation ID mới cho từng event:** log không còn liên kết các bước cùng workflow. Sửa bằng cách sao chép correlation từ ngữ cảnh đầu vào khi tạo event kế tiếp.
2. **Dùng `eventId` giống `correlationId`:** không thể phân biệt các event riêng biệt. Thiết kế hai trường, hai phạm vi nhận diện.
3. **Đặt `occurredAt = Instant.now()` ở consumer:** biến thời gian nhận thành thời gian sự việc xảy ra. Consumer nên ghi thêm `receivedAt` riêng.
4. **Thay `eventId` mỗi lần retry:** cơ chế deduplication theo event ID không còn nhận ra lần gửi lặp của cùng sự việc.
5. **Chỉ lưu correlation trong MDC:** async/broker làm mất ngữ cảnh, consumer không tự phục hồi được. Truyền metadata qua payload/header.
6. **Tin rằng `ApplicationEvent.getTimestamp()` là commit timestamp:** constructor event không có thông tin commit. Dùng trường nghiệp vụ rõ nghĩa.
7. **Sắp xếp event phân tán chỉ bằng thời gian:** clock skew và thời gian nhận khác nhau làm sai thứ tự. Khi thật sự cần, dùng sequence/version, partition ordering hoặc causal metadata phù hợp.
8. **Tin correlation ID là identity của người dùng:** nó chỉ liên kết các bước, không dùng cho xác thực hoặc phân quyền.
9. **Nhầm “publish thành công” là “consumer xử lý thành công”:** một lần publish ở Spring local event, outbox hay broker có các mức bảo đảm khác nhau; cần giám sát, retry và idempotency thích hợp.

## 11. Checklist khi chốt schema payload

Trước khi công bố event mới, trả lời rõ:

1. `occurredAt` nghĩa là lúc domain xác nhận điều gì? Nó có thể được tạo trước commit không?
2. Kiểu thời gian là `Instant`/ISO-8601 UTC hay số epoch? Nếu là số thì đơn vị gì?
3. Có cần cả `createdAt` hoặc `publishedAt` không, hay các trường đó chỉ là metadata vận chuyển?
4. `correlationId` được tạo ở boundary nào? Ai chịu trách nhiệm giữ qua các bước?
5. `eventId` có duy nhất cho sự việc, ổn định qua retry không?
6. `causationId` có trỏ tới đúng message/command trực tiếp gây ra event không?
7. ID và timestamp có được truyền qua HTTP, async, broker, outbox mà không bị tái tạo sai không?
8. Consumer có thực hiện dedupe bằng `eventId` thay vì bỏ trùng cả workflow theo correlation ID không?
9. Có nhầm `traceId`, `orderId` hoặc thông tin cá nhân với `correlationId` không?
10. Có test bằng `Clock.fixed` và kiểm chứng metadata sau serialize/deserialize, rollback và retry không?

### Ghi nhớ

~~~text
occurredAt    -> Khi nào sự việc nghiệp vụ xảy ra?
eventId       -> Sự kiện cụ thể nào?
correlationId -> Sự kiện này thuộc workflow nào?
causationId   -> Điều gì trực tiếp gây ra nó?
traceId       -> Trace hạ tầng quan sát lần thực thi nào?
publishedAt   -> Khi nào transport công bố event?
processedAt   -> Khi nào consumer hoàn thành?
~~~

**Thiết kế tốt không phải là nhồi mọi metadata vào mọi payload.** Cần giữ đúng trường có ích cho contract, nhưng luôn định nghĩa rõ cách đặt timestamp và phạm vi ID. Trong Spring Framework, cơ chế `ApplicationEventPublisher` và `@EventListener` giúp công bố/nhận event; việc giữ `occurredAt` và `correlationId` đúng ngữ nghĩa là trách nhiệm của ứng dụng.

## Tài liệu chính thức

- [Spring Framework — ApplicationEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEvent.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — ApplicationContext Events và EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [OpenTelemetry — Trace API Concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
