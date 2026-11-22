# Step bắt đầu, đang chạy, hoàn tất và thất bại

Trong Spring Batch, `Step` là một đơn vị công việc nằm bên trong một `Job`. Một Job thường gồm nhiều Step nối tiếp hoặc rẽ nhánh theo kết quả của Step trước đó. Khi một Step được thực thi, Spring Batch tạo một đối tượng `StepExecution` để ghi lại lần thực thi cụ thể đó: thời điểm bắt đầu và kết thúc, trạng thái, số item đã đọc/ghi, số lần bỏ qua, thông tin lỗi và dữ liệu checkpoint.

Vòng đời của Step giúp ứng dụng và người vận hành biết một phần công việc đã bắt đầu hay chưa, đang chạy, hoàn tất, dừng có kiểm soát hay thất bại. Hiểu đúng các trạng thái này cũng giúp quyết định khi nào có thể restart Job và khi nào cần điều tra trước khi chạy lại.

## 1. Step và StepExecution khác nhau như thế nào?

`Step` mô tả công việc cần thực hiện. Ví dụ, `importCustomersStep` có thể đọc file khách hàng, kiểm tra từng dòng và ghi dữ liệu hợp lệ vào database. Định nghĩa Step thường được tạo thành bean và được tham chiếu trong một Job.

`StepExecution` đại diện cho một lần chạy của Step trong một `JobExecution`. Nó lưu trạng thái của lần chạy đó. Nếu Job được restart sau khi thất bại, Spring Batch tạo một `JobExecution` mới và có thể tạo `StepExecution` mới cho Step cần chạy lại. Vì vậy, không nên coi Step bean và StepExecution là cùng một đối tượng:

- `Step` là định nghĩa có thể được sử dụng qua nhiều lần chạy.
- `StepExecution` là dữ liệu theo dõi một lần thực thi cụ thể của Step.
- Một `JobExecution` chứa các `StepExecution` tương ứng với những Step được thực hiện trong lần chạy Job đó.

Ví dụ, Job import khách hàng có ba Step:

```text
customerImportJob
       |
       v
validateFileStep
       |
       v
importCustomersStep
       |
       v
writeSummaryStep
```

Mỗi khi một Step được chạy, Spring Batch ghi một bản ghi thực thi tương ứng trong metadata của JobRepository. Nhờ đó, ứng dụng có thể tra cứu lịch sử từng Step thay vì chỉ biết Job cuối cùng thành công hay thất bại.

## 2. Các trạng thái trong vòng đời Step

Trạng thái của `StepExecution` được biểu diễn bằng `BatchStatus`. Trong quá trình thực thi, trạng thái có thể đi qua các mốc chính sau:

```text
        StepExecution được tạo
                  |
                  v
              STARTING
                  |
                  v
               STARTED
                  |
          +-------+--------+
          |                |
          v                v
      COMPLETED          FAILED

Trường hợp dừng có kiểm soát:
      STARTED -> STOPPING -> STOPPED
```

Đây là sơ đồ khái quát. Một số trạng thái có thể tồn tại rất ngắn hoặc chỉ xuất hiện trong những tình huống vận hành cụ thể. Không phải mọi lần thực thi đều quan sát được tất cả trạng thái trung gian.

### STARTING — Step đang được chuẩn bị

`STARTING` biểu thị StepExecution đã được tạo và quá trình khởi chạy đang được chuẩn bị. Spring Batch thiết lập thông tin thực thi, liên kết StepExecution với JobExecution và chuẩn bị chuyển sang thực hiện Step.

Trạng thái này thường chỉ là giai đoạn ngắn. Trong luồng thực thi thông thường, Step sớm chuyển sang `STARTED`. Nếu một hệ thống giám sát đọc metadata đúng vào thời điểm khởi chạy, nó có thể quan sát được `STARTING`.

### STARTED — Step đang chạy

`STARTED` cho biết Step đã bắt đầu thực hiện công việc. Spring Batch ghi thời điểm bắt đầu và cập nhật metadata. Tùy loại Step, công việc có thể là chạy một `Tasklet`, hoặc lặp qua các item theo mô hình chunk-oriented processing.

