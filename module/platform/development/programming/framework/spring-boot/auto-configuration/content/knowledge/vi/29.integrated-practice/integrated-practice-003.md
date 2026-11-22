# Thiết kế thư viện client tối thiểu có thuộc tính, bean mặc định và khóa bật tắt

## 1. Mục tiêu và hợp đồng của thư viện

Một thư viện client tích hợp Spring Boot thường cần giải quyết bốn việc:

1. Cung cấp một Java client có thể dùng độc lập.
2. Đọc endpoint và timeout từ cấu hình ứng dụng.
3. Tự đăng ký một bean mặc định khi ứng dụng có dùng thư viện.
4. Cho phép ứng dụng tắt bean mặc định hoặc thay thế nó bằng implementation riêng.

Bài thực hành xây dựng client HTTP tên **AcmeClient**, dùng Java 17 **java.net.http.HttpClient**. Spring Boot tự tạo client từ **AcmeClientProperties**. Ứng dụng có thể tắt việc tạo bean bằng **acme.client.enabled=false**, hoặc khai báo bean riêng để auto-configuration nhường quyền.

Ví dụ dùng **Java 17 và Spring Boot 3.3.13**. Thiết kế tập trung vào một hợp đồng nhỏ, dễ kiểm thử:

| Thành phần | Trách nhiệm |
|---|---|
| acme-client-core | Java client thuần, không phụ thuộc Spring |
| acme-client-spring-boot-autoconfigure | Properties, auto-configuration và bean mặc định |
| acme-client-spring-boot-starter | Artifact tiện dụng để ứng dụng thêm một dependency |
| AcmeClientProperties | Cấu hình endpoint, timeout và cờ enabled |
| AcmeClientAutoConfiguration | Tạo bean mặc định khi điều kiện phù hợp |
| @ConditionalOnMissingBean | Cho phép ứng dụng thay thế bean mặc định |
| @ConditionalOnProperty | Bật hoặc tắt việc tạo bean mặc định |

Ba module có thể nằm trong cùng một Maven multi-module repository. Nếu bài tập nhỏ, có thể đặt core và auto-configuration trong một module trước; khi phát hành thư viện dùng chung, tách chúng giúp ứng dụng chỉ cần Java client không phải kéo theo Spring Boot.

## 2. Hành vi mong muốn

Ta chọn các quy tắc cụ thể để tránh việc mỗi ứng dụng hiểu cờ bật tắt theo một cách khác nhau.

| Cấu hình | Properties bean | Bean AcmeClient do thư viện tạo |
|---|---|---|
| Không khai báo acme.client.enabled | Có | Có, vì mặc định bật |
| acme.client.enabled=true | Có | Có |
| acme.client.enabled=false | Có | Không |
| Ứng dụng tự khai báo AcmeClient | Có | Bean mặc định back off |
| Ứng dụng tự khai báo bean và đặt enabled=false | Có | Bean của ứng dụng vẫn tồn tại |

Cờ **enabled** trong bài này điều khiển **bean mặc định do auto-configuration tạo**. Nó không xóa hoặc vô hiệu hóa bean do ứng dụng tự đăng ký. Đây là ranh giới quan trọng: thư viện không nên âm thầm xóa cấu hình do ứng dụng sở hữu.

Ta chọn mặc định bật bằng hai cơ chế đồng nhất:

- Trường **enabled** trong properties có giá trị mặc định **true**.
- **@ConditionalOnProperty** đặt **matchIfMissing = true**, nên property bị thiếu vẫn cho phép bean mặc định được tạo.

Nếu muốn thư viện mặc định tắt, đổi giá trị mặc định thành **false** và đặt **matchIfMissing = false**; phải cập nhật cả tài liệu lẫn test.

## 3. Cấu trúc project

Cấu trúc đề xuất:

~~~text
acme-client/
├── pom.xml
├── acme-client-core/
│   ├── pom.xml
│   └── src/main/java/com/acme/client/
│       └── AcmeClient.java
├── acme-client-spring-boot-autoconfigure/
│   ├── pom.xml
│   ├── src/main/java/com/acme/client/autoconfigure/
│   │   ├── AcmeClientProperties.java
│   │   └── AcmeClientAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/acme/client/autoconfigure/
│       └── AcmeClientAutoConfigurationTests.java
└── acme-client-spring-boot-starter/
    └── pom.xml
