# Cố ý tạo lỗi đăng ký, điều kiện và xung đột bean rồi chẩn đoán theo bằng chứng

## Mục tiêu bài thực hành

Khi một bean do Spring Boot auto-configuration cung cấp không xuất hiện hoặc ApplicationContext không khởi động được, việc sửa annotation theo phỏng đoán thường làm lỗi khó hiểu hơn. Cách đáng tin cậy là tạo một lỗi có thể tái hiện, thu thập bằng chứng từ Spring, xác định giai đoạn thất bại rồi sửa đúng nguyên nhân.

Bài thực hành này cố ý tạo ba nhóm lỗi thường gặp:

1. **Lỗi đăng ký:** auto-configuration class không được phát hiện vì thiếu hoặc sai tên trong `AutoConfiguration.imports`.
2. **Lỗi condition:** class đã được phát hiện nhưng bị loại do property hoặc classpath condition không khớp.
3. **Xung đột bean:** hai bean dùng cùng tên khi overriding bị tắt, hoặc nhiều bean cùng kiểu khiến dependency injection không xác định được ứng viên.

Ta sẽ dùng một thư viện Acme nhỏ, Spring Boot 3.3, Java 17+, JUnit 5 và `ApplicationContextRunner`. Mỗi lỗi có cách tái hiện, dấu hiệu quan sát được, cách sửa và test hồi quy.

Sau bài học, bạn có thể:

- Phân biệt auto-configuration chưa được đăng ký với auto-configuration đã đăng ký nhưng condition không khớp.
- Dùng `--debug`, Condition Evaluation Report và Actuator `/actuator/conditions` để lấy bằng chứng.
- Kiểm tra bean names và bean types trong ApplicationContext.
- Phân biệt `BeanDefinitionOverrideException`, `NoUniqueBeanDefinitionException` và `NoSuchBeanDefinitionException`.
- Dùng `@ConditionalOnMissingBean` để default bean nhường cho implementation của ứng dụng.
- Dùng `@Primary` và `@Qualifier` để xử lý nhiều ứng viên cùng kiểu.
- Viết test tách riêng cho discovery, property condition, classpath condition và bean conflict.
- Xây dựng quy trình chẩn đoán theo bằng chứng thay vì thay đổi nhiều cấu hình cùng lúc.

## 1. Quy trình điều tra: xác định lỗi xảy ra ở giai đoạn nào

Một bean không xuất hiện có thể do nhiều nguyên nhân. Hãy chia quá trình thành các giai đoạn:

~~~text
1. Candidate discovery
   AutoConfiguration.imports có liệt kê class không?
             |
             v
2. Condition evaluation
   Class/property/bean/web/resource conditions có khớp không?
             |
             v
3. Bean definition registration
   Bean name có bị trùng? Bean definition có được đăng ký không?
             |
             v
4. Dependency resolution
   Dependency có bean phù hợp? Có một hay nhiều candidate?
             |
             v
5. Bean creation
   Constructor/factory method có tạo được instance không?
~~~

Mỗi giai đoạn để lại loại bằng chứng khác nhau:

| Dấu hiệu | Giai đoạn cần kiểm tra trước |
| --- | --- |
| Không có bean và auto-configuration không xuất hiện trong report | Candidate discovery hoặc resource imports |
| Auto-configuration có trong report nhưng bị negative match | Condition evaluation |
| Có lỗi `BeanDefinitionOverrideException` | Bean definition registration, thường trùng bean name |
| Có lỗi `NoUniqueBeanDefinitionException` | Dependency resolution, nhiều bean cùng kiểu |
| Có lỗi `NoSuchBeanDefinitionException` | Dependency cần thiết không được đăng ký hoặc condition đã loại bean |
| Bean definition có nhưng tạo instance thất bại | Constructor, factory method, dependency hoặc lifecycle |

Không bắt đầu bằng cách thêm `@Primary`, bật bean overriding hoặc đổi property ngẫu nhiên. Trước tiên hãy xác định lỗi thuộc giai đoạn nào.

## 2. Chuẩn bị ứng dụng Acme tối thiểu

Ta tạo một API, properties class, default implementation và auto-configuration. Ví dụ được giữ đơn giản để tập trung vào quá trình đăng ký bean.

### 2.1. Cấu trúc source

~~~text
acme-autoconfigure/
  build.gradle
  src/
    main/
      java/
        com/acme/api/AcmeClient.java
        com/acme/autoconfigure/AcmeClientProperties.java
        com/acme/autoconfigure/DefaultAcmeClient.java
        com/acme/autoconfigure/AcmeClientHealth.java
        com/acme/autoconfigure/AcmeClientAutoConfiguration.java
        com/acme/autoconfigure/AcmeCodecAdapter.java
        com/acme/autoconfigure/AcmeCodecAutoConfiguration.java
      resources/
        META-INF/spring/
          org.springframework.boot.autoconfigure.AutoConfiguration.imports
    test/
      java/
        com/acme/autoconfigure/AcmeAutoConfigurationTests.java
        com/acme/autoconfigure/AutoConfigurationDiscoveryTests.java
        com/acme/vendor/OptionalCodec.java
~~~

### 2.2. Public API

**Tệp:** `src/main/java/com/acme/api/AcmeClient.java`

~~~java
package com.acme.api;

public interface AcmeClient {

    String send(String payload);
}
~~~

Đây là contract mà ứng dụng có thể inject hoặc thay thế. API không chứa chi tiết Spring Boot.

