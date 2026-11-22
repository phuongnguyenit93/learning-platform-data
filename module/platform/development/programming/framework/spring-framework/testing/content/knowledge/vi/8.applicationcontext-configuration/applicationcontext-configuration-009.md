# ContextCustomizer và tác động tới cấu hình kiểm thử

Trong Spring TestContext Framework, **ContextCustomizer** là một extension point cho phép điều chỉnh ApplicationContext trong lúc Spring đang tạo context cho test. Nó được gọi sau khi context được khởi tạo nhưng trước khi context được refresh. Nhờ vị trí này, test có thể bổ sung property source, đăng ký bean hoặc thay đổi một phần cấu hình trước khi Spring tạo các singleton và hoàn tất quá trình khởi động.

ContextCustomizer thường được dùng khi cấu hình cần phụ thuộc vào chính test class hoặc metadata của test. Ví dụ, một test class khai báo annotation riêng để chọn vùng dịch vụ, một nhóm test cần cung cấp bean thay thế, hoặc một test cần đăng ký property được cấp động từ tài nguyên test.

Hai thành phần chính là:

- **ContextCustomizer**: thực hiện thay đổi trên ConfigurableApplicationContext.
- **ContextCustomizerFactory**: phát hiện test class và tạo ContextCustomizer tương ứng.

Điểm quan trọng là ContextCustomizer tham gia vào quá trình tạo và cache ApplicationContext. Cấu hình mà nó thêm vào có thể ảnh hưởng đến bean, property và hành vi của toàn bộ test class dùng context đó. Vì vậy, customizer cần có đầu vào rõ ràng, hành vi xác định và quy tắc equals/hashCode phù hợp để Spring Test nhận diện đúng các context có thể dùng chung.

## 1. ContextCustomizer nằm ở đâu trong quá trình tạo test context?

Một test Spring không nhất thiết tạo ApplicationContext mới mỗi khi chạy một test method. TestContext Framework xây dựng cấu hình đã hợp nhất, dùng cấu hình đó để tìm context trong cache, và chỉ tạo context mới khi chưa có context phù hợp.

Trong quá trình bootstrap:

1. Spring đọc metadata của test class như @ContextConfiguration, @ActiveProfiles và @TestPropertySource.
2. TestContext Framework hợp nhất thông tin cấu hình thành MergedContextConfiguration.
3. Các ContextCustomizerFactory được phát hiện và được yêu cầu tạo customizer phù hợp với test class.
4. Danh sách customizer được đưa vào cấu hình đã hợp nhất.
5. Spring kiểm tra cache ApplicationContext bằng cấu hình đó.
6. Nếu cần tạo context mới, ContextLoader tạo context và gọi các customizer trước khi refresh.
7. Sau khi refresh thành công, context được đưa vào cache để các test tương thích có thể dùng lại.

Có thể hình dung luồng này như sau:

~~~mermaid
flowchart TD
    A["Test class và annotation"] --> B["MergedContextConfiguration"]
    B --> C["ContextCustomizerFactory"]
    C --> D["ContextCustomizer"]
    D --> E["Tạo cache key"]
    E --> F{"Context phù hợp đã có trong cache?"}
    F -->|"Có"| G["Dùng lại ApplicationContext"]
    F -->|"Không"| H["ContextLoader tạo context"]
    H --> I["ContextCustomizer tùy chỉnh context"]
    I --> J["Refresh ApplicationContext"]
    J --> K["Đưa context vào cache"]
    G --> L["Chạy test"]
    K --> L
~~~

ContextCustomizer có thể tác động đến environment, bean factory hoặc cấu hình của context trước khi refresh. Ví dụ, property source được thêm trước refresh có thể được đọc khi Spring tạo bean và giải quyết placeholder.

**Customizer không phải callback chạy trước từng test method.** Nếu ApplicationContext được cache và tái sử dụng, customizer không được áp dụng lại cho mỗi method. Nó thuộc giai đoạn chuẩn bị context.

## 2. Hai interface cốt lõi

### ContextCustomizer

Interface nằm trong package:

~~~java
import org.springframework.test.context.ContextCustomizer;
~~~

Hợp đồng chính có một method:

~~~java
void customizeContext(
        ConfigurableApplicationContext context,
        MergedContextConfiguration mergedConfig
);
~~~

Trong đó:

- context là ApplicationContext có thể cấu hình đang được chuẩn bị.
- mergedConfig chứa cấu hình đã hợp nhất của test class, chẳng hạn locations, classes, initializers, active profiles, property sources, context customizers và context loader.

Một customizer có thể sử dụng context.getEnvironment() để thêm property source, hoặc dùng bean factory để đăng ký bean definition. Vì method chạy trước refresh, các thay đổi có thể tham gia vào quá trình tạo bean.

~~~java
public final class RegionContextCustomizer
        implements ContextCustomizer {

    private final String region;

    public RegionContextCustomizer(String region) {
        this.region = region;
    }

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        Map<String, Object> properties =
                Map.of("service.region", region);

        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "testRegion",
                                properties
                        )
                );
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof RegionContextCustomizer that)) {
            return false;
        }
        return region.equals(that.region);
    }

    @Override
    public int hashCode() {
        return region.hashCode();
    }
}
~~~

Ví dụ trên bổ sung property service.region vào đầu danh sách nguồn cấu hình. Nếu một nguồn thấp hơn cũng có key này, giá trị do test cung cấp sẽ được ưu tiên.

Việc triển khai equals/hashCode theo region có ý nghĩa đặc biệt đối với cache. Hai customizer cùng cấu hình vùng có thể được xem là tương đương; customizer có vùng khác nhau sẽ không bị xem là cùng cấu hình.

Trong Java 17 trở lên, có thể dùng record để có equals/hashCode dựa trên thành phần dữ liệu một cách tự động:

~~~java
record RegionContextCustomizer(String region)
        implements ContextCustomizer {

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "testRegion",
                                Map.of("service.region", region)
                        )
                );
    }
}
~~~

Record phù hợp khi customizer là một cấu hình bất biến, được xác định hoàn toàn bởi các giá trị constructor.

### ContextCustomizerFactory

Factory có nhiệm vụ quyết định test class nào cần customizer và tạo customizer tương ứng.

Interface nằm trong package:

~~~java
import org.springframework.test.context.ContextCustomizerFactory;
~~~

Method chính:

~~~java
ContextCustomizer createContextCustomizer(
        Class<?> testClass,
        List<ContextConfigurationAttributes> configAttributes
);
~~~

- testClass là class đang được chuẩn bị cho TestContext.
- configAttributes là danh sách thuộc tính cấu hình context được phát hiện từ test class và cấu trúc test liên quan.
- Factory trả về ContextCustomizer nếu cần tùy chỉnh; có thể trả về null nếu test class không cần customizer đó.

Factory thường được dùng để đọc annotation tùy chỉnh, kiểm tra metadata hoặc xác định các giá trị cần đưa vào context.

## 3. Ví dụ hoàn chỉnh: annotation chọn vùng dịch vụ

Giả sử ứng dụng có một property service.region. Mỗi test class có thể chọn vùng riêng mà không phải sửa file application.yml hoặc thay đổi environment của máy.

### Bước 1: khai báo annotation cho test

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface TestRegion {
    String value();
}
~~~

Annotation được đặt trên test class:

~~~java
@TestRegion("test-southeast")
@SpringJUnitConfig(RegionTestConfiguration.class)
class SoutheastRegionTest {
    // Tests
}
~~~

### Bước 2: tạo ContextCustomizer

~~~java
import java.util.Map;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.MergedContextConfiguration;

public record TestRegionContextCustomizer(String region)
        implements ContextCustomizer {

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig
    ) {
        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "testRegion",
                                Map.of("service.region", region)
                        )
                );
    }
}
~~~

Customizer chỉ làm một việc: đưa giá trị vùng được chọn vào Environment trước khi context refresh.

### Bước 3: tạo ContextCustomizerFactory

~~~java
import java.util.List;

