# Chọn exception được thử lại và exception không được thử lại

Trong hệ thống xử lý sự kiện, một message có thể thất bại vì nhiều nguyên nhân: dịch vụ phụ thuộc tạm thời không sẵn sàng, mạng bị timeout, dữ liệu không hợp lệ hoặc quy tắc nghiệp vụ từ chối yêu cầu. Nếu thử lại mọi lỗi, ứng dụng có thể lặp vô ích với dữ liệu sai, tạo tải lớn hơn khi hệ thống đang sự cố hoặc thực hiện một tác động nghiệp vụ nhiều lần. Nếu không thử lại lỗi tạm thời, message có thể bị đưa vào xử lý lỗi dù chỉ cần chờ một khoảng ngắn.

Spring Cloud Stream cho phép cấu hình chính sách retry ở từng consumer binding và phân loại exception bằng `retryableExceptions` cùng `defaultRetryable`. Bài học này trình bày cách phân biệt lỗi tạm thời với lỗi vĩnh viễn, chọn số lần thử và backoff, đưa message không thể xử lý vào dead-letter queue (DLQ), cũng như kiểm thử hành vi theo binder Kafka, RabbitMQ hoặc Pulsar.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt exception tạm thời có thể phục hồi với exception không thể phục hồi bằng retry.
- Chọn exception được thử lại và exception bị từ chối retry theo ngữ cảnh nghiệp vụ.
- Cấu hình `maxAttempts`, `backOffInitialInterval`, `backOffMaxInterval` và `backOffMultiplier`.
- Dùng `retryableExceptions` và `defaultRetryable` để phân loại lỗi theo kiểu exception.
- Hiểu thứ tự retry, recovery và DLQ trong xử lý consumer.
- Phân biệt retry của imperative consumer với retry trong reactive pipeline.
- Thiết kế idempotency, log và metric để tránh tác động lặp.
- Kiểm thử cả lỗi retryable, non-retryable và lỗi sau khi hết số lần thử.

## 1. Vì sao phải phân loại exception?

Retry có ích khi cùng một thao tác có khả năng thành công nếu thực hiện lại sau một khoảng thời gian. Ví dụ, dịch vụ kho tạm thời không phản hồi hoặc kết nối broker phụ trợ vừa bị gián đoạn. Trong khi đó, một message chứa mã đơn hàng sai hoặc vi phạm quy tắc nghiệp vụ thường không thể trở nên hợp lệ chỉ bằng cách gửi lại.

Có thể chia lỗi thành hai nhóm chính:

| Nhóm lỗi | Đặc điểm | Hành động thường phù hợp |
|---|---|---|
| Transient / tạm thời | Nguyên nhân có thể tự hết sau một khoảng thời gian | Retry có giới hạn và backoff |
| Permanent / không thể phục hồi bằng retry | Dữ liệu, quyền hoặc quy tắc không hợp lệ | Không retry; chuyển DLQ hoặc luồng xử lý lỗi |

Phân loại cần dựa trên nguyên nhân và khả năng phục hồi, không chỉ dựa vào việc exception là checked hay unchecked. Một `RuntimeException` có thể là lỗi tạm thời; một exception checked có thể biểu thị dữ liệu sai vĩnh viễn.

### Ví dụ lỗi thường có thể retry

- Timeout khi gọi dịch vụ kho hoặc thanh toán, nếu thao tác có thể được gọi lại an toàn.
- Kết nối database tạm thời bị gián đoạn.
- Dịch vụ phụ thuộc trả HTTP 503 hoặc 429 và có chính sách chờ phù hợp.
- Lỗi leader/partition tạm thời trong hạ tầng phân tán.
- Schema registry tạm thời không truy cập được, trong khi schema đã được phát hành hợp lệ.

### Ví dụ lỗi thường không nên retry

- Dữ liệu đầu vào thiếu trường bắt buộc hoặc sai định dạng.
- Đơn hàng vi phạm quy tắc nghiệp vụ, chẳng hạn tổng tiền âm.
- Currency hoặc loại sự kiện không được hỗ trợ.
- Schema không tương thích hoặc payload không thể giải mã do producer gửi sai wire format.
- Người gọi không có quyền thực hiện thao tác.
- Cấu hình sai cố định, ví dụ endpoint hoặc credentials không hợp lệ.

