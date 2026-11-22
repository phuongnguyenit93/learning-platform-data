# ApplicationContextInitializedEvent và ApplicationPreparedEvent

Spring Boot phát ra nhiều application event trong lúc khởi động. Hai event quan trọng ở giai đoạn trước khi context được refresh là `ApplicationContextInitializedEvent` và `ApplicationPreparedEvent`. Cả hai đều cho biết ứng dụng đã đi qua một mốc chuẩn bị, nhưng chúng xuất hiện ở hai thời điểm khác nhau và context có trạng thái khác nhau.

- `ApplicationContextInitializedEvent` được phát sau khi `ApplicationContext` đã được tạo, `Environment` đã được gắn vào context và các `ApplicationContextInitializer` đã chạy, nhưng trước khi các nguồn cấu hình chính được nạp thành bean definitions.
- `ApplicationPreparedEvent` được phát sau khi các nguồn cấu hình của ứng dụng đã được nạp vào context và context đã sẵn sàng để refresh, nhưng trước khi quá trình refresh bắt đầu.

Hiểu đúng hai mốc này giúp bạn biết khi nào có thể quan sát context, khi nào các bean definitions bắt đầu xuất hiện, vì sao một bean listener dùng `@EventListener` không nhận được các event rất sớm và nên dùng extension point nào để thay đổi cấu hình startup.

Bài học hướng tới Spring Boot 3.x. Một số chi tiết nội bộ có thể thay đổi giữa các phiên bản, nhưng ý nghĩa của hai event và vị trí của chúng trong startup lifecycle là nền tảng để đọc log, viết listener và chẩn đoán lỗi khởi động.

## 1. Vị trí của hai event trong startup lifecycle

Khi gọi `SpringApplication.run(...)`, Spring Boot chuẩn bị environment, tạo application context, nạp nguồn cấu hình, refresh context rồi mới chạy các runner và đánh dấu ứng dụng sẵn sàng.

Trình tự khái quát:

~~~mermaid
flowchart TD
    A["SpringApplication.run()"] --> B["ApplicationStartingEvent"]
    B --> C["Chuẩn bị Environment"]
    C --> D["ApplicationEnvironmentPreparedEvent"]
    D --> E["Tạo ApplicationContext"]
    E --> F["Chạy ApplicationContextInitializer"]
    F --> G["ApplicationContextInitializedEvent"]
    G --> H["Nạp application sources / bean definitions ban đầu"]
    H --> I["ApplicationPreparedEvent"]
    I --> J["ApplicationContext.refresh()"]
    J --> K["Configuration processing, component scan, @Bean"]
    K --> L["Tạo singleton và hoàn tất ContextRefreshedEvent"]
    L --> M["ApplicationStartedEvent"]
    M --> N["ApplicationRunner / CommandLineRunner"]
    N --> O["ApplicationReadyEvent"]
~~~

Hai event nằm trước `refresh()`. Chúng không có nghĩa ứng dụng đã phục vụ request hoặc mọi bean đã sẵn sàng.

| Event | Mốc phát | Trạng thái chính |
| --- | --- | --- |
| `ApplicationContextInitializedEvent` | Sau khi context được tạo và các initializer đã chạy | Context có Environment và đã được initializer chuẩn bị; application sources chưa được nạp |
| `ApplicationPreparedEvent` | Sau khi application sources được nạp, ngay trước refresh | Context sẵn sàng refresh; các source bean definitions ban đầu đã được đăng ký |
| `ContextRefreshedEvent` | Khi refresh hoàn tất | Context đã refresh và các singleton eager thông thường đã được khởi tạo |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Context đã khởi động; runner chưa hoàn tất |
| `ApplicationReadyEvent` | Sau khi runners hoàn tất | Ứng dụng đã hoàn tất giai đoạn startup và sẵn sàng nhận traffic theo lifecycle của Boot |

Tên event gần giống nhau nên dễ nhầm. Hãy nhớ rằng *Initialized* là mốc sau context initializer, còn *Prepared* là mốc sau khi application sources được nạp và trước refresh.

## 2. ApplicationContextInitializedEvent là gì?

`ApplicationContextInitializedEvent` thuộc package `org.springframework.boot.context.event`. Spring Boot phát event này khi:

1. `ApplicationContext` đã được tạo.
2. `Environment` đã được thiết lập cho context.
3. Các `ApplicationContextInitializer` đã được gọi.
4. Các application sources chưa được nạp vào context như bean definitions.

Event cung cấp context thông qua `getApplicationContext()`. Vì vậy listener có thể quan sát context và environment ở thời điểm rất sớm.

### 2.1. Những gì đã có tại thời điểm này?

Thông thường listener có thể:

