# Listener bị gọi nhiều lần trong Spring Framework Application Events

## 1. Triệu chứng và câu hỏi chẩn đoán đầu tiên

Một hệ thống quản lý đơn hàng phát sự kiện `OrderAccepted` để cập nhật thống kê và gửi thông báo. Trong log, cùng một dòng “Handling OrderAccepted” xuất hiện hai hoặc ba lần, đôi khi làm gửi hai email hoặc ghi trùng một bản audit. Nhiều người lập tức cho rằng “Spring tự gọi listener hai lần”. Trên thực tế, phải phân biệt **số lần event được phát**, **số listener/method phù hợp được đăng ký**, **sự lan truyền giữa các ApplicationContext**, và **những lần retry/replay thực sự xảy ra**.

Một lần `ApplicationEventPublisher.publishEvent(event)` có thể phân phối event đến **nhiều listener hợp lệ**. Ngược lại, một listener được đăng ký một lần có thể nhận **nhiều lần publish** của cùng một payload hoặc cùng `eventId`. Cả hai trường hợp đều có thể làm log tăng, nhưng nguyên nhân và cách sửa khác nhau.

**Không có quy tắc “mỗi loại event chỉ có một listener” hoặc “mỗi eventId chỉ được xử lý một lần” trong Spring Application Events.** Framework được thiết kế để phân phối event đến các listener phù hợp, không phải một hệ thống tự khử trùng thông điệp.

Trước khi chỉnh annotation hoặc xóa listener, hãy trả lời:

1. Có **bao nhiêu lời gọi publish** tương ứng với sự kiện đang xét?
2. Có **bao nhiêu bean/method listener thực sự nhận loại event đó**?
3. Có **bao nhiêu ApplicationContext** và event có lan từ con lên cha không?
4. Listener có **phát thêm event**, trả về event, hay khởi động một nhánh workflow mới?
5. Có **retry, replay, lịch chạy lại, redelivery từ broker/outbox** hoặc restart không?
6. Hai dòng log có chứng minh **hai callback độc lập**, hay chỉ là một callback được log ở nhiều lớp/interceptor?

Chủ đề thuộc nhóm **Chẩn đoán sự cố** trong Spring Framework Application Events. Mục tiêu là tìm đúng nguồn gây “gọi nhiều lần”, không dùng thủ thuật che log hoặc bỏ qua event hợp lệ.

## 2. Một event, nhiều callback: sơ đồ phân phối

Với multicaster mặc định đồng bộ:

```text
OrderService
    |
    | publishEvent(OrderAccepted(evt-100))
    v
ApplicationEventMulticaster
    |
    +--> AuditListener.onAccepted(evt-100)
    |
    +--> EmailListener.onAccepted(evt-100)
    |
    +--> ProjectionListener.onAccepted(evt-100)
```

**Một lần publish, ba callback khác nhau là hành vi đúng** nếu ba listener đều đăng ký cho `OrderAccepted`. Việc cả ba log cùng `eventId` không có nghĩa chính cùng một listener bị gọi ba lần.

Ngược lại:

```text
OrderService
    |
    +--> publishEvent(OrderAccepted(evt-100))
    |          |
    |          +--> AuditListener.onAccepted(evt-100)
    |
    +--> publishEvent(OrderAccepted(evt-100))
               |
               +--> AuditListener.onAccepted(evt-100)
```

**Hai lần publish, một listener, hai callback**. Nếu cùng `eventId` bị phát lại, Spring không có cơ chế tự nhận diện và bỏ sự kiện thứ hai. Ở môi trường có retry, điều này có thể hoàn toàn hợp lệ về mặt delivery nhưng phải xử lý idempotency ở tầng nghiệp vụ.

Một trường hợp thứ ba:

```text
Một lần publish OrderAccepted(evt-200)
    |
    v
ApplicationEventMulticaster
    |
    +--> AuditListener bean A: handle(evt-200)
    |
    +--> AuditListener bean B: handle(evt-200)
```

Ở đây **hai bean listener cùng loại** được đăng ký, ví dụ vì cấu hình khai báo hai `@Bean` hoặc một class được tạo bằng nhiều đường. Một event chỉ publish một lần nhưng tác dụng phụ “audit” có thể bị thực hiện hai lần nếu hai bean dùng cùng nghiệp vụ.

Vì vậy **callback count** không đủ để kết luận **publish count**, và **publish count** cũng không tự cho biết số lần tác dụng phụ xảy ra.

## 3. Phân loại nhanh theo dấu hiệu quan sát

| Dấu hiệu | Giả thuyết cần kiểm tra | Bằng chứng nên thu thập |
| --- | --- | --- |
| Cùng `eventId`, cùng bean/method, nhiều callback | Event được publish lại, listener đăng ký qua nhiều cơ chế, hoặc replay | Log tại điểm publish và điểm bắt đầu listener |
| Cùng `eventId`, nhiều bean/method | Nhiều subscriber hợp lệ hoặc bean được tạo trùng | Bean name, class, context ID và method |
| Cùng loại event, khác `eventId` | Hai sự việc khác nhau hoặc eventId bị sinh lại khi retry | Tác vụ nguồn, business key, correlation ID |
| Cùng event lifecycle như `ContextRefreshedEvent`, khác context | Context cha/con hoặc nhiều context được refresh | `event.getApplicationContext()` |
| Listener gọi lại chính event nhận được | Vòng lặp/chaining, return event hoặc publish tường minh | Causation ID và call path |
| Chỉ trùng khi chạy async | Hai task được submit, xử lý song song hoặc retry | Task ID, thread, attempt, queue |
| Chỉ xuất hiện sau restart/deploy | Startup mới hoặc khôi phục message chưa ack | Process/instance ID, startup time, broker offset |
| Log lặp nhưng counter side effect không tăng | Log ở interceptor/trace khác nhau hoặc log aggregator trùng | Message ID, logger name và callback entry |

