# Thu thập domain event trước khi publish trong Spring Framework

## 1. Vấn đề cần giải quyết

Trong thiết kế Domain-Driven Design (DDD), một thay đổi nghiệp vụ có thể làm phát sinh **domain event**: ví dụ đơn hàng được thanh toán (`OrderPaid`), hóa đơn được yêu cầu (`ReceiptRequested`), hoặc người dùng thay đổi email (`EmailChanged`). Domain event mô tả **một sự thật nghiệp vụ đã xảy ra trong mô hình domain**, chứ không đơn thuần là yêu cầu "hãy chạy hàm khác".

Nếu aggregate tự gọi `ApplicationEventPublisher.publishEvent(...)` ngay trong phương thức nghiệp vụ, mô hình domain sẽ phụ thuộc vào Spring và tác dụng phụ có thể chạy trước khi trạng thái aggregate được lưu thành công:

```text
Order.pay()
  ├─ đổi trạng thái order
  ├─ publishEvent(OrderPaid)     <-- gửi quá sớm
  └─ repository.save(order)      <-- có thể thất bại/rollback
```

Hệ quả: một listener có thể đã gửi email, cập nhật cache hoặc gọi hệ thống khác trong khi bản ghi chưa được lưu hoặc transaction sau đó rollback. Việc viết unit test cho `Order` cũng khó hơn khi nó cần `ApplicationEventPublisher`.

**Giải pháp:** domain chỉ **thu thập (record/register) event vào bộ đệm pending events**. Một lớp điều phối bên ngoài domain, ví dụ application service, repository adapter hoặc cơ chế Spring Data, chọn thời điểm bàn giao event cho publisher.

```text
Command / application service
       |
       v
Aggregate thực thi nghiệp vụ
  ├─ thay đổi state
  ├─ kiểm tra invariant
  └─ register(new OrderPaid(...))
       |
       v
pendingEvents = [OrderPaid, ReceiptRequested]
       |
       v
Application service / repository infrastructure
  ├─ persist aggregate
  ├─ lấy snapshot pending events
  ├─ publish / ghi outbox
  └─ acknowledge, clear hoặc chuyển quyền sở hữu các event
       |
       v
Spring ApplicationEventPublisher -> listeners
```

"Thu thập trước khi publish" là **tách việc ghi nhận sự kiện trong domain khỏi việc phân phối sự kiện ở tầng hạ tầng**, không phải cam kết tự động có giao hàng đúng một lần hoặc sau commit.

## 2. Pending events trong aggregate là gì?

Một aggregate root có thể có bộ đệm riêng, chẳng hạn `List<DomainEvent> pendingEvents`. Mỗi phương thức thực hiện hành vi nghiệp vụ hợp lệ sẽ thêm event vào danh sách đó mà **chưa publish ngay**.

Ba khái niệm cần phân biệt:

- **Trạng thái nghiệp vụ**: ví dụ `paid = true`; đây là state cần được lưu hoặc được suy ra từ event log tùy kiến trúc.
- **Pending domain event**: mô tả hành vi vừa được chấp nhận trong một vòng xử lý. Thường là danh sách tạm trong bộ nhớ, chưa tự bảo đảm tồn tại sau khi process chết.
- **Published/delivered event**: event đã được bàn giao cho cơ chế phát; việc listener đã xử lý xong hay chưa còn tùy multicaster và chiến lược async/retry.

Một aggregate đơn giản không phụ thuộc Spring có thể đăng ký sự kiện như sau (đây chỉ là trích đoạn):

```java
private final List<DomainEvent> pendingEvents = new ArrayList<>();

private void register(DomainEvent event) {
    pendingEvents.add(Objects.requireNonNull(event));
}

public List<DomainEvent> pendingEvents() {
    return List.copyOf(pendingEvents); // snapshot chỉ đọc từ bên ngoài
}
```

Phần nghiệp vụ có thể gọi `register(new OrderPaid(...))` sau khi kiểm tra invariant và cập nhật state hợp lệ. Mã domain không cần biết listener nào tồn tại và không cần import Spring.

### Thiết kế payload của event

Nên dùng immutable `record` (Java 17) hoặc object bất biến chứa dữ liệu snapshot mà consumer cần. Ví dụ:

```java
record OrderPaid(String orderId, String paymentId, long amountInCents) {}
```

- `orderId`: tham chiếu aggregate.
- `paymentId`: định danh nghiệp vụ để theo dõi/deduplicate nếu mỗi thanh toán có ID duy nhất.
- `amountInCents`: snapshot giá trị tại thời điểm event được tạo; tránh để listener đọc trực tiếp state của aggregate có thể đã thay đổi.

Trong hệ thống thực, có thể bổ sung event ID riêng, thời gian xảy ra sự kiện, phiên bản schema và aggregate version. Không truyền entity JPA mutable hoặc `EntityManager` tới listener như một "payload event" cần sống lâu, vì chúng có vòng đời gắn với transaction/persistence context.

### Không biến pending events thành một phần ngầm của state được persist

Nếu dùng JPA, pending events thường là chi tiết tạm của aggregate, có thể được đánh dấu `@Transient` trong entity. Nếu aggregate được load lại từ database mà bộ đệm tạm đã mất, không được giả định các event chưa phát sẽ tự xuất hiện trở lại. Khi đòi hỏi khôi phục sau lỗi tiến trình, cần **outbox bền vững** hoặc event store đúng nghĩa.

## 3. Khi nào thu thập, khi nào publish?

Một quy trình ứng dụng dễ hiểu:

1. Nhận command và load aggregate.
2. Gọi hành vi domain (`order.pay(...)`). Aggregate kiểm tra ràng buộc, đổi state và **register events**.
3. Ghi state qua repository hoặc Unit of Work.
4. Đọc snapshot pending events để quyết định cơ chế publish.
5. Bàn giao event cho `ApplicationEventPublisher`, hoặc ghi event vào outbox.
6. Đánh dấu những event đã được bàn giao theo chính sách thực thi.

**Thứ tự trên chỉ mô tả luồng đơn giản; không đồng nghĩa với "save xong là database đã commit".** Khi service có `@Transactional`, lời gọi repository `save(...)` thường diễn ra khi transaction còn mở. Nếu publish trực tiếp ngay sau `save` trong cùng transaction, listener đồng bộ có thể chạy **trước commit**.

Có ba chính sách cần lựa chọn rõ ràng:

| Cách xử lý | Tính chất | Phù hợp |
| --- | --- | --- |
| Publish ngay sau `save` khi transaction còn mở | Listener thông thường có thể chạy trước commit | Xử lý nội bộ cùng transaction, không tạo side effect khó thu hồi |
| Publish trong transaction và dùng `@TransactionalEventListener(AFTER_COMMIT)` | Listener chỉ được kích hoạt sau commit thành công | Hành vi sau commit trong cùng process; chưa có bảo đảm lưu event bền vững |
| Ghi **transactional outbox** trong cùng DB transaction; worker relay sau commit | Có bản ghi event bền vững để retry nếu process chết | Tích hợp liên dịch vụ, cần độ tin cậy và kiểm soát giao nhận |

Chỉ dùng `pendingEvents.clear()` sau publish không biến danh sách in-memory thành queue bền vững. Cần ghi rõ ranh giới xử lý thất bại và chiến lược retry trước khi đưa vào production.

## 4. Ví dụ chạy được: Java 17 + Spring Framework 6.2

Ví dụ này là **minh họa thu thập và bàn giao event trong một tiến trình**. Nó dùng repository giả lập trong bộ nhớ, không có database transaction; không được lấy nó làm bằng chứng rằng event và dữ liệu được commit nguyên tử.

Một lần gọi `checkout` ghi nhận **hai** event theo thứ tự: `OrderPaid` và `ReceiptRequested`. Domain không biết Spring. Application service lưu aggregate, lấy snapshot pending events rồi publish từng event. Khi `publishEvent` trả về bình thường, ví dụ xóa đúng event vừa được bàn giao.

### Cấu trúc Maven

```text
pending-domain-events/
├── pom.xml
└── src/main/java/demo/PendingDomainEventsDemo.java
```

