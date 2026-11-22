# Xử lý BeanDefinitionRegistryPostProcessor và BeanFactoryPostProcessor trong Spring Boot

## 1. Tại sao Spring cần hai loại post-processor này?

Trong quá trình khởi động Spring Boot, **ApplicationContext** không lập tức tạo mọi đối tượng từ **@Component**, **@Service**, **@Configuration** và **@Bean**. Trước tiên Spring thu thập và xử lý các **BeanDefinition**: metadata mô tả tên, kiểu, scope, lazy initialization, constructor arguments, property values và cách tạo một bean. Sau đó container mới khởi tạo phần lớn singleton ứng dụng.

Spring Framework cung cấp hai điểm mở rộng để can thiệp **trước giai đoạn khởi tạo bean thông thường**:

- **BeanDefinitionRegistryPostProcessor (BDRPP):** truy cập registry để đăng ký thêm, xóa hoặc thay đổi các BeanDefinition trước khi các BeanFactoryPostProcessor thông thường được gọi.
- **BeanFactoryPostProcessor (BFPP):** đọc và sửa metadata cấu hình trong **ConfigurableListableBeanFactory**, để những thay đổi được áp dụng khi Spring tạo bean.

Cả hai làm việc chủ yếu ở tầng **định nghĩa bean**, khác với **BeanPostProcessor** (BPP), loại được dùng để xử lý **instance** của bean trong quá trình khởi tạo.

~~~text
Nguồn cấu hình (@Bean, @Component, @Import...)
                   |
                   v
           BeanDefinitionRegistry
                   |
                   | BDRPP: registry callback
                   | đăng ký/chỉnh BeanDefinition
                   v
        ConfigurableListableBeanFactory
                   |
                   | BDRPP và BFPP: factory callback
                   | đọc/chỉnh metadata trước khi tạo bean
                   v
            Đăng ký BeanPostProcessor
                   |
                   v
          Tạo và khởi tạo các singleton
                   |
                   | BPP: trước/sau initialization
                   v
             Bean instance sẵn sàng
~~~

Ví dụ, nếu muốn tạo một bean tên **dynamicGreeting** theo metadata rồi sửa thuộc tính **message** trước khi constructor được gọi, BDRPP và BFPP là hai điểm mở rộng phù hợp. Không cần khởi tạo đối tượng rồi sửa nó thủ công.

## 2. Các interface, callback và trách nhiệm cụ thể

### 2.1. BeanFactoryPostProcessor

Interface **org.springframework.beans.factory.config.BeanFactoryPostProcessor** có một callback:

~~~java
void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory)
        throws BeansException;
~~~

Thông qua **ConfigurableListableBeanFactory**, processor có thể đọc metadata:

~~~java
BeanDefinition definition =
        beanFactory.getBeanDefinition("myService");

definition.setLazyInit(true);
definition.getPropertyValues().add("label", "updated");
~~~

Đây là **đoạn minh họa**, giả định đã tồn tại definition **myService**, lớp bean hỗ trợ property **label**, và code chạy tại giai đoạn BFPP. **setLazyInit(true)** là sửa chính sách tạo bean; **getPropertyValues().add(...)** là sửa giá trị mà Spring sẽ gán khi bean được tạo.

Một BFPP tiêu biểu của Spring là **PropertySourcesPlaceholderConfigurer**, hỗ trợ xử lý placeholder cấu hình trong BeanDefinition và các cơ chế resolve value tương ứng.

**Quan trọng:** BFPP nhận **bean factory**, nhưng không nên gọi **beanFactory.getBean(...)** để “lấy đối tượng ra chỉnh”. Điều đó có thể khởi tạo bean sớm, trước khi toàn bộ **BeanPostProcessor**, AOP proxy và các cơ chế injection liên quan hoạt động đầy đủ.

### 2.2. BeanDefinitionRegistryPostProcessor

Interface **org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor** kế thừa **BeanFactoryPostProcessor** và bổ sung callback:

~~~java
void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry)
        throws BeansException;
~~~

**BeanDefinitionRegistry** cung cấp các thao tác như:

- **registerBeanDefinition(name, definition):** đăng ký metadata mới.
- **containsBeanDefinition(name):** kiểm tra tên bean definition.
- **getBeanDefinition(name):** lấy metadata hiện có.
- **removeBeanDefinition(name):** xóa definition khi được phép và có lý do đúng.

Vì **BDRPP extends BFPP**, một BDRPP có **hai callback cần triển khai**:

~~~java
@Override
public void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry) {
    // Thêm/sửa/xóa BeanDefinition trong pha registry.
}

@Override
public void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory) {
    // Xử lý metadata trong pha factory.
}
~~~

Đây là **hai method thuộc một implementation**, không phải ứng dụng Java độc lập. Khi không cần thêm logic ở callback thứ hai, method có thể để trống. Spring vẫn gọi nó theo hợp đồng của BFPP, và **không gọi lại processor như một BFPP mới lần thứ hai**.

### 2.3. Phân biệt với BeanPostProcessor và FactoryBean

| Khái niệm | Xử lý cái gì? | Callback/API điển hình | Thời điểm |
| --- | --- | --- | --- |
| **BeanDefinitionRegistryPostProcessor** | Registry và BeanDefinition | **postProcessBeanDefinitionRegistry** | Sớm trong refresh |
| **BeanFactoryPostProcessor** | BeanDefinition/BeanFactory metadata | **postProcessBeanFactory** | Sau pha registry, trước đăng ký BPP |
| **BeanPostProcessor** | Đối tượng bean đã/đang được tạo | **postProcessBeforeInitialization**, **postProcessAfterInitialization** | Mỗi lần bean được khởi tạo qua container |
| **FactoryBean<T>** | Tạo một đối tượng bean theo cách riêng | **getObject()** | Khi container cần sản phẩm của FactoryBean |

**BeanPostProcessor không kế thừa BeanFactoryPostProcessor.** Một BFPP chạy ở giai đoạn metadata; nó không được gọi lại cho từng bean. **FactoryBean** cũng không phải một loại BFPP: tên giống nhau nhưng trách nhiệm hoàn toàn khác.

## 3. Vị trí chính xác trong ApplicationContext.refresh()

Spring Boot 3.3 dùng **SpringApplication** chuẩn bị Environment, tạo ApplicationContext, nạp nguồn cấu hình và gọi **refresh()**. Phần lõi Spring Framework, đặc biệt **AbstractApplicationContext**, điều phối các processor. Cơ chế chung áp dụng cho context non-web, Servlet và Reactive.

Trình tự quan trọng trong một lần refresh thành công:

~~~text
SpringApplication.run(...)
   |
   +-- Chuẩn bị Environment, tạo context, load sources
   |
   +-- ApplicationContext.refresh()
         |
         +-- prepareRefresh()
         +-- obtainFreshBeanFactory()
         +-- prepareBeanFactory(...)
         +-- context.postProcessBeanFactory(...)   [context hook]
         |
         +-- invokeBeanFactoryPostProcessors(...)
         |      |
         |      +-- BDRPP.postProcessBeanDefinitionRegistry(...)
         |      +-- BDRPP.postProcessBeanFactory(...)
         |      +-- BFPP.postProcessBeanFactory(...)
         |
         +-- registerBeanPostProcessors(...)
         +-- initMessageSource(...)
         +-- initApplicationEventMulticaster(...)
         +-- onRefresh()
         +-- registerListeners()
         +-- finishBeanFactoryInitialization(...)
         |      |
         |      +-- Tạo singleton không lazy còn lại
         |      +-- Áp dụng BeanPostProcessor
         |
         +-- finishRefresh()
   |
   +-- ApplicationStartedEvent
   +-- ApplicationRunner / CommandLineRunner
   +-- ApplicationReadyEvent
   +-- run(...) trả về context
~~~

**Lưu ý tên gọi:** **context.postProcessBeanFactory(...)** trong **AbstractApplicationContext.refresh()** là một *extension hook của context*, khác với **BeanFactoryPostProcessor.postProcessBeanFactory(...)** trên từng processor. Hook của context chạy trước bước invoke processors.

