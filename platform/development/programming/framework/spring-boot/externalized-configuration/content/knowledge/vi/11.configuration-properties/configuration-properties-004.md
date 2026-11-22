# Đăng ký tường minh bằng @EnableConfigurationProperties

Trong Spring Boot, annotation `@ConfigurationProperties` mô tả cách **liên kết một nhóm externalized configuration** với một kiểu Java. Tuy nhiên, chỉ gắn `@ConfigurationProperties` lên một class **không mặc nhiên bảo đảm class đó đã được đăng ký thành bean** trong ApplicationContext. Ứng dụng cần một cơ chế nhận diện và đăng ký kiểu cấu hình, ví dụ `@ConfigurationPropertiesScan`, một bean được tạo theo cách phù hợp, hoặc **`@EnableConfigurationProperties`**.

`@EnableConfigurationProperties` là lựa chọn **đăng ký tường minh**: người phát triển nêu chính xác các lớp `@ConfigurationProperties` mà một configuration class muốn đưa vào Spring container. Cách này đặc biệt phù hợp với module hạ tầng, auto-configuration, thư viện tích hợp, cấu hình ít lớp hoặc những nơi không muốn quét rộng một package.

Bài học trình bày vòng đời từ file cấu hình đến bean, cú pháp đăng ký một hoặc nhiều lớp, constructor binding với `record`, validation, cách sử dụng trong module, so sánh với scanning và xử lý những lỗi thường gặp.

## 1. Vấn đề: khai báo cấu hình không đồng nghĩa đăng ký bean

Xét `application.yml`:

~~~yaml
app:
  client:
    base-url: "https://api.example.invalid"
    connect-timeout: 2s
    max-attempts: 3
~~~

Ta định nghĩa một kiểu có cấu trúc rõ ràng:

~~~java
package example.client.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {}
~~~

Annotation `@ConfigurationProperties(prefix = "app.client")` khai báo: các property bên dưới prefix `app.client` có thể được bind vào `ClientProperties`. Ví dụ `base-url` ánh xạ vào `baseUrl`, `connect-timeout` vào `connectTimeout`.

Nhưng class `ClientProperties` chưa có `@Component`, chưa được một bean factory trả về và cũng chưa được một cơ chế configuration-properties registration khai báo. Nếu chỉ dừng ở đoạn code trên rồi inject:

~~~java
import org.springframework.stereotype.Service;

@Service
class ClientService {

    ClientService(ClientProperties properties) {
        // Cần một ClientProperties bean đã được đăng ký.
    }
}
~~~

Spring có thể báo thiếu bean kiểu `ClientProperties` khi khởi tạo `ClientService`. Đây là **lỗi đăng ký bean**, không phải tự động là lỗi YAML hay binding.

Cách đăng ký tường minh:

~~~java
package example.client.config;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
public class ClientConfiguration {
}
~~~

Khi `ClientConfiguration` thực sự được đưa vào ApplicationContext, Spring Boot sẽ đăng ký `ClientProperties` như một configuration-properties bean và thực hiện binding theo các nguồn property hiện có.

**Ý nghĩa cần nhớ:** `@ConfigurationProperties` mô tả **kiểu và prefix**; `@EnableConfigurationProperties(ClientProperties.class)` nói rõ **hãy đăng ký kiểu đó để Spring quản lý và bind**.

## 2. @EnableConfigurationProperties hoạt động như thế nào?

Một quy trình điển hình:

~~~text
application.yml / application.properties
biến môi trường / command line / Config Data imports
                    |
                    v
              Environment
       các PropertySource theo độ ưu tiên
                    |
                    v
   @Configuration được nạp vào context
   @EnableConfigurationProperties(
       ClientProperties.class
   )
                    |
                    v
     Đăng ký ClientProperties bean
                    |
                    v
            Spring Boot Binder
   - tìm các key dưới prefix app.client
   - ánh xạ tên property vào tham số/field
   - chuyển kiểu: URI, Duration, int ...
   - áp dụng validation nếu được cấu hình
                    |
                    v
             ClientProperties
                    |
                    v
             ClientService
~~~

Có ba chuyện khác nhau trong sơ đồ:

1. **Nguồn cấu hình**: Spring Boot tìm các giá trị từ file, environment, tham số hoặc nguồn bổ sung theo quy tắc ưu tiên.
2. **Đăng ký bean**: `@EnableConfigurationProperties` chỉ định class phải có mặt trong container.
3. **Binding và validation**: Binder chuyển giá trị sang kiểu Java. Các ràng buộc có thể từ chối giá trị sai.

Một bean có thể đã được đăng ký nhưng khởi tạo thất bại vì bind lỗi. Ngược lại, một `application.yml` có thể hoàn toàn hợp lệ mà ứng dụng vẫn không có bean `ClientProperties` vì thiếu registration.

## 3. Đăng ký ngay tại lớp @SpringBootApplication

Với ứng dụng nhỏ, có thể đặt annotation trên class chính:

~~~java
package example;

import example.client.config.ClientProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class ClientDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClientDemoApplication.class, args);
    }
}
~~~

Spring Boot sẽ nhận thông tin đăng ký `ClientProperties` trong context của ứng dụng. Một service có thể inject bean này:

~~~java
package example.client;

import example.client.config.ClientProperties;
import org.springframework.stereotype.Service;

@Service
public class RemoteCatalogService {

    private final ClientProperties properties;

    public RemoteCatalogService(ClientProperties properties) {
        this.properties = properties;
    }

    public String description() {
        return "Remote endpoint: " + properties.baseUrl();
    }
}
~~~

Ví dụ `description()` chỉ minh họa việc đọc cấu hình; không nên dùng cùng cách để in các giá trị nhạy cảm như token/password ra log hoặc response.

### Vì sao có thể cần explicit registration dù class nằm ngoài package scan?

