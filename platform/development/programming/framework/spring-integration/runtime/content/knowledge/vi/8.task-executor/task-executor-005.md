# ThreadPoolTaskExecutor và bounded queue

Trong **SPRING_INTEGRATION_RUNTIME**, executor quyết định task được thực thi trên thread nào và có bao nhiêu task có thể chờ worker. Khi một message flow chuyển xử lý sang executor, thread pool giúp giới hạn mức song song; **bounded queue** giới hạn số task chờ trong bộ nhớ. Hai giới hạn này quan trọng khi tốc độ producer có lúc cao hơn tốc độ xử lý của handler.

Spring cung cấp `ThreadPoolTaskExecutor` để cấu hình và quản lý một Java thread pool theo abstraction của Spring. Khi dùng với Spring Integration, executor có thể được gắn vào `ExecutorChannel`, poller hoặc các thành phần cần thực thi task bất đồng bộ. Muốn thread pool hoạt động ổn định, cần hiểu thứ tự nhận task, cách queue đầy, chính sách từ chối, ảnh hưởng tới transaction và cách shutdown.

## 1. Executor nằm ở đâu trong message flow?

Một message flow có thể chạy đồng bộ trên thread gửi hoặc chuyển một phần công việc sang worker thread. Với `DirectChannel`, subscriber thường được gọi trong thread gửi. Với `ExecutorChannel`, channel giao việc dispatch cho executor.

~~~mermaid
flowchart LR
    A["Producer"] --> B["DirectChannel"]
    B --> C["Endpoint / handler"]
    C --> D["ExecutorChannel"]
    D --> E["ThreadPoolTaskExecutor"]
    E --> F["Task queue"]
    E --> G["Worker threads"]
    G --> H["Handler downstream"]
~~~

Các thành phần có trách nhiệm khác nhau:

- **Channel** xác định cách message được chuyển giữa các bước.
- **Dispatcher** chọn subscriber nhận message.
- **Executor** thực thi task bằng thread hiện tại hoặc worker thread.
- **Task queue** giữ các task đã được nhận nhưng đang chờ worker.
- **Handler** thực hiện xử lý nghiệp vụ.

Khi một message đi qua `ExecutorChannel`, việc dispatch được giao cho executor. Producer thường không phải chờ handler hoàn tất; lời gọi gửi có thể kết thúc sau khi task được executor chấp nhận. Vì vậy, thời gian xử lý và exception của handler có thể xảy ra sau khi sender đã tiếp tục.

## 2. ThreadPoolTaskExecutor là gì?

`ThreadPoolTaskExecutor` là implementation của Spring cho `TaskExecutor`, được xây dựng trên Java `ThreadPoolExecutor`. Nó cung cấp các thuộc tính để kiểm soát số worker, queue, thời gian giữ thread nhàn rỗi, tên thread, chính sách từ chối và shutdown.

Các tham số quan trọng:

| Thuộc tính | Ý nghĩa | Tác động vận hành |
|---|---|---|
| `corePoolSize` | Số worker cơ bản | Mức song song nền của pool |
| `maxPoolSize` | Số worker tối đa | Giới hạn số task chạy đồng thời |
| `queueCapacity` | Số task tối đa được xếp hàng | Giới hạn backlog trong bộ nhớ của executor |
| `keepAliveSeconds` | Thời gian worker vượt core có thể nhàn rỗi trước khi bị thu hồi | Điều chỉnh khả năng co giãn pool |
| `allowCoreThreadTimeOut` | Cho phép worker core timeout | Có thể giảm thread khi tải thấp |
| `threadNamePrefix` | Tiền tố tên worker thread | Giúp đọc log và thread dump |
| `rejectedExecutionHandler` | Cách xử lý khi pool không nhận thêm task | Quyết định từ chối, chạy ở caller hoặc loại bỏ task |
| `taskDecorator` | Bọc task trước khi chạy | Truyền MDC hoặc context phù hợp sang worker |

Trong cấu hình mặc định phổ biến của `ThreadPoolTaskExecutor`, `corePoolSize` là 1, `maxPoolSize` rất lớn và `queueCapacity` mặc định là `Integer.MAX_VALUE`. Queue mặc định gần như không giới hạn khiến task thường được xếp hàng thay vì làm pool tăng worker vượt core. Vì vậy, nếu cần giới hạn backlog và kiểm soát concurrency, hãy cấu hình queue capacity cùng core/max một cách tường minh.

