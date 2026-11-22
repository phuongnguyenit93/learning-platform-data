# @Configuration và phương thức @Bean

Trong Spring, một bean không nhất thiết phải là lớp do bạn viết và đánh dấu bằng `@Component` hoặc `@Service`. Bạn cũng có thể **khai báo cách tạo bean bằng một phương thức Java**. Spring gọi phương thức đó như một factory method, nhận đối tượng trả về và quản lý đối tượng theo bean definition.

Cách khai báo này thường được dùng cùng `@Configuration` và `@Bean`:

- `@Configuration` đánh dấu một lớp chứa cấu hình bean.
- `@Bean` đánh dấu phương thức cung cấp một bean cho Spring container.
- Tham số của phương thức `@Bean` có thể là các dependency mà Spring cần giải quyết trước khi gọi phương thức.
- Giá trị trả về trở thành đối tượng do container quản lý, với scope và lifecycle tương ứng.

Đây là **Java-based configuration**: cấu hình ứng dụng bằng mã Java có kiểu dữ liệu và khả năng refactor của IDE. Cơ chế này đặc biệt hữu ích khi tạo bean từ thư viện bên thứ ba, khi cần tùy chỉnh constructor/factory, hoặc khi muốn tập hợp cấu hình của một module tại một vị trí rõ ràng.

## 1. Vì sao cần `@Configuration` và `@Bean`?

Với một lớp do bạn sở hữu, có thể dùng component scanning:

```java
@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

Spring phát hiện `@Service` trong package scan và đăng ký bean definition cho lớp đó.

Nhưng không phải mọi class đều có thể hoặc nên sửa để thêm annotation. Ví dụ, `Clock` thuộc JDK, `ObjectMapper` thuộc thư viện JSON, `DataSource` có thể được tạo bởi thư viện kết nối database. Bạn có thể muốn:

- Chọn constructor hoặc static factory cụ thể.
- Truyền tham số cấu hình vào khi khởi tạo.
- Tạo implementation phù hợp với môi trường.
- Đặt tên bean, scope hoặc callback lifecycle.
- Đăng ký class của thư viện mà không sửa source của nó.

Khi đó, factory method `@Bean` là lựa chọn tự nhiên:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Phương thức `applicationClock()` tạo một `Clock`. Spring gọi method trong quá trình tạo bean và quản lý object được trả về. `Clock` không cần mang annotation Spring.

**`@Bean` khai báo một bean definition thông qua factory method; nó không biến toàn bộ class được trả về thành một component để component scan tìm kiếm.** Container quản lý instance do factory method cung cấp.

## 2. `@Configuration` là gì?

`@Configuration` là annotation đánh dấu một class như nguồn khai báo bean definitions. Một lớp cấu hình thường gom những bean có quan hệ về một chủ đề:

```java
@Configuration
public class PaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    public PaymentService paymentService(
            PaymentGateway paymentGateway) {
        return new PaymentService(paymentGateway);
    }
}
```

Khi `PaymentConfiguration` được nạp vào Spring context, Spring xử lý các phương thức `@Bean` bên trong và đăng ký bean tương ứng.

Một lớp `@Configuration` thường được đưa vào context qua component scan, `@Import`, hoặc một cấu hình khác. `@Configuration` có meta-annotation `@Component`, nên bản thân nó cũng là một ứng viên component scan.

Ví dụ package:

```text
com.example.shop/
├── ShopApplication.java
├── config/
│   └── PaymentConfiguration.java
├── service/
│   └── PaymentService.java
└── api/
    └── PaymentController.java
