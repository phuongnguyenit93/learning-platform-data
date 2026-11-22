# Singleton khởi tạo sớm và quá trình tiền khởi tạo trong Spring Core Container

## 1. Mục tiêu bài học

Một trong những hành vi quan trọng nhất của Spring IoC Container là **thời điểm tạo bean**. Với `ApplicationContext`, Spring mặc định **tạo và cấu hình các singleton không lazy ngay trong quá trình khởi động context** (*eager singleton initialization / singleton pre-instantiation*). Nhờ đó, những lỗi như thiếu dependency, constructor thất bại, cấu hình sai hoặc callback khởi tạo lỗi thường được phát hiện trước khi ứng dụng bắt đầu xử lý công việc.

Khái niệm này dễ bị hiểu nhầm theo hai chiều:

- “Singleton chỉ được tạo khi có `getBean()` lần đầu” — **không đúng mặc định với `ApplicationContext`**.
- “Có bean definition nghĩa là object đã được tạo” — **không đúng**. Definition là metadata, còn instance xuất hiện ở một giai đoạn sau.
- “`@Lazy` bảo đảm bean không bao giờ được tạo khi startup” — **không tuyệt đối**. Một singleton eager phụ thuộc bắt buộc vào lazy bean có thể buộc Spring tạo lazy bean để hoàn thành dependency.
- “Pre-instantiation nghĩa là tạo tất cả bean của mọi scope” — **không đúng**. Nó chủ yếu liên quan **singleton không lazy**, có ngoại lệ và chi tiết riêng cho `FactoryBean`, dependency graph và cơ chế bootstrap.

Bài học này thuộc phần **Thời điểm tạo bean** của **Spring Framework – Core Container**, nhằm giúp bạn:

1. Phân biệt `BeanDefinition`, bean instance, scope singleton và cache singleton.
2. Nắm được thời điểm `ApplicationContext.refresh()` thực hiện pre-instantiation.
3. Hiểu hành vi mặc định **eager singleton** và lý do Spring ưu tiên phát hiện lỗi sớm.
4. Dùng `@Lazy`, XML `lazy-init`, `default-lazy-init` và hiểu cách dependency làm lazy bean bị tạo sớm.
5. So sánh `ApplicationContext` với `BeanFactory` sử dụng ở mức thấp.
6. Biết sự khác nhau giữa *được đăng ký*, *đang được tạo*, *đã khởi tạo đầy đủ* và *đang tồn tại trong singleton cache*.
7. Hiểu mối liên hệ của constructor, dependency injection, `@PostConstruct`, `InitializingBean`, `initMethod` và `BeanPostProcessor`.
8. Hiểu callback `SmartInitializingSingleton.afterSingletonsInstantiated()` tại cuối giai đoạn pre-instantiation.
9. Biết vì sao `@DependsOn` biểu diễn ordering chứ không thay thế constructor dependency hay job orchestration.
10. Chẩn đoán startup chậm, lỗi bean creation, vòng dependency và side effects trong startup.
11. Viết và chạy ví dụ **Java 17 + Spring Framework 6.2** có output ổn định, không phụ thuộc thứ tự tạo bean tình cờ.
12. Kiểm tra bean có thật sự được tạo bằng API phù hợp và xây integration tests theo lifecycle.

**Nguyên tắc trung tâm:** **singleton** trả lời câu hỏi “bao nhiêu instance được quản lý cho một bean definition trong một container?”, còn **eager/lazy** trả lời câu hỏi “instance được tạo lúc nào?”. Hai trục này độc lập về khái niệm.

## 2. Singleton trong Spring là gì?

Mặc định, một bean definition Spring có scope `singleton`:

```java
@Configuration(proxyBeanMethods = false)
class ServiceConfig {

    @Bean
    AccountService accountService() {
        return new AccountService();
    }
}
```

Đây là **đoạn minh họa**, cần class `AccountService` thực tế. Khi BeanFactory quản lý bean `accountService` theo singleton scope, những lần tra cứu bean này trong cùng container thường nhận cùng reference:

```java
// Đoạn minh họa dùng biến context đã được tạo.
Object first = context.getBean("accountService");
Object second = context.getBean("accountService");
System.out.println(first == second); // true
```

Spring lưu và trả lại instance singleton đã được quản lý; không gọi factory method một lần cho mỗi `getBean()`.

### Singleton của Spring không phải GoF Singleton pattern

| Khía cạnh | Spring singleton scope | GoF Singleton pattern |
| --- | --- | --- |
| Đơn vị quản lý | Mỗi **bean definition**, trong một **container** | Thường do class/loader hoặc static field kiểm soát |
| Cơ chế tạo | BeanFactory theo bean metadata và lifecycle | Logic trong class như private constructor + static method |
| Tính linh hoạt | Một class có thể có nhiều bean definitions tên khác nhau | Thường nhắm tới một instance toàn cục |
| Thử nghiệm | Mỗi test ApplicationContext có thể có các singleton riêng | Global static instance dễ gây chia sẻ state |
| AOP/proxy | Reference bean có thể là proxy được quản lý | Không phải đặc trưng của pattern |

Nếu một ApplicationContext khai báo hai bean names cùng dùng class `Client`, container có thể tạo **hai singleton độc lập**. “Singleton” không có nghĩa mỗi Java class chỉ có đúng một object trên toàn JVM.

### Scope và thời điểm tạo là hai thuộc tính khác nhau

Bean `singleton` có thể:

- **Eager:** được tạo khi context refresh, trước khi application code gọi `getBean()`.
- **Lazy:** được tạo khi container cần instance lần đầu.
- **Lazy nhưng bị dependency kéo lên sớm:** một singleton eager cần nó làm constructor parameter.
- **Được đăng ký sau khi context đã hoạt động:** các thao tác dynamic registration có lifecycle riêng, không nên mặc định diễn giải giống luồng refresh ban đầu.

Bean `prototype` thường được tạo mỗi lần được yêu cầu; nó không được “pre-instantiate toàn bộ” bằng một lượt refresh như singleton thông thường.

## 3. BeanDefinition không phải là bean instance

Spring đọc metadata từ nhiều nguồn: `@Configuration`/`@Bean`, component scanning, XML `<bean>`, hoặc registration qua `BeanDefinitionRegistry`. Từ các nguồn đó, nó biết **bean cần tồn tại** trước khi nhất thiết dựng object.

Sơ đồ:

```text
@Configuration / @Bean / @Component / XML
                     |
                     v
               BeanDefinition
         tên bean, class/factory method,
         scope, lazy, dependencies, init...
                     |
                     v
        BeanFactory đăng ký definition
                     |
                Theo nhu cầu
        hoặc singleton pre-instantiation
                     |
                     v
         Constructor / factory method
                     |
                     v
           Dependency injection
                     |
                     v
            Initialization phase
                     |
                     v
       Fully initialized managed bean
                     |
                     v
       Singleton cache / bean exposure
```

Một số bước có thể lồng nhau và Spring còn xử lý `BeanPostProcessor`, AOP proxies, circular-reference protection, awareness callbacks và hạ tầng liên quan. Sơ đồ là mô hình tư duy, **không phải mô tả đầy đủ từng bước nội bộ** của mọi BeanFactory.

### Kiểm tra “definition có” khác “singleton đã được tạo”

Với `ConfigurableApplicationContext`:

```java
// Minh họa khi context đang active.
boolean defined =
        context.getBeanFactory().containsBeanDefinition("client");
boolean instantiated =
        context.getBeanFactory().containsSingleton("client");
```

- `containsBeanDefinition("client")` hỏi registry có **local definition** tên đó không; không có nghĩa đã instantiate.
- `containsSingleton("client")` hỏi singleton registry hiện giữ **singleton object** cho tên đó hay chưa.
- `containsBean("client")` nói tên bean có thể resolve được hay không (có thể xét parent/alias theo API), **không** phải bài test “đã xây object”.
- `getBean("client")` **có thể tự làm bean được tạo**, nên đừng dùng nó để kiểm tra trạng thái trước-instantiation rồi nói rằng không ảnh hưởng quá trình quan sát.

Ngoài ra, hạ tầng có thể đăng ký singleton objects không xuất phát từ một BeanDefinition thông thường; đó là lý do đừng kết luận hai API kiểm tra definition và singleton cache luôn đồng nhất.

## 4. Eager singleton: hành vi mặc định của ApplicationContext

Trong `ApplicationContext` thông dụng, Spring tạo và cấu hình **những singleton bean bình thường, không lazy** khi context được khởi tạo/refresh.

```java
try (var context =
        new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Khi constructor trả về, refresh đã thực hiện
    // giai đoạn pre-instantiation mặc định.
}
```

Đây là đoạn minh họa, `AppConfig` cần được khai báo và import API `org.springframework.context.annotation.AnnotationConfigApplicationContext`.

