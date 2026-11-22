# Tránh truyền entity đang được quản lý trong payload của Spring Application Events

## 1. Mục tiêu bài học

Trong chủ đề **Thiết kế payload** của **Spring Framework Application Events**, một anti-pattern phổ biến là gửi trực tiếp JPA/Hibernate entity đang được persistence context quản lý:

```java
applicationEventPublisher.publishEvent(
    new OrderPlacedWithEntity(orderEntity)
);
```

Đoạn trên là **mã minh họa**, giả định `orderEntity` thuộc một transaction JPA đang mở. Về mặt Java, người nhận event có cùng tham chiếu object chứ không có một bản sao bất biến. Về mặt JPA, object đó còn chịu ảnh hưởng của dirty checking, lazy loading, lifecycle của `EntityManager` và transaction. Khi người dùng đổi thiết kế từ listener đồng bộ sang listener sau commit/async, các giả định trước đây có thể không còn đúng.

**Nguyên tắc thiết kế:** domain event phải ghi nhận **một sự thật nghiệp vụ tại thời điểm xảy ra**; payload nên gồm ID và **các value object/DTO bất biến** cần thiết, không chứa managed entity hay Hibernate proxy. Nếu consumer thực sự cần trạng thái DB mới nhất, nó có thể tự truy vấn bằng ID trong một transaction thích hợp.

Sau bài này, bạn cần biết:
1. Phân biệt managed/detached entity với immutable event.
2. Nhận diện lỗi shared mutable reference, lazy association, dirty checking và concurrency.
3. Chọn chiến lược payload **ID-only, immutable snapshot hoặc ID + snapshot**.
4. Dùng `@EventListener` và `@TransactionalEventListener(AFTER_COMMIT)` với ranh giới transaction rõ ràng.
5. Kiểm thử rollback, async, serialization, retry và dữ liệu lịch sử.

## 2. Managed entity là gì?

Một JPA **persistence context** theo dõi tập entity đang được quản lý. Ví dụ, kết quả từ `EntityManager.find(OrderEntity.class, id)` trong context phù hợp thường là managed instance. Entity có thể được tải từ repository trong một `@Transactional` service.

Một số đặc tính thiết yếu:

- **Identity map:** cùng persistence identity trong một persistence context thường ứng với cùng một entity Java instance.
- **Dirty checking:** nếu thay đổi một persistent property của managed entity, JPA provider có thể phát hiện và đồng bộ nó trong `flush()`/commit. Không cần gọi `save()` sau mọi setter.
- **Lazy associations:** một quan hệ `LAZY` có thể là proxy/collection chưa tải dữ liệu; khi truy cập có thể cần session còn hoạt động để chạy truy vấn.
- **Lifecycle:** khi context đóng, clear hoặc detach, entity chuyển sang detached. Trường dữ liệu đã tải vẫn là Java data, nhưng lazy association chưa được khởi tạo có thể không tải thêm được.
- **Transaction coupling:** trạng thái được quản lý, flush và rollback gắn với ranh giới transaction cụ thể chứ không phải bản thân sự kiện.

Ví dụ entity JPA:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Column(nullable = false)
    private String status;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    // Các constructor, getter và phương thức nghiệp vụ được lược bỏ.
}
```

Đoạn trên **không biên dịch độc lập**; cần `jakarta.persistence.*`, `java.util.*`, class `OrderLineEntity` và cấu hình JPA. Nó minh họa rằng entity chứa **trạng thái mutable** và quan hệ lazy. Một class chỉ có `@Entity` không tự động là managed: nó cần được gắn với persistence context thực tế.

### Managed ≠ snapshot

Một event có thể được lưu trong bộ nhớ hoặc xử lý muộn hơn lúc phát:

```text
Transaction mở
    |
    +--> OrderEntity managed, amount=12500
    |
    +--> publishEvent(new OrderPlacedWithEntity(order))
    |        |
    |        +--> Listener giữ tham chiếu cùng object
    |
    +--> Entity bị sửa tiếp, amount=19900
    |
    +--> Flush/commit/rollback; context cleanup
             |
             +--> Listener đọc lại object hoặc lazy proxy
