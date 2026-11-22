# JobLauncher với TaskExecutor

Trong Spring Batch, `JobLauncher` là thành phần nhận yêu cầu khởi chạy một `Job` cùng bộ `JobParameters`. Cách thực thi job phụ thuộc vào `TaskExecutor` mà launcher sử dụng. Nếu dùng executor đồng bộ, job chạy ngay trên thread gọi `JobLauncher.run` và phương thức chỉ trả về sau khi job kết thúc. Nếu dùng executor bất đồng bộ, launcher gửi công việc sang một thread khác và có thể trả về `JobExecution` ngay sau khi tác vụ được tiếp nhận.

Kết hợp `JobLauncher` với `TaskExecutor` giúp ứng dụng điều khiển cách khởi chạy batch: chạy đồng bộ cho luồng đơn giản, hoặc chạy nền để request web, scheduler hay thành phần điều phối không phải chờ toàn bộ job hoàn thành. `TaskExecutor` chỉ quyết định job được thực thi trên thread nào; nó không tự làm cho các step bên trong job chạy song song.

## Vai trò của JobLauncher

`JobLauncher` cung cấp API khởi chạy job:

```java
JobExecution execution = jobLauncher.run(job, jobParameters);
```

Khi nhận lời gọi, launcher phối hợp với `JobRepository` để xác định `JobInstance`, kiểm tra lịch sử chạy và tạo `JobExecution` phù hợp. Sau đó launcher yêu cầu executor thực thi job. Repository lưu metadata về instance, execution, trạng thái và các thông tin cần cho restart.

Các trách nhiệm chính có thể tóm tắt như sau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `JobLauncher` | Nhận yêu cầu chạy job, xác thực điều kiện khởi chạy và tạo `JobExecution` thông qua repository |
| `JobRepository` | Lưu metadata, kiểm soát danh tính instance và lịch sử execution |
| `TaskExecutor` | Thực thi tác vụ job trên thread đồng bộ hoặc thread do executor quản lý |
| `Job` | Điều phối các step và luồng xử lý đã cấu hình |
| `JobExecution` | Đại diện cho một lần thực thi cụ thể và cung cấp trạng thái, thời điểm, exit status |

`JobLauncher` không tự định nghĩa cách chạy song song các step. Nó điều phối việc bắt đầu một lần thực thi job. Nếu cần nhiều step chạy đồng thời trong cùng một job, cần cấu hình flow song song, partitioning hoặc cơ chế concurrency phù hợp ở cấp step.

## TaskExecutor là gì?

`TaskExecutor` là abstraction của Spring để thực thi một `Runnable`. Nó tương tự khái niệm executor trong Java nhưng tích hợp với hệ sinh thái Spring. `TaskExecutorJobLauncher` dùng abstraction này để chạy job.

Các implementation thường gặp:

| Implementation | Cách hoạt động | Trường hợp sử dụng |
| --- | --- | --- |
| `SyncTaskExecutor` | Chạy task ngay trên thread gọi `execute` | Mặc định đồng bộ, test hoặc luồng đơn giản |
| `SimpleAsyncTaskExecutor` | Tạo thread mới cho mỗi task, có thể giới hạn concurrency | Ví dụ nhỏ hoặc tải thấp; cần kiểm soát số thread |
| `ThreadPoolTaskExecutor` | Tái sử dụng thread từ pool, có queue và giới hạn số thread | Ứng dụng production cần kiểm soát tài nguyên |
| `ConcurrentTaskExecutor` | Adapter cho một `java.util.concurrent.Executor` | Tích hợp executor Java đã có |

Một điểm cần nhớ là tên `TaskExecutor` không đồng nghĩa với bất đồng bộ. `SyncTaskExecutor` thực thi đồng bộ. Chỉ khi cấu hình một executor thực thi trên thread khác, ví dụ `ThreadPoolTaskExecutor`, lời gọi `JobLauncher.run` mới có hành vi trả về sớm theo kiểu chạy nền.

## Đồng bộ và bất đồng bộ

### Chạy đồng bộ

