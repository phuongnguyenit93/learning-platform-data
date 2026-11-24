# InstanceSupplier, constructor và đường tạo bean được sinh

Trong ứng dụng Spring Boot, Spring IoC Container tạo bean từ các **bean definition** đã đăng ký. Khi dùng **Spring AOT** để chuẩn bị ứng dụng cho **GraalVM Native Image**, Spring phân tích các definition trong giai đoạn build và sinh mã Java để tái tạo cách đăng ký, khởi tạo và một số thao tác injection cần thiết. Một thành phần quan trọng của đường khởi tạo được sinh đó là **instance supplier**.

Trong chương **Bean và AOT** của module **`SPRING_BOOT_NATIVE_IMAGE`**, bài học này giải thích `InstanceSupplier`, `BeanInstanceSupplier`, cách Spring biểu diễn constructor và factory method, cách dependency được đưa vào constructor, và cách đọc generated source để hiểu container sẽ tạo bean ra sao. Đây là nền tảng để xử lý các trường hợp AOT không suy luận được, giảm phụ thuộc vào reflection và giúp Native Image phân tích ứng dụng chính xác hơn.

> **Phạm vi phiên bản:** `BeanInstanceSupplier` thuộc API AOT của Spring Framework từ dòng 6.0. Mã nguồn được sinh chính xác có thể thay đổi theo phiên bản Spring Framework/Spring Boot và loại bean definition. Các đoạn generated code trong bài là ví dụ minh họa dựa trên cấu trúc API; hãy đọc file được sinh từ chính phiên bản dự án khi debug.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **bean definition**, **bean instance** và **instance supplier**.
- Giải thích vì sao Spring AOT sinh supplier thay vì phải dò constructor/factory method động ở mọi lần khởi động.
- Đọc cấu trúc `BeanInstanceSupplier.forConstructor(...)` và `forFactoryMethod(...)`.
- Hiểu cách constructor injection, `@Bean` factory method và các thành viên `@Autowired` tham gia vào đường tạo bean.
- Nhận biết những cấu hình khó chuyển thành mã AOT, như custom instance supplier tự viết, custom arguments, nhiều constructor mơ hồ và đăng ký bean động.
- Biết cách truy vết generated bean definitions và sửa cấu hình nguồn để AOT xử lý ổn định.

## 2. Bean definition và bean instance khác nhau thế nào?

**Bean definition** là mô tả cho container biết cần quản lý một bean như thế nào: bean type, scope, constructor/factory method, dependency, lazy initialization, lifecycle callbacks và các metadata liên quan.

**Bean instance** là đối tượng Java thực tế được tạo từ bean definition. Ví dụ, `OrderService` là class; bean definition mô tả cách tạo `OrderService`; instance là một object `OrderService` cụ thể trong ApplicationContext.

Ví dụ:

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Khi Spring quét cấu hình ứng dụng, container đăng ký bean definition cho `OrderService`. Với singleton bean, object thường được tạo khi ApplicationContext khởi tạo (trừ khi lazy hoặc có cơ chế trì hoãn). Với prototype, object được tạo mỗi lần yêu cầu. Bean definition mô tả **cách tạo**, còn instance là **kết quả tạo**.

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Bean definition | Bean này có kiểu gì, scope nào, tạo bằng cách nào? | `RootBeanDefinition(OrderService.class)` |
| Instance supplier | Khi cần instance, gọi logic nào để tạo object? | Constructor reference hoặc `BeanInstanceSupplier` |
| Bean instance | Object thực tế nào đã được tạo? | `new OrderService(repository)` |

## 3. InstanceSupplier là gì?

**Instance supplier** là hàm/cơ chế được gắn với bean definition để tạo instance khi container cần. Thay vì chỉ lưu class rồi để container phải suy luận constructor hoặc factory method bằng reflection, bean definition có thể chỉ định một supplier rõ ràng.

Về mặt ý tưởng:

~~~java
Supplier<OrderService> supplier =
        () -> new OrderService(orderRepository);
~~~

Đoạn code trên chỉ minh họa vai trò của supplier. Trong Spring AOT, supplier được tạo theo ngữ cảnh bean và dependency thực tế; nó không nhất thiết là `java.util.function.Supplier` đơn giản.

