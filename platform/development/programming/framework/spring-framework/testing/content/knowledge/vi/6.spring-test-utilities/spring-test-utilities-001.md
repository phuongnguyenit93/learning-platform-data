# MockEnvironment và MockPropertySource

Khi một thành phần Spring cần đọc cấu hình qua Environment, kiểm thử của thành phần đó không nhất thiết phải khởi động toàn bộ Spring ApplicationContext hoặc đọc biến môi trường thật của máy. Spring Test cung cấp hai tiện ích nhỏ để tạo môi trường cấu hình trong bộ nhớ: **MockEnvironment** và **MockPropertySource**.

- **MockEnvironment** là một implementation dùng cho kiểm thử của ConfigurableEnvironment. Nó cho phép thành phần được kiểm tra đọc property, chuyển đổi kiểu và truy vấn profile qua hợp đồng Environment quen thuộc.
- **MockPropertySource** là một PropertySource có thể điều khiển trong test. Ta có thể thêm các property tùy ý, đặt nhiều nguồn cấu hình và kiểm tra thứ tự ưu tiên giữa chúng.

Hai lớp này đặc biệt hữu ích khi unit test một class nhận Environment qua constructor, hoặc khi muốn xác nhận logic lựa chọn cấu hình mà không truy cập file, biến môi trường hệ điều hành, JVM system properties hay dịch vụ ngoài.

Chúng thuộc Spring Test, thường có sẵn qua dependency spring-test hoặc spring-boot-starter-test ở test scope. Chúng không tự tạo Spring container, không tự inject @Value và không thay thế các bài kiểm thử cần xác nhận quá trình binding hoặc auto-configuration của Spring Boot.

## 1. Environment và PropertySource trong Spring

Spring cung cấp abstraction Environment để ứng dụng đọc các giá trị cấu hình theo tên. Thay vì buộc một class tự đọc System.getenv hoặc System.getProperty, class có thể nhận Environment và yêu cầu giá trị cần thiết:

~~~java
String region = environment.getProperty("service.region");
~~~

Environment còn hỗ trợ:

- Đọc property dưới dạng String hoặc chuyển sang kiểu được yêu cầu.
- Cung cấp giá trị mặc định khi property không tồn tại.
- Giải quyết placeholder trong chuỗi.
- Kiểm tra profile đang hoạt động.
- Truy cập các nguồn property thông qua ConfigurableEnvironment.

Các giá trị không nhất thiết nằm trong một Map duy nhất. Spring biểu diễn từng nguồn cấu hình bằng PropertySource và quản lý chúng trong MutablePropertySources.

Một ứng dụng có thể nhận cấu hình từ nhiều nơi, ví dụ:

- JVM system properties.
- Environment variables của hệ điều hành.
- File cấu hình.
- Nguồn cấu hình được ứng dụng bổ sung.
- Property được khai báo riêng cho test.

Mỗi PropertySource có tên và một cách tra cứu giá trị riêng. Khi nhiều nguồn cùng chứa một key, thứ tự trong MutablePropertySources quyết định nguồn nào được ưu tiên.

~~~mermaid
flowchart TD
    Consumer["Thành phần sử dụng Environment"] --> Env["Environment / PropertyResolver"]
    Env --> Sources["MutablePropertySources"]
    Sources --> First["Nguồn ưu tiên cao"]
    Sources --> Next["Nguồn tiếp theo"]
    Sources --> Last["Nguồn ưu tiên thấp"]
    First --> Lookup["Tìm key và trả về giá trị đầu tiên tìm thấy"]
    Next --> Lookup
    Last --> Lookup
~~~

**MockEnvironment** cung cấp một môi trường có thể điều khiển cho test. **MockPropertySource** cung cấp các nguồn property có thể tự đặt dữ liệu. Kết hợp hai lớp này giúp kiểm thử cách thành phần đọc cấu hình và cách thứ tự nguồn ảnh hưởng đến kết quả.

