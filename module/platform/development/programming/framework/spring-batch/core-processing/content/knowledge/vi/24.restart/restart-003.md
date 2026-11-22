# Restart từ step thất bại

Trong Spring Batch, một job có thể gồm nhiều step và mỗi step có thể xử lý hàng nghìn hoặc hàng triệu item. Nếu một step thất bại sau khi các step trước đã hoàn tất, thông thường không cần chạy lại toàn bộ quy trình từ đầu. Spring Batch lưu metadata về lần thực thi và trạng thái của từng step để hỗ trợ **restart từ step thất bại**.

Restart tạo một `JobExecution` mới cho cùng `JobInstance`, sau đó framework xác định step nào đã hoàn tất, step nào cần thực hiện lại và trạng thái nào cần khôi phục. Để quá trình này an toàn, ứng dụng phải giữ ổn định định danh job, lưu checkpoint đúng cách và thiết kế reader/writer có thể chịu được việc xử lý lại các item chưa commit.

## 1. Phân biệt JobInstance và JobExecution

Đây là nền tảng để hiểu restart. `JobInstance` đại diện cho một đơn vị xử lý logic; `JobExecution` đại diện cho một lần chạy cụ thể của đơn vị đó.

Một JobInstance được xác định bởi tên job và các identifying `JobParameters`. Khi job thất bại và được restart, Spring Batch tạo một JobExecution mới thuộc cùng JobInstance.

```text
Job: importOrdersJob
Identifying parameter: businessDate=2026-11-15
                  |
                  v
JobInstance: importOrdersJob / 2026-11-15
                  |
          +-------+--------+
          |                |
          v                v
   JobExecution #1   JobExecution #2
       FAILED          COMPLETED
```

Lần chạy thứ hai không phải một JobInstance mới. Nó là execution tiếp theo của cùng một đơn vị công việc logic.

| Khái niệm | Ý nghĩa khi restart |
|---|---|
| `JobInstance` | Giữ nguyên nếu tên job và identifying parameters không đổi. |
| `JobExecution` | Mỗi lần chạy/restart tạo một execution mới với ID riêng. |
| `StepExecution` | Mỗi lần step được thực thi có metadata riêng; lần restart có thể tạo StepExecution mới cho step cần chạy lại. |
| `ExecutionContext` | Lưu checkpoint và trạng thái cần thiết để khôi phục việc xử lý. |

Nếu thay đổi một identifying parameter, Spring Batch xem yêu cầu là một JobInstance khác. Vì vậy, khi muốn restart, cần dùng đúng tên job và đúng các identifying parameters của lần chạy ban đầu.

## 2. Điều gì xảy ra khi một step thất bại?

Giả sử job nhập đơn hàng gồm ba step:

1. `validateFileStep`: kiểm tra file đầu vào.
2. `importOrdersStep`: đọc, xử lý và ghi đơn hàng.
3. `publishSummaryStep`: tạo và gửi báo cáo tổng hợp.

Nếu step nhập dữ liệu thất bại, trạng thái có thể như sau:

```text
importOrdersJob
    |
    +-- validateFileStep       COMPLETED
    |
    +-- importOrdersStep       FAILED
    |
    +-- publishSummaryStep     NOT STARTED
```

Khi restart cùng JobInstance, Spring Batch thường bỏ qua step đã hoàn tất và bắt đầu lại từ step chưa hoàn tất/đã thất bại theo flow và trạng thái metadata:

```text
importOrdersJob - restart
    |
    +-- validateFileStep       COMPLETED (không chạy lại mặc định)
    |
    +-- importOrdersStep       chạy lại từ checkpoint phù hợp
    |
    +-- publishSummaryStep     chạy sau khi import hoàn tất
```

Hành vi này giúp tránh lặp lại công việc đã hoàn tất. Tuy nhiên, nó phụ thuộc cấu hình step và flow. Một step đã hoàn tất có thể được yêu cầu chạy lại bằng `allowStartIfComplete(true)`, còn giới hạn `startLimit` có thể ngăn step được khởi chạy thêm lần nữa.

