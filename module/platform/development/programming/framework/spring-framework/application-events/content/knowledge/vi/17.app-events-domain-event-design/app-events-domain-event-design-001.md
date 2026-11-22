# Domain event trong mô hình domain: thiết kế và triển khai với Spring Framework Application Events

## 1. Domain event là gì?

**Domain event (sự kiện miền)** diễn tả một **sự thật nghiệp vụ quan trọng đã xảy ra** bên trong domain: đơn hàng đã được đặt (`OrderPlaced`), thanh toán đã được xác nhận (`PaymentConfirmed`), tài khoản đã bị khóa (`AccountLocked`), hoặc hạn mức tín dụng đã thay đổi (`CreditLimitChanged`).

Trong tư duy Domain-Driven Design (DDD), domain event giúp mô hình diễn đạt **điều gì vừa xảy ra** bằng ngôn ngữ mà người làm nghiệp vụ hiểu được. Nó không chỉ là một thông báo kỹ thuật. Ví dụ, `OrderPlaced` khác với `RowInserted`: “đơn hàng đã được đặt” là một chuyển trạng thái có ý nghĩa với nghiệp vụ, còn “đã INSERT một dòng” chỉ là chi tiết lưu trữ.

Một domain event tốt trả lời được:
- **Chuyện gì đã xảy ra?** Tên sự kiện thể hiện trạng thái đã hoàn tất.
- **Đối tượng nào liên quan?** `orderId`, `customerId` hoặc aggregate identifier.
- **Thông tin nào cần được chụp lại?** Tổng tiền đã chốt, loại thay đổi, phiên bản nghiệp vụ.
- **Sự kiện thuộc ranh giới nào?** Aggregate/bounded context nào phát sinh nó.
- **Hệ thống phải phản ứng ra sao?** Các policy hoặc consumer độc lập xử lý hậu quả mà không thay thế tính bất biến của aggregate.

Domain event là một khái niệm **ở tầng domain**. Spring `ApplicationEventPublisher` và `@EventListener` chỉ là một trong nhiều **cơ chế kỹ thuật** để truyền và xử lý domain event trong một ứng dụng Java.

## 2. Domain event nằm ở đâu trong mô hình DDD?

Một hướng tổ chức điển hình:

```text
Client / Controller
        |
Application Service / Use Case
        |
Order Aggregate --------------> OrderPlaced (domain event)
  - giữ invariant                        |
  - chuyển DRAFT -> PLACED               |
  - thu thập pending events              |
        |                                 |
Repository.save(order)                   |
        |                                 |
Application Service / Unit of Work ------+
        |
        +--> Publish in-process / transaction synchronization
        |        |
        |        +--> Domain policy / handler cùng ứng dụng
        |
        +--> Transactional outbox (nếu cần giao nhận bền vững)
                 |
                 +--> Worker / broker / integration consumer
```

**Aggregate** chịu trách nhiệm tính đúng đắn của chính trạng thái nghiệp vụ. Khi một hành động hợp lệ làm trạng thái thay đổi, aggregate **ghi nhận** domain event. Một lớp điều phối bên ngoài (application service, unit of work hoặc repository integration) quyết định **khi nào và bằng cơ chế nào** phát các event đã ghi nhận.

Ví dụ, `Order.place()` phải kiểm tra đơn hàng đang ở trạng thái cho phép đặt; nếu không, nó ném lỗi, **không chuyển trạng thái và không phát `OrderPlaced`**. Việc aggregate tạo ra sự kiện phản ánh một quyết định nghiệp vụ đã được chấp nhận. Điều đó không tự đồng nghĩa giao dịch DB cuối cùng đã commit.

### Event là kết quả của hành vi, không phải lệnh