Giả sử class chính có package `example.web`, trong khi `ClientProperties` nằm ở `shared.client.config`. Quét component mặc định từ `example.web` có thể không tự tìm mọi class ở package khác.

Nếu application class đã import được kiểu `shared.client.config.ClientProperties`, việc đăng ký tường minh bằng `@EnableConfigurationProperties(ClientProperties.class)` không đòi hỏi phải quét toàn bộ package chứa properties class. Đây là ưu điểm khi ứng dụng lớn hoặc thư viện nằm trong module tách biệt.

Điều kiện là class **chứa `@EnableConfigurationProperties` phải được Spring nạp vào context**; đặt annotation trên một class cấu hình không được scan/import thì annotation đó cũng không phát huy tác dụng.

## 4. Đăng ký trong @Configuration chuyên trách

Khi ứng dụng có nhiều module, nên đặt đăng ký ngay bên cạnh cấu hình của module thay vì chất tất cả lên application class.

Ví dụ module payment:

~~~java
package example.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentModuleConfiguration {
}
~~~

Kiểu dữ liệu:

~~~java
package example.payment;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment.gateway")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        boolean enabled
) {}
~~~

Nguồn YAML:

~~~yaml
payment:
  gateway:
    enabled: true
    endpoint: "https://gateway.example.invalid"
    timeout: 5s
~~~

Một factory nhận typed properties thay vì tự đọc từng key:

~~~java
package example.payment;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
class PaymentClientConfiguration {

    @Bean
    PaymentGatewayClient paymentGatewayClient(
            PaymentProperties properties) {
        return new PaymentGatewayClient(
            properties.endpoint(),
            properties.timeout(),
            properties.enabled()
        );
    }
}
~~~

`PaymentGatewayClient` ở đây là lớp giả định có constructor nhận `URI`, `Duration` và `boolean`. Ví dụ thể hiện rằng một `@Configuration` có thể vừa **đăng ký properties type**, vừa **dùng type đó để tạo bean nghiệp vụ/hạ tầng khác**.

Trong code thực tế, chỉ cần **một vị trí chủ trì đăng ký** `PaymentProperties`. Hai class cấu hình kể trên là hai cách tổ chức minh họa; không cần đặt chúng cùng lúc nếu chỉ nhằm đăng ký cùng một kiểu.

## 5. Đăng ký nhiều lớp trong một annotation

`@EnableConfigurationProperties` nhận nhiều class:

~~~java
package example.infrastructure;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties({
    DatabasePoolProperties.class,
    StorageProperties.class,
    MonitoringProperties.class
})
public class InfrastructureConfiguration {
}
~~~

Mỗi lớp cần khai báo prefix của mình:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "infra.db-pool")
public record DatabasePoolProperties(
        int maxSize,
        Duration acquireTimeout
) {}
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "infra.storage")
public record StorageProperties(
        String bucketName,
        String region
) {}
~~~

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "infra.monitoring")
public record MonitoringProperties(
        boolean enabled,
        String serviceName
) {}
~~~

YAML tương ứng:

~~~yaml
infra:
  db-pool:
    max-size: 20
    acquire-timeout: 3s
  storage:
    bucket-name: "order-documents"
    region: "apac"
  monitoring:
    enabled: true
    service-name: "order-api"
~~~

Kiểu nào được đăng ký do danh sách trong `@EnableConfigurationProperties` quyết định; mỗi kiểu bind dữ liệu theo prefix riêng. Đây không phải một annotation “bật toàn bộ `@ConfigurationProperties` trong dự án”.

Nếu module có rất nhiều properties class và không muốn duy trì danh sách tường minh, có thể cân nhắc `@ConfigurationPropertiesScan` với phạm vi package cụ thể.

## 6. Record và constructor binding trong Spring Boot 3+

Đối với những dự án dùng Spring Boot hiện đại, `record` là cách tiện lợi để có một đối tượng cấu hình bất biến:

~~~java
package example.invoice;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "invoice")
public record InvoiceProperties(
        boolean enabled,
        Duration timeout,
        int maxItems
) {}
~~~

Đăng ký:

~~~java
package example.invoice;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InvoiceProperties.class)
class InvoiceConfiguration {
}
~~~

Trong Spring Boot 3.x, một configuration-properties class có **một constructor tham số hóa thích hợp** (bao gồm canonical constructor của record) được binder nhận diện theo cơ chế constructor binding; thông thường không cần gắn `@ConstructorBinding` lên record chỉ có một constructor. Với trường hợp có nhiều constructor, có thể cần chỉ định constructor muốn dùng theo API phù hợp với phiên bản Spring Boot.

Ưu điểm:

- Không cần setter.
- Các field nhất quán trong một đối tượng được khởi tạo.
- Code tiêu thụ có kiểu rõ ràng.
- Cấu hình dễ đưa vào test và truyền qua constructor.

Ví dụ sử dụng:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InvoiceScheduler {

    private final InvoiceProperties properties;

    public InvoiceScheduler(InvoiceProperties properties) {
        this.properties = properties;
    }

    public boolean isEnabled() {
        return properties.enabled();
    }
}
~~~

**Quan trọng:** constructor binding cho `@ConfigurationProperties` không phải constructor dependency injection thông thường. Các tham số constructor của `InvoiceProperties` ở đây là **giá trị cấu hình**, không phải Spring service bean. Do đó, không đặt `DataSource`, `Repository` hoặc `HttpClient` như tham số record cấu hình rồi kỳ vọng chúng được inject như dependency.

Đối với dự án dùng Spring Boot đời cũ, cú pháp constructor-binding và vị trí annotation `@ConstructorBinding` khác nhau; cần dùng API đúng với phiên bản đang chạy. Ví dụ trong bài hướng đến Spring Boot 3+.

## 7. Vì sao không gắn @Component lên record constructor-bound?

Một cách viết dễ gây nhầm:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        int retryCount
) {}
~~~