Spring Framework cung cấp `BeanInstanceSupplier<T>`, một implementation chuyên biệt của `InstanceSupplier<T>`. Nó lưu thông tin executable dùng để tạo bean (constructor hoặc factory method), hỗ trợ phân giải các đối số cần autowire và được dùng như một cách khởi tạo có mục tiêu thay cho cách injection dựa hoàn toàn vào reflection.

| API | Ý nghĩa |
|---|---|
| `BeanInstanceSupplier.forConstructor(...)` | Tạo supplier cho constructor có các kiểu tham số đã xác định |
| `BeanInstanceSupplier.forFactoryMethod(...)` | Tạo supplier cho factory method, ví dụ phương thức `@Bean` |
| `withGenerator(...)` | Chỉ định mã tạo instance; có thể nhận `RegisteredBean` và các đối số đã được phân giải |
| `get(RegisteredBean)` | Container yêu cầu supplier tạo instance cho bean đang đăng ký |

Nếu `BeanInstanceSupplier` không được cung cấp generator, nó có thể dùng reflection để tạo instance và đóng góp invocation hints tương ứng. Khi AOT có thể xác định constructor/factory method, generated generator cho phép biểu diễn thao tác tạo bean trực tiếp hơn. Vì vậy, sự hiện diện của `BeanInstanceSupplier` tự nó chưa đủ để kết luận mọi lời gọi đều không dùng reflection; hãy xem phần `withGenerator(...)` trong generated source.

Supplier **không phải bean được tạo sẵn trong giai đoạn build**. Nó là logic tạo bean được sinh và lưu trong bean definition. Khi ứng dụng chạy và container cần instance, supplier mới được gọi theo scope/lifecycle của bean.

## 4. Spring AOT phân tích bean như thế nào?

Trong runtime thông thường, Spring đọc cấu hình, xử lý component scan, phân tích `@Configuration`, tìm constructor phù hợp, phân giải dependency và khởi tạo bean. Một số bước cần metadata hoặc reflection.

Với Spring AOT, engine tạo một ApplicationContext phục vụ **AOT processing**. Context này được refresh ở chế độ đặc biệt: các cấu hình và bean definition được phân tích, điều kiện được đánh giá, nhưng **các bean ứng dụng thông thường không được khởi tạo**. Từ các definition đã biết, AOT engine tạo source code, bytecode cần thiết và Runtime Hints.

~~~mermaid
flowchart TD
    A["@Configuration / component scan / @Bean"] --> B["AOT ApplicationContext"]
    B --> C["Phân tích và đăng ký bean definitions"]
    C --> D["Xác định constructor hoặc factory method"]
    D --> E["Sinh InstanceSupplier / BeanInstanceSupplier"]
    E --> F["Sinh bean definition registration code"]
    F --> G["Compile generated sources"]
    G --> H["Native Image phân tích và biên dịch"]
    H --> I["Native executable"]
    I --> J["Runtime: container gọi supplier khi cần bean"]
    J --> K["Bean instance + injection/lifecycle"]
~~~

Điểm cần nhớ:

1. **Build time:** Spring phân tích cấu hình và sinh mã tái tạo bean definition cùng đường tạo instance.
2. **Runtime:** Spring sử dụng mã AOT đã sinh, gọi supplier khi cần tạo bean.
3. **Không phải mọi bean đều được khởi tạo ở build time.** Việc phân tích definition không đồng nghĩa tạo object production rồi đóng object đó vào image heap.

Một số infrastructure bean tham gia trực tiếp vào AOT processor có thể được khởi tạo để thực hiện nhiệm vụ xử lý build. Đây là trường hợp đặc biệt của hạ tầng AOT, không phải cách hiểu chung rằng Spring tạo toàn bộ bean ứng dụng lúc build.

### Những quyết định nào được cố định ở build time?

AOT làm việc với classpath và cấu hình ứng dụng đã xác định. Những bean definition chịu ảnh hưởng bởi `@Profile` hoặc `@Conditional` được đánh giá trong lúc AOT processing; profile/property có ảnh hưởng đến việc bean có tồn tại hay không cần được chọn phù hợp ở build time. Ứng dụng AOT không thể tùy ý thay toàn bộ tập bean definition theo một classpath hoặc profile khác lúc runtime.

