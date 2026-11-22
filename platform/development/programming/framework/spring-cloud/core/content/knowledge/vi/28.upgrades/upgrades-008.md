# Kiểm thử hồi quy thứ tự nguồn cấu hình và endpoint quản trị

Khi nâng cấp Spring Boot hoặc Spring Cloud, ứng dụng có thể vẫn khởi động bình thường nhưng đọc một giá trị cấu hình từ nguồn khác trước đây. Một property có thể đổi ưu tiên giữa file nội bộ, biến môi trường, Config Server, Config Data import, bootstrap legacy hoặc test property source. Endpoint quản trị cũng có thể đổi điều kiện bật, đường dẫn, quyền truy cập, cách sanitization hoặc cấu trúc phản hồi.

Vì vậy, kiểm thử hồi quy sau nâng cấp cần xác nhận hai hợp đồng: **giá trị nào thực sự thắng khi nhiều nguồn cùng khai báo một key**, và **endpoint quản trị nào còn được expose, đọc hoặc thay đổi cấu hình theo đúng quyền**. Không nên chỉ kiểm tra ứng dụng có start được hay không.

Bài học thuộc chương **Nâng cấp** của module **SPRING_CLOUD_CORE**. Ta sẽ xây dựng bộ kiểm thử cho Spring Environment, Config Data, bootstrap legacy, remote property source, `@ConfigurationProperties`, Actuator `env`/`configprops`/`refresh` và Spring Cloud Commons `serviceregistry`; sau đó tổ chức ma trận phiên bản và checklist CI để phát hiện thay đổi hành vi trước khi phát hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xây dựng ma trận nguồn cấu hình và thứ tự ưu tiên cần giữ sau nâng cấp.
- Kiểm tra giá trị hiệu lực bằng `Environment` và `MutablePropertySources`.
- Phân biệt thứ tự nguồn ở Spring Boot với thứ tự remote property source do Spring Cloud Config quản lý.
- Kiểm thử Config Data qua `spring.config.import` và bootstrap legacy riêng biệt.
- Dùng `MockEnvironment`, `TestPropertyValues` và `ApplicationContextRunner` cho unit/context test.
- Dùng integration test để xác minh `@ConfigurationProperties` nhận đúng giá trị.
- Kiểm thử các endpoint `env`, `configprops`, `refresh` và `serviceregistry`.
- Kiểm tra endpoint exposure, management base path, authentication, authorization và sanitization.
- Phân biệt lỗi cấu hình, lỗi endpoint contract và lỗi do test override property.
- Tổ chức kiểm thử trên các cặp Spring Boot/Spring Cloud được hỗ trợ.
- Tạo baseline regression có thể so sánh trước và sau khi nâng cấp.

## 2. Vì sao cần kiểm thử thứ tự nguồn cấu hình?

Một key có thể xuất hiện ở nhiều nguồn. Ví dụ `checkout.max-items` được khai báo trong file mặc định, file profile `production`, biến môi trường và Config Server.

Nếu thứ tự nguồn thay đổi, ứng dụng có thể chạy với giá trị khác mà không có lỗi startup:

| Nguồn | Giá trị ví dụ | Mục đích |
| --- | --- | --- |
| `application.yml` | `20` | Giá trị mặc định |
| `application-production.yml` | `30` | Giá trị của profile |
| OS environment | `40` | Override ở môi trường triển khai |
| Config Server | `50` | Cấu hình từ xa |
| Command line | `60` | Override lúc chạy |

Kết quả cuối cùng phụ thuộc vào cách các nguồn được thêm vào `Environment`, cách Config Data import được xử lý và chính sách override của Spring Cloud Config. Chỉ nhìn file cấu hình không đủ để biết giá trị runtime.

### 2.1. Ba khái niệm phải tách riêng

| Khái niệm | Câu hỏi | Cách kiểm tra |
| --- | --- | --- |
| Source precedence | Nguồn nào thắng khi key trùng? | `Environment.getProperty()` và thứ tự `PropertySources` |
| Binding | Giá trị hiệu lực có được bind đúng kiểu vào bean? | `@ConfigurationProperties` và `Binder` |
| Management contract | Operator có thể quan sát hoặc thay đổi property qua endpoint không? | HTTP integration test, security test và Actuator |

Một test chỉ kiểm tra `Environment.getProperty()` chưa chứng minh bean đã rebind. Một test chỉ gọi `/actuator/env` cũng chưa chứng minh `@ConfigurationProperties` đang dùng đúng giá trị.

## 3. Thứ tự nguồn của Spring Boot

Spring Boot dùng danh sách `PropertySource` có thứ tự. Nguồn đứng trước có độ ưu tiên cao hơn khi resolver tìm một key; nguồn có ưu tiên cao hơn sẽ quyết định giá trị nếu cùng key xuất hiện ở nhiều nơi.

Trong tài liệu Spring Boot hiện hành, các nhóm nguồn chính được xếp từ ưu tiên thấp lên cao như sau:

1. Default properties do `SpringApplication.setDefaultProperties(...)` cung cấp.
2. `@PropertySource` trên các configuration class.
3. Config Data như `application.properties`, `application.yml` và file profile.
4. `RandomValuePropertySource`.
5. OS environment variables.
6. Java system properties.
7. JNDI và servlet context/config parameters trong web application tương ứng.
8. `SPRING_APPLICATION_JSON`.
9. Command-line arguments.
10. Test properties do Spring Boot/Spring Test thêm vào, gồm các cơ chế test-specific.

Các test-specific property source có thứ tự riêng; `@DynamicPropertySource` có độ ưu tiên cao hơn `@TestPropertySource`. Giá trị inline của `@TestPropertySource` cao hơn giá trị đọc từ resource location của chính annotation đó.

Danh sách trên là mô hình khái quát của Spring Boot. Khi nâng cấp, hãy đối chiếu tài liệu của phiên bản đích vì thứ tự và các loại nguồn có thể thay đổi theo thế hệ framework hoặc loại application.

### 3.1. Config Data có thứ tự nội bộ

Trong nhóm Config Data, cần kiểm tra:

