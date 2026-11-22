# `@Order` không thay thế quan hệ phụ thuộc khi tạo bean

Trong Spring Boot, bạn có thể gắn `@Order(1)` lên một bean và `@Order(2)` lên bean khác. Điều đó giúp Spring sắp xếp chúng tại những nơi có sử dụng cơ chế order, chẳng hạn khi inject nhiều bean vào một `List` hoặc khi gọi các `CommandLineRunner`. Tuy nhiên, **`@Order` không phải công cụ điều khiển thứ tự khởi tạo mọi bean trong IoC container**.

Nếu bean B thực sự cần bean A được tạo và khởi tạo trước, ứng dụng phải biểu đạt quan hệ đó bằng dependency injection hoặc `@DependsOn` khi chỉ cần thứ tự khởi tạo vì một side effect. Gắn `@Order` lên A và B không tạo ra dependency giữa chúng.

Đây là khác biệt quan trọng khi thiết kế vòng đời bean:

- `@Order` trả lời: *Khi một cơ chế cần sắp xếp nhiều phần tử, phần tử này đứng ở vị trí nào?*
- Dependency injection trả lời: *Bean này cần bean nào để hoạt động?*
- `@DependsOn` trả lời: *Bean nào phải được khởi tạo trước bean này dù không cần inject trực tiếp nó?*

## 1. Spring tạo bean theo quan hệ phụ thuộc

Spring IoC container quản lý việc đăng ký bean definition, tạo instance, cấp dependency, gọi callback khởi tạo và hủy bean khi context đóng. Một bean có thể được tạo sớm hay muộn tùy scope, lazy initialization và những bean khác cần nó.

Ví dụ:

```java
@Component
public class DataSourceProvider {
    public DataSourceProvider() {
        System.out.println("Create DataSourceProvider");
    }
}

@Service
public class ReportService {
    private final DataSourceProvider dataSourceProvider;

    public ReportService(DataSourceProvider dataSourceProvider) {
        System.out.println("Create ReportService");
        this.dataSourceProvider = dataSourceProvider;
    }
}
```

`ReportService` cần `DataSourceProvider` để được tạo. Khi Spring tạo `ReportService`, container phải resolve tham số constructor trước. Vì vậy `DataSourceProvider` được tạo và khởi tạo trước khi Spring gọi constructor của `ReportService`.

Quan hệ này hình thành từ dependency thật trong constructor:

```text
DataSourceProvider
        |
        | cần có trước
        v
ReportService
```

Đây là một cạnh trong **dependency graph** của container. Spring có thông tin để biết bean nào cần bean nào, từ đó xác định thứ tự tạo phù hợp.

### 1.1. Constructor injection thể hiện dependency rõ ràng

```java
@Service
public class OrderService {
    private final PaymentGateway paymentGateway;
    private final InventoryService inventoryService;

    public OrderService(
            PaymentGateway paymentGateway,
            InventoryService inventoryService) {
        this.paymentGateway = paymentGateway;
        this.inventoryService = inventoryService;
    }
}
```

`OrderService` chỉ có thể được tạo sau khi Spring resolve được `PaymentGateway` và `InventoryService`. Nếu một dependency không có bean phù hợp, container báo lỗi tạo bean thay vì âm thầm khởi tạo `OrderService` với dependency thiếu.

Constructor injection có một số lợi ích:

- Thể hiện dependency bắt buộc ngay tại chữ ký constructor.
- Giúp đối tượng không được tạo trong trạng thái thiếu dependency.
- Dễ viết unit test bằng cách truyền fake hoặc mock.
- Cho Spring biết quan hệ giữa các bean để quản lý quá trình tạo.

### 1.2. Setter và field injection cũng tạo dependency

Spring còn hỗ trợ setter injection:

```java
@Service
public class ReportService {
    private DataSourceProvider dataSourceProvider;

    @Autowired
    public void setDataSourceProvider(
            DataSourceProvider dataSourceProvider) {
        this.dataSourceProvider = dataSourceProvider;
    }
}
```

Và field injection:

```java
@Service
public class ReportService {
    @Autowired
    private DataSourceProvider dataSourceProvider;
}
```

Trong cả hai trường hợp, Spring vẫn phải resolve bean phụ thuộc khi populate property. Dependency vẫn được container biết đến. Tuy nhiên, constructor injection thường dễ đọc và dễ kiểm soát hơn, nhất là với dependency bắt buộc.