- Đọc `context.getId()` và thông tin context.
- Đọc active/default profiles qua `context.getEnvironment()`.
- Kiểm tra các property đã được nạp vào Environment.
- Quan sát những thay đổi do `ApplicationContextInitializer` thực hiện.
- Ghi log hoặc thu thập thông tin chẩn đoán về giai đoạn khởi động.

Ví dụ, đọc profile:

~~~java
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationListener;

public class ContextInitializedLogger
        implements ApplicationListener<ApplicationContextInitializedEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextInitializedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("Context id: " + context.getId());
        System.out.println(
                "Active profiles: "
                        + String.join(
                                ",",
                                context.getEnvironment().getActiveProfiles()
                        )
        );
    }
}
~~~

Listener trên không cần là Spring bean. Nó có thể được đăng ký trực tiếp với `SpringApplication` trước khi gọi `run`.

### 2.2. Bean definitions của ứng dụng chưa được nạp

Tại thời điểm `ApplicationContextInitializedEvent` được phát, Spring Boot chưa nạp các primary application sources vào context. Vì vậy không nên kỳ vọng các class được khai báo qua `@SpringBootApplication`, component scan hoặc các `@Bean` method đã trở thành bean definitions đầy đủ.

Context có thể đã có hạ tầng hoặc bean definition do initializer chủ động đăng ký. Vì thế, không nên khẳng định bean factory luôn rỗng. Điều quan trọng là **các nguồn cấu hình chính của ứng dụng chưa được nạp ở mốc này**.

Nếu cần đăng ký hoặc thay đổi cấu trúc context trước khi application sources được nạp, `ApplicationContextInitializer` thường là extension point đúng hơn việc đợi event rồi thay đổi context.

### 2.3. Event này không có nghĩa bean đã được tạo

`ApplicationContextInitializedEvent` xảy ra trước `refresh()`. Các singleton eager thông thường chưa được tạo và các `@PostConstruct` chưa chạy.

Tránh gọi `context.getBean(...)` để lấy service ứng dụng ở thời điểm này. Bean definition có thể chưa tồn tại; ngay cả khi có một definition do initializer đăng ký, việc chủ động tạo bean quá sớm có thể làm thay đổi thứ tự lifecycle mà ứng dụng mong đợi.

## 3. ApplicationPreparedEvent là gì?

`ApplicationPreparedEvent` cũng thuộc package `org.springframework.boot.context.event`. Event được phát khi `SpringApplication` đã chuẩn bị xong `ApplicationContext` và context sẵn sàng để refresh.

Tại thời điểm này:

- Environment đã được chuẩn bị và gắn vào context.
- Application sources đã được nạp vào context.
- Các bean definitions ban đầu từ sources đã được đăng ký.
- Context chưa được refresh.
- Quá trình xử lý cấu hình đầy đủ, khởi tạo bean và gọi lifecycle callback chưa hoàn tất.

Listener nhận context qua `event.getApplicationContext()`.

Ví dụ:

~~~java
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;

public class ApplicationPreparedLogger
        implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationPreparedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("Prepared context: " + context.getId());
        System.out.println(
                "Initial bean definition count: "
                        + context.getBeanFactory().getBeanDefinitionCount()
        );
    }
}
~~~

Đoạn code đọc số lượng bean definitions để quan sát giai đoạn chuẩn bị. Con số thực tế phụ thuộc loại context, sources và initializer; không nên dùng một con số cố định làm điều kiện nghiệp vụ.

### 3.1. Application sources đã được nạp có nghĩa là gì?

Khi chạy:

~~~java
@SpringBootApplication
public class DemoApplication {
}
~~~

class `DemoApplication` được truyền cho `SpringApplication` như một primary source. Trong giai đoạn load, Spring đăng ký source class đó vào bean factory như một cấu hình cần xử lý.

Nhưng cần phân biệt **đăng ký source configuration** với **xử lý xong toàn bộ cấu hình**. Các bước như đọc `@Configuration`, xử lý `@ComponentScan`, tìm component và đăng ký các `@Bean` method thường diễn ra trong refresh, thông qua các bean factory post-processor như `ConfigurationClassPostProcessor`.

Vì vậy tại `ApplicationPreparedEvent`:

- Có thể quan sát các source bean definitions đã được nạp.
- Không nên giả định mọi component trong package scan đã được đăng ký.
- Không nên giả định mọi `@Bean` method đã được gọi.
- Không nên giả định service/repository/controller đã được instantiate.
- Không nên gọi bean nghiệp vụ để thực hiện công việc startup.

### 3.2. Prepared không đồng nghĩa với Ready

`ApplicationPreparedEvent` xảy ra trước refresh. Ứng dụng chưa hoàn tất việc tạo bean, chưa chắc web server đã được khởi động và chưa chạy `ApplicationRunner`/`CommandLineRunner`.

