# allowStartIfComplete

Trong Spring Batch, khi một Job thất bại và được restart với cùng JobInstance, các Step đã hoàn tất thường được bỏ qua. Cơ chế này giúp framework không phải chạy lại những phần công việc đã thành công. Tuy nhiên, có trường hợp một Step đã `COMPLETED` vẫn cần chạy lại khi Job được restart, chẳng hạn Step tạo dữ liệu trung gian cần được làm mới trước khi tiếp tục các Step phía sau.

Thuộc tính `allowStartIfComplete` cho phép cấu hình hành vi đó. Khi đặt `allowStartIfComplete(true)`, Spring Batch có thể khởi chạy lại Step dù lần thực thi trước của Step đã hoàn tất, nếu JobInstance đang được restart. Thuộc tính này không có nghĩa Step tự chạy nhiều lần trong một lần JobExecution, cũng không cho phép khởi động lại một JobInstance đã hoàn tất thành công.

## 1. Hành vi mặc định khi restart Job

Spring Batch lưu trạng thái Job và Step trong `JobRepository`. Một JobInstance được xác định bởi tên Job cùng các identifying JobParameters. Khi Job thất bại hoặc bị dừng, lần restart tạo một JobExecution mới cho cùng JobInstance.

Mặc định, nếu một Step đã có StepExecution với trạng thái `COMPLETED`, Spring Batch sẽ không chạy lại Step đó trong lần restart thông thường. Những Step chưa hoàn tất hoặc thất bại có thể được thực thi lại theo trạng thái, khả năng restart và cấu hình của Step.

Ví dụ Job có ba Step:

```text
Lần chạy đầu:

prepareDataStep       COMPLETED
        |
        v
importDataStep        COMPLETED
        |
        v
generateReportStep   FAILED
        |
        v
      Job FAILED

Restart cùng JobInstance:

prepareDataStep       bỏ qua (đã COMPLETED)
        |
        v
importDataStep        bỏ qua (đã COMPLETED)
        |
        v
generateReportStep   chạy lại
```

Hành vi mặc định tiết kiệm thời gian và tránh lặp tác dụng phụ. Nếu hai Step đầu đã tạo dữ liệu đúng và bền vững, không cần chạy lại chúng chỉ vì Step tạo báo cáo gặp lỗi.

## 2. `allowStartIfComplete` thay đổi điều gì?

Khi bật `allowStartIfComplete(true)` cho một Step, Spring Batch cho phép Step đó được khởi chạy lại trong lần restart JobInstance ngay cả khi lần thực thi trước của Step đã `COMPLETED`.

Ví dụ, nếu `prepareDataStep` cần chạy lại để làm mới dữ liệu trung gian trước khi `generateReportStep` tiếp tục, có thể bật thuộc tính này:

