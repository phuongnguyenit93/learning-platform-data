# Giữ điểm mở rộng gọn, có thể kiểm thử và tránh phụ thuộc bean quá sớm trong Spring Boot

## 1. Vì sao điểm mở rộng cần được thiết kế cẩn thận?

Spring Boot có nhiều **extension point**: listener, initializer, post-processor, lifecycle callback, runner và các cơ chế auto-configuration. Chúng cho phép chèn logic vào lúc ứng dụng đang khởi động, tạo bean, hoàn tất refresh hoặc dừng. Sức mạnh này đi kèm một rủi ro: **một callback chạy sớm hơn vòng đời mà lập trình viên tưởng tượng**.

Ví dụ, nếu một BeanFactoryPostProcessor cố gọi service nghiệp vụ để lấy dữ liệu, service ấy có thể bị tạo trước khi các BeanPostProcessor cần thiết được đăng ký. Một phần cơ chế như AOP proxy hoặc việc xử lý annotation có thể không được áp dụng đầy đủ. Ứng dụng có thể khởi động với trạng thái khó phát hiện lỗi.

Ba nguyên tắc xuyên suốt bài học:

1. **Đúng giai đoạn:** chọn điểm mở rộng theo loại dữ liệu cần thao tác và thời điểm dữ liệu ấy sẵn sàng.
2. **Phụ thuộc tối thiểu:** một callback bootstrap sớm chỉ dùng các API đã sẵn sàng ở giai đoạn của nó; không kéo theo cả hệ thống bean nghiệp vụ.
3. **Logic nhỏ, dễ kiểm thử:** callback chỉ làm nhiệm vụ thích ứng với framework, còn quy tắc tính toán/biến đổi được tách thành hàm hoặc lớp Java độc lập.

Mục tiêu là viết ứng dụng **dự đoán được thứ tự khởi động, dễ kiểm tra lỗi và dễ nâng cấp Spring Boot**, không tạo ra một lớp extension duy nhất làm quá nhiều việc.

## 2. Phân biệt các mốc để chọn đúng extension point

Trước khi viết một callback, cần biết chính xác nó chạy khi nào. Trong Spring Boot 3.3.x (Java 17+), trình tự rút gọn của một lần startup thành công là:

~~~text
SpringApplication.run(...)
    |
    +-- Chuẩn bị Environment và Config Data
    |      +-- EnvironmentPostProcessor
    |      +-- các sự kiện bootstrap sớm
    |
    +-- Tạo ApplicationContext
    +-- ApplicationContextInitializer
    +-- Load các nguồn cấu hình/BeanDefinition
    |
    +-- ApplicationContext.refresh()
    |      +-- BeanDefinitionRegistryPostProcessor
    |      +-- BeanFactoryPostProcessor
    |      +-- Đăng ký BeanPostProcessor
    |      +-- Tạo những singleton không lazy
    |      |      +-- BeanPostProcessor
    |      |      +-- @PostConstruct/InitializingBean
    |      +-- SmartInitializingSingleton (khi phù hợp)
    |      +-- finishRefresh, start SmartLifecycle
    |
    +-- ApplicationStartedEvent
    +-- ApplicationRunner/CommandLineRunner
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    |
    +-- run(...) trả về ConfigurableApplicationContext
~~~

Sơ đồ diễn tả **quan hệ thời điểm quan trọng**, không mô tả đầy đủ mọi hook và auto-configuration nội bộ. Một số bean hạ tầng vẫn phải được tạo trước khi container hoàn tất quá trình đăng ký post-processor. Một tác vụ chạy không đồng bộ có thể tiếp tục sau khi phương thức **run(...)** đã trả về.

**Không được nhầm “context đã tồn tại” với “mọi bean đã sẵn sàng”.** ApplicationContextInitializer nhận context trước khi các bean definition của ứng dụng được tải đầy đủ; BeanFactoryPostProcessor làm việc lúc container đang chuẩn bị cấu hình bean; ApplicationRunner chạy muộn hơn, khi context đã refresh.

### Bảng chọn extension point

| Nhu cầu thực tế | Điểm mở rộng phù hợp | Có nên phụ thuộc service bean? |
| --- | --- | --- |
| Sửa/thêm PropertySource lúc bootstrap | **EnvironmentPostProcessor** | **Không**; chưa có application context được tạo đầy đủ |
| Quan sát sự kiện trước khi context tồn tại | **ApplicationListener** được đăng ký sớm | **Không**; listener dạng bean không nhận được những sự kiện quá sớm |
| Chỉnh ConfigurableApplicationContext trước khi load definitions | **ApplicationContextInitializer** | **Không**; ưu tiên Environment và API context thích hợp |
| Đăng ký BeanDefinition mới sớm | **BeanDefinitionRegistryPostProcessor** | Tránh gọi bean nghiệp vụ |
| Sửa metadata của BeanDefinition | **BeanFactoryPostProcessor** | Tránh gọi **getBean()** để tạo instance |
| Quan sát/bọc instance khi tạo | **BeanPostProcessor** | Hạn chế dependency vì bản thân processor được tạo rất sớm |
| Làm việc sau khi singleton thường đã được tạo | **SmartInitializingSingleton** | Có thể dùng dependency phù hợp, nhưng callback vẫn thuộc refresh |
| Điều phối một thành phần cần start/stop | **SmartLifecycle** | Có thể dùng dependency hợp lý; tránh startup blocking không cần thiết |
| Chạy một công việc đồng bộ sau refresh và trước ready | **ApplicationRunner** hoặc **CommandLineRunner** | **Có**, phù hợp với dependency injection thông thường |
| Phản ứng khi startup đạt ready | Listener **ApplicationReadyEvent** | Có thể dùng bean, nhưng giữ callback ngắn và idempotent khi cần |