Một cấu hình minh họa:

~~~java
@Configuration
class IntegrationExecutorConfiguration {

    @Bean("integrationTaskExecutor")
    ThreadPoolTaskExecutor integrationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(30);
        executor.setThreadNamePrefix("si-worker-");

        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor;
    }
}
~~~

Spring quản lý bean executor và gọi lifecycle khởi tạo của nó. Khi cần sử dụng executor trong nhiều flow, có thể inject bean này vào các channel hoặc cấu hình poller tương ứng.

Các con số trong ví dụ chỉ để minh họa. Pool thực tế phải dựa trên thời gian xử lý, tốc độ message đến, giới hạn CPU, database connection pool và năng lực của hệ thống bên ngoài.

## 3. Bounded queue giới hạn điều gì?

### 3.1 Task queue khác message queue

Queue bên trong `ThreadPoolTaskExecutor` giữ **Runnable task** chờ worker thực thi. Khi Spring Integration giao một message cho executor, task có thể giữ tham chiếu tới message và logic dispatch.

Điều này khác với `QueueChannel`:

| Tiêu chí | Queue của ThreadPoolTaskExecutor | QueueChannel |
|---|---|---|
| Lưu gì? | Task thực thi, thường giữ message bên trong task | Đối tượng Message |
| Ai lấy phần tử? | Worker thread của executor | Polling consumer gọi `receive()` |
| Mục đích | Điều phối task và giới hạn công việc chờ worker | Đệm message giữa producer và consumer |
| Cấu hình giới hạn | `queueCapacity` | Dung lượng queue của channel |
| Độ bền | Thường là bộ nhớ của process | Phụ thuộc loại channel và MessageStore được cấu hình |
| Khi process dừng đột ngột | Task chờ có thể mất | Message trong queue bộ nhớ cũng có thể mất |

Bounded queue của executor không phải message broker và không tạo bảo đảm lưu message bền vững. Nó giới hạn số task đang chờ trong một pool.

### 3.2 Vì sao cần bounded queue?

Nếu queue không giới hạn, producer có thể tiếp tục submit task nhanh hơn tốc độ worker xử lý. Backlog sẽ tăng dần, kéo theo:

- Bộ nhớ bị chiếm bởi task và message được giữ trong task.
- Thời gian chờ của message tăng.
- Message cũ có thể chờ rất lâu trước khi được xử lý.
- Khi hệ thống phục hồi, một backlog lớn tiếp tục gây tải lên database hoặc dịch vụ ngoài.
- Process có thể thiếu heap và gặp lỗi do áp lực bộ nhớ.

Bounded queue tạo một giới hạn rõ ràng cho lượng công việc chờ. Khi queue đầy và pool đã đạt giới hạn worker, executor phải áp dụng rejection policy. Đây là thời điểm ứng dụng cần quyết định cách phản ứng với quá tải.

### 3.3 Queue capacity bằng 0 có nghĩa gì?

Trong `ThreadPoolTaskExecutor`, queue capacity dương tạo một `LinkedBlockingQueue` có giới hạn. Queue capacity bằng 0 hoặc âm sử dụng `SynchronousQueue`, tức cơ chế handoff trực tiếp giữa thread gửi task và worker.

`SynchronousQueue` không lưu task để chờ trong queue. Nếu không có worker sẵn sàng nhận, thread pool có thể tạo worker mới cho tới `maxPoolSize`; nếu đã đạt giới hạn, task bị từ chối theo rejection policy.

Do đó, queue capacity 0 không có nghĩa là “không giới hạn queue”. Nó có nghĩa là không giữ task chờ trong queue.

## 4. ThreadPoolExecutor nhận task theo thứ tự nào?

Để điều chỉnh pool chính xác, cần hiểu thuật toán nhận task của Java `ThreadPoolExecutor`. Với cấu hình thông thường, trình tự khái quát là:

1. Nếu số worker đang chạy nhỏ hơn `corePoolSize`, pool cố tạo worker mới để chạy task.
2. Nếu đã có đủ worker core, pool thử đưa task vào queue.
3. Nếu queue không nhận được task vì đã đầy, pool cố tạo worker mới cho tới `maxPoolSize`.
4. Nếu queue đầy và số worker đã đạt `maxPoolSize`, task bị từ chối.

