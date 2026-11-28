# Tránh bật dữ liệu debug nhạy cảm ở production

## 1. Vì sao observability có thể trở thành nguồn rò rỉ dữ liệu?

Spring Modulith hỗ trợ tổ chức ứng dụng Spring Boot thành các application module rõ ràng, sinh tài liệu **module graph**, kiểm chứng ranh giới và kết hợp với cơ chế quan sát để theo dõi tương tác giữa module. Trong quá trình phát triển, lập trình viên thường bật log chi tiết, Actuator, event tracing hoặc ghi lại toàn bộ payload để tìm lỗi. Nếu những thiết lập này đi vào production, dữ liệu vốn chỉ nên tồn tại trong hệ thống có thể bị ghi vào log, trace, metric, dashboard hoặc endpoint quản trị.

Ví dụ, một hệ thống gồm các module `ordering`, `payment` và `notification` có thể phát sự kiện `PaymentAuthorized`. Nếu event chứa email khách hàng, mã giao dịch, nội dung thanh toán hoặc token xác thực, câu lệnh `log.debug("event={}", event)` có thể vô tình đưa toàn bộ dữ liệu đó đến kho log dùng chung. Một span trace gắn `customer.email` làm thuộc tính cũng đưa dữ liệu sang hệ thống theo dõi phân tán. Việc gửi trace ở tỷ lệ nhỏ hơn không làm dữ liệu đã gửi trở nên an toàn.

Mục tiêu của chủ đề **“Tránh bật dữ liệu debug nhạy cảm ở production”** trong phần **Cấu hình môi trường** là xác định ranh giới an toàn cho việc quan sát hệ thống thật. Cần trả lời ba câu hỏi trước khi bật một cơ chế debug:

1. **Dữ liệu gì có thể xuất hiện?** Token, mật khẩu, dữ liệu cá nhân, payload event, header HTTP, thông tin kiến trúc, tên package hoặc thông tin cấu hình.
2. **Ai có thể nhìn thấy nó và trong bao lâu?** Người truy cập endpoint, nhóm vận hành, bên nhận telemetry, công cụ phân tích, hệ thống lưu trữ, đối tác monitoring.
3. **Có cách ít nhạy cảm hơn để chẩn đoán cùng vấn đề không?** Mã tương quan ngẫu nhiên, loại sự kiện, trạng thái xử lý, module nguồn/đích, latency, lỗi đã phân loại.

Trong module học `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`, cách làm phù hợp là **thu đủ tín hiệu để phát hiện lỗi kiến trúc và vận hành**, đồng thời hạn chế dữ liệu nhạy cảm trong module graph, Actuator, event metrics, tracing và context propagation.

## 2. Nhận diện bề mặt có thể lộ thông tin

Không chỉ log mới gây rủi ro. Dữ liệu debug có thể rời khỏi ứng dụng theo nhiều đường:

| Bề mặt | Dữ liệu có nguy cơ xuất hiện | Cách kiểm soát chính |
| --- | --- | --- |
| Application log | Nội dung request, event, stack trace chứa tham số, token, ID cá nhân | Không ghi payload mặc định; giới hạn log level; lọc trước khi ghi |
| HTTP access/request log | URL chứa query parameter, header xác thực, cookie, request body | Không ghi body/header nhạy cảm; thiết kế URL không chứa secret |
| Actuator `env` / `configprops` | Tên và giá trị property, host, endpoint nội bộ, đôi khi thông tin bí mật | Không expose công khai; giữ giá trị bị ẩn; xác thực và phân quyền |
| Actuator `heapdump` / `logfile` | Vùng nhớ đang chứa token/dữ liệu; log lịch sử | Không đưa ra cổng quản trị công khai; giới hạn người và thời gian truy cập |
| Actuator `mappings` / `beans` / endpoint về module | Cấu trúc endpoint, Bean, package/module và dependency | Chỉ cho nhóm có nhu cầu; kiểm soát mạng và quyền |
| Metric/tag | Email, orderId, requestId, đường dẫn URL động | Chỉ dùng nhãn có cardinality thấp và không nhạy cảm |
| Trace/span/baggage | Tham số nghiệp vụ, user ID, tenant, credential, trace baggage lan qua dịch vụ | Chỉ gắn thuộc tính được phê duyệt; kiểm soát propagation/export |
| Modulith event publication | Nội dung domain event và trạng thái công bố; dữ liệu trong registry | Payload tối thiểu, truy cập registry có kiểm soát, retention phù hợp |
| Tài liệu module graph | Tên module, package, class, quan hệ phụ thuộc nội bộ | Lưu trong kho/tài liệu nội bộ; chỉ xuất bản khi đã review |
| Debug snapshot/support bundle | Cấu hình, dump, log ghép từ nhiều nguồn | Làm sạch và hạn chế chia sẻ theo thời hạn |

Các rủi ro có hai lớp. **Bí mật vận hành** (secret, internal architecture, hostname) có thể hỗ trợ một cuộc tấn công; **dữ liệu khách hàng** có thể vi phạm cam kết bảo mật và làm tăng phạm vi xử lý sự cố. Không nên đánh đồng việc bảo vệ hai loại này với việc chỉ giảm số lượng log.

## 3. Đặt mặc định an toàn theo từng môi trường

