# Khởi chạy đồng bộ và bất đồng bộ

Trong Spring Batch, `JobLauncher` là thành phần nhận một `Job` cùng `JobParameters` và yêu cầu framework thực thi Job. Cách Job được thực thi phụ thuộc vào `TaskExecutor` mà JobLauncher sử dụng. Với thực thi **đồng bộ**, luồng gọi `run()` cũng thực hiện Job và chỉ tiếp tục sau khi Job kết thúc. Với thực thi **bất đồng bộ**, Job được giao cho một luồng thực thi khác; lời gọi `run()` có thể trả về trong khi Job vẫn đang chạy.

Hai cách chạy có cùng mục tiêu là thực thi một Job và đều tạo metadata `JobExecution` trong `JobRepository`. Điểm khác nhau chủ yếu nằm ở luồng thực thi, thời gian lời gọi chờ đợi và cách ứng dụng theo dõi kết quả.

## 1. JobLauncher làm gì khi khởi chạy Job?

Ứng dụng không gọi trực tiếp các Step để tự quản lý toàn bộ vòng đời Job. Thay vào đó, ứng dụng truyền Job definition và tham số đầu vào cho `JobLauncher`:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);
```

Khi nhận yêu cầu, JobLauncher phối hợp với `JobRepository` để kiểm tra JobParameters, tìm hoặc tạo `JobInstance`, tạo `JobExecution` mới nếu yêu cầu hợp lệ, rồi giao công việc thực thi cho executor được cấu hình.

JobExecution ghi nhận lần chạy cụ thể: ID, JobInstance, thời điểm, `BatchStatus`, `ExitStatus` và các StepExecution. Metadata này cho phép ứng dụng theo dõi Job ngay cả khi luồng gọi ban đầu đã kết thúc hoặc ứng dụng cần tra cứu lịch sử chạy sau đó.

Luồng tổng quát:

```text
Ứng dụng
   |
   | JobLauncher.run(job, parameters)
   v
JobLauncher
   |
   +--> JobRepository: xác định JobInstance và tạo JobExecution
   |
   +--> TaskExecutor: thực thi Job
              |
              +--> Job và các Step
              |
              +--> Cập nhật trạng thái, ExitStatus và metadata
```

`TaskExecutor` quyết định tác vụ được chạy ngay trên luồng gọi hay được giao cho một luồng khác. Vì vậy, có thể thay đổi hành vi đồng bộ/bất đồng bộ mà không cần viết lại logic nghiệp vụ trong các Step.

## 2. Khởi chạy đồng bộ

Trong chế độ đồng bộ, `TaskExecutor` thực hiện tác vụ ngay trên luồng gọi. Spring Batch thường dùng `SyncTaskExecutor` cho cấu hình này. Khi ứng dụng gọi `JobLauncher.run()`, luồng gọi đi vào quá trình thực thi Job và chờ cho đến khi Job kết thúc.

```text
Luồng gọi
   |
   +--> JobLauncher.run()
          |
          +--> Tạo JobExecution
          |
          +--> Chạy Step 1
          |
          +--> Chạy Step 2
          |
          +--> Hoàn tất Job
   |
   +--> Nhận JobExecution sau khi Job kết thúc
   |
   +--> Tiếp tục xử lý
```

Ví dụ cấu hình JobLauncher sử dụng `SyncTaskExecutor`:

```java
@Bean
public JobLauncher jobLauncher(JobRepository jobRepository) throws Exception {
    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(new SyncTaskExecutor());
    launcher.afterPropertiesSet();
    return launcher;
}
```

Với launcher này, đoạn gọi sau chỉ tiếp tục khi Job đã hoàn tất:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);

if (execution.getStatus() == BatchStatus.COMPLETED) {
    log.info("Import completed: executionId={}", execution.getId());
} else {
    log.warn("Import ended with status={}", execution.getStatus());
}
```

Nếu Job mất vài phút để xử lý, luồng gọi cũng bị giữ trong khoảng thời gian đó. Với một ứng dụng web, request thread có thể bị chiếm dụng cho đến khi Job kết thúc.