Nếu bean chỉ được đăng ký bởi logic chạy sau khi context đã được tạo theo cách AOT không quan sát được, generated registration có thể không chứa bean đó. Hãy đưa logic đăng ký vào cơ chế mà AOT nhận biết.

## 5. Constructor injection trở thành supplier như thế nào?

Xét hai class:

~~~java
@Repository
public class OrderRepository {
    public OrderRepository() {
    }
}
~~~

~~~java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
~~~

Spring biết `OrderService` cần một `OrderRepository` thông qua constructor. AOT có thể xác định constructor cần gọi và kiểu dependency cần phân giải.

### Ví dụ hình dạng supplier cho constructor

Đoạn dưới đây mô tả một generated supplier theo API `BeanInstanceSupplier`:

~~~java
private static BeanInstanceSupplier<OrderService> orderServiceInstanceSupplier() {
    return BeanInstanceSupplier.<OrderService>forConstructor(OrderRepository.class)
            .withGenerator((registeredBean, args) ->
                    new OrderService(args.get(0, OrderRepository.class)));
}
~~~

Ý nghĩa:

- `forConstructor(OrderRepository.class)` chỉ ra constructor có tham số kiểu `OrderRepository`.
- `BeanInstanceSupplier` yêu cầu container phân giải đối số constructor theo dependency của bean.
- `args.get(0, OrderRepository.class)` lấy dependency đã được phân giải ở vị trí tham số thứ nhất.
- `new OrderService(...)` là lệnh tạo object trực tiếp, có thể được compiler phân tích mà không cần dò constructor động tại mỗi lần tạo bean.

Một bean definition được đăng ký với supplier đó có thể có hình dạng rút gọn:

~~~java
RootBeanDefinition beanDefinition =
        new RootBeanDefinition(OrderService.class);
beanDefinition.setInstanceSupplier(orderServiceInstanceSupplier());
~~~

Đây là **mẫu giải thích cơ chế**, không phải cam kết tên class hoặc phương thức mà mọi bản Spring AOT sẽ sinh ra. Generated code thực tế có thể tách supplier thành phương thức riêng, dùng method reference hoặc có thêm đoạn xử lý field/method injection và lifecycle.

### Constructor được chọn ra sao?

Spring cần biết constructor nào là đường tạo bean. Một số nguyên tắc thực hành:

- Nếu class có **một constructor duy nhất**, Spring có thể dùng constructor đó cho constructor injection mà không cần `@Autowired`.
- Nếu có nhiều constructor, hãy đánh dấu constructor mong muốn bằng `@Autowired` khi phù hợp; tránh để việc lựa chọn trở nên mơ hồ.
- Constructor nên khai báo dependency cần thiết một cách rõ ràng và có kiểu cụ thể.
- Tránh dùng các cấu trúc tham số phức tạp mà AOT không thể biểu diễn thành mã tạo giá trị một cách đáng tin cậy, đặc biệt trong bean definition đăng ký thủ công.

Ví dụ có nhiều constructor:

~~~java
@Service
public class ReportService {
    private final ReportRepository repository;

    @Autowired
    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    public ReportService() {
        this.repository = null;
    }
}
~~~

Ví dụ này làm rõ ý định lựa chọn constructor, nhưng constructor mặc định gán `null` chỉ để minh họa; trong ứng dụng thực tế, nên thiết kế class sao cho mọi đường tạo hợp lệ đều nhận dependency cần thiết. Nếu không cần nhiều constructor, giữ một constructor duy nhất thường rõ ràng hơn.

## 6. `@Bean` factory method cũng có InstanceSupplier

Bean không nhất thiết được tạo bằng constructor trực tiếp của class. Một `@Bean` factory method có thể tạo và cấu hình object:

~~~java
@Configuration(proxyBeanMethods = false)
public class DataSourceConfiguration {

    @Bean
    public SimpleDataSource dataSource() {
        return new SimpleDataSource();
    }
}
~~~

Ở đây:

- `DataSourceConfiguration` là bean cấu hình.
- `dataSource()` là factory method.
- `SimpleDataSource` là kiểu của bean được trả về.

Spring AOT có thể sinh supplier dùng `BeanInstanceSupplier.forFactoryMethod(...)`. Hình dạng gần với generated code chính thức:

~~~java
private static BeanInstanceSupplier<SimpleDataSource> dataSourceInstanceSupplier() {
    return BeanInstanceSupplier.<SimpleDataSource>
            forFactoryMethod(DataSourceConfiguration.class, "dataSource")
            .withGenerator((registeredBean) ->
                    registeredBean.getBeanFactory()
                            .getBean(DataSourceConfiguration.class)
                            .dataSource());
}
~~~

Supplier trên gọi factory method `dataSource()` trên bean cấu hình đã được container quản lý. Bean definition của `SimpleDataSource` sẽ sử dụng supplier này khi cần tạo instance.

### Factory method có tham số

Ví dụ factory method phụ thuộc một bean khác:

~~~java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean
    public PaymentClient paymentClient(PaymentProperties properties) {
        return new PaymentClient(properties.endpoint());
    }
}
~~~

Trong generated code, Spring có thể dùng `forFactoryMethod(...)` để mô tả factory method cùng kiểu tham số, sau đó dùng generator nhận `RegisteredBean` và các đối số đã phân giải. Mã minh họa:

~~~java
BeanInstanceSupplier.<PaymentClient>forFactoryMethod(
        ClientConfiguration.class,
        "paymentClient",
        PaymentProperties.class)
    .withGenerator((registeredBean, args) ->
            registeredBean.getBeanFactory()
                    .getBean(ClientConfiguration.class)
                    .paymentClient(args.get(0, PaymentProperties.class)));
~~~

Đoạn này tập trung vào ý tưởng phân giải tham số và gọi factory method. Cách code generator tối ưu lời gọi có thể khác tùy bản Spring Framework và cấu hình `@Configuration`.

## 7. Đường tạo bean được sinh gồm những phần nào?

Khi đọc một class generated có tên dạng `...__BeanDefinitions`, thường cần tìm các thành phần:

1. **Bean type:** kiểu thực tế mà definition công bố.
2. **Bean definition:** metadata được tạo, thường là `RootBeanDefinition` hoặc API đăng ký tương đương.
3. **Instance supplier:** supplier được gắn vào definition qua `setInstanceSupplier(...)` hoặc API tương đương.
4. **Constructor/factory method:** executable tạo object, có thể là constructor reference, factory method hoặc `BeanInstanceSupplier`.
5. **Injection code:** các field/method được `@Autowired` có thể được xử lý bằng code/hook sinh ra trong quá trình AOT.
6. **Initialization/lifecycle metadata:** các callback init/destroy, post-processing và proxy cần thiết vẫn phải được bảo toàn.

Không phải mọi bean đều có cùng một mẫu. Một class có constructor không tham số có thể dùng method reference đơn giản:

~~~java
beanDefinition.setInstanceSupplier(MyConfiguration::new);
~~~

Một bean tạo bằng factory method có thể dùng `BeanInstanceSupplier`. Một bean có nhiều constructor arguments cần supplier có khả năng phân giải đối số. Một bean cần injection qua field hoặc method có thể có generated code bổ sung.

**Supplier chỉ giải quyết phần tạo instance.** Container vẫn chịu trách nhiệm về scope, quan hệ phụ thuộc, post-processors, AOP proxy, callback khởi tạo và hủy theo bean definition.

## 8. Injection qua field và method trong AOT

Ví dụ:

~~~java
@Component
public class NotificationService {

    @Autowired
    private MessageGateway gateway;

    @Autowired
    public void setClock(Clock clock) {
        // ...
    }
}
~~~

Ở runtime thông thường, Spring có thể dùng `AutowiredAnnotationBeanPostProcessor` để tìm các điểm injection. Trong AOT, processor này tham gia vào quá trình đăng ký AOT và có thể sinh code để thực hiện các thao tác cần thiết một cách rõ ràng hơn.

Vì vậy, khi đọc generated code, đừng chỉ tìm `new NotificationService(...)`. Hãy kiểm tra các phần xử lý member injection nếu bean sử dụng `@Autowired` trên field hoặc method. Constructor injection thường dễ nhìn và dễ biểu diễn hơn, đồng thời giúp dependency trở thành trạng thái `final` rõ ràng.

Ví dụ ưu tiên constructor injection:

~~~java
@Component
public class NotificationService {
    private final MessageGateway gateway;
    private final Clock clock;

    public NotificationService(MessageGateway gateway, Clock clock) {
        this.gateway = gateway;
        this.clock = clock;
    }
}
~~~

Với cách này, toàn bộ dependency cần thiết xuất hiện ngay trong chữ ký constructor, giúp AOT xác định đường tạo bean trực tiếp.

## 9. Bean type cần được khai báo cụ thể

Spring AOT cần biết chính xác loại bean để phân tích những đặc điểm như annotation, lifecycle method, injection point hoặc proxy.

Ví dụ chưa tối ưu:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    public PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
~~~

Phương thức khai báo kiểu trả về là `PaymentGateway`, trong khi object thực tế là `StripePaymentGateway`. Nếu implementation có annotation hoặc phương thức đặc biệt mà AOT cần nhận diện, việc chỉ công bố interface có thể khiến các thông tin đó không được xử lý đầy đủ.

Nên khai báo kiểu cụ thể khi có thể:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    public StripePaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
~~~

Consumer vẫn có thể inject theo interface:

~~~java
public CheckoutService(PaymentGateway gateway) {
    this.gateway = gateway;
}
~~~

Điểm quan trọng là **kiểu trả về của `@Bean` factory method** giúp AOT nhìn thấy loại bean cụ thể. Nếu abstraction là chủ ý và implementation không có metadata đặc biệt cần xử lý, interface return type vẫn có thể phù hợp; hãy dựa vào yêu cầu thực tế.

## 10. Những mẫu bean definition gây khó cho AOT

### 10.1. Tự đăng ký bean bằng callback không được AOT xử lý

Một số ứng dụng đăng ký bean bằng cách thao tác trực tiếp với `BeanFactory` ở một callback tùy biến. Nếu AOT engine không nhìn thấy bean definition đó trong giai đoạn phân tích, nó có thể không sinh registration code hoặc Runtime Hints cần thiết.

Khi đăng ký bean programmatically, nên sử dụng **`BeanDefinitionRegistry`** để đăng ký bean definition. Các cách tiếp cận thường phù hợp gồm:

- `ImportBeanDefinitionRegistrar` được import từ cấu hình Spring.
- `BeanDefinitionRegistryPostProcessor` khi cần xử lý registry ở thời điểm thích hợp.
- Các cơ chế AOT contribution như `BeanFactoryInitializationAotProcessor` khi hạ tầng tùy biến cần đóng góp code cho AOT.

Nếu một processor tự nó được đăng ký như bean và cần chạy trong cả AOT lẫn runtime, phải hiểu rõ lifecycle của nó để tránh xử lý lặp hoặc bỏ sót behavior.

### 10.2. Bean definition có custom instance supplier do ứng dụng cung cấp

Ví dụ:

~~~java
RootBeanDefinition definition = new RootBeanDefinition(MyClient.class);
definition.setInstanceSupplier(() -> createClientDynamically());
registry.registerBeanDefinition("myClient", definition);
~~~

Supplier lambda hoặc method reference **đã tồn tại trong bean definition đầu vào** không đồng nghĩa với generated supplier mà Spring AOT tự tạo. Spring AOT không thể tự biến mọi supplier tùy ý thành mã AOT, vì logic bên trong lambda có thể không biểu diễn được từ metadata.

Nếu có bean definition cần tạo động, hãy thiết kế cách đăng ký để AOT có thể phân tích, hoặc đóng góp code/hints riêng theo extension API phù hợp. Đừng giả định chỉ cần đặt lambda trong `setInstanceSupplier` là Native Image sẽ hiểu mọi class/resource mà lambda truy cập.

### 10.3. Gọi getBean với custom arguments

Container hỗ trợ yêu cầu tạo bean bằng custom arguments, nhưng kiểu gọi động này khiến Spring phải dò constructor hoặc factory method phù hợp tại runtime:

~~~java
// Ví dụ minh họa một cách tạo bean với tham số tùy ý:
MyPrototype prototype = beanFactory.getBean(MyPrototype.class, runtimeArgument);
~~~