Tách rõ cấu hình local, test, staging và production. Production phải nhận một profile được khai báo tường minh khi triển khai, ví dụ `prod` qua biến môi trường `SPRING_PROFILES_ACTIVE=prod`.

Ví dụ `application-prod.yml`:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod

logging:
  level:
    root: INFO
    org.springframework.modulith: INFO
    org.springframework.web: WARN

management:
  endpoints:
    web:
      exposure:
        include: "health"
  endpoint:
    health:
      show-details: never
    env:
      show-values: never
    configprops:
      show-values: never
  tracing:
    sampling:
      probability: 0.05
~~~

Ý nghĩa của mẫu:

- Chỉ công bố HTTP Actuator `health` trong ví dụ cơ bản. Nếu cần `info`, `metrics` hoặc `prometheus`, phải đánh giá độc lập và giới hạn truy cập trước khi thêm vào allowlist.
- Giữ `health.show-details: never` ở endpoint dùng cho kiểm tra liveness công khai; chỉ cần trạng thái tổng thể để hệ thống điều phối biết ứng dụng có đang sẵn sàng không.
- Yêu cầu `env` và `configprops` không hiển thị giá trị property nếu các endpoint này được bật ở nơi khác. Tuy vậy, **ẩn giá trị không thay thế việc hạn chế exposure**.
- Giữ mức log có thể vận hành mà không bật DEBUG/TRACE toàn cục.
- Sampling trace minh họa ở mức 5%. Đây là biện pháp giảm khối lượng telemetry, **không phải biện pháp xóa dữ liệu nhạy cảm**.

Tùy phiên bản Spring Boot/Modulith, tên property và hành vi mặc định có thể khác. Khi nâng cấp framework, hãy xác minh cấu hình có hiệu lực tại runtime và kiểm tra giao diện quản trị thực sự được exposed, thay vì chỉ đọc YAML.

### Tránh đảo ngược ưu tiên cấu hình

Spring Boot có nhiều nguồn property: file cấu hình, profile, biến môi trường, tham số dòng lệnh và nguồn cấu hình ngoài. Một biến được đưa vào pod/container hoặc lệnh startup có thể ghi đè giá trị trong `application-prod.yml`.

Ví dụ deployment cần quản lý nhất quán:

~~~text
SPRING_PROFILES_ACTIVE=prod
APP_RUNTIME_ENVIRONMENT=production
~~~

`APP_RUNTIME_ENVIRONMENT` là biến ứng dụng tự quy định, có thể dùng làm tín hiệu kiểm tra độc lập để phát hiện pod chạy production nhưng quên bật profile. Không được mặc nhiên giả định Spring Boot hiểu biến này như một property bảo mật có sẵn.

Trong pipeline, kiểm tra **cấu hình hiệu lực sau khi khởi động**. Nếu deployment mở `/actuator/env` hoặc bật TRACE vì một override ngoài ý muốn, giá trị đúng trong Git không còn bảo đảm an toàn.

### Một guard kiểm tra profile

Một hệ thống muốn phát hiện sai cấu hình khi khởi động có thể thêm guard minh họa:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

@Component
class ProductionProfileGuard implements ApplicationRunner {

    private final Environment environment;

    ProductionProfileGuard(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String runtime = environment.getProperty(
                "app.runtime.environment", "unknown");

        if ("production".equalsIgnoreCase(runtime)
                && !environment.acceptsProfiles(Profiles.of("prod"))) {
            throw new IllegalStateException(
                    "Production deployment must activate prod profile");
        }
    }
}
~~~

Guard này chỉ minh họa một kiểm tra bổ sung. Nó cần cả tín hiệu `app.runtime.environment` độc lập và quy ước deployment rõ ràng; không thể bảo vệ trường hợp tất cả tín hiệu môi trường đều bị khai báo sai. Nên kết hợp với chính sách CI/CD hoặc kiểm tra cấu hình deployment trước rollout.

## 4. Không đưa cấu hình debug local vào production

Các lựa chọn tiện lợi khi phát triển thường không phù hợp cho dữ liệu thật.

| Trong local/dev | Rủi ro khi dùng trên production | Phương án production |
| --- | --- | --- |
| `logging.level.root=DEBUG` | Ghi quá nhiều tham số, dữ liệu thư viện và thông điệp lỗi | INFO/WARN; chọn logger hẹp và thời hạn khi xử lý sự cố |
| `logging.level.org.springframework=TRACE` | Rất nhiều chi tiết request, bean, security hoặc integration | Chỉ bật có chọn lọc khi đã đánh giá dữ liệu phát ra |
| `spring.mvc.log-request-details=true` | Có thể lộ dữ liệu request/header tùy đường xử lý và logger | Giữ tắt, thu telemetry theo field allowlist |
| `spring.codec.log-request-details=true` | Có thể lộ thông tin request trên stack reactive | Giữ tắt ở hệ thống dữ liệu thật |
| Logging toàn bộ HTTP body | Payload có thể có thông tin khách hàng hoặc credential | Chỉ ghi method, route mẫu, status, duration |
| Expose `/actuator/*` | Mở đường đến dữ liệu vận hành và chức năng quản trị | Exposure allowlist, mạng riêng, phân quyền |
| In event object bằng `toString()` | Phát tán mọi field có trong record/entity | Log loại sự kiện, outcome và mã tương quan an toàn |
| Lưu toàn bộ trace attributes | Lộ định danh người dùng và dữ liệu nghiệp vụ qua exporter | Schema thuộc tính được review; loại PII/token |
| Dump heap/stack tự động ra nơi chia sẻ | Có thể chứa secret và object nhạy cảm | Chỉ dùng trong phiên điều tra có phê duyệt và xử lý an toàn |

