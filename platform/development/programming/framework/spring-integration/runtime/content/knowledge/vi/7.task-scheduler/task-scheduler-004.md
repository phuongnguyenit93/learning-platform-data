# TaskScheduler lifecycle và shutdown

Trong Spring Integration, poller và một số endpoint cần được kích hoạt theo lịch. **TaskScheduler** cung cấp hạ tầng lập lịch: nó quyết định khi nào một task được gọi và trả về handle để theo dõi hoặc hủy lịch. Scheduler không tự quyết định nghiệp vụ nào cần chạy; poller hoặc component đã đăng ký task mới định nghĩa công việc cần thực hiện.

Khi vận hành ứng dụng, cần quản lý hai vòng đời riêng:

- **Vòng đời của scheduled task hoặc Integration endpoint**: task được đăng ký, chạy theo trigger, tạm dừng hoặc hủy khi endpoint dừng.
- **Vòng đời của scheduler bean**: thread pool và tài nguyên lập lịch được khởi tạo, tiếp tục phục vụ các task, rồi được đóng khi ứng dụng shutdown.

Phân biệt hai vòng đời này giúp tránh lỗi phổ biến: dừng một poller nhưng vô tình tắt scheduler đang được nhiều endpoint dùng chung, hoặc đóng scheduler khi vẫn còn endpoint cần chạy.

## 1. TaskScheduler chịu trách nhiệm gì?

`TaskScheduler` là abstraction của Spring Framework để lập lịch thực thi `Runnable`. Nó hỗ trợ các dạng lịch phổ biến:

| API | Mục đích |
|---|---|
| `schedule(task, trigger)` | Chạy theo một `Trigger`, ví dụ cron hoặc trigger tùy chỉnh |
| `schedule(task, instant)` | Chạy một lần tại thời điểm xác định |
| `scheduleAtFixedRate(task, period)` | Chạy theo nhịp cố định |
| `scheduleWithFixedDelay(task, delay)` | Chạy lại sau một khoảng delay tính từ lúc lần trước hoàn tất |

Các phương thức lập lịch trả về `ScheduledFuture<?>` khi có lịch được đăng ký thành công. Handle này cho phép kiểm tra trạng thái, lấy kết quả nếu có và hủy task.

TaskScheduler giải quyết **thời điểm thực thi**. Nó không thay thế `TaskExecutor`:

- `TaskScheduler` quản lý thời điểm và lịch chạy.
- `TaskExecutor` quản lý việc thực thi task trên worker thread.
- `MessageChannel` quản lý cách message được chuyển tới consumer.

Một poller có thể được scheduler kích hoạt, rồi dùng executor để thực thi phần polling. Nếu không có executor tách riêng, task có thể chạy trực tiếp trên thread của scheduler.

## 2. TaskScheduler được dùng trong Spring Integration như thế nào?

Poller của Spring Integration đăng ký một polling task với scheduler. Trigger quyết định thời điểm kích hoạt; khi task chạy, polling endpoint gọi source hoặc nhận message từ pollable channel rồi gửi message vào flow.

~~~mermaid
flowchart TD
    A["ApplicationContext"] --> B["TaskScheduler bean"]
    B --> C["Lập lịch theo Trigger"]
    C --> D["Polling endpoint"]
    D --> E["MessageSource / PollableChannel"]
    E --> F["Message"]
    F --> G["Output channel"]
    G --> H["Downstream handler"]
    D -. "stop endpoint" .-> X["Hủy lịch của endpoint"]
    B -. "context shutdown" .-> Y["Đóng scheduler resources"]
~~~

Một scheduler có thể phục vụ nhiều poller. Ví dụ, ứng dụng có một poller đọc đơn hàng mỗi giây, một poller quét file mỗi phút và một poller kiểm tra trạng thái đối tác theo cron. Các task này cùng chia sẻ pool nếu được cấu hình dùng chung scheduler.