~~~mermaid
flowchart TD
    A["Submit task"] --> B{"Workers < core?"}
    B -->|Có| C["Tạo worker chạy task"]
    B -->|Không| D{"Queue còn chỗ?"}
    D -->|Có| E["Đưa task vào queue"]
    D -->|Không| F{"Workers < max?"}
    F -->|Có| G["Tạo worker bổ sung"]
    F -->|Không| H["Rejection policy"]
~~~

Điểm quan trọng: pool thường ưu tiên queue sau khi đã đạt core size, rồi mới tăng worker vượt core khi queue đầy. Vì vậy, chỉ tăng `maxPoolSize` mà vẫn dùng queue rất lớn có thể không làm pool tăng worker như mong đợi.

Ví dụ `corePoolSize=4`, `maxPoolSize=12`, `queueCapacity=100`:

- Bốn task đầu có thể được giao cho bốn worker core.
- Các task tiếp theo được xếp vào queue khi queue còn chỗ.
- Khi queue đã đầy, pool mới có thể tạo worker thứ 5 tới worker thứ 12.
- Khi đủ 12 worker và queue vẫn đầy, task mới bị từ chối.

Đây là lý do phải xem xét đồng thời cả ba tham số core, max và queue capacity.

## 5. Cấu hình bounded queue với ExecutorChannel

### 5.1 Kết nối executor vào channel

`ExecutorChannel` sử dụng executor để dispatch message tới subscriber. Ví dụ:

Các import và kiểu `OrderService` được lược bỏ để tập trung vào cách nối channel với executor.

~~~java
@Configuration
class OrderFlowConfiguration {

    @Bean
    MessageChannel ordersAsyncChannel(
            @Qualifier("integrationTaskExecutor") Executor executor) {
        return new ExecutorChannel(executor);
    }

    @Bean
    IntegrationFlow orderFlow(
            MessageChannel ordersAsyncChannel,
            OrderService orderService) {

        return IntegrationFlow.from("orders.input")
            .channel(ordersAsyncChannel)
            .handle(orderService, "process")
            .get();
    }
}
~~~

Trong ví dụ này:

1. Producer gửi message vào channel đầu vào.
2. Flow chuyển message tới `ordersAsyncChannel`.
3. Executor nhận task dispatch.
4. Worker thread gọi handler `orderService.process`.

Nếu queue có chỗ, task được xếp hàng và sender có thể tiếp tục. Nếu pool và queue đều bão hòa, hành vi gửi phụ thuộc rejection policy.

### 5.2 ExecutorChannel không phải QueueChannel

Cả hai có thể tạo ra một khoảng cách thời gian giữa gửi và xử lý, nhưng cơ chế khác nhau:

- `ExecutorChannel` dispatch tới một subscriber thông qua executor. Queue nội bộ giữ task chờ worker.
- `QueueChannel` giữ Message và cần consumer poll để lấy message.
- Executor queue không cung cấp API `receive()` cho ứng dụng lấy task.
- QueueChannel không tự tạo worker pool; concurrency phụ thuộc consumer và cấu hình downstream.

Chọn `ExecutorChannel` khi cần tách việc dispatch sang worker. Chọn `QueueChannel` khi cần một message buffer mà consumer chủ động lấy message. Nếu cần độ bền, cân nhắc broker hoặc message store phù hợp.

## 6. Rejection policy khi pool bão hòa

Khi tất cả worker đã bận, queue đầy và không thể tạo thêm worker, executor gọi `RejectedExecutionHandler`. Chính sách này ảnh hưởng trực tiếp đến message flow.

### 6.1 AbortPolicy

`AbortPolicy` ném exception khi task bị từ chối. Đây là lựa chọn dễ quan sát vì producer hoặc tầng gọi có thể nhận biết hệ thống đã bão hòa.

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.AbortPolicy());
~~~

Trong flow, lỗi submit task có thể xuất hiện ngay tại thao tác dispatch. Cần xác định nơi bắt lỗi, ghi log/metric và quyết định retry hoặc trả lỗi cho caller. Không nên bắt exception rồi bỏ qua nếu message cần được xử lý.

### 6.2 CallerRunsPolicy

`CallerRunsPolicy` yêu cầu thread gọi `execute()` tự chạy task khi executor còn hoạt động nhưng đã bão hòa.