## 2. MockEnvironment: tạo Environment trong bộ nhớ

MockEnvironment nằm trong package:

~~~java
import org.springframework.mock.env.MockEnvironment;
~~~

Có thể tạo một instance mới trong từng test:

~~~java
MockEnvironment environment = new MockEnvironment();
~~~

Sau đó thêm một MockPropertySource vào danh sách nguồn cấu hình:

~~~java
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.env.MockPropertySource;

MockEnvironment environment = new MockEnvironment();

MockPropertySource properties =
        new MockPropertySource("unitTestProperties");

properties.setProperty("feature.checkout.enabled", "true");
properties.setProperty("service.region", "ap-southeast-1");

environment.getPropertySources().addFirst(properties);
~~~

Từ đây, Environment có thể tra cứu những giá trị đã được thiết lập:

~~~java
assertEquals(
        "true",
        environment.getProperty("feature.checkout.enabled")
);

assertEquals(
        "ap-southeast-1",
        environment.getProperty("service.region")
);
~~~

MockEnvironment triển khai ConfigurableEnvironment, nên ngoài việc đọc property, test còn có thể cấu hình active profile và truy cập danh sách property source.

Một số phiên bản Spring cung cấp phương thức fluent withProperty trên MockEnvironment để thêm property trực tiếp. Dù dùng cách fluent hay gắn MockPropertySource tường minh, ý nghĩa vẫn là tạo dữ liệu cấu hình trong bộ nhớ cho test. Khi cần quan sát tên nguồn, thứ tự ưu tiên hoặc thay thế một nguồn cụ thể, cách tạo MockPropertySource riêng thường dễ hiểu hơn.

### Ví dụ: một thành phần đọc cờ tính năng

Giả sử ứng dụng có một feature flag:

~~~java
import org.springframework.core.env.Environment;

public final class CheckoutFeature {

    private final Environment environment;

    public CheckoutFeature(Environment environment) {
        this.environment = environment;
    }