**Lưu ý về thời điểm:** với constructor injection, dependency phải được resolve trước khi constructor của bean đang tạo được gọi. Với setter/field injection, object phụ thuộc có thể được tạo sau khi instance của bean chính đã được khởi tạo nhưng trước khi quá trình khởi tạo bean chính hoàn tất. Không nên diễn giải rằng mọi loại injection đều có cùng thứ tự ở mức constructor.

## 2. `@Order` thực sự làm gì?

`@Order` thuộc package `org.springframework.core.annotation`. Annotation khai báo mức ưu tiên để những cơ chế có hỗ trợ order comparator có thể sắp xếp các đối tượng.

Ví dụ:

```java
@Component
@Order(1)
public class FirstHandler implements TaskHandler {
}

@Component
@Order(2)
public class SecondHandler implements TaskHandler {
}
```

Giá trị nhỏ hơn có mức ưu tiên cao hơn, vì vậy `FirstHandler` đứng trước `SecondHandler` khi chúng được thu thập và sắp xếp theo order.

`Ordered` interface cũng cung cấp cách khai báo order bằng code:

```java
@Component
public class UrgentHandler implements TaskHandler, Ordered {
    @Override
    public int getOrder() {
        return 1;
    }
}
```

### 2.1. Những nơi thường sử dụng order

| Nơi sử dụng | Vai trò của `@Order` / `Ordered` |
| --- | --- |
| Inject `List<T>` có nhiều bean phù hợp | Sắp xếp phần tử trong list |
| Inject array `T[]` | Sắp xếp các phần tử của mảng theo cơ chế autowiring |
| `ObjectProvider<T>.orderedStream()` | Cung cấp stream theo order |
| `CommandLineRunner` / `ApplicationRunner` | Sắp xếp thứ tự gọi runner sau khi context khởi động |
| Spring AOP aspects | Xác định precedence giữa các aspect khi cùng áp dụng |
| Một số extension point của Spring | Sắp xếp processor hoặc strategy nếu hợp đồng extension point sử dụng order |

`@Order` không có nghĩa mọi danh sách, mọi bean hay mọi giai đoạn trong Spring đều tự động được sắp xếp. Tác dụng của nó phụ thuộc cơ chế đang đọc metadata order.

### 2.2. `@Order` không quyết định thứ tự tạo singleton

Đây là quy tắc quan trọng cần nhớ:

> `@Order` không điều khiển thứ tự khởi tạo singleton bean trong application context.

Ví dụ:

```java
@Component
@Order(1)
public class CacheInitializer {
    public CacheInitializer() {
        System.out.println("CacheInitializer constructor");
    }
}

@Component
@Order(2)
public class SearchInitializer {
    public SearchInitializer() {
        System.out.println("SearchInitializer constructor");
    }
}
```

Không nên coi `@Order(1)` là cam kết constructor của `CacheInitializer` luôn chạy trước constructor của `SearchInitializer`. Thứ tự khởi tạo singleton còn phụ thuộc cách bean được yêu cầu, quan hệ dependency, lazy initialization và quy trình của container.

Nếu `SearchInitializer` thực sự cần cache đã sẵn sàng, hãy biểu đạt dependency hoặc quan hệ khởi tạo phù hợp. Chỉ gắn `@Order` không làm Spring biết `SearchInitializer` phụ thuộc vào `CacheInitializer`.

## 3. `@Order` trong collection injection: thứ tự phần tử, không phải thứ tự tạo bean

Một nơi rất phù hợp để dùng `@Order` là khi một service cần tất cả implementation của cùng interface và muốn duyệt chúng theo trình tự.

Khai báo interface:

```java
public interface StartupTask {
    void execute();
}
```

Hai implementation:

```java
@Component
@Order(10)
public class LoadConfigurationTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Load configuration");
    }
}
```

```java
@Component
@Order(20)
public class PrintBannerTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Print banner");
    }
}
```

Service nhận danh sách:

```java
@Service
public class StartupCoordinator {
    private final List<StartupTask> tasks;

    public StartupCoordinator(List<StartupTask> tasks) {
        this.tasks = tasks;
    }

    public void runAll() {
        tasks.forEach(StartupTask::execute);
    }
}
```

Với cơ chế autowiring collection tiêu chuẩn, Spring sắp xếp các phần tử trong `tasks` theo order:

```text
tasks
  1. LoadConfigurationTask  (@Order(10))
  2. PrintBannerTask        (@Order(20))
```

Khi gọi `runAll()`, các phương thức `execute()` chạy theo thứ tự phần tử trong list. Đây là **thứ tự thực thi do service duyệt collection**, không phải cam kết rằng constructor của `LoadConfigurationTask` đã chạy trước constructor của `PrintBannerTask`.