```

Nếu lớp main có `@SpringBootApplication` tại package `com.example.shop`, cấu hình trong package con `config` thường được component scan phát hiện.

### `@Configuration` khác `@Component` như thế nào?

Cả hai đều có thể là nguồn khai báo bean bằng `@Bean`, nhưng `@Configuration` có ý nghĩa cấu hình chuyên biệt và mặc định sử dụng chế độ proxy bean methods.

| Khai báo lớp | Có thể chứa `@Bean`? | Mặc định xử lý lời gọi giữa các `@Bean` methods |
|---|---|---|
| `@Configuration` | Có | Full configuration: Spring tăng cường lớp cấu hình để intercept lời gọi giữa các bean methods. |
| `@Configuration(proxyBeanMethods = false)` | Có | Lite configuration: lời gọi Java trực tiếp, không intercept. |
| `@Component` | Có | Lite configuration: lời gọi Java trực tiếp, không intercept. |

Do đó, `@Configuration` không chỉ là một tên khác của `@Component`. Nó có thêm semantics cho các lời gọi giữa phương thức `@Bean` khi dùng full mode.

## 3. `@Bean` hoạt động như thế nào?

Một phương thức `@Bean` là **factory method**. Spring gọi method, nhận giá trị trả về và dùng nó làm bean instance.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Các thành phần:

- `@Bean`: đánh dấu phương thức là nguồn tạo bean.
- `appClock`: tên bean mặc định.
- `Clock`: kiểu trả về, cho biết loại object mà method cung cấp.
- `Clock.systemUTC()`: factory logic do lập trình viên định nghĩa.
- Object trả về: instance mà Spring đưa vào quản lý.

Nếu không chỉ định tên, Spring thường dùng **tên phương thức** làm bean name. Có thể chỉ định tên và alias:

```java
@Bean(name = {"appClock", "systemClock"})
public Clock clock() {
    return Clock.systemUTC();
}
```

Trong ví dụ, `appClock` là tên bean và `systemClock` là alias. Cả hai tên cùng trỏ tới một bean definition, không tạo hai instance khác nhau.

Bạn cũng có thể dùng dạng rút gọn:

```java
@Bean("appClock")
public Clock clock() {
    return Clock.systemUTC();
}
```

Tên bean cần nhất quán vì những nơi lookup theo tên hoặc dùng `@Qualifier` sẽ phụ thuộc vào nó.

## 4. Tham số của `@Bean` method là dependency injection

Một ưu điểm quan trọng của Java configuration là **Spring có thể inject dependency vào tham số của factory method**.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService(Clock appClock) {
        return new ReportService(appClock);
    }
}
```

Khi tạo `ReportService`, Spring giải quyết tham số `Clock` từ container rồi truyền vào method. Bạn không cần gọi trực tiếp `appClock()` để lấy bean.

Đây là cách diễn đạt quan hệ phụ thuộc rõ ràng:

```text
Clock bean definition
        │
        ▼
Clock instance
        │
        │ inject vào tham số
        ▼
reportService(Clock appClock)
        │
        ▼
ReportService bean definition / instance
```

Lợi ích:

- Dependency hiển thị ngay trên method signature.
- Không cần truy cập `ApplicationContext` thủ công.
- Có thể dùng `final` field trong object được tạo.
- Tương thích tốt với `proxyBeanMethods = false`.
- Dễ đọc và refactor hơn các lời gọi factory method lồng nhau.

Nếu có nhiều bean cùng kiểu, tham số có thể dùng `@Qualifier` hoặc các metadata chọn bean khác:

```java
@Bean
public PaymentService paymentService(
        @Qualifier("stripeGateway") PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Spring vẫn áp dụng quy tắc phân giải dependency thông thường cho tham số `@Bean` method.

## 5. Full `@Configuration`: Spring intercept lời gọi giữa các bean methods

Mặc định, `@Configuration` có `proxyBeanMethods = true`. Spring tạo một lớp tăng cường (enhanced class), thường thông qua CGLIB, để intercept lời gọi đến các phương thức `@Bean` khi chúng được gọi từ instance configuration đã được container quản lý.

Xét ví dụ:

```java
@Configuration
public class FullConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(appClock());
    }
}
```

Ở full configuration mode, lời gọi `appClock()` bên trong `reportService()` được intercept. Spring trả về bean `appClock` đã được container quản lý theo scope tương ứng, thay vì thực thi factory method như một lời gọi Java mới thông thường.

Với bean singleton mặc định, điều này có nghĩa `ReportService` nhận cùng bean `Clock` mà container cung cấp cho các dependency khác.

### Tại sao cần intercept?

Nếu chỉ là Java thông thường, lời gọi:

```java
return new ReportService(appClock());
```

sẽ gọi method `appClock()` và tạo một `Clock` mới mỗi lần `reportService()` chạy. Full configuration mode đảm bảo lời gọi giữa các bean methods trong cấu hình được xử lý theo semantics của container.

Một ví dụ dễ quan sát hơn:

```java
@Configuration
public class CounterConfiguration {

