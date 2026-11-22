# ApplicationListener, @EventListener và đăng ký listener đủ sớm

Spring Boot phát nhiều application event trong quá trình khởi động và vận hành. Listener có thể dùng để ghi log, chuẩn bị cache, quan sát trạng thái ứng dụng, khởi tạo tích hợp hoặc phản ứng khi context đã sẵn sàng.

Spring cung cấp hai cách viết listener thường gặp:

- **`ApplicationListener<E>`**: triển khai một interface với kiểu event cụ thể và method `onApplicationEvent`.
- **`@EventListener`**: đánh dấu một method trong bean Spring để method đó nhận event phù hợp.

Điểm quan trọng khi làm việc với event khởi động là **thời điểm đăng ký listener**. Một listener được tạo thành bean trong ApplicationContext thường chỉ được kết nối với event multicaster trong quá trình refresh context. Vì vậy nó không thể nhận những event đã phát trước khi context tồn tại hoặc trước khi listener được đăng ký. Nếu cần nghe event rất sớm như `ApplicationStartingEvent` hay `ApplicationEnvironmentPreparedEvent`, hãy đăng ký listener trực tiếp với `SpringApplication` trước khi gọi `run()`, hoặc công bố listener qua cơ chế `spring.factories` phù hợp.

Bài học đi từ mô hình event, hai cách viết listener, thứ tự các event startup, những điểm đăng ký đủ sớm, đến ordering, lỗi thường gặp và cách kiểm thử.

## 1. Spring application event hoạt động như thế nào?

Spring có mô hình event trong process. Một thành phần phát một object kế thừa `ApplicationEvent` hoặc dùng kiểu event được Spring hỗ trợ; các listener đã đăng ký sẽ nhận event tương ứng.

Ví dụ, một service có thể phát event nghiệp vụ:

~~~java
public record OrderPlacedEvent(String orderId) {
}
~~~

Một thành phần phát event qua `ApplicationEventPublisher`:

~~~java
@Service
public class OrderService {
    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void placeOrder(String orderId) {
        // Xử lý nghiệp vụ đặt hàng...
        events.publishEvent(new OrderPlacedEvent(orderId));
    }
}
~~~

Listener nhận event:

~~~java
@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println("Order placed: " + event.orderId());
    }
}
~~~

Khi `placeOrder` gọi `publishEvent`, Spring gửi event đến listener phù hợp đã đăng ký trong context.

Application event thường được xử lý đồng bộ trên thread phát event theo mặc định. Vì thế nếu listener làm việc lâu, lời gọi `publishEvent` cũng phải chờ listener hoàn tất. Có thể cấu hình asynchronous event multicaster hoặc dùng `@Async` khi phù hợp, nhưng khi chuyển sang xử lý bất đồng bộ cần thiết kế rõ executor, lỗi, thứ tự và tính nhất quán.

### 1.1. Event trong Spring Boot và event nghiệp vụ

Có hai nhóm event cần phân biệt:

**Spring Boot lifecycle event** mô tả tiến trình khởi động ứng dụng, ví dụ `ApplicationReadyEvent`.

**Application/domain event** mô tả một điều đã xảy ra trong nghiệp vụ, ví dụ `OrderPlacedEvent`.

Cả hai có thể được xử lý bằng `ApplicationListener` hoặc `@EventListener`, nhưng thời điểm và mục tiêu khác nhau. Lifecycle event có thể được phát trước khi bean thông thường được tạo; event nghiệp vụ thường được phát sau khi application context đã sẵn sàng.

## 2. Triển khai ApplicationListener<E>

`ApplicationListener` là interface của Spring:

~~~java
import org.springframework.context.ApplicationListener;
~~~

Listener có thể triển khai trực tiếp:

~~~java
@Component
public class OrderPlacedListener
        implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        System.out.println("Received order: " + event.orderId());
    }
}
~~~

Tham số generic `OrderPlacedEvent` cho biết loại event listener quan tâm. Spring có thể dùng kiểu này để lọc event phù hợp.

Một listener cho event Spring Boot:

~~~java
@Component
public class ReadyApplicationListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Application is ready");
    }
}
~~~

`ApplicationReadyEvent` được phát khi ứng dụng đã hoàn tất các bước startup và các runner đã chạy xong. Bean listener kiểu này phù hợp để thực hiện một phản ứng sau startup nếu công việc đó nên được quản lý bởi context.

### 2.1. Lọc event bằng kiểu generic

Nếu khai báo:

~~~java
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {
    // ...
}
~~~

listener chỉ quan tâm đến `ApplicationReadyEvent`.

Có thể triển khai listener nhận kiểu tổng quát hơn:

~~~java
public class BootEventListener
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        System.out.println(event.getClass().getSimpleName());
    }
}
~~~

Trong thực tế, chỉ nên nghe loại event rộng khi thật sự cần quan sát nhiều mốc lifecycle. Một listener nhận quá nhiều event có thể chứa nhiều nhánh điều kiện và khó bảo trì.

### 2.2. Listener có thể là bean hoặc đối tượng đăng ký trực tiếp

Một class implements `ApplicationListener` có thể được đăng ký bằng `@Component` hoặc `@Bean` để Spring context quản lý.

~~~java
@Configuration(proxyBeanMethods = false)
public class EventConfiguration {

