# @ConfigurationProperties để gom cấu hình theo tiền tố

Khi một ứng dụng Spring Boot có nhiều tham số cấu hình liên quan với nhau — như địa chỉ dịch vụ ngoài, timeout, số lần thử lại hoặc chế độ chạy — đọc từng giá trị riêng bằng `@Value` sẽ nhanh chóng làm code rời rạc. Các chuỗi tên property xuất hiện ở nhiều service, việc chuyển đổi kiểu khó quản lý, còn những điều kiện bắt buộc của cấu hình khó kiểm tra tập trung.

**`@ConfigurationProperties`** giải quyết vấn đề này: Spring Boot bind những property có cùng tiền tố (*prefix*) thành một object Java có cấu trúc và kiểu dữ liệu rõ ràng. Service chỉ việc inject object đó bằng constructor injection.

Ví dụ, nhóm cấu hình:

~~~yaml
app:
  payment:
    endpoint: https://payments.example.test
    connect-timeout: 2s
    read-timeout: 5s
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

có thể trở thành một object `PaymentProperties` với kiểu `URI`, `Duration` và một nhóm `Retry` lồng nhau. Điều quan trọng là service không cần biết giá trị đến từ YAML, file properties, environment variable hay command-line argument.

Bài học giải thích cách Spring Boot bind cấu hình, các cách đăng ký bean cấu hình, JavaBean và record bất biến, relaxed binding, conversion, validation, defaults, testing và những lỗi thường gặp.

## 1. Từ @Value rời rạc đến một hợp đồng cấu hình

Một ví dụ ban đầu:

~~~java
@Service
public class PaymentClient {

    public PaymentClient(
            @Value("${app.payment.endpoint}") String endpoint,
            @Value("${app.payment.connect-timeout}") String connectTimeout,
            @Value("${app.payment.read-timeout}") String readTimeout,
            @Value("${app.payment.retry.max-attempts}") int maxAttempts) {
        // Khởi tạo client...
    }
}
~~~

Cách viết này hợp lệ cho vài property nhỏ, nhưng khi số lượng tăng, ta gặp các vấn đề:

- Nhiều class phải biết tên property dạng chuỗi.
- Dễ lặp lại logic chuyển kiểu và giá trị mặc định.
- Khó nhìn thấy toàn bộ cấu hình của một module.
- Không có một nơi duy nhất để kiểm tra ràng buộc giữa các giá trị.
- Khi refactor, compiler không giúp tìm mọi chuỗi property viết sai.
- Constructor của service có thể dài chỉ vì chứa cấu hình.

