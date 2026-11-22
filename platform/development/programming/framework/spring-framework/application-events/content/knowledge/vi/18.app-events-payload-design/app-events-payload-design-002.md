# ID định danh đối tượng nghiệp vụ trong payload Spring Application Events

## 1. Mục tiêu: event mang ID thay vì ôm cả entity

Khi một nghiệp vụ thay đổi trạng thái, ứng dụng Spring có thể phát sự kiện bằng `ApplicationEventPublisher` và xử lý bằng `@EventListener` hoặc `ApplicationListener`. Một quyết định thiết kế rất quan trọng là: **event nên mang cả đối tượng nghiệp vụ hay chỉ mang ID định danh của đối tượng đó?**

Ví dụ, sau khi tạo đơn hàng:

~~~java
// Đơn giản và dễ kiểm soát: payload chứa ID và thông tin sự kiện cần thiết.
public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    long aggregateVersion
) {}
~~~

Khác với:

~~~java
// Cần cân nhắc: payload mang tham chiếu đến JPA entity có thể thay đổi.
public record OrderPlaced(OrderJpaEntity order) {}
~~~

Các đoạn này là **mã minh họa**, không phải chương trình độc lập. `OrderJpaEntity` giả định là entity của ứng dụng.

Việc truyền ID giúp listener **không phụ thuộc trực tiếp vào cùng instance entity, persistence context, lazy-loading proxy hoặc graph đối tượng quá lớn**. Nó cũng giúp ranh giới giữa các module rõ ràng: publisher thông báo “đơn hàng có ID X đã được tạo”, còn consumer lựa chọn cách lấy dữ liệu theo nhu cầu.

Nhưng quy tắc “luôn chỉ truyền ID” cũng không tuyệt đối. Nếu consumer cần chính xác trạng thái tại thời điểm sự kiện xảy ra, đọc lại đối tượng theo ID ở thời điểm xử lý có thể thấy phiên bản mới hơn hoặc đối tượng đã bị xóa. Khi đó cần kết hợp **ID + eventId + version**, snapshot bất biến, hoặc outbox tùy hợp đồng dữ liệu.

Bài học tập trung vào cách chọn, tạo, đặt tên, truyền và kiểm chứng **ID định danh đối tượng nghiệp vụ** trong Spring Application Events.

## 2. Định nghĩa các loại ID cần phân biệt

Một payload thực tế có thể chứa nhiều trường đều kết thúc bằng `Id` nhưng hoàn toàn khác trách nhiệm.

| Trường | Nhận dạng cái gì? | Ví dụ | Tính chất quan trọng |
|---|---|---|---|
| `orderId` / `aggregateId` | Một đối tượng nghiệp vụ hoặc aggregate cụ thể | UUID của đơn hàng | Ổn định theo vòng đời đối tượng |
| `eventId` | Một **lần xuất hiện** sự kiện cụ thể | UUID của `OrderPlaced` | Dùng cho deduplication/idempotency theo sự kiện |
| `customerId` | Đối tượng nghiệp vụ khác liên quan | ID khách hàng | Phải giữ rõ chủ sở hữu/loại ID |
| `tenantId` | Không gian tenant mà đối tượng thuộc về | ID tổ chức | Dùng để giới hạn quyền và định tuyến dữ liệu |
| `correlationId` | Một luồng yêu cầu hoặc quy trình qua nhiều sự kiện | ID saga/request | Hỗ trợ tracing nghiệp vụ |
| `causationId` | Event hoặc command đã gây ra event hiện tại | ID sự kiện nguồn | Hỗ trợ lần theo quan hệ nhân quả |
| `aggregateVersion` | Phiên bản của đối tượng khi sự kiện được phát | 12 | Hỗ trợ kiểm tra thứ tự/staleness; **không phải ID** |

**Không dùng `orderId` để thay `eventId`.** Một đơn hàng có thể phát `OrderPlaced`, `OrderPaid`, `OrderShipped` và nhiều lần `OrderUpdated`; các event đều có cùng `orderId` nhưng phải có khả năng nhận dạng riêng từng lần phát.

Ví dụ:

~~~json
{
  "eventId": "22222222-2222-4222-8222-222222222222",
  "eventType": "OrderPaid",
  "orderId": "11111111-1111-4111-8111-111111111111",
  "aggregateVersion": 7,
  "correlationId": "checkout-req-391",
  "occurredAt": "2026-11-11T05:20:00Z"
}
~~~

JSON chỉ để minh họa thiết kế; UUID và timestamp ở đây là dữ liệu giả định. **ID nghiệp vụ** trả lời câu hỏi “đối tượng nào?”, **ID sự kiện** trả lời “lần thay đổi nào?” và **version** trả lời “trạng thái thứ mấy?”.

## 3. ID kỹ thuật và mã nghiệp vụ có thể là hai thứ khác nhau

Trong nhiều hệ thống có cả khóa lưu trữ lẫn mã hiển thị:

~~~text
orders.id             = 9be6d7ce-...
orders.order_number   = SO-2026-000137
~~~

- `id`: khóa kỹ thuật ổn định để tham chiếu giữa module, bảng, event.
- `orderNumber`: mã người dùng nhập/nhìn thấy, có thể mang quy tắc theo năm, chi nhánh, loại đơn hoặc hệ thống bên ngoài.

