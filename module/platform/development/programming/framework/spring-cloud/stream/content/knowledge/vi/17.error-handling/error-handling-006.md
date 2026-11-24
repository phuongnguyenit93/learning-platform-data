# Consumer<ErrorMessage> và error-handler-definition

Khi một thông điệp đi vào input binding của Spring Cloud Stream và hàm xử lý ném exception, framework cần chuyển lỗi đến một cơ chế xử lý phù hợp. Với mô hình functional, ứng dụng có thể đăng ký một bean Consumer<ErrorMessage> để nhận thông tin lỗi cùng thông điệp đã gây ra lỗi. Thuộc tính error-handler-definition liên kết bean đó với input binding cần xử lý.

Cơ chế này hữu ích khi ứng dụng cần ghi nhận lỗi nghiệp vụ, tạo bản ghi kiểm toán, gửi cảnh báo hoặc gọi một dịch vụ hỗ trợ. Tuy nhiên, custom error handler là một lựa chọn ở cấp ứng dụng và thay thế các error handler mặc định của framework/binder cho binding đó. Nếu chọn cách này, cấu hình DLQ của binder sẽ không tự thực hiện việc gửi thông điệp thất bại vào DLQ. Cần hiểu rõ sự khác nhau giữa xử lý lỗi trong ứng dụng và xử lý lỗi do broker/binder đảm nhiệm trước khi chọn.

## 1. ErrorMessage chứa những thông tin gì?

org.springframework.messaging.support.ErrorMessage là một Spring Message có payload kiểu Throwable. Payload thường là exception được ném trong quá trình xử lý. Trong nhiều trường hợp, exception đó là MessagingException và có thể chứa thông điệp đã thất bại.

Một ErrorMessage có thể cung cấp:

| Thành phần | Ý nghĩa |
|---|---|
| getPayload() | Exception gây lỗi, kiểu Throwable |
| getHeaders() | Header của ErrorMessage, có thể chứa metadata phục vụ chẩn đoán |
| getOriginalMessage() | Thông điệp gốc tại điểm tạo ErrorMessage, nếu có |
| MessagingException.getFailedMessage() | Thông điệp thất bại được exception giữ lại, nếu payload là MessagingException và có dữ liệu này |

Không nên giả định getOriginalMessage() luôn khác null. Một số lỗi xảy ra trước khi framework có thể gắn thông điệp gốc vào ErrorMessage. Hãy kiểm tra null trước khi đọc payload hoặc header của original message.

Ví dụ:

~~~java
ErrorMessage errorMessage = ...;

Throwable failure = errorMessage.getPayload();
Message<?> original = errorMessage.getOriginalMessage();

if (original != null) {
    Object messageId = original.getHeaders().getId();
    Object payload = original.getPayload();
}
~~~

ErrorMessage không phải là payload nghiệp vụ ban đầu. Payload của nó là exception. Muốn đọc dữ liệu đơn hàng, mã sự kiện hoặc header correlation, cần lấy từ original message hoặc failed message có trong exception.

## 2. Đường đi của lỗi trong một input binding

Với imperative Function hoặc Consumer, khi message handler ném exception, lỗi được truyền về binder. Cơ chế retry của binder/framework có thể thử lại thông điệp trước khi chuyển lỗi đến cơ chế xử lý cuối cùng. Sau khi các lần thử thất bại, framework có thể:

- Ghi log lỗi.
- Chuyển lỗi đến custom error handler của ứng dụng.
- Dùng cơ chế riêng của binder để requeue hoặc gửi message đến Dead Letter Queue (DLQ), nếu được cấu hình và broker hỗ trợ.

~~~mermaid
flowchart TD
    A["Broker gửi message"] --> B["Input binding"]
    B --> C["Function / Consumer"]
    C -->|Thành công| D["Hoàn tất xử lý"]
    C -->|Ném exception| E["Retry theo cấu hình"]
    E -->|Còn lượt thử| C
    E -->|Hết lượt thử| F{"Cơ chế xử lý lỗi"}
    F --> G["Consumer<ErrorMessage>"]
    F --> H["Binder handler / DLQ"]
    F --> I["Log và xử lý mặc định"]
