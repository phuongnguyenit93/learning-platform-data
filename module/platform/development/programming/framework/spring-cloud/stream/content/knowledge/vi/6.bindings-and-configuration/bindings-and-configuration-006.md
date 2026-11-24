# Cấu hình mặc định và ghi đè theo từng binding

## Mục tiêu

Một ứng dụng Spring Cloud Stream thường có nhiều binding: một binding nhận đơn hàng, một binding nhận thanh toán và một hoặc nhiều binding phát sự kiện. Nếu mỗi binding đều khai báo lại content type, retry, concurrency và các thuộc tính chung, cấu hình sẽ dài, khó rà soát và dễ lệch nhau. Spring Cloud Stream cho phép đặt **giá trị mặc định dùng chung** rồi ghi đè ở **từng binding** khi luồng đó có yêu cầu riêng.

Bài học này giải thích cách tổ chức cấu hình theo phạm vi, cách đặt tên binding trong mô hình hàm, cách phân biệt thuộc tính chung với thuộc tính riêng của binder và cách xác định giá trị cuối cùng khi nhiều nguồn cấu hình cùng tham gia.

Sau bài học, bạn có thể:

- Dùng `spring.cloud.stream.default` để khai báo cấu hình chung.
- Ghi đè bằng `spring.cloud.stream.bindings.<bindingName>`.
- Phân biệt thuộc tính consumer/producer chung với thuộc tính mở rộng của Kafka, RabbitMQ hoặc Pulsar binder.
- Chọn binder mặc định hoặc binder cụ thể cho một binding.
- Tổ chức profile và biến môi trường để cấu hình theo từng môi trường triển khai.
- Kiểm tra cấu hình hiệu lực thay vì chỉ đọc một file YAML.

## 1. Binding là đơn vị cấu hình

Trong mô hình hàm, tên binding được suy ra từ tên bean hàm và vị trí đầu vào/đầu ra:

| Hàm | Binding | Vai trò |
|---|---|---|
| `Consumer<OrderCreated> orderCreated()` | `orderCreated-in-0` | Nhận sự kiện đơn hàng |
| `Function<Payment, Receipt> processPayment()` | `processPayment-in-0`, `processPayment-out-0` | Nhận thanh toán và phát kết quả |
| `Supplier<AuditEvent> auditEvents()` | `auditEvents-out-0` | Phát sự kiện kiểm toán |
| `Consumer<AuditEvent> auditLog()` | `auditLog-in-0` | Nhận sự kiện để ghi nhật ký |

Ví dụ:

```java
@Bean
Consumer<OrderCreated> orderCreated(OrderService service) {
    return service::handle;
}

@Bean
Function<Payment, Receipt> processPayment(PaymentService service) {
    return service::process;
}

@Bean
Supplier<AuditEvent> auditEvents(AuditService service) {
    return service::nextEvent;
}

@Bean
Consumer<AuditEvent> auditLog(AuditService service) {
    return service::handle;
}
```

Mỗi binding có thể được cấu hình riêng về destination, group, content type, consumer hoặc producer. Cấu hình cần dùng đúng tên binding. Nếu viết nhầm `processPayment-out-0` thành `process-payment-out-0`, thuộc tính có thể không áp dụng cho binding thực tế.

Có thể khai báo tên hàm cần kích hoạt:

```yaml
spring:
  cloud:
    function:
      definition: orderCreated;processPayment;auditEvents;auditLog
```

Khai báo này giúp xác định rõ các function bean được kết nối vào luồng. Nếu không khai báo, việc phát hiện và kích hoạt function phụ thuộc cơ chế auto-configuration và các bean có trong application context; với ứng dụng có nhiều hàm, khai báo tường minh dễ dự đoán hơn.

## 2. Đặt cấu hình chung làm mặc định

Các thuộc tính chung có thể đặt dưới `spring.cloud.stream.default`. Những binding không khai báo giá trị riêng sẽ sử dụng giá trị mặc định tương ứng.

Ví dụ đặt content type và retry mặc định cho consumer:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-multiplier: 2.0
          back-off-max-interval: 10000
```

Ý nghĩa:

- `content-type` là định dạng payload mặc định khi binding không chỉ định riêng.
- `consumer.max-attempts` đặt số lần thử xử lý tối đa theo cơ chế retry của Spring Cloud Stream.
- `back-off-initial-interval` là thời gian chờ ban đầu giữa các lần thử.
- `back-off-multiplier` điều chỉnh mức tăng thời gian chờ.
- `back-off-max-interval` giới hạn thời gian chờ tối đa.

Ví dụ này đặt ba lần thử tổng cộng theo cấu hình retry thông thường của consumer; số lần giao lại ở tầng broker có thể là một cơ chế khác. Không cộng hoặc nhân số lần thử một cách máy móc khi chưa kiểm tra cách binder xử lý lỗi.

Có thể đặt mặc định cho producer nếu các binding đầu ra có cùng chính sách. Ví dụ, khi các producer đều dùng một content type chung:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
```

