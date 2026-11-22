# Tùy chỉnh bằng thuộc tính, customizer hoặc bean người dùng: chọn đúng mức can thiệp

## 1. Bối cảnh: khi Spring Boot đã auto-configure một thành phần

Trong Spring Boot, **auto-configuration** cung cấp các bean và cấu hình mặc định dựa trên classpath, `Environment` và những bean mà ứng dụng đã đăng ký. Khi muốn đổi hành vi, có ba mức can thiệp thường gặp:

1. **Thuộc tính (properties):** điều chỉnh những lựa chọn đã được Spring Boot hoặc thư viện công khai qua `application.yml`, `application.properties`, biến môi trường… mà vẫn dùng bean do auto-configuration tạo.
2. **Customizer (bean callback):** thêm hoặc thay đổi một phần quá trình xây dựng bean bằng một callback mà auto-configuration **chủ động gọi**; vẫn giữ phần lớn mặc định của framework.
3. **Bean do người dùng định nghĩa (`@Bean`):** tự tạo thành phần thay thế; nếu auto-configuration có điều kiện `@ConditionalOnMissingBean` tương ứng, nhánh tạo bean mặc định sẽ **back off** (không đăng ký).

Đây là ba mức **quyền kiểm soát** khác nhau, không chỉ là ba cách viết cùng một giá trị. Chọn đúng mức giúp tận dụng các mặc định về bảo mật, metrics, resource management và nâng cấp phiên bản. Phần cuối còn phân biệt với **loại trừ hoàn toàn một auto-configuration**, biện pháp rộng hơn và chỉ nên dùng khi thực sự cần.

### Quy tắc chọn nhanh

| Cần thay đổi | Phương án thường phù hợp | Vì sao |
| --- | --- | --- |
| Timeout, endpoint, pool size, logging level hay cờ bật/tắt đã có key chính thức | **Properties** | Dễ cấu hình theo môi trường, ít mã Java, giữ đường đi mặc định |
| Thêm header/interceptor, codec, filter, serializer hay cấu hình builder mà key không hỗ trợ | **Customizer** | Thay đổi phần cụ thể, không mất các thiết lập còn lại |
| Cần implementation, thuật toán khởi tạo, lifecycle, topology hoặc integration khác hẳn | **Bean người dùng** | Toàn quyền tạo đối tượng và dependency |
| Không muốn **cả một nhóm** auto-configuration được áp dụng | **Exclude auto-configuration** | Tắt nhóm cấu hình, có thể kéo theo nhiều bean |

Đây là hướng dẫn quyết định, **không phải lời hứa rằng mọi thư viện đều có đủ cả ba cơ chế**. Phải xem tài liệu và mã auto-configuration thật: một thuộc tính chỉ có tác dụng nếu mã đọc nó, một customizer chỉ có tác dụng nếu mã áp dụng nó, và bean người dùng chỉ làm mặc định back off nếu điều kiện thực tế bao quát kiểu/tên bean đó.

## 2. Hiểu thứ tự và ranh giới can thiệp

Hình dung một auto-configuration điển hình có luồng:

```text
                Environment / PropertySources
                           |
                           v
               @ConfigurationProperties
                           |
                           v
               cấu hình mặc định cho Builder
                           |
                           v
       ObjectProvider<Customizer>.orderedStream()
                 áp dụng từng customizer
                           |
                           v
                       build()
                           |
                           v
          bean mặc định của auto-configuration
             (chỉ khi điều kiện khớp)
                           
Nếu người dùng đăng ký bean cùng kiểu phù hợp:
    @ConditionalOnMissingBean -> không đăng ký bean mặc định.
    Đường build() ở trên không chạy cho bean mặc định đó.
```

Đây là **một thiết kế mẫu**, không phải pipeline bắt buộc của mọi Spring Boot auto-configuration. Một số thành phần áp dụng customizer trước/bên trong builder configurer, một số dùng post-processor, một số không có builder. Hãy kiểm tra điểm được gọi và thứ tự thực tế.

Có hai thời điểm phải phân biệt:

- **Đăng ký bean definition:** Spring đánh giá `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và điều kiện khác. Các điều kiện bean chỉ nhìn thấy những định nghĩa đã được xử lý đến lúc đó. Auto-configuration được xử lý sau các cấu hình người dùng nên thích hợp làm nơi đặt điều kiện back-off.
- **Khởi tạo bean:** khi một phương thức `@Bean` được gọi, code nhận properties, customizers và các dependency, rồi xây đối tượng. Nếu điều kiện khiến phương thức bị loại, callback nằm **bên trong phương thức đó** không tự chạy cho bean do người dùng cung cấp.

`@Primary` và `@Qualifier` có thể tác động tới **chọn bean khi inject**; chúng không có nghĩa là Spring đã hủy bean mặc định. Ngược lại, `@ConditionalOnMissingBean` có thể ngăn hẳn bean mặc định được đăng ký, ngay trước bước inject.

## 3. Mức 1 — Tùy chỉnh bằng properties

### 3.1. Cách hoạt động

Spring Boot dùng `Environment` và `@ConfigurationProperties` để ánh xạ cấu hình thành các kiểu Java; ví dụ:

```properties
demo.client.base-url=https://api.example.test
demo.client.timeout=5s
demo.client.enabled=true
```

Trong một starter thiết kế tốt, `@ConfigurationProperties(prefix="demo.client")` giữ các setting như `baseUrl` và `timeout`, còn `@ConditionalOnProperty` có thể quyết định có tạo bean hay không. Có thể đặt key tương đương trong YAML:

```yaml
demo:
  client:
    base-url: https://api.example.test
    timeout: 5s
    enabled: true