Tệp `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>pending-domain-events</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.PendingDomainEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/PendingDomainEventsDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class PendingDomainEventsDemo {

    // Phần domain thuần Java, không import Spring.
    public sealed interface DomainEvent
            permits OrderPaid, ReceiptRequested {}

    public record OrderPaid(
            String orderId, String paymentId, long amountInCents)
            implements DomainEvent {}

    public record ReceiptRequested(
            String orderId, String paymentId)
            implements DomainEvent {}

    public static final class Order {
        private final String orderId;
        private boolean paid;
        private final List<DomainEvent> pending = new ArrayList<>();

        public Order(String orderId) {
            this.orderId = Objects.requireNonNull(orderId);
        }

        public String orderId() {
            return orderId;
        }

        public void pay(String paymentId, long amountInCents) {
            Objects.requireNonNull(paymentId);
            if (paid) {
                throw new IllegalStateException("Order already paid");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("Amount must be positive");
            }

            // Domain hoàn tất thay đổi hợp lệ, CHỈ ghi nhận event.
            paid = true;
            pending.add(new OrderPaid(orderId, paymentId, amountInCents));
            pending.add(new ReceiptRequested(orderId, paymentId));
        }

        public List<DomainEvent> pendingEvents() {
            return List.copyOf(pending); // snapshot, không lộ list mutable
        }

        public void acknowledge(DomainEvent event) {
            if (!pending.remove(event)) {
                throw new IllegalArgumentException("Unknown pending event");
            }
        }
    }

    public static final class InMemoryOrderRepository {
        public void save(Order order) {
            // Không phải persistence thật và không có DB transaction.
            System.out.println("repository: saved " + order.orderId());
        }
    }

    public static final class CheckoutService {
        private final InMemoryOrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public CheckoutService(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void checkout(
                Order order, String paymentId, long amountInCents) {
            order.pay(paymentId, amountInCents);
            System.out.println("service: pending=" +
                    order.pendingEvents().size());

            repository.save(order);

            // Snapshot để vừa iterate vừa acknowledge buffer gốc.
            List<DomainEvent> events = order.pendingEvents();
            for (DomainEvent event : events) {
                publisher.publishEvent(event);
                order.acknowledge(event); // sau khi hand-off thành công
            }
            System.out.println("service: pending=" +
                    order.pendingEvents().size());
        }
    }

    public static final class Handlers {
        @EventListener
        public void onPaid(OrderPaid event) {
            System.out.println("listener: paid " + event.orderId() +
                    " " + event.amountInCents());
        }

        @EventListener
        public void onReceipt(ReceiptRequested event) {
            System.out.println("listener: receipt " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        InMemoryOrderRepository repository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        Handlers handlers() {
            return new Handlers();
        }

        @Bean
        CheckoutService checkoutService(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new CheckoutService(repository, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Order order = new Order("O-42");

            System.out.println("before command: pending=" +
                    order.pendingEvents().size());
            context.getBean(CheckoutService.class)
                    .checkout(order, "PAY-9", 1500);
            System.out.println("after command: pending=" +
                    order.pendingEvents().size());
        }
    }
}
```

Chạy với JDK 17+ và Maven, tại thư mục dự án:

```bash
mvn -q clean compile exec:java
```

Đầu ra do những lệnh `System.out.println` của ví dụ tạo ra:

```text
before command: pending=0
service: pending=2
repository: saved O-42
listener: paid O-42 1500
listener: receipt O-42
service: pending=0
after command: pending=0
```

Lý giải:

1. `Order.pay()` thay đổi state và ghi hai event vào `pending`, nhưng chưa phát sự kiện; chưa có dòng log từ listener.
2. Service quan sát được hai pending events trước khi save.
3. Repository giả lập in `repository: saved ...` trước bất kỳ listener nào.
4. `ApplicationEventPublisher.publishEvent(Object)` bàn giao từng record cho Spring; record không cần kế thừa `ApplicationEvent`. Spring có thể bọc object event trong `PayloadApplicationEvent` khi dispatch.
5. Với multicaster đồng bộ mặc định và các listener đơn giản này, mỗi event được xử lý trong lời gọi `publishEvent`. Thứ tự trong ví dụ tuân theo thứ tự vòng lặp danh sách pending.
6. Sau mỗi lần gọi publish trả về bình thường, service `acknowledge` event và hết pending. `List.copyOf` giúp duyệt snapshot mà không gặp `ConcurrentModificationException` khi xóa khỏi danh sách gốc.

