# Tiêm ApplicationContext và Environment

Trong các bài kiểm thử Spring, đôi khi test cần truy cập trực tiếp vào ApplicationContext hoặc Environment để xác nhận cấu hình, kiểm tra bean đã được đăng ký và đọc các thuộc tính của môi trường kiểm thử. Spring TestContext Framework hỗ trợ inject hai đối tượng này vào test instance thông qua cơ chế dependency injection. Nhờ đó, test có thể quan sát context mà framework đã tạo và kiểm tra các giá trị cấu hình đang có hiệu lực.

ApplicationContext đại diện cho container quản lý bean của Spring. Environment cung cấp thông tin về profile và các nguồn thuộc tính (property sources) mà ứng dụng sử dụng. Hai đối tượng có liên hệ chặt chẽ, nhưng phục vụ hai mục đích khác nhau: context giúp truy cập bean và cấu trúc ứng dụng; environment giúp đọc profile và thuộc tính cấu hình.

## 1. ApplicationContext và Environment là gì?

### ApplicationContext

ApplicationContext là interface trung tâm của Spring IoC container. Nó mở rộng BeanFactory và cung cấp thêm các khả năng như:

- Truy cập bean đã đăng ký bằng tên hoặc kiểu.
- Truy cập resource theo cơ chế ResourceLoader.
- Phát và nhận application event.
- Giải quyết message thông qua MessageSource.
- Cung cấp Environment gắn với context.
- Hỗ trợ context cha-con trong cấu trúc ứng dụng phân cấp.

Trong ứng dụng, Spring tạo ApplicationContext từ cấu hình Java, XML, component scan hoặc cấu hình Spring Boot. Các bean được tạo và kết nối trong context theo dependency graph đã khai báo.

### Environment

Environment là abstraction đại diện cho môi trường chạy ứng dụng. Nó tập hợp hai nhóm thông tin chính:

- **Profiles:** các profile đang hoạt động hoặc profile mặc định, dùng để chọn bean và cấu hình phù hợp.
- **Properties:** các thuộc tính được tổng hợp từ nhiều PropertySource, chẳng hạn JVM system properties, environment variables, file cấu hình và thuộc tính dành riêng cho test.

Một Environment có thể trả lời câu hỏi như:

- Profile test có đang hoạt động không?
- Thuộc tính feature.inventory.enabled có giá trị gì?
- Thuộc tính bắt buộc service.endpoint có tồn tại không?
- Giá trị cấu hình có thể chuyển sang kiểu số, boolean hoặc kiểu dữ liệu khác không?

### Mối quan hệ giữa hai đối tượng

ApplicationContext cung cấp Environment của chính nó thông qua phương thức getEnvironment(). Vì vậy, trong một test context thông thường, Environment được inject là môi trường cấu hình mà context đang sử dụng.

~~~text
Spring TestContext Framework
          |
          v
   ApplicationContext
          |
          +---- Bean definitions và bean instances
          |
          +---- Environment
                    |
                    +---- Active / default profiles
                    |
                    +---- PropertySource thứ nhất
                    +---- PropertySource thứ hai
                    +---- PropertySource tiếp theo
~~~

Test có thể inject ApplicationContext để truy cập bean, đồng thời inject Environment để đọc cấu hình. Nếu chỉ cần đọc một property, inject Environment trực tiếp thường đơn giản hơn việc lấy Environment thông qua ApplicationContext.

## 2. Spring inject hai đối tượng vào test instance như thế nào?

TestContext Framework tích hợp với JUnit thông qua SpringExtension. Trong quá trình chuẩn bị test instance, DependencyInjectionTestExecutionListener yêu cầu Spring thực hiện autowire trên các trường hoặc phương thức injection của test class. ApplicationContext và Environment là các đối tượng hạ tầng mà Spring có thể cung cấp cho test.

