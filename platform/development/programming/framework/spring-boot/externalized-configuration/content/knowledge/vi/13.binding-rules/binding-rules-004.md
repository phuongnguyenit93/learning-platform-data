# Khác biệt giữa tra cứu trực tiếp Environment và liên kết đối tượng

## 1. Hai cách đọc cấu hình, một hệ thống nguồn dữ liệu

Spring Boot có thể lấy cấu hình từ nhiều nguồn: **application.properties**, **application.yml**, file ngoài JAR, biến môi trường, Java system properties, command-line arguments và các PropertySource do ứng dụng thêm vào. Các nguồn này có **thứ tự ưu tiên**, vì vậy cùng một key có thể nhận giá trị khác tùy nơi ứng dụng chạy.

Khi cần đưa dữ liệu ấy vào Java, hai cách phổ biến là:

- **Tra cứu trực tiếp qua Environment**: hỏi giá trị một key cụ thể, ví dụ **environment.getProperty("client.payment.base-url")**.
- **Liên kết đối tượng qua @ConfigurationProperties**: mô tả một nhóm cấu hình theo prefix như **client.payment**, rồi để Spring Boot **Binder** tạo một đối tượng Java có các field, nested object, List hoặc Map.

Hai cách không đại diện cho hai kho dữ liệu độc lập. Chúng cùng sử dụng những property được nạp từ hệ thống cấu hình của Spring Boot, nhưng khác nhau về **API**, **mức độ cấu trúc**, **chuyển kiểu**, **validation** và **vòng đời sử dụng**.

Ví dụ: nếu chỉ muốn xem cờ **maintenance.enabled**, một lời gọi Environment có thể đủ. Nếu payment client cần URL, timeout, retry policy và danh sách endpoint, **@ConfigurationProperties** thường diễn đạt hợp đồng cấu hình tốt hơn.

Bài học tập trung vào Spring Boot 3.3.x và Java 21.

## 2. Environment là gì?

**org.springframework.core.env.Environment** là API của Spring Framework để xem **property** và **profile** đang có hiệu lực.

Một số phương thức quan trọng:

~~~java
String name = environment.getProperty("spring.application.name");

String greeting = environment.getProperty(
        "app.greeting", "Xin chào");

Integer port = environment.getProperty(
        "server.port", Integer.class);

boolean present = environment.containsProperty(
        "app.greeting");

String required = environment.getRequiredProperty(
        "app.greeting");

String[] activeProfiles = environment.getActiveProfiles();
~~~

Ý nghĩa:

- **getProperty(key)**: đọc một key dưới dạng String; trả về **null** nếu không có.
- **getProperty(key, defaultValue)**: đưa ra fallback khi không tìm thấy key.
- **getProperty(key, Class<T>)**: yêu cầu chuyển sang kiểu đích khi ConversionService hỗ trợ.
- **containsProperty(key)**: kiểm tra nguồn cấu hình có thể giải quyết key đó hay không.
- **getRequiredProperty(key)**: ném **IllegalStateException** nếu không tìm thấy property bắt buộc.
- **getActiveProfiles()**: trả về danh sách tên profile đang hoạt động.

Điều này cho thấy Environment **không chỉ hỗ trợ String**. Tuy nhiên, từng lời gọi chủ yếu giải quyết **một key**, không tự tạo một object graph từ nhiều key.

### 2.1. ConfigurableEnvironment và PropertySource

**ConfigurableEnvironment** mở rộng Environment để làm việc với tập **PropertySource**.

~~~java
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

public void showSources(ConfigurableEnvironment environment) {
    for (PropertySource<?> source : environment.getPropertySources()) {
        System.out.println(source.getName());
    }
}
~~~

PropertySource biểu diễn một nguồn giá trị. Spring Boot kết hợp các PropertySource với thứ tự ưu tiên phù hợp, nên lời gọi **getProperty** sẽ nhận giá trị đã được giải quyết từ môi trường hiện tại.

Ví dụ file YAML:

~~~yaml
client:
  payment:
    base-url: "https://sandbox.example.invalid"
    connect-timeout: 3s
~~~

Nếu triển khai cấp biến môi trường:

~~~text
CLIENT_PAYMENT_BASEURL=https://production.example.invalid
~~~

thì **environment.getProperty("client.payment.base-url")** có thể nhận URL production, vì biến môi trường thường ưu tiên cao hơn Config Data trong file.

Dữ liệu vẫn nằm trong cùng hệ thống property sources; các component chỉ khác cách đọc.

## 3. Tra cứu trực tiếp một key với Environment

Giả sử ứng dụng có:

~~~yaml
app:
  greeting: "Xin chào"
~~~

Một service nhỏ có thể truy vấn property khi cần:

~~~java
package com.example.config;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final Environment environment;

    public GreetingService(Environment environment) {
        this.environment = environment;
    }

    public String greet() {
        return environment.getProperty(
                "app.greeting", "Chào bạn");
    }
}
~~~

Ưu điểm:

