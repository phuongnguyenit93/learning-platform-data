# Triển khai PropertySourceLocator cho nguồn cấu hình riêng

> **Chương:** Nguồn cấu hình tùy biến  
> **Module:** SPRING_CLOUD_CORE

Khi cấu hình của một ứng dụng không chỉ đến từ `application.yml`, biến môi trường hoặc Spring Cloud Config Server, đội phát triển có thể cần đọc thuộc tính từ một nguồn riêng: dịch vụ cấu hình nội bộ, kho tham số theo tenant, hệ thống quản lý feature, hoặc một API cấp phát cấu hình theo môi trường. Trong mô hình bootstrap truyền thống của Spring Cloud, **`PropertySourceLocator`** là extension point cho phép tích hợp nguồn đó vào `Environment` trước khi ApplicationContext chính hoàn tất khởi tạo.

Triển khai locator đòi hỏi hiểu rõ thời điểm nó chạy, cách đăng ký bootstrap configuration, cách trả về `PropertySource`, thứ tự ưu tiên, và chính sách khi nguồn từ xa lỗi. Bài này xây dựng một ví dụ có thể kiểm thử, đồng thời phân biệt locator trong bootstrap legacy với cơ chế mở rộng Config Data của Spring Boot hiện đại.

## 1. `PropertySourceLocator` giải quyết vấn đề gì?

Spring Boot biểu diễn cấu hình thông qua `Environment`. Mỗi `PropertySource` là một nguồn cung cấp giá trị theo tên thuộc tính, chẳng hạn:

- `application.yml` và `application-{profile}.yml`.
- Biến môi trường và Java system properties.
- Tham số dòng lệnh.
- Property source do Spring Cloud Config Client nạp.
- Property source do ứng dụng hoặc thư viện tích hợp thêm.

Một nguồn cấu hình tùy biến có thể lấy dữ liệu từ API riêng, nhưng cần đưa dữ liệu đó vào cùng mô hình property để các thành phần Spring sử dụng thống nhất. `PropertySourceLocator` cung cấp hợp đồng:

~~~java
public interface PropertySourceLocator {
    PropertySource<?> locate(Environment environment);
}
~~~

Spring Cloud gọi `locate` với `Environment` hiện có trong giai đoạn bootstrap. Locator có thể đọc các thuộc tính nhận diện ứng dụng, profile hoặc tenant, gọi client của nguồn cấu hình riêng, rồi trả về một `PropertySource<?>`. Các giá trị được thêm vào môi trường cấu hình để những thành phần khởi tạo sau có thể resolve.

Một số ví dụ về dữ liệu có thể lấy từ nguồn riêng:

| Nguồn | Dữ liệu ví dụ | Mục đích |
| --- | --- | --- |
| Tenant settings API | Giới hạn tính năng, mã vùng, cấu hình theo tenant | Dùng cùng artifact cho nhiều tenant |
| Internal parameter service | Endpoint phụ thuộc, timeout, quota | Quản lý tham số tập trung |
| Environment metadata service | Tên cluster, zone, deployment ring | Điều chỉnh hành vi theo môi trường |
| Feature configuration service | Trạng thái feature ở cấp ứng dụng | Cung cấp cấu hình khởi tạo cho feature |

Locator chỉ giải quyết việc **đưa thuộc tính vào Environment**. Nó không tự tạo giao diện quản trị, phân quyền người dùng, đồng bộ cấu hình động hoặc bảo đảm mọi bean có thể refresh khi dữ liệu nguồn thay đổi.

## 2. Vòng đời bootstrap và vị trí của locator

Trong mô hình legacy, Spring Cloud tạo bootstrap context trước ApplicationContext chính. Bootstrap context có thể tạo các bean cấu hình và gọi những locator được đăng ký. Các property source mà locator trả về được bổ sung vào môi trường để ứng dụng chính sử dụng khi khởi tạo.