Nếu mã nghiệp vụ có thể đổi, tái cấp hoặc không duy nhất toàn cục, **không coi nó là identity chính** của aggregate. Event nên mang khóa được bảo đảm duy nhất và ổn định; mã hiển thị chỉ là thông tin bổ sung khi thật cần.

Một số kiểu ID thường dùng:

| Kiểu | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|
| `long`/`Long` do DB sinh | Ngắn, hiệu quả lưu trữ/index, dễ dùng với quan hệ SQL | Thường chưa có trước insert; khó kết hợp nhiều hệ thống nếu không kèm namespace |
| `UUID` sinh ở ứng dụng | Có thể tạo trước khi persist; hợp với hệ thống phân tán | Dài hơn; cần đánh giá locality/index và chiến lược sinh |
| `String` mã nghiệp vụ | Dễ gắn ý nghĩa và tương tác với hệ thống bên ngoài | Format có thể thay đổi; dễ nhầm mã hiển thị với khóa ổn định |
| `record OrderId(UUID value)` | Type-safe, tránh nhầm `OrderId` với `CustomerId` | Cần converter/serializer và định nghĩa hợp đồng JSON |
| Khóa ghép, ví dụ `(tenantId, orderId)` | Phù hợp hệ thống đa tenant hoặc ID duy nhất theo tenant | Consumer phải nhận đủ thành phần, có index và quy tắc unique tương ứng |

**Nguyên tắc:** kiểu ID phải phản ánh *quy tắc định danh thật sự* của domain. Không mặc định mọi ID mang số đều là primary key; không mặc định UUID tự động làm event bền vững hoặc chống trùng.

## 4. Mẫu payload khuyến nghị với Java record

Java 17 có `record`, phù hợp với event đơn giản, bất biến ở mức các thành phần của record:

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPaid(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt
) {
    public OrderPaid {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        if (aggregateVersion < 1) {
            throw new IllegalArgumentException("version must be positive");
        }
    }
}
~~~

Đây là **đoạn record minh họa**. Khi chọn payload cần xác định:

1. **Tên rõ domain:** `orderId` tốt hơn `id` nếu event có nhiều đối tượng liên quan.
2. **Không null:** validate từ lúc khởi tạo, không đợi listener tự phát hiện.
3. **Kiểu ổn định:** cân nhắc converter giữa `OrderId`/`UUID`/`String` khi qua module hoặc JSON.
4. **Event occurrence:** cung cấp `eventId` nếu cần phát lại, quan sát hoặc dedupe.
5. **Version:** nếu listener cần phân biệt update cũ–mới, mang phiên bản aggregate đã lưu/được xác định đúng.
6. **Thời điểm:** `occurredAt` là thời gian ghi nhận sự kiện, **không chứng minh commit đã hoàn thành** và không phải clock toàn cục tuyệt đối.
7. **Không truyền secret:** tránh password, access token, dữ liệu cá nhân không cần thiết; ID cũng có thể là thông tin nhạy cảm tùy domain.

### Record là shallowly immutable

`record` làm các **field tham chiếu** cuối cùng và cung cấp constructor/accessors, nhưng nếu một field là `List` hoặc một entity mutable, bản thân object được tham chiếu vẫn có thể bị sửa. Với event định danh, ưu tiên thành phần bất biến như `UUID`, `String`, primitive hoặc value object thật sự immutable.

Ví dụ nên tránh:

~~~java
public record OrderChanged(UUID orderId, List<OrderLineEntity> lines) {}
// List và các OrderLineEntity bên trong có thể vẫn mutable.
// Không coi đây là snapshot bất biến chỉ vì dùng record.
~~~

Đoạn trên minh họa; `OrderLineEntity` và imports cần định nghĩa trong ứng dụng.

## 5. Vì sao không nên truyền JPA entity qua event một cách mặc định?

Xét payload:

~~~java
record OrderPlaced(Order order) {}
~~~

Nếu `Order` là JPA entity, event này có thể gặp các vấn đề:

- **Mutable reference:** publisher và listener giữ cùng Java object; listener nhìn thấy trạng thái thay đổi sau khi event được tạo.
- **Persistence context:** entity còn managed trong transaction T1 nhưng thành detached ở worker/transaction khác.
- **Lazy loading:** truy cập `order.getItems()` sau khi session đóng có thể lỗi `LazyInitializationException`.
- **Coupling:** listener bị phụ thuộc vào loại entity và mapping nội bộ của module tạo event.
- **Serialization:** entity chứa association/proxy phức tạp, vòng tham chiếu hoặc thông tin không muốn gửi.
- **Thời điểm:** listener async có thể chạy sau commit; entity truyền theo không tự được reattach.

Thay vì chia sẻ object, publisher phát:

~~~java
publisher.publishEvent(new OrderPlaced(order.getId(), order.getVersion()));
~~~

và consumer dùng repository riêng nếu cần:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Order order = repository.findById(event.orderId())
        .orElseThrow();
    // Chỉ dùng dữ liệu thực sự cần; lưu ý transaction và thời điểm đọc.
}
~~~

Hai đoạn này là **mẫu tích hợp**; `Order`, `OrderPlaced` và `repository` phải được định nghĩa đồng nhất. **Truyền ID không tự giải quyết mọi vấn đề về thời điểm:** khi event phát trước commit, consumer async đọc database có thể chưa thấy record; sau commit nó có thể đã thay đổi lần nữa.

## 6. Ví dụ Java 17 chạy được: phân biệt eventId, orderId và trạng thái hiện tại

