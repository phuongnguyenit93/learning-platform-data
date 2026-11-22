# Tách lớp cấu hình khỏi dịch vụ nghiệp vụ và phụ thuộc bean khác

## 1. Mục tiêu: cấu hình là dữ liệu, service là hành vi, bean khác là cộng tác viên

Khi một ứng dụng Spring Boot phát triển, lớp nghiệp vụ thường cần nhiều tham số: URL của dịch vụ ngoài, thời gian chờ, số lần thử lại, cờ bật/tắt, giới hạn kích thước, tên queue hoặc chính sách vận hành. Nếu mỗi service tự đọc `Environment` hay chứa hàng loạt annotation `@Value`, tên khóa cấu hình và quyết định kỹ thuật bị rải vào code nghiệp vụ.

Một ví dụ dễ gặp:

```java
@Service
public class ShippingService {

    @Value("${shipping.base-url}")
    private String baseUrl;

    @Value("${shipping.connect-timeout:2s}")
    private String connectTimeout;

    @Value("${shipping.max-attempts:3}")
    private int maxAttempts;

    // Bên dưới còn có logic nghiệp vụ gửi đơn hàng.
}
```

Cách viết này có thể hoạt động với ứng dụng nhỏ nhưng có một số hệ quả:

- Một nhóm thuộc tính liên quan bị phân tán thành nhiều trường và annotation.
- Service phải biết tên khóa `shipping.base-url`, `shipping.connect-timeout` thay vì làm việc với một hợp đồng Java có kiểu.
- Việc kiểm tra giá trị bắt buộc, ràng buộc số lần thử lại và thời gian chờ khó tập trung.
- Khi nhiều service cùng dùng một nhóm cấu hình, dễ lặp tên khóa hoặc dùng mặc định không đồng nhất.
- Kiểm thử logic nghiệp vụ dễ bị trói vào quá trình nạp tệp YAML và tạo Spring context.
- Dịch vụ có thể lẫn nhiệm vụ **đọc cấu hình**, **khởi tạo đối tượng hạ tầng** và **xử lý nghiệp vụ**.

`@ConfigurationProperties` giúp tách những trách nhiệm này bằng cách **liên kết một nhóm thuộc tính ngoài ứng dụng vào một đối tượng Java có kiểu**. Service nhận đối tượng đó như một phụ thuộc qua constructor. Những bean hạ tầng khác như `HttpClient`, `Clock`, `DataSource` hoặc adapter dịch vụ vẫn được quản lý riêng qua dependency injection.

Mô hình mong muốn:

```text
application.yml / biến môi trường / tham số chạy
                        |
                        v
                  Spring Environment
                        |
                        v
          Binder + @ConfigurationProperties
                        |
                        v
                ShippingProperties
             (giá trị, không hành vi IO)
                  /           \
                 v             v
          HttpClient bean   ShippingService
                 |             ^
                 +-------------+
                               ^
                               |
                         Clock bean
                               |
                               v
                       Kết quả nghiệp vụ
```

Một sự phân chia dễ ghi nhớ:

1. **Configuration Properties:** mô tả *dữ liệu cấu hình*.
2. **Infrastructure configuration:** dùng dữ liệu và bean liên quan để *lắp ráp đối tượng kỹ thuật*.
3. **Business service:** dùng các phụ thuộc đã được lắp ráp để *thực hiện hành vi nghiệp vụ*.
4. **Spring container:** chịu trách nhiệm *tạo bean và nối các phụ thuộc*.

Bài này xây một ví dụ xuyên suốt và giải thích vì sao không nên biến lớp `@ConfigurationProperties` thành một service hoặc một “kho chứa mọi bean”.

## 2. @ConfigurationProperties làm gì và không làm gì?

Annotation:

```java
@ConfigurationProperties(prefix = "shipping")
```

nói với Spring Boot rằng những thuộc tính dưới tiền tố `shipping` sẽ được liên kết vào kiểu Java tương ứng. Chẳng hạn:

```yaml
shipping:
  enabled: true
  base-url: https://shipping.example.invalid/api/
  connect-timeout: 2s
  max-attempts: 3
```

Các giá trị có thể được ánh xạ sang:

```java
boolean enabled
URI baseUrl
Duration connectTimeout
int maxAttempts
```

Spring Boot thực hiện binding và conversion dựa trên `Environment`. Những thuộc tính có cùng khóa từ nguồn ưu tiên cao hơn, chẳng hạn biến môi trường hoặc tham số dòng lệnh, có thể ghi đè giá trị trong YAML trước khi đối tượng cấu hình được tạo.

**`@ConfigurationProperties` không có nhiệm vụ gửi HTTP request, mở kết nối cơ sở dữ liệu hoặc điều phối quy trình giao hàng.** Nó cũng không phải cơ chế chung để tự động tiêm những Spring bean khác vào mọi tham số constructor của một record.

Ví dụ, trong lớp properties:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration connectTimeout,
        boolean enabled,
        int maxAttempts
) {}
```

bốn tham số constructor đại diện cho **bốn giá trị cấu hình**. Chúng không phải `@Autowired` cho một client HTTP, repository hoặc service khác. Việc constructor binding đối tượng cấu hình và dependency injection giữa Spring bean là **hai hoạt động khác nhau**, dù cuối cùng cùng xảy ra trong quá trình dựng application context.

## 3. Ví dụ xuyên suốt: tích hợp dịch vụ vận chuyển

Ta sẽ tổ chức một ứng dụng giả lập có nhiệm vụ xây dựng kế hoạch gọi dịch vụ vận chuyển. Ví dụ chỉ in kế hoạch và thông số; nó **không thực hiện HTTP request tới mạng thật**, nên có thể dùng URL minh họa an toàn.

Cấu trúc đề xuất:

```text
shipping-demo/
└── src/
    ├── main/
    │   ├── java/com/example/shipping/
    │   │   ├── ShippingApplication.java
    │   │   ├── config/
    │   │   │   ├── ShippingProperties.java
    │   │   │   └── InfrastructureConfiguration.java
    │   │   └── service/
    │   │       └── ShippingService.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-prod.yml
    └── test/
        └── java/com/example/shipping/
            └── ShippingApplicationTest.java