```java
@Bean
Step prepareDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PrepareDataTasklet tasklet) {

    return new StepBuilder("prepareDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Nếu Job thất bại ở một Step phía sau rồi được restart, `prepareDataStep` có thể được thực thi lại thay vì bị bỏ qua. Step sau đó tiếp tục theo flow sau khi Step này hoàn tất.

Thuộc tính này được cấu hình trên từng Step. Không cần bật cho mọi Step trong Job. Chỉ bật ở những Step mà việc chạy lại sau một lần hoàn tất là yêu cầu có chủ đích và an toàn.

## 3. `allowStartIfComplete` không phải là “luôn chạy Step”

Tên thuộc tính dễ khiến người đọc hiểu rằng Step sẽ luôn chạy mỗi lần Job được launch. Thực tế, nó chủ yếu điều chỉnh quyết định khi JobInstance được restart và Spring Batch phát hiện Step đã hoàn tất ở execution trước.

| Tình huống | Hành vi thường gặp |
|---|---|
| Launch JobInstance mới | Step chạy theo flow bình thường, dù thuộc tính bật hay tắt |
| Step chưa từng chạy trong JobInstance | Step chạy khi flow đi tới Step |
| Step trước đó `FAILED`, Job được restart | Step có thể được thực thi lại theo restart policy |
| Step trước đó `COMPLETED`, Job được restart, thuộc tính `false` | Step thường được bỏ qua |
| Step trước đó `COMPLETED`, Job được restart, thuộc tính `true` | Step được phép chạy lại |
| JobInstance đã `COMPLETED` và được launch lại với cùng identifying parameters | Không phải restart hợp lệ; thường bị từ chối vì JobInstance đã hoàn tất |

Nếu muốn chạy lại toàn bộ quy trình như một công việc nghiệp vụ mới sau khi Job đã hoàn tất, hãy tạo JobInstance mới bằng identifying JobParameters phù hợp. `allowStartIfComplete` không thay thế cơ chế định danh JobInstance.

## 4. Cấu hình cho chunk-oriented Step

`allowStartIfComplete` cũng có thể dùng với Step xử lý theo chunk. Ví dụ, một Step làm mới bảng staging trước khi Step import tiếp tục:

```java
@Bean
Step refreshStagingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<SourceRecord> reader,
        ItemWriter<StagingRecord> writer) {

    return new StepBuilder("refreshStagingStep", jobRepository)
            .<SourceRecord, StagingRecord>chunk(500, transactionManager)
            .reader(reader)
            .processor(this::toStagingRecord)
            .writer(writer)
            .allowStartIfComplete(true)
            .build();
}
```

Trong ví dụ, nếu Step đã hoàn tất nhưng một Step phía sau thất bại, lần restart có thể chạy lại `refreshStagingStep`. Cần thiết kế writer theo hướng upsert, thay thế dữ liệu theo `batchId`, hoặc xóa và nạp lại một phạm vi xác định trong transaction phù hợp. Nếu writer chỉ insert và không chống trùng, chạy lại Step có thể tạo dữ liệu duplicate.

Với reader có checkpoint, hãy hiểu rõ dữ liệu checkpoint và cách reader khởi tạo khi Step được thực thi lại. Không nên giả định reader luôn bắt đầu từ đầu hoặc luôn tiếp tục từ vị trí cũ chỉ dựa vào tên thuộc tính. Hãy kiểm thử hành vi restart với đúng loại reader, `ItemStream` và phiên bản Spring Batch của ứng dụng.

## 5. Cấu hình cho Tasklet Step

Với Tasklet, có thể đặt thuộc tính sau khi cấu hình tasklet:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        RefreshReferenceDataTasklet tasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Tasklet có thể thực hiện một thao tác làm mới dữ liệu tham chiếu hoặc chuẩn bị một file đầu vào. Khi chạy lại, Tasklet cần xác định đúng phạm vi dữ liệu cần làm mới và không tạo tác dụng phụ trùng.

Ví dụ, nếu Tasklet tạo file `summary.csv`, nên ghi vào file tạm gắn với batch ID, hoàn tất nội dung rồi thay thế file đích theo thao tác an toàn. Không nên append lại toàn bộ dữ liệu vào file cũ mỗi lần restart nếu nghiệp vụ yêu cầu một file duy nhất.

## 6. Khác biệt giữa `allowStartIfComplete` và `startLimit`

Hai thuộc tính này thường xuất hiện gần nhau trong cấu hình Step nhưng kiểm soát hai khía cạnh khác nhau:

- `allowStartIfComplete(true)` quyết định một Step đã `COMPLETED` có được phép chạy lại khi JobInstance được restart hay không.
- `startLimit(n)` giới hạn số lần Step được phép bắt đầu trong một JobInstance.

Ví dụ:

```java
return new StepBuilder("refreshDataStep", jobRepository)
        .tasklet(tasklet, transactionManager)
        .allowStartIfComplete(true)
        .startLimit(3)
        .build();