1. Dễ đọc, ít cấu trúc ban đầu.
2. Không cần tạo riêng một class cấu hình cho một giá trị lẻ.
3. Có thể chọn key trong code tại thời điểm thực thi.
4. Hữu ích khi viết công cụ chẩn đoán hoặc infrastructure code.
5. Có overload chuyển đổi sang kiểu đích.

Nhược điểm xuất hiện khi một component cần nhiều field liên quan:

~~~java
String url = environment.getProperty(
        "client.payment.base-url");

String timeout = environment.getProperty(
        "client.payment.connect-timeout");

String retries = environment.getProperty(
        "client.payment.retry.max-attempts");

String initialDelay = environment.getProperty(
        "client.payment.retry.initial-delay");
~~~

Cách này khiến logic nghiệp vụ mang theo nhiều chuỗi key, nhiều bước chuyển kiểu, nhiều nhánh xử lý giá trị thiếu. Khi các field phát triển thành nested object, list hoặc map, việc tự tổ chức sẽ phức tạp dần.

**Environment phù hợp với truy vấn; nó không phải một lớp model cấu hình có cấu trúc.**

## 4. @ConfigurationProperties và Binder

Spring Boot cung cấp **@ConfigurationProperties** để mô tả cả một nhánh property bằng một Java class hoặc record.

Ví dụ:

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client.payment")
public record PaymentProperties(
        URI baseUrl,
        Duration connectTimeout,
        Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration initialDelay) {
    }
}
~~~

Các key mà record biểu diễn:

~~~text
client.payment.base-url
client.payment.connect-timeout
client.payment.retry.max-attempts
client.payment.retry.initial-delay
~~~

File YAML:

~~~yaml
client:
  payment:
    base-url: "https://sandbox.example.invalid"
    connect-timeout: 3s
    retry:
      max-attempts: 4
      initial-delay: 200ms
~~~

Spring Boot Binder có thể tạo **PaymentProperties** với các giá trị:

~~~java
paymentProperties.baseUrl();                 // URI
paymentProperties.connectTimeout();          // Duration
paymentProperties.retry().maxAttempts();     // int
paymentProperties.retry().initialDelay();    // Duration
~~~

Đặc điểm:

- **prefix** xác định nhóm tên property cần bind.
- **baseUrl** trong Java tương ứng **base-url** ở cấu hình.
- **retry** trở thành nested object.
- Giá trị **3s**, **200ms** có thể được chuyển thành Duration.
- Class nghiệp vụ chỉ nhận một **PaymentProperties** thay vì tự biết mọi key.

Đây là **liên kết đối tượng**, không chỉ là tra cứu chuỗi.

## 5. Đăng ký class cấu hình

Với record immutable trong Spring Boot 3.3, constructor binding hoạt động khi type được đăng ký bằng cơ chế configuration properties phù hợp.

### 5.1. @ConfigurationPropertiesScan

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
~~~

Nếu **PaymentProperties** nằm dưới package **com.example.config**, việc quét từ **com.example** có thể tìm thấy type này.

### 5.2. @EnableConfigurationProperties

Cách thay thế:

~~~java
package com.example;

import com.example.config.PaymentProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(PaymentProperties.class)
public class ExampleApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExampleApplication.class, args);
    }
}
~~~

Đây là hai **lựa chọn thay thế**, không cần dùng đồng thời trong ví dụ.

Đối với record dùng constructor binding, không chỉ gắn **@Component** rồi mong Spring tự nhận các tham số constructor như property. Constructor binding của Spring Boot yêu cầu đăng ký type theo hạ tầng configuration properties phù hợp.

Với JavaBean mutable và setter, Spring Boot còn hỗ trợ setter-based binding; bài này dùng record để thể hiện rõ cấu hình immutable.

## 6. Ví dụ hoàn chỉnh: đọc cùng cấu hình bằng hai cách

Giả sử project có dependency **spring-boot-starter-web**, **spring-boot-starter-test**, Spring Boot 3.3.x và Java 21.

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

client:
  payment:
    base-url: "https://sandbox.example.invalid"
    connect-timeout: 3s
    retry:
      max-attempts: 4
      initial-delay: 200ms
~~~

Đăng ký **PaymentProperties** như mục trước.

Một REST controller minh họa:

~~~java
package com.example.config;

import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ConfigComparisonController {

    private final Environment environment;
    private final PaymentProperties payment;

    public ConfigComparisonController(
            Environment environment,
            PaymentProperties payment) {
        this.environment = environment;
        this.payment = payment;
    }

    @GetMapping("/config-comparison")
    public Map<String, Object> compare() {
        Map<String, Object> result = new LinkedHashMap<>();

        result.put("directBaseUrl",
                environment.getProperty(
                        "client.payment.base-url"));
        result.put("boundBaseUrl",
                payment.baseUrl().toString());

        result.put("directTimeout",
                environment.getProperty(
                        "client.payment.connect-timeout"));
        result.put("boundTimeoutMs",
                payment.connectTimeout().toMillis());

        result.put("directRetryCount",
                environment.getProperty(
                        "client.payment.retry.max-attempts"));
        result.put("boundRetryCount",
                payment.retry().maxAttempts());

        return result;
    }
}
~~~