~~~

Số lần thử và hành vi cuối phụ thuộc mô hình lập trình, binder và cấu hình. Tài liệu Spring Cloud Stream hiện hành mô tả retry mặc định ba lần cho message handler imperative; sau đó binder quyết định việc drop, requeue hoặc DLQ theo khả năng và cấu hình của nó.

Không áp dụng sơ đồ này một cách máy móc cho reactive function. Reactive function kết nối các Publisher thay vì xử lý từng message như imperative handler. Lỗi bên trong Reactor pipeline cần được xử lý bằng toán tử như onErrorResume hoặc retryWhen.

## 3. Tạo Consumer<ErrorMessage> làm custom error handler

Một custom error handler là một bean function có kiểu Consumer<ErrorMessage>. Bean được đăng ký trong Spring Function Catalog, nhưng không tự động trở thành handler cho mọi binding. Cần chỉ rõ tên bean bằng error-handler-definition.

Ví dụ dưới đây ghi lại thông tin lỗi và metadata của thông điệp gốc. Phần ghi nhận được đặt sau một interface để có thể thay bằng database, hệ thống audit hoặc dịch vụ cảnh báo:

~~~java
import java.time.Instant;
import java.util.function.Consumer;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;

record FailureRecord(
    String bindingName,
    String messageId,
    String exceptionType,
    String exceptionMessage,
    Instant occurredAt
) {}

@FunctionalInterface
interface FailureRecorder {
    void record(FailureRecord record);
}

@Configuration
class OrderErrorConfiguration {

    private static final Logger log =
        LoggerFactory.getLogger(OrderErrorConfiguration.class);

    @Bean
    Consumer<ErrorMessage> orderErrorHandler(FailureRecorder recorder) {
        return error -> {
            Throwable failure = error.getPayload();
            Message<?> original = error.getOriginalMessage();

            String messageId = original == null
                ? "unknown"
                : String.valueOf(original.getHeaders().getId());

            String payloadType = original == null
                ? "unknown"
                : original.getPayload().getClass().getSimpleName();

            log.error(
                "Order processing failed: messageId={}, payloadType={}",
                messageId,
                payloadType,
                failure
            );

            recorder.record(new FailureRecord(
                "processOrder-in-0",
                messageId,
                failure.getClass().getName(),
                failure.getMessage(),
                Instant.now()
            ));
        };
    }
}
~~~

Trong ví dụ:

- orderErrorHandler là tên bean được tham chiếu từ cấu hình.
- getPayload() lấy exception để ghi loại lỗi và stack trace.
- getOriginalMessage() lấy message ban đầu nếu framework cung cấp.
- FailureRecorder tách thao tác ghi nhận khỏi phần đọc ErrorMessage.
- Handler chỉ ghi metadata cần thiết; không log toàn bộ payload vì message có thể chứa dữ liệu cá nhân, thông tin thanh toán hoặc bí mật nghiệp vụ.

Một ErrorMessage có thể không có original message. Handler nên tiếp tục xử lý được trường hợp này thay vì ném thêm NullPointerException. Cũng cần thiết kế FailureRecorder có timeout và khả năng phục hồi phù hợp; nếu chính thao tác ghi audit thất bại, đừng để lỗi phụ che mất exception ban đầu.

## 4. Gắn handler với một input binding bằng error-handler-definition

Giả sử ứng dụng có Function tên processOrder, input binding mặc định là processOrder-in-0. Cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          error-handler-definition: orderErrorHandler
~~~

Thuộc tính cần chú ý:

~~~text
spring.cloud.stream.bindings.processOrder-in-0.error-handler-definition
~~~

Giá trị orderErrorHandler phải trùng tên bean Consumer<ErrorMessage> đã đăng ký. Thuộc tính nằm trực tiếp dưới binding, ngang cấp với destination, group và consumer; không đặt nó bên trong consumer.

