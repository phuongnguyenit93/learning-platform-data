# Khởi tạo constructor, tiêm dependency và callback vòng đời

Khi Spring tạo một bean, công việc không dừng ở việc gọi constructor. Container phải tìm và tạo các dependency cần thiết, gán chúng vào bean, chạy các callback khởi tạo, áp dụng các bộ xử lý hậu kỳ và cuối cùng quản lý việc hủy bean khi context đóng.

Hiểu đúng trình tự này giúp bạn biết nên đặt logic ở constructor hay `@PostConstruct`, vì sao dependency đã có thể được dùng trong một số callback nhưng chưa nên truy cập ở thời điểm khác, và tại sao bean singleton thường được tạo ngay khi ứng dụng Spring Boot khởi động.

Bài học thuộc chương **Vòng đời bean** của **Spring Boot Fundamentals**. Chúng ta sẽ theo dõi hành trình của một bean từ constructor, dependency injection, callback khởi tạo đến callback hủy; đồng thời phân biệt vòng đời singleton, prototype và bean được tạo qua `@Bean`.

## 1. Một bean đi qua những giai đoạn nào?

Với một bean thông thường do Spring quản lý, có thể hình dung luồng tổng quát:

```text
Bean definition được đăng ký
          │
          ▼
Container chọn cách tạo bean
(constructor hoặc factory method)
          │
          ▼
Giải quyết dependency cần cho việc tạo
          │
          ▼
Instantiate: tạo object
          │
          ▼
Populate properties / field / setter injection
          │
          ▼
Aware callbacks
          │
          ▼
BeanPostProcessor: trước initialization
          │
          ▼
Initialization callbacks
  @PostConstruct
  InitializingBean.afterPropertiesSet()
  custom init method
          │
          ▼
BeanPostProcessor: sau initialization
          │
          ▼
Bean sẵn sàng để sử dụng
          │
          ▼
Context đóng / bean bị hủy theo scope
          │
          ▼
Destruction callbacks
  @PreDestroy
  DisposableBean.destroy()
  custom destroy method
```

Đây là sơ đồ học tập cho một bean do container quản lý. Một số bước có thể khác nhau tùy cách tạo bean, scope, lazy initialization và hạ tầng được cấu hình. Ví dụ, dependency dùng constructor được resolve **trước khi constructor của bean hiện tại chạy**; field và setter injection diễn ra sau khi object đã được instantiate.

Các giai đoạn cần phân biệt:

- **Instantiation:** tạo object Java.
- **Dependency injection / property population:** cung cấp dependency và giá trị cấu hình.
- **Initialization:** chạy callback để bean hoàn tất chuẩn bị.
- **Post-processing:** cho phép Spring và framework tích hợp xử lý hoặc bọc bean, chẳng hạn tạo proxy.
- **Destruction:** gọi callback dọn dẹp khi container quản lý việc kết thúc vòng đời bean.

Không phải mọi object được tạo bằng `new` đều đi qua quy trình này. Một object chỉ nhận đầy đủ vòng đời Spring khi được đăng ký và quản lý như bean trong container.

## 2. Bean definition và bean instance

Trước khi tạo object, Spring cần biết **định nghĩa bean**. Bean definition mô tả cách tạo và quản lý một bean, chẳng hạn:

- Bean class hoặc factory method.
- Tên bean và alias.
- Constructor arguments hoặc property values.
- Scope như singleton hoặc prototype.
- Dependency cần thiết.
- Init method và destroy method.
- Các điều kiện cấu hình có liên quan.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class ClockConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Phương thức `applicationClock()` cung cấp định nghĩa bean. Khi container tạo bean theo định nghĩa này, nó gọi factory method và quản lý object trả về.

Phân biệt:

```text
Bean definition
  "Tạo một bean kiểu Clock bằng applicationClock()"
                 │
                 ▼
Bean instance
  Một object Clock cụ thể do factory method trả về
```

Bean definition không phải object; nó là metadata để container tạo và quản lý object.

## 3. Instantiation: constructor được gọi khi nào?

Instantiation là bước tạo object Java. Với bean được khai báo bằng class, Spring chọn constructor phù hợp, resolve các tham số cần thiết rồi gọi constructor để tạo instance.

