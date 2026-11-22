# Xây dựng PropertySourceLocator cho nguồn cấu hình riêng

Một ứng dụng Spring Cloud có thể cần đọc cấu hình từ một hệ thống nội bộ thay vì Spring Cloud Config Server. Ví dụ, doanh nghiệp đã có Configuration API, tenant configuration service hoặc một kho cấu hình do nền tảng vận hành. Ứng dụng vẫn cần đưa các giá trị này vào Spring Environment để có thể bind bằng @ConfigurationProperties, đọc qua Environment hoặc inject bằng @Value.

Spring Cloud Commons cung cấp PropertySourceLocator như một extension point của bootstrap. Locator nhận Environment sắp được dùng cho ApplicationContext, truy xuất nguồn cấu hình bên ngoài và trả về một PropertySource. Spring Cloud đưa PropertySource đó vào Environment trước khi các bean ứng dụng được khởi tạo.

Bài thực hành này xây dựng một locator đọc cấu hình từ HTTP API riêng. API nhận application name và active profiles, xác thực bằng bearer token, rồi trả JSON dạng key-value. Locator chuyển JSON thành MapPropertySource, kiểm tra namespace được phép, xử lý timeout và fail-fast, đồng thời hỗ trợ lần gọi theo profile.

Đây là cơ chế bootstrap của Spring Cloud. Với dự án mới muốn tích hợp nguồn cấu hình trực tiếp vào quy trình Config Data của Spring Boot, cần cân nhắc ConfigDataLocationResolver và ConfigDataLoader. Bài tập tập trung vào PropertySourceLocator theo đúng đề bài, đồng thời chỉ ra ranh giới giữa hai extension point.

## 1. Kết quả cần đạt

Hoàn thành bài thực hành, người học có thể:

1. Giải thích vai trò của PropertySourceLocator trong bootstrap context.
2. Thiết kế hợp đồng HTTP cho một custom configuration service.
3. Tạo PropertySourceLocator nhận application name và profile từ Environment.
4. Đọc cấu hình HTTP và chuyển JSON thành MapPropertySource.
5. Đăng ký bootstrap configuration bằng META-INF/spring.factories.
6. Bảo đảm locator nằm trong bootstrap context và không bị component scan nhầm.
7. Xử lý timeout, lỗi HTTP, lỗi JSON và chính sách fail-fast.
8. Giới hạn property key mà nguồn bên ngoài được phép cung cấp.
9. Hiểu vì sao locator có thể được gọi hai lần khi dùng profile.
10. Kiểm tra PropertySource, precedence và kết quả binding trong ứng dụng.
11. Viết test với HTTP server cục bộ mà không phụ thuộc môi trường thật.
12. Phân biệt PropertySourceLocator với Config Data API và chọn đúng cách mở rộng.

Kết quả cuối cùng là một ứng dụng Orders có thể nhận endpoint thanh toán, timeout và feature flag từ một custom configuration API trước khi các bean nghiệp vụ được tạo.

## 2. Bối cảnh và kiến trúc

### 2.1. Bài toán

Giả sử nền tảng của tổ chức cung cấp một API cấu hình có sẵn:

- Mỗi ứng dụng có một bộ cấu hình riêng.
- Mỗi môi trường hoặc profile có thể ghi đè cấu hình chung.
- API yêu cầu bearer token.
- Phản hồi là JSON với các property key dạng phẳng.
- Ứng dụng cần nạp cấu hình trước khi tạo DataSource, HTTP client hoặc các bean phụ thuộc.

Ví dụ, Orders cần cấu hình sau:

~~~properties
app.payment.base-url=https://payment-staging.internal
app.payment.timeout=450ms
feature.checkout.enabled=true
~~~

Các giá trị được quản lý ở configuration service. Ứng dụng không hard-code endpoint staging hoặc production trong artifact.

### 2.2. Luồng khởi tạo

~~~mermaid
flowchart TD
    A[SpringApplication starts] --> B[Bootstrap context]
    B --> C[Load bootstrap properties]
    C --> D[Discover BootstrapConfiguration]
    D --> E[Create PropertySourceLocator]
    E --> F[Read application name and profiles]
    F --> G[Call custom configuration API]
    G --> H[Validate response]
    H --> I[Create MapPropertySource]
    I --> J[Add source to Environment]
    J --> K[Create main ApplicationContext]
    K --> L[Bind ConfigurationProperties]
    L --> M[Application ready]
~~~

Locator chạy ở giai đoạn bootstrap. Nó phải hoàn thành việc lấy nguồn cấu hình trước khi main ApplicationContext tạo các bean cần các property đó.

### 2.3. Vai trò của các thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| Bootstrap context | Chuẩn bị nguồn cấu hình bên ngoài trước main context |
| BootstrapConfiguration | Đăng ký cấu hình và bean dành cho bootstrap |
| PropertySourceLocator | Truy xuất và trả về PropertySource |
| Environment | Cung cấp application name, profile và property sources hiện có |
| MapPropertySource | Đưa các key-value đã tải vào Environment |
| ConfigurationProperties | Bind cấu hình thành object có kiểu trong ứng dụng |
| Custom configuration API | Lưu và phục vụ cấu hình theo ứng dụng/profile |

### 2.4. Ranh giới trách nhiệm

PropertySourceLocator chỉ chịu trách nhiệm tìm và trả về nguồn property. Nó không nên:

- Tạo các bean nghiệp vụ của ứng dụng.
- Khởi tạo toàn bộ ApplicationContext.
- Tự polling cấu hình liên tục.
- Giữ một bản Environment có thể thay đổi để dùng cho toàn bộ vòng đời ứng dụng.
- Ghi secret hoặc response body chứa dữ liệu nhạy cảm vào log.
- Quyết định thay đổi bean graph sau khi main context đã khởi tạo.

Nếu muốn cập nhật cấu hình sau startup, cần thiết kế riêng cơ chế refresh, event broadcast hoặc runtime configuration provider. Việc locator chạy lúc bootstrap không tự tạo ra một luồng đồng bộ liên tục.

## 3. Thiết kế hợp đồng của Configuration API

### 3.1. Request

Locator gọi endpoint:

~~~http
GET /v1/config?application=orders-service&profiles=staging HTTP/1.1
Host: config.internal
Accept: application/json
Authorization: Bearer <token>
~~~

