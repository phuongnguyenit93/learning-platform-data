# Giới hạn header lỗi và frameMaxHeadroom

Khi một consumer Spring Cloud Stream dùng RabbitMQ binder xử lý message thất bại, binder có thể gửi message sang Dead Letter Queue (DLQ). Nếu bật `republishToDlq`, binder phát lại message tới DLQ và bổ sung metadata lỗi, trong đó có exception message và stack trace. Stack trace rất hữu ích khi điều tra sự cố, nhưng có thể dài hàng chục hoặc hàng trăm kilobyte nếu exception lồng nhau, có nhiều frame hoặc chứa thông tin từ nhiều thư viện.

RabbitMQ giới hạn kích thước frame AMQP qua `frame_max` được thương lượng trên kết nối. Các header của message phải nằm trong giới hạn frame phù hợp. Nếu stack trace quá lớn, nó có thể chiếm gần hết không gian dành cho header và khiến message không thể được republish như mong đợi. Spring Cloud Stream Rabbit binder cung cấp thuộc tính `frameMaxHeadroom` để dành trước một lượng byte cho các header khác khi tính kích thước stack trace được thêm vào DLQ message.

Thuộc tính này có giá trị mặc định **20.000 byte**. Nó chỉ điều chỉnh phần stack trace mà binder thêm vào header lỗi; nó không thay đổi `frame_max` của RabbitMQ và cũng không phải giới hạn kích thước payload nghiệp vụ.

## 1. Vì sao header lỗi có thể vượt giới hạn frame?

Một message AMQP có phần properties/headers và phần body. RabbitMQ truyền message qua các AMQP frame; `frame_max` giới hạn kích thước frame được dùng trên kết nối. Với message bình thường, các header nghiệp vụ như `contentType`, `correlationId`, `eventType` hoặc `tenantId` thường khá nhỏ.

Khi binder republish message lỗi tới DLQ, nó có thể thêm các header mô tả exception, ví dụ:

- `x-exception-message`: thông điệp lỗi.
- `x-exception-stacktrace`: stack trace của lỗi cuối cùng.

Stack trace có thể tăng nhanh khi:

- Exception được bọc qua nhiều lớp `cause`.
- Một lỗi xảy ra trong thư viện có stack trace rất dài.
- Exception message chứa dữ liệu đầu vào hoặc nội dung lớn.
- Framework thêm nhiều lớp xử lý bất đồng bộ, reflection hoặc proxy.
- Một batch hoặc chuỗi xử lý lỗi tạo ra thông tin chẩn đoán dài.

Nếu header stack trace cộng với phần dự phòng cho các header khác vượt quá `frame_max`, binder sẽ cắt ngắn stack trace và ghi log cảnh báo `WARN`. Mục đích là giữ đủ chỗ cho những header khác thay vì để riêng stack trace chiếm toàn bộ giới hạn.

## 2. frameMaxHeadroom là gì?

`frameMaxHeadroom` là số byte mà RabbitMQ binder dành riêng cho các header khác khi xác định lượng stack trace có thể thêm vào header DLQ. Giá trị mặc định là `20000`.

Có thể hình dung ngân sách theo cách đơn giản:

```text
frame_max của kết nối
  ├── phần dự phòng frameMaxHeadroom cho header khác
  └── phần còn lại có thể dùng cho header stack trace
```

Đây là mô hình khái niệm để hiểu cách giới hạn hoạt động, không phải công thức thay thế việc đo kích thước header thực tế. Kích thước còn phụ thuộc các header hiện có và cách AMQP/Spring AMQP mã hóa message properties.

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `frame_max` | Giới hạn kích thước frame AMQP được thương lượng giữa client và RabbitMQ trên kết nối |
| `frameMaxHeadroom` | Số byte dành trước cho các header khác khi binder thêm stack trace vào DLQ message |
| `x-exception-stacktrace` | Header chứa stack trace được binder thêm khi republish message lỗi |
| Message body | Payload nghiệp vụ, được truyền trong các content body frame; không phải phần mà `frameMaxHeadroom` giới hạn trực tiếp |

**Điểm cần nhớ:** tăng `frameMaxHeadroom` có nghĩa là dành nhiều byte hơn cho các header khác, vì vậy phần không gian còn lại cho stack trace sẽ nhỏ hơn. Nếu stack trace bị cắt vì quá dài, giải pháp chính thường là tăng `frame_max` phù hợp ở RabbitMQ hoặc giảm kích thước stack trace; không mặc định tăng `frameMaxHeadroom`.

