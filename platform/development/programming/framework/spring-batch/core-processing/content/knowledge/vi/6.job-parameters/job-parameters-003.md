# Parameter identifying và non-identifying

Trong Spring Batch, mỗi lần khởi chạy Job đều nhận một tập `JobParameters`. Mỗi parameter có tên, giá trị, kiểu dữ liệu và một thuộc tính cho biết nó có tham gia định danh lần chạy logic hay không. Thuộc tính này được gọi là **identifying** hoặc **non-identifying**.

Sự phân biệt này quyết định Spring Batch xem hai lần launch là cùng một `JobInstance` hay hai instance khác nhau. Vì vậy, identifying parameters cần phản ánh đúng đơn vị công việc nghiệp vụ; non-identifying parameters phù hợp với thông tin phụ trợ không làm thay đổi danh tính của công việc. Chọn sai có thể khiến Job không restart được, vô tình tạo instance mới hoặc xử lý trùng dữ liệu.

## 1. JobParameters gồm những gì?

`JobParameters` là tập hợp các tham số được truyền vào Job khi gọi `JobLauncher.run(job, parameters)`. Ví dụ, một Job đối soát có thể nhận ngày đối soát, mã file đầu vào, người yêu cầu chạy và địa chỉ nhận thông báo.

Mỗi parameter có các thành phần:

- **Tên:** khóa để Job truy cập giá trị, ví dụ `businessDate`.
- **Giá trị:** dữ liệu đầu vào, ví dụ `2026-11-15`.
- **Kiểu dữ liệu:** chuỗi, số nguyên dài, số thực, ngày hoặc kiểu được Spring Batch hỗ trợ trong phiên bản đang dùng.
- **Cờ identifying:** cho biết parameter có tham gia xác định `JobInstance` hay không.

Có thể tạo parameters bằng `JobParametersBuilder`:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .addString("sourceFile", "settlement-20261115-v2.csv", true)
        .addLong("requestedBy", 1024L, false)
        .addString("notificationEmail", "ops@example.com", false)
        .toJobParameters();
```

Trong các lời gọi trên, đối số boolean cuối cùng là cờ identifying:

- `true`: parameter tham gia định danh JobInstance.
- `false`: parameter được lưu cùng execution nhưng không tham gia định danh JobInstance.

Ví dụ sử dụng overload có cờ boolean giúp ý định của từng parameter được thể hiện rõ trong code. Các kiểu và overload cụ thể có thể khác theo phiên bản Spring Batch; hãy dùng API tương ứng với phiên bản dự án.

## 2. Identifying parameters là gì?

Identifying parameters là những giá trị xác định một đơn vị chạy nghiệp vụ. Spring Batch kết hợp tên Job với toàn bộ tập identifying parameters để xác định `JobInstance`.

Giả sử Job `dailySettlementJob` chạy đối soát theo ngày. Nếu `businessDate` là identifying parameter, hai lần launch có ngày khác nhau sẽ tạo hai JobInstance:

```text
dailySettlementJob
    + businessDate=2026-11-15
        -> JobInstance A

dailySettlementJob
    + businessDate=2026-11-16
        -> JobInstance B
```

Nếu Job nhận nhiều identifying parameters, toàn bộ tổ hợp giá trị được dùng để phân biệt instance. Ví dụ, cả `businessDate` và `sourceFileVersion` đều identifying:

| businessDate | sourceFileVersion | JobInstance |
|---|---|---|
| 2026-11-15 | v1 | Instance A |
| 2026-11-15 | v2 | Instance B |
| 2026-11-16 | v1 | Instance C |

Thay đổi bất kỳ identifying parameter nào, thêm hoặc bỏ một identifying parameter đều có thể tạo ra một định danh instance khác. Do đó, hãy chọn những giá trị mô tả chính xác phạm vi dữ liệu hoặc kỳ nghiệp vụ cần xử lý.

Những identifying parameters thường gặp:

- Ngày hoặc kỳ nghiệp vụ của báo cáo, đối soát, tính phí.
- Mã file hoặc phiên bản bất biến của file đầu vào.
- Mã lô dữ liệu (batch ID) từ hệ thống nguồn.
- Phạm vi dữ liệu, chẳng hạn mã tenant hoặc khoảng ngày cần xử lý, nếu phạm vi đó làm thay đổi nội dung công việc.
- Mã lần xử lý được nghiệp vụ cấp phát khi cho phép chạy lại cùng kỳ như một công việc mới.

Một identifying parameter nên có ý nghĩa nghiệp vụ rõ ràng. Không nên đánh dấu một giá trị là identifying chỉ để tạo ra một khóa duy nhất cho mỗi lần gọi API.

## 3. Non-identifying parameters là gì?

Non-identifying parameters vẫn là đầu vào của Job và vẫn có thể được lưu trong metadata của từng JobExecution. Điểm khác biệt là chúng không tham gia xác định `JobInstance`.

Ví dụ, `requestedBy` ghi nhận người vận hành đã yêu cầu Job và `notificationEmail` cho biết nơi gửi thông báo. Nếu hai giá trị này thay đổi nhưng identifying parameters không đổi, Spring Batch vẫn xem lần launch thuộc cùng JobInstance.

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("sourceFile", sourceFile, true)
        .addLong("requestedBy", operatorId, false)
        .addString("notificationEmail", email, false)
        .toJobParameters();
```