**Nguyên tắc:** một dòng log đơn lẻ không chứng minh Spring gọi một phương thức hai lần. Phải gắn dấu tại **điểm publish** và **điểm bắt đầu callback**, rồi so sánh cùng event occurrence.

## 4. Bước 1 — kiểm tra publisher có phát trùng không

### 4.1. Hai đường code cùng publish một event

Phản ví dụ:

```java
@RestController
public class OrderController {
    private final OrderService service;
    private final ApplicationEventPublisher publisher;

    // Constructor injection được lược bớt.
    @PostMapping("/orders/{id}/accept")
    public void accept(@PathVariable String id) {
        service.accept(id); // service đã publish OrderAccepted.
        publisher.publishEvent(new OrderAccepted(
                "evt-100", id)); // Publish lặp lần nữa.
    }
}
```

Đây là **đoạn minh họa**, thiếu constructor và định nghĩa service/event nên không phải mã chạy độc lập. Nó cho thấy lỗi sở hữu trách nhiệm: controller và service đều publish cùng sự việc. Chỉ **một lớp được giao trách nhiệm tạo và phát domain event** sau khi trạng thái nghiệp vụ thực sự thay đổi.

### 4.2. Mỗi invocation service lại publish

Một endpoint có thể bị gọi hai lần do người dùng double click, HTTP client retry, network timeout hoặc hai message cùng được giao cho handler. Khi đó service cũng chạy hai lần; việc Spring phân phối hai lần là đúng với hai lần publish.

Nếu operation có cùng business key, cần phân biệt:

- **Hai ý định nghiệp vụ hợp lệ:** ví dụ hai thanh toán riêng cho cùng đơn; không được chặn mù bằng `orderId`.
- **Một yêu cầu bị gửi lại:** nên có request/idempotency key ổn định và xử lý trùng tại nơi tạo thay đổi nghiệp vụ.
- **Một event đã tạo được replay:** giữ `eventId` của occurrence gốc khi phát lại, để consumer nhận biết đúng trùng.

### 4.3. Log ngay trước lời gọi publish

Mẫu tích hợp:

```java
log.info("PUBLISH type={} eventId={} orderId={} source={}",
        OrderAccepted.class.getSimpleName(),
        event.eventId(),
        event.orderId(),
        "OrderService.accept");
publisher.publishEvent(event);
```

Đoạn này cần `log`, `publisher` và `event` đã được khai báo trong service. Ở hệ thống lớn, có thể thêm `correlationId`, `causationId`, `instanceId` và ID của một lần gọi nguồn. **Không đưa thông tin nhạy cảm hoặc toàn bộ entity vào log.**

Lưu ý: `publishEvent(...)` được gọi không đồng nghĩa mọi listener async đã hoàn thành; log “PUBLISH” chỉ chứng minh lời gọi publish xảy ra tại điểm đó. Cần log bắt đầu/kết thúc listener riêng.

## 5. Bước 2 — tìm listener/bean bị đăng ký theo nhiều đường

Spring nhận listener qua những cơ chế phổ biến:

- `@EventListener` trên phương thức của Spring bean.
- Class triển khai `ApplicationListener<E>`.
- Listener được thêm tường minh vào multicaster hoặc context.
- Nhiều bean khác nhau có method lắng nghe cùng kiểu event.
- Listener được đăng ký vào nhiều context trong một hierarchy.

Một lỗi cấu hình dễ thấy là vừa đánh dấu class `@Component`, vừa tạo thêm **một instance khác** bằng `@Bean`:

```java
@Component
public class AuditListener {
    @EventListener
    public void onAccepted(OrderAccepted event) {
        // Cùng nghiệp vụ audit.
    }
}

@Configuration
class ExtraConfig {
    @Bean
    AuditListener auditListenerAgain() {
        return new AuditListener();
    }
}
```

**Đây là mẫu minh họa có khả năng tạo hai bean listener**, tùy phạm vi component scan và cấu hình context. Nếu cả hai bean đều thực sự được Spring đăng ký, một event có thể gọi hai method tương ứng. Không nên kết luận chỉ dựa vào việc nhìn thấy hai annotation; cần xác minh danh sách bean thật trong context.

Một dạng khác: một bean đồng thời triển khai `ApplicationListener<OrderAcceptedEvent>` và có thêm một phương thức `@EventListener` xử lý chính `OrderAcceptedEvent`, làm tác dụng phụ tương tự ở **hai callback khác nhau**. Đây là hai cơ chế xử lý mà chính ứng dụng đã khai báo, không phải Spring lặp ngẫu nhiên cùng một method.

### 5.1. Kiểm tra bằng bean name, không chỉ bằng class name

Khi phát hiện hai dòng log giống nhau, thêm:

```java
log.info("Listener bean={} class={} eventId={}",
        beanName,
        getClass().getName(),
        event.eventId());
```

Đây là snippet tích hợp. `beanName` có thể được cung cấp từ cấu hình hoặc `BeanNameAware`; không dùng `getClass().getSimpleName()` như một định danh duy nhất vì hai bean khác nhau có thể có cùng class. Với Spring AOP, class runtime có thể là proxy; nếu cần hiểu loại method, dùng bean definition và target class tương ứng trong công cụ debug.

Trong khi chẩn đoán, hãy ghi nhận **mỗi bean/method** một lần theo cặp tên bean và method, thay vì gộp toàn bộ log theo type. Điều này giúp phân biệt “một bean được gọi hai lần” với “hai bean được gọi một lần”.

### 5.2. Kiểm tra cấu hình scan/import

