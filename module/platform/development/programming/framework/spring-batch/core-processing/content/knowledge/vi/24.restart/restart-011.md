# JobParameters mới và instance mới

Trong Spring Batch, cần phân biệt việc tiếp tục một công việc đang dang dở với việc khởi chạy một lần xử lý nghiệp vụ mới. Hai thao tác này có thể dùng cùng một định nghĩa `Job`, nhưng tạo ra kết quả khác nhau trong metadata.

`JobInstance` đại diện cho một lần chạy nghiệp vụ được nhận diện bởi tên job và các identifying `JobParameters`. `JobExecution` đại diện cho một lần thực thi cụ thể của instance đó. Khi một execution thất bại hoặc dừng và được restart, Spring Batch tạo một `JobExecution` mới cho cùng `JobInstance`. Khi bộ identifying parameters thay đổi, Spring Batch tạo một `JobInstance` mới.

Đây là quy tắc nền tảng để hiểu khi nào nên giữ nguyên parameters để restart và khi nào cần tạo parameters mới để bắt đầu một instance khác.

## 1. JobInstance và JobExecution

Một job có thể được chạy nhiều lần. Spring Batch dùng `JobInstance` để nhận diện một lần xử lý nghiệp vụ, còn `JobExecution` để lưu từng lần thực thi của instance đó.

```text
Job: dailyOrderImport

JobInstance A
  identifying parameters:
    businessDate = 2026-11-15
    region       = NORTH

  JobExecution #1 -> FAILED
  JobExecution #2 -> COMPLETED  (restart cùng instance)

JobInstance B
  identifying parameters:
    businessDate = 2026-11-16
    region       = NORTH

  JobExecution #3 -> STARTED / COMPLETED
```

Trong ví dụ, execution #2 tiếp tục công việc của instance A vì identifying parameters không đổi. Ngày nghiệp vụ mới tạo instance B vì `businessDate` thay đổi.

Có thể ghi nhớ:

- `JobInstance` = tên job + identifying `JobParameters`.
- `JobExecution` = một lần chạy cụ thể của `JobInstance`.
- Một `JobInstance` có thể có nhiều `JobExecution` do restart.
- Mỗi `JobExecution` có trạng thái, thời gian, exit status và metadata riêng.

## 2. Identifying JobParameters quyết định instance

Không phải mọi parameter đều tham gia nhận diện `JobInstance`. Mỗi `JobParameter` có thuộc tính identifying. Các parameter có identifying bằng `true` được dùng để xác định instance; parameter có identifying bằng `false` không làm thay đổi danh tính instance.

Trong Spring Batch 5, có thể chỉ rõ thuộc tính này khi xây dựng parameters:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
```

Ở đây, `businessDate` và `region` là identifying parameters. `requestedBy` là non-identifying parameter nên thay đổi giá trị của nó không tạo một `JobInstance` mới.

Các overload không truyền cờ identifying trong `JobParametersBuilder` có thể có mặc định riêng theo API/phiên bản. Khi muốn thể hiện rõ ý định, đặc biệt với job production, hãy truyền cờ identifying tường minh.

### Chọn parameter nào là identifying?

Một parameter nên là identifying nếu nó thay đổi tập dữ liệu hoặc ý nghĩa nghiệp vụ của lần xử lý. Ví dụ:

| Parameter | Thường nên identifying? | Lý do |
|---|---|---|
| `businessDate` | Có | Xác định ngày dữ liệu cần xử lý |
| `tenantId` hoặc `region` | Có | Xác định phạm vi dữ liệu |
| `sourceFileId` hoặc `inputBatchId` | Có | Xác định nguồn đầu vào của lần nhập |
| `fromDate`, `toDate` | Có | Xác định khoảng dữ liệu |
| `requestedBy` | Thường không | Thông tin audit về người yêu cầu |
| `traceId` | Thường không | Dùng truy vết một lần launch, không xác định dữ liệu nghiệp vụ |
| `notificationEmail` | Tùy nghiệp vụ | Chỉ identifying nếu nó làm thay đổi kết quả xử lý được định nghĩa |

Không chọn identifying chỉ để tránh lỗi instance đã hoàn tất. Nếu một parameter ảnh hưởng đến dữ liệu hoặc kết quả nghiệp vụ, hãy đưa nó vào identity. Nếu chỉ là thông tin quan sát, nên để non-identifying.

## 3. Restart cùng JobInstance bằng parameters giống nhau

Khi một job execution thất bại hoặc bị dừng và instance có thể restart, hãy launch lại cùng job với cùng bộ identifying parameters. Spring Batch tìm lại `JobInstance` cũ và tạo một `JobExecution` mới để tiếp tục.

Ví dụ lần đầu launch:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .toJobParameters();

jobLauncher.run(orderImportJob, parameters);
```

