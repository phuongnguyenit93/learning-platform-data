# ApplicationContextInitializer và tùy chỉnh trước refresh

Trong quá trình khởi động Spring, ApplicationContext được tạo trước khi container bắt đầu refresh và khởi tạo các bean. Ở khoảng thời gian này, ứng dụng có thể cần bổ sung property source, điều chỉnh Environment hoặc chuẩn bị context trước khi các lớp cấu hình được nạp.

`ApplicationContextInitializer` là extension point dành cho công việc đó. Spring Boot gọi initializer sau khi đã tạo context và gắn Environment, nhưng trước khi nạp các nguồn cấu hình chính vào context và trước khi gọi `refresh()`. Vì vậy, initializer phù hợp với những thay đổi cần có hiệu lực trước khi Spring phân tích bean definition và tạo bean.

## 1. ApplicationContextInitializer là gì?

Interface `ApplicationContextInitializer` thuộc package `org.springframework.context`:

~~~java
public interface ApplicationContextInitializer<C extends ConfigurableApplicationContext> {

    void initialize(C applicationContext);
}
~~~

Initializer nhận một `ConfigurableApplicationContext`. Từ context này, nó có thể truy cập Environment, điều chỉnh một số thiết lập của context hoặc đăng ký các bước xử lý sẽ chạy trong quá trình refresh.

Các trường hợp sử dụng thường gặp:

- Thêm một property source trước khi Spring đánh giá điều kiện cấu hình.
- Thiết lập một số thuộc tính hoặc metadata của ApplicationContext.
- Đăng ký một BeanFactoryPostProcessor để xử lý bean definition trong giai đoạn refresh.
- Chuẩn bị context theo một yêu cầu bootstrap của ứng dụng hoặc thư viện.

Initializer không phải nơi khởi tạo service nghiệp vụ bằng cách gọi constructor thủ công. Việc tạo bean, tiêm dependency và quản lý lifecycle vẫn thuộc container Spring.

## 2. Initializer nằm ở đâu trong quá trình khởi động?

Khi gọi `SpringApplication.run()`, Spring Boot thực hiện một chuỗi bước. Luồng liên quan có thể mô tả như sau:

~~~text
SpringApplication.run()
        |
        v
Chuẩn bị Environment
        |
        +--> Đọc tham số, biến môi trường và nguồn cấu hình
        +--> Xử lý Config Data, application.yml và profile
        |
        v
Tạo ApplicationContext
        |
        v
Gắn Environment vào context
        |
        v
postProcessApplicationContext()
        |
        v
Gọi ApplicationContextInitializer.initialize()
        |
        v
Phát ApplicationContextInitializedEvent
        |
        v
Nạp các nguồn cấu hình chính (load)
        |
        v
ApplicationContext.refresh()
        |
        +--> Xử lý BeanFactoryPostProcessor
        +--> Đăng ký BeanPostProcessor
        +--> Tạo các singleton eager
        |
        v
ContextRefreshedEvent
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
ApplicationReadyEvent
~~~

Điểm quan trọng là initializer chạy trước `refresh()`. Các bean definition từ nguồn cấu hình chính chưa được nạp ở bước `initialize()`, nên không nên gọi `getBean()` để sử dụng service ứng dụng tại đây.

Mặt khác, Environment của Spring Boot đã được chuẩn bị trước khi context được tạo. Các nguồn cấu hình như command-line arguments, environment variables và Config Data thường đã có mặt. Thay đổi Environment trong initializer có thể ảnh hưởng đến việc xử lý bean definition sau đó, nhưng không quay ngược thời gian để làm Config Data được nạp lại.

## 3. Viết một ApplicationContextInitializer

Ví dụ, ứng dụng có một tính năng tùy chọn. Nếu chưa khai báo giá trị, initializer bổ sung giá trị mặc định vào Environment trước khi Spring xử lý các điều kiện:

~~~java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

public class FeatureDefaultsInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext applicationContext) {

        ConfigurableEnvironment environment =
                applicationContext.getEnvironment();