Ví dụ:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String greetingPrefix;

    public GreetingService() {
        this.greetingPrefix = "Xin chào";
    }

    public String greet(String name) {
        return greetingPrefix + ", " + name + "!";
    }
}
```

Khi Spring tạo bean `GreetingService`, nó gọi constructor. Sau đó bean được xử lý qua những giai đoạn tiếp theo của lifecycle.

### 3.1. Constructor có dependency

Thông thường, bean cần một dependency khác:

```java
package com.example.demo.service;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final MessageFormatter formatter;

    public GreetingService(MessageFormatter formatter) {
        this.formatter = formatter;
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

```java
package com.example.demo.service;

import org.springframework.stereotype.Component;

@Component
public class MessageFormatter {

    public String format(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Trước khi gọi constructor `GreetingService(MessageFormatter)`, Spring phải tìm một bean phù hợp kiểu `MessageFormatter`. Nếu bean đó chưa có instance và cần được tạo, container sẽ tạo dependency trước theo graph phụ thuộc.

```text
Tạo GreetingService
       │
       ▼
Cần MessageFormatter
       │
       ▼
Tạo MessageFormatter
       │
       ▼
Hoàn tất MessageFormatter
       │
       ▼
Gọi constructor GreetingService(formatter)
       │
       ▼
Hoàn tất GreetingService
```

Nhờ vậy, khi constructor `GreetingService` chạy, tham số `formatter` đã được cung cấp. Bạn không cần gọi `new MessageFormatter()` bên trong service.

### 3.2. Khi class chỉ có một constructor

Với một class Spring bean chỉ có **một constructor**, Spring có thể sử dụng constructor đó để inject dependency mà không cần ghi `@Autowired`.

```java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Cách này phổ biến vì:

- Dependency được thể hiện ngay trên constructor.
- Có thể khai báo field `final`.
- Object không cần tồn tại trong trạng thái thiếu dependency bắt buộc.
- Dễ viết unit test bằng cách truyền fake/mock dependency trực tiếp.
- Không cần field injection hoặc setter injection.

Nếu có nhiều constructor, bạn cần chỉ rõ constructor phù hợp bằng `@Autowired` hoặc cấu hình tương ứng. Không nên để nhiều constructor rồi kỳ vọng Spring tự đoán constructor theo ý muốn.

### 3.3. Dependency phải có sẵn trước khi constructor bean hiện tại chạy

Ví dụ:

```java
@Service
public class ReportService {

    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
        System.out.println("ReportService constructor");
    }
}
```

Nếu bean `Clock` chưa tồn tại, Spring phải tìm hoặc tạo bean phù hợp trước. Nếu không tìm thấy, container không thể gọi constructor với tham số hợp lệ và quá trình tạo `ReportService` thất bại.

Lỗi này thường được bọc trong `UnsatisfiedDependencyException` hoặc `BeanCreationException`. Cần đọc nguyên nhân sâu hơn để biết thiếu bean, có nhiều bean phù hợp hay dependency tự tạo thất bại.

## 4. Constructor injection, setter injection và field injection

Spring hỗ trợ nhiều cách cung cấp dependency. Chúng khác nhau ở thời điểm object được tạo và khả năng biểu đạt trạng thái hợp lệ của object.

### 4.1. Constructor injection

```java
@Service
public class InvoiceService {

    private final TaxCalculator taxCalculator;

    public InvoiceService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
    }
}
```

Dependency được resolve trước khi constructor chạy và truyền vào constructor. Bean không thể được tạo thành công nếu dependency bắt buộc không được cung cấp.

Đây thường là lựa chọn ưu tiên cho dependency bắt buộc.

### 4.2. Setter injection

```java
@Component
public class ReportExporter {

    private StorageClient storageClient;

    @Autowired
    public void setStorageClient(StorageClient storageClient) {
        this.storageClient = storageClient;
    }

    public void export(byte[] content) {
        storageClient.store(content);
    }
}
```

Setter injection cần object được instantiate trước, sau đó Spring gọi setter để gán dependency. Nó phù hợp hơn với dependency tùy chọn hoặc có thể thay đổi, nhưng cần tránh để bean được sử dụng khi setter chưa được gọi.

### 4.3. Field injection

```java
@Component
public class NotificationService {

    @Autowired
    private EmailSender emailSender;
}
```

Spring tạo object rồi inject vào field qua reflection trong bước populate properties. Cách này ngắn nhưng dependency bị ẩn khỏi constructor, field khó giữ bất biến và unit test thường phải dùng reflection hoặc khởi tạo Spring context.

Với ứng dụng mới, constructor injection thường rõ ràng hơn.

### 4.4. So sánh thời điểm

| Cách injection | Object được tạo khi nào? | Dependency được cung cấp khi nào? | Ghi chú |
|---|---|---|---|
| Constructor | Sau khi resolve các tham số constructor | Ngay trong constructor | Tốt cho dependency bắt buộc |
| Setter | Trước khi setter được gọi | Sau instantiation | Hữu ích cho dependency tùy chọn |
| Field | Trước khi field được inject | Sau instantiation, qua reflection | Dependency khó nhìn thấy từ API class |

Spring còn hỗ trợ method injection và một số cơ chế khác. Dù sử dụng cách nào, dependency phải được container resolve theo bean definitions và các quy tắc autowiring.

## 5. Field/property population diễn ra sau instantiation

Với setter hoặc field injection, trình tự cơ bản:

```text
Gọi constructor
      │
      ▼
Object được tạo
      │
      ▼
Spring xử lý dependency injection
      │
      ├── inject field
      ├── gọi setter
      └── áp dụng property values
      │
      ▼
Tiếp tục callback và initialization
```

Ví dụ:

```java
@Component
public class AuditService {

    private Clock clock;

    @Autowired
    public void setClock(Clock clock) {
        this.clock = clock;
    }

    @PostConstruct
    public void initialize() {
        System.out.println("Clock đã được inject: " + clock);
    }
}
```

Khi `@PostConstruct` được gọi trong quy trình initialization thông thường, setter injection đã được thực hiện. Vì vậy callback có thể sử dụng `clock`.

Tuy nhiên, không nên dùng constructor để truy cập một field được inject bằng `@Autowired` sau instantiation: tại thời điểm constructor chạy, field đó chưa được Spring gán.

```java
@Component
public class IncorrectService {

    @Autowired
    private Clock clock;

    public IncorrectService() {
        // clock chưa được field injection tại thời điểm này.
        // clock.instant(); // NullPointerException
    }
}
```

Đây là một lý do nữa để dùng constructor injection: các dependency bắt buộc có mặt ngay khi object được tạo.

## 6. Aware callbacks: bean nhận thông tin từ container

Sau khi object được instantiate và dependency/property được cung cấp, Spring có thể gọi các callback thuộc nhóm `Aware` để bean nhận thông tin về môi trường quản lý.

Ví dụ:

- `BeanNameAware`: nhận tên bean trong container.
- `BeanClassLoaderAware`: nhận class loader được dùng để tải bean.
- `BeanFactoryAware`: nhận BeanFactory đang quản lý bean.
- `ApplicationContextAware`: nhận ApplicationContext nếu hạ tầng context hỗ trợ callback này.

Ví dụ:

```java
@Component
public class ContainerInfo implements BeanNameAware, BeanFactoryAware {

    private String beanName;
    private BeanFactory beanFactory;

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
    }

    @Override
    public void setBeanFactory(BeanFactory beanFactory) {
        this.beanFactory = beanFactory;
    }

    @PostConstruct
    public void showInfo() {
        System.out.println("Bean name: " + beanName);
        System.out.println("BeanFactory: " + beanFactory.getClass().getName());
    }
}
```

Ví dụ cần import:

```java
import org.springframework.beans.factory.BeanFactory;
import org.springframework.beans.factory.BeanFactoryAware;
import org.springframework.beans.factory.BeanNameAware;
```

`Aware` callbacks là một phần của lifecycle. Chúng hữu ích cho infrastructure component hoặc tích hợp framework, nhưng business service thường không cần implement `ApplicationContextAware` để tự tìm dependency. Hãy ưu tiên constructor injection cho dependency nghiệp vụ.

Một số callback như `ApplicationContextAware` được xử lý bởi BeanPostProcessor của Spring context; vì vậy không nên coi mọi `Aware` interface đều được gọi trong cùng một method hoặc cùng một implementation nội bộ.

## 7. BeanPostProcessor: Spring can thiệp trước và sau initialization

`BeanPostProcessor` là một extension point quan trọng của Spring. Nó cho phép xử lý bean instance trước và sau các initialization callbacks.

Interface rút gọn:

```java
public interface BeanPostProcessor {

    Object postProcessBeforeInitialization(
            Object bean,
            String beanName
    );

    Object postProcessAfterInitialization(
            Object bean,
            String beanName
    );
}
```

Hai phương thức có thể trả về bean gốc hoặc một object wrapper/proxy. Spring và các thư viện tích hợp sử dụng cơ chế này cho nhiều chức năng.

Ví dụ về vai trò:

- Xử lý annotation lifecycle như `@PostConstruct`.
- Tạo proxy phục vụ AOP.
- Hỗ trợ một số annotation injection.
- Tích hợp các cơ chế xử lý bean đặc thù.

Bạn không cần tự viết `BeanPostProcessor` cho các service thông thường. Nhưng hiểu nó giúp giải thích vì sao object mà code nhận được sau startup có thể là proxy thay vì instance ban đầu.

### 7.1. Proxy có thể được tạo sau initialization

Ví dụ một service có `@Transactional` hoặc `@Async` có thể được Spring bọc bằng proxy thông qua infrastructure post-processing phù hợp.

```text
Object target được instantiate
          │
          ▼
Dependency injection
          │
          ▼
Initialization callbacks
          │
          ▼
BeanPostProcessor sau initialization
          │
          ▼
Proxy được trả về cho container/client
          │
          ▼
Lời gọi đi qua proxy để áp dụng advice
```

Đây là mô hình khái quát; proxy có thể được tạo ở những điểm khác nhau tùy cơ chế cụ thể. Điều quan trọng là bean được inject vào consumer có thể là proxy do Spring quản lý, không nhất thiết là object target thô.

## 8. Initialization callbacks: bean hoàn tất chuẩn bị

Sau khi dependency đã được inject và các bước post-processing trước initialization được thực hiện, Spring gọi các callback khởi tạo.

Có ba cách phổ biến:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method khai báo qua `@Bean(initMethod = "...")` hoặc XML.

Trong quy trình chuẩn, thứ tự là:

```text
Bean instance đã được tạo
          │
          ▼
Dependency đã được cung cấp
          │
          ▼
Aware callbacks
          │
          ▼
BeanPostProcessor.beforeInitialization
          │
          ▼
@PostConstruct
          │
          ▼
InitializingBean.afterPropertiesSet()
          │
          ▼
Custom init method
          │
          ▼
BeanPostProcessor.afterInitialization
          │
          ▼
Bean sẵn sàng
```

`@PostConstruct` được gọi thông qua hạ tầng post-processing tương ứng của Spring, nên nó nằm trong giai đoạn trước initialization callback của `InitializingBean`.

### 8.1. `@PostConstruct`

Ví dụ:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    @PostConstruct
    public void initialize() {
        System.out.println("CacheService đã được khởi tạo");
    }
}
```

`@PostConstruct` đánh dấu một method cần chạy sau khi dependency injection hoàn tất và trước khi bean được xem là đã khởi tạo xong.

Đặc điểm thường gặp:

- Method không nhận tham số.
- Return type là `void`.
- Không phải constructor.
- Không phải nơi để inject dependency.
- Có thể sử dụng các dependency đã được inject.
- Với Spring Boot 3, package annotation là `jakarta.annotation.PostConstruct`.

`@PostConstruct` phù hợp với thao tác chuẩn bị nhẹ, ví dụ kiểm tra trạng thái nội bộ, tạo dữ liệu cache cục bộ nhỏ hoặc chuẩn hóa cấu trúc dữ liệu sau khi cấu hình đã được inject.

Tránh thực hiện công việc dài, khó kiểm soát hoặc phụ thuộc hệ thống bên ngoài trong callback này nếu nó làm startup trở nên mong manh. Với tác vụ cần chạy theo sự kiện ứng dụng đã sẵn sàng, hãy cân nhắc `ApplicationRunner`, `CommandLineRunner` hoặc application event phù hợp.

### 8.2. `InitializingBean.afterPropertiesSet()`

Spring cung cấp interface:

```java
import org.springframework.beans.factory.InitializingBean;