~~~java
executor.setRejectedExecutionHandler(
    new ThreadPoolExecutor.CallerRunsPolicy());
~~~

Cách này tạo backpressure tự nhiên: producer phải dành thời gian chạy task nên tốc độ submit giảm. Tuy nhiên, ranh giới bất đồng bộ có thể thay đổi theo tải. Handler đôi khi chạy trên worker thread, đôi khi chạy ngay trên thread gửi message.

Điều đó có thể làm thay đổi latency của producer, transaction đang gắn với thread và cách ứng dụng dùng ThreadLocal. Không nên dựa vào CallerRunsPolicy để bảo đảm handler luôn chạy trên một thread cụ thể. Khi executor đã shutdown, CallerRunsPolicy của JDK không chạy task bị từ chối.

### 6.3 DiscardPolicy và DiscardOldestPolicy

- `DiscardPolicy` bỏ task mới bị từ chối mà không ném exception.
- `DiscardOldestPolicy` loại task cũ nhất đang chờ rồi thử submit task mới.

Hai chính sách này có thể làm mất công việc mà ứng dụng không nhận được tín hiệu lỗi rõ ràng. Với message flow xử lý đơn hàng, thanh toán hoặc dữ liệu cần bảo đảm, không nên chọn chúng nếu chưa có cơ chế bù, audit và chấp nhận mất message rõ ràng.

### 6.4 Chọn chính sách theo yêu cầu nghiệp vụ

| Chính sách | Hành vi | Khi cân nhắc |
|---|---|---|
| AbortPolicy | Từ chối bằng exception | Cần phát hiện quá tải và xử lý lỗi tường minh |
| CallerRunsPolicy | Thread gửi tự chạy task | Có thể dùng để tạo backpressure, chấp nhận producer bị chặn |
| DiscardPolicy | Bỏ task mới | Chỉ với công việc có thể mất và đã có giám sát riêng |
| DiscardOldestPolicy | Bỏ task cũ nhất trong queue | Chỉ với dữ liệu ưu tiên mới nhất và có chính sách mất dữ liệu rõ ràng |
| Custom handler | Hành vi do ứng dụng định nghĩa | Cần metric, audit hoặc điều phối đặc biệt |

Không có rejection policy tốt nhất cho mọi hệ thống. Cần gắn nó với SLA, khả năng retry, độ quan trọng của message và cách producer phản ứng khi bị từ chối.

## 7. Chọn corePoolSize, maxPoolSize và queueCapacity

### 7.1 Đo tốc độ đến và thời gian xử lý

Trước khi chọn pool size, thu thập:

- Tốc độ task đến trung bình và lúc cao điểm.
- Thời gian xử lý trung bình, p95 và p99.
- Tỷ lệ task CPU-bound và I/O-bound.
- Giới hạn connection pool của database và dịch vụ ngoài.
- Mức độ cho phép xử lý song song theo khóa nghiệp vụ.
- Thời gian chờ tối đa mà message có thể chấp nhận.

Một ước lượng sơ bộ: nếu handler mất trung bình 100 ms và có 8 worker hoạt động, năng lực lý thuyết là khoảng 80 task/giây khi worker luôn bận. Đây chỉ là ước lượng đơn giản; thời gian I/O, lock, GC, downstream và phân bố thời gian xử lý có thể làm throughput thực tế khác đáng kể.

Nếu database chỉ cho phép 10 connection đồng thời, tăng worker lên 100 có thể làm nhiều task cùng chờ connection thay vì tăng throughput. Pool nên được điều chỉnh theo nút thắt thực tế.

### 7.2 Queue là bộ đệm cho burst, không phải nơi giữ backlog vô hạn

Queue capacity nên đủ hấp thụ burst ngắn mà hệ thống có thể xử lý trong giới hạn độ trễ cho phép. Queue quá lớn có thể che giấu tình trạng thiếu năng lực xử lý và khiến message chờ quá lâu.

Ví dụ, nếu hệ thống xử lý được 80 task/giây và burst làm backlog tăng thêm 160 task, queue 160 có thể hấp thụ khoảng hai giây công việc trong điều kiện lý tưởng. Nếu tốc độ đến tiếp tục cao hơn tốc độ hoàn thành, queue sẽ lại đầy; tăng queue chỉ trì hoãn thời điểm từ chối.

