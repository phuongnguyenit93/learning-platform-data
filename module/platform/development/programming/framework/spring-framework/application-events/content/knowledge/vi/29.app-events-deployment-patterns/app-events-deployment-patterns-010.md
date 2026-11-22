# So sánh gọi trực tiếp và publish event trong Spring Framework Application Events

## 1. Bài toán và kết quả cần đạt

Trong một ứng dụng bán hàng, sau khi đơn hàng được chấp nhận, hệ thống cần:

1. Cập nhật trạng thái đơn.
2. Ghi audit.
3. Chuẩn bị thông báo cho khách.
4. Cập nhật số liệu thống kê.

Có hai cách triển khai quen thuộc:

- **Gọi trực tiếp (direct invocation):** service điều phối gọi rõ ràng từng dependency.
- **Publish event:** service công bố một sự kiện mô tả điều **đã xảy ra**; các listener đăng ký nhận sự kiện và tự thực hiện các phản ứng tương ứng.

Cả hai đều hợp lệ. Điều cần quyết định không phải cách nào “hiện đại hơn” mà là **hợp đồng nghiệp vụ**: tác vụ nào bắt buộc thành công trong đường gọi chính, tác vụ nào là phản ứng bổ sung, hệ thống cần độ tách rời bao nhiêu, lỗi lan truyền thế nào, transaction đóng ở đâu và mức độ tin cậy cần thiết ra sao.

Sau bài này, bạn có thể:

- Vẽ call flow của direct call và local application event trong Spring.
- Phân biệt **compile-time dependency**, **runtime coupling** và **event contract**.
- Hiểu hành vi mặc định của `ApplicationEventPublisher.publishEvent(...)`: **listener thông thường đồng bộ trên thread gọi**, không mặc nhiên chạy nền.
- Biết khi nào nên dùng direct call, `@EventListener`, `@Async` hoặc `@TransactionalEventListener`.
- Hiểu mối liên hệ giữa exception, thứ tự, kết quả trả về, transaction, rollback và eventual consistency.
- Tạo chương trình Java 17 + Spring Framework 6.2 chạy được để so sánh cùng một nghiệp vụ theo hai mẫu.
- Kiểm thử số event được phát, tác dụng phụ của listener và các trường hợp lỗi.
- Tránh hiểu lầm rằng event in-process là message broker, tự có retry hoặc đảm bảo exactly-once.

Chủ đề thuộc nhóm **Mẫu triển khai** của module **Spring Framework Application Events**.

## 2. So sánh bằng hai luồng xử lý

### 2.1. Direct invocation

```text
OrderController / command handler
              |
              v
       OrderApplicationService
              |
              +--> orderRepository.accept(orderId)
              |
              +--> auditService.record(orderId)
              |
              +--> notificationService.request(orderId)
              |
              +--> return result / throw exception
```

Source code nêu đích danh những thành phần được gọi. Khi đọc method, lập trình viên có thể biết khá rõ những bước nào sẽ chạy, theo thứ tự nào, và mỗi dependency trả về/throw gì.

Ví dụ:

```java
public void accept(String orderId) {
    orderRepository.accept(orderId);
    auditService.record(orderId);
    notificationService.request(orderId);
}
```

Đây là **đoạn mã minh họa**: cần định nghĩa repository và các service tương ứng. Trong chương trình hoàn chỉnh ở mục 7, các dependency thực sự được khai báo và inject bằng Spring.

### 2.2. Publish application event

```text
OrderController / command handler
              |
              v
       OrderApplicationService
              |
              +--> orderRepository.accept(orderId)
              |
              +--> publisher.publishEvent(
              |       OrderAccepted(eventId, orderId))
              |
              v
   Spring ApplicationEventMulticaster
              |
              +--> AuditListener.onAccepted(...)
              |
              +--> NotificationListener.onAccepted(...)
              |
              +--> MetricsListener.onAccepted(...)
```

Service phát event chỉ cần biết **event contract** và `ApplicationEventPublisher`, không phải danh sách mọi listener. Module mới có thể bổ sung listener cho event mà không sửa service nguồn, miễn là các điều kiện phân phối của Spring được đáp ứng.

Ví dụ:

```java
public void accept(String orderId) {
    orderRepository.accept(orderId);
    publisher.publishEvent(
            new OrderAccepted("evt-" + orderId, orderId));
}
```

Đây cũng là **đoạn minh họa**; trong hệ thống thật, `eventId` cần ổn định theo event occurrence và không đơn giản lấy `orderId` nếu có thể phát nhiều lần chấp nhận cho cùng một aggregate. Bài dùng công thức này **chỉ để có output xác định**.

### Điểm dễ nhầm nhất

**Publish event trong Spring không đồng nghĩa xử lý bất đồng bộ.** Spring sử dụng `SimpleApplicationEventMulticaster` với chiến lược **đồng bộ mặc định**, tức mỗi listener thông thường được gọi trên **thread của publisher**. Khi listener lỗi và exception không được xử lý, exception có thể lan tới `publishEvent(...)`. Do đó event giúp **giảm coupling ở mã nguồn**, nhưng **chưa tự tách rời thời gian thực thi, tài nguyên thread hoặc transaction**.

Muốn chuyển sang async phải **cấu hình rõ** `@Async`/executor hoặc multicaster thích hợp. Khi đó lại thay đổi hợp đồng về thứ tự, thời điểm hoàn tất và lan truyền lỗi.

## 3. Bảng so sánh kỹ thuật

