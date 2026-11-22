# Gắn thuộc tính vào bean mặc định mà không trộn logic nghiệp vụ vào cấu hình

## 1. Vấn đề cần giải quyết

Khi xây dựng một thư viện hoặc Spring Boot starter, ta thường muốn người dùng chỉ cần thêm dependency, đặt vài thuộc tính trong `application.yml` rồi có sẵn một bean mặc định. Đồng thời, thư viện phải cho phép ứng dụng thay thế bean khi cần implementation riêng.

Ví dụ: thư viện tích hợp hệ thống danh mục sản phẩm có một `CatalogClient`. Ứng dụng cần thay đổi `baseUri`, `timeout` và số lần thử tối đa bằng cấu hình. Những giá trị này là **thông số vận hành và kết nối**; chúng không nên kéo logic nghiệp vụ như xác định mã sản phẩm hợp lệ, chọn truy vấn, tính giá hay xử lý response vào `@ConfigurationProperties` hoặc phương thức `@Bean` của auto-configuration.

Thiết kế tách thành **ba trách nhiệm**:

1. **`@ConfigurationProperties`** — định nghĩa *dữ liệu cấu hình*, giá trị mặc định và các ràng buộc hợp lệ của cấu hình. Lớp này không xử lý use case.
2. **`@AutoConfiguration` + `@Bean`** — quyết định *khi nào* tạo bean mặc định và *nối các giá trị cấu hình* vào constructor/factory của implementation. Đây là tầng lắp ghép (wiring/composition).
3. **Implementation và service nghiệp vụ** — thực hiện *hành vi*, kiểm tra đầu vào nghiệp vụ, xây request, gọi dependency, chuyển đổi kết quả và áp dụng quy tắc của domain. Lớp này nhận cấu hình cần thiết qua constructor, không tự đi đọc file `application.yml`.

Đích đến: người dùng điều khiển các tùy chọn được hỗ trợ qua properties, còn code nghiệp vụ có thể kiểm thử độc lập; auto-configuration vẫn back off nếu ứng dụng cung cấp bean thay thế.

## 2. Mô hình phụ thuộc và luồng thực thi

```text
application.yml / application.properties / env vars / CLI
                          |
                          v
                Spring Environment
                          |
                          v
                Binder của Spring Boot
                          |
                          v
            CatalogClientProperties
              (baseUri, timeout,
                 maxAttempts)
                          |
                          v
             CatalogAutoConfiguration
      @EnableConfigurationProperties
      @ConditionalOnMissingBean(CatalogClient.class)
                          |
                          v
            new DefaultCatalogClient(...)
                          |
                          v
             CatalogClient interface
                          |
                          v
          ApplicationService / controller
               gọi planFor(sku)
                          |
                          v
        Behavior thực thi ở DefaultCatalogClient
```

Điều quan trọng là *mũi tên phụ thuộc*: implementation nhận giá trị đã chuyển đổi kiểu qua constructor; nó không phụ thuộc vào `Environment` hay API binding của Spring Boot. Service nghiệp vụ phụ thuộc vào interface `CatalogClient`, không phụ thuộc vào lớp auto-configuration.

### Phân quyền cụ thể

| Thành phần | Nên chứa | Không nên chứa |
| --- | --- | --- |
| `CatalogClientProperties` | `URI baseUri`, `Duration timeout`, `int maxAttempts`, default, quy tắc kiểm tra cấu hình hợp lệ | Gọi HTTP, phân nhánh theo đơn hàng, gọi repository, retry request thực, biến đổi response |
| `CatalogAutoConfiguration` | `@EnableConfigurationProperties`, điều kiện bean/property, `@Bean` factory ngắn gọn, chọn implementation mặc định | Thuật toán nghiệp vụ, vòng lặp retry, tính giá, xử lý JSON, logic của controller |
| `DefaultCatalogClient` | Sử dụng endpoint/timeout/retry, tạo request, xử lý lỗi và hành vi client thực | Đọc trực tiếp `application.yml`, giải mã `Environment` cho mỗi lần gọi |
| `ApplicationService` | Use case, quy tắc domain, phối hợp nhiều dependency | Tự khởi tạo client mặc định hay quyết định bean condition của starter |

Không có quy tắc cấm mọi câu lệnh `if` trong `@Configuration`: **điều kiện cấu hình** như "có class thư viện", "người dùng đã cung cấp bean", "property enable" vẫn thuộc tầng wiring. Cần tách **logic nghiệp vụ** khỏi **logic lựa chọn thành phần**.

## 3. Đặt tên và định nghĩa properties của thư viện

Giả sử thư viện chọn tiền tố `acme.catalog`:

```yaml
acme:
  catalog:
    enabled: true
    base-uri: https://catalog.example.test/api
    timeout: 5s
    max-attempts: 4
```

Ý nghĩa:

- `enabled`: chính sách tạo **bean mặc định**, không phải công tắc toàn cục để cấm ứng dụng tự đăng ký một client khác.
- `base-uri`: endpoint của tích hợp; trong Java dùng `URI` để tránh chuyển đổi chuỗi thủ công khắp nơi.
- `timeout`: dùng `Duration`, giúp binder nhận `500ms`, `2s`, `1m` theo cú pháp được Spring Boot hỗ trợ.
- `max-attempts`: tổng số lần thử mà **implementation** có thể sử dụng; thuật toán retry, ngoại lệ được retry và backoff phải nằm trong code client/chính sách retry, không nằm trong getter của properties.

Tên key nên có namespace của thư viện để tránh xung đột với `spring.*` hoặc một starter khác. Tên class cũng nên diễn đạt rõ ranh giới, ví dụ `CatalogClientProperties` và `CatalogAutoConfiguration`.

### Giá trị mặc định có hai nơi rất khác nhau

Có thể viết:

```java
private Duration timeout = Duration.ofSeconds(2);
```

Nếu `acme.catalog.timeout` không hiện diện, binder có thể để nguyên default này trên đối tượng `CatalogClientProperties`. Nhưng:

```java
environment.getProperty("acme.catalog.timeout"); // có thể null
```

Default trong Java **không tự thêm key vào Environment**. Vì vậy, nếu `enabled` có default `true` trong properties, condition ở auto-configuration cần có `matchIfMissing=true` để chủ động mô tả trường hợp key vắng mặt. Không được giả định `@ConditionalOnProperty` sẽ đọc getter `isEnabled()` của properties bean.

Đặt default hợp lý cho thư viện, cho phép override từ Environment, và **đừng đồng thời hard-code một default khác** trong implementation. Constructor có thể kiểm tra giá trị đầu vào hợp lệ nhưng nên nhận toàn bộ tùy chọn cuối cùng do tầng wiring chuyển tới.

## 4. Liên kết cấu hình với bean mặc định như thế nào?

Trong Spring Boot 3.x, cách rõ ràng cho thư viện là:

```java
@AutoConfiguration
@EnableConfigurationProperties(CatalogClientProperties.class)
class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    @ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    CatalogClient catalogClient(CatalogClientProperties properties) {
        return new DefaultCatalogClient(
            properties.getBaseUri(),
            properties.getTimeout(),
            properties.getMaxAttempts()
        );
    }
}
```

*Đây là đoạn minh họa*. Các lớp liên quan và imports đầy đủ có trong ví dụ chạy được ở mục 6.

Bốn annotation có vai trò riêng:

- `@AutoConfiguration`: đánh dấu lớp cấu hình của thư viện để Spring Boot có thể tự áp dụng khi starter được đăng ký đúng cách.
- `@EnableConfigurationProperties(CatalogClientProperties.class)`: yêu cầu tạo và bind bean properties. Một thư viện không cần giả định ứng dụng sẽ bật `@ConfigurationPropertiesScan` giúp mình.
- `@ConditionalOnMissingBean(CatalogClient.class)`: nếu ứng dụng đã khai báo một `CatalogClient` phù hợp, **không tạo bean mặc định**. Người dùng giữ quyền thay implementation.
- `@ConditionalOnProperty(...)`: chỉ quyết định có tạo bean mặc định khi thuộc tính bật; `matchIfMissing=true` khiến thiếu key được coi là bật theo chính sách mẫu.

**Điểm thiết kế:** phương thức `catalogClient(...)` chỉ nối dependency và gọi constructor. Mọi code nghiệp vụ chạy khi sử dụng client nằm trong `DefaultCatalogClient` hoặc trong các service tương ứng.

### Vì sao condition thường cần nằm trong auto-configuration?

`@ConditionalOnMissingBean` kiểm tra các **bean definitions đã được xử lý đến thời điểm condition chạy**. Spring Boot sắp xếp auto-configuration sau những cấu hình ứng dụng thông thường, nên đây là nơi phù hợp để mặc định back off trước bean người dùng. Đặt logic này ở một class `@Configuration` tùy ý và giả định mọi bean đã xuất hiện có thể tạo kết quả phụ thuộc thứ tự.

