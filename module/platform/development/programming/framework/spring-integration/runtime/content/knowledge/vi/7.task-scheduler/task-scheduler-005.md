# Scheduled task bị trễ khi công việc chạy lâu

Trong Spring Integration, poller và các tác vụ định kỳ dựa vào scheduler để kích hoạt công việc theo lịch. Nếu một tác vụ chiếm scheduler thread quá lâu, những lần chạy tiếp theo hoặc những tác vụ khác dùng chung scheduler có thể bị trễ. Đây là vấn đề về năng lực thực thi và cách phân bổ thread, không nhất thiết là biểu thức trigger sai.

Muốn xử lý đúng, cần tìm xem phần nào đang chiếm thread: polling task, lời gọi I/O đồng bộ, handler downstream hay một tác vụ định kỳ khác. Sau đó mới quyết định tăng scheduler pool, tách poller sang executor, rút ngắn công việc, điều chỉnh trigger hoặc giới hạn concurrency. Tăng thread mà không hiểu điểm nghẽn có thể chỉ chuyển hàng đợi từ scheduler sang executor hoặc làm downstream quá tải hơn.

Sau bài này, bạn có thể:

- Giải thích vì sao tác vụ chạy lâu làm trễ lịch của chính nó và các tác vụ khác.
- Phân biệt hành vi của `fixedRate`, `fixedDelay` và cron khi task vượt thời gian dự kiến.
- Nhận biết scheduler thread, poller task thread và downstream worker thread.
- Cấu hình pool scheduler và executor phù hợp với tải.
- Kiểm soát concurrency, thứ tự xử lý, transaction và shutdown khi tách thread.
- Đo và chẩn đoán độ trễ thay vì chỉ tăng số thread.

## 1. Vì sao scheduled task bị trễ?

Scheduler nhận trách nhiệm kích hoạt tác vụ khi trigger đến hạn. Nếu phần thân tác vụ chạy đồng bộ trên scheduler thread và mất nhiều thời gian, thread đó không thể đồng thời thực thi một scheduled task khác. Khi scheduler có ít thread, một công việc dài có thể làm chậm cả nhóm công việc dùng chung scheduler.

Ví dụ một scheduler có một worker thread:

```text
Scheduler pool: 1 thread

Thread-1:  [Poller A -------- xử lý 8 giây --------]
          lịch B đến hạn ^       lịch C đến hạn ^
                         nhưng chưa có thread rảnh

Sau khi A kết thúc:
Thread-1:                                  [Task B] [Task C]
```

Tác vụ B và C đã đến hạn nhưng phải chờ Thread-1 rảnh. Biểu thức lịch của chúng vẫn đúng; độ trễ xuất hiện ở giai đoạn thực thi.

Một số nguyên nhân phổ biến:

- Handler gọi API bên ngoài hoặc truy vấn database đồng bộ và chờ lâu.
- Polling task lấy một batch lớn, mỗi message mất nhiều thời gian xử lý.
- Nhiều poller hoặc `@Scheduled` task chia sẻ cùng một scheduler có pool nhỏ.
- Scheduler thread bị block bởi lock, I/O, transaction hoặc chờ tài nguyên.
- Task được giao sang executor nhưng executor đã đầy, khiến công việc nằm trong hàng đợi.
- Hệ thống chạy nhiều instance và mỗi instance cùng thực hiện một tác vụ nghiệp vụ mà không có cơ chế phối hợp.

Trước khi sửa, hãy xác định độ trễ nằm ở thời điểm scheduler kích hoạt, thời điểm task bắt đầu thực thi hay thời điểm handler hoàn tất. Ba mốc này cho biết cần điều chỉnh scheduler, executor hay chính công việc.

## 2. Phân biệt scheduler thread và thread xử lý message

Trong một polling flow, ít nhất ba vai trò thread có thể xuất hiện:

```text
Trigger / TaskScheduler
        |
        v
Scheduler thread
        |
        | kích hoạt polling task
        v
Poller task
        |
        | receive message và gọi downstream
        v
Message handler
        |
        +---- có thể chạy cùng thread poller
        |
        +---- hoặc được chuyển sang executor/channel khác
```

