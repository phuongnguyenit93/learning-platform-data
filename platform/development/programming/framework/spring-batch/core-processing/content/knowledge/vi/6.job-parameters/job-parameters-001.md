# JobParameters xác định JobInstance

Trong Spring Batch, một job có thể được chạy nhiều lần để xử lý các kỳ nghiệp vụ hoặc tập dữ liệu khác nhau. Framework cần biết hai yêu cầu khởi chạy có đại diện cho cùng một công việc logic hay không. Ví dụ, nhập file đơn hàng cho ngày 15/11 là một công việc; nhập file cho ngày 16/11 là một công việc khác. Spring Batch dùng **tên Job kết hợp với các identifying `JobParameters`** để xác định `JobInstance`.

Vì vậy, JobParameters không chỉ là những giá trị đầu vào mà reader hoặc processor sử dụng. Việc đánh dấu tham số nào tham gia định danh còn quyết định cách Spring Batch phân biệt chạy mới với restart, nhận diện yêu cầu trùng và lưu lịch sử thực thi.

## 1. JobParameters là gì?

`JobParameters` là tập các tham số được truyền vào khi khởi chạy một `Job`. Các tham số có thể mô tả dữ liệu cần xử lý hoặc cung cấp thông tin cho quy trình, chẳng hạn:

- Ngày nghiệp vụ cần nhập.
- Đường dẫn file đầu vào.
- Mã hệ thống nguồn.
- Phạm vi ID bản ghi cần xử lý.
- Người hoặc hệ thống yêu cầu chạy.
- Mã yêu cầu dùng để theo dõi một lần tiếp nhận.

Một tham số có tên, giá trị, kiểu dữ liệu và thuộc tính `identifying`. Thuộc tính này cho biết tham số có tham gia xác định JobInstance hay không.

Ví dụ một bộ tham số cho job nhập đơn hàng:

```text
businessDate = 2026-11-15    identifying = true
inputFile    = orders.csv   identifying = true
requestedBy  = scheduler    identifying = false
```

Trong ví dụ, ngày nghiệp vụ và file đầu vào xác định công việc logic cần xử lý. `requestedBy` chỉ ghi nhận ai đã yêu cầu chạy, nên không làm thay đổi danh tính của JobInstance.

## 2. JobInstance được xác định như thế nào?

Một `JobInstance` được xác định bởi hai thành phần:

1. Tên của `Job`.
2. Các `JobParameters` có `identifying=true`.

Có thể mô tả khái niệm này bằng công thức:

```text
JobInstance identity = Job name + identifying JobParameters
```

Ví dụ, job `importOrdersJob` chạy với `businessDate=2026-11-15` và `sourceSystem=ERP`:

```text
Job name: importOrdersJob

Identifying parameters:
  businessDate = 2026-11-15
  sourceSystem = ERP

              |
              v
JobInstance: importOrdersJob / 2026-11-15 / ERP
```

Nếu chạy cùng job với cùng các giá trị identifying, Spring Batch xác định đó là cùng một JobInstance. Nếu đổi tên job hoặc thay đổi một identifying parameter, kết quả là một JobInstance khác.

| Tên Job | Identifying parameters | Kết quả |
|---|---|---|
| `importOrdersJob` | `businessDate=2026-11-15` | Instance A |
| `importOrdersJob` | `businessDate=2026-11-15` | Cùng instance A |
| `importOrdersJob` | `businessDate=2026-11-16` | Instance B |
| `importCustomersJob` | `businessDate=2026-11-15` | Instance C |

Hai job khác tên không dùng chung một JobInstance, ngay cả khi chúng nhận cùng các tham số. Tương tự, hai lần chạy cùng tên job nhưng khác giá trị identifying sẽ đại diện cho hai đơn vị xử lý logic khác nhau.

## 3. Tạo JobParameters bằng JobParametersBuilder