Với `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration connectTimeout,
        Duration readTimeout,
        Retry retry
) {
    public record Retry(int maxAttempts, Duration backoff) {
    }
}
~~~

Service trở thành:

~~~java
@Service
public class PaymentClient {

    private final PaymentProperties properties;

    public PaymentClient(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI endpoint() {
        return properties.endpoint();
    }
}
~~~

Đây là mô hình **type-safe configuration**: config là dependency có tên, kiểu và cấu trúc rõ ràng, thay vì một tập string không liên hệ với nhau trong logic nghiệp vụ.

## 2. Cơ chế binding và ý nghĩa của tiền tố

Annotation thuộc Spring Boot:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
~~~

`@ConfigurationProperties(prefix = "app.payment")` cho binder biết cần đọc nhóm thuộc tính bắt đầu bằng `app.payment` từ `Environment`.

~~~text
application.yml / application.properties
         + environment variables
         + command-line arguments
                    |
                    v
              Environment
                    |
                    v
           Configuration Binder
             prefix: app.payment
                    |
                    v
             PaymentProperties
                    |
                    v
                PaymentClient
~~~

Ví dụ, nguồn cấu hình ở dạng properties:

~~~properties
app.payment.endpoint=https://payments.example.test
app.payment.connect-timeout=2s
app.payment.read-timeout=5s
app.payment.retry.max-attempts=3
app.payment.retry.backoff=500ms
~~~

Binder có thể tạo cấu trúc tương ứng:

~~~text
PaymentProperties
├── endpoint = https://payments.example.test
├── connectTimeout = PT2S
├── readTimeout = PT5S
└── retry
    ├── maxAttempts = 3
    └── backoff = PT0.5S
~~~

`PT2S` và `PT0.5S` là biểu diễn `Duration` cho hai giây và nửa giây.

**Prefix không phải tên bean, tên package hay đường dẫn file.** Nó là phần đầu của tên cấu hình logic. Ví dụ `app.mail.from-address` không thuộc nhóm `app.payment`.

### 2.1. Binding không chỉ đọc application.yml

`Environment` có thể chứa nhiều `PropertySource`. Spring Boot xử lý cấu hình từ file, biến môi trường, command-line và các nguồn khác theo thứ tự ưu tiên.

Nếu cùng một property xuất hiện ở nhiều nguồn, nguồn có precedence cao hơn có thể ghi đè nguồn thấp hơn. Java class dùng để bind vẫn không thay đổi.

### 2.2. Chỉ có annotation chưa đủ

Class:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(URI endpoint) {
}
~~~

chưa chắc đã trở thành bean chỉ nhờ annotation. Nó phải được đăng ký qua một cơ chế như `@ConfigurationPropertiesScan`, `@EnableConfigurationProperties`, hoặc một con đường đăng ký bean thích hợp.

## 3. Viết cấu hình mutable theo JavaBean

Với JavaBean có constructor mặc định và setter, Spring Boot có thể bind từng property sau khi tạo instance:

~~~java
package com.example.payment;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private URI endpoint;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration readTimeout = Duration.ofSeconds(5);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Ở đây:

- `endpoint` sẽ nhận giá trị từ `app.payment.endpoint`.
- `connectTimeout` nhận `app.payment.connect-timeout`.
- `readTimeout` nhận `app.payment.read-timeout`.
- Giá trị initializer có thể là default khi property tương ứng không được cung cấp.

Kiểu JavaBean dễ hiểu với các hệ thống cũ, nhưng object mutable và phải khai báo khá nhiều getter/setter. Nếu muốn tạo một object bất biến sau binding, record hoặc constructor binding thường phù hợp hơn.

## 4. Đăng ký bằng @ConfigurationPropertiesScan

Trong một ứng dụng có nhiều nhóm cấu hình, cách tiện lợi là scan:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Cấu trúc package:

~~~text
com.example
├── Application.java
├── payment
│   └── PaymentProperties.java
└── mail
    └── MailProperties.java
~~~

Vì `Application` nằm trong package cha, cấu hình scan phù hợp sẽ tìm các class `@ConfigurationProperties` trong những package con.

Có thể chỉ định phạm vi cụ thể:

~~~java
@ConfigurationPropertiesScan(
        basePackages = "com.example.shared.config"
)
~~~

hoặc dùng marker class tránh gắn với chuỗi package:

~~~java
@ConfigurationPropertiesScan(
        basePackageClasses = SharedConfigMarker.class
)
~~~

`SharedConfigMarker` là một class được định nghĩa trong package cần scan.

Lưu ý: `@ConfigurationPropertiesScan` không giống component scan của `@SpringBootApplication`; nó phục vụ việc tìm và đăng ký các class cấu hình properties. Những class đã được đăng ký như `@Component` không được xử lý theo cùng một con đường properties scan thông thường.

## 5. Đăng ký tường minh bằng @EnableConfigurationProperties

Khi chỉ muốn đăng ký một vài kiểu cấu hình cụ thể:

~~~java
package com.example.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentProperties.class)
public class PaymentConfiguration {
}
~~~

Hoặc:

~~~java
@EnableConfigurationProperties({
        PaymentProperties.class,
        MailProperties.class
})
~~~

Cách này đặc biệt phù hợp với:

- Auto-configuration của starter.
- Module có cấu hình riêng.
- Test context cần một class properties nhất định.
- Thành phần không muốn quét toàn bộ package.

| Đặc điểm | `@ConfigurationPropertiesScan` | `@EnableConfigurationProperties` |
| --- | --- | --- |
| Cách chọn class | Scan package | Danh sách class cụ thể |
| Khi thêm một kiểu properties | Có thể tự được scan | Cần khai báo thêm |
| Thường dùng | Ứng dụng | Starter, module, test |
| Hỗ trợ constructor-bound class | Có, trong dòng Boot hỗ trợ | Có, trong dòng Boot hỗ trợ |
| Cần `@Component` | Không | Không |

Nên chọn một đường đăng ký nhất quán cho từng nhóm properties.

## 6. @Component và JavaBean binding

Một class JavaBean có thể được đăng ký như component:

~~~java
@Component
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String endpoint;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

Spring tạo bean bằng cơ chế component thông thường và binder thiết lập property sau đó.

Tuy nhiên, nếu class là record hoặc immutable class được thiết kế để bind qua constructor, **không nên** đồng thời dùng `@Component`. Khi đó Spring có thể coi các tham số constructor là dependency cần autowire từ bean container thay vì các giá trị cấu hình.

Đối với record, nên dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

## 7. @Bean kết hợp @ConfigurationProperties

Khi class nằm trong thư viện ngoài và bạn không thể thêm annotation vào class đó, có thể đặt `@ConfigurationProperties` trên factory method:

~~~java
@Configuration(proxyBeanMethods = false)
public class ExternalClientConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.external")
    public ExternalClientOptions externalClientOptions() {
        return new ExternalClientOptions();
    }
}
~~~

`ExternalClientOptions` là kiểu minh họa có setter hoặc property writable để binder điền giá trị.

Cách này hữu ích cho class bên thứ ba có JavaBean-style properties. Nếu kiểu ngoài bất biến hoặc không hỗ trợ bind phù hợp, có thể định nghĩa một class `ExternalProperties` riêng rồi dùng factory method tạo client:

~~~java
@Bean
ExternalClient externalClient(ExternalProperties properties) {
    return ExternalClient.builder()
            .endpoint(properties.endpoint())
            .timeout(properties.timeout())
            .build();
}
~~~

Nhờ vậy, cấu hình thuộc quyền quản lý của ứng dụng, còn class thư viện chỉ nhận dữ liệu đã chuyển đổi và validate.

## 8. Khi nào chọn cách đăng ký nào?

Nếu bạn viết một ứng dụng Spring Boot bình thường và muốn sử dụng record properties, `@ConfigurationPropertiesScan` thường là lựa chọn dễ hiểu. Nếu viết auto-configuration cung cấp một contract cấu hình rõ ràng, dùng `@EnableConfigurationProperties`.

Nếu đang làm việc với thư viện mutable có setter, `@Bean` kết hợp `@ConfigurationProperties` có thể hữu ích. `@Component` vẫn dùng được với JavaBean mutable, nhưng không nên trộn nó với constructor-bound record.

Quan trọng nhất là **class properties phải thực sự được đăng ký**. Khi một service báo không inject được bean properties, hãy kiểm tra đường đăng ký trước khi nghi ngờ nội dung YAML.
## 9. Immutable record và constructor binding

Với Spring Boot hiện đại, record là một cách gọn gàng để mô tả cấu hình bất biến:

~~~java
package com.example.payment;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration connectTimeout,
        Duration readTimeout
) {
}
~~~

YAML:

~~~yaml
app:
  payment:
    endpoint: https://payments.example.test
    connect-timeout: 2s
    read-timeout: 5s
~~~

Binder dùng canonical constructor của record để tạo instance đã có dữ liệu. Sau đó service dùng các accessor như `endpoint()` và `readTimeout()`. Không cần setter, và người sử dụng không thể vô tình đổi timeout bằng một lời gọi setter trong lúc chạy.

### 9.1. @ConstructorBinding có bắt buộc không?

Với Spring Boot 3.x, một configuration properties class chỉ có một parameterized constructor thường được suy luận là constructor binding; một record thông thường **không cần** `@ConstructorBinding`.

Nếu class có nhiều constructor, một constructor có thể cần annotation `@ConstructorBinding` để chỉ rõ constructor dành cho binding:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private final URI endpoint;

    @ConstructorBinding
    public PaymentProperties(URI endpoint) {
        this.endpoint = endpoint;
    }

    public URI getEndpoint() {
        return endpoint;
    }
}
~~~

Trong Spring Boot 3.x, import:

~~~java
import org.springframework.boot.context.properties.bind.ConstructorBinding;
~~~

Với Spring Boot 2.x, annotation này có lịch sử và package khác theo phiên bản. Khi duy trì code cũ, cần dùng API phù hợp với dependency Boot thực tế, không sao chép import giữa các major versions.

### 9.2. Vì sao không dùng @Component trên record?

Ví dụ dưới đây không phải lựa chọn khuyến nghị:

~~~java
@Component
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(URI endpoint, Duration timeout) {
}
~~~

Spring có thể cố gắng resolve `URI` và `Duration` như các bean cần autowire trong constructor của component. Điều đó khác với constructor binding từ `Environment` và thường làm context không khởi động như mong đợi.

Giải pháp: bỏ `@Component`, dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(PaymentProperties.class)`.