Có ngoại lệ theo ngữ cảnh: HTTP 401 do token hết hạn có thể phục hồi sau khi làm mới token; HTTP 429 có thể retry sau thời gian server yêu cầu; lỗi schema registry do timeout có thể tạm thời, còn schema bị registry từ chối vì vi phạm compatibility thường là lỗi vĩnh viễn. Hãy phân loại theo nguyên nhân cụ thể.

## 2. Thiết kế exception theo ý nghĩa phục hồi

Nên dùng các exception thể hiện rõ lý do và khả năng phục hồi. Ví dụ:

~~~java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}

public class UnsupportedCurrencyException extends RuntimeException {
    public UnsupportedCurrencyException(String message) {
        super(message);
    }
}

public class TemporaryInventoryException extends RuntimeException {
    public TemporaryInventoryException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class RemoteServiceTimeoutException extends RuntimeException {
    public RemoteServiceTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Tên exception giúp người đọc hiểu lý do xử lý thất bại. Ví dụ:

- `InvalidOrderException`: message hợp lệ về mặt cú pháp nhưng vi phạm quy tắc nghiệp vụ; retry không làm thay đổi dữ liệu.
- `UnsupportedCurrencyException`: loại tiền không được hệ thống hỗ trợ; cần sửa dữ liệu hoặc hợp đồng.
- `TemporaryInventoryException`: dịch vụ kho tạm thời không sẵn sàng; có thể retry.
- `RemoteServiceTimeoutException`: chưa nhận được phản hồi đúng hạn; cần đánh giá liệu thao tác phía xa có thể đã hoàn tất hay chưa.

Không nên bắt mọi exception rồi chuyển thành một exception chung như `RuntimeException` nếu việc đó làm mất thông tin phân loại. Nếu phải bọc exception, giữ nguyên cause để bộ phân loại hoặc error handler có thể kiểm tra nguyên nhân gốc.

### Exception wrapper và cause

Trong ứng dụng messaging, lỗi có thể được bọc bởi `MessagingException`, `CompletionException` hoặc exception của client. Exception ngoài cùng chưa chắc là nguyên nhân cần phân loại. Hãy kiểm tra chuỗi cause và kiểm thử cách binder/RetryPolicy nhận exception thực tế.

Nếu một `TemporaryInventoryException` bị bọc trong một exception chung mà classifier chỉ xét kiểu ngoài cùng, chính sách có thể không hoạt động như mong đợi. Với hệ thống cần phân loại theo root cause, có thể dùng custom classifier hoặc retry policy; cần xác minh semantics của phiên bản Spring Retry và Spring Cloud Stream đang dùng.

## 3. Cấu hình retry ở consumer binding

Spring Cloud Stream cung cấp các thuộc tính consumer để điều khiển retry:

| Thuộc tính | Ý nghĩa |
|---|---|
| `maxAttempts` | Tổng số lần gọi handler tối đa, bao gồm lần đầu |
| `backOffInitialInterval` | Khoảng chờ trước lần retry đầu tiên, tính bằng mili giây |
| `backOffMaxInterval` | Giới hạn trên của khoảng chờ giữa các lần retry |
| `backOffMultiplier` | Hệ số nhân để tăng khoảng chờ sau mỗi lần thất bại |
| `defaultRetryable` | Mặc định phân loại exception không được liệt kê là retryable hay không |
| `retryableExceptions` | Map tên đầy đủ của exception class sang giá trị true/false |

Ví dụ cấu hình consumer xử lý đơn hàng:

~~~yaml
spring:
  cloud:
    function:
      definition: processOrder
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 4
            backOffInitialInterval: 500
            backOffMaxInterval: 5000
            backOffMultiplier: 2.0
            defaultRetryable: false
            retryableExceptions:
              com.example.order.TemporaryInventoryException: true
              com.example.order.RemoteServiceTimeoutException: true
              com.example.order.InvalidOrderException: false
              com.example.order.UnsupportedCurrencyException: false
~~~

Cấu hình này có nghĩa:

- Handler được gọi tối đa bốn lần: một lần ban đầu và tối đa ba lần retry.
- Khoảng chờ tăng theo cấp số nhân từ 500 ms, không vượt quá 5.000 ms.
- Chỉ những exception được đánh dấu `true` mới được retry.
- Exception không có trong map mặc định không được retry vì `defaultRetryable: false`.
- Lỗi nghiệp vụ được đánh dấu `false` sẽ đi thẳng đến bước recovery/error handling.

Đặt `defaultRetryable: false` là cách tiếp cận thận trọng khi muốn chỉ retry những lỗi đã được xác định rõ. Nếu ứng dụng chọn `defaultRetryable: true`, các exception không được liệt kê sẽ theo mặc định được xem là retryable; điều này có thể khiến lỗi dữ liệu hoặc lỗi lập trình bị lặp nhiều lần.

### maxAttempts tính như thế nào?

`maxAttempts` bao gồm lần gọi đầu tiên. Ví dụ:

| maxAttempts | Số lần thực hiện tối đa | Số lần retry tối đa |
|---:|---:|---:|
| 1 | 1 | 0 |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 3 |

Đặt `maxAttempts: 1` để không thực hiện retry ở chính sách consumer này. Điều đó không có nghĩa toàn hệ thống không thể retry ở tầng khác; binder client, service method hoặc producer có thể có chính sách riêng.

## 4. Hiểu backoff và ngân sách retry

Nếu retry liên tiếp không có khoảng chờ, nhiều consumer có thể đồng loạt gọi lại dịch vụ đang gặp sự cố. Hiện tượng này tạo retry storm và làm dịch vụ khó phục hồi hơn.

Backoff tăng thời gian chờ sau mỗi lần thất bại. Với cấu hình:

~~~yaml
consumer:
  maxAttempts: 4
  backOffInitialInterval: 500
  backOffMaxInterval: 5000
  backOffMultiplier: 2.0
~~~

Khoảng chờ minh họa giữa các lần thử là:

| Lần retry | Khoảng chờ dự kiến |
|---:|---:|
| 1 | 500 ms |
| 2 | 1.000 ms |
| 3 | 2.000 ms |

Thời gian thực tế phụ thuộc chính sách retry và thời gian xử lý mỗi lần gọi. `backOffMaxInterval` giới hạn khoảng chờ tối đa. Hệ thống có thể cần một retry budget tổng thể để bảo đảm thời gian xử lý không vượt SLA.

### Khi nào cần jitter?

Nếu nhiều consumer cùng thất bại tại một thời điểm, backoff cố định theo cùng một lịch có thể khiến chúng retry đồng loạt. Jitter thêm độ lệch ngẫu nhiên vào thời gian chờ để phân tán tải. Các thuộc tính backoff cơ bản nêu trên không nên được hiểu là tự động bật jitter; nếu cần, dùng retry policy tùy chỉnh hoặc cơ chế hỗ trợ jitter phù hợp với phiên bản.

### Đừng retry quá lâu

Thời gian retry cần được cân nhắc cùng:

- Thời gian message còn được giữ trên broker.
- SLA xử lý nghiệp vụ.
- Thời gian timeout của lời gọi phụ thuộc.
- Số consumer và lưu lượng retry đồng thời.
- Khả năng xử lý message cũ sau khi hệ thống phục hồi.

Nếu một message không thể xử lý trong ngân sách thời gian cho phép, chuyển nó sang luồng lỗi để điều tra thường tốt hơn giữ consumer bận trong thời gian dài.

## 5. Phân loại exception bằng retryableExceptions

`retryableExceptions` là map từ tên class đầy đủ sang boolean. Giá trị `true` cho biết exception được đánh dấu retryable; `false` cho biết không retry exception đó.

Ví dụ tối giản:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        inventory-in-0:
          consumer:
            defaultRetryable: false
            retryableExceptions:
              com.example.InventoryUnavailableException: true
              com.example.InvalidSkuException: false
~~~

Khi `InventoryUnavailableException` xảy ra, consumer áp dụng retry policy và backoff. Khi `InvalidSkuException` xảy ra, consumer không lặp lại handler theo retry policy đó mà chuyển sang bước xử lý lỗi/recovery.

Nếu exception không có trong map, `defaultRetryable` quyết định hành vi. Nên khai báo rõ những lỗi quan trọng và có test cho exception thực tế, đặc biệt khi lỗi bị bọc bởi framework hoặc thư viện client.

### Bảng quyết định mẫu

| Exception | Phân loại | Lý do | Chính sách |
|---|---|---|---|
| `TemporaryInventoryException` | Retryable | Dịch vụ kho tạm thời không sẵn sàng | Retry có giới hạn |
| `RemoteServiceTimeoutException` | Có điều kiện | Có thể timeout dù thao tác phía xa đã hoàn tất | Retry khi thao tác idempotent |
| `InvalidOrderException` | Non-retryable | Dữ liệu nghiệp vụ không hợp lệ | Chuyển DLQ hoặc xử lý thủ công |
| `UnsupportedCurrencyException` | Non-retryable | Hợp đồng không hỗ trợ currency | Không retry |
| `SchemaIncompatibleException` | Non-retryable | Writer/reader schema không tương thích | Điều tra producer và schema |
| `SchemaRegistryUnavailableException` | Retryable | Registry tạm thời không truy cập được | Retry có backoff |
| `AuthenticationException` | Thường non-retryable | Credentials hoặc quyền truy cập sai | Sửa cấu hình/quyền |
| `RateLimitExceededException` | Có điều kiện | Dịch vụ yêu cầu giảm tốc độ | Retry theo Retry-After hoặc backoff phù hợp |

Không dùng bảng này thay cho kiểm tra thực tế. Ví dụ, timeout sau thao tác ghi có thể có kết quả không rõ ràng: phía server đã commit nhưng client chưa nhận response. Retry khi đó có thể tạo giao dịch trùng nếu service không hỗ trợ idempotency.

## 6. Ví dụ consumer và phân loại lỗi

Consumer imperative có thể để exception thoát khỏi function để binder áp dụng retry policy:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderConsumerConfiguration {

    @Bean
    Consumer<OrderCreated> processOrder(OrderService orderService) {
        return event -> orderService.process(event);
    }
}
~~~

Service nghiệp vụ nên ném exception có ý nghĩa:

~~~java
public class OrderService {

    private final InventoryClient inventoryClient;

    public OrderService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    public void process(OrderCreated event) {
        if (event.total().signum() <= 0) {
            throw new InvalidOrderException("Tổng tiền phải lớn hơn 0");
        }

        try {
            inventoryClient.reserve(event.orderId());
        } catch (InventoryUnavailableException ex) {
            throw new TemporaryInventoryException(
                "Dịch vụ kho tạm thời không sẵn sàng",
                ex
            );
        }

        // Thực hiện bước nghiệp vụ tiếp theo sau khi reserve thành công.
    }
}
~~~

Khi `InvalidOrderException` xảy ra, không retry. Khi `TemporaryInventoryException` xảy ra, retry theo cấu hình. Nếu service bắt mọi exception và chỉ log rồi trả về bình thường, binder sẽ hiểu message đã xử lý thành công; không nên nuốt exception nếu muốn retry hoặc DLQ.

### Không dùng catch-all để biến lỗi thành thành công

Mẫu dễ gây mất message:

~~~java
@Bean
Consumer<OrderCreated> unsafeConsumer(OrderService service) {
    return event -> {
        try {
            service.process(event);
        } catch (Exception ex) {
            log.error("Không xử lý được đơn hàng", ex);
        }
    };
}
~~~

Consumer trên không ném lỗi ra ngoài. Binder không nhận được tín hiệu thất bại để áp dụng retry hoặc recovery. Nếu muốn ghi log, hãy log rồi ném lại exception hoặc chuyển lỗi qua một cơ chế recovery được thiết kế rõ ràng.

## 7. Retry, recovery và dead-letter queue

Một chu trình xử lý consumer thường có các bước:

1. Binder giao message cho consumer.
2. Function hoặc handler thực hiện nghiệp vụ.
3. Nếu handler ném exception, retry policy phân loại exception.
4. Nếu exception retryable và còn lượt, handler được gọi lại sau khoảng backoff.
5. Nếu exception non-retryable hoặc đã hết lượt, hệ thống đi tới bước recovery.
6. Nếu DLQ được cấu hình và binder hỗ trợ, message được chuyển tới dead-letter destination; nếu không, hành vi phụ thuộc error channel, acknowledgement và cấu hình binder.

~~~mermaid
flowchart TD
    A["Nhận message"] --> B["Gọi consumer"]
    B --> C{"Xử lý thành công?"}
    C -->|Có| D["Hoàn tất / acknowledge theo binder"]
    C -->|Không| E{"Exception retryable?"}
    E -->|Có| F{"Còn lượt thử?"}
    F -->|Có| G["Backoff"]
    G --> B
    F -->|Không| H["Recovery / error handling"]
    E -->|Không| H
    H --> I{"Có DLQ?"}
    I -->|Có| J["Gửi message vào DLQ"]
    I -->|Không| K["Error channel hoặc hành vi binder"]
~~~

DLQ là nơi cách ly message không thể xử lý tự động. DLQ giúp consumer chính tiếp tục xử lý message khác, đồng thời giữ lại dữ liệu lỗi để điều tra và replay sau khi khắc phục.

Không nên xem DLQ là nơi message tự động được sửa hoặc xử lý thành công. Cần có quy trình vận hành để phân loại nguyên nhân, khắc phục dữ liệu hoặc dịch vụ, rồi replay có kiểm soát.

## 8. Cấu hình DLQ theo binder

Chính sách retry chung nằm trên consumer binding; cách tạo và gửi tới DLQ là phần phụ thuộc binder.

### Kafka binder

Kafka binder hỗ trợ DLQ cho consumer có group. Ví dụ:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 4
            defaultRetryable: false
            retryableExceptions:
              com.example.TemporaryInventoryException: true
              com.example.InvalidOrderException: false
      kafka:
        bindings:
          processOrder-in-0:
            consumer:
              enableDlq: true
              dlqName: orders.order-processor.dlq
~~~

Trong ví dụ, message không retry hoặc đã hết số lần thử được chuyển vào DLQ theo khả năng và cấu hình Kafka binder. Consumer group cần được khai báo để binder xác định luồng xử lý và DLQ tương ứng. Tên DLQ có thể được đặt tường minh; nếu bỏ qua, binder dùng quy tắc tên mặc định theo phiên bản.

Khi vận hành, theo dõi topic DLQ cùng topic gốc. Với Kafka, metadata như topic, partition và offset gốc hữu ích khi truy vết. Cần xác minh số partition DLQ và quyền ghi của producer nội bộ binder.

### RabbitMQ binder

Rabbit binder có các thuộc tính riêng để khai báo dead-letter exchange/queue và hành vi republish. Ví dụ minh họa:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        processOrder-in-0:
          destination: orders
          group: order-processor
          consumer:
            maxAttempts: 4
            defaultRetryable: false
      rabbit:
        bindings:
          processOrder-in-0:
            consumer:
              autoBindDlq: true
              republishToDlq: true
~~~

`autoBindDlq` yêu cầu binder tạo/bind topology dead-letter theo cấu hình. `republishToDlq` cho phép binder republish message kèm thông tin lỗi theo khả năng binder. Các thuộc tính exchange, queue, routing key và quyền truy cập cần được đối chiếu với phiên bản Rabbit binder đang dùng.

### Pulsar binder

Pulsar hỗ trợ retry letter topic và dead-letter topic theo chính sách consumer/client. Binder có thể cung cấp cấu hình riêng để khai báo số lần redelivery, tên retry topic và dead-letter topic. Cấu hình cụ thể phụ thuộc phiên bản Spring Cloud Stream Pulsar binder và Spring for Apache Pulsar.

Không sao chép thuộc tính Kafka `enableDlq` hoặc Rabbit `autoBindDlq` sang Pulsar. Hãy kiểm tra tài liệu binder, xác minh subscription type và chính sách redelivery, rồi kiểm thử message được chuyển sang retry/DLQ topic đúng số lần.

### Khi chưa cấu hình DLQ

Nếu không có DLQ, message sau khi retry thất bại có thể được gửi tới error channel, bị reject, requeue hoặc xử lý theo cơ chế của binder/container. Không có một hành vi chung cho mọi broker và mọi phiên bản. Hãy xác định rõ failure path của binder đang sử dụng để tránh message bị lặp vô hạn hoặc bị loại bỏ ngoài dự kiến.

## 9. Retry trong reactive function

Reactive function xử lý lỗi dưới dạng tín hiệu `onError` trong Reactor. Có thể dùng `retryWhen` để retry một publisher con. Với luồng nhiều message, nên đặt retry bên trong xử lý từng phần tử nếu mục tiêu là retry riêng message đó.

Ví dụ:

~~~java
import java.time.Duration;
import java.util.function.Function;

import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

@Bean
Function<Flux<OrderCreated>, Flux<ProcessedOrder>> processOrders(
        ReactiveOrderService service) {

    return events -> events.flatMap(
        event -> service.process(event)
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(200))
                    .maxBackoff(Duration.ofSeconds(2))
                    .filter(this::isTransient)
            ),
        8
    );
}
~~~

