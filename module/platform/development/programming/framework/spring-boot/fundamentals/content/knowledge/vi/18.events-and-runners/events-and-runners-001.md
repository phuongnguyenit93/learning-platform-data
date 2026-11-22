# `SpringApplicationEvent` và sự kiện chuẩn của `ApplicationContext`

Spring Boot và Spring Framework đều sử dụng **event** để thông báo rằng một sự việc đã xảy ra trong vòng đời ứng dụng. Ví dụ, Spring Boot có thể phát sự kiện khi quá trình khởi động bắt đầu, khi `Environment` đã sẵn sàng, khi application context được refresh, khi các runner hoàn tất hoặc khi ứng dụng sẵn sàng nhận traffic. Spring Framework cũng phát các sự kiện chuẩn như `ContextRefreshedEvent` và `ContextClosedEvent`.

Các sự kiện này giúp một thành phần phản ứng với vòng đời của ứng dụng mà không cần được gọi trực tiếp từ thành phần phát sự kiện. Tuy nhiên, mỗi loại event có thời điểm và phạm vi riêng. **`ApplicationStartedEvent` không đồng nghĩa với `ContextRefreshedEvent`; `ApplicationReadyEvent` cũng không có nghĩa mọi tác vụ nền của ứng dụng đã hoàn tất.**

Bài học phân biệt:

- **`SpringApplicationEvent`**: các event do Spring Boot phát trong quá trình chạy `SpringApplication`.
- **Context lifecycle events**: các event do Spring Framework phát khi `ApplicationContext` được refresh, start, stop hoặc close.
- **Application event listener**: thành phần nhận và xử lý event bằng `ApplicationListener` hoặc `@EventListener`.
- **Event propagation**: cách event được chuyển tiếp giữa các context trong mô hình parent-child.

## 1. Event trong Spring là gì?

Event là một đối tượng biểu diễn một sự kiện đã xảy ra. Trong Spring Framework, event truyền thống kế thừa `ApplicationEvent`; một listener nhận event và thực hiện phản ứng phù hợp.

Ví dụ, sau khi một đơn hàng được tạo, ứng dụng có thể phát `OrderCreatedEvent` để những thành phần khác gửi email, ghi audit hoặc cập nhật một projection.

```text
OrderService
    |
    | publish OrderCreatedEvent
    v
ApplicationEventPublisher
    |
    v
ApplicationEventMulticaster
    |
    +------> EmailListener
    |
    +------> AuditListener
    |
    +------> MetricsListener
```

Publisher không cần biết cụ thể có bao nhiêu listener hoặc listener thực hiện công việc gì. Các listener đăng ký quan tâm đến event type của mình.

### 1.1. Event khác lời gọi method trực tiếp

Gọi method trực tiếp:

```java
emailService.sendOrderConfirmation(order);
auditService.recordOrderCreated(order);
```

`OrderService` phải biết các service cần gọi và phụ thuộc trực tiếp vào chúng.

Phát event:

```java
publisher.publishEvent(new OrderCreatedEvent(this, order));
```

`OrderService` chỉ phát thông báo rằng đơn hàng đã được tạo. Những listener phù hợp sẽ nhận thông báo theo cơ chế event của Spring.

Event hữu ích khi các phản ứng có thể được tách rời khỏi luồng nghiệp vụ chính. Nếu một thao tác là dependency bắt buộc để hoàn tất nghiệp vụ — chẳng hạn phải kiểm tra tồn kho trước khi xác nhận đơn — gọi service qua dependency injection thường thể hiện quan hệ rõ ràng hơn.

## 2. `SpringApplicationEvent` là gì?

`SpringApplicationEvent` là lớp event nền của các sự kiện do Spring Boot phát trong quá trình điều phối `SpringApplication`. Các event này thường mang thông tin về `SpringApplication` và, ở những giai đoạn thích hợp, `Environment` hoặc `ApplicationContext`.

Những event tiêu biểu:

| Event | Thời điểm khái quát |
| --- | --- |
| `ApplicationStartingEvent` | Quá trình khởi động bắt đầu, trước khi Environment và context được chuẩn bị đầy đủ |
| `ApplicationEnvironmentPreparedEvent` | Environment đã được chuẩn bị |
| `ApplicationContextInitializedEvent` | Context đã được tạo và các initializer đã chạy, trước khi nạp bean definitions từ application sources |
| `ApplicationPreparedEvent` | Context đã được chuẩn bị và nạp cấu hình, trước khi refresh |
| `ApplicationStartedEvent` | Context đã refresh, trước khi gọi application/command-line runners |
| `ApplicationReadyEvent` | Các runner đã hoàn tất; ứng dụng đã đi đến trạng thái ready theo quy trình startup |
| `ApplicationFailedEvent` | Quá trình khởi động thất bại |