### Khi nào nên dùng đồng bộ?

Đồng bộ phù hợp khi Job ngắn, kết quả cần có ngay để hoàn thành một thao tác, hoặc ứng dụng chủ động muốn luồng gọi chờ kết quả. Ví dụ, một bước nhập dữ liệu nhỏ trong công cụ nội bộ có thể chạy đồng bộ để người gọi nhận trạng thái cuối cùng ngay trong cùng lời gọi.

Ưu điểm là luồng điều khiển đơn giản: sau `run()`, ứng dụng có thể đọc trạng thái cuối cùng và tiếp tục theo kết quả. Việc xử lý lỗi và ghi log cũng dễ gắn với luồng gọi.

Hạn chế là thời gian chờ của caller tăng theo thời gian chạy Job. Nếu caller là HTTP request, cần cân nhắc timeout của gateway, web server và client. Nếu Job kéo dài hoặc có thể chạy song song nhiều lần, việc giữ request thread trong thời gian dài sẽ làm giảm khả năng phục vụ request khác.

## 3. Khởi chạy bất đồng bộ

Trong chế độ bất đồng bộ, JobLauncher giao tác vụ cho một `TaskExecutor` chạy ở luồng khác. Lời gọi `run()` có thể trả về sau khi tác vụ được chấp nhận và lên lịch, trong khi các Step vẫn đang thực thi.

```text
Luồng request / caller                 Luồng batch
       |                                   |
       +--> JobLauncher.run()              |
       |       |                           |
       |       +--> Tạo JobExecution       |
       |       +--> Giao tác vụ ---------->+
       |                                   +--> Chạy Step 1
       +<-- Nhận JobExecution              +--> Chạy Step 2
       |                                   +--> Cập nhật kết quả
       +--> Trả response / tiếp tục        |
                                           v
                                      Job kết thúc
```

Ví dụ cấu hình `TaskExecutorJobLauncher` với `ThreadPoolTaskExecutor`:

```java
@Bean
public ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("batch-");
    return executor;
}

@Bean
public JobLauncher jobLauncher(
        JobRepository jobRepository,
        ThreadPoolTaskExecutor batchTaskExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(batchTaskExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
```

`ThreadPoolTaskExecutor` quản lý một nhóm luồng có thể tái sử dụng. `corePoolSize`, `maxPoolSize` và `queueCapacity` giúp kiểm soát số tác vụ chạy đồng thời và số tác vụ chờ trong hàng đợi. Tên luồng `batch-` cũng giúp nhận diện log của các tác vụ batch.

Sau khi gọi launcher, ứng dụng nên giữ ID của JobExecution để theo dõi:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);