Nếu mục tiêu là thực hiện một hành động sau khi toàn bộ context đã refresh, hãy xem `ApplicationStartedEvent`, `ApplicationReadyEvent` hoặc lifecycle API tương ứng thay vì dùng prepared event.

## 4. So sánh trực tiếp hai event

| Tiêu chí | ApplicationContextInitializedEvent | ApplicationPreparedEvent |
| --- | --- | --- |
| Context đã được tạo | Có | Có |
| Environment đã gắn vào context | Có | Có |
| ApplicationContextInitializer đã chạy | Có | Có |
| Application sources đã được nạp | Chưa | Có |
| Source bean definitions ban đầu đã đăng ký | Chưa qua bước load sources | Có |
| Component scan đã hoàn tất | Chưa | Chưa thể giả định; thường xử lý trong refresh |
| `@Bean` methods đã được gọi | Chưa | Chưa thể giả định |
| Context đã refresh | Chưa | Chưa |
| Singleton eager thông thường đã sẵn sàng | Chưa | Chưa |
| Phù hợp để quan sát | Context sau initializer | Context sau khi load sources |
| Extension point để thay đổi context | ApplicationContextInitializer | Thường dùng initializer hoặc bean factory post-processor phù hợp |

Có thể ghi nhớ theo hai câu:

- `ApplicationContextInitializedEvent`: context đã được tạo và initializer đã chạy; nguồn cấu hình ứng dụng chưa được nạp.
- `ApplicationPreparedEvent`: nguồn cấu hình đã được nạp; context đang chờ refresh.

## 5. Vì sao listener phải được đăng ký trước khi context tạo bean?

Đây là điểm quan trọng khi xử lý hai event rất sớm.

Một listener triển khai `ApplicationListener<ApplicationContextInitializedEvent>` hoặc `ApplicationListener<ApplicationPreparedEvent>` phải được Spring Boot biết **trước khi các event tương ứng được phát**.

Cách đơn giản là đăng ký trực tiếp trên `SpringApplication`:

~~~java
import org.springframework.boot.SpringApplication;

public class ApplicationLauncher {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(
                new ContextInitializedLogger(),
                new ApplicationPreparedLogger()
        );

        application.run(args);
    }
}
~~~

`addListeners(...)` nhận các `ApplicationListener`. Khi Spring Boot phát các event startup, listener đã được đăng ký nên có thể nhận event đúng thời điểm.

Đây là cách phù hợp để minh họa và cũng hữu ích khi launcher cần kiểm soát listener.

### 5.1. Đăng ký qua META-INF/spring.factories

Một thư viện có thể muốn tự đăng ký listener khi được đưa vào classpath. Với Spring Boot, application listeners có thể được khai báo trong file:

~~~text
META-INF/spring.factories
~~~

Ví dụ nội dung:

~~~properties
org.springframework.context.ApplicationListener=\
com.acme.bootstrap.ContextInitializedLogger,\
com.acme.bootstrap.ApplicationPreparedLogger
~~~

File này nằm trong resource của JAR thư viện. Spring Boot sử dụng cơ chế SpringFactoriesLoader để phát hiện các listener được liệt kê.

Lưu ý về phiên bản:

- Spring Boot 3 dùng `AutoConfiguration.imports` để đăng ký auto-configuration classes.
- `spring.factories` vẫn có vai trò với một số extension point như `ApplicationListener` và `ApplicationContextInitializer`.
- Không chuyển nhầm listener sang `AutoConfiguration.imports`; file đó dành cho danh sách auto-configuration.

Một thư viện nên cân nhắc kỹ side effect khi tự đăng ký startup listener. Listener được nạp trên classpath có thể chạy trong mọi ứng dụng dùng thư viện, kể cả khi ứng dụng không mong muốn hành vi đó.

### 5.2. Đăng ký qua SpringApplicationBuilder

Nếu dùng builder:

~~~java
new SpringApplicationBuilder(DemoApplication.class)
        .listeners(
                new ContextInitializedLogger(),
                new ApplicationPreparedLogger()
        )
        .run(args);
~~~

Cách này tiện khi launcher đang cấu hình parent/child context hoặc cần chuỗi cấu hình fluent. Với một ứng dụng đơn giản, `SpringApplication.addListeners` cũng đủ rõ.

## 6. Vì sao @EventListener trong bean không nhận hai event này?

Bạn có thể thử:

~~~java
@Component
public class StartupEventBean {

    @EventListener
    public void onContextInitialized(
            ApplicationContextInitializedEvent event) {
        // Thường không nhận được event rất sớm này.
    }

    @EventListener
    public void onApplicationPrepared(ApplicationPreparedEvent event) {
        // Cũng không nhận được event trước refresh.
    }
}
~~~

Lý do là `@EventListener` dựa trên bean và cơ chế xử lý annotation của Spring context. Bean chứa method này chỉ được phát hiện/khởi tạo trong quá trình refresh. Event `ApplicationContextInitializedEvent` và `ApplicationPreparedEvent` đã được phát trước thời điểm đó.