Ngoài ra, `@ConditionalOnMissingBean(CatalogClient.class)` kiểm tra **kiểu**, không yêu cầu user bean phải tên `catalogClient`. Một bean `@Bean CatalogClient customClient()` có thể ngăn mặc định được tạo. Điều kiện cũng có quy tắc lọc các ứng viên bean và search strategy; hãy kiểm tra Javadoc đúng phiên bản nếu dùng hierarchy/phức tạp.

## 5. Giữ nghiệp vụ ra khỏi lớp cấu hình: ví dụ đúng và sai

### Ví dụ không nên làm

```java
// Anti-pattern: trộn wiring, thao tác I/O và logic nghiệp vụ
@Bean
CatalogClient catalogClient(CatalogClientProperties properties) {
    if (properties.getMaxAttempts() > 3) {
        // Gọi API hoặc repository để quyết định khách hàng ưu tiên.
        // Vòng lặp retry và xử lý kết quả ở ngay trong factory bean.
    }
    return ...;
}
```

Đây là **mã giả không biên dịch độc lập**, mục đích chỉ để chỉ ra ranh giới bị vượt qua. Việc tải dữ liệu, tính chính sách, hoặc thao tác I/O như một phần lựa chọn bean khiến startup khó kiểm thử và khó theo dõi.

### Cấu trúc tốt hơn

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogClientProperties p) {
    return new DefaultCatalogClient(p.getBaseUri(), p.getTimeout(), p.getMaxAttempts());
}
```

Và ở **implementation**:

```java
@Override
public QueryPlan planFor(String sku) {
    if (sku == null || sku.isBlank()) {
        throw new IllegalArgumentException("SKU must not be blank");
    }

    String code = URLEncoder.encode(sku, StandardCharsets.UTF_8);
    return new QueryPlan(
        URI.create(baseUriAsString + "/items?sku=" + code),
        timeout,
        maxAttempts
    );
}
```

Đây cũng là **trích đoạn**, các field/imports có trong ví dụ đầy đủ phía dưới. Lớp client kiểm tra đầu vào và quyết định cách tạo một request plan; lớp properties chỉ giữ cấu hình. Nếu thay `planFor` bằng thao tác HTTP thật, code xử lý request/response vẫn thuộc adapter, trong khi nghiệp vụ chọn SKU và cách sử dụng kết quả thường ở service ứng dụng.

Trong ví dụ, tạo `QueryPlan` nhằm kiểm thử việc wiring mà không cần mạng hoặc credentials. Nó **không gửi request HTTP** hay tự thực hiện retry; `timeout`/`maxAttempts` chỉ là thông tin adapter sẽ dùng khi tạo HTTP client thực tế.

## 6. Ví dụ Java 17 + Spring Boot 3.5: runnable, kiểm thử đủ các nhánh

Ví dụ gồm một tệp Maven và một tệp test. `CatalogClient` trả về một `QueryPlan` bất biến: URI được tạo từ base URI và SKU đã URL-encode, cùng timeout và số lần thử tối đa. Không gọi dịch vụ thật, giúp kiểm thử rõ giá trị bind và trách nhiệm từng lớp.

### Cấu trúc thư mục

```text
catalog-starter-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── CatalogAutoConfigurationTest.java
```

### Tệp `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>catalog-starter-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### Tệp `src/test/java/example/CatalogAutoConfigurationTest.java`