```

Giá trị đọc ở cuối có thể **khác** giá trị ở lúc tạo event. Nếu listener đang cầm object managed và tự sửa nó, listener còn có thể làm phát sinh UPDATE ngoài ý muốn. Domain event vốn nên ghi lại điều đã xảy ra, không phải mở quyền sửa aggregate qua tham chiếu động.

## 3. Những rủi ro cụ thể khi gửi managed entity

| Vấn đề | Vì sao xảy ra | Hệ quả |
| --- | --- | --- |
| Mutable reference | Event chứa cùng object instance | Consumer đọc giá trị không còn đúng tại thời điểm phát |
| Dirty checking | Listener đổi field của managed entity | UPDATE được flush cùng transaction mà publisher không dự định |
| Lazy loading | Consumer truy cập quan hệ chưa init ngoài context phù hợp | `LazyInitializationException` hoặc truy vấn ngoài dự tính |
| Transaction lifecycle | Listener chạy trước, trong hoặc sau commit | Hành vi phụ thuộc timing/rollback |
| Không thread-safe | JPA `EntityManager`/Hibernate Session không phù hợp để chia sẻ tùy tiện giữa thread | Race condition và truy cập không hợp lệ |
| Object graph quá lớn | Quan hệ hai chiều, cascading, lazy proxy | N+1, recursion, hiệu năng, memory, serialization lỗi |
| Coupling kiến trúc | Consumer biết quá nhiều về entity mapping | Thay đổi persistence model kéo theo thay đổi event handler |
| Không replay tốt | Entity hiện tại khác dữ liệu lịch sử | Khôi phục/retry có thể xử lý thông tin sai |
| Quá nhiều dữ liệu | Entity có PII/internal fields | Lộ thông tin không cần thiết khi log hoặc gửi broker |

Một listener đồng bộ có thể chạy trơn tru với entity hiện tại, nhưng đó **không phải bằng chứng payload an toàn**. Thay đổi cấu hình multicaster, executor, lifecycle transaction hoặc số lượng listener có thể làm các phụ thuộc ngầm lộ ra.

### 3.1. Listener vô tình làm thay đổi transaction

```java
@EventListener
public void on(OrderPlacedWithEntity event) {
    event.order().setInternalNote("audited");
}
```

Đây là anti-pattern minh họa, giả định entity đang managed trong cùng transaction và field `internalNote` được JPA ánh xạ. Lời gọi setter có thể được dirty-check và persist lúc flush. Một consumer vốn chỉ “nghe event” đã can thiệp vào trạng thái aggregate.

Một thiết kế domain tốt nên kiểm soát thay đổi aggregate qua **phương thức nghiệp vụ và transaction rõ ràng**, không để listener ngoài ý muốn sửa entity nguồn bằng cách lấy reference từ payload.

### 3.2. Record chứa entity không làm entity bất biến

```java
public record UnsafeOrderPlaced(OrderEntity order) {}
```

`record` chỉ ngăn việc gán lại component reference qua setter trên record; nó **không deep-copy** object đang được tham chiếu. Nếu `order` mutable, event vẫn có dữ liệu thay đổi được. Tương tự, `record Event(List<OrderLineEntity> lines)` chưa an toàn nếu `List` hoặc các phần tử mutable.

### 3.3. Lazy loading sau transaction

Nếu listener đọc `event.order().getLines()` lúc persistence context đã đóng, Hibernate có thể không tải được quan hệ lazy và ném `LazyInitializationException`. Nhưng **không phải cứ `AFTER_COMMIT` là chắc chắn ném lỗi**: một số context/resource có thể còn bound cho tới bước cleanup, hoặc collection đã được load sẵn. Chính vì hành vi phụ thuộc môi trường mà việc truyền entity làm API event khó tin cậy.

### 3.4. Async hoặc background thread

`@Async`/executor không tự truyền `EntityManager` và transaction từ publisher qua thread. Mặc dù object reference vẫn tới được thread khác, JPA session không phải tài nguyên thread-safe để dùng đồng thời tùy ý; object có thể detached hoặc đang được sửa trên thread nguồn. Đừng coi một entity có thể chuyển qua executor như một payload bất biến.

### 3.5. Serialization và object graph

Nếu event được đưa vào JSON/outbox/broker, việc serialize entity có thể truy cập getter lazy, đi theo quan hệ hai chiều đến vô hạn, kéo theo graph dữ liệu quá lớn hoặc lộ PII. Jackson annotation có thể che một số field, nhưng **không thay đổi bản chất entity là persistence model**. Integration event cần schema/value DTO riêng và versioning rõ ràng.

## 4. Thiết kế immutable event payload

Ví dụ domain event phù hợp:

```java
public record OrderPlaced(
    String eventId,
    Long orderId,
    long totalCents,
    String currency
) {}
```

Đây là **record Java 17+ độc lập**; nó không import Spring hoặc Hibernate. Ý nghĩa:
- `eventId`: định danh **một lần xảy ra nghiệp vụ**. Khi retry chính event đó, giữ nguyên ID để consumer có thể khử trùng lặp.
- `orderId`: identity của aggregate mà event nói đến.
- `totalCents`: **snapshot** số tiền khi đơn được đặt. Dùng số nguyên đơn vị nhỏ nhất để tránh lỗi làm tròn `double`.
- `currency`: đơn vị tiền tệ của snapshot.

Nếu cần thời gian hoặc phiên bản, bổ sung `occurredAt: Instant`, `aggregateVersion`, `schemaVersion`, `correlationId` theo yêu cầu cụ thể. Không tự đưa toàn bộ `OrderEntity`, `EntityManager` hoặc Hibernate collection vào event.

### 4.1. Collection cần defensive copy

Record là **shallow immutable**. Với collection, hãy sao chép theo chiều sâu phù hợp:

```java
public record OrderPlacedWithItems(
    Long orderId,
    List<String> productCodes
) {
    public OrderPlacedWithItems {
        productCodes = List.copyOf(productCodes);
    }
}
```

Đoạn này biên dịch khi import `java.util.List`. `List.copyOf` tạo một collection bất biến và từ chối phần tử null. Vì `String` cũng bất biến, consumer không thể sửa snapshot qua List đã lưu. Nếu phần tử là object mutable, cần value object immutable hoặc deep copy; chỉ copy container không đủ.

Với `byte[]`, `Date` hoặc array khác, tạo defensive copy khi nhận và khi trả; ưu tiên `Instant` và các value object bất biến nếu phù hợp.

### 4.2. Chụp đúng thời điểm domain

Payload bất biến vẫn có thể **sai ngữ nghĩa** nếu chụp trước khi quy tắc nghiệp vụ hoàn tất. Ví dụ một đơn hàng còn đang tính chiết khấu chưa phải đơn đã đặt. Hãy phát `OrderPlaced` sau khi aggregate kiểm tra invariant và chốt tổng tiền, không chỉ sau một dòng SQL tùy ý.

Không ghi `eventId` mới mỗi lần vận chuyển lại event cũ; một lần xảy ra domain fact phải giữ identity ổn định qua retry.

## 5. Payload chỉ ID, snapshot hay kết hợp?

| Kiểu | Ví dụ | Nên dùng khi | Đánh đổi |
| --- | --- | --- | --- |
| **ID-only** | `OrderPlaced(eventId, orderId)` | Consumer muốn đọc **trạng thái hiện tại** hoặc chỉ cần xóa cache | Phải query; trạng thái đọc có thể mới hơn lúc phát hoặc object đã bị xóa |
| **Snapshot** | `OrderPlaced(eventId, orderId, amount, currency)` | Consumer cần facts lịch sử tại thời điểm đặt đơn | Phải đảm bảo snapshot đúng và bảo trì schema |
| **ID + snapshot tối thiểu** | `OrderPlaced(eventId, orderId, totalCents)` | Consumer cần một số facts cố định và đôi lúc cần query thêm | Phải mô tả field nào là lịch sử và field nào được truy vấn |

Giả sử lúc đặt hàng tổng tiền là **12.500 cent**, rồi sau đó dữ liệu nguồn được cập nhật thành **19.900 cent**. Một listener tạo chứng từ giá tại thời điểm mua phải dùng `totalCents=12500` trong event; nếu query lại entity hiện tại nó có thể thu được 19.900 và tạo chứng từ sai.

Ngược lại, listener xóa cache trạng thái đơn hàng chỉ cần `orderId`. Gửi full entity để lấy ID là dư thừa. Với workflow cần **state mới nhất**, query lại sau commit dưới transaction riêng là hợp lý, nhưng nên chấp nhận hoặc giải quyết **eventual consistency** và xung đột phiên bản.

### 5.1. ID do database sinh ra

Nếu dùng `@GeneratedValue`, cần biết thời điểm ID thực sự được gán theo strategy; không phải mọi trường hợp đều có ID trước persist/flush. Hãy dựng payload khi ID cần thiết đã tồn tại hoặc tạo domain identifier ở application trước khi persist. Đừng tùy tiện flush chỉ để lấy ID mà bỏ qua tác động tới hiệu năng và thời điểm SQL.

Nếu payload cần `@Version` chính xác, chú ý giá trị phiên bản có thể tăng khi flush. Hãy kiểm chứng trong integration test và chọn mốc snapshot rõ ràng; không đoán rằng version mới luôn đã có ngay sau một setter.

## 6. Chương trình Java 17+ chạy được: lỗi reference mutable

Đây là chương trình Spring Context độc lập minh họa lỗi **giữ cùng reference tới object mutable**. Nó **không cấu hình JPA**: `OrderEntity` trong ví dụ là POJO mô phỏng đặc tính mutable; vì thế ví dụ không chứng minh dirty checking hoặc lazy loading. Phần JPA thật được áp dụng qua các mẫu tích hợp ở mục tiếp theo.

Cấu trúc:

```text
entity-event-payload-demo/
├── build.gradle
└── src/main/java/demo/EntityPayloadDemo.java
```

`build.gradle`:

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
    mainClass = 'demo.EntityPayloadDemo'
}
```

