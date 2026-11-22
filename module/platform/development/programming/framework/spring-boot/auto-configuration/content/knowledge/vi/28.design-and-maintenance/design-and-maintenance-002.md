# Mặc định tối thiểu, quyền tùy chỉnh minh bạch và hành vi tắt tính năng nhất quán

## 1. Mục tiêu thiết kế của một auto-configuration tốt

Một starter Spring Boot có thể giúp ứng dụng chạy được chỉ bằng cách thêm dependency. Nhưng sự tiện lợi đó chỉ có giá trị khi starter hành xử dễ dự đoán và không tự chiếm quyền điều khiển ứng dụng.

Một auto-configuration được thiết kế tốt cần đáp ứng ba nguyên tắc:

1. **Mặc định tối thiểu:** không bật integration có side effect chỉ vì thư viện xuất hiện trên classpath. Giá trị mặc định phải an toàn, ít tài nguyên và không tự tạo kết nối hoặc công việc nền không cần thiết.
2. **Quyền tùy chỉnh minh bạch:** ứng dụng biết bean/property nào có thể thay thế, thứ tự ưu tiên ra sao và khi nào starter sẽ lùi lại. Người dùng không phải cast sang implementation nội bộ hoặc phụ thuộc tên bean ngẫu nhiên.
3. **Tắt tính năng nhất quán:** khi feature bị tắt, tất cả thành phần do starter quản lý cho feature đó phải tuân theo cùng một trạng thái. Không để client bị tắt nhưng scheduler, listener, connection pool hoặc background task vẫn chạy.

Ba nguyên tắc liên kết với nhau. Một default an toàn giảm bất ngờ; một customization contract rõ ràng tránh tranh chấp bean; một feature switch nhất quán giúp ứng dụng kiểm soát vòng đời và tài nguyên.

Bài này dùng Java 17+, Maven và Spring Boot 3.3.13. Ví dụ là một thư viện Catalog có client HTTP tùy chọn. Mục tiêu là minh họa cách thiết kế và kiểm thử auto-configuration; ứng dụng thực tế cần điều chỉnh endpoint, xác thực, retry và chính sách lỗi theo API của dịch vụ.

## 2. Mặc định tối thiểu: chỉ làm điều người dùng đã yêu cầu

### 2.1. Có dependency không đồng nghĩa đã bật tính năng

Một ứng dụng thêm starter có thể chỉ muốn dùng một API, xem metadata hoặc chuẩn bị cấu hình cho môi trường khác. Nếu starter tự kết nối tới dịch vụ từ lúc khởi động, nó có thể:

- Gây lỗi startup khi dịch vụ bên ngoài tạm thời không sẵn sàng.
- Mở socket, tạo thread hoặc connection pool dù ứng dụng không dùng feature.
- Gửi request ngoài dự kiến.
- Làm tăng thời gian khởi động và chi phí tài nguyên.
- Tạo hành vi khác nhau giữa local, test, staging và production.

Với integration có tác động bên ngoài, một lựa chọn an toàn là **opt-in**: feature tắt khi property không được khai báo, và chỉ bật khi người dùng ghi rõ **enabled=true**.

Ví dụ:

```yaml
acme:
  catalog:
    enabled: true
```

Trong auto-configuration:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

**matchIfMissing=false** làm cho property bị thiếu có cùng kết quả với feature tắt. Viết rõ giá trị này giúp người đọc nhận ra chính sách opt-in ngay tại code.

### 2.2. Chọn default có giới hạn và có thể giải thích

Default tốt thường có những đặc điểm:

- Không tạo network connection hoặc background worker khi feature chưa được bật.
- Không tự phát hiện rồi sử dụng credential hoặc endpoint ngoài ý muốn.
- Có timeout hữu hạn thay vì chờ vô hạn.
- Có kích thước pool, queue và retry được giới hạn nếu những tài nguyên đó được tạo.
- Không bật logging nhạy cảm hoặc ghi nội dung request/response mặc định.
- Không tự thay đổi hành vi của bean do ứng dụng cung cấp.
- Có thể ghi đè bằng property hoặc extension point đã tài liệu hóa.

