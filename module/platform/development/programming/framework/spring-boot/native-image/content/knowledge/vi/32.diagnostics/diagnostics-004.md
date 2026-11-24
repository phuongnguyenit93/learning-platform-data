# Spring AOT không suy ra được kiểu bean hoặc cách tạo đối tượng

> **Chương:** Chẩn đoán  
> **Module:** `SPRING_BOOT_NATIVE_IMAGE`  
> **Mục tiêu:** Chẩn đoán các bean mà Spring AOT không xác định được kiểu thực hoặc chiến lược khởi tạo; sửa khai báo `@Bean`, `FactoryBean`, generic type và `BeanDefinition`; xử lý đăng ký bean động; phân biệt lỗi type prediction với lỗi RuntimeHints và lỗi native runtime.

## 1. Vì sao Spring AOT cần biết kiểu bean trước khi chạy?

Trong ứng dụng Spring thông thường, container có thể trì hoãn một số quyết định đến lúc runtime. Nó đọc bean definitions, khởi tạo bean, chạy `BeanFactoryPostProcessor` và `BeanPostProcessor`, rồi xác định thêm thông tin về kiểu, constructor, field injection, lifecycle callback hoặc proxy khi cần.

Spring AOT chuyển phần lớn quá trình khám phá và chuẩn bị đó sang build time. AOT tạo một `ApplicationContext` để phân tích, thu thập bean definitions và sinh mã khởi tạo tương ứng. Với bean được khai báo tĩnh, mã sinh ra có thể gọi trực tiếp constructor hoặc factory method thay vì phải dựa vào reflection khi ứng dụng chạy.

Muốn làm được việc đó, AOT cần biết:

- Bean nào sẽ tồn tại trong application context.
- Kiểu bean cụ thể hoặc kiểu sản phẩm mà bean cung cấp.
- Constructor, factory method hoặc cơ chế tạo instance nào được dùng.
- Các dependency cần inject vào bean.
- Các field/method injection và lifecycle callback cần xử lý.
- Những proxy, reflection, resource hoặc serialization metadata cần có.

Khi bean chỉ được mô tả bằng interface quá tổng quát, raw generic type, `FactoryBean` không công bố product type, supplier động hoặc singleton được đăng ký trực tiếp, AOT có thể không tái tạo được đầy đủ hành vi của container.

Tài liệu Spring Framework nêu rõ: classpath và bean definitions được cố định ở build time; `@Profile` và các điều kiện `@Conditional` được đánh giá khi AOT; bean definitions dùng instance supplier (lambda hoặc method reference) và singleton đăng ký bằng `registerSingleton` không thể được chuyển đổi ahead of time theo cách thông thường. Vì không thể dựa vào instance để suy ra kiểu, khai báo bean cần chính xác nhất có thể. [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)

## 2. Phân biệt lỗi suy luận kiểu với lỗi tạo bean và lỗi native metadata

Ba nhóm lỗi này thường bị nhầm lẫn:

| Nhóm | Câu hỏi mà Spring/GraalVM không giải quyết được | Ví dụ triệu chứng |
|---|---|---|
| Bean type prediction | Bean hoặc product của factory có kiểu gì? | Bean chỉ lộ ra `Object`, raw `FactoryBean`, generic chưa resolve |
| Bean instantiation | Tạo instance bằng constructor/factory method/supplier nào? | Supplier đăng ký động, custom constructor arguments, singleton tạo sẵn |
| Native runtime metadata | Khi chạy native, thao tác reflection/resource/proxy nào cần được giữ? | `NoSuchMethodException`, resource không tìm thấy, proxy không tạo được |

Một số ví dụ để phân biệt:

- `@Bean` trả về `Object` trong khi object thực tế là `PaymentGatewayImpl`: vấn đề type prediction.
- `BeanDefinition#setInstanceSupplier(...)` dùng lambda tạo bean theo dữ liệu runtime: vấn đề chuyển đổi chiến lược instantiation sang AOT.
- Bean type đã rõ nhưng thư viện gọi constructor qua reflection: vấn đề RuntimeHints.
- Bean được đăng ký bằng `registerSingleton`: instance đã được tạo sẵn, AOT không có bean definition đủ thông tin để tái tạo nó.
- `@ConditionalOnProperty` thay đổi giữa môi trường build và runtime: vấn đề điều kiện bean bị đóng cố định trong AOT.

Không nên bắt đầu bằng việc thêm `RuntimeHintsRegistrar` cho mọi lỗi AOT. Runtime hints giúp Native Image giữ các thao tác động; chúng không cho Spring biết bean nào cần được đăng ký hoặc tạo bằng cách nào.

## 3. Khai báo kiểu trả về cụ thể cho `@Bean`

Đây là nguyên nhân phổ biến nhất và cũng là cách sửa đơn giản nhất.