Các non-identifying parameters thường phù hợp với:

- Người hoặc hệ thống yêu cầu chạy Job.
- Địa chỉ nhận thông báo vận hành.
- Nhãn theo dõi, mã ticket hoặc thông tin ghi nhận yêu cầu.
- Tùy chọn trình bày báo cáo không làm thay đổi dữ liệu nghiệp vụ được xử lý.

Tuy nhiên, không phải mọi thông tin có vẻ phụ trợ đều nên là non-identifying. Nếu một parameter làm thay đổi dữ liệu được tính, quy tắc nghiệp vụ, tập bản ghi được đọc hoặc tác dụng phụ được tạo ra, nó có thể ảnh hưởng đến tính nhất quán khi restart. Khi đó, cần đưa nó vào định danh hoặc lưu một snapshot bất biến gắn với JobInstance.

## 4. So sánh identifying và non-identifying

| Tiêu chí | Identifying | Non-identifying |
|---|---|---|
| Tham gia xác định JobInstance | Có | Không |
| Được Job truy cập khi thực thi | Có | Có |
| Được lưu trong metadata execution | Có | Có |
| Thay đổi giá trị có tạo JobInstance khác? | Có | Không |
| Vai trò điển hình | Xác định đơn vị công việc nghiệp vụ | Bổ sung thông tin cho lần thực thi |
| Ví dụ | Ngày đối soát, mã file và phiên bản dữ liệu | Người yêu cầu, email thông báo, mã ticket |

Điểm cần nhớ là cờ identifying không quyết định parameter có được dùng trong Job hay không. Cả hai loại đều có thể được đọc trong Step. Cờ này chỉ quyết định parameter có tham gia định danh JobInstance.

## 5. Hai lần launch được xem là cùng JobInstance khi nào?

Hai lần launch hướng đến cùng JobInstance khi chúng có cùng tên Job và cùng tập identifying parameters. Giá trị của non-identifying parameters không làm thay đổi định danh đó.

Ví dụ, lần launch thứ nhất:

```java
JobParameters firstRun = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("sourceFile", "settlement-v2.csv", true)
        .addLong("requestedBy", 100L, false)
        .toJobParameters();
```

Lần launch thứ hai:

```java
JobParameters secondRun = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("sourceFile", "settlement-v2.csv", true)
        .addLong("requestedBy", 200L, false)
        .toJobParameters();
```

Hai lần launch có cùng tên Job, cùng `businessDate` và `sourceFile`. Dù `requestedBy` khác nhau, chúng vẫn nhắm đến cùng JobInstance.

Ngược lại, nếu `sourceFile` thay từ `settlement-v2.csv` sang `settlement-v3.csv` và parameter này là identifying, lần launch mới tạo JobInstance khác.

## 6. Ảnh hưởng đến restart

Spring Batch phân biệt `JobInstance` và `JobExecution`:

- `JobInstance` đại diện cho một lần chạy logic, được xác định bởi tên Job và identifying parameters.
- `JobExecution` là một lần thực thi cụ thể của JobInstance.

Một JobInstance có thể có nhiều JobExecution khi execution trước thất bại hoặc được dừng rồi restart.

```text
Job: dailySettlementJob
Identifying parameters:
  businessDate=2026-11-15
  sourceFile=settlement-v2.csv
                  |
                  v
             JobInstance
                  |
          +-------+-------+
          |               |
          v               v
    JobExecution 1   JobExecution 2
       FAILED          COMPLETED
          |               ^
          +--- restart ---+
```

Để restart một JobInstance đã thất bại, ứng dụng cần khởi chạy Job với cùng tên Job và cùng identifying parameters. Spring Batch tra cứu instance đó trong `JobRepository` và kiểm tra trạng thái trước đó. Nếu Job và Step cho phép restart, framework tạo JobExecution mới cho cùng instance.

Một số kết quả thường gặp:

| Trạng thái trước đó | Kết quả khi launch với cùng identifying parameters |
|---|---|
| Chưa có JobInstance | Tạo JobInstance và JobExecution mới |
| Đang có execution chạy | Có thể nhận `JobExecutionAlreadyRunningException` |
| Đã `COMPLETED` | Có thể nhận `JobInstanceAlreadyCompleteException` |
| `FAILED` hoặc `STOPPED` | Có thể restart nếu cấu hình cho phép |
| Job được cấu hình không restart | Có thể nhận `JobRestartException` |