Không phải mọi property đều nên có default. Một giá trị bắt buộc như endpoint, tenant hoặc credential nên để trống và báo lỗi rõ ràng khi người dùng bật feature nhưng chưa cung cấp. Tự bịa một endpoint production hoặc credential mặc định thường tạo cảm giác tiện lợi giả tạo.

### 2.3. Phân biệt cấu hình mặc định với hành động mặc định

Tạo một object cấu hình hoặc client wrapper không nhất thiết có nghĩa đã thực hiện I/O. Tuy vậy, constructor của object có thể tự mở connection, chạy migration, tạo thread hoặc gọi remote API.

Hãy giữ việc khởi tạo nhẹ:

- Tạo HttpClient hoặc object cấu hình có thể diễn ra khi feature bật.
- Chỉ gửi HTTP request khi consumer gọi method tương ứng.
- Chỉ tạo scheduler khi tính năng polling được bật rõ ràng.
- Chỉ đăng ký listener có side effect khi feature active.
- Không thực hiện network call trong constructor hoặc @Bean factory method.

Ví dụ trong bài tạo JDK HttpClient khi feature bật, nhưng không gửi request trong lúc khởi động. Request chỉ được gửi khi consumer gọi findById.

## 3. Quyền tùy chỉnh phải là một hợp đồng rõ ràng

### 3.1. Dùng interface công khai làm điểm thay thế

Nếu ứng dụng có thể dùng client riêng, hãy cung cấp một interface làm contract:

```java
public interface CatalogClient {

    Optional<String> findById(String id)
            throws IOException, InterruptedException;
}
```

Code nghiệp vụ phụ thuộc vào CatalogClient. Starter có thể cung cấp implementation mặc định, còn ứng dụng có thể cung cấp bean của chính nó.

Đừng yêu cầu consumer cast bean sang DefaultCatalogClient, import nested configuration hoặc gọi constructor của implementation nội bộ. Những chi tiết đó có thể thay đổi mà không làm thay đổi contract.

### 3.2. @ConditionalOnMissingBean thể hiện quyền ưu tiên

Một bean mặc định thường dùng:

```java
@Bean
@ConditionalOnMissingBean(CatalogClient.class)
CatalogClient catalogClient(CatalogProperties properties) {
    return new DefaultCatalogClient(properties);
}
```

Ý nghĩa: nếu context đã có bean phù hợp với CatalogClient, auto-configuration sẽ không tạo bean mặc định.

Quy tắc này tạo ra thứ tự ưu tiên dễ hiểu:

1. Ứng dụng cung cấp implementation riêng.
2. Nếu ứng dụng không cung cấp, starter tạo implementation mặc định.
3. Nếu feature bị tắt, auto-configuration không tạo các bean do starter quản lý.

@ConditionalOnMissingBean là một customization hook phổ biến trong auto-configuration. Nó không tự biến mọi bean thành API ổn định; thư viện vẫn cần tài liệu hóa type nào được phép thay thế và hành vi back-off mà người dùng có thể dựa vào.

### 3.3. Đặt điều kiện ở đúng phạm vi

Nếu feature bị tắt, nên đặt @ConditionalOnProperty trên configuration class hoặc nested configuration bao trọn các bean thuộc feature. Khi đó, client mặc định, properties bean và các thành phần phụ thuộc được bật/tắt cùng nhau.