- File mặc định trong classpath.
- File profile-specific như `application-production.yml`.
- File ngoài JAR và file profile-specific ngoài JAR.
- Các location được chỉ định bằng `spring.config.location`.
- Các location bổ sung bằng `spring.config.additional-location`.
- Import từ `spring.config.import`.
- Thứ tự profile nếu nhiều profile cùng active.

File profile-specific có thể override file không gắn profile. Khi nhiều profile cùng active, profile được xử lý sau có thể override profile trước. Thứ tự location và location group cũng ảnh hưởng kết quả.

### 3.2. spring.config.import ảnh hưởng precedence

Import được xử lý khi Config Data được nạp. Nội dung import được đặt ngay dưới document khai báo import trong thứ tự property source; do đó giá trị từ import có thể override giá trị trong document đã khai báo nó. Nhiều import được xử lý theo thứ tự khai báo, import sau có thể có ưu tiên cao hơn.

Ví dụ:

~~~yaml
spring:
  config:
    import:
      - optional:file:./region.yml
      - optional:file:./service.yml

checkout:
  max-items: 20
~~~

Nếu `region.yml` và `service.yml` cùng khai báo `checkout.max-items`, test phải xác nhận đúng giá trị của import sau theo thứ tự thực tế mà ứng dụng sử dụng. Không giả định thứ tự chỉ dựa vào vị trí dòng trong file.

### 3.3. spring.config.location và additional-location không giống nhau

`spring.config.location` thay thế các vị trí Config Data mặc định. `spring.config.additional-location` thêm vị trí mới vào danh sách mặc định; các giá trị ở location bổ sung có thể override giá trị đã nạp trước đó.

Khi nâng cấp, cần có test cho cả hai nếu ứng dụng sử dụng chúng. Một thay đổi nhầm từ `additional-location` sang `location` có thể làm mất cấu hình đóng gói trong JAR.

## 4. Remote property source của Spring Cloud Config

Không nên gộp thứ tự remote configuration vào một quy tắc duy nhất. Spring Cloud Config hỗ trợ hai cách nạp phổ biến:

| Cơ chế | Cách bật | Đặc điểm |
| --- | --- | --- |
| Config Data | `spring.config.import=configserver:` | Cơ chế mặc định hiện đại; dùng Config Data resolver/loader |
| Legacy bootstrap | `spring-cloud-starter-bootstrap` hoặc `spring.cloud.bootstrap.enabled=true` | Tạo bootstrap context và thêm remote source qua bootstrap lifecycle |

Không bật cả hai cơ chế cho cùng một ứng dụng nếu không có thiết kế rõ ràng. Tài liệu Config Client quy định Config Data import là cách mặc định; bootstrap legacy cần được bật tường minh.

### 4.1. Kiểm thử Config Data import

Ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: configserver:http://localhost:8888
  cloud:
    config:
      label: release-2026
~~~

Trong test, chạy Config Server giả lập hoặc WireMock/MockWebServer để trả response có property source xác định. Không gọi Config Server production trong test hồi quy.

Test cần xác minh:

- Client gửi đúng application name.
- Profile và label được gửi đúng.
- Config Data resolver được gọi trong startup.
- Remote property source xuất hiện trong `Environment`.
- Giá trị remote và local tuân theo precedence mong đợi.
- Khi server unavailable, `optional:` và fail-fast cho kết quả khác nhau đúng thiết kế.
- Khi remote config kích hoạt profile, client nạp cấu hình profile tương ứng.

### 4.2. Kiểm thử bootstrap legacy

Nếu ứng dụng còn dùng bootstrap legacy, test cần bật bootstrap bằng test runtime dependency hoặc property hệ thống tương ứng. Đăng ký custom `PropertySourceLocator` trong `META-INF/spring.factories` của test nếu cần xác minh bootstrap extension.

Kiểm thử riêng:

- Bootstrap context có được tạo hay không.
- Remote source có xuất hiện trong main application Environment hay không.
- `PropertySourceLocator` được gọi với application name/profile nào.
- `spring.cloud.config.allowOverride`, `overrideNone` và `overrideSystemProperties` có hiệu lực theo metadata từ remote source hay không.
- Refresh/bootstrap lifecycle có còn đúng sau nâng cấp hay không.

Đừng dùng test của Config Data để kết luận bootstrap legacy hoạt động, hoặc ngược lại. Hai đường có lifecycle và cơ chế thêm property source khác nhau.

### 4.3. Remote override flags

Với bootstrap remote property source, các cờ override phải được kiểm tra từ đúng nơi:

| Property | Ý nghĩa |
| --- | --- |
| `spring.cloud.config.allowOverride` | Remote source cho phép local source override hay không |
| `spring.cloud.config.overrideNone` | Cho phép mọi local source override remote source |
| `spring.cloud.config.overrideSystemProperties` | Điều khiển quan hệ ưu tiên với system properties, command line và environment |

`allowOverride` phải được cấp bởi remote property source; đặt cờ này chỉ trong local application config không có tác dụng như một quyền override do server cấp.

Ví dụ ma trận cần kiểm thử:

| allowOverride | overrideNone | overrideSystemProperties | Điều cần xác minh |
| --- | --- | --- | --- |
| `false` | — | — | Local source không override remote source |
| `true` | `true` | — | Local source được ưu tiên hơn remote |
| `true` | `false` | `false` | System properties, command line và environment có thể override; local config file không được phép |
| `true` | `false` | `true` | Hành vi theo mặc định của remote override policy, phải xác nhận bằng integration test |

Không chỉ assert giá trị cuối. Hãy ghi rõ nguồn thắng để khi một release train thay đổi cách sắp xếp property source, nhóm nâng cấp có thể xác định nguyên nhân.

## 5. Thiết kế regression matrix

Một bộ test tốt cần bao phủ cả nguồn, profile, binding và endpoint. Bảng sau là ma trận gợi ý:

| Nhóm | Kịch bản | Kết quả cần giữ |
| --- | --- | --- |
| Config Data | Classpath default + profile | Profile override default |
| External files | Classpath + file ngoài JAR | File ngoài thắng khi được nạp sau |
| Import | Hai import cùng khai báo một key | Import có ưu tiên cao hơn thắng |
| OS environment | File + environment variable | Environment variable thắng theo Boot precedence |
| System property | Environment + `-D` | System property thắng environment |
| Command line | File + command line | Command line thắng |
| Test override | Application config + test properties | Test override thắng theo test framework |
| Dynamic property | Testcontainers URL + test properties | Dynamic property thắng `@TestPropertySource` |
| Config Server | Remote + local config | Đúng chính sách remote override |
| Profile | Default + nhiều active profiles | Giá trị đúng profile order |
| Binding | `Environment` + `@ConfigurationProperties` | Bean nhận đúng giá trị và kiểu |
| Actuator env | GET `/actuator/env` | Đúng key, source và sanitization |
| Actuator configprops | GET `/actuator/configprops` | Bean property đã bind đúng |
| Refresh | POST `/actuator/refresh` | Environment/refresh-scoped bean thay đổi theo thiết kế |
| Env mutation | POST `/actuator/env` | Chỉ key được phép thay đổi; bean rebind đúng |
| Service registry | GET/POST `/actuator/serviceregistry` | Status trả về và cập nhật theo provider |
| Security | Thiếu quyền/CSRF token | Request quản trị bị từ chối |

### 5.1. Chọn key kiểm thử

Không nên chỉ dùng key đơn giản `demo.value`. Hãy chọn key đại diện cho các kiểu dữ liệu và hành vi mà ứng dụng thực sự sử dụng:

- String: tên service hoặc endpoint URL.
- Integer/Duration: timeout, retry count, pool size.
- Boolean: feature flag.
- Enum: chế độ xử lý.
- List: danh sách origin hoặc endpoint.
- Map: cấu hình theo tenant/region.
- Nested object: cấu hình được bind vào `@ConfigurationProperties`.

Với list, cần kiểm tra semantics thay thế toàn bộ list khi một nguồn có ưu tiên cao hơn khai báo list khác. Với map, các entry khác key có thể được hợp nhất trong khi cùng key lấy giá trị từ nguồn có ưu tiên cao hơn.

## 6. Unit test thứ tự PropertySource

Với unit test, dùng `MockEnvironment` và thêm các `MapPropertySource` có tên rõ ràng. Cách này giúp kiểm tra cả giá trị hiệu lực lẫn nguồn thắng.

### 6.1. Kiểm tra addFirst và addLast

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PropertySourcePrecedenceTests {

    @Test
    void firstPropertySourceWinsWhenKeysOverlap() {
        MockEnvironment environment = new MockEnvironment();
        MutablePropertySources sources = environment.getPropertySources();

        sources.addLast(new MapPropertySource(
                "application-config",
                Map.of("checkout.max-items", "20")));
        sources.addLast(new MapPropertySource(
                "remote-config",
                Map.of("checkout.max-items", "50")));
        sources.addFirst(new MapPropertySource(
                "command-line",
                Map.of("checkout.max-items", "60")));

        assertThat(environment.getProperty("checkout.max-items"))
                .isEqualTo("60");
        assertThat(sources.iterator().next().getName())
                .isEqualTo("command-line");
    }

    @Test
    void removingHighestPrioritySourceRevealsNextValue() {
        MockEnvironment environment = new MockEnvironment();
        MutablePropertySources sources = environment.getPropertySources();

        sources.addFirst(new MapPropertySource(
                "remote-config",
                Map.of("checkout.max-items", "50")));
        sources.addLast(new MapPropertySource(
                "application-config",
                Map.of("checkout.max-items", "20")));

        assertThat(environment.getProperty("checkout.max-items"))
                .isEqualTo("50");

        sources.remove("remote-config");

        assertThat(environment.getProperty("checkout.max-items"))
                .isEqualTo("20");
    }
}
~~~

Test không phụ thuộc Config Server, web server hoặc bootstrap. Nó kiểm tra hợp đồng của Spring `Environment`: property source đầu tiên chứa key sẽ cung cấp giá trị hiệu lực.

### 6.2. Dùng TestPropertyValues để tạo fixture

`TestPropertyValues` giúp thêm nhiều cặp key/value vào environment:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.util.TestPropertyValues;
import org.springframework.mock.env.MockEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class TestPropertyValuesTests {

    @Test
    void appliesControlledPropertiesToEnvironment() {
        MockEnvironment environment = new MockEnvironment();

        TestPropertyValues.of(
                "spring.application.name=orders-service",
                "spring.profiles.active=staging",
                "checkout.max-items=25",
                "checkout.enabled=true")
                .applyTo(environment);

        assertThat(environment.getProperty("spring.application.name"))
                .isEqualTo("orders-service");
        assertThat(environment.getProperty("spring.profiles.active"))
                .isEqualTo("staging");
        assertThat(environment.getProperty("checkout.max-items", Integer.class))
                .isEqualTo(25);
    }
}
~~~

`TestPropertyValues` thích hợp cho fixture ngắn. Nếu test đang xác minh thứ tự nhiều nguồn, hãy thêm source tường minh bằng `MutablePropertySources.addFirst/addLast` để tránh phụ thuộc vào cách helper chọn vị trí source.

### 6.3. Kiểm thử test property source

Trong integration test, có thể dùng:

- `@SpringBootTest(properties = ...)` để truyền property vào test application.
- `@TestPropertySource` để nạp file hoặc inline properties.
- `@DynamicPropertySource` để đăng ký URL/port được tạo động, thường từ Testcontainers.

Dynamic properties có độ ưu tiên cao hơn `@TestPropertySource`. Inline properties của `@TestPropertySource` có độ ưu tiên cao hơn file được khai báo trong `locations`. Khi hai nguồn cùng khai báo một key, test phải assert giá trị thắng theo đúng thứ tự này.

Ví dụ:

~~~java
@SpringBootTest
@TestPropertySource(properties = "checkout.max-items=30")
class CheckoutConfigurationTests {

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("checkout.max-items", () -> "40");
    }

    @Autowired
    Environment environment;

    @Test
    void dynamicPropertyOverridesTestPropertySource() {
        assertThat(environment.getProperty("checkout.max-items", Integer.class))
                .isEqualTo(40);
    }
}
~~~