```

Ưu điểm:

- Cấu hình theo dev/test/prod, container, profile hoặc biến môi trường mà không thay đổi code; các nguồn `PropertySource` có thứ tự ưu tiên.
- Binder hỗ trợ chuyển đổi kiểu như `Duration`, `URI`, danh sách, enum… và có thể xác thực cấu hình bằng Bean Validation khi dự án hỗ trợ.
- Phù hợp với các giá trị mà starter **đã công bố** để người dùng điều khiển.

Giới hạn:

- Không thể giả định rằng mọi setter trên một thư viện đều có key tương ứng.
- Một giá trị mặc định đặt trong field của `@ConfigurationProperties` **không tự xuất hiện trong Environment**.
- Nếu muốn điều kiện bật khi thiếu key, cần cấu hình `matchIfMissing` phù hợp; điều kiện không tự đọc giá trị sau binding của bean properties.
- Thay properties không bảo đảm cập nhật bean đã khởi tạo trong context đang chạy; thường cần restart/recreate context hoặc cơ chế refresh do ứng dụng thiết kế riêng.
- Properties có thể bị ghi đè từ nguồn ưu tiên cao hơn. Khi kết quả bất ngờ, hãy kiểm tra nguồn cuối cùng thay vì chỉ đọc một file.

**Ví dụ minh họa, không phải property có sẵn của Spring Boot:** các key `demo.client.*` ở trên do chính auto-configuration mẫu trong mục 6 định nghĩa. Chúng không thuộc namespace mặc định của Spring Boot.

### 3.2. Khi nào không nên nâng lên customizer

Nếu tài liệu đã cung cấp `spring.task.execution.pool.max-size` để cấu hình một thread pool thích hợp, viết custom `Executor` chỉ để đổi kích thước pool có thể làm thay đổi cả cách Boot chọn executor. Tương tự, khi chỉ cần đổi timeout HTTP mà component có property/builder setting chính thức, dùng cấu hình được hỗ trợ thường giảm công bảo trì hơn.

Không có thứ tự ưu tiên **toàn cục** kiểu "properties luôn thắng customizer" hoặc ngược lại. Thứ tự do code thiết kế quyết định. Trong ví dụ mục 6, properties được đưa vào builder **trước** customizer nên customizer ghi cùng trường sau đó sẽ thắng.

## 4. Mức 2 — Tùy chỉnh bằng customizer

### 4.1. Customizer là hợp đồng mở rộng, không phải một annotation thần kỳ

Một customizer là callback/interface được auto-configuration hỗ trợ, ví dụ `ClientCustomizer` với phương thức `customize(Builder)`. Ứng dụng đăng ký một bean triển khai interface; auto-configuration tập hợp và gọi nó khi tạo bean của chính mình.

Mẫu cơ bản:

```java
@FunctionalInterface
interface ClientCustomizer {
    void customize(Client.Builder builder);
}

// Trong auto-configuration:
@Bean
Client client(ClientProperties properties,
              ObjectProvider<ClientCustomizer> customizers) {
    Client.Builder builder = Client.builder()
        .timeout(properties.getTimeout());

    customizers.orderedStream()
        .forEach(customizer -> customizer.customize(builder));

    return builder.build();
}
```

Đoạn trên chỉ mô tả **ý tưởng**: `Client`, `ClientProperties` và imports là các kiểu giả định, chưa phải chương trình đầy đủ. Mục 6 cung cấp tệp Java biên dịch được với `DemoClient` và `DemoClientCustomizer`.

Điểm mấu chốt là lời gọi `customizers.orderedStream()...`. Nếu auto-configuration không đọc bean customizer thì **chỉ khai báo một callback bean sẽ không có tác dụng**. Ngay cả với Spring Boot có sẵn, một customizer cho builder được Boot quản lý thường không tự áp dụng cho mọi builder bạn tự tạo bằng `new` hoặc phương thức factory khác.

Các ví dụ API trong Spring Boot 3.5 có `org.springframework.boot.web.client.RestClientCustomizer` để thay đổi `RestClient.Builder`; các thành phần JSON cũng có những hook cụ thể. Tên và package có thể đổi giữa Spring Boot 3.x/4.x: luôn xem API của phiên bản đang dùng.

### 4.2. Thứ tự nhiều customizer

Khi auto-configuration dùng `ObjectProvider<T>.orderedStream()`, Spring sắp xếp theo các quy tắc `Ordered`/`@Order`. Giá trị order nhỏ hơn được xử lý trước. Ví dụ nếu hai customizer đều chỉnh cùng `label`:

```java
@Bean
@Order(10)
DemoClientCustomizer first() {
    return builder -> builder.label("first");
}