Các tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| application | Giá trị spring.application.name |
| profiles | Danh sách active profile, phân cách bằng dấu phẩy |
| Authorization | Bearer token do môi trường triển khai cấp |

Nếu chưa có active profile, locator gửi profiles rỗng để API trả cấu hình chung. Khi profile được xác định, locator có thể được gọi lại với danh sách profile tương ứng.

### 3.2. Response thành công

API trả HTTP 200 với JSON object có key phẳng:

~~~json
{
  "app.payment.base-url": "https://payment-staging.internal",
  "app.payment.timeout": "450ms",
  "feature.checkout.enabled": true
}
~~~

Mỗi key là một Spring property. Các giá trị có thể là String, number hoặc boolean. Các cấu trúc lồng nhau không thuộc hợp đồng của bài lab; nếu cần cấu hình lồng nhau, API nên trả key phẳng theo quy tắc dot notation.

### 3.3. Mã trạng thái

| HTTP status | Ý nghĩa | Hành vi đề xuất |
| --- | --- | --- |
| 200 | Có cấu hình | Parse và tạo PropertySource |
| 404 | Không có cấu hình cho ứng dụng/profile | Fail hoặc bỏ qua theo fail-fast |
| 401/403 | Token sai hoặc không đủ quyền | Dừng startup |
| 400 | Request sai | Dừng startup |
| 5xx | Configuration service lỗi | Dừng startup nếu cấu hình bắt buộc |
| Timeout/network error | Không truy cập được API | Fail-fast hoặc bỏ qua nếu nguồn tùy chọn |

Không trả thông tin nội bộ như token, stack trace hoặc credential trong error response.

### 3.4. Ví dụ dữ liệu theo profile

Cấu hình chung:

~~~json
{
  "app.payment.timeout": "800ms",
  "feature.checkout.enabled": false
}
~~~

Cấu hình staging:

~~~json
{
  "app.payment.base-url": "https://payment-staging.internal",
  "app.payment.timeout": "450ms",
  "feature.checkout.enabled": true
}
~~~

Cấu hình production:

~~~json
{
  "app.payment.base-url": "https://payment.internal",
  "app.payment.timeout": "300ms",
  "feature.checkout.enabled": true
}
~~~

API có thể hợp nhất cấu hình chung với profile trước khi trả response. Hoặc API trả từng lớp riêng và locator xử lý hợp nhất. Trong bài lab này, API trả về một map đã được hợp nhất cho application/profile đang yêu cầu.

## 4. Chuẩn bị project

### 4.1. Phiên bản nền tảng

Dùng JDK 17 trở lên và một cặp Spring Boot/Spring Cloud tương thích theo release train. Quản lý dependency Spring Cloud bằng BOM, không tự chọn version rời rạc cho từng starter.

Các API trong bài dùng Spring Cloud Context với PropertySourceLocator và Spring Boot Config Data hiện đại. Nếu dự án đang dùng release train khác, kiểm tra Javadoc và reference documentation của đúng phiên bản trước khi áp dụng.

### 4.2. Dependency Maven

Ví dụ phần dependency management:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>${spring-cloud.version}</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Dependencies cần dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-json</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-bootstrap</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

spring-cloud-starter-bootstrap kích hoạt bootstrap infrastructure cần cho ví dụ này. Nếu không dùng starter, phải bật bootstrap theo cơ chế được tài liệu Spring Cloud của release train đó hỗ trợ.

### 4.3. Cấu trúc thư mục

Tổ chức source như sau:

~~~text
orders-service/
  src/
    main/
      java/
        com/example/orders/
          OrdersApplication.java
          config/
            PaymentProperties.java
            CheckoutFeatureProperties.java
        com/example/bootstrap/
          CustomBootstrapConfiguration.java
          HttpPropertySourceLocator.java
      resources/
        bootstrap.yml
        application.yml
        META-INF/
          spring.factories
    test/
      java/
        com/example/bootstrap/
          HttpPropertySourceLocatorTest.java
~~~

Package bootstrap được đặt ngoài package com.example.orders để tránh bị component scan của OrdersApplication phát hiện và đăng ký lại trong main context.

## 5. Khai báo cấu hình bootstrap

### 5.1. File bootstrap.yml

Tạo src/main/resources/bootstrap.yml:

~~~yaml
spring:
  application:
    name: orders-service

