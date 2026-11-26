# RabbitListenerErrorHandler cho kết quả trả về bất đồng bộ

Trong Spring AMQP, phương thức gắn `@RabbitListener` có thể trả về `CompletableFuture<T>` hoặc `Mono<T>`. Kết quả xử lý và phản hồi tới bên gửi có thể xuất hiện **sau khi phương thức listener đã trả về**. Vì vậy, exception không nhất thiết phát sinh trên luồng gọi listener: nó có thể xuất hiện lúc `CompletableFuture` hoàn thành với lỗi hoặc `Mono` phát tín hiệu `onError`.

`RabbitListenerErrorHandler` giúp xử lý những lỗi này ở cấp **listener được chú thích `@RabbitListener`**: chuyển một lỗi dự kiến thành phản hồi có cấu trúc cho bên gửi, hoặc ném lỗi tiếp để framework áp dụng cơ chế reject/requeue/dead-letter. Từ **Spring AMQP 3.0.5**, error handler đã cấu hình còn được gọi khi kết quả **bất đồng bộ** thất bại; ở các phiên bản cũ hơn, không thể mặc định trông đợi hành vi này.

Bài học thuộc chương **Xử lý bất đồng bộ** của module **SPRING_AMQP**. Phạm vi đặt trong hệ thống tích hợp RabbitMQ bằng `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding và cơ chế xác nhận giao nhận, retry, dead-letter, quan sát để xây luồng xử lý tin cậy.

## 1. Vấn đề cần giải quyết

Xét dịch vụ tạo hóa đơn qua mô hình request/reply:

1. Service A dùng `RabbitTemplate` gửi yêu cầu tạo hóa đơn đến exchange `invoice.rpc` với routing key `invoice.make` và chờ phản hồi.
2. RabbitMQ định tuyến yêu cầu vào queue `invoice.rpc.requests`.
3. Service B nhận bằng `@RabbitListener`, chạy tạo hóa đơn bất đồng bộ trên một executor.
4. Xử lý có thể thành công hoặc lỗi, chẳng hạn mã hóa đơn không hợp lệ, database tạm thời không sẵn sàng.
5. Service A cần nhận phản hồi phù hợp cho lỗi nghiệp vụ, trong khi lỗi hạ tầng có thể phải để broker xử lý retry/DLQ.

Luồng thành công:

```text
RabbitTemplate (request/reply)
        |
        | invoice.rpc / invoice.make
        v
  invoice.rpc.requests
        |
        v
@RabbitListener -> CompletableFuture<String> ----------+
        |                                              |
        | trả về Future ngay                            | xử lý nền
        |                                              v
        |                                         future SUCCESS
        |                                              |
        +----------------------------------------------+
                                                       |
                                    gửi reply đến replyTo/correlationId
                                                       |
                                            ACK delivery nguồn
```

Luồng thất bại được xử lý:

```text
@RabbitListener -> Future hoàn thành exceptionally
                             |
                             v
                   RabbitListenerErrorHandler
                         /           \
       trả kết quả lỗi hợp lệ          ném exception tiếp
                 |                         |
      phản hồi lỗi cho caller         container xử lý thất bại
      + hoàn tất delivery             NACK/requeue hoặc DLX