Giả sử execution thất bại ở step `importOrders`. Sau khi khắc phục nguyên nhân, launch lại job với cùng `businessDate` và `region`:

```java
JobParameters restartParameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .toJobParameters();

jobLauncher.run(orderImportJob, restartParameters);
```

Vì định danh không đổi, đây là lần thực thi mới của cùng `JobInstance`, nếu trạng thái trước đó cho phép restart. Spring Batch dùng metadata và checkpoint đã lưu để xác định step nào đã hoàn thành và step nào cần chạy lại.

Không thêm timestamp hoặc `run.id` identifying mới khi mục tiêu là restart. Làm như vậy sẽ tạo `JobInstance` mới và không tiếp tục checkpoint của instance thất bại.

## 4. Khi nào cần JobInstance mới?

Tạo instance mới khi bạn muốn xử lý một lần nghiệp vụ độc lập, chẳng hạn:

- Nhập dữ liệu cho ngày nghiệp vụ khác.
- Chạy cùng job cho một tenant hoặc vùng khác.
- Xử lý một file đầu vào khác.
- Chạy lại một đợt dữ liệu đã hoàn tất như một lần xử lý mới có chủ đích.
- Thực hiện một lần backfill với khoảng ngày hoặc phạm vi khác.

Để tạo instance mới, thay đổi ít nhất một identifying parameter hoặc dùng một incrementer tạo bộ identifying parameters mới.

Ví dụ ngày nghiệp vụ mới:

```java
JobParameters nextBusinessDay = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("region", "NORTH", true)
    .toJobParameters();

jobLauncher.run(orderImportJob, nextBusinessDay);
```

`businessDate` khác nên Spring Batch tạo một `JobInstance` khác. Instance cũ vẫn giữ lịch sử execution của ngày trước.

## 5. Điều gì xảy ra nếu launch lại cùng identifying parameters?

Hành vi phụ thuộc trạng thái hiện tại của `JobInstance` và các execution trước đó.

| Trạng thái instance/execution trước | Launch với cùng identifying parameters |
|---|---|
| Chưa từng chạy | Tạo `JobInstance` và `JobExecution` đầu tiên |
| Execution đang chạy | Thường bị từ chối vì job instance đang chạy |
| Execution thất bại và được phép restart | Tạo `JobExecution` mới cho cùng instance |
| Execution bị dừng và được phép restart | Có thể tạo execution mới để tiếp tục |
| Instance đã hoàn thành | Thường ném `JobInstanceAlreadyCompleteException` |
| Step/job bị giới hạn số lần khởi chạy hoặc bị cấu hình không restart | Launch có thể bị từ chối |

Vì vậy, cùng parameters không có nghĩa lúc nào cũng chạy lại từ đầu. Với instance đã hoàn thành, Spring Batch ngăn launch trùng cùng định danh để tránh vô tình xử lý lại cùng một lần nghiệp vụ.