Khi chỉ cần áp dụng cấu hình bean thông thường, **@Bean**, **@ConfigurationProperties**, **@Conditional...** hoặc các thiết lập có sẵn của Boot thường đơn giản hơn việc viết một extension point tùy chỉnh.

## 3. Nhận diện phụ thuộc bean quá sớm

### 3.1. Early instantiation xảy ra như thế nào?

Spring cần tạo BeanFactoryPostProcessor và BeanPostProcessor để chúng tham gia vào quá trình chuẩn bị container. Nếu constructor của processor nhận một service ứng dụng, Spring có thể phải tạo service đó **trước khi toàn bộ BeanPostProcessor được đăng ký**.

Ví dụ thiết kế có rủi ro:

~~~java
@Component
class AuditBeanPostProcessor implements BeanPostProcessor {

    private final PaymentService paymentService;

    AuditBeanPostProcessor(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

Đây là **snippet minh họa**; giả định **PaymentService** là một bean nghiệp vụ đã được khai báo và có import tương ứng. Nguy cơ nằm ở dependency **PaymentService**: để tạo processor, Spring phải giải quyết dependency và có thể tạo service trong pha rất sớm. Service đó có thể chưa đủ điều kiện nhận mọi post-processing, như auto-proxy cho giao dịch hoặc AOP.

Spring Framework có cảnh báo điển hình:

~~~text
Bean 'someBean' of type [...] is not eligible for getting
processed by all BeanPostProcessors
(for example: not eligible for auto-proxying)
~~~

Cảnh báo này cần được xem xét cùng dependency graph. Nó **không chứng minh chắc chắn một nghiệp vụ đã lỗi**, nhưng cho thấy bean bị khởi tạo ở giai đoạn có thể chưa được xử lý đầy đủ bởi tất cả BeanPostProcessor.

### 3.2. Tránh gọi getBean() trong BeanFactoryPostProcessor

Mục đích của **BeanFactoryPostProcessor** là xử lý **metadata**:

~~~java
BeanDefinition definition =
        beanFactory.getBeanDefinition("reportService");

definition.setLazyInit(true);
~~~

Đừng thay bằng cách này chỉ để lấy dữ liệu:

~~~java
ReportService service =
        beanFactory.getBean("reportService", ReportService.class);
~~~

Đoạn thứ hai có thể kích hoạt tạo ReportService ngay trong lúc BFPP đang chạy. Hậu quả tiềm ẩn: bỏ qua một phần BeanPostProcessor, proxy chưa hình thành, vòng phụ thuộc xuất hiện sớm hoặc thứ tự khởi tạo bị sai.

Nếu cần sửa **BeanDefinition**, thao tác trên BeanDefinition. Nếu cần gọi **service nghiệp vụ**, chọn **ApplicationRunner**, một bean thông thường hoặc callback sau khi container đã chuẩn bị đầy đủ.

### 3.3. ObjectProvider và @Lazy không tự xóa vấn đề vòng đời

**ObjectProvider<MyService>** có thể giúp trì hoãn việc tra cứu dependency cho đến khi gọi **getObject()**. **@Lazy** có thể dùng proxy hoặc trì hoãn việc tạo instance. Tuy nhiên, nếu callback bootstrap vẫn **gọi getObject() hoặc dùng proxy ngay lúc đó**, bean có thể vẫn bị tạo quá sớm.

Ví dụ:

~~~java
final class StartupHook {

    private final ObjectProvider<ReportService> serviceProvider;

    StartupHook(ObjectProvider<ReportService> serviceProvider) {
        this.serviceProvider = serviceProvider;
    }

    void tooEarly() {
        serviceProvider.getObject().runReport();
    }
}
~~~

Đây là đoạn minh họa cần import và các lớp liên quan; nó cho thấy việc **trì hoãn tra cứu không có tác dụng nếu lập trình viên chủ động gọi trong pha bootstrap sớm**. Giải pháp nền tảng vẫn là chọn callback ở đúng mốc vòng đời.

## 4. Cách thiết kế callback nhỏ và giới hạn trách nhiệm

Một extension point tốt thường là một **adapter mỏng** giữa Spring Boot và logic ứng dụng:

~~~text
Spring Boot lifecycle callback
           |
           | lấy đúng input đã sẵn sàng
           v
Hàm/lớp xử lý thuần Java
           |
           | trả về kết quả/metadata
           v
Áp dụng thay đổi có giới hạn vào API phù hợp
~~~

Nên xác định rõ bốn câu hỏi:

1. **Input** là gì? Environment property, bean definition, application event hay bean instance?
2. **Output** là gì? Một PropertySource, BeanDefinition, log/số liệu, quyết định start/stop hay kết quả kiểm tra?
3. **Side effect** nào được phép? Chỉ sửa đúng property/bean cần thiết, không chạm global state không liên quan.
4. **Khi nào lỗi cần chặn startup?** Phân biệt cấu hình bắt buộc với tác vụ phụ trợ có thể báo lỗi và xử lý sau.

Thực hành hữu ích:

- Mỗi callback nên có **một nhiệm vụ chính**, tên phản ánh đúng mục đích.
- Không biến callback thành nơi gọi HTTP, database, cache, file I/O phức tạp khi giai đoạn bootstrap chưa thật sự cần.
- Không tạo thread nền tùy ý trong các processor chỉ để né việc phải chờ; lifecycle và shutdown sẽ khó quản lý.
- Chỉ đụng vào bean definition được xác định rõ tên/kiểu, thay vì quét rồi sửa tất cả.
- Không in token, mật khẩu hay toàn bộ Environment khi debug startup.
- Nếu cần thứ tự giữa nhiều processor hoặc runner, dùng **Ordered**, **PriorityOrdered** hoặc **@Order** đúng nơi và có test xác minh thứ tự cần thiết.
- Viết logic có thể chạy lại an toàn khi callback bị kích hoạt hơn một lần trong ngữ cảnh có nhiều ApplicationContext hoặc test khởi động lặp lại.

**Idempotent** nghĩa là chạy lại cùng một thao tác trong cùng điều kiện không tạo thêm tác động ngoài dự kiến. Ví dụ thêm một PropertySource với tên cố định cần xem xét đã tồn tại hay chưa; listener gửi thông báo cho một sự kiện cần tránh gửi trùng nếu có nhiều context hoặc lần retry.

## 5. Chọn đúng thời điểm để dùng bean dependency

### 5.1. Giai đoạn rất sớm: Environment và context bootstrap

**EnvironmentPostProcessor** (Spring Boot 3.3) chạy trước refresh và có hợp đồng:

~~~java
void postProcessEnvironment(
        ConfigurableEnvironment environment,
        SpringApplication application);
~~~

Triển khai của nó thường được đăng ký qua **META-INF/spring.factories**, không thông qua **@Component** hay **@Bean** để nhận một service ứng dụng. Có thể dùng để bổ sung PropertySource từ nguồn cấu hình thích hợp; không nên cố inject các bean như Repository hoặc RestClient.

**ApplicationContextInitializer** nhận **ConfigurableApplicationContext** trước khi tải toàn bộ bean definitions. Nó có thể đọc Environment, đăng ký một số thành phần hạ tầng ở mức metadata hoặc điều chỉnh context trong hợp đồng cho phép. Đây chưa phải nơi lấy một service bằng **context.getBean(MyService.class)**.

Một số **ApplicationListener** nhận sự kiện trước khi context được tạo, ví dụ **ApplicationStartingEvent** hoặc **ApplicationEnvironmentPreparedEvent**. Listener cần xử lý các sự kiện đó phải được **đăng ký từ trước** bằng **SpringApplication.addListeners(...)** hoặc cấu hình bootstrap phù hợp; listener là **@Bean** chỉ được phát hiện khi container đã bắt đầu xử lý bean definitions, nên không thể dùng cho tất cả sự kiện sớm.

### 5.2. Giai đoạn xử lý BeanDefinition

**BeanDefinitionRegistryPostProcessor** là điểm mở rộng để tạo/xóa/sửa BeanDefinition trong registry, còn **BeanFactoryPostProcessor** sửa metadata của bean definitions hiện có. Cả hai chạy trước phần lớn quá trình tạo singleton thông thường.

Một BFPP gọn có thể chỉ thay đổi một definition:

~~~java
@Configuration(proxyBeanMethods = false)
class OptionalReportConfiguration {

    @Bean
    static BeanFactoryPostProcessor optionalReportLazyPolicy() {
        return factory -> {
            if (factory.containsBeanDefinition("optionalReport")) {
                factory.getBeanDefinition("optionalReport")
                       .setLazyInit(true);
            }
        };
    }
}
~~~

Đây là **một lớp cấu hình dùng bên trong ứng dụng Spring Boot**, giả định có BeanDefinition tên **optionalReport**. Cần import **@Configuration**, **@Bean** và **BeanFactoryPostProcessor**. Code không truy vấn instance bằng getBean, không đụng các bean ngoài phạm vi và có thể được kiểm thử bằng metadata.

**Vì sao static @Bean?** Framework phải tạo BFPP từ rất sớm. Một **@Bean non-static** có thể buộc tạo sớm instance của configuration class chứa method, dẫn đến việc **@Autowired**, **@Value**, **@PostConstruct** trên configuration class không được xử lý theo vòng đời đầy đủ. Spring Framework khuyến nghị **static @Bean** cho những factory method trả về BFPP.

Tương tự, khi tự khai báo **BeanPostProcessor** qua **@Bean**, nên ưu tiên method **static**, dependency tối thiểu, và khai báo kiểu trả về đủ rõ để Spring tự phát hiện processor sớm.

### 5.3. Giai đoạn muộn: runner và lifecycle của bean

**ApplicationRunner** hoặc **CommandLineRunner** được gọi sau khi context refresh thành công và trước **ApplicationReadyEvent**. Chúng phù hợp để dùng service đã được DI bình thường, thực hiện kiểm tra cấu hình cần thiết hoặc chạy bước bootstrap nghiệp vụ ngắn.

**SmartLifecycle** phù hợp khi thành phần phải **start/stop** theo vòng đời context; cần hiểu nó có thể được start trong quá trình refresh, trước các runner. Nếu component cần giữ tài nguyên lâu dài, cấu hình shutdown hợp lý, xử lý lỗi và tránh start những tác vụ không có giới hạn.

**ApplicationReadyEvent** là mốc muộn hơn runner. Listener mặc định xử lý sự kiện đồng bộ, nên tác vụ quá lâu trong listener có thể làm chậm hoàn tất readiness. Không nhầm **ApplicationStartedEvent** (sau refresh, trước runner) với **ApplicationReadyEvent** (sau runner).

## 6. Ví dụ Java 17+ chạy được: initializer mỏng, logic thuần, runner dùng DI

Bài toán: cung cấp một giá trị **demo.message** mặc định nếu người vận hành không cấu hình, chuẩn hóa khoảng trắng của chuỗi, sau đó in kết quả trong một runner. Phần bootstrap **chỉ đăng ký nguồn cấu hình**; phần biến đổi chuỗi là Java thuần; runner **được inject dependency sau refresh**.

Yêu cầu: **Spring Boot 3.3.x**, **Java 17+**, dependency **spring-boot-starter**, một dự án có Spring Boot Gradle plugin. Tạo file:

**src/main/java/com/example/runtime/LeanExtensionApplication.java**

~~~java
package com.example.runtime;

import java.util.Map;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;

@SpringBootApplication
public class LeanExtensionApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LeanExtensionApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        app.addInitializers(context -> {
            Map<String, Object> defaults = Map.of(
                    "demo.message", "  Hello   Spring Boot  ");

            context.getEnvironment().getPropertySources()
                   .addLast(new MapPropertySource("demoDefaults", defaults));
        });

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    @Bean
    MessageFormatter messageFormatter() {
        return new MessageFormatter();
    }

    @Bean
    ApplicationRunner messageRunner(
            MessageFormatter formatter, Environment environment) {

        return args -> {
            String raw = environment.getRequiredProperty("demo.message");
            System.out.println("RUNNER | " + formatter.normalize(raw));
        };
    }

    static final class MessageFormatter {

        String normalize(String value) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "Message must not be blank");
            }
            return value.strip().replaceAll("\\s+", " ");
        }
    }
}
~~~