| Loại thông điệp | Ví dụ | Ngữ nghĩa |
| --- | --- | --- |
| Command | `PlaceOrder` | Yêu cầu thực hiện hành động; có thể bị từ chối |
| Domain event | `OrderPlaced` | Domain đã chấp nhận chuyển trạng thái “đã đặt” |
| Integration event | `OrderPlacedIntegrationEvent` | Thông điệp dành cho hệ thống/bounded context khác, có hợp đồng truyền nhận riêng |
| Technical event | `EntitySaved` | Thông báo kỹ thuật về thao tác lưu trữ; chưa chắc có ý nghĩa domain |

Đừng đặt tên domain event như một lệnh `SendEmailNow`: đó là yêu cầu xử lý, không phải một sự thật nghiệp vụ. Cũng không nên phát event cho từng thay đổi field nhỏ nếu thay đổi ấy không tạo thành một sự kiện đáng chú ý trong ngôn ngữ nghiệp vụ.

## 3. Chọn thời điểm tạo domain event trong aggregate

Aggregate nên tạo event **sau khi invariant được kiểm tra và chuyển trạng thái được chấp nhận**, trong cùng phương thức nghiệp vụ:

```java
public void place(String eventId) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException("Only DRAFT orders can be placed");
    }
    status = OrderStatus.PLACED;
    pendingEvents.add(
        new OrderPlaced(eventId, orderId, totalCents)
    );
}
```

Đây là **trích đoạn minh họa** trong class `Order`; chương trình chạy đầy đủ ở mục 6.

Lợi ích của việc tạo event tại thời điểm chuyển trạng thái:
1. Người đọc thấy rõ điều kiện nào dẫn đến `OrderPlaced`.
2. Event không bị phát vì một getter hoặc câu SQL bất kỳ.
3. Aggregate giữ được quyền kiểm soát invariant; consumer không cần đoán trạng thái trước đó.
4. Có thể kiểm thử nghiệp vụ thuần Java không cần Spring context.

Nếu command thất bại trước khi chuyển trạng thái, không ghi nhận domain event mới. Nếu transaction DB rollback sau khi aggregate ghi nhận event trong bộ nhớ, việc **truyền event ra ngoài** phải được điều phối theo kết quả transaction để tránh tạo side effect sai.

### Có cần domain biết Spring?

Không bắt buộc và trong một mô hình domain tách biệt thì thường **không nên**. Aggregate thuần Java không cần inject `ApplicationEventPublisher` hay gọi `@EventListener`. Nó chỉ trả về hoặc lưu danh sách domain event tạm thời. Application service có thể dịch chúng sang cơ chế Spring, lưu outbox, hoặc gửi đến message broker mà không buộc domain phụ thuộc Spring.

Một ứng dụng đơn giản có thể chọn cách phát event ngay tại application service. Điều quan trọng là **phân biệt ranh giới trách nhiệm** và ghi rõ thời điểm phát so với commit.

## 4. Thiết kế payload domain event

Với Java 17+, `record` rất phù hợp cho các event chủ yếu chứa dữ liệu bất biến:

```java
public record OrderPlaced(
    String eventId,
    String orderId,
    long totalCents
) {}
```

Ví dụ dữ liệu của một event:
- `eventId = "EVT-42"`: định danh duy nhất cho **một lần xảy ra** sự kiện. Giữ nguyên ID nếu retry phát lại cùng sự kiện.
- `orderId = "ORD-42"`: định danh aggregate.
- `totalCents = 12500`: tổng tiền tại thời điểm đặt đơn, dưới dạng số nguyên đơn vị nhỏ nhất để tránh lỗi làm tròn floating point.

Trong hệ thống lớn hơn, event có thể chứa `occurredAt` (thời điểm domain ghi nhận), `aggregateVersion` hoặc correlation/causation ID. Chỉ thêm những trường cần thiết. Không đưa mật khẩu, token, dữ liệu nhạy cảm hoặc toàn bộ JPA entity vào payload.

**Lưu ý:** `record` là shallow immutable: các field tham chiếu đến `List`, `Map` hoặc object mutable vẫn có thể đổi bên trong. Nên dùng kiểu bất biến, primitive, `String`, `Instant`, các value object bất biến hoặc defensive copy (`List.copyOf(...)`) khi phù hợp. Tên trường và kiểu dữ liệu cần phản ánh ngữ nghĩa domain, không phụ thuộc schema bảng DB.

