# Kiểm tra loại sự kiện, nội dung và số lần phát trong Spring Boot

Trong Spring Boot, một service có thể gọi `ApplicationEventPublisher.publishEvent(...)` để thông báo rằng **đơn hàng được đặt**, **đơn hàng bị hủy** hoặc **dữ liệu đã thay đổi**. Các listener dùng `@EventListener` hoặc `@TransactionalEventListener` để xử lý sự kiện, chẳng hạn ghi audit, cập nhật projection, hoặc gửi một thông báo. Test chỉ xác nhận “gọi phương thức đặt hàng không ném lỗi” **không chứng minh** sự kiện được phát **đúng loại, đúng dữ liệu, đúng một lần**.

Một test đáng tin phải phân biệt ít nhất ba câu hỏi:

1. **Đã publish sự kiện gì?** Sự kiện đúng **class/type** hay một loại khác tình cờ có nội dung gần giống?
2. **Payload có đúng không?** `orderId`, `quantity`, `correlationId` và các trường nghiệp vụ phải chính xác, không chỉ `notNull`.
3. **Publish bao nhiêu lần?** Một thao tác phát đúng một sự kiện, không bị thiếu hoặc lặp; nhiều thao tác được đếm đúng, từng type được đếm riêng.

Thêm hai câu hỏi mở rộng cho observability: listener có **xử lý** đúng số lần không, và một side effect bên ngoài (email, Kafka message, database row) có **hoàn thành** không? **Publish ≠ listener execution ≠ external delivery.** Đây là các bằng chứng khác nhau và cần các tests khác nhau.

Bài thuộc nhóm **Sự kiện và observability** của **Spring Boot - testing**. Nội dung trình bày cơ chế sự kiện Spring, `@RecordApplicationEvents` và `ApplicationEvents`, lọc theo loại, kiểm nội dung và số lần, Mockito `ArgumentCaptor` cho unit test, sự khác biệt giữa phát và xử lý, transaction commit/rollback, async listeners, các lỗi thường gặp và một dự án **Java 17 + Spring Boot 3.5 + JUnit Jupiter** với **17 test methods**. Mã dùng Spring application events **trong cùng JVM**, không cần Docker, database hoặc event broker.

## 1. Application event là gì và đi qua đâu?

Spring ApplicationContext có event publisher. Khi code gọi:

```java
publisher.publishEvent(
        new OrderPlacedEvent("ORD-1", 2, "REQ-1"));
```

Spring multicaster sẽ dispatch sự kiện tới các `ApplicationListener` hoặc `@EventListener` tương thích. Sự kiện tùy biến **không bắt buộc kế thừa `ApplicationEvent`**: record `OrderPlacedEvent` có thể là payload object. Spring sẽ bọc object đó trong `PayloadApplicationEvent` để chuyển qua cơ chế event listeners nội bộ.

```text
CheckoutService.placeOrder(...)
            |
            +-- validate order ID / quantity / correlation ID
            |
            +-- ApplicationEventPublisher.publishEvent(OrderPlacedEvent)
                         |
                         v
             ApplicationEventMulticaster
                         |
             +-----------+----------------+
             |                            |
             v                            v
      @EventListener                Spring TestContext
      OrderEventObserver            @RecordApplicationEvents
             |                            |
             v                            v
      xử lý / cập nhật state        ApplicationEvents.stream(
      của listener                  OrderPlacedEvent.class)
             |                            |
             v                            v
      assert listener count         assert publish count,
      và listener payload           type, payload
```

**Quy tắc quan trọng:**

- `ApplicationEventPublisher.publishEvent(Object)` là cơ chế **in-process** của Spring; tự nó **không gửi tới Kafka/RabbitMQ** và không có durable delivery guarantee.
- Theo cấu hình Spring thông thường, listener `@EventListener` được gọi **đồng bộ** bởi multicaster mặc định; nhưng ứng dụng có thể cấu hình executor, async listeners, transaction-bound listeners hoặc multicaster khác. Test phải hiểu cấu hình thực tế.
- `@EventListener` có thể tiêu thụ **payload record** trực tiếp, ví dụ `void onPlaced(OrderPlacedEvent event)`.
- `@EventListener` có thể **có điều kiện** hoặc chỉ nhận một subtype. Listener không được gọi không đồng nghĩa publisher không publish.
- Nếu listener method trả một object thay vì `void`, Spring có thể **phát tiếp một event từ return value**. Đây là một nguồn phát bổ sung cần tính khi đếm.
- Sự kiện không đồng nghĩa transaction đã commit. Với `@TransactionalEventListener`, listener có thể chờ commit/rollback; còn `@RecordApplicationEvents` ghi nhận việc event **được phát**, không đảm bảo giao dịch đã thành công.
- Một request có thể phát nhiều loại sự kiện; **không dùng tổng mọi Spring event** làm số sự kiện nghiệp vụ vì Spring framework cũng có context/lifecycle/test events.

### Vì sao record event tốt cho test payload?

Giả sử:

```java
public record OrderPlacedEvent(
        String orderId,
        int quantity,
        String correlationId) {
}
```

Java 17 record tự cung cấp `equals`, `hashCode` và accessors `orderId()`/`quantity()`/`correlationId()`. Nhờ đó test có thể so toàn bộ payload:

```java
assertThat(published)
        .containsExactly(
            new OrderPlacedEvent("ORD-1", 2, "REQ-1"));
```

Nếu event được tạo sai quantity hoặc correlation ID, assertion thất bại. Với class mutable hoặc payload chứa timestamp/ID ngẫu nhiên, nên inject `Clock`/ID generator để test deterministic hoặc dùng field-by-field assertions, tránh so wall-clock chính xác. Không thêm timestamp động vào event chỉ để có vẻ thực tế nhưng lại khiến test flaky.

## 2. `@RecordApplicationEvents` và `ApplicationEvents`

Spring TestContext cung cấp annotation `@RecordApplicationEvents` (từ Spring Framework 5.3.3) để thu các ứng dụng events **được publish trong phạm vi từng test method**. Cách dùng phổ biến trong JUnit Jupiter:

```java
@SpringBootTest
@RecordApplicationEvents
class OrderEventTest {

    @Autowired
    CheckoutService service;

    @Test
    void publishesExactlyOnce(ApplicationEvents events) {
        service.placeOrder("ORD-1", 2, "REQ-1");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
    }
}
```

Đây là snippet minh họa, cần classes/imports và Spring context; dự án hoàn chỉnh nằm ở phần 6. Spring TestContext phải có `ApplicationEventsTestExecutionListener`; listener này được đăng ký **mặc định**, trừ khi bạn tự cấu hình `@TestExecutionListeners` làm mất danh sách defaults.