Ngoài các event trên, Spring Boot còn phát những event liên quan đến availability và web server, chẳng hạn `AvailabilityChangeEvent`, `ServletWebServerInitializedEvent` hoặc `ReactiveWebServerInitializedEvent`.

Tên class nằm trong package `org.springframework.boot.context.event` đối với nhiều event vòng đời kể trên. Hãy tham chiếu API của đúng phiên bản Spring Boot đang sử dụng vì chi tiết event và thời điểm có thể được mở rộng giữa các phiên bản.

## 3. Trình tự event trong quá trình khởi động Spring Boot

Một trình tự thường gặp có thể hình dung như sau:

```text
SpringApplication.run(...)
        |
        v
ApplicationStartingEvent
        |
        v
Chuẩn bị Environment
        |
        v
ApplicationEnvironmentPreparedEvent
        |
        v
Tạo ApplicationContext
        |
        v
Chạy ApplicationContextInitializer
        |
        v
ApplicationContextInitializedEvent
        |
        v
Nạp primary sources / configuration
        |
        v
ApplicationPreparedEvent
        |
        v
Refresh ApplicationContext
        |
        +----> ContextRefreshedEvent
        |
        +----> Web server initialized event (nếu là web app)
        |
        v
ApplicationStartedEvent
        |
        v
AvailabilityChangeEvent: LivenessState.CORRECT
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
        |
        v
AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
```

Đây là sơ đồ tổng quan để định vị các mốc quan trọng. Một số event có thể được phát trong lúc refresh hoặc ở những nhánh startup khác nhau; khi startup thất bại, `ApplicationFailedEvent` được phát thay cho việc đi tới trạng thái ready.

### 3.1. `ApplicationStartingEvent`

Đây là một trong những event đầu tiên của Spring Boot. Nó được phát rất sớm, trước khi `Environment` và `ApplicationContext` của ứng dụng được chuẩn bị đầy đủ.

Có thể dùng event này để ghi nhận thời điểm tiến trình bắt đầu hoặc thực hiện một tác vụ hạ tầng rất sớm không cần bean của application context.

Vì context chưa sẵn sàng, một listener nhận event này không nên giả định có thể inject hoặc lấy các service nghiệp vụ từ application context.

### 3.2. `ApplicationEnvironmentPreparedEvent`

Event này được phát sau khi `Environment` đã được chuẩn bị. Các property source như command-line arguments, biến môi trường, system properties và file cấu hình đã tham gia vào quá trình xây dựng môi trường theo quy tắc Spring Boot.

Đây là mốc phù hợp để quan sát môi trường startup hoặc tích hợp những thao tác cần biết profile/property đã được chuẩn bị. Context vẫn chưa ở trạng thái đã refresh.

Ví dụ listener:

```java
import org.springframework.boot.context.event.ApplicationEnvironmentPreparedEvent;
import org.springframework.context.ApplicationListener;

public class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationEnvironmentPreparedEvent event) {
        String[] profiles =
                event.getEnvironment().getActiveProfiles();

        System.out.println(
                "Active profiles: " + String.join(", ", profiles)
        );
    }
}
```

Listener này đọc `Environment` trực tiếp từ event, không cần lấy bean từ context.

### 3.3. `ApplicationContextInitializedEvent`

Event được phát sau khi context đã được tạo và các `ApplicationContextInitializer` đã được áp dụng, nhưng trước khi application sources được nạp đầy đủ vào context.

Bạn có thể dùng nó để ghi nhận mốc context đã được chuẩn bị ban đầu. Không nên coi đây là thời điểm tất cả bean definitions đã đăng ký hoặc bean instances đã được tạo.

### 3.4. `ApplicationPreparedEvent`

Event này đánh dấu context đã được chuẩn bị với các application sources nhưng **chưa refresh**.

Đây vẫn là giai đoạn trước khi container hoàn tất quá trình tạo các singleton bean thông thường. Một listener ở giai đoạn này không nên gọi các service nghiệp vụ như thể application context đã sẵn sàng.

### 3.5. `ContextRefreshedEvent`

Đây là event của Spring Framework, không phải subclass của `SpringApplicationEvent`. Nó được phát khi `ApplicationContext` đã refresh thành công.

Trong ứng dụng Spring Boot, event này thường xuất hiện trong quá trình refresh context trước `ApplicationStartedEvent`.

`ContextRefreshedEvent` có thể được phát khi context refresh; trong hệ thống có nhiều context hoặc refresh nhiều lần, không nên giả định nó chỉ xuất hiện đúng một lần cho toàn JVM.

### 3.6. `ApplicationStartedEvent`

Spring Boot phát event này sau khi application context đã refresh và trước khi gọi các `ApplicationRunner` hoặc `CommandLineRunner`.

Đây là điểm khác biệt quan trọng:

- Context đã được refresh.
- Các singleton eager thông thường đã được khởi tạo.
- Startup runners vẫn chưa chạy.
- Ứng dụng chưa đi tới mốc `ApplicationReadyEvent`.

Nếu cần thực hiện công việc trong giai đoạn runner, đừng dùng `ApplicationStartedEvent` như bằng chứng rằng runner đã hoàn tất.

### 3.7. `ApplicationReadyEvent`

Event này được phát sau khi các runner hoàn tất. Nó biểu thị ứng dụng đã đi đến trạng thái sẵn sàng theo startup lifecycle của Spring Boot.

Ví dụ:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyReporter {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
```

Đây là nơi phù hợp để ghi nhận mốc startup hoàn tất hoặc kích hoạt một tác vụ hậu khởi động nhẹ, có kiểm soát.

Không nên đưa một tác vụ dài, không giới hạn hoặc có thể chặn startup vào listener này nếu không có chủ đích. Listener đồng bộ có thể làm chậm quá trình phát event và khiến `run()` chưa hoàn tất.

### 3.8. `ApplicationFailedEvent`

Event này được phát khi quá trình startup thất bại. Nó hữu ích cho logging, gửi tín hiệu giám sát hoặc ghi nhận lỗi khởi động.

Tuy nhiên, thất bại có thể xảy ra rất sớm, trước khi application context được tạo hoàn chỉnh. Vì vậy, không phải lúc nào listener cũng có thể dựa vào một context đầy đủ để lấy bean.

Listener nên đọc thông tin exception từ event, ghi nhận lỗi và tránh tạo thêm phụ thuộc vào những bean có thể chưa tồn tại.

## 4. Sự kiện availability trong Spring Boot

Spring Boot có các event biểu diễn trạng thái sống và khả năng nhận traffic của ứng dụng:

- `LivenessState.CORRECT`: ứng dụng đã vượt qua mốc startup tương ứng và tiến trình được xem là còn sống.
- `ReadinessState.ACCEPTING_TRAFFIC`: ứng dụng đã sẵn sàng nhận traffic.
- `ReadinessState.REFUSING_TRAFFIC`: ứng dụng tạm thời không nhận traffic.

Các thay đổi này được công bố qua `AvailabilityChangeEvent`.

Ví dụ listener:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadinessListener {

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        System.out.println(
                "Readiness: " + event.getState()
        );
    }
}
```

Ứng dụng cũng có thể chủ động công bố trạng thái:

```java
AvailabilityChangeEvent.publish(
        applicationContext,
        ReadinessState.REFUSING_TRAFFIC
);
```

Ví dụ trên cần một `ApplicationContext` phù hợp và import các kiểu availability tương ứng. Trong hệ thống thực tế, hãy kết hợp trạng thái này với health checks, load balancer và cơ chế orchestration đang dùng.

**Liveness và readiness không giống nhau:** một ứng dụng có thể vẫn sống nhưng tạm thời chưa sẵn sàng nhận request. Đừng dùng một trạng thái để thay thế trạng thái còn lại.

## 5. Sự kiện chuẩn của `ApplicationContext`

Spring Framework phát các event gắn với lifecycle của application context. Các event chuẩn thường gặp:

| Event | Khi nào được phát? | Ý nghĩa |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context refresh thành công | Context đã được nạp và sẵn sàng theo chu trình refresh |
| `ContextStartedEvent` | Gọi `ConfigurableApplicationContext.start()` | Context được yêu cầu bắt đầu hoạt động |
| `ContextStoppedEvent` | Gọi `ConfigurableApplicationContext.stop()` | Context được yêu cầu dừng |
| `ContextClosedEvent` | Context được đóng | Container đang kết thúc lifecycle |

Các class này thuộc package `org.springframework.context.event`.

### 5.1. `ContextRefreshedEvent`

Ví dụ listener:

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextRefreshReporter {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: " +
                event.getApplicationContext().getId()
        );
    }
}
```

Event mang theo application context đã refresh. Trong ứng dụng có parent-child contexts, mỗi context có thể phát event riêng. Một listener có thể nhận event được chuyển tiếp từ context con tùy vị trí đăng ký.

Không nên dùng `ContextRefreshedEvent` như event “ứng dụng đã hoàn toàn sẵn sàng” trong mọi ứng dụng Spring Boot. Runners vẫn có thể chưa được gọi; hãy dùng `ApplicationReadyEvent` khi cần mốc sau runners.

### 5.2. `ContextStartedEvent`

Event này được phát khi context được yêu cầu start qua API lifecycle:

```java
ConfigurableApplicationContext context = ...;
context.start();
```

Nó không đồng nghĩa với việc gọi `SpringApplication.run()` lần đầu. Trong nhiều ứng dụng Spring Boot thông thường, bạn ít khi phải gọi `context.start()` trực tiếp.

### 5.3. `ContextStoppedEvent`

Event được phát khi gọi:

```java
context.stop();
```

`stop()` biểu thị yêu cầu dừng lifecycle của context và các lifecycle bean phù hợp. Nó khác `close()`: context vẫn có thể được start lại nếu loại context và trạng thái cho phép.

### 5.4. `ContextClosedEvent`

Event được phát khi application context đóng:

```java
context.close();
```

Đây là mốc phù hợp để listener ghi nhận shutdown hoặc thực hiện phần cleanup cần thiết. Tuy nhiên, các bean có callback `@PreDestroy`, `DisposableBean` hoặc destroy method nên được ưu tiên dùng cho cleanup gắn với lifecycle của chính bean.

Không nên dựa vào `ContextClosedEvent` để gọi các service có thể đã bị hủy hoặc đang trong quá trình shutdown. Listener nên làm việc ngắn gọn và tránh tạo bean mới trong lúc context đóng.

## 6. Event của Spring Boot và event của ApplicationContext khác nhau thế nào?

| Tiêu chí | `SpringApplicationEvent` | Context lifecycle event |
| --- | --- | --- |
| Nguồn phát | Vòng đời chạy `SpringApplication` của Spring Boot | Vòng đời của một `ApplicationContext` trong Spring Framework |
| Phạm vi | Toàn bộ startup lifecycle ở cấp Spring Boot | Một context cụ thể |
| Ví dụ | `ApplicationStartingEvent`, `ApplicationReadyEvent` | `ContextRefreshedEvent`, `ContextClosedEvent` |
| Có thể xảy ra trước khi context tồn tại? | Có, với các event sớm | Không, vì event gắn với context |
| Dùng để trả lời | Ứng dụng Boot đang ở mốc startup nào? | Context này đang ở trạng thái lifecycle nào? |

Một event Boot có thể được phát tới listener qua cơ chế event của ứng dụng; đồng thời quá trình startup cũng làm context phát các event riêng. Chúng liên quan về thời gian nhưng không cùng loại.

### 6.1. So sánh hai mốc dễ nhầm

```text
ContextRefreshedEvent
        |
        v