Ví dụ:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {
    // Các bean của feature nằm trong configuration này.
}
```

Nếu chỉ đặt condition trên một @Bean method mà các bean khác vẫn được đăng ký, ứng dụng có thể rơi vào trạng thái nửa bật nửa tắt. Ví dụ client biến mất nhưng scheduler vẫn khởi động và liên tục tìm client.

Với auto-configuration lớn, có thể tách từng feature thành nested configuration riêng. Điều quan trọng là mọi thành phần có cùng vòng đời phải được bảo vệ bởi cùng một điều kiện hoặc các điều kiện tương đương.

### 3.4. Phân biệt bean do starter quản lý với bean do ứng dụng sở hữu

Property **acme.catalog.enabled=false** có thể ngăn auto-configuration tạo bean. Nó không xóa bean mà ứng dụng đã tự khai báo.

Đây là ranh giới quyền sở hữu có chủ đích:

- Starter kiểm soát những bean nằm trong auto-configuration của nó.
- Ứng dụng kiểm soát những bean do ứng dụng khai báo.
- Nếu ứng dụng muốn mọi consumer/scheduler của Catalog cũng dừng, các thành phần đó cần tuân theo cùng feature switch hoặc được ứng dụng điều khiển tương ứng.

Không nên tuyên bố một property của starter sẽ xóa mọi bean cùng type trong ApplicationContext. Spring không tự xóa bean do cấu hình khác đăng ký chỉ vì một auto-configuration bị condition loại bỏ.

## 4. Hành vi tắt tính năng phải nhất quán

### 4.1. Xác định rõ disabled có nghĩa gì

Với một integration tùy chọn, có thể định nghĩa trạng thái disabled như sau:

| Thành phần | Khi feature tắt |
|---|---|
| Client mặc định | Không được đăng ký |
| Properties bean riêng của feature | Không được đăng ký nếu chỉ cần khi feature active |
| HTTP request lúc startup | Không được gửi |
| Connection pool / scheduler | Không được tạo |
| Listener có side effect | Không được đăng ký |
| Metrics riêng của integration | Không được khởi tạo nếu chỉ phục vụ feature |
| Bean do ứng dụng tự khai báo | Vẫn thuộc quyền sở hữu của ứng dụng |

Bảng này là một contract thiết kế. Nếu thư viện muốn giữ một properties bean dù feature disabled để ứng dụng đọc giá trị, hãy nói rõ ngoại lệ đó và kiểm thử nó. Đừng để trạng thái thực tế phụ thuộc vào vị trí vô tình của annotation.

### 4.2. Tránh tạo tác dụng phụ trước khi condition được kiểm tra

Không làm các việc sau trong static initializer hoặc constructor của auto-configuration class:

- Mở socket hoặc gọi remote service.
- Khởi động thread.
- Đăng ký shutdown hook toàn cục.
- Thay đổi system property.
- Đọc credential từ vị trí không được người dùng cấu hình.
- Chạy migration hoặc tạo tài nguyên ngoài ApplicationContext.

Các tác vụ này có thể xảy ra trước khi Spring đánh giá condition của bean hoặc khó rollback khi context khởi động thất bại.

Đặt side effect trong lifecycle của bean được condition bảo vệ, và ưu tiên khởi tạo lazy nếu tính năng cho phép. Khi bean bị đóng hoặc context shutdown, giải phóng tài nguyên qua lifecycle contract phù hợp như close() hoặc @PreDestroy.

### 4.3. Tắt feature không được để lại một phần hệ thống chạy ngầm

Giả sử Catalog có client, polling scheduler và metrics exporter. Nếu chỉ client có condition, scheduler vẫn có thể được tạo và phát sinh lỗi hoặc tiêu thụ CPU.

Có thể dùng một nested configuration chung:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true")
static class CatalogEnabledConfiguration {

    // Client, scheduler và các bean chỉ tồn tại khi feature bật.
}
```

Nếu một thành phần có vòng đời khác, hãy mô tả điều kiện riêng và giải thích vì sao nó vẫn cần tồn tại khi feature chính tắt. Tránh các ngoại lệ không được tài liệu hóa.

### 4.4. Phân biệt disabled với lỗi cấu hình

Ba trạng thái cần có ý nghĩa khác nhau:

- **Disabled:** người dùng không bật feature; starter không đăng ký bean của feature và không tạo side effect.
- **Enabled và hợp lệ:** starter tạo bean mặc định hoặc dùng bean tùy chỉnh.
- **Enabled nhưng thiếu cấu hình bắt buộc:** startup fail-fast với thông báo chỉ rõ property cần bổ sung.

Không nên âm thầm coi thiếu endpoint là disabled khi người dùng đã ghi enabled=true. Điều đó che giấu lỗi cấu hình và khiến feature tưởng đã bật nhưng thực tế không hoạt động.

## 5. Thiết kế ví dụ Catalog

Ta xây dựng thư viện có các contract sau:

- CatalogClient: interface công khai để tìm item.
- CatalogProperties: cấu hình công khai với prefix acme.catalog.
- CatalogAutoConfiguration: tự tạo client mặc định khi feature bật và ứng dụng chưa cung cấp client.
- DefaultCatalogClient: implementation nội bộ dùng JDK HttpClient.

Chính sách của ví dụ:

| Property | Default | Quy tắc |
|---|---|---|
| acme.catalog.enabled | false | Phải bật rõ bằng true |
| acme.catalog.base-url | Không có | Bắt buộc khi starter tạo client mặc định |
| acme.catalog.connect-timeout | 2s | Phải dương |
| acme.catalog.request-timeout | 3s | Phải dương |

Khi feature disabled, CatalogAutoConfiguration không áp dụng và cả CatalogProperties lẫn CatalogClient do starter quản lý đều không được đăng ký. Khi enabled, endpoint phải là URI HTTP(S) tuyệt đối có host, không có query hoặc fragment.

Nếu ứng dụng cung cấp CatalogClient riêng, starter sẽ back off. Ứng dụng chịu trách nhiệm về endpoint, timeout, retry và vòng đời của client đó. base-url chỉ bắt buộc cho implementation mặc định.

## 6. Ví dụ Maven hoàn chỉnh với Spring Boot 3.3.13

### 6.1. Cấu trúc thư mục

```text
catalog-starter/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/catalog/
    │   │   ├── CatalogClient.java
    │   │   └── CatalogProperties.java
    │   ├── java/com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/catalog/autoconfigure/
        └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>catalog-starter</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
```

Configuration processor là tùy chọn và chỉ hỗ trợ tạo metadata cho IDE trong quá trình build. Nó không phải dependency runtime mà ứng dụng tiêu thụ cần khai báo để client hoạt động.

### 6.3. CatalogClient.java — contract công khai

```java
package com.acme.catalog;

import java.io.IOException;
import java.util.Optional;

public interface CatalogClient {

    Optional<String> findById(String id)
            throws IOException, InterruptedException;
}
```

Ứng dụng phụ thuộc vào interface này. Contract quy định item không tồn tại trả về Optional.empty(), còn lỗi I/O hoặc request bị interrupt được truyền cho caller.

### 6.4. CatalogProperties.java — cấu hình công khai

```java
package com.acme.catalog;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.catalog")
public class CatalogProperties {

    private boolean enabled = false;
    private URI baseUrl;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration requestTimeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
```

enabled mặc định false. baseUrl cố ý không có default để không gửi request tới một endpoint tưởng tượng. Hai timeout có giá trị mặc định hữu hạn để request không chờ vô thời hạn.

### 6.5. CatalogAutoConfiguration.java — điều kiện, override và default client

```java
package com.acme.catalog.autoconfigure;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Optional;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CatalogClient.class)
    CatalogClient catalogClient(CatalogProperties properties) {
        return new DefaultCatalogClient(properties);
    }

    private static final class DefaultCatalogClient
            implements CatalogClient {

        private final HttpClient httpClient;
        private final URI baseUrl;
        private final Duration requestTimeout;

        private DefaultCatalogClient(CatalogProperties properties) {
            this.baseUrl = requireBaseUrl(properties.getBaseUrl());
            Duration connectTimeout = requirePositive(
                    properties.getConnectTimeout(),
                    "acme.catalog.connect-timeout");
            this.requestTimeout = requirePositive(
                    properties.getRequestTimeout(),
                    "acme.catalog.request-timeout");

            this.httpClient = HttpClient.newBuilder()
                    .connectTimeout(connectTimeout)
                    .build();
        }

        @Override
        public Optional<String> findById(String id)
                throws IOException, InterruptedException {

            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException(
                        "Catalog item id must not be blank.");
            }

            String encodedId = URLEncoder.encode(
                    id,
                    StandardCharsets.UTF_8);

            URI requestUri = URI.create(
                    baseUrl.toASCIIString() + "?id=" + encodedId);

            HttpRequest request = HttpRequest.newBuilder(requestUri)
                    .timeout(requestTimeout)
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 404) {
                return Optional.empty();
            }

            if (response.statusCode() < 200
                    || response.statusCode() >= 300) {
                throw new IOException(
                        "Catalog returned HTTP " + response.statusCode());
            }

            return Optional.of(response.body());
        }

        private static URI requireBaseUrl(URI value) {
            String scheme = value == null ? null : value.getScheme();

            boolean valid = value != null
                    && value.isAbsolute()
                    && value.getHost() != null
                    && ("http".equalsIgnoreCase(scheme)
                        || "https".equalsIgnoreCase(scheme))
                    && value.getQuery() == null
                    && value.getFragment() == null;

            if (!valid) {
                throw new IllegalStateException(
                        "Property acme.catalog.base-url must be an "
                                + "absolute HTTP(S) URI with a host "
                                + "and without query or fragment.");
            }

            return value;
        }

        private static Duration requirePositive(
                Duration value,
                String propertyName) {

            if (value == null || value.isZero() || value.isNegative()) {
                throw new IllegalStateException(
                        "Property " + propertyName
                                + " must be greater than zero.");
            }

            return value;
        }
    }
}
```