### API cốt lõi

| API | Ý nghĩa | Lưu ý test |
|---|---|---|
| `@RecordApplicationEvents` | Bật thu sự kiện cho test class | Không đặt trên một method đơn lẻ thay vì class |
| `ApplicationEvents events` | Snapshot logic/stream của events trong test hiện tại | Inject vào JUnit method hoặc field |
| `events.stream()` | Stream **mọi `ApplicationEvent` đã được ghi** | Có thể gồm Spring context/test/lifecycle events |
| **`events.stream(OrderPlacedEvent.class)`** | Stream những event **hoặc payload** thuộc loại này | Trả `Stream<OrderPlacedEvent>` khi event là POJO/record payload |
| `events.stream(...).count()` | Số events/payloads của type được chỉ định | Dùng `1L`, `2L`, `0L` rõ ràng |
| `events.stream(...).toList()` | Lấy snapshot list để assert type/content/order | Stream là one-shot; tạo stream mới mỗi lần cần dùng |
| `events.clear()` | Xóa **recorded events** hiện tại của test | Không hoàn tác publish, không reset listener side effects |
| `@BeforeEach void reset(ApplicationEvents events)` | Dọn baseline của test khi cần | Phạm vi per-test, không clear global bus |

**Điểm thường gây lỗi:** một record event thường được Spring dispatch bằng `PayloadApplicationEvent`. Do đó `events.stream()` trả `ApplicationEvent` objects (có thể nhìn thấy wrapper), trong khi `events.stream(OrderPlacedEvent.class)` **lọc và đưa ra payload đúng loại**. Đừng cast toàn bộ `events.stream()` thành `OrderPlacedEvent` hoặc assert type wrapper là business event.

### Vì sao không nên đếm `events.stream().count()`?

Khi chạy `@SpringBootTest`, application context cũng publish `ContextRefreshedEvent`, `ContextClosedEvent` và các framework events khác; Spring TestContext cũng có thể publish event theo test lifecycle. Tổng số events chịu ảnh hưởng môi trường và thứ tự khởi tạo. Một assertion như:

```java
assertThat(events.stream().count()).isEqualTo(1);
```

là **quá rộng** nếu bạn chỉ muốn chứng minh **một `OrderPlacedEvent`**. Trong code thực, nên viết:

```java
assertThat(events.stream(OrderPlacedEvent.class).count())
        .isEqualTo(1L);
```

Nếu cần đếm **tất cả business event types** theo policy riêng, định nghĩa nhóm types/interface đánh dấu domain events và lọc có ý nghĩa, không đồng nhất tất cả application events với một domain event.

### `ApplicationEvents.clear()` làm gì?

`clear()` chỉ **xóa những sự kiện đã được ghi lại trong cửa sổ quan sát hiện tại**. Nó không gỡ sự kiện khỏi publisher, không hủy callback đã thực thi, không xóa email đã gửi hoặc record listener đã lưu. Với test cần baseline sạch, có thể gọi cả:

```java
@BeforeEach
void reset(ApplicationEvents events) {
    events.clear();      // reset nhật ký test
    observer.clear();    // reset state của listener fake
}
```

Snippet giả định `observer` là bean test hoặc component có API `clear()`. Ví dụ hoàn chỉnh phía dưới dùng chiến lược này. Với test chạy song song và context cache dùng chung, phải bảo đảm state của observer được cô lập theo test ID hoặc không chạy parallel; chỉ `events.clear()` không làm state của singleton listener thread-safe/test-isolated.

## 3. Kiểm tra loại sự kiện: type phải chính xác

Giả sử service có hai event types:

```java
public record OrderPlacedEvent(
        String orderId, int quantity, String correlationId) {}

public record OrderCancelledEvent(
        String orderId, String reason, String correlationId) {}
```

Khi test gọi `placeOrder(...)`, cần assert:

- Có **`OrderPlacedEvent`** đúng loại.
- **Không có `OrderCancelledEvent`**.
- Không nhầm hai types vì chúng đều chứa `orderId` hoặc chung prefix `Order`.
- Nếu logic chọn event type theo điều kiện, kiểm từng nhánh, không chỉ assertion `notNull`.

```java
List<OrderPlacedEvent> placed =
        events.stream(OrderPlacedEvent.class).toList();

assertThat(placed).containsExactly(
        new OrderPlacedEvent("ORD-1", 2, "REQ-1"));

assertThat(events.stream(OrderCancelledEvent.class).count())
        .isZero();
```

Ở đây `events.stream(Class<T>)` cho phép type-safe filtering. Nếu thử cast `PayloadApplicationEvent<?>` sang record, bạn đã kiểm sai tầng abstraction và có thể gặp `ClassCastException`.

### Type identity khác nội dung

Không nên so:

```java
assertThat(events.stream().anyMatch(
        e -> e.toString().contains("ORD-1"))).isTrue();
```

Đây là anti-pattern: `toString()` của wrapper hoặc framework event có thể chứa đoạn text tình cờ trùng; message formatting có thể đổi. Hãy truy xuất **đúng type**, rồi assert **field giá trị**. Trong ví dụ dùng Java record, `containsExactly(new OrderPlacedEvent(...))` đồng thời kiểm type, số lượng, thứ tự và toàn bộ payload.

### Một event type hay một subclass?

`stream(MyType.class)` dùng filtering dựa trên type; nếu dùng inheritance, các subtype có thể được chấp nhận theo kiểu được yêu cầu. Khi chính sách đòi event **phải đúng concrete class**, kiểm `event.getClass().equals(MyEvent.class)` trên từng event, hoặc dùng records/final types. Khi chính sách cho phép subtype, dùng `isInstanceOf`/filter theo base interface. Đừng chọn kiểu assertion tùy tiện: **“có thuộc type này”** khác **“đúng class này và không có subtype”**.

## 4. Kiểm nội dung: tránh assertion quá yếu hoặc quá dễ vỡ

Một publish test nên kiểm những trường **có ý nghĩa nghiệp vụ**:

| Trường | Tại sao phải kiểm? | Assertion hữu ích |
|---|---|---|
| `orderId` | Routing/dedup và phân biệt đối tượng | Bằng ID đúng của request |
| `quantity` | Tránh phát event với số lượng mặc định/đã bị biến đổi sai | Bằng số nguyên mong đợi |
| `correlationId` | Trace call-chain, đối soát request | Giữ nguyên ID từ đầu vào |
| `event type` | Đúng nhánh business workflow | `OrderPlacedEvent.class`, không phải cancelled |
| `reason` với cancel event | Lý do nghiệp vụ chuyển tiếp đúng | String chính xác hoặc enum phù hợp |
| `timestamp` nếu có | Thời điểm phát/ghi nhận | Inject `Clock.fixed(...)` hoặc compare within tolerance |
| `aggregate version` nếu có | Ordering/optimistic concurrency | Assert version bằng giá trị sự kiện mong đợi |
| `schemaVersion` nếu có | Compatibility khi gửi sang broker | Assert theo contract, không chỉ có mặt |

Ví dụ cụ thể:

```java
OrderPlacedEvent event =
        events.stream(OrderPlacedEvent.class)
                .findFirst()
                .orElseThrow();

assertThat(event.orderId()).isEqualTo("ORD-1");
assertThat(event.quantity()).isEqualTo(2);
assertThat(event.correlationId()).isEqualTo("REQ-1");
```

**Hạn chế:** `findFirst()` tự nó **không chứng minh duy nhất một event**; có thể có ba event, vẫn lấy được event đầu. Kèm `count() == 1` hoặc `containsExactly(...)` để kiểm số lượng.

Dùng giá trị cố định từ test cho IDs/timestamp (inject generators) khi cần deterministic. Tránh assert nguyên văn `toString()` của event, thứ tự JSON property không được contract bảo đảm, hoặc timezone hiện tại nếu bài không nhằm kiểm format thời gian.

## 5. Đếm số lần phát: đúng một lần, nhiều lần, không phát

### Một operation → một event

```java
service.placeOrder("ORD-1", 2, "REQ-1");

assertThat(events.stream(OrderPlacedEvent.class).count())
        .isEqualTo(1L);
```

Đây là assertion trực tiếp về **số lần publish** của type `OrderPlacedEvent` trong test scope, không phải số listener được gọi.

### Hai operations → hai events

```java
service.placeOrder("ORD-1", 2, "REQ-1");
service.placeOrder("ORD-2", 3, "REQ-2");

assertThat(events.stream(OrderPlacedEvent.class).toList())
        .containsExactly(
            new OrderPlacedEvent("ORD-1", 2, "REQ-1"),
            new OrderPlacedEvent("ORD-2", 3, "REQ-2"));
```

Với publisher và listener synchronous, thứ tự hai lời gọi trong cùng thread xác định cho demo. Trong thực tế nếu có nhiều threads/async dispatch, không giả định global ordering giữa các event producers. Nếu order không phải contract, dùng AssertJ `containsExactlyInAnyOrder(...)`; vẫn kiểm **đủ và không thừa**.

### Invalid input → không publish

```java
assertThatThrownBy(
        () -> service.placeOrder("", 1, "REQ-1"))
        .isInstanceOf(IllegalArgumentException.class);

assertThat(events.stream(OrderPlacedEvent.class).count())
        .isZero();
```

Bằng chứng này hữu ích khi event chỉ nên phát **sau khi validation/command acceptance**. Nếu service publish rồi throw sau đó, event vẫn có thể đã được gửi đến listener. Khi logic liên quan DB transaction, phải cân nhắc thời điểm publish vs commit và business definition của event.

### Tại sao đếm mỗi type riêng?

Nếu một action phát `OrderPlacedEvent`, listener phát tiếp `AuditEvent`, và framework phát thêm context events, `events.stream().count() == 1` có thể sai dù publisher nghiệp vụ hoàn toàn đúng. Đếm:

```java
long placedCount =
        events.stream(OrderPlacedEvent.class).count();
long cancelledCount =
        events.stream(OrderCancelledEvent.class).count();

assertThat(placedCount).isEqualTo(1);
assertThat(cancelledCount).isZero();
```

Nếu bạn cần khẳng định không phát **bất kỳ loại domain event nào khác**, cần bao phủ toàn bộ domain taxonomy hoặc dùng marker interface/event registry; hai assertions trên chỉ loại trừ những types mà bạn kiểm.

## 6. Ví dụ Maven hoàn chỉnh: Java 17, Spring Boot 3.5, 17 JUnit tests

Project mô phỏng đặt/hủy đơn hàng và công bố hai loại event. `OrderEventObserver` nhận events qua `@EventListener`; các tests tách bằng chứng **publish** (qua `@RecordApplicationEvents`) khỏi bằng chứng **listener handled** (qua observer state). Một test class thứ hai dùng Mockito `ArgumentCaptor` để chỉ kiểm contract publisher **ở unit level**.

### 6.1. Cây thư mục

```text
order-events-testing/
├── pom.xml
└── src/
    ├── main/java/com/example/events/
    │   ├── EventsDemoApplication.java
    │   ├── OrderPlacedEvent.java
    │   ├── OrderCancelledEvent.java
    │   ├── CheckoutService.java
    │   └── OrderEventObserver.java
    └── test/java/com/example/events/
        ├── CheckoutEventIntegrationTest.java
        └── CheckoutServiceUnitTest.java
```

Test không cần `application.properties` hay database. Spring Boot application context tải `CheckoutService`, `OrderEventObserver` và default Spring event multicaster.

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>order-events-testing</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter` tạo Spring ApplicationContext và event infrastructure. `spring-boot-starter-test` mang Spring TestContext, JUnit Jupiter, AssertJ và Mockito. Không cần `spring-boot-starter-web` vì ví dụ không chạy controller/HTTP. Java 17 đáp ứng record API; Spring Boot 3.5 parent quản lý dependency versions. Lệnh `mvn test` sẽ thực thi cả hai test classes.

### 6.3. Spring Boot application class

File **`src/main/java/com/example/events/EventsDemoApplication.java`**:

```java
package com.example.events;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EventsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(EventsDemoApplication.class, args);
    }
}
```

Các test `@SpringBootTest(webEnvironment=NONE)` không mở embedded web server. Class main cung cấp `@SpringBootConfiguration` và component scan cho service/listener.

### 6.4. Hai event types là Java records

File **`src/main/java/com/example/events/OrderPlacedEvent.java`**:

```java
package com.example.events;

public record OrderPlacedEvent(
        String orderId,
        int quantity,
        String correlationId) {
}
```

File **`src/main/java/com/example/events/OrderCancelledEvent.java`**:

```java
package com.example.events;