Với `SyncTaskExecutor`, job chạy trên thread hiện tại. Lời gọi `run` chỉ kết thúc khi quá trình thực thi job đã hoàn thành hoặc thất bại.

```text
Thread gọi
    |
    v
JobLauncher.run(job, parameters)
    |
    v
Job thực thi các step
    |
    v
Job hoàn thành hoặc thất bại
    |
    v
Trả JobExecution cho caller
```

Ưu điểm của cách chạy này là luồng điều khiển dễ hiểu: caller có thể nhận kết quả cuối cùng ngay sau khi `run` trả về. Nó phù hợp với command-line runner, batch nhỏ hoặc trường hợp thành phần gọi cần đợi kết quả để thực hiện bước tiếp theo.

Nhược điểm là thread gọi phải chờ. Nếu caller là thread xử lý HTTP request, request có thể giữ kết nối trong suốt thời gian job chạy. Một job kéo dài cũng có thể chiếm thread scheduler hoặc thread của thành phần điều phối.

### Chạy bất đồng bộ

Với executor như `ThreadPoolTaskExecutor`, launcher gửi công việc sang pool. Thread gọi có thể nhận `JobExecution` trước khi job hoàn tất.

```text
HTTP request / Scheduler thread
          |
          v
JobLauncher.run(job, parameters)
          |
          +----> JobRepository tạo JobExecution
          |
          +----> TaskExecutor nhận task
          |                 |
          v                 v
   Trả JobExecution     Worker thread
                            |
                            v
                       Job thực thi
                            |
                            v
                       Cập nhật trạng thái
                       trong JobRepository
```

Caller không phải chờ toàn bộ job. Nó có thể trả về mã `JobExecution` cho client, ghi nhận yêu cầu hoặc tiếp tục xử lý tác vụ khác. Trạng thái cuối cùng được cập nhật trong repository sau khi worker thực thi xong.

Ngay sau khi launcher trả về, `JobExecution` có thể vẫn ở trạng thái như `STARTING` hoặc `STARTED`. Không được xem việc nhận được đối tượng `JobExecution` là bằng chứng job đã hoàn thành. Muốn biết kết quả cuối cùng, cần tra cứu trạng thái sau đó qua `JobExplorer`, API quản trị hoặc cơ chế theo dõi tương đương.

## Cấu hình TaskExecutorJobLauncher

Trong các phiên bản Spring Batch hiện đại, `TaskExecutorJobLauncher` là implementation dùng `TaskExecutor` để thực thi job. Khi không chỉ định executor bất đồng bộ, launcher thường sử dụng executor đồng bộ. Để chạy job trên thread pool, cần cấu hình executor và gắn nó với launcher.

Ví dụ cấu hình với `ThreadPoolTaskExecutor`:

```java
@Configuration
public class BatchLauncherConfiguration {

    @Bean
    public ThreadPoolTaskExecutor batchJobTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("batch-job-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(60);
        return executor;
    }

    @Bean(name = "jobLauncher")
    public JobLauncher jobLauncher(
            JobRepository jobRepository,
            ThreadPoolTaskExecutor batchJobTaskExecutor) throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(batchJobTaskExecutor);
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

Trong ví dụ:

- `JobRepository` được cung cấp cho launcher để tạo và cập nhật metadata.
- `ThreadPoolTaskExecutor` quản lý worker thread thực thi job.
- `corePoolSize` là số thread cơ bản được duy trì trong pool.
- `maxPoolSize` giới hạn số thread tối đa khi pool cần mở rộng.
- `queueCapacity` giới hạn số task chờ trước khi pool mở rộng đến giới hạn hoặc từ chối task.
- `threadNamePrefix` giúp nhận diện worker trong log và thread dump.
- `waitForTasksToCompleteOnShutdown` cùng `awaitTerminationSeconds` hỗ trợ chờ task đang chạy khi ứng dụng tắt.

Đây là cấu hình minh họa cho ứng dụng tự quản lý launcher. Nếu Spring Boot đã tự cấu hình `JobLauncher`, cần kiểm tra cơ chế auto-configuration và điều kiện tạo bean của phiên bản đang dùng trước khi khai báo bean thay thế. Không nên vô tình tạo nhiều launcher với tên hoặc cấu hình khác nhau khiến các thành phần gọi sử dụng nhầm launcher.

API cấu hình có thể khác giữa các phiên bản Spring Batch. Các ví dụ cũ có thể dùng `SimpleJobLauncher`; trong những phiên bản mới, hãy ưu tiên implementation được tài liệu phiên bản dự án khuyến nghị, thường là `TaskExecutorJobLauncher`.

## Khởi chạy job từ ứng dụng

Sau khi cấu hình launcher, thành phần nghiệp vụ có thể inject `JobLauncher` và gọi `run` với bộ parameter phù hợp.

```java
@Service
public class SettlementJobService {