Thông thường, ứng dụng tạo tham số bằng `JobParametersBuilder`. Builder giúp thêm từng giá trị và chỉ định rõ thuộc tính identifying.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders.csv", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Các đối số quan trọng của `addString` gồm tên tham số, giá trị và cờ identifying. Cờ `true` nghĩa là tham số tham gia xác định JobInstance; cờ `false` nghĩa là không tham gia.

Sau khi tạo xong, truyền JobParameters cho JobLauncher:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
```

Builder còn hỗ trợ các kiểu dữ liệu khác ngoài chuỗi, chẳng hạn số nguyên dài, số thực hoặc kiểu ngày theo API của phiên bản Spring Batch đang sử dụng. Nên chọn kiểu phù hợp với ý nghĩa dữ liệu và giữ cách biểu diễn ổn định giữa các lần chạy.

Một lưu ý quan trọng: các phương thức builder không chỉ định cờ identifying có thể áp dụng giá trị mặc định theo API của phiên bản. Khi danh tính JobInstance có ý nghĩa nghiệp vụ, nên truyền cờ một cách tường minh để người đọc code hiểu ngay tham số nào ảnh hưởng đến identity.

## 4. Phân biệt identifying và non-identifying parameters

Hai nhóm tham số có mục đích khác nhau:

| Loại tham số | `identifying` | Ảnh hưởng đến JobInstance | Ví dụ |
|---|---:|---|---|
| Tham số định danh | `true` | Có | Ngày nghiệp vụ, mã batch, hệ thống nguồn, phiên bản file đầu vào. |
| Tham số không định danh | `false` | Không | Người yêu cầu, thông tin trace, ghi chú vận hành hoặc thông tin tiếp nhận. |

### Identifying parameters

Tham số định danh phải mô tả đơn vị công việc logic. Nếu hai yêu cầu xử lý hai tập dữ liệu khác nhau, chúng thường cần ít nhất một giá trị identifying khác nhau.

Ví dụ, một job đối soát theo ngày và hệ thống nguồn có thể dùng:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSystem", "ERP", true)
        .toJobParameters();
```

Ngày nghiệp vụ và hệ thống nguồn xác định một phạm vi đối soát. Chạy cùng job với ngày khác hoặc nguồn khác sẽ tạo JobInstance mới.

### Non-identifying parameters

Tham số không định danh vẫn có thể được đọc trong job, nhưng thay đổi giá trị của nó không tạo JobInstance mới.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "manual-user", false)
        .addString("requestId", "REQ-83921", false)
        .toJobParameters();
```

Ở đây, `requestedBy` và `requestId` là thông tin theo dõi yêu cầu. Nếu chỉ thay đổi `requestId`, Spring Batch vẫn xác định cùng JobInstance vì các tham số định danh không đổi.

Điều này cũng có nghĩa không nên đặt một giá trị làm thay đổi tập dữ liệu hoặc kết quả nghiệp vụ vào nhóm non-identifying. Nếu `inputFile` thay đổi sang một file chứa dữ liệu khác nhưng vẫn không định danh, hai yêu cầu có thể bị coi là cùng một công việc logic. Hãy chọn identifying parameters theo dữ liệu thực sự cần xử lý.

## 5. Quan hệ giữa JobInstance và JobExecution

`JobInstance` biểu diễn một đơn vị xử lý logic. `JobExecution` biểu diễn một lần thực thi cụ thể của đơn vị đó. Một JobInstance có thể có nhiều JobExecution nếu lần chạy trước thất bại và được restart.

```text
Job: importOrdersJob
          |
          +-- JobInstance (businessDate=2026-11-15)
                    |
                    +-- JobExecution #1: FAILED
                    |
                    +-- JobExecution #2: COMPLETED

          +-- JobInstance (businessDate=2026-11-16)
                    |
                    +-- JobExecution #3: COMPLETED
