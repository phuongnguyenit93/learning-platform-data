# Callback, runner hoặc listener không được gọi đúng thời điểm mong đợi

Trong Spring Boot, một đoạn code có thể được gọi tự động khi bean được tạo, khi ApplicationContext hoàn tất refresh, sau khi ứng dụng khởi động, khi một application event được phát hoặc khi ứng dụng bắt đầu dừng. Những điểm mở rộng này rất tiện, nhưng chúng không có cùng thời điểm và cũng không có cùng điều kiện kích hoạt.

Một số tình huống thường gặp:

- Method `@PostConstruct` chạy trước khi bạn nghĩ rằng toàn bộ ứng dụng đã sẵn sàng.
- `CommandLineRunner` không chạy vì bean không được đăng ký hoặc startup đã thất bại trước giai đoạn runner.
- `ApplicationReadyEvent` không xuất hiện vì một runner ném exception.
- `@EventListener` không nhận được event đã được phát trước khi listener được đăng ký.
- `@TransactionalEventListener` không chạy vì event được publish ngoài transaction.
- Listener chạy bất đồng bộ nên log xuất hiện muộn hơn hoặc thứ tự hoàn tất khác mong đợi.
- Test thứ hai không thấy runner chạy vì Spring tái sử dụng ApplicationContext đã cache.
- Callback shutdown không chạy khi process bị kill cưỡng bức.

Bài học thuộc chương **Chẩn đoán lỗi** của **Spring Boot Fundamentals**. Mục tiêu là hiểu đúng lifecycle, chọn đúng callback/event cho công việc, nhận diện nguyên nhân khi callback không chạy hoặc chạy sai thời điểm, và có quy trình kiểm tra dựa trên bằng chứng.

## 1. Phân biệt callback, runner và listener

Ba từ này thường bị dùng lẫn nhau, nhưng trong Spring chúng chỉ những cơ chế khác nhau.

| Cơ chế | Được kích hoạt khi nào? | Ví dụ |
|---|---|---|
| Bean lifecycle callback | Trong quá trình tạo hoặc hủy một bean | `@PostConstruct`, `@PreDestroy` |
| Application runner | Sau khi ApplicationContext refresh thành công, trong quá trình startup | `ApplicationRunner`, `CommandLineRunner` |
| Application event listener | Khi một event phù hợp được publish trong event system | `@EventListener`, `ApplicationListener` |
| Context lifecycle callback | Khi context refresh hoặc close | `ContextRefreshedEvent`, `ContextClosedEvent` |
| Lifecycle component | Khi container bắt đầu/dừng các thành phần có lifecycle | `SmartLifecycle` |
| Scheduled task | Theo lịch sau khi scheduling được kích hoạt | `@Scheduled` |

Một callback không chạy không nhất thiết có nghĩa Spring bị lỗi. Có thể callback được gắn vào một lifecycle phase khác với phase bạn đang quan sát, bean chưa được tạo, event chưa được publish hoặc điều kiện kích hoạt không đúng.

### 1.1. Bắt đầu bằng câu hỏi “tôi đang chờ điều gì?”

Trước khi sửa code, hãy viết rõ:

- Tôi muốn method chạy **một lần khi bean được tạo**?
- Tôi muốn chạy **sau khi toàn bộ singleton beans được khởi tạo**?
- Tôi muốn chạy **sau khi Spring context refresh**?
- Tôi muốn chạy **sau khi tất cả startup runners hoàn tất**?
- Tôi muốn xử lý **mỗi event cụ thể**?
- Tôi muốn chạy **sau khi transaction commit**?
- Tôi muốn chạy **định kỳ hoặc theo một scheduler**?
- Tôi muốn dọn tài nguyên **khi context đóng**?

Nếu chưa xác định được thời điểm mong đợi, rất dễ chọn sai extension point.

## 2. Timeline khởi động Spring Boot

Một ứng dụng Spring Boot đi qua nhiều giai đoạn. Những callback khác nhau được kích hoạt ở các điểm khác nhau.

Sơ đồ khái quát:

```text
SpringApplication.run(...)
          │
          ▼
ApplicationStartingEvent
          │
          ▼
Chuẩn bị Environment và cấu hình
          │
          ▼
ApplicationEnvironmentPreparedEvent
          │
          ▼
Tạo ApplicationContext
          │
          ▼
ApplicationContextInitializedEvent
          │
          ▼
ApplicationPreparedEvent
          │
          ▼
Load bean definitions / refresh context
          │
          ├── Bean construction
          ├── Dependency injection
          ├── @PostConstruct
          ├── afterPropertiesSet()
          ├── custom init method
          ├── SmartInitializingSingleton
          ├── SmartLifecycle start
          └── ContextRefreshedEvent
          │
          ▼
ApplicationStartedEvent
          │
          ▼
LivenessState.CORRECT
          │
          ▼
ApplicationRunner / CommandLineRunner
          │
          ▼
ApplicationReadyEvent
          │
          ▼
ReadinessState.ACCEPTING_TRAFFIC
          │
          ▼
Ứng dụng sẵn sàng
```

Đây là timeline chính để chẩn đoán startup. Một số sự kiện chi tiết có thể xen giữa tùy loại application context, web server và phiên bản Spring Boot. Điều quan trọng là phân biệt **bean initialization**, **context refresh**, **runner execution** và **application ready**.

### 2.1. Những mốc cần nhớ

| Mốc | Ý nghĩa |
|---|---|
| `ApplicationStartingEvent` | SpringApplication bắt đầu chạy; Environment và context chưa được chuẩn bị đầy đủ |
| `ApplicationEnvironmentPreparedEvent` | Environment đã sẵn sàng cho các bước tiếp theo |
| `ApplicationContextInitializedEvent` | ApplicationContext đã được tạo và initializers đã được áp dụng |
| `ApplicationPreparedEvent` | Context đã chuẩn bị, bean definitions sắp được load/refresh theo bootstrap |
| `ContextRefreshedEvent` | Một ApplicationContext đã hoàn tất refresh |
| `ApplicationStartedEvent` | Boot đã refresh context; startup runners chưa được gọi |
| `ApplicationReadyEvent` | Các startup runners đã hoàn tất; ứng dụng chuyển sang giai đoạn ready |
| `ApplicationFailedEvent` | Startup thất bại ở một giai đoạn được SpringApplication xử lý |

`ApplicationReadyEvent` là mốc phù hợp khi một tác vụ thật sự cần chờ các startup runners hoàn tất. `ContextRefreshedEvent` xuất hiện sớm hơn và có thể được phát cho nhiều context trong một hệ phân cấp.

### 2.2. Web server đã mở cổng chưa có nghĩa ứng dụng đã ready

Trong web application, embedded server có thể được khởi tạo trong quá trình context refresh. Tuy nhiên, Spring Boot quản lý trạng thái readiness riêng; các startup runners vẫn còn phải chạy trước khi ứng dụng chuyển sang `ReadinessState.ACCEPTING_TRAFFIC`.

Vì vậy, không nên suy luận chỉ từ việc thấy port đang listen rằng mọi startup work đã hoàn tất.

## 3. Bean lifecycle callback chạy ở đâu?

Các callback gắn với vòng đời bean thường xảy ra khi Spring tạo và khởi tạo bean.

Ví dụ:

```java
@Component
public class CacheWarmup {

    @PostConstruct
    void initialize() {
        System.out.println("Bean initialized");
    }
}
```

`@PostConstruct` được gọi sau khi dependency injection cho bean hoàn tất và trong giai đoạn initialization của bean.

Nó **không có nghĩa toàn bộ ApplicationContext đã sẵn sàng**. Những bean khác có thể chưa được khởi tạo, và application startup runners chưa chạy.

### 3.1. Thứ tự initialization callback phổ biến

Trong lifecycle của một bean singleton thông thường, thứ tự khái quát:

1. Constructor.
2. Dependency injection và các bước populate properties.
3. BeanPostProcessor trước initialization, trong đó có xử lý `@PostConstruct`.
4. `InitializingBean.afterPropertiesSet()` nếu bean implement interface đó.
5. Custom init method khai báo trong bean definition/`@Bean`.
6. BeanPostProcessor sau initialization, có thể bọc bean bằng proxy.
7. Bean được đưa vào sử dụng theo lifecycle của container.

Thứ tự cụ thể còn phụ thuộc post-processors và cơ chế tạo bean. Không nên dùng một callback để suy ra rằng tất cả bean khác đã hoàn tất initialization.

### 3.2. @PostConstruct không phải ApplicationReadyEvent

Ví dụ:

```java
@Component
public class StartupProbe {

    private static final Logger log =
            LoggerFactory.getLogger(StartupProbe.class);

    @PostConstruct
    void afterInjection() {
        log.info("StartupProbe bean initialized");
    }

    @EventListener(ApplicationReadyEvent.class)
    void afterApplicationReady() {
        log.info("Application is ready");
    }
}
```

Hai log có thể xuất hiện cách nhau bởi quá trình tạo các bean khác, refresh context và chạy startup runners.

Nếu method cần gọi các bean khác với giả định toàn bộ context đã sẵn sàng, `@PostConstruct` thường không phải nơi thích hợp.

### 3.3. @PostConstruct không chạy nếu bean chưa được tạo

Ví dụ:

```java
@Component
@Lazy
public class ExpensiveInitializer {

    @PostConstruct
    void initialize() {
        System.out.println("ExpensiveInitializer initialized");
    }
}
```

Với lazy initialization, bean có thể chưa được tạo trong giai đoạn context refresh. Callback chỉ chạy khi bean thực sự được instantiate.

Một số cơ chế như runner lookup hoặc listener infrastructure có thể khiến bean được tạo sau đó. Vì vậy, đừng kết luận rằng annotation không hoạt động chỉ vì log không xuất hiện ngay khi context refresh.

### 3.4. @PostConstruct không phải nơi thích hợp cho mọi startup task

Tránh đặt trong `@PostConstruct` những công việc:

- Cần tất cả application beans đã sẵn sàng.
- Cần web server đã hoàn tất lifecycle.
- Cần các startup runners khác chạy trước.
- Tốn nhiều thời gian hoặc block thread tạo context.
- Cần retry/backoff phức tạp.
- Cần quản lý transaction hoặc async workflow rõ ràng.

Hãy chọn runner, event listener hoặc một component lifecycle chuyên biệt theo yêu cầu.

## 4. InitializingBean và custom init method

