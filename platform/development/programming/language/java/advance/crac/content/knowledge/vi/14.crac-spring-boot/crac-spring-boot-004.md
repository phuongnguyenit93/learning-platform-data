# Thứ tự phase và quan hệ phụ thuộc giữa các bean

Trong Spring Boot, một ứng dụng được tạo từ nhiều bean: service, repository, DataSource, client HTTP, scheduler, message listener và các thành phần hạ tầng khác. Spring IoC container chịu trách nhiệm tạo các bean, tiêm dependency, gọi callback khởi tạo, áp dụng BeanPostProcessor và quản lý vòng đời của những thành phần được đăng ký.

Để hiểu thứ tự hoạt động, cần phân biệt ba khái niệm:

- **Refresh phase:** các giai đoạn Spring thực hiện khi ApplicationContext được khởi tạo hoặc refresh.
- **Bean dependency:** quan hệ giữa các bean, quyết định bean phụ thuộc cần được tạo trước bean sử dụng nó.
- **Lifecycle phase:** thứ tự start/stop của những bean triển khai Lifecycle hoặc SmartLifecycle.

Các khái niệm này có liên quan nhưng không thay thế cho nhau. Trong ứng dụng dùng CRaC, còn có một vòng đời thứ tư: callback trước checkpoint và sau restore. Việc hiểu rõ từng lớp giúp tránh khởi động service quá sớm, đóng resource sai thứ tự hoặc giả định bean sẽ được khởi tạo lại sau restore.

## 1. ApplicationContext refresh là gì?

ApplicationContext là container trung tâm của Spring. Trong quá trình refresh, Spring chuẩn bị BeanFactory, đăng ký các processor, tạo singleton cần thiết, khởi chạy các bean có lifecycle và phát sự kiện cho ứng dụng.

Với một Spring Boot application thông thường, SpringApplication tạo ApplicationContext phù hợp với loại ứng dụng rồi gọi refresh. Các bước bên trong được thực hiện theo một trình tự xác định bởi AbstractApplicationContext.

Sơ đồ rút gọn:

~~~text
SpringApplication
       |
       v
Tạo ApplicationContext
       |
       v
prepareRefresh()
       |
       v
obtainFreshBeanFactory()
       |
       v
prepareBeanFactory()
       |
       v
postProcessBeanFactory()
       |
       v
invokeBeanFactoryPostProcessors()
       |
       v
registerBeanPostProcessors()
       |
       v
initMessageSource()
       |
       v
initApplicationEventMulticaster()
       |
       v
onRefresh()
       |
       v
registerListeners()
       |
       v
finishBeanFactoryInitialization()
       |
       v
finishRefresh()
       |
       v
ApplicationContext sẵn sàng
       |
       v
Spring Boot gọi ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent
~~~

Đây là sơ đồ khái quát. Một số bước có thể được subclass của ApplicationContext mở rộng, ví dụ web application context tạo embedded web server trong hook onRefresh().

## 2. Các phase chính trong quá trình refresh

### prepareRefresh()

Spring chuẩn bị trạng thái của context trước khi tạo bean:

- Ghi nhận thời điểm bắt đầu refresh.
- Đặt cờ context đang active.
- Khởi tạo hoặc kiểm tra các property source cần thiết.
- Kiểm tra các thuộc tính bắt buộc đã được khai báo.
- Chuẩn bị bộ quản lý sự kiện nội bộ.

Ở giai đoạn này, phần lớn application bean chưa được khởi tạo. Đây là bước chuẩn bị môi trường cho quá trình refresh.

### obtainFreshBeanFactory()

Spring lấy hoặc tạo BeanFactory mới cho ApplicationContext. BeanFactory chứa các BeanDefinition mô tả cách tạo bean: class, constructor, factory method, scope, dependency, lazy flag và các metadata khác.

BeanDefinition không phải bean instance. Việc đăng ký một định nghĩa bean chưa có nghĩa constructor của bean đó đã được gọi.

Ví dụ một bean có thể được khai báo bằng component scan:

~~~java
@Component
public class PaymentService {
}
~~~

Hoặc bằng Java configuration:

~~~java
@Configuration
public class PaymentConfiguration {
    @Bean
    PaymentService paymentService() {
        return new PaymentService();
    }
}
~~~

Ở bước này, Spring xây dựng nền tảng mô tả bean và quan hệ giữa chúng.

### prepareBeanFactory()

Spring cấu hình BeanFactory với các thành phần cơ bản như class loader, expression resolver, property editor và các interface đặc biệt mà bean có thể implement.

Một số bean có thể nhận callback theo các interface Aware, chẳng hạn BeanNameAware hoặc BeanFactoryAware. Những callback này xảy ra khi chính bean được tạo, không phải ở bước prepareBeanFactory().

### postProcessBeanFactory()

Đây là hook cho subclass của ApplicationContext tùy chỉnh BeanFactory sau khi nó được chuẩn bị. Web context hoặc context chuyên biệt có thể bổ sung cấu hình riêng.

Ứng dụng thông thường hiếm khi cần override bước này. Phần lớn mở rộng container được thực hiện qua BeanFactoryPostProcessor hoặc BeanDefinitionRegistryPostProcessor.

### invokeBeanFactoryPostProcessors()

Spring gọi các BeanFactoryPostProcessor đã đăng ký. Chúng có thể thay đổi metadata của BeanDefinition trước khi các bean ứng dụng được khởi tạo.

Có hai loại quan trọng:

- BeanDefinitionRegistryPostProcessor: có thể đăng ký thêm BeanDefinition và chạy ở giai đoạn xử lý registry.
- BeanFactoryPostProcessor: có thể chỉnh sửa metadata trong BeanFactory sau khi registry đã được xử lý.

Các processor này thường được dùng bởi cấu hình, property source, component scanning và framework integration.