Các property trên là ví dụ những **chế độ cần thận trọng**, không phải mọi property luôn ghi toàn bộ dữ liệu. Mức độ lộ phụ thuộc framework, logging configuration, filters và instrumentation thực tế. Kiểm chứng bằng request mẫu không nhạy cảm trong môi trường kiểm thử trước khi kết luận.

## 5. Bảo vệ Actuator và endpoint chứa thông tin kiến trúc

Spring Boot Actuator giúp kiểm tra health, metrics và trạng thái hệ thống. Spring Modulith có thể bổ sung metadata về application modules khi module Actuator tương ứng được tích hợp. Các endpoint này hữu ích cho vận hành nhưng có thể làm lộ package name, cấu trúc Bean, endpoint nội bộ và quan hệ phụ thuộc.

### 5.1. Tư duy allowlist

Khởi đầu production bằng các endpoint thật sự cần:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health"
  endpoint:
    health:
      show-details: never
~~~

Nếu monitoring server cần scrape Prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
~~~

Khi thêm `prometheus`, cần bảo đảm endpoint này chỉ truy cập được từ mạng thu thập metrics hoặc qua cơ chế xác thực đã thiết kế; không chỉ thêm tên vào allowlist. Tương tự, thông tin `info`, `loggers`, `env`, `configprops`, `beans`, `mappings`, `heapdump`, `threaddump` và endpoint cấu trúc module chỉ nên khả dụng khi thực sự có nhu cầu và quyền tương ứng.

Không dùng `include: "*"` trên cổng có thể truy cập từ Internet. Ngay cả khi một endpoint đã được Actuator khử một số giá trị mặc định, metadata, tên property và địa chỉ nội bộ vẫn có thể nhạy cảm.

### 5.2. Defense in depth: giới hạn mạng và quyền truy cập

Đối với endpoint nội bộ, áp dụng nhiều lớp:

1. Giới hạn exposure ở ứng dụng.
2. Đặt management interface/port trong mạng vận hành, không qua public ingress nếu không cần.
3. Áp dụng xác thực và phân quyền vai trò; phân biệt quyền đọc telemetry với quyền thay đổi log level.
4. Bảo đảm TLS, access log an toàn, audit và retention phù hợp.
5. Kiểm tra gateway, ingress, service mesh và Spring Security thực tế; đừng suy ra rằng chỉ vì endpoint không có link trên UI thì nó không truy cập được.

Ví dụ minh họa security chain riêng cho các endpoint Actuator trong ứng dụng có Spring Security:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {

    http.securityMatcher(EndpointRequest.toAnyEndpoint());
    http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .anyRequest().hasRole("OPS"));

    return http.build();
}
~~~

Đây là một đoạn cấu hình **tham khảo** đặt trong `@Configuration`, không phải cấu hình bảo mật hoàn chỉnh. Dự án phải có authentication provider, chain bảo vệ API ứng dụng, quy tắc CSRF/session phù hợp và cách cấp role `OPS` nhất quán. Nếu application tự định nghĩa `SecurityFilterChain`, hành vi bảo vệ Actuator mặc định có thể bị thay đổi; cần test đường đi thực tế.

### 5.3. Dữ liệu của `env` và `configprops`

Giá trị property có thể được khử nhạy cảm theo cấu hình và phiên bản framework. Tuy nhiên, không đưa secret vào output bằng cách bật:

~~~yaml
# Chỉ là ví dụ cần tránh trong production
management:
  endpoint:
    env:
      show-values: always
    configprops:
      show-values: always
~~~

Trong production, lựa chọn thận trọng:

~~~yaml
management:
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
~~~

Chỉ tắt hiển thị giá trị vẫn chưa đủ nếu endpoint bị expose không cần thiết. Tốt nhất là không đưa chúng vào danh sách HTTP endpoint có thể truy cập từ phía ngoài.

### 5.4. Tách cổng quản trị khi phù hợp

Một triển khai có thể cấu hình cổng Actuator riêng:

~~~yaml
management:
  server:
    port: 9090
~~~

Cổng riêng **không mặc nhiên là cổng riêng tư**; vẫn cần quy tắc firewall, network policy, ingress và authentication. Với cấu hình riêng biệt phù hợp, có thể bind management server vào địa chỉ nội bộ; nếu chỉ bind loopback, monitoring ở bên ngoài pod/host có thể không truy cập được, nên phải thiết kế theo hạ tầng thật.

## 6. Logging an toàn cho tương tác giữa application module

Trong Spring Modulith, cùng một yêu cầu người dùng có thể gọi nhiều module hoặc phát các domain event. Cách log thuận tiện như dưới đây có thể rất nguy hiểm:

~~~java
// KHÔNG NÊN trên production nếu event chứa dữ liệu nhạy cảm
log.debug("Received event: {}", event);
log.debug("Input payload: {}", request);
log.debug("Authorization: {}", authorizationHeader);
~~~

Nếu `event` hoặc `request` dùng record hoặc Lombok `@ToString`, chuỗi biểu diễn có thể bao gồm toàn bộ field. Một thay đổi thêm trường `customerEmail` hoặc `accessToken` cũng khiến log bị lộ mà không cần ai sửa câu lệnh log.