Ngoài `@PostConstruct`, Spring hỗ trợ interface `InitializingBean`:

```java
@Component
public class ConnectionRegistry implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Kiểm tra cấu hình và chuẩn bị trạng thái của bean.
    }
}
```

Hoặc dùng custom init method:

```java
@Configuration
class ClientConfiguration {

    @Bean(initMethod = "initialize")
    ClientRegistry clientRegistry() {
        return new ClientRegistry();
    }
}
```

Ba cách thường gặp:

| Cách | Ưu điểm | Lưu ý |
|---|---|---|
| `@PostConstruct` | Annotation rõ ràng, phổ biến | Callback trong bean initialization |
| `InitializingBean` | Hợp đồng lifecycle bằng interface | Class phụ thuộc Spring API |
| `@Bean(initMethod = "...")` | Cấu hình lifecycle từ bean definition | Phải khai báo method hợp lệ |

Chúng không phải startup runners. Chúng phục vụ việc hoàn thiện **một bean cụ thể**.

### 4.1. Nếu cần chạy sau tất cả singleton beans?

Spring có `SmartInitializingSingleton`:

```java
@Component
public class SingletonInitializationReporter
        implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        // Các regular singleton beans đã được pre-instantiate.
    }
}
```

Callback này chạy sau khi quá trình pre-instantiation các regular singleton beans hoàn tất, trong lúc refresh context.

Nó vẫn diễn ra **trước ApplicationStartedEvent và trước startup runners** trong quy trình Spring Boot thông thường. Nếu cần chờ runners, dùng mốc sau runners như `ApplicationReadyEvent`.

### 4.2. Không tạo vòng phụ thuộc lifecycle

Nếu bean A trong `@PostConstruct` gọi bean B, còn bean B lại phụ thuộc A hoặc gọi ngược A trong initialization, bạn có thể tạo vòng phụ thuộc hoặc quan sát trạng thái chưa hoàn chỉnh.

Hãy giữ bean initialization đơn giản: validate state cục bộ, chuẩn bị dữ liệu của bean và fail sớm nếu cấu hình không hợp lệ.

## 5. ApplicationRunner và CommandLineRunner

Hai interface này dành cho công việc chạy trong giai đoạn startup **sau khi ApplicationContext refresh thành công**.

### 5.1. CommandLineRunner

```java
@Component
public class InitialDataRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Runner started");
    }
}
```

Nó nhận các command-line arguments dưới dạng chuỗi.

### 5.2. ApplicationRunner

```java
@Component
public class ConfigurationReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Option names: " + args.getOptionNames()
        );
    }
}
```

`ApplicationArguments` hỗ trợ phân biệt option arguments dạng `--key=value` và non-option arguments.

### 5.3. Khai báo runner bằng @Bean

Không bắt buộc runner phải là một class `@Component`:

```java
@Configuration
class StartupConfiguration {

    @Bean
    ApplicationRunner initialCheck() {
        return args -> {
            System.out.println("Initial check completed");
        };
    }
}
```

Nếu dùng `@Bean`, kiểm tra method có thực sự được cấu hình trong class được Spring scan/import hay không.

### 5.4. Runner không chạy ở mỗi request

Runner thường chạy một lần trong mỗi lần SpringApplication khởi động ApplicationContext. Nó không phải:

- HTTP request callback.
- Scheduled task.
- Message consumer callback.
- Callback được gọi mỗi lần một bean được inject.
- Event listener cho mọi lần refresh tùy ý.

Nếu muốn xử lý mỗi request, đặt logic ở controller/filter/interceptor hoặc service boundary phù hợp. Nếu muốn chạy định kỳ, dùng scheduling. Nếu muốn xử lý message, dùng listener của message broker.

## 6. Runner không được gọi: các nguyên nhân phổ biến

Khi `run(...)` không chạy, kiểm tra theo thứ tự.

### 6.1. Bean runner chưa được đăng ký

Sai:

```java
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import started");
    }
}
```

Class trên không có `@Component` và cũng không được khai báo bằng `@Bean`. Nếu không có cơ chế đăng ký khác, Spring không biết phải tạo bean này.

Đúng:

```java
@Component
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import started");
    }
}
```

Hoặc:

```java
@Configuration
class ImportConfiguration {

    @Bean
    CommandLineRunner importRunner() {
        return args -> System.out.println("Import started");
    }
}
```

### 6.2. Package nằm ngoài component scan

Giả sử main class:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Mặc định component scan thường bắt đầu từ package của class cấu hình này và các package con.

Nếu runner nằm ở:

```text
com.other.startup.ImportRunner
```

nó có thể nằm ngoài scan boundary.

Giải pháp:

- Đặt runner dưới package gốc của application.
- Hoặc khai báo component scan có chủ đích.
- Hoặc import configuration chứa bean runner.

Ví dụ:

```java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.shop",
                "com.other.startup"
        }
)
public class ShopApplication {
}
```

Đừng mở component scan toàn bộ package rộng hơn mức cần thiết nếu có thể gây đăng ký nhầm bean.

### 6.3. Bean bị loại bởi profile hoặc condition

Ví dụ:

```java
@Component
@Profile("maintenance")
public class MaintenanceRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // ...
    }
}
```

Nếu profile `maintenance` không active, bean không được đăng ký.

Tương tự với `@ConditionalOnProperty`:

```java
@Component
@ConditionalOnProperty(
        prefix = "app.import",
        name = "enabled",
        havingValue = "true"
)
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // ...
    }
}
```

Nếu property không có hoặc không có giá trị `true` theo điều kiện đã cấu hình, runner không xuất hiện trong context.

Kiểm tra active profiles và giá trị property hiệu lực trong đúng môi trường đang chạy.

### 6.4. Context không đi qua SpringApplication startup path

`ApplicationRunner` và `CommandLineRunner` được gọi bởi quy trình startup của `SpringApplication`.

Nếu bạn tự tạo một context và gọi `refresh()` theo cách thủ công, đừng mặc định Spring sẽ tự chạy toàn bộ Boot runner orchestration như `SpringApplication.run(...)`.

Trong ứng dụng Spring Boot bình thường, entry point nên gọi:

```java
SpringApplication.run(ShopApplication.class, args);
```

### 6.5. Startup thất bại trước giai đoạn runner

Nếu một bean constructor, configuration properties binding hoặc context refresh thất bại, Spring Boot chưa tới giai đoạn gọi runners.

Tìm lỗi đầu tiên trong cause chain, ví dụ:

```text
ApplicationContextException
BeanCreationException
UnsatisfiedDependencyException
ConfigurationPropertiesBindException
```

Đừng sửa runner trước khi khắc phục lỗi khiến context không refresh thành công.

### 6.6. Runner khác ném exception

Nếu một runner chạy trước ném exception, quá trình startup có thể dừng và những runners sau không được gọi.

Ví dụ:

```java
@Bean
@Order(1)
CommandLineRunner firstRunner() {
    return args -> {
        throw new IllegalStateException("Initialization failed");
    };
}

@Bean
@Order(2)
CommandLineRunner secondRunner() {
    return args -> System.out.println("This may never run");
}
```

Nếu thấy runner thứ hai không xuất hiện trong log, kiểm tra runner đứng trước và startup failure. Không nên bắt mọi exception rồi bỏ qua chỉ để làm cho startup có vẻ thành công; hãy xác định tác vụ nào thực sự bắt buộc.

### 6.7. Runner đã chạy nhưng log không được nhìn thấy

Có thể:

- Logger level đang tắt.
- Output được gửi sang file/container collector khác.
- Log bị filter.
- Runner chạy ở process/replica khác.
- Bạn đang xem nhầm profile hoặc instance.
- Method chạy nhưng không có log ở đúng nhánh code.

Đặt một breakpoint hoặc log ở đầu method, dùng logger phù hợp và kiểm tra process identity. Đừng kết luận method không chạy chỉ từ việc không thấy một dòng log.

## 7. Thứ tự runner và việc một runner chạy quá sớm

Nếu có nhiều runner, Spring Boot sắp xếp chúng theo order.

Ví dụ:

```java
@Component
@Order(10)
public class DatabaseCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Database check");
    }
}
```

```java
@Component
@Order(20)
public class CacheWarmupRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Cache warmup");
    }
}
```

Order nhỏ hơn chạy trước. `ApplicationRunner` và `CommandLineRunner` cùng tham gia quá trình sắp xếp startup runners.

### 7.1. Vì sao một runner thấy dữ liệu chưa sẵn sàng?

Có thể runner đang chạy trước runner khác có trách nhiệm chuẩn bị dữ liệu.

Ví dụ:

```text
Runner A: đọc dữ liệu cấu hình từ database
Runner B: warm cache bằng dữ liệu đó
```

Nếu B chạy trước A, cache có thể rỗng hoặc thiếu dữ liệu.

Cách xử lý:

- Đặt order có chủ đích khi hai tác vụ thực sự độc lập theo lifecycle runner.
- Tốt hơn, biểu diễn quan hệ phụ thuộc bằng một service/workflow rõ ràng và gọi trực tiếp bước trước.
- Không dựa vào thứ tự tình cờ của bean discovery.

### 7.2. Tie order không phải một hợp đồng ổn định

Nếu nhiều runner có cùng order hoặc không khai báo order, không nên dựa vào thứ tự cụ thể mà framework tình cờ chọn. Hãy cấu hình order rõ nếu thứ tự là yêu cầu, hoặc gom các bước phụ thuộc vào một orchestration service.

### 7.3. Runner không phải dependency graph

`@Order` điều khiển thứ tự callback, không biểu diễn đầy đủ dependency giữa tác vụ, retry, rollback hoặc workflow phân tán.

Nếu một tác vụ cần kết quả của tác vụ khác, hãy làm dependency rõ ràng trong code thay vì dựa vào số thứ tự rải rác.

## 8. ApplicationStartedEvent và ApplicationReadyEvent

Hai event này thường bị nhầm lẫn.

### 8.1. ApplicationStartedEvent

Event này được phát sau khi ApplicationContext đã refresh thành công và trước khi startup runners được gọi.

Ví dụ:

```java
@Component
public class StartedListener {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Context refreshed; runners are next");
    }
}
```

Đây là thời điểm hữu ích để quan sát ứng dụng đã qua context refresh. Nếu bạn cần chờ runner, event này còn quá sớm.

### 8.2. ApplicationReadyEvent

Event này được phát sau khi các startup runners hoàn tất.

