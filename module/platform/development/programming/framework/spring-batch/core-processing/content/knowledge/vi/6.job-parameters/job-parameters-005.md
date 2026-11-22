# Tham số mặc định và tính xác định

Trong Spring Batch, `JobParameters` cung cấp dữ liệu đầu vào cho một lần khởi chạy Job. Một số tham số có thể do scheduler, command line hoặc API truyền vào; một số khác có thể được ứng dụng gán giá trị mặc định khi người gọi bỏ qua. Cách chọn và chuẩn hóa các giá trị này ảnh hưởng trực tiếp đến **tính xác định của JobInstance**.

Spring Batch xác định một `JobInstance` dựa trên tên Job và các JobParameters được đánh dấu là *identifying*. Khi cùng một Job được khởi chạy với cùng bộ tham số identifying, yêu cầu đó đại diện cho cùng một JobInstance. Nếu một giá trị mặc định thay đổi ngoài dự kiến, ứng dụng có thể vô tình tạo JobInstance mới; nếu một giá trị thay đổi nhưng đáng lẽ phải giữ nguyên, khả năng restart có thể bị ảnh hưởng.

Vì vậy, khi thiết kế JobParameters, cần quyết định rõ tham số nào có giá trị mặc định, giá trị mặc định được tính từ đâu, và thay đổi của tham số có đại diện cho một công việc nghiệp vụ mới hay không.

## 1. JobParameters và danh tính của JobInstance

`JobParameters` là tập hợp các tham số được truyền vào khi khởi chạy Job. Ví dụ, một Job nhập đơn hàng có thể nhận ngày nghiệp vụ, file đầu vào và chế độ xử lý:

```text
businessDate = 2026-11-15
inputFile    = data/orders-2026-11-15.csv
mode         = FULL
```

Spring Batch phân biệt hai loại tham số:

- **Identifying parameter:** tham gia xác định JobInstance. Thay đổi giá trị này có thể tạo một JobInstance khác.
- **Non-identifying parameter:** được lưu như dữ liệu đầu vào của lần chạy nhưng không tham gia xác định danh tính JobInstance.

Quan hệ tổng quát:

```text
Job name + identifying JobParameters
                  |
                  v
             JobInstance
                  |
                  +-- JobExecution #1
                  +-- JobExecution #2 (restart)
```

JobInstance đại diện cho công việc nghiệp vụ logic cần hoàn thành; JobExecution đại diện cho từng lần thử thực thi công việc đó. Các tham số identifying vì vậy cần mô tả đúng ranh giới nghiệp vụ của một công việc.

## 2. Tham số mặc định là gì?

Spring Batch cung cấp API để xây dựng `JobParameters`, nhưng việc chọn giá trị mặc định thường là trách nhiệm của ứng dụng hoặc thành phần khởi chạy. Ví dụ, API có thể cho phép người gọi bỏ qua `mode`; khi đó service gán `FULL`. Một tham số khác như `businessDate` có thể bắt buộc phải truyền rõ ràng vì ngày nghiệp vụ quyết định tập dữ liệu được xử lý.

Ví dụ, ứng dụng đặt mặc định cho chế độ xử lý:

```java
String mode = requestMode;

if (mode == null || mode.isBlank()) {
    mode = "FULL";
}
```

Sau đó đưa giá trị đã xác định vào JobParameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("mode", mode, true)
        .toJobParameters();