@Bean
@Order(20)
DemoClientCustomizer second() {
    return builder -> builder.label("second");
}
```

Giả sử các bean này được gọi **theo `orderedStream()` và không có callback khác ghi lại `label`**, kết quả cuối cùng là `"second"` vì customizer thứ hai được áp dụng sau. Đoạn này là snippet minh họa nằm trong một class cấu hình, cần imports và những kiểu được định nghĩa ở ví dụ đầy đủ.

Không suy luận "customizer có `@Order(1)` sẽ luôn ưu tiên cao nhất" khi **cùng ghi đè một trường**: nếu logic đơn giản là gọi các setter tuần tự, callback chạy **sau** mới là callback quyết định giá trị cuối. Khi cùng order hoặc không khai báo order, tránh phụ thuộc vào thứ tự ngẫu nhiên; đặt thứ tự rõ ràng hoặc tách trách nhiệm customizer.

### 4.3. Khi customizer phù hợp

Nên dùng khi bạn cần thêm interceptor, header policy, serialization module, mapper options, callback, connection customization... nhưng vẫn muốn auto-configuration chịu trách nhiệm tạo, đăng ký và đóng bean chính.

Hãy lưu ý:

- Customizer đôi khi được gọi cho **nhiều builder/nhiều bean**, vì vậy nên tránh tác dụng phụ không mong đợi, đặc biệt thao tác I/O hoặc thay đổi singleton chia sẻ trong callback.
- Nếu callback chạy trước khi bean hoàn tất, đừng trông chờ bean mục tiêu đã tồn tại để inject ngược vào chính customizer đó; có thể gây circular dependency.
- Ưu tiên customizer idempotent khi API có khả năng gọi lặp.
- Không dùng customizer để thay đổi cấu trúc mà builder/API không hỗ trợ; lúc này cần bean người dùng hoặc cơ chế mở rộng khác.
- Có những hook áp dụng cho builder, những hook áp dụng cho **đối tượng sau xây dựng**; hiệu lực và thứ tự không thể suy ra chỉ từ tên interface.

## 5. Mức 3 — Tạo bean người dùng và cơ chế back-off

### 5.1. Điều kiện @ConditionalOnMissingBean

Trong auto-configuration, mẫu phổ biến:

```java
@Bean
@ConditionalOnMissingBean(DemoClient.class)
DemoClient demoClient(...) {
    // Tạo bean mặc định.
}
```

Khi ứng dụng tự cung cấp một bean loại `DemoClient` phù hợp, Spring Boot **không đăng ký** bean `demoClient` mặc định. Đây là *back-off*: bean người dùng vẫn hoạt động theo cách họ tạo; Boot không tự lấy property/customizer của bean mặc định rồi áp lên bean tùy biến.

Có thể để annotation không khai báo `value` trên phương thức `@Bean`: khi đó Spring Boot suy ra kiểu cần kiểm tra từ **kiểu trả về** của phương thức. Tuy nhiên `@ConditionalOnMissingBean(DemoClient.class)` làm ý định rõ ràng và tránh phụ thuộc vào việc suy ra từ một kiểu trả về quá rộng.

Điều kiện có thể so khớp theo **kiểu**, **tên** hoặc các tiêu chí khác theo cấu hình annotation. Không phải mọi auto-configuration đều back off theo cùng cách; ví dụ trong vài tích hợp tên bean cụ thể như `applicationTaskExecutor` cũng là một hợp đồng quan trọng. Hãy tra các điều kiện thực tế trong auto-configuration đang dùng.

### 5.2. @Primary, bean definition overriding và back-off khác nhau

- `@Primary`: chọn một bean làm ứng viên mặc định khi có nhiều bean tương thích được inject. **Không tự ngăn đăng ký** bean auto-configured.
- `@Qualifier`: chỉ định bean tại điểm inject; không tạo hoặc xóa bean auto-configured.
- **Back-off**: nếu `@ConditionalOnMissingBean` không khớp, bean mặc định bị bỏ qua khi đăng ký; đây là cơ chế có chủ đích của auto-configuration.
- **Bean definition overriding**: hai định nghĩa trùng tên có thể gây lỗi; bật `spring.main.allow-bean-definition-overriding=true` không phải cách được khuyến nghị để thay thế bình thường. Dựa vào back-off đúng kiểu/tên giúp rõ ý định hơn.
- **Exclude auto-configuration**: loại bỏ cả auto-configuration ra khỏi danh sách ứng viên, rộng hơn việc một `@Bean` back off.

**Đừng mặc định rằng chỉ cần đặt cùng tên với bean mặc định là Boot sẽ thay nó.** Nếu condition kiểm tra **kiểu**, một bean khác kiểu nhưng trùng tên không đáp ứng điều kiện và có thể gây lỗi trùng tên. Ngược lại, nếu condition kiểm tra kiểu `DemoClient`, một bean cùng kiểu nhưng tên `manualClient` cũng có thể khiến bean mặc định back off.

### 5.3. Hệ quả khi dùng bean thay thế

Bean người dùng chịu trách nhiệm về constructor, cấu hình, kết nối, timeout, lifecycle, metrics/tracing, SSL, decorators và tương thích với code phụ thuộc. Các tiện ích của auto-configuration **không tự động được sao chép** sang bean ấy.

Cần kiểm tra những bean khác phụ thuộc vào bean mặc định. Đôi khi auto-configuration chỉ back off một bean, còn các bean phụ trợ vẫn được tạo; đôi khi condition đặt trên class có thể làm cả nhóm bị loại. Đọc chính xác nơi đặt annotation và chạy test cho cấu trúc bean sau khi thay thế.

Đặc biệt với bean có interface chung, hãy nêu kiểu trả về của `@Bean` đủ cụ thể để điều kiện có metadata đáng tin. Nếu đăng ký `@Bean Object manualClient()` nhưng runtime mới trả về `DemoClient`, việc suy luận kiểu trước khi instantiate có thể không nhận ra bean thay thế.

## 6. Ví dụ hoàn chỉnh với Java 17 và Spring Boot 3.5

Mục tiêu: tạo một client mẫu không thực hiện I/O mạng, chỉ lưu cấu hình bất biến. Ví dụ kiểm chứng chính xác ba mức can thiệp:

1. Không cấu hình gì: auto-configuration tạo `DemoClient` với default.
2. Đặt property: client mặc định được tạo với giá trị từ `Environment`.
3. Đăng ký `DemoClientCustomizer`: client mặc định tiếp tục được tạo, nhưng customizer sửa builder sau khi gán properties.
4. Tự đăng ký `DemoClient`: auto-configuration back off; customizer dùng trong nhánh mặc định **không tự thay đổi** bean người dùng.
5. Đặt `demo.client.enabled=false`: tắt việc tạo **bean mặc định**.

Ví dụ sử dụng `ApplicationContextRunner` nên không cần web server hay máy chủ API. Phần code là mô hình của một auto-configuration do mình viết, **không phải cam kết rằng Spring Boot có sẵn `demo.client.*` hoặc `DemoClientCustomizer`**.

### Cấu trúc thư mục

```text
customization-choice-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── CustomizationChoiceTest.java
```

### Tệp pom.xml

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
    <artifactId>customization-choice-demo</artifactId>
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

### Tệp src/test/java/example/CustomizationChoiceTest.java

```java
package example;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
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