## 10. Relaxed binding: tên Java và tên property không cần giống hệt

Spring Boot Binder hỗ trợ **relaxed binding**. Cùng một thuộc tính có thể biểu diễn bằng cách viết khác nhau trong các nguồn cấu hình thích hợp.

Java:

~~~java
public record PaymentProperties(Duration connectTimeout) {
}
~~~

Các dạng property thường được binder nhận diện:

~~~properties
app.payment.connect-timeout=2s
app.payment.connectTimeout=2s
app.payment.connect_timeout=2s
~~~

Để nhất quán, nên dùng **kebab-case** trong `application.yml`, `application.properties` và tài liệu:

~~~properties
app.payment.connect-timeout=2s
~~~

Trong Java, tên component/field là `connectTimeout` theo camelCase.

### 10.1. Quy tắc environment variable

Với canonical property name, quy tắc phổ biến để chuyển thành OS environment variable là:

1. Thay dấu chấm bằng dấu gạch dưới.
2. Bỏ dấu gạch nối trong mỗi segment.
3. Chuyển tên thành chữ hoa.

Ví dụ:

| Canonical property | Environment variable |
| --- | --- |
| `app.payment.endpoint` | `APP_PAYMENT_ENDPOINT` |
| `app.payment.read-timeout` | `APP_PAYMENT_READTIMEOUT` |
| `app.payment.retry.max-attempts` | `APP_PAYMENT_RETRY_MAXATTEMPTS` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |

Điểm dễ nhầm: `read-timeout` chuyển thành `READTIMEOUT`, không phải mặc nhiên chèn thêm dấu gạch dưới giữa `READ` và `TIMEOUT`. Dấu gạch dưới biểu thị ranh giới các segment vốn ngăn cách bằng dấu chấm.

Hãy thử giá trị env thực tế trên môi trường deploy để chắc chắn công cụ cấu hình container, shell hoặc CI/CD đã truyền đúng.

### 10.2. Danh sách từ environment

Với cấu hình:

~~~yaml
app:
  routing:
    regions:
      - ap-southeast-1
      - eu-west-1
~~~

có thể khai báo các phần tử theo chỉ số:

~~~text
APP_ROUTING_REGIONS_0=ap-southeast-1
APP_ROUTING_REGIONS_1=eu-west-1
~~~

Quy tắc index trong environment variable dùng số được bao quanh bởi dấu underscore.

### 10.3. Tránh đặt nhiều alias khó hiểu

Relaxed binding không có nghĩa nên đổi cách viết tên property liên tục. Hãy công bố một canonical name, giữ ổn định trong tài liệu vận hành, và dùng quy tắc chuyển đổi tương ứng cho từng property source.

## 11. Chuyển đổi kiểu dữ liệu khi binding

`@ConfigurationProperties` không chỉ bind string. Spring Boot cung cấp conversion cho nhiều kiểu thông dụng:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
        boolean enabled,
        int maxConnections,
        Duration requestTimeout,
        DataSize maxUploadSize,
        URI endpoint,
        List<String> allowedRegions,
        Map<String, String> tags
) {
}
~~~

Ví dụ YAML:

~~~yaml
app:
  storage:
    enabled: true
    max-connections: 20
    request-timeout: 750ms
    max-upload-size: 20MB
    endpoint: https://objects.example.test
    allowed-regions:
      - ap-southeast-1
      - eu-west-1
    tags:
      owner: platform
      environment: staging
~~~

Các nhóm kiểu thường gặp:

| Kiểu Java | Ví dụ cấu hình | Kết quả |
| --- | --- | --- |
| `boolean` | `true` | Bật/tắt |
| `int`, `long` | `20` | Số nguyên |
| `String` | `staging` | Văn bản |
| `Duration` | `750ms`, `2s`, `5m` | Khoảng thời gian |
| `DataSize` | `20MB`, `512KB` | Kích thước dữ liệu |
| `URI` | `https://objects.example.test` | URI |
| Enum | `STRICT` | Một giá trị trong enum |
| `List<T>` | YAML sequence | Danh sách |
| `Map<K,V>` | YAML mapping | Bảng key/value |
| Object lồng nhau | `retry.max-attempts` | Nhóm con |

`DataSize` thuộc Spring Framework:

~~~java
import org.springframework.util.unit.DataSize;
~~~

### 11.1. Ghi rõ đơn vị thời gian

Ví dụ:

~~~properties
app.payment.connect-timeout=2s
app.payment.retry.backoff=500ms
~~~

Binder chuyển thành `Duration`. Dùng suffix `ms`, `s`, `m`, `h` giúp tránh phải đoán một số trần trụi là mili giây hay giây. Trong một số tình huống, `@DurationUnit` cho phép xác định đơn vị mặc định khi số không có suffix.

### 11.2. Ghi rõ đơn vị kích thước

Ví dụ:

~~~properties
app.storage.max-upload-size=20MB
~~~