`@Component` yêu cầu Spring đăng ký kiểu đó qua cơ chế component thông thường. Constructor của record khi ấy có thể bị xem là constructor cần injection bean, trong khi tham số như `String` và `int` thực chất là **giá trị cấu hình**.

Đối với constructor binding, Spring Boot khuyến nghị đăng ký bằng **configuration properties scanning** hoặc **`@EnableConfigurationProperties`**, thay vì tạo bean qua `@Component`, `@Bean` hay cơ chế đăng ký Spring bean thông thường. Đây là ranh giới quan trọng giữa việc Binder tạo đối tượng cấu hình và Spring inject dependencies để tạo một component.

Cách nên dùng:

~~~java
@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String baseUrl,
        int retryCount
) {}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ClientProperties.class)
class ClientConfig {
}
~~~

Một lựa chọn khác dành cho object **mutable theo JavaBean** là đăng ký class như component và cho binder set property qua setter. Nhưng khi đã chọn record bất biến để nhận externalized configuration, nên thống nhất theo cách đăng ký dành riêng cho configuration properties.

Không nên thêm cả `@Component` **và** `@EnableConfigurationProperties(ClientProperties.class)` theo thói quen, vì có thể gây các bean/đường tạo bean trùng ý nghĩa hoặc hành vi khó đoán.

## 8. So sánh @EnableConfigurationProperties và @ConfigurationPropertiesScan

Hai cơ chế đều giúp Spring Boot quản lý các kiểu `@ConfigurationProperties`; khác nhau ở **cách chọn class**.

| Tiêu chí | `@EnableConfigurationProperties` | `@ConfigurationPropertiesScan` |
| --- | --- | --- |
| Cách chọn class | Liệt kê chính xác các class | Quét các package được chỉ định |
| Phạm vi | Các kiểu được khai báo | Các kiểu phù hợp tìm thấy trong phạm vi scan |
| Khi thêm properties class mới | Cần bổ sung vào danh sách | Có thể được tìm thấy tự động nếu đúng package |
| Tính tường minh | Cao | Phụ thuộc cấu trúc package |
| Module/thư viện | Rất phù hợp khi biết trước các types | Phù hợp khi quản lý nhiều types cùng package |
| Record/constructor binding | Hỗ trợ | Hỗ trợ |
| Phụ thuộc vào package scan | Không cần quét package chứa properties class | Cần định nghĩa phạm vi quét thích hợp |

Ví dụ **quét**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = "example.config")
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Ví dụ **tường minh**:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties({
    ApiClientProperties.class,
    BillingProperties.class
})
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Không có phương án “luôn tốt hơn”. Với vài class hoặc thư viện có boundary rõ, tường minh giúp người đọc biết module này đăng ký gì. Với một ứng dụng có nhiều class cấu hình nằm dưới package chuẩn, scan giúp giảm danh sách bảo trì thủ công.

**Tránh trùng lặp:** Nếu đã scan một properties class, thông thường không cần đăng ký lặp lại class đó qua `@EnableConfigurationProperties` ở chỗ khác. Một dự án nên có quy ước về nơi chịu trách nhiệm đăng ký để giảm ambiguity và khó kiểm chứng.

## 9. Phân biệt @EnableConfigurationProperties với @ConfigurationProperties

Hai annotation có vai trò khác nhau:

~~~java
@ConfigurationProperties(prefix = "remote.api")
public record RemoteApiProperties(
        String baseUrl,
        int maxRetries
) {}
~~~

Khai báo trên class nói rằng class có các thuộc tính được ánh xạ từ `remote.api`.

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(RemoteApiProperties.class)
class RemoteApiConfiguration {
}
~~~

Khai báo trên configuration class nói rằng Spring Boot phải **đăng ký RemoteApiProperties để sử dụng trong context này**.

Không thể thay `@ConfigurationProperties(prefix = ...)` chỉ bằng `@EnableConfigurationProperties(...)` mà không có định nghĩa prefix và cấu trúc kiểu tương ứng. Ngược lại, chỉ tạo properties class mà không có cách đăng ký thì những bean khác cũng không tự inject được nó.

Nếu cùng một class vừa là properties type vừa được đánh dấu `@Configuration`, thiết kế có thể làm lẫn **dữ liệu cấu hình** và **khai báo bean**. Thường nên tách:

~~~text
RemoteApiProperties.java     -> Chỉ typed configuration data
RemoteApiConfiguration.java  -> Đăng ký properties và các bean hạ tầng
RemoteApiClient.java         -> Dùng properties cho công việc thực tế
~~~

Sự tách biệt này giúp tránh việc cấu hình mang theo logic nghiệp vụ hoặc phụ thuộc runtime không cần thiết.

## 10. Khi nào nên đặt @EnableConfigurationProperties trong auto-configuration?

Một thư viện Spring Boot starter có thể cung cấp client và muốn người dùng cấu hình:

~~~yaml
acme:
  client:
    enabled: true
    base-url: "https://api.example.invalid"
    timeout: 3s
~~~

Thư viện định nghĩa:

~~~java
package example.autoconfig;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        boolean enabled,
        URI baseUrl,
        Duration timeout
) {}
~~~

Auto-configuration của thư viện:

~~~java
package example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@EnableConfigurationProperties(AcmeClientProperties.class)
class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
            properties.baseUrl(),
            properties.timeout()
        );
    }
}
~~~

`AcmeClient` là lớp client giả định. Code này minh họa pattern: auto-configuration **đăng ký rõ ràng properties type** của mình, sau đó tạo bean khác bằng typed properties. Thư viện không cần yêu cầu ứng dụng quét package `example.autoconfig`.

Để auto-configuration thực sự được Spring Boot nạp, thư viện phải đăng ký nó theo cơ chế của phiên bản Spring Boot tương ứng. Trong Spring Boot 3, một cách thông thường là liệt kê fully qualified name của auto-configuration class trong:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ nội dung file:

~~~text
example.autoconfig.AcmeClientAutoConfiguration
~~~

Nếu thiếu registration này, auto-configuration class có thể không được nạp dù code annotation đã viết chính xác.

### Đăng ký properties không bắt buộc tạo client bean

Trong ví dụ trên, `@EnableConfigurationProperties` đăng ký và bind `AcmeClientProperties`. Việc `AcmeClient` được tạo hay không còn phụ thuộc vào `@Bean` và các điều kiện của nó.

Nếu client chỉ nên tồn tại khi `acme.client.enabled=true`, có thể thêm:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "acme.client",
    name = "enabled",
    havingValue = "true"
)
@ConditionalOnMissingBean
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
        properties.baseUrl(),
        properties.timeout()
    );
}
~~~

Nhớ rằng **điều kiện trên client bean không tự loại bỏ việc bind/validate properties bean** đã đăng ký. Nếu validation yêu cầu endpoint dù feature tắt, cần thiết kế default và validation theo điều kiện hợp lý, hoặc đặt điều kiện ở boundary registration nếu thực sự muốn không đăng ký module trong trạng thái tắt.

## 11. Kết hợp validation để phát hiện cấu hình sai khi khởi động

Đăng ký tường minh giúp typed properties được tạo nhưng chưa thay thế **ràng buộc dữ liệu**. Ví dụ:

~~~yaml
integration:
  base-url: ""
  max-attempts: -5
~~~

Hai giá trị đều có thể đọc được, nhưng không phù hợp với một HTTP client cần URL và số lần thử lại không âm.

Có thể thêm Jakarta Bean Validation (với dependency validator phù hợp, thường là Spring Boot validation starter):

~~~java
package example.integration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "integration")
public record IntegrationProperties(
        @NotBlank String baseUrl,
        @Min(1) int maxAttempts,
        Duration timeout
) {}
~~~

Đăng ký:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(IntegrationProperties.class)
class IntegrationConfiguration {
}
~~~

Nếu `base-url` rỗng hoặc `max-attempts` bằng 0/âm, quá trình validate configuration bean có thể dừng startup với lỗi binding/validation phù hợp.

**Cần phân biệt:**

1. **Thiếu bean:** Không có cơ chế đăng ký typed properties hoặc configuration class không được nạp.
2. **Binding lỗi:** Có bean registration nhưng giá trị không thể chuyển thành kiểu Java, ví dụ `timeout: "later"` sang `Duration`.
3. **Validation lỗi:** Giá trị bind được nhưng không thỏa mãn ràng buộc, ví dụ `max-attempts: -5` với `@Min(1)`.
4. **Khởi tạo client lỗi:** Typed properties hợp lệ về dữ liệu, nhưng client không kết nối hoặc một dependency khác không được cấp.

Với cấu hình phân cấp, những nested object cần validation có thể yêu cầu `@Valid` phù hợp. Không nên giả định mọi trường con trong cấu hình phức tạp tự được kiểm tra chỉ vì root type có `@Validated`.

### Vắng property và kiểu primitive

Một record có `int maxAttempts` có thể nhận giá trị mặc định ngôn ngữ hoặc bị ảnh hưởng bởi cách Binder xây dựng object khi thiếu key. Nếu cấu hình yêu cầu người dùng phải cung cấp giá trị, nên dùng ràng buộc phù hợp; với những trường hợp cần phân biệt “không khai báo” và “khai báo 0”, kiểu `Integer` có thể biểu diễn sự vắng mặt rõ hơn `int`.

Không nên dựa vào việc `@EnableConfigurationProperties` tự xác định property nào “bắt buộc”. Annotation đó **đăng ký**, còn ý nghĩa required/default cần được thiết kế tại typed properties và validation.

## 12. Giá trị mặc định cho properties type

Trong cấu hình, một vài property có thể có mặc định an toàn:

~~~yaml
service:
  timeout: 3s
  max-retries: 2
~~~

Nhưng file cấu hình có thể không khai báo mọi key. Với constructor binding, có thể dùng default ở cấp tham số theo API Spring Boot thích hợp. Ví dụ Spring Boot 3:

~~~java
package example.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @DefaultValue("3s") Duration timeout,
        @DefaultValue("2") int maxRetries,
        @DefaultValue("false") boolean enabled
) {}
~~~

Một `ServiceProperties` được đăng ký qua `@EnableConfigurationProperties(ServiceProperties.class)` có thể nhận các default này khi các property tương ứng không xuất hiện.

Nguyên tắc:

- Dùng mặc định khi nó **có ý nghĩa và an toàn ở mọi môi trường**.
- Với secret, endpoint bắt buộc hoặc thông số an toàn quan trọng, nên validate rõ thay vì đặt giá trị giả.
- Không coi default là cách tự động bỏ qua giá trị cấu hình sai kiểu.
- Nếu môi trường có cung cấp giá trị, Binder cố chuyển giá trị đó theo kiểu đích; không thể mặc nhiên quay lại default khi nội dung không hợp lệ.

Đừng đặt tất cả default rải rác ở mỗi service. Đối tượng properties là nơi hợp lý để tập trung các quyết định này.

## 13. Nested objects và collection được đăng ký ra sao?

Giả sử cấu hình:

~~~yaml
store:
  enabled: true
  endpoints:
    - "https://one.example.invalid"
    - "https://two.example.invalid"
  retry:
    attempts: 3
    delay: 250ms
~~~

Kiểu Java:

~~~java
package example.store;

import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "store")
public record StoreProperties(
        boolean enabled,
        List<String> endpoints,
        Retry retry
) {
    public record Retry(
            int attempts,
            Duration delay
    ) {}
}
~~~

Đăng ký **root type**:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(StoreProperties.class)
class StoreConfiguration {
}
~~~