Ví dụ trên cần các import JUnit, Spring Test, `Environment`, `@Autowired` và AssertJ tương ứng. Không dùng `@DynamicPropertySource` để mô phỏng property tĩnh; chỉ dùng khi giá trị phụ thuộc tài nguyên có lifecycle bên ngoài context.

## 7. Kiểm thử binding bằng ApplicationContextRunner

`ApplicationContextRunner` cho phép khởi tạo một application context nhỏ với cấu hình và property có kiểm soát. Nó phù hợp để kiểm tra auto-configuration, conditional bean và binding mà không cần chạy toàn bộ ứng dụng.

### 7.1. Tạo configuration properties

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private int maxItems;
    private boolean enabled;
    private Duration requestTimeout = Duration.ofSeconds(2);

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

### 7.2. Kiểm tra giá trị đã bind

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CheckoutPropertiesBindingTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsEffectiveValuesWithExpectedTypes() {
        contextRunner
                .withPropertyValues(
                        "checkout.max-items=45",
                        "checkout.enabled=true",
                        "checkout.request-timeout=1500ms")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    CheckoutProperties properties =
                            context.getBean(CheckoutProperties.class);

                    assertThat(properties.getMaxItems()).isEqualTo(45);
                    assertThat(properties.isEnabled()).isTrue();
                    assertThat(properties.getRequestTimeout())
                            .isEqualTo(Duration.ofMillis(1500));
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(CheckoutProperties.class)
    static class TestConfiguration {
    }
}
~~~

Test này xác nhận binder chuyển string thành integer, boolean và duration. Khi nâng cấp Spring Boot, giữ test cho những converter hoặc custom `@ConfigurationPropertiesBinding` mà ứng dụng đang dùng.

### 7.3. Kiểm tra điều kiện bật bean

Nếu auto-configuration hoặc component phụ thuộc vào property, thêm test cho cả hai nhánh:

- Property không được khai báo: xác minh default và `matchIfMissing`.
- Property được bật/tắt tường minh: xác minh bean xuất hiện hoặc biến mất.

Không chỉ assert bean tồn tại. Hãy kiểm tra property source thắng để tránh một test property vô tình che mất cấu hình runtime.

## 8. Integration test Config Data và remote source

Unit test property source không kiểm tra Config Data resolver/loader. Cần thêm integration test khởi động Spring Boot với Config Server giả lập.

### 8.1. Dùng ConfigDataApplicationContextInitializer cho file Config Data

Nếu chỉ cần kiểm tra file `application.properties` được nạp vào `Environment`, có thể dùng `ConfigDataApplicationContextInitializer`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConfigDataInitializerTests {

    @Test
    void loadsConfigDataIntoEnvironment() {
        new ApplicationContextRunner()
                .withInitializer(new ConfigDataApplicationContextInitializer())
                .withUserConfiguration(TestConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getEnvironment()
                            .getProperty("checkout.max-items"))
                            .isEqualTo("25");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class TestConfiguration {
    }
}
~~~

Đặt fixture `application.properties` trong test classpath hoặc cấu hình location riêng cho runner. `ConfigDataApplicationContextInitializer` chỉ nạp Config Data vào Environment; nếu cần `@Value` placeholder processing, hãy dùng `@SpringBootTest` hoặc cấu hình `PropertySourcesPlaceholderConfigurer` phù hợp.

### 8.2. Kiểm thử Config Server qua HTTP giả lập

Một integration test đầy đủ có thể:

1. Khởi động WireMock hoặc MockWebServer trên port ngẫu nhiên.
2. Trả response Config Server cho application/profile/label cụ thể.
3. Đưa URL server vào `spring.config.import` bằng dynamic property.
4. Khởi động ứng dụng với profile test xác định.
5. Assert `Environment.getProperty()` và bean `@ConfigurationProperties`.
6. Kiểm tra request mà Config Client gửi tới server.

Các trường hợp nên có:

| Trường hợp | Response giả lập | Assertion |
| --- | --- | --- |
| Config có sẵn | HTTP 200, property source hợp lệ | Remote key xuất hiện |
| Optional server unavailable | Connection refused hoặc timeout | App tiếp tục startup nếu import optional |
| Required server unavailable | Connection refused hoặc timeout | Startup fail |
| Unauthorized | HTTP 401 | App fail hoặc thử URL khác theo cấu hình |
| Profile activation | Default response kích hoạt profile | Có request/response profile bổ sung |
| Label thay đổi | Trả cấu hình theo label | Giá trị đúng label được chọn |
| Remote/local collision | Cả hai nguồn cùng khai báo key | Giá trị thắng đúng precedence đã cam kết |

Không assert số request tuyệt đối nếu Config Data resolver có thể gọi server nhiều lần để xác định active profiles. Assert nội dung request và kết quả cuối thay vì giả định chỉ có một lần fetch.

## 9. Kiểm thử hợp đồng endpoint quản trị

Endpoint quản trị là API vận hành. Sau nâng cấp, cần xác nhận endpoint còn được bật, mapping đúng, trả dữ liệu đúng và chỉ cho phép caller có quyền thực hiện thao tác thay đổi cấu hình.

### 9.1. Phân biệt endpoint access và exposure

Actuator endpoint chỉ truy cập được khi endpoint được phép hoạt động và được expose qua HTTP hoặc JMX. Hai cấu hình cần được kiểm tra riêng:

- `management.endpoints.web.exposure.include/exclude`: endpoint nào được map ra HTTP.
- `management.endpoint.<id>.access`: endpoint có được phép truy cập theo access policy hay không (tùy phiên bản Spring Boot).

Ví dụ test profile:

~~~yaml
management:
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include:
          - health
          - info
          - env
          - configprops
          - refresh
          - serviceregistry
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Chỉ dùng cấu hình exposure này trong test hoặc management network được bảo vệ. Không expose `env`, `configprops`, `refresh` hay `serviceregistry` công khai chỉ để làm test pass.

### 9.2. Ma trận endpoint

| Endpoint | Method | Điều kiện chính | Assertion hồi quy |
| --- | --- | --- | --- |
| `/actuator/env` | GET | Actuator `env` được expose | Có key/source cần kiểm tra; giá trị nhạy cảm được mask |
| `/actuator/env` | POST | Spring Cloud Context env POST được bật và key nằm trong allowlist | Key hợp lệ cập nhật được; key ngoài allowlist bị từ chối |
| `/actuator/configprops` | GET | Actuator `configprops` được expose | Prefix và bean được bind có mặt; secret được mask |
| `/actuator/refresh` | POST | Spring Cloud Context refresh endpoint được expose | Environment được refresh và bean refresh scope được invalidated |
| `/actuator/serviceregistry` | GET | Có `Registration` bean và endpoint được expose | Trả status của registration |
| `/actuator/serviceregistry` | POST | Có `Registration` bean và status hợp lệ của provider | Registry nhận status mới |

Không phải mọi ứng dụng đều cần tất cả endpoint. Regression suite chỉ nên kiểm tra endpoint nằm trong operational contract của ứng dụng.

### 9.3. Kiểm thử GET env và configprops

Ví dụ dùng MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,env,configprops",
        "management.endpoint.env.show-values=never",
        "management.endpoint.configprops.show-values=never",
        "checkout.max-items=45",
        "checkout.api-token=synthetic-secret"
})
@AutoConfigureMockMvc
class ConfigurationActuatorReadTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void envEndpointExposesKeyMetadataButMasksSecret() throws Exception {
        mockMvc.perform(get("/actuator/env"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("checkout.max-items")))
                .andExpect(content().string(
                        containsString("checkout.api-token")))
                .andExpect(content().string(
                        containsString("******")));
    }

    @Test
    void configpropsEndpointShowsBoundConfigurationAndMasksSecret()
            throws Exception {
        mockMvc.perform(get("/actuator/configprops"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("checkout")))
                .andExpect(content().string(
                        containsString("******")));
    }
}
~~~