Điều quan trọng là **trước khi đi vào body của `try`**, constructor `AnnotationConfigApplicationContext(AppConfig.class)` đã tạo context và refresh. Vì vậy một singleton eager có thể đã gọi constructor/init callback ngay cả khi user code chưa tra cứu bean nào.

### Vì sao Spring tạo sớm?

- **Fail fast:** Thiếu bean, lỗi converter, sai property hoặc constructor exception lộ ra khi startup.
- **Dependency graph:** Các singleton thường sẵn sàng phục vụ lần gọi đầu tiên của application.
- **Lifecycle ổn định hơn:** Init callbacks của các bean cần thiết được thực thi trước khi context được coi là hoàn tất khởi tạo.
- **Khả năng quan sát:** Lỗi cấu hình có nguyên nhân rõ tại startup thay vì phát sinh ngẫu nhiên khi người dùng đầu tiên gọi API.
- **Nghĩa vụ của container:** `ApplicationContext` có thể chủ động chuẩn bị một loạt infrastructure beans như listener, lifecycle processors và bean post-processors đúng giai đoạn.

Đổi lại, việc tạo nhiều singleton có thể làm startup tốn CPU, RAM, filesystem, I/O và thời gian kết nối external dependencies. Cần phân biệt **chi phí dựng bean hợp lệ** với **business workflow nặng bị nhét vào constructor/init callback**.

### Chính xác Spring tạo cái gì?

Cách diễn đạt hữu ích là: Spring pre-instantiates **regular, non-lazy singleton beans** trong BeanFactory. Đây **không** phải tuyên bố mọi bean ở mọi scope, lazy dependencies hay mọi external resource đều đã sẵn sàng.

Một bean prototype không tự được tạo chỉ vì đã có definition. Nhưng nếu constructor của eager singleton cần prototype, Spring có thể **tạo một prototype instance** để inject vào singleton. Đó là **dependency-driven creation**, không phải “preinstantiate tất cả prototype beans”.

## 5. Giai đoạn pre-instantiation nằm ở đâu trong refresh?

`ApplicationContext.refresh()` thực hiện nhiều bước để biến metadata thành container có thể phục vụ. Một luồng khái niệm:

```text
ApplicationContext.refresh()
   |
   +--> Chuẩn bị Environment và context
   |
   +--> Tạo / lấy BeanFactory, nạp bean definitions
   |
   +--> BeanFactoryPostProcessor / registry processing
   |
   +--> Đăng ký BeanPostProcessor
   |
   +--> Hạ tầng application events, message source, lifecycle...
   |
   +--> finishBeanFactoryInitialization(...)
   |       |
   |       +--> preInstantiateSingletons()
   |                |
   |                +--> Tạo regular singleton non-lazy
   |                +--> Resolve dependencies
   |                +--> Chạy bean-local initialization
   |                +--> SmartInitializingSingleton callbacks
   |
   +--> finishRefresh(...)
           |
           +--> Lifecycle startup theo cơ chế tương ứng
           +--> ContextRefreshedEvent
```

Đây là **sơ đồ đơn giản hóa** cho ApplicationContext chuẩn, không cam kết chi tiết ordering của mọi extension point, bean definition, event multicaster hay công việc background trong mọi phiên bản.

### preInstantiateSingletons() là API nào?

`org.springframework.beans.factory.config.ConfigurableListableBeanFactory` công bố:

```java
void preInstantiateSingletons();
```

Method này đảm bảo pre-instantiation cho **non-lazy singletons**, với xử lý riêng liên quan `FactoryBean`, và có thể ném `BeansException` nếu không tạo được một bean.

Trong `ApplicationContext`, bạn thường **không cần gọi method này bằng tay**, vì lifecycle `refresh()` đảm trách. API này hữu ích để hiểu cơ chế hoặc khi bạn làm việc với một `DefaultListableBeanFactory` ở mức thấp.

### “Đã pre-instantiate” không có nghĩa “đã chạy mọi business task”

Pre-instantiation hoàn thiện nhóm bean instances theo lifecycle của chúng. Nó không tự:

- Seed cơ sở dữ liệu hoặc chạy migration nghiệp vụ nếu không có code/hạ tầng được đăng ký làm việc đó.
- Bảo đảm message broker, database cluster, external APIs đã healthy.
- Tạo tất cả singleton lazy không cần dùng.
- Bảo đảm scheduler/consumer lifecycle đã start xong trước mọi mốc lifecycle khác.
- Biến một callback init thành cơ chế exactly-once trong môi trường nhiều replicas.

## 6. Phân biệt BeanFactory thuần và ApplicationContext

`BeanFactory` là giao diện IoC container nền tảng. Một số chương trình có thể dùng `DefaultListableBeanFactory` và tự đăng ký `BeanDefinition`, rồi gọi `getBean` khi cần.

Nếu bạn chỉ đăng ký definition vào một `DefaultListableBeanFactory` mới, nó **không tự giả định bạn muốn làm đầy toàn bộ non-lazy singletons ngay lúc registration**. Bạn có thể gọi `preInstantiateSingletons()` khi cần hoặc để chúng được tạo qua `getBean()`.

Ngược lại, `AnnotationConfigApplicationContext`/`ClassPathXmlApplicationContext` thường điều phối cả BeanFactory setup, BeanPostProcessors và pre-instantiation trong `refresh()`.

### Ví dụ minh họa

```java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "tool", new RootBeanDefinition(Tool.class));

// Có definition, chưa chắc đã có instance.
boolean before = factory.containsSingleton("tool");

// Kích hoạt pre-instantiation bằng tay:
factory.preInstantiateSingletons();
boolean after = factory.containsSingleton("tool");
```

Đây là đoạn minh họa, `Tool` phải là class phù hợp với public constructor và cần imports `DefaultListableBeanFactory`/`RootBeanDefinition`. Một phiên bản runnable riêng của ý tưởng này nằm ở mục 14.

**Không dùng raw BeanFactory demo để suy ra toàn bộ tính năng ApplicationContext hoạt động tự động**: BeanPostProcessors, annotation-driven features, application events và lifecycle orchestration có những bước registration riêng.

## 7. Lazy singleton: trì hoãn việc tạo

`@Lazy` khiến một bean definition có chủ đích **không bị pre-instantiate** như singleton eager thông thường.

```java
@Configuration(proxyBeanMethods = false)
class Config {

    @Bean
    @Lazy
    HeavyCatalog heavyCatalog() {
        return new HeavyCatalog();
    }
}
```

Đây là minh họa cần `HeavyCatalog`. Nếu không có eager bean nào phụ thuộc bắt buộc vào `HeavyCatalog`, container có thể trì hoãn khởi tạo cho đến lần đầu nó được yêu cầu.

Trong XML:

```xml
<bean id="heavyCatalog"
      class="example.HeavyCatalog"
      lazy-init="true"/>
```

### Eager mặc định và lazy tường minh

| Bean definition | Scope | Lazy? | Khi nào thường tạo? |
| --- | --- | --- | --- |
| `@Bean CatalogRepository repository()` | singleton mặc định | Không | Trong `ApplicationContext.refresh()` |
| `@Bean @Lazy CacheClient cacheClient()` | singleton | Có | Khi được yêu cầu lần đầu nếu không bị eager dependency kéo lên |
| XML `<bean id="repo" .../>` | singleton mặc định | Không | Khi ApplicationContext refresh |
| XML `<bean id="cache" ... lazy-init="true"/>` | singleton | Có | On demand, trừ khi cần cho bean eager |
| `@Scope("prototype")` | prototype | Không gắn eager singleton semantics | Theo nhu cầu, kể cả khi làm dependency |
| Lazy singleton dependency của eager singleton | singleton | Có | Có thể **bị tạo lúc startup** |

Đặc biệt: **lazy không phải một scope mới**. Một singleton lazy sau khi được tạo vẫn có singleton identity như thường.

### @Lazy trên class @Configuration

```java
@Configuration
@Lazy
class LazyConfiguration {
    @Bean
    ExpensiveClient client() {
        return new ExpensiveClient();
    }
}
```

Theo Spring reference, `@Lazy` trên `@Configuration` có thể đặt default lazy initialization cho các bean definitions thuộc configuration đó. Nhưng những singleton bị eager beans khác yêu cầu vẫn có thể được tạo, và infrastructure/configuration-processing mechanics có quy tắc riêng. Không mặc định toàn context trở thành “không khởi tạo bean nào”.

### XML default-lazy-init

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">
    <bean id="client" class="example.Client"/>
    <bean id="service" class="example.Service"/>
</beans>
```

Đây là minh họa giản lược namespace; trong ứng dụng thật, nên khai báo XML schema và các namespace đầy đủ. `default-lazy-init="true"` đặt default lazy cho beans trong phạm vi metadata đó. Bean có `lazy-init="false"` tường minh có thể được đánh eager, và dependency graph vẫn có thể tạo sớm lazy collaborators.

## 8. Bẫy: lazy bean là dependency của eager singleton

Đây là ngoại lệ được Spring docs nhấn mạnh.

Giả sử:

```java
@Configuration(proxyBeanMethods = false)
class Config {