Spring Boot Binder xử lý prefix `store` và các field con theo cấu trúc. Bạn **không cần** đăng ký riêng `StoreProperties.Retry` bằng `@EnableConfigurationProperties`, vì nó chỉ là một nested value object, không phải một independent configuration-properties root bean.

Với thiết kế đúng, adapter chỉ cần inject `StoreProperties`:

~~~java
import org.springframework.stereotype.Service;

@Service
class StoreService {

    private final StoreProperties properties;

    StoreService(StoreProperties properties) {
        this.properties = properties;
    }

    int maxAttempts() {
        return properties.retry().attempts();
    }
}
~~~

Nếu `retry` có thể vắng mặt, cần thiết kế default hoặc validation cho trường hợp đó, tránh truy cập `retry().attempts()` khi nested value object null.

## 14. Đăng ký một class cấu hình từ module ngoài

Ví dụ ứng dụng `order-service` dùng một thư viện tự phát triển chứa:

~~~text
shared-client/
  src/main/java/shared/client/
    SharedClientProperties.java
    SharedClientConfiguration.java

order-service/
  src/main/java/example/order/
    OrderApplication.java
~~~

Trong thư viện:

~~~java
package shared.client;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shared.client")
public record SharedClientProperties(
        String baseUrl,
        Duration timeout
) {}
~~~

~~~java
package shared.client;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(SharedClientProperties.class)
public class SharedClientConfiguration {
}
~~~

Ứng dụng có thể import configuration class:

~~~java
package example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;
import shared.client.SharedClientConfiguration;

@SpringBootApplication
@Import(SharedClientConfiguration.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Trong trường hợp này, `@Import` đưa `SharedClientConfiguration` vào context; `@EnableConfigurationProperties` của module đăng ký kiểu `SharedClientProperties`. App không cần mở rộng component scan tới mọi package của thư viện.

Có thể chọn một phương án khác: dùng `@EnableConfigurationProperties(SharedClientProperties.class)` trực tiếp ở application class. Quan trọng là xác định **một boundary đăng ký rõ ràng**, không tạo nhiều cấu hình cạnh tranh vì thói quen.

## 15. Tại sao @EnableConfigurationProperties không giống @Import?

Cả hai đều liên quan tới registration, nhưng vai trò khác nhau.

`@Import(SomeConfiguration.class)` giúp đưa một cấu hình Spring hoặc một kiểu được hỗ trợ vào context theo cơ chế import. `@EnableConfigurationProperties(SomeProperties.class)` là cơ chế **chuyên dụng cho typed externalized configuration** và tích hợp quá trình binding.

Với properties record:

~~~java
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(
        String currency,
        int retryCount
) {}
~~~

Cách nên dùng:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(BillingProperties.class)
class BillingConfig {
}
~~~

Không nên thay bằng:

~~~java
@Configuration(proxyBeanMethods = false)
@Import(BillingProperties.class)
class BillingConfig {
}
~~~

rồi giả định constructor của `BillingProperties` sẽ tự nhận `billing.currency` và `billing.retry-count` theo constructor binding. Đăng ký bằng cơ chế Spring bean thông thường không tương đương với quá trình tạo typed configuration-properties bean.

Đối với một loại object được tạo bằng `@Bean` rồi được bind qua `@ConfigurationProperties` đặt trên phương thức, đó là **mẫu khác**, thường hữu ích khi thư viện bên thứ ba không thể chỉnh sửa class. Không nên trộn hai mẫu mà không hiểu vì sao.

## 16. Cấu hình đối tượng bên thứ ba: khi nào dùng @Bean?

Giả sử một thư viện cung cấp kiểu mutable:

~~~java
public class VendorPool {
    private int maxSize;

    public int getMaxSize() {
        return maxSize;
    }

    public void setMaxSize(int maxSize) {
        this.maxSize = maxSize;
    }
}
~~~

Bạn không sửa source của `VendorPool` để thêm `@ConfigurationProperties` được. Spring Boot cho phép gắn annotation binding lên factory method:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class VendorConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.pool")
    VendorPool vendorPool() {
        return new VendorPool();
    }
}
~~~

Với:

~~~yaml
vendor:
  pool:
    max-size: 16
~~~

Spring tạo `VendorPool` bằng factory method rồi binder áp dụng property qua các setter phù hợp.

Đây là một **lựa chọn riêng** so với:

~~~java
@EnableConfigurationProperties(VendorPool.class)
~~~

vì `VendorPool` không nhất thiết mang annotation `@ConfigurationProperties` trên class và không được thiết kế như constructor-bound typed properties của ứng dụng.

Nói gọn:

- **Class thuộc quyền sở hữu dự án**, tạo cấu hình có kiểu: `@ConfigurationProperties` trên class + `@EnableConfigurationProperties` hoặc scan.
- **Type bên thứ ba mutable**: có thể dùng `@Bean` + `@ConfigurationProperties` trên factory method để bind.

Mục tiêu là có một con đường tạo bean và binding phù hợp với loại object, không cần áp dụng mọi annotation cho mọi loại class.

## 17. Tên bean và cách injection

Khi Spring Boot đăng ký một properties class bằng phương pháp chuyên dụng như `@EnableConfigurationProperties` hoặc scanning, tên bean theo quy ước có thể dựa trên prefix và **fully qualified name** của class; ví dụ dạng:

~~~text
app.client-example.client.config.ClientProperties
~~~

Không nên lấy một bean name viết tay làm hợp đồng chính của mã ứng dụng. Đa số trường hợp, inject bằng **type**:

~~~java
@Service
class ClientManager {

    private final ClientProperties properties;

    ClientManager(ClientProperties properties) {
        this.properties = properties;
    }
}
~~~

Nếu có nhiều bean cùng một Java type trong ApplicationContext, việc inject theo type có thể ambiguous; cần điều chỉnh thiết kế, dùng qualifier phù hợp hoặc tách các configuration types theo mục đích.