error-handler-definition liên kết error handler với binding đầu vào. Nó không phải tên destination, tên consumer group hoặc tên bean nghiệp vụ. Bean processOrder tiếp tục xử lý message bình thường; bean orderErrorHandler chỉ nhận ErrorMessage khi binding gặp lỗi theo cơ chế tương ứng.

Nên khai báo rõ spring.cloud.function.definition để xác định các function nghiệp vụ cần kích hoạt. Error handler cũng nằm trong Function Catalog; nếu ứng dụng có nhiều bean hàm, khai báo definition tường minh giúp tránh việc tự phát hiện hàm không như dự định.

## 5. Dùng một error handler mặc định cho nhiều function

Nếu nhiều input binding cần cùng một cách ghi nhận lỗi, có thể cấu hình một handler mặc định:

~~~yaml
spring:
  cloud:
    function:
      definition: "processOrder;processShipment"
    stream:
      default:
        error-handler-definition: commonErrorHandler
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
        processShipment-in-0:
          destination: shipments.submitted
          group: shipment-service
~~~

Bean commonErrorHandler là Consumer<ErrorMessage> được dùng làm handler mặc định cho các function binding. Cấu hình này phù hợp khi chính sách audit, cảnh báo và lưu lỗi giống nhau.

Nếu một binding cần thông tin hoặc cách xử lý riêng, khai báo error-handler-definition ngay tại binding đó. Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: "processOrder;processShipment"
    stream:
      default:
        error-handler-definition: commonErrorHandler
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          error-handler-definition: orderErrorHandler
        processShipment-in-0:
          destination: shipments.submitted
          group: shipment-service
~~~

Ở đây processOrder-in-0 dùng handler riêng orderErrorHandler; processShipment-in-0 dùng handler mặc định commonErrorHandler. Hãy đặt tên bean và binding rõ ràng để dễ theo dõi khi có nhiều luồng.

## 6. Ánh xạ tên binding tường minh

Nếu ứng dụng đổi tên binding mặc định bằng spring.cloud.stream.function.bindings, thuộc tính error-handler-definition phải dùng tên binding sau ánh xạ.

Ví dụ:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
      bindings:
        processOrder-in-0: ordersInput
    stream:
      bindings:
        ordersInput:
          destination: orders.submitted
          group: order-service
          error-handler-definition: orderErrorHandler
~~~

Sau ánh xạ, ordersInput là tên binding được dùng trong cấu hình Stream. Vì vậy, handler được đặt tại:

~~~text
spring.cloud.stream.bindings.ordersInput.error-handler-definition
~~~

Nếu ánh xạ input thành ordersInput nhưng vẫn đặt handler ở processOrder-in-0, cấu hình có thể không được áp dụng cho binding thực tế. Khi chẩn đoán, hãy kiểm tra tên binding sau ánh xạ trước khi kiểm tra tên bean handler.

## 7. Phân biệt custom error handler với retry và DLQ

Ba cơ chế có trách nhiệm khác nhau:

| Cơ chế | Trách nhiệm | Ví dụ cấu hình |
|---|---|---|
| Retry | Thử xử lý lại message khi lỗi có thể tạm thời | consumer.max-attempts, backoff |
| Custom error handler | Nhận ErrorMessage để audit, thông báo hoặc thực hiện xử lý ứng dụng | error-handler-definition |
| Binder DLQ | Đưa message thất bại vào destination lỗi của broker để kiểm tra hoặc phát lại | enable-dlq, auto-bind-dlq |

Custom error handler của Spring Cloud Stream loại trừ các error handler mặc định do framework/binder cung cấp để chúng không can thiệp lẫn nhau. Khi gắn custom Consumer<ErrorMessage>, cơ chế binder-specific DLQ sẽ không gửi message thất bại vào DLQ, kể cả khi cấu hình DLQ vẫn bật.

Đây là điểm quan trọng khi thiết kế:

- Chọn Consumer<ErrorMessage> khi ứng dụng cần tự xử lý thông tin lỗi, ví dụ ghi audit hoặc gửi cảnh báo.
- Chọn DLQ của binder khi cần broker lưu giữ message thất bại để đội vận hành xem xét hoặc phát lại.
- Nếu cần cả audit và DLQ, có thể dùng DLQ của broker rồi triển khai một consumer riêng đọc DLQ để ghi audit. Cách này giữ nguyên trách nhiệm lưu giữ message ở broker.

Không nên bật custom error handler và đồng thời kỳ vọng binder tự động DLQ cùng message đó. Nếu handler tự gửi message sang một destination khác, đó là logic do ứng dụng tự triển khai; cần tự quản lý lỗi khi gửi, chống lặp và vòng lặp gửi lỗi.

## 8. Cấu hình retry trước khi chuyển lỗi

Với imperative message handler, có thể cấu hình số lần thử và khoảng chờ trên input binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
          error-handler-definition: orderErrorHandler
~~~

max-attempts là tổng số lần thử xử lý theo cấu hình retry. Các thuộc tính backoff điều khiển khoảng chờ tăng dần giữa các lần thử. Giá trị mặc định thường là ba lần thử, khoảng chờ ban đầu một giây, tối đa mười giây và multiplier bằng hai; hãy xác minh với phiên bản Spring Cloud Stream và binder của dự án.

Retry phù hợp với lỗi tạm thời như timeout dịch vụ phụ thuộc hoặc kết nối gián đoạn. Không nên retry vô hạn với dữ liệu sai schema hoặc vi phạm quy tắc nghiệp vụ vì lần thử tiếp theo thường không sửa được dữ liệu.

Sau khi retry hết lượt, custom error handler có thể ghi nhận ErrorMessage. Handler không tự làm cho message được retry lại lần nữa. Nếu muốn xử lý lại, cần có chính sách riêng như DLQ, outbox, thao tác replay có kiểm soát hoặc một lệnh nghiệp vụ mới.

## 9. Khi nào dùng DLQ của Kafka hoặc RabbitMQ?

Nếu mục tiêu là giữ lại message thất bại tại broker, hãy dùng tính năng DLQ do binder hỗ trợ thay vì custom Consumer<ErrorMessage>.

### 9.1. Kafka binder

Kafka binder yêu cầu consumer group tường minh để bật DLQ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 3
    kafka:
      bindings:
        processOrder-in-0:
          consumer:
            enable-dlq: true
~~~

Sau khi các lần thử thất bại, binder chuyển record sang DLQ theo cấu hình. Tên mặc định thường có dạng error.<destination>.<group>; có thể tùy chỉnh bằng thuộc tính DLQ của Kafka binder. Kiểm tra số partition của DLQ vì Kafka binder mặc định có thể gửi record vào cùng partition number với record gốc.

### 9.2. RabbitMQ binder

RabbitMQ binder có thể tự tạo dead-letter queue cho consumer binding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders.submitted
          group: order-service
          consumer:
            max-attempts: 3
    rabbit:
      bindings:
        processOrder-in-0:
          consumer:
            auto-bind-dlq: true
~~~

Rabbit binder tạo queue DLQ gắn với topology tương ứng. Các thuộc tính như requeue, republish-to-dlq và dead-letter exchange có ngữ nghĩa riêng; hãy tham khảo tài liệu đúng phiên bản Rabbit binder.

Không sao chép cấu hình Kafka DLQ sang RabbitMQ hoặc ngược lại. Với Pulsar, cần kiểm tra dead-letter policy và khả năng của Pulsar binder/Spring for Apache Pulsar đang dùng.

## 10. Phạm vi của error-handler-definition

error-handler-definition được dùng để liên kết custom error consumer với lỗi của input binding trong mô hình message handler. Không nên xem nó như một bộ xử lý mọi lỗi trong ứng dụng.