Một nguyên tắc vận hành:

- Chọn worker theo concurrency mà CPU và dependency có thể chịu.
- Chọn queue theo burst và thời gian chờ tối đa.
- Chọn rejection policy theo khả năng backpressure hoặc retry.
- Đặt metric để nhận ra queue đang tăng trước khi nó đầy liên tục.

### 7.3 Vì sao queue lớn có thể làm latency xấu hơn?

Khi queue đầy 1000 task, một task mới có thể phải chờ toàn bộ task trước nó được xử lý. Nếu worker xử lý chậm, task mới dù chưa bị từ chối vẫn có thể vi phạm SLA.

Bounded queue cần được chọn theo thời gian chờ có thể chấp nhận, không chỉ theo số lượng message. Queue capacity là giới hạn số task chờ, không phải cam kết về thời gian hoàn thành.

## 8. Backpressure và bảo vệ hệ thống downstream

Backpressure là cách làm chậm nguồn phát khi hệ thống phía sau không còn khả năng nhận thêm công việc. Bounded queue kết hợp rejection policy có thể tạo tín hiệu quá tải hoặc làm producer chạy chậm lại.

Các cách xử lý thường gặp:

- **Abort + retry có backoff**: producer nhận lỗi và thử lại sau khoảng thời gian tăng dần.
- **CallerRunsPolicy**: producer phải thực thi task và tự giảm tốc độ gửi.
- **Giới hạn concurrency**: giảm số worker để bảo vệ database hoặc API.
- **QueueChannel/broker**: tách producer và consumer, có thể giữ message theo cơ chế lưu trữ riêng.
- **Rate limiting**: giới hạn tốc độ gửi trước khi submit task.
- **Circuit breaker**: tạm ngừng gọi dependency đang lỗi để tránh dồn task chờ.

Không retry ngay lập tức trong vòng lặp nhanh khi executor từ chối task. Cách đó có thể tạo thêm áp lực đúng lúc hệ thống đang quá tải. Cần delay, jitter, giới hạn lần thử và dead-letter/error flow khi message không thể tiếp tục.

## 9. Thread context, transaction và exception

### 9.1 Transaction không tự truyền sang worker thread

Transaction Spring thông thường gắn với thread hiện tại. Khi message được chuyển qua `ExecutorChannel`, handler chạy trên worker thread; transaction của producer không tự truyền sang worker.

Nếu handler cần transaction, hãy đặt transaction boundary tại endpoint hoặc service xử lý trên worker thread. Không dựa vào việc sender và handler đôi khi chạy cùng thread do CallerRunsPolicy; đó là hành vi chỉ xuất hiện khi pool bão hòa.

### 9.2 MDC và ThreadLocal

Các giá trị trong ThreadLocal, ví dụ MDC của logging, không tự động được sao chép sang worker thread. Nếu cần correlation ID hoặc thông tin tracing trong log, có thể dùng `TaskDecorator` để chụp context ở thread submit và khôi phục context trong worker.

Ví dụ minh họa với MDC của SLF4J:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(captured);
            }
            task.run();
        }
        finally {
            if (previous == null) {
                MDC.clear();
            }
            else {
                MDC.setContextMap(previous);
            }
        }
    };
});
~~~

Đoạn code cần các import MDC và Map tương ứng. Việc khôi phục context cũ trong finally giúp tránh để dữ liệu của task trước rò sang task kế tiếp trên cùng worker thread.

Với tracing hoặc security context, ưu tiên cơ chế propagation do thư viện tương ứng cung cấp; không sao chép mọi ThreadLocal một cách tùy tiện.

### 9.3 Exception trong xử lý bất đồng bộ

Nếu task bị từ chối ngay lúc submit, lỗi có thể xuất hiện ở sender. Nếu task đã được nhận và handler ném exception sau đó, sender thường không thể nhận exception đó như một lời gọi đồng bộ.

Cần cấu hình error handling cho flow, sử dụng error channel hoặc cơ chế giám sát phù hợp. Ghi nhận riêng:

- Lỗi submit do queue đầy hoặc executor shutdown.
- Lỗi handler khi task đang chạy.
- Lỗi dependency như database hoặc HTTP.
- Lỗi retry đã hết số lần thử.