```

**Hai cơ chế khác nhau:** gửi một phản hồi `ERROR` cho requester là một kết quả nghiệp vụ có chủ đích; ném exception đến container thể hiện delivery chưa được xử lý thành công. Cùng một exception có thể được phân loại khác nhau tùy yêu cầu của hệ thống.

## 2. Điều kiện phiên bản và vòng đời bất đồng bộ

### 2.1. Hỗ trợ phiên bản

| Phiên bản Spring AMQP | Hành vi cần biết |
|---|---|
| 2.0+ | `@RabbitListener(errorHandler = "...")` hỗ trợ xử lý exception từ listener, ban đầu chủ yếu ở nhánh đồng bộ |
| 2.1+ | Có khả năng trả về kiểu bất đồng bộ như `Mono` và `ListenableFuture` trong các dòng cũ |
| 2.4.7+ | Bổ sung `CompletableFuture<?>` cho asynchronous reply |
| **3.0.5+** | **`RabbitListenerErrorHandler` được gọi sau khi kết quả bất đồng bộ lỗi**; cũng áp dụng cho listener Kotlin `suspend` |
| 3.1.3+ | API handler có biến thể nhận thêm `Channel`, giúp thao tác manual ack rõ ràng hơn |
| 3.2+/4.x | Có thể dùng chữ ký handler **bốn đối số** `(amqpMessage, channel, convertedMessage, exception)` như ví dụ trong bài |

Ở các bản cũ như Spring AMQP 2.4.x, callback error handler thường có **ba đối số** `(amqpMessage, convertedMessage, exception)`. Cần kiểm tra phiên bản dependency của dự án trước khi sao chép ví dụ bốn đối số; không thể dùng cùng một chữ ký source code cho mọi phiên bản.

Các kiểu được dùng phổ biến hiện nay là `CompletableFuture<?>` và `Mono<?>`. `ListenableFuture` đã bị loại khỏi API hiện đại. Kotlin `suspend` cũng tuân theo các quy tắc về completion và acknowledgment của listener bất đồng bộ khi có dependency tích hợp coroutine cần thiết.

### 2.2. Vì sao acknowledgment phải chờ completion?

Với listener trả về kết quả đồng bộ và `AcknowledgeMode.AUTO`, container thường xác nhận delivery khi phương thức xử lý kết thúc thành công. Nhưng với kết quả bất đồng bộ:

```java
@RabbitListener(queues = "invoice.rpc.requests")
public CompletableFuture<String> createInvoice(String invoiceId) {
    return CompletableFuture.supplyAsync(() -> doWork(invoiceId));
}
```

Lúc phương thức `createInvoice` trả về, `doWork` có thể **chưa xong**. Nếu ACK ngay tại thời điểm này, thông điệp nguồn đã được xác nhận dù công việc sau đó có thể thất bại.

Spring AMQP sử dụng cơ chế xác nhận phù hợp với completion bất đồng bộ:

- Cấu hình container ở `AcknowledgeMode.MANUAL` để tránh ACK trên luồng consumer trước khi có kết quả.
- Framework theo dõi kết quả future/reactive; khi kết thúc, nhánh hoàn thành sẽ ACK hoặc NACK theo kết quả và quy tắc lỗi.
- Một số phiên bản Spring AMQP tự chuyển sang `MANUAL` khi nhận ra kiểu trả về bất đồng bộ, nhưng **khai báo rõ** trong listener container factory giúp người đọc và người vận hành hiểu quy tắc.

Ở chế độ này, **không nên tự gọi `basicAck` trong listener rồi lại để framework ACK khi future hoàn thành**: ACK hai lần cho cùng delivery tag có thể khiến channel gặp lỗi. Handler cũng cần tránh ACK/NACK thủ công trùng với hành vi của adapter.

## 3. API RabbitListenerErrorHandler và các kết quả có thể có

`RabbitListenerErrorHandler` là functional interface trong package `org.springframework.amqp.rabbit.listener.api`. Với Spring AMQP 3.2+/4.x, ý nghĩa chữ ký:

```java
Object handleError(
    org.springframework.amqp.core.Message amqpMessage,
    com.rabbitmq.client.Channel channel,
    org.springframework.messaging.Message<?> convertedMessage,
    ListenerExecutionFailedException exception
) throws Exception;
```

| Tham số | Ý nghĩa | Cách dùng |
|---|---|---|
| `amqpMessage` | Message AMQP gốc | Đọc `messageId`, `correlationId`, `replyTo`, headers, body gốc |
| `channel` | RabbitMQ channel | Dành cho trường hợp cần ACK/NACK thủ công có kiểm soát |
| `convertedMessage` | Spring Messaging message sau chuyển đổi | Lấy payload, headers nghiệp vụ; **có thể `null` khi conversion lỗi** |
| `exception` | `ListenerExecutionFailedException` | Tìm nguyên nhân gốc; phân loại lỗi có thể trả về và lỗi phải ném tiếp |

Khi handler được gọi, nó thường có hai lựa chọn:

1. **`return` một kết quả:** Framework dùng kết quả như phản hồi của `@RabbitListener` theo quy tắc `replyTo`/`@SendTo`. Đây là cách gửi một đối tượng lỗi nghiệp vụ phù hợp giao thức của caller, thay vì gửi nguyên Java exception.
2. **`throw` exception:** Lỗi tiếp tục đi theo pipeline của listener/container. Việc requeue, reject và dead-letter phụ thuộc exception, cấu hình container và topology của broker.

Nếu message không có `replyTo` và listener không có đích reply cố định phù hợp, đừng kỳ vọng kết quả trả về tự tìm được người nhận. `RabbitListenerErrorHandler` không tự tạo exchange/queue phản hồi.

### 3.1. Phân biệt hai tầng error handler

| Thành phần | Cấp xử lý | Thường làm gì? |
|---|---|---|
| `RabbitListenerErrorHandler` | Adapter của method `@RabbitListener` | Biến lỗi method thành reply hoặc ném tiếp; có thể xem request gốc và dữ liệu đã chuyển đổi |
| Container `ErrorHandler`, ví dụ `ConditionalRejectingErrorHandler` | Listener container | Phân loại lỗi ở cấp consumer; ảnh hưởng cách container reject/requeue |
| `RabbitTemplate` callbacks / confirms / returns | Bên publish | Theo dõi kết quả gửi message, routing; không xử lý lỗi trong method listener |
| RabbitMQ DLX | Broker, sau khi message bị dead-letter | Định tuyến message lỗi sang exchange/queue nếu topology đã cấu hình |

Handler của method không thay thế cơ chế xác nhận publish của `RabbitTemplate` hoặc quy tắc dead-letter của broker. Trong thực tế, có thể sử dụng cả bốn ở các giai đoạn khác nhau của một request.

## 4. Ví dụ end-to-end bằng CompletableFuture

Ví dụ sử dụng Spring AMQP **3.2+/4.x**, Java 17+, Spring Boot và RabbitMQ. Phản hồi là `String` để minh họa ngữ nghĩa async mà không phụ thuộc một JSON converter cụ thể. Khi triển khai API thật, nên dùng DTO phản hồi có schema nhất quán.

### 4.1. Khai báo exchange, queue, binding và listener factory

Ứng dụng nhận request tại `invoice.rpc.requests`. Những lỗi được handler **ném tiếp**, nếu không requeue, có thể chuyển tới `invoice.rpc.dead` qua DLX:

```java
@Configuration
@EnableRabbit
public class InvoiceAmqpConfiguration {