Ví dụ đơn giản:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ContextAndEnvironmentTest {
    @Autowired
    private ApplicationContext applicationContext;

    @Autowired
    private Environment environment;

    @Test
    void injectsContextAndEnvironment() {
        assertNotNull(applicationContext);
        assertNotNull(environment);
    }
}
~~~

@SpringJUnitConfig kết hợp việc đăng ký SpringExtension với cấu hình context cho JUnit Jupiter. Khi test chạy, Spring tạo hoặc lấy lại ApplicationContext phù hợp từ context cache, sau đó inject các đối tượng cần thiết vào test instance.

Test class vẫn do JUnit quản lý. ApplicationContext là đối tượng do Spring TestContext tạo và quản lý. Việc inject context vào test không biến test class thành bean của ứng dụng.

Nếu dùng @ContextConfiguration thay cho @SpringJUnitConfig, cần đăng ký SpringExtension riêng:

~~~java
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class ContextAndEnvironmentWithExtensionTest {
    // Có thể inject ApplicationContext và Environment tại đây.
}
~~~

Với JUnit Jupiter, @SpringJUnitConfig thường ngắn gọn hơn cho trường hợp thông dụng.

## 3. Inject ApplicationContext để kiểm tra bean

Sau khi được inject, test có thể dùng ApplicationContext để xác nhận bean đã được đăng ký, kiểm tra kiểu bean hoặc lấy một bean cụ thể.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(InventoryTestConfig.class)
class InventoryContextTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void registersInventoryService() {
        assertTrue(context.containsBean("inventoryService"));

        InventoryService service =
                context.getBean(InventoryService.class);

        assertNotNull(service);
    }
}
~~~

Các phương thức thường dùng:

| Phương thức | Công dụng |
|---|---|
| getBean(Class<T>) | Lấy bean theo kiểu |
| getBean(String) | Lấy bean theo tên |
| getBean(String, Class<T>) | Lấy bean theo tên và kiểm tra kiểu |
| containsBean(String) | Kiểm tra tên bean có tồn tại trong context hay không |
| getBeanNamesForType(Class<?>) | Lấy các tên bean phù hợp với một kiểu |
| getBeansOfType(Class<T>) | Lấy các bean phù hợp với một kiểu dưới dạng map |
| getParent() | Truy cập context cha nếu có |
| getEnvironment() | Lấy Environment gắn với context |

Nếu có nhiều bean cùng implement một interface, getBean(Interface.class) có thể ném NoUniqueBeanDefinitionException. Trong trường hợp đó, test có thể truy vấn theo tên bean, kiểm tra tập bean theo kiểu hoặc xác nhận qualifier/primary theo cấu hình.

Ví dụ kiểm tra nhiều implementation:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PaymentTestConfig.class)
class PaymentConfigurationTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void registersTheExpectedPaymentGateways() {
        Map<String, PaymentGateway> gateways =
                context.getBeansOfType(PaymentGateway.class);

        assertEquals(2, gateways.size());
        assertTrue(gateways.containsKey("cardPaymentGateway"));
        assertTrue(gateways.containsKey("bankTransferGateway"));
    }
}
~~~

Đoạn test minh họa việc quan sát bean graph. Trong một bài test thực tế, lớp test cần có cấu hình Spring tương ứng, chẳng hạn @SpringJUnitConfig(PaymentTestConfig.class).

### Kiểm tra bean theo tên và kiểu

Tên bean có thể được tạo từ tên lớp khi dùng component scan hoặc được chỉ định rõ trong @Bean. Khi test kiểm tra tên bean, nó đang xác nhận một chi tiết của cấu hình. Chỉ nên khóa chặt tên khi tên đó là một phần có ý nghĩa của hợp đồng cấu hình; nếu không, kiểm tra theo kiểu hoặc hành vi thường ít phụ thuộc vào cách đặt tên hơn.

