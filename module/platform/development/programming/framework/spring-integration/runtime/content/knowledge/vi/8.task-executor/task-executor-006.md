# Core pool, max pool và queue capacity

Trong Spring Integration Runtime, `TaskExecutor` quyết định các task được thực thi trên thread nào và có thể chạy đồng thời bao nhiêu việc. Với `ThreadPoolTaskExecutor`, ba tham số quan trọng nhất là `corePoolSize`, `maxPoolSize` và `queueCapacity`.

Ba tham số này không hoạt động độc lập. `corePoolSize` đặt quy mô worker nền; `queueCapacity` quyết định bao nhiêu task được chờ trước khi pool mở rộng; `maxPoolSize` giới hạn số worker khi queue đã đầy. Vì vậy, tăng `maxPoolSize` mà giữ queue không giới hạn thường không làm pool tạo thêm thread. Ngược lại, đặt queue quá nhỏ hoặc bằng 0 có thể làm thread tăng nhanh và đẩy tải xuống database, HTTP client hoặc hệ thống đích.

Muốn cấu hình đúng, cần hiểu thuật toán nhận task của `ThreadPoolExecutor`, sau đó chọn giới hạn dựa trên workload, tài nguyên downstream và chính sách khi pool bão hòa.

## 1. TaskExecutor tham gia vào message flow như thế nào?

Spring Framework định nghĩa `TaskExecutor` để ứng dụng giao một `Runnable` cho cơ chế thực thi. Implementation có thể chạy task trên thread riêng, thread pool hoặc thậm chí thực thi đồng bộ; tên abstraction không tự bảo đảm có thread pool.

Trong Spring Integration, executor thường xuất hiện ở hai ranh giới:

- **ExecutorChannel** dùng executor để dispatch message tới subscriber trên worker thread. Việc gửi message và xử lý handler trở thành hai phần thực thi tách biệt.
- **Polling endpoint** có thể cấu hình `TaskExecutor` để polling task chạy trên worker thay vì chiếm thread của `TaskScheduler`.

Sơ đồ đơn giản:

~~~mermaid
flowchart TD
    P["Producer / Poller"] --> S["Submit task"]
    S --> E["ThreadPoolTaskExecutor"]
    E --> A{"Pool admission"}
    A -->|"Worker available / create core"| W["Worker thread"]
    A -->|"Queue has capacity"| Q["Work queue"]
    Q --> W
    A -->|"Queue full, below max"| X["Create extra worker"]
    X --> W
    A -->|"At max and queue full"| R["Reject task"]
    W --> H["Handler / business work"]
~~~

Executor điều khiển việc thực thi task. Nó không tự quyết định message có được lưu bền vững, được acknowledge hay được retry hay không. Nếu một message được gửi qua `ExecutorChannel`, executor queue là hàng đợi `Runnable` trong JVM; nó khác với `QueueChannel` chứa message và khác với queue của broker.

### Vì sao phải tách hai loại queue?

| Queue | Chứa gì? | Ai lấy phần tử ra? |
|---|---|---|
| `QueueChannel` | `Message<?>` đang chờ consumer | Polling consumer |
| Executor work queue | Task `Runnable` đang chờ worker | Worker thread của executor |
| Broker queue | Message do broker lưu | Broker consumer/adapter |

Một message có thể đã được lấy khỏi `QueueChannel` rồi nhưng task xử lý vẫn đang chờ executor. Ngược lại, executor queue có thể chứa các task polling đang chờ worker trong khi message queue chưa có dữ liệu. Khi điều tra backlog, phải quan sát đúng queue.

## 2. Ba tham số cốt lõi

| Tham số | Ý nghĩa | Tác động chính |
|---|---|---|
| `corePoolSize` | Số worker cốt lõi mà pool duy trì theo chính sách timeout | Quyết định khi nào pool bắt đầu xếp task vào queue |
| `maxPoolSize` | Số worker tối đa được phép tồn tại trong pool | Giới hạn concurrency khi queue không nhận thêm task |
| `queueCapacity` | Số task có thể chờ trong work queue | Quyết định thời điểm pool tạo worker vượt core |

Một worker không nhất thiết luôn tồn tại ngay khi ứng dụng khởi động. Mặc định, thread thường được tạo theo nhu cầu khi có task. Có thể prestart core threads nếu muốn pool sẵn sàng trước khi nhận tải.