Ví dụ, ConfigurationClassPostProcessor xử lý các lớp @Configuration, @ComponentScan, @Import và các phương thức @Bean để đăng ký định nghĩa bean.

Không nên dùng BeanFactoryPostProcessor để lấy một service thông thường bằng cách gọi getBean() nếu không có lý do rõ ràng. Việc tạo bean quá sớm có thể làm thay đổi thứ tự khởi tạo và khiến bean được tạo trước khi các BeanPostProcessor cần thiết được đăng ký.

### registerBeanPostProcessors()

Spring đăng ký các BeanPostProcessor. Chúng can thiệp vào bean instance trước và sau initialization callback.

Các tính năng như annotation injection, xử lý @PostConstruct, AOP proxy và một số cơ chế framework được triển khai thông qua BeanPostProcessor.

Vì vậy, BeanPostProcessor cần được đăng ký trước khi phần lớn application bean được tạo. Một bean bị khởi tạo quá sớm có thể chưa đi qua đầy đủ các processor, hoặc có thể nhận cảnh báo về việc không được xử lý bởi tất cả BeanPostProcessor.

### initMessageSource() và initApplicationEventMulticaster()

Spring khởi tạo các thành phần nội bộ cho:

- MessageSource: phân giải message và hỗ trợ internationalization.
- ApplicationEventMulticaster: phân phối ApplicationEvent đến các listener.

Các listener được đăng ký hoặc phát hiện ở những bước tiếp theo. Event system là cơ chế truyền thông báo trong ApplicationContext; nó không tự động bảo đảm mọi công việc bất đồng bộ đã hoàn tất trước một phase khác.

### onRefresh()

ApplicationContext gọi hook onRefresh() để subclass thực hiện công việc riêng.

Ví dụ, ServletWebServerApplicationContext tạo embedded web server trong quá trình refresh. Việc tạo server và việc server bắt đầu nhận traffic là hai việc cần phân biệt; phần start thường được điều phối bởi lifecycle bean của web server trong giai đoạn hoàn tất refresh.

### registerListeners()

Spring đăng ký các ApplicationListener đã được khai báo. Một số listener có thể nhận các event trong giai đoạn refresh và trong suốt thời gian context hoạt động.

Event listener không phải là công cụ phù hợp để biểu diễn mọi quan hệ phụ thuộc khởi tạo. Nếu service B bắt buộc cần service A sẵn sàng, nên khai báo dependency hoặc dùng lifecycle coordinator rõ ràng thay vì dựa vào việc một event tình cờ được phát trước.

### finishBeanFactoryInitialization()

Spring hoàn tất cấu hình BeanFactory và tạo các singleton không lazy còn lại.

Các bước đáng chú ý gồm:

- Hoàn thiện các thành phần chuyển đổi kiểu cần thiết.
- Freeze cấu hình BeanFactory khi phù hợp.
- Khởi tạo các non-lazy singleton còn lại.

Đây là lúc phần lớn service, repository và component singleton của ứng dụng được tạo. Bean lazy có thể vẫn chưa được tạo cho đến khi có lần truy cập đầu tiên.

### finishRefresh()

Spring hoàn tất refresh:

- Khởi tạo LifecycleProcessor nếu chưa có.
- Gọi LifecycleProcessor.onRefresh() để khởi động các lifecycle bean phù hợp, đặc biệt là SmartLifecycle có autoStartup.
- Phát ContextRefreshedEvent.

Với ứng dụng web, các lifecycle component như web server có thể bắt đầu hoạt động trong phase này.

Sau khi context refresh hoàn tất, Spring Boot tiếp tục quy trình khởi động cấp ứng dụng. Các ApplicationRunner và CommandLineRunner được gọi trước khi Spring Boot phát ApplicationReadyEvent và đánh dấu ứng dụng đã sẵn sàng theo lifecycle của Boot.

## 3. Thứ tự khởi tạo bên trong một bean

Khi Spring cần tạo một bean, quá trình khái quát thường gồm:

~~~text
Chọn BeanDefinition
       |
       v
Tạo instance bằng constructor / factory method
       |
       v
Tiêm dependency và populate property
       |
       v
Gọi các callback Aware phù hợp
       |
       v
BeanPostProcessor.postProcessBeforeInitialization()
       |
       v
@PostConstruct
       |
       v
InitializingBean.afterPropertiesSet()
       |
       v
Custom init-method
       |
       v
BeanPostProcessor.postProcessAfterInitialization()
       |
       v
Bean sẵn sàng được sử dụng
~~~

Thứ tự chi tiết có thể được mở rộng bởi framework và processor. Sơ đồ trên mô tả luồng initialization phổ biến của một bean singleton.

### Constructor hoặc factory method

Spring tạo object bằng constructor được chọn hoặc factory method. Với constructor injection, các dependency cần thiết phải được giải quyết trước khi constructor của bean phụ thuộc có thể hoàn tất.

~~~java
@Service
public class OrderService {
    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

Trong ví dụ, Spring phải có PaymentService trước khi tạo OrderService.

### Populate property và dependency injection

Sau khi instance được tạo, Spring tiêm các dependency qua field, setter hoặc các cơ chế injection khác.

~~~java
@Service
public class ReportService {
    @Autowired
    private ReportRepository repository;
}
~~~

Field injection xảy ra sau constructor. Vì vậy, constructor của ReportService không thể sử dụng repository vừa được tiêm qua field.

Constructor injection thường dễ kiểm tra hơn vì dependency được thể hiện rõ và object không được tạo ở trạng thái thiếu dependency bắt buộc.

### Aware callbacks

Nếu bean implement các interface Aware, Spring có thể cung cấp thông tin container trước initialization callback, ví dụ:

- BeanNameAware: tên bean.
- BeanClassLoaderAware: class loader.
- BeanFactoryAware: BeanFactory.
- ApplicationContextAware: ApplicationContext.

Không nên dùng ApplicationContextAware như service locator cho mọi dependency. Constructor injection thường làm quan hệ phụ thuộc rõ ràng hơn.

### Initialization callbacks

Spring hỗ trợ nhiều cách khai báo initialization:

~~~java
@Component
public class CacheLoader implements InitializingBean {