Spring cần tạo các bean để cung cấp chúng cho constructor của `StartupCoordinator`. Thứ tự tạo các instance có thể khác với thứ tự các phần tử được sắp xếp trong list.

### 3.1. Minh họa hai loại thứ tự

```text
Thời điểm tạo bean:

Container cần các bean StartupTask
       |
       +--> Tạo các instance (thứ tự không do @Order quy định)
       |
       v
Tập hợp các bean phù hợp
       |
       v
Sắp xếp collection theo @Order
       |
       v
Inject List<StartupTask> vào StartupCoordinator
       |
       v
StartupCoordinator.runAll()
       |
       +--> LoadConfigurationTask.execute()
       |
       +--> PrintBannerTask.execute()
```

Nếu mục tiêu chỉ là chạy các handler theo thứ tự, `@Order` và collection injection là phù hợp. Nếu mục tiêu là bảo đảm một bean được khởi tạo hoàn chỉnh trước bean khác, cần quan hệ dependency riêng.

### 3.2. Giá trị order nhỏ hơn đứng trước

| Bean | Order | Vị trí trong list |
| --- | ---: | ---: |
| `LoadConfigurationTask` | 10 | 1 |
| `PrintBannerTask` | 20 | 2 |
| `CleanupTask` | 30 | 3 |

Nếu không khai báo order, giá trị mặc định thường tương đương `Ordered.LOWEST_PRECEDENCE`. Khi hai bean có cùng order, không nên dựa vào thứ tự đầu vào không được bảo đảm để làm quy tắc nghiệp vụ.

### 3.3. `List`, array, `Set` và `Map`

| Kiểu nhận dependency | Cách hiểu |
| --- | --- |
| `List<T>` | Phù hợp khi cần nhiều bean theo thứ tự; autowiring list được sắp xếp theo order |
| `T[]` | Có thể nhận nhiều bean và được sắp xếp theo cơ chế autowiring array |
| `Set<T>` | Biểu diễn tập phần tử; không nên dựa vào thứ tự iteration |
| `Map<String, T>` | Hữu ích để tra cứu bean theo tên; không nên coi thứ tự iteration là hợp đồng `@Order` |

Nếu cần lấy bean theo thứ tự một cách trì hoãn:

```java
@Service
public class TaskRunner {
    private final ObjectProvider<StartupTask> tasks;

    public TaskRunner(ObjectProvider<StartupTask> tasks) {
        this.tasks = tasks;
    }

    public void runAll() {
        tasks.orderedStream().forEach(StartupTask::execute);
    }
}
```

`orderedStream()` yêu cầu sắp xếp các bean theo order comparator. `stream()` thông thường không nên được coi là đã sắp xếp theo `@Order`.

## 4. Biểu đạt dependency bằng constructor injection

Nếu bean B thực sự cần bean A để hoạt động, hãy inject A vào B:

```java
@Component
public class DatabaseInitializer {

    public DatabaseInitializer() {
        System.out.println("Create DatabaseInitializer");
    }

    public void initialize() {
        System.out.println("Initialize database metadata");
    }
}
```

```java
@Service
public class CustomerRepository {
    private final DatabaseInitializer initializer;

    public CustomerRepository(DatabaseInitializer initializer) {
        this.initializer = initializer;
        System.out.println("Create CustomerRepository");
    }
}
```

Trong ví dụ minh họa, `CustomerRepository` có dependency trực tiếp vào `DatabaseInitializer`. Container phải resolve dependency trước khi hoàn tất việc tạo `CustomerRepository`.

Tuy nhiên, nếu `CustomerRepository` không cần gọi phương thức của `DatabaseInitializer`, việc inject chỉ để tạo thứ tự có thể biểu đạt sai ý nghĩa thiết kế. Trong tình huống chỉ cần một side effect hoàn thành trước, `@DependsOn` có thể phù hợp hơn.

### 4.1. Dependency được dùng trong nghiệp vụ

Đây là trường hợp nên dùng constructor injection:

```java
@Service
public class InvoiceService {
    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }

    public BigDecimal calculateTotal(BigDecimal amount) {
        return taxCalculator.calculate(amount);
    }
}
```

`InvoiceService` cần `TaxCalculator` để tính toán. Quan hệ được thể hiện trực tiếp trong API của class và Spring tự bảo đảm dependency phù hợp được resolve trước khi bean chính sẵn sàng.

Không cần thêm `@Order` hoặc `@DependsOn` để lặp lại quan hệ đã được constructor injection thể hiện.

## 5. `@DependsOn`: khi cần thứ tự khởi tạo nhưng không inject trực tiếp