Cùng một nguyên tắc áp dụng cho class có `@Component` và implement `ApplicationListener`: nếu class chỉ được phát hiện nhờ component scan, nó cũng chưa sẵn sàng để nhận event trước khi component scan diễn ra.

Hãy phân biệt hai nhóm:

| Cách đăng ký | Có thể nhận event trước refresh? | Lý do |
| --- | --- | --- |
| `SpringApplication.addListeners(...)` | Có | Listener được đăng ký trước khi run |
| `META-INF/spring.factories` với ApplicationListener | Có | Listener được Spring Boot nạp trong giai đoạn chuẩn bị |
| `@Component` implement ApplicationListener | Không nên dựa vào | Component scan diễn ra trong refresh |
| Bean có method `@EventListener` | Không | Listener method được đăng ký từ bean trong context |
| `ApplicationContextInitializer` | Không phải listener event | Là callback được gọi trực tiếp trong giai đoạn chuẩn bị context |

`@EventListener` rất phù hợp với event phát trong lúc ứng dụng đã hoạt động, chẳng hạn domain/application event, hoặc event context mà listener bean đã được đăng ký trước khi event xảy ra. Với early startup event, hãy dùng listener đăng ký sớm.

## 7. ApplicationContextInitializer khác gì ApplicationContextInitializedEvent?

Hai tên rất giống nhau nhưng một cái là **callback mở rộng**, một cái là **event thông báo**.

`ApplicationContextInitializer`:

- Là interface có method `initialize(context)`.
- Được SpringApplication gọi trong quá trình chuẩn bị context.
- Có thể điều chỉnh context trước khi application sources được nạp.
- Có thể được đăng ký bằng `SpringApplication.addInitializers(...)` hoặc cơ chế factories phù hợp.

`ApplicationContextInitializedEvent`:

- Là application event được phát sau khi các initializer đã chạy.
- Cho phép listener quan sát trạng thái context ở mốc đó.
- Không phải callback mà Spring gọi để yêu cầu listener sửa context.

Ví dụ initializer:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class StartupContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.setId("demo-application-context");
        // Có thể đăng ký thêm bean definition hoặc chuẩn bị context
        // theo yêu cầu bootstrap.
    }
}
~~~

Đăng ký:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.addInitializers(new StartupContextInitializer());
application.addListeners(new ContextInitializedLogger());

application.run(args);
~~~

Khi `ApplicationContextInitializedEvent` được phát, listener có thể quan sát context sau khi initializer đã thực hiện công việc.

### 7.1. Khi nào dùng initializer?

Dùng `ApplicationContextInitializer` nếu bạn cần:

- Thay đổi hoặc chuẩn bị context trước khi load application sources.
- Đăng ký một bean definition ở giai đoạn rất sớm.
- Thiết lập một phần cấu hình context trước refresh.
- Tích hợp một framework cần callback chuẩn trong quá trình bootstrap.

Dùng `ApplicationContextInitializedEvent` nếu bạn cần:

- Ghi nhận mốc context đã được tạo.
- Kiểm tra Environment sau khi initializer chạy.
- Thu thập thông tin chẩn đoán.
- Phát tín hiệu cho một listener hạ tầng khác đang được đăng ký sớm.

Không dùng event listener chỉ để làm việc mà initializer đã có hợp đồng rõ ràng.

## 8. ApplicationPreparedEvent khác BeanFactoryPostProcessor như thế nào?

`ApplicationPreparedEvent` cho biết context đã sẵn sàng refresh và application sources đã được nạp. Nhưng nếu mục tiêu là can thiệp vào bean definitions hoặc metadata trước khi bean được tạo, Spring có extension point chuyên biệt hơn.

### 8.1. BeanFactoryPostProcessor

`BeanFactoryPostProcessor` làm việc với bean factory sau khi các bean definitions đã được nạp, nhưng trước khi singleton thông thường được khởi tạo.

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.stereotype.Component;

@Component
public class DefinitionInspector implements BeanFactoryPostProcessor {

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        String[] names = beanFactory.getBeanDefinitionNames();

        for (String name : names) {
            // Kiểm tra metadata của bean definition.
        }
    }
}
~~~

Ví dụ minh họa vị trí lifecycle. Trong thực tế, không nên thêm processor chỉ để ghi log mọi bean; có thể dùng condition report, Actuator hoặc công cụ chẩn đoán phù hợp.

### 8.2. BeanDefinitionRegistryPostProcessor

Nếu cần đăng ký thêm bean definitions trước khi bean factory post-processors thông thường chạy, có thể dùng `BeanDefinitionRegistryPostProcessor`:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public class ExtraDefinitionRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {
        // Đăng ký BeanDefinition bổ sung.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        // Xử lý bean factory sau giai đoạn registry.
    }
}
~~~

