# Đo context switch, queue wait và handler time

Khi một Spring Integration flow chậm, chỉ nhìn tổng thời gian request thường không đủ để tìm ra nguyên nhân. Message có thể phải chờ trong queue, chờ một thread của executor, bị trì hoãn vì scheduler bận, hoặc thực sự mất nhiều thời gian trong handler. Hệ điều hành cũng có thể phải chuyển CPU liên tục giữa nhiều thread, nhưng **thread handoff trong ứng dụng không đồng nghĩa với một OS context switch**.

Ba nhóm số liệu cần tách riêng:

- **Context switch và thread scheduling** cho biết thread có thường xuyên bị chuyển trạng thái, chờ CPU hoặc bị block hay không.
- **Queue wait** đo thời gian message/task nằm chờ trước khi consumer hoặc worker bắt đầu xử lý.
- **Handler time** đo thời gian handler thực sự thực thi logic của nó.

Khi đo đúng từng khoảng, nhóm phát triển có thể xác định bottleneck nằm ở channel, executor, scheduler, handler hay dependency bên ngoài, rồi chọn thay đổi phù hợp thay vì tăng thread pool theo cảm tính.

## 1. Phân biệt các khoảng thời gian

Một message đi qua flow có thể trải qua nhiều giai đoạn:

~~~mermaid
flowchart LR
    A["Source tạo message"] --> B["Channel send"]
    B --> C["Queue wait"]
    C --> D["Consumer nhận"]
    D --> E["Handler bắt đầu"]
    E --> F["Handler kết thúc"]
    F --> G["Channel / endpoint tiếp theo"]
~~~

Các phép đo cơ bản:

| Chỉ số | Điểm bắt đầu | Điểm kết thúc | Ý nghĩa |
|---|---|---|---|
| Queue wait | Message được đưa vào queue | Consumer lấy message ra | Thời gian message nằm chờ trong queue |
| Executor queue wait | Task được submit | Worker bắt đầu chạy task | Thời gian task chờ worker thread |
| Handler time | Handler bắt đầu xử lý | Handler hoàn tất hoặc ném lỗi | Chi phí thực thi logic handler |
| End-to-end latency | Sự kiện bắt đầu tại source | Kết quả cuối cùng hoàn tất | Tổng thời gian mà nghiệp vụ phải chờ |
| Scheduler lateness | Thời điểm trigger dự kiến | Thời điểm task thực sự bắt đầu | Độ trễ do scheduler hoặc tải hệ thống |
| OS context switch | Một thread nhường CPU hoặc bị preempt | Một thread khác được chạy | Hoạt động chuyển CPU giữa các thread của hệ điều hành |

Không cộng các chỉ số một cách máy móc nếu chúng đo các đoạn thời gian chồng lấn. Ví dụ, một handler có thể chạy đồng bộ bên trong polling task; thời gian handler lúc đó cũng nằm trong thời gian thực thi polling task. Cần xác định ranh giới đo trước khi xây dựng dashboard.

## 2. Thread handoff không phải OS context switch

Trong Spring Integration, message có thể đi qua nhiều execution context:

- `DirectChannel` thường gọi handler ngay trong thread gửi message.
- `QueueChannel` giữ message cho đến khi consumer nhận, thường qua một polling endpoint.
- `ExecutorChannel` chuyển việc dispatch đến `TaskExecutor`.
- `PublishSubscribeChannel` có thể gọi subscriber trong thread gửi hoặc dispatch qua executor tùy cấu hình.
- Poller được `TaskScheduler` kích hoạt; handler đồng bộ phía sau có thể tiếp tục chạy trên thread của polling task.

Việc chuyển từ thread A sang thread B là **thread handoff** ở cấp ứng dụng. Khi B được chạy, hệ điều hành có thể cần context switch, nhưng không phải mỗi lần handoff đều tương ứng chính xác một context switch có thể quy cho message đó. Thread B có thể đã chạy trên CPU, đang ở trạng thái runnable, hoặc bị trì hoãn bởi các thread khác.