Có trường hợp bean B không cần giữ tham chiếu tới bean A, nhưng quá trình khởi tạo B cần một **side effect** do A thực hiện trước đó. Ví dụ A đăng ký plugin vào registry chung, còn B đọc registry trong initialization callback.

`@DependsOn` thuộc `org.springframework.context.annotation.DependsOn`. Annotation cho Spring biết những bean nào phải được khởi tạo trước bean mang annotation.

Ví dụ:

```java
@Component("pluginCatalogInitializer")
public class PluginCatalogInitializer {

    @PostConstruct
    public void registerPlugins() {
        System.out.println("Register plugins in shared catalog");
    }
}
```

Bean sử dụng registry sau khi catalog đã được chuẩn bị:

```java
@Component
@DependsOn("pluginCatalogInitializer")
public class PluginConsumer {

    @PostConstruct
    public void loadPlugins() {
        System.out.println("Read registered plugins");
    }
}
```

`PluginConsumer` không cần inject `PluginCatalogInitializer`. Nhưng Spring vẫn phải khởi tạo bean `pluginCatalogInitializer` trước khi khởi tạo `PluginConsumer`.

Kết quả mong đợi về thứ tự initialization:

```text
Register plugins in shared catalog
Read registered plugins
```

Tên bean trong `@DependsOn` phải khớp với bean name thực tế. Nếu không khai báo tên riêng cho component `PluginCatalogInitializer`, tên mặc định thường là `pluginCatalogInitializer`.

### 5.1. Dùng `@DependsOn` trên class

```java
@Component
@DependsOn({"configurationLoader", "pluginCatalogInitializer"})
public class PluginConsumer {
}
```

Các bean được liệt kê phải được khởi tạo trước `PluginConsumer`. Có thể khai báo nhiều bean name trong mảng.

### 5.2. Dùng `@DependsOn` trên phương thức `@Bean`

```java
@Configuration(proxyBeanMethods = false)
public class PluginConfiguration {

    @Bean
    public PluginCatalogInitializer pluginCatalogInitializer() {
        return new PluginCatalogInitializer();
    }

    @Bean
    @DependsOn("pluginCatalogInitializer")
    public PluginConsumer pluginConsumer() {
        return new PluginConsumer();
    }
}
```

Ở đây bean được tạo qua factory method. `@DependsOn` trên phương thức `@Bean` áp dụng quan hệ khởi tạo cho bean được đăng ký từ phương thức đó.

### 5.3. `@DependsOn` và thứ tự hủy singleton

Với singleton bean, quan hệ `@DependsOn` cũng ảnh hưởng thứ tự hủy: bean phụ thuộc được hủy trước bean mà nó phụ thuộc vào.

Nếu `pluginConsumer` phụ thuộc vào side effect của `pluginCatalogInitializer`, khi application context đóng, Spring có thể hủy consumer trước rồi mới hủy initializer, theo quan hệ phụ thuộc đã khai báo.

Điều này hữu ích khi bean cần tài nguyên hoặc registry vẫn còn tồn tại trong quá trình cleanup. Hành vi hủy cụ thể vẫn phụ thuộc scope và lifecycle callback của bean.

## 6. Constructor injection hay `@DependsOn`: chọn đúng theo bản chất

Hai cơ chế đều giúp Spring tạo bean theo quan hệ cần thiết, nhưng biểu đạt ý nghĩa khác nhau.

| Tình huống | Cách nên dùng | Lý do |
| --- | --- | --- |
| `OrderService` cần `PaymentGateway` để xử lý đơn | Constructor injection | Đây là dependency thực sự được sử dụng |
| `ReportService` cần `DataSource` để truy vấn | Constructor injection | Bean phải có dependency trước khi hoạt động |
| `PluginConsumer` cần plugin được đăng ký trong registry trước khi đọc | `@DependsOn` nếu không cần tham chiếu initializer | Quan hệ chủ yếu là thứ tự side effect khởi tạo |
| `CacheWarmupTask` và `BannerTask` chỉ cần được duyệt theo trình tự trong pipeline | `@Order` trên collection | Đây là thứ tự xử lý các phần tử |
| Nhiều `CommandLineRunner` cần chạy theo trình tự sau startup | `@Order` / `Ordered` | Spring Boot sắp xếp thứ tự gọi runner |
| Một bean cần một implementation mặc định trong nhiều ứng viên | `@Primary` hoặc `@Qualifier` | Đây là lựa chọn bean, không phải dependency order |