```

Trong ví dụ, Step được phép chạy lại dù đã hoàn tất, nhưng tổng số lần bắt đầu bị giới hạn theo `startLimit(3)`. Khi vượt giới hạn, Spring Batch có thể ném `StartLimitExceededException` và không cho Step bắt đầu thêm.

| Tiêu chí | `allowStartIfComplete` | `startLimit` |
|---|---|---|
| Câu hỏi | Step đã hoàn tất có được chạy lại khi restart không? | Step được bắt đầu tối đa bao nhiêu lần? |
| Kiểu cấu hình | Boolean | Số nguyên dương |
| Mục tiêu | Điều khiển việc bỏ qua Step đã `COMPLETED` | Chặn số lần bắt đầu quá mức |
| Ví dụ | Làm mới dữ liệu đã tạo ở Step trước | Giới hạn Step tốn kém hoặc có số lần thử hữu hạn |

`startLimit` không tự cho phép chạy lại Step đã hoàn tất; `allowStartIfComplete` cũng không đặt giới hạn số lần chạy. Nếu dùng đồng thời, cần tính cả số lần chạy lại do restart để chọn limit phù hợp.

## 7. Khác biệt với retry

Retry xử lý lỗi tạm thời trong một lần thực thi Step hoặc chunk. `allowStartIfComplete` liên quan đến quyết định thực thi lại một Step đã hoàn tất khi JobInstance được restart sau đó.

Ví dụ:

- Writer gặp deadlock trong chunk: dùng retry policy để thử lại thao tác theo cấu hình fault tolerance.
- Job đã chạy xong `refreshDataStep`, nhưng Step tạo báo cáo phía sau thất bại: dùng `allowStartIfComplete(true)` nếu cần làm mới dữ liệu trước khi restart phần sau.

| Tiêu chí | Retry | `allowStartIfComplete` |
|---|---|---|
| Phạm vi | Lần thử thao tác/item/chunk gặp lỗi | Lần thực thi Step đã hoàn tất trong JobInstance được restart |
| Nguyên nhân | Exception có thể tự hết | Step cần chạy lại dù lần trước đã `COMPLETED` |
| Cơ chế | Retry policy, retry limit, backoff | Thuộc tính trên Step |
| Đơn vị chạy lại | Thao tác hoặc đơn vị retry trong Step | Toàn bộ Step theo flow và lifecycle của Job |

Không nên bật `allowStartIfComplete` để thay thế retry cho lỗi database hoặc service tạm thời. Cũng không nên tăng retry limit để xử lý yêu cầu làm mới một Step đã hoàn thành.

## 8. Khác biệt với `restartable` của Job

Job có thể được cấu hình restartable hoặc non-restartable. Đây là quyết định ở cấp Job, trong khi `allowStartIfComplete` là quyết định ở cấp Step.

- Job restartable cho phép một JobInstance chưa hoàn tất được khởi chạy lại sau trạng thái thất bại hoặc dừng theo quy tắc framework.
- Job non-restartable không cho phép restart instance đó sau khi thất bại.
- `allowStartIfComplete(true)` cho phép một Step đã hoàn tất chạy lại trong một JobInstance đang được restart.

Nếu Job không restartable, bật `allowStartIfComplete` trên Step không làm Job trở nên restartable. Nếu Job đã `COMPLETED`, thuộc tính này cũng không cho phép launch lại cùng JobInstance.

## 9. Chọn Step nào nên bật thuộc tính này?

Chỉ bật cho Step có đầu ra cần được tạo lại hoặc xác nhận lại khi tiếp tục một Job đã thất bại.

Các trường hợp có thể phù hợp:

- Làm mới bảng staging theo một `batchId` ổn định trước khi Step phía sau đọc.
- Tái tạo dữ liệu dẫn xuất có thể tính lại từ nguồn bất biến.
- Kiểm tra lại một resource bên ngoài trước khi tiếp tục, nếu thao tác kiểm tra không tạo tác dụng phụ.
- Tạo lại file trung gian từ dữ liệu nguồn ổn định và ghi đè an toàn.
- Làm mới cache hoặc snapshot tạm thời mà các Step tiếp theo phụ thuộc.

Các trường hợp cần thận trọng hoặc thường không phù hợp:

- Gửi email, SMS hoặc thông báo có thể gửi trùng.
- Thực hiện thanh toán, tạo giao dịch hoặc chuyển tiền.
- Gọi API tạo tài nguyên mới mà không có idempotency key.
- Xóa dữ liệu dùng chung ngoài phạm vi batch hiện tại.
- Cập nhật trạng thái nghiệp vụ không thể đảo ngược.
- Tạo file bằng cách append vào file cũ mà không xác định được phần đã ghi.

Nếu một Step tạo tác dụng phụ không thể lặp an toàn, hãy để mặc định bỏ qua Step đã hoàn tất và thiết kế một quy trình xác nhận/đối soát riêng nếu cần.

## 10. Idempotency là điều kiện quan trọng

Khi bật `allowStartIfComplete`, Step có thể thực hiện lại sau khi lần chạy trước đã commit. Do đó, các thao tác phải được thiết kế để chạy lại mà không tạo trạng thái sai hoặc tác dụng phụ trùng.

Một thao tác idempotent có thể được lặp lại với cùng định danh nghiệp vụ mà không làm thay đổi kết quả ngoài ý muốn.

Ví dụ, thay vì insert vô điều kiện dữ liệu staging:

```sql
INSERT INTO staging_customer(batch_id, customer_id, full_name)
VALUES (:batchId, :customerId, :fullName);
```

có thể dùng unique key theo `(batch_id, customer_id)` kết hợp upsert hoặc xóa và nạp lại phạm vi batch trong một transaction có kiểm soát. Cú pháp upsert phụ thuộc database, nhưng mục tiêu là cùng một lần xử lý không tạo bản ghi trùng.

Với service ngoài, dùng idempotency key ổn định:

```java
String key = "refresh-customer-summary:" + batchId;