Trong cấu hình Spring Integration thông dụng, scheduler có thể được cung cấp bằng bean theo tên quy ước `taskScheduler`; ứng dụng cũng có thể cấu hình scheduler riêng cho hạ tầng hoặc endpoint tùy phiên bản và cách cấu hình. Khi cần kiểm soát shutdown và số thread, nên khai báo scheduler tường minh để biết chính xác bean nào sở hữu thread pool.

Điểm quan trọng: scheduler không phải một message channel và cũng không phải worker pool chuyên xử lý toàn bộ nghiệp vụ. Nó chỉ kích hoạt công việc theo lịch.

## 3. Các implementation và hành vi thread

`TaskScheduler` là interface. Concrete implementation quyết định cách quản lý thread, pool, lỗi và shutdown.

| Implementation | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| `ThreadPoolTaskScheduler` | Dùng `ScheduledThreadPoolExecutor`; task thường chạy trực tiếp trên scheduler thread | Poller và scheduled task cần pool có thể cấu hình |
| `ConcurrentTaskScheduler` | Adapter quanh một `ScheduledExecutorService` hoặc scheduler có sẵn | Tích hợp với executor do ứng dụng quản lý |
| `SimpleAsyncTaskScheduler` | Mô hình scheduler đơn giản hơn, có hỗ trợ virtual thread trong các phiên bản Spring phù hợp | Workload phù hợp với mô hình thread và phiên bản đang dùng |

`ThreadPoolTaskScheduler` là lựa chọn phổ biến trong ứng dụng Spring. Pool size mặc định của implementation này thường là một thread nếu không cấu hình; vì vậy một task blocking có thể làm các task khác bị trễ. Hãy kiểm tra implementation thực tế và cấu hình của ứng dụng thay vì suy luận từ interface.

Ví dụ khai báo scheduler:

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("integration-scheduler-");
    scheduler.setRemoveOnCancelPolicy(true);
    return scheduler;
}
~~~

Ở đây pool có bốn scheduler thread và tên thread có prefix riêng để dễ nhận diện trong thread dump. `setRemoveOnCancelPolicy(true)` yêu cầu scheduled executor loại task đã hủy khỏi hàng đợi nội bộ, giúp tránh giữ các task canceled quá lâu trong những ứng dụng đăng ký/hủy lịch thường xuyên.

Không nên tăng pool size chỉ vì thấy một poller chậm. Trước tiên cần xác định task bị chậm ở source, downstream handler hay do scheduler thiếu thread. Nếu công việc xử lý message dài, có thể tách execution bằng `TaskExecutor` hoặc channel bất đồng bộ thay vì để scheduler thread thực hiện cả nghiệp vụ.

## 4. Poller, scheduler và executor tạo thành một execution path

Với flow polling, ba thành phần có nhiệm vụ khác nhau:

1. **Poller** mô tả trigger, batch size, transaction advice và các chính sách của lần polling.
2. **TaskScheduler** lên lịch để polling endpoint được kích hoạt.
3. **TaskExecutor** có thể thực thi polling task hoặc các công việc được dispatch bất đồng bộ, tùy cấu hình endpoint.

Ví dụ:

~~~java
@Bean
IntegrationFlow pollOrders(
        MessageSource<Order> orderSource,
        OrderService orderService) {

    return IntegrationFlow.from(orderSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(Duration.ofSeconds(1))
                                    .maxMessagesPerPoll(10)))
            .handle(orderService, "process")
            .get();
}
~~~

Trong ví dụ này, poller được gắn vào inbound endpoint của source. Scheduler kích hoạt endpoint theo fixed delay. Khi endpoint chạy, nó lấy tối đa số message được cấu hình trong một chu kỳ và gửi message qua flow.

