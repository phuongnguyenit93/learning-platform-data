# ExecutorChannel dispatcher và async handoff

`ExecutorChannel` là một channel kiểu point-to-point của Spring Integration, dùng `TaskExecutor` để chuyển việc gọi handler sang worker thread. Khi producer gửi message, channel giao một task cho executor; worker thread thực hiện dispatch tới subscriber được chọn. Nhờ đó, producer có thể tiếp tục sau khi executor chấp nhận task mà không phải đợi handler hoàn tất.

Async handoff tạo ra một ranh giới thực thi mới. Nó thay đổi thời điểm hoàn tất của `send()`, cách exception được quan sát, thứ tự xử lý, transaction boundary và việc truyền dữ liệu gắn với thread. Hiểu rõ những thay đổi này giúp tránh nhầm rằng message đã được xử lý chỉ vì thao tác gửi trả về thành công.

## 1. ExecutorChannel nằm ở đâu trong flow?

Một message flow thường có producer gửi message vào channel rồi channel chuyển message tới consumer. Với `DirectChannel`, subscriber được gọi đồng bộ trên thread gửi. Với `ExecutorChannel`, channel giao một task cho `TaskExecutor` để dispatch bất đồng bộ.

```mermaid
flowchart LR
    P[Producer thread] --> S[send message]
    S --> EC[ExecutorChannel]
    EC -->|submit task| Q[Executor task queue]
    Q --> W[Worker thread]
    W --> D[Dispatcher chọn subscriber]
    D --> H[Message handler]
```

Các bước chính:

1. Producer gọi `send()` trên `ExecutorChannel`.
2. Channel tạo công việc dispatch message và giao cho `TaskExecutor`.
3. Executor chấp nhận task hoặc từ chối nếu đã quá tải/shutdown.
4. Worker thread lấy task và dispatcher gọi handler phù hợp.
5. Handler hoàn tất hoặc phát sinh lỗi trên worker thread.

Queue ở sơ đồ là queue của executor, không phải một `QueueChannel` do Spring Integration tạo riêng. `ExecutorChannel` không phải message broker và không tự cung cấp persistence hay acknowledgement cho task đang chờ.

## 2. So sánh DirectChannel và ExecutorChannel

| Đặc điểm | `DirectChannel` | `ExecutorChannel` |
|---|---|---|
| Dispatch | Đồng bộ trên thread gửi | Giao task cho executor |
| Thời điểm handler chạy | Trong call stack của `send()` | Trên worker thread khi executor chạy task |
| Thời điểm `send()` trả về | Thường sau khi dispatch/handler hoàn tất | Thường sau khi task được executor chấp nhận |
| Exception từ handler | Có thể truyền về caller | Xảy ra bất đồng bộ; caller thường không nhận trực tiếp |
| Transaction | Có thể cùng thread với producer và chia sẻ transaction hiện tại | Không kéo transaction thread-bound của sender sang worker |
| Thứ tự hoàn tất | Theo lần dispatch đồng bộ | Có thể khác thứ tự gửi khi nhiều worker cùng xử lý |
| Tài nguyên cần quản lý | Thread của caller | Executor, worker, task queue và rejection policy |

`DirectChannel` phù hợp khi muốn xử lý ngay trong luồng gửi và cần exception/transaction cùng call stack. `ExecutorChannel` phù hợp khi muốn tách thời gian xử lý khỏi producer, cho phép worker xử lý song song và chấp nhận semantics bất đồng bộ.

Không nên đổi `DirectChannel` thành `ExecutorChannel` chỉ để tăng thread count. Ranh giới bất đồng bộ ảnh hưởng tới tính nhất quán, thứ tự, error handling và phản hồi của API gọi flow.

## 3. ExecutorChannel là point-to-point

`ExecutorChannel` dùng dispatcher kiểu unicast: một message được gửi tới một subscriber được chọn trong số các subscriber đã đăng ký. Khi có nhiều subscriber, dispatcher áp dụng cơ chế load balancing của nó; channel không tự broadcast cùng message tới tất cả subscriber.