public class SearchIndexService implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        System.out.println("SearchIndexService đã nhận đủ properties");
    }
}
```

Spring gọi `afterPropertiesSet()` sau khi dependency/property injection hoàn tất. Nó có mục đích gần với `@PostConstruct`, nhưng yêu cầu class triển khai một interface của Spring.

Cách này hữu ích trong một số thư viện hoặc class vốn được thiết kế để tích hợp chặt với Spring. Với business class mới, `@PostConstruct` thường ít ràng buộc framework hơn.

### 8.3. Custom init method với `@Bean`

Bạn có thể khai báo method khởi tạo riêng:

```java
public class LegacyClient {

    public void connect() {
        System.out.println("Đã chuẩn bị LegacyClient");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(initMethod = "connect")
    public LegacyClient legacyClient() {
        return new LegacyClient();
    }
}
```

Sau khi Spring tạo bean và inject các dependency liên quan, nó gọi method `connect()` như custom initialization callback.

Custom init method hữu ích khi class đến từ thư viện bên ngoài và bạn không thể thêm `@PostConstruct` hoặc implement `InitializingBean` vào class đó.

Method được chỉ định làm init method phải tồn tại và có signature phù hợp; nếu không, bean creation có thể thất bại.

### 8.4. Có nên dùng cả ba callback trong một class?

Về kỹ thuật, một bean có thể tham gia nhiều loại callback. Thứ tự callback quan trọng khi chúng cùng tồn tại:

| Callback | Vị trí trong chuỗi initialization |
|---|---|
| `@PostConstruct` | Trước `afterPropertiesSet()` |
| `InitializingBean.afterPropertiesSet()` | Sau `@PostConstruct` |
| Custom init method | Sau `afterPropertiesSet()` |

Không nên chia cùng một thao tác khởi tạo thành ba nơi chỉ để tận dụng tất cả callback. Hãy chọn một cơ chế phù hợp để người đọc biết rõ nơi bean hoàn tất chuẩn bị.

Nếu cần hiểu thứ tự trong một ví dụ, có thể ghi log trong từng callback:

```java
@Component
public class LifecycleProbe implements InitializingBean {