```java
@Component
public class ReadyListener {

    private static final Logger log =
            LoggerFactory.getLogger(ReadyListener.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("Application startup work completed");
    }
}
```

Nếu một tác vụ cần tất cả startup runners hoàn tất, đây thường là mốc phù hợp hơn.

### 8.3. Ready event không phải callback cho mỗi lần traffic

`ApplicationReadyEvent` thường được phát một lần trong mỗi SpringApplication startup tương ứng. Nó không được phát cho mỗi request hoặc mỗi lần một controller được gọi.

Nếu cần chạy định kỳ, hãy dùng scheduler; nếu cần phản ứng với event nghiệp vụ, hãy publish event nghiệp vụ riêng.

### 8.4. Vì sao không thấy ApplicationReadyEvent?

Các nguyên nhân phổ biến:

- Context refresh chưa thành công.
- Một startup runner ném exception.
- Listener bean không được đăng ký.
- Listener được đăng ký quá muộn so với event.
- Bạn đang lắng nghe event của sai context/process.
- Ứng dụng chưa tới mốc ready vì startup task bị block.
- Log listener bị filter hoặc chạy ở instance khác.

Kiểm tra runner failure và startup logs trước khi kết luận event listener hỏng.

## 9. Spring Application events và Context events

Spring có nhiều loại event. Không phải event nào cũng có cùng lifecycle hoặc được phát ở cùng thời điểm.

### 9.1. Application events của Spring Boot

Các event như:

- `ApplicationStartingEvent`.
- `ApplicationEnvironmentPreparedEvent`.
- `ApplicationContextInitializedEvent`.
- `ApplicationPreparedEvent`.
- `ApplicationStartedEvent`.
- `ApplicationReadyEvent`.
- `ApplicationFailedEvent`.

được phát bởi `SpringApplication` trong quá trình bootstrap.

### 9.2. Spring context events

Các event như:

- `ContextRefreshedEvent`.
- `ContextStartedEvent`.
- `ContextStoppedEvent`.
- `ContextClosedEvent`.

gắn với lifecycle của `ApplicationContext`.

### 9.3. Đừng dùng event chỉ vì tên nghe gần giống

Ví dụ:

- `ContextRefreshedEvent` có nghĩa một context refresh xong.
- `ApplicationStartedEvent` có nghĩa giai đoạn Spring Boot startup đã tới mốc tương ứng.
- `ApplicationReadyEvent` có nghĩa startup runners đã hoàn tất.

Nếu dùng `ContextRefreshedEvent` để thay cho “tất cả runner đã chạy xong”, bạn có thể thực hiện tác vụ quá sớm.

## 10. @EventListener không được gọi: kiểm tra những gì?

Ví dụ:

```java
@Component
public class OrderEventListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        System.out.println("Received " + event.orderId());
    }
}
```

Nếu method không chạy, kiểm tra từng điều kiện.

### 10.1. Listener có phải Spring bean không?

Class cần được component scan, import hoặc đăng ký bằng một cách phù hợp.

Sai nếu class chỉ được tạo thủ công:

```java
OrderEventListener listener = new OrderEventListener();
```

Object này không tự được đăng ký với Spring event infrastructure.

Đúng:

```java
@Component
public class OrderEventListener {
    // ...
}
```

hoặc đăng ký listener/configuration bằng cơ chế Spring tương ứng.

### 10.2. Event có thực sự được publish không?

Một listener chỉ phản ứng khi event được publish.

```java
@Component
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String orderId) {
        // Lưu đơn hàng hoặc thực hiện nghiệp vụ.
        publisher.publishEvent(
                new OrderCreatedEvent(orderId)
        );
    }
}
```

Event type:

```java
public record OrderCreatedEvent(String orderId) {
}
```

Nếu nhánh code chứa `publishEvent` không được thực thi, listener không có gì để nhận.

Đặt breakpoint ngay trước lệnh publish và ngay trong listener để xác nhận cả hai phía.

### 10.3. Listener lắng nghe sai event type

Ví dụ publisher phát:

```java
publisher.publishEvent(new OrderCreatedEvent(orderId));
```

nhưng listener lại nhận:

```java
@EventListener
public void onEvent(PaymentCompletedEvent event) {
    // ...
}
```

Hai event type khác nhau; method này không được gọi bởi `OrderCreatedEvent`.

Kiểm tra package, class, generic event type và kiểu object thực tế được publish.

### 10.4. Listener được đăng ký sau khi event đã phát

Spring event multicaster không phải một message queue lưu lịch sử và replay event cho listener mới.

Nếu event được publish trước khi listener được đăng ký, listener đăng ký sau đó không tự nhận lại event cũ.

Đây là vấn đề phổ biến với những event rất sớm trong startup. Listener bean trong ApplicationContext không thể mặc nhiên nhận mọi `SpringApplication` event phát trước khi context/listener infrastructure sẵn sàng.

### 10.5. Event được publish vào context khác

Trong ứng dụng có parent/child contexts, cần hiểu event được publish từ context nào và listener đăng ký ở đâu.

Thông thường event từ child context có thể được truyền lên parent theo cơ chế hierarchy; event từ parent không tự động được phát xuống mọi child context.

Nếu ứng dụng có management context hoặc nhiều context, hãy log identity/context source của event và kiểm tra vị trí listener.

### 10.6. @EventListener condition loại event

Ví dụ:

```java
@EventListener(condition = "#event.priority > 5")
public void onHighPriority(OrderCreatedEvent event) {
    // Chỉ xử lý khi điều kiện đúng.
}
```

Nếu điều kiện SpEL trả false, method không chạy dù event đã được publish và listener đã đăng ký.

Kiểm tra điều kiện và dữ liệu event. Khi debug, tạm thời bỏ condition hoặc log giá trị predicate ở nơi phù hợp.

### 10.7. Method signature không phù hợp

`@EventListener` thường dùng method có một event parameter hoặc annotation được cấu hình với event classes cụ thể.

Ví dụ đơn giản:

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
}
```

Nếu method dùng sai type hoặc signature không thể được event infrastructure diễn giải, quá trình đăng ký listener có thể thất bại hoặc không match event như mong đợi.

## 11. Listener cho event rất sớm phải đăng ký sớm

Một listener dạng bean:

```java
@Component
public class EarlyStartupListener {

    @EventListener
    public void onStarting(ApplicationStartingEvent event) {
        // ...
    }
}
```

không phải lựa chọn đáng tin cậy cho event phát trước khi ApplicationContext và listener bean infrastructure được tạo.

Đối với những SpringApplication events rất sớm, đăng ký listener trực tiếp với `SpringApplication` trước khi gọi `run`.

Ví dụ:

```java
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ShopConfiguration.class);

        application.addListeners(
                (ApplicationListener<ApplicationStartingEvent>) event ->
                        System.out.println("SpringApplication is starting")
        );

        application.run(args);
    }
}
```

Listener được đăng ký trước khi bootstrap bắt đầu, nên có thể nhận event sớm hơn listener chỉ tồn tại như một bean trong context.

### 11.1. Dùng ApplicationListener class rõ ràng

```java
public class StartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationStartingEvent event
    ) {
        System.out.println("Starting event received");
    }
}
```

Đăng ký:

```java
application.addListeners(new StartupListener());
```

Cách này phù hợp khi cần nhận event ở giai đoạn rất sớm.

### 11.2. Đừng đặt dependency injection vào early listener

Early listener có thể chạy trước khi ApplicationContext được tạo hoặc trước khi dependency injection sẵn sàng. Vì vậy, nó không nên giả định có thể inject service/repository bình thường.

Giữ listener sớm đơn giản, chỉ dùng dữ liệu có sẵn từ event và những thành phần thực sự sẵn sàng ở bootstrap phase đó.

## 12. @TransactionalEventListener không chạy

Đây là một nguyên nhân rất phổ biến khi event listener có vẻ hoạt động ở một môi trường nhưng im lặng ở môi trường khác.

Ví dụ:

```java
@Component
public class PurchaseListener {

    @TransactionalEventListener
    public void afterPurchaseCreated(PurchaseCreatedEvent event) {
        // ...
    }
}
```

Mặc định `@TransactionalEventListener` được liên kết với transaction phase `AFTER_COMMIT`.

Nó chỉ được kích hoạt theo transaction synchronization khi event được publish trong một transaction đang hoạt động phù hợp.

### 12.1. Publish event ngoài transaction

Ví dụ:

```java
@Service
public class PurchaseService {

    private final ApplicationEventPublisher publisher;

    public PurchaseService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void createPurchase(String id) {
        publisher.publishEvent(new PurchaseCreatedEvent(id));
    }
}
```

Nếu method này không chạy trong transaction, `@TransactionalEventListener` mặc định có thể không được gọi.

Điều này khác với `@EventListener` thông thường, vốn xử lý event khi được publish mà không cần transaction.

### 12.2. Đặt transaction boundary rõ ràng

```java
@Service
public class PurchaseService {

    private final PurchaseRepository repository;
    private final ApplicationEventPublisher publisher;

    public PurchaseService(
            PurchaseRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void createPurchase(String id) {
        repository.save(new Purchase(id));

        publisher.publishEvent(
                new PurchaseCreatedEvent(id)
        );
    }
}
```

Khi event được publish trong transaction đang hoạt động, listener `AFTER_COMMIT` có thể chạy sau khi transaction commit thành công.

### 12.3. Transaction rollback thì sao?

Nếu transaction rollback, listener phase `AFTER_COMMIT` không được gọi như khi commit thành công.

Bạn có thể chọn phase khác:

- `BEFORE_COMMIT`.
- `AFTER_COMMIT` (mặc định).
- `AFTER_ROLLBACK`.
- `AFTER_COMPLETION`.

Ví dụ:

```java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK
)
public void onPurchaseRollback(PurchaseCreatedEvent event) {
    // Xử lý khi transaction rollback.
}
```

Chọn phase theo ngữ nghĩa nghiệp vụ. Không chuyển tất cả listener sang `fallbackExecution=true` chỉ để “làm cho nó chạy”.

### 12.4. fallbackExecution

Nếu listener cần xử lý event cả khi không có transaction, có thể cấu hình:

```java
@TransactionalEventListener(fallbackExecution = true)
public void onPurchase(PurchaseCreatedEvent event) {
    // ...
}
```

Khi không có transaction, listener có thể được thực thi ngay theo fallback behavior.

Nhưng điều này làm thay đổi semantics: cùng một event có thể được xử lý trong transaction hoặc ngoài transaction. Chỉ bật khi behavior đó thực sự đúng với yêu cầu.

### 12.5. Transaction manager và proxy boundary

Nếu bạn đặt `@Transactional` nhưng method được gọi bằng self-invocation hoặc bean không đi qua transactional proxy, transaction có thể không được mở như mong đợi.

Khi đó `@TransactionalEventListener` cũng không có transaction synchronization để chờ.

Kiểm tra:

- Bean có do Spring quản lý không?
- Transaction management có được bật/cấu hình không?
- Có transaction manager phù hợp không?
- Lời gọi có đi qua proxy không?
- Có exception khiến transaction rollback không?
- Event được publish trước hay sau khi transaction thực sự bắt đầu?

## 13. @EventListener đồng bộ và bất đồng bộ

Mặc định, Spring event listener thường được gọi đồng bộ trên thread publish event, theo event multicaster hiện tại.

Ví dụ:

```java
publisher.publishEvent(new OrderCreatedEvent(orderId));

