# Tasklet cho thao tác một lần

Trong Spring Batch, `Tasklet` phù hợp với một Step thực hiện một hành động độc lập, có thể hoàn tất trong một lần gọi, chẳng hạn xóa dữ liệu tạm, gọi stored procedure, kiểm tra điều kiện, chuẩn bị tài nguyên hoặc di chuyển một tệp. Với kiểu công việc này, ứng dụng không cần xây dựng pipeline đọc, xử lý và ghi từng item như chunk-oriented processing.

Tasklet thường trả về `RepeatStatus.FINISHED` sau khi thao tác hoàn tất. Kết quả này báo cho Spring Batch rằng không cần gọi lại Tasklet trong Step hiện tại. Đây là ý nghĩa của “thao tác một lần”: một lần thực thi logic của Step có thể hoàn tất bằng một lần gọi `execute`. Nó không có nghĩa hành động sẽ chỉ xảy ra đúng một lần trong toàn bộ vòng đời ứng dụng; Job có thể được khởi chạy bằng JobInstance mới hoặc Step có thể được chạy lại khi restart theo chính sách đã cấu hình.

## 1. Tasklet là gì?

`Tasklet` là interface Spring Batch dùng để biểu diễn một đơn vị công việc. Hợp đồng chính có dạng:

```java
public interface Tasklet {
    RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception;
}
```

Phương thức `execute` nhận hai đối tượng ngữ cảnh:

- `StepContribution` cho phép Tasklet truy cập thông tin của lần thực thi Step và đóng góp một số thông tin như bộ đếm hoặc trạng thái contribution.
- `ChunkContext` cung cấp ngữ cảnh của lần gọi, bao gồm `StepContext`, `StepExecution` và các thuộc tính liên quan.

Tasklet không yêu cầu `ItemReader`, `ItemProcessor` hoặc `ItemWriter`. Logic của thao tác được đặt trong `execute` hoặc được ủy quyền cho một service chuyên trách.

## 2. RepeatStatus.FINISHED biểu thị thao tác đã hoàn tất

Với Tasklet thực hiện một hành động độc lập, thông thường phương thức `execute` trả về `RepeatStatus.FINISHED` sau khi hành động thành công:

```java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        CleanupService cleanupService) {

    return new StepBuilder("cleanupStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                cleanupService.deleteTemporaryData();
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Trong ví dụ, Step gọi service dọn dữ liệu tạm một lần. Khi service kết thúc bình thường, Tasklet trả về `FINISHED` và Step có thể kết thúc thành công.

Nếu `execute` ném exception, Spring Batch xem lần thực thi Step là lỗi và xử lý theo cơ chế transaction, trạng thái và chính sách lỗi của Step. Không nên bắt exception rồi vẫn trả về `FINISHED` nếu thao tác thực tế chưa hoàn tất; điều đó có thể khiến Job báo thành công dù công việc bị bỏ dở.

## 3. TaskletStep gọi Tasklet như thế nào?

Khi một Tasklet được gắn vào Step bằng `.tasklet(...)`, Spring Batch tạo một Tasklet-oriented Step. Trong quá trình chạy, framework gọi `execute` và xem `RepeatStatus` để quyết định có tiếp tục lặp hay không:

```text
TaskletStep bắt đầu
       |
       v
Mở transaction
       |
       v
Tasklet.execute(...)
       |
       +-- FINISHED ------> Hoàn tất Step
       |
       +-- CONTINUABLE --> Gọi lại Tasklet
       |
       +-- Exception ----> Rollback theo transaction
                            và xử lý Step failure