    public boolean isEnabled() {
        return environment.getProperty(
                "feature.checkout.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

Class chỉ phụ thuộc vào interface Environment. Test có thể tạo một MockEnvironment và cung cấp property:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;
import org.springframework.mock.env.MockPropertySource;

class CheckoutFeatureTest {

    @Test
    void enablesCheckoutWhenPropertyIsTrue() {
        MockEnvironment environment = new MockEnvironment();

        MockPropertySource properties =
                new MockPropertySource("testProperties");
        properties.setProperty("feature.checkout.enabled", "true");

        environment.getPropertySources().addFirst(properties);

        CheckoutFeature feature = new CheckoutFeature(environment);

        assertTrue(feature.isEnabled());
    }
}
~~~

Bài test này chạy trực tiếp trên object Java. Không cần component scan, ApplicationContext, file application.yml hoặc biến môi trường thật. Nó xác nhận rằng **CheckoutFeature** đọc đúng property và áp dụng default value theo cách đã viết.

Có thể thêm test cho trường hợp thiếu property:

~~~java
@Test
void disablesCheckoutWhenPropertyIsMissing() {
    CheckoutFeature feature =
            new CheckoutFeature(new MockEnvironment());

    assertFalse(feature.isEnabled());
}
~~~

Với overload getProperty nhận kiểu và giá trị mặc định, property không tồn tại sẽ dẫn đến giá trị mặc định. Test có thể bảo vệ hành vi fallback này mà không phải chỉnh cấu hình của máy chạy.

## 3. MockPropertySource: điều khiển một nguồn cấu hình

MockPropertySource nằm trong package:

~~~java
import org.springframework.mock.env.MockPropertySource;
~~~

Nó cho phép tạo một PropertySource có dữ liệu do test đặt. Ví dụ:

~~~java
MockPropertySource properties =
        new MockPropertySource("testOverrides");

properties.setProperty("service.timeout", "2500");
properties.setProperty("service.name", "checkout-test");
~~~

Sau khi tạo, nguồn có thể được thêm vào ConfigurableEnvironment:

~~~java
environment.getPropertySources().addFirst(properties);
~~~

Các thao tác thường dùng với MutablePropertySources gồm:

| Thao tác | Ý nghĩa |
|---|---|
| addFirst(source) | Thêm nguồn ở đầu danh sách, có ưu tiên cao nhất |
| addLast(source) | Thêm nguồn ở cuối danh sách, có ưu tiên thấp nhất |
| addBefore(name, source) | Chèn nguồn trước một nguồn đã có tên |
| addAfter(name, source) | Chèn nguồn sau một nguồn đã có tên |
| remove(name) | Loại bỏ nguồn theo tên |
| replace(name, source) | Thay nguồn có tên bằng nguồn mới |

Tên nguồn cần được chọn rõ ràng và duy nhất trong test để việc thay thế hoặc loại bỏ không vô tình tác động đến nguồn khác.

### Một Environment với nhiều nguồn property

Giả sử ứng dụng có cấu hình mặc định và cấu hình override. Ta có thể tạo hai MockPropertySource:

~~~java
MockEnvironment environment = new MockEnvironment();

MockPropertySource defaults =
        new MockPropertySource("defaults");
defaults.setProperty("service.timeout", "5000");
defaults.setProperty("service.region", "default-region");

MockPropertySource testOverrides =
        new MockPropertySource("testOverrides");
testOverrides.setProperty("service.timeout", "1000");

environment.getPropertySources().addLast(defaults);
environment.getPropertySources().addFirst(testOverrides);
~~~

Khi đọc property:

~~~java
assertEquals("1000", environment.getProperty("service.timeout"));
assertEquals("default-region", environment.getProperty("service.region"));
~~~

Key service.timeout có trong cả hai nguồn. Nguồn testOverrides được thêm bằng addFirst nên được tra cứu trước và thắng giá trị mặc định. Key service.region chỉ có trong defaults nên giá trị ở đó được sử dụng.

Có thể hình dung thứ tự như sau:

~~~text
Ưu tiên cao
    testOverrides
    mockProperties của MockEnvironment (nếu còn giá trị)
    defaults
Ưu tiên thấp
~~~

Thứ tự cụ thể phụ thuộc các nguồn mà test đã thêm. Quy tắc cần nhớ là Spring tra cứu property source theo thứ tự trong MutablePropertySources và dùng giá trị đầu tiên tìm thấy. addFirst tạo nguồn ưu tiên cao; addLast tạo nguồn ưu tiên thấp.

### Kiểm thử rõ ràng hành vi override

Một test độc lập có thể chứng minh rằng giá trị override thắng giá trị mặc định:

~~~java
@Test
void firstPropertySourceOverridesLaterSource() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource defaults =
            new MockPropertySource("defaults");
    defaults.setProperty("service.timeout", "5000");

    MockPropertySource overrides =
            new MockPropertySource("overrides");
    overrides.setProperty("service.timeout", "1000");

    environment.getPropertySources().addLast(defaults);
    environment.getPropertySources().addFirst(overrides);

    assertEquals("1000", environment.getProperty("service.timeout"));
}
~~~

Test này không kiểm tra thứ tự file YAML hoặc cách Spring Boot nạp cấu hình. Nó kiểm tra quy tắc tra cứu của Environment với hai PropertySource đã được thêm trực tiếp.

## 4. Kiểm tra kiểu dữ liệu và giá trị mặc định

Giá trị trong cấu hình thường được biểu diễn dưới dạng chuỗi. Environment có các overload cho phép yêu cầu kiểu đích:

~~~java
Boolean enabled =
        environment.getProperty(
                "feature.checkout.enabled",
                Boolean.class
        );
~~~

Có thể yêu cầu một giá trị mặc định:

~~~java
boolean enabled =
        environment.getProperty(
                "feature.checkout.enabled",
                Boolean.class,
                false
        );
~~~

Điều này hữu ích khi một cấu hình có thể bị bỏ trống. Test nên mô tả cả trường hợp property tồn tại và trường hợp property vắng mặt.

~~~java
@Test
void convertsStringPropertyToBoolean() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource properties =
            new MockPropertySource("test");
    properties.setProperty("feature.enabled", "true");

    environment.getPropertySources().addFirst(properties);

    assertEquals(
            Boolean.TRUE,
            environment.getProperty("feature.enabled", Boolean.class)
    );
}
~~~

Việc chuyển đổi phụ thuộc vào cơ chế conversion được cấu hình cho Environment. Với các kiểu đơn giản như Boolean, Integer hoặc Duration trong cấu hình phù hợp, có thể kiểm tra qua API chuyển đổi kiểu. Nếu ứng dụng có converter riêng, format tùy chỉnh hoặc binding phức tạp, cần kiểm tra chính converter/binder đó trong phạm vi thích hợp.

Không nên giả định mọi chuỗi đều chuyển được sang mọi kiểu. Property sai định dạng có thể dẫn tới lỗi chuyển đổi. Nếu hành vi xử lý giá trị sai là một phần hợp đồng của thành phần, hãy viết test riêng cho trường hợp đó.

## 5. Kiểm thử thành phần phụ thuộc vào Environment

Một lý do phổ biến để dùng MockEnvironment là test class nhận Environment qua constructor. Điều này thường phù hợp với class cần đọc cấu hình để đưa ra một quyết định.

Ví dụ, một thành phần chọn endpoint theo property:

~~~java
import org.springframework.core.env.Environment;

public final class ServiceEndpoint {