**Scheduler thread** chịu trách nhiệm thực thi scheduled callback. Với cấu hình polling đơn giản, polling task và handler có thể chạy ngay trên thread này. Khi đó handler chậm sẽ chiếm scheduler thread.

**Poller task executor** có thể tách phần công việc poll khỏi thread lập lịch. Scheduler kích hoạt theo trigger rồi công việc được giao cho executor. Cách tách này giúp scheduler quay lại phục vụ lịch, nhưng executor vẫn có giới hạn thread và hàng đợi riêng.

**Downstream executor** như executor của `ExecutorChannel` có thể tách tiếp phần xử lý handler. Đây là một ranh giới bất đồng bộ khác. Khi thêm nhiều tầng executor, cần hiểu message đang nằm ở queue nào và lỗi được chuyển đến đâu.

Không phải mọi endpoint đều dùng poller. Event-driven consumer trên `DirectChannel` nhận message khi producer gửi; nó không có lịch polling. Tuy nhiên, handler đồng bộ trên thread gửi vẫn có thể làm chậm producer hoặc upstream flow. Phân biệt đúng loại endpoint giúp tránh điều chỉnh scheduler cho một vấn đề không liên quan đến scheduler.

## 3. fixedRate và fixedDelay khi task chạy lâu

Hai trigger này phản ứng khác nhau khi polling task mất nhiều thời gian.

### 3.1. fixedDelay

`fixedDelay` tính khoảng nghỉ sau khi lần thực thi trước hoàn tất. Nếu task mất 8 giây và delay là 2 giây, lần tiếp theo được lên lịch sau khoảng 10 giây tính từ thời điểm bắt đầu lần trước (bỏ qua sai số scheduler).

```text
Task A: [--------- 8s ---------] nghỉ 2s [Task B]
        0s                     8s        10s
```

Vì vậy, fixedDelay không cố giữ nhịp bắt đầu cố định khi công việc lâu. Nó giữ khoảng nghỉ sau mỗi lần chạy, phù hợp khi muốn giảm áp lực lên nguồn dữ liệu hoặc downstream.

### 3.2. fixedRate

`fixedRate` đặt các thời điểm bắt đầu dự kiến theo chu kỳ. Nếu chu kỳ là 2 giây nhưng một lần chạy mất 8 giây, task không thể tự chạy chồng lấn lên chính nó khi được lập lịch như một periodic task thông thường của `ScheduledExecutorService`. Lần chạy kế tiếp bị trễ và có thể bắt đầu ngay sau khi lần trước kết thúc để bắt kịp lịch.

```text
Mốc dự kiến: 0s  2s  4s  6s  8s  10s
Task thực tế: [--------- 8s ---------][--------- ...
             0s                    ~8s
```

Điều này có thể khiến task gần như chạy liên tục, không có khoảng nghỉ. Nếu công việc liên tục vượt chu kỳ, tăng scheduler pool không làm cùng một periodic task tự chạy đồng thời; pool lớn chủ yếu giúp các scheduled task độc lập khác có thread thực thi.

### 3.3. Cron

Cron biểu diễn các mốc trên đồng hồ lịch, ví dụ mỗi phút hoặc lúc 02:00 mỗi ngày. Nếu một lần chạy kéo dài qua mốc tiếp theo, lần kích hoạt kế tiếp có thể bị trễ hoặc bị bỏ qua tùy semantics của trigger và scheduler đang dùng. Không nên giả định mọi mốc cron bị lỡ đều tự động được chạy bù.

Với Spring `CronTrigger`, cần hiểu chế độ thực thi được chọn và phiên bản Spring. Một số phiên bản cung cấp lựa chọn lenient execution (tính lần tiếp theo từ thời điểm hoàn tất, có thể bỏ qua mốc bị lỡ) và fixed execution (bám lịch dự kiến để không bỏ qua các mốc). Hãy chọn theo yêu cầu nghiệp vụ và kiểm tra hành vi cụ thể trước khi dựa vào catch-up.

