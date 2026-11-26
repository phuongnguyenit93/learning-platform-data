# Lỗi trước khi tạo Future hoặc Mono và lỗi khi hoàn tất

Trong **Spring AMQP**, `@RabbitListener` có thể xử lý message theo cách bất đồng bộ bằng cách trả về `CompletableFuture<?>` hoặc `Mono<?>`. RabbitMQ chuyển message đến listener trước, còn công việc nghiệp vụ có thể hoàn tất muộn hơn trên một thread khác hoặc khi một luồng reactive phát tín hiệu kết thúc.

Khác biệt quan trọng nhất là **thời điểm phát sinh lỗi**. Có lỗi xảy ra **trước khi listener tạo/trả về Future hoặc Mono**; có lỗi chỉ xuất hiện **sau khi kết quả bất đồng bộ đã được trả về**. Hai trường hợp đi qua các đường xử lý khác nhau và ảnh hưởng trực tiếp đến việc **ACK, NACK, requeue, retry và dead-letter**.

Bài học thuộc chương **Xử lý bất đồng bộ** của module **SPRING_AMQP**: vận dụng RabbitMQ, `RabbitTemplate`, `@RabbitListener`, exchange, queue, binding và cơ chế xác nhận giao nhận để không đánh mất message khi xử lý bất đồng bộ gặp sự cố.

## 1. Đường đi của một message bất đồng bộ

Với listener đồng bộ, phương thức kết thúc gần như cùng thời điểm công việc kết thúc. Với listener trả về `CompletableFuture` hoặc `Mono`, **trả về đối tượng không đồng nghĩa xử lý nghiệp vụ thành công**.

~~~mermaid
flowchart TD
    A["RabbitMQ giao message"] --> B["Adapter: chuyển đổi payload và bind tham số"]
    B -->|Lỗi trước khi gọi method| E0["Đường lỗi của adapter / container"]
    B --> C["@RabbitListener được gọi"]
    C --> D{"Đã trả về kết quả async?"}
    D -->|Chưa: throw trực tiếp| E1["Đường lỗi đồng bộ của listener"]
    D -->|"Có: CompletableFuture / Mono"| W["Framework theo dõi kết quả"]
    W --> S{"Tín hiệu hoàn tất"}
    S -->|Thành công / complete| ACK["ACK message"]
    S -->|Complete exceptionally / onError| NACK["NACK hoặc reject theo chính sách"]
    E0 --> EH["Error handler / chính sách container"]
    E1 --> EH
    NACK --> R{"Có requeue?"}
    R -->|Có| RE["Đưa về queue để thử lại"]
    R -->|"Không, có DLX"| DLX["Dead-letter qua DLX"]
    R -->|"Không, không có DLX"| DROP["Message bị loại bỏ"]
~~~

Ta cần phân biệt ba ranh giới:

| Giai đoạn | Ví dụ lỗi | Kết quả async đã tồn tại? | Ai có thể xử lý? |
|---|---|---|---|
| **Trước khi vào method** | JSON conversion, thiếu kiểu dữ liệu, bind tham số thất bại | Chưa | Listener adapter / container error handler |
| **Trong method, trước khi return** | Kiểm tra dữ liệu ném exception, gọi API đồng bộ, executor từ chối task, gọi `Mono.just(expensiveCall())` | Chưa chắc | `try/catch` trong method nếu bao được thao tác; nếu không, đường lỗi đồng bộ |
| **Sau khi đã return** | Task `CompletableFuture` ném exception, network timeout, `Mono` phát `onError`, callback bất đồng bộ thất bại | Đã có | Cơ chế hoàn tất async của Spring AMQP và chính sách lỗi |

Chú ý: `Mono` thường *lazy*; phương thức tạo `Mono.defer(...)` có thể trả về thành công, còn code bên trong supplier chỉ chạy khi được subscribe. `CompletableFuture.runAsync(...)` thường **lập lịch ngay lúc gọi**; việc gửi task vào executor cũng có thể ném lỗi ngay lập tức.

## 2. Lỗi trước khi tạo kết quả async

### 2.1. Lỗi ngay bên trong listener

Ví dụ:

~~~java
@RabbitListener(queues = "orders.async.q", ackMode = "MANUAL")
public CompletableFuture<Void> consume(String payload) {
    validate(payload); // Có thể throw trước khi Future được tạo.
    return CompletableFuture.runAsync(
            () -> orderService.process(payload), executor);
}
~~~

Nếu `validate(payload)` ném `IllegalArgumentException`, method không trả về `CompletableFuture` nào. Spring AMQP sẽ thấy exception theo đường gọi listener đồng bộ; không có callback hoàn tất Future để nó quan sát. Tương tự, ngay cả khi validation thành công, `runAsync(...)` có thể ném `RejectedExecutionException` hoặc exception của executor vì hàng đợi task đã đầy.

Một cách làm dễ kiểm soát hơn là **chuyển exception xảy ra trong method thành một kết quả bất đồng bộ thất bại**:

~~~java
@RabbitListener(queues = "orders.async.q", ackMode = "MANUAL")
public CompletableFuture<Void> consume(String payload) {
    try {
        validate(payload);
        return CompletableFuture.runAsync(
                () -> orderService.process(payload), executor);
    } catch (RuntimeException ex) {
        return CompletableFuture.failedFuture(ex); // Java 9+
    }
}
~~~

Khi đó Spring AMQP vẫn nhận được một `CompletableFuture`, nhưng nó ở trạng thái **completed exceptionally**. Việc xử lý lỗi/acknowledgment đi theo cùng đường hoàn tất async như các lỗi phát sinh trong task. Đây là ưu điểm lớn khi muốn có chính sách nhất quán cho hai thời điểm lỗi.

Với Java 8 chưa có `CompletableFuture.failedFuture`, có thể tạo thủ công:

~~~java
private static <T> CompletableFuture<T> failedFuture(Throwable ex) {
    CompletableFuture<T> future = new CompletableFuture<>();
    future.completeExceptionally(ex);
    return future;
}
~~~

Tuy nhiên, khối `try/catch` chỉ bao được lỗi **sau khi method được gọi**. Nó không bắt được lỗi chuyển đổi payload xảy ra ở listener adapter trước khi Spring gọi method. Các lỗi này cần được xử lý ở tầng container/error handler.

### 2.2. Lỗi conversion xảy ra trước cả method

Ví dụ method khai báo `consume(OrderCreated event)` nhưng message có JSON không hợp lệ hoặc không thể chuyển thành `OrderCreated`. Khi đó framework có thể thất bại trong chuyển đổi/bind tham số và **method không chạy**. Vì chưa có `Future` hay `Mono`, việc xử lý phụ thuộc vào listener adapter, error handler và các thiết lập của container.

Không nên cho rằng mọi lỗi loại này đều tự động được retry. Một số lỗi conversion nghiêm trọng có thể được error handler mặc định phân loại là không nên requeue. Trong Spring AMQP, `ConditionalRejectingErrorHandler` là một thành phần cần biết khi cấu hình cách xử lý các lỗi được xem là *fatal*. Cần kiểm thử tình huống JSON hỏng trong đúng phiên bản Spring AMQP đang sử dụng để xác nhận đường đi tới dead-letter queue.

## 3. Lỗi khi Future hoàn tất

`CompletableFuture` có thể kết thúc theo hai hướng:

- **Hoàn tất bình thường:** `complete(value)`, `runAsync` chạy xong hoặc chuỗi `then...` kết thúc thành công.
- **Hoàn tất lỗi:** `completeExceptionally(ex)`, task ném exception, callback `thenApply/thenCompose` ném exception, hoặc timeout hoàn tất Future với lỗi.

Giả sử:

~~~java
CompletableFuture<Void> job =
        CompletableFuture.runAsync(() -> orderService.process(payload), executor);
return job;
~~~

Nếu `orderService.process` ném lỗi trên thread của executor, method listener **đã return từ trước**. Exception không bay ngược về dòng `return` hay về khối `try/catch` bên ngoài `runAsync`; thay vào đó, `job` hoàn tất bất thường. Spring AMQP theo dõi việc hoàn tất này và thực hiện xử lý lỗi/negative acknowledgment theo cấu hình.

Vì vậy, đoạn mã sau **không bắt được lỗi bên trong task**:

~~~java
try {
    return CompletableFuture.runAsync(
            () -> orderService.process(payload), executor);
} catch (RuntimeException ex) {
    // Chỉ bắt lỗi tạo/lập lịch Future tại thời điểm hiện tại.
    return CompletableFuture.failedFuture(ex);
}
~~~

Nếu cần ghi log lỗi async mà vẫn để Spring AMQP nhận ra thất bại, sử dụng callback **không đổi trạng thái lỗi**:

~~~java
return CompletableFuture
        .runAsync(() -> orderService.process(payload), executor)
        .whenComplete((ignored, ex) -> {
            if (ex != null) {
                logger.error("Xử lý message thất bại", ex);
            }
        });
~~~

Ngược lại, có những toán tử **biến lỗi thành thành công**, từ đó khiến framework ACK message:

~~~java
// Sai nếu mục tiêu là retry/dead-letter khi process() lỗi:
return CompletableFuture
        .runAsync(() -> orderService.process(payload), executor)
        .exceptionally(ex -> {
            logger.error("Có lỗi", ex);
            return null; // Future mới hoàn tất THÀNH CÔNG.
        });
~~~

Các toán tử `handle(...)` và `exceptionally(...)` không sai, nhưng nếu chúng trả về một giá trị thành công thì luồng lỗi đã được **xử lý xong**. Chỉ dùng cách này khi nghiệp vụ thực sự chấp nhận bỏ qua lỗi và ACK message.

Ngoài ra, exception bất đồng bộ có thể được bao bởi `CompletionException` hoặc `ExecutionException` tùy API quan sát; khi ghi log, phân loại retry hay hiển thị lỗi, nên truy vết nguyên nhân gốc một cách có kiểm soát.

## 4. Lỗi với Mono: tạo publisher và phát tín hiệu onError

Reactor phân biệt **tạo publisher** với **thực thi pipeline khi subscription xảy ra**.

### 4.1. Toán tử eager dễ ném lỗi quá sớm

~~~java
@RabbitListener(queues = "orders.reactive.q", ackMode = "MANUAL")
public Mono<String> consume(String payload) {
    return Mono.just(orderService.lookup(payload));
}
~~~

`orderService.lookup(payload)` chạy **trước khi** `Mono.just(...)` được gọi. Nếu `lookup` ném exception, listener chưa trả về `Mono`. Nếu kết quả trả về `null`, `Mono.just(null)` cũng gây lỗi; nó không có nghĩa là `Mono.empty()`.

Muốn chuyển việc gọi hàm vào thời điểm subscription, có thể dùng:

~~~java
@RabbitListener(queues = "orders.reactive.q", ackMode = "MANUAL")
public Mono<String> consume(String payload) {
    return Mono.fromCallable(() -> orderService.lookup(payload));
}
~~~

Khi subscribe, `lookup` được thực thi; nếu throw, Reactor chuyển lỗi thành tín hiệu **`onError`**. Chú ý `Mono.fromCallable` hoàn tất rỗng nếu callable trả về `null`, vì vậy cần xác định rõ việc “không tìm thấy dữ liệu” có được xem là thành công hay phải thành exception nghiệp vụ.

### 4.2. Mono.defer cho code khởi tạo pipeline cũng có thể lỗi

~~~java
@RabbitListener(queues = "orders.reactive.q", ackMode = "MANUAL")
public Mono<Void> consume(String payload) {
    return Mono.defer(() -> {
        validate(payload);  // Lỗi được phát khi subscribe.
        return reactiveOrderService.process(payload);
    });
}
~~~

`Mono.defer(...)` trì hoãn cả bước validation và gọi phương thức tạo pipeline đến khi có subscription. Nếu `validate` ném exception hoặc `process` ném exception khi xây publisher, Reactor chuyển thành `onError`; nếu `process` trả về `Mono` hợp lệ rồi lỗi khi chạy, nó cũng phát `onError`.

Có thể chuyển lỗi một cách tường minh:

~~~java
@RabbitListener(queues = "orders.reactive.q", ackMode = "MANUAL")
public Mono<Void> consume(String payload) {
    if (payload == null || payload.isBlank()) {
        return Mono.error(new IllegalArgumentException("Payload trống"));
    }
    return reactiveOrderService.process(payload);
}
~~~