Đối chiếu phạm vi `@ComponentScan`, `@Import`, auto-configuration, `@Bean` và những module tạo listener thủ công. Không phải mọi khai báo trùng class đều tạo bean trùng: Spring có thể nhận diện cấu hình lặp, ghi đè bean name hoặc tránh đăng ký trùng theo trường hợp cụ thể. **Bằng chứng quyết định vẫn là bean thực tế và số method được đăng ký.**

Không nên sửa bằng cách xóa ngẫu nhiên một `@Component` khi chưa biết bean đó có được dùng ở context khác hoặc bởi chức năng khác không.

## 6. Ví dụ hoàn chỉnh: hai nguyên nhân khác nhau nhưng cùng hai callback

Chương trình Java 17 + Spring Framework 6.2 dưới đây tái hiện hai trường hợp bằng **hai ApplicationContext độc lập**:

**Tình huống A:** chỉ một listener bean, nhưng publisher phát `OrderAccepted` **hai lần**.

**Tình huống B:** publisher phát **một lần**, nhưng context chứa **hai listener bean** của cùng class, được đặt tên `audit-one` và `audit-two`.

Cả hai tình huống đều tạo hai callback. Ta in thêm **tập tên handler** để chứng minh nguyên nhân khác nhau.

### 6.1. Cấu trúc dự án

```text
duplicate-listener-diagnosis/
├── pom.xml
└── src/main/java/example/DuplicateListenerDemo.java
```

### 6.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>duplicate-listener-diagnosis</artifactId>
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
                <configuration>
                    <mainClass>example.DuplicateListenerDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.3. Tệp src/main/java/example/DuplicateListenerDemo.java

```java
package example;

import java.util.ArrayList;
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class DuplicateListenerDemo {

    public record OrderAccepted(String eventId, String orderId) {}

    // Trace chỉ dùng trong các context chạy đồng bộ của demo.
    public static final class Trace {
        private final List<String> entries = new ArrayList<>();

        public void record(String handlerName, String eventId) {
            entries.add(handlerName + ":" + eventId);
        }

        public int callbackCount() {
            return entries.size();
        }

        public List<String> handlerNames() {
            return entries.stream()
                    .map(s -> s.substring(0, s.indexOf(':')))
                    .distinct()
                    .sorted()
                    .toList();
        }
    }

    // Hai instance của cùng class là hai listener khác nhau.
    public static class AuditListener {
        private final String name;
        private final Trace trace;

        public AuditListener(String name, Trace trace) {
            this.name = name;
            this.trace = trace;
        }

        @EventListener
        public void onAccepted(OrderAccepted event) {
            trace.record(name, event.eventId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class OneListenerConfig {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public AuditListener auditOne(Trace trace) {
            return new AuditListener("audit-one", trace);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class TwoListenersConfig {

        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public AuditListener auditOne(Trace trace) {
            return new AuditListener("audit-one", trace);
        }

        @Bean
        public AuditListener auditTwo(Trace trace) {
            return new AuditListener("audit-two", trace);
        }
    }

    public static void main(String[] args) {
        // Case A: 2 publishes -> 2 callbacks from ONE listener.
        try (var context = new AnnotationConfigApplicationContext(
                OneListenerConfig.class)) {
            Trace trace = context.getBean(Trace.class);

            context.publishEvent(
                    new OrderAccepted("evt-100", "ORD-42"));
            context.publishEvent(
                    new OrderAccepted("evt-100", "ORD-42"));

            System.out.println(
                    "A publishes=2 callbacks=" + trace.callbackCount());
            System.out.println(
                    "A handlers=" + trace.handlerNames());
        }

        // Case B: 1 publish -> 2 callbacks from TWO listener beans.
        try (var context = new AnnotationConfigApplicationContext(
                TwoListenersConfig.class)) {
            Trace trace = context.getBean(Trace.class);

            context.publishEvent(
                    new OrderAccepted("evt-200", "ORD-43"));

            System.out.println(
                    "B publishes=1 callbacks=" + trace.callbackCount());
            System.out.println(
                    "B handlers=" + trace.handlerNames());
        }
    }
}
```

### 6.4. Chạy

Dùng JDK 17+ và Maven trong thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java
```

**Bốn dòng do chương trình in**, không tính log Maven/Spring nếu có:

```text
A publishes=2 callbacks=2
A handlers=[audit-one]
B publishes=1 callbacks=2
B handlers=[audit-one, audit-two]
```

### 6.5. Giải thích kết quả

- `OneListenerConfig` có một bean `AuditListener` với tên được ghi trong trace là `audit-one`. `main` chủ động gọi `publishEvent(...)` hai lần với cùng `eventId=evt-100`, do đó `trace.callbackCount() == 2`.
- `TwoListenersConfig` có hai bean khác nhau `auditOne` và `auditTwo`; mỗi bean có một method `@EventListener` nhận `OrderAccepted`. `main` chỉ publish `evt-200` một lần, nhưng hai bean đều phù hợp nên `trace.callbackCount() == 2`.
- `handlerNames()` lấy tên handler từ các entry, gọi `distinct()` và `sorted()`, nên kết quả in có thứ tự ổn định ngay cả khi thứ tự dispatch giữa các listener thay đổi.
- Hai context được tạo và đóng tuần tự, không chia sẻ bean `Trace`. Vì vậy counter của case A không làm nhiễu case B.
- Event `OrderAccepted` là Java record; Spring chấp nhận record trực tiếp qua `publishEvent(Object)` và chuyển payload tới `@EventListener`.
- Ví dụ dùng multicaster đồng bộ mặc định, không `@Async`, không transaction, không broker và không retry. Nhờ đó không cần `Thread.sleep` và có thể đọc trace ngay sau publish.

**Bài học rút ra:** cùng một thông báo “callbacks=2” có thể có hai lời giải hoàn toàn khác nhau. Trước khi sửa, luôn ghi nhận **publish count** và **handler identity**.

### 6.6. Cách mở rộng để in từng callback

Thay vì chỉ xem tổng, có thể thêm trong `AuditListener.onAccepted`:

```java
System.out.println(
        "listener=" + name
                + " eventId=" + event.eventId()
                + " thread=" + Thread.currentThread().getName());
