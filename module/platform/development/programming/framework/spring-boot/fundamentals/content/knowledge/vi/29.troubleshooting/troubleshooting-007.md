# BeanCreationException do constructor, init hoặc dependency thất bại

Khi Spring Boot khởi động, Spring container tạo các bean theo dependency graph và thực hiện nhiều bước trong lifecycle. Nếu một bean không thể được khởi tạo, một dependency không thể được resolve hoặc callback khởi tạo ném exception, quá trình tạo bean có thể thất bại với `BeanCreationException` hoặc một exception chuyên biệt có liên quan.

Thông báo ở đầu stack trace thường chỉ cho biết **bean nào không tạo được**. Nguyên nhân thực sự có thể nằm sâu hơn:

- Constructor ném exception khi kiểm tra cấu hình hoặc mở resource.
- Constructor injection không tìm thấy bean phù hợp.
- Có nhiều bean cùng kiểu nhưng không xác định được bean cần dùng.
- Một dependency khác thất bại trong constructor hoặc callback init.
- `@PostConstruct`, `afterPropertiesSet()` hoặc custom init method ném exception.
- Property không convert được sang kiểu cần bind.
- Bean phụ thuộc vào cấu hình/profile không được kích hoạt.
- Có vòng lặp dependency không thể giải quyết.
- Một `@Bean` factory method trả về `null`, ném exception hoặc tạo object không hợp lệ.

Để xử lý đúng, đừng dừng ở dòng `Error creating bean with name ...`. Hãy lần theo **exception chain tới nguyên nhân gốc**, xác định bean đầu tiên thất bại và lifecycle phase nơi lỗi xuất hiện.

## 1. `BeanCreationException` biểu thị điều gì?

`BeanCreationException` là exception của Spring BeanFactory, cho biết container không thể tạo hoặc cấu hình một bean theo yêu cầu.

Ví dụ thông báo minh họa:

```text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService':
Injection of autowired dependencies failed
```

Thông báo này cho biết bean `orderService` thất bại khi Spring xử lý dependency injection. Nhưng nó chưa nói dependency cụ thể nào hỏng hoặc vì sao dependency đó hỏng.

Một stack trace có thể tiếp tục:

```text
BeanCreationException: Error creating bean with name 'orderService'
  ...
Caused by: UnsatisfiedDependencyException:
  Error creating bean with name 'paymentGateway'
  ...
Caused by: BeanCreationException:
  Error creating bean with name 'paymentClient'
  ...
Caused by: IllegalStateException:
  Missing endpoint configuration
```

Trong ví dụ, `orderService` chỉ là bean đầu tiên mà container báo lỗi ở một tầng. Root cause có ý nghĩa nằm ở `paymentClient` và cuối cùng là `Missing endpoint configuration`.

### 1.1. Exception bên ngoài và nguyên nhân bên trong

| Exception | Ý nghĩa thường gặp |
| --- | --- |
| `BeanCreationException` | Bean không thể được tạo hoặc khởi tạo |
| `UnsatisfiedDependencyException` | Một dependency của bean không thể được thỏa mãn |
| `BeanInstantiationException` | Spring không thể instantiate class hoặc gọi factory method theo cách yêu cầu |
| `NoSuchBeanDefinitionException` | Không có bean phù hợp để resolve |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng phù hợp nhưng không xác định được một bean duy nhất |
| `BeanCurrentlyInCreationException` | Bean đang trong quá trình tạo lại bị yêu cầu theo cách không thể giải quyết, thường liên quan circular dependency |
| `BeanDefinitionStoreException` | Có vấn đề khi đọc, parse hoặc đăng ký bean definitions |
| `BeanNotOfRequiredTypeException` | Bean được tìm thấy nhưng object không có kiểu được yêu cầu |
| `BindException` / `ConfigurationPropertiesBindException` | Property binding thất bại |

Một số exception trên có thể nằm trong cause chain của `BeanCreationException`; một số có thể xuất hiện trực tiếp ở tầng cao hơn tùy thời điểm và đường code.

### 1.2. Đừng chỉ tìm chữ `BeanCreationException`

Khi debug, cần đọc:

1. Bean name đầu tiên Spring báo không tạo được.
2. Message mô tả phase hoặc thao tác thất bại.
3. Các `Caused by` tiếp theo.
4. Exception sâu nhất có nguyên nhân kỹ thuật cụ thể.
5. Dòng code đầu tiên trong stack trace thuộc package ứng dụng hoặc thư viện mà bạn kiểm soát.

Root cause không phải lúc nào cũng là exception sâu nhất về mặt số lượng. Một số exception ở dưới chỉ là wrapper kỹ thuật; hãy chọn exception giải thích được **vì sao thao tác thất bại**.

## 2. Bean lifecycle: lỗi có thể xảy ra ở bước nào?

Một singleton bean thông thường trải qua các bước khái quát:

```text
BeanDefinition được đăng ký
          |
          v
Resolve constructor và dependencies
          |
          v
Instantiate object (gọi constructor)
          |
          v
Populate properties / field / setter injection
          |
          v
Aware callbacks
          |
          v
BeanPostProcessor: before initialization
          |
          v
Initialization callbacks
  - @PostConstruct
  - InitializingBean.afterPropertiesSet()
  - custom init method
          |
          v
BeanPostProcessor: after initialization
          |
          v
Expose bean reference cho client
```

Đây là mô hình khái quát cho một bean thông thường. Factory beans, lazy initialization, proxy creators, early references, scoped beans và nhiều extension point có thể làm chi tiết phức tạp hơn.

### 2.1. Lỗi trước khi constructor chạy

Với constructor injection, Spring phải resolve các dependency trước khi có thể gọi constructor của bean đang tạo.

```java
@Service
public class OrderService {

    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Nếu không có bean `PaymentGateway` phù hợp, Spring có thể không gọi được constructor của `OrderService` vì không thể cung cấp đối số.

### 2.2. Lỗi bên trong constructor

```java
@Service
public class PaymentGateway {

    public PaymentGateway() {
        throw new IllegalStateException("Cannot initialize gateway");
    }
}
```

Spring có thể instantiate class nhưng constructor ném exception. Bean không thể được tạo thành công.

### 2.3. Lỗi sau constructor

```java
@Component
public class SearchIndexClient {

    @PostConstruct
    void initialize() {
        throw new IllegalStateException("Index is unavailable");
    }
}
```

Constructor có thể chạy thành công, nhưng callback `@PostConstruct` thất bại. Spring không xem bean đã được khởi tạo thành công.

### 2.4. Lỗi trong BeanPostProcessor

Một `BeanPostProcessor` có thể xử lý bean trước hoặc sau initialization. Nếu code xử lý của processor ném exception, bean creation cũng có thể thất bại.

Khi stack trace dẫn tới custom post-processor, hãy kiểm tra:

- Processor có áp dụng cho bean nào?
- Có giả định sai về runtime type không?
- Có gọi dependency quá sớm không?
- Có xử lý proxy hoặc factory bean đúng không?

## 3. Constructor thất bại do code bên trong

Constructor nên chủ yếu nhận dependency và thiết lập trạng thái ban đầu. Những thao tác có side effect, phụ thuộc mạng hoặc có thể chờ lâu thường không nên đặt trực tiếp trong constructor.

### 3.1. Ví dụ constructor mở kết nối từ xa

```java
@Component
public class PartnerClient {

    private final PartnerConnection connection;

    public PartnerClient() {
        this.connection = PartnerConnection.connect(
                "https://partner.example.test"
        );
    }
}
```

Nếu đối tác không truy cập được, constructor có thể ném exception. Kết quả là application context không hoàn tất startup.

### 3.2. Constructor có quá nhiều trách nhiệm

Một constructor như sau rất khó chẩn đoán:

```java
public ReportService(
        DataSource dataSource,
        HttpClient httpClient,
        Clock clock) {

    this.dataSource = dataSource;
    this.httpClient = httpClient;
    this.clock = clock;

    validateRemoteAccount();
    preloadAllReports();
    startBackgroundPolling();
}
```

Nó vừa nhận dependency, vừa gọi mạng, truy vấn dữ liệu lớn và tạo công việc nền. Một lỗi bất kỳ đều có thể biến thành lỗi tạo bean.

Tách các trách nhiệm:

- Constructor chỉ lưu dependency.
- Cấu hình và validation tĩnh được thực hiện qua typed configuration.
- Warm-up bắt buộc có một lifecycle step riêng, có timeout và readiness policy.
- Công việc nền dùng executor/worker được Spring quản lý.
- Resource được đóng bằng destroy lifecycle phù hợp.

### 3.3. Giữ constructor đơn giản

```java
@Service
public class ReportService {

    private final ReportRepository repository;
    private final PartnerClient partnerClient;

    public ReportService(
            ReportRepository repository,
            PartnerClient partnerClient) {
        this.repository = repository;
        this.partnerClient = partnerClient;
    }
}
```

Constructor injection làm dependency rõ ràng và cho phép field là `final`. Những kiểm tra nghiệp vụ hoặc thao tác từ xa có thể được thực hiện trong method chuyên biệt với error handling phù hợp.

### 3.4. Khi nào startup cần kiểm tra dependency từ xa?

Một số ứng dụng có yêu cầu bắt buộc phải xác nhận database/schema hoặc dịch vụ hạ tầng trước khi nhận traffic. Có thể thực hiện warm-up/validation ở startup lifecycle step, nhưng cần:

- Timeout cho network/database calls.
- Failure message có ngữ cảnh và không chứa secret.
- Quyết định rõ lỗi nào phải fail startup.
- Quyết định rõ lỗi nào chỉ làm readiness từ chối traffic.
- Không retry vô hạn trong startup.

Không phải mọi dependency tùy chọn đều nên làm toàn bộ ứng dụng không khởi động được.

## 4. Dependency injection thất bại

Constructor injection là cách dễ đọc dependency graph:

```java
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Nếu Spring không tìm được bean phù hợp, startup thất bại trước khi `CheckoutService` được tạo.

### 4.1. Không có bean tương ứng

Ví dụ:

```java
public interface PaymentGateway {
    void charge(String orderId);
}
```

Nhưng không có implementation được đăng ký:

```java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway paymentGateway) {
    }
}
```

Spring có thể báo:

```text
No qualifying bean of type 'PaymentGateway' available
```

Kiểm tra:

- Implementation có được tạo không?
- Package có nằm trong component scan không?
- Class có annotation stereotype phù hợp không?
- `@Bean` factory method có nằm trong configuration được load không?
- Profile/condition có vô tình loại bean không?
- Có module/dependency runtime bị thiếu không?

### 4.2. Component scan không bao phủ package

Ví dụ:

```text
com.example.app
  ├── Application.java
  └── order
      └── OrderService.java

com.example.payment
  └── PaymentGatewayImpl.java
```

Nếu `Application.java` dùng `@SpringBootApplication` ở `com.example.app`, component scan mặc định tập trung vào package đó và các package con. `com.example.payment` là package sibling, có thể không được scan.

Cách xử lý có chủ đích:

```java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.app",
        "com.example.payment"
    }
)
public class Application {
}
```

Hoặc đặt application class ở package gốc phù hợp với cấu trúc module.

Không mở rộng component scan thành toàn bộ package của mọi thư viện một cách tùy tiện; điều đó có thể đăng ký bean ngoài dự kiến.

### 4.3. Conditional bean không được tạo

```java
@Configuration
public class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
        name = "payment.provider",
        havingValue = "partner"
    )
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Nếu `payment.provider` không có giá trị `partner`, bean trên không được đăng ký.

Một service constructor bắt buộc `PaymentGateway` sẽ thất bại nếu không có bean thay thế.

Kiểm tra:

- Property thực tế đã được nạp chưa?
- Có nguồn cấu hình nào ghi đè không?
- Condition có đúng tên/giá trị không?
- Có implementation mặc định cho môi trường không?

### 4.4. Profile không được kích hoạt

```java
@Service
@Profile("production")
public class ProductionPaymentGateway implements PaymentGateway {
}
```

Nếu ứng dụng không chạy profile `production`, bean này không được đăng ký.

Một dependency bắt buộc vào `PaymentGateway` có thể vì thế không được thỏa mãn.

Chạy:

```bash
java -jar app.jar --spring.profiles.active=production
```

hoặc cấu hình profile bằng nguồn phù hợp của môi trường.

Đừng sửa dependency thành optional chỉ để che việc profile production bị cấu hình sai.

## 5. Có nhiều bean cùng kiểu

Một lỗi khác:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
```

Ví dụ:

```java
@Service
public class CardPaymentGateway implements PaymentGateway {
}
```

```java
@Service
public class WalletPaymentGateway implements PaymentGateway {
}
```

Client:

```java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway gateway) {
    }
}
```

Spring có hai ứng viên phù hợp và không biết chọn cái nào.

### 5.1. Dùng `@Qualifier`

```java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("cardPaymentGateway")
            PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Tên qualifier mặc định có thể dựa trên bean name, thường là tên class theo camel case nếu được component scan đăng ký.

### 5.2. Dùng `@Primary`

```java
@Service
@Primary
public class CardPaymentGateway implements PaymentGateway {
}
```

`@Primary` đánh dấu một bean ưu tiên khi resolve một dependency theo kiểu và có nhiều ứng viên.

### 5.3. Chọn bean theo nghiệp vụ

Nếu lựa chọn gateway phụ thuộc vào dữ liệu request, không nên cố inject một bean duy nhất rồi mong `@Primary` giải quyết mọi trường hợp.

Có thể inject nhiều implementation:

```java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    public PaymentGateway gatewayFor(String provider) {
        PaymentGateway gateway = gateways.get(provider);
        if (gateway == null) {
            throw new IllegalArgumentException(
                    "Unsupported payment provider"
            );
        }
        return gateway;
    }
}
```

Trong ứng dụng thực tế, nên dùng provider key đã chuẩn hóa và xử lý lỗi phù hợp. Không đưa raw input không kiểm soát vào tên bean.

## 6. Lỗi trong `@PostConstruct`

`@PostConstruct` đánh dấu một method initialization được gọi sau khi dependency injection hoàn tất và trước khi bean được xem là khởi tạo xong.

### 6.1. Ví dụ method init thất bại

```java
@Component
public class CurrencyCatalog {

    @PostConstruct
    void load() {
        if (!catalogFileExists()) {
            throw new IllegalStateException(
                    "Currency catalog is missing"
            );
        }
    }

    private boolean catalogFileExists() {
        return false;
    }
}
```

Nếu callback ném exception, Spring không thể hoàn tất creation của `currencyCatalog`.

Các bean khác phụ thuộc vào nó cũng có thể thất bại theo chuỗi.

### 6.2. Vì sao exception ở một bean làm nhiều bean thất bại?

Giả sử:

```text
CheckoutController
       |
       v
CheckoutService
       |
       v
CurrencyCatalog
       |
       v
@PostConstruct throws
```

Spring có thể báo lỗi ở `CurrencyCatalog`, rồi các bean phụ thuộc vào `CheckoutService` hoặc controller cũng không được tạo. Stack trace có thể có nhiều wrapper; hãy tìm bean đầu tiên gây lỗi thay vì sửa lần lượt mọi bean ở phía trên.

### 6.3. Đừng dùng `@PostConstruct` cho công việc dài hoặc không giới hạn

Không nên:

```java
@PostConstruct
void initialize() {
    while (true) {
        pollPartner();
    }
}
```

Context không thể hoàn tất refresh vì method không trả về.

`@PostConstruct` phù hợp với việc khởi tạo ngắn, đồng bộ, có giới hạn và gắn trực tiếp với trạng thái của bean.

Nếu cần công việc dài:

- Dùng runner hoặc lifecycle component có thiết kế rõ.
- Dùng timeout.
- Cập nhật readiness nếu instance chưa phục vụ được.
- Tách worker khỏi constructor/init callback.

### 6.4. Không giả định mọi dependency đã sẵn sàng cho mọi thao tác

Trong `@PostConstruct`, dependency đã được inject, nhưng những component khác có thể chưa hoàn tất lifecycle theo cách bạn mong đợi. Không gọi ngược một bean khác để kích hoạt cả hệ thống trong khi context còn đang khởi tạo.

Tránh phụ thuộc vòng giữa các initialization callbacks.

## 7. `InitializingBean.afterPropertiesSet()`

Spring hỗ trợ interface:

```java
org.springframework.beans.factory.InitializingBean
```

Ví dụ:

```java
@Component
public class SearchClient implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        // Kiểm tra trạng thái nội bộ sau khi properties được inject
    }
}
```

Nếu `afterPropertiesSet()` ném exception, bean initialization thất bại.

### 7.1. So sánh ba cơ chế init

| Cơ chế | Cách khai báo | Khi phù hợp |
| --- | --- | --- |
| `@PostConstruct` | Annotation trên method | Callback ngắn gắn với bean |
| `InitializingBean` | Implement `afterPropertiesSet()` | Class chấp nhận phụ thuộc Spring lifecycle API |
| Custom init method | `@Bean(initMethod = "initialize")` | Class bên ngoài hoặc muốn khai báo lifecycle trong config |

### 7.2. Custom init method

```java
@Configuration(proxyBeanMethods = false)
public class SearchConfiguration {