Nếu cần chạy lại dữ liệu đã hoàn tất, hãy quyết định đó là instance mới với identifying parameter mới hay một quy trình reprocessing được thiết kế rõ ràng. Đừng sửa metadata trực tiếp trong JobRepository để ép job chạy lại.

## 6. Non-identifying parameters không tạo instance mới

Có thể truyền thêm thông tin không tham gia identity:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .addString("requestedBy", "operator-42", false)
    .addString("traceId", "trace-a1b2", false)
    .toJobParameters();
```

Các parameter `requestedBy` và `traceId` không tạo instance mới. Chúng có thể hữu ích cho audit hoặc tracing của một lần launch.

Không nên để non-identifying parameter thay đổi phạm vi dữ liệu hoặc quy tắc xử lý. Nếu `sourceFile` thay đổi nhưng lại được đánh dấu non-identifying, job có thể được coi là cùng instance dù đầu vào đã khác. Điều này làm metadata, restart và tính đúng đắn của dữ liệu trở nên khó hiểu.

Quy tắc thực tế: nếu thay đổi parameter có thể khiến cùng một JobInstance xử lý một tập dữ liệu khác hoặc tạo kết quả nghiệp vụ khác, parameter đó nên là identifying.

## 7. Dùng RunIdIncrementer để tạo instance tiếp theo

`JobParametersIncrementer` tạo bộ parameters kế tiếp từ bộ parameters hiện tại. `RunIdIncrementer` là implementation có sẵn, thường dùng để tăng parameter `run.id` mỗi lần yêu cầu instance mới.

```java
@Bean
Job orderImportJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("orderImportJob", jobRepository)
        .incrementer(new RunIdIncrementer())
        .start(importOrdersStep)
        .build();
}
```

Khi dùng `RunIdIncrementer`, parameters kế tiếp sẽ có `run.id` tăng dần. `run.id` được dùng như một identifying parameter để tạo một `JobInstance` mới.

Ví dụ:

| Lần chạy | businessDate | run.id | Instance |
|---|---|---:|---|
| 1 | 2026-11-15 | 1 | Instance A |
| 2 | 2026-11-15 | 2 | Instance B |
| 3 | 2026-11-15 | 3 | Instance C |

Ví dụ này tạo ba instance riêng cho cùng ngày nghiệp vụ. Hãy chỉ dùng cách đó khi thực sự muốn một lần xử lý mới. Nếu instance A thất bại và cần restart, phải dùng lại parameters của A, không tăng `run.id`.

## 8. JobParametersIncrementer tùy chỉnh

Khi `run.id` không phản ánh ý nghĩa nghiệp vụ, có thể tạo incrementer riêng. Ví dụ, job xử lý từng kỳ đối soát có thể tăng `cycle` hoặc chọn ngày nghiệp vụ kế tiếp.

```java
public class ReconciliationIncrementer implements JobParametersIncrementer {

