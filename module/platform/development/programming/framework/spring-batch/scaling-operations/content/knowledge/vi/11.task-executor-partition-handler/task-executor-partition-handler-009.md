# Giới hạn queue của executor

Khi sử dụng **TaskExecutorPartitionHandler** để chạy nhiều partition của một Spring Batch job trong cùng JVM, một câu hỏi vận hành rất quan trọng là: **điều gì xảy ra khi số partition được giao lớn hơn khả năng xử lý của thread pool?** Nếu để queue của executor quá lớn, hệ thống có thể tích lũy nhiều công việc đang chờ, làm che giấu tắc nghẽn và tăng áp lực bộ nhớ. Nếu giới hạn queue quá nhỏ mà không có cơ chế kiểm soát tốc độ gửi task, manager có thể gặp **task rejection** trong khi một số worker đã bắt đầu xử lý.

Bài học thuộc chương **TaskExecutorPartitionHandler** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng tới mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán, đồng thời đo nút thắt, đảm bảo thread safety, retry/restart, vận hành job và chọn kiến trúc phù hợp tài nguyên. Chủ đề ở đây là **thiết lập giới hạn queue có chủ đích, hiểu quan hệ giữa số partition và số thread, xử lý saturation an toàn và đo hiệu quả của cơ chế backpressure**.

**Thông điệp chính:** `queueCapacity` kiểm soát **số task chờ trong executor**, không kiểm soát số partition được tạo, không thay thế giới hạn thread pool và không phải một hàng đợi bền vững có khả năng tự khôi phục sau khi JVM chết.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `TaskExecutorPartitionHandler`, `Partitioner`, `gridSize`, `ThreadPoolTaskExecutor` và `StepExecution`.
2. Phân biệt `corePoolSize`, `maxPoolSize`, `queueCapacity`, số partition **đã tạo**, số task **đang chạy**, **đang chờ** và **chưa được chấp nhận**.
3. Dự đoán chính xác hành vi của thread pool với queue dương, queue bằng 0 và queue mặc định rất lớn.
4. Cấu hình Spring Batch 5.x/Java 17+ để chạy local partitioning trong một ngân sách tài nguyên hữu hạn.
5. Chọn cách xử lý task bị từ chối mà không làm biến mất partition hoặc che giấu lỗi.
6. Thiết kế backpressure cho workload lớn thay vì tăng queue vô hạn.
7. Kiểm thử saturation bằng `CountDownLatch`, xử lý thất bại/restart và theo dõi metrics của executor, JobRepository, DB pool.

**Tình huống xuyên suốt:** job xử lý một triệu bản ghi từ 64 partition độc lập. Do giới hạn DB và tài nguyên JVM, hệ thống muốn chỉ có tối đa bốn worker hoạt động đồng thời. Nhóm đề xuất `corePoolSize=4`, `maxPoolSize=4`, `queueCapacity=8`. Cấu hình đó **không tự bảo đảm manager có thể gửi một lượt 64 partition mà không bị từ chối**. Cần hiểu cách admission và batching của việc điều phối partition trước khi triển khai.

## 2. TaskExecutorPartitionHandler điều phối những gì?

Trong **local partitioning**, một **manager step** dùng `Partitioner` để tạo bản đồ `partitionName -> ExecutionContext`. Từng entry được đại diện bởi một worker `StepExecution`. **TaskExecutorPartitionHandler** sử dụng một `TaskExecutor` để thực thi các worker step, rồi thu thập kết quả thực thi. Ở mức ý tưởng:

~~~mermaid
flowchart TD
    J["JobExecution"] --> M["Manager Step"]
    M --> P["Partitioner: trả map partition"]
    P --> H["TaskExecutorPartitionHandler"]
    H --> E["ThreadPoolTaskExecutor"]
    E --> R["Running: tối đa theo pool"]
    E --> Q["Queue: task đã nhận, chưa chạy"]
    H -. "Khi executor hết khả năng nhận" .-> X["TaskRejectedException / rejection"]
    R --> W["Worker StepExecution / chunk transaction"]
    Q --> R
    W --> DB[("JobRepository và business DB")]
~~~

**Cần phân biệt hai cấp thực thi:**

- **Partition task** là công việc executor nhận từ handler, thường đại diện cho việc chạy **một worker StepExecution**.
- **Chunk** nằm **bên trong** worker step và có thể gồm nhiều lần đọc, xử lý, ghi và commit. `queueCapacity` của executor partition không phải “số chunk chờ” hay “số item chờ”.

Trong cách dùng thông thường, một worker step xử lý nhiều chunk trên thread mà handler đã phân công. Nếu bật thêm `taskExecutor` bên trong worker step, hệ thống có **hai tầng concurrency** cần kiểm tra riêng; không được lấy giới hạn queue ở tầng manager làm giới hạn mọi thread/transaction của ứng dụng.

### Một ví dụ phân công

~~~text
Partitioner trả 16 entry:
  partition0 .. partition15

Executor:
  core = 4
  max  = 4
  queueCapacity = 12

Tại thời điểm tất cả worker còn bận:
  4 task đang chạy
  12 task đang chờ
  0 task bị từ chối trong đợt gửi 16 task
~~~

Đây là **kịch bản minh họa có executor chỉ dành cho job đó**, không phải cam kết scheduling của mọi thời điểm. Nếu pool dùng chung với task khác, đã có task tồn đọng, hoặc `Partitioner` trả nhiều hơn 16 entry, ngân sách sẽ khác.

## 3. Bốn con số không được đánh đồng

