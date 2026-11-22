# Phân biệt callback khởi tạo bean, runner và tín hiệu sẵn sàng

Trong Spring Boot, có nhiều cách để chạy code khi ứng dụng khởi động. Bạn có thể đặt logic vào `@PostConstruct`, triển khai `InitializingBean`, khai báo `initMethod` trong `@Bean`, viết `ApplicationRunner` hoặc `CommandLineRunner`, hoặc lắng nghe `ApplicationReadyEvent`.

Những cơ chế này xuất hiện ở các **thời điểm khác nhau** và trả lời **những câu hỏi khác nhau**:

- **Callback khởi tạo bean:** Bean này cần chuẩn bị gì trước khi được sử dụng?
- **Runner:** Sau khi application context đã được khởi động, ứng dụng cần thực hiện công việc nào trước khi công bố trạng thái sẵn sàng?
- **Tín hiệu sẵn sàng:** Ứng dụng đã vượt qua những bước startup cần thiết và có thể bắt đầu nhận traffic theo cơ chế readiness chưa?

Nếu nhầm các mốc trên, bạn có thể vô tình gọi một service khi dependency chưa sẵn sàng, chạy truy vấn nặng trong constructor, hoặc để load balancer gửi request vào ứng dụng khi dữ liệu khởi tạo vẫn chưa hoàn tất.

## 1. Bức tranh tổng thể của quá trình khởi động

Với một ứng dụng Spring Boot sử dụng application context thông thường, có thể hình dung trình tự:

```text
SpringApplication.run(args)
          |
          v
Chuẩn bị Environment và ApplicationContext
          |
          v
Đọc cấu hình và đăng ký BeanDefinition
          |
          v
Tạo những singleton bean cần thiết
          |
          +--> Constructor
          |
          +--> Dependency injection / property population
          |
          +--> @PostConstruct
          |
          +--> InitializingBean.afterPropertiesSet()
          |
          +--> @Bean(initMethod = "...")
          |
          v
ApplicationContext refresh hoàn tất
          |
          +--> ContextRefreshedEvent
          |
          v
ApplicationStartedEvent
          |
          v
ApplicationRunner / CommandLineRunner
          |
          v
ApplicationReadyEvent
          |
          v
ReadinessState.ACCEPTING_TRAFFIC
```

Sơ đồ được giản lược để tập trung vào các mốc đang học. Trên thực tế còn có `BeanPostProcessor`, xử lý proxy, `SmartLifecycle`, khởi động embedded web server, các event khác và những bước nội bộ phụ thuộc phiên bản Spring Boot.

Một điểm quan trọng: **một web server có thể đã được khởi tạo và bắt đầu lắng nghe trước `ApplicationReadyEvent`**. Vì thế, cần phân biệt việc socket có thể nhận kết nối với tín hiệu readiness dùng để điều phối traffic.

### 1.1. Bảng so sánh nhanh

| Cơ chế | Thời điểm điển hình | Phạm vi | Dùng cho |
| --- | --- | --- | --- |
| Constructor | Khi Spring tạo instance | Một bean | Nhận dependency và thiết lập trạng thái đối tượng |
| `@PostConstruct` | Sau dependency injection, trong quá trình khởi tạo bean | Một bean | Kiểm tra và chuẩn bị trạng thái nội bộ |
| `InitializingBean` | Trong giai đoạn initialization của bean | Một bean | Callback khởi tạo theo interface Spring |
| `@Bean(initMethod = "...")` | Trong giai đoạn initialization của bean | Một bean | Callback tùy chỉnh, nhất là class của thư viện |
| `SmartInitializingSingleton` | Sau khi pre-instantiate các singleton non-lazy trong bean factory | Bean/container | Công việc cần các singleton eager đã được tạo |
| `ContextRefreshedEvent` | Khi context refresh hoàn tất | Một `ApplicationContext` | Quan sát mốc refresh |
| `ApplicationRunner` | Sau `ApplicationStartedEvent`, trước `ApplicationReadyEvent` | Lần chạy ứng dụng | Startup task cần `ApplicationArguments` |
| `CommandLineRunner` | Cùng giai đoạn với `ApplicationRunner` | Lần chạy ứng dụng | Startup task nhận `String... args` |
| `ApplicationReadyEvent` | Sau khi các runner chạy xong | Lần chạy Spring Boot | Quan sát mốc application ready |
| `AvailabilityChangeEvent<ReadinessState>` | Khi trạng thái readiness thay đổi | Trạng thái availability | Thông báo chấp nhận hoặc từ chối traffic |

## 2. Callback khởi tạo bean: gắn với vòng đời của từng đối tượng

Spring quản lý bean qua các bước tạo instance, cấp dependency, khởi tạo và hủy theo scope. Callback initialization là nơi bean tự hoàn tất những việc cần thiết để ở trạng thái sử dụng được.

Ví dụ, một component có thể cần:

- Kiểm tra giá trị cấu hình đã được inject.
- Tạo một cấu trúc dữ liệu nội bộ từ cấu hình.
- Chuẩn bị bộ ánh xạ hoặc bảng tra cứu nhỏ.
- Đăng ký tài nguyên cục bộ thuộc quyền sở hữu của bean.

Callback này **không phải** tín hiệu rằng toàn bộ ứng dụng đã khởi động, bởi các bean khác vẫn có thể đang chờ được tạo và application context có thể chưa refresh xong.

### 2.1. Constructor và callback không giống nhau

Ví dụ:

```java
package com.example.demo;

import org.springframework.stereotype.Component;

@Component
public class CurrencyFormatter {

    private final CurrencySettings settings;

    public CurrencyFormatter(CurrencySettings settings) {
        this.settings = settings;
        System.out.println("1. Constructor CurrencyFormatter");
    }
}
```

Constructor thể hiện dependency bắt buộc. Spring phải có `CurrencySettings` phù hợp trước khi gọi constructor.