app:
  config-source:
    enabled: ${CUSTOM_CONFIG_ENABLED:false}
    uri: ${CUSTOM_CONFIG_URI:http://localhost:8099/v1/config}
    token: ${CUSTOM_CONFIG_TOKEN:}
    fail-fast: true
~~~

Các property:

- spring.application.name xác định application mà API cần trả cấu hình.
- app.config-source.enabled cho phép bật/tắt locator trong từng môi trường.
- app.config-source.uri là endpoint của custom configuration API.
- app.config-source.token nhận bearer token từ biến môi trường.
- app.config-source.fail-fast xác định hành vi khi API không có cấu hình hoặc không truy cập được.

Trong môi trường local, enabled mặc định false giúp ứng dụng vẫn chạy khi chưa có mock configuration service. Trong staging/production, pipeline cần bật nguồn cấu hình và cấp token qua secret store.

Không ghi token thật vào bootstrap.yml, application.yml hoặc repository.

### 5.2. File application.yml

Tạo cấu hình mặc định an toàn:

~~~yaml
app:
  payment:
    base-url: https://payment-default.internal
    timeout: 800ms

feature:
  checkout:
    enabled: false
~~~

Custom PropertySource có thể cung cấp các key cùng tên. Sau khi locator được đăng ký đúng, ứng dụng có thể đọc giá trị cuối cùng từ Environment và bind vào object.

### 5.3. Vì sao application name cần sẵn sàng ở bootstrap?

Locator cần biết nó đang tải cấu hình cho service nào. Nếu spring.application.name chỉ xuất hiện trong một nguồn chưa được nạp khi locator chạy, API có thể nhận sai application hoặc không nhận được tên.

Đặt application name trong bootstrap.yml giúp nó có sẵn ở giai đoạn bootstrap. Có thể dùng biến môi trường nếu nhiều deployment dùng chung artifact và mỗi deployment có tên ứng dụng riêng.

## 6. Đăng ký BootstrapConfiguration

### 6.1. Tạo cấu hình bootstrap

Tạo com.example.bootstrap.CustomBootstrapConfiguration:

~~~java
package com.example.bootstrap;

import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomBootstrapConfiguration {

    @Bean
    PropertySourceLocator httpPropertySourceLocator() {
        return new HttpPropertySourceLocator();
    }
}
~~~

Class này được nạp trong bootstrap context. Bean trả về một PropertySourceLocator để Spring Cloud gọi trong quá trình chuẩn bị property sources.

### 6.2. Đăng ký qua META-INF/spring.factories

Tạo file src/main/resources/META-INF/spring.factories:

~~~properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=com.example.bootstrap.CustomBootstrapConfiguration
~~~

Spring Cloud đọc danh sách BootstrapConfiguration, tạo bootstrap context và nạp các cấu hình được khai báo. PropertySourceLocator được đăng ký trong context này.

### 6.3. Tránh component scan nhầm

Bootstrap configuration có thể bị scan vào main context nếu package nằm bên dưới package gốc của @SpringBootApplication.

Ví dụ không nên:

~~~text
com.example.orders/
  OrdersApplication.java
  bootstrap/
    CustomBootstrapConfiguration.java
~~~

Nếu OrdersApplication dùng component scan mặc định từ com.example.orders, class bootstrap có thể bị scan thêm lần nữa.

Ví dụ phù hợp:

~~~text
com.example/
  bootstrap/
    CustomBootstrapConfiguration.java
  orders/
    OrdersApplication.java
~~~

Trong ứng dụng lớn, package bootstrap nên được đặt riêng và được kiểm tra trong integration test để tránh đăng ký bean hai lần.

## 7. Cài đặt HttpPropertySourceLocator

### 7.1. Import cần thiết

Tạo com.example.bootstrap.HttpPropertySourceLocator:

~~~java
package com.example.bootstrap;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.cloud.bootstrap.config.PropertySourceLocator;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;
import org.springframework.util.StringUtils;
~~~

### 7.2. Khai báo locator

~~~java
@Order(Ordered.LOWEST_PRECEDENCE)
public class HttpPropertySourceLocator implements PropertySourceLocator {

    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    public HttpPropertySourceLocator() {
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        this.objectMapper = new ObjectMapper();
    }

    @Override
    public PropertySource<?> locate(Environment environment) {
        boolean enabled = environment.getProperty(
                "app.config-source.enabled",
                Boolean.class,
                false
        );

        if (!enabled) {
            return null;
        }

        String endpoint = environment.getProperty(
                "app.config-source.uri"
        );

        if (!StringUtils.hasText(endpoint)) {
            throw new IllegalStateException(
                    "app.config-source.uri must be configured when the source is enabled"
            );
        }

        String application = environment.getProperty(
                "spring.application.name"
        );

        if (!StringUtils.hasText(application)) {
            throw new IllegalStateException(
                    "spring.application.name is required by the custom configuration source"
            );
        }

        String token = environment.getProperty(
                "app.config-source.token"
        );

        if (!StringUtils.hasText(token)) {
            throw new IllegalStateException(
                    "app.config-source.token must be supplied when the source is enabled"
            );
        }

        boolean failFast = environment.getProperty(
                "app.config-source.fail-fast",
                Boolean.class,
                true
        );

        String profiles = String.join(
                ",",
                environment.getActiveProfiles()
        );

        URI requestUri = buildRequestUri(
                endpoint,
                application,
                profiles
        );

        HttpRequest request = HttpRequest.newBuilder(requestUri)
                .timeout(Duration.ofSeconds(3))
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + token)
                .GET()
                .build();

        return loadPropertySource(
                request,
                application,
                profiles,
                failFast
        );
    }
}
~~~

Đây là phần khung của class. Ở các mục tiếp theo, đặt những helper method vào bên trong HttpPropertySourceLocator, trước dấu đóng class cuối cùng.

Locator thực hiện các bước:

1. Kiểm tra nguồn có được bật không.
2. Đọc endpoint, application name và token.
3. Lấy active profiles từ Environment.
4. Tạo HTTP request với timeout.
5. Gọi API và chuyển response thành PropertySource.

Nếu nguồn không được bật, locator trả null. Đây là cách biểu diễn rằng locator không bổ sung property source nào.

### 7.3. Tạo URI theo application và profiles

Thêm các method sau vào class:

~~~java
private URI buildRequestUri(
        String endpoint,
        String application,
        String profiles
) {
    String separator = endpoint.contains("?") ? "&" : "?";

    String query = "application="
            + encode(application)
            + "&profiles="
            + encode(profiles);

    return URI.create(endpoint + separator + query);
}

private String encode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8);
}
~~~

Không nối trực tiếp application name hoặc profile vào URL mà không encode. Các giá trị có dấu cách, dấu phẩy hoặc ký tự đặc biệt cần được biểu diễn hợp lệ trong query string.

### 7.4. Gọi API và xử lý response

Thêm method:

~~~java
private PropertySource<?> loadPropertySource(
        HttpRequest request,
        String application,
        String profiles,
        boolean failFast
) {
    try {
        HttpResponse<String> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)
        );

        if (response.statusCode() == 404 && !failFast) {
            return null;
        }

        if (response.statusCode() >= 500 && !failFast) {
            return null;
        }

        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException(
                    "Custom configuration service returned HTTP "
                            + response.statusCode()
            );
        }

        Map<String, Object> values = objectMapper.readValue(
                response.body(),
                new TypeReference<LinkedHashMap<String, Object>>() {
                }
        );

        if (values == null || values.isEmpty()) {
            return null;
        }

        validateValues(values);

        String profilePart = StringUtils.hasText(profiles)
                ? profiles.replace(",", "_")
                : "base";

        String sourceName = "custom-http:"
                + application
                + ":"
                + profilePart;

        Map<String, Object> immutableValues =
                Collections.unmodifiableMap(new LinkedHashMap<>(values));

        return new MapPropertySource(
                sourceName,
                immutableValues
        );
    }
    catch (InterruptedException exception) {
        Thread.currentThread().interrupt();

        throw new IllegalStateException(
                "Interrupted while loading custom configuration",
                exception
        );
    }
    catch (JsonProcessingException exception) {
        throw new IllegalStateException(
                "Custom configuration service returned invalid JSON",
                exception
        );
    }
    catch (IOException exception) {
        if (!failFast) {
            return null;
        }

        throw new IllegalStateException(
                "Could not load custom configuration",
                exception
        );
    }
}
~~~