Trong thời gian Step chạy, các bộ đếm và trạng thái cần thiết được cập nhật. Với chunk processing, sau mỗi chunk commit thành công, framework lưu tiến độ và checkpoint phù hợp trong JobRepository. Nếu Step xử lý một lượng dữ liệu lớn, trạng thái `STARTED` có thể kéo dài khá lâu.

Khi thấy Step ở trạng thái `STARTED`, người vận hành cần phân biệt một Step thực sự còn chạy với metadata cũ còn sót lại sau khi tiến trình bị dừng đột ngột. Không nên khởi chạy thêm một execution cho cùng JobInstance chỉ vì thấy thời gian chạy lâu; trước tiên cần kiểm tra tiến trình và trạng thái JobExecution hiện tại.

### COMPLETED — Step hoàn tất thành công

`COMPLETED` biểu thị Step đã kết thúc theo luồng thực thi thành công. Spring Batch ghi thời điểm kết thúc, cập nhật metadata và cho phép Job chuyển sang Step tiếp theo hoặc kết thúc nếu đây là Step cuối cùng.

`COMPLETED` không nhất thiết có nghĩa mọi bản ghi đầu vào đều được ghi ra đích. Ví dụ, một Step có thể được cấu hình skip một số item không hợp lệ. Step vẫn có thể hoàn tất với trạng thái `COMPLETED`, trong khi `skipCount` lớn hơn 0. Vì vậy, cần xem cả bộ đếm và kết quả nghiệp vụ, không chỉ nhìn vào trạng thái.

Khi Job được restart, Step đã `COMPLETED` thường được bỏ qua để tránh chạy lại phần việc đã hoàn tất. Có thể thay đổi hành vi đó bằng cấu hình `allowStartIfComplete(true)` khi thực sự cần thực hiện lại Step đã hoàn thành.

### FAILED — Step thất bại

`FAILED` biểu thị Step không thể hoàn tất bình thường do gặp lỗi. Nguyên nhân có thể là exception trong reader, processor hoặc writer; lỗi kết nối database; dữ liệu đầu vào không hợp lệ; hay lỗi từ dịch vụ phụ thuộc.

Spring Batch lưu trạng thái thất bại cùng thông tin exception và các bộ đếm liên quan. Job thường chuyển sang trạng thái thất bại nếu không có luồng xử lý khác được cấu hình cho kết quả của Step.

Khi Step xử lý theo chunk, các chunk đã commit trước thời điểm lỗi vẫn được giữ lại trong database. Chunk đang nằm trong transaction bị rollback nếu transaction đó thất bại. Vì vậy, số item đã đọc có thể lớn hơn số item đã ghi thành công. Khi restart, Spring Batch có thể tiếp tục từ checkpoint đã lưu nếu reader và Step hỗ trợ khôi phục trạng thái.

`FAILED` không có nghĩa là luôn phải chạy toàn bộ Job từ đầu. Nếu Job cho phép restart và metadata còn đầy đủ, người vận hành có thể khắc phục nguyên nhân rồi restart cùng JobInstance. Spring Batch sẽ dựa vào trạng thái của từng Step để xác định phần cần thực hiện tiếp.

## 3. Các trạng thái khác cần biết

Ngoài các trạng thái chính ở trên, `BatchStatus` còn có một số giá trị phục vụ việc dừng và xử lý các tình huống đặc biệt:

| Trạng thái | Ý nghĩa |
|---|---|
| `STOPPING` | Step đang trong quá trình dừng theo yêu cầu; framework cần hoàn tất việc dừng an toàn |
| `STOPPED` | Step đã dừng có kiểm soát; Job có thể được restart nếu cấu hình và trạng thái cho phép |
| `ABANDONED` | StepExecution được đánh dấu không tiếp tục; khi restart, Step tương ứng có thể được bỏ qua |
| `UNKNOWN` | Không thể xác định chắc chắn kết quả thực thi; cần điều tra metadata và tác động nghiệp vụ trước khi tiếp tục |