import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.test.context.ContextConfigurationAttributes;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.ContextCustomizerFactory;

public class TestRegionContextCustomizerFactory
        implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(
            Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes
    ) {
        TestRegion annotation =
                AnnotatedElementUtils.findMergedAnnotation(
                        testClass,
                        TestRegion.class
                );

        if (annotation == null) {
            return null;
        }

        return new TestRegionContextCustomizer(annotation.value());
    }
}
~~~

AnnotatedElementUtils.findMergedAnnotation giúp tìm annotation theo cơ chế merged annotation của Spring, bao gồm các trường hợp annotation được tổng hợp hoặc kế thừa theo quy tắc hỗ trợ.

Nếu test class không khai báo @TestRegion, factory không cần thêm cấu hình. Nếu có, factory tạo customizer với giá trị từ annotation.

### Bước 4: đăng ký factory

Spring Test phát hiện ContextCustomizerFactory thông qua SpringFactoriesLoader. Đăng ký factory trong file:

~~~text
src/test/resources/META-INF/spring.factories
~~~

Nội dung:

~~~properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.test.TestRegionContextCustomizerFactory
~~~

Thay com.example.test bằng package thực tế chứa factory.

File này phải nằm trên test runtime classpath. Nếu factory nằm trong thư viện test dùng chung, đăng ký trong resources của thư viện để các module tiêu thụ có thể phát hiện factory.

### Bước 5: sử dụng property trong cấu hình ứng dụng

~~~java
@Configuration
class RegionTestConfiguration {

    @Bean
    RegionService regionService(Environment environment) {
        return new RegionService(
                environment.getRequiredProperty("service.region")
        );
    }
}
~~~

Test service:

~~~java
@TestRegion("test-southeast")
@SpringJUnitConfig(RegionTestConfiguration.class)
class SoutheastRegionTest {

    @Autowired
    private RegionService regionService;

    @Test
    void usesRegionFromTestAnnotation() {
        assertEquals(
                "test-southeast",
                regionService.region()
        );
    }
}
~~~

Khi Spring tạo context cho test class:

1. Factory đọc @TestRegion.
2. Factory tạo TestRegionContextCustomizer.
3. Spring tạo context.
4. Customizer thêm service.region vào Environment.
5. Context refresh và tạo RegionService.
6. RegionService đọc property đã được cung cấp.

Ví dụ này cho thấy ContextCustomizer có thể biến metadata trên test class thành cấu hình của ApplicationContext.

## 4. Tại sao equals và hashCode của ContextCustomizer quan trọng?

Spring TestContext Framework cache ApplicationContext để tránh khởi tạo lại các context có cấu hình tương đương. Cache key dựa trên MergedContextConfiguration. Cấu hình hợp nhất có chứa tập ContextCustomizer, và tập này tham gia vào equals/hashCode của cấu hình.

Vì vậy, customizer không chỉ là một callback được gọi khi tạo context. Nó còn là một phần của danh tính cấu hình context.

Có hai lỗi thiết kế thường gặp.

### Không triển khai equality cho customizer có trạng thái

Giả sử factory luôn tạo object mới:

~~~java
return new RegionContextCustomizer(annotation.value());
~~~

Nếu customizer chỉ dùng equals/hashCode mặc định của Object, hai instance có cùng region vẫn khác nhau vì identity khác nhau. Spring có thể xem các cấu hình tương đương là khác nhau và tạo nhiều cache entry.

Hậu quả:

- ApplicationContext bị khởi tạo lặp lại.
- Test suite chạy chậm hơn.
- Cache sử dụng nhiều entry hơn.
- Các test tưởng như có cấu hình giống nhau không tận dụng được context chung.

Dùng record hoặc triển khai equals/hashCode dựa trên toàn bộ cấu hình ảnh hưởng đến context sẽ giúp Spring nhận diện tính tương đương.

### Equality bỏ qua dữ liệu làm thay đổi context

Trường hợp nguy hiểm hơn là customizer có cấu hình khác nhau nhưng equals/hashCode lại coi chúng giống nhau.