    @PostConstruct
    public void initializeCache() {
        // Chuẩn bị cache.
    }

    @Override
    public void afterPropertiesSet() {
        // Initialization callback của Spring.
    }

    public void warmUp() {
        // Custom init method nếu được cấu hình.
    }
}
~~~

Với các cơ chế phổ biến, thứ tự initialization là:

1. Method có @PostConstruct.
2. InitializingBean.afterPropertiesSet().
3. Custom init-method được khai báo trong bean definition hoặc @Bean(initMethod = "...").

Nên chọn một cơ chế chính để dễ theo dõi. Không nên chia một quy trình khởi tạo thành nhiều callback có phụ thuộc thứ tự ngầm nếu có thể gom vào một phương thức rõ ràng.

Ví dụ Java configuration:

~~~java
@Configuration
public class CacheConfiguration {

    @Bean(initMethod = "warmUp", destroyMethod = "close")
    CacheClient cacheClient() {
        return new CacheClient();
    }
}
~~~

### BeanPostProcessor sau initialization

BeanPostProcessor có thể trả về một object khác thay cho instance ban đầu. AOP auto-proxy creator là một ví dụ: bean có thể được bọc trong proxy để áp dụng transaction, security, caching hoặc advice.

Do đó, object mà bean khác nhận được có thể là proxy chứ không phải object target trực tiếp.

Điều này có ý nghĩa khi:

- Gọi method có @Transactional từ bên trong cùng một object (self-invocation thường không đi qua proxy).
- Giữ tham chiếu tới target trước khi proxy được tạo.
- Tự gọi method trên bean trong initialization callback.
- Kiểm tra class thực tế của bean bằng getClass().

Không nên dựa vào việc bean đã chạy constructor để kết luận tất cả AOP hoặc proxy behavior đã sẵn sàng.

## 4. Quan hệ dependency quyết định thứ tự tạo bean

Spring tạo bean theo nhu cầu. Khi bean A cần bean B, container phải giải quyết B trước khi hoàn tất việc tạo A.

Ví dụ:

~~~java
@Repository
public class OrderRepository {
}

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}

@RestController
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }
}
~~~

Quan hệ phụ thuộc:

~~~text
OrderController
      |
      v
OrderService
      |
      v
OrderRepository
~~~

Khi Spring tạo OrderController, nó cần OrderService. Khi tạo OrderService, nó cần OrderRepository. Do đó repository được tạo trước service, rồi service trước controller.

Đây là quan hệ dependency thực sự. Nó không dựa trên thứ tự alphabet, thứ tự file source hoặc thứ tự component được tìm thấy trong package.

### Constructor injection

Constructor injection thể hiện dependency bắt buộc:

~~~java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final TaxService taxService;

    public InvoiceService(
            InvoiceRepository repository,
            TaxService taxService) {
        this.repository = repository;
        this.taxService = taxService;
    }
}
~~~

Spring phải giải quyết cả InvoiceRepository và TaxService trước khi tạo InvoiceService.

Ưu điểm:

- Dependency bất biến sau khi tạo object.
- Dễ viết unit test.
- Tránh bean tồn tại ở trạng thái chưa được tiêm dependency.
- Quan hệ phụ thuộc được thể hiện ngay trong constructor.

### Setter và field injection

Setter injection phù hợp với dependency tùy chọn hoặc cần thay đổi theo lifecycle:

~~~java
@Component
public class NotificationService {
    private TemplateProvider templateProvider;

    @Autowired
    public void setTemplateProvider(
            TemplateProvider templateProvider) {
        this.templateProvider = templateProvider;
    }
}
~~~

Field injection ngắn gọn nhưng làm dependency ẩn trong class và khó tạo instance độc lập trong unit test.

Cả setter và field injection đều được xử lý sau khi constructor đã tạo object. Nếu constructor cần dùng dependency đó, field hoặc setter chưa sẵn sàng.

### @DependsOn

Khi hai bean có quan hệ khởi tạo nhưng không thể hiện qua dependency injection, có thể dùng @DependsOn:

~~~java
@Component
public class DatabaseBootstrap {
    @PostConstruct
    public void prepareSchemaMetadata() {
        // Chuẩn bị metadata cần thiết.
    }
}

@Component
@DependsOn("databaseBootstrap")
public class BackgroundIndexer {
    @PostConstruct
    public void startIndexing() {
        // Chỉ chạy sau khi databaseBootstrap được khởi tạo.
    }
}
~~~

@DependsOn yêu cầu bean được chỉ định khởi tạo trước bean hiện tại. Với singleton, bean phụ thuộc được hủy theo thứ tự ngược khi container shutdown.

Tuy nhiên, @DependsOn chỉ biểu diễn thứ tự khởi tạo. Nó không tự tiêm một object vào bean và không thay thế constructor injection. Nếu BackgroundIndexer thực sự cần gọi DatabaseBootstrap, hãy khai báo dependency trực tiếp trong constructor.

Không dùng @DependsOn để sửa một kiến trúc dependency vòng hoặc để bảo đảm dịch vụ bên ngoài luôn sẵn sàng.

## 5. Phân biệt @DependsOn, @Order, @Primary và @Lazy

Các annotation này giải quyết những vấn đề khác nhau.