`src/main/java/demo/EntityPayloadDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EntityPayloadDemo {

    // POJO mutable mô phỏng một phần hành vi JPA entity.
    public static final class OrderEntity {
        private final String id;
        private long totalCents;

        public OrderEntity(String id, long totalCents) {
            this.id = id;
            this.totalCents = totalCents;
        }

        public String id() {
            return id;
        }

        public long totalCents() {
            return totalCents;
        }

        public void changeTotal(long newTotalCents) {
            this.totalCents = newTotalCents;
        }
    }

    public record UnsafeOrderPlaced(OrderEntity order) {}

    public record OrderPlaced(
            String eventId,
            String orderId,
            long totalCents
    ) {}

    public static final class UnsafeConsumer {
        private OrderEntity savedReference;

        @EventListener
        public void on(UnsafeOrderPlaced event) {
            savedReference = event.order();
        }

        public String readLater() {
            return "UNSAFE later totalCents="
                    + savedReference.totalCents();
        }
    }

    public static final class SafeConsumer {
        private OrderPlaced savedSnapshot;

        @EventListener
        public void on(OrderPlaced event) {
            savedSnapshot = event;
        }

        public String readLater() {
            return "SAFE snapshot totalCents="
                    + savedSnapshot.totalCents();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public UnsafeConsumer unsafeConsumer() {
            return new UnsafeConsumer();
        }

        @Bean
        public SafeConsumer safeConsumer() {
            return new SafeConsumer();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            OrderEntity order = new OrderEntity("ORD-42", 12_500);
            context.publishEvent(new UnsafeOrderPlaced(order));
            context.publishEvent(new OrderPlaced(
                "EVT-42", order.id(), order.totalCents()
            ));

            // Sau publish, object gốc bị thay đổi.
            order.changeTotal(19_900);

            System.out.println(
                context.getBean(UnsafeConsumer.class).readLater()
            );
            System.out.println(
                context.getBean(SafeConsumer.class).readLater()
            );
        }
    }
}
```

