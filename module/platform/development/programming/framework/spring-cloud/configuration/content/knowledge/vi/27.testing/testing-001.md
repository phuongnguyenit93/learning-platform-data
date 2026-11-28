# Kiểm thử binding và validation bằng ApplicationContextRunner

Spring Cloud Config cung cấp cấu hình tập trung cho nhiều ứng dụng Spring Boot. Sau khi Config Client nạp property source từ Config Server, Spring Boot đưa các giá trị vào `Environment`; `@ConfigurationProperties` bind chúng thành object có kiểu để bean nghiệp vụ sử dụng. Một lỗi nhỏ như sai tên property, sai đơn vị thời gian, thiếu giá trị bắt buộc hoặc giá trị vượt giới hạn có thể chỉ xuất hiện khi ứng dụng khởi động.

`ApplicationContextRunner` giúp kiểm thử riêng quá trình tạo Spring context, binding và validation mà không cần khởi động toàn bộ ứng dụng. Mỗi test tạo một context nhỏ với cấu hình được chọn, kiểm tra bean và đóng context sau khi callback hoàn tất. Cách này phù hợp để xác minh contract cấu hình của một component trước khi kiểm thử tích hợp Config Server hoặc triển khai thật.

## 1. ApplicationContextRunner giải quyết vấn đề gì?

`ApplicationContextRunner` thuộc Spring Boot Test. Nó tạo một `ApplicationContext` tối giản, cho phép thêm configuration class, auto-configuration và property values riêng cho từng test.

Một test thường thực hiện các bước:

1. Đăng ký configuration class có `@EnableConfigurationProperties` hoặc component cần kiểm thử.
2. Thêm property values bằng `withPropertyValues(...)`.
3. Gọi `run(...)` để Spring tạo context và bind cấu hình.
4. Kiểm tra context khởi động thành công hay thất bại.
5. Lấy bean và assert giá trị đã bind hoặc nguyên nhân validation.

So với `@SpringBootTest`, runner nhẹ hơn vì không tự khởi động toàn bộ application, web server hoặc mọi thành phần tích hợp. Mỗi test có thể tạo một bộ property values khác nhau mà không phải sửa file cấu hình dùng chung.

| Công cụ | Phạm vi phù hợp |
| --- | --- |
| `ApplicationContextRunner` | Binding, validation, conditional bean và cấu hình của một nhóm component |
| `WebApplicationContextRunner` | Kiểm thử cấu hình trong web application context |
| `@SpringBootTest` | Kiểm thử tích hợp rộng hơn với application context thực tế |
| Testcontainers/HTTP test | Kiểm tra tương tác với Config Server, Git, Vault hoặc dịch vụ bên ngoài |

## 2. Thêm dependency kiểm thử

Với Maven, dùng `spring-boot-starter-test` trong scope test. Nếu cần Jakarta Bean Validation, thêm `spring-boot-starter-validation` để có API và provider validation.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

Với Gradle:

```kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
```

Các phiên bản dependency nên được quản lý bởi Spring Boot BOM/plugin của dự án. Không tự thêm một phiên bản Spring Framework hoặc Hibernate Validator khác dòng với phiên bản Spring Boot đang dùng.

Với Spring Boot 3.x, các constraint được import từ `jakarta.validation.constraints`:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
```

Các dự án Spring Boot 2.x dùng namespace `javax.validation.constraints`. Không trộn hai namespace trong cùng một ứng dụng; chọn package theo phiên bản Spring Boot và validator đang dùng.

## 3. Khai báo lớp cấu hình cần kiểm thử

Giả sử dịch vụ `billing-api` cần endpoint, số lần retry, timeout và một số endpoint nhà cung cấp. Ta định nghĩa một lớp `@ConfigurationProperties`:

```java
@ConfigurationProperties(prefix = "acme.billing", ignoreUnknownFields = false)
@Validated
public class BillingProperties {

    @NotBlank
    private String endpoint;

    @Min(1)
    private int maxAttempts = 3;

    @NotNull
    private Duration connectTimeout = Duration.ofSeconds(2);

    private Map<String, URI> providerEndpoints = new LinkedHashMap<>();

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Map<String, URI> getProviderEndpoints() {
        return providerEndpoints;
    }