Trong ví dụ:

- `service.process(event)` trả về một publisher cho từng message.
- `retryWhen` đặt bên trong `flatMap`, nên retry publisher của message đó.
- Tối đa ba lần retry sau lần subscribe đầu tiên theo semantics của Reactor Retry.
- `filter(this::isTransient)` chỉ cho retry exception được phân loại tạm thời.
- `flatMap(..., 8)` giới hạn tối đa tám publisher con đang xử lý đồng thời.

Không đặt retry một cách tùy tiện quanh toàn bộ Flux nếu chỉ muốn retry một message. Retry ở cấp toàn luồng có thể resubscribe nguồn và làm xử lý lại nhiều phần tử đã đi qua.

Với reactive function, binder và phiên bản có thể có semantics acknowledgement/retry riêng. Đừng giả định `maxAttempts` của consumer binding và `retryWhen` trong Reactor luôn cộng hoặc thay thế nhau theo cùng một cách. Kiểm thử end-to-end để biết message được acknowledge khi nào, lỗi nào kết thúc subscription và DLQ được kích hoạt ra sao.

## 10. Tránh retry lồng nhau và retry storm

Một service method có thể tự dùng Spring Retry hoặc `@Retryable`, trong khi consumer binding cũng có `maxAttempts`. Nếu cả hai tầng retry, số lần gọi thực tế có thể nhân lên.

