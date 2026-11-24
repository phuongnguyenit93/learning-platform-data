# Phạm vi bật nhóm cấu hình và lựa chọn theo từng Feign client

Một ứng dụng Spring có thể khai báo nhiều Feign client để gọi các dịch vụ như tồn kho, thanh toán, vận chuyển và khách hàng. Các client thường dùng chung một số thiết lập như log level hoặc decoder, nhưng cũng có thể cần timeout, interceptor, retry policy và fallback khác nhau. Nếu cấu hình không đúng phạm vi, một thay đổi dành cho client tồn kho có thể vô tình ảnh hưởng đến client thanh toán hoặc mọi Feign client trong ứng dụng.

Spring Cloud OpenFeign tổ chức cấu hình theo từng client bằng một context riêng. `@EnableFeignClients` xác định nhóm client được đăng ký và có thể cung cấp cấu hình mặc định cho nhóm đó; `@FeignClient(configuration = ...)` bổ sung cấu hình riêng cho một client. Khi bật tích hợp Spring Cloud CircuitBreaker, ứng dụng còn có thể lựa chọn fallback và chính sách circuit breaker theo client, đồng thời bật hỗ trợ group nếu cần gom các phương thức của cùng client.

## 1. Phân biệt phạm vi quét client và phạm vi cấu hình

`@EnableFeignClients` quyết định Spring tìm và đăng ký những interface nào có `@FeignClient`. Có thể giới hạn phạm vi bằng `basePackages`, `basePackageClasses` hoặc liệt kê tường minh bằng `clients`.

```java
import org.springframework.cloud.openfeign.EnableFeignClients;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableFeignClients(
    basePackages = {
        "com.example.inventory.client",
        "com.example.payment.client"
    }
)
public class FeignClientsConfiguration {
}
```

Trong ví dụ, chỉ các interface Feign nằm trong hai package đã khai báo được đăng ký bởi cấu hình này. Nếu dùng `basePackages` quá rộng, ứng dụng có thể vô tình đăng ký client từ các package không thuộc phạm vi mong muốn. Với ứng dụng lớn, có thể dùng `basePackageClasses` để tránh phụ thuộc vào chuỗi tên package hoặc `clients` để liệt kê chính xác các interface cần đăng ký.

Phạm vi quét không đồng nghĩa với phạm vi áp dụng bean cấu hình. `basePackages` chọn interface Feign; `defaultConfiguration` và thuộc tính `configuration` chọn nguồn cấu hình được dùng khi tạo client.

## 2. Cấu hình mặc định cho một nhóm Feign client

Thuộc tính `defaultConfiguration` của `@EnableFeignClients` cung cấp cấu hình mặc định cho các Feign client được đăng ký thông qua annotation đó:

```java
@Configuration(proxyBeanMethods = false)
@EnableFeignClients(
    basePackages = "com.example.client",
    defaultConfiguration = DefaultFeignConfiguration.class
)
public class FeignClientRegistration {
}
```

Ví dụ lớp cấu hình mặc định:

```java
import feign.Logger;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DefaultFeignConfiguration {

    @Bean
    Logger.Level feignLoggerLevel() {
        return Logger.Level.BASIC;
    }
}
```

Trong trường hợp này, các client thuộc phạm vi đăng ký dùng log level `BASIC`, trừ khi có cấu hình riêng ghi đè. Có thể đặt các bean dùng chung khác tại đây nếu chúng thực sự phù hợp với mọi client trong nhóm, chẳng hạn decoder hoặc interceptor tiêu chuẩn.

Không nên đưa chính sách đặc thù của một dịch vụ vào cấu hình mặc định. Ví dụ, interceptor gắn token riêng cho dịch vụ thanh toán không nên được áp dụng cho client tồn kho nếu hai dịch vụ có cơ chế xác thực khác nhau.

## 3. Cấu hình riêng cho từng Feign client

Thuộc tính `configuration` của `@FeignClient` chỉ định lớp cấu hình cho client đó. Ví dụ, hai client có thể dùng cùng service discovery name nhưng cần cấu hình độc lập:

```java
import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient",
    configuration = InventoryReadFeignConfiguration.class
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryAdminClient",
    configuration = InventoryAdminFeignConfiguration.class
)
public interface InventoryAdminClient {
    void reserveStock(String sku, int quantity);
}
```

