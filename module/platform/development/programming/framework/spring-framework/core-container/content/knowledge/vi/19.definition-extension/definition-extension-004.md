# Đăng ký post-processor tự động và bằng mã trong Spring Core Container

## 1. Mục tiêu: mở rộng container đúng pha, đúng cách đăng ký

Spring IoC Container cung cấp những **post-processor** để ứng dụng hoặc framework tích hợp có thể tham gia vào quá trình đăng ký định nghĩa, cấu hình metadata và khởi tạo bean. Có hai cách tổ chức thường gặp:

1. **Tự động phát hiện (auto-detection):** khai báo post-processor thành Spring bean bên trong một `ApplicationContext`. Context phát hiện type tương ứng, đăng ký và gọi tại đúng giai đoạn của `refresh()`.
2. **Đăng ký bằng mã (programmatic registration):** tạo processor và đưa trực tiếp vào API container trước khi bean được tạo, hoặc gọi callback bằng tay khi đang dùng một `BeanFactory` thuần.

Điểm khác biệt **không chỉ ở cú pháp**. Chúng tác động tới **thứ tự thực thi**, **thời điểm đăng ký**, **phạm vi bean có thể được xử lý** và **các processor nào Spring có thể tự khám phá**.

### Ba interface chủ chốt

| Extension point | Phạm vi thay đổi | Callback quan trọng | Thời điểm thông thường |
| --- | --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | **Registry chứa bean definitions**: thêm/xóa/điều chỉnh definition sớm | `postProcessBeanDefinitionRegistry(BeanDefinitionRegistry)`, kế thừa `postProcessBeanFactory(...)` | Trước pha xử lý metadata thông thường; trước tạo regular beans |
| `BeanFactoryPostProcessor` (BFPP) | **Metadata/bean definitions**, chưa phải object đã tạo | `postProcessBeanFactory(ConfigurableListableBeanFactory)` | Sau khi bean definitions được chuẩn bị, trước tạo regular bean instances |
| `BeanPostProcessor` (BPP) | **Bean instance** đã/đang được khởi tạo; có thể kiểm tra hoặc trả proxy | `postProcessBeforeInitialization(Object,String)` và `postProcessAfterInitialization(Object,String)` | Quanh các init callbacks của mỗi bean được tạo sau khi BPP đã đăng ký |

`BeanDefinitionRegistryPostProcessor` kế thừa `BeanFactoryPostProcessor` nên có thêm callback metadata thông thường. Đây không phải là hai processor không liên quan.

**Một câu dễ nhớ:** registry processor thay đổi *những bean nào có định nghĩa*; bean-factory processor thay đổi *cách bean được mô tả/cấu hình*; bean post-processor thay đổi/bao bọc *instance được tạo từ cấu hình ấy*.

## 2. Luồng khởi động tiêu biểu của ApplicationContext

~~~text
ApplicationContext.refresh()
  |
  +-- Load/parse bean definitions
  |      └-- ví dụ ConfigurationClassPostProcessor đọc @Configuration
  |
  +-- Invoke BeanDefinitionRegistryPostProcessors
  |      └-- có thể đăng ký thêm bean definitions
  |
  +-- Invoke BeanFactoryPostProcessors
  |      └-- thay metadata/property values, không tạo bean nghiệp vụ
  |
  +-- Detect + instantiate + register BeanPostProcessors
  |      └-- nhóm này được dựng sớm để xử lý các bean về sau
  |
  +-- Pre-instantiate regular non-lazy singleton beans
  |      ├-- constructor/factory method
  |      ├-- dependency/property injection
  |      ├-- BPP.beforeInitialization()
  |      ├-- @PostConstruct, InitializingBean, custom init
  |      └-- BPP.afterInitialization() → có thể trả proxy
  |
  +-- Finish initialization, lifecycle/events của context
  |
  +-- ApplicationContext usable
~~~

Đây là **sơ đồ khái niệm**, không phải danh sách mọi nội bộ `refresh()` hay khẳng định mọi BeanPostProcessor sẽ chạy đúng một lần trên mọi object trong mọi tình huống. `@PostConstruct` được xử lý bởi một BeanPostProcessor thích hợp, nên thứ tự tương đối của nó với **các BPP tùy biến trước khởi tạo** phụ thuộc ordering của processor. Các bean đặc biệt như `FactoryBean`, scoped proxy, bean definition của processor và cơ chế early reference có thêm chi tiết.

Không được lấy sơ đồ trên để cho rằng mọi bean có `@Lazy` hoặc scope `prototype` đều phải được tạo trước khi context refresh hoàn tất: chúng thường được tạo khi cần; lúc đó các BPP đã đăng ký có thể tiếp tục xử lý instance mới.

## 3. BeanFactoryPostProcessor: xử lý định nghĩa, không xử lý instance

`BeanFactoryPostProcessor` có hợp đồng:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

public final class LabelDefinitionPatch implements BeanFactoryPostProcessor {
    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        if (beanFactory.containsBeanDefinition("messageBean")) {
            beanFactory.getBeanDefinition("messageBean")
                    .getPropertyValues()
                    .add("label", "configured");
        }
    }
}
~~~

Đoạn trên là một class Java minh họa; nó **sửa property value trên BeanDefinition**, chưa gọi setter trên bean instance. Nếu class `MessageBean` có setter `setLabel(String)`, property value được Spring áp dụng trong quá trình tạo bean sau đó.