```

Đây là đoạn code thay thế một phần thân method trong chương trình, không phải bài chạy độc lập. Với bất đồng bộ, thêm `instanceId` và `contextId` để phân biệt các worker/process; không chỉ dựa vào tên thread như một khóa duy nhất.

## 7. Bước 3 — kiểm tra ApplicationContext cha/con

Spring có thể tổ chức context theo hierarchy, ví dụ parent chứa bean dùng chung và child chứa phần web/module. Event được phát trong **child context** có thể được **chuyển lên ancestor context** theo cơ chế Spring.

```text
Parent ApplicationContext
    |
    +--> ParentListener (đăng ký tại parent)
    ^
    | event từ child được propagate lên
    |
Child ApplicationContext
    |
    +--> ChildListener (đăng ký tại child)
    |
    +<-- publishEvent(...)
```

Một lần publish ở child có thể khiến **listener của child** và **listener của parent** cùng được gọi. Đây không phải Spring “nhân bản task” sai; hai context có những subscription khác nhau. Nếu cùng chức năng audit/email được cài ở cả hai tầng, hiệu ứng nghiệp vụ có thể bị thực hiện hai lần.

**Đối với event vòng đời** như `ContextRefreshedEvent` hoặc `ContextClosedEvent`, event thường chứa context nguồn; listener của parent có thể thấy cả event của child lẫn event của parent. Nếu chỉ xử lý event thuộc chính context mình:

```java
@Component
public class LocalContextObserver {
    private final ApplicationContext ownContext;

    public LocalContextObserver(ApplicationContext ownContext) {
        this.ownContext = ownContext;
    }

    @EventListener
    public void onRefreshed(ContextRefreshedEvent event) {
        if (event.getApplicationContext() != ownContext) {
            return; // Không xử lý event đến từ descendant context.
        }

        // Logic chỉ áp dụng cho context của bean này.
    }
}
```

Đây là đoạn tích hợp cần import `@Component`, `ApplicationContext`, `@EventListener` và `ContextRefreshedEvent`.

**Giới hạn:** record payload như `OrderAccepted` không có sẵn `getApplicationContext()`. Nếu cần lọc các event nghiệp vụ theo nguồn, hãy mang metadata phù hợp trong payload hoặc bố trí listener ở đúng context, không ép cast record thành `ApplicationContextEvent`.

### Phân biệt với nhiều lần refresh/startup

Một ứng dụng có thể khởi tạo/đóng nhiều context qua test suite, reload hoặc deploy. Các event vòng đời phát ra ở mỗi lần tạo/refresh context là những **occurrence khác nhau**, kể cả khi log cùng loại `ContextRefreshedEvent`. Đừng gom chúng thành “cùng một event bị gọi lại” nếu context ID và thời điểm khác nhau.

## 8. Bước 4 — phát event trong listener hoặc trả về event

Spring hỗ trợ việc một `@EventListener` **đồng bộ** trả về một event mới. Nếu method trả về `Collection` hoặc array, từng phần tử được publish như các event riêng.

Ví dụ:

```java
@EventListener
public InventoryRequested onAccepted(OrderAccepted event) {
    return new InventoryRequested(event.orderId());
}
```

Đây là đoạn minh họa cần record `InventoryRequested`. Khi `OrderAccepted` được nhận, Spring tự công bố `InventoryRequested`. Nếu một listener khác nhận `InventoryRequested` và tiếp tục phát `OrderAccepted`, ứng dụng có thể tạo **chuỗi lặp**.

```text
OrderAccepted
    -> InventoryRequested
        -> OrderAccepted
            -> InventoryRequested
                -> ...
```

Trong xử lý đồng bộ, vòng lặp vô hạn có thể làm tăng độ sâu lời gọi, cuối cùng gây `StackOverflowError`. Với async, nó có thể thành fan-out vào queue, gây quá tải tài nguyên.

### 8.1. Cần phân biệt event gốc với event dẫn xuất

Nên đặt metadata:

```java
public record EventMetadata(
        String eventId,
        String correlationId,
        String causationId
) {}
```

- `eventId`: định danh occurrence cụ thể.
- `correlationId`: nhóm một workflow.
- `causationId`: event cha trực tiếp gây ra event hiện tại.

Nếu log thấy chuỗi `evt-1 -> evt-2 -> evt-1` hoặc nhiều event mới cùng `causationId`, cần kiểm tra luồng phát tiếp. Đừng suy luận quan hệ nhân quả từ `ApplicationEvent.getSource()` vì source của framework không phải định danh event cha nghiệp vụ.

### 8.2. Khi nào trả về event không tự phát tiếp?

Với listener `@Async`, Spring **không hỗ trợ** việc publish event tiếp theo thông qua return value. Nếu cần tạo event dẫn xuất từ listener async, phải inject `ApplicationEventPublisher` và gọi `publishEvent(...)` tường minh.

Cả hai cơ chế vẫn có thể tạo nhiều callback hợp lệ; khác nhau ở điểm publish và thread thực thi. Nếu mỗi listener gọi `publishEvent` cùng một event hai lần, hãy tìm lỗi trong logic chứ không chỉ trong annotation.

## 9. Bước 5 — listener có kiểu quá rộng hoặc nhiều method trùng nghiệp vụ

Một ứng dụng có thể có:

```java
@EventListener
public void onAnyDomainEvent(DomainEvent event) {
    auditService.write(event);
}