### 6.1. Chỉ log thuộc tính phục vụ chẩn đoán

Giả sử hệ thống có sự kiện nghiệp vụ:

~~~java
package com.acme.shop.payment.events;

public record PaymentAuthorized(
        String paymentId,
        String customerEmail,
        long amountInCents,
        String gatewayReference) {
}
~~~

Đừng dùng toàn bộ record làm message. Có thể log sự kiện theo loại, kết quả và thời gian xử lý; chỉ bổ sung một mã tương quan đã được tạo riêng cho telemetry, không mang thông tin khách hàng.

~~~java
void handle(PaymentAuthorized event) {
    long started = System.nanoTime();

    try {
        process(event);
        log.info("module_event type=PaymentAuthorized result=success");
    } catch (RuntimeException ex) {
        log.warn("module_event type=PaymentAuthorized result=failure "
                + "errorCategory=processing");
        throw ex;
    } finally {
        long durationMs =
                java.util.concurrent.TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);
        log.debug("module_event_duration type=PaymentAuthorized ms={}",
                durationMs);
    }
}
~~~

Đoạn code mang tính minh họa, giả định `process` thuộc module nghiệp vụ và `log` được khởi tạo. Không ghi nguyên văn exception message trước khi xem xét vì message cũng có thể chứa token, SQL fragment hoặc input từ người dùng. Nếu cần stack trace, nên giới hạn ở logger đã được đánh giá, có quyền xem chặt chẽ và kiểm tra khả năng chứa dữ liệu nhạy cảm.

### 6.2. Quy tắc redaction

Phân biệt hai chiến lược:

- **Data minimization:** không tạo trường log/trace chứa dữ liệu nhạy cảm ngay từ đầu.
- **Redaction/masking:** xử lý làm sạch khi vì lý do cụ thể phải xử lý dữ liệu có nguy cơ nhạy cảm.

Ưu tiên loại bỏ dữ liệu ngay tại nơi tạo log. Masking chuỗi bằng regex có thể bỏ sót JSON lồng nhau, token lạ, URL encode hoặc exception message. Nên dùng allowlist các trường log được phép thay vì blacklist vài key thường gặp.

Ví dụ bộ trường phù hợp cho một log định dạng JSON:

~~~json
{
  "service": "shop",
  "module": "payment",
  "event_type": "PaymentAuthorized",
  "outcome": "success",
  "duration_ms": 18,
  "trace_id": "opaque-trace-identifier"
}
~~~

`trace_id` là mã tương quan do hệ thống tracing tạo ra, không phải email hoặc mã tài khoản. Đừng gắn thông tin khách hàng vào giá trị correlation ID. Kích thước, nguồn phát và retention của trace ID vẫn cần được quản lý.

### 6.3. Mức log đúng cho production

Ví dụ:

~~~yaml
logging:
  level:
    root: INFO
    com.acme.shop: INFO
    org.springframework.modulith: INFO
    org.springframework.security: WARN
    org.springframework.web: WARN
~~~

Điều chỉnh logger dựa vào loại sự cố cần chẩn đoán, không dựa trên cảm giác rằng “DEBUG sẽ giúp xem rõ hơn”. Bật `DEBUG`/`TRACE` trong một cuộc điều tra production cần được xem là **ngoại lệ có giới hạn thời gian**, được xác nhận phạm vi, người truy cập và khả năng lộ dữ liệu, sau đó tự trở về cấu hình an toàn.

## 7. Đảm bảo metric không chứa định danh nhạy cảm hoặc cardinality cao

Trong hệ observability, metric thường gắn nhãn như `module`, `operation`, `outcome` hoặc `status`. Một metric ví dụ:

~~~text
modulith_module_operation_total{
  module="inventory",
  operation="checkAvailability",
  outcome="success"
} 1840
~~~

Đây là **tên minh họa**, không khẳng định Spring Modulith tự sinh đúng metric này. Điều quan trọng là nhãn có tập giá trị nhỏ, ổn định và hữu ích cho phân tích.

Không nên làm như sau:

~~~text
module_calls_total{
  customer_email="person@example.test",
  order_id="ORD-927481",
  jwt="eyJ..."
} 1
~~~

Các trường này vừa chứa dữ liệu không cần thiết vừa tạo số lượng time series rất lớn. Một tag `orderId` có hàng triệu giá trị có thể tăng chi phí lưu trữ và ảnh hưởng hiệu năng hệ metrics.

Bảng lựa chọn:

| Nhãn thường phù hợp | Nhãn cần tránh |
| --- | --- |
| `module=ordering` | `customerEmail=...` |
| `operation=placeOrder` | `paymentToken=...` |
| `outcome=success/failure` | `sessionId=...` |
| `errorCategory=timeout/validation` | `exceptionMessage=<input người dùng>` |
| `integration=erp` | `rawUrl=/orders/<orderId>` |

Dùng **route mẫu** như `/orders/{id}` khi cần thống kê HTTP, không ghi nguyên đường dẫn có định danh. Kiểm tra metric dimensions từ thư viện cũng như các tag thêm thủ công bằng `ObservationConvention`, `MeterFilter` hoặc instrumentation nội bộ.

## 8. Tracing: giữ giá trị chẩn đoán mà không truyền PII