**BFPP chạy trước khi tạo phần lớn singleton ứng dụng**, nhưng không có nghĩa JVM chưa có object nào: để vận hành, Spring đã phải tạo một số processor và bean hạ tầng ở giai đoạn sớm. Một lời gọi **getBean(...)** cưỡng ép trong BFPP có thể tạo thêm bean ứng dụng trước thời điểm dự kiến.

Mục tiêu của thứ tự này là bảo đảm metadata được sửa **trước khi nó được sử dụng** để tạo singleton, inject dependencies và gọi initialization callbacks.

## 4. Spring xử lý BDRPP trước BFPP theo thuật toán nào?

Spring không chạy các processor theo thứ tự dòng code hoặc thứ tự tên file. Trong **invokeBeanFactoryPostProcessors**, framework có cơ chế xử lý registry riêng. Điều này quan trọng vì một BDRPP có thể đăng ký **BeanDefinition của một BDRPP khác**.

### Pha 1 — xử lý BeanDefinitionRegistryPostProcessor

Spring ưu tiên các BDRPP được đăng ký với context theo chương trình, sau đó xử lý các processor được tìm qua bean definitions theo các nhóm:

1. Các processor **PriorityOrdered**.
2. Các processor **Ordered** còn lại.
3. Các processor chưa khai báo thứ tự.

Ở giai đoạn registry, Spring **lặp tiếp** khi có BDRPP mới được phát hiện, đến khi không còn BDRPP cần chạy. Điều này cho phép các định nghĩa phát sinh trong pha registry tham gia vòng xử lý thích hợp.

Callback được dùng là **postProcessBeanDefinitionRegistry(registry)**; trong callback, processor có thể đăng ký một **RootBeanDefinition** mới hoặc sửa definition hiện có. Các processor chạy tiếp sau đó sẽ nhìn thấy registry đã được cập nhật.

### Pha 2 — callback factory của chính các BDRPP

Sau khi hoàn tất xử lý registry, Spring gọi **postProcessBeanFactory(beanFactory)** của các BDRPP đã thực thi. Dù BDRPP kế thừa BFPP, callback này chỉ thuộc **một lần xử lý của processor đó**, không phải thêm một processor độc lập.

### Pha 3 — các BeanFactoryPostProcessor thông thường

Các BFPP còn lại được xử lý lần lượt theo nhóm **PriorityOrdered**, **Ordered**, rồi các BFPP không khai báo thứ tự. Kết thúc bước này, Spring mới tiếp tục đăng ký các BeanPostProcessor và tạo singleton ứng dụng còn lại.

~~~text
BDRPP registry callbacks
   -> PriorityOrdered
   -> Ordered
   -> các processor còn lại (quét lặp nếu có BDRPP mới)
           |
           v
BDRPP factory callbacks
           |
           v
BFPP factory callbacks
   -> PriorityOrdered
   -> Ordered
   -> còn lại
           |
           v
Đăng ký BeanPostProcessor
           |
           v
Khởi tạo singleton và callback trên từng bean
~~~

**Trường hợp đặc biệt:** processor được thêm trực tiếp bằng **ApplicationContext.addBeanFactoryPostProcessor(...)** có quy tắc xử lý riêng, không thể coi nó giống hoàn toàn với các processor được context tự tìm từ bean definitions.

### 4.1. PriorityOrdered và Ordered

Nếu cần thứ tự rõ ràng giữa các custom processor, implementation có thể dùng **org.springframework.core.PriorityOrdered** hoặc **org.springframework.core.Ordered**. Trong cùng nhóm sắp xếp, **getOrder()** nhỏ hơn thường được xử lý trước:

~~~java
final class MetadataProcessor
        implements BeanFactoryPostProcessor, Ordered {

    @Override
    public int getOrder() {
        return 100;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Thay đổi metadata có chọn lọc.
    }
}
~~~

Đây là **snippet trong project đã khai báo import**, không phải chương trình độc lập. Với nhiều processor, không nên dựa vào thứ tự tên bean, thứ tự phương thức **@Bean** hoặc vị trí trong file. Nếu hai processor cần phụ thuộc chặt vào nhau, hãy tổ chức lại logic hoặc xác định thứ tự dựa trên hợp đồng framework.

## 5. ConfigurationClassPostProcessor là BDRPP quan trọng của Spring