~~~java
@Configuration
class InventoryTestConfig {
    @Bean
    InventoryRepository inventoryRepository() {
        return new InMemoryInventoryRepository();
    }

    @Bean
    InventoryService inventoryService(
            InventoryRepository inventoryRepository) {
        return new InventoryService(inventoryRepository);
    }
}
~~~

Test có thể lấy InventoryService theo kiểu mà không cần biết tên bean do phương thức cấu hình tạo ra. Cách này phù hợp khi chỉ cần xác nhận context có thể cung cấp một bean theo hợp đồng.

## 4. Inject Environment để đọc thuộc tính

Environment cho phép test đọc các property đã được tổng hợp từ những nguồn cấu hình khác nhau. Phương thức getProperty() trả về null nếu không tìm thấy property; có thể cung cấp giá trị mặc định hoặc yêu cầu property bắt buộc.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestPropertySource(properties = {
        "feature.inventory.enabled=true",
        "inventory.retry-count=3",
        "inventory.region=ap-southeast-1"
})
class EnvironmentPropertyTest {
    @Autowired
    private Environment environment;

    @Test
    void readsTestProperties() {
        assertEquals(
                "true",
                environment.getProperty("feature.inventory.enabled"));

        assertEquals(
                3,
                environment.getProperty("inventory.retry-count", Integer.class));

        assertEquals(
                "ap-southeast-1",
                environment.getRequiredProperty("inventory.region"));

        assertFalse(
                environment.getProperty("feature.missing", Boolean.class, false));
    }
}
~~~

Trong ví dụ, @TestPropertySource thêm thuộc tính vào môi trường của test context. Test đọc giá trị qua Environment mà không cần truy cập trực tiếp vào hệ điều hành hoặc file cấu hình. Phương thức getProperty(key, targetType) yêu cầu Spring chuyển giá trị sang kiểu đích bằng cơ chế conversion phù hợp.

Các cách đọc property thường dùng:

~~~java
String endpoint = environment.getProperty("service.endpoint");

String endpointOrDefault = environment.getProperty(
        "service.endpoint",
        "http://localhost:8080");

int timeout = environment.getProperty(
        "service.timeout",
        Integer.class,
        2000);

String requiredEndpoint = environment.getRequiredProperty(
        "service.endpoint");
~~~

getRequiredProperty() ném IllegalStateException khi property không tồn tại. Cách này phù hợp khi test cần xác nhận một cấu hình bắt buộc đã được cung cấp. Với cấu hình tùy chọn, dùng getProperty() cùng giá trị mặc định sẽ diễn đạt đúng ý định hơn.

### Kiểm tra property có tồn tại

Environment có containsProperty() để kiểm tra một key có thể được phân giải từ các nguồn property hiện tại hay không:

~~~java
assertTrue(environment.containsProperty("service.endpoint"));
~~~

containsProperty() chỉ xác nhận khả năng tìm thấy key. Nếu cần xác nhận giá trị hoặc kiểu dữ liệu, hãy đọc property và assertion trên kết quả.

## 5. Đọc và kiểm tra active profiles

Profiles cho phép Spring lựa chọn bean hoặc cấu hình theo môi trường, ví dụ test, development, staging hoặc production. Environment cung cấp danh sách profile đang hoạt động và profile mặc định.

Test có thể khai báo profile bằng @ActiveProfiles:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@ActiveProfiles("test")
class ActiveProfileTest {
    @Autowired
    private Environment environment;

    @Test
    void activatesTheTestProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
    }
}
~~~

Có thể đọc trực tiếp các profile:

~~~java
String[] activeProfiles = environment.getActiveProfiles();
String[] defaultProfiles = environment.getDefaultProfiles();
~~~

getActiveProfiles() trả về những profile đã được kích hoạt. Nếu không có profile active, Spring có thể sử dụng profile mặc định, thường là default. getDefaultProfiles() cho biết tập profile mặc định của Environment.