| Tiêu chí | Gọi trực tiếp | Publish event nội bộ |
| --- | --- | --- |
| Quan hệ phụ thuộc | Caller inject và gọi service cụ thể | Publisher biết event type và `ApplicationEventPublisher`; không cần biết listener |
| Phát hiện đường thực thi | Dễ theo call graph | Cần tìm những `@EventListener`/`ApplicationListener` phù hợp |
| Nhiều phản ứng | Caller phải gọi hoặc dùng orchestrator | Nhiều listener có thể cùng nhận một event |
| Kết quả trả về | Method có thể trả kết quả có kiểu | `publishEvent(...)` không trả aggregate result của các listener |
| Thứ tự | Thứ tự gọi trong code rõ | Có thể dùng `@Order` cho listener đồng bộ; không tự đảm bảo thứ tự hoàn tất async |
| Đồng bộ mặc định | Có | **Có** với multicaster mặc định và listener thông thường |
| Lan truyền exception | Exception dependency thường quay về caller | Exception listener đồng bộ thường có thể quay về publisher |
| Transaction | Dễ quan sát đường gọi; cùng thread có thể dùng transaction đang hoạt động | Listener đồng bộ có thể tham gia transaction; hậu commit cần annotation riêng |
| Async | Tự tạo executor, `@Async` hoặc tương đương | Không tự async; có thể gắn `@Async` cho listener |
| Testing | Mock/stub từng dependency | Unit test publisher và integration test để xác nhận event + listener |
| Thêm hành vi mới | Thường phải đổi orchestrator | Có thể thêm listener mà không sửa publisher |
| Coupling với schema | API service có chữ ký rõ | Event schema là contract, cũng cần versioning |
| Tính đáng tin sau crash | Phụ thuộc transaction và external effect | Local event **không tự bền vững**; cần outbox/broker nếu không được mất |
| Khử trùng | Caller/consumer tự thiết kế | Framework **không** dedupe `eventId` |
| Performance | Vài method calls và công việc bên trong | Có overhead event dispatch, listener matching, payload; không mặc nhiên nhanh hơn |
| Độ minh bạch nghiệp vụ | Các bước bắt buộc hiện rõ | Fan-out dễ mở rộng nhưng có thể che giấu side effects quan trọng |

**Không có kết luận “publish event luôn tốt hơn”.** Chọn đúng phương thức theo tính bắt buộc, độ ổn định của workflow và mức độ cần mở rộng.

## 4. Gọi trực tiếp phù hợp khi nào?

### 4.1. Bước là điều kiện tiên quyết của kết quả

Nếu thao tác A **không được xem là thành công khi B chưa thành công**, một direct call hoặc một workflow/orchestrator tường minh thường hợp lý hơn.

Ví dụ đặt hàng chỉ được xác nhận nếu **reserve tồn kho** thành công:

```java
public Confirmation confirm(String orderId) {
    inventoryService.reserve(orderId);
    paymentService.authorize(orderId);
    return orderService.confirm(orderId);
}
```

Đây là **mã minh họa**, chưa phải một transaction đa dịch vụ chạy được. Nó thể hiện quan hệ phụ thuộc rõ: lệnh `confirm` cần biết kết quả `reserve` và `authorize`. Trong kiến trúc phân tán, nếu các bước ở nhiều service, cần saga/compensation hoặc protocol riêng; gọi trực tiếp qua HTTP cũng không tự cung cấp atomic transaction.

### 4.2. Caller cần kết quả hoặc lỗi ngay

Ví dụ:

```java
TaxCalculation tax = taxService.calculate(lines, region);
if (tax.total().signum() < 0) {
    throw new IllegalStateException("Invalid tax result");
}
```

Caller cần kiểu kết quả rõ để quyết định bước sau. `publishEvent(...)` là API công bố, **không** là request-response API tổng hợp giá trị từ mọi listener. Nếu caller cần một câu trả lời bắt buộc, không nên thay direct service call bằng event chỉ để giảm imports.

### 4.3. Ràng buộc transaction và thứ tự chặt

Một lệnh phải ghi dữ liệu liên quan trong **cùng transaction** thường nên thể hiện rõ các operation quan trọng. Ví dụ ghi invoice và dòng invoice qua repository trong một transaction. Nếu tách thành các `@EventListener` chỉ vì “modular”, người đọc có thể không nhận ra việc listener đồng bộ vẫn tham gia transaction, và việc một listener ném lỗi ảnh hưởng rollback.

**Mẫu thiết kế:** service trực tiếp điều phối các invariant bắt buộc; sau khi hoàn thành sự thật nghiệp vụ, phát event để thông báo cho **những phản ứng không tạo thành điều kiện tiên quyết**.

## 5. Publish event phù hợp khi nào?

### 5.1. Một sự kiện có nhiều subscriber độc lập

Ví dụ `OrderAccepted` có thể dẫn tới:

- Audit ghi một record.
- Thống kê tăng số đơn được chấp nhận.
- Hệ thống thông báo chuẩn bị email.
- Read model được cập nhật.
- Module bên ngoài quan sát để bổ sung tính năng.

Nếu mỗi module đều phải được hard-code vào `OrderService`, số dependency tăng và thay đổi một tính năng phụ có thể buộc sửa phần nghiệp vụ lõi. Event giúp module phát sự kiện không cần biết **số listener và danh tính cụ thể** của chúng.

### 5.2. Event diễn tả một sự thật quá khứ

Một event tốt nên mô tả **điều đã xảy ra**, ví dụ:

```java
public record OrderAccepted(
        String eventId,
        String orderId
) {}
```

Không nên đặt tên event theo một command bắt buộc như `PleaseChargeCreditCardNow` rồi phát nó với kỳ vọng listener duy nhất chắc chắn thực thi và trả kết quả. Command/intent có hợp đồng khác với domain fact.

### 5.3. Các module có vòng đời thay đổi độc lập

Khi marketing bổ sung analytics listener, domain service không cần thay đổi. Tuy nhiên, contract event vẫn phải ổn định: rename field, đổi kiểu event, thay ngữ nghĩa `eventId` hoặc bỏ `orderId` có thể phá subscriber. **Coupling không biến mất; nó chuyển từ dependency trực tiếp sang hợp đồng sự kiện và cấu hình runtime.**

### 5.4. Phản ứng phụ chịu được eventual consistency

Các công việc như cập nhật projection, gửi email thông báo, indexing search có thể phù hợp với event, nhưng chỉ nếu nghiệp vụ đã cho phép chúng hoàn thành muộn và có cơ chế retry/durability khi cần. Với Spring event đồng bộ mặc định, chúng **chưa chạy muộn**; chọn async/outbox nếu thực sự cần tách thời gian xử lý.

## 6. Spring xử lý publish event như thế nào?

### 6.1. ApplicationEventPublisher

`ApplicationEventPublisher` có các overload nhận `ApplicationEvent` hoặc object bất kỳ:

```java
publisher.publishEvent(new OrderAccepted("evt-100", "ORD-42"));
```

Một record Java không cần kế thừa `ApplicationEvent`. Spring có thể bọc nó bằng `PayloadApplicationEvent<T>` để phân phối; phương thức `@EventListener` có thể nhận **trực tiếp kiểu record**.