Kiểu `DataSize` thể hiện ý định tốt hơn một số nguyên có đơn vị byte không được giải thích.

### 11.3. Enum

~~~java
public enum RetryPolicy {
    NONE, FIXED, EXPONENTIAL
}
~~~

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(RetryPolicy retryPolicy) {
}
~~~

~~~properties
app.payment.retry-policy=EXPONENTIAL
~~~

Nếu giá trị không chuyển được sang enum hoặc kiểu dữ liệu khác, Boot có thể báo lỗi binding lúc khởi động, thay vì để một string không hợp lệ đi sâu vào nghiệp vụ.

## 12. Nested properties: nhóm con, danh sách và map

Một module lớn thường có cấu hình nhiều cấp.

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        boolean enabled,
        String fromAddress,
        Retry retry
) {
    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {
    }
}
~~~

YAML:

~~~yaml
app:
  notification:
    enabled: true
    from-address: noreply@example.test
    retry:
      max-attempts: 3
      backoff: 250ms
~~~

Service có thể gọi:

~~~java
int maxAttempts = properties.retry().maxAttempts();
Duration backoff = properties.retry().backoff();
~~~

Điều kiện là `retry` phải tồn tại. Nếu cấu hình cho phép bỏ cả nhóm nested, hãy khai báo default hoặc validation; không mặc nhiên dereference một object có thể null.

### 12.1. Nested object trong JavaBean

Với JavaBean, có thể khởi tạo object con:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public class NotificationProperties {

    private Retry retry = new Retry();

    public Retry getRetry() {
        return retry;
    }

    public void setRetry(Retry retry) {
        this.retry = retry;
    }

    public static class Retry {

        private int maxAttempts = 3;
        private Duration backoff = Duration.ofMillis(250);

        public int getMaxAttempts() {
            return maxAttempts;
        }

        public void setMaxAttempts(int maxAttempts) {
            this.maxAttempts = maxAttempts;
        }

        public Duration getBackoff() {
            return backoff;
        }

        public void setBackoff(Duration backoff) {
            this.backoff = backoff;
        }
    }
}
~~~

Nếu file không có `retry`, object con đã được khởi tạo và giữ default đã khai báo.

### 12.2. Danh sách các object

YAML:

~~~yaml
app:
  routing:
    targets:
      - name: primary
        url: https://primary.example.test
      - name: backup
        url: https://backup.example.test
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(List<Target> targets) {

    public record Target(String name, URI url) {
    }
}
~~~

Binder tạo danh sách `Target` với giá trị từ YAML.

**Chú ý khi override list:** với các nguồn cấu hình ở mức ưu tiên khác nhau, Spring Boot thường lấy danh sách từ nguồn ưu tiên cao hơn thay vì cộng dồn từng phần tử của nhiều danh sách. Không nên giả định `application-prod.yml` sẽ chỉ bổ sung thêm phần tử vào danh sách trong `application.yml`.

### 12.3. Map và key đặc biệt

Map thích hợp với cặp cấu hình theo tên:

~~~yaml
app:
  routing:
    labels:
      owner: platform
      team: billing
~~~

Java:

~~~java
@ConfigurationProperties(prefix = "app.routing")
public record RoutingProperties(Map<String, String> labels) {
}
~~~

Nếu map key có dấu đặc biệt hoặc cần giữ nguyên dấu chấm/ký tự, binder có quy tắc map key riêng, bao gồm bracket notation trong một số trường hợp. Hãy kiểm thử các key thực tế, đặc biệt khi key là một phần cấu hình định danh bên ngoài.

## 13. Giá trị mặc định: JavaBean initializer và @DefaultValue

Một số property nên có default rõ ràng, ví dụ timeout hoặc số lần retry. Một số property khác, đặc biệt endpoint quan trọng hoặc secret, nên bắt buộc có giá trị.

### 13.1. JavaBean field initializer

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private Duration readTimeout = Duration.ofSeconds(5);

    public Duration getReadTimeout() {
        return readTimeout;
    }

    public void setReadTimeout(Duration readTimeout) {
        this.readTimeout = readTimeout;
    }
}
~~~

Nếu không có `app.payment.read-timeout`, field có thể giữ giá trị khởi tạo.

### 13.2. Record và @DefaultValue

Với Spring Boot 3.x và các dòng hỗ trợ:

~~~java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @DefaultValue("5s") Duration readTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
~~~

Nếu property không được cung cấp, binder có thể dùng default này trong constructor binding.

### 13.3. Object lồng nhau có default

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        @DefaultValue Retry retry
) {
    public record Retry(
            @DefaultValue("3") int maxAttempts,
            @DefaultValue("250ms") Duration backoff
    ) {
    }
}
~~~

`@DefaultValue` không có nội dung trên component `Retry` có thể yêu cầu tạo object nested kể cả khi không có key con, rồi apply default cho từng thành phần.

Không nên đặt default tùy tiện để làm ứng dụng khởi động với endpoint giả hoặc credential không hợp lệ trong production.

## 14. Validation: fail fast khi cấu hình sai

Binding đúng kiểu chưa chắc cấu hình đúng nghiệp vụ. Ví dụ, số lần retry là 0, chuỗi email rỗng hoặc endpoint thiếu.

Có thể dùng **Bean Validation** để kiểm tra trong quá trình tạo configuration properties bean.

Dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Ví dụ record:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @NotNull URI endpoint,
        @NotBlank String fromAddress,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {
    }
}
~~~

Nếu cấu hình:

~~~yaml
app:
  mail:
    endpoint: https://mail.example.test
    from-address: ""
    request-timeout: 5s
    retry:
      max-attempts: 0
      backoff: 250ms
~~~

thì `fromAddress` vi phạm `@NotBlank` và `maxAttempts` vi phạm `@Min(1)`. Startup có thể thất bại và báo constraint nào không thỏa mãn.

### 14.1. @Valid và nested validation

`@Valid` cho phép validation đi vào object con `Retry`. `@NotNull` kiểm tra sự hiện diện của object.