```java
package example;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
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
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CatalogAutoConfigurationTest {

    // 1. Data-only: giữ cấu hình và default, không chứa nghiệp vụ.
    @ConfigurationProperties(prefix = "acme.catalog")
    public static class CatalogClientProperties {
        private boolean enabled = true;
        private URI baseUri = URI.create("https://catalog.example.test/api");
        private Duration timeout = Duration.ofSeconds(2);
        private int maxAttempts = 3;

        public boolean isEnabled() {
            return enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }

        public URI getBaseUri() {
            return baseUri;
        }

        public void setBaseUri(URI baseUri) {
            this.baseUri = baseUri;
        }

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }
    }

    // 2. API của thư viện, không phụ thuộc Spring.
    record QueryPlan(URI uri, Duration timeout, int maxAttempts) {}

    @FunctionalInterface
    interface CatalogClient {
        QueryPlan planFor(String sku);
    }

    // 3. Hành vi ở implementation, không nằm trong @Configuration.
    static final class DefaultCatalogClient implements CatalogClient {
        private final URI baseUri;
        private final Duration timeout;
        private final int maxAttempts;

        DefaultCatalogClient(URI baseUri, Duration timeout, int maxAttempts) {
            this.baseUri = baseUri;
            this.timeout = timeout;
            this.maxAttempts = maxAttempts;
        }

        @Override
        public QueryPlan planFor(String sku) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU must not be blank");
            }

            String encoded = URLEncoder.encode(sku, StandardCharsets.UTF_8);
            String root = baseUri.toString();
            if (root.endsWith("/")) {
                root = root.substring(0, root.length() - 1);
            }

            URI uri = URI.create(root + "/items?sku=" + encoded);
            return new QueryPlan(uri, timeout, maxAttempts);
        }
    }

    // 4. Auto-configuration chỉ bind + wiring + back-off.
    @AutoConfiguration
    @EnableConfigurationProperties(CatalogClientProperties.class)
    static class CatalogAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        CatalogClient catalogClient(CatalogClientProperties p) {
            return new DefaultCatalogClient(
                p.getBaseUri(), p.getTimeout(), p.getMaxAttempts()
            );
        }
    }

    // 5. Người dùng tự thay thế interface theo nhu cầu.
    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return sku -> new QueryPlan(
                URI.create("https://custom.example.test/request"),
                Duration.ofMillis(250),
                1
            );
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class)
            );

    @Test
    void defaultsAreBoundToTheAutoConfiguredClient() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(CatalogClient.class);
            assertThat(context).hasBean("catalogClient");
            assertThat(context)
                .hasSingleBean(CatalogClientProperties.class);

            CatalogClient client = context.getBean(CatalogClient.class);
            QueryPlan plan = client.planFor("ABC 1");

            assertThat(plan.uri().toString()).isEqualTo(
                "https://catalog.example.test/api/items?sku=ABC+1"
            );
            assertThat(plan.timeout()).isEqualTo(Duration.ofSeconds(2));
            assertThat(plan.maxAttempts()).isEqualTo(3);

            assertThat(context.getEnvironment()
                .containsProperty("acme.catalog.timeout")).isFalse();
            assertThat(context.getBean(CatalogClientProperties.class)
                .getTimeout()).isEqualTo(Duration.ofSeconds(2));
        });
    }

    @Test
    void environmentPropertiesOverrideTheJavaDefaults() {
        runner.withPropertyValues(
                "acme.catalog.base-uri=https://override.example.test/v2/",
                "acme.catalog.timeout=5s",
                "acme.catalog.max-attempts=6"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);

                QueryPlan plan = context.getBean(CatalogClient.class)
                    .planFor("A/B");

                assertThat(plan.uri().toString()).isEqualTo(
                    "https://override.example.test/v2/items?sku=A%2FB"
                );
                assertThat(plan.timeout()).isEqualTo(Duration.ofSeconds(5));
                assertThat(plan.maxAttempts()).isEqualTo(6);
            });
    }

    @Test
    void businessValidationLivesInTheClientNotTheProperties() {
        runner.run(context -> {
            CatalogClient client = context.getBean(CatalogClient.class);

            assertThatThrownBy(() -> client.planFor("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("SKU must not be blank");
        });
    }

    @Test
    void userProvidedBeanMakesTheDefaultBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
            .withPropertyValues("acme.catalog.timeout=7s")
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context).hasBean("customCatalogClient");
                assertThat(context).doesNotHaveBean("catalogClient");

                QueryPlan plan = context.getBean(CatalogClient.class)
                    .planFor("SKU-42");

                assertThat(plan.uri().toString())
                    .isEqualTo("https://custom.example.test/request");
                assertThat(plan.timeout())
                    .isEqualTo(Duration.ofMillis(250));
                assertThat(plan.maxAttempts()).isEqualTo(1);

                // Bean tự tạo không bị factory mặc định cấu hình lại.
                assertThat(context.getBean(CatalogClientProperties.class)
                    .getTimeout()).isEqualTo(Duration.ofSeconds(7));
            });
    }

    @Test
    void disabledPropertyTurnsOffOnlyTheDefaultBean() {
        runner.withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(CatalogClient.class);
                assertThat(context)
                    .hasSingleBean(CatalogClientProperties.class);
                assertThat(context.getBean(CatalogClientProperties.class)
                    .isEnabled()).isFalse();
            });
    }

    @Test
    void disablingDefaultDoesNotForbidAUserBean() {
        runner.withUserConfiguration(UserClientConfiguration.class)
            .withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).hasSingleBean(CatalogClient.class);
                assertThat(context).hasBean("customCatalogClient");
                assertThat(context).doesNotHaveBean("catalogClient");
            });
    }
}
```

### Cách chạy

Dùng JDK 17 trở lên, Maven và kết nối mạng để Maven lấy dependency ban đầu:

```bash
java -version
mvn -version
mvn test
```