Không nên inject một bean chỉ để “ép thứ tự” nếu bean đó không phải dependency thật. Ngược lại, cũng không nên dùng `@DependsOn` khi constructor có thể diễn đạt rõ đối tượng cần sử dụng.

## 7. `@Order` và `@DependsOn` có thể cùng xuất hiện nhưng không thay thế nhau

Một bean có thể cần tham gia pipeline có thứ tự và đồng thời cần một bean khác được khởi tạo trước do side effect. Hai yêu cầu này độc lập.

Ví dụ:

```java
@Component("schemaInitializer")
public class SchemaInitializer {
    @PostConstruct
    public void initialize() {
        System.out.println("Prepare schema");
    }
}
```

```java
@Component
@DependsOn("schemaInitializer")
@Order(10)
public class ImportTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Import data");
    }
}
```

```java
@Component
@Order(20)
public class ReportTask implements StartupTask {
    @Override
    public void execute() {
        System.out.println("Generate report");
    }
}
```

Trong ví dụ:

- `@DependsOn("schemaInitializer")` bảo đảm initializer được khởi tạo trước `ImportTask`.
- `@Order(10)` và `@Order(20)` sắp xếp `ImportTask` và `ReportTask` khi chúng được đưa vào collection có hỗ trợ order.
- `@Order` trên `ImportTask` không làm `schemaInitializer` tự động khởi tạo trước.
- `@DependsOn` trên `ImportTask` không quyết định `ImportTask` đứng trước hay sau `ReportTask` trong collection.

Nếu `ReportTask` cũng cần schema đã sẵn sàng, nó cần quan hệ dependency riêng hoặc cả hai task phải phụ thuộc vào một service/initializer chung. Không nên giả định vì `ImportTask` có `@DependsOn` nên `ReportTask` cũng được bảo đảm.

## 8. `@Order` trong `CommandLineRunner` khác thứ tự tạo bean

Spring Boot gọi `CommandLineRunner` và `ApplicationRunner` sau khi application context đã được khởi động. Các runner có thể được sắp xếp bằng `Ordered` hoặc `@Order`.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class StartupConfiguration {

    @Bean
    @Order(10)
    CommandLineRunner loadData() {
        return args -> System.out.println("Load data");
    }

    @Bean
    @Order(20)
    CommandLineRunner printStatus() {
        return args -> System.out.println("Print status");
    }
}
```

Spring Boot gọi `loadData` runner trước `printStatus` runner theo order. Nhưng không nên diễn giải điều này thành cam kết rằng object đại diện cho runner đầu tiên luôn được **khởi tạo trước** object runner thứ hai.

### 8.1. Khi runner thứ hai cần kết quả từ runner thứ nhất

Nếu `printStatus` cần dữ liệu do `loadData` tạo, có thể dùng order để xác định thứ tự gọi runner trong cùng cơ chế Spring Boot:

```text
Context đã refresh
       |
       v
loadData.run()       @Order(10)
       |
       v
printStatus.run()    @Order(20)
```

Tuy nhiên, nếu dữ liệu đó là dependency thiết yếu của một bean trong lúc tạo bean, `@Order` trên runner không giúp bean đó được tạo sau runner. Runner chạy sau giai đoạn context refresh; các singleton eager thông thường đã được khởi tạo trước đó.

Nếu một bean cần tài nguyên ngay trong constructor hoặc `@PostConstruct`, hãy tạo dependency khởi tạo phù hợp, không dựa vào runner chạy trước.

### 8.2. Tách khởi tạo dữ liệu khỏi bean construction

Tránh đưa công việc nặng hoặc phụ thuộc thứ tự nghiệp vụ vào constructor:

```java
@Service
public class SearchService {
    public SearchService() {
        // Không nên tải toàn bộ index hoặc chạy tác vụ dài tại đây
    }
}
```

Có thể tách thành service khởi tạo rõ ràng và điều phối sau khi context sẵn sàng:

```java
@Component
public class SearchIndexLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Tải hoặc làm mới index sau khi context đã khởi động
    }
}
```

Nếu nhiều runner cần thứ tự gọi, dùng `@Order`. Nếu một bean cần một dependency trong quá trình tạo, inject dependency đó. Hai giai đoạn phải được thiết kế riêng.

## 9. Thứ tự tạo bean và thứ tự gọi lifecycle callback

Một bean singleton thông thường trải qua những bước chính:

```text
Đăng ký BeanDefinition
       |
       v
Resolve constructor dependencies
       |
       v
Instantiate object
       |
       v
Populate properties / inject dependencies
       |
       v
BeanPostProcessor trước initialization
       |
       v
Initialization callbacks
(@PostConstruct, InitializingBean, initMethod...)
       |
       v