BFPP có thể thêm metadata, thay property values hoặc kiểm tra định nghĩa mà không cần tạo bean. Một số BFPP tích hợp trong Spring giải quyết placeholder/configuration metadata theo cơ chế riêng.

**Không dùng `beanFactory.getBean("messageBean")` trong BFPP chỉ để thay giá trị của bean:** điều này ép tạo bean **trước khi quá trình đăng ký BPP/auto-proxying hoàn tất**, có thể gây thiếu xử lý AOP, callback annotation hoặc tạo bean dependency quá sớm. Muốn sửa object, dùng `BeanPostProcessor` hoặc injection/configuration phù hợp.

Nếu BeanDefinition mới cần được **đăng ký** từ sớm, đặc biệt để processor khác cũng quan sát nó, `BeanDefinitionRegistryPostProcessor` thường phù hợp hơn BFPP thuần.

## 4. BeanDefinitionRegistryPostProcessor: đăng ký thêm BeanDefinition

`BeanDefinitionRegistryPostProcessor` có callback mở rộng ở pha registry:

~~~java
import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.support.RootBeanDefinition;

public final class ExtraTypeRegistrar
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) throws BeansException {
        if (!registry.containsBeanDefinition("extraService")) {
            registry.registerBeanDefinition(
                    "extraService",
                    new RootBeanDefinition(ExtraService.class));
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory)
            throws BeansException {
        // Có thể điều chỉnh metadata sau pha registry nếu cần.
    }
}
~~~

Đoạn này là ví dụ class minh họa, `ExtraService` là một Java type cần được định nghĩa; không phải ứng dụng standalone. Ưu điểm: Spring có thể xử lý bean definitions được thêm **trước regular bean instantiation**. Đây cũng là lớp extension point mà Spring dùng cho các processor xử lý cấu hình, chẳng hạn `ConfigurationClassPostProcessor` (một BeanDefinitionRegistryPostProcessor có các vai trò bổ sung).

**Quy tắc:** registry callback nên làm việc trên `BeanDefinitionRegistry`, còn factory callback nên làm việc trên metadata; không gọi các bean nghiệp vụ chỉ để biết có nên đăng ký definition.

## 5. BeanPostProcessor: xử lý một instance trước/sau init

`BeanPostProcessor` được gọi khi Spring tạo các bean phù hợp sau thời điểm processor đã được đăng ký. Hai method cơ bản:

~~~java
import org.springframework.beans.factory.config.BeanPostProcessor;

public final class TaggingPostProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if ("messageBean".equals(beanName)
                && bean instanceof MessageBean message) {
            message.setTag("POST");
        }
        return bean;
    }
}
~~~

Đoạn trên là class minh họa, `MessageBean` phải có setter phù hợp. BPP nhận **bean instance và beanName**, không phải BeanDefinition. Trong pha `postProcessAfterInitialization`, BPP có thể **trả một object khác** (proxy/wrapper) thay cho target ban đầu; đó là cơ sở của nhiều tính năng AOP.

Không được nhầm tên API: `postProcessBeanFactory(...)` không có `beanName` và sửa metadata; `postProcessAfterInitialization(...)` sửa/wrap instance.

### BPP và @PostConstruct

Spring xử lý `@PostConstruct` qua một BeanPostProcessor về lifecycle annotation. Do đó BPP tùy biến không được tự giả định mọi `beforeInitialization` đều chạy trước `@PostConstruct`. Thứ tự tương đối tùy danh sách/ordering của BPP.

Phần lớn business code không cần tự tạo BPP. Đây là extension point dành cho framework logic cắt ngang nhiều bean như proxy, annotation convention, validation hạ tầng hoặc adapter.

## 6. Đăng ký tự động khi dùng ApplicationContext

Trong `ApplicationContext`, có thể khai báo BFPP/BDRPP/BPP thành bean qua `@Component` + component scanning, XML bean definitions hoặc `@Bean` trên Java configuration.

~~~java
@Configuration(proxyBeanMethods = false)
public class ExtensionConfig {
    @Bean
    static BeanFactoryPostProcessor metadataProcessor() {
        return beanFactory -> {
            // Đọc/sửa metadata (không gọi getBean nghiệp vụ).
        };
    }

    @Bean
    static BeanPostProcessor instanceProcessor() {
        return new TaggingPostProcessor();
    }
}
~~~

Đây là cấu hình minh họa, cần import `@Configuration`, `@Bean`, `BeanFactoryPostProcessor`, `BeanPostProcessor` và class `TaggingPostProcessor`. Khi config được đăng ký và context refresh, Spring phát hiện hai bean processor qua type rồi đăng ký vào pipeline phù hợp.

**Các điểm phải đúng:**

- **Bean definition** của processor phải được đưa vào context trước giai đoạn phát hiện tương ứng. Có thể thông qua `@ComponentScan` hoặc `register(Config.class)` với Java config.
- Một `@Bean` trả về BPP nên khai báo **return type nhận diện được là `BeanPostProcessor` hoặc implementation**, không dùng return type quá chung kiểu `Object` vì container cần phát hiện type trước khi tạo instance.
- Nên viết `@Bean static` cho BFPP và BPP, đặc biệt BFPP, để tránh buộc Spring tạo sớm instance `@Configuration` và các dependency của config.
- Không đặt `@Lazy` rồi kỳ vọng processor chỉ chạy khi người dùng gọi `getBean`: processors được context xử lý trong startup phase.
- Các post-processors thường được tạo rất sớm. Tránh inject business service nặng vào constructor của BPP/BDRPP/BFPP.