**Giới hạn của ví dụ:** Việc in `repository: saved` không có nghĩa dữ liệu được durable commit; implementation này chỉ in ra màn hình. Trong một repository JPA thật với `@Transactional`, `save` không nhất thiết đồng nghĩa commit. Và việc `publishEvent` trả về không nói rằng tất cả listener async đã hoàn thành hoặc tác dụng phụ bên ngoài đã bền vững.

## 5. Tại sao nên thu thập theo aggregate, không publish bên trong entity?

### Giữ domain độc lập framework

Một aggregate tốt nên mô tả các quy tắc như "không thanh toán một đơn hàng hai lần" hoặc "số tiền phải dương". Nếu inject `ApplicationEventPublisher` vào entity, domain phải biết infrastructure và dễ bị trộn với code network/notification. Thu thập events giữ entity là Java thuần và dễ test.

### Bảo vệ invariant trước khi tạo event

Lệnh nghiệp vụ thất bại khi kiểm tra invariant **không được** thêm `OrderPaid`. Nếu event được tạo trước khi kiểm tra hợp lệ hoặc trước khi thay state nhất quán, listener có thể quan sát một điều chưa thật sự xảy ra.

### Cho phép nhiều thay đổi trước một lần bàn giao

Một command có thể chạm nhiều phương thức của cùng aggregate và sinh vài event. Application service có thể thu snapshot sau khi xử lý xong một đơn vị nghiệp vụ, thay vì phát sự kiện rời rạc trong lúc các bước domain vẫn đang thực hiện.

Tuy nhiên, danh sách pending **không tự là event log**: một event log lưu trữ bền vững và là nguồn sự thật của mô hình event-sourced, còn pending list thường chỉ là bộ đệm tạm để phát các thông báo phát sinh.

### Tối ưu kiểm thử

Không cần khởi động Spring khi test aggregate:

```java
Order order = new Order("O-42");
order.pay("PAY-9", 1500);
assert order.pendingEvents().size() == 2;
```

Trích đoạn này mang tính minh họa và đòi cùng định nghĩa `Order` như ví dụ chính. Trong test JUnit thực tế, ưu tiên `assertEquals(...)`/`assertThrows(...)` thay vì Java `assert` có thể bị vô hiệu khi không bật `-ea`. Test nên xác nhận trạng thái mới, loại/số lượng/payload events và không có event khi invariant bị từ chối.

## 6. Hỗ trợ sẵn của Spring Data: @DomainEvents và @AfterDomainEventPublication

Khi aggregate được quản lý qua Spring Data repository, có thể dùng `@DomainEvents` và `@AfterDomainEventPublication` thay cho vòng lặp publish bằng tay.

Ví dụ cấu trúc API (trích đoạn, cần thêm class/interface/import và repository thực tế):