Giả sử ứng dụng có interface và implementation:

```java
public interface PaymentGateway {
    PaymentResult charge(PaymentCommand command);
}

public class PaymentGatewayImpl implements PaymentGateway {

    @Override
    public PaymentResult charge(PaymentCommand command) {
        // Gọi nhà cung cấp thanh toán.
        return PaymentResult.approved();
    }

    public void validateProviderConfiguration() {
        // Kiểm tra cấu hình riêng của implementation.
    }
}
```

Khai báo sau chỉ cho AOT biết bean có kiểu `PaymentGateway`:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new PaymentGatewayImpl();
    }
}
```

Ở runtime, code vẫn nhận được `PaymentGatewayImpl`. Nhưng trong AOT processing, Spring dùng kiểu khai báo trên factory method để phân tích bean. Những annotation, injection point hoặc lifecycle callback chỉ có trên `PaymentGatewayImpl` có thể không được nhận diện.

Hãy khai báo kiểu cụ thể nhất mà cấu hình thực sự tạo ra:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentGatewayImpl paymentGateway() {
        return new PaymentGatewayImpl();
    }
}
```

Consumer vẫn có thể inject theo interface:

```java
@Service
class CheckoutService {

    private final PaymentGateway paymentGateway;

    CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }
}
```

Điều này không buộc code nghiệp vụ phụ thuộc vào implementation. Nó chỉ giúp bean definition công bố đủ thông tin cho container ở build time.

### 3.1. Khi nào nên giữ kiểu interface?

Nếu factory thực sự có thể trả về nhiều implementation theo cấu hình, không được khai báo một implementation cụ thể sai với hành vi runtime. Hãy tách các bean thành những factory method riêng, dùng điều kiện cấu hình rõ ràng và bảo đảm điều kiện được quyết định ở AOT build.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @Profile("sandbox")
    SandboxPaymentGateway sandboxPaymentGateway() {
        return new SandboxPaymentGateway();
    }

    @Bean
    @Profile("production")
    ProductionPaymentGateway productionPaymentGateway() {
        return new ProductionPaymentGateway();
    }
}
```

Cả hai method công bố concrete type. Bean nào được đưa vào AOT context phụ thuộc profile đã kích hoạt khi build. Khi chạy AOT/native, profile và bean conditions được cố định theo cấu hình build; đổi `SPRING_PROFILES_ACTIVE` lúc runtime không thể bật một bean đã bị loại khỏi AOT output.

Nếu cùng một binary cần hỗ trợ nhiều môi trường, hãy thiết kế một bean có kiểu cụ thể ổn định và để nó đọc cấu hình runtime qua các dependency được hỗ trợ, hoặc tạo artifact AOT riêng cho từng tập profile/condition. Không dựa vào việc đổi profile runtime để thay đổi tập bean đã sinh.

## 4. Kiểm tra factory method và constructor

Spring AOT cần xác định cách tạo bean. Với class thông thường, hãy để constructor và dependency rõ ràng:

```java
@Component
class InvoiceService {

    private final InvoiceRepository repository;
    private final TaxCalculator taxCalculator;

    InvoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator) {
        this.repository = repository;
        this.taxCalculator = taxCalculator;
    }
}
```

Nếu class có nhiều constructor, đánh dấu constructor được Spring sử dụng bằng `@Autowired` khi cần phân biệt. Với một constructor duy nhất, Spring có thể sử dụng constructor đó mà không cần annotation.

Tránh một class có nhiều đường tạo instance không rõ ràng, constructor nhận đối số tùy biến chỉ xuất hiện tại runtime hoặc factory method nhận tham số mà AOT không thể dự đoán.

Ví dụ factory method tĩnh, khai báo dependency qua tham số:

```java
@Configuration(proxyBeanMethods = false)
class InvoiceConfiguration {

    @Bean
    InvoiceService invoiceService(
            InvoiceRepository repository,
            TaxCalculator taxCalculator) {
        return new InvoiceService(repository, taxCalculator);
    }
}
```

Spring có thể mô tả dependency của factory method qua bean definitions và sinh mã gọi method tương ứng.

### 4.1. Tránh truyền custom arguments khi gọi `getBean`

Một số ứng dụng tạo prototype bean bằng custom arguments:

```java
InvoiceJob job = beanFactory.getBean(
        InvoiceJob.class, invoiceId, requestedAt);
```

Cách này yêu cầu container tìm constructor hoặc factory method phù hợp với các đối số động. Spring AOT không thể suy ra toàn bộ tổ hợp argument và reflection cần thiết từ lời gọi runtime. Ngoài ra, tạo bean bằng custom arguments có thể bỏ qua instance supplier đã sinh, khiến các tối ưu hóa injection trên field/method không được áp dụng như mong đợi.

Thay vào đó, tạo một bean factory chuyên trách với dependency tường minh:

```java
@Component
class InvoiceJobFactory {