```

Điểm quan trọng là Job nhận được một giá trị cụ thể, không cần tự suy đoán xem caller có truyền tham số hay không. Việc defaulting nên được thực hiện tại một ranh giới rõ ràng, chẳng hạn service khởi chạy Job hoặc lớp chuyển đổi tham số đầu vào.

### Chọn giá trị mặc định theo nghiệp vụ

Giá trị mặc định cần có ý nghĩa nghiệp vụ rõ ràng:

- `mode=FULL` có thể là mặc định hợp lý nếu quy trình mặc định phải nhập toàn bộ dữ liệu.
- `businessDate` có thể bắt buộc nếu chạy nhầm ngày gây ảnh hưởng đến kết quả.
- `inputFile` có thể được suy ra từ ngày nghiệp vụ theo một quy ước tên file ổn định.
- `notificationEmail` có thể lấy từ cấu hình ứng dụng nếu chỉ dùng để gửi thông báo và không làm thay đổi tập dữ liệu cần xử lý.

Không nên đặt một giá trị mặc định chỉ vì muốn tránh kiểm tra đầu vào. Nếu không có giá trị mặc định an toàn và có ý nghĩa, hãy yêu cầu caller truyền tham số hoặc từ chối yêu cầu với thông báo rõ ràng.

## 3. Xây dựng JobParameters sau khi áp dụng default

Ví dụ dưới đây minh họa một service nhận tham số tùy chọn và tạo JobParameters. Ngày nghiệp vụ là bắt buộc; chế độ xử lý có mặc định `FULL`; email nhận thông báo có thể lấy từ cấu hình và được đánh dấu non-identifying:

```java
public JobParameters createParameters(
        String requestedBusinessDate,
        String requestedMode,
        String requestedInputFile,
        String defaultNotificationEmail) {

    if (requestedBusinessDate == null || requestedBusinessDate.isBlank()) {
        throw new IllegalArgumentException("businessDate is required");
    }

    String businessDate = requestedBusinessDate.trim();
    String mode = (requestedMode == null || requestedMode.isBlank())
            ? "FULL"
            : requestedMode.trim().toUpperCase(Locale.ROOT);

    String inputFile = (requestedInputFile == null || requestedInputFile.isBlank())
            ? "data/orders-" + businessDate + ".csv"
            : requestedInputFile.trim();

    return new JobParametersBuilder()
            .addString("businessDate", businessDate, true)
            .addString("mode", mode, true)
            .addString("inputFile", inputFile, true)
            .addString("notificationEmail", defaultNotificationEmail, false)
            .toJobParameters();
}
```

Trong ví dụ này:

- `businessDate` xác định ngày dữ liệu cần xử lý nên là identifying.
- `mode` làm thay đổi phạm vi xử lý (`FULL` hoặc một chế độ khác), nên được xem là identifying nếu hai chế độ đại diện cho hai công việc logic khác nhau.
- `inputFile` là identifying nếu file khác nhau tương ứng với một tập dữ liệu nghiệp vụ khác.
- `notificationEmail` chỉ thay đổi người nhận thông báo nên có thể là non-identifying.

Việc đánh dấu identifying phải dựa trên quy tắc nghiệp vụ, không phải dựa vào kiểu dữ liệu hay việc tham số có được truyền từ bên ngoài hay không.

Lưu ý: ví dụ dùng `requestedBusinessDate` ở dạng chuỗi đã chuẩn hóa theo một định dạng thống nhất, chẳng hạn `yyyy-MM-dd`. Ứng dụng thực tế nên parse và validate ngày trước khi tạo JobParameters, đồng thời chuẩn hóa tên file theo quy tắc của hệ thống.

## 4. Tính xác định của JobInstance

Một yêu cầu khởi chạy có tính xác định khi cùng Job name và cùng các giá trị identifying tạo ra cùng danh tính JobInstance. Có thể diễn đạt bằng quy tắc:

```text
JobInstance identity = Job name + identifying JobParameters
```

Giả sử `importOrdersJob` dùng `businessDate` và `mode` làm tham số identifying:

| Lần gọi | businessDate | mode | JobInstance |
|---|---|---|---|
| A | `2026-11-15` | `FULL` | Instance X |
| B | `2026-11-15` | `FULL` | Instance X |
| C | `2026-11-15` | `DELTA` | Instance Y |
| D | `2026-11-16` | `FULL` | Instance Z |

Lần A và B có cùng danh tính vì các tham số identifying giống nhau. Lần C tạo danh tính khác do chế độ xử lý thay đổi; lần D khác do ngày nghiệp vụ thay đổi.

Nếu lần A đã hoàn tất, lần B với cùng identifying parameters thường bị từ chối bằng `JobInstanceAlreadyCompleteException`. Nếu lần A thất bại và có thể restart, lần B có thể tạo JobExecution mới trên cùng JobInstance. Đó là cách Spring Batch phân biệt một lần restart với một công việc nghiệp vụ mới.

### Giá trị mặc định ảnh hưởng đến tính xác định

Giả sử `mode` không được caller truyền vào. Nếu ứng dụng luôn default thành `FULL`, mọi lần gọi cùng ngày và cùng file sẽ có cùng identifying parameters. Việc retry vì vậy tiếp tục hướng đến cùng JobInstance.

Ngược lại, nếu default được tính bằng một giá trị thay đổi mỗi lần gọi, chẳng hạn timestamp hiện tại, mỗi lần gọi có thể tạo JobInstance mới. Một lần retry tưởng như cùng công việc nghiệp vụ khi đó lại trở thành một công việc mới, làm mất ý nghĩa restart.

## 5. Identifying và non-identifying parameters

Phương thức `JobParametersBuilder` cho phép chỉ rõ tham số có tham gia nhận diện JobInstance hay không:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("mode", "FULL", true)
        .addString("notificationEmail", "ops@example.com", false)
        .toJobParameters();
```