```

Tên package chỉ là một ví dụ về phân tách code theo vai trò. Trong một dự án lớn, cũng có thể phân chia theo feature, chẳng hạn `shipping/config` và `shipping/service`. Điểm quan trọng hơn tên folder là **chiều phụ thuộc**: service được cấp giá trị cấu hình, chứ lớp dữ liệu cấu hình không kéo logic nghiệp vụ vào trong nó.

### 3.1. Tệp cấu hình chung

Tạo `src/main/resources/application.yml`:

```yaml
shipping:
  enabled: true
  base-url: https://shipping.example.invalid/api/
  connect-timeout: 2s
  max-attempts: 3
```

Ý nghĩa:

- `shipping.enabled`: cờ quyết định chức năng tích hợp đang được bật hay không.
- `shipping.base-url`: địa chỉ gốc của dịch vụ vận chuyển, ở đây là một URL minh họa.
- `shipping.connect-timeout`: thời gian thiết lập kết nối.
- `shipping.max-attempts`: giới hạn số lần thử theo chính sách của ứng dụng.

Giá trị `2s` biểu diễn thời lượng, không phải một chuỗi mà service phải tự chia tách thành số và đơn vị. `base-url` được chuyển sang kiểu `URI` để code làm việc với đại diện có cấu trúc của địa chỉ.

Trong môi trường thật, các tham số cần được lựa chọn theo SLA, hành vi retry và kiến trúc hệ thống. Các số ở đây chỉ để giúp người học quan sát binding.

## 4. Tạo lớp cấu hình thuần dữ liệu

Tạo `config/ShippingProperties.java`:

```java
package com.example.shipping.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {
}
```

Đây là record Java (phù hợp với Java 17 trở lên và cách constructor binding thông dụng của Spring Boot 3).

Record làm rõ vài nguyên tắc:

- Mỗi thành phần đại diện một dữ liệu mà môi trường triển khai có thể cung cấp.
- Các giá trị được cung cấp lúc tạo đối tượng, thay vì để service gọi setter giữa chừng.
- Service truy cập bằng `properties.enabled()`, `properties.baseUrl()`, v.v.
- Không có `Environment`, repository, HTTP client, tài khoản truy cập hay service nghiệp vụ trong constructor.
- Không có logic gọi mạng, ghi dữ liệu hoặc thay đổi trạng thái hệ thống trong record.

**Không cần đánh dấu record này bằng `@Component` để bắt Spring tự tạo nó.** Ta sẽ đăng ký `@ConfigurationProperties` bằng một cơ chế chuyên dụng ở phần tiếp theo.

### Vì sao không dùng một class có hàng chục @Value?

Giả sử ba thành phần của hệ thống cùng cần `shipping.connect-timeout`. Với `@Value` riêng lẻ, mỗi nơi có thể viết:

```java
@Value("${shipping.connect-timeout:2s}")
Duration timeout;
```

Một nơi khác có thể vô tình dùng `${shipping.connection-timeout:3s}` và cho ra hành vi khác. Khi tập thuộc tính được định nghĩa tập trung qua `ShippingProperties`, tất cả bean có thể nhận **cùng một kiểu và cùng một nhóm giá trị đã được liên kết**.

Đây không phải là lệnh cấm `@Value`: annotation đó vẫn hữu ích cho một vài thuộc tính độc lập. Nhưng khi đã có một nhóm cấu hình cùng miền ý nghĩa, `@ConfigurationProperties` thường dễ duy trì và dễ kiểm thử hơn.

## 5. Đăng ký @ConfigurationProperties trong Spring container

Một lớp có annotation `@ConfigurationProperties` cần được Spring Boot biết tới qua cơ chế đăng ký thích hợp. Với đúng một lớp properties, cách tường minh là `@EnableConfigurationProperties`.

Tạo `ShippingApplication.java`:

```java
package com.example.shipping;

import com.example.shipping.config.ShippingProperties;
import com.example.shipping.service.ShippingService;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShippingApplication.class, args);
    }

    @Bean
    ApplicationRunner demoRunner(ShippingService shippingService) {
        return args -> {
            System.out.println(shippingService.preview());
        };
    }
}
```

`@EnableConfigurationProperties(ShippingProperties.class)` đăng ký lớp properties để Spring Boot binder tạo giá trị từ tiền tố `shipping`.

Nếu ứng dụng có nhiều lớp cấu hình, có thể chọn quét theo package:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ShippingApplication {
    // ...
}
```

`@ConfigurationPropertiesScan` cần import từ `org.springframework.boot.context.properties.ConfigurationPropertiesScan`. Chọn **một cách đăng ký rõ ràng** cho lớp cần dùng, tránh tự ý thêm `@Component` hoặc đăng ký trùng đối tượng rồi không biết bean nào đang được inject.

### Constructor binding và bean injection không phải một

Khi Spring Boot constructor-bind `ShippingProperties`, nó tìm các giá trị tương ứng với tên trường trong nguồn cấu hình. Nếu record chứa thêm một tham số kiểu `HttpClient`, binder không hiểu tham số ấy là một phụ thuộc Spring cần `@Autowired` như service thông thường. Đây không phải cách đúng để gộp client hạ tầng vào properties.

Đừng viết:

```java
// Phản ví dụ thiết kế: không trộn dữ liệu cấu hình với Spring bean
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        HttpClient httpClient,
        ShippingService shippingService
) {}
```

`httpClient` và `shippingService` không phải dữ liệu thuộc tính ngoài ứng dụng. Chúng là bean được tạo và quản lý bởi Spring container. Đưa chúng vào record cấu hình làm lẫn hai cơ chế tạo đối tượng.

## 6. Tạo bean hạ tầng từ các thuộc tính đã được binding

Giả sử ứng dụng cần `java.net.http.HttpClient` dùng thời gian chờ được cấu hình. Một class `@Configuration` có thể nhận `ShippingProperties` và tạo client.

Tạo `config/InfrastructureConfiguration.java`:

```java
package com.example.shipping.config;

import java.net.http.HttpClient;
import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class InfrastructureConfiguration {

    @Bean
    HttpClient shippingHttpClient(ShippingProperties properties) {
        return HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

Hai phương thức `@Bean` trả về những đối tượng hạ tầng thực sự:

- `shippingHttpClient` là client HTTP được khởi tạo với thời gian thiết lập kết nối từ cấu hình.
- `clock` là đồng hồ hệ thống, phục vụ những thao tác cần thời gian. Khi kiểm thử, ta có thể thay bằng một đồng hồ cố định mà không phải sửa lớp cấu hình.

Quan hệ được lắp ráp:

```text
ShippingProperties ---connectTimeout()---> HttpClient.Builder
                              |
                              v
                         HttpClient bean