    @Bean
    @Lazy
    PriceRules priceRules() {
        return new PriceRules();
    }

    @Bean
    CheckoutService checkoutService(PriceRules priceRules) {
        return new CheckoutService(priceRules);
    }
}
```

Hai kiểu ở đây là minh họa. `priceRules` có metadata lazy; nhưng `checkoutService` là singleton không lazy. Khi Spring cần tạo `checkoutService` lúc refresh, nó phải truyền một `PriceRules` instance vào constructor, vì vậy bean `priceRules` được tạo **lúc startup**.

```text
checkoutService (eager singleton)
         |
         +--> constructor parameter: PriceRules
                            |
                            v
                   priceRules (lazy definition)
                            |
                            v
              Vẫn bị instantiate lúc refresh
```

**Ghi nhớ:** `@Lazy` trên **bean definition** không tự tạo proxy cho mọi dependency injection point. Nếu eager consumer cần instance thật để hoàn thành constructor, BeanFactory sẽ resolve nó.

### @Lazy ở injection point khác lazy ở definition

Spring cũng hỗ trợ `@Lazy` trên điểm injection để tạo một **lazy-resolution proxy** trong những tình huống phù hợp:

```java
final class CheckoutService {
    private final PriceRules rules;

    CheckoutService(@Lazy PriceRules rules) {
        this.rules = rules;
    }
}
```

Đoạn này cần import `org.springframework.context.annotation.Lazy`. Tại injection point, Spring có thể inject proxy trì hoãn target resolution. Nhưng việc dùng proxy có giới hạn type/proxy semantics, và **không sửa vòng dependency/thiết kế sai** chỉ bằng trì hoãn.

Hơn nữa, nếu code gọi method của proxy trong constructor hoặc init callback, target vẫn có thể bị tạo rất sớm. Đừng coi `@Lazy` injection point là bảo đảm tuyệt đối cho mọi trạng thái startup.

## 9. Prototype khác pre-instantiated singleton như thế nào?

`prototype` có nghĩa BeanFactory tạo một instance mới mỗi lần được yêu cầu theo semantics của scope đó.

```java
@Bean
@Scope("prototype")
Worker worker() {
    return new Worker();
}
```

Đây là minh họa cần `Worker` và import `Scope`. Bean `worker` sẽ không bị bulk pre-instantiated chỉ vì nằm trong registry.

Tuy nhiên:

```java
@Bean
JobRunner jobRunner(Worker worker) {
    return new JobRunner(worker);
}
```

Nếu `jobRunner` là singleton eager, Spring tạo một `Worker` prototype để inject **khi JobRunner được tạo**. `JobRunner` giữ cùng worker ấy cho đến khi logic của nó tự thay đổi reference; không tự nhận prototype mới cho mỗi lần gọi `run()`.

### Factory/Provider cho nhu cầu object mới mỗi lần

```java
final class JobRunner {
    private final ObjectProvider<Worker> workers;

    JobRunner(ObjectProvider<Worker> workers) {
        this.workers = workers;
    }

    void runJob() {
        Worker fresh = workers.getObject();
        fresh.run();
    }
}
```

Đây là minh họa cần import `org.springframework.beans.factory.ObjectProvider` và method `Worker.run()`. Mỗi lượt `getObject()` đối với prototype có thể tạo một instance mới. Nhưng đừng dùng provider chỉ để che một vòng constructor hay dependency bắt buộc bị thiếu.

### Prototype destruction

Container thực hiện initialization cho prototype bean được tạo, nhưng không tự quản lý destroy callbacks của mọi prototype giống singleton sau khi phát instance cho caller. Nếu worker sở hữu file/socket/resource, application phải thiết kế ownership và cleanup.

## 10. Lifecycle của một eager singleton

Pre-instantiation không đơn giản là gọi constructor rồi lưu object. Với Spring-managed bean, có thể có:

1. Đăng ký bean definition.
2. Chọn constructor hoặc `@Bean` factory method.
3. Resolve các bean dependencies bắt buộc.
4. Construct raw instance.
5. Dependency/property injection.
6. `Aware` callbacks phù hợp.
7. `BeanPostProcessor` hooks và initialization annotations.
8. `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, custom `initMethod` theo cơ chế Spring.
9. Proxy wrapping và các post-processing hoàn tất.
10. Publish bean instance trong singleton registry theo semantics của container.

Các bước có thể khác trong những infrastructure beans hoặc extension points; nhất là AOP/proxy, factory methods, `FactoryBean` và early singleton references. Điều cốt lõi là chỉ khi bean đã trải qua lifecycle thích hợp mới nên coi nó “sẵn sàng”.

### Constructor chạy trước @PostConstruct

```java
final class LocalIndex {
    private boolean ready;

    public LocalIndex() {
        ready = false;
    }

    void initialize() {
        ready = true;
    }
}
```

Nếu khai báo `@Bean(initMethod="initialize")`, Spring gọi init method sau khi factory tạo instance và chuẩn bị injection tương ứng. Trong init callback của bean, không nên giả định mọi bean khác trong toàn context đều sẵn sàng.

### Không chạy nghiệp vụ nặng trong constructor và @PostConstruct

Spring 6.2 documentation lưu ý initialization callbacks của singleton thường chạy trong phạm vi quản lý **singleton creation lock**. Công việc nặng, external I/O hoặc truy cập lẫn lộn sang bean khác từ init callback có thể kéo dài startup hoặc phát sinh deadlock.

Phù hợp:

- Validate local settings.
- Chuẩn bị một bảng tra cứu nội bộ nhỏ.
- Xác nhận invariant của bean.
- Khởi tạo resource mà bean thực sự sở hữu theo lifecycle được thiết kế, với timeout/cleanup.

Cần cân nhắc cơ chế muộn hơn:

- Seed dữ liệu nghiệp vụ.
- Gọi nhiều API ngoài để chuẩn bị hệ thống.
- Start background worker dài hạn.
- Điều phối transaction và readiness giữa nhiều modules.

Các việc này nên có startup coordinator hoặc lifecycle extension point thích hợp, không gắn ngẫu nhiên vào mọi constructor.

## 11. SmartInitializingSingleton: hook cuối pha pre-instantiation

`org.springframework.beans.factory.SmartInitializingSingleton` cung cấp callback:

```java
public interface SmartInitializingSingleton {
    void afterSingletonsInstantiated();
}
```

Một singleton non-lazy implement interface này có thể được gọi **sau khi BeanFactory hoàn tất pre-instantiation các singleton thông thường**.

Lợi ích:

- Bean muốn làm một bước hậu khởi tạo có thể giả định các **regular non-lazy singleton beans** đã tạo xong.
- Giảm nguy cơ một lời gọi `getBeansOfType(...)` vô tình gây early initialization trong chính giai đoạn tạo singleton.
- Phù hợp cho công việc hậu khởi tạo nhiều bean nhưng không cần ApplicationContext event model.
- Cơ chế được hỗ trợ bởi `ListableBeanFactory` thích hợp, không chỉ listener của `ApplicationContext`.

### Callback có chạy cho một lazy singleton tạo sau startup?

**Không mặc định.** Javadoc nêu callback này không được kích hoạt cho singleton vốn lazy và chỉ được tạo theo nhu cầu **sau BeanFactory bootstrap**, cũng không được kích hoạt cho các scope khác.

Nếu coordinator cần chạy ở startup, hãy bảo đảm chính coordinator là managed **non-lazy singleton** được tạo trong pre-instantiation phase.

### Callback này có phải ApplicationReadyEvent của Spring Boot?

Không. `SmartInitializingSingleton` nằm trong Spring Framework beans module và chạy ở cuối **singleton pre-instantiation**, không mang nghĩa toàn bộ web server đã công bố readiness hay toàn hệ thống bên ngoài đã sẵn sàng.

`ContextRefreshedEvent` được phát sau các giai đoạn refresh phù hợp. `ApplicationReadyEvent` thuộc **Spring Boot**, thường xuất hiện muộn hơn trong lifecycle Boot. Đừng gộp những mốc này thành một khái niệm “ứng dụng đã làm xong mọi thứ”.

### Khi nào nên dùng SmartLifecycle thay thế?

Nếu thành phần có **start/stop theo phase** như consumer, poller hoặc long-running listener, Spring khuyến nghị `Lifecycle`/`SmartLifecycle` để quản lý start/stop, shutdown callbacks và phase ordering. `SmartInitializingSingleton` thích hợp cho callback ngắn sau pre-instantiation, không phải nơi đặt một vòng lặp vô hạn.

## 12. Ví dụ runnable: eager, lazy, lazy bị kéo lên sớm