## 3. Khi nào thuộc tính này có tác dụng?

`frameMaxHeadroom` là thuộc tính consumer của RabbitMQ binder. Nó có ý nghĩa khi binder republish message thất bại tới DLQ và thêm stack trace vào header.

Các điều kiện thường gặp:

1. Input binding sử dụng RabbitMQ binder.
2. Consumer có cấu hình DLQ, ví dụ bật `autoBindDlq` hoặc đã provision hạ tầng dead-letter phù hợp.
3. `republishToDlq` được bật để binder gửi lại message cùng metadata lỗi.
4. Stack trace được thêm vào header và cần được giới hạn để vừa với frame.

Nếu `republishToDlq` tắt, binder có thể reject message để RabbitMQ định tuyến bản message gốc qua dead-letter exchange. Trong trường hợp đó, binder không republish message kèm stack trace theo cơ chế này, nên `frameMaxHeadroom` không điều khiển header stack trace được thêm vào.

Tài liệu Rabbit binder hiện hành ghi `republishToDlq` mặc định là `true`, còn `autoBindDlq` mặc định là `false`. Hãy cấu hình rõ ràng thay vì dựa vào mặc định khi thiết kế luồng lỗi production.

## 4. Cấu hình theo từng input binding

Ví dụ ứng dụng xử lý đơn hàng với binding `processOrder-in-0`:

```yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.created
          group: order-service
          content-type: application/json
          consumer:
            maxAttempts: 3
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              frameMaxHeadroom: 20000
```

Trong cấu hình này:

- `destination` ánh xạ tới exchange của Rabbit binder.
- `group` xác định queue tiêu thụ có tên ổn định.
- `maxAttempts: 3` cho phép tối đa ba lần xử lý trong một lượt giao, bao gồm lần đầu.
- `autoBindDlq: true` yêu cầu binder khai báo DLQ và dead-letter exchange theo quy ước của binder.
- `republishToDlq: true` yêu cầu binder republish message thất bại với metadata lỗi.
- `frameMaxHeadroom: 20000` dành 20.000 byte cho các header khác khi tính phần stack trace được thêm vào.

Thuộc tính Rabbit-specific được đặt dưới `spring.cloud.stream.rabbit.bindings.<bindingName>.consumer`. Không đặt `frameMaxHeadroom` dưới `spring.cloud.stream.bindings.<bindingName>.consumer`, vì đó là namespace thuộc tính consumer chung và không phải nơi khai báo thuộc tính riêng của Rabbit binder.

## 5. Cấu hình mặc định cho nhiều binding

Nếu nhiều Rabbit input binding cần cùng một giá trị, có thể đặt default ở cấp Rabbit binder:

```yaml
spring:
  cloud:
    stream:
      rabbit:
        default:
          frameMaxHeadroom: 24000
        bindings:
          processOrder-in-0:
            consumer:
              frameMaxHeadroom: 30000
          processPayment-in-0:
            consumer:
              republishToDlq: true
              autoBindDlq: true
```

Trong ví dụ, các binding Rabbit dùng `frameMaxHeadroom` mặc định là 24.000 byte. Binding `processOrder-in-0` ghi đè thành 30.000 byte. Binding-specific property có độ ưu tiên cao hơn default tương ứng.

Không nên đặt giá trị lớn nhất có thể cho mọi binding. Mỗi luồng có tập header nghiệp vụ, độ dài exception và yêu cầu chẩn đoán khác nhau. Chọn giá trị theo kích thước header thực tế và frame limit của môi trường.

## 6. Quan hệ giữa frameMaxHeadroom và republishToDlq

Hai thuộc tính giải quyết hai việc khác nhau:

| Thuộc tính | Trách nhiệm |
| --- | --- |
| `republishToDlq` | Chọn cách binder gửi message lỗi tới DLQ; khi bật, binder thêm metadata lỗi như exception message và stack trace |
| `frameMaxHeadroom` | Dành trước dung lượng cho các header khác khi giới hạn stack trace được thêm vào message DLQ |

Ví dụ cấu hình có retry và republish:

```yaml
spring:
  cloud:
    stream:
      bindings:
        processPayment-in-0:
          destination: payments.requested
          group: payment-service
          consumer:
            maxAttempts: 4
            backOffInitialInterval: 1000
            backOffMaxInterval: 8000
            backOffMultiplier: 2.0
      rabbit:
        bindings:
          processPayment-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
              frameMaxHeadroom: 24000
```