| Cơ chế | Mục đích | Có quyết định thứ tự tạo bean không? |
|---|---|---|
| @DependsOn | Yêu cầu bean khác được khởi tạo trước | Có, cho quan hệ được khai báo |
| @Order | Sắp xếp phần tử trong một số collection hoặc danh sách có thứ tự | Không phải quy tắc tổng quát cho bean initialization |
| @Primary | Chọn bean ưu tiên khi có nhiều ứng viên cùng kiểu | Không |
| @Qualifier | Chọn ứng viên theo qualifier cụ thể | Không |
| @Lazy | Trì hoãn khởi tạo cho đến khi bean được yêu cầu | Có thể làm thời điểm tạo muộn hơn, nhưng không phải cơ chế dependency ordering |
| @DependsOn + dependency injection | Kết hợp thứ tự tạo với quan hệ sử dụng | Có |

### @Order không phải thứ tự khởi tạo

Ví dụ:

~~~java
@Component
@Order(1)
public class FirstHandler implements Handler {
}

@Component
@Order(2)
public class SecondHandler implements Handler {
}
~~~

Nếu inject List<Handler>, Spring có thể sắp xếp các phần tử theo thứ tự tương ứng khi áp dụng các quy tắc Ordered/@Order.

Nhưng @Order(1) không bảo đảm FirstHandler được khởi tạo trước mọi bean khác trong ApplicationContext. Đừng dùng @Order như thay thế cho @DependsOn.

### @Primary và @Qualifier

Khi có nhiều implementation cùng kiểu:

~~~java
public interface PaymentGateway {
    void pay();
}

@Component
@Primary
public class CardGateway implements PaymentGateway {
    public void pay() {
    }
}

@Component
public class BankGateway implements PaymentGateway {
    public void pay() {
    }
}
~~~

@Primary làm CardGateway trở thành ứng viên mặc định khi injection cần một PaymentGateway và không có qualifier cụ thể.

Nếu muốn chọn rõ:

~~~java
@Service
public class BankTransferService {
    private final PaymentGateway gateway;

    public BankTransferService(
            @Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Các annotation này giải quyết việc chọn bean, không quyết định lifecycle phase.

### @Lazy

Bean lazy không nhất thiết được tạo trong finishBeanFactoryInitialization(). Nó có thể chỉ được tạo khi một bean khác hoặc code ứng dụng yêu cầu nó.

~~~java
@Component
@Lazy
public class ExpensiveReportEngine {
}
~~~

Nếu một non-lazy bean cần trực tiếp một lazy bean, dependency đó vẫn có thể khiến lazy bean được tạo khi bean non-lazy được khởi tạo. @Lazy trên injection point có thể dùng proxy để trì hoãn việc lấy target.

Không nên dựa vào @Lazy để né dependency sai hoặc trì hoãn một resource bắt buộc mà không có readiness check.

## 6. Circular dependency và bean được tạo sớm

Circular dependency xảy ra khi A cần B và B lại cần A:

~~~text
ServiceA ----> ServiceB
   ^              |
   |              |
   +--------------+
~~~

Với constructor injection, chu trình như vậy không thể giải quyết bằng cách tạo một bean hoàn chỉnh trước bean kia; Spring thường báo lỗi BeanCurrentlyInCreationException hoặc lỗi vòng phụ thuộc tương ứng.

~~~java
@Service
public class ServiceA {
    public ServiceA(ServiceB serviceB) {
    }
}

@Service
public class ServiceB {
    public ServiceB(ServiceA serviceA) {
    }
}
~~~

Một số circular dependency giữa singleton dùng setter/field injection có thể được giải quyết bằng cơ chế early singleton reference trong các cấu hình Spring cho phép. Tuy nhiên, cách này làm lifecycle và proxy phức tạp hơn. Spring Boot mặc định không cho phép circular references trong cấu hình ứng dụng thông thường kể từ Boot 2.6, trừ khi được bật rõ ràng.

Cách xử lý tốt hơn là tách phần trách nhiệm chung ra một service thứ ba hoặc dùng event/port abstraction nếu quan hệ thực sự là giao tiếp hai chiều.

### Vì sao bean được tạo sớm có thể thiếu proxy?

Spring có thể cung cấp early reference để giải quyết một số circular dependency. Nếu bean được tạo trước khi các BeanPostProcessor hoặc auto-proxy creator hoàn tất, nó có thể bị inject dưới dạng target hoặc early proxy không tương đương với proxy cuối cùng.

Điều này có thể làm một lời gọi bỏ qua transaction, security hoặc advice mong đợi. Đây là một lý do nữa để tránh circular dependency và tránh gọi getBean() sớm trong BeanFactoryPostProcessor.

## 7. BeanFactoryPostProcessor và BeanPostProcessor cần được khai báo cẩn thận

Hai loại processor thường bị nhầm lẫn:

| Loại | Thời điểm | Tác động |
|---|---|---|
| BeanFactoryPostProcessor | Sau khi BeanDefinition được nạp, trước khi regular bean được tạo | Chỉnh sửa metadata BeanDefinition |
| BeanPostProcessor | Khi bean instance được tạo | Can thiệp trước/sau initialization, có thể tạo proxy |

Ví dụ khai báo BeanFactoryPostProcessor bằng @Bean:

~~~java
@Configuration
public class FeatureConfiguration {

    @Bean
    static PropertyOverrideConfigurer propertyOverrides() {
        return new PropertyOverrideConfigurer();
    }
}
~~~

Đối với các processor có thể được tạo rất sớm, phương thức @Bean static giúp Spring tạo processor mà không cần khởi tạo sớm instance của lớp @Configuration chứa nó.

Với BeanPostProcessor, nên khai báo return type cụ thể thay vì chỉ khai báo Object nếu có thể. Spring cần nhận diện processor để đăng ký đúng thời điểm.

Không inject nhiều application service vào một BeanPostProcessor nếu không cần thiết. Việc tạo processor có thể kéo theo tạo sớm một phần application graph và khiến các bean đó không đi qua đầy đủ processor khác.

## 8. Lifecycle của bean sau khi khởi tạo

Bean được tạo xong không có nghĩa nó đã bắt đầu nhận công việc. Spring có một lifecycle riêng cho các component cần start và stop.

Hai interface thường gặp:

- Lifecycle: start(), stop(), isRunning().
- SmartLifecycle: mở rộng Lifecycle, thêm autoStartup(), getPhase() và stop(Runnable callback).

SmartLifecycle hữu ích cho các thành phần như message listener, scheduler, background worker hoặc server connector.

~~~java
@Component
public class ImportWorker implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Bắt đầu nhận công việc.
    }