    @Bean
    Declarables invoiceTopology() {
        DirectExchange rpc = new DirectExchange("invoice.rpc");
        DirectExchange dlx = new DirectExchange("invoice.dlx");

        Queue requests = QueueBuilder.durable("invoice.rpc.requests")
                .deadLetterExchange("invoice.dlx")
                .deadLetterRoutingKey("invoice.failed")
                .build();
        Queue dead = QueueBuilder.durable("invoice.rpc.dead").build();

        return new Declarables(
                rpc, dlx, requests, dead,
                BindingBuilder.bind(requests).to(rpc).with("invoice.make"),
                BindingBuilder.bind(dead).to(dlx).with("invoice.failed"));
    }

    @Bean("invoiceExecutor")
    Executor invoiceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("invoice-worker-");
        executor.initialize();
        return executor;
    }

    @Bean("invoiceAsyncListenerFactory")
    SimpleRabbitListenerContainerFactory invoiceAsyncListenerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory =
                new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setAcknowledgeMode(AcknowledgeMode.MANUAL);
        factory.setDefaultRequeueRejected(false);
        factory.setPrefetchCount(8);
        return factory;
    }
}
```

Các kiểu chính cần import:

```java
import java.util.concurrent.Executor;
import org.springframework.amqp.core.*;
import org.springframework.amqp.core.AcknowledgeMode;
import org.springframework.amqp.rabbit.annotation.EnableRabbit;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
```

**Vì sao chọn `defaultRequeueRejected(false)`?** Ví dụ cố ý tránh vòng giao lại vô hạn khi một lỗi được ném tới container. Queue nguồn đã có DLX nên những delivery bị reject không requeue có điểm đến là `invoice.rpc.dead`. Trong hệ thống thực, thường thêm retry hữu hạn có backoff trước khi chuyển DLQ; không phải lỗi hạ tầng nào cũng nên dead-letter ngay.

`prefetchCount=8` chỉ minh họa giới hạn số delivery chưa ACK cho một consumer. Khi futures xử lý lâu, nhiều message có thể ở trạng thái `unacknowledged`; cần điều chỉnh prefetch, concurrency và số luồng executor dựa trên tải thực tế.

### 4.2. Tạo bean RabbitListenerErrorHandler

Với lỗi kiểm tra dữ liệu đầu vào, ứng dụng trả một phản hồi dạng `ERROR:VALIDATION`. Với lỗi khác, handler ném tiếp exception để container xử lý. Callback bốn tham số là chữ ký phù hợp Spring AMQP 3.2+/4.x.

```java
@Configuration
public class InvoiceErrorHandlingConfiguration {