Tracing giúp nhìn thấy luồng gọi qua các module và dịch vụ:

~~~mermaid
flowchart LR
    A["HTTP /checkout"] --> B["ordering"]
    B --> C["inventory"]
    B --> D["payment"]
    D --> E["notification listener"]
    E --> F["Telemetry exporter"]
~~~

Sơ đồ chỉ minh họa một luồng. Trong thực tế, `notification listener` có thể xử lý bất đồng bộ thông qua event, và exporter thu telemetry từ nhiều tiến trình hoặc thread khác nhau.

Một span hữu ích có thể mang:

~~~text
name: ordering.placeOrder
attributes:
  module.name: ordering
  operation: placeOrder
  outcome: success
  error.category: none
duration: 45 ms
~~~

Không thêm:

~~~text
attributes:
  customer.email: real-user@example.test
  authorization: Bearer ...
  payment.card_number: ...
  event.payload: {...}
~~~

Trace có thể được truyền đến hệ thống thứ ba và lưu lâu hơn dự kiến. Một thuộc tính không được xem là an toàn chỉ vì giao diện dashboard giới hạn quyền xem; dữ liệu đã được xuất qua mạng vẫn tồn tại ở nơi nhận.

### 8.1. Sampling không phải bảo vệ bí mật

`management.tracing.sampling.probability` giúp điều chỉnh tỷ lệ trace được ghi. Một request chứa secret vẫn có khả năng được chọn và gửi đi. Dù tỷ lệ bằng 1%, việc thêm token vào span vẫn là lỗi thiết kế.

Các quyết định cần tách biệt:

1. Có được phép thu loại dữ liệu này không?
2. Có được phép xuất dữ liệu đó đến backend tracing không?
3. Nếu có, tần suất và thời hạn lưu trữ là bao nhiêu?

Chỉ sau khi giải quyết hai câu hỏi đầu mới nên điều chỉnh sampling.

### 8.2. Baggage và context propagation

**Baggage** là dữ liệu ngữ cảnh có thể lan theo trace qua thread hoặc ranh giới dịch vụ tùy cấu hình. Nếu đưa email, user ID, tenant secret hoặc token vào baggage, giá trị đó có thể xuất hiện ở nhiều dịch vụ hoặc HTTP headers hơn phạm vi dự kiến.

Nên truyền các trường nghiệp vụ nhạy cảm qua cơ chế được thiết kế cho nghiệp vụ và xác thực. Với telemetry, dùng tập khóa nhỏ đã phê duyệt. Nếu thực sự cần tenant discriminator để debug, cân nhắc giá trị nhóm không định danh hoặc định danh đã được đánh giá theo chính sách; tránh tự động dùng raw tenant/customer ID.

Với listener bất đồng bộ, xác nhận việc chuyển tiếp `trace context` và `MDC`:

- Executor có thể cần cấu hình context propagation tùy stack Micrometer/Spring Boot/Modulith.
- MDC gắn với thread cần được làm sạch đúng sau mỗi task để không trộn thông tin giữa request khác nhau.
- Trace bị mất liên kết không có nghĩa event không được xử lý; cần phối hợp log outcome, event publication status và trace.
- Không giải quyết lỗi mất context bằng cách tự sao chép toàn bộ request headers hoặc security context vào mọi event.

## 9. Domain event và event publication: giới hạn nội dung được quan sát

Spring Modulith hỗ trợ mô hình tương tác giữa module bằng Spring application events và có cơ chế theo dõi event publication trong những cấu hình phù hợp. Mục tiêu của event publication registry là hỗ trợ độ tin cậy và xử lý publication; dữ liệu lưu trữ có thể gồm thông tin sự kiện, trạng thái, thời điểm và metadata tùy triển khai.

Một event có thể mang dữ liệu cần thiết cho nghiệp vụ, ví dụ:

~~~java
public record OrderPlaced(
        java.util.UUID orderId,
        java.time.Instant occurredAt) {
}
~~~

Khi consumer cần đọc thêm chi tiết, cân nhắc truy vấn qua API module hoặc thiết kế event contract tối thiểu. Không nhồi vào event những thông tin chỉ phục vụ debug như toàn bộ HTTP request, JWT hoặc bản sao database entity. Event được gửi qua nhiều listener thường có **phạm vi tiếp cận rộng hơn** lời gọi trực tiếp.

Những điều cần kiểm tra khi bật observability cho event:

| Câu hỏi | Kiểm soát đề xuất |
| --- | --- |
| Event payload có chứa dữ liệu khách hàng không? | Chỉ đưa field phục vụ consumer, không log nguyên object |
| Listener có in event trong exception không? | Dùng mã lỗi ổn định, xử lý exception message cẩn trọng |
| Event registry có lưu payload không? | Kiểm tra schema, quyền truy cập DB, mã hóa/retention phù hợp |
| Debug/replay có thể tải lại event không? | Hạn chế quyền và ghi audit với thao tác nhạy cảm |
| Metric được gắn những tag nào? | Dùng loại event, module và outcome; tránh ID động |
| Tracing có truyền context qua listener? | Chỉ giữ context cần thiết; kiểm tra propagation/cleanup |

Tùy công nghệ serialization và store, một payload an toàn để truyền nội bộ vẫn cần bảo vệ ở nơi lưu. Không dùng log hoặc trace làm kho lưu trữ thứ cấp cho event đầy đủ.