log.info("Event published");
```

Với listener đồng bộ:

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
    log.info("Listener handling orderId={}", event.orderId());
}
```

Listener thường xử lý xong trước khi lời gọi `publishEvent` trở về.

### 13.1. Vì sao log listener xuất hiện muộn?

Nếu listener dùng `@Async`:

```java
@EnableAsync
@Configuration
class AsyncConfiguration {
}
```

```java
@Component
public class AsyncOrderListener {

    @Async
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Xử lý nền.
    }
}
```

Lời gọi listener được chuyển sang executor theo async configuration. Publisher không nhất thiết chờ listener hoàn thành.

Log:

```text
Event published
Async listener started
Async listener completed
```

có thể xuất hiện theo thứ tự khác với thời gian bạn kỳ vọng, nhất là khi có nhiều tasks hoặc executor threads.

### 13.2. @Async cần được bật và đi qua proxy phù hợp

Trong cấu hình Spring thông thường, cần `@EnableAsync` hoặc một async infrastructure tương ứng.

`@Async` dựa vào proxy trong chế độ phổ biến. Tự gọi method async từ cùng object có thể bỏ qua proxy và khiến method chạy đồng bộ.

Đừng giả định chỉ thêm annotation `@Async` là mọi method trong class tự động chạy nền.

### 13.3. Exception trong async listener không trở về publisher

Với listener chạy bất đồng bộ, exception xảy ra trên worker thread thường không được ném ngược về thread đã publish event.

Bạn cần:

- Log exception ở async boundary.
- Cấu hình `AsyncUncaughtExceptionHandler` cho method void khi phù hợp.
- Dùng `Future`/`CompletableFuture` nếu caller cần quan sát kết quả.
- Có retry/dead-letter strategy nếu event quan trọng và cần độ bền.

### 13.4. Thứ tự hoàn tất không được bảo đảm bởi @Order

`@Order` có thể sắp xếp listener invocation trong một event multicaster đồng bộ. Khi listener chuyển sang executor, thứ tự **bắt đầu hoặc hoàn tất** các tasks có thể khác nhau do concurrency.

Nếu listener B phải chạy sau khi listener A hoàn tất, hãy orchestration rõ ràng bằng service/workflow hoặc chain async result, không chỉ đặt hai giá trị `@Order`.

## 14. Event được publish nhưng listener không xử lý đúng dữ liệu

Một event nên chứa dữ liệu cần thiết cho listener, hoặc một identifier đủ để listener tải lại dữ liệu hợp lệ.

Ví dụ:

```java
public record OrderCreatedEvent(
        String orderId,
        Instant occurredAt
) {
}
```

Publisher:

```java
publisher.publishEvent(
        new OrderCreatedEvent(
                orderId,
                Instant.now()
        )
);
```

Listener:

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
    log.info(
            "Order event: orderId={} occurredAt={}",
            event.orderId(),
            event.occurredAt()
    );
}
```

### 14.1. Đừng publish mutable object rồi thay đổi ngay sau đó

Nếu event mang một object mutable và publisher sửa object sau khi publish, listener bất đồng bộ có thể đọc trạng thái khác với trạng thái tại thời điểm event được phát.

Nên dùng immutable event payload như record hoặc object bất biến, hoặc chỉ truyền identifier và tải dữ liệu theo một quy tắc nhất quán.

### 14.2. Event nội bộ không phải message broker

Spring application events mặc định là cơ chế giao tiếp trong process. Chúng không tự bảo đảm:

- Persist event qua restart.
- Replay event khi listener mới xuất hiện.
- Delivery exactly-once.
- Retry bền vững.
- Giao tiếp giữa nhiều application instances.

Nếu event là business fact cần bảo đảm giao nhận giữa service/process, hãy xem message broker và transactional outbox phù hợp thay vì coi `ApplicationEventPublisher` là một message queue bền vững.

## 15. Context hierarchy và listener nhận event nhiều lần

Một số ứng dụng có parent/child ApplicationContexts, chẳng hạn web context và root context hoặc management context riêng.

Event được publish từ child context có thể được truyền lên parent; vì vậy listener đặt ở parent và child đôi khi cùng nhận một event tùy cách đăng ký.

Điều này có thể tạo cảm giác listener chạy hai lần.

### 15.1. Kiểm tra event source

```java
@EventListener
public void onContextRefresh(ContextRefreshedEvent event) {
    log.info(
            "Refreshed context id={}",
            event.getApplicationContext().getId()
    );
}
```

Ghi context ID để phân biệt context nào phát event.

### 15.2. ContextRefreshedEvent có thể xuất hiện nhiều lần

`ContextRefreshedEvent` biểu thị một context đã refresh. Một ứng dụng có thể có nhiều contexts hoặc có lifecycle refresh phức tạp.

Đừng giả định đây là “một event duy nhất trong toàn bộ JVM”.

Nếu chỉ cần startup event của một ứng dụng Boot, cân nhắc `ApplicationReadyEvent` hoặc một lifecycle hook hẹp hơn, và lọc đúng context khi cần.

### 15.3. Tránh side effect lặp lại

Nếu listener khởi tạo dữ liệu hoặc gửi thông báo, event lặp có thể tạo side effects trùng.

Hãy thiết kế idempotency hoặc kiểm tra context identity/event identity khi việc lặp không được phép. Với tác vụ startup quan trọng, cần xác định rõ phạm vi “một lần”: mỗi bean, mỗi context, mỗi process hay toàn cluster.

## 16. SmartLifecycle: quản lý start/stop theo lifecycle

`SmartLifecycle` phù hợp với component cần được container điều khiển start và stop, ví dụ consumer hoặc background component có vòng đời rõ ràng.

Ví dụ:

```java
@Component
public class MessageConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        // Khởi động consumer.
        running = true;
    }

    @Override
    public void stop() {
        // Dừng consumer.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }
}
```

Trong ứng dụng thật, start/stop cần phối hợp với consumer client, xử lý in-flight messages và timeout.

### 16.1. Phase điều khiển thứ tự

`SmartLifecycle` hỗ trợ `getPhase()`. Các lifecycle components được start/stop theo phase order của container; khi shutdown, thứ tự dừng thường ngược với thứ tự start để quản lý dependency.

Ví dụ:

```java
@Override
public int getPhase() {
    return 100;
}
```

Không nên chọn phase tùy tiện. Nếu component A cần component B đang chạy, hãy xác định phase để B khởi động trước và dừng sau theo quan hệ dependency.

### 16.2. isAutoStartup

Nếu `isAutoStartup()` trả false, container không tự động start component theo lifecycle startup mặc định. Đây là một nguyên nhân trực tiếp khiến bạn không thấy `start()` được gọi.

Kiểm tra giá trị này trước khi nghi ngờ Spring lifecycle processor.

### 16.3. Callback stop có timeout

`SmartLifecycle` hỗ trợ stop callback bất đồng bộ:

```java
@Override
public void stop(Runnable callback) {
    try {
        // Yêu cầu consumer dừng và chờ tác vụ cần thiết.
    } finally {
        running = false;
        callback.run();
    }
}
```

Phải gọi callback khi quá trình stop hoàn tất theo hợp đồng lifecycle. Nếu quên gọi, shutdown có thể chờ đến timeout.

## 17. @PreDestroy và shutdown callback không chạy

`@PreDestroy` được gọi trong quá trình Spring hủy bean, khi context đóng bình thường.

Ví dụ:

```java
@Component
public class ResourceHolder {

    @PreDestroy
    void close() {
        System.out.println("ResourceHolder is closing");
    }
}
```

### 17.1. Những trường hợp có thể không chạy

- Process bị kill cưỡng bức, ví dụ `SIGKILL`.
- JVM crash hoặc máy bị mất điện.
- Context không được đóng theo lifecycle bình thường.
- Bean chưa được tạo.
- Bean không do Spring quản lý.
- Container bị terminate trước khi shutdown phase hoàn tất.
- Callback ném exception hoặc log bị mất trong shutdown.
- Test context bị dừng theo một đường lifecycle khác với process production.

Không có callback Java nào bảo đảm chạy khi process bị dừng tức thời.

### 17.2. Shutdown hook của SpringApplication

SpringApplication thường đăng ký shutdown hook để đóng context khi JVM shutdown bình thường.

Có thể tắt bằng cấu hình tương ứng, nhưng không nên làm vậy nếu ứng dụng dựa vào Spring lifecycle để đóng resource.

Ví dụ:

```java
SpringApplication application =
        new SpringApplication(ShopApplication.class);