Một số quyết định đáng chú ý:

- Timeout kết nối và timeout request có giới hạn.
- 404 có thể được bỏ qua nếu nguồn không bắt buộc.
- HTTP status khác 2xx là lỗi mặc định; chỉ 404 và 5xx được bỏ qua khi fail-fast=false.
- Khi thread bị interrupt, locator khôi phục interrupt flag trước khi báo lỗi.
- Response body không được đưa vào exception message vì có thể chứa dữ liệu nhạy cảm.
- Map được bọc read-only để tránh thay đổi property source sau khi đã thêm vào Environment.

### 7.5. Chỉ chấp nhận property key thuộc namespace được phép

Thêm method:

~~~java
private void validateValues(Map<String, Object> values) {
    for (Map.Entry<String, Object> entry : values.entrySet()) {
        String key = entry.getKey();
        Object value = entry.getValue();

        boolean allowedNamespace = key != null
                && (key.startsWith("app.")
                || key.startsWith("feature."));

        if (!allowedNamespace) {
            throw new IllegalArgumentException(
                    "Custom configuration contains a property outside the allowed namespaces"
            );
        }

        if (value == null
                || value instanceof Map<?, ?>
                || value instanceof List<?>) {
            throw new IllegalArgumentException(
                    "Custom configuration values must be non-null scalar values"
            );
        }
    }
}
~~~

Bài lab chỉ cho phép API cấp property thuộc app.* và feature.*. Những key điều khiển nền tảng như spring.*, management.* hoặc server.* không được API này thay đổi.

Đây là một ranh giới quan trọng. Nếu nguồn cấu hình bên ngoài có thể thay tùy ý mọi property, nó có thể tác động đến profile, bảo mật, endpoint quản trị hoặc cấu trúc bean của ứng dụng.

Trong hệ thống thực tế, allowlist cần được thiết kế theo quyền sở hữu property. Không nên chỉ dựa vào việc API đã xác thực để cho phép mọi key.

## 8. Hoàn thiện ứng dụng Orders

### 8.1. Main application

Tạo OrdersApplication:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

ConfigurationPropertiesScan tìm các class có @ConfigurationProperties trong package ứng dụng.

### 8.2. PaymentProperties

Tạo class cấu hình:

~~~java
package com.example.orders.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        String baseUrl,
        Duration timeout
) {
}
~~~

Record phù hợp vì các giá trị này được nạp lúc startup và không cần mutable rebind trong bài thực hành.

### 8.3. CheckoutFeatureProperties

~~~java
package com.example.orders.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "feature.checkout")
public record CheckoutFeatureProperties(
        boolean enabled
) {
}
~~~

### 8.4. Xác nhận cấu hình đã được bind

Có thể tạo một ApplicationRunner chỉ in thông tin không nhạy cảm:

~~~java
package com.example.orders;

import com.example.orders.config.CheckoutFeatureProperties;
import com.example.orders.config.PaymentProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrdersStartupConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrdersStartupConfiguration.class);

    @Bean
    ApplicationRunner showConfiguration(
            PaymentProperties payment,
            CheckoutFeatureProperties checkout
    ) {
        return args -> log.info(
                "Payment endpoint configured: {}, timeout: {}, checkout enabled: {}",
                payment.baseUrl(),
                payment.timeout(),
                checkout.enabled()
        );
    }
}
~~~

Không log bearer token, password hoặc toàn bộ Environment. Mục tiêu của runner là xác nhận cấu hình đã được nạp và bind đúng.

## 9. Hiểu thứ tự và hai lần gọi theo profile

### 9.1. Locator nhận Environment của ứng dụng sắp khởi tạo

Environment truyền vào locate là Environment của ApplicationContext mà Spring Cloud đang chuẩn bị thêm property sources.

Environment đã có các property sources thông thường mà Spring Boot cung cấp. Vì vậy, locator có thể đọc spring.application.name, active profiles và các thông tin bootstrap cần thiết để xác định nguồn dữ liệu.

### 9.2. Từ Spring Cloud 2022.0.3, locator có thể được gọi hai lần

Spring Cloud Commons ghi nhận từ phiên bản 2022.0.3, PropertySourceLocators được gọi hai lần:

1. Lần đầu lấy property sources khi chưa có active profiles. Nguồn cấu hình có thể cung cấp dữ liệu chung.
2. Sau khi main ApplicationContext khởi tạo, locator được gọi lại với active profiles để lấy cấu hình profile-specific.

Do đó, implementation cần idempotent và không giả định chỉ được gọi đúng một lần.

Ví dụ:

~~~text
Lần 1:
application = orders-service
profiles   =

Lần 2:
application = orders-service
profiles   = staging
~~~

Tên PropertySource trong ví dụ có chứa application và profile để phân biệt hai lần tải.

### 9.3. Không lưu profile trong biến static

Không nên dùng static field để lưu active profile hoặc response của lần gọi trước. Locator có thể được gọi nhiều lần trong lifecycle bootstrap và có thể được dùng trong context hierarchy.

Mỗi lần locate nên đọc Environment được truyền vào, tạo request tương ứng và trả về một PropertySource độc lập.

### 9.4. Nguồn chung và profile-specific

Configuration API có thể trả về:

- Cấu hình chung khi profiles rỗng.
- Cấu hình bổ sung hoặc ghi đè khi có active profile.

Trong bài lab, API đã hợp nhất cấu hình chung và profile-specific thành một map cho từng request. Nếu API trả hai lớp riêng, cần quy định rõ precedence và tên PropertySource để profile-specific source thắng theo thiết kế.

### 9.5. Thứ tự giữa nhiều locator

Nếu ứng dụng có nhiều PropertySourceLocator, thứ tự xử lý có thể được điều khiển bằng @Order hoặc Ordered. Ví dụ trong bài dùng LOWEST_PRECEDENCE để locator HTTP có thứ tự thấp trong danh sách locator.

Khi có nhiều nguồn cùng cung cấp một key, hãy kiểm tra thứ tự thực tế của composite property source trong Environment. Không chỉ dựa vào tên source hoặc thứ tự khai báo trong một file.

### 9.6. Remote property source và local override

Property source được thêm từ bootstrap thường có precedence cao. Điều đó có thể khiến giá trị từ nguồn bên ngoài thắng application.yml hoặc file local.