Các quyết định quan trọng:

1. @ConditionalOnProperty đặt trên toàn bộ auto-configuration. Khi property thiếu hoặc false, các bean do starter quản lý không được đăng ký.
2. @EnableConfigurationProperties nằm trên class được bảo vệ, vì vậy CatalogProperties chỉ được tạo khi feature bật.
3. @ConditionalOnMissingBean(CatalogClient.class) cho phép ứng dụng thay client mặc định theo type.
4. DefaultCatalogClient là private nested class; consumer chỉ nhìn thấy CatalogClient.
5. Endpoint và timeout được kiểm tra khi tạo default client. Cấu hình sai làm startup fail-fast với property cụ thể.
6. HttpClient được tạo nhưng không gửi request lúc startup. I/O chỉ diễn ra khi caller gọi findById.
7. Không có scheduler, thread riêng hoặc remote side effect nào được tạo khi feature disabled.

Endpoint trong ví dụ được hiểu là URL của resource collection; request gửi tới base-url?id=... Hợp đồng HTTP thực tế cần khớp API của dịch vụ mà thư viện tích hợp.

### 6.6. AutoConfiguration.imports

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

Chỉ đăng ký top-level auto-configuration. Consumer không cần import implementation hoặc bean method.

### 6.7. application.yml khi muốn bật feature

```yaml
acme:
  catalog:
    enabled: true
    base-url: https://catalog.example.test/items
    connect-timeout: 2s
    request-timeout: 3s
```

Nếu không có enabled: true, feature vẫn tắt. Nếu bật nhưng không có base-url, starter báo lỗi thay vì âm thầm tạo client không hoạt động.

## 7. Kiểm thử chính sách default, override và disabled

ApplicationContextRunner cho phép kiểm tra auto-configuration trong context nhỏ mà không cần khởi động web server hoặc gọi dịch vụ thật.

### 7.1. CatalogAutoConfigurationTests.java

```java
package com.acme.catalog.autoconfigure;

import java.net.URI;
import java.time.Duration;
import java.util.Optional;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void featureIsDisabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(CatalogClient.class);
            assertThat(context).doesNotHaveBean(CatalogProperties.class);
        });
    }

    @Test
    void explicitFalseKeepsAllStarterManagedBeansDisabled() {
        runner.withPropertyValues("acme.catalog.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(CatalogClient.class);
                    assertThat(context).doesNotHaveBean(
                            CatalogProperties.class);
                });
    }

    @Test
    void enabledFeatureCreatesDefaultClientWithBoundSettings() {
        runner.withPropertyValues(
                        "acme.catalog.enabled=true",
                        "acme.catalog.base-url=https://catalog.example.test/items",
                        "acme.catalog.connect-timeout=1s",
                        "acme.catalog.request-timeout=4s")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    CatalogProperties properties =
                            context.getBean(CatalogProperties.class);

                    assertThat(properties.getBaseUrl())
                            .isEqualTo(URI.create(
                                    "https://catalog.example.test/items"));
                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofSeconds(1));
                    assertThat(properties.getRequestTimeout())
                            .isEqualTo(Duration.ofSeconds(4));
                });
    }

    @Test
    void applicationClientOverridesTheDefaultClient() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    CatalogClient client =
                            context.getBean(CatalogClient.class);

                    assertThat(client.findById("42"))
                            .isEqualTo(Optional.of("custom-item:42"));
                });
    }

    @Test
    void enabledFeatureWithoutBaseUrlFailsFast() {
        runner.withPropertyValues("acme.catalog.enabled=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining(
                                    "Property acme.catalog.base-url");
                });
    }

    @Test
    void disabledAutoConfigurationDoesNotRemoveAnApplicationOwnedBean() {
        runner.withPropertyValues("acme.catalog.enabled=false")
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    assertThat(context.getBean(CatalogClient.class)
                            .findById("42"))
                            .isEqualTo(Optional.of("custom-item:42"));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return id -> Optional.of("custom-item:" + id);
        }
    }
}
```