~~~

Vai trò từng module:

- **core** chỉ biết Java và HTTP client của JDK. Nó không import org.springframework.
- **autoconfigure** phụ thuộc core và Spring Boot. Nó chuyển properties thành client bean.
- **starter** chủ yếu gom dependency. Ứng dụng tiêu thụ thêm starter và nhận core cùng auto-configuration theo dependency graph.

Tách module làm cho core có thể dùng trong ứng dụng Java thuần, trong khi ứng dụng Spring Boot chỉ cần một dependency starter.

## 4. Module core: tạo client Java thuần

Tệp **acme-client-core/src/main/java/com/acme/client/AcmeClient.java**:

~~~java
package com.acme.client;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Objects;

public final class AcmeClient {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final Duration requestTimeout;
    private final HttpClient httpClient;

    public AcmeClient(
            URI baseUrl,
            Duration connectTimeout,
            Duration requestTimeout) {

        this.baseUrl = normalizeBaseUrl(baseUrl);
        this.connectTimeout = requirePositive(
                connectTimeout, "connectTimeout");
        this.requestTimeout = requirePositive(
                requestTimeout, "requestTimeout");

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(this.connectTimeout)
                .build();
    }

    public HttpResponse<String> get(String path)
            throws IOException, InterruptedException {

        if (path == null || path.isBlank()) {
            throw new IllegalArgumentException(
                    "path must not be blank");
        }

        URI relativeUri = URI.create(path);
        if (relativeUri.isAbsolute()
                || relativeUri.getRawAuthority() != null) {
            throw new IllegalArgumentException(
                    "path must be relative to the configured base URL");
        }

        String relativePath = path.startsWith("/")
                ? path.substring(1)
                : path;

        URI target = this.baseUrl.resolve(relativePath);

        HttpRequest request = HttpRequest.newBuilder(target)
                .timeout(this.requestTimeout)
                .GET()
                .build();

        return this.httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    public URI getBaseUrl() {
        return this.baseUrl;
    }

    public Duration getConnectTimeout() {
        return this.connectTimeout;
    }

    public Duration getRequestTimeout() {
        return this.requestTimeout;
    }

    private static URI normalizeBaseUrl(URI baseUrl) {
        Objects.requireNonNull(baseUrl, "baseUrl");

        String scheme = baseUrl.getScheme();
        boolean supportedScheme =
                "http".equalsIgnoreCase(scheme)
                || "https".equalsIgnoreCase(scheme);

        if (!baseUrl.isAbsolute()
                || baseUrl.getHost() == null
                || !supportedScheme) {
            throw new IllegalArgumentException(
                    "baseUrl must be an absolute HTTP or HTTPS URI");
        }

        if (baseUrl.getRawQuery() != null
                || baseUrl.getRawFragment() != null) {
            throw new IllegalArgumentException(
                    "baseUrl must not contain a query or fragment");
        }

        String value = baseUrl.toString();
        return URI.create(value.endsWith("/") ? value : value + "/");
    }

    private static Duration requirePositive(
            Duration value, String name) {

        Objects.requireNonNull(value, name);

        if (value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(
                    name + " must be greater than zero");
        }

        return value;
    }
}
~~~

Client có ba trách nhiệm nhỏ:

- Chuẩn hóa **baseUrl** để đường dẫn tương đối được ghép nhất quán.
- Tạo **HttpClient** với connect timeout.
- Gửi GET với request timeout và trả **HttpResponse<String>** cho caller.

**HttpClient** của JDK có thể được dùng lại giữa nhiều request. Client này không mở kết nối mạng khi bean được tạo; kết nối chỉ được thực hiện khi gọi **get()**.

Phương thức **get()** nhận đường dẫn tương đối như **products/42** hoặc **/products/42**. Dấu slash đầu được bỏ để đường dẫn vẫn nằm dưới base path đã cấu hình. URI tuyệt đối và authority bên ngoài bị từ chối để caller không vô tình dùng client này như một URL tùy ý.

Client trả cả status code và response body. HTTP 404 hoặc 500 không tự động trở thành exception; ứng dụng tiêu thụ phải kiểm tra **response.statusCode()** và quyết định cách xử lý. Phương thức đồng bộ có thể ném **IOException** hoặc **InterruptedException**; tầng gọi cần xử lý hai trường hợp này. Nếu bắt **InterruptedException** mà không ném tiếp, hãy khôi phục interrupt flag bằng **Thread.currentThread().interrupt()**.

## 5. Module auto-configuration: khai báo properties

Properties gom cấu hình của client vào một prefix duy nhất. Không rải các property rời rạc vào nhiều class.

Tệp **AcmeClientProperties.java**:

~~~java
package com.acme.client.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.client")
public class AcmeClientProperties {