Ví dụ, hai test class yêu cầu region khác nhau nhưng customizer chỉ so sánh tên class. Khi cache key bị xem là giống nhau, test sau có thể nhận context đã được tạo với region của test trước.

Đây là lỗi cấu hình test có thể rất khó chẩn đoán vì từng test chạy riêng đều có thể xanh, nhưng chạy cùng suite lại nhận dữ liệu cấu hình không đúng.

Quy tắc thiết kế:

- Customizer bất biến sau khi được tạo.
- Equality phải bao gồm mọi giá trị có ảnh hưởng đến context.
- Không đưa dữ liệu theo từng test method vào customizer.
- Không dùng thời điểm hiện tại hoặc random value trong customizer nếu giá trị đó không phải một phần có chủ đích của cấu hình.
- Factory cần tạo customizer có cùng equality khi cấu hình thực sự tương đương.

## 5. Tác động tới cache ApplicationContext

MergedContextConfiguration chứa nhiều yếu tố dùng để xác định một context có thể tái sử dụng hay không, chẳng hạn:

- Resource locations và configuration classes.
- Context initializer classes.
- Context loader.
- Active profiles.
- Property source locations và inline properties.
- Parent context nếu có hierarchy.
- Context customizers.

Khi ContextCustomizer thay đổi cấu hình, nó có thể làm cache key thay đổi. Điều này là cần thiết nếu hai test cần context khác nhau.

Ví dụ:

| Test class | Customizer | Context có thể chia sẻ? |
|---|---|---|
| SoutheastRegionTest | region = test-southeast | Có thể chia sẻ với test có cùng cấu hình |
| SoutheastRegionAnotherTest | region = test-southeast | Có thể dùng chung nếu các phần cấu hình còn lại cũng tương đương |
| EuropeRegionTest | region = test-europe | Cần context khác vì cấu hình khác |
| Test không có TestRegion | Không có customizer này | Không cùng cấu hình customizer với nhóm trên |

"Giống nhau" ở đây phải xét toàn bộ MergedContextConfiguration, không chỉ riêng customizer. Cùng region nhưng khác bean configuration, profile hoặc property source vẫn có thể tạo context khác.

### Customizer không chạy lại khi context được cache

Nếu hai test class có cấu hình tương đương và cache trả về context đã có, Spring không cần tạo context mới và không chạy lại quá trình customizeContext cho lần dùng lại đó.

Điều này có nghĩa customizer không phải nơi phù hợp để:

- Reset dữ liệu trước từng test method.
- Sinh dữ liệu ngẫu nhiên mới cho từng test.
- Đặt trạng thái thay đổi theo thứ tự test.
- Mở tài nguyên mà mỗi test method cần một instance riêng.
- Thực hiện side effect cần chạy lại ở mỗi lần test.

Những nhiệm vụ theo từng method nên dùng @BeforeEach, @AfterEach, TestExecutionListener phù hợp hoặc fixture riêng. Những tài nguyên theo context có thể dùng lifecycle bean hoặc cơ chế quản lý tài nguyên gắn với context.

## 6. ContextCustomizer thay đổi Environment và property precedence

Một use case phổ biến là thêm property source trước khi context refresh. Ví dụ:

~~~java
context.getEnvironment()
        .getPropertySources()
        .addFirst(
                new MapPropertySource(
                        "customTestProperties",
                        Map.of(
                                "feature.search.enabled", "true",
                                "service.timeout", "1500"
                        )
                )
        );
~~~

addFirst đưa nguồn mới lên đầu danh sách, nên giá trị ở đó được ưu tiên khi nhiều nguồn cùng chứa key.

Đây là một điểm cần cẩn trọng. Nếu customizer thêm nguồn ở vị trí ưu tiên cao, nó có thể ghi đè giá trị được khai báo trong:

- @TestPropertySource.
- application-test.properties hoặc application-test.yml.
- System properties.
- Environment variables.
- Các nguồn cấu hình khác đang có trong Environment.