| Trigger | Khi task lâu hơn chu kỳ/mốc |
|---|---|
| `fixedDelay` | Đợi đủ delay sau khi task kết thúc; nhịp bắt đầu tự giãn. |
| `fixedRate` | Không chồng lấn cùng một periodic task; lần sau có thể chạy trễ hoặc sát ngay sau lần trước. |
| `cron` | Xử lý mốc bị lỡ tùy chế độ trigger; có thể bỏ qua hoặc tiếp tục bám lịch. |

## 4. Scheduler pool size và phạm vi ảnh hưởng

`ThreadPoolTaskScheduler` sử dụng thread pool để chạy scheduled task. Khi pool chỉ có một thread, một task block có thể làm trễ các task khác cùng scheduler. Tăng `poolSize` cho phép nhiều task độc lập chạy song song, miễn là chúng không bị giới hạn bởi cùng tài nguyên bên ngoài.

Ví dụ khai báo scheduler có bốn worker:

```java
@Configuration
class SchedulingConfiguration {

    @Bean(name = "taskScheduler")
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(4);
        scheduler.setThreadNamePrefix("integration-scheduler-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        return scheduler;
    }
}
```

Tên bean scheduler cần khớp với cách cấu hình và cơ chế discovery của ứng dụng. Spring Integration thường tìm scheduler theo quy ước bean name của integration context; Spring Boot hoặc cấu hình riêng có thể cung cấp scheduler khác. Hãy xác minh scheduler nào thực sự đang được poller sử dụng trước khi thay pool size.

Tăng pool size có thể giúp khi nhiều task độc lập đang chờ nhau vì thiếu scheduler thread. Nhưng nó không sửa được một task riêng lẻ chạy quá lâu. Một periodic task cụ thể vẫn không tự chồng lấn với chính nó chỉ vì pool lớn hơn.

Ngoài ra, tăng pool size có thể làm database/API nhận nhiều request đồng thời hơn. Nếu downstream có giới hạn connection hoặc rate limit, việc tăng thread có thể chuyển độ trễ thành timeout, lock contention hoặc lỗi từ chối. Hãy tăng dần và theo dõi cả scheduler lẫn downstream.

## 5. Tách công việc poller sang TaskExecutor

Với polling endpoint, có thể cấu hình executor cho poller để scheduled callback không phải trực tiếp thực hiện toàn bộ công việc nhận và xử lý message. Ví dụ Java DSL:

```java
@Bean
ThreadPoolTaskExecutor pollerExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("poller-worker-");
    return executor;
}

@Bean
IntegrationFlow pollOrders(OrderHandler handler,
                            ThreadPoolTaskExecutor pollerExecutor) {
    return IntegrationFlow.from(
            "ordersQueue",
            endpoint -> endpoint.poller(
                    Pollers.fixedDelay(1_000)
                            .taskExecutor(pollerExecutor)
                            .maxMessagesPerPoll(10)))
            .handle(handler, "handle")
            .get();
}
```

Đây là cách tách thread cho polling endpoint khi API builder của phiên bản Spring Integration đang dùng hỗ trợ `taskExecutor` trên poller. Scheduler kích hoạt công việc theo trigger; executor tiếp nhận phần công việc poll. Cần đo cả thời gian submit lẫn thời gian xử lý thực tế, vì task có thể chờ trong executor queue sau khi trigger đã đến hạn.

Khi poller task được giao bất đồng bộ, lịch có thể tiếp tục kích hoạt trong khi task trước vẫn đang chờ hoặc đang chạy, tùy implementation và cấu hình. Với executor nhiều thread, phải kiểm tra nguy cơ nhiều lần poll cùng endpoint chạy đồng thời. Điều này có thể làm thay đổi thứ tự message, tăng tải downstream và ảnh hưởng transaction. Nếu nghiệp vụ yêu cầu tuần tự, hãy giới hạn concurrency phù hợp, dùng executor đơn luồng hoặc cơ chế khóa/serialization rõ ràng.

Tách executor không đồng nghĩa tạo thêm năng lực vô hạn. Khi executor queue đầy, task có thể chờ lâu hoặc bị từ chối theo rejection policy. Khi đó scheduler không còn là điểm nghẽn đầu tiên; backlog nằm ở executor.