## 10. Module graph và tài liệu kiến trúc cũng cần kiểm soát truy cập

Spring Modulith có thể dùng `ApplicationModules` và thành phần tài liệu để sinh sơ đồ phụ thuộc. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentationTest {

    @Test
    void writeModuleDocumentation() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        new Documenter(modules).writeDocumentation();
    }
}
~~~

Ví dụ trên giả định dự án có class `ShopApplication` và dependency documentation phù hợp. Kết quả phụ thuộc phiên bản/thư mục output được cấu hình.

Module graph hữu ích để xem `ordering` có gọi `payment` qua API công khai hay không, có phụ thuộc vòng không, và cấu trúc sau refactor có đúng dự kiến. Tuy nhiên nó có thể tiết lộ:

- Tên module nghiệp vụ hoặc tích hợp nhạy cảm.
- Package và class triển khai nội bộ.
- Cạnh nối đến payment provider, legacy adapter hoặc thành phần nhận dữ liệu nhạy cảm.
- Thông tin về miền nghiệp vụ và khả năng hệ thống.

Vì vậy, nên sinh tài liệu trong CI/tài liệu nội bộ, phân quyền theo nhu cầu và review trước khi xuất bản ra tài liệu công khai. Không đưa module graph nguyên vẹn vào một endpoint không xác thực chỉ vì nó “không chứa mật khẩu”. Nếu phải chia sẻ ra ngoài, tạo phiên bản tóm lược chỉ gồm thành phần và phụ thuộc được phép công bố.

## 11. Cấu hình secret và biến môi trường

Các giá trị như database password, API key, private key, signing secret, token hoặc credentials của telemetry exporter không nên nằm trực tiếp trong file cấu hình lưu chung:

~~~yaml
# KHÔNG NÊN: ví dụ cấu hình chứa secret thật trong Git
payment:
  gateway:
    api-key: "real-secret-here"
~~~

Thay bằng cơ chế quản lý secret của môi trường triển khai hoặc injected environment variable:

~~~yaml
payment:
  gateway:
    api-key: "${PAYMENT_GATEWAY_API_KEY}"
~~~

Ví dụ trên chỉ giải quyết **nguồn cung cấp giá trị**, không bảo đảm giá trị không bị log hoặc xuất qua Actuator. Secret vẫn có trong bộ nhớ ứng dụng và có thể xuất hiện ở dump nếu không bảo vệ. Production cần kiểm tra role có quyền truy cập secret store, cơ chế rotation, phạm vi tài khoản và chính sách export logs/traces.

Không ghi mã bí mật vào thông báo lỗi kiểm tra cấu hình:

~~~java
// Không ghi: "Invalid payment API key: " + suppliedKey
throw new IllegalStateException(
        "Payment gateway credentials are unavailable or invalid");
~~~

Nếu credential lỗi, ghi một mã lỗi không nhạy cảm và để hệ quản lý secret/audit xác định nguyên nhân kỹ thuật.

## 12. Đặt quy trình bật debug tạm thời khi production có sự cố

Thỉnh thoảng, dữ liệu production là nơi duy nhất tái hiện được lỗi. Thay vì cố định DEBUG/TRACE, có thể dùng quy trình tăng mức quan sát có kiểm soát.

### 12.1. Trước khi bật

1. Mô tả lỗi cần tìm: module, operation, khoảng thời gian và triệu chứng.
2. Chọn logger hoặc observation hẹp nhất có thể cung cấp tín hiệu.
3. Kiểm tra xem logger có ghi body, header, DTO, event payload hoặc exception message nhạy cảm không.
4. Xác định ai có quyền bật và ai được xem kết quả, thời hạn áp dụng và nơi dữ liệu sẽ đi.
5. Ưu tiên tạo thêm một metric an toàn hoặc log theo mã lỗi thay vì bật TRACE của cả framework.

### 12.2. Trong lúc bật

Giới hạn phạm vi theo instance/module nếu hạ tầng cho phép. Theo dõi dung lượng log và chi phí telemetry; xem mẫu output đã được làm sạch trong cửa sổ điều tra. Không copy log, dump hoặc trace chứa dữ liệu thật vào ticket/chats không có phân quyền phù hợp.

Nếu sử dụng endpoint `loggers` để thay đổi mức log lúc chạy, endpoint này phải có xác thực, audit và quyền cao hơn các endpoint chỉ đọc. Không expose rộng cho mọi người chỉ vì nó thuận tiện.

### 12.3. Sau khi kết thúc

Khôi phục mức log chuẩn; kiểm tra cấu hình đã trở lại INFO/WARN và không có override ở deployment. Đánh giá dữ liệu đã thu, xóa/giới hạn quyền các hiện vật không cần thiết theo chính sách, và chuyển phát hiện thành kiểm thử hoặc telemetry an toàn lâu dài.

Giải pháp có thể duy trì tốt nhất thường là **thêm log/metric có cấu trúc theo loại lỗi**, thay vì duy trì TRACE thường trực.

## 13. Kiểm tra cấu hình hiệu lực trước khi mở traffic

Chỉ review YAML không đủ: biến môi trường, tham số launch, Helm chart, ConfigMap hoặc policy của gateway có thể ghi đè. Hãy xác minh bản triển khai dự kiến bằng các thao tác có thể lặp lại.

### 13.1. Kiểm tra Actuator từ đúng đường mạng