Restart không phải là chạy lại toàn bộ job một cách mù quáng. Framework dựa trên metadata đã lưu để xác định tiến trình trước đó và những phần cần tiếp tục.

## 3. Điều kiện để một job có thể restart

Một số điều kiện quan trọng cần được đáp ứng:

- Job phải cho phép restart; không được cấu hình `preventRestart()` nếu muốn restart.
- JobInstance phải ở trạng thái cho phép restart, thường là `FAILED` hoặc `STOPPED`.
- Không được có một execution khác của cùng JobInstance đang chạy.
- Step cần chạy lại không được vượt `startLimit`.
- Flow phải có đường đi hợp lệ từ trạng thái execution trước đó.
- JobParameters identifying phải trỏ đến đúng JobInstance cũ.
- JobRepository phải lưu metadata đủ bền vững để khôi phục trạng thái.
- Reader/writer cần lưu và khôi phục checkpoint phù hợp nếu muốn tiếp tục từ giữa step.

Các trạng thái `FAILED` và `STOPPED` thường là những trạng thái có thể restart. Một JobInstance đã `COMPLETED` không thể được chạy lại như một lần restart thông thường với cùng identifying parameters. Trạng thái `ABANDONED` hoặc `UNKNOWN` cần được xử lý thận trọng theo quy tắc vận hành và phiên bản framework; không nên tự sửa metadata để ép chạy tiếp.

## 4. Cấu hình job cho phép restart

Job thông thường có thể restart nếu không bị vô hiệu hóa khả năng restart. Có thể chủ động ngăn restart bằng `preventRestart()`:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateFileStep,
        Step importOrdersStep,
        Step publishSummaryStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateFileStep)
            .next(importOrdersStep)
            .next(publishSummaryStep)
            .build();
}
```

Ví dụ trên không gọi `preventRestart()`, do đó job vẫn có thể restart theo trạng thái và điều kiện của Spring Batch.

Nếu job được thiết kế chỉ chạy một lần và không có khả năng tiếp tục an toàn, có thể cấu hình:

```java
return new JobBuilder("oneTimeExportJob", jobRepository)
        .start(exportStep)
        .preventRestart()
        .build();
```

Khi đã gọi `preventRestart()`, yêu cầu restart JobInstance sẽ bị từ chối. Chỉ sử dụng tùy chọn này khi nghiệp vụ thực sự không cho phép restart và có quy trình xử lý lỗi khác.

## 5. Khởi chạy lại cùng JobInstance

Có hai cách phổ biến để yêu cầu restart: gọi lại `JobLauncher` với cùng identifying parameters hoặc dùng API vận hành `JobOperator.restart` với execution ID cũ.

### Dùng JobLauncher

Ví dụ lần đầu chạy job:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders-20261115.csv", true)
        .toJobParameters();

JobExecution firstExecution = jobLauncher.run(importOrdersJob, parameters);
```

Sau khi execution thất bại và nguyên nhân đã được khắc phục, gọi lại cùng job với cùng identifying parameters:

```java
JobExecution restartExecution = jobLauncher.run(importOrdersJob, parameters);
```

Spring Batch nhận diện cùng JobInstance và tạo JobExecution mới nếu trạng thái cho phép restart. Nếu lần chạy trước đã hoàn tất, cùng parameters thường dẫn đến `JobInstanceAlreadyCompleteException`.

### Dùng JobOperator

Trong quy trình vận hành, thường đã có JobExecution ID của lần chạy thất bại. `JobOperator` cung cấp API restart theo ID:

```java
long newExecutionId = jobOperator.restart(failedExecutionId);
```

API có thể phát sinh các exception quản trị như không tìm thấy execution, không thể restart hoặc parameters không hợp lệ. Cần kiểm tra trạng thái và quyền vận hành trước khi gọi.

`JobOperator.restart` sử dụng metadata của execution trước để xác định job và parameters cần restart. Đây là lựa chọn phù hợp cho màn hình quản trị hoặc quy trình vận hành có kiểm soát.

## 6. JobParameters phải ổn định khi restart

Giả sử job `importOrdersJob` dùng ngày nghiệp vụ và file đầu vào làm identifying parameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders-20261115.csv", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Khi restart, cần giữ nguyên các identifying values:

| Tham số | Identifying | Khi restart |
|---|---:|---|
| `businessDate` | Có | Giữ nguyên ngày nghiệp vụ của instance cũ. |
| `inputFile` | Có | Giữ nguyên định danh file/batch đầu vào. |
| `requestedBy` | Không | Không ảnh hưởng JobInstance identity, nhưng thay đổi giá trị có thể ảnh hưởng audit hoặc logic ứng dụng. |

Không thêm timestamp hoặc UUID mới làm identifying parameter khi mục tiêu là restart. Làm vậy sẽ tạo JobInstance mới thay vì tiếp tục instance thất bại.

Ngay cả với tham số non-identifying, cần thận trọng khi thay đổi giá trị giữa các lần thực thi. Nếu processor hoặc writer phụ thuộc vào tham số đó, thay đổi có thể khiến lần restart xử lý cùng JobInstance bằng logic khác. Hãy giữ ổn định mọi tham số ảnh hưởng đến kết quả nghiệp vụ.

## 7. Step đã COMPLETED có chạy lại không?

Theo mặc định, khi restart job, các step đã hoàn tất trong execution trước thường không chạy lại. Điều này giúp tránh lặp lại công việc đã hoàn thành.

Nếu một step đã hoàn tất nhưng cần chạy lại mỗi lần job restart, có thể cấu hình `allowStartIfComplete(true)`:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet refreshTasklet = (contribution, chunkContext) -> {
        // Đồng bộ dữ liệu tham chiếu theo chính sách của ứng dụng.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(refreshTasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Khi restart, step này có thể được thực hiện lại ngay cả khi execution trước đã `COMPLETED`. Điều đó hữu ích với step chuẩn bị cần chạy lại để bảo đảm điều kiện đầu vào hiện tại.

Không nên bật tùy chọn này cho mọi step. Nếu step gửi thanh toán, gửi email, tạo file cuối cùng hoặc cập nhật dữ liệu không idempotent, chạy lại có thể tạo tác dụng phụ trùng.

## 8. startLimit giới hạn số lần khởi chạy step

`startLimit` giới hạn số lần một step được phép bắt đầu. Mặc định, step thường có giới hạn rất lớn; có thể đặt giới hạn thấp hơn để bảo vệ tài nguyên hoặc nghiệp vụ.

```java
@Bean
Step fragileExternalCallStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        // Gọi một hệ thống ngoài theo chính sách của ứng dụng.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("fragileExternalCallStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .startLimit(3)
            .build();
}
```

Nếu step đã đạt giới hạn, một lần restart tiếp theo có thể bị từ chối bằng `StartLimitExceededException`. Cần phân biệt `startLimit` với retry limit:

| Cấu hình | Phạm vi |
|---|---|
| `retryLimit` | Số lần thử lại một thao tác/item theo retry policy trong step execution. |
| `startLimit` | Số lần step được phép bắt đầu qua các execution. |
| `skipLimit` | Tổng số item/lỗi được phép bỏ qua trong step execution theo skip policy. |

Nếu muốn restart step thất bại, đừng đặt `startLimit` quá thấp so với số lần vận hành có thể cần. Ngược lại, giới hạn có thể hữu ích khi step tạo tác dụng phụ khó hoàn tác hoặc có chi phí cao.

## 9. Restart từ checkpoint trong chunk-oriented step

Một ưu điểm quan trọng của Spring Batch là hỗ trợ checkpoint. Trong chunk-oriented step, reader và writer có thể triển khai `ItemStream` để lưu trạng thái vào `ExecutionContext`.

Ví dụ, reader file lưu vị trí đã đọc. Sau mỗi chunk commit, trạng thái đọc được cập nhật. Nếu chunk tiếp theo thất bại, lần restart có thể tiếp tục từ checkpoint cuối cùng đã commit.

```text
Đọc và ghi chunk 1 -> COMMIT -> checkpoint 1
Đọc và ghi chunk 2 -> COMMIT -> checkpoint 2
Đọc chunk 3       -> lỗi, ROLLBACK

Restart:
  khôi phục checkpoint 2
  đọc lại phần chưa commit của chunk 3
  tiếp tục chunk 4...
```

Điểm khôi phục là trạng thái đã được lưu bền vững, không phải câu lệnh Java cuối cùng đã chạy trước khi process chết. Item trong chunk chưa commit có thể được đọc và xử lý lại.

Nhiều reader tích hợp như `FlatFileItemReader`, `JdbcPagingItemReader` hoặc các reader hỗ trợ `ItemStream` có thể lưu state. Khi tự viết reader, cần triển khai `ItemStream`/`ItemStreamReader` nếu muốn hỗ trợ checkpoint.

## 10. ItemStream và ExecutionContext

Vòng đời `ItemStream` gồm các phương thức quan trọng:

- `open(ExecutionContext)`: mở tài nguyên và khôi phục trạng thái đã lưu.
- `update(ExecutionContext)`: cập nhật trạng thái cần checkpoint.
- `close()`: giải phóng tài nguyên.

Ví dụ minh họa reader tự viết lưu vị trí đọc:

```java
public class NumberReader implements ItemStreamReader<Long> {

    private long current;
    private final long max;

    public NumberReader(long max) {
        this.max = max;
    }

    @Override
    public void open(ExecutionContext context) {
        current = context.containsKey("numberReader.current")
                ? context.getLong("numberReader.current")
                : 0L;
    }

    @Override
    public Long read() {
        if (current >= max) {
            return null;
        }
        current++;
        return current;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("numberReader.current", current);
    }

    @Override
    public void close() {
        // Đóng tài nguyên nếu reader có mở tài nguyên.
    }
}
```

Đây là ví dụ đơn giản về cách lưu state. Reader thực tế cần chú ý transaction boundary, cách framework gọi `update`, tính ổn định của nguồn dữ liệu và thread safety. Không nên lưu đối tượng tài nguyên đang mở như `InputStream` hoặc `ResultSet` vào ExecutionContext; chỉ lưu thông tin đủ để mở lại và tiếp tục.

## 11. Restart với reader từ file

Với `FlatFileItemReader`, nên bật lưu state và đặt tên reader ổn định:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readString("customerId"),
                    fieldSet.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`@StepScope` cho phép lấy đường dẫn file từ JobParameters tại thời điểm step execution. `saveState(true)` cho phép reader lưu vị trí đọc.

Điều kiện quan trọng: file phải giữ nguyên nội dung và thứ tự dòng giữa lần chạy đầu và restart. Nếu file cùng đường dẫn bị thay thế bằng nội dung khác, checkpoint cũ có thể trỏ đến vị trí không còn tương ứng với cùng dữ liệu. Với file lớn hoặc quan trọng, nên lưu file bất biến theo batch ID hoặc checksum.

## 12. Restart với reader database

Với `JdbcPagingItemReader`, cần dùng thứ tự ổn định và sort key duy nhất để checkpoint có ý nghĩa. Ví dụ:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderInput> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause("select order_id, customer_id, amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate")
            .parameterValues(Map.of("businessDate", businessDate))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Để restart ổn định:

- `order_id` phải xác định được thứ tự duy nhất trong tập kết quả, hoặc cần thêm khóa phụ để tạo thứ tự duy nhất.
- Điều kiện `businessDate` phải giữ nguyên.
- Tập dữ liệu không nên thay đổi theo cách làm dịch chuyển ranh giới trang trong lúc job chạy.
- Nếu dữ liệu có thể thay đổi, hãy dùng snapshot, batch ID hoặc watermark để cố định phạm vi.

Cursor reader và paging reader có semantics checkpoint khác nhau. Hãy xem implementation cụ thể và hành vi database/driver thay vì giả định mọi reader khôi phục theo cùng một cách.

## 13. Tasklet step và restart

Tasklet step cũng có thể restart. Tuy nhiên, tasklet tự viết phải quản lý trạng thái và tác dụng phụ phù hợp.

Nếu tasklet thực hiện một thao tác đơn lẻ và transaction rollback được toàn bộ thay đổi, restart có thể chạy lại thao tác đó. Nhưng nếu tasklet gọi API ngoài, tạo file hoặc gửi email, transaction database không thể tự hoàn tác các tác dụng phụ đó.

Ví dụ tasklet lưu trạng thái trong Step ExecutionContext:

```java
@Bean
Step prepareExportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        ExecutionContext context = contribution.getStepExecution()
                .getExecutionContext();

        String exportReference = context.containsKey("exportReference")
                ? context.getString("exportReference")
                : UUID.randomUUID().toString();

        context.putString("exportReference", exportReference);

        // Dùng exportReference ổn định cho tác vụ tiếp theo.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("prepareExportStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

Ví dụ minh họa việc lưu một reference; việc tạo UUID trong tasklet chỉ an toàn nếu giá trị được lưu và khôi phục đúng theo transaction/restart semantics, và không tạo mới ở mỗi lần gọi sau khi đã có giá trị. Với tác dụng phụ bên ngoài, nên có cơ chế idempotency riêng.

Nếu tasklet trả `RepeatStatus.CONTINUABLE`, nó có thể được gọi nhiều lần trong cùng step execution. Cần cập nhật checkpoint nhất quán để mỗi lần gọi tiếp tục đúng phần công việc chưa hoàn tất.

## 14. allowStartIfComplete và việc chạy lại step đã hoàn tất

Theo mặc định, step đã hoàn tất không được chạy lại khi restart job. `allowStartIfComplete(true)` thay đổi hành vi này.

Nên dùng khi step có nhiệm vụ chuẩn bị hoặc đồng bộ cần được thực hiện lại trước step thất bại, ví dụ:

- Làm mới dữ liệu tham chiếu có thể tái lập.
- Kiểm tra điều kiện đầu vào hiện tại.
- Tạo lại một file trung gian có thể tạo lặp an toàn.
- Chuẩn bị môi trường mà step sau cần.

Không nên dùng với step tạo giao dịch không idempotent, ví dụ:

- Gửi tiền hoặc ghi nhận thanh toán.
- Gửi email/notification không có khóa chống trùng.
- Tạo một đơn hàng mới mỗi lần chạy.
- Publish sự kiện không có cơ chế deduplication.

Nếu cần chạy lại step đã hoàn tất theo một yêu cầu nghiệp vụ mới, hãy cân nhắc tạo JobInstance mới với identifying parameter thể hiện lần xử lý mới thay vì dùng `allowStartIfComplete` để thay đổi semantics restart.

## 15. startLimit và khả năng restart step thất bại

`startLimit` kiểm soát số lần step được phép bắt đầu. Nếu đặt quá thấp, step có thể không được restart sau một số lần thất bại.

Ví dụ:

```java
return new StepBuilder("loadExternalDataStep", jobRepository)
        .tasklet(loadTasklet, transactionManager)
        .startLimit(2)
        .build();
```

Với giới hạn này, step chỉ được phép bắt đầu tối đa hai lần theo quy tắc start limit của framework. Khi đã hết giới hạn, lần restart tiếp theo có thể phát sinh `StartLimitExceededException`.

Hãy chọn giới hạn dựa trên khả năng phục hồi thực tế, chi phí và tác dụng phụ của step. Nếu step có thể restart an toàn sau khi sửa nguyên nhân, giới hạn cần cho phép đủ số lần vận hành hợp lý.

## 16. Flow và conditional transition khi restart

Restart còn phụ thuộc cấu trúc flow. Một job có thể dùng `ExitStatus` để rẽ nhánh sang step khác. Khi restart, framework tiếp tục theo flow và metadata đã lưu, vì vậy cần hiểu các transition có thể dẫn đến step nào.

Ví dụ:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step warningStep,
        Step reportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateStep)
                .on("COMPLETED").to(importStep)
            .from(importStep)
                .on("COMPLETED_WITH_WARNINGS").to(warningStep)
            .from(importStep)
                .on("COMPLETED").to(reportStep)
            .from(warningStep)
                .on("*").to(reportStep)
            .from(reportStep)
                .on("*").end()
            .end()
            .build();
}
```

Trong flow có điều kiện, cần bảo đảm `ExitStatus` của step được tạo nhất quán khi restart. Nếu một step thất bại rồi được chạy lại, kết quả mới có thể dẫn đến nhánh khác so với lần trước. Những step đã hoàn tất và bị bỏ qua khi restart vẫn có thể ảnh hưởng đến flow dựa trên metadata đã lưu.

Không nên dựa vào side effect trong listener để quyết định flow mà không lưu kết quả vào metadata phù hợp. Nếu flow cần kết quả nghiệp vụ, hãy biểu diễn rõ bằng ExitStatus hoặc dữ liệu trong ExecutionContext.

## 17. StepExecution và JobExecution cũ vẫn được giữ lại

Restart không ghi đè execution cũ. JobRepository lưu lịch sử để có thể theo dõi các lần chạy.

Ví dụ:

```text
JobInstance: importOrdersJob / businessDate=2026-11-15
  |
  +-- JobExecution #101: FAILED
  |      +-- validateFileStep: COMPLETED
  |      +-- importOrdersStep: FAILED
  |
  +-- JobExecution #205: COMPLETED
         +-- importOrdersStep: COMPLETED
         +-- publishSummaryStep: COMPLETED
```

Khi điều tra, hãy xem đúng JobExecution ID và StepExecution ID. Không nên chỉ tra cứu trạng thái mới nhất theo job name nếu có nhiều JobInstance chạy đồng thời.

`JobExplorer` hỗ trợ đọc metadata:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    System.out.println("Status: " + execution.getStatus());
    System.out.println("Exit: " + execution.getExitStatus());

    for (StepExecution stepExecution : execution.getStepExecutions()) {
        System.out.println(
                stepExecution.getStepName() + " -> " + stepExecution.getStatus());
    }
}
```

`JobExplorer` phù hợp để giám sát lịch sử. `JobOperator` hỗ trợ các thao tác vận hành như restart/stop theo API được cấu hình. Không nên cập nhật trực tiếp các bảng metadata để ép execution sang trạng thái mong muốn.

## 18. Những lỗi thường gặp khi restart

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Tạo JobInstance mới ngoài ý muốn | Thêm timestamp/UUID hoặc thay identifying parameter. | Dùng lại đúng identifying parameters khi restart. |
| `JobInstanceAlreadyCompleteException` | Instance đã hoàn tất; gọi lại cùng identity như thể restart. | Xác định đây là yêu cầu chạy mới hay cần thao tác quản trị khác. |
| `JobExecutionAlreadyRunningException` | Execution trước vẫn đang chạy. | Kiểm tra trạng thái thực tế trước khi gửi yêu cầu khác. |
| `JobRestartException` | Job/step không cho restart hoặc trạng thái không phù hợp. | Kiểm tra `preventRestart`, metadata, flow và cấu hình step. |
| `StartLimitExceededException` | Step đã dùng hết start limit. | Xem lại chính sách start limit và quy trình vận hành. |
| Step đã hoàn tất nhưng không chạy lại | Hành vi mặc định bỏ qua completed step. | Chỉ bật `allowStartIfComplete(true)` nếu step an toàn khi chạy lại. |
| Reader đọc sai vị trí | Không lưu state, tên reader thay đổi hoặc nguồn dữ liệu đã thay đổi. | Dùng ItemStream, tên ổn định và input bất biến. |
| Ghi trùng dữ liệu | Chunk chưa commit được xử lý lại hoặc tác dụng phụ ngoài transaction bị lặp. | Dùng unique key, upsert, idempotency key hoặc outbox. |
| Không tìm thấy metadata sau khi process restart | Dùng repository không bền vững hoặc metadata bị xóa. | Dùng JobRepository bền vững và giữ schema metadata. |
| Restart đi sai nhánh | Flow transition hoặc ExitStatus không được thiết kế cho restart. | Kiểm tra trạng thái và kết quả của từng step trong execution trước. |

## 19. JobRepository phải lưu metadata bền vững

Restart chỉ đáng tin cậy khi metadata thực thi được lưu bền vững. Nếu ứng dụng dùng repository chỉ lưu trong bộ nhớ, trạng thái có thể mất khi JVM dừng. Khi đó framework không có đủ thông tin để biết step nào đã hoàn tất hoặc reader đã đọc đến đâu.

Trong môi trường cần restart qua lần khởi động ứng dụng, nên dùng JobRepository lưu trong database với schema Spring Batch phù hợp phiên bản. Các node/worker cần truy cập repository nhất quán nếu cùng tham gia một quy trình phân tán.

Không xóa metadata JobInstance/JobExecution đang cần restart. Xóa metadata có thể làm mất checkpoint, lịch sử lỗi và quan hệ giữa các lần thực thi. Nếu cần dọn dữ liệu cũ, phải có chính sách retention rõ ràng và chỉ xóa những execution đã hết thời hạn vận hành/audit.

## 20. Transaction boundary và dữ liệu đã commit

Restart không rollback những chunk đã commit trước khi step thất bại. Ví dụ, step đã ghi thành công 20 chunk rồi chunk thứ 21 lỗi. Sau restart, 20 chunk đầu vẫn tồn tại; framework tiếp tục từ checkpoint cuối cùng đã commit nếu reader hỗ trợ.

Điều này cũng có nghĩa writer cần được thiết kế để không ghi trùng khi item chưa commit bị xử lý lại. Transaction database chỉ bảo vệ tài nguyên tham gia transaction đó. Nếu processor/writer đã gửi email hoặc gọi API ngoài trước khi rollback, tác dụng phụ có thể đã xảy ra.

Các biện pháp thường dùng:

- Khóa nghiệp vụ duy nhất ở bảng đích.
- Upsert hoặc merge theo quy tắc rõ ràng.
- Idempotency key cho API ngoài.
- Outbox pattern để phát sự kiện sau khi transaction dữ liệu commit.
- Bảng trạng thái xử lý theo batch ID/item ID.
- Quy trình đối soát các tác dụng phụ có kết quả không rõ ràng.

## 21. Restart trong partitioning

Với partitioning, mỗi worker step có `StepExecution` và `ExecutionContext` riêng. Khi một partition thất bại, các partition khác đã hoàn tất hoặc đã commit không tự động rollback.

```text
managerStep
  |
  +-- partition0: COMPLETED
  +-- partition1: FAILED
  +-- partition2: COMPLETED
  +-- partition3: COMPLETED