    @Bean
    public Counter counter() {
        return new Counter();
    }

    @Bean
    public CounterConsumer counterConsumer() {
        return new CounterConsumer(counter());
    }
}
```

Trong full mode, `counter()` được intercept khi gọi từ `counterConsumer()`, vì vậy `CounterConsumer` nhận bean `Counter` do container quản lý. Nếu bean là singleton, đó là instance singleton đã đăng ký.

### Giới hạn của full mode

Để Spring có thể tạo subclass và intercept method, cấu hình full mode có một số giới hạn:

- Lớp `@Configuration` không nên là `final`.
- Phương thức `@Bean` được intercept không được là `private` hoặc `final`.
- Không nên gọi các phương thức cấu hình trên một object tự tạo bằng `new FullConfiguration()`, vì object đó không phải enhanced configuration instance do Spring quản lý.
- Các giới hạn proxy cũng cần được lưu ý với ngôn ngữ JVM có class/method final mặc định, chẳng hạn Kotlin nếu chưa bật plugin phù hợp.

Trong phần lớn ứng dụng, không cần tự tạo subclass hay xử lý CGLIB. Chỉ cần hiểu rằng full mode cho phép lời gọi giữa các bean methods được container điều phối.

## 6. Lite configuration: `@Configuration(proxyBeanMethods = false)` và `@Component`

Lite mode không tăng cường lớp cấu hình để intercept lời gọi giữa các phương thức `@Bean`. Các lời gọi method là **Java method calls thông thường**.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class LiteConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService() {
        return new ReportService(appClock());
    }
}
```

Ở đây, `appClock()` bên trong `reportService()` là lời gọi Java thông thường. Nó chạy factory method và tạo object mới theo code của method. Nó không tự động quay lại container để lấy bean `appClock` hiện hữu.

Vì vậy, `ReportService` có thể nhận một `Clock` khác với singleton bean `appClock` mà container đăng ký.

Đây là khác biệt cốt lõi giữa full và lite configuration:

| Hành vi | Full mode | Lite mode |
|---|---|---|
| `@Configuration` mặc định | Có | Không |
| `@Configuration(proxyBeanMethods = false)` | Không | Có |
| `@Component` chứa `@Bean` | Không | Có |
| Gọi `appClock()` từ một `@Bean` method khác | Được intercept và phân giải theo container | Lời gọi Java trực tiếp |
| Cần CGLIB enhancement cho inter-bean method calls | Có | Không |
| Dùng tham số method để inject dependency | Được hỗ trợ | Được hỗ trợ và thường nên dùng |

### Cách viết đúng trong lite mode

Thay vì gọi trực tiếp `appClock()`, khai báo dependency thành tham số:

```java
@Configuration(proxyBeanMethods = false)
public class TimeConfiguration {

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    public ReportService reportService(Clock appClock) {
        return new ReportService(appClock);
    }
}
```

Spring giải quyết `Clock` trước khi gọi factory method. Cách này rõ ràng và hoạt động đúng trong cả full mode lẫn lite mode.

**Quy tắc thực hành:** nếu không cần gọi trực tiếp một `@Bean` method từ method khác, ưu tiên `@Configuration(proxyBeanMethods = false)` và inject dependency qua tham số. Nếu cần semantics intercept inter-bean calls, giữ full mode mặc định.

## 7. `@Bean` có thể đặt trong `@Component` không?