Spring Cloud Config có cơ chế allowOverride và các thuộc tính override liên quan dành cho remote property source của Config Server. Không tự động giả định các cờ đó điều khiển custom locator này. Với custom source, hãy xác định rõ chính sách override và kiểm tra bằng test.

## 10. Kiểm thử locator với HTTP server cục bộ

### 10.1. Mục tiêu test

Không gọi configuration service thật trong unit test. Dùng com.sun.net.httpserver.HttpServer để tạo endpoint tạm trên loopback.

Test cần xác nhận:

- Locator gọi đúng path.
- Query chứa application name và profile.
- Bearer token được gửi.
- JSON được chuyển thành MapPropertySource.
- Property key nằm trong allowlist.
- Nguồn bị tắt thì locator trả null.
- API lỗi được xử lý theo fail-fast policy.

### 10.2. Test tải cấu hình thành công

~~~java
package com.example.bootstrap;

import static org.assertj.core.api.Assertions.assertThat;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.PropertySource;
import org.springframework.mock.env.MockEnvironment;

class HttpPropertySourceLocatorTest {

    @Test
    void loadsPropertiesForApplicationAndProfile() throws IOException {
        AtomicReference<String> query = new AtomicReference<>();
        AtomicReference<String> authorization = new AtomicReference<>();

        String json = """
                {
                  "app.payment.base-url": "https://payment-staging.internal",
                  "app.payment.timeout": "450ms",
                  "feature.checkout.enabled": true
                }
                """;

        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0),
                0
        );

        server.createContext("/v1/config", exchange -> {
            query.set(exchange.getRequestURI().getRawQuery());
            authorization.set(
                    exchange.getRequestHeaders().getFirst("Authorization")
            );

            byte[] body = json.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type",
                    "application/json"
            );

            exchange.sendResponseHeaders(200, body.length);

            try (OutputStream output = exchange.getResponseBody()) {
                output.write(body);
            }
            finally {
                exchange.close();
            }
        });

        server.start();

        try {
            String uri = "http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/v1/config";

            MockEnvironment environment = new MockEnvironment()
                    .withProperty("app.config-source.enabled", "true")
                    .withProperty("app.config-source.uri", uri)
                    .withProperty("app.config-source.token", "test-token")
                    .withProperty("app.config-source.fail-fast", "true")
                    .withProperty("spring.application.name", "orders-service");

            environment.setActiveProfiles("staging");

            HttpPropertySourceLocator locator =
                    new HttpPropertySourceLocator();

            PropertySource<?> source = locator.locate(environment);

            assertThat(source).isNotNull();

            assertThat(source.getProperty("app.payment.base-url"))
                    .isEqualTo("https://payment-staging.internal");

            assertThat(source.getProperty("app.payment.timeout"))
                    .isEqualTo("450ms");

            assertThat(source.getProperty("feature.checkout.enabled"))
                    .isEqualTo(true);

            assertThat(query.get())
                    .contains("application=orders-service")
                    .contains("profiles=staging");

            assertThat(authorization.get())
                    .isEqualTo("Bearer test-token");
        }
        finally {
            server.stop(0);
        }
    }
}
~~~

Test dùng cổng động để tránh xung đột port. Token chỉ là giá trị giả trong test và không được dùng ở môi trường thật.

### 10.3. Test nguồn bị tắt

~~~java
@Test
void returnsNullWhenSourceIsDisabled() {
    MockEnvironment environment = new MockEnvironment()
            .withProperty("app.config-source.enabled", "false");

    HttpPropertySourceLocator locator =
            new HttpPropertySourceLocator();

    assertThat(locator.locate(environment)).isNull();
}
~~~

Khi disabled, locator không cần URI, token hoặc HTTP server.

### 10.4. Test profile được thay đổi giữa hai lần gọi

Tạo một test dùng HTTP server và ghi lại query string. Gọi locator lần đầu khi không có active profile. Sau đó gọi:

~~~java
environment.setActiveProfiles("staging");
~~~

Gọi locator lần hai và xác nhận query chứa profiles=staging.

Test này mô phỏng việc locator được gọi lại sau khi active profile đã được xác định. Không dùng static cache để giữ kết quả lần đầu.

### 10.5. Test property key không được phép

Cho HTTP server trả response:

~~~json
{
  "app.payment.timeout": "450ms",
  "spring.datasource.password": "not-allowed"
}
~~~

Kỳ vọng locator ném IllegalArgumentException vì response chứa key ngoài namespace cho phép.

Test này kiểm tra rằng xác thực HTTP không đồng nghĩa nguồn cấu hình được quyền ghi mọi property.

### 10.6. Test lỗi HTTP và fail-fast

Viết các trường hợp:

- HTTP 404 với fail-fast=true: startup phải báo lỗi.
- HTTP 404 với fail-fast=false: locator trả null.
- HTTP 401/403: luôn báo lỗi xác thực.
- HTTP 500: báo lỗi nếu fail-fast=true; trả null nếu nguồn là tùy chọn và fail-fast=false.
- Timeout hoặc connection refused với fail-fast=true: startup thất bại.
- Timeout hoặc connection refused với fail-fast=false: locator bỏ qua nguồn nếu policy cho phép.

JSON sai định dạng hoặc property key ngoài allowlist luôn làm locator báo lỗi. Không dùng fail-fast=false để che lỗi 401/403 hoặc response sai hợp đồng.

## 11. Kiểm tra tích hợp trong ứng dụng

### 11.1. Bật bootstrap source khi chạy local

Trong PowerShell:

~~~powershell
$env:CUSTOM_CONFIG_ENABLED = "true"
$env:CUSTOM_CONFIG_URI = "http://localhost:8099/v1/config"
$env:CUSTOM_CONFIG_TOKEN = "local-test-token"
~~~

Khởi động configuration API test ở port 8099 rồi chạy OrdersApplication.

Nếu API chưa chạy và fail-fast=true, ứng dụng phải dừng startup. Đây là hành vi đúng khi cấu hình là bắt buộc.

### 11.2. Kiểm tra Environment

Trong integration test hoặc debugger, đọc:

~~~java
environment.getProperty("app.payment.base-url");
environment.getProperty("app.payment.timeout");
environment.getProperty("feature.checkout.enabled");
~~~

Xác nhận giá trị đến từ custom source.

Có thể kiểm tra danh sách PropertySource:

~~~java
environment.getPropertySources().forEach(source ->
        System.out.println(source.getName())
);
~~~