    private boolean enabled = true;

    private URI baseUrl =
            URI.create("https://api.example.test/v1/");

    private Duration connectTimeout = Duration.ofSeconds(2);

    private Duration requestTimeout = Duration.ofSeconds(5);

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getBaseUrl() {
        return this.baseUrl;
    }

    public void setBaseUrl(URI baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getConnectTimeout() {
        return this.connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return this.requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

Các giá trị mặc định:

| Property | Kiểu | Mặc định | Ý nghĩa |
|---|---|---|---|
| acme.client.enabled | boolean | true | Cho phép tạo bean client mặc định |
| acme.client.base-url | URI | https://api.example.test/v1/ | Endpoint gốc |
| acme.client.connect-timeout | Duration | 2s | Thời gian chờ thiết lập kết nối |
| acme.client.request-timeout | Duration | 5s | Thời gian tối đa cho một request |

Tên miền .test dành cho ví dụ và không phải API thật. Ứng dụng phải thay bằng endpoint của dịch vụ mình sử dụng.

Spring Boot hỗ trợ bind các kiểu **URI** và **Duration**. Người dùng có thể viết duration bằng các đơn vị dễ đọc như **1500ms**, **2s** hoặc **1m**.

Lớp properties chỉ giữ dữ liệu cấu hình. Nó không tạo HttpClient, gọi service, đọc file hoặc inject bean khác. Việc tạo client thuộc trách nhiệm của auto-configuration.

## 6. Auto-configuration: tạo bean mặc định và khóa bật tắt

Tệp **AcmeClientAutoConfiguration.java**:

~~~java
package com.acme.client.autoconfigure;

import com.acme.client.AcmeClient;

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
            havingValue = "true",
            matchIfMissing = true)
    @ConditionalOnMissingBean(AcmeClient.class)
    public AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.getBaseUrl(),
                properties.getConnectTimeout(),
                properties.getRequestTimeout());
    }
}
~~~

Hai condition có nhiệm vụ khác nhau:

**@ConditionalOnProperty kiểm tra cờ enabled.**

- Khi property thiếu, **matchIfMissing = true** cho phép tạo bean mặc định.
- Khi property là **true**, condition match.
- Khi property là **false**, method bean không được đăng ký.

**@ConditionalOnMissingBean kiểm tra ứng dụng đã cung cấp client hay chưa.**

- Nếu chưa có bean **AcmeClient**, thư viện tạo default.
- Nếu ứng dụng đã có bean **AcmeClient**, default back off.
- Return type cụ thể của method giúp Spring Boot có type metadata để đánh giá condition.

**@EnableConfigurationProperties** đăng ký **AcmeClientProperties** để Spring bind cấu hình. Trong ví dụ này, properties bean vẫn tồn tại khi **enabled=false**, vì cờ bật tắt đặt trên bean method chứ không đặt trên toàn bộ auto-configuration class. Điều đó giúp ứng dụng vẫn có thể đọc cấu hình và hiển thị trạng thái dù client mặc định không được tạo.

Không gọi **getBean()** trong auto-configuration hoặc condition để kiểm tra client. Việc kiểm tra bean presence phải dựa vào condition metadata; Spring sẽ inject dependency khi khởi tạo bean.