`corePoolSize` không phải giới hạn tổng số task đang xử lý và cũng không phải số thread luôn hoạt động. Nó là mốc worker cốt lõi của `ThreadPoolExecutor`. `maxPoolSize` là giới hạn trên, còn queue capacity điều khiển việc pool có cần tăng từ core lên max hay không.

### Giá trị mặc định của ThreadPoolTaskExecutor

Theo Javadoc của Spring Framework, `ThreadPoolTaskExecutor` mặc định có:

| Thuộc tính | Giá trị mặc định |
|---|---:|
| `corePoolSize` | 1 |
| `maxPoolSize` | `Integer.MAX_VALUE` |
| `queueCapacity` | `Integer.MAX_VALUE` |
| `keepAliveSeconds` | 60 |
| `allowCoreThreadTimeOut` | `false` |

Cấu hình mặc định gần giống một executor chỉ dùng một worker vì queue gần như không giới hạn sẽ nhận task sau khi core thread bận. `maxPoolSize` rất lớn không làm pool tự tăng thread khi queue vẫn nhận task.

Đây là mặc định của class `ThreadPoolTaskExecutor`. Nếu ứng dụng dùng Spring Boot auto-configuration hoặc tự khai báo executor bean, hãy kiểm tra bean thực tế và các thuộc tính cấu hình; không nên mặc định executor của mọi ứng dụng có cùng giá trị.

## 3. Thuật toán nhận task của ThreadPoolExecutor

Điểm quan trọng nhất là thứ tự ưu tiên giữa worker và queue. Khi một task mới được submit, `ThreadPoolExecutor` xử lý theo logic khái quát sau:

1. Nếu số worker hiện tại nhỏ hơn `corePoolSize`, thử tạo worker mới để chạy task.
2. Nếu đã đạt core size, thử đưa task vào work queue.
3. Nếu queue không nhận được task vì đã đầy, thử tạo worker mới vượt core size, miễn chưa vượt `maxPoolSize`.
4. Nếu không thể queue và cũng không thể tạo thêm worker, task bị reject theo rejection policy.

Có thể ghi nhớ bằng sơ đồ:

~~~mermaid
flowchart TD
    N["Task mới được submit"] --> C{"Worker count < core?"}
    C -->|"Có"| NC["Tạo core worker chạy task"]
    C -->|"Không"| Q{"Queue nhận được task?"}
    Q -->|"Có"| ENQ["Đưa task vào queue"]
    Q -->|"Không"| M{"Worker count < max?"}
    M -->|"Có"| NM["Tạo worker vượt core"]
    M -->|"Không"| RJ["Rejection policy"]
~~~

Ví dụ cấu hình:

- `corePoolSize = 4`
- `maxPoolSize = 12`
- `queueCapacity = 100`

Nếu task đến liên tục và worker chưa kịp hoàn thành:

| Nhóm task | Hành vi |
|---|---|
| Task 1–4 | Tạo tối đa 4 core worker để chạy |
| Task tiếp theo, tối đa 100 task | Được xếp vào queue |
| Khi queue đã đầy | Pool bắt đầu tạo worker thứ 5 đến tối đa worker thứ 12 |
| Khi đã có 12 worker và queue vẫn đầy | Task mới bị reject |

Con số trên minh họa trạng thái bão hòa khi worker đang bận. Trong runtime thật, worker có thể hoàn thành và lấy task từ queue trong lúc task mới tới, nên số task ở mỗi vùng thay đổi liên tục.

### Vì sao queue được xét trước maxPoolSize?

Đây là hành vi có chủ đích của `ThreadPoolExecutor`. Sau khi core worker đã được tạo, executor ưu tiên xếp task vào queue. Chỉ khi queue từ chối task thì nó mới tăng số worker vượt core.

Do đó, `maxPoolSize` chỉ phát huy tác dụng khi queue có giới hạn và queue đã đầy. Cấu hình `core=4`, `max=20`, `queueCapacity=Integer.MAX_VALUE` thường vẫn chỉ chạy tối đa 4 worker cho tải thông thường, trong khi task chờ có thể tích tụ rất lớn.

## 4. Queue capacity quyết định chiến lược scale