## 6. Giới hạn công việc mỗi lần poll

`maxMessagesPerPoll` giới hạn số message mà một polling task có thể lấy trong một chu kỳ. Nếu mỗi message xử lý mất 500 ms và một poll lấy 100 message, một task có thể giữ thread khoảng 50 giây, chưa tính I/O và overhead. Batch lớn làm tăng throughput trong một số trường hợp nhưng cũng làm tăng thời gian chiếm thread.

Ví dụ:

```java
Pollers.fixedDelay(1_000)
        .maxMessagesPerPoll(5)
```

Nếu queue luôn đầy, task có thể xử lý tối đa 5 message rồi kết thúc. Giảm batch size giúp scheduler có cơ hội chạy các công việc khác thường xuyên hơn, nhưng cũng tăng số lần poll và overhead. Chọn giá trị dựa trên thời gian xử lý thực tế, kích thước message và năng lực downstream.

Nếu mỗi lần poll chỉ cần một message để giữ transaction nhỏ hoặc giảm thời gian chiếm thread, đặt `maxMessagesPerPoll(1)`. Nếu muốn drain queue theo batch, có thể tăng giới hạn nhưng cần có giới hạn thời gian hoặc cơ chế back-pressure phù hợp. Không nên dùng giá trị không giới hạn khi nguồn có thể liên tục trả message.

## 7. Concurrency, thứ tự và xử lý trùng

Khi chuyển poller sang executor hoặc tăng pool size, số task có thể chờ/chạy đồng thời tăng lên. Điều này làm thay đổi giả định tuần tự mà một số handler đang dựa vào.

Các rủi ro thường gặp:

- Hai poll task xử lý cùng một loại dữ liệu cùng lúc và cập nhật cùng bản ghi.
- Message cùng một business key hoàn tất sai thứ tự.
- Handler không idempotent nên retry hoặc gửi lại tạo tác động trùng.
- Database connection pool hoặc API downstream bị quá tải.
- Một instance chạy nhiều task đồng thời trong khi instance khác cũng chạy cùng lịch.

Nếu nghiệp vụ cần tuần tự, hãy xác định phạm vi tuần tự: toàn bộ endpoint, theo tenant, theo order ID hay theo partition. Có thể dùng một executor đơn luồng cho endpoint, phân vùng theo key, khóa ở tầng dữ liệu hoặc distributed lock nếu cần phối hợp nhiều instance. Chỉ dùng distributed lock khi thực sự cần đảm bảo một lần thực thi trên toàn cụm; lock cần lease/timeout và xử lý trường hợp instance chết.

Nếu message được lấy từ broker, bảo đảm acknowledgement/transaction semantics phù hợp với concurrency. Với `QueueChannel` trong bộ nhớ, nhiều poller có thể lấy message khác nhau; điều đó không tự đảm bảo thứ tự hoàn tất theo thời gian gửi.

## 8. Transaction và context khi đổi thread

Transaction thông thường gắn với thread. Khi polling task và handler chạy đồng bộ trên cùng thread, transaction advice được cấu hình quanh poller có thể bao phủ phần xử lý tương ứng. Khi chuyển công việc sang executor, transaction thread-bound ở scheduler thread không tự động truyền sang worker thread.

Vì vậy:

- Đặt transaction boundary ở nơi thực sự thực hiện thao tác dữ liệu.
- Không giả định transaction của producer bao trùm tác vụ bất đồng bộ.
- Xác định transaction bao quanh một message hay cả batch.
- Kiểm tra hành vi rollback và việc message có được nhận lại hay không.
- Với executor, kiểm tra error handling trên worker thread và cách exception được báo về flow.

Tách thread cũng có thể làm thay đổi `ThreadLocal` context như security context, MDC logging hoặc context tùy chỉnh. Nếu cần truyền context, dùng cơ chế propagation được hỗ trợ thay vì giả định nó tự có mặt ở thread mới.

## 9. Timeout, I/O và back-pressure

Một task lâu thường do chờ tài nguyên hơn là do tính toán CPU. Nếu handler gọi HTTP mà không có connect/read timeout, một request có thể giữ thread rất lâu. Tương tự, query database không có timeout hoặc lock chờ lâu có thể chiếm poller worker và làm backlog tăng.