### 7.2. Ý nghĩa sáu test

| Test | Cấu hình | Kết quả được kiểm tra |
|---|---|---|
| featureIsDisabledWhenPropertyIsMissing | Không khai báo enabled | Không có client hoặc properties bean của starter |
| explicitFalseKeepsAllStarterManagedBeansDisabled | enabled=false | Không có bean do starter quản lý |
| enabledFeatureCreatesDefaultClientWithBoundSettings | enabled=true và endpoint hợp lệ | Có client; property được bind đúng |
| applicationClientOverridesTheDefaultClient | enabled=true và user bean | Chỉ có client do ứng dụng cung cấp |
| enabledFeatureWithoutBaseUrlFailsFast | enabled=true nhưng thiếu endpoint | Context fail với thông báo property |
| disabledAutoConfigurationDoesNotRemoveAnApplicationOwnedBean | enabled=false và user bean | Bean do ứng dụng khai báo vẫn tồn tại |

Test cuối cùng làm rõ quyền sở hữu: property disabled ngăn starter tạo bean mặc định; nó không xóa bean do ứng dụng tự đăng ký. Nếu một ứng dụng muốn tắt toàn bộ luồng nghiệp vụ Catalog, ứng dụng cần áp dụng cùng trạng thái cho các consumer hoặc scheduler do ứng dụng quản lý.

### 7.3. Chạy test

Dùng JDK 17+ và Maven trong thư mục có pom.xml:

```bash
mvn test
```

Với sáu test trên, kết quả mong đợi:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là kết quả kỳ vọng từ mã ví dụ, không phải log của một lần chạy đã thực thi. Các test không gọi findById, vì vậy không gửi HTTP request tới endpoint bên ngoài.

## 8. Quy tắc ưu tiên giữa property và bean tùy chỉnh

Một starter thường có cả hai loại customization:

- Property điều chỉnh implementation mặc định.
- Bean do ứng dụng cung cấp thay implementation mặc định.

Cần công bố thứ tự ưu tiên. Ví dụ của bài dùng quy tắc:

1. enabled quyết định starter có tham gia hay không.
2. Nếu disabled, auto-configuration không tạo bean của feature.
3. Nếu enabled và ứng dụng có CatalogClient, starter back off.
4. Nếu enabled và chưa có CatalogClient, starter yêu cầu base-url, kiểm tra timeout rồi tạo default client.
5. Khi custom client được dùng, ứng dụng chịu trách nhiệm về cấu hình và vòng đời của client đó.

Không nên để người dùng phải đoán base-url có được áp dụng cho custom client hay không. Trong ví dụ, property này chỉ được default implementation sử dụng. Nếu muốn property luôn có hiệu lực kể cả khi custom client được cung cấp, thư viện cần thiết kế contract khác, chẳng hạn một CatalogClientCustomizer được gọi sau khi tạo client hoặc một properties object được truyền vào implementation của người dùng.

### 8.1. Không âm thầm ghi đè bean của ứng dụng

Tránh đăng ký bean mặc định mà không có condition:

```java
@Bean
CatalogClient catalogClient() {
    return new DefaultCatalogClient(...);
}
```

Nếu ứng dụng cũng đăng ký CatalogClient, context có thể có hai candidate, gây NoUniqueBeanDefinitionException, hoặc hành vi injection phụ thuộc qualifier.

Dùng @ConditionalOnMissingBean(CatalogClient.class) khi thư viện chủ đích cho phép override. Nếu bean mặc định bắt buộc duy nhất và không được thay thế, phải nói rõ điều đó và thiết kế contract phù hợp; đừng để conflict trở thành cơ chế ngăn customization ngoài ý muốn.

### 8.2. Không dùng property để âm thầm đổi implementation

Ví dụ, một property acme.catalog.custom=true mà không có tài liệu về bean precedence có thể làm ứng dụng khó hiểu vì implementation nào đang hoạt động.