Nếu output channel là `DirectChannel`, downstream handler thường chạy đồng bộ trên thread đang gửi message. Khi đó thời gian xử lý của handler có thể kéo dài polling task và chiếm scheduler thread. Nếu output channel là `QueueChannel`, adapter có thể gửi message vào queue rồi kết thúc phần intake; consumer đọc queue là một endpoint khác, có thể có poller riêng. Nếu dùng `ExecutorChannel`, message được dispatch qua executor theo cấu hình channel.

Do đó, khi một poller bị trễ, hãy xem toàn bộ execution path thay vì chỉ tăng scheduler pool.

## 5. Lịch được đăng ký và hủy như thế nào?

Khi endpoint được start, nó đăng ký polling task với scheduler và giữ handle của lịch đã tạo. Khi endpoint được stop, endpoint hủy lịch của chính nó để không có lần kích hoạt mới.

Với code tự lập lịch, `ScheduledFuture` là handle trực tiếp:

~~~java
@Component
class RefreshJob {

    private final TaskScheduler scheduler;
    private ScheduledFuture<?> future;

    RefreshJob(TaskScheduler scheduler) {
        this.scheduler = scheduler;
    }

    void start() {
        if (future == null || future.isCancelled()) {
            future = scheduler.scheduleAtFixedRate(
                    this::refresh,
                    Duration.ofSeconds(30));
        }
    }

    void stop() {
        if (future != null) {
            future.cancel(false);
            future = null;
        }
    }

    private void refresh() {
        // Thực hiện công việc cập nhật trạng thái.
    }
}
~~~

Ví dụ minh họa quyền sở hữu lịch: component tạo lịch giữ lại handle và hủy đúng lịch đó khi không còn cần thiết. Trong flow Spring Integration, hãy để lifecycle của endpoint quản lý lịch poller. Không tự đăng ký một lịch thứ hai cho cùng source nếu endpoint đã tự polling.

`cancel(false)` yêu cầu hủy các lần chạy tiếp theo mà không yêu cầu interrupt task đang chạy. Với một task đang thực thi, thao tác hủy lịch không đồng nghĩa nghiệp vụ đã hoàn tất hoặc đã rollback. Nếu task cần dừng sớm, code phải có cơ chế cooperative cancellation và timeout riêng.

## 6. TaskScheduler và lifecycle của Spring bean

`TaskScheduler` chỉ định nghĩa hợp đồng lập lịch; interface không quy định đầy đủ lifecycle hoặc cách đóng tài nguyên của mọi implementation.

Với scheduler do Spring quản lý như `ThreadPoolTaskScheduler`, Spring có thể khởi tạo pool khi bean được tạo và đóng tài nguyên theo lifecycle/destroy hook khi application context shutdown. Một scheduler tùy chỉnh bọc executor bên ngoài có thể không tự đóng executor đó nếu không được cấu hình hoặc quản lý rõ ràng.

Cần xác định ai sở hữu scheduler:

- Nếu scheduler là bean singleton dùng chung trong application context, context thường là nơi quản lý vòng đời của nó.
- Nếu component tự tạo `ScheduledExecutorService`, component đó phải hủy executor khi bị destroy.
- Nếu scheduler được chia sẻ giữa nhiều application context hoặc được inject từ bên ngoài, không để một endpoint tự ý shutdown tài nguyên dùng chung.
- Nếu scheduler là tài nguyên do nền tảng khác cấp, phải tuân theo hợp đồng sở hữu của nền tảng đó.

Không gọi `shutdown()` trên scheduler dùng chung chỉ vì một flow hoặc một tenant ngừng hoạt động. Hãy stop endpoint hoặc hủy đúng scheduled task mà component đó sở hữu.

## 7. SmartLifecycle, autoStartup và phase

Spring quản lý nhiều endpoint Integration thông qua lifecycle của bean. Các endpoint thường hỗ trợ `start()`, `stop()` và `isRunning()`. Những thành phần triển khai `SmartLifecycle` còn có `autoStartup`, `phase` và callback khi stop.