~~~mermaid
flowchart TB
    A["Tiến trình Spring Boot bắt đầu"]
    A --> B["Tạo bootstrap context"]
    B --> C["Đăng ký BootstrapConfiguration"]
    C --> D["Khởi tạo PropertySourceLocator"]
    D --> E["locate(Environment)"]
    E --> F["Đọc application/profile/tenant"]
    F --> G["Client truy vấn nguồn cấu hình riêng"]
    G --> H["MapPropertySource / CompositePropertySource"]
    H --> I["Bổ sung property source vào Environment"]
    I --> J["Khởi tạo ApplicationContext chính"]
    J --> K["Bind @ConfigurationProperties và tạo bean"]
~~~

Điểm quan trọng là locator chạy **sớm hơn nhiều bean nghiệp vụ**. Vì vậy, nó không nên phụ thuộc vào một service chỉ được tạo trong ApplicationContext chính. Những dependency cần cho locator phải được cung cấp trong bootstrap context hoặc được khởi tạo độc lập ở đó.

### 2.1. Khi nào bootstrap context được kích hoạt?

Trong các ứng dụng Spring Cloud sử dụng cơ chế legacy, bootstrap thường được bật bằng dependency `spring-cloud-starter-bootstrap` hoặc cờ `spring.cloud.bootstrap.enabled=true` được cung cấp đủ sớm theo phiên bản. Chỉ tạo file `bootstrap.yml` không có nghĩa bootstrap context chắc chắn hoạt động trong mọi cấu hình hiện đại.

Khi bootstrap không được bật, việc có một class implement `PropertySourceLocator` trong classpath không tự bảo đảm Spring Cloud sẽ gọi nó. Cần xác minh dependency, cách đăng ký và log khởi động.

### 2.2. Locator không phải Config Data loader

Spring Boot 2.4 trở lên có Config Data API để nạp nguồn cấu hình qua `spring.config.import`. Spring Cloud Config Client tích hợp Config Data bằng location như `configserver:`. Đây là một đường mở rộng khác với bootstrap legacy.

| Extension point | Giai đoạn | Trường hợp phù hợp |
| --- | --- | --- |
| `PropertySourceLocator` | Bootstrap context legacy của Spring Cloud | Tích hợp nguồn cấu hình vào mô hình bootstrap cũ |
| `ConfigDataLocationResolver` và `ConfigDataLoader` | Config Data của Spring Boot | Tạo location riêng có thể khai báo qua `spring.config.import` |
| `EnvironmentPostProcessor` | Giai đoạn chuẩn bị Environment theo cơ chế Spring Boot | Bổ sung hoặc biến đổi Environment trong phạm vi extension được hỗ trợ |

Nếu dự án đang dùng Config Data và muốn khai báo một nguồn riêng như `vaultx:` hoặc `tenantconfig:` trong `spring.config.import`, hãy tìm hiểu `ConfigDataLocationResolver`/`ConfigDataLoader`. Không nên dùng `PropertySourceLocator` như một cách thay thế trực tiếp cho mọi extension point hiện đại.

## 3. Đăng ký BootstrapConfiguration

Một class cấu hình bootstrap cần được Spring Cloud phát hiện. Trong mô hình bootstrap truyền thống, thư viện hoặc ứng dụng đăng ký class đó trong file `META-INF/spring.factories` bằng key `org.springframework.cloud.bootstrap.BootstrapConfiguration`.

Ví dụ file:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.example.order.bootstrap.TenantBootstrapConfiguration
~~~

Class cấu hình:

~~~java
package com.example.order.bootstrap;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TenantBootstrapConfiguration {

    @Bean
    PropertySourceLocator tenantPropertySourceLocator(
            TenantSettingsClient client) {
        return new TenantPropertySourceLocator(client);
    }
}
~~~

Trong dự án thực tế, `TenantSettingsClient` là thành phần do ứng dụng hoặc thư viện cung cấp để gọi nguồn cấu hình. Nó phải có mặt trong bootstrap context. Nếu bean này phụ thuộc vào các bean chỉ được tạo trong ApplicationContext chính, cần tách phần client tối thiểu sang cấu hình bootstrap hoặc dùng một implementation độc lập.

### 3.1. Nội dung và vị trí của spring.factories