Không nên đặt công việc có side effect lớn như gọi API mạng, tạo database schema hoặc chạy batch job trong constructor. Nếu constructor ném exception, việc tạo bean thất bại; nếu thao tác mất nhiều thời gian, startup có thể bị giữ lại ở giai đoạn container đang tạo bean.

### 2.2. `@PostConstruct`

Trong ứng dụng dùng Spring Boot 3.x với Jakarta APIs, annotation nằm ở:

```java
import jakarta.annotation.PostConstruct;
```

Ví dụ:

```java
package com.example.demo;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class ExchangeRateTable {

    private final CurrencySettings settings;
    private int defaultPrecision;

    public ExchangeRateTable(CurrencySettings settings) {
        this.settings = settings;
    }

    @PostConstruct
    public void initialize() {
        defaultPrecision = settings.precision();
        if (defaultPrecision < 0) {
            throw new IllegalArgumentException(
                    "Currency precision must be non-negative"
            );
        }
        System.out.println("ExchangeRateTable initialized");
    }

    public int precision() {
        return defaultPrecision;
    }
}
```

Ở đây `CurrencySettings` là dependency được dự án định nghĩa, ví dụ một bean hoặc configuration properties object phù hợp. `@PostConstruct` chạy sau khi Spring đã thực hiện dependency injection cần thiết cho bean và trước khi bean được công khai như đã khởi tạo hoàn chỉnh.

Nếu dự án đang dùng Spring Boot 2.x, annotation có thể là `javax.annotation.PostConstruct`; hãy sử dụng package tương ứng với phiên bản Spring Framework/Boot của dự án.

### 2.3. `InitializingBean.afterPropertiesSet()`

Spring còn cung cấp interface:

```java
import org.springframework.beans.factory.InitializingBean;
```

Ví dụ:

```java
@Component
public class TemplateRegistry implements InitializingBean {

    private final TemplateProperties properties;

    public TemplateRegistry(TemplateProperties properties) {
        this.properties = properties;
    }

    @Override
    public void afterPropertiesSet() {
        if (properties.directory() == null) {
            throw new IllegalStateException(
                    "Template directory is required"
            );
        }
        System.out.println("TemplateRegistry initialized");
    }
}
```

`InitializingBean` gắn class trực tiếp với API của Spring. Điều này phù hợp với một số thành phần framework, nhưng với class nghiệp vụ thông thường, `@PostConstruct` hoặc init method do cấu hình khai báo thường giúp class ít phụ thuộc framework hơn.

### 2.4. `@Bean(initMethod = "...")`

Nếu một class không thể sửa source code, ví dụ do thư viện ngoài cung cấp, bạn vẫn có thể cấu hình callback khởi tạo:

```java
package com.example.demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ParserConfiguration {

    @Bean(initMethod = "initialize", destroyMethod = "close")
    public ParserEngine parserEngine() {
        return new ParserEngine();
    }
}
```

Ví dụ giả định `ParserEngine` có phương thức `initialize()` và `close()` phù hợp. Spring gọi `initialize()` trong quá trình khởi tạo bean, và gọi `close()` theo lifecycle hủy thích hợp.

Callback init method có ích khi class thư viện không mang `@PostConstruct` hoặc không triển khai `InitializingBean`.

### 2.5. Thứ tự callback bên trong một bean

Với một singleton thông thường sử dụng đầy đủ các cơ chế, thứ tự khái quát là:

```text
Constructor / factory method
          |
          v
Dependency injection
          |
          v
BeanPostProcessor trước initialization
          |
          v
@PostConstruct
          |
          v
InitializingBean.afterPropertiesSet()
          |
          v
Custom init method
          |
          v
BeanPostProcessor sau initialization
          |
          v
Bean được cung cấp cho các thành phần khác
```

`@PostConstruct` thường được kích hoạt qua `BeanPostProcessor` chuyên trách, vì vậy sơ đồ trên chỉ tách nó thành một bước dễ học; trong implementation thực tế, nó nằm trong phần xử lý trước initialization callback của bean. Proxy có thể được tạo ở một thời điểm thích hợp trong quy trình post-processing.

**Thứ tự callback bên trong một bean không đồng nghĩa với thứ tự khởi tạo giữa các bean khác nhau.** Nếu bean B cần bean A, hãy khai báo dependency bằng constructor injection hoặc dùng `@DependsOn` trong tình huống chỉ cần ràng buộc thứ tự khởi tạo.

## 3. Callback khởi tạo không có nghĩa mọi bean đều đã sẵn sàng

Giả sử có hai component:

```java
@Component
public class CatalogCache {
    @PostConstruct
    public void initialize() {
        System.out.println("CatalogCache initialized");
    }
}
```

```java
@Component
public class PriceIndex {
    @PostConstruct
    public void initialize() {
        System.out.println("PriceIndex initialized");
    }
}
```

Không nên giả định `CatalogCache` luôn khởi tạo trước `PriceIndex` chỉ vì file của nó đứng trước trong source tree. Cả hai không có quan hệ dependency được khai báo.

Nếu `PriceIndex` thật sự cần `CatalogCache`, hãy thể hiện quan hệ:

```java
@Component
public class PriceIndex {

    private final CatalogCache cache;

    public PriceIndex(CatalogCache cache) {
        this.cache = cache;
    }

    @PostConstruct
    public void initialize() {
        // Cache đã được resolve và khởi tạo phù hợp
    }
}
```

Container hiểu `CatalogCache` là dependency của `PriceIndex`. Không cần dùng `@Order` để tạo quan hệ này.

### 3.1. Tác động của `@Lazy`

```java
@Component
@Lazy
public class HeavyDictionary {

    @PostConstruct
    public void initialize() {
        System.out.println("HeavyDictionary initialized");
    }
}
```

Bean được khai báo lazy có thể chỉ được tạo khi có thành phần thực sự yêu cầu nó. Vì vậy callback khởi tạo của bean lazy **có thể chạy sau `ApplicationReadyEvent`** nếu không có dependency eager nào yêu cầu bean đó trong startup.