- `autoStartup` quyết định endpoint có tự start khi application context hoàn tất khởi động hay không.
- `phase` quy định thứ tự start/stop tương đối giữa các bean lifecycle.
- Khi start, phase thấp thường được xử lý trước.
- Khi stop, thứ tự được đảo ngược để các thành phần ở phase cao dừng trước.

Điều này hữu ích khi cần đảm bảo consumer đã sẵn sàng trước khi nguồn bắt đầu polling. Khi shutdown, nguồn vào nên dừng nhận message trước, sau đó mới dừng các consumer và tài nguyên downstream theo thứ tự phù hợp.

Không nên đặt `phase` theo cảm tính. Hãy vẽ dependency giữa source, channel, consumer, connection và scheduler, rồi chọn thứ tự start/stop đáp ứng dependency đó. Với endpoint có `autoStartup=false`, ứng dụng cần có một nơi rõ ràng chịu trách nhiệm start endpoint sau khi dependency sẵn sàng.

## 8. Dừng endpoint khác với shutdown scheduler

Đây là khác biệt quan trọng nhất khi vận hành:

| Hành động | Tác động |
|---|---|
| Stop một polling endpoint | Hủy lịch của endpoint đó; scheduler dùng chung vẫn có thể phục vụ endpoint khác |
| Cancel một `ScheduledFuture` | Hủy lịch cụ thể mà handle đại diện |
| Stop một `SmartLifecycle` scheduler | Yêu cầu scheduler dừng theo lifecycle mà implementation hỗ trợ |
| Shutdown scheduler executor | Đóng thread pool; các task khác dùng pool đó cũng bị ảnh hưởng |
| Đóng application context | Kích hoạt quá trình stop và destroy bean theo lifecycle của context |

Dừng endpoint không đảm bảo một lần poll đang chạy sẽ bị dừng giữa chừng. Nếu source đang thực hiện query hoặc API call, thao tác đó có thể tiếp tục cho đến khi hoàn tất hoặc timeout. Nếu downstream đang xử lý message đồng bộ, thời gian stop có thể phụ thuộc vào handler.

Ngược lại, shutdown scheduler dùng chung có thể khiến mọi endpoint dựa vào scheduler đó không còn được kích hoạt. Vì vậy, việc shutdown scheduler thường thuộc giai đoạn cuối của quá trình dừng ứng dụng.

## 9. Graceful shutdown và immediate shutdown

**Graceful shutdown** cho phép hệ thống ngừng nhận công việc mới, chờ phần việc đang chạy hoàn tất trong giới hạn thời gian, rồi đóng tài nguyên. **Immediate shutdown** ưu tiên dừng nhanh và có thể để lại công việc chưa hoàn tất cần phục hồi.

Một quy trình graceful shutdown nên có các bước:

1. Stop hoặc quiesce các inbound endpoint để không nhận thêm message mới.
2. Chờ polling task đang chạy kết thúc hoặc đạt timeout.
3. Chờ consumer hoàn tất các message in-flight.
4. Drain queue theo chính sách của ứng dụng nếu cần.
5. Đóng scheduler và executor sau khi không còn thành phần cần chúng.
6. Đóng database, broker connection và các dependency ở thời điểm phù hợp.

Graceful shutdown không đồng nghĩa mọi message đều đã commit. Hệ thống vẫn cần xác định trạng thái nguồn, transaction và idempotency để phục hồi sau crash hoặc timeout.

### Cấu hình ThreadPoolTaskScheduler khi shutdown

Ví dụ cấu hình scheduler với thời gian chờ kết thúc task:

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("integration-scheduler-");

    scheduler.setWaitForTasksToCompleteOnShutdown(true);
    scheduler.setAwaitTerminationSeconds(30);
    scheduler.setRemoveOnCancelPolicy(true);

    return scheduler;
}
~~~

`setWaitForTasksToCompleteOnShutdown(true)` yêu cầu executor chờ các task đã được nhận theo chính sách shutdown của implementation. `setAwaitTerminationSeconds(30)` đặt giới hạn thời gian chờ khi đóng pool. `setRemoveOnCancelPolicy(true)` giúp loại bỏ task đã hủy khỏi hàng đợi scheduled executor.