Nếu mục tiêu là gửi cùng message tới mọi subscriber, dùng `PublishSubscribeChannel`. Channel đó có semantics publish-subscribe và có thể được cấu hình với executor để dispatch bất đồng bộ tới các subscriber.

| Nhu cầu | Channel phù hợp |
|---|---|
| Gửi message tới một handler theo cơ chế point-to-point | `DirectChannel` hoặc `ExecutorChannel` |
| Tách handler sang worker thread | `ExecutorChannel` |
| Phát cùng message tới nhiều subscriber | `PublishSubscribeChannel` |
| Lưu message để consumer chủ động nhận sau | `QueueChannel` hoặc một `PollableChannel` phù hợp |

Không nhầm `ExecutorChannel` với `QueueChannel`: executor queue giữ task thực thi, còn queue channel giữ message chờ consumer polling. Hai loại queue có lifecycle, timeout và semantics khác nhau.

## 4. Khai báo ExecutorChannel

Có thể tạo channel bằng cách truyền một `TaskExecutor`:

```java
@Configuration
class AsyncChannelConfiguration {

    @Bean("integrationExecutor")
    ThreadPoolTaskExecutor integrationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("si-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean("ordersAsyncChannel")
    MessageChannel ordersAsyncChannel(
            @Qualifier("integrationExecutor") TaskExecutor executor) {
        return new ExecutorChannel(executor);
    }
}
```

Pool trong ví dụ có 4 worker cốt lõi, tối đa 8 worker và queue chờ 200 task. Đây là cấu hình minh họa; cần chọn các con số theo thời gian xử lý, CPU, I/O, latency mục tiêu và giới hạn của hệ thống downstream.

Khi dùng `ThreadPoolTaskExecutor`, queue capacity và max pool size phối hợp với nhau. Thông thường executor tạo worker tới core size, sau đó ưu tiên xếp task vào queue; chỉ khi queue đầy mới tăng worker vượt core tới max size. Khi cả pool và queue đã đầy, rejection policy được áp dụng.

## 5. Nối channel vào IntegrationFlow

Ví dụ flow chuyển message qua một `ExecutorChannel` trước khi gọi service:

```java
@Bean
IntegrationFlow ordersFlow(OrderService orderService) {
    return IntegrationFlow
            .from("orders.input")
            .channel("ordersAsyncChannel")
            .handle(orderService, "process")
            .get();
}
```

Ở đây, các bước trước `ordersAsyncChannel` chạy theo execution model của upstream. Khi message được gửi qua channel này, việc dispatch tới handler phía sau được giao cho executor. Handler `process` chạy trên worker thread khi task được thực thi.

Có thể dùng `@ServiceActivator` thay cho Java DSL:

```java
@ServiceActivator(inputChannel = "ordersAsyncChannel")
public void process(Order order) {
    orderService.process(order);
}
```

Tên channel phải trỏ tới bean `ExecutorChannel` đã được khai báo. Nếu có nhiều flow dùng chung executor, hãy xác định rõ pool nào chịu trách nhiệm cho từng nhóm công việc để tránh một loại tải chiếm hết worker của loại khác.

## 6. Ý nghĩa của send() và async handoff

Với `ExecutorChannel`, thao tác `send()` thường trả về sau khi task được executor chấp nhận. Kết quả đó xác nhận việc dispatch được tiếp nhận theo semantics của executor/channel; nó không xác nhận handler đã bắt đầu hoặc nghiệp vụ đã hoàn tất.

Có ba trạng thái cần phân biệt:

1. **Message chưa được chấp nhận:** executor từ chối task hoặc channel không thể dispatch. Lỗi có thể xuất hiện ngay trên thread gửi.
2. **Task đã được chấp nhận nhưng đang chờ:** message nằm trong task queue của executor; handler chưa chạy.
3. **Task đang hoặc đã xử lý:** worker thực hiện handler; kết quả nghiệp vụ và lỗi được quan sát qua execution path bất đồng bộ.