@EventListener
public void onOrderAccepted(OrderAccepted event) {
    auditService.write(event);
}
```

Đây là snippet minh họa; `DomainEvent` cần là supertype/interface được `OrderAccepted` triển khai, và `auditService` là dependency được inject. Với `OrderAccepted`, **cả hai method đều có thể khớp**; nếu cùng gọi `auditService.write`, audit bị thực hiện hai lần.

Cần hỏi: “Đó là hai handler được thiết kế để làm hai việc khác nhau, hay hai đường cùng thực hiện cùng effect?”

- Nếu một method dùng cho logging chung và một method gửi email, cả hai được gọi là đúng.
- Nếu cả hai đều ghi cùng bản audit mà không có cơ chế chống trùng, đó là lỗi thiết kế chức năng.
- Có thể dùng typed handler cụ thể hoặc điều kiện lọc phù hợp, nhưng phải giữ hành vi bắt buộc của các loại event khác.

### Condition không phải công cụ deduplication

`@EventListener(condition = "...")` có thể lọc event theo một biểu thức SpEL, nhưng nó **không lưu lịch sử eventId đã xử lý**, không giải quyết retry và không làm các consumer ngoài xử lý đúng một lần.

Không dùng một điều kiện `eventId != null` để xem như chống trùng: tất cả lần publish trùng đều có eventId hợp lệ và vẫn vượt qua condition.

### @Order không thay đổi số lần gọi

`@Order` điều chỉnh thứ tự invoke những listener phù hợp trong phạm vi hỗ trợ, **không chọn một listener duy nhất**. Thêm `@Order(1)` vào một handler không làm handler khác biến mất và không bảo đảm thứ tự hoàn tất của những task async.

## 10. Bước 6 — transaction, retry và redelivery

### 10.1. @TransactionalEventListener không tự chống trùng

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` đăng ký callback gắn với transaction. Theo mặc định, listener này được kích hoạt sau khi transaction **đã commit**; nếu publish ngoài transaction thì thường không chạy do `fallbackExecution = false`.

Nhưng nếu code gọi `publishEvent(event)` **hai lần trong cùng transaction**, Spring có thể đăng ký hai lần callback hậu commit. Cả hai callback có thể chạy sau commit; `AFTER_COMMIT` chỉ quyết định **thời điểm**, không tự gộp các occurrence có cùng `eventId`.

Ví dụ tích hợp:

```java
@Transactional
public void payOrder(String orderId) {
    // Cập nhật DB cho nghiệp vụ.
    publisher.publishEvent(new PaymentCaptured("evt-77", orderId));
    publisher.publishEvent(new PaymentCaptured("evt-77", orderId));
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onPayment(PaymentCaptured event) {
    // Có thể chạy 2 lần vì publish 2 lần.
}
```

Đây là snippet mô phỏng cần import, service, transaction manager thật và record `PaymentCaptured`. Không tự kết luận rằng `REQUIRES_NEW` hoặc đổi phase sẽ tự khử trùng.

### 10.2. Retry và transaction rollback

Nếu một service được retry **cả method**, nó có thể publish event ở từng attempt. Với `@EventListener` đồng bộ, listener có thể thực thi trước khi transaction bị rollback, gây tác dụng phụ ngoài DB. Với `@TransactionalEventListener(AFTER_COMMIT)`, attempt rollback không kích hoạt callback hậu commit; **nhưng attempt commit vẫn có thể publish trùng nếu nghiệp vụ phát nhiều lần**, hoặc thao tác được gọi lại sau lần commit thành công.

Hãy lưu ý:

- Exception ở listener đồng bộ có thể lan ngược caller và ảnh hưởng transaction hiện tại.
- Exception ở `@Async void` có thể được xử lý qua `AsyncUncaughtExceptionHandler`, không tự quay về publisher.
- `AFTER_COMMIT` không bảo đảm callback được retry sau crash.
- Một số transaction resource vẫn có thể còn bound trong callback sau commit; khi ghi DB mới từ listener, dùng transaction mới phù hợp (ví dụ `REQUIRES_NEW` qua proxy hoặc `TransactionTemplate`).

### 10.3. Broker và transactional outbox

Nếu sự kiện bắt nguồn từ Kafka, RabbitMQ, scheduler, outbox poller hoặc một job được retry, event có thể được chuyển lại khi:

- Handler đã thực hiện effect nhưng chưa ack thành công.
- Worker chết sau khi gửi tới dịch vụ ngoài nhưng trước khi đánh dấu done.
- Timeout khiến upstream không biết phía nhận đã xử lý.
- Nhiều worker cùng claim một việc chưa được khóa đúng.
- Replay một đoạn lịch sử để khôi phục read model.

Spring Application Events tự thân là hạ tầng in-process, **không tự lưu event để replay**. Nhưng ứng dụng có thể nhận message từ broker rồi chuyển nó thành `publishEvent(...)`, tạo ra những lần publish lại trong local context. Vì vậy phải theo dõi **message ID/offset/deliveryAttempt ở ranh giới nguồn**.

## 11. Chống xử lý trùng ở tầng nghiệp vụ: idempotency

Nếu side effect không được phép chạy hai lần cho cùng một event occurrence, đừng chỉ cố khiến log listener “xuất hiện một lần”. Cần thiết kế **idempotent effect**.

### 11.1. Khóa định danh ổn định

Một event có thể chứa:

```java
public record PaymentCaptured(
        String eventId,
        String paymentId,
        String orderId,
        String correlationId
) {}
```

Khóa idempotency theo handler thường là:

```text
(consumer_name, event_id)
```

Ví dụ `(invoice-creator, evt-77)` và `(email-sender, evt-77)` là **hai consumer khác nhau**, mỗi consumer được xử lý event một lần theo chính sách riêng. Không dùng duy nhất `eventId` trên toàn bộ ứng dụng nếu điều đó vô tình chặn các subscriber hợp lệ khác.

