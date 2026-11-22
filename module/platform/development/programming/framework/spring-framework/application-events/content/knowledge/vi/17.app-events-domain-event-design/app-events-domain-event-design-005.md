# Aggregate và domain event trong Spring Application Events

## 1. Bài toán: thay đổi nghiệp vụ và thông báo điều đã xảy ra

Giả sử hệ thống bán hàng có đơn đặt hàng. Khi thanh toán thành công, trạng thái đơn hàng chuyển từ `PENDING` sang `PAID`; các chức năng khác cần biết để cập nhật báo cáo, gửi thông báo hoặc kích hoạt quy trình giao hàng. Nếu đặt mọi hành động này trong cùng một phương thức thanh toán, mã nguồn nhanh chóng phụ thuộc chặt vào email, kho, vận chuyển và nhiều dịch vụ khác.

**Aggregate** trong Domain-Driven Design (DDD) xác định ranh giới chịu trách nhiệm bảo vệ quy tắc nghiệp vụ. **Domain event** diễn tả một sự kiện có ý nghĩa với nghiệp vụ, thường là một sự thật đã xảy ra trong một aggregate, ví dụ `OrderPaid`. Spring `ApplicationEventPublisher` cung cấp cơ chế truyền thông báo đó tới những thành phần quan tâm **bên trong ứng dụng**.

Ba khái niệm có vai trò riêng:

1. **Aggregate:** quyết định hành động có hợp lệ hay không và cập nhật trạng thái theo các bất biến nghiệp vụ (*invariants*).
2. **Domain event:** ghi nhận kết quả nghiệp vụ đã đạt được, không yêu cầu bên nhận thực hiện một lệnh cụ thể.
3. **Application event mechanism:** chuyển đối tượng event đến listener; đây là cơ chế kỹ thuật của Spring, không tự tạo transaction, hàng đợi bền vững hoặc bảo đảm delivery.

Ví dụ: `Order.pay()` xác minh đơn chưa thanh toán, cập nhật trạng thái rồi ghi nhận `OrderPaid`. Một application service lưu aggregate và dùng Spring phát event. Một listener khác xử lý thông báo mà không phải thay đổi mã `Order.pay()` mỗi lần có thêm chức năng phụ.

## 2. Aggregate là gì và vì sao có ranh giới?

Trong DDD, một aggregate là một **nhóm entity và value object được quản lý như một đơn vị nhất quán**; một entity trong nhóm đóng vai trò **aggregate root**. Các thành phần bên ngoài tương tác với aggregate thông qua root, thay vì tự ý thay đổi chi tiết nội bộ.

Ví dụ aggregate `Order` có thể chứa:

- `Order` (root): mã đơn, trạng thái, tổng tiền và các thao tác `addItem()`, `confirm()`, `pay()`, `cancel()`.
- `OrderLine`: các dòng hàng gắn với đơn; thay đổi số lượng cần đi qua root để giữ tổng tiền và quy tắc hợp lệ.
- `Money`, `Address`: value object thể hiện giá trị, có thể là bất biến.

Các **invariants** tiêu biểu: một đơn đã hủy không được thanh toán; không tạo hai lần thanh toán cho cùng chuyển trạng thái; tổng tiền không âm; không được giao đơn chưa thanh toán (tùy quy định kinh doanh).

### Ranh giới nhất quán

Thông thường, những quy tắc phải đúng ngay khi thao tác hoàn tất được kiểm tra **bên trong một aggregate**. Các aggregate khác như `Inventory`, `Shipment` hay `CustomerLoyalty` có thể phản ứng với domain event và đạt nhất quán sau đó. Không mặc định mọi aggregate cần nằm trong một transaction duy nhất.

Điểm cần nhớ: **aggregate không đồng nghĩa với một hàng trong database**, và cũng không phải tất cả entity thuộc một bounded context. Một aggregate có thể gồm nhiều bảng; kích thước ranh giới được chọn theo invariants, xung đột ghi và nhu cầu nhất quán.

## 3. Domain event nên mô tả điều gì?

Một domain event tốt thể hiện **sự thật trong quá khứ**, được đặt tên theo ngôn ngữ nghiệp vụ:

| Loại thông điệp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Command | `PayOrder` | Yêu cầu một hành động; có thể bị từ chối |
| Domain event | `OrderPaid` | Đơn hàng đã được xác nhận thanh toán theo quy tắc nghiệp vụ |
| Domain event | `OrderCancelled` | Đơn hàng đã bị hủy |
| Integration event | `order.paid.v1` | Thông điệp công bố cho hệ thống khác với hợp đồng schema và delivery riêng |

Một event thường chỉ mang **dữ liệu cần thiết để người nhận hiểu sự việc**: `eventId` để phát hiện lặp, `aggregateId`, mã giao dịch hoặc mã nghiệp vụ, thời gian xảy ra, phiên bản hay các giá trị bất biến. Không nhất thiết phải copy toàn bộ entity.

Ví dụ Java 17+:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        String orderId,
        long amountCents,
        Instant occurredAt) {
}
```

Đây là **định nghĩa dữ liệu minh họa**, chưa phải một chương trình độc lập. Java `record` giúp cố định các field ở mức nông (*shallow immutability*); nếu record chứa `List` hoặc object mutable thì phải sao chép phòng vệ khi cần. Khi tạo event thực tế, cung cấp dữ liệu đúng thời điểm quy tắc nghiệp vụ xác nhận, không yêu cầu listener truy cập entity đang mutable hoặc lazy-loading proxy.

**Domain event không bắt buộc kế thừa `ApplicationEvent`.** Spring cho phép `publishEvent(Object)` nhận POJO/record; khi cần, Spring sẽ dùng wrapper nội bộ. Không nên đặt annotation hay API của Spring vào mọi class domain nếu có thể giữ domain thuần Java.

## 4. Ai tạo và ai phát domain event?

Cách tổ chức phổ biến theo ranh giới:

```text
HTTP/API/Job
    |
    v
Application Service: PayOrder
    |
    v
Repository.load(orderId)
    |
    v
Order Aggregate Root
  - kiểm tra invariant
  - đổi trạng thái PENDING -> PAID
  - ghi nhận OrderPaid
    |
    v
Repository.save(order)
    |
    v
Phát các event đã ghi nhận
    |
    v
Spring ApplicationEventPublisher
    |
    +--> Listener cập nhật projection
    +--> Listener tạo yêu cầu thông báo
    +--> Adapter chuẩn bị integration/outbox