    @PostConstruct
    public void postConstruct() {
        System.out.println("1 - @PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("2 - afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("3 - custom init method");
    }
}
```

Khai báo `customInit` qua `@Bean(initMethod = "customInit")` nếu bean được tạo từ factory method. Output minh họa theo thứ tự là `1`, `2`, `3`.

## 9. Constructor không phải callback khởi tạo

Constructor và `@PostConstruct` có thời điểm, mục tiêu khác nhau.

| Constructor | `@PostConstruct` |
|---|---|
| Tạo object Java | Hoàn tất bước chuẩn bị sau injection |
| Tham số constructor có thể nhận dependency | Có thể dùng dependency đã được inject |
| Chạy trước field/setter injection | Chạy sau injection |
| Dùng để thiết lập trạng thái bắt buộc ban đầu | Dùng để thực hiện initialization phụ thuộc vào bean đã được lắp ráp |
| Không phải callback do Spring định nghĩa | Là lifecycle annotation được Spring xử lý |

Ví dụ:

```java
@Service
public class PricingService {

    private final TaxCalculator taxCalculator;
    private Map<String, BigDecimal> rates;

    public PricingService(TaxCalculator taxCalculator) {
        this.taxCalculator = taxCalculator;
        // Dependency constructor đã có tại đây.
    }

    @PostConstruct
    public void loadRates() {
        // Có thể dùng taxCalculator và cấu hình đã inject.
        this.rates = Map.of(
                "STANDARD", new BigDecimal("0.10"),
                "REDUCED", new BigDecimal("0.05")
        );
    }
}
```

Constructor phù hợp với việc bảo đảm object có dependency bắt buộc. `@PostConstruct` phù hợp với bước cần thực hiện sau khi object đã được container lắp ráp.

Tuy nhiên, không nên coi `@PostConstruct` là nơi thay thế hoàn toàn constructor. Trạng thái cốt lõi mà object cần để tồn tại hợp lệ vẫn nên được biểu diễn qua constructor khi có thể.

## 10. Bean được tạo bằng `@Bean` cũng có lifecycle

Không chỉ các class có `@Component` mới có lifecycle. Object trả về từ `@Bean` cũng được container quản lý.

Ví dụ:

```java
public class ReportClient {

    private final String endpoint;

    public ReportClient(String endpoint) {
        this.endpoint = endpoint;
    }

    public void initialize() {
        System.out.println("Connecting to " + endpoint);
    }