## 7. Đăng ký auto-configuration trong JAR

Spring Boot 3 dùng file imports để phát hiện auto-configuration từ thư viện bên ngoài.

Tạo file:

**acme-client-spring-boot-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

Nội dung:

~~~text
com.acme.client.autoconfigure.AcmeClientAutoConfiguration
~~~

Mỗi dòng là fully qualified class name của một auto-configuration. Không cần ứng dụng tiêu thụ phải dùng **@Import(AcmeClientAutoConfiguration.class)** hoặc component-scan package của thư viện.

Nếu file bị thiếu hoặc sai tên class, dependency vẫn có thể xuất hiện trong dependency tree nhưng auto-configuration không được phát hiện. Vì vậy, cần kiểm tra file này trong JAR đã đóng gói, không chỉ kiểm tra source tree.

Với Spring Boot 3.x, đăng ký auto-configuration qua key **EnableAutoConfiguration** trong **spring.factories** đã bị loại bỏ. **spring.factories** vẫn được dùng cho một số SPI khác; không nhầm các cơ chế đó với file **AutoConfiguration.imports**.

## 8. Maven dependencies cho các module

### 8.1. Core module

**acme-client-core** chỉ cần Java 17. Không thêm Spring Boot dependency vào module này.

Cấu hình compiler trong POM của core:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

### 8.2. Auto-configuration module

POM rút gọn cho **acme-client-spring-boot-autoconfigure**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-client-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>3.3.13</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong project thật, root parent có thể quản lý chung version, plugin và module. POM trên minh họa dependency tối thiểu của auto-configuration module.

**spring-boot-configuration-processor** là optional vì nó phục vụ compile-time metadata cho IDE. Processor có thể sinh metadata từ **@ConfigurationProperties**, giúp người dùng có gợi ý và completion khi viết YAML hoặc properties. Nó không phải dependency runtime cần thiết để bind cấu hình.

### 8.3. Starter module

Starter chủ yếu gom dependency để ứng dụng không phải khai báo từng artifact.

POM rút gọn của **acme-client-spring-boot-starter**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-client-spring-boot-starter</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client-spring-boot-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

Core được kéo vào qua dependency của auto-configuration module. Starter không cần chứa Java code nếu nó chỉ có nhiệm vụ tập hợp dependency.

Ứng dụng Spring Boot tiêu thụ thêm:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-client-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

Ứng dụng tiêu thụ vẫn nên dùng Spring Boot BOM của chính ứng dụng để quản lý Spring dependencies. Thư viện không nên ép version Spring Framework riêng trong POM phát hành.

## 9. Cấu hình trong ứng dụng tiêu thụ

Khi thêm starter, ứng dụng có thể cấu hình trong **application.yml**:

~~~yaml
acme:
  client:
    enabled: true
    base-url: https://catalog.example.test/api/
    connect-timeout: 1500ms
    request-timeout: 4s
~~~

Nếu không khai báo **enabled**, default client vẫn được tạo. Nếu muốn tắt:

~~~yaml
acme:
  client:
    enabled: false
~~~

Có thể dùng environment variable tương ứng:

~~~bash
ACME_CLIENT_ENABLED=false
ACME_CLIENT_BASE_URL=https://catalog.example.test/api/
ACME_CLIENT_CONNECT_TIMEOUT=1500ms
ACME_CLIENT_REQUEST_TIMEOUT=4s
~~~

Spring Boot relaxed binding ánh xạ tên environment variable sang property theo quy tắc của nó. Khi triển khai, hãy giữ cùng một prefix để tránh cấu hình trùng lặp giữa môi trường local, test và production.

### 9.1. Inject và gọi client

Ví dụ service trong ứng dụng:

~~~java
package com.example.catalog;

import com.acme.client.AcmeClient;

import java.io.IOException;
import java.net.http.HttpResponse;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final AcmeClient client;

    public CatalogService(AcmeClient client) {
        this.client = client;
    }

    public String findProduct() throws IOException, InterruptedException {
        HttpResponse<String> response = this.client.get("products/42");

        if (response.statusCode() >= 400) {
            throw new IllegalStateException(
                    "Catalog API returned HTTP " + response.statusCode());
        }

        return response.body();
    }
}
~~~