### Sự kiện có phải luôn chứa toàn bộ dữ liệu?

Không. Có hai cách cần cân nhắc:
- **Event chứa snapshot cần thiết:** consumer không cần đọc lại trạng thái đang thay đổi; thuận tiện cho audit, replay và xử lý bất đồng bộ. Payload lớn hơn và phải quản lý version.
- **Event chủ yếu chứa ID:** consumer đọc dữ liệu từ repository; payload nhỏ nhưng phải xét dữ liệu đã commit chưa, độ trễ eventual consistency và khả năng dữ liệu thay đổi giữa thời điểm xảy ra event và lúc xử lý.

Đừng ghi “trạng thái mới” vào event nếu nó có thể được tính lại và khác với sự thật tại thời điểm phát; cũng đừng buộc mọi consumer gọi lại một mutable aggregate để đoán dữ liệu lịch sử.

## 5. Phân biệt domain event, Spring application event và integration event

**Domain event:** thuộc từ vựng nghiệp vụ và có thể tồn tại hoàn toàn độc lập với framework. Một record `OrderPlaced` có thể là domain event kể cả khi không có bean Spring nào được chạy.

**Spring application event:** là hạ tầng phát sự kiện **trong một `ApplicationContext`**. `ApplicationEventPublisher.publishEvent(event)` chuyển sự kiện cho multicaster. Từ Spring 4.2, event có thể là object bất kỳ; object không kế thừa `ApplicationEvent` được bọc thành `PayloadApplicationEvent`. `@EventListener` có thể nhận payload theo kiểu Java thông thường.

**Integration event:** là hợp đồng trao đổi giữa hệ thống, thường đòi hỏi serializer, schema evolution, event ID, chính sách version, broker/outbox, retry và idempotency. Integration event có thể được tạo **từ** domain event sau khi transaction commit, nhưng không mặc nhiên là chính instance Java đó.

| Câu hỏi | Domain event | Spring application event | Integration event |
| --- | --- | --- | --- |
| Định nghĩa bởi | Domain model | Cơ chế Spring | Hợp đồng giữa dịch vụ |
| Ranh giới chính | Aggregate/bounded context | Application context/process | Process/service/network |
| Bảo đảm bền vững | Tùy nơi lưu | Không tự lưu bền vững | Tùy outbox/broker |
| Phụ thuộc Spring | Không cần | Có | Không cần |
| Ví dụ | `OrderPlaced` | Publish `OrderPlaced` qua Spring | JSON event gửi broker sau commit |

Dùng chung một kiểu Java cho domain và integration event chỉ phù hợp khi đã cân nhắc hợp đồng/version và phạm vi coupling. Một thay đổi nội bộ trong aggregate không nên tự động phá vỡ consumer ở dịch vụ khác.

## 6. Ví dụ Java 17+ chạy được: aggregate thuần Java, Spring chỉ publish

Chương trình nhỏ dưới đây dùng Spring Context, không cần Spring Boot hay DB. Domain aggregate tự kiểm tra quy tắc và lưu các domain event chưa phát. Application service lưu aggregate vào repository in-memory rồi publish event bằng Spring. Hai listener nhận cùng payload nhưng không phụ thuộc vào thứ tự của nhau.

Cấu trúc:

```text
domain-events-demo/
├── build.gradle
└── src/main/java/demo/DomainEventDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.DomainEventDemo'
}
```