    @Bean("invoiceAsyncErrorHandler")
    RabbitListenerErrorHandler invoiceAsyncErrorHandler() {
        return (raw, channel, converted, failure) -> {
            Throwable cause = unwrap(failure);

            if (cause instanceof IllegalArgumentException) {
                // Một lỗi nghiệp vụ đã được biểu diễn thành reply hợp lệ.
                return "ERROR:VALIDATION";
            }

            // Lỗi hạ tầng/không dự kiến: cho container quyết định NACK.
            throw failure;
        };
    }

    private static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null
                && (current instanceof ListenerExecutionFailedException
                    || current instanceof CompletionException
                    || current instanceof ExecutionException)) {
            current = current.getCause();
        }
        return current;
    }
}
```

Các import của đoạn trên:

```java
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import org.springframework.amqp.rabbit.listener.api.RabbitListenerErrorHandler;
import org.springframework.amqp.rabbit.support.ListenerExecutionFailedException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
```

Hàm `unwrap` giải quyết trường hợp exception thực tế bị bọc bởi `CompletionException` (do `CompletableFuture`), `ExecutionException` hoặc `ListenerExecutionFailedException`. Không nên phân loại lỗi bằng cách so sánh nguyên văn `exception.getMessage()` vì thông điệp lỗi có thể thay đổi và chứa dữ liệu nhạy cảm.

`raw` vẫn có thể dùng để lấy `correlationId` hoặc `messageId` khi cần theo dõi; `converted` có thể bằng `null` nếu lỗi xảy ra ở bước chuyển đổi message. Ví dụ chưa truy cập các giá trị này vì phản hồi cố định không cần chúng.

### 4.3. Listener trả về CompletableFuture

```java
@Component
public class InvoiceAsyncListener {

    private final Executor executor;

    public InvoiceAsyncListener(@Qualifier("invoiceExecutor")
                                Executor executor) {
        this.executor = executor;
    }

    @RabbitListener(
            queues = "invoice.rpc.requests",
            containerFactory = "invoiceAsyncListenerFactory",
            errorHandler = "invoiceAsyncErrorHandler")
    public CompletableFuture<String> makeInvoice(String invoiceId) {
        try {
            return CompletableFuture.supplyAsync(() -> {
                if ("INVALID".equals(invoiceId)) {
                    throw new IllegalArgumentException("Mã hóa đơn không hợp lệ");
                }
                if ("DB_DOWN".equals(invoiceId)) {
                    throw new IllegalStateException("Database chưa sẵn sàng");
                }
                // Thay bằng logic nghiệp vụ thật.
                return "OK:" + invoiceId;
            }, executor);
        } catch (RuntimeException cannotSchedule) {
            // Ví dụ: executor không nhận thêm task. Vẫn trả Future lỗi.
            return CompletableFuture.failedFuture(cannotSchedule);
        }
    }
}
```

Các import chính:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
```