    private final InvoiceRepository repository;
    private final Clock clock;

    InvoiceJobFactory(InvoiceRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    InvoiceJob create(long invoiceId) {
        return new InvoiceJob(invoiceId, clock.instant(), repository);
    }
}
```

Ở đây factory bean được Spring quản lý theo một kiểu xác định. Dữ liệu thay đổi theo từng job được truyền qua method `create`, còn dependency dài hạn được inject khi factory được tạo. Đây cũng là cách dễ kiểm thử và dễ kiểm soát vòng đời object hơn.

## 5. Generic type bị mất do raw type hoặc type erasure

Spring sử dụng `ResolvableType` để giữ và phân tích generic metadata. Nếu khai báo bean bằng raw type, một phần thông tin có thể bị mất.

Ví dụ chưa đủ thông tin:

```java
@Bean
RepositoryAdapter repositoryAdapter() {
    return new RepositoryAdapter();
}
```

Nếu adapter thực tế quản lý `Customer`, khai báo type có generic rõ ràng:

```java
@Bean
RepositoryAdapter<Customer, Long> customerRepositoryAdapter() {
    return new RepositoryAdapter<>();
}
```

Với bean definition lập trình, sử dụng `RootBeanDefinition` và đặt target type bằng `ResolvableType`:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(RepositoryAdapter.class);

definition.setTargetType(
        ResolvableType.forClassWithGenerics(
                RepositoryAdapter.class,
                Customer.class,
                Long.class));

registry.registerBeanDefinition(
        "customerRepositoryAdapter", definition);
```

`ResolvableType.forClassWithGenerics(...)` giữ được kiểu tham số mà raw `Class` không biểu diễn được. Điều này đặc biệt quan trọng khi bean factory, `FactoryBean`, collection injection hoặc framework extension cần biết product type chính xác. [Spring Framework — ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html)

## 6. Xử lý `FactoryBean` khi AOT không biết product type

`FactoryBean` tạo ra một object khác với bản thân factory. Spring phải biết cả kiểu của factory lẫn kiểu sản phẩm mà `getObject()` trả về. Nếu product type không xác định được, các bước type prediction và post-processing có thể không nhận diện đầy đủ bean mà consumer thực sự inject.

Ví dụ factory generic nhưng không được tham số hóa:

```java
public class ClientFactoryBean<T extends AbstractClient>
        implements FactoryBean<T> {

    private final Class<T> productType;
    private final Supplier<T> supplier;

    public ClientFactoryBean(Class<T> productType, Supplier<T> supplier) {
        this.productType = productType;
        this.supplier = supplier;
    }

    @Override
    public T getObject() {
        return supplier.get();
    }

    @Override
    public Class<?> getObjectType() {
        return productType;
    }
}
```

Khai báo raw type làm mất generic metadata:

```java
@Bean
ClientFactoryBean paymentClient() {
    return new ClientFactoryBean(
            PaymentClient.class, PaymentClient::new);
}
```

Hãy công bố generic type đã resolve:

```java
@Bean
ClientFactoryBean<PaymentClient> paymentClient() {
    return new ClientFactoryBean<>(
            PaymentClient.class, PaymentClient::new);
}
```

Kiểu `ClientFactoryBean<PaymentClient>` cho Spring thông tin generic về product. Nếu factory được đăng ký programmatically, phải mô tả cả factory class và target type:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(ClientFactoryBean.class);

definition.setTargetType(
        ResolvableType.forClassWithGenerics(
                ClientFactoryBean.class,
                PaymentClient.class));

registry.registerBeanDefinition("paymentClient", definition);
```

Khi cần, `FactoryBean#getObjectType()` cũng nên trả về product class ổn định mà factory có thể công bố mà không cần tạo product instance. Tránh trả về `null` hoặc chỉ suy luận product type sau khi gọi dịch vụ ngoài, đọc file runtime hay tạo client.

### 6.1. Khi nào nên thay `FactoryBean` bằng `@Bean`?

Spring Framework khuyến nghị cân nhắc thay `FactoryBean` bằng factory method thông thường nếu factory không giữ state dài hạn và không cần tồn tại ở runtime. Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class ClientConfiguration {

    @Bean
    PaymentClient paymentClient(
            PaymentClientProperties properties,
            HttpClient httpClient) {
        return new PaymentClient(properties.endpoint(), httpClient);
    }
}
```

Factory method làm rõ product type và dependency. Chỉ giữ `FactoryBean` khi abstraction đó thực sự cần thiết, chẳng hạn cần tích hợp một API framework hoặc factory phải được truy cập như một bean độc lập.

## 7. Đăng ký bean programmatically bằng `BeanDefinitionRegistry`

Nếu ứng dụng cần tạo bean theo module/plugin, hãy đăng ký bean definition trước khi AOT phân tích context. Cách phù hợp là dùng `ImportBeanDefinitionRegistrar` hoặc `BeanDefinitionRegistryPostProcessor` theo đúng lifecycle.

Ví dụ registrar khai báo bean definition với concrete class:

```java
public class PaymentClientRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        RootBeanDefinition definition =
                new RootBeanDefinition(PaymentClient.class);