public record OrderCancelledEvent(
        String orderId,
        String reason,
        String correlationId) {
}
```

Hai events là **payload objects**, không kế thừa `ApplicationEvent`. `ApplicationEventPublisher.publishEvent(Object)` hỗ trợ dạng này; Spring listener có thể nhận record trực tiếp. Record là immutable theo trường (với field types ở đây đều immutable), rất phù hợp để quan sát history và so equality trong test.

### 6.5. `CheckoutService`: publish sau khi kiểm input

File **`src/main/java/com/example/events/CheckoutService.java`**:

```java
package com.example.events;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ApplicationEventPublisher publisher;

    public CheckoutService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void placeOrder(
            String orderId, int quantity, String correlationId) {

        requireText(orderId, "orderId");
        requireText(correlationId, "correlationId");

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }

        publisher.publishEvent(
                new OrderPlacedEvent(
                        orderId, quantity, correlationId));
    }

    public void cancelOrder(
            String orderId, String reason, String correlationId) {

        requireText(orderId, "orderId");
        requireText(reason, "reason");
        requireText(correlationId, "correlationId");

        publisher.publishEvent(
                new OrderCancelledEvent(
                        orderId, reason, correlationId));
    }

    private static void requireText(
            String value, String field) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must be non-blank");
        }
    }
}
```

Service publish **đúng một event mỗi method invocation hợp lệ**. Nó không có lưu DB, không có idempotency hoặc deduplication. Vì vậy hai calls cùng `orderId` vẫn publish **hai events** — đó là đặc tính **demo**, không phải kết luận rằng duplicate events là an toàn trong hệ thống sản xuất. Nếu nghiệp vụ yêu cầu exactly-once business transition, cần enforce invariant/idempotency và test trạng thái persisted/outbox.

### 6.6. Listener đếm và lưu payload đã xử lý

File **`src/main/java/com/example/events/OrderEventObserver.java`**:

```java
package com.example.events;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventObserver {

    private final List<OrderPlacedEvent> placed =
            new CopyOnWriteArrayList<>();
    private final List<OrderCancelledEvent> cancelled =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void onPlaced(OrderPlacedEvent event) {
        placed.add(event);
    }

    @EventListener
    public void onCancelled(OrderCancelledEvent event) {
        cancelled.add(event);
    }

    public List<OrderPlacedEvent> placed() {
        return List.copyOf(placed);
    }

    public List<OrderCancelledEvent> cancelled() {
        return List.copyOf(cancelled);
    }

    public void clear() {
        placed.clear();
        cancelled.clear();
    }
}
```

Listener methods trả `void` để không vô tình publish event mới từ return value. `CopyOnWriteArrayList` an toàn cho việc đọc/ghi đơn giản giữa threads, nhưng **không tự bảo đảm test isolation khi nhiều tests chạy song song trên cùng singleton Spring context**. Bộ JUnit example giả định thực thi tuần tự mặc định. Trong dự án có JUnit parallel, dùng collector theo `correlationId`, per-test scope hoặc listener fake riêng, không dùng `clear()` trên singleton đang được tests khác chia sẻ.

**Bằng chứng khác nhau:** `events.stream(OrderPlacedEvent.class).count()` chứng minh Spring TestContext quan sát được số lần **publish**; `observer.placed().size()` chứng minh listener tương ứng đã **xử lý đến điểm append**. Hai số này chỉ thường bằng nhau với listener sync thành công và không có filter; không nên mặc định bằng nhau ở production dùng async, transaction phases hoặc consumer retries.

### 6.7. Spring integration tests: 13 test methods

File **`src/test/java/com/example/events/CheckoutEventIntegrationTest.java`**:

```java
package com.example.events;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@RecordApplicationEvents
class CheckoutEventIntegrationTest {

    @Autowired
    private CheckoutService service;

    @Autowired
    private OrderEventObserver observer;

    @BeforeEach
    void reset(ApplicationEvents events) {
        events.clear();
        observer.clear();
    }

    @Test
    void onePlacementHasExactTypeAndPayload(
            ApplicationEvents events) {

        service.placeOrder("ORD-1", 2, "REQ-1");

        assertThat(events.stream(OrderPlacedEvent.class).toList())
                .containsExactly(new OrderPlacedEvent(
                        "ORD-1", 2, "REQ-1"));
    }

    @Test
    void listenerHandlesExactlyOneMatchingPlacedEvent(
            ApplicationEvents events) {

        service.placeOrder("ORD-2", 5, "REQ-2");

        OrderPlacedEvent expected =
                new OrderPlacedEvent("ORD-2", 5, "REQ-2");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
        assertThat(observer.placed()).containsExactly(expected);
    }

    @Test
    void placementDoesNotEmitCancellation(
            ApplicationEvents events) {

        service.placeOrder("ORD-3", 1, "REQ-3");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isZero();
        assertThat(observer.cancelled()).isEmpty();
    }

    @Test
    void twoDistinctPlacementsEmitExactlyTwoInOrder(
            ApplicationEvents events) {

        service.placeOrder("ORD-A", 1, "REQ-A");
        service.placeOrder("ORD-B", 3, "REQ-B");

        assertThat(events.stream(OrderPlacedEvent.class).toList())
                .containsExactly(
                    new OrderPlacedEvent("ORD-A", 1, "REQ-A"),
                    new OrderPlacedEvent("ORD-B", 3, "REQ-B"));

        assertThat(observer.placed()).hasSize(2);
    }

    @Test
    void twoCallsWithSameIdAreVisibleAsTwoPublications(
            ApplicationEvents events) {

        service.placeOrder("ORD-SAME", 1, "REQ-A");
        service.placeOrder("ORD-SAME", 1, "REQ-B");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(2L);
        assertThat(observer.placed()).hasSize(2);
        // Demo không dedupe; production cần idempotency nếu cần.
    }

    @Test
    void cancellationEmitsOnlyCancellationTypeWithPayload(
            ApplicationEvents events) {

        service.cancelOrder("ORD-9", "customer-request", "REQ-9");

        assertThat(events.stream(OrderCancelledEvent.class).toList())
                .containsExactly(new OrderCancelledEvent(
                        "ORD-9", "customer-request", "REQ-9"));
        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
        assertThat(observer.cancelled()).hasSize(1);
    }

    @Test
    void mixedBusinessTypesAreCountedSeparately(
            ApplicationEvents events) {

        service.placeOrder("ORD-10", 1, "REQ-10");
        service.cancelOrder("ORD-10", "changed-mind", "REQ-11");
        service.placeOrder("ORD-11", 4, "REQ-12");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(2L);
        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isEqualTo(1L);
        assertThat(observer.placed()).hasSize(2);
        assertThat(observer.cancelled()).hasSize(1);
    }