Các bên tham gia:

```text
ApplicationEventPublisher
        |
        v
ApplicationContext
        |
        v
ApplicationEventMulticaster
        |
        +--> @EventListener handlers
        +--> ApplicationListener implementations
```

Đây là event **in-process** trong một `ApplicationContext`, không phải message bus mạng.

### 6.2. Event listener

```java
@Component
public class AuditListener {
    @EventListener
    public void onAccepted(OrderAccepted event) {
        auditService.record(event.orderId());
    }
}
```

Đây là snippet tích hợp cần các dependency/import. Event listener chỉ hoạt động khi class là **Spring-managed bean**, phương thức phù hợp được hạ tầng phát hiện và event type khớp. Tạo `new AuditListener(...)` bằng tay bên ngoài context rồi mong Spring tự quét instance là sai.

### 6.3. Nhiều listener, không phải “mỗi event chỉ một callback”

Một lần publish có thể gọi **tất cả** listener phù hợp với kiểu event (có thể có filter/condition). `@Order` có thể giúp sắp thứ tự invoke giữa những listener:

```java
@Order(10)
@EventListener
public void auditFirst(OrderAccepted event) {
    // ...
}

@Order(20)
@EventListener
public void notifyLater(OrderAccepted event) {
    // ...
}
```

Đây là snippet minh họa cần class bean và event tương ứng. Với multicaster đồng bộ mặc định, thứ tự invoke này có thể được quan sát. Nhưng **`@Order` không tạo một transaction commit ordering hay bảo đảm completion ordering giữa các worker async**.

### 6.4. Listener có thể phát event dẫn xuất

Một listener **đồng bộ** có thể trả về event mới:

```java
@EventListener
public InventoryRequested onOrderAccepted(OrderAccepted event) {
    return new InventoryRequested(event.orderId());
}
```

Spring có thể publish return value dưới dạng event dẫn xuất; nếu method trả về collection/array, từng phần tử có thể được publish. Đây là đoạn tích hợp cần định nghĩa `InventoryRequested`. Không nên lạm dụng chaining nếu có thể tạo vòng lặp vô hạn hoặc khó xác định transaction và chủ thể điều phối.

Với listener `@Async`, **không dùng return value để publish event tiếp theo**; cần gọi `ApplicationEventPublisher.publishEvent(...)` tường minh.

## 7. Ví dụ chạy được: cùng một nghiệp vụ, hai kiểu tổ chức

Chương trình này dùng **Java 17**, **Spring Framework 6.2**, **Maven**, không cần Spring Boot, web server hoặc database.

Bối cảnh:

- `DirectOrderFlow` chấp nhận đơn rồi **gọi thẳng** `AuditAction` và `NotificationAction`.
- `EventOrderFlow` chấp nhận đơn rồi chỉ **publish `OrderAccepted`**.
- Ở event flow, có ba listener độc lập: audit, notification và metrics.
- `@Order(10/20/30)` cho output ổn định trong ví dụ **đồng bộ mặc định**.
- Một `ActionTrace` ghi nhận thứ tự từng bước; `InMemoryOrders` lưu trạng thái cho demo.
- Để đơn giản, `eventId = "evt-" + orderId` trong demo là **giá trị minh họa**, không phải chiến lược ID production.

### 7.1. Cấu trúc thư mục

```text
direct-vs-event/
├── pom.xml
└── src/
    ├── main/java/example/DirectVsEventDemo.java
    └── test/java/example/DirectVsEventDemoTest.java
```

### 7.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>direct-vs-event</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-test</artifactId>
            <version>6.2.0</version>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.3</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>example.DirectVsEventDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. Tệp src/main/java/example/DirectVsEventDemo.java

```java
package example;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class DirectVsEventDemo {

    public record OrderAccepted(String eventId, String orderId) {
        public OrderAccepted {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            if (eventId.isBlank() || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "IDs must not be blank");
            }
        }
    }

    public static final class ActionTrace {
        private final List<String> entries = new ArrayList<>();

        public void add(String entry) {
            entries.add(entry);
        }

        public List<String> snapshot() {
            return List.copyOf(entries);
        }

        public void clear() {
            entries.clear();
        }
    }

    public static final class InMemoryOrders {
        private final Map<String, String> states = new HashMap<>();
        private final ActionTrace trace;

        public InMemoryOrders(ActionTrace trace) {
            this.trace = trace;
        }

        public void accept(String orderId) {
            states.put(orderId, "ACCEPTED");
            trace.add("state:" + orderId);
        }

        public String status(String orderId) {
            return states.get(orderId);
        }
    }

    public static final class AuditAction {
        private final ActionTrace trace;

        public AuditAction(ActionTrace trace) {
            this.trace = trace;
        }

        public void record(String orderId) {
            trace.add("audit:" + orderId);
        }
    }

    public static final class NotificationAction {
        private final ActionTrace trace;

        public NotificationAction(ActionTrace trace) {
            this.trace = trace;
        }

        public void request(String orderId) {
            trace.add("notify:" + orderId);
        }
    }

    public static final class DirectOrderFlow {
        private final InMemoryOrders orders;
        private final AuditAction audit;
        private final NotificationAction notification;

        public DirectOrderFlow(
                InMemoryOrders orders,
                AuditAction audit,
                NotificationAction notification) {
            this.orders = orders;
            this.audit = audit;
            this.notification = notification;
        }

        public void accept(String orderId) {
            orders.accept(orderId);
            audit.record(orderId);
            notification.request(orderId);
        }
    }

    public static final class EventOrderFlow {
        private final InMemoryOrders orders;
        private final ApplicationEventPublisher publisher;

        public EventOrderFlow(
                InMemoryOrders orders,
                ApplicationEventPublisher publisher) {
            this.orders = orders;
            this.publisher = publisher;
        }

        public void accept(String orderId) {
            orders.accept(orderId);
            OrderAccepted event = new OrderAccepted(
                    "evt-" + orderId, orderId);
            publisher.publishEvent(event);
        }
    }

    public static class AuditEventListener {
        private final AuditAction audit;

        public AuditEventListener(AuditAction audit) {
            this.audit = audit;
        }

        @Order(10)
        @EventListener
        public void onOrderAccepted(OrderAccepted event) {
            audit.record(event.orderId());
        }
    }

    public static class NotificationEventListener {
        private final NotificationAction notification;

        public NotificationEventListener(
                NotificationAction notification) {
            this.notification = notification;
        }

        @Order(20)
        @EventListener
        public void onOrderAccepted(OrderAccepted event) {
            notification.request(event.orderId());
        }
    }

    public static class MetricsEventListener {
        private final ActionTrace trace;

        public MetricsEventListener(ActionTrace trace) {
            this.trace = trace;
        }

        @Order(30)
        @EventListener
        public void onOrderAccepted(OrderAccepted event) {
            trace.add("metric:" + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public ActionTrace trace() {
            return new ActionTrace();
        }

        @Bean
        public InMemoryOrders orders(ActionTrace trace) {
            return new InMemoryOrders(trace);
        }

        @Bean
        public AuditAction auditAction(ActionTrace trace) {
            return new AuditAction(trace);
        }

        @Bean
        public NotificationAction notificationAction(
                ActionTrace trace) {
            return new NotificationAction(trace);
        }

        @Bean
        public DirectOrderFlow directOrderFlow(
                InMemoryOrders orders,
                AuditAction audit,
                NotificationAction notification) {
            return new DirectOrderFlow(orders, audit, notification);
        }

        @Bean
        public EventOrderFlow eventOrderFlow(
                InMemoryOrders orders,
                ApplicationEventPublisher publisher) {
            return new EventOrderFlow(orders, publisher);
        }

        @Bean
        public AuditEventListener auditEventListener(
                AuditAction audit) {
            return new AuditEventListener(audit);
        }

        @Bean
        public NotificationEventListener notificationEventListener(
                NotificationAction notification) {
            return new NotificationEventListener(notification);
        }

        @Bean
        public MetricsEventListener metricsEventListener(
                ActionTrace trace) {
            return new MetricsEventListener(trace);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            DirectOrderFlow direct =
                    context.getBean(DirectOrderFlow.class);
            EventOrderFlow eventFlow =
                    context.getBean(EventOrderFlow.class);
            ActionTrace trace =
                    context.getBean(ActionTrace.class);
            InMemoryOrders orders =
                    context.getBean(InMemoryOrders.class);

            direct.accept("ORD-D");
            System.out.println("DIRECT " + trace.snapshot());

            trace.clear();

            eventFlow.accept("ORD-E");
            System.out.println("EVENT  " + trace.snapshot());

            System.out.println(
                    "STATUS ORD-D=" + orders.status("ORD-D"));
            System.out.println(
                    "STATUS ORD-E=" + orders.status("ORD-E"));
        }
    }
}
```