Chạy từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Trong lần chạy không có giá trị **demo.message** ở PropertySource ưu tiên cao hơn, **các dòng do chương trình chủ động in ra** có nội dung và thứ tự kỳ vọng:

~~~text
RUNNER | Hello Spring Boot
MAIN | active=true
~~~

Log từ framework có thể xen giữa. Vì ví dụ chạy **WebApplicationType.NONE**, context được đóng bởi **try-with-resources** sau phép quan sát. Đây là vòng đời phù hợp với chương trình CLI ngắn, không phải mẫu đóng context ngay sau **run(...)** cho ứng dụng web phục vụ lâu dài.

### 6.1. Vì sao initializer này an toàn ở giai đoạn sớm?

Callback:

~~~java
app.addInitializers(context -> {
    context.getEnvironment().getPropertySources()
           .addLast(new MapPropertySource("demoDefaults",
                    Map.of("demo.message", "  Hello   Spring Boot  ")));
});
~~~

chỉ dùng **Environment** đã hiện diện trong context, tạo một **MapPropertySource** nhỏ bằng dữ liệu Java thuần, không gọi **context.getBean(...)**, không mở kết nối database và không yêu cầu repository hay service.

Dùng **addLast(...)** cho PropertySource mặc định nhằm đặt nó ở mức ưu tiên thấp hơn các nguồn đã có. Vì thế giá trị được cung cấp từ cấu hình bên ngoài hoặc CLI có thể ghi đè mặc định này theo thứ tự PropertySource thông thường.