    @Test
    void blankOrderIdDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.placeOrder(" ", 1, "REQ-BAD"))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
        assertThat(observer.placed()).isEmpty();
    }

    @Test
    void zeroQuantityDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.placeOrder("ORD-BAD", 0, "REQ-BAD"))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
    }

    @Test
    void blankCorrelationIdDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.placeOrder("ORD-BAD", 1, ""))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
    }

    @Test
    void blankCancellationReasonDoesNotPublish(
            ApplicationEvents events) {

        assertThatThrownBy(() ->
                service.cancelOrder("ORD-12", "", "REQ-12"))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isZero();
    }

    @Test
    void clearStartsNewRecordedWindowButNotListenerReset(
            ApplicationEvents events) {

        service.placeOrder("ORD-BEFORE", 1, "REQ-BEFORE");

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isEqualTo(1L);
        assertThat(observer.placed()).hasSize(1);

        events.clear(); // Không undo listener side effect.

        service.placeOrder("ORD-AFTER", 2, "REQ-AFTER");

        assertThat(events.stream(OrderPlacedEvent.class).toList())
                .containsExactly(new OrderPlacedEvent(
                        "ORD-AFTER", 2, "REQ-AFTER"));
        assertThat(observer.placed()).hasSize(2);
    }

    @Test
    void typedBusinessStreamStartsEmptyAfterReset(
            ApplicationEvents events) {

        assertThat(events.stream(OrderPlacedEvent.class).count())
                .isZero();
        assertThat(events.stream(OrderCancelledEvent.class).count())
                .isZero();
        assertThat(observer.placed()).isEmpty();
        assertThat(observer.cancelled()).isEmpty();
        // Không assert events.stream().count() == 0:
        // framework/test lifecycle có thể publish event khác.
    }
}
```

**13 phương thức `@Test`** này cho thấy: mỗi test có `ApplicationEvents` riêng, được reset bằng `events.clear()`, observer cũng được reset, có cả positive/negative cases, và số lần phát được kiểm theo **từng event type**. Không assert tổng mọi Spring framework events. Test `clearStartsNewRecordedWindowButNotListenerReset` chứng minh reset nhật ký event **không xóa việc listener đã xử lý**.

### 6.8. Mockito unit tests: kiểm publisher call khi không chạy Spring context

File **`src/test/java/com/example/events/CheckoutServiceUnitTest.java`**:

```java
package com.example.events;

import org.junit.jupiter.api.Test;

import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;

class CheckoutServiceUnitTest {

    @Test
    void publishesOneExactOrderPlacedPayload() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        service.placeOrder("ORD-U1", 7, "REQ-U1");

        ArgumentCaptor<OrderPlacedEvent> captor =
                ArgumentCaptor.forClass(OrderPlacedEvent.class);
        verify(publisher, times(1))
                .publishEvent(captor.capture());

        assertThat(captor.getValue()).isEqualTo(
                new OrderPlacedEvent("ORD-U1", 7, "REQ-U1"));
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void invalidInputNeverCallsPublisher() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        assertThatThrownBy(() ->
                service.placeOrder("", 1, "REQ-U2"))
                .isInstanceOf(IllegalArgumentException.class);