`queueCapacity` không chỉ là số task được phép chờ. Nó quyết định executor sẽ giữ task trong queue bao lâu trước khi mở rộng worker.

Spring `ThreadPoolTaskExecutor` tạo queue theo `queueCapacity`:

- Giá trị dương tạo `LinkedBlockingQueue` có capacity tương ứng.
- Giá trị `0` tạo `SynchronousQueue`, tức cơ chế handoff trực tiếp không lưu task chờ.
- Với queue không giới hạn, task có thể tiếp tục được nhận vào queue và pool không cần tăng vượt core.

### Unbounded queue

Ví dụ:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(20);
// queueCapacity không được đặt: mặc định rất lớn
~~~

Sau khi 4 worker bận, task mới tiếp tục được đưa vào queue. Executor không cần tạo worker thứ 5 vì queue vẫn nhận task.

Hệ quả:

- `maxPoolSize=20` gần như không có tác dụng trong điều kiện queue còn nhận task.
- Thời gian chờ task có thể tăng liên tục khi arrival rate lớn hơn completion rate.
- Queue có thể tiêu thụ heap cho tới khi ứng dụng gặp áp lực bộ nhớ hoặc `OutOfMemoryError`.
- Pool trông có vẻ ổn định vì số thread thấp, trong khi latency và backlog tăng.

Unbounded queue có thể phù hợp với một số workload có tải được kiểm soát và task độc lập, nhưng không phải lựa chọn an toàn mặc định cho hệ thống message có burst hoặc producer không bị giới hạn.

### Bounded queue

Ví dụ:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(100);
~~~

Pool bắt đầu bằng tối đa 4 core worker. Khi tất cả core worker bận, tối đa 100 task tiếp theo được chờ. Chỉ khi queue đầy, executor mới tạo worker vượt core cho tới 12. Khi cả 12 worker đều bận và queue đầy, task mới bị reject.

Ưu điểm:

- Giới hạn lượng task đang chờ trong bộ nhớ.
- Tạo một ngưỡng rõ ràng để pool mở rộng.
- Có thể dự đoán gần đúng giới hạn task đang hoạt động cộng với task đang chờ.
- Khi bão hòa, hệ thống biểu hiện quá tải qua rejection thay vì giữ backlog vô hạn.

Đổi lại, queue quá nhỏ có thể làm pool tăng worker thường xuyên và reject burst ngắn. Queue quá lớn làm task chờ lâu trước khi pool tăng worker và có thể che giấu tình trạng downstream chậm.

### SynchronousQueue với queueCapacity bằng 0

`SynchronousQueue` không lưu phần tử. Mỗi lần submit phải handoff trực tiếp cho worker có thể nhận ngay hoặc khiến pool tạo worker mới nếu chưa đạt max.

Ví dụ:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setQueueCapacity(0);
~~~

Khi 4 core worker đều bận, task mới không thể nằm chờ trong queue. Pool sẽ tạo worker vượt core cho tới 12. Khi 12 worker đều bận và không có worker nhận trực tiếp, task bị reject.

Cách này phản ứng nhanh bằng cách tăng thread, nhưng concurrency có thể tăng mạnh trong burst. Luôn đặt `maxPoolSize` hữu hạn và kiểm tra giới hạn database, HTTP connection, CPU và bộ nhớ. `queueCapacity=0` không có nghĩa là “không giới hạn task”; nó có nghĩa không có buffer chờ trong queue.

## 5. So sánh các cấu hình queue

| Cấu hình queue | Hành vi khi core bận | Tác động đến maxPoolSize | Rủi ro chính |
|---|---|---|---|
| Unbounded (`Integer.MAX_VALUE`) | Hầu như luôn xếp task vào queue | Max gần như không được dùng | Backlog và heap tăng |
| Bounded (ví dụ 100) | Xếp tối đa 100 task | Tăng worker khi queue đầy | Chọn sai capacity làm latency hoặc rejection tăng |
| Direct handoff (`0`) | Không lưu task; handoff hoặc tạo worker | Scale nhanh tới max | Thread tăng nhanh, reject sớm khi max đạt |

Không có một kiểu queue luôn tốt nhất. Hãy chọn theo mức độ burst, độ dài task, khả năng chịu latency và khả năng downstream tiếp nhận concurrency.

