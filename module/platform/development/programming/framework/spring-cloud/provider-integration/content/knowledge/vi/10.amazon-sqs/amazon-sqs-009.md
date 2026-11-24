# Batch, mức song song, backpressure và dừng listener an toàn

Một consumer Amazon Simple Queue Service (Amazon SQS) cần cân bằng ba yếu tố: số message nhận trong mỗi lượt, số message xử lý đồng thời và khả năng chịu tải của các dependency phía sau. Nếu nhận quá ít, consumer có thể không tận dụng được tài nguyên; nếu nhận quá nhiều hoặc chạy quá nhiều handler song song, database và API downstream có thể bị quá tải. Khi ứng dụng cần dừng hoặc triển khai phiên bản mới, listener còn phải ngừng poll, hoàn tất công việc đang xử lý và xác nhận message trong khoảng thời gian cho phép.

Spring Cloud AWS cung cấp `SqsMessageListenerContainer` và `@SqsListener` để điều phối các yếu tố này. **Batch processing** gom nhiều payload vào một lần gọi listener; **concurrency** giới hạn số message đang xử lý; **backpressure** điều tiết nhịp poll theo số slot còn trống; **container lifecycle** quản lý start/stop và thời gian chờ shutdown.

Bài học sử dụng **Spring Cloud AWS 3.4.1**, tập trung vào cách chọn batch size, `maxConcurrentMessages`, `maxMessagesPerPoll`, `maxDelayBetweenPolls`, ba `BackPressureMode`, xử lý Standard/FIFO, giới hạn thread, observability và graceful shutdown.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích sự khác nhau giữa batch listener, batch receive và acknowledgment batching.
- Viết `@SqsListener` nhận `List<T>` hoặc `List<Message<T>>`.
- Cấu hình `maxConcurrentMessages`, `maxMessagesPerPoll`, `pollTimeout` và `maxDelayBetweenPolls`.
- Tính gần đúng throughput và nhận diện nút thắt ở database, HTTP client hoặc thread pool.
- Chọn `AUTO`, `ALWAYS_POLL_MAX_MESSAGES` hoặc `FIXED_HIGH_THROUGHPUT`.
- Điều chỉnh concurrency cho Standard và FIFO queue.
- Dùng `CompletableFuture` và executor phù hợp để tránh block thread của AWS SDK.
- Dừng listener container có kiểm soát, chờ message đang xử lý và acknowledgment hoàn tất.
- Kiểm thử batch, backpressure, tải cao và shutdown trong điều kiện có message in-flight.

## 2. Các khái niệm cần tách biệt

Các thuật ngữ sau liên quan với nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa |
|---|---|
| **Receive batch** | Một request `ReceiveMessage` có thể trả tối đa 10 message từ SQS |
| **Batch listener** | Một lần gọi method nhận một danh sách payload/message thay vì một message |
| **`maxMessagesPerPoll`** | Số message tối đa container muốn cung cấp cho một lượt poll; giá trị lớn hơn 10 được ghép từ nhiều request receive |
| **`maxConcurrentMessages`** | Số message tối đa đang được xử lý đồng thời trên mỗi queue |
| **Acknowledgment batching** | Gom các yêu cầu xóa message để gửi DeleteMessageBatch theo interval/threshold |
| **Backpressure** | Điều tiết polling dựa trên số permit/slot xử lý còn trống |
| **Graceful shutdown** | Ngừng nhận việc mới, chờ công việc và acknowledgment đang chạy trong thời gian cho phép |

Một batch listener có thể xử lý nhiều message trong cùng một lần gọi method, nhưng điều đó không tự động có nghĩa các phần tử trong danh sách chạy song song. Một listener có thể duyệt tuần tự, gọi bulk operation của database hoặc dùng concurrency có giới hạn.

## 3. Batch processing với @SqsListener

Trong Spring Cloud AWS 3.4.1, một method `@SqsListener` nhận `List<Payload>` hoặc `List<Message<Payload>>` sẽ bật batch mode:

```java
import io.awspring.cloud.sqs.annotation.SqsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderBatchListener {
    private final OrderService orderService;

    public OrderBatchListener(OrderService orderService) {
        this.orderService = orderService;
    }

    @SqsListener("${app.sqs.order-queue}")
    public void handle(List<OrderEvent> events) {
        orderService.applyBatch(events);
    }
}
```

Container chuyển toàn bộ kết quả của lượt poll cho listener. Nếu `maxMessagesPerPoll` là 10, method có thể nhận tối đa 10 payload trong một lượt. SQS API không trả quá 10 message trong một request `ReceiveMessage`.

### 3.1. Nhận metadata theo từng message

Nếu cần `MessageHeaders`, nhận danh sách `Message<T>`:

```java
@SqsListener("${app.sqs.order-queue}")
public void handle(List<Message<OrderEvent>> messages) {
    for (Message<OrderEvent> message : messages) {
        String correlationId = message.getHeaders()
            .get("Sqs_MA_correlationId", String.class);
        orderService.apply(message.getPayload(), correlationId);
    }
}
```

Batch listener có thể nhận thêm `BatchAcknowledgement` khi dùng `MANUAL` hoặc `BatchVisibility` để thay đổi visibility của một phần/toàn bộ batch. Với tham số dạng `List`, metadata của từng phần tử được đọc từ `Message.getHeaders()`.