Hai interface cùng gọi `inventory-service`, nhưng có `contextId` khác nhau và có thể dùng cấu hình riêng. `name` xác định dịch vụ đích hoặc tên client dùng trong load balancing; `contextId` xác định định danh cấu hình của client ensemble và giúp tránh xung đột khi có nhiều client cùng `name`.

Ví dụ lớp cấu hình riêng cho client đọc tồn kho:

```java
import feign.Logger;
import feign.Retryer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class InventoryReadFeignConfiguration {

    @Bean
    Logger.Level inventoryLoggerLevel() {
        return Logger.Level.BASIC;
    }

    @Bean
    Retryer inventoryRetryer() {
        return Retryer.NEVER_RETRY;
    }
}
```

Client đọc tồn kho có thể dùng log level `BASIC` và không retry ở Feign layer. Client quản trị có thể dùng một cấu hình khác, ví dụ timeout ngắn hơn hoặc interceptor riêng. Hãy chỉ đặt bean trong lớp cấu hình riêng khi bean đó thực sự cần khác biệt so với mặc định.

### Tránh cấu hình riêng bị quét thành cấu hình toàn cục

Lớp được tham chiếu bởi `@FeignClient(configuration = ...)` có thể được đánh dấu `@Configuration`, nhưng cần tránh để nó bị component scan của ứng dụng chính phát hiện như cấu hình toàn cục. Nếu lớp này lọt vào application context cha, các bean như `Encoder`, `Decoder`, `Contract`, `Retryer` hoặc `RequestInterceptor` có thể trở thành mặc định cho nhiều Feign client khác.

Có thể đặt các lớp cấu hình Feign riêng ở package nằm ngoài vùng component scan chính, hoặc điều chỉnh phạm vi scan để chúng chỉ được nạp thông qua cấu hình của client tương ứng. Đây là một trong những lỗi phạm vi thường gặp nhất khi tổ chức nhiều Feign client.

## 4. Dùng contextId để tách cấu hình khi cùng gọi một dịch vụ

`name` và `contextId` không có cùng mục đích. Một dịch vụ có thể có nhiều client với hợp đồng khác nhau: client đọc dữ liệu, client quản trị hoặc client nội bộ. Khi cùng dùng `name = "inventory-service"`, nên đặt `contextId` riêng để cấu hình và bean ensemble không xung đột.

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| `name` | Tên dịch vụ hoặc định danh đích của Feign client. | `inventory-service` |
| `contextId` | Định danh cấu hình riêng của client ensemble. | `inventoryReadClient` |
| `configuration` | Lớp cấu hình bổ sung cho client cụ thể. | `InventoryReadFeignConfiguration.class` |
| `fallback` / `fallbackFactory` | Lớp dự phòng gắn với client cụ thể. | `InventoryReadFallbackFactory.class` |

Khi cấu hình properties riêng, dùng đúng khóa client mà OpenFeign resolve. Với client có `contextId`, nên dùng chính định danh `contextId` làm tên cấu hình trong `spring.cloud.openfeign.client.config` để phân biệt các client cùng `name`.

## 5. Cấu hình properties mặc định và theo từng client

Spring Cloud OpenFeign cho phép khai báo cấu hình mặc định bằng khóa `default` và ghi đè theo từng client:

```yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          default:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
          inventoryReadClient:
            connectTimeout: 300
            readTimeout: 800
            loggerLevel: full
          paymentClient:
            connectTimeout: 500
            readTimeout: 2000
            loggerLevel: basic
```

Trong ví dụ:

- `default` đặt timeout và log level nền cho các client.
- `inventoryReadClient` ghi đè timeout và log level cho client đọc tồn kho.
- `paymentClient` có thời gian đọc dài hơn vì phụ thuộc có thể cần xử lý giao dịch lâu hơn.

Tên khóa sau `config` phải khớp với định danh client mà OpenFeign sử dụng; khi đã khai báo `contextId`, hãy dùng định danh đó nhất quán. Các giá trị timeout trong ví dụ tính bằng mili giây. Đặt giá trị theo ngân sách độ trễ thực tế và tránh để `readTimeout` dài hơn deadline mà caller cho phép.