## 6. Ví dụ cấu hình ThreadPoolTaskExecutor trong Spring

Một cấu hình giới hạn worker và queue:

~~~java
@Configuration
class IntegrationExecutorConfiguration {

    @Bean("integrationTaskExecutor")
    ThreadPoolTaskExecutor integrationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(100);
        executor.setKeepAliveSeconds(60);

        executor.setThreadNamePrefix("si-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy()
        );

        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);

        return executor;
    }
}
~~~

Spring quản lý lifecycle của `ThreadPoolTaskExecutor` khi bean được đăng ký trong application context. Các thuộc tính cần chú ý:

- `corePoolSize`: worker nền mà pool giữ theo chính sách timeout.
- `maxPoolSize`: giới hạn worker tối đa.
- `queueCapacity`: số task được phép chờ trước khi pool tăng vượt core.
- `keepAliveSeconds`: thời gian worker vượt core được phép idle trước khi bị thu hồi.
- `threadNamePrefix`: giúp nhận diện pool trong log và thread dump.
- `rejectedExecutionHandler`: chính sách khi executor không nhận thêm task.
- `waitForTasksToCompleteOnShutdown`: yêu cầu chờ task hoàn tất khi shutdown.
- `awaitTerminationSeconds`: thời gian chờ tối đa cho việc kết thúc pool theo cấu hình.

Các giá trị 4, 12 và 100 chỉ là ví dụ để giải thích thuật toán. Không sao chép chúng vào production nếu chưa đo tải và giới hạn tài nguyên của ứng dụng.

## 7. Rejection policy khi pool đã bão hòa

Khi worker count đã đạt max và queue không còn chỗ, executor phải quyết định xử lý task mới thế nào. Đây là một phần của behavior contract giữa producer và executor.