**ConfigurationClassPostProcessor** là một **BeanDefinitionRegistryPostProcessor** hạ tầng, có mức ưu tiên **PriorityOrdered**. Nó giúp Spring xử lý các lớp cấu hình dựa trên annotation:

- Phân tích **@Configuration** và nguồn cấu hình.
- Xử lý các chỉ dẫn liên quan **@ComponentScan**, **@Import**, **@Bean**.
- Đăng ký BeanDefinition cho các bean được phát hiện và các method **@Bean**.
- Thực hiện một số bước hoàn thiện liên quan tới configuration class.

Ví dụ:

~~~java
@Configuration
class FeatureConfiguration {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

Ở thời điểm đọc cấu hình, Spring có thể đăng ký **BeanDefinition** mô tả method **greetingService()** mà **chưa cần tạo GreetingService ngay**.

Đó là lý do **ConfigurationClassPostProcessor phải hoạt động sớm**: các bean definitions từ **@Bean** cần xuất hiện trước khi các BFPP còn lại tùy biến chúng.

**Cảnh báo về thứ tự:** nếu một BDRPP tự viết được gọi sau ConfigurationClassPostProcessor và đăng ký thêm một definition của lớp **@Configuration**, không được mặc nhiên cho rằng Spring sẽ **tự chạy lại toàn bộ quá trình quét annotation** đã hoàn tất trước đó. Hãy đăng ký definition đúng hợp đồng hoặc dùng cơ chế cấu hình/registrar được Spring hỗ trợ cho nhu cầu đó.

## 6. Ví dụ Java 17+ chạy được: đăng ký bean rồi chỉnh metadata

Ví dụ sau dùng dự án **Spring Boot 3.3.x**, **Java 17+**, dependency **spring-boot-starter** và Spring Boot Gradle plugin. Chạy ở chế độ **non-web** để tập trung vào các callback của container.

Tạo file:

**src/main/java/com/example/runtime/PostProcessorDemoApplication.java**

~~~java
package com.example.runtime;

import org.springframework.beans.BeansException;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.beans.factory.support.RootBeanDefinition;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class PostProcessorDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(PostProcessorDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context = app.run(args)) {
            GreetingService service =
                    context.getBean("dynamicGreeting", GreetingService.class);

            System.out.println("5 | main: " + service.getMessage());
        }
    }

    @Bean
    static BeanDefinitionRegistryPostProcessor registryProcessor() {
        return new BeanDefinitionRegistryPostProcessor() {

            @Override
            public void postProcessBeanDefinitionRegistry(
                    BeanDefinitionRegistry registry)
                    throws BeansException {

                RootBeanDefinition definition =
                        new RootBeanDefinition(GreetingService.class);

                definition.getPropertyValues()
                          .add("message", "initial message");

                registry.registerBeanDefinition(
                        "dynamicGreeting", definition);

                System.out.println(
                        "1 | registry: dynamicGreeting registered");
            }

            @Override
            public void postProcessBeanFactory(
                    ConfigurableListableBeanFactory beanFactory)
                    throws BeansException {

                System.out.println("2 | registry: factory callback");
            }
        };
    }

    @Bean
    static BeanFactoryPostProcessor metadataProcessor() {
        return beanFactory -> {
            BeanDefinition definition =
                    beanFactory.getBeanDefinition("dynamicGreeting");

            definition.getPropertyValues()
                      .add("message", "updated before instantiation");

            System.out.println("3 | factory: bean definition updated");
        };
    }

    public static class GreetingService {

        private String message;

        public GreetingService() {
            System.out.println("4 | bean: constructor executed");
        }

        public void setMessage(String message) {
            this.message = message;
        }

        public String getMessage() {
            return message;
        }
    }
}
~~~

Chạy bằng Gradle Wrapper từ thư mục dự án Boot:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Các dòng do ví dụ tự in theo thứ tự kỳ vọng:**

~~~text
1 | registry: dynamicGreeting registered
2 | registry: factory callback
3 | factory: bean definition updated
4 | bean: constructor executed
5 | main: updated before instantiation
~~~