    public void setProviderEndpoints(Map<String, URI> providerEndpoints) {
        this.providerEndpoints = providerEndpoints;
    }
}
```

Các annotation quan trọng:

- `@ConfigurationProperties(prefix = "acme.billing")` gom các property cùng namespace vào một object.
- `@Validated` yêu cầu Spring áp dụng Bean Validation khi bind.
- `@NotBlank` yêu cầu endpoint có nội dung.
- `@Min(1)` ngăn số lần retry bằng 0 hoặc âm.
- `@NotNull` ngăn timeout bị null.
- `ignoreUnknownFields = false` yêu cầu binder báo lỗi nếu có property không được ánh xạ vào lớp cấu hình.

Các field có giá trị khởi tạo cung cấp default khi property không xuất hiện. Default phải có ý nghĩa vận hành an toàn; không đặt giá trị giả cho một endpoint hoặc credential bắt buộc chỉ để ứng dụng khởi động được.

## 4. Đăng ký configuration class trong runner

`@ConfigurationProperties` chỉ mô tả cách bind. Bean vẫn phải được đăng ký trong context test. Có thể dùng `@EnableConfigurationProperties`:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(BillingProperties.class)
class BillingPropertiesConfiguration {
}
```

Sau đó tạo runner dùng configuration class này:

```java
class BillingPropertiesTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BillingPropertiesConfiguration.class)
                    .withConfiguration(AutoConfigurations.of(
                            ValidationAutoConfiguration.class));
}
```

`ValidationAutoConfiguration` đăng ký validator theo cơ chế Spring Boot khi validation provider có mặt. Nếu dự án đã cung cấp `Validator` bean riêng, hãy cấu hình runner để dùng đúng validator đó.

Các import chính trong test:

```java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
```

Runner được khai báo một lần làm fixture; mỗi lần gọi `run` vẫn tạo context riêng. Không giữ bean lấy từ callback để sử dụng sau khi callback kết thúc vì context đã được đóng.

## 5. Kiểm thử binding giá trị hợp lệ

`withPropertyValues` nhận các chuỗi theo dạng `key=value`. Test có thể xác minh relaxed binding, chuyển đổi kiểu và map binding:

```java
@Test
void bindsPropertiesFromEnvironment() {
    contextRunner
            .withPropertyValues(
                    "acme.billing.endpoint=https://billing.internal",
                    "acme.billing.max-attempts=5",
                    "acme.billing.connect-timeout=750ms",
                    "acme.billing.provider-endpoints.fast=https://fast.internal")
            .run(context -> {
                assertThat(context).hasNotFailed();

                BillingProperties properties =
                        context.getBean(BillingProperties.class);

                assertThat(properties.getEndpoint())
                        .isEqualTo("https://billing.internal");
                assertThat(properties.getMaxAttempts()).isEqualTo(5);
                assertThat(properties.getConnectTimeout())
                        .isEqualTo(Duration.ofMillis(750));
                assertThat(properties.getProviderEndpoints())
                        .containsEntry("fast", URI.create("https://fast.internal"));
            });
}
```

Test này xác nhận:

- Property prefix được ánh xạ đúng.
- `max-attempts` được bind vào field `maxAttempts` theo relaxed binding.
- Chuỗi `750ms` được chuyển thành `Duration`.
- Key con `provider-endpoints.fast` được bind thành entry của map.
- Bean được đăng ký và có thể lấy từ context.

Nên assert từng giá trị quan trọng. Chỉ kiểm tra context không lỗi chưa đủ để chứng minh property đã bind đúng; property có thể bị bỏ qua nếu tên sai và `ignoreUnknownFields` vẫn đang bật.

## 6. Kiểm thử giá trị mặc định

Khi property không được cung cấp, binder giữ default khai báo trong lớp cấu hình. Test nên chứng minh default đúng với contract:

```java
@Test
void usesSafeDefaultsWhenOptionalPropertiesAreMissing() {
    contextRunner
            .withPropertyValues(
                    "acme.billing.endpoint=https://billing.internal")
            .run(context -> {
                assertThat(context).hasNotFailed();

                BillingProperties properties =
                        context.getBean(BillingProperties.class);

                assertThat(properties.getMaxAttempts()).isEqualTo(3);
                assertThat(properties.getConnectTimeout())
                        .isEqualTo(Duration.ofSeconds(2));
                assertThat(properties.getProviderEndpoints()).isEmpty();
            });
}
```