File `spring.factories` phải nằm đúng vị trí:

~~~text
src/main/resources/
  META-INF/
    spring.factories
~~~

Nếu locator được đóng gói trong một thư viện, file phải được đưa vào JAR của thư viện đó. Ứng dụng sử dụng thư viện cần dependency tương ứng và bật bootstrap theo cách mà phiên bản Spring Cloud hỗ trợ.

Không đặt class bootstrap vào một package được component scan thông thường rồi cho rằng điều đó đủ để đăng ký bootstrap configuration. Bootstrap context có cơ chế discovery riêng. Kiểm tra nội dung JAR sau khi build nếu ứng dụng không tìm thấy locator.

Lưu ý về phiên bản: cơ chế đăng ký bootstrap legacy dựa trên `spring.factories` dành cho `BootstrapConfiguration`. Cơ chế auto-configuration của Spring Boot ở các phiên bản mới có thể dùng metadata khác, nhưng điều đó không thay thế cơ chế đăng ký bootstrap legacy.

## 4. Thiết kế client cho nguồn cấu hình riêng

Giả sử hệ thống có một Tenant Settings Service trả về cấu hình theo tên ứng dụng, tenant và profile. Tách việc gọi mạng khỏi locator bằng một interface:

~~~java
import java.util.Map;

public interface TenantSettingsClient {

    Map<String, Object> fetch(
            String applicationName,
            String tenantId,
            String[] profiles);
}
~~~

Interface này giúp locator không phụ thuộc HTTP library cụ thể. Khi kiểm thử, có thể dùng fake hoặc mock client. Trong implementation thực tế, client có thể dùng WebClient, RestClient hoặc HTTP client phù hợp với phiên bản Spring.

Một response ví dụ:

~~~json
{
  "catalog.client.base-url": "https://catalog.tenant-a.internal",
  "catalog.client.read-timeout": "2s",
  "feature.new-checkout.enabled": true,
  "tenant.region": "ap-southeast"
}
~~~

Các key trong response cần là tên property mà ứng dụng dự định bind. Nếu dùng namespace riêng như `catalog.client`, ứng dụng có thể bind bằng `@ConfigurationProperties(prefix = "catalog.client")` sau khi property source đã được nạp.

Không trả về đối tượng tùy ý không thể chuyển đổi hoặc dữ liệu nhạy cảm không cần thiết. Hãy xác định schema của response, kiểu dữ liệu, phiên bản hợp đồng và cách xử lý key không được nhận diện.

### 4.1. Không đưa credential vào source code

Client gọi dịch vụ cấu hình có thể cần token hoặc chứng thư. Credential phải được lấy từ nguồn bảo mật phù hợp ở bootstrap, chẳng hạn secret được mount hoặc biến môi trường do nền tảng cấp. Không hard-code token trong `spring.factories`, YAML đã commit hoặc mã Java.

Cũng không log toàn bộ response, request header hoặc map property. Nguồn cấu hình có thể chứa password, token, URL nội bộ và thông tin hạ tầng.

## 5. Triển khai locator

Dưới đây là một implementation minh họa. Nó đọc application name và tenant ID từ Environment, gọi client, rồi trả về `MapPropertySource`.

~~~java
package com.example.order.bootstrap;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.Ordered;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.util.StringUtils;