Sau khi chạy ứng dụng và gọi:

~~~bash
curl http://localhost:8080/config-comparison
~~~

Kết quả minh họa:

~~~json
{
  "directBaseUrl": "https://sandbox.example.invalid",
  "boundBaseUrl": "https://sandbox.example.invalid",
  "directTimeout": "3s",
  "boundTimeoutMs": 3000,
  "directRetryCount": "4",
  "boundRetryCount": 4
}
~~~

Nhận xét:

- **Environment** trả từng giá trị theo key.
- **PaymentProperties** biểu diễn cả nhóm bằng object có kiểu.
- Trong ví dụ, **getProperty** không chỉ ra mối liên hệ giữa base URL, timeout và retry.
- Với object đã bind, service có thể gọi **payment.retry().maxAttempts()** mà không biết property key thực tế.

**Không triển khai endpoint hiển thị cấu hình nội bộ như một API công khai trong production.** Ví dụ chỉ dùng dữ liệu giả để minh họa.

## 7. Bảng so sánh

| Tiêu chí | Environment.getProperty | @ConfigurationProperties |
| --- | --- | --- |
| Cách sử dụng | Tra cứu một key theo tên | Bind một prefix thành object |
| API | **getProperty**, **getRequiredProperty** | Bean/record, getters hoặc record accessors |
| Nguồn dữ liệu | Environment và các PropertySource | Cũng dùng các nguồn cấu hình của Spring Boot |
| Kiểu trả về | String hoặc kiểu đích theo ConversionService | Model Java có các field được bind |
| Nested properties | Phải đọc các key thành phần | Hỗ trợ nested object |
| List, Map | Không tự động dựng object graph bằng một getProperty | Hỗ trợ binding collection |
| Relaxed binding | Phụ thuộc cách Environment/PropertySource giải quyết tên | Là tính năng rõ ràng của Binder |
| Validation | Kiểm tra thủ công hoặc cơ chế riêng | Có thể tích hợp Bean Validation |
| Metadata | Không tự sinh metadata từ các string key | Có thể sinh metadata cho configuration properties |
| Mặc định | Truyền default vào mỗi lần gọi | Khai báo trong Config Data hoặc model |
| Vòng đời | Gọi trực tiếp tại thời điểm tùy ý | Bean thường bind khi ApplicationContext được tạo |
| Phù hợp nhất | Key đơn, key chọn động, chẩn đoán | Cấu hình của subsystem có cấu trúc |

**Không đúng nếu phát biểu rằng Environment không hỗ trợ chuyển kiểu.** Nó có overload nhận **Class<T>**. Sự khác biệt quan trọng là Binder giải quyết **cấu trúc và hợp đồng cấu hình toàn nhóm**.

## 8. Relaxed binding và cách đặt tên property

Với **@ConfigurationProperties**, Spring Boot cung cấp các quy tắc relaxed binding. Ví dụ field Java:

~~~java
Duration connectTimeout;
~~~

dưới prefix **client.payment** có tên canonical:

~~~text
client.payment.connect-timeout
~~~

Một số dạng trong file properties/YAML có thể cùng bind vào field:

~~~text
client.payment.connect-timeout
client.payment.connectTimeout
client.payment.connect_timeout
~~~

Tên biến môi trường được suy ra từ canonical:

~~~text
CLIENT_PAYMENT_CONNECTTIMEOUT
~~~

Quy tắc từ canonical sang environment variable:

1. Dấu chấm **.** đổi thành dấu gạch dưới **_**.
2. Dấu gạch ngang **-** bị **loại bỏ**.
3. Chữ cái được viết hoa.

Do đó, không nên tự suy rằng **CLIENT_PAYMENT_CONNECT_TIMEOUT** là dạng chuẩn chỉ vì tên Java là **connectTimeout**.

### 8.1. Tra cứu Environment có relaxed binding giống hệt Binder không?

**Environment.getProperty(key)** tra cứu một key cụ thể; một số PropertySource hoặc hạ tầng Spring Boot có hỗ trợ tìm những dạng tên tương ứng. Đặc biệt, nguồn biến môi trường có quy tắc tra cứu thuận tiện cho những tên không chứa dấu chấm.

Tuy nhiên, không nên mặc nhiên coi **getProperty** là một lời gọi **Binder** và giả định mọi biến thể tên, list index hay map key đều được xử lý hoàn toàn giống khi bind cấu trúc.

Cách an toàn:

- Viết key trong Config Data theo **lowercase kebab-case**.
- Gọi **Environment.getProperty** bằng tên canonical.
- Dùng **@ConfigurationProperties** nếu thực sự cần relaxed binding và binding cấu trúc đầy đủ.
- Kiểm tra property thực tế trong nguồn tương ứng khi thấy khác biệt.

Đây là khác biệt về **mục đích API**, không phải phán đoán rằng Environment luôn so khớp chuỗi tuyệt đối.

## 9. @Value là cơ chế thứ ba, không phải Binder

Spring cũng có **@Value**:

~~~java
package com.example.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class PaymentClientName {

    private final String baseUrl;

    public PaymentClientName(
            @Value("${client.payment.base-url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

So sánh nhanh:

- **Environment**: code chủ động hỏi một giá trị.
- **@Value**: Spring container tiêm một expression/property vào bean.
- **@ConfigurationProperties**: Binder tổ chức nhiều property thành object có kiểu.

**@Value** có hỗ trợ SpEL, còn **@ConfigurationProperties** không xử lý SpEL như một cơ chế liên kết field. Spring Boot khuyến nghị viết property placeholder trong **@Value** dưới dạng canonical kebab-case để tận dụng logic tìm key thích hợp.

Với nhiều field có quan hệ, hãy cân nhắc **@ConfigurationProperties** thay vì hàng loạt **@Value**.

## 10. Nested object: một nhánh cấu hình thay vì nhiều lời gọi

Giả sử YAML:

~~~yaml
client:
  payment:
    retry:
      max-attempts: 4
      initial-delay: 200ms
      max-delay: 2s
~~~

Tra cứu trực tiếp:

~~~java
Integer maxAttempts = environment.getProperty(
        "client.payment.retry.max-attempts",
        Integer.class);

String delay = environment.getProperty(
        "client.payment.retry.initial-delay");

String maxDelay = environment.getProperty(
        "client.payment.retry.max-delay");
~~~

Ba lời gọi là ba thao tác riêng. Nếu cần chuyển delay thành Duration, code phải chọn cách chuyển phù hợp hoặc dùng typed lookup.

Cách bind object:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client.payment")
public record RetryProperties(Retry retry) {

    public record Retry(
            int maxAttempts,
            Duration initialDelay,
            Duration maxDelay) {
    }
}
~~~

Bean đại diện cho cả một retry policy. Những nơi sử dụng có thể nhận đúng type và dễ kiểm thử hơn.

**Lưu ý:** đây là một model độc lập để minh họa. Nếu dự án đã có **PaymentProperties** chứa **Retry**, không cần đăng ký thêm **RetryProperties** cùng prefix chỉ để chạy cùng một bài tập.

## 11. List: getProperty theo chỉ số khác bind cả danh sách

**application.yml**:

~~~yaml
client:
  payment:
    endpoints:
      - name: primary
        url: "https://primary.example.invalid"
      - name: backup
        url: "https://backup.example.invalid"
~~~

Các đường property sau khi làm phẳng:

~~~text
client.payment.endpoints[0].name
client.payment.endpoints[0].url
client.payment.endpoints[1].name
client.payment.endpoints[1].url
~~~

Environment có thể tra cứu những key đơn lẻ:

~~~java
String firstName = environment.getProperty(
        "client.payment.endpoints[0].name");

String secondUrl = environment.getProperty(
        "client.payment.endpoints[1].url");
~~~

Nhưng lời gọi:

~~~java
environment.getProperty("client.payment.endpoints");
~~~

không có nghĩa là Spring tự tạo **List<Endpoint>** bằng cách tổng hợp tất cả field có chỉ số. Tùy nguồn dữ liệu, key tổng có thể có giá trị scalar hoặc không; đây không phải API dựng object graph.

Dùng configuration properties:

~~~java
package com.example.config;

import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client.payment")
public record EndpointProperties(List<Endpoint> endpoints) {

    public record Endpoint(String name, URI url) {
    }
}
~~~

Sau khi bind:

~~~java
List<EndpointProperties.Endpoint> items =
        endpointProperties.endpoints();

String primaryName = items.get(0).name();
URI backupUrl = items.get(1).url();
~~~

Điểm mạnh: không cần hard-code số lượng endpoint, và kiểu dữ liệu của cả danh sách được định nghĩa rõ.

### 11.1. List trong biến môi trường

Các key:

~~~text
client.payment.endpoints[0].name
client.payment.endpoints[1].url
~~~

chuyển sang:

~~~text
CLIENT_PAYMENT_ENDPOINTS_0_NAME
CLIENT_PAYMENT_ENDPOINTS_1_URL
~~~

Đây là quy tắc của Binder khi dùng biến môi trường: chỉ số phần tử List được phân cách bằng dấu gạch dưới.

### 11.2. Quy tắc thay thế danh sách

Khi cùng một **List** được cấu hình ở nhiều nguồn, Spring Boot dùng danh sách của nguồn ưu tiên cao hơn thay cho danh sách của nguồn thấp hơn; nó **không merge từng phần tử** để giữ phần tử chưa được override.

Ví dụ YAML có hai endpoints, nhưng nguồn môi trường ưu tiên cao hơn chỉ cung cấp một endpoint ở chỉ số 0: kết quả binding có thể chỉ còn endpoint đó. Đừng dùng việc một vài lời gọi getProperty tìm được key từ nguồn cũ để suy ra kết quả của toàn List.

## 12. Map và key theo tên

Khi cấu hình cần ánh xạ từ khóa sang giá trị, **Map** có thể phù hợp hơn List.

~~~yaml
client:
  feature-flags:
    search-v2: true
    checkout-v2: false
~~~

Type:

~~~java
package com.example.config;

import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "client")
public record FeatureFlagProperties(
        Map<String, Boolean> featureFlags) {
}
~~~

Sử dụng:

~~~java
boolean enabled = featureFlagProperties.featureFlags()
        .getOrDefault("search-v2", false);
~~~

Tra cứu trực tiếp một cờ qua Environment cũng được:

~~~java
Boolean enabled = environment.getProperty(
        "client.feature-flags.search-v2",
        Boolean.class,
        false);
~~~

Cả hai cách hợp lệ. **Map** thuận tiện hơn nếu ứng dụng cần toàn bộ tập các cờ không cố định khi viết code.

Lưu ý rằng **Map và List có quy tắc merge khác nhau** giữa các nguồn cấu hình. Map có thể kết hợp những khóa từ nhiều nguồn; List thường bị thay thế theo nguồn ưu tiên. Khi map key chứa dấu **.** hoặc ký tự đặc biệt, hãy xem quy tắc bracket notation của Spring Boot.

## 13. Chuyển kiểu trong Environment và Binder

Environment hỗ trợ typed lookup, ví dụ:

~~~java
Integer port = environment.getProperty(
        "server.port",
        Integer.class);

Boolean enabled = environment.getProperty(
        "client.feature-flags.search-v2",
        Boolean.class,
        false);
~~~

Các phép chuyển kiểu phụ thuộc ConversionService của Environment.

Binder của Spring Boot cung cấp hạ tầng chuyển đổi thích hợp cho cấu hình, gồm những kiểu thường gặp:

- **Duration**, ví dụ **3s**, **250ms**.
- **DataSize**, ví dụ **10MB**.
- **URI** hoặc những kiểu khác có converter phù hợp.
- Enum, boolean, số nguyên.
- Nested object, List và Map.

Ví dụ:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;

@ConfigurationProperties(prefix = "client.upload")
public record UploadProperties(
        Duration requestTimeout,
        DataSize maxPayloadSize) {
}
~~~

YAML:

~~~yaml
client:
  upload:
    request-timeout: 5s
    max-payload-size: 10MB
~~~

Code sử dụng:

~~~java
Duration timeout = uploadProperties.requestTimeout();
DataSize limit = uploadProperties.maxPayloadSize();
~~~

Một object có kiểu giúp các service sử dụng cấu hình mà không cần lặp chuyển đổi String ở nhiều nơi.

**Phân biệt lỗi:** nếu giá trị **max-payload-size=not-a-size** không thể chuyển sang DataSize, đây là vấn đề **binding/conversion**, không phải lỗi về ưu tiên nguồn.

## 14. Validation: từ dữ liệu được bind đến cấu hình hợp lệ

Khi dùng Environment trực tiếp, code thường phải kiểm tra thủ công:

~~~java
String url = environment.getProperty(
        "client.payment.base-url");

if (url == null || url.isBlank()) {
    throw new IllegalStateException(
            "Payment base URL is required");
}
~~~

Với **@ConfigurationProperties**, Spring Boot hỗ trợ Bean Validation khi có dependency phù hợp.

Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Một model có validation:

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "client.payment")
public record ValidatedPaymentProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Valid @NotNull Retry retry) {

    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration initialDelay) {
    }
}
~~~