Không nên tạo nhiều `ClientProperties` bean chỉ vì muốn bind hai prefix khác nhau vào cùng class rồi kỳ vọng `@EnableConfigurationProperties` tự phân biệt. Mỗi typed configuration root thường nên có type/prefix rõ ràng, đặc biệt nếu hai nhóm thuộc các module khác nhau.

Ngoài ra, properties bean không phải entity hay request-scoped object. Nó thường đại diện cho các giá trị cấu hình **của ứng dụng** được bind trong giai đoạn startup.

## 18. Lỗi thường gặp: NoSuchBeanDefinition / No qualifying bean

Giả sử service:

~~~java
@Service
class EmailService {

    EmailService(EmailProperties properties) {
    }
}
~~~

Và:

~~~java
@ConfigurationProperties(prefix = "email")
public record EmailProperties(
        String senderName
) {}
~~~

Nếu context không đăng ký `EmailProperties`, startup có thể báo thiếu bean kiểu này. Cách tìm nguyên nhân:

1. Class `EmailProperties` đã có `@ConfigurationProperties(prefix = "email")` chưa?
2. Có `@EnableConfigurationProperties(EmailProperties.class)` hoặc scan phù hợp chưa?
3. Configuration class chứa annotation có được Spring Boot nạp vào context không?
4. Có điều kiện `@Conditional...` nào khiến configuration không được kích hoạt không?
5. Code đang inject đúng kiểu `EmailProperties` hay một type cùng tên khác package?

Không nên “sửa nhanh” bằng cách thêm `@Component` vào record constructor-bound; điều đó có thể đưa vấn đề sang cơ chế Spring bean creation khác.

Một lỗi thiếu bean trong test nhưng không xảy ra khi chạy ứng dụng thường xuất phát từ test context chỉ nạp một phần configuration, thiếu lớp có `@EnableConfigurationProperties`.

## 19. Lỗi thường gặp: prefix sai hoặc giá trị không bind được

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "mail.client")
public record MailClientProperties(
        String host,
        int port
) {}
~~~

YAML:

~~~yaml
mail:
  server:
    host: "smtp.example.invalid"
    port: 2525
~~~

Đăng ký kiểu thành công nhưng prefix `mail.client` không khớp với `mail.server`. Các property `mail.client.host` và `mail.client.port` không được cung cấp từ YAML này.

Không nên kết luận `@EnableConfigurationProperties` không hoạt động. Phải kiểm tra **prefix và tên key**.

Cách sửa:

~~~yaml
mail:
  client:
    host: "smtp.example.invalid"
    port: 2525
~~~

Nếu cấu hình:

~~~yaml
mail:
  client:
    host: "smtp.example.invalid"
    port: "unknown"
~~~

thì `port` không chuyển được sang `int`. Đây là lỗi conversion/binding chứ không phải registration. Khác biệt này quan trọng vì sửa annotation sẽ không giải quyết lỗi dữ liệu.

Một số giá trị đặc biệt như duration, data size, enum và URI cần format được converter hỗ trợ. Annotation đăng ký chỉ bật quá trình binding đúng cách, không thay thế converter hoặc validation.

## 20. Lỗi thường gặp: bean trùng hoặc nhiều đường đăng ký

Một thiết kế dễ gây nhầm:

~~~java
@Component
@ConfigurationProperties(prefix = "mail.client")
public class MailClientProperties {
    // mutable fields, getters/setters ...
}
~~~

và đồng thời:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(MailClientProperties.class)
class MailConfig {
}
~~~

Người viết có thể vô tình tạo hai đường đăng ký cho cùng một mục đích. Tùy cấu trúc context và cách naming, kết quả có thể là các bean cạnh tranh, ambiguity khi injection hoặc hành vi không mong muốn.

Quy ước đơn giản:

- Nếu dùng **constructor-bound immutable properties**, để `@ConfigurationProperties` trên type và đăng ký bằng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
- Nếu dùng **JavaBean-style properties như một component** vì có lý do cụ thể, hiểu rõ cách binding và tránh thêm registration song song.
- Với nhiều module, chỉ định module nào là chủ sở hữu của mỗi properties type và đường đưa nó vào context.
- Không đánh dấu properties class bằng `@Service`, `@Repository` hay `@Controller`; chúng là dữ liệu cấu hình, không phải tầng nghiệp vụ hoặc HTTP endpoint.

**Không cần thêm một `@Bean` trả về `new ClientProperties(...)`** chỉ để compiler “nhìn thấy” object. Cách đó sẽ làm mất lợi ích của config binding chuyên dụng nếu không tự đảm bảo cơ chế binding phù hợp.

## 21. Test đăng ký tường minh với ApplicationContextRunner

Khi viết auto-configuration hoặc module hạ tầng, `ApplicationContextRunner` từ Spring Boot test là công cụ thuận tiện để tạo context nhỏ và xác nhận registration/binding.

Ví dụ:

~~~java
package example.client.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ClientConfigurationTest {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestClientConfig.class);

    @Test
    void registersAndBindsProperties() {
        contextRunner
            .withPropertyValues(
                "app.client.base-url=https://api.example.invalid",
                "app.client.connect-timeout=2s",
                "app.client.max-attempts=3"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                    ClientProperties.class);

                ClientProperties properties =
                    context.getBean(ClientProperties.class);

                assertThat(properties.maxAttempts())
                    .isEqualTo(3);
                assertThat(properties.connectTimeout())
                    .isEqualTo(java.time.Duration.ofSeconds(2));
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ClientProperties.class)
    static class TestClientConfig {
    }
}
~~~

Giả sử `ClientProperties` record của phần trước tồn tại trong package này. Bài test chứng minh ba điều cụ thể:

1. `TestClientConfig` được đưa vào context.
2. `@EnableConfigurationProperties` đăng ký đúng một `ClientProperties` bean.
3. Giá trị từ property sources được bind thành typed fields.