InfrastructureConfiguration ---clock()---> Clock bean
```

Một điểm quan trọng: `ShippingProperties` **không cần gọi `new HttpClient`** và cũng không cần biết bean `Clock` tồn tại. Cấu hình thuần dữ liệu được tái sử dụng bởi lớp lắp ráp bean.

Trong một dự án có nhiều bean `HttpClient`, cần dùng `@Qualifier` hoặc định danh bean rõ ràng khi inject. Ở ví dụ tối thiểu này chỉ có một bean `HttpClient`, nên có thể inject theo kiểu.

### Tại sao nên tạo client ở @Configuration mà không tạo ngay trong service?

Nếu service tự viết:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(properties.connectTimeout())
        .build();
```

trong từng constructor, service vừa chịu trách nhiệm nghiệp vụ, vừa chịu trách nhiệm quản lý chi tiết kỹ thuật khởi tạo client. Khi thêm TLS, proxy, interceptor hoặc test double, phải thay đổi service.

Dời phần lắp ráp sang `@Configuration` khiến việc thử nghiệm đơn giản hơn. Service chỉ yêu cầu một `HttpClient` đã sẵn sàng; cấu hình hạ tầng chịu trách nhiệm cách tạo nó.

Tất nhiên, không phải mọi object kỹ thuật đều cần một Spring bean độc lập. Khi có lifecycle, cần tái sử dụng, cần thay thế trong test hoặc cần cấu hình tập trung, một bean hạ tầng thường hợp lý.

## 7. Service nhận properties và bean khác qua constructor

Tạo `service/ShippingService.java`:

```java
package com.example.shipping.service;

import com.example.shipping.config.ShippingProperties;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {

    private final ShippingProperties properties;
    private final HttpClient httpClient;
    private final Clock clock;

    public ShippingService(
            ShippingProperties properties,
            HttpClient httpClient,
            Clock clock) {
        this.properties = properties;
        this.httpClient = httpClient;
        this.clock = clock;
    }

    public String preview() {
        if (!properties.enabled()) {
            return "Shipping integration disabled";
        }

        URI endpoint = properties.baseUrl().resolve("v1/shipments");
        Duration timeout = httpClient.connectTimeout()
                .orElse(Duration.ZERO);

        return "endpoint=" + endpoint
                + ", maxAttempts=" + properties.maxAttempts()
                + ", connectTimeout=" + timeout
                + ", observedAt=" + clock.instant();
    }
}
```

Service có ba loại phụ thuộc với ba vai trò rõ ràng:

| Phụ thuộc | Vai trò | Được tạo từ đâu? |
| --- | --- | --- |
| `ShippingProperties` | Dữ liệu cấu hình có kiểu | Spring Boot Binder từ `shipping.*` |
| `HttpClient` | Công cụ giao tiếp HTTP | `@Bean` trong `InfrastructureConfiguration` |
| `Clock` | Nguồn thời gian để quan sát | `@Bean` trong `InfrastructureConfiguration` |

Logic `preview()` chỉ dựng chuỗi minh họa. Nó không gửi HTTP request. Trong ứng dụng thực tế, phương thức nghiệp vụ có thể dùng client để gọi API, nhưng mục tiêu bài này là **phân tách phụ thuộc**, không phải thực hành giao tiếp mạng.

Với cấu hình ở phần 3, kết quả tương tự:

```text
endpoint=https://shipping.example.invalid/api/v1/shipments,
maxAttempts=3,
connectTimeout=PT2S,
observedAt=<thời điểm chạy UTC>
```

`Duration.toString()` in khoảng hai giây theo dạng ISO-8601 `PT2S`. Phần `observedAt` thay đổi theo thời điểm chạy. Điều đó không ảnh hưởng đến cách binding cấu hình.

Lợi ích quan trọng: **ShippingService không tự tìm `shipping.base-url` trong YAML**, không tự đọc biến môi trường và không quyết định cách tạo bean `HttpClient`.

## 8. Ranh giới phụ thuộc: chiều nào là hợp lý?

Một thiết kế đơn giản có thể xem bằng sơ đồ:

```text
       [Nguồn cấu hình ngoài]
                 |
                 v
       [ShippingProperties]
           |          |
           v          v
 [Infrastructure]  [ShippingService]
           |          ^
           v          |
        [HttpClient] -+
                       ^
                       |
                    [Clock]
```

Các nguyên tắc nên giữ:

1. **Properties không phụ thuộc vào service.** Nó định nghĩa dữ liệu, không gọi nghiệp vụ.
2. **Properties không phụ thuộc vào hạ tầng được khởi tạo từ nó.** Không chứa `HttpClient` trong record cấu hình.
3. **Infrastructure bean có thể đọc properties.** Chẳng hạn timeout để tạo client.
4. **Service có thể nhận cả properties và các bean cộng tác.** Một số giá trị ảnh hưởng trực tiếp đến chính sách nghiệp vụ; một số cần được dùng để cấu hình bean hạ tầng.
5. **Không tạo vòng phụ thuộc.** Nếu service cần properties và một bean hạ tầng, đừng để bean hạ tầng đồng thời cần service chỉ để lấy lại cùng properties.

Ví dụ vòng nên tránh:

```text
ShippingService
    -> ShippingHttpClientFactory
          -> ShippingService
```

Thay vì factory hỏi service về timeout, hãy để cả hai cùng nhận `ShippingProperties` hoặc để cấu hình hạ tầng tạo client trước khi service nhận nó.

### Trách nhiệm nào thuộc service?

Không phải cứ dữ liệu xuất phát từ YAML là mọi xử lý quanh dữ liệu phải nằm trong lớp properties. Ví dụ số lần thử lại `maxAttempts` là một tham số; nhưng **thuật toán retry** bao gồm quyết định retry khi nào, backoff, xử lý lỗi nghiệp vụ và idempotency. Thuật toán đó thuộc về service hoặc thành phần chuyên trách retry, không thuộc record `ShippingProperties`.

Có thể mô tả:

```text
ShippingProperties.maxAttempts() = 3     // dữ liệu
RetryPolicy / ShippingService           // quyết định retry
HttpClient                              // công cụ truyền tải
```

Phân tách này ngăn lớp cấu hình biến thành nơi chứa ngẫu nhiên mọi logic.

## 9. Một ví dụ phản diện: service biết quá nhiều về Environment

Xem kiểu thiết kế sau:

```java
@Service
public class ShippingService {

    private final Environment env;

    public ShippingService(Environment env) {
        this.env = env;
    }

    public String baseUrl() {
        return env.getProperty("shipping.base-url");
    }

    public int maxAttempts() {
        return Integer.parseInt(
                env.getProperty("shipping.max-attempts", "3"));
    }
}
```