Các đối số này không nhất thiết được AOT biết trước. Việc dùng custom arguments có thể đòi hỏi reflection hints thủ công; đồng thời bỏ qua instance supplier đã được tạo, khiến các tối ưu hóa sau khâu tạo instance (ví dụ injection qua field/method được supplier xử lý) không được thực hiện như đường AOT dự kiến.

Với prototype cần dữ liệu đầu vào thay đổi theo request, nên dùng **factory bean/service chuyên trách**:

~~~java
@Component
public class ReportFactory {
    public Report create(String title, ReportRepository repository) {
        return new Report(title, repository);
    }
}
~~~

Factory là bean do Spring quản lý theo đường tạo đã biết; logic tạo object có tham số động được đặt ở một nơi rõ ràng thay vì yêu cầu container dò constructor tùy từng lần gọi.

### 10.4. Nhiều constructor nhưng không xác định rõ constructor ưu tiên

Container có thể lựa chọn constructor từ nhiều ứng viên, nhưng dựa vào heuristic làm cho đường tạo bean khó đọc và khó phân tích. Hãy:

- Giữ một constructor chính nếu thiết kế cho phép.
- Dùng `@Autowired` để đánh dấu constructor mong muốn khi có nhiều constructor.
- Nếu không sửa được class, xem xét metadata `preferredConstructors` của bean definition trong trường hợp phù hợp với API/version đang dùng.

### 10.5. Circular dependency

Một số vòng phụ thuộc qua setter hoặc field injection có thể chạy ở runtime thông thường nhờ cơ chế xử lý circular reference. Trong AOT-optimized context, explicit circular dependencies có thể khiến ứng dụng không khởi động được.

Nên thiết kế lại dependency graph để tránh vòng lặp. Nếu cần truy cập lazy, có thể dùng `@Lazy` tại injection point hoặc `ObjectProvider<T>` để lấy dependency khi thực sự cần.

## 11. Constructor và factory method nên đơn giản, có kiểu rõ ràng

Spring AOT phải sinh Java code để biểu diễn giá trị và dependency. Với các bean definition được đăng ký thủ công, một cấu trúc dữ liệu tùy biến phức tạp làm constructor argument hoặc property có thể không được code generator biểu diễn trực tiếp.

Ví dụ:

~~~java
record RuntimeOptions(Map<String, List<CustomRule>> rules) {}

public class RuleEngine {
    public RuleEngine(RuntimeOptions options) {
        // ...
    }
}
~~~

Việc sử dụng record không tự động sai với AOT. Vấn đề xuất hiện khi **bean definition được tạo programmatically với giá trị cấu trúc tùy biến** mà code generator không biết cách biểu diễn. Nếu AOT báo không thể generate value code, hãy cân nhắc:

- Chuyển giá trị phức tạp thành một bean có bean definition riêng.
- Chia cấu trúc thành các kiểu đơn giản hoặc dependency được container quản lý.
- Dùng factory method có kiểu trả về cụ thể.
- Chỉ triển khai `ValueCodeGenerator.Delegate` khi thực sự cần hỗ trợ một loại giá trị đặc biệt và đã hiểu extension API.

Không nên thêm custom code generator trước khi xác định rõ loại giá trị gây lỗi.

## 12. Cách tìm và đọc generated bean definitions

Spring AOT thường sinh source code có tên class dạng `...__BeanDefinitions` và một entry point `ApplicationContextInitializer` dùng để khởi tạo ApplicationContext với AOT optimizations.

Các vị trí thường gặp:

| Build tool | Generated AOT sources (thường gặp) |
|---|---|
| Maven | `target/spring-aot/main/sources/` |
| Gradle | `build/generated/aotSources/` |

Đây là các vị trí phổ biến được Spring documentation mô tả; cấu hình output của plugin có thể thay đổi. Tìm theo tên bean hoặc class:

~~~bash
# Linux/macOS, ví dụ khi dùng Maven
find target/spring-aot -type f -name '*.java'
grep -R "BeanInstanceSupplier" target/spring-aot

# Ví dụ khi dùng Gradle
find build/generated -type f -name '*.java'
grep -R "BeanInstanceSupplier" build/generated
~~~

PowerShell:

~~~powershell
Get-ChildItem target/spring-aot, build/generated -Recurse -Filter *.java -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName

Get-ChildItem target/spring-aot, build/generated -Recurse -Filter *.java -ErrorAction SilentlyContinue |
    Select-String -Pattern 'BeanInstanceSupplier|setInstanceSupplier'
~~~

Khi tìm thấy generated class, đọc theo thứ tự:

1. Bean name và bean type được khai báo.
2. Phương thức trả về supplier.
3. Constructor/factory method được mô tả.
4. Các dependency arguments được lấy từ `AutowiredArguments`.
5. Đoạn injection/lifecycle bổ sung.
6. Nơi bean definition gắn supplier và được đăng ký.

**Không sửa generated source trực tiếp.** Hãy sửa class, constructor, `@Bean` method, bean registration hoặc Runtime Hints trong mã nguồn quản lý rồi chạy lại AOT.

## 13. Ví dụ thực hành: từ constructor đến generated supplier

Tạo hai class đơn giản:

~~~java
package com.example.checkout;

import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    public boolean available(String sku) {
        return true;
    }
}
~~~

~~~java
package com.example.checkout;

import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final InventoryRepository inventoryRepository;

    public CheckoutService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    public boolean canCheckout(String sku) {
        return inventoryRepository.available(sku);
    }
}
~~~

Một quy trình thực hành:

**Bước 1 — Kiểm tra đường tạo bean ở mã nguồn.** `CheckoutService` chỉ có một constructor, nhận `InventoryRepository`; dependency được khai báo tường minh.

**Bước 2 — Chạy Spring AOT theo build tool của dự án.** Với Maven, goal thường gặp là:

~~~bash
./mvnw -Pnative package
~~~

Với Gradle:

~~~bash
./gradlew processAot
~~~

Các lệnh giả định dự án đã cấu hình profile/plugin tương ứng. Nếu chỉ muốn quan sát AOT trước khi biên dịch native, chạy task/goal AOT riêng phù hợp phiên bản.

**Bước 3 — Tìm generated bean definition.** Dùng đường dẫn ở phần trước, tìm `CheckoutService` hoặc `BeanInstanceSupplier`.

**Bước 4 — Xác nhận supplier chỉ ra constructor phù hợp.** Trong generated code, tìm tham số kiểu `InventoryRepository` và đoạn tạo `CheckoutService`.

**Bước 5 — Thử thay đổi thiết kế để quan sát.** Thêm một constructor thứ hai hoặc đổi factory method, chạy lại AOT và xem code generation thay đổi ra sao. Sau đó quay lại thiết kế rõ ràng, tránh để nhiều đường tạo bean không cần thiết.

**Bước 6 — Build và chạy native application.** Native Image kiểm tra toàn bộ reachable code và metadata; generated supplier là một phần của quá trình, không bảo đảm mọi thư viện động khác đều tương thích.

## 14. Phân biệt supplier với reflection hints

`BeanInstanceSupplier` và `RuntimeHints` có liên quan đến AOT nhưng giải quyết hai vấn đề khác nhau:

| Cơ chế | Mục đích | Ví dụ |
|---|---|---|
| `InstanceSupplier` / `BeanInstanceSupplier` | Tạo bean bằng constructor hoặc factory method đã xác định | `forConstructor(OrderRepository.class)` |
| Generated bean definitions | Tái tạo cấu hình/đăng ký bean ở runtime | `RootBeanDefinition` + `setInstanceSupplier(...)` |
| Injection code | Gắn dependency vào constructor/field/method | Generated calls cho `@Autowired` |
| `RuntimeHints` | Đăng ký reflection, resource, serialization, JDK proxy cần thiết | `hints.resources().registerPattern(...)` |

Supplier tạo object không đồng nghĩa mọi thao tác reflection trong object đó đều đã được đăng ký. Nếu `OrderService` gọi một thư viện tải class bằng tên hoặc đọc file từ classpath, Native Image vẫn có thể cần hints cho những thao tác đó.

Ngược lại, thêm reflection hints cho một constructor không sửa được thiết kế bean definition không được AOT nhìn thấy. Cần xác định đúng loại lỗi trước khi thêm metadata.

## 15. Bài tập tự kiểm tra

**Câu 1.** `InstanceSupplier` là gì?

**Gợi ý:** là logic được bean definition sử dụng để tạo bean instance khi container cần; không phải object được tạo sẵn lúc AOT build.