Ngược lại, nếu một singleton non-lazy inject trực tiếp `HeavyDictionary`, Spring cần resolve dependency và có thể tạo bean ngay trong startup.

Đừng dùng `@PostConstruct` của một bean lazy làm mốc rằng toàn bộ ứng dụng đã được khởi tạo.

### 3.2. Tác động của prototype scope

Một bean `prototype` được tạo mới mỗi lần Spring được yêu cầu cung cấp instance theo scope đó:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class JobContext {

    @PostConstruct
    public void initialize() {
        System.out.println("New JobContext initialized");
    }
}
```

Trong ví dụ này cần import `Scope` và `ConfigurableBeanFactory` tương ứng. Callback có thể chạy nhiều lần khi nhiều prototype instances được tạo, kể cả sau khi ứng dụng đã ready.

Do đó, bean initialization là một **vòng đời theo bean instance**, không phải một sự kiện startup toàn ứng dụng chỉ xảy ra đúng một lần.

## 4. `SmartInitializingSingleton`: sau các singleton non-lazy

Spring Framework cung cấp `SmartInitializingSingleton` với phương thức `afterSingletonsInstantiated()`.

```java
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.stereotype.Component;

@Component
public class StartupRegistryInspector
        implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println(
                "Regular non-lazy singletons have been instantiated"
        );
    }
}
```

Callback này được gọi sau giai đoạn pre-instantiation của các singleton non-lazy trong `BeanFactory`. Nó hữu ích khi một thành phần cần nhìn thấy trạng thái đã được chuẩn bị bởi các singleton eager.

Tuy nhiên, vẫn có những giới hạn:

- Bean lazy có thể chưa được tạo.
- Bean prototype không được pre-instantiate như singleton eager.
- Application context vẫn có thể chưa hoàn tất refresh.
- Startup runners chưa chạy.
- Không có bảo đảm hệ thống bên ngoài đã sẵn sàng.

`SmartInitializingSingleton` là cơ chế phù hợp với một số thành phần hạ tầng cần phối hợp giữa các bean, nhưng **không thay thế `ApplicationReadyEvent`** khi muốn quan sát mốc ứng dụng đã đi qua runners.

## 5. Khi nào `ApplicationContext` được xem là đã refresh?

Khi `ApplicationContext.refresh()` hoàn tất, Spring Framework đã thực hiện những bước quan trọng như xử lý bean definitions, tạo các singleton eager thích hợp, đăng ký listener và khởi động những lifecycle processor liên quan.

Spring Framework phát:

```java
ContextRefreshedEvent
```

Ví dụ:

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

Trong ứng dụng Spring Boot, event này thông thường đến **trước `ApplicationStartedEvent` và trước các startup runners**.

Nếu ứng dụng có nhiều application context, ví dụ parent-child hierarchy, các context có thể refresh riêng và event có thể được propagate. Đừng coi `ContextRefreshedEvent` là tín hiệu duy nhất cho toàn bộ ứng dụng Spring Boot.

### 5.1. `SmartLifecycle` và server startup

Spring còn có interface `SmartLifecycle` cho các thành phần cần start/stop theo lifecycle của context. Những thành phần này có thể được điều phối khi context refresh hoặc khi context start/stop, tùy phase và cấu hình.

Đây là cơ chế khác với `@PostConstruct`:

- Initialization callback chuẩn bị **một bean**.
- `SmartLifecycle.start()`/`stop()` quản lý **hoạt động của một thành phần trong context**.
- Runner thực hiện **startup task ở giai đoạn sau context refresh**.

Ví dụ một message listener container cần bắt đầu tiêu thụ message có thể dùng lifecycle management. Nhưng việc component đã start không chứng minh tất cả startup runner đã hoàn tất hoặc readiness đã chuyển sang accepting traffic.

## 6. `ApplicationRunner` và `CommandLineRunner` là gì?

Hai interface do Spring Boot cung cấp để thực hiện công việc **sau khi application context đã được refresh**, nhưng **trước khi Spring Boot phát `ApplicationReadyEvent`**.

`CommandLineRunner`:

```java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

`ApplicationRunner`:

```java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

Khi Spring Boot khởi động thành công tới giai đoạn runner, nó tìm các bean triển khai hai interface này, sắp xếp chúng theo order được hỗ trợ và gọi các phương thức `run(...)`.

### 6.1. `CommandLineRunner` nhận đối số thô

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class PrintArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        for (String arg : args) {
            System.out.println("Argument: " + arg);
        }
    }
}
```

Runner nhận các chuỗi argument mà chương trình truyền vào. Ví dụ `--mode=import` vẫn là một chuỗi; muốn phân tích cú pháp bạn cần tự xử lý hoặc dùng `ApplicationRunner`.

### 6.2. `ApplicationRunner` nhận `ApplicationArguments`

```java
package com.example.demo.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class ImportModeRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (args.containsOption("mode")) {
            List<String> values = args.getOptionValues("mode");
            System.out.println("Modes: " + values);
        }

        System.out.println(
                "Non-option arguments: " + args.getNonOptionArgs()
        );
    }
}
```

Ví dụ nếu chạy ứng dụng với:

```text
--mode=import catalog.json
```

`ApplicationArguments` giúp tách option `mode` và non-option argument `catalog.json`. Nó hữu ích cho ứng dụng command-line hoặc batch job.

### 6.3. Runner dùng được bean đã được Spring quản lý

```java
package com.example.demo.startup;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class CatalogWarmupRunner implements ApplicationRunner {

    private final CatalogService catalogService;

    public CatalogWarmupRunner(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalogService.warmUp();
    }
}
```

`CatalogService` là một Spring bean phù hợp được inject qua constructor. Khi runner được gọi, application context đã refresh, nên đây thường là nơi thích hợp hơn `@PostConstruct` để điều phối công việc startup cần nhiều service.

Vẫn phải lưu ý các bean lazy, kết nối ngoài và điều kiện khởi tạo thực tế; context refresh thành công không tự bảo đảm Redis, database hoặc dịch vụ đối tác sẽ phản hồi.