Đây là một lựa chọn dễ đọc nếu điều kiện kiểm tra đơn giản và chắc chắn không ném lỗi bất ngờ trước khi return. `Mono.error(...)` là **publisher báo thất bại**, không phải lệnh ném exception ngay tại dòng đó.

Nếu service thực chất là blocking I/O, không đặt trực tiếp thao tác chặn vào thread chạy reactive pipeline:

~~~java
return Mono.<Void>fromRunnable(() -> blockingOrderService.process(payload))
        .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` dành cho công việc blocking có giới hạn; với tài nguyên ngoài như database hoặc HTTP, client reactive thực sự thường thích hợp hơn. Dù dùng executor hay scheduler, phải theo dõi số task đang chạy và thời gian xử lý.

### 4.3. Đừng nuốt onError hoặc tự subscribe

~~~java
// Sai nếu lỗi phải dẫn đến retry/dead-letter:
return reactiveOrderService.process(payload)
        .onErrorResume(ex -> {
            logger.error("Lỗi xử lý", ex);
            return Mono.empty(); // Kết thúc bình thường -> ACK.
        });
~~~

Để chỉ ghi log và vẫn phát `onError`:

~~~java
return reactiveOrderService.process(payload)
        .doOnError(ex -> logger.error("Lỗi xử lý", ex));
~~~

Đồng thời, tránh:

~~~java
@RabbitListener(queues = "orders.reactive.q")
public void consume(String payload) {
    reactiveOrderService.process(payload).subscribe();
    // Method void đã trả về: container không theo dõi completion của pipeline.
}
~~~

Ở mẫu trên, subscription chạy độc lập với lifecycle của message. Container có thể xác nhận giao nhận trước khi thao tác nghiệp vụ kết thúc; lỗi muộn trong pipeline sẽ không tự động dẫn đến NACK của message gốc.

**Quy tắc:** nếu dùng `@RabbitListener` với `Mono`, hãy **return publisher** để tích hợp Spring AMQP quản lý completion. Đừng tự subscribe chỉ để khởi chạy rồi trả `void`.

## 5. ACK/NACK phải gắn với kết quả hoàn tất

Đối với listener trả về `CompletableFuture` hoặc `Mono` được Spring AMQP hỗ trợ, framework có thể theo dõi completion để thực hiện acknowledgment **sau khi thao tác bất đồng bộ kết thúc**. Để dùng đúng cơ chế này, cần bảo đảm listener container ở chế độ **manual acknowledgment** phù hợp với phiên bản Spring AMQP.

Ở các phiên bản Spring AMQP hiện đại, framework có hỗ trợ tự chọn `MANUAL` cho listener trả về kiểu bất đồng bộ được nhận diện; với phiên bản cũ cần cấu hình thủ công. Khai báo tường minh `ackMode = "MANUAL"` giúp biểu đạt rõ ý định. Việc tự gọi `channel.basicAck(...)` rồi đồng thời để framework ACK kết quả async có thể dẫn đến **double ACK** hoặc lỗi channel.

Cấu hình Spring Boot minh họa:

~~~yaml
spring:
  rabbitmq:
    listener:
      simple:
        acknowledge-mode: manual
        default-requeue-rejected: false
        prefetch: 16
~~~

Trong ví dụ này, `default-requeue-rejected: false` định hướng các lỗi xử lý về **reject không requeue**; nếu work queue đã khai báo dead-letter exchange và binding đúng, broker có thể định tuyến message thất bại sang dead-letter queue. Nếu không có DLX, message bị loại bỏ khi reject không requeue. Thay đổi policy cần dựa vào phân loại lỗi và thiết kế retry cụ thể.

| Kết quả listener | Ý nghĩa | Kỳ vọng về giao nhận |
|---|---|---|
| `CompletableFuture` hoàn tất thành công | Nghiệp vụ thành công | ACK |
| `CompletableFuture` hoàn tất đặc biệt/exceptionally | Nghiệp vụ thất bại | NACK/reject và quyết định requeue theo policy |
| `Mono` phát `onComplete`, kể cả `Mono.empty()` | Publisher kết thúc thành công | ACK |
| `Mono` phát `onError` | Publisher thất bại | NACK/reject và quyết định requeue theo policy |
| `Mono.never()` hoặc Future không bao giờ hoàn tất | Công việc treo | Message có thể giữ trạng thái unacked; chiếm quota prefetch |
| Method ném lỗi trước khi trả async result | Không có kết quả để theo dõi | Đường xử lý lỗi đồng bộ; phải kiểm thử theo container và error handler |

Nếu mã của bạn dùng **manual ACK theo cách tự quản lý Channel** thay vì async return type, bạn phải tự bảo đảm channel, delivery tag và thời điểm ACK đúng. Không nên pha hai phương án ack trong cùng một listener.

### Liên hệ DLX, retry và giới hạn thử lại

Một lỗi tạm thời như HTTP 503 có thể đáng thử lại, còn payload sai schema thường nên cách ly ngay. Việc Future/Mono kết thúc lỗi **không tự tạo ra retry có backoff**. Retry phụ thuộc vào cấu hình listener, advice, broker requeue, hoặc topology DLX/TTL đã thiết kế.

Ví dụ một work queue có DLX:

~~~java
@Bean
Queue asyncWorkQueue() {
    return QueueBuilder.durable("orders.async.q")
            .deadLetterExchange("orders.failed.x")
            .deadLetterRoutingKey("orders.failed")
            .build();
}
~~~

Muốn giữ message không thành công, cần khai báo thêm `orders.failed.x`, queue đích và binding tương ứng. Nếu triển khai retry trì hoãn bằng TTL, nên giới hạn số vòng quay lại và có queue cách ly cuối cùng; requeue trực tiếp có thể tạo vòng lặp nhanh với message lỗi vĩnh viễn.

Không nhầm **retry bên trong Future/Mono** với **RabbitMQ redelivery**. Ví dụ Reactor `retry(2)` có thể chạy lại thao tác trong **cùng một lần RabbitMQ giao message**; chỉ sau khi pipeline cuối cùng phát `onError`, container mới xét NACK. Vì thế số lần gọi nghiệp vụ thực tế có thể lớn hơn số lần message được broker giao lại.

## 6. Một ví dụ CompletableFuture đầy đủ trong listener

Đoạn mã sau thể hiện hai nhóm lỗi trong cùng một listener: validation hoặc executor reject xảy ra **trước khi return**, còn lỗi trong `orderService.process` xảy ra **sau khi return**.

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
public class AsyncOrderListener {
    private final OrderService orderService;
    private final Executor orderExecutor;

    public AsyncOrderListener(
            OrderService orderService,
            @Qualifier("orderExecutor") Executor orderExecutor) {
        this.orderService = orderService;
        this.orderExecutor = orderExecutor;
    }

    @RabbitListener(queues = "orders.async.q", ackMode = "MANUAL")
    public CompletableFuture<Void> onMessage(String payload) {
        try {
            if (payload == null || payload.isBlank()) {
                throw new IllegalArgumentException("Payload không hợp lệ");
            }

            // Việc xếp task có thể ném lỗi ngay nếu executor quá tải.
            return CompletableFuture.runAsync(
                    () -> orderService.process(payload), orderExecutor);
        } catch (RuntimeException ex) {
            // Giữ hợp đồng async: luôn có Future báo thành công/thất bại.
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

`OrderService` là thành phần nghiệp vụ do ứng dụng cung cấp, có phương thức `void process(String payload)`. `orderExecutor` là bean Executor được quản lý dung lượng (chẳng hạn `ThreadPoolTaskExecutor` với giới hạn thread và queue). Cần cấu hình rejection policy phù hợp, không để executor vô hạn trở thành chỗ tích tụ công việc khi tốc độ message cao hơn tốc độ xử lý.

Trong cùng một cấu hình `MANUAL` cho async result, **không cần thêm tham số `Channel` hay tự `basicAck`**: Spring AMQP theo dõi Future. Cách này cũng tránh việc một callback chạy muộn cố dùng channel theo giả định từ thread listener ban đầu.

Nếu timeout là yêu cầu nghiệp vụ, có thể sử dụng `orTimeout(...)` hoặc cơ chế timeout của client để Future cuối cùng không treo mãi. Nhưng timeout của Future **không bảo đảm tác vụ nền đã bị hủy**: sau khi message được retry, tác vụ cũ vẫn có thể gây tác dụng phụ. Vì vậy, cần idempotency (ví dụ theo `eventId` hoặc `orderId` + loại sự kiện) và timeout tại tài nguyên I/O thực sự.

## 7. Kiểm thử lỗi tại từng ranh giới

Nên kiểm tra cả kết quả xử lý và trạng thái message trên broker, vì test chỉ xác minh số lần gọi method có thể bỏ qua lỗi ACK/NACK.

| Kịch bản kiểm thử | Cách tạo lỗi | Kết quả cần xác minh |
|---|---|---|
| Validation trước Future | Payload trống | Listener trả Future thất bại; message đi theo chính sách xử lý lỗi |
| Executor reject trước Future | Đặt queue executor rất nhỏ, tạo tải | Không làm message biến mất âm thầm; ghi nhận lỗi, NACK/reject phù hợp |
| Lỗi trong task Future | `process` ném exception sau khi listener return | Future hoàn tất exceptionally; broker ghi nhận xử lý thất bại |
| Future thành công chậm | Task chờ trong thời gian kiểm thử rồi hoàn tất | Không ACK trước khi hoàn tất; ACK sau khi thành công |
| Eager Mono thất bại | `Mono.just(service.call())` với call ném lỗi | Phát hiện lỗi đồng bộ trước khi Mono tồn tại |
| Deferred Mono thất bại | `Mono.defer` hoặc `fromCallable` ném lỗi lúc subscribe | Nhận tín hiệu `onError`; xử lý negative ack |
| Bị nuốt lỗi | `exceptionally(... → null)` hoặc `onErrorResume(... → Mono.empty())` | Future/Mono trở thành thành công, message có thể bị ACK |
| Lỗi chuyển đổi JSON | Gửi payload không thể bind kiểu tham số | Method không chạy; error handler/DLX hoạt động đúng |
| Pipeline không kết thúc | Future chưa complete hoặc `Mono.never()` | Thấy unacked tăng; có timeout và cảnh báo |
| Mất kết nối/consumer restart | Dừng consumer khi Future đang chạy | Broker redeliver message chưa ACK; nghiệp vụ khử trùng lặp an toàn |

Các tín hiệu vận hành cần theo dõi gồm: số message *ready* và *unacked*, thời gian từ lúc nhận đến khi ACK, tỷ lệ completion lỗi, tỷ lệ executor reject, độ dài task queue, timeout, số lần retry và số message vào dead-letter queue. Gắn `messageId`/`correlationId`, số lượt thử và mã lỗi vào log hoặc tracing giúp liên hệ việc xử lý nghiệp vụ với bản ghi RabbitMQ.

## 8. Checklist tránh những lỗi phổ biến

1. Xác định **điểm lỗi**: trước khi gọi method, trong method trước return, hay khi Future/Mono hoàn tất.
2. Với `CompletableFuture`, bao validation và thao tác xếp task trong `try/catch`; chuyển exception sớm thành `failedFuture` khi cần hợp đồng async nhất quán.
3. Với `Mono`, dùng `defer`/`fromCallable` để trì hoãn thao tác có thể ném lỗi; tránh chạy nghiệp vụ ngay trong tham số `Mono.just(...)`.
4. **Return** Future hoặc Mono để framework quan sát completion; không fire-and-forget bằng `subscribe()` hoặc task background ngoài lifecycle message.
5. Tránh `exceptionally` hoặc `onErrorResume` vô tình biến thất bại thành thành công, trừ khi ACK là ý định nghiệp vụ rõ ràng.
6. Cấu hình và kiểm thử chế độ acknowledgment, requeue, DLX/binding và timeout của đúng container đang chạy.
7. Giới hạn inflight qua prefetch, concurrency và executor; thêm idempotency để chịu được redelivery và công việc cũ kết thúc muộn.

Điểm mấu chốt: **trả về Future hoặc Mono chỉ tạo ra một lời hứa sẽ xử lý**. Spring AMQP cần quan sát **trạng thái cuối cùng của lời hứa đó** để ACK hay xử lý thất bại. Những lỗi xuất hiện trước khi có lời hứa cần được chuyển thành kết quả lỗi bất đồng bộ khi phù hợp, hoặc được xử lý ở adapter/container nếu method chưa được gọi. Cách phân định rõ hai đường lỗi giúp hệ thống RabbitMQ retry, dead-letter và vận hành đáng tin cậy hơn.