Ví dụ, consumer cho phép bốn lần thử và service method cho phép ba lần gọi tổng cộng mỗi lần consumer chạy. Một message có thể kích hoạt tối đa mười hai lần gọi service. Khi có nhiều message lỗi, số request tăng nhanh.

Hãy chọn một tầng sở hữu retry chính cho mỗi thao tác. Nếu cần retry ở nhiều tầng, hãy tính tổng số lần gọi và thời gian chờ, tránh vượt retry budget. Các nguyên tắc giảm retry storm:

- Giới hạn tổng số lần thử.
- Dùng backoff tăng dần.
- Dùng jitter khi nhiều instance có thể retry cùng lúc.
- Tôn trọng Retry-After hoặc quota của dịch vụ phụ thuộc.
- Giới hạn concurrency của các lần retry.
- Dừng retry khi lỗi đã được xác định là permanent.
- Theo dõi số lần retry và tỷ lệ message vào DLQ.

## 11. Idempotency và kết quả không xác định

Retry có thể gọi lại handler sau khi lần trước đã tạo tác động bên ngoài nhưng response bị mất. Ví dụ, dịch vụ thanh toán đã ghi nhận giao dịch, nhưng consumer timeout trước khi nhận kết quả. Nếu gửi lại lệnh thanh toán mà không có idempotency key, hệ thống có thể tạo giao dịch trùng.