Đây là **một phiên bản thay thế** cho PaymentProperties, không cần đăng ký đồng thời hai model cùng prefix.

Nếu thiếu **base-url** hoặc đặt **retry.max-attempts=0**, validation có thể khiến ứng dụng báo lỗi khi khởi tạo context. Dùng **@Valid** để đi sâu kiểm tra nested object.

Khác biệt quan trọng:

- **Conversion**: chuỗi **abc** có chuyển được sang số/duration không?
- **Validation**: số **0** chuyển thành int được nhưng có thỏa **@Min(1)** không?

Để tránh lỗi chỉ xuất hiện lúc xử lý request, cấu hình của subsystem quan trọng nên được kiểm tra sớm.

## 15. Giá trị mặc định: nơi gọi hay trong hợp đồng?

### 15.1. Environment: fallback tại mỗi lời gọi

~~~java
int attempts = environment.getProperty(
        "client.payment.retry.max-attempts",
        Integer.class,
        3);
~~~

Giá trị mặc định **3** nằm ngay tại vị trí gọi. Nếu hai service khác nhau tự chọn default 3 và 5, ứng dụng có thể có hành vi không nhất quán.

### 15.2. @ConfigurationProperties: default trong file hoặc model

Có thể đặt default trong **application.yml** hoặc dùng cơ chế binding hỗ trợ **@DefaultValue**:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "client.payment")
public record PaymentDefaultProperties(
        @DefaultValue("3s") Duration connectTimeout,
        @DefaultValue("4") int maxAttempts) {
}
~~~

Đây cũng là model minh họa độc lập.

Ưu điểm: default trở thành phần của cấu hình có kiểu, thay vì bị lặp ở nhiều nơi. Tuy nhiên, không nên đặt default giả cho những giá trị **bắt buộc** như credential hoặc URL quan trọng. Với chúng, validation/fail-fast thường phù hợp hơn.