Một lệnh kiểm tra minh họa:

~~~bash
# Địa chỉ này chỉ là ví dụ; phải thay bằng deployment cần kiểm tra.
curl --silent --show-error --include "https://shop.example.test/actuator/health"
curl --silent --show-error --include "https://shop.example.test/actuator/env"
curl --silent --show-error --include "https://shop.example.test/actuator/heapdump"
~~~

Ở public ingress, kỳ vọng `health` chỉ tiết lộ dữ liệu cho phép; `env` và `heapdump` không được truy cập thành công bởi người không có quyền. Với cấu hình chỉ expose health, các endpoint không expose thường không có route HTTP; tùy security/gateway, kết quả có thể khác nhau (404, 401 hoặc 403). Điều quan trọng là **không trả dữ liệu nhạy cảm**, đồng thời kiểm tra từ cả đường public và mạng quản trị nếu có.

Đừng thử tải thật heapdump trên production chỉ để kiểm tra bảo mật; chỉ cần xác nhận người không có quyền không truy cập được endpoint, tránh tạo dump nhạy cảm không cần thiết.

### 13.2. Kiểm tra telemetry thực tế

Tạo request kiểm thử bằng dữ liệu giả đã được phê duyệt, rồi kiểm tra log và trace xuất đi. Dùng một bộ giá trị mô phỏng dễ nhận diện, ví dụ email `qa-probe@example.test` và marker `TEST-SENSITIVE-MARKER`; chúng không phải dữ liệu cá nhân thật. Gửi qua workflow mẫu, sau đó tìm marker trong log, traces và metric labels.

Một kiểm thử hữu ích phải trả lời:

- Có xuất hiện body, header `Authorization`, cookie hay token trong log không?
- `event.toString()` có in tất cả field của event không?
- Span attributes hoặc baggage có mang email/mã khách hàng không?
- Metric label có gắn ID động làm tăng cardinality không?
- Module metadata/graph có bị công bố công khai không?
- Một workflow bất đồng bộ có giữ được trace correlation mà không lan thông tin nhạy cảm không?

Một lần quét không tìm thấy marker là bằng chứng cục bộ, không chứng minh mọi đường đi đều an toàn. Cần chọn fixture đại diện cho lỗi, retry, exception và cả các listener hiếm khi chạy.

### 13.3. Kiểm tra cấu hình dưới CI

Các cổng kiểm tra nên bao gồm:

| Cổng | Điều kiện kiểm tra |
| --- | --- |
| Profile | Deployment production bật đúng profile và guard khởi động |
| Actuator | Danh sách endpoint exposed khớp allowlist đã duyệt |
| Log level | Không có DEBUG/TRACE toàn cục hoặc override không được phê duyệt |
| HTTP request logging | Không in header/body nhạy cảm |
| Trace/metrics | Chỉ có trường cho phép, không có PII/secret trong attributes và tags |
| Event publication | Payload/registry có phân quyền, retention và dữ liệu tối thiểu |
| Module documentation | Tài liệu/graph chỉ xuất hiện trong phạm vi truy cập dự kiến |
| Remote access | Public ingress, management network và role authorization đã được kiểm chứng |
| Rollout | Có thể khôi phục cấu hình an toàn nếu phát hiện dữ liệu bị rò |

Với trường hợp chưa thể tự động hóa, ghi nhận ai kiểm tra, build nào được kiểm tra, đường mạng nào được dùng và kết quả quan sát.

## 14. Một tình huống thực tế: trace chứa email trong luồng thanh toán

**Bối cảnh:** `ordering` tạo đơn và gọi `payment`. Khi thanh toán thành công, `payment` phát event để `notification` gửi email xác nhận. Sau một lần nâng cấp instrumentation, kỹ sư thêm `customer.email` làm span attribute để tìm request dễ hơn.

**Dấu hiệu:** dashboard tracing hiển thị email thật cho mọi request được sample; cùng một thuộc tính được export tới hệ thống quan sát tập trung. Bài kiểm tra module graph vẫn đạt vì phụ thuộc kiến trúc không có vấn đề.

**Phân tích:** việc gắn email vào span là nguyên nhân. Giảm sampling chỉ làm ít trace chứa email hơn. Đổi `payment` từ module mở sang đóng cũng không xử lý được vì đây là lỗi dữ liệu telemetry, không phải lỗi module boundary.

**Cách sửa:** loại thuộc tính `customer.email` khỏi instrumenter; dùng correlation ID ngẫu nhiên và tên module/operation/outcome. Đánh giá trace đã export theo chính sách dữ liệu, giới hạn quyền và retention; thêm bài kiểm tra với marker mô phỏng vào CI để giảm nguy cơ tái phạm. Kiểm tra cả event listener bất đồng bộ để chắc rằng baggage không tiếp tục chuyển email sang `notification`.

Trường hợp này cho thấy **kiểm chứng kiến trúc** và **kiểm tra độ an toàn của dữ liệu quan sát** là hai trách nhiệm riêng cần được thực hiện cùng nhau.

## 15. Nếu đã lỡ ghi dữ liệu nhạy cảm thì làm gì?

Khi phát hiện secret, thông tin cá nhân hoặc payload nhạy cảm đã đi vào log/trace/metric, xử lý theo quy trình sự cố của tổ chức:

1. **Ngăn nguồn phát:** tắt logger/instrumentation gây rò, đưa deployment về cấu hình an toàn và chặn exporter/endpoint khi cần.
2. **Khoanh vùng:** xác định thời gian, môi trường, loại dữ liệu, phạm vi hệ thống nhận (log shipper, object storage, APM, vendor), người có thể truy cập.
3. **Thu hồi hoặc xoay secret:** credential/token đã xuất hiện cần được đánh giá khả năng bị lộ và rotate/revoke theo quy định, thay vì chỉ xóa dòng log.
4. **Quản lý bản sao:** kiểm tra log index, trace backend, backup, support bundle và bản export; áp dụng xóa/retention theo chính sách và khả năng kỹ thuật.
5. **Thông báo và điều tra:** chuyển đến bộ phận phụ trách bảo mật/quyền riêng tư theo quy trình; lưu bằng chứng ở nơi được kiểm soát.
6. **Ngăn tái diễn:** thêm field allowlist, kiểm thử telemetry, kiểm tra profile/exposure và review thay đổi instrumentation.

Không dán chính dữ liệu bị lộ vào issue công khai hoặc channel mở trong lúc điều tra. Với token, tính nhạy cảm không biến mất ngay chỉ vì hệ thống đã bật masking về sau.

## 16. Bài thực hành

Xây dựng ứng dụng Spring Boot modular monolith có module `catalog`, `ordering` và `notification`. Cho `ordering` phát một event chứa dữ liệu mô phỏng và `notification` xử lý event. Có thể sử dụng tracing/metrics trong môi trường test hoặc local, không cần dữ liệu khách hàng thật.

**Nhiệm vụ:**

1. Tạo `application-prod.yml` chỉ expose `health`, ẩn health details và giữ log root INFO.
2. Kiểm tra đường public đến `/actuator/health`, `/actuator/env`, `/actuator/beans` và metadata Modulith nếu có; ghi mã HTTP và thông tin thực sự nhận được.
3. Thêm một field mô phỏng `TEST-SENSITIVE-MARKER` trong event; cố ý log toàn bộ event ở môi trường test để hiểu rủi ro, rồi thay bằng log theo loại sự kiện/outcome.
4. Thiết lập trace với nhãn `module`, `operation` và `outcome`; xác nhận không gắn email, token, raw payload vào attributes hoặc baggage.
5. Kiểm tra một listener bất đồng bộ: trace có liên kết đúng không? Có bị lẫn MDC của request khác không?
6. Dùng `Documenter` tạo module graph; xác định artifact có phù hợp để công khai hay chỉ nên lưu trong tài liệu nội bộ.
7. Tạo một kiểm thử smoke từ địa chỉ mô phỏng public ingress để bảo đảm Actuator sensitive endpoints không trả dữ liệu cho người chưa xác thực.
8. Thử một biến môi trường ghi đè log level trong môi trường test, kiểm tra pipeline có phát hiện và ngăn áp dụng cấu hình đó vào production không.

**Câu hỏi tự đánh giá:**

- Tại sao `management.tracing.sampling.probability=0.01` vẫn không bảo vệ được token nếu instrumentation gắn token vào span?
- Vì sao `@NamedInterface` hoặc module đóng không tự bảo vệ event payload khỏi bị log?
- Khi nào endpoint `health` có thể để công khai và nên ẩn những chi tiết nào?
- Một metric có tag `orderId` gặp vấn đề gì ngoài rò dữ liệu?
- Vì sao cần kiểm tra cả cấu hình trong Git và cấu hình hiệu lực sau deployment?

## 17. Checklist trước khi phát hành production

- [ ] Deployment production bật profile được quy định, có kiểm tra chống sai profile.
- [ ] Không có DEBUG/TRACE toàn cục hoặc request body/header logging chưa được duyệt.
- [ ] Log, exception message, event output và listener chỉ ghi các trường an toàn, cần thiết.
- [ ] Không đưa secret, email, token, raw URL động, payload vào metric tags hoặc span attributes.
- [ ] Trace baggage và MDC được kiểm soát khi đi qua thread, event listener hoặc dịch vụ khác.
- [ ] Sampling, telemetry exporter, retention và phân quyền dashboard được cấu hình theo chính sách.
- [ ] Actuator chỉ expose các endpoint cần thiết và quản trị từ đường mạng/role phù hợp.
- [ ] `env` / `configprops` không hiển thị property values nhạy cảm; `heapdump` và `logfile` không truy cập công khai.
- [ ] Không có module graph, package metadata, tài liệu nội bộ bị xuất bản ngoài ý muốn.
- [ ] Event publication registry, storage và retry/replay được kiểm soát quyền và dữ liệu lưu.
- [ ] Đã chạy kiểm thử với marker dữ liệu giả để phát hiện rò rỉ vào log, trace và metric.
- [ ] Có runbook bật debug tạm thời, rollback, xử lý sự cố dữ liệu và rotate secrets.

**Tiêu chí xác nhận:** production vẫn phải cung cấp được tín hiệu về tình trạng module, lỗi event, độ trễ và luồng tương tác để vận hành, nhưng **không xuất dữ liệu nhạy cảm ra các kênh debug**. Cấu hình an toàn cần được kiểm tra trên deployment thực tế, đặc biệt khi thay đổi Spring Boot, Spring Modulith, Micrometer, Actuator, exporter hoặc hạ tầng thu thập telemetry.