OS context switch là hoạt động của scheduler hệ điều hành. Một thread có thể bị chuyển ra vì hết time slice, chờ I/O, chờ lock hoặc bị preempt. Context switch cao có thể là dấu hiệu của quá nhiều thread hoặc workload blocking, nhưng tự nó không chứng minh Spring Integration đang có vấn đề.

Cần kết hợp:

- OS context switches và CPU migrations.
- Thread count, runnable/blocked/waiting state.
- CPU usage và CPU throttling nếu chạy trong container.
- Executor active count, queue size và rejected task.
- Queue wait, handler duration và end-to-end latency.

## 3. Channel quyết định queue wait có tồn tại hay không

Không phải mọi channel đều có queue wait giống nhau.

| Channel | Thread xử lý điển hình | Có queue wait? | Điều cần đo |
|---|---|---|---|
| `DirectChannel` | Thread gọi `send()` | Không có queue nội bộ | Thời gian send và handler time |
| `PublishSubscribeChannel` không executor | Thread gửi message gọi các subscriber | Không có queue nội bộ | Tổng thời gian dispatch và từng subscriber |
| `PublishSubscribeChannel` có executor | Worker do executor cấp | Có thể có executor queue wait | Task submit-to-start và handler time |
| `QueueChannel` | Polling consumer nhận message | Có queue wait | Enqueue-to-dequeue và backlog |
| `PriorityChannel` | Consumer lấy theo thứ tự ưu tiên | Có queue wait | Queue wait theo priority và backlog |
| `ExecutorChannel` | Worker do `TaskExecutor` cấp | Có thể có executor queue wait | Executor queue wait và handler time |

`ExecutorChannel` không tự bảo đảm một hàng đợi nghiệp vụ có persistence. Khả năng task phải chờ phụ thuộc `TaskExecutor` được cấu hình. Nếu dùng executor thực thi trực tiếp, queue wait gần như không có; nếu dùng thread pool có hàng đợi, task có thể chờ worker rảnh.

`QueueChannel` có thể có capacity hữu hạn. Khi queue đầy, thao tác gửi có thể chờ đến timeout hoặc thất bại tùy cấu hình và cách gọi. Cần đo cả thời gian producer bị chặn khi gửi, vì đó là một dạng backpressure ở ranh giới channel.

## 4. Đo queue wait trong QueueChannel

Queue wait được tính bằng:

\[
T_{queue}=T_{dequeue}-T_{enqueue}
\]

Để đo chính xác trong cùng JVM, có thể ghi `System.nanoTime()` khi message đi qua `preSend`, sau đó lấy lại thời điểm trong `postReceive`. Đồng hồ monotonic phù hợp để đo elapsed time vì không bị thay đổi bởi chỉnh đồng hồ hệ thống.

Ví dụ một `ChannelInterceptor` chuyên đo queue wait:

~~~java
final class QueueWaitInterceptor implements ChannelInterceptor {

    private static final String ENQUEUED_AT =
            "diag.enqueuedAtNanos";

    private final MeterRegistry registry;