Đối với `BeanDefinitionRegistryPostProcessor`, có thể khai báo một `@Bean static BeanDefinitionRegistryPostProcessor` hoặc component tương ứng. Registry processing phải diễn ra trước khi phần lớn bean thường được tạo để những definitions mới có cơ hội tham gia lifecycle bình thường.

### Tại sao static @Bean quan trọng?

Ví dụ cấu hình **không nên ưu tiên**:

~~~java
@Configuration
public class BadConfig {
    @Autowired
    private DataSource dataSource;

    @Bean
    BeanFactoryPostProcessor metadataProcessor() {
        return factory -> { /* ... */ };
    }
}
~~~

Do BFPP phải được tạo **sớm**, method không static có thể khiến Spring phải tạo `BadConfig` trước khi các bước annotation processing thông thường hoàn tất. Những callback/annotation trên chính configuration class như `@Autowired`, `@PostConstruct` có nguy cơ bị bỏ qua; Spring có thể log INFO cảnh báo về non-static BFPP `@Bean` method.

Phiên bản nên dùng:

~~~java
@Configuration
public class GoodConfig {
    @Bean
    static BeanFactoryPostProcessor metadataProcessor() {
        return factory -> { /* ... */ };
    }
}
~~~

Không có lý do để truyền một `DataSource` nghiệp vụ vào processor chỉ nhằm đọc một BeanDefinition. Tránh ép phụ thuộc hạ tầng nặng tạo sớm.

## 7. Đăng ký BeanFactoryPostProcessor bằng mã trên ApplicationContext

Với `ConfigurableApplicationContext` (ví dụ `AnnotationConfigApplicationContext`), có thể thêm BFPP instance **trước `refresh()`**:

~~~java
var context = new AnnotationConfigApplicationContext();
context.register(AppConfig.class);
context.addBeanFactoryPostProcessor(new LabelDefinitionPatch());
context.refresh();
try {
    // Sử dụng bean đã được context tạo.
} finally {
    context.close();
}
~~~

Đây là ví dụ minh họa, cần class `AppConfig` và `LabelDefinitionPatch` hợp lệ. Cấu hình không tự refresh khi dùng constructor không tham số, cho phép thêm BFPP trước refresh.

Phân biệt hai thao tác:

- **Khai báo BFPP như một bean:** Spring tự phát hiện processor và gọi trong startup.
- **`addBeanFactoryPostProcessor(instance)`:** đưa thẳng processor instance vào danh sách của context để nó được gọi khi refresh; không bắt buộc có bean definition riêng cho processor instance.

Đừng gọi `addBeanFactoryPostProcessor` **sau khi `refresh()` đã xong** rồi kỳ vọng nó sửa những singleton đã tạo. API thêm vào danh sách không tự chạy lại toàn bộ pipeline, không tự hủy/tái tạo beans và không bảo đảm áp dụng hồi tố.

### Ordering trong trường hợp programmatic BFPP

Theo javadoc Spring, các `BeanFactoryPostProcessor` được **auto-detect** trong ApplicationContext được xử lý theo ngữ nghĩa `PriorityOrdered` và `Ordered`. Nhưng những BFPP **được đăng ký programmatically** với `ConfigurableApplicationContext` áp dụng theo **thứ tự đăng ký**, không theo ordering interface. `@Order` trên class BFPP cũng **không** được dùng như công tắc tự sắp thứ tự BFPP.

Nếu vừa có BFPP programmatic vừa có auto-detected BFPP, cần hiểu chúng đi qua những danh sách/lượt xử lý riêng; không gán một “tổng thứ tự duy nhất” theo các số `getOrder()` giữa hai nhóm mà chưa kiểm chứng.

## 8. Đăng ký BeanPostProcessor bằng mã trên BeanFactory

Khi dùng `DefaultListableBeanFactory` hoặc một `ConfigurableBeanFactory` thuần, ta có thể đăng ký BPP trực tiếp:

~~~java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "messageBean", new RootBeanDefinition(MessageBean.class));

factory.addBeanPostProcessor(new TaggingPostProcessor());
MessageBean bean = factory.getBean("messageBean", MessageBean.class);
~~~

Đây là snippet, cần imports `DefaultListableBeanFactory`, `RootBeanDefinition` và các class minh họa. Điểm quan trọng là **gọi `addBeanPostProcessor()` trước khi tạo các bean bạn muốn xử lý**.

`BeanPostProcessor` được thêm bằng mã vào `ConfigurableBeanFactory` sẽ:

- Chạy theo **thứ tự đăng ký trực tiếp**; Spring **không sắp xếp lại** chúng theo `PriorityOrdered`/`Ordered`.
- Được ưu tiên xử lý trước các BPP auto-detected của context nếu cùng pipeline có cả hai nguồn.
- Không tự tạo lại hay chạy hồi tố cho bean đã instantiated/cached trước thời điểm BPP được thêm.

**Ví dụ kiểm chứng thứ tự:** nếu gọi `addBeanPostProcessor(A)` rồi `addBeanPostProcessor(B)`, BPP programmatic chạy theo **A rồi B**, kể cả B implements `PriorityOrdered` và khai báo order rất nhỏ. Đừng kỳ vọng số `getOrder()` đảo thứ tự.

### BeanFactory thuần không tự khám phá processor beans

Nếu viết:

~~~java
factory.registerBeanDefinition(
        "myProcessor", new RootBeanDefinition(TaggingPostProcessor.class));