### 7.4. Chạy bằng Maven

Tại thư mục có `pom.xml`, dùng JDK 17+:

```bash
mvn -q compile exec:java
```

**Bốn dòng mà chương trình trực tiếp in ra**, không tính log hạ tầng nếu có:

```text
DIRECT [state:ORD-D, audit:ORD-D, notify:ORD-D]
EVENT  [state:ORD-E, audit:ORD-E, notify:ORD-E, metric:ORD-E]
STATUS ORD-D=ACCEPTED
STATUS ORD-E=ACCEPTED
```

### 7.5. Giải thích tại sao output đúng

**Direct flow:**

1. `DirectOrderFlow.accept("ORD-D")` gọi `orders.accept(...)`, ghi trạng thái và thêm `state:ORD-D`.
2. Gọi `AuditAction.record(...)`, thêm `audit:ORD-D`.
3. Gọi `NotificationAction.request(...)`, thêm `notify:ORD-D`.
4. Không có lời gọi `publishEvent(...)`, nên ba `@EventListener` của event flow không được kích hoạt bởi direct flow này.
5. Sau khi in, `trace.clear()` xóa các dòng trace, **không xóa trạng thái đơn hàng**.

**Event flow:**

1. `EventOrderFlow.accept("ORD-E")` gọi `orders.accept(...)`, thêm `state:ORD-E`.
2. Service tạo một `OrderAccepted`, rồi gọi `publisher.publishEvent(event)` **một lần**.
3. Spring tìm ba listener phù hợp nhận `OrderAccepted`.
4. Với multicaster đồng bộ mặc định, các method được gọi trên thread publisher. `@Order(10)` audit, `@Order(20)` notification, `@Order(30)` metrics làm thứ tự callback hiển thị theo thứ tự đó.
5. Vì phương thức publish đồng bộ trong demo, sau khi `eventFlow.accept(...)` trả về, trace đã chứa cả ba callback.
6. Event flow có thêm `metric:ORD-E` **mà không thêm dependency vào `EventOrderFlow`**. Đây là lợi ích mở rộng subscription.
7. Cả hai phương thức đều đặt trạng thái đơn hàng thành `ACCEPTED`; không có database hoặc transaction, nên demo không minh họa durability hay rollback.

**Điều không nên suy luận từ output:** event flow không mặc nhiên nhanh hơn, thread-safe hơn, bền hơn hay bảo đảm sau commit. Kết quả được thiết kế cho một Spring context, một thread đồng bộ và state in-memory.

## 8. Kiểm thử bằng Spring TestContext và JUnit 5

Bộ test dưới đây là phần tiếp nối trực tiếp của dự án mục 7; nó xác minh:

- Direct flow thực thi các action rõ ràng nhưng **không publish `OrderAccepted`**.
- Event flow publish **một** `OrderAccepted` có đúng payload và dẫn tới **ba subscriber** cùng xử lý.
- Từng test reset `ActionTrace` để tránh ảnh hưởng giữa các phương thức trong context được cache.

### 8.1. Tệp src/test/java/example/DirectVsEventDemoTest.java