Phương thức acceptsProfiles(Profiles.of("test")) kiểm tra điều kiện profile theo biểu thức của Spring. Với nhiều profile, có thể viết:

~~~java
boolean testOrIntegration = environment.acceptsProfiles(
        Profiles.of("test", "integration"));
~~~

Trong biểu thức này, Profiles.of("test", "integration") có nghĩa test chấp nhận nếu một trong các profile được nêu đang hoạt động. Có thể dùng toán tử phủ định trong biểu thức profile, ví dụ !production, khi cần kiểm tra điều kiện ngược.

### Profile ảnh hưởng đến bean nào?

@Profile có thể điều khiển việc đăng ký bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
class PaymentConfiguration {
    @Bean
    @Profile("test")
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("production")
    PaymentGateway livePaymentGateway() {
        return new LivePaymentGateway();
    }
}
~~~

Test có thể inject Environment để xác nhận profile test đang hoạt động và dùng ApplicationContext để xác nhận bean tương ứng được đăng ký:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(PaymentConfiguration.class)
@ActiveProfiles("test")
class PaymentProfileTest {
    @Autowired
    private Environment environment;

    @Autowired
    private ApplicationContext context;

    @Test
    void loadsTheFakeGatewayForTests() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertTrue(context.containsBean("fakePaymentGateway"));
        assertFalse(context.containsBean("livePaymentGateway"));
    }
}
~~~

Ví dụ cho thấy hai đối tượng hỗ trợ hai loại assertion: Environment xác nhận profile; ApplicationContext xác nhận bean graph kết quả từ profile đó.

## 6. Kiểm tra thuộc tính và profile cùng lúc

Một test cấu hình có thể xác nhận cả profile lẫn giá trị property. Ví dụ ứng dụng bật một tính năng theo profile test và property:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

@Configuration
class FeatureTestConfig {
    @Bean
    @Profile("test")
    FeatureService featureService(Environment environment) {
        boolean enabled = environment.getProperty(
                "feature.inventory.enabled",
                Boolean.class,
                false);
        return new FeatureService(enabled);
    }
}

class FeatureService {
    private final boolean enabled;

    FeatureService(boolean enabled) {
        this.enabled = enabled;
    }

    boolean isEnabled() {
        return enabled;
    }
}
~~~

Test có thể cung cấp profile và property:

~~~java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(FeatureTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "feature.inventory.enabled=true")
class FeatureEnvironmentTest {
    @Autowired
    private Environment environment;

    @Autowired
    private FeatureService featureService;

    @Test
    void loadsFeatureConfigurationForTestProfile() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertTrue(environment.getProperty(
                "feature.inventory.enabled",
                Boolean.class,
                false));
        assertTrue(featureService.isEnabled());
    }
}
~~~

Ở đây, cấu hình bean đọc Environment khi Spring tạo FeatureService. Test đồng thời kiểm tra giá trị property và hành vi của bean đã được tạo. Nếu chỉ kiểm tra property, assertion trên Environment là đủ; nếu cần xác nhận property thực sự ảnh hưởng đến cấu hình bean, nên kiểm tra thêm bean hoặc hành vi tương ứng.

## 7. Environment và @Value có vai trò khác nhau

@Value là cơ chế inject một giá trị đã được phân giải vào trường, tham số constructor hoặc phương thức. Environment là abstraction cho phép truy vấn nhiều property một cách linh hoạt tại thời điểm chạy.

Ví dụ dùng @Value:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
class InventoryClientSettings {
    private final String endpoint;
    private final int timeout;

    InventoryClientSettings(
            @Value("\u0024{inventory.endpoint}") String endpoint,
            @Value("\u0024{inventory.timeout:2000}") int timeout) {
        this.endpoint = endpoint;
        this.timeout = timeout;
    }

    String endpoint() {
        return endpoint;
    }

    int timeout() {
        return timeout;
    }
}
~~~