Các assertion chuỗi ở đây tránh khóa test vào toàn bộ JSON layout của Actuator. Với ứng dụng có JSON contract cụ thể, dùng JSONPath cho field ổn định mà ứng dụng thực sự phụ thuộc. Không snapshot toàn bộ response vì cấu trúc metadata có thể mở rộng giữa các phiên bản.

Nếu endpoint được map dưới management base path khác hoặc management port riêng, test phải dùng đúng URL/port thực tế. `MockMvc` phù hợp khi management endpoint chạy trong web application context được mock; dùng `RANDOM_PORT` và HTTP client thật nếu cần kiểm tra management server riêng.

Để `/actuator/configprops` có dữ liệu của `checkout`, test application context phải đăng ký bean `CheckoutProperties` bằng `@EnableConfigurationProperties` hoặc component scan như ứng dụng thật.

### 9.4. Kiểm thử POST env

Spring Cloud Context hỗ trợ POST vào `/actuator/env` để cập nhật property, rebind `@ConfigurationProperties` và thay đổi log level. Endpoint cần được bật rõ ràng và giới hạn key bằng regex.

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: "^(checkout\\.(enabled|max-items))$"
~~~

Test phải xác minh:

- POST với `checkout.enabled` hoặc `checkout.max-items` được chấp nhận.
- POST với key như `spring.datasource.password` bị từ chối.
- Bean `@ConfigurationProperties` nhận giá trị mới theo cơ chế rebind.
- Key không hợp lệ không làm thay đổi Environment.
- Request không có quyền quản trị bị từ chối.

Ví dụ request:

~~~http
POST /actuator/env
Content-Type: application/json

{
  "name": "checkout.max-items",
  "value": "55"
}
~~~

Không bật POST env trong production nếu không có use case quản trị cụ thể, key allowlist và authorization phù hợp. Khi test chỉ cần GET, không bật POST.

### 9.5. Kiểm thử POST refresh

Spring Cloud Context cung cấp `/actuator/refresh` để refresh Environment/bootstrap property sources và invalidate bean `@RefreshScope`. Endpoint này khác với POST `/actuator/env`: một endpoint cập nhật property được gửi trực tiếp, endpoint còn lại yêu cầu cơ chế refresh cấu hình của ứng dụng.

Test hồi quy nên:

1. Khởi động ứng dụng với property ban đầu.
2. Dùng config source giả trả giá trị mới.
3. Gọi POST `/actuator/refresh`.
4. Assert changed keys nếu response contract của phiên bản cung cấp.
5. Đọc Environment và bean `@ConfigurationProperties`.
6. Truy cập bean `@RefreshScope` và xác minh target mới dùng giá trị mới.

Không giả định endpoint refresh luôn tồn tại trong mọi ứng dụng. Nó phụ thuộc Spring Cloud Context và exposure. Nếu ứng dụng chuyển từ bootstrap legacy sang Config Data, cần xác minh refresh behavior bằng integration test trên đúng cơ chế đang dùng.

### 9.6. Kiểm thử service registry endpoint

Spring Cloud Commons cung cấp `/actuator/serviceregistry`. GET trả status registration; POST cập nhật status của registration hiện tại. Endpoint cần có `Registration` bean và status được hỗ trợ bởi provider.

Ví dụ test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties =
        "management.endpoints.web.exposure.include=health,serviceregistry")
@AutoConfigureMockMvc
class ServiceRegistryEndpointTests {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void registryStatusCanBeReadAndUpdated() throws Exception {
        mockMvc.perform(get("/actuator/serviceregistry"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("UP")));

        mockMvc.perform(post("/actuator/serviceregistry")
                        .contentType("application/json")
                        .content("{\"status\":\"OUT_OF_SERVICE\"}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/actuator/serviceregistry"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("OUT_OF_SERVICE")));
    }
}
~~~

Ví dụ trên giả định test context đã cấu hình một registration có status ban đầu là `UP` và registry provider hỗ trợ `OUT_OF_SERVICE`, chẳng hạn Eureka. Với Consul, Zookeeper hoặc custom registry, dùng status và semantics do implementation cung cấp. Để kiểm tra logic độc lập với provider, inject `ServiceRegistry` fake và assert `setStatus` được gọi với registration tương ứng.

## 10. Kiểm thử security và sanitization