    private final JobLauncher jobLauncher;
    private final Job dailySettlementJob;

    public SettlementJobService(
            JobLauncher jobLauncher,
            Job dailySettlementJob) {
        this.jobLauncher = jobLauncher;
        this.dailySettlementJob = dailySettlementJob;
    }

    public JobExecution start(LocalDate businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate.toString(), true)
                .toJobParameters();

        return jobLauncher.run(dailySettlementJob, parameters);
    }
}
```

`businessDate` được đánh dấu identifying vì nó xác định đơn vị quyết toán logic. Nếu job chạy bất đồng bộ, method `start` thường trả về trước khi settlement hoàn tất. Caller có thể lấy `execution.getId()` để cung cấp mã tra cứu cho client hoặc lưu lại để theo dõi.

Không thêm một timestamp identifying mới cho mỗi lần gọi chỉ nhằm tránh lỗi khởi chạy trùng. Nếu cùng ngày nghiệp vụ đã có một execution đang chạy, repository cần nhận diện đó là cùng `JobInstance` và áp dụng quy tắc chống chạy trùng. Nếu cần một lần xử lý logic mới, hãy thêm parameter identifying có ý nghĩa nghiệp vụ rõ ràng.

## Theo dõi JobExecution sau khi launcher trả về

Khi dùng executor bất đồng bộ, caller thường chỉ nhận được thông tin lần chạy đã được tạo và gửi tới executor. Để biết job đã kết thúc chưa, có thể dùng `JobExplorer` tra cứu execution theo ID.

```java
@Service
public class BatchExecutionQueryService {

    private final JobExplorer jobExplorer;