ApplicationStartedEvent
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
```

Vì vậy:

- Dùng `ContextRefreshedEvent` khi quan tâm context vừa refresh.
- Dùng `ApplicationStartedEvent` khi quan tâm startup đã qua refresh nhưng runner chưa chạy.
- Dùng `ApplicationReadyEvent` khi quan tâm các runner đã hoàn tất.

Nếu chỉ cần chạy code sau khi bean được khởi tạo, có thể dùng lifecycle callback của bean. Nếu cần một mốc toàn ứng dụng, chọn event đúng với thời điểm mong muốn.

## 7. Đăng ký listener bằng `ApplicationListener`

`ApplicationListener<E>` là interface chuẩn của Spring:

```java
public interface ApplicationListener<E extends ApplicationEvent> {
    void onApplicationEvent(E event);
}
```

Ví dụ:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.stereotype.Component;

@Component
public class ApplicationReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready: " + event.getApplicationContext().getId());
    }
}
```

Khi class được component scan và context được khởi tạo, Spring đăng ký listener để nhận event type tương ứng.

### 7.1. Listener cho event sớm phải đăng ký trước khi context tồn tại

Một listener được tạo bằng `@Component` chỉ có thể đăng ký khi Spring xử lý bean definitions và khởi tạo listener bean. Vì vậy nó không thể nhận những event xảy ra trước thời điểm đó, chẳng hạn `ApplicationStartingEvent`.

Để nhận event sớm, đăng ký listener trực tiếp trên `SpringApplication`:

```java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.addListeners(new StartingListener());
application.run(args);
```

Ví dụ listener:

```java
public class StartingListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("Spring Boot is starting");
    }
}
```

Có thể đăng ký listener qua cơ chế factory metadata phù hợp của Spring Boot khi phát triển thư viện. Với ứng dụng đơn giản, `SpringApplication.addListeners(...)` dễ nhìn thấy và dễ kiểm soát.

### 7.2. `setListeners()` và `addListeners()`

`SpringApplication` cung cấp cả thao tác thiết lập danh sách và bổ sung listener:

```java
application.addListeners(
        new StartingListener(),
        new EnvironmentPreparedListener()
);
```

`addListeners(...)` thể hiện ý định thêm listener vào cấu hình hiện có. Nếu dùng `setListeners(...)`, bạn đang thiết lập danh sách listener theo setter đó; hãy chú ý không vô tình thay thế những listener đã được cấu hình từ nơi khác.

## 8. Đăng ký listener bằng `@EventListener`