    private final Environment environment;

    public ServiceEndpoint(Environment environment) {
        this.environment = environment;
    }

    public String baseUrl() {
        return environment.getProperty(
                "partner.base-url",
                "https://partner.example.test"
        );
    }
}
~~~

Test có thể xác nhận giá trị cấu hình ghi đè default:

~~~java
@Test
void usesConfiguredPartnerUrl() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource properties =
            new MockPropertySource("test");
    properties.setProperty(
            "partner.base-url",
            "https://stub.example.test"
    );

    environment.getPropertySources().addFirst(properties);

    ServiceEndpoint endpoint = new ServiceEndpoint(environment);

    assertEquals(
            "https://stub.example.test",
            endpoint.baseUrl()
    );
}
~~~

Đây chỉ là kiểm tra giá trị URL mà thành phần trả về. Nó không mở kết nối tới URL và không xác nhận endpoint có thể truy cập được. Nếu thành phần sau đó dùng URL để gọi HTTP, HTTP adapter cần được kiểm tra riêng.

### Kiểm thử profile

MockEnvironment cũng là một ConfigurableEnvironment, vì vậy test có thể thiết lập profile hoạt động:

~~~java
@Test
void recognizesTestProfile() {
    MockEnvironment environment = new MockEnvironment();
    environment.setActiveProfiles("test", "local");

    assertTrue(environment.acceptsProfiles(Profiles.of("test")));
    assertTrue(environment.acceptsProfiles(Profiles.of("local")));
    assertFalse(environment.acceptsProfiles(Profiles.of("production")));
}
~~~

Test này hữu ích khi một class tự kiểm tra profile thông qua Environment. Nó không chứng minh Spring container đã chọn đúng bean theo @Profile. Việc chọn bean theo profile xảy ra trong quá trình tạo ApplicationContext và cần context test nếu đó là hành vi cần xác nhận.

## 6. Giải quyết placeholder và property lồng nhau

Environment mở rộng PropertyResolver, nên có thể giải quyết placeholder dựa trên các property source hiện có. Ví dụ, một cấu hình có thể tham chiếu tới một key khác:

~~~java
@Test
void resolvesPlaceholderFromMockPropertySource() {
    MockEnvironment environment = new MockEnvironment();

    MockPropertySource properties =
            new MockPropertySource("test");
    properties.setProperty("service.host", "localhost");
    properties.setProperty("service.port", "8081");

    environment.getPropertySources().addFirst(properties);

    String resolved = environment.resolveRequiredPlaceholders(
            "http://$" + "{service.host}:$" + "{service.port}"
    );

    assertEquals("http://localhost:8081", resolved);
}
~~~

Ở đây, chuỗi placeholder được ghép trong ví dụ Java để tránh nhầm cú pháp tài liệu với cú pháp template. Trong code thực tế, có thể viết trực tiếp chuỗi placeholder chuẩn của Spring.

Phương thức resolveRequiredPlaceholders yêu cầu các placeholder được tham chiếu phải giải quyết được; nếu thiếu property cần thiết, thao tác sẽ báo lỗi. Phương thức resolvePlaceholders có hành vi mềm hơn với placeholder không tìm thấy và có thể giữ nguyên chuỗi chưa giải quyết, tùy cách cấu hình resolver.

Nên chọn API theo hợp đồng của ứng dụng. Nếu cấu hình bắt buộc phải có, test nên xác nhận trường hợp thiếu property được phát hiện. Nếu cấu hình có fallback, test cần xác nhận fallback đó.

## 7. MockEnvironment không thay thế Spring ApplicationContext

Đây là ranh giới quan trọng nhất khi sử dụng hai tiện ích này.

MockEnvironment giúp kiểm tra một object đọc Environment. Nó không tự thực hiện những công việc thuộc container:

- Không quét component và đăng ký bean.
- Không inject constructor hoặc field cho bean trong ứng dụng.
- Không xử lý @Value trên bean như BeanFactoryPostProcessor trong context.
- Không đánh giá @Conditional hoặc @ConditionalOnProperty để quyết định tạo bean.
- Không chạy auto-configuration của Spring Boot.
- Không thực hiện binding @ConfigurationProperties như một ApplicationContext Boot đã cấu hình.
- Không áp dụng AOP, transaction proxy hoặc method security.

Ví dụ, nếu mục tiêu là kiểm tra class thuần có gọi getProperty đúng key, MockEnvironment là đủ. Nếu mục tiêu là kiểm tra @Value được inject đúng vào bean, cần dựng Spring context với property tương ứng.

Có thể sử dụng các công cụ khác tùy câu hỏi:

| Mục tiêu | Cách kiểm thử phù hợp |
|---|---|
| Class tự đọc Environment qua constructor | MockEnvironment |
| Kiểm tra thứ tự ưu tiên PropertySource | MockEnvironment + MockPropertySource |
| Kiểm tra bean được tạo theo property | ApplicationContextRunner hoặc context test |
| Kiểm tra @Value được inject | Spring TestContext hoặc Spring Boot context test |
| Kiểm tra @ConfigurationProperties binding | Spring Boot Binder test hoặc ApplicationContextRunner |
| Kiểm tra profile chọn implementation | ApplicationContext với profile tương ứng |
| Kiểm tra giá trị động từ Testcontainers | @DynamicPropertySource hoặc cơ chế property registration phù hợp |

### Ví dụ với ApplicationContextRunner

Giả sử có cấu hình bean phụ thuộc property:

~~~java
@Configuration
class CheckoutConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "feature.checkout.enabled",
            havingValue = "true"
    )
    CheckoutFeature checkoutFeature(Environment environment) {
        return new CheckoutFeature(environment);
    }
}
~~~

Nếu muốn xác nhận bean xuất hiện khi property bằng true, có thể dùng ApplicationContextRunner của Spring Boot:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(CheckoutConfiguration.class);

@Test
void registersFeatureWhenPropertyIsEnabled() {
    contextRunner
            .withPropertyValues("feature.checkout.enabled=true")
            .run(context -> {
                assertThat(context)
                        .hasSingleBean(CheckoutFeature.class);
            });
}
~~~