Tại thời điểm `makeInvoice` trả về `CompletableFuture`, việc tạo hóa đơn có thể chưa hoàn tất. Với Spring AMQP 3.0.5+, khi future hoàn thành exceptionally, framework có thể gọi bean `invoiceAsyncErrorHandler` đã chỉ định qua `errorHandler`.

**Bẫy thường gặp:** `CompletableFuture.supplyAsync(...)` cũng có thể ném exception **ngay lúc lên lịch** nếu executor từ chối task. Khối `try/catch` ở ví dụ biến trường hợp này thành `failedFuture`; nhờ vậy mọi nhánh đều trả về một kết quả bất đồng bộ có thể được framework theo dõi.

### 4.4. Bên gửi request bằng RabbitTemplate

`RabbitTemplate.convertSendAndReceive` gửi request và chờ reply theo cơ chế request/reply. Để đơn giản, caller dùng chuỗi và converter mặc định:

```java
@Component
public class InvoiceClient {

    private final RabbitTemplate rabbitTemplate;

    public InvoiceClient(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public String request(String invoiceId) {
        Object reply = rabbitTemplate.convertSendAndReceive(
                "invoice.rpc",
                "invoice.make",
                invoiceId);
        if (reply == null) {
            throw new IllegalStateException("Không nhận được reply trước timeout");
        }
        return (String) reply;
    }
}
```

Các import liên quan:

```java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;
```

Với `convertSendAndReceive`, Spring AMQP quản lý các thuộc tính request/reply như `replyTo` và correlation để ghép phản hồi với request. Trong thực tế, caller cần cấu hình `replyTimeout` phù hợp với giới hạn thời gian xử lý. Timeout **không bảo đảm** tác vụ nền hoặc delivery tại consumer đã bị hủy.

Nếu muốn caller cũng bất đồng bộ, có thể xem xét `AsyncRabbitTemplate` hoặc API request/reply tương ứng với phiên bản đang dùng. Điều đó là bất đồng bộ ở **phía caller**, tách biệt với việc `@RabbitListener` trả về `CompletableFuture` ở phía consumer.

## 5. So sánh kết quả của ba request mẫu

Giả sử topology và cấu hình ở trên đã được khai báo thành công, client gọi:

| Request | Future ở listener | Error handler | Reply có thể nhận | Xử lý delivery gốc |
|---|---|---|---|---|
| `INV-100` | Hoàn thành thành công | Không gọi | `OK:INV-100` | Framework ACK sau hoàn thành |
| `INVALID` | Hoàn thành với `IllegalArgumentException` | Trả `ERROR:VALIDATION` | `ERROR:VALIDATION` | Lỗi được xử lý thành phản hồi; delivery được hoàn tất |
| `DB_DOWN` | Hoàn thành với `IllegalStateException` | Ném tiếp | Không có reply thành công; caller có thể timeout | Container xử lý lỗi; với `defaultRequeueRejected=false` và DLX hợp lệ, message được dead-letter |

Bảng mô tả **hành vi mong đợi** khi exchange, binding, listener adapter, reply path và acknowledgment hoạt động bình thường. Mất kết nối broker, lỗi gửi reply, channel đóng hoặc các chính sách xử lý bổ sung có thể làm kết quả quan sát được khác đi.

Trong kịch bản `INVALID`, error handler trả về chuỗi lỗi không có nghĩa bước tạo hóa đơn đã thành công; nó có nghĩa hệ thống đã **quyết định và trả lời xong** một lỗi nghiệp vụ dự kiến. Nếu quy trình cần audit hoặc bù trừ, ứng dụng phải thực hiện chúng theo yêu cầu riêng.

## 6. Những lỗi khó nhìn thấy trong xử lý bất đồng bộ

### 6.1. Exception xảy ra sau khi method listener trả về

```java
public CompletableFuture<String> handle(String value) {
    return CompletableFuture.supplyAsync(() -> {
        throw new IllegalArgumentException("late failure");
    }, executor);
}
```