Với cách này, service chịu trách nhiệm đặt tên khóa, tra cứu, mặc định và chuyển kiểu. Khi thêm `shipping.connect-timeout`, nó phải tự quyết định cách parse `2s`. Việc kiểm thử cũng dễ yêu cầu môi trường cấu hình thay vì một đối tượng có kiểu được truyền thẳng.

Cách viết tách lớp:

```java
@Service
public class ShippingService {

    private final ShippingProperties properties;

    public ShippingService(ShippingProperties properties) {
        this.properties = properties;
    }

    public int maxAttempts() {
        return properties.maxAttempts();
    }
}
```

Trong ví dụ tối giản này, service chỉ nhận dữ liệu cần dùng. Việc binding đã xảy ra trước khi bean được cấp cho service.

**Đừng hiểu sai rằng `Environment` luôn không nên dùng.** Nó hữu ích ở mã hạ tầng, adapter kỹ thuật hoặc trường hợp thực sự cần tra cứu động. Nhưng nếu service chỉ cần vài giá trị cấu hình cố định, một object `@ConfigurationProperties` có kiểu giúp ý định rõ ràng hơn.

## 10. Kết hợp nhiều nhóm @ConfigurationProperties

Một ứng dụng thực tế có thể có nhiều miền cấu hình:

```text
shipping.*          -> ShippingProperties
payment.*           -> PaymentProperties
notification.*      -> NotificationProperties
storage.*           -> StorageProperties
```

Không nên tạo một record duy nhất như:

```java
@ConfigurationProperties(prefix = "application")
public record ApplicationProperties(
        String shippingBaseUrl,
        int shippingAttempts,
        String paymentUrl,
        String mailHost,
        String storageBucket,
        // ... 70 trường không liên quan
) {}
```

vì nó khiến một đối tượng chứa quá nhiều trách nhiệm, buộc các feature cùng phụ thuộc vào một mô hình cấu hình lớn. Một thay đổi ở storage có thể tác động đến cấu trúc dữ liệu mà service vận chuyển cũng nhận.

Tách theo miền:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxAttempts
) {}

@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        URI gatewayUrl,
        Duration requestTimeout
) {}
```

Sau đó service chỉ inject đúng đối tượng nó cần. Nếu một nghiệp vụ cần phối hợp shipping và payment, một *orchestrator service* có thể nhận cả hai service liên quan, thay vì ép hai nhóm properties biết đến nhau.

### Một service nhận nhiều nhóm properties được không?

Được, khi đó là nhu cầu thực tế:

```java
@Service
public class CheckoutCoordinator {
    public CheckoutCoordinator(
            ShippingProperties shipping,
            PaymentProperties payment) {
        // Sử dụng các chính sách cần thiết cho checkout.
    }
}
```

Tuy nhiên, nếu số lượng phụ thuộc tăng nhanh, cần cân nhắc lại ranh giới service, không biến constructor thành một danh sách tất cả cấu hình của ứng dụng.

## 11. @ConfigurationProperties và việc phụ thuộc vào một bean khác

Câu hỏi thường gặp: “Lớp properties có thể inject repository, service hoặc bean kỹ thuật để tính một giá trị không?”

Về mặt thiết kế, **không nên biến lớp configuration properties thành nơi tiêu thụ bean khác**. Các lớp properties do constructor binding tạo nên tập trung vào dữ liệu từ môi trường. Nếu cần kết hợp cấu hình với một bean khác, hãy thực hiện phép kết hợp ở lớp sở hữu hành vi hoặc lớp `@Configuration` tạo bean.

Ví dụ yêu cầu: khi tạo một outbound gateway, cần cả timeout từ YAML lẫn một `TokenProvider` do Spring quản lý.

Sơ đồ đúng:

```text
application.yml -> GatewayProperties ----+
                                         |
TokenProvider bean ---------------------+--> GatewayClient bean
                                         |
HttpClient bean ------------------------+
```

Ta có thể viết phương thức bean:

```java
@Configuration
public class GatewayConfiguration {

    @Bean
    GatewayClient gatewayClient(
            GatewayProperties properties,
            TokenProvider tokenProvider,
            HttpClient httpClient) {
        return new GatewayClient(
                properties.baseUrl(),
                properties.timeout(),
                tokenProvider,
                httpClient
        );
    }
}
```

`GatewayClient` và `TokenProvider` trong đoạn này là các kiểu ứng dụng cần định nghĩa; ví dụ chủ yếu minh họa **vị trí tiêm phụ thuộc bean**.

`GatewayProperties` nên là object chứa `URI baseUrl` và `Duration timeout`, không có constructor nhận `TokenProvider`. Mỗi công việc có đúng chỗ:

- Binder tạo properties từ cấu hình.
- Spring container tiêm `TokenProvider` và `HttpClient`.
- `@Bean` phối hợp chúng để tạo `GatewayClient`.

Nếu `GatewayClient` có nhiều phương thức và lifecycle riêng, có thể chuyển sang một lớp `@Component`/`@Service` nhận ba phụ thuộc qua constructor thay vì `@Bean`; ý tưởng tách trách nhiệm vẫn như nhau.

## 12. Validation: kiểm tra cấu hình trước khi service chạy

Binding thành kiểu Java không tự bảo đảm giá trị hợp lý. `maxAttempts = -3` vẫn là `int` hợp lệ về mặt kiểu, nhưng không có nghĩa trong chính sách retry. `connectTimeout = 0ms` có thể không phù hợp với cách tạo client của ứng dụng. `baseUrl` có thể vắng mặt.

Có thể sử dụng Jakarta Bean Validation nếu dự án có dependency hỗ trợ, thường là `spring-boot-starter-validation`.

Ví dụ thay đổi record:

```java
package com.example.shipping.config;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        boolean enabled,
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @Min(1) int maxAttempts
) {
}
```

Với validation được kích hoạt thích hợp:

- Thiếu `shipping.base-url` có thể bị phát hiện bởi `@NotNull`.
- Thiếu `shipping.connect-timeout` có thể bị phát hiện bởi `@NotNull`.
- `shipping.max-attempts=0` không đạt ràng buộc `@Min(1)`.
- Một chuỗi `shipping.max-attempts=lots` không thể chuyển thành `int`, dẫn đến binding/conversion error trước khi giá trị hợp lệ được inject.

Một số ràng buộc không thể biểu diễn chỉ bằng `@NotNull` hoặc `@Min`. Ví dụ URI phải có scheme `https`, timeout phải dương, hoặc một tính năng `enabled=false` thì endpoint được phép thiếu. Những quy tắc đó cần validation phù hợp với chính hợp đồng cấu hình; có thể dùng custom validator hay phương thức kiểm tra chuyên dụng.

**Lưu ý cấu hình mẫu:** các trường `URI` và `Duration` đơn giản không tự thực hiện mọi kiểm tra nghiệp vụ. Không nên khẳng định chỉ cần chuyển thành `URI` là bảo đảm URL có thể kết nối hoặc sử dụng HTTPS.

### Nên kiểm tra ở lớp properties hay service?

Một quy tắc phân chia hữu ích:

| Kiểm tra | Vị trí thường phù hợp |
| --- | --- |
| Khóa bắt buộc có được cấp không? | Validation khi binding properties |
| `maxAttempts` có là số dương? | Validation properties |
| Timeout có dương và trong giới hạn chấp nhận? | Validation properties hoặc logic khởi tạo hạ tầng |
| Khách hàng có được phép tạo vận đơn? | Service nghiệp vụ / authorization |
| Đơn hàng có đủ thông tin giao hàng? | Logic nghiệp vụ |
| API ngoài có đang khả dụng? | Health check, client và cơ chế vận hành |
| Credential đã hết hạn? | Cơ chế xác thực và quản lý bí mật |

Mục đích là **fail fast khi cấu hình sai**, không biến record properties thành nơi chạy quy trình nghiệp vụ.

## 13. Giá trị mặc định: đặt ở đâu?

Có nhiều cách đặt mặc định, và mỗi cách truyền đạt một hợp đồng khác nhau.

### 13.1. Mặc định trong application.yml

```yaml
shipping:
  enabled: false
  connect-timeout: 2s
  max-attempts: 3
