# EnvironmentAware, ApplicationContextAware và giới hạn phụ thuộc vào container

Spring cung cấp nhóm interface **Aware** để một bean nhận được một đối tượng hạ tầng từ container trong quá trình khởi tạo. Hai interface quan trọng là `EnvironmentAware` và `ApplicationContextAware`:

- `EnvironmentAware` cung cấp `Environment` để đọc property sources và profiles.
- `ApplicationContextAware` cung cấp `ApplicationContext` đang quản lý bean, cho phép truy cập các chức năng rộng hơn của container như bean lookup, resource loading, event publishing và message resolution.

Các interface này hữu ích cho một số thành phần tích hợp framework hoặc hạ tầng. Tuy nhiên, chúng làm class phụ thuộc trực tiếp vào Spring container. Với service nghiệp vụ thông thường, constructor injection, `@Value` hoặc `@ConfigurationProperties` thường diễn đạt dependency rõ ràng và dễ kiểm thử hơn.

Bài học trình bày Aware callback được gọi khi nào, cách dùng hai interface, trường hợp phù hợp, giới hạn về lifecycle và test, cùng các abstraction hẹp hơn để tránh biến `ApplicationContext` thành service locator toàn cục.

## 1. Aware callback là gì?

Một bean có thể triển khai interface kết thúc bằng hậu tố `Aware` để nhận một đối tượng do container cung cấp. Khi Spring tạo bean, nó nhận diện các interface Aware được hỗ trợ và gọi callback tương ứng trong quá trình chuẩn bị bean.

Ví dụ:

~~~java
public class ExampleBean implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }
}
~~~

Spring gọi `setEnvironment` và truyền `Environment` của context đang quản lý bean. Lập trình viên không tự gọi callback này trong luồng sử dụng thông thường.

Aware callback là một phần của **lifecycle contract**. Nó không phải cơ chế component scanning, không tự đăng ký bean và cũng không thay thế dependency injection. Class phải được Spring tạo và quản lý thì callback mới được thực hiện.

### 1.1. Một số Aware interface thường gặp

| Interface | Đối tượng bean nhận được | Mục đích |
| --- | --- | --- |
| `BeanNameAware` | Tên bean trong container | Biết bean name đang được đăng ký |
| `BeanClassLoaderAware` | ClassLoader | Nạp class/resource theo class loader |
| `BeanFactoryAware` | BeanFactory | Truy cập factory quản lý bean |
| `EnvironmentAware` | Environment | Đọc property và profile |
| `EmbeddedValueResolverAware` | StringValueResolver | Resolve placeholder/expression theo resolver được cấu hình |
| `ResourceLoaderAware` | ResourceLoader | Tải resource theo abstraction của Spring |
| `ApplicationEventPublisherAware` | ApplicationEventPublisher | Phát application event |
| `MessageSourceAware` | MessageSource | Tra cứu message đã cấu hình |
| `ApplicationContextAware` | ApplicationContext | Truy cập application context hiện tại |

Không phải bean nào cũng nên triển khai tất cả interface này. Hãy nhận đúng abstraction nhỏ nhất mà thành phần thực sự cần.

### 1.2. Aware callback khác constructor injection

Constructor injection truyền dependency như một phần hợp đồng khởi tạo:

~~~java
@Service
public class GreetingService {
    private final Environment environment;

    public GreetingService(Environment environment) {
        this.environment = environment;
    }
}
~~~

Aware callback truyền dependency sau khi object đã được tạo:

~~~java
@Component
public class GreetingEnvironment implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }
}
~~~

Constructor injection làm dependency bắt buộc hiển thị ngay trong constructor và cho phép dùng field `final`. Aware callback là hook do container gọi trong lifecycle; field thường không thể là `final` vì được gán sau constructor. Nếu class cần `Environment` để thực hiện nghiệp vụ, truyền nó qua constructor thường rõ ràng hơn.

## 2. Environment là gì?

`Environment` là abstraction của Spring để truy cập các đặc tính môi trường của ứng dụng, chủ yếu gồm:

- `PropertySources`: nguồn property như system properties, environment variables, file cấu hình và nguồn do ứng dụng thêm vào.
- `Profiles`: tập profile đang active hoặc default, dùng để chọn cấu hình/bean phù hợp.
- API đọc property theo tên, kiểu dữ liệu và giá trị mặc định.

Trong Spring Boot, `Environment` được cấu hình từ các nguồn như `application.properties`, `application.yml`, profile-specific configuration, environment variables, Java system properties và các nguồn khác theo thứ tự ưu tiên.

~~~mermaid
flowchart TD
    A["Environment"] --> B["PropertySources"]
    B --> C["application.yml / properties"]
    B --> D["Profile-specific config"]
    B --> E["Environment variables"]
    B --> F["JVM system properties"]
    B --> G["Property sources bổ sung"]
    A --> H["Active profiles"]
    A --> I["Default profiles"]
~~~