BeanPostProcessor sau initialization
       |
       v
Bean sẵn sàng cho client
```

Đây là sơ đồ giản lược. Thứ tự thực tế có các bước nội bộ và post-processor khác nhau.

Nếu `ServiceB` constructor inject `ServiceA`, Spring phải resolve `ServiceA` trước khi tạo hoàn chỉnh `ServiceB`. Khi `ServiceA` đã được khởi tạo xong, Spring mới có thể cung cấp nó để tiếp tục tạo `ServiceB`.

Nếu `ServiceB` chỉ có `@Order(2)` và `ServiceA` có `@Order(1)`, không có nghĩa callback `@PostConstruct` của A luôn chạy trước B. `@Order` không thêm dependency edge vào lifecycle graph.

### 9.1. `@PostConstruct` không phải cơ chế thay thế dependency injection

Ví dụ:

```java
@Component
public class FirstInitializer {
    @PostConstruct
    public void initialize() {
        System.out.println("Initialize first");
    }
}

@Component
public class SecondInitializer {
    @PostConstruct
    public void initialize() {
        System.out.println("Initialize second");
    }
}
```

Không có quan hệ dependency giữa hai bean. Gắn `@Order` lên class không phải cam kết chung rằng hai `@PostConstruct` sẽ chạy theo thứ tự order.

Nếu thứ tự này là yêu cầu thực sự, có thể:

- Đưa logic vào một coordinator nhận `List<Initializer>` đã sắp xếp và gọi các phương thức theo thứ tự sau khi context sẵn sàng.
- Dùng `@DependsOn` nếu bean thứ hai cần bean thứ nhất hoàn tất khởi tạo vì side effect.
- Thiết kế lại để quan hệ dependency được thể hiện bằng constructor injection.

### 9.2. `@DependsOn` ảnh hưởng cả thời điểm hủy

Giả sử `ClientBean` phụ thuộc vào một tài nguyên được `ResourceRegistry` chuẩn bị:

```java
@Component("resourceRegistry")
public class ResourceRegistry {
    @PostConstruct
    public void start() {
        // Chuẩn bị registry
    }

    @PreDestroy
    public void stop() {
        // Dọn dẹp registry
    }
}

@Component
@DependsOn("resourceRegistry")
public class ClientBean {
    @PreDestroy
    public void close() {
        // Đóng client khi registry vẫn còn tồn tại
    }
}
```

Với singleton beans, Spring khởi tạo `resourceRegistry` trước `clientBean` và hủy `clientBean` trước `resourceRegistry`. Điều này bảo đảm client có cơ hội đóng tài nguyên trước khi registry bị dọn dẹp.

## 10. Vấn đề lazy initialization và prototype

Thứ tự tạo bean còn bị ảnh hưởng bởi scope và lazy initialization. `@Order` không thay đổi những quy tắc này.

### 10.1. `@Lazy`

```java
@Component
@Lazy
public class ExpensiveCatalog {
    public ExpensiveCatalog() {
        System.out.println("Create ExpensiveCatalog");
    }
}
```

Bean được đánh dấu lazy có thể được trì hoãn tạo cho đến khi cần. Nếu một non-lazy singleton inject trực tiếp `ExpensiveCatalog` qua constructor, Spring vẫn cần tạo dependency để hoàn thành singleton đó.

`@Order(1)` trên `ExpensiveCatalog` không ép nó được khởi tạo trước các bean khác. Nếu muốn trì hoãn lookup, có thể dùng `ObjectProvider<ExpensiveCatalog>` và gọi `getObject()` khi cần.

### 10.2. Prototype

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {
}
```

Prototype bean được tạo mới khi container được yêu cầu resolve bean theo scope này. Nếu inject trực tiếp prototype vào một singleton qua constructor, việc resolve thường xảy ra một lần khi singleton được tạo; singleton giữ cùng instance prototype đó.

Muốn lấy instance mới mỗi lần xử lý:

```java
@Service
public class JobService {
    private final ObjectProvider<JobContext> contexts;

    public JobService(ObjectProvider<JobContext> contexts) {
        this.contexts = contexts;
    }

    public void process() {
        JobContext context = contexts.getObject();
        // Xử lý công việc với context mới
    }
}
```

`@Order` trên `JobContext` không quyết định lúc nào prototype được tạo. Nó chỉ có thể ảnh hưởng cách bean được sắp xếp ở những điểm hỗ trợ order.

## 11. Circular dependency không được giải quyết bằng `@Order`

Giả sử:

```java
@Service
public class ServiceA {
    public ServiceA(ServiceB serviceB) {
    }
}
```