### 2.3. Properties

**Tệp:** `src/main/java/com/acme/autoconfigure/AcmeClientProperties.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme.client")
public record AcmeClientProperties(
        @DefaultValue("https://api.acme.example") URI endpoint
) {
}
~~~

### 2.4. Default implementation và dependent bean

**Tệp:** `src/main/java/com/acme/autoconfigure/DefaultAcmeClient.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;

public final class DefaultAcmeClient implements AcmeClient {

    private final URI endpoint;

    public DefaultAcmeClient(URI endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public String send(String payload) {
        // Stub xác định để kiểm thử wiring; không gửi HTTP request thật.
        return endpoint + "|" + payload;
    }
}
~~~

**Tệp:** `src/main/java/com/acme/autoconfigure/AcmeClientHealth.java`

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;

public record AcmeClientHealth(AcmeClient client) {
}
~~~

`AcmeClientHealth` đại diện cho một bean phụ thuộc vào AcmeClient. Khi có nhiều AcmeClient cùng kiểu mà không có primary/qualifier phù hợp, bean này là nơi lỗi injection có thể xuất hiện.

### 2.5. Auto-configuration

**Tệp:** `src/main/java/com/acme/autoconfigure/AcmeClientAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    public DefaultAcmeClient acmeClient(AcmeClientProperties properties) {
        return new DefaultAcmeClient(properties.endpoint());
    }

    @Bean
    @ConditionalOnMissingBean(AcmeClientHealth.class)
    public AcmeClientHealth acmeClientHealth(AcmeClient client) {
        return new AcmeClientHealth(client);
    }
}
~~~

Ta có hai condition ở hai phạm vi:

- Condition class-level: chỉ áp dụng toàn bộ cấu hình khi `acme.client.enabled=true`, hoặc property không được khai báo vì `matchIfMissing=true`.
- Condition trên bean method: chỉ tạo default AcmeClient nếu chưa có bean nào phù hợp kiểu AcmeClient; tương tự cho AcmeClientHealth.

Khi người dùng cung cấp một AcmeClient, default client sẽ back off. Bean health vẫn có thể được tạo và inject custom client.

### 2.6. Auto-configuration dùng dependency tùy chọn

Ví dụ optional integration:

**Tệp:** `src/main/java/com/acme/autoconfigure/AcmeCodecAdapter.java`

~~~java
package com.acme.autoconfigure;

public class AcmeCodecAdapter {
}
~~~

**Tệp:** `src/main/java/com/acme/autoconfigure/AcmeCodecAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.acme.vendor.OptionalCodec")
public class AcmeCodecAutoConfiguration {

    @Bean
    public AcmeCodecAdapter acmeCodecAdapter() {
        return new AcmeCodecAdapter();
    }
}
~~~

Optional type chỉ được nhắc bằng tên trong class condition; method signature không tham chiếu trực tiếp kiểu vendor. Điều này giúp configuration class được bảo vệ khi optional dependency không có mặt.

## 3. Lỗi 1 — Auto-configuration không được đăng ký

### 3.1. Cố ý tạo lỗi

Spring Boot 3 dùng resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng là FQCN của một auto-configuration class.

**Nội dung đúng:**

~~~text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeCodecAutoConfiguration
~~~

Cố ý xóa dòng `AcmeClientAutoConfiguration`:

~~~text
com.acme.autoconfigure.AcmeCodecAutoConfiguration
~~~

Sau đó khởi động ứng dụng có `@EnableAutoConfiguration`. AcmeClient không xuất hiện dù class có `@AutoConfiguration` và các condition có thể khớp.

### 3.2. Bằng chứng cần thu thập

Kiểm tra đúng resource trong source:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Kiểm tra artifact đã build:

~~~bash
jar tf build/libs/acme-autoconfigure-1.0.0.jar
~~~

Tìm file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trích xuất và đọc nội dung:

~~~bash
jar xf build/libs/acme-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu class không nằm trong candidate list, nó không được đánh giá như một auto-configuration candidate. Vì vậy, có thể không có negative condition entry cho class đó trong Condition Evaluation Report.

**Bằng chứng mạnh nhất** là kết hợp:
- Imports resource không có FQCN cần thiết.
- Bean không tồn tại.
- Test đi qua `@EnableAutoConfiguration` cũng không phát hiện bean.

Không kết luận chỉ từ việc không thấy một dòng trong report; hãy xác minh resource và candidate discovery.

### 3.3. Test discovery đúng cách

Test dùng `AutoConfigurations.of(AcmeClientAutoConfiguration.class)` sẽ nạp class trực tiếp. Cách đó kiểm tra condition và bean behavior, nhưng **bỏ qua việc tìm candidate từ imports resource**.

Để kiểm tra discovery, dùng `@EnableAutoConfiguration`:

**Tệp:** `src/test/java/com/acme/autoconfigure/AutoConfigurationDiscoveryTests.java`

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationDiscoveryTests {

    @Test
    void clientAutoConfigurationIsDiscoveredFromImportsResource() {
        new ApplicationContextRunner()
                .withUserConfiguration(ImportsDrivenApplication.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context).hasSingleBean(AcmeClientHealth.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ImportsDrivenApplication {
    }
}
~~~

Cố ý xóa dòng AcmeClient khỏi imports file rồi chạy test:
- Test sẽ thất bại vì không có AcmeClient.
- Khôi phục FQCN trong resource.
- Chạy lại và xác nhận test pass.

Đây là regression test cho resource discovery. Nó khác với test trực tiếp auto-configuration ở các phần sau.

### 3.4. Cách sửa

Khôi phục FQCN chính xác, bảo đảm:
- File nằm đúng đường dẫn.
- Mỗi candidate là một FQCN trên một dòng.
- Package/class name đúng với class đã build.
- Resource được đóng gói trong JAR.
- Không dựa vào component scan để phát hiện auto-configuration.

Spring Boot 3 dùng `AutoConfiguration.imports`. Không áp dụng máy móc hướng dẫn `spring.factories` của các phiên bản cũ cho việc đăng ký auto-configuration mới.

## 4. Lỗi 2 — Auto-configuration được phát hiện nhưng condition không khớp

Khi candidate đã được đăng ký, Spring Boot đánh giá các condition trên class và bean methods. Nếu một condition không khớp, configuration hoặc bean tương ứng sẽ không được tạo.

### 4.1. Cố ý làm property condition không khớp

Auto-configuration đang dùng:

~~~java
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
~~~

Cố ý cấu hình:

~~~yaml
acme:
  client:
    enabled: false
~~~

Kết quả:
- Candidate vẫn được phát hiện từ imports file.
- Property condition không khớp.
- Cả AcmeClient và AcmeClientHealth đều không được đăng ký qua configuration này.

Đây là lỗi điều kiện có chủ đích, không phải lỗi registration.

### 4.2. Bằng chứng từ Condition Evaluation Report

Chạy ứng dụng với:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot in Condition Evaluation Report. Tìm tên `AcmeClientAutoConfiguration` và xem negative match. Message cụ thể phụ thuộc condition và version, nhưng cần xác định:
- Property nào được kiểm tra.
- Giá trị hiện tại là gì.
- Giá trị nào được yêu cầu.
- `matchIfMissing` có cho phép property vắng mặt không.

Có thể dùng Actuator:
1. Thêm `spring-boot-starter-actuator`.
2. Expose endpoint conditions trong môi trường chẩn đoán.
3. Gọi `GET /actuator/conditions`.
4. Tìm `AcmeClientAutoConfiguration` trong `positiveMatches` hoặc `negativeMatches`.

Ví dụ cấu hình:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Endpoint conditions có thể tiết lộ chi tiết cấu hình nội bộ. Chỉ expose theo chính sách bảo mật của môi trường; không mở công khai ngoài ý muốn.

### 4.3. Test property condition

**Tệp:** `src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTests.java`

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeClientAutoConfiguration.class));