Spring Boot có thể in các log khởi động xen giữa những dòng trên. Chỉ các dòng đánh số do ví dụ tự in mới có thứ tự và nội dung cần đối chiếu.

### 6.1. Vì sao có thứ tự này?

**Bước 1:** BDRPP tạo một **RootBeanDefinition** cho **GreetingService**, đặt giá trị ban đầu **message = "initial message"** rồi đăng ký tên bean **dynamicGreeting**. Chưa có đối tượng GreetingService nào được tạo chỉ vì đăng ký definition.

**Bước 2:** Cũng processor registry đó nhận callback **postProcessBeanFactory**, chứng minh một BDRPP đồng thời là BFPP.

**Bước 3:** BFPP thông thường tìm bean definition vừa được thêm, sửa **message = "updated before instantiation"**. Đây là sửa **định nghĩa**, không phải gọi setter trên instance.

**Bước 4:** Trong quá trình Spring hoàn tất refresh, singleton không lazy **dynamicGreeting** được tạo. Constructor in dòng số 4; sau đó Spring dùng setter **setMessage(...)** để áp dụng property value đã được chỉnh.

**Bước 5:** **SpringApplication.run(...)** trả về context; **main** tra cứu bean đã tồn tại và đọc giá trị cuối cùng là **updated before instantiation**.

Nếu bỏ riêng **metadataProcessor()** mà giữ processor registry, giá trị cuối thông thường sẽ là **initial message**. Ví dụ vì thế minh họa cả **cơ chế đăng ký** lẫn **cơ chế sửa metadata trước khi bean được tạo**.

### 6.2. Vì sao các @Bean method trả về processor là static?

Các processor thuộc nhóm **BeanFactoryPostProcessor** được tạo **rất sớm**. Nếu khai báo bằng **@Bean instance method**, Spring có thể phải tạo sớm chính đối tượng **@Configuration** chứa phương thức. Việc đó có thể khiến **@Autowired**, **@Value**, **@PostConstruct** hoặc các bước xử lý annotation trên configuration class không thực hiện theo vòng đời đầy đủ.

Khai báo:

~~~java
@Bean
static BeanFactoryPostProcessor metadataProcessor() {
    return beanFactory -> {
        // Xử lý bean definition.
    };
}
~~~

cho phép Spring gọi method mà **không cần khởi tạo instance của lớp cấu hình**. Nên dùng **static @Bean** cho BDRPP/BFPP khi khai báo dưới dạng method trên configuration class, giữ dependency của processor đơn giản và hạn chế gọi bean ứng dụng khác trong constructor.

### 6.3. Vì sao không lấy bean instance trong processor?

Đoạn đúng trong BFPP:

~~~java
BeanDefinition definition =
        beanFactory.getBeanDefinition("dynamicGreeting");
~~~

Đoạn có nguy cơ sai vòng đời:

~~~java
GreetingService service =
        beanFactory.getBean("dynamicGreeting", GreetingService.class);
~~~

Lệnh **getBean(...)** có thể khiến Spring tạo **GreetingService quá sớm**, trước khi đầy đủ BeanPostProcessor được đăng ký. Hậu quả có thể là thiếu AOP proxy, bỏ qua một số cơ chế initialization hoặc gặp lỗi dependency. **BFPP cần sửa metadata, còn BPP/lifecycle callbacks xử lý instance.**

## 7. Có thể thay đổi những gì trong BeanDefinition?

| Metadata | API minh họa | Ý nghĩa |
| --- | --- | --- |
| Bean class | **new RootBeanDefinition(MyService.class)** | Quy định lớp được tạo |
| Bean name | **registerBeanDefinition("myService", definition)** | Đặt tên tra cứu bean |
| Property values | **getPropertyValues().add("name", value)** | Gán giá trị thông qua property binding phù hợp |
| Constructor arguments | **getConstructorArgumentValues()** | Khai báo tham số constructor |
| Scope | **setScope("prototype")** | Lựa chọn vòng đời instance |
| Lazy flag | **setLazyInit(true)** | Cho phép trì hoãn tạo singleton khi không có phụ thuộc yêu cầu |
| Depends-on | **setDependsOn("anotherBean")** | Khai báo phụ thuộc vòng đời rõ ràng |