```

Khi restart, framework có thể bỏ qua partition đã hoàn tất và tiếp tục partition chưa hoàn tất theo metadata. Điều này yêu cầu:

- Tên partition ổn định.
- Phạm vi dữ liệu của từng partition không thay đổi trong cùng JobInstance.
- Partitioner tạo lại hoặc cung cấp đúng partition identity.
- Worker reader lưu checkpoint riêng.
- Writer có thể chịu được việc xử lý lại item chưa commit.

Nếu partitioner chia lại phạm vi khác với lần chạy đầu, metadata cũ có thể không còn tương ứng với công việc hiện tại. Hãy cố định batch input, partition name và ranh giới dữ liệu trong suốt vòng đời restart.

## 22. Quy trình vận hành restart từ step thất bại

Khi một job thất bại, người vận hành nên làm theo trình tự có kiểm soát:

1. **Tra cứu JobExecution:** lấy ID, JobInstance, parameters, BatchStatus và ExitStatus.
2. **Xác định step thất bại:** xem StepExecution, exception cuối cùng, thời điểm và counter.
3. **Kiểm tra các step đã hoàn tất:** xác định step nào sẽ được bỏ qua khi restart và step nào có `allowStartIfComplete`.
4. **Xác định checkpoint:** kiểm tra reader/writer có lưu state và checkpoint cuối cùng ở đâu.
5. **Kiểm tra dữ liệu đã commit:** xác định chunk nào đã commit và tác dụng phụ ngoài transaction nào có thể đã xảy ra.
6. **Khắc phục nguyên nhân:** sửa dữ liệu, khôi phục dịch vụ, điều chỉnh cấu hình hoặc giải phóng lock.
7. **Kiểm tra parameters:** giữ đúng identifying values và các tham số ảnh hưởng đến kết quả nghiệp vụ.
8. **Kiểm tra điều kiện restart:** `preventRestart`, start limit, trạng thái execution và flow.
9. **Yêu cầu restart:** dùng JobOperator hoặc JobLauncher theo quy trình của ứng dụng.
10. **Theo dõi execution mới:** xác nhận step thất bại đã hoàn tất, step sau chạy đúng và dữ liệu đầu ra không trùng.
11. **Lưu audit:** giữ liên kết giữa execution cũ, execution mới và nguyên nhân khắc phục.

Không nên restart liên tục khi nguyên nhân chưa được xử lý. Nếu lỗi là dữ liệu cố định hoặc schema sai, restart chỉ lặp lại thất bại. Nếu lỗi là hạ tầng tạm thời, cần xác nhận hệ thống đã phục hồi trước khi chạy lại.

## 23. Kiểm thử khả năng restart

Một job cần restart nên có integration test mô phỏng thất bại sau một số chunk đã commit:

- Chạy job với JobParameters xác định.
- Cấu hình writer hoặc processor test để ném exception tại một item/chunk cụ thể.
- Xác nhận JobExecution đầu tiên kết thúc `FAILED`.
- Xác nhận các chunk trước lỗi đã commit và checkpoint được lưu.
- Khắc phục điều kiện gây lỗi trong test.
- Restart cùng JobInstance bằng identifying parameters cũ.
- Xác nhận step đã hoàn tất không chạy lại theo mặc định.
- Xác nhận step thất bại tiếp tục từ checkpoint phù hợp.
- Xác nhận dữ liệu đầu ra không bị trùng và step sau được chạy.

Kiểm thử riêng các tùy chọn `allowStartIfComplete`, `startLimit` và `preventRestart` nếu ứng dụng sử dụng chúng. Với reader tự viết, kiểm thử `open`, `update` và khôi phục trạng thái sau khi tạo reader instance mới.

Unit test chỉ kiểm tra logic processor hoặc reader thường không đủ để chứng minh restart. Cần integration test có JobRepository và transaction manager để xác nhận metadata và ranh giới commit thực tế.

## 24. Những điểm cần ghi nhớ

- Restart tạo `JobExecution` mới cho cùng `JobInstance`; không tạo instance mới nếu identifying parameters giữ nguyên.
- Khi restart, step đã `COMPLETED` thường được bỏ qua; step thất bại/chưa hoàn tất được thực hiện lại theo flow và metadata.
- `preventRestart()` vô hiệu hóa restart; `allowStartIfComplete(true)` cho phép chạy lại step đã hoàn tất; `startLimit` giới hạn số lần step bắt đầu.
- `retryLimit`, `skipLimit` và `startLimit` là ba giới hạn khác nhau.
- Checkpoint của reader/writer được lưu qua `ExecutionContext`; chunk chưa commit có thể được đọc và xử lý lại.
- Reader cần hỗ trợ `ItemStream`/lưu state và nguồn dữ liệu phải ổn định giữa lần chạy đầu và restart.
- Giữ nguyên identifying JobParameters và mọi tham số ảnh hưởng đến kết quả nghiệp vụ.
- JobRepository phải lưu metadata bền vững để restart sau khi JVM dừng.
- Các chunk đã commit không tự rollback khi step thất bại; writer cần idempotent để tránh ghi trùng.
- Tác dụng phụ ngoài transaction như email, HTTP request hoặc publish message cần idempotency/outbox/đối soát.
- Với partitioning, partition name và phạm vi dữ liệu phải ổn định; partition đã commit không tự rollback khi partition khác thất bại.
- Dùng JobExplorer để điều tra metadata và JobOperator để thực hiện thao tác restart theo quy trình vận hành.

Restart từ step thất bại là khả năng phục hồi dựa trên metadata và checkpoint, không phải thao tác chạy lại tùy ý. Hãy giữ định danh job ổn định, bảo đảm các step được phép chạy lại theo đúng chính sách, lưu trạng thái reader/writer và kiểm soát tác dụng phụ của dữ liệu đã commit. Khi đó, job có thể tiếp tục từ phần chưa hoàn tất mà vẫn giữ được lịch sử, tính nhất quán và khả năng đối soát.