`STOPPING` thường xuất hiện khi có yêu cầu dừng một Job hoặc Step đang chạy. Framework cố gắng đưa công việc đến ranh giới an toàn để kết thúc. `STOPPED` khác `FAILED`: dừng là một hành động có chủ đích, còn thất bại là kết quả do lỗi.

`ABANDONED` thường được dùng trong quy trình vận hành để đánh dấu một execution không nên được restart. Đây là trạng thái cần được sử dụng có chủ đích vì nó ảnh hưởng đến cách Spring Batch xử lý Step khi chạy lại Job.

`UNKNOWN` cần được xem xét cẩn thận. Nó có thể phản ánh tình huống framework không thể xác định trạng thái cuối cùng, chẳng hạn lỗi nghiêm trọng trong lúc lưu metadata. Không nên tự động restart hoặc xóa metadata để bỏ qua trạng thái này; trước tiên cần đối chiếu dữ liệu đã ghi và xác minh tác dụng phụ của lần chạy trước.

## 4. Vòng đời một Step diễn ra như thế nào?

Với một Step thông thường, trình tự khái quát gồm các giai đoạn sau:

1. **Job bắt đầu:** JobLauncher khởi chạy Job và JobRepository tạo hoặc tra cứu JobInstance, JobExecution.
2. **Job chọn Step:** luồng của Job xác định Step tiếp theo cần chạy. Step đã hoàn tất có thể được bỏ qua khi restart.
3. **Tạo StepExecution:** Spring Batch tạo đối tượng theo dõi lần thực thi Step và gắn nó với JobExecution.
4. **Bắt đầu thực thi:** trạng thái chuyển sang `STARTED`, thời gian bắt đầu và metadata được cập nhật.
5. **Thực hiện công việc:** Tasklet hoặc chu trình đọc, xử lý, ghi item được chạy. Các bộ đếm và checkpoint được cập nhật theo tiến độ.
6. **Kết thúc:** nếu công việc thành công, Step chuyển sang `COMPLETED`; nếu có lỗi không được xử lý, Step chuyển sang `FAILED`; nếu có yêu cầu dừng, Step có thể chuyển qua `STOPPING` đến `STOPPED`.
7. **Cập nhật metadata:** thời gian kết thúc, trạng thái, ExitStatus, exception và ExecutionContext được lưu để theo dõi hoặc restart.

Các callback của listener cho phép ứng dụng gắn logic vào những mốc thích hợp, chẳng hạn ghi log khi Step bắt đầu hoặc thu thập số liệu sau khi Step kết thúc.

## 5. Ví dụ định nghĩa Step và theo dõi trạng thái

Đoạn mã sau minh họa một Step dùng Tasklet trong Spring Batch 5:

```java
@Bean
Step validateFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateFileTasklet) {

    return new StepBuilder("validateFileStep", jobRepository)
            .tasklet(validateFileTasklet, transactionManager)
            .build();
}
```

Khi Job thực thi Step này, Spring Batch quản lý StepExecution và cập nhật trạng thái tương ứng. Ứng dụng có thể dùng `StepExecutionListener` để quan sát vòng đời:

```java
public class StepLoggingListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        System.out.println(
                "Starting step: " + stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        System.out.println(
                "Step status: " + stepExecution.getStatus());
        System.out.println(
                "Read count: " + stepExecution.getReadCount());
        System.out.println(
                "Write count: " + stepExecution.getWriteCount());
        System.out.println(
                "Skip count: " + stepExecution.getSkipCount());

        return null;
    }
}
```

Trong `afterStep`, trả về `null` có nghĩa listener không yêu cầu thay đổi ExitStatus hiện tại. Listener có thể trả về một ExitStatus khác để bổ sung kết quả cho luồng Job, nhưng cần làm việc này có chủ đích vì ExitStatus có thể ảnh hưởng đến bước tiếp theo.

Listener có thể được gắn vào Step khi xây dựng:

```java
@Bean
Step validateFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet validateFileTasklet,
        StepLoggingListener stepLoggingListener) {

    return new StepBuilder("validateFileStep", jobRepository)
            .tasklet(validateFileTasklet, transactionManager)
            .listener(stepLoggingListener)
            .build();
}
```

Trong ứng dụng thực tế, nên dùng logger thay cho `System.out.println`, đồng thời gắn JobExecution ID và StepExecution ID vào log để có thể truy vết một lần chạy cụ thể.

## 6. BatchStatus và ExitStatus không giống nhau

Hai khái niệm này thường xuất hiện cùng nhau nhưng phục vụ hai mục đích khác nhau:

- **`BatchStatus`:** trạng thái vòng đời do Spring Batch quản lý, ví dụ `STARTED`, `COMPLETED`, `FAILED` hoặc `STOPPED`.
- **`ExitStatus`:** mã kết quả mà Step trả về để mô tả kết quả thực thi và hỗ trợ điều khiển luồng Job. ExitStatus có thể chứa exit code mặc định hoặc mã tùy chỉnh.

Ví dụ, một Step có thể có `BatchStatus.COMPLETED` nhưng listener đặt ExitStatus thành `COMPLETED_WITH_WARNINGS` để Job rẽ nhánh sang Step kiểm tra cảnh báo. Điều này hữu ích khi công việc hoàn tất về mặt kỹ thuật nhưng nghiệp vụ cần xử lý tiếp dựa trên kết quả.