```java
package example;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import example.DirectVsEventDemo.ActionTrace;
import example.DirectVsEventDemo.DirectOrderFlow;
import example.DirectVsEventDemo.EventOrderFlow;
import example.DirectVsEventDemo.OrderAccepted;

@SpringJUnitConfig(DirectVsEventDemo.Config.class)
@RecordApplicationEvents
class DirectVsEventDemoTest {

    @Autowired
    DirectOrderFlow direct;

    @Autowired
    EventOrderFlow eventFlow;

    @Autowired
    ActionTrace trace;

    @BeforeEach
    void reset() {
        trace.clear();
    }

    @Test
    void directCallsActionsWithoutPublishing(
            ApplicationEvents events) {
        events.clear();

        direct.accept("TEST-D");

        assertEquals(0,
                events.stream(OrderAccepted.class).count());
        assertEquals(
                List.of(
                        "state:TEST-D",
                        "audit:TEST-D",
                        "notify:TEST-D"),
                trace.snapshot());
    }

    @Test
    void eventPublishesOnceAndNotifiesThreeListeners(
            ApplicationEvents events) {
        events.clear();

        eventFlow.accept("TEST-E");

        List<OrderAccepted> published =
                events.stream(OrderAccepted.class).toList();
        assertEquals(1, published.size());
        assertEquals("evt-TEST-E", published.get(0).eventId());
        assertEquals("TEST-E", published.get(0).orderId());
        assertEquals(
                List.of(
                        "state:TEST-E",
                        "audit:TEST-E",
                        "notify:TEST-E",
                        "metric:TEST-E"),
                trace.snapshot());
    }
}
```

### 8.2. Chạy test

```bash
mvn test
```

Trong điều kiện dependencies được tải đầy đủ và code chạy thành công, báo cáo Surefire của bộ `DirectVsEventDemoTest` kỳ vọng:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là **các trường tổng kết kỳ vọng**, không phải toàn bộ stdout của Maven; phiên bản plugin, thiết lập CI và log môi trường có thể thêm thông tin. File kết quả ở `target/surefire-reports/example.DirectVsEventDemoTest.txt`.

### 8.3. Vì sao hai phép kiểm thử có giá trị khác nhau?

Test direct chỉ xác minh method trực tiếp gọi action theo thứ tự; không có event được ghi nhận. Với Spring TestContext, `@RecordApplicationEvents` giúp ghi lại những event phát trong test, còn `ApplicationEvents.stream(OrderAccepted.class)` lọc đúng event type.

Test event không chỉ đếm event mà **assert payload** và **trace của listener**. Điều này tránh nhầm “service publish một event” với “handler chắc chắn đã tạo đúng effect”: đó là hai assertion khác nhau.

**Giới hạn:** test dùng context đồng bộ/in-memory. Với listener `@Async`, không nên assert trace ngay sau publish; cần latch/future có timeout và cấu trúc lưu kết quả an toàn luồng. Với transaction hậu commit, cần commit thực tế trước khi assert callback.

## 9. Exception: direct call và event đồng bộ khác nhau thế nào?

### 9.1. Direct call: exception ở điểm gọi rõ ràng

Ví dụ:

```java
orderRepository.accept(orderId);
auditService.record(orderId);
notificationService.request(orderId); // Có thể throw
```

Nếu `auditService.record(...)` ném exception, dòng notification thường không được chạy. Caller thấy exception qua call stack, trừ khi code bắt/chuyển đổi. Nếu cả các thao tác DB cùng tham gia transaction, exception phù hợp có thể khiến transaction rollback. **External side effect đã hoàn tất không tự rollback được**.

### 9.2. @EventListener đồng bộ: exception vẫn có thể quay về publisher

```java
@Order(10)
@EventListener
public void audit(OrderAccepted event) {
    throw new IllegalStateException("Audit failed");
}
```

Đây là snippet minh họa. Với `SimpleApplicationEventMulticaster` đồng bộ mặc định **không gắn `ErrorHandler` đặc biệt**, exception từ listener có thể lan ra `publishEvent(...)`, làm publisher thất bại. Khi đó các listener phía sau có thể chưa được gọi. Nếu subscriber tạo effect ngoài không rollback được trước khi exception xuất hiện, kết quả nghiệp vụ có thể không nhất quán.

**Sự khác biệt thực tế:** direct call thể hiện rõ dependency nào có thể làm caller thất bại. Với event, caller có thể không nhìn thấy đầy đủ tập listener phụ thuộc theo mã nguồn, nhưng vẫn bị lỗi từ chúng nếu chạy đồng bộ.

### 9.3. ErrorHandler của multicaster

Có thể cấu hình một `ApplicationEventMulticaster` với `ErrorHandler` để xử lý exception khác hợp đồng mặc định. Nhưng nếu error handler **nuốt lỗi**, publisher có thể trả về thành công trong khi một listener thất bại. Đây có thể là chính sách hợp lệ cho best-effort monitoring, nhưng không nên dùng để che lỗi trong workflow có hiệu ứng bắt buộc.

Không dùng “bắt mọi exception và tiếp tục” làm giải pháp chung. Cần quyết định trước **business-critical effects**, retry và compensation.

## 10. @Async làm thay đổi những gì?

Đánh dấu listener:

```java
@EnableAsync
@Configuration
class AsyncConfig {
    // Khai báo TaskExecutor được quản lý bởi Spring.
}

@Async("eventExecutor")
@EventListener
public void onAccepted(OrderAccepted event) {
    notificationService.request(event.orderId());
}
```

Đây là **đoạn tích hợp**; cần đặt method trong bean phù hợp, `@EnableAsync` được xử lý bởi cấu hình Spring, bean `eventExecutor` thực sự tồn tại và đã cấu hình. Đoạn trên không phải chương trình chạy độc lập.

Khi `@Async` được kích hoạt qua Spring proxy:

- Listener có thể chạy trên worker thread, **sau khi `publishEvent(...)` trả về**.
- Caller thường không nhận được exception từ một listener `@Async void`; xử lý qua `AsyncUncaughtExceptionHandler` hoặc cơ chế kết quả phù hợp.
- Không thể dựa vào `@Order` để khẳng định **thứ tự hoàn tất** trên nhiều thread.
- `ThreadLocal`, MDC và transaction của publisher **không tự động đi sang worker**.
- Một listener thất bại có thể cần retry riêng; local `@Async` trong RAM **không bền vững qua crash**.
- Kết quả trả về của listener async không được dùng làm cơ chế publish event dẫn xuất; cần publish tường minh.

**Điều này làm hợp đồng khác direct call:** không thể đặt “gửi email phải xong trước khi xác nhận đơn” vào listener async mà không có cơ chế đồng bộ, lỗi và bù trừ riêng.

### TaskDecorator cho logging context

Nếu cần giữ `traceId` trong log, có thể dùng `TaskDecorator` cài/khôi phục MDC khi executor thực thi task. Nhưng **logging context không phải transaction context hoặc security authorization**. Nếu event cần `orderId`, `tenantId`, `correlationId` cho xử lý đáng tin, hãy đưa dữ liệu cần thiết vào payload đã được xác minh.