    QueueWaitInterceptor(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Message<?> preSend(
            Message<?> message, MessageChannel channel) {

        return MessageBuilder.fromMessage(message)
                .setHeader(ENQUEUED_AT, System.nanoTime())
                .build();
    }

    @Override
    public Message<?> postReceive(
            Message<?> message, MessageChannel channel) {

        if (message == null) {
            return null;
        }

        Object value = message.getHeaders().get(ENQUEUED_AT);
        if (value instanceof Long enqueuedAt) {
            long elapsed = System.nanoTime() - enqueuedAt;

            Timer.builder("integration.channel.queue.wait")
                    .tag("channel", "orders.queue")
                    .register(registry)
                    .record(elapsed, TimeUnit.NANOSECONDS);
        }

        return MessageBuilder.fromMessage(message)
                .removeHeader(ENQUEUED_AT)
                .build();
    }
}
~~~

Đăng ký interceptor cho đúng channel cần đo:

~~~java
@Bean
@GlobalChannelInterceptor(patterns = "orders.queue")
QueueWaitInterceptor queueWaitInterceptor(MeterRegistry registry) {
    return new QueueWaitInterceptor(registry);
}
~~~

Trong ví dụ, interceptor đóng dấu thời gian trước khi gửi vào channel và đo khoảng thời gian khi consumer nhận message. Header đo đạc được gỡ bỏ sau khi đo để không rò rỉ sang các endpoint hoặc adapter tiếp theo.

Đây là phép đo gần đúng từ trước lời gọi enqueue đến lúc dequeue. `preSend` chạy trước khi channel thực sự đưa message vào queue; nếu `QueueChannel` bounded đã đầy và producer phải chờ capacity, khoảng đo sẽ bao gồm cả thời gian producer bị block khi gửi. Hãy đo riêng thời gian `send()` hoặc instrument sâu hơn ở queue implementation nếu cần queue residence time thuần. Với queue còn capacity và send không block, phần chênh này thường nhỏ.

Chỉ áp dụng interceptor này cho channel pollable cần đo. Nếu gắn vào mọi channel, phép đo sẽ không còn là queue wait thuần túy và có thể tạo overhead không cần thiết. Cần kiểm tra phiên bản Spring Integration đang dùng và bảo đảm interceptor được áp dụng đúng channel bean.

### Giới hạn của phép đo bằng nanoTime

`System.nanoTime()` chỉ có ý nghĩa so sánh trong cùng một tiến trình/JVM. Không serialize giá trị này vào message để gửi qua broker hoặc lưu bền vững rồi trừ ở tiến trình khác; mốc nanoTime giữa hai JVM không cùng hệ quy chiếu.

Với message qua broker hoặc persistence:

- Dùng timestamp được ghi ở nơi enqueue và timestamp ở nơi consume nếu cần đo xuyên tiến trình.
- Đồng bộ clock giữa các máy bằng cơ chế thời gian của hạ tầng.
- Ưu tiên distributed tracing hoặc broker-native metrics nếu cần đo chính xác thời gian chờ trong broker.
- Tách thời gian ở broker, thời gian truyền mạng và thời gian chờ trong consumer local.

Nếu dùng wall-clock `Instant`, cần nhận biết sai số clock và khả năng đồng hồ bị điều chỉnh. Với duration nội bộ JVM, monotonic clock vẫn là lựa chọn phù hợp hơn.

## 5. Đo queue wait của TaskExecutor

Đối với `ExecutorChannel` hoặc endpoint dispatch qua thread pool, message có thể đã được submit nhưng worker chưa bắt đầu chạy. Đây là **executor queue wait**, không phải `QueueChannel` wait.

Spring `TaskDecorator` có thể bọc task tại thời điểm submit và đo khi task bắt đầu thực thi:

~~~java
@Bean
ThreadPoolTaskExecutor integrationExecutor(MeterRegistry registry) {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(16);
    executor.setQueueCapacity(500);
    executor.setThreadNamePrefix("integration-worker-");

    executor.setTaskDecorator(task -> {
        long submittedAt = System.nanoTime();

        return () -> {
            long wait = System.nanoTime() - submittedAt;

            Timer.builder("integration.executor.queue.wait")
                    .tag("executor", "integration-worker")
                    .register(registry)
                    .record(wait, TimeUnit.NANOSECONDS);

            task.run();
        };
    });

    return executor;
}
~~~

Gắn executor này vào `ExecutorChannel` hoặc endpoint cần đo. `TaskDecorator` ghi thời điểm submit và tính thời gian khi worker bắt đầu. Thời gian này gần với thời gian chờ worker, bao gồm cả phần chờ trong hàng đợi executor và độ trễ scheduling của worker.

Để phép đo có ý nghĩa, cần phân biệt task bị từ chối với task được nhận nhưng phải chờ. Nếu executor từ chối task khi queue đầy, task không có thời điểm bắt đầu để ghi queue wait; cần đếm riêng rejected execution.

Không phải mọi `TaskExecutor` đều có queue. Với executor chạy trực tiếp trên caller thread, task có thể bắt đầu ngay và queue wait gần bằng zero. Với virtual-thread-per-task executor, khái niệm queue wait của thread pool có thể không còn phù hợp; hãy đo thời gian chờ tài nguyên downstream và thời gian scheduling thực tế thay vì giả định có một worker queue.

## 6. Đo handler time

Handler time được tính từ lúc logic handler bắt đầu đến lúc kết thúc:

\[
T_{handler}=T_{finish}-T_{start}
\]

Có thể dùng Micrometer `Timer` để ghi duration và phân loại kết quả thành success/error.

~~~java
@Service
class OrderHandler {