```java
class OrderAggregate {
    private final List<Object> events = new ArrayList<>();

    void pay(String paymentId) {
        // cập nhật domain state, kiểm tra invariant...
        events.add(new OrderPaid(/* immutable snapshot */));
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

**Lưu ý:** phần `new OrderPaid(/* ... */)` ở ví dụ API trên là placeholder minh họa, không phải chương trình độc lập; chạy ví dụ đầy đủ ở mục 4 hoặc thay bằng constructor thật.

Ý nghĩa annotation:

- `@DomainEvents` đặt trên một phương thức **không nhận tham số**, trả về một event hoặc collection để repository infrastructure publish.
- `@AfterDomainEventPublication` đặt trên callback chạy sau khi infrastructure phát các event, thường dùng để xóa buffer.
- Theo tài liệu Spring Data Commons, các hook này gắn với repository operations nhận aggregate instance như `save(...)`, `saveAll(...)`, và một số dạng `delete(...)`; **không giả định `deleteById(...)` luôn kích hoạt**, vì framework có thể xóa theo ID mà không đưa aggregate instance tới cơ chế event.

Điều quan trọng: `@AfterDomainEventPublication` là mốc **sau khi gọi cơ chế publication**, không phải bằng chứng rằng transaction đã commit thành công, event đã được gửi qua broker, hoặc tất cả listener async đã xử lý xong.

### AbstractAggregateRoot giúp giảm boilerplate

Spring Data Commons có base class `org.springframework.data.domain.AbstractAggregateRoot<A>`, cung cấp:

- `registerEvent(event)` để thêm event;
- `andEvent(event)` để thêm event rồi trả lại aggregate;
- `domainEvents()` để lộ các event đang chờ;
- `clearDomainEvents()` để xóa buffer sau publication thông qua annotation thích hợp.

Ví dụ trích đoạn:

```java
class OrderEntity extends AbstractAggregateRoot<OrderEntity> {
    void pay(String paymentId) {
        // Sau khi cập nhật state và kiểm tra invariant:
        registerEvent(new PaymentAccepted(orderId, paymentId));
    }
}
```

Tên `PaymentAccepted`/`orderId` cần được định nghĩa trong dự án thực tế. Dùng Spring Data repository tiêu chuẩn để infrastructure thực hiện hook; **tự gọi phương thức trên entity không tự publish event**.

Không tự xóa pending list trong `@PostPersist` hoặc lifecycle callback ORM nếu cơ chế Spring Data đang chịu trách nhiệm publication, vì rất dễ làm mất event trước khi infrastructure lấy ra.

## 7. Bàn giao event và transaction: ba vấn đề độc lập

### 7.1. Đã lưu state chưa?

`repository.save(order)` chỉ là một lời gọi repository. Với JPA, thao tác ghi SQL có thể được flush sau đó và transaction chỉ commit ở ranh giới service. Nếu service bị rollback sau khi repository save trả về, state cuối cùng có thể không được lưu.

Vì thế nguyên tắc "save trước rồi publish" **không đủ** để bảo đảm listener ngoài DB chỉ xử lý event của một transaction đã commit.

### 7.2. Đã publish chưa?

`ApplicationEventPublisher.publishEvent(Object)` là thao tác **handoff** cho Spring multicaster. Tài liệu Spring Framework nhấn mạnh đây không phải cam kết mọi listener chạy đồng bộ, chạy ngay, hoặc đã hoàn tất. Với mặc định đồng bộ, lỗi listener có thể truyền về publisher; với `@Async` hoặc executor async, publisher có thể trả về trước khi listener chạy xong.

Nếu gọi `clear` ngay sau handoff, danh sách pending không còn giữ event để retry khi xử lý async về sau thất bại.

### 7.3. Đã được consumer xử lý đúng một lần chưa?

Dù event được publish thành công, consumer có thể thất bại sau khi thực hiện một phần tác dụng phụ. Retry sau lỗi timeout hoặc process restart có thể gây duplicate. **"Exactly once" ở mức tác dụng phụ ngoại hệ thống không tự có từ pending list, @DomainEvents hay @TransactionalEventListener.**

Để tăng khả năng chống trùng, mỗi event nên có event ID ổn định và consumer dùng idempotent operation hoặc lưu ID đã xử lý với unique constraint phù hợp.

## 8. Hai chiến lược an toàn hơn khi có transaction

### 8.1. @TransactionalEventListener(AFTER_COMMIT) cho in-process reaction

Publisher có thể phát event khi transaction còn mở, nhưng listener đăng ký:

```java
@Component
class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPaid event) {
        // Chỉ được gọi khi transaction imperative tương ứng commit.
    }
}
```

Đây là trích đoạn cần import/bean đầy đủ. Với giao dịch imperative thread-bound, listener đăng ký callback theo transaction đang hoạt động; code xử lý chỉ chạy sau commit. Mặc định `@TransactionalEventListener` không xử lý event nếu **không có transaction**; có `fallbackExecution = true` khi chính sách nghiệp vụ cho phép.

Cách này giải quyết vấn đề **chạy listener trước commit**, nhưng không giải quyết triệt để trường hợp process chết sau commit trước khi listener thực hiện side effect. Dữ liệu event in-memory vẫn có thể mất. Với thao tác ghi database mới từ `AFTER_COMMIT`, xem xét transaction độc lập `REQUIRES_NEW`; transaction cũ không tự có thêm lần commit.

### 8.2. Transactional outbox khi cần giao hàng bền vững

Khi hệ thống cần event được gửi sang message broker hoặc dịch vụ khác ngay cả sau crash, đưa pending events sang **outbox table** cùng transaction với state aggregate:

```text
BEGIN TRANSACTION
  update orders
  insert into outbox(event_id, aggregate_id, type, payload, created_at)
COMMIT