    public void close() {
        System.out.println("Closing client");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ReportClientConfiguration {

    @Bean(initMethod = "initialize", destroyMethod = "close")
    public ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
```

Spring quản lý instance do factory method trả về và gọi các callback đã khai báo theo lifecycle. Bean không cần mang `@Component` để được container quản lý.

Nếu factory method có tham số:

```java
@Bean
public ReportClient reportClient(AppProperties properties) {
    return new ReportClient(properties.reportEndpoint());
}
```

Spring resolve `AppProperties` trước khi gọi method `reportClient(...)`. Đây là factory-method dependency injection, có cùng nguyên tắc resolve dependency như constructor injection.

## 11. Destruction callbacks: khi nào bean được hủy?

Khi ApplicationContext đóng bình thường, Spring có thể gọi các callback hủy cho những bean mà container quản lý vòng đời.

Ba cơ chế phổ biến:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method, ví dụ `@Bean(destroyMethod = "close")`.

Trình tự tiêu biểu:

```text
ApplicationContext bắt đầu đóng
          │
          ▼
Singleton bean cần hủy
          │
          ▼
@PreDestroy
          │
          ▼
DisposableBean.destroy()
          │
          ▼
Custom destroy method
          │
          ▼
Hoàn tất destruction callback
```

### 11.1. `@PreDestroy`

```java
package com.example.demo.service;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class CacheService {

    @PreDestroy
    public void cleanup() {
        System.out.println("CacheService đang dọn dẹp");
    }
}
```

Spring gọi callback này trong quá trình hủy bean được quản lý khi context đóng bình thường.

Các công việc phù hợp có thể gồm:

- Đóng tài nguyên nội bộ.
- Dừng executor do bean tạo và sở hữu.
- Flush dữ liệu buffer cần thiết.
- Giải phóng handle hoặc client mà bean trực tiếp quản lý.

Không nên dựa vào `@PreDestroy` như một cơ chế bảo đảm chạy trong mọi kiểu kết thúc process. Nếu máy bị tắt đột ngột, process bị kill cưỡng bức hoặc JVM crash, callback có thể không có cơ hội chạy.

### 11.2. `DisposableBean.destroy()`

```java
import org.springframework.beans.factory.DisposableBean;

public class LegacyResource implements DisposableBean {

    @Override
    public void destroy() {
        System.out.println("LegacyResource đã đóng");
    }
}
```

Đây là interface callback của Spring. Nó phù hợp với một số class tích hợp framework, nhưng tạo sự phụ thuộc trực tiếp vào Spring API.

### 11.3. Custom destroy method

Ví dụ:

```java
public class ExternalClient {

    public void close() {
        System.out.println("ExternalClient closed");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ExternalClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
```

Khi context đóng và bean được hủy theo lifecycle, Spring gọi `close()`.

Với `@Bean`, Spring có thể suy luận một số destroy method phổ biến như `close` hoặc `shutdown` trong những trường hợp phù hợp. Khai báo tường minh giúp người đọc thấy rõ ý định và tránh phụ thuộc vào suy luận khi class có nhiều phương thức dọn dẹp.

## 12. Thứ tự destruction callbacks

Nếu một bean sử dụng cả ba cách:

```java
@Component
public class ResourceManager implements DisposableBean {

    @PreDestroy
    public void preDestroy() {
        System.out.println("1 - @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2 - DisposableBean.destroy");
    }

    public void closeResource() {
        System.out.println("3 - custom destroy method");
    }
}
```

Nếu custom method được cấu hình phù hợp, thứ tự tiêu biểu là:

```text
@PreDestroy
    ↓
DisposableBean.destroy()
    ↓
custom destroy method
```

Không nên lặp lại cùng một thao tác đóng tài nguyên ở cả ba callback. Nếu `@PreDestroy` đã đóng client, custom destroy method không nên đóng lại một tài nguyên không còn ở trạng thái hợp lệ.

## 13. ApplicationContext đóng như thế nào?

Với context có khả năng đóng, có thể sử dụng `try-with-resources`:

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class ContextLifecycleExample {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            GreetingService service =
                    context.getBean(GreetingService.class);

            System.out.println(service.greet("Lan"));
        }

        // Context đã được đóng sau khi thoát try block.
    }
}
```

`AnnotationConfigApplicationContext` là context có thể đóng. Khi thoát `try`, `close()` được gọi và destruction callbacks của singleton được quản lý có thể chạy.

Với Spring Boot web application, không đóng context ngay sau `SpringApplication.run(...)`, vì web server và các bean ứng dụng cần tiếp tục hoạt động.

Spring Boot thường tích hợp shutdown hook để đóng ApplicationContext khi JVM kết thúc theo quy trình bình thường. Trong môi trường service/container, hệ thống vận hành cần cho process đủ thời gian shutdown để các callback dọn dẹp hoàn tất.

### 13.1. Đóng context khác với hủy một bean thủ công

Không nên lấy bean từ context rồi tự gọi `destroy()` hoặc `close()` tùy tiện nếu container vẫn đang quản lý bean đó. Điều này có thể khiến bean tiếp tục được inject vào nơi khác dù tài nguyên bên trong đã bị đóng.

Hãy để container quản lý destruction, hoặc thiết kế một API nghiệp vụ riêng nếu cần kết thúc một phiên/operation mà không kết thúc bean singleton.

## 14. Scope ảnh hưởng đến lifecycle như thế nào?

### 14.1. Singleton

`singleton` là scope mặc định. Trong một IoC container, mỗi bean definition singleton thường tương ứng với một instance dùng chung.

Với ApplicationContext thông thường, singleton không lazy thường được tạo trong quá trình refresh context. Khi context đóng bình thường, Spring gọi destruction callbacks cho singleton mà nó quản lý.

```java
@Component
public class ApplicationCache {

    public ApplicationCache() {
        System.out.println("ApplicationCache constructor");
    }

    @PreDestroy
    public void close() {
        System.out.println("ApplicationCache destroyed");
    }
}
```

Đây là loại bean thường thấy trong ứng dụng Spring Boot.

Lưu ý: singleton của Spring là singleton **theo bean definition trong một container**, không phải duy nhất trên toàn JVM. Hai ApplicationContext độc lập có thể có hai instance cùng bean name.

### 14.2. Prototype

`@Scope("prototype")` yêu cầu container tạo instance mới mỗi lần bean được yêu cầu theo cơ chế lookup tương ứng:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryReport {
}
```

Spring thực hiện việc tạo và initialization callbacks cho prototype, sau đó giao object cho client. **Spring không tự động quản lý đầy đủ destruction callbacks của prototype** sau khi giao object ra ngoài, vì container không theo dõi vòng đời sử dụng của từng instance prototype.

Nếu prototype giữ tài nguyên cần đóng, client nhận object phải chịu trách nhiệm dọn dẹp hoặc dùng một factory/lifecycle mechanism phù hợp.

Đây là khác biệt quan trọng so với singleton.

### 14.3. Request và session scope

Ứng dụng web có thể dùng scope theo request hoặc session nếu context và web infrastructure tương ứng đã được cấu hình.

- `request`: instance gắn với một HTTP request.
- `session`: instance gắn với HTTP session.
- Các web scope khác tùy môi trường.

Những bean này có lifecycle phụ thuộc vào request/session, không giống singleton tồn tại suốt thời gian context.

Nếu inject request-scoped bean vào singleton, Spring thường cần proxy hoặc một cơ chế provider phù hợp để truy cập đúng instance theo request hiện tại.

### 14.4. Bảng so sánh scope và destruction

| Scope | Quy tắc instance | Initialization | Destruction |
|---|---|---|---|
| singleton | Một instance cho mỗi bean definition trong container | Khi container tạo bean, thường eager trong context refresh nếu không lazy | Container gọi callback khi context đóng bình thường |
| prototype | Instance mới mỗi lần được container yêu cầu | Mỗi instance đều được khởi tạo theo lifecycle tương ứng | Container không tự gọi destruction callbacks sau khi giao instance |
| request | Instance theo HTTP request | Khi request scope cần bean | Theo vòng đời request và web context |
| session | Instance theo HTTP session | Khi session scope cần bean | Theo vòng đời session và web context |

Các web scope cần môi trường web phù hợp; không áp dụng chúng trong một BeanFactory thuần không có web scope infrastructure.

## 15. Lazy initialization và thời điểm constructor chạy

Bean singleton thường được tạo sớm trong quá trình ApplicationContext refresh nếu không được đánh dấu lazy. Với `@Lazy`, việc tạo có thể được trì hoãn cho đến khi bean được yêu cầu.

Ví dụ:

```java
@Component
@Lazy
public class ExpensiveSearchIndex {

    public ExpensiveSearchIndex() {
        System.out.println("Search index initialized");
    }
}
```

Nếu không có eager bean nào yêu cầu `ExpensiveSearchIndex` trong quá trình startup, constructor có thể chưa chạy khi context refresh hoàn tất. Lần đầu bean được inject/lookup theo cách kích hoạt việc tạo, container mới tạo instance.

Nhưng `@Lazy` không bảo đảm constructor luôn chạy muộn:

- Một singleton eager khác có dependency trực tiếp vào bean lazy có thể yêu cầu nó trong startup.
- Một lời gọi `getBean()` trong startup callback có thể kích hoạt việc tạo bean.
- Lazy initialization có thể được cấu hình ở cấp ứng dụng, ảnh hưởng nhiều bean.

Vì vậy, **thời điểm constructor chạy phụ thuộc cả scope, lazy flag và dependency graph**.

## 16. Circular dependency và constructor injection

Một circular dependency xảy ra khi hai bean phụ thuộc lẫn nhau:

```text
ServiceA cần ServiceB
      ▲       │
      │       ▼
      └──── ServiceB cần ServiceA
```

Ví dụ constructor cycle:

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

Để tạo `ServiceA`, Spring cần `ServiceB`. Để tạo `ServiceB`, Spring lại cần `ServiceA`, trong khi constructor của `ServiceA` chưa hoàn tất. Container không thể tạo hai object theo chuỗi constructor này và thường báo `BeanCurrentlyInCreationException` hoặc một lỗi circular reference được bọc trong `UnsatisfiedDependencyException`.

Constructor injection làm dependency graph rõ ràng, nhờ vậy vòng phụ thuộc thường được phát hiện sớm.

### 16.1. Có nên đổi sang field/setter injection để né circular dependency?

Một số dạng circular dependency qua setter/field có thể được xử lý nhờ cơ chế early singleton reference trong một số cấu hình Spring. Nhưng Spring Boot hiện đại mặc định không cho phép circular references trong nhiều cấu hình ứng dụng, và việc đổi sang setter injection chỉ để né vòng phụ thuộc thường che giấu vấn đề thiết kế.

Cách tốt hơn là phân tích trách nhiệm:

- Có thể tách logic dùng chung vào một service thứ ba.
- Có thể đổi một chiều phụ thuộc thành event hoặc callback phù hợp.
- Có thể truyền dữ liệu cần thiết thay vì để hai service gọi lẫn nhau.
- Nếu một dependency thực sự chỉ cần tại một thời điểm muộn, có thể dùng `ObjectProvider<T>` hoặc cơ chế lazy có chủ đích, nhưng cần hiểu lifecycle và semantics của nó.

Không dùng `@Lazy` như cách chữa mặc định cho mọi circular dependency. Hãy thiết kế dependency graph có hướng rõ ràng.

## 17. Những callback và sự kiện sau khi bean đã được khởi tạo

Không phải mọi thao tác sau khi context startup đều thuộc lifecycle callback của một bean riêng lẻ.

### 17.1. `SmartInitializingSingleton`

Interface này cung cấp callback `afterSingletonsInstantiated()` sau khi các singleton eager thông thường đã được tạo xong.

```java
@Component
public class StartupSummary implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println("Các singleton eager đã được khởi tạo");
    }
}
```

Nó phù hợp với infrastructure bean cần quan sát trạng thái sau khi các singleton eager được tạo. Đây không phải callback thay thế `@PostConstruct` cho mỗi bean.

### 17.2. `ApplicationRunner` và `CommandLineRunner`

Spring Boot cung cấp hai interface để chạy logic sau khi ApplicationContext đã refresh và trước khi ứng dụng phát tín hiệu sẵn sàng hoàn toàn.

```java
@Component
public class StartupTasks implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Ứng dụng đã hoàn tất bước refresh context");
    }
}
```

`CommandLineRunner` có phương thức `run(String... args)`; `ApplicationRunner` nhận `ApplicationArguments`.

Các runner phù hợp với công việc ở cấp ứng dụng sau khi context đã khởi tạo, ví dụ nạp dữ liệu mẫu có kiểm soát hoặc kiểm tra trạng thái khởi động. Chúng không phải callback initialization của từng bean.

### 17.3. Application events

ApplicationContext phát các event trong quá trình lifecycle, chẳng hạn `ContextRefreshedEvent` khi context đã refresh và `ContextClosedEvent` khi context đóng.

Có thể lắng nghe:

```java
@Component
public class ContextEventLogger {