Trong flow Job, điều kiện chuyển tiếp thường được khai báo theo exit code của Step. Ví dụ minh họa:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step notifyFailureStep,
        Step createReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importStep)
                .on("FAILED").to(notifyFailureStep)
            .from(importStep)
                .on("*").to(createReportStep)
            .end()
            .build();
}
```

Đoạn flow trên minh họa việc chọn Step tiếp theo theo ExitStatus. Khi xây dựng flow thực tế, cần khai báo đầy đủ các nhánh cần thiết và kiểm tra cách Job kết thúc ở mỗi nhánh. Một ExitStatus tùy chỉnh phải khớp với điều kiện chuyển tiếp đã khai báo.

## 7. Theo dõi Step qua metadata và bộ đếm

Chỉ nhìn vào trạng thái `COMPLETED` hoặc `FAILED` thường chưa đủ để hiểu một Step đã làm gì. `StepExecution` còn lưu các thông tin hữu ích cho vận hành:

| Thuộc tính | Ý nghĩa |
|---|---|
| `startTime` | Thời điểm Step bắt đầu |
| `endTime` | Thời điểm Step kết thúc |
| `lastUpdated` | Thời điểm metadata StepExecution được cập nhật gần nhất |
| `readCount` | Số item đã đọc |
| `writeCount` | Số item đã ghi |
| `filterCount` | Số item bị processor lọc bỏ |
| `readSkipCount` | Số item bị bỏ qua do lỗi khi đọc |
| `processSkipCount` | Số item bị bỏ qua do lỗi khi xử lý |
| `writeSkipCount` | Số item bị bỏ qua do lỗi khi ghi |
| `commitCount` | Số lần transaction của chunk được commit |
| `rollbackCount` | Số lần rollback được ghi nhận |
| `failureExceptions` | Các exception liên quan đến lần thực thi thất bại |
| `executionContext` | Trạng thái được lưu để phục vụ việc tiếp tục hoặc restart |

Các bộ đếm giúp phát hiện vấn đề. Chẳng hạn, nếu `readCount` lớn nhưng `writeCount` thấp, cần xem `filterCount`, các skip count và log để hiểu dữ liệu đã bị lọc hay bị lỗi. Nếu thời gian chạy tăng đột biến, có thể cần kiểm tra database, hệ thống nguồn, hệ thống đích hoặc kích thước chunk.

`JobRepository` lưu metadata phục vụ theo dõi và restart. Ứng dụng có thể truy vấn thông tin thực thi qua các API như `JobExplorer` hoặc các giao diện giám sát được xây dựng trên metadata đó. Nên giữ metadata bền vững trong môi trường cần theo dõi lịch sử hoặc khôi phục sau khi ứng dụng khởi động lại.

## 8. Trạng thái Step ảnh hưởng đến restart như thế nào?

Trạng thái cuối của Step quyết định cách Spring Batch xử lý Step khi Job được restart:

| Trạng thái trước đó | Hành vi thường gặp khi restart |
|---|---|
| `COMPLETED` | Bỏ qua Step đã hoàn thành, trừ khi cấu hình `allowStartIfComplete(true)` |
| `FAILED` | Có thể thực thi lại Step trong JobInstance cũ nếu Job cho phép restart và giới hạn Step chưa bị vượt |
| `STOPPED` | Có thể tiếp tục Job theo trạng thái đã lưu nếu cấu hình cho phép |
| `ABANDONED` | Step được đánh dấu không tiếp tục trong lần restart |
| `UNKNOWN` | Cần xử lý thủ công và xác minh trạng thái trước khi tiếp tục |
| `STARTED` | Có thể đang chạy; cần xác minh execution hiện tại trước khi thao tác |

Với chunk-oriented Step, checkpoint trong ExecutionContext cho phép reader tiếp tục từ vị trí đã lưu. Những chunk đã commit được giữ lại; chunk chưa commit có thể phải xử lý lại. Điều này chỉ hoạt động đúng khi reader lưu được trạng thái, dữ liệu đầu vào ổn định và các thao tác ghi an toàn khi retry.

Nếu Step gọi dịch vụ bên ngoài, gửi email hoặc ghi file, các tác dụng phụ đó có thể không nằm trong transaction database của chunk. Một lần chạy lại có thể lặp lại thao tác đã xảy ra trước khi tiến trình bị dừng. Vì vậy, cần dùng idempotency key, unique constraint, transactional outbox hoặc cơ chế đối soát phù hợp với nghiệp vụ.

## 9. Những lỗi thường gặp khi đọc trạng thái Step

**Nhầm `FAILED` với `STOPPED`:** `FAILED` biểu thị lỗi làm Step không thể hoàn tất bình thường; `STOPPED` biểu thị việc dừng có kiểm soát. Cách khắc phục và quyết định restart có thể khác nhau.

**Cho rằng `COMPLETED` nghĩa là không có bản ghi lỗi:** một Step cho phép skip vẫn có thể hoàn tất. Cần xem skip count và kết quả nghiệp vụ.

**Cho rằng Step `STARTED` chắc chắn vẫn đang hoạt động:** nếu tiến trình bị kill hoặc máy chủ gặp sự cố, metadata có thể chưa phản ánh trạng thái cuối. Cần xác minh tiến trình trước khi khởi chạy lại.

**Chỉ xem trạng thái Job mà bỏ qua StepExecution:** Job thất bại có thể do một Step cụ thể. Kiểm tra StepExecution giúp xác định đúng vị trí và nguyên nhân.

**Coi BatchStatus và ExitStatus là một:** BatchStatus mô tả vòng đời; ExitStatus mô tả mã kết quả và có thể điều khiển flow. Thay đổi ExitStatus không đồng nghĩa với việc thay đổi BatchStatus.

**Xóa metadata để làm sạch trạng thái:** metadata chứa thông tin về lịch sử và checkpoint. Xóa tùy tiện có thể làm mất khả năng restart và khiến ứng dụng không biết phần dữ liệu nào đã được xử lý.

## Kết luận

Vòng đời của Step được theo dõi qua `StepExecution`. Step bắt đầu trong giai đoạn `STARTING`, chuyển sang `STARTED` khi thực thi, rồi kết thúc thường ở `COMPLETED` hoặc `FAILED`; nó cũng có thể dừng có kiểm soát qua `STOPPING` và `STOPPED`. `BatchStatus` cho biết trạng thái vòng đời, còn `ExitStatus` cung cấp mã kết quả phục vụ điều khiển flow. Khi vận hành, hãy xem cả trạng thái, bộ đếm, exception và checkpoint trong JobRepository để hiểu chính xác Step đã xử lý đến đâu và có thể restart an toàn hay không.