background relay
  read committed outbox rows
  publish to broker / external destination
  mark delivered or delete after acknowledgement
  retry with backoff on failure
```

Các lợi ích và điều kiện cần thiết:

1. State và outbox được commit/rollback **cùng nhau**; nếu transaction rollback, bản ghi event outbox cũng rollback.
2. Sau crash, relay có thể đọc lại outbox và tiếp tục.
3. Relay có thể gửi một event hơn một lần nếu publish đã thành công nhưng chưa kịp đánh dấu hoàn tất; **consumer phải idempotent**.
4. Cần job/relay, monitoring, chính sách retry, dead-letter, giữ thứ tự theo aggregate khi quan trọng, kiểm soát throughput và retention.
5. Event payload/schema nên bất biến và versioned để consumer không phụ thuộc trực tiếp cấu trúc entity.

Outbox không phải tính năng tự động của `@DomainEvents`. Nó là thiết kế lưu trữ và truyền thông điệp riêng được tổ chức xung quanh transaction.

## 9. Chính sách xóa pending events: các lựa chọn và bẫy

| Tình huống | Phản ứng đúng |
| --- | --- |
| Aggregate tạo event nhưng command bị từ chối trước khi thay state | Không tạo event |
| Repository save thất bại | Không giả định có thể phát; giữ hoặc loại buffer theo chính sách rollback/reload |
| `publishEvent` ném exception giữa danh sách | Có thể có event trước đó đã được xử lý; không xóa mù toàn bộ buffer |
| `publishEvent` trả về với executor async | Chỉ chứng minh handoff, không chứng minh listener hoàn thành |
| Giao dịch sau đó rollback | Event phát sớm có thể gây side effect sai; dùng after-commit/outbox |
| Event consumer nhận lại cùng event | Dùng event ID và idempotency/deduplication |
| Aggregate được load lại từ DB khác process | Pending list tạm có thể biến mất; cần outbox để phục hồi |
| Nhiều command đồng thời trên một aggregate | Dùng optimistic/pessimistic concurrency và isolation phù hợp |

Có hai chính sách phổ biến:

**(A) Acknowledge từng event sau handoff** giống ví dụ mục 4. Ưu điểm là lỗi ở phần tử thứ ba không xóa hai phần tử chưa được bàn giao. Nhược điểm: hai event đầu có thể đã chạy, nhưng retry cả batch có thể phát lại vì state/transaction không bền vững. Vì vậy cần tránh xử lý lặp hoặc ghi lại trạng thái handoff một cách an toàn.

**(B) Chụp snapshot rồi clear theo một ranh giới được định nghĩa rõ.** Ví dụ Spring Data infrastructure có `@AfterDomainEventPublication`. Ưu điểm là tránh phát lại ngoài ý muốn trong cùng persistence context. Nhược điểm là không bảo đảm after-commit hoặc exactly-once.

Không tự động "clear trước để tránh trùng": nếu việc publish thất bại sau khi clear, bạn đã đánh mất thông tin về event cần retry. Ngược lại, "clear sau khi gọi publisher" cũng không đủ nếu listener async lỗi sau đó. Chọn chính sách dựa trên retry, idempotency và durability, không chỉ dựa trên tính tiện lợi của API.

## 10. Thu thập ở aggregate hay ở Unit of Work?

### Aggregate-owned event buffer

Đây là lựa chọn phổ biến khi event phản ánh invariant và trạng thái của **một aggregate**. Event được tạo ngay tại hành vi domain; application service có thể thu thập rồi bàn giao ở ranh giới persistence.

Ưu điểm: logic rõ, test đơn giản, domain không phụ thuộc framework, dễ dùng với `AbstractAggregateRoot`.

Hạn chế: cần quản lý vòng đời của pending list, trạng thái aggregate sau lỗi, và mapping nếu ORM persist entity. Không được chia sẻ cùng aggregate instance mutable qua nhiều request/thread mà không có cơ chế concurrency.

### Unit-of-Work/event collector ở application layer

Trong những nghiệp vụ đụng nhiều aggregate hoặc cần chính sách phát event tập trung, có thể dùng một collector cho một đơn vị công việc. Mỗi aggregate ghi sự kiện vào collector được truyền qua interface domain hoặc trả ra dưới dạng kết quả. Application service phát hoặc ghi outbox sau khi xử lý tất cả thành công.

Phải đặc biệt chú ý scope của collector: không dùng singleton mutable list chung cho mọi request vì sẽ trộn event của các transaction khác nhau. Nên có scope rõ (command/transaction), cơ chế thread-safety và cleanup, không phụ thuộc vào `ThreadLocal` khi chuyển async/reactive context mà chưa truyền thông tin cần thiết.

**Quy tắc chọn:** aggregate buffer khi cần bảo vệ semantic của một aggregate; Unit of Work khi cần gom sự kiện từ nhiều đơn vị domain; transactional outbox khi ưu tiên durability và giao tiếp liên dịch vụ. Các cách này có thể kết hợp, nhưng cần có đúng một nơi chịu trách nhiệm chuyển event từ pending sang published/outbox.

## 11. Kiểm thử các trường hợp trọng yếu

Ngoài bài test happy path, nên kiểm tra các tình huống:

1. **Không phát sớm:** gọi `order.pay(...)` và assert `pendingEvents` tăng, nhưng listener chưa được gọi trước khi application service publish.
2. **Payload đúng:** ID, payment ID, số tiền và snapshot khớp dữ liệu khi domain operation hoàn tất.
3. **Invariant thất bại:** số tiền không hợp lệ hoặc đơn hàng đã paid thì không tạo event mới.
4. **Save lỗi:** giả lập repository ném exception; verify publisher không nhận event nào.
5. **Publish lỗi giữa batch:** verify chiến lược acknowledge/giữ pending và khả năng retry rõ ràng; không khẳng định không có duplicate nếu chưa có idempotency.
6. **Rollback:** với transaction thật, verify `AFTER_COMMIT` listener không chạy khi transaction rollback.
7. **Crash/retry:** nếu dùng outbox, verify event row tồn tại sau commit và relay gửi lại được sau restart.
8. **Duplicate delivery:** consumer xử lý cùng event ID hai lần mà side effect chỉ được áp dụng theo chính sách idempotency.
9. **Concurrent commands:** aggregate version hoặc row lock ngăn invariant bị vi phạm khi hai command cùng xử lý.

Các kiểm thử nên được tách thành unit test thuần domain, test integration cho Spring publisher/repository, và test integration/contract cho outbox/broker khi có sử dụng.

## 12. Tóm tắt và câu hỏi tự kiểm tra

**Quy trình tư duy:** domain thay đổi hợp lệ → ghi pending events → persistence boundary → lựa chọn publish hoặc outbox → acknowledge/cleanup theo chính sách đã định nghĩa. Tách tạo event ra khỏi phát event giúp domain sạch và kiểm soát thời điểm tốt hơn, nhưng **không tự tạo atomic commit hoặc bảo đảm giao hàng bền vững**.

Câu hỏi:

1. **Tại sao aggregate không nên gọi ApplicationEventPublisher trực tiếp trong `pay()`?** — Để không phụ thuộc Spring và tránh side effect trước persistence/commit.
2. **Pending list có phải event store không?** — Không; thường chỉ là bộ đệm trong bộ nhớ.
3. **Một domain operation có thể thu thập nhiều event?** — Có, ví dụ `OrderPaid` và `ReceiptRequested`.
4. **Save trả về có đồng nghĩa transaction đã commit không?** — Không.
5. **`publishEvent` trả về có chứng minh mọi listener đã xử lý xong?** — Không, nhất là khi có async.
6. **`@AfterDomainEventPublication` có nghĩa "đã gửi thành công sang broker" không?** — Không, nó là callback sau bước publication của Spring Data.
7. **Vì sao `deleteById` không bảo đảm cơ chế @DomainEvents?** — Repository có thể xóa chỉ bằng ID mà không nhận aggregate instance.
8. **Khi cần không mất event sau DB commit và process crash thì chọn gì?** — Transactional outbox với relay/retry/idempotent consumer.
9. **Nếu không có transaction, `@TransactionalEventListener` mặc định có chạy không?** — Không, trừ khi cấu hình fallback phù hợp.
10. **Chính sách xử lý duplicate quan trọng thế nào?** — Retry có thể gây gửi lại, nên event ID và idempotent handler là những cơ chế quan trọng.

## Tài liệu tham khảo

- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Data Commons — AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