```java
@Service
public class ServiceB {
    public ServiceB(ServiceA serviceA) {
    }
}
```

Hai bean phụ thuộc constructor lẫn nhau:

```text
ServiceA cần ServiceB
    ^             |
    |             v
ServiceB cần ServiceA
```

Không có thứ tự tạo hợp lệ vì A cần B trước khi A có thể được tạo, trong khi B cũng cần A trước khi B có thể được tạo. Gắn `@Order(1)` và `@Order(2)` không phá được vòng phụ thuộc này.

Spring thường báo lỗi circular dependency trong quá trình tạo bean. Cách xử lý bền vững là xem lại trách nhiệm class:

- Tách phần logic dùng chung thành bean thứ ba.
- Đảo chiều dependency bằng interface hoặc event khi phù hợp.
- Dùng `ObjectProvider`/`@Lazy` cho lookup trì hoãn nếu quan hệ đó thực sự cần thiết.
- Tránh hai service gọi trực tiếp lẫn nhau khi có thể tổ chức lại nghiệp vụ.

Không nên sử dụng `@DependsOn` để tạo thêm một vòng dependency khác; nó cũng không thể giải quyết chu trình khởi tạo.

## 12. Những nhầm lẫn thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Bean có `@Order(1)` luôn được tạo trước bean `@Order(2)`.” | `@Order` không điều khiển thứ tự khởi tạo singleton chung. |
| “`@Order` tạo quan hệ dependency.” | Nó chỉ cung cấp metadata order cho cơ chế có sử dụng comparator. |
| “Hai bean có order khác nhau thì `@PostConstruct` chạy theo order.” | Không có bảo đảm chung như vậy; cần dependency hoặc coordinator. |
| “`@DependsOn` và constructor injection giống nhau.” | Constructor injection biểu đạt dependency cần sử dụng; `@DependsOn` biểu đạt thứ tự khởi tạo theo tên bean. |
| “`@DependsOn` inject bean vào field.” | Nó không cấp tham chiếu; muốn sử dụng object, hãy inject nó. |
| “`@Order` chọn implementation mặc định.” | Dùng `@Primary` hoặc `@Qualifier` để chọn một bean. |
| “Order của runner quyết định thứ tự tạo runner.” | Nó quyết định thứ tự gọi runner trong giai đoạn Spring Boot thực thi runner. |
| “Thêm `@Order` có thể giải quyết circular dependency.” | Chu trình dependency cần được thiết kế lại hoặc lookup trì hoãn có chủ đích. |
| “Bean singleton luôn được tạo theo thứ tự file hoặc thứ tự khai báo.” | Không dựa vào thứ tự khai báo; biểu đạt quan hệ cần thiết bằng dependency graph. |

## 13. Cách chẩn đoán khi bean khởi tạo sai thứ tự mong đợi

Khi thấy log constructor hoặc `@PostConstruct` chạy theo thứ tự khác dự kiến, hãy xác định **bạn thực sự cần thứ tự nào**.

### 13.1. Nếu bean B cần object A

Kiểm tra chữ ký constructor của B:

```java
public ServiceB(ServiceA serviceA) {
    this.serviceA = serviceA;
}
```

Nếu không có dependency này nhưng B thật sự cần A, hãy bổ sung dependency phù hợp. Đừng chỉ thêm `@Order`.

### 13.2. Nếu B cần side effect của A nhưng không cần object A

Kiểm tra `@DependsOn`:

```java
@Component
@DependsOn("initializerA")
public class ServiceB {
}
```

Đảm bảo tên bean đúng và initializer thực sự hoàn thành công việc trong lifecycle callback trước khi bean B được khởi tạo.

### 13.3. Nếu cần sắp xếp các thao tác

Kiểm tra code có nhận `List<T>` hay `ObjectProvider<T>.orderedStream()` và có thực sự duyệt collection theo thứ tự không. Chỉ gắn `@Order` lên class mà không có cơ chế sắp xếp/điều phối thì chưa đủ.

### 13.4. Nếu thứ tự runner sai

Kiểm tra các runner có implement `Ordered` hoặc mang `@Order`, và ứng dụng đang dùng cơ chế Spring Boot gọi runner tiêu chuẩn hay không. Đừng suy ra thứ tự tạo bean từ thứ tự log bên trong `run()`.

### 13.5. Ghi log để quan sát

Bạn có thể in log ở constructor, `@PostConstruct` và method thực thi:

```java
@Component
@Order(10)
public class ImportTask implements StartupTask {

    public ImportTask() {
        System.out.println("Construct ImportTask");
    }

    @PostConstruct
    public void initialize() {
        System.out.println("Initialize ImportTask");
    }

    @Override
    public void execute() {
        System.out.println("Execute ImportTask");
    }
}
```

So sánh ba loại log:

- `Construct ...`: thời điểm object được khởi tạo.
- `Initialize ...`: callback lifecycle của bean.
- `Execute ...`: thời điểm code nghiệp vụ/runner được gọi.

Nếu mục tiêu là điều khiển thứ tự `execute()` của một collection, `@Order` có thể phù hợp. Nếu mục tiêu là `Initialize A` phải hoàn tất trước khi `Construct B`, hãy thể hiện dependency hoặc dùng `@DependsOn` theo đúng bản chất.

## 14. Bài thực hành

### Bài 1 — Quan sát `@Order` không quyết định constructor order

Tạo hai component:

```java
@Component
@Order(1)
public class AlphaTask {
    public AlphaTask() {
        System.out.println("Create AlphaTask");
    }
}

@Component
@Order(2)
public class BetaTask {
    public BetaTask() {
        System.out.println("Create BetaTask");
    }
}
```

Khởi động ứng dụng và ghi lại thứ tự constructor. Không kết luận thứ tự đó là hợp đồng của `@Order`.

### Bài 2 — Quan sát collection order

Tạo interface `Task`, cho `AlphaTask` và `BetaTask` implement interface. Inject `List<Task>` vào một coordinator và in danh sách theo thứ tự. So sánh với log constructor ở Bài 1.

**Câu hỏi:** hai loại thứ tự có phải một không? Vì sao?

### Bài 3 — Tạo dependency thật

Sửa `BetaTask` để constructor nhận `AlphaTask`:

```java
public BetaTask(AlphaTask alphaTask) {
    this.alphaTask = alphaTask;
}
```

Khởi động lại. Giải thích vì sao Spring cần resolve `AlphaTask` trước khi gọi constructor `BetaTask`, dù không có `@Order`.

### Bài 4 — Thử `@DependsOn`

Tạo bean `RegistryInitializer` có `@PostConstruct` đăng ký một giá trị vào registry dùng chung. Tạo bean `RegistryConsumer` đọc giá trị đó trong `@PostConstruct` và đặt:

```java
@DependsOn("registryInitializer")
```

Quan sát log. Sau đó bỏ `@DependsOn` và giải thích vì sao không nên dựa vào thứ tự component scan.

### Bài 5 — Sắp xếp runner

Khai báo ba `CommandLineRunner` có order 30, 10 và 20. Ghi log trong phương thức `run()`. Xác định thứ tự gọi và giải thích vì sao đây là trường hợp `@Order` có tác dụng.

### Bài 6 — Phân biệt ba yêu cầu

Cho các tình huống:

1. `InvoiceService` cần `TaxCalculator` để tính hóa đơn.
2. `PluginConsumer` cần registry được khởi tạo trước, nhưng không dùng object initializer.
3. `ValidationTask`, `AuditTask`, `NotificationTask` phải chạy theo trình tự trong pipeline.

Chọn giữa constructor injection, `@DependsOn` và `@Order`. Giải thích vì sao các công cụ không thể thay thế nhau.

### Bài 7 — Nhận diện circular dependency

Tạo hai service inject constructor lẫn nhau. Quan sát lỗi startup. Thử gắn `@Order` lên hai class và xác định vì sao lỗi không biến mất. Đề xuất cách tách trách nhiệm hoặc dùng provider khi cần lookup trì hoãn.

## 15. Ghi nhớ

**`@Order` sắp xếp phần tử ở những nơi có sử dụng order comparator; nó không tạo quan hệ phụ thuộc và không quyết định thứ tự khởi tạo singleton bean.** Khi một bean cần một bean khác để được tạo hoặc hoạt động, hãy biểu đạt quan hệ đó bằng dependency injection. Khi chỉ cần một bean được khởi tạo trước vì side effect, cân nhắc `@DependsOn`. Khi cần duyệt nhiều bean theo trình tự, dùng `@Order` với collection hoặc extension point hỗ trợ sắp xếp.

Hãy tách rõ ba câu hỏi khi thiết kế vòng đời bean: *Bean cần object nào? Bean nào phải hoàn thành khởi tạo trước? Và các thao tác trên một tập bean cần chạy theo thứ tự nào?* Trả lời đúng từng câu hỏi giúp ứng dụng Spring Boot dễ dự đoán, ít phụ thuộc vào thứ tự đăng ký tình cờ và dễ bảo trì hơn.