| Loại lỗi | Cơ chế cần xem xét |
|---|---|
| Function imperative ném exception khi xử lý message | Retry và error handler gắn với input binding |
| Consumer imperative ném exception | Retry và error handler gắn với input binding |
| Lỗi trong reactive Function<Flux<T>, Flux<R>> | Toán tử Reactor như onErrorResume, retryWhen; không áp dụng nguyên cơ chế RetryTemplate của imperative handler |
| Lỗi gửi message ở output binding | Error channel/producer error handling và tính năng của binder |
| Lỗi deserialize trước khi message handler nhận payload | Cơ chế deserialization error handler riêng của binder, ví dụ Kafka hoặc Kafka Streams |
| Lỗi khởi tạo kết nối broker hoặc cấu hình binding | Log khởi động, binder health, retry kết nối và cấu hình vận hành |

Nếu một lỗi xảy ra trước khi framework tạo message cho input handler, không nên mặc định rằng custom Consumer<ErrorMessage> của binding sẽ nhận được nó. Ví dụ Kafka deserialization exception có thể được xử lý bởi cơ chế deserialization exception handler riêng của Kafka binder hoặc Kafka Streams binder.

Tương tự, lỗi phát sinh khi gửi message từ output binding không phải lỗi xử lý của input binding. Cần dùng cơ chế error channel hoặc producer error handling tương ứng.

## 11. Viết handler an toàn và có thể vận hành

Custom error handler thường chạy trên đường xử lý lỗi. Nếu chính handler ném exception, việc xử lý lỗi ban đầu có thể trở nên khó dự đoán. Hãy thiết kế handler như một thành phần vận hành có giới hạn rõ ràng:

- Kiểm tra ErrorMessage.getOriginalMessage() có thể null.
- Lấy exception từ getPayload() và giữ nguyên nguyên nhân gốc khi ghi log.
- Ghi message ID, binding, exception type và thời điểm; chỉ lưu payload khi có chính sách dữ liệu phù hợp.
- Không log token, mật khẩu, thông tin thanh toán hoặc toàn bộ payload nhạy cảm.
- Đặt timeout cho HTTP call hoặc thao tác audit bên ngoài.
- Dùng khóa idempotency khi ghi bản ghi lỗi để tránh nhân đôi khi message được giao lại.
- Phân biệt lỗi tạm thời với lỗi dữ liệu không thể khắc phục.
- Đặt cảnh báo khi tỷ lệ lỗi tăng, không gửi một thông báo vận hành cho mọi message lỗi nếu lưu lượng cao.
- Theo dõi lỗi của chính error handler, không để chúng biến mất trong log chung.

Một handler nên làm một số tác vụ có thể hoàn thành nhanh và đáng tin cậy. Nếu cần xử lý điều tra dài, hãy lưu metadata lỗi rồi chuyển công việc sang một queue hoặc hệ thống xử lý riêng.

## 12. Kiểm thử Consumer<ErrorMessage>

Nên kiểm thử riêng logic của error handler và cách framework gắn handler vào binding.

### 12.1. Unit test trực tiếp Consumer

Có thể tạo ErrorMessage trong bộ nhớ để xác minh handler đọc được exception và original message:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.ErrorMessage;
import org.springframework.messaging.support.MessageBuilder;

class OrderErrorHandlerTest {

    @Test
    void recordsExceptionAndOriginalMessageId() {
        List<FailureRecord> records = new ArrayList<>();
        FailureRecorder recorder = records::add;
        var configuration = new OrderErrorConfiguration();
        var handler = configuration.orderErrorHandler(recorder);

        Message<String> original = MessageBuilder
            .withPayload("order-900")
            .build();
        ErrorMessage error = new ErrorMessage(
            new IllegalStateException("inventory unavailable"),
            original
        );

        handler.accept(error);

        assertEquals(1, records.size());
        assertEquals(
            original.getHeaders().getId().toString(),
            records.get(0).messageId()
        );
        assertEquals(
            IllegalStateException.class.getName(),
            records.get(0).exceptionType()
        );
    }
}
~~~

Test này xác minh logic xử lý ErrorMessage mà không cần broker. Có thể bổ sung trường hợp originalMessage là null và trường hợp FailureRecorder ném exception.

### 12.2. Integration test với Test Binder