### 3.2. Batch listener không bắt buộc xử lý song song

Đoạn code sau xử lý tuần tự:

```java
@SqsListener("${app.sqs.order-queue}")
public void handle(List<OrderEvent> events) {
    for (OrderEvent event : events) {
        orderService.applyIdempotently(event);
    }
}
```

Xử lý tuần tự dễ giữ thứ tự trong batch và đơn giản hóa transaction, nhưng tổng thời gian có thể bằng tổng thời gian xử lý từng message. Nếu batch gồm 10 message, mỗi message mất trung bình 500 ms, thời gian tuần tự có thể xấp xỉ 5 giây cộng overhead.

Nếu chuyển sang xử lý song song, hãy giới hạn số tác vụ đồng thời theo năng lực database/API. Không tạo một thread mới vô hạn cho từng message. Với FIFO, không chạy song song các message cùng `MessageGroupId` nếu điều đó làm đảo thứ tự tác dụng phụ.

## 4. maxMessagesPerPoll và giới hạn 10 message của SQS

Một request `ReceiveMessage` của SQS trả tối đa 10 message. Spring Cloud AWS cho phép cấu hình `maxMessagesPerPoll` lớn hơn 10 cho batch listener; framework sẽ kết hợp kết quả của nhiều lần poll để tạo một batch lớn hơn.

Ví dụ:

```java
@SqsListener(
    value = "${app.sqs.order-queue}",
    maxMessagesPerPoll = "25",
    maxConcurrentMessages = "25"
)
public void handle(List<OrderEvent> events) {
    orderService.applyBatch(events);
}
```

Container có thể cần nhiều request receive để tạo batch tối đa 25 message. Batch thực tế vẫn có thể nhỏ hơn vì queue không có đủ message hoặc SQS trả ít hơn số lượng yêu cầu.

Các quy tắc cần nhớ trong 3.4.1:

- `maxMessagesPerPoll` mặc định là 10.
- Giá trị phải nhỏ hơn hoặc bằng `maxConcurrentMessages`.
- Một request SQS không trả quá 10 message; giá trị lớn hơn 10 được ghép từ nhiều poll.
- Chỉ dùng batch lớn khi listener thực sự hưởng lợi từ bulk processing hoặc giảm overhead mỗi message.

Batch lớn làm tăng thời gian một lần listener xử lý, lượng bộ nhớ cần giữ và số message cùng chịu ảnh hưởng khi batch thất bại. Với workload có latency biến động, batch nhỏ hơn thường dễ kiểm soát hơn.

## 5. maxConcurrentMessages và số message đang xử lý

`maxConcurrentMessages` giới hạn số message được xử lý đồng thời trên **mỗi queue** trong một container. Giá trị mặc định của Spring Cloud AWS 3.4.1 là 10.

Ví dụ container xử lý hai queue với `maxConcurrentMessages = 20` có thể xử lý tối đa khoảng 40 message đồng thời trên hai queue, tùy tình trạng poll, batch và acknowledgment. Giá trị này không phải throughput theo giây; nó là giới hạn số message đang được xử lý.

### 5.1. Chọn concurrency từ thời gian xử lý

Một ước lượng đơn giản cho throughput lý thuyết:

\[
\text{throughput} \approx \frac{\text{concurrency}}{\text{processing time trung bình}}
\]

Ví dụ 20 message xử lý song song, mỗi message mất trung bình 0,5 giây:

\[
20 / 0.5 \approx 40\ \text{message/giây}
\]

Đây chỉ là ước lượng lý thuyết. Throughput thực tế còn phụ thuộc latency SQS, batch size, thời gian acknowledgment, database connection pool, downstream rate limit, CPU, network và tỷ lệ retry.

### 5.2. Concurrency là giới hạn theo queue

Khi một container chứa nhiều queue, tổng số message có thể đang xử lý bằng số queue nhân với `maxConcurrentMessages`. Cần tính tổng tải lên các dependency dùng chung. Ví dụ ba queue cùng cập nhật một database, mỗi queue có concurrency 20 thì database có thể nhận tới khoảng 60 thao tác đồng thời từ container đó.

Khi bật acknowledgment batching, framework xem message đã được đưa vào acknowledgment queue là không còn chiếm permit xử lý; số message SQS hiển thị là in-flight có thể cao hơn `maxConcurrentMessages` trong lúc chờ batch delete.

## 6. Cấu hình container factory

Có thể đặt mặc định cho các listener bằng `SqsMessageListenerContainerFactory`:

```java
import io.awspring.cloud.sqs.config.SqsMessageListenerContainerFactory;
import io.awspring.cloud.sqs.listener.BackPressureMode;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.sqs.SqsAsyncClient;

import java.time.Duration;

@Configuration
public class SqsListenerConfiguration {
    @Bean
    SqsMessageListenerContainerFactory<Object> defaultSqsListenerContainerFactory(
            SqsAsyncClient sqsAsyncClient) {
        return SqsMessageListenerContainerFactory.builder()
            .sqsAsyncClient(sqsAsyncClient)
            .configure(options -> options
                .maxConcurrentMessages(20)
                .maxMessagesPerPoll(10)
                .maxDelayBetweenPolls(Duration.ofSeconds(5))
                .pollTimeout(Duration.ofSeconds(10))
                .backPressureMode(BackPressureMode.AUTO)
                .listenerShutdownTimeout(Duration.ofSeconds(30))
                .acknowledgementShutdownTimeout(Duration.ofSeconds(30))
            )
            .build();
    }
}
```