Chỉ in tên source trong log chẩn đoán. Không in toàn bộ property values vì nguồn cấu hình có thể chứa thông tin nhạy cảm.

### 11.3. Kiểm tra ConfigurationProperties

Inject PaymentProperties và CheckoutFeatureProperties rồi xác nhận:

- baseUrl đúng với response.
- timeout được convert thành Duration.
- enabled được convert thành boolean.

Nếu Environment có giá trị đúng nhưng bean có giá trị khác, kiểm tra property source precedence, prefix, tên property và thời điểm binding.

### 11.4. Test bootstrap registration

Nếu locator unit test chạy nhưng ứng dụng không có custom PropertySource, kiểm tra:

1. spring-cloud-starter-bootstrap đã nằm trên classpath.
2. BootstrapConfiguration key trong spring.factories chính xác.
3. File nằm trong META-INF/spring.factories của artifact.
4. Package bootstrap không bị scan nhầm.
5. spring.cloud.bootstrap.enabled không bị tắt.
6. app.config-source.enabled đang là true.
7. bootstrap.yml được đóng gói và đọc đúng.
8. spring.application.name có giá trị trước khi locator chạy.

### 11.5. Kiểm tra nội dung JAR

Sau khi build, kiểm tra artifact có các file:

~~~text
BOOT-INF/classes/bootstrap.yml
BOOT-INF/classes/META-INF/spring.factories
BOOT-INF/classes/com/example/bootstrap/CustomBootstrapConfiguration.class
BOOT-INF/classes/com/example/bootstrap/HttpPropertySourceLocator.class
~~~

Nếu META-INF/spring.factories bị thiếu hoặc sai tên key, bootstrap configuration sẽ không được phát hiện.

## 12. Thứ tự PropertySource và chẩn đoán precedence

### 12.1. PropertySource không phải một map độc lập

Environment chứa nhiều PropertySource. Khi gọi getProperty, Spring tìm key theo thứ tự ưu tiên. Nếu nhiều source có cùng key, source có precedence cao hơn quyết định giá trị hiệu lực.

Ví dụ:

| Nguồn | app.payment.timeout |
| --- | --- |
| Command line | 900ms |
| Custom bootstrap source | 450ms |
| application.yml | 800ms |

Giá trị thực tế phụ thuộc thứ tự source trong Environment và các quy tắc override của bootstrap. Đừng suy luận precedence chỉ từ việc source được tải từ xa.

### 12.2. Không đặt cùng key ở nhiều nơi nếu không cần

Nếu custom source là nguồn sở hữu endpoint và timeout, hãy hạn chế khai báo lại các key đó trong nhiều nguồn. Cấu hình mặc định có thể dùng cho local, còn môi trường triển khai cấp giá trị thực.

Khi cần override cục bộ, hãy xác định policy rõ ràng và test cả môi trường local lẫn production.

### 12.3. Ghi nhận source name

Source name trong bài có dạng:

~~~text
custom-http:orders-service:base
custom-http:orders-service:staging
~~~

Tên này giúp nhận biết nguồn và profile khi quan sát Environment. Không đưa token hoặc dữ liệu bí mật vào source name.

### 12.4. Thứ tự giữa nhiều locator

Khi có nhiều locator, đặt @Order hoặc implement Ordered. Sau đó kiểm tra composite PropertySource để xác nhận nguồn nào thắng khi trùng key.

Nếu một locator cần cung cấp default và locator khác cung cấp override, thiết kế order có chủ đích. Không dùng cùng source name cho các nguồn có ý nghĩa khác nhau.

## 13. Bảo mật và độ tin cậy

### 13.1. Bảo vệ token

Token cần được cấp từ environment variable hoặc secret manager. Không commit token vào Git, không nhúng token vào image và không truyền token qua command line nếu có thể tránh.

HTTP request dùng HTTPS trong môi trường thật. Không tắt certificate validation để khắc phục lỗi TLS.

### 13.2. Không log secret hoặc response body

Không log:

- Authorization header.
- Bearer token.
- Password hoặc private key.
- Toàn bộ JSON response.
- Toàn bộ Environment.
- Exception message do server trả về nếu có thể chứa dữ liệu nhạy cảm.

Log nên chứa application name, profile, source name, thời gian gọi và status code. Không ghi token.

### 13.3. Giới hạn property namespace

Allowlist app.* và feature.* giới hạn tác động của custom source. Nếu muốn cho phép property khác, cần review từng nhóm và kiểm thử tác động đến bootstrap, security và bean creation.

Không cho configuration service tùy ý thay đổi spring.profiles.active, spring.main.*, management.* hoặc security properties nếu không có quy trình quản trị tương ứng.

Allowlist chỉ giới hạn phạm vi key, không tự biến API thành secret manager. Không trả password hoặc private key qua endpoint cấu hình thông thường; dùng Vault hoặc secret manager chuyên trách. Nếu hệ thống có lý do phải phân phối credential qua API này, cần áp dụng quyền riêng, TLS, audit, rotation và quy tắc che giá trị tương ứng.

### 13.4. Timeout và retry

Locator chạy trong quá trình startup. Một request không có timeout có thể làm deployment treo lâu.

Bài lab dùng:

- Connect timeout 2 giây.
- Request timeout 3 giây.
- Không có retry loop không giới hạn.

Nếu cần retry, dùng số lần thử hữu hạn, backoff và deadline tổng thể. Thời gian bootstrap phải nằm trong startup budget của nền tảng triển khai.

### 13.5. Fail-fast hay optional

Dùng fail-fast=true khi cấu hình cần thiết để ứng dụng hoạt động an toàn. Dùng optional khi nguồn thực sự bổ sung và ứng dụng có default hợp lệ.

Không biến lỗi xác thực hoặc response sai schema thành optional. Điều đó có thể khiến ứng dụng khởi động với cấu hình không đúng mà không ai nhận ra.

### 13.6. Cache và consistency

Nếu API có cache, cache key cần bao gồm application và profiles. Không dùng một response chung cho mọi service hoặc mọi môi trường.

Nếu có version cấu hình, nên trả thêm metadata revision ở response header hoặc một property riêng đã được allowlist. Có thể ghi nhận revision để phục vụ audit mà không log toàn bộ nội dung.

### 13.7. Nhiều replica

