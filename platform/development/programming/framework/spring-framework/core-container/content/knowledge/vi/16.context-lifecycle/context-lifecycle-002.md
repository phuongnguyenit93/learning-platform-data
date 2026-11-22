# Vòng đời ApplicationContext: nạp định nghĩa, chạy post-processor và tạo singleton

## 1. Mục tiêu và ý nghĩa

Một Spring `ApplicationContext` không đơn giản “quét class rồi gọi constructor”. Trong lúc `refresh()`, container đi qua nhiều bước được thiết kế có thứ tự: **đọc và đăng ký bean definitions**, mở cơ hội cho những extension point chỉnh sửa metadata, **đăng ký các processor chạy trên instance**, cuối cùng **tạo các singleton không lazy** và công bố sự kiện context đã refresh.

Hiểu trình tự này giúp trả lời những câu hỏi thường gặp:

- Vì sao `BeanFactoryPostProcessor` thay đổi metadata trước khi bean được tạo?
- `BeanDefinitionRegistryPostProcessor` khác `BeanFactoryPostProcessor` ở quyền gì?
- Vì sao `BeanPostProcessor` được đăng ký trước lúc khởi tạo bean nghiệp vụ?
- Tại sao constructor, `@PostConstruct`, `afterPropertiesSet()`, custom init, `SmartInitializingSingleton` và `ContextRefreshedEvent` xuất hiện vào những thời điểm khác nhau?
- “Singleton được tạo lúc startup” có ngoại lệ nào với `@Lazy`, `prototype` và `FactoryBean`?
- Khi nào việc gọi `getBean()` sớm làm phá vỡ kỳ vọng post-processing?

Bài học tập trung vào **Core Container của Spring Framework 6.2**, áp dụng được cho các phiên bản 6.x có cùng hợp đồng. Spring Boot bổ sung auto-configuration, runners và một số lifecycle event; chúng nằm ở lớp cao hơn, không thay đổi nguyên tắc cơ bản này.

## 2. Bốn đối tượng cần phân biệt

| Khái niệm | Là gì? | Ví dụ |
| --- | --- | --- |
| **Bean definition** | Metadata/container recipe mô tả class/factory method, scope, dependencies, lazy, init/destroy callbacks | `BeanDefinition`, `RootBeanDefinition` |
| **Bean instance** | Đối tượng thực sự được container tạo hoặc nhận từ factory, có lifecycle riêng | `new OrderService(...)` |
| **BeanFactory** | Thành phần giữ definitions, tạo và tra cứu beans, quản lý scope | `ConfigurableListableBeanFactory`, `DefaultListableBeanFactory` |
| **ApplicationContext** | Container cấp cao tích hợp BeanFactory với Environment, events, resources, internationalization và lifecycle | `AnnotationConfigApplicationContext`, `GenericApplicationContext` |

Từ khóa dễ nhầm: “bean đã đăng ký” có thể chỉ **bean definition tồn tại**, hoàn toàn chưa có instance. `containsBeanDefinition("orderService")` có thể trả `true` trước khi constructor của `OrderService` chạy.

`BeanDefinition` thường ghi nhận type/constructor args/property values/scope/lazy flags. Các bean definition còn có thể gắn factory method, parent definition hoặc cấu hình cần được hậu xử lý trước khi cuối cùng tạo instance.

## 3. Bức tranh tổng thể của refresh()

Trong các `AbstractApplicationContext`, `refresh()` là điểm điều phối quan trọng. Sơ đồ giản lược, giữ các giai đoạn trọng tâm:

```text
refresh()
  |
  +--> prepareRefresh()
  |       - trạng thái khởi động, environment
  |
  +--> obtainFreshBeanFactory()
  |       - có/đưa về BeanFactory phù hợp
  |       - nạp bean definitions tùy loại context
  |
  +--> prepareBeanFactory()
  |       - class loader, expression resolver,
  |         một số Aware/processor nền tảng
  |
  +--> postProcessBeanFactory() [hook của subclass]
  |
  +--> invokeBeanFactoryPostProcessors()
  |       - BeanDefinitionRegistryPostProcessor
  |       - BeanFactoryPostProcessor
  |       - xử lý @Configuration, @Bean, @Import,
  |         @ComponentScan, placeholders... khi phù hợp
  |
  +--> registerBeanPostProcessors()
  |       - chuẩn bị processor xử lý bean instance
  |
  +--> initMessageSource()
  +--> initApplicationEventMulticaster()
  +--> onRefresh() [hook của subclass]
  +--> registerListeners()
  |
  +--> finishBeanFactoryInitialization()
  |       - còn bước chuẩn bị/metadata khác
  |       - preInstantiateSingletons()
  |       - tạo singleton non-lazy bình thường
  |       - callback SmartInitializingSingleton
  |
  +--> finishRefresh()
          - khởi động lifecycle processor thích hợp
          - phát ContextRefreshedEvent
          - thông báo context hoàn thành refresh
```

Đây là bản diễn giải định hướng học tập, **không phải copy nguyên source**. Chẳng hạn với `GenericApplicationContext` hoặc `AnnotationConfigApplicationContext`, một số definitions đã được đăng ký **trước** `refresh()` qua `register(...)`, `registerBean(...)` hay registry APIs. Với những context đọc XML, definitions có thể được nạp trong quá trình `obtainFreshBeanFactory()`. Đừng khẳng định mọi loại context “chỉ bắt đầu đăng ký definitions sau khi gọi `refresh()`”.

