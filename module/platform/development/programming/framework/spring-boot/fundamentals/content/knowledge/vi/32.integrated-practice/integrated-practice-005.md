# Theo dõi constructor, init, proxy, runner và callback hủy

Khi một Spring Boot application khởi động, nhiều việc diễn ra nối tiếp nhau: Spring tạo object, inject dependency, gọi callback khởi tạo, có thể bọc object bằng AOP proxy, refresh application context, chạy startup runners rồi mới báo ứng dụng sẵn sàng. Khi ứng dụng dừng, Spring gọi các callback đóng tài nguyên và dừng những component có lifecycle.

Nếu chỉ thêm `System.out.println()` vào constructor và `@PostConstruct`, bạn mới quan sát được một phần vòng đời. Muốn hiểu log đầy đủ, cần phân biệt **vòng đời của một bean**, **thời điểm proxy xuất hiện**, **vòng đời của application context** và **các bước khởi động của Spring Boot**.

Bài học này hướng dẫn theo dõi các giai đoạn đó bằng constructor, `@PostConstruct`, `InitializingBean`, `BeanPostProcessor`, AOP proxy, `SmartInitializingSingleton`, `ApplicationRunner`, `CommandLineRunner`, `@PreDestroy`, `DisposableBean` và `SmartLifecycle`. Các ví dụ dùng Spring Boot hiện đại với Spring Framework 6 và Jakarta annotations.

## 1. Bốn mốc lớn trong vòng đời ứng dụng

Một cách nhìn tổng quát:

```text
APPLICATION START
      │
      ▼
Chuẩn bị Environment và ApplicationContext
      │
      ▼
Refresh ApplicationContext
      │
      ├── Tạo các singleton cần khởi tạo sớm
      │      │
      │      ├── Constructor
      │      ├── Inject dependencies / populate properties
      │      ├── Aware callbacks
      │      ├── BeanPostProcessor before initialization
      │      ├── Init callbacks
      │      └── BeanPostProcessor after initialization
      │
      ├── SmartInitializingSingleton callbacks
      ├── SmartLifecycle start
      └── ContextRefreshedEvent
      │
      ▼
ApplicationStartedEvent
      │
      ▼
ApplicationRunner / CommandLineRunner
      │
      ▼
ApplicationReadyEvent
      │
      ▼
APPLICATION READY
      │
      │  Requests / scheduled work / message processing
      │
      ▼
SHUTDOWN
      │
      ├── ContextClosedEvent
      ├── SmartLifecycle stop
      ├── Bean destruction callbacks
      └── Release container resources
```

Sơ đồ cho thấy hai loại thời điểm khác nhau:

- Các callback `init`/`destroy` gắn với **một bean**.
- Runner và application events gắn với **quá trình khởi động ứng dụng**.

`SmartLifecycle` lại là một cơ chế lifecycle khác: component được start/stop theo lifecycle processor của application context.

Không phải mọi bean đều được tạo ngay lúc startup. Lazy beans, prototype beans và những bean chỉ được tạo khi có request có thể xuất hiện muộn hơn. Vì vậy, thứ tự log thực tế còn phụ thuộc dependency graph, lazy initialization và cấu hình của ứng dụng.

## 2. Bean lifecycle và ApplicationContext lifecycle

**Bean lifecycle** mô tả cách Spring quản lý một object:

1. Tạo instance.
2. Inject dependencies và các property.
3. Gọi các callback trước/sau initialization.
4. Đưa bean vào sử dụng.
5. Gọi callback hủy khi bean được quản lý và context đóng.

**ApplicationContext lifecycle** mô tả quá trình xây dựng và đóng container:

- Chuẩn bị environment và bean definitions.
- Refresh context.
- Khởi động lifecycle components.
- Phát các context/application events.
- Chạy startup runners.
- Đóng context và hủy singleton beans.

Ví dụ `@PostConstruct` chạy khi một bean cụ thể được khởi tạo. `ApplicationRunner` chạy sau khi application context đã refresh. Hai callback không cùng một giai đoạn.

## 3. Constructor: Spring tạo instance

Constructor được gọi khi Spring cần tạo bean instance.

```java
@Component
public class OrderService {

    public OrderService() {
        System.out.println("[OrderService] constructor");
    }
}
```

Nếu bean có constructor injection:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
        System.out.println("[OrderService] constructor");
    }
}
```

Spring phải resolve `OrderRepository` trước khi gọi constructor của `OrderService`, rồi truyền dependency vào constructor.

Trong constructor, các dependency constructor đã được truyền vào có thể sử dụng. Nhưng field injection và setter injection của chính bean chưa hoàn tất ở thời điểm constructor chạy.

Vì vậy, tránh đọc field được đánh dấu `@Autowired` trong constructor nếu field đó được inject sau khi object được tạo.

## 4. Constructor injection và field injection khác thời điểm

Constructor injection:

```java
@Component
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
        System.out.println("constructor: repository available");
    }
}
```

Field injection:

```java
@Component
public class ReportService {

    @Autowired
    private ReportRepository repository;

    public ReportService() {
        System.out.println("constructor: repository is not injected yet");
    }

    @PostConstruct
    void initialize() {
        System.out.println("init: repository available = "
                + (repository != null));
    }
}
```

Trong ví dụ thứ hai, Spring tạo instance trước, sau đó mới populate field. Khi `@PostConstruct` được gọi, field injection đã hoàn thành.

Constructor injection thường dễ quan sát và kiểm thử hơn vì object không thể được tạo nếu thiếu dependency bắt buộc. Nó cũng giúp khai báo dependency bằng `final`.

## 5. Property population và dependency injection

Sau khi instance được tạo, Spring populate bean properties. Công việc này có thể gồm:

- Resolve các dependency cho field injection.
- Gọi setter injection.
- Áp dụng các giá trị được cấu hình qua bean definition.
- Thực hiện các bước population do container quản lý.

Ví dụ setter injection:

```java
@Component
public class SearchService {

    private SearchRepository repository;

    @Autowired
    public void setRepository(SearchRepository repository) {
        this.repository = repository;
        System.out.println("[SearchService] setter injection");
    }
}
```

Nếu theo dõi log, bạn có thể thấy constructor chạy trước setter. Đừng dựa vào thứ tự tạo bean toàn cục để kết luận một bean nào đó luôn được tạo trước; Spring tạo dependency theo graph và những bean khác có thể được khởi tạo vì nhiều lý do.

## 6. Aware callbacks: bean nhận thông tin từ container

Một số bean cần biết thông tin về chính container quản lý chúng. Spring cung cấp các `Aware` interfaces.

Ví dụ:

```java
@Component
public class ContainerAwareProbe
        implements BeanNameAware, BeanFactoryAware {

    @Override
    public void setBeanName(String name) {
        System.out.println("[Aware] bean name = " + name);
    }

    @Override
    public void setBeanFactory(BeanFactory beanFactory) {
        System.out.println("[Aware] BeanFactory injected");
    }
}
```

Các interface thường gặp:

| Interface | Thông tin được cung cấp |
|---|---|
| `BeanNameAware` | Bean name trong container |
| `BeanClassLoaderAware` | ClassLoader liên quan |
| `BeanFactoryAware` | BeanFactory quản lý bean |
| `EnvironmentAware` | Environment |
| `ResourceLoaderAware` | ResourceLoader |
| `ApplicationEventPublisherAware` | Event publisher |
| `MessageSourceAware` | MessageSource |
| `ApplicationContextAware` | ApplicationContext |

Các callback `Aware` được gọi sau khi bean đã được tạo và dependency population diễn ra, trước các initialization callbacks thông thường.

Không nên implement nhiều `Aware` interfaces chỉ để tiện lấy mọi dependency từ container. Constructor injection thường thể hiện dependency rõ ràng hơn. Dùng `Aware` khi bean thực sự cần tích hợp với hạ tầng container.

## 7. BeanPostProcessor: quan sát trước và sau initialization

`BeanPostProcessor` cho phép Spring xử lý bean trước và sau initialization callbacks.

Hai method quan trọng:

```java
Object postProcessBeforeInitialization(
        Object bean,
        String beanName
)