Thứ tự ưu tiên giữa property sources ảnh hưởng đến giá trị cuối cùng khi nhiều nguồn cùng khai báo một key. Không nên giả định file cấu hình luôn thắng environment variable hoặc system property; hãy kiểm tra quy tắc cấu hình của Spring Boot và cách nguồn được thêm vào ứng dụng.

## 3. EnvironmentAware và cách triển khai

`EnvironmentAware` thuộc package `org.springframework.context` và định nghĩa callback:

~~~java
public interface EnvironmentAware extends Aware {
    void setEnvironment(Environment environment);
}
~~~

Một bean triển khai interface này sẽ nhận `Environment` từ Spring trong giai đoạn khởi tạo.

### 3.1. Đọc property

~~~java
package com.example.infrastructure;

import org.springframework.context.EnvironmentAware;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RuntimeEnvironmentInfo implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public String applicationRegion() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

Cấu hình:

~~~yaml
app:
  region: apac
~~~

Khi được gọi, `applicationRegion()` trả về property `app.region` nếu tồn tại; nếu không, nó trả về `local`.

Trong ví dụ này, field không thể là `final` vì callback gán nó sau constructor. Đây là một khác biệt thực tế so với constructor injection.

### 3.2. Đọc property có kiểu dữ liệu

`Environment` hỗ trợ chuyển đổi kiểu thông qua overload `getProperty`:

~~~java
String region = environment.getProperty("app.region");

Integer maxAttempts = environment.getProperty(
        "app.retry.max-attempts",
        Integer.class,
        3
);

Boolean enabled = environment.getProperty(
        "feature.audit.enabled",
        Boolean.class,
        false
);
~~~

Có thể dùng `getRequiredProperty` khi property là bắt buộc:

~~~java
String apiEndpoint =
        environment.getRequiredProperty("partner.api.endpoint");
~~~

Nếu property không tồn tại, `getRequiredProperty` ném lỗi thay vì trả null. Đây là cách fail fast khi thiếu cấu hình bắt buộc.

Không nên đưa secret hoặc credential vào log khi đọc property. Việc có thể truy cập giá trị không có nghĩa giá trị đó được phép ghi ra console hay response.

### 3.3. Kiểm tra profile

`Environment` cho phép kiểm tra profile đang active:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

public boolean isProduction(Environment environment) {
    return environment.acceptsProfiles(Profiles.of("prod"));
}
~~~

Hoặc đọc danh sách profile:

~~~java
String[] activeProfiles = environment.getActiveProfiles();
String[] defaultProfiles = environment.getDefaultProfiles();
~~~

Một số điểm cần nhớ:

- Profile là cơ chế chọn cấu hình hoặc bean, không phải hệ thống phân quyền.
- Không dùng profile `prod` để thay thế authorization hoặc security check.
- Nếu không có profile active, Spring có thể sử dụng default profile theo cấu hình.
- Một bean có thể được đăng ký có điều kiện bằng `@Profile` thay vì tự kiểm tra profile trong từng method.

Ví dụ:

~~~java
@Configuration
@Profile("prod")
public class ProductionIntegrationConfiguration {
    // Bean chỉ được đăng ký khi profile prod phù hợp.
}
~~~

Khi mục tiêu là chọn implementation theo môi trường, `@Profile` thường diễn đạt ý định rõ hơn việc service tự hỏi `Environment` trong mỗi lần xử lý.

## 4. ApplicationContextAware là gì?

`ApplicationContextAware` thuộc package `org.springframework.context`. Nó cho phép bean nhận context đang quản lý nó:

~~~java
public interface ApplicationContextAware extends Aware {
    void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException;
}
~~~

Ví dụ:

~~~java
package com.example.infrastructure;

import org.springframework.beans.BeansException;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ApplicationContextAware;
import org.springframework.stereotype.Component;

@Component
public class ContextInformation implements ApplicationContextAware {
    private ApplicationContext applicationContext;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext)
            throws BeansException {
        this.applicationContext = applicationContext;
    }

    public String contextDisplayName() {
        return applicationContext.getDisplayName();
    }
}
~~~

`ApplicationContext` là abstraction rộng hơn `Environment`. Ngoài property và profile, context còn cung cấp khả năng truy cập bean, resource, event publisher, message source và lifecycle quản lý bean.

### 4.1. Một số khả năng của ApplicationContext

| API | Mục đích |
| --- | --- |
| `getBean(...)` | Tra cứu bean theo tên hoặc kiểu |
| `getEnvironment()` | Truy cập Environment |
| `getResource(...)` | Lấy Resource theo location |
| `publishEvent(...)` | Phát application event |
| `getMessage(...)` | Tra cứu message qua MessageSource |
| `ConfigurableApplicationContext.getBeanFactory()` | Truy cập bean factory khi đang làm việc với configurable context |
| `getDisplayName()` | Lấy tên hiển thị của context |