Ví dụ dùng **Java 17, Spring Framework 6.2.19 và Maven**. Nó không cần Spring Boot, DB, network hay các file ngoài project.

Để tránh dựa vào **thứ tự constructor output** của Spring, ta dùng `Tracker` ghi lại các mốc sự kiện. Chương trình chỉ in các **trạng thái đúng theo hợp đồng dependency** sau khi context refresh hoàn thành, nhờ đó stdout ổn định.

### 12.1. Cấu trúc dự án

```text
spring-eager-singletons/
├── pom.xml
└── src/main/java/demo/
    └── EagerSingletonDemo.java
```

### 12.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-eager-singletons</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 12.3. File Java đầy đủ

Tạo `src/main/java/demo/EagerSingletonDemo.java`:

```java
package demo;

import java.util.HashSet;
import java.util.Set;

import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

public class EagerSingletonDemo {

    public static final class Tracker {
        private final Set<String> events = new HashSet<>();

        public void mark(String event) {
            events.add(event);
        }

        public boolean has(String event) {
            return events.contains(event);
        }
    }

    public static final class EagerCache {
        private final Tracker tracker;

        public EagerCache(Tracker tracker) {
            this.tracker = tracker;
            tracker.mark("eager.constructed");
        }

        public void initialize() {
            tracker.mark("eager.initialized");
        }

        public void shutdown() {
            tracker.mark("eager.destroyed");
        }
    }

    public static final class RequiredIndex {
        public RequiredIndex(Tracker tracker) {
            tracker.mark("required.created");
        }
    }

    public static final class OptionalGateway {
        public OptionalGateway(Tracker tracker) {
            tracker.mark("optional.created");
        }
    }

    public static final class EagerConsumer {
        private final RequiredIndex index;
        private final EagerCache cache;

        public EagerConsumer(RequiredIndex index, EagerCache cache) {
            this.index = index;
            this.cache = cache;
        }

        public boolean hasDependencies() {
            return index != null && cache != null;
        }
    }

    public static final class StartupCheck
            implements SmartInitializingSingleton {
        private final Tracker tracker;

        public StartupCheck(Tracker tracker) {
            this.tracker = tracker;
        }

        @Override
        public void afterSingletonsInstantiated() {
            tracker.mark("afterSingletons");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public Tracker tracker() {
            return new Tracker();
        }

        @Bean(initMethod = "initialize", destroyMethod = "shutdown")
        public EagerCache eagerCache(Tracker tracker) {
            return new EagerCache(tracker);
        }

        @Bean
        @Lazy
        public RequiredIndex requiredIndex(Tracker tracker) {
            return new RequiredIndex(tracker);
        }

        @Bean
        @Lazy
        public OptionalGateway optionalGateway(Tracker tracker) {
            return new OptionalGateway(tracker);
        }

        @Bean
        public EagerConsumer eagerConsumer(
                RequiredIndex index, EagerCache cache) {
            return new EagerConsumer(index, cache);
        }

        @Bean
        public StartupCheck startupCheck(Tracker tracker) {
            return new StartupCheck(tracker);
        }
    }

    public static void main(String[] args) {
        Tracker tracker;

        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            tracker = context.getBean(Tracker.class);

            System.out.println("eager.constructed=" +
                    tracker.has("eager.constructed"));
            System.out.println("eager.initialized=" +
                    tracker.has("eager.initialized"));
            System.out.println("requiredLazy.created=" +
                    tracker.has("required.created"));
            System.out.println("optionalLazy.createdBefore=" +
                    tracker.has("optional.created"));
            System.out.println("afterSingletons.called=" +
                    tracker.has("afterSingletons"));
            System.out.println("consumer.dependencies=" +
                    context.getBean(EagerConsumer.class).hasDependencies());

            OptionalGateway first =
                    context.getBean(OptionalGateway.class);
            OptionalGateway second =
                    context.getBean(OptionalGateway.class);

            System.out.println("optionalLazy.createdAfter=" +
                    tracker.has("optional.created"));
            System.out.println("optionalLazy.sameSingleton=" +
                    (first == second));
        }

        System.out.println("eager.destroyedAfterClose=" +
                tracker.has("eager.destroyed"));
    }
}
```

### 12.4. Lệnh chạy

Ở thư mục chứa `pom.xml`:

```bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.EagerSingletonDemo
```

### 12.5. Output dự kiến chính xác

Đây là **các dòng do chương trình in**; log của Maven và các framework components (nếu có) không tính vào stdout ứng dụng:

```text
eager.constructed=true
eager.initialized=true
requiredLazy.created=true
optionalLazy.createdBefore=false
afterSingletons.called=true
consumer.dependencies=true
optionalLazy.createdAfter=true
optionalLazy.sameSingleton=true
eager.destroyedAfterClose=true
```

### 12.6. Giải thích từng nhóm dòng

**`eager.constructed=true`:** `eagerCache` là singleton không lazy. Spring tạo nó trong quá trình refresh, nên constructor đã đánh dấu `eager.constructed` trước khi code trong `main` kiểm tra.

**`eager.initialized=true`:** `@Bean(initMethod = "initialize")` bảo Spring gọi `EagerCache.initialize()` sau khi tạo bean và chuẩn bị dependency. Do đó lúc constructor ApplicationContext trả về, bean đã hoàn tất local init callback.

**`requiredLazy.created=true`:** `requiredIndex` có `@Lazy`, nhưng `eagerConsumer` là eager singleton cần `RequiredIndex` qua constructor. Container buộc phải tạo `requiredIndex` để có thể hoàn tất `eagerConsumer`.

**`optionalLazy.createdBefore=false`:** `optionalGateway` cũng có `@Lazy` nhưng không bean eager nào yêu cầu nó. Vì vậy ngay sau refresh trong ví dụ, object này chưa được tạo.

**`afterSingletons.called=true`:** `startupCheck` là eager singleton thực thi `SmartInitializingSingleton`. Spring gọi callback sau khi hoàn tất pre-instantiation các regular non-lazy singleton beans, nên marker đã được ghi.

**`consumer.dependencies=true`:** `EagerConsumer` nhận đủ `RequiredIndex` và `EagerCache` qua parameters của `@Bean` method. Cả hai references không null.

**`optionalLazy.createdAfter=true`:** Khi `main` gọi `context.getBean(OptionalGateway.class)`, Spring tạo bean lazy còn thiếu. Constructor ghi dấu mới vào Tracker.

**`optionalLazy.sameSingleton=true`:** Bean lazy sau khi tạo vẫn là singleton. Lấy hai lần trong cùng context trả cùng reference.

**`eager.destroyedAfterClose=true`:** Kết thúc `try-with-resources` gọi `ApplicationContext.close()`, kích hoạt `@Bean(destroyMethod = "shutdown")` của `eagerCache`. Marker được đọc qua Java reference `tracker` vẫn còn trong local variable sau khi context đóng, chỉ để chứng minh lifecycle callback; không nên tiếp tục sử dụng managed bean phục vụ nghiệp vụ sau khi container đã close.

### 12.7. Những điểm làm ví dụ đáng tin cậy

- Mọi bean classes đều là `public static` nested classes; Spring có thể tạo chúng từ Java `@Bean` methods mà không cần outer object.
- Không có static mutable global counter; các trạng thái thuộc `Tracker` bean của context hiện tại.
- Không dùng thứ tự duyệt `HashSet` để in kết quả, chỉ dùng membership checks. Vì vậy thứ tự bean construction nội bộ không ảnh hưởng thứ tự stdout.
- Không gọi `getBean(OptionalGateway.class)` **trước** khi in `optionalLazy.createdBefore`.
- `@Configuration(proxyBeanMethods=false)` an toàn vì dependencies được truyền bằng **factory method parameters**, không gọi trực tiếp một `@Bean` method khác.
- Không dùng Spring Boot, `@SpringBootApplication` hoặc web server; `spring-context` đủ cho code này.
- Dùng `try-with-resources` để thể hiện cleanup của managed singleton.

## 13. Thử nghiệm đơn lẻ với BeanFactory thuần

Để hiểu sự khác biệt **registration** và **pre-instantiation**, sau đây là project nhỏ chạy với dependency Maven ở mục 12. Tạo file Java thứ hai `src/main/java/demo/BeanFactoryPreInstantiationDemo.java`:

```java
package demo;

import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;

public class BeanFactoryPreInstantiationDemo {

    public static final class Tool {
        public Tool() {
        }
    }

    public static void main(String[] args) {
        DefaultListableBeanFactory factory =
                new DefaultListableBeanFactory();

        factory.registerBeanDefinition(
                "tool", new RootBeanDefinition(Tool.class));

        System.out.println("definition=" +
                factory.containsBeanDefinition("tool"));
        System.out.println("before=" +
                factory.containsSingleton("tool"));

        factory.preInstantiateSingletons();

        System.out.println("after=" +
                factory.containsSingleton("tool"));

        factory.destroySingletons();

        System.out.println("afterDestroy=" +
                factory.containsSingleton("tool"));
    }
}
```