class CustomizationChoiceTest {

    @ConfigurationProperties(prefix = "demo.client")
    public static class DemoClientProperties {
        private URI baseUrl = URI.create("https://api.example.test");
        private Duration timeout = Duration.ofSeconds(2);

        public URI getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(URI baseUrl) {
            this.baseUrl = baseUrl;
        }

        public Duration getTimeout() {
            return timeout;
        }

        public void setTimeout(Duration timeout) {
            this.timeout = timeout;
        }
    }

    // Đối tượng bất biến; không tạo kết nối mạng trong test.
    record DemoClient(URI baseUrl, Duration timeout, String label) {

        static Builder builder() {
            return new Builder();
        }

        static final class Builder {
            private URI baseUrl;
            private Duration timeout;
            private String label = "auto";

            Builder baseUrl(URI value) {
                this.baseUrl = value;
                return this;
            }

            Builder timeout(Duration value) {
                this.timeout = value;
                return this;
            }

            Builder label(String value) {
                this.label = value;
                return this;
            }

            DemoClient build() {
                return new DemoClient(baseUrl, timeout, label);
            }
        }
    }

    @FunctionalInterface
    interface DemoClientCustomizer {
        void customize(DemoClient.Builder builder);
    }

    @AutoConfiguration
    @EnableConfigurationProperties(DemoClientProperties.class)
    static class DemoClientAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(DemoClient.class)
        @ConditionalOnProperty(
            prefix = "demo.client",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        DemoClient demoClient(
                DemoClientProperties properties,
                ObjectProvider<DemoClientCustomizer> customizers) {

            DemoClient.Builder builder = DemoClient.builder()
                .baseUrl(properties.getBaseUrl())
                .timeout(properties.getTimeout());

            customizers.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

            return builder.build();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCustomizerConfiguration {
        @Bean
        DemoClientCustomizer tuneClient() {
            return builder -> builder
                .timeout(Duration.ofSeconds(8))
                .label("tuned");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserBeanConfiguration {
        @Bean
        DemoClient manualClient() {
            return new DemoClient(
                URI.create("https://manual.example.test"),
                Duration.ofSeconds(42),
                "manual"
            );
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(DemoClientAutoConfiguration.class)
            );

    @Test
    void defaultBeanUsesJavaDefaults() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(DemoClient.class);
            assertThat(context).hasBean("demoClient");

            DemoClient client = context.getBean(DemoClient.class);
            assertThat(client.baseUrl())
                .isEqualTo(URI.create("https://api.example.test"));
            assertThat(client.timeout())
                .isEqualTo(Duration.ofSeconds(2));
            assertThat(client.label()).isEqualTo("auto");
        });
    }

    @Test
    void propertiesChangeTheAutoConfiguredBean() {
        runner.withPropertyValues(
                "demo.client.base-url=https://configured.example.test",
                "demo.client.timeout=5s"
            )
            .run(context -> {
                DemoClient client = context.getBean(DemoClient.class);
                assertThat(client.baseUrl())
                    .isEqualTo(
                        URI.create("https://configured.example.test")
                    );
                assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(5));
                assertThat(client.label()).isEqualTo("auto");
            });
    }

    @Test
    void customizerChangesTheBuilderAfterPropertyBinding() {
        runner.withUserConfiguration(UserCustomizerConfiguration.class)
            .withPropertyValues("demo.client.timeout=5s")
            .run(context -> {
                assertThat(context).hasSingleBean(DemoClient.class);
                assertThat(context).hasBean("demoClient");

                DemoClient client = context.getBean(DemoClient.class);
                assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(8));
                assertThat(client.label()).isEqualTo("tuned");
            });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        runner.withUserConfiguration(
                UserBeanConfiguration.class,
                UserCustomizerConfiguration.class
            )
            .withPropertyValues("demo.client.timeout=5s")
            .run(context -> {
                assertThat(context).hasSingleBean(DemoClient.class);
                assertThat(context).hasBean("manualClient");
                assertThat(context).doesNotHaveBean("demoClient");

                DemoClient client = context.getBean(DemoClient.class);
                assertThat(client.baseUrl())
                    .isEqualTo(URI.create("https://manual.example.test"));
                assertThat(client.timeout())
                    .isEqualTo(Duration.ofSeconds(42));
                assertThat(client.label()).isEqualTo("manual");
            });
    }