**Kết quả mong đợi:** sáu bài kiểm thử JUnit pass; Maven kết thúc với `BUILD SUCCESS`. Không có chuỗi stdout nghiệp vụ xác định, vì chương trình kiểm thử dùng assertions và không gọi `System.out.println`; báo cáo chi tiết do Maven Surefire ghi trong `target/surefire-reports`.

Giải thích:

- **Default:** không có key cấu hình, Spring Boot bind các giá trị khởi tạo của `CatalogClientProperties`; factory tạo `DefaultCatalogClient` và client sử dụng cấu hình qua constructor. `Environment` vẫn có thể không chứa key thiếu.
- **Properties override:** Binder chuyển `base-uri` thành `URI`, `timeout=5s` thành `Duration` và `max-attempts=6` thành số nguyên. Bean mặc định được tạo với giá trị mới.
- **Behavior:** `planFor("   ")` ném lỗi vì SKU không hợp lệ. Quy tắc kiểm tra input đặt ở `DefaultCatalogClient`; properties không có phương thức `planFor`, không biết nghiệp vụ.
- **Bean người dùng:** khi cung cấp một `CatalogClient` khác tên, `@ConditionalOnMissingBean` làm factory mặc định back off. Các properties vẫn có thể được bind, nhưng không được tự ép vào bean thay thế.
- **Disable:** `acme.catalog.enabled=false` làm điều kiện của **bean mặc định** không khớp. Khi ứng dụng tự cung cấp client thì client đó vẫn được giữ.

### Giới hạn có chủ ý của ví dụ

`QueryPlan` chỉ là dữ liệu mô tả request. Trong thư viện HTTP thật, `DefaultCatalogClient` có thể sử dụng `RestClient`, `WebClient` hoặc SDK chính thức, chuyển `Duration` thành timeout của client, thi hành retry policy và chuyển đổi response. Các việc đó cần tài liệu API/thư viện và kiểm thử integration riêng. Không diễn giải ví dụ trên như một HTTP client hoạt động ngoài mạng.

Để dùng auto-configuration trong **starter thật**, tạo file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` ở artifact thư viện và ghi tên class auto-configuration đủ package. Trong demo, `ApplicationContextRunner` đã chủ động load class bằng `AutoConfigurations.of(...)`, vì thế không cần tạo file imports.

## 7. Gắn thuộc tính vào bean: lựa chọn cơ chế phù hợp

Có hai mẫu phổ biến.

### 7.1. Bind vào bean properties riêng rồi truyền qua constructor (khuyên dùng cho integration)

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogClientProperties p) {
    return new DefaultCatalogClient(
        p.getBaseUri(), p.getTimeout(), p.getMaxAttempts()
    );
}
```

Đây là snippet minh họa sử dụng các lớp của ví dụ. Ưu điểm là `DefaultCatalogClient` giữ độc lập với Spring Boot, nhận thông số bất biến ngay từ khởi tạo và có thể được dùng/test bằng Java thuần.

Nếu constructor nhiều tham số, có thể gom chúng thành một **configuration value object** `ClientOptions` bất biến, rồi tạo một lần trong factory:

```java
public record ClientOptions(URI baseUri, Duration timeout, int maxAttempts) {}

@Bean
CatalogClient catalogClient(CatalogClientProperties p) {
    ClientOptions options = new ClientOptions(
        p.getBaseUri(), p.getTimeout(), p.getMaxAttempts()
    );
    return new DefaultCatalogClient(options);
}
```

Đây là phương án thiết kế **minh họa**, phải đổi constructor `DefaultCatalogClient` tương ứng; không được copy song song với constructor ba tham số trong demo mà mong biên dịch. Value object giúp tránh truyền nhầm vị trí tham số và tránh gắn type Spring lên logic xử lý.

### 7.2. Bind trực tiếp lên bean hiện có bằng @ConfigurationProperties trên @Bean

Spring Boot cũng cho phép đặt `@ConfigurationProperties` trên một phương thức `@Bean` để bind properties lên đối tượng được trả về. Điều này hữu ích khi cấu hình một class thư viện bên thứ ba có setters nhưng **không thể sửa source của nó**:

```java
@Bean
@ConfigurationProperties(prefix = "acme.third-party")
ThirdPartyOptions thirdPartyOptions() {
    return new ThirdPartyOptions();
}
```

Đây là snippet cần class `ThirdPartyOptions` phù hợp với JavaBean binding và phải đăng ký bean trong configuration hợp lệ. Nó **không tương đương** việc đặt `@ConfigurationProperties` trên một domain service có side effects; binder sẽ gọi setters của object, nên càng cần chắc chắn object đó là đối tượng cấu hình, không phải một service đang xử lý nghiệp vụ.