Các giá trị trên là cấu hình minh họa cho Standard queue. `maxConcurrentMessages` là 20, mỗi lượt poll tối đa 10 message, container có thể thực hiện hai poll song song khi tải cao. `maxDelayBetweenPolls` cho phép chờ slot để tạo batch đầy đủ trước khi thử poll một batch nhỏ hơn.

### 6.1. Override ở từng listener

Thuộc tính annotation ghi đè giá trị tương ứng của factory:

```java
@SqsListener(
    value = "${app.sqs.audit-queue}",
    id = "audit-listener",
    maxConcurrentMessages = "8",
    maxMessagesPerPoll = "8",
    pollTimeoutSeconds = "10"
)
public void handle(List<AuditEvent> events) {
    auditService.storeBatch(events);
}
```

Một listener có thể có factory riêng bằng thuộc tính `factory`. Dùng factory riêng khi queue có profile tải hoặc yêu cầu shutdown khác biệt rõ ràng; tránh tạo quá nhiều cấu hình gần giống nhau khó vận hành.

### 6.2. Giá trị mặc định trong Spring Cloud AWS 3.4.1

| Option | Mặc định | Ghi chú |
|---|---:|---|
| `maxConcurrentMessages` | 10 | Số message đang xử lý tối đa trên mỗi queue |
| `maxMessagesPerPoll` | 10 | Một SQS receive request tối đa 10; giá trị container lớn hơn 10 được ghép nhiều poll |
| `pollTimeout` | 10 giây | Phạm vi cấu hình của listener container là 1–10 giây |
| `maxDelayBetweenPolls` | 10 giây | Chờ permit để tạo batch đầy đủ trước khi partial poll |
| `backPressureMode` | `AUTO` | Chế độ cân bằng mặc định |
| `listenerShutdownTimeout` | 20 giây | Chờ xử lý message đang chạy |
| `acknowledgementShutdownTimeout` | 20 giây | Chờ batch acknowledgment sau khi xử lý kết thúc |

Nếu một giá trị được đặt ở cả factory và `@SqsListener`, giá trị annotation được ưu tiên cho listener đó.

## 7. maxDelayBetweenPolls và partial polling

Container cần permit trước khi nhận message để không lấy nhiều message hơn khả năng xử lý. Nếu `maxConcurrentMessages` đang gần đầy, polling thread có thể chờ các message đang xử lý hoàn tất để có đủ permit cho một batch mới.

`maxDelayBetweenPolls` là khoảng thời gian tối đa chờ đủ permit. Sau khoảng đó, nếu chế độ backpressure cho phép partial polling, container có thể lấy một batch nhỏ hơn với số permit hiện còn trống.

Ví dụ:

```text
maxConcurrentMessages = 20
maxMessagesPerPoll    = 10

20 message đang được xử lý
6 message hoàn tất sau 5 giây
maxDelayBetweenPolls = 5 giây

Container có thể poll 6 message thay vì chờ đủ 10 permit.
```

Partial polling giúp tận dụng slot đã trống, nhưng có thể tạo nhiều request receive nhỏ. Nếu chi phí poll cao hơn lợi ích sử dụng sớm các slot, có thể chọn chế độ chỉ poll batch đầy đủ.

## 8. Ba BackPressureMode

Spring Cloud AWS 3.4.1 hỗ trợ ba chế độ:

| Mode | Cách hoạt động | Khi phù hợp |
|---|---|---|
| `AUTO` | Mặc định. Bắt đầu ở low throughput, chuyển sang high throughput khi nhận được message; hỗ trợ partial polling | Lựa chọn cân bằng cho phần lớn workload |
| `ALWAYS_POLL_MAX_MESSAGES` | Tắt partial polling; chờ đủ permit cho batch đầy đủ trước khi poll tiếp | Muốn giảm số request poll, chấp nhận throughput thấp hơn khi slot chỉ trống một phần |
| `FIXED_HIGH_THROUGHPUT` | Luôn giữ high throughput, không quay về low throughput; vẫn có thể poll batch một phần | Workload tải cao liên tục, cần tránh chi phí chuyển chế độ |

### 8.1. AUTO

`AUTO` bắt đầu với một poll tại một thời điểm. Nếu poll trả về ít nhất một message, container chuyển sang high throughput và thực hiện các poll song song để tiến tới `maxConcurrentMessages`. Nếu poll trả rỗng, container quay về low throughput và chỉ poll một lần tại một thời điểm cho đến khi có message mới.

Đây là chế độ mặc định và thường là điểm khởi đầu tốt. Không nên thay đổi mode chỉ vì muốn tăng concurrency; trước tiên hãy đo backlog, thời gian xử lý và số poll thực tế.

### 8.2. ALWAYS_POLL_MAX_MESSAGES

Chế độ này tắt partial batch polling. Nếu `maxMessagesPerPoll = 10`, container chờ đủ 10 permit trống mới poll batch tiếp theo. Điều này có thể giảm số request poll nhỏ, nhưng một số slot đã trống vẫn không được tận dụng trong thời gian chờ.

Chọn mode này khi số request poll là chi phí đáng kể và workload có batch đầy đủ ổn định. Không phù hợp khi message đến thưa hoặc latency yêu cầu thấp.