    @Override
    public JobParameters getNext(JobParameters parameters) {
        String currentCycle = parameters == null
            ? null
            : parameters.getString("cycle");

        long nextCycle = currentCycle == null
            ? 1L
            : Long.parseLong(currentCycle) + 1L;

        return new JobParametersBuilder(parameters == null
                ? new JobParameters()
                : parameters)
            .addString("cycle", Long.toString(nextCycle), true)
            .toJobParameters();
    }
}
```

Incrementer nhận parameters hiện tại và trả về parameters cho instance tiếp theo. Trong ví dụ, `cycle` là identifying nên mỗi giá trị tạo một instance khác.

Khi viết incrementer, cần bảo đảm:

- Kết quả luôn tạo identity mới khi yêu cầu instance tiếp theo.
- Giữ lại các identifying parameters cần thiết khác như tenant hoặc region.
- Không vô tình biến thông tin audit thành identifying parameter.
- Xử lý trường hợp parameters đầu vào null hoặc thiếu key.
- Quy tắc tăng có tính xác định và phù hợp với nghiệp vụ.

Không nên dùng thời gian hiện tại một cách tùy tiện nếu có thể tạo collision hoặc khiến việc vận hành khó xác định instance nào tương ứng với lần nghiệp vụ nào.

## 9. startNextInstance qua JobOperator

Khi job được cấu hình `JobParametersIncrementer`, `JobOperator.startNextInstance(jobName)` có thể yêu cầu Spring Batch tạo parameters tiếp theo và khởi chạy instance kế tiếp.

```java
long executionId = jobOperator.startNextInstance("orderImportJob");
```

`JobOperator` tìm instance gần nhất của job, gọi incrementer đã cấu hình để tạo parameters tiếp theo rồi khởi chạy instance mới. Cách này hữu ích cho các job chạy theo chu kỳ hoặc cần một lệnh vận hành “start next”.

Phương thức này tạo instance tiếp theo theo incrementer; nó không restart instance đang thất bại. Khi cần restart, launch lại bằng identifying parameters của instance cũ hoặc dùng thao tác restart phù hợp qua JobOperator với execution ID đã biết.

## 10. Phân biệt restart, start mới và start next

Ba hành động thường bị nhầm lẫn:

| Hành động | Parameters | Kết quả |
|---|---|---|
| Restart instance thất bại | Giữ nguyên identifying parameters | Tạo JobExecution mới cho cùng JobInstance |
| Start instance mới | Thay đổi identifying parameter | Tạo JobInstance mới |
| Start next instance | Gọi incrementer để tạo parameters kế tiếp | Tạo JobInstance mới theo quy tắc incrementer |

Ví dụ:

- Job nhập ngày 15 thất bại: chạy lại ngày 15 với cùng identifying parameters để restart.
- Job nhập ngày 15 đã hoàn tất, cần nhập ngày 16: thay `businessDate` để tạo instance mới.
- Job cần tạo một đợt chạy tiếp theo với `run.id`: dùng incrementer hoặc `startNextInstance`.

Không dùng một hành động thay cho hành động khác chỉ để vượt trạng thái của JobRepository. Chọn đúng semantics sẽ giúp lịch sử và checkpoint phản ánh chính xác nghiệp vụ.

## 11. Ví dụ hoàn chỉnh với businessDate và run.id

Job dưới đây xử lý dữ liệu theo ngày. `businessDate` xác định dữ liệu nghiệp vụ, còn `requestedBy` chỉ phục vụ audit.

```java
@Bean
Job dailyImportJob(
        JobRepository jobRepository,
        Step dailyImportStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
        .start(dailyImportStep)
        .build();
}

JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();