```

Với thao tác một lần, trả `FINISHED` là cách thông thường. `RepeatStatus.CONTINUABLE` có nghĩa Tasklet còn công việc cần thực hiện và Spring Batch sẽ gọi lại `execute` trong vòng lặp của Step.

Mỗi lần gọi Tasklet được thực hiện trong transaction do Step cấu hình. Vì vậy, nếu Tasklet trả `CONTINUABLE`, các lần gọi có thể có ranh giới transaction riêng. Với thao tác một lần, điều này thường có nghĩa một lần gọi thực hiện công việc và kết thúc; nếu cần nhiều lượt, hãy xác định rõ checkpoint và khả năng chạy lại.

## 4. Khi nào nên dùng Tasklet cho thao tác một lần?

Tasklet phù hợp khi công việc có thể được mô tả như một hành động có đầu vào và kết quả ở cấp tác vụ, không cần xử lý riêng từng item.

### Dọn dữ liệu tạm

Trước khi import dữ liệu mới, ứng dụng có thể cần xóa dữ liệu staging cũ hoặc các bản ghi tạm đã hết hạn. Nếu thao tác là một câu SQL hoặc lời gọi service độc lập, Tasklet là lựa chọn tự nhiên.

```java
@Bean
Step clearStagingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("clearStagingStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("DELETE FROM order_staging");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Đây là ví dụ minh họa; câu SQL thực tế cần có điều kiện phù hợp để chỉ xóa dữ liệu thuộc batch hoặc phạm vi được phép. Nếu bảng rất lớn hoặc thao tác xóa tạo transaction dài, cần cân nhắc chiến lược xóa theo phân đoạn, partition hoặc cơ chế database phù hợp.

### Gọi stored procedure

Nếu database đã có stored procedure xử lý một tác vụ tổng hợp hoặc cập nhật tập dữ liệu, Tasklet có thể gọi procedure một lần:

```java
@Bean
Step refreshSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcTemplate jdbcTemplate) {

    return new StepBuilder("refreshSummaryStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                jdbcTemplate.update("call refresh_daily_summary()");
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Cú pháp gọi procedure phụ thuộc hệ quản trị cơ sở dữ liệu và cách khai báo procedure. Nếu procedure trả về tham số output hoặc kết quả phức tạp, có thể dùng `SimpleJdbcCall` hoặc JDBC API phù hợp.

### Kiểm tra điều kiện trước khi xử lý

Một Step có thể xác nhận tệp đầu vào tồn tại, kiểm tra một batch đang ở trạng thái được phép xử lý hoặc kiểm tra một điều kiện nghiệp vụ chung. Nếu điều kiện không đạt, Tasklet có thể ném exception phù hợp để Job dừng ở Step đó.

```java
@Bean
Step verifyInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        InputFileService inputFileService) {

    return new StepBuilder("verifyInputStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                if (!inputFileService.isReady()) {
                    throw new IllegalStateException("Input file is not ready");
                }
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Nếu kiểm tra chỉ xác nhận một điều kiện nhanh, Tasklet phù hợp. Nếu cần kiểm tra hàng triệu bản ghi hoặc phân tích từng dòng dữ liệu, nên dùng chunk processing hoặc một bước kiểm tra chuyên biệt theo tập dữ liệu.

### Chuẩn bị hoặc giải phóng tài nguyên

Tasklet có thể tạo thư mục, khởi tạo một bảng staging, chuẩn bị một manifest, đóng một tài nguyên hoặc dọn các file trung gian. Những thao tác này thường không cần pipeline item.

### Di chuyển hoặc archive một tệp

Sau khi một Step import hoàn tất, Tasklet cuối Job có thể chuyển tệp đầu vào sang thư mục archive hoặc đổi tên tệp để đánh dấu đã xử lý. Thao tác này thường được mô tả như một hành động đơn lẻ.

Khi làm việc với filesystem, cần tính đến trường hợp file đã được chuyển nhưng tiến trình dừng trước khi metadata của Step được cập nhật. Lần restart có thể gọi lại Tasklet. Hãy kiểm tra file nguồn/đích và thiết kế hành động có thể chạy lại an toàn.

## 5. Khai báo Tasklet bằng Java configuration

Trong Spring Batch 5, Tasklet được gắn với Step bằng `StepBuilder.tasklet(tasklet, transactionManager)`:

```java
@Bean
Step archiveInputFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveService archiveService) {

    Tasklet archiveTasklet = (contribution, chunkContext) -> {
        archiveService.archiveProcessedFile();
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("archiveInputFileStep", jobRepository)
            .tasklet(archiveTasklet, transactionManager)
            .build();
}
```

Có thể khai báo Tasklet dưới dạng lambda cho logic ngắn hoặc tạo class riêng khi logic có nhiều nhánh, cần dependency phức tạp hoặc cần unit test độc lập.

### Tách Tasklet thành class riêng

```java
@Component
public class ArchiveFileTasklet implements Tasklet {

    private final ArchiveService archiveService;

    public ArchiveFileTasklet(ArchiveService archiveService) {
        this.archiveService = archiveService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        archiveService.archiveProcessedFile();
        return RepeatStatus.FINISHED;
    }
}
```

Đăng ký class này vào Step:

```java
@Bean
Step archiveInputFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveFileTasklet archiveFileTasklet) {

    return new StepBuilder("archiveInputFileStep", jobRepository)
            .tasklet(archiveFileTasklet, transactionManager)
            .build();
}
```

Class riêng giúp tách trách nhiệm và kiểm thử dễ hơn. Nếu Tasklet giữ trạng thái mutable, cần chú ý scope và việc cùng bean có thể được sử dụng bởi nhiều execution. Không nên lưu trạng thái riêng của một lần chạy trong field của singleton Tasklet nếu các Job có thể chạy đồng thời.

## 6. Lấy JobParameters và execution context trong Tasklet

Một thao tác một lần thường cần tham số như tên tệp hoặc ngày nghiệp vụ. Tasklet có thể đọc chúng từ `StepContribution` hoặc `ChunkContext` thông qua `StepExecution` và `JobExecution`.

```java
@Bean
Step archiveFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ArchiveService archiveService) {

    return new StepBuilder("archiveFileStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                StepExecution stepExecution = contribution.getStepExecution();
                JobParameters parameters = stepExecution
                        .getJobExecution()
                        .getJobParameters();

                String inputFile = parameters.getString("inputFile");
                LocalDate businessDate = parameters.getLocalDate("businessDate");

                archiveService.archive(inputFile, businessDate);
                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Các phương thức lấy tham số phải phù hợp với kiểu đã truyền và phiên bản Spring Batch. Trong ví dụ, `businessDate` được lưu dưới dạng kiểu ngày; nếu ứng dụng truyền ngày dưới dạng chuỗi, cần parse theo format đã quy định.

Nếu Tasklet cần chia sẻ một kết quả cho Step tiếp theo, có thể ghi dữ liệu nhỏ vào Job `ExecutionContext`. Nếu chỉ cần checkpoint riêng của Tasklet, dùng Step `ExecutionContext`. Không nên lưu payload nghiệp vụ lớn trong context; hãy lưu khóa hoặc tham chiếu đến dữ liệu được lưu ở nơi phù hợp.

## 7. Transaction của thao tác một lần

TaskletStep thực thi Tasklet trong transaction được cấu hình cho Step. Với một lần gọi trả `FINISHED`, thao tác database tham gia transaction manager có thể được commit khi lần gọi hoàn tất bình thường hoặc rollback khi exception làm transaction thất bại.

Ví dụ, nếu Tasklet thực hiện một câu `UPDATE` bằng `JdbcTemplate` và dùng cùng transaction manager với Step, thay đổi database có thể tham gia transaction đó.

Tuy nhiên, transaction không tự hoàn tác mọi loại tác dụng phụ:

- HTTP request đã gửi đến hệ thống khác.
- Email đã được gửi.
- File đã được di chuyển hoặc xóa.
- Lệnh gọi hệ thống ngoài đã được tiếp nhận.

Nếu một Tasklet vừa cập nhật database vừa gọi API ngoài, transaction database rollback không làm API quên yêu cầu đã nhận. Hãy tách tác dụng phụ, dùng idempotency key hoặc transactional outbox khi cần phối hợp dữ liệu và sự kiện.

Nếu stored procedure tự commit hoặc sử dụng transaction độc lập, cần xác định hành vi transaction thực tế của database. Không giả định procedure luôn rollback cùng transaction của Step.

## 8. “Một lần” trong Tasklet không đồng nghĩa exactly-once

Tasklet trả về `FINISHED` sau một lần gọi chỉ có nghĩa Step không cần gọi lại Tasklet trong vòng lặp hiện tại. Hành động vẫn có thể được thực hiện lần nữa trong các tình huống khác:

- Job được khởi chạy bằng một JobInstance mới với identifying parameters khác.
- Step thất bại và Job được restart theo chính sách cho phép.
- Một thao tác bên ngoài đã hoàn tất nhưng tiến trình dừng trước khi metadata ghi nhận Step hoàn tất.
- Step đã hoàn tất được cấu hình `allowStartIfComplete(true)` và được chạy lại trong một lần restart phù hợp.
- Người vận hành chủ động khởi chạy lại nghiệp vụ bằng một định danh mới.

Vì vậy, Tasklet không tự cung cấp bảo đảm exactly-once cho tác dụng phụ bên ngoài. Cần phân biệt “một lần gọi trong một lần thực thi Step” với “chỉ xảy ra đúng một lần trong toàn bộ hệ thống”.

### Thiết kế idempotent

Một thao tác idempotent có thể được gọi lại mà kết quả nghiệp vụ cuối cùng vẫn đúng. Ví dụ:

- Xóa các bản ghi tạm theo một `batchId` cụ thể; xóa lần nữa không gây sai lệch.
- Tạo thư mục nếu chưa tồn tại.
- Chuyển file nếu file nguồn tồn tại và file đích chưa tồn tại; nếu file đích đã có, kiểm tra nội dung hoặc trạng thái thay vì ghi đè mù quáng.
- Cập nhật trạng thái theo business key và điều kiện trạng thái trước đó.
- Gọi API với idempotency key để hệ thống đích nhận diện yêu cầu lặp.

Nếu thao tác không thể lặp an toàn, cần một cơ chế phối hợp và đối soát rõ ràng trước khi cho phép restart hoặc launch lại.

## 9. Restart và chạy lại Tasklet

Spring Batch lưu trạng thái StepExecution trong JobRepository. Khi Job thất bại và được restart, Step chưa hoàn tất có thể được thực thi lại theo chính sách của Job và Step. Tasklet cần được thiết kế để xử lý tình huống này.

Nếu Step đã hoàn tất, khi restart cùng JobInstance, Spring Batch thường bỏ qua Step đó. Có thể cấu hình `allowStartIfComplete(true)` để Step đã hoàn tất được chạy lại trong một lần restart phù hợp:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ReferenceDataTasklet tasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Chỉ bật tùy chọn này nếu thao tác cần chạy lại khi Job được restart và có thể thực hiện an toàn. Nó không phải cách để launch lại một JobInstance đã hoàn tất bằng một lệnh launch thông thường.

Nếu Job dùng `preventRestart()`, Job không được restart sau khi execution trước đã kết thúc theo trạng thái cho phép restart. Đây là chính sách ở cấp Job; chỉ sử dụng khi nghiệp vụ thật sự không cho phép tiếp tục execution cũ. Không nên dùng `preventRestart()` như một cách thay thế thiết kế idempotent.

### Lưu checkpoint khi Tasklet có nhiều lượt

Nếu một tác vụ có nhiều giai đoạn hoặc cần chia thành nhiều lượt, Tasklet có thể lưu tiến độ vào `ExecutionContext` và trả `CONTINUABLE`:

```java
.tasklet((contribution, chunkContext) -> {
    ExecutionContext context = contribution
            .getStepExecution()
            .getExecutionContext();

    int page = context.getInt("nextPage", 0);
    boolean hasMore = migrationService.processPage(page);

    if (hasMore) {
        context.putInt("nextPage", page + 1);
        return RepeatStatus.CONTINUABLE;
    }

    return RepeatStatus.FINISHED;
}, transactionManager)
```

Đây là khung minh họa cho Tasklet nhiều lượt, không phải ví dụ thao tác một lần thuần túy. Checkpoint phải được cập nhật nhất quán với phần công việc đã hoàn tất. Nếu công việc có bản chất xử lý nhiều item và cần commit interval, skip/retry theo item hoặc checkpoint tự động, chunk processing thường phù hợp hơn.

## 10. Khi nào không nên dùng Tasklet cho thao tác một lần?

Tasklet không phải lựa chọn tốt nếu công việc thực tế là xử lý một tập lớn item theo cùng một pipeline.

Ví dụ không nên gói toàn bộ việc import hàng triệu dòng vào một vòng lặp lớn trong `execute` nếu cần:

- Commit theo nhóm để tránh transaction kéo dài.
- Theo dõi số item đã đọc, xử lý, ghi và skip.
- Retry hoặc skip riêng cho từng item.
- Restart từ checkpoint đọc/ghi.
- Dùng reader và writer chuẩn của Spring Batch.

Trong trường hợp đó, chunk processing giúp tổ chức công việc và cung cấp cơ chế quản lý item phù hợp hơn.

Ngược lại, không cần tạo reader trả về một item duy nhất và writer chỉ gọi một service để mô phỏng chunk step nếu thao tác thực chất là một hành động độc lập. Tasklet thể hiện trực tiếp ý nghĩa của công việc.

## 11. Kết hợp Tasklet với chunk Step trong một Job

Một Job có thể dùng Tasklet cho các thao tác chuẩn bị/kết thúc và chunk processing cho phần dữ liệu:

```text
Job: import-orders
  |
  v
Tasklet Step: kiểm tra file và chuẩn bị staging
  |
  v
Chunk Step: đọc, kiểm tra, chuyển đổi và ghi đơn hàng
  |
  v
Tasklet Step: tạo báo cáo và archive file
```

Ví dụ:

- Tasklet đầu tiên kiểm tra tệp đầu vào và xóa dữ liệu staging thuộc batch hiện tại.
- Chunk Step xử lý từng đơn hàng theo nhóm và commit theo chunk.
- Tasklet cuối cùng tạo báo cáo tổng kết và di chuyển tệp đã xử lý.

Cách kết hợp này giúp mỗi Step có trách nhiệm rõ ràng. Tasklet xử lý hành động độc lập; chunk step xử lý pipeline item.

## 12. Xử lý lỗi trong Tasklet

Tasklet có thể ném exception khi thao tác thất bại. Spring Batch sẽ xử lý transaction của lần gọi và cập nhật trạng thái Step theo kết quả thực thi.

Ví dụ, nếu không tìm thấy file bắt buộc, Tasklet có thể ném exception:

```java
if (!Files.exists(inputPath)) {
    throw new FileNotFoundException(
            "Required input file was not found");
}
```

Không nên bắt exception rồi trả `FINISHED` nếu công việc chưa hoàn tất. Nếu muốn coi một trường hợp là không có việc cần làm, hãy xác định đó là kết quả nghiệp vụ hợp lệ và ghi nhận rõ ràng, sau đó mới trả `FINISHED`.

Nếu một lỗi có thể phục hồi, cần chọn cách retry phù hợp với Step và bảo đảm thao tác có thể lặp. Nếu lỗi không thể phục hồi hoặc dữ liệu không đáng tin cậy, để Step thất bại và xử lý qua quy trình restart/điều tra.

Tasklet có thể dùng listener để ghi nhận thời điểm bắt đầu/kết thúc hoặc exit status tùy chỉnh. Không nên đặt toàn bộ logic nghiệp vụ vào listener; hành động chính nên nằm trong Tasklet hoặc service mà Tasklet gọi.

## 13. Những lỗi thường gặp

### Quên trả về RepeatStatus.FINISHED

Nếu Tasklet trả về `CONTINUABLE`, Spring Batch sẽ gọi lại `execute`. Với thao tác một lần, cần trả về `FINISHED` sau khi hoàn tất để Step kết thúc vòng lặp.

### Nghĩ rằng Tasklet chỉ chạy đúng một lần trong mọi trường hợp

Tasklet có thể được gọi lại do `CONTINUABLE`, restart, retry hoặc một JobInstance mới. Hãy xác định rõ phạm vi “một lần” và thiết kế idempotency.

### Bắt exception rồi vẫn trả FINISHED

Điều này có thể khiến Step được đánh dấu thành công dù thao tác chưa hoàn tất. Chỉ trả `FINISHED` khi kết quả đã đạt yêu cầu hoặc trường hợp không làm gì là kết quả hợp lệ được định nghĩa rõ.

### Đặt vòng lặp xử lý hàng triệu item trong một lần execute

Tasklet có thể chạy vòng lặp, nhưng ứng dụng sẽ phải tự quản lý commit, checkpoint, retry, skip và thống kê. Nếu công việc là xử lý item, chunk step thường phù hợp hơn.

### Giả định rollback database hoàn tác được file hoặc API

Transaction của Step không tự hoàn tác thao tác filesystem hoặc request HTTP. Hãy dùng kiểm tra trạng thái, idempotency key, outbox hoặc quy trình đối soát.

### Lưu trạng thái execution trong field của singleton Tasklet

Một bean Tasklet singleton có thể được dùng bởi nhiều execution. Lưu business state mutable trong field có thể khiến các Job làm ảnh hưởng lẫn nhau. Dùng Job/Step ExecutionContext hoặc bean scope phù hợp cho trạng thái của từng execution.

### Bật allowStartIfComplete mà không xem xét tác dụng phụ

Tùy chọn này cho phép Step đã hoàn tất được chạy lại khi restart. Nếu thao tác không idempotent, việc chạy lại có thể tạo dữ liệu trùng hoặc lặp hành động bên ngoài.

## 14. Quy trình thiết kế một Tasklet cho thao tác một lần

Khi xây dựng một Step dạng Tasklet, có thể đi theo trình tự:

1. Xác định hành động có thể hoàn tất như một đơn vị độc lập hay thực chất là pipeline nhiều item.
2. Đưa logic nghiệp vụ vào service phù hợp; giữ `execute` ngắn và rõ trách nhiệm điều phối.
3. Truyền dependency qua constructor hoặc tham số bean, không tạo kết nối hoặc tài nguyên tùy tiện trong mỗi lần gọi.
4. Xác định transaction manager và tài nguyên nào thực sự tham gia transaction.
5. Trả `RepeatStatus.FINISHED` khi hành động hoàn tất.
6. Để exception được truyền lên nếu thao tác thất bại; không đánh dấu thành công giả.
7. Thiết kế thao tác có thể chạy lại an toàn hoặc xác định quy trình phục hồi rõ ràng.
8. Dùng ExecutionContext nếu cần lưu checkpoint hoặc chia sẻ kết quả giữa Step.
9. Kiểm tra tình huống restart và JobInstance mới để tránh tác dụng phụ trùng lặp.

| Công việc | Tasklet có phù hợp? | Lý do |
|---|---|---|
| Gọi stored procedure làm mới bảng tổng hợp | Có | Một lời gọi cấp hệ thống. |
| Xóa dữ liệu staging của một batch | Có | Một thao tác SQL có phạm vi rõ ràng. |
| Kiểm tra một file đầu vào tồn tại | Có | Một điều kiện tiền xử lý. |
| Archive một file sau import | Có | Một thao tác filesystem độc lập, cần thiết kế chạy lại an toàn. |
| Tạo thư mục hoặc file marker | Có | Một hành động chuẩn bị/hoàn tất. |
| Import hàng triệu dòng và validate từng dòng | Thường không | Cần pipeline item, commit interval và checkpoint. |
| Skip bản ghi lỗi và retry item gặp lỗi tạm thời | Thường không | Chunk processing có fault tolerance ở cấp item. |

## Kết luận

Tasklet phù hợp với một thao tác độc lập có thể hoàn tất trong một lần gọi `execute`, ví dụ dọn dữ liệu, gọi stored procedure, kiểm tra điều kiện hoặc archive file. Sau khi thao tác thành công, trả `RepeatStatus.FINISHED` để Spring Batch kết thúc vòng lặp của Step. “Một lần” chỉ mô tả lần gọi trong một lần thực thi Step; restart, JobInstance mới hoặc cấu hình `allowStartIfComplete(true)` vẫn có thể khiến hành động chạy lại. Vì vậy, hãy hiểu rõ transaction boundary, để lỗi được phản ánh đúng và thiết kế tác vụ idempotent khi có thể.
