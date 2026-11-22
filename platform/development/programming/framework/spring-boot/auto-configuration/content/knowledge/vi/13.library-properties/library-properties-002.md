# Đăng ký lớp thuộc tính thư viện bằng @EnableConfigurationProperties trong Spring Boot

## 1. Bài toán: thư viện cần một bean cấu hình có kiểu rõ ràng

Một thư viện tích hợp thường cần nhận cấu hình từ ứng dụng sử dụng thư viện, chẳng hạn endpoint, thời gian chờ và cờ bật tính năng:

~~~properties
acme.client.endpoint=https://orders.example/api
acme.client.connect-timeout=5s
acme.client.enabled=true
~~~

Trong Spring Boot, `@ConfigurationProperties` mô tả cách **bind** các key có cùng prefix vào một Java object. Nhưng việc đặt `@ConfigurationProperties` trên class **chưa đủ để đảm bảo class đó được đăng ký thành Spring bean** trong mọi context. Khi tạo một starter hoặc auto-configuration của thư viện, cách đăng ký tường minh và ổn định là:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {
    // Các @Bean của thư viện sử dụng AcmeClientProperties
}
~~~

Kết quả mong muốn là:
- Spring Boot biết phải đăng ký `AcmeClientProperties` làm bean của `ApplicationContext` khi cấu hình này được áp dụng.
- Hệ thống binding lấy giá trị tương ứng từ Spring `Environment` và ánh xạ vào các trường/constructor của class.
- Các bean nghiệp vụ được tạo về sau có thể nhận `AcmeClientProperties` bằng constructor hoặc tham số của phương thức `@Bean`.
- Ứng dụng tiêu thụ starter không phải tự khai báo `@Bean AcmeClientProperties` hoặc tự quét package riêng của thư viện.

**Điểm mấu chốt:** `@ConfigurationProperties` mô tả **hình dạng dữ liệu và prefix**, còn `@EnableConfigurationProperties` ở cấu hình sử dụng thư viện xác định **những lớp properties nào được đăng ký**. Nó không có nghĩa là tự động tìm mọi lớp properties trong classpath.

## 2. Ba vai trò: khai báo, đăng ký và sử dụng

Hãy phân biệt ba bước:

| Bước | Cơ chế | Trách nhiệm |
| --- | --- | --- |
| **Khai báo kiểu cấu hình** | `@ConfigurationProperties(prefix = "acme.client")` | Chọn namespace và ánh xạ key sang thuộc tính Java có kiểu. |
| **Đăng ký bean cấu hình** | `@EnableConfigurationProperties(AcmeClientProperties.class)` | Cho Spring Boot biết class properties cụ thể phải được xử lý trong context. |
| **Sử dụng bean đã bind** | Constructor injection hoặc tham số `@Bean` | Đọc các giá trị đã bind để khởi tạo thành phần nghiệp vụ. |

Ví dụ khái quát:

~~~text
application.yml / application.properties / biến môi trường
                         |
                         v
                 Spring Environment
                         |
                         v
           Configuration Properties Binder
                         |
                         v
           AcmeClientProperties (Spring bean)
                         |
                         v
          ClientAutoConfiguration @Bean
                         |
                         v
                     AcmeClient
~~~

Chuỗi này diễn tả **luồng nguồn giá trị đến consumer**. Trong thực tế Spring Boot thực hiện đăng ký bean definition, binding và khởi tạo bean theo lifecycle của container; sơ đồ không có nghĩa mọi giai đoạn luôn diễn ra tuần tự như một pipeline runtime.

### Hai annotation không thay thế cho nhau

~~~java
@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {
    // fields / getters / setters
}
~~~

Class này có metadata để binder xử lý nhưng việc tự viết class và đưa JAR vào classpath không đủ để mọi ứng dụng tự tạo bean. Muốn bật cho class cụ thể, ghi:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(AcmeClientProperties.class)
class AcmeClientConfiguration {
}
~~~