**Bất biến quan trọng:** các processor xử lý **metadata của BeanFactory** phải được chạy trước vòng khởi tạo hàng loạt singleton thông thường. Các `BeanPostProcessor` cần được đăng ký trước khi bean nghiệp vụ được tạo để có cơ hội áp dụng đầy đủ.

## 4. Nạp và xây dựng bean definitions

### 4.1. Nguồn bean definition

Spring có thể nhận metadata từ nhiều nguồn:

- XML `<bean>`: class, constructor args, property values, scope, init/destroy methods.
- `@Configuration` và `@Bean`: phương thức factory trở thành bean definition; class cấu hình cũng có definition.
- `@Component`, `@Service`, `@Repository` và `@Controller`: component scanning phát hiện class và tạo definitions.
- `@Import`, `ImportSelector`, `ImportBeanDefinitionRegistrar`: thêm nội dung cấu hình/definitions theo hợp đồng.
- Java API: `GenericApplicationContext.registerBean(...)` hoặc `BeanDefinitionRegistry.registerBeanDefinition(...)`.
- Extension points: `BeanDefinitionRegistryPostProcessor` có thể đăng ký thêm definitions trước lúc tạo bean nghiệp vụ.

Các cách trên không mặc nhiên tạo instance ngay khi vừa đăng ký. `@ComponentScan` cũng không “new mọi class ở lúc scan”: nó đưa metadata vào registry để container xử lý về sau.

### 4.2. Class metadata và runtime instance

Ví dụ một định nghĩa chương trình:

```java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(ReportService.class)
        .setScope(BeanDefinition.SCOPE_SINGLETON)
        .setLazyInit(false)
        .getBeanDefinition();

registry.registerBeanDefinition("reportService", definition);
```

Đây là **mảnh code minh họa**, yêu cầu `registry` kiểu `BeanDefinitionRegistry` và một class `ReportService` thực sự tồn tại; không phải chương trình Java độc lập. `registerBeanDefinition` ở đây chủ yếu đưa *recipe* vào registry. Constructor sẽ chạy khi bean cần được tạo, thường trong `preInstantiateSingletons()` nếu nó là singleton non-lazy bình thường.

Đăng ký hai definition cùng tên, alias, bean definition override và điều kiện cấu hình là các chủ đề độc lập. Với production, tránh dựa trên quy tắc override theo mặc định vì có thể khác giữa container/configuration.

### 4.3. @ConfigurationClassPostProcessor

`ConfigurationClassPostProcessor` là extension point tiêu biểu: nó là `BeanDefinitionRegistryPostProcessor` và diễn giải `@Configuration`, `@ComponentScan`, `@Import`, `@Bean` cùng các cấu trúc cấu hình liên quan. Do nó có thể phát hiện và đăng ký **thêm** bean definitions, việc chạy bước cấu hình phải hoàn thành trước khi Spring quyết định vòng khởi tạo singleton thông thường.

Một class:

```java
@Configuration(proxyBeanMethods = false)
class AppConfiguration {
    @Bean
    ServiceA serviceA() {
        return new ServiceA();
    }
}
```

không nên được hiểu như “ngay khi đọc annotation, Spring đã gọi `serviceA()` và tạo `ServiceA`”. Method `@Bean` trở thành một factory recipe; Spring gọi phương thức ở thời điểm bean thực sự được yêu cầu theo scope.

Đây là mảnh cấu hình minh họa, chưa bao gồm imports và definitions của `ServiceA`.

## 5. BeanDefinitionRegistryPostProcessor: can thiệp vào registry

Giao diện `org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor` mở rộng `BeanFactoryPostProcessor` với thêm method:

```java
void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry);
```

Đây là chữ ký minh họa từ interface. Nó cho phép đăng ký hoặc điều chỉnh bean definitions **trước khi các `BeanFactoryPostProcessor` thông thường được phát hiện và chạy**.

Một implementation có hai điểm móc:

```java
class CustomRegistrar implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        // Registry phase: thêm/chỉnh definitions.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // BeanFactory phase: xem/chỉnh factory metadata.
    }
}
```

Đây là mảnh minh họa; cần imports của `BeanDefinitionRegistryPostProcessor`, `BeanDefinitionRegistry` và `ConfigurableListableBeanFactory`. Hai method thuộc **hai pha gọi khác nhau** dù cùng một instance processor.

Các công việc hợp lý trong registry phase: thêm bean definition có điều kiện, chỉnh scope/lazy flag, tạo synthetic infrastructure bean definition, hoặc tích hợp một cơ chế cấu hình riêng. Vì đây là lúc container còn đang xây dựng metadata, **không gọi `getBean()` chỉ để “xem bean có chạy không”**: điều đó có thể làm instance bị tạo quá sớm, trước khi các processor khác sẵn sàng.

### Registry processor có thể tiếp tục đăng ký processor khác

Spring phải xử lý trường hợp một `BeanDefinitionRegistryPostProcessor` đăng ký thêm một `BeanDefinitionRegistryPostProcessor` khác. Vì vậy một cách triển khai chuẩn sẽ tiếp tục tìm các registry processors chưa chạy trước khi kết thúc pha registry. Điều này là một lý do không thể suy luận đơn giản thứ tự chỉ dựa vào vị trí các method Java trong source.

Khi các registry processors được Spring tự phát hiện thành beans, `PriorityOrdered` và `Ordered` giúp sắp xếp **trong nhóm phù hợp**; với processor đăng ký trực tiếp qua `ConfigurableApplicationContext.addBeanFactoryPostProcessor(...)`, thứ tự đăng ký chương trình là yếu tố áp dụng cho nhóm đó, và metadata order không được dùng theo cùng cách.