### 8.3. FIXED_HIGH_THROUGHPUT

Chế độ này không chuyển về low throughput sau khi queue rỗng. Container tiếp tục thực hiện poll song song và có thể poll một phần khi có permit trống.

Điều này có ích cho tải cao liên tục, nhưng có thể tạo nhiều request receive rỗng khi queue tạm thời không có message. Theo dõi `NumberOfEmptyReceives`, chi phí request và backlog trước khi chọn.

Ví dụ:

```java
@Bean
SqsMessageListenerContainerFactory<Object> highThroughputFactory(
        SqsAsyncClient sqsAsyncClient) {
    return SqsMessageListenerContainerFactory.builder()
        .sqsAsyncClient(sqsAsyncClient)
        .configure(options -> options
            .maxConcurrentMessages(100)
            .maxMessagesPerPoll(10)
            .backPressureMode(BackPressureMode.FIXED_HIGH_THROUGHPUT)
        )
        .build();
}
```

Đây là cấu hình cần được benchmark trong môi trường gần production. Concurrency 100 không có nghĩa database hoặc API đích chịu được 100 request đồng thời.

## 9. Backpressure không thay thế giới hạn của downstream

Backpressure của listener container điều tiết polling theo permit và số message đang xử lý. Nó không tự biết database đang chậm, API đang rate limit hay connection pool đã cạn nếu các listener vẫn đang chiếm slot.

Hãy kết hợp với giới hạn ở tầng nghiệp vụ:

- Cấu hình connection pool phù hợp với tổng concurrency của tất cả queue.
- Dùng bulk API hoặc batch insert nếu database hỗ trợ.
- Dùng semaphore/bounded executor để giới hạn lời gọi tới API downstream.
- Áp dụng timeout, circuit breaker và retry có backoff cho dependency.
- Giảm `maxConcurrentMessages` khi downstream không thể xử lý tải hiện tại.
- Không tạo executor không giới hạn hoặc xếp hàng vô hạn trong bộ nhớ.

Nếu listener nhận message rồi đẩy vào một queue nội bộ không giới hạn và return thành công, SQS có thể xóa message trong khi công việc vẫn còn nằm trong RAM. Khi process chết, các công việc đó mất. Nếu dùng hàng đợi nội bộ, cần cơ chế lưu bền vững hoặc chỉ acknowledge sau khi công việc được ghi nhận an toàn.

## 10. Batch failure và acknowledgment

Với `ON_SUCCESS`, nếu batch listener ném exception, lần gọi batch được xem là thất bại và các message của batch không được tự động xác nhận. Khi visibility timeout hết, chúng có thể được giao lại. Điều này có thể khiến những phần tử đã xử lý thành công trong batch chạy lại.

Nếu cần xác nhận riêng từng phần tử, dùng `MANUAL` và `BatchAcknowledgement`:

```java
import io.awspring.cloud.sqs.annotation.SqsListener;
import io.awspring.cloud.sqs.listener.acknowledgement.BatchAcknowledgement;
import org.springframework.messaging.Message;

@SqsListener(
    value = "${app.sqs.order-queue}",
    acknowledgementMode = "MANUAL"
)
public void handleBatch(
        List<Message<OrderEvent>> messages,
        BatchAcknowledgement<OrderEvent> acknowledgement) {

    List<Message<OrderEvent>> succeeded = new ArrayList<>();

    for (Message<OrderEvent> message : messages) {
        try {
            orderService.applyIdempotently(message.getPayload());
            succeeded.add(message);
        } catch (RecoverableProcessingException ex) {
            log.warn("Will retry eventId={}", message.getPayload().eventId(), ex);
        }
    }

    if (!succeeded.isEmpty()) {
        acknowledgement.acknowledge(succeeded);
    }
}
```

Chỉ xác nhận những message đã được xử lý bền vững. Những message còn lại sẽ được giao lại khi visibility timeout hết. Consumer vẫn phải idempotent vì một message có thể được nhận lại sau khi database commit nhưng acknowledgment thất bại.

### 10.1. Acknowledgment batching là một lớp khác

Batch listener gom payload thành một lần gọi method. Acknowledgment batching gom yêu cầu xóa message theo interval/threshold. Có thể bật batch listener mà vẫn xác nhận ngay, hoặc xử lý từng message riêng lẻ nhưng dùng acknowledgment batching ở container. Hai cấu hình có mục tiêu khác nhau.

Khi acknowledgment batching được bật, message có thể vẫn ở trạng thái in-flight trên SQS trong khi container đã giải phóng permit sau khi đưa message vào acknowledgment queue. Hãy tính thời gian chờ ack vào visibility timeout và theo dõi số message not visible trên CloudWatch.

## 11. FIFO batch và message group

Với FIFO queue, container chia message theo `MessageGroupId`. Các message trong cùng group được xử lý tuần tự; các group khác nhau có thể xử lý song song.

Trong batch mode, `fifoBatchGroupingStrategy` mặc định là `PROCESS_MESSAGE_GROUPS_IN_PARALLEL_BATCHES`: các group được tách thành batch riêng và xử lý song song, vẫn giữ thứ tự trong mỗi group.

Có thể chọn `PROCESS_MULTIPLE_GROUPS_IN_SAME_BATCH` để đưa message từ nhiều group vào cùng một batch. Khi đó listener cần xử lý metadata `MessageGroupId` và bảo toàn thứ tự của từng group trong logic nghiệp vụ.