**Câu 2.** Vì sao AOT dùng `BeanInstanceSupplier.forConstructor(...)`?

**Gợi ý:** nó mô tả constructor cụ thể, cho phép Spring phân giải dependency arguments và sinh code tạo object trực tiếp, giảm phụ thuộc vào dò constructor bằng reflection.

**Câu 3.** `forFactoryMethod(...)` dùng cho trường hợp nào?

**Gợi ý:** bean được tạo bởi một factory method, chẳng hạn phương thức `@Bean` trong class `@Configuration`.

**Câu 4.** Spring AOT có tạo tất cả bean instance ở build time không?

**Gợi ý:** không. AOT processing chủ yếu tạo bean definitions và generated assets; bean application thông thường được tạo khi ứng dụng chạy và container cần chúng.

**Câu 5.** Vì sao nên khai báo kiểu trả về cụ thể cho `@Bean` method?

**Gợi ý:** AOT cần biết chính xác bean type để phân tích annotation, injection point, lifecycle callbacks và proxy trên implementation.

**Câu 6.** Gọi `getBean(MyPrototype.class, runtimeArgument)` có thể gây vấn đề gì?

**Gợi ý:** custom arguments cần dò constructor/factory method động, có thể cần reflection hints và bỏ qua instance supplier đã tối ưu, làm mất một số xử lý injection được sinh.

**Câu 7.** Nếu không thấy `BeanInstanceSupplier` trong generated source thì có thể kết luận AOT không chạy không?

**Gợi ý:** chưa đủ. Bean không tham số có thể dùng constructor reference trực tiếp; factory method đơn giản có thể dùng method reference; output directory cũng có thể khác. Hãy tìm `setInstanceSupplier`, `InstanceSupplier` và bean definition class.

## 16. Checklist thiết kế bean thân thiện với AOT

- [ ] Mỗi bean có một đường tạo instance rõ ràng, ưu tiên constructor injection.
- [ ] Nếu có nhiều constructor, xác định constructor được chọn bằng annotation hoặc metadata phù hợp.
- [ ] `@Bean` factory method khai báo kiểu trả về cụ thể khi có thể.
- [ ] Dependency cần thiết được thể hiện bằng tham số constructor/factory method.
- [ ] Tránh custom instance supplier không thể phân tích nếu chưa có AOT contribution phù hợp.
- [ ] Tránh yêu cầu container tạo bean bằng custom arguments tùy từng lần gọi; dùng factory bean/service cho dữ liệu động.
- [ ] Bean được đăng ký programmatically thông qua `BeanDefinitionRegistry` hoặc extension AOT phù hợp.
- [ ] Hạn chế circular dependencies; cân nhắc `@Lazy` hoặc `ObjectProvider` nếu cần trì hoãn.
- [ ] Không sửa generated sources trực tiếp; tìm và sửa nguồn cấu hình tạo ra chúng.
- [ ] Phân biệt lỗi đường tạo bean với lỗi reflection/resource metadata.
- [ ] Kiểm thử Spring AOT và Native Image trên đúng phiên bản Spring/GraalVM của dự án.

## 17. Tài liệu tham khảo

- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): quy trình AOT, generated bean definitions, supplier, best practices và Runtime Hints.
- [Spring Framework Javadoc — BeanInstanceSupplier](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/aot/BeanInstanceSupplier.html): API `forConstructor`, `forFactoryMethod`, `withGenerator` và `get`.
- [Spring Framework Javadoc — AutowiredArguments](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/aot/AutowiredArguments.html): cách truy xuất các dependency argument đã được phân giải.

**Ghi nhớ:** Spring AOT biến cách đăng ký và tạo bean đã biết thành mã Java tường minh. `InstanceSupplier` là điểm nối giữa bean definition và thao tác tạo instance; `BeanInstanceSupplier` giúp biểu diễn constructor/factory method cùng dependency arguments. Generated supplier được gọi ở runtime theo scope của bean, còn AOT build chủ yếu phân tích definition và sinh code. Thiết kế constructor rõ ràng, factory method có kiểu cụ thể và bean registration có thể phân tích sẽ giúp Spring Boot Native Image dễ build, dễ debug và ổn định hơn.