## 6. BeanFactoryPostProcessor: chỉnh định nghĩa trước khi tạo bean

`BeanFactoryPostProcessor` định nghĩa:

```java
void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory);
```

Đây là chữ ký API minh họa. Processor này xử lý **BeanFactory và bean definitions**, không xử lý **một bean instance vừa được constructor tạo**.

Ví dụ hợp lý:

- Sửa property value có trong `BeanDefinition`.
- Áp dụng cấu hình placeholder bằng `PropertySourcesPlaceholderConfigurer`.
- Đăng ký custom scope bằng `CustomScopeConfigurer`.
- Điều chỉnh metadata để các bean sau này được tạo đúng.

Thứ tự logic tổng quát:

```text
Definitions đã có trong registry
    -> registry post-processors chạy
    -> factory post-processors chạy
    -> BeanPostProcessors được đăng ký
    -> singleton thường được tạo
```

**Lưu ý**: nếu code của một `BeanFactoryPostProcessor` chủ động gọi `getBean()`, nó **có thể ép khởi tạo một bean sớm**. Điều đó phá vỡ lợi thế của giai đoạn metadata và có thể khiến bean không được xử lý đầy đủ bởi `BeanPostProcessor` hoặc AOP proxy. Đây là anti-pattern đáng tránh.

### BeanFactoryPostProcessor so với BeanPostProcessor

| Tiêu chí | BeanFactoryPostProcessor | BeanPostProcessor |
| --- | --- | --- |
| Đối tượng được xử lý | BeanFactory và metadata/bean definitions | Bean instance |
| Thời điểm điển hình | Trong `invokeBeanFactoryPostProcessors()`, trước tạo singleton thông thường | Trong quá trình khởi tạo từng bean |
| API trọng tâm | `postProcessBeanFactory(...)` | `postProcessBeforeInitialization(...)` / `postProcessAfterInitialization(...)` |
| Ví dụ | `PropertySourcesPlaceholderConfigurer`, `CustomScopeConfigurer` | `CommonAnnotationBeanPostProcessor`, auto-proxy creators |
| Sai lầm phổ biến | Gọi `getBean` quá sớm | Nhầm với chỉnh bean definition |
| Có thể thêm bean definitions? | Không phải mục đích chính của BFPP thường | Không phải nhiệm vụ của BPP |
| Sắp xếp bằng | `PriorityOrdered`/`Ordered` với auto-detected BFPP, quy tắc riêng khi add thủ công | `PriorityOrdered`/`Ordered` tùy cách đăng ký BPP |

`BeanDefinitionRegistryPostProcessor` là trường hợp chuyên biệt có quyền làm việc với registry, khác với `BeanFactoryPostProcessor` thông thường.

## 7. Đăng ký BeanPostProcessor trước khi tạo singleton

`BeanPostProcessor` cung cấp hai hook thường gặp:

```java
Object postProcessBeforeInitialization(
        Object bean, String beanName);

Object postProcessAfterInitialization(
        Object bean, String beanName);
```

Chúng chạy cho từng bean được Spring tạo và qua pipeline tương ứng; processor có thể trả nguyên instance hoặc một wrapper/proxy. Spring đăng ký các bean implement `BeanPostProcessor` vào BeanFactory ở giai đoạn `registerBeanPostProcessors()`, trước việc `finishBeanFactoryInitialization()` tạo các singleton non-lazy bình thường.

### BeanPostProcessor không đồng nghĩa “sau mọi callback”

Trên một bean được Spring quản lý thông thường:

```text
instantiate
 -> dependency injection/populate properties
 -> BeanNameAware / BeanFactoryAware và các aware hooks cơ bản
 -> postProcessBeforeInitialization (chuỗi các processor)
      [có thể xử lý @PostConstruct trong chuỗi này]
 -> InitializingBean.afterPropertiesSet()
 -> custom init-method
 -> postProcessAfterInitialization (chuỗi các processor)
      [có thể tạo AOP proxy]
 -> bean sẵn sàng được publish
```

`@PostConstruct` được xử lý bởi lifecycle annotation processor (thường `CommonAnnotationBeanPostProcessor`) trong **before-initialization chain**. Vì vậy không đúng khi nói “mọi user-defined before processor nhất thiết chạy trước `@PostConstruct`”. Thứ tự giữa các processor liên quan còn phụ thuộc order/registration.

Một proxy AOP thường được tạo/hoàn tất trong các post-processing stages. Nếu bạn gọi method cần advice ở constructor hoặc `@PostConstruct`, đừng giả định method đi qua proxy cuối cùng.

### Tại sao chính các processor đôi khi không được đầy đủ AOP?

`BeanPostProcessor` và dependency mà chúng cần có thể phải tạo **sớm để container đủ khả năng xử lý các bean khác**. Vì vậy chúng có thể không đủ điều kiện auto-proxying do các processor còn lại chưa đăng ký. Spring có thể log dạng “not eligible for getting processed by all BeanPostProcessors”, tùy cấu hình. Đây là tín hiệu phải kiểm tra dependency graph và thời điểm tạo bean, không nên tắt logging rồi bỏ qua.

## 8. finishBeanFactoryInitialization() và non-lazy singleton

Khi metadata processors đã chạy, BeanPostProcessors đã được đăng ký và các thành phần hỗ trợ của context đã chuẩn bị, Spring thực hiện `finishBeanFactoryInitialization(beanFactory)`. Trong các bước bên trong, lệnh then chốt là `preInstantiateSingletons()`.