| Tham số / số đo | Nằm ở đâu | Nó quy định điều gì? | Nó **không** quy định điều gì? |
| --- | --- | --- | --- |
| `gridSize` | Manager/handler, truyền cho `Partitioner` | Gợi ý độ chia của kế hoạch, tùy implementation | Không giới hạn cứng số entry map nếu Partitioner bỏ qua gợi ý |
| `corePoolSize` | ThreadPoolTaskExecutor | Số worker core mà pool cố gắng duy trì theo chính sách thread pool | Không phải số partition đang tồn tại trong JobRepository |
| `maxPoolSize` | ThreadPoolTaskExecutor | Số thread tối đa của pool | Không phải số task được nhận; còn có queue |
| `queueCapacity` | ThreadPoolTaskExecutor | Số task có thể **đợi trong hàng đợi** | Không phải số worker chạy song song hoặc hàng đợi bền vững |

Thêm hai số quan sát vận hành:

- **Active count:** số thread đang thực thi task ở thời điểm lấy mẫu; biến thiên khi worker hoàn tất.
- **Queue size:** số task đã được chấp nhận nhưng chưa được một thread lấy ra chạy, không bao gồm task đang thực thi.

Nếu một Partitioner tạo 64 entry, pool có bốn thread và queue chứa tám task, **52 partition còn lại không tự động nằm trong queue ấy**. Chúng có thể đang ở logic điều phối chưa gửi, hoặc nếu handler cố gửi ngay thì có thể xảy ra rejection. Không nên suy đoán rằng executor tự chia batch để chờ hết 64 partition chỉ vì queue có 8 slot.

## 4. Cách ThreadPoolExecutor thực sự dùng queue

Spring Framework `ThreadPoolTaskExecutor` bao bọc cơ chế thread pool của Java. Khi **queueCapacity > 0**, nó thường sử dụng `LinkedBlockingQueue` với giới hạn tương ứng. Khi **queueCapacity = 0**, nó dùng hàng đợi chuyển giao trực tiếp kiểu `SynchronousQueue`, tức **không lưu task đợi trong queue**. Hành vi tạo thread của pool thông thường:

1. Nếu số thread đang tồn tại nhỏ hơn `corePoolSize`, pool tạo thêm core thread cho task mới.
2. Khi đã đạt core, pool **ưu tiên xếp task vào queue** nếu còn chỗ.
3. Chỉ khi queue đầy, pool mới tăng thêm thread ngoài core, tối đa `maxPoolSize`.
4. Nếu queue đầy và đã đạt max, task tiếp theo bị xử lý theo **RejectedExecutionHandler**.

### Ví dụ 1: queue rộng khiến maxPoolSize ít có tác dụng

~~~text
corePoolSize   = 2
maxPoolSize    = 8
queueCapacity  = 1000
Số partition   = 100

Giả sử worker chạy đủ lâu, không hoàn tất khi manager gửi task:
  2 task chạy
  98 task xếp queue
  Pool chưa cần tăng tới 8 thread
~~~

Một cấu hình `maxPoolSize=8` trông có vẻ cho tám worker song song, nhưng với queue lớn, **chỉ hai core worker có thể đang làm việc**. Đó là một trong những lý do thường gặp khiến tăng `maxPoolSize` mà throughput không cải thiện.

### Ví dụ 2: queue có giới hạn, thread mới được tạo khi queue đầy

~~~text
corePoolSize  = 2
maxPoolSize   = 6
queueCapacity = 10

Khi các task chưa kịp hoàn tất:
  Task 1-2   -> 2 core threads
  Task 3-12  -> queue 10 task
  Task 13-16 -> tạo 4 thread thêm, tổng 6 thread
  Task 17    -> rejection
~~~

Ở thời điểm bão hòa và không có worker hoàn tất, pool này nhận tối đa **6 task đang chạy + 10 task chờ = 16 task**. Công thức `maxPoolSize + queueCapacity` là một **cận minh họa cho số task outstanding được executor chứa trong trạng thái bão hòa**, không phải cam kết cho mọi lịch chạy: worker có thể hoàn tất và nhận task tiếp theo ngay trong lúc manager còn gửi.

### Ví dụ 3: queueCapacity bằng 0

~~~text
corePoolSize  = 2
maxPoolSize   = 6
queueCapacity = 0

Các task có thể được chuyển giao trực tiếp tới các thread:
  Tối đa 6 task chạy đồng thời (khi pool đã tăng đến max)
  Không có slot giữ task chờ trong queue
  Task tiếp theo khi mọi thread bận -> rejection
~~~

Queue bằng 0 có thể hữu ích cho một chiến lược **admission có kiểm soát từ bên ngoài**, nhưng dễ gây task rejection nếu handler submit một loạt partition mà chưa chờ có worker rảnh.

### Giá trị mặc định cũng cần xem kỹ

`ThreadPoolTaskExecutor` thường mặc định `corePoolSize=1`, `maxPoolSize` rất lớn và `queueCapacity` rất lớn. Do queue nhận task trước khi pool tăng vượt core, một pool khai báo sơ sài có thể chạy gần như **một thread** và tích lũy task đợi. **Luôn cấu hình rõ cả core/max/queue khi dùng cho batch** và kiểm tra hành vi theo phiên bản Spring Framework thực tế.

## 5. Vì sao phải giới hạn queue?

Hàng đợi dài không đồng nghĩa thông lượng lớn. Nó chủ yếu **dịch thời gian chờ và áp lực tài nguyên sang bên trong JVM**.

| Rủi ro | Queue quá lớn | Queue quá nhỏ nếu không có backpressure |
| --- | --- | --- |
| Thời gian chờ | Partition có thể đợi lâu, thời gian job khó dự báo | Task có thể bị từ chối trước khi chạy |
| Bộ nhớ | Nhiều Runnable/Future/context được giữ, tăng heap và GC pressure | Ít task tồn đọng trong executor |
| Quan sát nút thắt | Dễ che giấu worker chậm, DB pool nghẽn | Saturation lộ rõ, nhưng cần xử lý có chủ đích |
| Dừng job | Nhiều task đã xếp lịch phải được xử lý/hủy đúng | Từ chối task phải được ghi nhận ở manager |
| Restart | Queue là bộ nhớ tạm, **không** lưu bền vững | Vẫn phụ thuộc JobRepository, không phải queue tự retry |