## 11. Transaction: vấn đề quan trọng hơn cú pháp gọi

### 11.1. Event đồng bộ không mặc nhiên chạy sau commit

Giả sử:

```java
@Transactional
public void acceptOrder(String orderId) {
    orderRepository.accept(orderId);
    publisher.publishEvent(
            new OrderAccepted("evt-100", orderId));
}
```

Với listener `@EventListener` đồng bộ mặc định, callback thường chạy **trong khi transaction còn đang mở**, trước khi commit thành công. Nếu listener gửi email/HTTP ngay, email đã đi nhưng transaction rollback thì tạo ra “ghost notification”. Gọi trực tiếp email trong cùng method cũng có rủi ro giống hệt.

**Khác biệt không nằm ở direct hay event:** vấn đề là **ranh giới transaction** và thời điểm phát side effect ra ngoài.

### 11.2. @TransactionalEventListener(AFTER_COMMIT)

Nếu muốn phản ứng chỉ chạy sau commit thành công:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void onAcceptedAfterCommit(OrderAccepted event) {
    externalGateway.publish(event);
}
```

Đây là snippet tích hợp, cần transaction manager thực sự và bean listener. `@TransactionalEventListener` mặc định dùng `AFTER_COMMIT`. Nếu publish ngoài transaction, listener thường **không chạy** do `fallbackExecution = false`; khi rollback, callback hậu commit cũng không chạy.

**Giới hạn cực kỳ quan trọng:** callback `AFTER_COMMIT` chỉ là callback trong process. Nếu database đã commit nhưng process crash **trước callback hoặc trước broker ACK**, event có thể bị mất; annotation không cung cấp durability.

### 11.3. Ghi DB sau commit và REQUIRES_NEW

Spring lưu ý rằng trong callback after completion, một số resource transaction vẫn có thể còn gắn với thread. Nếu callback cần ghi DB mới, hãy dùng một transaction mới thật sự, ví dụ service riêng với `@Transactional(propagation = Propagation.REQUIRES_NEW)` qua Spring proxy hoặc `TransactionTemplate` cấu hình `PROPAGATION_REQUIRES_NEW`.

Ghi vào DB sau commit **không bù lại được** cửa sổ crash giữa business commit và callback. Đây là lý do mẫu transactional outbox có giá trị.

### 11.4. Outbox để bảo đảm chuyển thông điệp ra ngoài

```text
BUSINESS TRANSACTION
    +--> UPDATE order
    +--> INSERT event_outbox(eventId, payload, PENDING)
    +--> COMMIT cả hai

RELAY WORKER
    +--> poll committed outbox
    +--> send broker/HTTP with retry
    +--> mark SENT after acknowledgment
```

Transactional outbox lưu **ý định publish** cùng business state. Nếu process chết sau commit, row vẫn còn để worker chạy lại. Relay có thể gửi trùng khi crash sau broker ACK trước mark SENT, nên consumer cần idempotency.

Không lấy một `@TransactionalEventListener` ghi outbox **sau commit** rồi coi là một outbox nguyên tử cùng business state; đó là **hai transaction** và vẫn có cửa sổ mất việc.

## 12. Khi nào nên dùng hybrid pattern?

Một cách tổ chức cân bằng:

```text
OrderApplicationService
    |
    +--> direct: validate order
    +--> direct: reserve inventory (nếu bắt buộc)
    +--> direct: persist order + outbox cùng transaction
    |
    +--> local event/hint (optional) để đánh thức relay
             |
             +--> notification projection
             +--> analytics
             +--> audit best-effort