        Map<String, Object> defaults = Map.of(
                "app.feature.enabled", "true",
                "app.feature.region", "local"
        );

        environment.getPropertySources().addLast(
                new MapPropertySource(
                        "featureDefaults",
                        defaults
                )
        );
    }
}
~~~

Initializer lấy Environment từ context và thêm một `MapPropertySource` có tên `featureDefaults`. Trong ví dụ, property source được thêm bằng `addLast()`, tức có độ ưu tiên thấp. Các giá trị do người dùng cung cấp ở nguồn có độ ưu tiên cao hơn vẫn được giữ.

Sau đó, cấu hình có thể đọc các thuộc tính này:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.feature",
        name = "enabled",
        havingValue = "true"
)
public class FeatureConfiguration {

    @Bean
    FeatureService featureService() {
        return new FeatureService();
    }
}
~~~

Nếu người vận hành đặt `app.feature.enabled=false` trong một nguồn cấu hình có độ ưu tiên cao hơn, điều kiện không khớp và bean `FeatureService` không được đăng ký. Giá trị mặc định trong initializer chỉ được dùng khi không có nguồn ưu tiên cao hơn cung cấp giá trị.

### addFirst và addLast khác nhau như thế nào?

`MutablePropertySources` cho phép thêm property source ở đầu hoặc cuối danh sách:

- `addFirst(source)`: đưa nguồn lên đầu, có độ ưu tiên cao hơn các nguồn phía sau. Có thể ghi đè giá trị từ application config, biến môi trường hoặc command-line property source nếu chúng nằm phía sau.
- `addLast(source)`: đưa nguồn xuống cuối, thường phù hợp để cung cấp giá trị mặc định có thể bị ghi đè.

Vì vậy, hãy chọn vị trí theo ý nghĩa của nguồn dữ liệu. Nếu initializer cung cấp default, `addLast()` thường dễ dự đoán hơn. Chỉ dùng `addFirst()` khi thật sự muốn nguồn đó có quyền ưu tiên cao.

Tên property source cần ổn định và duy nhất trong Environment. Nếu nhiều initializer có thể thêm cùng nguồn, nên kiểm tra `propertySources.contains(name)` trước khi thêm để tránh thay thế ngoài ý muốn.

## 4. Đăng ký initializer bằng SpringApplication

Cách trực tiếp là tạo `SpringApplication`, thêm initializer rồi chạy ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;

public class ApplicationLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addInitializers(
                new FeatureDefaultsInitializer()
        );

        application.run(args);
    }
}
~~~

Initializer được thêm vào đối tượng `SpringApplication` và được áp dụng khi đối tượng đó tạo ApplicationContext.

Nếu dùng `SpringApplicationBuilder`, có thể đăng ký initializer trong builder:

~~~java
new SpringApplicationBuilder(Application.class)
        .initializers(new FeatureDefaultsInitializer())
        .run(args);
~~~

Cách đăng ký tường minh phù hợp khi ứng dụng sở hữu điểm khởi chạy và muốn nhìn thấy rõ initializer nào được dùng.

### Đăng ký initializer qua Spring factories

Một thư viện có thể tự công bố initializer bằng file `META-INF/spring.factories`:

~~~properties
org.springframework.context.ApplicationContextInitializer=\
com.example.bootstrap.FeatureDefaultsInitializer
~~~

Spring Boot sử dụng cơ chế `SpringFactoriesLoader` để phát hiện các implementation được công bố theo key tương ứng. Khi đóng gói thư viện, cần bảo đảm file resource được đưa vào JAR đúng đường dẫn và tên lớp đầy đủ chính xác.

Không nhầm cơ chế này với danh sách auto-configuration trong Spring Boot 3. Auto-configuration candidates được công bố bằng `AutoConfiguration.imports`; `ApplicationContextInitializer` vẫn là một extension point được đăng ký qua Spring factories hoặc qua `SpringApplication` API.