```

**Trách nhiệm của aggregate:** phát hiện và mô tả sự thay đổi hợp lệ. Aggregate không cần biết listener cụ thể và không nên tự gọi email client, HTTP API hay `ApplicationEventPublisher` của Spring trong phương thức domain.

**Trách nhiệm của application service / infrastructure:** tải aggregate, thiết lập transaction khi có DB, lưu thay đổi và điều phối publication. Khi dùng Spring Data, hạ tầng repository cũng có thể tự lấy domain events từ aggregate root để publish.

**Trách nhiệm của listener:** thực hiện hậu quả hoặc projection tách biệt, có quản lý lỗi và tính lặp. Listener không nên tự ý thay đổi lại invariants của aggregate nguồn dựa trên object entity được truyền trực tiếp.

Chỉ đổi trạng thái `order.paid = true` rồi tự publish event mà không qua method giữ invariant là một dấu hiệu thiết kế cần sửa: bên ngoài đã có thể phá ranh giới aggregate.

## 5. Ví dụ chạy được: aggregate thuần Java + Spring ApplicationEventPublisher

Ví dụ sử dụng **Spring Boot 3.x, Java 17+**, không kết nối DB để quan sát rõ ranh giới domain và thứ tự xử lý. Repository trong bộ nhớ chỉ dùng để mô phỏng bước lưu; nó **không cung cấp transaction, khóa ghi hoặc lưu bền**.

Yêu cầu nghiệp vụ:

- Một đơn chưa thanh toán, tổng tiền dương, có thể chuyển thành `PAID`.
- Lần thanh toán thứ hai không tạo thêm `OrderPaid`.
- Aggregate ghi nhận event; service lưu và publish; listener chỉ in thông báo.
- Mẫu output cố định để kiểm chứng event chỉ xuất hiện một lần.

### Cấu trúc file

```text
aggregate-domain-event-demo/
├── pom.xml
└── src/main/java/example/events/AggregateEventDemo.java
```

### pom.xml

Ví dụ cố định Spring Boot 3.3.13 và JDK 17:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>aggregate-domain-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### AggregateEventDemo.java

```java
package example.events;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class AggregateEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(AggregateEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner đã chạy trong startup; context sẽ đóng khi ra khỏi try.
        }
    }

    // Thông điệp nghiệp vụ bất biến, không cần extends ApplicationEvent.
    public record OrderPaid(String orderId, long amountCents) {
    }

    // Aggregate root thuần Java: chỉ root quyết định có được thanh toán.
    public static final class Order {
        private final String id;
        private final long amountCents;
        private boolean paid;
        private final List<Object> pendingEvents = new ArrayList<>();

        public Order(String id, long amountCents) {
            if (id == null || id.isBlank() || amountCents <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            this.id = id;
            this.amountCents = amountCents;
        }

        public String id() {
            return id;
        }

        public boolean pay() {
            if (paid) {
                return false; // Lặp thao tác không phát event lần hai.
            }
            paid = true;
            pendingEvents.add(new OrderPaid(id, amountCents));
            return true;
        }

        public List<Object> drainEvents() {
            List<Object> result = List.copyOf(pendingEvents);
            pendingEvents.clear();
            return result;
        }
    }

    // Chỉ minh họa persistence; không tương đương JPA/database.
    public static final class InMemoryOrderRepository {
        private final Map<String, Order> orders = new ConcurrentHashMap<>();

        public void save(Order order) {
            orders.put(order.id(), order);
        }

        public Order getRequired(String id) {
            Order order = orders.get(id);
            if (order == null) {
                throw new IllegalArgumentException("Order not found: " + id);
            }
            return order;
        }
    }

    // Application service biết repository và Spring publisher;
    // domain aggregate không phụ thuộc framework.
    public static final class PayOrderService {
        private final InMemoryOrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public PayOrderService(InMemoryOrderRepository repository,
                               ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public boolean pay(String id) {
            Order order = repository.getRequired(id);
            if (!order.pay()) {
                return false;
            }
            repository.save(order);
            for (Object event : order.drainEvents()) {
                publisher.publishEvent(event);
            }
            return true;
        }
    }

    public static final class OrderPaidListener {
        @EventListener
        public void on(OrderPaid event) {
            System.out.printf("EVENT order=%s amount=%d%n",
                    event.orderId(), event.amountCents());
        }
    }

    @Bean
    InMemoryOrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    PayOrderService payOrderService(
            InMemoryOrderRepository repository,
            ApplicationEventPublisher publisher) {
        return new PayOrderService(repository, publisher);
    }

    @Bean
    OrderPaidListener orderPaidListener() {
        return new OrderPaidListener();
    }

    @Bean
    CommandLineRunner demo(InMemoryOrderRepository repository,
                           PayOrderService service) {
        return args -> {
            repository.save(new Order("ORD-42", 12500));
            System.out.println("FIRST pay=" + service.pay("ORD-42"));
            System.out.println("SECOND pay=" + service.pay("ORD-42"));
        };
    }
}
```

### Chạy và quan sát

Trong thư mục chứa `pom.xml`:

```bash
mvn -q package
java -jar target/aggregate-domain-event-demo-1.0.0.jar
```

Ngoài log riêng của Spring Boot, ba dòng **do mã demo in** là:

```text
EVENT order=ORD-42 amount=12500
FIRST pay=true
SECOND pay=false
```

Tại sao `EVENT` xuất hiện trước `FIRST`? Mặc định, Spring dùng `SimpleApplicationEventMulticaster` để gọi `@EventListener` đồng bộ trong luồng `publishEvent(...)`. Lời gọi `service.pay(...)` chưa trả về cho runner cho đến khi listener chạy xong. Lần gọi thứ hai thấy `paid == true` nên trả về `false` và không tạo event mới.

**Ranh giới của ví dụ:** `InMemoryOrderRepository` giữ reference tới `Order`, không có transaction DB, optimistic locking, concurrency control, rollback hoặc outbox. `drainEvents()` xóa event khỏi danh sách ngay trước khi publish; nếu tiến trình chết hoặc listener ném lỗi, event có thể mất. Cần chọn cơ chế khác khi phải bảo đảm không mất tác vụ.

## 6. Bất biến nghiệp vụ phải ở aggregate, không nằm trong listener

Một thiết kế dễ sai:

```java
// Anti-pattern: application service sửa trực tiếp trạng thái,
// còn listener mới quyết định có được thanh toán hay không.
order.setPaid(true);
publisher.publishEvent(new OrderPaid(order.getId(), total));
```

Đoạn trên chỉ minh họa **hướng thiết kế sai**, không thuộc demo ở mục 5. Nếu nhiều luồng hoặc nhiều service có thể gọi setter, rule "đơn đã hủy không được thanh toán" bị bỏ qua ở một số đường đi. Listener là nơi phản ứng, không phải hàng rào duy nhất bảo vệ trạng thái gốc.

Hướng phù hợp hơn:

```java
public boolean pay() {
    if (status == Status.CANCELLED) {
        throw new IllegalStateException("Cancelled order cannot be paid");
    }
    if (status == Status.PAID) {
        return false;
    }
    status = Status.PAID;
    registerDomainEvent(new OrderPaid(orderId, amountCents));
    return true;
}
```

Đây là **pseudocode Java về phương thức domain**: giả định `Status`, `orderId`, `amountCents` và `registerDomainEvent(...)` đã được định nghĩa trong aggregate. Logic chính là **kiểm tra invariant → cập nhật trạng thái → ghi nhận sự kiện**. Việc lưu và phát là bước khác, do service hoặc repository adapter quản lý.

Sự kiện thường được tạo **sau khi quyết định nghiệp vụ có hiệu lực trong bộ nhớ**, nhưng **sự thay đổi chỉ trở thành bền vững khi transaction lưu trữ commit thành công**. Vì vậy cần phân biệt "aggregate đã chuyển trạng thái" với "DB đã commit" khi đặt listener có tác dụng phụ.

## 7. Spring Data: @DomainEvents và @AfterDomainEventPublication

Spring Data Commons cung cấp cơ chế publication domain events từ aggregate root qua repository. Một root có thể khai báo:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

public class OrderAggregate {
    private final List<Object> events = new ArrayList<>();

    public void markPaid(String orderId, long amountCents) {
        // Sau khi kiểm tra invariant và cập nhật trạng thái:
        events.add(new OrderPaid(orderId, amountCents));
    }

    @DomainEvents
    Collection<Object> domainEvents() {
        return List.copyOf(events);
    }

    @AfterDomainEventPublication
    void clearDomainEvents() {
        events.clear();
    }
}
```

Đây là **mảnh cấu trúc minh họa**, không phải một JPA entity đầy đủ và không dùng trực tiếp trong demo mục 5. Một method `@DomainEvents` không có tham số, trả về một đối tượng event hoặc collection; sau khi hạ tầng phát event, method `@AfterDomainEventPublication` có thể xóa các event đã ghi nhận.

Spring Data hỗ trợ truy xuất các event khi những phương thức repository phù hợp được gọi với instance của root như `save(...)`, `saveAll(...)` và một số dạng `delete(...)`. **Không giả định `deleteById(...)` luôn phát domain events**: phương thức này có thể chỉ thực thi lệnh xóa theo ID mà không truy cập instance aggregate.

Điểm quan trọng: gọi `aggregate.markPaid(...)` **không tự động** publish event chỉ vì có `@DomainEvents`. Cần đi qua phương thức repository có hỗ trợ publication. Tương tự, `@AfterDomainEventPublication` chỉ phản ánh event đã được chuyển cho hạ tầng publication, **không chứng minh database đã commit hoặc mọi listener đã xử lý thành công**.

### AbstractAggregateRoot giảm mã boilerplate

Spring Data Commons còn có `AbstractAggregateRoot<A>`. Class này cung cấp sẵn danh sách event và các phương thức `registerEvent(...)`, `andEvent(...)`, `domainEvents()`, `clearDomainEvents()`.

```java
import org.springframework.data.domain.AbstractAggregateRoot;

public class OrderEntity extends AbstractAggregateRoot<OrderEntity> {

    public void markPaid(String orderId, long amountCents) {
        // Kiểm tra invariant và cập nhật trạng thái ở đây.
        registerEvent(new OrderPaid(orderId, amountCents));
    }
}
```

Đây là **đoạn minh họa việc kế thừa**, giả định `OrderPaid` đã được định nghĩa. Trong ứng dụng JPA thực tế, entity còn cần `@Entity`, khóa `@Id`, mapping thích hợp và repository. Không cần viết lại `@DomainEvents` / `@AfterDomainEventPublication` khi dùng hành vi sẵn có của `AbstractAggregateRoot`.

Ưu điểm: ít công việc quản lý event list. Đổi lại, lớp domain phụ thuộc vào Spring Data. Nếu muốn domain hoàn toàn độc lập framework, giữ queue event thuần Java và dùng adapter/application service để publish như ví dụ trước.

## 8. Thời điểm publish, transaction và AFTER_COMMIT

Có ba điểm khác nhau:

1. Aggregate tạo domain event khi thực hiện chuyển trạng thái nghiệp vụ.
2. Spring application event được **publish** khi application service/repository gọi cơ chế phát.
3. Transaction database **commit** ở cuối unit of work, nếu thực sự có transaction.

Các mốc này có thể không trùng nhau. Ví dụ một application service dùng `@Transactional`, thay đổi aggregate rồi gọi `repository.save(order)`. Spring Data có thể publish event trong luồng gọi repository, **trước khi transaction bên ngoài commit**.

Nếu listener gắn `@EventListener` mặc định và thực hiện side effect ngay (gửi email, gọi API), side effect có thể xảy ra **trước khi DB commit**; nếu transaction sau đó rollback, email đã gửi vẫn tồn tại.

Đối với phản ứng chỉ hợp lệ khi đã commit, Spring Framework hỗ trợ:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AfterCommitOrderListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPaid(OrderPaid event) {
        // Gọi một adapter thông báo/đồng bộ sau commit.
        // Cần retry/idempotency nếu không được phép mất event.
    }
}
```

Đây là **lớp minh họa**, cần phụ thuộc transaction của Spring, một transaction đang hoạt động khi event được publish, và kiểu `OrderPaid` tương ứng. Không thả trực tiếp đoạn này vào demo in-memory ở mục 5: demo đó **không mở transaction**, nên listener `@TransactionalEventListener` mặc định sẽ **không được gọi**.

Các pha hỗ trợ: `BEFORE_COMMIT`, `AFTER_COMMIT` (mặc định), `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Nếu không có transaction đang chạy, listener mặc định **bỏ qua event**; có thể đặt `fallbackExecution = true` nhưng phải chấp nhận hành vi không có commit để chờ.