Tuy nhiên, **queue bounded không tự là backpressure hoàn chỉnh**. Nếu nhà sản xuất task (handler) không chờ được khi queue đầy, executor chỉ phát ra lỗi từ chối. Backpressure thật nghĩa là **điều phối viên giảm tốc độ submit, tạm chờ tài nguyên hoặc chia việc thành đợt với giao thức retry rõ ràng**.

## 6. GridSize, số partition và kích thước queue: chọn nhất quán

Đặt:

- `P`: số partition thực tế mà Partitioner trả về.
- `W`: số worker chạy đồng thời theo ngân sách tài nguyên, thường gần `corePoolSize=maxPoolSize` khi muốn giới hạn cứng.
- `Q`: số task đợi tối đa trong executor.
- `A`: số task outstanding mà executor có thể nhận trong một đợt gửi khi mọi worker bị giữ, xấp xỉ `W + Q`.

Với **một đợt submit toàn bộ P task, không có task nào hoàn tất trong lúc submit**, nếu pool dành riêng cho job:

~~~text
Muốn nhận tất cả P task ngay:
  cần đủ sức chứa cho P task outstanding
  khi corePoolSize = maxPoolSize = W:
      Q >= max(0, P - W)

Ví dụ P=16, W=4:
  Q >= 12 nếu không muốn rejection trong tình huống xấu nhất.
~~~

Đây là **cách tính ngân sách đơn giản cho số partition vừa phải**, không phải lời khuyên luôn tăng queue theo P. Nếu `P=100000` thì tăng queue lên 99996 có thể là một thiết kế vận hành tồi. Cần chuyển sang **bounded submission, nhóm partition hoặc cơ chế điều phối khác**.

### Nếu corePoolSize khác maxPoolSize

Với queue dương, task thường được đưa vào queue sau khi đạt core; thread chỉ tăng đến max khi queue đầy. Vì vậy **thời điểm** queue đầy ảnh hưởng số worker thực sự hoạt động. Nếu muốn giới hạn cứng concurrency và hành vi dễ dự đoán cho batch, cấu hình `corePoolSize=maxPoolSize=W` là điểm xuất phát dễ vận hành hơn. Nếu muốn elastic pool, phải đo đúng hiệu ứng queue và chính sách mở rộng thread.

### Nếu nhiều job dùng chung pool

Công thức `P <= W+Q` **không đủ** nếu pool đã chứa task của job khác. Cần:

- executor riêng theo workload/SLA hoặc một lớp admission dùng chung;
- ngân sách tổng của các job cạnh tranh;
- giới hạn connection pool, transaction và API quota tương ứng;
- kiểm thử khi **hai job cùng chạy**, không chỉ chạy từng job riêng lẻ.

## 7. Cấu hình Spring Batch 5.x với queue bounded

Ví dụ Java 17+, Spring Batch 5.x, Spring Boot 3.x. Giả sử đã có `JobRepository`, `PlatformTransactionManager`, `workerStep` và `Partitioner` phù hợp. Trong ví dụ, Partitioner được cấu hình để trả **không quá 16 partition**, còn executor có bốn thread cố định và queue 12.

~~~java
@Bean
ThreadPoolTaskExecutor partitionTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setThreadNamePrefix("partition-worker-");
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(12);

    // Từ chối rõ ràng thay vì bỏ rơi partition lặng lẽ.
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());

    // Shutdown graceful cần được phối hợp với JobRepository/lifecycle.
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    executor.initialize();
    return executor;
}

@Bean
Step managerStep(
        JobRepository jobRepository,
        @Qualifier("workerStep") Step workerStep,
        @Qualifier("rangePartitioner") Partitioner partitioner,
        @Qualifier("partitionTaskExecutor") TaskExecutor executor) {

    return new StepBuilder("managerStep", jobRepository)
            .partitioner(workerStep.getName(), partitioner)
            .step(workerStep)
            .gridSize(16)
            .taskExecutor(executor)
            .build();
}
~~~

Với builder này, Spring Batch cấu hình cơ chế local partitioning sử dụng `TaskExecutorPartitionHandler` ở dưới. **Điều kiện quan trọng:** `gridSize(16)` chỉ là tham số cho Partitioner/điều phối, không phải ràng buộc tự động số entry trả về. Nếu `rangePartitioner` tạo 64 entry dù nhận gridSize=16, manager có thể submit nhiều hơn ngân sách 16 task và bị rejection.

`setWaitForTasksToCompleteOnShutdown(true)` và `setAwaitTerminationSeconds(60)` chỉ thể hiện ý đồ chờ công việc khi application context shutdown; **không phải** cơ chế giao dịch phân tán hoặc bảo đảm mọi worker chắc chắn commit được trước khi tiến trình bị kill. Thời hạn chờ phải được lựa chọn theo đặc tính job và yêu cầu vận hành.

### Một Partitioner chỉ để minh họa số lượng task

~~~java
final class DemonstrationPartitioner implements Partitioner {
    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        if (gridSize <= 0) {
            throw new IllegalArgumentException("gridSize must be positive");
        }
        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        for (int i = 0; i < gridSize; i++) {
            ExecutionContext context = new ExecutionContext();
            context.putInt("bucket", i);
            context.putInt("bucketCount", gridSize);
            result.put("partition" + i, context);
        }
        return result;
    }
}
~~~

Đoạn Partitioner trên **chỉ sinh metadata**. Worker thật phải dùng `bucket` và `bucketCount` để lọc dữ liệu không giao nhau, có nguồn dữ liệu bất biến và writer idempotent; nếu worker bỏ qua hai giá trị ấy, mọi partition có thể xử lý cùng toàn bộ dữ liệu. Đừng dùng phần sinh map làm bằng chứng đã chia đúng workload.

## 8. Khi số partition lớn: không tăng queue vô hạn