Nếu có nhiều initializer, cần xác định thứ tự thực thi có chủ đích. Các initializer được phát hiện qua Spring factories có thể sử dụng `Ordered` hoặc `@Order` theo cơ chế sắp xếp của Spring. Với initializer được thêm trực tiếp vào `SpringApplication`, hãy kiểm tra thứ tự danh sách đăng ký thực tế thay vì dựa vào giả định không được kiểm chứng.

## 5. Tùy chỉnh Environment trước khi refresh

Một trong những công việc phù hợp nhất với initializer là thay đổi Environment trước khi Spring xử lý cấu hình ứng dụng.

Ngoài việc thêm property source, initializer có thể:

- Đọc thuộc tính hiện có để xác định cách chuẩn bị context.
- Đặt một số thuộc tính context như id nếu có yêu cầu rõ ràng.
- Thiết lập active profiles trong những trường hợp phù hợp với thời điểm bootstrap.
- Đăng ký một BeanFactoryPostProcessor để thực hiện xử lý bean definition trong giai đoạn refresh.

Cần phân biệt thời điểm thay đổi Environment với thời điểm Spring Boot nạp Config Data. Boot chuẩn bị Environment trước khi tạo ApplicationContext và gọi initializer. Do đó, nếu mục tiêu là quyết định file `application-{profile}.yml` nào được nạp, hãy cấu hình profile từ đầu bằng `spring.profiles.active`, biến môi trường hoặc command-line argument.

Ví dụ, đặt active profile trong initializer không làm cho quá trình Config Data đã chạy trước đó tự động nạp lại file cấu hình theo profile mới. Nếu cần can thiệp vào Environment trước hoặc trong quá trình nạp Config Data, hãy xem xét `EnvironmentPostProcessor` và thứ tự chạy của nó.

### Đăng ký BeanFactoryPostProcessor từ initializer

Nếu cần xử lý bean definition trong giai đoạn refresh, initializer có thể đăng ký một `BeanFactoryPostProcessor` với context:

~~~java
import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class BeanFactoryPreparationInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext applicationContext) {

        applicationContext.addBeanFactoryPostProcessor(
                beanFactory -> {
                    // Xử lý BeanDefinition ở giai đoạn refresh.
                }
        );
    }
}
~~~

Initializer chỉ đăng ký callback. Spring gọi BeanFactoryPostProcessor trong quá trình refresh, sau khi các bean definition được nạp và trước khi khởi tạo các singleton thông thường.

Nếu chỉ cần đăng ký bean nghiệp vụ, nên dùng `@Configuration`, `@Bean`, component scanning hoặc cơ chế import. Không nên đưa logic đăng ký bean thông thường vào initializer nếu không có lý do bootstrap cụ thể.

## 6. ApplicationContextInitializer khác EnvironmentPostProcessor như thế nào?

Hai extension point đều có thể liên quan tới Environment nhưng chạy ở thời điểm khác nhau:

| Cơ chế | Thời điểm | Phạm vi phù hợp |
|---|---|---|
| `EnvironmentPostProcessor` | Khi Spring Boot đang chuẩn bị Environment, trước khi tạo ApplicationContext | Thêm hoặc điều chỉnh property source sớm, can thiệp vào bước chuẩn bị Environment/Config Data |
| `ApplicationContextInitializer` | Sau khi context được tạo và gắn Environment, trước khi nạp nguồn cấu hình chính và refresh | Tùy chỉnh context hoặc Environment ở giai đoạn trước refresh |
| `BeanFactoryPostProcessor` | Trong quá trình refresh, sau khi bean definition được nạp và trước khi tạo bean thông thường | Thay đổi hoặc kiểm tra bean definition |
| `BeanPostProcessor` | Trong quá trình khởi tạo từng bean | Can thiệp instance trước/sau initialization |
| `@PostConstruct` | Trong quá trình khởi tạo bean hiện tại | Chuẩn bị trạng thái của chính bean |
| `ApplicationRunner` | Sau khi context refresh, trong quá trình startup của Spring Boot | Chạy công việc ứng dụng sau khi bean đã được tạo |

### Chọn EnvironmentPostProcessor khi cần tác động sớm