    @Test
    void enabledFalseDisablesOnlyTheAutoConfiguredClient() {
        runner.withPropertyValues("demo.client.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(DemoClient.class);
                assertThat(context)
                    .hasSingleBean(DemoClientProperties.class);
            });
    }
}
```

### Chạy và diễn giải

Ở thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
```

**Kết quả kỳ vọng:** cả **5 test** của `CustomizationChoiceTest` pass và Maven báo `BUILD SUCCESS` (nếu dependency được tải và môi trường hoạt động bình thường). Code không in stdout nghiệp vụ cố định. Kết quả chi tiết thường nằm trong `target/surefire-reports`. Không cần gọi URL `example.test` vì demo chỉ lưu `URI`.

Cách đọc 5 test:

| Test | Can thiệp | Bean chính nhận được |
| --- | --- | --- |
| `defaultBeanUsesJavaDefaults` | Không cung cấp gì | `demoClient` có timeout 2 giây và label `auto` |
| `propertiesChangeTheAutoConfiguredBean` | Property base URL và timeout | `demoClient` có timeout 5 giây và URL mới |
| `customizerChangesTheBuilderAfterPropertyBinding` | Property timeout 5 giây và customizer | `demoClient` có timeout 8 giây, label `tuned` |
| `userBeanMakesDefaultBackOff` | Bean tự định nghĩa, thêm cả property/customizer | Chỉ `manualClient` với timeout 42 giây, label `manual` |
| `enabledFalseDisablesOnlyTheAutoConfiguredClient` | Property `enabled=false` | Không có `DemoClient` mặc định; `DemoClientProperties` vẫn tồn tại |

**Lưu ý về thứ tự trong ví dụ:** chính `DemoClientAutoConfiguration.demoClient(...)` gán giá trị properties trước, rồi mới gọi `customizers.orderedStream()`. Nếu sửa code để customizer chạy trước properties, kết quả khi cả hai cùng chỉnh timeout có thể đảo ngược. Không thể mở rộng quy tắc "customizer thắng property" thành cam kết cho mọi starter.

**Lưu ý về thay thế:** trong test `userBeanMakesDefaultBackOff`, user bean có tên `manualClient`, khác `demoClient`. Bean vẫn làm auto-configured `demoClient` back off vì condition kiểm tra **kiểu `DemoClient`**, không đòi cùng tên. Và customizer không được tự áp dụng vào `manualClient` vì phương thức tạo bean mặc định đã không chạy.