Sau khi bốn lần thử trong một lượt giao đều thất bại, binder republish message tới DLQ theo cấu hình. `frameMaxHeadroom` ảnh hưởng phần stack trace được đính kèm ở bước republish; nó không thay đổi số lần retry và cũng không quyết định message có được gửi tới DLQ hay không.

Nếu `maxAttempts` bằng `1`, retry nội bộ bị tắt. Khi đó cần hiểu rõ `requeueRejected`: nếu bật requeue trong khi không republish tới DLQ, message có thể bị giao lại liên tục. Hãy chọn chính sách reject, requeue và DLQ một cách nhất quán để tránh vòng lặp không giới hạn.

## 7. Điều gì bị cắt ngắn khi vượt giới hạn?

Khi phần stack trace vượt ngân sách, binder cắt ngắn stack trace được thêm vào header và ghi một cảnh báo. Việc này không có nghĩa payload nghiệp vụ của message bị cắt theo cùng cơ chế. Message gốc vẫn được republish cùng phần body của nó, trong khi thông tin stack trace ở header có thể chỉ còn một phần.

Điều đó tạo ra hai yêu cầu vận hành:

- Không phụ thuộc vào header stack trace như bản lưu trữ duy nhất của bằng chứng lỗi.
- Dùng log tập trung hoặc hệ thống quan sát để lưu đầy đủ exception, correlation ID và event ID.

Nếu stack trace bị cắt, header `x-exception-message` vẫn có thể giúp nhận biết loại lỗi, nhưng cũng cần kiểm tra kích thước và nội dung của các header khác. `frameMaxHeadroom` dành chỗ cho chúng; nó không làm mọi header lớn trở nên hợp lệ nếu tổng header vượt giới hạn frame.

## 8. Ví dụ hàm consumer và exception gọn

Một consumer có thể ghi đầy đủ exception vào log tập trung, sau đó ném một exception nghiệp vụ gọn hơn để binder thêm stack trace ngắn vào DLQ header.

```java
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public record OrderCreated(String eventId, String orderId) {}

@Configuration
public class OrderConsumerConfiguration {

    private static final Logger log =
            LoggerFactory.getLogger(OrderConsumerConfiguration.class);

    @Bean
    public Consumer<OrderCreated> processOrder(OrderService orderService) {
        return event -> {
            try {
                orderService.process(event);
            }
            catch (RemoteDependencyException ex) {
                // Lưu đầy đủ cause và stack trace ở hệ thống log tập trung.
                log.error("Order processing failed; eventId={}, orderId={}",
                        event.eventId(), event.orderId(), ex);

                // Exception gọn mang mã tra cứu, không gắn lại cause lớn.
                throw new OrderProcessingException(
                        "ORDER_DEPENDENCY_FAILURE eventId=" + event.eventId());
            }
        };
    }
}
```

Ví dụ giả định `RemoteDependencyException`, `OrderService` và `OrderProcessingException` là kiểu của ứng dụng. Việc không gắn cause vào exception mới giúp stack trace republish ngắn hơn, nhưng full exception đã được ghi ở nơi có kiểm soát. Chỉ dùng cách này khi correlation/event ID cho phép tìm lại log đầy đủ; không làm mất thông tin chẩn đoán cần thiết.

Không nên cắt stack trace bằng cách loại bỏ tùy tiện mọi cause hoặc che giấu lỗi gốc. Hãy cân bằng giữa giới hạn header và khả năng điều tra, đồng thời tránh ghi payload nhạy cảm hoặc token vào exception message.

## 9. Khi nào nên thay đổi frameMaxHeadroom?

Giữ giá trị mặc định 20.000 byte khi stack trace và business headers có kích thước bình thường. Chỉ thay đổi khi đã quan sát cảnh báo hoặc đo được kích thước header thực tế.

| Tình huống | Hướng xử lý |
| --- | --- |
| Stack trace bị cắt, các header nghiệp vụ nhỏ và `frame_max` còn dư địa | Tăng `frame_max` ở RabbitMQ nếu chính sách hạ tầng cho phép, hoặc giảm stack trace |
| Ứng dụng có nhiều header nghiệp vụ lớn | Tăng `frameMaxHeadroom` để dành thêm chỗ cho các header đó; chấp nhận phần stack trace được giữ lại sẽ ngắn hơn |
| Exception có cause chain rất dài | Ghi full exception vào log tập trung, ném exception gọn có event ID/correlation ID |
| Message body lớn | Đánh giá kích thước payload và cách truyền body; `frameMaxHeadroom` không phải giới hạn body |
| Chỉ một binding có stack trace lớn | Điều chỉnh `frameMaxHeadroom` riêng cho binding đó thay vì thay đổi default toàn ứng dụng |
| Không cần stack trace trong DLQ | Cân nhắc `republishToDlq: false` và dùng dead-letter routing của broker, sau khi đánh giá việc mất metadata exception do binder thêm |