Endpoint quản trị có thể đọc thông tin nhạy cảm hoặc thay đổi hành vi runtime. Vì vậy, kiểm thử endpoint phải bao gồm cả positive và negative authorization.

### 10.1. Security matrix

| Caller | GET env/configprops | POST env/refresh | POST serviceregistry |
| --- | --- | --- | --- |
| Không xác thực | Theo policy: thường bị từ chối khi có security | Bị từ chối | Bị từ chối |
| Read-only operator | Được đọc metadata đã sanitize | Bị từ chối | Bị từ chối |
| Config operator | Được đọc | Chỉ được gọi nếu có quyền thay đổi config | Chỉ được gọi nếu có quyền thay đổi registry |
| Application identity | Chỉ endpoint cần cho health/monitoring | Không mặc định có quyền mutation | Không mặc định có quyền mutation |

Quyền thực tế do Spring Security và cấu hình Actuator của ứng dụng quyết định. Test phải kiểm tra role/authority thực tế thay vì chỉ xác minh HTTP 200.

### 10.2. Sanitization là một phần của contract

`/actuator/env` và `/actuator/configprops` có thể trả thông tin nhạy cảm. Với Spring Boot hiện hành, `show-values` có thể là `never`, `always` hoặc `when-authorized`; giữ mặc định `never` nếu không có nhu cầu rõ ràng.

Regression test nên dùng secret giả và xác minh:

- Tên key có thể được quan sát nếu policy cho phép.
- Giá trị secret không xuất hiện trong response khi `show-values=never`.
- `when-authorized` chỉ hiển thị giá trị với user có role được cấu hình.
- Custom `SanitizingFunction` tiếp tục được áp dụng sau nâng cấp.

Không dùng secret thật trong test fixture hoặc snapshot JSON.

### 10.3. CSRF và POST endpoint

Nếu Spring Security bật CSRF protection, POST endpoint quản trị có thể trả 403 khi thiếu CSRF token ngay cả khi user đã xác thực. Test cần phân biệt:

- 401: chưa xác thực.
- 403 do thiếu quyền.
- 403 do CSRF token không hợp lệ/thiếu.
- 400 do payload hoặc key không hợp lệ.
- 404 do endpoint không được expose hoặc path sai.

Với MockMvc, dùng request post có CSRF token cho test thành công và test riêng request thiếu token. Không tắt CSRF toàn bộ chỉ để một test endpoint pass; áp dụng policy phù hợp cho management network và authentication scheme.

## 11. Lập baseline trước khi nâng cấp

Regression test có giá trị nhất khi có baseline rõ ràng từ phiên bản đang chạy ổn định. Trước khi đổi BOM hoặc Spring Boot, hãy ghi lại những hành vi ứng dụng cam kết giữ:

- Giá trị hiệu lực của các key quan trọng.
- Property source thắng cho từng key.
- Active profiles và label của Config Server.
- Giá trị đã bind vào `@ConfigurationProperties`.
- Endpoint quản trị được expose và HTTP method được phép.
- Quyền cần thiết cho từng endpoint.
- Quy tắc sanitization.
- Hành vi refresh và service registry status.

### 11.1. Không snapshot toàn bộ Environment

Không nên lưu toàn bộ `/actuator/env` hoặc `/actuator/configprops` làm golden file. Response có thể chứa metadata nội bộ, thứ tự source, tên bean và trường bổ sung thay đổi giữa phiên bản.

Thay vào đó, tạo baseline có chọn lọc:

~~~yaml
configuration-contract:
  application: orders-service
  profile: production
  assertions:
    - key: checkout.max-items
      expected-value: "45"
      expected-source: systemEnvironment
    - key: checkout.enabled
      expected-value: "true"
      expected-source: configserver:orders-service
    - key: checkout.request-timeout
      expected-value: "1500ms"
      expected-source: application-production.yml
~~~

Đây là format tài liệu hóa do nhóm dự án tự định nghĩa, không phải format cấu hình Spring. Chỉ đưa key không nhạy cảm vào baseline. Nếu tên source có thể thay đổi do framework nội bộ, ưu tiên assert giá trị hiệu lực và source category thay vì khóa cứng chuỗi implementation detail.

### 11.2. Ghi nhận profile và label

Một giá trị có thể đúng ở `default` nhưng sai ở `production`. Baseline phải ghi:

- `spring.application.name`.
- Active profiles theo thứ tự.
- Config Server label/commit nếu sử dụng.
- Config Data locations/imports quan trọng.
- Các biến môi trường được phép override.

Nếu test không cố định profile, nó có thể vô tình chạy với profile `default` và bỏ qua lỗi chỉ xuất hiện ở production.

### 11.3. Chỉ so sánh dữ liệu ổn định

Nên assert:

- Key quan trọng có giá trị mong đợi.
- Source category phù hợp.
- Bean được bind đúng kiểu.
- Endpoint có HTTP status và quyền đúng.
- Secret được mask.

Tránh assert:

- Toàn bộ thứ tự của mọi property source nội bộ.
- Timestamp, random value hoặc metadata thay đổi theo lần chạy.
- Toàn bộ JSON response của Actuator.
- Tên bean/auto-configuration không phải API công khai.

## 12. Ma trận nâng cấp Spring Boot và Spring Cloud

Spring Cloud release train được thiết kế để tương thích với một dải Spring Boot nhất định. Khi nâng cấp, cần kiểm thử cặp phiên bản được quản lý bằng Spring Cloud BOM.

Ví dụ ma trận trong pipeline:

| Job | Spring Boot | Spring Cloud BOM | Mục đích |
| --- | --- | --- | --- |
| Baseline | Phiên bản đang production | Release train hiện tại | Xác nhận test contract hiện hành |
| Candidate | Phiên bản Boot đích | Release train tương thích | Kiểm tra thay đổi hành vi |
| Compatibility | Phiên bản Boot thấp nhất được hỗ trợ | Release train tương ứng | Phát hiện mất hỗ trợ nếu thư viện công bố dải tương thích |

Không tự ghép một Spring Boot version với release train không được hỗ trợ chỉ để CI chạy. Dùng BOM quản lý dependency versions thay vì override từng Spring Cloud module rời rạc.