| Policy | Hành vi | Khi nào cân nhắc |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException`; Spring `ThreadPoolTaskExecutor` chuyển thành `TaskRejectedException` theo contract `TaskExecutor` | Muốn lỗi rõ ràng để retry, báo động hoặc xử lý ở caller |
| `CallerRunsPolicy` | Thread submit task tự chạy task nếu executor chưa shutdown | Tạo backpressure khi caller có thể chịu việc bị block |
| `DiscardPolicy` | Bỏ task mới mà không báo lỗi | Chỉ dùng khi task có thể mất và điều đó đã được chấp thuận |
| `DiscardOldestPolicy` | Bỏ task cũ nhất trong queue rồi thử submit task mới | Chỉ cân nhắc khi task cũ có thể bị bỏ và thứ tự đã được đánh giá |

Với message processing quan trọng, `DiscardPolicy` và `DiscardOldestPolicy` có thể làm mất công việc mà không có cơ chế phục hồi phù hợp. Cần tránh dùng chỉ để loại bỏ exception.

### CallerRunsPolicy có thể tạo backpressure

Khi executor bão hòa, `CallerRunsPolicy` khiến thread submit task thực thi task đó. Tốc độ producer vì vậy có thể chậm lại, tạo một dạng backpressure đơn giản.

Nhưng cần xác định thread submit là thread nào:

- Với `ExecutorChannel`, đó có thể là thread gọi `send()`.
- Với poller, đó có thể là scheduler thread.
- Với service xử lý request, đó có thể là request thread.

Nếu caller là scheduler thread dùng chung, CallerRunsPolicy có thể làm trễ các poller khác. Nếu caller giữ transaction hoặc lock trong khi chạy task, có thể tăng thời gian giữ tài nguyên hoặc gây deadlock nếu task phụ thuộc ngược vào caller.

### Rejection khác với lỗi handler

`TaskRejectedException` có nghĩa executor không tiếp nhận task theo policy hiện tại. Nó không có nghĩa handler đã chạy và xử lý thất bại.

Cần phân biệt:

- **Submit failure:** task không được nhận vào executor.
- **Execution failure:** task đã chạy nhưng code bên trong ném exception.
- **Business failure:** handler chạy thành công về mặt kỹ thuật nhưng nghiệp vụ từ chối yêu cầu.

Ba loại lỗi này có thể cần retry, logging và error handling khác nhau.

## 8. Queue capacity ảnh hưởng latency như thế nào?

Queue lớn làm giảm khả năng reject trong burst ngắn, nhưng task có thể chờ lâu trước khi được xử lý. Khi queue gần đầy, người dùng thường thấy latency tăng dù CPU chưa đạt 100%.

Ví dụ, một executor có 4 worker. Mỗi task mất trung bình 200 ms. Nếu 100 task nằm trong queue, thời gian chờ của task cuối có thể lên tới nhiều giây, ngay cả khi không có thêm task mới. Đây chỉ là ước lượng theo xử lý tuần tự của bốn worker; thời gian thực tế phụ thuộc độ dài task, độ biến động và cách worker lấy task.

Queue capacity cần cân bằng ba mục tiêu:

1. Hấp thụ burst ngắn mà không reject ngay.
2. Giữ thời gian chờ task trong giới hạn latency chấp nhận được.
3. Không giữ quá nhiều task trong heap khi downstream bị chậm.

Một queue đầy không nhất thiết là lỗi tức thời nếu burst sắp kết thúc và worker đang xả queue. Nhưng queue depth tăng liên tục trong thời gian dài là dấu hiệu arrival rate vượt completion rate.

### Ước lượng capacity cho burst

Nếu arrival rate là `λin` task/giây và completion rate là `λout` task/giây, khi `λin > λout`, backlog tăng gần bằng:

\[
\Delta Q \approx (\lambda_{in} - \lambda_{out}) \times t
\]

Trong đó `t` là thời gian burst. Ví dụ, hệ thống nhận 80 task/giây, xử lý 60 task/giây trong một burst kéo dài 5 giây thì backlog tăng xấp xỉ 100 task. Đây là ước lượng ban đầu; thực tế còn phụ thuộc concurrency, thời gian task và phân bố arrival.

Không nên chọn queue capacity chỉ dựa trên số task trung bình. Hãy quan sát burst thực tế, p95/p99 latency và thời gian downstream phục hồi sau khi bị chậm.

## 9. Chọn corePoolSize và maxPoolSize theo workload

Pool size phải phản ánh đặc tính task và giới hạn tài nguyên.

| Workload | Cách chọn ban đầu |
|---|---|
| CPU-bound | Bắt đầu gần số core CPU khả dụng; tăng thread quá nhiều có thể làm context switching tăng |
| I/O-bound | Có thể cần nhiều thread hơn vì worker thường chờ I/O, nhưng phải giới hạn theo connection pool và dịch vụ đích |
| Task ngắn, lưu lượng ổn định | Core size đủ xử lý tải nền; queue vừa phải để hấp thụ dao động |
| Task dài, burst lớn | Bounded queue và max pool hữu hạn để kiểm soát concurrency |
| Task cần phản hồi nhanh | Queue nhỏ hơn hoặc direct handoff, nhưng cần kiểm soát rejection và max |
| Task nền có thể chờ | Queue có thể lớn hơn nếu latency được chấp nhận và heap có giới hạn |

Một ước lượng concurrency ban đầu có thể dùng định luật Little:

\[
N \approx \lambda \times W
\]

Trong đó `λ` là throughput mong muốn (task/giây), `W` là thời gian xử lý trung bình (giây), và `N` là số task đồng thời trung bình cần có trong trạng thái ổn định.

Ví dụ, cần xử lý 20 task/giây và mỗi task mất 0,25 giây thì concurrency trung bình xấp xỉ 5 task. Pool 5 thread chỉ là điểm bắt đầu lý thuyết; cần headroom cho thời gian xử lý biến động, retry và thời gian chờ I/O. Đồng thời phải kiểm tra downstream có chịu được 5 hoặc nhiều request đồng thời hay không.

### Core và max không thay thế nhau

- Core quá thấp có thể làm pool xử lý tải nền chậm nếu queue lớn khiến pool không mở rộng.
- Core quá cao có thể giữ nhiều thread idle và tiêu thụ tài nguyên ngay cả khi tải thấp.
- Max quá thấp làm task bị reject khi burst vượt khả năng pool và queue.
- Max quá cao có thể tạo quá nhiều thread, gây áp lực CPU, memory stack, database connection hoặc API rate limit.
- Queue quá lớn trì hoãn việc scale và làm latency tăng.
- Queue quá nhỏ khiến pool tăng worker sớm và reject burst ngắn.

Hãy điều chỉnh cả ba cùng lúc dựa trên metrics, thay vì tăng riêng max để chữa mọi vấn đề.

## 10. keepAlive và vòng đời worker

Khi pool đã mở rộng vượt `corePoolSize`, các worker vượt core có thể được thu hồi nếu idle lâu hơn `keepAliveSeconds`.

Ví dụ:

~~~java
executor.setCorePoolSize(4);
executor.setMaxPoolSize(12);
executor.setKeepAliveSeconds(30);
executor.setAllowCoreThreadTimeOut(false);
~~~

Trong cấu hình này, worker vượt core có thể bị thu hồi sau khoảng 30 giây idle. Core worker được giữ lại theo mặc định.

Nếu bật `allowCoreThreadTimeOut(true)`, core thread cũng có thể bị thu hồi khi idle, miễn keep-alive time lớn hơn 0. Điều này giúp pool co lại sâu hơn khi tải thấp, nhưng khi có tải mới cần tạo thread lại.

`prestartAllCoreThreads` có thể dùng để khởi động sẵn core worker trước khi task đầu tiên tới. Cách này giảm độ trễ tạo thread ở task đầu tiên nhưng làm pool dùng tài nguyên ngay khi khởi động.

## 11. Sử dụng executor trong Spring Integration

### ExecutorChannel

`ExecutorChannel` dùng `TaskExecutor` để dispatch message tới subscriber:

~~~java
@Bean
MessageChannel asyncOrdersChannel(
        @Qualifier("integrationTaskExecutor") TaskExecutor executor
) {
    return new ExecutorChannel(executor);
}
~~~

Khi producer gửi message, executor nhận task dispatch. Handler chạy trên worker thread. Ranh giới này làm mất single-thread execution context giữa sender và receiver; transaction context gắn với thread gửi không tự động truyền sang handler. Nếu handler ném exception sau khi sender đã nhận kết quả gửi, exception không thể truyền ngược theo call stack thông thường.

Vì vậy, `ExecutorChannel` cần queue capacity và rejection policy phù hợp. Khi executor bão hòa, `send()` có thể gặp lỗi từ chối task tùy executor và channel configuration.

### Poller có TaskExecutor

Một polling endpoint có thể dùng executor riêng:

~~~java
@Bean
IntegrationFlow ordersPollingFlow(
        QueueChannel ordersQueue,
        @Qualifier("integrationTaskExecutor") TaskExecutor executor,
        OrderHandler handler
) {
    return IntegrationFlow.from(
                    ordersQueue,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(500)
                                    .maxMessagesPerPoll(10)
                                    .taskExecutor(executor)
                    )
            )
            .handle(handler, "process")
            .get();
}
~~~

Trong trường hợp này, executor quản lý polling task. `corePoolSize`, `maxPoolSize` và `queueCapacity` quyết định bao nhiêu poll task được thực thi, chờ hoặc bị từ chối. Nếu có nhiều poller dùng chung executor, một poller có batch dài hoặc `receiveTimeout` lớn có thể chiếm worker và ảnh hưởng endpoint khác.

### Chia sẻ hay tách executor?

| Cách tổ chức | Ưu điểm | Rủi ro |
|---|---|---|
| Một executor dùng chung | Ít pool, quản lý tập trung | Workload chậm có thể chiếm worker của flow quan trọng |
| Executor theo nhóm workload | Cô lập tài nguyên tốt hơn | Nhiều pool làm tăng tổng số thread và độ phức tạp |
| Executor riêng từng endpoint | Kiểm soát chi tiết | Dễ tạo quá nhiều thread và cấu hình trùng lặp |

Hãy nhóm executor theo SLA và đặc tính workload. Không nên tạo một pool cho mỗi flow nếu các flow có tải nhỏ và cùng một chính sách vận hành. Cũng không nên dồn mọi task vào một pool nếu có một workload có thể chiếm hết worker.

## 12. Tránh starvation và deadlock khi queue đầy

Một số lỗi không xuất phát từ số thread quá nhỏ mà từ cách các task phụ thuộc lẫn nhau.

Ví dụ, pool có 4 worker. Cả 4 worker đang chạy task A; mỗi task A chờ một task B được submit vào cùng executor. Queue đã đầy hoặc không còn worker rảnh để chạy B. Task A không thể hoàn tất, còn task B không thể được thực thi. Đây là một dạng thread starvation hoặc thread-pool deadlock.

Cần lưu ý:

- Tránh task trong pool chờ đồng bộ `Future.get()` của task khác được submit vào chính pool đó nếu concurrency không đủ.
- Không để callback cần cùng executor nhưng bị block bởi task đang chờ callback.
- Không dùng `CallerRunsPolicy` khi caller đang giữ lock mà task cần lock đó.
- Tránh queue không giới hạn nếu task có dependency ngược nhau và có thể tích tụ.
- Tách executor cho các nhóm công việc có dependency hoặc SLA khác nhau khi cần.

Một bounded queue và max hữu hạn giúp hệ thống biểu hiện saturation rõ hơn, nhưng không tự sửa được deadlock. Cần thiết kế dependency và timeout của task.

## 13. TaskDecorator và context propagation

Worker thread được tái sử dụng giữa nhiều task. ThreadLocal như MDC logging context, tracing context hoặc security context không nên được giả định tự động chuyển từ thread submit sang worker.

`ThreadPoolTaskExecutor` hỗ trợ `TaskDecorator` để bọc task trước khi thực thi. Có thể dùng decorator để capture và restore context theo thư viện đang dùng.

Ví dụ khái quát với MDC:

~~~java
executor.setTaskDecorator(task -> {
    Map<String, String> context = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            if (context != null) {
                MDC.setContextMap(context);
            }
            else {
                MDC.clear();
            }
            task.run();
        }
        finally {
            if (previous != null) {
                MDC.setContextMap(previous);
            }
            else {
                MDC.clear();
            }
        }
    };
});
~~~

Ví dụ chỉ minh họa việc capture/restore MDC. Với tracing và security context, hãy dùng cơ chế propagation chính thức của thư viện tương ứng để tránh sao chép sai hoặc rò rỉ context giữa các task. Luôn restore hoặc clear context trong `finally`, vì worker thread được tái sử dụng.

## 14. Quan sát pool trong runtime

`ThreadPoolTaskExecutor` cung cấp các thông tin để quản lý và giám sát, như `corePoolSize`, `maxPoolSize`, `keepAliveSeconds`, `poolSize` và `activeCount`. Một số thuộc tính cấu hình có thể được điều chỉnh runtime tùy phiên bản và cách quản lý bean.

Nên theo dõi:

| Metric | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Pool size | Số worker hiện tại | Tăng liên tục tới max |
| Active count | Worker đang bận | Luôn bằng max |
| Queue depth | Task đang chờ | Tăng đều, không giảm sau burst |
| Queue capacity | Giới hạn task chờ | Thường xuyên đạt 100% |
| Rejected task count | Số task bị từ chối | Tăng đột biến hoặc kéo dài |
| Task wait time | Thời gian từ submit tới khi bắt đầu chạy | P95/P99 tăng |
| Task execution time | Thời gian worker chạy task | Tăng do downstream chậm |
| Completed task count | Số task đã hoàn tất | Tăng chậm hơn submit rate |

`activeCount` bằng core size chưa chắc là vấn đề; điều cần xem là queue depth, task wait time và completion rate. Pool size bằng max liên tục cùng queue đầy và rejection tăng là dấu hiệu saturation rõ hơn.

### Cách đọc một số tình huống

| Quan sát | Diễn giải có thể |
|---|---|
| Pool chỉ có core worker, queue tăng | Queue còn chỗ nên executor chưa scale vượt core |
| Pool tăng tới max, queue đầy | Tải vượt khả năng hiện tại; task mới có thể bị reject |
| Pool nhỏ, queue không tăng, latency thấp | Capacity có thể đang phù hợp với tải |
| Active count thấp, queue tăng | Task có thể bị block ở tài nguyên khác hoặc metrics không phản ánh đúng executor đang dùng |
| Queue rỗng nhưng active count luôn max | Worker đang bận xử lý task dài hoặc chờ I/O |
| Rejection tăng nhưng CPU thấp | Có thể queue capacity nhỏ, task block I/O hoặc executor đang shutdown |

Đừng chỉ nhìn CPU để quyết định tăng thread. Với workload I/O-bound, CPU có thể thấp trong khi toàn bộ worker đang chờ database hoặc HTTP.

## 15. Quy trình tuning có kiểm soát

Khi pool không đáp ứng throughput hoặc latency, hãy điều chỉnh theo trình tự:

1. **Xác định đúng executor.** Kiểm tra bean nào được inject vào `ExecutorChannel`, poller hoặc service; tránh tune nhầm pool.
2. **Đo baseline.** Ghi nhận arrival rate, completion rate, task duration, wait time, active count, queue depth và rejection.
3. **Xác định loại workload.** Phân biệt CPU-bound, I/O-bound, task ngắn và task dài.
4. **Kiểm tra downstream.** Xem database connection pool, HTTP connection limit, broker throughput và rate limit.
5. **Chọn core size.** Đặt mức concurrency nền phù hợp với tải thường xuyên.
6. **Chọn queue capacity.** Đặt giới hạn hấp thụ burst trong thời gian latency chấp nhận được.
7. **Chọn max size.** Đặt trần concurrency khi queue đầy và downstream vẫn có thể chịu tải.
8. **Chọn rejection policy.** Xác định task bị từ chối sẽ retry, báo lỗi, backpressure hay được xử lý theo chính sách khác.
9. **Load test theo burst và saturation.** Kiểm tra cả lúc tải tăng, tải giảm và downstream bị chậm.
10. **Theo dõi sau triển khai.** Xác nhận queue drain trở lại, rejection không kéo dài và latency nằm trong SLA.

Không tăng đồng thời core, max và queue mà không đo. Nếu thay cả ba, sẽ khó xác định yếu tố nào tạo ra cải thiện hoặc gây tác dụng phụ.

## 16. Checklist trước khi đưa executor vào production

- [ ] Đã xác định đúng executor bean mà endpoint hoặc channel sử dụng chưa?
- [ ] `corePoolSize` có phù hợp với tải nền và tài nguyên CPU không?
- [ ] `maxPoolSize` có giới hạn concurrency phù hợp với downstream không?
- [ ] `queueCapacity` có hữu hạn và phù hợp với burst/latency không?
- [ ] Đã hiểu queue được xét trước khi tạo worker vượt core chưa?
- [ ] Nếu dùng queue không giới hạn, đã chấp nhận rủi ro backlog và heap chưa?
- [ ] Nếu `queueCapacity=0`, max thread có hữu hạn không?
- [ ] `keepAliveSeconds` và `allowCoreThreadTimeOut` có phù hợp với biến động tải không?
- [ ] Rejection policy có giữ được semantics của message và nghiệp vụ không?
- [ ] CallerRunsPolicy có thể block scheduler, request thread hoặc giữ lock không?
- [ ] Task có phụ thuộc task khác trong cùng pool và có nguy cơ starvation không?
- [ ] Database, HTTP client và broker có chịu được concurrency đã chọn không?
- [ ] MDC, tracing và security context có được propagate an toàn không?
- [ ] Có metric cho pool size, active count, queue depth, wait time và rejection không?
- [ ] Shutdown có chờ task theo timeout và ownership rõ ràng không?

`corePoolSize`, `maxPoolSize` và `queueCapacity` tạo thành một chính sách admission và concurrency thống nhất. Core xác định quy mô worker nền; queue xác định lượng task được chờ và thời điểm scale; max đặt trần worker khi queue đầy. Khi hiểu đúng thứ tự này, có thể chọn pool để hấp thụ burst trong giới hạn, bảo vệ downstream và phát hiện saturation trước khi backlog làm hệ thống mất ổn định.

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — TaskExecutor abstraction và thứ tự core, queue, max, rejection.
- [Spring Framework — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html) — default values, queueCapacity, poolSize, activeCount và runtime management.
- [Java Platform — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html) — worker creation, queuing strategies và rejection.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html) — ExecutorChannel và ranh giới thread/transaction.
- [Spring Integration — Message Endpoints](https://docs.spring.io/spring-integration/reference/endpoint.html) — TaskExecutor support cho polling endpoint.

Default values và chi tiết implementation có thể thay đổi theo Spring Framework, JDK và Spring Integration version. Hãy đối chiếu Javadoc đúng dependency của ứng dụng và kiểm tra executor bean thực tế trước khi áp dụng cấu hình.