Nếu thêm timestamp hoặc UUID mới như một identifying parameter mỗi lần thử lại, Spring Batch sẽ tạo JobInstance mới. Job mới có thể bắt đầu lại từ đầu thay vì tiếp tục checkpoint của instance thất bại. Đây là lỗi thiết kế thường gặp khi hệ thống tự động retry một request launch.

### Non-identifying parameters có thể thay đổi khi restart không?

Về mặt định danh, non-identifying parameters có thể khác mà không tạo JobInstance mới. Tuy nhiên, việc thay đổi chúng giữa các execution phải được cân nhắc kỹ. Mỗi JobExecution có bộ JobParameters riêng; vì thế, một lần restart có thể nhận giá trị non-identifying mới trong khi vẫn thuộc cùng JobInstance.

Điều này chỉ an toàn nếu thay đổi đó không làm cho các phần đã commit trước đây và phần tiếp tục xử lý có ý nghĩa nghiệp vụ khác nhau. Ví dụ, thay người yêu cầu hoặc địa chỉ nhận thông báo thường không ảnh hưởng dữ liệu settlement. Ngược lại, thay tỷ giá, quy tắc tính phí hoặc chế độ lọc dữ liệu có thể khiến kết quả của một JobInstance không nhất quán.

Nếu một giá trị có ảnh hưởng đến kết quả nghiệp vụ, hãy giữ nó ổn định qua restart. Có thể đánh dấu nó là identifying hoặc lưu snapshot cấu hình đầu vào bất biến theo JobInstance và chỉ tham chiếu snapshot đó trong mọi execution.

## 7. Chọn loại parameter theo ví dụ nghiệp vụ

### Job tính phí cuối ngày

Giả sử Job tính phí cho tất cả tài khoản trong một ngày. `businessDate` cần là identifying vì mỗi ngày là một đơn vị công việc khác nhau. Nếu đầu vào là một bản chụp dữ liệu có version, `snapshotId` cũng nên là identifying.

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("snapshotId", snapshotId, true)
        .addLong("requestedBy", operatorId, false)
        .toJobParameters();
```

### Job import file

Nếu mỗi file được nhập đúng một lần, mã file hoặc checksum của nội dung file có thể là identifying. Chỉ dùng tên file nếu tên đó ổn định và đại diện duy nhất cho nội dung. Nếu cùng tên file có thể được ghi đè bằng nội dung khác, tên file đơn thuần không đủ để xác định nguồn dữ liệu.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("fileId", fileId, true)
        .addString("fileChecksum", checksum, true)
        .addString("submittedBy", username, false)
        .toJobParameters();
```

### Job tạo báo cáo với tùy chọn trình bày

Nếu `outputFormat` chỉ thay đổi cách xuất báo cáo, còn dữ liệu nghiệp vụ được tổng hợp vẫn giống nhau, có thể cân nhắc để nó là non-identifying. Nhưng nếu mỗi định dạng được lưu thành một artifact độc lập và cần theo dõi riêng, việc coi định dạng là identifying có thể hợp lý. Quyết định phụ thuộc vào định nghĩa một lần chạy trong nghiệp vụ.

Không có một quy tắc cứng cho mọi tên parameter. Hãy xác định trước câu hỏi: “Nếu giá trị này thay đổi, tôi có muốn Spring Batch coi đây là một lần chạy logic khác hay không?”

## 8. Truy cập cả hai loại parameter trong Step

Cả identifying và non-identifying parameters đều có thể được truy cập trong Step. Ví dụ, một Tasklet lấy ngày nghiệp vụ và người yêu cầu từ `ChunkContext`:

```java
@Bean
@StepScope
Tasklet settlementTasklet() {
    return (contribution, chunkContext) -> {
        Map<String, Object> parameters = chunkContext
                .getStepContext()
                .getJobParameters();

        LocalDate businessDate = (LocalDate) parameters.get("businessDate");
        Long requestedBy = (Long) parameters.get("requestedBy");

        // Xử lý dữ liệu theo businessDate và ghi nhận requestedBy.
        return RepeatStatus.FINISHED;
    };
}
```

Trong ví dụ, cả hai giá trị đều được đọc như đầu vào. Cờ identifying không làm thay đổi cách Tasklet truy cập chúng. `@StepScope` cho phép bean nhận giá trị của lần chạy hiện tại thay vì cố định tham số tại thời điểm ứng dụng khởi động.

Khi dùng `@Value` để late-bind một parameter, cần khai báo bean với scope phù hợp:

```java
@Bean
@StepScope
FlatFileItemReader<SettlementInput> settlementReader(
        @Value("#{jobParameters['sourceFile']}") String sourceFile) {

    return new FlatFileItemReaderBuilder<SettlementInput>()
            .name("settlementReader")
            .resource(new FileSystemResource(sourceFile))
            .delimited()
            .names("accountId", "amount")
            .targetType(SettlementInput.class)
            .build();
}
```

## 9. Quy tắc thiết kế identifying parameters

Để Job có hành vi dễ dự đoán, nên áp dụng các nguyên tắc sau:

1. **Định nghĩa đơn vị công việc trước:** xác định một JobInstance tương ứng với ngày, file, kỳ, tenant hay lô dữ liệu nào.
2. **Chọn khóa nghiệp vụ ổn định:** dùng mã hoặc giá trị không đổi trong suốt một lần chạy và các lần restart.
3. **Đưa các yếu tố thay đổi kết quả vào định danh hoặc snapshot:** không để một lần restart âm thầm sử dụng quy tắc nghiệp vụ khác.
4. **Giữ thông tin vận hành ở non-identifying:** người yêu cầu, ticket hoặc địa chỉ thông báo thường không cần tạo instance mới.
5. **Không tạo UUID mới cho mỗi lần retry:** nếu cần idempotency, dùng một request ID ổn định xuyên suốt các lần gửi lại.
6. **Không để tất cả parameters đều non-identifying một cách vô tình:** khi không có identifying parameter, cùng một tên Job có thể luôn ánh xạ về cùng một JobInstance, kể cả các lần chạy nghiệp vụ khác nhau.
7. **Xác thực trước khi launch:** kiểm tra tham số bắt buộc, kiểu dữ liệu, miền giá trị và sự nhất quán giữa các giá trị.

### Trường hợp không có tham số nghiệp vụ tự nhiên

Một Job có thể cần chạy nhiều lần độc lập nhưng không có ngày, mã file hoặc khóa nghiệp vụ tự nhiên. Khi đó, có thể dùng một tham số định danh lần chạy được cấp phát có chủ đích, hoặc `JobParametersIncrementer` như `RunIdIncrementer` trong quy trình tạo instance tiếp theo.

Ví dụ:

```java
@Bean
Job adHocReportJob(JobRepository jobRepository, Step reportStep) {
    return new JobBuilder("adHocReportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(reportStep)
            .build();
}
```

Incrementer hỗ trợ tạo identifying parameter mới cho một JobInstance tiếp theo khi dùng cơ chế như `JobOperator.startNextInstance()`. Nó không tự động thay đổi tham số trong lời gọi trực tiếp `JobLauncher.run(job, parameters)`. Quan trọng hơn, một `run.id` mới tạo instance mới; nó không phải cách restart instance đã thất bại.

## 10. Các lỗi thường gặp

**Đánh dấu mọi parameter là identifying:** những thông tin phụ trợ như người yêu cầu hoặc email thông báo làm phát sinh nhiều JobInstance không cần thiết. Việc tra cứu lịch sử và xử lý restart trở nên khó hiểu.

**Đánh dấu mọi parameter là non-identifying:** các lần chạy cho ngày hoặc file khác nhau có thể bị gom vào cùng JobInstance. Khi instance đã hoàn tất, launch tiếp theo có thể bị từ chối dù nghiệp vụ muốn xử lý một kỳ mới.

**Thêm timestamp mới mỗi lần retry:** mỗi lần gọi tạo instance khác, dẫn đến xử lý lại từ đầu thay vì restart execution trước.

**Thay đổi đầu vào nghiệp vụ nhưng giữ cùng định danh:** restart có thể tiếp tục với một bộ dữ liệu hoặc quy tắc khác, làm kết quả không nhất quán.

**Nhầm non-identifying với không được lưu:** non-identifying parameters vẫn là một phần của JobParameters được lưu cho execution và có thể được Job truy cập.

**Đưa bí mật vào parameters:** JobParameters có thể được lưu trong JobRepository. Không nên đưa password, access token hoặc secret trực tiếp vào metadata.

**Truyền payload lớn:** JobParameters nên chứa khóa, phạm vi hoặc tham chiếu đến dữ liệu. File lớn và danh sách bản ghi nên được lưu ở nguồn dữ liệu thích hợp.

## Kết luận

Identifying parameters xác định JobInstance cùng với tên Job; non-identifying parameters cung cấp thêm dữ liệu cho execution nhưng không thay đổi định danh instance. Cả hai loại đều có thể được sử dụng bên trong Step và được lưu trong metadata. Hãy đánh dấu identifying cho các giá trị xác định đơn vị công việc nghiệp vụ, giữ chúng ổn định khi restart và dùng non-identifying cho thông tin phụ trợ. Cách thiết kế này giúp Spring Batch phân biệt chính xác lần chạy mới với lần restart, hạn chế xử lý trùng và giữ kết quả nhất quán qua nhiều execution.