Muốn giữ việc đăng ký PropertySource có tính idempotent nếu initializer có khả năng được gọi lại trên một Environment, có thể kiểm tra tên trước khi thêm:

~~~java
var sources = context.getEnvironment().getPropertySources();
if (!sources.contains("demoDefaults")) {
    sources.addLast(new MapPropertySource(
            "demoDefaults", Map.of("demo.message", "  Hello   Spring Boot  ")));
}
~~~

Đây là snippet đặt **bên trong initializer** trong ứng dụng đã import MapPropertySource và Map.

### 6.2. Vì sao logic normalize nằm trong MessageFormatter?

**MessageFormatter.normalize(...)** chỉ phụ thuộc vào input String, không biết SpringApplication, BeanFactory, ApplicationContext hoặc Environment. Do đó:

- Có thể kiểm tra các case khoảng trắng, đầu vào trống, Unicode mà **không khởi động Spring**.
- Thay đổi quy tắc định dạng không tác động cách Boot đăng ký PropertySource.
- Không phải mock ApplicationContext chỉ để kiểm thử một phép biến đổi chuỗi.
- Thông báo lỗi **Message must not be blank** xuất phát từ logic riêng, có thể kiểm tra bằng một unit test.

Việc dùng **@Bean MessageFormatter** chỉ là cách kết nối logic thuần với DI. Nếu dự án lớn hơn, đặt MessageFormatter thành một tệp riêng, giữ nó không phụ thuộc API của Spring.