    private final MeterRegistry registry;
    private final OrderRepository repository;

    OrderHandler(
            MeterRegistry registry,
            OrderRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    public void process(Order order) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            repository.saveProcessed(order);
        }
        catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        }
        finally {
            sample.stop(Timer.builder("integration.handler.duration")
                    .tag("handler", "process-order")
                    .tag("outcome", outcome)
                    .register(registry));
        }
    }
}
~~~

Timer có thể cung cấp count, total time, max và percentile/histogram tùy cấu hình registry. Dùng tag có cardinality thấp như tên handler, flow hoặc outcome. Không dùng `orderId`, `correlationId`, user ID hoặc payload value làm tag vì số lượng time series sẽ tăng không giới hạn.

### Handler time không phải end-to-end latency

Một handler có thể mất 5 ms nhưng message đã chờ 2 giây trong queue. Ngược lại, handler có thể chạy 500 ms nhưng message được dispatch ngay và SLA vẫn đáp ứng.

Vì vậy dashboard nên đặt các chỉ số cạnh nhau:

- Queue wait P50/P95/P99.
- Executor queue wait P50/P95/P99.
- Handler duration P50/P95/P99.
- Message throughput và error rate.
- Queue depth và executor active/queued/rejected.
- End-to-end latency của nghiệp vụ.

Nếu handler gọi database hoặc HTTP client, có thể đo riêng dependency duration. Khi handler time tăng, phép đo này giúp xác định thời gian nằm trong code, lock, connection pool hay remote call.

## 7. Đo scheduler lateness

Poller được kích hoạt bởi `TaskScheduler`. Nếu task bắt đầu muộn hơn thời điểm trigger dự kiến, đó là scheduler lateness.

\[
T_{lateness}=T_{actualStart}-T_{scheduledStart}
\]

Có thể đo bằng cách bọc `Runnable` hoặc dùng instrumentation tại scheduler abstraction. Với Spring Integration, hãy kết hợp thời điểm poll thực tế, thời gian source `receive()` và thời gian gửi message. Nếu thời điểm kích hoạt không được expose trực tiếp ở abstraction đang dùng, có thể ghi timestamp ở đầu polling task bằng advice hoặc wrapper phù hợp với phiên bản.

Không nên lấy thời gian từ lúc message được tạo làm scheduler lateness. Message có thể được tạo sau nhiều thao tác I/O trong source; hai khoảng này đo hai hiện tượng khác nhau.

## 8. Đo OS context switch và CPU scheduling

Micrometer metrics của Spring Integration thường không tự cung cấp một bộ đếm context switch chính xác cho từng message. Đây là số liệu thuộc hệ điều hành, cần quan sát từ OS hoặc công cụ profiling.

### Trên Windows

Có thể dùng Performance Monitor (PerfMon) để theo dõi counter ~System\Context Switches/sec~. Counter này phản ánh hoạt động context switch của toàn hệ thống, không tự phân tách theo từng message hoặc từng Spring Integration channel.

Để điều tra sâu hơn, dùng Windows Performance Recorder và Windows Performance Analyzer với trace CPU scheduling/context switch. Công cụ ETW giúp xem thread nào bị preempt, thread nào chờ CPU, và thời gian thread ở trạng thái ready hoặc waiting.

### Trên Linux

Một số lệnh thường dùng:

~~~bash
pidstat -w -p <java-pid> 1
~~~

Lệnh này hiển thị voluntary và non-voluntary context switches theo process/thread tùy phiên bản sysstat.

~~~bash
perf stat -e context-switches,cpu-migrations -p <java-pid>
~~~

Lệnh này đếm context switch và CPU migration trong khoảng theo dõi của process. Cần quyền hệ thống phù hợp để dùng perf.

