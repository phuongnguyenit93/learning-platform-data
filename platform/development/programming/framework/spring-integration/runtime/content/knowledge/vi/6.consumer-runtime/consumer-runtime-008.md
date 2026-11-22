# Poller task executor và concurrent polling

Trong Spring Integration, poller quyết định khi nào một polling endpoint lấy message từ nguồn. Khi flow cần xử lý nhiều message hoặc một lần poll có thể mất nhiều thời gian, ta thường cân nhắc gắn `TaskExecutor` vào poller để các lần poll chạy trên worker thread. Cấu hình này có thể tăng throughput, nhưng cũng có thể làm nhiều lần poll chồng lấn, thay đổi thứ tự xử lý và tạo áp lực lên database, broker hoặc dịch vụ phía sau.

Để chọn đúng cấu hình, cần tách ba khái niệm: `TaskScheduler` lên lịch thời điểm poll, `TaskExecutor` thực thi công việc poll, còn `maxMessagesPerPoll` giới hạn số message được lấy trong một lần poll. Chúng tác động tới ba khía cạnh khác nhau và không thể thay thế cho nhau.

## 1. Poller nằm ở đâu trong consumer runtime?

Spring Integration có hai dạng polling endpoint thường gặp:

- `SourcePollingChannelAdapter` chủ động gọi `MessageSource.receive()` để lấy message từ một nguồn bên ngoài rồi gửi message vào channel.
- `PollingConsumer` lấy message từ một `PollableChannel`, ví dụ `QueueChannel`, rồi chuyển cho handler xử lý.

Cả hai dùng poller để kích hoạt việc nhận message theo lịch. Chúng khác nhau ở nơi message được lấy ra: một bên đọc từ `MessageSource`, bên kia nhận từ channel có khả năng poll.

Luồng xử lý khái quát:

~~~mermaid
flowchart LR
    T[TaskScheduler] -->|Đến thời điểm poll| P[Polling task]
    P -->|Submit công việc| X[TaskExecutor]
    X --> W[Worker thread]
    W --> R[Receive message]
    R --> H[Message handler]
    H --> C[Output channel / reply]
~~~

Khi không cấu hình executor riêng cho poller, tác vụ poll có thể chạy trực tiếp trên thread thực thi lịch. Khi cấu hình `TaskExecutor`, poller giao công việc poll cho executor. Worker thread sẽ thực hiện thao tác nhận message và phần xử lý đồng bộ tiếp theo của endpoint.

Nếu downstream channel là `DirectChannel`, handler tiếp theo thường chạy trên cùng worker thread. Nếu flow chuyển sang `ExecutorChannel`, một ranh giới bất đồng bộ khác được tạo ra và công việc phía sau có thể chạy trên pool khác. Cần vẽ rõ các ranh giới thread trước khi tăng số pool.

## 2. Phân biệt TaskScheduler và TaskExecutor

Hai abstraction có mục đích khác nhau:

| Thành phần | Trách nhiệm | Câu hỏi cần trả lời |
|---|---|---|
| `TaskScheduler` | Lên lịch thời điểm kích hoạt poll theo fixed delay, fixed rate hoặc cron | Khi nào poll tiếp theo được kích hoạt? |
| `TaskExecutor` | Chạy tác vụ poll trên thread thực thi | Thread nào thực hiện lần poll này? |
| `maxMessagesPerPoll` | Giới hạn số message xử lý trong một lần poll | Một lần poll được lấy bao nhiêu message? |

Ví dụ, poller có thể được kích hoạt mỗi 500 ms bởi scheduler, giao tác vụ cho executor có 4 worker và xử lý tối đa 10 message trong mỗi lần poll. Ba con số này lần lượt mô tả nhịp kích hoạt, khả năng chạy song song và số message trong một lượt.

Không nên hiểu `TaskExecutor` là bộ định thời. Executor không quyết định cron hay fixed delay; nó chỉ chạy task đã được kích hoạt. Tương tự, tăng `maxMessagesPerPoll` không tạo thêm worker thread.

## 3. Cấu hình fixed delay và TaskExecutor

Ví dụ sau tạo một `QueueChannel` và polling consumer lấy tối đa 10 message mỗi lần poll. Poller được kích hoạt theo fixed delay và thực thi trên pool riêng:

~~~java
@Configuration
@EnableIntegration
public class OrderPollingConfiguration {

    @Bean
    QueueChannel ordersQueue() {
        return new QueueChannel(1_000);
    }

    @Bean
    ThreadPoolTaskExecutor orderPollerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("orders-poller-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }

    @Bean
    IntegrationFlow orderPollingFlow(
            QueueChannel ordersQueue,
            TaskExecutor orderPollerExecutor,
            OrderService orderService) {

        return IntegrationFlow.from(ordersQueue, endpoint -> endpoint
                        .poller(Pollers.fixedDelay(Duration.ofMillis(500))
                                .maxMessagesPerPoll(10)
                                .taskExecutor(orderPollerExecutor)))
                .handle(orderService, "process")
                .get();
    }
}
~~~

Các import liên quan trong ví dụ:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
~~~

`ThreadPoolTaskExecutor` được Spring quản lý như một bean và khởi tạo theo lifecycle của bean. `corePoolSize` là số worker cốt lõi, `maxPoolSize` là giới hạn worker tối đa, còn `queueCapacity` là số task có thể chờ trong hàng đợi của executor. Với `ThreadPoolExecutor`, task thường được xếp vào queue sau khi core thread bận; pool chỉ mở rộng vượt core khi queue đầy và còn dưới `maxPoolSize`. Vì vậy, `maxPoolSize=8` không có nghĩa ứng dụng lập tức chạy 8 poll song song.

Ví dụ dùng queue capacity hữu hạn để tạo giới hạn cho task đang chờ. Khi queue đầy và pool đã đạt giới hạn, executor có thể từ chối task theo rejection policy. Hãy theo dõi số task bị từ chối và chọn chính sách phù hợp; không dùng một queue không giới hạn để che giấu tình trạng poller tạo task nhanh hơn khả năng xử lý.

## 4. Fixed delay, fixed rate và cron

Poller có thể được kích hoạt theo các chiến lược lịch khác nhau:

| Kiểu trigger | Ý nghĩa | Khi phù hợp |
|---|---|---|
| Fixed delay | Lên lịch lần tiếp theo sau khoảng delay tính từ lần thực thi lịch trước | Công việc định kỳ, ưu tiên khoảng nghỉ giữa các lần kích hoạt |
| Fixed rate | Kích hoạt theo nhịp thời gian đều đặn | Cần nhịp polling ổn định theo đồng hồ |
| Cron | Kích hoạt theo biểu thức lịch | Đồng bộ theo giờ, ngày hoặc lịch nghiệp vụ |

Ví dụ DSL:

~~~java
Pollers.fixedDelay(Duration.ofSeconds(1));
Pollers.fixedRate(Duration.ofSeconds(1));
Pollers.cron("0 */5 * * * *");
~~~

Lưu ý khi có `TaskExecutor`: scheduler có thể hoàn tất bước dispatch sau khi submit poll task vào executor, trong khi worker vẫn đang xử lý message. Do đó, fixed delay giữa các lần kích hoạt không nhất thiết là khoảng nghỉ sau khi toàn bộ xử lý message trước hoàn tất. Nếu worker chạy lâu hơn chu kỳ kích hoạt, task mới có thể được submit khi task trước vẫn đang chạy. Đây là một nguồn tạo concurrent polling.

Nếu yêu cầu là không bao giờ có hai lần poll đồng thời, phải thiết kế để lần poll trước hoàn tất trước khi lần sau được phép bắt đầu, ví dụ dùng executor một worker với cơ chế xếp hàng phù hợp hoặc một cơ chế khóa/điều phối rõ ràng. Không suy ra tính tuần tự chỉ từ việc dùng `fixedDelay`.

## 5. maxMessagesPerPoll và concurrent polling

`maxMessagesPerPoll` giới hạn số message mà một polling task lấy trong một lượt. Giá trị dương đặt giới hạn cụ thể; giá trị `-1` biểu thị tiếp tục nhận message cho tới khi nguồn không còn message. Giá trị mặc định có thể khác giữa các loại polling endpoint, vì vậy nên cấu hình tường minh khi hành vi này quan trọng.

Ví dụ với `maxMessagesPerPoll(10)`, một worker có thể nhận tối đa 10 message trong một lượt poll. Nếu executor có nhiều worker và scheduler kích hoạt nhiều lượt trong lúc các worker trước chưa xong, nhiều lượt poll có thể cùng hoạt động. Khi đó tổng số message đang được xử lý có thể lớn hơn 10.

Phân biệt hai kiểu tăng tải:

- **Tăng batch size:** tăng `maxMessagesPerPoll`, một poll task xử lý nhiều message hơn trước khi kết thúc.
- **Tăng concurrency:** cho phép nhiều poll task chạy cùng lúc trên nhiều worker.

Hai cách có hệ quả khác nhau. Batch lớn có thể giảm overhead scheduling nhưng giữ worker lâu hơn và làm một transaction chứa nhiều message hơn nếu transaction bao quanh poll. Concurrency cao có thể tăng throughput khi tài nguyên còn dư, nhưng làm tăng số message đang xử lý, kết nối database đồng thời và mức cạnh tranh trên tài nguyên dùng chung.

Với `maxMessagesPerPoll(-1)`, một nguồn liên tục có message có thể khiến một lượt poll chạy rất lâu. Nếu không có executor riêng, thread scheduler có thể bị chiếm dụng. Nếu có executor, worker có thể liên tục tiêu thụ message trong khi các lần kích hoạt tiếp theo tiếp tục được submit, làm tăng hàng đợi task. Dùng batch hữu hạn giúp giới hạn thời gian một worker dành cho mỗi lượt và tạo cơ hội công bằng hơn giữa các nguồn công việc.

## 6. Concurrent polling tác động tới thứ tự và tính an toàn

Khi có nhiều poll task chạy đồng thời, thứ tự message bắt đầu xử lý có thể khác thứ tự hoàn tất. Ví dụ, message A được nhận trước nhưng xử lý chậm; message B được nhận sau và hoàn tất trước. Nếu nghiệp vụ yêu cầu thứ tự theo khóa, chỉ tăng poller concurrency có thể làm sai thứ tự quan sát.

Trước khi bật concurrent polling, hãy kiểm tra:

1. **MessageSource có thread-safe không?** Nguồn tùy chỉnh phải chịu được nhiều thread gọi `receive()` cùng lúc hoặc phải được bảo vệ bằng đồng bộ phù hợp.
2. **Handler có thread-safe không?** Không chia sẻ mutable state không được bảo vệ giữa các lần xử lý.
3. **Thứ tự nghiệp vụ có quan trọng không?** Nếu cần thứ tự theo order/customer key, dùng partitioning, serial executor theo key hoặc thiết kế consumer riêng cho từng partition.
4. **Tài nguyên phía sau có chịu tải không?** Database connection pool, HTTP connection pool và giới hạn rate của dịch vụ bên ngoài phải phù hợp với concurrency.
5. **Message có thể được xử lý trùng không?** Retry, redelivery và transaction rollback đòi hỏi handler idempotent hoặc có cơ chế deduplication.

`QueueChannel` có thể được nhiều consumer poll đồng thời, nhưng việc message được lấy khỏi queue không bảo đảm thứ tự hoàn tất xử lý. Với `DirectChannel`, concurrency thường đến từ nhiều thread gửi đồng thời; với `ExecutorChannel`, nó đến từ executor downstream. Hãy xác định đúng nơi tạo concurrency thay vì chỉ nhìn vào poller.

## 7. Transaction và advice khi polling song song

Poller có thể kết hợp advice chain để áp dụng transaction, retry, logging hoặc các hành vi cắt ngang khác quanh lần poll. Khi bật concurrency, mỗi poll task có thể chạy trên thread riêng và transaction thường được tạo theo ranh giới thực thi của task đó, tùy cấu hình advice và transaction manager.

Một số hệ quả cần lưu ý:

- Transaction không tự truyền từ thread gửi message sang worker thread. Worker cần transaction của chính nó hoặc cơ chế context propagation được hỗ trợ.
- Nếu một poll task lấy nhiều message trong một transaction, lỗi ở một message có thể ảnh hưởng kết quả commit/rollback của cả lượt tùy cấu hình.
- Nhiều poll task đồng thời có thể mở nhiều transaction và chiếm nhiều connection database hơn.
- Retry quanh poll task có thể thử lại một đơn vị công việc lớn hơn một message đơn lẻ, tùy vị trí advice trong chuỗi.
- Với broker, acknowledgment và transaction phải tương thích với adapter và broker; không giả định transaction database tự bao trùm acknowledgment bên ngoài.

Khi cần transaction, hãy xác định rõ ranh giới mong muốn: một transaction cho mỗi message hay cho một poll batch. Sau đó kiểm tra bằng log transaction và thử nghiệm với lỗi ở message giữa batch. Nếu nghiệp vụ không chấp nhận rollback nhiều message cùng nhau, giảm batch size hoặc chuyển ranh giới transaction về từng message theo thiết kế phù hợp.

## 8. Backpressure và giới hạn tài nguyên

Concurrent polling chỉ có lợi khi downstream còn khả năng xử lý. Nếu poller tạo công việc nhanh hơn handler hoàn tất, task sẽ tích tụ trong executor queue hoặc message tiếp tục tích tụ trong channel/broker.

Hãy đặt giới hạn ở nhiều lớp:

| Lớp | Giới hạn nên xem xét |
|---|---|
| Poller | Chu kỳ kích hoạt, `maxMessagesPerPoll`, số endpoint poll cùng nguồn |
| TaskExecutor | Core/max pool size, queue capacity, rejection policy |
| QueueChannel | Capacity, send timeout và chiến lược khi đầy |
| Database | Connection pool, transaction timeout và giới hạn truy vấn đồng thời |
| Remote service | Connection pool, rate limit, timeout và circuit breaker |
| Broker | Consumer concurrency, prefetch, acknowledgment và partition ownership |

Không nên tăng đồng thời pool size, batch size và số endpoint chỉ vì backlog đang tăng. Trước tiên xác định bottleneck: poller không lấy đủ nhanh, executor thiếu worker, handler chậm, database hết connection hay remote service giới hạn tốc độ. Tăng concurrency khi bottleneck nằm ở downstream có thể làm backlog và lỗi tăng nhanh hơn.

Với executor queue hữu hạn, rejection là một tín hiệu áp lực ngược. Hãy quyết định task bị từ chối sẽ được báo lỗi, retry hoặc làm chậm nguồn như thế nào. Không bỏ qua exception từ executor vì message có thể không được xử lý như kỳ vọng.

## 9. Error handling và shutdown

Lỗi phát sinh trên worker thread có thể không truyền ngược về thread đã gửi message ban đầu. Với polling endpoint, hãy cấu hình error handling phù hợp và quan sát ErrorMessage, errorChannel, retry count cùng log theo message ID/Correlation ID. Nếu một message gây lỗi liên tục, cần có giới hạn retry và dead-letter/error flow để không chặn worker vô hạn.

Khi ứng dụng shutdown, endpoint thường ngừng tạo poll task mới theo lifecycle. Tuy nhiên, task đã được submit vào executor có thể vẫn đang chờ hoặc đang chạy. Vì vậy:

- Chặn hoặc giảm nguồn message trước khi shutdown nếu cần drain.
- Chọn chính sách executor chờ task hoàn tất trong thời gian giới hạn.
- Đặt queue capacity hữu hạn và kiểm tra task bị từ chối.
- Không shutdown executor dùng chung khi chỉ muốn dừng một polling endpoint.
- Nếu cần bảo đảm không mất message, dựa vào durable broker/store và acknowledgment/transaction đúng cấu hình.

`setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(...)` trên `ThreadPoolTaskExecutor` có thể giúp chờ các task đã nhận trong khoảng thời gian xác định. Đây không phải bảo đảm vô hạn: nếu task không kết thúc trong thời hạn, ứng dụng vẫn phải xử lý tình huống shutdown theo chính sách đã chọn.

## 10. Đo lường và chẩn đoán concurrent polling

Khi bật executor, hãy đặt thread name prefix riêng, ví dụ `orders-poller-`, để phân biệt log của poller với worker khác. Log có cấu trúc nên có endpoint/component name, thread name, message ID, Correlation ID, thời gian nhận và thời gian xử lý.

Theo dõi các số liệu sau:

- Poll count và thời gian mỗi lần poll.
- Số message nhận được mỗi poll và số poll rỗng.
- Số worker active, pool size và executor queue size.
- Số task bị từ chối hoặc thời gian chờ trong executor.
- QueueChannel/broker backlog và tuổi của message cũ nhất.
- Throughput, processing latency, error rate và retry count.
- Database connection usage, lock wait và latency của dịch vụ downstream.

Các dấu hiệu phổ biến:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Executor queue tăng liên tục | Poller dispatch nhanh hơn worker xử lý; handler hoặc downstream là bottleneck |
| Worker luôn bận, throughput không tăng | Tắc nghẽn DB/remote service, lock contention hoặc batch quá lớn |
| Nhiều poll task chạy chồng lấn | Chu kỳ kích hoạt ngắn hơn thời gian xử lý; executor có nhiều worker |
| Message hoàn tất sai thứ tự | Concurrent polling hoặc downstream executor làm thay đổi thứ tự hoàn tất |
| RejectedExecutionException | Executor queue đầy và pool đã đạt giới hạn |
| CPU thấp nhưng backlog cao | Worker đang chờ I/O, connection pool hoặc lock |
| Lỗi tăng sau khi tăng pool size | Downstream bị quá tải hoặc giới hạn tài nguyên bị vượt |

Khi điều tra, hãy so sánh thời gian poll, thời gian chờ executor và thời gian xử lý handler. Nếu chỉ đo tổng thời gian từ trigger đến khi message hoàn tất, sẽ khó biết chậm ở khâu scheduling, queue task hay business processing.

## 11. Quy trình chọn cấu hình

1. **Xác định loại endpoint.** Là `SourcePollingChannelAdapter` hay `PollingConsumer`, nguồn có thread-safe không và channel có buffer không?
2. **Đo baseline.** Ghi throughput, latency, backlog, poll duration và thời gian xử lý handler khi chưa bật concurrency.
3. **Chọn batch size.** Đặt `maxMessagesPerPoll` hữu hạn nếu cần giới hạn thời gian một poll task và kích thước transaction.
4. **Chọn nhịp trigger.** Dùng fixed delay, fixed rate hoặc cron theo yêu cầu nghiệp vụ; tránh poll quá dày khi nguồn thường xuyên rỗng.
5. **Chọn executor.** Bắt đầu với pool nhỏ, queue hữu hạn và thread name riêng; chỉ tăng khi số liệu cho thấy worker là bottleneck.
6. **Kiểm tra thứ tự và idempotency.** Thử nghiệm message xử lý chậm, lỗi giữa batch, retry và redelivery.
7. **Đặt backpressure.** Kiểm tra capacity ở channel, executor, database và remote service.
8. **Quan sát sau triển khai.** Theo dõi throughput, latency, queue age, rejection và error rate trước khi tăng tải tiếp.

## 12. Checklist cấu hình Poller và TaskExecutor

- [ ] Phân biệt rõ vai trò `TaskScheduler` và `TaskExecutor`.
- [ ] Chọn fixed delay, fixed rate hoặc cron theo yêu cầu thực tế.
- [ ] Đặt `maxMessagesPerPoll` rõ ràng; tránh batch không giới hạn nếu nguồn luôn có message.
- [ ] Dùng executor có pool size và queue capacity hữu hạn.
- [ ] Xác minh MessageSource, handler và tài nguyên dùng chung thread-safe.
- [ ] Xác định yêu cầu thứ tự theo message, tenant hoặc partition.
- [ ] Kiểm tra transaction boundary khi một poll task xử lý nhiều message.
- [ ] Cấu hình error handling, retry và dead-letter cho task/message thất bại.
- [ ] Đo backlog, worker active, executor queue và rejected task.
- [ ] Xác minh shutdown không làm mất message hoặc bỏ lại task ngoài dự kiến.

Poller, TaskScheduler, TaskExecutor và `maxMessagesPerPoll` kiểm soát những phần khác nhau của consumer runtime. Khi tách được thời điểm kích hoạt, số message mỗi lượt và số worker chạy song song, ta có thể tăng throughput có kiểm soát, giữ an toàn cho nguồn dữ liệu và tránh biến backlog thành một hàng đợi task không giới hạn.

## Tài liệu tham khảo

- [Spring Integration Reference: Poller](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference: Java DSL](https://docs.spring.io/spring-integration/reference/dsl/java.html)
- [Spring Framework Reference: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework API: ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