Với bean được quản lý bởi Spring, `@EventListener` thường ngắn gọn hơn việc implement interface:

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter {

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application ready");
    }
}
```

Spring phát hiện method mang `@EventListener` và đăng ký nó làm listener cho event type của tham số.

### 8.1. Một class có thể nghe nhiều event

```java
@Component
public class LifecycleReporter {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println("Context refreshed");
    }

    @EventListener
    public void onClose(ContextClosedEvent event) {
        System.out.println("Context closing");
    }
}
```

Mỗi method lắng nghe một event type riêng. Cách này giúp gom các phản ứng lifecycle có liên quan vào một component.

### 8.2. Lắng nghe event theo kiểu cha

Listener có thể nhận một kiểu event tổng quát hơn. Ví dụ, một method nhận `ApplicationEvent` có thể được gọi với nhiều event thuộc hệ thống Spring, miễn là event được publish trong phạm vi mà listener đăng ký.

```java
@EventListener
public void onAnyApplicationEvent(ApplicationEvent event) {
    System.out.println(event.getClass().getSimpleName());
}
```

Trong ứng dụng thực tế, listener tổng quát cần lọc event cẩn thận để tránh log quá nhiều hoặc xử lý nhầm event không liên quan.

### 8.3. `@EventListener` có thể phát event tiếp theo

Một listener method có thể trả về một object event/payload; Spring sẽ publish kết quả đó như event tiếp theo theo quy tắc hỗ trợ của `@EventListener`.

Ví dụ khái niệm:

```java
@EventListener
public OrderAuditedEvent onOrderCreated(OrderCreatedEvent event) {
    return new OrderAuditedEvent(event.orderId());
}
```

Trong ứng dụng lớn, cân nhắc phát event tường minh qua `ApplicationEventPublisher` nếu luồng event cần dễ theo dõi hoặc method cần trả về kết quả nghiệp vụ khác.

## 9. Phát event tùy chỉnh bằng `ApplicationEventPublisher`

Spring cung cấp `ApplicationEventPublisher` để bean phát event:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createOrder(String orderId) {
        // Thực hiện logic tạo đơn
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
```

Event class có thể là một object đơn giản:

```java
public record OrderCreatedEvent(String orderId) {
}
```

Spring hiện đại cho phép publish object bất kỳ; không bắt buộc custom event phải kế thừa `ApplicationEvent`. Khi publish object không phải `ApplicationEvent`, Spring có thể bọc nó trong `PayloadApplicationEvent`.

Listener:

```java
@Component
public class OrderCreatedListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Order created: " + event.orderId());
    }
}
```

`ApplicationEventPublisher` là abstraction để publish event; service không cần biết cụ thể listener nào sẽ nhận.

### 9.1. Khi nào nên dùng custom event?

Custom event phù hợp khi một sự việc trong domain có thể tạo ra nhiều phản ứng độc lập:

- Đơn hàng được tạo.
- Người dùng đăng ký tài khoản.
- Thanh toán được xác nhận.
- Hồ sơ được cập nhật.
- Một batch job hoàn tất.

Đặt tên event theo sự việc đã xảy ra, thường dùng thì quá khứ như `OrderCreatedEvent`, `PaymentConfirmedEvent`. Điều đó giúp listener hiểu rằng event mô tả một fact, không phải một lệnh yêu cầu thực hiện hành động.

## 10. Event được xử lý đồng bộ hay bất đồng bộ?

Theo cấu hình mặc định phổ biến, event listener của Spring được gọi **đồng bộ** trong thread phát event. Điều này có nghĩa:

```java
publisher.publishEvent(event);
```

thường không trả về cho publisher cho đến khi các listener đồng bộ hoàn tất.

Hệ quả:

- Listener chậm có thể làm chậm luồng nghiệp vụ đang publish event.
- Exception từ listener đồng bộ có thể ảnh hưởng tới luồng phát event.
- Event nội bộ không tự động trở thành message queue hay tác vụ chạy nền.

### 10.1. Chạy listener bất đồng bộ

Một cách là kết hợp `@Async` và `@EnableAsync`:

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
```

```java
@Component
public class EmailListener {