Ví dụ, một thư viện cần thêm property source trước khi Spring Boot xử lý Config Data hoặc xác định profile. Khi đó, `EnvironmentPostProcessor` phù hợp hơn initializer vì nó tham gia giai đoạn chuẩn bị Environment trước khi ApplicationContext được tạo.

`EnvironmentPostProcessor` thường được công bố qua `META-INF/spring.factories` với key:

~~~properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.bootstrap.CustomEnvironmentPostProcessor
~~~

Thứ tự của processor có thể ảnh hưởng tới việc property source nào được xử lý trước. Nếu cần tương tác với Config Data, phải xác định thứ tự so với các processor liên quan; không nên giả định processor luôn chạy trước hoặc sau Config Data mà không cấu hình và kiểm chứng.

### Chọn ApplicationContextInitializer khi cần context đã tồn tại

Nếu cần truy cập `ConfigurableApplicationContext`, thay đổi id, thêm property source cho giai đoạn xử lý bean definition hoặc đăng ký một post-processor với context, initializer là điểm phù hợp.

Câu hỏi quyết định là: thay đổi cần có hiệu lực trước khi Environment được chuẩn bị hay chỉ cần trước khi context refresh? Trả lời câu hỏi này sẽ giúp chọn đúng extension point.

## 7. Điều gì nên và không nên làm trong initializer?

Initializer chạy trong giai đoạn bootstrap, khi context đã tồn tại nhưng chưa refresh. Hãy giữ công việc ở phạm vi phù hợp.

Nên làm:

- Bổ sung property source có nguồn gốc và độ ưu tiên rõ ràng.
- Thiết lập metadata của context trước khi refresh.
- Đăng ký một BeanFactoryPostProcessor khi thật sự cần xử lý bean definition.
- Kiểm tra các giá trị bootstrap cần thiết và dừng startup sớm nếu cấu hình không hợp lệ.

Không nên:

- Gọi `getBean()` để sử dụng service nghiệp vụ trước khi context refresh.
- Tự gọi constructor và quản lý vòng đời service bên ngoài container.
- Tự gọi `refresh()` trên context do Spring Boot quản lý.
- Thực hiện truy cập mạng hoặc công việc dài làm chậm startup mà không có chính sách timeout rõ ràng.
- Đặt active profile ở thời điểm quá muộn rồi kỳ vọng Boot nạp lại Config Data.
- Thêm property source ở đầu Environment mà không xem xét việc nó có thể ghi đè cấu hình do người vận hành cung cấp.

Nếu initializer ném exception, quá trình khởi động sẽ thất bại. Điều này phù hợp khi một điều kiện bootstrap bắt buộc không được đáp ứng, nhưng exception cần mô tả rõ nguồn cấu hình và nguyên nhân.

## 8. Kiểm thử ApplicationContextInitializer

Có thể kiểm thử initializer độc lập với toàn bộ ứng dụng. Spring Boot Test cung cấp `ApplicationContextRunner`, cho phép gắn initializer và xác nhận giá trị Environment được áp dụng trước khi điều kiện bean được đánh giá.