Nếu cấu hình chưa nạp được do test environment hay converter, cần xem loại context và dependency. `ApplicationContextRunner` cung cấp bối cảnh nhỏ hữu ích nhưng không nhất thiết giống một ứng dụng đầy đủ có tất cả auto-configuration.

### Test thiếu registration

Một bài test có thể cố tình tạo context chỉ chứa service cần `ClientProperties` mà không có `ClientConfiguration`. Nếu service bắt buộc constructor parameter đó, context sẽ không khởi tạo thành công.

Ý nghĩa của test là chứng minh module có dependency với properties bean. Không nên biến thiếu registration thành property default hoặc xử lý lỗi ở client; lỗi nằm ở **composition của ApplicationContext**.

### Test cấu hình sai

Ví dụ:

~~~java
contextRunner
    .withPropertyValues(
        "app.client.base-url=https://api.example.invalid",
        "app.client.connect-timeout=not-a-duration",
        "app.client.max-attempts=3"
    )
    .run(context -> {
        assertThat(context).hasFailed();
    });
~~~

Nếu converter cố chuyển `not-a-duration` sang `Duration`, khởi tạo configuration-properties bean có thể thất bại. Test này giúp phân biệt lỗi registration với lỗi conversion và phát hiện cấu hình deployment bị sai trước khi chạy production.

## 22. Test với @SpringBootTest và cấu hình thật của ứng dụng

Trong integration test có Spring Boot context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "app.client.base-url=https://test.example.invalid",
    "app.client.connect-timeout=1s",
    "app.client.max-attempts=2"
})
class ClientPropertiesIntegrationTest {

    @Autowired
    ClientProperties properties;

    @Test
    void resolvesConfiguration() {
        assertThat(properties.baseUrl().toString())
            .isEqualTo("https://test.example.invalid");
        assertThat(properties.maxAttempts()).isEqualTo(2);
    }
}
~~~

Ví dụ giả định application class của test đã nạp configuration có `@EnableConfigurationProperties(ClientProperties.class)`. Nếu test chỉ khởi tạo slice context không bao gồm class đó, cần import hoặc enable properties một cách phù hợp trong cấu hình test.

Cần tránh test dựa vào secret hoặc endpoint production. Hãy cấp giá trị giả lập, test container hoặc test-specific properties đủ để kích hoạt cấu trúc ứng dụng mà không gọi dịch vụ thật.

## 23. Registration, binding và validation là ba trách nhiệm độc lập

Một điểm cốt lõi nên nằm trong tư duy thiết kế:

| Câu hỏi | Cơ chế chủ yếu |
| --- | --- |
| Type nào đại diện cho nhóm property? | `@ConfigurationProperties(prefix = ...)` |
| Type đó có phải Spring bean không? | `@EnableConfigurationProperties`, scan hoặc cơ chế đăng ký phù hợp |
| Giá trị đến từ đâu? | Spring Environment và các PropertySource/Config Data |
| Tên key được ánh xạ sang field ra sao? | Spring Boot Binder và relaxed binding |
| Giá trị chuỗi chuyển sang kiểu Java thế nào? | ConversionService / Binder |
| Giá trị có hợp lệ với yêu cầu vận hành không? | Validation/kiểm tra ràng buộc |
| Bean client có được tạo không? | `@Bean`, `@Conditional...` và các điều kiện của context |
| Giá trị có đổi tức thời khi sửa YAML không? | Không mặc nhiên; cần thiết kế refresh riêng |

Ví dụ có `@EnableConfigurationProperties(MailProperties.class)` nhưng thiếu `mail.host`: bean registration có thể hợp lệ, trong khi binding/validation hoặc logic tạo mail client có thể thất bại.

Ngược lại, YAML có `mail.host` chuẩn xác nhưng không đăng ký `MailProperties` thì Spring không tự có bean cùng type để inject.

## 24. Cấu hình theo profile và thứ tự ưu tiên

Ví dụ cấu hình chung:

~~~yaml
# application.yml
app:
  client:
    base-url: "https://dev.example.invalid"
    connect-timeout: 2s
    max-attempts: 3
~~~

Profile production:

~~~yaml
# application-prod.yml
app:
  client:
    base-url: "https://prod.example.invalid"
    connect-timeout: 5s
~~~

Nếu ứng dụng kích hoạt profile `prod`, và không có nguồn nào ưu tiên cao hơn ghi đè, properties bean nhận `baseUrl` và `connectTimeout` từ cấu hình production, còn `maxAttempts` có thể giữ giá trị từ cấu hình chung.

Bạn **không cần**:

~~~java
@EnableConfigurationProperties(
    ProdClientProperties.class
)
~~~

chỉ vì endpoint khác ở production, nếu cả hai môi trường dùng cùng một cấu trúc typed properties. Một `ClientProperties` duy nhất, đăng ký một lần, sẽ nhận **giá trị phù hợp với môi trường hiện hành**.

Đừng tạo `LocalClientProperties`, `StagingClientProperties`, `ProdClientProperties` nếu chỉ khác URI hoặc timeout. Profile và externalized configuration xử lý khác biệt **giá trị**; properties type biểu diễn **hợp đồng cấu hình**.

Nếu topology bean thực sự khác, có thể dùng `@Profile` hoặc `@ConditionalOnProperty` ở lớp khai báo bean tích hợp; điều kiện tạo bean và việc đăng ký typed properties là hai khía cạnh riêng.

## 25. Khi nào nên dùng đăng ký tường minh?

Chọn `@EnableConfigurationProperties` khi:

- Module có **một hoặc một vài** properties types đã biết rõ.
- Muốn class cấu hình thể hiện chính xác module đăng ký những hợp đồng cấu hình nào.
- Properties types nằm ngoài package quét thông thường.
- Đang xây dựng thư viện/starter/auto-configuration và không muốn yêu cầu ứng dụng scan package của thư viện.
- Muốn test một tập cấu hình nhỏ trong isolated ApplicationContext.
- Muốn giữ record immutable không bị biến thành component-style bean creation.