```

Khi khởi chạy lại với cùng tên job và cùng identifying parameters:

- Nếu JobInstance chưa từng chạy, Spring Batch tạo instance và execution đầu tiên.
- Nếu instance đang có execution hoạt động, yêu cầu khởi chạy khác thường bị từ chối.
- Nếu execution trước thất bại hoặc dừng theo cách cho phép restart, framework có thể tạo execution mới cho cùng instance.
- Nếu instance đã hoàn tất, gọi lại với cùng identity thường phát sinh `JobInstanceAlreadyCompleteException`.

Như vậy, JobParameters giúp framework xác định yêu cầu thuộc công việc nào; trạng thái đã lưu của JobInstance quyết định yêu cầu tiếp theo có thể được thực hiện như một lần chạy mới hay restart hay không.

## 6. Thay đổi tham số nào sẽ tạo JobInstance mới?

Chỉ thay đổi identifying parameters mới làm thay đổi identity. Thay đổi tham số không định danh không tạo instance mới.

Giả sử bộ tham số ban đầu là:

```text
businessDate = 2026-11-15   identifying = true
sourceSystem = ERP          identifying = true
requestedBy  = scheduler    identifying = false
```

| Lần chạy | Thay đổi | Kết quả identity |
|---|---|---|
| A | Bộ tham số ban đầu | Tạo instance A |
| B | Chỉ đổi `requestedBy` thành `operator` | Vẫn là instance A |
| C | Đổi `businessDate` thành `2026-11-16` | Tạo instance B |
| D | Đổi `sourceSystem` thành `CRM` | Tạo instance C |
| E | Đổi cả ngày và nguồn | Tạo instance D |

Hãy nhớ rằng đổi tham số không định danh không tạo ra một JobInstance mới. Nếu instance hiện tại đã `COMPLETED`, gọi launcher lại với cùng các tham số định danh vẫn có thể bị từ chối, dù giá trị `requestedBy` khác.

## 7. JobParameters và JobParametersValidator giải quyết hai vấn đề khác nhau

Thuộc tính identifying trả lời câu hỏi: “Bộ tham số này đại diện cho JobInstance nào?”. Nó không tự kiểm tra tham số có hợp lệ về nghiệp vụ hay không.

Ví dụ, `businessDate=2026-11-15` có thể là một giá trị hợp lệ, trong khi `businessDate=tomorrow` có thể không đúng định dạng ứng dụng yêu cầu. Cả hai vẫn có thể là giá trị identifying về mặt cấu trúc, nhưng ứng dụng cần validator để từ chối dữ liệu không hợp lệ.

Spring Batch hỗ trợ `JobParametersValidator` để kiểm tra tham số trước khi job thực hiện. Ví dụ, có thể kiểm tra tham số bắt buộc như ngày nghiệp vụ và file đầu vào:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(parameters -> {
                String businessDate = parameters.getString("businessDate");
                String inputFile = parameters.getString("inputFile");

                if (businessDate == null || businessDate.isBlank()) {
                    throw new JobParametersInvalidException(
                            "businessDate is required");
                }
                if (inputFile == null || inputFile.isBlank()) {
                    throw new JobParametersInvalidException(
                            "inputFile is required");
                }
            })
            .start(importOrdersStep)
            .build();
}
```

Ví dụ trên dùng lambda để minh họa cách kiểm tra. Trong ứng dụng thực tế, có thể tách validator thành bean riêng, kiểm tra định dạng ngày, file có tồn tại, phạm vi dữ liệu có hợp lệ và người gọi có quyền xử lý hay không.

Việc một tham số là identifying không có nghĩa tham số đó bắt buộc phải có. Việc một tham số là non-identifying cũng không có nghĩa nó không cần validate. Hai khái niệm phục vụ hai mục đích khác nhau.

## 8. Chọn identifying parameters theo đơn vị nghiệp vụ

Việc chọn tham số định danh nên bắt đầu từ câu hỏi: “Một lần xử lý logic trong nghiệp vụ được nhận diện bằng những thông tin nào?”. Không nên quyết định chỉ dựa vào việc có sẵn giá trị nào trong request.

Ví dụ về một số job:

| Loại job | Identifying parameters có thể dùng | Lý do |
|---|---|---|
| Import đơn hàng hằng ngày | `businessDate`, `sourceSystem` | Mỗi ngày và nguồn dữ liệu là một đơn vị import. |
| Import một file được tải lên | `batchId` hoặc mã file bất biến | Mỗi file/batch cần được xử lý đúng một lần logic. |
| Đối soát tài khoản | `businessDate`, `accountGroup` | Phân biệt kỳ đối soát và phạm vi tài khoản. |
| Tạo báo cáo theo tháng | `reportMonth`, `reportType` | Mỗi loại báo cáo cho một tháng là một đơn vị công việc. |
| Đồng bộ theo khoảng ID | `fromId`, `toId`, `sourceSystem` | Phân biệt phạm vi bản ghi được xử lý. |

Không có một bộ tham số chung cho mọi job. Cần chọn giá trị đủ để phân biệt hai tập dữ liệu hoặc hai lần xử lý logic độc lập, đồng thời giữ ổn định khi restart.

### Dùng đường dẫn file làm tham số định danh

Đường dẫn file có thể là identifying parameter nếu đường dẫn đó đại diện ổn định cho một file đầu vào. Tuy nhiên, cần chú ý trường hợp file bị ghi đè:

- Lần đầu `data/orders.csv` chứa dữ liệu A và job thất bại.
- Sau đó file cùng đường dẫn bị thay bằng dữ liệu B.
- Lần chạy lại dùng cùng identifying parameter `inputFile=data/orders.csv`.

Spring Batch vẫn nhận diện cùng JobInstance, dù nội dung file đã thay đổi. Điều này có thể làm checkpoint cũ không còn phù hợp với dữ liệu mới. Với file có thể bị thay thế, nên dùng mã batch bất biến, phiên bản file hoặc checksum nội dung như một phần identity; đồng thời lưu trữ file đầu vào bất biến trong suốt vòng đời restart.

## 9. Chuẩn hóa giá trị tham số để identity ổn định

Hai giá trị có cùng ý nghĩa nghiệp vụ nhưng biểu diễn khác nhau vẫn có thể tạo identity khác nhau. Ví dụ:

```text
businessDate = 2026-11-15
businessDate = 15/11/2026
```

Nếu ứng dụng truyền hai chuỗi này như các giá trị khác nhau, Spring Batch có thể xem chúng là hai giá trị identifying khác nhau. Tương tự, các trường hợp khác biệt về chữ hoa/chữ thường, khoảng trắng hoặc múi giờ cũng cần được xử lý nhất quán theo quy ước của ứng dụng.

Một số nguyên tắc:

- Dùng định dạng chuẩn cho ngày và thời gian, chẳng hạn biểu diễn ISO nhất quán.
- Chuẩn hóa mã hệ thống, mã khách hàng hoặc mã batch trước khi tạo parameters.
- Loại bỏ khoảng trắng thừa nếu khoảng trắng không mang ý nghĩa nghiệp vụ.
- Xác định múi giờ rõ ràng khi tham số có thành phần thời gian.
- Không dùng đường dẫn tạm thời thay đổi theo từng lần tải lên nếu nó không phải identity nghiệp vụ.
- Không tái sử dụng cùng một identity cho những nội dung đầu vào khác nhau.

Chuẩn hóa giúp tránh tạo JobInstance trùng về mặt nghiệp vụ nhưng khác nhau về cách biểu diễn tham số.

## 10. Timestamp và UUID: khi nào nên dùng?

Một lỗi thường gặp là thêm timestamp hoặc UUID mới vào mọi lần gọi JobLauncher và đánh dấu nó là identifying:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("requestId", UUID.randomUUID().toString(), true)
        .toJobParameters();
```

Vì `requestId` thay đổi mỗi lần gọi, mỗi yêu cầu tạo một JobInstance mới. Cách này có thể phù hợp nếu mỗi request thực sự là một đơn vị xử lý độc lập và cần được chạy riêng. Nhưng nếu mục tiêu là restart một instance đã thất bại, cách làm này khiến ứng dụng không còn dùng lại identity cũ.

Nếu UUID chỉ phục vụ trace hoặc ghi nhận yêu cầu, có thể đánh dấu non-identifying:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("requestId", UUID.randomUUID().toString(), false)
        .toJobParameters();
```