Các thuộc tính này không tự drain queue nghiệp vụ, không xác nhận message ở broker và không bảo đảm transaction downstream đã commit. Với task định kỳ, cần kiểm tra thêm chính sách xử lý delayed/periodic task khi shutdown của phiên bản Spring đang dùng. Hãy kiểm thử hành vi shutdown trong môi trường gần production, đặc biệt khi task có thể chạy lâu hơn timeout.

## 10. Trigger và chính sách chạy ảnh hưởng đến shutdown

Scheduler có thể chạy task theo fixed delay, fixed rate hoặc cron. Loại trigger ảnh hưởng thời điểm task được lên lịch, nhưng không tự quyết định cách nghiệp vụ đang chạy được dừng.

| Lịch | Cách tính lần tiếp theo | Điều cần lưu ý |
|---|---|---|
| Fixed delay | Sau khi lần trước hoàn tất, chờ delay rồi chạy lại | Task chạy lâu làm thời điểm tiếp theo lùi lại |
| Fixed rate | Theo nhịp cố định dựa trên thời điểm bắt đầu | Nếu task kéo dài, lần chạy sau có thể trễ; cùng một periodic task không chạy chồng lên chính nó trong `ScheduledThreadPoolExecutor` |
| Cron | Theo các thời điểm khớp biểu thức | Shutdown có thể xảy ra gần thời điểm trigger; task đã bắt đầu cần xử lý như in-flight work |

Không nên xem fixed rate là cơ chế tự tạo concurrency. Muốn các công việc khác nhau chạy song song, cần đủ scheduler thread hoặc chuyển phần xử lý sang executor phù hợp. Nếu một task fixed rate kéo dài, hãy đo duration và xem xét fixed delay hoặc tách phần công việc nặng.

## 11. Chọn pool size và tránh scheduler starvation

Scheduler pool quá nhỏ có thể khiến task độc lập chờ nhau. Pool quá lớn lại tạo nhiều thread, tăng context switching và có thể gây tải đồng thời lên database hoặc dịch vụ ngoài.

Các nguyên tắc thực tế:

- Đếm số scheduled task có thể chạy đồng thời, không chỉ đếm số poller.
- Đo thời gian thực thi và tỷ lệ task bị chặn I/O.
- Tách nhóm task có latency và độ quan trọng khác nhau sang scheduler riêng khi cần.
- Đưa xử lý nghiệp vụ nặng sang `TaskExecutor` hoặc endpoint bất đồng bộ nếu execution model cho phép.
- Đặt timeout cho source và dependency để task không giữ scheduler thread vô hạn.
- Theo dõi số task đang chạy, độ trễ so với trigger dự kiến và hàng đợi của executor.

`ThreadPoolTaskScheduler` thường thực thi `Runnable` trên chính thread trong scheduler pool. Với poller dùng `DirectChannel`, nếu handler downstream chạy đồng bộ, handler đó cũng có thể chiếm scheduler thread. Đây là nguyên nhân phổ biến khiến các lịch khác bị trễ dù trigger được cấu hình ngắn.

## 12. Xử lý exception của scheduled task

Exception trong scheduled task cần được xử lý có chủ đích. Nếu task định kỳ ném exception, hành vi tiếp tục hoặc ngừng lịch phụ thuộc scheduler, trigger và cách đăng ký task. Với `ThreadPoolTaskScheduler`, có thể cấu hình `ErrorHandler` để ghi log, tăng metric hoặc chuyển lỗi tới cơ chế giám sát phù hợp.

Ví dụ:

~~~java
@Bean(name = "taskScheduler")
ThreadPoolTaskScheduler taskScheduler() {
    ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
    scheduler.setPoolSize(4);
    scheduler.setThreadNamePrefix("integration-scheduler-");
    scheduler.setErrorHandler(error ->
            LoggerFactory.getLogger("integration.scheduler")
                    .error("Scheduled task failed", error));
    return scheduler;
}
~~~