        verifyNoInteractions(publisher);
    }

    @Test
    void cancelUsesCancellationEventNotPlacedType() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        service.cancelOrder("ORD-U3", "duplicate", "REQ-U3");

        ArgumentCaptor<OrderCancelledEvent> captor =
                ArgumentCaptor.forClass(OrderCancelledEvent.class);
        verify(publisher, times(1))
                .publishEvent(captor.capture());

        assertThat(captor.getValue()).isEqualTo(
                new OrderCancelledEvent(
                        "ORD-U3", "duplicate", "REQ-U3"));
        verifyNoMoreInteractions(publisher);
    }

    @Test
    void twoInvocationsCallPublisherTwice() {
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        CheckoutService service = new CheckoutService(publisher);

        service.placeOrder("ORD-U4", 1, "REQ-U4");
        service.placeOrder("ORD-U5", 2, "REQ-U5");

        verify(publisher, times(2))
                .publishEvent(any(OrderPlacedEvent.class));
        verifyNoMoreInteractions(publisher);
    }
}
```

**4 phương thức `@Test`** này có mục tiêu khác integration suite: Mockito chỉ quan sát lệnh gọi `ApplicationEventPublisher.publishEvent(...)`, không tạo Spring ApplicationContext, không dispatch thật tới listener. `ArgumentCaptor` cho phép assert type/payload/count ngay ở publication boundary. Unit tests thường nhanh hơn và rất hữu ích khi muốn kiểm mỗi nhánh business publish đúng. Nhưng **verify publisher không chứng minh listener chạy**, chưa nói tới external broker hoặc side effects.

Ở Java, `ApplicationEventPublisher` có overload `publishEvent(ApplicationEvent)` và `publishEvent(Object)`; các event records trong demo **không kế thừa `ApplicationEvent`**, vì vậy lời gọi `publishEvent(captor.capture())` hoặc `publishEvent(any(OrderPlacedEvent.class))` trỏ tới overload `Object` và Mockito có thể quan sát đúng.

### 6.9. Cách chạy, kỳ vọng và giới hạn

Dùng JDK 17+, Maven, không cần Docker:

```bash
mvn test
mvn -Dtest=CheckoutEventIntegrationTest test
mvn -Dtest=CheckoutServiceUnitTest test
```

Nếu project có Maven Wrapper: `./mvnw test` (Linux/macOS) hoặc `mvnw.cmd test` (Windows). Theo mã ví dụ, kỳ vọng **13 integration + 4 unit = 17 JUnit tests**, không có failures/errors. Các tests dùng dữ liệu cố định và event dispatch đồng bộ trong context mặc định, nên không cần `Thread.sleep` hay await eventual state.

**Không có stdout nghiệp vụ cố định.** Output Maven Surefire và Spring context log thay đổi theo phiên bản/cấu hình. Mã đã được rà soát theo API Spring Framework 6.2/Spring Boot 3.5/Java 17; **đây không phải tuyên bố đã thực thi Maven**. Khi dùng thực tế, hãy chạy trong project/CI của bạn và xác nhận Spring test listeners cùng event multicaster config.

## 7. Phân biệt publish count, listener invocation count và side effects

| Chỉ số | Có nghĩa là gì? | Công cụ test | Không chứng minh |
|---|---|---|---|
| Publisher call count | Service gọi `publishEvent` bao nhiêu lần | Mockito `verify(..., times(n))` | Listener thực chạy |
| Recorded application event count | Spring TestContext thấy bao nhiêu payload event của type đó | `@RecordApplicationEvents` + `events.stream(Type.class).count()` | Listener/consumer đã hoàn tất |
| Listener handled count | Listener đã vào code và hoàn thành một điểm checkpoint cụ thể | Fake collector/spy, counter/sink | External email/Kafka đã giao |
| External command count | Số lần adapter gọi API Kafka/email/HTTP | Fake gateway, broker recorder/test double | Provider đã xử lý chính xác |
| Persisted outcome count | Số rows/outbox messages sau commit | DB integration test + cleanup | Kafka consumer đã nhận exactly once |
| End-user/business outcome | Hành động nghiệp vụ đã đạt invariant | End-to-end/saga/integration tests | Event bus tự cung cấp exactly-once |

Ví dụ có **một event** và **hai listeners**: publication count = 1 nhưng tổng listener invocation có thể = 2. Hoặc listener tự phát `AuditEvent` thì tổng events = 2 dù command publish `OrderPlacedEvent` đúng một lần. Một listener có `condition` chỉ chạy khi dữ liệu phù hợp; recorded count vẫn có thể là 1 trong khi handled count = 0.

**Không viết một assertion `Mockito.verify(listener, times(1))` rồi gọi đó là “publisher phát đúng một lần”.** Nó chỉ chứng minh method listener được gọi một lần trong phạm vi spy/mock, có thể do một đường gọi khác, và không chứng minh loại payload đã được publish. Ngược lại, `@RecordApplicationEvents` cho biết việc publish nhưng không bảo đảm listener thành công nếu async/transacted.

### `@EventListener` có thể tự publish event mới từ return value

Một ví dụ cần tránh nếu không chủ đích:

```java
@EventListener
public AuditEvent handle(OrderPlacedEvent placed) {
    return new AuditEvent(placed.orderId(), "PLACED");
}
```

Đây là **snippet** cần định nghĩa class `AuditEvent` và imports; không nằm trong runnable demo. Theo semantics Spring `@EventListener`, return value không phải `void` có thể được publish như một event tiếp theo. Nếu test đếm `events.stream().count()` sẽ thấy nhiều hơn tưởng tượng; hãy lọc theo type cụ thể và kiểm listener nghiệp vụ có được phép emit follow-up event hay không.

Nếu listener vừa ghi DB vừa return `AuditEvent`, test cần phân biệt: event đã xuất hiện trong bus, listener đã ghi thành công, hay outbox đã commit? Phát event không tự cung cấp transaction atomicity.

## 8. Transaction-bound events: publish có trước commit

Spring cung cấp `@TransactionalEventListener` với phases:

- `BEFORE_COMMIT`: trước commit.
- `AFTER_COMMIT` (**mặc định**): chạy sau khi giao dịch commit thành công.
- `AFTER_ROLLBACK`: chạy sau rollback.
- `AFTER_COMPLETION`: sau khi transaction kết thúc dù commit hay rollback.

Ví dụ:

```java
@Component
class NotificationHandler {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    void notifyAfterCommit(OrderPlacedEvent event) {
        // Chỉ chạy khi transaction chứa publication COMMIT.
        // Đây là snippet, không phải runnable component đầy đủ.
    }
}
```

Nếu **không có transaction đang hoạt động**, listener theo transaction **không chạy** theo mặc định; có thể chọn `fallbackExecution=true` nếu business contract cho phép xử lý ngoài transaction. Phải cân nhắc rõ yêu cầu; không thêm fallback tùy tiện để test xanh.

### Vì sao test `@Transactional` hay bị hiểu sai?

Một test Spring có `@Transactional` thường được TestContext rollback cuối test. Nếu service publish event trong transaction đó:

```text
@Transactional test begins
       |
       +-- service publishes OrderPlacedEvent
       |       |
       |       +-- @RecordApplicationEvents thấy publish: count=1
       |
       +-- @TransactionalEventListener(AFTER_COMMIT)
       |       |
       |       +-- CHƯA chạy vì chưa commit
       |
       +-- test ends -> rollback
               |
               +-- AFTER_COMMIT listener KHÔNG chạy
```

Vậy **recorded publication count=1** và **after-commit listener count=0** đều có thể đúng. Đây không phải lỗi Spring event bus. Nếu mục tiêu là kiểm listener chạy sau commit, cần **chủ động commit một transaction thuộc test**, chẳng hạn Spring `TestTransaction` trong test có `@Transactional` và transaction manager thật, hoặc dùng `TransactionTemplate` với database/transaction manager test phù hợp. Đừng gắn `@Commit` bừa bãi làm ô nhiễm DB shared; cleanup theo test ID.

Với `TestTransaction`, flow khái niệm (snippet, không runnable độc lập):

```java
// Test được quản lý bởi Spring TestContext, đang có
// @Transactional và PlatformTransactionManager thật.
service.placeOrder("ORD-1", 1, "REQ-1");

TestTransaction.flagForCommit();
TestTransaction.end();   // commit: AFTER_COMMIT có thể xử lý

// Assert listener side effect / state sau commit.
// Nếu muốn mở transaction mới: TestTransaction.start().
```

**Quan trọng:** `@RecordApplicationEvents` ghi nhận **publication** và không tự kiểm commit, listener side effect hay DB persistence. Nếu listener `AFTER_COMMIT` cần ghi dữ liệu mới vào DB, transaction resources có thể vẫn accessible nhưng transaction đã kết thúc; thường cần transaction mới (`REQUIRES_NEW`) cho thao tác ghi theo tài liệu Spring. Không suy rằng mọi write bên trong AFTER_COMMIT được commit một cách mặc định.

Với reactive transactions, transaction context nằm trong Reactor Context, không phải thread-bound như imperative transaction manager; hãy theo hướng dẫn `TransactionalEventPublisher` và reactive tests nếu sử dụng WebFlux/R2DBC.

## 9. Async listeners và điều kiện thời gian trong tests

Một listener có thể cấu hình `@Async @EventListener`, hoặc event multicaster có task executor. Trong trường hợp đó:

1. Lời gọi `publishEvent` có thể return **trước khi listener thực hiện xong**.
2. `@RecordApplicationEvents` có thể đã ghi publication trong test, nhưng listener side effect chưa xong.
3. Assertion ngay sau publication về listener count có thể flaky.
4. Một exception ném trong async listener có thể được xử lý bởi executor/error handler, **không tự quay về JUnit test thread**.
5. Scope ghi sự kiện của `ApplicationEvents` gắn với lifecycle của test method và test thread/descendant threads theo Spring TestContext. Không dựa vào việc ghi events phát từ một worker bất kỳ sau khi test kết thúc.
6. Nếu test có nhiều loại event trong parallel pipelines, thứ tự publish/consume toàn cục không luôn xác định.

### Cách kiểm async listener đúng

Dùng **bounded acknowledgement** thay vì `Thread.sleep(1000)`:

```text
Test thread                       Async listener
     |                                   |
     +-- publish(event) ---------------->|
     |                                   +-- process event
     |                                   +-- completion.complete(result)
     |
     +-- completion.get(5, SECONDS) <----+
     +-- assert processed type/payload/count