Không đánh đồng “send thành công” với “handler xử lý thành công”. Với executor, send thành công thường chỉ cho biết task đã được chấp nhận để thực thi.

## 10. Shutdown và task đang chờ

ThreadPoolTaskExecutor là tài nguyên có lifecycle. Khi ứng dụng dừng, cần xác định task đang chạy và task còn trong queue sẽ được xử lý thế nào.

Có thể cấu hình:

~~~java
executor.setWaitForTasksToCompleteOnShutdown(true);
executor.setAwaitTerminationSeconds(30);
~~~

Ý nghĩa:

- Yêu cầu executor chờ task đã submit hoàn tất trong quá trình shutdown.
- Giới hạn thời gian chờ ở ví dụ là 30 giây.
- Nếu hết thời gian chờ, ứng dụng cần hiểu rõ task còn lại có thể chưa hoàn thành.

Graceful shutdown nên phối hợp với message flow:

1. Ngừng nhận message mới từ ingress hoặc producer.
2. Đợi các task đã submit hoàn tất trong thời gian cho phép.
3. Theo dõi active worker và queue size.
4. Dừng endpoint và giải phóng executor theo lifecycle.
5. Ghi nhận task chưa hoàn thành để có thể phục hồi nếu nghiệp vụ yêu cầu.

Queue của executor chỉ nằm trong bộ nhớ. Nếu process bị kill hoặc máy mất điện, task đang chờ không được bảo đảm tồn tại. Với message cần độ bền, hãy lưu trong broker hoặc store bền vững trước khi giao cho worker.

## 11. Quan sát ThreadPoolTaskExecutor trong runtime

ThreadPoolTaskExecutor cung cấp một số thông tin runtime như pool size, active count và số task đã hoàn thành. Có thể kết hợp với metric của ứng dụng để quan sát:

| Chỉ số | Ý nghĩa | Dấu hiệu cần chú ý |
|---|---|---|
| Pool size | Số worker hiện tại | Luôn chạm max có thể báo thiếu năng lực |
| Active count | Số worker đang bận | Luôn bằng pool size nghĩa là pool thường xuyên bão hòa |
| Queue size | Số task đang chờ | Tăng liên tục nghĩa là tốc độ đến cao hơn tốc độ xử lý |
| Completed task count | Số task hoàn tất | Dùng để tính throughput theo thời gian |
| Rejected task count | Số task bị từ chối, nếu có metric riêng | Tăng đột biến báo quá tải hoặc shutdown |
| Queue wait time | Thời gian task chờ trước khi chạy | Cao có thể làm vi phạm SLA dù không bị reject |
| Handler duration | Thời gian xử lý nghiệp vụ | Giúp phân biệt nghẽn executor với nghẽn downstream |

Một số thuộc tính có thể lấy từ executor đã khởi tạo:

~~~java
int poolSize = executor.getPoolSize();
int activeCount = executor.getActiveCount();
int queueSize = executor.getThreadPoolExecutor()
    .getQueue()
    .size();
~~~

Chỉ gọi `getThreadPoolExecutor()` sau khi executor đã được khởi tạo. Nếu bean chưa initialize, underlying executor chưa sẵn sàng.

Đặt tên thread có ý nghĩa để tìm trong log và thread dump, ví dụ `si-order-`, `si-invoice-`. Theo dõi queue size cùng queue wait time; chỉ nhìn CPU hoặc active count sẽ không đủ để kết luận nguyên nhân chậm.

## 12. Quy trình chẩn đoán khi queue đầy

Khi executor liên tục đầy queue hoặc từ chối task, kiểm tra theo thứ tự:

1. Xác nhận task nào đang được submit và từ endpoint/channel nào.
2. Đo tốc độ task đến trong khoảng thời gian đại diện.
3. Đo thời gian xử lý trung bình và p95/p99 của handler.
4. Kiểm tra pool size, active count và queue size.
5. Kiểm tra dependency: database pool, remote API, lock, file I/O.
6. Xem rejection policy và nơi xử lý exception.
7. Kiểm tra có retry quá nhanh làm tăng thêm tải hay không.
8. Đối chiếu queue wait time với SLA.
9. Điều chỉnh worker, queue hoặc backpressure rồi đo lại.