public final class TenantPropertySourceLocator
        implements PropertySourceLocator, Ordered {

    private final TenantSettingsClient client;

    public TenantPropertySourceLocator(TenantSettingsClient client) {
        this.client = client;
    }

    @Override
    public PropertySource<?> locate(Environment environment) {
        String applicationName = environment.getProperty(
                "spring.application.name", "unknown-application");

        String tenantId = environment.getProperty("platform.tenant-id");

        if (!StringUtils.hasText(tenantId)) {
            return null;
        }

        String[] profiles = environment.getActiveProfiles();
        Map<String, Object> values =
                client.fetch(applicationName, tenantId, profiles);

        if (values == null || values.isEmpty()) {
            return null;
        }

        Map<String, Object> copy = new LinkedHashMap<>(values);

        return new MapPropertySource(
                "tenantSettings:" + tenantId,
                copy);
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
~~~

Các điểm cần chú ý:

- `locate(Environment)` nhận môi trường hiện có để đọc định danh ứng dụng và tenant.
- `spring.application.name` có giá trị mặc định trong ví dụ để log/chẩn đoán không gặp null; dự án thật có thể chọn yêu cầu bắt buộc và fail-fast.
- `platform.tenant-id` là thuộc tính do ứng dụng định nghĩa. Nó cần có từ một nguồn được nạp trước locator, ví dụ biến môi trường hoặc system property.
- `getActiveProfiles()` trả về profile đang active tại thời điểm locator được gọi. Nếu một profile được thêm sau đó bởi nguồn khác, locator hiện tại không tự chạy lại chỉ vì profile thay đổi.
- `MapPropertySource` cung cấp map key/value cho Spring.
- Tên property source nên có ý nghĩa và ổn định để việc quan sát Environment dễ dàng.
- `Ordered` cho phép xác định thứ tự locator khi có nhiều locator. Thứ tự cuối cùng giữa các property source còn phụ thuộc cách bootstrap tích hợp và các nguồn khác; phải kiểm tra giá trị hiệu lực thay vì suy đoán.

### 5.1. Vì sao trả về null khi không có tenant?

Trong ví dụ, tenant ID là điều kiện để gọi nguồn cấu hình. Nếu ứng dụng không khai báo tenant, locator trả về null để báo rằng nó không có property source bổ sung.

Đây là lựa chọn chính sách, không phải quy tắc cho mọi hệ thống. Nếu tenant bắt buộc ở production, việc thiếu tenant nên làm khởi động thất bại bằng lỗi cấu hình rõ ràng thay vì âm thầm bỏ qua nguồn. Nếu nguồn chỉ được dùng cho một số môi trường, có thể bỏ qua ở local nhưng yêu cầu ở staging/production.

Ví dụ kiểm tra bắt buộc:

~~~java
if (!StringUtils.hasText(tenantId)) {
    throw new IllegalStateException(
            "platform.tenant-id is required for remote tenant configuration");
}
~~~

Không dùng `return null` để che lỗi xác thực hoặc lỗi mạng khi dữ liệu remote là bắt buộc.

## 6. Chính sách lỗi và tính sẵn sàng

`PropertySourceLocator` thường chạy đồng bộ trong giai đoạn khởi tạo. Vì vậy, một lần gọi remote bị treo có thể kéo dài startup hoặc khiến ứng dụng không khởi động được. Thiết kế client cần có timeout và chính sách lỗi rõ ràng.

| Trạng thái nguồn cấu hình | Nguồn là bắt buộc | Nguồn là tùy chọn |
| --- | --- | --- |
| Trả dữ liệu hợp lệ | Nạp property source | Nạp property source |
| Không có cấu hình cho tenant | Báo lỗi nếu thiếu dữ liệu là không hợp lệ | Bỏ qua hoặc trả source rỗng theo quy ước |
| Timeout/kết nối lỗi | Fail-fast với thông báo rõ ràng | Có thể fallback nếu đã định nghĩa an toàn |
| Response sai schema | Báo lỗi để tránh dùng cấu hình sai | Bỏ qua chỉ khi dữ liệu đó thực sự tùy chọn và có cảnh báo |
| Thiếu tenant ID | Fail-fast | Bỏ qua nếu môi trường này không cần tenant config |

Các nguyên tắc triển khai:

1. **Timeout hữu hạn:** cấu hình connect timeout và response/read timeout; không để startup chờ vô hạn.
2. **Retry có giới hạn:** chỉ retry lỗi tạm thời, có backoff và giới hạn tổng thời gian.
3. **Không retry mù quáng:** request đọc cấu hình thường idempotent, nhưng vẫn cần giới hạn tải lên Config Service.
4. **Fail-fast khi dữ liệu bắt buộc:** không khởi động với cấu hình thiếu có thể gây lỗi nghiệp vụ hoặc mất an toàn.
5. **Fallback có chủ đích:** chỉ dùng giá trị cục bộ nếu chúng là phương án dự phòng được chấp thuận.
6. **Thông báo lỗi hữu ích:** ghi application, tenant và loại lỗi; không ghi token hay giá trị secret.
7. **Không che mọi exception:** bắt và chuyển đổi lỗi ở ranh giới client khi cần, nhưng giữ nguyên nguyên nhân để chẩn đoán.

Ví dụ, client có thể ném exception chuyên biệt:

~~~java
public final class TenantSettingsUnavailableException
        extends RuntimeException {

    public TenantSettingsUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Locator hoặc bootstrap flow có thể để lỗi này làm startup thất bại nếu nguồn là bắt buộc. Với nguồn tùy chọn, có thể bắt đúng loại exception đã xác định, ghi cảnh báo không chứa secret và trả về null. Không nên bắt `Exception` chung chung rồi âm thầm coi mọi lỗi là “không có cấu hình”.

## 7. Thứ tự ưu tiên và xung đột property

Khi nhiều nguồn cùng khai báo một key, Spring resolve giá trị theo thứ tự property source trong Environment. Locator có thể trả về một nguồn chứa key trùng với `application.yml` hoặc Config Server. Do đó cần xác định rõ ai sở hữu key và nguồn nào được quyền ghi đè.

Ví dụ:

`application.yml`:

~~~yaml
catalog:
  client:
    read-timeout: 5s
    max-attempts: 2
~~~

Nguồn tenant trả về:

~~~json
{
  "catalog.client.read-timeout": "2s",
  "catalog.client.max-attempts": 3
}
~~~

Giá trị thực tế mà `@ConfigurationProperties` nhận phụ thuộc thứ tự các property source. Không nên giả định rằng locator luôn có ưu tiên cao nhất hoặc thấp nhất ở mọi phiên bản/cấu hình. Các thuộc tính điều khiển override của Spring Cloud Config Server cũng không nên áp dụng một cách máy móc cho locator tùy biến.

Hãy xác minh bằng cách đọc giá trị cuối cùng từ `Environment` hoặc bean đã bind trong test. Nếu có nhiều locator, xác định thứ tự bằng `Ordered` và đặt tên property source riêng biệt.

### 7.1. Tránh ghi đè cấu hình nhạy cảm ngoài ý muốn

Không nên cho nguồn tenant tùy ý ghi đè mọi key. Có thể giới hạn tập key được phép trả về:

~~~java
private static final Set<String> ALLOWED_PREFIXES = Set.of(
        "catalog.client.",
        "feature.",
        "tenant."
);
~~~

Trước khi tạo property source, kiểm tra từng key có nằm trong namespace được phép. Với các key như datasource password, signing key, token hoặc security policy, cần một quy trình quản lý riêng và quyền truy cập chặt chẽ.

Một phương án khác là chỉ cho remote source cung cấp một object cấu hình riêng, ví dụ `tenant.features.*`, thay vì có quyền ghi đè toàn bộ Environment. Phạm vi càng nhỏ thì xung đột càng dễ kiểm soát.

## 8. Kiểm thử PropertySourceLocator

Nên kiểm thử locator độc lập trước, sau đó kiểm thử tích hợp bootstrap context. Test độc lập giúp xác nhận việc đọc Environment, gọi client và tạo property source mà không cần khởi động Config Server.

Ví dụ dùng `MockEnvironment` và một fake client:

~~~java
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MockEnvironment;
import org.springframework.core.env.PropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class TenantPropertySourceLocatorTest {

    @Test
    void createsPropertySourceForConfiguredTenant() {
        TenantSettingsClient client = (application, tenant, profiles) ->
                Map.of(
                        "tenant.region", "ap-southeast",
                        "catalog.client.read-timeout", "2s"
                );

        TenantPropertySourceLocator locator =
                new TenantPropertySourceLocator(client);

        MockEnvironment environment = new MockEnvironment()
                .withProperty("spring.application.name", "order-service")
                .withProperty("platform.tenant-id", "tenant-a");

        environment.setActiveProfiles("production");

        PropertySource<?> source = locator.locate(environment);

        assertThat(source).isInstanceOf(MapPropertySource.class);
        assertThat(source.getProperty("tenant.region"))
                .isEqualTo("ap-southeast");
        assertThat(source.getProperty("catalog.client.read-timeout"))
                .isEqualTo("2s");
    }
}
~~~

Test trên dùng fake client để tập trung vào logic locator. Trong dự án, cần bổ sung test cho các trường hợp:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Tenant ID có mặt, client trả map | Có property source với đúng key/value |
| Tenant ID thiếu và nguồn tùy chọn | Locator không tạo source |
| Tenant ID thiếu và nguồn bắt buộc | Khởi động thất bại với lỗi dễ hiểu |
| Client trả map rỗng | Không thêm source hoặc xử lý theo quy ước đã chọn |
| Client timeout | Áp dụng fail-fast/fallback đúng chính sách |
| Response có key ngoài allowlist | Từ chối hoặc loại key theo chính sách |
| Có hai locator cùng cung cấp một key | Giá trị hiệu lực đúng thứ tự đã thiết kế |
| Profile thay đổi | Xác minh locator được gọi lại hay cần restart theo vòng đời thực tế |

### 8.1. Kiểm thử tích hợp bootstrap

Unit test không xác nhận `spring.factories` đã được đóng gói và bootstrap context thực sự phát hiện cấu hình. Cần có một bài kiểm thử tích hợp hoặc smoke test khởi động ứng dụng với bootstrap được bật, sau đó kiểm tra:

- Locator được tạo trong bootstrap context.
- Client được inject đúng.
- Config source xuất hiện trong Environment của ứng dụng chính.
- `@ConfigurationProperties` bind được các key do locator cung cấp.
- Không có request remote ngoài dự kiến.
- Lỗi khi nguồn bắt buộc không truy cập được được báo đúng cách.

Nếu locator nằm trong thư viện, kiểm tra JAR có file `META-INF/spring.factories` và tên class chính xác. Đây là lỗi đóng gói dễ bị bỏ sót khi unit test chạy trực tiếp trong module.

## 9. Locator và refresh cấu hình

`PropertySourceLocator` không phải cơ chế polling hoặc subscription. Locator được gọi trong vòng đời bootstrap; việc nguồn cấu hình thay đổi sau đó không có nghĩa locator tự chạy lại liên tục.

Nếu cần thay đổi cấu hình khi ứng dụng đang chạy, phải chọn một cơ chế riêng, chẳng hạn:

- Dùng Spring Cloud Config và refresh event phù hợp.
- Xây dựng endpoint/event để cập nhật nguồn cấu hình và quản lý vòng đời bean.
- Dùng feature flag service chuyên biệt nếu mục tiêu là bật/tắt tính năng động.
- Khởi động lại hoặc rolling deploy nếu thay đổi liên quan tới cấu hình không thể áp dụng an toàn khi runtime đang chạy.

Spring Cloud Context có `@RefreshScope` cho một số bean có thể được tạo lại khi refresh. Tuy nhiên, việc làm mới property source và việc bean nhận giá trị mới là hai phần cần xác minh riêng. Locator legacy không tự cung cấp kênh phát sự kiện hay chính sách refresh cho nguồn riêng.

Không dùng một locator đồng bộ ở bootstrap để tạo ra một hệ thống cấu hình động bằng cách gọi API liên tục. Nếu cần cập nhật thường xuyên, hãy dùng cơ chế chuyên cho runtime update, có bảo mật, quan sát và kiểm soát tần suất.

## 10. Bảo mật và vận hành

Nguồn cấu hình tùy biến có thể chứa endpoint nội bộ, feature flag, tenant metadata và secret. Vì vậy, cần kiểm soát cả phía client lẫn server.

- **Xác thực nguồn:** dùng TLS và cơ chế xác thực service-to-service phù hợp.
- **Phân quyền theo tenant:** tenant ID do client gửi phải được xác thực; không tin tenant ID từ request người dùng nếu nó quyết định cấu hình khởi tạo.
- **Giới hạn key:** chỉ nhận namespace mà ứng dụng cho phép.
- **Bảo vệ secret:** không log payload, không expose qua Actuator hoặc exception message.
- **Timeout và capacity:** giới hạn kết nối, response time và số request đồng thời tới config service.
- **Quan sát:** ghi thời gian tải cấu hình, trạng thái thành công/thất bại, tenant/app/profile ở mức metadata an toàn.
- **Kiểm soát version:** định nghĩa schema và version của response để thay đổi phía server không làm client cũ khởi động lỗi ngoài dự kiến.
- **Fallback:** ghi rõ giá trị nào được phép dùng khi nguồn từ xa không sẵn sàng; tránh fallback âm thầm cho cấu hình bắt buộc.

Có thể ghi metric như số lần locator gọi nguồn, thời gian tải, số lỗi theo loại và số lần fallback. Tránh dùng tenant ID không giới hạn làm metric label nếu điều đó tạo cardinality quá cao; có thể dùng log có cấu trúc hoặc nhãn đã chuẩn hóa.

## 11. Các lỗi thường gặp

1. **Locator không được gọi:** bootstrap chưa bật, thiếu starter/cờ phù hợp hoặc bootstrap configuration chưa được đăng ký.
2. **Không tìm thấy class cấu hình:** file `spring.factories` sai key, sai tên class hoặc không được đóng gói trong JAR.
3. **Không inject được client:** client chỉ tồn tại trong ApplicationContext chính, trong khi locator được tạo ở bootstrap context.
4. **Gọi Config Service quá lâu:** thiếu connect/read timeout hoặc retry không giới hạn.
5. **Giá trị remote không ghi đè như mong đợi:** chưa kiểm tra thứ tự property source và thứ tự locator.
6. **Nguồn tùy biến ghi đè nhầm key:** không giới hạn namespace hoặc không xác định quyền sở hữu property.
7. **Thay đổi nguồn nhưng bean không cập nhật:** locator không tự polling; cần cơ chế refresh riêng hoặc restart.
8. **Bật locator legacy cùng Config Data import:** có thể tạo hai đường nạp cấu hình; chọn extension point phù hợp với cơ chế đang dùng.
9. **Lộ secret trong log:** log toàn bộ map hoặc exception từ HTTP client; chỉ ghi metadata không nhạy cảm.
10. **Test pass nhưng production không phát hiện locator:** chưa kiểm tra JAR và bootstrap context thật.

## 12. Chọn extension point phù hợp

Trước khi triển khai, hãy trả lời ba câu hỏi:

| Câu hỏi | Nếu câu trả lời là... | Hướng lựa chọn |
| --- | --- | --- |
| Ứng dụng có đang dùng bootstrap context legacy? | Có, và cần nạp source trước context chính | `PropertySourceLocator` |
| Nguồn riêng cần được khai báo bằng `spring.config.import`? | Có, ứng dụng dùng Config Data | `ConfigDataLocationResolver` và `ConfigDataLoader` |
| Chỉ cần bổ sung một số property trong giai đoạn chuẩn bị Environment theo Spring Boot? | Có, không cần mô hình location riêng | Xem xét `EnvironmentPostProcessor` và thứ tự thực thi của nó |

Không chọn extension point chỉ vì tên interface quen thuộc. Cần đối chiếu phiên bản Spring Boot/Spring Cloud, vòng đời khởi tạo, khả năng xử lý lỗi và yêu cầu cập nhật runtime.

**Điểm ghi nhớ:** `PropertySourceLocator` là hợp đồng của Spring Cloud bootstrap legacy để lấy một `PropertySource` từ `Environment` và bổ sung vào quá trình khởi tạo ứng dụng. Triển khai đúng cần đăng ký `BootstrapConfiguration`, cung cấp dependency trong bootstrap context, đặt timeout và chính sách lỗi rõ ràng, kiểm soát key được phép ghi đè và kiểm thử cả locator lẫn quá trình đóng gói. Với nguồn tùy biến mới trong Config Data, hãy dùng resolver/loader tương ứng thay vì vô tình mở thêm một đường bootstrap.