Nên thiết lập timeout phù hợp cho:

- HTTP client, database query và các lời gọi RPC.
- Chờ message hoặc chờ kết quả từ dịch vụ khác.
- Lock và semaphore.
- Shutdown/await termination của scheduler và executor.

Back-pressure cần được xử lý ở ranh giới tiếp nhận công việc. Có thể giới hạn batch, queue capacity, concurrency hoặc tốc độ producer. Nếu producer liên tục phát nhanh hơn consumer, tăng scheduler thread chỉ khiến nhiều task cùng tranh chấp tài nguyên. Hãy theo dõi queue depth và thời gian chờ để quyết định giảm tốc độ nhận, tăng năng lực thực sự hay chuyển tải sang broker.

## 10. Graceful shutdown khi task còn chạy

Khi ApplicationContext shutdown, scheduler và executor cần có chính sách cho task đang chạy và task đang chờ. `ThreadPoolTaskScheduler` và `ThreadPoolTaskExecutor` có các tùy chọn chờ tác vụ hoàn tất và thời gian chờ kết thúc; giá trị cần cân đối với thời gian xử lý tối đa và timeout shutdown của môi trường triển khai.

Một quy trình shutdown hợp lý thường là:

1. Ngừng producer hoặc endpoint tạo thêm công việc.
2. Dừng các poller theo lifecycle và phase phù hợp.
3. Cho phép task đang xử lý hoàn tất trong khoảng thời gian giới hạn.
4. Xử lý task còn chờ theo chính sách: tiếp tục, giữ trong queue bền vững hoặc trả lại nguồn.
5. Đóng executor và scheduler sau khi các component phụ thuộc đã dừng.

`waitForTasksToCompleteOnShutdown` không phải bảo đảm mọi tác vụ hoàn tất vô hạn. `awaitTerminationSeconds` hoặc timeout tương ứng giới hạn thời gian chờ. Nếu task bị kẹt do I/O không timeout, shutdown vẫn có thể kéo dài hoặc kết thúc không như mong đợi.

## 11. Đo và chẩn đoán độ trễ

Đừng chỉ ghi log “task started” và “task finished”. Để phân biệt scheduler delay với processing time, cần ghi ít nhất các mốc:

| Mốc | Ý nghĩa |
|---|---|
| Scheduled/due time | Thời điểm task dự kiến được kích hoạt theo trigger. |
| Actual start time | Thời điểm task thực sự bắt đầu chạy. |
| Poll receive time | Thời điểm message được lấy khỏi channel/source. |
| Handler completion time | Thời điểm xử lý message kết thúc. |
| Queue wait time | Thời gian task/message chờ trong hàng đợi trước khi chạy. |

Từ đó có thể phân rã:

- **Scheduler lag** = actual start time trừ scheduled/due time.
- **Task duration** = thời điểm hoàn tất task trừ actual start time.
- **Executor queue wait** = thời điểm worker bắt đầu trừ thời điểm task được submit.
- **Message processing duration** = handler completion trừ handler start.

Theo dõi thêm:

- Scheduler pool size, active threads và số tác vụ đang chờ.
- Executor active count, queue depth, completed task và rejected task.
- Queue/channel depth và tốc độ message vào/ra.
- Thời gian handler, timeout, retry và lỗi downstream.
- Số lần poll thực tế so với số lần dự kiến.

Thread name prefix giúp nhận diện thread trong log và thread dump. Khi task bị kẹt, thread dump cho biết scheduler đang chạy code nào, chờ monitor/lock nào hoặc đang block ở I/O. Dùng metrics và tracing để xác định điểm nghẽn kéo dài thay vì chỉ nhìn CPU.

## 12. Quy trình xử lý một scheduled task bị trễ

Giả sử poller được cấu hình chạy mỗi 2 giây nhưng log cho thấy có lúc cách nhau 15 giây. Thực hiện theo thứ tự:

1. **Xác nhận lịch dự kiến.** Kiểm tra trigger, `initialDelay`, timezone nếu là cron và thời điểm task đáng lẽ chạy.
2. **Đo scheduler lag.** So sánh due time với actual start time để biết task bị trễ trước khi bắt đầu hay chạy lâu sau khi bắt đầu.
3. **Xác định thread thực thi.** Kiểm tra thread name và thread dump xem scheduler thread có đang chạy handler/I/O hay chờ lock.
4. **Kiểm tra scheduler dùng chung.** Xác định poller và scheduled task nào cùng dùng `TaskScheduler`; kiểm tra pool size và task duration.
5. **Kiểm tra executor nếu có.** Đo queue wait, active worker, queue capacity và rejected task.
6. **Giảm thời gian chiếm thread.** Đặt timeout, giảm `maxMessagesPerPoll`, tối ưu I/O hoặc tách xử lý sang executor phù hợp.
7. **Kiểm soát concurrency.** Nếu tách executor, xác định có cho phép poll chồng lấn không; bảo vệ thứ tự, transaction và idempotency.
8. **Đo lại sau thay đổi.** So sánh scheduler lag, throughput, queue depth và lỗi downstream trước/sau.

| Triệu chứng | Điểm nghẽn có khả năng | Hướng xử lý đầu tiên |
|---|---|---|
| Nhiều scheduled task cùng trễ | Scheduler pool thiếu thread hoặc task dùng chung bị block. | Thread dump, xác định task chiếm thread; cân nhắc pool size/tách scheduler. |
| Chỉ một poller trễ, các task khác đúng lịch | Chính poller hoặc nguồn dữ liệu của nó chậm. | Đo receive/handler duration, timeout và batch size. |
| Trigger đúng nhưng worker bắt đầu muộn | Executor queue backlog. | Kiểm tra queue wait, pool size và rejection. |
| fixedRate chạy liên tục sau task dài | Task thường xuyên vượt period. | Tăng period, giảm thời gian/batch hoặc chọn fixedDelay. |
| Queue tăng dù nhiều thread | Downstream là nút thắt hoặc producer quá nhanh. | Đo throughput thực, timeout và giới hạn concurrency. |
| Xử lý sai thứ tự sau khi tăng pool | Nhiều task chạy đồng thời. | Serialize theo key hoặc giới hạn concurrency. |

## 13. Tự kiểm tra

**Tình huống:** Một ứng dụng có ba poller dùng chung `ThreadPoolTaskScheduler` với một thread. Poller A gọi API ngoài và mất 12 giây; poller B chạy mỗi 2 giây nhưng log cho thấy B thường bắt đầu trễ 10 giây. Sau khi tăng scheduler pool lên 4, B đúng lịch hơn nhưng database bắt đầu quá tải.

1. Vì sao poller A làm poller B trễ?
2. Vì sao tăng scheduler pool giúp B nhưng có thể làm database quá tải?
3. Khi nào nên dùng executor riêng cho poller?
4. Nếu executor cho phép nhiều poll task chạy đồng thời, cần kiểm tra những rủi ro nào?

**Gợi ý trả lời:** (1) A chiếm scheduler thread duy nhất nên B phải chờ. (2) Nhiều task độc lập có thể chạy cùng lúc và tạo nhiều request đồng thời đến database. (3) Khi muốn tách thời điểm kích hoạt khỏi phần công việc poll/handler có thể block, đồng thời đã xác định được giới hạn concurrency và queue. (4) Thứ tự xử lý, cập nhật cùng dữ liệu, transaction thread-bound, idempotency, connection pool và tải downstream.

**Bài tập thực hành:** Tạo hai scheduled/polling task dùng chung một scheduler. Cho task A ngủ 5 giây và task B chạy mỗi giây; ghi due time, actual start và completion. Thử pool size 1 rồi 2. Tiếp tục tách task A sang executor riêng, giới hạn queue và concurrency. So sánh scheduler lag, queue wait, throughput và thứ tự xử lý.

## Tài liệu tham khảo

- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Javadoc — ThreadPoolTaskScheduler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Framework Javadoc — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html#polling-consumer)
- [Spring Integration Java DSL — Poller Configuration](https://docs.spring.io/spring-integration/reference/dsl.html)