    @Bean(initMethod = "initialize", destroyMethod = "close")
    public SearchClient searchClient() {
        return new SearchClient();
    }
}
```

`SearchClient` ở đây là class giả định có `initialize()` và `close()`.

Nếu `initialize()` ném exception, bean không được tạo thành công; context refresh có thể thất bại.

### 7.3. Thứ tự initialization callbacks

Trong lifecycle bean thông thường, Spring thực hiện các callback init theo thứ tự hỗ trợ, gồm:

1. `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method được khai báo.

BeanPostProcessor có callback trước/sau initialization bao quanh các bước tương ứng.

Không nên định nghĩa cùng một thao tác cleanup/init ở nhiều nơi nếu không cần thiết. Một hành động khởi tạo bị gọi lặp có thể tạo connection hoặc thread trùng lặp.

## 8. Property binding và cấu hình sai kiểu

Một bean có thể thất bại khi Spring bind cấu hình.

Ví dụ:

```java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        int retryCount
) {
}
```

Nếu cấu hình:

```yaml
payment:
  endpoint: "not-a-valid-uri"
  timeout: "many seconds"
  retry-count: "three"
```

Spring không thể convert một số giá trị thành kiểu mong muốn. Tùy vị trí bind, bạn có thể gặp `BindException`, `ConfigurationPropertiesBindException` hoặc một exception được bọc trong lỗi tạo bean.

### 8.1. Kiểm tra giá trị và kiểu dữ liệu

Ví dụ đúng:

```yaml
payment:
  endpoint: "https://payments.example.test"
  timeout: 5s
  retry-count: 3
```

Spring Boot hỗ trợ conversion cho nhiều kiểu phổ biến như `Duration`, `DataSize`, URI và các kiểu scalar.

### 8.2. Bật validation cho configuration properties

```java
@ConfigurationProperties(prefix = "payment")
@Validated
public record PaymentProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(0) @Max(5) int retryCount
) {
}
```

Ví dụ cần dependency validation phù hợp và imports `jakarta.validation.constraints.*`, `org.springframework.validation.annotation.Validated`.

Nếu validation thất bại, startup có thể fail với message rõ hơn thay vì đợi tới request đầu tiên mới phát hiện cấu hình không hợp lệ.

### 8.3. Property bắt buộc bị thiếu

Với `@Value`:

```java
@Value("${payment.endpoint}")
private URI endpoint;
```

Nếu property không có và không có default, placeholder resolution có thể thất bại trong quá trình tạo bean.

Nếu property là bắt buộc, lỗi startup rõ ràng có thể là hành vi đúng. Nếu property tùy chọn, hãy thể hiện điều đó qua default hoặc kiểu dữ liệu phù hợp.

### 8.4. Không dùng default để che cấu hình production thiếu

Ví dụ:

```java
@Value("${payment.endpoint:http://localhost:8080}")
```

Default local có thể làm ứng dụng khởi động thành công trong production nhưng gọi nhầm endpoint.

Chỉ đặt default khi nó là một giá trị an toàn và đúng về mặt nghiệp vụ. Với endpoint/secret bắt buộc, nên fail fast với thông báo cụ thể nhưng không lộ secret.

## 9. `@Bean` factory method thất bại

Không phải bean nào cũng được tạo qua constructor của một class có `@Component`. Một bean có thể được tạo từ method `@Bean`.

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    public PartnerClient partnerClient(
            PartnerProperties properties) {

        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                    "Partner endpoint is required"
            );
        }

        return PartnerClient.connect(properties.endpoint());
    }
}
```

Nếu method ném exception, Spring không thể tạo bean `partnerClient`.

### 9.1. Factory method gọi dependency khác

```java
@Bean
public ReportService reportService(
        ReportRepository repository,
        Clock clock) {
    return new ReportService(repository, clock);
}
```

Nếu `ReportRepository` hoặc `Clock` không thể resolve, factory method không được gọi thành công.

### 9.2. Không trả về null

Một factory method `@Bean` thông thường phải cung cấp bean instance hợp lệ. Trả `null` có thể tạo hành vi không mong muốn hoặc khiến bean không được cung cấp như client kỳ vọng.

Nếu một integration tùy chọn không tồn tại, hãy dùng condition để không đăng ký bean, hoặc dùng abstraction rõ ràng biểu diễn sự vắng mặt. Đừng dùng `null` để giả lập optional dependency mà không có contract.

### 9.3. FactoryBean có lifecycle riêng

`FactoryBean<T>` là abstraction Spring cho một factory tạo object được expose như bean. Nếu factory hoặc `getObject()` thất bại, lỗi có thể xuất hiện khi Spring tạo/tra cứu product của factory.

Khi stack trace có `FactoryBean`, hãy phân biệt:

- Bean factory object.
- Product object mà factory tạo.
- Thời điểm product được tạo (eager/lazy).

Không mặc định class factory là object mà client nhận được.

## 10. Circular dependency

Một lỗi khó chịu khi tạo bean là dependency cycle:

```text
OrderService -> PaymentService -> OrderService
```

Ví dụ:

```java
@Service
public class OrderService {

    public OrderService(PaymentService paymentService) {
    }
}
```

```java
@Service
public class PaymentService {

    public PaymentService(OrderService orderService) {
    }
}
```

Để tạo `OrderService`, Spring cần `PaymentService`; để tạo `PaymentService`, Spring lại cần `OrderService` đang tạo dở.

### 10.1. Constructor cycle thường không thể giải quyết

Với constructor injection thuần túy, Spring không thể tạo object đầu tiên vì chưa có đối tượng nào hoàn chỉnh để cung cấp cho constructor còn lại.

Lỗi có thể xuất hiện dưới dạng:

```text
BeanCurrentlyInCreationException
```

hoặc một thông báo circular reference trong startup failure.

### 10.2. Setter/field cycle có thể được xử lý trong một số trường hợp

Spring Framework có cơ chế early singleton references để xử lý một số circular dependencies giữa singleton beans không phụ thuộc constructor cycle. Tuy nhiên, khả năng này phụ thuộc loại bean, proxy/post-processor và cấu hình.

Spring Boot từ dòng 2.6 mặc định không cho phép circular references trong cấu hình ứng dụng mới, trừ khi được bật lại bằng property tương ứng.

Không nên dựa vào việc bật circular references như cách sửa kiến trúc lâu dài.

### 10.3. Thiết kế lại để bỏ vòng lặp

Thay:

```text
OrderService <----> PaymentService
```

bằng một component điều phối:

```text
OrderWorkflow
   |       |
   v       v
OrderService  PaymentService
```

Ví dụ:

```java
@Service
public class OrderWorkflow {

    private final OrderService orders;
    private final PaymentService payments;

    public OrderWorkflow(
            OrderService orders,
            PaymentService payments) {
        this.orders = orders;
        this.payments = payments;
    }

    public void checkout(String orderId) {
        orders.validate(orderId);
        payments.charge(orderId);
        orders.markPaid(orderId);
    }
}
```

Hai service không cần phụ thuộc lẫn nhau. Orchestrator thể hiện rõ thứ tự use case.

### 10.4. `@Lazy` có thể trì hoãn resolve nhưng không sửa thiết kế

```java
public PaymentService(@Lazy OrderService orderService) {
    this.orderService = orderService;
}
```

`@Lazy` ở injection point có thể tạo proxy/lazy reference và phá vòng lặp khởi tạo trong một số trường hợp.

Nhưng nó có thể chỉ trì hoãn lỗi tới lần gọi method đầu tiên, hoặc tạo một dependency cycle về mặt nghiệp vụ vẫn còn nguyên.

Chỉ dùng khi lazy resolution là một phần thiết kế có chủ đích, không phải cách né mọi circular dependency.

## 11. Optional dependency: phân biệt tùy chọn thật và dependency bắt buộc

Nếu một integration không bắt buộc, có một số cách thể hiện rõ sự tùy chọn.

### 11.1. `ObjectProvider<T>`

```java
@Service
public class NotificationService {

    private final ObjectProvider<PushGateway> pushGatewayProvider;

    public NotificationService(
            ObjectProvider<PushGateway> pushGatewayProvider) {
        this.pushGatewayProvider = pushGatewayProvider;
    }

    public void notifyUser(String userRef) {
        PushGateway gateway =
                pushGatewayProvider.getIfAvailable();

        if (gateway != null) {
            gateway.send(userRef);
        }
    }
}
```

`ObjectProvider` cho phép resolve dependency tại thời điểm sử dụng và xử lý trường hợp không có bean theo API phù hợp.

Nếu có nhiều bean và không có lựa chọn rõ, một số phương thức resolve vẫn có thể ném lỗi ambiguity.

### 11.2. `Optional<T>`

```java
public NotificationService(Optional<PushGateway> pushGateway) {
    this.pushGateway = pushGateway;
}
```

Đây là một cách biểu diễn dependency có thể vắng mặt trong những tình huống Spring hỗ trợ.

### 11.3. `@Autowired(required = false)`

Field hoặc setter injection có thể khai báo optional:

```java
@Autowired(required = false)
public void setPushGateway(PushGateway pushGateway) {
    this.pushGateway = pushGateway;
}
```

Tuy nhiên, optional field có thể tạo object ở trạng thái thiếu dependency và khiến lỗi chỉ xuất hiện khi method được gọi. Constructor injection với `Optional` hoặc `ObjectProvider` thường diễn đạt ý định rõ hơn.

### 11.4. Đừng biến dependency bắt buộc thành optional để startup pass

Nếu ứng dụng không thể thực hiện checkout khi thiếu payment gateway, dependency đó phải được coi là bắt buộc hoặc readiness phải từ chối traffic cho tới khi gateway sẵn sàng.

Đừng dùng `getIfAvailable()` rồi âm thầm bỏ qua thanh toán chỉ để không có `BeanCreationException`.

## 12. Lỗi do proxy và post-processing

Bean có thể được proxy bởi Spring AOP hoặc một cơ chế hạ tầng khác. Proxy creation thường xảy ra trong quá trình bean post-processing.

Một số lỗi:

- Target class không thể được subclass trong class-based proxy strategy.
- Final class/method không phù hợp với subclass proxy.
- Advisor hoặc custom `BeanPostProcessor` ném exception.
- Code phụ thuộc concrete class trong khi bean được expose bằng JDK proxy.
- Bean bị truy cập quá sớm trước khi proxy được tạo hoàn chỉnh.

### 12.1. Final class và CGLIB

```java
@Service
public final class PaymentService {
}
```

Nếu cấu hình yêu cầu class-based proxy cho bean này, Spring không thể tạo subclass của final class theo cơ chế thông thường.

Giải pháp có thể là bỏ `final`, thiết kế interface phù hợp và dùng interface proxy, hoặc xem lại yêu cầu AOP.

### 12.2. BeanPostProcessor truy cập bean quá sớm

Một custom post-processor không nên gọi `getBean()` tùy tiện trong giai đoạn xử lý bean definitions. Việc tạo bean quá sớm có thể làm bean post-processor khác chưa được đăng ký hoặc làm lifecycle bị lệch.

Nếu có cảnh báo:

```text
Bean ... is not eligible for getting processed by all BeanPostProcessors
```

hãy xem cách khai báo post-processor, dependency của nó và việc có vô tình tạo bean quá sớm hay không.

### 12.3. Không ép cast proxy sang implementation

Nếu một bean được expose bằng JDK proxy, code như:

```java
PaymentService service =
        (PaymentService) applicationContext.getBean("paymentService");
```

có thể gây `ClassCastException`.

Inject qua interface nghiệp vụ hoặc điều chỉnh proxy strategy phù hợp. Không dùng cast như cách sửa bean creation.

## 13. Phân biệt lỗi bean creation với lỗi sau startup

Không phải exception nào xuất hiện sau khi ứng dụng chạy cũng là `BeanCreationException`.

| Thời điểm | Ví dụ | Nhóm vấn đề |
| --- | --- | --- |
| Đọc bean definitions | Parse configuration lỗi | Configuration/definition failure |
| Resolve constructor args | Thiếu hoặc ambiguous dependency | Dependency resolution |
| Instantiate | Constructor/factory method throw | Bean instantiation |
| Populate properties | Injection/conversion thất bại | Dependency/property population |
| Init callback | `@PostConstruct` throw | Initialization |
| Sau startup, khi xử lý request | Method service throw | Runtime business failure |
| Khi context đóng | Destroy callback throw | Shutdown/cleanup failure |

### 13.1. Runtime method exception không tự biến thành BeanCreationException

Ví dụ:

```java
@Service
public class OrderService {

    public void submit() {
        throw new IllegalStateException("Order rejected");
    }
}
```

Nếu `submit()` chỉ được gọi sau khi context đã tạo thành công, exception thường là lỗi thực thi method, không phải lỗi tạo bean.

### 13.2. Lazy bean có thể làm lỗi xuất hiện muộn

Với:

```java
@Lazy
@Component
public class ReportEngine {

    public ReportEngine() {
        throw new IllegalStateException("Invalid report engine");
    }
}
```

Spring có thể trì hoãn việc tạo bean cho đến khi có nơi yêu cầu. Ứng dụng có thể khởi động thành công rồi mới thất bại khi bean được resolve lần đầu.

Điều này không biến constructor lỗi thành runtime method error; nó chỉ thay đổi thời điểm bean creation xảy ra.

### 13.3. Lazy initialization có thể che lỗi khỏi startup smoke test

Nếu một deployment chỉ kiểm tra startup log, những bean lazy chưa được tạo có thể chưa phát hiện lỗi constructor/init.

Nếu một bean cốt lõi phải hợp lệ trước khi nhận traffic, cân nhắc không lazy hóa nó hoặc có readiness/warm-up check chủ động resolve và kiểm tra bean cần thiết.

Không ép khởi tạo mọi bean chỉ để một health check trở nên nặng nề; chọn đúng thành phần bắt buộc.

## 14. Đọc stack trace có hệ thống

Khi gặp:

```text
Application run failed
  BeanCreationException: Error creating bean with name 'checkoutController'
    UnsatisfiedDependencyException:
      Error creating bean with name 'checkoutService'
        BeanCreationException:
          Error creating bean with name 'paymentGateway'
            IllegalStateException: Missing provider endpoint
```

Thực hiện:

### Bước 1 — Tìm exception cuối cùng có message cụ thể

Ở đây:

```text
IllegalStateException: Missing provider endpoint
```

### Bước 2 — Xác định bean sở hữu lỗi

Ở đây:

```text
paymentGateway
```

### Bước 3 — Xác định phase

Nếu stack dẫn tới constructor hoặc factory method, kiểm tra instantiate. Nếu dẫn tới `@PostConstruct` hoặc `afterPropertiesSet`, kiểm tra init callback.

### Bước 4 — Kiểm tra nguồn dữ liệu/configuration

Property endpoint có được nạp không? Profile có đúng không? Environment variable có tên phù hợp không? Có source nào override không?

### Bước 5 — Kiểm tra dependency graph

Bean nào đang yêu cầu `paymentGateway`? Có một bean khác cũng thất bại trước nó không?

### Bước 6 — Sửa nguyên nhân gốc

Không sửa `checkoutController` nếu controller chỉ là bean phía trên trong dependency chain.

### Bước 7 — Chạy lại một phép kiểm tra nhỏ

Tạo context test tối thiểu cho configuration/bean đang lỗi, hoặc integration test phù hợp. Không cần chạy cả hệ thống nếu có thể cô lập failure.

## 15. Một ví dụ đầy đủ: constructor thất bại do property thiếu

### 15.1. Interface và client

```java
public interface PartnerGateway {
    void submit(String operationRef);
}
```

```java
@Component
public class HttpPartnerGateway implements PartnerGateway {

    private final URI endpoint;

    public HttpPartnerGateway(
            @Value("${partner.endpoint}") URI endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public void submit(String operationRef) {
        // Gọi đối tác bằng HTTP client phù hợp
    }
}
```

Nếu `partner.endpoint` không có trong Environment hoặc không convert được sang `URI`, Spring có thể thất bại khi resolve constructor argument.

### 15.2. Service phụ thuộc gateway

```java
@Service
public class PartnerSubmissionService {

    private final PartnerGateway gateway;

    public PartnerSubmissionService(PartnerGateway gateway) {
        this.gateway = gateway;
    }
}
```

Khi gateway không tạo được, service này cũng không tạo được. Những bean phía trên tiếp tục thất bại theo dependency chain.

### 15.3. Cấu hình đúng

`application.yml`:

```yaml
partner:
  endpoint: "https://partner.example.test/api"
```

Hoặc truyền từ command line:

```bash
java -jar app.jar --partner.endpoint=https://partner.example.test/api
```

Hoặc environment variable theo relaxed binding phù hợp:

```text
PARTNER_ENDPOINT=https://partner.example.test/api
```

### 15.4. Không đưa secret vào lỗi

Nếu endpoint có credential hoặc token trong URL, không đưa nguyên URI vào exception message:

```java
throw new IllegalStateException(
        "Cannot connect to " + endpoint
);
```

Thay bằng thông tin an toàn:

```java
throw new IllegalStateException(
        "Partner endpoint configuration is invalid"
);
```

Nếu cần chẩn đoán, log một provider identifier đã được chuẩn hóa và failure code, không in token hoặc URL có secret.

## 16. Một ví dụ đầy đủ: `@PostConstruct` thất bại khi preload dữ liệu

Giả sử service cần bảng mã tiền tệ:

```java
@Service
public class CurrencyService {