Thứ tự thực tế phụ thuộc các nguồn mà Spring Boot hoặc Spring Test đã đăng ký và vị trí customizer thêm nguồn. Không nên mặc định rằng giá trị trong file luôn thắng property do customizer cung cấp.

Nếu chỉ cần thêm giá trị mặc định cho test, có thể dùng addLast hoặc kiểm tra xem key đã tồn tại trước khi bổ sung. Nếu chủ đích là override, hãy đặt tên nguồn rõ ràng và viết test xác nhận giá trị cuối cùng.

### Ví dụ kiểm tra property được customizer cung cấp

Một test context có thể inject Environment và kiểm tra giá trị:

~~~java
@TestRegion("test-southeast")
@SpringJUnitConfig(RegionTestConfiguration.class)
class RegionEnvironmentTest {

    @Autowired
    private Environment environment;

    @Test
    void exposesRegionProperty() {
        assertEquals(
                "test-southeast",
                environment.getProperty("service.region")
        );
    }
}
~~~

Test này xác nhận property source đã tham gia context. Nếu mục tiêu là xác nhận bean được tạo theo property, hãy kiểm tra bean tương ứng thay vì chỉ kiểm tra chuỗi trong Environment.

## 7. ContextCustomizer có thể đăng ký bean hoặc thay đổi BeanFactory

Ngoài Environment, customizer còn nhận ConfigurableApplicationContext. Nó có thể thay đổi bean factory trước refresh.

Ví dụ, đăng ký một singleton test-only:

~~~java
@Override
public void customizeContext(
        ConfigurableApplicationContext context,
        MergedContextConfiguration mergedConfig
) {
    context.getBeanFactory().registerSingleton(
            "testClock",
            Clock.fixed(
                    Instant.parse("2026-11-12T00:00:00Z"),
                    ZoneOffset.UTC
            )
    );
}
~~~

Các bean được tạo sau đó có thể sử dụng Clock đã đăng ký theo kiểu phù hợp với cơ chế autowire và tên bean trong context.

Với cấu hình cần quản lý vòng đời đầy đủ hoặc cần bean definition có scope/metadata, có thể đăng ký BeanDefinition thay vì singleton instance. Ví dụ:

~~~java
RootBeanDefinition definition =
        new RootBeanDefinition(TestClockProvider.class);

context.getBeanFactory().registerBeanDefinition(
        "testClockProvider",
        definition
);
~~~

Việc đăng ký bean definition cần tuân theo các quy tắc về tên bean, dependency và thứ tự xử lý của BeanFactory. Nếu có nhiều customizer cùng đăng ký một tên, cần xác định chính sách xung đột thay vì phụ thuộc thứ tự ngẫu nhiên.

Customizer nên thực hiện thay đổi cấu hình có thể dự đoán. Tránh gọi context.refresh() thủ công, tự khởi tạo toàn bộ bean hoặc truy cập bean quá sớm trước khi context hoàn tất quá trình refresh.

## 8. ContextCustomizer và các cơ chế cấu hình test khác

Spring có nhiều cơ chế cung cấp cấu hình cho test. ContextCustomizer là một extension point mức thấp hơn, hữu ích khi cấu hình cần được tạo theo metadata của test class.

| Cơ chế | Cách cung cấp cấu hình | Khi nên dùng |
|---|---|---|
| @TestPropertySource | Khai báo property inline hoặc file | Property cố định, dễ đọc ngay trên test |
| @ActiveProfiles | Chọn profile cho context | Cấu hình bean theo profile |
| @ContextConfiguration(initializers = ...) | Khai báo ApplicationContextInitializer | Cần initializer cụ thể, được chỉ định rõ |
| @DynamicPropertySource | Đăng ký property động qua supplier | Giá trị như host/port của Testcontainers |
| @Import / @TestConfiguration | Bổ sung cấu hình hoặc bean | Test cần thêm bean rõ ràng |
| ContextCustomizerFactory | Tạo customizer dựa trên test metadata | Cần quy tắc tùy chỉnh có thể tái sử dụng và tự động phát hiện |

### So sánh với ApplicationContextInitializer