### 6.3. Vì sao ApplicationRunner có thể phụ thuộc MessageFormatter?

Spring chỉ gọi **messageRunner** sau khi context đã refresh và những BeanPostProcessor cần thiết đã được đăng ký. Runner nhận **MessageFormatter** và **Environment** bằng dependency injection thông thường; nó không ép tạo một service nghiệp vụ ngay trong giai đoạn BeanFactoryPostProcessor hoặc ApplicationContextInitializer.

Dòng **MAIN** xuất hiện sau **RUNNER** vì **SpringApplication.run(...)** chỉ trả về sau khi callback runner đồng bộ hoàn tất thành công.

Chạy lại với tham số:

~~~bash
./gradlew bootRun --args='--demo.message=  Alternate   greeting  '
~~~

Do cách shell truyền khoảng trắng khác nhau, đây là ví dụ ý tưởng; để truyền giá trị chứa khoảng trắng chắc chắn, nên dùng dấu quote cho toàn bộ argument phù hợp với shell. Chẳng hạn trên Linux/macOS:

~~~bash
./gradlew bootRun --args="--demo.message='  Alternate   greeting  '"
~~~

Kết quả dự kiến sau khi tham số được truyền đúng là **RUNNER | Alternate greeting**. Đừng dùng thay đổi cấu hình để xác nhận thứ tự lifecycle nếu shell chưa truyền đúng giá trị.

## 7. Unit test thuần Java và integration test cần có giới hạn

### 7.1. Unit test không tạo ApplicationContext

Với **spring-boot-starter-test** (JUnit Jupiter), tạo file:

**src/test/java/com/example/runtime/MessageFormatterTest.java**