    @Bean
    ApplicationListener<ApplicationReadyEvent> readyListener() {
        return event -> System.out.println("Ready event received");
    }
}
~~~

Cách đăng ký này phù hợp với event được phát sau khi listener bean đã được thêm vào context. Với event rất sớm, một bean trong context có thể được đăng ký quá muộn; phần sau sẽ trình bày cách xử lý.

## 3. Dùng @EventListener trên method

Thay vì triển khai interface, có thể đánh dấu method bằng `@EventListener`:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventHandlers {

    @EventListener
    public void handleOrderPlaced(OrderPlacedEvent event) {
        System.out.println("Order: " + event.orderId());
    }
}
~~~

Spring phát hiện method được đánh dấu trong bean và đăng ký method đó làm event listener.

Một method có thể nhận kiểu event trực tiếp qua tham số. Tên method tùy ý; kiểu tham số giúp Spring xác định loại event.

Có thể khai báo loại event tường minh:

~~~java
@EventListener(OrderPlacedEvent.class)
public void handle(Object event) {
    // ...
}
~~~

Dù vậy, kiểu tham số cụ thể thường giúp code dễ đọc hơn:

~~~java
@EventListener
public void handle(OrderPlacedEvent event) {
    // ...
}
~~~

### 3.1. Một class có thể có nhiều event handler

~~~java
@Component
public class ApplicationLifecycleHandlers {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Context refreshed; runners have not run yet");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Runners completed; application is ready");
    }

    @EventListener
    public void onFailed(ApplicationFailedEvent event) {
        System.err.println("Application startup failed");
    }
}
~~~

Các method này được đăng ký như các listener riêng cho từng event type. Listener bean chỉ có thể nhận những event được phát sau khi method listener đã được đăng ký.

### 3.2. Method listener có thể trả về event khác

Một `@EventListener` method có thể trả về một object event. Spring sẽ phát object được trả về như một event mới:

~~~java
@EventListener
public OrderNotificationEvent onOrderPlaced(OrderPlacedEvent event) {
    return new OrderNotificationEvent(event.orderId());
}
~~~

Ví dụ này giả định `OrderNotificationEvent` là kiểu event do ứng dụng định nghĩa. Listener khác có thể nhận event mới.

Không nên dùng return event để tạo chuỗi xử lý khó theo dõi. Nếu luồng nghiệp vụ phức tạp, một service điều phối tường minh thường dễ đọc hơn.

### 3.3. Event listener method không phải endpoint HTTP

`@EventListener` không tạo route web và không nhận request từ bên ngoài. Nó chỉ đăng ký method để xử lý application event trong Spring context.

Nếu cần xử lý HTTP request, dùng controller mapping như `@GetMapping` hoặc `@PostMapping`. Nếu cần xử lý message từ broker, dùng listener abstraction tương ứng như Kafka hoặc JMS listener; application event không tự thay thế message broker.

## 4. Các event quan trọng trong vòng đời Spring Boot

Spring Boot phát một chuỗi event trong quá trình `SpringApplication.run`. Một số event xuất hiện trước khi ApplicationContext được tạo; một số event xuất hiện sau refresh và sau khi runner hoàn tất.

Chuỗi lifecycle khái quát trong một ứng dụng Spring Boot hiện đại:

~~~text
SpringApplication bắt đầu
        │
        ▼
ApplicationStartingEvent
        │
        ▼
ApplicationEnvironmentPreparedEvent
        │
        ▼
ApplicationContextInitializedEvent
        │
        ▼
ApplicationPreparedEvent
        │
        ▼
ApplicationContext.refresh()
        │
        ▼
ContextRefreshedEvent
        │
        ▼
ApplicationStartedEvent
        │
        ▼
AvailabilityChangeEvent (LivenessState.CORRECT)
        │
        ▼
ApplicationRunner / CommandLineRunner
        │
        ▼
ApplicationReadyEvent
        │
        ▼
AvailabilityChangeEvent (ReadinessState.ACCEPTING_TRAFFIC)
~~~

Nếu startup thất bại, Boot có thể phát `ApplicationFailedEvent` trong quá trình xử lý lỗi.

Tên event và mốc lifecycle có thể thay đổi giữa các thế hệ Spring Boot. Các mốc dưới đây mô tả lifecycle phổ biến ở các dòng Boot hiện đại; hãy đối chiếu API version dự án khi cần phụ thuộc vào một event cụ thể.

### 4.1. ApplicationStartingEvent

Được phát rất sớm, khi `SpringApplication` vừa bắt đầu chạy.

Ở thời điểm này:

- Environment của ứng dụng chưa được chuẩn bị hoàn chỉnh.
- ApplicationContext chưa được tạo.
- Các bean ứng dụng chưa được đăng ký.
- Không thể dựa vào dependency injection từ application context.

Đây là event phù hợp để listener rất sớm ghi nhận việc startup bắt đầu hoặc cấu hình hành vi quan sát ban đầu. Listener cần được đăng ký trước khi gọi `run()`.

### 4.2. ApplicationEnvironmentPreparedEvent

Được phát sau khi Boot chuẩn bị Environment và trước khi ApplicationContext được tạo.

Listener có thể đọc environment, profiles và properties đã được nạp ở giai đoạn này:

~~~java
public class EnvironmentPreparedListener
        implements ApplicationListener<ApplicationEnvironmentPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationEnvironmentPreparedEvent event) {
        Environment environment = event.getEnvironment();

        System.out.println(
                "Active profiles: "
                        + Arrays.toString(environment.getActiveProfiles())
        );
    }
}
~~~

Listener này vẫn phải được đăng ký sớm qua `SpringApplication` hoặc cơ chế listener discovery tương ứng. Một bean trong ApplicationContext chưa thể nhận event đã phát trước khi context được tạo.

### 4.3. ApplicationContextInitializedEvent

Event này được phát sau khi ApplicationContext đã được tạo và các `ApplicationContextInitializer` đã chạy, nhưng trước khi các nguồn bean definition của ứng dụng được nạp đầy đủ vào context.

Nó hữu ích khi cần quan sát hoặc làm việc ở mốc context đã khởi tạo nhưng chưa bước vào giai đoạn chuẩn bị/refresh hoàn chỉnh.

Không nên coi đây là thời điểm mọi bean đã tồn tại. Các bean singleton thông thường chưa được tạo chỉ vì event này đã phát.

### 4.4. ApplicationPreparedEvent

Được phát sau khi context đã được chuẩn bị và bean definitions đã được nạp, nhưng trước khi context được refresh.

Ở mốc này, context đã có thông tin cấu hình và bean definition, nhưng các singleton chưa nhất thiết đã được khởi tạo. Listener có thể quan sát trạng thái chuẩn bị của context; không nên giả định mọi dependency đã sẵn sàng để sử dụng.

### 4.5. ContextRefreshedEvent

Đây là event của Spring Framework, được phát khi ApplicationContext hoàn tất refresh.

Với một context ứng dụng Spring Boot thông thường, các bean cần thiết đã được khởi tạo theo quá trình refresh (trừ những bean lazy hoặc các trường hợp đặc biệt).

Listener bean trong context có thể nhận event này nếu nó đã được đăng ký trước thời điểm phát event.

~~~java
@Component
public class ContextRefreshListener {

    @EventListener
    public void onRefresh(ContextRefreshedEvent event) {
        System.out.println("Application context refreshed");
    }
}
~~~

Nếu ứng dụng có parent-child context, mỗi context có thể phát event refresh riêng. Listener cần cân nhắc event source/context nếu không muốn xử lý nhiều lần.

### 4.6. ApplicationStartedEvent

Được phát sau khi ApplicationContext đã refresh và trước khi `ApplicationRunner` cùng `CommandLineRunner` được gọi.

Event này thích hợp khi cần biết context đã khởi động xong, nhưng các startup runner có thể vẫn chưa hoàn tất.

Đừng dùng `ApplicationStartedEvent` làm bằng chứng rằng mọi tác vụ khởi tạo do runner thực hiện đã xong.

### 4.7. AvailabilityChangeEvent với LivenessState.CORRECT

Sau mốc started, Boot cập nhật trạng thái liveness sang `CORRECT` trong lifecycle hiện đại.

Liveness cho biết tiến trình ứng dụng đã khởi động đủ để được xem là đang sống theo mô hình availability của Boot. Nó không tự chứng minh mọi dependency ngoài đều khỏe mạnh hoặc ứng dụng đã sẵn sàng nhận traffic.

### 4.8. ApplicationRunner và CommandLineRunner

Sau `ApplicationStartedEvent`, Boot gọi các bean triển khai `ApplicationRunner` và `CommandLineRunner`.

Đây là callback dành cho tác vụ chạy một lần sau khi context đã refresh và trước event ready:

~~~java
@Component
public class StartupDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Load startup data");
    }
}
~~~

Runner phù hợp với công việc như nạp dữ liệu khởi tạo, kiểm tra cấu hình nghiệp vụ hoặc chuẩn bị tài nguyên cần hoàn tất trước khi ứng dụng báo ready.

Runner không phải event listener. Nó là một callback startup riêng, có quy tắc ordering riêng và được Boot gọi trực tiếp trong quá trình run.

### 4.9. ApplicationReadyEvent

Được phát sau khi các runner hoàn tất. Đây là mốc báo rằng ứng dụng đã hoàn thành startup theo quy trình của Boot.

~~~java
@Component
public class ReadyListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Application startup completed");
    }
}
~~~

Bean listener trong context có thể nhận event này vì listener đã được đăng ký trong quá trình refresh trước đó.

Dùng event này khi cần phản ứng sau startup, chẳng hạn ghi nhận mốc sẵn sàng hoặc phát tín hiệu cho một thành phần nội bộ. Nếu cần chạy một tác vụ bắt buộc trước khi ứng dụng được xem là ready, cân nhắc runner thay vì bắt đầu tác vụ bất đồng bộ rồi lập tức trả về từ listener.

### 4.10. AvailabilityChangeEvent với ReadinessState.ACCEPTING_TRAFFIC

Sau mốc ready, Boot chuyển readiness sang `ACCEPTING_TRAFFIC` trong lifecycle tiêu chuẩn.

Readiness thể hiện ứng dụng có thể nhận traffic hay chưa. Nó khác liveness:

- Liveness: tiến trình có còn sống theo trạng thái ứng dụng không?
- Readiness: ứng dụng có sẵn sàng nhận yêu cầu không?

Nếu triển khai trên nền tảng orchestration, readiness state có thể được sử dụng bởi health indicator và cơ chế routing để quyết định có chuyển traffic tới instance hay không.

### 4.11. ApplicationFailedEvent

Được phát khi quá trình khởi động thất bại và Boot có thông tin về exception gây lỗi.

~~~java
public class StartupFailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();
        System.err.println("Startup failed: " + failure.getMessage());
    }
}
~~~

Vì event này có thể phát khi context chưa hoàn tất hoặc đã bị đóng trong quá trình xử lý lỗi, listener không nên giả định có thể inject và gọi mọi bean ứng dụng. Một listener đăng ký đủ sớm thường phù hợp hơn nếu cần quan sát lỗi ở mọi giai đoạn startup.

## 5. Đăng ký listener đủ sớm: điều quan trọng nhất

Không phải mọi listener đều có thể nhận mọi lifecycle event. Điều quyết định là listener đã được đăng ký vào nguồn phát event trước thời điểm event được publish hay chưa.

### 5.1. Listener là bean trong ApplicationContext

Ví dụ:

~~~java
@Component
public class ReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Ready");
    }
}
~~~

Hoặc:

~~~java
@Component
public class StartingListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Ready");
    }
}
~~~

Các listener dạng bean được phát hiện và đăng ký trong quá trình context refresh. Chúng phù hợp với các event phát sau khi listener đã được đăng ký, ví dụ `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent` và event runtime sau đó.

Chúng không thể nhận các event đã phát trước khi ApplicationContext được tạo và listener được kết nối, chẳng hạn `ApplicationStartingEvent` và `ApplicationEnvironmentPreparedEvent`.

### 5.2. Đăng ký bằng SpringApplication.addListeners trước run()

Nếu cần nhận event rất sớm, hãy tạo listener và đăng ký trực tiếp trên `SpringApplication` trước khi gọi `run()`.

~~~java
public class EarlyStartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
~~~

Lớp main:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addListeners(new EarlyStartupListener());

        application.run(args);
    }
}
~~~

Trong ứng dụng thông thường, có thể thay các annotation trên bằng `@SpringBootApplication`:

~~~java
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addListeners(new EarlyStartupListener());

        application.run(args);
    }
}
~~~

Điểm mấu chốt: listener được thêm trước `run()`, vì thế nó có mặt khi Boot phát event starting.

Có thể đăng ký nhiều listener:

~~~java
application.addListeners(
        new EarlyStartupListener(),
        new EnvironmentPreparedListener()
);
~~~

Các listener này không phải bean được tạo qua constructor injection của ApplicationContext. Nếu chúng cần dependency, hãy thiết kế để dùng dữ liệu có sẵn trên event hoặc environment, hoặc chuyển công việc cần bean sang giai đoạn sau khi context đã sẵn sàng.

### 5.3. Dùng SpringApplicationBuilder

Một cách khác là cấu hình qua `SpringApplicationBuilder`:

~~~java
new SpringApplicationBuilder(Application.class)
        .listeners(new EarlyStartupListener())
        .run(args);
~~~

Listener cũng được đăng ký trước khi ứng dụng chạy.

Cách này hữu ích khi xây dựng ứng dụng có nhiều context hoặc cần cấu hình builder theo chuỗi.

### 5.4. Đăng ký listener qua spring.factories

Nếu phát triển thư viện hoặc starter muốn listener tự được phát hiện khi ứng dụng dùng thư viện đó, có thể công bố listener trong file:

~~~text
META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.context.ApplicationListener=\
com.example.boot.EarlyStartupListener
~~~

Spring Boot dùng cơ chế SpringFactoriesLoader để phát hiện các listener được khai báo theo key này. Listener được tạo sớm để có thể nhận các event của SpringApplication trước khi application context tồn tại.

Cách này phù hợp khi listener thuộc thư viện và cần được cài đặt cùng dependency. Nó khác metadata auto-configuration imports:

- `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener` dùng để công bố application listener.
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` dùng để công bố auto-configuration trong các dòng Boot hiện đại.

Đừng chuyển listener sang file `AutoConfiguration.imports`; file đó không phải registry cho `ApplicationListener`.

### 5.5. Listener được tạo sớm cần tự quản lý dependency

Một early listener có thể được tạo bởi `SpringApplication` hoặc `SpringFactoriesLoader` trước khi ApplicationContext sẵn sàng. Vì vậy không nên viết:

~~~java
@Component
public class EarlyListener implements ApplicationListener<ApplicationStartingEvent> {

    private final SomeApplicationService service;

    public EarlyListener(SomeApplicationService service) {
        this.service = service;
    }

    // ...
}
~~~

và kỳ vọng Boot tự inject `SomeApplicationService` trước khi context được tạo. Listener đăng ký qua cơ chế early không được khởi tạo như một bean thông thường trong context.

Thay vào đó:

- Giữ early listener đơn giản, ít dependency.
- Đọc dữ liệu từ event hoặc Environment nếu event cung cấp.
- Ghi nhận thông tin cần thiết rồi chuyển phần xử lý có dependency sang một bean sau refresh.
- Nếu cần cấu hình bean trong context, cân nhắc `ApplicationContextInitializer` hoặc cấu hình Spring phù hợp với đúng lifecycle hook.

## 6. Bảng chọn cách đăng ký theo thời điểm event

| Event cần nhận | Listener bean trong context | addListeners trước run() / spring.factories |
| --- | --- | --- |
| `ApplicationStartingEvent` | Quá muộn | Phù hợp |
| `ApplicationEnvironmentPreparedEvent` | Quá muộn | Phù hợp |
| `ApplicationContextInitializedEvent` | Thường quá muộn | Phù hợp |
| `ApplicationPreparedEvent` | Không nên dựa vào bean listener | Phù hợp |
| `ContextRefreshedEvent` | Có thể nhận khi đã đăng ký trong refresh | Có thể nhận |
| `ApplicationStartedEvent` | Có thể nhận | Có thể nhận |
| `ApplicationReadyEvent` | Có thể nhận | Có thể nhận |
| Event nghiệp vụ sau startup | Có thể nhận | Có thể nhận |

Bảng này mô tả quy tắc thông thường của một context Boot. Với parent-child contexts hoặc custom lifecycle, cần kiểm tra chính xác context nào phát event và listener được gắn với context nào.

Một quy tắc thực hành dễ nhớ:

- Cần event trước khi context được tạo: đăng ký listener trước `run()`.
- Cần event trong hoặc sau refresh: listener bean là lựa chọn tự nhiên.
- Cần listener dùng dependency do Spring quản lý: ưu tiên listener bean ở giai đoạn context đã sẵn sàng.

## 7. Ordering: listener nào chạy trước?

Một event có thể được nhiều listener xử lý. Nếu thứ tự quan trọng, dùng `Ordered` hoặc `@Order`.

### 7.1. Với ApplicationListener

~~~java
@Component
@Order(10)
public class FirstReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("First");
    }
}
~~~

Listener khác:

~~~java
@Component
@Order(20)
public class SecondReadyListener
        implements ApplicationListener<ApplicationReadyEvent> {

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        System.out.println("Second");
    }
}
~~~

Giá trị order thấp hơn được ưu tiên trước khi Spring sắp xếp listener theo ordering contract.

Có thể triển khai `Ordered` trực tiếp:

~~~java
public class OrderedReadyListener
        implements ApplicationListener<ApplicationReadyEvent>, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void onApplicationEvent(ApplicationReadyEvent event) {
        // ...
    }
}
~~~

### 7.2. Với @EventListener method

~~~java
@Component
public class ReadyHandlers {

    @EventListener
    @Order(10)
    public void prepareMetrics(ApplicationReadyEvent event) {
        System.out.println("Prepare metrics");
    }

    @EventListener
    @Order(20)
    public void logReady(ApplicationReadyEvent event) {
        System.out.println("Log ready");
    }
}
~~~

`@Order` giúp điều khiển thứ tự các listener cùng xử lý event trong cơ chế Spring event. Không nên dùng nó để thay thế dependency giữa các bước nghiệp vụ.

### 7.3. Listener order không thay đổi thứ tự lifecycle event

`@Order` chỉ sắp xếp listener cùng xử lý một event theo quy tắc ordering. Nó không thể làm `ApplicationReadyEvent` phát trước `ApplicationStartedEvent` hoặc thay đổi thứ tự lifecycle do Spring Boot quản lý.

Nếu tác vụ B cần hoàn tất sau tác vụ A, cách rõ ràng là điều phối hai tác vụ trong cùng một service/runner thay vì hy vọng thứ tự giữa các event khác nhau sẽ giải quyết dependency.

## 8. @EventListener và xử lý bất đồng bộ

Mặc định, listener được gọi đồng bộ trong luồng phát event. Nếu listener thực hiện công việc lâu, startup hoặc request phát event có thể bị chặn.

Có thể đánh dấu method listener bằng `@Async` khi ứng dụng đã bật async processing:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class AsyncReadyListener {

    @Async
    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        // Công việc nền có thể chạy lâu.
    }
}
~~~

Cần cân nhắc:

- Tạo executor phù hợp thay vì để mọi tác vụ dùng chung một executor không kiểm soát.
- Xử lý exception vì lỗi trong async listener không được truyền ngược như lời gọi đồng bộ thông thường.
- Không giả định listener hoàn tất trước khi event publisher tiếp tục.
- Không dùng async cho công việc bắt buộc phải xong trước khi ứng dụng báo ready nếu Boot không được cấu hình chờ công việc đó.
- Đặt giới hạn thời gian, retry và idempotency cho tác vụ có side effect.

Nếu một bước khởi tạo phải hoàn thành trước khi ứng dụng được đánh dấu sẵn sàng, `ApplicationRunner` hoặc `CommandLineRunner` thường phù hợp hơn. Runner chạy trong chuỗi startup trước `ApplicationReadyEvent`.

## 9. So sánh listener với ApplicationRunner và CommandLineRunner

Cả listener và runner đều có thể thực hiện công việc lúc startup, nhưng lifecycle hook khác nhau.

### 9.1. ApplicationRunner

~~~java
@Component
public class ReferenceDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Nạp dữ liệu tham chiếu sau khi context refresh.
    }
}
~~~

`ApplicationRunner` nhận `ApplicationArguments`, cho phép truy cập tham số dòng lệnh đã được parse.

### 9.2. CommandLineRunner

~~~java
@Component
public class StartupReporter implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Arguments count: " + args.length);
    }
}
~~~

`CommandLineRunner` nhận mảng chuỗi argument gốc.

### 9.3. Bảng so sánh

| Tiêu chí | ApplicationListener / @EventListener | ApplicationRunner | CommandLineRunner |
| --- | --- | --- | --- |
| Mục tiêu | Phản ứng khi event được phát | Chạy một tác vụ sau refresh | Chạy một tác vụ sau refresh |
| Kích hoạt | Event tương ứng | Boot gọi trong startup | Boot gọi trong startup |
| Nhận biết lifecycle event | Có | Không trực tiếp | Không trực tiếp |
| Nhận command-line args | Qua event phù hợp hoặc Environment | `ApplicationArguments` | `String... args` |
| Có thể chạy trước ApplicationReadyEvent | Tùy event; runner chạy trước ready | Có | Có |
| Phù hợp với | Quan sát lifecycle, phản ứng event | Startup task có cấu trúc | Startup task đơn giản |

Nếu cần xử lý khi `ApplicationReadyEvent` phát, dùng listener. Nếu cần chạy công việc bắt buộc hoàn tất trước ready, dùng runner. Nếu cần nhận event rất sớm, listener phải được đăng ký trước khi context tồn tại.

## 10. Event listener không phải cơ chế lưu trữ message bền vững

Spring application event thường chỉ tồn tại trong process và context hiện tại:

- Không có replay mặc định sau khi ứng dụng restart.
- Không có durable queue hoặc delivery guarantee giữa các process.
- Listener chưa đăng ký khi event phát sẽ không tự nhận lại event cũ.
- Exception và retry phụ thuộc cách event multicaster/executor được cấu hình.
- Event đồng bộ có thể ảnh hưởng trực tiếp đến latency của publisher.

Nếu cần gửi event giữa các service, lưu trữ event để xử lý lại, hoặc bảo đảm message tồn tại qua restart, hãy cân nhắc message broker hoặc một cơ chế event persistence phù hợp.

Application event rất hữu ích để tách các thành phần trong cùng một ứng dụng, nhưng không nên coi nó là Kafka, RabbitMQ hay một event store.

## 11. Ví dụ hoàn chỉnh: ghi nhận các mốc startup

Có thể đăng ký một early listener để nghe event trước context:

~~~java
public class EarlyLifecycleListener
        implements ApplicationListener<SpringApplicationEvent> {

    @Override
    public void onApplicationEvent(SpringApplicationEvent event) {
        System.out.println(
                "Early lifecycle event: "
                        + event.getClass().getSimpleName()
        );
    }
}
~~~

Main class:

~~~java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(DemoApplication.class);

        app.addListeners(new EarlyLifecycleListener());
        app.run(args);
    }
}
~~~

Listener này được đăng ký trước `run()` và có thể quan sát các `SpringApplicationEvent` phù hợp trong quá trình startup.

Để xử lý event sau khi context sẵn sàng, dùng bean:

~~~java
@Component
public class ApplicationLifecycleLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ApplicationLifecycleLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        log.info("Context refreshed; startup runners are next");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("Startup runners completed; application is ready");
    }

    @EventListener
    public void onFailure(ApplicationFailedEvent event) {
        log.error("Application startup failed", event.getException());
    }
}
~~~

Ví dụ minh họa hai nhóm thời điểm:

- Early listener đăng ký với `SpringApplication` để nhận lifecycle event trước context.
- Listener bean dùng `@EventListener` để xử lý event sau khi method đã được đăng ký trong context.

Không nên dùng một listener bean duy nhất để kỳ vọng nhận mọi event từ lúc JVM bắt đầu khởi động.

## 12. Kiểm thử listener

### 12.1. Kiểm thử @EventListener trong context

Có thể tạo context nhỏ và phát event thủ công:

~~~java
class OrderEventListenerTest {

    @Test
    void handlesPublishedOrderEvent() {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                        OrderEventListenerConfiguration.class
                );

        try {
            OrderEventRecorder recorder =
                    context.getBean(OrderEventRecorder.class);

            context.publishEvent(new OrderPlacedEvent("order-123"));

            assertEquals("order-123", recorder.lastOrderId());
        } finally {
            context.close();
        }
    }
}
~~~

Listener recorder:

~~~java
@Component
public class OrderEventRecorder {
    private String lastOrderId;

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        this.lastOrderId = event.orderId();
    }

    public String lastOrderId() {
        return lastOrderId;
    }
}
~~~

Cấu hình test:

~~~java
@Configuration
@ComponentScan(basePackageClasses = OrderEventRecorder.class)
class OrderEventListenerConfiguration {
}
~~~

Ví dụ cần import JUnit và Spring Context phù hợp. Test xác nhận event được phát sau khi context và listener đã sẵn sàng.

### 12.2. Kiểm thử early listener

Early listener có thể được kiểm tra bằng cách tạo `SpringApplication` và đăng ký listener trước khi chạy:

~~~java
@SpringBootTest
class EarlyListenerTest {
    // Có thể dùng ApplicationContextRunner hoặc một SpringApplication test riêng
    // để xác nhận listener nhận đúng lifecycle event.
}
~~~

Khi kiểm tra event rất sớm, đừng chỉ tạo listener như một bean trong test context. Cần kiểm tra chính đường đăng ký trước `run()` mà ứng dụng production sử dụng.

Có thể tách phần ghi nhận event thành một class đơn giản và truyền một recorder vào listener trong test nếu listener được tạo thủ công. Điều này giúp xác nhận logic mà không phụ thuộc vào việc Spring context đã tồn tại.

### 12.3. Kiểm thử runner khác với listener

Nếu mục tiêu là xác nhận dữ liệu đã được nạp trước `ApplicationReadyEvent`, hãy kiểm tra runner hoàn tất và event ready được phát sau đó. Không nên chỉ gọi method `run` bằng tay rồi coi đó là kiểm tra đầy đủ lifecycle của Boot.

## 13. Những lỗi thường gặp

### 13.1. @EventListener không nhận ApplicationStartingEvent

**Nguyên nhân:** Bean chứa method listener chỉ được đăng ký trong ApplicationContext, nhưng `ApplicationStartingEvent` phát trước khi context được tạo.

**Cách xử lý:** Đăng ký `ApplicationListener` qua `SpringApplication.addListeners` trước `run()` hoặc công bố listener qua `spring.factories`.

### 13.2. Listener không nhận ApplicationEnvironmentPreparedEvent

**Nguyên nhân:** Event phát trước giai đoạn tạo và refresh ApplicationContext. Bean listener không thể nhận event đã phát.

**Cách xử lý:** Dùng early listener. Đọc Environment từ event nếu cần cấu hình đã chuẩn bị.

### 13.3. Early listener không được inject dependency

**Nguyên nhân:** Listener được tạo bởi SpringApplication hoặc SpringFactoriesLoader trước khi ApplicationContext sẵn sàng.

**Cách xử lý:** Giữ listener độc lập, dùng dữ liệu từ event, hoặc chuyển công việc cần bean sang listener bean/runner sau refresh.

### 13.4. Listener chạy hai lần

**Nguyên nhân có thể:**

- Listener được đăng ký cả qua `addListeners` và qua `spring.factories`.
- Ứng dụng có nhiều context trong hierarchy.
- Cùng một logic được đăng ký ở nhiều bean hoặc method.
- Một event được phát ở nhiều context.

**Cách xử lý:** Kiểm tra tất cả đường đăng ký, xác định context phát event và làm handler idempotent nếu có thể nhận event lặp.

### 13.5. Listener làm startup chậm

**Nguyên nhân:** Listener chạy đồng bộ và thực hiện tác vụ lâu.

**Cách xử lý:** Chuyển công việc bắt buộc trước ready sang runner; nếu có thể chạy nền sau ready, dùng async executor được cấu hình rõ ràng. Đo thời gian thực tế và xử lý lỗi async.

### 13.6. Dùng ApplicationReadyEvent để chạy công việc bắt buộc trước ready

**Nguyên nhân:** Event ready chỉ phát sau khi runner hoàn tất. Một listener async trên event này có thể bắt đầu công việc sau khi ứng dụng đã được đánh dấu ready.

**Cách xử lý:** Dùng `ApplicationRunner` hoặc `CommandLineRunner` cho tác vụ phải hoàn tất trước ready.

### 13.7. Dùng @Order để thay đổi thứ tự lifecycle

**Nguyên nhân:** Nhầm thứ tự listener cùng một event với thứ tự các event lifecycle.

**Cách xử lý:** `@Order` sắp xếp listener cho event; không thay đổi thứ tự event do Boot phát.

### 13.8. Dùng application event cho giao tiếp liên service

**Nguyên nhân:** Nhầm event trong process với message broker.

**Cách xử lý:** Dùng broker hoặc cơ chế truyền message phù hợp khi cần giao tiếp qua mạng, lưu trữ bền vững, retry và replay.

## 14. Quy trình chọn listener và thời điểm đăng ký

Khi thiết kế một listener, hãy trả lời các câu hỏi theo thứ tự:

1. **Event nào cần xử lý?** Event lifecycle của Boot hay event nghiệp vụ do ứng dụng phát?
2. **Event phát khi nào?** Trước khi context tạo, trong refresh hay sau ready?
3. **Listener có cần dependency từ Spring không?** Nếu có, listener bean trong context thường phù hợp hơn.
4. **Có cần nghe event rất sớm không?** Dùng `SpringApplication.addListeners` hoặc `spring.factories`.
5. **Có cần thứ tự với listener khác không?** Dùng `@Order` hoặc `Ordered`.
6. **Tác vụ phải hoàn tất trước ready không?** Dùng runner thay vì listener async sau ready.
7. **Tác vụ có thể chạy lâu không?** Cân nhắc executor, async và xử lý lỗi.
8. **Event có cần bền vững hoặc truyền qua service khác không?** Nếu có, dùng messaging infrastructure phù hợp.

Chọn lifecycle hook theo yêu cầu thực tế giúp tránh listener chạy quá muộn, phụ thuộc bean chưa tồn tại hoặc vô tình kéo dài thời gian startup.

## 15. Bài thực hành

### Bài A: Nghe ApplicationReadyEvent bằng @EventListener

Tạo bean có method `@EventListener` nhận `ApplicationReadyEvent`. Chạy ứng dụng và xác nhận log xuất hiện sau các runner.

### Bài B: So sánh ApplicationStartedEvent và ApplicationReadyEvent

Tạo hai listener riêng. Thêm một `ApplicationRunner` ghi log.

Quan sát thứ tự:

- Context refresh hoàn tất.
- `ApplicationStartedEvent` được phát.
- Runner thực thi.
- `ApplicationReadyEvent` được phát.

Giải thích vì sao hai event này không thể hoán đổi cho nhau.

### Bài C: Đăng ký ApplicationStartingEvent đủ sớm

Tạo class implements `ApplicationListener<ApplicationStartingEvent>`. Đăng ký bằng `SpringApplication.addListeners` trước `run()`.

Sau đó thử biến listener thành `@Component` trong context và quan sát vì sao nó không nhận event starting.

### Bài D: Đăng ký listener qua spring.factories

Tạo file `META-INF/spring.factories` với key `org.springframework.context.ApplicationListener`. Đóng gói listener vào module test hoặc thư viện thử nghiệm và xác nhận Boot phát hiện listener.

So sánh với file `AutoConfiguration.imports` và giải thích vai trò riêng của hai metadata file.

### Bài E: Ordering

Tạo hai `@EventListener` method cùng nhận `ApplicationReadyEvent`. Gắn `@Order(1)` và `@Order(2)`, quan sát thứ tự log.

Sau đó phát một event khác và xác nhận `@Order` không thay đổi thứ tự lifecycle giữa hai event.

### Bài F: Chuyển tác vụ startup sang runner

Viết một listener `ApplicationReadyEvent` đang thực hiện tác vụ bắt buộc. Chuyển tác vụ đó sang `ApplicationRunner` và xác nhận công việc hoàn tất trước khi event ready phát.

### Bài G: Kiểm thử event nghiệp vụ

Tạo `OrderPlacedEvent`, phát bằng `ApplicationEventPublisher` và kiểm thử listener bằng context nhỏ. Xác nhận listener không cần HTTP request để được gọi.

## 16. Câu hỏi tự kiểm tra

**1. `ApplicationListener` và `@EventListener` khác nhau thế nào?**

`ApplicationListener<E>` là interface được triển khai bằng method `onApplicationEvent`. `@EventListener` đánh dấu method trong bean để Spring đăng ký xử lý event tương ứng.

**2. Vì sao bean listener không nhận được `ApplicationStartingEvent`?**

Vì event phát trước khi ApplicationContext được tạo và listener bean được đăng ký.

**3. Cách nào đăng ký listener đủ sớm?**

Dùng `SpringApplication.addListeners` hoặc `SpringApplicationBuilder.listeners` trước `run()`; với listener thuộc thư viện, có thể công bố qua `META-INF/spring.factories` bằng key `org.springframework.context.ApplicationListener`.

**4. `ApplicationStartedEvent` và `ApplicationReadyEvent` khác nhau thế nào?**

Started phát sau context refresh nhưng trước các runner. Ready phát sau khi các runner hoàn tất.

**5. Khi nào dùng ApplicationRunner thay cho @EventListener?**

Khi cần một tác vụ startup có cấu trúc phải hoàn tất trước khi ứng dụng báo ready.

**6. `@Order` có thay đổi thứ tự các lifecycle event không?**

Không. Nó sắp xếp listener cùng xử lý một event theo quy tắc ordering.

**7. Listener chạy đồng bộ hay bất đồng bộ?**

Mặc định event listener xử lý đồng bộ. Có thể dùng async khi cấu hình phù hợp, nhưng cần quản lý executor và lỗi.

**8. `@EventListener` có phải message broker không?**

Không. Đây là event nội bộ trong process, không cung cấp durable delivery hoặc replay mặc định.

**9. Vì sao early listener nên ít dependency?**

Vì listener có thể được tạo trước ApplicationContext, nên chưa thể nhận các bean dependency thông qua constructor injection thông thường.

## 17. Kết luận

`ApplicationListener` và `@EventListener` là hai cách xử lý application event trong Spring. Interface phù hợp khi muốn một listener class rõ ràng và kiểu event cụ thể; annotation phù hợp khi muốn đăng ký handler trực tiếp trên method của bean.

Khi xử lý lifecycle event của Spring Boot, **thời điểm đăng ký quyết định event nào listener có thể nhận**. Listener bean trong context phù hợp với event phát trong hoặc sau refresh. Muốn nhận event rất sớm như `ApplicationStartingEvent` hay `ApplicationEnvironmentPreparedEvent`, hãy đăng ký trước `SpringApplication.run()` bằng `addListeners` hoặc công bố listener trong `spring.factories`.

Hãy dùng `@Order` để sắp xếp các listener cùng nhận một event, dùng runner cho công việc bắt buộc hoàn tất trước `ApplicationReadyEvent` và cân nhắc async cho tác vụ nền có thể tách khỏi startup. Chọn đúng hook theo lifecycle giúp listener nhận event đúng lúc, sử dụng dependency đúng giai đoạn và giữ quá trình khởi động dễ kiểm soát.