        definition.setTargetType(
                ResolvableType.forClass(PaymentClient.class));

        registry.registerBeanDefinition(
                "paymentClient", definition);
    }
}
```

Import registrar từ configuration:

```java
@Configuration(proxyBeanMethods = false)
@Import(PaymentClientRegistrar.class)
class PaymentClientConfiguration {
}
```

AOT engine xử lý configuration model và callback được gọi trong quá trình phân tích cấu hình. Vì vậy, registrar được import theo cách này có thể đóng góp bean definitions trước khi code generation diễn ra.

Nếu cần đăng ký bean theo generic type, hãy dùng `RootBeanDefinition#setTargetType(ResolvableType)` như mục trước. Nếu cần constructor hoặc factory method cụ thể, khai báo bean class và factory method rõ ràng thay vì chỉ lưu một instance đã tạo sẵn.

### 7.1. Tránh đăng ký instance đã tạo sẵn bằng `registerSingleton`

Ví dụ sau tạo object trước khi container có bean definition để phân tích:

```java
PaymentClient client = createClientFromRuntimeState();

beanFactory.registerSingleton("paymentClient", client);
```

AOT không thể chuyển đổi singleton đã đăng ký trực tiếp thành quy trình tạo bean có thể tái tạo. Nó chỉ thấy instance có sẵn trong quá trình build, không có mô tả đầy đủ để khởi tạo object tương đương khi native executable chạy.

Thay bằng bean definition hoặc `@Bean` factory method:

```java
@Bean
PaymentClient paymentClient(
        PaymentClientProperties properties,
        HttpClient httpClient) {
    return createClient(properties, httpClient);
}
```

Nếu logic tạo client cần đọc cấu hình runtime, inject properties hoặc abstraction cần thiết vào factory method. Không gọi external service trong AOT phase để lấy object rồi đăng ký singleton.

### 7.2. Tránh `BeanDefinition#setInstanceSupplier` tùy biến

Một bean definition dùng lambda hoặc method reference làm instance supplier có thể hoạt động trên JVM:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(PaymentClient.class);

definition.setInstanceSupplier(
        () -> createClientFromRuntimeState());

registry.registerBeanDefinition("paymentClient", definition);
```

Nhưng Spring AOT không thể chuyển đổi instance supplier tùy biến này thành mã khởi tạo tĩnh theo cơ chế thông thường. Hãy ưu tiên `beanClass`, constructor metadata hoặc factory method có kiểu rõ ràng. Nếu thư viện cần đóng góp logic khởi tạo đặc biệt cho AOT, hãy xem xét AOT contribution API thay vì kỳ vọng AOT có thể phân tích nội dung lambda.

Lưu ý: AOT code generation tự sinh instance supplier cho bean definitions đã phân tích là một phần triển khai nội bộ bình thường. Giới hạn ở đây nói về supplier do ứng dụng tự gắn vào bean definition trước AOT processing.

## 8. Chọn đúng extension point cho AOT

Nếu thư viện hoặc integration module tự đăng ký bean, có thể cần đóng góp cả bean definitions và mã tái tạo hành vi ở runtime. Chọn extension point theo trách nhiệm:

| API | Trách nhiệm | Khi nên dùng |
|---|---|---|
| `ImportBeanDefinitionRegistrar` | Đăng ký bean definitions trong quá trình phân tích configuration | Thêm bean từ annotation/import hoặc module integration |
| `BeanDefinitionRegistryPostProcessor` | Thay đổi registry trước khi factory xử lý bean definitions | Hạ tầng hiện có cần điều chỉnh registry |
| `BeanFactoryInitializationAotProcessor` | Đóng góp mã khởi tạo bean factory và RuntimeHints | Cần tái tạo một hành vi infrastructure ở AOT |
| `BeanRegistrationAotProcessor` | Đóng góp code/hints cho từng bean registration | Cần xử lý đặc biệt theo bean definition |
| `RuntimeHintsRegistrar` | Đăng ký reflection, resource, serialization, JDK proxy hints | Bean đã được nhận diện nhưng Native Image thiếu metadata |

`BeanFactoryInitializationAotProcessor` có thể được đăng ký trong `META-INF/spring/aot.factories` bằng key là fully qualified name của interface. Nó cũng có thể được khai báo như bean; trong trường hợp đó, processor và dependency của nó được khởi tạo trong AOT phase, rồi bean processor được loại khỏi AOT-optimized context vì đóng góp của nó đã được áp dụng.

`BeanRegistrationAotProcessor` cũng là extension point hạ tầng. Nếu chính bean implement interface này, bean và dependency của nó được khởi tạo trong AOT processing. Spring khuyến nghị giới hạn những processor này ở infrastructure beans có dependency nhỏ và đã được khởi tạo sớm. Nếu khai báo qua `@Bean`, factory method nên là `static` để không phải khởi tạo enclosing configuration class. [Spring Framework — AOT Contributions](https://docs.spring.io/spring-framework/reference/core/aot.html)

Không tự viết AOT processor chỉ để sửa một `@Bean` có return type quá rộng. Trước hết hãy sửa bean definition gốc. Custom AOT processor dành cho thư viện hoặc hạ tầng thật sự cần tái tạo một hành vi đặc biệt.

## 9. Điều kiện `@Profile` và `@Conditional` được quyết định ở build time

Spring AOT phân tích ApplicationContext theo classpath và Environment có tại thời điểm build. Các điều kiện quyết định bean có tồn tại hay không được đánh giá trong quá trình đó.

Ví dụ:

```java
@Bean
@ConditionalOnProperty(
        prefix = "payment",
        name = "gateway",
        havingValue = "external")