restClient.post()
        .uri("/customer-summaries/refresh")
        .header("Idempotency-Key", key)
        .body(new RefreshRequest(batchId))
        .retrieve()
        .toBodilessEntity();
```

Ví dụ chỉ có tác dụng nếu hệ thống đích thực sự hỗ trợ và thực thi idempotency key. Không tạo key mới cho mỗi lần restart nếu các lần gọi đều đại diện cho cùng một hành động nghiệp vụ.

## 11. Transaction và dữ liệu đã commit

`allowStartIfComplete` không mở một transaction bao trùm toàn bộ Job. Khi Step hoàn tất, transaction của Tasklet hoặc các chunk đã commit theo cấu hình. Nếu một Step phía sau thất bại, những thay đổi đã commit của Step trước vẫn tồn tại.

Khi restart và Step trước được phép chạy lại, nó thực hiện công việc trong transaction mới. Transaction mới không tự động xóa hoặc rollback các thay đổi của lần chạy trước.

Ví dụ:

```text
Lần chạy đầu:
  refreshStagingStep -> commit dữ liệu staging
  importStep         -> commit một số chunk
  reportStep         -> FAILED

Restart:
  refreshStagingStep -> chạy lại và commit lần nữa
  importStep         -> được xử lý theo trạng thái/checkpoint
  reportStep         -> chạy lại