application.setRegisterShutdownHook(false);
```

Nếu tắt hook, ứng dụng hoặc runtime host phải chịu trách nhiệm đóng context theo cách khác.

### 17.3. Không đặt công việc không thể mất vào @PreDestroy

Nếu cần bảo đảm một business event được xử lý, đừng chỉ dựa vào `@PreDestroy` để gửi message cuối cùng. Shutdown có thể bị timeout hoặc cưỡng bức.

Hãy persist state/commands trước đó, dùng broker/outbox và thiết kế graceful shutdown để giảm rủi ro mất việc.

## 18. @Scheduled không phải startup runner

Một method:

```java
@Scheduled(fixedDelay = 5000)
public void refreshCache() {
    // ...
}
```

là scheduled task, không phải runner.

Để scheduling hoạt động, cần bật infrastructure phù hợp, thường bằng:

```java
@EnableScheduling
@Configuration
class SchedulingConfiguration {
}
```

### 18.1. Vì sao scheduled method không chạy ngay khi startup?

`fixedDelay` thường tính khoảng delay sau khi lần thực thi trước hoàn tất. Nếu bạn cần chạy một lần ngay sau startup rồi chạy định kỳ, có thể dùng `initialDelay` phù hợp hoặc gọi một service từ startup hook.

Ví dụ:

```java
@Scheduled(
        initialDelay = 0,
        fixedDelay = 5000
)
public void refreshCache() {
    // ...
}
```

Nhưng hãy xác định yêu cầu concurrency và scheduler lifecycle. Không dùng scheduled task như một cách thay thế tùy tiện cho `ApplicationRunner`.

### 18.2. Nhiều replica cùng chạy scheduled method

Nếu ứng dụng chạy nhiều replicas, mỗi process có scheduler riêng và có thể cùng chạy một job.

Nếu tác vụ cần chỉ chạy một lần toàn cluster, cần distributed coordination/lock hoặc scheduler chuyên dụng; `@Scheduled` tự nó không đảm bảo singleton across replicas.

## 19. Listener chạy trước/sau transaction như thế nào?

Chọn đúng event listener tùy thuộc việc bạn cần phản ứng trước hay sau commit.

| Cơ chế | Thời điểm |
|---|---|
| `@EventListener` | Khi event được publish, thường đồng bộ ngay theo multicaster |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước khi transaction commit |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau khi commit thành công |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau khi transaction hoàn tất dù commit hay rollback |

### 19.1. Vì sao gửi email trong @EventListener có thể sai?

Giả sử:

```java
@Transactional
public void createOrder(...) {
    repository.save(order);
    publisher.publishEvent(new OrderCreatedEvent(order.getId()));
}
```

Listener thường:

```java
@EventListener
public void sendEmail(OrderCreatedEvent event) {
    mailService.sendConfirmation(event.orderId());
}
```

Với listener đồng bộ, email có thể được gửi **trước khi transaction commit**. Nếu transaction rollback sau đó, khách hàng vẫn nhận email xác nhận đơn hàng không tồn tại.

Dùng `@TransactionalEventListener(AFTER_COMMIT)` có thể phù hợp hơn nếu yêu cầu là chỉ gửi sau khi dữ liệu commit thành công.

### 19.2. Sau commit không đồng nghĩa có delivery bền vững

Ngay cả khi listener chạy sau commit, process có thể crash giữa commit và việc gửi email. Event nội bộ không được persist tự động.

Nếu không được phép mất email/notification, hãy dùng transactional outbox hoặc một cơ chế messaging bền vững phù hợp.

### 19.3. Database operation sau commit

Sau `AFTER_COMMIT`, transaction gốc đã hoàn tất. Nếu listener cần ghi thêm dữ liệu bằng transaction mới, hãy thiết kế transaction boundary riêng (ví dụ service method có propagation phù hợp) thay vì giả định transaction ban đầu vẫn đang mở.

## 20. Event listener trả về event mới

`@EventListener` có thể trả về một object event/payload mới để Spring publish tiếp trong một số trường hợp listener đồng bộ.

Ví dụ:

```java
@EventListener
public OrderAuditEvent onOrderCreated(OrderCreatedEvent event) {
    return new OrderAuditEvent(event.orderId());
}
```

Listener khác có thể nhận `OrderAuditEvent`.

Tuy nhiên, cách này không phù hợp với listener bất đồng bộ được đánh dấu `@Async`, vì event return value không được publish theo cơ chế đồng bộ như trên. Khi cần async chain, dùng `ApplicationEventPublisher` tường minh hoặc một workflow phù hợp.

### 20.1. Tránh chuỗi event khó theo dõi

Nếu event A tạo B, B tạo C, rồi C kích hoạt side effects, hãy giữ event names, correlation ID và ownership rõ ràng. Một chuỗi event không có observability dễ khiến việc debug “listener nào chạy trước?” trở nên khó khăn.

Với workflow nghiệp vụ dài, cân nhắc orchestrator/service hoặc message broker có tracing/retry phù hợp.

## 21. Test làm callback/runner có vẻ không chạy

Một nguyên nhân rất hay gặp trong test suite là **Spring TestContext cache**.

Spring có thể tái sử dụng cùng ApplicationContext cho nhiều test classes nếu context configuration tương đương.

Ví dụ:

```java
@SpringBootTest
class FirstIntegrationTest {

    @Test
    void testOne() {
    }
}
```

```java
@SpringBootTest
class SecondIntegrationTest {

    @Test
    void testTwo() {
    }
}
```

Nếu hai test sử dụng cùng cache key, context có thể chỉ được tạo một lần và được dùng lại.

Vì runner chạy trong quá trình SpringApplication/context startup, nó không nhất thiết chạy lại cho từng test method hoặc từng test class.

### 21.1. Đừng mong runner chạy trước mỗi @Test

Runner không phải JUnit lifecycle callback.

Nếu cần setup trước mỗi test:

```java
@BeforeEach
void setUp() {
    // Chuẩn bị dữ liệu cho test này.
}
```

Nếu cần setup một lần cho class:

```java
@BeforeAll
static void beforeAll() {
    // Setup class-level.
}
```

Nếu cần một Spring bean fixture, dùng test configuration hoặc test lifecycle phù hợp. Đừng dùng `ApplicationRunner` như hook của từng test.

### 21.2. @DirtiesContext

`@DirtiesContext` yêu cầu Spring Test đánh dấu context bị thay đổi và loại khỏi cache để context mới có thể được tạo cho lần tiếp theo.

Ví dụ:

```java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ContextRecreationTest {
}
```

Khi context được tạo lại, startup lifecycle và runner có thể chạy lại.

Nhưng không nên thêm `@DirtiesContext` chỉ để ép runner xuất hiện trong log. Nó làm test suite chậm và có thể che giấu shared-state problem.

### 21.3. Test context không nhất thiết dùng SpringApplication.run như production

Spring TestContext có bootstrapper riêng để tạo context phù hợp với test. Dù nhiều lifecycle và Boot infrastructure vẫn hoạt động, không nên suy luận mọi startup event/runner sẽ được lặp lại theo từng test như khi khởi động một process mới.

Nếu cần kiểm tra event/lifecycle cụ thể, viết test có mục tiêu rõ ràng và kiểm soát context creation.

## 22. Kiểm thử runner đúng cách

Có thể test logic runner bằng cách gọi trực tiếp `run`, không cần khởi động toàn bộ ứng dụng.

Ví dụ:

```java
@Component
public class ImportRunner implements ApplicationRunner {

    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importPending();
    }
}
```

Unit test:

```java
@ExtendWith(MockitoExtension.class)
class ImportRunnerTest {

    @Mock
    ImportService importService;

    @InjectMocks
    ImportRunner runner;

    @Test
    void invokesImportService() throws Exception {
        runner.run(
                new DefaultApplicationArguments(
                        "--mode=initial"
                )
        );

        verify(importService).importPending();
    }
}
```

Test này xác nhận behavior của runner khi được gọi. Nó **không** xác nhận Spring Boot tự đăng ký hoặc tự gọi runner trong startup.

### 22.1. Integration test kiểm tra runner được đăng ký

Nếu cần kiểm tra Spring phát hiện runner bean, có thể load context với test configuration và dùng spy/recording bean phù hợp để xác nhận invocation.

Ví dụ khái niệm:

```java
@SpringBootTest
class RunnerStartupIntegrationTest {

    @MockitoSpyBean
    ImportRunner runner;

    @Test
    void runnerBeanIsCreatedAndStartupInvoked() {
        verify(runner).run(any(ApplicationArguments.class));
    }
}
```

API `@MockitoSpyBean` thuộc các phiên bản Spring Framework mới có bean override support; project cũ có thể dùng cơ chế spy/mock bean tương ứng của phiên bản Boot. Cần cẩn thận với context caching và việc runner được gọi trước khi test method bắt đầu.

### 22.2. Recording event listener

Để kiểm tra event được publish:

```java
@Component
public class RecordingOrderListener {

    private final List<OrderCreatedEvent> received =
            new CopyOnWriteArrayList<>();

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        received.add(event);
    }

    public List<OrderCreatedEvent> received() {
        return List.copyOf(received);
    }
}
```

Test có thể publish event qua `ApplicationEventPublisher` rồi assert listener nhận đúng payload.

Nếu listener async, cần đợi bằng synchronization phù hợp (Awaitility, latch hoặc future), không dùng `Thread.sleep` tùy tiện để đoán thời gian.

## 23. Test @TransactionalEventListener

Để kiểm tra listener sau commit, test cần tạo transaction thực sự và quan sát phase.

Các điều cần phân biệt:

- Test method tự được `@Transactional` bao quanh.
- Service method có transaction riêng.
- Event được publish trong transaction nào.
- Test transaction có commit hay mặc định rollback.
- Listener phase là AFTER_COMMIT hay AFTER_ROLLBACK.

Một test method có `@Transactional` mặc định rollback sau test có thể khiến `AFTER_COMMIT` listener không chạy vì không có commit thành công.

### 23.1. Vì sao test xanh nhưng listener không chạy?

Ví dụ:

```java
@SpringBootTest
@Transactional
class PurchaseEventTest {

    @Test
    void publishesPurchaseEvent() {
        purchaseService.createPurchase("P-1");
    }
}
```

Nếu transaction test vẫn rollback ở cuối method, listener `AFTER_COMMIT` có thể không được kích hoạt.

Hãy quyết định rõ test cần xác nhận commit behavior hay chỉ xác nhận publish. Với integration test, có thể chủ động commit transaction hoặc dùng transaction test utilities phù hợp, nhưng tránh làm test phụ thuộc vào trạng thái database còn sót lại.

### 23.2. Kiểm tra cả positive và negative path

- Commit thành công: listener AFTER_COMMIT được gọi.
- Rollback: listener AFTER_COMMIT không được gọi.
- Rollback: listener AFTER_ROLLBACK được gọi nếu có đăng ký.
- Publish ngoài transaction: listener transactional mặc định không chạy nếu fallback bị tắt.

Các case này giúp phát hiện việc chọn sai transaction phase.

## 24. ApplicationFailedEvent và startup exception

Nếu startup thất bại, Spring Boot có thể phát `ApplicationFailedEvent` trong quá trình xử lý failure.

Ví dụ listener đăng ký sớm:

```java
public class FailureListener
        implements ApplicationListener<ApplicationFailedEvent> {

    @Override
    public void onApplicationEvent(ApplicationFailedEvent event) {
        Throwable failure = event.getException();

        System.err.println(
                "Application startup failed: "
                        + failure.getClass().getName()
        );
    }
}
```

Đăng ký trước startup:

```java
SpringApplication application =
        new SpringApplication(ShopApplication.class);