Chạy với JDK 17+ và Gradle đã cài:

```bash
gradle run --quiet
```

**Stdout nghiệp vụ:**

```text
UNSAFE later totalCents=19900
SAFE snapshot totalCents=12500
```

Giải thích output:

1. `UnsafeOrderPlaced` giữ reference `OrderEntity`. `UnsafeConsumer` lưu reference đó, nên khi đọc **sau khi** `order.changeTotal(19900)` nó thấy 19.900.
2. `OrderPlaced` nhận các giá trị ID/tổng tiền **được copy** khi record được tạo. `SafeConsumer` thấy 12.500 bất kể entity gốc đổi sau đó.
3. Cả hai listener nhận event đồng bộ trong cùng Spring context; lỗi xuất hiện vì **giữ reference để đọc sau**, không cần thread bất đồng bộ.
4. Trong ứng dụng JPA thực, một listener đồng bộ còn có thể sửa managed entity và khiến provider flush thay đổi. Chương trình mô phỏng không làm việc đó vì không có `EntityManager`.

Để unit test, bạn cũng có thể kiểm tra `UnsafeConsumer.readLater()` đổi theo object nguồn còn `SafeConsumer.readLater()` giữ nguyên snapshot. Không dùng mẫu singleton giữ event vô hạn trong production; ở đây listener lưu đúng một reference chỉ để biểu diễn khác biệt.