Giả sử có 10.000 phân vùng (ví dụ 10.000 file nhỏ), nhưng DB chỉ chịu được 8 worker. Đặt queue 9.992 cho phép handler gửi cả loạt nhưng không hề tăng số worker đồng thời; các partition vẫn nối đuôi nhau. Khi StepExecution metadata, Future và logic quản lý tồn tại đồng thời với số lượng lớn, chi phí điều phối có thể đáng kể.

Có ba hướng thiết kế:

### 8.1. Giảm số partition bằng cách nhóm công việc

Thay 10.000 file/partition bằng khoảng 100 nhóm file, mỗi nhóm gồm một tập file ổn định và không giao nhau. Worker dùng `MultiResourceItemReader` hoặc manifest nhóm. Điều này giảm overhead metadata/scheduling nhưng cần chú ý cân bằng tải và checkpoint khi nhóm chứa nhiều file.

Nhóm theo tenant, region, khoảng khóa chính hoặc tổng dung lượng có thể hợp lý hơn một partition cho một item nhỏ. **Thứ tự và thành viên nhóm phải bất biến qua restart**.

### 8.2. Thực hiện theo đợt với cơ chế điều phối có trạng thái

Một tầng orchestration có thể gửi tối đa `K` partition, đợi kết quả rồi gửi đợt tiếp theo. Tuy nhiên, **không thay đổi tùy ý tên/ranh giới partition khi restart**; trạng thái của các đợt đã hoàn tất cần được lưu bền vững và liên kết với JobInstance tương ứng.

Nếu tự triển khai một `PartitionHandler` có admission theo đợt, phải định nghĩa rõ: task lỗi được ghi nhận ra sao, manager đợi/kết thúc khi nào, shutdown/interruption xử lý thế nào, và không bao giờ báo COMPLETED khi vẫn còn partition chưa được xác nhận.

### 8.3. Giới hạn số task “đang bay” bằng semaphore

Có thể bọc một `TaskExecutor` bằng **admission gate**. Trước khi executor nhận task, một permit phải được cấp; khi task kết thúc, permit được trả lại. Thay vì cố submit cả 10.000 task vào queue, thread điều phối sẽ chờ khi số task outstanding đạt ngưỡng.

Đây là một cách tiếp cận **nâng cao cần kiểm thử kỹ cùng TaskExecutorPartitionHandler**, không phải chức năng tự động được bật bằng `queueCapacity`. Nó thay đổi hành vi của thread gửi task: **thread đó có thể bị chặn trong execute()**, cần bảo đảm không giữ transaction/lock gây deadlock.

~~~java
final class AdmissionLimitedTaskExecutor implements TaskExecutor {
    private final TaskExecutor delegate;
    private final Semaphore permits;

    AdmissionLimitedTaskExecutor(TaskExecutor delegate, int maxInFlight) {
        if (maxInFlight <= 0) {
            throw new IllegalArgumentException("maxInFlight must be positive");
        }
        this.delegate = delegate;
        this.permits = new Semaphore(maxInFlight, true);
    }

    @Override
    public void execute(Runnable task) {
        try {
            permits.acquire(); // Đợi có slot, có thể bị interrupt.
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new TaskRejectedException(
                    "Interrupted while waiting for partition admission", ex);
        }

        // Bảo đảm release đúng một lần, cả khi executor chạy inline.
        AtomicBoolean released = new AtomicBoolean(false);
        try {
            delegate.execute(() -> {
                try {
                    task.run();
                } finally {
                    releaseOnce(released);
                }
            });
        } catch (RuntimeException ex) {
            releaseOnce(released); // Nếu delegate từ chối trước khi chạy.
            throw ex;
        }
    }

    private void releaseOnce(AtomicBoolean released) {
        if (released.compareAndSet(false, true)) {
            permits.release();
        }
    }
}
~~~

Với **executor chuyên dụng** `core=max=4`, `queueCapacity=4` và wrapper `maxInFlight=4`, chỉ bốn task được gửi khi chưa có task kết thúc. Một worker vừa hoàn tất có thể trả permit trước khi thread pool lấy task mới; queue 4 slot giúp hấp thụ khoảng chuyển trạng thái ngắn đó. Không dùng công thức này như bằng chứng an toàn cho pool có nhiều nhà sản xuất task khác; cần thiết kế ngân sách **toàn hệ thống**.

**Những giới hạn của ví dụ:**

- Không có timeout chờ permit ngoài interruption. Production có thể dùng `tryAcquire(timeout)`, cancellation policy và metrics wait time.
- Nếu wrapper được chia sẻ giữa nhiều job, permit là ngân sách **chung**, không bảo đảm quota công bằng theo tenant.
- Nếu code worker treo vô hạn, permit không được trả cho tới khi task thật sự kết thúc hoặc bị hủy; cần timeout/health check cấp nghiệp vụ.
- `TaskExecutorPartitionHandler` cần được integration test với wrapper để bảo đảm điều phối/restart vẫn đúng trong môi trường ứng dụng; không chỉ unit test wrapper.
- Tất cả nguồn dữ liệu, `StepExecution` và writer phải chịu được worker retry/restart; semaphore chỉ giới hạn concurrency, **không** tạo exactly-once business effect.

## 9. RejectedExecutionHandler: chọn chính sách nào?

Khi executor đã đạt giới hạn, JDK `ThreadPoolExecutor` gọi một **RejectedExecutionHandler**. Các chính sách thường gặp:

| Chính sách | Hành vi bão hòa | Đánh giá cho TaskExecutorPartitionHandler |
| --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` (Spring có thể chuyển thành `TaskRejectedException`) | **Mặc định ưu tiên nếu không có admission**: lỗi rõ, không âm thầm bỏ task |
| `CallerRunsPolicy` | Cho thread gọi `execute()` chạy task, nếu pool còn hoạt động | Có tác dụng làm chậm bên gửi, nhưng worker có thể chạy trên **manager thread**; phải đánh giá ngữ cảnh và deadlock |
| `DiscardPolicy` | Bỏ task bị từ chối mà không báo lỗi | **Không phù hợp**: partition có thể không được chạy hoặc logic đợi kết quả bị treo |
| `DiscardOldestPolicy` | Loại task cũ trong queue rồi thử task mới | **Không phù hợp**: có thể bỏ công việc đã được manager tin rằng đã gửi |

### Vì sao CallerRunsPolicy không luôn là lời giải an toàn?

Khi pool bão hòa, `CallerRunsPolicy` có thể thực thi worker step **ngay trên thread đang submit**. Điều này:

- làm thay đổi mô hình thread, stack và thời gian mà manager chờ ở lệnh `execute`;
- có thể đưa các thao tác DB, MDC, bảo mật và transaction sang thread không dự kiến;
- có thể gây vấn đề nếu thread điều phối đang giữ lock hoặc tài nguyên mà worker cần;
- khiến số thread pool quan sát được không phản ánh tổng số worker đang thực thi, vì một task có thể chạy ngoài pool.

Nó **không nhất thiết sai trong mọi ứng dụng**, nhưng phải được kiểm tra chủ động về tính đúng đắn, thread context, shutdown và hiệu năng. Không chỉ thêm `CallerRunsPolicy` để che `TaskRejectedException` trong production.

**Đặc biệt tránh DiscardPolicy/DiscardOldestPolicy.** Một task bao bọc worker StepExecution có thể đã được hệ thống điều phối dự kiến nhận kết quả; việc bỏ Runnable một cách im lặng có thể làm thiếu xử lý hoặc khiến manager chờ không có tín hiệu hoàn tất.

## 10. Khi một task bị từ chối, dữ liệu đã xử lý ra sao?

Task bị từ chối là **lỗi admission**, không đồng nghĩa “toàn job chưa làm gì”. Trước đó, một số partition có thể:

- đã bắt đầu và commit nhiều chunk;
- đã hoàn tất và lưu StepExecution COMPLETED;
- đang chạy transaction chưa biết đã commit hay rollback;
- nằm trong queue nhưng chưa bắt đầu.

Với cấu hình mặc định, lỗi từ executor thường lan về phía manager/handler tùy điểm gọi; job có thể thất bại hoặc bị ngắt điều phối. **Không được suy ra trạng thái từng worker chỉ từ exception ở manager.** Cần xem lại metadata trong `JobRepository`, log của worker và dữ liệu đích.

~~~text
T0: 16 partition được lên kế hoạch
T1: 4 worker chạy; 8 task xếp queue
T2: manager gửi partition13; pool từ chối do bão hòa
T3: một vài chunk của worker đang chạy có thể đã commit
T4: điều tra, dừng/đợi worker đúng quy trình, đọc JobRepository
T5: sửa nguyên nhân admission; restart cùng JobInstance
T6: đối soát business key và giá trị sau khi hoàn tất
~~~

**Cần nhớ:** queue của executor nằm trong bộ nhớ JVM, **không phải durable work queue**. JobRepository giữ metadata batch để hỗ trợ restart theo trạng thái StepExecution, nhưng việc những task nào còn trong queue ở thời điểm JVM chết **không phải trạng thái có thể khôi phục bằng cách đọc queue**.

### Nguyên tắc restart sau saturation

1. Không chỉnh sửa thủ công JobRepository để đánh dấu partition COMPLETED.
2. Bảo đảm worker cũ thật sự đã dừng hoặc không còn quyền ghi trước khi dispatch lại cùng partition.
3. Giữ tên partition, ranh giới, identifying JobParameters và snapshot đầu vào nhất quán.
4. Điều chỉnh executor/admission để tránh rejection lặp lại; cân nhắc giới hạn worker từ DB pool thực.
5. Dùng writer idempotent hoặc cơ chế dedup/compensation để bảo vệ khi chunk bị replay.
6. Đối soát dữ liệu thật theo business key, không chỉ `BatchStatus.COMPLETED`.

Nếu job dùng remote partitioning, có thêm các tình huống ACK thất lạc, worker chết và redelivery. Queue của `ThreadPoolTaskExecutor` dùng trong **local** TaskExecutorPartitionHandler không thay thế queue của message broker và không thể mô hình hóa mọi lỗi phân tán.

## 11. Chọn concurrency theo nguồn lực, không theo queue

Trong job dữ liệu lớn, năng lực chạy đồng thời thường bị giới hạn bởi **DB connection pool, lock, I/O, CPU hoặc API quota** trước khi bị giới hạn bởi queue task.

Ví dụ pool DB có 12 connection, hệ thống khác thường cần 4 connection và mỗi worker có thể cần đến hai connection cùng thời điểm tùy reader/writer/transaction. Không thể đơn giản đặt `maxPoolSize=12` rồi cho 12 worker: có nguy cơ connection starvation. Cần **đo connection đang sử dụng theo worker** và dành chỗ cho JobRepository, tác vụ ngoài batch và transaction metadata.

| Tài nguyên | Dấu hiệu quá tải | Cách điều chỉnh |
| --- | --- | --- |
| CPU | CPU bão hòa, context switching/GC tăng | Giảm active worker hoặc tối ưu processor |
| DB connection pool | Hikari active gần max, threads waiting, timeout | Giảm worker hoặc tăng pool khi DB thực sự có khả năng |
| DB lock/index | Lock wait/deadlock, commit latency tăng | Phân vùng tránh tranh record, tối ưu transaction/SQL |
| Disk/network | IOPS bão hòa, read latency tăng | Giảm worker, staging hợp lý, tận dụng sequential I/O |
| External API | HTTP 429, timeout, rate limit | Quota/concurrency per tenant hoặc circuit breaker |
| JobRepository | Metadata write contention, truy vấn execution chậm | Bớt partition rất nhỏ, tối ưu hạ tầng metadata |

Giới hạn queue nên **bộc lộ** saturation sớm và thúc đẩy admission hợp lý, nhưng không được xem nó là giải pháp trực tiếp để giảm số transaction đang chạy. Giới hạn transaction thực tế chủ yếu đến từ **số worker active và thiết kế reader/writer**.

## 12. Quan sát pool, queue và tình trạng partition

Trong Spring Framework, `ThreadPoolTaskExecutor` cung cấp các số đo như **activeCount**, **poolSize** và **queueSize**. Có thể tích hợp Micrometer/Actuator hoặc metric riêng để theo dõi:

~~~java
@Component
class PartitionPoolMetrics {
    private final ThreadPoolTaskExecutor executor;

    PartitionPoolMetrics(
            @Qualifier("partitionTaskExecutor")
            ThreadPoolTaskExecutor executor) {
        this.executor = executor;
    }

    Map<String, Integer> snapshot() {
        return Map.of(
                "activeThreads", executor.getActiveCount(),
                "poolThreads", executor.getPoolSize(),
                "queuedTasks", executor.getQueueSize());
    }
}
~~~

Đây là ví dụ lấy mẫu metric, **không phải mô hình dashboard hoàn chỉnh**. Hãy dùng metric với tên/tag phù hợp và không gắn tenant ID có cardinality quá lớn vào mọi time series nếu không có kế hoạch kiểm soát chi phí.

| Metric / tín hiệu | Ý nghĩa vận hành | Cảnh báo cần thiết |
| --- | --- | --- |
| `activeThreads` | Task thực thi trong pool tại một thời điểm | Gần max lâu nhưng throughput thấp |
| `queuedTasks` | Task đã nhận nhưng chưa chạy | Queue tăng liên tục hoặc gần capacity |
| `poolThreads` | Pool đã tạo bao nhiêu thread | Không vượt core dù queue dài vì cấu hình lớn |
| Rejected task count | Lỗi admission | **Bất kỳ rejection không dự kiến** đều cần điều tra |
| Partition start delay | Thời gian từ được giao đến khi bắt đầu xử lý | p95/p99 tăng, job bị queue chờ |
| StepExecution status | Partition nào COMPLETED/FAILED/STARTED | Worker có trạng thái treo hoặc retry quá mức |
| Read/write/commit/rollback | Tiến độ và kết quả từng partition | Đếm lệch, rollback bất thường |
| DB active/waiting connections | Downstream capacity | Pool cạn dù queue chưa đầy |
| Memory/GC/CPU | JVM có chịu được số task/worker? | Heap tăng, stop-the-world GC, CPU saturation |

**Lưu ý về telemetry:** executor không tự có một bộ đếm “đã từ chối tổng cộng” chuẩn cho mọi phiên bản. Có thể bọc `RejectedExecutionHandler` hoặc instrumentation khác để tăng counter trước khi ném lỗi. Đừng dựa riêng vào `getQueueSize()` để tính backlog toàn job, vì các partition chưa submit và trạng thái bền vững trong JobRepository không nằm trong số đó.

### Quan hệ giữa các trạng thái

~~~text
Tập partition của snapshot
  = đã hoàn tất + đang chạy + đang chờ executor
    + chưa submit + lỗi/chờ retry + các trạng thái khác

Phân loại phải bảo đảm không đếm một partition vào hai nhóm.
Queue size chỉ là một phần nhỏ của toàn bộ bức tranh.
~~~

Theo dõi **thời gian manager mất để submit** và **thời gian một worker nằm trong queue** nếu có admission gate. Queue luôn bằng 0 chưa chắc là tín hiệu tốt: có thể manager đang bị chặn ở semaphore, hoặc các worker bị nghẽn CPU/DB.

## 13. Kiểm thử đơn vị: queue bị bão hòa phải phát tín hiệu

Đừng kiểm tra saturation bằng `Thread.sleep` và phỏng đoán timing. Dùng `CountDownLatch` để giữ các worker bận, rồi gửi thêm task.

JUnit 5, giả định đã import JUnit assertions và Java concurrency:

~~~java
@Test
void boundedQueueRejectsWhenAllSlotsAreOccupied() throws Exception {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(1);
    executor.setThreadNamePrefix("queue-test-");
    executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
    executor.initialize();

    CountDownLatch started = new CountDownLatch(2);
    CountDownLatch release = new CountDownLatch(1);

    Runnable blockingWorker = () -> {
        started.countDown();
        try {
            if (!release.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test release timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    };

    try {
        executor.execute(blockingWorker);
        executor.execute(blockingWorker);

        // Hai worker chắc chắn đã chiếm hết thread pool.
        assertTrue(started.await(10, TimeUnit.SECONDS));

        executor.execute(() -> { /* task thứ ba nằm trong queue */ });
        assertEquals(1, executor.getQueueSize());

        // Task thứ tư bị từ chối, không bị bỏ lặng.
        assertThrows(TaskRejectedException.class,
                () -> executor.execute(() -> {}));
    } finally {
        release.countDown();
        executor.shutdown();
    }
}
~~~

**Điều test chứng minh:** khi pool có hai worker đang bận và một task đang chờ, lời gửi thứ tư bị từ chối bởi bounded queue và `AbortPolicy`. Test không chứng minh một JobRepository restart được, cũng không đo throughput.

Tùy phiên bản Spring, loại exception từ `ThreadPoolTaskExecutor.execute` được đóng gói thành `TaskRejectedException`; nếu kiểm thử tầng `java.util.concurrent.ThreadPoolExecutor` trực tiếp thì thường thấy `RejectedExecutionException`. Kiểm tra type tại **API mà ứng dụng đang dùng**, không bắt mọi `Exception` rồi coi là đúng.

### Negative test để phát hiện hiểu sai maxPoolSize

Đặt `core=2`, `max=8`, `queueCapacity=100`, gửi 20 worker đang chờ latch. Kiểm tra active threads tại điểm đồng bộ chỉ có thể đạt 2 khi queue chưa đầy. Test này phát hiện giả định sai rằng `maxPoolSize=8` luôn có tám thread đang làm việc.

## 14. Integration test cùng TaskExecutorPartitionHandler

Sau unit test executor, cần chạy **job thực** với `JobRepository`, `Partitioner` và worker step:

1. Chuẩn bị snapshot với 16 vùng dữ liệu không giao nhau, có tổng số item và checksum/giá trị mong đợi.
2. Cho Partitioner trả đúng 16 entry. Cấu hình `core=max=4`, `queueCapacity=12`, `gridSize=16`.
3. Dùng probe/latch tại worker để xác nhận tối đa bốn worker đồng thời, không có task thứ 17 ngoài kế hoạch và queue không vượt 12.
4. Mở latch, đợi JobExecution kết thúc rồi kiểm tra mọi worker StepExecution `COMPLETED` và tổng business output đúng.
5. Thử `queueCapacity=2` trên cấu hình **không có backpressure**, giữ worker bận; kiểm tra saturation được báo là lỗi chứ không âm thầm mất partition.
6. Thử admission gate hoặc điều phối theo đợt; kiểm chứng không có task rejection, không deadlock và mọi partition được xử lý.
7. Giả lập lỗi worker sau một số chunk commit; restart cùng JobInstance, đối soát không trùng dữ liệu.

### Probe đếm số worker đồng thời

~~~java
final class WorkerConcurrencyProbe {
    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    void enter() {
        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);
    }

    void exit() {
        active.decrementAndGet();
    }

    int peakActive() {
        return peak.get();
    }
}
~~~

Trong test worker, phải gọi `enter()`/ `exit()` bằng `try/finally`, tránh giữ bộ đếm sai khi task ném exception. Dùng latch hoặc barrier để tạo overlap, **không** kết luận concurrency chỉ từ tổng thời gian chạy. Probe này đếm worker đã vào đoạn được instrument, không tự đếm số transaction hoặc số connection DB.

### Test cần đối soát cái gì?

| Kết quả | Assertion |
| --- | --- |
| Điều phối | Số partition đã tạo, số StepExecution, trạng thái mỗi partition |
| Concurrency | `peakActive <= 4`; với workload và latch phù hợp có thể chứng minh `peakActive == 4` |
| Queue | `queueSize <= 12`; rejection không xảy ra trong ca bình thường |
| Dữ liệu | Tập business key/giá trị cuối khớp snapshot, không trùng/thiếu |
| Lỗi có chủ đích | Step/job phản ánh lỗi, không báo COMPLETED khi có partition chưa chạy |
| Restart | Giữ mapping partition và dữ liệu snapshot; replay không nhân đôi side effect |

Không dùng kết quả “queueSize lúc đo bằng 0” để chứng minh queue không từng đầy. Nếu cần, thu thập **high-water mark** của queue và counter rejection qua instrumentation trong toàn bộ vòng đời job.

## 15. Kiểm thử hiệu năng và capacity planning

Một ma trận thử nghiệm cho workload **64 partition**:

| Kịch bản | Core / Max | Queue | Admission | Quan sát |
| --- | --- | --- | --- | --- |
| A: tuần tự | 1 / 1 | 63 | Nhận toàn bộ | Baseline thời gian, DB load |
| B: bốn worker | 4 / 4 | 60 | Nhận toàn bộ | Throughput và connection wait |
| C: queue nhỏ, không gate | 4 / 4 | 8 | Không có | Rejection nếu worker không kịp hoàn tất |
| D: queue nhỏ, có gate | 4 / 4 | 4 | Giới hạn in-flight 4 | Không tích backlog lớn; đo thời gian manager chờ |
| E: tám worker | 8 / 8 | 56 | Nhận toàn bộ | CPU, DB lock, GC, throughput |

Các giá trị queue lớn trong A/B/E **chỉ để đối chiếu phương án đơn giản chấp nhận toàn bộ 64 partition**. Chúng không phải cấu hình mặc định được khuyên dùng nếu P lên hàng chục nghìn. Khi chạy test, giữ nguyên snapshot, logic processor/writer, transaction, phần cứng và tải ngoài hệ thống càng ổn định càng tốt.

### Tính throughput và thời gian đợi

Theo dõi:

- `itemsPerSecond = số item xử lý hợp lệ / thời gian thực thi` theo định nghĩa nghiệp vụ.
- `partitionQueueWait = workerStartTime - submitAcceptedTime` nếu có instrumentation đủ chính xác.
- `partitionDuration` theo từng StepExecution; chú ý **partition chậm nhất**.
- Thời gian manager bị chặn do admission, task rejection count, số permit đang dùng.
- Tổng thời gian job bao gồm **partition preparation, scheduling, worker processing, aggregation** và đối soát.

**Ví dụ:** bốn worker mỗi worker xử lý ổn định một partition trong 2 phút; với 64 partition gần đều, thời gian worker lý tưởng xấp xỉ 32 phút cộng overhead. Tăng queue từ 8 lên 60 **không giảm** 32 phút lý tưởng nếu số worker không đổi. Ngược lại, tăng worker lên tám có thể giảm thời gian nếu CPU/DB/IO còn dư; nếu DB pool đã cạn thì có thể chậm hơn.

## 16. Checklist khi queue đầy trong production

Khi thấy `TaskRejectedException` hoặc queue đạt capacity, đừng chỉ tăng queue ngay. Áp dụng quy trình:

1. **Xác định phạm vi:** JobExecution/manager StepExecution nào gặp lỗi, Partitioner trả bao nhiêu entry, executor dùng riêng hay chung.
2. **Đo tại thời điểm lỗi:** `core/max/queueCapacity`, active count, queue size, thời gian worker đang chạy và số job đồng thời.
3. **Phân biệt tốc độ submit và tốc độ xử lý:** manager có gửi toàn bộ một lượt hay có admission? Worker bị chậm do CPU, DB, disk, API hay lock?
4. **Kiểm tra những task đã nhận:** StepExecution nào đang chạy/đã commit và task nào chưa khởi động; không suy ra tất cả chưa xử lý.
5. **Ổn định hệ thống:** điều chỉnh concurrency/backpressure hoặc chia nhóm partition; không thay đổi mapping của JobInstance đang restart.
6. **Khôi phục an toàn:** chờ/dừng worker theo runbook, dùng JobRepository và writer idempotent để restart, đối soát data.
7. **Ngăn tái diễn:** cảnh báo high-water mark, rejection, queue wait, throughput và downstream saturation.

Không sửa dữ liệu trong bảng metadata của Spring Batch để “cho qua” một partition chưa chạy. Nếu lỗi admission xảy ra đồng thời với lỗi DB, cần xác định nguyên nhân gốc; việc tăng queue có thể chỉ trì hoãn sự cố tiếp theo.

## 17. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| Đặt max=16 nhưng chỉ có 2 worker chạy | Core=2, queue rất lớn nên pool chưa tăng vượt core | Cân nhắc core=max theo mục tiêu, đo active |
| TaskRejectedException khi P lớn | Queue nhỏ, handler submit nhanh hơn worker giải phóng slot | Giảm P, admission gate, handler theo đợt hoặc budget đúng |
| Job lâu nhưng queueSize gần 0 | Thread điều phối đang bị gate chặn; hoặc worker không có việc | Đo admission wait/StepExecution, không chỉ queue |
| Heap tăng dần với hàng chục nghìn partition | Queue/metadata/futures tích lũy, Partitioner quá mịn | Nhóm partition, giảm outstanding |
| Task mất mà không thấy lỗi | Dùng DiscardPolicy hoặc handler nuốt exception | Bỏ silent-discard, kiểm tra JobRepository/đối soát |
| Worker chạy ngay trên manager thread | CallerRunsPolicy kích hoạt | Rà soát ngữ cảnh, lock, tracing, dùng admission rõ ràng |
| Job đã bị từ chối task nhưng có dữ liệu đích | Partition khác đã commit trước rejection | Restart/idempotency và đối soát, không xóa bừa |
| Tăng queue nhưng throughput không tăng | Worker/DB là nút thắt | Tối ưu bottleneck thay vì nới queue |
| Pool DB cạn khi tăng worker | Chọn W theo số core mà bỏ qua connection/transaction | Đo active connection và dự phòng cho JobRepository |
| Không khôi phục được sau JVM crash | Tưởng queue của executor là durable queue | Dựa trên JobRepository, mapping bất biến, checkpoint và writer idempotent |
| Queue đầy chỉ khi nhiều job cùng chạy | Dùng shared TaskExecutor không có ngân sách toàn hệ thống | Executor chuyên dụng hoặc admission/quota chung |

## 18. Bài thực hành và tiêu chí hoàn thành

**Bài thực hành:** tạo một job có 32 partition không giao nhau, mỗi partition xử lý dữ liệu từ snapshot ổn định và ghi kết quả theo unique business key. Dùng local `TaskExecutorPartitionHandler` trên `ThreadPoolTaskExecutor`.

Thực hiện lần lượt:

1. **Đối chứng queue:** tạo pool `core=max=2`, `queueCapacity=1`; giữ hai task bằng latch và chứng minh task thứ tư bị từ chối với exception rõ ràng.
2. **Baseline job:** chạy 32 partition với pool bốn thread và queue 28; đo active worker, queue high-water mark, tổng thời gian, DB waiting connections.
3. **Tái hiện rejection:** giảm queue xuống 4, dùng latch giữ worker bận; xác minh manager không báo thành công khi còn partition chưa chạy.
4. **Bổ sung admission:** giảm số partition được submit cùng lúc bằng wrapper có permit hoặc handler theo đợt; chứng minh không rejection và không deadlock.
5. **Negative test CallerRunsPolicy:** bật chính sách này trong môi trường kiểm thử, ghi nhận thread name và xác nhận có thể phát sinh worker chạy ngoài pool.
6. **Failure/restart:** cho worker ném lỗi sau khi commit vài chunk, restart cùng JobInstance; xác nhận StepExecution và dữ liệu cuối chính xác.
7. **Performance:** thử bốn và tám worker trên cùng dataset, quan sát throughput, queue wait, DB pool, GC, CPU và thời gian partition chậm nhất.

### Checklist trước khi triển khai

- [ ] Partitioner trả số entry được biết/đo; `gridSize` không bị hiểu nhầm thành giới hạn executor.
- [ ] `corePoolSize`, `maxPoolSize`, `queueCapacity` và rejection handler được cấu hình rõ.
- [ ] Có chiến lược nhận task khi số partition lớn: nhóm, bounded admission hoặc chia đợt có lưu trạng thái.
- [ ] Không dùng DiscardPolicy/DiscardOldestPolicy để giấu saturation.
- [ ] CallerRunsPolicy (nếu chọn) đã được kiểm thử trên manager thread, transaction/context, shutdown và deadlock.
- [ ] Worker, reader, writer, DB pool và JobRepository được giới hạn theo năng lực thực.
- [ ] Snapshot, partition name, identifying JobParameters và checkpoint ổn định khi restart.
- [ ] Writer idempotent và mọi side effect ngoài transaction có khóa chống lặp tương ứng.
- [ ] Có metric active, queue, rejection, admission wait, StepExecution và downstream saturation.
- [ ] Có unit test saturation, integration test job, lỗi worker, restart và đối soát dữ liệu.

**Ghi nhớ:** `queueCapacity` là **ngưỡng số task chờ bên trong executor**, không phải “số partition có thể xử lý an toàn” và cũng không phải cơ chế backpressure tự động. Với TaskExecutorPartitionHandler, hãy phối hợp **số partition thực, giới hạn thread, queue bounded, chính sách rejection rõ ràng và admission có kiểm soát**. Đảm bảo đúng dữ liệu vẫn phụ thuộc StepExecution, snapshot ổn định, transaction và writer có thể replay an toàn; hiệu năng phải được xác nhận bằng số đo CPU/DB/I/O chứ không chỉ thay kích thước queue.