    @Async
    @EventListener
    public void sendEmail(OrderCreatedEvent event) {
        // Gửi email trong executor phù hợp
    }
}
```

Để sử dụng trong production, nên cấu hình executor có giới hạn thread/queue, xử lý exception và quan sát tình trạng tác vụ. `@Async` không bảo đảm công việc được lưu bền vững nếu tiến trình dừng đột ngột.

Nếu yêu cầu cần bảo đảm giao nhận, retry hoặc xử lý qua nhiều tiến trình, hãy cân nhắc message broker hoặc transactional outbox thay vì dựa hoàn toàn vào in-process event.

### 10.2. Sự kiện đồng bộ không phải transaction tự động

Phát event không tự tạo transaction và không bảo đảm listener chạy sau khi transaction commit. Nếu listener đọc dữ liệu vừa ghi trong transaction, cần hiểu transaction boundary và thời điểm listener được gọi.

Spring cung cấp `@TransactionalEventListener` cho những trường hợp listener cần gắn với transaction phase:

```java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void afterOrderCommitted(OrderCreatedEvent event) {
        // Thực hiện phản ứng sau khi transaction commit
    }
}
```

Listener kiểu này thường chỉ được gọi khi có transaction phù hợp. Có thể cấu hình `fallbackExecution` nếu muốn xử lý khi không có transaction, nhưng cần cân nhắc ngữ nghĩa nghiệp vụ trước khi bật.

`AFTER_COMMIT` có nghĩa listener được gọi sau khi transaction commit; nó không tự biến email hoặc HTTP call thành thao tác bền vững. Nếu ứng dụng cần bảo đảm event không bị mất giữa commit và gửi message, hãy xem xét transactional outbox.

## 11. Thứ tự thực thi listener

Nếu nhiều listener cùng nhận một event, bạn có thể dùng `@Order` hoặc `Ordered` để xác định thứ tự trong cơ chế event multicaster hỗ trợ order.

Ví dụ:

```java
@Component
@Order(10)
public class AuditListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Audit order " + event.orderId());
    }
}
```

```java
@Component
@Order(20)
public class MetricsListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Metric order " + event.orderId());
    }
}
```

Với listener đồng bộ trong cùng multicaster, listener có order nhỏ hơn được ưu tiên trước. Nếu listener chạy bất đồng bộ, thứ tự bắt đầu hoặc hoàn tất tác vụ không nên được coi là tuần tự chỉ vì có `@Order`.

Không nên dùng order để biểu đạt dependency nghiệp vụ phức tạp giữa listener. Nếu listener B cần kết quả do listener A tạo, hãy cân nhắc một workflow/coordinator rõ ràng hoặc phát event tiếp theo sau khi bước A hoàn tất.

## 12. Event propagation trong parent-child context

Spring hỗ trợ application context hierarchy. Một context con có thể có parent context. Trong mô hình này, event được publish từ child có thể được chuyển tiếp lên parent để listener ở parent nhận được.

```text
             Parent ApplicationContext
             (Shared listeners)
                      ^
                      | event từ child được chuyển lên
                      |
             Child ApplicationContext
             (Web/API listeners)
```

Quy tắc cần nhớ:

- Event được publish trong child có thể lan lên parent.
- Event được publish trong parent không tự động lan xuống child.
- Hai context có event multicaster và bean listener riêng.
- Nếu cùng một listener được đăng ký ở nhiều context, cần chú ý khả năng nhận cùng event nhiều lần qua các đường đăng ký/propagation.

Ví dụ:

```java
@Component
public class SharedAuditListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Shared audit: " + event.orderId());
    }
}
```

Nếu listener nằm trong parent context, nó có thể nhận event được publish từ child context thông qua propagation. Tuy nhiên, đừng giả định parent có thể nhìn thấy bean listener chỉ được đăng ký ở child.

## 13. Event web và các event khác trong Spring Boot

Ngoài event vòng đời application, ứng dụng web còn có những event đặc thù:

| Event | Ý nghĩa |
| --- | --- |
| `ServletWebServerInitializedEvent` | Web server servlet đã được khởi tạo |
| `ReactiveWebServerInitializedEvent` | Web server reactive đã được khởi tạo |
| `RequestHandledEvent` | Một request đã được xử lý trong những môi trường Spring web hỗ trợ event này |

Ví dụ lắng nghe server servlet:

```java
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class WebServerReporter {

    @EventListener
    public void onWebServerInitialized(
            WebServerInitializedEvent event) {
        System.out.println(
                "Server port: " + event.getWebServer().getPort()
        );
    }
}
```

`WebServerInitializedEvent` là kiểu cha của những event khởi tạo server cụ thể. Khi muốn chỉ nhận servlet hoặc reactive server, có thể dùng kiểu event cụ thể tương ứng.

Event server initialized hữu ích khi cổng được chọn động, ví dụ `server.port=0`. Khi đó, đọc cổng thực tế từ web server event giúp biết cổng mà hệ điều hành cấp.

## 14. Chọn đúng event theo mục tiêu

| Mục tiêu | Event hoặc cơ chế nên cân nhắc |
| --- | --- |
| Ghi nhận ứng dụng bắt đầu chạy rất sớm | `ApplicationStartingEvent` |
| Đọc profile/property sau khi Environment chuẩn bị | `ApplicationEnvironmentPreparedEvent` |
| Quan sát context vừa refresh | `ContextRefreshedEvent` |
| Thực hiện công việc sau khi context refresh nhưng trước runner | `ApplicationStartedEvent` |
| Thực hiện công việc sau khi runner hoàn tất | `ApplicationReadyEvent` |
| Ghi nhận startup thất bại | `ApplicationFailedEvent` |
| Biết web server đã có cổng thực tế | `WebServerInitializedEvent` hoặc subtype phù hợp |
| Ghi nhận context đóng | `ContextClosedEvent` |
| Phản ứng với domain event của ứng dụng | Custom event qua `ApplicationEventPublisher` |
| Chỉ xử lý domain event sau commit | `@TransactionalEventListener(AFTER_COMMIT)` |
| Thực hiện dependency bắt buộc trong nghiệp vụ | Constructor injection và lời gọi service trực tiếp |

Đừng chọn event chỉ vì tên nghe phù hợp. Hãy xác định listener cần chạy **trước hay sau context refresh, trước hay sau runners, trước hay sau transaction commit**, rồi mới chọn cơ chế.

## 15. Ví dụ tổng hợp: ghi nhận startup lifecycle

Ta có thể kết hợp một listener sớm được đăng ký trên `SpringApplication` với listener trong context.

### 15.1. Listener cho event sớm

```java
import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("[1] Application starting");
    }
}
```

### 15.2. Listener cho event trong context

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ContextLifecycleListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        System.out.println("[2] Context refreshed");
    }

    @EventListener
    public void onApplicationReady(ApplicationReadyEvent event) {
        System.out.println("[3] Application ready");
    }
}
```