Lỗi phát sinh ở luồng executor. `try/catch` bao quanh lời gọi listener ở một lớp khác có thể không bắt được lỗi này, vì khi lời gọi kết thúc, task chưa chạy xong. `CompletableFuture` giữ trạng thái failed; framework đăng ký xử lý completion và gọi `RabbitListenerErrorHandler` tương ứng ở phiên bản hỗ trợ.

### 6.2. Lỗi trước khi tạo future

```java
public CompletableFuture<String> handle(String value) {
    validateBeforeFuture(value); // có thể ném ngay!
    return remoteCallAsync(value);
}
```

Nếu `validateBeforeFuture` ném exception, method chưa trả về Future. Tài liệu Spring AMQP yêu cầu cẩn trọng với lỗi ngăn không cho đối tượng async được tạo vì acknowledgment có thể không đi theo nhánh completion mong muốn. Cách an toàn là trả một Future thất bại có chủ đích:

```java
public CompletableFuture<String> handle(String value) {
    try {
        validateBeforeFuture(value);
        return remoteCallAsync(value);
    } catch (RuntimeException ex) {
        return CompletableFuture.failedFuture(ex);
    }
}
```

### 6.3. Handler trả về `null` hoặc tự ACK/NACK

Giá trị `null` không phải phản hồi lỗi rõ ràng cho RPC, đặc biệt khi phía gửi chờ reply. Ngoài ra, các phiên bản Spring AMQP có hành vi mặc định ACK message khi error handler trả `null` trong manual mode; từ Spring AMQP 3.2.11 có tùy chọn `setAcknowledgeOnError(false)` trên adapter để tránh auto-ACK nếu muốn handler tự reject. Đừng tự trộn ACK/NACK thủ công trong callback với tự động ACK/NACK của nhánh async khi chưa kiểm tra API và phiên bản đang chạy.

Trong bài này, handler hoặc trả về **giá trị lỗi không null**, hoặc ném exception; việc xác nhận delivery do framework quản lý.

### 6.4. Chuyển mọi lỗi thành phản hồi `ERROR`

Nếu handler trả lỗi JSON/chuỗi cho cả sự cố database, message có thể được **ACK** và không vào DLQ để retry, dù công việc nghiệp vụ chưa hoàn thành. Nên định nghĩa hợp đồng rõ:

- **Validation/business failure có thể trả lời:** trả mã lỗi có cấu trúc, ví dụ `VALIDATION_FAILED` hoặc `NOT_FOUND`.
- **Lỗi hạ tầng có thể thử lại:** ném tiếp, tổ chức retry hữu hạn và backoff; khi hết retry thì dead-letter hoặc parking.
- **Lỗi không xác định:** ưu tiên cơ chế theo dõi và khôi phục có kiểm soát; không gửi chi tiết stack trace thô cho caller.

Handler không nên nuốt exception chỉ để mọi request luôn có chuỗi trả về nếu điều đó làm mất khả năng phục hồi message.

### 6.5. Chuỗi phản hồi và JSON

Ví dụ dùng `String` để giảm cấu hình. Khi chuyển sang DTO:

```java
public record InvoiceReply(
        String requestId,
        String status,
        String errorCode,
        String detail) {}
```

Cần đặt converter tương thích ở cả listener và caller (ví dụ converter JSON phù hợp với dòng Spring AMQP), đồng thời thống nhất schema, content type và cách xử lý các trường không có. Đừng dựa vào việc Java exception tự serialize thành JSON; cơ chế `returnExceptions=true` sử dụng `RemoteInvocationResult`, chủ yếu thích hợp với Java serialization của `SimpleMessageConverter` chứ không phải một hợp đồng lỗi JSON an toàn và ổn định.

### 6.6. Không có người nhận reply

Nếu message đến `@RabbitListener` không có `replyTo` và cũng không có `@SendTo` hợp lệ, object handler trả về không bảo đảm được gửi tới requester. Với luồng chỉ cần xử lý fire-and-forget, hãy cân nhắc error handler chỉ để phân loại/lưu log và để retry/DLQ quyết định việc xử lý lại, thay vì cố tạo một RPC reply.

## 7. Ack, Nack, retry và dead-letter: quy tắc quyết định