## 16. Placeholder resolution và hai cách sử dụng

File **application.yml** có thể chứa placeholder:

~~~yaml
client:
  payment:
    base-url: "${payment.gateway-url:https://sandbox.example.invalid}"
~~~

Khi Spring Boot đọc property **client.payment.base-url**, biểu thức có thể tham chiếu **payment.gateway-url** từ Environment và sử dụng fallback nếu cần.

Cả Environment.getProperty và Binder đều sử dụng dữ liệu được giải quyết qua infrastructure cấu hình; placeholder resolution không làm hai cách đọc trở thành hai hệ thống độc lập.

Ví dụ nếu truyền:

~~~bash
java -jar app.jar \
  --payment.gateway-url=https://uat.example.invalid
~~~

thì giá trị **client.payment.base-url** có thể được giải quyết thành **https://uat.example.invalid** cho đối tượng cấu hình.

Đối với placeholder trong **@Value**, Spring Boot khuyến nghị dùng tên **canonical kebab-case** để tận dụng logic tra cứu tên phù hợp.

## 17. Vòng đời đọc: lời gọi trực tiếp và bean được bind

Một khác biệt dễ bị hiểu sai là **thời điểm đọc**.

- Với Environment, code có thể gọi **getProperty** nhiều lần ở những thời điểm khác nhau.
- Với **@ConfigurationProperties**, bean thường được tạo và bind khi ApplicationContext khởi tạo.
- Một bean singleton nhận configuration object qua constructor thường giữ object đã bind.
- Biến môi trường của process Java không tự đổi chỉ vì người dùng sửa biến ở terminal khác.
- Việc sửa file YAML trên đĩa cũng không tự bảo đảm Environment đã nạp lại file.

Vì vậy, nói “Environment luôn cập nhật realtime còn @ConfigurationProperties là giá trị cố định” là quá đơn giản.

Nếu một PropertySource **thật sự được cập nhật trong Environment**, lần tra cứu sau có thể thấy giá trị mới. Nếu không có cơ chế cập nhật nguồn, cả hai cách đều có thể tiếp tục dùng cấu hình cũ.

Một hệ thống cần dynamic refresh phải thiết kế và triển khai cơ chế refresh riêng, đồng thời xử lý tính nhất quán giữa các bean. Với triển khai thông thường, đổi biến môi trường thường đi cùng **restart hoặc rolling deployment**.

### 17.1. Thời điểm phát hiện lỗi

Nếu một record dùng **Duration connectTimeout** và YAML chứa:

~~~properties
client.payment.connect-timeout=not-a-duration
~~~

Binder có thể báo lỗi khi bean được khởi tạo.

Trong khi đó, nếu code chỉ gọi **environment.getProperty("client.payment.connect-timeout", Duration.class)** rất muộn, lỗi chuyển đổi tương ứng có thể chỉ xuất hiện khi đường code đó chạy.

Thời điểm cụ thể còn phụ thuộc lifecycle, lazy initialization và cách property được truy cập. Điểm quan trọng là object binding thường tạo ra **hợp đồng cấu hình rõ ràng và dễ xác thực sớm**.

## 18. Binder thủ công: cầu nối giữa hai cách

Spring Boot còn cung cấp **Binder** để bind một cấu trúc khi code chủ động yêu cầu, thay vì luôn đăng ký một @ConfigurationProperties bean.

~~~java
package com.example.config;

import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.core.env.Environment;

public final class ManualBindingExample {

    public PaymentProperties readPayment(Environment environment) {
        return Binder.get(environment)
                .bind("client.payment",
                      Bindable.of(PaymentProperties.class))
                .orElseThrow(() ->
                        new IllegalStateException(
                                "client.payment configuration is missing"));
    }
}
~~~

Ý nghĩa:

1. **Binder.get(environment)** tạo Binder dựa trên Environment.
2. **bind(prefix, Bindable.of(Type.class))** yêu cầu bind cả nhóm.
3. Nếu không bind được giá trị mong đợi, code chủ động xử lý trường hợp thiếu.

Cách này phù hợp trong công cụ hạ tầng hoặc khi prefix/type được lựa chọn động. Với cấu hình ổn định của một application component, **@ConfigurationProperties** vẫn là cách chuẩn hơn vì tích hợp thuận tiện với dependency injection, lifecycle, metadata và validation.

Không dùng Binder thủ công chỉ để tránh việc khai báo một class cấu hình có ý nghĩa.

## 19. Configuration metadata và IDE completion

Một lớp **@ConfigurationProperties** có thể được xử lý bởi **spring-boot-configuration-processor** để tạo metadata. IDE có thể sử dụng metadata để gợi ý tên property và kiểu dữ liệu khi viết YAML/properties.

Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Metadata thường nằm trong **META-INF/spring-configuration-metadata.json** của output.

Ví dụ nhóm tên:

~~~text
client.payment.base-url
client.payment.connect-timeout
client.payment.retry.max-attempts
client.payment.retry.initial-delay
~~~