Mỗi replica có thể gọi custom API lúc startup. API cần chịu được burst khi rollout hoặc autoscaling. Cân nhắc cache ở server, rate limit hợp lý và khả năng phục vụ nhiều request đồng thời.

PropertySourceLocator không tự đồng bộ các replica sau startup. Nếu cấu hình thay đổi, phải có cơ chế triển khai hoặc broadcast phù hợp.

## 14. Khi nào nên dùng Config Data API thay cho PropertySourceLocator?

### 14.1. PropertySourceLocator thuộc bootstrap extension

PropertySourceLocator được đăng ký trong bootstrap context thông qua BootstrapConfiguration và spring.factories. Nó phù hợp khi ứng dụng đang dùng Spring Cloud bootstrap model và cần đưa nguồn cấu hình vào Environment ở giai đoạn bootstrap.

### 14.2. Config Data API là extension point của Spring Boot

Từ Spring Boot 2.4, Config Data API cung cấp hai interface quan trọng:

- ConfigDataLocationResolver: phân tích location do ứng dụng khai báo thành một hoặc nhiều resource.
- ConfigDataLoader: tải resource thành ConfigData để Spring Boot đưa vào Environment.

Ví dụ ứng dụng khai báo:

~~~yaml
spring:
  config:
    import: customconfig:https://config.internal/orders
~~~

Resolver nhận prefix customconfig:, xác định resource; loader gọi nguồn cấu hình và trả về ConfigData.

### 14.3. So sánh hai cách

| Tiêu chí | PropertySourceLocator | Config Data API |
| --- | --- | --- |
| Chủ sở hữu lifecycle | Spring Cloud bootstrap | Spring Boot Config Data |
| Cách đăng ký | BootstrapConfiguration trong spring.factories | Resolver/loader trong spring.factories |
| Cách kích hoạt | Bootstrap infrastructure | spring.config.import |
| Profile-specific loading | Locator có thể được gọi lại với active profiles theo phiên bản | Resolver có resolveProfileSpecific |
| Optional location | Tự thiết kế policy của locator | Hỗ trợ optional: trong Config Data |
| Nguồn gốc cấu hình | Cần thiết kế metadata riêng | Tích hợp với Config Data origin/resource model |
| Phù hợp | Tích hợp theo bootstrap model hiện có | Custom location cho ứng dụng Boot hiện đại |

### 14.4. Không trộn hai cơ chế tùy tiện

Không đăng ký cùng một nguồn cấu hình qua cả PropertySourceLocator và ConfigDataLoader nếu chưa có quy tắc rõ ràng. Hai nguồn có thể cùng cung cấp một key và tạo ra precedence khó hiểu.

Nếu module hiện tại đã dựa trên Spring Cloud bootstrap và đề bài yêu cầu PropertySourceLocator, hãy hoàn thành bài theo bootstrap model. Với một custom config location mới cho ứng dụng Spring Boot hiện đại, cân nhắc Config Data API trước khi chọn bootstrap.

## 15. Mở rộng bài thực hành

### 15.1. Hỗ trợ profile-specific API response

Thay đổi mock server để trả response khác nhau theo profiles. Kiểm thử lần gọi không profile và lần gọi staging. Xác nhận source name và giá trị cuối cùng đúng.

### 15.2. Hỗ trợ revision

Thêm header X-Config-Revision vào response. Locator có thể đọc header và tạo metadata property không nhạy cảm, ví dụ app.config-source.revision.

Không đưa token hoặc thông tin xác thực vào revision.

### 15.3. Hỗ trợ ETag

Configuration API có thể trả ETag. Locator có thể gửi If-None-Match nếu có cache hợp lệ trong cùng lifecycle.

Với bootstrap locator, cache phải được thiết kế cẩn thận vì locator có thể được gọi hai lần theo profile. Không dùng một ETag của base configuration cho profile-specific response.

### 15.4. Hỗ trợ nhiều tenant

Nếu một process phục vụ nhiều tenant, không nên dùng một PropertySourceLocator để nạp một tenant-specific config rồi giả định mọi request đều dùng chung. PropertySource trong Environment thường là cấu hình cấp application/context.

Cấu hình theo tenant thay đổi theo request nên được quản lý bởi tenant configuration provider riêng, có cache key và policy theo tenant.

### 15.5. Hỗ trợ nhiều nguồn

Có thể tạo nhiều locator cho:

- Platform defaults.
- Application settings.
- Feature flags.

Mỗi locator có source name riêng và thứ tự được xác định. Nếu các nguồn cùng khai báo một key, test precedence phải chứng minh kết quả đúng.

### 15.6. Đưa validation vào contract

Có thể dùng schema version hoặc response version để kiểm tra tương thích. Ví dụ API trả header X-Config-Schema-Version. Locator từ chối response không tương thích thay vì bind các key sai định dạng.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Locator không được gọi | Bootstrap starter thiếu hoặc bootstrap bị tắt | Kiểm tra dependency và bootstrap enabled |
| Không thấy custom PropertySource | spring.factories sai key hoặc sai package | Kiểm tra META-INF/spring.factories trong JAR |
| spring.application.name rỗng | Chỉ khai báo ở nguồn được nạp sau bootstrap | Đặt trong bootstrap.yml hoặc environment sớm |
| API nhận sai profile | Locator dùng profile mặc định hoặc static cache | Đọc active profiles từ Environment mỗi lần locate |
| API bị gọi hai lần | Spring Cloud từ 2022.0.3 gọi theo hai giai đoạn profile | Thiết kế locator idempotent và source name theo profile |
| Bean không nhận giá trị remote | PropertySource precedence hoặc prefix sai | Kiểm tra Environment và ConfigurationProperties |
| Giá trị local luôn thắng | Custom source có precedence thấp hơn source khác | Kiểm tra thứ tự locator và PropertySource |
| 401/403 | Token thiếu, hết hạn hoặc policy sai | Cấp token đúng và kiểm tra quyền |
| Startup treo khi API lỗi | HTTP request không có timeout | Đặt connect/request timeout hữu hạn |
| JSON parse lỗi | API trả HTML, array hoặc schema không đúng | Kiểm tra Content-Type và contract |
| Property không được bind | Key không khớp prefix hoặc type conversion lỗi | Kiểm tra tên key và kiểu dữ liệu |
| Một source làm thay đổi property hệ thống | Không có allowlist | Giới hạn namespace và từ chối key nhạy cảm |
| Test phụ thuộc server thật | Test không cô lập HTTP | Dùng HttpServer cục bộ với port động |
| Locator bị tạo hai lần trong main context | Bootstrap package bị component scan | Đưa bootstrap package ra ngoài application scan |
| Replica dùng config khác nhau | Source thay đổi giữa các lần startup | Dùng revision bất biến và audit config revision |
| Thay đổi sau startup không được cập nhật | Locator chỉ tải cấu hình lúc bootstrap | Thiết kế refresh/broadcast hoặc restart riêng |