    @Test
    void defaultConfigurationCreatesClient() {
        this.runner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context).hasSingleBean(AcmeClientHealth.class);
            assertThat(context.getBean(AcmeClientProperties.class).endpoint())
                    .isEqualTo(URI.create("https://api.acme.example"));
        });
    }

    @Test
    void falsePropertyDisablesTheWholeAutoConfiguration() {
        this.runner
                .withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AcmeClient.class);
                    assertThat(context).doesNotHaveBean(AcmeClientHealth.class);
                    assertThat(context).doesNotHaveBean(AcmeClientProperties.class);
                });
    }
}
~~~

Ở đây `AutoConfigurations.of(...)` cố ý nạp candidate trực tiếp để cô lập property condition. Test discovery bằng imports resource được đặt riêng ở phần trước.

### 4.4. Cố ý làm classpath condition không khớp

Optional codec configuration dùng:

~~~java
@ConditionalOnClass(name = "com.acme.vendor.OptionalCodec")
~~~

Nếu vendor JAR không có trong runtime classpath, codec configuration không được áp dụng. Có thể tái hiện bằng `FilteredClassLoader` trong test.

Tạo fixture test:

**Tệp:** `src/test/java/com/acme/vendor/OptionalCodec.java`

~~~java
package com.acme.vendor;

public class OptionalCodec {
}
~~~

Test:

~~~java
@Test
void optionalCodecConfigurationIsSkippedWhenClassIsMissing() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(AcmeCodecAutoConfiguration.class))
            .withClassLoader(new FilteredClassLoader(OptionalCodec.class))
            .run(context ->
                    assertThat(context).doesNotHaveBean(AcmeCodecAdapter.class));
}
~~~

Và test class hiện diện:

~~~java
@Test
void optionalCodecConfigurationMatchesWhenClassIsPresent() {
    new ApplicationContextRunner()
            .withConfiguration(
                    AutoConfigurations.of(AcmeCodecAutoConfiguration.class))
            .run(context ->
                    assertThat(context).hasSingleBean(AcmeCodecAdapter.class));
}
~~~

Hai test cho thấy classpath condition thay đổi theo class loader. Nếu optional type xuất hiện trong method signature hoặc field của configuration class, hãy đặt class condition ở cấp configuration class và tách integration ra riêng để tránh resolve kiểu tùy chọn trước khi condition bảo vệ được nó.

### 4.5. Những nguyên nhân condition không khớp khác

| Condition | Lỗi cố ý | Bằng chứng cần đọc |
| --- | --- | --- |
| `@ConditionalOnProperty` | Sai prefix/name hoặc value false | Property source và negative match message |
| `@ConditionalOnClass` | Dependency thiếu hoặc class loader lọc class | Classpath/dependency tree và negative match |
| `@ConditionalOnBean` | Bean phụ thuộc chưa được đăng ký | Bean definitions đã xử lý và ordering |
| `@ConditionalOnMissingBean` | User bean đã tồn tại | Candidate type/name và positive/negative match |
| `@ConditionalOnWebApplication` | Context không phải Servlet/Reactive như mong đợi | ApplicationContext class và web condition message |
| `@ConditionalOnResource` | Resource thiếu hoặc sai path | JAR contents và resource condition |