Với Environment, những chuỗi key viết trong code không tự tạo ra metadata tương đương. Đây là lợi ích đáng kể của việc mô tả cấu hình thành type khi phát triển thư viện hoặc starter.

**Metadata hỗ trợ công cụ phát triển**; nó không thay thế việc đăng ký bean hoặc quá trình runtime binding.

## 20. Kiểm thử sự tương đồng và khác biệt

Giả sử ứng dụng đã đăng ký PaymentProperties và có **spring-boot-starter-test**.

~~~java
package com.example.config;

import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = {
    "client.payment.base-url=https://test.example.invalid",
    "client.payment.connect-timeout=2s",
    "client.payment.retry.max-attempts=2",
    "client.payment.retry.initial-delay=100ms"
})
class EnvironmentVsBindingTest {

    @Autowired Environment environment;
    @Autowired PaymentProperties payment;

    @Test
    void readsTheSameConfigurationThroughTwoApis() {
        assertEquals(
                "https://test.example.invalid",
                environment.getProperty("client.payment.base-url"));

        assertEquals(
                URI.create("https://test.example.invalid"),
                payment.baseUrl());

        assertEquals(
                "2s",
                environment.getProperty(
                    "client.payment.connect-timeout"));

        assertEquals(
                Duration.ofSeconds(2),
                payment.connectTimeout());

        assertEquals(2, payment.retry().maxAttempts());
    }
}
~~~

Hai cách đọc ở đây dựa trên **cùng nguồn test properties**. Không có chuyện một cách được ưu tiên hơn cách kia chỉ vì nó sử dụng annotation.

Nếu cần kiểm tra riêng binding một configuration type mà không khởi động web server, có thể dùng **ApplicationContextRunner** với **@EnableConfigurationProperties** thích hợp.

## 21. Khi nào nên dùng Environment?

Chọn Environment khi:

- Cần đọc một hoặc vài key lẻ.
- Key được chọn động theo logic có kiểm soát.
- Viết công cụ chẩn đoán các property/profile.
- Đang xây framework/infrastructure code cần nhìn trực tiếp Environment.
- Muốn chủ động quyết định lúc nào tra cứu giá trị.

Ví dụ đơn giản:

~~~java
String region = environment.getProperty(
        "deployment.region", "local");
~~~

Không cần tạo một configuration record riêng chỉ cho một key nếu lợi ích không đáng kể.

Tuy nhiên, khi một nhóm property bắt đầu xuất hiện ở nhiều chỗ, hãy cân nhắc chuyển sang một type có cấu trúc để giảm các string literal lặp lại.

## 22. Khi nào nên dùng @ConfigurationProperties?

Chọn @ConfigurationProperties khi:

- Một subsystem có nhiều key liên quan.
- Cần nested object, List, Map hoặc kiểu domain rõ ràng.
- Cần conversion có cấu trúc như Duration, DataSize, URI.
- Cần validation cho giá trị bắt buộc và giới hạn.
- Cần metadata giúp IDE completion.
- Muốn service chỉ phụ thuộc vào một object immutable.
- Muốn mô tả và kiểm thử hợp đồng cấu hình dễ dàng.

Một kiến trúc dễ bảo trì có thể là:

~~~text
PaymentService      -> PaymentProperties
ShippingService     -> ShippingProperties
NotificationService -> NotificationProperties
DiagnosticsService  -> Environment
~~~

Các service nghiệp vụ nhận object tương ứng với trách nhiệm của mình. Service chẩn đoán nhận Environment để truy vấn các key theo yêu cầu.

## 23. Những lỗi thường gặp

### Lỗi 1: cho rằng Environment chỉ đọc String

Có overload **getProperty(key, Class<T>)**. Hạn chế chính là API tra cứu theo key, không phải tuyệt đối không hỗ trợ chuyển kiểu.

### Lỗi 2: mong getProperty(prefix) tạo POJO

Lời gọi **getProperty("client.payment")** không có nghĩa là yêu cầu Binder dựng **PaymentProperties**. Để bind cấu trúc, dùng @ConfigurationProperties hoặc Binder.

### Lỗi 3: rải chuỗi key khắp code

Việc lặp **"client.payment.base-url"** ở nhiều service làm đổi tên khó khăn và dễ sai chính tả. Dùng configuration object nếu nhóm key cùng mô tả một trách nhiệm.

### Lỗi 4: nhầm relaxed binding với mọi kiểu tên đều tự tương đương

Spring Boot Binder có quy tắc relaxed binding. Environment và từng PropertySource có hành vi tra cứu riêng. Nên giữ canonical kebab-case và kiểm tra kết quả thực tế.

### Lỗi 5: quên đăng ký @ConfigurationProperties type

Gắn annotation lên record chưa đủ nếu nó nằm ngoài phạm vi scanning hoặc chưa được @EnableConfigurationProperties đăng ký.

### Lỗi 6: dùng @Component với constructor binding một cách máy móc

Constructor binding được Spring Boot hỗ trợ trong cơ chế đăng ký configuration properties, không phải qua mọi cách tạo Spring bean.

### Lỗi 7: tưởng List tự merge khi có override