Chạy:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.BeanFactoryPreInstantiationDemo
```

Output:

```text
definition=true
before=false
after=true
afterDestroy=false
```

**Giải thích:**

1. `registerBeanDefinition` đăng ký metadata, nên `definition=true`.
2. Chưa yêu cầu instance và chưa chạy pre-instantiation, nên `before=false`.
3. `preInstantiateSingletons()` kích hoạt tạo singleton non-lazy `tool`, nên `after=true`.
4. `destroySingletons()` giải phóng singleton instances trong registry ở ví dụ BeanFactory thấp cấp này, nên `afterDestroy=false`.

**Giới hạn:** Demo BeanFactory này minh họa registration và singleton cache, không tái hiện toàn bộ lifecycle `ApplicationContext.refresh()`. Không nên thay ApplicationContext trong ứng dụng thông thường chỉ để tự kiểm soát thời điểm khởi tạo nếu bạn vẫn cần full annotations, events và lifecycle infrastructure.

## 14. Cách cấu hình trong Spring XML

Mặc dù ví dụ chính dùng Java configuration, cơ chế eager/lazy cũng áp dụng cho bean definitions đọc từ XML.

### 14.1. Singleton eager mặc định

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="catalog" class="example.CatalogService"/>

</beans>
```

Giả sử `example.CatalogService` có constructor hợp lệ và classpath đầy đủ, bean singleton này sẽ được pre-instantiate trong `ClassPathXmlApplicationContext` theo mặc định.

### 14.2. Lazy trên một bean

```xml
<bean id="optionalClient"
      class="example.OptionalClient"
      lazy-init="true"/>
```

Bean này không bị pre-instantiate mặc định **nếu không có eager dependency khác cần nó**.

### 14.3. Default lazy cho nhóm beans

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">
    <bean id="clientA" class="example.ClientA"/>
    <bean id="clientB" class="example.ClientB"/>
</beans>
```

Snippet lược bớt schema để tập trung vào thuộc tính. Một BeanFactory đọc XML có thể áp dụng default laziness cho definitions trong scope đó. Cần nhớ infrastructure beans và eager dependency requirements có thể khiến một số objects vẫn được tạo lúc startup.

### 14.4. Lazy bean bị reference từ eager bean

```xml
<beans xmlns="http://www.springframework.org/schema/beans">
    <bean id="lazyRules"
          class="example.PriceRules"
          lazy-init="true"/>

    <bean id="checkoutService"
          class="example.CheckoutService">
        <constructor-arg ref="lazyRules"/>
    </bean>
</beans>
```

Theo quy tắc dependency resolution, `checkoutService` mặc định eager, nên `lazyRules` được tạo đủ sớm để có thể truyền vào constructor. Đây là **XML tương đương** với trường hợp `@Bean @Lazy` + eager consumer trong Java.

### 14.5. Scope prototype trong XML

```xml
<bean id="jobWorker"
      class="example.JobWorker"
      scope="prototype"/>
```

Không có khái niệm pre-instantiating toàn bộ prototype beans theo một lượt vì số instances phụ thuộc yêu cầu của caller.

## 15. @DependsOn và điều khiển thứ tự

`@DependsOn`/XML `depends-on` có thể làm BeanFactory **khởi tạo một bean trước một bean khác** khi có ordering requirement ngoài constructor/property dependency.

Java:

```java
@Bean
@DependsOn("schemaValidator")
ReportService reportService() {
    return new ReportService();
}
```

XML:

```xml
<bean id="reportService"
      class="example.ReportService"
      depends-on="schemaValidator"/>
```

Đây là các đoạn minh họa cần định nghĩa `schemaValidator` và class `ReportService`. Nếu `reportService` được tạo, Spring bảo đảm bean `schemaValidator` được tạo trước theo dependency ordering mà metadata yêu cầu.

### Quan hệ đã có qua constructor không cần @DependsOn nữa

```java
@Bean
ReportService reportService(ReportRepository repository) {
    return new ReportService(repository);
}
```

Ở đây BeanFactory phải có `ReportRepository` để gọi method factory tạo `ReportService`. Vì vậy thông thường không cần thêm `@DependsOn("reportRepository")` chỉ để lặp lại dependency đã rõ.

### @DependsOn không bảo đảm application readiness

`@DependsOn` không phải job scheduler hay business orchestration. Nó không có transaction, retry, readiness, idempotency hoặc phân tán coordination mặc định.

Nếu `schemaValidator` chỉ tồn tại để chạy nghiệp vụ khi constructor gọi, hãy xem liệu đó có phải tác vụ cần startup coordinator/hạ tầng migration riêng không. Không gắn side effects nặng vào constructors chỉ để ép ordering.

### Phụ thuộc vòng

Nếu A `@DependsOn("b")` và B `@DependsOn("a")`, bạn đã khai báo thứ tự bất khả giải. Spring không thể vừa tạo A trước B vừa B trước A. Tương tự, constructor dependencies A→B→A phải sửa ở dependency graph, không thể chữa bằng đảo thứ tự bean definitions.

## 16. Pre-instantiation và BeanPostProcessor/AOP

Trong `ApplicationContext`, Spring đăng ký nhiều loại bean infrastructure **trước** khi tạo các regular non-lazy singleton beans. `BeanPostProcessor` có thể tham gia giai đoạn bean initialization và wrap target bằng proxy, ví dụ để hỗ trợ một số AOP features.

Điều này tạo ra các quy tắc quan trọng:

- Đừng gọi `getBean` tùy tiện trong một `BeanFactoryPostProcessor` để cố “làm nóng” các business services; nó có thể khiến bean được tạo **quá sớm** trước khi các BeanPostProcessors cần thiết được đăng ký.
- Những `BeanFactoryPostProcessor`/`BeanPostProcessor` definitions có thể cần được tạo rất sớm để container hoạt động, không đơn giản tuân theo mọi quy tắc “eager regular singleton” như application service thông thường.
- Bean khởi tạo sớm ngoài chu kỳ post-processing có thể không được AOP proxy như kỳ vọng và Spring có thể đưa ra diagnostic về eligibility.
- Nếu `@Configuration` định nghĩa một `BeanFactoryPostProcessor` qua non-static `@Bean`, framework có thể phải instantiate configuration class sớm. Khi phù hợp, khai báo `static @Bean` cho post-processor để tránh early config instance creation.
- Khi đọc log, hãy phân biệt target object, proxy object và bean definition; không mặc định mọi constructor log chứng minh bean sẽ được caller nhìn thấy cùng raw reference.

### Có thể dựa vào thứ tự constructor của các beans không?

**Không nên.** Với những bean độc lập, thứ tự nội bộ có thể thay đổi theo registration, dependencies, version và tùy chọn bootstrap. Spring bảo đảm **dependency ordering cần thiết**, không bảo đảm thứ tự business initialization nếu bạn chỉ dựa vào dòng log “bean A xuất hiện trước bean B”.

Muốn có ordering có ý nghĩa, mô tả dependency hoặc dùng lifecycle orchestration phù hợp. Ví dụ chính cố tình kiểm tra **trạng thái tại một mốc ổn định** thay vì đưa stdout phụ thuộc thứ tự tạo beans.

## 17. FactoryBean trong giai đoạn pre-instantiation

`FactoryBean<T>` là một extension point Spring có thể tạo **product bean**. Nó khác `@Bean` factory method và khác GoF factory class thông thường.

Với BeanFactory, khi tên bean ứng với một `FactoryBean`:

- `getBean("name")` thường trả **product** của factory.
- `getBean("&name")` (dấu `&`) trả chính **FactoryBean object**.
- `FactoryBean.isSingleton()` xác định product do factory cung cấp có singleton semantics hay không.
- Việc pre-instantiation có logic riêng để tạo/check `FactoryBean` và trong các trường hợp được đánh dấu eager-init, có thể khởi tạo product sớm theo hợp đồng `SmartFactoryBean`/container.

Không nên kết luận “mọi FactoryBean product đều eager” hoặc “mọi FactoryBean product đều lazy”. Cần xem:

1. Definition của factory itself có non-lazy singleton hay không.
2. Product có singleton semantics không.
3. Factory có hỗ trợ eager product initialization hay không.
4. Dependency graph có yêu cầu product sớm hay không.
5. Type inspection có buộc Spring initialize factory nhằm xác định type không.

### Cẩn trọng với getBeansOfType và allowEagerInit

Một số overloads của `getBeanNamesForType`/`getBeansOfType` có tham số `allowEagerInit`. Với `FactoryBean`, type introspection đôi khi đòi initialize factory để biết `getObjectType()`. Vì vậy một phép “khảo sát beans theo type” không phải lúc nào cũng hoàn toàn không có side effects.

Nếu mục tiêu chỉ là kiểm tra một singleton đã tồn tại tại một thời điểm, `containsSingleton(beanName)` thích hợp hơn việc dùng `getBean` hoặc cố duyệt mọi beans.

## 18. Pre-instantiation và vòng phụ thuộc

Constructor cycle:

```java
final class Alpha {
    Alpha(Beta beta) {
    }
}