Các API trên hoạt động ở tầng metadata. **Sửa BeanDefinition không tương đương sửa mọi singleton đã được tạo từ trước.** Khi bean đã được khởi tạo, thay đổi definition thường không làm đối tượng đó tự động tạo lại.

### 7.1. Phòng tránh đăng ký trùng tên

Với BeanDefinitionRegistry, nên kiểm tra có cần tránh trùng tên hay không:

~~~java
if (!registry.containsBeanDefinition("dynamicGreeting")) {
    registry.registerBeanDefinition("dynamicGreeting", definition);
}
~~~

Đây là đoạn minh họa, giả định **definition** đã được tạo phù hợp. Đăng ký trùng tên có thể bị từ chối theo chính sách bean overriding hoặc vô tình che cấu hình hiện hữu nếu được cho phép. Không nên ghi đè những bean hạ tầng mà bạn không nắm rõ vai trò.

### 7.2. Duyệt definition có chọn lọc

Một BFPP có thể duyệt metadata:

~~~java
for (String name : beanFactory.getBeanDefinitionNames()) {
    BeanDefinition definition =
            beanFactory.getBeanDefinition(name);

    // Chỉ chỉnh khi bean đúng tên/kiểu/điều kiện mục tiêu.
}
~~~

Không nên đặt **lazy**, scope hoặc property value đại trà lên mọi definition của ứng dụng và thư viện. Những bean hạ tầng của Spring có yêu cầu vòng đời riêng; tác động thiếu kiểm soát có thể làm container không thể khởi động.

## 8. Chọn processor nào cho nhu cầu nào?

| Yêu cầu | Cơ chế phù hợp | Giải thích |
| --- | --- | --- |
| Đăng ký BeanDefinition mới trước khi BFPP chạy | **BeanDefinitionRegistryPostProcessor** | Có quyền thao tác registry |
| Đổi cấu hình của những definition đã có | **BeanFactoryPostProcessor** | Hoạt động trên metadata trước khi tạo bean |
| Bọc/proxy một bean instance khi được tạo | **BeanPostProcessor** | Nhận callback trước/sau initialization |
| Sinh đối tượng bean theo factory đặc thù | **FactoryBean<T>** | Cung cấp phương thức tạo sản phẩm bean |
| Khai báo một bean ứng dụng bình thường | **@Bean**, **@Component** | Dễ đọc và dễ kiểm thử hơn processor tùy chỉnh |
| Cấu hình bean theo điều kiện của Spring Boot | **@Conditional...**, auto-configuration | Tận dụng cơ chế có sẵn của framework |
| Đăng ký beans từ annotation riêng ở thời điểm xử lý cấu hình | **ImportBeanDefinitionRegistrar** | Phù hợp với pipeline annotation/configuration |

BDRPP và BFPP thích hợp cho **hạ tầng, starter, thư viện tích hợp hoặc thay đổi metadata trên nhiều definition**. Nếu chỉ cần tạo một service đơn giản, khai báo **@Bean** thường dễ bảo trì hơn.

## 9. Quan hệ với Spring Boot auto-configuration

Spring Boot sử dụng chính cơ chế xử lý cấu hình của Spring Framework. **@SpringBootApplication** kích hoạt các thành phần liên quan đến **@Configuration**, **@ComponentScan**, **@EnableAutoConfiguration**. **ConfigurationClassPostProcessor** và các cấu hình hạ tầng tạo ra bean definitions trước khi các BFPP khác xử lý metadata.

Ba điểm cần lưu ý:

1. Điều kiện auto-configuration như **@ConditionalOnMissingBean** được đánh giá ở thời điểm xử lý cấu hình. Nếu một bean được BDRPP đăng ký **quá muộn**, không nên giả định framework sẽ đánh giá lại mọi điều kiện đã hoàn tất trước đó.
2. Processor tự viết có thể sửa metadata do auto-configuration tạo, nhưng phải biết processor nào còn chạy sau đó và có khả năng sửa cùng definition.
3. Một BDRPP/BFPP thuộc **một ApplicationContext cụ thể**. Trong hệ thống có parent/child contexts, processor của context này không mặc nhiên xử lý mọi definition của context khác.