Không phải tất cả khả năng này đều cần thiết cho một bean nghiệp vụ. Việc nhận toàn bộ context tạo ra coupling rộng hơn so với inject một dependency cụ thể.

### 4.2. Tra cứu bean bằng ApplicationContext

Ví dụ một plugin registry đơn giản:

~~~java
@Component
public class ExporterRegistry implements ApplicationContextAware {
    private ApplicationContext applicationContext;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        this.applicationContext = applicationContext;
    }

    public Exporter exporter(String beanName) {
        return applicationContext.getBean(beanName, Exporter.class);
    }
}
~~~

Đoạn mã cho thấy khả năng tra cứu bean động. Tuy nhiên, nó cũng làm `ExporterRegistry` phụ thuộc trực tiếp vào container và tên bean ở runtime. Consumer không thể biết qua constructor rằng registry có thể trả về những exporter nào, và lỗi tên bean chỉ xuất hiện khi gọi method.

Nếu tập exporter có thể biết trước, inject collection sẽ minh bạch hơn:

~~~java
@Component
public class ExporterRegistry {
    private final Map<String, Exporter> exporters;

    public ExporterRegistry(Map<String, Exporter> exporters) {
        this.exporters = Map.copyOf(exporters);
    }

    public Exporter exporter(String name) {
        Exporter exporter = exporters.get(name);
        if (exporter == null) {
            throw new IllegalArgumentException("Unknown exporter: " + name);
        }
        return exporter;
    }
}
~~~

Spring có thể inject map bean name → bean instance khi constructor yêu cầu `Map<String, Exporter>`. Cách này thể hiện dependency ngay lúc khởi tạo và không cần giữ ApplicationContext.

### 4.3. Không giữ ApplicationContext trong static field

Một anti-pattern thường gặp:

~~~java
@Component
public class SpringContextHolder implements ApplicationContextAware {
    private static ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext applicationContext) {
        SpringContextHolder.context = applicationContext;
    }

    public static <T> T getBean(Class<T> type) {
        return context.getBean(type);
    }
}
~~~

Cách này tạo một service locator toàn cục. Nó có nhiều rủi ro:

- Mọi class có thể âm thầm lấy bean mà không khai báo dependency.
- Unit test khó cô lập vì static state tồn tại giữa các test.
- Nhiều context hoặc context được đóng/mở lại có thể để lại reference cũ.
- Vòng đời bean bị che giấu sau một API static.
- Code nghiệp vụ bị phụ thuộc mạnh vào Spring và khó tái sử dụng ngoài Spring.

Chỉ nên xây cơ chế context holder khi có một nhu cầu framework/integration rất cụ thể và có chính sách quản lý lifecycle rõ ràng. Không dùng nó làm cách injection mặc định.

## 5. Khi nào callback Aware được gọi?

Aware callback diễn ra trong quá trình Spring tạo bean, sau khi instance được tạo và dependency/property đã được populate, nhưng trước các initialization callback như `@PostConstruct`.

Với một bean thông thường, trình tự khái quát:

~~~mermaid
flowchart TD
    A["Instantiate bean"] --> B["Populate properties / inject dependencies"]
    B --> C["BeanNameAware / BeanClassLoaderAware / BeanFactoryAware nếu có"]
    C --> D["ApplicationContextAwareProcessor gọi các ApplicationContext Aware callbacks"]
    D --> E["BeanPostProcessor trước initialization"]
    E --> F["@PostConstruct"]
    F --> G["InitializingBean.afterPropertiesSet()"]
    G --> H["Custom init method"]
    H --> I["BeanPostProcessor sau initialization"]
    I --> J["Bean sẵn sàng sử dụng"]
~~~

`ApplicationContextAwareProcessor` là một `BeanPostProcessor` do Spring đăng ký để xử lý các interface như `EnvironmentAware`, `ResourceLoaderAware`, `ApplicationEventPublisherAware`, `MessageSourceAware` và `ApplicationContextAware`.

Không cần tự tạo processor này trong ứng dụng thông thường. Đây là chi tiết giải thích tại sao callback được thực hiện trong lifecycle.

### 5.1. Aware callback không phải constructor

Không nên đọc field được gán trong `setEnvironment` hoặc `setApplicationContext` từ constructor của cùng bean. Tại thời điểm constructor chạy, callback chưa được thực hiện.

Nếu cần property để xác định trạng thái ban đầu của object, constructor injection hoặc configuration properties phù hợp hơn.

### 5.2. Callback chỉ được gọi cho bean do Spring quản lý

`new` object Java không kích hoạt lifecycle của Spring:

~~~java
RuntimeEnvironmentInfo info = new RuntimeEnvironmentInfo();
// Spring không gọi setEnvironment(...) cho instance này.
~~~

Nếu gọi method cần field `environment`, instance trên sẽ không có giá trị đã inject. Đây là lý do các class dùng Aware callback phải được tạo và quản lý bởi container theo cách mong đợi.