Khi thiết kế starter mới, cách rõ ràng nhất thường vẫn là tách properties thành type riêng và tạo bean nghiệp vụ thông qua factory ngắn gọn. Bind trực tiếp lên bean bên thứ ba nên được dùng khi API đó thực sự có mô hình thuộc tính tương thích.

## 8. Ràng buộc giá trị cấu hình và ràng buộc nghiệp vụ là hai việc khác nhau

Không "trộn nghiệp vụ" không có nghĩa properties không được validate. Một **giá trị cấu hình kỹ thuật** cần hợp lệ trước khi khởi tạo client.

Ví dụ các quy tắc hợp lý cho `CatalogClientProperties`:

- `baseUri` không được null và phải là `http` hoặc `https` nếu thư viện chỉ hỗ trợ HTTP.
- `timeout` phải dương nếu adapter yêu cầu thời gian chờ lớn hơn 0.
- `maxAttempts` phải từ 1 trở lên; 0 hoặc âm không có ý nghĩa với thiết kế retry này.

Những quy tắc đó liên quan trực tiếp đến **hợp đồng cấu hình**. Có thể áp dụng Jakarta Bean Validation bằng `@Validated` với các constraint phù hợp và thêm dependency `spring-boot-starter-validation`, hoặc tự validate khi tạo immutable options. **Không được mặc định rằng `spring-boot-starter-test` luôn cung cấp đầy đủ Bean Validation runtime cho mọi starter.**

Ngược lại, "SKU phải tồn tại trong kho", "khách hàng VIP được giảm 10%", "đơn hàng trên hạn mức phải phê duyệt" là **nghiệp vụ**. Chúng thuộc service/domain hoặc client adapter tùy trách nhiệm, không thuộc `CatalogClientProperties`.

### Lưu ý về bất biến

`@ConfigurationProperties` JavaBean mutable với setters phù hợp khi cần binding thông thường. Nếu muốn cấu hình bất biến, trong Spring Boot 3.x có thể dùng một record với constructor binding và `@DefaultValue` cho các thành phần cần default. Khi đó luồng tạo và validation khác với JavaBean; không trộn cả hai kiểu binding lên cùng một object theo cảm tính. Chọn **một chiến lược rõ ràng**, viết test cho key thiếu/override/không hợp lệ.

## 9. Chọn nơi áp dụng default, tùy chỉnh và thay thế

Có ba nguồn gây nhầm lẫn khi thư viện phát triển:

| Nhu cầu | Công cụ | Lưu ý |
| --- | --- | --- |
| Cấu hình host, timeout, pool size, retry parameter | Properties + Binder | Đảm bảo key tồn tại và được factory sử dụng |
| Bổ sung interceptor, codec hoặc cách dựng client mà properties không diễn tả | Customizer hook nếu thư viện cung cấp | Auto-configuration phải **gọi** customizer đó trong lúc tạo bean |
| Thay toàn bộ implementation hoặc lifecycle | Bean người dùng + `@ConditionalOnMissingBean` ở auto-configuration | Bean mặc định back off; custom properties/customizers của factory mặc định không tự được áp lên bean user |

Thực tế, một starter có thể hỗ trợ cả customizer và properties trong quá trình tạo bean mặc định. Tuy nhiên không có quy tắc chung rằng property luôn thắng customizer hoặc ngược lại: **thứ tự áp dụng do code của starter quy định**. Nếu bỏ qua bean mặc định, đường tạo bean đó không chạy, nên phải phân biệt giữa "đã tạo một customizer bean" và "customizer thực sự được áp dụng".

## 10. Các lỗi dễ gặp khi thiết kế starter

### Lỗi 1 — Đưa service và repository vào @ConfigurationProperties

Một lớp properties có phương thức `calculateDiscount(customer)` hoặc gọi database làm cấu hình phụ thuộc nghiệp vụ, khó bind và khó test. Chỉ lưu thông số và xác thực cấu hình tại đây; tách behavior sang service/adapter.

### Lỗi 2 — Đọc Environment trong mỗi lần xử lý request

Code như `environment.getProperty("acme.catalog.timeout")` trong `planFor` khiến implementation lệ thuộc Spring, khó tái sử dụng và có thể áp dụng kiểu conversion/default không nhất quán. Với những tùy chọn cố định trong vòng đời bean, bind một lần và inject qua constructor. Nếu ứng dụng thật cần refresh động, hãy thiết kế cơ chế cập nhật có kiểm soát, không coi lookup Environment mỗi lần là lời giải tự động.

### Lỗi 3 — Tạo hai bộ default khác nhau