Đây là extension point chuyên dụng cho bean definition registry. Việc đăng ký processor cần được thực hiện theo đúng lifecycle để Spring phát hiện nó trong refresh; không nên tùy tiện tạo processor bằng cách gọi `getBean` trong `ApplicationPreparedEvent`.

### 8.3. Chọn đúng công cụ

| Mục tiêu | Cơ chế phù hợp |
| --- | --- |
| Thay đổi context trước khi sources được nạp | `ApplicationContextInitializer` |
| Quan sát context sau khi initializer chạy | `ApplicationContextInitializedEvent` |
| Quan sát context sau khi sources được nạp, trước refresh | `ApplicationPreparedEvent` |
| Chỉnh sửa bean definitions/metadata trong refresh | `BeanDefinitionRegistryPostProcessor` hoặc `BeanFactoryPostProcessor` |
| Tạo bean theo điều kiện classpath/property | Auto-configuration và condition |
| Thực hiện tác vụ sau khi context refresh | `ApplicationStartedEvent`, runner hoặc lifecycle phù hợp |
| Thực hiện tác vụ sau khi runners hoàn tất | `ApplicationReadyEvent` |

## 9. Quan sát bean definitions trong ApplicationPreparedEvent

Một listener có thể đọc metadata từ bean factory mà không yêu cầu tạo bean:

~~~java
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;

public class BeanDefinitionCountListener
        implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationPreparedEvent event) {
        var beanFactory = event.getApplicationContext().getBeanFactory();

        System.out.println(
                "Bean definitions at prepared stage: "
                        + beanFactory.getBeanDefinitionCount()
        );

        for (String name : beanFactory.getBeanDefinitionNames()) {
            System.out.println("Definition: " + name);
        }
    }
}
~~~

Đây là thao tác đọc metadata. Danh sách ở giai đoạn này có thể chưa phản ánh kết quả cuối cùng của component scan và configuration class processing.

Nếu muốn biết chính xác component scan đã đăng ký bean nào, cần quan sát sau khi các configuration class được xử lý trong refresh, hoặc kiểm tra context sau refresh. Đừng dùng số lượng definition tại prepared event làm số lượng bean cuối cùng.

### 9.1. Vì sao không gọi getBean ở giai đoạn này?

Gọi `getBean` trước refresh có thể:

- Không tìm thấy bean vì definition chưa được đăng ký.
- Kích hoạt khởi tạo sớm ngoài lifecycle thông thường.
- Tạo dependency graph chưa hoàn chỉnh.
- Làm các post-processor hoặc proxy chưa được áp dụng như mong đợi.
- Gây lỗi khi bean cần một hạ tầng chỉ được chuẩn bị trong refresh.

Nếu cần đọc metadata, dùng `getBeanDefinition` hoặc các API của bean factory ở mức phù hợp. Nếu cần sử dụng object thực, hãy chờ giai đoạn sau refresh.

## 10. Quan hệ với các event startup khác

Hai event đang học nằm trong chuỗi nhiều event. Biết các mốc kế cận giúp chọn đúng thời điểm cho một công việc.

| Event | Khi nào được phát | Dùng để làm gì |
| --- | --- | --- |
| `ApplicationStartingEvent` | Khi SpringApplication bắt đầu chạy | Ghi nhận startup rất sớm |
| `ApplicationEnvironmentPreparedEvent` | Environment đã được chuẩn bị | Quan sát môi trường trước khi context được tạo |
| `ApplicationContextInitializedEvent` | Context đã tạo và initializer đã chạy | Quan sát context sau initializer |
| `ApplicationPreparedEvent` | Sources đã nạp, trước refresh | Quan sát context chờ refresh |
| `ContextRefreshedEvent` | Context refresh hoàn tất | Phản ứng với lifecycle refresh của context |
| `WebServerInitializedEvent` | Web server đã được khởi tạo | Lấy thông tin server như port thực tế |
| `ApplicationStartedEvent` | Sau refresh, trước runners | Biết context đã khởi động |
| `ApplicationReadyEvent` | Sau runners | Biết ứng dụng hoàn tất startup |
| `ApplicationFailedEvent` | Startup thất bại | Ghi nhận lỗi khởi động |

Các event có thể được phát trong cùng một tiến trình startup nhưng phục vụ mục đích khác nhau. Ví dụ, nếu cần lấy port thực tế của embedded server, `ApplicationPreparedEvent` quá sớm; hãy quan sát `WebServerInitializedEvent`. Nếu cần chạy tác vụ sau khi runner hoàn tất, hãy dùng `ApplicationReadyEvent`.

### 10.1. ContextRefreshedEvent không phải ApplicationPreparedEvent