## 6. EnvironmentAware hay inject Environment qua constructor?

Cả hai cách đều có thể nhận `Environment`. Lựa chọn phụ thuộc vai trò của class.

### 6.1. Constructor injection

~~~java
@Service
public class FeaturePolicy {
    private final Environment environment;

    public FeaturePolicy(Environment environment) {
        this.environment = environment;
    }

    public boolean auditEnabled() {
        return environment.getProperty(
                "feature.audit.enabled",
                Boolean.class,
                false
        );
    }
}
~~~

Ưu điểm:

- Dependency được khai báo rõ ràng.
- Field có thể là `final`.
- Unit test có thể truyền một `StandardEnvironment` hoặc mock/fake phù hợp.
- Không cần dựa vào callback lifecycle để object hoàn chỉnh.

Nếu service chỉ cần một vài property, `@ConfigurationProperties` hoặc `@Value` còn hẹp và rõ hơn.

### 6.2. EnvironmentAware

~~~java
@Component
public class EnvironmentDiagnostics implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public String activeProfileSummary() {
        return String.join(",", environment.getActiveProfiles());
    }
}
~~~

Cách này có thể phù hợp với một infrastructure component được thiết kế để nhận callback chuẩn của Spring, hoặc một thành phần tích hợp phải triển khai nhiều Aware interface theo contract của framework.

Nhưng nếu đây chỉ là một service nghiệp vụ cần đọc cấu hình, constructor injection thường đơn giản hơn.

### 6.3. Dùng @Value cho một giá trị đơn

Nếu class chỉ cần một property, không nhất thiết inject toàn bộ Environment:

~~~java
@Component
public class EmailPolicy {
    private final String senderAddress;

    public EmailPolicy(
            @Value("${mail.sender-address}") String senderAddress) {
        this.senderAddress = senderAddress;
    }
}
~~~

`@Value` có thể resolve property placeholder và chuyển đổi kiểu theo conversion service phù hợp. Với property bắt buộc, placeholder không có default có thể làm context khởi động thất bại nếu thiếu giá trị.

Dùng `@Value` cho vài giá trị đơn giản; tránh rải quá nhiều property rời rạc trong constructor của một class lớn.

### 6.4. Dùng @ConfigurationProperties cho nhóm cấu hình

Khi có nhiều property liên quan, gom chúng thành một kiểu cấu hình:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "partner.client")
public record PartnerClientProperties(
        String baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {
    public PartnerClientProperties {
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalArgumentException("baseUrl is required");
        }
        if (connectTimeout == null || connectTimeout.isNegative()) {
            throw new IllegalArgumentException("connectTimeout must be non-negative");
        }
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }
    }
}
~~~

YAML:

~~~yaml
partner:
  client:
    base-url: https://api.example.test
    connect-timeout: 2s
    max-attempts: 3
~~~

Đăng ký properties bằng một trong các cách phù hợp, ví dụ:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {
}
~~~

Hoặc `@EnableConfigurationProperties(PartnerClientProperties.class)` trên một configuration class.

Consumer chỉ cần nhận object cấu hình:

~~~java
@Service
public class PartnerClient {
    private final PartnerClientProperties properties;

    public PartnerClient(PartnerClientProperties properties) {
        this.properties = properties;
    }
}
~~~

Đây thường là lựa chọn tốt cho cấu hình có cấu trúc vì kiểu dữ liệu, validation và quan hệ giữa các thuộc tính được thể hiện rõ. `EnvironmentAware` vẫn có chỗ dùng khi một thành phần thực sự cần thao tác với Environment abstraction tổng quát, thay vì chỉ cần một nhóm cấu hình cố định.

## 7. ApplicationContextAware hay inject abstraction hẹp hơn?

`ApplicationContext` cung cấp nhiều chức năng, nhưng hầu hết class chỉ cần một phần nhỏ. Spring cho phép inject trực tiếp các abstraction tương ứng.

| Nhu cầu | Dependency hẹp hơn nên cân nhắc |
| --- | --- |
| Đọc property và profile | `Environment` hoặc configuration properties |
| Phát application event | `ApplicationEventPublisher` |
| Tải resource | `ResourceLoader` hoặc `Resource` được inject |
| Tra cứu bean tùy chọn/lazy | `ObjectProvider<T>` |
| Dùng nhiều implementation cùng interface | `List<T>`, `Set<T>` hoặc `Map<String, T>` |
| Tra cứu message | `MessageSource` |
| Thao tác ở mức bean factory | `BeanFactory` nếu thật sự cần API factory |
| Truy cập toàn bộ container | `ApplicationContext` chỉ khi trách nhiệm cần đầy đủ context |

### 7.1. Thay ApplicationContextAware bằng ApplicationEventPublisher

Nếu class chỉ cần phát event:

~~~java
@Component
public class OrderEventPublisher {
    private final ApplicationEventPublisher publisher;