factory.registerBeanDefinition(
        "messageBean", new RootBeanDefinition(MessageBean.class));
~~~

thì với `DefaultListableBeanFactory` thuần, việc bean definition `myProcessor` tồn tại **không đủ** để nó tự tham gia pipeline BPP. Phải tạo/đăng ký processor bằng mã như `addBeanPostProcessor(...)`, hoặc bootstrap container qua ApplicationContext hỗ trợ auto-detection.

Tương tự, chỉ đăng ký `BeanFactoryPostProcessor` thành một bean definition trong plain BeanFactory **không khiến nó tự chạy**; phải gọi `postProcessBeanFactory(...)` trong giai đoạn chuẩn bị thích hợp nếu tự dùng BeanFactory, hoặc chuyển sang `ApplicationContext`.

## 9. BeanFactoryPostProcessor với BeanFactory thuần phải được gọi

Một ví dụ tối giản cho metadata transformation:

~~~java
DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
factory.registerBeanDefinition(
        "messageBean", new RootBeanDefinition(MessageBean.class));

// Factory thuần không tự phát hiện BeanFactoryPostProcessor.
new LabelDefinitionPatch().postProcessBeanFactory(factory);

// BPP instance pipeline cần đăng ký riêng trước khi getBean().
factory.addBeanPostProcessor(new TaggingPostProcessor());

MessageBean bean = factory.getBean("messageBean", MessageBean.class);
~~~

Đây là snippet, giả định `LabelDefinitionPatch` và `TaggingPostProcessor` đúng class như phần trước.

Với `BeanDefinitionRegistryPostProcessor` thuần, cần thêm một lượt gọi `postProcessBeanDefinitionRegistry(factory)` khi `factory` triển khai `BeanDefinitionRegistry`, trước khi callback `postProcessBeanFactory(factory)`. Nếu có **nhiều registry processors** hoặc cấu hình `@Configuration` phức tạp, việc thủ công sắp xếp mọi processor dễ sai; dùng `ApplicationContext` để Spring orchestration trọn pipeline thường an toàn hơn.

### Gọi trực tiếp với processor đã là Spring bean?

Khi dùng `ApplicationContext`, đừng vừa khai báo processor thành bean cho Spring tự phát hiện **vừa tự gọi callback hoặc thêm cùng instance lần nữa** vì bạn có thể tạo double processing, thay đổi thứ tự, thay property values hai lần hoặc wrap bean nhiều lần. Quyết định rõ ownership của processor.

## 10. Thứ tự PriorityOrdered, Ordered và @Order

Spring cung cấp những hợp đồng ordering khác nhau. Trong nhóm processor **auto-detected** thông thường:

1. Implementations của `PriorityOrdered` được ưu tiên trước `Ordered` thường.
2. `Ordered.getOrder()` với **số nhỏ hơn** thể hiện ưu tiên cao hơn trong nhóm phù hợp.
3. Processor không implements ordering được xử lý sau các nhóm có ordering, theo các quy tắc container có thể thay đổi giữa những tập processor.

Điểm đặc biệt: thứ tự không nên xác định bằng tên class, tên `@Bean`, thứ tự đọc file, thứ tự quét package hoặc vị trí khai báo method trong source.

| Đăng ký | `PriorityOrdered` / `Ordered` | `@Order` annotation trên class |
| --- | --- | --- |
| BFPP auto-detected trong `ApplicationContext` | Có hiệu lực theo contract | Không được dùng để order BFPP |
| BFPP programmatic qua `addBeanFactoryPostProcessor` | **Bỏ qua**, xử lý theo thứ tự đăng ký | Không phải cách kiểm soát thứ tự |
| BPP auto-detected trong `ApplicationContext` | Có hiệu lực theo contract | Không được dùng để order BPP |
| BPP programmatic qua `addBeanPostProcessor` | **Bỏ qua**, xử lý theo thứ tự đăng ký | Không phải cách kiểm soát thứ tự |
| BDRPP | Có các pha registry đặc biệt và quy tắc ordering của pipeline | Không tự đồng nhất hoàn toàn với nhóm BFPP thông thường |

Lưu ý: `@Order` có tác dụng ở **các tình huống Spring khác** như ordered injection collections, event listener hay AOP advice theo ngữ cảnh. Nhưng không vì thế mà nó thay thế interface `Ordered` trong hợp đồng dành riêng cho BFPP/BPP.

### Ví dụ interface ordering

~~~java
public final class FirstMetadataProcessor
        implements BeanFactoryPostProcessor, PriorityOrdered {

    @Override
    public int getOrder() {
        return 0;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory factory) {
        // Điều chỉnh metadata.
    }
}
~~~

Đây là snippet, cần imports `BeanFactoryPostProcessor`, `PriorityOrdered`, `ConfigurableListableBeanFactory`. Với BFPP **auto-detected**, số order có ý nghĩa; với BFPP **đăng ký programmatic**, thứ tự đăng ký mới là ưu tiên.

## 11. Ví dụ Java 17 chạy được: auto-detection và programmatic registration

Ví dụ đối chiếu trong **một chương trình**:

- `AnnotationConfigApplicationContext` auto-detect `BeanFactoryPostProcessor` và `BeanPostProcessor` được khai báo bằng static `@Bean`.
- `DefaultListableBeanFactory` thuần đăng ký bean definition rồi **tự gọi** BFPP và **tự thêm** BPP vào pipeline.
- Hai cách đều có thể dẫn tới cùng logic cấu hình metadata và can thiệp instance, nhưng ownership và thời điểm kích hoạt khác nhau.