```

Nếu refresh Step xóa và nạp lại staging, cần bảo đảm Step import khi restart vẫn đọc đúng snapshot và không bị ảnh hưởng bởi dữ liệu đã thay đổi ngoài dự kiến. Nếu staging được dùng bởi Job khác, cần cô lập theo batch ID hoặc version để tránh một lần refresh làm thay đổi dữ liệu của quy trình khác.

## 12. ExecutionContext và dữ liệu cũ khi Step chạy lại

Step có thể sử dụng `StepExecutionContext` để lưu checkpoint hoặc trạng thái trung gian. Khi Step được thực thi lại trong quá trình restart, không nên mặc định rằng mọi key trong context đều trống hoặc mọi giá trị cũ đều còn phù hợp.

Một số nguyên tắc:

- Khởi tạo hoặc ghi đè key mà Step sở hữu trước khi dùng.
- Dùng tên key có namespace để tránh xung đột.
- Không dùng giá trị checkpoint cũ nếu lần chạy lại cần bắt đầu một quy trình làm mới từ đầu.
- Giữ các giá trị định danh batch/snapshot ổn định để xác định đúng dữ liệu nguồn.
- Kiểm thử context thực tế sau restart với reader và writer đang sử dụng.

Ví dụ Tasklet có thể đặt lại trạng thái bước chuẩn bị:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    ExecutionContext context = contribution
            .getStepExecution()
            .getExecutionContext();

    context.putLong("preparedRecordCount", 0L);
    context.putString("preparationStatus", "STARTED");

    long count = preparationService.rebuildCurrentBatch();

    context.putLong("preparedRecordCount", count);
    context.putString("preparationStatus", "COMPLETED");

    return RepeatStatus.FINISHED;
}
```

Đây là ví dụ minh họa. Cần lưu ý thời điểm Spring Batch persist ExecutionContext theo lifecycle và transaction của Step. Nếu dữ liệu cần được Step tiếp theo sử dụng, hãy bảo đảm nó được lưu bền vững trước khi Step kết thúc và không chỉ tồn tại trong bộ nhớ.

## 13. Ví dụ Job hoàn chỉnh với Step được chạy lại

Giả sử Job có ba Step: làm mới dữ liệu tham chiếu, import dữ liệu và tạo báo cáo. Nếu import hoặc báo cáo thất bại, nghiệp vụ yêu cầu làm mới dữ liệu tham chiếu trước khi tiếp tục.

```java
@Bean
Job customerBatchJob(
        JobRepository jobRepository,
        Step refreshReferenceDataStep,
        Step importCustomersStep,
        Step generateReportStep) {

    return new JobBuilder("customerBatchJob", jobRepository)
            .start(refreshReferenceDataStep)
            .next(importCustomersStep)
            .next(generateReportStep)
            .build();
}

@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        RefreshReferenceDataTasklet tasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Trong lần chạy đầu, nếu refresh và import hoàn tất nhưng báo cáo thất bại, lần restart cùng JobInstance sẽ cho phép refresh chạy lại. Import Step có thể được bỏ qua nếu đã `COMPLETED`, hoặc tiếp tục theo checkpoint nếu trước đó thất bại. Báo cáo được thực thi lại theo trạng thái của nó.

Đây chỉ là lựa chọn đúng nếu việc refresh không làm thay đổi dữ liệu mà import đã dùng theo cách gây mất nhất quán. Nếu import phải tiếp tục trên đúng snapshot đã dùng trước khi lỗi, cần lưu snapshot/version và tái tạo đúng snapshot đó, không đơn giản đọc dữ liệu mới nhất.

## 14. Kiểm thử `allowStartIfComplete`

Nên có integration test chứng minh Step đã hoàn tất được chạy lại khi JobInstance restart, đồng thời Step hoàn tất khác vẫn giữ hành vi mặc định.

Một kịch bản test:

1. `prepareStep` tăng một bộ đếm bền vững hoặc ghi một bản ghi có version.
2. `processStep` hoàn tất.
3. `finalStep` thất bại có chủ đích trong lần đầu.
4. Xác nhận JobExecution đầu tiên là `FAILED` và `prepareStep` đã chạy một lần.
5. Launch lại Job bằng cùng identifying JobParameters.
6. Xác nhận `prepareStep` chạy lần thứ hai vì đã bật `allowStartIfComplete(true)`.
7. Xác nhận Step đã `COMPLETED` nhưng không bật thuộc tính không chạy lại.
8. Xác nhận Job hoàn tất và dữ liệu đầu ra không bị trùng.

Ví dụ khung kiểm thử:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchRestartTestConfiguration.class)
class AllowStartIfCompleteTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    PreparationAuditRepository auditRepository;

    @Test
    void rerunsCompletedStepWhenJobIsRestarted() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "BATCH-100", true)
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, auditRepository.countByBatchId("BATCH-100"));

        JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
        assertEquals(2, auditRepository.countByBatchId("BATCH-100"));
    }
}
```