Một message nghiệp vụ nên có định danh ổn định, chẳng hạn `eventId`. Dịch vụ nhận lệnh có thể lưu idempotency key cùng kết quả xử lý và trả lại kết quả cũ khi nhận cùng key lần nữa.

Các biện pháp hữu ích:

- Dùng eventId hoặc business operation ID làm idempotency key.
- Đặt unique constraint ở nơi lưu trạng thái đã xử lý.
- Dùng transactional outbox/inbox khi cần phối hợp database và broker.
- Không coi timeout là bằng chứng thao tác phía xa chưa xảy ra.
- Phân biệt lỗi trước khi commit với lỗi sau khi commit nhưng mất response.

Retry policy giải quyết việc thử lại; idempotency bảo vệ tác động nghiệp vụ khi cùng thao tác được thực hiện nhiều lần. Hai cơ chế bổ trợ cho nhau.

## 12. Kiểm thử exception classification

Nên xây dựng test matrix cho các loại exception:

| Kịch bản | Số lần gọi mong đợi | Kết quả |
|---|---:|---|
| Handler thành công | 1 | Message được xử lý |
| Exception retryable, lần sau thành công | 2 hoặc nhiều hơn tùy lần phục hồi | Message được xử lý sau retry |
| Exception retryable, luôn thất bại | Tối đa maxAttempts | Đi tới recovery/DLQ |
| Exception non-retryable | 1 | Đi tới recovery/DLQ ngay |
| Exception không nằm trong map, defaultRetryable=false | 1 | Không retry |
| Exception không nằm trong map, defaultRetryable=true | Theo maxAttempts | Retry theo mặc định |
| Exception wrapper chứa cause retryable | Theo classifier thực tế | Cần xác minh cause traversal |