`CatalogClientProperties.timeout=2s` nhưng `DefaultCatalogClient` hard-code `5s` nếu không thấy config gây hai nguồn sự thật. Nên chọn một nơi mô tả default chính thức và truyền giá trị cuối cùng. Có thể dùng fallback trong implementation khi nó được sử dụng ngoài Spring, nhưng phải ghi rõ hợp đồng và kiểm thử.

### Lỗi 4 — Đặt @ConditionalOnMissingBean sai nơi hoặc sai kiểu

`@ConditionalOnMissingBean(CatalogClient.class)` trong một class cấu hình thường có thể được đánh giá trước khi user beans cần thiết xuất hiện. Đặt nó trong auto-configuration. Đồng thời, nếu ứng dụng cung cấp `@Bean Object customClient()` rồi mới trả runtime `CatalogClient`, điều kiện có thể không suy ra kiểu đúng từ bean definition. Khai báo kiểu trả về `CatalogClient` hoặc concrete subtype để metadata đủ rõ.

### Lỗi 5 — Thêm @Primary rồi tưởng bean mặc định biến mất

`@Primary` chỉ điều chỉnh ưu tiên inject khi có nhiều ứng viên. Cơ chế tạo/không tạo bean dựa trên condition của auto-configuration. Nếu vẫn có hai bean và logic phụ thuộc tên hoặc `@Qualifier`, `@Primary` không giải quyết triệt để.

### Lỗi 6 — Dùng property enabled như công tắc xóa mọi bean

Nếu `enabled=false` chỉ nằm trên factory bean mặc định, nó **không chặn bean người dùng**. Muốn cấm toàn bộ tính năng trong một ứng dụng, phải định nghĩa chính sách rõ ràng ở điểm sử dụng, thay vì tin một condition trên factory sẽ xóa những bean khác.

### Lỗi 7 — Bất kỳ thay đổi file YAML nào cũng có hiệu lực tức thời

Bean được tạo trong context với snapshot cấu hình ở thời điểm khởi tạo. Sửa file config không đảm bảo bean đã tồn tại thay timeout/lifecycle. Mọi cơ chế refresh động phải được thiết kế và test riêng.

### Lỗi 8 — Factory @Bean tự tạo HTTP request hoặc mở connection trong lúc startup

Nếu constructor hoặc factory thực hiện I/O, startup có thể bị chặn bởi mạng, nhiều test phải mock external services và lỗi endpoint làm ApplicationContext khó lên. Nếu thư viện cần eager startup checks, hãy xem đó là chức năng riêng và cấu hình/kiểm thử có chủ đích; không giấu side effect trong code wiring.

### Lỗi 9 — Tin rằng mọi @Bean đều back off

Spring Boot auto-configuration **chỉ** back off khi condition tương ứng được khai báo và thỏa quy tắc tìm ứng viên. Đọc annotation thực tế và viết test; không thể suy luận chỉ từ tên "AutoConfiguration".

### Lỗi 10 — Cấu hình không được document hay có key trùng namespace

Tên không nhất quán như `acme.catalog.timeout` và `acme.catalog.request-timeout` có thể khiến người dùng đổi sai key. Duy trì prefix rõ ràng, metadata gợi ý IDE và changelog khi đổi contract. Với starter phát hành, có thể bổ sung `spring-boot-configuration-processor` để sinh metadata cấu hình, nhưng metadata chỉ hỗ trợ tooling; nó **không tự bind** hay khởi tạo bean.

## 11. Kiểm thử đủ các nhánh của auto-configuration

Một bộ test cho starter nên kiểm tra:

1. **Key thiếu:** property defaults đúng, bean mặc định xuất hiện hoặc không xuất hiện theo hợp đồng.
2. **Properties được override:** giá trị từ Environment được binder chuyển kiểu chính xác, factory thật sự đưa nó vào implementation.
3. **Hành vi độc lập:** unit test cho client/domain với constructor trực tiếp, không cần khởi tạo Spring context; nghiệp vụ không bị giấu trong config.
4. **Bean người dùng thay thế:** đặt một bean `CatalogClient` đủ kiểu trong user configuration, đảm bảo mặc định back off.
5. **Cờ disable:** xác nhận chỉ bean đúng phạm vi bị chặn.
6. **Giá trị không hợp lệ:** validation nêu thông báo rõ, startup không bỏ qua config xấu và vô tình áp default.
7. **Nhiều beans/điều kiện:** nếu thư viện có nhiều implementation hoặc customizer, test cạnh tranh type/name, order và qualifier.
8. **Nâng cấp framework:** test trên các Spring Boot versions được thư viện công bố hỗ trợ, vì hợp đồng package/API có thể thay đổi.