Vì vậy, code sau không có nghĩa `orderService.process()` đã hoàn tất:

```java
boolean accepted = ordersAsyncChannel.send(message);
if (accepted) {
    log.info("Message was accepted for dispatch");
}
```

Nếu caller cần biết kết quả xử lý, phải thiết kế reply, callback, trạng thái công việc hoặc một cơ chế correlation phù hợp. Không dùng giá trị trả về của `send()` như acknowledgement nghiệp vụ.

## 7. Xử lý quá tải và rejection policy

Khi executor hết worker và queue đã đầy, task mới bị từ chối theo rejection policy. Đây là một điểm quan trọng của async handoff: producer có thể bị từ chối ngay cả khi channel vẫn tồn tại và message hợp lệ.

| Policy | Hành vi | Hệ quả với ExecutorChannel |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Producer nhận được tín hiệu quá tải ngay tại thao tác dispatch |
| `CallerRunsPolicy` | Thread gọi `execute()` chạy task nếu executor chưa shutdown | Async handoff có thể trở thành xử lý đồng bộ khi quá tải; sender bị block |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Có nguy cơ mất message âm thầm |
| `DiscardOldestPolicy` | Bỏ task cũ nhất trong queue rồi thử submit task mới | Có nguy cơ mất một message đang chờ |

Với message nghiệp vụ cần bảo toàn, không nên dùng policy bỏ task nếu không có yêu cầu rõ ràng cho phép mất dữ liệu. `AbortPolicy` giúp phát hiện quá tải, nhưng ứng dụng phải quyết định cách phản hồi: trả lỗi cho caller, retry có giới hạn, giảm tốc producer hoặc chuyển message sang một hệ thống lưu trữ bền vững.

`CallerRunsPolicy` tạo backpressure tự nhiên vì sender phải thực hiện công việc khi pool bão hòa. Tuy nhiên, nó làm thay đổi thread thực thi và có thể khiến HTTP request thread hoặc broker listener thread bị giữ lâu. Hãy đo tác động và bảo đảm handler an toàn khi chạy trên cả sender thread lẫn worker thread.

## 8. Queue của executor không phải durable message store

Task queue trong `ThreadPoolTaskExecutor` thường nằm trong bộ nhớ tiến trình. Nếu JVM dừng đột ngột, task đang chờ có thể mất. `ExecutorChannel` không tự ghi message xuống database hoặc broker và không có cơ chế redelivery bền vững như một message broker.

Nếu yêu cầu dữ liệu phải tồn tại qua restart, hãy đưa message qua broker có persistence/acknowledgement hoặc một cơ chế lưu bền vững trước ranh giới bất đồng bộ. Executor phù hợp cho scheduling và concurrency trong một tiến trình; nó không thay thế hạ tầng messaging durable.

Queue capacity cũng cần hữu hạn. Một queue quá lớn có thể giữ nhiều message payload trong heap, làm latency tăng và cuối cùng gây `OutOfMemoryError`. Theo dõi queue depth, remaining capacity, thời gian task chờ và rejected count.

## 9. Thứ tự xử lý và tính đồng thời

Khi executor có nhiều worker, các task có thể bắt đầu hoặc kết thúc theo thứ tự khác với thứ tự gửi. Ví dụ, message A được gửi trước message B nhưng handler của A gọi một API chậm; worker khác có thể hoàn tất B trước A.

Ngay cả khi executor queue FIFO, FIFO chỉ nói về thứ tự lấy task khỏi queue; nó không bảo đảm thứ tự hoàn tất khi nhiều worker cùng chạy. Ngoài ra, nếu `ExecutorChannel` có nhiều subscriber, dispatcher có thể phân phối các message tới subscriber khác nhau theo load balancing.