final class Beta {
    Beta(Alpha alpha) {
    }
}
```

Nếu cả hai là singleton eager với constructors yêu cầu nhau, BeanFactory không thể hoàn thành khởi tạo:

```text
alpha -> beta -> alpha (currently in creation)
```

Spring có thể ném `BeanCurrentlyInCreationException` hoặc exception chain `UnsatisfiedDependencyException`/`BeanCreationException`, tùy giai đoạn gây lỗi.

### Fail-fast là lợi ích, không phải nhược điểm

Nếu dependency graph thực sự sai, lỗi ở startup giúp bạn phát hiện trước khi người dùng thao tác. Chuyển tất cả beans sang lazy có thể chỉ đẩy lỗi tới lần đầu API được gọi, khiến runtime failures khó đoán hơn.

### Setter/field cycles cũng nên sửa thiết kế

Một số vòng setter/field injection trong Spring có thể được xử lý bằng early singleton references nếu cơ chế được phép; nhưng code có thể thấy incomplete state hoặc proxy semantics khó lường. Constructor cycle thường vẫn không giải quyết được.

**Giải pháp bền vững** là chỉnh đồ thị dependency:

```text
Trước:
OrderService <--> PaymentService

Sau:
CheckoutCoordinator --> OrderService
                   \-> PaymentService
```

Hoặc trích abstraction/policy chung để services không phải inject lẫn nhau. Không bật cờ circular-reference support chỉ để bỏ qua thiết kế thiếu rõ ràng.

## 19. Startup nhanh hơn bằng lazy có phải luôn tốt?

Không. Lazy giúp trì hoãn **chi phí tạo instance**, chứ không xóa chi phí đó.

Nếu bean chậm vì kết nối remote service hoặc tải dữ liệu lớn, chuyển bean sang lazy có thể:

- Làm startup nhanh hơn.
- Làm **request đầu tiên** chậm hoặc thất bại.
- Dồn việc kết nối vào một thời điểm chịu áp lực traffic.
- Che lỗi cấu hình cho đến khi tính năng hiếm khi dùng được kích hoạt.
- Khi nhiều threads gọi cùng lúc, khiến concurrent callers chờ initialization.

### Khi nên dùng lazy

- Tính năng ít dùng.
- Một bean có chi phí dựng cao nhưng nhiều lượt chạy ứng dụng không cần đến.
- Optional integration chỉ được gọi khi người dùng bật feature.
- Tooling/admin bean không thuộc đường phục vụ request quan trọng.
- Muốn defer construction có chủ đích, với monitoring và timeout.

### Khi nên giữ eager

- Service cốt lõi được dùng ngay sau startup.
- Cần phát hiện lỗi cấu hình trước khi sẵn sàng phục vụ.
- Dependency phải được xác thực sớm vì ảnh hưởng tính an toàn của application.
- Cần hoàn tất resource initialization trước khi chấp nhận traffic.

**Quy tắc thực dụng:** Ưu tiên sửa nguyên nhân làm construction nặng trước. Nếu constructor tải hàng triệu records, vấn đề có thể là business initialization đặt sai lifecycle; `@Lazy` chỉ dời khối lượng việc sang request khác.

## 20. Startup side effects và tính idempotent

Đặt lệnh nghiệp vụ trong constructor của eager singleton:

```java
// Phản ví dụ; các kiểu ứng dụng cần được định nghĩa riêng.
final class WelcomeMailService {
    WelcomeMailService(MailGateway gateway) {
        gateway.sendWelcomeToAllUsers();
    }
}
```

vô tình khiến mỗi lần ApplicationContext pre-instantiate bean là một lần chạy mail workflow. Nhiều contexts trong tests, restart ứng dụng, nhiều replicas hoặc staging environment có thể làm nghiệp vụ chạy lặp.

Tách ra:

- Constructor: lưu dependency và validate invariant.
- Bean init callback: chuẩn bị local resource/state nhỏ, theo hợp đồng bean.
- Startup coordinator: quyết định có gọi seed/check/migration hay không ở lifecycle phù hợp.
- Service method: chứa use case nghiệp vụ.
- Storage/transaction: bảo đảm idempotency nếu tác vụ có thể chạy lặp.

`SmartInitializingSingleton` có thể làm điểm kích hoạt một bước hậu khởi tạo, nhưng **không** tự đảm bảo exactly-once toàn cluster. Với DB seed cần unique constraints/UPSERT hoặc cơ chế coordination phù hợp.

## 21. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Giải thích khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| Constructor chạy dù chưa `getBean()` | Eager singleton pre-instantiation ở `ApplicationContext.refresh()` | Xem scope và `@Lazy`/XML `lazy-init` |
| Bean `@Lazy` vẫn tạo khi startup | Là dependency của eager singleton | Vẽ dependency graph; xem injection point |
| `containsBeanDefinition` trả true, `containsSingleton` false | Có metadata nhưng instance chưa được tạo | Đúng với lazy hoặc BeanFactory chưa pre-instantiate |
| Prototype xuất hiện trong startup log | Eager singleton đã yêu cầu prototype làm dependency | Xem factory parameters/constructor injection |
| Bean bị tạo hai lần dù scope singleton | Có hai contexts, hai bean names, direct `new` hoặc factory method call ngoài container | Kiểm tra registry/identity/scope |
| Test từ IDE chạy được, startup prod lỗi | Different profiles/config/resource dependencies; eager validation lộ sai | Chạy integration test với config prod tương ứng |
| Startup quá chậm | Eager beans nhiều hoặc init callbacks làm I/O nặng | Profile startup, xem constructors và init methods |
| Bean lazy lỗi sau request đầu | Dependency/config chỉ được kiểm tra khi cần | Test feature path và readiness/fail-fast policy |
| `BeanCurrentlyInCreationException` | Circular dependency hoặc early bean access | Vẽ bean graph; bỏ vòng constructors |
| `@PostConstruct` gây treo startup | Callback init làm tác vụ nặng/call bean ngoài | Dời sang lifecycle coordinator phù hợp |
| `SmartInitializingSingleton` callback không chạy | Coordinator bean lazy, prototype, hoặc không được đăng ký vào BeanFactory | Đảm bảo eager managed singleton |
| Callback chạy nhưng external system chưa sẵn | Hook chỉ bảo đảm regular singleton pre-instantiation | Thiết kế explicit dependency checks và readiness |
| `@Transactional` không áp dụng ở init | Callback trước proxy interception/self-invocation | Gọi service qua managed proxy ở phase phù hợp |
| `@DependsOn` thêm vòng | Ordering A→B và B→A | Xóa vòng dependency |
| BeanPostProcessor không xử lý một bean | Bean bị tạo quá sớm trong post-processor/bootstrap | Kiểm tra early getBean/configuration static @Bean |
| FactoryBean được initialize khi type lookup | `allowEagerInit` hoặc product type introspection | Dùng API inspection đúng nhu cầu |
| `getBeanNamesForType` xuất hiện trước bean creation | Có thể đọc metadata type, không phải chứng minh instance đã có | Dùng `containsSingleton`/constructor instrumentation khi cần |
| Shutdown không cleanup resource | Không đóng ApplicationContext, thiếu destroy callback, hoặc object ngoài container | Dùng try-with-resources và lifecycle cleanup |
| Spring Boot start nhanh nhưng endpoint đầu chậm | Lazy global / deferred resource startup | Đánh giá startup vs first-use latency |

### Debug theo trình tự

1. Xác định bean name và scope.
2. Kiểm tra bean definition có `lazyInit` flag hay không.
3. Xem bean có được yêu cầu bởi một eager singleton khác không.
4. Kiểm tra loại context và thời điểm `refresh()`.
5. Xem constructor/factory method, `@PostConstruct`, custom init callbacks đang làm gì.
6. Xác định lỗi ở definition registration, bean instantiation hay lifecycle callback.
7. Kiểm tra bean đã nằm trong singleton cache chưa mà không làm phát sinh creation.
8. Xem các factories/post-processors có khởi tạo bean sớm ngoài ý định hay không.
9. Kiểm tra profile, properties, conditional beans và classpath thực.
10. Sửa nguyên nhân, sau đó chạy một context startup test và một first-use test cho beans lazy.

## 22. Testing: chứng minh eager và lazy không gây side effect ngoài ý muốn

### Test eager đã được khởi tạo trước client code

Trong ví dụ mục 12, bạn có thể thêm assert:

```java
if (!tracker.has("eager.constructed")) {
    throw new AssertionError("Eager singleton was not created");
}
if (!tracker.has("eager.initialized")) {
    throw new AssertionError("Eager init method did not run");
}
```

Đặt trong body của `try` sau khi tạo `context` và lấy `tracker`; assertions không in thêm khi pass.

### Test lazy chưa tạo trước khi được yêu cầu

```java
if (tracker.has("optional.created")) {
    throw new AssertionError("Optional lazy bean created too early");
}
```

Không gọi `context.getBean(OptionalGateway.class)` trước assertion này; nếu gọi, test đã thay đổi điều kiện đang đo.

### Test lazy bị kéo lên sớm bởi eager consumer

```java
if (!tracker.has("required.created")) {
    throw new AssertionError("Required lazy dependency was not resolved");
}
```

Bởi `EagerConsumer` là eager singleton bắt buộc nhận `RequiredIndex`, marker đó phải được ghi sau refresh.

### Test singleton identity sau first-use

```java
OptionalGateway first = context.getBean(OptionalGateway.class);
OptionalGateway second = context.getBean(OptionalGateway.class);