**Mục tiêu:** tạo trước phần lớn các bean `singleton` có `lazy-init=false` để phát hiện sớm lỗi wiring/cấu hình và chuẩn bị ứng dụng phục vụ.

Một singleton thông thường lúc này trải qua:

1. Xác định và chọn constructor hoặc factory method.
2. Resolve constructor arguments và dependencies cần thiết.
3. Instantiate đối tượng.
4. Populate property/field/setter dependencies.
5. Gọi callbacks `Aware` phù hợp.
6. Chạy `BeanPostProcessor` trước khởi tạo, bao gồm lifecycle annotation callbacks.
7. Gọi `InitializingBean.afterPropertiesSet()` nếu có.
8. Gọi custom init method nếu cấu hình.
9. Chạy `BeanPostProcessor` sau khởi tạo; có thể trả AOP proxy.
10. Lưu/expose singleton hoàn tất trong registry singleton.

Một vài chi tiết ở đây có thể được Spring tối ưu, gọi sớm theo dependency hoặc xử lý đặc biệt cho FactoryBean/AOP/circular references. Đừng coi danh sách trên là bảo đảm mọi bean đều được tạo cùng một cách.

### Singleton nào không nhất thiết được tạo ngay?

- `@Lazy` singleton chưa bị bean eager nào cần tới.
- `prototype` không được tạo hàng loạt chỉ vì có definition.
- `request`/`session` phụ thuộc scope và ngữ cảnh đang hoạt động.
- Bean không có definition độc lập mà chỉ được tạo bởi code thủ công `new` thì không thuộc quá trình container quản lý.
- Với `FactoryBean`, cần phân biệt singleton **factory object** và **product** do `getObject()` trả về; có trường hợp đặc biệt liên quan `SmartFactoryBean` và eager initialization.

### Depends-on, constructor dependency và thứ tự

Spring tôn trọng quan hệ dependency thật sự: một bean có constructor parameter cần bean khác sẽ kéo bean phụ thuộc vào vòng tạo trước; `@DependsOn` khai báo dependency cần khởi tạo trước. Điều này **không tạo ra một thứ tự tổng quát** cho các singleton không liên quan.

Không dựa vào thứ tự khai báo các method `@Bean`, thứ tự tên class hoặc thứ tự quét package như một hợp đồng startup. `@Order` cũng không có nghĩa mọi singleton sẽ được instantiate theo order đó.

## 9. Sau khi tạo singleton: SmartInitializingSingleton và ContextRefreshedEvent

`SmartInitializingSingleton.afterSingletonsInstantiated()` chạy ở cuối vòng pre-instantiation singleton thông thường. Nó hữu ích khi một singleton phải thực hiện bước kiểm tra sau khi **các singleton eager thông thường đã được tạo**, mà không muốn vô tình tạo chúng quá sớm trong `@PostConstruct`.

```java
public class RegistryCheck implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Kiểm tra sau vòng non-lazy singleton pre-instantiation.
    }
}
```

Đây là mảnh code minh họa, cần interface import và class được đăng ký làm bean singleton. Callback này **không chạy trên các prototype** và không đương nhiên chạy cho singleton lazy được tạo muộn. Nó cũng không nghĩa toàn bộ hệ thống bên ngoài (database, queue, network) đã healthy.

Đến `finishRefresh()`, container sử dụng lifecycle processor để start các thành phần lifecycle thích hợp, sau đó phát `ContextRefreshedEvent`. Ứng dụng có thể lắng nghe mốc này:

```java
@Component
class RefreshedListener {
    @EventListener
    void ready(ContextRefreshedEvent event) {
        // Một ApplicationContext vừa refresh xong.
    }
}
```

Đây là mảnh minh họa yêu cầu import `Component`, `EventListener` và `ContextRefreshedEvent`. Với context hierarchy, sự kiện từ child có thể propagate đến parent; nếu cần chỉ xử lý context cụ thể, hãy lọc `event.getApplicationContext()`.

**Không đồng nhất callback init của từng bean với event context đã refresh.** Ở `@PostConstruct` của bean A, các singleton khác có thể chưa hoàn tất. Sau `ContextRefreshedEvent`, lần refresh tương ứng đã hoàn tất, nhưng vẫn có lazy beans hoặc prototype chưa tạo.

## 10. Ví dụ thực hành Java 17+ quan sát chuỗi sự kiện

Mẫu sau dùng Spring Framework 6.2.x không phụ thuộc Spring Boot. Nó cố ý **đăng ký một registry processor, một factory processor và một instance post-processor qua Java API** để luồng chạy quan sát được, rồi tạo một singleton non-lazy và đóng context. Không dùng component scanning trong ví dụ này nhằm tách rõ các pha.

Cấu trúc:

```text
context-startup-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/ContextStartupDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'context-startup-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ContextStartupDemo'
}
```

### src/main/java/ContextStartupDemo.java