### Unit test cho classifier

Có thể kiểm tra riêng hàm phân loại của ứng dụng:

~~~java
boolean isTransient(Throwable error) {
    Throwable cause = error;

    while (cause != null) {
        if (cause instanceof TemporaryInventoryException
                || cause instanceof RemoteServiceTimeoutException) {
            return true;
        }
        cause = cause.getCause();
    }

    return false;
}
~~~

Đây là ví dụ classifier cho reactive pipeline hoặc logic ứng dụng. Nếu dùng `retryableExceptions` của Spring Cloud Stream, hãy kiểm thử cấu hình binding với exception thực tế thay vì giả định map tự động dùng đúng quy tắc duyệt cause của hàm trên.

### Binding và broker integration test

Dùng test binder hoặc broker thật để xác minh:

1. Consumer binding có đúng tên và group.
2. `maxAttempts` tạo đúng số lần gọi.
3. Backoff xảy ra trong giới hạn dự kiến.
4. Exception non-retryable không bị gọi lại.
5. Exception retryable được gọi lại và dừng khi thành công hoặc hết lượt.
6. Message sau recovery đi đúng DLQ/error channel.
7. Metadata lỗi và payload gốc còn đủ để điều tra.
8. Replay không tạo tác động nghiệp vụ trùng.