if (first != second) {
    throw new AssertionError("Lazy singleton identity is broken");
}
```

Đây là check identity **trong cùng một context**, không phải qua hai contexts độc lập.

### Test shutdown

Sau khi close context trong ví dụ, `tracker.has("eager.destroyed")` phải là true. Không tiếp tục gọi business methods trên beans đã bị Spring hủy, dù Java object reference còn tồn tại.

### Tránh test phụ thuộc thứ tự tạo beans không có hợp đồng

Không viết assertions kiểu “constructor A nhất định được gọi ngay trước constructor B” trừ khi A↔B có dependency/ordering contract rõ. Kiểm tra các mốc **trước refresh / sau refresh / sau first use / sau close** đáng tin và ít flaky hơn.

## 23. So sánh với Spring Boot

Spring Boot dùng Spring Framework Core Container bên dưới, nên vẫn có eager/lazy, singleton scopes và dependency-driven creation. Ngoài ra Boot có một số convenience settings như:

```properties
spring.main.lazy-initialization=true
```

Đây là **Spring Boot property**, không phải Java annotation hoặc generic property mà plain `AnnotationConfigApplicationContext` tự đọc để bật global laziness.

Boot global lazy initialization có thể cải thiện startup times trong một số ứng dụng nhưng trì hoãn lỗi cấu hình đến lần dùng đầu; đặc biệt không bảo đảm mọi infrastructure beans trở nên lazy.

Phân biệt các lifecycle hooks:

| Mốc | Thuộc tầng | Ý nghĩa chính |
| --- | --- | --- |
| `preInstantiateSingletons()` | Spring BeanFactory | Dựng regular non-lazy singletons |
| `SmartInitializingSingleton` | Spring Beans | Callback cuối pha pre-instantiation |
| `ContextRefreshedEvent` | Spring Context | Context đã initialized/refreshed |
| `SmartLifecycle.start()` | Spring Context | Thành phần có vòng đời được start qua lifecycle processor |
| `ApplicationRunner`/`CommandLineRunner` | Spring Boot | Startup runners do Boot gọi |
| `ApplicationReadyEvent` | Spring Boot | Tín hiệu Boot đã hoàn thành startup sequence thường dùng |
| Readiness/liveness probes | Spring Boot/operations | Quan sát trạng thái vận hành, không thay thế dependency graph |

**Không đồng nhất những mốc này** thành “mọi external service đã thành công”. Readiness thực tế cần kiểm tra business-critical dependencies phù hợp; pre-instantiation một object client không nhất thiết đã chứng minh network endpoint đang healthy.

## 24. Câu hỏi thường gặp

### Có phải singleton chỉ tạo một lần cho toàn JVM?

Không. Spring singleton mặc định là **mỗi bean definition trong mỗi container**. Hai ApplicationContexts có thể có hai instances cho cùng một class/bean name.

### Singleton eager có nghĩa phải gọi getBean() một lần?

Không. ApplicationContext thường pre-instantiate non-lazy singletons trong refresh; caller không phải lấy từng bean thủ công.

### @Lazy có nghĩa prototype?

Không. Lazy nói về thời điểm; prototype nói về số instances. Lazy singleton sau first-use vẫn trả cùng reference.

### Tại sao @Lazy vẫn chạy constructor lúc startup?

Bean đó có thể là dependency bắt buộc của eager singleton, hoặc bị một cơ chế startup khác yêu cầu. Kiểm tra full dependency graph và early lookups.

### Context refresh có tạo mọi bean?

Không. Prototype, lazy singleton không bị yêu cầu và một số scoped objects không thuộc bulk singleton pre-instantiation.

### Pre-instantiation có phải là constructor order theo source code?

Không nên dựa vào source order hay tên methods. Dependencies và infrastructure processing mới quyết định thứ tự cần thiết; những independent beans không nên có behavior phụ thuộc thứ tự.

### Có thể bỏ eager để che thiếu dependency không?

Không nên. Nếu dependency là bắt buộc, chuyển bean sang lazy có thể chỉ dời lỗi tới lúc phục vụ request, làm reliability tệ hơn. Hãy sửa cấu hình hoặc xác định điều kiện feature availability.

### @PostConstruct chạy khi nào so với SmartInitializingSingleton?

`@PostConstruct` là callback **cục bộ của từng bean** khi bean đang được khởi tạo; `SmartInitializingSingleton` chạy **sau giai đoạn pre-instantiation của các regular non-lazy singleton beans**.

### Một lazy singleton vừa tạo sau refresh có được gọi afterSingletonsInstantiated không?

Theo contract, **không**. Callback đó dành cho thời điểm kết thúc singleton pre-instantiation, không phải mỗi lần Spring tạo bất kỳ singleton mới về sau.

### Nếu getBeanNamesForType không lấy instance thì an toàn tuyệt đối?

Không. Một số type introspection, đặc biệt với `FactoryBean` và `allowEagerInit`, có thể làm factory được tạo để biết product type. Chọn API phù hợp nếu muốn quan sát mà không thay đổi trạng thái.

### Spring có đảm bảo singleton thread-safe?

Spring cung cấp safe publication của managed singleton initialization state, nhưng **không biến mọi mutable business state trong singleton thành thread-safe**. Nếu bean giữ counters, maps hoặc state thay đổi sau startup, bạn vẫn cần synchronization/concurrent data structures phù hợp.

### Một bean @Bean có tự được gọi initMethod nếu mình new trực tiếp từ Java?

Không. `new` gọi constructor Java, nhưng các lifecycle callbacks do Spring quản lý chỉ được gọi tự động khi object được BeanFactory tạo/quản lý theo definition có metadata phù hợp.

### @DependsOn có thay constructor dependency không?

Không. `@DependsOn` nói về ordering, còn constructor parameter injection cung cấp collaborator instance. Với dependency qua parameter đã có, thường không cần `@DependsOn` nữa.

## 25. Bài tập thực hành có đáp án

### Bài 1 — Định nghĩa và instance

Bạn đăng ký bean definition tên `mailClient` vào `DefaultListableBeanFactory` nhưng chưa gọi `getBean` hay `preInstantiateSingletons`. Có chắc instance đã tồn tại?

**Đáp án:** Không. Registration thêm metadata; chưa bắt buộc instantiate. Kiểm tra `containsBeanDefinition` và `containsSingleton` để phân biệt.

### Bài 2 — Eager singleton mặc định

Một `@Bean Repository repository()` có scope singleton và không `@Lazy`. Tạo `AnnotationConfigApplicationContext(AppConfig.class)` thành công rồi mới gọi `getBean(Repository.class)`. Constructor Repository thường chạy ở mốc nào?

**Đáp án:** Trong `refresh()` của ApplicationContext, trước khi context constructor trả về. `getBean` sau đó lấy managed singleton đã tạo.

### Bài 3 — @Lazy riêng lẻ

Bean `mailGateway` có `@Lazy` và không eager bean nào cần nó. Sau refresh, bean đã nhất thiết được tạo chưa?

**Đáp án:** Không. Thông thường nó còn deferred cho tới lần đầu được request.

### Bài 4 — Lazy bị dependency kéo lên

`A` eager singleton có constructor `A(B b)`; `B` singleton nhưng `@Lazy`. Sau refresh, `B` có thể đã được tạo không?

**Đáp án:** Có. Spring phải cung cấp `B` để tạo eager `A`, trừ khi injection được thiết kế để trì hoãn bằng proxy/provider theo hợp đồng riêng.

### Bài 5 — Prototype

`Worker` prototype là constructor dependency của eager `Scheduler` singleton. Có bao nhiêu `Worker` được tạo cho Scheduler trong constructor?

**Đáp án:** Một instance được resolve để inject tại thời điểm Scheduler được tạo, với constructor một parameter như mô tả. Không phải Spring pre-instantiate mọi prototype trên classpath.

### Bài 6 — SmartInitializingSingleton

Callback `afterSingletonsInstantiated` có bảo đảm lazy singleton chưa bao giờ được tạo không?

**Đáp án:** Không. Một lazy definition có thể đã bị eager dependency yêu cầu. Hook bảo đảm những regular non-lazy singleton beans đã qua pre-instantiation, chứ không đảm bảo lazy beans đều vắng.

### Bài 7 — Lazy coordinator

Một bean implement `SmartInitializingSingleton` nhưng được `@Lazy` và không ai cần nó khi refresh. Callback có tự chạy lúc bootstrap không?

**Đáp án:** Không. Theo Javadoc, callback không chạy cho lazy singleton chỉ được tạo sau khi BeanFactory bootstrap kết thúc.

### Bài 8 — Quan sát trạng thái

Bạn muốn biết bean đã có instance chưa mà không làm nó bị tạo. Chọn `getBean("x")` hay `containsSingleton("x")`?

**Đáp án:** `containsSingleton("x")` kiểm tra cache mà không yêu cầu tạo. `getBean("x")` có thể kích hoạt bean creation.

### Bài 9 — Thứ tự constructor

Hai singleton A, B độc lập. Có nên assert A constructor luôn chạy trước B chỉ vì `@Bean a()` xuất hiện trên source trước `@Bean b()`?

**Đáp án:** Không. Chỉ kiểm tra thứ tự khi có explicit dependency/lifecycle contract; tránh phụ thuộc thứ tự implementation.

### Bài 10 — Startup chậm

Một eager singleton constructor gọi API tải 100 MB dữ liệu. Bật `@Lazy` có phải sửa tận gốc?

**Đáp án:** Không. Nó dời chi phí/khả năng lỗi sang first use. Cần xem có phải business/bootstrap workflow đặt sai trong constructor và chọn cơ chế startup/async/readiness phù hợp.

### Bài 11 — BeanFactory thuần

Với `DefaultListableBeanFactory`, API nào giúp chủ động khởi tạo các singleton non-lazy đã đăng ký?

**Đáp án:** `preInstantiateSingletons()` trên `ConfigurableListableBeanFactory`/implementation tương ứng.

### Bài 12 — Scope và context

Hai ApplicationContexts khác nhau đều khai báo singleton bean tên `reportService` cùng class. Có bắt buộc chúng là cùng object reference không?

**Đáp án:** Không. Singleton scope là theo bean definition trong từng container.

### Bài 13 — BeanFactory vs ApplicationContext

Tại sao chương trình BeanFactory tự đăng ký definition nhưng chưa có singleton instance, trong khi ApplicationContext tạo singleton trước lời gọi `getBean`?

**Đáp án:** ApplicationContext `refresh()` thường điều phối pre-instantiation tự động; registration ở BeanFactory thấp cấp không tương đương full refresh.

### Bài 14 — Trạng thái sau close

Sau khi `try (ApplicationContext ...)` kết thúc, một Java local reference tới singleton vẫn tồn tại. Có nên dùng reference đó làm bean hoạt động bình thường?

**Đáp án:** Không. Container đã close/destroy callbacks có thể đã chạy; trạng thái runtime và resource ownership không còn được bảo đảm. Dùng reference sau close trong ví dụ chỉ để quan sát marker học thuật.

### Bài 15 — @DependsOn và vòng

`@DependsOn("b")` trên A, `@DependsOn("a")` trên B. Eager initialization có thể tuân thủ cả hai không?

**Đáp án:** Không. Đây là ordering cycle. Phải sửa dependency direction.

### Bài 16 — FactoryBean

`FactoryBean` singleton được pre-instantiated có nhất thiết đồng nghĩa product được tạo sớm không?

**Đáp án:** Không. Cần phân biệt factory object, product singleton flag, `SmartFactoryBean` eager-init contract, type introspection và dependency demand.

### Bài 17 — Spring Boot global lazy

Property `spring.main.lazy-initialization=true` có tự hoạt động trong chương trình plain Spring `new AnnotationConfigApplicationContext(AppConfig.class)` không?

**Đáp án:** Không. Đây là cấu hình Spring Boot, không phải property universal được plain ApplicationContext tự đọc để bật global laziness.

### Bài 18 — Dự đoán output

Trong ví dụ mục 12, vì sao `requiredLazy.created=true` nhưng `optionalLazy.createdBefore=false`?

**Đáp án:** Cả hai bean definitions là lazy, nhưng `EagerConsumer` eager bắt buộc cần `RequiredIndex`; không eager bean nào cần `OptionalGateway` trước khi main gọi nó.

## 26. Checklist áp dụng vào dự án

- [ ] Phân biệt **bean definition đã đăng ký** và **bean instance đã được tạo**.
- [ ] Hiểu singleton là per-bean, per-container, không mặc nhiên là per-JVM.
- [ ] Biết `ApplicationContext.refresh()` pre-instantiate regular non-lazy singletons.
- [ ] Dùng `@Lazy` hoặc XML `lazy-init` theo yêu cầu first-use, không dùng để giấu lỗi.
- [ ] Kiểm tra eager singleton nào phụ thuộc vào lazy singleton.
- [ ] Không kỳ vọng prototype được bulk pre-instantiated.
- [ ] Nếu singleton cần prototype mới theo từng job, sử dụng provider/factory phù hợp.
- [ ] Constructor và bean-local init callbacks nhẹ, deterministic và có cleanup.
- [ ] Không chạy business side effects không idempotent chỉ vì eager bean được tạo.
- [ ] Biết đúng ý nghĩa `SmartInitializingSingleton` và giới hạn của lazy beans.
- [ ] Tách startup readiness, refresh event và Boot application ready khỏi singleton pre-instantiation.
- [ ] Không khởi tạo business beans quá sớm từ BeanFactoryPostProcessor.
- [ ] FactoryBean type queries/eager semantics được cân nhắc nếu ứng dụng dùng chúng.
- [ ] Không dựa vào thứ tự các constructors độc lập cho business ordering.
- [ ] Không tự động bật circular references để xử lý dependency design sai.
- [ ] Integration tests kiểm tra trạng thái **sau refresh**, **sau first use** và **sau close**.
- [ ] Không dùng `getBean` để khảo sát xem lazy bean đã tạo hay chưa nếu mục tiêu là không tác động trạng thái.
- [ ] Có startup metrics/logs giúp phát hiện cost và root cause, không ghi secrets.
- [ ] Nếu dùng Boot global lazy, đã đánh giá startup speed đổi lấy first-request latency.
- [ ] Tài nguyên kết nối/threads có timeout và destruction/lifecycle phù hợp.

## Kết luận

**Eager singleton pre-instantiation** là hành vi mặc định quan trọng của `ApplicationContext`: Spring tạo và cấu hình các **regular singleton không lazy** ngay trong lúc refresh, phát hiện lỗi cấu hình trước khi application code bắt đầu gọi services. Điều đó khác với chỉ đăng ký `BeanDefinition` trong `DefaultListableBeanFactory`.

Cần nhớ bốn quy tắc:

1. **Singleton là identity/scope**, **eager/lazy là thời điểm**.
2. `@Lazy` không ngăn bean bị tạo sớm nếu **eager dependency** bắt buộc cần nó.
3. `preInstantiateSingletons()` hoàn tất giai đoạn bulk singleton creation và liên quan callback `SmartInitializingSingleton`, nhưng **không** có nghĩa tất cả prototype/lazy beans/external services đã sẵn sàng.
4. Constructor/init callbacks nên xử lý trách nhiệm **cục bộ của bean**, còn workflow nghiệp vụ và readiness phải có điểm kích hoạt/chính sách riêng.

Hãy đo trạng thái ở những mốc rõ ràng, tôn trọng dependency graph, viết tests cho startup và first-use, rồi chỉ dùng lazy khi việc trì hoãn thật sự phù hợp yêu cầu ứng dụng.

## Tài liệu chính thức của Spring

- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): `ApplicationContext` eager pre-instantiation, `@Lazy`/`lazy-init` và lazy dependencies của eager singletons.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton per-container/per-bean, prototype semantics.
- [Spring Framework 6.2 — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): lifecycle, init callbacks, `SmartInitializingSingleton` và `SmartLifecycle`.
- [Spring Framework 6.2 — ConfigurableListableBeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/ConfigurableListableBeanFactory.html): `preInstantiateSingletons()`.
- [Spring Framework 6.2 — SmartInitializingSingleton Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback sau regular singleton pre-instantiation và giới hạn đối với lazy beans.
- [Spring Framework 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): dependency ordering.
- [Spring Framework 6.2 — The IoC Container](https://docs.spring.io/spring-framework/reference/6.2/core/beans.html): BeanFactory, ApplicationContext và bean definitions.