Có. Spring cho phép khai báo `@Bean` method trong một component class, không chỉ trong `@Configuration`.

Ví dụ:

```java
@Component
public class ClientFactory {

    @Bean
    public Clock clientClock() {
        return Clock.systemUTC();
    }
}
```

Nếu `ClientFactory` được component scan hoặc được đăng ký theo cách khác, Spring xử lý method `@Bean` bên trong. Tuy nhiên, class này thuộc **lite configuration**: gọi `clientClock()` từ một method khác là lời gọi Java thông thường, không được intercept theo full configuration semantics.

Điều đó không có nghĩa `@Bean` trong `@Component` là sai. Đây là một cách hợp lệ khi component đồng thời cung cấp một factory method. Nhưng nếu class chủ yếu có nhiệm vụ khai báo bean definitions, dùng `@Configuration` sẽ thể hiện ý định rõ hơn.

### Không nhầm `@Component` với `@Bean`

```java
@Component
public class EmailSender {
    public void send(String message) {
        // ...
    }
}
```

Trong ví dụ này, component scan phát hiện class `EmailSender` và đăng ký bean.

Còn:

```java
@Configuration(proxyBeanMethods = false)
public class EmailConfiguration {

    @Bean
    public EmailSender emailSender() {
        return new EmailSender();
    }
}
```

Ở đây, Spring phát hiện class cấu hình, sau đó gọi factory method để tạo `EmailSender`. Cả hai cách đều có thể tạo một bean, nhưng **nguồn đăng ký và cách kiểm soát việc khởi tạo khác nhau**. Không cần áp dụng cả `@Component` và `@Bean` cho cùng một instance chỉ để “đảm bảo Spring nhận diện”.

## 8. Tạo bean từ class của thư viện bên thứ ba

Đây là một trường hợp rất phù hợp với `@Bean`.

Giả sử ứng dụng cần một `Clock` hoặc client từ thư viện ngoài, và class đó không có stereotype Spring. Bạn có thể khai báo:

```java
@Configuration(proxyBeanMethods = false)
public class InfrastructureConfiguration {

    @Bean
    public Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Hoặc cấu hình client với dependency:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    public PaymentClient paymentClient(
            PaymentClientProperties properties) {
        return new PaymentClient(
                properties.endpoint(),
                properties.apiKey()
        );
    }
}
```

Ví dụ thứ hai giả định `PaymentClientProperties` đã được đăng ký và `PaymentClient` có constructor tương ứng. Mã thực tế cần quản lý secret từ nguồn an toàn; không ghi API key thật vào source code.

Ưu điểm là không cần sửa class thư viện, và cấu hình khởi tạo nằm trong module ứng dụng chịu trách nhiệm tích hợp thư viện đó.

## 9. Tên bean và alias trong `@Bean`

Tên bean mặc định là tên phương thức factory:

```java
@Bean
public Clock systemClock() {
    return Clock.systemUTC();
}
```

Bean name là `systemClock`.

Có thể đặt nhiều tên:

```java
@Bean(name = {"systemClock", "utcClock"})
public Clock clock() {
    return Clock.systemUTC();
}
```

Tên đầu tiên là bean name; các tên còn lại là alias. Alias không phải bean instance mới.

Tên bean quan trọng khi:

- Dùng `@Qualifier`.
- Lookup bằng `ApplicationContext.getBean("...")`.
- Có nhiều implementation cùng kiểu.
- Tích hợp với cấu hình hoặc thư viện dựa trên một bean name đã quy ước.

Nếu tên không phải contract bắt buộc, dependency injection theo type thường ít phụ thuộc vào tên method hơn.

## 10. Kiểu trả về của `@Bean` method

Nên khai báo kiểu trả về đủ cụ thể để Spring và các công cụ có thể nhận diện bean phù hợp.

Ví dụ:

```java
@Bean
public PaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Ở đây kiểu trả về là interface `PaymentGateway`. Consumer có thể inject theo interface, và cấu hình không buộc caller phụ thuộc vào class `StripePaymentGateway`.

Nếu chỉ khai báo kiểu quá rộng như `Object`, Spring có ít thông tin hơn để dự đoán type bean trước khi factory method được gọi. Điều này có thể ảnh hưởng đến autowiring theo type, điều kiện auto-configuration và việc kiểm tra dependency ở giai đoạn sớm.

**Khuyến nghị:** trả về interface hoặc abstraction mà consumer cần, nhưng đừng khai báo rộng hơn mức cần thiết. Nếu một số consumer cần concrete type, hãy cân nhắc xem việc phụ thuộc vào implementation có thực sự hợp lý hay không.

## 11. Scope của bean khai báo bằng `@Bean`

Bean do `@Bean` method tạo ra vẫn tuân theo scope của Spring. Có thể đặt `@Scope` trên method:

```java
@Configuration(proxyBeanMethods = false)
public class DraftConfiguration {

    @Bean
    @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
    public ReportDraft reportDraft() {
        return new ReportDraft();
    }
}
```

Trong ví dụ này, mỗi lần container được yêu cầu bean `reportDraft`, prototype scope tạo một instance mới.

Có thể dùng scope web nếu ứng dụng có web context phù hợp:

```java
@Bean
@RequestScope
public RequestMetadata requestMetadata() {
    return new RequestMetadata();
}
```

Hoặc khai báo `@SessionScope`/`@ApplicationScope` cho bean factory method tương ứng.

Nhớ rằng scope quy định hành vi cấp instance, còn `@Bean` chỉ là cách khai báo factory method. Hai khái niệm này giải quyết hai vấn đề khác nhau.

## 12. Lifecycle callback của bean tạo bằng `@Bean`

Bean được tạo qua `@Bean` vẫn tham gia lifecycle của Spring. Có thể dùng các callback chuẩn như `@PostConstruct`, `@PreDestroy`, hoặc khai báo tên method init/destroy.

Ví dụ:

```java
public class ManagedClient {

    public void connect() {
        System.out.println("Client initialized");
    }

    public void close() {
        System.out.println("Client closed");
    }
}
```

Khai báo:

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(initMethod = "connect", destroyMethod = "close")
    public ManagedClient managedClient() {
        return new ManagedClient();
    }
}
```

Spring gọi `connect()` trong giai đoạn khởi tạo bean và gọi `close()` khi container hủy bean theo lifecycle bình thường.

Spring cũng hỗ trợ `@PostConstruct`, `@PreDestroy`, `InitializingBean` và `DisposableBean`. Không cần trộn mọi cơ chế vào một class; chọn một cách rõ ràng.

Một số bean có method `close()` hoặc `shutdown()` có thể được Spring suy luận làm destroy method mặc định. Nếu không muốn Spring gọi destroy method được suy luận, `@Bean(destroyMethod = "")` có thể tắt hành vi suy luận đó.

Lưu ý:

- Callback hủy phụ thuộc vào việc container có cơ hội shutdown đúng quy trình.
- Nếu tiến trình bị kill cưỡng bức hoặc máy bị dừng đột ngột, không đảm bảo callback hủy được gọi.
- Prototype bean được tạo và khởi tạo bởi container, nhưng container không tự quản lý đầy đủ destruction callback cho từng prototype sau khi đã giao instance cho caller.
- Không dùng lifecycle callback để thay thế xử lý transaction nghiệp vụ hoặc lưu dữ liệu quan trọng.

## 13. Kết hợp `@Bean` với `@Primary`, `@Qualifier` và `@Profile`

Các metadata lựa chọn bean có thể đặt trên method `@Bean`.

### `@Primary`

```java
@Configuration(proxyBeanMethods = false)
public class GatewayConfiguration {

    @Bean
    @Primary
    public PaymentGateway defaultGateway() {
        return new StripePaymentGateway();
    }

    @Bean
    public PaymentGateway bankGateway() {
        return new BankPaymentGateway();
    }
}
```