~~~bash
vmstat 1
~~~

`vmstat` cho biết số context switch toàn hệ thống theo chu kỳ cùng các chỉ số CPU và runnable process. Đây là góc nhìn tổng thể, không thay thế phân tích theo process.

### Đọc số liệu context switch đúng cách

- **Voluntary context switch** thường xảy ra khi thread chủ động chờ I/O, lock, condition hoặc sleep.
- **Involuntary context switch** thường xảy ra khi thread bị preempt hoặc hết time slice.
- **CPU migration** là thread chuyển sang CPU core khác; nó không đồng nghĩa với context switch.
- Context switch tăng có thể do nhiều thread, blocking, lock contention hoặc workload hệ thống khác.

Không có một ngưỡng context switch/sec phù hợp cho mọi ứng dụng. Hãy so sánh với baseline khi tải tương đương, CPU usage, latency và throughput. Nếu context switch tăng nhưng latency và throughput ổn định, chưa chắc cần thay đổi. Nếu context switch tăng cùng queue wait, CPU saturation và handler latency, cần tìm thread contention hoặc pool sizing không phù hợp.

## 9. Dùng Java Flight Recorder và thread dump

Java Flight Recorder (JFR) hữu ích để tìm lý do thread không tiến triển. Các event cần xem tùy workload:

- `jdk.ThreadPark`: thread park khi chờ synchronizer hoặc executor.
- `jdk.JavaMonitorEnter`: thời gian chờ monitor lock.
- `jdk.JavaMonitorWait`: thời gian chờ monitor.
- `jdk.ThreadSleep`: thời gian thread ngủ.
- `jdk.ExecutionSample`: sample stack của thread đang thực thi.
- `jdk.ThreadCPULoad`: tải CPU theo thread nếu runtime/version hỗ trợ event này.

JFR giúp thấy thread đang chạy code, chờ lock hoặc park. Nó không thay thế bộ đếm OS context switch; dùng OS trace nếu cần số liệu context switch chính xác.

Thread dump là ảnh chụp trạng thái thread tại một thời điểm. Có thể dùng:

~~~bash
jcmd <java-pid> Thread.print
~~~

Nên chụp nhiều thread dump cách nhau một khoảng ngắn. Một thread ở `BLOCKED` liên tục có thể đang tranh chấp monitor; `WAITING` hoặc `TIMED_WAITING` có thể đang chờ queue, condition hoặc I/O. `RUNNABLE` không có nghĩa chắc chắn thread đang dùng CPU; nó có thể runnable nhưng chưa được scheduler cấp CPU.

Đối chiếu tên thread với prefix đã cấu hình:

- `integration-scheduler-`: scheduler thread.
- `integration-worker-`: worker executor.
- Thread của HTTP client, JDBC pool hoặc broker client: dependency bên ngoài.

Tên thread là tín hiệu giúp khoanh vùng; hãy xem stack trace và trạng thái thực tế trước khi kết luận.

## 10. Đọc queue depth và executor saturation

Queue wait cao thường đi cùng queue depth hoặc executor saturation, nhưng hai chỉ số không thay thế nhau.

| Chỉ số | Câu hỏi trả lời |
|---|---|
| Queue depth | Có bao nhiêu message đang chờ? |
| Queue wait | Một message đã chờ bao lâu trước khi được nhận? |
| Arrival rate | Message đến với tốc độ bao nhiêu? |
| Completion rate | Consumer hoàn thành message với tốc độ bao nhiêu? |
| Executor active count | Bao nhiêu worker đang chạy task? |
| Executor queue size | Bao nhiêu task đang chờ worker? |
| Rejected count | Có bao nhiêu task không được executor chấp nhận? |

Nếu arrival rate liên tục lớn hơn completion rate, queue depth sẽ tăng. Khi queue tăng, queue wait thường cũng tăng. Nếu queue depth nhỏ nhưng queue wait cao, có thể consumer bị dừng lâu, scheduler bị trễ hoặc queue chỉ có một consumer xử lý rất chậm.