Không sửa condition cho đến khi đã xác định chính xác condition nào không khớp và vì sao.

## 5. Lỗi 3 — Hai bean cùng tên gây BeanDefinitionOverrideException

Spring phân biệt **bean name** và **bean type**. Hai bean có thể cùng kiểu nhưng khác tên; hoặc hai bean definitions có thể cùng tên dù kiểu giống hay khác nhau.

Lỗi trùng tên thường xảy ra khi hai configuration cùng đăng ký một bean name.

### 5.1. Cố ý tạo hai bean cùng tên

~~~java
@Configuration(proxyBeanMethods = false)
class FirstClientConfiguration {

    @Bean("sharedClient")
    AcmeClient firstClient() {
        return payload -> "first:" + payload;
    }
}

@Configuration(proxyBeanMethods = false)
class SecondClientConfiguration {

    @Bean("sharedClient")
    AcmeClient secondClient() {
        return payload -> "second:" + payload;
    }
}
~~~

Hai method cùng đăng ký tên `sharedClient`. Khi bean definition overriding bị tắt, context không thể đăng ký definition thứ hai.

Lỗi thường gặp:

~~~text
BeanDefinitionOverrideException:
Invalid bean definition with name 'sharedClient'
...
Cannot register bean definition ...
There is already ... bound.
~~~

Đây là lỗi **trùng tên bean definition**, chưa phải lỗi nhiều bean cùng kiểu.

### 5.2. Test để tái hiện

~~~java
import org.springframework.beans.factory.support.BeanDefinitionOverrideException;
import org.springframework.beans.factory.support.DefaultListableBeanFactory;

@Test
void duplicateBeanNamesFailWhenOverridingIsDisabled() {
    new ApplicationContextRunner()
            .withInitializer(context ->
                    ((DefaultListableBeanFactory) context.getBeanFactory())
                            .setAllowBeanDefinitionOverriding(false))
            .withUserConfiguration(
                    FirstClientConfiguration.class,
                    SecondClientConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                BeanDefinitionOverrideException.class);
            });
}
~~~

Initializer đặt rõ `allowBeanDefinitionOverriding=false` để test không phụ thuộc default của context factory. Đây là một test failure có chủ đích; nó phải thất bại theo đúng exception được kỳ vọng.

### 5.3. Cách sửa

Chọn một trong các cách sau theo ý nghĩa thiết kế:

- Đổi bean name nếu đây là hai implementation độc lập.
- Chỉ giữ một nơi sở hữu bean nếu hai cấu hình vô tình đăng ký cùng một trách nhiệm.
- Dùng `@ConditionalOnMissingBean` cho default bean trong auto-configuration.
- Tách bean theo qualifier nếu consumer cần cả hai implementation.
- Nếu một bean là customization của ứng dụng, công bố interface và contract override rõ ràng.

Không nên bật `spring.main.allow-bean-definition-overriding=true` chỉ để làm ứng dụng khởi động được. Cách đó có thể che giấu cấu hình trùng và khiến kết quả phụ thuộc thứ tự đăng ký. Chỉ cho phép override khi đó là chủ đích được thiết kế, tài liệu hóa và kiểm thử.

## 6. Lỗi 4 — Nhiều bean cùng kiểu gây NoUniqueBeanDefinitionException

Đây là lỗi khác với trùng bean name. Hai bean có tên khác nhau có thể cùng implement `AcmeClient`. Spring có nhiều ứng viên cho một dependency theo kiểu nhưng không biết phải chọn bean nào.

### 6.1. Cố ý tạo hai AcmeClient

~~~java
@Configuration(proxyBeanMethods = false)
class AmbiguousClientsConfiguration {

    @Bean
    AcmeClient firstClient() {
        return payload -> "first:" + payload;
    }

    @Bean
    AcmeClient secondClient() {
        return payload -> "second:" + payload;
    }
}
~~~

Auto-configuration default có:

~~~java
@Bean
@ConditionalOnMissingBean(AcmeClient.class)
public DefaultAcmeClient acmeClient(AcmeClientProperties properties) {
    return new DefaultAcmeClient(properties.endpoint());
}
~~~

Khi hai user bean đã tồn tại, default client back off. Tuy nhiên, bean `AcmeClientHealth` cần một `AcmeClient` qua constructor/factory method. Spring thấy hai ứng viên và không thể chọn một.

Lỗi thường gặp:

~~~text
NoUniqueBeanDefinitionException:
No qualifying bean of type 'com.acme.api.AcmeClient' available:
expected single matching bean but found 2: firstClient,secondClient
~~~

### 6.2. Test để tái hiện

~~~java
@Test
void twoClientsWithoutPrimaryCauseAmbiguousInjection() {
    this.runner
            .withUserConfiguration(AmbiguousClientsConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                                NoUniqueBeanDefinitionException.class);
            });
}
~~~

Bằng chứng quan trọng là exception nêu kiểu dependency và tên các candidate. Điều này cho biết:
- Auto-configuration đã đi tới bước tạo bean phụ thuộc.
- Có nhiều AcmeClient cùng phù hợp.
- Đây không phải lỗi thiếu classpath hay thiếu imports resource.