    public OrderEventPublisher(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void publishOrderCreated(String orderId) {
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

Event type:

~~~java
public record OrderCreatedEvent(String orderId) {}
~~~

Consumer:

~~~java
@Component
public class OrderAuditListener {
    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        // Ghi audit theo event.
    }
}
~~~

Class publisher không cần biết toàn bộ ApplicationContext. Nó chỉ cần abstraction phát event.

Lưu ý: publish event đồng bộ mặc định có thể khiến listener chạy trong cùng call flow. Nếu cần async listener, transaction-bound event hoặc bảo đảm delivery bền vững, phải thiết kế cơ chế phù hợp; application event trong bộ nhớ không thay thế message broker.

### 7.2. Thay ApplicationContextAware bằng ObjectProvider

Nếu class cần bean có thể không tồn tại hoặc muốn trì hoãn resolve:

~~~java
@Service
public class OptionalSearchService {
    private final ObjectProvider<SearchExtension> extensionProvider;

    public OptionalSearchService(
            ObjectProvider<SearchExtension> extensionProvider) {
        this.extensionProvider = extensionProvider;
    }

    public void search(String query) {
        SearchExtension extension = extensionProvider.getIfAvailable();
        if (extension != null) {
            extension.enrich(query);
        }
    }
}
~~~

`ObjectProvider` làm rõ rằng chỉ một loại dependency được tra cứu động. Nó không buộc service nhận toàn bộ context.

Nếu cần tất cả extension, inject collection ngay từ đầu. Nếu cần chọn theo một tiêu chí runtime, xây dựng registry/factory có API rõ ràng thay vì cho business service gọi `getBean` tùy ý.

### 7.3. Thay ApplicationContextAware bằng ResourceLoader

Nếu mục đích là đọc resource:

~~~java
@Component
public class TemplateCatalog {
    private final ResourceLoader resourceLoader;

    public TemplateCatalog(ResourceLoader resourceLoader) {
        this.resourceLoader = resourceLoader;
    }

    public Resource template(String location) {
        return resourceLoader.getResource(location);
    }
}
~~~

Consumer chỉ phụ thuộc vào chức năng tải resource. Có thể dùng location dạng classpath hoặc URL theo cơ chế ResourceLoader và môi trường ứng dụng. Hãy xử lý việc resource không tồn tại hoặc lỗi đọc một cách rõ ràng.

## 8. Giới hạn và rủi ro khi phụ thuộc ApplicationContext

`ApplicationContextAware` có thể hữu ích, nhưng làm class phụ thuộc trực tiếp vào container.

### 8.1. Che giấu dependency

~~~java
@Service
public class CheckoutService implements ApplicationContextAware {
    private ApplicationContext context;

    @Override
    public void setApplicationContext(ApplicationContext context) {
        this.context = context;
    }

    public void checkout(String orderId) {
        PaymentGateway gateway =
                context.getBean(PaymentGateway.class);
        gateway.charge(orderId);
    }
}
~~~

Nhìn vào constructor, người đọc không biết `CheckoutService` cần `PaymentGateway`. Dependency chỉ lộ ra khi method chạy. Điều này khiến việc hiểu bean graph, viết test và refactor khó hơn.

Cách rõ ràng hơn:

~~~java
@Service
public class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void checkout(String orderId) {
        gateway.charge(orderId);
    }
}
~~~

### 8.2. Tăng coupling với Spring

Class triển khai `ApplicationContextAware` không còn là một service Java độc lập. Nó phụ thuộc trực tiếp vào Spring API và lifecycle. Nếu muốn dùng logic đó trong một ứng dụng khác, test thuần hoặc một module domain không dùng Spring, phải mang theo container abstraction hoặc tạo adapter.

Một nguyên tắc hữu ích là giữ domain/application logic phụ thuộc vào interface và kiểu Java thuần; để adapter/configuration ở ranh giới Spring đảm nhiệm việc kết nối container.

### 8.3. Có thể tạo vòng phụ thuộc khó thấy

Nếu bean A lấy B bằng `getBean` trong callback hoặc trong `@PostConstruct`, còn B lại phụ thuộc A, vòng phụ thuộc có thể bị che giấu sau lookup động. Lỗi xuất hiện ở thời điểm runtime và khó đọc hơn constructor cycle.

Constructor injection làm dependency graph rõ ngay lúc khởi tạo. Nếu có vòng, hãy xem lại trách nhiệm, trích xuất collaborator hoặc dùng event/port phù hợp thay vì gọi `getBean` để né phát hiện vòng.

### 8.4. Không dùng ApplicationContext để điều khiển scope thủ công

Gọi `getBean` lặp đi lặp lại để cố quản lý vòng đời request/session hoặc tạo instance mới có thể bỏ qua scope contract. Với prototype, scoped bean hoặc dependency lazy, hãy dùng đúng cơ chế như `ObjectProvider`, scoped proxy hoặc factory abstraction.

### 8.5. Nhiều ApplicationContext

Một ứng dụng có thể có parent và child context, hoặc nhiều context được tạo trong test/embedded setup. `ApplicationContextAware` nhận context đang quản lý bean đó, không phải một context toàn cục duy nhất.

Nếu code lưu context vào static field, context mới có thể ghi đè context cũ hoặc một reference đã đóng vẫn tồn tại. Đừng giả định `getBean` luôn truy cập cùng một tập bean trong mọi context.

## 9. Aware callback và thứ tự lifecycle

Aware callback được thực hiện trước initialization callback. Khi `@PostConstruct` chạy, bean đã nhận các Aware dependency mà Spring hỗ trợ.

~~~java
@Component
public class EnvironmentStartupReporter implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @PostConstruct
    public void report() {
        String[] profiles = environment.getActiveProfiles();
        // Có thể đọc environment tại đây.
    }
}
~~~