```

Đây là cách dễ đọc cho các giá trị chung. File theo profile hoặc môi trường chạy có thể ghi đè từng khóa. Một bean khác tra cứu cùng khóa qua `Environment` cũng nhận được giá trị từ nguồn chung này.

### 13.2. Mặc định trong lớp cấu hình

Với record, có thể dùng một constructor hoặc mô hình dữ liệu thích hợp để áp dụng mặc định, nhưng phải hiểu rõ điều kiện constructor binding và giá trị `null`/primitive khi property vắng mặt. Không nên viết constructor nhận thêm Spring bean chỉ để tính mặc định.

Spring Boot còn hỗ trợ annotation như `@DefaultValue` trong ngữ cảnh constructor binding. Ví dụ ý tưởng:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        @DefaultValue("false") boolean enabled,
        URI baseUrl,
        @DefaultValue("2s") Duration connectTimeout,
        @DefaultValue("3") int maxAttempts
) {}
```

Lớp binder áp dụng mặc định tại thành phần khi không có thuộc tính phù hợp. Điều này khác với fallback được đặt rải ở từng annotation `@Value`.

### 13.3. Mặc định trong service

Nếu đó thực sự là **quy tắc nghiệp vụ** (chẳng hạn tối đa số bước xử lý nếu một chính sách nghiệp vụ không được cung cấp), service có thể chứa quy tắc của mình. Nhưng nếu mặc định thuộc **hợp đồng cấu hình vận hành**, đặt ở properties hoặc file cấu hình chung thường rõ hơn.

Tránh cùng một giá trị có ba mặc định khác nhau:

```text
application.yml          max-attempts=3
ShippingProperties       default=5
ShippingService          fallback=10
```

Việc trùng nguồn sự thật khiến người vận hành không biết giá trị nào mới được áp dụng và dễ gây lỗi khi chuyển môi trường.

## 14. Mỗi môi trường dùng cùng service như thế nào?

Lớp `ShippingService` không thay đổi khi ứng dụng chạy với profile khác nhau. Chỉ nguồn cấu hình có hiệu lực thay đổi.

Giữ `application.yml` như phần 3. Tạo `application-prod.yml`:

```yaml
shipping:
  enabled: true
  base-url: https://shipping-prod.example.invalid/api/
  connect-timeout: 800ms
  max-attempts: 2
```

Để chạy với profile production:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Khi `prod` hoạt động, Spring Boot nạp cấu hình theo profile rồi binder liên kết giá trị có hiệu lực vào `ShippingProperties`. Bean `HttpClient` nhận timeout từ properties; `ShippingService` nhận cùng một object properties và client đã được cấu hình.

Không cần viết trong service:

```java
if ("prod".equals(activeProfile)) {
    // Đọc timeout production
} else {
    // Đọc timeout development
}
```

Việc chọn tham số vận hành đã được đặt ở cấu hình. Service vẫn thực hiện logic nhất quán cho mọi môi trường.

### Nguồn có ưu tiên cao hơn file theo profile

Ví dụ:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --shipping.max-attempts=4
```

Trong cấu hình Spring Boot chuẩn, tham số dòng lệnh có ưu tiên cao hơn Config Data trong `application-prod.yml`. Vì vậy `ShippingProperties.maxAttempts()` nhận `4` thay vì `2`. Không có lớp service nào cần biết giá trị đến từ đâu.

Tương tự, biến môi trường có thể ghi đè một giá trị. Trong quy tắc tên biến môi trường thông dụng của Spring Boot, `shipping.max-attempts` có dạng `SHIPPING_MAXATTEMPTS`. Với tên khóa canonical, binder có thể liên kết các nguồn tương ứng theo relaxed binding.

**Không đưa password hoặc token thật vào YAML đã commit.** Khi cần secret, nên cấp qua cơ chế quản lý bí mật của môi trường triển khai. `@ConfigurationProperties` không tự biến dữ liệu cấu hình thành dữ liệu được mã hóa hoặc bảo vệ.

## 15. Kiểm thử ShippingService mà không khởi động Spring

Đây là một lợi ích quan trọng của việc tách cấu hình khỏi nghiệp vụ. Trong unit test, ta **tự tạo một ShippingProperties** với giá trị mong muốn rồi truyền vào service như bất kỳ object Java nào khác. Không cần đọc `application.yml` và không cần khởi động application context.

Ví dụ dùng JUnit 5:

```java
package com.example.shipping.service;

import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shipping.config.ShippingProperties;