application.addListeners(new FailureListener());

application.run(args);
```

### 24.1. Listener bean trong context có thể không tồn tại khi startup fail sớm

Nếu lỗi xảy ra trước khi ApplicationContext hoàn tất, một listener chỉ được đăng ký dưới dạng bean trong context có thể chưa sẵn sàng nhận failure event.

Nếu cần quan sát startup failure ở giai đoạn rất sớm, đăng ký listener trực tiếp với SpringApplication.

### 24.2. Không thay thế logging/exit code bằng failure listener

Failure listener hữu ích để thu thập thông tin bổ sung. Nó không nên nuốt exception hoặc khiến process trả exit code thành công khi startup đã thất bại.

Hãy giữ nguyên failure semantics để orchestrator/CI nhận ra ứng dụng không khởi động được.

## 25. ApplicationContextInitializer, BeanFactoryPostProcessor và BeanPostProcessor khác callback nào?

Các extension points này thường bị nhầm với startup runners.

### 25.1. ApplicationContextInitializer

`ApplicationContextInitializer` được gọi trong giai đoạn chuẩn bị context trước refresh.

Ví dụ:

```java
public class CustomContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context
    ) {
        // Điều chỉnh Environment hoặc context trước refresh.
    }
}
```

Dùng khi cần tùy chỉnh context trước khi bean được tạo. Nó không phải callback sau khi application ready.

### 25.2. BeanFactoryPostProcessor

`BeanFactoryPostProcessor` làm việc với bean definitions trước khi các application beans thông thường được instantiate.

Ví dụ:

```java
@Component
public class DefinitionInspector
        implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory
    ) {
        // Kiểm tra/chỉnh sửa bean definitions.
    }
}
```

Không nên lấy nó làm nơi gọi service nghiệp vụ vì phần lớn application beans chưa được tạo.

### 25.3. BeanPostProcessor

`BeanPostProcessor` can thiệp từng bean trước/sau initialization. Spring sử dụng nhiều post-processors để xử lý annotation, dependency và proxy.

Đây là hạ tầng lifecycle cấp bean, không phải một event được phát cho business workflow.

### 25.4. Chọn extension point theo thời điểm

| Nhu cầu | Extension point phù hợp |
|---|---|
| Thay đổi Environment/context trước refresh | ApplicationContextInitializer hoặc EnvironmentPostProcessor theo giai đoạn |
| Thay đổi bean definitions | BeanFactoryPostProcessor |
| Can thiệp bean trong lifecycle | BeanPostProcessor |
| Khởi tạo trạng thái của một bean | @PostConstruct/init method |
| Sau khi regular singletons được khởi tạo | SmartInitializingSingleton |
| Sau context refresh | ContextRefreshedEvent |
| Sau context refresh nhưng trước runners | ApplicationStartedEvent |
| Sau runners | ApplicationReadyEvent |
| Công việc startup với arguments | ApplicationRunner/CommandLineRunner |
| Start/stop component | SmartLifecycle |
| Định kỳ | @Scheduled |

## 26. Một ví dụ đầy đủ: startup runner và ready listener

Ví dụ dưới đây cho thấy thứ tự log mong đợi.

### 26.1. Application class

```java
@SpringBootApplication
public class LifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                LifecycleApplication.class,
                args
        );
    }
}
```

### 26.2. Bean initialization

```java
@Component
public class InitializationLogger {

    private static final Logger log =
            LoggerFactory.getLogger(InitializationLogger.class);

    @PostConstruct
    void initialize() {
        log.info("1. Bean initialization callback");
    }
}
```

### 26.3. Application started listener

```java
@Component
public class StartedEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(StartedEventLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        log.info("2. ApplicationStartedEvent");
    }
}
```

### 26.4. Startup runner

```java
@Component
public class InitialCheckRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(InitialCheckRunner.class);

    @Override
    public void run(ApplicationArguments args) {
        log.info("3. ApplicationRunner executing");
    }
}
```

### 26.5. Ready listener

```java
@Component
public class ReadyEventLogger {