Nếu nghiệp vụ cần thứ tự:

- Dùng một worker cho nhóm message cần tuần tự hóa, nếu throughput cho phép.
- Partition theo business key để cùng một key đi qua cùng một luồng xử lý.
- Dùng sequence number và cơ chế resequencing nếu cần khôi phục thứ tự.
- Làm handler idempotent và xử lý message đến trễ hoặc trùng lặp.

Không dùng một executor nhiều thread cho nghiệp vụ có thứ tự nghiêm ngặt nếu chưa có cơ chế bảo đảm thứ tự ở tầng ứng dụng.

## 10. Exception và error channel ở ranh giới bất đồng bộ

Với `DirectChannel`, exception từ handler có thể quay lại sender vì handler chạy trong cùng call stack. Với `ExecutorChannel`, worker xử lý sau khi sender đã tiếp tục. Exception phát sinh trong handler vì vậy không thể tự truyền ngược về thread đã gọi `send()` và có thể không được bắt bởi `try/catch` bao quanh thao tác gửi.

Hãy cấu hình và kiểm thử error handling cho endpoint bất đồng bộ. Spring Integration hỗ trợ định tuyến lỗi qua error channel; có thể dùng header `errorChannel` trên message hoặc error channel mặc định của ứng dụng tùy cấu hình. Error flow thường nhận `ErrorMessage` chứa exception và thông tin message liên quan.

Ví dụ khai báo một error channel để quan sát lỗi:

```java
@Bean
MessageChannel integrationErrors() {
    return new PublishSubscribeChannel();
}

@ServiceActivator(inputChannel = "integrationErrors")
public void handleError(ErrorMessage errorMessage) {
    Throwable cause = errorMessage.getPayload();
    Message<?> failedMessage = errorMessage.getOriginalMessage();
    log.error("Asynchronous message handling failed: {}", failedMessage, cause);
}
```

Đoạn code minh họa cấu trúc error flow; cấu hình thực tế cần bảo đảm lỗi từ executor/endpoint được publish tới đúng error channel. Không giả định mọi exception đều tự động đến một bean tên `integrationErrors` nếu chưa cấu hình liên kết.

Nếu task bị executor từ chối trước khi chạy, đây là lỗi dispatch trên sender path. Nếu handler ném exception sau khi worker bắt đầu, đây là lỗi xử lý bất đồng bộ. Hai trường hợp cần log và recovery khác nhau.

## 11. Transaction không tự đi qua executor boundary

Spring transaction thông thường gắn với thread hiện tại. `DirectChannel` giữ handler trên cùng thread nên handler có thể tham gia transaction đang mở ở sender nếu cùng transaction manager và propagation phù hợp.

`ExecutorChannel` chuyển handler sang worker thread. Transaction đang mở trên sender thread không tự động lan sang worker. Vì vậy, transaction bao quanh `send()` không thể mặc nhiên bao gồm xử lý handler phía sau channel.

Nếu handler cần transaction, hãy đặt transaction boundary tại worker-side endpoint bằng transaction advice hoặc cơ chế phù hợp. Nếu cần nhất quán giữa cập nhật database và publish message, cân nhắc outbox/inbox, transactional broker hoặc thiết kế idempotent/retry phù hợp.

Không dựa vào việc `send()` trả về thành công để commit một transaction với giả định handler đã xử lý xong. Với async handoff, sender chỉ biết task đã được tiếp nhận; kết quả nghiệp vụ có thể xuất hiện sau đó.

## 12. ThreadLocal, SecurityContext và MDC

Thread-local state không tự động được chuyển từ sender thread sang worker thread. Những dữ liệu thường bị ảnh hưởng gồm:

- MDC logging context, ví dụ correlation ID và request ID.
- Security context được lưu theo thread.
- Transaction resource gắn với thread.
- Locale hoặc context tùy chỉnh do ứng dụng lưu trong `ThreadLocal`.