Ví dụ này kiểm tra điều kiện tạo bean trong Spring Boot context. Đây là một câu hỏi khác với việc tạo MockEnvironment và gọi trực tiếp CheckoutFeature. Context runner khởi tạo cơ chế cấu hình cần thiết và đánh giá điều kiện bean trong quá trình refresh.

### Ví dụ với @TestPropertySource

Với test dùng Spring TestContext, có thể cung cấp property inline:

~~~java
@SpringJUnitConfig(CheckoutConfiguration.class)
@TestPropertySource(properties = {
        "feature.checkout.enabled=true"
})
class CheckoutConfigurationTest {
    // Autowire bean và kiểm tra context tại đây.
}
~~~

Cách này phù hợp khi muốn property tham gia vào quá trình dựng context thật của test. Nếu chỉ cần kiểm tra một class nhỏ đọc property, việc khởi tạo context có thể không cần thiết.

## 8. Các nguồn cấu hình của ứng dụng thật và giới hạn của MockEnvironment

MockEnvironment tạo môi trường có thể điều khiển trong test, nhưng nó không tự động tái hiện mọi nguồn cấu hình của runtime.

Một StandardEnvironment trong ứng dụng thường có system properties và system environment. Ứng dụng Spring Boot còn có cơ chế nạp file cấu hình, profile-specific configuration, command-line arguments và các nguồn property do Boot quản lý.

Trong khi đó, MockEnvironment được thiết kế cho test. Nó không tự đọc file application.properties, application.yml, biến môi trường của máy hoặc các nguồn cấu hình triển khai.

Điều này có hai hệ quả:

1. Test có thể chủ động đặt đúng các key cần thiết mà không phụ thuộc máy phát triển hay CI.
2. Test với MockEnvironment không chứng minh ứng dụng production đang nạp và ưu tiên các nguồn cấu hình theo đúng cách dự kiến.

Nếu code cần mô phỏng một nguồn cụ thể, hãy tạo PropertySource tương ứng và thêm nó rõ ràng. Không nên đọc biến môi trường thật chỉ để làm test pass trên máy cá nhân.

Với các trường hợp cần kiểm tra cách Spring xử lý environment variable, system property hoặc file cấu hình thật, hãy chọn test có phạm vi phù hợp và cung cấp nguồn đó một cách kiểm soát. Nếu mục tiêu là xác nhận hành vi Spring Boot Config Data, cần kiểm tra qua Spring Boot context hoặc cơ chế cấu hình tương ứng.

## 9. Những lỗi thường gặp khi dùng MockEnvironment và MockPropertySource

### Thêm property source ở sai vị trí

Nếu test có nhiều nguồn cùng chứa một key, nguồn được thêm ở vị trí đầu sẽ được ưu tiên. Dùng addLast khi muốn override có thể khiến test nhận giá trị khác dự kiến.

Hãy đặt tên nguồn và thêm bằng addFirst/addLast có chủ đích. Trong test về precedence, assertion nên kiểm tra trực tiếp giá trị cuối cùng mà Environment trả về.

### Dùng lại một MockEnvironment giữa nhiều test

MockEnvironment và MockPropertySource có thể thay đổi. Nếu dùng chung static instance, một test có thể để lại property hoặc active profile ảnh hưởng test tiếp theo.

Tạo environment mới cho mỗi test hoặc mỗi fixture. Nếu có helper dùng chung, helper nên trả về instance mới với dữ liệu được khai báo rõ ràng.

### Kiểm tra Environment nhưng kết luận @Value đã hoạt động

Một object được tạo trực tiếp và nhận MockEnvironment không trải qua quá trình xử lý @Value của Spring. Muốn xác nhận injection, cần bean được tạo bởi context và assertion trên giá trị được inject.

### Kiểm tra property trực tiếp nhưng kết luận @ConditionalOnProperty đúng

Điều kiện bean được đánh giá trong quá trình cấu hình context. Việc Environment trả về chuỗi "true" không tự chứng minh conditional configuration đã đăng ký bean. Dùng ApplicationContextRunner hoặc một context test để kiểm tra kết quả tạo bean.