Object postProcessAfterInitialization(
        Object bean,
        String beanName
)
```

Một processor đơn giản:

```java
public class TraceBeanPostProcessor
        implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName) {

        System.out.println(
                "[BPP before] " + beanName
                        + " : " + bean.getClass().getName()
        );

        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean,
            String beanName) {

        System.out.println(
                "[BPP after] " + beanName
                        + " : " + bean.getClass().getName()
        );

        return bean;
    }
}
```

Processor phải trả về bean (hoặc wrapper/proxy thay thế) mà container sẽ tiếp tục sử dụng. Nếu trả về `null`, chuỗi post-processing tiếp theo có thể bị dừng theo contract của `BeanPostProcessor`; không dùng `null` như cách bỏ qua một bean một cách tùy tiện.

## 8. Đăng ký BeanPostProcessor đúng cách

Có thể đăng ký processor qua một `@Bean` method:

```java
@Configuration(proxyBeanMethods = false)
public class TraceConfiguration {

    @Bean
    static BeanPostProcessor traceBeanPostProcessor() {
        return new TraceBeanPostProcessor();
    }
}
```

`BeanPostProcessor` là một phần của hạ tầng tạo bean và được đăng ký sớm trong quá trình refresh. Dùng static `@Bean` method cho processor giúp tránh khởi tạo configuration class chứa nó quá sớm.

Trong ứng dụng lớn, một processor tổng quát có thể in rất nhiều log. Hãy lọc bean theo package hoặc tên cần theo dõi, tránh log cả framework beans và thông tin nhạy cảm.

Đừng inject các application beans thông thường vào constructor của một `BeanPostProcessor` nếu không hiểu rõ hệ quả khởi tạo sớm. Dependency của processor có thể bị tạo trước khi toàn bộ processor khác được đăng ký, khiến một số bean không được xử lý đầy đủ hoặc không đủ điều kiện auto-proxying.

## 9. Thứ tự initialization callbacks

Với một bean thông thường, thứ tự callback initialization phổ biến của Spring là:

1. `BeanPostProcessor.postProcessBeforeInitialization(...)`.
2. `@PostConstruct`.
3. `InitializingBean.afterPropertiesSet()`.
4. Custom init method được khai báo trong bean definition hoặc `@Bean(initMethod=...)`.
5. `BeanPostProcessor.postProcessAfterInitialization(...)`.

Các callback `Aware` tương ứng được gọi trước bước post-processing before initialization.

Ví dụ:

```java
@Component
public class LifecycleProbe implements InitializingBean {

    public LifecycleProbe() {
        System.out.println("1. constructor");
    }

    @PostConstruct
    public void postConstruct() {
        System.out.println("2. @PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("3. afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("4. custom init");
    }
}
```

Khai báo custom init method cho bean bằng `@Bean` hoặc bean definition như phần tiếp theo. Các con số trong log chỉ minh họa thứ tự mong đợi của một bean; log của các bean khác có thể xen kẽ vì dependency graph.

## 10. @PostConstruct

`@PostConstruct` đánh dấu method được gọi sau khi dependency injection hoàn tất và trước khi bean được đưa vào sử dụng bình thường.

```java
import jakarta.annotation.PostConstruct;

@Component
public class CacheWarmup {

    private final ProductRepository repository;

    public CacheWarmup(ProductRepository repository) {
        this.repository = repository;
    }

    @PostConstruct
    void warmup() {
        System.out.println("CacheWarmup initialized");
        // Có thể chuẩn bị state nội bộ cần thiết.
    }
}
```

Trong Spring Framework 6 và Spring Boot 3, annotation thường dùng là `jakarta.annotation.PostConstruct`. Các dự án cũ thuộc thế hệ Spring 5/Boot 2 thường dùng `javax.annotation.PostConstruct`.

JDK hiện đại không còn đóng gói các Java EE/Jakarta annotations này trong JDK như trước; dependency cung cấp annotation có thể cần được khai báo tùy dòng framework và starter đang dùng.

Method `@PostConstruct` thường không nhận tham số, không trả về giá trị và nên ngắn gọn. Không dùng nó để khởi chạy một vòng lặp vô hạn hoặc chờ một hệ thống ngoài không giới hạn.

## 11. InitializingBean.afterPropertiesSet()

`InitializingBean` là interface Spring cung cấp:

```java
public interface InitializingBean {
    void afterPropertiesSet() throws Exception;
}
```

Ví dụ:

```java
@Component
public class SearchIndexManager implements InitializingBean {

    @Override
    public void afterPropertiesSet() {
        System.out.println("SearchIndexManager ready");
    }
}
```

`afterPropertiesSet()` được gọi sau các property/dependency injection và sau `@PostConstruct` trong chuỗi initialization chuẩn.

Ưu điểm là callback được thể hiện qua interface. Nhược điểm là class phụ thuộc trực tiếp vào Spring API. Nếu muốn class domain/application ít phụ thuộc Spring hơn, `@PostConstruct` hoặc custom init method có thể phù hợp hơn.

Không cần implement `InitializingBean` chỉ để in một log; nó có ý nghĩa khi bean thực sự cần một bước khởi tạo gắn với contract của interface.

## 12. Custom init method với @Bean

Có thể dùng `initMethod` trong `@Bean`:

```java
public class ExternalClientHolder {

    public void connect() {
        System.out.println("ExternalClientHolder initialized");
    }

    public void disconnect() {
        System.out.println("ExternalClientHolder destroyed");
    }
}
```

```java
@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(
        initMethod = "connect",
        destroyMethod = "disconnect"
    )
    ExternalClientHolder externalClientHolder() {
        return new ExternalClientHolder();
    }
}
```

Cách này phù hợp khi class không được thiết kế để implement Spring lifecycle interfaces hoặc khi bạn muốn giữ cấu hình lifecycle ở configuration class.

Spring gọi custom init method sau `@PostConstruct` và `afterPropertiesSet()` nếu bean cũng dùng hai cơ chế đó.

Method phải phù hợp với contract init/destroy: thông thường là method không tham số, trả về `void` hoặc kiểu phù hợp với lifecycle invocation; dùng public no-arg `void` methods là cách rõ ràng nhất.

## 13. Kết hợp ba loại init callback

Một bean có thể sử dụng nhiều cơ chế:

```java
@Component
public class MultiInitProbe implements InitializingBean {

    public MultiInitProbe() {
        System.out.println("constructor");
    }