Trong hệ sinh thái Boot, hãy ưu tiên **@Conditional...**, **@ConfigurationProperties**, **@Bean**, **ImportBeanDefinitionRegistrar** hoặc cơ chế tùy biến chính thức khi đủ dùng; chỉ chạm trực tiếp BeanDefinition khi bài toán thật sự cần.

## 10. Những lỗi phổ biến và cách tránh

### 10.1. Nhầm BFPP với BeanPostProcessor

**Triệu chứng:** muốn sửa giá trị field của instance trong BFPP, hoặc tưởng BFPP được gọi sau khi từng bean được tạo. **Cách sửa:** BFPP xử lý metadata; BPP và callback vòng đời phù hợp xử lý instance.

### 10.2. BFPP dùng @Autowired để kéo service ứng dụng vào quá sớm

**Triệu chứng:** service bị tạo trước toàn bộ BPP/AOP, log cho biết bean không đủ điều kiện nhận tất cả post-processors. **Cách sửa:** giữ BFPP gần như chỉ phụ thuộc vào metadata, Environment hoặc hạ tầng giai đoạn sớm; tránh gọi **getBean** trên service thông thường.

### 10.3. @Bean trả về BFPP nhưng không static

**Triệu chứng:** Spring cảnh báo phương thức **@Bean** không static hoặc annotation trên configuration class xử lý không trọn vẹn. **Cách sửa:** khai báo **static @Bean** khi có thể.

### 10.4. BDRPP chỉ triển khai callback registry

Vì BDRPP kế thừa BFPP, implementation vẫn phải có **postProcessBeanFactory**. Nếu không có việc xử lý ở pha factory, hãy để callback rỗng; đừng gọi lại registry callback từ đó.

### 10.5. Phụ thuộc thứ tự các processor không được bảo đảm

**Triệu chứng:** ở môi trường này processor nhìn thấy definition, sang môi trường khác lại không. **Cách sửa:** xét **PriorityOrdered/Ordered**, nhóm processor đã đăng ký theo chương trình, việc CCPP được ưu tiên và những dependency khác trong classpath. Không xem thứ tự khai báo method là hợp đồng.

### 10.6. Đăng ký definition sau ApplicationReadyEvent và mong BFPP chạy lại

Các callback BFPP của lần **refresh** đã hoàn tất. Thêm/sửa registry ở runtime không làm framework tự chạy lại pipeline và không thay instance đã tạo. Với nhu cầu thay đổi runtime, cần thiết kế cơ chế quản lý riêng.

### 10.7. Tưởng BeanDefinition là một instance đang hoạt động

Một **RootBeanDefinition** mới chỉ là bản mô tả cách tạo bean. Trước thời điểm khởi tạo, constructor của lớp đích chưa nhất thiết chạy. Việc tra cứu **getBeanDefinition** không cho phép gọi method nghiệp vụ trên bean.

### 10.8. Can thiệp hạ tầng mà không kiểm tra AOT/native

Các custom registration/post-processing có thể hoạt động khác khi build AOT/native, nhất là code phụ thuộc reflection hoặc class được lựa chọn động. Với ứng dụng cần native image, kiểm chứng trực tiếp theo hợp đồng AOT của phiên bản Spring Boot sử dụng.

## 11. Cách kiểm chứng và debug khi startup có lỗi

Khi chẩn đoán, nên phân loại lỗi theo pha: **đăng ký definition**, **factory metadata**, **đăng ký BPP**, hoặc **tạo bean instance**.

Một cách quan sát hữu ích là ghi log có chọn lọc ở ba điểm:

~~~text
REGISTRY: postProcessBeanDefinitionRegistry
FACTORY:  postProcessBeanFactory
BEAN:     constructor / initialization
~~~

Sau đó kiểm tra definition cụ thể bằng **containsBeanDefinition**, **getBeanDefinition** và metadata của nó. Tránh dùng **getBean()** chỉ để xem thử vì việc đó tự thay đổi thời điểm khởi tạo và có thể che lỗi gốc.