Properties có thể cấu hình nhiều thành phần của Feign client như `connectTimeout`, `readTimeout`, `loggerLevel`, `errorDecoder`, `retryer`, `requestInterceptors`, `defaultRequestHeaders`, `defaultQueryParameters`, `dismiss404` và các tùy chọn hỗ trợ khác tùy phiên bản Spring Cloud OpenFeign. Kiểm tra tài liệu của release train đang dùng trước khi sử dụng một thuộc tính mới.

## 6. Thứ tự ưu tiên giữa properties và Java configuration

Mặc định, cấu hình properties có thể ghi đè bean được khai báo trong lớp cấu hình Java của Feign client. Điều này giúp thay đổi timeout hoặc log level theo môi trường mà không cần sửa mã.

Có thể thay đổi thứ tự ưu tiên bằng:

```yaml
spring:
  cloud:
    openfeign:
      client:
        default-to-properties: false
```

Khi `default-to-properties` là `false`, cấu hình Java được ưu tiên theo cơ chế của Spring Cloud OpenFeign. Hãy chọn một quy ước nhất quán cho toàn ứng dụng và ghi rõ cấu hình nào là nguồn có thẩm quyền. Nếu cùng một thuộc tính được khai báo ở cả YAML và Java mà nhóm phát triển không biết nguồn nào thắng, việc điều tra cấu hình runtime sẽ khó khăn.

Không nên sao chép cùng một giá trị vào cả hai nơi nếu không cần thiết. Cấu hình thay đổi theo môi trường thường phù hợp với properties; cấu hình tạo bean hoặc logic tùy chỉnh phức tạp phù hợp với Java configuration.

## 7. Bật tích hợp CircuitBreaker cho Feign

Spring Cloud OpenFeign có thể tích hợp Spring Cloud CircuitBreaker để bọc lời gọi Feign. Bật tính năng bằng thuộc tính:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
```

Khi bật, các lời gọi Feign được tạo qua tích hợp này có thể đi qua circuit breaker. Cần có provider Spring Cloud CircuitBreaker tương ứng trên classpath, ví dụ starter Resilience4j. Nếu chưa bật `spring.cloud.openfeign.circuitbreaker.enabled`, việc chỉ khai báo `fallback` hoặc `fallbackFactory` không tự động bảo đảm lời gọi được bọc bởi circuit breaker.

Đây là công tắc cấp ứng dụng cho tích hợp OpenFeign-CircuitBreaker. Việc lựa chọn cấu hình và fallback vẫn có thể thực hiện theo từng Feign client bằng annotation và cấu hình tương ứng. Không nên giả định có một thuộc tính `enabled` độc lập cho từng client nếu phiên bản đang dùng không cung cấp cơ chế đó.

## 8. Bật hỗ trợ group cho các phương thức của cùng Feign client

Theo mặc định, OpenFeign tích hợp circuit breaker theo định danh của từng lời gọi. Có thể bật hỗ trợ group để factory nhận thêm tên nhóm tương ứng với Feign client:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
        group:
          enabled: true
```

Khi group support được bật, Spring Cloud OpenFeign có thể cung cấp tên client làm group name khi tạo circuit breaker. Điều này hữu ích khi muốn tổ chức các phương thức thuộc cùng Feign client dưới một nhóm cấu hình hoặc nhóm quản lý chung, trong khi định danh circuit breaker của từng phương thức vẫn có thể riêng.

Group support không đồng nghĩa tất cả phương thức trong client tự động dùng chung một trạng thái circuit breaker. Tên circuit breaker, group name và cách provider áp dụng cấu hình group là các khái niệm riêng. Cần kiểm tra cách provider đang dùng diễn giải `id` và `groupName`, đặc biệt khi cấu hình Resilience4j cho từng instance hoặc group.

Ví dụ cấu hình Resilience4j có cấu hình nền và instance:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      feignDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventoryReadClient:
        baseConfig: feignDefault
      paymentClient:
        baseConfig: feignDefault
        failureRateThreshold: 40