Test này chỉ bỏ các property có default. `endpoint` vẫn được cung cấp vì lớp cấu hình đánh dấu nó là bắt buộc. Nếu default thay đổi, test sẽ phát hiện thay đổi contract ngoài dự kiến.

Không dùng default để che giấu cấu hình bắt buộc bị thiếu. Ví dụ database URL, signing key hoặc credential cần được xử lý theo policy fail-fast hoặc secret management riêng.

## 7. Kiểm thử validation khi giá trị không hợp lệ

Một cấu hình sai cần làm context startup thất bại. Ví dụ `max-attempts=0` vi phạm `@Min(1)`:

```java
@Test
void rejectsInvalidRetryCount() {
    contextRunner
            .withPropertyValues(
                    "acme.billing.endpoint=https://billing.internal",
                    "acme.billing.max-attempts=0")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining(
                                "must be greater than or equal to 1");
            });
}
```

Tương tự, `endpoint` rỗng phải bị từ chối bởi `@NotBlank`:

```java
@Test
void rejectsBlankEndpoint() {
    contextRunner
            .withPropertyValues("acme.billing.endpoint=   ")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("must not be blank");
            });
}
```

Thông báo validation mặc định có thể thay đổi theo provider hoặc locale. Nếu dự án dùng message bundle riêng, hãy assert thông điệp theo contract của dự án hoặc kiểm tra root cause/constraint violation thay vì phụ thuộc toàn bộ stack trace.

## 8. Kiểm thử property bắt buộc bị thiếu

Với `@NotBlank`, endpoint không được cung cấp cũng làm validation thất bại:

```java
@Test
void rejectsMissingRequiredEndpoint() {
    contextRunner
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("endpoint");
            });
}
```

Phân biệt hai trường hợp:

- **Missing:** property không có trong bất kỳ nguồn nào.
- **Blank:** property tồn tại nhưng là chuỗi rỗng hoặc chỉ có khoảng trắng.

`@NotNull`, `@NotEmpty` và `@NotBlank` có ngữ nghĩa khác nhau. Chọn annotation theo kiểu dữ liệu và yêu cầu nghiệp vụ. Với collection, `@NotEmpty` kiểm tra collection không rỗng; với chuỗi, `@NotBlank` còn loại cả chuỗi chỉ có whitespace.

## 9. Kiểm thử lỗi chuyển đổi kiểu

Binder cần chuyển chuỗi từ `Environment` sang kiểu Java. Một giá trị không đúng định dạng phải làm binding thất bại thay vì âm thầm tạo ra cấu hình sai.

Ví dụ timeout cần là `Duration` hợp lệ:

```java
@Test
void rejectsMalformedDuration() {
    contextRunner
            .withPropertyValues(
                    "acme.billing.endpoint=https://billing.internal",
                    "acme.billing.connect-timeout=not-a-duration")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("connect-timeout");
            });
}
```

Spring Boot hỗ trợ chuyển đổi các dạng `Duration` như `10s`, `500ms` hoặc giá trị số theo đơn vị mặc định được quy định. Nên dùng suffix rõ ràng để người đọc không phải suy luận đơn vị.

Tương tự, kiểm thử URI, enum, `DataSize`, boolean và số nguyên ở cả giá trị hợp lệ lẫn không hợp lệ nếu các kiểu này ảnh hưởng trực tiếp tới hành vi hệ thống.

## 10. Kiểm thử typo và unknown fields

Một lỗi thường gặp là viết sai tên property:

```text
acme.billing.max-attemps=5
```

Tên đúng là `max-attempts`. Nếu `ignoreUnknownFields` để mặc định `true`, property sai có thể bị bỏ qua và field giữ default, khiến test chỉ kiểm tra context thành công không phát hiện lỗi.

Đặt `ignoreUnknownFields = false` để yêu cầu binder báo lỗi khi có property không được ánh xạ. Sau đó kiểm thử một property viết sai:

```java
@Test
void rejectsUnknownPropertyNames() {
    contextRunner
            .withPropertyValues(
                    "acme.billing.endpoint=https://billing.internal",
                    "acme.billing.max-attemps=5")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("max-attemps");
            });
}
```

Chính sách từ chối unknown field hữu ích với namespace do một nhóm sở hữu rõ ràng. Tuy nhiên, nếu cùng prefix chứa property được mở rộng bởi module khác, cần xác định ranh giới binding phù hợp để không từ chối hợp lệ các thuộc tính của component khác.