Khi có nhiều processor, xem class implements **PriorityOrdered/Ordered**, cách đăng ký, stack trace và log của Spring. Bật log phù hợp cho từng package thay vì in toàn bộ bean definitions. Nếu lỗi liên quan auto-configuration, báo cáo condition evaluation của Spring Boot có thể giúp hiểu vì sao một bean definition được/chưa được đăng ký.

### Những câu hỏi cần trả lời khi debug

- Processor của bạn đã được tạo và Spring nhận diện như BDRPP/BFPP chưa?
- Callback **registry** và callback **factory** có được gọi, theo thứ tự nào?
- BeanDefinition mục tiêu đã tồn tại **ở thời điểm** processor xử lý chưa?
- Có processor khác ghi đè/sửa lại metadata sau callback của bạn không?
- Có lệnh **getBean(...)** hoặc dependency nào gây **eager instantiation** trước khi chỉnh xong metadata không?
- Bạn đang debug đúng ApplicationContext khi có nhiều context chứ?

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một BDRPP đăng ký definition **auditClient**. BFPP thông thường có thể thay lazy flag của definition đó trong cùng lượt refresh không?

**Đáp án:** Có. Pha registry diễn ra trước pha BFPP; nếu đăng ký thành công và không bị xóa hoặc thay thế, BFPP nhìn thấy definition mới.

**Câu 2.** BDRPP có được callback **postProcessBeanFactory** không?

**Đáp án:** Có. BDRPP kế thừa BFPP nên Spring gọi cả callback registry lẫn callback factory của implementation.

**Câu 3.** Có nên lấy **PaymentService** bằng **beanFactory.getBean(...)** trong BFPP rồi gán field cho service không?

**Đáp án:** Không nên. Điều đó có thể kích hoạt khởi tạo sớm, bỏ qua một số post-processing và làm sai mục đích BFPP. Hãy chỉnh BeanDefinition hoặc sử dụng extension point ở giai đoạn instance.

**Câu 4.** Một BFPP phụ thuộc định nghĩa do BDRPP đăng ký. Có cần tự gọi BFPP từ callback registry để bảo đảm thứ tự?

**Đáp án:** Không. Framework đã có pha registry trước pha factory; gọi callback thủ công có thể dẫn tới xử lý lặp và side effect không mong đợi.

**Câu 5.** Vì sao nên dùng **@Bean static BeanFactoryPostProcessor**?

**Đáp án:** Vì Spring cần tạo BFPP rất sớm. Static method không buộc Spring khởi tạo instance của configuration class trước khi các annotation processor thực hiện đầy đủ công việc.

**Câu 6.** BDRPP đăng ký một **@Configuration** class muộn, chắc chắn ConfigurationClassPostProcessor sẽ quét lại class đó?

**Đáp án:** Không. Cần hiểu thứ tự xử lý và lựa chọn extension mechanism phù hợp; không dựa vào việc pipeline đã hoàn thành tự động chạy lại.

**Câu 7.** Trong code ví dụ, dòng constructor **GreetingService** xuất hiện trước hay sau dòng BFPP sửa metadata?

**Đáp án:** Sau, vì singleton thông thường được tạo ở giai đoạn sau khi BFPP hoàn tất.

## 13. Ghi nhớ và tài liệu chính thức

**BeanDefinitionRegistryPostProcessor thay đổi tập BeanDefinition**, còn **BeanFactoryPostProcessor thay đổi metadata của những BeanDefinition đó**. BDRPP kế thừa BFPP và có hai callback. Spring thực hiện các pha này **trước khi đăng ký đầy đủ BeanPostProcessor và khởi tạo singleton thông thường**, nên những thay đổi đúng lúc sẽ ảnh hưởng đến cách bean được tạo.

Tránh khởi tạo service quá sớm trong processor, chọn **static @Bean** cho processor khi thích hợp, và xác định rõ thứ tự nếu nhiều processor phụ thuộc lẫn nhau.

Nguồn tham khảo chính thức:

- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Framework 6.1 API — BeanDefinitionRegistryPostProcessor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html
- Spring Framework 6.1 API — BeanFactoryPostProcessor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html
- Spring Framework 6.1 API — ConfigurationClassPostProcessor: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/annotation/ConfigurationClassPostProcessor.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html