```java
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;

public class ContextStartupDemo {

    static class Registrar implements BeanDefinitionRegistryPostProcessor {
        @Override
        public void postProcessBeanDefinitionRegistry(
                BeanDefinitionRegistry registry) {
            System.out.println("01 BDRPP.registry");
            registry.registerBeanDefinition(
                    "task",
                    BeanDefinitionBuilder
                            .genericBeanDefinition(TrackedTask.class)
                            .setInitMethodName("customInit")
                            .setDestroyMethodName("customDestroy")
                            .getBeanDefinition()
            );
        }

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory) {
            System.out.println("02 BDRPP.factory");
        }
    }

    static class TracingPostProcessor implements BeanPostProcessor {
        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {
            if ("task".equals(beanName)) {
                System.out.println("06 BPP.before");
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {
            if ("task".equals(beanName)) {
                System.out.println("09 BPP.after");
            }
            return bean;
        }
    }

    public static class TrackedTask
            implements BeanNameAware, InitializingBean,
                       SmartInitializingSingleton,
                       ApplicationListener<ContextRefreshedEvent>,
                       DisposableBean {

        public TrackedTask() {
            System.out.println("04 constructor");
        }

        @Override
        public void setBeanName(String beanName) {
            System.out.println("05 BeanNameAware " + beanName);
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("07 afterPropertiesSet");
        }

        public void customInit() {
            System.out.println("08 customInit");
        }

        @Override
        public void afterSingletonsInstantiated() {
            System.out.println("10 afterSingletonsInstantiated");
        }

        @Override
        public void onApplicationEvent(ContextRefreshedEvent event) {
            System.out.println("11 ContextRefreshedEvent");
        }

        @Override
        public void destroy() {
            System.out.println("13 DisposableBean.destroy");
        }

        public void customDestroy() {
            System.out.println("14 customDestroy");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Đăng ký registry/factory processors trước refresh().
            context.addBeanFactoryPostProcessor(new Registrar());
            context.addBeanFactoryPostProcessor(
                    beanFactory -> System.out.println(
                            "03 BFPP.definition=" +
                            beanFactory.containsBeanDefinition("task")));

            // Đăng ký một BPP thủ công trước khi tạo bean nghiệp vụ.
            context.getBeanFactory().addBeanPostProcessor(
                    new TracingPostProcessor());

            context.refresh();

            TrackedTask first = context.getBean(TrackedTask.class);
            TrackedTask second = context.getBean(TrackedTask.class);
            System.out.println("12 sameSingleton=" + (first == second));
        }
    }
}
```

Chạy từ thư mục chứa `build.gradle`:

```bash
gradle run --quiet
# Nếu đã tạo Gradle Wrapper trong dự án:
# ./gradlew run --quiet
```

Các dòng do **chương trình tự in ra qua System.out**:

```text
01 BDRPP.registry
02 BDRPP.factory
03 BFPP.definition=true
04 constructor
05 BeanNameAware task
06 BPP.before
07 afterPropertiesSet
08 customInit
09 BPP.after
10 afterSingletonsInstantiated
11 ContextRefreshedEvent
12 sameSingleton=true
13 DisposableBean.destroy
14 customDestroy
```

**Vì sao thứ tự này phù hợp?**

1. `Registrar` được context đăng ký thủ công và chạy pha registry đầu tiên; method đó đưa definition `task` vào registry.
2. `Registrar.postProcessBeanFactory` chạy trong pha factory processor của registrar.
3. BFPP lambda chạy sau pha registrar và quan sát `containsBeanDefinition("task") == true`, chứng tỏ definition đã có mà task chưa cần được instantiate.
4. `refresh()` đến `finishBeanFactoryInitialization()` và tạo `TrackedTask` là singleton mặc định; constructor in `04`.
5. `BeanNameAware` chạy trong bước initialize bean; tên do registry đặt là `task`.
6. `TracingPostProcessor` đã được add trước refresh, nên nhận callback before.
7. `InitializingBean.afterPropertiesSet` chạy, sau đó custom init tên `customInit` được định nghĩa trong bean metadata.
8. `TracingPostProcessor` nhận after callback.
9. `SmartInitializingSingleton.afterSingletonsInstantiated` chạy khi pre-instantiation singleton thông thường kết thúc.
10. `ContextRefreshedEvent` được phát trong bước hoàn tất refresh. `TrackedTask` cũng là `ApplicationListener`, nên được gọi.
11. Hai `getBean(TrackedTask.class)` trả cùng singleton.
12. Khi `try-with-resources` đóng context, `DisposableBean.destroy()` chạy trước custom destroy của cùng bean.

Nếu thêm bean/processor khác vào chương trình, log có thể xen thêm event hoặc thứ tự gián tiếp thay đổi. Đó là lý do chương trình sử dụng những method đơn giản và in số thứ tự một cách có chủ đích. Logging của framework không phải một phần của các dòng `System.out` được liệt kê.

## 11. Biến thể: @PostConstruct đứng ở đâu?

Có thể mở rộng `TrackedTask` bằng:

```java
import jakarta.annotation.PostConstruct;

@PostConstruct
public void initAnnotated() {
    System.out.println("@PostConstruct");
}
```

Đây là mảnh code để thêm vào class của chương trình, cần dependency `jakarta.annotation:jakarta.annotation-api` có mặt trong classpath khi cần. Khi Spring đăng ký lifecycle annotation processor, method này chạy trong chuỗi `BeanPostProcessor.postProcessBeforeInitialization`. Nó diễn ra **trước `afterPropertiesSet` và trước custom init**, nhưng vị trí tương đối giữa log `BPP.before` tự đăng ký và `@PostConstruct` phụ thuộc thứ tự các post-processors. Không ghép mảnh code này rồi kỳ vọng output in sẵn ở mục 10 còn nguyên.

Với ba init mechanism khác tên trên cùng bean, Spring quy định:

```text
@PostConstruct
 -> InitializingBean.afterPropertiesSet()
 -> custom init-method
```