Long executionId = execution.getId();
log.info("Job accepted for execution, id={}", executionId);
```

Trong ví dụ trên, log nên diễn đạt rằng yêu cầu đã được khởi chạy hoặc tiếp nhận. Không nên log rằng Job đã hoàn tất chỉ vì phương thức `run()` đã trả về.

### Khi nào nên dùng bất đồng bộ?

Bất đồng bộ phù hợp với Job chạy lâu, được khởi động từ API hoặc giao diện người dùng, được kích hoạt theo lịch, hoặc cần thực thi nhiều Job mà không giữ luồng gọi chờ đợi. Ví dụ, API nhận yêu cầu nhập một file lớn có thể trả về execution ID để client truy vấn trạng thái sau đó.

Ưu điểm là caller có thể tiếp tục công việc khác trong khi Job chạy. Hạn chế là ứng dụng phải có cơ chế theo dõi trạng thái, xử lý lỗi, giới hạn concurrency và thông báo kết quả khi Job kết thúc.

## 4. So sánh đồng bộ và bất đồng bộ

| Tiêu chí | Đồng bộ | Bất đồng bộ |
|---|---|---|
| Luồng thực thi | Cùng luồng gọi `run()` | Luồng do TaskExecutor quản lý |
| Thời điểm `run()` trả về | Thường sau khi Job kết thúc | Có thể ngay sau khi tác vụ được giao/lên lịch |
| Trạng thái khi nhận kết quả | Thường là trạng thái cuối cùng | Có thể vẫn là `STARTING` hoặc `STARTED` |
| Caller có phải chờ Job? | Có | Không cần chờ Job hoàn tất |
| Theo dõi tiến trình | Có thể đọc kết quả ngay sau lời gọi | Thường cần truy vấn JobRepository/JobExplorer hoặc cơ chế thông báo |
| Tài nguyên | Chiếm luồng gọi trong suốt thời gian chạy | Chiếm luồng worker trong lúc chạy; caller được giải phóng |
| Trường hợp phù hợp | Job ngắn, cần kết quả ngay | Job dài, API, scheduler, xử lý nền |

Cả hai chế độ đều sử dụng `JobExecution` và `JobRepository`. Khác biệt không nằm ở định nghĩa Job hay dữ liệu nghiệp vụ, mà nằm ở cách tác vụ được thực thi và thời điểm caller nhận quyền điều khiển trở lại.

## 5. TaskExecutor quyết định cách thực thi

Spring Batch dùng abstraction `TaskExecutor` của Spring để quyết định tác vụ chạy ở đâu. Một số implementation thường gặp:

| TaskExecutor | Hành vi | Khi sử dụng |
|---|---|---|
| `SyncTaskExecutor` | Chạy ngay trên luồng gọi | Muốn thực thi đồng bộ, dễ theo dõi |
| `SimpleAsyncTaskExecutor` | Tạo luồng mới cho từng tác vụ; không tái sử dụng thread pool | Tác vụ nền đơn giản, số lượng được kiểm soát |
| `ThreadPoolTaskExecutor` | Dùng thread pool, có giới hạn luồng và hàng đợi | Ứng dụng cần kiểm soát concurrency và tài nguyên |

Không nên chọn executor chỉ dựa vào việc muốn “chạy nhanh hơn”. Executor bất đồng bộ có thể làm nhiều Job chạy cùng lúc, khiến tải lên database, file system hoặc dịch vụ bên ngoài tăng. Cần cấu hình giới hạn phù hợp với năng lực hệ thống.

Với `ThreadPoolTaskExecutor`, cần cân nhắc:

- Số Job có thể chạy đồng thời và số luồng tối đa.
- Dung lượng hàng đợi khi tất cả worker đang bận.
- Chính sách khi hàng đợi đầy hoặc executor đã shutdown.
- Thời gian shutdown và cách ứng dụng xử lý Job còn đang chạy khi dừng.
- Tài nguyên dùng chung như connection pool, API rate limit và dung lượng bộ nhớ.

Nếu cấu hình một pool quá lớn, nhiều Job có thể cùng tranh chấp database connection hoặc tài nguyên I/O. Nếu pool quá nhỏ hoặc hàng đợi quá dài, yêu cầu chạy có thể phải chờ lâu trước khi bắt đầu. Hãy đo tải thực tế và đặt giới hạn có chủ đích.

## 6. Đọc trạng thái khi Job chạy bất đồng bộ

Trong chế độ bất đồng bộ, đối tượng `JobExecution` trả về từ `run()` có thể chưa chứa trạng thái cuối cùng. Tùy thời điểm executor bắt đầu thực thi, trạng thái quan sát được có thể là `STARTING` hoặc `STARTED`. `endTime` cũng chưa có khi Job chưa kết thúc.

Ứng dụng có thể dùng `JobExplorer` để đọc metadata mới nhất theo execution ID:

```java
JobExecution latest = jobExplorer.getJobExecution(executionId);