Ví dụ giả định `finalStep` chỉ thất bại ở lần đầu, audit repository ghi nhận mỗi lần `prepareStep` chạy và test dùng cùng JobRepository/database qua hai lần launch. Trong test thực tế, cần xác nhận StepExecution mới của lần restart, các bộ đếm và dữ liệu đầu ra. Không dùng `RunIdIncrementer` hoặc thêm identifying parameter mới cho lần restart vì sẽ tạo JobInstance khác.

## 15. Kiểm thử trường hợp không bật `allowStartIfComplete`

Nên có test đối chứng: cấu hình Step đã hoàn tất với thuộc tính mặc định, làm một Step phía sau thất bại rồi restart Job. Xác nhận Step đã hoàn tất không được chạy lại.

Test đối chứng giúp chứng minh rằng:

- `allowStartIfComplete(true)` thực sự thay đổi hành vi của Step được cấu hình.
- Những Step khác không bị ảnh hưởng.
- Job restart vẫn dùng cùng JobInstance.
- Step thất bại được chạy lại theo restart behavior bình thường.

Không chỉ assert số lần gọi một mock trong bộ nhớ nếu mục tiêu là kiểm tra transaction và restart. Dùng repository/database test để xác nhận trạng thái đã lưu qua hai lần JobExecution.

## 16. Tương tác với flow transition

`allowStartIfComplete` không thay thế flow transition. Nó chỉ cho phép Step đã hoàn tất được thực thi lại khi restart; flow vẫn quyết định Step tiếp theo dựa trên cấu hình `.next()` hoặc transition theo `ExitStatus`.

Ví dụ, nếu Job có flow điều kiện:

```java
return new JobBuilder("validationJob", jobRepository)
        .start(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("FAILED").to(rejectStep)
        .end()
        .build();
```

Nếu `validateStep` được bật `allowStartIfComplete(true)` và JobInstance được restart, Step có thể chạy lại; kết quả ExitStatus mới của lần thực thi sẽ tham gia điều khiển flow. Hãy bảo đảm các transition bao phủ những trạng thái mà Step có thể trả về sau khi chạy lại.

Nếu một Step hoàn tất với ExitStatus tùy chỉnh, không nên giả định nó tương đương `COMPLETED` trong mọi flow. Hãy kiểm tra điều kiện transition và listener đang sửa ExitStatus.

## 17. Tác động khi Step nằm trong split flow hoặc partitioning

Trong Job có nhiều flow branch hoặc partition, cần hiểu phạm vi Step được cấu hình. Mỗi worker StepExecution có trạng thái riêng; việc cho phép một Step đã hoàn tất chạy lại có thể khiến phần công việc đó được thực hiện lại khi Job restart, tùy cấu hình flow và cơ chế partition.

Với partitioning, không nên bật thuộc tính một cách máy móc cho worker Step. Cần xem partition nào đã hoàn tất, partition nào thất bại, partition name và checkpoint có ổn định không. Nếu worker đã hoàn tất nhưng được chạy lại, writer cần idempotent theo partition hoặc business key.

Với split flow, các Step ở nhánh khác nhau có thể đã commit độc lập. Nếu một nhánh thất bại và Job restart, Step hoàn tất trong nhánh khác thường được bỏ qua theo mặc định. Chỉ bật `allowStartIfComplete` nếu nhánh đó cần tái tạo đầu ra và việc chạy lại an toàn.