Nếu **acme.client.enabled=false** và ứng dụng không tự cung cấp **AcmeClient**, việc inject bắt buộc như ví dụ trên sẽ khiến context không thể tạo **CatalogService**. Khi tắt client, các bean tiêu thụ client cũng phải được điều kiện hóa, hoặc dependency phải được thiết kế tùy chọn theo nhu cầu ứng dụng.

## 10. Cho phép ứng dụng thay thế bean mặc định

Một thư viện tốt cho phép consumer thay implementation mặc định mà không sửa code thư viện.

Ví dụ ứng dụng tự đăng ký client:

~~~java
package com.example.catalog;

import com.acme.client.AcmeClient;

import java.net.URI;
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomClientConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new AcmeClient(
                URI.create("https://internal-catalog.example.test/api/"),
                Duration.ofSeconds(1),
                Duration.ofSeconds(3));
    }
}
~~~

Do **AcmeClientAutoConfiguration** dùng **@ConditionalOnMissingBean(AcmeClient.class)**, default bean không được đăng ký khi user bean đã có.

Một số lưu ý:

- Method trả về **AcmeClient** để Spring và condition có type metadata chính xác.
- Không khai báo bean mặc định với return type quá rộng như **Object**.
- Không cần đặt **@Primary** nếu chỉ có một bean vì default đã back off.
- Nếu ứng dụng cố ý đăng ký nhiều **AcmeClient**, ứng dụng phải giải quyết ambiguity bằng **@Primary** hoặc **@Qualifier**.
- Bean do ứng dụng khai báo vẫn tồn tại khi **acme.client.enabled=false**; property này chỉ tắt default bean của thư viện.

## 11. Kiểm thử auto-configuration với ApplicationContextRunner

**ApplicationContextRunner** tạo một context nhỏ để kiểm tra điều kiện và bean registration mà không cần khởi chạy server hoặc kết nối đến endpoint.

Tệp **AcmeClientAutoConfigurationTests.java**:

~~~java
package com.acme.client.autoconfigure;

import com.acme.client.AcmeClient;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultClientWhenEnabledPropertyIsMissing() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClientProperties.class);
            assertThat(context).hasSingleBean(AcmeClient.class);

            AcmeClient client = context.getBean(AcmeClient.class);
            assertThat(client.getBaseUrl()).isEqualTo(
                    URI.create("https://api.example.test/v1/"));
            assertThat(client.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(2));
            assertThat(client.getRequestTimeout())
                    .isEqualTo(Duration.ofSeconds(5));
        });
    }

    @Test
    void bindsEndpointAndTimeoutProperties() {
        this.runner
                .withPropertyValues(
                        "acme.client.base-url=https://catalog.example.test/api",
                        "acme.client.connect-timeout=1500ms",
                        "acme.client.request-timeout=4s")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    AcmeClientProperties properties =
                            context.getBean(AcmeClientProperties.class);
                    AcmeClient client =
                            context.getBean(AcmeClient.class);

                    assertThat(properties.getConnectTimeout())
                            .isEqualTo(Duration.ofMillis(1500));
                    assertThat(properties.getRequestTimeout())
                            .isEqualTo(Duration.ofSeconds(4));
                    assertThat(client.getBaseUrl()).isEqualTo(
                            URI.create("https://catalog.example.test/api/"));
                });
    }

    @Test
    void doesNotCreateDefaultClientWhenDisabled() {
        this.runner
                .withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(AcmeClientProperties.class);
                    assertThat(context)
                            .doesNotHaveBean(AcmeClient.class);
                    assertThat(context
                            .getBean(AcmeClientProperties.class).isEnabled())
                            .isFalse();
                });
    }

    @Test
    void backsOffWhenApplicationProvidesItsOwnClient() {
        this.runner
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).getBaseUrl())
                            .isEqualTo(URI.create(
                                    "https://custom.example.test/"));
                });
    }

    @Test
    void keepsUserClientWhenDefaultAutoConfigurationIsDisabled() {
        this.runner
                .withPropertyValues("acme.client.enabled=false")
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).getBaseUrl())
                            .isEqualTo(URI.create(
                                    "https://custom.example.test/"));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new AcmeClient(
                    URI.create("https://custom.example.test/"),
                    Duration.ofSeconds(1),
                    Duration.ofSeconds(3));
        }
    }
}
~~~