**Lưu ý về chiều điều chỉnh:** tăng `frameMaxHeadroom` dành thêm dung lượng cho các header khác và làm phần stack trace có thể giữ lại nhỏ hơn. Nếu mục tiêu là giữ nhiều stack trace hơn, hãy xem xét tăng `frame_max` hoặc giảm stack trace; không tăng headroom một cách máy móc.

## 10. frame_max được quản lý ở đâu?

`frame_max` là giới hạn giao thức AMQP được thương lượng trên kết nối RabbitMQ. Nó thuộc cấu hình kết nối/broker, khác với `frameMaxHeadroom` là thuộc tính của Rabbit binder.

Ví dụ một cấu hình broker có thể đặt giới hạn frame trong `rabbitmq.conf`:

```ini
frame_max = 262144
```

Giá trị trên chỉ là ví dụ. Trước khi thay đổi, cần kiểm tra giới hạn do phiên bản RabbitMQ, client và chính sách vận hành hỗ trợ; các kết nối hiện có có thể cần được tạo lại để thương lượng lại tham số. Không tăng `frame_max` chỉ để che một stack trace bất thường mà chưa kiểm tra nguyên nhân.

Hai lớp cấu hình có phạm vi khác nhau:

| Cấu hình | Nơi đặt | Ảnh hưởng |
| --- | --- | --- |
| `frame_max` | RabbitMQ broker/AMQP connection | Giới hạn frame được thương lượng cho kết nối |
| `frameMaxHeadroom` | `spring.cloud.stream.rabbit.bindings.<binding>.consumer` hoặc `spring.cloud.stream.rabbit.default` | Giới hạn phần stack trace binder thêm vào DLQ header, dành chỗ cho header khác |

Nếu tăng `frame_max`, hãy đánh giá bộ nhớ, kích thước frame, network và giới hạn client. Các client có thể đề xuất frame size riêng; giá trị hiệu lực là kết quả thương lượng chứ không chỉ là một dòng cấu hình trong file broker.

## 11. Chẩn đoán cảnh báo stack trace bị truncate

Khi thấy cảnh báo của Rabbit binder nói stack trace bị truncate, hãy kiểm tra theo trình tự:

1. Xác định input binding nào đang dùng `republishToDlq`.
2. Xác nhận `frameMaxHeadroom` hiệu lực từ cấu hình binding hoặc default.
3. Kiểm tra `frame_max` hiệu lực của kết nối RabbitMQ.
4. Đo kích thước các header nghiệp vụ và stack trace được tạo ra.
5. Xem exception có cause chain dài, message bất thường hoặc dữ liệu nhạy cảm không.
6. Kiểm tra log tập trung có giữ đầy đủ stack trace và event ID không.
7. Chọn thay đổi nhỏ nhất: rút gọn exception, giảm header không cần thiết, điều chỉnh headroom cho header nghiệp vụ hoặc tăng frame limit nếu được phê duyệt.
8. Tạo lại kết nối nếu thay đổi broker/client cần thương lượng frame mới.
9. Kiểm thử republish thực tế và xác nhận DLQ vẫn nhận được message cùng metadata cần thiết.

Không chỉ tăng `frame_max` hoặc giảm `frameMaxHeadroom` mà không đo. Nếu các header nghiệp vụ đã gần chạm giới hạn, giảm headroom có thể khiến việc republish thất bại hoặc không còn đủ chỗ cho header khác.

## 12. Kiểm thử cấu hình và hành vi DLQ

Nên có integration test với RabbitMQ thật hoặc Testcontainers RabbitMQ cho các tình huống:

- Consumer xử lý thành công: message được xác nhận và không xuất hiện trong DLQ.
- Consumer thất bại hết `maxAttempts`: message được chuyển tới DLQ.
- `republishToDlq: true`: DLQ message có metadata lỗi theo cấu hình.
- Stack trace ngắn: header giữ được đầy đủ nội dung dự kiến.
- Stack trace dài: binder ghi cảnh báo và stack trace bị cắt theo giới hạn; payload gốc vẫn có thể đọc được.
- Business headers lớn: kiểm tra phần headroom có đủ cho header khác.
- Binding-specific `frameMaxHeadroom` ghi đè default.
- Broker `frame_max` được thay đổi: xác minh kết nối mới thương lượng giá trị mong đợi.
- `republishToDlq: false`: xác minh dead-letter routing của broker và việc không có stack trace do binder republish thêm.
- Lỗi publish tới DLQ: kiểm tra acknowledgment/transaction và bảo đảm message không bị mất âm thầm.