Đoạn code chỉ minh họa điểm gắn error handler. Trong ứng dụng thực tế, hãy dùng logger và telemetry theo chuẩn của dự án, đồng thời tránh log payload hoặc credential nhạy cảm.

Với poller Spring Integration, cần phân biệt exception từ source, exception khi gửi message và exception từ downstream handler. Một số lỗi được xử lý bởi poller advice hoặc error channel của endpoint; lỗi ở scheduled infrastructure có thể đi qua ErrorHandler của scheduler. Không giả định mọi exception đều tự động xuất hiện trong cùng một error channel.

Retry nên có giới hạn, backoff và phân loại lỗi. Nếu scheduled task bị lỗi liên tục, cần có metric và cảnh báo để tránh lịch vẫn tồn tại nhưng công việc không tạo kết quả.

## 13. Thứ tự shutdown của endpoint và dependency

Thứ tự dừng phải phản ánh đường đi của message. Ví dụ một ứng dụng có inbound polling source, channel, service activator, outbound adapter và scheduler dùng chung:

~~~mermaid
flowchart TD
    A["1. Stop inbound source"] --> B["2. Chờ polling task đang chạy"]
    B --> C["3. Drain / hoàn tất consumer"]
    C --> D["4. Stop downstream endpoints"]
    D --> E["5. Shutdown scheduler và executor"]
    E --> F["6. Đóng database / broker connections"]
~~~

Sơ đồ là một thứ tự tham khảo. Ứng dụng có thể cần dừng outbound adapter sau khi consumer đã drain, hoặc giữ database connection mở cho tới khi transaction cuối cùng hoàn tất. Điều quan trọng là không đóng dependency trong khi endpoint còn có thể sử dụng nó.

Với `SmartLifecycle`, phase giúp điều phối thứ tự stop. Callback của `stop(Runnable callback)` cần được gọi khi component thực sự dừng xong; component tự quản lý công việc bất đồng bộ phải không báo hoàn tất quá sớm. Nếu dùng context shutdown timeout của nền tảng, hãy đặt giới hạn đủ cho in-flight work nhưng vẫn phù hợp thời gian terminate của container.

## 14. Quan sát trạng thái và chẩn đoán

Khi scheduled task không chạy đúng, hãy xác định nó dừng ở giai đoạn nào:

1. Bean scheduler có được tạo và khởi tạo thành công không?
2. Endpoint đã start chưa? `isRunning()` trả về gì?
3. Trigger có tạo lịch và thời điểm kích hoạt như mong đợi không?
4. Scheduler pool có thread rảnh không, hay tất cả thread đang bị block?
5. Task có bắt đầu nhưng không kết thúc do source hoặc handler bị treo không?
6. Task đã bị cancel khi endpoint stop hoặc context shutdown chưa?
7. Exception được xử lý bởi poller advice, endpoint error flow hay scheduler `ErrorHandler`?
8. Scheduler đã bị shutdown bởi một component khác đang dùng chung pool không?

Thread name prefix giúp nhận ra thread thuộc scheduler nào trong thread dump. Có thể bổ sung metrics về active thread, pool size, queue size, thời gian thực thi, số lần poll, thời điểm poll cuối và số lỗi. Nếu dùng Micrometer Observation, hãy gắn trace/correlation phù hợp để nối scheduled invocation với các message được tạo ra.

### Dấu hiệu và hướng xử lý