`ApplicationContextRunner` là công cụ kiểm thử auto-configuration (dùng trong unit/integration tests, không phải một Spring Boot application chạy production). Trong auto-configuration được đóng gói thành starter thật, cần công bố lớp auto-configuration trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; ví dụ test chủ động nạp nó bằng `AutoConfigurations.of(...)` nên không cần file imports này.

## 7. Một số tình huống chọn mức can thiệp trong dự án

### Tình huống A: đổi timeout của thành phần đã hỗ trợ key

**Chọn properties.** Kiểm tra tài liệu cấu hình hiện hành, key, đơn vị thời gian và hệ quả của profile. Chỉ chuyển sang customizer khi key không diễn tả được yêu cầu hoặc khi cần logic tùy chỉnh thay cho giá trị cố định.

### Tình huống B: bổ sung header chuẩn cho HTTP client do Boot cấp

**Chọn customizer dành cho builder/HTTP client đó**, ví dụ loại callback mà Spring Boot 3.5 có `RestClientCustomizer`, nếu bạn đang dùng bean/builder được auto-configuration quản lý và hook được gọi. Kiểm tra thứ tự với những customizer do framework đăng ký để không vô tình thay thế các cấu hình cần giữ.

Không cần định nghĩa `RestClient.Builder` hoặc `RestClient` mới chỉ để thêm một header nếu hook chính thức đã đáp ứng. Nếu ứng dụng tự gọi `RestClient.builder()` và bỏ qua builder được Boot cấp, hook phụ thuộc builder của Boot có thể không được dùng.

### Tình huống C: thay giao thức hoặc tích hợp HTTP client đặc thù

**Chọn bean tự tạo** khi cần kiểm soát toàn bộ factory, lifecycle và các dependency mà customizer không đáp ứng. Kiểm tra `@ConditionalOnMissingBean`, kiểu, tên bean, annotation khác và bean phụ trợ. Nếu cần vẫn giữ một phần mặc định, xem builder/configurer mà Boot cung cấp hoặc cơ chế tùy chỉnh khác trước khi tự xây mọi thứ.

### Tình huống D: có một bean dự phòng trong starter nhưng ứng dụng muốn dùng implementation riêng

**Chọn bean người dùng** và để starter dùng `@ConditionalOnMissingBean`. Trong code starter, bảo đảm điều kiện chỉ xuất hiện trong auto-configuration và kiểu trả về `@Bean` đủ rõ. Tránh yêu cầu người dùng đổi cờ bean-definition-overriding toàn ứng dụng chỉ để thay thế một bean.

### Tình huống E: muốn tắt hoàn toàn cấu hình datasource mặc định

Nếu thật sự **không muốn** Spring Boot tạo datasource từ auto-configuration, có thể loại trừ class auto-configuration tương ứng:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Hoặc cấu hình trên class ứng dụng (snippet, cần dependency Spring Boot tương ứng):