Ví dụ dùng Environment:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class InventoryEndpointResolver {
    private final Environment environment;

    InventoryEndpointResolver(Environment environment) {
        this.environment = environment;
    }

    String endpointFor(String region) {
        String key = "inventory.endpoint." + region;
        return environment.getRequiredProperty(key);
    }
}
~~~

@Value phù hợp khi một bean cần một số giá trị xác định trong cấu hình. Environment phù hợp khi cần truy vấn property theo key, kiểm tra profile hoặc xử lý một tập thuộc tính động. Với cấu hình có nhiều trường liên quan, @ConfigurationProperties thường cung cấp mô hình có kiểu rõ ràng hơn.

Trong test, có thể inject Environment để xác nhận property source và inject bean settings để xác nhận giá trị cuối cùng đã được bind. Không nên thay thế toàn bộ kiểm tra cấu hình bean bằng việc chỉ đọc property, vì bean còn có thể áp dụng default, validation hoặc logic chuyển đổi riêng.

## 8. PropertySource và thứ tự ưu tiên

Environment tổng hợp giá trị từ nhiều PropertySource. Khi cùng một key xuất hiện ở nhiều nguồn, thứ tự ưu tiên quyết định giá trị nào được trả về.

Các nguồn thường gặp gồm:

- JVM system properties, chẳng hạn tham số -Dinventory.timeout=3000.
- Environment variables của hệ điều hành.
- File cấu hình ứng dụng.
- Thuộc tính khai báo bằng @TestPropertySource.
- Thuộc tính động đăng ký qua @DynamicPropertySource.
- Property source được thêm bởi cấu hình hoặc framework tích hợp.

Với Spring TestContext Framework, inline properties của @TestPropertySource có độ ưu tiên cao hơn các resource locations được khai báo trong cùng annotation. Những property source khác có thứ tự cụ thể theo cơ chế Environment và TestContext. Trong Spring Boot, Config Data và các nguồn cấu hình Boot cũng tham gia hệ thống precedence của Boot.

Test có thể xem các PropertySource đang có:

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.core.env.PropertySource;