`ApplicationContextRunner` là công cụ hữu ích để tạo context nhỏ cho các nhánh bean conditions. Mỗi bài test nên chạy context tách biệt, dùng `withPropertyValues(...)` và `withUserConfiguration(...)` để đưa vào dữ liệu cần thiết.

Đối với logic thực sự gọi HTTP, cần **unit test và integration test riêng** cho timeout/retries, lỗi mạng, HTTP status, idempotency và shutdown. Demo `QueryPlan` không phải thay thế các test đó.

## 12. Checklist trước khi phát hành thư viện

- [ ] Key được đặt trong namespace riêng, có default rõ và loại Java phù hợp (`URI`, `Duration`, enum…).
- [ ] Class `@ConfigurationProperties` chỉ chứa dữ liệu và validation cấu hình; không gọi domain service hoặc repository.
- [ ] Auto-configuration dùng `@EnableConfigurationProperties`, tự đăng ký bean mặc định, không trộn nghiệp vụ.
- [ ] Interface nghiệp vụ và implementation được tách; implementation nhận tùy chọn qua constructor hoặc immutable options.
- [ ] `@ConditionalOnMissingBean` dùng đúng kiểu và được đặt trong auto-configuration để ứng dụng thay implementation.
- [ ] Nếu có `enabled`, xử lý key thiếu bằng `matchIfMissing` theo đúng default đã công bố.
- [ ] Kiểm tra default, property override, user bean replacement, disabled và invalid config.
- [ ] Tạo `AutoConfiguration.imports` cho starter thật và đăng ký metadata properties phù hợp.
- [ ] Tài liệu nêu rõ các thuộc tính dùng để chỉnh gì, liệu thay đổi có cần restart không và những bean nào sẽ back off.

## 13. Câu hỏi tự kiểm tra

**Câu 1:** Một phương thức trong `@ConfigurationProperties` gọi repository để xem SKU có còn hàng. Có phù hợp không?  
**Đáp án:** Không; đó là logic nghiệp vụ/I/O. Lớp properties chỉ giữ và validate cấu hình kết nối.

**Câu 2:** `acme.catalog.timeout` vắng mặt nhưng field `timeout` khởi tạo là 2 giây. `Environment#getProperty("acme.catalog.timeout")` có nhất thiết trả về `"2s"` không?  
**Đáp án:** Không. Default của đối tượng Java không được tự đẩy vào Environment.

**Câu 3:** Nếu ứng dụng khai báo `@Bean CatalogClient ownClient()` thì `@ConditionalOnMissingBean(CatalogClient.class)` có cho phép bean mặc định được tạo tiếp không?  
**Đáp án:** Thông thường không, nếu bean ứng dụng đã được xử lý và đủ tư cách làm ứng viên ở thời điểm condition đánh giá.

**Câu 4:** Nếu `acme.catalog.enabled=false`, mọi `CatalogClient` trong toàn context đều biến mất?  
**Đáp án:** Không. Condition trong mẫu chỉ kiểm soát factory bean mặc định; client do người dùng cung cấp có thể vẫn tồn tại.

**Câu 5:** Muốn một integration HTTP client thực thi retry và xử lý response, nên đặt vòng lặp/thuật toán ở đâu?  
**Đáp án:** Trong implementation/adapter hoặc chính sách retry riêng mà nó dùng; properties chỉ chứa tham số như `maxAttempts`, còn auto-configuration chỉ nối các dependency.

**Câu 6:** Một bean `CatalogClientProperties` đã được bind, nhưng bean `DefaultCatalogClient` không nhận được timeout mới. Chẩn đoán đâu trước?  
**Đáp án:** Kiểm tra factory có dùng `getTimeout()` để tạo client hay không, liệu có user bean làm mặc định back off, và source properties có đúng key. Binding thành công không tự ép giá trị vào một bean tùy biến.

## Tài liệu tham khảo

- Spring Boot 3.5 Reference — Externalized Configuration và Binding `@ConfigurationProperties`: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, bean conditions và `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot API — `@EnableConfigurationProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html
- Spring Boot API — `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot Reference — Configuration Metadata: https://docs.spring.io/spring-boot/3.5/reference/configuration-metadata/annotation-processor.html

**Ghi nhớ:** Properties trả lời **“bean mặc định cần những thông số nào?”**; auto-configuration trả lời **“có tạo bean nào, và nối thông số ra sao?”**; implementation/domain trả lời **“hành vi thực sự là gì?”**. Tách đúng các tầng giúp starter dễ cấu hình, dễ thay thế và không làm logic nghiệp vụ phụ thuộc Spring Boot.