ExternalPaymentGateway externalPaymentGateway() {
    return new ExternalPaymentGateway();
}
```

Nếu property không có hoặc có giá trị khác khi chạy AOT, bean có thể không được đưa vào generated context. Đặt `PAYMENT_GATEWAY=external` sau khi image đã được build không thể thêm bean definition đã bị loại khỏi output.

Cần phân biệt:

- **Cấu hình chọn bean:** profile/condition quyết định bean nào được tạo. Giá trị phải được cung cấp cho AOT build.
- **Cấu hình vận hành bean:** endpoint, timeout, credential hoặc feature data được bean đọc khi runtime. Các giá trị này có thể tiếp tục được externalize nếu không làm thay đổi tập bean definitions.

Ví dụ cấu hình profile cho Maven AOT execution:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <configuration>
                <profiles>native</profiles>
            </configuration>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Cấu hình thực tế phụ thuộc build plugin và profile của dự án. Kiểm tra effective POM và log `process-aot` để xác nhận profile/property nào được dùng.

Với Gradle, cấu hình profile cho task AOT bằng argument của `ProcessAot` task:

```groovy
tasks.withType(org.springframework.boot.gradle.tasks.aot.ProcessAot).configureEach {
    args('--spring.profiles.active=profile-a,profile-b')
}
```

Spring Boot ghi rõ `@Conditional` được đánh giá khi AOT và profile cũng bị ảnh hưởng. Các bean được tạo trong AOT phase sẽ được tạo khi ứng dụng chạy với AOT; không thể bật/tắt lại chúng bằng cách thay property runtime. [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/how-to/aot.html)

### 9.1. Một binary cho nhiều môi trường

Nếu một binary phải chạy ở nhiều môi trường nhưng có các implementation khác nhau, có ba cách thiết kế:

1. Tạo artifact AOT riêng cho mỗi tập profile/condition nếu cấu trúc bean khác nhau.
2. Đăng ký một implementation ổn định, inject properties/runtime strategy và chọn hành vi bằng cấu hình runtime.
3. Đưa các implementation vào cùng một bean graph khi tất cả đều cần có mặt, sau đó chọn bằng một strategy bean có kiểu xác định.

Không cố dùng runtime profile để thay đổi cấu trúc context đã được cố định trong generated initializer.

## 10. Bean registration động và plugin discovery

Một ứng dụng JVM có thể scan classpath hoặc plugin directory lúc khởi động rồi tạo bean cho từng implementation tìm được. Trong native image, classpath và tập type được phân tích tại build time. Không thể giả định runtime scan sẽ tìm được class mới mà Native Image không đưa vào executable.

Nếu plugin là một phần của sản phẩm:

- Xác định danh sách plugin trước khi chạy AOT.
- Đăng ký bean definitions bằng configuration/import registrar.
- Giữ plugin classes trên build classpath.
- Khai báo concrete type và generic type của từng plugin.
- Tạo AOT artifact tương ứng với tập plugin được hỗ trợ.
- Nếu plugin được nạp từ file ngoài, xem xét tách plugin thành process/service riêng thay vì kỳ vọng native executable tự load class mới.

`BeanDefinitionRegistryPostProcessor` có thể tham gia quá trình AOT nếu được gọi trong lúc configuration được xử lý. Tuy nhiên, nếu chính processor được đăng ký như một bean, nó có thể được gọi lại khi ứng dụng chạy. Nếu cần thay thế hành vi runtime bằng generated code, processor phải đóng góp AOT phù hợp, chẳng hạn implement `BeanFactoryInitializationAotProcessor`. Spring Framework khuyến nghị `ImportBeanDefinitionRegistrar` cho trường hợp thông thường cần đăng ký bean từ configuration. [Spring Framework — Programmatic Bean Registration](https://docs.spring.io/spring-framework/reference/core/aot.html)

## 11. Xử lý circular dependency trước khi tối ưu AOT

Một số circular dependency có thể vô tình hoạt động trên JVM nhờ field injection hoặc setter injection. AOT-optimized context không hỗ trợ các explicit circular dependencies theo cách runtime truyền thống có thể xử lý.

Ví dụ chu trình:

```text
OrderService -> InventoryService -> ReservationService -> OrderService
```

Nên sửa thiết kế để tách trách nhiệm hoặc chuyển một dependency thành truy cập lazy có kiểm soát.

Dùng `ObjectProvider` khi bean chỉ cần được lấy tại thời điểm một operation cụ thể:

```java
@Service
class ReservationService {