## 7. Mẫu dùng JPA thật: phát event từ application service

### 7.1. Anti-pattern trong transaction

```java
@Transactional
public void placeOrder(Long id) {
    OrderEntity order = orderRepository.findById(id)
        .orElseThrow();

    order.place();
    publisher.publishEvent(new OrderPlacedWithEntity(order));
}
```

Đây là đoạn tích hợp, không phải file Java tự chạy: cần JPA entity, repository, event, Spring service, `@Transactional` và transaction manager. `order` thường là managed entity trong transaction. Listener thông thường có thể nhìn và sửa object **trước commit**.

### 7.2. Truyền immutable DTO thay vì entity

```java
public record OrderPlacedEvent(
    String eventId,
    Long orderId,
    long totalCents
) {}

@Service
public class PlaceOrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public PlaceOrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void place(Long id) {
        OrderEntity order = repository.findById(id).orElseThrow();
        order.place();

        publisher.publishEvent(new OrderPlacedEvent(
            java.util.UUID.randomUUID().toString(),
            order.getId(),
            order.getTotalCents()
        ));
    }
}
```

Đây là mẫu **tích hợp**, giả định `OrderRepository`, `OrderEntity`, import Spring/JPA tương ứng và Spring-managed bean. Nó không gửi entity ra khỏi service; publisher chỉ gửi ID và total snapshot. `OrderPlacedEvent` là record thuần dữ liệu.

**Cảnh báo:** event đã được publish **trước khi transaction kết thúc**. Nếu listener bình thường gây side effect ngoài DB thì side effect đó không rollback cùng transaction. Payload immutable giải quyết coupling object, **không tự giải quyết timing commit**. Cần xử lý phase hoặc lưu outbox theo yêu cầu nghiệp vụ.

Nếu domain có event pending trong aggregate, application service có thể chuyển các domain event đó thành payload ứng dụng hoặc outbox record. Tránh để aggregate inject `ApplicationEventPublisher` chỉ để phát một entity đang managed.

## 8. Ranh giới transaction của listener

### 8.1. Listener bình thường chạy khi dispatch

Với `SimpleApplicationEventMulticaster` đồng bộ mặc định, `@EventListener` nhận event trong lời gọi `publishEvent(...)`, thường cùng thread và trong transaction hiện hành nếu publisher được gọi bên trong `@Transactional` method.

Hệ quả:
- Có thể nhìn trạng thái chưa commit.
- Có thể truy cập lazy relations trong một số điều kiện.
- Nếu listener được trao entity managed, có thể gây dirty checking.
- Một lỗi listener có thể lan sang publisher, ảnh hưởng luồng transaction tùy cấu hình error handler.

Vì vậy, đừng dựa vào “hiện tại listener đọc được entity” để cho rằng payload contract đúng.

### 8.2. Listener sau commit

Khi nghiệp vụ yêu cầu công việc chỉ diễn ra sau commit:

```java
@Component
public class OrderNotificationListener {

    private final NotificationGateway notifications;

    public OrderNotificationListener(
            NotificationGateway notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        notifications.confirm(
            event.orderId(),
            event.totalCents()
        );
    }
}
```