import java.net.URI;
import java.net.http.HttpClient;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class ShippingServiceTest {

    @Test
    void previewUsesProvidedConfigurationAndCollaborators() {
        ShippingProperties properties = new ShippingProperties(
                true,
                URI.create("https://test.example.invalid/api/"),
                Duration.ofSeconds(2),
                4
        );

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        ShippingService service = new ShippingService(
                properties, client, fixedClock
        );

        String preview = service.preview();

        assertTrue(preview.contains(
                "https://test.example.invalid/api/v1/shipments"));
        assertTrue(preview.contains("maxAttempts=4"));
        assertTrue(preview.contains("connectTimeout=PT2S"));
        assertTrue(preview.contains("2026-01-01T00:00:00Z"));
    }
}
```

Kiểm thử này làm rõ ranh giới:

- `ShippingProperties` là object có thể tạo trực tiếp.
- `HttpClient` và `Clock` là cộng tác viên riêng.
- `ShippingService` là class Java thuần có constructor rõ ràng.
- Không phải giả lập `Environment`, không phụ thuộc vào profile hoặc đường dẫn YAML.
- Kiểm thử không gửi network request vì `preview()` chỉ xây chuỗi.

Với nghiệp vụ thật, có thể thay `HttpClient` bằng một interface adapter do ứng dụng định nghĩa và dùng fake trong unit test. Các thao tác HTTP nên được kiểm thử riêng với mock server hoặc integration test phù hợp. Đừng buộc mọi unit test phải kéo theo một client HTTP thật nếu chức năng cần kiểm tra là xử lý nghiệp vụ.

## 16. Kiểm thử binding riêng với logic nghiệp vụ

Unit test service ở phần trước chỉ chứng minh service xử lý những object được truyền vào. Nó **không xác nhận** `shipping.connect-timeout: 2s` đã được binder chuyển thành `Duration.ofSeconds(2)`.

Để kiểm chứng binding, dùng kiểm thử có Spring context hoặc `ApplicationContextRunner`.

Ví dụ với Spring Boot Test và JUnit 5:

```java
package com.example.shipping;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.shipping.config.ShippingProperties;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
    "shipping.enabled=true",
    "shipping.base-url=https://integration.example.invalid/api/",
    "shipping.connect-timeout=750ms",
    "shipping.max-attempts=5"
})
class ShippingApplicationTest {

    @Autowired
    ShippingProperties shippingProperties;

    @Test
    void bindsExternalizedValuesToTypedProperties() {
        assertTrue(shippingProperties.enabled());
        assertEquals(
            URI.create("https://integration.example.invalid/api/"),
            shippingProperties.baseUrl()
        );
        assertEquals(
            Duration.ofMillis(750),
            shippingProperties.connectTimeout()
        );
        assertEquals(5, shippingProperties.maxAttempts());
    }
}
```

Trường hợp này chủ đích kiểm tra cơ chế:

1. Thuộc tính kiểm thử được cấp vào Spring context.
2. Binder chuyển các giá trị từ nguồn cấu hình sang kiểu Java.
3. `ShippingProperties` được đăng ký nhờ `@EnableConfigurationProperties`.
4. Các trường có đúng giá trị kỳ vọng.

Ứng dụng ví dụ có `ApplicationRunner` in preview khi context khởi động. Điều đó không gửi HTTP request, nhưng sẽ tạo dòng log kiểm thử; với ứng dụng thật, cần thiết kế khởi động test phù hợp để không thực hiện tác vụ nguy hiểm.

Từ đó, có thể phân biệt hai loại kiểm thử:

| Kiểm thử | Mục đích | Có cần Spring context? |
| --- | --- | --- |
| Unit test `ShippingService` | Logic sử dụng dữ liệu và các cộng tác viên | Không |
| Test binding `ShippingProperties` | Tên khóa, chuyển kiểu và đăng ký bean | Có, hoặc dùng cơ chế binder trong test có chủ đích |
| Integration test outbound gateway | Tương tác API và cấu hình client | Thường cần test environment / mock server |

Nhờ phân chia, khi test thất bại sẽ dễ biết lỗi thuộc về **cấu hình**, **wiring bean** hay **logic nghiệp vụ**.

## 17. Có nên đưa phương thức tính toán vào lớp properties?

Một record thuần dữ liệu vẫn có thể có phương thức dẫn xuất nhỏ nếu nó thực sự là đặc tính tự nhiên của cấu hình. Chẳng hạn:

```java
@ConfigurationProperties(prefix = "shipping")
public record ShippingProperties(
        URI baseUrl,
        Duration connectTimeout
) {
    public URI shipmentsUri() {
        return baseUrl.resolve("v1/shipments");
    }
}
```

Việc tính URI từ giá trị đã có là phép biến đổi thuần túy, không gọi service khác. Cách này có thể hợp lý nếu nhiều thành phần cần cùng phép biến đổi và quy ước URL đã ổn định.

Nhưng nên cân nhắc khi phương thức bắt đầu:

- Gọi API ngoài để tìm endpoint.
- Đọc database để xác định chính sách giao hàng.
- Truy cập security context của người dùng.
- Ghi file hoặc cập nhật cache.
- Lựa chọn quy trình nghiệp vụ có nhiều nhánh.

Những hành vi đó không còn là “giá trị cấu hình”; chúng thuộc về service, adapter hoặc thành phần chuyên trách.

Một tiêu chí đơn giản: **Properties có thể được tạo bằng `new` và hiểu được mà không cần Spring hay môi trường bên ngoài.** Nếu phải có cả repository, clock, HTTP client và transaction manager để khởi tạo properties, ranh giới có khả năng đã sai.

## 18. Khi một bean cần cấu hình nhưng không thể sửa mã nguồn của nó

Nhiều thư viện cung cấp class hạ tầng mà ứng dụng không sở hữu. Trong những trường hợp như vậy, ta có thể dùng một `@Bean` làm adapter cấu hình:

```java
@Configuration
public class ThirdPartyConfiguration {