Sử dụng Java 17, Maven, Spring Framework 6.2.12. Không cần Spring Boot, web server hay annotation scanning ngoài Java config.

Cấu trúc tệp:

~~~text
post-processor-registration/
├── pom.xml
└── src/main/java/example/PostProcessorRegistrationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>post-processor-registration</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
~~~

`src/main/java/example/PostProcessorRegistrationDemo.java`:

~~~java
package example;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class PostProcessorRegistrationDemo {

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AutoConfig.class)) {
            MessageBean bean = context.getBean("messageBean", MessageBean.class);
            System.out.println("Auto: " + bean.render());
        }

        DefaultListableBeanFactory factory = new DefaultListableBeanFactory();
        factory.registerBeanDefinition(
                "messageBean", new RootBeanDefinition(MessageBean.class));

        // Plain BeanFactory: BFPP phải được gọi; BPP phải được thêm.
        new SetLabelDefinitionProcessor("MANUAL")
                .postProcessBeanFactory(factory);
        factory.addBeanPostProcessor(new TaggingBeanPostProcessor());

        MessageBean bean = factory.getBean("messageBean", MessageBean.class);
        System.out.println("Manual: " + bean.render());

        factory.destroySingletons();
    }

    @Configuration(proxyBeanMethods = false)
    public static class AutoConfig {
        @Bean("messageBean")
        public MessageBean messageBean() {
            return new MessageBean();
        }

        // static tránh tạo @Configuration instance quá sớm.
        @Bean
        public static BeanFactoryPostProcessor autoMetadataProcessor() {
            return new SetLabelDefinitionProcessor("AUTO");
        }

        @Bean
        public static BeanPostProcessor autoInstanceProcessor() {
            return new TaggingBeanPostProcessor();
        }
    }

    public static final class MessageBean {
        private String label = "DEFAULT";
        private String tag = "NONE";

        public MessageBean() {
        }

        public void setLabel(String label) {
            this.label = label;
        }

        public void setTag(String tag) {
            this.tag = tag;
        }

        public String render() {
            return label + "|" + tag;
        }
    }

    public static final class SetLabelDefinitionProcessor
            implements BeanFactoryPostProcessor {
        private final String label;

        public SetLabelDefinitionProcessor(String label) {
            this.label = label;
        }

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory)
                throws BeansException {
            beanFactory.getBeanDefinition("messageBean")
                    .getPropertyValues()
                    .add("label", label);
        }
    }

    public static final class TaggingBeanPostProcessor
            implements BeanPostProcessor {
        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) throws BeansException {
            if ("messageBean".equals(beanName)
                    && bean instanceof MessageBean message) {
                message.setTag("BPP");
            }
            return bean;
        }
    }
}
~~~

Lệnh chạy từ thư mục `post-processor-registration`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.PostProcessorRegistrationDemo
~~~

Stdout của **chính các câu lệnh `System.out.println`** (không tính logging do Maven hoặc SLF4J):

~~~text
Auto: AUTO|BPP
Manual: MANUAL|BPP
~~~

**Vì sao kết quả hợp lý?**

1. `AnnotationConfigApplicationContext(AutoConfig.class)` đăng ký config và `refresh()`. Hai method `@Bean static` khai báo rõ return types `BeanFactoryPostProcessor` và `BeanPostProcessor`, nên context có thể phát hiện chúng đúng pha.
2. Auto BFPP tìm BeanDefinition `messageBean` và đặt property `label="AUTO"`. Khi tạo instance từ `@Bean messageBean()`, Spring tiếp tục xử lý property values của bean definition, gọi `MessageBean.setLabel("AUTO")`.
3. Auto BPP kiểm tra name/type trong `postProcessAfterInitialization`, gọi `setTag("BPP")`. Mã nhận được `MessageBean` nên `render()` là `AUTO|BPP`.
4. `DefaultListableBeanFactory` ở nhánh manual không tự tìm processor beans. Ta chủ động gọi `SetLabelDefinitionProcessor("MANUAL").postProcessBeanFactory(factory)` trước khi `getBean`, rồi gọi `factory.addBeanPostProcessor(...)`.
5. Plain BeanFactory khởi tạo `MessageBean`, điền property `label="MANUAL"` và gọi BPP đã đăng ký. Kết quả `MANUAL|BPP`.
6. `destroySingletons()` giải phóng singleton của plain BeanFactory theo hợp đồng nếu có destroy callback; demo bean không giữ tài nguyên hoặc custom destroy method.

Ví dụ cố ý **không in log từ processor**, tránh lệ thuộc thời điểm xử lý các infrastructure beans. Hai dòng stdout được kiểm chứng bằng việc chỉ in sau khi các context/factory đã cung cấp `MessageBean`.

### Điểm khác nếu dùng AnnotationConfigApplicationContext dạng manual

Có thể lấy context chưa refresh, thêm BFPP và sau đó refresh:

~~~java
try (var context = new AnnotationConfigApplicationContext()) {
    context.register(AutoConfig.class);
    context.addBeanFactoryPostProcessor(
            new SetLabelDefinitionProcessor("OVERRIDE"));
    context.refresh();
}
~~~