```

Các operation thuộc **invariant** và cần kết quả tức thì được thể hiện rõ bằng direct calls. Event biểu diễn một fact đã xảy ra cho các subscriber bổ sung. Nếu có nhu cầu delivery bền vững ra ngoài, outbox được persist cùng transaction, không phụ thuộc vào việc Spring listener có được gọi trong process hay không.

**Mẫu hybrid không có nghĩa** phát event sau mọi dòng code. Sự kiện cần có ý nghĩa domain, boundary rõ, schema có version và tác động được quản trị.

### Một sự kiện hay nhiều sự kiện?

Ví dụ `OrderAccepted` và `PaymentCaptured` là hai sự việc khác nhau. Không dồn mọi thay đổi vào một `GenericEvent(type, payload)` chỉ để có một API publish chung, vì consumer mất type safety và test khó hơn.

Nếu một nghiệp vụ dẫn tới nhiều facts, mỗi occurrence cần `eventId` riêng, có thể chung `correlationId`, và event dẫn xuất có `causationId` trỏ nguồn tương ứng. Việc này giúp trace fan-out và retry đúng hơn.

## 13. Những điều phải quyết định trước khi chuyển direct sang event

### 13.1. Thành công của caller nghĩa là gì?

Một service direct có thể chỉ trả về khi các dependency đã hoàn tất. Nếu thay bằng async listeners, caller có thể trả “success” trước khi notification hoặc projection sẵn sàng. Nếu API contract từng hứa “đặt hàng xong là có biên nhận”, refactor có thể làm sai hợp đồng.

Hãy xác định **SLA của phản ứng**: đồng bộ trong request, eventual vài giây, hay phải commit/ack ngay.

### 13.2. Ai chịu lỗi?

Khi direct dependency thất bại, caller thường chịu xử lý. Với local event đồng bộ, lỗi listener vẫn có thể lan về publisher. Với async event, lỗi thường thuộc listener và hạ tầng retry/monitor riêng. Không nên thay đổi trách nhiệm lỗi mà không bổ sung dead-letter, retry hoặc status.

### 13.3. Ai sở hữu dữ liệu?

Event payload nên chứa snapshot immutable của dữ liệu cần thiết. Không đưa JPA entity còn attached/lazy, `HttpServletRequest`, transaction object hoặc mutable shared list cho handler async rồi nghĩ mọi dữ liệu luôn còn hợp lệ. Trong event lâu dài, dùng ID/metadata ổn định, kiểm chứng quyền tenant và schema phù hợp.

### 13.4. Ai chịu duplicate?

Một `OrderAccepted(eventId)` có thể được publish lại do retry hoặc được chuyển lại từ outbox/broker. Spring không tự dedupe theo `eventId`. Với effect không được lặp, handler phải có idempotency, ví dụ unique key `(consumer_name, event_id)` và một business unique constraint khi cần.

### 13.5. Fan-out có tạo vòng lặp không?

Một listener có thể publish event dẫn xuất, rồi một listener khác lại publish event gốc. Nếu không có quy tắc chuyển trạng thái/causation, một chuỗi có thể chạy vô hạn. Direct workflow dễ nhìn thấy thứ tự hơn, còn event chain nên có trace graph và giới hạn rõ ràng.

## 14. Test strategy: hai mẫu cần bằng chứng khác nhau

| Câu hỏi | Direct call | Publish event |
| --- | --- | --- |
| Method bắt buộc có được gọi? | Mock/spies/fixture cho dependency | Nếu là điều kiện bắt buộc, cân nhắc direct orchestration |
| Sự kiện đúng loại được phát? | Không áp dụng nếu không phát event | Dùng `@RecordApplicationEvents` hoặc mock publisher |
| Payload đúng? | Assert input truyền tới service | Assert eventId, aggregateId, timestamp, schema, metadata |
| Listener nào xử lý? | Nhìn ở call graph; test effect từng service | Integration test Spring bean listener, condition và type matching |
| Có callback trùng? | Assert số invocation từng dependency | So publish count, listener count, duplicate delivery |
| Exception lan về caller? | Test throw từ dependency | Test listener đồng bộ, ErrorHandler hoặc async behavior riêng |
| Commit/rollback? | Test transaction nghiệp vụ và effect | Test `AFTER_COMMIT` với transaction commit/rollback thực |
| Async hoàn tất chưa? | Khi trực tiếp dùng async cần Future/latch | Không assert ngay sau publish; dùng latch/timeout |
| Crash/restart và durable delivery? | Cần persistence/retry theo workflow | Cần outbox/broker/recovery; Spring event đơn thuần không đủ |

### Vì sao không chỉ mock publisher?

Một unit test:

```java
verify(publisher).publishEvent(captor.capture());
assertEquals("ORD-42", captor.getValue().orderId());
```

Đây là **snippet Mockito**, cần mock publisher/captor được khai báo. Nó chứng minh service đã gọi publish với payload cụ thể, **không** chứng minh Spring đã đăng ký listener, condition được thỏa hay listener tạo effect đúng.

Cần ít nhất một integration test Spring cho đường phát/nhận quan trọng. Phần 8 đã cung cấp một bộ test dùng `@SpringJUnitConfig` và `@RecordApplicationEvents`.

### Vì sao không chỉ assert listener có log?

Logger có thể filter, batch hoặc bị collector thu trùng; một dòng log không phải bằng chứng duy nhất của business effect. Test nên kiểm tra state, outbox row hoặc nội dung recorder an toàn luồng khi cần.

## 15. Hiệu năng và độ phức tạp

Trong cùng một JVM, publish event vẫn cần tạo payload, tìm listener và gọi handler. Với multicaster đồng bộ, tổng thời gian request chịu ảnh hưởng của **toàn bộ listener**. Thêm một listener gửi network request chậm có thể làm chậm publisher dù source service không inject dependency đó.

Direct call có chi phí call method thấp và dễ dự đoán hơn, nhưng **mức chi phí tổng thể vẫn do nghiệp vụ phía trong** quyết định, không phải chỉ một call instruction.

### Không tối ưu theo cảm giác

Cần đo:

- Độ trễ request khi có 1/5/20 listener đồng bộ.
- CPU và allocation khi publish event tần suất cao.
- Số task queue/backpressure khi bật async.
- Tỷ lệ exception, callback timeout, retry, duplicate.
- Độ trễ từ business commit tới effect hoàn tất.
- Ảnh hưởng của một subscriber chậm lên các subscriber khác.

Nếu fan-out lớn và effect cần chạy độc lập, có thể nên chuyển sang outbox + broker hoặc job queue thay vì cố xử lý mọi thứ bằng local application events.

## 16. Khác biệt về quan sát và debug

Direct call thường dễ trace bằng stack và line number. Với event, “ai nhận event này?” trở thành câu hỏi tìm subscriber runtime. Logging nên có:

```text
eventType
eventId
aggregateId
correlationId
causationId
publisherMethod
listenerBean
listenerMethod
transactionPhase
threadName
processingAttempt
processingStatus
```

Một event được publish một lần có thể có ba dòng `LISTENER_START` vì ba bean; đây là fan-out đúng. Nhưng cùng bean nhận cùng eventId nhiều lần có thể do publish lặp/retry hoặc nhiều registration. Đừng chỉ đếm dòng log rồi khẳng định framework tự gọi trùng.

Với listener async, MDC/trace context thường không tự propagate; `TaskDecorator` hoặc cơ chế Micrometer Context Propagation có thể giúp observability nhưng không thay transaction/security context.

### Một vài hướng debug thực tế

1. Log tại **nguồn `publishEvent(...)`** với invocation ID.
2. Log ở **đầu listener** với bean name, eventId và thread.
3. Phân biệt publish time, listener start và listener finish.
4. Kiểm tra lỗi/transaction phase, không chỉ output cuối.
5. Kiểm tra mỗi module có bao nhiêu listener bean thật trong context.
6. Nếu có context cha/con, kiểm tra nguồn context; event ở child có thể được chuyển lên parent.
7. Khi có broker/outbox, thêm delivery attempt và message offset/claim ID.
8. Kiểm tra effect thực tế trong DB hoặc hệ thống ngoài, không chỉ log.

## 17. Các lỗi phổ biến

1. **Nghĩ publish event tự chạy async.** Spring mặc định gọi listener thường đồng bộ.
2. **Dùng event thay direct call cho bước bắt buộc trả kết quả.** `publishEvent(...)` không là request-response API.
3. **Tưởng event tách luôn transaction.** Listener đồng bộ có thể tham gia transaction nguồn.
4. **Gọi email/HTTP trong listener đồng bộ trước commit.** Rollback có thể để lại ghost effect.
5. **Chọn `AFTER_COMMIT` rồi tưởng event không thể mất.** Callback trong RAM vẫn có cửa sổ crash.
6. **Cho rằng `@Order` đảm bảo completion order của async listeners.** Không.
7. **Cho rằng listener mới thêm không ảnh hưởng caller.** Listener đồng bộ chậm/lỗi vẫn ảnh hưởng publisher.
8. **Bỏ qua exception path khi refactor từ direct sang event.** Caller có thể thấy lỗi khác hẳn.
9. **Dùng `@Async void` rồi nghĩ lỗi sẽ quay về controller.** Cần error handler/monitoring riêng.
10. **Bắt exception listener rồi nuốt để “giảm coupling”.** Có thể che failure nghiêm trọng.
11. **Giữ entity mutable/lazy trong event.** Async handler có thể thấy state sai hoặc persistence context đóng.
12. **Truyền `SecurityContext`/MDC như nguồn dữ liệu nghiệp vụ.** Không bền vững qua task/process.
13. **Publish hai lần cùng eventId rồi mong Spring dedupe.** Framework không làm việc này.
14. **Tạo vòng lặp event dẫn xuất.** Fan-out có thể gây đệ quy hoặc backlog vô hạn.
15. **Không có test integration Spring cho event type.** Mock publisher chưa đủ.
16. **Đếm mọi ApplicationEvent trong test.** Event context lifecycle có thể làm test sai; lọc theo class.
17. **Không tách hiệu ứng bắt buộc với phản ứng bổ sung.** Event làm contract thành công mơ hồ.
18. **Cho rằng in-process event cũng là broker durable.** Restart có thể mất task/ callback pending.
19. **Đưa quá nhiều field không ổn định vào event schema.** Consumer bị coupling ngầm.
20. **Đo benchmark giữa direct với event nhưng không cùng workload.** Kết luận không có giá trị.
21. **Làm một mega-listener cho tất cả event.** Mất lợi thế module độc lập và rối type/condition.
22. **Dùng event như command bus không có routing/ack thích hợp.** Không bảo đảm exactly-one consumer.
23. **Không tính tác động của context hierarchy.** Parent và child có thể nhận những event liên quan.
24. **Dùng cùng một eventId mới khi tạo occurrence khác.** Consumer idempotency có thể chặn nhầm nghiệp vụ.

## 18. Ma trận quyết định thực hành

| Tình huống | Ưu tiên | Lý do |
| --- | --- | --- |
| Validate input/permission trước khi ghi | **Direct** | Phải trả lỗi rõ ràng, không phải sự kiện đã xảy ra |
| Reserve inventory bắt buộc trước khi xác nhận đơn | **Direct / orchestrator** | Caller cần biết thành công |
| Tính thuế để trả kết quả API | **Direct** | Cần giá trị trả về |
| Thêm audit phụ trợ trong cùng ứng dụng | **Event**, nếu failure policy phù hợp | Tách subscriber khỏi source |
| Analytics/metric không phải điều kiện thành công | **Event** | Fan-out dễ mở rộng |
| Nhiều module cùng phản ứng `OrderAccepted` | **Event** | Publisher không cần biết danh sách listener |
| Gửi email sau commit, chấp nhận best-effort | `@TransactionalEventListener(AFTER_COMMIT)` | Gắn thời điểm với commit, nhưng có thể mất khi crash |
| Bắt buộc gửi event đến broker sau commit | **Transactional outbox + relay** | Tách dual write, lưu job bền vững |
| Bên nhận cần phản hồi đồng bộ để quyết định | **Direct request-response** | Event bus không có tổng hợp return value |
| Workflow nhiều service, phải có bù trừ | **Saga/orchestrator + events** | Cần state machine và compensation rõ ràng |
| Replay các event để rebuild projection | **Event + durable store** | Local event đơn thuần không lưu lịch sử |
| Tính toán CPU cực nhỏ tần suất rất cao | **Đo trước; thường direct đơn giản hơn** | Không thêm dispatch overhead nếu không cần decoupling |

### Quy tắc chọn nhanh

Nếu thiếu bước B thì **A không được thành công**, hãy làm quan hệ B **tường minh** (direct/orchestration). Nếu A đã hoàn tất một sự thật và các module khác **có quyền phản ứng độc lập** theo SLA riêng, event có ích. Nếu event phải vượt process hoặc tồn tại qua crash, **đừng chỉ dùng Spring in-process event**.

## 19. Checklist trước khi refactor

- [ ] Xác định bước nào thuộc **business invariant**, bước nào chỉ là subscriber phụ.
- [ ] Xác định contract thành công của API và chỗ xử lý exception.
- [ ] Đã kiểm tra Spring multicaster hiện tại chạy đồng bộ hay custom async.
- [ ] Không giả định `publishEvent(...)` là một queue bền vững.
- [ ] Các listener là Spring bean, đăng ký đúng event type.
- [ ] Nếu dùng `@Order`, hiểu giới hạn với async và failure.
- [ ] Nếu listener có return value event dẫn xuất, kiểm soát vòng lặp.
- [ ] Event đặt tên theo fact và payload có ID/metadata bất biến.
- [ ] Listener chỉ đọc dữ liệu cần thiết, không giữ mutable entity/request.
- [ ] Cân nhắc transaction: đồng bộ trước commit, AFTER_COMMIT hay outbox.
- [ ] Không gửi external effect trước business commit khi không được tạo ghost event.
- [ ] Event cần durability có outbox/broker/retry/idempotency phù hợp.
- [ ] Có test direct action, publish count, payload, listener effect, exception và transaction outcome.
- [ ] Async tests dùng latch/future có timeout, không đoán thời gian bằng sleep.
- [ ] Không có listener trùng chức năng gây double effect không kiểm soát.
- [ ] Có metrics và log theo `eventId`, listener name, attempt và effect ID.
- [ ] Đã đo độ trễ và backlog nếu có nhiều subscriber.
- [ ] Quy tắc bảo mật/tenant ID được thực thi tại nơi tạo và xử lý effect.

**Kết luận:** **gọi trực tiếp** làm rõ trách nhiệm và dependency khi một bước cần **kết quả bắt buộc**; **publish event** giúp thông báo một sự thật cho nhiều subscriber với coupling yếu hơn ở mã nguồn. Tuy nhiên, với Spring Framework, **event thường vẫn được xử lý đồng bộ theo mặc định** và không tự có transaction isolation, retry hoặc durability. Thiết kế vững thường kết hợp direct orchestration cho core workflow, event cho phản ứng bổ sung, và **transactional outbox** khi cần gửi dữ liệu ra ngoài sau commit một cách đáng tin.

## Tài liệu tham khảo

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework 6.2 — EventListener API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — SimpleApplicationEventMulticaster API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