    private final CurrencyRepository repository;
    private Map<String, Currency> currencies;

    public CurrencyService(CurrencyRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void initialize() {
        currencies = repository.findAll()
                .stream()
                .collect(Collectors.toUnmodifiableMap(
                        Currency::code,
                        Function.identity()
                ));
    }
}
```

Một số nguyên nhân khiến init fail:

- Database không kết nối được.
- Schema chưa được migrate.
- Repository query ném exception.
- Hai currency có cùng code làm collector ném lỗi duplicate key.
- Mapping trả về code null.
- Dataset lớn khiến memory hoặc thời gian startup vượt giới hạn.

### 16.1. Tách nguyên nhân kỹ thuật khỏi logic preload

Nếu bảng currency là dữ liệu bắt buộc, hãy xác định rõ:

- Có cần preload toàn bộ không?
- Có thể query theo demand không?
- Có cần kiểm tra duplicate key trước khi publish map?
- Startup có nên fail nếu dataset rỗng?
- Có timeout database phù hợp?

### 16.2. Tránh trạng thái object nửa khởi tạo

Không gán field dùng chung từng phần trước khi preload hoàn tất. Có thể xây dựng biến local:

```java
@PostConstruct
void initialize() {
    Map<String, Currency> loaded =
            repository.findAll()
                    .stream()
                    .collect(Collectors.toUnmodifiableMap(
                            Currency::code,
                            Function.identity()
                    ));

    this.currencies = loaded;
}
```

Chỉ publish kết quả sau khi phép tạo map thành công. Nếu method ném exception, bean không được expose như một instance đã khởi tạo hoàn chỉnh.

### 16.3. Khi nào preload nên là một runner?

Nếu preload là một bước startup lớn, cần log tiến độ hoặc điều khiển readiness, một `ApplicationRunner`/startup coordinator có thể phù hợp hơn `@PostConstruct`.

Nhưng runner chạy sau context refresh; các bean có thể đã được tạo và injection hoàn tất. Nếu dữ liệu bắt buộc để phục vụ request, phải ngăn traffic cho đến khi runner hoàn tất và readiness chuyển đúng trạng thái.

## 17. Kiểm tra component scan và bean registration

Một bean không được tìm thấy có thể không phải do constructor của nó lỗi.

### 17.1. `@SpringBootApplication`

Annotation này kết hợp nhiều chức năng, trong đó có component scanning từ package chứa application class.

Ví dụ:

```java
package com.example;

@SpringBootApplication
public class Application {
}
```

Các package con như `com.example.order` và `com.example.payment` thường nằm trong phạm vi scan mặc định.

### 17.2. Bean khai báo bằng `@Bean`

```java
@Configuration
public class GatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new PartnerPaymentGateway();
    }
}
```

Nếu configuration class không được scan hoặc import, factory method không được đăng ký.

### 17.3. Dùng `@Import` khi module cần được đăng ký rõ

```java
@Configuration
@Import(PaymentConfiguration.class)
public class ApplicationModules {
}
```

Đây là một cách thể hiện module configuration tường minh.

### 17.4. Điều tra điều kiện auto-configuration

Nếu bean được cung cấp bởi Spring Boot auto-configuration hoặc starter:

- Dependency starter có trên runtime classpath không?
- Auto-configuration có được exclude không?
- Property condition có khớp không?
- Có bean người dùng khiến auto-configuration back off không?

Chạy:

```bash
java -jar app.jar --debug
```

để xem Conditions Evaluation Report trong những trường hợp phù hợp. Report giúp giải thích auto-configuration conditions; nó không thay thế việc đọc root cause của `BeanCreationException`.

## 18. Dependency graph: tìm bean đầu tiên hỏng

Một lỗi ở bean cuối graph có thể làm nhiều bean phía trên thất bại.

Ví dụ:

```text
OrderController
      |
      v
CheckoutService
   /       \
  v         v
Payment   Inventory
Gateway   Client
  |
  v
PaymentProperties
  |
  v
Invalid endpoint
```

Nếu `PaymentProperties` bind thất bại:

- `PaymentGateway` không tạo được.
- `CheckoutService` không thể inject gateway.
- `OrderController` không thể inject checkout service.

Spring có thể báo một hoặc nhiều exception ở những tầng khác nhau. Sửa controller không giải quyết vấn đề.

### 18.1. Xác định bean root

Một cách đọc stack:

```text
Error creating bean with name 'orderController'
  ...
Caused by: Error creating bean with name 'checkoutService'
  ...
Caused by: Error creating bean with name 'paymentGateway'
  ...
Caused by: Failed to bind properties under 'payment.endpoint'
```

Hãy kiểm tra `payment.endpoint` trước.

### 18.2. Bean tạo thành công không đồng nghĩa dependency runtime khỏe

Một constructor có thể tạo HTTP client object mà chưa mở connection. Context khởi động thành công, nhưng lần gọi API đầu tiên có thể timeout.

Đây là runtime dependency failure, không phải lỗi bean creation. Nếu kết nối cần xác nhận trước khi nhận traffic, hãy thêm bước validation/readiness riêng.

## 19. Optional bean và condition theo môi trường

Một integration chỉ được sử dụng ở production có thể được cấu hình theo profile:

```java
@Configuration
@Profile("production")
public class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
```

Trong môi trường test, có thể cung cấp implementation giả:

```java
@TestConfiguration
public class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

Nếu profile và test configuration không khớp, dependency có thể thiếu.

### 19.1. Tránh cấu hình test lọt vào production

Không để test implementation trong package được component scan production nếu không có condition rõ. Dùng `@TestConfiguration` trong test source set và import theo nhu cầu.

### 19.2. Condition theo property

`@ConditionalOnProperty` phù hợp cho feature/integration có thể bật tắt bằng config. Nhưng service phụ thuộc bắt buộc phải được thiết kế tương thích với trạng thái condition.

Có thể:

- Có một implementation mặc định.
- Dùng optional abstraction thật sự.
- Chỉ load service trong profile có gateway.
- Fail startup rõ ràng khi môi trường yêu cầu gateway nhưng config thiếu.

## 20. Đừng che `BeanCreationException` bằng catch quá rộng

Không nên:

```java
try {
    SpringApplication.run(Application.class, args);
} catch (Exception ex) {
    System.out.println("Application started");
}
```

Code này báo thành công ngay cả khi context startup thất bại.

### 20.1. Nếu cần custom exit behavior

```java
public static void main(String[] args) {
    try {
        SpringApplication.run(Application.class, args);
    } catch (Exception ex) {
        // Log một thông điệp startup failure phù hợp
        throw ex;
    }
}
```

Thông thường, để exception propagate cho launcher/process supervisor xử lý sẽ giữ đúng failure semantics.

Nếu cần exit code có cấu trúc cho batch app, hãy dùng `ExitCodeGenerator` hoặc `SpringApplication.exit(...)` sau khi context được tạo phù hợp. Không biến startup failure thành exit code 0.

### 20.2. Không log cùng stack trace ở mọi tầng

Nếu một exception được log rồi rethrow ở nhiều lớp, có thể xuất hiện nhiều stack trace trùng nhau. Hãy chọn một ranh giới chịu trách nhiệm ghi lỗi đầy đủ, còn các lớp khác bổ sung context an toàn hoặc để exception propagate.

## 21. Chẩn đoán startup failure với Spring Boot

### 21.1. Đọc đầy đủ log khởi động

Đừng chỉ copy 3 dòng cuối. Lỗi đầu tiên có thể xuất hiện trước những exception wrapper ở cuối.

Ghi nhận:

- Profile active.
- Bean name.
- Constructor/factory/init method.
- Property key có vấn đề.
- `Caused by` chain.
- Dòng code đầu tiên thuộc ứng dụng.

### 21.2. Dùng `--debug` khi cần điều tra auto-configuration

```bash
java -jar app.jar --debug
```

Spring Boot in Conditions Evaluation Report giúp xác định auto-configuration nào match hoặc không match.

Nó đặc biệt hữu ích khi bean đến từ starter, conditional configuration hoặc auto-configuration.

### 21.3. Không dump mọi property source

`Environment` có thể chứa password, token hoặc endpoint có credential. Không in toàn bộ `Environment`, `System.getProperties()` hoặc config object nhạy cảm để tìm một property bị thiếu.

Hãy kiểm tra đúng key không nhạy cảm:

```java
log.info(
        "payment configuration present={}",
        environment.containsProperty("payment.endpoint")
);
```

Nếu cần log giá trị, chỉ log khi đã xác nhận đó là giá trị không nhạy cảm và được phép xuất hiện trong log.

### 21.4. Actuator conditions và config props

Trong môi trường đã được bảo vệ, Actuator có thể cung cấp endpoint chẩn đoán như:

```text
/actuator/conditions
/actuator/configprops
```

Endpoint cụ thể phụ thuộc Actuator version và exposure configuration. Chúng không phải công cụ để public thông tin cấu hình ra Internet.

### 21.5. Không dùng health endpoint làm cách xem root cause startup

Nếu context không khởi động thành công, health endpoint thường cũng không thể phục vụ như một ứng dụng đã sẵn sàng. Hãy xem process logs, exit code, container events và startup exception.

## 22. Kiểm thử bean creation có kiểm soát

Khi một bean fail lúc startup, có thể cô lập bằng test context nhỏ thay vì luôn khởi động toàn bộ ứng dụng.

### 22.1. Test constructor injection

```java
class CheckoutServiceTest {

    @Test
    void createsServiceWithPaymentGateway() {
        PaymentGateway gateway = mock(PaymentGateway.class);

        CheckoutService service =
                new CheckoutService(gateway);

        assertThat(service).isNotNull();
    }
}
```

Unit test này kiểm tra constructor thuần Java. Nó không chứng minh Spring component scan hoặc bean registration đúng.

### 22.2. Test Spring context tối thiểu

```java
class PaymentConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(PaymentConfiguration.class);

    @Test
    void createsGatewayWhenPropertyIsPresent() {
        contextRunner
                .withPropertyValues(
                        "payment.provider=partner",
                        "payment.endpoint=https://partner.example.test"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(PaymentGateway.class);
                });
    }
}
```

Ví dụ giả định `PaymentConfiguration` khai báo bean theo các property trên và có dependency test phù hợp.

`ApplicationContextRunner` rất hữu ích cho việc kiểm thử conditional auto-configuration hoặc một nhóm bean nhỏ.

### 22.3. Test property binding

Kiểm tra:

- Giá trị hợp lệ bind thành công.
- Giá trị sai kiểu làm context startup fail.
- Validation constraint được thực thi.
- Default value chỉ được dùng ở nơi thật sự cho phép.

### 22.4. Test init callback

Tạo một bean test có `@PostConstruct`, cho nó nhận dependency giả lập rồi xác nhận callback được gọi trong context.

Nếu callback throw, assert rằng context runner ghi nhận failure thay vì application được xem là khởi động thành công.

### 22.5. Test circular dependency

Không cần viết một integration test rất lớn. Tạo hai bean constructor phụ thuộc lẫn nhau trong một context nhỏ và xác nhận startup failure. Sau đó tách orchestration thành bean thứ ba và xác nhận context khởi động được.

## 23. Tình huống thực tế và hướng xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `No qualifying bean` | Bean không được scan/import/condition | Kiểm tra package, configuration, profile |
| `expected single matching bean but found 2` | Có nhiều implementation | `@Qualifier`, `@Primary` hoặc router |
| `BeanInstantiationException` | Constructor/factory method throw | Xem cause và code tạo object |
| `Failed to bind properties` | Sai kiểu hoặc thiếu property | Kiểm tra nguồn config và typed binding |
| `@PostConstruct` thất bại | Preload/validation/resource operation lỗi | Tách init, timeout, xác định dữ liệu bắt buộc |
| `BeanCurrentlyInCreationException` | Circular dependency | Thiết kế lại dependency graph |
| Chỉ lỗi ở profile prod | Bean profile hoặc config source khác | Xác nhận active profiles và conditions |
| Chỉ lỗi khi lazy bean được dùng | Bean tạo trễ | Resolve/test bean trước traffic nếu là critical |
| CGLIB proxy không tạo được | Final class/method hoặc type constraint | Xem lại proxy strategy và class design |
| Factory method ném exception | Resource/configuration không hợp lệ | Kiểm tra method và arguments |
| Context fail sau khi `Started ...` log | Runner hoặc lifecycle step sau log thất bại | Xem runner failure và ready event |
| App khởi động nhưng request đầu tiên fail | Dependency được tạo lazy hoặc lỗi runtime | Kiểm tra thời điểm resolve và request trace |

## 24. Quy trình xử lý `BeanCreationException`

Một quy trình có thể áp dụng:

```text
Application startup failed
          |
          v
Tìm bean name đầu tiên được báo lỗi
          |
          v
Đọc toàn bộ Caused by chain
          |
          v
Xác định lifecycle phase
          |
          +--> Constructor / factory method
          |
          +--> Dependency resolution
          |
          +--> Property binding
          |
          +--> Init callback / post-processor
          |
          v
Tìm nguyên nhân gốc trong code/config/dependency
          |
          v
Sửa đúng nguyên nhân
          |
          v
Viết test tái hiện nhỏ
          |
          v
Khởi động lại và xác nhận context ready
```

### Bước 1 — Thu thập đúng lỗi

Lấy đầy đủ stack trace từ lần startup thất bại, bao gồm các `Caused by` và log trước đó có liên quan.

### Bước 2 — Tìm bean root

Phân biệt bean đầu tiên Spring báo và bean sâu hơn thực sự thất bại.

### Bước 3 — Phân loại phase

Constructor, dependency resolution, property binding, initialization callback, post-processor hay factory method?

### Bước 4 — Kiểm tra cấu hình và dependency graph

Kiểm tra profile, conditions, component scan, qualifier, primary và property sources.

### Bước 5 — Sửa nguyên nhân gốc

Không thêm `@Lazy`, optional injection hoặc catch exception nếu điều đó chỉ trì hoãn/che lỗi.

### Bước 6 — Tái hiện trong test nhỏ

Dùng unit test cho logic thuần, `ApplicationContextRunner` cho configuration nhỏ hoặc `@SpringBootTest` cho integration cần toàn bộ context.

### Bước 7 — Xác nhận startup thành công

Kiểm tra context refresh, runner, ready event và health/readiness theo yêu cầu triển khai. Một dòng `Started ...` đơn lẻ chưa phải bằng chứng đủ nếu runner phía sau có thể thất bại.

## 25. Các anti-pattern nên tránh

### 25.1. Constructor làm I/O không giới hạn

Constructor gọi HTTP, tải file lớn, query toàn bộ bảng hoặc chờ queue vô hạn làm startup khó dự đoán.

### 25.2. `@PostConstruct` chạy worker vô hạn

Một init method không trả về sẽ ngăn context hoàn tất refresh.

### 25.3. Catch rồi bỏ qua exception

```java
@PostConstruct
void init() {
    try {
        connect();
    } catch (Exception ex) {
        // Ignore
    }
}
```

Bean có thể được đánh dấu khởi tạo xong dù trạng thái nội bộ không hợp lệ. Nếu lỗi có thể phục hồi, hãy thể hiện trạng thái và readiness; nếu lỗi khiến bean không dùng được, fail startup rõ ràng.

### 25.4. Dùng `@Lazy` để che mọi lỗi

Lazy initialization chỉ đổi thời điểm tạo bean. Nó không sửa constructor, property hoặc dependency bị lỗi.

### 25.5. Dùng `@Autowired(required=false)` cho dependency bắt buộc

Điều này có thể tạo object thiếu collaborator và gây `NullPointerException` sau startup.

### 25.6. Bật circular references để tránh refactor

Có thể làm ứng dụng khởi động trong một số trường hợp, nhưng giữ dependency graph khó hiểu và dễ gặp lỗi khi proxy/post-processor thay đổi.

### 25.7. In toàn bộ configuration để debug

Có nguy cơ làm lộ password, token và connection string. Kiểm tra từng property an toàn.

### 25.8. Sửa bean phía trên thay vì bean root

Controller không phải nguyên nhân nếu payment gateway phía dưới thiếu endpoint.

## 26. Bài tập thực hành

### Bài 1 — Đọc exception chain

Cho:

```text
BeanCreationException: Error creating bean with name 'orderController'
  Caused by: UnsatisfiedDependencyException:
    Error creating bean with name 'orderService'
      Caused by: BeanCreationException:
        Error creating bean with name 'paymentGateway'
          Caused by: IllegalStateException:
            Missing payment endpoint
```

Hãy xác định:

- Bean nào đầu tiên được báo ở ngoài?
- Bean nào là nguồn lỗi gần nhất?
- Root cause là gì?
- Cấu hình hoặc code nào cần kiểm tra?

### Bài 2 — Constructor dependency thiếu

Tạo `OrderService` cần `PaymentGateway` nhưng không đăng ký implementation.

Khởi động context và quan sát lỗi. Sau đó thêm implementation bằng `@Component` hoặc `@Bean`.

Giải thích vì sao constructor không được gọi thành công trước khi dependency được resolve.

### Bài 3 — Nhiều bean cùng kiểu

Tạo `CardPaymentGateway` và `WalletPaymentGateway` cùng implement `PaymentGateway`.

Inject interface mà không qualifier. Quan sát ambiguity error, rồi thử `@Primary` và `@Qualifier`.