Test binder hữu ích cho logic function và binding, nhưng hành vi DLQ, acknowledgement và redelivery cần broker integration test cho Kafka, RabbitMQ hoặc Pulsar.

## 13. Vận hành DLQ và replay

DLQ cần có quy trình vận hành cụ thể. Một message trong DLQ nên được điều tra theo các thông tin:

- Payload và eventId gốc.
- Destination, group và binder nguồn.
- Exception class, message và thời điểm thất bại.
- Số lần retry và thời gian xử lý.
- Metadata broker như topic/partition/offset hoặc routing/subscription nếu có.
- Phiên bản ứng dụng và schema message.

Không đưa secret, access token hoặc dữ liệu nhạy cảm vào header lỗi hay log. Stack trace có thể chứa đường dẫn, query hoặc dữ liệu nội bộ; cần kiểm soát quyền truy cập DLQ và log.

Quy trình replay gợi ý:

1. Phân loại message trong DLQ.
2. Xác định nguyên nhân: dữ liệu sai, schema, quyền, dịch vụ phụ thuộc hay lỗi ứng dụng.
3. Khắc phục nguyên nhân trước khi replay.
4. Xác minh payload vẫn tương thích schema hiện tại.
5. Chọn tập message cần replay và ghi nhận eventId.
6. Replay vào luồng phù hợp với kiểm soát tốc độ.
7. Xác minh kết quả và chống xử lý trùng.
8. Giữ lại dấu vết audit về thao tác replay.

Không cấu hình consumer đọc DLQ rồi gửi lại chính message đó vào cùng DLQ mà không có điều kiện dừng; điều này có thể tạo vòng lặp vô hạn.