ApplicationContextInitializer cũng có thể tùy chỉnh ConfigurableApplicationContext trước refresh:

~~~java
public class RegionInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext context
    ) {
        context.getEnvironment()
                .getPropertySources()
                .addFirst(
                        new MapPropertySource(
                                "initializerProperties",
                                Map.of("service.region", "test-region")
                        )
                );
    }
}
~~~

Initializer thường được khai báo trực tiếp trong @ContextConfiguration:

~~~java
@ContextConfiguration(
        classes = RegionConfiguration.class,
        initializers = RegionInitializer.class
)
~~~

Sự khác biệt chính:

- Initializer được khai báo như một phần của cấu hình test, phù hợp với hành vi khởi tạo chung và cụ thể.
- ContextCustomizer được tạo thông qua factory, có thể đọc test class và các ContextConfigurationAttributes để quyết định tùy chỉnh.
- ContextCustomizer là một phần của tập customizer trong MergedContextConfiguration và tham gia vào việc xác định cache key.
- Factory có thể tự động áp dụng quy tắc cho các test class có annotation hoặc metadata nhất định mà không cần khai báo initializer trên từng class.

Nếu chỉ cần thêm một property cố định cho một test, @TestPropertySource thường dễ hiểu hơn. Nếu cần logic tự động dựa trên annotation hoặc loại test, ContextCustomizerFactory phù hợp hơn.

### So sánh với @DynamicPropertySource

@DynamicPropertySource cho phép đăng ký property thông qua DynamicPropertyRegistry:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("service.base-url", server::baseUrl);
}
~~~

Cơ chế này thường dùng với Testcontainers hoặc server test có địa chỉ được cấp lúc runtime. Spring Test có ContextCustomizerFactory nội bộ để phát hiện và áp dụng các method @DynamicPropertySource.

Khi nhu cầu chỉ là đăng ký các property động theo API đã có, hãy ưu tiên @DynamicPropertySource. Không cần tự viết một factory mới chỉ để làm lại cùng chức năng.

### So sánh với @TestConfiguration và @Import

Nếu test cần một bean thay thế hoặc một cấu hình bổ sung, có thể khai báo @TestConfiguration rồi import:

~~~java
@TestConfiguration
class TestClockConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-11-12T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

~~~java
@SpringBootTest
@Import(TestClockConfiguration.class)
class SubscriptionServiceTest {
    // Tests
}
~~~

Cách này rõ ràng và dễ tìm khi cấu hình chỉ áp dụng cho một nhóm test đã xác định. ContextCustomizer hữu ích hơn khi cần tự động hóa quy tắc theo metadata, hoặc khi muốn đóng gói hành vi tùy chỉnh thành một test infrastructure có thể tái sử dụng.

## 9. Một số trường hợp sử dụng thực tế

### Thêm cấu hình theo annotation riêng

Test class khai báo annotation mô tả một chế độ test, factory đọc annotation rồi tạo customizer để bổ sung property hoặc bean. Cách này giúp các test chỉ cần khai báo ý định thay vì lặp lại setup.

Ví dụ, @TestRegion ở phần trước có thể được mở rộng để nhận profile, tên tenant hoặc chế độ feature flag. Tuy nhiên, annotation chỉ nên chứa metadata có ý nghĩa. Không nên biến annotation thành một DSL cấu hình quá rộng khiến test khó đọc.

### Đăng ký bean giả lập dùng chung cho một nhóm test

Một factory có thể nhận biết annotation đánh dấu test cần một clock cố định, fake client hoặc một bean test-only. Customizer đăng ký bean trước refresh để các bean khác có thể inject nó.

Với mock bean trong Spring context, nên dùng cơ chế bean override được Spring hoặc Spring Boot hỗ trợ ở phiên bản dự án. Customizer tự đăng ký singleton có thể hoạt động cho trường hợp đơn giản, nhưng cần quản lý tên, type, candidate selection và lifecycle rõ ràng.

### Bổ sung property lấy từ tài nguyên test