    private static final Logger log =
            LoggerFactory.getLogger(ReadyEventLogger.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        log.info("4. ApplicationReadyEvent");
    }
}
```

Log minh họa:

```text
1. Bean initialization callback
2. ApplicationStartedEvent
3. ApplicationRunner executing
4. ApplicationReadyEvent
```

Thứ tự giữa nhiều bean initialization callbacks không nên được dùng làm dependency contract nếu không có ordering/lifecycle design rõ ràng. Ví dụ trên chỉ minh họa các giai đoạn chính.

### 26.6. Thêm một runner lỗi

Nếu runner ném exception:

```java
@Override
public void run(ApplicationArguments args) {
    throw new IllegalStateException("Startup validation failed");
}
```

thì `ApplicationReadyEvent` có thể không được phát vì startup chưa hoàn tất thành công.

Đây là một phép thử hữu ích để hiểu vì sao ready listener không xuất hiện dù started event đã xuất hiện.

## 27. Chẩn đoán “listener chạy hai lần”

Nếu listener xuất hiện hai lần, đừng vội thêm biến static để chặn lần thứ hai. Hãy tìm nguồn phát trùng.

Các nguyên nhân thường gặp:

1. Cùng listener bean bị đăng ký trong hai contexts.
2. Cả parent và child context cùng có listener phù hợp.
3. Publisher gọi `publishEvent` hai lần.
4. Hai component cùng phát event cho một hành động.
5. Retry logic phát event lại.
6. Consumer/message handler nhận duplicate delivery từ hệ thống bên ngoài.
7. Test context được tạo lại hoặc test chạy nhiều lần.
8. Một listener phát event mới có cùng loại và tạo chuỗi phản hồi ngoài ý muốn.

### 27.1. Log event identity và source

```java
@EventListener
public void onOrderCreated(OrderCreatedEvent event) {
    log.info(
            "Received event: orderId={} source={}",
            event.orderId(),
            event.getClass().getName()
    );
}
```

Với SpringApplication/context events, log thêm context ID hoặc source object phù hợp. Với business events, cân nhắc event ID duy nhất và correlation ID.

### 27.2. Idempotency tốt hơn static boolean

Một biến static `alreadyHandled` có thể ngăn event chạy hai lần trong một process, nhưng không xử lý được:

- Nhiều replicas.
- Process restart.
- Concurrent delivery.
- Event retry hợp lệ.
- Context recreation trong tests.

Nếu event là business operation cần xử lý đúng một lần theo nghĩa nghiệp vụ, hãy dùng idempotency key và persistence/locking phù hợp.

## 28. Chẩn đoán callback chạy quá sớm hoặc quá muộn

### 28.1. Chạy quá sớm

Triệu chứng:

- Một bean khác chưa được khởi tạo.
- Database migration chưa hoàn tất.
- Cache warmup chưa chạy.
- Runner phụ thuộc dữ liệu do runner khác tạo.
- Ready listener cần đợi runner nhưng lại đặt ở ApplicationStartedEvent.

Cách xử lý:

1. Xác định dependency nào chưa sẵn sàng.
2. Chọn lifecycle phase đúng.
3. Dùng service orchestration thay vì dựa vào thứ tự tình cờ.
4. Nếu cần sau runners, chuyển sang ApplicationReadyEvent.
5. Nếu cần sau transaction commit, dùng transactional event listener phase phù hợp.

### 28.2. Chạy quá muộn

Triệu chứng:

- Tác vụ cần hoàn tất trước khi traffic vào nhưng chỉ bắt đầu ở một scheduled task sau startup.
- Listener được đăng ký sau khi event đã publish.
- Async listener xử lý trên executor sau khi publisher đã tiếp tục.
- Task bị block bởi một tác vụ khác trong cùng executor.

Cách xử lý:

1. Xác nhận thời điểm publish và thời điểm listener đăng ký.
2. Kiểm tra listener có @Async hay multicaster executor không.
3. Kiểm tra executor queue, thread count và saturation.
4. Chọn runner hoặc lifecycle callback nếu công việc phải hoàn tất trước readiness.
5. Không dùng async nếu caller cần đợi kết quả đồng bộ.

### 28.3. Không có cam kết thời gian chỉ từ @Order

`@Order` sắp xếp một số callback/listener trong phạm vi cơ chế tương ứng. Nó không bảo đảm một listener async hoàn tất trước listener khác, không tạo dependency graph và không bảo đảm thời gian thực thi.

Nếu yêu cầu là “B chỉ chạy sau khi A hoàn tất”, hãy gọi B sau A trong cùng workflow hoặc chain kết quả rõ ràng.

## 29. Một quy trình debug có hệ thống

Khi callback, runner hoặc listener không chạy đúng kỳ vọng, làm theo trình tự:

### Bước 1 — Ghi lại mốc mong đợi

Ví dụ: “Tôi cần callback sau khi tất cả runners hoàn tất” khác với “sau khi context refresh”.

### Bước 2 — Xác định cơ chế đang dùng

`@PostConstruct`, `ApplicationRunner`, `@EventListener`, `@TransactionalEventListener`, `@Async`, `@Scheduled` hay `SmartLifecycle`?

### Bước 3 — Xác nhận bean/listener được đăng ký

Kiểm tra component scan, `@Bean`, import, profile và conditional annotations.

### Bước 4 — Xác nhận nguồn kích hoạt

Runner: SpringApplication đã tới giai đoạn call runners chưa?

Listener: publisher đã phát đúng event type chưa?

Transactional listener: có transaction active và đúng phase không?

Scheduled task: scheduling đã bật và trigger có tới chưa?

### Bước 5 — Xác nhận thứ tự lifecycle

Đối chiếu với timeline: bean init, context refresh, started, runners, ready, shutdown.

### Bước 6 — Xác nhận sync/async

Listener có chuyển sang executor? Có bị queue hoặc exception trên worker thread?

### Bước 7 — Kiểm tra context và process identity

Bạn đang nhìn đúng ApplicationContext, JVM, container, pod và replica không?

### Bước 8 — Đọc startup failure cause

Nếu ready/runner không tới, kiểm tra lỗi context refresh và runner đứng trước.

### Bước 9 — Kiểm tra test caching

Runner có thể đã chạy khi context được tạo cho test trước đó và không chạy lại do cache.

### Bước 10 — Thêm quan sát tạm thời

Dùng log ở đầu callback, breakpoint, event type, context ID, thread name và correlation ID. Gỡ log chẩn đoán quá chi tiết sau khi tìm được nguyên nhân.

## 30. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
|---|---|---|
| @PostConstruct không chạy | Bean chưa được tạo, không phải Spring bean, hoặc bean lazy | Kiểm tra bean registration và thời điểm instantiate |
| @PostConstruct chạy trước khi service khác sẵn sàng | Đang dùng bean init cho việc cần toàn context | Chuyển sang runner/ready event hoặc orchestration |
| CommandLineRunner không chạy | Bean không được đăng ký hoặc context không refresh xong | Kiểm tra scan, profile, conditions và startup exception |
| Runner thứ hai không chạy | Runner trước ném exception | Xem thứ tự và exception đầu tiên |
| ApplicationReadyEvent không xuất hiện | Runner thất bại hoặc startup chưa hoàn tất | Kiểm tra ApplicationFailedEvent và runner logs |
| ApplicationStartedEvent xuất hiện nhưng runner chưa chạy | Đây là thứ tự bình thường | Runner chạy sau started event |
| @EventListener không nhận event | Sai event type, listener chưa đăng ký, event chưa publish | Breakpoint publisher và listener |
| Listener không nhận early startup event | Bean listener được đăng ký quá muộn | Đăng ký trực tiếp với SpringApplication |
| @TransactionalEventListener không chạy | Không có transaction active hoặc transaction rollback | Kiểm tra transaction boundary/phase |
| Listener chạy ngay ngoài transaction | fallbackExecution=true | Kiểm tra semantics fallback |
| Listener chạy muộn | @Async hoặc executor queue | Kiểm tra thread/executor |
| Listener chạy hai lần | Parent/child context hoặc publish trùng | Log source/context/event ID |
| @PreDestroy không chạy | Process kill cưỡng bức hoặc context không close | Dùng graceful shutdown; không dựa vào callback khi SIGKILL |
| SmartLifecycle.start không chạy | isAutoStartup=false hoặc lifecycle chưa start | Kiểm tra lifecycle processor và phase |
| @Scheduled không chạy | Chưa bật scheduling hoặc trigger chưa tới | Kiểm tra @EnableScheduling và schedule config |
| Runner không chạy lại ở test sau | Spring TestContext cache | Hiểu context reuse; dùng test lifecycle phù hợp |
| Callback chạy trên thread khác | Async executor hoặc multicaster async | Log thread name và kiểm tra propagation |
| Event xử lý nhưng dữ liệu không như mong đợi | Mutable payload bị sửa hoặc event thiếu snapshot | Dùng immutable event payload |
| Event bị mất khi process restart | Application event không durable | Dùng broker/outbox nếu cần delivery bền vững |

## 31. Các ví dụ anti-pattern cần tránh

### 31.1. Dùng @PostConstruct để gọi một workflow phức tạp

Không nên:

```java
@PostConstruct
void initialize() {
    importAllFiles();
    callRemoteApi();
    warmEveryCache();
    sendStartupEmails();
}
```

Bean initialization nên nhanh và có phạm vi rõ. Một workflow lớn trong đó có thể làm context refresh kéo dài hoặc thất bại khó chẩn đoán.

Tốt hơn: tách startup orchestration thành một runner/service với logging, timeout, retry và readiness policy rõ ràng.

### 31.2. Nuốt exception trong runner

Không nên:

```java
@Override
public void run(String... args) {
    try {
        validateStartupData();
    } catch (Exception ignored) {
        // Startup tiếp tục dù trạng thái có thể sai.
    }
}
```

Nếu validation là bắt buộc, hãy fail startup với thông tin rõ ràng. Nếu có thể tiếp tục ở chế độ degraded, hãy thể hiện trạng thái và readiness một cách có chủ đích.

### 31.3. Dùng event nội bộ như hàng đợi bền vững

Không nên publish một application event rồi giả định event sẽ được xử lý sau khi process restart. Spring application events mặc định không persist/replay.

Dùng message broker hoặc outbox cho yêu cầu delivery bền vững.

### 31.4. Dùng Thread.sleep để đợi listener

Không nên:

```java
publisher.publishEvent(event);
Thread.sleep(2000);
assertThat(listener.completed()).isTrue();
```

Đây là test không ổn định, phụ thuộc tốc độ máy và executor.

Dùng latch, future, Awaitility hoặc synchronization có timeout rõ ràng.

### 31.5. Chạy công việc không giới hạn trong startup runner

Một runner chờ remote API vô thời hạn có thể khiến ứng dụng không bao giờ ready.

Đặt timeout, retry budget và chính sách thất bại rõ ràng. Nếu công việc không bắt buộc để nhận traffic, có thể đưa sang background workflow sau readiness.

### 31.6. Dùng static state để chống callback trùng

Static boolean có thể tồn tại qua nhiều context trong cùng JVM và làm test không độc lập. Với multi-process, nó không đồng bộ giữa replicas.

Hãy chọn idempotency ở đúng phạm vi cần bảo đảm.

## 32. Thiết kế startup task có chủ đích

Một startup task nên trả lời:

- Có bắt buộc hoàn tất trước khi nhận traffic không?
- Có thể chạy lại an toàn khi restart không?
- Có timeout không?
- Có retry không? Retry tối đa bao nhiêu lần?
- Nếu thất bại, startup fail hay app chạy degraded?
- Có thể chạy trên mọi replica hay chỉ một replica?
- Có cần lock hoặc leader election?
- Có thể quan sát tiến độ và lỗi không?
- Có cần persistence để resume không?

### 32.1. Phân loại tác vụ

| Loại tác vụ | Cách triển khai thường phù hợp |
|---|---|
| Validate cấu hình của bean | @PostConstruct hoặc validation binding |
| Kiểm tra toàn bộ context đã sẵn sàng | Context/application lifecycle event |
| Tác vụ bắt buộc sau context refresh | ApplicationRunner/CommandLineRunner |
| Tác vụ sau mọi runner | ApplicationReadyEvent |
| Khởi động/dừng consumer | SmartLifecycle hoặc integration lifecycle |
| Phản ứng với business event nội bộ | @EventListener |
| Chỉ thực hiện sau commit | @TransactionalEventListener(AFTER_COMMIT) |
| Tác vụ định kỳ | @Scheduled hoặc scheduler chuyên dụng |
| Giao việc bền vững giữa process | Message broker/outbox |
| Cleanup khi context close | @PreDestroy/DisposableBean/SmartLifecycle.stop |

### 32.2. Startup runner có nên chạy trên mọi replica?

Nếu mỗi instance cần warm cache cục bộ, mỗi replica chạy runner có thể hợp lý.

Nếu runner tạo dữ liệu dùng chung, gửi email, chạy migration hoặc thực hiện một tác vụ chỉ được chạy một lần toàn cluster, nhiều replicas cùng thực thi có thể gây duplicate side effects.

Cần phân biệt “một lần mỗi ApplicationContext” với “một lần toàn hệ thống”.

### 32.3. Database migration và startup order

Các công cụ migration như Flyway/Liquibase có lifecycle và auto-configuration riêng. Nếu runner cần schema đã được migrate, hãy dựa vào cơ chế migration startup được cấu hình đúng và kiểm thử integration; không thêm một runner tùy tiện rồi giả định nó luôn chạy sau migration chỉ dựa vào thứ tự bean.

Nếu cần ordering, hãy biểu diễn dependency phù hợp hoặc dùng service/initializer integration được hỗ trợ.

## 33. Observability cho callback và event

Khi debug lifecycle, log nên chứa thông tin giúp phân biệt process, context và thread.

Ví dụ:

```java
log.info(
        "Lifecycle callback: phase={} contextId={} thread={}",
        "application-ready",
        context.getId(),
        Thread.currentThread().getName()
);
```

Với business event:

```java
log.info(
        "Handling event: eventType={} eventId={} orderId={}",
        event.getClass().getSimpleName(),
        event.eventId(),
        event.orderId()
);
```

Những field như event ID và order ID hữu ích trong logs. Không nên dùng UUID/order ID làm metric tags nếu chúng tạo cardinality cao.

### 33.1. Đo duration của startup task

Một runner có thể đo thời gian:

```java
long started = System.nanoTime();

try {
    warmupService.execute();
} finally {
    long elapsed = System.nanoTime() - started;
    log.info("Warmup completed in {} ms", elapsed / 1_000_000);
}
```

Trong ứng dụng có Micrometer, bạn cũng có thể dùng Timer với tag có cardinality thấp như `task=cache-warmup`.

### 33.2. Đừng log chỉ “listener called”

Một log:

```text
Listener called
```

không giúp xác định listener nào, event nào hoặc context nào.

Tốt hơn:

```java
log.info(
        "Received OrderCreatedEvent: orderId={} eventId={}",
        event.orderId(),
        event.eventId()
);
```

Đối với startup callback, ghi tên phase và thời gian bắt đầu/kết thúc nếu tác vụ có thể kéo dài.

## 34. Ví dụ: event listener không chạy vì thiếu transaction

### 34.1. Event type

```java
public record InvoiceCreatedEvent(String invoiceId) {
}
```

### 34.2. Publisher không có transaction

```java
@Service
public class InvoiceService {

    private final ApplicationEventPublisher publisher;

    public InvoiceService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void create(String invoiceId) {
        publisher.publishEvent(
                new InvoiceCreatedEvent(invoiceId)
        );
    }
}
```

### 34.3. Listener mặc định chờ commit

```java
@Component
public class InvoiceListener {

    private static final Logger log =
            LoggerFactory.getLogger(InvoiceListener.class);