```

Đoạn cấu hình minh họa việc tái sử dụng cấu hình nền và điều chỉnh riêng cho một instance. Tên instance phải khớp với circuit breaker ID thực tế được tạo ra. Tên đó có thể phụ thuộc vào quy tắc đặt tên của OpenFeign và `CircuitBreakerNameResolver`; không nên suy ra tên chỉ từ interface Java nếu chưa kiểm tra quy tắc của phiên bản đang chạy.

## 9. Đặt fallback hoặc fallbackFactory cho từng Feign client

Fallback được khai báo ngay trên `@FeignClient`, do đó có thể chọn phương án dự phòng riêng cho từng client:

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient",
    configuration = InventoryReadFeignConfiguration.class,
    fallbackFactory = InventoryReadFallbackFactory.class
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

Ví dụ `FallbackFactory` nhận nguyên nhân lỗi:

```java
import org.springframework.cloud.openfeign.FallbackFactory;
import org.springframework.stereotype.Component;

@Component
public class InventoryReadFallbackFactory
        implements FallbackFactory<InventoryReadClient> {

    @Override
    public InventoryReadClient create(Throwable cause) {
        return sku -> {
            // Ghi nhận nguyên nhân có kiểm soát và trả trạng thái dự phòng.
            return Stock.unavailable(sku);
        };
    }
}
```

`fallbackFactory` hữu ích khi cần phân biệt timeout, lỗi kết nối và `CallNotPermittedException`. Nếu chỉ cần trả một kết quả dự phòng cố định, có thể dùng thuộc tính `fallback` với một bean triển khai interface. Chọn một trong hai cơ chế theo nhu cầu; không khai báo cả `fallback` và `fallbackFactory` cho cùng client.

Fallback cần giữ đúng ngữ nghĩa nghiệp vụ. Ví dụ, `Stock.unavailable` phải cho caller biết dữ liệu tồn kho hiện không sẵn có; không trả số lượng bằng 0 nếu chưa truy vấn được dịch vụ đích. Với thao tác ghi như thanh toán hoặc đặt hàng, không trả thành công giả khi chưa biết dịch vụ đã xử lý giao dịch hay chưa.

## 10. Tên CircuitBreaker và phạm vi theo phương thức

Khi bật CircuitBreaker cho OpenFeign, tên circuit breaker thường được tạo từ client và phương thức. Quy tắc đặt tên mặc định có thể thay đổi theo phiên bản Spring Cloud và có thể được tùy chỉnh bằng `CircuitBreakerNameResolver`.

Điều này có nghĩa một Feign client có nhiều phương thức có thể tạo nhiều circuit breaker ID riêng. Bật group support bổ sung group name cho client; nó không nhất thiết gộp mọi method vào một breaker duy nhất. Khi cần cấu hình Resilience4j theo instance, hãy kiểm tra tên ID thực tế bằng log, metrics hoặc cấu hình resolver.

Một số phiên bản hỗ trợ tùy chọn chuyển tên breaker sang dạng chỉ gồm ký tự chữ và số:

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        alphanumeric-ids:
          enabled: true
```

Tùy chọn này hữu ích khi tên mặc định có dấu chấm, dấu ngoặc hoặc ký tự không phù hợp với quy ước tên instance của cấu hình provider. Chỉ bật khi phiên bản OpenFeign đang dùng hỗ trợ thuộc tính đó; sau khi bật, cập nhật khóa instance Resilience4j theo tên mới và kiểm tra metrics để bảo đảm mapping chính xác.

## 11. Ví dụ tổng hợp: hai client cùng service nhưng khác chính sách

Giả sử ứng dụng có client đọc tồn kho và client quản trị tồn kho. Cả hai gọi cùng `inventory-service`, nhưng client đọc cần timeout ngắn và fallback dữ liệu tạm thời; client quản trị thực hiện lệnh ghi nên không được retry tùy tiện.

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient",
    configuration = InventoryReadFeignConfiguration.class,
    fallbackFactory = InventoryReadFallbackFactory.class
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryAdminClient",
    configuration = InventoryAdminFeignConfiguration.class
)
public interface InventoryAdminClient {
    void reserveStock(String sku, int quantity);
}
```

```yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
        group:
          enabled: true
      client:
        config:
          inventoryReadClient:
            connectTimeout: 300
            readTimeout: 800
            loggerLevel: basic
          inventoryAdminClient:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