jobLauncher.run(dailyImportJob, parameters);
```

Khi execution thất bại, dùng lại `businessDate=2026-11-15` để restart. Nếu ngày tiếp theo là 16, thay identifying parameter:

```java
JobParameters nextDay = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
```

Nếu nghiệp vụ cho phép chạy lại cùng ngày như một instance hoàn toàn mới, có thể thêm identifying `run.id` hoặc `reprocessVersion`. Hãy ghi rõ lý do reprocess và bảo đảm writer có chính sách idempotency/upsert phù hợp.

## 12. JobParameters và tính duy nhất của dữ liệu đầu vào

Identifying parameters nên mô tả ổn định tập dữ liệu đầu vào của một instance. Ví dụ nếu job đọc file, có thể dùng `sourceFileId` hoặc một mã batch được cấp bởi hệ thống nguồn.

Không nên chỉ dùng tên file nếu cùng một đường dẫn có thể được ghi đè bằng nội dung khác. Hai file cùng tên nhưng khác nội dung có thể bị coi là cùng một instance. Có thể dùng ID file bất biến, checksum hoặc version nguồn làm identifying parameter.

Với job theo khoảng thời gian, cần xác định timezone và quy ước biên rõ ràng. `fromDate=2026-11-01` và `toDate=2026-11-15` phải có semantics ổn định, chẳng hạn khoảng nửa mở `[from, to)`, để restart không vô tình thay đổi dữ liệu.

## 13. Restart và checkpoint không phụ thuộc vào incrementer

Incrementer tạo parameters cho instance mới. Nó không lưu vị trí reader, không khôi phục chunk và không quyết định step nào đã hoàn thành.

Khả năng restart phụ thuộc vào:

- JobRepository lưu metadata của JobInstance, JobExecution và StepExecution.
- Reader hoặc tasklet lưu checkpoint phù hợp trong `ExecutionContext`.
- Step name và cấu trúc job đủ ổn định để metadata cũ được đối chiếu.
- JobInstance đang ở trạng thái có thể restart.
- Writer và side effect bên ngoài an toàn khi một phần công việc được thực hiện lại.

Nếu reader không lưu state hoặc nguồn đầu vào đã thay đổi, restart có thể đọc sai vị trí hoặc xử lý trùng. Identifying parameters giúp chọn đúng instance; checkpoint giúp tiếp tục đúng tiến độ. Hai cơ chế bổ sung cho nhau.

## 14. Identifying parameters và concurrency

JobRepository bảo vệ việc tạo instance để hai lần launch cùng job với cùng identifying parameters không vô tình tạo hai JobInstance độc lập. Nếu một instance đang chạy, lần launch trùng thường bị từ chối với lỗi trạng thái phù hợp.

Nếu cần hai lần xử lý đồng thời cho cùng một ngày nhưng phạm vi nghiệp vụ khác nhau, hãy thêm identifying parameter mô tả phạm vi thực sự, ví dụ `tenantId`, `sourceBatchId` hoặc `reprocessVersion`. Không thêm một giá trị ngẫu nhiên nếu nó không đại diện cho một khác biệt nghiệp vụ được quản lý.

Khi dùng non-identifying parameters khác nhau cho các lần launch của cùng instance, hãy thận trọng: chúng không tạo danh tính mới. Đừng dựa vào chúng để thay đổi input hoặc logic xử lý theo cách làm restart không còn tái lập được.

## 15. Kiểm tra JobParameters trước khi launch

Job nên xác thực parameters bắt buộc trước khi bắt đầu xử lý. Có thể dùng `DefaultJobParametersValidator` hoặc validator tùy chỉnh để kiểm tra key, kiểu và quan hệ giữa các giá trị.

Ví dụ validator bắt buộc có `businessDate` và `region`:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
        new String[] { "businessDate", "region" },
        new String[] { "requestedBy", "traceId" }
    );
}
```

Đăng ký validator trên job:

```java
return new JobBuilder("dailyImportJob", jobRepository)
    .validator(importParametersValidator)
    .start(dailyImportStep)
    .build();
```

Validator giúp phát hiện thiếu parameter trước khi reader hoặc writer thực hiện side effect. Với ngày tháng, số lượng hoặc khoảng thời gian, nên kiểm tra định dạng và điều kiện nghiệp vụ trong validator hoặc một bước validation riêng.

## 16. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Thêm timestamp identifying khi muốn restart | Tạo JobInstance mới, mất liên kết với checkpoint cũ | Giữ nguyên identifying parameters của instance thất bại |
| Launch lại instance đã COMPLETED với cùng parameters | `JobInstanceAlreadyCompleteException` | Tạo identity mới nếu thực sự cần một lần nghiệp vụ mới |
| Đánh dấu input parameter là non-identifying | Hai tập dữ liệu khác nhau có thể bị coi là cùng instance | Đánh dấu identifying mọi parameter làm thay đổi phạm vi dữ liệu |
| Dùng `run.id` cho mọi lần restart | Tạo instance mới thay vì tiếp tục instance cũ | Chỉ tăng `run.id` khi muốn instance mới |
| Nghĩ incrementer lưu checkpoint | Không khôi phục được tiến độ step | Dùng ExecutionContext/ItemStream cho checkpoint |
| Thêm identifying parameter ngẫu nhiên | Khó truy vết, dễ tạo nhiều instance không cần thiết | Dùng khóa nghiệp vụ ổn định và có ý nghĩa |
| Đổi tên job hoặc step tùy tiện | Metadata cũ khó được restart theo cấu trúc mới | Giữ tên ổn định hoặc lập kế hoạch migration |
| Dùng non-identifying parameter để đổi nguồn dữ liệu | Restart có thể chạy với input khác | Đưa source identity vào identifying parameters |