### Bài 4 — Component scan

Đặt implementation trong package sibling ngoài package của application class.

Quan sát `NoSuchBeanDefinitionException`, rồi sửa package layout hoặc `scanBasePackages`.

### Bài 5 — Profile và condition

Đăng ký một gateway bằng `@Profile("production")` và một gateway bằng `@ConditionalOnProperty`.

Chạy với profile/property khác nhau. Ghi lại bean nào tồn tại và khi nào constructor consumer không resolve được dependency.

### Bài 6 — Constructor ném exception

Tạo một bean constructor validate endpoint và ném exception nếu endpoint sai.

Kiểm tra cause chain. Sau đó chuyển validation sang một configuration properties object có `@Validated` để startup message cụ thể hơn.

### Bài 7 — `@PostConstruct`

Tạo bean load một danh sách dữ liệu trong `@PostConstruct`. Cho repository giả lập ném exception.

Quan sát context startup fail. Sau đó kiểm tra cách tách preload sang runner và readiness gate nếu dữ liệu được tải bất đồng bộ.

### Bài 8 — Custom init method

Tạo class có `initialize()` và khai báo:

```java
@Bean(initMethod = "initialize")
```

Cho init method throw. Xác định exception nào được bọc ở tầng Spring và bean nào không được expose.

### Bài 9 — `InitializingBean`

Implement `afterPropertiesSet()` và cố ý ném exception. So sánh với `@PostConstruct`.

### Bài 10 — Property binding sai kiểu

Tạo `@ConfigurationProperties` với `Duration`, `URI`, `int`. Truyền giá trị không hợp lệ và quan sát binding exception.

Sau đó thêm validation constraints để lỗi config được phát hiện sớm.

### Bài 11 — Circular constructor injection

Tạo `OrderService -> PaymentService -> OrderService`.

Quan sát circular dependency failure. Tách workflow orchestration thành bean thứ ba và kiểm tra context khởi động thành công.

### Bài 12 — Optional dependency

Tạo một gateway tùy chọn và thử `ObjectProvider`, `Optional` và `@Autowired(required=false)`.

Phân tích cách mỗi lựa chọn thể hiện trạng thái vắng mặt và rủi ro nếu dependency thực tế là bắt buộc.

### Bài 13 — Lazy bean

Đánh dấu một bean là `@Lazy` và cho constructor throw.

Quan sát context có thể khởi động trước khi bean được yêu cầu. Sau đó gọi bean và ghi nhận thời điểm lỗi xuất hiện.

### Bài 14 — Factory method

Tạo một `@Bean` method kiểm tra cấu hình endpoint rồi ném exception khi thiếu.

Đọc stack trace và xác định factory method nào thất bại.

### Bài 15 — BeanPostProcessor

Viết một `BeanPostProcessor` nhỏ áp dụng cho một bean cụ thể. Cố ý ném exception trong callback để quan sát bean creation failure.

Giải thích vì sao custom post-processor cần hạn chế side effects và tránh resolve dependency quá sớm.

### Bài 16 — Test context tối thiểu

Dùng `ApplicationContextRunner` để:

- Kiểm tra property condition.
- Kiểm tra bean tồn tại/không tồn tại.
- Kiểm tra binding.
- Kiểm tra context startup failure khi dependency thiếu.

### Bài 17 — Startup log và ready event

Tạo `ApplicationRunner` ném exception. Quan sát startup logs, `ApplicationStartedEvent` và `ApplicationReadyEvent`.

Giải thích vì sao log `Started ...` có thể xuất hiện trước khi runner thất bại.

### Bài 18 — Thiết kế startup validation

Một service cần database và một API đối tác. Phân loại:

- Điều kiện nào bắt buộc để tạo bean?
- Điều kiện nào cần xác nhận trước readiness?
- Điều kiện nào chỉ cần retry khi xử lý request?
- Timeout và failure policy của mỗi điều kiện là gì?

Tránh đưa mọi remote call vào constructor hoặc `@PostConstruct`.

## 27. Ghi nhớ

`BeanCreationException` cho biết Spring không thể hoàn tất việc tạo một bean, nhưng **nguyên nhân gốc có thể nằm sâu trong dependency graph**. Hãy đọc toàn bộ `Caused by` chain, xác định bean đầu tiên thực sự thất bại và phân loại lifecycle phase: resolve dependency, instantiate, populate property, initialization callback hay bean post-processing.

Constructor nên tập trung nhận và lưu dependency. `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom init method phù hợp với khởi tạo ngắn, đồng bộ và có giới hạn. Remote I/O, preload lớn hoặc background work cần lifecycle, timeout và readiness policy riêng.

Nếu thiếu bean, kiểm tra component scan, `@Bean`, profile và conditions. Nếu có nhiều bean, dùng qualifier/primary hoặc router phù hợp. Nếu property binding lỗi, kiểm tra nguồn cấu hình và kiểu dữ liệu. Nếu circular dependency xuất hiện, thiết kế lại dependency graph thay vì mặc định bật circular references hoặc thêm `@Lazy` để che vấn đề.

Sau khi sửa, hãy tái hiện bằng unit test hoặc context test nhỏ, rồi xác nhận toàn bộ startup lifecycle hoàn tất. **Một ứng dụng chỉ được xem là khởi động thành công khi context, các runner bắt buộc và những điều kiện sẵn sàng theo hợp đồng đều hoàn tất**, không chỉ vì một dòng log đã được in ra.
# BeanCreationException do constructor, init hoặc dependency thất bại

Khi Spring Boot khởi động, Spring phải tạo một tập hợp bean và nối chúng thành một object graph. Controller cần service, service cần repository, repository cần DataSource, còn DataSource cần URL, driver và credential hợp lệ. Chỉ cần một mắt xích không thể được khởi tạo, quá trình tạo bean phía trên có thể thất bại theo dây chuyền.

Một lỗi thường thấy trong log:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService':
Invocation of init method failed
~~~

Thông báo này cho biết Spring không thể hoàn tất việc tạo bean `orderService`. Nó **chưa đủ để kết luận nguyên nhân gốc**. Lỗi thật có thể nằm ở constructor ném exception, dependency không tồn tại, hai bean cùng phù hợp, property không bind được, method khởi tạo thất bại hoặc một bean thấp hơn trong dependency graph không thể được tạo.

**`BeanCreationException` là exception thuộc Spring container, thường mô tả việc tạo bean thất bại.** Nó có thể bao bọc một exception cụ thể hơn và chứa thông tin về bean, resource hoặc dependency liên quan. Khi chẩn đoán, phải đi từ bean được nhắc tới trong message, lần theo chuỗi dependency và tìm **root cause** sâu nhất có ý nghĩa.

Bài học giải thích vòng đời tạo bean, constructor injection, dependency resolution, các callback khởi tạo, exception wrapping, circular dependencies, cấu hình và property binding, cùng một quy trình điều tra có thể áp dụng cho ứng dụng Spring Boot thực tế.

## 1. BeanCreationException là gì?

`BeanCreationException` nằm trong package:

~~~java
org.springframework.beans.factory.BeanCreationException
~~~

Đây là một loại `BeansException` được Spring dùng khi không thể tạo một bean theo bean definition đã đăng ký.

Ví dụ:

~~~java
@Service
public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }
}
~~~

Nếu Spring không tìm được bean phù hợp với `PaymentClient`, quá trình tạo `OrderService` không thể hoàn tất. Spring có thể báo `UnsatisfiedDependencyException` hoặc `NoSuchBeanDefinitionException` ở chuỗi nguyên nhân, sau đó lỗi được phản ánh trong exception container ở tầng trên.

Một ví dụ khác:

~~~java
@Component
public class CacheInitializer {

    @PostConstruct
    void initialize() {
        throw new IllegalStateException("Cache configuration is invalid");
    }
}
~~~

Bean có thể được instantiate và inject dependency thành công, nhưng callback `@PostConstruct` ném exception. Spring không thể hoàn tất initialization, vì vậy bean creation thất bại và exception được bọc trong lỗi của container.

### BeanCreationException không phải lúc nào cũng là lỗi ở class được nêu đầu tiên

Giả sử log:

~~~text
Error creating bean with name 'orderController'
  Unsatisfied dependency expressed through constructor parameter 0
  Error creating bean with name 'orderService'
    Error creating bean with name 'paymentClient'
      Failed to bind properties
        Invalid URL: "ht!tp://..."
~~~

Có thể đọc chuỗi như sau:

1. Spring đang tạo `orderController`.
2. Controller cần `orderService` nhưng dependency đó chưa sẵn sàng.
3. Spring thử tạo `orderService`.
4. Service cần `paymentClient`.
5. Việc tạo client thất bại vì property URL không hợp lệ.

Bean đầu tiên xuất hiện trong log thường chỉ là **nơi lỗi được phát hiện qua dependency chain**, không nhất thiết là nơi có bug.

## 2. Vòng đời tạo bean và vị trí có thể phát sinh lỗi

Với một singleton bean thông thường, quá trình khái quát gồm những bước:

~~~text
Spring cần bean
      |
      v
Tìm BeanDefinition
      |
      v
Chọn constructor / factory method
      |
      v
Instantiate object
      |
      v
Inject dependencies và populate properties
      |
      v
Aware callbacks
      |
      v
BeanPostProcessor: before initialization
      |
      v
Initialization callbacks
  - @PostConstruct
  - InitializingBean.afterPropertiesSet()
  - custom init method
      |
      v
BeanPostProcessor: after initialization
      |
      v
Bean sẵn sàng cho caller
~~~

Đây là luồng khái quát. Extension points đặc biệt, scoped beans, FactoryBeans và proxy creation có thể bổ sung hoặc thay đổi những chi tiết của quy trình.

| Giai đoạn | Ví dụ lỗi |
|---|---|
| Đọc bean definition | Class không tồn tại, cấu hình không hợp lệ |
| Resolve constructor | Không tìm được constructor phù hợp |
| Resolve dependency | Thiếu bean, nhiều bean cùng kiểu |
| Instantiate | Constructor ném exception |
| Populate properties | Setter/field injection hoặc type conversion thất bại |
| Aware callbacks | Callback ném exception |
| Before-init processor | BeanPostProcessor thất bại |
| Initialization | `@PostConstruct` hoặc `afterPropertiesSet()` ném exception |
| Custom init method | Method khai báo qua `@Bean(initMethod=...)` thất bại |
| After-init processor | Proxy/processor không tạo được bean cuối cùng |
| FactoryBean | Tạo factory hoặc lấy object do factory cung cấp thất bại |

### Phân biệt instantiate và initialize

- **Instantiate:** tạo object Java, thường bằng constructor hoặc factory method.
- **Populate:** gắn dependency và property cần thiết.
- **Initialize:** chạy callback và xử lý trước khi bean được sử dụng bình thường.

Constructor chạy thành công không bảo đảm bean sẽ khởi tạo thành công. Dependency injection hoàn tất cũng không bảo đảm `@PostConstruct` không thất bại.

## 3. Đọc exception chain thay vì chỉ đọc dòng đầu

Một stack trace Spring thường có nhiều lớp exception. Ví dụ:

~~~text
org.springframework.beans.factory.BeanCreationException:
Error creating bean with name 'orderService':
Could not autowire field: private PaymentClient paymentClient

Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
No qualifying bean of type 'PaymentClient' available
~~~

Thông tin cần lấy:

- **Bean đang được tạo:** `orderService`.
- **Vị trí phụ thuộc:** field `paymentClient`.
- **Loại nguyên nhân:** `NoSuchBeanDefinitionException`.
- **Ý nghĩa:** context không có bean nào phù hợp với kiểu `PaymentClient` tại thời điểm resolve.

Một ví dụ khác:

~~~text
BeanCreationException:
Error creating bean with name 'cacheInitializer':
Invocation of init method failed

Caused by: IllegalStateException:
Cache endpoint must be configured
~~~

Ở đây dependency có thể đã được inject đầy đủ; nguyên nhân nằm trong logic khởi tạo.

### Cách tìm root cause trong IDE

1. Mở log từ đầu lần khởi động thất bại.
2. Tìm lần xuất hiện đầu tiên của `BeanCreationException`.
3. Đọc tên bean và mô tả thao tác Spring đang thực hiện.
4. Lần xuống từng `Caused by`.
5. Tìm exception cụ thể nhất có thông điệp liên quan trực tiếp tới lỗi.
6. Đối chiếu stack trace của exception đó với constructor, init callback hoặc dependency tương ứng.

Không nên chỉ copy dòng `Error creating bean with name ...` rồi sửa bean đó theo phỏng đoán.

### Root cause sâu nhất không phải lúc nào cũng là nguyên nhân hữu ích nhất

Một chuỗi lỗi có thể kết thúc bằng `NullPointerException` trong thư viện, nhưng nguyên nhân thiết kế nằm ở việc ứng dụng đã truyền cấu hình null. Cần đọc cả root cause và context nơi exception được phát sinh, không chỉ chọn exception nằm cuối stack trace.

## 4. Constructor injection thất bại

Constructor injection là cách phổ biến để thể hiện dependency bắt buộc:

~~~java
@Service
public class InvoiceService {

    private final InvoiceRepository repository;
    private final TaxCalculator taxCalculator;

    public InvoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator
    ) {
        this.repository = repository;
        this.taxCalculator = taxCalculator;
    }
}
~~~

Khi Spring tạo `InvoiceService`, nó phải tìm bean phù hợp với cả `InvoiceRepository` và `TaxCalculator`.

Nếu thiếu một dependency, constructor không thể được gọi. Spring có thể báo `UnsatisfiedDependencyException`, `NoSuchBeanDefinitionException` hoặc exception container được bọc ở tầng trên.

### Thiếu bean implementation

Interface:

~~~java
public interface TaxCalculator {
    BigDecimal calculate(BigDecimal amount);
}
~~~

Không có implementation được đăng ký:

~~~java
@Service
public class InvoiceService {

    public InvoiceService(TaxCalculator taxCalculator) {
        // ...
    }
}
~~~

Context không thể tạo `InvoiceService` nếu không có bean `TaxCalculator` phù hợp.

Cách xử lý là xác định implementation cần thiết và đăng ký đúng cách:

~~~java
@Component
public class StandardTaxCalculator implements TaxCalculator {

    @Override
    public BigDecimal calculate(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.10"));
    }
}
~~~

Hoặc đăng ký bean qua `@Configuration` và `@Bean` nếu implementation được tạo từ thư viện hoặc cần factory logic.

### Class có @Component nhưng vẫn không được tìm thấy

Một class có `@Component` chưa chắc được đăng ký. Kiểm tra:

- Package của class có nằm trong component scan không?
- Configuration class có được import không?
- Profile có đang loại bean đó không?
- Condition có match không?
- Bean có bị exclude bởi scan filter không?
- Class có thực sự nằm trong runtime classpath không?

Không nên thêm `@ComponentScan("com")` một cách rộng chỉ để làm mất lỗi. Scan quá rộng có thể kéo theo nhiều bean ngoài ý muốn và tạo xung đột mới.

## 5. Không có bean phù hợp: NoSuchBeanDefinitionException

`NoSuchBeanDefinitionException` thường xuất hiện khi Spring cần một bean theo type hoặc name nhưng không tìm thấy candidate.

Ví dụ:

~~~java
@Service
public class ReportService {

    private final ReportExporter exporter;

    public ReportService(ReportExporter exporter) {
        this.exporter = exporter;
    }
}
~~~

Nếu không có bean `ReportExporter`, context không thể tạo `ReportService`.

### Cách điều tra

1. Xác định type Spring đang tìm.
2. Tìm implementation trong project và dependencies.
3. Kiểm tra implementation có được đăng ký không.
4. Kiểm tra điều kiện profile/property/classpath.
5. Kiểm tra cấu hình có bị import/scan hay không.
6. Nếu dependency optional, quyết định bean cần được bỏ qua hay context phải fail.

### Optional dependency phải được thiết kế rõ

Nếu một integration thực sự tùy chọn, có thể dùng condition:

~~~java
@AutoConfiguration
@ConditionalOnClass(RemoteReportClient.class)
public class RemoteReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "reports.remote",
            name = "enabled",
            havingValue = "true"
    )
    ReportExporter remoteReportExporter(
            RemoteReportClient client
    ) {
        return new RemoteReportExporter(client);
    }
}
~~~

Các class trong ví dụ là thành phần minh họa. Khi thư viện tùy chọn vắng mặt, cấu hình tích hợp tương ứng không nên tạo bean phụ thuộc vào nó.

Nếu dependency là bắt buộc, không nên âm thầm bỏ qua lỗi rồi để ứng dụng chạy trong trạng thái thiếu chức năng.

## 6. Có nhiều bean cùng phù hợp: NoUniqueBeanDefinitionException

Một lỗi khác là Spring tìm được **nhiều hơn một candidate** cho dependency đơn.

Ví dụ:

~~~java
public interface PaymentGateway {
    void charge(BigDecimal amount);
}
~~~

Hai implementation:

~~~java
@Component
public class CardPaymentGateway implements PaymentGateway {
    @Override
    public void charge(BigDecimal amount) {
        // ...
    }
}
~~~

~~~java
@Component
public class WalletPaymentGateway implements PaymentGateway {
    @Override
    public void charge(BigDecimal amount) {
        // ...
    }
}
~~~

Consumer:

~~~java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway gateway) {
        // ...
    }
}
~~~

Spring có hai candidate nhưng constructor không nói rõ cần bean nào. Có thể gặp `NoUniqueBeanDefinitionException`, sau đó lỗi được phản ánh trong chuỗi tạo `CheckoutService`.

### Cách 1: @Primary

~~~java
@Component
@Primary
public class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

`@Primary` đánh dấu candidate ưu tiên khi injection theo type có nhiều lựa chọn phù hợp.

### Cách 2: @Qualifier

~~~java
@Service
public class CheckoutService {

    private final PaymentGateway gateway;

    public CheckoutService(
            @Qualifier("walletPaymentGateway")
            PaymentGateway gateway
    ) {
        this.gateway = gateway;
    }
}
~~~

`@Qualifier` chỉ rõ candidate cần dùng. Đây là lựa chọn phù hợp khi một consumer có yêu cầu cụ thể.

### Cách 3: inject tất cả implementations

Nếu nghiệp vụ thực sự cần lựa chọn nhiều strategy, có thể inject collection:

~~~java
@Service
public class PaymentRouter {

    private final Map<String, PaymentGateway> gateways;

    public PaymentRouter(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }
}
~~~

Khi đó service chịu trách nhiệm chọn implementation theo một quy tắc rõ ràng.

Không nên dùng `@Primary` chỉ để che một thiết kế có nhiều implementation nhưng không có policy lựa chọn phù hợp.

## 7. Constructor có nhiều lựa chọn và @Autowired

Spring cần quyết định constructor nào dùng để tạo bean.

Một class chỉ có một constructor thường không cần đặt `@Autowired`:

~~~java
@Service
public class SearchService {

    private final SearchRepository repository;

    public SearchService(SearchRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu có nhiều constructor, lựa chọn cần rõ ràng:

~~~java
@Component
public class ClientRegistry {

    private final RemoteClient client;

    @Autowired
    public ClientRegistry(RemoteClient client) {
        this.client = client;
    }

    public ClientRegistry() {
        this.client = new NoOpRemoteClient();
    }
}
~~~

Trong những trường hợp nhiều constructor có tham số và các mức required/optional khác nhau, quy tắc lựa chọn của Spring có thể phức tạp hơn. Hãy dùng annotation một cách tường minh và tránh tạo nhiều constructor có thể cùng được coi là candidate nhưng không có đủ dependency để resolve.

### Constructor ambiguity

Ví dụ:

~~~java
@Component
public class AmbiguousService {

    public AmbiguousService(FirstClient first) {
    }

    public AmbiguousService(SecondClient second) {
    }
}
~~~

Nếu không có chỉ dẫn constructor phù hợp, Spring có thể không biết phải chọn constructor nào.

Thiết kế dễ hiểu hơn là giữ một constructor dependency rõ ràng, hoặc đánh dấu constructor mong muốn theo contract của Spring.

### Lombok có thể tạo constructor mà developer không nhìn thấy trực tiếp

Ví dụ:

~~~java
@Service
@RequiredArgsConstructor
public class CustomerService {
    private final CustomerRepository repository;
    private final EmailSender emailSender;
}
~~~

`@RequiredArgsConstructor` tạo constructor cho các field final/required. Nếu class đồng thời khai báo constructor thủ công hoặc có annotation Lombok khác, cần kiểm tra code được generate để hiểu Spring đang nhìn thấy những constructor nào.

Khi log nói parameter index 1 không resolve được, có thể đối chiếu constructor thực tế sau annotation processing, không chỉ source code nhìn bằng mắt.

## 8. Dependency trong @Bean factory method

Không phải mọi bean đều được tạo bằng constructor của class có `@Component`. Một `@Bean` method cũng có thể nhận dependency:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    RemoteClient remoteClient(
            HttpClient httpClient,
            RemoteClientProperties properties
    ) {
        return new RemoteClient(
                httpClient,
                properties.endpoint()
        );
    }
}
~~~

Spring phải resolve các tham số của factory method trước khi gọi nó.

Nếu thiếu `HttpClient` hoặc `RemoteClientProperties`, việc tạo bean `remoteClient` thất bại. Log có thể nói lỗi ở factory method, nhưng nguyên nhân vẫn là dependency resolution.

### Factory method ném exception

~~~java
@Bean
RemoteClient remoteClient(RemoteClientProperties properties) {
    URI endpoint = properties.endpoint();

    if (endpoint == null) {
        throw new IllegalStateException(
                "Remote endpoint is required"
        );
    }

    return new RemoteClient(endpoint);
}
~~~

Ở đây dependency đã được resolve, nhưng factory method ném exception. Spring không thể hoàn tất bean creation.

### Đặt validation ở đúng boundary

Nếu endpoint là property bắt buộc, có thể dùng `@ConfigurationProperties` với validation để báo lỗi sớm và có thông điệp rõ hơn, thay vì chờ factory method ném một exception chung chung.

## 9. Constructor tự ném exception

Một constructor có thể thất bại vì logic bên trong:

~~~java
@Component
public class CertificateProvider {

    private final Certificate certificate;

    public CertificateProvider() {
        try {
            this.certificate = loadCertificate();
        } catch (IOException ex) {
            throw new IllegalStateException(
                    "Cannot load signing certificate",
                    ex
            );
        }
    }

    private Certificate loadCertificate() throws IOException {
        // Đọc file hoặc parse certificate.
        return CertificateFactory.getInstance("X.509")
                .generateCertificate(
                        new ByteArrayInputStream(new byte[0])
                );
    }
}
~~~

Ví dụ trên cố ý minh họa constructor có thể ném lỗi; dữ liệu certificate rỗng sẽ không phải certificate hợp lệ.

Spring thường bọc lỗi khởi tạo bằng exception mô tả bean, chẳng hạn `BeanInstantiationException` và `BeanCreationException` ở các tầng phù hợp.

### Constructor nên làm ít việc

Constructor nên chủ yếu nhận dependency và gán state bắt buộc:

~~~java
@Service
public class ReportService {

    private final ReportRepository repository;
    private final ReportFormatter formatter;

    public ReportService(
            ReportRepository repository,
            ReportFormatter formatter
    ) {
        this.repository = repository;
        this.formatter = formatter;
    }
}
~~~

Hạn chế gọi network, query database lớn, đọc file cấu hình phức tạp hoặc khởi chạy thread trong constructor. Những side effects này làm object khó tạo trong test, khó kiểm soát retry và có thể xảy ra trước khi container hoàn tất quản lý lifecycle.

Nếu một tài nguyên cần mở lúc khởi tạo, hãy dùng lifecycle rõ ràng và có cleanup tương ứng.

## 10. @PostConstruct thất bại

`@PostConstruct` là callback được gọi sau khi dependency injection và những bước chuẩn bị bean phù hợp đã hoàn tất, trước khi bean được đưa vào sử dụng bình thường.

Với Spring Boot 3/Spring Framework 6, import thường là:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Ví dụ:

~~~java
@Component
public class SearchIndexInitializer {

    private final SearchIndexClient client;

    public SearchIndexInitializer(SearchIndexClient client) {
        this.client = client;
    }

    @PostConstruct
    void initialize() {
        if (!client.isConfigured()) {
            throw new IllegalStateException(
                    "Search index client is not configured"
            );
        }
    }
}
~~~

Nếu `initialize()` ném exception, Spring không thể hoàn tất initialization của bean. Lỗi thường xuất hiện với thông tin tương tự:

~~~text
BeanCreationException:
Error creating bean with name 'searchIndexInitializer':
Invocation of init method failed
~~~

Root cause có thể là `IllegalStateException` do code ném ra.

### @PostConstruct không phải nơi phù hợp cho mọi tác vụ dài

Nếu callback gọi remote service hoặc tải hàng triệu record, ứng dụng có thể khởi động rất lâu hoặc fail hoàn toàn khi dịch vụ bên ngoài tạm thời không khả dụng.

Hãy quyết định rõ:

- Tài nguyên này có bắt buộc để service nhận request không?
- Có thể retry sau startup không?
- Cần timeout bao lâu?
- Có cần readiness ở trạng thái chưa sẵn sàng trong lúc warm-up không?
- Khi khởi tạo thất bại, có thể cleanup những resource đã mở không?

Không biến `@PostConstruct` thành một nơi thực hiện toàn bộ startup workflow nếu nhiệm vụ có lifecycle riêng.

## 11. InitializingBean.afterPropertiesSet() thất bại

Spring hỗ trợ interface:

~~~java
org.springframework.beans.factory.InitializingBean
~~~

Ví dụ:

~~~java
@Component
public class QueueConsumer implements InitializingBean {

    private final QueueClient queueClient;

    public QueueConsumer(QueueClient queueClient) {
        this.queueClient = queueClient;
    }

    @Override
    public void afterPropertiesSet() {
        if (!queueClient.isReady()) {
            throw new IllegalStateException(
                    "Queue client is not ready"
            );
        }
    }
}
~~~

`afterPropertiesSet()` được gọi trong giai đoạn initialization sau khi các dependency/property phù hợp đã được populate.

Nếu method ném exception, Spring coi bean initialization thất bại và có thể bọc lỗi trong `BeanCreationException`.

### @PostConstruct và InitializingBean có thể cùng tồn tại

Một bean có thể có nhiều loại initialization callback. Trong lifecycle thông thường, Spring gọi các callback theo thứ tự:

1. Method được đánh dấu `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method được khai báo trong bean definition, ví dụ `@Bean(initMethod = "initialize")`.