    @Bean
    SomeThirdPartyClient thirdPartyClient(
            ThirdPartyProperties properties) {
        return SomeThirdPartyClient.builder()
                .endpoint(properties.endpoint())
                .timeout(properties.timeout())
                .build();
    }
}
```

`SomeThirdPartyClient` và `ThirdPartyProperties` ở đây là các kiểu minh họa. Ý chính là **để lớp properties giữ dữ liệu**, còn phương thức bean tạo object thư viện bằng API public của thư viện đó.

Trong Spring Boot còn có thể dùng `@ConfigurationProperties` trực tiếp trên một phương thức `@Bean` khi muốn binder điền các thuộc tính vào một JavaBean của thư viện bên thứ ba có API setter phù hợp. Đó là một tình huống riêng, có điều kiện về khả năng binding của class đích; không đồng nghĩa với việc phải tiêm service vào constructor của properties record.

Khi thư viện dùng builder và yêu cầu đồng thời những bean cộng tác khác, phương thức `@Bean` rõ ràng như ví dụ thường cho khả năng kiểm soát tốt hơn.

## 19. Khi cấu hình thay đổi trong lúc ứng dụng chạy

Thông thường, `ShippingProperties` được binding trong quá trình khởi tạo application context; `HttpClient` cũng được dựng từ giá trị timeout tại thời điểm tạo bean.

Giả sử người vận hành sửa `shipping.connect-timeout` từ `2s` sang `500ms` trong file ngoài JAR sau khi tiến trình đã khởi động. Không thể mặc định rằng:

- `ShippingProperties.connectTimeout()` tự nhận giá trị mới.
- `HttpClient` đang tồn tại tự đổi thời gian chờ.
- Mọi bean nghiệp vụ đang giữ tham chiếu cũ tự được làm mới.

Một ứng dụng Spring Boot thông thường cần khởi động lại để áp dụng thay đổi cấu hình theo cách dễ kiểm soát. Nếu cần refresh cấu hình động, phải thiết kế rõ cơ chế cập nhật object properties, khởi tạo lại bean hạ tầng và xử lý các yêu cầu đang chạy.

Điều này cũng liên quan đến tính bất biến của record: record thuận tiện vì các giá trị được cố định sau khi tạo. Nếu yêu cầu ứng dụng cập nhật liên tục mà không khởi động lại, cần một mô hình quản lý trạng thái rõ ràng, không nên âm thầm gán lại các trường properties từ nhiều thread.

## 20. Các lỗi phổ biến khi phân tách cấu hình

### 20.1. Vừa @ConfigurationProperties vừa @Component trên record

`@Component` đưa class vào component scanning theo cơ chế bean thông thường, trong khi record `@ConfigurationProperties` muốn Spring Boot binder gắn tham số constructor với các thuộc tính ngoài. Với constructor binding, nên đăng ký record qua `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan` như ví dụ, thay vì trông chờ vào `@Component`.

### 20.2. Tiêm repository/HttpClient vào constructor của properties

`@ConfigurationProperties` không phải service locator. Tham số `URI`, `Duration`, `boolean` là dữ liệu cấu hình; `Repository` hoặc `HttpClient` là phụ thuộc bean. Hãy tạo chúng trong `@Configuration` hoặc inject thẳng vào service cần dùng.

### 20.3. Service tự đọc lại Environment dù đã có properties

Nếu service đã nhận `ShippingProperties` nhưng vẫn gọi `environment.getProperty("shipping.max-attempts")`, ứng dụng có **hai con đường truy cập một giá trị**. Điều này làm khó việc kiểm thử và đôi khi tạo chênh lệch nếu một con đường có fallback riêng. Dùng một hợp đồng rõ ràng, trừ khi có lý do kỹ thuật thật sự cần đọc động.

### 20.4. Đưa toàn bộ nghiệp vụ vào properties

`ShippingProperties` nên chứa thời gian chờ và giới hạn thử lại, không nên gọi API để tạo vận đơn hoặc quyết định hoàn tiền. Chọn tên lớp sát vai trò: `ShippingProperties` cho dữ liệu; `ShippingService` cho nghiệp vụ; `ShippingClient` cho giao tiếp.

### 20.5. Chia quá nhiều record rất nhỏ không có lý do

Nếu mỗi thuộc tính nằm trong một class riêng, việc đọc và wiring trở nên rườm rà. Nên nhóm những giá trị cùng vòng đời và cùng miền ý nghĩa. Không có quy tắc bắt buộc “mỗi thuộc tính một lớp”; mục tiêu là **ranh giới dễ hiểu**, không phải số lượng lớp tối đa.

### 20.6. Trộn mật khẩu thật vào file đã commit

Cấu hình ngoài không có nghĩa mọi dữ liệu đều an toàn để lưu trong repository. Profile và `@ConfigurationProperties` không mã hóa secret. Cần sử dụng kênh cấp bí mật phù hợp và tránh log toàn bộ properties.

### 20.7. Nghĩ cấu hình từ YAML luôn thắng

Tham số dòng lệnh, biến môi trường, config ngoài JAR, cấu hình kiểm thử và các nguồn khác có thể có ưu tiên khác nhau. Binder đọc giá trị có hiệu lực, không nhất thiết lấy giá trị hiển thị trong một file YAML cụ thể.

### 20.8. Quên xác thực các ràng buộc nghiệp vụ

Chuyển được `"-3"` sang `int -3` không làm `maxAttempts=-3` trở thành cấu hình hợp lệ. Dùng validation khi binding và kiểm tra tính nhất quán giữa các tham số nếu cần.

### 20.9. Tạo vòng giữa service và cấu hình hạ tầng

Nếu `ShippingService` cần `HttpClient`, còn phương thức tạo `HttpClient` lại gọi `ShippingService` để hỏi timeout, ta tạo phụ thuộc vòng. Cách giải quyết là cho phương thức tạo client dùng trực tiếp `ShippingProperties`, không đi vòng qua service.

## 21. Quy trình thiết kế khi thêm một nhóm cấu hình mới

Khi có yêu cầu “tích hợp đối tác mới với timeout, URL và retry”, có thể thực hiện theo thứ tự:

1. **Liệt kê dữ liệu vận hành:** endpoint, timeouts, flags, giới hạn thử lại.
2. **Đặt một prefix nhất quán:** ví dụ `partner.orders.*`, chọn tên kebab-case dễ đọc.
3. **Tạo một class `@ConfigurationProperties` có kiểu:** dùng `URI`, `Duration`, `int` thay vì để mọi thứ là `String`.
4. **Đăng ký class với Boot Binder:** dùng `@EnableConfigurationProperties` hoặc `@ConfigurationPropertiesScan`.
5. **Đặt mặc định ở một nơi có chủ đích:** cấu hình chung hoặc mặc định của binder, tránh nhiều nguồn mặc định mâu thuẫn.
6. **Kiểm tra tính hợp lệ:** khóa bắt buộc và phạm vi giá trị.
7. **Lắp ráp bean hạ tầng trong `@Configuration`:** ví dụ HTTP client, message producer, executor.
8. **Inject object cấu hình và cộng tác viên vào service qua constructor.**
9. **Unit test service bằng object tạo trực tiếp; test binding trong một test khác.**
10. **Thử một lần chạy với override ở nguồn ưu tiên cao hơn**, để chứng minh không phải sửa Java khi đổi môi trường.

Sơ đồ trách nhiệm:

```text
Tên khóa + giá trị
        |
        v
  ShippingProperties
        |
        +-----------------------+
        |                       |
        v                       v