## 17. Checklist hoàn thành lab

### Bootstrap integration

- [ ] Có dependency spring-cloud-starter-bootstrap.
- [ ] BootstrapConfiguration được đăng ký trong spring.factories.
- [ ] Bootstrap package nằm ngoài component scan của ứng dụng.
- [ ] spring.application.name có sẵn trước khi locator chạy.
- [ ] Locator trả null khi source disabled.
- [ ] Locator đọc Environment trong từng lần gọi.

### HTTP source

- [ ] Request chứa application và profiles.
- [ ] Query parameter được URL encode.
- [ ] Bearer token lấy từ secret/environment.
- [ ] Connect timeout và request timeout hữu hạn.
- [ ] JSON được parse thành map key-value.
- [ ] Property key được kiểm tra theo allowlist.
- [ ] Response body và token không bị log.
- [ ] Fail-fast policy được kiểm thử.

### Profile và precedence

- [ ] Test lần gọi không profile.
- [ ] Test lần gọi có profile.
- [ ] Locator không dùng static cache.
- [ ] PropertySource name phân biệt application/profile.
- [ ] Thứ tự giữa các locator được xác định.
- [ ] Giá trị cuối cùng được kiểm tra trong Environment.

### Kiểm thử và vận hành

- [ ] Unit test dùng HTTP server cục bộ.
- [ ] Test nguồn disabled.
- [ ] Test success và bearer token.
- [ ] Test key ngoài allowlist.
- [ ] Test 404, 401/403 và 5xx.
- [ ] Test timeout và fail-fast.
- [ ] Integration test xác nhận ConfigurationProperties binding.
- [ ] Artifact chứa bootstrap.yml và spring.factories.
- [ ] Production dùng HTTPS và secret manager.
- [ ] Có kế hoạch cập nhật cấu hình sau startup.

## 18. Bài tập vận dụng

**Bài tập 1 — PropertySource đơn giản.** Viết locator trả về MapPropertySource có một property cố định. Xác nhận Environment đọc được key.

**Bài tập 2 — Application-aware source.** Đọc spring.application.name và trả cấu hình khác nhau cho orders-service và inventory-service.

**Bài tập 3 — Profile-aware source.** Đọc active profiles và trả timeout khác nhau cho local, staging và production.

**Bài tập 4 — HTTP source.** Triển khai HttpPropertySourceLocator gọi mock HTTP API, parse JSON và tạo MapPropertySource.

**Bài tập 5 — Authentication.** Gửi bearer token từ environment variable. Test token thiếu, token đúng và token sai.

**Bài tập 6 — Fail-fast.** Mô phỏng 404, 401 và 503. Xác định trường hợp nào được bỏ qua và trường hợp nào phải dừng startup.

**Bài tập 7 — Property allowlist.** Cho API trả key spring.datasource.password. Xác nhận locator từ chối key này.

**Bài tập 8 — Hai lần locate.** Gọi locator khi không có profile rồi gọi lại với staging. Xác nhận hai request nhận đúng query.

**Bài tập 9 — Precedence.** Đặt app.payment.timeout ở application.yml và custom source. Quan sát giá trị hiệu lực và giải thích thứ tự PropertySource.

**Bài tập 10 — Config Data API.** Tạo một thử nghiệm riêng với ConfigDataLocationResolver và ConfigDataLoader cho prefix customconfig:. So sánh cách kích hoạt và profile handling với PropertySourceLocator.

**Bài tập 11 — Nhiều locator.** Tạo hai locator cho platform defaults và application settings. Dùng @Order và kiểm tra source nào thắng khi cùng khai báo một key.

**Bài tập 12 — Revision và rollout.** Thêm config revision vào response. Ghi nhận revision trong startup log, triển khai hai replica và xác nhận cả hai dùng cùng revision.

## 19. Ghi nhớ và nguồn tra cứu

- PropertySourceLocator là extension point của Spring Cloud bootstrap để tìm nguồn property cho Environment.
- Locator nhận Environment của ApplicationContext sắp được tạo và có thể đọc application name, profile cùng các property đã có.
- Đăng ký locator thông qua BootstrapConfiguration trong META-INF/spring.factories.
- Đặt bootstrap package ngoài component scan của ứng dụng chính.
- Từ Spring Cloud 2022.0.3, PropertySourceLocators được gọi hai lần: trước khi có active profiles và sau khi profile được xác định.
- Locator cần idempotent, không dùng static cache và tạo source name phân biệt application/profile.
- MapPropertySource phù hợp để đưa map key-value vào Environment.
- Nguồn cấu hình bên ngoài cần timeout, xác thực, allowlist, error policy và fail-fast rõ ràng.
- Không log bearer token, response body nhạy cảm hoặc toàn bộ Environment.
- PropertySourceLocator nạp cấu hình trong bootstrap; nó không tự polling hoặc đồng bộ các replica sau startup.
- Với custom config location mới trong Spring Boot, cân nhắc ConfigDataLocationResolver và ConfigDataLoader được kích hoạt qua spring.config.import.
- Kiểm tra đúng Spring Boot/Spring Cloud release train và tài liệu của phiên bản đang dùng.

Nguồn chính thức:

1. [Spring Cloud Commons 5.0.4 – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
2. [Spring Cloud Commons – PropertySourceLocator API](https://docs.spring.io/spring-cloud-commons/reference/)
3. [Spring Cloud Commons – BootstrapConfiguration và PropertySourceLocator source](https://github.com/spring-cloud/spring-cloud-commons/tree/main/spring-cloud-context)
4. [Spring Boot 4.1 – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
5. [Spring Boot – ConfigDataLocationResolver API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataLocationResolver.html)
6. [Spring Boot – ConfigDataLoader API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/config/ConfigDataLoader.html)
7. [Spring Cloud – Release train và tương thích Spring Boot](https://spring.io/projects/spring-cloud/)