## 11. Kiểm thử nested properties và validation lồng nhau

Với cấu hình lồng nhau, cần dùng `@Valid` ở field cha để kích hoạt validation trên object con. Ví dụ:

```java
@ConfigurationProperties(prefix = "acme.billing")
@Validated
public class BillingProperties {

    @NotBlank
    private String endpoint;

    @Valid
    private Retry retry = new Retry();

    public static class Retry {
        @Min(1)
        private int maxAttempts = 3;

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }
    }

    // Getter/setter cho endpoint và retry được khai báo tương ứng.
}
```

Property tương ứng:

```yaml
acme:
  billing:
    endpoint: https://billing.internal
    retry:
      max-attempts: 4
```

Test cần xác nhận cả binding đúng `retry.max-attempts` và validation khi giá trị bằng 0. Nếu thiếu `@Valid`, constraint trên object con có thể không được cascade theo cách mong đợi.

## 12. Kiểm thử conditional configuration

Một số bean chỉ được tạo khi property bật:

```java
@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "acme.payment",
            name = "enabled",
            havingValue = "true")
    PaymentClient paymentClient() {
        return new PaymentClient();
    }
}
```

Có thể dùng cùng `ApplicationContextRunner` để kiểm tra hai nhánh:

```java
private final ApplicationContextRunner paymentRunner =
        new ApplicationContextRunner()
                .withUserConfiguration(PaymentClientConfiguration.class);

@Test
void createsClientWhenEnabled() {
    paymentRunner.withPropertyValues("acme.payment.enabled=true")
            .run(context -> assertThat(context)
                    .hasSingleBean(PaymentClient.class));
}

@Test
void doesNotCreateClientWhenDisabled() {
    paymentRunner.withPropertyValues("acme.payment.enabled=false")
            .run(context -> assertThat(context)
                    .doesNotHaveBean(PaymentClient.class));
}
```

Đây là một ví dụ quan trọng với Config Client: property có thể được nạp đúng nhưng conditional bean vẫn không được tạo nếu tên, giá trị hoặc `havingValue` không khớp.

## 13. Tách test binding khỏi test Config Server

`ApplicationContextRunner.withPropertyValues(...)` đưa property trực tiếp vào test context. Nó **không tự đọc `application.yml`, không kết nối Config Server, không clone Git và không xác minh TLS/authentication**.

Nên chia kiểm thử thành các tầng:

| Tầng | Mục tiêu | Công cụ phù hợp |
| --- | --- | --- |
| Unit/binding test | Kiểm tra type conversion, default và validation | `ApplicationContextRunner` |
| Auto-configuration test | Kiểm tra bean conditional và cấu hình module | `ApplicationContextRunner` + `AutoConfigurations` |
| Config Data test | Kiểm tra import location, profile và property source | Test context có `ConfigDataApplicationContextInitializer` hoặc Spring Boot test phù hợp |
| Config Server integration | Kiểm tra endpoint, application/profile/label và response | `@SpringBootTest`, HTTP test hoặc Testcontainers |
| End-to-end | Kiểm tra client khởi động, bind và hành vi với backend thật | Môi trường integration/staging |

Không nên mock Config Server trong test binding rồi kết luận tích hợp Config Server đã hoạt động. Ngược lại, không cần khởi động Git server hoặc Config Server thật cho mọi test nhỏ về `@Min`, `@NotBlank` hay conversion `Duration`.

## 14. Kiểm thử thứ tự ưu tiên của property source

Binding test có thể kiểm tra giá trị cuối cùng sau khi nhiều nguồn cung cấp cùng một property. Ví dụ, tạo hai property source trong environment initializer:

```java
private final ApplicationContextRunner precedenceRunner =
        new ApplicationContextRunner()
                .withInitializer(context -> context.getEnvironment()
                        .getPropertySources()
                        .addFirst(new MapPropertySource(
                                "test-override",
                                Collections.<String, Object>singletonMap(
                                        "acme.billing.max-attempts", "7"))))
                .withUserConfiguration(BillingPropertiesConfiguration.class);
```