Kết quả bất đồng bộ có ý nghĩa đối với acknowledgment của message đầu vào:

| Trạng thái xử lý | Hành động điển hình | Điểm cần kiểm tra |
|---|---|---|
| Future hoàn thành thành công | Framework ACK | Có thực hiện nghiệp vụ trước khi Future success không? |
| Future lỗi, handler tạo reply nghiệp vụ | Reply lỗi và xử lý delivery như một kết quả đã giải quyết | Đã phân biệt lỗi nghiệp vụ với lỗi hạ tầng chưa? |
| Future lỗi, handler ném tiếp | Container NACK/reject theo exception và cấu hình | `defaultRequeueRejected`, exception đặc biệt, retry interceptor |
| Consumer reject với `requeue=false` | Broker có thể dead-letter | Queue nguồn phải khai báo DLX và binding đúng |
| Consumer requeue | Message có thể được giao lại | Giới hạn số lần, backoff, idempotency |
| Caller hết thời gian chờ reply | Caller báo timeout | Không suy ra message gốc đã bị NACK hay task nền đã dừng |

Một số exception được Spring AMQP nhận biết có ngữ nghĩa điều khiển requeue:

- `AmqpRejectAndDontRequeueException`: yêu cầu không requeue dù cấu hình mặc định cho phép.
- `ImmediateRequeueAmqpException`: yêu cầu requeue ngay dù cấu hình mặc định là không requeue.
- `defaultRequeueRejected`: cài đặt mặc định ở container khi xử lý lỗi.

Mặc định `defaultRequeueRejected` thường là `true`; lặp requeue liên tục có thể làm queue bị nóng. Với retry có giới hạn, hãy tách số lần thử và cách delay khỏi logic trả lời lỗi. Nếu dùng DLX, quan sát `x-death` nhưng không coi nó là số lần thực thi mọi bước trong ứng dụng.

**Không có một transaction tự động giữa** việc cập nhật database, gửi reply và ACK nguồn. Một reply đã được gửi nhưng ACK thất bại có thể dẫn đến xử lý lại request. Cần gắn business ID và thiết kế idempotent ở consumer; nếu nghiệp vụ quan trọng, cân nhắc transactional outbox và quy tắc ghi nhận kết quả.

## 8. Quan sát và kiểm thử các nhánh bất đồng bộ

### 8.1. Checklist thử nghiệm tối thiểu

| Ca thử | Kích thích | Kết quả cần kiểm chứng |
|---|---|---|
| Thành công | Gửi `INV-100` | Reply `OK:INV-100`, error handler không chạy, delivery được ACK |
| Lỗi nghiệp vụ trễ | Gửi `INVALID` | Future lỗi, error handler được gọi sau completion, reply `ERROR:VALIDATION` |
| Lỗi hạ tầng trễ | Gửi `DB_DOWN` | Handler ném tiếp, không có reply thành công, request đi DLQ khi có DLX |
| Executor quá tải | Làm đầy task queue hoặc dùng executor từ chối task | Listener vẫn trả failed Future; container không bị treo vì exception trong bước scheduling |
| Reply timeout | Dùng task chậm hơn `replyTimeout` | Caller timeout nhưng consumer vẫn có thể xử lý/ACK sau đó |
| Lỗi converter | Gửi payload sai định dạng so với DTO mong đợi | Phân biệt conversion error; `convertedMessage` trong handler có thể là `null` |
| Broker gián đoạn | Dừng kết nối trong khi task đang chạy | Theo dõi ACK/NACK, redelivery, duplicate và thời điểm reply thực sự được gửi |

Không cần tạo integration test cho từng lớp cấu hình minh họa; những ca cần ưu tiên ở ứng dụng thật là kiểm chứng **có broker**, vì chúng liên quan đến queue, reply routing, ACK/NACK và DLQ.

### 8.2. Thông tin nên đo