Không phải mọi thuộc tính của broker đều có thể đặt trong `default`. Chỉ dùng tại đây những thuộc tính chung mà Spring Cloud Stream hỗ trợ ở cấp binding, consumer hoặc producer.

## 3. Ghi đè ở từng binding

Khi một luồng có yêu cầu khác với mặc định, đặt thuộc tính trong `spring.cloud.stream.bindings.<bindingName>`. Cấu hình ở binding cụ thể có độ ưu tiên cao hơn giá trị mặc định tương ứng.

Ví dụ: đa số consumer retry ba lần, riêng luồng thanh toán được phép thử năm lần và luồng kiểm toán không cần retry:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
          back-off-initial-interval: 1000
          back-off-multiplier: 2.0
          back-off-max-interval: 10000

      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service

        processPayment-in-0:
          destination: payments.authorized
          group: billing-service
          consumer:
            max-attempts: 5

        auditLog-in-0:
          destination: audit.events
          group: audit-service
          consumer:
            max-attempts: 1

        auditEvents-out-0:
          destination: audit.generated
```

Trong ví dụ:

- `orderCreated-in-0` dùng JSON và retry mặc định ba lần.
- `processPayment-in-0` dùng JSON, nhưng ghi đè số lần thử thành năm; các thuộc tính backoff còn lại vẫn lấy từ mặc định.
- `auditLog-in-0` dùng JSON và chỉ thử một lần, phù hợp nếu lỗi được chuyển sang quy trình xử lý khác đã được thiết kế.
- `auditEvents-out-0` là binding đầu ra của Supplier và không nhận các thuộc tính consumer.

Cấu hình binding cụ thể chỉ ghi những thuộc tính cần khác biệt. Không cần sao chép lại toàn bộ cấu hình mặc định vào từng binding.

### Ví dụ ghi đè content type và destination

Một binding có thể dùng định dạng khác với phần còn lại:

```yaml
spring:
  cloud:
    stream:
      default:
        content-type: application/json
      bindings:
        auditEvents-out-0:
          destination: audit.events
          content-type: application/cloudevents+json
```

Content type trong ví dụ là một lựa chọn của hợp đồng sự kiện; producer và consumer phải thống nhất schema và khả năng chuyển đổi. Việc thay content type chỉ ở producer mà không cập nhật consumer có thể khiến lỗi deserialize xảy ra trước khi hàm nghiệp vụ được gọi.

## 4. Phân biệt thuộc tính chung và thuộc tính riêng của binder

Spring Cloud Stream có hai nhóm cấu hình cần phân biệt:

**Thuộc tính chung** áp dụng qua abstraction của framework, ví dụ:

- Destination, group và content type.
- Consumer retry, backoff và concurrency.
- Producer partitioning ở mức thuộc tính chung được hỗ trợ.
- Binder được chọn cho binding.

**Thuộc tính mở rộng của binder** điều khiển khả năng riêng của broker, ví dụ:

- Kafka: consumer isolation level, offset reset, cấu hình producer Kafka, transaction và các thuộc tính client.
- RabbitMQ: exchange, queue, routing, prefetch, dead-letter và các tùy chọn listener/container.
- Pulsar: subscription type, acknowledgment timeout, subscription name, schema và các tùy chọn client.

Thuộc tính mở rộng thường nằm trong namespace riêng của binder, theo dạng:

```text
spring.cloud.stream.<binder>.bindings.<bindingName>.consumer...
spring.cloud.stream.<binder>.bindings.<bindingName>.producer...
```

Ví dụ minh họa với Kafka binder:

```yaml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
      kafka:
        bindings:
          orderCreated-in-0:
            consumer:
              configuration:
                isolation.level: read_committed
```

`isolation.level` là thuộc tính Kafka consumer; không nên đặt nó dưới cấu hình consumer chung rồi mong RabbitMQ hoặc Pulsar hiểu cùng ý nghĩa. Cấu trúc và tên thuộc tính mở rộng cần được đối chiếu với tài liệu của đúng phiên bản binder đang sử dụng.

Đối với RabbitMQ hoặc Pulsar, dùng namespace tương ứng của binder và xác minh tên thuộc tính theo phiên bản. Không sao chép cấu hình Kafka sang binder khác chỉ bằng cách thay tên broker.

## 5. Chọn binder mặc định và binder cho từng binding

Khi ứng dụng chỉ sử dụng một binder, framework thường có thể tự chọn binder phù hợp từ dependency và cấu hình hiện có. Nếu ứng dụng có nhiều binder hoặc muốn lựa chọn rõ ràng, có thể khai báo binder mặc định:

```yaml
spring:
  cloud:
    stream:
      default-binder: kafka