### 15.3. Đăng ký listener sớm trước `run()`

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(new EarlyStartupListener());
        application.run(args);
    }
}
```

`EarlyStartupListener` được đăng ký trước khi `run()` bắt đầu, vì vậy có thể nhận `ApplicationStartingEvent`. `ContextLifecycleListener` là bean nên chỉ bắt đầu nhận event sau khi được phát hiện và đăng ký trong context.

Thứ tự log minh họa:

```text
[1] Application starting
[2] Context refreshed
[3] Application ready
```

Các log startup khác có thể xen giữa. Đặc biệt, nếu có nhiều context, `ContextRefreshedEvent` có thể xuất hiện nhiều lần.

## 16. Những lỗi và hiểu nhầm thường gặp

### 16.1. `@Component` listener không nhận được `ApplicationStartingEvent`

Nguyên nhân thường là listener bean chỉ được đăng ký sau khi context xử lý configuration. `ApplicationStartingEvent` xảy ra sớm hơn.

**Cách xử lý:** đăng ký listener trực tiếp trên `SpringApplication` trước khi gọi `run()`.

### 16.2. Dùng `ContextRefreshedEvent` để khẳng định ứng dụng ready

Context đã refresh nhưng `ApplicationRunner` và `CommandLineRunner` có thể chưa chạy.

**Cách xử lý:** dùng `ApplicationReadyEvent` nếu cần mốc sau runner.

### 16.3. Listener đồng bộ làm chậm startup

Một listener `ApplicationReadyEvent` có thể thực hiện công việc dài và giữ thread phát event.

**Cách xử lý:** giới hạn công việc trong listener, hoặc dùng executor/async khi có chính sách xử lý lỗi và shutdown rõ ràng.

### 16.4. Event bị xử lý hai lần trong context hierarchy

Một listener có thể được đăng ký ở parent và child, đồng thời event từ child được propagate lên parent.

**Cách xử lý:** xác định listener được đăng ký ở context nào, kiểm tra context ID và thiết kế một nơi chịu trách nhiệm xử lý.

### 16.5. Dùng event thay cho transaction hoặc message queue

In-process application event không tự bảo đảm bền vững, retry hay giao nhận giữa nhiều instance.

**Cách xử lý:** dùng `@TransactionalEventListener` khi cần transaction phase; dùng message broker/outbox khi cần giao nhận bền vững và liên tiến trình.

### 16.6. Cho rằng `ContextStoppedEvent` và `ContextClosedEvent` giống nhau

`stop()` và `close()` có ý nghĩa lifecycle khác nhau. Stop yêu cầu dừng các lifecycle component phù hợp; close kết thúc context và kích hoạt quy trình hủy bean.

**Cách xử lý:** chọn API theo mục tiêu dừng tạm thời hay kết thúc context.

## 17. Kiểm thử event

Event listener nên được kiểm thử để xác nhận đúng event type và hành vi.

### 17.1. Kiểm tra custom event với `ApplicationEventPublisher`

Ví dụ listener:

```java
@Component
public class OrderEventListener {
    private final List<String> received = new ArrayList<>();

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        received.add(event.orderId());
    }

    public List<String> receivedOrders() {
        return List.copyOf(received);
    }
}
```

Test có thể lấy publisher và listener từ context:

```java
@SpringBootTest
class OrderEventTest {

    @Autowired
    ApplicationEventPublisher publisher;

    @Autowired
    OrderEventListener listener;