`ContextRefreshedEvent` được phát khi context đã refresh. Đến thời điểm này, configuration class processing và bean factory post-processing đã diễn ra, các singleton eager thông thường đã được khởi tạo và các initialization callback đã chạy.

`ApplicationPreparedEvent` chỉ báo context sẵn sàng để refresh. Nó không bảo đảm các bean nghiệp vụ đã có thể sử dụng.

### 10.2. ApplicationStartedEvent và ApplicationReadyEvent

`ApplicationStartedEvent` được phát sau khi context refresh xong nhưng trước khi các `ApplicationRunner` và `CommandLineRunner` chạy.

`ApplicationReadyEvent` được phát sau khi các runner hoàn tất. Đây thường là mốc phù hợp nếu công việc cần các bean đã khởi tạo và startup runners đã chạy xong.

Không dùng prepared event cho công việc cần database client, repository, web server hoặc các service đã hoàn tất khởi tạo.

## 11. Ví dụ hoàn chỉnh: đăng ký và ghi log hai event

Ví dụ gồm một ứng dụng Boot tối giản và hai listener độc lập.

### 11.1. Application class

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.addListeners(
                new ContextInitializedLogger(),
                new ApplicationPreparedLogger()
        );

        application.run(args);
    }
}
~~~

### 11.2. Listener cho ApplicationContextInitializedEvent

~~~java
package com.example.demo.bootstrap;

import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.context.ApplicationListener;

public class ContextInitializedLogger
        implements ApplicationListener<ApplicationContextInitializedEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextInitializedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("[ContextInitialized]");
        System.out.println("Context id: " + context.getId());
        System.out.println(
                "Profiles: "
                        + String.join(
                                ",",
                                context.getEnvironment().getActiveProfiles()
                        )
        );
    }
}
~~~

### 11.3. Listener cho ApplicationPreparedEvent

~~~java
package com.example.demo.bootstrap;

import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;

public class ApplicationPreparedLogger
        implements ApplicationListener<ApplicationPreparedEvent> {

    @Override
    public void onApplicationEvent(ApplicationPreparedEvent event) {
        var context = event.getApplicationContext();

        System.out.println("[ApplicationPrepared]");
        System.out.println("Context id: " + context.getId());
        System.out.println(
                "Initial definitions: "
                        + context.getBeanFactory().getBeanDefinitionCount()
        );
    }
}
~~~

Hai class listener không cần `@Component` vì được tạo và đăng ký trực tiếp trong launcher. Chúng có thể nhận event trước khi Spring tạo các bean ứng dụng.

### 11.4. Kết quả log minh họa

~~~text
[ContextInitialized]
Context id: application
Profiles: local

[ApplicationPrepared]
Context id: application
Initial definitions: 1
...
Started DemoApplication
~~~

Số lượng bean definition trong ví dụ chỉ là giá trị minh họa; nó thay đổi theo source, initializer và phiên bản. Thứ tự hai event mới là điều cần quan sát: context initialized được phát trước application prepared.

## 12. Kiểm thử thứ tự hai event

Có thể kiểm tra hai event bằng một `SpringApplication` thật trong test. Không cần khởi động web server nếu chỉ kiểm tra startup lifecycle; đặt web type là `NONE` giúp test gọn hơn.

Ví dụ JUnit 5:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationContextInitializedEvent;
import org.springframework.boot.context.event.ApplicationPreparedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.ConfigurableApplicationContext;

class StartupEventsTest {

    @Configuration(proxyBeanMethods = false)
    static class TestApplication {
    }