Cân nhắc `@ConfigurationPropertiesScan` khi:

- Ứng dụng có nhiều properties types nằm trong package được tổ chức nhất quán.
- Danh sách các type thay đổi thường xuyên, việc duy trì liệt kê thủ công làm tăng chi phí.
- Đội ngũ đã quy định package scan rõ ràng và dễ kiểm tra.

Cân nhắc `@Bean` + `@ConfigurationProperties` trên method khi:

- Đối tượng cấu hình là class bên thứ ba cần bind qua setter.
- Bạn không thể đặt annotation trên class đó.
- Bạn hiểu rõ nó là bean được tạo thông thường rồi mới được bind, không phải record constructor binding.

## 26. Checklist chẩn đoán

Khi một properties bean không hoạt động như mong muốn:

1. **Type**: class đã có `@ConfigurationProperties` với prefix chính xác chưa?
2. **Registration**: có `@EnableConfigurationProperties(Type.class)` hoặc scan phù hợp chưa?
3. **Configuration class**: class mang `@EnableConfigurationProperties` có được Spring nạp không?
4. **Trùng lặp**: có kết hợp `@Component`, scan và explicit registration gây nhiều đường tạo bean không?
5. **Nguồn property**: file, profile, import, biến môi trường và command line đã chứa key đúng chưa?
6. **Binding**: YAML có map đúng cấu trúc, tên kebab-case và kiểu Java không?
7. **Conversion**: giá trị số, boolean, `Duration`, `URI`, enum có định dạng được hỗ trợ không?
8. **Validation**: có dependency validation và annotation `@Validated`/ràng buộc cần thiết không?
9. **Bean consumer**: service/client cần inject type nào, có nhiều bean cùng type không?
10. **Test context**: test có load đủ configuration, hay chỉ là một context slice đã loại bỏ phần registration?
11. **Deployment**: giá trị có bị nguồn ưu tiên cao hơn override không?
12. **Startup lifecycle**: cấu hình thay đổi có yêu cầu restart/refresh riêng không?

Một số thông báo lỗi có thể giúp phân loại:

~~~text
No qualifying bean of type '...ClientProperties'
    -> Xem registration và context composition.

Failed to bind properties under 'app.client'
    -> Xem prefix, cấu trúc nguồn và conversion.

Validation failed for ...Properties
    -> Xem các ràng buộc và giá trị cụ thể.

No qualifying bean of type '...Client'
    -> Xem factory @Bean / @ConditionalOnProperty / @Profile.
~~~

Tên message chi tiết có thể khác tùy phiên bản và cấu trúc exception; hãy đọc nguyên nhân gốc thay vì chỉ nhìn headline “Application failed to start”.

## 27. Bài tập tổng hợp

**Đề bài:** ứng dụng cần một typed configuration cho worker, trong đó số thread tối đa bằng 8, polling interval bằng 5 giây, và một cờ bật/tắt chức năng. Đăng ký tường minh bean cấu hình, không dùng `@Component` trên record.

**Bước 1 — application.yml:**

~~~yaml
worker:
  enabled: true
  max-threads: 8
  polling-interval: 5s
~~~

**Bước 2 — typed properties:**

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        boolean enabled,
        int maxThreads,
        Duration pollingInterval
) {}
~~~

**Bước 3 — registration:**

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(WorkerProperties.class)
class WorkerConfiguration {
}
~~~

**Bước 4 — consumer:**

~~~java
import org.springframework.stereotype.Service;

@Service
class WorkerService {

    private final WorkerProperties properties;

    WorkerService(WorkerProperties properties) {
        this.properties = properties;
    }

    int concurrency() {
        return properties.maxThreads();
    }
}
~~~

**Bước 5 — câu hỏi tự kiểm tra:**

- Nếu bỏ `@EnableConfigurationProperties(WorkerProperties.class)` và không có scan khác, service có thể gặp lỗi gì?
- Nếu đặt `max-threads: "many"`, đó là lỗi registration hay conversion?
- Nếu đặt `max-threads: -1`, cần ràng buộc gì để khởi động thất bại có chủ đích?
- Nếu production muốn `max-threads: 16`, có cần tạo `ProdWorkerProperties` không?
- Nếu `WorkerProperties` nằm trong module thư viện ngoài package scan, làm sao bảo đảm `WorkerConfiguration` được import/nạp?

Đáp án tư duy: bean registration, binding, validation và giá trị theo môi trường là các trách nhiệm tách biệt. Không nên giải một trách nhiệm bằng cách gắn thêm annotation bất kỳ thuộc trách nhiệm khác.

## 28. Ghi nhớ

`@EnableConfigurationProperties` dùng để **đăng ký tường minh một hoặc nhiều class `@ConfigurationProperties`** trong ApplicationContext. Nó thường được đặt trên `@Configuration` hoặc application class đã được Spring Boot nạp. Sau registration, Binder đọc các property dưới prefix được khai báo, chuyển kiểu, rồi tạo đối tượng cấu hình có thể inject vào service và bean factory.

Dùng annotation này để làm rõ module nào sở hữu typed configuration, đặc biệt với record bất biến hoặc module library/auto-configuration. So với `@ConfigurationPropertiesScan`, nó hạn chế việc tìm class dựa vào package và thể hiện danh sách chính xác hơn. Tránh trộn constructor binding với `@Component`, không tạo nhiều đường đăng ký trùng lặp, và không nhầm **có bean** với **cấu hình hợp lệ**.

**Công thức ngắn gọn: `@ConfigurationProperties` định nghĩa hợp đồng; `@EnableConfigurationProperties` đăng ký hợp đồng thành bean; Spring Boot Binder áp dụng giá trị; validation xác nhận giá trị đúng yêu cầu.**