Mẫu này cần bean `NotificationGateway` và các import Spring. Listener **chỉ dùng DTO**. `@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`; nếu không có transaction phù hợp, nó **mặc định không chạy** (`fallbackExecution=false`).

**Quan trọng:** `AFTER_COMMIT` cho biết DB transaction gốc đã commit, **không** tự bảo đảm notification được gửi, broker đã lưu message hoặc HTTP request thành công. Nếu callback thất bại, không thể rollback transaction gốc đã commit.

### 8.3. Đọc DB sau commit: dùng transaction mới khi cần

Nếu event chỉ mang ID và consumer cần thông tin hiện tại, tổ chức truy vấn thành một Spring service riêng:

```java
@Service
public class OrderSnapshotReader {

    private final OrderRepository orders;

    public OrderSnapshotReader(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(
        readOnly = true,
        propagation = Propagation.REQUIRES_NEW
    )
    public OrderSummary read(Long id) {
        OrderEntity order = orders.findById(id).orElseThrow();
        return new OrderSummary(
            order.getId(),
            order.getStatus(),
            order.getTotalCents()
        );
    }
}

public record OrderSummary(
    Long id,
    String status,
    long totalCents
) {}
```

Đây là mẫu tích hợp, không phải file độc lập; yêu cầu repository/entity/import phù hợp. Listener `AFTER_COMMIT` gọi `OrderSnapshotReader` **qua Spring proxy** để transaction mới có hiệu lực. Vì tài nguyên transaction cũ có thể vẫn bound trong một phần callback after-completion, `REQUIRES_NEW` làm rõ rằng thao tác DB hậu commit có transaction mới độc lập. Self-invocation trong cùng bean có thể bỏ qua proxy advice và không tạo transaction mới.

Phân biệt rõ **hai câu hỏi nghiệp vụ**: `OrderPlacedEvent.totalCents()` trả lời “giá lúc đặt hàng?”, còn `OrderSnapshotReader.read(id)` trả lời “giá đang lưu khi đọc?”. Nếu dữ liệu đổi giữa hai thời điểm, hai số khác nhau là bình thường.

## 9. Async, lazy loading và serialization

### 9.1. Bất đồng bộ không kế thừa transaction context

`@Async` hoặc executor task có thể chạy sau khi transaction gốc đóng. Entity vẫn là object Java nhưng không tự mang `EntityManager` phù hợp sang thread khác. Sharing session/concurrent entity state không an toàn; riêng lazy proxy có thể phụ thuộc Session mà thread này không sở hữu.

Giải pháp: truyền immutable DTO; nếu cần database, để handler đọc bằng ID trong transaction phù hợp ở phía mình. Nếu việc xử lý là quan trọng, dùng queue/worker có quản lý, retry và quan sát. Đổi từ sync sang async không tự đảm bảo reliability.

### 9.2. Không phụ thuộc Open Session in View

Open EntityManager in View (OSIV) có thể giữ persistence context mở đến cuối web request ở một số cấu hình. Nó **không** hứa rằng background job hoặc event async sẽ có session tương ứng, và không phải giải pháp để biến managed entity thành event payload an toàn. Quan hệ lazy nên được xử lý có chủ đích bằng query/fetch phù hợp hoặc snapshot trong transaction cần thiết.

### 9.3. JSON/integration event

Không serialize entity trực tiếp cho đối tác hoặc broker: có thể truy vấn bất ngờ, vòng lặp quan hệ, kiểu proxy đặc thù, PII và schema bị ràng buộc với database mapping. Hãy định nghĩa integration event DTO riêng với các trường được phép công khai, versioning, serialization test và chính sách bảo vệ dữ liệu. Snapshot trong event phải đủ cho consumer cần lịch sử; ID-only có thể phù hợp với consumer cần dữ liệu hiện tại.

## 10. Khi side effect phải bền vững: transactional outbox

Spring `ApplicationEventPublisher` là cơ chế dispatch **trong một application context**, không phải message broker bền vững. `@TransactionalEventListener(AFTER_COMMIT)` giúp chọn phase nhưng vẫn có khoảng trống nếu tiến trình chết sau DB commit trước khi callback gửi thành công.