**Cảnh báo về thao tác ghi DB sau commit:** Tại `AFTER_COMMIT`, một số resource giao dịch có thể còn gắn với thread. Nếu listener cần thực hiện **transaction ghi DB mới**, hãy gọi sang một service khác có `@Transactional(propagation = Propagation.REQUIRES_NEW)` (qua Spring proxy) hoặc dùng `TransactionTemplate` tương ứng. Chỉ thêm `@Transactional` mặc định vào method listener không bảo đảm lần ghi được commit trong một transaction mới.

## 9. Tại sao AFTER_COMMIT vẫn chưa là bảo đảm gửi sự kiện?

`@TransactionalEventListener(AFTER_COMMIT)` tránh kích hoạt tác dụng phụ khi transaction rollback, nhưng **không đảm bảo bền vững** cho event sau commit. Một tiến trình có thể chết ngay sau khi DB commit, trước khi listener gửi email hoặc truyền thông điệp. Khi đó thay đổi đơn hàng đã lưu nhưng event vẫn chưa đi ra ngoài.

Đối với sự kiện quan trọng cần được chuyển đáng tin cậy, cân nhắc **Transactional Outbox**:

```text
Transaction database:
  UPDATE orders SET status='PAID' WHERE ...
  INSERT INTO outbox(event_id, type, payload, status)
  COMMIT
            |
            v
Worker / CDC đọc outbox đã commit
            |
            v
Message broker / integration adapter
            |
            v
Consumer có idempotency, retry, DLQ
```