### 12.1. Bật compatibility verifier trong test

Spring Cloud Commons có compatibility verifier để kiểm tra phiên bản Spring Boot. Có thể bật trong test/CI:

~~~yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
~~~

Verifier giúp phát hiện một số cặp phiên bản không tương thích khi context khởi động. Nó không thay thế regression test cho property precedence hoặc Actuator endpoint; ứng dụng vẫn có thể dùng cặp phiên bản được hỗ trợ nhưng thay đổi hành vi.

### 12.2. Chạy cùng bộ test trên hai BOM

Nếu build hỗ trợ matrix, hãy chạy cùng một suite trên:

- BOM đang dùng trong production.
- BOM candidate được chọn cho nâng cấp.

So sánh các assertion về effective values, source categories, bean binding và endpoint behavior. Khi có sai khác, phân loại:

1. Thay đổi có chủ ý trong framework.
2. Thay đổi do cấu hình hoặc dependency bị thiếu.
3. Test fixture đang override giá trị runtime.
4. Hành vi regression cần sửa hoặc rollback.

Không sửa expected value chỉ để làm CI xanh. Trước khi chấp nhận thay đổi, phải hiểu nguồn nào đang thắng và endpoint nào thay đổi contract.

## 13. Checklist CI sau nâng cấp

Một pipeline regression có thể chia thành các tầng:

| Tầng | Test | Tốc độ tương đối | Phụ thuộc |
| --- | --- | --- | --- |
| 1 | Unit test `MockEnvironment` và `MutablePropertySources` | Nhanh | Không |
| 2 | `ApplicationContextRunner` và configuration binding | Nhanh | Không |
| 3 | Config Data file/location/profile tests | Nhanh | Test resources |
| 4 | Config Server HTTP contract test | Trung bình | WireMock/MockWebServer |
| 5 | Actuator MockMvc tests | Trung bình | Application context |
| 6 | Management port/security integration tests | Trung bình | Web server/security |
| 7 | Provider integration test (Eureka/Consul) | Chậm hơn | Registry test container |
| 8 | Smoke test trên candidate image | Chậm | Môi trường staging |

### 13.1. Điều kiện pass

Candidate chỉ nên được chấp nhận khi:

- Mọi key trong baseline có giá trị hiệu lực đúng.
- Nguồn thắng đúng hoặc sai khác đã được giải thích và phê duyệt.
- `@ConfigurationProperties` bind đúng giá trị và kiểu.
- Config Data/Config Server/legacy bootstrap hoạt động theo đúng mode ứng dụng sử dụng.
- Endpoint quản trị có mapping, exposure và method đúng.
- Authorization và sanitization không bị nới lỏng ngoài ý muốn.
- POST endpoint không thể sửa key ngoài allowlist.
- Refresh và service registry test pass với provider thực tế.
- Compatibility verifier không báo cặp Boot/Cloud không tương thích.

### 13.2. Lưu report dễ so sánh

Mỗi job nên xuất một report ngắn:

~~~text
Spring Boot: 4.x.y
Spring Cloud BOM: 5.x.y
Config mode: config-data
Active profiles: production

Property precedence:
- checkout.max-items: PASS (systemEnvironment)
- checkout.enabled: PASS (configserver)
- checkout.request-timeout: PASS (application-production.yml)

Management endpoints:
- GET /actuator/env: PASS
- GET /actuator/configprops: PASS
- POST /actuator/env allowlisted key: PASS
- POST /actuator/env forbidden key: PASS
- POST /actuator/refresh: PASS
- GET/POST /actuator/serviceregistry: PASS

Security:
- unauthenticated management request: DENIED
- secret sanitization: PASS
~~~

Không ghi giá trị secret vào report. Source category và trạng thái assertion thường đủ để so sánh giữa các job.

## 14. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Giá trị khác sau nâng cấp nhưng startup pass | Thứ tự property source hoặc Config Data import thay đổi | Kiểm tra `Environment.getProperty()` và source thắng |
| Local config không override Config Server | Remote source không cấp `allowOverride` hoặc mode bootstrap có policy khác | Kiểm tra remote metadata và override flags |
| Config Server không được gọi | Thiếu `spring.config.import` hoặc bootstrap legacy chưa bật | Xác định mode nạp config rồi kiểm tra starter/property |
| Config Server bị gọi nhiều lần | Config Data fetch default profile và active profiles | Assert request semantics, không hard-code một request |
| Profile production không được nạp | Active profile sai hoặc profile order thay đổi | Set profile tường minh trong test và kiểm tra request |
| `@DynamicPropertySource` thắng test properties | Dynamic source có precedence cao hơn `@TestPropertySource` | Kiểm tra fixture, không sửa expected tùy tiện |
| Environment đúng nhưng bean sai | Binder/converter/bean lifecycle hoặc test đang đọc instance cũ | Assert bean binding, context refresh và custom converter |
| `/actuator/env` trả 404 | Endpoint chưa expose hoặc management base path/port khác | Kiểm tra exposure và URL thật |
| `/actuator/env` trả 403 | Security, CSRF hoặc access policy | Phân biệt thiếu quyền và thiếu CSRF token |
| Secret hiển thị thô | `show-values` hoặc custom sanitizer bị thay đổi | Đặt `never` hoặc role policy và thêm regression test |
| POST env không hoạt động | Chưa bật POST hoặc key không match regex | Kiểm tra `management.endpoint.env.post.*` |
| POST refresh không tồn tại | Spring Cloud Context không có trên classpath hoặc endpoint chưa expose | Kiểm tra dependency và Actuator exposure |
| ServiceRegistry endpoint trả 404 | Thiếu `Registration` bean hoặc endpoint chưa expose | Kiểm tra provider auto-configuration và registration |
| POST service registry trả lỗi | Status không được provider hỗ trợ | Dùng status hợp lệ của implementation |
| Test pass riêng nhưng fail cả suite | Context cache, system properties hoặc fixture dùng chung | Tạo fixture cô lập, phục hồi system properties và dùng `@DirtiesContext` khi cần |
| Candidate chỉ fail trên CI | Environment variables hoặc JVM system properties của runner khác local | In metadata nguồn thắng, không in secret value |