Nếu event bắt buộc phải đến consumer ngoài hệ thống:

```text
Trong cùng DB transaction:
  1. Aggregate chuyển trạng thái nghiệp vụ hợp lệ.
  2. Tạo immutable OrderPlacedEvent (không có JPA entity).
  3. INSERT outbox(eventId, aggregateId, type, payloadJson, version).
  4. COMMIT aggregate + outbox nguyên tử.

Outbox publisher/worker:
  5. Đọc các bản ghi chưa gửi.
  6. Publish integration DTO lên broker.
  7. Ghi nhận kết quả hoặc retry/backoff.

Consumer:
  8. Dedupe dựa trên eventId.
  9. Xử lý idempotent với transaction phù hợp.
```

Nếu transaction rollback, outbox cũng rollback. Nếu commit, ý định phát thông điệp đã được lưu và có thể retry sau restart. Tuy nhiên worker có thể publish thành công rồi crash trước khi đánh dấu đã gửi, dẫn đến **at-least-once delivery**; consumer vẫn cần idempotency. Không coi outbox là exactly-once toàn hệ thống một cách mặc định.

Không ghi một object entity vào outbox rồi mong khôi phục nó như managed instance. Outbox lưu payload độc lập với JPA persistence context.

## 11. Event ID, snapshot, version và tính nhất quán

Sự kiện `OrderPlaced` nên có một `eventId` ổn định cho lần xảy ra đó. Nếu bản ghi được retry giao 3 lần, dùng **cùng eventId** để consumer nhận ra duplicate. `orderId` định danh aggregate, không tự phân biệt nhiều event khác nhau trên cùng order.

Với aggregate có thay đổi liên tiếp, có thể cần `aggregateVersion` hoặc sequence nhằm phát hiện event đến sai thứ tự. Nhưng với JPA `@Version`, giá trị version có thể tăng lúc flush: đừng mặc định lấy ngay trước flush là đúng version mới. Đối với consumer cần lịch sử, snapshot giữ lại fact ở thời điểm xảy ra; còn consumer cần trạng thái mới nhất phải chấp nhận eventual consistency hoặc dùng cơ chế ordering/optimistic locking.

Một event bất biến chỉ an toàn khi **ngữ nghĩa** cũng rõ. Ví dụ snapshot tổng tiền tại thời điểm order được đặt khác với giá trị hiện tại trong DB; dùng nhầm chúng có thể gây lỗi nghiệp vụ dù code hoàn toàn compile.

## 12. Kiểm thử cần thiết

| Kịch bản | Cách test | Kỳ vọng |
| --- | --- | --- |
| Mutable reference | Publish event chứa object, sau đó sửa object nguồn | Chứng minh event sai có thể đọc giá trị mới; DTO snapshot vẫn giữ giá trị gốc |
| Domain invariant | Một thao tác thất bại trước khi chuyển trạng thái | Không tạo domain event giả |
| Dirty checking | Integration test với JPA managed entity và listener thay field | Xác minh nguy cơ thay đổi bị flush ngoài ý muốn; code tốt không gửi entity |
| Lazy association | Đóng persistence context rồi truy cập collection chưa load | Trường hợp sai có thể `LazyInitializationException`; DTO không phụ thuộc |
| Commit | Publish trong transaction, commit thật | Listener `AFTER_COMMIT` xử lý đúng event |
| Rollback | Publish trong transaction rồi rollback | Không có side effect `AFTER_COMMIT` |
| Async | Chuyển consumer sang executor | Không cần session/transaction của publisher; chỉ nhận DTO |
| Serialization | Serialize event qua serializer thật | Không có proxy/entity; schema chính xác, không rò rỉ PII |
| Retry | Phát lại cùng eventId | Consumer không lặp side effect bất hợp lệ |
| Snapshot lịch sử | Sửa entity sau thời điểm tạo event | Consumer lịch sử dùng dữ liệu snapshot, không phải trạng thái mới |
| Outbox | Commit và rollback cả aggregate lẫn outbox | Không có outbox khi rollback; có record khi commit |