Sau đó cung cấp một giá trị khác bằng `withPropertyValues` và kiểm tra giá trị nào được bind. `addFirst` đặt property source test lên trước các nguồn còn lại. Test như vậy giúp xác nhận component đọc giá trị đã phân giải từ `Environment`, nhưng không chứng minh thứ tự của Config Server property source trong một deployment thật; phần đó cần Config Data/integration test riêng.

Không tạo test phụ thuộc thứ tự nội bộ không được cam kết của framework. Hãy kiểm tra thứ tự bằng API `PropertySources` hoặc dùng initializer có chủ đích như ví dụ để kiểm soát fixture.

## 15. Kiểm tra lỗi startup và nguyên nhân gốc

Khi binding hoặc validation thất bại, context runner vẫn gọi callback với context có startup failure. Test cần kiểm tra context thất bại và thông tin nguyên nhân đủ cụ thể.

Một số loại lỗi thường gặp:

| Loại lỗi | Nguyên nhân |
| --- | --- |
| `BindException` | Binder không thể bind hoặc chuyển đổi property |
| `BindValidationException` | Giá trị bind được nhưng vi phạm constraint validation |
| Unknown/unbound property error | Có key không được ánh xạ khi `ignoreUnknownFields=false` |
| Bean creation failure | Configuration class hoặc bean phụ thuộc bị lỗi khi khởi tạo |
| Missing bean | Chưa đăng ký `@ConfigurationProperties` hoặc conditional không thỏa |

Không nên assert toàn bộ stack trace vì nó thay đổi giữa phiên bản Spring Boot và validator. Ưu tiên kiểm tra loại lỗi, tên property hoặc constraint message ổn định theo contract của ứng dụng.

## 16. Tổ chức test để tránh rò rỉ trạng thái

Mỗi lần `run` tạo và đóng một context. Để test độc lập:

- Khai báo property values ngay trong test, không sửa file YAML dùng chung.
- Không dùng static mutable bean hoặc cache chia sẻ giữa các context.
- Không lưu bean sau khi callback kết thúc.
- Dùng một runner fixture bất biến và tạo biến thể bằng `withPropertyValues`/`withUserConfiguration`.
- Không gọi mạng trong test binding; thay dependency bên ngoài bằng stub nếu cần kiểm tra bean wiring.
- Nếu test dùng system property hoặc environment variable thật, khôi phục trạng thái sau test và tránh chạy song song gây xung đột.

## 17. Checklist cho bộ kiểm thử configuration properties

- [ ] Đăng ký `@ConfigurationProperties` bean rõ ràng trong runner.
- [ ] Có validation provider và `ValidationAutoConfiguration` khi kiểm thử Bean Validation.
- [ ] Kiểm tra binding giá trị hợp lệ.
- [ ] Kiểm tra default của property tùy chọn.
- [ ] Kiểm tra property bắt buộc bị thiếu.
- [ ] Kiểm tra chuỗi rỗng/blank và constraint số.
- [ ] Kiểm tra conversion `Duration`, `DataSize`, URI, enum hoặc kiểu được sử dụng.
- [ ] Kiểm tra nested properties với cascade `@Valid`.
- [ ] Kiểm tra map/list và relaxed binding nếu component sử dụng.
- [ ] Kiểm tra unknown fields để phát hiện typo nếu policy yêu cầu.
- [ ] Kiểm tra conditional bean cho cả trạng thái bật và tắt.
- [ ] Kiểm tra property source precedence bằng fixture có chủ đích.
- [ ] Tách binding test khỏi Config Server/Git/HTTP integration test.
- [ ] Kiểm tra failure cause đủ cụ thể nhưng không phụ thuộc toàn bộ stack trace.

## 18. Tài liệu tham khảo

- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `ApplicationContextRunner` và kiểm thử auto-configuration.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): `@ConfigurationProperties`, binding, conversion và validation.
- [Spring Boot — Configuration Metadata](https://docs.spring.io/spring-boot/specification/configuration-metadata/index.html): metadata cho property để hỗ trợ IDE và người vận hành.

`ApplicationContextRunner` giúp kiểm tra nhanh và cô lập contract cấu hình của từng component: property nào được bind, default nào được dùng, giá trị nào bị từ chối và bean nào được tạo. Kết hợp các test thành công, thất bại và conditional với integration test riêng cho Config Data/Config Server sẽ tạo một bộ kiểm thử nhiều tầng, phát hiện lỗi cấu hình sớm mà không làm mọi test phụ thuộc vào hạ tầng bên ngoài.