Tuy nhiên, hãy chắc chắn `requestId` không làm thay đổi tập dữ liệu hoặc logic nghiệp vụ. Nếu mỗi request UUID đại diện cho một lần xử lý độc lập có ý nghĩa, nó nên tham gia định danh. Nếu chỉ là mã theo dõi lần tiếp nhận, nó thường nên là non-identifying.

## 11. Chạy mới, restart và chạy lại cùng dữ liệu

Ba yêu cầu này cần được phân biệt rõ:

### Chạy mới cho đơn vị dữ liệu khác

Ví dụ, job nhập đơn hàng đã xử lý ngày 15/11 và cần xử lý ngày 16/11. Hãy truyền `businessDate=2026-11-16` nếu ngày là identifying. Spring Batch tạo JobInstance mới.

### Restart một instance thất bại

Nếu job cho ngày 15/11 thất bại, hãy dùng lại cùng tên job và các identifying parameters của lần chạy đó. Spring Batch tạo JobExecution mới cho cùng JobInstance nếu trạng thái và cấu hình cho phép.

### Xử lý lại cùng dữ liệu theo một yêu cầu nghiệp vụ mới

Đôi khi nghiệp vụ yêu cầu chạy lại dữ liệu đã hoàn tất, ví dụ chạy lại báo cáo sau khi thay đổi thuật toán hoặc thực hiện một đợt tái xử lý có kiểm soát. Đây là một đơn vị xử lý mới theo nghiệp vụ, không phải restart execution cũ. Cần có tham số identifying bổ sung như `reprocessVersion`, `reprocessBatchId` hoặc một mã lần xử lý được cấp rõ ràng.

Không nên xóa metadata của JobInstance đã hoàn tất chỉ để gọi lại cùng tham số. Làm như vậy có thể mất lịch sử và khiến framework không còn nhận diện được quan hệ giữa các lần thực thi.

## 12. JobParametersIncrementer và việc tạo identity tiếp theo

Một số job cần tạo JobInstance mới cho mỗi lần chạy, dù các tham số nghiệp vụ khác không thay đổi. Spring Batch có `JobParametersIncrementer` để hỗ trợ sinh bộ tham số tiếp theo dựa trên bộ tham số trước đó.

Một ví dụ quen thuộc là `RunIdIncrementer`, thường dùng để tăng tham số `run.id`:

```java
@Bean
Job reportJob(JobRepository jobRepository, Step reportStep) {
    return new JobBuilder("reportJob", jobRepository)
            .start(reportStep)
            .incrementer(new RunIdIncrementer())
            .build();
}
```

Incrementer mô tả cách tạo bộ tham số cho một instance tiếp theo khi được gọi bởi API hoặc thành phần điều phối hỗ trợ cơ chế này, chẳng hạn thao tác start-next-instance của `JobOperator`. Chỉ khai báo incrementer không có nghĩa mọi lời gọi `JobLauncher.run(job, parameters)` sẽ tự động tăng `run.id`; khi gọi JobLauncher trực tiếp, ứng dụng vẫn truyền bộ JobParameters cụ thể.

`run.id` thường là identifying parameter. Khi giá trị tăng, JobInstance mới được tạo. Đây là cách phù hợp cho các lần chạy logic độc lập có chủ đích, nhưng không nên tăng run ID khi muốn restart instance đang thất bại.

## 13. JobParameters khác ExecutionContext như thế nào?

Hai thành phần này đều có thể chứa dữ liệu key-value nhưng phục vụ mục đích khác nhau.

| Tiêu chí | `JobParameters` | `ExecutionContext` |
|---|---|---|
| Nguồn tạo | Được cung cấp khi khởi chạy job. | Được job/step cập nhật trong quá trình thực thi. |
| Mục đích | Mô tả đầu vào của một lần xử lý và xác định JobInstance qua identifying parameters. | Lưu trạng thái runtime và checkpoint để hỗ trợ restart hoặc trao đổi metadata giữa các step. |
| Thời điểm | Có trước khi job bắt đầu. | Được cập nhật trong quá trình chạy. |
| Ví dụ | Ngày nghiệp vụ, file đầu vào, hệ thống nguồn. | Dòng file đã đọc, tên file trung gian, số lượng đã xử lý. |