Năm test kiểm tra các hợp đồng quan trọng:

| Test | Điều cần chứng minh |
|---|---|
| Property thiếu | Default bật và client được tạo bằng giá trị mặc định |
| Property tùy chỉnh | URI và Duration được bind rồi truyền vào client |
| Enabled false | Properties bean còn, default client không có |
| User bean có mặt | Auto-configuration nhường quyền cho bean của ứng dụng |
| User bean và enabled false | Cờ tắt không xóa bean do ứng dụng sở hữu |

Các test này không gửi HTTP request. Chúng kiểm tra wiring, binding, điều kiện tạo bean và hành vi back-off. Có thể bổ sung test riêng cho **AcmeClient.get()** bằng local HTTP server nếu cần kiểm tra request/response.

Chạy test trong Maven reactor:

~~~bash
./mvnw -pl acme-client-spring-boot-autoconfigure -am test
~~~

Nếu muốn xác nhận cả starter module và artifact đóng gói:

~~~bash
./mvnw -pl acme-client-spring-boot-starter -am verify
~~~

Sau khi build, kiểm tra imports resource nằm trong JAR auto-configuration:

~~~bash
jar tf acme-client-spring-boot-autoconfigure/target/acme-client-spring-boot-autoconfigure-1.0.0.jar
~~~

Trong output cần có:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**ApplicationContextRunner** ở trên nạp class trực tiếp bằng **AutoConfigurations.of(...)**, vì vậy kiểm tra JAR resource là bước bổ sung để xác nhận discovery metadata được đóng gói.

## 12. Kiểm tra cấu hình và lỗi thường gặp

### 12.1. Không thấy bean mặc định

Kiểm tra lần lượt:

1. Ứng dụng có dependency starter hoặc auto-configuration module không?
2. Core module có nằm trong runtime classpath không?
3. File **AutoConfiguration.imports** có đúng tên class không?
4. Property **acme.client.enabled** có đang là **false** không?
5. Có điều kiện khác hoặc auto-configuration exclusion nào loại cấu hình không?
6. Bean **AcmeClient** do ứng dụng khai báo đã khiến default back off chưa?

Bật condition report bằng:

~~~bash
java -jar application.jar --debug
~~~

Tìm entry của **AcmeClientAutoConfiguration** và lý do condition match/no-match.

### 12.2. Bean có nhưng cấu hình không đúng

Kiểm tra prefix và property name. Ví dụ **acme.client.base-url** phải khớp prefix **acme.client** và field **baseUrl**.

Kiểm tra thứ tự nguồn cấu hình: command-line arguments, environment variables, external config files và packaged **application.yml** có thể có độ ưu tiên khác nhau. Đừng kết luận binder lỗi trước khi xác định nguồn nào đang thắng.

Nếu URI sai hoặc timeout bằng 0/âm, constructor của **AcmeClient** ném **IllegalArgumentException** khi tạo default bean. Thông báo lỗi nên chỉ rõ property cần sửa; trong hệ thống lớn có thể bổ sung Jakarta Bean Validation và dependency validation tương ứng để báo lỗi sớm hơn.

### 12.3. Bean mặc định không back off

- Kiểm tra custom bean có đúng type **AcmeClient** không.
- Khai báo return type cụ thể trên **@Bean** method.
- Đảm bảo custom configuration là user configuration được nạp trước auto-configuration.
- Kiểm tra context hierarchy nếu bean nằm trong parent hoặc child context.
- Không dùng một bean **Object** rồi mong condition theo **AcmeClient** suy ra runtime implementation.

### 12.4. Đã tắt nhưng ứng dụng vẫn thấy client