| Dấu hiệu | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Poller trễ so với lịch | Scheduler pool thiếu thread hoặc task trước chạy quá lâu | Đo task duration, tách tác vụ blocking, tăng pool có căn cứ |
| Nhiều poller cùng bị trễ | Dùng chung scheduler bị starvation | Tách scheduler theo nhóm workload và kiểm soát blocking |
| Endpoint báo stopped nhưng task vẫn chạy | In-flight task chưa kết thúc | Dùng timeout, cooperative cancellation và theo dõi in-flight work |
| Một endpoint stop làm mọi lịch ngừng | Component đã shutdown scheduler dùng chung | Chỉ cancel lịch/stop endpoint sở hữu; scheduler do context quản lý |
| Shutdown chờ quá lâu | Task blocking hoặc await termination quá dài | Đặt timeout dependency và thời hạn drain hợp lý |
| Scheduled task lỗi lặp lại | Exception không được phân loại hoặc recovery | Cấu hình ErrorHandler, retry có giới hạn và cảnh báo |
| Queue tăng trong khi scheduler vẫn khỏe | Scheduler chỉ intake; consumer phía sau là bottleneck | Đo tốc độ producer/consumer, giới hạn queue và điều chỉnh concurrency |

## 15. Kiểm thử lifecycle và shutdown

Kiểm thử scheduler nên xác minh hành vi thay vì phụ thuộc vào thời gian chờ dài.

- Đăng ký task và xác nhận task được gọi theo trigger.
- Hủy `ScheduledFuture` rồi xác nhận không có lần chạy mới.
- Stop endpoint và xác nhận poller không tiếp tục kích hoạt.
- Xác nhận scheduler dùng chung vẫn hoạt động cho endpoint khác sau khi một endpoint dừng.
- Đóng application context và xác nhận scheduler-owned thread pool được giải phóng.
- Kiểm thử task đang chạy khi shutdown để xác định timeout và hành vi in-flight.
- Kiểm thử exception để xác nhận ErrorHandler/advice nhận được lỗi.
- Kiểm thử scheduler có task blocking để phát hiện starvation.

Dùng latch hoặc test scheduler để điều khiển thời điểm chạy. Tránh dùng `Thread.sleep()` dài và assertion dựa trên timing mong manh. Với kiểm thử Spring context, cần đóng context rõ ràng để xác minh destroy hook và tránh thread còn sống sau test.

## 16. Checklist vận hành

Trước khi triển khai scheduler vào production, hãy kiểm tra:

- Scheduler bean nào đang được poller và scheduled component sử dụng?
- Ai sở hữu scheduler và ai có quyền shutdown nó?
- Pool size và thread name prefix đã được cấu hình và quan sát chưa?
- Scheduled task nào có thể block hoặc gọi downstream chậm?
- Poller có dùng executor riêng khi cần tách execution không?
- Endpoint có `autoStartup` và `phase` phù hợp không?
- Stop endpoint có hủy đúng lịch mà không ảnh hưởng scheduler dùng chung không?
- Shutdown có ngừng intake trước, chờ in-flight work rồi mới đóng dependency không?
- `waitForTasksToCompleteOnShutdown` và `awaitTerminationSeconds` có phù hợp không?
- Delayed/periodic task có chính sách shutdown rõ ràng không?
- ErrorHandler, retry và metrics có phát hiện scheduled task lỗi không?
- Kiểm thử có bao gồm stop endpoint, context close và task đang chạy không?

TaskScheduler được vận hành tốt khi lịch được đăng ký đúng chủ sở hữu, task không chiếm thread vô hạn, endpoint dừng đúng phạm vi và scheduler chỉ bị đóng sau khi những thành phần phụ thuộc đã hoàn tất công việc cần thiết.

## Tài liệu tham khảo

Các tài liệu dưới đây thuộc Spring Framework và Spring Integration Reference Guide. Hãy đối chiếu phiên bản dependency của ứng dụng vì lifecycle hook và thuộc tính shutdown có thể thay đổi theo phiên bản.

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — TaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/TaskScheduler.html)
- [Spring Framework — ThreadPoolTaskScheduler API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskScheduler.html)
- [Spring Integration — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration — Configuration and Lifecycle](https://docs.spring.io/spring-integration/reference/configuration.html)
- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)