Đây là snippet **minh họa riêng**, không thêm trực tiếp vào chương trình hai dòng stdout trên. Trong ví dụ này đã có BFPP tự động đặt `AUTO`, nên **hai processors cùng sửa một property**. Kết quả cuối có thể phụ thuộc pha và thứ tự xử lý; để tránh cấu hình mâu thuẫn, chỉ chọn một processor làm owner của field `label` hoặc định nghĩa override precedence tường minh rồi test. Không dùng mẫu này để suy diễn programmatic BFPP luôn thắng/luôn thua một auto-detected BFPP trong mọi ngữ cảnh.

## 12. Các cách đăng ký khác nhau trong thực tế

### 12.1. @Component và @ComponentScan

~~~java
@Component
public final class ValidationProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        return bean;
    }
}
~~~

Khi package chứa processor được component scan, Spring tạo bean definition và tự nhận diện type BPP. Nhưng **component scanning không xảy ra nếu chưa được cấu hình**; chỉ đặt `@Component` lên class rồi tạo một `DefaultListableBeanFactory` thuần không tự kích hoạt scan/processor.

Một lưu ý nhỏ: processor beans được tạo sớm, vì thế tránh constructor nhận business services phức tạp; điều đó có thể tạo sớm cả những bean lẽ ra cần được auto-proxy.

### 12.2. @Bean static

Đây thường là cách có kiểm soát khi processor yêu cầu config chính xác. Với BFPP phải đặc biệt ưu tiên `static`; với BPP cũng được khuyến nghị `static`, ít hoặc không có dependencies, khai báo return type là class BPP/`BeanPostProcessor` để Spring phát hiện trước khởi tạo.

### 12.3. XML hoặc bean definitions thủ công trong context

Bean definitions có implementation của BFPP/BPP cũng có thể được đăng ký qua XML hoặc API. Khi được thêm vào **ApplicationContext trước refresh**, Spring auto-detect theo type và gọi theo pipeline. Khi đăng ký cùng definition vào **plain BeanFactory**, không có guarantee tự gọi processor nếu không kích hoạt cơ chế tương ứng bằng mã.

### 12.4. BeanDefinitionRegistryPostProcessor bằng @Bean

Nếu cần thêm các bean definitions mới, processor trả từ `@Bean static` có thể triển khai BDRPP. Nhưng chú ý tương tác với `ConfigurationClassPostProcessor` đang xử lý config classes: BDRPP muốn thêm definition trước khi quá trình scan/config kết thúc cần tuân thủ thứ tự registry processing, không lạm dụng `getBean()`.

### 12.5. Manual BPP trên ApplicationContext đã refresh

`context.getBeanFactory().addBeanPostProcessor(myBpp)` về mặt kỹ thuật đăng ký BPP cho các bean được tạo **sau đó**; nó **không retroactively xử lý singleton đã tạo**. Nếu bạn muốn xử lý toàn bộ eager singletons, phải thêm trước khi chúng được tạo. Với ứng dụng thông thường, khai báo BPP bean để Spring auto-detect là cách ít rủi ro hơn.

## 13. Vì sao processor đăng ký sớm và dependency sớm là nguy hiểm?

Các `BeanPostProcessor` phải tồn tại **trước khi** các regular beans được khởi tạo để chạy trên chúng. Vì vậy Spring tạo chính những processor này và các dependency trực tiếp của chúng rất sớm. Điều này dẫn tới các hệ quả:

- Những bean được tạo sớm cùng processor có thể **không đủ điều kiện nhận mọi BeanPostProcessor**, bao gồm auto-proxying.
- Có thể xuất hiện thông báo WARN kiểu bean không eligible for being processed by all BeanPostProcessors.
- Nếu BPP có constructor injection một `TransactionalService`, service có thể được dựng trước khi transactional auto-proxy creator đã hoạt động đầy đủ; behavior có thể khác kỳ vọng.
- Nếu BFPP dùng `getBean` để giải quyết metadata, nó có thể dựng instance trước BPP pipeline.
- Gọi network, database migration hoặc bắt đầu thread trong processor init/callback khiến context startup chậm và khó khắc phục.

**Thực hành an toàn:** giữ processor **nhẹ, ít dependency, không gọi bean nghiệp vụ trong pha định nghĩa**, và dùng registry/metadata APIs thay vì instantiation khi vấn đề là cấu hình.

Một BPP thật sự cần phụ thuộc vào hạ tầng nào đó có thể tách hạ tầng thành một bean được thiết kế dành riêng cho early startup (không trông chờ AOP) hoặc trì hoãn một số thao tác cho đến thời điểm được bảo đảm; cần test đường bootstrap thực tế, không chỉ test bình thường sau refresh.

## 14. Container hierarchy: mỗi processor xử lý phạm vi nào?

Post-processors về nguyên tắc là **per-container**:

~~~text
Parent ApplicationContext
    ├── Parent Bean A
    └── Parent BeanPostProcessor P
            └── xử lý bean của parent, không tự xử lý bean child

Child ApplicationContext
    ├── Child Bean B
    └── Child BeanPostProcessor C
            └── xử lý bean của child, không tự xử lý bean parent
~~~

Việc child context có thể **lookup parent bean** không đồng nghĩa child BPP được áp dụng lên instance parent đã được tạo. Tương tự BFPP ở parent tác động definitions thuộc factory mà nó quản lý, không tự duyệt/sửa tất cả definitions trong child factory.

Khi nhiều module/context cùng cần một processor, phải đăng ký processor trong những context thích hợp; không giả định BeanPostProcessor tự lan xuống cây context. Copy một BPP instance bằng mã sang context khác chỉ nên làm khi processor stateless hoặc được thiết kế để dùng đa context; cẩn thận reference giữ tới owner context.