Nếu chỉ đánh dấu constraint trên class ngoài nhưng quên `@Valid`, các constraint bên trong nested object có thể không được đánh giá như mong đợi.

### 14.2. Binding error khác validation error

Giá trị:

~~~properties
app.mail.request-timeout=not-a-duration
~~~

không chuyển được sang `Duration`: đây là lỗi conversion/binding.

Giá trị:

~~~properties
app.mail.retry.max-attempts=0
~~~

có thể chuyển sang `int`, nhưng vi phạm `@Min(1)`: đây là lỗi validation.

Khi đọc startup exception, hãy tìm tên property gây lỗi, giá trị được nhận, kiểu mong đợi và constraint liên quan.

### 14.3. Jakarta và javax theo phiên bản Boot

Spring Boot 3 trở lên dùng Jakarta namespace như `jakarta.validation.constraints.NotBlank`. Với ứng dụng Spring Boot 2, Bean Validation thường dùng `javax.validation.*`. Không trộn code import của các major versions.

## 15. Inject properties vào service bằng constructor

Sau khi bean properties đã được đăng ký, service inject như mọi dependency khác:

~~~java
@Service
public class MailClient {

    private final MailProperties mailProperties;

    public MailClient(MailProperties mailProperties) {
        this.mailProperties = mailProperties;
    }

    public URI destination() {
        return mailProperties.endpoint();
    }

    public Duration timeout() {
        return mailProperties.requestTimeout();
    }
}
~~~

Cách này giúp:

- Service không cần phụ thuộc trực tiếp `Environment`.
- Không lặp lại property key strings ở nhiều nơi.
- Unit test chỉ cần tạo một instance `MailProperties` với giá trị mong muốn.
- IDE có thể refactor Java symbol thay vì quét các chuỗi tùy ý.
- Validation và type conversion được gom ở boundary cấu hình.

Properties object nên giữ vai trò dữ liệu cấu hình; không nên đặt việc gọi HTTP, ghi database hay workflow nghiệp vụ vào getter/setter của nó.
## 16. So sánh @ConfigurationProperties và @Value

`@Value` không sai; nó hữu ích khi chỉ cần một vài giá trị đơn giản. Nhưng khi nhóm cấu hình phát triển, `@ConfigurationProperties` thường dễ quản lý hơn.

| Khía cạnh | `@Value` | `@ConfigurationProperties` |
| --- | --- | --- |
| Cách dùng | Trên field, constructor parameter, method | Trên class hoặc method `@Bean` |
| Phạm vi | Thường một giá trị | Nhóm nhiều giá trị có tiền tố |
| Tên property | Biểu thức dạng string | Một tiền tố, các field Java tương ứng |
| Nested object | Cần xử lý riêng | Hỗ trợ trực tiếp |
| List và map | Có thể xử lý nhưng cần chú ý biểu thức | Binder hỗ trợ có cấu trúc |
| Type safety | Phụ thuộc parameter/field | Một class contract rõ ràng |
| Validation toàn nhóm | Không phải khả năng chính | Hỗ trợ Bean Validation |
| Relaxed binding | Không nên giả định như Binder | Được thiết kế cho relaxed binding |
| Metadata/IDE completion | Hạn chế theo cách dùng | Có configuration metadata processor |
| SpEL | Có thể dùng SpEL | Không dùng SpEL như một template trong properties binder |

Ví dụ `@Value`:

~~~java
@Value("${app.title:My Application}")
private String title;
~~~

Nếu ứng dụng chỉ cần một tiêu đề tĩnh, đây là cách đơn giản.

Nhưng khi một feature có endpoint, retry policy, timeout, credentials và validation, một nhóm `@ConfigurationProperties` thường thể hiện hợp đồng cấu hình tốt hơn.

### 16.1. Thời điểm nên giữ @Value

- Giá trị đơn giản, độc lập.
- Một thành phần nhỏ chỉ cần đúng một property.
- Có nhu cầu thực sự với biểu thức SpEL.

Không nên máy móc tạo một class cấu hình cho mỗi string. Mục tiêu là gom **những property liên quan về chức năng** chứ không phải tăng số lượng file.

## 17. Nguồn cấu hình và thứ tự ưu tiên

`@ConfigurationProperties` nhận giá trị từ `Environment`. Do đó, khi một tên property có ở nhiều nguồn, precedence của Spring Boot quyết định nguồn nào được ưu tiên.

File `application.yml`:

~~~yaml
app:
  payment:
    read-timeout: 5s
~~~

Nếu môi trường chạy cung cấp:

~~~text
APP_PAYMENT_READTIMEOUT=10s
~~~

thì trong cấu hình Boot phổ biến, OS environment variable có precedence cao hơn packaged `application.yml` và có thể override timeout thành 10 giây.

Command line:

~~~bash
java -jar app.jar --app.payment.read-timeout=20s
~~~

thường có precedence cao hơn các file cấu hình và OS environment trong cấu hình mặc định của Boot.

Tuy nhiên, khi dự án có thêm `PropertySource` tùy chỉnh, config server hoặc cấu hình đặc thù, cần kiểm tra thứ tự nguồn thực tế.

### 17.1. Profile-specific files

Ví dụ:

~~~text
application.yml
application-dev.yml
application-prod.yml
~~~

`application.yml`:

~~~yaml
app:
  payment:
    connect-timeout: 2s
    read-timeout: 5s
~~~

`application-prod.yml`:

~~~yaml
app:
  payment:
    read-timeout: 10s
~~~

Khi profile `prod` được bật và các file được nạp theo cơ chế Spring Boot, giá trị `read-timeout` của profile có thể ghi đè base; `connect-timeout` vẫn dùng base nếu không bị override.

Code Java không thay đổi:

~~~java
public PaymentClient(PaymentProperties properties) {
    this.properties = properties;
}
~~~

Đây là một lợi ích thiết thực: cùng một artifact có thể chạy nhiều môi trường với cấu hình khác nhau.

### 17.2. Danh sách qua nhiều nguồn không mặc nhiên nối nhau

Nếu base config có:

~~~yaml
app:
  routing:
    targets:
      - name: primary
        url: https://primary.example.test
~~~

và production profile định nghĩa lại `targets`, binder thường sử dụng toàn bộ list ở nguồn có precedence cao hơn. Không mặc định nối hai danh sách.

Nếu cần override chi tiết theo định danh, đôi khi `Map<String, Target>` phù hợp hơn một `List<Target>`.

### 17.3. Thay file runtime không tự refresh bean

Nếu cập nhật `application.yml` khi ứng dụng đã chạy, `@ConfigurationProperties` không tự bảo đảm bean được rebind ngay lập tức. Cấu hình runtime refresh cần cơ chế riêng, thường bao gồm cách phát hiện thay đổi, điều phối bean và bảo đảm tính nhất quán.

Không dùng object properties như một kho trạng thái runtime biến đổi tùy ý.

## 18. Metadata giúp IDE gợi ý property

Spring Boot có configuration processor có thể sinh metadata cho các class `@ConfigurationProperties`, hỗ trợ completion và mô tả trong IDE.

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

Với Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Khi build, processor có thể sinh file:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Ví dụ cấu trúc metadata giản lược:

~~~json
{
  "groups": [
    {
      "name": "app.payment",
      "type": "com.example.payment.PaymentProperties"
    }
  ],
  "properties": [
    {
      "name": "app.payment.read-timeout",
      "type": "java.time.Duration"
    }
  ]
}
~~~

Metadata thực tế có thể bổ sung source type, description, default values và các trường khác tùy source code.

### 18.1. Metadata không thay binder runtime

Configuration processor phục vụ phát triển và tooling; binding runtime do Spring Boot Binder và `Environment` thực hiện.

IDE không gợi ý property không đồng nghĩa property đó chắc chắn không bind được. Ngược lại, gợi ý trong IDE cũng không chứng minh môi trường deploy đã cung cấp cấu hình hợp lệ.

### 18.2. Mô tả property và gợi ý

Nên viết Javadoc giải thích các field không hiển nhiên, ví dụ timeout là connect timeout hay request timeout, đơn vị khuyến nghị, giá trị nào là required.

Với thư viện cung cấp starter, metadata tốt giúp người dùng biết một module hỗ trợ những tên property nào mà không phải đọc source trực tiếp.

## 19. Kiểm thử binding với ApplicationContextRunner

Một bài test hữu ích phải xác nhận **object được tạo qua Binder**, không chỉ tạo constructor thủ công.