void printPropertySources(Environment environment) {
    ConfigurableEnvironment configurableEnvironment =
            (ConfigurableEnvironment) environment;

    for (PropertySource<?> source :
            configurableEnvironment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

Environment là interface thiên về truy vấn. Để duyệt danh sách PropertySource, cần dùng ConfigurableEnvironment, interface mở rộng có API cấu hình và truy cập PropertySources. Trong test, nếu mục tiêu là quan sát thứ tự, có thể ép kiểu khi context thực tế cung cấp ConfigurableEnvironment.

~~~java
ConfigurableEnvironment configurableEnvironment =
        (ConfigurableEnvironment) environment;

MutablePropertySources propertySources =
        configurableEnvironment.getPropertySources();

PropertySource<?> highestPrioritySource =
        propertySources.iterator().next();
~~~

Đoạn trên cần import MutablePropertySources. Không nên mặc định tên hoặc vị trí một PropertySource giống nhau trong mọi phiên bản và mọi loại context. Hãy dùng environment.getProperty(key) để kiểm tra giá trị hiệu lực; chỉ duyệt property sources khi cần chẩn đoán nguồn cung cấp.

## 9. Dùng ApplicationContext và Environment trong context hierarchy

Một test có thể tải context cha và context con. Context con có thể truy cập bean từ context cha, đồng thời có Environment riêng gắn với context. Việc inject ApplicationContext vào test cho phép quan sát context mà test đang sử dụng; getParent() giúp kiểm tra quan hệ hierarchy nếu cấu hình có parent.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.ContextHierarchy;
import org.springframework.test.context.junit.jupiter.SpringExtension;

@ExtendWith(SpringExtension.class)
@ContextHierarchy({
    @ContextConfiguration(classes = RootTestConfig.class),
    @ContextConfiguration(classes = WebTestConfig.class)
})
class WebApplicationContextTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void exposesTheParentContextWhenConfigured() {
        ApplicationContext parent = context.getParent();
        assertNotNull(parent);
    }
}
~~~

Test này cần được khai báo với @ContextHierarchy hoặc cấu hình tương ứng để có parent context. Nếu không có hierarchy, getParent() có thể trả về null. Trong ví dụ, @ContextHierarchy tự tích hợp cấu hình context phân cấp; không cần đồng thời đặt @SpringJUnitConfig.

Với context phân cấp, bean từ parent có thể được tìm thấy qua child context. Vì vậy, containsBean() hoặc getBean() trên child có thể nhìn thấy bean được kế thừa từ parent. Nếu cần xác nhận bean được định nghĩa ở cấp nào, hãy truy vấn parent riêng và so sánh với child.

Environment của context có thể chịu ảnh hưởng từ quan hệ cha-con và cấu hình property source. Khi kiểm tra profile hoặc property trong hierarchy, hãy xác định rõ test đang inject context nào và giá trị được cung cấp ở cấp cấu hình nào.

## 10. Inject bằng constructor hoặc tham số test method

Ngoài field injection, SpringExtension hỗ trợ parameter injection cho JUnit Jupiter. Cách này hữu ích khi chỉ một test method cần ApplicationContext hoặc Environment.

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
class ContextParameterTest {
    @Test
    void receivesContextAndEnvironment(
            @Autowired ApplicationContext context,
            @Autowired Environment environment) {
        assertNotNull(context);
        assertNotNull(environment);
    }
}
~~~

Nếu muốn inject constructor parameter cho toàn bộ test class, có thể dùng @TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL) hoặc cấu hình chế độ autowire toàn cục theo Spring TestContext. Khi đó, SpringExtension tham gia phân giải tham số constructor.

Chọn field injection khi nhiều test method dùng chung context hoặc environment. Chọn method parameter injection khi chỉ một số method cần chúng và muốn thể hiện phụ thuộc ngay trên chữ ký method. Cả hai cách đều không làm test class trở thành bean.

## 11. Tránh dùng ApplicationContext như service locator trong mã ứng dụng

ApplicationContext có thể lấy bean theo tên hoặc kiểu, nhưng điều đó không có nghĩa mọi service nên nhận context rồi tự tìm dependency khi cần.

Ví dụ thiết kế phụ thuộc ẩn:

~~~java
public class OrderService {
    private final ApplicationContext context;

    public OrderService(ApplicationContext context) {
        this.context = context;
    }

    public void placeOrder(Order order) {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        gateway.charge(order);
    }
}
~~~

Constructor chỉ cho thấy OrderService phụ thuộc vào ApplicationContext; dependency thực sự là PaymentGateway bị ẩn bên trong phương thức. Unit test phải tạo hoặc mock cả ApplicationContext, rồi cấu hình getBean(). Điều đó làm test gắn với cơ chế tra cứu bean và khiến đồ thị phụ thuộc khó đọc.

Thiết kế rõ hơn là inject trực tiếp collaborator:

~~~java
public class OrderService {
    private final PaymentGateway paymentGateway;

    public OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public void placeOrder(Order order) {
        paymentGateway.charge(order);
    }
}
~~~

ApplicationContext injection có ích trong test cần kiểm tra cấu hình container, hoặc trong một số thành phần hạ tầng có nhu cầu thực sự cần truy cập container. Với logic nghiệp vụ thông thường, constructor injection của từng dependency giúp mã dễ hiểu và dễ kiểm thử hơn.

Environment cũng nên được sử dụng có chủ đích. Một bean cần một tập cấu hình cố định thường có thể nhận các giá trị qua constructor hoặc @ConfigurationProperties. Inject toàn bộ Environment vào nhiều service để tra cứu property tùy ý có thể làm cấu hình bị phân tán và khó kiểm soát.