`@PostConstruct` diễn ra sau callback `setEnvironment` trong lifecycle thông thường. Nhưng constructor chạy trước đó, nên không truy cập field này trong constructor.

### 9.1. Không dùng callback để chạy tác vụ startup dài

Không nên biến `setApplicationContext` hoặc `setEnvironment` thành nơi chạy hàng loạt truy vấn database, gọi API ngoài hoặc khởi chạy luồng nền. Aware callback nên nhận và lưu abstraction mà bean cần, còn công việc khởi động nên dùng lifecycle mechanism phù hợp và có quản lý lỗi/timeout.

Các lựa chọn gồm `ApplicationRunner`, `CommandLineRunner`, `ApplicationReadyEvent` hoặc `SmartLifecycle` tùy yêu cầu. Không dùng Aware callback chỉ vì nó được gọi sớm.

### 9.2. Aware callback không bảo đảm mọi dependency đã sẵn sàng về nghiệp vụ

Spring đảm bảo các dependency cần thiết cho việc tạo bean được resolve theo lifecycle của container. Nhưng điều đó không có nghĩa database ngoài đã sẵn sàng, broker đã nhận kết nối, schema migration đã hoàn tất hoặc remote service đã healthy. Các điều kiện đó cần health check, retry, readiness hoặc orchestration riêng.

## 10. Kiểm thử EnvironmentAware

Một class triển khai `EnvironmentAware` có thể kiểm thử bằng cách tạo context nhỏ, để Spring gọi callback, hoặc gọi callback trực tiếp trong unit test nếu chỉ muốn kiểm tra logic xử lý environment.

Ví dụ class:

~~~java
@Component
public class RegionResolver implements EnvironmentAware {
    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    public String resolve() {
        return environment.getProperty("app.region", "local");
    }
}
~~~

Unit test trực tiếp callback:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.mock.env.MockEnvironment;

class RegionResolverTest {
    @Test
    void returnsConfiguredRegion() {
        MockEnvironment environment = new MockEnvironment()
                .withProperty("app.region", "apac");

        RegionResolver resolver = new RegionResolver();
        resolver.setEnvironment(environment);

        assertEquals("apac", resolver.resolve());
    }

    @Test
    void usesDefaultWhenPropertyIsMissing() {
        RegionResolver resolver = new RegionResolver();
        resolver.setEnvironment(new MockEnvironment());

        assertEquals("local", resolver.resolve());
    }
}
~~~

Test này gọi callback trực tiếp để kiểm tra logic đọc property; nó không kiểm tra Spring có tự gọi Aware callback khi tạo bean hay không.

Nếu cần kiểm tra integration với container, có thể dùng `ApplicationContextRunner` hoặc `AnnotationConfigApplicationContext` để đăng ký class và lấy bean sau khi refresh context.

### 10.1. Kiểm thử với StandardEnvironment

Có thể tạo `StandardEnvironment` và thêm property source:

~~~java
var environment = new StandardEnvironment();
environment.getPropertySources().addFirst(
        new MapPropertySource(
                "test",
                Map.of("app.region", "emea")
        )
);
~~~

Sau đó truyền environment vào bean hoặc đăng ký environment phù hợp cho context test. `MockEnvironment` của Spring Test thường tiện hơn cho unit test property đơn giản.

## 11. Kiểm thử ApplicationContextAware

Nếu một class thực sự cần context, test có thể tạo context nhỏ:

~~~java
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

class ContextInformationTest {
    @Test
    void receivesOwningApplicationContext() {
        try (var context =
                new AnnotationConfigApplicationContext(ContextInformation.class)) {
            ContextInformation bean = context.getBean(ContextInformation.class);
            assertNotNull(bean.contextDisplayName());
        }
    }
}
~~~

Ví dụ cần class `ContextInformation` được khai báo như phần trước. Khi context refresh, Spring tạo bean và gọi `setApplicationContext`. Test lấy bean sau khi context đã khởi tạo.

Test chỉ chứng minh callback được gọi trong context đó. Nó không chứng minh thiết kế dùng ApplicationContext là lựa chọn tốt nhất cho logic nghiệp vụ. Nếu mục tiêu thực tế chỉ là phát event hoặc tra cứu một extension, hãy test abstraction hẹp hơn.