    @TransactionalEventListener
    public void afterCommit(InvoiceCreatedEvent event) {
        log.info(
                "Invoice committed: invoiceId={}",
                event.invoiceId()
        );
    }
}
```

Nếu `create` không nằm trong transaction, listener mặc định không chạy.

### 34.4. Sửa bằng transaction boundary

```java
@Transactional
public void create(String invoiceId) {
    repository.save(new Invoice(invoiceId));

    publisher.publishEvent(
            new InvoiceCreatedEvent(invoiceId)
    );
}
```

Sau commit thành công, listener mới xử lý.

### 34.5. Kiểm tra bằng integration test

Test cần xác nhận:

- Invoice được lưu.
- Event được publish trong transaction.
- Listener chỉ chạy sau commit.
- Khi rollback, after-commit listener không chạy.

Đừng chỉ dùng Mockito verify `publishEvent` rồi kết luận transaction listener đã hoạt động. Mockito chỉ chứng minh publisher method được gọi, không chứng minh transaction synchronization thực thi đúng.

## 35. Ví dụ: listener sớm và listener trong ApplicationContext

Giả sử muốn ghi nhận hai mốc:

- `ApplicationStartingEvent`: rất sớm.
- `ApplicationReadyEvent`: sau startup runners.

### 35.1. Early listener

```java
public class EarlyListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(
            ApplicationStartingEvent event
    ) {
        System.out.println("EARLY: application starting");
    }
}
```

Đăng ký:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(ShopApplication.class);

    application.addListeners(new EarlyListener());

    application.run(args);
}
```

### 35.2. Ready listener trong context

```java
@Component
public class ReadyListener {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("READY: all runners completed");
    }
}
```

Hai listener có cách đăng ký và lifecycle khác nhau. Không thể dùng một `@EventListener` bean bình thường rồi kỳ vọng nó luôn nhận được những event phát trước khi context listener infrastructure được tạo.

## 36. Phân biệt “callback không chạy” với “callback chạy nhưng chưa hoàn tất”

Đặc biệt với async:

```java
@Async
@EventListener
public void onEvent(MyEvent event) {
    longRunningOperation();
}
```

Publisher có thể trở về trước khi `longRunningOperation` hoàn tất.

Có ba mốc riêng:

1. Event được publish.
2. Listener invocation được dispatch/submit.
3. Listener xử lý xong.

Một log ở publisher chỉ xác nhận mốc 1. Một metric executor queue hoặc log đầu method giúp xác nhận mốc 2. Log cuối method/future/latch giúp xác nhận mốc 3.

Khi điều tra, hãy nói rõ bạn đang chờ mốc nào.

## 37. Thực hành: chọn đúng lifecycle hook

Một số yêu cầu mẫu:

| Yêu cầu | Lựa chọn phù hợp | Vì sao |
|---|---|---|
| Validate giá trị field sau injection | @PostConstruct hoặc configuration validation | Thuộc initialization của bean |
| Đọc toàn bộ command-line options và chạy import | ApplicationRunner | Có ApplicationArguments |
| Chạy tác vụ sau tất cả startup runners | ApplicationReadyEvent | Được phát sau runner phase |
| Khởi tạo consumer và dừng nó cùng context | SmartLifecycle | Có start/stop lifecycle |
| Gửi email chỉ sau transaction commit | @TransactionalEventListener(AFTER_COMMIT) | Tránh gửi trước khi dữ liệu commit |
| Cập nhật metrics/log khi order được tạo | @EventListener hoặc trực tiếp service | Phản ứng với business event |
| Chạy báo cáo mỗi ngày | @Scheduled hoặc scheduler | Công việc theo lịch |
| Đóng resource khi context dừng bình thường | @PreDestroy/SmartLifecycle.stop | Cleanup theo lifecycle |
| Nhận ApplicationStartingEvent | SpringApplication.addListeners | Listener phải đăng ký trước context |
| Setup trước mỗi JUnit test | @BeforeEach | JUnit lifecycle, không phải Boot runner |

## 38. Bài thực hành

### Bài 1 — Quan sát @PostConstruct

Tạo một bean có constructor, injection dependency và `@PostConstruct`. Ghi log ở từng bước, sau đó thêm một bean khác để quan sát vì sao không nên giả định tất cả beans đã sẵn sàng trong callback của một bean.

### Bài 2 — So sánh InitializingBean và custom init method

Tạo bean dùng `InitializingBean.afterPropertiesSet()` và bean dùng `@Bean(initMethod=...)`. Quan sát thứ tự với `@PostConstruct` và ghi rõ các callback thuộc lifecycle của bean.

### Bài 3 — Quan sát SmartInitializingSingleton

Tạo hai singleton beans và một `SmartInitializingSingleton`. Ghi log khi từng bean được khởi tạo và khi callback chạy. So sánh với `ContextRefreshedEvent`.

### Bài 4 — Tạo CommandLineRunner

Tạo `CommandLineRunner` component, truyền vài command-line arguments và in chúng. Xác nhận runner chạy một lần trong mỗi application startup.

### Bài 5 — Tạo ApplicationRunner

Dùng `ApplicationArguments` để đọc option `--mode=initial` và non-option arguments. So sánh với `CommandLineRunner`.

### Bài 6 — Tái hiện runner không được scan

Đặt runner ở package ngoài component scan. Xác nhận nó không được đăng ký, sau đó sửa package hoặc component scan và quan sát runner chạy.

### Bài 7 — Tái hiện runner bị condition loại

Gắn `@Profile` hoặc `@ConditionalOnProperty`. Chạy với giá trị/profile khác nhau và xác định lý do runner xuất hiện hoặc biến mất.

### Bài 8 — Tái hiện runner trước làm startup thất bại

Tạo hai runners có order khác nhau; runner đầu ném exception. Quan sát runner sau và `ApplicationReadyEvent`. Đọc cause chain của startup failure.

### Bài 9 — So sánh ApplicationStartedEvent và ApplicationReadyEvent

Đăng ký hai listener và một runner. Ghi timestamp để thấy started event xảy ra trước runners, còn ready event xảy ra sau runners.

### Bài 10 — Early event listener

Đăng ký `ApplicationStartingEvent` listener bằng `SpringApplication.addListeners`. So sánh với một `@EventListener` bean trong ApplicationContext và giải thích khác biệt thời điểm đăng ký.

### Bài 11 — Publish business event

Tạo `OrderCreatedEvent` và publish qua `ApplicationEventPublisher`. Đăng ký `@EventListener`, kiểm tra đúng event type và payload.

### Bài 12 — Điều kiện @EventListener

Thêm SpEL condition dựa trên priority. Publish event có priority thấp/cao và quan sát listener chỉ xử lý event thỏa điều kiện.

### Bài 13 — Transactional event

Tạo `@TransactionalEventListener(AFTER_COMMIT)`. Publish event trong và ngoài transaction. Kiểm tra behavior mặc định và thử `fallbackExecution=true` trong một test riêng.

### Bài 14 — Transaction rollback

Tạo transaction lưu dữ liệu rồi ném exception. Đăng ký AFTER_COMMIT và AFTER_ROLLBACK listeners, xác nhận listener tương ứng với kết quả transaction.

### Bài 15 — Async event listener

Bật `@EnableAsync`, đánh dấu listener `@Async`. Ghi thread names và thời điểm publish/complete. Dùng CountDownLatch hoặc Awaitility trong test thay vì `Thread.sleep`.

### Bài 16 — Context hierarchy

Tạo parent/child contexts hoặc cấu hình nhiều contexts trong một test. Ghi context ID khi nhận `ContextRefreshedEvent` và tìm lý do listener có thể nhận event nhiều lần.

### Bài 17 — SmartLifecycle

Tạo component implement `SmartLifecycle`, ghi log start/stop và phase. Thử `isAutoStartup=false` rồi bật lại để quan sát sự khác nhau.

### Bài 18 — Shutdown callback

Tạo bean có `@PreDestroy`. Đóng context bình thường và quan sát callback. So sánh về mặt lý thuyết với process bị kill cưỡng bức và giải thích vì sao cleanup không được bảo đảm trong trường hợp đó.

### Bài 19 — Runner và Spring TestContext cache

Tạo hai `@SpringBootTest` dùng cùng cấu hình. Ghi log runner và quan sát việc context được tái sử dụng. Thử `@DirtiesContext` để xem context được tạo lại, rồi đánh giá chi phí.

### Bài 20 — Kiểm thử runner độc lập

Dùng Mockito để unit test `ApplicationRunner.run`. Assert service dependency được gọi. Sau đó giải thích test này không chứng minh component scan hoặc Boot startup tự gọi runner.

### Bài 21 — Scheduled task

Bật `@EnableScheduling`, tạo `@Scheduled` method với initial delay. Quan sát nó khác runner như thế nào. Chạy hai application instances và phân tích nguy cơ job được thực thi hai lần.

### Bài 22 — Debug callback sai thời điểm

Tạo một workflow có dependency giữa cache warmup và dữ liệu khởi tạo. Ban đầu dùng hai runner không có order, sau đó sửa thành orchestration rõ ràng. Giải thích vì sao dependency graph tốt hơn dựa vào thứ tự tình cờ.

### Bài 23 — Đo thời gian startup task

Dùng `System.nanoTime` hoặc Micrometer Timer để đo warmup duration. Thêm log phase, context ID và thread name để hỗ trợ vận hành.

### Bài 24 — Thiết kế event bền vững

Tạo một event nghiệp vụ cần bảo đảm không mất sau restart. So sánh Spring application event với message broker/transactional outbox và đề xuất kiến trúc phù hợp.

## 39. Tài liệu tham khảo chính thức

- [Spring Boot Reference — SpringApplication Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): lifecycle events, runners và application availability.
- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-events-and-listeners): các event trong quá trình SpringApplication bootstrap.
- [Spring Boot Reference — Application Runners](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.command-line-runner): `ApplicationRunner` và `CommandLineRunner`.
- [Spring Framework Reference — Bean Lifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization, destruction callbacks và lifecycle.
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events): publish/subscribe application events.
- [Spring Framework Reference — Annotation-based Event Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-annotation): `@EventListener` và listener method.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và transaction phases.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor và `@Scheduled`.
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle): `SmartLifecycle` và callback lifecycle.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): test context, startup behavior và Spring Boot testing.

**Điều quan trọng nhất khi chẩn đoán callback, runner hoặc listener:** xác định đúng lifecycle phase trước khi kiểm tra code. `@PostConstruct` thuộc initialization của một bean; runners chạy sau khi context refresh; `ApplicationReadyEvent` xuất hiện sau startup runners; `@EventListener` cần listener được đăng ký trước khi event được publish; `@TransactionalEventListener` còn phụ thuộc transaction phase; async listener có thời điểm hoàn tất riêng. Khi hiểu đúng các ranh giới này, bạn có thể tìm nguyên nhân từ bean registration, component scan, profile/condition, startup exception, event type, transaction, executor hoặc context caching thay vì thêm delay hay gọi callback thủ công một cách ngẫu nhiên.