## 17. Quy trình quyết định restart hay tạo instance mới

Khi vận hành job, hãy trả lời theo thứ tự:

1. Đây có phải cùng một lần xử lý nghiệp vụ hay là một lần mới?
2. Nếu cùng lần xử lý, xác định chính xác bộ identifying parameters ban đầu.
3. Kiểm tra trạng thái JobInstance và execution gần nhất trong JobRepository.
4. Nếu execution thất bại/dừng và có thể restart, launch lại với cùng identifying parameters.
5. Nếu cần xử lý input hoặc kỳ nghiệp vụ mới, thay identifying parameter tương ứng.
6. Nếu cần instance mới cho cùng input đã hoàn tất, dùng một identifying version/reprocess key có ý nghĩa hoặc incrementer được cấu hình.
7. Xác nhận checkpoint, input snapshot và writer idempotency trước khi restart/reprocess.
8. Ghi audit lý do tạo instance mới để phân biệt chạy định kỳ với chạy lại có chủ đích.

## 18. Kiểm thử identity và restart

Integration test nên dùng `JobRepository` thực tế hoặc cấu hình test tương đương để kiểm tra semantics identity.

Các trường hợp cần có:

1. Launch lần đầu với identifying parameters: tạo một JobInstance và JobExecution.
2. Launch cùng identifying parameters khi instance đang chạy: lần launch trùng bị từ chối.
3. Làm execution thất bại rồi launch cùng identifying parameters: tạo JobExecution mới cho cùng JobInstance nếu restart được phép.
4. Thay một identifying parameter: tạo JobInstance mới.
5. Chỉ thay non-identifying parameter: không tạo JobInstance mới.
6. Launch lại instance đã hoàn tất với cùng identifying parameters: xác nhận bị từ chối theo quy tắc instance đã hoàn tất.
7. Dùng incrementer: xác nhận identifying parameter được tăng và instance mới được tạo.
8. Restart reader có checkpoint: xác nhận tiếp tục từ vị trí đã commit.
9. Reprocess instance mới: xác nhận writer không tạo side effect trùng ngoài dự kiến.

Kiểm tra cả `JobInstance` ID, `JobExecution` ID, parameters đã lưu, trạng thái step và dữ liệu đầu ra. Chỉ kiểm tra job status không đủ để chứng minh identity được tạo đúng.

## Kết luận

`JobInstance` được xác định bởi tên job và các identifying `JobParameters`; mỗi lần launch hoặc restart là một `JobExecution` thuộc instance đó. Muốn restart công việc đang dang dở, giữ nguyên identifying parameters và để Spring Batch sử dụng metadata/checkpoint đã lưu. Muốn bắt đầu một lần xử lý nghiệp vụ mới, thay đổi identifying parameter hoặc dùng `JobParametersIncrementer` để tạo bộ parameters tiếp theo.

Chọn identifying parameters theo phạm vi dữ liệu và ý nghĩa nghiệp vụ. Dùng non-identifying parameters cho thông tin audit/tracing không làm thay đổi kết quả. `RunIdIncrementer` và `startNextInstance` phù hợp khi cần instance tiếp theo; chúng không thay thế restart. Kết hợp identity ổn định, checkpoint bền vững và writer idempotent để vận hành job an toàn.