    public BatchExecutionQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(Long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Ví dụ một API có thể trả về execution ID ngay sau khi khởi chạy:

```java
@RestController
@RequestMapping("/batch/settlements")
public class SettlementController {

    private final SettlementJobService jobService;

    public SettlementController(SettlementJobService jobService) {
        this.jobService = jobService;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> start(
            @RequestParam LocalDate businessDate) throws Exception {

        JobExecution execution = jobService.start(businessDate);

        return ResponseEntity.accepted().body(Map.of(
                "executionId", execution.getId(),
                "status", execution.getStatus().toString()
        ));
    }
}
```

HTTP `202 Accepted` thể hiện yêu cầu đã được tiếp nhận để xử lý nền. Giá trị `status` trong response chỉ là trạng thái tại thời điểm trả response; client cần gọi endpoint tra cứu trạng thái để biết kết quả cuối cùng. Một API production thường trả thêm URL theo dõi hoặc cung cấp endpoint GET nhận `executionId`.

Khi đọc trạng thái, nên truy vấn repository qua `JobExplorer` hoặc service quản trị thay vì giữ một đối tượng `JobExecution` trong bộ nhớ và giả định nó sẽ luôn phản ánh trạng thái mới nhất. Trong hệ thống nhiều node, database metadata là nguồn trạng thái dùng chung đáng tin cậy.

## Xử lý lỗi khi khởi chạy bất đồng bộ

Cần phân biệt lỗi xảy ra trong lúc tiếp nhận yêu cầu và lỗi xảy ra trong quá trình job thực thi.

### Lỗi trước khi task được tiếp nhận

Một số lỗi được phát hiện ngay trong thread gọi, ví dụ job không hợp lệ, parameter không phù hợp với instance hiện có, instance đã hoàn thành, execution đang chạy hoặc repository không tạo được execution. Executor cũng có thể từ chối task khi pool và queue đã đầy; với Spring executor, tình huống này thường được biểu diễn bằng `TaskRejectedException`.

Caller cần xử lý những lỗi này để trả phản hồi phù hợp, ghi log và thông báo rằng yêu cầu chưa được khởi chạy thành công. Không nên trả mã execution như thể task chắc chắn đã được tiếp nhận nếu lời gọi `run` ném exception.

### Lỗi trong worker thread

Sau khi task đã được gửi sang worker, lỗi trong reader, processor, writer hoặc step xảy ra ở thread thực thi. Spring Batch cập nhật trạng thái `JobExecution` và `StepExecution` theo kết quả thực thi. Caller ban đầu thường đã kết thúc request nên không thể nhận exception bất đồng bộ như một exception thông thường từ lời gọi `run`.

Ứng dụng cần theo dõi trạng thái cuối trong repository, ghi log có execution ID và cung cấp cơ chế thông báo hoặc giám sát nếu nghiệp vụ cần biết kết quả. Job thất bại thường được biểu diễn bằng `BatchStatus.FAILED` và exit status tương ứng trong metadata; không nên chỉ dựa vào HTTP response lúc khởi chạy.

Ví dụ xử lý lỗi tiếp nhận:

```java
try {
    JobExecution execution = jobLauncher.run(job, parameters);
    return execution.getId();
} catch (JobExecutionAlreadyRunningException ex) {
    // Cùng JobInstance đã có execution đang chạy.
    throw ex;
} catch (JobInstanceAlreadyCompleteException ex) {
    // Logical job này đã hoàn thành.
    throw ex;
} catch (JobParametersInvalidException ex) {
    // Bộ parameter không hợp lệ.
    throw ex;
} catch (TaskRejectedException ex) {
    // Executor không thể tiếp nhận thêm task tại thời điểm này.
    throw ex;
}
```

Các exception cụ thể có thể khác theo phiên bản API và cách bọc lỗi của ứng dụng. Trong thực tế nên xử lý ở lớp điều phối phù hợp, ghi nhận nguyên nhân và ánh xạ sang phản hồi nghiệp vụ dễ hiểu.

## Giới hạn concurrency và quản lý thread pool

`ThreadPoolTaskExecutor` giúp kiểm soát số job có thể chạy đồng thời trong một instance ứng dụng. Nếu pool có 4 worker thread, tối đa 4 task có thể được thực thi đồng thời trong pool đó; các task tiếp theo có thể chờ trong queue hoặc bị từ chối tùy cấu hình.

Các tham số quan trọng:

| Tham số | Ý nghĩa | Cần cân nhắc |
| --- | --- | --- |
| `corePoolSize` | Số worker thread cơ bản | Chọn theo số job cần chạy thường xuyên và tài nguyên máy |
| `maxPoolSize` | Số worker tối đa khi tải tăng | Giới hạn CPU, memory và connection pool của database |
| `queueCapacity` | Số task có thể chờ | Queue quá lớn có thể làm job chờ lâu và tiêu thụ bộ nhớ |
| `keepAliveSeconds` | Thời gian giữ thread vượt mức core khi nhàn rỗi | Hữu ích với tải tăng giảm theo thời điểm |
| Rejection policy | Cách xử lý khi pool và queue đều đầy | Phải có hành vi từ chối hoặc back-pressure rõ ràng |

Với `ThreadPoolTaskExecutor`, khi số worker đã đạt core size, task mới thường được đưa vào queue. Khi queue đầy, pool mới mở rộng tới max size; nếu cả pool lẫn queue đều đầy, task bị từ chối theo rejection policy. Vì vậy, tăng `maxPoolSize` không có nghĩa mọi task sẽ lập tức tạo thêm thread nếu queue vẫn còn chỗ.

Không nên cấu hình số worker chỉ dựa trên số CPU. Job thường tiêu thụ database connection, lock, bộ nhớ, file descriptor và tài nguyên của hệ thống ngoài. Nếu 20 job cùng chạy và mỗi job mở nhiều kết nối hoặc giữ transaction lâu, database có thể quá tải dù máy ứng dụng còn CPU.

Hãy chọn pool size dựa trên:

- Số job có thể chạy đồng thời theo yêu cầu nghiệp vụ.
- CPU và memory tiêu thụ của từng loại job.
- Connection pool và năng lực xử lý của database.
- Thời gian giữ transaction, lock và mức độ truy cập hệ thống ngoài.
- Số node triển khai; giới hạn concurrency ở mỗi node cần được nhân với số node để hiểu tải toàn hệ thống.

## Quan hệ giữa TaskExecutor và JobRepository

`TaskExecutor` điều khiển thread thực thi; `JobRepository` quản lý metadata và quy tắc định danh. Hai thành phần có vai trò khác nhau và cần phối hợp đúng.

Trong ứng dụng production, nhiều launcher hoặc nhiều node có thể cùng gửi yêu cầu chạy job. Các node nên dùng chung một `JobRepository` bền vững. Repository dùng transaction và các ràng buộc phù hợp để ngăn hai yêu cầu đồng thời tạo hoặc chạy xung đột cho cùng `JobInstance`.

Nếu cùng tên job và cùng identifying parameters, các lần gọi trỏ đến cùng logical job. Khi execution đang chạy, yêu cầu khác cho cùng instance thường bị từ chối với lỗi tương ứng như `JobExecutionAlreadyRunningException`. Nếu identifying parameters khác nhau, đó là các `JobInstance` khác và có thể chạy đồng thời nếu tài nguyên cùng cấu hình cho phép.

Executor không thay thế cơ chế khóa và transaction của repository. Chỉ giới hạn số thread trong một JVM không đủ để ngăn job trùng trên nhiều node hoặc nhiều ứng dụng khởi chạy độc lập.

## TaskExecutor không làm step tự động chạy song song

Đây là điểm dễ nhầm khi cấu hình `JobLauncher` với executor.

Khi launcher dùng `ThreadPoolTaskExecutor`, toàn bộ job được thực thi trên một worker thread do pool cấp. Bên trong job, các step vẫn chạy theo flow đã cấu hình, thường là tuần tự. Ví dụ:

```text
JobLauncher
    |
    v
Worker thread A
    |
    v
Step 1 -> Step 2 -> Step 3
```

Nếu muốn nhiều job khác nhau chạy đồng thời, có thể dùng một launcher với thread pool và khởi chạy các `JobInstance` độc lập. Nếu muốn nhiều step hoặc nhánh flow của cùng một job chạy song song, cần cấu hình `split` với executor hoặc cách xử lý song song khác được Spring Batch hỗ trợ. Nếu muốn chia dữ liệu lớn thành các phần chạy đồng thời, có thể dùng partitioning hoặc remote chunking.

Không nên tăng pool của `JobLauncher` với kỳ vọng một job đơn lẻ sẽ tự tăng tốc bằng cách chạy mọi step cùng lúc. Launcher pool kiểm soát concurrency giữa các lần thực thi job được gửi vào pool.

## Gọi JobLauncher từ web request hoặc scheduler

### Từ web request

Với job chạy lâu, mô hình bất đồng bộ thường phù hợp hơn: API nhận yêu cầu, tạo `JobExecution`, trả về ID và cung cấp endpoint tra cứu trạng thái. Client không cần giữ HTTP connection cho tới khi job kết thúc.

API nên xác thực quyền khởi chạy, kiểm tra input, xác định identifying parameters và xử lý yêu cầu trùng. Nếu có thể, hãy áp dụng idempotency key ở tầng API để hai request retry do timeout không vô tình tạo hai yêu cầu nghiệp vụ độc lập.

### Từ scheduler

Scheduler có thể gọi launcher để gửi job vào pool. Cần xác định rõ lịch chạy có cho phép các lần chạy chồng lấn hay không. Nếu job ngày hôm trước vẫn chạy khi lịch ngày hôm sau đến, ứng dụng cần quyết định có xếp hàng, bỏ qua, từ chối hay cho chạy song song với parameter khác.

Việc dùng executor bất đồng bộ không tự giải quyết lịch chạy chồng lấn. Cần kết hợp identifying parameters, repository dùng chung và chính sách scheduler phù hợp. Nếu scheduler có thể phát lại trigger sau lỗi, thiết kế job phải chịu được yêu cầu khởi chạy lặp.

## Context của thread và các thành phần phụ trợ

Khi task chuyển sang worker thread, các dữ liệu gắn với thread gọi không tự động được truyền sang thread mới. Ví dụ `ThreadLocal`, security context, MDC logging context, locale hoặc một số tracing context có thể không tồn tại trong worker.

Nếu job cần biết người dùng đã yêu cầu chạy, hãy truyền định danh cần thiết qua `JobParameters` hoặc một cơ chế context có kiểm soát. Không nên dựa vào HTTP request hoặc security context của thread gọi vì request có thể đã kết thúc khi job bắt đầu thực thi.

Với logging/tracing, có thể cấu hình `TaskDecorator` cho `ThreadPoolTaskExecutor` để sao chép các context cần thiết từ thread gửi task sang worker, đồng thời khôi phục trạng thái thread sau khi task hoàn tất. Chỉ truyền dữ liệu cần thiết và bảo đảm xóa context sau mỗi task để tránh rò rỉ thông tin giữa các job chạy trên cùng worker thread.

`@Async` và `@EnableAsync` là cơ chế xử lý bất đồng bộ ở tầng Spring method invocation. Chúng không phải điều kiện bắt buộc để `TaskExecutorJobLauncher` chạy job bất đồng bộ. Launcher đã trực tiếp sử dụng `TaskExecutor` được cấu hình. Tránh bọc thêm `@Async` quanh cùng lời gọi mà không có lý do rõ ràng, vì có thể tạo hai lớp executor, làm khó kiểm soát queue và lỗi.

## Tắt ứng dụng trong khi job đang chạy

Với executor chạy nền, job có thể còn hoạt động khi ứng dụng nhận tín hiệu shutdown. Nếu pool dừng ngay lập tức, worker có thể bị ngắt giữa quá trình xử lý. Cần cấu hình lifecycle và shutdown policy phù hợp với thời gian chạy job.

`waitForTasksToCompleteOnShutdown` cho phép executor chờ các task đã được tiếp nhận hoàn tất trong quá trình shutdown; `awaitTerminationSeconds` giới hạn thời gian chờ. Đây không phải bảo đảm tuyệt đối rằng mọi job sẽ hoàn thành: thời gian chờ có giới hạn, tiến trình có thể bị kill và lỗi hạ tầng vẫn có thể xảy ra.

Job dài cần có chiến lược restart và checkpoint đúng. Khi tiến trình dừng đột ngột, Spring Batch có thể cần phân tích trạng thái execution và khôi phục theo quy trình vận hành. Không nên đánh dấu job hoàn thành chỉ vì executor đã được shutdown hoặc task đã rời khỏi queue.

## Khi nào nên dùng TaskExecutor với JobLauncher?

| Nhu cầu | Cách cấu hình gợi ý |
| --- | --- |
| Job ngắn, caller cần kết quả ngay | `SyncTaskExecutor` hoặc launcher đồng bộ |
| API nhận yêu cầu cho job chạy lâu | `ThreadPoolTaskExecutor` và trả execution ID |
| Scheduler khởi chạy nhiều job độc lập | Thread pool có giới hạn và repository dùng chung |
| Tải thấp, ví dụ thử nghiệm | Executor đơn giản; vẫn kiểm soát số thread nếu chạy nền |
| Cần nhiều step chạy song song trong cùng job | Cấu hình parallel flow/step riêng; không chỉ đổi launcher executor |
| Cần xử lý nhiều partition | Cấu hình partition handler và executor ở cấp step |

Trước khi chọn bất đồng bộ, hãy xác định ai theo dõi trạng thái cuối, cách xử lý lỗi sau khi task được tiếp nhận, giới hạn concurrency và hành vi khi ứng dụng shutdown.

## Các lỗi thường gặp

### Gọi run nhưng job vẫn chạy trên request thread

Nguyên nhân thường là launcher đang dùng `SyncTaskExecutor` hoặc cấu hình auto-configuration vẫn là đồng bộ. Kiểm tra implementation launcher thực tế và bean `TaskExecutor` đã được gắn vào launcher hay chưa.

### API trả về STARTING hoặc STARTED

Đây là hành vi bình thường khi launcher chạy bất đồng bộ. Response được trả khi job mới được gửi tới executor; client cần tra cứu lại qua `JobExplorer` hoặc endpoint trạng thái.

### Task bị từ chối khi tải tăng

Pool và queue có thể đã đầy. Kiểm tra `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy và thời gian job chờ. Cần trả lỗi tiếp nhận phù hợp hoặc áp dụng back-pressure thay vì âm thầm bỏ yêu cầu.

### Hai request cùng khởi chạy một logical job

Nếu hai request có cùng tên job và identifying parameters, chúng cùng trỏ tới một `JobInstance`. Khi execution đã chạy, yêu cầu thứ hai thường bị repository từ chối. Kiểm tra identifying parameters và xử lý exception ở tầng API.

### Job thất bại nhưng request đã trả thành công

Response thành công chỉ thể hiện yêu cầu đã được tiếp nhận. Worker có thể gặp lỗi sau đó. Theo dõi `BatchStatus`, `ExitStatus`, log và metadata bằng `JobExplorer`; cung cấp cơ chế thông báo khi nghiệp vụ cần biết kết quả.

### Job chạy song song gây quá tải database

Pool có thể cho phép nhiều job cùng mở transaction hoặc đọc/ghi database. Giảm concurrency, tối ưu query, kiểm tra connection pool và lock contention. Không chỉ tăng số worker mà không đo tải database.

## Nguyên tắc triển khai

Khi đưa `JobLauncher` bất đồng bộ vào production, cần thống nhất các điểm sau:

1. Chọn executor rõ ràng; cấu hình pool, queue và rejection policy theo năng lực hệ thống.
2. Dùng `JobRepository` bền vững và dùng chung giữa các node liên quan.
3. Thiết kế identifying parameters để chống khởi chạy trùng và hỗ trợ restart.
4. Trả execution ID cho caller; cung cấp API hoặc cơ chế theo dõi trạng thái cuối.
5. Phân biệt lỗi tiếp nhận task với lỗi xảy ra trong worker thread.
6. Kiểm soát thread context, logging, tracing và security context khi cần truyền qua worker.
7. Cấu hình graceful shutdown và bảo đảm job có thể restart sau khi tiến trình dừng.
8. Đo concurrency cùng tải database, memory, CPU và các hệ thống ngoài.
9. Cấu hình parallel flow hoặc partitioning riêng nếu mục tiêu là song song bên trong một job.

## Ghi nhớ

`JobLauncher` nhận job và parameters, còn `TaskExecutor` quyết định cách thực thi tác vụ. Với `SyncTaskExecutor`, `run` chạy đồng bộ trên thread gọi. Với `ThreadPoolTaskExecutor`, job có thể chạy nền trên worker thread và launcher trả về `JobExecution` trước khi job hoàn thành. Khi đó, trạng thái cuối phải được theo dõi qua `JobRepository` hoặc `JobExplorer`, lỗi trong worker cần được quan sát qua metadata và log, còn lỗi tiếp nhận task phải được xử lý ngay tại caller. Thread pool cần giới hạn theo tài nguyên thực tế; executor của launcher điều khiển concurrency giữa các job, không tự làm các step trong một job chạy song song.