Để kiểm tra wiring, tạo một input function cố ý ném exception với một payload nhất định, cấu hình error-handler-definition, gửi message vào input destination của Test Binder và xác minh recorder nhận được ErrorMessage tương ứng.

Integration test nên xác minh:

1. Tên bean trong error-handler-definition được tìm thấy trong Function Catalog.
2. Binding được chọn đúng và handler không bị đăng ký như một input function bình thường.
3. ErrorMessage có exception mong đợi.
4. Original message và message ID được giữ lại nếu binder/framework cung cấp.
5. Handler mặc định hoặc handler riêng được gọi đúng theo cấu hình.
6. Khi dùng DLQ, test xác minh cơ chế binder-native riêng và không cấu hình custom handler cùng lúc.

Test Binder hữu ích để kiểm tra đường đi thông điệp trong ứng dụng, nhưng không thay thế integration test với broker thật cho acknowledgement, retry, requeue và DLQ.

## 13. Quy trình chọn và cấu hình error handler

Khi một binding cần xử lý lỗi, thực hiện theo thứ tự:

1. Xác định lỗi xảy ra trong imperative handler, reactive pipeline, deserialization hay producer.
2. Xác định binding đầu vào và tên binding sau khi ánh xạ.
3. Quyết định ứng dụng cần custom error consumer hay muốn binder quản lý retry/requeue/DLQ.
4. Nếu chọn custom handler, tạo bean Consumer<ErrorMessage> với xử lý null và lỗi phụ thuộc rõ ràng.
5. Khai báo spring.cloud.function.definition cho các function nghiệp vụ.
6. Đặt error-handler-definition trực tiếp dưới binding hoặc cấu hình spring.cloud.stream.default.error-handler-definition nếu dùng chung.
7. Cấu hình retry cho lỗi tạm thời nếu cần và kiểm tra hành vi sau lần thử cuối.
8. Không kỳ vọng binder DLQ tự hoạt động khi custom error handler đang được gắn.
9. Viết unit test cho Consumer và integration test cho wiring.
10. Quan sát log, metric, audit record và backlog để xác nhận lỗi được xử lý theo đúng chính sách.

## 14. Những lỗi cấu hình thường gặp

| Biểu hiện | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Handler không được gọi | Sai tên bean trong error-handler-definition | So khớp tên bean và cấu hình |
| Handler gắn nhầm binding | Dùng tên binding cũ sau khi ánh xạ | Dùng alias sau spring.cloud.stream.function.bindings |
| Ứng dụng báo không xác định được function | Có nhiều bean function nhưng thiếu spring.cloud.function.definition | Khai báo rõ function nghiệp vụ |
| Không thấy DLQ dù đã bật | Custom error handler đang thay thế binder error handler | Chọn một cơ chế: custom handler hoặc binder DLQ |
| Handler ném NullPointerException | Giả định original message luôn tồn tại | Kiểm tra null trước khi đọc message |
| Lỗi vẫn xuất hiện sau khi ghi audit | Handler không làm thay đổi nguyên nhân gốc hoặc tác vụ downstream còn lỗi | Phân biệt audit với retry/requeue và kiểm tra binder |
| Không nhận lỗi deserialize | Lỗi xảy ra trước message handler | Dùng cơ chế deserialization error handler riêng của binder |
| Lỗi producer không vào handler | error-handler-definition đang gắn với input binding | Kiểm tra producer error channel và binder-specific handler |

## Tài liệu tham khảo chính thức

- [Spring Cloud Stream - Error Handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html): Consumer<ErrorMessage>, error-handler-definition, handler mặc định, retry và DLQ.
- [Spring Framework - ErrorMessage Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ErrorMessage.html): payload Throwable và getOriginalMessage().
- [Spring Cloud Stream - Kafka Dead-Letter Topic Processing](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder/dlq.html): điều kiện group, retry và bật DLQ cho Kafka binder.
- [Spring Cloud Stream - Kafka Binder Reference](https://docs.spring.io/spring-cloud-stream/docs/current/reference/html/spring-cloud-stream-binder-kafka.html): thuộc tính DLQ và cấu hình riêng của Kafka consumer.