    @PostConstruct
    void postConstruct() {
        System.out.println("@PostConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("afterPropertiesSet");
    }

    public void customInit() {
        System.out.println("customInit");
    }
}
```

Nếu bean được đăng ký bằng component scanning, không có thuộc tính `initMethod` tự động trỏ tới `customInit`. Bạn cần khai báo custom init qua bean definition phù hợp hoặc chọn một cơ chế đăng ký khác.

Trong code production, nên chọn một callback phù hợp với nhu cầu. Dùng cả ba có thể hữu ích trong ví dụ quan sát, nhưng trong ứng dụng thật dễ khiến initialization logic bị chia nhỏ và khó theo dõi.

## 14. BeanPostProcessor sau initialization và AOP proxy

Một số Spring features dùng `BeanPostProcessor` để tạo proxy, ví dụ:

- `@Transactional`.
- `@Async`.
- `@Cacheable`.
- Custom Spring AOP aspects.

Auto-proxy creator thường phát hiện bean cần advice và bọc target bằng proxy trong quá trình post-processing sau initialization.

Luồng khái quát:

```text
Tạo target object
      │
      ▼
Inject dependencies
      │
      ▼
Init callbacks trên target
      │
      ▼
BeanPostProcessor after initialization
      │
      ▼
AOP infrastructure kiểm tra advisors
      │
      ├── Không cần proxy ──► Trả target
      │
      └── Cần proxy ────────► Trả proxy
                                  │
                                  ▼
                         Consumer nhận bean
```

Đây là mô hình thông thường. Circular dependencies và early references có thể làm quá trình phức tạp hơn; tránh dùng một sơ đồ đơn giản để suy luận mọi trường hợp nâng cao.

## 15. Proxy khác target object

Giả sử:

```java
@Service
public class InvoiceService {

    @Transactional
    public void createInvoice() {
        System.out.println("create invoice");
    }
}
```

Spring có thể expose một proxy thay cho target `InvoiceService`. Consumer inject bean theo type và gọi method qua proxy. Proxy áp dụng transaction advice trước khi delegate tới target.

Có thể kiểm tra trong code chẩn đoán:

```java
import org.springframework.aop.support.AopUtils;

boolean proxy = AopUtils.isAopProxy(invoiceService);
boolean jdkProxy = AopUtils.isJdkDynamicProxy(invoiceService);
boolean cglibProxy = AopUtils.isCglibProxy(invoiceService);
```

Không nên đưa các kiểm tra proxy này vào business logic. Chúng phù hợp hơn trong diagnostics hoặc test khi cần xác nhận cấu hình AOP.

## 16. JDK dynamic proxy và class-based proxy

Hai hình thức proxy phổ biến:

| Loại | Đặc điểm |
|---|---|
| JDK dynamic proxy | Proxy theo interface |
| Class-based proxy (thường qua CGLIB) | Tạo subclass của class mục tiêu |

Nếu dùng JDK proxy, consumer thường cần truy cập bean qua interface. Class-based proxy có thể expose class type nhưng có giới hạn của subclassing, ví dụ không override được final methods.

Lựa chọn proxy phụ thuộc cấu hình AOP và framework. Đừng giả định mọi bean có `@Transactional` đều có cùng runtime class với source code.

Khi log `bean.getClass().getName()` trong `BeanPostProcessor`, có thể thấy proxy class ở giai đoạn sau initialization. Tên proxy có thể dài và khác nhau giữa JDK/CGLIB, không nên dùng tên generated class làm contract ứng dụng.

## 17. Self-invocation: gọi qua this không đi qua proxy

Ví dụ:

```java
@Service
public class BillingService {

    public void process() {
        save();
    }

    @Transactional
    public void save() {
        // Persist data.
    }
}
```

Lời gọi `save()` từ `process()` là lời gọi nội bộ qua `this`, không đi qua proxy bên ngoài trong mô hình proxy-based AOP thông thường. Vì vậy transaction advice có thể không được áp dụng cho lời gọi đó.

Cách xử lý thường dùng:

- Tách transactional operation sang một bean khác và inject qua proxy.
- Gọi qua proxy bean từ consumer phù hợp.
- Dùng AspectJ weaving nếu project thực sự cần interception cho self-invocation và đã cấu hình đúng.

Theo dõi proxy giúp phát hiện rằng **bean có proxy không đồng nghĩa mọi method call đều đi qua proxy**.

## 18. Constructor và method @Transactional

Không gọi method cần AOP advice từ constructor và không kỳ vọng proxy đã sẵn sàng trong constructor.

Lúc constructor chạy, target instance đang được tạo. Proxy thông thường được tạo trong quá trình post-processing sau initialization.

Tương tự, trong `@PostConstruct`, bean đang thực hiện initialization trên target. Gọi một method khác cùng bean từ callback này không nên được coi là lời gọi qua proxy cuối cùng.

Nếu cần thực hiện một thao tác sau khi context đã hoàn tất refresh hoặc sau khi application sẵn sàng, hãy chọn callback/event phù hợp thay vì dùng constructor hoặc `@PostConstruct` để ép proxy hoạt động sớm.

## 19. Circular dependency và early proxy reference

Circular dependency xảy ra khi bean A cần B trong lúc B lại cần A.

Một số trường hợp singleton circular references có thể được xử lý bằng early references; Spring AOP có cơ chế liên quan để đảm bảo object được expose và proxy hóa nhất quán trong một số cấu hình. Tuy nhiên, điều này làm lifecycle trace phức tạp hơn.

Dấu hiệu thường gặp:

- Bean được khởi tạo sớm hơn dự kiến.
- Có log “currently in creation”.
- Bean được inject không giống object target mà bạn quan sát.
- Một số bean không đủ điều kiện được xử lý bởi mọi `BeanPostProcessor`.
- Constructor circular dependency thường không thể giải quyết theo cách setter/field circular reference có thể được xử lý.

Cách tốt nhất là thiết kế dependency graph không có vòng tròn. Tách trách nhiệm, dùng event hoặc đảo chiều dependency khi phù hợp. Không dựa vào early singleton exposure như một kỹ thuật thiết kế thông thường.

## 20. SmartInitializingSingleton

`SmartInitializingSingleton` cung cấp callback:

```java
void afterSingletonsInstantiated()
```

Callback được gọi sau khi các regular singleton beans đã được pre-instantiate trong quá trình refresh.

Ví dụ:

```java
@Component
public class StartupRegistry implements SmartInitializingSingleton {