Khi bản ghi thay đổi trạng thái và bản ghi outbox được lưu **cùng một transaction**, commit thành công đảm bảo cả hai xuất hiện cùng nhau. Worker gửi sau đó có thể retry khi lỗi. Vì retry, delivery thường cần tư duy *at-least-once*: consumer phải xử lý idempotent bằng `eventId` hoặc một khóa nghiệp vụ đủ ổn định.

**Không nhầm lẫn:**

- `@EventListener`: dispatch trong ứng dụng, mặc định đồng bộ.
- `@Async @EventListener`: dispatch công việc qua executor trong bộ nhớ, không tự bền vững.
- `@TransactionalEventListener(AFTER_COMMIT)`: gắn callback với phase commit của transaction, không lưu bền event.
- **Outbox + broker/worker:** mô hình lưu và chuyển event có thể khôi phục sau crash, đổi lại chi phí vận hành, độ trễ và xử lý lặp.

## 10. Domain event và integration event có giống nhau không?

Không bắt buộc.

**Domain event** mô tả điều đã xảy ra trong domain model; đối tượng nhận có thể nằm trong cùng bounded context. Nó có thể mang dữ liệu thuận tiện cho các xử lý nội bộ nhưng không nên bị ràng buộc vào schema mạng công khai.

**Integration event** là hợp đồng giữa các ứng dụng/bounded context. Nó thường cần:

- Tên loại event ổn định và phiên bản schema, ví dụ `OrderPaidV1`.
- `eventId`, timestamp, aggregate ID và dữ liệu cần thiết theo hợp đồng.
- Quy tắc tương thích ngược, retry, deduplication và theo dõi consumer.
- Quy tắc bảo mật, giảm dữ liệu cá nhân, che hoặc mã hóa thông tin nhạy cảm.

Một adapter có thể chuyển `OrderPaid` nội bộ thành `order.paid.v1` gửi qua outbox. Không để thay đổi đối tượng Java nội bộ buộc mọi consumer bên ngoài nâng cấp tức thì.

Vì event là **sự thật quá khứ**, listener không nên giả định luôn có thể hủy nghiệp vụ gốc. Nếu quy trình cần hoàn tác, thiết kế một command và một chuyển trạng thái bù trừ riêng (ví dụ hoàn tiền), tùy domain.

## 11. Những lỗi thiết kế phổ biến

**1. Dùng domain event để thay invariant của aggregate.** Ví dụ listener kiểm tra hạn mức thanh toán sau khi root đã ghi nhận trả tiền. Quy tắc bắt buộc ngay phải nằm ở nơi ra quyết định nghiệp vụ, thường trong aggregate hoặc domain service phù hợp.

**2. Publish event ngay trong entity bằng ApplicationEventPublisher.** Điều này ghép domain vào Spring container, gây khó kiểm thử và khó biết liệu entity đã được lưu thành công. Hãy để aggregate ghi nhận event, adapter/service quản lý phát.

**3. Phát event khi mới nhận command.** Tên `OrderPaid` phải chỉ xuất hiện sau khi nghiệp vụ xác nhận trạng thái đã chuyển, không phải ngay lúc có `PayOrder` request.

**4. Không xét transaction và rollback.** `@EventListener` đồng bộ có thể chạy trước commit. Dùng phase listener phù hợp hoặc outbox nếu side effect phụ thuộc commit.

**5. Coi Spring Data @DomainEvents là tự động gửi bền vững.** Cơ chế này phát event khi repository thao tác với aggregate root; nó không thay thế transaction commit, message broker hay outbox.

**6. Phát trùng khi save hoặc retry.** Tránh đăng ký lại cùng event trên mỗi lần `save(...)` nếu trạng thái không thay đổi. Dùng idempotent command, giữ event ID, xử lý dedup khi consumer có thể nhận lại.

**7. Gửi nguyên JPA entity cho listener.** Có thể gặp lazy-loading, stale/mutable state, tham chiếu vòng hoặc lộ dữ liệu. Ưu tiên immutable snapshot dữ liệu cần thiết hoặc aggregate ID kèm quy tắc truy vấn rõ ràng.

**8. Một listener sửa trực tiếp nhiều aggregate trong luồng async rồi cho rằng nhất quán ngay.** Mỗi bước cần transaction/điều phối tương ứng, có thể tồn tại độ trễ và lỗi cục bộ; cân nhắc workflow/saga hoặc mô hình nhất quán khác.