~~~java
package com.example.runtime;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MessageFormatterTest {

    private final LeanExtensionApplication.MessageFormatter formatter =
            new LeanExtensionApplication.MessageFormatter();

    @Test
    void normalizesExtraWhitespace() {
        String result = formatter.normalize("  Hello   Spring Boot  ");
        assertEquals("Hello Spring Boot", result);
    }

    @Test
    void rejectsBlankMessage() {
        assertThrows(IllegalArgumentException.class,
                () -> formatter.normalize("   "));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Các test này kiểm tra **đúng logic biến đổi** mà không cần mở web server, load toàn bộ auto-configuration hoặc tạo database. Việc class formatter là một **static nested class** cho phép test cùng package truy cập trực tiếp mà không cần Spring test runner.

### 7.2. Kiểm thử wiring và lifecycle ở mức phù hợp

Unit test ở trên chưa chứng minh rằng Spring Boot gọi initializer hoặc runner theo dự kiến. Khi cần kiểm tra tích hợp:

- Dùng **@SpringBootTest** để kiểm tra context thực sự khởi động và dependency injection hoạt động trong một ứng dụng đầy đủ.
- Dùng **ApplicationContextRunner** (thuộc spring-boot-test) để kiểm tra cấu hình bean, điều kiện auto-configuration hoặc metadata trong context gọn. **ApplicationContextRunner không tự chạy toàn bộ quy trình SpringApplication.run và các ApplicationRunner**; đừng kỳ vọng nó xác minh trực tiếp event/runner.
- Nếu cần kiểm tra callback thật sự chạy ở mốc bootstrap sớm, dựng một **SpringApplication** nhỏ với initializer/listener rồi kiểm tra tác động trên Environment hoặc context sau khi chạy.
- Chỉ mock những phụ thuộc I/O cần thiết. Đừng mock toàn bộ BeanFactory khi mục tiêu thật sự là xác nhận Spring có nhận diện BeanDefinition/PostProcessor hay không.

**Các test khác nhau bảo vệ các hợp đồng khác nhau**: unit test cho thuật toán, context test cho wiring/metadata, startup test cho thứ tự lifecycle. Không cần test nhiều tầng chỉ để lặp lại cùng một khẳng định.

### 7.3. Ví dụ kiểm tra một BeanFactoryPostProcessor không ép tạo bean

Giả sử có BFPP đổi lazy flag cho definition **optionalReport**. Unit test khả dụng có thể tạo **DefaultListableBeanFactory**, đăng ký **RootBeanDefinition**, gọi processor bằng factory đó rồi kiểm tra **isLazyInit()**. Cách này không đòi hỏi tạo **optionalReport**.

Các bước logic:

~~~text
DefaultListableBeanFactory
   -> registerBeanDefinition("optionalReport", ...)
   -> processor.postProcessBeanFactory(beanFactory)
   -> assertTrue(beanFactory.getBeanDefinition("optionalReport").isLazyInit())
~~~

Đây là sơ đồ quy trình test, không phải code Java độc lập. Với một BDRPP có logic phụ thuộc nhiều processor khác, nên có thêm kiểm thử context thật để phát hiện vấn đề thứ tự registry.

## 8. Tránh side effect và công việc quá nặng trong callback

Một hook được gọi trong startup thường ảnh hưởng trực tiếp đến **thời gian khởi động**, khả năng phục hồi và readiness. Những công việc cần cân nhắc:

| Tác vụ | Tại sao nguy hiểm khi đưa vào hook sớm? | Hướng xử lý |
| --- | --- | --- |
| Gọi HTTP API bên ngoài trong BFPP | Network timeout có thể giữ cả refresh hoặc làm startup thất bại | Cấu hình bằng metadata; gọi I/O ở service/runtime thích hợp |
| Truy cập database trong ApplicationContextInitializer | DataSource/Repository chưa được tạo đầy đủ | Chuyển sang runner hoặc service sau refresh nếu việc đó là điều kiện startup |
| Tạo thread tùy ý trong BeanPostProcessor | Khó quản lý start/stop và kiểm thử | Dùng task executor hoặc thành phần có lifecycle rõ |
| In toàn bộ Environment để debug | Có thể lộ thông tin nhạy cảm và tạo log lớn | Chỉ log các key được phép, ẩn secrets |
| Duyệt rồi sửa mọi BeanDefinition | Dễ tác động bean hạ tầng ngoài mục tiêu | Giới hạn tên/kiểu, xác nhận điều kiện |
| Gửi thông báo ở ApplicationReadyEvent | Có thể chậm readiness, gửi trùng trong multi-context | Thiết kế callback ngắn, deduplicate, xử lý nền có kiểm soát |

Nếu **một tác vụ phải hoàn tất để ứng dụng sẵn sàng**, runner đồng bộ có thể là một lựa chọn, nhưng cần có timeout, xử lý lỗi rõ và tiêu chí vận hành thích hợp. Nếu tác vụ có thể chạy sau khi ứng dụng sẵn sàng, dùng service hoặc cơ chế background được quản lý, đừng giữ một callback sớm lâu chỉ vì tiện.

Không nên **nuốt exception** của cấu hình bắt buộc rồi công bố readiness thành công. Ngược lại, lỗi của một tác vụ phụ trợ không thiết yếu nên được xử lý theo chính sách đã định, tránh biến mọi gián đoạn nhỏ thành lỗi khởi động toàn bộ ứng dụng.

## 9. Quy tắc kiểm thử lỗi và mốc thất bại

Một extension point được viết tốt cần có hợp đồng lỗi rõ ràng:

**Đối với logic thuần:** đầu vào không hợp lệ nên gây exception cụ thể như **IllegalArgumentException** hoặc trả về kiểu kết quả được định nghĩa rõ. Test đầy đủ đầu vào rỗng, null, Unicode, trùng key và thứ tự ưu tiên.

**Đối với BeanDefinition:** không sửa definition khi không tồn tại; nếu bắt buộc phải có, ném lỗi rõ ràng kèm bean name, không gọi getBean() để thử rồi khiến Spring khởi tạo sớm.

**Đối với bootstrap config:** cân nhắc property override và môi trường triển khai. Nếu đặt default, dùng mức ưu tiên thấp; nếu bảo vệ một invariant, validate và ghi lỗi rõ thay vì âm thầm ghi đè cấu hình operator.

**Đối với runner:** lỗi đồng bộ có thể làm **SpringApplication.run(...)** thất bại và phát **ApplicationFailedEvent**. Cần quyết định tác vụ có thật sự là điều kiện startup hay không trước khi đưa nó vào runner.

**Đối với event listener:** Spring Boot mặc định phát nhiều event bằng cơ chế đồng bộ; một listener rất chậm có thể trì hoãn mốc sẵn sàng. Với parent/child context, listener ở parent có thể nhận event từ child nên cần lọc đúng context khi event có thể xuất hiện nhiều lần.

Nên log **tên callback, mốc lifecycle, tên bean/property liên quan và nguyên nhân lỗi**. Không log những giá trị nhạy cảm. Nếu nhiều processor thao tác cùng metadata, ghi rõ thứ tự dựa trên **PriorityOrdered/Ordered** hoặc điều kiện đã xác định.

## 10. Dấu hiệu thiết kế kém và cách refactor

### 10.1. Một initializer có quá nhiều trách nhiệm

**Trước:** initializer đọc Environment, gọi endpoint xác thực, tạo DataSource thủ công, tải danh sách khách hàng và đăng ký trực tiếp nhiều singleton.

**Sau:** initializer chỉ nạp hoặc đăng ký cấu hình bootstrap thật sự cần sớm. Logic validate/biến đổi được chuyển thành Java thuần; DataSource do auto-configuration hoặc bean thông thường quản lý; tác vụ nghiệp vụ chạy ở mốc phù hợp với dependency.

Lợi ích: không tạo vòng phụ thuộc, giảm tác vụ trước refresh, có thể kiểm thử từng bước.

### 10.2. BeanPostProcessor phụ thuộc service có @Transactional

**Trước:** BPP nhận một **OrderService** có **@Transactional** qua constructor và gọi nó ngay để lấy danh sách cấu hình.

**Vấn đề:** để tạo BPP, OrderService có thể phải được tạo sớm và không được auto-proxy đầy đủ. Các giả định về transaction/AOP có thể sai.

**Sau:** tách phần quy tắc nhỏ cần cho BPP thành class Java thuần hoặc metadata an toàn, không yêu cầu service đang chạy. Nếu cần gọi OrderService thực sự, thực hiện ở một callback sau refresh như runner hoặc trong luồng xử lý nghiệp vụ.

Không cố chữa bằng **@Lazy** rồi gọi dependency ngay trong constructor của BPP.

### 10.3. BeanFactoryPostProcessor sửa instance

**Trước:** BFPP lấy bean bằng **getBean()**, sau đó gọi setter trên instance.

**Sau:** nếu thay đổi cần có trước khi tạo bean, sửa property metadata qua **getBeanDefinition()**; nếu logic phải làm việc trên instance, dùng BPP/lifecycle phù hợp.

### 10.4. Callback phụ thuộc thứ tự ngẫu nhiên

**Trước:** hai processor chỉnh cùng BeanDefinition và kỳ vọng Spring sẽ gọi theo thứ tự tên method **@Bean** trong source.

**Sau:** phân tách rõ mục đích, tránh ghi đè lẫn nhau; khai báo **Ordered/PriorityOrdered** khi phù hợp và test thứ tự quan trọng. Nếu hai bước luôn phải cùng thực thi, gộp chúng để giảm phụ thuộc vào sắp xếp.

### 10.5. Listener cho event sớm được khai báo bằng @Component

**Trước:** một **@Component ApplicationListener<ApplicationEnvironmentPreparedEvent>** được kỳ vọng thấy sự kiện trước khi context tạo.

**Vấn đề:** listener là bean chưa được phát hiện tại thời điểm event sớm ấy.

**Sau:** đăng ký listener bằng **SpringApplication.addListeners(...)** trước run hoặc cơ chế bootstrap được Boot hỗ trợ; nếu chỉ cần đọc Environment sau refresh, chọn callback muộn hơn và inject dependency bình thường.

### 10.6. Tác vụ rất lâu trong ApplicationReadyEvent

**Trước:** listener ready chạy migration dữ liệu, kết nối nhiều API và làm đầy cache trước khi trả về.

**Vấn đề:** event listener mặc định đồng bộ; readiness có thể bị trì hoãn, lỗi khó tách biệt với startup.

**Sau:** nếu công việc là điều kiện readiness, đặt nó vào một bước startup có timeout/chính sách lỗi và đo thời gian rõ ràng. Nếu không phải điều kiện readiness, chuyển nó sang thành phần nền có quản lý, có khả năng shutdown và retry.

## 11. Khung lựa chọn khi triển khai extension point thật

Trước khi thêm một extension point mới, đi theo luồng sau:

1. **Xác định mục tiêu:** điều chỉnh cấu hình, đăng ký BeanDefinition, thay đổi instance, chạy logic lúc startup hay quản lý lifecycle?
2. **Chọn mốc sớm nhất thực sự cần:** một tác vụ có thể chạy sau refresh thì không cần đặt vào BFPP.
3. **Liệt kê dependency bắt buộc:** nếu có Repository, transaction manager, HTTP client hoặc proxy service, nên ưu tiên điểm mở rộng muộn.
4. **Tách logic thuần:** nhận dữ liệu đơn giản, trả về kết quả cụ thể; không truyền ApplicationContext vào mọi lớp.
5. **Giới hạn side effect:** chỉ thay đổi đúng bean/property được chỉ định và kiểm soát retry/idempotence.
6. **Thiết kế lỗi có chủ đích:** điều gì chặn startup, điều gì ghi cảnh báo, điều gì được xử lý sau?
7. **Kiểm thử đúng tầng:** unit test thuật toán, context test wiring/metadata, startup test callback/order khi thật sự có yêu cầu.
8. **Theo dõi runtime:** log gọn và an toàn, xem warning early initialization và đo startup khi cần.

### Checklist tự đánh giá

- [ ] Callback thực thi ở giai đoạn input của nó đã sẵn sàng.
- [ ] Không gọi **getBean(...)** trong BFPP chỉ để truy cập service.
- [ ] BPP/BFPP đăng ký bằng **static @Bean** hoặc cơ chế hợp lệ khác khi cần.
- [ ] Không đưa service proxy/AOP vào dependency trực tiếp của BPP sớm.
- [ ] Logic biến đổi/validate có thể test mà không cần chạy Spring.
- [ ] Không sửa BeanDefinition hoặc PropertySource ngoài phạm vi.
- [ ] Thứ tự giữa các callback phụ thuộc nhau có hợp đồng rõ.
- [ ] Event listener xử lý đúng context, không phát side effect trùng.
- [ ] Lỗi và timeout có quy tắc rõ, không che giấu startup failure.
- [ ] Tác vụ nền có cơ chế dừng và không phụ thuộc vào callback sớm.

## 12. Bài tự kiểm tra

**Câu 1.** Vì sao một **BeanPostProcessor** không nên inject thẳng **PaymentService** có **@Transactional** trong constructor?

**Đáp án:** Để tạo processor sớm, Spring có thể tạo PaymentService trước khi auto-proxy và tất cả BPP đã sẵn sàng. Điều đó có nguy cơ khiến service không được áp dụng đầy đủ cơ chế proxy/annotation như dự kiến.

**Câu 2.** **ObjectProvider<PaymentService>** có giải quyết hoàn toàn lỗi early instantiation nếu BFPP gọi **getObject()** ngay trong callback không?

**Đáp án:** Không. ObjectProvider chỉ trì hoãn việc lấy dependency; gọi getObject() sớm vẫn có thể khởi tạo service ở thời điểm quá sớm.

**Câu 3.** Bạn cần đổi **BeanDefinition.setLazyInit(true)** cho một bean cụ thể trước khi bean được tạo. Nên dùng BFPP hay ApplicationReadyEvent?

**Đáp án:** **BeanFactoryPostProcessor**; ApplicationReadyEvent đến khi context đã refresh và quá muộn để thay đổi metadata khởi tạo của singleton đã tạo.

**Câu 4.** Muốn xác nhận thuật toán chuẩn hóa khoảng trắng có đúng không, có cần @SpringBootTest?

**Đáp án:** Không. Kiểm thử trực tiếp **MessageFormatter.normalize** bằng JUnit là đủ cho thuật toán đó. Cần integration/startup test riêng khi muốn xác minh cách Spring gọi initializer/runner.

**Câu 5.** Một **@Bean ApplicationListener<ApplicationStartingEvent>** có được bảo đảm nhìn thấy sự kiện starting của lần khởi động đó không?

**Đáp án:** Không. Event starting được phát trước lúc context chứa listener bean được tạo và đăng ký. Cần đăng ký listener từ trước lúc **run(...)** bắt đầu.

**Câu 6.** ApplicationRunner nhận service bằng constructor injection rồi chạy trước **ApplicationReadyEvent** có đúng vòng đời không?

**Đáp án:** Có. Runner là bean được gọi sau refresh, khi dependency injection thông thường đã được thiết lập; tác vụ đồng bộ của runner cần hoàn tất trước mốc ready của lần khởi động thành công.

**Câu 7.** Một callback thêm PropertySource có giá trị mặc định có nên dùng **addFirst** để luôn thắng mọi cấu hình của người vận hành không?

**Đáp án:** Thông thường không. Đối với giá trị mặc định, dùng mức ưu tiên thấp như **addLast** để cấu hình của operator vẫn có thể ghi đè.

**Câu 8.** Nếu **ApplicationContextRunner** tạo được bean của bạn, điều đó chứng minh **ApplicationRunner.run** đã chạy?

**Đáp án:** Không. ApplicationContextRunner kiểm thử context/configuration; nó không tái hiện đầy đủ cơ chế SpringApplication gọi các runner. Muốn kiểm chứng mốc đó cần một startup test tương ứng.

## 13. Ghi nhớ và tài liệu chính thức

Điểm mở rộng tốt trong Spring Boot **được đặt ở mốc vòng đời hợp lý, chỉ lấy dependency đã sẵn sàng và tập trung vào một nhiệm vụ cụ thể**. Những callback sớm như **EnvironmentPostProcessor**, **ApplicationContextInitializer**, **BeanDefinitionRegistryPostProcessor** và **BeanFactoryPostProcessor** nên thao tác chủ yếu với Environment/metadata. BeanPostProcessor cũng cần dependency tối thiểu để tránh kéo các service vào pha tạo bean quá sớm.

Khi cần logic nghiệp vụ có DI đầy đủ, hãy ưu tiên callback muộn như **ApplicationRunner** hoặc một service bình thường. Tách thuật toán thành Java thuần giúp unit test nhanh, còn integration test xác minh riêng hợp đồng framework. Thiết kế như vậy giảm lỗi startup khó chẩn đoán, tăng khả năng bảo trì và kiểm thử.

Nguồn tham khảo chính thức (Spring Boot 3.3 / Spring Framework 6.1):

- Spring Framework — Container Extension Points: https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html
- Spring Boot — SpringApplication, Application Events and Listeners, ApplicationRunner: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — EnvironmentPostProcessor API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/env/EnvironmentPostProcessor.html
- Spring Boot — Customize the Environment or ApplicationContext Before It Starts: https://docs.spring.io/spring-boot/how-to/application.html
- Spring Framework — ApplicationContextInitializer API: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/context/ApplicationContextInitializer.html
- Spring Boot 3.3 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html