    @Override
    public void afterSingletonsInstantiated() {
        System.out.println(
                "All regular singletons have been instantiated"
        );
    }
}
```

Nó hữu ích khi một component cần biết giai đoạn tạo regular singleton beans đã hoàn tất, chẳng hạn xây registry từ các beans đã đăng ký.

Đây chưa phải tín hiệu `ApplicationReadyEvent`. Sau callback này, context vẫn còn các bước hoàn tất refresh và Spring Boot còn chạy application runners.

Lazy singleton beans chưa được khởi tạo không được đảm bảo đã tồn tại chỉ vì callback này chạy.

## 21. SmartLifecycle: component có start/stop riêng

`SmartLifecycle` mở rộng lifecycle management của Spring với khả năng điều khiển phase, auto-startup và asynchronous stop callback.

Một implementation đơn giản:

```java
@Component
public class MessageConsumerLifecycle implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        running = true;
        System.out.println("Message consumer started");
    }

    @Override
    public void stop() {
        running = false;
        System.out.println("Message consumer stopped");
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

Interface còn có các method/default behavior liên quan như:

- `isAutoStartup()`.
- `getPhase()`.
- `stop(Runnable callback)`.

Dùng `SmartLifecycle` khi component cần được start/stop theo lifecycle processor của context, ví dụ consumer, connector hoặc background infrastructure có vòng đời rõ ràng.

Đối với một bean chỉ cần chuẩn bị state nội bộ sau injection, `@PostConstruct` đơn giản hơn.

## 22. SmartLifecycle phase

`getPhase()` xác định thứ tự start/stop giữa các lifecycle components.

Quy tắc khái quát:

- Phase thấp hơn được start trước.
- Phase cao hơn được start sau.
- Khi stop, thứ tự đảo ngược: phase cao hơn được stop trước.

Ví dụ:

```java
@Override
public int getPhase() {
    return 100;
}
```

Nếu component B cần component A đã start trước, có thể dùng phase phù hợp để biểu đạt thứ tự. Tuy nhiên, hãy giữ dependency lifecycle đơn giản và kiểm tra cả behavior khi shutdown.

`@Order` trên bean không thay thế `SmartLifecycle.getPhase()` trong việc điều khiển start/stop phase. Đây là hai cơ chế khác nhau.

## 23. SmartLifecycle asynchronous stop

`SmartLifecycle` có overload:

```java
@Override
public void stop(Runnable callback) {
    try {
        running = false;
        // Ngừng nhận message mới và chờ công việc đang xử lý.
    }
    finally {
        callback.run();
    }
}
```

Spring lifecycle processor dùng callback để biết component đã hoàn tất stop. Nếu không gọi callback, quá trình shutdown có thể phải chờ tới timeout.

Trong implementation thực tế, nếu stop bất đồng bộ, hãy gọi callback đúng một lần sau khi component đã dừng. Không gọi callback ngay lập tức nếu resource vẫn đang được sử dụng.

Dùng timeout có giới hạn và ghi log thời gian shutdown. Không chờ vô hạn một external dependency.

## 24. ContextRefreshedEvent

Khi application context đã refresh, Spring phát `ContextRefreshedEvent`.

```java
@Component
public class ContextRefreshListener {

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        System.out.println(
                "Context refreshed: "
                        + event.getApplicationContext().getId()
        );
    }
}
```

Event có thể được phát cho nhiều context trong hierarchy. Nếu ứng dụng có parent/child contexts, listener có thể nhận nhiều event. Khi cần, kiểm tra context ID hoặc quan hệ context để chỉ xử lý context mong muốn.

`ContextRefreshedEvent` cho biết context đã refresh, nhưng trong Spring Boot đây vẫn chưa phải mốc application đã hoàn tất mọi startup runner.

## 25. Spring Boot application events

Spring Boot phát nhiều application events trong quá trình startup/shutdown.

Một số event thường gặp theo trình tự:

| Event | Thời điểm khái quát |
|---|---|
| `ApplicationStartingEvent` | Rất sớm, trước khi Environment và context hoàn chỉnh |
| `ApplicationEnvironmentPreparedEvent` | Environment đã chuẩn bị |
| `ApplicationContextInitializedEvent` | Context đã được tạo và initializer đã chạy |
| `ApplicationPreparedEvent` | Context chuẩn bị refresh |
| `ContextRefreshedEvent` | Spring context đã refresh |
| `ApplicationStartedEvent` | Context đã refresh, trước runners |
| `ApplicationReadyEvent` | Sau khi runners hoàn thành |
| `ContextClosedEvent` | Context đang đóng |

Một số event rất sớm được phát trước khi application context tồn tại. Listener cho các event này có thể cần đăng ký qua `SpringApplication.addListeners(...)` hoặc cơ chế bootstrap phù hợp; không phải lúc nào một `@Component` trong context cũng nhận được event xảy ra trước khi component được tạo.

## 26. ApplicationStartedEvent và ApplicationReadyEvent khác nhau

`ApplicationStartedEvent` được phát sau khi application context đã refresh và trước khi `ApplicationRunner`/`CommandLineRunner` hoàn tất.

`ApplicationReadyEvent` được phát sau khi runners hoàn thành.

```text
Context refresh complete
        │
        ▼
ApplicationStartedEvent
        │
        ▼
ApplicationRunner / CommandLineRunner
        │
        ▼
ApplicationReadyEvent
        │
        ▼
Application accepts traffic
```

Vì vậy:

- Dùng `ApplicationStartedEvent` khi muốn quan sát context đã khởi tạo.
- Dùng `ApplicationRunner`/`CommandLineRunner` cho startup work cần chạy sau refresh.
- Dùng `ApplicationReadyEvent` khi muốn biết các runner đã kết thúc và ứng dụng đã tới giai đoạn ready.

Đừng dùng `@PostConstruct` để thay thế tín hiệu application ready.

## 27. ApplicationRunner

`ApplicationRunner` nhận `ApplicationArguments`, giúp đọc command-line arguments theo dạng đã phân tích.

```java
@Component
@Order(10)
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ImportRunner started");

        if (args.containsOption("import")) {
            System.out.println("Import option supplied");
        }

        System.out.println("ImportRunner finished");
    }
}
```

`ApplicationArguments` cung cấp:

- `getSourceArgs()`: arguments gốc.
- `getOptionNames()`: tên các option.
- `containsOption(name)`: kiểm tra option.
- `getOptionValues(name)`: các giá trị của option.
- `getNonOptionArgs()`: các arguments không phải option.

Ví dụ chạy:

```bash
java -jar app.jar --import=initial data.csv
```

Cách parse option phụ thuộc cú pháp command line; dùng `ApplicationArguments` thay vì tự tách chuỗi thủ công.

## 28. CommandLineRunner

`CommandLineRunner` nhận các arguments thô dưới dạng `String...`.

```java
@Component
@Order(20)
public class StartupReportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "StartupReportRunner args = "
                        + Arrays.toString(args)
        );
    }
}
```

Nó phù hợp khi muốn đọc trực tiếp arguments hoặc gọi một startup task đơn giản.

So sánh:

| Tiêu chí | `ApplicationRunner` | `CommandLineRunner` |
|---|---|---|
| Tham số | `ApplicationArguments` | `String... args` |
| Parsed options | Có | Tự xử lý |
| Non-option args | Có API riêng | Có trong raw array |
| Thời điểm chạy | Sau context refresh | Sau context refresh |
| Mục tiêu | Startup task | Startup task |

Hai interface không phải hai giai đoạn riêng biệt. Spring Boot gọi cả hai trong quá trình startup runner invocation.

## 29. Thứ tự nhiều runners với @Order

Nếu có nhiều runners, có thể dùng `Ordered` hoặc `@Order`.

```java
@Component
@Order(10)
public class DatabaseCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("10 - database check");
    }
}
```

```java
@Component
@Order(20)
public class CacheWarmupRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("20 - cache warmup");
    }
}
```

```java
@Component
@Order(30)
public class StartupSummaryRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("30 - startup summary");
    }
}
```

Trong cùng quá trình gọi runners, Spring Boot áp dụng thứ tự dựa trên `Ordered`/`@Order` cho runner beans. Giá trị order thấp hơn chạy trước.

Không dựa vào thứ tự component scanning hoặc tên class. Nếu một runner phụ thuộc runner khác, khai báo thứ tự tường minh hoặc gộp orchestration vào một component có trách nhiệm rõ.

## 30. Runner chạy khi nào so với @PostConstruct?

Một ví dụ so sánh:

```java
@Component
public class StartupProbe {

    public StartupProbe() {
        System.out.println("constructor");
    }

    @PostConstruct
    void initialize() {
        System.out.println("@PostConstruct");
    }
}
```

```java
@Component
public class StartupProbeRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("ApplicationRunner");
    }
}
```

Log của `StartupProbe` xuất hiện trong quá trình bean được tạo, thường trước khi context refresh hoàn tất. Runner chạy sau khi context đã refresh.

Nếu runner inject `StartupProbe`, dependency sẽ được tạo trước khi runner chạy. Tuy nhiên, những bean lazy không được yêu cầu có thể chưa tồn tại.

Dùng init callback cho bước khởi tạo nội bộ của bean; dùng runner cho công việc ở cấp application sau khi context đã sẵn sàng để các dependency thông thường được inject.

## 31. Runner thất bại có làm startup thất bại không?

Có. Nếu một `ApplicationRunner` hoặc `CommandLineRunner` ném exception không được xử lý, quá trình startup có thể thất bại và ứng dụng không phát `ApplicationReadyEvent` theo luồng thành công thông thường.

Ví dụ:

```java
@Component
public class RequiredDataCheckRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (!requiredDataAvailable()) {
            throw new IllegalStateException(
                    "Required startup data is unavailable"
            );
        }
    }

    private boolean requiredDataAvailable() {
        return true;
    }
}
```

Đây là cách fail-fast cho prerequisite bắt buộc.

Nếu công việc không bắt buộc, hãy xử lý lỗi có chủ đích và ghi nhận trạng thái degraded. Đừng bắt tất cả exception rồi bỏ qua, khiến application báo ready trong khi chức năng cốt lõi chưa sẵn sàng.

## 32. Không dùng runner cho tác vụ chạy vô hạn

Runner được thiết kế cho startup work hữu hạn. Tránh viết:

```java
@Override
public void run(ApplicationArguments args) {
    while (true) {
        pollMessages();
    }
}
```

Vòng lặp như vậy có thể giữ quá trình startup không hoàn tất, khiến `ApplicationReadyEvent` không được phát và readiness không chuyển sang trạng thái nhận traffic như mong đợi.

Đối với background component có lifecycle, cân nhắc:

- `SmartLifecycle`.
- `TaskExecutor`/`TaskScheduler` được quản lý.
- Message listener container do Spring quản lý.
- `@Scheduled` cho công việc định kỳ phù hợp.
- Một worker service có cơ chế start/stop rõ ràng.

Không tự tạo thread không được quản lý rồi để nó chạy qua shutdown mà không có cơ chế dừng.

## 33. ApplicationReadyEvent

Có thể lắng nghe mốc ứng dụng đã hoàn tất startup:

```java
@Component
public class ReadyListener {

    @EventListener(ApplicationReadyEvent.class)
    public void onReady(ApplicationReadyEvent event) {
        System.out.println(
                "Application ready: "
                        + event.getApplicationContext().getId()
        );
    }
}
```

Event này phù hợp để:

- Ghi nhận startup hoàn tất.
- Gửi một tín hiệu quan sát nội bộ.
- Bắt đầu một hoạt động hậu-startup nhỏ nếu thiết kế yêu cầu.

Không nên dùng listener này để thay thế toàn bộ hệ thống readiness/health. Spring Boot có availability states và Actuator health để phối hợp với orchestrator.

Nếu cần thực hiện prerequisite mà thất bại phải chặn ứng dụng ready, hãy thực hiện trong runner hoặc cơ chế startup phù hợp trước `ApplicationReadyEvent`.

## 34. ApplicationAvailability và readiness

Spring Boot có `ApplicationAvailability` để quan sát trạng thái availability của application.

Hai trạng thái quan trọng:

- `LivenessState`: ứng dụng còn sống hay không.
- `ReadinessState`: ứng dụng đã sẵn sàng nhận traffic hay chưa.

Có thể quan sát:

```java
@Component
public class AvailabilityProbe {

    private final ApplicationAvailability availability;

    public AvailabilityProbe(ApplicationAvailability availability) {
        this.availability = availability;
    }

    public void printState() {
        System.out.println(
                availability.getLivenessState()
        );
        System.out.println(
                availability.getReadinessState()
        );
    }
}
```

Runners hoàn tất là một mốc trong startup sequence trước khi ứng dụng được đánh dấu ready theo luồng Boot thông thường.

Đừng tự đánh dấu readiness `ACCEPTING_TRAFFIC` trước khi prerequisite của ứng dụng hoàn tất. Với custom startup workflow, hãy dùng availability events đúng thời điểm và kiểm tra cách orchestrator tiêu thụ readiness probe.

## 35. @PreDestroy

`@PreDestroy` đánh dấu method được gọi khi Spring hủy bean được quản lý.

```java
import jakarta.annotation.PreDestroy;

@Component
public class FileBuffer {

    @PreDestroy
    public void cleanup() {
        System.out.println("FileBuffer cleanup");
    }
}
```

Method thường không nhận tham số và trả về `void`.

Các use case:

- Đóng resource nội bộ.
- Flush buffer có giới hạn.
- Dừng một task do bean quản lý.
- Giải phóng handle/file/socket do bean sở hữu.

Không dùng `@PreDestroy` làm nơi thực hiện một công việc nghiệp vụ dài hoặc phụ thuộc vào một remote service chắc chắn còn hoạt động. Shutdown có giới hạn thời gian và có thể bị cắt bởi process/container termination.

## 36. DisposableBean.destroy()

`DisposableBean` định nghĩa:

```java
public interface DisposableBean {
    void destroy() throws Exception;
}
```

Ví dụ:

```java
@Component
public class ConnectionRegistry implements DisposableBean {

    @Override
    public void destroy() {
        System.out.println("ConnectionRegistry destroyed");
    }
}
```

Interface này gắn class trực tiếp với Spring API. Nếu muốn giữ class ít phụ thuộc Spring, `@PreDestroy` hoặc custom destroy method có thể phù hợp hơn.

Khi một bean dùng cả `@PreDestroy` và `DisposableBean`, Spring gọi `@PreDestroy` trước rồi đến `destroy()` theo thứ tự destruction callbacks chuẩn.

## 37. Custom destroy method với @Bean

Ví dụ:

```java
public class ClientPool {

    public void initialize() {
        System.out.println("ClientPool initialized");
    }

    public void shutdown() {
        System.out.println("ClientPool shutdown");
    }
}
```

Đăng ký:

```java
@Configuration(proxyBeanMethods = false)
public class PoolConfiguration {

    @Bean(
        initMethod = "initialize",
        destroyMethod = "shutdown"
    )
    ClientPool clientPool() {
        return new ClientPool();
    }
}
```

Spring gọi custom destroy method khi bean singleton được hủy bởi container.

Với `@Bean`, Spring có cơ chế suy luận destroy method theo mặc định cho một số method phổ biến như `close` hoặc `shutdown`. Có thể dùng `destroyMethod = ""` để tắt inference khi cần, chẳng hạn object được mượn từ nơi khác và Spring không nên tự đóng nó.

Hãy khai báo rõ destroy method khi ownership của resource không hiển nhiên.

## 38. Thứ tự destruction callbacks

Với một bean thông thường, thứ tự destruction callbacks chuẩn là:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method trong bean definition/`@Bean`.

Ví dụ:

```java
@Component
public class DestroyProbe implements DisposableBean {

    @PreDestroy
    void preDestroy() {
        System.out.println("1. @PreDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("2. DisposableBean.destroy");
    }

    public void customShutdown() {
        System.out.println("3. custom destroy");
    }
}
```

Để custom method `customShutdown()` chạy, bean definition cần khai báo method đó làm destroy method.

Nếu bean có dependency, Spring thường hủy dependent beans trước bean mà chúng phụ thuộc, để dependency còn tồn tại trong lúc dependent bean cleanup. Đừng dựa vào thứ tự tùy tiện giữa những singleton độc lập không có quan hệ dependency.

## 39. Dependency và @DependsOn ảnh hưởng thứ tự hủy

Giả sử `ReportService` dùng `ReportRepository`. Khi container quản lý quan hệ dependency, Spring đảm bảo dependent bean được hủy trước dependency mà nó cần.

Có thể khai báo dependency rõ bằng `@DependsOn`:

```java
@Component("databaseConnection")
public class DatabaseConnection {

    @PreDestroy
    void close() {
        System.out.println("database connection closed");
    }
}
```

```java
@Component
@DependsOn("databaseConnection")
public class ReportService {

    @PreDestroy
    void cleanup() {
        System.out.println("report service cleanup");
    }
}
```

`ReportService` phụ thuộc `databaseConnection`; khi hủy, service được cleanup trước connection.

`@DependsOn` cũng ảnh hưởng thứ tự khởi tạo theo hướng dependency phải được khởi tạo trước bean phụ thuộc. Tuy nhiên, constructor injection thường đã biểu đạt dependency thực tế tốt hơn. Chỉ dùng `@DependsOn` khi cần ordering giữa các beans mà không có dependency injection trực tiếp.

## 40. Prototype bean có tự gọi destroy callback không?

Không. Spring quản lý việc tạo và cấu hình prototype bean, nhưng không theo dõi toàn bộ lifecycle để tự gọi destruction callbacks như với singleton beans.

Ví dụ:

```java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class TemporaryDocument implements AutoCloseable {

    @Override
    public void close() {
        System.out.println("TemporaryDocument closed");
    }
}
```

Nếu lấy prototype bean từ container:

```java
TemporaryDocument document =
        applicationContext.getBean(TemporaryDocument.class);
```

ứng dụng phải chịu trách nhiệm đóng resource của object đó khi không còn sử dụng.

Nếu bean prototype sở hữu file handle, stream hoặc resource khác, hãy quản lý bằng `try-with-resources`, `AutoCloseable`, custom factory hoặc scope có lifecycle phù hợp.

Đừng giả định `@PreDestroy` trên prototype sẽ tự chạy khi application context đóng.

## 41. Lazy singleton và destruction

Một singleton được đánh dấu `@Lazy` có thể chưa được khởi tạo cho đến khi có consumer yêu cầu.

```java
@Component
@Lazy
public class ExpensiveCatalog {

    public ExpensiveCatalog() {
        System.out.println("ExpensiveCatalog constructed");
    }

    @PreDestroy
    void cleanup() {
        System.out.println("ExpensiveCatalog destroyed");
    }
}
```

Nếu bean chưa từng được tạo, không có instance để gọi initialization hoặc destruction callback.

Nếu lazy bean đã được tạo và được container quản lý như singleton, nó tham gia destruction khi context đóng.

Điều này giải thích vì sao một bean có `@PreDestroy` có thể không xuất hiện trong shutdown log: có thể instance chưa từng được khởi tạo, hoặc bean không thuộc scope mà container tự quản lý destruction.

## 42. Context close và JVM shutdown hook

Spring có thể đóng application context một cách tường minh:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(OrdersApplication.class, args);

context.close();
```

Trong ứng dụng Boot thông thường, SpringApplication đăng ký shutdown hook để đóng context khi JVM shutdown bình thường. Có thể tắt hook qua cấu hình `SpringApplication` nếu ứng dụng tự quản lý lifecycle, nhưng cần có cơ chế đóng context thay thế.

Shutdown hook không chạy trong mọi tình huống:

- Process bị kill cưỡng bức (`SIGKILL`).
- Máy/container mất điện đột ngột.
- JVM crash nghiêm trọng.
- Runtime bị dừng mà không có cơ hội shutdown bình thường.

Vì vậy, callback hủy là cơ chế cleanup tốt nhất-effort trong shutdown có kiểm soát, không phải nơi duy nhất bảo đảm dữ liệu bền vững.

## 43. Graceful shutdown trong Spring Boot

Với web server được Boot hỗ trợ, có thể bật graceful shutdown:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Graceful shutdown cho phép server ngừng nhận request mới và xử lý các request đang diễn ra theo cơ chế của server, trong giới hạn timeout cấu hình.

`spring.lifecycle.timeout-per-shutdown-phase` đặt thời gian chờ cho từng lifecycle phase. Đây không phải một cam kết rằng toàn bộ shutdown luôn hoàn tất trong đúng tổng số giây đơn giản; có thể có nhiều phase và thành phần khác nhau.

Khi chạy trong container/orchestrator, thời gian termination grace period bên ngoài cần đủ dài cho quá trình shutdown của ứng dụng. Nếu container bị kill trước khi Spring hoàn tất, callback có thể bị cắt.

## 44. Shutdown callback nên làm gì?

Một callback cleanup tốt nên:

- Dừng nhận công việc mới.
- Chờ hoặc từ chối công việc đang chạy theo policy rõ ràng.
- Flush dữ liệu có giới hạn.
- Đóng resource mà bean sở hữu.
- Ghi log ngắn gọn và hữu ích.
- Hoàn thành trong timeout có thể dự đoán.

Tránh:

- Chờ vô hạn một remote server.
- Bắt đầu một workflow mới dài hạn.
- Dựa vào một bean khác đã bị hủy trước đó.
- Ném exception rồi che mất lỗi gốc mà không log.
- Thực hiện side effect không idempotent có thể gây hỏng trạng thái khi shutdown lặp lại.

Nếu resource quan trọng cần bảo toàn, hãy persist dữ liệu trong quá trình hoạt động bình thường và dùng shutdown callback như bước cleanup cuối, không phải lần duy nhất ghi dữ liệu.

## 45. Theo dõi toàn bộ vòng đời bằng log

Một chiến lược log hữu ích là gắn cùng một bean name và một stage cho mỗi message:

```text
[bean=orderService] constructor
[bean=orderService] dependencies populated
[bean=orderService] before initialization
[bean=orderService] @PostConstruct
[bean=orderService] afterPropertiesSet
[bean=orderService] after initialization / proxy
[application] ContextRefreshedEvent
[application] ApplicationStartedEvent
[application] ApplicationRunner
[application] ApplicationReadyEvent
[application] ContextClosedEvent
[bean=orderService] @PreDestroy
[bean=orderService] destroy
```

Trong ứng dụng thật, các log có thể xen kẽ với bean khác. Hãy log `beanName`, class name, context ID và timestamp khi cần.

Không log toàn bộ object bằng `toString()` nếu object có thể chứa password, token hoặc dữ liệu người dùng. Tên bean và class thường đủ để theo dõi lifecycle.

## 46. Một probe cho initialization callbacks

Ví dụ kết hợp các callback trên một bean:

```java
@Component
public class OrderLifecycleProbe
        implements BeanNameAware, InitializingBean, DisposableBean {

    private String beanName;

    public OrderLifecycleProbe() {
        System.out.println("[probe] constructor");
    }

    @Override
    public void setBeanName(String name) {
        this.beanName = name;
        System.out.println("[probe] BeanNameAware: " + name);
    }

    @PostConstruct
    void postConstruct() {
        System.out.println("[probe] @PostConstruct: " + beanName);
    }

    @Override
    public void afterPropertiesSet() {
        System.out.println("[probe] afterPropertiesSet: " + beanName);
    }

    @PreDestroy
    void preDestroy() {
        System.out.println("[probe] @PreDestroy: " + beanName);
    }

    @Override
    public void destroy() {
        System.out.println("[probe] DisposableBean.destroy: " + beanName);
    }
}
```

Bean này giúp quan sát thứ tự callback. Nếu muốn xem `BeanPostProcessor` trước/sau initialization, đăng ký `TraceBeanPostProcessor` riêng.

Đừng để probe trở thành một dependency của các bean production khác chỉ để ép thứ tự log. Việc thêm dependency có thể làm thay đổi chính lifecycle mà bạn đang muốn quan sát.

## 47. Theo dõi runner và event bằng một component

Ví dụ:

```java
@Component
public class StartupTimeline {

    @EventListener(ApplicationStartedEvent.class)
    public void started() {
        System.out.println("[application] started event");
    }

    @EventListener(ApplicationReadyEvent.class)
    public void ready() {
        System.out.println("[application] ready event");
    }

    @EventListener(ContextClosedEvent.class)
    public void closed() {
        System.out.println("[application] context closed");
    }
}
```

Runner:

```java
@Component
@Order(10)
public class StartupTask implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("[application] runner started");
        // Startup task hữu hạn.
        System.out.println("[application] runner finished");
    }
}
```

Một log thông thường sẽ thể hiện `ApplicationStartedEvent` trước runner và `ApplicationReadyEvent` sau khi runners hoàn tất.

Nếu runner ném exception, không kỳ vọng `ApplicationReadyEvent` xuất hiện theo luồng thành công.

## 48. Quan sát proxy bằng BeanPostProcessor

Có thể mở rộng processor để in class trước/sau initialization:

```java
public class ProxyTracePostProcessor
        implements BeanPostProcessor {

    @Override
    public Object postProcessBeforeInitialization(
            Object bean,
            String beanName) {

        if (beanName.equals("invoiceService")) {
            System.out.println(
                    "before: " + bean.getClass().getName()
            );
        }

        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean,
            String beanName) {

        if (beanName.equals("invoiceService")) {
            System.out.println(
                    "after: " + bean.getClass().getName()
            );
            System.out.println(
                    "isProxy: " + AopUtils.isAopProxy(bean)
            );
        }

        return bean;
    }
}
```

Trong một cấu hình AOP thông thường, bạn có thể thấy class target ở giai đoạn trước và proxy ở giai đoạn sau.

Không phải mọi bean đều được proxy. Bean chỉ được bọc khi có infrastructure/advisor phù hợp và bean đủ điều kiện. Việc không thấy proxy không nhất thiết là lỗi; hãy kiểm tra annotation, pointcut, method visibility, proxy mode và dependency graph.

## 49. Test thứ tự callback

Một cách kiểm thử đơn giản là ghi lại stage vào một collection do test kiểm soát.

Ví dụ bean:

```java
@Component
public class OrderedLifecycleProbe implements InitializingBean {