```

Một binding có thể ghi đè lựa chọn đó bằng thuộc tính `binder`:

```yaml
spring:
  cloud:
    stream:
      default-binder: kafka
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
          binder: kafka
        alertEvents-out-0:
          destination: inventory.alerts
          binder: rabbit
```

Tên `kafka` và `rabbit` ở đây phải tương ứng với binder đã được đăng ký trong ứng dụng. Khi cấu hình nhiều instance của cùng loại binder, khai báo binder trong `spring.cloud.stream.binders` với tên, loại và môi trường riêng; sau đó tham chiếu tên đó từ thuộc tính `binder` của binding.

Chọn binder theo binding là quyết định tích hợp. Application service không nên kiểm tra tên binder để quyết định quy tắc nghiệp vụ. Nếu một luồng cần gửi sang hai hệ thống, hãy mô hình hóa hai cổng hoặc hai adapter đầu ra và cấu hình từng binding tương ứng.

## 6. Thứ tự áp dụng cấu hình

Khi điều tra giá trị thực tế, hãy phân biệt hai cấp ưu tiên:

1. **Trong cấu hình Spring Cloud Stream:** giá trị mặc định được dùng khi binding không khai báo giá trị riêng; thuộc tính binding cụ thể ghi đè giá trị mặc định tương ứng. Thuộc tính mở rộng binder điều khiển hành vi riêng của binder.
2. **Giữa các nguồn cấu hình Spring Boot:** file cấu hình, file profile, biến môi trường, system property và tham số dòng lệnh có thứ tự ưu tiên riêng. Nguồn có độ ưu tiên cao hơn có thể ghi đè giá trị trong `application.yml`.

Ví dụ file cơ sở:

```yaml
spring:
  cloud:
    stream:
      default:
        consumer:
          max-attempts: 3
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
```

File profile production có thể ghi đè một giá trị cụ thể:

```yaml
# application-prod.yml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          consumer:
            max-attempts: 5
```

Khi chạy với profile `prod`, binding `orderCreated-in-0` dùng năm lần thử. Các binding khác vẫn dùng giá trị mặc định ba lần nếu không có nguồn cấu hình ưu tiên cao hơn ghi đè.

Có thể đưa giá trị thay đổi theo môi trường vào biến môi trường:

```text
SPRING_CLOUD_STREAM_BINDINGS_ORDERCREATED_IN_0_CONSUMER_MAX_ATTEMPTS=5
```

Tên biến minh họa theo quy tắc chuyển tên thuộc tính Spring Boot sang chữ hoa và dấu gạch dưới. Với tên binding có dấu gạch nối hoặc ký tự đặc biệt, cần xác minh cách ánh xạ biến môi trường của Spring Boot và kiểm tra giá trị thực tế khi khởi động. Với các cấu hình phức tạp, profile YAML thường dễ đọc và ít nhầm hơn.

Không nên giả định một giá trị trong file YAML là giá trị cuối cùng. Khi có sự khác biệt giữa local, test, staging và production, hãy kiểm tra profile đang hoạt động, biến môi trường và tham số khởi chạy.

## 7. Cấu hình theo môi trường mà không nhân bản toàn bộ file

Một cách tổ chức dễ bảo trì là đặt phần chung trong `application.yml`, chỉ ghi các khác biệt trong profile:

```yaml
# application.yml
spring:
  cloud:
    function:
      definition: orderCreated;processPayment
    stream:
      default:
        content-type: application/json
        consumer:
          max-attempts: 3
      bindings:
        orderCreated-in-0:
          destination: orders.created
          group: inventory-service
        processPayment-in-0:
          destination: payments.authorized
          group: billing-service
```

```yaml
# application-dev.yml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          destination: dev.orders.created
```

```yaml
# application-prod.yml
spring:
  cloud:
    stream:
      bindings:
        orderCreated-in-0:
          destination: orders.created
        processPayment-in-0:
          consumer:
            max-attempts: 5