## 7. Runner có thể làm gì và không nên làm gì?

Những tình huống phù hợp:

- Kiểm tra cấu hình quan trọng trước khi công bố readiness.
- Tải dữ liệu tham chiếu nhỏ hoặc cache bắt buộc cho request đầu tiên.
- Thực hiện startup job hữu hạn của ứng dụng console.
- Kiểm tra khả năng dùng một dịch vụ phụ thuộc nếu ứng dụng **không thể phục vụ** khi thiếu dịch vụ đó.
- Ghi nhận thông tin startup hoặc các bước migration/initialization đã được thiết kế riêng.

Những tình huống cần cẩn trọng:

- Chạy vòng lặp vô hạn trong runner.
- Gọi API không có timeout.
- Đồng bộ hóa dữ liệu lớn không giới hạn thời gian.
- Khởi chạy thread chạy nền rồi mặc nhiên xem công việc đó đã hoàn tất.
- Thực hiện migration database cạnh tranh giữa nhiều replica mà không có cơ chế khóa/idempotency.

Vì runner chạy **trước `ApplicationReadyEvent`**, một runner đồng bộ chạy lâu sẽ làm chậm hoặc ngăn ứng dụng đi tới readiness. Đây có thể là hành vi mong muốn nếu công việc là điều kiện bắt buộc để phục vụ traffic, nhưng phải có thời gian chờ, xử lý lỗi và khả năng giám sát.

### 7.1. Khi runner ném exception

Ví dụ:

```java
@Component
public class StartupValidationRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        throw new IllegalStateException(
                "Required reference data is missing"
        );
    }
}
```

Nếu exception không được xử lý, Spring Boot coi quá trình startup là thất bại và không đi tới `ApplicationReadyEvent` như trong luồng khởi động thành công. Spring Boot có thể phát `ApplicationFailedEvent`, thực hiện shutdown và báo lỗi tương ứng.

Điểm khác biệt với exception trong `@PostConstruct`: lỗi callback xảy ra trong lúc tạo bean/refresh context; lỗi runner xảy ra **sau khi context đã refresh**, trong giai đoạn startup task.

### 7.2. Runner chạy bất đồng bộ không chặn readiness

Ví dụ cần suy nghĩ:

```java
@Component
public class BackgroundWarmupRunner implements ApplicationRunner {

    private final Executor executor;
    private final CatalogService catalogService;

    public BackgroundWarmupRunner(
            Executor executor,
            CatalogService catalogService) {
        this.executor = executor;
        this.catalogService = catalogService;
    }

    @Override
    public void run(ApplicationArguments args) {
        executor.execute(catalogService::warmUp);
    }
}
```

Giả sử một `Executor` phù hợp đã được cấu hình. Runner chỉ **gửi công việc vào executor rồi trả về**. Spring Boot có thể tiếp tục phát `ApplicationReadyEvent` trong khi `warmUp()` còn đang chạy.

Nếu dữ liệu warm-up là điều kiện bắt buộc để xử lý request, cách này chưa đủ để ngăn ứng dụng nhận traffic quá sớm. Cần đợi công việc hoàn tất trong runner, hoặc thiết kế readiness gate riêng dựa trên trạng thái thực tế.

## 8. Thứ tự thực thi nhiều runner

Spring Boot có thể có nhiều bean `ApplicationRunner` và `CommandLineRunner`. Bạn có thể dùng `@Order` hoặc interface `Ordered` để sắp xếp.

Ví dụ:

```java
@Component
@Order(10)
public class ValidateConfigurationRunner
        implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("1. Validate configuration");
    }
}
```

```java
@Component
@Order(20)
public class LoadCatalogRunner
        implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("2. Load catalog");
    }
}
```

Khi hai runner được sắp xếp theo order, runner có giá trị nhỏ hơn được gọi trước. Spring Boot sắp xếp các runner thuộc hai interface trong cùng giai đoạn startup.

**`@Order` ở đây điều chỉnh thứ tự gọi `run(...)`, không quyết định thứ tự constructor hoặc `@PostConstruct` của những bean runner.**

Nếu runner thứ hai bắt buộc cần kết quả do runner thứ nhất tạo, nên cân nhắc:

- Gộp các bước vào một coordinator có thứ tự rõ ràng.
- Biểu đạt dependency qua service phù hợp.
- Dùng `@Order` nếu cả hai thực sự là startup tasks và thứ tự là hợp đồng của ứng dụng.
- Bảo đảm kết quả được kiểm tra, lỗi được báo và tác vụ có thể chạy lại an toàn.

Không nên dựa vào thứ tự giữa hai runner có cùng giá trị order khi thứ tự đó có ý nghĩa nghiệp vụ.

### 8.1. Khác `@DependsOn` như thế nào?

```java
@Component
@DependsOn("schemaInitializer")
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // ...
    }
}
```

`@DependsOn("schemaInitializer")` yêu cầu bean có tên `schemaInitializer` được khởi tạo trước `ImportRunner`. Nó **không** tự yêu cầu Spring gọi `run()` của một runner khác trước runner này.

Vì vậy cần phân biệt:

| Cơ chế | Điều khiển |
| --- | --- |
| Constructor injection | Dependency cần được resolve để tạo bean |
| `@DependsOn` | Quan hệ thứ tự khởi tạo các bean |
| `@Order` trên runner | Thứ tự gọi các runner trong giai đoạn startup |

## 9. `ApplicationStartedEvent` và `ApplicationReadyEvent`

Spring Boot phát hai event dễ bị nhầm:

```text
ApplicationContext refresh hoàn tất
             |
             v
ApplicationStartedEvent
             |
             v
Chạy ApplicationRunner / CommandLineRunner
             |
             v
ApplicationReadyEvent
```

### 9.1. `ApplicationStartedEvent`

`ApplicationStartedEvent` được phát sau khi context refresh và trước runners. Nó phù hợp khi muốn ghi nhận rằng nền tảng Spring đã được dựng xong nhưng startup tasks vẫn chưa thực hiện.