    private final List<String> events;

    public OrderedLifecycleProbe(List<String> events) {
        this.events = events;
        events.add("constructor");
    }

    @PostConstruct
    void init() {
        events.add("postConstruct");
    }

    @Override
    public void afterPropertiesSet() {
        events.add("afterPropertiesSet");
    }
}
```

Trong project thật, không nên dùng một `List<String>` bean toàn cục tùy tiện cho mọi test. Hãy tạo fixture/test configuration riêng để tránh state leak và đảm bảo list được chia sẻ đúng giữa probe và test.

Một test có thể khởi tạo context, lấy list và assert thứ tự callback. Khi test destruction, đóng context rồi kiểm tra các destruction events.

Đối với runner/event ordering, tạo một context test nhỏ hoặc `@SpringBootTest` và ghi nhận event sequence trong một collector test-only.

## 50. Đóng context trong test

Ví dụ dùng `AnnotationConfigApplicationContext` để quan sát init/destroy mà không khởi chạy web server:

```java
try (AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext()) {

    context.register(LifecycleConfiguration.class);
    context.refresh();

    LifecycleProbe probe =
            context.getBean(LifecycleProbe.class);

    System.out.println("context is running");
}
```

Khi thoát khỏi try-with-resources, context được đóng và Spring gọi destruction callbacks cho singleton beans được quản lý.

Cách này phù hợp để test bean lifecycle nhỏ. Với startup runners và Boot application events, dùng `SpringApplication`/`@SpringBootTest` vì chúng thuộc quy trình của Spring Boot.

## 51. Những khác biệt theo scope

| Scope | Initialization | Destruction |
|---|---|---|
| Singleton | Khi container tạo bean (eager hoặc lazy) | Container gọi callbacks khi context đóng |
| Prototype | Mỗi lần container tạo instance | Client/application tự quản lý cleanup |
| Request/session | Theo scope web tương ứng | Theo vòng đời request/session và scope infrastructure |
| Custom scope | Theo implementation của scope | Theo contract của custom scope |

Không áp dụng một quy tắc destroy duy nhất cho mọi scope. Khi bean sở hữu resource, hãy xác định ai là owner và ai có trách nhiệm đóng.

Nếu bean prototype được inject trực tiếp vào singleton, singleton chỉ nhận một instance tại thời điểm injection theo cách cấu hình hiện tại; muốn lấy prototype mới mỗi lần cần dùng `ObjectProvider`, provider hoặc scope proxy phù hợp.

## 52. Lỗi thường gặp khi đọc lifecycle log

| Hiện tượng | Nguyên nhân có thể | Điều tra |
|---|---|---|
| Field `@Autowired` là null trong constructor | Field injection diễn ra sau constructor | Dùng constructor injection hoặc kiểm tra sau population |
| `@PostConstruct` không chạy | Bean chưa được tạo, sai annotation namespace hoặc bean không do Spring quản lý | Kiểm tra registration/scope/dependency |
| Init method không được gọi | Tên method sai hoặc chưa khai báo `initMethod` | Kiểm tra bean definition |
| `@Transactional` không hoạt động trong init | Target chưa được expose qua proxy cuối hoặc self-invocation | Chuyển công việc sang giai đoạn phù hợp |
| Không thấy proxy | Không có advisor phù hợp hoặc bean không được proxy | Kiểm tra AOP configuration và pointcut |
| Self-invocation bỏ qua advice | Call đi qua `this`, không qua proxy | Tách bean hoặc gọi qua proxy |
| Runner không chạy | Context startup fail trước runners hoặc bean runner không được đăng ký | Đọc startup exception và bean definitions |
| `ApplicationReadyEvent` không xuất hiện | Runner thất bại hoặc startup chưa hoàn tất | Kiểm tra runner logs/exception |
| Runner làm app không ready | Công việc dài hoặc block | Chuyển background work sang lifecycle-managed component |
| `@PreDestroy` không xuất hiện | Bean chưa được tạo, scope không được container hủy, hoặc shutdown cưỡng bức | Kiểm tra scope và cách đóng context |
| Prototype không được destroy | Prototype destruction do caller quản lý | Dùng `close()`/resource management |
| Shutdown bị treo | Callback chờ vô hạn hoặc stop callback không được gọi | Đặt timeout và hoàn tất callback |
| Hai callback init chạy hai lần | Bean/context được tạo nhiều lần hoặc có nhiều context | Log context ID và bean identity |
| Thứ tự log thay đổi | Dependency graph/lazy init/order khác nhau | Xác định dependency và thứ tự cần thiết |
| BeanPostProcessor không thấy một số bean | Processor đăng ký quá muộn hoặc dependency khởi tạo sớm | Kiểm tra đăng ký BPP và early initialization |

## 53. Quy trình điều tra một log khó hiểu

Khi startup log không theo thứ tự bạn dự kiến:

1. Ghi lại tên bean và context ID của từng dòng.
2. Phân loại dòng log là constructor, population, Aware, BPP, init, proxy, runner, event hay destroy.
3. Kiểm tra dependency graph của bean.
4. Xác nhận bean có lazy hay không.
5. Kiểm tra các `BeanPostProcessor` và AOP advisors liên quan.
6. Xác định log thuộc application context nào.
7. Kiểm tra `@Order`/`Ordered` nếu đang so sánh runners hoặc lifecycle phase.
8. Kiểm tra có exception làm startup dừng giữa chừng không.
9. Kiểm tra cách context được đóng và scope của bean.
10. Chỉ dựa vào các quan hệ ordering được Spring đảm bảo; không giả định thứ tự giữa beans độc lập.

Log tốt cần stage và identity rõ ràng. Một timestamp đơn lẻ không đủ nếu nhiều bean được tạo song song hoặc log đến từ nhiều context.

## 54. Bài tập thực hành

### Bài tập A — Constructor và dependency injection

Tạo `OrderService` inject `OrderRepository` qua constructor. Ghi log trong constructor và trong `@PostConstruct`. So sánh với field injection để thấy thời điểm field được populate.

### Bài tập B — Thứ tự init callbacks

Tạo một bean dùng `@PostConstruct`, `InitializingBean.afterPropertiesSet()` và custom init method. Đăng ký custom method qua `@Bean(initMethod=...)`. Quan sát thứ tự callback.

### Bài tập C — BeanPostProcessor

Viết `TraceBeanPostProcessor` và đăng ký bằng static `@Bean` method. In bean name/class trước và sau initialization. Thử lọc theo package để tránh log quá nhiều.

### Bài tập D — AOP proxy

Tạo service có `@Transactional` hoặc một aspect đơn giản. Dùng `AopUtils.isAopProxy()` để kiểm tra bean được inject. So sánh target type và proxy type.

### Bài tập E — Self-invocation

Tạo hai method trong cùng một service, một method có `@Transactional`, method kia gọi nội bộ. Quan sát advice không chạy như mong đợi. Tách method sang bean khác và so sánh.

### Bài tập F — SmartInitializingSingleton

Tạo một bean implement `SmartInitializingSingleton`. Ghi log `afterSingletonsInstantiated()` và so sánh với `ContextRefreshedEvent` và `ApplicationRunner`.

### Bài tập G — Runner ordering

Tạo hai `ApplicationRunner` và một `CommandLineRunner`, gắn `@Order` khác nhau. Chạy ứng dụng với arguments và ghi lại thứ tự.

### Bài tập H — Runner failure

Cho một runner ném exception. Quan sát startup log và xác định `ApplicationReadyEvent` có xuất hiện hay không. Sau đó xử lý lỗi theo policy fail-fast hoặc degraded startup.

### Bài tập I — ApplicationReadyEvent

Tạo listener cho `ApplicationStartedEvent` và `ApplicationReadyEvent`. Đặt một runner có log bắt đầu/kết thúc để xác nhận thứ tự.

### Bài tập J — Destroy callbacks

Tạo bean dùng `@PreDestroy`, `DisposableBean` và custom destroy method. Đóng context tường minh và quan sát thứ tự.

### Bài tập K — Prototype cleanup

Tạo prototype bean sở hữu resource giả lập. Lấy nhiều instances từ container, đóng chúng bằng `AutoCloseable` hoặc cơ chế quản lý riêng. Xác nhận context không tự quản lý destruction cho các prototype instances như singleton.

### Bài tập L — SmartLifecycle

Tạo hai lifecycle components với phase khác nhau. Ghi log start/stop và xác nhận thứ tự đảo ngược khi shutdown. Thử asynchronous `stop(Runnable)` và bảo đảm callback được gọi đúng một lần.

### Bài tập M — Graceful shutdown

Bật `server.shutdown=graceful`, cấu hình timeout phù hợp và gửi request đang xử lý khi ứng dụng nhận tín hiệu shutdown. Quan sát server ngừng nhận request mới và chờ request đang chạy trong giới hạn được cấu hình.

### Bài tập N — Lifecycle timeline

Kết hợp một probe bean, BPP, AOP service, `SmartInitializingSingleton`, runner, application event listeners và destruction callbacks. Vẽ timeline từ startup đến shutdown dựa trên log thực tế.

## 55. Ghi nhớ

1. Constructor tạo instance; constructor dependencies phải được resolve trước khi gọi constructor.
2. Field/setter injection diễn ra sau khi instance được tạo; không đọc field injection trong constructor.
3. Aware callbacks cung cấp thông tin container trước initialization callbacks.
4. `BeanPostProcessor` có hai giai đoạn chính: trước và sau initialization.
5. Thứ tự init phổ biến là `@PostConstruct`, `afterPropertiesSet()`, custom init method.
6. AOP auto-proxy creator thường bọc target trong post-processing; consumer nhận proxy khi bean cần advice.
7. Bean có proxy không có nghĩa self-invocation sẽ đi qua proxy.
8. `SmartInitializingSingleton` chạy sau khi regular singleton beans đã được pre-instantiate.
9. `SmartLifecycle` quản lý start/stop theo phase của application context.
10. `ContextRefreshedEvent` không đồng nghĩa Spring Boot application đã hoàn tất runners.
11. `ApplicationRunner` và `CommandLineRunner` chạy sau context refresh, trước `ApplicationReadyEvent`.
12. `@Order`/`Ordered` xác định thứ tự runners; không dựa vào component scanning order.
13. Runner thất bại có thể làm startup thất bại và ngăn application đạt ready state.
14. Không dùng runner cho vòng lặp vô hạn hoặc background task không có lifecycle.
15. `@PreDestroy`, `DisposableBean.destroy()` và custom destroy method được gọi theo thứ tự destruction chuẩn.
16. Singleton beans được container quản lý destruction; prototype cleanup thuộc trách nhiệm caller.
17. Lazy bean chưa được tạo thì không có instance để gọi init/destroy callbacks.
18. `SmartLifecycle` stop có thể bất đồng bộ; phải hoàn tất callback trong timeout hợp lý.
19. Graceful shutdown cần phối hợp timeout của Spring Boot với termination grace period của container/orchestrator.
20. Shutdown hook không chạy nếu process bị kill cưỡng bức hoặc máy/JVM gặp sự cố đột ngột.
21. Cleanup callback nên ngắn, bounded, idempotent và chỉ đóng resource mà bean sở hữu.
22. Log cần bean name, stage và context ID để phân biệt nhiều bean/context.
23. Khi phân tích thứ tự, chỉ dựa vào dependency/order/phase mà framework đảm bảo; đừng giả định thứ tự của beans độc lập.

**Tư duy cốt lõi:** constructor và init callbacks cho biết **một bean được tạo và chuẩn bị thế nào**; BeanPostProcessor và AOP cho biết **object nào được expose cho consumer**; runners và application events cho biết **khi nào ứng dụng hoàn tất startup**; destroy callbacks và SmartLifecycle cho biết **cách ứng dụng dừng và giải phóng tài nguyên**. Khi phân loại log theo đúng bốn lớp này, bạn có thể lần theo vòng đời Spring Boot từ lúc tạo bean đến khi shutdown mà không nhầm một callback với trạng thái sẵn sàng của toàn ứng dụng.