## 15. Idempotence, độ an toàn và tránh double registration

Post-processors ảnh hưởng lifecycle rộng nên lỗi nhỏ có thể lan tới nhiều beans.

### 15.1. Chỉ định rõ owner đăng ký

Nếu dùng auto-detection trong ApplicationContext, không cần tự gọi processor thêm một lần. Nếu dùng plain BeanFactory, gọi processor thủ công theo đúng sequence; không vừa add BPP vừa để hệ thống khác thêm cùng instance lần nữa không kiểm soát.

### 15.2. Thay metadata có idempotent không?

Nếu BFPP thêm prefix vào property bằng phép cộng chuỗi, chạy hai lần có thể biến `service` thành `X-X-service`. Khi processor có thể được invoke lại do cấu hình hoặc test, viết callback sao cho đặt giá trị cuối rõ ràng, check attribute đã xử lý, hoặc định nghĩa semantics idempotent.

### 15.3. BPP wrapping nhiều lớp proxy

Một BPP có thể trả wrapper/proxy mới. Nếu cùng logic được kích hoạt hai lần, client có thể nhận proxy lồng nhau, equals/hashCode hoặc reflection khác dự kiến. Khi thiết kế processor có khả năng được gọi lại, cần nhận biết object đã được wrap, hoặc bảo đảm bean được xử lý một lần trong pipeline hợp lệ.

### 15.4. Phạm vi thay đổi

BFPP chỉ nên sửa definitions đã biết theo type/name/attribute có kiểm soát. BPP nên kiểm tra type/name/annotation trước khi can thiệp instance; đừng cast tất cả beans thành một class nghiệp vụ hay mutate mọi singleton không liên quan.

### 15.5. Failure policy

Nếu processor ném exception trong startup, context có thể không refresh được. Với config lỗi nghiêm trọng đây có thể là hành vi đúng, nhưng logger cần giải thích bean name/definition nào không hợp lệ. Không nuốt exception rồi tiếp tục khi metadata bị sửa một nửa mà trạng thái không còn đáng tin.

## 16. Khi nào chọn auto-detection hoặc đăng ký bằng mã?

| Tình huống | Cách thường phù hợp | Vì sao |
| --- | --- | --- |
| Ứng dụng Spring bình thường cần BPP/BFPP | `@Bean static` hoặc `@Component` trong `ApplicationContext` | Spring tự áp dụng pipeline và ordering |
| Infrastructure library có post-processor cố định | Bean definition/cấu hình import rõ ràng | Khả năng auto-detection và bảo trì tốt |
| Cần thêm BFPP theo điều kiện ở bootstrap trước refresh | `context.addBeanFactoryPostProcessor(...)` | Chọn processor trước khi metadata được xử lý |
| Dùng `DefaultListableBeanFactory` trực tiếp | Gọi BFPP bằng tay, `addBeanPostProcessor` trước `getBean` | BeanFactory không tự phát hiện processor beans |
| Cần thêm bean definitions trước khi các regular beans được tạo | `BeanDefinitionRegistryPostProcessor` | Registry-phase extension phù hợp |
| Chỉ sửa bean property thường qua cấu hình | `@Bean`/`@Value`/constructor DI trước | Không cần processor nếu wiring thường giải quyết được |
| Proxying nhiều beans theo annotation/custom semantics | BPP/Infrastructure AOP | Extension instance có cơ chế rõ |
| Muốn xử lý những singleton đã tạo xong | Không kỳ vọng BPP thêm muộn tự áp dụng | Thiết kế lại thời điểm đăng ký hoặc cơ chế explicit transformation |

Không tạo BPP/BFPP chỉ để thay một property mà `@Configuration`, `@Bean` hoặc `@ConfigurationProperties` đã biểu đạt rõ. Processor là hook cấp container, thường ảnh hưởng rộng, khó suy luận hơn cấu hình tường minh.

## 17. Những lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân điển hình | Hướng kiểm tra/sửa |
| --- | --- | --- |
| Processor là bean nhưng không chạy | Dùng plain BeanFactory, chưa register/invoke processor | `addBeanPostProcessor`/gọi BFPP thủ công hoặc dùng ApplicationContext |
| Processor @Bean không được auto-detect | Return type khai báo quá chung, thiếu scan/import | Khai báo `BeanPostProcessor`/implementation return type rõ |
| Processor làm cấu hình @Autowired/@PostConstruct của @Configuration mất tác dụng | BFPP @Bean method không static gây khởi tạo config quá sớm | Sửa thành `static @Bean` |
| Bean không được auto-proxy | BPP hoặc dependency của BPP được khởi tạo quá sớm | Giảm early dependency, static @Bean, xem warning |
| BFPP sửa object đã tồn tại | Dùng `getBean` trong metadata phase | Sửa `BeanDefinition`, không instantiate business bean |
| Thêm BPP sau getBean nhưng không thấy tác dụng | Bean singleton đã được tạo/cached | Đăng ký BPP trước bean creation |
| Implement Ordered nhưng programmatic processor chạy sai thứ tự | Programmatic registration bỏ qua ordering interface | Đổi **thứ tự đăng ký** |
| Dùng @Order để điều khiển BFPP/BPP | Hợp đồng ordering của processor không dùng @Order | Implement `PriorityOrdered`/`Ordered` cho auto-detected |
| Multiple processors chỉnh cùng property | Conflict, thứ tự không rõ | Một owner hoặc precedence/test cụ thể |
| BPP bị gọi trên infrastructure bean lạ | BPP xử lý nhiều beans phù hợp trong container | Filter theo type/name/annotation |
| Context con không thấy BPP của parent | Post-processors scoped per container | Đăng ký ở đúng child context |
| Startup treo | Processor init hoặc BFPP lookup kéo network/deadlock | Thread dump, bỏ I/O/bean lookup không cần thiết |
| BDRPP không thấy definition mới | Đăng ký registry processor quá muộn | Đưa processor vào bootstrap/registry phase |
| Exception BeanCreationException khi processor chạy | Post-processor tự tạo bean hoặc lỗi config | Đọc root cause và điểm xử lý metadata |
| @PostConstruct order so với BPP sai dự đoán | Annotation lifecycle cũng do BPP xử lý | Xem processor ordering, không suy luận mọi before đều trước annotation |