    @Override
    public void stop() {
        running = false;
        // Ngừng nhận công việc và dừng worker.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Ví dụ rút gọn. Trong ứng dụng thật, stop() phải thực hiện drain hoặc yêu cầu worker dừng có kiểm soát; không chỉ đặt một boolean nếu còn tác vụ đang chạy.

## 9. SmartLifecycle phase và thứ tự start/stop

SmartLifecycle cho phép gán phase để điều khiển thứ tự start và stop của lifecycle bean.

Quy tắc tổng quát:

- Phase thấp hơn được start trước.
- Phase cao hơn được start sau.
- Khi stop, thứ tự đảo ngược: phase cao hơn dừng trước.
- Quan hệ dependency thực tế giữa các bean vẫn được ưu tiên hơn thứ tự phase.

Ví dụ:

| Bean | Phase | Vai trò |
|---|---:|---|
| DatabaseConnector | 0 | Chuẩn bị dependency kết nối |
| MessageListener | 50 | Bắt đầu nhận message |
| ImportWorker | 100 | Xử lý công việc nền |
| MetricsReporter | 200 | Báo cáo trạng thái |

Thứ tự start dự kiến:

~~~text
DatabaseConnector (0)
        |
        v
MessageListener (50)
        |
        v
ImportWorker (100)
        |
        v
MetricsReporter (200)
~~~

Thứ tự stop dự kiến:

~~~text
MetricsReporter (200)
        |
        v
ImportWorker (100)
        |
        v
MessageListener (50)
        |
        v
DatabaseConnector (0)
~~~

Sơ đồ chỉ minh họa phase. Nếu MessageListener phụ thuộc DatabaseConnector, dependency graph cũng phải thể hiện mối quan hệ đó. Không nên dựa vào số phase để che giấu dependency bị thiếu.

### Lifecycle phase khác refresh phase

Refresh phase là trình tự container tạo và chuẩn bị ApplicationContext. SmartLifecycle phase là thứ tự start/stop của các lifecycle component sau khi container đã tạo bean.

Một bean có getPhase() bằng 100 không có nghĩa bean đó được khởi tạo sau mọi bean có phase 50. Phase không điều khiển constructor hoặc dependency injection.

### SmartLifecycle và autoStartup

SmartLifecycle có thể khai báo isAutoStartup() để Spring biết có tự động start component trong quá trình context refresh hay không.

Nếu autoStartup() trả về false, component có thể được tạo nhưng chưa tự chạy. Ứng dụng có thể start nó sau khi dependency hoặc điều kiện nghiệp vụ đã sẵn sàng.

Không dùng start() để thực hiện một lần khởi tạo object nặng nếu việc đó thuộc về @PostConstruct. Hãy tách:
- Initialization: cấu hình object và kiểm tra bất biến nội bộ.
- Lifecycle start: bắt đầu nhận việc hoặc mở tài nguyên hoạt động.
- Lifecycle stop: ngừng nhận việc và giải phóng trạng thái hoạt động.

## 10. Application events và ApplicationRunner

Spring Boot phát nhiều event trong quá trình khởi động. Một số event thường gặp:

| Event | Thời điểm khái quát |
|---|---|
| ApplicationStartingEvent | Bắt đầu SpringApplication |
| ApplicationEnvironmentPreparedEvent | Environment đã chuẩn bị |
| ApplicationContextInitializedEvent | Context đã được khởi tạo nhưng chưa refresh |
| ApplicationPreparedEvent | Bean definitions đã nạp, trước refresh |
| ContextRefreshedEvent | ApplicationContext hoàn tất refresh |
| ApplicationStartedEvent | Context refresh xong, trước runners |
| ApplicationReadyEvent | Runners đã hoàn tất, ứng dụng sắp nhận traffic |
| ApplicationFailedEvent | Khởi động thất bại |

Tên và trình tự chi tiết có thể phụ thuộc phiên bản Spring Boot và loại context. Khi cần logic phụ thuộc phase, hãy tham khảo lifecycle contract của phiên bản đang sử dụng.

### ApplicationRunner và CommandLineRunner

Các runner được gọi sau khi ApplicationContext refresh xong:

~~~java
@Component
public class InitialDataLoader implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        // Nạp dữ liệu ban đầu hoặc chạy tác vụ startup.
    }
}
~~~

Nếu có nhiều runner, có thể dùng Ordered hoặc @Order để sắp xếp thứ tự gọi runner. Đây là thứ tự chạy runner, không phải thứ tự tạo bean.

Không nên dùng ApplicationRunner để tạo một dependency mà một SmartLifecycle bean đã bắt đầu sử dụng trong finishRefresh(). Nếu cần dependency sẵn sàng trước khi listener start, hãy đưa logic vào dependency initialization hoặc lifecycle coordination phù hợp.

## 11. Thứ tự hủy bean khi context shutdown

Khi ApplicationContext đóng, Spring dừng lifecycle bean và hủy singleton theo quan hệ phụ thuộc.

Các initialization callback có callback tương ứng khi destroy:

- @PreDestroy.
- DisposableBean.destroy().
- Custom destroy-method khai báo trong bean definition hoặc @Bean.

Thứ tự phổ biến của destroy callback trên một bean là @PreDestroy, DisposableBean.destroy(), rồi custom destroy-method.