```

File profile chỉ khai báo phần khác biệt. Các giá trị còn lại được kế thừa từ cấu hình chung, miễn là không có nguồn cấu hình ưu tiên cao hơn thay đổi chúng.

Không đưa mật khẩu, token hoặc credential vào file được commit. Dùng secret manager hoặc biến môi trường được quản lý trong môi trường triển khai. Destination, group và số lần retry cũng cần được xem là cấu hình vận hành có chủ đích; tránh để mỗi máy phát triển tự chọn một giá trị không được kiểm soát.

## 8. Những lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Binding không dùng retry mặc định | Đặt sai cấp hoặc sai tên binding | Đối chiếu tên function và hậu tố `-in-0`/`-out-0` |
| Một binding không nhận JSON | Content type ở binding ghi đè mặc định hoặc producer gửi định dạng khác | Kiểm tra content type hai phía và schema |
| RabbitMQ không áp dụng thuộc tính Kafka | Đặt thuộc tính mở rộng sai namespace | Đưa thuộc tính vào namespace của đúng binder |
| Local và production có số lần retry khác nhau | Profile hoặc biến môi trường ghi đè | Kiểm tra active profile và externalized configuration |
| Binding dùng sai broker | `default-binder` hoặc `binder` không đúng | Kiểm tra tên binder được đăng ký và lựa chọn ở binding |
| Sửa cấu hình nhưng hành vi không đổi | Thuộc tính sai chính tả, không được hỗ trợ hoặc bị nguồn khác ghi đè | Kiểm tra startup log, cấu hình đã bind và tài liệu đúng phiên bản |
| Retry tăng nhiều hơn dự kiến | Retry của framework kết hợp redelivery của broker | Kiểm tra số lần thử ở từng tầng và trạng thái ack/offset |

Một thuộc tính không hợp lệ có thể bị bỏ qua, bị báo lỗi khi khởi động hoặc không có hiệu lực tùy cách binder và phiên bản xử lý. Không kết luận chỉ dựa vào việc ứng dụng khởi động thành công.

## 9. Quy trình xác minh cấu hình hiệu lực

Khi một binding hoạt động khác dự kiến, kiểm tra theo trình tự:

1. Xác định function bean đang được kích hoạt qua `spring.cloud.function.definition`.
2. Tính đúng tên binding từ tên hàm và vị trí input/output.
3. Tìm cấu hình mặc định trong `spring.cloud.stream.default`.
4. Tìm cấu hình cụ thể trong `spring.cloud.stream.bindings.<bindingName>`.
5. Kiểm tra thuộc tính mở rộng trong namespace của binder.
6. Xác định binder được chọn qua `default-binder` hoặc thuộc tính `binder` tại binding.
7. Kiểm tra active profile, biến môi trường, system properties và tham số dòng lệnh.
8. Xác minh hành vi bằng integration test hoặc quan sát startup log/Actuator environment nếu ứng dụng được phép bật endpoint đó an toàn.

Không bật endpoint quản trị cấu hình công khai chỉ để debug. Nếu dùng Spring Boot Actuator, giới hạn quyền truy cập và không để lộ credential hoặc dữ liệu nhạy cảm.

### Ví dụ kiểm tra bằng test

Có thể kiểm tra cấu hình ở mức application context bằng test Spring Boot, sau đó dùng Test Binder để gửi message và quan sát hành vi. Một unit test thuần chỉ đọc object cấu hình không chứng minh binder thực sự áp dụng retry, partition hoặc DLQ. Các thuộc tính mở rộng cần test với binder tương ứng.

Ví dụ tình huống test cần có:

- Binding không có cấu hình riêng nhận giá trị mặc định.
- Binding có `max-attempts` riêng sử dụng giá trị ghi đè.
- Binding có content type riêng chuyển đổi payload đúng.
- Profile production ghi đè cấu hình cơ sở.
- Binding được chọn đúng binder khi ứng dụng có nhiều binder.
- Thuộc tính Kafka/Rabbit/Pulsar chỉ tác động đến binding dùng binder tương ứng.

## Kết luận

Đặt cấu hình chung trong `spring.cloud.stream.default` giúp các binding dùng chung chính sách nhất quán. Khi một luồng cần hành vi khác, khai báo giá trị ở `spring.cloud.stream.bindings.<bindingName>`; cấu hình cụ thể sẽ ghi đè mặc định tương ứng. Thuộc tính riêng của broker cần nằm trong namespace của binder phù hợp.

Khi triển khai Spring Cloud Stream với Kafka, RabbitMQ hoặc Pulsar, hãy tổ chức phần chung, phần riêng từng binding và phần mở rộng binder theo đúng phạm vi. Kiểm tra tên binding, binder được chọn, profile và các nguồn cấu hình bên ngoài để xác nhận hành vi cuối cùng. Cấu hình chỉ được xem là đúng khi đã được kiểm chứng với binder và môi trường triển khai thực tế.