```

Trong thiết kế này:

- Cả hai client đều được đăng ký và có thể dùng tích hợp CircuitBreaker toàn ứng dụng.
- `contextId` tách riêng cấu hình và định danh client ensemble dù cùng `name`.
- Timeout được đặt riêng theo từng client.
- FallbackFactory chỉ gắn với client đọc tồn kho.
- Client quản trị cần chính sách ghi an toàn, idempotency và xử lý lỗi rõ ràng; không tự động retry thao tác reserve nếu chưa có cơ chế chống trùng.

Nếu cấu hình CircuitBreaker theo instance Resilience4j, hãy xác định ID thực tế do resolver tạo cho từng phương thức và dùng đúng ID đó. Nếu cần một chính sách chung cho cả client, group support có thể giúp tổ chức cấu hình theo client; cần kiểm tra provider áp dụng group ra sao trong phiên bản dự án.

## 12. Những lỗi phạm vi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Bean cấu hình của một client ảnh hưởng tất cả client | Lớp cấu hình riêng bị component scan vào application context cha. | Đưa lớp ra ngoài component scan hoặc giới hạn phạm vi scan. |
| Hai client cùng `name` bị xung đột cấu hình | Không đặt `contextId` riêng. | Gán `contextId` khác nhau cho từng client ensemble. |
| Properties riêng không được áp dụng | Khóa YAML không khớp định danh client mà OpenFeign resolve. | Kiểm tra `name`/`contextId` và dùng khóa tương ứng. |
| Java config bị YAML ghi đè | `default-to-properties` đang bật theo mặc định. | Xác định nguồn cấu hình mong muốn và đặt thuộc tính ưu tiên có chủ đích. |
| Fallback không được gọi | Chưa bật CircuitBreaker integration, thiếu provider hoặc fallback không được đăng ký thành bean. | Kiểm tra starter, `spring.cloud.openfeign.circuitbreaker.enabled` và bean fallback. |
| Cấu hình Resilience4j không khớp breaker | Dùng sai ID hoặc chưa tính đến resolver/alphanumeric IDs. | Quan sát tên breaker thực tế rồi cập nhật khóa instance. |
| Group config không có tác dụng như kỳ vọng | Nhầm group name với circuit breaker ID hoặc provider không áp dụng group theo cách giả định. | Kiểm tra `create(id, groupName)` và tài liệu provider đang dùng. |

## 13. Kiểm tra phạm vi trước khi phát hành

Trước khi đưa cấu hình OpenFeign và CircuitBreaker vào môi trường thật, hãy kiểm tra:

- [ ] `@EnableFeignClients` chỉ quét package hoặc danh sách client cần thiết.
- [ ] `defaultConfiguration` chỉ chứa bean thực sự dùng chung cho nhóm client.
- [ ] Mỗi client cần chính sách riêng có `configuration` rõ ràng.
- [ ] Lớp cấu hình riêng không bị component scan thành cấu hình toàn cục.
- [ ] Các client cùng `name` có `contextId` riêng.
- [ ] Khóa `spring.cloud.openfeign.client.config` khớp định danh client.
- [ ] Thứ tự ưu tiên giữa properties và Java configuration đã được xác định.
- [ ] CircuitBreaker integration được bật và provider tương ứng có mặt.
- [ ] Group support chỉ được bật khi cần dùng group name.
- [ ] Fallback hoặc FallbackFactory gắn đúng client và trả kết quả có ý nghĩa nghiệp vụ.
- [ ] Resilience4j instance ID khớp tên breaker thực tế.
- [ ] Retry của Gateway, Feign và SDK không nhân số attempt ngoài ngân sách.

Tổ chức cấu hình theo đúng phạm vi giúp ứng dụng có chính sách chung nhất quán mà vẫn giữ được khác biệt cần thiết giữa từng Feign client. Hãy dùng `@EnableFeignClients` để giới hạn nhóm được đăng ký, `defaultConfiguration` cho thiết lập nền, `@FeignClient(configuration = ...)` và `contextId` cho từng client, rồi bật CircuitBreaker/group support có chủ đích. Sau cùng, xác minh tên breaker, properties, fallback và metrics ở runtime để chắc chắn cấu hình đang áp dụng đúng nơi.