### 6.3. Cách sửa bằng @Primary

Nếu một implementation là lựa chọn mặc định cho injection theo kiểu, đánh dấu nó:

~~~java
@Configuration(proxyBeanMethods = false)
class PrimaryClientsConfiguration {

    @Bean
    @Primary
    AcmeClient primaryClient() {
        return payload -> "primary:" + payload;
    }

    @Bean
    AcmeClient secondaryClient() {
        return payload -> "secondary:" + payload;
    }
}
~~~

Khi đó Spring chọn primary candidate cho dependency không có qualifier.

Test:

~~~java
@Test
void primaryClientResolvesAmbiguousInjection() {
    this.runner
            .withUserConfiguration(PrimaryClientsConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClientHealth.class);
                assertThat(context.getBeanNamesForType(AcmeClient.class))
                        .containsExactlyInAnyOrder(
                                "primaryClient", "secondaryClient");

                assertThat(context.getBean(AcmeClientHealth.class).client())
                        .isSameAs(context.getBean("primaryClient"));
            });
}
~~~

Hai AcmeClient vẫn tồn tại. `@Primary` chỉ giải quyết lựa chọn candidate cho injection point không chỉ định qualifier.

### 6.4. Cách sửa bằng @Qualifier

Nếu consumer cần lựa chọn rõ ràng giữa nhiều implementation, dùng qualifier:

~~~java
@Component
class SecondaryClientJob {

    private final AcmeClient client;

    SecondaryClientJob(
            @Qualifier("secondaryClient") AcmeClient client) {
        this.client = client;
    }
}
~~~

Qualifier chỉ định bean cụ thể cho dependency đó. Không cần dùng `@Primary` nếu mỗi consumer đều biết rõ implementation mình cần.

### 6.5. Phân biệt ba cơ chế

| Cơ chế | Tác dụng | Không làm gì |
| --- | --- | --- |
| `@ConditionalOnMissingBean(AcmeClient.class)` | Ngăn default AcmeClient được tạo khi đã có bean phù hợp | Không chọn giữa hai user beans |
| `@Primary` | Chọn candidate ưu tiên khi autowire theo kiểu | Không xóa bean còn lại, không ngăn default bean bằng chính nó |
| `@Qualifier` | Chọn bean theo qualifier/name tại injection point | Không ngăn bean khác được đăng ký |

Nếu có nhiều bean cùng kiểu, phải quyết định rõ liệu ứng dụng muốn một implementation duy nhất hay nhiều implementation có vai trò khác nhau.

## 7. Dùng ConditionEvaluationReport làm bằng chứng

Spring Boot có Condition Evaluation Report trong ApplicationContext. Đây là công cụ chính để phân biệt candidate được áp dụng, condition khớp và condition không khớp.

### 7.1. Bật report khi chạy ứng dụng

~~~bash
java -jar app.jar --debug
~~~

Hoặc dùng system property:

~~~bash
java -Ddebug -jar app.jar
~~~

Tìm:
- `AcmeClientAutoConfiguration` trong positive/negative matches.
- `OnPropertyCondition` và message về `acme.client.enabled`.
- `OnBeanCondition` cho default AcmeClient.
- Các condition khác trên class hoặc bean method.

### 7.2. Dùng report trong ApplicationContextRunner

Có thể in report trong test:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(AcmeClientAutoConfiguration.class))
        .withPropertyValues("acme.client.enabled=false")
        .run(context -> {
            assertThat(context).doesNotHaveBean(AcmeClient.class);
        });
~~~

Cách này giúp quan sát lý do condition trong test mà không phải chạy toàn bộ ứng dụng.

### 7.3. Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator, expose endpoint `conditions` trong môi trường được bảo vệ:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
~~~

Gọi:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

Response có:
- `positiveMatches`: các condition khớp.
- `negativeMatches`: các configuration bị loại và condition không khớp.
- `unconditionalClasses`: các auto-configuration không cần condition để được áp dụng.

Endpoint giúp xem report dưới dạng JSON. Hãy bảo vệ endpoint theo security policy của ứng dụng; không expose thông tin cấu hình nội bộ ra Internet công khai.

### 7.4. Điều report không chứng minh

Nếu một auto-configuration không được liệt kê trong imports candidate, nó có thể không xuất hiện trong report. Vì vậy:
- Report negative match là bằng chứng condition đã được đánh giá và không khớp.
- Report positive match là bằng chứng các condition tương ứng khớp.
- Không thấy class trong report cần kiểm tra imports resource và candidate discovery.
- Report không thay thế exception stack trace khi bean creation hoặc dependency injection thất bại.

## 8. Kiểm tra bean names và bean types trong context

Khi context đã khởi động, có thể kiểm tra bean theo kiểu:

~~~java
String[] names = applicationContext.getBeanNamesForType(AcmeClient.class);
~~~

Nếu cần xem bean definition, dùng `ConfigurableApplicationContext`:

~~~java
ConfigurableApplicationContext configurable =
        (ConfigurableApplicationContext) applicationContext;

for (String name : configurable.getBeanFactory()
        .getBeanNamesForType(AcmeClient.class)) {

    var definition =
            configurable.getBeanFactory().getBeanDefinition(name);

    System.out.println("name=" + name
            + ", class=" + definition.getBeanClassName()
            + ", primary=" + definition.isPrimary());
}
~~~

Ví dụ output minh họa khi có hai bean:

~~~text
name=primaryClient, class=null, primary=true
name=secondaryClient, class=null, primary=false
~~~

`class=null` có thể xuất hiện với factory method definitions vì implementation type được xác định từ factory method/return type chứ không phải bean class trực tiếp. Để biết kiểu runtime thực tế, dùng:

~~~java
Object bean = configurable.getBean(name);
System.out.println(bean.getClass().getName());
~~~

Không gọi `getBean` trong condition. Đoạn inspection này dành cho chẩn đoán sau khi context đã refresh thành công hoặc trong test callback; nó có thể khởi tạo lazy bean nếu bean chưa được tạo.

## 9. Đọc exception theo đúng ý nghĩa

| Exception | Ý nghĩa thường gặp | Việc cần làm |
| --- | --- | --- |
| `BeanDefinitionOverrideException` | Hai definition cùng bean name và override bị cấm | Tìm cả hai nguồn đăng ký; đổi tên hoặc thống nhất owner |
| `NoUniqueBeanDefinitionException` | Có nhiều candidate cùng kiểu cho một injection point | Dùng `@Primary`, `@Qualifier` hoặc injection collection |
| `NoSuchBeanDefinitionException` | Không có candidate phù hợp cho dependency | Kiểm tra imports, condition, type và scope |
| `BeanCreationException` | Factory/constructor tạo bean thất bại | Đọc nested cause và bean name; truy ngược dependency |
| `ClassNotFoundException` / `NoClassDefFoundError` | Class thiếu hoặc bị resolve ngoài classpath mong đợi | Kiểm tra dependency scope, optional module và class-level condition |
| `UnsatisfiedDependencyException` | Không thể cung cấp dependency cho constructor/factory method | Đọc nested cause: missing, ambiguous hay bean creation failure |

Không dừng ở dòng đầu của stack trace. Tìm deepest meaningful cause và bean name đang được tạo. Một `UnsatisfiedDependencyException` thường chỉ là wrapper; root cause có thể là `NoUniqueBeanDefinitionException` hoặc `NoSuchBeanDefinitionException`.

## 10. Một bộ test hồi quy tổng hợp

Sau khi sửa các lỗi, bộ test nên giữ lại các kịch bản quan trọng:

~~~java
@Test
void defaultClientIsCreatedWhenEnabled() {
    runner.run(context ->
            assertThat(context).hasSingleBean(AcmeClient.class));
}

@Test
void propertyCanDisableClient() {
    runner.withPropertyValues("acme.client.enabled=false")
            .run(context ->
                    assertThat(context).doesNotHaveBean(AcmeClient.class));
}

@Test
void userClientMakesDefaultBackOff() {
    runner.withUserConfiguration(CustomClientConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClient.class);
                assertThat(context.getBean(AcmeClient.class))
                        .isSameAs(context.getBean("customAcmeClient"));
            });
}

@Test
void primaryResolvesMultipleCandidates() {
    runner.withUserConfiguration(PrimaryClientsConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(AcmeClientHealth.class);
                assertThat(context.getBean(AcmeClientHealth.class).client())
                        .isSameAs(context.getBean("primaryClient"));
            });
}
~~~

Đây là các method test minh họa dùng cùng `ApplicationContextRunner` và cấu hình đã định nghĩa ở trên. Giữ thêm test registration qua `@EnableAutoConfiguration` và test classpath qua `FilteredClassLoader` để không bỏ sót hai lớp lỗi khác.

### 10.1. Ma trận test cần có

| Kịch bản | Cách dựng | Assertion chính |
| --- | --- | --- |
| Discovery thành công | `@EnableAutoConfiguration` | Auto-config bean xuất hiện |
| Imports thiếu | Xóa FQCN khỏi resource trong test experiment | Auto-config bean không xuất hiện |
| Property false | `withPropertyValues(...=false)` | Configuration bean vắng mặt |
| Optional class thiếu | `FilteredClassLoader` | Optional adapter vắng mặt |
| Custom bean | `withUserConfiguration` | Default bean back off |
| Hai bean cùng tên | Hai `@Bean` cùng name, override false | `BeanDefinitionOverrideException` |
| Hai bean cùng kiểu | Hai AcmeClient, không primary | `NoUniqueBeanDefinitionException` |
| Có primary | Một AcmeClient có `@Primary` | Dependency được inject đúng bean |

Mỗi test nên cô lập một nguyên nhân. Tránh tạo đồng thời property sai, thiếu class và bean trùng vì khi đó không thể biết điều kiện nào đã quyết định kết quả.

## 11. Dependency và lệnh chạy test

Yêu cầu Java 17+, Spring Boot 3.3.x, JUnit 5 và AssertJ. Ví dụ Gradle Groovy DSL:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy toàn bộ test:

~~~bash
# Linux/macOS
./gradlew test

# Windows
gradlew.bat test
~~~

Chạy riêng test class:

~~~bash
./gradlew test --tests "com.acme.autoconfigure.AcmeAutoConfigurationTests"
~~~

**Kết quả mong đợi sau khi sửa:**
- Discovery test pass khi imports file chứa đúng FQCN.
- Default/property tests pass.
- Custom bean test chứng minh default back off.
- Test duplicate name cố ý thất bại với `BeanDefinitionOverrideException` và được xem là pass khi assertion nhận đúng exception.
- Test hai bean cùng kiểu không primary cố ý thất bại với `NoUniqueBeanDefinitionException`.
- Test có primary pass và inject đúng bean.