    @Test
    void listenerReceivesPublishedEvent() {
        publisher.publishEvent(new OrderCreatedEvent("ORD-100"));

        assertThat(listener.receivedOrders())
                .contains("ORD-100");
    }
}
```

Ví dụ giả định listener xử lý đồng bộ theo cấu hình mặc định. Nếu listener dùng `@Async`, test cần chờ kết quả theo cách đồng bộ hóa phù hợp thay vì assert ngay lập tức.

### 17.2. Ghi nhận event startup

Có thể đăng ký một listener kiểm thử thông qua `SpringApplication.addListeners(...)` để thu thập những mốc startup. Khi test event sớm, không nên chỉ dựa vào một `@Component` listener vì nó chưa tồn tại ở giai đoạn trước context.

### 17.3. Kiểm tra context lifecycle

Có thể tạo context trong test, refresh và close rõ ràng:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.register(TestConfiguration.class);
context.refresh();
context.close();
```

Listener được đăng ký trong context có thể quan sát `ContextRefreshedEvent` và `ContextClosedEvent`. Đây là cách kiểm tra lifecycle ở mức Spring Framework mà không cần khởi động toàn bộ ứng dụng Spring Boot.

## 18. Bài thực hành

### Bài 1 — Ghi nhận các mốc Spring Boot startup

Tạo listener cho:

- `ApplicationStartingEvent`
- `ApplicationEnvironmentPreparedEvent`
- `ApplicationContextInitializedEvent`
- `ApplicationPreparedEvent`
- `ApplicationStartedEvent`
- `ApplicationReadyEvent`

Đăng ký những listener cần nhận event sớm qua `SpringApplication.addListeners(...)`. In tên event và so sánh thứ tự xuất hiện.

### Bài 2 — So sánh `ContextRefreshedEvent` và `ApplicationReadyEvent`

Tạo hai listener, mỗi listener ghi một dòng log. Thêm một `CommandLineRunner` mất một khoảng thời gian ngắn để hoàn tất.

Quan sát:

1. Context refresh xảy ra khi nào?
2. Runner chạy ở giữa những event nào?
3. `ApplicationReadyEvent` xuất hiện trước hay sau runner?

### Bài 3 — Tạo custom event

Tạo `UserRegisteredEvent`, publish từ `UserService` và viết hai listener:

- `WelcomeEmailListener`
- `AuditListener`

Xác nhận cả hai nhận cùng event mà `UserService` không cần gọi trực tiếp hai listener.

### Bài 4 — Kiểm tra listener sớm

Thử đăng ký một `ApplicationStartingEvent` listener bằng `@Component`. Quan sát listener có nhận event không. Sau đó chuyển sang `SpringApplication.addListeners(...)` trước `run()` và so sánh.

### Bài 5 — Thử event đồng bộ và bất đồng bộ

Tạo listener ghi thời điểm bắt đầu/kết thúc và một listener có `@Async`. So sánh thread và thời gian trả về của `publishEvent()`.

Giải thích vì sao in-process async listener không bảo đảm tác vụ được lưu bền vững nếu JVM dừng.

### Bài 6 — Thử parent-child propagation

Tạo parent và child `ApplicationContext`. Đăng ký listener ở parent, publish custom event từ child và quan sát event có được nhận. Sau đó publish event từ parent và kiểm tra child listener.

Giải thích chiều propagation và nguy cơ nhận event trùng khi listener được đăng ký ở nhiều cấp.

### Bài 7 — Gắn event với transaction

Tạo `OrderCreatedEvent` được publish trong một phương thức `@Transactional`. Viết một `@EventListener` thường và một `@TransactionalEventListener(phase = AFTER_COMMIT)`.

Quan sát sự khác biệt khi transaction commit thành công và khi rollback. Giải thích vì sao event thông thường không tự chờ transaction commit.

## 19. Ghi nhớ

`SpringApplicationEvent` mô tả những mốc trong vòng đời khởi động Spring Boot, từ `ApplicationStartingEvent` đến `ApplicationReadyEvent` hoặc `ApplicationFailedEvent`. Các event chuẩn của `ApplicationContext` như `ContextRefreshedEvent`, `ContextStartedEvent`, `ContextStoppedEvent` và `ContextClosedEvent` mô tả lifecycle của từng context.

Hãy chọn event theo đúng mốc cần phản ứng: Environment đã sẵn sàng, context đã refresh, runners đã hoàn tất hay context đang đóng. Listener sớm phải được đăng ký trước khi context tồn tại; listener trong context có thể dùng `ApplicationListener` hoặc `@EventListener`. Mặc định event thường được xử lý đồng bộ, còn async và transaction-bound listener cần cấu hình cùng ngữ nghĩa rõ ràng.

Event giúp giảm phụ thuộc trực tiếp giữa publisher và listener, nhưng không thay thế dependency injection, transaction manager hoặc message broker. Khi hiểu đúng loại event, thời điểm phát và phạm vi context, bạn có thể mở rộng ứng dụng Spring Boot theo vòng đời một cách rõ ràng và dễ kiểm soát.