Nội dung `src/main/java/demo/DomainEventDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class DomainEventDemo {

    // Domain types: không import Spring.
    public sealed interface DomainEvent permits OrderPlaced {
        String eventId();
        String aggregateId();
    }

    public record OrderPlaced(
            String eventId,
            String aggregateId,
            long totalCents
    ) implements DomainEvent {}

    public static final class Order {
        private enum State { DRAFT, PLACED }

        private final String orderId;
        private final long totalCents;
        private State state = State.DRAFT;
        private final List<DomainEvent> pendingEvents = new ArrayList<>();

        private Order(String orderId, long totalCents) {
            if (orderId == null || orderId.isBlank() || totalCents <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            this.orderId = orderId;
            this.totalCents = totalCents;
        }

        public static Order draft(String id, long totalCents) {
            return new Order(id, totalCents);
        }

        public void place(String eventId) {
            if (state != State.DRAFT) {
                throw new IllegalStateException("Order already placed");
            }
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("Missing event id");
            }
            state = State.PLACED;
            pendingEvents.add(
                new OrderPlaced(eventId, orderId, totalCents)
            );
        }

        public String id() {
            return orderId;
        }

        public boolean isPlaced() {
            return state == State.PLACED;
        }

        public List<DomainEvent> drainEvents() {
            List<DomainEvent> copy = List.copyOf(pendingEvents);
            pendingEvents.clear();
            return copy;
        }
    }

    // Adapter lưu trữ giả lập: thay bằng DB/repository thật khi triển khai.
    public static final class InMemoryOrderRepository {
        private final Map<String, Order> orders = new HashMap<>();

        public void save(Order order) {
            orders.put(order.id(), order);
            System.out.println(
                "SAVED " + order.id() + " placed=" + order.isPlaced()
            );
        }
    }

    // Application service quyết định lưu và phát event.
    public static final class PlaceOrderUseCase {
        private final InMemoryOrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public PlaceOrderUseCase(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void place(String orderId, long amount, String eventId) {
            Order order = Order.draft(orderId, amount);
            order.place(eventId);
            repository.save(order);
            for (DomainEvent event : order.drainEvents()) {
                publisher.publishEvent(event);
            }
        }
    }

    public static final class AuditListener {
        @EventListener
        public void whenPlaced(OrderPlaced event) {
            System.out.println(
                "AUDIT " + event.eventId() + " " + event.aggregateId()
            );
        }
    }

    public static final class MetricsListener {
        @EventListener
        public void whenPlaced(OrderPlaced event) {
            System.out.println(
                "METRICS " + event.aggregateId()
                    + " totalCents=" + event.totalCents()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public InMemoryOrderRepository repository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        public PlaceOrderUseCase placeOrderUseCase(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new PlaceOrderUseCase(repository, publisher);
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }

        @Bean
        public MetricsListener metricsListener() {
            return new MetricsListener();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            context.getBean(PlaceOrderUseCase.class)
                .place("ORD-42", 12_500L, "EVT-42");
        }
    }
}
```

Chạy khi đã có JDK 17+ và Gradle:

```bash
gradle run --quiet
```

**Ba dòng output nghiệp vụ kỳ vọng** (hai dòng listener có thể đổi thứ tự):

```text
SAVED ORD-42 placed=true
AUDIT EVT-42 ORD-42
METRICS ORD-42 totalCents=12500
```

Giải thích:
1. `Order.place(...)` kiểm tra quy tắc `DRAFT → PLACED`, rồi ghi `OrderPlaced` vào danh sách event của aggregate. Nó không biết Spring.
2. `PlaceOrderUseCase` lưu aggregate trước khi phát. `drainEvents()` trả về bản sao bất biến của danh sách và xóa các event chờ phát để tránh publish trùng trong vòng đời object demo.
3. `ApplicationEventPublisher.publishEvent(Object)` chấp nhận `OrderPlaced` dù record không kế thừa `ApplicationEvent`. Spring `@EventListener` tự chọn các listener có tham số tương ứng.
4. Listener audit chỉ đọc event ID và aggregate ID; listener metrics chỉ đọc tổng tiền. Chúng không dựa vào side effect lẫn nhau.
5. Repository ở đây **lưu trong RAM**, không có transaction/commit. “`SAVED`” chỉ là log từ `Map.put`, không chứng minh event được lưu bền vững hoặc rollback được. `drainEvents()` xóa event đã chờ, nhưng nếu publisher lỗi sau đó thì demo cũng không có cơ chế retry. Phần triển khai production bên dưới giải quyết vấn đề này.