## 12. Không thay đổi context hoặc Environment tùy tiện trong test

ApplicationContext và Environment được dùng chung bởi các test có cùng cache key. Nếu một test sửa property source hoặc trạng thái bean dùng chung, test khác có thể quan sát kết quả đã bị thay đổi.

ConfigurableEnvironment cho phép thêm, xóa hoặc sắp xếp PropertySource. API này hữu ích khi xây dựng context, nhưng việc thay đổi sau khi context đã được sử dụng có thể khiến kết quả test phụ thuộc thứ tự chạy.

Nếu cần cấu hình property cho test, ưu tiên các cơ chế khai báo:

- @TestPropertySource cho thuộc tính cố định của test.
- @ActiveProfiles cho profile của test.
- @DynamicPropertySource cho giá trị chỉ có được lúc chạy, chẳng hạn cổng Testcontainers.
- Cấu hình test riêng hoặc bean override cho dependency cần thay thế.

Ví dụ khai báo property tĩnh:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(TestConfiguration.class)
@TestPropertySource(properties = {
        "inventory.endpoint=http://localhost:8081",
        "inventory.timeout=1500"
})
class InventoryEndpointTest {
    @Autowired
    private Environment environment;

    @Test
    void readsTheConfiguredEndpoint() {
        assertEquals(
                "http://localhost:8081",
                environment.getRequiredProperty("inventory.endpoint"));
    }
}
~~~

Nếu thật sự cần thêm PropertySource theo chương trình, hãy thực hiện ở giai đoạn khởi tạo context qua initializer hoặc cơ chế cấu hình thích hợp. Tránh thêm property source trong một test method rồi kỳ vọng các test khác có trạng thái độc lập.

## 13. Lỗi thường gặp khi inject ApplicationContext và Environment

### Test không nhận được injection

Nếu trường ApplicationContext hoặc Environment vẫn null, kiểm tra test đã được tích hợp SpringExtension chưa. Với JUnit Jupiter, dùng @SpringJUnitConfig hoặc kết hợp @ExtendWith(SpringExtension.class) và @ContextConfiguration. Cũng cần kiểm tra test có đang chạy bằng JUnit Jupiter hay một test engine khác không hỗ trợ cùng cơ chế.

### Không tìm thấy bean khi gọi getBean()

NoSuchBeanDefinitionException cho biết context hiện tại không có bean phù hợp. Kiểm tra lớp cấu hình đã được nạp, component scan có bao phủ package cần thiết, profile có đang hoạt động và điều kiện đăng ký bean có được đáp ứng không.

### Có nhiều bean cùng kiểu

NoUniqueBeanDefinitionException xảy ra khi tra cứu theo kiểu nhưng có nhiều bean cùng thỏa mãn. Dùng tên bean, qualifier hoặc kiểm tra tập bean theo kiểu. Nếu ứng dụng cần một lựa chọn mặc định, xác định rõ @Primary hoặc @Qualifier trong cấu hình.

### Property trả về null

Environment.getProperty() trả về null khi không tìm thấy key. Kiểm tra chính tả, property source đã được nạp, profile, resource path và precedence. Dùng getRequiredProperty() khi thiếu property phải được xem là lỗi.

### Đọc sai profile

getActiveProfiles() có thể trả về mảng rỗng nếu test không kích hoạt profile rõ ràng. Khi đó, Spring sử dụng default profile. Khai báo @ActiveProfiles nếu test cần một profile cụ thể và kiểm tra bằng acceptsProfiles(Profiles.of(...)).

### Property source bị thay đổi giữa các test

Nếu test sửa ConfigurableEnvironment hoặc thay đổi singleton bean, context cache có thể làm trạng thái tồn tại qua nhiều test. Chuyển cấu hình sang annotation hoặc initializer và dọn trạng thái dùng chung bằng cơ chế có vòng đời rõ ràng.