Nếu injection point chỉ yêu cầu `PaymentGateway` mà không có qualifier, bean primary có thể được chọn làm ứng viên ưu tiên.

### `@Qualifier`

```java
@Bean
@Qualifier("external")
public PaymentGateway remoteGateway() {
    return new RemotePaymentGateway();
}
```

Injection point có thể dùng qualifier tương ứng để chọn bean theo vai trò.

### `@Profile`

```java
@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {

    @Bean
    @Profile("local")
    public StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("prod")
    public StorageClient productionStorageClient() {
        return new RemoteStorageClient();
    }
}
```

Bean tương ứng chỉ được đăng ký khi profile phù hợp đang active. Nếu không profile nào được bật và consumer yêu cầu `StorageClient`, ứng dụng có thể thiếu bean. Nếu bật cả hai profile, có thể có nhiều ứng viên và cần lựa chọn rõ ràng.

Ngoài ra, `@Bean` method có thể kết hợp với các annotation điều kiện trong hệ sinh thái Spring Boot như `@ConditionalOnProperty` hoặc `@ConditionalOnMissingBean` khi được sử dụng trong đúng loại configuration context.

## 14. `@Bean` method và thứ tự khởi tạo

Không nên dựa vào thứ tự khai báo các method trong cùng một class để điều khiển thứ tự tạo bean. Spring giải quyết dependency dựa trên bean definitions và quan hệ phụ thuộc.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationConfiguration {

    @Bean
    public ReportService reportService(Clock clock) {
        return new ReportService(clock);
    }

    @Bean
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Dù `reportService()` được viết trước `appClock()`, Spring vẫn biết `ReportService` cần `Clock` và giải quyết dependency phù hợp.

Nếu có yêu cầu phụ thuộc về thứ tự khởi tạo ngoài quan hệ constructor/method dependency, cần xem xét cơ chế lifecycle phù hợp như `@DependsOn`, `SmartLifecycle` hoặc application events. Không nên đổi thứ tự method trong file với hy vọng container sẽ tuân theo thứ tự văn bản.

### Bean phụ thuộc vào bean khác nên dùng tham số method

Đây là cách thể hiện dependency rõ ràng:

```java
@Bean
public ReportService reportService(Clock clock) {
    return new ReportService(clock);
}
```

Cách gọi method khác:

```java
@Bean
public ReportService reportService() {
    return new ReportService(appClock());
}
```

có semantics khác nhau giữa full và lite mode. Vì vậy, tham số method là lựa chọn ít gây bất ngờ và không phụ thuộc `proxyBeanMethods`.

## 15. Khi nào cần `static @Bean` method?

Phần lớn `@Bean` method có thể là instance method bình thường. Một số bean infrastructure như `BeanFactoryPostProcessor` hoặc `BeanDefinitionRegistryPostProcessor` được tạo rất sớm trong quá trình container chuẩn bị bean definitions.

Trong trường hợp đó, khai báo factory method `static` có thể tránh phải khởi tạo sớm configuration class chứa nó:

```java
@Configuration(proxyBeanMethods = false)
public class PlaceholderConfiguration {

    @Bean
    public static PropertySourcesPlaceholderConfigurer
            propertySourcesPlaceholderConfigurer() {
        return new PropertySourcesPlaceholderConfigurer();
    }
}
```

Ví dụ này minh họa một infrastructure bean xử lý placeholder. Trong ứng dụng Spring Boot thông thường, auto-configuration thường đã cung cấp các thành phần phổ biến, vì vậy không nên thêm lại nếu không có nhu cầu rõ ràng.

`static @Bean` method không thể sử dụng instance field của configuration class. Nó cũng không được hưởng semantics intercept inter-bean call giống instance `@Bean` method trong full configuration.

Chỉ sử dụng static factory method khi loại bean và lifecycle của nó thực sự yêu cầu tạo sớm hoặc tài liệu framework khuyến nghị.

## 16. Tổ chức nhiều lớp configuration

Khi ứng dụng lớn lên, không nên gom tất cả bean vào một class cấu hình duy nhất. Có thể chia theo trách nhiệm:

```text
config/
├── WebConfiguration.java
├── PersistenceConfiguration.java
├── SecurityConfiguration.java
├── ClientConfiguration.java
└── TimeConfiguration.java
```

Mỗi class có thể chứa các bean liên quan. Nếu chúng nằm dưới package gốc, component scan có thể tìm thấy; nếu ở package ngoài, có thể import rõ ràng:

```java
@Configuration(proxyBeanMethods = false)
@Import({
    ClientConfiguration.class,
    TimeConfiguration.class
})
public class InfrastructureConfiguration {
}
```

Cách tổ chức theo module giúp:

- Biết bean nào thuộc integration nào.
- Dễ tắt hoặc thay một phần cấu hình.
- Tránh class cấu hình khổng lồ.
- Giữ dependency giữa các module rõ ràng.
- Kiểm thử một cấu hình trong phạm vi phù hợp.

Không nên chia class chỉ theo số lượng method; hãy nhóm theo trách nhiệm và ranh giới thay đổi.

## 17. Những lỗi thường gặp với `@Configuration` và `@Bean`

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không inject được bean khai báo bằng `@Bean` | Lớp cấu hình chưa được scan/import; điều kiện/profile không phù hợp. | Kiểm tra package scan, `@Import`, active profile và conditions. |
| Có hai instance của cùng một dependency | Lite mode gọi trực tiếp một `@Bean` method từ method khác. | Dùng tham số method để inject dependency hoặc bật full configuration nếu cần interception. |
| Bean name không như mong đợi | Tên mặc định là method name hoặc alias khai báo khác. | Đặt `@Bean(name = "...")` rõ ràng và kiểm tra alias. |
| `NoUniqueBeanDefinitionException` | Nhiều `@Bean` methods cung cấp cùng type. | Dùng `@Qualifier`, `@Primary` hoặc thiết kế lại type. |
| Configuration class không proxy được | Class/method final/private trong full mode hoặc hạn chế proxy. | Để class/method có thể subclass/intercept, hoặc dùng lite mode và method parameter injection. |
| `@Bean` gọi được nhưng object không phải bean mong muốn | Method được gọi trên object cấu hình tự tạo bằng `new`, hoặc direct call trong lite mode. | Để container gọi factory method và inject dependency qua tham số. |
| Bean khởi tạo sớm ngoài dự kiến | Dependency chain hoặc infrastructure bean yêu cầu khởi tạo sớm. | Kiểm tra lazy mode, factory method và loại bean infrastructure. |
| Destroy callback không chạy | Context không shutdown bình thường, bean scope không được quản lý destruction như mong đợi. | Kiểm tra lifecycle, scope và cơ chế dừng ứng dụng. |

### Lỗi thường gặp: gọi `@Bean` method từ code nghiệp vụ

Không nên viết:

```java
@Service
public class ReportService {

    public void generate() {
        Clock clock = new TimeConfiguration().appClock();
        // ...
    }
}
```

Đoạn này tự tạo configuration object và gọi method như Java bình thường. Nó không yêu cầu Spring cung cấp bean `Clock` đã quản lý.

Hãy inject dependency:

```java
@Service
public class ReportService {

    private final Clock clock;

    public ReportService(Clock clock) {
        this.clock = clock;
    }

    public void generate() {
        // Dùng clock đã được container inject.
    }
}
```

Mã nghiệp vụ không nên phụ thuộc vào class cấu hình để tạo lại dependency.

## 18. Kiểm tra bean do `@Bean` method cung cấp

Có thể quan sát bean name và type trong test:

```java
@SpringBootTest
class TimeConfigurationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void applicationClockIsRegistered() {
        Clock clock =
                context.getBean("applicationClock", Clock.class);

        assertNotNull(clock);
    }
}
```

Ví dụ giả định cấu hình `TimeConfiguration` đã được nạp và có bean tên `applicationClock`.

Có thể truy vấn tất cả bean theo type:

```java
Map<String, Clock> clocks = context.getBeansOfType(Clock.class);

clocks.forEach((name, clock) ->
        System.out.println(name + " -> " + clock.getClass().getName()));
```

Nếu có nhiều `Clock` bean, map cho biết tên các ứng viên. Nếu object được proxy, `getClass()` có thể phản ánh proxy thay vì concrete target; hãy kết hợp với bean definition và cấu hình để hiểu nguồn tạo.

Với ứng dụng có Actuator được cấu hình phù hợp, endpoint `/actuator/beans` cũng có thể cung cấp thông tin bean. Chỉ expose endpoint quản trị trong phạm vi được bảo vệ, không công khai chỉ để debug.

## 19. Bài tập thực hành

### Bài tập A — Tạo bean từ JDK class

1. Tạo `TimeConfiguration` với `@Bean Clock applicationClock()`.
2. Inject `Clock` vào `TimeService` qua constructor.
3. Viết unit test sử dụng `Clock.fixed(...)`.
4. Giải thích vì sao `Clock` không cần `@Component`.

### Bài tập B — So sánh full và lite configuration

Tạo hai configuration có `counter()` và `counterConsumer()`; method consumer gọi `counter()` trực tiếp.

- Thử `@Configuration` mặc định.
- Thử `@Configuration(proxyBeanMethods = false)`.
- So sánh identity của object được truyền vào consumer với bean mà context trả về.
- Sau đó thay lời gọi trực tiếp bằng tham số method và quan sát hai mode hoạt động nhất quán.

### Bài tập C — Tên bean và qualifier

Khai báo hai `PaymentGateway` bằng hai `@Bean` methods. Inject theo type không qualifier để quan sát ambiguity. Thêm `@Primary`, sau đó thêm `@Qualifier` để chọn implementation cụ thể.

### Bài tập D — Scope và lifecycle

Khai báo một bean prototype bằng `@Scope`, thêm init/destroy callback. Yêu cầu container cấp nhiều instance và quan sát callback nào được gọi. Giải thích vì sao prototype destruction không được container quản lý giống singleton.

### Bài tập E — Cấu hình theo profile

Khai báo hai `StorageClient` factory methods với `@Profile("local")` và `@Profile("prod")`. Chạy với từng profile và kiểm tra bean nào xuất hiện. Thử không bật profile nào và ghi nhận behavior của consumer.

### Bài tập F — Đăng ký cấu hình ngoài package

Đặt một configuration class trong package không nằm dưới package main. Thử component scan mặc định rồi thêm `@Import`. So sánh cách bean definition được đưa vào context.

## 20. Nguyên tắc cần nhớ

1. **`@Configuration`** đánh dấu class chứa cấu hình bean; nó thường được nạp bằng component scan hoặc import.
2. **`@Bean`** đánh dấu factory method; giá trị trả về là object Spring quản lý.
3. **Tham số `@Bean` method** là dependency injection do container giải quyết, thường là cách rõ ràng nhất để liên kết các bean.
4. **Full configuration** mặc định intercept lời gọi giữa các bean methods; **lite configuration** dùng Java method calls thông thường.
5. **`@Configuration(proxyBeanMethods = false)`** và `@Component` chứa `@Bean` là lite mode; không gọi trực tiếp method để lấy một bean singleton khác.
6. **Bean name mặc định** lấy từ tên factory method; có thể đặt tên và alias tường minh.
7. Bean tạo bằng `@Bean` vẫn có scope, lifecycle, qualifier, primary và điều kiện đăng ký như các bean khác.
8. Dùng `@Bean` đặc biệt phù hợp với object của JDK/thư viện ngoài hoặc khi cần factory logic tùy chỉnh.

Khi thiết kế Java configuration, hãy coi mỗi `@Bean` method là **một khai báo có kiểu về cách container tạo một dependency**. Để Spring giải quyết các dependency qua tham số method, đặt tên bean có chủ đích khi cần, và chọn full/lite mode dựa trên việc bạn có thực sự cần intercept lời gọi giữa các factory method hay không.