Các test failure-injection phải assert exception cụ thể. Không coi một test là thành công chỉ vì context thất bại với bất kỳ nguyên nhân nào.

## 12. Quy trình chẩn đoán theo bằng chứng

Khi gặp lỗi trong ứng dụng thật, đi theo thứ tự:

1. **Xác nhận triệu chứng.** Bean không xuất hiện hay context không khởi động?
2. **Kiểm tra candidate registration.** Mở đúng JAR và đọc `AutoConfiguration.imports`; xác nhận FQCN có trong resource.
3. **Kiểm tra condition report.** Chạy `--debug` hoặc xem `/actuator/conditions`; tìm positive/negative match.
4. **Kiểm tra Environment.** Xác nhận property hiệu lực, profile, command-line args và environment variables.
5. **Kiểm tra classpath.** Dùng dependency tree và test FilteredClassLoader cho optional class.
6. **Kiểm tra bean names/types.** Dùng `getBeanNamesForType` và bean definition metadata.
7. **Đọc root cause.** Phân loại BeanDefinitionOverrideException, NoUniqueBeanDefinitionException, NoSuchBeanDefinitionException hoặc lỗi tạo bean.
8. **Sửa một nguyên nhân.** Không đồng thời đổi resource, property và bean names.
9. **Thêm regression test.** Tái hiện lỗi cũ và xác nhận fix.
10. **Kiểm tra artifact.** Build lại JAR, xác nhận imports resource và chạy sample consumer.

### 12.1. Bảng quyết định nhanh

| Bằng chứng quan sát | Kết luận ưu tiên | Hành động tiếp theo |
| --- | --- | --- |
| FQCN không có trong imports file | Registration thiếu | Thêm đúng dòng, rebuild JAR |
| FQCN có trong imports, report negative match | Condition không khớp | Đọc message, sửa property/class/bean condition |
| Report positive match, bean method không tạo bean | Condition method-level hoặc registration method | Kiểm tra method conditions và bean name/type |
| Bean name đã được đăng ký từ hai nguồn | Bean name conflict | Tìm hai definition và thống nhất tên/owner |
| Hai bean cùng kiểu, injection báo 2 candidates | Ambiguous dependency | Primary, qualifier hoặc collection |
| Dependency không có bean | Missing dependency | Kiểm tra condition và thứ tự xử lý bean definitions |
| Class không resolve được | Dependency/classpath issue | Kiểm tra runtime scope và optional class protection |

## 13. Các nguyên tắc thiết kế giúp tránh lỗi

### 13.1. Auto-configuration phải có resource registration rõ ràng

- Dùng `@AutoConfiguration`.
- Liệt kê FQCN trong `AutoConfiguration.imports`.
- Kiểm tra resource trong JAR.
- Không dựa vào component scan.

### 13.2. Condition phải có contract dễ dự đoán

- Dùng `@ConditionalOnProperty` với prefix/name/havingValue rõ ràng.
- Chọn `matchIfMissing` có chủ đích.
- Bảo vệ optional dependencies bằng class-level condition.
- Đặt bean conditions trong auto-configuration.
- Dùng `@ConditionalOnMissingBean` cho default implementation có thể thay thế.

### 13.3. Bean type và name phải có chủ đích

- Bean name mô tả vai trò, không dùng một tên chung cho hai trách nhiệm khác nhau.
- Public bean return type phải cung cấp đủ type information cho condition.
- Nếu có nhiều implementation, tài liệu hóa qualifier hoặc primary.
- Không dùng bean overriding như cách xử lý xung đột mặc định.

### 13.4. Test từng lớp độc lập

- Discovery test qua `@EnableAutoConfiguration`.
- Condition test qua `ApplicationContextRunner`.
- Optional class test qua `FilteredClassLoader`.
- Bean conflict test cho cả name và type.
- Artifact test cho resource đã đóng gói.

## 14. Lỗi thường gặp khi chẩn đoán

1. **Thấy bean vắng mặt rồi thêm @Primary.** Primary chỉ giải quyết nhiều candidate; nó không đăng ký auto-configuration còn thiếu.
2. **Thấy condition không khớp rồi thêm dependency ngay.** Nếu property đang false, thêm JAR không sửa được property condition.
3. **Chỉ dùng AutoConfigurations.of để test imports file.** Cách này nạp class trực tiếp; dùng @EnableAutoConfiguration để kiểm tra discovery.
4. **Không kiểm tra JAR.** Resource đúng trong IDE nhưng thiếu trong artifact phát hành vẫn làm consumer không phát hiện auto-configuration.
5. **Cho rằng không có report entry nghĩa là condition false.** Candidate có thể chưa được đăng ký; kiểm tra imports resource.
6. **Nhầm BeanDefinitionOverrideException với NoUniqueBeanDefinitionException.** Một lỗi là trùng tên definition, lỗi kia là nhiều candidate cùng kiểu.
7. **Bật allow-bean-definition-overriding để che lỗi.** Có thể che giấu owner conflict và khiến kết quả phụ thuộc thứ tự đăng ký.
8. **Dùng @Primary để thay default bean.** Default có thể vẫn tồn tại; dùng @ConditionalOnMissingBean để back off.
9. **Dùng @Qualifier để xóa bean.** Qualifier chỉ chọn ứng viên tại injection point.
10. **Đặt @ConditionalOnMissingBean trong cấu hình user thông thường.** Condition có thể chạy trước khi bean definitions mong muốn được xử lý; dùng trong auto-configuration.
11. **Không khai báo return type cụ thể trên @Bean method.** Bean condition có thể thiếu type information để đánh giá chính xác.
12. **Dùng classpath condition nhưng method signature vẫn lộ optional type.** Tách configuration class và bảo vệ ở class-level.
13. **Chỉ đọc exception đầu tiên.** Root cause có thể giải thích chính xác missing hay ambiguous dependency.
14. **Thay nhiều thứ cùng lúc.** Không thể biết fix nào giải quyết lỗi; thay một yếu tố và chạy lại test.
15. **Không giữ test failure-injection.** Lỗi có thể quay lại khi đổi imports, property hoặc thêm implementation mới.