### 11.2. Ràng buộc unique trong database

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(100) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Một thao tác `INSERT` với unique constraint cho phép database giải quyết race giữa nhiều worker. Không chỉ dùng:

```text
if (!exists(eventId)) {
    performSideEffect();
    saveProcessed(eventId);
}
```

Đây là mã giả **không nguyên tử**: hai worker đều có thể thấy chưa tồn tại rồi thực hiện side effect hai lần.

### 11.3. Marker phải đi cùng effect giao dịch được

Giả sử listener cần tạo một bản ghi công việc `notification_outbox`. Marker và bản ghi outbox nên được ghi **trong cùng một transaction mới** (khi chạy hậu commit) để cùng commit hoặc cùng rollback. Nếu ghi marker trước nhưng outbox thất bại, retry sẽ bị chặn và mất công việc.

Với email/HTTP ngoài database, transaction DB không thể rollback lần gửi đã rời ứng dụng. Vì vậy nên dùng transactional outbox, worker retry, và idempotency key được bên nhận hỗ trợ khi có thể. Không tuyên bố exactly-once end-to-end chỉ vì listener đã lọc một lần.

### 11.4. Khóa theo event và khóa theo bất biến nghiệp vụ

Đôi khi cùng một `orderId` có **nhiều event hợp lệ**: `OrderAccepted`, `OrderPaid`, `OrderShipped`. Khóa theo `orderId` đơn thuần có thể chặn nhầm event khác. Trái lại, nếu nghiệp vụ quy định **một hóa đơn cho mỗi paymentId**, chỉ chống trùng `eventId` có thể chưa đủ nếu hai eventId khác nhau nhưng cùng yêu cầu phát một hóa đơn.

Thường cần cả:

- Marker theo `consumer + eventId` để khử delivery trùng.
- Unique business key (ví dụ `invoiceType + paymentId`) để bảo vệ bất biến hiệu ứng.

**Nhớ:** duplicate delivery và duplicate business action là hai vấn đề liên quan nhưng không đồng nhất.

## 12. Thu thập bằng chứng: log ở ba ranh giới

### 12.1. Log tại nguồn publish

```text
stage=PUBLISH eventType=OrderAccepted eventId=evt-100
source=OrderService.accept context=app-main
correlationId=flow-7
```

### 12.2. Log khi vào callback

```text
stage=LISTENER_START eventType=OrderAccepted eventId=evt-100
listenerBean=auditListener listenerMethod=onAccepted
context=app-main thread=http-5
```

### 12.3. Log kết quả

```text
stage=LISTENER_END eventId=evt-100
listenerBean=auditListener status=SUCCESS
effectId=audit-450
```

Những dòng trên là **mẫu trường log**, không phải output từ chương trình mục 6. Với một lần publish, nếu thấy hai `LISTENER_START` của hai bean khác nhau thì đó là fan-out. Nếu thấy hai `PUBLISH` cùng eventId và một listenerBean thì nghi nguồn phát lặp. Nếu một `PUBLISH` từ child nhưng callback xuất hiện ở cả parent/child, xem context hierarchy.

### Nên đặt ID nào?

| Trường | Mục đích | Cảnh báo |
| --- | --- | --- |
| `eventId` | Phân biệt occurrence và replay | Giữ nguyên khi retry cùng occurrence |
| `correlationId` | Nhóm workflow/request | Không phải dedupe key tự động |
| `causationId` | Truy event cha trực tiếp | Không đồng nghĩa `getSource()` |
| `publisherInvocationId` | Phân biệt **mỗi lần gọi publish** | Chỉ là ID chẩn đoán; không thay eventId |
| `listenerBean` + `method` | Xác định registration/handler | Class name riêng lẻ chưa đủ |
| `contextId` | Phân biệt parent/child/restart | Có thể cần thêm instance ID |
| `attempt`/`deliveryTag` | Phân biệt retry/redelivery | Lấy từ nguồn broker/job nếu có |
| `thread` | Quan sát đồng bộ/async | Không dùng làm ID duy nhất |
| `instanceId` | Phân biệt các replica | Log của nhiều process có thể xen kẽ |
| `status`/`effectId` | Xác minh hiệu ứng | Log thành công không thay thế kiểm chứng dữ liệu |

**Một điểm tinh vi:** `publisherInvocationId` có thể đổi giữa các lần phát của **cùng eventId**; nó rất hữu ích để chứng minh Spring đã nhận **hai lệnh publish**, trong khi eventId cho biết đó là cùng occurrence được giao lại.

Không log toàn bộ payload có thể chứa dữ liệu khách hàng, token, số thẻ hoặc secrets chỉ để tìm duplicate.

## 13. Quy trình điều tra thực tế từng bước

### Bước 1 — tạo một tình huống tái hiện tối thiểu

Chọn một `orderId` và `eventId` rõ ràng, tránh hệ thống đang có nhiều request đồng thời. Nếu môi trường cho phép, dùng local context không có broker, thread pool hoặc transaction để xác minh logic cơ bản.

**Không sửa production** để publish thêm event thật chỉ nhằm debug nếu event có side effect. Dùng test hoặc môi trường sandbox và mock các dịch vụ ngoài.

### Bước 2 — đếm publish ở chỗ gần nguồn

Gắn log/counter trước từng `publisher.publishEvent(...)`, có source method và ID lần gọi. Nếu có hai dòng publish, tìm các đường controller/service/scheduler/handler dẫn tới chúng. Nếu chỉ một dòng ở một service, nhớ rằng có thể còn publisher khác; quét mã/trace có phạm vi đúng sự kiện cần xét.

### Bước 3 — liệt kê listener bean và method

Dùng thông tin bean registration của application context, cấu hình `@Component`/`@Bean`, `ApplicationListener` và `@EventListener`. Với cùng một class có hai instance, ghi **bean name** riêng. Chỉ xóa bean dư khi đã chứng minh không có nhu cầu nghiệp vụ khác.