Đó là thứ tự của callback init trên **từng bean**, độc lập với việc các bean không liên quan có được tạo trước hay sau nhau.

## 12. Cách Spring sắp thứ tự post-processors

### 12.1. Factory-level processors

Khi container **tự phát hiện** `BeanDefinitionRegistryPostProcessor` hoặc `BeanFactoryPostProcessor` là bean, các interface `PriorityOrdered` và `Ordered` có thể điều khiển thứ tự **trong nhóm xử lý tương ứng**. Spring cần hoàn tất pha registry trước khi làm tiếp các BFPP thường.

Một điểm quan trọng: `@Order` trên class bean **không tự thay thế** quy tắc ordering của `BeanFactoryPostProcessor`. Javadoc nêu `@Order` không được tính cho BFPP beans, trong khi `PriorityOrdered` và `Ordered` được dùng nếu processor được tự phát hiện.

Nếu đăng ký trực tiếp processor bằng `context.addBeanFactoryPostProcessor(...)`, chúng được áp dụng theo **registration order** phù hợp với cơ chế programmatic; `PriorityOrdered`/`Ordered` của chúng không được Spring dùng như khi processor được autodetect.

### 12.2. Instance-level processors

`BeanPostProcessor` làm việc với objects. Các BPP auto-detected có thứ tự gắn với `PriorityOrdered`/`Ordered` hoặc thứ tự đăng ký phù hợp. Khi bạn gọi trực tiếp `beanFactory.addBeanPostProcessor(...)`, thứ tự đăng ký tương ứng có ý nghĩa, và các processor vừa được đăng ký cũng có thể ảnh hưởng việc auto-detected BPP còn lại được gọi như thế nào.

Khi phải kiểm soát thứ tự nhiều BPP, hãy test trên Spring version triển khai cụ thể, kiểm tra order contract và không tạo bean nghiệp vụ trước lúc processors đã được đăng ký.

### 12.3. Không lấy @Order để sắp xếp mọi singleton

`@Order` có nhiều mục đích, ví dụ sắp xếp collection dependency hoặc các extension point hỗ trợ ordering. Nó **không là tổng thứ tự instantiate tất cả singleton**. Nếu service A cần B sẵn sàng trước, hãy khai báo constructor dependency hoặc `@DependsOn` ở trường hợp phù hợp.

## 13. @Lazy, prototype, request scope và thay đổi thời điểm tạo

| Loại bean | Có definition ở lúc refresh? | Thời điểm instance xuất hiện |
| --- | --- | --- |
| Eager singleton thông thường | Có | Thường trong `preInstantiateSingletons()`, có thể sớm hơn khi dependency cần |
| `@Lazy` singleton | Có | Khi lần đầu thực sự cần; có thể bị eager bean yêu cầu ngay lúc refresh |
| Prototype | Có | Mỗi lần BeanFactory tạo/resolve một prototype (trừ trường hợp reference prototype được giữ cố định ở bean khác) |
| Request-scoped | Có | Khi request scope active và bean được yêu cầu |
| Session-scoped | Có | Khi session scope active và bean được yêu cầu |
| `FactoryBean` | Có definition của factory | Factory và product có lifecycle/cache semantics riêng; xem scope và contract của factory |

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class LazyConfig {
    @Bean
    @Lazy
    ExpensiveClient expensiveClient() {
        return new ExpensiveClient();
    }
}
```

Đây là mảnh minh họa, class `ExpensiveClient` chưa được định nghĩa. Definition có thể đã tồn tại khi context refresh hoàn thành mà instance `ExpensiveClient` chưa từng được tạo. Nhưng nếu singleton eager phụ thuộc trực tiếp vào `ExpensiveClient` lúc constructor injection, bean có thể bị tạo ngay để thỏa dependency dù annotated lazy.

Với prototype, bean cũng nhận BeanPostProcessors/init callbacks mỗi lần được tạo qua container. Spring không tự theo dõi hoàn chỉnh destruction cho prototype sau khi giao cho caller; caller cần chủ động cleanup.

## 14. FactoryBean: khởi tạo factory không đồng nhất với product

`FactoryBean<T>` là một Spring contract đặc biệt: bean definition thường biểu diễn **factory**; gọi `getBean("name")` có thể lấy **product** do `getObject()` tạo, còn `getBean("&name")` lấy factory.

Do đó hai câu hỏi cần tách riêng:

1. Khi nào **factory instance** được tạo/khởi tạo?
2. Khi nào **product** được tạo và cache hay không, theo `FactoryBean.isSingleton()` cùng BeanFactory semantics?

Không nên khẳng định rằng “vì factory singleton eager nên tất cả product của mọi FactoryBean chắc chắn cũng eager”. `SmartFactoryBean.isEagerInit()` và cách lookup/type resolution có thể ảnh hưởng trường hợp cụ thể. BeanPostProcessor có thể xử lý cả factory object và những sản phẩm theo quy tắc hỗ trợ của container.

Khi debug, dùng bean name/`&` prefix chính xác và kiểm tra bean definition, `FactoryBean` implementation cùng điều kiện lazy/eager của version hiện tại.

## 15. Bean creation sớm: vì sao nguy hiểm?

Một số cảnh báo kiểu:

```text
Bean 'x' is not eligible for getting processed by all BeanPostProcessors
```

cho thấy instance `x` được tạo khi bộ processor chưa hoàn thiện (tùy Spring version và hoàn cảnh cụ thể). Những nguyên nhân có thể gồm:

- Một `BeanFactoryPostProcessor` gọi `getBean("x")` trong `postProcessBeanFactory`.
- Constructor của một `BeanPostProcessor` yêu cầu quá nhiều beans nghiệp vụ.
- Auto-proxy creator hoặc processor liên quan khởi tạo dependencies sớm.
- Bean phải được khởi tạo sớm để xử lý metadata/processor trước khi mọi infrastructure hoàn tất.

Ví dụ anti-pattern:

```java
class BadFactoryProcessor implements BeanFactoryPostProcessor {
    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Không nên làm thế chỉ để "validate" một bean nghiệp vụ.
        Object service = beanFactory.getBean("businessService");
        System.out.println(service);
    }
}
```

Đây là mảnh minh họa; cần import `BeanFactoryPostProcessor` và `ConfigurableListableBeanFactory`. Do BFPP chạy ở giai đoạn metadata, `getBean` có thể làm `businessService` bị instantiate trước khi nhiều `BeanPostProcessor` auto-detected được đăng ký.

Cách thay thế: xác thực **metadata** của bean definition ở giai đoạn factory processor; nếu phải làm việc với instance, chuyển logic tới callback sau singleton initialization như `SmartInitializingSingleton` hoặc một sự kiện phù hợp, nhưng chỉ khi đó là đúng mốc nghiệp vụ.

## 16. Xác minh context đã tạo singleton thật sự

Một số quan sát có giá trị:

```java
ConfigurableListableBeanFactory factory =
        context.getBeanFactory();