## 15. Checklist hoàn thành bài thực hành

- [ ] Cố ý xóa một FQCN khỏi `AutoConfiguration.imports` và quan sát bean không được phát hiện.
- [ ] Dùng test qua `@EnableAutoConfiguration` để xác nhận registration.
- [ ] Cố ý đặt property enabled=false và đọc negative match.
- [ ] Cố ý loại optional class bằng `FilteredClassLoader`.
- [ ] Tạo hai bean cùng tên khi overriding bị tắt và nhận diện `BeanDefinitionOverrideException`.
- [ ] Tạo hai bean cùng kiểu không có primary và nhận diện `NoUniqueBeanDefinitionException`.
- [ ] Thêm `@Primary` hoặc `@Qualifier` và xác nhận injection.
- [ ] Dùng `@ConditionalOnMissingBean` để custom bean thay default.
- [ ] Đọc Condition Evaluation Report hoặc Actuator conditions endpoint.
- [ ] Kiểm tra bean names/types trong ApplicationContext.
- [ ] Khôi phục imports resource và chạy toàn bộ regression tests.
- [ ] Kiểm tra JAR cuối cùng có resource đúng.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Class có `@AutoConfiguration` nhưng không có trong `AutoConfiguration.imports`. Điều gì xảy ra?

**Đáp án:** Nó không được phát hiện như candidate qua cơ chế auto-configuration imports. Annotation trên class không tự đăng ký candidate.

**Câu 2.** Vì sao `AutoConfigurations.of(AcmeClientAutoConfiguration.class)` không chứng minh imports file đúng?

**Đáp án:** Vì runner nạp class trực tiếp. Muốn kiểm tra discovery, dùng `@EnableAutoConfiguration` hoặc `@SpringBootApplication` để Boot đọc candidate resource.

**Câu 3.** `acme.client.enabled=false` nhưng imports file đúng. Đây là lỗi gì?

**Đáp án:** Candidate đã được đăng ký nhưng property condition không khớp. Xem Condition Evaluation Report để xác nhận giá trị và message.

**Câu 4.** Hai configuration khai báo cùng bean name và override bị tắt. Exception nào thường xuất hiện?

**Đáp án:** `BeanDefinitionOverrideException`.

**Câu 5.** Hai bean có tên khác nhau nhưng cùng implement AcmeClient, constructor chỉ nhận AcmeClient. Exception nào có thể xuất hiện?

**Đáp án:** `NoUniqueBeanDefinitionException`, vì Spring không chọn được một candidate duy nhất.

**Câu 6.** `@Primary` có khiến default bean không được tạo không?

**Đáp án:** Không. `@Primary` chỉ ưu tiên candidate khi autowire; `@ConditionalOnMissingBean` mới giúp default bean back off khi đã có bean phù hợp.

**Câu 7.** Khi nào dùng `FilteredClassLoader`?

**Đáp án:** Khi cần mô phỏng class hoặc package không có trên runtime classpath để kiểm tra classpath condition và optional integration.

**Câu 8.** Không thấy auto-configuration trong Condition Evaluation Report có đủ kết luận condition không khớp không?

**Đáp án:** Không. Candidate có thể chưa được đăng ký. Hãy kiểm tra imports resource và artifact trước.

## 17. Ghi nhớ

Chẩn đoán auto-configuration cần đi theo bằng chứng và đúng giai đoạn. Trước hết xác nhận candidate có được phát hiện từ `AutoConfiguration.imports`. Nếu có, đọc Condition Evaluation Report để biết condition nào không khớp. Khi bean definitions đã được đăng ký, phân biệt xung đột tên với xung đột kiểu qua exception và danh sách bean candidates.

`BeanDefinitionOverrideException` thường chỉ ra hai definition cùng tên. `NoUniqueBeanDefinitionException` chỉ ra nhiều bean cùng kiểu cho một injection point. `@ConditionalOnMissingBean` giúp default implementation nhường chỗ cho custom bean; `@Primary` và `@Qualifier` giúp chọn giữa nhiều implementation. Các cơ chế này giải quyết những vấn đề khác nhau.

Hãy giữ ba test riêng: discovery qua `@EnableAutoConfiguration`, condition qua `ApplicationContextRunner`, và bean conflicts qua context có các cấu hình cố ý xung đột. Sau khi sửa, kiểm tra JAR đã build và giữ regression tests để lỗi không quay lại.

### Tài liệu Spring Boot 3.3 chính thức

- [Creating Your Own Auto-configuration — Conditions and Testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Troubleshooting Auto-configuration — Condition Evaluation Report](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
- [Conditions Actuator Endpoint — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
- [@ConditionalOnMissingBean Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [ApplicationContextRunner Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [FilteredClassLoader Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