```

Khi test dùng một fake listener, có thể expose `CompletableFuture<Void>` hoặc `CountDownLatch` signal sau khi thật sự xử lý. Test chờ `get(timeout)`/`await(timeout)`, kiểm lỗi từ worker bằng `completeExceptionally` và dọn thread state. Tránh sleep, tránh lặp polling vô hạn, tránh assert “listener count=1” khi worker chưa kịp chạy.

**Cẩn trọng với `@RecordApplicationEvents` và async:** các sự kiện phát từ threads không thuộc lifecycle test hoặc tới sau khi test kết thúc có thể không được ghi như mong đợi. Khi điều cần chứng minh là kết quả **consumer đã xử lý**, kiểm kết quả/acknowledgement của consumer thay vì chỉ đọc recorded events. Với event broker như Kafka/RabbitMQ, dùng consumer test, embedded broker hoặc Testcontainers phù hợp; không coi Spring in-process bus là đại diện cho network delivery.

## 10. Observability: event emission khác metric/log/trace

Một ứng dụng có thể có cả:

- **Domain event**: `OrderPlacedEvent` — dữ liệu nghiệp vụ về một transition.
- **Micrometer counter**: `order.events.published` tăng khi publish, có thể gắn event type/outcome.
- **Observation/span**: trace correlation, latency, status và error nếu có instrumentation.
- **Audit log**: thông điệp cho người vận hành; log không phải event store.
- **Outbox record**: bản ghi đáng tin cậy dùng để phát tới broker sau commit.
- **Broker message**: event/message đã được gửi qua Kafka/RabbitMQ.
- **Consumer acknowledgement**: consumer đã xử lý hoặc ack theo semantics broker.

Đừng dùng **log line count** để khẳng định ứng dụng đã publish event đúng một lần: logging có filter, retries, batching, duplication, async appenders hoặc level config. Nếu quan trọng, test **publisher boundary trực tiếp** bằng Mockito hoặc `@RecordApplicationEvents`. Với metric, dùng `MeterRegistry` test và assert counter delta trước/sau operation (tránh leak giữa tests), nhưng đó là **đếm metric**, không thay thế event payload test.

### CorrelationId và high-cardinality

`correlationId` trong payload là hữu ích để trace/đối soát từng operation. Khi gắn metric tags, **không** đưa mọi `orderId`/`correlationId` làm tag nếu sinh vô hạn giá trị: high cardinality làm tăng chi phí metrics và có thể gây rủi ro vận hành. Gắn event type/outcome theo tập hữu hạn, còn correlationId đưa vào trace/log đã được kiểm soát, tránh PII/secrets.

Nếu event mang dữ liệu nhạy cảm, không dùng `toString()` của record để log toàn bộ payload. Test nội dung event cũng cần dùng giá trị giả lập, không hardcode token thật, tên khách hàng hoặc payment details.

## 11. Kịch bản QA và lỗi phổ biến

| Lỗi trong code/test | Vì sao nguy hiểm? | Bằng chứng hoặc cách sửa |
|---|---|---|
| Chỉ assert service không throw | Có thể không publish gì | Assert `events.stream(Type.class).count()` |
| Chỉ assert event count > 0 | Có thể publish trùng nhiều lần | Assert count **đúng bằng 1** và payload |
| Chỉ `findFirst()` | Có thể còn nhiều events phía sau | Assert `containsExactly(...)` hoặc count |
| Đếm `events.stream().count()` | Lẫn framework/test/lifecycle events | Filter `events.stream(DomainType.class)` |
| Assert message `toString()` | Không type-safe, dễ sai khi format đổi | Assert record equality/fields |
| Không kiểm event khác loại | Logic có thể phát nhầm cancellation | Assert target type có, wrong type không |
| Listener count = 1 được coi như publish count | Hai listener hoặc event condition làm số khác | Test publisher và listener ở boundaries khác |
| Dùng Mockito publisher mock để chứng minh listener thật chạy | Mock không dispatch | Bổ sung `@SpringBootTest` + `@RecordApplicationEvents` |
| Chỉ dùng `@RecordApplicationEvents` để chứng minh Kafka đã gửi | In-process events không tự đồng nghĩa broker delivery | Broker/adapter integration test |
| Không dùng `@RecordApplicationEvents` | `ApplicationEvents` không được cấu hình cho test | Gắn annotation và giữ TestExecutionListener mặc định |
| Tự thay `@TestExecutionListeners` làm mất defaults | Không có ApplicationEventsTestExecutionListener | Merge mặc định hoặc đăng ký listener phù hợp |
| Dùng `clear()` để mong hoàn tác listener | clear chỉ reset recorded history | Reset fake observer/DB state riêng |
| Context cache + singleton observer, parallel tests | State trộn giữa tests | Per-test correlation/isolation hoặc disable parallel |
| Dựa vào order giữa async publishers | Race giữa threads | `containsExactlyInAnyOrder` nếu order không thuộc contract |
| Assertion listener chạy ngay sau async publish | Handler chưa hoàn thành | Bounded latch/future, không sleep |
| Test `@Transactional` rollback nhưng expect AFTER_COMMIT listener | Không có commit | TestTransaction/TransactionTemplate với commit thật |
| Ghi event trước transaction commit và expect exactly-once DB outcome | Rollback sau publication vẫn để lại event đã phát | Transaction-bound event/outbox/compensation |
| Listener return non-void vô tình phát event mới | Spring publish return value | Dùng void hoặc test follow-up event riêng |
| Event xử lý nhiều lần do caller retry | Không có idempotency/dedup | Stable operation ID, stateful integration tests |
| Assert toàn bộ timestamp `Instant.now()` chính xác | Flaky do scheduling | Inject Clock hoặc tolerance có lý do |
| Đếm Spring context events như domain events | Startup tạo events ngoài nghiệp vụ | Dùng event type và correlation ID |
| Ghi raw event payload vào log | Có thể lộ PII/secrets | Redact và kiểm log-level policy |
| Test không bao quát invalid command | Có thể publish sau validate fail | Negative tests: invalid input -> 0 events |
| Service publishes 2 events nhưng test chỉ assert 1 match | Extra emissions bị bỏ qua | Assert exact count + wrong types + listener checkpoint |

### Quy trình phân tích khi số lượng event không đúng

1. **Xác định boundary**: cần kiểm publish tại service, dispatch tới Spring listener, hay message ra broker?
2. **Đếm theo concrete type** bằng `ApplicationEvents.stream(EventType.class)` hoặc publisher call verification, không tổng framework events.
3. **Gắn correlation/aggregate ID** cho mỗi thao tác; phát nhiều events cùng type có phải business contract hay do retry?
4. **Quan sát payload** đầy đủ: method nào tạo giá trị, có trả field mặc định/nhầm ID không?
5. **Kiểm listener side effect riêng**: có `@EventListener(condition=...)`, multiple listeners, async, transactional phases?
6. **Xác minh transaction boundary**: event được publish trước hay sau commit? Test @Transactional có rollback không?
7. **Kiểm duplicate sources**: service publish hai nơi, event listener return value, retry ở controller/service, request bị gọi hai lần, broker redelivery.
8. **Cô lập test state**: `@BeforeEach` reset recorder/observer; nếu parallel, dùng per-test IDs và synchronized collectors thay vì singleton clear.
9. **Giữ assertion chặt**: exact count, exact payload và expected absent types; không đổi thành `isNotEmpty()` chỉ để test pass.
10. **Tách observability khỏi delivery guarantee**: event counter đúng không đồng nghĩa e-mail/DB/outbox/Kafka đã giao thành công.

## 12. Mở rộng: kiểm sự kiện dùng ApplicationEvent subclass

Không phải mọi event đều là record payload. Bạn cũng có thể định nghĩa class extends `ApplicationEvent`:

```java
public class InventoryChangedEvent extends ApplicationEvent {