## 18. Theo dõi việc Step được chạy lại

Khi bật `allowStartIfComplete`, nên theo dõi số lần Step bắt đầu trong một JobInstance để người vận hành hiểu tại sao một Step đã từng `COMPLETED` lại xuất hiện thêm StepExecution.

Các thông tin hữu ích:

- JobInstance ID và JobExecution ID.
- Step name và StepExecution ID.
- Trạng thái StepExecution trước đó và lần hiện tại.
- Số lần Step bắt đầu trong JobInstance.
- `allowStartIfComplete` và `startLimit` đã cấu hình.
- Business key hoặc batch ID của dữ liệu được làm mới.
- Số bản ghi tạo mới, cập nhật, xóa hoặc thay thế.
- Thời gian chạy lại và kết quả cuối cùng.

Log nên phân biệt “Step chạy lần đầu” với “Step được thực thi lại do Job restart”. Có thể dùng `StepExecution` và `JobExecution` metadata để liên kết các lần chạy, không cần tự ghi đè các bảng `BATCH_*`.

## 19. Các lỗi thường gặp

**Cho rằng thuộc tính làm Step luôn chạy ở mọi lần launch:** nó điều chỉnh việc bỏ qua Step đã hoàn tất khi JobInstance được restart; JobInstance mới vốn đã chạy Step theo flow.

**Cho rằng có thể restart Job đã `COMPLETED`:** một JobInstance đã hoàn tất không thể được chạy lại chỉ nhờ `allowStartIfComplete`; cần JobInstance mới nếu muốn một lần chạy nghiệp vụ mới.

**Bật cho mọi Step:** có thể lặp lại thanh toán, gửi thông báo, insert dữ liệu hoặc các tác dụng phụ không thể đảo ngược.

**Nhầm với retry:** retry xử lý lỗi trong một lần thực thi; `allowStartIfComplete` cho phép chạy lại Step đã hoàn tất khi restart Job.

**Nhầm với `startLimit`:** một thuộc tính cho phép chạy lại Step đã hoàn tất; thuộc tính kia giới hạn số lần Step được bắt đầu.

**Không thiết kế idempotency:** Step có thể ghi trùng hoặc thực hiện tác dụng phụ nhiều lần khi được chạy lại.

**Giả định ExecutionContext trống:** Step có thể phụ thuộc trạng thái đã lưu. Cần khởi tạo hoặc ghi đè key thuộc quyền sở hữu của Step và kiểm thử reader/checkpoint.

**Không cố định dữ liệu nguồn:** Step làm mới dữ liệu từ nguồn thay đổi có thể tạo kết quả khác với lần chạy trước, khiến các Step phía sau không còn nhất quán.

**Không kiểm thử restart thực tế:** chỉ unit test thuộc tính không chứng minh được hành vi với JobRepository, StepExecution và transaction của ứng dụng.

## Kết luận

`allowStartIfComplete(true)` cho phép một Step đã `COMPLETED` được thực thi lại khi JobInstance được restart. Mặc định, Spring Batch bỏ qua Step đã hoàn tất để tránh lặp công việc và tác dụng phụ. Thuộc tính này hữu ích khi một Step tạo dữ liệu trung gian cần được làm mới trước khi tiếp tục, nhưng chỉ nên bật khi đầu ra có thể tái tạo và thao tác an toàn khi lặp. Nó khác với retry, `startLimit` và khả năng restart của Job; không cho phép chạy lại một JobInstance đã hoàn tất. Hãy thiết kế idempotency, kiểm soát dữ liệu nguồn và ExecutionContext, theo dõi từng StepExecution, đồng thời kiểm thử bằng hai lần launch cùng identifying JobParameters để xác nhận Step được chạy lại đúng như mong muốn.