boolean hasDefinition = factory.containsBeanDefinition("task");
boolean hasSingleton = factory.containsSingleton("task");
boolean singletonConfigured = factory.getBeanDefinition("task").isSingleton();
```

Đây là mảnh minh họa, giả định `context` là `AnnotationConfigApplicationContext` đã được khởi tạo, đồng thời cần import `ConfigurableListableBeanFactory`. Chúng trả lời các câu hỏi **khác nhau**:

- `containsBeanDefinition`: recipe có tồn tại trong local BeanFactory hay không.
- `containsSingleton`: singleton instance mang name tương ứng đã được đăng ký trong singleton cache hay chưa.
- `BeanDefinition.isSingleton`: metadata nói scope singleton hay không, không chứng minh instance đã tồn tại.

Đặc biệt, trước `refresh` với `AnnotationConfigApplicationContext`, không nên chủ động gọi các factory APIs tùy ý vốn yêu cầu context đã active chỉ để thăm dò; cách an toàn trong bài demo là đọc registry metadata khi phù hợp, rồi đọc runtime state sau `refresh()`.

Nếu cần kiểm tra **số singleton**, `getSingletonCount()` đếm những singleton instance đã đăng ký trong cache, bao gồm nhiều infrastructure beans, không thể đồng nhất với tổng số class có `@Component` hoặc số definition trong registry.

### Log và breakpoint hữu ích

Bật log mức debug/trace cho các package Spring beans/context thích hợp trong môi trường local để theo dõi bean definition, dependency resolution và bean instantiation. Tùy phiên bản, thông báo log cụ thể có thể đổi; đừng viết test dựa trên text log nội bộ cố định.

Các điểm gỡ lỗi có ích:

- `AbstractApplicationContext.refresh()` để theo dõi các pha.
- `PostProcessorRegistrationDelegate.invokeBeanFactoryPostProcessors(...)`.
- `PostProcessorRegistrationDelegate.registerBeanPostProcessors(...)`.
- `DefaultListableBeanFactory.preInstantiateSingletons()`.
- `AbstractAutowireCapableBeanFactory.createBean(...)` / `doCreateBean(...)`.
- `AbstractAutowireCapableBeanFactory.initializeBean(...)`.
- `AbstractApplicationContext.finishRefresh()`.

Tên method/class là cơ sở để đọc source Spring Framework; chúng không phải API mà business code nên phụ thuộc.

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Chính xác hơn |
| --- | --- |
| “Scan xong là tất cả object đã được new” | Scan tạo/đăng ký definitions; tạo instance là pha riêng |
| “BFPP là callback chạy trên bean object” | BFPP làm việc trên factory/definition; BPP mới làm việc với instance |
| “Registry post-processor chỉ đọc definitions” | BDRPP có thể thêm/sửa definitions trong registry |
| “Mọi singleton chỉ được tạo trong finishBeanFactoryInitialization” | Đó là vòng eager chung; dependencies/infrastructure có thể bị tạo sớm |
| “@Lazy bean chắc chắn không tạo cho tới sau startup” | Nếu eager bean phụ thuộc nó, lazy bean có thể cần tạo ngay |
| “@Order luôn điều khiển constructor order” | Không; dependency graph và lifecycle hooks mới là điều kiện cần xét |
| “Bean đã có definition nghĩa là getBean trả sẵn object” | Definition có thể tồn tại khi object chưa instantiate |
| “@PostConstruct là một callback chạy sau mọi BeanPostProcessor” | Nó do lifecycle processor kích hoạt trong before-initialization chain |
| “SmartInitializingSingleton báo tất cả beans mọi scope đều có instance” | Chỉ mốc kết thúc regular singleton pre-instantiation |
| “ContextRefreshedEvent nghĩa là tất cả tài nguyên ngoài đều ready” | Event chỉ bảo đảm lần refresh của context đã hoàn tất |
| “BeanFactoryPostProcessor dùng để sửa state của bean” | Nên chỉnh metadata, tránh tạo object sớm |
| “FactoryBean eager nghĩa là product luôn eager” | Factory và product là hai đối tượng, behavior còn phụ thuộc FactoryBean contract |

## 18. Checklist thiết kế và kiểm thử

Trước khi tạo một custom extension point:

1. Bạn muốn **thêm bean definitions** hay chỉ chỉnh metadata của definitions đã có? Chọn `BeanDefinitionRegistryPostProcessor` hoặc `BeanFactoryPostProcessor` cho đúng.
2. Bạn muốn thay đổi instance ngay lúc nó được tạo? Chọn `BeanPostProcessor`.
3. Bạn muốn init logic **trên một bean sau dependency injection**? Dùng `@PostConstruct`, `InitializingBean` hoặc custom init method, tránh logic dài/blocking gọi nhiều bean khác.
4. Bạn cần công việc chạy **sau các non-lazy singletons**? Cân nhắc `SmartInitializingSingleton`.
5. Bạn cần mốc context hoàn thành refresh? Lắng nghe `ContextRefreshedEvent`, cân nhắc hierarchy/event phát lặp.
6. Bean là singleton eager, singleton lazy, prototype hay custom scope? Scope quyết định instance creation và ownership.
7. Có processor nào gọi `getBean()` trong constructor/BFPP và đẩy bean nghiệp vụ vào đường early initialization?
8. Có dependency edge thực sự/`@DependsOn`, hay bạn đang dựa vào thứ tự class scanning không được cam kết?
9. Bean có lifecycle state, tài nguyên socket, pool, executor hoặc AOP proxy cần sẵn sàng trước khi dùng?
10. Có test xác nhận event order, number of instances và cleanup không?

### Các ca kiểm thử nên có

- Sau registry processor, `containsBeanDefinition("task") == true` nhưng constructor chưa chạy.
- BFPP chạy trước `TrackedTask` constructor.
- BPP before/after của `task` chạy quanh init callbacks.
- Singleton `task` được lấy hai lần là cùng reference.
- Sau singleton pre-instantiation, `SmartInitializingSingleton` chạy trước `ContextRefreshedEvent`.
- Đóng context gọi destruction callbacks của singleton theo hợp đồng.
- Khi chuyển bean sang `@Lazy`, việc tạo instance có thể lùi tới lần `getBean` đầu tiên.
- Khi chuyển sang prototype, hai `getBean` độc lập cho ra hai instance.
- Gọi `getBean` sớm trong BFPP có thể làm lệch expected behavior và không nên được coi là cách khởi tạo chuẩn.

## 19. Kết nối với cách thiết kế ứng dụng

Trong ứng dụng web hoặc service, việc hiểu rõ pipeline ảnh hưởng trực tiếp đến chất lượng code:

**Cấu hình**: sử dụng `@Bean`, `@Configuration`, `@ComponentScan` và classpath scanner để nạp metadata; tránh side effect trong constructors của configuration classes.

**Processor metadata**: các cơ chế như placeholder resolution, custom scopes hoặc configuration registration nên triển khai trước phase singleton instantiation. Điều này giúp container có metadata đúng để wiring ổn định.

**Processor instance**: annotation support, lifecycle callbacks và AOP cần được gắn vào container trước khi bean được tạo; thiết kế processor tránh phụ thuộc quá rộng vào business services.

**Các singleton nghiệp vụ**: constructor injection làm dependency graph rõ ràng, kiểm chứng invariant sớm; `@PostConstruct` chỉ kiểm tra và chuẩn bị state cục bộ, tránh khởi chạy background thread hoặc truy vấn mạng kéo dài khi container còn trong quá trình tạo beans.

**Readiness**: nếu cần bước khởi động ứng dụng sau khi có đầy đủ singletons, chọn hook có mốc đúng như `SmartInitializingSingleton`, `ContextRefreshedEvent` hoặc `SmartLifecycle`. Mốc lifecycle của Spring Core không đồng nghĩa liveness/readiness ở load balancer hoặc trạng thái các hệ thống bên ngoài.

**Shutdown**: context refresh và context close là hai nửa vòng đời khác nhau. Singleton destruction, `@PreDestroy`, `DisposableBean` và `destroyMethod` xảy ra khi container quản lý teardown; prototype không tự được container quản lý destruction sau khi giao cho caller.

## 20. Tài liệu chuẩn để đối chiếu

- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): mục `BeanFactoryPostProcessor` và `BeanPostProcessor`, khác biệt metadata so với instance, early initialization và ordering.
- [Spring Framework Reference — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html): đăng ký annotation processors và lifecycle handling.
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): component scanning, stereotypes và registration.
- [Spring Framework 6.2 Javadoc — BeanDefinitionRegistryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html): hợp đồng registry phase.
- [Spring Framework 6.2 Javadoc — BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html): xử lý metadata trước khi tạo instance và semantics ordering.
- [Spring Framework 6.2 Javadoc — SmartInitializingSingleton](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback cuối vòng pre-instantiation singleton.
- [Spring Framework 6.2 Javadoc — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `refresh` và các pha context lifecycle.
- [Spring Framework 6.2 Javadoc — DefaultListableBeanFactory](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html): singleton pre-instantiation và BeanFactory API.

**Chuỗi quan trọng để ghi nhớ:** **bean definitions → registry/factory post-processors → đăng ký BeanPostProcessors → khởi tạo eager singletons → SmartInitializingSingleton → ContextRefreshedEvent**. Mỗi bước có một trách nhiệm riêng; hiểu đúng ranh giới này giúp triển khai Spring Core Container an toàn và giải thích chính xác các lỗi khởi tạo.