if (latest != null) {
    BatchStatus status = latest.getStatus();

    if (status == BatchStatus.COMPLETED) {
        log.info("Job completed: {}", executionId);
    } else if (status == BatchStatus.FAILED) {
        log.error("Job failed: {}", executionId);
    } else {
        log.info("Job is still in progress: status={}", status);
    }
}
```

`JobExplorer` là API đọc metadata của JobRepository. Nó phù hợp cho endpoint truy vấn trạng thái, dashboard vận hành hoặc tác vụ giám sát. Nếu cần đọc trạng thái mới nhất, hãy truy vấn lại thay vì giữ một object cũ và giả định object đó luôn phản ánh mọi cập nhật được ghi bởi luồng thực thi khác.

Không nên tạo vòng lặp polling liên tục với tần suất quá cao. Có thể giới hạn tần suất truy vấn, dùng cơ chế thông báo khi Job kết thúc hoặc xây dựng một endpoint trạng thái để client chủ động kiểm tra theo khoảng thời gian hợp lý.

## 7. Thiết kế API khởi chạy Job bất đồng bộ

Một API khởi chạy Job dài thường không nên giữ kết nối HTTP đến khi toàn bộ dữ liệu được xử lý. Thay vào đó, API xác nhận yêu cầu đã được tiếp nhận và trả về ID để client truy vấn tiến trình.

Ví dụ minh họa service:

```java
@Service
public class BatchJobService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchJobService(JobLauncher jobLauncher, Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public Long startImport(String businessDate, String inputFile)
            throws JobExecutionException {

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("inputFile", inputFile, true)
                .toJobParameters();

        JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
        return execution.getId();
    }
}
```

Controller có thể trả về HTTP `202 Accepted` cùng execution ID:

```java
@RestController
@RequestMapping("/batch/imports")
public class ImportController {

    private final BatchJobService batchJobService;

    public ImportController(BatchJobService batchJobService) {
        this.batchJobService = batchJobService;
    }