Trong thiết kế này, **enabled=false** chỉ ngăn method auto-configuration tạo default bean. Nếu ứng dụng có **@Bean AcmeClient** riêng, bean đó vẫn tồn tại. Nếu mục tiêu là tắt cả tính năng sử dụng client, các bean nghiệp vụ tiêu thụ client cũng cần được điều kiện hóa hoặc ứng dụng phải kiểm soát luồng gọi.

### 12.5. Properties không có gợi ý trong IDE

Kiểm tra dependency **spring-boot-configuration-processor** trong auto-configuration module. Đây là compile-time processor; nó tạo metadata cho IDE. Việc bind runtime vẫn do Spring Boot thực hiện.

## 13. Quyết định thiết kế cần thống nhất trước khi phát hành

| Câu hỏi | Quyết định trong ví dụ | Khi nào nên thay đổi |
|---|---|---|
| Client mặc định bật hay tắt? | Bật nếu property bị thiếu | Thư viện nhạy cảm hoặc tạo kết nối tốn kém có thể chọn mặc định tắt |
| enabled điều khiển gì? | Chỉ default bean | Nếu muốn điều khiển cả feature, áp dụng điều kiện ở ranh giới feature của ứng dụng |
| User bean có được ưu tiên? | Có, default back off | Chỉ đổi nếu thư viện bắt buộc một implementation cụ thể |
| Properties có tồn tại khi disabled? | Có | Nếu muốn tắt toàn bộ integration, có thể đặt condition ở class-level |
| Client có phụ thuộc Spring? | Không, core dùng JDK | Chỉ thêm Spring API vào core nếu đó là một phần public contract có chủ đích |
| HTTP API đồng bộ hay reactive? | Đồng bộ bằng JDK HttpClient | Dùng adapter WebClient riêng nếu consumer chạy reactive stack |
| Timeout có giá trị mặc định? | Có, 2s connect và 5s request | Điều chỉnh dựa trên latency và SLA thực tế của dịch vụ |

Không nên thêm retry, authentication, circuit breaker, metrics hoặc cache vào core chỉ để làm ví dụ phức tạp hơn. Những năng lực đó có thể là module hoặc extension riêng, với dependency và policy rõ ràng.

## 14. Những sai lầm thường gặp

- **Đặt @ConfigurationProperties nhưng không đăng ký:** thêm @EnableConfigurationProperties(AcmeClientProperties.class) hoặc configuration properties scanning phù hợp.
- **Quên file AutoConfiguration.imports:** JAR có class nhưng Boot không tự phát hiện auto-configuration.
- **Dùng @ConditionalOnProperty mà quên matchIfMissing:** property thiếu sẽ không tạo default nếu mặc định của condition là không match.
- **Properties nói enabled=true nhưng condition mặc định tắt:** hai chính sách mâu thuẫn; đồng bộ giá trị mặc định và matchIfMissing.
- **Quên @ConditionalOnMissingBean:** ứng dụng không thể thay thế default hoặc dễ gặp nhiều bean cùng type.
- **Trả Object từ @Bean method:** mất type metadata cần cho bean conditions.
- **Đặt cờ enabled ở sai cấp:** đặt trên toàn class sẽ tắt cả properties bean; đặt trên method chỉ tắt default bean. Chọn theo hợp đồng đã công bố.
- **Dùng @DependsOn để điều khiển điều kiện đăng ký:** nó liên quan instance initialization, không thay thế bean conditions.
- **Tạo HTTP connection trong constructor:** có thể làm context startup phụ thuộc mạng và khiến test khó ổn định. Constructor chỉ nên chuẩn bị client.
- **Gọi API trong lúc bind properties:** properties là dữ liệu cấu hình, không phải lifecycle hook để thực hiện I/O.
- **Đặt timeout bằng 0 hoặc số âm:** phải kiểm tra giá trị và báo lỗi dễ hiểu.
- **Để core phụ thuộc Spring Boot:** ứng dụng Java thuần bị kéo theo framework không cần thiết.
- **Dùng latest.release trong build:** dependency có thể thay đổi mà không có source change; pin BOM hoặc version catalog rõ ràng.
- **Chỉ test default case:** cần kiểm tra disabled, custom override và binding giá trị.
- **Chỉ test AutoConfigurations.of(...):** cần kiểm tra resource trong JAR để xác nhận discovery metadata được đóng gói.
- **Nghĩ disabled xóa user bean:** condition trên default method không xóa bean do ứng dụng đăng ký.
- **Nhầm connect timeout với request timeout:** connect timeout giới hạn thiết lập kết nối; request timeout giới hạn thời gian cho request cụ thể.