### Đóng ApplicationContext thủ công

Không tự đóng context được inject trong test. TestContext Framework quản lý context cache và vòng đời đóng context khi cần. Đóng context thủ công có thể làm những test khác đang dùng cùng cache entry thất bại. Chỉ quản lý vòng đời context do chính test tạo độc lập ngoài TestContext.

## 14. Ví dụ tổng hợp: kiểm tra bean, profile và property

Ví dụ dưới đây kết hợp cấu hình bean theo profile với property được cung cấp cho test:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.env.Environment;

interface NotificationGateway {
    String endpoint();
}

class TestNotificationGateway implements NotificationGateway {
    private final String endpoint;

    TestNotificationGateway(String endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public String endpoint() {
        return endpoint;
    }
}

@Configuration
class NotificationTestConfig {
    @Bean
    @Profile("test")
    NotificationGateway notificationGateway(Environment environment) {
        String endpoint = environment.getRequiredProperty(
                "notification.endpoint");
        return new TestNotificationGateway(endpoint);
    }
}
~~~

Test inject cả ApplicationContext và Environment:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(NotificationTestConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties =
        "notification.endpoint=http://localhost:9090")
class NotificationContextTest {
    @Autowired
    private ApplicationContext context;

    @Autowired
    private Environment environment;

    @Test
    void exposesTheExpectedTestConfiguration() {
        assertTrue(environment.acceptsProfiles(Profiles.of("test")));
        assertEquals(
                "http://localhost:9090",
                environment.getRequiredProperty("notification.endpoint"));

        NotificationGateway gateway =
                context.getBean(NotificationGateway.class);

        assertEquals(
                "http://localhost:9090",
                gateway.endpoint());
    }
}
~~~

Test xác nhận ba điều: profile test đang hoạt động, Environment cung cấp endpoint mong muốn và ApplicationContext có NotificationGateway được tạo theo cấu hình đó. Cấu hình không cần khởi tạo một endpoint bên ngoài vì implementation trong test chỉ giữ giá trị endpoint để minh họa việc bind property.

## 15. Nguyên tắc sử dụng

- Inject ApplicationContext khi test cần quan sát bean graph, cấu hình container hoặc quan hệ context cha-con.
- Inject Environment khi test cần kiểm tra profile, property source hoặc giá trị cấu hình hiệu lực.
- Dùng getProperty() cho property tùy chọn và getRequiredProperty() cho property bắt buộc.
- Dùng getProperty(key, type) để nhận giá trị đã chuyển sang kiểu cần thiết.
- Dùng getActiveProfiles(), getDefaultProfiles() và acceptsProfiles() để kiểm tra profile.
- Dùng @TestPropertySource, @ActiveProfiles hoặc @DynamicPropertySource để cung cấp cấu hình cho test.
- Dùng @Autowired field, constructor hoặc method parameter qua SpringExtension tùy phạm vi sử dụng.
- Phân biệt mock trong test fixture với bean trong ApplicationContext; dùng bean override khi cần thay dependency trong context.
- Không dùng ApplicationContext như service locator trong logic nghiệp vụ thông thường; inject dependency cụ thể qua constructor.
- Không sửa Environment hoặc đóng context được TestContext quản lý trong test method.
- Dùng log và truy vấn property source khi cần chẩn đoán nguồn cấu hình, nhưng ưu tiên kiểm tra giá trị hiệu lực qua Environment.

ApplicationContext và Environment là hai đối tượng hạ tầng hữu ích trong kiểm thử Spring. Context cho phép xác nhận bean đã được đăng ký và kết nối; Environment cho phép xác nhận profile và property đang có hiệu lực. Khi inject đúng đối tượng và giữ việc quan sát cấu hình trong phạm vi phù hợp, test có thể kiểm tra cách Spring lắp ráp ứng dụng mà vẫn giữ rõ ranh giới giữa fixture của test và bean do container quản lý.