Đối với auto-configuration, dùng `@AutoConfiguration` thay `@Configuration` là lựa chọn phù hợp vì Spring Boot có cơ chế phát hiện và điều kiện hóa auto-configuration riêng.

## 3. Cú pháp chính xác của @EnableConfigurationProperties

Annotation cần import từ:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
~~~

Thuộc tính `value` là mảng `Class<?>[]` nên có thể đăng ký **một hoặc nhiều** lớp đã đánh dấu `@ConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties({
    AcmeClientProperties.class,
    AcmeRetryProperties.class
})
public class AcmeClientAutoConfiguration {
}
~~~

Các class `AcmeClientProperties` và `AcmeRetryProperties` ở đoạn trên là class do thư viện cung cấp; chúng cần được định nghĩa và đặt `@ConfigurationProperties` phù hợp. Dạng chỉ có một class có thể viết gọn:

~~~java
@EnableConfigurationProperties(AcmeClientProperties.class)
~~~

Dạng không truyền class:

~~~java
@EnableConfigurationProperties
~~~

vẫn kích hoạt hỗ trợ xử lý `@ConfigurationProperties` theo cơ chế của Spring Boot, **nhưng không đăng ký tùy ý mọi class properties mà thư viện có trên classpath**. Nếu chủ đích là đăng ký kiểu của thư viện, hãy đưa class vào danh sách `value`.

### Đặt annotation ở đâu?

- Trên `@AutoConfiguration` của thư viện: cách phù hợp khi thư viện được tích hợp qua starter.
- Trên `@Configuration` thông thường: phù hợp nếu ứng dụng chủ động import cấu hình.
- Không đặt trên một phương thức `@Bean`: `@EnableConfigurationProperties` có target **TYPE**, dùng ở mức class/interface annotation hợp lệ, không phải METHOD.

Khi auto-configuration class bị loại bởi điều kiện cấp class, các khai báo bean và đăng ký properties gắn với cấu hình đó cũng không được áp dụng qua class ấy. Ngược lại, khi class được áp dụng nhưng chỉ **một phương thức `@Bean`** bị loại bởi điều kiện cấp method, `@EnableConfigurationProperties` ở cấp class vẫn có thể đăng ký bean properties.

## 4. Ví dụ cấu trúc thư viện thực tế (Java 17+, Spring Boot 3.3)

Giả sử thư viện có một class properties, một client, và một auto-configuration. Ba file sau là một ví dụ minh họa đầy đủ về cách kết nối các phần; package và tên class phải khớp khi áp dụng vào dự án.

**File `src/main/java/com/acme/client/AcmeClientProperties.java`:**

~~~java
package com.acme.client;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {

    private URI endpoint = URI.create("https://api.example.invalid");
    private Duration connectTimeout = Duration.ofSeconds(2);
    private boolean enabled;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Class có constructor mặc định do Java tạo, getter/setter chuẩn JavaBean và các giá trị mặc định. Spring Boot có thể chuyển `String` thành `URI` và `Duration` khi bind, ví dụ `5s` thành `Duration.ofSeconds(5)`.

**File `src/main/java/com/acme/client/AcmeClient.java`:**

~~~java
package com.acme.client;

import java.net.URI;
import java.time.Duration;

public class AcmeClient {

    private final URI endpoint;
    private final Duration connectTimeout;

    public AcmeClient(URI endpoint, Duration connectTimeout) {
        this.endpoint = endpoint;
        this.connectTimeout = connectTimeout;
    }

    public String description() {
        return endpoint.getHost() + " | " + connectTimeout.toSeconds() + "s";
    }
}
~~~

`AcmeClient` ở đây là đối tượng Java đơn giản để minh họa việc nhận cấu hình; nó không mở kết nối HTTP. Trong thư viện thực tế, client có thể là một adapter HTTP, message producer hoặc service xử lý nghiệp vụ.

**File `src/main/java/com/acme/client/AcmeClientAutoConfiguration.java`:**

~~~java
package com.acme.client;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.client",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.getEndpoint(),
                properties.getConnectTimeout()
        );
    }
}
~~~

Có hai quyết định riêng trong code:

1. `@EnableConfigurationProperties(AcmeClientProperties.class)` đăng ký bean chứa cấu hình của thư viện.
2. `@ConditionalOnProperty(... havingValue = "true")` trên `@Bean` chỉ bật `AcmeClient` khi `acme.client.enabled=true`; `@ConditionalOnMissingBean` cho phép ứng dụng cung cấp `AcmeClient` riêng.

Vì vậy **`enabled=false` không đồng nghĩa properties bean biến mất**. Class auto-configuration vẫn tham gia, properties bean vẫn được đăng ký, chỉ `AcmeClient` do phương thức trên tạo bị bỏ qua.

### Đăng ký auto-configuration trong JAR

Tạo file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Với nội dung một dòng:

~~~text
com.acme.client.AcmeClientAutoConfiguration
~~~

Đây là file mà Spring Boot 3.x dùng để tìm class auto-configuration trong JAR. Chỉ thêm `@AutoConfiguration` và `@EnableConfigurationProperties` vào class mà **không đăng ký class auto-configuration đúng cách** thì starter chưa bảo đảm được ứng dụng tự áp dụng cấu hình.

Dự án tiêu thụ thêm dependency chứa các class trên vào classpath và thiết lập:

~~~yaml
acme:
  client:
    enabled: true
    endpoint: https://orders.example/api
    connect-timeout: 5s
~~~

Khi context khởi động thành công, `AcmeClientProperties` sẽ được bind và bean `AcmeClient` dùng endpoint/timeout trên. Ví dụ `description()` trả `orders.example | 5s`. Đây là giá trị trả về từ method minh họa; không phải log startup mặc định.

## 5. Bean được đặt tên thế nào và được tiêm ra sao?

Khi lớp `@ConfigurationProperties` được đăng ký bằng `@EnableConfigurationProperties` (hoặc `@ConfigurationPropertiesScan`), Spring Boot dùng tên bean theo quy ước:

~~~text
<prefix>-<fully-qualified-class-name>
~~~

Ví dụ đối với class trong mục 4:

~~~text
acme.client-com.acme.client.AcmeClientProperties
~~~

Nếu `@ConfigurationProperties` không có prefix, tên thường là tên class đầy đủ. Cơ chế đặt tên này khác với tên mặc định của bean tạo bởi một method `@Bean`, vốn thường lấy từ tên method.

Tuy nhiên, khi tiêu thụ properties trong một phương thức bean, **hãy tiêm theo type**:

~~~java
@Bean
AcmeClient acmeClient(AcmeClientProperties properties) {
    return new AcmeClient(
            properties.getEndpoint(),
            properties.getConnectTimeout()
    );
}
~~~

Đoạn trên chỉ minh họa dependency injection, không phải một cấu hình đầy đủ để chạy độc lập. Thông thường ứng dụng **không cần và không nên hardcode** tên bean theo prefix+FQN để nhận instance.

Việc type `AcmeClientProperties` xuất hiện trong tham số `@Bean` **không tự đăng ký** bean đó. Nếu context chưa có bean properties, constructor/method injection có thể thất bại bằng lỗi không tìm thấy dependency. Điều kiện tiên quyết là lớp đã được đăng ký qua cơ chế phù hợp.

### Không đăng ký lặp theo nhiều đường không kiểm soát

Tránh đồng thời:
- Đăng ký `AcmeClientProperties` qua `@EnableConfigurationProperties(AcmeClientProperties.class)`.
- Đánh dấu cùng class với `@Component` để component scan cũng phát hiện.
- Tự tạo thêm `@Bean AcmeClientProperties` mà không có lý do rõ ràng.

Các đường đăng ký khác nhau có thể làm **xuất hiện nhiều bean cùng type**, gây ambiguous injection, lifecycle khó kiểm soát và bất ngờ về binding/validation. Không mặc định giả định rằng mỗi cách đăng ký đều tạo cùng một tên hoặc tự loại trừ nhau. Trong starter, nên dùng một đường đăng ký được tài liệu hóa rõ ràng.

## 6. So sánh với @ConfigurationPropertiesScan và @Component

| Cách đăng ký | Cách hoạt động | Dùng khi nào |
| --- | --- | --- |
| `@EnableConfigurationProperties(X.class)` | Đăng ký **tường minh** class X | Thư viện, auto-configuration, chỉ kích hoạt nhóm properties cần thiết |
| `@ConfigurationPropertiesScan` | Tìm class `@ConfigurationProperties` trong package được scan | Ứng dụng sở hữu package properties và muốn đăng ký nhiều class cùng quy ước |
| `@Component` trên class `@ConfigurationProperties` | Component scan đăng ký như một Spring bean thông thường, sau đó binding xử lý metadata | JavaBean mutable có lifecycle và nhu cầu scan thông thường; không phù hợp constructor binding thuần |
| `@Bean` với `@ConfigurationProperties` trên method | Đăng ký instance do method tạo, rồi binder gắn properties | Thành phần của thư viện thứ ba không sửa được source để đặt annotation lên class |

**Phân biệt đặc biệt quan trọng:** `@SpringBootApplication` bao gồm component scan cho component, nhưng điều đó **không tự bật `@ConfigurationPropertiesScan`** cho mọi class properties thuần. Nếu class không là component và không có cơ chế enable/scan riêng, nó có thể không có bean.

Đối với **thư viện**, tránh phụ thuộc ứng dụng khác có scan package `com.acme.client`. Package của thư viện có thể nằm ngoài scan root của ứng dụng. Khai báo `@EnableConfigurationProperties` trên auto-configuration giúp dependency được định nghĩa **tại nơi thư viện chịu trách nhiệm**.

Ví dụ scan trong ứng dụng (không phải chiến lược bắt buộc cho starter):

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan("com.example.app.config")
public class ExampleApplication {

    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
~~~

Đoạn này cần các import `SpringBootApplication`, `ConfigurationPropertiesScan` và `SpringApplication` tương ứng, đồng thời giả định package `com.example.app.config` chứa các class properties hợp lệ. Nó minh họa sự khác biệt về **phạm vi tìm kiếm class**, không thay thế phần đăng ký starter ở mục 4.

## 7. Record, constructor binding và JavaBean binding

Spring Boot 3.3 hỗ trợ hai phong cách chủ yếu:

**JavaBean binding:** class có constructor rỗng, getter/setter, phù hợp ví dụ `AcmeClientProperties` ở trên. Có thể đặt giá trị mặc định tại field và bind các property được cấu hình.

**Constructor binding:** class immutable/`record` nhận các giá trị từ constructor thay vì setter. Với một constructor thích hợp (như record một constructor canonical), Spring Boot 3.x suy luận constructor binding; không cần đặt `@ConstructorBinding` trên cả class chỉ để dùng record.

Ví dụ **record riêng**:

~~~java
package com.acme.client;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.retry")
public record AcmeRetryProperties(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("2s") Duration backoff
) {
}
~~~

Để sử dụng record:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeRetryProperties.class)
class AcmeRetryAutoConfiguration {
}
~~~

Hai đoạn này là ví dụ về cấu hình record; ngoài project cần các import `AutoConfiguration` và `EnableConfigurationProperties` trong file cấu hình.

**Ràng buộc của constructor binding:** các class properties được tạo qua cơ chế enable hoặc configuration property scanning hỗ trợ kiểu binding này. Constructor binding **không dành cho một bean được tạo bằng các cơ chế Spring thông thường** như `@Component`, method `@Bean`, hay `@Import`. Đừng đánh dấu cùng record đó thành component chỉ để “đăng ký cho nhanh”. Với trường hợp bắt buộc tạo bean bằng factory method, thường dùng JavaBean binding và thiết kế object phù hợp.

Để nhận tên tham số constructor khi bind, project cần biên dịch với `-parameters`. Spring Boot Gradle plugin và cấu hình Maven chuẩn của Boot hỗ trợ việc này. Nếu không dùng build conventions đó, cần kiểm tra compiler flags.

### Không nên đưa dependency nghiệp vụ vào class properties

Class `@ConfigurationProperties` tốt nhất đại diện **dữ liệu từ Environment**. Không nên constructor-inject service/repository vào nó rồi nhầm dependency bean với giá trị property. Bean nghiệp vụ nên nhận properties sau khi chúng đã bind:

~~~text
Environment -> AcmeClientProperties -> AcmeClient
~~~

Cách tổ chức này cho phép test binder và test nghiệp vụ độc lập.

## 8. Validation và giới hạn của @EnableConfigurationProperties

`@EnableConfigurationProperties` giúp đăng ký bean, **không có nghĩa dữ liệu tự động hợp lệ**. Khi cần ràng buộc input, Spring Boot hỗ trợ validation của `@ConfigurationProperties`:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "acme.credentials")
public record AcmeCredentialsProperties(
        @NotBlank String token,
        @Positive int poolSize
) {
}
~~~

Đây là **trích đoạn minh họa**; đặt trong class/file hợp lệ và bảo đảm có một Jakarta Bean Validation provider, thường qua dependency `spring-boot-starter-validation`. Sau đó đăng ký `AcmeCredentialsProperties.class` trong `@EnableConfigurationProperties`. Nếu không cung cấp `token` hoặc `pool-size` phù hợp, quá trình bind/validate có thể làm ứng dụng khởi động thất bại với lỗi cấu hình, giúp phát hiện sớm.

Không nhầm ba việc:
1. **Đăng ký:** `@EnableConfigurationProperties`.
2. **Bind dữ liệu:** `@ConfigurationProperties`, binder, conversion.
3. **Kiểm tra tính hợp lệ:** `@Validated` + constraints và provider validation.

`@ConfigurationProperties` mặc định không dùng Spring Expression Language (SpEL) như `@Value`. Bản thân annotation enable không cấp quyền truy cập secret hoặc chủ động nạp file property mới; giá trị lấy từ các property sources đã có trong `Environment` theo thứ tự ưu tiên.

## 9. Bài kiểm thử Spring Boot 3.3 chạy được

Ví dụ sau là **một file test Java hoàn chỉnh**, độc lập với ba file minh họa ở mục 4. Nó sử dụng Java 17+, Spring Boot 3.3, JUnit 5, AssertJ và `ApplicationContextRunner` để kiểm tra cả đăng ký properties, bind giá trị, điều kiện bật client và khả năng người dùng thay bean mặc định.

Tạo file `src/test/java/com/example/demo/EnableLibraryPropertiesTest.java`:

~~~java
package com.example.demo;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class EnableLibraryPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ClientAutoConfiguration.class));

    @ConfigurationProperties(prefix = "acme.client")
    public static class ClientProperties {
        private URI endpoint = URI.create("https://api.example.invalid");
        private Duration connectTimeout = Duration.ofSeconds(2);
        private boolean enabled;

        public URI getEndpoint() {
            return endpoint;
        }

        public void setEndpoint(URI endpoint) {
            this.endpoint = endpoint;
        }

        public Duration getConnectTimeout() {
            return connectTimeout;
        }

        public void setConnectTimeout(Duration connectTimeout) {
            this.connectTimeout = connectTimeout;
        }

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    static final class ClientFacade {
        private final URI endpoint;
        private final Duration timeout;

        ClientFacade(URI endpoint, Duration timeout) {
            this.endpoint = endpoint;
            this.timeout = timeout;
        }

        String description() {
            return endpoint.getHost() + " | " + timeout.toSeconds() + "s";
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(ClientProperties.class)
    static class ClientAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.client",
                name = "enabled",
                havingValue = "true"
        )
        @ConditionalOnMissingBean(ClientFacade.class)
        ClientFacade clientFacade(ClientProperties properties) {
            return new ClientFacade(
                    properties.getEndpoint(),
                    properties.getConnectTimeout()
            );
        }
    }

    @Test
    void annotationAloneDoesNotRegisterPropertiesBean() {
        new ApplicationContextRunner().run(context ->
                assertThat(context).doesNotHaveBean(ClientProperties.class));
    }

    @Test
    void enabledRegistrationCreatesPropertiesWithDefaults() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(ClientProperties.class);
            assertThat(context).doesNotHaveBean(ClientFacade.class);

            ClientProperties properties = context.getBean(ClientProperties.class);
            assertThat(properties.getEndpoint().toString())
                    .isEqualTo("https://api.example.invalid");
            assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(properties.isEnabled()).isFalse();
        });
    }

    @Test
    void bindsValuesFromSpringEnvironment() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://orders.example/api",
                "acme.client.connect-timeout=5s",
                "acme.client.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);
                    assertThat(context).hasSingleBean(ClientFacade.class);

                    ClientProperties properties =
                            context.getBean(ClientProperties.class);
                    assertThat(properties.getEndpoint().getHost())
                            .isEqualTo("orders.example");
                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                    assertThat(properties.isEnabled()).isTrue();
                    assertThat(context.getBean(ClientFacade.class).description())
                            .isEqualTo("orders.example | 5s");
                });
    }

    @Test
    void disabledClientDoesNotRemovePropertiesBean() {
        runner.withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);
                    assertThat(context).doesNotHaveBean(ClientFacade.class);
                });
    }

    @Test
    void userClientBeanMakesAutoConfigurationBackOff() {
        runner.withPropertyValues("acme.client.enabled=true")
                .withBean(ClientFacade.class,
                        () -> new ClientFacade(
                                URI.create("https://user.example"),
                                Duration.ofSeconds(9)))
                .run(context -> {
                    assertThat(context).hasSingleBean(ClientProperties.class);
                    assertThat(context).hasSingleBean(ClientFacade.class);
                    assertThat(context.getBean(ClientFacade.class).description())
                            .isEqualTo("user.example | 9s");
                });
    }
}
~~~

Chạy trong project có dependency `org.springframework.boot:spring-boot-starter-test` và Gradle wrapper:

~~~bash
./gradlew test --tests "com.example.demo.EnableLibraryPropertiesTest"
~~~

Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.EnableLibraryPropertiesTest"
~~~

**Kết quả kỳ vọng:** cả **5 test PASS**. Chúng là assertion kiểm tra bean và giá trị, không phải những lệnh sinh stdout cố định. `ApplicationContextRunner` dùng `AutoConfigurations.of(...)` để cung cấp auto-configuration trực tiếp trong test; do đó fixture test này không cần `AutoConfiguration.imports`. Đóng gói starter chạy trong ứng dụng thực vẫn cần file imports như mục 4.

Các test chứng minh:
- Chỉ có metadata `@ConfigurationProperties` trên class không đủ để bean tự xuất hiện trong context rỗng.
- `@EnableConfigurationProperties(ClientProperties.class)` đăng ký bean kể cả khi không truyền bất kỳ property nào; giá trị mặc định Java vẫn dùng.
- Các key `connect-timeout` được relaxed-binding vào `connectTimeout` và chuỗi `5s` được chuyển thành `Duration`.
- Condition trên bean client có thể không khớp mà bean properties vẫn tồn tại.
- Bean do người dùng cung cấp được ưu tiên khi auto-configuration có `@ConditionalOnMissingBean`.

## 10. Các lỗi hay gặp trong thư viện

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` với `AcmeClientProperties` | Class có `@ConfigurationProperties` nhưng chưa được đăng ký qua enable/scan/bean | Đặt `@EnableConfigurationProperties(AcmeClientProperties.class)` trên auto-configuration tham gia |
| Class auto-configuration không được áp dụng | Thiếu mục trong `AutoConfiguration.imports` hoặc bị điều kiện/exclude loại | Kiểm tra đường dẫn file imports và condition cấp class |
| Property YAML có giá trị nhưng Java field vẫn mặc định | Prefix/key sai, class chưa đăng ký, thiếu setter hoặc mapping không phù hợp | Kiểm tra prefix, relaxed binding, accessor/constructor và giá trị hiệu lực trong `Environment` |
| Nhiều bean cùng type properties | Vừa `@EnableConfigurationProperties` vừa tạo `@Bean`/scan component khác | Chọn một cách đăng ký chính; kiểm tra bean definitions trước khi xóa cấu hình |
| Record không được bind bằng constructor như kỳ vọng | Dùng đăng ký theo `@Component`/`@Bean` thông thường hoặc thiếu thông tin tham số compiler | Đăng ký bằng enable/scan và bảo đảm build hỗ trợ `-parameters` |
| Bean client vắng mặt nhưng properties có mặt | Condition trên method `@Bean` không khớp | Kiểm tra `@ConditionalOnProperty`/`@ConditionalOnClass` của bean nghiệp vụ |
| Dự án thêm starter nhưng IDE không gợi ý key | Thiếu metadata processor hoặc mô tả properties | Thêm `spring-boot-configuration-processor` và kiểm tra metadata được build |
| Validation không kích hoạt | Thiếu `@Validated`, constraint hoặc validator provider | Cấu hình validation đầy đủ và test input sai |
| Tên bean properties khác tên class ngắn | Quy ước bean name khi được enable/scan dùng prefix + FQN | Tiêm theo type, tránh hardcode tên bean |
| Thư viện chỉ hoạt động khi ứng dụng scan package thư viện | Dựa vào component scan của app tiêu thụ | Đăng ký tường minh bằng `@EnableConfigurationProperties` trong auto-configuration |