## 14. Lỗi thường gặp khi chọn exception retry

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Lỗi dữ liệu bị retry nhiều lần | `defaultRetryable` vẫn true hoặc chưa phân loại exception | Đặt default phù hợp và đánh dấu lỗi nghiệp vụ false |
| Lỗi timeout không được retry | Exception thực tế bị bọc hoặc không khớp map | Kiểm tra root cause và classifier |
| Consumer gọi dịch vụ quá nhiều | Retry lồng ở binder và service | Tính tổng lần gọi, chọn một tầng sở hữu retry |
| Message vào DLQ ngay | Exception được phân loại non-retryable hoặc maxAttempts=1 | Kiểm tra map và số lần thử |
| Message lặp vô hạn | Requeue/retry của binder không có giới hạn phù hợp | Xác định failure path, maxAttempts và DLQ |
| DLQ không được tạo | Chưa bật cấu hình DLQ hoặc thiếu group/quyền | Kiểm tra thuộc tính binder và topology |
| Message vào DLQ nhưng thiếu metadata | Binder không republish hoặc cấu hình metadata chưa đúng | Kiểm tra khả năng republish và header mapping |
| Retry storm khi dịch vụ phục hồi | Backoff đồng loạt, concurrency quá lớn | Thêm jitter, giảm concurrency và giới hạn retry |
| Giao dịch bị thực hiện trùng | Retry sau timeout không có idempotency | Dùng eventId/idempotency key và inbox/outbox |
| Reactive stream dừng sau một lỗi | Lỗi phát ra ở cấp toàn Flux | Phân loại và xử lý lỗi theo từng message khi phù hợp |

Khi điều tra, hãy lấy exception thực tế trong log, xác định cause chain, kiểm tra map và default, tính số lần thử, rồi xác minh recovery path của binder. Đừng chỉ nhìn cấu hình YAML mà kết luận message sẽ vào DLQ.

## 15. Bài thực hành: phân loại lỗi xử lý đơn hàng

Tạo consumer `processOrder` đọc destination `orders`:

1. Khai báo `InvalidOrderException`, `UnsupportedCurrencyException`, `TemporaryInventoryException` và `RemoteServiceTimeoutException`.
2. Cập nhật service để ném đúng exception theo nguyên nhân.
3. Cấu hình `maxAttempts: 4`, backoff ban đầu 500 ms, tối đa 5.000 ms và multiplier 2.
4. Đặt `defaultRetryable: false`.
5. Đánh dấu hai exception tạm thời là retryable.
6. Đánh dấu hai exception nghiệp vụ là non-retryable.
7. Gửi message hợp lệ và xác minh handler chạy một lần.
8. Mô phỏng dịch vụ kho lỗi tạm thời rồi phục hồi; xác minh consumer retry và xử lý thành công.
9. Gửi đơn hàng sai dữ liệu; xác minh handler không retry.
10. Giữ dịch vụ kho lỗi liên tục; xác minh số lần gọi không vượt maxAttempts.
11. Bật DLQ theo binder và xác minh message thất bại đến đúng destination.
12. Replay một message sau khi khắc phục nguyên nhân và xác minh idempotency.
13. Thử exception bị bọc trong `MessagingException` để kiểm tra cách classifier nhận diện cause.

Bảng nghiệm thu:

| Hạng mục | Kết quả cần xác nhận |
|---|---|
| Exception taxonomy | Có phân loại transient/permanent rõ ràng |
| defaultRetryable | Giá trị phù hợp chính sách ứng dụng |
| retryableExceptions | Class name và boolean đúng |
| maxAttempts | Đếm cả lần đầu |
| Backoff | Tăng dần và có giới hạn |
| Non-retryable | Không gọi handler lặp |
| Exhausted retry | Đi tới recovery đúng |
| DLQ | Message và metadata đủ để điều tra |
| Idempotency | Replay không tạo tác động trùng |
| Observability | Có metric retry, error và DLQ |

## Kết luận

Chọn exception được retry hay không là quyết định về khả năng phục hồi của nghiệp vụ. Lỗi tạm thời có thể được thử lại với số lần hữu hạn và backoff; lỗi dữ liệu, quyền hoặc quy tắc nghiệp vụ thường nên đi thẳng tới recovery/DLQ để được điều tra.

Trong Spring Cloud Stream, hãy dùng `retryableExceptions` và `defaultRetryable` để phân loại rõ ràng, đặt `maxAttempts` và backoff theo retry budget, đồng thời xác minh hành vi DLQ theo binder. Kết hợp retry với idempotency, kiểm thử exception wrapper và theo dõi retry storm để message được xử lý an toàn khi Kafka, RabbitMQ hoặc Pulsar gặp lỗi.

## Tài liệu tham khảo

- [Spring Cloud Stream – Consumer Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream – Kafka Binder and DLQ](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-binder.html)
- [Spring Cloud Stream – Rabbit Binder](https://docs.spring.io/spring-cloud-stream/reference/rabbit/rabbit_overview.html)
- [Project Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)