**Điểm cần test domain độc lập với Spring:** tạo `Order.draft(...)`, gọi `place(...)` rồi kiểm tra `isPlaced()`, một `OrderPlaced` với payload đúng. Gọi `place(...)` lần thứ hai phải ném `IllegalStateException` và không thêm event. Không cần mở `ApplicationContext` để kiểm tra invariant.

## 7. Thời điểm publish và transaction boundary

Ví dụ in-memory chỉ minh họa sự phân lớp. Với database thật, “aggregate đã chuyển trạng thái trong RAM” và “transaction đã commit” là hai mốc khác nhau.

Giả sử application service dùng `@Transactional`, một hướng triển khai thường gặp:

```java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = orderRepository.load(command.orderId());
    order.place(command.eventId());
    orderRepository.save(order);

    for (DomainEvent event : order.drainEvents()) {
        applicationEventPublisher.publishEvent(event);
    }
}
```

Đây là **mẫu tích hợp**, không phải chương trình biên dịch độc lập; giả định `PlaceOrder`, repository và fields đã được định nghĩa, cùng transaction manager và Spring proxy phù hợp.

Trong cấu hình multicaster đồng bộ mặc định, `@EventListener` chạy **khi event được phát**, thường là **trước khi transaction commit**. Vì thế, listener có thể thấy dữ liệu chưa commit trong cùng transaction, và một lời gọi HTTP/email từ listener có thể đã thực hiện dù DB cuối cùng rollback.

Đối với side effect chỉ hợp lệ sau commit, có thể dùng:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderPlaced(OrderPlaced event) {
    notificationJobService.enqueue(event.aggregateId());
}
```

Đây cũng là **mẫu tích hợp**, yêu cầu bean/listener Spring và các kiểu service thích hợp. `@TransactionalEventListener` mặc định xử lý ở `AFTER_COMMIT`; nếu không có transaction thì mặc định **không chạy**, trừ khi đặt `fallbackExecution=true`. Không bật fallback nếu yêu cầu nghiệp vụ là “chỉ chạy sau commit thành công”.

### Vì sao AFTER_COMMIT chưa bảo đảm giao nhận?

Nếu DB vừa commit nhưng process bị dừng trước khi callback hoàn tất, công việc hậu commit có thể chưa được làm. Một listener `AFTER_COMMIT` lỗi cũng **không rollback được transaction chính đã commit**. Đừng xem transaction callback hoặc Spring event in-process là queue bền vững.

Nếu callback sau commit cần ghi DB mới, phải mở **transaction mới** phù hợp qua service/transaction manager, ví dụ phương thức proxied với `Propagation.REQUIRES_NEW`. Resource transaction cũ có thể vẫn còn gắn trong lifecycle callback, nhưng thay đổi mới không tự được commit lần nữa.

Với tác vụ bắt buộc phải giao sau commit (gửi thông báo, cập nhật dịch vụ khác, báo cáo), cân nhắc **transactional outbox**.

## 8. Domain event, outbox và integration event

### 8.1. Mẫu transactional outbox

Application service lưu thay đổi aggregate và outbox record trong **cùng một DB transaction**:

```text
Transaction:
  1) UPDATE orders SET status = PLACED ...
  2) INSERT outbox(event_id, event_type, aggregate_id, payload, ...)
  3) COMMIT cả hai

Worker riêng:
  4) Đọc outbox chưa giao
  5) Publish integration event tới broker
  6) Ghi nhận delivery/retry
Consumer:
  7) Khử trùng lặp theo event ID hoặc business key
  8) Cập nhật trạng thái của chính mình