### Phân biệt hai annotation processor

- `spring-boot-configuration-processor` tạo **metadata cấu hình** để IDE cung cấp autocomplete và mô tả các key properties.
- `spring-boot-autoconfigure-processor` tạo **metadata hỗ trợ filter auto-configuration** để tối ưu quá trình khởi động.

Không processor nào là sự thay thế cho `@EnableConfigurationProperties(AcmeClientProperties.class)` hoặc cho việc đăng ký auto-configuration bằng file imports.

## 11. Cách chẩn đoán và thiết kế an toàn

Khi một bean properties của thư viện không xuất hiện, kiểm tra theo trình tự:

1. **Lớp properties:** có `@ConfigurationProperties(prefix = "...")` đúng trên class và getter/setter hoặc constructor binding hợp lệ?
2. **Class cấu hình đăng ký:** có `@EnableConfigurationProperties(X.class)` với **đúng type X** và class đó thực sự tham gia context?
3. **Phát hiện auto-configuration:** file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` có đúng tên class, đúng dấu phân tách cho nested class nếu có?
4. **Điều kiện cấp class:** `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` hoặc exclude có làm class không tham gia?
5. **Nguồn cấu hình:** key tồn tại ở nguồn nào, giá trị cuối cùng theo precedence của `Environment` là gì, có đánh nhầm prefix/cách viết?
6. **Binding và validation:** kiểu Java có chuyển đổi từ property được không, có null/giá trị sai, Bean Validation có được bật?
7. **Consumer bean:** properties đã tồn tại nhưng `@Bean` nghiệp vụ có condition riêng hay bị `@ConditionalOnMissingBean` back off?

Bật `--debug` hoặc `debug=true` của Spring Boot để quan sát **Condition Evaluation Report** nếu nghi auto-configuration bị loại. Khi đã cài Actuator và expose endpoint phù hợp, `/actuator/configprops` giúp kiểm tra các bean cấu hình (thận trọng với các giá trị nhạy cảm và cơ chế che dữ liệu), còn `/actuator/conditions` giúp xem lý do match/unmatch. Với test tự động, `ApplicationContextRunner` hỗ trợ dựng từng trường hợp bằng `withPropertyValues(...)` và `withBean(...)` để thấy rõ điều kiện.

Trong thiết kế thư viện, nên giữ một namespace thuộc sở hữu thư viện như `acme.client`, chọn default rõ ràng, quản lý validation cho giá trị bắt buộc và để auto-configuration đóng vai trò đăng ký các properties bean cụ thể. Tránh bắt ứng dụng tiêu thụ hiểu package nội bộ của thư viện.

## 12. Tự kiểm tra kiến thức

1. Chỉ viết `@ConfigurationProperties("acme.client")` trên POJO rồi đưa JAR vào classpath có bảo đảm bean được tạo không? **Không.** Cần cơ chế đăng ký.
2. `@EnableConfigurationProperties(A.class)` có tự phát hiện mọi class B, C cùng package không? **Không.** Nó chỉ định class được đăng ký.
3. Vì sao nên đặt `@EnableConfigurationProperties` ở auto-configuration của thư viện? **Để chính thư viện quyết định bean properties cần thiết, độc lập với scan root của ứng dụng tiêu thụ.**
4. Bean properties có còn tồn tại khi một method `@Bean` client gắn `@ConditionalOnProperty` không khớp không? **Có thể có**, vì việc đăng ký properties diễn ra ở cấp class auto-configuration vẫn được áp dụng.
5. `@ConfigurationPropertiesScan` có phải một phần tự động của `@SpringBootApplication` không? **Không**; cần kích hoạt scan khi lựa chọn cơ chế đó.
6. Class properties đăng ký qua enable có tên bean mặc định nào? **`<prefix>-<FQN>`**, ví dụ `acme.client-com.acme.client.AcmeClientProperties`.
7. Khi dùng record constructor binding, nên khai báo thêm `@Component` để “chắc chắn” scan ra bean không? **Không.** Dùng enable hoặc configuration property scanning và bảo đảm tham số constructor được nhận biết.
8. `@EnableConfigurationProperties` có tự validate một field `@NotBlank` khi không có validator provider không? **Không nên kỳ vọng**; cần `@Validated` và Bean Validation được cấu hình phù hợp.
9. Nếu config class chưa có trong `AutoConfiguration.imports`, chỉ thêm `@EnableConfigurationProperties` lên nó có làm starter tự chạy không? **Không.** Cần cơ chế nạp auto-configuration.
10. Vì sao một bean type `AcmeClientProperties` có thể thiếu dù giá trị `acme.client.enabled=true` đã có trong YAML? Vì **property source không tự biến class properties thành bean**; phải đăng ký, bind và đảm bảo cấu hình tương ứng được áp dụng.

## Tài liệu chính thức

- [Spring Boot 3.3 — Externalized Configuration, type-safe configuration properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): cơ chế binding, `@EnableConfigurationProperties`, scanning, constructor binding, validation và bean name.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): phát hiện auto-configuration qua `AutoConfiguration.imports` và thiết kế starter.
- [Spring Boot 3.3 — JavaDoc `@EnableConfigurationProperties`](https://docs.spring.io/spring-boot/3.3.8/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html): annotation cấp type, `value` và đăng ký bean cụ thể.
- [Spring Boot 3.3 — Configuration Metadata Annotation Processor](https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata/annotation-processor.html): metadata dành cho hỗ trợ IDE.