Sau đó các BeanPostProcessors sau-init có thể tiếp tục xử lý bean.

Không nên để nhiều callback cùng thực hiện một side effect không idempotent. Ví dụ nếu cả `@PostConstruct` và `afterPropertiesSet()` đều gửi một lệnh tạo resource bên ngoài, bạn có thể tạo trùng resource.

## 12. Custom init method qua @Bean(initMethod)

Một configuration có thể khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {

    @Bean(initMethod = "connect", destroyMethod = "close")
    StorageClient storageClient() {
        return new StorageClient();
    }
}
~~~

Class:

~~~java
public class StorageClient {

    public void connect() {
        // Mở connection hoặc chuẩn bị tài nguyên.
    }

    public void close() {
        // Giải phóng tài nguyên.
    }
}
~~~

Nếu `connect()` ném exception, việc tạo `storageClient` thất bại.

### Đọc đúng bean definition

Log có thể nêu:

~~~text
Invocation of init method failed
~~~

Khi đó, tìm:

- Bean được tạo bằng `@Bean` nào?
- Bean definition có `initMethod` không?
- Method init có tồn tại và có thể được gọi không?
- Method có ném exception nào?
- Tài nguyên nào đã được mở trước khi exception xảy ra?

Đừng mặc định mọi lỗi `init method failed` đều đến từ `@PostConstruct`. Custom init method có thể là nguồn lỗi.

## 13. Phân biệt ba kiểu init callback

| Cách | Cách khai báo | Điểm cần chú ý |
|---|---|---|
| `@PostConstruct` | Annotation trên method | Chuẩn Jakarta; callback do Spring lifecycle processor xử lý |
| `InitializingBean` | Implement `afterPropertiesSet()` | Bean phụ thuộc trực tiếp Spring API |
| `@Bean(initMethod = "...")` | Metadata trong bean definition | Phù hợp khi class do thư viện cung cấp hoặc không muốn sửa class |

Ví dụ cùng một bean có thể có:

~~~java
@Component
public class ResourceManager implements InitializingBean {

    @PostConstruct
    void prepare() {
        // Bước chuẩn bị đầu tiên.
    }

    @Override
    public void afterPropertiesSet() {
        // Bước sau khi properties đã được populate.
    }

    public void customStart() {
        // Có thể được cấu hình làm initMethod.
    }
}
~~~

Không nhất thiết phải dùng cả ba. Chọn một cách phù hợp với quyền kiểm soát class và convention của dự án.

### Spring Boot 2 và 3: namespace annotation

- Spring Boot 3 dựa trên Jakarta EE 9+ và thường dùng `jakarta.annotation.PostConstruct`.
- Spring Boot 2 cũ thường dùng `javax.annotation.PostConstruct`, tùy phiên bản/dependency.

Import sai namespace có thể khiến annotation không được nhận diện theo infrastructure đang có.

## 14. Dependency có tồn tại nhưng chính nó tạo thất bại

Giả sử:

~~~java
@Service
public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }
}
~~~

Bean `PaymentClient` có thể đã được đăng ký nhưng bản thân nó lại thất bại:

~~~java
@Component
public class PaymentClient {

    public PaymentClient(PaymentProperties properties) {
        if (properties.endpoint() == null) {
            throw new IllegalArgumentException(
                    "Payment endpoint is required"
            );
        }
    }
}
~~~

Chuỗi lỗi:

~~~text
OrderController
    |
    v
OrderService
    |
    v
PaymentClient
    |
    v
PaymentProperties / endpoint
    |
    v
IllegalArgumentException
~~~

Lúc này `OrderService` không phải bean cần sửa. Nó chỉ không thể được tạo vì dependency `PaymentClient` không hoàn tất.

### Nguyên tắc dependency chain

Nếu một bean A cần bean B và B không thể được tạo, lỗi A là **hệ quả**. Tìm bean đầu tiên trong chuỗi có một nguyên nhân cụ thể, chẳng hạn:

- Constructor exception.
- Init callback exception.
- Missing property.
- Conversion/binding failure.
- Dependency ambiguity.
- Circular reference.
- External resource failure.

Sửa đúng mắt xích đó thường làm toàn bộ chuỗi phía trên khởi động được.

## 15. @Value và property placeholder thất bại

Một bean có thể phụ thuộc property bằng `@Value` hoặc `Environment`. Ví dụ dùng Environment để thể hiện rõ điểm đọc cấu hình:

~~~java
@Component
public class PartnerClient {

    private final URI endpoint;

    public PartnerClient(Environment environment) {
        this.endpoint = URI.create(
                environment.getRequiredProperty("partner.api.endpoint")
        );
    }
}
~~~

Nếu `partner.api.endpoint` không tồn tại, `getRequiredProperty` ném lỗi vì property bắt buộc chưa được cung cấp. Trong cách dùng `@Value`, placeholder không có default cũng có thể gây lỗi resolve trong quá trình tạo bean.

Ví dụ cấu hình:

~~~yaml
partner:
  api:
    endpoint: https://partner.example.test
~~~

### Dùng default khi default thật sự hợp lệ