    private final String sku;

    public InventoryChangedEvent(Object source, String sku) {
        super(source);
        this.sku = sku;
    }

    public String getSku() {
        return sku;
    }
}
```

Đây là **snippet** cần import `org.springframework.context.ApplicationEvent` và enclosing package, không nằm trong runnable demo. Với subclass như vậy, Spring publisher dùng `publishEvent(ApplicationEvent)`, và `ApplicationEvents.stream(InventoryChangedEvent.class)` lọc chính event class; không cần unwrapping payload object.

**Chọn cách nào?** Với Java 17 và domain event đơn giản, record payload tiện vì immutable và equality dễ test. Kế thừa `ApplicationEvent` hữu ích nếu bạn thật sự cần event metadata/source theo cơ chế class truyền thống. Tránh dùng `ApplicationEvent.getSource()` làm nơi chứa dữ liệu nhạy cảm hoặc trao quyền; nó không tạo được bảo đảm durable event schema.

## 13. Checklist cho bài test sự kiện và observability

- [ ] Đề bài xác định **event boundary**: publisher, Spring listener, broker, outbox hay external side effect.
- [ ] Test có `@RecordApplicationEvents` và `ApplicationEventsTestExecutionListener` mặc định.
- [ ] Test sử dụng `events.stream(ExactEventType.class)`, không đếm tất cả Spring events.
- [ ] Event type đúng và không lẫn với event type khác.
- [ ] Payload được assert theo **đủ các trường có ý nghĩa**, không chỉ `notNull` hoặc `toString()`.
- [ ] Số events đúng chính xác: 0, 1, 2... theo mỗi nghiệp vụ.
- [ ] Có positive case một event và negative case input invalid -> 0 events.
- [ ] Có case nhiều operations để phát hiện thiếu event hoặc duplicate.
- [ ] Có test kiểm payload giữ đúng correlationId/aggregate ID.
- [ ] Không dùng `findFirst` để thay cho assertion uniqueness.
- [ ] Khi cần kiểm publisher unit level, dùng Mockito `ArgumentCaptor`/`verify(times(n))`.
- [ ] Khi cần kiểm event dispatch, chạy qua Spring context/`@EventListener` thật.
- [ ] Listener count được assert riêng, không đồng nhất với publication count.
- [ ] Test state được reset đúng: `events.clear()` và fake listener collector riêng.
- [ ] Nếu context cached / JUnit parallel, có test isolation theo IDs và thread safety phù hợp.
- [ ] Test nhận biết `@EventListener` return non-void có thể republish event.
- [ ] Nếu có `@TransactionalEventListener`, đã kiểm AFTER_COMMIT/ROLLBACK theo transaction thật.
- [ ] Không kỳ vọng AFTER_COMMIT chạy khi Spring test transaction chỉ rollback.
- [ ] Nếu async listener, dùng bounded future/latch để đợi, không dùng Thread.sleep.
- [ ] Nếu event gửi Kafka/RabbitMQ, có integration test cho broker delivery/retry/dedup riêng.
- [ ] Không suy từ recorded event rằng DB commit, listener success hay external delivery đã hoàn tất.
- [ ] Metric/log/trace là bằng chứng quan sát khác nhau; đừng thay event payload test bằng log count.
- [ ] Không tạo high-cardinality metric tags bằng orderId/correlationId.
- [ ] Không log payload có secrets/PII; data của test dùng thông tin giả.
- [ ] Đã chạy `mvn test` trên JDK 17+ / Boot 3.5 và rà lại event multicaster config production.

**Kết luận:** Để chứng minh Spring Boot phát sự kiện đúng, hãy kiểm **đúng loại, đúng nội dung, đúng số lần**, trong một cửa sổ test đã được cô lập. `@RecordApplicationEvents` + `ApplicationEvents.stream(EventType.class)` là công cụ mạnh cho integration tests, còn Mockito `ArgumentCaptor` phù hợp unit tests của publisher. **Đừng đánh đồng một sự kiện đã publish với listener đã xử lý, giao dịch đã commit hoặc message đã tới hệ bên ngoài.** Những điều đó cần các bằng chứng và tests bổ sung tại đúng boundary.

### Tài liệu chính thức

- [Spring Framework 6.2 — Application Events trong TestContext](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/application-events.html)
- [Spring Framework 6.2 — @RecordApplicationEvents](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-recordapplicationevents.html)
- [Spring Framework 6.2 — ApplicationEvents Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/test/context/event/ApplicationEvents.html)
- [Spring Framework — Standard and Custom Events / @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Mockito — ArgumentCaptor API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/ArgumentCaptor.html)