### Bước 4 — kiểm tra hierarchy

Nếu ứng dụng có nhiều `ApplicationContext`, ghi context source và listener context. Với `ApplicationContextEvent` như `ContextRefreshedEvent`, dùng `event.getApplicationContext()` để lọc event của context không mong muốn.

### Bước 5 — kiểm tra event chain

Nếu một handler return event, gọi `publishEvent(...)` hoặc phát một event có supertype trùng, dựng đồ thị `eventId / causationId`. Phát hiện vòng lặp hoặc những nhánh tạo hai event tương đương.

### Bước 6 — kiểm tra nguồn retry và ngoại lệ

Tìm retry policy, transaction retry, message redelivery, dead-letter replay, outbox poller, cron hoặc client request retry. Chụp attempt count và điều kiện ack/commit của nguồn dữ liệu.

### Bước 7 — tạm điều tra ở chế độ đồng bộ có kiểm soát

Trong test tối thiểu, dùng multicaster đồng bộ mặc định và **không bật `@Async`** để nhận diện số lần dispatch. Đây là kỹ thuật cô lập lỗi, **không phải đề xuất tắt async trên production**, vì thay đổi thời gian xử lý hoặc tính năng.

### Bước 8 — test effect và đặt bảo vệ

Sau khi sửa nguyên nhân phát/đăng ký trùng, thêm test idempotency cho consumer quan trọng. Cả khi nguyên nhân ban đầu được sửa, retry hoặc redelivery hợp lệ vẫn có thể xảy ra về sau.

## 14. Kiểm thử để ngăn listener trùng trở lại

Một bộ test cần kiểm tra ba thứ khác nhau:

1. **Publish count:** service phát đúng bao nhiêu occurrence cho một lệnh nghiệp vụ.
2. **Dispatch count:** số bean/method nhận event, và có trùng registration không.
3. **Effect count:** một hành động không được phép lặp thực sự được ghi bao nhiêu lần.

### 14.1. Dùng @RecordApplicationEvents để kiểm tra phát event

Với Spring TestContext:

```java
@SpringJUnitConfig(MyConfig.class)
@RecordApplicationEvents
class OrderEventTests {

    @Autowired
    OrderService orderService;

    @Test
    void publishesOneOrderAccepted(ApplicationEvents events) {
        events.clear();
        orderService.accept("ORD-42");

        assertEquals(1,
                events.stream(OrderAccepted.class).count());
    }
}
```

Đây là **đoạn tích hợp** cần `MyConfig`, `OrderService`, record và các import JUnit/Spring Test tương ứng; không phải một phần ví dụ chạy Maven ở mục 6.

`@RecordApplicationEvents` giúp xem những event Spring đã publish/ghi nhận trong phạm vi test, nhưng **không phải công cụ đo số callback của mọi listener**. Một event có thể được record một lần và hai listener cùng nhận. Ngược lại, listener async có thể chưa xử lý xong lúc assertion chạy.

### 14.2. Kiểm tra bao nhiêu listener được gọi

Dùng recorder được inject vào các listener trong test rồi assert tên bean/method cùng số lần ghi. Ví dụ mục 6 có `Trace.callbackCount()` và `Trace.handlerNames()`. Nếu có async, thay `ArrayList` bằng cấu trúc an toàn luồng và dùng `CountDownLatch` với timeout; không đoán rằng `Thread.sleep(50)` đã đủ.

**Không chỉ assert listener được gọi “một lần” trong một test không có retry** rồi tuyên bố đã đạt idempotency. Idempotency cần kiểm chứng với **hai lần delivery đồng thời hoặc lặp lại**, và phải assert effect chỉ xảy ra một lần.

### 14.3. Test với transaction

Một test `@Transactional` thường rollback sau mỗi test method; khi listener dùng `AFTER_COMMIT`, callback có thể không chạy. Dùng transaction được commit có chủ đích qua `TransactionTemplate` hoặc `TestTransaction` để chứng minh listener hậu commit, rồi thêm case rollback không tạo effect.

Nếu event được publish hai lần trước commit, phải assert **hai callback hậu commit** là khả năng xảy ra; không trông chờ Spring tự gộp chúng.

### 14.4. Test retry/redelivery

Với một consumer có unique key `(consumer,eventId)`:

- Xử lý cùng event một lần: effect được tạo.
- Xử lý lại event đã thành công: không tạo effect thứ hai.
- Hai worker xử lý đồng thời: unique constraint bảo đảm chỉ một claim thành công.
- Lỗi sau khi ghi marker nhưng trước effect: marker và effect cùng rollback nếu giao dịch được thiết kế đúng.
- Gọi API ngoài timeout sau khi phía nhận đã xử lý: dùng idempotency key hoặc reconcile trạng thái với đối tác.

## 15. Async: vì sao log có thể gây ảo giác duplicate?

Khi dùng:

```java
@Async("eventExecutor")
@EventListener
public void onAccepted(OrderAccepted event) {
    log.info("Processing {}", event.eventId());
}
```

publisher có thể trả về trước khi callback chạy. Log của nhiều request/event có thể xen kẽ, khiến nhìn theo timestamp đơn thuần rất dễ nhầm. Một số trường hợp:

- `eventId` được sinh mới ở mỗi retry: nhiều eventId nhưng cùng business key.
- Hai worker chạy callback cùng lúc: cùng eventId xuất hiện gần nhau, cần tra xem có hai task/attempt hay không.
- Logging interceptor in “before” và method in “processing”: **hai dòng log trong một callback**, không phải hai callback.
- Nền tảng log collector thu thập trùng một log entry: duplicate ở tầng log ingestion, không ở event handler.
- Một event dẫn xuất được publish trong listener async, làm log workflow nối tiếp xuất hiện sau thời gian dài.