```

Nếu transaction rollback, cả aggregate và outbox record rollback. Nếu commit thành công, ý định phát event đã được lưu cùng dữ liệu nghiệp vụ; worker có thể tiếp tục sau restart.

Điều này thường mang ngữ nghĩa **at-least-once delivery** khi retry, vì worker có thể publish thành công rồi crash trước khi đánh dấu đã gửi. Do đó consumer phải **idempotent**. Không coi outbox là exactly-once end-to-end một cách mặc định.

### 8.2. Chuyển từ domain event sang integration event

Không cần gửi nguyên object domain ra ngoài. Một mapper có thể tạo payload công khai:
- `type`: ví dụ `sales.order.placed`.
- `eventId`: ID ổn định để khử trùng lặp.
- `aggregateId` và `aggregateVersion` (nếu cần ordering theo aggregate).
- `occurredAt`, `schemaVersion`, `correlationId`.
- Các trường được phép công khai theo hợp đồng và chính sách dữ liệu.

Domain có thể thay đổi class/field nội bộ trong khi integration event được version hóa độc lập. Nếu nhiều bounded context cần ý nghĩa khác nhau, có thể tạo các integration event phù hợp từ cùng một domain fact thay vì ép mọi consumer hiểu cấu trúc aggregate nội bộ.

## 9. Độc lập giữa các listener và chính sách lỗi

Nhiều listener cùng nghe `OrderPlaced` phải được coi là nhiều consumer của **cùng một sự thật**, không phải các bước bắt buộc gọi theo thứ tự ngầm.

Sai lầm thường gặp:

```text
Listener A: tính loyalty points rồi ghi vào Map tạm
Listener B: đọc Map đó để phát voucher
```

Nếu B chạy trước A, dữ liệu không có. Gán `@Order` chỉ ràng buộc ưu tiên gọi trong những cấu hình nhất định; nó không định nghĩa workflow có retry, transaction và durability rõ ràng.

Khi hai nhiệm vụ thật sự độc lập, mỗi listener nhận đủ dữ liệu từ event hoặc nguồn đã commit và sở hữu side effect của mình. Khi B **bắt buộc** cần kết quả A, hãy mô hình hóa bước A→B bằng application workflow hoặc sự kiện tiếp nối (ví dụ `PointsCalculated`), với cơ chế giao nhận phù hợp.

**Lỗi listener đồng bộ:** với multicaster Spring mặc định, `publishEvent` có thể ném exception của một listener; các listener phía sau có thể không được chạy. Muốn cô lập tác vụ phụ, xác định error handler, queue/executor và retry; không chỉ đổi `@Async` rồi cho rằng hệ thống đáng tin cậy. Bất đồng bộ thay đổi thời điểm hoàn tất, quan sát lỗi và transaction context.

**Idempotency:** một domain event có thể được gửi lại sau retry, hoặc hai sự kiện logic khác nhau cùng tác động một aggregate. Phân biệt `eventId` của lần xảy ra với `aggregateId` của đối tượng. Consumer nên có unique constraint hoặc transaction để đảm bảo một tác vụ không bị làm trùng ngoài ý muốn. Trong ví dụ, `EVT-42` được truyền cố định để stdout dự đoán được; trong production, hệ thống cần tạo ID duy nhất cho từng lần phát sinh sự kiện logic rồi giữ nguyên qua các lần retry.

## 10. Phiên bản, ordering và eventual consistency

Domain event thường diễn tả một trạng thái **tại một thời điểm**. Khi aggregate phát nhiều event, chẳng hạn:

```text
OrderPlaced(orderId=ORD-42, aggregateVersion=7)
OrderAddressChanged(orderId=ORD-42, aggregateVersion=8)
OrderCancelled(orderId=ORD-42, aggregateVersion=9)
```

Đây là mô hình minh họa. Nếu consumer nhận v9 trước v8, nó phải có chính sách rõ: chờ, sắp lại theo aggregate version, bỏ qua event cũ, hoặc truy vấn trạng thái cuối phù hợp. Event ID duy nhất giúp chống xử lý trùng nhưng **không tự giải quyết ordering**.

Nhiều hệ thống chấp nhận **eventual consistency** giữa bounded context: dữ liệu của consumer có thể cập nhật chậm hơn aggregate nguồn. Với tác vụ quan trọng cần nhất quán tức thời, hãy cân nhắc xử lý trong ranh giới transaction của aggregate thay vì ngầm kỳ vọng event async tạo ra tính nhất quán mạnh.

### Có cần event sourcing?

**Không.** Domain events và event sourcing là hai khái niệm khác nhau:
- Domain event là cách mô tả sự thật nghiệp vụ để các thành phần phản ứng.
- Event sourcing dùng chuỗi event như **nguồn dữ liệu gốc** để dựng lại trạng thái aggregate.

Một ứng dụng CRUD truyền thống vẫn có thể tạo domain events và dùng transactional outbox. Không phải cứ có `OrderPlaced` là cần dựng lại aggregate từ event log. Nếu chọn event sourcing, phải xử lý đầy đủ versioning, replay, snapshot và mutation theo aggregate; đó là một quyết định kiến trúc riêng.

## 11. Thiết kế event cho tính bảo trì

Một vài quy tắc thực tế:

1. **Tên theo nghiệp vụ ở thì đã xảy ra:** `OrderPlaced`, `PaymentCaptured`; tránh `DoSomethingEvent`, `UpdateTableEvent`.
2. **Payload bất biến và vừa đủ:** ID, dữ liệu snapshot có ý nghĩa, không truyền JPA entity mutable/lazy reference.
3. **Giữ ranh giới aggregate:** event được sinh ra bởi hành vi domain đã thỏa invariant; listener không được âm thầm sửa aggregate nguồn trong lúc event còn đang được phát.
4. **Tách domain khỏi vận chuyển:** aggregate thuần Java; application/infrastructure chịu trách nhiệm publish, transaction, outbox.
5. **Thời điểm publish có chủ đích:** phân biệt domain đã ghi nhận event, đã save, đã commit, consumer đã hoàn tất.
6. **Version hóa khi có consumer lâu dài:** không đổi ý nghĩa trường cũ một cách âm thầm, có khả năng xử lý payload version trước đó.
7. **Bảo đảm idempotency:** xử lý duplicate bằng key ổn định và transaction phù hợp.
8. **Quan sát hệ thống:** log/trace theo `eventId` hoặc correlation ID; đo retry, failed delivery và độ trễ. Tránh tag metric bằng event ID làm tăng cardinality không kiểm soát.
9. **Dữ liệu nhạy cảm:** giới hạn và phân loại payload. Event có thể được lưu lâu hoặc được gửi tới nhiều consumer.
10. **Không dùng event vì mọi thay đổi nhỏ:** chọn những chuyển trạng thái mang ý nghĩa và có consumer/policy thật sự.

## 12. Kiểm thử domain event theo từng tầng

| Tầng | Bài kiểm tra | Kỳ vọng |
| --- | --- | --- |
| Domain thuần Java | `Order.draft(...).place(...)` | State thành `PLACED`; tạo đúng một `OrderPlaced` với payload đúng |
| Domain invariant | Gọi `place(...)` lần thứ hai hoặc dữ liệu không hợp lệ | Ném lỗi hợp lý; không tạo event mới cho thao tác bị từ chối |
| Application service | Save aggregate rồi publish đúng các pending events | Gửi đúng event; không tự publish lại event đã drain trong cùng vòng đời |
| Spring integration | Mở `AnnotationConfigApplicationContext`, publish `OrderPlaced` | Hai `@EventListener` cùng nhận đúng payload |
| Transaction commit | Publish trong transaction rồi commit thật | Listener `AFTER_COMMIT` xử lý đúng thời điểm |
| Transaction rollback | Publish trong transaction rồi rollback | Không tạo side effect hậu commit; nhánh rollback nếu có được xử lý đúng |
| Outbox | Lưu aggregate + outbox cùng một transaction | Cùng commit hoặc rollback; không có outbox khi nghiệp vụ thất bại |
| Duplicate/retry | Giao lại cùng `eventId` | Consumer không tạo side effect không hợp lệ lần hai |
| Version/ordering | Gửi event cũ và mới đảo thứ tự | Consumer xử lý theo chính sách phiên bản/ordering đã định |

Test ở domain không cần Spring hay DB; đó là lợi ích trực tiếp của việc tách aggregate khỏi hạ tầng. Integration test dùng DB thật hoặc database test tương đương để xác minh rollback và outbox; mock `publishEvent` đơn thuần không chứng minh dữ liệu đã commit.

Nếu dùng `@Transactional` trong test và framework tự rollback khi kết thúc, listener `AFTER_COMMIT` có thể không chạy. Hãy dùng transaction được commit tường minh hoặc cơ chế test transaction phù hợp khi cần xác minh nhánh commit thật.

## 13. Các sai lầm phổ biến

- **Gọi Spring publisher trực tiếp từ mọi entity:** domain trở nên phụ thuộc framework, khó kiểm thử và khó kiểm soát commit.
- **Phát sự kiện trước khi kiểm tra invariant:** tạo thông báo cho hành động bị từ chối.
- **Xem `@EventListener` đồng nghĩa với “sau commit”:** listener thông thường có thể chạy trước khi transaction kết thúc.
- **Xem `@TransactionalEventListener(AFTER_COMMIT)` là durable queue:** tiến trình vẫn có thể chết sau commit trước khi side effect hoàn tất.
- **Truyền entity JPA mutable/lazy vào event:** dễ gặp race condition, stale state hoặc lỗi truy cập lazy ngoài transaction.
- **Không quản lý event ID ổn định:** retry có thể tạo duplicate khó nhận biết.
- **Nhầm domain event và integration event:** thay đổi nội bộ bất ngờ phá hợp đồng với dịch vụ khác.
- **Buộc các listener cùng event chạy theo thứ tự:** thực chất là một workflow có phụ thuộc cần mô hình rõ.
- **Không xử lý ngoại lệ khi publish:** lỗi listener đồng bộ có thể ảnh hưởng application service và listener khác.
- **Giả định mọi event cần event sourcing:** event sourcing là một cơ chế lưu trữ trạng thái riêng, không phải yêu cầu của DDD domain event.

## 14. Checklist khi review thiết kế

- [ ] Tên event mô tả một sự thật nghiệp vụ đã xảy ra?
- [ ] Aggregate tạo event tại chỗ chuyển trạng thái hợp lệ và bảo vệ invariant?
- [ ] Domain event là kiểu Java độc lập với cơ chế Spring/broker?
- [ ] Payload là snapshot bất biến, có ID ổn định và chỉ chứa dữ liệu cần thiết?
- [ ] Application service xác định rõ lúc save, publish, commit và xử lý lỗi?
- [ ] Side effect ngoài DB được trì hoãn hoặc lưu outbox khi nghiệp vụ yêu cầu?
- [ ] Domain event và integration event có ranh giới hợp đồng, versioning phù hợp?
- [ ] Consumer có idempotency, chính sách ordering, retry và quan sát?
- [ ] Tests bao phủ domain invariant, commit, rollback, duplicate và lỗi?
- [ ] Không dùng domain event để che giấu một chuỗi bước bắt buộc có dependency?

**Ghi nhớ:** domain event ghi lại một điều **đã xảy ra trong mô hình nghiệp vụ**. Aggregate quyết định khi nào điều đó đúng; application layer và infrastructure quyết định cách lưu, phát và xử lý event an toàn. Spring Application Events là một cơ chế tiện dụng trong một process, còn giao nhận liên hệ thống đáng tin cậy thường cần transaction/outbox, versioning và idempotency.

## Tài liệu tham khảo

- [Martin Fowler — Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring 6.1 API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring 6.1 API — EventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring 6.1 API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