Ví dụ, `businessDate` là JobParameter vì nó xác định kỳ nghiệp vụ. `currentLine` có thể là giá trị trong Step ExecutionContext vì nó thể hiện tiến độ reader. Không nên dùng ExecutionContext để thay thế tham số định danh đầu vào hoặc dùng JobParameters để lưu checkpoint thay đổi liên tục.

## 14. JobRepository lưu và tra cứu identity

Spring Batch sử dụng `JobRepository` để lưu metadata của JobInstance và các execution. Trong cấu hình dùng cơ sở dữ liệu, repository ghi thông tin vào các bảng metadata của framework.

Khi JobLauncher nhận yêu cầu, JobRepository giúp xác định JobInstance tương ứng dựa trên tên job và identifying parameters. Repository cũng quản lý việc tạo JobExecution, lưu trạng thái và hỗ trợ truy vấn lịch sử.

Điều này có một hệ quả vận hành: nếu metadata bị xóa hoặc repository không bền vững, framework có thể mất khả năng nhận diện instance trước đó. Trong môi trường cần restart qua lần khởi động ứng dụng, nên dùng JobRepository lưu metadata bền vững và giữ schema phù hợp với phiên bản Spring Batch.

JobRepository không tự bảo đảm dữ liệu nghiệp vụ không bị trùng. Nó quản lý identity và trạng thái thực thi của framework. Các ràng buộc unique, idempotency và kiểm soát đồng thời ở bảng nghiệp vụ vẫn do ứng dụng thiết kế.

## 15. Các lỗi thiết kế JobParameters thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đánh dấu UUID mới là identifying trong mọi lần chạy | Mỗi request tạo một JobInstance mới; restart không tìm lại instance cũ. | Chỉ dùng UUID làm identifying khi nó đại diện cho đơn vị xử lý độc lập. |
| Đưa tham số ảnh hưởng dữ liệu vào nhóm non-identifying | Hai tập dữ liệu khác nhau có thể bị coi là cùng JobInstance. | Đưa mọi thuộc tính cần phân biệt dữ liệu vào identifying parameters. |
| Dùng cùng identifying parameters cho nhiều kỳ nghiệp vụ | Yêu cầu sau có thể gặp lỗi instance đã hoàn tất hoặc đang chạy. | Bổ sung giá trị định danh phản ánh đúng kỳ hoặc phạm vi xử lý. |
| Thay đổi định dạng tham số giữa các lần chạy | Cùng ý nghĩa nghiệp vụ có thể tạo nhiều instance khác nhau. | Chuẩn hóa định dạng trước khi xây dựng JobParameters. |
| Dùng file có thể bị ghi đè làm đầu vào định danh | Restart có thể đọc nội dung mới với checkpoint cũ. | Lưu file bất biến và định danh theo batch ID hoặc phiên bản/checksum. |
| Nghĩ identifying đồng nghĩa với required | Thiếu tham số có thể vẫn tạo được bộ parameters nếu không có validator. | Dùng JobParametersValidator để kiểm tra tham số bắt buộc và định dạng. |
| Nghĩ non-identifying là không được sử dụng trong job | Bỏ lỡ thông tin theo dõi cần thiết. | Dùng non-identifying cho metadata không làm thay đổi đơn vị xử lý. |
| Tự thêm run ID khi restart | Vô tình tạo instance mới thay vì tiếp tục instance cũ. | Giữ nguyên identity khi restart; chỉ tăng run ID cho lần xử lý mới. |

## 16. Quy trình thiết kế identifying parameters

Khi xây dựng một job mới, có thể thực hiện theo các bước sau:

1. **Xác định đơn vị xử lý nghiệp vụ:** ví dụ một file, một ngày, một nhóm tài khoản hoặc một phạm vi ID.
2. **Liệt kê dữ liệu đầu vào ảnh hưởng đến kết quả:** xác định những giá trị nào khiến hai lần chạy trở thành hai công việc logic khác nhau.
3. **Chọn identifying parameters:** đưa các giá trị cần phân biệt đơn vị xử lý vào nhóm identifying.
4. **Chọn non-identifying parameters:** thêm thông tin trace, người yêu cầu hoặc ghi chú vận hành nếu cần mà không làm thay đổi identity.
5. **Chuẩn hóa giá trị:** thống nhất định dạng ngày, mã, đường dẫn, múi giờ và cách biểu diễn phạm vi dữ liệu.
6. **Xây dựng validator:** kiểm tra tham số bắt buộc, kiểu dữ liệu và quy tắc nghiệp vụ trước khi chạy.
7. **Xác định hành vi chạy lại:** làm rõ trường hợp nào là chạy mới, trường hợp nào là restart và trường hợp nào là tái xử lý có chủ đích.
8. **Kiểm tra repository:** bảo đảm metadata được lưu bền vững và các instance ứng dụng nhìn thấy trạng thái nhất quán.
9. **Kiểm tra tác dụng phụ:** bảo đảm restart hoặc chạy lại không tạo dữ liệu trùng lặp trong hệ thống nghiệp vụ.

Ví dụ một bộ tham số hoàn chỉnh:

```java
JobParameters parameters = new JobParametersBuilder()
        // Xác định kỳ nghiệp vụ và nguồn dữ liệu.
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSystem", "ERP", true)
        .addString("batchId", "ERP-20261115-001", true)

        // Chỉ phục vụ theo dõi yêu cầu.
        .addString("requestedBy", "nightly-scheduler", false)
        .addString("requestId", "REQ-83921", false)
        .toJobParameters();
```

Ở đây, ngày nghiệp vụ, hệ thống nguồn và batch ID xác định tập dữ liệu cần xử lý. Người yêu cầu và request ID chỉ hỗ trợ theo dõi. Nếu muốn restart, ứng dụng dùng lại các identifying parameters này. Nếu muốn xử lý một batch khác, batch ID hoặc một identifying value phù hợp phải thay đổi.

## 17. Những điểm cần ghi nhớ

- `JobInstance` được xác định bởi tên `Job` và các `JobParameters` có `identifying=true`.
- Thay đổi identifying parameter tạo JobInstance mới; thay đổi non-identifying parameter không làm thay đổi identity.
- Một JobInstance có thể có nhiều JobExecution qua các lần restart.
- Muốn restart, phải dùng lại đúng tên job và các identifying parameters của instance đã thất bại.
- Không nên thêm timestamp hoặc UUID thay đổi ở mọi lần chạy vào identifying parameters nếu mục tiêu là restart.
- Tham số ảnh hưởng đến tập dữ liệu hoặc kết quả nghiệp vụ thường phải tham gia định danh.
- Identifying không đồng nghĩa với required; hãy dùng JobParametersValidator để kiểm tra tham số bắt buộc và tính hợp lệ.
- Chuẩn hóa giá trị tham số và giữ dữ liệu đầu vào bất biến để restart không dùng nhầm dữ liệu.
- `JobParameters` là đầu vào của job; `ExecutionContext` lưu trạng thái runtime và checkpoint.
- `JobParametersIncrementer` có thể tạo bộ tham số cho một instance tiếp theo khi được API điều phối phù hợp sử dụng; JobLauncher không tự tăng tham số chỉ vì job có incrementer.

Khi đọc code một ứng dụng Spring Batch, hãy tìm nơi tạo `JobParameters`, kiểm tra cờ identifying của từng giá trị và đối chiếu chúng với đơn vị dữ liệu nghiệp vụ. Từ đó có thể hiểu vì sao một yêu cầu tạo JobInstance mới, vì sao yêu cầu khác được xem là restart, và làm thế nào để thiết kế tham số ổn định cho cả vận hành lẫn khôi phục sau lỗi.