Trong ví dụ trên, thay đổi email không tạo JobInstance mới, còn thay đổi ngày hoặc mode sẽ tạo danh tính khác.

Non-identifying không có nghĩa là tham số bị bỏ qua. Giá trị vẫn có thể được đọc qua `JobExecution.getJobParameters()` và được dùng trong quá trình chạy. Nó chỉ không tham gia xác định JobInstance.

Hãy đánh dấu identifying khi thay đổi giá trị có nghĩa là đang xử lý một công việc logic khác. Hãy đánh dấu non-identifying khi thay đổi giá trị không làm thay đổi danh tính công việc, chẳng hạn một tùy chọn thông báo hoặc thông tin theo dõi không ảnh hưởng dữ liệu xử lý.

### Rủi ro khi đánh dấu sai

Nếu một tham số làm thay đổi tập dữ liệu nhưng lại được đánh dấu non-identifying, yêu cầu mới có thể trỏ đến JobInstance cũ. Điều đó có thể dẫn đến việc không thể khởi chạy do instance đã hoàn tất hoặc khiến lần restart sử dụng metadata không phù hợp với ý định nghiệp vụ.

Nếu một tham số không làm thay đổi công việc nghiệp vụ nhưng lại được đánh dấu identifying, mỗi thay đổi nhỏ có thể tạo JobInstance mới. Điều này làm lịch sử metadata phân mảnh và khiến retry không còn gắn với công việc trước đó.

## 6. Giá trị mặc định phải ổn định giữa các lần retry

Một nguyên tắc quan trọng là default của identifying parameter phải được tính theo cùng một quy tắc cho mọi lần thử của cùng công việc.

Ví dụ, nếu ngày nghiệp vụ được mặc định là ngày hiện tại, một lần chạy lúc 23:59 và retry lúc 00:01 có thể nhận hai ngày khác nhau. Hệ thống khi đó tạo hai JobInstance khác nhau dù người vận hành chỉ muốn retry cùng một đợt xử lý.

Có một số cách thiết kế:

- Với Job chạy theo lịch, scheduler truyền rõ ngày nghiệp vụ vào JobParameters.
- Với Job được khởi chạy thủ công, API yêu cầu người dùng chọn ngày hoặc dùng một ngày mặc định được xác định trước trong cấu hình nghiệp vụ.
- Nếu ngày mặc định được tính theo múi giờ nghiệp vụ, tính giá trị đó một lần ở ranh giới khởi chạy và lưu lại để retry sử dụng đúng giá trị ban đầu.
- Khi caller gửi lại yêu cầu, giữ nguyên identifying parameters của yêu cầu gốc thay vì tính lại default từ thời điểm retry.

Ví dụ, scheduler có thể truyền ngày nghiệp vụ một cách tường minh:

```java
String businessDate = scheduledBusinessDate.format(
        DateTimeFormatter.ISO_LOCAL_DATE
);

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("mode", "FULL", true)
        .toJobParameters();
```

Giá trị `scheduledBusinessDate` phải được xác định từ lịch nghiệp vụ và được giữ nguyên cho các lần retry của cùng lịch chạy. Không nên gọi `LocalDate.now()` ở nhiều vị trí khác nhau trong quá trình retry rồi kỳ vọng kết quả nhận diện luôn giống nhau.

## 7. Chuẩn hóa tham số trước khi xây dựng JobParameters

Hai giá trị có thể giống nhau về ý nghĩa nghiệp vụ nhưng khác nhau về biểu diễn. Ví dụ `FULL`, `full` và ` FULL ` có thể được caller gửi lên. Nếu đưa nguyên văn vào identifying parameters, Spring Batch coi chúng là các giá trị khác nhau.