## 12. Những Aware interface hẹp hơn nên biết

Spring cung cấp nhiều interface Aware để bean nhận đúng capability mà nó cần. Việc dùng interface hẹp giúp giảm coupling.

### 12.1. ApplicationEventPublisherAware

Dùng khi một thành phần framework cần callback để nhận publisher:

~~~java
@Component
public class AuditEventSource implements ApplicationEventPublisherAware {
    private ApplicationEventPublisher publisher;

    @Override
    public void setApplicationEventPublisher(
            ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

Trong ứng dụng thông thường, constructor injection `ApplicationEventPublisher` thường rõ hơn:

~~~java
@Component
public class AuditEventSource {
    private final ApplicationEventPublisher publisher;

    public AuditEventSource(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }
}
~~~

### 12.2. MessageSourceAware

Dùng khi một thành phần cần tra cứu message đã cấu hình. Nếu chỉ cần message source, không cần toàn bộ context.

### 12.3. ResourceLoaderAware

Dùng khi thành phần tích hợp framework cần nhận resource loader qua callback. Nếu code ứng dụng thông thường cần tải resource, constructor injection `ResourceLoader` dễ kiểm thử hơn.

### 12.4. BeanFactoryAware

`BeanFactoryAware` cung cấp bean factory thấp hơn `ApplicationContext`. Nó vẫn là phụ thuộc container và thường chỉ phù hợp với infrastructure component, factory hoặc extension point thực sự cần API bean factory.

Không nên đổi `ApplicationContextAware` sang `BeanFactoryAware` chỉ để tránh tên ApplicationContext mà vẫn giữ service locator pattern. Hãy inject đúng collaborator cần thiết.

## 13. Phân biệt Aware interface với annotation cấu hình

Một số annotation cũng cho phép class hoặc method sử dụng cấu hình Spring, nhưng ý nghĩa khác với Aware callback.

| Cơ chế | Vai trò |
| --- | --- |
| `EnvironmentAware` | Nhận Environment qua lifecycle callback |
| Constructor injection `Environment` | Nhận Environment như dependency khởi tạo |
| `@Value` | Bind một giá trị property/expression vào field, parameter hoặc method |
| `@ConfigurationProperties` | Bind một nhóm property có cấu trúc vào object |
| `@Profile` | Điều kiện đăng ký bean theo profile |
| `@ConditionalOnProperty` | Điều kiện auto-configuration theo property |
| `ApplicationContextAware` | Nhận toàn bộ context qua callback |
| `@Import` / `@Bean` | Đăng ký và lắp ghép bean definition |

Nếu chỉ muốn chọn bean theo profile, không cần inject `Environment` rồi tự viết if/else ở mỗi nơi. Có thể dùng `@Profile` hoặc condition phù hợp ngay tại cấu hình.

Ví dụ:

~~~java
@Configuration
@Profile("dev")
class DevelopmentMailConfiguration {
    @Bean
    MailSender mailSender() {
        return new ConsoleMailSender();
    }
}

@Configuration
@Profile("prod")
class ProductionMailConfiguration {
    @Bean
    MailSender mailSender(ProductionMailClient client) {
        return new ProductionMailSender(client);
    }
}
~~~

Mỗi cấu hình chịu trách nhiệm đăng ký implementation phù hợp với môi trường. Service chỉ cần inject `MailSender` mà không biết profile đang active.

## 14. Các lỗi và hiểu lầm thường gặp

| Triệu chứng hoặc hiểu lầm | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Field Environment null | Object được tạo bằng `new` hoặc callback chưa được Spring gọi | Để Spring quản lý bean hoặc dùng constructor injection |
| Field ApplicationContext null | Bean không được tạo bởi context hoặc code truy cập quá sớm | Kiểm tra lifecycle và cách tạo object |
| `ApplicationContextAware` được dùng để lấy mọi dependency | Service locator che giấu dependency | Inject collaborator qua constructor |
| Không đọc được property | Key sai, property source chưa nạp hoặc profile khác | Kiểm tra Environment, profile và nguồn cấu hình |
| Property trả về null | Dùng `getProperty` không có default cho key không tồn tại | Dùng default hoặc `getRequiredProperty` nếu bắt buộc |
| Gọi getBean thất bại | Bean chưa đăng ký, sai tên hoặc sai kiểu | Kiểm tra bean definition, scope và qualifier |
| Test phụ thuộc thứ tự | Static context hoặc shared mutable state | Bỏ global holder, tạo context riêng và đóng đúng cách |
| Aware callback chạy nhưng remote service chưa sẵn sàng | Callback chỉ phản ánh lifecycle container | Dùng health check/retry/readiness |
| Đọc property trong constructor từ field Aware | Callback xảy ra sau constructor | Dùng constructor injection hoặc đọc trong lifecycle callback phù hợp |
| Bean phụ thuộc vào context cụ thể | Coupling container làm giảm khả năng tái sử dụng | Inject abstraction hẹp hơn |

### 14.1. Không dùng Environment làm nơi lưu trạng thái runtime tùy tiện

`Environment` chủ yếu biểu diễn cấu hình và profile. Không nên thêm property source mutable để lưu dữ liệu request, user state hoặc trạng thái nghiệp vụ thay đổi liên tục. Những dữ liệu đó thuộc domain object, database, cache hoặc context có lifecycle phù hợp.

### 14.2. Không coi profile là bảo mật

Profile giúp chọn bean/cấu hình theo môi trường, ví dụ dev/test/prod. Nó không xác thực người dùng và không kiểm soát quyền truy cập endpoint. Security phải dùng authentication, authorization và secret management thích hợp.

### 14.3. Không lạm dụng ApplicationContextAware trong domain

Nếu một class nghiệp vụ nhận toàn bộ ApplicationContext, nó có thể tra cứu bất kỳ bean nào trong tương lai. Điều này khiến dependency graph không còn phản ánh đầy đủ trong constructor và tạo ranh giới khó kiểm soát. Hãy giữ container ở tầng composition/infrastructure khi có thể.

## 15. Hướng dẫn chọn cơ chế

Dựa vào nhu cầu thực tế:

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Đọc một property đơn | `@Value` hoặc constructor parameter |
| Đọc nhóm cấu hình có cấu trúc | `@ConfigurationProperties` |
| Kiểm tra profile để đăng ký bean | `@Profile` hoặc conditional configuration |
| Một infrastructure component cần callback Environment | `EnvironmentAware` |
| Phát event | `ApplicationEventPublisher` |
| Tra cứu bean optional/lazy | `ObjectProvider<T>` |
| Cần tất cả implementation | Inject `List<T>` / `Map<String, T>` |
| Tải resource | `ResourceLoader` |
| Framework extension cần owning context | `ApplicationContextAware` |
| Business service cần gọi collaborator | Constructor injection |

Một nguyên tắc thực tế: **chọn dependency nhỏ nhất đủ đáp ứng trách nhiệm của class**. Chỉ nhận toàn bộ ApplicationContext khi class thực sự cần chức năng của context và bản thân nó thuộc tầng tích hợp với container.

## 16. Bài tập thực hành

### Bài tập 1 — Đọc profile bằng EnvironmentAware

Tạo bean `EnvironmentReporter` triển khai `EnvironmentAware`. Cấu hình hai profile `dev` và `prod`. Viết method trả về danh sách active profile và kiểm tra với hai cấu hình khác nhau.

### Bài tập 2 — Chuyển từ Aware sang constructor injection

Cho class `FeaturePolicy` triển khai `EnvironmentAware` chỉ để đọc `feature.audit.enabled`. Viết lại class dùng constructor injection `Environment` hoặc `@ConfigurationProperties`. So sánh khả năng test và mức độ phụ thuộc container.

### Bài tập 3 — Thay service locator

Cho class dùng `ApplicationContextAware` và `getBean("csvExporter")` để lấy exporter. Thay bằng constructor injection `Map<String, Exporter>` hoặc registry có API rõ ràng. Viết unit test không cần Spring.

### Bài tập 4 — Chọn abstraction hẹp

Một component triển khai `ApplicationContextAware` nhưng chỉ gọi `publishEvent`. Hãy thay bằng `ApplicationEventPublisher` qua constructor. Giải thích vì sao dependency mới thể hiện đúng trách nhiệm.

### Bài tập 5 — Kiểm thử lifecycle callback

Viết một context test để xác nhận Spring gọi `setEnvironment` trước `@PostConstruct`. Sau đó tạo cùng class bằng `new` và giải thích vì sao callback không tự chạy.

## 17. Ghi nhớ

`EnvironmentAware` và `ApplicationContextAware` là các lifecycle callback cho phép bean nhận abstraction từ Spring container. `EnvironmentAware` cung cấp môi trường cấu hình và profile; `ApplicationContextAware` cung cấp context rộng hơn với khả năng truy cập bean, resource, event và message source.

Chúng chỉ được Spring gọi khi bean thực sự được container quản lý. Callback diễn ra sau khi instance được tạo và dependency/property được populate, trước các initialization callback như `@PostConstruct`. Vì vậy không truy cập field Aware trong constructor và không mong object được tạo bằng `new` tự nhận callback.

Với service nghiệp vụ, constructor injection thường rõ ràng và dễ test hơn. Dùng `@Value` cho property đơn, `@ConfigurationProperties` cho nhóm cấu hình, `ApplicationEventPublisher` để phát event, `ResourceLoader` để tải resource hoặc `ObjectProvider` cho lookup có chủ đích. Giữ `ApplicationContextAware` cho infrastructure component thực sự cần owning context; tránh biến nó thành service locator hoặc static global context.