    private final ObjectProvider<OrderService> orderServiceProvider;

    ReservationService(
            ObjectProvider<OrderService> orderServiceProvider) {
        this.orderServiceProvider = orderServiceProvider;
    }

    void confirm(Reservation reservation) {
        OrderService orderService = orderServiceProvider.getObject();
        orderService.markReserved(reservation.orderId());
    }
}
```

`@Lazy` trên injection point cũng có thể trì hoãn việc resolve dependency. Tuy nhiên, đây nên là giải pháp cho dependency thực sự cần lazy access; nếu hai service gọi qua lại liên tục, hãy tách phần nghiệp vụ chung thành một service thứ ba để loại bỏ vòng phụ thuộc.

## 12. RuntimeHints không sửa được bean type prediction

Khi bean definition đã rõ, nhưng native image báo lỗi vì reflection, resource hoặc proxy, hãy bổ sung metadata tương ứng. Ví dụ:

```java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                PaymentSerializer.class,
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

Kích hoạt registrar:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
class PaymentNativeConfiguration {
}
```

Đoạn này giúp Native Image giữ constructor và public methods cần reflection. Nó không giúp Spring biết `PaymentSerializer` là product type của một `FactoryBean`, không tạo lại singleton đã đăng ký trực tiếp và không biến một supplier tùy biến thành mã khởi tạo AOT.

Hãy chọn đúng công cụ:

| Vấn đề | Cách xử lý |
|---|---|
| `@Bean` return type quá rộng | Khai báo concrete return type |
| Generic bị mất | Dùng generic signature đầy đủ và `ResolvableType` |
| `FactoryBean` không rõ product type | Resolve generic và khai báo `getObjectType()` |
| Bean đăng ký sau AOT hoặc bằng singleton | Đăng ký `BeanDefinition` trong configuration phase |
| Supplier tùy biến | Dùng constructor/factory method có thể phân tích hoặc AOT contribution |
| Bean bị condition loại khỏi AOT | Cung cấp profile/property cho build hoặc thiết kế graph ổn định |
| Constructor/member reflection bị thiếu | Đăng ký RuntimeHints đúng thao tác |
| Resource không có trong image | Đăng ký resource hints hoặc chuyển sang external file phù hợp |

## 13. Quy trình chẩn đoán khi AOT không nhận diện bean

Hãy chẩn đoán từ bean definition gốc, sau đó mới xem generated code và native runtime.

### Bước 1: Xác định bean name và nguồn đăng ký

Tìm nơi bean được khai báo:

- Annotation component như Component, Service hoặc Repository.
- Bean factory method.
- Import hoặc ImportBeanDefinitionRegistrar.
- BeanDefinitionRegistryPostProcessor.
- FactoryBean.
- Đăng ký trực tiếp bằng registerSingleton hoặc setInstanceSupplier.

Nếu bean chỉ xuất hiện sau khi một callback chạy ở runtime, AOT có thể không nhìn thấy bean definition đó. Xác định callback có chạy trong AOT configuration phase hay không.

### Bước 2: Kiểm tra kiểu mà BeanFactory dự đoán

Có thể dùng ConfigurableListableBeanFactory trong một test hoặc infrastructure diagnostic để xem type prediction:

```java
ConfigurableListableBeanFactory beanFactory =
        applicationContext.getBeanFactory();

Class<?> predictedType =
        beanFactory.getType("paymentClient", false);

ResolvableType productType =
        beanFactory.getBeanDefinition("paymentClient")
                .getResolvableType();