Ví dụ dùng Spring Framework **6.2.8**, Maven, Java 17 và repository trong bộ nhớ để làm rõ ranh giới giữa payload định danh và entity state. Không cần Spring Boot, database hay transaction để chạy ví dụ cơ bản.

Chương trình thực hiện:

1. Tạo một `OrderId` type-safe.
2. Lưu trạng thái đơn ở repository.
3. Phát một `OrderPlaced` có `eventId`, `orderId` và `aggregateVersion`.
4. Listener chỉ nhận event mang ID, rồi **tra repository theo ID**.
5. Sau khi event được xử lý, service tiếp tục cập nhật trạng thái đơn; event đã phát không bị biến đổi theo bản ghi mới.

Cấu trúc:

~~~text
business-id-event-demo/
├── pom.xml
└── src/main/java/demo/BusinessIdEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>business-id-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/BusinessIdEventDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class BusinessIdEventDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {

            OrderId orderId = new OrderId(UUID.fromString(
                "00000000-0000-0000-0000-000000000197"
            ));

            OrderService service = context.getBean(OrderService.class);
            OrderRepository repository = context.getBean(OrderRepository.class);

            service.place(orderId);

            repository.changeStatus(orderId, "PACKED");
            OrderState current = repository.find(orderId).orElseThrow();

            System.out.println("after update: " + current.status()
                + " (version=" + current.version() + ")");
        }
    }

    public record OrderId(UUID value) {
        public OrderId {
            Objects.requireNonNull(value, "value");
        }
    }

    public record OrderPlaced(
        UUID eventId,
        OrderId orderId,
        long aggregateVersion
    ) {
        public OrderPlaced {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            if (aggregateVersion < 1) {
                throw new IllegalArgumentException("aggregateVersion < 1");
            }
        }
    }

    public record OrderState(OrderId id, String status, long version) {
    }

    public static final class OrderRepository {
        private final Map<OrderId, OrderState> orders =
            new ConcurrentHashMap<>();

        public void save(OrderState state) {
            orders.put(state.id(), state);
        }

        public Optional<OrderState> find(OrderId id) {
            return Optional.ofNullable(orders.get(id));
        }

        public void changeStatus(OrderId id, String newStatus) {
            orders.compute(id, (key, current) -> {
                if (current == null) {
                    throw new IllegalStateException("Order not found");
                }
                return new OrderState(id, newStatus, current.version() + 1);
            });
        }
    }

    public static final class OrderService {
        private final OrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public OrderService(OrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void place(OrderId orderId) {
            repository.save(new OrderState(orderId, "PLACED", 1L));
            publisher.publishEvent(new OrderPlaced(
                UUID.fromString("00000000-0000-0000-0000-000000000901"),
                orderId,
                1L
            ));
        }
    }

    public static final class OrderPlacedListener {
        private final OrderRepository repository;

        public OrderPlacedListener(OrderRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void handle(OrderPlaced event) {
            OrderState state =
                repository.find(event.orderId()).orElseThrow();

            System.out.println("received orderId: "
                + event.orderId().value());
            System.out.println("received eventId: " + event.eventId());
            System.out.println("event version: "
                + event.aggregateVersion());
            System.out.println("state at handling: " + state.status());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderRepository orderRepository() {
            return new OrderRepository();
        }

        @Bean
        public OrderService orderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new OrderService(repository, publisher);
        }

        @Bean
        public OrderPlacedListener orderPlacedListener(
                OrderRepository repository) {
            return new OrderPlacedListener(repository);
        }
    }
}
~~~

Chạy từ thư mục `business-id-event-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.BusinessIdEventDemo
~~~

Các dòng ứng dụng in ra, khi chạy đúng:

~~~text
received orderId: 00000000-0000-0000-0000-000000000197
received eventId: 00000000-0000-0000-0000-000000000901
event version: 1
state at handling: PLACED
after update: PACKED (version=2)
~~~

### Đọc kết quả cho đúng

- `OrderPlaced` là record payload bình thường; Spring Framework cho phép `ApplicationEventPublisher.publishEvent(Object)` nhận đối tượng không kế thừa `ApplicationEvent`. Spring đóng gói nó vào `PayloadApplicationEvent` và chuyển tới listener phù hợp.
- `OrderId` là value object bọc UUID. Hai order ID khác nhau không bị vô tình xem như cùng một domain type chỉ vì đều dùng `UUID`.
- `eventId` nhận dạng event cụ thể, **không bằng** `orderId`. Trong demo, hai UUID cố định để stdout xác định; hệ thống thật phải có chính sách sinh event ID duy nhất như `UUID.randomUUID()` hoặc ID do hệ thống cấp.
- Listener đồng bộ mặc định nên nó tra repository khi trạng thái vẫn là `PLACED`. Sau khi lời gọi publish hoàn tất, chương trình mới chuyển state thành `PACKED`/version 2.
- Event đã phát giữ `aggregateVersion=1`. Nếu listener xử lý trễ và tra repository lại, nó có thể đọc `PACKED`/version 2. Đây chính là lý do phải phân biệt **sự kiện đã xảy ra** với **trạng thái tại thời điểm tra cứu**.
- Repository trong bộ nhớ dùng các record immutable, `ConcurrentHashMap` và `compute` để minh họa, **không phải một transaction DB**. Ví dụ này không tuyên bố cung cấp atomicity hay khả năng replay sau crash.

Khi cần chứng minh commit/rollback thực tế, phải thay repository bằng JDBC/JPA/R2DBC cùng transaction manager và kiểm thử ở ranh giới DB. Không giả định những guarantee trong demo memory là guarantee của database.

## 7. ID được tạo ở đâu và khi nào event có thể phát?

### Trường hợp A: ID do ứng dụng tạo trước khi lưu

~~~java
UUID orderId = UUID.randomUUID();
Order order = new Order(orderId, ...);
repository.save(order);
publisher.publishEvent(new OrderPlacedEvent(UUID.randomUUID(), orderId));
~~~

Đoạn minh họa trên yêu cầu định nghĩa `Order` và `OrderPlacedEvent`. Ưu điểm: có ID ngay từ đầu, thuận tiện ghi outbox cùng transaction. Tuy nhiên, nếu lưu DB lỗi hoặc transaction rollback, event phát trực tiếp vẫn có thể đã được listener đồng bộ nhận. **Có ID sớm không có nghĩa record đã commit.**

### Trường hợp B: ID do database cấp

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    Order order = new Order(command);
    Order saved = orderRepository.save(order);

    // Chỉ publish khi ID đã thực sự được gán theo chiến lược ID của ORM.
    if (saved.getId() == null) {
        throw new IllegalStateException("Order ID was not assigned");
    }

    publisher.publishEvent(new OrderCreated(
        UUID.randomUUID(), saved.getId()
    ));
}
~~~

Đây là **mã tích hợp**, không phải chương trình độc lập. Với JPA ID generation, thời điểm nhận được ID phụ thuộc chiến lược (`IDENTITY`, sequence, UUID generator, v.v.). Khi cần tương tác DB thật, việc `save`, `flush` và commit có ngữ nghĩa khác nhau:

- **ID được gán:** application đã có khóa để định danh entity.
- **SQL đã flush:** ORM đã gửi SQL cần thiết xuống DB trong transaction; vẫn có thể rollback.
- **Transaction đã commit:** thay đổi của transaction đã được xác nhận hoàn tất thành công.

Không dùng `flush()` như một cách thay thế commit. Không phát event với `null` ID, và cũng không giả định mọi entity có ID ngay khi gọi constructor.

### Event khi xóa đối tượng

Với `OrderDeleted(orderId)`, listener thường **không thể đọc lại entity** sau commit vì record đã bị xóa. Nếu consumer cần thêm giá trị như tên, trạng thái trước xóa hoặc thông tin routing, event nên chứa một snapshot tối thiểu bất biến hoặc tombstone/metadata đủ để xử lý. Trường hợp này minh họa vì sao quy tắc “chỉ ID là đủ” phải tùy use case.

## 8. Transaction: phát event chứa ID trước commit chưa chắc đọc được ID ấy

Trong Spring, `@EventListener` thông thường được gọi đồng bộ khi dùng multicaster mặc định. Nếu service đang trong `@Transactional`, listener đồng bộ có thể chạy **ngay bên trong transaction đang mở**. Nếu listener dùng `@Async` hoặc multicaster executor, công việc có thể chạy trên thread khác, không có cùng transaction. Khi đó lệnh `SELECT` theo ID có thể không thấy hàng chưa commit hoặc gặp dữ liệu khác kỳ vọng.

Mẫu rủi ro:

~~~java
@Transactional
public void place(long orderId) {
    repository.insert(orderId);
    publisher.publishEvent(new OrderPlaced(orderId));
    // T1 chưa commit ở thời điểm publish.
}
~~~

Đây là mẫu kiến trúc minh họa. Nếu listener gửi message ra ngoài rồi transaction rollback, hệ thống ngoài có thể nhận được ID của record chưa hề tồn tại dưới trạng thái committed.

Khi chỉ muốn hậu xử lý **sau commit thành công**, cân nhắc:

~~~java
@Component
class SearchIndexerListener {
    private final CommittedOrderReader reader;

    SearchIndexerListener(CommittedOrderReader reader) {
        this.reader = reader;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        OrderSnapshot snapshot = reader.load(event.orderId());
        // Cập nhật chỉ mục bằng snapshot đã đọc sau commit.
    }
}
~~~

Ở đây `OrderPlaced`, `OrderSnapshot`, `CommittedOrderReader` là các kiểu ứng dụng giả định cần định nghĩa; đây không phải code chạy độc lập. **`@TransactionalEventListener` mặc định chỉ xử lý khi event phát bên trong transaction phù hợp**; không có transaction thì không chạy, trừ khi bật `fallbackExecution=true`. Một event không được đảm bảo “xử lý chính xác một lần” chỉ vì dùng `AFTER_COMMIT`.

### Đọc lại từ DB nên có transaction mới rõ ràng

Spring lưu ý trong `AFTER_COMMIT`, transaction đã commit nhưng resource có thể còn gắn với thread trước khi cleanup. Nếu consumer muốn SELECT bằng ranh giới transaction mới, có thể tách sang bean khác:

~~~java
@Service
public class CommittedOrderReader {
    private final OrderRepository repository;

    public CommittedOrderReader(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        readOnly = true
    )
    public OrderSnapshot load(OrderId id) {
        Order order = repository.findById(id).orElseThrow();
        return new OrderSnapshot(order.getId(), order.getStatus());
    }
}
~~~

Đây là code tích hợp; cần các import Spring transaction, `OrderRepository`, `Order`, `OrderId` và `OrderSnapshot` phù hợp với ứng dụng. `REQUIRES_NEW` thiết lập transaction độc lập qua transaction manager phù hợp, giúp phân biệt lần đọc này với persistence context cũ. Lời gọi phải đi qua **Spring proxy**: tự gọi `this.load(...)` trong cùng bean có thể khiến annotation không được áp dụng.

Cần nhớ: **AFTER_COMMIT không đồng nghĩa đọc đúng phiên bản event**. Nếu một transaction khác cập nhật ID đó ngay sau commit và trước SELECT, listener có thể thấy version mới hơn. Nếu đọc qua read replica, còn có thể thấy dữ liệu cũ do replication lag. ID chỉ chỉ ra *đối tượng nào*, không mang một snapshot lịch sử.

## 9. Version, concurrency và tính đúng đắn khi đọc lại

Giả sử chuỗi nghiệp vụ:

~~~text
T1: Order #42 = PLACED, version 1; commit
    +--> publish OrderPlaced(orderId=42, version=1)
T2: Order #42 = PAID, version 2; commit
Listener của OrderPlaced đọc DB theo ID #42
    +--> nhận version 2 thay vì version 1
~~~

Nếu nhiệm vụ của listener là “tạo projection về **trạng thái mới nhất**”, việc thấy version 2 có thể hợp lệ. Nếu nhiệm vụ là “gửi thông báo **đơn hàng vừa được đặt** với đúng chi tiết lúc đặt”, chỉ mang ID là chưa đủ.

Những chiến lược thường dùng:

| Mục tiêu của consumer | Thiết kế phù hợp |
|---|---|
| Lấy trạng thái mới nhất | ID + repository lookup, chấp nhận eventual consistency |
| Chỉ xử lý nếu đúng version | ID + aggregateVersion + so sánh version trước khi áp dụng |
| Diễn lại chính xác lịch sử thay đổi | Event chứa snapshot/delta bất biến đã được lưu bền |
| Khôi phục khi consumer offline | Outbox/broker kết hợp eventId và payload versioned |
| Đồng bộ nhiều update không đảo thứ tự | Sequence/version cùng phân vùng theo aggregate ID; thiết kế reorder/dedup |
| Xử lý delete không còn record | Tombstone event chứa ID và metadata tối thiểu |

### Quy tắc kiểm tra version

Ví dụ consumer projection lưu `lastAppliedVersion`. Nó nhận event version 11 khi DB/projection hiện ở version 10:

~~~text
incoming.version <= lastAppliedVersion  -> đã áp dụng hoặc event cũ; bỏ/kiểm tra
incoming.version == lastAppliedVersion+1 -> áp dụng bản kế tiếp
incoming.version > lastAppliedVersion+1  -> thiếu gap; đợi hoặc tái đồng bộ
~~~

Đây là **một chiến lược**, không phải quy tắc mặc định của Spring. Nó phù hợp khi version được cấp liên tục trong phạm vi aggregate và consumer xử lý một chuỗi event có contract đó. Nếu ứng dụng bỏ qua một số loại event hoặc version không tăng mỗi event, không thể yêu cầu luôn `+1`. Khi cùng một version có nhiều event hợp lệ, cần thêm sequence ở cấp event/aggregate.

### Vì sao không nên dùng timestamp để thay version?

Timestamp có thể trùng, lệch do clock giữa node hoặc được ghi ở thời điểm khác commit. `occurredAt` tốt cho audit/observability nhưng không phải cơ sở duy nhất để quyết định thứ tự tuyệt đối trên hệ thống phân tán.

## 10. eventId và idempotency: một entity có nhiều sự kiện hợp lệ

Một consumer nhận lại cùng `eventId` hai lần do retry. Nó phải có khả năng nhận diện duplicate và xử lý an toàn.

Ví dụ:

~~~text
OrderPaid(eventId=E1, orderId=O1, version=4)
OrderShipped(eventId=E2, orderId=O1, version=5)
Retry: OrderPaid(eventId=E1, orderId=O1, version=4)
~~~

Nếu dedupe theo `orderId=O1`, consumer sẽ bỏ nhầm `OrderShipped` hợp lệ. Nếu dedupe theo `eventId`, chỉ lần retry E1 bị nhận diện trùng.

Một mô hình lưu trạng thái:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Khi consumer xử lý event quan trọng trong database, có thể ghi dấu event và thực hiện side effect DB **trong cùng local transaction**; constraint unique giúp chỉ một lần được áp dụng ở consumer đó. Nếu side effect là gửi email, gọi API hoặc publish ra hệ thống khác, local DB transaction **không tự biến các side effect đó thành exactly-once**. Cần idempotency key ở API đích, outbox cho bước kế tiếp hoặc cơ chế retry có kiểm soát.

Cần phân biệt:

- **eventId** duy nhất cho một occurrence; retry cùng occurrence giữ nguyên eventId.
- **commandId** nhận dạng yêu cầu tạo thay đổi; có thể liên hệ eventId nhưng không nên tự giả định là một.
- **orderId** nhận dạng aggregate, được dùng cho lookup và partition/order.
- **messageId** do broker cấp có thể khác eventId; chuyển đổi broker không nên phá identity nghiệp vụ của event.

Đặt các trường định danh đúng tên trong payload để tránh xử lý trùng sai.

## 11. Trường hợp đa tenant và khóa ghép

Trong SaaS nhiều tenant, cùng một `orderId=42` có thể tồn tại ở tenant A và tenant B nếu ID chỉ unique theo tenant. Khi đó identity thật sự là cặp `(tenantId, orderId)`.

~~~java
public record OrderKey(UUID tenantId, long orderId) {
    public OrderKey {
        Objects.requireNonNull(tenantId, "tenantId");
        if (orderId <= 0) {
            throw new IllegalArgumentException("orderId must be positive");
        }
    }
}

public record OrderPlaced(UUID eventId, OrderKey orderKey) {}
~~~

Đây là các record minh họa với import `UUID` và `Objects`. Consumer **không được** tra `findById(orderId)` nếu kho dữ liệu yêu cầu tenant:

~~~java
repository.findByTenantIdAndId(
    event.orderKey().tenantId(),
    event.orderKey().orderId()
);
~~~

Việc có `tenantId` trong event **không tự xác thực quyền truy cập**. Khi event đi qua broker hoặc từ hệ thống ngoài, phải xác minh nguồn, ủy quyền và phạm vi tenant của consumer. Không tin mọi tenantId từ payload như đầu vào đã được kiểm chứng.

Khi dùng UUID duy nhất toàn cục cho order, tenantId vẫn có thể cần cho định tuyến, lọc dữ liệu, chính sách bảo mật và audit; thiết kế tùy contract hệ thống.

## 12. ID là value object: type safety và serialization

Thay vì truyền khắp code các `UUID` khó phân biệt, có thể tạo:

~~~java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "value");
    }
}

public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Java không cho truyền `CustomerId` vào phương thức nhận `OrderId`, giúp tránh nhầm ID khi refactor hoặc thêm đối tượng liên quan.

Nhưng value object cần có quy ước chuyển đổi:

- Với JPA: mapping bằng `AttributeConverter` hoặc cách mapping phù hợp; không mặc định Hibernate hiểu mọi record ID wrapper.
- Với JDBC: bind kiểu SQL thực tế (`UUID`/`VARCHAR`...), chuyển từ/đến `OrderId` ở repository layer.
- Với JSON: xác định contract rõ là chuỗi UUID thẳng (ví dụ `"f7..."`) hay object `{"value":"f7..."}`; cấu hình serializer/deserializer nhất quán.
- Với Kafka/AMQP/HTTP: giữ schema version, field names và độ dài/format phù hợp để không làm consumer cũ hỏng.

Nếu nhiều service dùng các ngôn ngữ khác nhau, không bắt buộc chia sẻ lớp Java `OrderId`; chỉ cần thống nhất **wire format** và ý nghĩa field. Domain type mạnh nên ở phía ứng dụng, còn public message schema phải bền vững qua phiên bản triển khai.

### UUID, ULID và cách tạo khóa

UUID ngẫu nhiên thường thuận tiện cho định danh trước DB insert. Các biến thể có tính thời gian (ví dụ UUIDv7), ULID hoặc sequence có trade-off về độ sắp xếp, lưu trữ và tính phân tán. Không chọn chỉ theo độ dài chuỗi; xem khả năng cấp phát, collision, database index, tính nhạy cảm của metadata và hỗ trợ thư viện/hệ thống.

**Đừng dùng ID tăng tuần tự như cơ chế phân quyền.** ID đoán được không cho phép truy cập record khác khi API có kiểm tra authorization đúng; nhưng hệ thống cũng không nên để lộ ID nhạy cảm nếu không cần thiết.

## 13. Snapshot tối thiểu hay truy vấn bằng ID?

Tùy business requirement, một trong ba hình thức có thể đúng:

### A. Chỉ ID

~~~java
public record CustomerAddressChanged(UUID customerId) {}
~~~

Ưu: payload nhỏ và loosely coupled. Nhược: consumer phải query; nếu địa chỉ thay đổi lần nữa trước khi consumer đọc, event không mô tả giá trị cũ/mới.

### B. ID + thuộc tính bất biến cần dùng

~~~java
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    long version,
    String currency,
    long amountMinorUnits
) {}
~~~

Ưu: consumer có thể xử lý theo đúng giá trị tại thời điểm event. Nhược: hợp đồng chứa thêm dữ liệu, cần quản lý schema, PII và bảo đảm snapshot được tạo đúng.

### C. ID + version rồi consumer tra state lịch sử

~~~java
public record OrderChanged(
    UUID eventId,
    UUID orderId,
    long version
) {}
~~~

Phù hợp khi repository có **historical snapshots/event store** hoặc API đọc theo version; nếu chỉ có một row chứa trạng thái mới nhất, `version=5` không tự giúp SELECT lại được trạng thái version 5 khi row đã thành version 6.

**Quy tắc chọn:** nếu downstream phải ra quyết định dựa trên những giá trị không thể thay đổi theo thời gian, hãy gửi snapshot/delta tối thiểu cần thiết hoặc có kho lịch sử phù hợp. Nếu mục tiêu là trigger “đã có cập nhật, hãy đồng bộ trạng thái mới nhất”, ID thường đủ.

## 14. Giao hàng bền vững: transactional outbox với aggregateId

`ApplicationEventPublisher` là cơ chế event trong JVM, không phải một durable queue. Đối với sự kiện qua microservices, cách thực tế thường là ghi outbox **cùng transaction** với thay đổi của aggregate.

Ví dụ lược đồ:

~~~sql
CREATE TABLE orders (
    id VARCHAR(36) PRIMARY KEY,
    state VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(36) PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(36) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload_json CLOB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Trong một transaction T1:

~~~text
1. Tạo/cập nhật orders(id, state, version)
2. Tạo eventId và payload bất biến
3. INSERT outbox_events(eventId, aggregateId, version, payload)
4. COMMIT T1
5. Một worker độc lập đọc outbox, phát message, đánh dấu published
6. Consumer dedupe theo eventId và xử lý idempotent
~~~

Vì orders và outbox cùng DB/transaction, rollback T1 sẽ rollback cả hai. Nếu tiến trình chết sau commit nhưng trước publish, outbox record vẫn còn cho lần xử lý sau. Tuy nhiên, nếu worker publish thành công rồi chết trước khi đánh dấu, nó có thể gửi lại message: **cần at-least-once handling và idempotency**; outbox không tự cho exactly-once end-to-end.

Nhận dạng chính:

- `event_id`: PK của record event; thích hợp dedupe.
- `aggregate_id`: khoá đối tượng, dùng cho partition/định tuyến.
- `aggregate_version`: kiểm soát thứ tự/version nếu hệ thống duy trì hợp đồng tương ứng.
- `event_type`/`schemaVersion`: phân loại và tương thích message.
- `payload_json`: dữ kiện tối thiểu để consumer không phụ thuộc trực tiếp vào database publisher.

Nếu luồng outbox dùng CDC, broker partition key thường là aggregate ID để tăng khả năng giữ thứ tự cho cùng một đối tượng, nhưng **không có bảo đảm tự động rằng toàn bộ pipeline end-to-end luôn xử lý đúng thứ tự**; consumer vẫn cần quản lý retry, partition, fan-out và version.

## 15. Thiết kế event cho module nội bộ và tích hợp bên ngoài

Event nội bộ Java và integration event không nhất thiết dùng cùng một class:

~~~text
OrderService
  |
  | domain event: OrderPaid(orderId, eventId, version)
  v
In-process @EventListener
  |
  | chuyển sang integration event schema v2
  v
Outbox / Broker
  |
  | JSON/Avro/Protobuf gồm ID, type, version, occurredAt
  v
Service khác
~~~

Một mapper riêng có thể chuyển `OrderId` type-safe thành UUID/string theo wire schema. Việc tách lớp sự kiện nội bộ và sự kiện tích hợp giúp domain không phải luôn phơi bày entity model hoặc các thay đổi schema nội bộ.

Các thuộc tính nên định nghĩa trong event contract:

| Thuộc tính | Câu hỏi cần trả lời |
|---|---|
| Chủ sở hữu | Module nào có quyền định nghĩa meaning của orderId? |
| Uniqueness | ID unique toàn hệ thống, theo tenant hay theo aggregate type? |
| Lifetime | ID có thể tái sử dụng sau xóa không? |
| Format | UUID chuẩn, số nguyên, string prefix, base64…? |
| Serialization | String hay number? Có mất precision khi qua JS? |
| Versioning | Aggregate version tăng khi nào và với quy tắc nào? |
| Deduplication | Consumer dùng eventId hay composite key nào? |
| Authorization | Consumer được phép đọc ID này không? |
| Missing state | Nếu entity đã xóa hoặc chưa replicate, phải retry/bỏ qua/tombstone? |

Đặc biệt khi qua JavaScript, số nguyên 64-bit lớn hơn `Number.MAX_SAFE_INTEGER` có thể mất độ chính xác nếu serialize thành JSON number rồi client parse theo `Number`. Với ID kiểu `long` dùng ở boundary tương thích JS, cân nhắc biểu diễn chuỗi và công bố hợp đồng rõ ràng.

## 16. Kiểm thử thiết kế payload chứa ID

Một bộ test hữu ích cần chứng minh các thuộc tính sau.

### Test 1 — Event không chia sẻ entity mutable

Publisher phát `OrderPlaced(orderId, version=1)`, sau đó repository đổi trạng thái sang version 2. Assert event vẫn giữ version 1; listener xử lý muộn phải có chính sách rõ về cách đọc.

### Test 2 — Đúng ID và đúng loại

Dùng `OrderId` và `CustomerId` type-safe, hoặc test bằng request ID hợp lệ để xác nhận consumer lookup đúng aggregate. Không dùng `String id` mơ hồ trong các API có nhiều loại ID.

### Test 3 — Rollback không kích hoạt hậu xử lý AFTER_COMMIT

Trong test Spring transaction thực sự, phát event ở T1 rồi rollback. Listener `@TransactionalEventListener(AFTER_COMMIT)` không chạy. Thử nhánh commit và xác nhận event được xử lý khi transaction hoàn thành.

### Test 4 — Event trùng

Gửi hai bản sao cùng `eventId`. Consumer idempotent chỉ áp dụng side effect một lần; một event khác với **cùng orderId nhưng eventId khác** vẫn được xử lý.

### Test 5 — Entity thiếu hoặc bị xóa

Phát event chứa ID đã bị xóa; consumer không nên chỉ dùng `orElseThrow()` rồi loop retry vô hạn. Xác định cách phân biệt lỗi tạm thời (replication lag) với object thực sự không còn tồn tại (tombstone/terminal state).

### Test 6 — Concurrency và version

Cho event version 5 đến sau version 6. Consumer không được vô tình ghi đè projection mới bằng dữ liệu cũ. Kiểm thử cả trường hợp hai event hợp lệ cùng aggregate nhưng thứ tự đến đảo.

### Test 7 — Format JSON và tenant

Round-trip payload qua serializer; kiểm tra ID không bị đổi kiểu, cắt bớt chữ số, mất tenantId hoặc lẫn giá trị ID giữa hai loại đối tượng. Ở API ngoài, kiểm tra quyền truy cập thay vì chỉ tin ID.

Với xử lý async, dùng `CountDownLatch` hoặc công cụ await condition có timeout; không chỉ gọi `publishEvent` rồi assert ngay và giả định listener đã hoàn tất.

## 17. Các lỗi phổ biến và hướng xử lý

| Triệu chứng / sai lầm | Nguyên nhân có thể | Hướng sửa |
|---|---|---|
| Event có `orderId=null` | ID do DB cấp chưa được gán, publish quá sớm | Kiểm tra chiến lược ID và thời điểm save/flush |
| Consumer đọc không thấy record | Publish trước commit; async hoặc replica lag | Dùng transaction phase phù hợp, retry có giới hạn, đọc primary khi cần |
| Consumer đọc trạng thái khác lúc event | Record đã cập nhật sau event | Mang version/snapshot hoặc truy vấn lịch sử |
| `LazyInitializationException` | Payload mang entity/proxy lazy qua transaction | Chuyển sang ID + DTO bất biến, fetch trong transaction của consumer |
| Bỏ nhầm event hợp lệ | Dedupe bằng aggregateId thay vì eventId | Lưu processed eventId theo consumer |
| Đổi order number làm mất liên kết | Mã hiển thị bị dùng làm primary identity | Dùng ID ổn định và giữ business code riêng |
| ID khách hàng bị dùng như ID đơn | Các API cùng nhận UUID/String | Dùng value objects hoặc field rõ tên |
| Lẫn đơn của tenant khác | ID chỉ unique theo tenant, query thiếu tenantId | Định nghĩa OrderKey; query và authorize theo tenant |
| Event sau khi xóa không thể lookup | Đối tượng đã biến mất | Event tombstone/snapshot tối thiểu hoặc chiến lược not-found |
| Duplicate side effect khi retry | Không lưu eventId/idempotency key | DB uniqueness + idempotent side effects |
| Listener chậm làm publisher chậm | `@EventListener` mặc định đồng bộ | Tách xử lý async/queue phù hợp; hiểu lỗi và transaction |
| Consumer sau crash mất sự kiện | Application events không durable | Outbox/broker/retry và trạng thái xử lý |
| JSON làm tròn long ID | Consumer dùng JS number cho số lớn | Serialize ID dạng chuỗi, quy định schema |
| Lộ đối tượng của người khác | Biết ID nhưng thiếu authorization | Kiểm tra quyền tại mỗi boundary và consumer |

## 18. Checklist thiết kế nhanh

Trước khi chốt một event có entity ID, hỏi:

1. **Đối tượng gì?** `orderId`, `customerId` hay khóa ghép?
2. **Ổn định và duy nhất ở đâu?** Trong toàn hệ thống hay trong một tenant?
3. **ID sẵn sàng lúc nào?** Có trước khi lưu, sau insert/flush hay chỉ sau một bước nghiệp vụ?
4. **Consumer cần state gì?** Trạng thái mới nhất, trạng thái lúc event, hay chỉ biết sự kiện đã xảy ra?
5. **Có eventId riêng chưa?** Retry và dedupe có nhận dạng đúng một lần phát không?
6. **Có version không?** Nếu concurrency quan trọng, version có contract rõ không?
7. **Khi rollback thì sao?** Listener phải chạy trước/ sau commit, hay event phải có outbox?
8. **Entity có thể bị xóa trước khi đọc không?** Có tombstone/snapshot hoặc chính sách not-found chưa?
9. **Có nhiều tenant không?** ID và tra cứu đã gồm tenant và authorization chưa?
10. **Có chuyển ra ngoài JVM không?** Schema, serialization, privacy, idempotency, durability đã được xử lý chưa?

### Tổng kết

Trong Spring Application Events, payload mang **ID định danh đối tượng nghiệp vụ** là một phương án quan trọng để giảm coupling giữa publisher và listener. Nó giữ event nhỏ, tránh tham chiếu tới entity mutable/persistence context và cho phép consumer lấy dữ liệu bằng repository hoặc API của chính mình.

Tuy nhiên, cần phân biệt **aggregateId** (“đối tượng nào”), **eventId** (“lần sự kiện nào”), **version** (“trạng thái thứ mấy”) và **snapshot** (“giá trị khi sự kiện xảy ra”). Chỉ có ID không chứng minh dữ liệu đã commit, không giữ trạng thái lịch sử và không đảm bảo delivery. Kết hợp đúng transaction phase, dữ liệu bất biến, idempotency và outbox khi yêu cầu nghiệp vụ đòi hỏi.

### Tài liệu tham khảo chính thức

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html) — `ApplicationEventPublisher`, `@EventListener`, payload events và dispatch.
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — `@TransactionalEventListener` và `AFTER_COMMIT`.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html) — publication contract.
- [Spring Data JPA Reference — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/repositories/core-domain-events.html) — `@DomainEvents` và event từ aggregate.