## 15. Quy trình triển khai từ đầu đến cuối

1. Chốt public API của client thuần Java và tránh đưa Spring type vào core.
2. Chọn prefix duy nhất, ví dụ **acme.client**.
3. Tạo **AcmeClientProperties** với kiểu dữ liệu và default rõ ràng.
4. Đăng ký properties bằng **@EnableConfigurationProperties**.
5. Tạo auto-configuration với một **@Bean** method trả về type client cụ thể.
6. Đặt **@ConditionalOnProperty** để kiểm soát default bean và quyết định rõ hành vi khi property thiếu.
7. Đặt **@ConditionalOnMissingBean** để cho phép ứng dụng thay implementation.
8. Đăng ký class trong **AutoConfiguration.imports**.
9. Cấu hình configuration processor để sinh metadata cho IDE.
10. Viết test cho default, binding, disabled, user override và custom bean khi disabled.
11. Kiểm tra JAR có imports resource và starter kéo đúng dependency.
12. Công bố property table, default, semantics của enabled và cách thay thế bean.

## 16. Câu hỏi tự kiểm tra

1. Core client có nên phụ thuộc Spring Boot không? **Không.** Core nên giữ độc lập nếu không cần Spring API.
2. Annotation nào bind **AcmeClientProperties**? **@ConfigurationProperties(prefix = "acme.client").**
3. Làm thế nào để đăng ký properties class từ auto-configuration? **Dùng @EnableConfigurationProperties(AcmeClientProperties.class).**
4. Annotation nào tạo bean mặc định khi chưa có bean cùng type? **@ConditionalOnMissingBean(AcmeClient.class).**
5. Annotation nào bật/tắt default bean theo property? **@ConditionalOnProperty.**
6. matchIfMissing=true có ý nghĩa gì? **Property bị thiếu vẫn cho condition match.**
7. Vì sao cần return type cụ thể trên @Bean method? **Để Spring có type metadata chính xác khi đánh giá bean conditions.**
8. User-defined AcmeClient có bị xóa khi enabled=false không? **Không.** Cờ chỉ tắt bean mặc định của auto-configuration.
9. Properties bean có còn khi enabled=false trong ví dụ không? **Có**, vì condition đặt trên bean method thay vì auto-configuration class.
10. File đăng ký auto-configuration của Boot 3 nằm ở đâu? **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.**
11. Configuration processor có cần ở runtime không? **Không.** Nó sinh metadata ở compile time để IDE hỗ trợ completion.
12. connectTimeout và requestTimeout khác nhau thế nào? **Một giá trị giới hạn thiết lập kết nối, giá trị còn lại giới hạn thời gian của request.**
13. Test nào kiểm tra bean registration mà không chạy server? **ApplicationContextRunner.**
14. Vì sao cần kiểm tra JAR sau khi build? **Để xác nhận imports resource thực sự được đóng gói và Boot có thể phát hiện auto-configuration.**

## 17. Tài liệu tham khảo chính thức

- [Creating Your Own Auto-configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): điều kiện, default bean, back-off, ordering và đăng ký auto-configuration.
- [Externalized Configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): bind @ConfigurationProperties và đăng ký bằng @EnableConfigurationProperties.
- [ConditionalOnProperty API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue, matchIfMissing và quy tắc so khớp property.
- [ConditionalOnMissingBean API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): điều kiện tạo default khi chưa có bean phù hợp.
- [AutoConfiguration API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): auto-configuration annotation và thứ tự xử lý.
- [ApplicationContextRunner API — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): dựng context độc lập để test auto-configuration.
- [Configuration Metadata Specification — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html): metadata được sinh để IDE cung cấp trợ giúp và code completion.