Spring Boot cung cấp `ApplicationContextRunner` để dựng context nhỏ:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration readTimeout,
        @DefaultValue("3") int maxAttempts
) {
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class PaymentPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfig.class);

    @Test
    void bindsPropertiesByPrefix() {
        runner.withPropertyValues(
                "app.payment.endpoint=https://payments.example.test",
                "app.payment.read-timeout=750ms"
        ).run(context -> {
            PaymentProperties props =
                    context.getBean(PaymentProperties.class);

            assertThat(props.endpoint())
                    .isEqualTo(URI.create("https://payments.example.test"));
            assertThat(props.readTimeout())
                    .isEqualTo(Duration.ofMillis(750));
            assertThat(props.maxAttempts())
                    .isEqualTo(3);
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(PaymentProperties.class)
    static class TestConfig {
    }
}
~~~

Test này cần dependency `spring-boot-test`, JUnit và AssertJ tương ứng. Với ứng dụng Spring Boot, `spring-boot-starter-test` thường cung cấp các phần cần thiết.

### 19.1. Test conversion thất bại

Ví dụ:

~~~java
@Test
void rejectsInvalidDuration() {
    runner.withPropertyValues(
            "app.payment.endpoint=https://payments.example.test",
            "app.payment.read-timeout=not-a-duration"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Giá trị `not-a-duration` không phù hợp với kiểu `Duration`. Context phải phản ánh lỗi binding thay vì silently tạo một giá trị tùy ý.

### 19.2. Test validation thất bại

Nếu class được đánh dấu `@Validated` và có `@NotBlank`, `@Min`, `@NotNull`, hãy thử các case như:

- Endpoint bị thiếu.
- Sender rỗng.
- Retry bằng 0.
- Timeout âm nếu nghiệp vụ không chấp nhận.

Cần có Bean Validation provider trên test classpath. Test nên xác nhận context fail và, ở mức cần thiết, thông báo lỗi liên quan đến property đúng.

### 19.3. Test nested/list

Nếu class có nested retry, kiểm tra giá trị sau binding:

~~~java
assertThat(props.retry().maxAttempts()).isEqualTo(3);
assertThat(props.retry().backoff())
        .isEqualTo(Duration.ofMillis(250));
~~~

Nếu có list targets, kiểm tra số phần tử, thứ tự nếu quan trọng và giá trị của từng phần tử. Đừng chỉ test một field đơn giản rồi giả định mọi cấu trúc nested đều hoạt động.

## 20. Ví dụ Spring Boot hoàn chỉnh: cấu hình email client

Giả sử ứng dụng cần một mail API client. Cấu hình:

~~~yaml
app:
  mail:
    endpoint: https://mail-api.example.test
    sender: noreply@example.test
    connect-timeout: 2s
    request-timeout: 10s
    retry:
      max-attempts: 3
      backoff: 500ms
~~~

`MailProperties.java`:

~~~java
package com.example.mail;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.mail")
public record MailProperties(
        @NotNull URI endpoint,
        @NotBlank String sender,
        @NotNull Duration connectTimeout,
        @NotNull Duration requestTimeout,
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts,
            @NotNull Duration backoff
    ) {
    }
}
~~~

`MailClient.java`:

~~~java
package com.example.mail;

import org.springframework.stereotype.Service;

@Service
public class MailClient {

    private final MailProperties properties;

    public MailClient(MailProperties properties) {
        this.properties = properties;
    }

    public String describeConfiguration() {
        return "Endpoint=" + properties.endpoint()
                + ", sender=" + properties.sender()
                + ", timeout=" + properties.requestTimeout();
    }
}
~~~

`Application.java`:

~~~java
package com.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Với dependency Spring Boot và Bean Validation phù hợp, tiến trình khởi động thực hiện:

1. Tải các property source.
2. Scan và đăng ký `MailProperties`.
3. Bind các giá trị có prefix `app.mail`.
4. Chuyển string URL thành `URI`, timeout thành `Duration`.
5. Kiểm tra validation của các field bắt buộc.
6. Tạo `MailClient` và inject properties đã bind.

`MailClient` ở ví dụ chỉ minh họa việc sử dụng cấu hình; nó chưa thực hiện gửi email thật. Ở dự án thực tế cần thư viện HTTP client, authentication, timeout, retry có giới hạn và xử lý lỗi phù hợp.

### 20.1. Thay cấu hình mà không sửa code nghiệp vụ

Local:

~~~yaml
app:
  mail:
    endpoint: http://localhost:9091
~~~

Staging:

~~~yaml
app:
  mail:
    endpoint: https://mail-staging.example.test
~~~

Khi thay endpoint qua config source, `MailClient` vẫn inject cùng một kiểu `MailProperties`. Đây là ranh giới tốt giữa code và triển khai.

### 20.2. Nếu có API token hoặc mật khẩu

Có thể bổ sung `apiToken` vào properties class, nhưng cần bảo vệ:

- Không commit secret vào Git.
- Không hard-code secret trong Java source.
- Không log toàn bộ properties object; record `toString()` có thể lộ dữ liệu nhạy cảm.
- Dùng secret manager, environment hoặc hệ cấu hình bảo mật phù hợp.
- Kiểm soát truy cập và chính sách che thông tin của Actuator/configuration endpoints.

`@ConfigurationProperties` là cơ chế binding, **không phải** một cơ chế bảo mật secret.

## 21. Những lỗi thường gặp

### 21.1. Không tìm thấy bean properties

**Triệu chứng:** Service constructor báo không tìm được `PaymentProperties`.

**Nguyên nhân:** Class có `@ConfigurationProperties` nhưng chưa được đăng ký.

**Cách xử lý:** Dùng `@ConfigurationPropertiesScan` ở package phù hợp hoặc `@EnableConfigurationProperties(PaymentProperties.class)`.

### 21.2. Sai prefix hoặc indentation YAML

**Triệu chứng:** Field vẫn null hoặc chỉ có default.

**Nguyên nhân:** Annotation dùng `app.payment` còn file dùng `app.payments`, hoặc YAML lồng sai cấp.

**Cách xử lý:** Đối chiếu cấu trúc property và prefix, không chỉ nhìn tên field.

### 21.3. Dùng @Component trên immutable record

**Triệu chứng:** Spring tìm bean kiểu `URI`, `Duration`, `String` để inject vào constructor.

**Nguyên nhân:** Spring xử lý record như component autowiring thông thường.

**Cách xử lý:** Bỏ `@Component` và đăng ký bằng configuration-properties scan/enable.

### 21.4. Sai kiểu dữ liệu

**Triệu chứng:** Bind `Duration`, `DataSize`, `URI` hoặc enum thất bại.

**Nguyên nhân:** Giá trị cấu hình không hợp lệ hoặc không thể convert.

**Cách xử lý:** Ghi đơn vị rõ ràng, dùng enum đúng và đọc root cause của binding error.

### 21.5. Nested object bị null

**Triệu chứng:** `props.retry().maxAttempts()` ném `NullPointerException`.

**Nguyên nhân:** Nhóm retry không được cung cấp, không có default và không validate required.

**Cách xử lý:** Dùng default cho nested object hoặc `@Valid @NotNull` để fail fast khi thiếu nhóm bắt buộc.

### 21.6. Validation không chạy

**Triệu chứng:** Giá trị invalid vẫn được chấp nhận.

**Nguyên nhân:** Thiếu `@Validated`, constraint, `@Valid` trên nested object hoặc Bean Validation provider.

**Cách xử lý:** Kiểm tra annotation và dependency `spring-boot-starter-validation`.

### 21.7. Environment variable đặt tên không khớp

**Triệu chứng:** Giá trị env không override YAML.

**Nguyên nhân:** Quy tắc chuyển dấu chấm và dấu gạch nối bị áp dụng sai.

**Cách xử lý:** Chuyển canonical name đúng quy tắc, ví dụ `app.payment.read-timeout` thành `APP_PAYMENT_READTIMEOUT`.

### 21.8. List từ profile ghi đè dữ liệu base

**Triệu chứng:** Một số phần tử biến mất khi bật profile.

**Nguyên nhân:** List thường được thay thế bởi cấu hình ở nguồn ưu tiên cao hơn, không cộng dồn tự động.

**Cách xử lý:** Khai báo đầy đủ list cần dùng trong profile hoặc chuyển sang map nếu cần override từng key.

### 21.9. Mong file cấu hình thay đổi sẽ tự cập nhật bean

**Triệu chứng:** Thay `application.yml` nhưng service vẫn dùng giá trị cũ.

**Nguyên nhân:** Runtime refresh không phải hành vi mặc định của `@ConfigurationProperties`.

**Cách xử lý:** Cần một chiến lược reload rõ ràng nếu thật sự muốn config động; đừng dùng properties object như shared runtime state.

### 21.10. Lộ token trong log

**Triệu chứng:** API key xuất hiện khi debug.

**Nguyên nhân:** Log toàn bộ object properties, gọi `toString()` hoặc xuất các thuộc tính nhạy cảm qua endpoint không bảo vệ.

**Cách xử lý:** Chỉ log dữ liệu không nhạy cảm và đặt chính sách truy cập/che giá trị phù hợp.

## 22. Quy trình thiết kế một nhóm properties

Khi thêm cấu hình cho một tính năng, nên:

1. Chọn tiền tố mang ý nghĩa module, ví dụ `app.mail` hoặc `app.payment`.
2. Xác định field nào bắt buộc, field nào tùy chọn.
3. Chọn kiểu Java phù hợp: `URI`, `Duration`, `DataSize`, enum, list/map.
4. Quyết định JavaBean mutable hay record immutable.
5. Đặt canonical property name bằng kebab-case.
6. Tạo nested object cho các nhóm có quan hệ chặt.
7. Chỉ đặt default khi đó là giá trị an toàn và có chủ đích.
8. Thêm validation và failure message rõ ràng.
9. Đăng ký bean bằng scan hoặc enable tường minh.
10. Inject qua constructor vào service sử dụng.
11. Viết test cho một case hợp lệ và những case thiếu/sai quan trọng.
12. Viết tài liệu cấu hình, cách override và nguồn secret.

Một `@ConfigurationProperties` class tốt đóng vai trò **hợp đồng cấu hình của module**. Nó giải thích module cần dữ liệu gì, kiểu của chúng ra sao và lỗi xảy ra khi cấu hình không hợp lệ.

## 23. Bài thực hành

### Bài A: Chuyển bốn @Value thành một class

Cho các property:

~~~properties
app.report.endpoint=https://reports.example.test
app.report.timeout=3s
app.report.format=PDF
app.report.enabled=true
~~~

Tạo `ReportProperties` chứa `URI endpoint`, `Duration timeout`, enum `Format` và `boolean enabled`. Đăng ký bean và inject vào `ReportService`, thay các tham số `@Value` cũ.

### Bài B: Dùng record và relaxed binding

Tạo record với component `requestTimeout`, cấu hình tên `request-timeout` trong YAML, rồi test giá trị bind.

Sau đó chạy với environment variable `APP_REPORT_REQUESTTIMEOUT` và kiểm tra kết quả override.

### Bài C: Nested retry

Thêm nhóm:

~~~yaml
app:
  report:
    retry:
      max-attempts: 4
      backoff: 300ms
~~~

Tạo nested `Retry` record và thử bỏ nhóm này. Dùng `@DefaultValue` nếu retry là tùy chọn; dùng validation nếu là required.

### Bài D: Validation

Thử timeout sai định dạng, endpoint thiếu, retry bằng 0. Phân biệt lỗi conversion và lỗi constraint trong startup log.

### Bài E: Bind một class thư viện

Giả sử `ExternalClientOptions` có setter `setEndpoint` và `setTimeout`. Dùng `@Bean` kết hợp `@ConfigurationProperties(prefix = "app.external")` để bind.

Sau đó tạo phương án dùng record `ExternalProperties` và factory method, so sánh nơi đặt validation.

### Bài F: Profile và list

Cho một list routing targets trong base config và một list khác trong profile `prod`. Viết test với profile hoạt động, quan sát cách list được thay thế thay vì nối phần tử.

### Bài G: Kiểm thử hợp đồng cấu hình

Dùng `ApplicationContextRunner` để xác nhận ba tình huống: cấu hình hợp lệ, cấu hình thiếu trường bắt buộc và cấu hình sai kiểu dữ liệu.

## 24. Câu hỏi tự kiểm tra

**1. `@ConfigurationProperties` làm gì?**

Nó bind nhóm các property có cùng tiền tố thành một object Java có cấu trúc và kiểu dữ liệu rõ ràng.

**2. Prefix `app.payment` có phải tên bean không?**

Không. Đó là một tiền tố logic của tên cấu hình trong `Environment`.

**3. Chỉ đặt `@ConfigurationProperties` lên class đã đủ chưa?**

Chưa. Class phải được đăng ký bằng scan, enable hoặc một cơ chế bean phù hợp.

**4. Record properties có cần setter không?**

Không. Constructor binding tạo một object bất biến với dữ liệu đã bind.

**5. Vì sao không dùng `@Component` cho record constructor-bound?**

Vì Spring có thể xử lý tham số constructor như các dependency bean thông thường, thay vì bind chúng từ property source.

**6. `read-timeout` tương ứng với component Java nào?**

`readTimeout`, nhờ relaxed binding.

**7. Có thể bind `2s` và `20MB` thành những kiểu gì?**

`Duration` và `DataSize`.

**8. `@Validated` có vai trò gì?**

Kích hoạt validation của configuration properties theo các constraint đã khai báo, giúp phát hiện cấu hình không hợp lệ.

**9. `@ConfigurationProperties` có tự reload khi file đổi sau startup không?**

Không theo mặc định. Cần một cơ chế refresh/reload riêng nếu cần config động.

**10. Khi nào `@Value` vẫn hợp lý?**

Khi chỉ cần một vài property đơn giản và không có một nhóm cấu hình có ý nghĩa cần quản lý.

**11. Có nên log một record properties chứa token không?**

Không. `toString()` hoặc logging có thể làm lộ secret.

## 25. Kết luận

`@ConfigurationProperties` giúp Spring Boot **gom cấu hình theo tiền tố thành một object có cấu trúc và kiểu dữ liệu rõ ràng**. Đây là cách tách code nghiệp vụ khỏi nguồn cấu hình và tránh sự lan rộng của những chuỗi tên property trong controller, service và client.

Dùng `@ConfigurationPropertiesScan` khi muốn phát hiện những nhóm cấu hình ở cấp ứng dụng, dùng `@EnableConfigurationProperties` cho module hoặc test cần đăng ký class cụ thể, và dùng `@Bean` có `@ConfigurationProperties` khi cần bind một object được tạo bởi factory method. Record bất biến phù hợp với constructor binding ở các dòng Boot hiện đại; JavaBean mutable vẫn có chỗ đứng cho những class dùng setter.

Hãy sử dụng canonical property name dạng kebab-case, đặt default cho tùy chọn, validation cho dữ liệu bắt buộc, inject properties qua constructor và kiểm thử binding từ property sources. Cuối cùng, nhớ rằng binding không tự cung cấp runtime refresh hay bảo mật secret.

Một nhóm configuration properties được thiết kế như hợp đồng của module sẽ giúp ứng dụng dễ hiểu, dễ kiểm thử và dễ triển khai trên nhiều môi trường mà không phải thay đổi logic nghiệp vụ.