**9. Đánh đồng "publish xong" với "listener thành công".** Một listener bất đồng bộ có thể fail sau khi publisher trả về. Thiết lập metrics cho event created, published, processed, failed, retried và DLQ riêng.

**10. Coi aggregate bằng một bảng hoặc gom cả hệ thống thành một aggregate.** Ranh giới quá nhỏ khiến invariant bị rải rác; quá lớn tạo tranh chấp và transaction phức tạp. Quyết định theo yêu cầu nhất quán thực tế.

## 12. Kiểm thử aggregate và publication ở các mức

Một chiến lược tốt gồm:

### Unit test domain không khởi động Spring

Kiểm tra bản thân `Order.pay()` với các trường hợp:

| Trường hợp | Kết quả state | Domain event |
| --- | --- | --- |
| Đơn PENDING, tổng tiền dương | Chuyển PAID | Có đúng một `OrderPaid` |
| Gọi `pay()` lần hai | Không đổi trạng thái | Không có event mới |
| Đơn CANCELLED | Bị từ chối theo rule | Không tạo `OrderPaid` |
| Dữ liệu không hợp lệ | Exception/validation thích hợp | Không tạo event |

Ví dụ mục 5 minh họa hai dòng đầu; trường hợp `CANCELLED` cần bổ sung trạng thái và rule tương ứng trước khi viết test. Unit test nên kiểm tra field payload và tính bất biến, không kiểm tra Spring container.

### Integration test với Spring Application Events

Dùng context thật hoặc `ApplicationEvents` trong Spring Boot Test để xác minh application service phát đúng kiểu event, đúng dữ liệu và đúng số lần. Khi dùng `@DomainEvents`, hãy thực sự gọi phương thức repository được Spring Data hỗ trợ thay vì chỉ gọi method domain.

### Kiểm thử transaction, rollback và retry

Với integration test có DB transaction thật:

1. Commit thành công → `@TransactionalEventListener(AFTER_COMMIT)` được gọi theo hợp đồng.
2. Transaction rollback → AFTER_COMMIT không chạy.
3. Không có transaction → mặc định listener transaction không chạy.
4. Process chết sau commit trước khi gửi → mô hình outbox có thể khôi phục.
5. Một event được nhận lại → consumer không thực hiện side effect hai lần.

Không dùng một test tự động bọc transaction rồi rollback để kết luận rằng callback AFTER_COMMIT hoạt động; nhiều test Spring có `@Transactional` sẽ rollback mặc định. Cần thiết kế test commit thật hoặc dùng tiện ích test transaction thích hợp.

## 13. Checklist khi áp dụng

1. Aggregate root đã là nơi kiểm tra bất biến cần giữ ngay chưa?
2. Domain event đặt tên theo **điều đã xảy ra**, có payload tối thiểu và immutable chưa?
3. Event được **ghi nhận tại lúc trạng thái chuyển hợp lệ**, có tránh tạo lại khi gọi lặp chưa?
4. Application service/repository đã phân định rõ nơi lưu và nơi publish event chưa?
5. Với Spring Data, hiểu các repository method kích hoạt `@DomainEvents` và vai trò `@AfterDomainEventPublication` chưa?
6. Các listener phụ thuộc commit đã dùng transaction phase thích hợp chưa?
7. Nếu không được mất sự kiện, có outbox/retry/idempotency/dedup chưa?
8. Có test domain thuần Java, integration event, commit/rollback và xử lý lại chưa?
9. Đã cân nhắc thứ tự, concurrency, thông tin nhạy cảm và phạm vi bounded context chưa?

**Kết luận:** Aggregate quyết định trạng thái hợp lệ và ghi nhận domain event; Spring chuyển thông tin đó đến các listener. Việc phát event nội bộ, việc commit dữ liệu và việc chuyển thông điệp đáng tin cậy là ba trách nhiệm khác nhau. Phân biệt đúng chúng giúp hệ thống giữ invariants vững và mở rộng hành vi khi nghiệp vụ thay đổi.

## Tham khảo

- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): `@DomainEvents` và `@AfterDomainEventPublication`.
- [Spring Data Commons — AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html): cách ghi nhận domain events.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, commit/rollback và fallback.