Ví dụ, dùng initializer ở phần trước để cung cấp giá trị mặc định:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FeatureDefaultsInitializerTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withInitializer(new FeatureDefaultsInitializer())
                    .withUserConfiguration(FeatureConfiguration.class);

    @Test
    void usesInitializerDefaultWhenPropertyIsMissing() {
        contextRunner.run(context -> {
            assertThat(context.getEnvironment().getProperty(
                    "app.feature.enabled"
            )).isEqualTo("true");

            assertThat(context).hasSingleBean(FeatureService.class);
        });
    }

    @Test
    void externalPropertyOverridesInitializerDefault() {
        contextRunner
                .withPropertyValues("app.feature.enabled=false")
                .run(context -> {
                    assertThat(context.getEnvironment().getProperty(
                            "app.feature.enabled"
                    )).isEqualTo("false");

                    assertThat(context)
                            .doesNotHaveBean(FeatureService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class FeatureConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "app.feature",
                name = "enabled",
                havingValue = "true"
        )
        FeatureService featureService() {
            return new FeatureService();
        }
    }
}
~~~

Bộ kiểm thử này xác nhận hai điều:

1. Property source được initializer thêm vào trước khi Spring xử lý cấu hình và điều kiện.
2. Property do test cung cấp có độ ưu tiên cao hơn giá trị mặc định từ initializer.

Khi kiểm thử initializer thực tế của ứng dụng, cũng nên xác nhận property source không bị thêm trùng, thứ tự các initializer rõ ràng và lỗi bootstrap có thông báo dễ hiểu.

## 9. Những lỗi thường gặp

### Dùng initializer để thay đổi profile rồi mong file cấu hình profile được nạp

Spring Boot đã chuẩn bị Environment và xử lý Config Data trước khi gọi initializer. Đổi active profile ở initializer không làm quy trình nạp Config Data chạy lại. Hãy cung cấp profile trước khi khởi chạy hoặc dùng EnvironmentPostProcessor ở đúng thời điểm.

### Gọi bean nghiệp vụ khi context chưa refresh

Các nguồn cấu hình chính có thể chưa được nạp và các singleton thông thường chưa được khởi tạo. Gọi `getBean()` tại đây có thể tạo bean quá sớm hoặc khiến quá trình bootstrap thất bại. Hãy giới hạn initializer ở công việc chuẩn bị context.

### Thêm property source với độ ưu tiên không phù hợp

Dùng `addFirst()` có thể ghi đè cấu hình do người vận hành truyền vào. Nếu chỉ muốn cung cấp giá trị mặc định, dùng vị trí ưu tiên thấp như `addLast()` và kiểm thử trường hợp có property được truyền từ bên ngoài.

### Nhầm initializer với BeanFactoryPostProcessor

Initializer được gọi trước khi Spring nạp các nguồn cấu hình chính vào context. BeanFactoryPostProcessor được thực thi trong refresh, sau khi bean definition được nạp. Nếu cần duyệt hoặc thay đổi bean definition, hãy đăng ký post-processor và để Spring gọi đúng giai đoạn.

### Nghĩ initializer tự chạy lại khi context thay đổi

Initializer được gọi trong quá trình chuẩn bị context. Nó không phải listener theo dõi Environment hoặc bean trong suốt thời gian ứng dụng chạy. Nếu context mới được tạo, initializer được đăng ký cho lần khởi tạo đó có thể được gọi lại; còn thay đổi property trong context đang chạy không tự kích hoạt initializer.

## 10. Quy trình chọn và sử dụng initializer

Khi cần tùy chỉnh trước refresh, có thể thực hiện theo trình tự:

1. Xác định thay đổi có cần thực hiện trước khi Environment được chuẩn bị hay chỉ cần trước khi context refresh.
2. Chọn `EnvironmentPostProcessor` nếu cần can thiệp vào giai đoạn chuẩn bị Environment hoặc Config Data; chọn `ApplicationContextInitializer` nếu cần một context đã tồn tại.
3. Viết initializer với kiểu context phù hợp, ưu tiên thay đổi nhỏ và có thể kiểm soát.
4. Chọn cách đăng ký: `SpringApplication.addInitializers`, `SpringApplicationBuilder.initializers` hoặc Spring factories.
5. Xác định rõ thứ tự khi có nhiều initializer.
6. Kiểm tra thứ tự ưu tiên của property source và bảo đảm giá trị người vận hành cung cấp được xử lý đúng.
7. Kiểm thử kết quả trước khi bean definition và điều kiện được áp dụng.
8. Giữ công việc khởi tạo bean và logic nghiệp vụ trong cơ chế quản lý bean của Spring.

`ApplicationContextInitializer` cung cấp một điểm can thiệp rõ ràng sau khi ApplicationContext được tạo nhưng trước khi refresh. Khi sử dụng đúng thời điểm, initializer giúp chuẩn bị Environment và context để quá trình phân tích cấu hình diễn ra theo mong muốn, đồng thời giữ việc tạo bean và quản lý lifecycle trong phạm vi trách nhiệm của Spring.