Nếu xử lý một message trong group thất bại, các message sau trong cùng group bị loại khỏi lượt xử lý hiện tại và có thể được nhận lại sau visibility timeout. Các message đã xử lý thành công và được acknowledge không bị giao lại chỉ vì message phía sau lỗi.

Không dùng một listener container cho cả Standard và FIFO queue. Nếu ứng dụng cần hai loại queue, tạo listener/container/factory riêng.

## 12. FIFO concurrency bị giới hạn bởi số group hoạt động

Tăng `maxConcurrentMessages` không làm một FIFO group chạy song song. Nếu toàn bộ message dùng cùng một `MessageGroupId`, container vẫn chỉ tiến hành một chuỗi tại một thời điểm.

Ví dụ:

```text
orders.fifo

Group order-101: Created → Paid → Shipped
Group order-202: Created → Cancelled
Group order-303: Created → Paid
```

Ba group có thể xử lý đồng thời, nhưng trong mỗi group vẫn theo thứ tự. Nếu chỉ có `order-101` đang có message, tăng concurrency từ 10 lên 100 không tạo thêm 99 luồng xử lý hữu ích.

Chọn `MessageGroupId` theo aggregate cần giữ thứ tự. Không tạo group ngẫu nhiên nếu sự kiện cùng đơn hàng/tài khoản phải được áp dụng tuần tự.

## 13. Blocking và non-blocking listener

SQS integration của Spring Cloud AWS dựa trên `CompletableFuture` và AWS SDK 2.x async client. Polling, thay đổi visibility và acknowledgment được thực hiện theo cơ chế bất đồng bộ. Listener có thể là method đồng bộ hoặc trả về `CompletableFuture<Void>`.

Listener đồng bộ:

```java
@SqsListener("${app.sqs.inventory-queue}")
public void handle(InventoryAdjusted event) {
    inventoryService.apply(event);
}
```

Listener bất đồng bộ với tác vụ blocking được đưa sang executor riêng:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

import org.springframework.stereotype.Component;

@Component
public class AsyncInventoryListener {
    private final InventoryService inventoryService;
    private final Executor inventoryExecutor;

    public AsyncInventoryListener(
            InventoryService inventoryService,
            Executor inventoryExecutor) {
        this.inventoryService = inventoryService;
        this.inventoryExecutor = inventoryExecutor;
    }

    @SqsListener("${app.sqs.inventory-queue}")
    public CompletableFuture<Void> handle(InventoryAdjusted event) {
        return CompletableFuture.runAsync(
            () -> inventoryService.apply(event),
            inventoryExecutor
        );
    }
}
```

Container chờ future hoàn tất để xác định kết quả xử lý. Không gọi `.join()` hoặc `.get()` trên thread xử lý bất đồng bộ của AWS SDK. Nếu nghiệp vụ blocking, dùng synchronous listener hoặc chuyển việc blocking sang executor có giới hạn.

### 13.1. Kích thước executor

Mặc định Spring Cloud AWS dùng `ThreadPoolTaskExecutor` cho các component cần thread xử lý. Nếu cung cấp `componentsTaskExecutor` riêng, executor cần đủ thread cho tải tối đa, thường tính theo `maxConcurrentMessages × tổng số queue` trong container, cộng phần dự phòng phù hợp với các blocking component.

Không chia sẻ một executor nhỏ cho nhiều queue tải cao mà không đo queue wait time. Thread pool cạn có thể khiến message đã nhận chờ trong ứng dụng lâu, làm tăng nguy cơ visibility timeout hết trước khi xử lý xong.

## 14. Poll backoff khi request SQS gặp lỗi

`pollBackOffPolicy` điều khiển thời gian chờ khi polling thread gặp exception, ví dụ throttling hoặc lỗi kết nối. Trong Spring Cloud AWS 3.4.1, mặc định là exponential backoff với delay ban đầu 1 giây, multiplier 2 và tối đa 10 giây.

Đây là backoff cho lỗi poll, khác với retry message processing trong `ErrorHandler`. Một bên điều tiết request nhận message; bên kia điều khiển message đã nhận nhưng xử lý thất bại.

Nếu polling liên tục thất bại, hãy kiểm tra credentials, IAM, Region, queue URL, network và quota. Không tăng concurrency để khắc phục lỗi quyền hoặc lỗi kết nối.

## 15. Graceful shutdown của listener container

`MessageListenerContainer` triển khai `SmartLifecycle`. Với listener tạo từ `@SqsListener`, Spring Cloud AWS đăng ký các container trong `MessageListenerContainerRegistry`; registry quản lý start/stop cùng lifecycle của Spring ApplicationContext. Container được tạo từ annotation không phải bean Spring độc lập.

Khi ứng dụng shutdown, container mặc định chờ các hoạt động polling, processing và acknowledgment hoàn tất trong khoảng thời gian cấu hình. Nếu hết thời gian chờ, các operation còn lại bị hủy và container cố gắng dừng cưỡng bức.

Hai timeout quan trọng trong 3.4.1:

| Option | Mặc định | Ý nghĩa |
|---|---:|---|
| `listenerShutdownTimeout` | 20 giây | Thời gian chờ các task xử lý message kết thúc |
| `acknowledgementShutdownTimeout` | 20 giây | Thời gian chờ batch acknowledgment hoàn tất sau khi listener processing đã kết thúc hoặc timeout |

Có thể cấu hình riêng:

```java
.configure(options -> options
    .listenerShutdownTimeout(Duration.ofSeconds(45))
    .acknowledgementShutdownTimeout(Duration.ofSeconds(20))
)
```

Đây là hai giai đoạn chờ khác nhau. `acknowledgementShutdownTimeout` bắt đầu tính sau khi listener processing hoàn tất hoặc hết timeout xử lý. Chọn giá trị dựa trên thời gian xử lý thực tế và thời gian API delete cần hoàn tất.

### 15.1. Dừng một listener theo ID

Có thể lấy container từ registry bằng ID đã khai báo trong `@SqsListener`:

```java
@SqsListener(
    value = "${app.sqs.order-queue}",
    id = "order-listener"
)
public void handle(OrderEvent event) {
    orderService.applyIdempotently(event);
}
```

```java
import io.awspring.cloud.sqs.listener.MessageListenerContainer;
import io.awspring.cloud.sqs.listener.MessageListenerContainerRegistry;
import org.springframework.stereotype.Service;