### Giả định MockEnvironment có dữ liệu từ máy chạy

Không nên giả định MockEnvironment tự mang theo mọi system property hoặc environment variable của máy. Hãy đặt dữ liệu cần thiết trực tiếp bằng MockPropertySource. Cách này giữ test ổn định giữa máy cá nhân, CI và các môi trường khác nhau.

### Dùng mock property để kiểm tra dịch vụ bên ngoài

MockPropertySource chỉ cung cấp dữ liệu cấu hình. Nó không tạo database, HTTP server hoặc broker. Nếu test cần xác nhận kết nối tới endpoint, cần kiểm thử adapter hoặc tích hợp riêng.

### Không kiểm tra trường hợp thiếu hoặc sai property

Một test chỉ kiểm tra giá trị cấu hình đúng có thể bỏ qua hành vi fallback hoặc lỗi khi property không hợp lệ. Hãy mô tả rõ property nào bắt buộc, property nào có default và giá trị sai được xử lý thế nào.

## 10. Tổ chức helper để tạo môi trường test dễ đọc

Nếu nhiều test cần cùng một nhóm property, có thể tạo một factory nhỏ. Factory nên tạo instance mới mỗi lần gọi và để test override những key cần thiết.

~~~java
final class TestEnvironments {

    private TestEnvironments() {
    }

    static MockEnvironment checkoutEnabled() {
        MockEnvironment environment = new MockEnvironment();

        MockPropertySource properties =
                new MockPropertySource("checkoutTest");

        properties.setProperty("feature.checkout.enabled", "true");
        properties.setProperty("service.region", "test-region");

        environment.getPropertySources().addFirst(properties);

        return environment;
    }
}
~~~

Test sử dụng factory:

~~~java
@Test
void enablesCheckoutInConfiguredEnvironment() {
    CheckoutFeature feature =
            new CheckoutFeature(TestEnvironments.checkoutEnabled());

    assertTrue(feature.isEnabled());
}
~~~

Nếu một test cần tắt feature, nên tạo fixture riêng hoặc cho factory nhận tham số có ý nghĩa thay vì sửa global state. Không nên xây dựng một bộ test utility quá phức tạp chỉ để tránh vài dòng khởi tạo.

## 11. Khi nào nên chọn từng tiện ích?

**Chọn MockEnvironment khi:**

- Class nhận Environment hoặc ConfigurableEnvironment qua constructor.
- Cần kiểm tra logic đọc property, giá trị mặc định hoặc chuyển đổi kiểu.
- Cần kiểm tra logic liên quan active profile ở cấp object.
- Muốn test không phụ thuộc system property hoặc environment variable thật.

**Chọn MockPropertySource khi:**

- Cần tự tạo một nguồn cấu hình trong bộ nhớ.
- Cần kiểm tra thứ tự ưu tiên giữa nhiều nguồn.
- Cần thêm, thay thế hoặc loại bỏ một nguồn theo tên.
- Cần cung cấp một nhóm key cho Environment trong test.

**Chọn Spring context test khi:**

- Cần xác nhận bean được đăng ký theo property/profile.
- Cần kiểm tra @Value hoặc @ConfigurationProperties binding.
- Cần kiểm tra auto-configuration, conditional bean hoặc cơ chế injection.
- Cần chứng minh cấu hình Spring thực sự được áp dụng trong ApplicationContext.

Hai tiện ích MockEnvironment và MockPropertySource rất phù hợp với unit test vì chúng làm cho dữ liệu cấu hình trở nên tường minh, có thể kiểm soát và không cần mạng. Hãy dùng chúng để kiểm tra cách một thành phần đọc và diễn giải Environment; khi câu hỏi chuyển sang cách Spring nạp cấu hình, bind property hoặc tạo bean, hãy chuyển sang context test tương ứng. Sự phân biệt này giúp test nhanh, độc lập và chứng minh đúng hành vi mà nó được thiết kế để bảo vệ.