Với các bean có dependency, bean phụ thuộc được hủy trước dependency mà nó sử dụng. Ví dụ:

~~~text
Tạo:
DataSource -> Repository -> Service -> Listener

Hủy:
Listener -> Service -> Repository -> DataSource
~~~

Sơ đồ cho thấy dependency nền tảng được tạo trước consumer và thường được đóng sau consumer.

Với SmartLifecycle, Spring dừng component theo phase ngược với thứ tự start. Component có thể dùng stop(Runnable callback) để báo khi quá trình dừng bất đồng bộ đã hoàn tất.

Không đóng DataSource trong khi listener hoặc worker vẫn đang sử dụng nó. Dừng consumer trước, chờ in-flight work kết thúc, rồi mới đóng dependency.

## 12. Quan hệ bean trong ứng dụng Spring Boot dùng CRaC

CRaC bổ sung một vòng đời khác với Spring bean lifecycle.

Trong một lần chạy bình thường:

~~~text
SpringApplication
       |
       v
ApplicationContext refresh
       |
       v
Bean initialization
       |
       v
SmartLifecycle start
       |
       v
ApplicationRunner / CommandLineRunner
       |
       v
ApplicationReadyEvent
       |
       v
Ứng dụng phục vụ request
~~~

Khi yêu cầu checkpoint:

~~~text
Ứng dụng đang phục vụ
       |
       v
Ngừng nhận request / trigger mới
       |
       v
Drain worker và transaction
       |
       v
Dừng lifecycle component
       |
       v
Resource.beforeCheckpoint()
       |
       v
Checkpoint image
~~~

Sau restore:

~~~text
Restore heap và tiến trình
       |
       v
Resource.afterRestore()
       |
       v
Tạo lại connection / client / file handle
       |
       v
Kiểm tra dependency
       |
       v
Start worker và listener
       |
       v
Mở request gate
~~~

Điểm quan trọng: restore từ checkpoint image không đồng nghĩa với việc Spring tạo ApplicationContext mới và chạy lại toàn bộ constructor, @PostConstruct hoặc refresh phase. Trạng thái bean đã có trong heap được khôi phục. Những tài nguyên bên ngoài cần được tạo lại phải được xử lý qua cơ chế CRaC hoặc integration tương ứng.

### Bean dependency không tự xử lý resource sau restore

Ví dụ OrderService có constructor dependency tới PaymentClient:

~~~java
@Service
public class OrderService {
    private final PaymentClient paymentClient;

    public OrderService(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }
}
~~~

Constructor injection bảo đảm PaymentClient bean tồn tại trước khi OrderService được tạo. Nhưng nó không bảo đảm socket trong PaymentClient còn hợp lệ sau restore.

PaymentClient cần lifecycle riêng để đóng kết nối trước checkpoint và tạo lại sau restore. OrderService vẫn giữ tham chiếu tới bean PaymentClient; vì vậy bean PaymentClient nên giữ một delegate có thể thay thế hoặc cập nhật trạng thái nội bộ khi reconnect.

### Không coi @DependsOn là thứ tự CRaC callback

@DependsOn điều khiển thứ tự khởi tạo và hủy bean singleton. Nó không phải một hợp đồng tổng quát để điều khiển thứ tự callback của mọi Resource trong CRaC.

Tương tự, SmartLifecycle phase điều khiển start/stop lifecycle bean; không tự động điều khiển thứ tự mọi Resource.beforeCheckpoint() và Resource.afterRestore().

Nếu thứ tự tài nguyên quan trọng, hãy:
- Dùng một coordinator duy nhất với trình tự rõ ràng.
- Hoặc dùng integration CRaC của Spring Boot đúng phiên bản và tuân theo thứ tự callback mà integration đó quy định.
- Khai báo dependency rõ ràng giữa các resource.
- Chỉ mở traffic sau khi mọi dependency bắt buộc đã sẵn sàng.

Không dựa vào thứ tự tình cờ của component scan hoặc thứ tự đăng ký bean.

## 13. Ví dụ phối hợp Spring Lifecycle và CRaC

Giả sử ứng dụng có:

- DatabasePool: tạo và đóng JDBC pool.
- ImportWorker: nhận và xử lý công việc nền.
- RequestGate: ngừng nhận công việc mới.
- CheckpointCoordinator: điều phối checkpoint.

Một abstraction có thể là:

~~~java
public interface RequestGate {
    void stopAccepting();
    void awaitInFlight() throws Exception;
    void resumeAccepting();
}

public interface DatabaseResource {
    void closeForCheckpoint() throws Exception;
    void reopenAfterRestore() throws Exception;
}
~~~

Worker triển khai SmartLifecycle để Spring quản lý start/stop:

~~~java
import org.springframework.context.SmartLifecycle;