Với `ThreadPoolTaskExecutor`, có thể quan sát pool size, active count và queue size từ executor implementation hoặc Micrometer executor instrumentation. Với `QueueChannel`, cần theo dõi queue capacity và số message hiện có bằng cơ chế phù hợp với implementation; không phải channel nào cũng expose cùng một bộ metrics.

## 11. Thiết kế metrics và tags

Một bộ metric hữu ích nên có tên ổn định và tag giới hạn:

| Metric | Tags gợi ý | Dùng để |
|---|---|---|
| `integration.channel.queue.wait` | `channel`, `flow` | Đo thời gian message chờ trong channel |
| `integration.executor.queue.wait` | `executor`, `flow` | Đo thời gian task chờ worker |
| `integration.handler.duration` | `handler`, `outcome` | Đo thời gian thực thi handler |
| `integration.poll.duration` | `endpoint`, `outcome` | Đo thời gian một chu kỳ poll |
| `integration.message.processed` | `flow`, `outcome` | Đếm số message xử lý thành công/thất bại |
| `integration.message.backlog` | `channel` | Theo dõi số message chờ |
| `integration.executor.rejected` | `executor` | Phát hiện task bị từ chối |

Các metric này là quy ước đặt tên minh họa cho ứng dụng; không mặc định rằng Spring Integration tự đăng ký tất cả tên trên. Hãy dùng Micrometer Timer, Counter và Gauge hoặc observation instrumentation của phiên bản đang chạy.

Giữ tag values ổn định. Tránh đưa các giá trị có cardinality cao như message ID, order ID, correlation ID, URL đầy đủ hoặc exception message vào tag. Những giá trị này phù hợp hơn trong trace/log có kiểm soát.

## 12. Observation và tracing trong Spring Integration

Spring Integration có tích hợp Micrometer Observation ở các phiên bản hỗ trợ. Observation có thể liên kết hoạt động gửi/nhận message với tracing và metrics khi ứng dụng cấu hình `ObservationRegistry` và integration management tương ứng.

Khi bật instrumentation:

- Chọn component cần theo dõi thay vì instrument mọi thành phần mà không cân nhắc overhead.
- Dùng trace context để nối các bước trong flow và các lời gọi ra ngoài.
- Đặt tên span/observation có ý nghĩa như channel, handler hoặc adapter.
- Kiểm tra context propagation khi message chuyển qua executor hoặc broker.
- Không ghi payload nhạy cảm vào span attribute.

Tracing cho biết một message đi qua những span nào và span nào chậm. Metrics cho biết xu hướng và phân phối theo thời gian. OS profiling cho biết thread và CPU đang hoạt động ra sao. Ba góc nhìn bổ sung cho nhau.

## 13. Phân tích một số mẫu bottleneck

| Quan sát | Khả năng nguyên nhân | Bước kiểm tra tiếp theo |
|---|---|---|
| Queue wait tăng, handler time ổn định | Consumer thiếu concurrency hoặc queue backlog tăng | So sánh arrival/completion rate, active consumer và queue capacity |
| Executor queue wait tăng, CPU cao | Pool thiếu worker hoặc task CPU-bound | Profile CPU, kiểm tra pool size và thời gian task |
| Executor queue wait tăng, CPU thấp | Worker bị block I/O hoặc chờ lock | Dùng JFR và thread dump để tìm wait/park |
| Handler time tăng, queue wait thấp | Logic handler hoặc dependency chậm | Đo riêng DB/API/lock trong handler |
| Context switch tăng, throughput không tăng | Quá nhiều thread hoặc contention | Xem voluntary/involuntary switch, runnable threads và lock |
| Scheduler lateness tăng | Scheduler pool bị chiếm hoặc task blocking | Kiểm tra scheduler thread dump và duration từng poller |
| Queue depth thấp nhưng end-to-end latency cao | Chậm trước enqueue hoặc trong handler/downstream | Đặt mốc thời gian tại source, handler và completion |
| CPU thấp nhưng queue wait cao | Consumer không được kích hoạt, thread bị block hoặc endpoint stopped | Kiểm tra lifecycle, poller schedule và consumer state |