Vì vậy, hãy chuẩn hóa trước khi xây dựng JobParameters:

- Trim khoảng trắng ở đầu và cuối chuỗi.
- Chuẩn hóa chữ hoa/thường theo quy ước, chẳng hạn dùng `Locale.ROOT` cho mã chế độ.
- Chuẩn hóa ngày theo một định dạng duy nhất, chẳng hạn ISO `yyyy-MM-dd`.
- Chuẩn hóa đường dẫn file hoặc mã nguồn dữ liệu theo quy tắc của hệ điều hành và nghiệp vụ.
- Validate enum, phạm vi số và giá trị bắt buộc trước khi khởi chạy.
- Không dùng giá trị hiển thị phụ thuộc locale làm định danh nếu có thể dùng mã ổn định.

Ví dụ:

```java
String normalizedMode = rawMode == null || rawMode.isBlank()
        ? "FULL"
        : rawMode.trim().toUpperCase(Locale.ROOT);

LocalDate parsedDate = LocalDate.parse(rawBusinessDate);
String normalizedDate = parsedDate.format(DateTimeFormatter.ISO_LOCAL_DATE);
```

Chuẩn hóa giúp cùng một yêu cầu nghiệp vụ tạo ra cùng một bộ tham số identifying, bất kể caller gửi cách viết hoặc khoảng trắng khác nhau.

## 8. JobParametersIncrementer và việc tạo instance tiếp theo

Spring Batch có `JobParametersIncrementer` để tạo bộ JobParameters tiếp theo dựa trên bộ hiện tại. Một ứng dụng có thể gắn incrementer vào Job và dùng các API như `JobOperator.startNextInstance` để yêu cầu bắt đầu một JobInstance tiếp theo.

Ví dụ `RunIdIncrementer` thường được dùng để tăng tham số `run.id`:

```java
@Bean
public Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .incrementer(new RunIdIncrementer())
            .build();
}
```

Incrementer có thể tạo ra bộ tham số với `run.id` tăng dần. Nếu `run.id` là identifying, mỗi giá trị mới tạo một JobInstance mới. Đây là hành vi phù hợp khi nghiệp vụ yêu cầu một lần chạy độc lập tiếp theo.

Không nên dùng incrementer để thay thế cơ chế restart. Restart nhằm tiếp tục cùng JobInstance sau một execution thất bại hoặc bị dừng; tạo `run.id` mới thường có nghĩa là tạo một JobInstance mới. Ngoài ra, `JobLauncher.run()` không tự động tăng tham số chỉ vì Job có gắn incrementer; incrementer được dùng bởi API khởi chạy instance tiếp theo như `JobOperator.startNextInstance`.

## 9. Phân biệt retry, restart và một lần chạy mới

Các thuật ngữ này dễ bị nhầm khi thiết kế default parameters:

| Hành động | JobInstance | JobExecution | Ý nghĩa |
|---|---|---|---|
| Restart một JobInstance thất bại | Giữ nguyên | Tạo execution mới | Tiếp tục công việc logic cũ |
| Khởi chạy cùng identifying parameters sau khi instance đã hoàn tất | Giữ nguyên danh tính | Thường bị từ chối | Không tự động chạy lại công việc đã hoàn tất |
| Khởi chạy với identifying parameter mới | Tạo instance mới | Tạo execution mới | Bắt đầu công việc logic khác |
| Dùng incrementer tạo run ID mới | Thường tạo instance mới nếu run ID identifying | Tạo execution mới | Tạo một lượt xử lý độc lập tiếp theo |

Một lần gọi lại API do client timeout chưa chắc là restart. Nếu request thứ nhất đã tạo JobExecution nhưng client không nhận được response, request thứ hai với cùng tham số identifying có thể gặp lỗi instance đang chạy hoặc instance đã hoàn tất. API nên có cách tra cứu theo business key hoặc request ID để caller tìm lại execution ban đầu thay vì tạo tham số ngẫu nhiên mới.

## 10. Thiết kế idempotency cho API khởi chạy

Với API khởi chạy Job, client có thể gửi lại yêu cầu do timeout hoặc mất kết nối. Nếu mỗi lần gọi đều thêm timestamp làm identifying parameter, hệ thống sẽ tạo nhiều JobInstance cho cùng một yêu cầu nghiệp vụ.