Nếu một tài nguyên được khởi chạy trước context và cung cấp thông tin kết nối, customizer có thể đưa endpoint vào Environment. Tuy nhiên, với Testcontainers, @DynamicPropertySource thường là API dễ hiểu và được hỗ trợ tốt hơn cho mục tiêu này.

Không nên để customizer tự khởi chạy một container hoặc một server nặng nếu có thể quản lý tài nguyên bằng lifecycle riêng. Context cache có thể khiến tài nguyên sống lâu hơn một test method; vòng đời của tài nguyên phải tương thích với vòng đời context.

### Áp dụng chính sách cấu hình cho một loại test class

Factory có thể kiểm tra annotation, superclass hoặc metadata để xác định test nào cần một tùy chỉnh chung. Ví dụ, mọi test class có @UsesTestTenant sẽ nhận property tenant tương ứng.

Điểm cần giữ rõ là factory chỉ tạo customizer dựa trên metadata. Thay đổi thật trên ApplicationContext nằm trong customizeContext. Tách hai trách nhiệm giúp việc tìm nguyên nhân dễ hơn: một lỗi có thể nằm ở bước phát hiện metadata, hoặc ở bước áp dụng cấu hình.

## 10. Những lỗi thường gặp khi viết ContextCustomizer

### Customizer giữ trạng thái mutable

Nếu customizer chứa Map hoặc object có thể thay đổi sau khi được tạo, equals/hashCode có thể thay đổi trong thời gian đối tượng đang tham gia cache key. Điều này làm hành vi cache khó dự đoán.

Hãy tạo customizer bất biến, sao chép dữ liệu đầu vào nếu cần và không lưu trạng thái theo test method.

### Factory tạo customizer khác nhau dù cấu hình tương đương

Nếu customizer dùng equality theo identity, Spring có thể xem mỗi lần tạo là một cấu hình mới và giảm khả năng tái sử dụng context. Dùng record hoặc equals/hashCode theo các giá trị ảnh hưởng đến context.

### Equality không bao gồm property thực tế

Nếu hai customizer có region khác nhau nhưng equals/hashCode không xét region, cache có thể dùng lại context sai cấu hình. Tất cả giá trị làm thay đổi Environment hoặc bean definition phải tham gia equality.

### Thêm property source ở vị trí không phù hợp

addFirst có thể ghi đè property từ nguồn khác. Nếu test cần kiểm tra cấu hình mặc định của ứng dụng, customizer có thể vô tình che mất giá trị đó. Chọn vị trí nguồn có chủ đích và kiểm tra precedence.

### Đăng ký bean trùng tên

Hai customizer hoặc test configuration có thể đăng ký cùng một bean name. Kết quả phụ thuộc cách BeanFactory xử lý override và cấu hình cho phép hay không. Đặt tên có phạm vi rõ ràng, hoặc dùng cơ chế bean override chính thức khi cần thay thế bean hiện hữu.

### Thực hiện side effect khi customize context

Không nên gửi HTTP request, truy cập hệ thống production hoặc ghi dữ liệu nghiệp vụ trong customizeContext. Method này thuộc giai đoạn tạo context và có thể chỉ chạy một lần do cache. Side effect không idempotent có thể khiến test suite khó lặp lại.

### Dùng customizer để reset trạng thái từng test

Customizer không chạy trước mỗi method. Nếu cần reset mock, repository hoặc dữ liệu trước mỗi test, hãy dùng lifecycle phù hợp như @BeforeEach, @AfterEach, transaction test hoặc listener chuyên biệt.

### Tạo customizer cho một property đơn giản

Nếu một test chỉ cần một property cố định, @TestPropertySource thường ngắn gọn hơn. Tự viết factory và đăng ký spring.factories sẽ làm tăng số thành phần cần duy trì mà không mang lại lợi ích tương xứng.

## 11. Chẩn đoán khi cấu hình context không như mong đợi

Khi bean hoặc property không có giá trị dự kiến, hãy xác định lỗi thuộc giai đoạn nào:

**Factory không được phát hiện**