### 14.1. Quy trình điều tra sai lệch precedence

1. Ghi lại active profiles và application name.
2. Gọi `Environment.getProperty(key)` để lấy giá trị hiệu lực.
3. Duyệt `MutablePropertySources` để xác định nguồn đầu tiên chứa key.
4. Kiểm tra Config Data locations/import và profile-specific files.
5. Nếu có Config Server, xác định đang dùng Config Data hay bootstrap legacy.
6. Kiểm tra remote override flags nếu bootstrap legacy được bật.
7. Kiểm tra test properties có đang override cấu hình production hay không.
8. Kiểm tra bean `@ConfigurationProperties` đã bind lại đúng chưa.
9. Chạy lại test trên BOM cũ và BOM candidate để cô lập thay đổi.

### 14.2. Quy trình điều tra endpoint quản trị

1. Xác nhận endpoint ID và management base path.
2. Xác nhận endpoint được expose qua HTTP/JMX.
3. Kiểm tra access policy và Spring Security filter chain.
4. Kiểm tra CSRF cho request POST.
5. Xác minh `Registration` bean nếu endpoint yêu cầu.
6. Kiểm tra payload, status hợp lệ và regex allowlist.
7. Kiểm tra sanitization bằng secret giả.
8. So sánh response contract cần thiết, tránh snapshot toàn bộ JSON.

## 15. Bài tập thực hành

### Bài 1 — Viết test precedence ba nguồn

Tạo ba `MapPropertySource` cùng khai báo `checkout.max-items`. Thêm chúng bằng `addFirst` và `addLast`, xác minh giá trị hiệu lực và source thắng. Sau đó remove source đầu tiên và kiểm tra giá trị kế tiếp.

### Bài 2 — Profile và Config Data import

Tạo fixture cho default profile và `production`. Thêm hai import cùng khai báo một key. Viết test xác minh profile order và import precedence. Thử đảo thứ tự import để quan sát kết quả thay đổi.

### Bài 3 — Remote Config Server

Dùng WireMock hoặc MockWebServer để trả cấu hình theo application/profile/label. Kiểm thử Config Data import và, nếu ứng dụng còn dùng bootstrap legacy, viết một test riêng cho bootstrap mode. Không dùng Config Server thật.

### Bài 4 — Binding regression

Dùng `ApplicationContextRunner` để kiểm tra String, Integer, Duration, Boolean, List và Map được bind đúng. Thêm một converter tùy chỉnh nếu ứng dụng có dùng.

### Bài 5 — Actuator read contract

Dùng MockMvc để gọi GET `/actuator/env` và `/actuator/configprops`. Xác minh key quan trọng xuất hiện, giá trị secret bị mask và endpoint chỉ được expose theo test configuration.

### Bài 6 — Actuator mutation contract

Bật POST `/actuator/env` với allowlist regex trong test. Kiểm tra key hợp lệ thay đổi bean, key ngoài allowlist bị từ chối và user thiếu quyền không thể gọi endpoint.

### Bài 7 — Refresh và registry endpoint

Kiểm tra POST `/actuator/refresh` trên ứng dụng có refresh scope. Với provider registry, kiểm tra GET/POST `/actuator/serviceregistry` và status hợp lệ của implementation.

### Bài 8 — So sánh BOM trước và sau nâng cấp

Chạy cùng bộ test trên BOM hiện tại và BOM candidate. Xuất report gồm Boot version, Cloud BOM, config mode, profile, property source thắng, endpoint status và security result. Giải thích mọi khác biệt trước khi cập nhật baseline.

**Tiêu chí hoàn thành:** bạn có thể chứng minh giá trị cấu hình runtime và hành vi endpoint quản trị không bị thay đổi ngoài dự kiến sau khi nâng cấp Spring Boot/Spring Cloud.

## 16. Tổng kết

Kiểm thử hồi quy cấu hình cần kiểm tra cả source precedence, binding và management endpoint contract. Spring Boot có thứ tự nguồn cấu hình riêng; Config Data có thêm thứ tự file, profile, location và import. Spring Cloud Config có hai cơ chế nạp khác nhau là Config Data và bootstrap legacy, với chính sách override remote property source cần được kiểm thử đúng mode.

Dùng `MockEnvironment`, `MutablePropertySources`, `TestPropertyValues` và `ApplicationContextRunner` để kiểm tra logic nhỏ, sau đó dùng integration test với Config Server giả lập và MockMvc để kiểm tra hành vi ứng dụng thật. Với Actuator, xác minh exposure, mapping, method, authorization, CSRF và sanitization. Với Spring Cloud Commons, kiểm tra `serviceregistry` cùng `Registration` và status của provider.

Trước khi nâng cấp, hãy ghi baseline có chọn lọc cho key quan trọng, source category, profile, bean binding và endpoint. Chạy cùng regression suite trên BOM cũ và BOM candidate; chỉ chấp nhận sai khác sau khi hiểu nguyên nhân và xác nhận thay đổi đó là chủ ý.

## Tài liệu tham khảo

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): thứ tự property source, Config Data locations, profiles, imports và property precedence.
- [Spring Boot — Test Utilities](https://docs.spring.io/spring-boot/reference/testing/test-utilities.html): `ConfigDataApplicationContextInitializer`, `TestPropertyValues` và tiện ích kiểm thử context.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure, access, sanitization và contract của `env`/`configprops`.
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource` và precedence so với `@TestPropertySource`.
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): inline properties, resource locations và thứ tự test property source.
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): endpoint `env`, `refresh`, bootstrap context và refresh behavior.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, auto-registration và `/serviceregistry` endpoint.
- [Spring Cloud Config — Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import, bootstrap legacy, profile/label và remote property source.
- [Spring Cloud Config — Property Overrides](https://docs.spring.io/spring-cloud-config/reference/server/environment-repository/property-overrides.html): remote overrides và `overrideNone`.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): compatibility verifier và các property điều khiển Config/Commons.

Luôn kiểm tra tài liệu của đúng Spring Boot và Spring Cloud release train trong dự án. Các property, endpoint access policy và cấu trúc response có thể thay đổi giữa các thế hệ phiên bản.