Một thiết kế ổn định thường gồm:

1. Xác định business key của yêu cầu, ví dụ ngày nghiệp vụ và mã nguồn dữ liệu.
2. Chuẩn hóa business key và chuyển các thành phần cần thiết thành identifying JobParameters.
3. Có thể lưu request ID của client trong một kho dữ liệu riêng để truy vết việc tiếp nhận yêu cầu.
4. Khi client gửi lại cùng request, tra cứu execution đã tạo hoặc xử lý trạng thái đang chạy/đã hoàn tất theo quy tắc nghiệp vụ.
5. Chỉ tạo identifying parameter mới khi thật sự muốn bắt đầu một công việc logic mới.

Không nên dựa vào việc JobParameters tự giải quyết mọi tình huống idempotency của HTTP. JobRepository bảo vệ danh tính và trạng thái JobInstance, còn API cần thiết kế response và cơ chế tra cứu phù hợp với việc client gửi lại request.

## 11. Kiểm tra và quan sát JobParameters

Khi điều tra vì sao một yêu cầu tạo JobInstance mới hoặc bị từ chối, hãy ghi nhận các tham số identifying đã chuẩn hóa và ID JobInstance/JobExecution. Không ghi log bí mật hoặc dữ liệu nhạy cảm.

Có thể đọc tham số từ JobExecution:

```java
JobParameters parameters = execution.getJobParameters();

String businessDate = parameters.getString("businessDate");
String mode = parameters.getString("mode");
Long runId = parameters.getLong("run.id");

log.info(
        "jobInstanceId={}, executionId={}, businessDate={}, mode={}, runId={}",
        execution.getJobInstance().getId(),
        execution.getId(),
        businessDate,
        mode,
        runId
);
```

Nếu một tham số có thể vắng mặt, hãy xử lý giá trị `null` trước khi dùng. Không nên giả định tất cả tham số luôn tồn tại chỉ vì một số luồng khởi chạy có default.

## 12. Những nhầm lẫn thường gặp

**Cho rằng Spring Batch tự đặt default cho mọi tham số.** Việc chọn giá trị mặc định thường thuộc về ứng dụng, scheduler hoặc lớp chuyển đổi tham số. JobParametersBuilder chỉ xây dựng tập tham số từ những giá trị được cung cấp.

**Dùng thời điểm hiện tại làm default identifying cho mọi lần gọi.** Timestamp thay đổi sẽ tạo JobInstance mới, khiến retry không còn hướng đến cùng công việc logic.

**Cho rằng non-identifying parameter không có tác dụng.** Tham số này vẫn được lưu và có thể được Job sử dụng; nó chỉ không tham gia xác định JobInstance.

**Đánh dấu mọi tham số là identifying.** Chỉ những giá trị xác định công việc nghiệp vụ mới nên tham gia identity. Thông tin phụ như người nhận thông báo thường không cần tạo instance mới.

**Dùng RunIdIncrementer để restart.** Incrementer thường tạo một định danh mới cho instance tiếp theo. Restart giữ nguyên JobInstance và tạo JobExecution mới trên instance đó.

**Không chuẩn hóa chuỗi.** Khác biệt về khoảng trắng, chữ hoa/thường hoặc định dạng ngày có thể tạo identifying parameters khác nhau. Hãy chuẩn hóa trước khi gọi JobLauncher.

## 13. Cách thiết kế default và identity phù hợp

Hãy bắt đầu từ câu hỏi nghiệp vụ: hai yêu cầu có cần được coi là cùng một công việc cần hoàn thành hay không? Nếu có, chúng phải tạo cùng Job name và cùng bộ identifying parameters sau khi chuẩn hóa. Nếu không, ít nhất một identifying parameter phải khác.

Đặt default tại một ranh giới khởi chạy rõ ràng, chọn giá trị ổn định và có ý nghĩa nghiệp vụ, validate đầu vào, rồi tạo JobParameters với cờ identifying được khai báo tường minh. Dùng JobParametersIncrementer khi cần chủ động tạo instance tiếp theo; dùng restart khi cần tiếp tục cùng một instance. Cách thiết kế này giúp retry có thể lặp lại một cách xác định, lịch sử JobInstance dễ hiểu và ứng dụng tránh tạo những lần xử lý trùng ngoài ý muốn.