Integration test dùng `@Transactional` của Spring Test đôi khi tự rollback cuối test, khiến `AFTER_COMMIT` không được gọi. Muốn kiểm tra commit, sử dụng `TransactionTemplate` hoặc phương án kết thúc transaction của test framework rồi assert trạng thái DB và số callback. Mock `publishEvent` một mình không chứng minh transaction hay lazy lifecycle đúng.

### Static review

Khi thấy một event có field kiểu `OrderEntity`, `CustomerEntity`, `HibernateProxy`, `PersistentCollection` hoặc cả aggregate mutable, hãy hỏi: consumer có thật sự cần object đó không? Nếu chỉ cần ID hoặc một vài fact, đổi sang DTO. Value object immutable do domain định nghĩa không phải JPA entity và thường là thành phần phù hợp của event.

## 13. Lỗi phổ biến

1. **Dùng `record Event(OrderEntity entity)` và gọi nó immutable**: record chỉ bất biến nông.
2. **Để listener tùy ý sửa entity đang managed**: dirty checking có thể ghi DB ngoài chủ đích.
3. **Tin rằng entity luôn truy cập lazy được**: phụ thuộc session/context và dữ liệu đã tải.
4. **Chuyển entity sang `@Async` thread**: transaction/session không tự chuyển theo.
5. **Bật OSIV để xử lý mọi LazyInitializationException**: không giải quyết hợp đồng payload event.
6. **Serialize toàn bộ entity**: graph và proxy gây lỗi, có nguy cơ lộ dữ liệu.
7. **Chỉ gửi ID khi consumer cần fact lịch sử**: query lại có thể đọc giá trị mới hơn event.
8. **Tạo snapshot trước khi nghiệp vụ chốt giá/trạng thái**: payload bất biến nhưng sai ngữ nghĩa.
9. **Gọi `@EventListener` là sau commit**: listener thường có thể chạy trước DB commit.
10. **Coi `@TransactionalEventListener` như queue bền vững**: callback sau commit có thể bị mất khi crash.
11. **Ghi DB trong after-commit mà không tạo transaction mới**: resource cũ không tự tạo commit mới.
12. **Phát lại event bằng eventId mới**: làm khó khử trùng lặp.
13. **Dùng entity mapping làm public event schema**: đổi database làm ảnh hưởng consumer bên ngoài.

## 14. Checklist triển khai

- [ ] Domain event diễn đạt một fact nghiệp vụ, không chỉ “entity đã save”?
- [ ] Payload **không** chứa JPA managed entity, lazy proxy, Hibernate Session hay persistence context?
- [ ] Có ID và immutable snapshot tối thiểu phù hợp với nhu cầu lịch sử/trạng thái hiện tại?
- [ ] Record/list/value object đã defensive-copy đúng mức?
- [ ] ID được sinh đã sẵn sàng và eventId ổn định khi retry?
- [ ] Snapshot được chụp **sau** khi quyết định nghiệp vụ hoàn tất?
- [ ] Có phân biệt `@EventListener` trong transaction và `@TransactionalEventListener` sau commit?
- [ ] Nếu listener hậu commit đọc/ghi DB, có transaction riêng khi cần?
- [ ] Async consumer không phụ thuộc thread/session của publisher?
- [ ] Payload có schema/version, không lộ PII hoặc graph dữ liệu dư thừa?
- [ ] Nếu không được phép mất event, có outbox/durable messaging và idempotency?
- [ ] Tests bao gồm rollback, lazy loading, serialization, retry và mutable reference?

**Kết luận:** managed entity là object sống trong lifecycle persistence/transaction; domain event là một **fact** cần giữ nguyên ý nghĩa qua thời gian và consumer. Tránh gửi trực tiếp managed entity trong Spring event payload. Hãy truyền **ID cùng immutable snapshot phù hợp**, query lại trong transaction rõ ràng khi cần trạng thái mới nhất, và dùng outbox khi sự kiện phải được giao bền vững.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring 6.1 API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring 6.1 API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Jakarta Persistence 3.1 specification](https://jakarta.ee/specifications/persistence/3.1/)
- [Hibernate ORM 6.4 User Guide](https://docs.jboss.org/hibernate/orm/6.4/userguide/html_single/Hibernate_User_Guide.html)