- Kiểm tra file META-INF/spring.factories có nằm trên test runtime classpath không.
- Kiểm tra key là org.springframework.test.context.ContextCustomizerFactory.
- Kiểm tra tên class đầy đủ, constructor mặc định và khả năng tải class.
- Kiểm tra test đang dùng TestContext Framework và bootstrapper tương ứng.

**Factory được gọi nhưng không tạo customizer**

- Kiểm tra test class có annotation cần thiết không.
- Kiểm tra annotation có runtime retention không.
- Kiểm tra cách tìm annotation, meta-annotation và class hierarchy.
- Kiểm tra factory có trả về null do điều kiện không khớp không.

**Customizer chạy nhưng property không có hiệu lực**

- Xác nhận customizer thêm property source vào đúng context.
- Kiểm tra tên key và vị trí trong property source list.
- Kiểm tra property có bị nguồn ưu tiên cao hơn ghi đè sau đó không.
- Xác nhận bean đọc property sau khi customizer đã áp dụng và context refresh.
- Kiểm tra code có đang đọc một Environment khác được tạo độc lập không.

**Test nhận nhầm context đã cache**

- Kiểm tra equals/hashCode của customizer.
- Xác nhận mọi tham số cấu hình đều được tính vào equality.
- Kiểm tra các thành phần khác của MergedContextConfiguration.
- Chỉ dùng @DirtiesContext khi test thật sự làm thay đổi context và cần loại context khỏi cache; không dùng nó để che một lỗi equality.

**Test chạy riêng xanh nhưng chạy cả suite lại sai**

- Kiểm tra bean singleton có mutable state không.
- Kiểm tra customizer hoặc factory có giữ trạng thái static không.
- Kiểm tra các test có dùng chung context với cấu hình tương đương không.
- Kiểm tra dữ liệu theo method có bị đặt nhầm vào customizer không.

## 12. Hướng dẫn quyết định: có nên tự viết ContextCustomizer?

Trước khi tạo customizer, hãy xem nhu cầu thuộc trường hợp nào:

| Nhu cầu | Lựa chọn nên cân nhắc đầu tiên |
|---|---|
| Một property cố định cho test | @TestPropertySource |
| Chọn bean theo profile | @ActiveProfiles và @Profile |
| Thêm một bean test-only | @TestConfiguration và @Import |
| Property động từ container/server | @DynamicPropertySource |
| Một initializer được chỉ định rõ | ApplicationContextInitializer |
| Quy tắc tùy chỉnh dựa trên annotation/metadata của nhiều test class | ContextCustomizerFactory |
| Cần thay bean trong context bằng mock | Cơ chế bean override của Spring/Boot phù hợp phiên bản |

Tự viết ContextCustomizer phù hợp khi có một quy tắc cấu hình lặp lại, phụ thuộc metadata của test class và không được biểu diễn gọn bằng các API khai báo sẵn.

Khi triển khai, cần đảm bảo:

1. Factory được phát hiện trên test runtime classpath.
2. Factory chỉ tạo customizer khi test class thực sự cần.
3. Customizer chỉ thay đổi context trước refresh.
4. Dữ liệu cấu hình bất biến và được xác định rõ.
5. equals/hashCode phản ánh toàn bộ cấu hình có ảnh hưởng đến context.
6. Customizer không thực hiện công việc theo từng test method.
7. Property precedence và bean name được kiểm soát.
8. Test có thể chạy độc lập và trong toàn bộ suite mà không phụ thuộc thứ tự.

ContextCustomizer là một công cụ mở rộng mạnh của TestContext Framework vì nó cho phép biến metadata của test thành cấu hình ApplicationContext có thể tái sử dụng. Nhưng chính sự tham gia vào context cache khiến nó cần được thiết kế cẩn thận. Khi customizer bất biến, equality đúng và thay đổi cấu hình được giới hạn rõ ràng, các test có thể chia sẻ context an toàn, đồng thời những test cần cấu hình khác nhau vẫn nhận được context riêng. Khi nhu cầu chỉ là một property hoặc bean đơn giản, các annotation và initializer sẵn có thường giúp cấu hình dễ đọc hơn.