Danh sách từ nguồn ưu tiên cao hơn có thể thay toàn bộ danh sách từ nguồn thấp hơn. Phải cấp đủ phần tử cần dùng hoặc thay cách thiết kế nếu cần merge theo key.

### Lỗi 8: không validation các trường bắt buộc

Binder chuyển một giá trị sang đúng kiểu chưa bảo đảm nó hợp lệ về nghiệp vụ. Dùng validation để phát hiện sớm những giá trị không hợp lệ.

### Lỗi 9: nghĩ sửa YAML sẽ tự làm mới bean

Không tự giả định có hot reload/refresh cấu hình. Hiểu lifecycle, PropertySource và cơ chế restart của môi trường triển khai.

### Lỗi 10: log secret khi xem Environment

PropertySource có thể chứa password, token hoặc thông tin nội bộ. Chỉ log key/giá trị không nhạy cảm; bảo vệ Actuator và các endpoint debug.

### Lỗi 11: nhiều model cùng prefix mà không có chủ đích

Có thể bind một prefix vào nhiều class, nhưng điều đó dễ tạo hợp đồng cấu hình phân tán. Nên có ranh giới sở hữu rõ, chẳng hạn một PaymentProperties với nested Retry.

## 24. Bài thực hành

### Bài A — đọc cùng property theo hai cách

1. Tạo **client.payment.connect-timeout: 3s** trong application.yml.
2. Gọi **Environment.getProperty(...)** để nhận giá trị chuỗi.
3. Tạo record PaymentProperties với **Duration connectTimeout**.
4. So sánh **3s** với **Duration.ofSeconds(3)**.

**Điều cần hiểu:** cùng nguồn cấu hình nhưng cách biểu diễn trong Java khác nhau.

### Bài B — ghi đè bằng biến môi trường

1. Giữ YAML với **connect-timeout: 3s**.
2. Khởi động với **CLIENT_PAYMENT_CONNECTTIMEOUT=8s**.
3. Đọc bằng Environment và PaymentProperties.
4. Khởi động lại không có biến đó.

**Điều cần hiểu:** thứ tự ưu tiên nguồn ảnh hưởng đến cả hai cách đọc; không cần sửa JAR.

### Bài C — tạo nested object

1. Thêm **retry.max-attempts** và **retry.initial-delay**.
2. Thử đọc từng key bằng Environment.
3. Bind nested record Retry và kiểm tra giá trị.
4. Viết assertion cho **retry().maxAttempts()**.

**Điều cần hiểu:** binding object mô tả cấu trúc rõ hơn.

### Bài D — thêm List

1. Tạo hai endpoints trong YAML.
2. Dùng Environment đọc **endpoints[0].name**.
3. Dùng List<Endpoint> bind cả danh sách.
4. Thay cả danh sách qua nguồn ưu tiên cao hơn và quan sát kết quả.

**Điều cần hiểu:** getProperty theo chỉ số không tương đương bind collection.

### Bài E — thử lỗi conversion và validation

1. Đặt **connect-timeout=wrong** để quan sát lỗi chuyển Duration.
2. Đặt **max-attempts=0** với ràng buộc @Min(1).
3. So sánh loại lỗi và thời điểm lỗi xuất hiện.

**Điều cần hiểu:** conversion và validation là hai chức năng khác nhau.

### Bài F — so sánh vòng đời

1. Khởi động ứng dụng với file cấu hình ban đầu.
2. Sửa file ngoài JAR khi ứng dụng vẫn đang chạy.
3. Quan sát giá trị đọc lại từ Environment và bean đã bind.
4. Restart và so sánh.

**Điều cần hiểu:** không có bảo đảm tự refresh nếu ứng dụng chưa thiết kế cơ chế nạp lại.

## 25. Ghi nhớ

- **Environment** là API truy vấn property và profile của Spring.
- **getProperty(...)** giải quyết một key, có thể trả về String hoặc chuyển thành kiểu đích phù hợp.
- **@ConfigurationProperties** liên kết cả một prefix vào object Java có kiểu.
- Cả hai dùng dữ liệu từ hệ thống PropertySource, nên chịu ảnh hưởng của thứ tự ưu tiên cấu hình.
- **Binder** hỗ trợ relaxed binding, nested object, List, Map và conversion có cấu trúc.
- **Validation** và **configuration metadata** là những lợi ích quan trọng khi thiết kế configuration properties cho subsystem.
- **@Value** là một cách tiêm property khác; không đồng nhất với Binder.
- Lời gọi Environment có thể diễn ra ở thời điểm tùy ý, còn configuration properties bean thường bind trong vòng đời khởi tạo context.
- Với key đơn hoặc debug, Environment là lựa chọn phù hợp. Với nhóm cấu hình nhiều trường, nên ưu tiên @ConfigurationProperties.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Externalized Configuration, *Type-safe Configuration Properties*, *Relaxed Binding*, *@ConfigurationProperties vs. @Value*, *Merging Complex Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework — Environment and PropertySource abstraction: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
- Spring Boot 3.3 API — Binder: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/Binder.html