@Service
public class ListenerControlService {
    private final MessageListenerContainerRegistry registry;

    public ListenerControlService(MessageListenerContainerRegistry registry) {
        this.registry = registry;
    }

    public void stopOrderListener() {
        MessageListenerContainer<?> container =
            registry.getContainerById("order-listener");
        if (container != null) {
            container.stop();
        }
    }

    public void startOrderListener() {
        MessageListenerContainer<?> container =
            registry.getContainerById("order-listener");
        if (container != null) {
            container.start();
        }
    }
}
```

`stop()` ngừng container nhận thêm message và điều phối việc dừng theo lifecycle. Có thể dùng cơ chế này để pause consumer khi bảo trì hoặc khi downstream cần ngừng nhận tải. Nếu cung cấp endpoint quản trị, cần giới hạn quyền truy cập và ghi audit.

### 15.2. autoStartup=false

Có thể cấu hình `autoStartup(false)` để container không tự khởi động cùng application context. Ứng dụng phải gọi `start()` khi dependency đã sẵn sàng hoặc khi đạt điều kiện vận hành. Cách này hữu ích khi cần khởi động theo thứ tự, nhưng phải có cơ chế bảo đảm listener cuối cùng được start và được theo dõi trạng thái.

## 16. Shutdown trong Kubernetes và môi trường container

Timeout của Spring chỉ là một phần trong ngân sách shutdown. Kubernetes hoặc nền tảng chạy ứng dụng cũng có thời gian chờ termination riêng. Nếu `terminationGracePeriodSeconds` ngắn hơn tổng thời gian listener cần xử lý và acknowledgment, process có thể bị SIGKILL trước khi container hoàn tất.

Một trình tự triển khai an toàn:

1. Đánh dấu instance không nhận thêm traffic mới nếu ứng dụng còn phục vụ HTTP.
2. Dừng listener container hoặc bắt đầu Spring context shutdown để ngừng poll.
3. Chờ các message đang xử lý hoàn tất trong `listenerShutdownTimeout`.
4. Chờ acknowledgment hoàn tất trong `acknowledgementShutdownTimeout`.
5. Hoàn tất các cleanup khác và thoát process trước khi nền tảng cưỡng bức dừng.

Ví dụ, nếu listener có thể mất tối đa 45 giây và acknowledgment tối đa 20 giây, termination grace period phải lớn hơn tổng thời gian đó và có thêm khoảng đệm cho Spring context cùng cleanup của ứng dụng. Các giá trị cụ thể cần dựa trên SLA và thời gian xử lý thực tế.

Nếu process bị dừng cưỡng bức trước khi message được acknowledge, message có thể được nhận lại sau visibility timeout. Điều này là cơ chế phục hồi bình thường của SQS; consumer phải idempotent để lần nhận tiếp theo không lặp side effect.

## 17. Visibility timeout phải bao phủ batch và shutdown

Khi container nhận batch, visibility timeout bắt đầu từ lúc SQS trả các message, không phải khi listener bắt đầu xử lý từng phần tử. Nếu listener xử lý tuần tự, message cuối batch có thể phải chờ trong khi các phần tử trước được xử lý.

Hãy tính:

```text
Thời gian message cần được ẩn
  >= thời gian chờ trong batch
   + thời gian xử lý phần tử
   + thời gian commit nghiệp vụ
   + thời gian acknowledgment
   + khoảng đệm mạng/scheduling