InfrastructureConfiguration   ShippingService
        |                       ^
        v                       |
    HttpClient -----------------+
        |
        v
  Không chứa logic nghiệp vụ
```

Cấu trúc này giúp các thành phần có thể thay đổi tương đối độc lập: cấu hình có thể được cấp từ môi trường mới, client có thể được cấu hình thêm proxy, còn service có thể thay đổi chính sách xử lý mà không phải chỉnh cách đọc YAML.

## 22. Bài tập thực hành

### Bài tập 1: tách một service đang dùng @Value

Cho:

```java
@Service
public class ImportService {

    @Value("${import.enabled:true}")
    private boolean enabled;

    @Value("${import.batch-size:100}")
    private int batchSize;

    @Value("${import.storage-url}")
    private String storageUrl;
}
```

Hãy tạo `ImportProperties` với prefix `import`, dùng `boolean`, `int` và `URI`, đăng ký bằng `@EnableConfigurationProperties` rồi chuyển `ImportService` sang constructor injection.

Khi làm xong, `ImportService` không còn biết ba tên khóa văn bản và không cần tự chuyển URL sang `URI`.

### Bài tập 2: tạo bean cần cả properties và Clock

Giả sử một thành phần `BatchScheduler` cần `ImportProperties` và `Clock`. Hãy đặt `Clock` vào một `@Configuration` riêng, sau đó inject hai phụ thuộc vào `BatchScheduler`.

Đừng thêm `Clock` vào record `ImportProperties` chỉ để lấy giờ hệ thống. Đồng hồ là bean cộng tác, không phải dữ liệu cấu hình.

### Bài tập 3: thay bean hạ tầng mà không sửa service

Tạo một interface:

```java
public interface DeliveryGateway {
    String sendPreview(String orderId);
}
```

Có thể tạo một implementation thật và một implementation fake trong hai class khác nhau. `ShippingService` chỉ phụ thuộc vào `DeliveryGateway` và `ShippingProperties`. Trong unit test, inject fake gateway để kiểm tra quyết định của service mà không cần gọi mạng.

Điều cần chứng minh là service không phải tạo trực tiếp adapter HTTP hoặc đọc YAML để biết implementation đang dùng.

### Bài tập 4: ràng buộc sai giá trị

Cấp lần lượt:

```properties
shipping.max-attempts=0
shipping.connect-timeout=-1s
shipping.base-url=
```

Xác định điều kiện nào bị phát hiện bởi type conversion, điều kiện nào cần Bean Validation, và điều kiện nào cần một quy tắc nghiệp vụ riêng. Không kỳ vọng mọi trường hợp đều được sửa bằng giá trị mặc định.

### Bài tập 5: source override

Giữ `shipping.max-attempts=3` trong YAML, rồi khởi chạy với:

```bash
java -jar app.jar --shipping.max-attempts=7
```

Dự đoán giá trị `ShippingProperties.maxAttempts()` và giá trị mà `ShippingService.preview()` hiển thị. Giải thích vì sao service không cần biết đối số dòng lệnh đã được truyền.

### Bài tập 6: nhận diện trách nhiệm

Phân loại những yêu cầu sau:

| Việc cần làm | Nên đặt ở đâu? |
| --- | --- |
| Khai báo endpoint | `@ConfigurationProperties` |
| Chuyển chuỗi `2s` thành `Duration` | Spring Boot Binder |
| Tạo client có timeout 2 giây | `@Configuration` hoặc client factory |
| Kiểm tra đơn hàng có đủ địa chỉ | Service nghiệp vụ |
| Gọi API vận chuyển | Gateway/client adapter |
| Giả lập thời gian trong unit test | `Clock` fake/fixed trong test |
| Đổi endpoint giữa staging và prod | Nguồn cấu hình ngoài |
| Chọn chính sách retry theo lỗi | Service hoặc retry policy |
| Xác minh `maxAttempts >= 1` | Validation cấu hình |

Mục tiêu không phải ghi nhớ một cấu trúc thư mục cố định, mà là nhận ra ranh giới dữ liệu – lắp ráp – hành vi.

## 23. Tổng kết

`@ConfigurationProperties` được dùng để **đại diện cho một nhóm giá trị cấu hình** dưới một prefix, với kiểu Java cụ thể và khả năng validation tập trung. Nó tạo một hợp đồng rõ ràng giữa nguồn cấu hình ngoài ứng dụng và code tiêu thụ những giá trị đó.

Một thiết kế tách trách nhiệm sẽ có luồng:

```text
Nguồn cấu hình (application.yml, env, CLI...)
             |
             v
         Boot Binder
             |
             v
     ShippingProperties
             |
      +------+------+
      |             |
      v             v
Tạo HttpClient   ShippingService <--- Clock bean
      |             ^
      +-------------+
                    |
                    v
            Xử lý nghiệp vụ
```

Hãy nhớ ba phân biệt quan trọng:

1. **Configuration properties không phải service:** nó mô tả dữ liệu, không thay thế xử lý nghiệp vụ.
2. **Configuration properties không phải nơi inject mọi bean khác:** việc kết hợp properties với `HttpClient`, `Clock` hay repository thuộc về `@Configuration`, service hoặc factory chuyên trách.
3. **Cùng một service có thể chạy ở nhiều môi trường:** binder giải quyết các nguồn cấu hình theo ưu tiên, tạo object có kiểu, và Spring container cấp object đó cho service mà không phải thay logic Java.

Khi tăng số lượng thuộc tính hoặc bean cộng tác, nên tách các nhóm theo miền ý nghĩa, định nghĩa ranh giới rõ ràng, dùng constructor injection, validation phù hợp và kiểm thử binding riêng với nghiệp vụ. Đây là giá trị kiến trúc lớn nhất của `@ConfigurationProperties`: không chỉ “đọc được YAML”, mà còn giúp ứng dụng **dễ thay cấu hình, dễ thay hạ tầng, dễ kiểm thử và dễ bảo trì**.

Tài liệu tham khảo để học tiếp: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties), và [Spring Framework — Bean Definitions](https://docs.spring.io/spring-framework/reference/core/beans/definition.html).