```java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

Đây là **loại trừ một auto-configuration thực sự**, không phải back-off của một `@Bean` đơn lẻ. Nó có thể làm các chức năng phụ thuộc datasource không được khởi tạo. Đừng exclude `DataSourceAutoConfiguration` chỉ vì muốn đổi JDBC URL, username, pool properties; trường hợp đó thường nên cấu hình `spring.datasource.*`.

`spring.autoconfigure.exclude` nhận tên **class auto-configuration** được Boot nhận diện; không dùng tùy ý để tắt một class `@Configuration` ứng dụng. Khi dùng snippet Java cần import `org.springframework.boot.autoconfigure.SpringBootApplication`, `org.springframework.boot.SpringApplication` và `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`; đây không phải tệp trong demo test mục 6.

## 8. Vấn đề thứ tự và độ ưu tiên trong thực tế

### 8.1. Không có hệ thống ưu tiên chung cho ba cơ chế

Ví dụ mẫu áp dụng properties rồi customizers. Khi xuất hiện bean người dùng, phần build mặc định bị bỏ qua. Nhưng auto-configurations khác có thể dùng:

- Customizer để thay đổi một builder **trước** bước binding hoặc apply các configurer của framework.
- Bean post-processor chạy **sau** khi bean được tạo (khác customizer builder).
- Một customizer chỉ đăng ký nếu classpath có class cần thiết hoặc property bật.
- Điều kiện chỉ back off theo tên, chỉ theo type, hoặc yêu cầu nhiều tiêu chí.

Vì vậy, câu đúng không phải "thường ưu tiên bean > customizer > property" như một phép toán toàn cục; phải xem **nơi từng cơ chế được áp dụng và điều kiện nào đang kiểm tra**.

### 8.2. Khi có nhiều bean cùng kiểu

Nếu tự tạo `@Primary DemoClient customClient()` trong khi mặc định vẫn được đăng ký do điều kiện khác, có thể tồn tại cả hai bean. `@Primary` chỉ ảnh hưởng resolution tại điểm inject không có qualifier; nó không bảo đảm mọi code sẽ chọn bean đó, đặc biệt với `@Qualifier` hoặc truy vấn theo tên.

Nếu đã có một auto-configured bean và chỉ muốn thay hành vi trong phạm vi hẹp, dùng customizer cho đúng đối tượng hoặc bean được đặt tên chính xác có thể ít rủi ro hơn. Nếu muốn back off, phải kiểm tra liệu điều kiện thực tế có bỏ qua bean `defaultCandidate=false`, bean không đủ điều kiện autowire hoặc kiểu generic đặc biệt hay không.

### 8.3. Hệ quả đối với upgrade

Thay properties được hỗ trợ thường dễ nâng cấp hơn vì code framework giữ nhiệm vụ dựng bean. Customizer phụ thuộc API hook cụ thể nên cần theo dõi phiên bản. Bean thay thế mang phần lớn trách nhiệm tích hợp; cần kiểm thử lại khi Framework/Boot thay đổi phương thức khởi tạo, tracing, metrics, SSL, timeouts, thread model hoặc lifecycle.

Đó là **xu hướng bảo trì**, không phải thứ tự hiệu quả tuyệt đối. Nếu yêu cầu thực sự cần một implementation khác thì bean thay thế vẫn là lựa chọn đúng.

## 9. Chẩn đoán khi cấu hình không có tác dụng

1. **Sai key hoặc nguồn cấu hình:** tra metadata `@ConfigurationProperties`, log thuộc tính hợp lệ, profile và thứ tự `PropertySource`. Một thuộc tính sai chính tả có thể được bỏ qua, tùy validation/binding; không nên kết luận "Boot bỏ qua" trước khi kiểm tra tên thực.
2. **Customizer không được gọi:** xác nhận bean có đúng interface, được scan/import vào cùng ApplicationContext, không bị điều kiện lọc, và auto-configuration có lấy nó qua dependency hoặc `ObjectProvider`.
3. **Customizer được gọi nhưng giá trị bị ghi đè:** kiểm tra thứ tự `@Order`, thứ tự builder/configurer, những callback khác sửa cùng setting, hoặc việc tạo instance mới không dùng builder được tùy chỉnh.
4. **Bean mặc định vẫn còn:** xem `@ConditionalOnMissingBean` kiểm tra kiểu hay tên gì; xem kiểu khai báo trên phương thức `@Bean` và bean có đủ tư cách làm ứng viên không.
5. **Bean tùy chỉnh không tồn tại:** kiểm tra `@Configuration` có được nạp, bean bị profile/condition loại hay chưa, lỗi khởi tạo dependency, hoặc do trùng tên.
6. **Bean mặc định không còn nhưng hệ thống lỗi:** bean thay thế có thể thiếu các khả năng/nhãn/qualifier phụ thuộc của phần còn lại. Kiểm tra những integration được Boot quản lý.
7. **Đã exclude quá rộng:** tìm class nằm trong `spring.autoconfigure.exclude` hoặc `@SpringBootApplication(exclude=...)`; một nhóm auto-config phụ trợ có thể không được đăng ký.
8. **Nhầm thời điểm đánh giá:** `@ConditionalOnMissingBean` kiểm tra bean definition đã được xử lý đến thời điểm condition được đánh giá; Spring Boot khuyến nghị đặt loại điều kiện này ở auto-configuration, không trong cấu hình thường không có bảo đảm thứ tự.

Để đọc báo cáo điều kiện của ứng dụng Spring Boot có executable jar, có thể chạy:

```bash
java -jar app.jar --debug
```

Với Spring Boot Actuator đã được cài và cấu hình endpoint phù hợp, `/actuator/conditions` thể hiện báo cáo condition; `/actuator/configprops` giúp kiểm tra các bean `@ConfigurationProperties` đã bind. Không nên mở công khai các endpoint chẩn đoán nhạy cảm trên hệ thống production. Với một auto-configuration tự viết, các test `ApplicationContextRunner` trong mục 6 cung cấp kiểm tra tự động rõ ràng hơn.

## 10. Các lỗi thiết kế thường gặp và cách sửa

- **Viết bean mới cho một setting đơn giản:** dễ làm mất mặc định. Hãy dùng property đã công bố trước.
- **Tin rằng bất kỳ bean có hậu tố "Customizer" đều tự được áp dụng:** bắt buộc phải có nơi gọi hook.
- **Dùng customizer của builder nhưng lại tự tạo builder mới:** hook áp dụng trong pipeline quản lý builder, không tự chạy với mọi đối tượng cùng kiểu.
- **Nhầm `@Primary` với back-off:** đây là hai cơ chế độc lập.
- **Dùng `spring.main.allow-bean-definition-overriding=true` làm giải pháp tổng quát:** che giấu xung đột tên và tạo phụ thuộc khó theo dõi; hãy dùng bean type/condition hợp lệ.
- **Đặt `@ConditionalOnMissingBean` trong cấu hình người dùng xử lý sớm:** có thể nhìn thấy ít bean definition hơn dự kiến; đặt điều kiện vào auto-configuration.
- **Viết `@Bean Object customClient()` cho đối tượng thực thuộc `DemoClient`:** metadata quá rộng có thể khiến condition không nhận diện khi cần.
- **Đặt nhiều customizer sửa một field mà không định thứ tự:** kết quả có thể khó dự đoán.
- **Cho rằng customizer vẫn chạy khi bean mặc định back off:** nếu callback chỉ được gọi trong phương thức tạo bean mặc định, nó không chạy cho bean người dùng.
- **Exclude cả auto-configuration chỉ để thay một bean:** có thể mất nhiều bean phụ trợ; thường chỉ cần bean override bằng back-off.
- **Không kiểm tra test trên nhiều kịch bản:** phải test default, property-only, customizer, replacement và disablement.

## 11. Checklist quyết định trước khi can thiệp

Trả lời theo thứ tự:

1. **Tôi cần đổi cái gì?** Một giá trị được công bố, một bước builder, hay toàn bộ implementation?
2. **Có property chính thức không?** Tìm trong Spring Boot reference/metadata và tài liệu starter; xác định kiểu, default, đơn vị, ảnh hưởng theo môi trường.
3. **Có hook customizer chính thức không?** Kiểm tra interface, nơi auto-configuration gọi, thứ tự, phạm vi và lifecycle.
4. **Nếu đăng ký bean riêng, điều kiện back-off là gì?** Kiểm tra `@ConditionalOnMissingBean` theo kiểu/tên và những điều kiện đi kèm; tránh dự đoán.
5. **Những mặc định nào tôi sẽ phải tự mang theo?** Timeout, headers, tracing, metrics, resources, SSL, thread management, shutdown và tích hợp liên quan.
6. **Có thật sự cần exclude không?** Dành cho việc tắt cả một auto-configuration; hiểu rõ tác động lên các bean phụ trợ.
7. **Đã kiểm thử ít nhất các nhánh nào?** Không tùy chỉnh; property; customizer; bean người dùng; tắt qua property; trường hợp nhiều customizer/multiple beans nếu thực tế có.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Muốn đổi timeout mà starter đã có key chính thức, có nhất thiết phải định nghĩa `@Bean` mới không?  
**Đáp án:** Không. Property đủ khi auto-configuration dùng key đó.

**Câu 2.** Một customizer bean đã có mặt nhưng auto-configuration không inject hay gọi nó. Giá trị builder có tự thay đổi không?  
**Đáp án:** Không. Bean callback cần một điểm gọi cụ thể trong quá trình cấu hình.

**Câu 3.** `@ConditionalOnMissingBean(DemoClient.class)` sẽ back off nếu người dùng định nghĩa bean cùng kiểu tên `manualClient`?  
**Đáp án:** Có, giả sử bean là ứng viên được xét ở thời điểm đánh giá condition, vì ở đây điều kiện dựa trên kiểu.

**Câu 4.** Nếu tạo bean `DemoClient` bằng tay, customizer trong phương thức `demoClient(...)` có tự chạy với bean đó không?  
**Đáp án:** Không, nếu chính phương thức auto-configured đã back off và không có nơi khác gọi customizer.

**Câu 5.** Đánh dấu bean người dùng `@Primary` có phải là xóa bean auto-configured?  
**Đáp án:** Không. `@Primary` chỉ có vai trò trong chọn dependency; back-off phụ thuộc điều kiện bean của auto-configuration.

**Câu 6.** Muốn bỏ hoàn toàn một nhóm auto-configuration thay vì chỉ đổi timeout, nên cân nhắc gì?  
**Đáp án:** Có thể exclude class auto-configuration phù hợp, nhưng kiểm tra những bean phụ trợ bị mất và lý do cần loại bỏ cả nhóm.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — **Creating Your Own Auto-configuration** (bean conditions, back-off, thứ tự và `ApplicationContextRunner`): https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — **Externalized Configuration** (`Environment`, `@ConfigurationProperties`, conversion, nguồn ưu tiên): https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Framework 6.2 Javadoc — `ObjectProvider.orderedStream()` và quy tắc `@Order`: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/beans/factory/ObjectProvider.html
- Spring Boot 3.5 API — `RestClientCustomizer`, ví dụ hook cho HTTP client: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
- Spring Boot 3.5 Reference — **Task Execution and Scheduling** (property, custom executor và các quy tắc bean names): https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html

**Ghi nhớ:** chỉnh **giá trị** bằng property khi được hỗ trợ; chỉnh **một phần đường xây bean** bằng customizer khi hook thực sự được gọi; **thay đối tượng** bằng bean của người dùng khi cần toàn quyền và điều kiện back-off phù hợp. Exclude chỉ khi muốn loại bỏ auto-configuration ở phạm vi rộng hơn. Trước khi quyết định, đọc điều kiện và thử nghiệm đúng nhánh cấu hình đang dùng.