Thông tin cần thiết cho nghiệp vụ nên nằm trong payload hoặc message headers. Nếu cần truyền security context hoặc MDC, dùng cơ chế context propagation phù hợp như `TaskDecorator` hoặc wrapper được hỗ trợ, đồng thời dọn context sau khi task kết thúc để tránh rò rỉ giữa các task trên cùng worker.

Ví dụ, correlation ID nên được đặt thành header trước khi gửi qua channel:

```java
Message<Order> message = MessageBuilder
        .withPayload(order)
        .setHeader("correlationId", correlationId)
        .build();

ordersAsyncChannel.send(message);
```

Worker có thể đọc correlation ID từ message để ghi log hoặc liên kết các bước xử lý. Không nên dựa vào MDC của thread gửi sẽ tự có mặt trên worker.

## 13. Payload và thread safety

Message envelope và headers được thiết kế bất biến, nhưng payload object không tự động trở thành immutable. Khi gửi cùng một object qua `ExecutorChannel`, producer và worker có thể cùng giữ tham chiếu tới object đó trong các thời điểm khác nhau.

Nếu producer tiếp tục sửa payload sau khi gửi, worker có thể đọc dữ liệu đang thay đổi hoặc gặp race condition. Nên dùng DTO immutable, copy dữ liệu cần thiết trước khi handoff hoặc áp dụng đồng bộ hóa phù hợp nếu payload buộc phải mutable.

Handler chạy song song cũng cần thread-safe. Tránh cập nhật shared mutable state không có đồng bộ, dùng singleton service với field mutable không an toàn hoặc giả định mỗi handler chỉ được gọi một lần tại một thời điểm.

## 14. Request/reply qua ExecutorChannel

`ExecutorChannel` có thể nằm giữa request và handler cần tạo reply. Tuy nhiên, việc dispatch bất đồng bộ không có nghĩa caller tự động nhận reply ngay. Nếu dùng messaging gateway, gateway có thể chờ reply qua reply channel tới timeout đã cấu hình. Trong thời gian đó, worker xử lý request và gửi reply theo correlation/reply-channel metadata.

Nếu caller không cần reply, thiết kế theo kiểu fire-and-forget và cung cấp cách tra cứu trạng thái hoặc nhận kết quả sau. Nếu caller cần kết quả đồng bộ, hãy xác định timeout, reply channel và cách xử lý khi handler lỗi hoặc reply đến muộn.

Không giữ request thread chờ một reply dài chỉ để tạo cảm giác synchronous nếu hệ thống có thể dùng API bất đồng bộ rõ ràng hơn.

## 15. Interceptor và quan sát async handoff

Channel interceptor quan sát các thao tác gửi/nhận trên channel. Với `ExecutorChannel`, các callback quanh `send()` thường diễn ra trên sender path và phản ánh việc gửi/dispatch task, không nhất thiết phản ánh thời điểm handler hoàn tất trên worker.

Muốn đo end-to-end processing, hãy thêm metrics hoặc observation ở worker-side handler/endpoint. Nên phân biệt các mốc:

1. Thời điểm producer gửi message.
2. Thời điểm executor chấp nhận task.
3. Thời điểm worker bắt đầu xử lý.
4. Thời điểm handler hoàn tất hoặc thất bại.

Các metric hữu ích gồm queue wait, active worker, queue depth, rejected task, handler duration, error count và end-to-end latency p95/p99. Dùng message ID/correlation ID để nối log sender và worker.

## 16. Shutdown và lifecycle của executor

Executor là tài nguyên do application context quản lý nếu được khai báo thành bean. Khi context đóng, Spring thực hiện shutdown theo cấu hình của `ThreadPoolTaskExecutor`.

Các thuộc tính thường cần xem xét:

| Thuộc tính | Ý nghĩa |
|---|---|
| `waitForTasksToCompleteOnShutdown` | Chờ task đã nhận hoàn tất theo chính sách shutdown |
| `awaitTerminationSeconds` | Thời gian tối đa chờ executor kết thúc |
| `threadNamePrefix` | Giúp nhận diện worker trong log và thread dump |
| Queue capacity | Giới hạn số task chờ trong executor trước khi từ chối hoặc áp dụng policy |

Shutdown có trật tự cần ngừng nhận message mới, chờ hoặc xử lý task đang chạy, rồi giải phóng executor. Nếu timeout hết, cần biết task đang chờ sẽ bị hủy hay còn được thực thi tùy chính sách và phiên bản. Với flow động, stop/destroy endpoint trước khi đóng executor riêng do flow sở hữu. Không đóng executor dùng chung khi flow khác vẫn cần nó.

## 17. Chẩn đoán sự cố ExecutorChannel

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `send()` trả về nhưng handler chưa chạy | Task đang chờ trong executor queue | Queue depth, active worker, task wait time |
| `send()` bị exception ngay | Executor từ chối task hoặc channel không dispatch được | Rejected count, max pool, queue capacity, executor shutdown |
| Handler lỗi nhưng sender không nhận exception | Lỗi phát sinh trên worker thread | Error channel, error handler, log worker |
| Message hoàn tất sai thứ tự | Nhiều worker hoặc nhiều subscriber | Executor concurrency, dispatcher load balancing, sequence key |
| Latency tăng dù CPU thấp | Worker chờ I/O hoặc queue wait cao | Thread dump, downstream latency, queue depth |
| Message bị mất khi restart | Task queue chỉ ở bộ nhớ | Durable broker/store và shutdown policy |
| Sender bất ngờ bị block | `CallerRunsPolicy` hoặc xử lý đồng bộ ở một boundary khác | Rejection policy, channel topology, thread name |
| Context đóng chậm | Worker task bị block hoặc executor chờ quá lâu | Await termination, I/O timeout, thread dump |

Khi điều tra, tách lỗi dispatch khỏi lỗi handler. Kiểm tra executor còn nhận task không, task có được worker lấy ra không, handler đã bắt đầu chưa và error flow có nhận lỗi không. Chỉ nhìn log phía producer thường không đủ để biết điều gì xảy ra sau async handoff.

## 18. Nguyên tắc sử dụng ExecutorChannel

- **Chọn khi thực sự cần ranh giới bất đồng bộ:** xác định rõ caller không chờ handler hoàn tất.
- **Dùng executor có giới hạn:** cấu hình core/max size, queue capacity và rejection policy theo tải.
- **Không nhầm queue:** executor queue giữ task; `QueueChannel` giữ message.
- **Xác định semantics dispatch:** `ExecutorChannel` point-to-point; dùng `PublishSubscribeChannel` khi cần broadcast.
- **Thiết kế error flow:** tách lỗi từ chối task trên sender path và lỗi handler trên worker path.
- **Đặt transaction ở đúng thread:** transaction của sender không tự lan sang worker.
- **Truyền context có chủ đích:** payload/header cho dữ liệu nghiệp vụ, wrapper/TaskDecorator cho context theo thread.
- **Bảo vệ thứ tự và payload:** dùng immutable payload, handler thread-safe và partition/resequence nếu cần ordering.
- **Quan sát cả hai phía:** đo dispatch acceptance, queue wait, handler completion và rejected task.
- **Quản lý shutdown:** dừng producer/endpoint, drain hoặc xử lý task đang chạy, rồi đóng executor đúng chủ sở hữu.

Trước khi đặt một `ExecutorChannel` vào flow, hãy xác định caller cần biết điều gì khi `send()` trả về, task queue có giới hạn bao nhiêu, lỗi worker sẽ đi đâu, transaction nào áp dụng cho handler và thứ tự message có quan trọng không. Những câu trả lời này xác định hợp đồng async handoff và giúp channel hoạt động ổn định khi tải tăng hoặc downstream gặp sự cố.