    @EventListener
    public void onClosed(ContextClosedEvent event) {
        System.out.println("ApplicationContext is closing");
    }
}
```

Sự kiện context là tín hiệu ở cấp container. Không nên thay `@PreDestroy` của bean bằng một listener context event nếu mục tiêu là dọn dẹp một tài nguyên thuộc sở hữu của bean đó. Dùng callback phù hợp với phạm vi lifecycle.

## 18. Callback lifecycle trong Spring Boot 3

Với Spring Boot 3, hệ sinh thái đã chuyển sang Jakarta namespace. Vì vậy, các annotation lifecycle phổ biến được import từ:

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
```

Không dùng nhầm package cũ `javax.annotation.PostConstruct` hoặc `javax.annotation.PreDestroy` trong ứng dụng Boot 3 nếu dependency hiện tại không cung cấp chúng.

Ví dụ đầy đủ:

```java
package com.example.demo.service;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;

@Service
public class ConnectionManager {

    private boolean initialized;

    public ConnectionManager() {
        System.out.println("1 - Constructor");
    }

    @PostConstruct
    public void initialize() {
        initialized = true;
        System.out.println("2 - PostConstruct");
    }

    public void execute() {
        if (!initialized) {
            throw new IllegalStateException("Bean chưa sẵn sàng");
        }
        System.out.println("Đang thực hiện công việc");
    }

    @PreDestroy
    public void cleanup() {
        System.out.println("3 - PreDestroy");
        initialized = false;
    }
}
```

Để biên dịch, project cần có Jakarta annotation API trên compile classpath. Các starter và dependency của Spring Boot có thể cung cấp API này tùy cấu hình; nếu compiler báo không tìm thấy package `jakarta.annotation`, hãy kiểm tra dependency đã được resolve chưa.

## 19. Lỗi thường gặp trong constructor, injection và callback

| Triệu chứng | Giai đoạn thường liên quan | Nguyên nhân cần kiểm tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Resolve dependency | Không có bean phù hợp type/name/qualifier |
| `NoUniqueBeanDefinitionException` | Resolve dependency | Nhiều bean cùng phù hợp nhưng chưa chọn được một |
| `UnsatisfiedDependencyException` | Tạo bean/inject | Dependency của constructor, field, setter hoặc factory method không được resolve |
| `BeanCurrentlyInCreationException` | Instantiation/dependency graph | Circular dependency hoặc truy cập bean khi đang tạo |
| `BeanCreationException` | Nhiều giai đoạn tạo bean | Constructor, factory method, injection hoặc init callback thất bại |
| `NullPointerException` trong constructor khi dùng field `@Autowired` | Instantiation | Field injection chưa diễn ra |
| `NoSuchMethodException` hoặc lỗi init method | Initialization | Tên custom init method không tồn tại hoặc signature không phù hợp |
| Exception trong `@PostConstruct` | Initialization | Logic callback thất bại; bean không hoàn tất tạo |
| Tài nguyên không đóng khi shutdown | Destruction | Context không được đóng bình thường, callback không được đăng ký hoặc bean scope không được container quản lý destruction |
| Prototype không gọi `@PreDestroy` tự động | Destruction | Container không theo dõi vòng đời prototype sau khi giao instance |

### 19.1. Đọc chuỗi `Caused by`

Một lỗi dependency có thể được bọc nhiều lớp:

```text
BeanCreationException:
  Error creating bean with name 'checkoutService'

Caused by: UnsatisfiedDependencyException:
  Error creating bean with name 'checkoutService'

Caused by: NoUniqueBeanDefinitionException:
  No qualifying bean of type 'PaymentGateway'
  available: expected single matching bean but found 2
```

Dòng đầu cho biết bean nào thất bại. Nguyên nhân sâu nhất cho biết Spring không chọn được một `PaymentGateway`. Hướng xử lý phải tập trung vào candidate/qualifier/primary thay vì sửa callback `@PostConstruct`.

### 19.2. Constructor ném exception

Nếu constructor ném exception:

```java
@Component
public class FileIndex {

    public FileIndex() {
        throw new IllegalStateException("Không thể tạo index");
    }
}
```

bean không được tạo thành công; các bean phụ thuộc vào nó cũng có thể thất bại. Nếu logic khởi tạo cần dependency đã inject, không thể đặt nó vào constructor mà lại trông chờ field/setter injection đã hoàn tất.

Hãy cân nhắc `@PostConstruct`, init method hoặc một runner/event cấp ứng dụng tùy mục tiêu, và xử lý lỗi có chủ đích.

### 19.3. Exception trong `@PostConstruct`

Nếu callback khởi tạo thất bại, Spring coi bean không hoàn tất initialization. Quá trình refresh context có thể dừng và ứng dụng không startup thành công.

Vì vậy, callback này nên có phạm vi rõ ràng, xử lý lỗi hợp lý và không thực hiện tác vụ dài không cần thiết. Đối với tác vụ có thể retry hoặc phụ thuộc dịch vụ ngoài, nên thiết kế một quy trình vận hành riêng thay vì buộc mọi lần startup phải hoàn thành ngay tác vụ đó.

## 20. Ví dụ hoàn chỉnh theo dõi thứ tự lifecycle

Ta tạo một bean minh họa với constructor, setter injection, callback initialization và destruction. Ví dụ dùng setter để dễ quan sát thời điểm injection; trong business code thật, constructor injection thường được ưu tiên cho dependency bắt buộc.

```java
package com.example.demo.lifecycle;

import org.springframework.stereotype.Component;

@Component
public class LifecycleDependency {

    public LifecycleDependency() {
        System.out.println("A - Dependency constructor");
    }

    public void use() {
        System.out.println("Dependency is ready");
    }
}
```

```java
package com.example.demo.lifecycle;

import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

@Component
public class LifecycleProbe implements InitializingBean {

    private LifecycleDependency dependency;

    public LifecycleProbe() {
        System.out.println("B - Probe constructor");
    }

    @Autowired
    public void setDependency(LifecycleDependency dependency) {
        this.dependency = dependency;
        System.out.println("C - Setter injection");
    }

    @PostConstruct
    public void postConstruct() {
        System.out.println("D - @PostConstruct");
        dependency.use();
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("E - afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("F - Custom init");
    }

    @PreDestroy
    public void preDestroy() {
        System.out.println("G - @PreDestroy");
    }

    public void customDestroy() {
        System.out.println("H - Custom destroy");
    }
}
```

Đăng ký custom init/destroy method nếu muốn theo dõi hai callback đó bằng một bean definition phù hợp, hoặc chuyển class sang cấu hình `@Bean` có `initMethod`/`destroyMethod`. Nếu class đã được component scan, hãy chọn một đường đăng ký bean duy nhất để tránh đăng ký cùng class qua hai nguồn.

Một cách tách rõ ràng là dùng factory method:

```java
@Configuration(proxyBeanMethods = false)
public class LifecycleConfiguration {

    @Bean(initMethod = "customInit", destroyMethod = "customDestroy")
    public LifecycleProbe lifecycleProbe() {
        return new LifecycleProbe();
    }
}
```

Trong trường hợp này hãy bỏ `@Component` trên `LifecycleProbe` để tránh đăng ký class đó qua component scan đồng thời với `@Bean`. Bean vẫn nhận setter injection và các callback tương ứng.

Kết quả log khái quát khi context được refresh rồi đóng:

```text
A - Dependency constructor
B - Probe constructor
C - Setter injection
D - @PostConstruct
Dependency is ready
E - afterPropertiesSet
F - Custom init

... ứng dụng sử dụng bean ...

G - @PreDestroy
H - Custom destroy
```

Thứ tự log giữa các bean khác nhau phụ thuộc dependency graph và thứ tự khởi tạo. Ví dụ trên chỉ mô tả quan hệ lifecycle trong một bean và dependency của nó; không nên dựa vào thứ tự alphabet của tên class để đoán thứ tự tạo mọi bean trong ứng dụng.

## 21. Nguyên tắc thiết kế lifecycle trong dự án Spring Boot

Khi xây dựng service, hãy áp dụng các nguyên tắc sau:

- **Constructor:** thiết lập trạng thái bắt buộc và nhận dependency bắt buộc qua tham số.
- **Constructor injection:** dùng cho phần lớn dependency của service/controller/repository.
- **Setter/field injection:** chỉ dùng khi có lý do rõ ràng; setter phù hợp hơn với dependency tùy chọn hoặc cấu hình có thể thay đổi.
- **`@PostConstruct`:** dùng cho bước chuẩn bị ngắn cần chạy sau khi dependency đã được inject.
- **`InitializingBean`/custom init method:** dùng khi cần tích hợp với interface hoặc class bên ngoài, nhưng tránh nhiều cơ chế cùng làm một việc.
- **`@PreDestroy`/destroy method:** đóng tài nguyên mà bean sở hữu khi container kết thúc vòng đời.
- **Prototype:** tự quản lý việc giải phóng tài nguyên sau khi nhận instance.
- **`ApplicationRunner`/`CommandLineRunner`:** dùng cho công việc ở cấp ứng dụng sau khi context đã refresh, không dùng thay callback của từng bean.
- **Circular dependency:** xem lại thiết kế dependency graph trước khi dùng lazy/provider hoặc đổi injection style.

Một bean có vòng đời dễ hiểu khi mỗi giai đoạn có một trách nhiệm rõ: constructor nhận dependency bắt buộc, container lắp ráp object, initialization hoàn tất phần chuẩn bị, bean phục vụ ứng dụng và destruction giải phóng tài nguyên.

## 22. Bài thực hành

### Bài 1 — Quan sát constructor injection

Tạo `MessageFormatter` và `GreetingService`. Đăng ký chúng thành bean, dùng constructor injection và in log trong constructor. Quan sát dependency được tạo trước bean cần nó.

### Bài 2 — So sánh setter injection

Chuyển một dependency sang setter injection. In log trong constructor, setter và `@PostConstruct`. Ghi lại thứ tự để thấy object được instantiate trước khi setter được gọi.

### Bài 3 — Quan sát thứ tự initialization callbacks

Tạo một bean triển khai `InitializingBean`, thêm `@PostConstruct` và khai báo custom init method. In log trong từng callback. Quan sát thứ tự callback của cùng một bean.

### Bài 4 — Quan sát destruction

Thêm `@PreDestroy` và custom destroy method. Chạy ứng dụng với một context có thể đóng, gọi `close()` hoặc dùng `try-with-resources`. Quan sát log hủy bean.

### Bài 5 — So sánh singleton và prototype

Tạo hai bean cùng class, một singleton và một prototype. Yêu cầu mỗi bean hai lần, so sánh identity và constructor log. Thêm `@PreDestroy` rồi quan sát khác biệt khi context đóng; tự dọn dẹp instance prototype theo cách phù hợp.

### Bài 6 — Thử circular dependency

Tạo `ServiceA` yêu cầu `ServiceB` qua constructor và ngược lại. Quan sát lỗi khi context khởi tạo. Sau đó tách trách nhiệm hoặc chuyển phần logic chung sang service thứ ba để loại bỏ vòng phụ thuộc.

### Bài 7 — Phân biệt init callback với application startup task

Tạo `@PostConstruct` trong một bean và `ApplicationRunner` trong bean khác. In log để quan sát callback của bean diễn ra trong quá trình khởi tạo, còn runner chạy sau khi context đã refresh.

### Bài 8 — Theo dõi lỗi trong callback

Cố ý ném exception trong `@PostConstruct`, quan sát context startup thất bại và đọc chuỗi `Caused by`. Khôi phục code rồi thử ném exception trong runner để so sánh vị trí và ý nghĩa của lỗi.

Sau các bài thực hành, bạn cần phân biệt được **constructor tạo object**, **dependency injection lắp ráp object**, **initialization callbacks hoàn tất bean**, và **destruction callbacks dọn dẹp bean**. Đây là nền tảng để đọc log Spring Boot, thiết kế service có dependency rõ ràng và quản lý tài nguyên đúng vòng đời của IoC container.