Nếu có nhiều implementation do starter cung cấp, hãy đặt điều kiện riêng, công bố property tương ứng và kiểm thử từng lựa chọn. Có thể dùng @ConditionalOnProperty, @ConditionalOnClass hoặc customizer, nhưng phải có quy tắc rõ ràng khi nhiều điều kiện cùng khớp.

## 9. Thiết kế feature switch cho nhiều bean

Với feature thực tế, một integration có thể có nhiều bean:

- Client.
- Health indicator.
- Metrics binder.
- Scheduler hoặc listener.
- Cache.
- Retry infrastructure.
- Connection pool.

Nếu tất cả chỉ có ý nghĩa khi Catalog enabled, đặt chúng dưới một configuration chung:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class CatalogEnabledConfiguration {

        // Client, metrics, scheduler và các bean của feature.
    }
}
```

Nếu một bean có thể tồn tại độc lập, tách nó thành auto-configuration riêng và ghi rõ điều kiện. Ví dụ, metadata gợi ý IDE không cần bean runtime; một health indicator chỉ nên xuất hiện khi client thực sự có mặt.

Với scheduler, cần kiểm tra cả việc tạo task và việc dừng task. Chỉ condition bean scheduler chưa đủ nếu một singleton hoặc static initializer khác đã tạo thread trước đó.

Với listener, cần xác định listener được đăng ký qua bean, spring.factories hay API khác. Một listener được nạp rất sớm có thể không chịu cùng vòng đời với bean trong auto-configuration. Nếu feature disabled phải vô hiệu hóa listener, điều kiện phải nằm ở cơ chế đăng ký tương ứng.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Thêm starter là ứng dụng tự gọi dịch vụ ngoài | Feature bật mặc định hoặc bean constructor thực hiện I/O | Dùng opt-in khi phù hợp; chỉ gửi request khi consumer gọi |
| Ứng dụng không cấu hình endpoint nhưng vẫn có client vô dụng | Endpoint có default giả hoặc validation quá lỏng | Để endpoint bắt buộc khi bật default client và fail-fast |
| Có hai bean cùng type | Bean mặc định không có @ConditionalOnMissingBean | Thể hiện rõ quyền override theo type |
| Custom bean không được dùng | Condition đặt sai phạm vi hoặc auto-configuration xử lý trước bean ứng dụng | Dùng auto-configuration ordering chuẩn và test với user configuration |
| Tắt client nhưng scheduler vẫn chạy | Feature condition chỉ bảo vệ một bean | Đặt các bean cùng vòng đời dưới configuration chung |
| Feature disabled nhưng properties bean vẫn xuất hiện ngoài ý muốn | @EnableConfigurationProperties đặt ngoài configuration được bảo vệ | Đưa annotation vào vùng condition hoặc tài liệu hóa ngoại lệ |
| Property false làm mất bean do ứng dụng tạo | Nhầm điều kiện của starter với quyền sở hữu toàn ApplicationContext | Chỉ condition bean của starter; để ứng dụng quản lý bean của mình |
| Enabled=true nhưng thiếu endpoint không gây lỗi | Code âm thầm fallback hoặc trì hoãn lỗi không có chủ đích | Validate cấu hình bắt buộc khi tạo default bean |
| Client mở socket trong startup | Constructor hoặc factory method thực hiện I/O | Tách tạo object khỏi gửi request; dùng timeout và lifecycle rõ ràng |
| Timeout bằng 0 hoặc âm | Không validate property | Kiểm tra giá trị dương và thông báo tên property |
| Custom client vẫn bị buộc có endpoint mà default client cần | Validation đặt ở tầng chung dù user bean đã thay thế default | Chỉ validate dependency mà implementation đang được chọn thực sự cần |
| Disable không dừng thread hoặc connection đã tạo | Side effect nằm ngoài bean lifecycle hoặc không có cleanup | Quản lý tài nguyên bằng lifecycle và đóng khi context shutdown |

## 11. Quy trình thiết kế và bảo trì

Trước khi phát hành một auto-configuration, hãy thực hiện:

1. Viết rõ feature switch: property nào bật, default là gì và missing có nghĩa gì.
2. Liệt kê tất cả bean, thread, listener, scheduler, connection pool và side effect thuộc feature.
3. Chọn default ít tác động nhất; không tạo kết nối hoặc task nền nếu feature chưa được bật.
4. Xác định property bắt buộc và property có default; validate giá trị ngay khi default implementation được tạo.
5. Công bố interface hoặc customization hook mà ứng dụng có thể thay thế.
6. Dùng @ConditionalOnMissingBean cho bean mặc định nếu override được hỗ trợ.
7. Đặt condition bao trọn các bean cùng vòng đời để tránh trạng thái nửa bật nửa tắt.
8. Xác định rõ user-owned bean có tồn tại khi feature disabled hay không; thông thường starter không xóa bean của ứng dụng.
9. Viết test cho property missing, false, true, cấu hình thiếu, custom bean và trạng thái disabled.
10. Kiểm tra không có network call hoặc background activity khi startup và khi feature disabled.
11. Kiểm tra tài nguyên được đóng đúng khi ApplicationContext shutdown.
12. Đọc Condition Evaluation Report khi kết quả không khớp với chính sách đã công bố.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một integration có side effect thường nên tắt khi property enabled bị thiếu?

**Đáp án:** Vì thêm dependency không đồng nghĩa người dùng muốn mở kết nối, chạy thread hoặc gửi request. Opt-in giảm tác động bất ngờ và giúp ứng dụng kiểm soát feature.

**Câu 2.** matchIfMissing=false có ý nghĩa gì với @ConditionalOnProperty?

**Đáp án:** Nếu property không tồn tại, condition không khớp. Đây là cách thể hiện rõ default disabled.

**Câu 3.** @ConditionalOnMissingBean(CatalogClient.class) cho phép điều gì?

**Đáp án:** Khi ứng dụng đã cung cấp bean CatalogClient, starter không tạo implementation mặc định.

**Câu 4.** Property disabled có xóa bean do ứng dụng tự khai báo không?

**Đáp án:** Không. Nó chỉ ngăn auto-configuration được bảo vệ đăng ký bean của starter. Bean do ứng dụng sở hữu vẫn tồn tại.

**Câu 5.** Vì sao nên đặt feature condition trên configuration bao trọn client và scheduler?

**Đáp án:** Để các bean cùng vòng đời được bật/tắt nhất quán, tránh scheduler hoặc listener tiếp tục chạy khi client đã bị tắt.

**Câu 6.** Khi enabled=true nhưng thiếu endpoint bắt buộc, nên làm gì?

**Đáp án:** Fail-fast với thông báo chỉ rõ property. Không âm thầm tạo client không hoạt động hoặc coi cấu hình sai là feature disabled.

**Câu 7.** Custom client có nhất thiết phải cung cấp endpoint mà default client cần không?

**Đáp án:** Không nếu endpoint chỉ phục vụ default implementation. Khi custom bean thay thế default, ứng dụng chịu trách nhiệm về cấu hình mà implementation riêng cần.

**Câu 8.** Tạo HttpClient có đồng nghĩa đã gửi HTTP request không?

**Đáp án:** Không. Trong ví dụ, HttpClient chỉ được xây dựng khi feature bật; request chỉ được gửi khi consumer gọi findById.

## 13. Ghi nhớ

- Chọn default tối thiểu; với integration có side effect, cân nhắc opt-in và dùng matchIfMissing=false.
- Không tự đặt endpoint, credential hoặc hành vi remote mà người dùng chưa yêu cầu.
- Timeout và tài nguyên phải có giới hạn, giá trị hợp lệ và tài liệu rõ.
- Dùng interface công khai và @ConditionalOnMissingBean để cho phép ứng dụng thay implementation mặc định.
- Nói rõ property nào áp dụng cho default client, property nào vẫn có hiệu lực với custom client.
- Đặt feature condition ở đúng phạm vi để client, scheduler, listener, metrics và resource liên quan có trạng thái nhất quán.
- Disabled ngăn starter đăng ký bean của nó; không xóa bean do ứng dụng tự khai báo.
- Tách khởi tạo object khỏi network I/O và background activity.
- Enabled nhưng thiếu cấu hình bắt buộc phải fail-fast với thông báo hành động được.
- Kiểm thử missing/false/true, override, cấu hình sai và bean do ứng dụng sở hữu.

### Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot 3.3 API — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