Ví dụ:

```java
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartedReporter {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("Context refreshed; runners not yet called");
    }
}
```

Không nên dùng event này để xác nhận dữ liệu do `CatalogWarmupRunner` chuẩn bị đã hoàn tất.

### 9.2. `ApplicationReadyEvent`

`ApplicationReadyEvent` được phát sau khi các startup runners hoàn tất thành công.

```java
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyReporter {

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println("Spring Boot application ready");
    }
}
```

Đây là mốc hữu ích để thông báo rằng quá trình startup của Spring Boot đã đi đến cuối luồng bình thường.

Tuy nhiên, **`ApplicationReadyEvent` không tự chứng minh tất cả external services đang khỏe hoặc tất cả background jobs đã kết thúc**. Nó chỉ có ý nghĩa dựa trên những bước khởi động mà ứng dụng thực sự thực hiện và chờ hoàn tất.

### 9.3. Listener `ApplicationReadyEvent` có thể chặn quá trình phát event

Trong mô hình event multicaster đồng bộ thông thường, listener được gọi trong luồng phát event. Nếu listener làm việc lâu, việc phát `ApplicationReadyEvent` sẽ bị giữ lại cho tới khi listener hoàn tất.

```java
@EventListener(ApplicationReadyEvent.class)
public void onReady() {
    // Nếu thực hiện một thao tác blocking dài ở đây,
    // quá trình hoàn tất startup có thể bị kéo dài.
}
```

Nếu listener tự khởi chạy một thread/tác vụ async rồi trả về ngay, nó cũng không thể bảo đảm tác vụ đã hoàn tất khi Spring Boot tiếp tục xử lý trạng thái readiness.

Với công việc **bắt buộc trước khi ready**, một runner đồng bộ có timeout và xử lý lỗi rõ ràng thường dễ hiểu hơn. Với công việc **không bắt buộc**, event listener hoặc một thành phần chạy nền có quản lý lifecycle có thể phù hợp hơn.

## 10. Readiness: tín hiệu sẵn sàng nhận traffic

Spring Boot cung cấp API availability để biểu diễn hai khái niệm:

- **Liveness:** tiến trình/ứng dụng vẫn hoạt động và không rơi vào trạng thái cần được khởi động lại.
- **Readiness:** ứng dụng đang sẵn sàng nhận request từ hệ thống điều phối hoặc load balancer.

Các enum thường dùng:

```java
LivenessState.CORRECT
LivenessState.BROKEN

ReadinessState.ACCEPTING_TRAFFIC
ReadinessState.REFUSING_TRAFFIC
```

Chúng nằm trong package `org.springframework.boot.availability`.

### 10.1. Readiness thay đổi qua những mốc nào?

Ở mức khái niệm:

```text
Quá trình startup
       |
       v
ReadinessState.REFUSING_TRAFFIC
       |
       v
Context refresh
       |
       v
Startup runners
       |
       v
ApplicationReadyEvent
       |
       v
ReadinessState.ACCEPTING_TRAFFIC
```

Theo luồng Spring Boot phổ biến, trạng thái accepting được công bố sau `ApplicationReadyEvent`. Khi quá trình shutdown bắt đầu, readiness có thể được chuyển về refusing trước khi hoàn tất đóng ứng dụng.

Đây là tín hiệu **logic** của ứng dụng. Việc load balancer có thực sự ngừng hoặc bắt đầu gửi request còn phụ thuộc probe, cấu hình orchestration, chu kỳ thăm dò và thời gian cập nhật endpoint.

### 10.2. `ApplicationAvailability`

Bạn có thể inject `ApplicationAvailability` để xem trạng thái hiện tại:

```java
package com.example.demo;

import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.stereotype.Service;

@Service
public class AvailabilityReporter {

    private final ApplicationAvailability availability;

    public AvailabilityReporter(
            ApplicationAvailability availability) {
        this.availability = availability;
    }

    public boolean acceptingTraffic() {
        return availability.getReadinessState()
                == ReadinessState.ACCEPTING_TRAFFIC;
    }
}
```

`ApplicationAvailability` mô tả trạng thái được Spring Boot và ứng dụng công bố, không phải một phép kiểm tra tự động mọi dependency bên ngoài.

### 10.3. Phát `AvailabilityChangeEvent`

Ứng dụng có thể thay đổi trạng thái readiness:

```java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationContext;

public void refuseNewTraffic(ApplicationContext context) {
    AvailabilityChangeEvent.publish(
            context,
            ReadinessState.REFUSING_TRAFFIC
    );
}
```

Ví dụ này hữu ích khi ứng dụng đang hoạt động nhưng tạm thời không thể xử lý request, chẳng hạn khi đang mất một tài nguyên bắt buộc.

**Thời điểm phát rất quan trọng:** nếu một listener phát `REFUSING_TRAFFIC` ngay trong `ApplicationReadyEvent`, Spring Boot vẫn có thể phát `ACCEPTING_TRAFFIC` sau khi xử lý xong ready event. Vì vậy, không nên chỉ dùng một lệnh publish trong ready listener để làm cơ chế chặn readiness trong toàn bộ quá trình startup.

Nếu cần chặn traffic cho đến khi một tác vụ hoàn tất, hãy chọn thiết kế cụ thể: chờ công việc trong startup runner, dùng readiness health indicator/gate phản ánh trạng thái chuẩn bị, hoặc điều phối trạng thái sau startup một cách rõ ràng.

### 10.4. Readiness không đồng nghĩa với kết nối TCP đã mở

Trong web application, embedded server có thể bắt đầu nhận kết nối trước khi Spring Boot phát readiness accepting. Một client gọi trực tiếp vào cổng vẫn có thể nhận response, trong khi orchestrator chưa đưa instance vào danh sách nhận traffic.

Điều này giải thích tại sao cần readiness probe trong môi trường triển khai nhiều replica: probe giúp hệ thống điều phối quyết định khi nào bắt đầu định tuyến request đến replica mới.