Không nên tăng concurrency trước khi biết bottleneck. Nếu database connection pool chỉ có 10 connection, tăng executor lên 100 thread có thể tạo thêm 90 thread chờ connection và làm context switch tăng. Nếu handler CPU-bound, thêm thread vượt số core có thể giảm hiệu quả vì contention và scheduling overhead.

## 14. Quy trình đo trong một lần điều tra

Một quy trình điều tra có thể thực hiện theo thứ tự:

1. **Xác định đường đi**: ghi lại source, channel, endpoint, executor và handler của message.
2. **Đặt mốc thời gian**: enqueue/dequeue, task submit/start, handler start/end và completion.
3. **Đo baseline**: thu thập P50/P95/P99, throughput, error rate, queue depth và CPU ở tải bình thường.
4. **Tái hiện tải**: dùng workload gần production và giữ nguyên kích thước message, concurrency, dependency.
5. **Khoanh vùng**: xác định khoảng thời gian chiếm phần lớn end-to-end latency.
6. **Đối chiếu thread**: dùng JFR/thread dump và OS context switch khi cần.
7. **Thay đổi một yếu tố**: ví dụ batch size, pool size, channel hoặc timeout.
8. **Đo lại cùng điều kiện**: so sánh latency, throughput, CPU, context switch và error rate.
9. **Kiểm tra tải đỉnh**: xác nhận queue không tăng vô hạn và executor không liên tục reject task.

Không kết luận từ một lần đo ngắn. Cần đủ thời gian để thấy chu kỳ polling, burst traffic và biến động dependency.

## 15. Kiểm thử instrumentation

Instrumentation cần được kiểm tra để tránh tạo số liệu sai:

- Queue wait phải bắt đầu trước enqueue và kết thúc sau dequeue.
- Executor wait phải bắt đầu tại submit và kết thúc khi worker bắt đầu chạy.
- Handler time phải kết thúc cả trong trường hợp exception.
- Header đo nội bộ phải được xóa trước khi message qua ranh giới persistence/broker.
- Timer phải có tag cardinality thấp.
- Message bị reject hoặc bị drop phải có counter riêng; không để chúng biến mất khỏi thống kê.
- Instrumentation không được thay đổi payload, routing hoặc semantics của channel.
- Đo overhead của interceptor/decorator trong tải cao.

Dùng test clock hoặc đồng hồ monotonic giả lập nếu framework test hỗ trợ. Với interceptor dựa trên `nanoTime`, có thể kiểm thử rằng timestamp được thêm trước send, duration được ghi sau receive và header chẩn đoán bị loại khỏi message trả về.

## 16. Checklist chẩn đoán production

Khi flow chậm hoặc throughput giảm, hãy trả lời:

- Message đi qua channel nào? Channel đó có buffer hay dispatch đồng bộ?
- Có bao nhiêu thread handoff giữa source và handler?
- Queue wait và executor queue wait được đo ở đúng ranh giới chưa?
- Handler time có tách riêng dependency I/O và lock wait không?
- P50/P95/P99 có cho thấy tail latency tăng không?
- Queue depth và completion rate có cho thấy backlog đang tăng không?
- Executor có active thread cao, queue lớn hoặc rejected task không?
- Scheduler có bị blocking hoặc trễ trigger không?
- OS context switch tăng do workload của ứng dụng hay do process khác?
- JFR/thread dump có cho thấy lock contention, park hoặc blocking I/O không?
- Metrics có tag cardinality thấp và không chứa dữ liệu nhạy cảm không?
- Sau khi thay đổi, throughput và latency có cải thiện trong cùng điều kiện tải không?

Đo queue wait, handler time và context switch ở đúng tầng giúp phân biệt message đang chờ được xử lý với message đang được xử lý chậm. Đây là nền tảng để điều chỉnh channel, poller, executor và số thread có căn cứ.

## Tài liệu tham khảo

Các tài liệu chính thức dưới đây mô tả các API và công cụ theo phiên bản. Hãy đối chiếu với Spring Integration, Spring Framework, Micrometer và JDK mà ứng dụng đang sử dụng.

- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html)
- [Spring Integration — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskExecutor and TaskDecorator](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [JDK Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api.html)