Không tăng queue capacity trước khi hiểu vì sao worker không xử lý kịp. Nếu database là nút thắt, tăng worker có thể chỉ làm nhiều connection request cùng chờ hơn. Nếu handler có một đoạn CPU-bound, tăng concurrency quá cao có thể làm context switching tăng và throughput giảm.

## 13. Kiểm thử bounded queue và rejection

Nên kiểm tra cả trạng thái bình thường và lúc bão hòa:

- Pool chạy đúng core/max theo tải thử.
- Queue không vượt capacity đã cấu hình.
- Task được nhận khi queue còn chỗ.
- Rejection policy hoạt động đúng khi worker và queue đều đầy.
- CallerRunsPolicy làm producer chậm lại như mong muốn.
- AbortPolicy phát tín hiệu lỗi để caller có thể xử lý.
- TaskDecorator khôi phục MDC sau khi task kết thúc.
- Shutdown chờ task theo giới hạn thời gian.
- Task bị từ chối hoặc lỗi handler được ghi nhận qua log/metric/error flow.

Để kiểm thử rejection một cách xác định, có thể dùng handler giả có latch để giữ worker bận, submit đủ task lấp queue rồi submit thêm một task. Tránh dùng sleep ngẫu nhiên để đoán thời điểm queue đầy.

## 14. Những nhầm lẫn cần tránh

- **Bounded executor queue không phải QueueChannel**: một bên lưu task, một bên lưu Message.
- **maxPoolSize không có nghĩa pool luôn tăng tới max**: thread pool thường queue task sau khi đạt core và chỉ tăng worker vượt core khi queue đầy.
- **Queue lớn không làm throughput tăng**: nó chỉ giữ thêm task chờ và có thể làm latency tăng.
- **Queue capacity 0 không phải queue vô hạn**: nó dùng cơ chế handoff trực tiếp.
- **ExecutorChannel không bảo đảm xử lý thành công**: nó chỉ giao việc dispatch cho executor.
- **CallerRunsPolicy làm thay đổi thread thực thi**: không dựa vào thread boundary cố định khi pool bão hòa.
- **Discard policy có thể làm mất task**: không dùng cho message quan trọng nếu thiếu cơ chế bù.
- **Transaction và ThreadLocal không tự truyền qua worker**: cần cấu hình boundary và context propagation.
- **Queue trong bộ nhớ không bền vững**: cần broker hoặc store phù hợp khi message không được phép mất.
- **Tăng pool không luôn tăng throughput**: phải xét giới hạn database, API, CPU và lock.

## 15. Tự kiểm tra

1. Với corePoolSize = 4, maxPoolSize = 12 và queueCapacity = 100, khi nào worker thứ 5 được tạo?
2. Vì sao một queue không giới hạn có thể khiến maxPoolSize gần như không phát huy tác dụng?
3. Queue của ThreadPoolTaskExecutor giữ Runnable hay Message? Nó khác QueueChannel ở điểm nào?
4. Khi queue đầy, AbortPolicy và CallerRunsPolicy tạo ra hành vi khác nhau như thế nào?
5. Vì sao CallerRunsPolicy có thể làm transaction và thread context quan sát được thay đổi?
6. Nếu queue size tăng liên tục nhưng CPU thấp, cần kiểm tra dependency nào trước khi tăng worker?
7. Vì sao không thể dựa vào executor queue để bảo đảm message tồn tại sau khi process bị kill?
8. Khi gỡ một flow hoặc shutdown ứng dụng, cần phối hợp executor và ingress theo trình tự nào?

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java — ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
- [Spring Integration — ExecutorChannel API](https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/channel/ExecutorChannel.html)

## Kết luận

ThreadPoolTaskExecutor quản lý worker thread và task queue cho các thành phần cần thực thi bất đồng bộ. Bounded queue giới hạn lượng task chờ, còn corePoolSize và maxPoolSize giới hạn mức song song. Khi queue đầy, rejection policy quyết định cách hệ thống phản ứng; lựa chọn đó ảnh hưởng tới backpressure, khả năng mất task và thread thực thi. Muốn cấu hình ổn định, hãy đo tốc độ task đến, thời gian xử lý, queue wait time và giới hạn downstream, sau đó chọn pool, queue và chính sách từ chối theo SLA. Executor queue chỉ là bộ đệm trong bộ nhớ; message cần độ bền phải được lưu bằng broker hoặc store phù hợp trước khi xử lý bất đồng bộ.