## 11. Readiness với Spring Boot Actuator

Khi có Spring Boot Actuator, ứng dụng có thể expose health endpoints, bao gồm các health group cho liveness/readiness nếu được hỗ trợ và cấu hình phù hợp.

Ví dụ dependency trong một dự án Spring Boot 3.x dùng Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Để bật health probes trong môi trường local phù hợp:

```properties
management.endpoint.health.probes.enabled=true
```

Khi các endpoint được expose qua HTTP và không bị chặn bởi cấu hình bảo mật, bạn có thể kiểm tra:

```text
GET /actuator/health/liveness
GET /actuator/health/readiness
```

Đường dẫn cụ thể còn tùy `management.endpoints.web.base-path`, management port và cấu hình Actuator. Nếu ứng dụng chạy trên Kubernetes, Spring Boot có thể tự nhận biết môi trường và bật probes theo quy tắc của phiên bản đang dùng.

### 11.1. Ví dụ cấu hình Kubernetes probe

Ví dụ khái niệm:

```yaml
livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
```

Đây chỉ là phần cấu hình probe cần đặt dưới một container trong Pod spec. Thông số delay, timeout và threshold phải được chọn theo thời gian startup và yêu cầu thực tế; không nên sao chép nguyên xi vào production.

Nếu Actuator chạy trên **management port riêng**, probe ở cổng quản trị có thể vẫn thành công khi cổng ứng dụng chính gặp vấn đề. Khi cần kiểm tra sát đường nhận traffic thực tế, hãy xem khả năng expose probe trên cổng ứng dụng chính theo cấu hình Actuator của phiên bản đang sử dụng.

### 11.2. Có nên đưa mọi dependency vào liveness/readiness?

Liveness chỉ nên phản ánh tình trạng cần khởi động lại tiến trình. Nếu cho lỗi tạm thời của database vào liveness, orchestrator có thể liên tục restart những replica đang khỏe về mặt tiến trình và làm tình hình xấu hơn.

Readiness có thể phản ánh các dependency **thực sự bắt buộc để phục vụ request**, nhưng cũng cần cân nhắc: nếu tất cả replica cùng mất kết nối một dịch vụ chung, đánh dấu tất cả unready có thể khiến hệ thống không còn endpoint nhận traffic.

Do đó, readiness phải gắn với cách ứng dụng phục vụ traffic và chiến lược phục hồi của hệ thống, thay vì tự động coi mọi dependency bên ngoài là nguyên nhân từ chối request.

## 12. Một ví dụ chạy xuyên suốt ba mốc

Ví dụ sau minh họa một bean chuẩn bị trạng thái nội bộ, một runner làm công việc bắt buộc sau context refresh, và một listener ghi nhận mốc ready.

### 12.1. Lớp khởi động

`DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 12.2. Bean có callback initialization

`LocalCatalog.java`:

```java
package com.example.demo;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;

@Component
public class LocalCatalog {

    private boolean initialized;
    private boolean warmedUp;

    @PostConstruct
    public void initialize() {
        initialized = true;
        System.out.println("[1] LocalCatalog initialized");
    }

    public void warmUp() {
        if (!initialized) {
            throw new IllegalStateException(
                    "LocalCatalog has not been initialized"
            );
        }
        warmedUp = true;
        System.out.println("[3] LocalCatalog warm-up completed");
    }

    public boolean isWarmedUp() {
        return warmedUp;
    }
}
```

`LocalCatalog.initialize()` chỉ chuẩn bị trạng thái cơ bản của chính bean đó. Công việc warm-up sẽ được runner gọi sau khi context refresh.

Ở ví dụ này, `initialized` và `warmedUp` là trạng thái đơn giản dùng để quan sát. Nếu trạng thái được truy cập đồng thời bởi nhiều thread, ứng dụng thực tế cần cơ chế đồng bộ hóa phù hợp như `volatile`, atomic type hoặc thiết kế immutable.

### 12.3. Ghi nhận `ApplicationStartedEvent`

`StartedListener.java`:

```java
package com.example.demo;