## 18. Checklist kiểm tra trước khi triển khai

1. Xác định đang dùng `ApplicationContext` hay plain `DefaultListableBeanFactory`.
2. Chọn **registry**, **metadata** hay **instance** extension point theo nhiệm vụ.
3. Processor definitions đã được đăng ký trước refresh/bean creation chưa?
4. Nếu `@Bean` trả processor, method có `static` và return type nhận diện được không?
5. Processor có tránh dependency hạ tầng nặng và business beans cần auto-proxy không?
6. BFPP/BDRPP có chỉ thao tác definitions/registry, không gọi getBean nghiệp vụ không?
7. BPP có lọc bean name/type/annotation và trả bean hoặc wrapper hợp lệ không?
8. Có dùng `PriorityOrdered`/`Ordered` cho **auto-detected** nếu thứ tự cần thiết?
9. Nếu programmatic, thứ tự **đăng ký thực tế** đã được test chưa?
10. Có tránh thêm BPP quá muộn khiến singleton cũ không được xử lý không?
11. Có phân biệt lifecycle của processor với lifecycle của beans nó xử lý?
12. Có test idempotence, duplicate registration, fail-fast và shutdown?
13. Có hiểu processor không tự lan từ parent context sang child context không?
14. Nếu chỉ cần sửa một bean cụ thể, đã cân nhắc `@Bean`/DI thường trước khi mở rộng container chưa?

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Một `BeanPostProcessor` được khai báo qua `@Bean static` trong `AnnotationConfigApplicationContext` và có return type đúng. Cần gọi `addBeanPostProcessor` nữa không?

**Đáp án:** Không. ApplicationContext tự phát hiện BPP bean, tạo/đăng ký ở startup rồi áp dụng cho các bean được tạo sau giai đoạn đó.

**Câu 2.** `DefaultListableBeanFactory` đăng ký BeanDefinition của `MyPostProcessor implements BeanPostProcessor` rồi `getBean("service")`. Processor tự chạy không?

**Đáp án:** Không tự động. BeanFactory thuần không auto-detect loại bean này; cần `addBeanPostProcessor` hoặc bootstrap thông qua context hỗ trợ.

**Câu 3.** Một `BeanFactoryPostProcessor` muốn thay field của singleton đã instantiated. Gọi `getBean()` ngay trong BFPP có đúng extension point không?

**Đáp án:** Không. BFPP tác động bean metadata trước khi regular bean instances được tạo. Gọi `getBean` ở đây dễ khởi tạo bean quá sớm và thiếu BPP/AOP; nếu cần tác động instance, chọn BPP hoặc DI/configuration phù hợp.

**Câu 4.** BPP A implements `Ordered` order=100, BPP B implements `PriorityOrdered` order=0. Nếu `factory.addBeanPostProcessor(A)` rồi `factory.addBeanPostProcessor(B)`, ai chạy trước?

**Đáp án:** Trong **programmatic registration** này, A trước B theo thứ tự thêm, không theo interface order.

**Câu 5.** BFPP auto-detected dùng `@Order(-100)` để ưu tiên, có được bảo đảm không?

**Đáp án:** Không. `@Order` annotation không được dùng để xác định thứ tự BFPP theo contract. Cần implement `PriorityOrdered` hoặc `Ordered` khi dùng auto-detection.

**Câu 6.** Cần đăng ký thêm bean definition trong quá trình config processing. Chọn BFPP hay BDRPP?

**Đáp án:** `BeanDefinitionRegistryPostProcessor` phù hợp vì có registry-phase hook trước khi phần lớn bean definitions hoàn tất xử lý.

**Câu 7.** Vì sao khai báo `@Bean static BeanFactoryPostProcessor`?

**Đáp án:** Để container tạo post-processor sớm mà không phải instantiate configuration class quá sớm, tránh lifecycle conflicts với các annotation như `@Autowired` và `@PostConstruct` trên config class.

**Câu 8.** Đăng ký BPP sau khi singleton `service` đã được tạo có tự wrap lại service không?

**Đáp án:** Không. BPP áp dụng ở quá trình tạo instance, không retroactively sửa các singleton đã tạo/cached.

## 20. Tham khảo chính thức

- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html)
- [Spring Framework — The BeanFactory API](https://docs.spring.io/spring-framework/reference/core/beans/beanfactory.html)
- [Spring Framework — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html)
- [Spring Framework — Bean Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Framework 6.2 Javadoc — BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html)
- [Spring Framework 6.2 Javadoc — BeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html)
- [Spring Framework Javadoc — BeanDefinitionRegistryPostProcessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html)