Với property tùy chọn như timeout, có thể cung cấp giá trị mặc định bằng `@Value` placeholder hoặc typed properties:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public class PartnerApiSettings {

    private Duration timeout = Duration.ofSeconds(3);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Nhưng không nên đặt default cho property bắt buộc như endpoint production chỉ để startup không fail. Một default sai có thể khiến ứng dụng kết nối nhầm môi trường hoặc chạy trong trạng thái không an toàn.

### Type conversion cũng có thể thất bại

~~~properties
partner.api.timeout=three-seconds
~~~

Nếu target type là `Duration` và converter không thể parse giá trị này, quá trình inject/bind có thể thất bại.

Khi điều tra, phân biệt:

- Property không tồn tại.
- Property có nhưng rỗng.
- Property có nhưng sai định dạng.
- Property bị nguồn khác ghi đè bằng giá trị sai.

## 16. @ConfigurationProperties binding và validation thất bại

Với cấu hình có nhiều trường, dùng typed properties:

~~~java
@ConfigurationProperties(prefix = "partner.api")
@Validated
public class PartnerApiProperties {

    @NotNull
    private URI endpoint;

    @Min(1)
    private int maxAttempts = 3;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
~~~

Đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` theo cấu trúc ứng dụng.

Nếu property không bind được hoặc vi phạm validation, context có thể thất bại trong quá trình tạo properties bean. Bean khác phụ thuộc properties đó sau đó cũng không tạo được.

### Ví dụ cấu hình không hợp lệ

~~~yaml
partner:
  api:
    endpoint: "not a uri"
    max-attempts: 0
~~~

Có thể phát sinh lỗi chuyển đổi URI hoặc lỗi constraint `@Min(1)`.

### Phân biệt bind failure và validation failure

- **Bind failure:** không chuyển được dữ liệu nguồn thành kiểu Java mong muốn.
- **Validation failure:** dữ liệu đã bind nhưng vi phạm constraint.
- **Bean creation failure phía sau:** service/client không thể tạo vì properties bean không hợp lệ.

Đọc root cause và tên property được nêu trong thông báo để biết lỗi thuộc nhóm nào.

### Không tắt validation chỉ để ứng dụng khởi động

Nếu property bảo vệ endpoint, timeout, pool size hoặc giới hạn tài nguyên, validation là một cơ chế fail-fast có giá trị. Hãy sửa cấu hình sai thay vì xóa constraint để che lỗi.

## 17. Lỗi chuyển đổi kiểu khi inject dependency

Ví dụ:

~~~java
@Component
public class RetryPolicy {

    public RetryPolicy(
            @Value("retry.max-attempts") int maxAttempts
    ) {
        // Minh họa kiểu dữ liệu nhận vào; cấu hình thực tế dùng placeholder.
    }
}
~~~

Nếu cấu hình:

~~~properties
retry.max-attempts=lots
~~~

Spring không thể chuyển chuỗi `lots` thành `int`. Bean creation thất bại ở quá trình resolve constructor argument/property.

Một thông báo lỗi có thể chứa tên property hoặc giá trị không chuyển đổi được. Hãy kiểm tra:

- Target type.
- Property source có precedence cao nhất.
- Cú pháp giá trị.
- Custom converter/formatter có đăng ký không.
- Test/runtime classpath có cùng conversion infrastructure không.

Đối với configuration phức tạp, `@ConfigurationProperties` thường giúp tập trung metadata, binding và validation hơn việc rải nhiều `@Value` trong constructor.

## 18. Bean phụ thuộc tài nguyên bên ngoài khi khởi tạo

Một số bean cần kết nối database, message broker, object storage hoặc remote API ngay lúc tạo:

~~~java
@Component
public class PartnerConnection {

    private final PartnerClient client;

    public PartnerConnection(PartnerClient client) {
        this.client = client;
    }

    @PostConstruct
    void connect() {
        client.ping();
    }
}
~~~

Nếu partner đang bảo trì, DNS lỗi, TLS certificate không hợp lệ hoặc credential sai, callback có thể ném exception và làm Spring context không khởi động.

### Có nên fail startup khi dịch vụ ngoài không sẵn sàng?

Đây là quyết định vận hành, không chỉ là quyết định code.

Fail startup có thể phù hợp nếu service không thể phục vụ bất kỳ request nào khi partner không sẵn sàng. Nhưng nếu integration có thể retry hoặc chức năng chỉ là optional, bắt toàn ứng dụng fail có thể làm giảm khả năng phục hồi.

Có thể cân nhắc:

- Tạo client mà không kết nối ngay trong constructor.
- Thực hiện connection check bằng health/readiness logic.
- Retry có giới hạn và backoff.
- Đánh dấu readiness chưa đạt cho đến khi dependency sẵn sàng.
- Tách integration tùy chọn khỏi bean core.
- Dùng timeout rõ ràng và circuit breaker phù hợp.

Không nên để một startup callback block vô hạn chờ remote service.

### Không nuốt exception rồi giả vờ khởi động thành công

~~~java
@PostConstruct
void connect() {
    try {
        client.connect();
    } catch (Exception ex) {
        log.warn("Partner connection failed", ex);
    }
}
~~~

Cách này có thể khiến context khởi động dù bean ở trạng thái không dùng được. Nếu ứng dụng vẫn nhận request và sau đó thất bại, lỗi trở nên khó hiểu hơn.

Nếu chọn degraded mode, phải biểu diễn trạng thái đó rõ ràng, có health indicator và hành vi request tương ứng. Không chỉ ghi warning rồi bỏ qua.

## 19. Circular dependency và BeanCurrentlyInCreationException

Một lỗi khó chịu khác xảy ra khi hai hoặc nhiều bean phụ thuộc vòng tròn.

~~~text
OrderService -> InventoryService
      ^               |
      |               v
      +----------- StockService
~~~

Ví dụ constructor injection:

~~~java
@Service
public class OrderService {

    public OrderService(InventoryService inventoryService) {
    }
}
~~~

~~~java
@Service
public class InventoryService {

    public InventoryService(OrderService orderService) {
    }
}
~~~

Spring phải tạo `OrderService` để có `InventoryService`, nhưng lại cần `OrderService` để tạo `InventoryService`. Với constructor cycle, không có object hoàn chỉnh để đưa cho dependency còn lại.

Lỗi có thể thể hiện qua `BeanCurrentlyInCreationException` và chuỗi `BeanCreationException`.

### Spring Boot mặc định không khuyến khích circular references

Trong các thế hệ Spring Boot hiện đại, circular references thường bị cấm theo mặc định. Vì vậy, một số setter/field cycles từng có thể được giải quyết bằng early references trong cấu hình Spring cũ có thể vẫn thất bại trong Boot mặc định.

Không nên bật `spring.main.allow-circular-references=true` như một cách sửa đầu tiên. Nó có thể che giấu coupling không hợp lý và khiến lifecycle/proxy phức tạp.

### Cách sửa tốt hơn: tách trách nhiệm

Thay vì:

~~~text
OrderService <----> InventoryService
~~~

có thể tạo một service điều phối:

~~~text
OrderApplicationService
       |           |
       v           v
OrderService  InventoryService
~~~

Hoặc tách một abstraction nhỏ mà cả hai cùng cần, tránh phụ thuộc ngược.

### Dùng event khi phù hợp

Nếu một service chỉ cần thông báo rằng một nghiệp vụ đã xảy ra, application event có thể giảm coupling:

~~~java
public record OrderPlacedEvent(UUID orderId) {}
~~~

Một thành phần khác xử lý event:

~~~java
@Component
public class InventoryEventHandler {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        // Giữ hàng.
    }
}
~~~

Đây là lựa chọn thiết kế, không phải công thức thay mọi dependency. Nếu yêu cầu cần tính nhất quán transaction hoặc xử lý bền vững, phải cân nhắc transaction-bound events hoặc message/outbox pattern phù hợp.

## 20. @Lazy có thể trì hoãn dependency, không tự sửa thiết kế

`@Lazy` trên bean hoặc injection point có thể trì hoãn việc khởi tạo/resolve một dependency thông qua proxy ở những trường hợp hỗ trợ.

Ví dụ:

~~~java
@Service
public class ReportService {

    private final ExpensiveReportEngine engine;

    public ReportService(@Lazy ExpensiveReportEngine engine) {
        this.engine = engine;
    }
}
~~~

Nếu engine chưa cần ngay, nó có thể được khởi tạo khi proxy được sử dụng lần đầu.

Nhưng:

- Khi bean lazy được sử dụng, lỗi khởi tạo vẫn có thể xuất hiện.
- Dependency cycle không tự biến mất về mặt thiết kế.
- Lỗi được chuyển từ startup sang request/runtime path.
- Một bean bị trì hoãn có thể khiến health/readiness không phản ánh đầy đủ khả năng thực thi.

Dùng `@Lazy` khi trì hoãn khởi tạo có ý nghĩa, không dùng để che một dependency bắt buộc không thể tạo.

## 21. @DependsOn không phải cơ chế inject dependency

`@DependsOn` chỉ định thứ tự khởi tạo/đóng giữa các bean khi cần side-effect ordering.

Ví dụ:

~~~java
@Component
public class SearchIndexer {
}

@Component
@DependsOn("searchIndexer")
public class SearchWarmup {
}
~~~

Spring sẽ đảm bảo bean được chỉ định được khởi tạo trước bean phụ thuộc theo cơ chế của container.

Nhưng `@DependsOn` **không cung cấp một reference dependency** để inject vào constructor và không phải cách giải quyết circular constructor injection.

Nếu `SearchWarmup` thực sự cần gọi `SearchIndexer`, hãy inject nó qua constructor. Khi có dependency thật, Spring tự hiểu relationship và quản lý lifecycle phù hợp.

## 22. BeanFactoryPostProcessor hoặc BeanPostProcessor thất bại

Spring có những extension points chạy trong quá trình xử lý bean definitions hoặc tạo bean:

- `BeanFactoryPostProcessor` thao tác metadata/bean factory trước khi các bean ứng dụng thông thường được khởi tạo.
- `BeanPostProcessor` xử lý object trước/sau initialization.
- Auto-configuration và framework infrastructure đăng ký những processor của riêng mình.

Nếu một processor thất bại, có thể nhiều bean khác không được tạo hoặc context không thể refresh.

Ví dụ:

~~~java
@Component
public class InvalidBeanPostProcessor
        implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName
    ) {
        if ("orderService".equals(beanName)) {
            throw new IllegalStateException(
                    "Order service cannot be initialized"
            );
        }

        return bean;
    }
}
~~~

Ví dụ này cố ý tạo lỗi để minh họa. Trong thực tế, processor có thể lỗi vì reflection, proxy creation, metadata hoặc logic xử lý bean.

### Chẩn đoán processor

- Tìm bean name được ghi trong message.
- Xem exception xuất hiện trước hay sau init callback.
- Xác định processor nào đang xử lý bean.
- Kiểm tra ordering và dependencies của processor.
- Nếu processor thuộc thư viện bên thứ ba, xem version và auto-configuration condition.

Đừng nhầm một exception do BeanPostProcessor ném ra với exception từ constructor của bean target.

## 23. FactoryBean: tạo factory thành công nhưng object thất bại

`FactoryBean` là một abstraction cho phép Spring lấy object từ một factory bean.

Ví dụ khái niệm:

~~~java
public class ReportClientFactory
        implements FactoryBean<ReportClient> {

    @Override
    public ReportClient getObject() {
        return new ReportClient(loadConfiguration());
    }

    @Override
    public Class<?> getObjectType() {
        return ReportClient.class;
    }
}
~~~

Có hai lớp cần phân biệt:

1. Spring tạo `ReportClientFactory`.
2. Spring yêu cầu factory cung cấp `ReportClient`.

Factory bean có thể được tạo thành công nhưng `getObject()` ném exception. Khi đó bean mà application yêu cầu không thể được cung cấp, và lỗi container có thể xuất hiện dưới dạng BeanCreationException hoặc exception liên quan factory bean.

### Cần đọc tên bean và FactoryBean contract

Khi thấy lỗi liên quan `FactoryBean`, kiểm tra:

- FactoryBean constructor.
- `getObject()`.
- `getObjectType()`.
- Dependency mà factory cần.
- Cấu hình được dùng để tạo sản phẩm.
- Việc khởi tạo có được cache hay lặp lại theo scope không.

Không nên chỉ debug class factory mà bỏ qua object thực sự nó tạo ra.

## 24. @Configuration class và @Bean method thất bại

Một `@Configuration` class cũng là một bean và có thể thất bại khi tạo. Những nguyên nhân thường gặp:

- Constructor của configuration class không resolve được dependency.
- Một `@Bean` factory method ném exception.
- Một bean method trả về null trong trường hợp không hợp lệ.
- Class được proxy nhưng có cấu trúc method không tương thích với cách cấu hình.
- Một condition đăng ký configuration không như mong đợi.
- Static initializer của class ném lỗi.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway(
            PaymentProperties properties
    ) {
        if (properties.endpoint() == null) {
            throw new IllegalStateException(
                    "Payment endpoint must be configured"
            );
        }

        return new HttpPaymentGateway(properties.endpoint());
    }
}
~~~

Nếu endpoint thiếu, lỗi được phát hiện khi Spring gọi factory method.

### Phân biệt method được gọi trực tiếp và bean lifecycle

Trong configuration kiểu `proxyBeanMethods = false`, không nên gọi một `@Bean` method khác trực tiếp để lấy singleton bean như thể đó là dependency injection. Hãy khai báo dependency dưới dạng tham số factory method:

~~~java
@Bean
PaymentFacade paymentFacade(PaymentGateway paymentGateway) {
    return new PaymentFacade(paymentGateway);
}
~~~

Cách này làm dependency graph rõ ràng và phù hợp với lite configuration mode.

## 25. Static initializer và lỗi class loading

Java class có thể chạy static initializer trước khi Spring gọi constructor:

~~~java
public class CryptoRegistry {

    static {
        if (System.getenv("CRYPTO_HOME") == null) {
            throw new IllegalStateException(
                    "CRYPTO_HOME is required"
            );
        }
    }
}
~~~

Khi class được load/initialize, exception có thể được bọc thành `ExceptionInInitializerError` hoặc lỗi class initialization khác. Sau đó Spring không thể instantiate bean dùng class đó.

### Kiểm tra các dấu hiệu

- `ExceptionInInitializerError`.
- `NoClassDefFoundError` ở những lần truy cập tiếp theo.
- `ClassNotFoundException`.
- Lỗi static field initialization hoặc thư viện native.

Đừng chỉ tìm constructor. Nếu class chưa thể initialize, constructor có thể chưa được gọi.

### Không đọc runtime secret trong static initializer

Giá trị môi trường có thể khác giữa máy developer, CI và production. Static initialization cũng có timing khác khi chạy JVM, test hoặc native executable. Hãy đưa cấu hình vào bean qua Environment/ConfigurationProperties và validate ở đúng lifecycle boundary.

## 26. Profile hoặc condition khiến dependency không tồn tại

Một service có thể yêu cầu bean chỉ được đăng ký trong profile khác:

~~~java
@Component
@Profile("prod")
public class ProductionPaymentGateway
        implements PaymentGateway {
}
~~~

Nhưng service không có điều kiện:

~~~java
@Service
public class CheckoutService {

    public CheckoutService(PaymentGateway gateway) {
    }
}
~~~

Nếu chạy với profile `dev` và không có bean `PaymentGateway` nào khác, context có thể fail.

### Những câu hỏi cần kiểm tra

- Profile nào đang active?
- Có default profile nào đang được sử dụng không?
- Bean implementation có đúng profile không?
- Condition có match property không?
- Một dependency optional có bị thiếu không?
- Có một bean fallback phù hợp không?

### Không tạo fallback production tùy tiện

Nếu dev cần fake gateway, hãy định nghĩa bean dev rõ ràng. Nếu production cần real gateway, hãy kiểm tra production configuration bắt buộc. Không dùng một no-op implementation chung để mọi profile đều khởi động được nếu điều đó có thể khiến giao dịch bị bỏ qua mà không ai biết.

## 27. Auto-configuration back-off và lỗi bean trùng

Spring Boot auto-configuration thường tạo bean mặc định khi ứng dụng chưa cung cấp bean tùy chỉnh:

~~~java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
~~~

Nếu user configuration đã tạo một bean `PaymentGateway` phù hợp, auto-configuration nên back off theo điều kiện.

Nếu condition/order không đúng hoặc bean tùy chỉnh không được phát hiện tại thời điểm đánh giá, ứng dụng có thể gặp:

- Nhiều bean cùng kiểu.
- Bean mặc định vẫn được tạo dù đã có bean custom.
- Injection ambiguity.
- Bean definition override conflict tùy tên và chính sách override.

### Phân biệt lỗi creation với lỗi registration

- **Registration conflict:** Spring không thể đăng ký bean definition theo tên/chính sách hiện tại.
- **Creation failure:** bean definition đã tồn tại nhưng object không tạo/initialize được.
- **Injection ambiguity:** nhiều bean hợp lệ cùng đáp ứng một dependency nhưng không có candidate ưu tiên.

Các loại này có thể cùng xuất hiện trong một startup log, nhưng cách sửa khác nhau.

## 28. Dependency scope và lỗi khi tạo bean

Singleton thường được tạo khi context refresh, trừ khi lazy. Prototype được tạo mỗi lần được yêu cầu. Scoped beans có thể được tạo khi scope tương ứng hoạt động, ví dụ request scope.

Do đó, cùng một lỗi constructor có thể xuất hiện ở thời điểm khác:

- Singleton eager: thường xuất hiện trong startup.
- Singleton lazy: có thể chỉ xuất hiện ở lần đầu được truy cập.
- Prototype: có thể lặp lại mỗi lần tạo instance.
- Request-scoped: có thể xuất hiện khi xử lý request đầu tiên phù hợp.

### Context khởi động thành công chưa chắc mọi bean đều tạo được

Nếu một bean được lazy-init hoặc chỉ được yêu cầu trong một nhánh runtime, context có thể khởi động thành công dù bean đó sẽ fail khi được gọi lần đầu.

Đối với các integration quan trọng, cần test việc khởi tạo thực tế hoặc có health/readiness check phù hợp, thay vì chỉ xác nhận process đã start.

## 29. BeanCreationException trong test context

Một test Spring có thể fail trước khi test method được chạy:

~~~java
@SpringBootTest
class OrderServiceTests {

    @Autowired
    OrderService orderService;

    @Test
    void createsOrder() {
        // ...
    }
}
~~~

Nếu một bean trong toàn application context không tạo được, Spring Test không thể inject test dependencies và có thể báo context load failure.

### Đọc test failure

- Xem test class đang yêu cầu loại context nào.
- Tìm lần load context đầu tiên thất bại.
- Tìm bean và root cause.
- Xem test property sources, active profiles và mocks.
- Kiểm tra bean có bị phụ thuộc một service bên ngoài không.

### Test hẹp khi chỉ cần kiểm tra configuration

Với một auto-configuration nhỏ, `ApplicationContextRunner` có thể giúp cô lập:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(MyConfiguration.class)
        .withPropertyValues("demo.feature.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(MyFeature.class);
        });
~~~

Nếu context fail, callback có thể kiểm tra `context.hasFailed()` và `context.getStartupFailure()`. Cách này hữu ích để xác nhận failure có chủ đích hoặc condition, không cần khởi động toàn bộ ứng dụng.

### Test hẹp không thay thế full application test

Nếu cần chứng minh toàn bộ application có thể khởi động với production-like profile và database configuration, vẫn cần một integration test phù hợp. Runner nhỏ chỉ chứng minh tập configuration được đưa vào nó.

## 30. Dùng ApplicationContextRunner để kiểm tra startup failure

Ví dụ cấu hình cần một dependency:

~~~java
@Configuration(proxyBeanMethods = false)
class RequiredClientConfiguration {

    @Bean
    ReportService reportService(RequiredClient client) {
        return new ReportService(client);
    }
}
~~~

Test:

~~~java
@Test
void failsWhenRequiredClientIsMissing() {
    new ApplicationContextRunner()
            .withUserConfiguration(
                    RequiredClientConfiguration.class
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

Nếu cần, có thể assert root cause:

~~~java
assertThat(context.getStartupFailure())
        .hasRootCauseInstanceOf(
                NoSuchBeanDefinitionException.class
        );
~~~

Điều này kiểm tra contract rằng dependency thực sự bắt buộc. Nếu integration là optional, test nên chứng minh context vẫn khởi động mà không đăng ký integration bean.

## 31. FailureAnalyzer của Spring Boot

Spring Boot có cơ chế **FailureAnalyzer** để biến một số lỗi startup phổ biến thành thông báo dễ hiểu hơn.

Khi context startup thất bại, Boot có thể:

1. Nhận exception gốc.
2. Tìm analyzer phù hợp.
3. Tạo một analysis result với description/action.
4. In thông tin giúp developer hiểu nguyên nhân và cách khắc phục.

Ví dụ một số lỗi có analyzer hoặc thông báo chuyên biệt:

- Port đã được sử dụng.
- Bean definition/constructor injection thất bại.
- Configuration properties sai.
- Logging system không khởi động được.
- Một số lỗi auto-configuration phổ biến.

Không phải mọi exception tùy chỉnh đều có FailureAnalyzer. Nếu analyzer không tìm được kết quả, stack trace vẫn là nguồn chẩn đoán quan trọng.

### Không bỏ qua phần Description và Action

Khi Boot in một phần:

~~~text
APPLICATION FAILED TO START

Description:
...

Action:
...
~~~

hãy đọc cả hai phần. Description nói điều kiện nào thất bại; Action có thể chỉ ra thay đổi cấu hình cần thực hiện.

Đừng chỉ đọc dòng cuối `Application run failed`.

## 32. Bật debug để xem condition evaluation report

Nếu nghi ngờ bean không được tạo do auto-configuration condition, có thể chạy:

~~~bash
java -jar store-service.jar --debug
~~~

Hoặc cấu hình:

~~~properties
debug=true
~~~

Spring Boot có thể in **Condition Evaluation Report**, cho biết một số auto-configurations match hoặc không match và lý do.

### Debug report trả lời câu hỏi nào?

- Auto-configuration nào được áp dụng?
- Condition classpath có match không?
- Property có giá trị phù hợp không?
- Bean có sẵn khiến auto-configuration back off không?
- Vì sao một cấu hình bị loại?

### Debug không thay thế stack trace

Condition report giúp giải thích bean registration. Nếu constructor đã được gọi và ném exception, cần đọc stack trace để tìm nguyên nhân trong constructor/init logic.

### Cẩn thận dữ liệu nhạy cảm

Debug log có thể chứa nhiều chi tiết cấu hình và môi trường hơn bình thường. Không bật verbose logging kéo dài trong production nếu chưa kiểm soát việc lộ endpoint, property và metadata nội bộ.

## 33. Bật log cho bean factory khi cần

Khi lỗi khó xác định, có thể tăng log level cho các package Spring liên quan trong một môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.beans.factory: DEBUG
    org.springframework.context: DEBUG
    org.springframework.boot.autoconfigure: DEBUG
~~~

Điều này có thể cho thấy quá trình tạo bean, dependency resolution và condition evaluation chi tiết hơn.

Không nên bật `TRACE` toàn bộ Spring trong production nếu chưa đánh giá lượng log và thông tin được ghi.

### Dùng phạm vi hẹp

Nếu nghi ngờ auto-configuration:

~~~yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
~~~

Nếu nghi ngờ bean lifecycle:

~~~yaml
logging:
  level:
    org.springframework.beans.factory.support: DEBUG
~~~

Tên logger và lượng log phụ thuộc version. Chỉ bật khi có mục tiêu điều tra cụ thể rồi đưa level về bình thường.

## 34. Quy trình chẩn đoán từ log tới source code

Một quy trình có thể lặp lại:

~~~text
Ứng dụng không khởi động
          |
          v
Tìm BeanCreationException đầu tiên
          |
          v
Ghi tên bean đang được tạo
          |
          v
Đọc mô tả thao tác thất bại
          |
          v
Lần theo dependency chain
          |
          +--> Constructor?
          |
          +--> Dependency missing/ambiguous?
          |
          +--> Property binding/conversion?
          |
          +--> @PostConstruct/init method?
          |
          +--> External resource?
          |
          +--> Circular dependency?
          |
          +--> BeanPostProcessor/FactoryBean?
          |
          v
Đối chiếu profile, conditions, classpath
          |
          v
Sửa đúng nguồn và chạy lại test phù hợp
~~~

### Bước 1: xác định bean name

Ví dụ `orderService`. Tìm class/configuration đăng ký bean đó:

- `@Component`/`@Service`.
- `@Bean` method.
- Auto-configuration.
- FactoryBean.
- Imported configuration.

### Bước 2: xác định Spring đang làm gì

Các mô tả phổ biến:

- `Error creating bean with name ...`.
- `Unsatisfied dependency expressed through constructor parameter ...`.
- `Invocation of init method failed`.
- `Failed to bind properties under ...`.
- `FactoryBean threw exception on object creation`.

Mỗi mô tả gợi ý một giai đoạn khác nhau.

### Bước 3: tìm root cause

Đọc tất cả `Caused by`, không dừng ở exception đầu tiên. Đối chiếu root cause với source code hoặc cấu hình được nêu trong message.

### Bước 4: xác nhận môi trường

Kiểm tra:

- Active/default profiles.
- Runtime properties và precedence.
- Dependencies trên runtime classpath.
- Bean conditions.
- External endpoint/credential.
- Environment variables và secret mounts.
- Version của framework/library.

### Bước 5: sửa và xác nhận

Sau khi sửa, chạy test phù hợp với phạm vi lỗi:

- Unit test cho constructor/init logic thuần.
- ApplicationContextRunner cho conditional configuration.
- Spring context test cho wiring.
- Integration test cho database/HTTP/broker thật.
- Smoke test cho artifact đã đóng gói.

Không cần dùng full integration test cho một lỗi typo đơn giản trong property, nhưng cũng không dùng unit test thuần để tuyên bố auto-configuration toàn ứng dụng hoạt động.

## 35. Ví dụ đọc một dependency chain hoàn chỉnh

Giả sử log:

~~~text
Error creating bean with name 'invoiceController'
  Unsatisfied dependency expressed through constructor parameter 0

Caused by: Error creating bean with name 'invoiceService'
  Unsatisfied dependency expressed through constructor parameter 1

Caused by: Error creating bean with name 'taxClient'
  Invocation of init method failed

Caused by: IllegalStateException:
  Tax endpoint must use HTTPS
~~~

Đọc từ ngoài vào:

| Bean | Vai trò | Trạng thái |
|---|---|---|
| `invoiceController` | Cần InvoiceService | Không tạo được vì dependency |
| `invoiceService` | Cần taxClient ở parameter 1 | Không tạo được vì dependency |
| `taxClient` | Init method kiểm tra endpoint | Init thất bại |
| `IllegalStateException` | Nguyên nhân cụ thể | URL không dùng HTTPS |

Nguồn lỗi thực tế nằm ở cấu hình endpoint hoặc logic validation của `taxClient`. Sửa controller không giải quyết vấn đề.

Ví dụ cấu hình sai:

~~~yaml
tax:
  endpoint: http://tax.internal
~~~

Cấu hình đúng theo contract ví dụ:

~~~yaml
tax:
  endpoint: https://tax.internal
~~~

Nếu endpoint thực tế phải hỗ trợ HTTP trong development, điều kiện validation cần phản ánh chính sách theo profile rõ ràng; không nên ép HTTPS ở mọi môi trường mà không xét yêu cầu thực tế.

## 36. Phân biệt lỗi Spring với lỗi gốc của thư viện

Một constructor có thể gọi thư viện ngoài:

~~~java
public SearchClient(SearchSettings settings) {
    this.delegate = ThirdPartyClient.create(settings.url());
}
~~~

Nếu thư viện ném `IllegalArgumentException` hoặc `LinkageError`, Spring có thể bọc exception đó trong lỗi tạo bean.

Cần xác định:

- Lỗi do tham số cấu hình không hợp lệ?
- Dependency version không tương thích?
- Class bị thiếu?
- Native library không load được?
- TLS/provider/security setting sai?
- Thư viện yêu cầu một system property chưa có?

Không nên mặc định Spring container có bug chỉ vì exception cuối cùng mang package `org.springframework.beans.factory`.

### NoClassDefFoundError và ClassNotFoundException

Hai lỗi này thường chỉ ra vấn đề class loading:

- `ClassNotFoundException` thường xuất hiện khi code chủ động yêu cầu nạp class theo tên mà không tìm thấy.
- `NoClassDefFoundError` có thể xuất hiện khi JVM không tìm được định nghĩa cần thiết hoặc class từng không thể initialize thành công.

Kiểm tra runtime dependency graph, scope và phiên bản artifact trước khi sửa bean wiring.

## 37. Lỗi database trong init callback

Ví dụ:

~~~java
@Component
public class SchemaVerifier {

    private final JdbcTemplate jdbcTemplate;

    public SchemaVerifier(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostConstruct
    void verify() {
        jdbcTemplate.queryForObject(
                "select 1",
                Integer.class
        );
    }
}
~~~

Nếu database chưa sẵn sàng, bean init thất bại và context có thể không khởi động.

### Có nên query database trong @PostConstruct?

Không có một câu trả lời chung. Nếu ứng dụng bắt buộc phải kết nối database để phục vụ request, fail-fast có thể là lựa chọn hợp lý. Nhưng nếu dependency có thể phục hồi, startup check đồng bộ có thể khiến orchestration restart loop.

Các lựa chọn:

- Dùng health indicator/readiness để biểu diễn dependency status.
- Dùng retry có timeout và backoff.
- Tách schema migration khỏi bean constructor/init.
- Đảm bảo migration chỉ chạy đúng một lần và có concurrency control.
- Không cho readiness đạt khi dependency bắt buộc chưa sẵn sàng.

### Startup và readiness là hai mốc khác nhau

Một process có thể đã tạo xong context nhưng chưa đủ điều kiện phục vụ traffic. Ngược lại, nếu mọi dependency check đều thực hiện trong init callback, context có thể fail trước khi orchestrator quan sát được trạng thái readiness.

Thiết kế health/lifecycle cần phù hợp với cách nền tảng điều phối container.

## 38. Không dùng catch-all để che BeanCreationException

Một anti-pattern là bắt mọi exception trong constructor/init rồi tiếp tục:

~~~java
@PostConstruct
void initialize() {
    try {
        loadRequiredConfiguration();
    } catch (Exception ex) {
        log.error("Initialization failed", ex);
    }
}
~~~

Bean có thể được xem là khởi tạo thành công dù invariant quan trọng không được thiết lập.

Nếu lỗi khiến bean không thể thực hiện contract, hãy để startup thất bại với exception rõ ràng hoặc chuyển ứng dụng vào trạng thái degraded được thiết kế có chủ đích.

### Nếu cần degraded mode

Biểu diễn trạng thái:

~~~java
@Component
public class PartnerAvailability {

    private volatile boolean available;

    public boolean isAvailable() {
        return available;
    }

    public void markAvailable() {
        available = true;
    }

    public void markUnavailable() {
        available = false;
    }
}
~~~

Một workflow khác có thể retry và cập nhật trạng thái; health indicator/consumer cần sử dụng trạng thái này rõ ràng. Đây chỉ là mô hình minh họa, cần đồng bộ và lifecycle phù hợp trong ứng dụng thực.

Không nên coi log warning là bằng chứng ứng dụng đã xử lý lỗi.

## 39. Side effects đã xảy ra trước khi bean creation thất bại

Giả sử init callback:

1. Tạo một queue ở remote broker.
2. Mở connection.
3. Nạp cấu hình.
4. Bước 3 thất bại.

Spring có thể đóng những singleton bean đã tạo thành công theo quy trình context shutdown, nhưng **không bảo đảm tự hoàn tác mọi side effect bên ngoài đã xảy ra**. Một remote queue đã tạo có thể vẫn tồn tại; một request đã gửi không thể tự undo.

### Thiết kế init có khả năng cleanup

- Mở resource theo thứ tự có thể đóng ngược.
- Nếu init thất bại giữa chừng, tự cleanup phần đã mở khi cần.
- Dùng idempotent operations khi có thể.
- Tránh thực hiện business transaction lớn trong callback khởi tạo.
- Để destruction callbacks đóng đúng tài nguyên mà bean sở hữu.

### Startup failure không phải transaction toàn hệ thống

ApplicationContext là container lifecycle, không phải một distributed transaction. Đừng giả định mọi constructor/init callback đều được rollback như một database transaction.

## 40. Shutdown callbacks khi startup thất bại

Khi refresh context thất bại, Spring có cơ chế cleanup những singleton đã được tạo/đăng ký phù hợp trong quá trình refresh. Những bean đã khởi tạo thành công có thể được destruction callbacks gọi.

Tuy nhiên:

- Bean đang tạo dở có thể không có đầy đủ lifecycle để cleanup tự động.
- Side effect ngoài Spring container không tự rollback.
- Thread do code tạo thủ công có thể sống sót nếu không được quản lý đúng.
- Một process bị kill cưỡng bức không bảo đảm shutdown callbacks chạy.

Vì vậy, constructor/init code phải quản lý resource có chủ đích. Không dựa vào giả định “nếu bean không tạo xong thì Spring sẽ tự dọn mọi thứ”.

## 41. Constructor nên tránh gọi bean khác bằng ApplicationContext

Một cách làm khó bảo trì:

~~~java
@Component
public class OrderService implements ApplicationContextAware {

    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.context = context;
    }

    public void execute() {
        PaymentClient client =
                context.getBean(PaymentClient.class);
        // ...
    }
}
~~~

Cách này che dependency khỏi constructor và làm lỗi bean creation xuất hiện muộn hơn, khi method chạy.

Ưu tiên constructor injection:

~~~java
@Service
public class OrderService {

    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    public void execute() {
        paymentClient.pay();
    }
}
~~~

Dependency bắt buộc trở nên rõ ngay lúc context tạo bean. Nếu thiếu, Spring fail fast và log chỉ ra constructor parameter.

ApplicationContext access có thể hợp lý ở một số infrastructure/extension cases, nhưng không nên là cách mặc định để tránh khai báo dependency.

## 42. @Autowired(required=false), Optional và ObjectProvider

Một dependency thực sự tùy chọn có thể được biểu diễn rõ.

### Optional

~~~java
@Service
public class NotificationService {

    private final Optional<PushSender> pushSender;

    public NotificationService(Optional<PushSender> pushSender) {
        this.pushSender = pushSender;
    }
}
~~~

Nếu không có `PushSender`, `Optional` có thể là empty.

### ObjectProvider

~~~java
@Service
public class ReportService {

    private final ObjectProvider<ReportExporter> exporters;

    public ReportService(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void export() {
        ReportExporter exporter = exporters.getIfAvailable();
        if (exporter == null) {
            // Xử lý khi không có exporter tùy chọn.
            return;
        }

        exporter.export();
    }
}
~~~

`ObjectProvider` hỗ trợ resolve dependency theo yêu cầu và một số lựa chọn như lấy candidate có sẵn.

### Không làm dependency bắt buộc thành optional để che lỗi

Nếu ứng dụng không thể hoạt động khi thiếu `PaymentGateway`, việc đổi sang `Optional<PaymentGateway>` rồi bỏ qua khi empty chỉ khiến lỗi xuất hiện muộn và khó phát hiện hơn.

Chỉ dùng optional injection khi nghiệp vụ thực sự cho phép thiếu dependency.

## 43. @Lazy và lỗi bị trì hoãn tới runtime

Một bean lazy có thể không được tạo lúc context startup. Điều đó làm ứng dụng khởi động thành công dù bean có thể thất bại sau này.

Ví dụ:

~~~java
@Service
@Lazy
public class ExternalCatalogClient {

    public ExternalCatalogClient(CatalogSettings settings) {
        validate(settings);
    }
}
~~~

Nếu một request đầu tiên yêu cầu `ExternalCatalogClient`, Spring mới tạo bean và có thể ném `BeanCreationException` tại thời điểm đó.

### Tại sao điều này quan trọng?

Nếu log ghi lỗi BeanCreationException sau vài phút chạy, không có nghĩa Spring đã restart hoặc context startup lần đầu thất bại. Có thể bean lazy/scoped chỉ được tạo lần đầu khi một request truy cập.

Hãy kiểm tra timestamp, thread, request/job context và bean scope để biết lỗi xuất hiện trong startup hay runtime.

## 44. Bean scope và proxy cũng có thể gây lỗi tạo bean

Các scope như request/session hoặc custom scope có thể yêu cầu scope context đang hoạt động. Nếu một bean scoped được truy cập ngoài request context mà không có proxy phù hợp, có thể xuất hiện lỗi liên quan scope.

Ví dụ:

~~~java
@Component
@RequestScope
public class RequestMetadata {

    private String requestId;
}
~~~

Một singleton thường không nên trực tiếp giữ một instance request-scoped đã được tạo ở thời điểm startup. Có thể dùng scoped proxy hoặc provider theo thiết kế phù hợp.

Nếu lỗi nói không có active request scope, vấn đề không phải constructor dependency thiếu theo nghĩa thông thường mà là **lifecycle/scope mismatch**.

## 45. Dependency version và classpath gây lỗi tạo bean

Một bean có thể thất bại do thư viện ngoài không tương thích:

- API class có mặt nhưng method/class trong version mong đợi không có.
- Hai version của cùng library cùng tồn tại.
- Runtime scope bị loại nên class có ở compile nhưng thiếu khi chạy.
- JNI/native library không đúng architecture.
- Framework starter kéo thêm auto-configuration không mong muốn.
- Jakarta/Javax namespace không tương thích giữa các thế hệ.

Ví dụ lỗi:

~~~text
NoSuchMethodError
NoClassDefFoundError
AbstractMethodError
LinkageError
~~~

Những lỗi này có thể xuất hiện trong constructor hoặc init callback rồi được bọc thành BeanCreationException.

### Kiểm tra dependency tree

Maven:

~~~bash
mvn dependency:tree
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Có thể dùng dependency insight để xem vì sao một version được chọn:

~~~bash
./gradlew dependencyInsight \
  --dependency some-library \
  --configuration runtimeClasspath
~~~

Không nên nâng/hạ ngẫu nhiên mọi dependency. Tìm artifact và version gây mismatch, xem BOM/Boot dependency management và compatibility matrix của thư viện.

## 46. Khác biệt giữa NoSuchBeanDefinitionException và NoUniqueBeanDefinitionException

Hai lỗi này thường xuất hiện trong dependency resolution:

| Exception | Ý nghĩa |
|---|---|
| `NoSuchBeanDefinitionException` | Không tìm thấy bean phù hợp |
| `NoUniqueBeanDefinitionException` | Có nhiều bean phù hợp nhưng không xác định được một candidate duy nhất |

Ví dụ:

~~~java
public CheckoutService(PaymentGateway gateway) {
}
~~~

- Không có `PaymentGateway` → thiếu bean.
- Có `CardGateway` và `WalletGateway`, không có qualifier/primary phù hợp → nhiều bean.

Cách sửa tương ứng khác nhau. Thêm một implementation vào trường hợp thứ hai có thể làm tình hình tệ hơn.

## 47. BeanDefinitionOverrideException không giống BeanCreationException

Nếu hai cấu hình đăng ký bean cùng tên trong context mà việc override bị cấm, Spring có thể báo lỗi bean definition conflict, ví dụ `BeanDefinitionOverrideException`.

Đây là vấn đề **đăng ký definition**, xảy ra trước khi object được tạo.

Ví dụ:

~~~java
@Configuration
class FirstConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new CardGateway();
    }
}
~~~

~~~java
@Configuration
class SecondConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new WalletGateway();
    }
}
~~~

Hai method có cùng bean name `paymentGateway`. Nếu cả hai cấu hình được nạp và override không cho phép, context fail khi đăng ký definitions.

Cách sửa:

- Đặt bean name khác nếu cả hai cần tồn tại.
- Dùng profile/condition để chỉ chọn một.
- Dùng `@ConditionalOnMissingBean` cho default auto-configuration.
- Dùng qualifier/primary nếu nhiều implementations có chủ đích.

Không nên bật bean definition overriding toàn cục để che xung đột chưa hiểu rõ.

## 48. Kiểm tra @ConditionalOnProperty và cấu hình đang thực sự được nạp

Một bean có thể không được tạo vì:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "feature.search",
        name = "enabled",
        havingValue = "true"
)
SearchService searchService() {
    return new SearchService();
}
~~~

Cấu hình mong muốn:

~~~yaml
feature:
  search:
    enabled: true
~~~

Nhưng runtime có thể nhận:

~~~text
FEATURE_SEARCH_ENABLED=false
~~~

từ environment variable hoặc một property source có precedence cao hơn.

Khi đó condition không match, bean không được đăng ký. Service khác phụ thuộc `SearchService` có thể gây lỗi tạo bean.

### Cách điều tra

- Xem active profile.
- Xem giá trị property hiệu lực.
- Kiểm tra command line, system property và environment variable.
- Bật condition evaluation report bằng `--debug`.
- Kiểm tra tên property và kiểu giá trị.
- Xác nhận config file được nạp đúng location.

Đừng chỉ nhìn `application.yml` trong source rồi kết luận đó là cấu hình runtime cuối cùng.

## 49. Khi nào nên dùng ApplicationContextRunner?

Nếu lỗi nằm ở auto-configuration/conditions, một test nhỏ có thể cô lập:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(AuditConfiguration.class)
        .withPropertyValues("demo.audit.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

Với auto-configuration:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        AuditAutoConfiguration.class
                )
        )
        .withPropertyValues("demo.audit.enabled=true")
        .run(context -> {
            assertThat(context).hasSingleBean(AuditSink.class);
        });
~~~

Nếu cần kiểm tra context fail khi thiếu dependency:

~~~java
new ApplicationContextRunner()
        .withUserConfiguration(RequiredClientConfiguration.class)
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
~~~

Runner phù hợp cho condition và bean registration. Nếu cần xác nhận toàn application có khởi động được cùng database, messaging và web server, hãy dùng integration test phạm vi rộng hơn.

## 50. Một ví dụ hoàn chỉnh: constructor, dependency và init callback

Giả sử một dịch vụ gửi thông báo cần ba điều kiện:

1. Có bean `MessageTransport`.
2. Property endpoint hợp lệ.
3. Transport phải kết nối thành công khi service được khởi tạo.

Properties:

~~~java
@ConfigurationProperties(prefix = "notify")
@Validated
public class NotifyProperties {

    @NotNull
    private URI endpoint;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Transport:

~~~java
public interface MessageTransport {
    void connect(URI endpoint);
    void close();
}
~~~

Implementation:

~~~java
@Component
public class HttpMessageTransport implements MessageTransport {

    @Override
    public void connect(URI endpoint) {
        if (!"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                    "Notification endpoint must use HTTPS"
            );
        }
    }

    @Override
    public void close() {
        // Close resources.
    }
}
~~~

Service:

~~~java
@Service
public class NotificationService {

    private final NotifyProperties properties;
    private final MessageTransport transport;

    public NotificationService(
            NotifyProperties properties,
            MessageTransport transport
    ) {
        this.properties = properties;
        this.transport = transport;
    }

    @PostConstruct
    void initialize() {
        transport.connect(properties.getEndpoint());
    }
}
~~~

Cấu hình:

~~~yaml
notify:
  endpoint: http://notify.internal
~~~

Startup có thể thất bại ở `@PostConstruct` vì endpoint dùng HTTP thay vì HTTPS theo contract ví dụ.

### Cách đọc lỗi

- `NotifyProperties` có thể bind thành công vì URL là URI hợp lệ.
- `MessageTransport` có thể được inject thành công.
- `NotificationService` được instantiate.
- `initialize()` gọi transport.
- Transport ném `IllegalArgumentException`.
- Spring báo BeanCreationException cho `notificationService`.

### Cách sửa đúng

~~~yaml
notify:
  endpoint: https://notify.internal
~~~

Nếu development cần HTTP, hãy định nghĩa policy theo môi trường một cách rõ ràng và kiểm thử riêng. Không bỏ validation chỉ để làm mất stack trace.

### Cải tiến thiết kế nếu connect là network call

Nếu `connect` có thể chờ lâu hoặc phụ thuộc mạng, cân nhắc không gọi trong `@PostConstruct`. Có thể để transport tạo client nhẹ lúc startup và dùng health/readiness hoặc một startup workflow được quản lý để kiểm tra kết nối. Quyết định này phụ thuộc service có thể phục vụ an toàn khi partner chưa sẵn sàng hay không.

## 51. Kiểm thử constructor/init logic riêng

Nếu logic khởi tạo có thể tách thành một class thuần Java, hãy unit test nó trực tiếp.

Ví dụ validator:

~~~java
public final class EndpointValidator {

    public void validate(URI endpoint) {
        if (endpoint == null
                || !"https".equalsIgnoreCase(endpoint.getScheme())) {
            throw new IllegalArgumentException(
                    "HTTPS endpoint is required"
            );
        }
    }
}
~~~

Unit test:

~~~java
@Test
void rejectsHttpEndpoint() {
    EndpointValidator validator = new EndpointValidator();

    assertThatThrownBy(() ->
            validator.validate(URI.create("http://example.test"))
    ).isInstanceOf(IllegalArgumentException.class);
}
~~~

Test thuần này chứng minh logic validation. Nó không chứng minh Spring gọi `@PostConstruct` đúng, nên cần một context test nếu muốn kiểm tra integration lifecycle.

### Test lifecycle qua context

~~~java
@Test
void contextFailsForInvalidEndpoint() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues(
                    "notify.endpoint=http://notify.internal"
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .isNotNull();
            });
}
~~~

Ví dụ giả định `NotificationConfiguration` đăng ký properties, transport và service cần thiết.

Test thành công:

~~~java
@Test
void contextStartsForValidEndpoint() {
    new ApplicationContextRunner()
            .withUserConfiguration(NotificationConfiguration.class)
            .withPropertyValues(
                    "notify.endpoint=https://notify.internal"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                        NotificationService.class
                );
            });
}
~~~

Nếu việc connect gọi network thật, hãy thay bằng fake transport trong test để tránh test phụ thuộc endpoint ngoài.

## 52. Khi nào cần @SpringBootTest?

Dùng `@SpringBootTest` khi mục tiêu là kiểm tra một phạm vi rộng hơn, chẳng hạn:

- Main application configuration có khởi động được không?
- Component scan có tìm đúng bean không?
- Profile và application config được nạp như production không?
- Auto-configurations tương tác với nhau ra sao?
- Database/messaging/web infrastructure có wiring đúng không?
- Bean lifecycle của toàn ứng dụng có hoàn tất không?

Ví dụ:

~~~java
@SpringBootTest
class ApplicationStartupTests {

    @Test
    void contextLoads() {
    }
}
~~~

Test này hữu ích như một smoke test nhưng có thể chậm và fail vì nhiều dependency khác nhau. Nếu nó thất bại, vẫn phải đọc root cause thay vì kết luận “contextLoads test bị lỗi” như nguyên nhân.

### Dùng cả test hẹp và test rộng

- Unit test: logic constructor/init thuần.
- ApplicationContextRunner: điều kiện và configuration hẹp.
- Spring context test: wiring trong một context có chọn lọc.
- `@SpringBootTest`: integration ở phạm vi application.
- Container/native smoke test: artifact/runtime thực tế.

Mỗi tầng trả lời một câu hỏi khác nhau.

## 53. Một bảng phân loại nhanh theo root cause

| Root cause / exception | Ý nghĩa | Việc đầu tiên cần kiểm tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Thiếu bean | Component scan, profile, condition, configuration import |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng phù hợp | `@Primary`, `@Qualifier`, bean conditions |
| `BeanCurrentlyInCreationException` | Dependency cycle/bean đang tạo dở | Constructor graph và phụ thuộc vòng |
| `BeanInstantiationException` | Không instantiate được | Constructor/factory method và exception gốc |
| `UnsatisfiedDependencyException` | Dependency không resolve được | Parameter/field/method được nhắc tới |
| `BindException` hoặc lỗi binding | Property không bind được | Property key, type, conversion và source |
| `ConstraintViolationException` trong binding path | Property vi phạm validation | Constraint và giá trị runtime |
| `ExceptionInInitializerError` | Static initialization thất bại | Static block/field và environment |
| `NoClassDefFoundError` | Thiếu class hoặc class không initialize được | Runtime dependency/version/classpath |
| `NoSuchMethodError` | API/library version mismatch | Dependency tree và BOM |
| `IllegalStateException` từ init | Invariant khởi tạo không thỏa | `@PostConstruct`, init method, state/config |
| `IOException` | File/resource/I/O thất bại | Path, permission, mount, content |
| `SQLException` | Database operation thất bại | URL, credential, driver, schema/network |
| `BeanDefinitionOverrideException` | Bean definitions xung đột tên | Configuration import, bean names, conditions |

Tên exception có thể được bọc qua nhiều lớp. Hãy xác định exception nào là nguyên nhân trực tiếp và exception nào chỉ báo lỗi container.

## 54. Những hiểu nhầm cần tránh

### “BeanCreationException nghĩa là constructor của bean đó bị lỗi”

Không đúng. Bean có thể instantiate thành công nhưng dependency, property population, init callback hoặc BeanPostProcessor thất bại.

### “Bean đầu tiên trong log là class cần sửa”

Không nhất thiết. Bean đầu tiên có thể chỉ là consumer không tạo được vì dependency sâu hơn thất bại.

### “Thêm @Component là sửa được missing bean”

Chỉ khi class thật sự cần được component scan và không bị điều kiện khác loại bỏ. Nếu thiếu implementation, profile không match hoặc dependency không có trong classpath, annotation không tự giải quyết.

### “Bật allow-circular-references sẽ sửa dependency graph”

Nó có thể thay đổi khả năng xử lý một số setter/field cycles, nhưng không giải quyết constructor cycle nói chung và không sửa coupling thiết kế. Hãy phá vòng phụ thuộc.

### “@Lazy làm bean lỗi biến mất”

Nó có thể trì hoãn thời điểm tạo và trì hoãn lỗi tới runtime. Không đảm bảo bean hợp lệ.

### “@DependsOn inject bean trước”

Nó điều khiển ordering, không thay thế constructor injection và không giải quyết dependency cycle.

### “Nuốt exception trong @PostConstruct là ứng dụng đã khởi động an toàn”

Không. Bean có thể ở trạng thái không dùng được. Nếu chọn degraded mode, phải biểu diễn trạng thái và health/readiness rõ ràng.

### “Spring sẽ rollback mọi side effect khi context fail”

Không. Container cleanup không phải distributed transaction. Side effect ngoài container cần được quản lý riêng.

### “Context startup thành công chứng minh mọi bean hợp lệ”

Không nếu có lazy, prototype, scoped beans hoặc những đường code chỉ được kích hoạt về sau.

## 55. Checklist chẩn đoán thực tế

Khi gặp BeanCreationException, đi theo các bước:

1. **Đọc toàn bộ phần startup failure.** Không dừng ở dòng đầu hoặc cuối.
2. **Xác định bean name và thao tác thất bại.** Constructor, dependency, init, factory method hay processor?
3. **Lần theo từng nested exception.** Ghi lại root cause cụ thể.
4. **Kiểm tra dependency parameter.** Thiếu candidate hay có nhiều candidate?
5. **Kiểm tra constructor/factory method.** Có logic ném exception hoặc overload mơ hồ không?
6. **Kiểm tra lifecycle callback.** `@PostConstruct`, `afterPropertiesSet`, custom init method có side effect gì?
7. **Kiểm tra properties.** Key, precedence, conversion, validation, active profile.
8. **Kiểm tra conditions và auto-configuration.** Có bean bị loại hoặc tạo trùng không?
9. **Kiểm tra circular dependency.** Vẽ dependency graph nếu cần.
10. **Kiểm tra external resource.** Database, broker, file, TLS, network, credential và timeout.
11. **Kiểm tra runtime classpath.** Thiếu class, version conflict, scope sai?
12. **Kiểm tra bean scope/lazy behavior.** Lỗi xảy ra lúc startup hay lúc truy cập đầu tiên?
13. **Bật debug/condition report khi có căn cứ.** Không bật verbose logging vô thời hạn.
14. **Sửa nguyên nhân gốc.** Tránh catch-all, thêm scan rộng hoặc bật circular references để che lỗi.
15. **Chạy test phù hợp.** Từ unit đến context runner hoặc full integration.
16. **Kiểm tra cleanup và side effects.** Đảm bảo lần khởi động thất bại không để lại resource ngoài hệ thống.

## Kết luận

`BeanCreationException` cho biết Spring không thể hoàn tất việc tạo một bean, nhưng bản thân nó thường chỉ là **lớp thông báo ở container boundary**. Nguyên nhân thật có thể nằm trong constructor, dependency resolution, factory method, property binding, initialization callback, BeanPostProcessor, FactoryBean, class loading hoặc một dịch vụ bên ngoài mà bean gọi trong lúc khởi tạo.

Cách điều tra đáng tin cậy là đọc bean name và giai đoạn thất bại, lần theo chuỗi `Caused by`, tìm root cause cụ thể, rồi đối chiếu với dependency graph và cấu hình runtime. `NoSuchBeanDefinitionException` gợi ý thiếu candidate; `NoUniqueBeanDefinitionException` gợi ý ambiguity; `BeanCurrentlyInCreationException` gợi ý vòng phụ thuộc; còn thông báo `Invocation of init method failed` yêu cầu kiểm tra `@PostConstruct`, `InitializingBean` hoặc custom init method.

Constructor nên thể hiện dependency bắt buộc và tránh side effect nặng. Init callback cần có timeout, cleanup và chính sách fail-fast/degraded mode rõ ràng. Với lỗi configuration, test hẹp bằng `ApplicationContextRunner` giúp kiểm tra conditions và bean registration; với wiring toàn ứng dụng hoặc external resources, cần integration test phù hợp.

Khi tách đúng **lỗi tạo bean, lỗi dependency và root cause**, bạn sẽ không phải sửa nhầm controller/service ở phía trên của chuỗi. Thay vào đó, có thể xác định chính xác điều kiện nào khiến Spring không thể tạo object graph và khôi phục startup theo cách có thể kiểm chứng.