**Cách xác nhận:** gắn counter/trace tại đúng đầu method, có `listenerBean`, `eventId`, `attempt` và một `handlerInvocationId`, rồi so với effect thực tế. Nếu chỉ có một callback entry nhưng hai dòng log, sửa logging instrumentation hoặc cách phân tích log.

Exception trong `@Async void` không tự lan về publisher; có thể được báo qua `AsyncUncaughtExceptionHandler`. Nếu nguồn message có retry độc lập, sau lỗi nó có thể giao lại sự kiện; vì vậy việc sửa error handler mà không xử lý retry/idempotency chưa đủ.

## 16. Những lỗi thường gặp khi “sửa” listener trùng

1. **Thêm `@Order` để mong chỉ còn một listener.** `@Order` thay đổi thứ tự, không loại listener.
2. **Thêm điều kiện SpEL nhưng không có idempotency state.** Condition không nhận ra eventId đã được xử lý trước đó.
3. **Chỉ dùng `synchronized` trong một instance.** Không bảo vệ qua nhiều replica, restart hoặc các bean instance khác.
4. **Dùng `Set<String>` trong RAM làm nguồn chống trùng duy nhất.** Mất trạng thái khi restart; mỗi instance có set riêng.
5. **Chỉ lọc theo `orderId`.** Có thể chặn các event hợp lệ khác của cùng đơn.
6. **Sinh eventId mới khi retry cùng occurrence.** Consumer không nhận ra delivery trùng.
7. **Bắt exception rồi nuốt.** Broker/transaction có thể coi đã thành công hoặc mất khả năng retry đúng.
8. **Gửi email rồi mới đánh dấu xử lý xong mà không có idempotency bên nhận.** Crash có thể dẫn tới gửi trùng.
9. **Đánh dấu đã xử lý trước khi effect được lưu.** Crash có thể làm mất effect mãi mãi.
10. **Gọi mọi event từ context con là duplicate vô nghĩa.** Parent context có thể cần biết event; lọc theo mục đích.
11. **Xóa một `@EventListener` theo tên class mà không kiểm tra bean instance.** Có thể xóa subscriber hợp lệ.
12. **Dùng `getSource()` như định danh context cho mọi payload record.** Record POJO không có API này.
13. **Bỏ qua event được return từ listener đồng bộ.** Framework có thể publish event dẫn xuất mà code không có lời gọi publish hiển thị ở caller.
14. **Tin rằng `@TransactionalEventListener` tự gom trùng.** Pha commit không phải dedupe.
15. **Cho rằng một log “done” chứng minh external API chỉ được gọi một lần.** Cần kiểm tra record/effect/nhà cung cấp.
16. **Chỉ chạy một test đơn luồng.** Không phát hiện race khi hai worker cùng claim một event.
17. **Dùng listener quá rộng và listener chuyên biệt cùng thực hiện một effect.** Hai phương thức có thể đều khớp event.
18. **Cho rằng Spring xử lý event chỉ một lần trên toàn bộ cluster.** Spring Application Events là cơ chế in-process, mỗi instance có context riêng; cross-process delivery do hệ thống ngoài quyết định.
19. **Nhầm một lần publish với một lần xử lý toàn workflow.** Fan-out nhiều handler là tính năng, không phải lỗi.
20. **Sửa callback count thay vì điều tra business effect.** Nếu số callback đúng nhưng effect trùng, vấn đề có thể nằm ở logic phía downstream.

## 17. Checklist đưa vào vận hành

- [ ] Có `eventId` ổn định cho từng event occurrence, cùng `correlationId` cho workflow.
- [ ] Log tại **publisher** và **listener entry** để so publish count với callback count.
- [ ] Log/metric phân biệt bean name, method, context, instance và retry attempt.
- [ ] Đã rà soát những chỗ `publishEvent(...)` trùng trong controller/service/scheduler.
- [ ] Đã rà soát `@Bean`, `@Component`, `@EventListener`, `ApplicationListener` và listener thêm thủ công.
- [ ] Nếu có parent/child context, kiểm tra phạm vi event và lọc đúng nguồn khi cần.
- [ ] Nếu có event trả về từ listener, đã dựng chuỗi causation và giới hạn vòng lặp.
- [ ] Các listener rộng/chuyên biệt không vô tình thực hiện cùng side effect hai lần.
- [ ] Retry, broker redelivery, outbox và rollback đều đã được phân tích.
- [ ] Không coi `@Order`, `@Async` hoặc `@TransactionalEventListener` là cơ chế chống trùng.
- [ ] Consumer quan trọng có unique/idempotency key ở lưu trữ bền vững.
- [ ] Marker và thay đổi dữ liệu cùng commit/rollback; external API có chiến lược retry thích hợp.
- [ ] Có test một lần publish/nhiều listener và nhiều lần publish/một listener.
- [ ] Có test duplicate, concurrency, transaction, retry và effect cuối cùng.
- [ ] Không phụ thuộc vào thứ tự log để kết luận thứ tự completion khi async.
- [ ] Đã xác nhận logging collector không tự nhân đôi log trước khi đổi business code.

**Kết luận:** khi thấy “listener bị gọi nhiều lần”, hãy xác định liệu đó là **nhiều lần phát**, **nhiều subscription phù hợp**, **sự lan truyền qua context**, hay **retry/replay/event chain**. Cơ chế event của Spring có thể hoạt động đúng trong cả bốn tình huống. Muốn sửa lỗi, phải khắc phục đúng nguồn hoặc bảo vệ tác dụng phụ bằng idempotency, thay vì cố ép mọi listener chỉ chạy một lần.

## Tài liệu tham khảo

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Testing Application Events](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html)
- [Spring Boot — Application Events and Context Hierarchies](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