import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartedListener {

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        System.out.println("[2] Application started");
    }
}
```

Listener này chạy sau context refresh và trước startup runners.

### 12.4. Runner làm công việc bắt buộc

`CatalogWarmupRunner.java`:

```java
package com.example.demo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class CatalogWarmupRunner implements ApplicationRunner {

    private final LocalCatalog catalog;

    public CatalogWarmupRunner(LocalCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public void run(ApplicationArguments args) {
        catalog.warmUp();
    }
}
```

Runner được gọi ở giai đoạn sau context refresh. Vì `warmUp()` chạy đồng bộ trong phương thức `run(...)`, Spring Boot chờ runner hoàn tất trước khi tiến đến `ApplicationReadyEvent`.

### 12.5. Listener quan sát mốc ready

`ReadyListener.java`:

```java
package com.example.demo;

import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ReadyListener {

    private final LocalCatalog catalog;

    public ReadyListener(LocalCatalog catalog) {
        this.catalog = catalog;
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        System.out.println(
                "[4] Application ready; catalog warmed up = " +
                catalog.isWarmedUp()
        );
    }
}
```

### 12.6. Đầu ra minh họa

Trong một ứng dụng có các component trên và không có lỗi startup, những dòng log do ví dụ in ra thường xuất hiện theo thứ tự:

```text
[1] LocalCatalog initialized
[2] Application started
[3] LocalCatalog warm-up completed
[4] Application ready; catalog warmed up = true
```

Những log khác của Spring Boot có thể xen giữa. Nếu ứng dụng có các bean hoặc runner khác, không nên lấy ví dụ này làm cam kết tuyệt đối về thứ tự callback giữa mọi bean. Thứ tự của **các mốc chính** là điều cần chú ý:

```text
Bean initialization
       <
ApplicationStartedEvent
       <
Runner hoàn tất
       <
ApplicationReadyEvent
```

Trong ví dụ, `LocalCatalog` được tạo sớm do runner và listener phụ thuộc vào nó. Với một bean lazy không được yêu cầu trong startup, callback bean đó có thể chạy sau các mốc trên.

## 13. Khi khởi động thất bại, những mốc nào còn xảy ra?

Đây là cách thực tế để nhận ra vai trò của từng cơ chế.

### 13.1. Exception trong `@PostConstruct`

```java
@PostConstruct
public void initialize() {
    throw new IllegalStateException("Invalid configuration");
}
```

Nếu đây là bean eager được tạo trong quá trình refresh và exception không được xử lý, context refresh có thể thất bại. Khi đó startup không đi tiếp tới runner và `ApplicationReadyEvent`.

### 13.2. Exception trong runner

```java
@Override
public void run(ApplicationArguments args) {
    throw new IllegalStateException("Catalog warm-up failed");
}
```

Context có thể đã refresh thành công và `ApplicationStartedEvent` đã được phát. Nhưng startup runner thất bại, nên `ApplicationReadyEvent` không được phát theo luồng thành công.

### 13.3. Lỗi sau khi đã ready

Giả sử `ApplicationReadyEvent` đã được phát, readiness đã chuyển sang accepting, rồi ứng dụng mất kết nối tới một dịch vụ bắt buộc.

Đó là lỗi **runtime**, không còn là lỗi trong chu trình khởi động. Cần xử lý bằng chính sách retry, circuit breaker, monitoring, health/readiness state và cơ chế phục hồi phù hợp. Không thể yêu cầu Spring Boot tự chạy lại `ApplicationRunner` chỉ vì một dependency bên ngoài gặp sự cố.

### 13.4. Bảng tình huống

| Tình huống | Context refresh | Runner | Ready event |
| --- | --- | --- | --- |
| Khởi động bình thường, bean eager hợp lệ | Hoàn tất | Chạy, hoàn tất | Có |
| Bean eager lỗi trong `@PostConstruct` khi refresh | Thất bại | Không đi tới giai đoạn runner | Không |
| Runner ném exception | Đã hoàn tất | Đã gọi nhưng lỗi | Không |
| Async warm-up được gửi vào executor rồi runner trả về | Đã hoàn tất | Có thể hoàn tất sớm | Có thể phát dù warm-up chưa xong |
| Bean lazy chỉ được yêu cầu sau ready | Đã hoàn tất | Không nhất thiết liên quan | Có thể đã phát trước callback của bean lazy |

## 14. Sử dụng đúng cơ chế theo mục đích

### 14.1. Kiểm tra cấu hình riêng của bean

Dùng `@PostConstruct`, `InitializingBean` hoặc init method khi công việc gắn trực tiếp với **khả năng hoạt động của chính bean**.

Ví dụ: kiểm tra một số cấu hình bắt buộc, tạo map nội bộ hoặc chuẩn bị parser.

### 14.2. Thực hiện công việc cấp ứng dụng trước khi ready

Dùng `ApplicationRunner` hoặc `CommandLineRunner` nếu cần điều phối nhiều service hoặc xử lý dữ liệu startup hữu hạn mà ứng dụng phải hoàn tất trước khi công bố ready.

Ví dụ: nạp dữ liệu danh mục cần thiết để API có thể trả kết quả ngay.

### 14.3. Ghi nhận ứng dụng đã hoàn tất startup

Dùng `ApplicationReadyEvent` khi cần quan sát mốc ứng dụng đã hoàn thành runners.

Ví dụ: ghi log thời gian startup, phát metrics hoặc thông báo nội bộ rằng startup đã hoàn tất.

### 14.4. Quyết định nhận hay từ chối traffic

Dùng readiness state/probe khi cần điều phối traffic dựa trên khả năng phục vụ request hiện tại.

Ví dụ: ứng dụng tạm thời từ chối request khi một thành phần bắt buộc đang khôi phục, dù JVM vẫn sống và các bean đã được khởi tạo từ lâu.

### 14.5. Dọn dẹp tài nguyên khi bean hoặc context kết thúc

Đây là chiều ngược lại của startup:

- `@PreDestroy`, `DisposableBean` hoặc custom destroy method: cleanup gắn với bean.
- `SmartLifecycle.stop()`: dừng một thành phần có lifecycle.
- `ContextClosedEvent`: quan sát context đang đóng.
- Readiness `REFUSING_TRAFFIC`: tín hiệu điều phối traffic khi shutdown hoặc gián đoạn runtime.

Không nên dùng `ApplicationReadyEvent` làm nơi quản lý cleanup hoặc dùng `@PreDestroy` làm tín hiệu khởi động.

## 15. Những nhầm lẫn thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`@PostConstruct` chạy khi toàn bộ ứng dụng ready.” | Nó chạy khi bean cụ thể được khởi tạo, có thể sớm hoặc muộn tùy scope/lazy |
| “Bean có `@PostConstruct` tức mọi bean khác đã tồn tại.” | Callback chỉ thuộc lifecycle của bean đang tạo |
| “`SmartInitializingSingleton` tương đương ready.” | Nó chạy sau giai đoạn pre-instantiation singleton non-lazy, trước nhiều mốc startup khác |
| “`ContextRefreshedEvent` nghĩa là runner đã xong.” | Runner thường được gọi sau refresh |
| “`ApplicationStartedEvent` và `ApplicationReadyEvent` giống nhau.” | Started xảy ra trước runners; Ready sau khi runners hoàn tất |
| “Runner chạy async thì Spring Boot chờ task hoàn tất.” | Runner trả về là Spring Boot có thể tiếp tục; background task còn chạy |
| “Ready nghĩa là mọi external API đều khỏe.” | Readiness phản ánh điều kiện/kiểm tra mà ứng dụng thực sự áp dụng |
| “Web server mở cổng là readiness đã accepting.” | Server có thể lắng nghe trước khi readiness được công bố |
| “`@Order` trên bean quyết định thứ tự constructor.” | Nó sắp xếp ở điểm mở rộng có hỗ trợ, chẳng hạn thứ tự runner |
| “Lỗi runner thì context chưa refresh.” | Runner được gọi sau refresh; lỗi có thể xảy ra khi context đã refresh thành công |
| “Readiness refusing có nghĩa tiến trình đã chết.” | Ứng dụng có thể còn sống nhưng chưa sẵn sàng nhận traffic |
| “`ApplicationReadyEvent` tự chờ tất cả thread nền.” | Spring Boot chỉ chờ những công việc đồng bộ thuộc luồng startup mà nó điều phối |

## 16. Bài thực hành

### Bài 1 — In các mốc khởi động

Tạo một Spring Boot project với:

1. Bean có constructor in `"Constructor"`.
2. Method `@PostConstruct` in `"PostConstruct"`.
3. Listener `ContextRefreshedEvent` in `"ContextRefreshed"`.
4. Listener `ApplicationStartedEvent` in `"Started"`.
5. `ApplicationRunner` in `"Runner"`.
6. Listener `ApplicationReadyEvent` in `"Ready"`.

Khởi động và ghi thứ tự log. Phân biệt những dòng gắn với bean lifecycle và những dòng gắn với application lifecycle.

### Bài 2 — Chuyển công việc khỏi `@PostConstruct`

Giả sử một service đang tải dữ liệu lớn từ database trong `@PostConstruct`, gây thời gian khởi tạo bean lâu và khó kiểm soát lỗi.

Chuyển việc tải dữ liệu bắt buộc đó sang một `ApplicationRunner`, giữ trong bean callback chỉ phần kiểm tra trạng thái nội bộ cần thiết.

**Câu hỏi:** thời điểm lỗi tải dữ liệu thay đổi thế nào? Spring Boot có phát `ApplicationReadyEvent` nếu runner thất bại không?

### Bài 3 — So sánh hai runner

Tạo một `ApplicationRunner` với `@Order(10)` và một `CommandLineRunner` với `@Order(20)`.

Khởi động với:

```text
--mode=demo sample.txt
```

Quan sát cách `ApplicationArguments` và `String... args` thể hiện đối số, cũng như thứ tự `run(...)` của hai runner.

### Bài 4 — Tạo lỗi startup

Lần lượt:

- Ném exception trong `@PostConstruct` của một bean eager.
- Ném exception trong `ApplicationRunner`.

Ghi nhận có hay không `ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`. Giải thích nguyên nhân dựa trên thời điểm lỗi.

### Bài 5 — Mô phỏng warm-up bất đồng bộ

Tạo runner gửi tác vụ warm-up vào `Executor` rồi trả về ngay. Trong `ApplicationReadyEvent` listener, in cờ `warmUpCompleted`.

**Câu hỏi:** vì sao cờ có thể vẫn là `false` khi ready event được phát? Bạn sẽ sửa như thế nào nếu dữ liệu warm-up là điều kiện bắt buộc trước khi nhận traffic?

### Bài 6 — Quan sát readiness

Thêm Spring Boot Actuator và bật probes trong môi trường local. Quan sát `/actuator/health/readiness` trong lúc startup và sau khi runner hoàn tất.

Nếu ứng dụng khởi động quá nhanh, tạo một runner thực hiện công việc hữu hạn với thời gian đủ để quan sát. Không sử dụng vòng lặp vô hạn; không dùng sleep như cơ chế nghiệp vụ trong ứng dụng production.

### Bài 7 — Phân biệt lỗi runtime và lỗi startup

Sau khi ứng dụng đã ready, mô phỏng một dependency bắt buộc tạm thời mất kết nối. Thiết kế cách cập nhật readiness hoặc custom health indicator thích hợp, và giải thích vì sao không nên restart mọi replica chỉ vì dependency dùng chung gặp sự cố ngắn hạn.

### Bài 8 — Chọn cơ chế phù hợp

Chọn cơ chế cho từng yêu cầu:

| Yêu cầu | Lựa chọn gợi ý |
| --- | --- |
| Kiểm tra cấu hình thuộc chính một bean khi bean được tạo | `@PostConstruct` hoặc init method |
| Cần quan sát các singleton eager đã được khởi tạo | `SmartInitializingSingleton` |
| Bắt buộc nạp danh mục trước khi ứng dụng ready | Runner đồng bộ, có xử lý lỗi |
| Log thông tin khi runners đã hoàn tất | `ApplicationReadyEvent` |
| Tạm thời rút instance khỏi load balancer | Readiness state/probe phù hợp |
| Cleanup tài nguyên của một bean khi context đóng | `@PreDestroy` hoặc destroy method |

Giải thích vì sao thay một lựa chọn bằng `@Order` hoặc `ContextRefreshedEvent` chưa chắc đáp ứng yêu cầu.

## 17. Ghi nhớ

**Callback khởi tạo bean phục vụ lifecycle của từng bean; runner phục vụ công việc khởi động ở cấp ứng dụng; readiness biểu diễn khả năng nhận traffic.** Ba lớp trách nhiệm có liên quan nhưng không đồng nhất.

Trong luồng startup thông thường, một bean eager được khởi tạo và chạy callback trước khi context refresh hoàn tất. Sau đó Spring Boot phát `ApplicationStartedEvent`, gọi các runner rồi phát `ApplicationReadyEvent`; readiness có thể chuyển sang `ACCEPTING_TRAFFIC` khi startup hoàn thành.

Hãy đặt công việc chuẩn bị nội bộ vào callback bean, đặt tác vụ bắt buộc trước ready vào runner đồng bộ có giới hạn và xử lý lỗi rõ ràng, dùng `ApplicationReadyEvent` để quan sát mốc hoàn tất startup, và dùng readiness probe/state để điều phối traffic trong suốt vòng đời ứng dụng. Chọn đúng cơ chế giúp startup dễ dự đoán, phát hiện lỗi đúng thời điểm và tránh phục vụ request trước khi ứng dụng thực sự có khả năng đáp ứng.