public final class ImportWorker implements SmartLifecycle {
    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        // Bắt đầu consumer hoặc worker loop.
    }

    @Override
    public void stop() {
        running = false;
        // Yêu cầu worker dừng và drain công việc.
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stopAndAwaitCompletion();
        } finally {
            callback.run();
        }
    }

    private void stopAndAwaitCompletion() {
        // Chờ tác vụ đang chạy hoàn tất với timeout.
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
~~~

Coordinator triển khai CRaC Resource:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;
import org.springframework.context.LifecycleProcessor;

public final class SpringCheckpointCoordinator implements Resource {
    private final RequestGate requestGate;
    private final LifecycleProcessor lifecycleProcessor;
    private final DatabaseResource database;

    public SpringCheckpointCoordinator(
            RequestGate requestGate,
            LifecycleProcessor lifecycleProcessor,
            DatabaseResource database) {
        this.requestGate = requestGate;
        this.lifecycleProcessor = lifecycleProcessor;
        this.database = database;

        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        requestGate.stopAccepting();
        requestGate.awaitInFlight();

        lifecycleProcessor.stop();
        database.closeForCheckpoint();
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        database.reopenAfterRestore();
        lifecycleProcessor.start();

        requestGate.resumeAccepting();
    }
}
~~~

Đây là khung minh họa, không phải một integration hoàn chỉnh cho mọi Spring Boot version. Cần bổ sung xử lý lỗi, timeout, readiness và rollback nếu checkpoint bị hủy. DatabaseResource và RequestGate là abstraction do ứng dụng triển khai.

Trong thực tế, cần tránh để lifecycleProcessor.stop() dừng chính component mà coordinator đang cần để hoàn thành callback. Nếu context có nhiều lifecycle bean không nên dừng trong checkpoint, có thể dùng một lifecycle coordinator riêng hoặc quản lý các component cần dừng theo nhóm.

Không gọi resumeAccepting() nếu database chưa kết nối, worker chưa start hoặc bất kỳ dependency bắt buộc nào chưa sẵn sàng.

### Xử lý checkpoint bị hủy

Nếu ứng dụng gọi Core.checkpointRestore() trực tiếp và checkpoint thất bại, tiến trình ban đầu tiếp tục. afterRestore() không chạy cho nhánh này.

Coordinator cần bắt CheckpointException ở luồng gọi API và phục hồi các resource đã đóng, sau đó start lại lifecycle component và mở gate nếu tất cả bước phục hồi thành công.

Nếu checkpoint được yêu cầu bằng jcmd từ bên ngoài, luồng nghiệp vụ không có khối try/catch quanh lời gọi đó. Cần một quy trình quản trị riêng hoặc dùng cơ chế quản trị trong ứng dụng để điều phối rollback.

## 14. Những lỗi thường gặp khi sắp xếp bean

### Dùng @Order để ép bean khởi tạo trước

@Order chủ yếu sắp xếp một số collection hoặc danh sách được framework xử lý. Nó không phải quy tắc tổng quát để điều khiển constructor hoặc thứ tự khởi tạo singleton.

Cách xử lý: khai báo dependency qua constructor hoặc @DependsOn khi thật sự cần quan hệ khởi tạo không được thể hiện bằng injection.

### Dùng @DependsOn thay cho dependency injection

Bean A được tạo sau bean B nhưng A không có tham chiếu tới B. Điều đó không giúp A gọi được B hoặc biết B đã sẵn sàng về nghiệp vụ.

Cách xử lý: dùng constructor injection nếu A cần B. Dùng @DependsOn chỉ khi cần thứ tự khởi tạo mà không cần inject object.

### Khởi động worker trong @PostConstruct

@PostConstruct chạy trong quá trình initialization của bean. Khi đó, toàn bộ ApplicationContext có thể chưa refresh xong và các lifecycle bean khác chưa start.

Nếu worker bắt đầu nhận message ngay trong @PostConstruct, nó có thể chạy trước khi listener, database pool hoặc readiness gate được cấu hình hoàn chỉnh.

Cách xử lý: dùng SmartLifecycle hoặc cơ chế startup coordinator để bắt đầu worker sau khi dependency đã sẵn sàng.

### Dùng constructor để mở kết nối dài hạn

Constructor nên tạo trạng thái object và nhận dependency. Việc mở socket, chạy thread nền hoặc đăng ký lịch dài hạn trong constructor khiến object có side effect trước khi proxy và các lifecycle processor hoàn tất.

Cách xử lý: tách tạo object khỏi start tài nguyên; dùng lifecycle callback phù hợp và CRaC Resource cho checkpoint/restore.

### Giả định @PostConstruct chạy lại sau restore

Restore khôi phục heap của tiến trình. Nó không mặc định tạo lại mọi bean và gọi lại constructor hoặc @PostConstruct.

Cách xử lý: đăng ký Resource hoặc dùng CRaC integration phù hợp để mở lại tài nguyên bên ngoài.

### Dựa vào thứ tự component scan

Thứ tự tìm thấy class không phải hợp đồng khởi tạo. Nếu bean A phụ thuộc bean B, khai báo dependency rõ ràng.

### Dùng @DependsOn để điều khiển mọi callback CRaC

@DependsOn và SmartLifecycle phase không thay thế thứ tự callback Resource. Dùng coordinator hoặc integration được hỗ trợ để điều khiển checkpoint/restore.

### Mở traffic trước khi dependency sẵn sàng

Context có thể refresh xong trong khi database, broker hoặc remote service chưa sẵn sàng. ContextRefreshedEvent không phải bằng chứng rằng mọi dịch vụ ngoài tiến trình đều khỏe.

Cách xử lý: dùng readiness state, health check và startup gate. Chỉ mở traffic khi các dependency bắt buộc đã hoạt động.

## 15. Cách thiết kế dependency graph rõ ràng

Một dependency graph tốt có các đặc điểm:

- Hướng phụ thuộc đi từ tầng ứng dụng xuống tầng hạ tầng hoặc abstraction.
- Không có chu trình không cần thiết.
- Dependency bắt buộc được khai báo bằng constructor injection.
- Dependency tùy chọn dùng ObjectProvider hoặc cơ chế rõ ràng.
- Side effect và background thread được start trong lifecycle phase.
- Resource bên ngoài có callback đóng/mở lại phù hợp với CRaC.
- Readiness chỉ chuyển sang ready sau khi dependency thực sự hoạt động.

Ví dụ:

~~~text
Request Listener
       |
       v
Application Service
       |
       v
Repository
       |
       v
DataSource
       |
       v
Database
~~~

Với worker nền:

~~~text
SmartLifecycle Worker
       |
       +------> Application Service
       |
       +------> Scheduler
       |
       +------> Message Client
                      |
                      v
                   Broker
~~~

Trước checkpoint, dừng consumer và worker trước khi đóng client, scheduler hoặc DataSource mà chúng sử dụng. Sau restore, tạo lại các dependency hạ tầng trước rồi mới start consumer.

## 16. Kiểm tra thứ tự thực tế trong Spring Boot

Khi thứ tự khởi tạo không như dự kiến, có thể dùng các cách sau:

### Log constructor và lifecycle callback

Trong môi trường phát triển, ghi log tại:

- Constructor hoặc factory method.
- @PostConstruct.
- afterPropertiesSet().
- BeanPostProcessor trước/sau initialization.
- SmartLifecycle.start() và stop().
- ApplicationRunner.
- ApplicationReadyEvent.
- CRaC beforeCheckpoint() và afterRestore().

Đính kèm bean name, thread name, timestamp và instance ID để nhìn được trình tự.

Không nên dùng log trong production với dữ liệu nhạy cảm hoặc log quá nhiều ở các callback chạy thường xuyên.

### ApplicationContext và Actuator

Spring Boot Actuator có thể cung cấp endpoint beans để quan sát bean đã đăng ký và endpoint conditions để xem điều kiện auto-configuration. Chỉ expose các endpoint cần thiết và bảo vệ quyền truy cập.

### ApplicationStartup

Spring Framework cung cấp ApplicationStartup và các StartupStep để ghi nhận các bước startup. Spring Boot có thể cấu hình BufferingApplicationStartup để thu thập thông tin khởi động.

Ví dụ:

~~~java
SpringApplication application =
    new SpringApplication(MyApplication.class);

application.setApplicationStartup(
    new BufferingApplicationStartup(2048)
);

application.run(args);
~~~

Thông tin startup giúp xác định phase tốn thời gian và các bean được tạo trong quá trình refresh. Nó không thay thế thread dump hoặc log lifecycle khi điều tra lỗi sau restore.

### Kiểm tra dependency graph

Có thể bật log debug của Spring, quan sát bean creation và dependency resolution. Khi cần, dùng ApplicationContext.getBeanDefinitionNames() để xem danh sách định nghĩa bean; danh sách này không nên được coi là thứ tự tạo bean.

## 17. Quy trình triển khai

### Khi ứng dụng khởi động

1. Để Spring nạp BeanDefinition và đăng ký các processor.
2. Khai báo dependency bắt buộc bằng constructor injection.
3. Dùng @DependsOn cho quan hệ thứ tự khởi tạo không thể biểu diễn bằng injection.
4. Để BeanPostProcessor hoàn tất việc proxy và initialization.
5. Dùng SmartLifecycle để start listener, worker và scheduler.
6. Chỉ phát readiness khi dependency ngoài tiến trình đã sẵn sàng.

### Trước checkpoint

1. Ngừng nhận request và trigger mới.
2. Drain in-flight request, transaction và message đang xử lý.
3. Stop worker/listener theo lifecycle coordinator.
4. Đóng DataSource, HTTP client, file handle và resource cần tạo lại.
5. Hoàn tất callback trước checkpoint sau khi mọi thành phần đã ở trạng thái an toàn.

### Sau restore

1. Giữ request gate ở trạng thái đóng.
2. Tạo lại resource bên ngoài.
3. Cập nhật delegate hoặc wrapper mà các bean đang giữ.
4. Xác minh database, broker và remote service.
5. Start worker/listener theo dependency và lifecycle phase.
6. Khởi động scheduler khi dependency sẵn sàng.
7. Mở request gate và đánh dấu ứng dụng ready.

### Khi checkpoint bị hủy

Nếu ứng dụng chủ động gọi Core.checkpointRestore(), bắt CheckpointException và khôi phục các resource đã đóng trong tiến trình ban đầu. Sau đó start lại lifecycle component theo thứ tự dependency và chỉ mở gate nếu mọi bước thành công.

Nếu rollback thất bại, giữ readiness false và báo lỗi cho hệ thống giám sát. Không dùng afterRestore() để xử lý nhánh checkpoint bị hủy.

## 18. Nguyên tắc cần ghi nhớ

- ApplicationContext refresh có các phase rõ ràng; phần lớn non-lazy singleton được tạo trong finishBeanFactoryInitialization().
- BeanDefinition được đăng ký trước khi bean instance được tạo.
- Constructor/factory method, dependency injection, Aware callback, initialization callback và BeanPostProcessor có thứ tự riêng.
- @PostConstruct thường chạy trước afterPropertiesSet() và custom init-method.
- Dependency injection quyết định thứ tự tạo bean theo dependency graph.
- @DependsOn điều khiển thứ tự khởi tạo singleton; @Order không phải quy tắc tổng quát cho bean creation.
- @Primary và @Qualifier chọn bean; @Lazy trì hoãn tạo bean.
- SmartLifecycle phase điều khiển thứ tự start/stop, phase thấp start trước và phase cao stop trước.
- ApplicationRunner và CommandLineRunner chạy sau context refresh; @Order có thể sắp xếp runner.
- Destroy callback và dependency destruction thường chạy theo thứ tự ngược với initialization.
- Restore từ checkpoint không mặc định chạy lại constructor, @PostConstruct hoặc toàn bộ refresh phase.
- @DependsOn và SmartLifecycle phase không tự điều khiển thứ tự CRaC Resource callbacks.
- Tạo lại resource bên ngoài trước khi start worker/listener và mở request gate.
- Dùng coordinator rõ ràng để phối hợp dependency, readiness và rollback khi checkpoint bị hủy.

Thứ tự bean trong Spring Boot được quyết định bởi các phase của ApplicationContext, dependency graph và lifecycle contract. Khi phân biệt đúng ba lớp này và phối hợp riêng với CRaC, ứng dụng có thể khởi động theo thứ tự dễ dự đoán, dừng consumer trước dependency và khôi phục resource trước khi nhận công việc sau restore.