Unit test có thể kiểm tra logic chọn exception gọn hoặc mapping header, nhưng không chứng minh frame negotiation và AMQP frame size. Các hành vi đó cần integration test với RabbitMQ và phiên bản binder thực tế.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
| --- | --- |
| `frameMaxHeadroom` tăng giới hạn frame của RabbitMQ | Nó chỉ dành chỗ cho header khác khi binder giới hạn stack trace; `frame_max` vẫn do broker/connection quyết định |
| Tăng `frameMaxHeadroom` giúp giữ stack trace dài hơn | Tăng headroom dành nhiều chỗ hơn cho header khác, nên phần stack trace có thể nhỏ hơn |
| Stack trace bị truncate nghĩa là payload bị mất | Thuộc tính này nhắm vào stack trace trong header lỗi, không phải payload body |
| `frameMaxHeadroom` là thuộc tính producer | Đây là thuộc tính consumer Rabbit binder, dùng khi republish lỗi tới DLQ |
| Bật `autoBindDlq` tự động thêm stack trace | `autoBindDlq` khai báo DLQ/DLX; `republishToDlq` điều khiển việc republish kèm metadata lỗi |
| Đặt thuộc tính dưới `spring.cloud.stream.bindings` là đủ | Phải dùng namespace Rabbit-specific `spring.cloud.stream.rabbit.bindings...consumer` hoặc `spring.cloud.stream.rabbit.default` |

## 14. Checklist production

Trước khi triển khai Rabbit consumer có republish DLQ:

- Đặt consumer group ổn định và xác định DLQ/DLX đích.
- Cấu hình `autoBindDlq` hoặc hạ tầng DLQ có sẵn một cách rõ ràng.
- Quyết định có cần `republishToDlq` và metadata stack trace hay không.
- Đặt retry count/backoff phù hợp với loại lỗi.
- Xác nhận `frame_max` hiệu lực và `frameMaxHeadroom` theo từng binding.
- Đo header nghiệp vụ và độ dài stack trace trong tình huống lỗi thực tế.
- Lưu full exception vào log tập trung với event ID/correlation ID.
- Không để exception message chứa payload nhạy cảm hoặc dữ liệu quá lớn.
- Theo dõi cảnh báo stack trace bị truncate và lỗi publish DLQ.
- Kiểm thử cả header nhỏ, header lớn, stack trace dài và broker reconnect.
- Xác nhận DLQ giữ payload, key, delivery mode và metadata cần thiết.
- Ghi rõ cấu hình broker và binder trong tài liệu vận hành.

## Tài liệu tham khảo

- [Spring Cloud Stream RabbitMQ Binder — Consumer Properties (`frameMaxHeadroom`, `republishToDlq`)](https://docs.spring.io/spring-cloud-stream-binder-rabbit/docs/current/reference/html/spring-cloud-stream-binder-rabbit.html)
- [Spring Cloud Stream RabbitMQ Binder — DLQ behavior](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [RabbitMQ — AMQP 0-9-1 Protocol and Frame](https://www.rabbitmq.com/amqp-0-9-1-reference)
- [RabbitMQ — Configuration](https://www.rabbitmq.com/docs/configure)

Đối chiếu tài liệu theo đúng phiên bản Spring Cloud Stream Rabbit binder, Spring AMQP và RabbitMQ đang triển khai. Đặc biệt kiểm tra default của `frameMaxHeadroom`, cấu hình `republishToDlq`, header được mapper giữ lại và giới hạn frame thực tế trên kết nối.

## Kết luận

Khi Rabbit binder republish message lỗi tới DLQ, stack trace được thêm vào header có thể quá lớn so với `frame_max`. `frameMaxHeadroom` dành trước byte cho các header khác; mặc định là 20.000 byte. Nếu stack trace cộng với phần dự phòng vượt giới hạn, binder cắt ngắn stack trace và ghi cảnh báo. Thuộc tính này không thay đổi `frame_max` và không giới hạn payload body. Muốn giữ thông tin lỗi hữu ích, hãy cấu hình nó ở đúng Rabbit consumer binding, đo kích thước header, lưu full exception trong log tập trung và chỉ điều chỉnh broker frame hoặc stack trace sau khi đã kiểm tra tác động.