```

Nếu batch lớn và thời gian xử lý biến động, hãy giảm batch size, xử lý bulk hiệu quả hoặc dùng `BatchVisibility` để gia hạn các message đang xử lý. Không đặt visibility quá ngắn rồi dựa vào retry để điều chỉnh throughput; điều đó dễ tạo duplicate side effect.

Shutdown timeout cũng cần phù hợp với visibility. Nếu ứng dụng thường xuyên bị dừng trước khi xử lý/ack hoàn tất, message sẽ được giao lại. Không thể bảo đảm message chỉ xử lý một lần bằng cách tăng shutdown timeout; cần idempotency và transaction đúng thứ tự.

## 18. Observability và chỉ số cần theo dõi

Để điều chỉnh batch và concurrency, hãy quan sát cả queue và ứng dụng:

| Chỉ số | Dấu hiệu | Hướng điều tra |
|---|---|---|
| `ApproximateNumberOfMessagesVisible` | Backlog tăng liên tục | Consumer poll chậm hoặc năng lực xử lý thấp |
| `ApproximateNumberOfMessagesNotVisible` | In-flight cao | Concurrency cao, xử lý lâu, ack chậm hoặc visibility dài |
| `ApproximateAgeOfOldestMessage` | Độ trễ message tăng | Backlog, retry hoặc group FIFO bị chặn |
| `NumberOfMessagesReceived` so với `NumberOfMessagesDeleted` | Chênh lệch lớn | Redelivery, xử lý lỗi hoặc acknowledgment thất bại |
| `NumberOfEmptyReceives` | Tăng cao | Queue rỗng, poll quá thường xuyên hoặc mode throughput chưa phù hợp |
| Listener processing duration p95/p99 | Tăng | Database/API chậm, batch quá lớn hoặc thread pool thiếu |
| Active threads và executor queue size | Thread pool gần cạn | Blocking work hoặc executor không đủ năng lực |
| Acknowledgment failures | Delete request lỗi | IAM, receipt handle, throttling hoặc network |

Spring Cloud AWS hỗ trợ Micrometer Observation cho SQS. Observation `spring.aws.sqs.listener` ghi nhận quá trình xử lý trong listener container. Bật observability và kết nối registry/exporter phù hợp để theo dõi latency, error và throughput.

Khi log, ghi queue, listener ID, `eventId`, message ID và thời gian xử lý. Không log receipt handle hoặc payload nhạy cảm.

## 19. Kiểm thử batch, backpressure và shutdown

| Kiểm thử | Cách làm | Kết quả cần xác minh |
|---|---|---|
| Batch receive | Gửi 25 message và đặt `maxMessagesPerPoll = 25` | Listener có thể nhận batch ghép từ nhiều lần poll |
| Partial batch | Chỉ gửi 4 message với batch tối đa 10 | Listener nhận batch nhỏ hơn 10, không chờ đủ batch vô hạn |
| Concurrency cap | Đặt `maxConcurrentMessages = 5`, tăng tải | Số message đang xử lý trên queue không vượt giới hạn đã cấu hình theo semantics ack |
| AUTO backpressure | Gửi burst rồi để queue rỗng | Container chuyển low/high throughput theo kết quả poll |
| ALWAYS_POLL_MAX_MESSAGES | Cố ý chỉ giải phóng một phần permit | Container chờ đủ batch permit trước khi poll tiếp |
| FIXED_HIGH_THROUGHPUT | Giữ queue rỗng rồi gửi burst | Container duy trì polling song song; quan sát empty receives |
| Batch failure | Một phần tử ném exception với `ON_SUCCESS` | Toàn bộ lần gọi batch có thể được giao lại |
| Partial manual ack | Dùng `BatchAcknowledgement` xác nhận phần thành công | Message chưa xác nhận có thể được giao lại |
| FIFO batch | Gửi message của nhiều group | Thứ tự trong group được giữ; group khác có thể chạy song song |
| Graceful stop | Gọi `container.stop()` khi listener đang xử lý | Container ngừng poll mới và chờ xử lý/ack trong timeout |
| Forced shutdown | Đặt timeout ngắn hơn thời gian xử lý | Operation còn lại bị hủy; message chưa ack có thể được giao lại |
| Kubernetes termination | Dừng pod với grace period đã cấu hình | Process thoát trước SIGKILL và không bỏ qua acknowledgment đang chờ |

LocalStack phù hợp để kiểm thử luồng SQS cơ bản. Cần kiểm thử thêm trên môi trường AWS test khi cần xác minh quota, IAM, visibility và hành vi tải thực tế.

## 20. Lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Batch luôn nhỏ hơn mong đợi | Queue chưa có đủ message hoặc SQS trả ít hơn số yêu cầu | Không giả định batch luôn đầy; kiểm tra backlog và poll timeout |
| Batch lớn gây timeout | Listener xử lý tuần tự, visibility không đủ hoặc downstream chậm | Giảm batch, bulk operation hoặc gia hạn visibility |
| Concurrency tăng nhưng throughput không tăng | Database/API đã bão hòa hoặc FIFO chỉ có ít group | Đo latency dependency và số group hoạt động |
| Queue backlog tăng dù listener đang chạy | Poll lỗi, thread pool cạn, listener chậm hoặc IAM/network lỗi | Kiểm tra poll logs, executor, visible/in-flight và CloudWatch |
| Nhiều empty receive | FIXED_HIGH_THROUGHPUT khi queue rỗng hoặc poll mode không phù hợp | Thử AUTO và theo dõi chi phí empty receive |
| Executor queue tăng liên tục | Listener chuyển công việc sang executor không giới hạn hoặc executor quá nhỏ | Dùng bounded queue, giới hạn concurrency và trả future đại diện cho công việc |
| Message được xử lý lại khi shutdown | Process bị dừng trước acknowledgment hoặc listener vượt timeout | Tăng shutdown budget hợp lý, visibility và idempotency |
| FIFO throughput thấp dù concurrency cao | Tất cả message dùng cùng group ID | Chọn group theo aggregate độc lập cần xử lý song song |
| Message in-flight cao hơn maxConcurrentMessages | Acknowledgment batching đã giải phóng permit trước khi SQS delete hoàn tất | Theo dõi ack queue và điều chỉnh interval/threshold/visibility |

## 21. Bài tập thực hành

**Bài 1 — Batch cơ bản:** Tạo listener nhận `List<OrderEvent>`, gửi 25 message và đặt `maxMessagesPerPoll = 10`. Quan sát số lần gọi listener và số message trong mỗi batch.

**Bài 2 — Batch lớn:** Đặt `maxMessagesPerPoll = 25`, gửi 25 message nhanh. Xác minh container kết hợp kết quả từ nhiều lần poll để gọi batch listener.

**Bài 3 — Concurrency:** Chạy thử `maxConcurrentMessages` lần lượt 5, 10 và 20. Ghi throughput, p95 processing duration và tải database.

**Bài 4 — Backpressure:** So sánh `AUTO`, `ALWAYS_POLL_MAX_MESSAGES` và `FIXED_HIGH_THROUGHPUT` với queue có burst traffic rồi rỗng. Đo empty receives và thời gian drain backlog.

**Bài 5 — Partial acknowledgment:** Tạo batch listener với `MANUAL`, làm một phần tử lỗi và chỉ xác nhận phần tử thành công. Quan sát các message lỗi được nhận lại.

**Bài 6 — FIFO grouping:** Gửi sự kiện vào ba `MessageGroupId`, quan sát thứ tự trong group và mức song song giữa các group. Thử hai `fifoBatchGroupingStrategy`.

**Bài 7 — Graceful shutdown:** Đặt listener xử lý trong 10 giây, gọi stop khi message đang chạy. Xác minh container không poll thêm và acknowledgment hoàn tất trong timeout.

**Bài 8 — Forced shutdown:** Giảm `listenerShutdownTimeout` xuống thấp hơn thời gian xử lý. Quan sát message được giao lại sau visibility timeout và xác minh idempotency.

**Bài 9 — Kubernetes:** Cấu hình termination grace period dài hơn tổng ngân sách listener shutdown, acknowledgment shutdown và cleanup. Thực hiện rolling update khi queue có backlog.

## 22. Câu hỏi tự kiểm tra

1. Batch listener được bật bằng cách nào? **Method `@SqsListener` nhận `List<Payload>` hoặc `List<Message<Payload>>`.**
2. Một request SQS `ReceiveMessage` trả tối đa bao nhiêu message? **10 message.**
3. `maxMessagesPerPoll` lớn hơn 10 có ý nghĩa gì? **Spring Cloud AWS ghép kết quả từ nhiều poll thành batch lớn hơn.**
4. `maxConcurrentMessages` được tính theo phạm vi nào? **Theo từng queue trong container.**
5. `AUTO` hoạt động như thế nào? **Tự chuyển giữa low/high throughput và cho phép partial polling theo permit còn trống.**
6. `ALWAYS_POLL_MAX_MESSAGES` đánh đổi điều gì? **Giảm poll batch nhỏ nhưng có thể để slot trống chờ đủ permit.**
7. Vì sao tăng concurrency không luôn tăng FIFO throughput? **Message trong cùng group vẫn phải xử lý tuần tự; chỉ group độc lập mới tạo song song.**
8. `listenerShutdownTimeout` mặc định là bao lâu? **20 giây trong Spring Cloud AWS 3.4.1.**
9. `acknowledgementShutdownTimeout` bắt đầu tính khi nào? **Sau khi listener processing hoàn tất hoặc hết timeout.**
10. Nếu process bị kill trước acknowledgment, điều gì có thể xảy ra? **Message có thể được nhận lại sau visibility timeout; consumer cần idempotent.**

## 23. Tài liệu tham khảo

- [Spring Cloud AWS 3.4.1 — Batch Processing](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html): batch listener, `List<T>`, `maxMessagesPerPoll` và nhiều lần poll.
- [Spring Cloud AWS 3.4.1 — Message Processing Throughput](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html): concurrency, polling, backpressure và các mode.
- [Spring Cloud AWS 3.4.1 — Container Lifecycle](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html): start/stop, registry và shutdown behavior.
- [Spring Cloud AWS 3.4.1 — SqsContainerOptionsBuilder API](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/apidocs/io/awspring/cloud/sqs/listener/SqsContainerOptionsBuilder.html): cấu hình queue/container options.
- [Spring Cloud AWS 3.4.1 — ContainerOptionsBuilder API](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/apidocs/io/awspring/cloud/sqs/listener/ContainerOptionsBuilder.html): concurrency, max messages, backpressure và shutdown timeout.
- [Spring Cloud AWS 3.4.1 — SqsListener API](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/apidocs/io/awspring/cloud/sqs/annotation/SqsListener.html): annotation properties, batch listener và concurrency.
- [Amazon SQS — ReceiveMessage API](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ReceiveMessage.html): giới hạn số message mỗi request và receive behavior.

**Ghi nhớ:** Batch giảm overhead khi xử lý nhiều message; concurrency quyết định số message được xử lý cùng lúc; backpressure điều tiết nhịp poll theo năng lực còn trống; graceful shutdown giúp hoàn tất công việc và acknowledgment trước khi process dừng. Hãy điều chỉnh bốn yếu tố này cùng với visibility timeout, khả năng downstream và idempotency của consumer.