    @PostMapping
    public ResponseEntity<Map<String, Object>> startImport(
            @RequestParam String businessDate,
            @RequestParam String inputFile) throws JobExecutionException {

        Long executionId = batchJobService.startImport(businessDate, inputFile);

        return ResponseEntity.accepted().body(Map.of(
                "executionId", executionId,
                "statusUrl", "/batch/imports/" + executionId
        ));
    }
}
```

Một endpoint GET riêng có thể dùng `JobExplorer` để trả về trạng thái hiện tại. Response `202 Accepted` có nghĩa yêu cầu đã được tiếp nhận để xử lý; nó không có nghĩa Job đã hoàn tất thành công.

Trong hệ thống thực tế, cần xác thực người gọi, kiểm tra quyền truy cập execution ID và giới hạn việc khởi chạy trùng lặp. Không nên cho phép người dùng tra cứu tùy ý JobExecution của người khác chỉ bằng cách đoán ID.

## 8. Phân biệt lỗi khởi chạy và lỗi trong quá trình thực thi

Khi gọi `JobLauncher.run()`, cần phân biệt hai nhóm lỗi:

**Lỗi khiến yêu cầu không thể khởi chạy hợp lệ:** ví dụ JobParameters không hợp lệ, JobInstance đã hoàn tất, một execution của JobInstance vẫn đang chạy, hoặc Job không cho phép restart. Các trường hợp này có thể được biểu diễn bằng exception như `JobParametersInvalidException`, `JobInstanceAlreadyCompleteException`, `JobExecutionAlreadyRunningException` hoặc `JobRestartException`.

**Lỗi phát sinh trong quá trình Job thực thi:** ví dụ không đọc được file, lỗi ghi database hoặc lỗi từ một dịch vụ bên ngoài. Những lỗi này thường được phản ánh qua `BatchStatus.FAILED`, `ExitStatus` và metadata exception của JobExecution. Trong chế độ đồng bộ, caller thường nhận được JobExecution sau khi Job kết thúc với trạng thái thất bại. Trong chế độ bất đồng bộ, caller có thể đã nhận JobExecution ban đầu trước khi lỗi xảy ra; cần truy vấn metadata sau đó để biết kết quả.

Ngoài ra, executor có thể từ chối nhận tác vụ nếu đã shutdown hoặc không thể tiếp nhận thêm công việc. Đây là lỗi ở bước giao tác vụ và cần được xử lý riêng trong vận hành.

Ví dụ xử lý các exception khởi chạy:

```java
try {
    JobExecution execution = jobLauncher.run(importOrdersJob, jobParameters);
    log.info("executionId={}, status={}", execution.getId(), execution.getStatus());
} catch (JobExecutionAlreadyRunningException ex) {
    log.warn("This JobInstance is already running", ex);
} catch (JobInstanceAlreadyCompleteException ex) {
    log.info("This JobInstance has already completed", ex);
} catch (JobParametersInvalidException | JobRestartException ex) {
    log.error("Job could not be launched", ex);
}
```

Các exception cụ thể có thể được gom hoặc chuyển thành response phù hợp ở tầng API. Dù xử lý theo cách nào, cần phân biệt lỗi yêu cầu khởi chạy với trạng thái FAILED của một execution đã bắt đầu.

## 9. JobParameters và khởi chạy đồng thời

JobParameters tham gia xác định JobInstance nếu được đánh dấu identifying. Khi hai yêu cầu dùng cùng Job và cùng identifying parameters, chúng hướng đến cùng một JobInstance. Spring Batch không cho phép hai JobExecution cùng chạy đồng thời trên cùng một JobInstance theo cách thông thường; JobRepository kiểm tra trạng thái và có thể từ chối yêu cầu thứ hai bằng `JobExecutionAlreadyRunningException`.

Nếu ứng dụng cần xử lý hai tập dữ liệu nghiệp vụ khác nhau song song, mỗi yêu cầu cần có tham số identifying phù hợp để đại diện cho JobInstance khác nhau. Ví dụ, hai ngày nghiệp vụ khác nhau có thể tạo hai JobInstance riêng. Không nên thêm một timestamp ngẫu nhiên vào mọi lần chạy chỉ để tránh exception, vì làm vậy có thể vô tình tạo nhiều JobInstance cho cùng một công việc nghiệp vụ và phá vỡ khả năng restart.

Trong môi trường nhiều application instance, JobRepository và database cần được cấu hình để phối hợp việc tạo execution và kiểm soát khởi chạy trùng. Không dựa vào một biến boolean hoặc bộ nhớ cục bộ của một server để ngăn hai server chạy cùng một JobInstance.

## 10. Context và transaction khi chạy bất đồng bộ

Khi Job được chuyển sang worker thread, luồng thực thi không mặc nhiên kế thừa mọi trạng thái gắn với request thread. Ví dụ, transaction đang mở ở controller, thông tin bảo mật trong thread-local hoặc MDC dùng cho logging không tự động được truyền sang luồng batch.

Vì vậy:

- Truyền dữ liệu đầu vào cần thiết qua `JobParameters` hoặc lưu ở một kho dữ liệu có thể truy cập từ worker.
- Để các Step quản lý transaction của chính chúng theo cấu hình Spring Batch; không dựa vào transaction của HTTP request để bao bọc một Job bất đồng bộ.
- Nếu cần thông tin người khởi chạy, hãy lưu một định danh phù hợp trong JobParameters hoặc metadata nghiệp vụ và kiểm soát dữ liệu nhạy cảm.
- Nếu cần truyền SecurityContext, tracing context hoặc MDC, hãy cấu hình cơ chế propagation rõ ràng cho executor; không giả định các thread-local tự được sao chép.
- Đảm bảo các bean và component dùng chung trong Job an toàn khi có nhiều execution đồng thời. Tránh lưu trạng thái riêng của một lần chạy trong mutable field của singleton bean.

Những điểm này đặc biệt quan trọng khi chuyển một Job vốn chạy đồng bộ sang bất đồng bộ: code có thể vẫn biên dịch và chạy, nhưng giả định về transaction, thread-local hoặc dữ liệu trong bộ nhớ có thể không còn đúng.

## 11. Cấu hình theo phiên bản và môi trường ứng dụng

Tên class triển khai JobLauncher và cách Spring Boot tự cấu hình có thể khác nhau theo phiên bản Spring Batch. Trong các phiên bản hiện đại, `TaskExecutorJobLauncher` là implementation sử dụng `TaskExecutor`; các dự án cũ có thể gặp `SimpleJobLauncher`. Hãy dùng implementation và API phù hợp với phiên bản dependency của dự án.

Trong ứng dụng Spring Boot, framework có thể tự cấu hình JobLauncher và các thành phần batch. Nếu cần thay đổi executor, hãy kiểm tra cấu hình hiện có trước khi khai báo bean thay thế để tránh tạo hai launcher hoặc làm mất các thiết lập repository mà ứng dụng đang sử dụng.

Một số điểm cần xác nhận khi cấu hình:

- JobRepository được dùng bởi JobLauncher phải là repository mà các Job và Step của ứng dụng sử dụng.
- Executor cần được quản lý vòng đời bởi Spring để có thể shutdown đúng cách.
- Kích thước pool cần phù hợp với giới hạn database connection và tài nguyên downstream.
- Cần xác định hành vi khi ứng dụng shutdown trong lúc Job đang chạy, gồm chờ hoàn tất, dừng có kiểm soát hoặc cho phép restart sau khi khởi động lại.
- Với nhiều instance ứng dụng, metadata repository phải được chia sẻ và cấu hình phù hợp cho concurrency.

## 12. Những nhầm lẫn thường gặp

**Cho rằng bất đồng bộ làm Job xử lý nhanh hơn.** Bất đồng bộ giải phóng caller và cho phép quản lý nhiều tác vụ, nhưng không tự làm một Step xử lý nhanh hơn. Hiệu năng phụ thuộc reader, processor, writer, database, I/O và mức song song thực tế.

**Cho rằng `run()` trả về nghĩa là Job đã hoàn tất.** Điều này thường đúng với executor đồng bộ, nhưng không đúng với executor bất đồng bộ. Hãy xem trạng thái JobExecution và truy vấn metadata mới nhất.

**Dùng số luồng quá lớn để tăng throughput.** Quá nhiều Job đồng thời có thể làm cạn connection pool, tăng tranh chấp và gây quá tải dịch vụ bên ngoài. Hãy giới hạn concurrency theo năng lực hệ thống.

**Không xử lý JobExecutionAlreadyRunningException.** Hai yêu cầu có cùng identifying parameters có thể nhắm đến cùng JobInstance. Ứng dụng cần quyết định có báo đang chạy, từ chối yêu cầu trùng hay xếp lịch theo nghiệp vụ.

**Giả định transaction của request áp dụng cho Job bất đồng bộ.** Worker thread thực thi độc lập với request thread. Transaction của Job/Step phải được cấu hình ở chính luồng batch.

**Không có cách xem trạng thái sau khi trả response.** Khi dùng bất đồng bộ, hãy lưu execution ID và cung cấp API hoặc màn hình tra cứu bằng JobExplorer/JobRepository.

## 13. Chọn chế độ khởi chạy phù hợp

Dùng đồng bộ khi Job ngắn và caller cần kết quả ngay trong cùng lời gọi. Dùng bất đồng bộ khi Job dài, được kích hoạt qua API hoặc scheduler, hoặc cần giải phóng caller trong lúc xử lý. Với bất đồng bộ, cần thiết kế thêm cách theo dõi trạng thái, xử lý yêu cầu trùng, giới hạn số Job đồng thời và quản lý shutdown.

Trong cả hai chế độ, `JobLauncher` vẫn khởi chạy cùng Job definition, `JobRepository` vẫn quản lý JobInstance và JobExecution, còn các Step vẫn thực hiện logic nghiệp vụ. Hiểu rõ vai trò của `TaskExecutor` giúp lựa chọn thời điểm caller chờ đợi và tổ chức tài nguyên thực thi phù hợp với yêu cầu ứng dụng.