    @Test
    void publishesContextInitializedBeforeApplicationPrepared() {
        List<String> observed = new ArrayList<>();

        SpringApplication application =
                new SpringApplication(TestApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.addListeners(
                (ApplicationListener<ApplicationContextInitializedEvent>)
                        event -> observed.add("context-initialized"),
                (ApplicationListener<ApplicationPreparedEvent>)
                        event -> observed.add("application-prepared")
        );

        try (ConfigurableApplicationContext context = application.run()) {
            assertThat(context.isActive()).isTrue();
        }

        assertThat(observed).containsSubsequence(
                "context-initialized",
                "application-prepared"
        );
    }
}
~~~

Test minh họa việc đăng ký listener trước khi gọi `run` và xác nhận thứ tự phát event. Dự án cần các dependency test tương ứng, chẳng hạn Spring Boot test starter để có JUnit và AssertJ theo dependency management.

### 12.1. Test initializer chạy trước ContextInitializedEvent

Có thể bổ sung initializer ghi một dấu mốc:

~~~java
application.addInitializers(context -> {
    context.getEnvironment().setActiveProfiles("test");
});
~~~

Trong listener `ApplicationContextInitializedEvent`, đọc active profiles và xác nhận profile `test` đã được thiết lập.

Bài test này xác nhận thứ tự callback initializer và event. Nếu thay đổi Environment cho mục tiêu cấu hình production, hãy chọn đúng extension point để thay đổi property/profile; ví dụ trên chủ yếu minh họa lifecycle.

### 12.2. Test ApplicationPreparedEvent không phải nơi kiểm tra bean sẵn sàng

Đừng viết test gọi `context.getBean(MyService.class)` trong listener prepared rồi xem đó là cách xác nhận startup. Test như vậy có thể ép tạo bean quá sớm và không còn kiểm tra lifecycle thông thường.

Nếu mục tiêu là kiểm tra bean sau refresh, hãy lấy bean từ context sau khi `application.run()` hoàn tất. Nếu mục tiêu là kiểm tra bean definitions, dùng API bean factory hoặc kiểm thử `BeanFactoryPostProcessor`.

## 13. Dùng early event để chẩn đoán startup

Hai event rất hữu ích khi cần biết ứng dụng đã tiến đến mốc nào trước khi lỗi xảy ra.

### 13.1. Ghi lại environment đã chuẩn bị

Ở `ApplicationContextInitializedEvent`, có thể ghi:

- Context ID.
- Active profiles.
- Default profiles.
- Một số property không nhạy cảm.
- Tên môi trường hoặc chế độ khởi động.

Không log password, token, private key hoặc toàn bộ Environment vì có thể làm lộ secret.

### 13.2. Ghi lại source definitions ban đầu

Ở `ApplicationPreparedEvent`, có thể ghi:

- Context ID.
- Bean definition count ban đầu.
- Danh sách primary source nếu ứng dụng tự quản lý.
- Thông tin cấu hình khởi động không nhạy cảm.
- Mốc thời gian trước khi refresh.

Dữ liệu này giúp phân biệt lỗi xảy ra trước khi load source, trong lúc refresh hay sau khi ứng dụng đã sẵn sàng.

### 13.3. Đừng dùng early listener thay thế condition report

Nếu cần biết vì sao auto-configuration không match, condition evaluation report hoặc debug mode của Spring Boot thường hữu ích hơn việc tự liệt kê bean definitions ở prepared event.

Early listener có thể ghi nhận mốc startup và môi trường, nhưng không tự cung cấp kết luận đầy đủ về mọi condition được đánh giá trong refresh.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Listener không nhận ApplicationContextInitializedEvent | Listener chỉ được đăng ký bằng component scan hoặc @EventListener | Đăng ký trước run bằng addListeners hoặc spring.factories |
| Listener không nhận ApplicationPreparedEvent | Bean listener chưa tồn tại khi event đã phát | Dùng ApplicationListener được đăng ký sớm |
| Gọi getBean trong ContextInitializedEvent thất bại | Application sources chưa được nạp | Dùng initializer hoặc chờ giai đoạn sau refresh |
| Gọi service trong ApplicationPreparedEvent lỗi | Context chưa refresh, bean có thể chưa được tạo | Chờ ApplicationStartedEvent/Ready hoặc dùng extension point đúng |
| Không thấy component scan bean trong prepared event | Configuration class processing diễn ra trong refresh | Quan sát sau refresh hoặc dùng bean factory post-processor |
| Nghĩ ApplicationPreparedEvent nghĩa là server đã mở port | Nhầm prepared với web server initialized | Theo dõi WebServerInitializedEvent |
| Listener được gọi hai lần trong ứng dụng nhiều context | Có parent/child context hoặc nhiều SpringApplication | Ghi context ID và xác định event thuộc context nào |
| Listener gây startup chậm | Thực hiện I/O hoặc công việc nặng trong callback sớm | Chuyển công việc sang lifecycle/runner phù hợp |
| Test không ổn định do listener static | Dùng shared mutable state giữa lần chạy context | Dùng state riêng cho từng test và đóng context |
| Thay đổi property không có hiệu lực | Can thiệp sau giai đoạn property binding/condition mong đợi hoặc sai thứ tự | Dùng EnvironmentPostProcessor hoặc cấu hình sớm hơn |

### 14.1. Listener không được phát hiện

Kiểm tra listener đã được đăng ký trước `SpringApplication.run` hay chưa. Nếu dùng `spring.factories`, xác nhận file nằm đúng đường dẫn resource trong JAR và key là `org.springframework.context.ApplicationListener`.

Không đặt listener trong package scan rồi kỳ vọng nó nhận event được phát trước component scan.

### 14.2. Gọi bean quá sớm

`ApplicationContextInitializedEvent` và `ApplicationPreparedEvent` đều trước refresh. Không dùng chúng để truy cập repository, service hoặc client cần bean lifecycle hoàn tất.

Nếu công việc cần object, dùng runner hoặc event sau refresh. Nếu công việc chỉ cần metadata, đọc bean definition thay vì instantiate bean.

### 14.3. Nhầm nhiều context

Ứng dụng có thể tạo nhiều context, ví dụ parent/child hoặc test context riêng. Listener đã đăng ký ở cấp SpringApplication có thể quan sát event của quá trình tạo context tương ứng. Khi log, nên ghi context ID hoặc identity để tránh tưởng một event được phát trùng trong cùng một context.

## 15. Lựa chọn extension point theo thời điểm

Hãy bắt đầu từ câu hỏi “tôi cần làm việc gì và cần thực hiện trước mốc nào?”:

| Nhu cầu | Thời điểm/cơ chế nên dùng |
| --- | --- |
| Thay đổi Environment trước khi tạo context | `EnvironmentPostProcessor` |
| Chuẩn bị context trước khi load application sources | `ApplicationContextInitializer` |
| Quan sát context sau khi initializer chạy | `ApplicationContextInitializedEvent` |
| Quan sát context sau khi load sources, trước refresh | `ApplicationPreparedEvent` |
| Đăng ký/điều chỉnh bean definitions trong refresh | `BeanDefinitionRegistryPostProcessor` |
| Chỉnh metadata bean trước khi tạo singleton | `BeanFactoryPostProcessor` |
| Phản ứng khi context refresh xong | `ContextRefreshedEvent` |
| Chạy tác vụ sau khi context khởi động, trước runners | `ApplicationStartedEvent` |
| Chạy tác vụ sau khi runners hoàn tất | `ApplicationReadyEvent` hoặc runner phù hợp |
| Quản lý start/stop thành phần theo phase | `SmartLifecycle` |

Một số extension point được gọi ở thời điểm rất sớm nên có thể ảnh hưởng lớn đến startup. Hãy chọn cơ chế nhỏ nhất đáp ứng yêu cầu và giữ công việc callback ngắn, dễ kiểm soát lỗi.

## 16. Bài tập thực hành

### Bài tập 1 — Ghi nhận hai event

Tạo hai class implement `ApplicationListener` cho `ApplicationContextInitializedEvent` và `ApplicationPreparedEvent`. Đăng ký bằng `SpringApplication.addListeners`. Chạy ứng dụng và ghi lại thứ tự xuất hiện.

### Bài tập 2 — Quan sát initializer

Tạo `ApplicationContextInitializer` để đặt một profile hoặc context ID. Trong `ApplicationContextInitializedEvent`, đọc lại giá trị vừa thiết lập. Giải thích vì sao listener quan sát được thay đổi đó.

### Bài tập 3 — So sánh bean definitions

Trong `ApplicationPreparedEvent`, ghi số lượng bean definitions ban đầu. Sau khi `application.run()` hoàn tất, ghi lại số lượng definitions. Giải thích vì sao hai giá trị có thể khác nhau.

### Bài tập 4 — Chứng minh @EventListener đến quá muộn

Tạo một component có method `@EventListener` nhận `ApplicationPreparedEvent`. So sánh với một listener được thêm bằng `SpringApplication.addListeners`. Quan sát listener nào nhận event và giải thích lifecycle component scan.

### Bài tập 5 — Chọn extension point

Cho ba yêu cầu:

1. Thêm property source trước khi condition của auto-configuration được đánh giá.
2. Đăng ký một bean definition trước refresh.
3. Ghi log khi context đã refresh và service có thể được sử dụng.

Chọn extension point cho từng yêu cầu và giải thích vì sao hai early event không phải lựa chọn phù hợp cho mọi công việc.

## 17. Ghi nhớ

`ApplicationContextInitializedEvent` được phát sau khi Spring Boot tạo `ApplicationContext`, gắn Environment và gọi các `ApplicationContextInitializer`, nhưng trước khi application sources được nạp. Nó phù hợp để quan sát context sau initializer và ghi nhận thông tin khởi động sớm.

`ApplicationPreparedEvent` được phát sau khi application sources đã được nạp và context sẵn sàng refresh. Các source bean definitions ban đầu đã được đăng ký, nhưng context chưa refresh; configuration class processing, component scan, `@Bean` registration và khởi tạo singleton thông thường chưa hoàn tất. Nó phù hợp để quan sát mốc ngay trước refresh, không phải để gọi service nghiệp vụ.

Hai event phải được lắng nghe bằng `ApplicationListener` đăng ký sớm qua `SpringApplication.addListeners` hoặc cơ chế `spring.factories`. Bean chỉ được tìm thấy trong component scan và method `@EventListener` thường được đăng ký quá muộn để nhận chúng.

Nếu cần thay đổi context, hãy dùng `ApplicationContextInitializer`; nếu cần thay đổi bean definitions trong refresh, hãy dùng bean factory post-processor; nếu cần dùng service đã sẵn sàng, hãy đợi sau refresh hoặc sau runners theo yêu cầu. Chọn đúng mốc lifecycle giúp startup dễ quan sát, dễ kiểm thử và tránh tạo bean quá sớm.