System.out.println("predictedType=" + predictedType);
System.out.println("resolvableType=" + productType);
```

Tham số allowFactoryBeanInit=false tránh yêu cầu khởi tạo FactoryBean chỉ để tìm product type. Kết quả có thể là null nếu container chưa thể dự đoán. Đừng gọi getBean() trong bước chẩn đoán chỉ để xem kiểu, vì việc đó có thể che khuất vấn đề bằng cách tạo instance sớm.

Nếu bean là FactoryBean, kiểm tra riêng factory type và product type. Nếu bean có generic, kiểm tra ResolvableType thay vì chỉ nhìn Class.

### Bước 3: Kiểm tra profile và condition của AOT build

Ghi lại:

- Active profiles trong AOT phase.
- Environment properties ảnh hưởng Conditional.
- Classpath và dependency version khi chạy AOT.
- Các profile/property runtime có khác với build không.

Bật debug log hoặc đọc condition evaluation report khi nghi ngờ auto-configuration bị loại. Nếu bean không có trong AOT bean definitions, hãy xác định condition nào đã loại nó.

### Bước 4: Chạy AOT processing riêng

Với Maven, khi plugin đã cấu hình goal process-aot, có thể chạy:

```bash
mvn -Pnative spring-boot:process-aot
```

Với Gradle Spring Boot plugin:

```bash
./gradlew processAot
```

Tên task/profile và cách truyền profile có thể khác theo cấu hình dự án. Dùng log của plugin để xác nhận AOT task thực sự chạy và sử dụng đúng Environment.

### Bước 5: Đọc generated sources

Tìm generated initializer và bean definition classes. Tên class thường có dạng:

- PaymentConfiguration__BeanDefinitions
- PaymentApplication__ApplicationContextInitializer
- Các generated bean factory registrations hoặc contribution classes.

Thư mục output thay đổi theo Spring Boot/build plugin version. Maven thường đặt output dưới target/spring-aot/; Gradle thường dùng các thư mục build/generated/aotSources, aotClasses và aotResources. Dùng đường dẫn trong build log của dự án hiện tại thay vì giả định một path cố định.

Kiểm tra generated code:

- Bean name có được đăng ký không?
- Bean definition có concrete target type không?
- Factory method nào được gọi để tạo instance?
- Constructor arguments và dependency có đúng không?
- Có bean nào bị loại do condition/profile?
- Có generated code cho processor/registrar dự kiến không?

Nếu bean không xuất hiện ở đây, thêm reflection hints sẽ không giải quyết nguyên nhân.

### Bước 6: Chạy AOT-processed application trên JVM

Sau khi build artifact chứa AOT output, có thể chạy với AOT mode bật:

```bash
java -Dspring.aot.enabled=true -jar target/payment-api.jar
```

Với Gradle, thay bằng đường dẫn JAR thực tế trong build/libs/. AOT mode trên JVM giúp phát hiện lỗi generated initializer và bean registration trước khi native compilation. Nó không thay thế native runtime tests, nhưng giúp thu hẹp phạm vi lỗi.

### Bước 7: Chạy native executable

Khi AOT-processed JVM context khởi động đúng, build native executable và kiểm tra các bean/use case liên quan. Nếu chỉ native runtime thất bại, phân loại lại vấn đề: reflection, resource, proxy, JNI, serialization, dynamic class loading hoặc thư viện chưa có reachability metadata.

## 14. Đọc lỗi theo dấu hiệu

| Dấu hiệu | Khả năng cao | Việc cần kiểm tra trước |
|---|---|---|
| Bean không xuất hiện trong generated initializer | Condition/profile không được bật hoặc registration diễn ra quá muộn | AOT Environment và registration callback |
| Type prediction trả về interface/Object | Bean factory method return type quá rộng | Concrete factory method return type |
| Type prediction trả về null cho product | FactoryBean không resolve product type | Generic parameter và getObjectType() |
| ResolvableType là raw/unresolved | Generic type bị xóa hoặc bean definition thiếu target type | Generic signature, setTargetType |
| Supplier lambda không được AOT chuyển đổi | Custom instance supplier | Thay bằng constructor/factory method hoặc AOT contribution |
| Bean chỉ có khi chạy JVM thường | Singleton registration hoặc runtime classpath scanning | Chuyển sang bean definitions có thể phân tích ở build time |
| Bean có trong generated code nhưng startup báo circular dependency | Explicit circular dependency | Tách service, dùng ObjectProvider/@Lazy có chủ đích |
| AOT JVM chạy được nhưng native báo NoSuchMethodException | Reflection metadata thiếu | RuntimeHints cho đúng constructor/method |
| Native báo ClassNotFoundException | Type không có trong native image hoặc dependency/classpath sai | Build classpath và reachability |
| Native báo resource không tìm thấy | Classpath resource chưa được include | Resource hints hoặc external file |
| Runtime profile không bật bean | Profile/condition đã được quyết định khi AOT | Tạo artifact theo profile hoặc giữ bean graph ổn định |

Không có một thông báo lỗi duy nhất cho mọi trường hợp “AOT không suy ra được bean”. Hãy dựa vào nguồn bean definition, type prediction và generated code để xác định chính xác giai đoạn thất bại.

## 15. Những cách sửa dễ gây lỗi mới

### 15.1. Đổi mọi return type thành implementation cụ thể một cách máy móc

Chỉ khai báo concrete type khi factory thực sự luôn tạo implementation đó. Nếu factory có nhiều kết quả, tách factory methods hoặc thiết kế strategy bean ổn định. Khai báo type không đúng có thể làm container dự đoán sai type và ảnh hưởng autowiring.

### 15.2. Thêm reflection hints cho toàn bộ package

Reflection hints không khắc phục bean không được đăng ký hoặc product type không rõ. Chỉ đăng ký constructor/member mà thư viện thực sự gọi qua reflection, và dùng RuntimeHintsPredicates để kiểm tra.

### 15.3. Ép tạo bean trong AOT để lấy kiểu

Gọi getBean() trong BeanFactoryPostProcessor hoặc AOT callback chỉ để xem concrete class có thể kích hoạt constructor, kết nối database hoặc gọi dịch vụ ngoài trong build. Hãy mô tả type trên bean definition; không cần tạo instance để suy ra kiểu.

### 15.4. Dựa vào classpath scan lúc runtime

Native image không cung cấp classpath linh hoạt như JVM. Nếu plugin hoặc implementation phải được phát hiện, hãy scan/đăng ký khi AOT processing diễn ra và bảo đảm class nằm trong build input.

### 15.5. Dùng circular dependency để giữ nguyên cấu trúc service

AOT có thể phát hiện vòng phụ thuộc mà JVM thường xử lý được. Dùng Lazy hoặc ObjectProvider khi cần trì hoãn truy cập; ưu tiên tách trách nhiệm nếu vòng phụ thuộc phản ánh thiết kế service chưa hợp lý.

## 16. Checklist trước khi build Native Image

- [ ] Mọi bean quan trọng đều có nguồn đăng ký xác định trong AOT phase.
- [ ] Bean factory methods khai báo kiểu trả về cụ thể nhất có thể.
- [ ] Consumer vẫn inject theo interface khi phù hợp.
- [ ] Bean có nhiều constructor đã xác định constructor được sử dụng.
- [ ] Generic signatures không bị raw type hoặc unresolved type làm mất thông tin.
- [ ] FactoryBean công bố product type cụ thể bằng generic đã resolve và/hoặc getObjectType().
- [ ] Programmatic registration dùng BeanDefinitionRegistry và bean definitions có target type rõ.
- [ ] Không dựa vào registerSingleton để tạo bean cần tái tạo trong native runtime.
- [ ] Không gắn custom instanceSupplier mà kỳ vọng AOT tự chuyển đổi lambda.
- [ ] Không tạo prototype bean bằng custom getBean arguments nếu có thể dùng factory bean.
- [ ] Profile và condition properties được cung cấp đúng trong AOT build.
- [ ] Plugin discovery/bean registration diễn ra trước code generation.
- [ ] Infrastructure AOT processors chỉ được dùng khi cần và có dependency tối thiểu.
- [ ] Không có explicit circular dependencies chưa được xử lý.
- [ ] Generated bean definitions và initializer đã được kiểm tra.
- [ ] AOT-processed application chạy được trên JVM.
- [ ] RuntimeHints chỉ được thêm cho reflection/resource/proxy thực sự cần thiết.
- [ ] Native executable đã chạy integration tests cho các bean và use case bị ảnh hưởng.

## 17. Ghi nhớ

Spring AOT cần biết bean nào tồn tại, bean có kiểu gì và tạo instance bằng cách nào trước khi native executable được build. Hãy bắt đầu bằng việc làm rõ bean definitions: khai báo concrete return type, giữ generic metadata bằng ResolvableType, công bố product type của FactoryBean, và đăng ký bean programmatically trong configuration phase.

Các supplier tùy biến, singleton tạo sẵn, plugin chỉ được scan lúc runtime và điều kiện profile/property khác với AOT build đều có thể khiến generated context không phản ánh ứng dụng mong muốn. Khi đó, kiểm tra type prediction và generated initializer trước khi thêm RuntimeHints. Chỉ sau khi bean registration/instantiation đã đúng mới xử lý reflection, resource hoặc proxy metadata còn thiếu.

### Tài liệu tham khảo

- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework — ResolvableType Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/ResolvableType.html)
- [Spring Framework — BeanFactoryInitializationAotProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/aot/BeanFactoryInitializationAotProcessor.html)
- [Spring Framework — BeanRegistrationAotProcessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/aot/BeanRegistrationAotProcessor.html)
- [Spring Boot — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/how-to/aot.html)
- [Spring Boot — Ahead-of-Time Processing with the JVM](https://docs.spring.io/spring-boot/reference/packaging/aot.html)
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