- Tổng số lần listener bắt đầu và hoàn tất; thời gian từ delivery đến Future success/failure.
- Số lần `RabbitListenerErrorHandler` chạy, phân loại theo `errorCode` nghiệp vụ hay loại exception.
- Độ dài queue nguồn, `messages_ready`, `messages_unacknowledged`, queue retry/DLQ và số lượng redelivery.
- Request `messageId`, `correlationId`, business ID trong cả log caller và consumer; tránh log nguyên payload/stack trace chứa thông tin nhạy cảm.
- Executor active threads, queue capacity, rejected tasks và tỷ lệ timeout ở caller.

Khi lượng `unacknowledged` tăng, có thể hệ thống đang xử lý nền chậm, executor bị nghẽn hoặc channel gặp sự cố. Đừng chỉ tăng prefetch hay thread pool mà không đo thông lượng thực và tải lên dịch vụ phụ thuộc.

## 9. Tự kiểm tra hiểu bài

1. **Future trả về bình thường nhưng sau đó hoàn thành exceptionally:** lỗi xuất hiện trên luồng nào, và tại sao `try/catch` đồng bộ thông thường không đủ?
2. **Spring AMQP 3.0.4:** có thể mặc định đợi `RabbitListenerErrorHandler` chạy khi `CompletableFuture` lỗi không? Phiên bản nào thay đổi điều này?
3. **Handler trả `ERROR:VALIDATION`:** tại sao caller nhận được lỗi nghiệp vụ nhưng delivery nguồn vẫn có thể được ACK?
4. **Handler ném `IllegalStateException` tiếp và `defaultRequeueRejected=false`:** chuyện gì xảy ra nếu queue nguồn chưa cấu hình DLX?
5. **Caller `replyTimeout`:** việc timeout có đồng nghĩa task đã bị cancel hoặc message đã vào DLQ không?
6. **Handler tự `basicReject` và framework vẫn ACK cùng delivery tag:** hệ quả có thể xảy ra ở channel là gì?

Đáp án ngắn: (1) ở completion của Future/luồng executor; (2) không, hỗ trợ gọi handler cho async failure bắt đầu từ 3.0.5; (3) handler đã biến lỗi thành phản hồi hợp lệ; (4) message có thể bị loại mà không vào queue lỗi; (5) không; (6) xác nhận trùng, có thể gây lỗi channel.

## 10. Ghi nhớ khi thiết kế hệ thống

`RabbitListenerErrorHandler` là điểm mở rộng để biến **exception của listener** thành một phản hồi có chủ đích. Từ Spring AMQP **3.0.5**, nó có thể tham gia xử lý lỗi phát sinh **sau** khi phương thức `@RabbitListener` trả về `CompletableFuture`/`Mono`, nhờ đó rất hữu ích cho RPC bất đồng bộ. Nó không tự thay thế acknowledgment, retry, dead-letter hay publisher confirms.

Thiết kế đáng tin cậy cần thống nhất ba quyết định: **lỗi nào được chuyển thành reply**, **lỗi nào phải ném tiếp để xử lý lại**, và **delivery đầu vào được ACK/NACK ở thời điểm nào**. Hãy cấu hình ack mode cho asynchronous completion, giới hạn retry, đo hàng đợi chưa ACK và đảm bảo idempotency khi nhận lại cùng một yêu cầu.

### Tài liệu tham khảo

- [Spring AMQP — Asynchronous `@RabbitListener` Return Types](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-returns.html): async return types, hoàn thành Future, ACK/NACK và thay đổi từ 3.0.5.
- [Spring AMQP — Handling Exceptions](https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/error-handling.html): `RabbitListenerErrorHandler`, `returnExceptions`, phản hồi từ handler và lỗi chuyển đổi message.
- [RabbitListenerErrorHandler API (Spring AMQP 3.2.x)](https://docs.spring.io/spring-amqp/docs/3.2.x/api/org/springframework/amqp/rabbit/listener/api/RabbitListenerErrorHandler.html): chữ ký callback có `Channel`.
- [Spring AMQP — Resilience: Recovering from Errors and Broker Failures](https://docs.spring.io/spring-amqp/reference/amqp/resilience-recovering-from-errors-and-broker-failures.html): reject/requeue, recovery, listener container và DLX.

